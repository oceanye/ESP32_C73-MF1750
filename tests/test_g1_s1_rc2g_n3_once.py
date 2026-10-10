from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import canonical_json_bytes
from tests.n3_bundle_fixture import (
    EVALUATED_AT,
    _profile,
    _write_json,
    build_finalized_session,
    fixture_sha256,
    registered_assets,
)
from tools import g1_s1_n3_execution_contract as execution
from tools import g1_s1_rc2g_n3_once as runner


class N3ExactPlanAndRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = execution.compile_n3b_exact_plan(
            measurement_assets=registered_assets()
        )
        cls.pair = build_finalized_session(cls.plan, 0)

    def test_n3b_exact_plan_is_four_blocks_16_routes_32_actions(self) -> None:
        plan = execution.validate_n3_exact_plan(self.plan)
        self.assertEqual(plan["study"], "N3B")
        self.assertEqual(len(plan["selected_routes"]), 16)
        self.assertEqual(len(plan["fixed_actions"]), 32)
        self.assertEqual(
            plan["selection"]["branch_ids"],
            [f"n3b-balanced-block-{index}" for index in range(1, 5)],
        )
        self.assertTrue(plan["readiness"]["measurement_assets_ready"])
        self.assertFalse(plan["readiness"]["hardware_ready"])
        self.assertFalse(plan["power_semantics"]["ordinary_session_requires_j2_cycle"])
        self.assertTrue(plan["power_semantics"]["j2_may_remain_on_between_sessions"])

    def test_default_plan_remains_asset_blocked_and_never_hardware_ready(self) -> None:
        plan = execution.compile_n3b_exact_plan()
        self.assertEqual(len(plan["readiness"]["measurement_asset_blockers"]), 10)
        self.assertFalse(plan["readiness"]["measurement_assets_ready"])
        self.assertFalse(plan["classification"]["hardware_ready"])
        self.assertEqual(
            plan["integrity"]["canonical_sha256"],
            execution.EXPECTED_DEFAULT_N3B_PLAN_CANONICAL_SHA256,
        )
        self.assertEqual(
            execution.exact_plan_file_sha256(plan),
            execution.EXPECTED_DEFAULT_N3B_PLAN_FILE_SHA256,
        )

    def test_n3a_compiler_calls_deep_n2_analyzer_and_selects_one_template(self) -> None:
        fake = {
            "winner_gates": {"all_pass": True},
            "selected_winner": {
                "cell_id": "Q3",
                "winner_identity_sha256": fixture_sha256("n2-q3-winner"),
                "authorized_use": "N3_branch_selection_only",
                "algorithm_qualified": False,
                "population_inference": False,
            },
        }
        with (
            mock.patch.object(
                execution._n2_analyzer,
                "analyze_n2p_campaign",
                return_value=fake,
            ) as deep_analyzer,
            mock.patch.object(
                execution._n2_analyzer,
                "validate_n2p_analysis",
                return_value=fake,
            ),
        ):
            plan = execution.compile_n3a_exact_plan(
                n2_result_directories={"sentinel": Path("unused")},
                repeat_count=2,
                measurement_assets=registered_assets(),
            )
        deep_analyzer.assert_called_once()
        self.assertEqual(plan["selection"]["winner_cell_id"], "Q3")
        self.assertEqual(plan["selection"]["repeat_count"], 2)
        self.assertEqual(len(plan["selected_routes"]), 2)
        self.assertEqual(len(plan["fixed_actions"]), 4)
        self.assertNotIn("n3a-q1-r2-repeat1-map", plan["fixed_actions"])

    def test_n3a_tie_null_and_invalid_repeat_fail_closed(self) -> None:
        tie = {"winner_gates": {"all_pass": False}, "selected_winner": None}
        with mock.patch.object(
            execution._n2_analyzer,
            "validate_n2p_analysis",
            return_value=tie,
        ):
            with self.assertRaisesRegex(
                execution.N3ExecutionContractError, "unique.*winner"
            ):
                execution._selection_from_n2_analysis(tie, 2)
        fake = {
            "winner_gates": {"all_pass": True},
            "selected_winner": {
                "cell_id": "Q1",
                "winner_identity_sha256": fixture_sha256("winner"),
                "authorized_use": "N3_branch_selection_only",
                "algorithm_qualified": False,
                "population_inference": False,
            },
        }
        with mock.patch.object(
            execution._n2_analyzer,
            "validate_n2p_analysis",
            return_value=fake,
        ):
            with self.assertRaisesRegex(
                execution.N3ExecutionContractError, "2, 3, or 4"
            ):
                execution._selection_from_n2_analysis(fake, 5)

    def test_describe_only_has_zero_claim_network_and_authorization(self) -> None:
        key = self.plan["selected_routes"][2]["map_action_key"]
        with (
            mock.patch.object(
                runner, "_claim_action", side_effect=AssertionError("claim")
            ),
            mock.patch.object(
                runner, "http_request", side_effect=AssertionError("network")
            ),
        ):
            description = runner.describe_n3_fixed_action(
                self.plan, key, evaluated_at=EVALUATED_AT
            )
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["claim_created"])
        self.assertIn("missing_reviewed_limit_profile", description["blockers"])
        self.assertEqual(
            len(description["required_authorization_confirmation_sha256"]), 64
        )

    def test_unknown_action_rejected_before_claim_or_network(self) -> None:
        with (
            mock.patch.object(
                runner, "_claim_action", side_effect=AssertionError("claim")
            ),
            mock.patch.object(
                runner, "http_request", side_effect=AssertionError("network")
            ),
            self.assertRaisesRegex(runner.N3FixedActionError, "exact N3 plan"),
        ):
            runner.describe_n3_fixed_action(
                self.plan, "custom-action", evaluated_at=EVALUATED_AT
            )

    def test_legacy_live_profile_path_is_disabled_before_claim_and_network(self) -> None:
        route = self.plan["selected_routes"][0]
        with (
            mock.patch.object(runner, "_claim_action", side_effect=AssertionError("claim")),
            mock.patch.object(runner, "http_request", side_effect=AssertionError("network")),
            self.assertRaisesRegex(runner.N3FixedActionError, "legacy N3 live execution"),
        ):
            runner.run_n3_fixed_action_once(
                self.plan,
                execution.exact_plan_file_sha256(self.plan),
                route["map_action_key"],
                Path("must-not-be-created"),
                "http://device",
                limit_profile_file=Path("must-not-be-read.json"),
                evaluated_at=EVALUATED_AT,
                authorization_confirmation="must-not-be-read",
                start_temperature_c=25,
            )

    def test_claim_precedes_network_and_claimed_failure_is_permanent(self) -> None:
        route = self.plan["selected_routes"][3]
        key = route["map_action_key"]
        snapshot = execution.load_n3_action_snapshot(self.plan, key)
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            registry = root / "claims"
            profile = _write_json(root / "profile.json", _profile(snapshot.campaign, prior_completed=False))
            request = mock.Mock(side_effect=RuntimeError("synthetic transport failure"))
            with (
                mock.patch.object(runner, "_require_deep_production_profile_path"),
                mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", registry),
                mock.patch.object(runner, "http_request", request),
                mock.patch.object(runner, "_utc_now", return_value="2026-08-08T00:00:30Z"),
                self.assertRaises(runner.N3FixedActionUnknown),
            ):
                runner.run_n3_fixed_action_once(
                    self.plan,
                    execution.exact_plan_file_sha256(self.plan),
                    key,
                    root / "first-result",
                    "http://device",
                    limit_profile_file=profile,
                    evaluated_at=EVALUATED_AT,
                    authorization_confirmation=runner.required_authorization_confirmation(
                        self.plan, key
                    ),
                    start_temperature_c=25,
                    confirm_reviewed_panel_build_and_exact_plan=True,
                    confirm_registered_measurement_assets_present=True,
                    confirm_supervised_supply_cv_current_normal=True,
                    confirm_physical_cutoff_available=True,
                    confirm_single_visible_refresh=True,
                    confirm_controller_fresh_boot=True,
                )
            self.assertTrue((registry / snapshot.action["claim"]["filename"]).is_file())
            first_calls = request.call_count
            with (
                mock.patch.object(runner, "_require_deep_production_profile_path"),
                mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", registry),
                mock.patch.object(runner, "http_request", request),
                mock.patch.object(runner, "_utc_now", return_value="2026-08-08T00:00:31Z"),
                self.assertRaises(runner.N3FixedActionUnknown),
            ):
                runner.run_n3_fixed_action_once(
                    self.plan,
                    execution.exact_plan_file_sha256(self.plan),
                    key,
                    root / "second-result",
                    "http://device",
                    limit_profile_file=profile,
                    evaluated_at=EVALUATED_AT,
                    authorization_confirmation=runner.required_authorization_confirmation(
                        self.plan, key
                    ),
                    start_temperature_c=25,
                    confirm_reviewed_panel_build_and_exact_plan=True,
                    confirm_registered_measurement_assets_present=True,
                    confirm_supervised_supply_cv_current_normal=True,
                    confirm_physical_cutoff_available=True,
                    confirm_single_visible_refresh=True,
                    confirm_controller_fresh_boot=True,
                )
            self.assertEqual(request.call_count, first_calls)

    def test_deep_finalized_pair_binds_prior_result_and_finalization(self) -> None:
        route = self.plan["selected_routes"][0]
        map_validated = execution.validate_n3_finalized_action_bundle(
            self.plan,
            self.pair["map_bundle"],
            expected_action_key=route["map_action_key"],
        )
        target_validated = execution.validate_n3_finalized_action_bundle(
            self.plan,
            self.pair["target_bundle"],
            expected_action_key=route["target_action_key"],
            prior_bundle=self.pair["map_bundle"],
        )
        self.assertEqual(map_validated["state"], "PASS")
        self.assertEqual(target_validated["state"], "PASS")
        self.assertEqual(
            target_validated["prior_result_file_sha256"],
            self.pair["map_bundle"]["result_file_sha256"],
        )
        self.assertEqual(
            target_validated["prior_finalization_file_sha256"],
            self.pair["map_bundle"]["finalization_file_sha256"],
        )

    def test_nested_tamper_and_missing_prior_fail_closed(self) -> None:
        route = self.plan["selected_routes"][0]
        with self.assertRaisesRegex(
            execution.N3ExecutionContractError, "requires the exact"
        ):
            execution.validate_n3_finalized_action_bundle(
                self.plan,
                self.pair["target_bundle"],
                expected_action_key=route["target_action_key"],
            )
        tampered = deepcopy(self.pair["map_bundle"])
        tampered["claim"]["maximum_post_requests"] = 2
        with self.assertRaisesRegex(
            execution.N3ExecutionContractError, "whole-file SHA-256"
        ):
            execution.validate_n3_finalized_action_bundle(
                self.plan,
                tampered,
                expected_action_key=route["map_action_key"],
            )

    def test_plan_file_is_canonical_and_cli_has_no_identity_overrides(self) -> None:
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            plan_path = Path(temporary) / "plan.json"
            plan_path.write_bytes(canonical_json_bytes(self.plan))
            loaded, digest = runner.load_n3_exact_plan_file(plan_path)
        self.assertEqual(loaded["plan_id"], self.plan["plan_id"])
        self.assertEqual(digest, execution.exact_plan_file_sha256(self.plan))
        with self.assertRaises(SystemExit):
            runner.parse_args(
                [
                    "--plan-file",
                    "plan.json",
                    "--action",
                    next(iter(self.plan["fixed_actions"])),
                    "--evaluated-at",
                    EVALUATED_AT,
                    "--describe-only",
                    "--frame-sha256",
                    fixture_sha256("override"),
                ]
            )


if __name__ == "__main__":
    unittest.main()
