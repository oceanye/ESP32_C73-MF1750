from __future__ import annotations

from copy import deepcopy
import inspect
import unittest

from host.visible_refresh_campaign import ResultState, build_result_record, result_file_sha256
from tests import n8_bundle_fixture as fixture
from tools import g1_s1_n8_analyzer as analyzer
from tools import g1_s1_n8_execution_contract as execution


def _rehash_camera_replay(bundle: dict[str, object], source: dict[str, object]) -> None:
    source_camera = source["observation"]["camera"]
    target_camera = bundle["observation"]["camera"]
    target_camera["capture_file_sha256"] = source_camera["capture_file_sha256"]
    target_camera["capture_evidence_sha256"] = source_camera["capture_evidence_sha256"]
    bundle["observation_file_sha256"] = execution._sha256(bundle["observation"])
    finalization = bundle["finalization"]
    finalization["action_observation_file_sha256"] = bundle["observation_file_sha256"]
    finalization["camera_capture_file_sha256"] = target_camera["capture_file_sha256"]
    bundle["finalization_file_sha256"] = execution._sha256(finalization)
    old_result = bundle["result"]
    result = build_result_record(
        action_identity_sha256=old_result["action_identity_sha256"],
        state=old_result["state"],
        completed_at=old_result["completed_at"],
        evidence_manifest_sha256=bundle["finalization_file_sha256"],
        post_request_count=old_result["post_request_count"],
        details=old_result["details"],
    )
    bundle["result"] = result
    bundle["result_file_sha256"] = result_file_sha256(result)


