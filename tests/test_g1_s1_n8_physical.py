from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState
from tests.n8_physical_fixture import (
    BASE_TIME,
    N8PhysicalFixture,
    timestamp,
)
from tools import g1_s1_n8_execution_contract as frozen
from tools import g1_s1_n8_physical_analyzer as analyzer
from tools import g1_s1_n8_physical_execution as physical
from tools import g1_s1_rc2g_n8_once as legacy_runner
from tools import g1_s1_rc2g_n8_physical_once as runner


class N8PhysicalProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        hardware.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=hardware)
        cls.root = Path(cls.temporary.name)
        cls.fixture = N8PhysicalFixture(cls.root)
        cls.fixture.run_all()
        cls.actions = tuple(
            analyzer.N8PhysicalActionEvidence(bundle=bundle, production=production)
            for bundle, production in zip(
                cls.fixture.bundles, cls.fixture.production_profiles
            )
        )
        cls.report = analyzer.analyze_n8_physical_actions(
            cls.fixture.context, actions=cls.actions
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_physical_contract_runner_and_tokens_cover_exact_frozen_campaign(self) -> None:
        context = self.fixture.context
        contract = physical.validate_n8_physical_execution_context(context)
        source = frozen._source_manifest()["p0_campaign"]
        self.assertEqual(len(contract["fixed_actions"]), 15)
        self.assertEqual(len(contract["sequences"]), 5)
        self.assertEqual(len(contract["p0_campaign"]["actions"]), 15)
        self.assertEqual(len(contract["p0_campaign"]["sessions"]), 5)
        self.assertEqual(
            len(
                {
                    action["action_identity_sha256"]
                    for action in contract["p0_campaign"]["actions"]
                }
            ),
            15,
        )
        self.assertTrue(
            {
                action["action_identity_sha256"]
                for action in source["actions"]
            }.isdisjoint(
                {
                    action["action_identity_sha256"]
                    for action in contract["p0_campaign"]["actions"]
                }
            )
        )
        self.assertTrue(
            {action["claim"]["filename"] for action in source["actions"]}.isdisjoint(
                {
                    action["claim"]["filename"]
                    for action in contract["p0_campaign"]["actions"]
                }
            )
        )
        schedule = contract["reviewed_schedule"]
        self.assertTrue(schedule["not_a_supplier_rating"])
        self.assertGreater(schedule["minimum_interval_seconds"], 0)
        self.assertGreaterEqual(schedule["planned_cooldown_seconds"], 0)
        self.assertEqual(len(list(self.fixture.registry.glob("*.json"))), 15)
        self.assertTrue(
            all(
                request.calls.count(("POST", "/api/frame")) == 1
                for request in self.fixture.scripted_requests
            )
        )
        self.assertTrue(
            all(
                sum(method == "POST" for method, _endpoint in request.calls) == 1
                for request in self.fixture.scripted_requests
            )
        )
        for directory in self.fixture.result_directories:
            self.assertFalse((directory / self.fixture.reviewer_key.name).exists())
        action_key = contract["fixed_actions"][0]["action_key"]
        production = self.fixture.production_profiles[0]
        self.assertIn(
            contract["fixed_actions"][0]["action_identity_sha256"].upper(),
            runner.required_authorization_confirmation(context, action_key),
        )
        self.assertIn(
            context.physical_campaign["panel"]["serial"],
            runner.required_panel_confirmation(context),
        )
        self.assertIn(
            production.profile_file.sha256.upper(),
            runner.required_production_profile_confirmation(production),
        )
        for bundle in self.fixture.bundles:
            evidence = bundle["evidence"]
            self.assertLessEqual(
                evidence["live_evaluation_age_seconds"],
                physical.MAX_LIVE_EVALUATED_AT_AGE_SECONDS,
            )
            self.assertEqual(
                evidence["effective_minimum_interval_seconds"],
                max(
                    evidence["materialized_minimum_interval_seconds"],
                    evidence["authority_minimum_interval_seconds"],
                ),
            )
            self.assertEqual(
                evidence["effective_minimum_cooldown_seconds"],
                max(
                    evidence["materialized_planned_cooldown_seconds"],
                    evidence["authority_minimum_cooldown_seconds"],
                ),
            )

    def test_exact_fifteen_directory_formal_analysis_is_deep_and_not_qualified(self) -> None:
        report = self.report
        self.assertEqual(report["verified_action_count"], 15)
        self.assertEqual(report["verified_sequence_count"], 5)
        self.assertTrue(report["analysis_ready"])
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertFalse(report["hardware_qualified"])
        self.assertFalse(report["algorithm_qualified"])
        self.assertTrue(
            report["global_usage_chain"]["all_15_actions_accounted_for_in_order"]
        )
        self.assertTrue(
            report["continuity_summary"]["warm_dynamic_baseline_chain_verified"]
        )
        self.assertTrue(
            report["continuity_summary"][
                "esp32_no_restart_continuity_verified"
            ]
        )
        replayed = analyzer.analyze_n8_physical_result_directories(
            plan_files=self.fixture.plan_files,
            reviewer_key_file=self.fixture.reviewer_key,
            result_directories=self.fixture.result_directories,
        )
        self.assertEqual(replayed, report)
        self.assertEqual(
            analyzer.validate_n8_physical_analysis_report(
                report,
                self.fixture.context,
                actions=self.actions,
            ),
            report,
        )

    def test_analyzer_rejects_duplicate_tamper_cross_panel_and_report_change(self) -> None:
        duplicate_directories = [
            self.fixture.result_directories[0],
            *self.fixture.result_directories[:-1],
        ]
        with self.assertRaisesRegex(
            analyzer.N8PhysicalAnalysisError, "duplicate/replay"
        ):
            analyzer.analyze_n8_physical_result_directories(
                plan_files=self.fixture.plan_files,
                reviewer_key_file=self.fixture.reviewer_key,
                result_directories=duplicate_directories,
            )

        tampered_bundle = deepcopy(self.fixture.bundles[0])
        tampered_bundle["claim"]["maximum_post_requests"] = 2
        tampered_actions = (
            analyzer.N8PhysicalActionEvidence(
                bundle=tampered_bundle,
                production=self.fixture.production_profiles[0],
            ),
            *self.actions[1:],
        )
        with self.assertRaisesRegex(
            analyzer.N8PhysicalAnalysisError, "deep validation failed"
        ):
            analyzer.analyze_n8_physical_actions(
                self.fixture.context, actions=tampered_actions
            )

        cross_campaign = deepcopy(
            self.fixture.production_profiles[0].inputs.campaign
        )
        cross_campaign["panel"]["serial"] = "OTHER-PHYSICAL-PANEL"
        cross_inputs = replace(
            self.fixture.production_profiles[0].inputs,
            campaign=cross_campaign,
        )
        cross_production = replace(
            self.fixture.production_profiles[0], inputs=cross_inputs
        )
        cross_actions = (
            analyzer.N8PhysicalActionEvidence(
                bundle=self.fixture.bundles[0],
                production=cross_production,
            ),
            *self.actions[1:],
        )
        with self.assertRaisesRegex(
            analyzer.N8PhysicalAnalysisError, "production-ready"
        ):
            analyzer.analyze_n8_physical_actions(
                self.fixture.context, actions=cross_actions
            )

        changed_report = deepcopy(self.report)
        changed_report["hardware_qualified"] = True
        with self.assertRaises(analyzer.N8PhysicalAnalysisError):
            analyzer.validate_n8_physical_analysis_report(
                changed_report,
                self.fixture.context,
                actions=self.actions,
            )

    def test_freshness_precedes_claim_and_post_claim_failure_is_durable_unknown(self) -> None:
        row = self.fixture.context.contract["fixed_actions"][0]
        snapshot = physical.load_n8_physical_action_snapshot(
            self.fixture.context, row["action_key"]
        )
        production_files = self.fixture.production_files[0]
        production_profile = self.fixture.production_profiles[0]
        common = {
            "plan_files": self.fixture.plan_files,
            "production_files": production_files,
            "evaluated_at": self.fixture.evaluated_ats[0],
            "authorization_confirmation": (
                runner.required_authorization_confirmation(
                    self.fixture.context, row["action_key"]
                )
            ),
            "panel_confirmation": runner.required_panel_confirmation(
                self.fixture.context
            ),
            "profile_confirmation": (
                runner.required_production_profile_confirmation(
                    production_profile
                )
            ),
            "start_external_temperature_c": 24,
            "confirmations": self.fixture.confirmations(snapshot),
            "sleeper": lambda _seconds: None,
            "clock": lambda: 0.0,
        }

        stale_registry = self.root / "stale-claims"
        stale_destination = self.root / "stale-result"
        with (
            mock.patch.object(
                legacy_runner._fixed,
                "DEFAULT_CLAIM_REGISTRY",
                stale_registry,
            ),
            mock.patch.object(
                runner,
                "http_request",
                side_effect=AssertionError("network must not occur"),
            ),
            self.assertRaisesRegex(
                runner.N8PhysicalActionError, "too old"
            ),
        ):
            runner.run_n8_physical_action_once(
                row["action_key"],
                stale_destination,
                "http://fake-device",
                **common,
                wall_clock=lambda: timestamp(
                    BASE_TIME + timedelta(seconds=301)
                ),
            )
        self.assertFalse(stale_registry.exists())
        self.assertFalse(stale_destination.exists())

        unknown_registry = self.root / "unknown-claims"
        unknown_destination = self.root / "unknown-result"
        with (
            mock.patch.object(
                legacy_runner._fixed,
                "DEFAULT_CLAIM_REGISTRY",
                unknown_registry,
            ),
            mock.patch.object(
                runner,
                "http_request",
                side_effect=OSError("offline fake HTTP failure"),
            ),
            self.assertRaises(runner.N8PhysicalActionUnknown),
        ):
            runner.run_n8_physical_action_once(
                row["action_key"],
                unknown_destination,
                "http://fake-device",
                **common,
                wall_clock=lambda: self.fixture.live_nows[0],
            )
        self.assertEqual(len(list(unknown_registry.glob("*.json"))), 1)
        self.assertTrue((unknown_destination / runner.EVIDENCE_FILENAME).is_file())
        result = json.loads(
            (unknown_destination / runner.P0_RESULT_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["state"], ResultState.UNKNOWN_DO_NOT_RETRY.value)
        self.assertEqual(result["post_request_count"], 0)

        uncertain_registry = self.root / "claim-uncertain-registry"
        uncertain_destination = self.root / "claim-uncertain-result"
        original_atomic_commit = legacy_runner._fixed._atomic_commit

        def uncertain_claim_commit(
            path: Path, payload: bytes, *, unknown_after_commit: bool
        ) -> None:
            if unknown_after_commit:
                raise legacy_runner._fixed.N2PFixedActionUnknown(
                    "injected uncertain claim commit"
                )
            original_atomic_commit(
                path, payload, unknown_after_commit=unknown_after_commit
            )

        with (
            mock.patch.object(
                legacy_runner._fixed,
                "DEFAULT_CLAIM_REGISTRY",
                uncertain_registry,
            ),
            mock.patch.object(
                legacy_runner._fixed,
                "_atomic_commit",
                side_effect=uncertain_claim_commit,
            ),
            mock.patch.object(
                runner,
                "http_request",
                side_effect=AssertionError("network must not occur"),
            ),
            self.assertRaises(runner.N8PhysicalActionUnknown),
        ):
            runner.run_n8_physical_action_once(
                row["action_key"],
                uncertain_destination,
                "http://fake-device",
                **common,
                wall_clock=lambda: self.fixture.live_nows[0],
            )
        self.assertTrue(
            (
                uncertain_destination
                / runner.CLAIM_COMMIT_UNCERTAIN_FILENAME
            ).is_file()
        )
        uncertain_result = json.loads(
            (uncertain_destination / runner.P0_RESULT_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            uncertain_result["state"], ResultState.UNKNOWN_DO_NOT_RETRY.value
        )
        self.assertEqual(uncertain_result["post_request_count"], 0)

    def test_operator_cli_modes_are_mutually_exclusive_and_complete(self) -> None:
        parsed = runner.parse_args(
            [
                "--validate-result",
                "--result-file",
                str(
                    self.fixture.result_directories[0]
                    / runner.P0_RESULT_FILENAME
                ),
                "--reviewer-key",
                str(self.fixture.reviewer_key),
            ]
        )
        self.assertTrue(parsed.validate_result)
        with self.assertRaises(SystemExit):
            runner.parse_args(["--describe-only", "--finalize"])
        with self.assertRaises(SystemExit):
            runner.parse_args(["--action", frozen.FIXED_ACTION_KEYS[0]])


if __name__ == "__main__":
    unittest.main()
