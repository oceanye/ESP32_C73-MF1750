from __future__ import annotations

from copy import deepcopy
import inspect
import unittest
from unittest import mock

from tests.n3_bundle_fixture import (
    build_finalized_session,
    registered_assets,
)
from tools import g1_s1_n3_analyzer as analyzer
from tools import g1_s1_n3_execution_contract as execution
from tools import g1_s1_rc2g_n3_once as runner


class N3DeepBundleAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = execution.compile_n3b_exact_plan(
            measurement_assets=registered_assets()
        )
        cls.pair = build_finalized_session(cls.plan, 0)

    def test_public_analyzer_surface_accepts_deep_bundles_not_loose_observations(self) -> None:
        self.assertEqual(
            set(inspect.signature(analyzer.analyze_n3b).parameters),
            {"plan", "session_bundles"},
        )
        with self.assertRaises(TypeError):
            analyzer.analyze_n3b(self.plan, observations=[])  # type: ignore[call-arg]

    def test_one_deep_pair_derives_canonical_session_observation(self) -> None:
        observation = analyzer.build_n3_session_observation(
            self.plan, **self.pair
        )
        route = self.plan["selected_routes"][0]
        self.assertEqual(
            observation["map_action_identity_sha256"],
            route["map_action_identity_sha256"],
        )
        self.assertEqual(
            observation["target_action_identity_sha256"],
            route["target_action_identity_sha256"],
        )
        self.assertEqual(observation["candidate_cell_id"], "Q1")
        self.assertEqual(observation["pair_state"], "complete-pass-pair")
        analyzer.validate_n3_observation(
            self.plan["execution_manifest"], observation
        )

    def test_analyzer_replays_nested_bundle_and_finalization_validators(self) -> None:
        tampered = deepcopy(self.pair)
        tampered["target_bundle"]["observation"]["visual"][
            "photo_difference_score"
        ] += 0.5
        with self.assertRaisesRegex(analyzer.N3AnalysisError, "bundle pair is invalid"):
            analyzer.build_n3_session_observation(self.plan, **tampered)

        tampered = deepcopy(self.pair)
        tampered["target_bundle"]["finalization"]["visual_pass"] = False
        with self.assertRaisesRegex(analyzer.N3AnalysisError, "bundle pair is invalid"):
            analyzer.build_n3_session_observation(self.plan, **tampered)

    def test_incomplete_n3b_report_is_descriptive_and_small_sample_guarded(self) -> None:
        report = analyzer.analyze_n3b(
            self.plan, session_bundles=[self.pair]
        )
        self.assertFalse(report["complete"])
        self.assertFalse(report["analysis_ready"])
        self.assertEqual(report["expected_observation_count"], 16)
        self.assertEqual(report["observed_observation_count"], 1)
        self.assertTrue(report["analyzer_accepts_deep_bundles_only"])
        self.assertEqual(len(report["validated_bundle_chains"]), 1)
        summary = report["overall_metric_summaries"][
            "visual.photo_difference_score"
        ]
        self.assertEqual(summary["n"], 1)
        self.assertIsNone(summary["p95"])
        self.assertIsNone(summary["p99"])
        self.assertEqual(
            summary["extreme_reporting"],
            "maximum-observed-only-n-less-than-10",
        )
        analyzer.validate_n3_report(report, plan=self.plan)

    def test_cross_route_bundle_pair_is_rejected(self) -> None:
        foreign = build_finalized_session(self.plan, 1)
        replay = {
            "map_bundle": foreign["map_bundle"],
            "target_bundle": self.pair["target_bundle"],
        }
        with self.assertRaisesRegex(analyzer.N3AnalysisError, "bundle pair is invalid"):
            analyzer.build_n3_session_observation(self.plan, **replay)

    def test_analysis_path_performs_no_network_claim_or_authorization(self) -> None:
        with (
            mock.patch.object(
                runner, "http_request", side_effect=AssertionError("network")
            ),
            mock.patch.object(
                runner, "_claim_action", side_effect=AssertionError("claim")
            ),
            mock.patch.object(
                runner,
                "required_authorization_confirmation",
                side_effect=AssertionError("authorization"),
            ),
        ):
            report = analyzer.analyze_n3_exact_plan(
                self.plan, session_bundles=[self.pair]
            )
        self.assertEqual(report["classification"]["network_io_performed"], False)

    def test_report_plan_binding_and_bundle_chain_tamper_fail_closed(self) -> None:
        report = analyzer.analyze_n3b(self.plan, session_bundles=[self.pair])
        tampered = deepcopy(report)
        tampered["exact_plan_id"] = "foreign-plan"
        with self.assertRaisesRegex(
            analyzer.N3AnalysisError, "binding changed|integrity"
        ):
            analyzer.validate_n3_report(tampered, plan=self.plan)
        tampered = deepcopy(report)
        tampered["validated_bundle_chains"][0][
            "execution_evidence_verified"
        ] = False
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = analyzer._integrity(
            unsigned, analyzer.REPORT_HASH_SCOPE
        )
        with self.assertRaisesRegex(analyzer.N3AnalysisError, "unverified"):
            analyzer.validate_n3_report(tampered, plan=self.plan)


if __name__ == "__main__":
    unittest.main()
