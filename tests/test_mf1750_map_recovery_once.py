from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.epd_frame import generate_fixture
from tests.test_frame_tool import ScriptedRequester, valid_refresh_responses
from tools import mf1750_map_recovery_once as recovery


class MapRecoveryOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.registry.mkdir()
        self.result_dir = self.root / "result"
        self.frame = generate_fixture("map-orient-v1")
        self.incident_directory = self.root / "incident"
        self.incident_directory.mkdir()
        self.incident_result = self.incident_directory / recovery._INCIDENT_RESULT_FILENAME
        self.job_path = self.incident_directory / recovery._DEVICE_JOB_FILENAME
        self.diagnostic_path = (
            self.incident_directory / recovery._DEVICE_DIAGNOSTIC_FILENAME
        )
        self.status_path = self.incident_directory / recovery._DEVICE_STATUS_FILENAME
        self.incident_result.write_bytes(
            recovery._canonical_json(
                {
                    "kind": recovery.INCIDENT_RESULT_KIND,
                    "attempt_id": recovery.INCIDENT_ATTEMPT_ID,
                    "outcome": "unknown_do_not_retry",
                    "authorization_consumed_permanently": True,
                    "candidate": {"frame_fnv1a": recovery.INCIDENT_FRAME_FNV1A},
                }
            )
        )
        self.job = {
            "job_id": 2,
            "action": "uploaded_frame",
            "state": "failed",
            "result": False,
            "queued_at_ms": 1000,
            "started_at_ms": 1010,
            "finished_at_ms": 96610,
            "frame_fnv1a": int(recovery.INCIDENT_FRAME_FNV1A, 16),
        }
        self.diagnostic = {
            "job_id": 2,
            "job_action": "uploaded_frame",
            "job_state": "failed",
            "job_result": False,
            "job_operation_id": 2,
            "operation_id": 2,
            "valid": True,
            "running": False,
            "sequence_ok": False,
            "wait_timeout": True,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": False,
            "post_psr_busy_seen": False,
            "spi_hz": 1_000_000,
            "input_fnv1a": int(recovery.INCIDENT_FRAME_FNV1A, 16),
            "cs1_dtm_fnv1a": 0x43E97823,
            "cs2_dtm_fnv1a": 0xE8FA6243,
            "pon_ms": 180,
            "drf_ms": 60010,
            "pof_ms": 0,
            "post_psr_ms": 0,
            "last_wait_ms": 30005,
            "last_wait_stage": "POF cleanup after DRF failure",
            "timeout_stage": "DRF",
            "busy_missing_stage": "none",
            "job_queued_at_ms": 1000,
            "job_started_at_ms": 1010,
            "job_finished_at_ms": 96610,
            "mapping": {
                "cs1_source_half": 0,
                "cs1_flip_x": False,
                "cs1_flip_y": False,
                "cs1_nibble_swap": False,
                "cs2_source_half": 1,
                "cs2_flip_x": False,
                "cs2_flip_y": False,
                "cs2_nibble_swap": False,
            },
        }
        self.status = {"busy": 0, "rst": 0, "cs": 0, "cs2": 0}
        self._write_raw_evidence()
        self.original_evidence_hashes = self._evidence_hashes()

    def _write_raw_evidence(self) -> None:
        self.job_path.write_bytes(recovery._canonical_json(self.job))
        self.diagnostic_path.write_bytes(recovery._canonical_json(self.diagnostic))
        self.status_path.write_bytes(recovery._canonical_json(self.status))

    def _evidence_hashes(self) -> dict[str, str]:
        return {
            "result": hashlib.sha256(self.incident_result.read_bytes()).hexdigest(),
            "job": hashlib.sha256(self.job_path.read_bytes()).hexdigest(),
            "diagnostic": hashlib.sha256(self.diagnostic_path.read_bytes()).hexdigest(),
            "status": hashlib.sha256(self.status_path.read_bytes()).hexdigest(),
        }

    @contextlib.contextmanager
    def _patched_frozen_evidence(self, hashes=None):
        selected = self._evidence_hashes() if hashes is None else hashes
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    recovery,
                    "_fixed_incident_directory_path",
                    return_value=self.incident_directory,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    recovery, "_FIXED_INCIDENT_RESULT_SHA256", selected["result"]
                )
            )
            stack.enter_context(
                mock.patch.object(recovery, "_FIXED_DEVICE_JOB_SHA256", selected["job"])
            )
            stack.enter_context(
                mock.patch.object(
                    recovery,
                    "_FIXED_DEVICE_DIAGNOSTIC_SHA256",
                    selected["diagnostic"],
                )
            )
            stack.enter_context(
                mock.patch.object(
                    recovery, "_FIXED_DEVICE_STATUS_SHA256", selected["status"]
                )
            )
            yield

    def _run(self, requester, *, result_dir=None, **overrides):
        actual_perform_refresh = recovery.perform_refresh

        def perform_fixed(base_url, frame):
            return actual_perform_refresh(
                base_url,
                frame,
                expected_mappings=recovery.FIXED_CONTROLLER_MAPPINGS,
                requester=requester,
                sleeper=lambda _seconds: None,
            )

        arguments = {
            "incident_attempt_id": recovery.INCIDENT_ATTEMPT_ID,
            "confirm_recovery_after_incident": True,
            "confirm_j2_powered_supervised": True,
            "confirm_cold_start": True,
        }
        arguments.update(overrides)
        with self._patched_frozen_evidence(), mock.patch.object(
            recovery, "_authorization_registry", return_value=self.registry
        ), mock.patch.object(recovery, "_perform_fixed_refresh", side_effect=perform_fixed):
            return recovery.run_map_recovery_once(
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                **arguments,
            )

    def test_success_posts_fixed_map_once_and_binds_claim(self) -> None:
        scripted = ScriptedRequester(valid_refresh_responses(self.frame))

        def requester(*args, **kwargs):
            self.assertTrue((self.result_dir / recovery.LOCK_FILENAME).is_file())
            return scripted(*args, **kwargs)

        result = self._run(requester)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        lock = json.loads((self.result_dir / recovery.LOCK_FILENAME).read_text("utf-8"))
        stored = json.loads(
            (self.result_dir / recovery.RESULT_FILENAME).read_text("utf-8")
        )
        claim_path = self.registry / recovery.CLAIM_FILENAME
        claim_bytes = claim_path.read_bytes()
        claim = json.loads(claim_bytes)
        expected_reference = {
            "registry_id": recovery.CLAIM_REGISTRY_ID,
            "file": recovery.RECOVERY_IDENTITY_SHA256,
            "sha256": hashlib.sha256(claim_bytes).hexdigest(),
            "recovery_identity_sha256": recovery.RECOVERY_IDENTITY_SHA256,
            "attempt_id": claim["attempt_id"],
            "state": "recovery_identity_permanently_consumed_do_not_rerun",
        }
        self.assertEqual(lock["authorization_claim"], expected_reference)
        self.assertEqual(result["authorization_claim"], expected_reference)
        self.assertEqual(stored, result)
        self.assertEqual(result["fixture"]["sha256"], recovery.MAP_FRAME_SHA256)
        self.assertEqual(result["fixture"]["full_fnv1a"], "0x9D04142D")
        self.assertEqual(result["outcome"], "protocol_verified_manual_observation_required")
        self.assertIs(result["formal"], False)
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["hardware_tested"], False)

    def test_same_recovery_identity_new_result_directory_still_has_only_one_post(self) -> None:
        parameters = inspect.signature(recovery.run_map_recovery_once).parameters
        for forbidden in ("frame", "pattern", "requester", "authorization_registry", "registry"):
            self.assertNotIn(forbidden, parameters)

        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        result_a = self.root / "result-a"
        result_b = self.root / "result-b"
        self._run(requester, result_dir=result_a)
        calls_after_first = list(requester.calls)
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)

        with self.assertRaisesRegex(recovery.MapRecoveryError, "already permanently consumed"):
            self._run(requester, result_dir=result_b)

        self.assertEqual(requester.calls, calls_after_first)
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertFalse(result_b.exists())

    def test_network_exception_records_unknown_and_cannot_be_reused(self) -> None:
        responses = valid_refresh_responses(self.frame)
        responses["/api/frame"] = [OSError("simulated transport loss")]
        requester = ScriptedRequester(responses)

        with self.assertRaises(recovery.MapRecoveryUnknown):
            self._run(requester)

        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        lock = json.loads((self.result_dir / recovery.LOCK_FILENAME).read_text("utf-8"))
        result = json.loads((self.result_dir / recovery.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(result["outcome"], "unknown_do_not_retry")
        self.assertEqual(result["authorization_claim"], lock["authorization_claim"])
        calls_before = list(requester.calls)
        retry_dir = self.root / "after-network-failure"
        with self.assertRaisesRegex(recovery.MapRecoveryError, "already permanently consumed"):
            self._run(requester, result_dir=retry_dir)
        self.assertEqual(requester.calls, calls_before)
        self.assertFalse(retry_dir.exists())

    def test_local_failure_after_claim_is_unknown_and_cannot_be_reused(self) -> None:
        requester = ScriptedRequester({})
        first_dir = self.root / "local-failure"
        with mock.patch.object(
            recovery,
            "_create_result_directory",
            side_effect=recovery.MapRecoveryError("simulated local failure"),
        ):
            with self.assertRaises(recovery.MapRecoveryUnknown):
                self._run(requester, result_dir=first_dir)

        self.assertEqual(requester.calls, [])
        self.assertFalse(first_dir.exists())
        self.assertTrue((self.registry / recovery.CLAIM_FILENAME).is_file())
        retry_dir = self.root / "after-local-failure"
        with self.assertRaisesRegex(recovery.MapRecoveryError, "already permanently consumed"):
            self._run(requester, result_dir=retry_dir)
        self.assertEqual(requester.calls, [])
        self.assertFalse(retry_dir.exists())

    def test_non_map_frame_cannot_be_supplied_or_generated(self) -> None:
        with self.assertRaises(TypeError):
            recovery.run_map_recovery_once(
                self.result_dir,
                "http://device",
                incident_attempt_id=recovery.INCIDENT_ATTEMPT_ID,
                confirm_recovery_after_incident=True,
                confirm_j2_powered_supervised=True,
                confirm_cold_start=True,
                frame=generate_fixture("global-h-bars"),
            )

        registry = mock.Mock()
        network = mock.Mock()
        with self._patched_frozen_evidence(), mock.patch.object(
            recovery, "generate_fixture", return_value=generate_fixture("global-h-bars")
        ), mock.patch.object(recovery, "_authorization_registry", registry), mock.patch.object(
            recovery, "_perform_fixed_refresh", network
        ):
            with self.assertRaisesRegex(recovery.MapRecoveryError, "identity changed"):
                recovery.run_map_recovery_once(
                    self.result_dir,
                    "http://device",
                    incident_attempt_id=recovery.INCIDENT_ATTEMPT_ID,
                    confirm_recovery_after_incident=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                )
        registry.assert_not_called()
        network.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_cli_requires_incident_file_hash_pair_or_explicit_attempt(self) -> None:
        common = ["--result-dir", str(self.result_dir), "--url", "http://device"]
        with self.assertRaises(SystemExit):
            recovery.parse_args(common)
        with self.assertRaises(SystemExit):
            recovery.parse_args(common + ["--incident-result-path", "incident.json"])
        parsed = recovery.parse_args(
            common + ["--incident-attempt-id", recovery.INCIDENT_ATTEMPT_ID]
        )
        self.assertEqual(parsed.incident_attempt_id, recovery.INCIDENT_ATTEMPT_ID)

    def test_incident_result_path_and_attempt_id_both_verify_frozen_bundle(self) -> None:
        with self._patched_frozen_evidence():
            evidence = recovery._incident_evidence(
                incident_result_path=self.incident_result,
                incident_result_sha256=self._evidence_hashes()["result"],
                incident_attempt_id=None,
            )
            by_id = recovery._incident_evidence(
                incident_result_path=None,
                incident_result_sha256=None,
                incident_attempt_id=recovery.INCIDENT_ATTEMPT_ID,
            )
        self.assertEqual(evidence["incident_attempt_id"], recovery.INCIDENT_ATTEMPT_ID)
        self.assertEqual(evidence["files"], by_id["files"])
        self.assertEqual(len(evidence["files"]), 4)
        self.assertTrue(all(evidence["semantics_verified"].values()))

    def test_self_reported_hash_and_five_field_forgery_are_rejected(self) -> None:
        forged = self.root / "forged-result.json"
        forged.write_bytes(self.incident_result.read_bytes())
        self.assertNotEqual(
            hashlib.sha256(forged.read_bytes()).hexdigest(),
            recovery._FIXED_INCIDENT_RESULT_SHA256,
        )
        with self.assertRaisesRegex(recovery.MapRecoveryError, "not the frozen SHA-256"):
            recovery._incident_evidence(
                incident_result_path=forged,
                incident_result_sha256=hashlib.sha256(forged.read_bytes()).hexdigest(),
                incident_attempt_id=None,
            )

    def test_attempt_id_mode_rejects_semantically_forged_raw_evidence(self) -> None:
        scenarios = (
            (self.job, "state", "completed", "failed job 2"),
            (self.diagnostic, "drf_ms", 60011, "DRF and cleanup timeouts"),
            (self.status, "cs2", 1, "panel pins low"),
        )
        for record, key, value, message in scenarios:
            with self.subTest(key=key):
                original = record[key]
                record[key] = value
                self._write_raw_evidence()
                try:
                    with self._patched_frozen_evidence():
                        with self.assertRaisesRegex(recovery.MapRecoveryError, message):
                            recovery._incident_evidence(
                                incident_result_path=None,
                                incident_result_sha256=None,
                                incident_attempt_id=recovery.INCIDENT_ATTEMPT_ID,
                            )
                finally:
                    record[key] = original
                    self._write_raw_evidence()

    def test_claim_temp_unlink_failure_after_link_is_safely_ignored(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        real_unlink = Path.unlink

        def unlink_with_claim_staging_failure(path, *args, **kwargs):
            if (
                path.parent == self.registry
                and path.name.startswith(f".{recovery.CLAIM_FILENAME}.tmp-")
            ):
                raise OSError("simulated unlink failure after successful claim link")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(
            Path, "unlink", autospec=True, side_effect=unlink_with_claim_staging_failure
        ):
            result = self._run(requester)

        self.assertEqual(result["outcome"], "protocol_verified_manual_observation_required")
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertTrue((self.registry / recovery.CLAIM_FILENAME).is_file())
        self.assertTrue((self.result_dir / recovery.LOCK_FILENAME).is_file())
        self.assertTrue((self.result_dir / recovery.RESULT_FILENAME).is_file())


if __name__ == "__main__":
    unittest.main()
