from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import g1_s1_rc2g_map_baseline_once as baseline
from tools import g1_s1_rc2g_n1_low_balanced_map_primer_once as runner
from tests.test_g1_s1_rc2g_map_baseline_once import (
    ScriptedRequester,
    TickClock,
    _responses,
)


class N1LowBalancedMapPrimerOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.registry.mkdir()
        self.result_dir = self.root / "result"

    def _run(
        self,
        requester: ScriptedRequester,
        *,
        result_dir: Path | None = None,
        registry: Path | None = None,
        **overrides,
    ):
        active_registry = self.registry if registry is None else registry
        active_registry.mkdir(exist_ok=True)
        arguments = {
            "authorization_confirmation": runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
            "confirm_rc2g_flashed_fresh_boot": True,
            "confirm_j2_powered_supervised": True,
            "confirm_supply_and_temperature_normal": True,
            "confirm_single_visible_primer_refresh": True,
            "sleeper": lambda _seconds: None,
            "clock": TickClock(),
        }
        arguments.update(overrides)
        with mock.patch.object(
            runner, "_authorization_registry", return_value=active_registry
        ), mock.patch.object(runner, "http_request", side_effect=requester):
            return runner.run_n1_low_balanced_map_primer_once(
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                **arguments,
            )

    def test_action_claim_authorization_and_registry_are_independent(self) -> None:
        self.assertNotEqual(runner.FIXED_ACTION_ID, baseline.FIXED_ACTION_ID)
        self.assertNotEqual(
            runner.DEFAULT_AUTHORIZATION_REGISTRY,
            baseline.DEFAULT_AUTHORIZATION_REGISTRY,
        )
        self.assertNotEqual(
            runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
            baseline.REQUIRED_AUTHORIZATION_CONFIRMATION,
        )
        self.assertNotEqual(
            runner.ACTION_IDENTITY_SHA256, baseline.ACTION_IDENTITY_SHA256
        )
        self.assertEqual(runner.PILOT_ID, "n1-low-balanced-pilot-v1")
        self.assertTrue(
            runner.ACTION_IDENTITY["claim_scope"]["workspace_global_fixed_action"]
        )
        self.assertFalse(
            runner.ACTION_IDENTITY["claim_scope"]["partitioned_by_campaign_id"]
        )
        self.assertFalse(
            runner.ACTION_IDENTITY["pilot_binding"][
                "follow_up_visible_refresh_authorized"
            ]
        )

    def test_frozen_identity_reuses_exact_rc2g_map_and_strict_gates(self) -> None:
        self.assertEqual(runner.EXPECTED_BUILD_TAG, baseline.EXPECTED_BUILD_TAG)
        self.assertEqual(runner.EXPECTED_FRAME_SHA256, baseline.EXPECTED_FRAME_SHA256)
        self.assertEqual(
            (runner.EXPECTED_CS1_DTM_FNV1A, runner.EXPECTED_CS2_DTM_FNV1A),
            (0xF26832DD, 0xFE199FF5),
        )
        self.assertEqual(
            runner.NOMINAL_TIMING_RANGES_MS, baseline.NOMINAL_TIMING_RANGES_MS
        )
        self.assertEqual(
            runner.AUTHORIZATION_CONFIRMATION_SHA256,
            "403d0c52a6c34ce8dee1226bd5422f8c5df586ea6dc2c09a0b812d14746aeb7d",
        )
        self.assertEqual(
            runner.ACTION_IDENTITY_SHA256,
            "6354b456bc71033fa4ef96ebc8ff972e8d1e45f0f27403977c99bdee4cc20660",
        )
        self.assertEqual(
            runner.AUTHORIZATION_CONFIRMATION_SHA256,
            hashlib.sha256(
                runner.REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii")
            ).hexdigest(),
        )
        self.assertEqual(
            runner.ACTION_IDENTITY_SHA256,
            hashlib.sha256(runner._canonical_json(runner.ACTION_IDENTITY)).hexdigest(),
        )

    def test_cli_and_public_function_have_no_campaign_or_claim_partition_override(self) -> None:
        parsed = runner.parse_args(
            [
                "--result-dir",
                str(self.result_dir),
                "--url",
                "http://device",
                "--confirm",
                runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                "--confirm-rc2g-flashed-fresh-boot",
                "--confirm-j2-powered-supervised",
                "--confirm-supply-and-temperature-normal",
                "--confirm-single-visible-primer-refresh",
            ]
        )
        self.assertTrue(parsed.confirm_single_visible_primer_refresh)
        parameters = inspect.signature(
            runner.run_n1_low_balanced_map_primer_once
        ).parameters
        for forbidden in (
            "campaign_id",
            "action_id",
            "pilot_id",
            "registry",
            "requester",
            "frame",
            "retry",
            "recovery",
            "force",
        ):
            self.assertNotIn(forbidden, parameters)
        source = inspect.getsource(runner.parse_args)
        for forbidden_option in (
            "--campaign-id",
            "--action-id",
            "--registry",
            "--retry",
            "--recovery",
            "--force",
        ):
            self.assertNotIn(forbidden_option, source)

    def test_wrong_or_missing_confirmation_is_preclaim_zero_network(self) -> None:
        for field in (
            "confirm_rc2g_flashed_fresh_boot",
            "confirm_j2_powered_supervised",
            "confirm_supply_and_temperature_normal",
            "confirm_single_visible_primer_refresh",
        ):
            with self.subTest(field=field), mock.patch.object(
                runner, "_authorization_registry"
            ) as registry, mock.patch.object(runner, "http_request") as request:
                arguments = {
                    "authorization_confirmation": runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    "confirm_rc2g_flashed_fresh_boot": True,
                    "confirm_j2_powered_supervised": True,
                    "confirm_supply_and_temperature_normal": True,
                    "confirm_single_visible_primer_refresh": True,
                }
                arguments[field] = False
                with self.assertRaisesRegex(
                    runner.N1LowBalancedMapPrimerError, "all four"
                ):
                    runner.run_n1_low_balanced_map_primer_once(
                        self.result_dir, "http://device", **arguments
                    )
            registry.assert_not_called()
            request.assert_not_called()
        with mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(
                runner.N1LowBalancedMapPrimerError, "exact N1"
            ):
                runner.run_n1_low_balanced_map_primer_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation="yes",
                    confirm_rc2g_flashed_fresh_boot=True,
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_single_visible_primer_refresh=True,
                )
        registry.assert_not_called()
        request.assert_not_called()

    def test_claim_exists_before_first_network_and_success_is_exact_map_job1(self) -> None:
        def assert_claim_exists() -> None:
            self.assertTrue((self.registry / runner.FIXED_ACTION_ID).is_file())

        scripted = ScriptedRequester(
            _responses(), before_first_call=assert_claim_exists
        )
        result = self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(result["fresh_boot_preflight"]["job_raw"]["job_id"], 0)
        evidence = result["completed_map_evidence"]
        self.assertEqual(evidence["job_raw"]["job_id"], 1)
        self.assertEqual(evidence["diagnostic_raw"]["operation_id"], 1)
        self.assertEqual(evidence["nominal_timing"]["drf_ms"], 21_690)
        self.assertTrue(evidence["busy_trace"]["command_edge_contract_verified"])
        self.assertFalse(result["follow_up_low_balanced_refresh_authorized"])
        self.assertFalse(result["campaign_id_override_supported"])
        self.assertEqual(
            result["outcome"], "protocol_verified_manual_observation_required"
        )

    def test_fresh_boot_violation_is_unknown_zero_post_with_read_only_evidence(self) -> None:
        responses = _responses()
        stale = json.loads(responses["/api/job"][0][1])
        stale["job_id"] = 7
        responses["/api/job"][0] = (200, json.dumps(stale))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.N1LowBalancedMapPrimerUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 0)
        self.assertIsNotNone(recorded["best_effort_postclaim_evidence"])

    def test_strict_timing_failure_preserves_report_diagnostic_and_gpio(self) -> None:
        scripted = ScriptedRequester(
            _responses(
                timing={
                    "total_ms": 70_000,
                    "pon_ms": 37_110,
                    "drf_ms": 21_690,
                }
            )
        )
        with self.assertRaises(runner.N1LowBalancedMapPrimerUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIsNotNone(recorded["network_report"])
        self.assertEqual(recorded["post_refresh_diagnostic_raw"]["pon_ms"], 37_110)
        self.assertIsNotNone(recorded["post_refresh_gpio_status_raw"])

    def test_post_gpio_output_failure_preserves_raw_snapshot(self) -> None:
        responses = _responses()
        raw = {"busy": 1, "rst": 0, "cs": 1, "cs2": 0}
        responses["/api/diagnostic/status"][1] = (200, json.dumps(raw))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.N1LowBalancedMapPrimerUnknown):
            self._run(scripted)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["post_refresh_gpio_status_raw"], raw)
        self.assertIsNotNone(recorded["post_refresh_diagnostic_raw"])
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)

    def test_transport_unknown_consumes_fixed_claim_for_every_result_directory(self) -> None:
        responses = _responses()
        responses["/api/frame"] = [OSError("simulated lost response")]
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.N1LowBalancedMapPrimerUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        calls = list(scripted.calls)
        with self.assertRaisesRegex(
            runner.N1LowBalancedMapPrimerError, "already permanently"
        ):
            self._run(scripted, result_dir=self.root / "different-result-directory")
        self.assertEqual(scripted.calls, calls)
        self.assertFalse((self.root / "different-result-directory").exists())

    def test_audited_requester_blocks_second_post_before_issuing_it(self) -> None:
        scripted = ScriptedRequester(_responses())

        def malicious_refresh(base_url, frame, *, requester, **_kwargs):
            requester(
                base_url, "/api/frame", method="POST", data=frame, timeout=20.0
            )
            requester(
                base_url, "/api/frame", method="POST", data=frame, timeout=20.0
            )
            raise AssertionError("unreachable")

        with mock.patch.object(
            runner.baseline, "perform_refresh", side_effect=malicious_refresh
        ):
            with self.assertRaises(runner.N1LowBalancedMapPrimerUnknown):
                self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["request_audit"]["post_attempt_count"], 2)
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)

    def test_existing_result_directory_rejected_before_claim_and_network(self) -> None:
        self.result_dir.mkdir()
        with mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(
                runner.N1LowBalancedMapPrimerError, "already exists"
            ):
                runner.run_n1_low_balanced_map_primer_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_rc2g_flashed_fresh_boot=True,
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_single_visible_primer_refresh=True,
                )
        registry.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
