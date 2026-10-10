from __future__ import annotations

from contextlib import redirect_stderr
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import canonical_json_bytes
from tests.test_g1_s1_rc2g_n2_physical_analyzer import (
    PANEL,
    REVIEW_BYTES as N2_REVIEW_BYTES,
    PhysicalAnalyzerFixture,
)
from tools import g1_s1_n2_physical_campaign as n2_physical
from tools import g1_s1_n3_campaign as planning
from tools import g1_s1_n3a_physical_plan as physical_plan
from tools import g1_s1_rc2g_n2_photo_campaign as frozen_n2
from tools import g1_s1_rc2g_n2_physical_analyzer as physical_analyzer


N3A_REVIEW_BYTES = b"reviewed physical N2 winner to N3A exact plan binding\n"
MINIMUM_INTERVAL_SECONDS = 150
PLANNED_COOLDOWN_SECONDS = 150


def _sha256(value: object) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _reseal_analysis(analysis: dict) -> dict:
    unsigned = dict(analysis)
    unsigned.pop("integrity", None)
    analysis["integrity"] = {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": physical_analyzer.ANALYSIS_HASH_SCOPE,
    }
    return analysis


def _forge_q3_winner_with_self_consistent_seals(analysis: dict) -> dict:
    forged = deepcopy(analysis)
    q3 = next(row for row in forged["scorecard"] if row["cell_id"] == "Q3")
    q4 = next(row for row in forged["scorecard"] if row["cell_id"] == "Q4")
    q3["scores"] = {
        dimension: 5 for dimension in physical_analyzer.SCORE_DIMENSIONS
    }
    q3["score_total"] = 30
    q3["score_mean"] = 5.0
    q4["scores"] = {
        dimension: 4 for dimension in physical_analyzer.SCORE_DIMENSIONS
    }
    q4["score_total"] = 24
    q4["score_mean"] = 4.0
    totals = sorted(
        {row["score_total"] for row in forged["scorecard"]}, reverse=True
    )
    rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
    forged["ranking"] = sorted(
        (
            {"rank": rank_by_total[row["score_total"]], **row}
            for row in forged["scorecard"]
        ),
        key=lambda row: (row["rank"], row["cell_id"]),
    )
    forged["tie_state"] = {
        "top_score_total": 30,
        "top_tie": False,
        "top_tied_cell_ids": ["Q3"],
        "arbitrary_tie_break_performed": False,
    }
    forged["winner_gates"]["unique_top_total"] = True
    forged["winner_gates"]["all_pass"] = True
    winner = {
        "cell_id": q3["cell_id"],
        "algorithm": q3["algorithm"],
        "action_key": q3["action_key"],
        "action_identity_sha256": q3["action_identity_sha256"],
        "frame_sha256": q3["frame_sha256"],
        "target_result_file_sha256": q3["target_result_file_sha256"],
        "score_total": q3["score_total"],
        "score_mean": q3["score_mean"],
        "selection_basis": "unique_highest_preregistered_six_dimension_total",
        "authorized_use": "N3_branch_selection_only",
        "algorithm_qualified": False,
        "population_inference": False,
    }
    winner["winner_identity_sha256"] = _sha256(winner)
    forged["selected_winner"] = winner
    return _reseal_analysis(forged)


def _reseal_plan(plan: dict) -> dict:
    unsigned = dict(plan)
    unsigned.pop("integrity", None)
    plan["integrity"] = {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": physical_plan.PLAN_HASH_SCOPE,
    }
    return plan


def _registered_assets() -> dict:
    return planning.build_measurement_asset_registry(
        timing_clock_asset_sha256="1" * 64,
        temperature_sensor_asset_sha256="2" * 64,
        temperature_calibration_asset_sha256="3" * 64,
        temperature_location_asset_sha256="4" * 64,
        camera_body_asset_sha256="5" * 64,
        camera_lens_asset_sha256="6" * 64,
        camera_mount_asset_sha256="7" * 64,
        camera_capture_config_sha256="8" * 64,
        camera_crop_asset_sha256="9" * 64,
        illumination_asset_sha256="a" * 64,
    )


