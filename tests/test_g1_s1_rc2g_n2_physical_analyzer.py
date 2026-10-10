from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import (
    ResultState,
    build_result_record,
    canonical_json_bytes,
)
from tools import g1_s1_n2_physical_campaign as physical
from tools import g1_s1_rc2g_n2_photo_campaign as frozen
from tools import g1_s1_rc2g_n2_photo_campaign_once as legacy
from tools import g1_s1_rc2g_n2_physical_analyzer as analyzer
from tools import g1_s1_rc2g_n2_physical_once as runner


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-ANALYZER-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
REVIEW_BYTES = b"physical analyzer panel-binding review\n"
BASE_TIME = datetime(2026, 8, 8, tzinfo=timezone.utc)
MINIMUM_INTERVAL_SECONDS = 150
PLANNED_COOLDOWN_SECONDS = 150
ACTION_SPACING_SECONDS = 160


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sealed(unsigned: dict) -> dict:
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": "unit-test canonical scope",
        },
    }


class PhysicalAnalyzerFixture:
    def __init__(self, root: Path, operator: dict) -> None:
        self.root = root
        self.reviewer_key_file = root / "trusted-reviewer.key"
        self.reviewer_key_file.write_bytes(bytes(range(32)))
        self.operator = deepcopy(operator)
        self.campaign = self.operator["physical_campaign_contract"]
        self.action_by_key = {
            f"{action['identity']['cell_id'].lower()}-{action['identity']['phase']}": action
            for action in self.campaign["actions"]
        }
        self.allowlist = deepcopy(self.operator["limit_profile_draft"]["action_allowlist"])
        self.limits = {
            "maximum_campaign_visible_refreshes": 32,
            "maximum_session_visible_refreshes": 2,
            "maximum_consecutive_visible_refreshes": 2,
            "minimum_interval_seconds": MINIMUM_INTERVAL_SECONDS,
            "minimum_cooldown_seconds": PLANNED_COOLDOWN_SECONDS,
            "minimum_start_temperature_c": 10,
            "maximum_start_temperature_c": 40,
            "maximum_post_refresh_temperature_c": 45,
        }
        self.stable_hashes = {
            runner.COPIED_SOURCE_MANIFEST_FILENAME: _sha(b"source"),
            runner.COPIED_PANEL_FILENAME: _sha(b"panel"),
            runner.COPIED_BINDING_REVIEW_FILENAME: _sha(REVIEW_BYTES),
            runner.COPIED_FIRMWARE_FILENAME: self.campaign["firmware"][
                "binary_sha256"
            ],
        }
        self.directories: dict[str, Path] = {}
        self._build()

    def _write(self, path: Path, value: object) -> str:
        payload = canonical_json_bytes(value)
        path.write_bytes(payload)
        return _sha(payload)

    def _read(self, directory: Path, filename: str) -> dict:
        return json.loads((directory / filename).read_text(encoding="utf-8"))

    def _result(self, action_sha: str, completed_at: str, finalization: dict) -> dict:
        return build_result_record(
            action_identity_sha256=action_sha,
            state=ResultState.PASS,
            completed_at=completed_at,
            evidence_manifest_sha256=_sha(canonical_json_bytes(finalization)),
            post_request_count=1,
            details="synthetic deeply-validated physical analyzer fixture",
        )

    def _profile(
        self,
        *,
        index: int,
        key: str,
        previous_completed_at: str | None,
    ) -> tuple[dict, str, str]:
        phase = "map-primer" if key.endswith("map-primer") else "target"
        usage_file_sha = _sha(f"usage-{index}".encode())
        review_file_sha = _sha(f"review-{index}".encode())
        snapshot_at = (
            BASE_TIME
            if previous_completed_at is None
            else datetime.fromisoformat(previous_completed_at.replace("Z", "+00:00"))
            + timedelta(seconds=MINIMUM_INTERVAL_SECONDS)
        )
        unsigned = {
            "schema_version": 1,
            "kind": "mf1750-visible-refresh-limit-profile",
            "profile_id": f"n2p-physical-action-profile-{index}",
            "profile_version": f"1.0.{index}",
            "panel": deepcopy(self.campaign["panel"]),
            "firmware": deepcopy(self.campaign["firmware"]),
            "action_allowlist": deepcopy(self.allowlist),
            "limits": deepcopy(self.limits),
            "usage": {
                "cumulative_visible_refresh_count": index,
                "session_visible_refresh_count": 0 if phase == "map-primer" else 1,
                "consecutive_visible_refresh_count": 0 if phase == "map-primer" else 1,
                "last_visible_refresh_completed_at": previous_completed_at,
                "snapshot_at": _stamp(snapshot_at),
                "evidence_sha256": usage_file_sha,
            },
            "validity": {
                "valid_from": _stamp(BASE_TIME + timedelta(seconds=index)),
                "expires_at": _stamp(BASE_TIME + timedelta(days=1, seconds=index)),
            },
            "review": {
                "approved": True,
                "reviewer_id": "trusted-physical-analyzer-reviewer",
                "reviewed_at": _stamp(BASE_TIME - timedelta(minutes=1)),
                "review_artifact_sha256": review_file_sha,
            },
        }
        return _sealed(unsigned), usage_file_sha, review_file_sha

    def _camera(self, *, index: int, captured: bool) -> tuple[dict, dict | None]:
        if not captured:
            return (
                {
                    "capture_performed": False,
                    "file": None,
                    "sha256": None,
                    "camera_id": None,
                    "tripod_position_id": None,
                    "lighting_setup_id": None,
                    "exposure_mode": None,
                    "white_balance_mode": None,
                    "focus_mode": None,
                    "image_processing": None,
                    "full_panel_uncropped": None,
                },
                None,
            )
        capture_sha = _sha(f"camera-capture-{index}".encode())
        return (
            {
                "capture_performed": True,
                "file": f"capture-{index}.png",
                "sha256": capture_sha,
                "camera_id": "camera-body-1",
                "tripod_position_id": "tripod-mark-1",
                "lighting_setup_id": "lighting-1",
                "exposure_mode": "manual-1/60-f8-iso100",
                "white_balance_mode": "fixed-5500k",
                "focus_mode": "manual-fixed",
                "image_processing": "raw-neutral-v1",
                "full_panel_uncropped": True,
            },
            {
                "copied_file": runner.CAMERA_CAPTURE_FILENAME,
                "bytes": 128,
                "sha256": capture_sha,
                "decoded_format": "PNG",
                "width": 800,
                "height": 480,
                "source_path_recorded_but_not_trusted_after_copy": f"capture-{index}.png",
            },
        )

    def _build(self) -> None:
        operator_sha = _sha(canonical_json_bytes(self.operator))
        campaign_sha = _sha(canonical_json_bytes(self.campaign))
        primer_result_shas: dict[str, str] = {}
        previous_completed_at: str | None = None
        for index, key in enumerate(analyzer.EXPECTED_RESULT_KEYS):
            directory = self.root / key
            directory.mkdir()
            self.directories[key] = directory
            action = self.action_by_key[key]
            action_sha = action["action_identity_sha256"]
            cell_id = action["identity"]["cell_id"]
            phase = action["identity"]["phase"]
            profile, usage_sha, review_sha = self._profile(
                index=index,
                key=key,
                previous_completed_at=previous_completed_at,
            )
            profile_sha = self._write(
                directory / runner.COPIED_PROFILE_FILENAME, profile
            )
            authority = {
                "schema_version": 1,
                "kind": "mf1750-visible-refresh-supervised-experimental-process-policy",
                "not_a_supplier_rating": True,
                "supervised_only": True,
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "issuer": "trusted-physical-analyzer-reviewer",
                "policy_id": f"n2p-action-policy-{index}",
                "issued_at": _stamp(BASE_TIME + timedelta(seconds=index)),
                "panel_model": self.campaign["panel"]["model"],
                "maximum_usage_snapshot_age_seconds": 900,
                "limits": deepcopy(self.limits),
                "validity": deepcopy(profile["validity"]),
                "field_provenance": {
                    field: {
                        "classification": "operator_selected_conservative_process_gate",
                        "source_document_sha256": _sha(b"supplier-document"),
                    }
                    for field in self.limits
                },
            }
            authority_sha = self._write(
                directory / runner.COPIED_SUPPLIER_FILENAME, authority
            )
            self._write(directory / runner.COPIED_OPERATOR_FILENAME, self.operator)
            self._write(directory / runner.COPIED_CAMPAIGN_FILENAME, self.campaign)
            score = index // 2 + 2
            camera, camera_binding = self._camera(
                index=index, captured=phase == "target"
            )
            observation = {
                "schema_version": 1,
                "kind": runner.OBSERVATION_KIND,
                "action_key": key,
                "action_identity_sha256": action_sha,
                "observed_at": _stamp(
                    BASE_TIME
                    + timedelta(seconds=(index + 1) * ACTION_SPACING_SECONDS)
                ),
                "observer_id": "physical-analyzer-operator",
                "full_panel_inspected": True,
                "reference_preview_sha256": _sha(f"preview-{key}".encode()),
                "viewing_distance_cm": 60,
                "stable_lighting": True,
                "visual": (
                    {
                        dimension: score for dimension in analyzer.SCORE_DIMENSIONS
                    }
                    if phase == "target"
                    else {
                        "screen_matches_reference": True,
                        "orientation_correct": True,
                        "labels_legible": True,
                        "center_seam_correct": True,
                        "all_six_colors_present": True,
                        "no_retained_old_regions": True,
                    }
                ),
                "electrical": {},
                "post_refresh_temperature_c": 26,
                "camera": camera,
                "visual_pass": True,
                "electrical_pass": True,
                "post_refresh_temperature_pass": True,
                "overall_state": ResultState.PASS.value,
                "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
                "camera_observation_contract_sha256": (
                    legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
                ),
                "source_observation_file_sha256": _sha(f"observation-{key}".encode()),
                "verified_camera_evidence": camera_binding,
            }
            self._write(directory / runner.OBSERVATION_FILENAME, observation)
            finalization = {
                "kind": runner.FINALIZATION_KIND,
                "action_key": key,
                "action_identity_sha256": action_sha,
                "state": ResultState.PASS.value,
                "camera_capture_present_for_this_action": camera_binding is not None,
                "camera_capture_file_sha256": (
                    camera_binding["sha256"] if camera_binding else None
                ),
            }
            self._write(directory / runner.FINALIZATION_FILENAME, finalization)
            completed_at = observation["observed_at"]
            result = self._result(action_sha, completed_at, finalization)
            result_sha = self._write(directory / runner.P0_RESULT_FILENAME, result)
            if phase == "map-primer":
                primer_result_shas[cell_id] = result_sha
                prior_sha = None
            else:
                prior_sha = primer_result_shas[cell_id]
            claim = {
                "registry_id": "workspace-global-p0-action-claims-v1",
                "filename": f"{action_sha}.json",
                "file_sha256": _sha(f"claim-{index}".encode()),
                "attempt_id": f"physical-attempt-{index + 1}",
                "action_identity_sha256": action_sha,
                "state": "authorization_permanently_consumed_do_not_rerun",
            }
            snapshot_files = {
                filename: {"bytes": 1, "sha256": sha}
                for filename, sha in self.stable_hashes.items()
            }
            snapshot_files.update(
                {
                    runner.COPIED_OPERATOR_FILENAME: {
                        "bytes": 1,
                        "sha256": operator_sha,
                    },
                    runner.COPIED_CAMPAIGN_FILENAME: {
                        "bytes": 1,
                        "sha256": campaign_sha,
                    },
                    runner.COPIED_PROFILE_FILENAME: {
                        "bytes": 1,
                        "sha256": profile_sha,
                    },
                    runner.COPIED_SUPPLIER_FILENAME: {
                        "bytes": len(canonical_json_bytes(authority)),
                        "sha256": authority_sha,
                    },
                    runner.COPIED_USAGE_FILENAME: {
                        "bytes": 1,
                        "sha256": usage_sha,
                    },
                    runner.COPIED_PROFILE_REVIEW_FILENAME: {
                        "bytes": 1,
                        "sha256": review_sha,
                    },
                }
            )
            confirmations = (
                {"controller_fresh_boot": True}
                if phase == "map-primer"
                else {
                    "map_fidelity_from_same_cell_primer": True,
                    "esp32_not_restarted_since_primer": True,
                    "no_j2_disconnect_since_primer": True,
                    "no_panel_power_cycle_since_primer": True,
                    "no_other_visible_refresh_since_primer": True,
                }
            )
            evidence = {
                "action_key": key,
                "action_identity_sha256": action_sha,
                "cell_id": cell_id,
                "phase": phase,
                "attempt_id": claim["attempt_id"],
                "claim": claim,
                "prior_result_file_sha256": prior_sha,
                "operator_manifest_canonical_sha256": self.operator["integrity"][
                    "canonical_sha256"
                ],
                "campaign_canonical_sha256": self.campaign["integrity"][
                    "canonical_sha256"
                ],
                "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
                "profile_file_sha256": profile_sha,
                "reviewer_key_id": _sha(self.reviewer_key_file.read_bytes()),
                "snapshot_files": snapshot_files,
                "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
                "camera_observation_contract_sha256": (
                    legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
                ),
                "confirmations": confirmations,
            }
            self._write(directory / runner.EVIDENCE_FILENAME, evidence)
            lock = {
                "action_key": key,
                "action_identity_sha256": action_sha,
                "attempt_id": claim["attempt_id"],
                "claim": claim,
            }
            self._write(directory / runner.LOCK_FILENAME, lock)
            previous_completed_at = completed_at

    def validation(self, result_dir: Path, **kwargs) -> dict:
        if kwargs.get("reviewer_key_file") != self.reviewer_key_file:
            raise AssertionError("analyzer did not pass the trusted reviewer key")
        if kwargs.get("require_finalized") is not True:
            raise AssertionError("analyzer did not require finalized physical result")
        evidence = self._read(result_dir, runner.EVIDENCE_FILENAME)
        result = self._read(result_dir, runner.P0_RESULT_FILENAME)
        return {
            "schema_version": 1,
            "kind": runner.VALIDATION_KIND,
            "valid": True,
            "action_key": evidence["action_key"],
            "action_identity_sha256": evidence["action_identity_sha256"],
            "outcome": "protocol_verified_observation_pending",
            "finalized": True,
            "state": result["state"],
            "operator_manifest_canonical_sha256": evidence[
                "operator_manifest_canonical_sha256"
            ],
            "campaign_canonical_sha256": evidence["campaign_canonical_sha256"],
            "profile_canonical_sha256": evidence["profile_canonical_sha256"],
            "reviewer_key_id": evidence["reviewer_key_id"],
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }

    def rewrite(self, key: str, filename: str, value: dict) -> str:
        return self._write(self.directories[key] / filename, value)

    def mutate_profile(self, key: str, mutator) -> None:
        directory = self.directories[key]
        profile = self._read(directory, runner.COPIED_PROFILE_FILENAME)
        profile.pop("integrity", None)
        mutator(profile)
        profile = _sealed(profile)
        profile_sha = self.rewrite(key, runner.COPIED_PROFILE_FILENAME, profile)
        evidence = self._read(directory, runner.EVIDENCE_FILENAME)
        evidence["profile_canonical_sha256"] = profile["integrity"]["canonical_sha256"]
        evidence["profile_file_sha256"] = profile_sha
        evidence["snapshot_files"][runner.COPIED_PROFILE_FILENAME]["sha256"] = profile_sha
        evidence["snapshot_files"][runner.COPIED_USAGE_FILENAME]["sha256"] = profile[
            "usage"
        ]["evidence_sha256"]
        self.rewrite(key, runner.EVIDENCE_FILENAME, evidence)

    def mutate_camera_id(self, key: str, camera_id: str) -> None:
        observation = self._read(self.directories[key], runner.OBSERVATION_FILENAME)
        observation["camera"]["camera_id"] = camera_id
        self.rewrite(key, runner.OBSERVATION_FILENAME, observation)

    def set_target_scores(self, cell: int, score: int) -> None:
        key = f"q{cell}-target"
        observation = self._read(self.directories[key], runner.OBSERVATION_FILENAME)
        for dimension in analyzer.SCORE_DIMENSIONS:
            observation["visual"][dimension] = score
        self.rewrite(key, runner.OBSERVATION_FILENAME, observation)

    def mutate_common_campaign(self, mutator) -> None:
        campaign = deepcopy(self.campaign)
        mutator(campaign)
        unsigned_campaign = dict(campaign)
        unsigned_campaign.pop("integrity", None)
        campaign = _sealed(unsigned_campaign)
        operator = deepcopy(self.operator)
        operator["physical_campaign_contract"] = campaign
        unsigned_operator = dict(operator)
        unsigned_operator.pop("integrity", None)
        operator = _sealed(unsigned_operator)
        operator_sha = _sha(canonical_json_bytes(operator))
        campaign_sha = _sha(canonical_json_bytes(campaign))
        for key in analyzer.EXPECTED_RESULT_KEYS:
            self.rewrite(key, runner.COPIED_OPERATOR_FILENAME, operator)
            self.rewrite(key, runner.COPIED_CAMPAIGN_FILENAME, campaign)
            evidence = self._read(self.directories[key], runner.EVIDENCE_FILENAME)
            evidence["operator_manifest_canonical_sha256"] = operator["integrity"][
                "canonical_sha256"
            ]
            evidence["campaign_canonical_sha256"] = campaign["integrity"][
                "canonical_sha256"
            ]
            evidence["snapshot_files"][runner.COPIED_OPERATOR_FILENAME][
                "sha256"
            ] = operator_sha
            evidence["snapshot_files"][runner.COPIED_CAMPAIGN_FILENAME][
                "sha256"
            ] = campaign_sha
            self.rewrite(key, runner.EVIDENCE_FILENAME, evidence)

    def make_one_cross_campaign(self, key: str) -> None:
        directory = self.directories[key]
        campaign = self._read(directory, runner.COPIED_CAMPAIGN_FILENAME)
        campaign["campaign_id"] += "-other"
        campaign["integrity"]["canonical_sha256"] = _sha(b"other-campaign")
        operator = self._read(directory, runner.COPIED_OPERATOR_FILENAME)
        operator["physical_campaign_contract"] = campaign
        operator["operator_manifest_id"] += "-other"
        operator["integrity"]["canonical_sha256"] = _sha(b"other-operator")
        campaign_sha = self.rewrite(key, runner.COPIED_CAMPAIGN_FILENAME, campaign)
        operator_sha = self.rewrite(key, runner.COPIED_OPERATOR_FILENAME, operator)
        evidence = self._read(directory, runner.EVIDENCE_FILENAME)
        evidence["campaign_canonical_sha256"] = campaign["integrity"]["canonical_sha256"]
        evidence["operator_manifest_canonical_sha256"] = operator["integrity"][
            "canonical_sha256"
        ]
        evidence["snapshot_files"][runner.COPIED_CAMPAIGN_FILENAME][
            "sha256"
        ] = campaign_sha
        evidence["snapshot_files"][runner.COPIED_OPERATOR_FILENAME][
            "sha256"
        ] = operator_sha
        self.rewrite(key, runner.EVIDENCE_FILENAME, evidence)


