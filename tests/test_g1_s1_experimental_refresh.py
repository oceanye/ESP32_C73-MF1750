from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.epd_frame import FRAME_BYTES, fnv1a, generate_fixture, unpack_pixels
from tests.test_frame_tool import ScriptedRequester, valid_refresh_responses
from tools import g1_s1_experimental_refresh as runner


class ExperimentalRefreshRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.result_dir = self.root / "result"
        self.authorization_registry = self.root / "authorization-registry"
        self.authorization_registry.mkdir()
        self.frame = generate_fixture("global-h-bars")
        self.previews = {
            "source": b"source-png",
            "mapped": b"mapped-png",
            "final": b"final-png",
            "model": b"model-png",
        }
        for stage, payload in self.previews.items():
            (self.candidate / f"{stage}.png").write_bytes(payload)
        (self.candidate / "frame.bin").write_bytes(self.frame)
        self.manifest = self._manifest()
        self.manifest_bytes = runner._canonical_json(self.manifest)
        (self.candidate / "manifest.json").write_bytes(self.manifest_bytes)
        self.authorization = hashlib.sha256(self.manifest_bytes).hexdigest()

    def _manifest(self) -> dict:
        manifest = {
            "schema_version": 1,
            "kind": "mf1750-g1-s1-experimental-panel-candidate",
            "classification": {
                "experimental": True,
                "uncalibrated": True,
                "formal": False,
                "hardware_tested": False,
                "upload_authorized": False,
            },
            "source": {"pattern_id": "test"},
            "mapped": {"rgb8_sha256": "1" * 64},
            "frame": {
                "file": "frame.bin",
                "encoding": "canonical-row-major-two-4bit-codes-per-byte",
                "bytes": FRAME_BYTES,
                "sha256": hashlib.sha256(self.frame).hexdigest(),
                "fnv1a": f"0x{fnv1a(self.frame):08X}",
                "codes_sha256": hashlib.sha256(
                    unpack_pixels(self.frame, 1024, 600)
                ).hexdigest(),
            },
            "profile": {"profile_id": "synthetic-test"},
            "options": {
                "value": {"algorithm": "area-weighted-ordered-8x8"},
                "canonical_sha256": "2" * 64,
            },
            "previews": {
                stage: {
                    "file": f"{stage}.png",
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                for stage, payload in self.previews.items()
            },
            "simulation": {"report_canonical_sha256": "3" * 64},
            "transport": {
                "mode": "offline",
                "endpoint": None,
                "method": None,
                "device_io_performed": False,
                "hardware_tested": False,
            },
            "manifest_integrity": {
                "canonical_sha256": "4" * 64,
                "canonical_sha256_scope": "test",
            },
        }
        return manifest

    def _run(self, requester, *, result_dir=None, **overrides):
        arguments = {
            "authorized_manifest_sha256": self.authorization,
            "confirm_experimental_uncalibrated": True,
            "confirm_j2_powered_supervised": True,
            "confirm_cold_start": True,
            "sleeper": lambda _seconds: None,
        }
        arguments.update(overrides)
        real_perform_refresh = runner.perform_refresh

        def scripted_refresh(*args, **kwargs):
            return real_perform_refresh(*args, requester=requester, **kwargs)

        with mock.patch.object(
            runner, "validate_candidate_directory", return_value=self.manifest
        ), mock.patch.object(
            runner, "_authorization_registry", return_value=self.authorization_registry
        ), mock.patch.object(
            runner, "perform_refresh", side_effect=scripted_refresh
        ):
            return runner.run_experimental_refresh(
                self.candidate,
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                **arguments,
            )

    def test_candidate_tamper_and_authorization_mismatch_make_zero_network_requests(self) -> None:
        for scenario in ("tamper", "authorization"):
            with self.subTest(scenario=scenario):
                result_dir = self.root / f"result-{scenario}"
                requester = ScriptedRequester({})
                if scenario == "tamper":
                    original = (self.candidate / "frame.bin").read_bytes()
                    (self.candidate / "frame.bin").write_bytes(b"\x00" + original[1:])
                    authorization = self.authorization
                else:
                    original = None
                    authorization = "0" * 64
                with mock.patch.object(
                    runner, "validate_candidate_directory", return_value=self.manifest
                ), mock.patch.object(runner, "perform_refresh") as refresh:
                    with self.assertRaises(runner.ExperimentalRefreshError):
                        runner.run_experimental_refresh(
                            self.candidate,
                            result_dir,
                            "http://device",
                            authorized_manifest_sha256=authorization,
                            confirm_experimental_uncalibrated=True,
                            confirm_j2_powered_supervised=True,
                            confirm_cold_start=True,
                        )
                    refresh.assert_not_called()
                self.assertEqual(requester.calls, [])
                self.assertFalse(result_dir.exists())
                if original is not None:
                    (self.candidate / "frame.bin").write_bytes(original)

    def test_photo_source_input_is_exactly_bound_after_deep_validation(self) -> None:
        source_input = b"frozen-photo-input"
        (self.candidate / runner.SOURCE_INPUT_FILENAME).write_bytes(source_input)
        self.manifest["schema_version"] = 2
        self.manifest["source"] = {
            "source_kind": runner.PHOTO_SOURCE_KIND,
            "input": {
                "file": runner.SOURCE_INPUT_FILENAME,
                "bytes": len(source_input),
                "sha256": hashlib.sha256(source_input).hexdigest(),
            },
        }
        self.manifest_bytes = runner._canonical_json(self.manifest)
        (self.candidate / "manifest.json").write_bytes(self.manifest_bytes)
        self.authorization = hashlib.sha256(self.manifest_bytes).hexdigest()

        with mock.patch.object(
            runner, "validate_candidate_directory", return_value=self.manifest
        ):
            snapshot = runner._load_candidate_snapshot(
                self.candidate, self.authorization
            )
            self.assertEqual(snapshot.manifest_file_sha256, self.authorization)
            (self.candidate / runner.SOURCE_INPUT_FILENAME).write_bytes(b"tampered")
            with self.assertRaisesRegex(
                runner.ExperimentalRefreshError, "photo source input bytes changed"
            ):
                runner._load_candidate_snapshot(self.candidate, self.authorization)

    def test_success_posts_api_frame_exactly_once_and_remains_nonformal(self) -> None:
        parameters = inspect.signature(runner.run_experimental_refresh).parameters
        self.assertNotIn("requester", parameters)
        self.assertNotIn("authorization_registry", parameters)
        self.assertEqual(runner.RESULT_FILENAME, "EXPERIMENT-RESULT.json")
        scripted = ScriptedRequester(valid_refresh_responses(self.frame))

        def requester(*args, **kwargs):
            self.assertTrue(
                (self.result_dir / runner.LOCK_FILENAME).is_file(),
                "the immutable attempt lock must exist before the first request",
            )
            return scripted(*args, **kwargs)

        result = self._run(requester)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
        self.assertTrue((self.result_dir / runner.RESULT_FILENAME).is_file())
        claim_path = self.authorization_registry / self.authorization
        self.assertTrue(claim_path.is_file())
        self.assertEqual(
            [path.name for path in self.authorization_registry.iterdir()],
            [self.authorization],
        )
        claim_bytes = claim_path.read_bytes()
        claim = json.loads(claim_bytes)
        self.assertEqual(claim["kind"], runner.CLAIM_KIND)
        self.assertEqual(claim["manifest_file_sha256"], self.authorization)
        self.assertEqual(claim["state"], "authorization_permanently_consumed_do_not_rerun")
        lock = json.loads((self.result_dir / runner.LOCK_FILENAME).read_text("utf-8"))
        self.assertTrue(lock["created_at_utc"].endswith("Z"))
        self.assertEqual(lock["state"], "authorization_permanently_consumed_do_not_rerun")
        self.assertIs(lock["authorization_consumed_permanently"], True)
        self.assertEqual(lock["exact_action"], runner.EXACT_ACTION)
        self.assertEqual(lock["algorithm"], "area-weighted-ordered-8x8")
        self.assertEqual(lock["simulation_report_canonical_sha256"], "3" * 64)
        self.assertEqual(
            lock["fixed_controller_mappings"],
            [
                {"source_half": 0, "flip_x": False, "flip_y": False, "nibble_swap": False},
                {"source_half": 1, "flip_x": False, "flip_y": False, "nibble_swap": False},
            ],
        )
        self.assertEqual(result["outcome"], "protocol_verified_manual_observation_required")
        self.assertTrue(result["recorded_at_utc"].endswith("Z"))
        self.assertEqual(result["exact_action"], runner.EXACT_ACTION)
        self.assertEqual(
            result["authorization_state"],
            "authorization_permanently_consumed_do_not_rerun",
        )
        self.assertEqual(result["candidate"]["algorithm"], "area-weighted-ordered-8x8")
        self.assertEqual(result["candidate"]["simulation_report_canonical_sha256"], "3" * 64)
        expected_claim_reference = {
            "registry_id": runner.CLAIM_REGISTRY_ID,
            "file": self.authorization,
            "sha256": hashlib.sha256(claim_bytes).hexdigest(),
            "attempt_id": claim["attempt_id"],
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
        self.assertEqual(lock["authorization_claim"], expected_claim_reference)
        self.assertEqual(result["authorization_claim"], expected_claim_reference)
        self.assertIs(result["formal"], False)
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["hardware_tested"], False)
        self.assertFalse(result["manual_observation_completed"])
        self.assertGreater(len(result["manual_observation_required"]), 0)

    def test_existing_result_directory_blocks_any_rerun_before_network(self) -> None:
        self.result_dir.mkdir()
        requester = ScriptedRequester({})
        with mock.patch.object(
            runner, "validate_candidate_directory"
        ) as validator, mock.patch.object(runner, "perform_refresh") as refresh:
            with self.assertRaisesRegex(runner.ExperimentalRefreshError, "already exists"):
                runner.run_experimental_refresh(
                    self.candidate,
                    self.result_dir,
                    "http://device",
                    authorized_manifest_sha256=self.authorization,
                    confirm_experimental_uncalibrated=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                )
        validator.assert_not_called()
        refresh.assert_not_called()
        self.assertEqual(requester.calls, [])

    def test_same_authorized_manifest_cannot_post_again_with_new_result_directory(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        result_a = self.root / "result-a"
        result_b = self.root / "result-b"

        first = self._run(requester, result_dir=result_a)
        self.assertEqual(first["outcome"], "protocol_verified_manual_observation_required")
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        calls_after_first = list(requester.calls)

        with self.assertRaisesRegex(
            runner.ExperimentalRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=result_b)

        self.assertEqual(requester.calls, calls_after_first)
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertFalse(result_b.exists())
        self.assertEqual(
            [path.name for path in self.authorization_registry.iterdir()],
            [self.authorization],
        )

    def test_claim_survives_local_failure_before_attempt_directory_is_created(self) -> None:
        requester = ScriptedRequester({})
        result_a = self.root / "local-failure-a"
        result_b = self.root / "local-failure-b"

        with mock.patch.object(
            runner,
            "_create_result_directory",
            side_effect=runner.ExperimentalRefreshError("simulated local failure"),
        ):
            with self.assertRaisesRegex(
                runner.ExperimentalRefreshError, "simulated local failure"
            ):
                self._run(requester, result_dir=result_a)

        self.assertEqual(requester.calls, [])
        self.assertFalse(result_a.exists())
        claim = json.loads(
            (self.authorization_registry / self.authorization).read_text("utf-8")
        )
        self.assertEqual(claim["result_directory"], str(result_a.resolve()))

        with self.assertRaisesRegex(
            runner.ExperimentalRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=result_b)
        self.assertEqual(requester.calls, [])
        self.assertFalse(result_b.exists())

    def test_network_exception_keeps_lock_records_unknown_and_never_retries(self) -> None:
        responses = valid_refresh_responses(self.frame)
        responses["/api/frame"] = [OSError("simulated transport loss")]
        requester = ScriptedRequester(responses)

        with self.assertRaises(runner.ExperimentalRefreshUnknown):
            self._run(requester)

        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertIs(recorded["formal"], False)
        self.assertIs(recorded["hardware_qualified"], False)
        self.assertIs(recorded["hardware_tested"], False)
        self.assertIs(recorded["automatic_retry_authorized"], False)
        lock = json.loads((self.result_dir / runner.LOCK_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["authorization_claim"], lock["authorization_claim"])

        calls_before = list(requester.calls)
        retry_result = self.root / "result-after-unknown"
        with self.assertRaisesRegex(
            runner.ExperimentalRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=retry_result)
        self.assertEqual(requester.calls, calls_before)
        self.assertFalse(retry_result.exists())


if __name__ == "__main__":
    unittest.main()