class N3APhysicalPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_n2 = frozen_n2.compile_campaign_manifest()
        cls.operator = n2_physical._assemble_manifest(
            cls.source_n2,
            PANEL,
            n2_physical._review_artifact_record(N2_REVIEW_BYTES),
            n2_physical._operator_process_schedule(
                MINIMUM_INTERVAL_SECONDS, PLANNED_COOLDOWN_SECONDS
            ),
        )
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        cls.temporary = tempfile.TemporaryDirectory(dir=hardware)
        cls.fixture = PhysicalAnalyzerFixture(Path(cls.temporary.name), cls.operator)
        cls.validator_patcher = mock.patch.object(
            physical_analyzer.fixed,
            "validate_physical_result",
            side_effect=cls.fixture.validation,
        )
        cls.validator_mock = cls.validator_patcher.start()
        cls.analysis = physical_analyzer.analyze_n2p_physical_campaign(
            cls.fixture.directories,
            reviewer_key_file=cls.fixture.reviewer_key_file,
        )
        cls.assets = _registered_assets()
        cls.plan2 = physical_plan.compile_n3a_physical_plan(
            cls.analysis,
            cls.operator,
            n2_result_directories=cls.fixture.directories,
            reviewer_key_file=cls.fixture.reviewer_key_file,
            repeat_count=2,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            binding_review_bytes=N3A_REVIEW_BYTES,
            measurement_assets=cls.assets,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.validator_patcher.stop()
        cls.temporary.cleanup()

    def compile(self, repeat_count: int = 2, **kwargs) -> dict:
        return physical_plan.compile_n3a_physical_plan(
            kwargs.pop("analysis", self.analysis),
            kwargs.pop("operator", self.operator),
            n2_result_directories=kwargs.pop(
                "result_directories", self.fixture.directories
            ),
            reviewer_key_file=kwargs.pop(
                "reviewer_key_file", self.fixture.reviewer_key_file
            ),
            repeat_count=repeat_count,
            minimum_interval_seconds=kwargs.pop(
                "minimum_interval", MINIMUM_INTERVAL_SECONDS
            ),
            planned_cooldown_seconds=kwargs.pop(
                "planned_cooldown", PLANNED_COOLDOWN_SECONDS
            ),
            binding_review_bytes=kwargs.pop("review", N3A_REVIEW_BYTES),
            measurement_assets=kwargs.pop("assets", self.assets),
            **kwargs,
        )

    def test_unique_physical_winner_compiles_only_selected_exact_template(self) -> None:
        plan = physical_plan.validate_n3a_physical_plan(
            self.plan2,
            n2_result_directories=self.fixture.directories,
            reviewer_key_file=self.fixture.reviewer_key_file,
            binding_review_bytes=N3A_REVIEW_BYTES,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            n2_physical_analysis=self.analysis,
            physical_operator_manifest=self.operator,
            repeat_count=2,
        )
        self.assertEqual(plan["selection"]["winner_cell_id"], "Q4")
        self.assertEqual(plan["selection"]["authorized_use"], "N3_branch_selection_only")
        self.assertEqual(plan["selected_source"]["template_id"], "n3a-q4-repeat2")
        self.assertEqual(len(plan["selected_routes"]), 2)
        self.assertEqual(len(plan["fixed_actions"]), 4)
        self.assertEqual(
            plan["physical_rebind"]["physical_campaign"]["panel"],
            self.operator["physical_campaign_contract"]["panel"],
        )
        self.assertEqual(
            plan["physical_rebind"]["physical_campaign"]["firmware"],
            self.operator["physical_campaign_contract"]["firmware"],
        )
        self.assertTrue(
            plan["selection"]["same_operator_campaign_panel_firmware_validated"]
        )
        self.assertEqual(
            plan["process_schedule"]["minimum_interval_seconds"], 150.0
        )
        self.assertEqual(
            plan["process_schedule"]["planned_cooldown_seconds"], 150.0
        )
        self.assertEqual(
            plan["process_schedule"]["classification"],
            "operator_selected_experimental_process_schedule",
        )
        self.assertTrue(plan["process_schedule"]["not_a_supplier_rating"])
        self.assertEqual(
            plan["selection"]["process_schedule"], plan["process_schedule"]
        )
        provenance = plan["n2_physical_provenance"]
        self.assertEqual(provenance["result_directory_count"], 8)
        self.assertEqual(len(provenance["finalized_chains"]), 8)
        self.assertFalse(provenance["analysis_json_alone_is_authority"])
        for chain in provenance["finalized_chains"]:
            self.assertEqual(len(chain["action_identity_sha256"]), 64)
            self.assertEqual(len(chain["result_file_sha256"]), 64)
            self.assertEqual(len(chain["claim_file_sha256"]), 64)
            self.assertEqual(len(chain["profile_file_sha256"]), 64)
        self.assertTrue(
            plan["readiness"]["future_live_runner_raw_evidence_replay_required"]
        )
        self.assertTrue(
            plan["evidence_contract"][
                "n2_physical_analyzer_replayed_on_every_public_consumer"
            ]
        )
        self.assertFalse(plan["classification"]["hardware_execution_authorized"])
        self.assertFalse(plan["classification"]["claim_created"])
        self.assertFalse(plan["classification"]["network_io_performed"])
        self.assertFalse(plan["classification"]["device_io_performed"])
        before_describe = self.validator_mock.call_count
        description = physical_plan.describe_n3a_physical_plan(
            plan,
            n2_result_directories=self.fixture.directories,
            reviewer_key_file=self.fixture.reviewer_key_file,
            binding_review_bytes=N3A_REVIEW_BYTES,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
        )
        self.assertEqual(description["winner_cell_id"], "Q4")
        self.assertEqual(self.validator_mock.call_count - before_describe, 8)

    def test_only_integer_repeat_2_3_4_and_all_identities_are_fresh(self) -> None:
        for repeat_count in (2, 3, 4):
            with self.subTest(repeat_count=repeat_count):
                plan = self.plan2 if repeat_count == 2 else self.compile(repeat_count)
                campaign = plan["physical_rebind"]["physical_campaign"]
                self.assertEqual(len(campaign["actions"]), 2 * repeat_count)
                self.assertEqual(len(campaign["sessions"]), repeat_count)
                self.assertTrue(
                    all(
                        action["identity"]["schedule"][
                            "minimum_interval_since_prior_seconds"
                        ]
                        == 150.0
                        for action in campaign["actions"]
                        if action["identity"]["phase"] == "target"
                    )
                )
                self.assertTrue(
                    all(
                        session["planned_cooldown_seconds"] == 150.0
                        for session in campaign["sessions"]
                    )
                )
                identity = plan["identity_rebind_contract"]
                self.assertTrue(identity["all_action_identities_rebuilt"])
                self.assertTrue(identity["all_prior_identities_rebuilt"])
                self.assertTrue(identity["all_session_action_identity_vectors_rebuilt"])
                self.assertTrue(
                    identity["all_workspace_global_claim_filenames_rebuilt"]
                )
                self.assertTrue(
                    identity["source_and_physical_action_identities_disjoint"]
                )
                self.assertTrue(
                    identity["n2_anchor_and_n3_action_identities_disjoint"]
                )
                actions = {
                    action["action_identity_sha256"]: action
                    for action in campaign["actions"]
                }
                for route in plan["selected_routes"]:
                    self.assertEqual(
                        actions[route["target_action_identity_sha256"]]["identity"][
                            "prior"
                        ]["action_identity_sha256"],
                        route["map_action_identity_sha256"],
                    )
        for rejected in (1, 5, 2.0, True, None):
            with self.subTest(rejected=rejected), self.assertRaisesRegex(
                physical_plan.N3APhysicalPlanError, "integer 2, 3, or 4"
            ):
                self.compile(rejected)  # type: ignore[arg-type]
        for interval, cooldown in (
            (0, 150),
            (-1, 150),
            (True, 150),
            (float("inf"), 150),
            (150, -1),
            (150, True),
            (150, float("nan")),
        ):
            with self.subTest(interval=interval, cooldown=cooldown), self.assertRaises(
                physical_plan.N3APhysicalPlanError
            ):
                self.compile(
                    minimum_interval=interval,
                    planned_cooldown=cooldown,
                )
        missing_directory = dict(self.fixture.directories)
        missing_directory.pop("q4-target")
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "exactly the eight"
        ):
            self.compile(result_directories=missing_directory)

    def test_tie_null_unauthorized_and_cross_campaign_inputs_fail_closed(self) -> None:
        tied = deepcopy(self.analysis)
        q3 = next(row for row in tied["scorecard"] if row["cell_id"] == "Q3")
        q3["scores"] = {dimension: 5 for dimension in physical_analyzer.SCORE_DIMENSIONS}
        q3["score_total"] = 30
        q3["score_mean"] = 5.0
        totals = sorted({row["score_total"] for row in tied["scorecard"]}, reverse=True)
        rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
        tied["ranking"] = sorted(
            (
                {"rank": rank_by_total[row["score_total"]], **row}
                for row in tied["scorecard"]
            ),
            key=lambda row: (row["rank"], row["cell_id"]),
        )
        tied["tie_state"] = {
            "top_score_total": 30,
            "top_tie": True,
            "top_tied_cell_ids": ["Q3", "Q4"],
            "arbitrary_tie_break_performed": False,
        }
        tied["winner_gates"]["unique_top_total"] = False
        tied["winner_gates"]["all_pass"] = False
        tied["selected_winner"] = None
        _reseal_analysis(tied)
        physical_analyzer.validate_n2p_physical_analysis(tied)
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "does not exactly match"
        ):
            self.compile(analysis=tied)

        unauthorized = deepcopy(self.analysis)
        unauthorized["selected_winner"]["authorized_use"] = "algorithm-qualified"
        _reseal_analysis(unauthorized)
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "does not exactly match"
        ):
            self.compile(analysis=unauthorized)

        other_panel = {**PANEL, "serial": "MF1750-LAB-PANEL-N3A-CROSS-0002"}
        other_operator = n2_physical._assemble_manifest(
            self.source_n2,
            other_panel,
            n2_physical._review_artifact_record(b"other N2 panel binding review\n"),
            n2_physical._operator_process_schedule(
                MINIMUM_INTERVAL_SECONDS, PLANNED_COOLDOWN_SECONDS
            ),
        )
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "same exact operator/campaign"
        ):
            self.compile(operator=other_operator)

    def test_forged_q4_to_q3_resealed_analysis_is_rejected_before_plan_generation(
        self,
    ) -> None:
        forged = _forge_q3_winner_with_self_consistent_seals(self.analysis)
        # This is the original PoC: self-contained semantic validation cannot
        # recover the authenticated scores from their finalized directories.
        physical_analyzer.validate_n2p_physical_analysis(forged)
        self.assertEqual(forged["selected_winner"]["cell_id"], "Q3")
        before_validator_calls = self.validator_mock.call_count
        with (
            mock.patch.object(
                physical_plan,
                "_assemble_plan",
                wraps=physical_plan._assemble_plan,
            ) as assemble,
            mock.patch.object(
                physical_analyzer.fixed,
                "_claim_action",
                side_effect=AssertionError("claim creation forbidden"),
            ) as claim,
            mock.patch.object(
                physical_analyzer.fixed,
                "run_physical_action_once",
                side_effect=AssertionError("device path forbidden"),
            ) as device,
            mock.patch.object(
                physical_analyzer.fixed.legacy,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ) as network,
            self.assertRaisesRegex(
                physical_plan.N3APhysicalPlanError,
                "does not exactly match.*eight finalized",
            ),
        ):
            self.compile(analysis=forged)
        self.assertEqual(
            self.validator_mock.call_count - before_validator_calls,
            8,
        )
        assemble.assert_not_called()
        claim.assert_not_called()
        device.assert_not_called()
        network.assert_not_called()

    def test_ten_measurement_assets_and_scientific_source_contract_are_exact(self) -> None:
        plan = self.plan2
        contract = plan["measurement_asset_contract"]
        self.assertEqual(contract["identity_field_count"], 10)
        self.assertEqual(contract["registered_identity_count"], 10)
        self.assertTrue(contract["all_identities_registered"])
        self.assertEqual(contract["blockers"], [])
        self.assertEqual(
            plan["source_n3a_manifest"]["measurement_asset_registry"], self.assets
        )
        planning.validate_n3a_manifest(plan["source_n3a_manifest"])
        self.assertEqual(
            plan["source_n3a_manifest"]["repeat_contract"]["repeat_counts"],
            [2, 3, 4],
        )
        missing = self.compile(assets=None)
        self.assertEqual(
            missing["measurement_asset_contract"]["registered_identity_count"], 0
        )
        self.assertEqual(
            len(missing["readiness"]["measurement_asset_blockers"]), 10
        )
        self.assertFalse(missing["readiness"]["measurement_assets_ready"])
        self.assertFalse(missing["readiness"]["hardware_ready"])

    def test_resealed_plan_tamper_and_wrong_actual_review_bytes_are_rejected(self) -> None:
        tampered = deepcopy(self.plan2)
        tampered["selected_routes"][0]["target_action_identity_sha256"] = "f" * 64
        _reseal_plan(tampered)
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "deterministic deep reconstruction"
        ):
            physical_plan.validate_n3a_physical_plan(
                tampered,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                binding_review_bytes=N3A_REVIEW_BYTES,
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            )
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "review artifact bytes"
        ):
            physical_plan.validate_n3a_physical_plan(
                self.plan2,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                binding_review_bytes=b"wrong N3A review bytes\n",
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            )
        with self.assertRaisesRegex(
            physical_plan.N3APhysicalPlanError, "explicit operator schedule"
        ):
            physical_plan.validate_n3a_physical_plan(
                self.plan2,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                binding_review_bytes=N3A_REVIEW_BYTES,
                minimum_interval_seconds=151,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            )

    def test_cli_requires_both_explicit_operator_schedule_values(self) -> None:
        common = [
            "compile",
            "--n2-analysis",
            "analysis.json",
            "--physical-operator-manifest",
            "operator.json",
            "--binding-review-artifact",
            "review.bin",
            "--repeat-count",
            "2",
            "--output-dir",
            "output",
            "--reviewer-key",
            "reviewer.key",
        ]
        for key in physical_analyzer.EXPECTED_RESULT_KEYS:
            common.extend([f"--{key}-dir", f"{key}-result"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            physical_plan.parse_args(common)
        parsed = physical_plan.parse_args(
            [
                *common,
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
            ]
        )
        self.assertEqual(parsed.minimum_interval_seconds, 150.0)
        self.assertEqual(parsed.planned_cooldown_seconds, 150.0)

    def test_exclusive_canonical_two_file_publish_and_bundle_validation(self) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            analysis_file = root / "N2P-PHYSICAL-ANALYSIS.json"
            operator_file = root / n2_physical.OPERATOR_MANIFEST_FILENAME
            review_file = root / "N3A-BINDING-REVIEW.bin"
            assets_file = root / "N3A-MEASUREMENT-ASSETS.json"
            output = root / "n3a-physical-plan"
            analysis_file.write_bytes(canonical_json_bytes(self.analysis))
            operator_file.write_bytes(canonical_json_bytes(self.operator))
            review_file.write_bytes(N3A_REVIEW_BYTES)
            assets_file.write_bytes(canonical_json_bytes(self.assets))

            plan = physical_plan.publish_n3a_physical_plan_bundle(
                analysis_file,
                operator_file,
                review_file,
                output,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                repeat_count=2,
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
                measurement_assets_file=assets_file,
            )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {
                    physical_plan.PHYSICAL_CAMPAIGN_FILENAME,
                    physical_plan.PLAN_MANIFEST_FILENAME,
                },
            )
            self.assertEqual(
                (output / physical_plan.PLAN_MANIFEST_FILENAME).read_bytes(),
                canonical_json_bytes(plan),
            )
            self.assertEqual(
                (output / physical_plan.PHYSICAL_CAMPAIGN_FILENAME).read_bytes(),
                canonical_json_bytes(plan["physical_rebind"]["physical_campaign"]),
            )
            read_back = physical_plan.read_n3a_physical_plan(
                output / physical_plan.PLAN_MANIFEST_FILENAME,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                binding_review_artifact_file=review_file,
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            )
            self.assertEqual(read_back, plan)
            validated = physical_plan.validate_n3a_physical_plan_bundle(
                output,
                review_file,
                n2_result_directories=self.fixture.directories,
                reviewer_key_file=self.fixture.reviewer_key_file,
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
                n2_physical_analysis_file=analysis_file,
                physical_operator_manifest_file=operator_file,
            )
            self.assertEqual(validated, plan)
            with self.assertRaisesRegex(
                physical_plan.N3APhysicalPlanError, "already exists"
            ):
                physical_plan.publish_n3a_physical_plan_bundle(
                    analysis_file,
                    operator_file,
                    review_file,
                    output,
                    n2_result_directories=self.fixture.directories,
                    reviewer_key_file=self.fixture.reviewer_key_file,
                    repeat_count=2,
                    minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                    planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
                    measurement_assets_file=assets_file,
                )

            forged_analysis_file = root / "FORGED-N2P-PHYSICAL-ANALYSIS.json"
            forged_analysis_file.write_bytes(
                canonical_json_bytes(
                    _forge_q3_winner_with_self_consistent_seals(self.analysis)
                )
            )
            forged_output = root / "forged-n3a-plan"
            with self.assertRaisesRegex(
                physical_plan.N3APhysicalPlanError, "does not exactly match"
            ):
                physical_plan.publish_n3a_physical_plan_bundle(
                    forged_analysis_file,
                    operator_file,
                    review_file,
                    forged_output,
                    n2_result_directories=self.fixture.directories,
                    reviewer_key_file=self.fixture.reviewer_key_file,
                    repeat_count=2,
                    minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                    planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
                    measurement_assets_file=assets_file,
                )
            self.assertFalse(forged_output.exists())


if __name__ == "__main__":
    unittest.main()