class N2PhysicalAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = frozen.compile_campaign_manifest()
        review = physical._review_artifact_record(REVIEW_BYTES)
        cls.operator = physical._assemble_manifest(
            source,
            PANEL,
            review,
            physical._operator_process_schedule(
                MINIMUM_INTERVAL_SECONDS, PLANNED_COOLDOWN_SECONDS
            ),
        )

    def setUp(self) -> None:
        hardware = physical.REPO_ROOT / ".test-output" / "hardware"
        self.temporary = tempfile.TemporaryDirectory(dir=hardware)
        self.addCleanup(self.temporary.cleanup)
        self.fixture = PhysicalAnalyzerFixture(
            Path(self.temporary.name), self.operator
        )
        self.validator = mock.patch.object(
            analyzer.fixed,
            "validate_physical_result",
            side_effect=self.fixture.validation,
        )
        self.validator_mock = self.validator.start()
        self.addCleanup(self.validator.stop)

    def analyze(self) -> dict:
        return analyzer.analyze_n2p_physical_campaign(
            self.fixture.directories,
            reviewer_key_file=self.fixture.reviewer_key_file,
        )

    def test_unique_winner_is_physical_bound_and_calls_deep_validator(self) -> None:
        result = self.analyze()
        self.assertTrue(result["winner_gates"]["all_pass"])
        self.assertEqual(result["selected_winner"]["cell_id"], "Q4")
        self.assertEqual(result["selected_winner"]["score_total"], 30)
        self.assertTrue(result["camera_comparability"]["comparable"])
        self.assertEqual(len(result["validated_chains"]), 8)
        self.assertEqual(len(result["validated_sessions"]), 4)
        self.assertEqual(self.validator_mock.call_count, 8)
        analyzer.validate_n2p_physical_analysis(result)
        self.assertFalse(result["network_io_performed"])
        self.assertFalse(result["claim_created"])
        self.assertFalse(result["authorization_created"])

    def test_missing_extra_and_duplicate_directories_are_rejected(self) -> None:
        missing = dict(self.fixture.directories)
        missing.pop("q4-target")
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "exactly"):
            analyzer.analyze_n2p_physical_campaign(
                missing, reviewer_key_file=self.fixture.reviewer_key_file
            )
        extra = {**self.fixture.directories, "q5-target": next(iter(missing.values()))}
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "exactly"):
            analyzer.analyze_n2p_physical_campaign(
                extra, reviewer_key_file=self.fixture.reviewer_key_file
            )
        duplicate = dict(self.fixture.directories)
        duplicate["q4-target"] = duplicate["q3-target"]
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "duplication"):
            analyzer.analyze_n2p_physical_campaign(
                duplicate, reviewer_key_file=self.fixture.reviewer_key_file
            )

    def test_nested_prior_tamper_is_rejected(self) -> None:
        q2_primer_sha = self.fixture.action_by_key["q2-map-primer"][
            "action_identity_sha256"
        ]

        def tamper(campaign: dict) -> None:
            q1_target_sha = self.fixture.operator["fixed_actions"]["q1-target"]
            target = next(
                action
                for action in campaign["actions"]
                if action["action_identity_sha256"] == q1_target_sha
            )
            target["identity"]["prior"]["action_identity_sha256"] = q2_primer_sha

        self.fixture.mutate_common_campaign(tamper)
        with self.assertRaisesRegex(
            analyzer.N2PhysicalAnalysisError, "disjoint MAP-to-target"
        ):
            self.analyze()

    def test_cross_campaign_is_rejected(self) -> None:
        self.fixture.make_one_cross_campaign("q4-target")
        with self.assertRaisesRegex(
            analyzer.N2PhysicalAnalysisError, "same operator/campaign"
        ):
            self.analyze()

    def test_profile_safety_lineage_mismatch_is_rejected(self) -> None:
        self.fixture.mutate_profile(
            "q4-target",
            lambda profile: profile["limits"].__setitem__(
                "maximum_post_refresh_temperature_c", 44
            ),
        )
        with self.assertRaisesRegex(
            analyzer.N2PhysicalAnalysisError, "profile safety lineage"
        ):
            self.analyze()

    def test_action_specific_profile_identity_and_validity_are_preserved(self) -> None:
        result = self.analyze()
        states = [chain["profile_state"] for chain in result["validated_chains"]]
        self.assertEqual(len({state["profile_id"] for state in states}), 8)
        self.assertEqual(len({state["valid_from"] for state in states}), 8)
        analyzer.validate_n2p_physical_analysis(result)

    def test_stale_usage_snapshot_replay_is_rejected(self) -> None:
        q1_map = self.fixture._read(
            self.fixture.directories["q1-map-primer"], runner.COPIED_PROFILE_FILENAME
        )["usage"]

        def stale(profile: dict) -> None:
            profile["usage"].update(q1_map)
            profile["usage"]["evidence_sha256"] = _sha(b"stale-but-new-file")

        self.fixture.mutate_profile("q2-map-primer", stale)
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "campaign order"):
            self.analyze()

    def test_camera_mismatch_is_explicit_but_does_not_break_manual_winner(self) -> None:
        self.fixture.mutate_camera_id("q4-target", "different-camera-body")
        result = self.analyze()
        self.assertFalse(result["camera_comparability"]["comparable"])
        self.assertEqual(
            result["camera_comparability"]["reasons"],
            ["camera_or_fixed_settings_differ_across_targets"],
        )
        self.assertEqual(result["selected_winner"]["cell_id"], "Q4")
        self.assertFalse(
            result["camera_comparability"]["affects_manual_score_winner"]
        )

    def test_equal_top_total_is_tie_with_no_winner(self) -> None:
        self.fixture.set_target_scores(3, 5)
        result = self.analyze()
        self.assertTrue(result["tie_state"]["top_tie"])
        self.assertEqual(result["tie_state"]["top_tied_cell_ids"], ["Q3", "Q4"])
        self.assertIsNone(result["selected_winner"])
        self.assertFalse(result["winner_gates"]["all_pass"])

    def test_canonical_writer_and_analysis_tamper_rejection(self) -> None:
        output = Path(self.temporary.name) / "N2P-PHYSICAL-ANALYSIS.json"
        result = analyzer.write_n2p_physical_analysis(
            self.fixture.directories,
            output,
            reviewer_key_file=self.fixture.reviewer_key_file,
        )
        self.assertEqual(output.read_bytes(), canonical_json_bytes(result))
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "already exists"):
            analyzer.write_n2p_physical_analysis(
                self.fixture.directories,
                output,
                reviewer_key_file=self.fixture.reviewer_key_file,
            )
        tampered = deepcopy(result)
        tampered["ranking"] = list(reversed(tampered["ranking"]))
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = {
            "canonical_sha256": _sha(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": analyzer.ANALYSIS_HASH_SCOPE,
        }
        with self.assertRaisesRegex(analyzer.N2PhysicalAnalysisError, "ranking"):
            analyzer.validate_n2p_physical_analysis(tampered)


if __name__ == "__main__":
    unittest.main()