class N8DeepBundleAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundles = list(fixture.build_all_pass())

    def test_analyzer_boundary_accepts_only_finalized_deep_bundles(self) -> None:
        signature = inspect.signature(analyzer.analyze_n8_bundles).parameters
        self.assertIn("bundles", signature)
        for forbidden in ("observations", "photos", "temperatures", "ledgers"):
            self.assertNotIn(forbidden, signature)
        with self.assertRaises(analyzer.N8AnalysisError):
            analyzer.validate_n8_action_bundle(
                {
                    "action_identity_sha256": execution.FIXED_ACTION_SHA256S[
                        "n8-aba-q1-q4-q1-map"
                    ],
                    "photo": {"fidelity_pass": True},
                    "external_temperature": {"pre_c": 24},
                }
            )

    def test_complete_15_action_report_is_descriptive_and_never_qualified(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        self.assertEqual(report["bundle_count"], 15)
        self.assertEqual(report["sequence_ledger_count"], 5)
        self.assertTrue(report["complete"])
        self.assertTrue(report["analysis_ready"])
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertFalse(report["hardware_qualified"])
        self.assertFalse(report["algorithm_qualified"])
        self.assertTrue(
            report["classification"]["input_requires_deep_verified_finalized_bundles"]
        )
        analyzer.validate_n8_report(report, bundles=self.bundles)

    def test_five_ledgers_have_exact_4_5_2_2_2_action_counts_and_sha_chains(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        counts = {
            key: value["observed_action_count"]
            for key, value in report["sequence_summaries"].items()
        }
        self.assertEqual(
            counts,
            {
                "n8-aba-q1-q4-q1": 4,
                "n8-warm-q1-q2-q3-q4": 5,
                "n8-temperature-low-q4": 2,
                "n8-temperature-nominal-q4": 2,
                "n8-temperature-high-q4": 2,
            },
        )
        warm = [
            bundle for bundle in self.bundles
            if bundle["evidence"]["sequence_id"] == "n8-warm-q1-q2-q3-q4"
        ]
        ledger = analyzer.build_n8_sequence_ledger(
            sequence_id="n8-warm-q1-q2-q3-q4", bundles=warm
        )
        self.assertEqual(
            ledger["derived_observations"][0]["completed_job_id"], 1
        )
        self.assertEqual(
            [item["completed_job_id"] for item in ledger["derived_observations"]],
            [1, 2, 3, 4, 5],
        )
        self.assertEqual(ledger["qualification_state"], "NOT_QUALIFIED")

    def test_aba_compares_a1_and_a2_after_b_not_map(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        aba = report["sequence_summaries"]["n8-aba-q1-q4-q1"]["aba_evidence"]
        self.assertEqual(aba["primer_role"], "MAP")
        self.assertFalse(aba["primer_is_carryover_target"])
        self.assertEqual(aba["direct_visible_history_role"], "B")
        self.assertEqual(aba["comparison_roles"], ["A1", "A2"])
        self.assertTrue(aba["same_fixed_exposure"])
        self.assertTrue(aba["same_crop"])
        self.assertTrue(aba["comparable"])
        self.assertEqual(aba["qualification_state"], "NOT_QUALIFIED")

    def test_fixed_camera_temperature_meter_and_clock_are_comparable_and_unique(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        value = report["measurement_comparability"]
        self.assertTrue(value["fixed_measurement_assets"])
        self.assertTrue(value["no_capture_or_capture_evidence_replay"])
        self.assertEqual(value["raw_capture_count"], 15)
        self.assertEqual(value["unique_raw_capture_file_count"], 15)
        self.assertEqual(value["unique_capture_evidence_count"], 15)
        self.assertEqual(
            len(
                value[
                    "runtime_panel_firmware_profile_and_method_binding_sha256s"
                ]
            ),
            1,
        )
        self.assertTrue(value["comparable"])

    def test_one_session_per_temperature_bin_forbids_population_inference(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        bins = report["temperature_bin_sessions"]
        self.assertEqual(len(bins), 3)
        for value in bins.values():
            self.assertEqual(value["session_observation_count"], 1)
            self.assertFalse(value["population_inference_allowed"])
        self.assertFalse(report["interpretation"]["population_inference_allowed"])
        self.assertFalse(
            report["interpretation"]["causal_threshold_conclusion_allowed"]
        )

    def test_small_samples_never_report_p95_or_p99(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        for sequence in report["sequence_summaries"].values():
            for summary in sequence["metric_summaries"].values():
                self.assertLess(summary["n"], 10)
                self.assertIsNone(summary["p95"])
                self.assertIsNone(summary["p99"])
                self.assertIsNone(summary["percentile_method"])
        direct = analyzer.summarize_numeric(
            [10.0],
            u95_values=[0.25],
            u95_evidence_sha256s=[fixture.fixture_sha256("u95")],
        )
        self.assertEqual(direct["maximum_plus_u95"], 10.25)
        self.assertIsNone(direct["p95"])

    def test_incomplete_prefix_is_valid_but_not_analysis_ready(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles[:1])
        self.assertFalse(report["complete"])
        self.assertFalse(report["analysis_ready"])
        self.assertIsNone(report["terminal_state"])
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")

    def test_finalized_fail_stops_sequence_and_rejects_later_action(self) -> None:
        failed = fixture.build_sequence(
            "n8-temperature-high-q4",
            runtime=fixture.ready_manifest(),
            states={2: ResultState.FAIL},
        )
        ledger = analyzer.build_n8_sequence_ledger(
            sequence_id="n8-temperature-high-q4", bundles=failed
        )
        self.assertEqual(ledger["terminal_state"], "FINALIZED_FAIL_STOP_NO_RETRY")
        self.assertTrue(ledger["stop_remaining_actions"])
        report = analyzer.analyze_n8_bundles(bundles=failed)
        self.assertEqual(report["terminal_state"], "FINALIZED_FAIL_STOP_NO_RETRY")
        self.assertFalse(report["analysis_ready"])

    def test_capture_replay_is_deep_valid_but_analyzer_rejects_comparability(self) -> None:
        replay = deepcopy(self.bundles[:2])
        _rehash_camera_replay(replay[1], replay[0])
        execution.validate_n8_finalized_action_bundle(
            execution.compile_n8_execution_contract(), replay[1]
        )
        with self.assertRaises(analyzer.N8AnalysisError):
            analyzer.analyze_n8_bundles(bundles=replay)

    def test_report_tamper_with_recomputed_integrity_is_rejected_by_rebuild(self) -> None:
        report = analyzer.analyze_n8_bundles(bundles=self.bundles)
        tampered = deepcopy(report)
        tampered["analysis_ready"] = False
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = analyzer._integrity(unsigned, analyzer.REPORT_HASH_SCOPE)
        with self.assertRaises(analyzer.N8AnalysisError):
            analyzer.validate_n8_report(tampered, bundles=self.bundles)


if __name__ == "__main__":
    unittest.main()
