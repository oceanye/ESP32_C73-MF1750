from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.epd_frame import (
    FRAME_BYTES,
    controller_stream,
    fnv1a,
    generate_fixture,
)
from tests.test_frame_tool import ScriptedRequester, valid_refresh_responses
from tools import g1_s1_low_spatial_diagnostic_refresh_once as runner


class LowSpatialDiagnosticRefreshOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.production_manifest_sha256 = runner.EXPECTED_MANIFEST_SHA256
        self.production_frame_identity = (
            runner.EXPECTED_FRAME_SHA256,
            runner.EXPECTED_FRAME_FNV1A,
            runner.EXPECTED_CS1_DTM_SHA256,
            runner.EXPECTED_CS1_DTM_FNV1A,
            runner.EXPECTED_CS2_DTM_SHA256,
            runner.EXPECTED_CS2_DTM_FNV1A,
        )
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "diagnostic"
        self.bundle.mkdir()
        self.result_dir = self.root / "result"
        self.registry = self.root / "authorization-registry"
        self.registry.mkdir()

        self.frame = generate_fixture("global-h-bars")
        self.frame_sha256 = hashlib.sha256(self.frame).hexdigest()
        self.frame_fnv1a = fnv1a(self.frame)
        self.controller_streams = tuple(
            controller_stream(self.frame, mapping)
            for mapping in runner.FIXED_CONTROLLER_MAPPINGS
        )
        self.controller_sha256s = tuple(
            hashlib.sha256(stream).hexdigest() for stream in self.controller_streams
        )
        self.controller_fnv1as = tuple(fnv1a(stream) for stream in self.controller_streams)

        identity_values = {
            "EXPECTED_FRAME_SHA256": self.frame_sha256,
            "EXPECTED_FRAME_FNV1A": self.frame_fnv1a,
            "EXPECTED_CS1_DTM_SHA256": self.controller_sha256s[0],
            "EXPECTED_CS1_DTM_FNV1A": self.controller_fnv1as[0],
            "EXPECTED_CS2_DTM_SHA256": self.controller_sha256s[1],
            "EXPECTED_CS2_DTM_FNV1A": self.controller_fnv1as[1],
        }
        for name, value in identity_values.items():
            patcher = mock.patch.object(runner, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        (self.bundle / "frame.bin").write_bytes(self.frame)
        for name in ("strict-final.png", "transition-map.png", "model.png"):
            (self.bundle / name).write_bytes(f"test-{name}".encode("ascii"))
        self.manifest = self._manifest()
        self.manifest_bytes = runner._canonical_json(self.manifest)
        (self.bundle / "manifest.json").write_bytes(self.manifest_bytes)
        self.manifest_sha256 = hashlib.sha256(self.manifest_bytes).hexdigest()
        manifest_patcher = mock.patch.object(
            runner, "EXPECTED_MANIFEST_SHA256", self.manifest_sha256
        )
        manifest_patcher.start()
        self.addCleanup(manifest_patcher.stop)

    def _manifest(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "mf1750-g1-s1-low-spatial-diagnostic-test",
            "classification": {
                "experimental": True,
                "formal": False,
                "hardware_qualified": False,
                "hardware_tested": False,
                "simulation_only": True,
                "upload_authorized": False,
            },
            "transport": {
                "mode": "offline",
                "device_io_performed": False,
                "network_io_performed": False,
                "ingress_performed": False,
                "endpoint": None,
                "method": None,
                "upload_authorized": False,
            },
            "prior_state": {"frame": dict(runner.EXPECTED_MAP_PRIOR)},
            "diagnostic": {
                "frame": {
                    "file": "frame.bin",
                    "bytes": FRAME_BYTES,
                    "sha256": self.frame_sha256,
                    "fnv1a": f"0x{self.frame_fnv1a:08X}",
                    "codes_sha256": "1" * 64,
                },
                "controllers": runner._controller_records(),
            },
            "previews": {
                name: {
                    "file": name,
                    "bytes": len((self.bundle / name).read_bytes()),
                    "sha256": hashlib.sha256((self.bundle / name).read_bytes()).hexdigest(),
                }
                for name in ("strict-final.png", "transition-map.png", "model.png")
            },
        }

    def _patch_offline_dependencies(self):
        return (
            mock.patch.object(
                runner,
                "_deep_validate_diagnostic_directory",
                return_value=self.manifest,
            ),
            mock.patch.object(
                runner, "_authorization_registry", return_value=self.registry
            ),
        )

    def _run(self, requester, *, result_dir: Path | None = None, **overrides):
        arguments = {
            "confirm_map_prior_unchanged": True,
            "confirm_j2_powered_supervised": True,
            "confirm_cold_start": True,
            "confirm_single_post_authorized": True,
            "sleeper": lambda _seconds: None,
        }
        arguments.update(overrides)
        real_perform_refresh = runner.perform_refresh

        def scripted_refresh(*args, **kwargs):
            return real_perform_refresh(*args, requester=requester, **kwargs)

        validator_patch, registry_patch = self._patch_offline_dependencies()
        with validator_patch, registry_patch, mock.patch.object(
            runner, "perform_refresh", side_effect=scripted_refresh
        ):
            return runner.run_low_spatial_diagnostic_refresh_once(
                self.bundle,
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                **arguments,
            )

    def test_production_frame_and_prior_identities_are_frozen(self) -> None:
        self.assertEqual(
            self.production_frame_identity,
            (
                "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65",
                0xA9641618,
                "c85a03621501c8bb0c535467a1581ab451f5bb0fc50fc4227c31e576d23d6070",
                0xCB085C03,
                "bf25594c886c2046512eecf24795f8c2a5dacf1d9c565501658a6e6ea9889bd7",
                0x9ABD749A,
            ),
        )
        self.assertEqual(runner.EXPECTED_MAP_PRIOR["fixture"], "map-orient-v1")
        self.assertEqual(runner.EXPECTED_MAP_PRIOR["fnv1a"], "0x9D04142D")
        self.assertEqual(runner.EXPECTED_BUILD_TAG.count("RC2F"), 1)
        self.assertEqual(runner.EXPECTED_DRIVER_API, "MF1750_R16_CASCADE_V3")
        self.assertEqual(runner.EXPECTED_REFRESH_SPI_HZ, 1_000_000)
        self.assertEqual(
            self.production_manifest_sha256,
            "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d",
        )

    def test_runner_is_not_parameterized_with_requester_registry_or_manifest_hash(self) -> None:
        parameters = inspect.signature(
            runner.run_low_spatial_diagnostic_refresh_once
        ).parameters
        self.assertNotIn("requester", parameters)
        self.assertNotIn("authorization_registry", parameters)
        self.assertNotIn("authorized_manifest_sha256", parameters)
        source = inspect.getsource(runner)
        self.assertIn("validate_diagnostic_directory", source)
        self.assertNotIn("g1_s1_panel_candidate", source)
        self.assertNotIn("run_experimental_refresh", source)

    def test_real_generator_deep_validator_and_frozen_schema_interoperate(self) -> None:
        from tools.g1_s1_low_spatial_diagnostic import write_diagnostic_directory

        production = self.production_frame_identity
        real_bundle = self.root / "real-diagnostic"
        with mock.patch.multiple(
            runner,
            EXPECTED_MANIFEST_SHA256=(
                "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d"
            ),
            EXPECTED_FRAME_SHA256=production[0],
            EXPECTED_FRAME_FNV1A=production[1],
            EXPECTED_CS1_DTM_SHA256=production[2],
            EXPECTED_CS1_DTM_FNV1A=production[3],
            EXPECTED_CS2_DTM_SHA256=production[4],
            EXPECTED_CS2_DTM_FNV1A=production[5],
        ):
            manifest = write_diagnostic_directory(real_bundle)
            snapshot = runner._load_diagnostic_snapshot(
                real_bundle, runner._frozen_manifest_sha256()
            )

        self.assertEqual(snapshot.manifest, manifest)
        self.assertEqual(
            snapshot.manifest_file_sha256,
            "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d",
        )
        self.assertEqual(hashlib.sha256(snapshot.frame).hexdigest(), production[0])
        self.assertEqual(set(path.name for path in real_bundle.iterdir()), runner.REQUIRED_DIAGNOSTIC_FILES)

    def test_invalid_frozen_manifest_constant_fails_before_validator_claim_or_network(self) -> None:
        with mock.patch.object(
            runner, "EXPECTED_MANIFEST_SHA256", "PENDING"
        ), mock.patch.object(
            runner, "_deep_validate_diagnostic_directory"
        ) as validator, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(runner, "perform_refresh") as refresh:
            with self.assertRaisesRegex(
                runner.LowSpatialDiagnosticRefreshError, "64 hexadecimal"
            ):
                runner.run_low_spatial_diagnostic_refresh_once(
                    self.bundle,
                    self.result_dir,
                    "http://device",
                    confirm_map_prior_unchanged=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                    confirm_single_post_authorized=True,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        refresh.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_deep_validator_failure_makes_zero_claim_result_or_network(self) -> None:
        with mock.patch.object(
            runner,
            "_deep_validate_diagnostic_directory",
            side_effect=runner.LowSpatialDiagnosticRefreshError("deep reject"),
        ) as validator, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(runner, "perform_refresh") as refresh:
            with self.assertRaisesRegex(
                runner.LowSpatialDiagnosticRefreshError, "deep reject"
            ):
                runner.run_low_spatial_diagnostic_refresh_once(
                    self.bundle,
                    self.result_dir,
                    "http://device",
                    confirm_map_prior_unchanged=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                    confirm_single_post_authorized=True,
                )
        validator.assert_called_once_with(self.bundle)
        registry.assert_not_called()
        refresh.assert_not_called()
        self.assertEqual(list(self.registry.iterdir()), [])
        self.assertFalse(self.result_dir.exists())

    def test_tampered_frame_fails_before_claim_or_network(self) -> None:
        original = (self.bundle / "frame.bin").read_bytes()
        (self.bundle / "frame.bin").write_bytes(b"\x00" + original[1:])
        validator_patch, registry_patch = self._patch_offline_dependencies()
        with validator_patch, registry_patch as registry, mock.patch.object(
            runner, "perform_refresh"
        ) as refresh:
            with self.assertRaises(runner.LowSpatialDiagnosticRefreshError):
                runner.run_low_spatial_diagnostic_refresh_once(
                    self.bundle,
                    self.result_dir,
                    "http://device",
                    confirm_map_prior_unchanged=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                    confirm_single_post_authorized=True,
                )
        registry.assert_not_called()
        refresh.assert_not_called()
        self.assertEqual(list(self.registry.iterdir()), [])
        self.assertFalse(self.result_dir.exists())

    def test_success_claims_before_result_and_posts_api_frame_once(self) -> None:
        scripted = ScriptedRequester(valid_refresh_responses(self.frame))
        real_create = runner._create_result_directory

        def checked_create(destination, snapshot, claim):
            self.assertTrue((self.registry / self.manifest_sha256).is_file())
            self.assertFalse(destination.exists())
            return real_create(destination, snapshot, claim)

        def requester(*args, **kwargs):
            self.assertTrue((self.registry / self.manifest_sha256).is_file())
            self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
            return scripted(*args, **kwargs)

        with mock.patch.object(
            runner, "_create_result_directory", side_effect=checked_create
        ):
            result = self._run(requester)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        claim_path = self.registry / self.manifest_sha256
        claim = json.loads(claim_path.read_text("utf-8"))
        lock = json.loads((self.result_dir / runner.LOCK_FILENAME).read_text("utf-8"))
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(claim["kind"], runner.CLAIM_KIND)
        self.assertEqual(claim["manifest_file_sha256"], self.manifest_sha256)
        self.assertEqual(claim["exact_action"], runner.EXACT_ACTION)
        self.assertIs(claim["automatic_recovery_authorized"], False)
        self.assertEqual(
            claim["state"], "authorization_permanently_consumed_do_not_rerun"
        )
        self.assertEqual(lock["authorization_claim"], result["authorization_claim"])
        self.assertEqual(recorded, result)
        self.assertEqual(
            result["outcome"], "protocol_verified_manual_observation_required"
        )
        self.assertIs(result["protocol_verified"], True)
        self.assertIs(result["formal"], False)
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["hardware_tested"], False)
        self.assertIs(result["algorithm_qualification"], False)
        self.assertFalse(result["manual_observation_completed"])

    def test_same_manifest_cannot_post_with_a_different_result_directory(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        first_dir = self.root / "first"
        second_dir = self.root / "second"
        first = self._run(requester, result_dir=first_dir)
        self.assertEqual(
            first["outcome"], "protocol_verified_manual_observation_required"
        )
        calls_after_first = list(requester.calls)

        with self.assertRaisesRegex(
            runner.LowSpatialDiagnosticRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=second_dir)

        self.assertEqual(requester.calls, calls_after_first)
        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertFalse(second_dir.exists())
        self.assertEqual(
            [path.name for path in self.registry.iterdir()], [self.manifest_sha256]
        )

    def test_post_claim_local_failure_is_unknown_and_claim_stays_consumed(self) -> None:
        requester = ScriptedRequester({})
        first_dir = self.root / "local-failure"
        second_dir = self.root / "after-local-failure"
        with mock.patch.object(
            runner,
            "_create_result_directory",
            side_effect=OSError("simulated create failure"),
        ):
            with self.assertRaises(runner.LowSpatialDiagnosticRefreshUnknown):
                self._run(requester, result_dir=first_dir)

        self.assertTrue((self.registry / self.manifest_sha256).is_file())
        self.assertFalse(first_dir.exists())
        self.assertEqual(requester.calls, [])
        with self.assertRaisesRegex(
            runner.LowSpatialDiagnosticRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=second_dir)
        self.assertFalse(second_dir.exists())
        self.assertEqual(requester.calls, [])

    def test_network_exception_records_unknown_and_never_posts_again(self) -> None:
        responses = valid_refresh_responses(self.frame)
        responses["/api/frame"] = [OSError("simulated transport loss")]
        requester = ScriptedRequester(responses)

        with self.assertRaises(runner.LowSpatialDiagnosticRefreshUnknown):
            self._run(requester)

        self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(
            [call for call in requester.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        result = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(result["outcome"], "unknown_do_not_retry")
        self.assertIs(result["protocol_verified"], None)
        self.assertIs(result["automatic_retry_authorized"], False)
        self.assertIs(result["automatic_recovery_authorized"], False)

        calls_before_retry = list(requester.calls)
        with self.assertRaisesRegex(
            runner.LowSpatialDiagnosticRefreshError, "already permanently consumed"
        ):
            self._run(requester, result_dir=self.root / "retry")
        self.assertEqual(requester.calls, calls_before_retry)

    def test_wrong_build_is_post_claim_unknown_and_performs_no_frame_post(self) -> None:
        responses = valid_refresh_responses(self.frame)
        status, version = responses["/api/version"][0]
        responses["/api/version"] = [(status, version.replace("RC2F", "RC2X"))]
        requester = ScriptedRequester(responses)

        with self.assertRaises(runner.LowSpatialDiagnosticRefreshUnknown):
            self._run(requester)

        self.assertEqual(requester.calls, [("GET", "/api/version")])
        self.assertTrue((self.registry / self.manifest_sha256).is_file())
        result = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(result["outcome"], "unknown_do_not_retry")

    def test_runner_rechecks_all_frozen_network_report_identities(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        report = runner.perform_refresh(
            "http://device",
            self.frame,
            expected_mappings=runner.FIXED_CONTROLLER_MAPPINGS,
            requester=requester,
            sleeper=lambda _seconds: None,
        )
        mutations = {
            "build": lambda value: value["preflight"].__setitem__("build_tag", "wrong"),
            "api": lambda value: value["preflight"].__setitem__("driver_api", "wrong"),
            "dimensions": lambda value: value["preflight"].__setitem__("panel", "1x1"),
            "frame-bytes": lambda value: value["preflight"].__setitem__("frame_bytes", 1),
            "spi": lambda value: value["preflight"].__setitem__("refresh_spi_hz", 100_000),
            "mapping": lambda value: value["preflight"]["controller_mappings"][0][
                "mapping"
            ].__setitem__("flip_x", True),
            "job-frame": lambda value: value["job"].__setitem__("frame_fnv1a", 0),
            "operation": lambda value: value["diagnostic"].__setitem__("operation_id", 0),
            "dtm": lambda value: value["diagnostic"]["physical_controllers"][0].__setitem__(
                "dtm_fnv1a", 0
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(report)
                mutate(changed)
                with self.assertRaises(runner.LowSpatialDiagnosticRefreshError):
                    runner._validate_network_report(changed)

    def test_missing_confirmation_is_preclaim_and_zero_network(self) -> None:
        with mock.patch.object(
            runner, "_deep_validate_diagnostic_directory"
        ) as validator, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(runner, "perform_refresh") as refresh:
            with self.assertRaisesRegex(
                runner.LowSpatialDiagnosticRefreshError, "four explicit"
            ):
                runner.run_low_spatial_diagnostic_refresh_once(
                    self.bundle,
                    self.result_dir,
                    "http://device",
                    confirm_map_prior_unchanged=True,
                    confirm_j2_powered_supervised=True,
                    confirm_cold_start=True,
                    confirm_single_post_authorized=False,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        refresh.assert_not_called()
        self.assertEqual(list(self.registry.iterdir()), [])
        self.assertFalse(self.result_dir.exists())


if __name__ == "__main__":
    unittest.main()
