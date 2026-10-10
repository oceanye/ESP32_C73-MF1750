from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState, ValidatedProductionProfile
from host.visible_refresh_campaign import production_profile as production
from tools import g1_s1_n3_analyzer as n3_legacy
from tools import g1_s1_n3b_physical_analyzer as n3
from tools import g1_s1_n4_v3_analyzer as n4_legacy
from tools import g1_s1_n4_v3_physical_analyzer as n4


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-PHYSICAL-ANALYZER-TEST",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
FIRMWARE = {
    "build_tag": "mf1750-g1-s1-rc2g",
    "binary_sha256": hashlib.sha256(b"firmware").hexdigest(),
}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _artifact(label: str) -> production.ArtifactSnapshot:
    payload = label.encode("utf-8")
    return production.ArtifactSnapshot(
        path=Path(f"/{label}.json"),
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _profile(
    action_key: str,
    usage: dict[str, object],
) -> ValidatedProductionProfile:
    authority = {
        "issuer": "physical-analyzer-test-owner",
        "policy_id": "common-reviewed-process-policy",
    }
    inputs = production.ProductionInputs(
        campaign={},
        campaign_file=_artifact("common-campaign"),
        firmware_binary=_artifact("common-firmware-binary"),
        supplier_limits=authority,
        supplier_limits_file=_artifact("common-limit-authority"),
        usage_evidence={},
        usage_evidence_file=_artifact(f"usage-{action_key}"),
    )
    return ValidatedProductionProfile(
        profile={
            "panel": PANEL,
            "firmware": FIRMWARE,
            "profile_id": "common-physical-profile",
            "profile_version": "1.0.0",
            "review": {"reviewer_id": "physical-analyzer-test-reviewer"},
            "usage": usage,
            "integrity": {"canonical_sha256": _sha(f"profile-{action_key}")},
        },
        profile_file=_artifact(f"profile-file-{action_key}"),
        inputs=inputs,
        review_artifact={},
        review_artifact_file=_artifact(f"review-{action_key}"),
        reviewer_key_id=_sha("common-reviewer-key"),
        report={
            "evaluated_at": f"2026-08-08T{action_key[-2:]}:00:00Z",
            "limit_authority_kind": "supervised-experimental-process-policy",
            "limit_authority_classification": (
                "supervised-experimental-process-authority"
            ),
        },
    )


def _usage(
    cumulative: int,
    *,
    session: int,
    consecutive: int,
    last_completed_at: str | None,
) -> dict[str, object]:
    return {
        "cumulative_visible_refresh_count": cumulative,
        "session_visible_refresh_count": session,
        "consecutive_visible_refresh_count": consecutive,
        "last_visible_refresh_completed_at": last_completed_at,
        "snapshot_at": "2026-08-08T00:00:00Z",
    }


def _validated(action_key: str, completed_at: str) -> dict[str, object]:
    return {
        "action_identity_sha256": _sha(f"action-{action_key}"),
        "attempt_id": f"attempt-{action_key}",
        "result_file_sha256": _sha(f"result-{action_key}"),
        "finalization_file_sha256": _sha(f"finalization-{action_key}"),
        "state": ResultState.PASS.value,
        "result": {
            "state": ResultState.PASS.value,
            "completed_at": completed_at,
        },
        "observation": {},
    }


def _bundle(action_key: str, validated: dict[str, object]) -> dict[str, object]:
    return {
        "validated": validated,
        "observation": {
            "source_observation_file_sha256": _sha(f"source-{action_key}"),
            "camera": {"capture_file_sha256": None},
        },
    }


class N3BPhysicalAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        orders = (
            ("Q1", "Q2", "Q4", "Q3"),
            ("Q2", "Q3", "Q1", "Q4"),
            ("Q3", "Q4", "Q2", "Q1"),
            ("Q4", "Q1", "Q3", "Q2"),
        )
        routes = []
        for block_index, order in enumerate(orders, start=1):
            for position, candidate in enumerate(order, start=1):
                stem = f"b{block_index}s{position}"
                routes.append(
                    {
                        "block_index": block_index,
                        "session_position": position,
                        "candidate_cell_id": candidate,
                        "cell_id": f"cell-{candidate}",
                        "session_id": f"session-{stem}",
                        "map_action_key": f"{stem}-map",
                        "target_action_key": f"{stem}-target",
                    }
                )
        cls.plan = {
            "kind": n3.physical.PLAN_KIND,
            "plan_id": "n3b-physical-analyzer-test",
            "integrity": {"canonical_sha256": _sha("n3b-plan")},
            "selected_routes": routes,
            "execution_manifest": {"panel": PANEL, "firmware": FIRMWARE},
            "process_schedule": {
                "classification": "operator_selected_experimental_process_schedule",
                "not_a_supplier_rating": True,
                "minimum_interval_seconds": 150.0,
                "planned_cooldown_seconds": 150.0,
            },
        }
        cls.context = SimpleNamespace(plan=cls.plan)
        cls.sessions = cls._sessions()

    @classmethod
    def _sessions(cls) -> tuple[n3.N3BPhysicalSessionEvidence, ...]:
        result = []
        prior_completed_at = None
        baseline = 40
        for index, route in enumerate(cls.plan["selected_routes"]):
            map_key = route["map_action_key"]
            target_key = route["target_action_key"]
            map_completed = f"2026-08-08T{index:02d}:01:00Z"
            target_completed = f"2026-08-08T{index:02d}:06:00Z"
            map_validated = _validated(map_key, map_completed)
            target_validated = _validated(target_key, target_completed)
            map_bundle = _bundle(map_key, map_validated)
            target_bundle = _bundle(target_key, target_validated)
            target_bundle["observation"]["camera"][
                "capture_file_sha256"
            ] = _sha(f"capture-{target_key}")
            map_profile = _profile(
                map_key,
                _usage(
                    baseline + 2 * index,
                    session=0,
                    consecutive=0,
                    last_completed_at=prior_completed_at,
                ),
            )
            target_profile = _profile(
                target_key,
                _usage(
                    baseline + 2 * index + 1,
                    session=1,
                    consecutive=1,
                    last_completed_at=map_completed,
                ),
            )
            unsigned = {
                "schema_version": n3.SCHEMA_VERSION,
                "kind": n3.runner.SESSION_KIND,
                "plan_canonical_sha256": cls.plan["integrity"][
                    "canonical_sha256"
                ],
                "session_id": route["session_id"],
                "cell_id": route["cell_id"],
                "map_action_identity_sha256": map_validated[
                    "action_identity_sha256"
                ],
                "map_result_file_sha256": map_validated["result_file_sha256"],
                "map_finalization_file_sha256": map_validated[
                    "finalization_file_sha256"
                ],
                "target_action_identity_sha256": target_validated[
                    "action_identity_sha256"
                ],
                "target_result_file_sha256": target_validated[
                    "result_file_sha256"
                ],
                "target_finalization_file_sha256": target_validated[
                    "finalization_file_sha256"
                ],
                "target_state": ResultState.PASS.value,
                "map_target_continuity_deep_validated": True,
                "automatic_inference": False,
            }
            observation = {
                **unsigned,
                "integrity": {
                    "canonical_sha256": n3._sha256(unsigned),
                    "canonical_sha256_scope": (
                        "entire physical N3B session observation excluding "
                        "integrity; canonical JSON"
                    ),
                },
            }
            result.append(
                n3.N3BPhysicalSessionEvidence(
                    map_bundle=map_bundle,
                    target_bundle=target_bundle,
                    map_production=map_profile,
                    target_production=target_profile,
                    physical_session_observation=observation,
                )
            )
            prior_completed_at = target_completed
        return tuple(result)

    def _derived(self, _context, _map, target):
        target_sha = target["action_identity_sha256"]
        route = next(
            route
            for route in self.plan["selected_routes"]
            if _sha(f"action-{route['target_action_key']}") == target_sha
        )
        value = float(route["block_index"] * 10 + route["session_position"])
        return {
            "pair_state": "complete-pass-pair",
            "candidate_cell_id": route["candidate_cell_id"],
            "session_position": route["session_position"],
            "timing": {
                phase: {field: value for field in n3_legacy.TIMING_FIELDS}
                for phase in ("map", "target")
            },
            "temperature": {
                field: 25.0 + value / 100
                for field in n3_legacy.TEMPERATURE_FIELDS
            },
            "visual": {
                "photo_difference_score": value / 100,
                "photo_luminance_mean": 120.0 + value,
                "photo_luminance_standard_deviation": 2.0 + value / 100,
            },
        }

    def _patches(self):
        return (
            mock.patch.object(
                n3.physical,
                "validate_n3b_physical_execution_context",
                return_value=self.plan,
            ),
            mock.patch.object(
                n3.physical,
                "n3b_physical_plan_file_sha256",
                return_value=_sha("n3b-plan-file"),
            ),
            mock.patch.object(
                n3.physical,
                "validate_n3b_physical_finalized_action_bundle",
                side_effect=lambda _context, bundle, **_kwargs: bundle["validated"],
            ),
            mock.patch.object(n3, "_derived_observation", side_effect=self._derived),
        )

    def test_complete_williams_evidence_is_descriptive_only(self) -> None:
        context_patch, plan_hash_patch, deep_patch, derived_patch = self._patches()
        with context_patch, plan_hash_patch, deep_patch as deep, derived_patch:
            report = n3.analyze_n3b_physical_sessions(
                self.context, sessions=self.sessions
            )
            n3.validate_n3b_physical_analysis_report(
                report, self.context, sessions=self.sessions
            )
        self.assertEqual(deep.call_count, 64)
        self.assertEqual(report["verified_visible_action_count"], 32)
        self.assertTrue(report["williams_design"]["each_candidate_once_per_position"])
        self.assertTrue(
            report["williams_design"][
                "each_ordered_immediate_predecessor_once"
            ]
        )
        self.assertEqual(report["camera_comparability"]["target_capture_count"], 16)
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertFalse(
            report["inference_contract"]["hardware_qualification_allowed"]
        )

    def test_duplicate_or_tampered_session_evidence_fails_closed(self) -> None:
        duplicate_bundle = deepcopy(self.sessions[-1].map_bundle)
        duplicate_bundle["observation"]["source_observation_file_sha256"] = (
            self.sessions[0].map_bundle["observation"][
                "source_observation_file_sha256"
            ]
        )
        duplicated = list(self.sessions)
        duplicated[-1] = replace(
            duplicated[-1], map_bundle=duplicate_bundle
        )
        context_patch, plan_hash_patch, deep_patch, derived_patch = self._patches()
        with (
            context_patch,
            plan_hash_patch,
            deep_patch,
            derived_patch,
            self.assertRaisesRegex(n3.N3BPhysicalAnalysisError, "duplicate"),
        ):
            n3.analyze_n3b_physical_sessions(self.context, sessions=duplicated)

        tampered_observation = deepcopy(
            self.sessions[0].physical_session_observation
        )
        tampered_observation["automatic_inference"] = True
        tampered = list(self.sessions)
        tampered[0] = replace(
            tampered[0], physical_session_observation=tampered_observation
        )
        context_patch, plan_hash_patch, deep_patch, derived_patch = self._patches()
        with (
            context_patch,
            plan_hash_patch,
            deep_patch,
            derived_patch,
            self.assertRaisesRegex(
                n3.N3BPhysicalAnalysisError, "does not match the deep pair"
            ),
        ):
            n3.analyze_n3b_physical_sessions(self.context, sessions=tampered)


class N4V3PhysicalAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = {"integrity": {"canonical_sha256": _sha("n4-contract")}}
        cls.context = SimpleNamespace(
            contract=cls.contract,
            physical_campaign={"panel": PANEL, "firmware": FIRMWARE},
            rebind_manifest={
                "integrity": {"canonical_sha256": _sha("n4-rebind")},
                "binding": {
                    "reviewed_schedule": {
                        "classification": (
                            "operator_selected_experimental_process_schedule"
                        ),
                        "not_a_supplier_rating": True,
                        "minimum_interval_seconds": 150.0,
                        "planned_cooldown_seconds": 150.0,
                    }
                },
            },
        )
        cls.cells = cls._cells()

    @classmethod
    def _cells(cls) -> tuple[n4.N4V3PhysicalCellEvidence, ...]:
        result = []
        prior_completed_at = None
        baseline = 80
        for index, cell_id in enumerate(n4_legacy.CELL_ORDER):
            map_key = f"{cell_id}-map-primer"
            target_key = f"{cell_id}-target"
            map_completed = f"2026-08-08T{index * 2:02d}:01:00Z"
            target_completed = f"2026-08-08T{index * 2 + 1:02d}:01:00Z"
            map_validated = _validated(map_key, map_completed)
            target_validated = _validated(target_key, target_completed)
            visual = {
                "observation_kind": "standardized-manual",
                "protocol_sha256": _sha("n4-visual-protocol"),
                "observation_evidence_sha256": _sha(f"visual-{cell_id}"),
                "reference_preview_sha256": _sha(f"preview-{cell_id}"),
                "observer_or_camera_asset_sha256": _sha("n4-observer"),
                "capture_file_sha256": None,
                "fixed_exposure_profile_sha256": None,
                "roi_definition_sha256": _sha("n4-roi"),
                "map_fidelity_pass": True,
                "target_fidelity_pass": True,
                "orientation_pass": True,
                "seam_assessment_pass": True,
                "fidelity_score": 0.90 + index / 100,
                "ghosting_score": 0.04 + index / 100,
                "artifact_severity_score": 0.02 + index / 100,
            }
            timing = {field: 100.0 + index for field in n4_legacy.TIMING_FIELDS}
            electrical = {
                "meter_asset_sha256": _sha("n4-meter"),
                "clock_asset_sha256": _sha("n4-clock"),
                "map": {
                    "pre_voltage_v": 3.3,
                    "post_voltage_v": 3.3,
                    "peak_current_a": 0.1 + index / 100,
                    "constant_voltage_mode": True,
                    "timing_ms": timing,
                },
                "target": {
                    "pre_voltage_v": 3.3,
                    "post_voltage_v": 3.29,
                    "peak_current_a": 0.2 + index / 100,
                    "constant_voltage_mode": True,
                    "timing_ms": timing,
                },
                "external_temperature": {
                    "session_max_c": 26.0 + index / 10,
                    "uncertainty_u95_c": 0.5,
                    "sensor_asset_sha256": _sha("n4-sensor"),
                    "calibration_artifact_sha256": _sha("n4-calibration"),
                    "map_measurement_evidence_sha256": _sha(
                        f"map-temperature-{cell_id}"
                    ),
                    "target_measurement_evidence_sha256": _sha(
                        f"target-temperature-{cell_id}"
                    ),
                    "uncertainty_evidence_sha256": _sha("n4-uncertainty"),
                },
                "reviewed_limits_pass": True,
                "thermal_limits_pass": True,
                "continuity": {
                    "controller_reboot_between_actions": False,
                    "panel_power_cycle_between_actions": False,
                    "j2_disconnect_between_actions": False,
                    "other_visible_refresh_between_actions": False,
                },
            }
            map_validated["derived_visual"] = visual
            map_validated["derived_electrical"] = electrical
            target_validated["derived_visual"] = visual
            target_validated["derived_electrical"] = electrical
            map_bundle = _bundle(map_key, map_validated)
            target_bundle = _bundle(target_key, target_validated)
            map_profile = _profile(
                map_key,
                _usage(
                    baseline + 2 * index,
                    session=0,
                    consecutive=0,
                    last_completed_at=prior_completed_at,
                ),
            )
            target_profile = _profile(
                target_key,
                _usage(
                    baseline + 2 * index + 1,
                    session=1,
                    consecutive=1,
                    last_completed_at=map_completed,
                ),
            )
            unsigned = {
                "schema_version": n4.SCHEMA_VERSION,
                "kind": n4.runner.CELL_OBSERVATION_KIND,
                "physical_execution_contract_canonical_sha256": cls.contract[
                    "integrity"
                ]["canonical_sha256"],
                "cell_id": cell_id,
                "map_action_identity_sha256": map_validated[
                    "action_identity_sha256"
                ],
                "map_result_file_sha256": map_validated["result_file_sha256"],
                "map_finalization_file_sha256": map_validated[
                    "finalization_file_sha256"
                ],
                "target_action_identity_sha256": target_validated[
                    "action_identity_sha256"
                ],
                "target_result_file_sha256": target_validated[
                    "result_file_sha256"
                ],
                "target_finalization_file_sha256": target_validated[
                    "finalization_file_sha256"
                ],
                "target_state": ResultState.PASS.value,
                "map_and_target_deep_validated": True,
                "automatic_inference": False,
            }
            observation = {
                **unsigned,
                "integrity": {
                    "canonical_sha256": n4._sha256(unsigned),
                    "canonical_sha256_scope": (
                        "entire physical N4 cell observation excluding integrity; "
                        "canonical JSON"
                    ),
                },
            }
            result.append(
                n4.N4V3PhysicalCellEvidence(
                    map_bundle=map_bundle,
                    target_bundle=target_bundle,
                    map_production=map_profile,
                    target_production=target_profile,
                    physical_cell_observation=observation,
                )
            )
            prior_completed_at = target_completed
        return tuple(result)

    def _patches(self):
        return (
            mock.patch.object(
                n4.physical,
                "validate_n4_physical_execution_context",
                return_value=self.contract,
            ),
            mock.patch.object(
                n4.physical,
                "n4_physical_execution_contract_file_sha256",
                return_value=_sha("n4-contract-file"),
            ),
            mock.patch.object(
                n4.physical,
                "validate_n4_physical_finalized_action_bundle",
                side_effect=lambda _context, bundle, **_kwargs: bundle["validated"],
            ),
            mock.patch.object(
                n4.physical,
                "load_n4_physical_action_snapshot",
                side_effect=lambda _context, action_key: SimpleNamespace(
                    reference_preview={
                        "sha256": _sha(
                            f"preview-{action_key.removesuffix('-target')}"
                        )
                    }
                ),
            ),
            mock.patch.object(
                n4.legacy_analyzer,
                "_derived_cell_measurements",
                side_effect=lambda _cell, map_value, _target: (
                    map_value["derived_visual"],
                    map_value["derived_electrical"],
                ),
            ),
        )

    def test_complete_2x2_evidence_keeps_visual_and_electrical_separate(self) -> None:
        patches = self._patches()
        with (
            patches[0],
            patches[1],
            patches[2] as deep,
            patches[3],
            patches[4],
        ):
            report = n4.analyze_n4_v3_physical_cells(
                self.context, cells=self.cells
            )
            n4.validate_n4_v3_physical_analysis_report(
                report, self.context, cells=self.cells
            )
        self.assertEqual(deep.call_count, 16)
        self.assertEqual(report["verified_visible_action_count"], 8)
        self.assertTrue(report["analysis_ready"])
        self.assertIsNone(report["visual_electrical_joint_conclusion"])
        self.assertEqual(set(report["visual_analysis"]), set(n4_legacy.VISUAL_METRICS))
        self.assertEqual(
            set(report["electrical_analysis"]), set(n4_legacy.ELECTRICAL_METRICS)
        )
        self.assertEqual(
            report["camera_comparability"]["expected_camera_capture_count"], 0
        )
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")

    def test_duplicate_and_wrong_camera_cardinality_fail_closed(self) -> None:
        duplicate_bundle = deepcopy(self.cells[-1].target_bundle)
        duplicate_bundle["observation"]["source_observation_file_sha256"] = (
            self.cells[0].map_bundle["observation"][
                "source_observation_file_sha256"
            ]
        )
        duplicated = list(self.cells)
        duplicated[-1] = replace(
            duplicated[-1], target_bundle=duplicate_bundle
        )
        patches = self._patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            self.assertRaisesRegex(n4.N4V3PhysicalAnalysisError, "duplicate"),
        ):
            n4.analyze_n4_v3_physical_cells(self.context, cells=duplicated)

        camera_cells = deepcopy(self.cells)
        for index, cell in enumerate(camera_cells):
            cell.map_bundle["validated"]["derived_visual"][
                "observation_kind"
            ] = "fixed-camera"
            cell.map_bundle["validated"]["derived_visual"][
                "fixed_exposure_profile_sha256"
            ] = _sha("fixed-exposure")
            cell.map_bundle["validated"]["derived_visual"][
                "capture_file_sha256"
            ] = _sha(f"derived-target-camera-{index}")
            cell.target_bundle["observation"]["camera"][
                "capture_file_sha256"
            ] = _sha(f"only-target-camera-{index}")
        patches = self._patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            self.assertRaisesRegex(
                n4.N4V3PhysicalAnalysisError, "camera capture count"
            ),
        ):
            n4.analyze_n4_v3_physical_cells(self.context, cells=camera_cells)


if __name__ == "__main__":
    unittest.main()
