from __future__ import annotations

import hashlib
import io
import json
import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.application.simulation import SimulationAlgorithm
from host.epd_frame import FRAME_BYTES, HEIGHT, WIDTH, fnv1a, generate_fixture
from tools import g1_s1_panel_candidate as tool


class _FakeResult:
    def __init__(self) -> None:
        self.frame = generate_fixture("global-h-bars")
        self.codes = b"codes"
        self.previews = {
            "source": b"source-png",
            "mapped": b"mapped-png",
            "final": b"final-png",
            "model": b"model-png",
        }
        self.report = {
            "mapping": {
                "mapped_rgb8_sha256": "1" * 64,
                "report_canonical_sha256": "2" * 64,
            },
            "report_integrity": {"canonical_sha256": "3" * 64},
        }

    def validated_snapshot(self):
        return self


class CandidateGenerationTests(unittest.TestCase):
    def test_source_is_deterministic_panel_mix_gradient_edge_pattern(self) -> None:
        first = tool.generate_test_image()
        second = tool.generate_test_image()
        self.assertEqual((first.width, first.height, first.mode), (WIDTH, HEIGHT, "RGB"))
        self.assertEqual(first.pixels, second.pixels)
        self.assertEqual(len(first.pixels), WIDTH * HEIGHT * 3)
        self.assertEqual(
            hashlib.sha256(first.pixels).hexdigest(),
            "d21d164ffee9e8a65395662804b53d20cf22d3092471be160513e3c4316b8c5b",
        )
        self.assertNotEqual(first.pixels[0:3], first.pixels[(300 * WIDTH + 512) * 3 : (300 * WIDTH + 512) * 3 + 3])
        self.assertNotEqual(first.pixels[(400 * WIDTH + 510) * 3 : (400 * WIDTH + 510) * 3 + 3], first.pixels[(400 * WIDTH + 511) * 3 : (400 * WIDTH + 511) * 3 + 3])

    def test_allowlist_is_exact_and_other_algorithms_fail_closed(self) -> None:
        self.assertEqual(
            {item.value for item in tool.ALLOWED_ALGORITHMS},
            {
                "atkinson",
                "area-weighted-ordered-8x8",
                "area-weighted-blue-noise",
                "multicolor-dbs",
                "overlap-aware-dbs",
            },
        )
        with self.assertRaisesRegex(tool.CandidateError, "allowlist"):
            tool._normalize_algorithm(SimulationAlgorithm.FLOYD_STEINBERG)

    def test_build_calls_panel_simulator_and_is_offline_by_default(self) -> None:
        fake = _FakeResult()
        with mock.patch.object(tool, "simulate_panel", return_value=fake) as simulator:
            manifest, result = tool.build_candidate("atkinson", seed=7)
        self.assertIs(result, fake)
        source = simulator.call_args.args[0]
        self.assertEqual((source.width, source.height), (WIDTH, HEIGHT))
        options = simulator.call_args.kwargs["options"]
        self.assertEqual(options.algorithm, SimulationAlgorithm.ATKINSON)
        self.assertEqual(options.seed, 7)
        self.assertEqual(manifest["classification"]["experimental"], True)
        self.assertEqual(manifest["classification"]["uncalibrated"], True)
        self.assertEqual(manifest["classification"]["formal"], False)
        self.assertEqual(manifest["classification"]["hardware_tested"], False)
        self.assertEqual(manifest["transport"]["mode"], "offline")
        self.assertFalse(manifest["transport"]["device_io_performed"])
        unsigned = dict(manifest)
        del unsigned["manifest_integrity"]
        self.assertEqual(
            manifest["manifest_integrity"]["canonical_sha256"],
            hashlib.sha256(tool._canonical_json(unsigned)).hexdigest(),
        )


class CandidateIngressTests(unittest.TestCase):
    def test_optional_network_surface_posts_only_to_ingress(self) -> None:
        frame = generate_fixture("global-h-bars")
        calls = []

        def requester(base_url, endpoint, *, method, data, timeout):
            calls.append((base_url, endpoint, method, data, timeout))
            return 200, json.dumps(
                {
                    "ok": True,
                    "bytes": FRAME_BYTES,
                    "fnv1a": fnv1a(frame),
                    "free_psram": 7_800_000,
                    "epd_action": "none",
                }
            )

        report = tool.perform_ingress("http://192.0.2.10/", frame, requester=requester)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:3], (tool.INGRESS_ENDPOINT, "POST"))
        self.assertEqual(calls[0][3], frame)
        self.assertEqual(report["mode"], "ingress-only")
        self.assertEqual(report["epd_action"], "none")
        self.assertFalse(report["hardware_tested"])

    def test_ingress_rejects_any_display_action_claim(self) -> None:
        frame = generate_fixture("global-h-bars")

        def requester(_base_url, _endpoint, **_kwargs):
            return 200, json.dumps(
                {
                    "ok": True,
                    "bytes": FRAME_BYTES,
                    "fnv1a": fnv1a(frame),
                    "free_psram": 7_800_000,
                    "epd_action": "unexpected",
                }
            )

        with self.assertRaisesRegex(tool.CandidateError, "epd_action"):
            tool.perform_ingress("http://192.0.2.10", frame, requester=requester)


class CandidateBundleTests(unittest.TestCase):
    def _fake_manifest(self, result: _FakeResult) -> dict:
        source = tool.generate_test_image()
        options = {
            "algorithm": "atkinson",
            "mapping": {"mode": "gamut-map", "intent": "perceptual", "strength": 1.0, "cache_entries": 65536},
            "seed": tool.DEFAULT_SEED,
            "budget": None,
            "white_protection": True,
            "preserve_edges": True,
            "text_mode": False,
            "area_weight_lut_bits": 4,
        }
        manifest = {
            "schema_version": tool.MANIFEST_SCHEMA_VERSION,
            "kind": tool.MANIFEST_KIND,
            "classification": {"experimental": True, "uncalibrated": True, "formal": False, "hardware_tested": False, "upload_authorized": False},
            "source": {"pattern_id": tool.SOURCE_PATTERN_ID, "width": WIDTH, "height": HEIGHT, "mode": "RGB", "pixels_bytes": len(source.pixels), "pixels_sha256": hashlib.sha256(source.pixels).hexdigest()},
            "mapped": {"rgb8_sha256": "1" * 64, "mapping_report_sha256": "2" * 64},
            "frame": {"file": "frame.bin", "encoding": "canonical-row-major-two-4bit-codes-per-byte", "bytes": len(result.frame), "sha256": hashlib.sha256(result.frame).hexdigest(), "fnv1a": f"0x{fnv1a(result.frame):08X}", "codes_sha256": hashlib.sha256(tool.unpack_pixels(result.frame, WIDTH, HEIGHT)).hexdigest()},
            "controllers": tool._controller_records(result.frame),
            "profile": {"profile_id": "p", "canonical_sha256": "4" * 64, "characterization_level": "reference", "model_kind": "m", "palette_id": "palette", "palette_canonical_sha256": "5" * 64},
            "options": {"value": options, "canonical_sha256": hashlib.sha256(tool._canonical_json(options)).hexdigest()},
            "previews": {stage: {"file": tool.PREVIEW_FILES[stage], "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()} for stage, payload in result.previews.items()},
            "simulation": {"report_canonical_sha256": "3" * 64, "report_hash_scope": tool.SIMULATION_REPORT_HASH_SCOPE, "report": result.report},
            "transport": {"mode": "offline", "endpoint": None, "method": None, "device_io_performed": False, "hardware_tested": False},
        }
        manifest["manifest_integrity"] = {"canonical_sha256": hashlib.sha256(tool._canonical_json(manifest)).hexdigest(), "canonical_sha256_scope": tool.MANIFEST_HASH_SCOPE}
        return manifest

    def test_bundle_writes_fixed_files_canonically_and_refuses_existing_dir(self) -> None:
        result = _FakeResult()
        manifest = self._fake_manifest(result)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            tool.write_candidate_directory(output, manifest, result)  # type: ignore[arg-type]
            self.assertEqual({path.name for path in output.iterdir()}, tool.REQUIRED_FILES)
            self.assertEqual((output / "manifest.json").read_bytes(), tool._canonical_json(manifest))
            with self.assertRaisesRegex(tool.CandidateError, "already exists"):
                tool.write_candidate_directory(output, manifest, result)  # type: ignore[arg-type]

    def test_disk_validator_calls_deep_simulation_validator_and_detects_preview_tamper(self) -> None:
        result = _FakeResult()
        manifest = self._fake_manifest(result)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            tool.write_candidate_directory(output, manifest, result)  # type: ignore[arg-type]
            with mock.patch.object(tool, "validate_simulation_report") as deep_validator:
                with mock.patch.object(tool, "generate_test_image", return_value=tool.generate_test_image()):
                    # Stop after the required deep call; the fake nested report is intentionally incomplete.
                    deep_validator.side_effect = tool.CandidateError("deep-called")
                    with self.assertRaisesRegex(tool.CandidateError, "deep-called"):
                        tool.validate_candidate_directory(output)
                    deep_validator.assert_called_once()
            (output / "model.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(tool.CandidateError, "preview identities"):
                tool.validate_candidate_directory(output)

    def test_cli_requires_explicit_new_output_directory_and_has_no_force(self) -> None:
        with self.assertRaises(SystemExit):
            tool.parse_args([])
        with self.assertRaises(SystemExit):
            tool.parse_args(["--output-dir", "candidate", "--force"])

    def test_validator_rejects_directory_and_file_symlinks(self) -> None:
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlinks are unavailable")
        result = _FakeResult()
        manifest = self._fake_manifest(result)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "candidate"
            tool.write_candidate_directory(output, manifest, result)  # type: ignore[arg-type]
            alias = root / "candidate-alias"
            try:
                alias.symlink_to(output, target_is_directory=True)
            except OSError:
                self.skipTest("this account cannot create symlinks")
            with self.assertRaisesRegex(tool.CandidateError, "directory.*symlink"):
                tool.validate_candidate_directory(alias)
            alias.unlink()
            source = output / "source.png"
            original = output / "source-original.png"
            source.rename(original)
            source.symlink_to(original.name)
            with self.assertRaisesRegex(tool.CandidateError, "files.*symlinks"):
                tool.validate_candidate_directory(output)

    def test_validate_cli_freezes_before_optional_ingress(self) -> None:
        frame = generate_fixture("global-h-bars")
        manifest = {
            "manifest_integrity": {"canonical_sha256": "a" * 64},
            "frame": {
                "file": "frame.bin",
                "encoding": "canonical-row-major-two-4bit-codes-per-byte",
                "bytes": len(frame),
                "sha256": hashlib.sha256(frame).hexdigest(),
                "fnv1a": f"0x{fnv1a(frame):08X}",
                "codes_sha256": hashlib.sha256(
                    tool.unpack_pixels(frame, WIDTH, HEIGHT)
                ).hexdigest(),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "candidate"
            directory.mkdir()
            (directory / "frame.bin").write_bytes(frame)
            events = []

            def validate(path):
                events.append(("validate", path))
                return manifest

            def ingress(url, payload):
                events.append(("ingress", url, payload))
                return {"mode": "ingress-only", "hardware_tested": False}

            stdout = io.StringIO()
            with mock.patch.object(tool, "validate_candidate_directory", side_effect=validate), mock.patch.object(
                tool, "perform_ingress", side_effect=ingress
            ), mock.patch.object(tool, "build_candidate") as build, contextlib.redirect_stdout(stdout):
                status = tool.main(
                    ["--validate-dir", str(directory), "--url", "http://192.0.2.10"]
                )
            self.assertEqual(status, 0)
            self.assertEqual([event[0] for event in events], ["validate", "ingress"])
            self.assertEqual(events[1][2], frame)
            build.assert_not_called()
            rendered = json.loads(stdout.getvalue())
            self.assertFalse(rendered["classification"]["hardware_tested"])

    def test_validate_cli_rejects_post_validation_frame_swap_before_ingress(self) -> None:
        original = generate_fixture("global-h-bars")
        replacement = generate_fixture("global-v-bars")
        self.assertNotEqual(original, replacement)
        manifest = {
            "manifest_integrity": {"canonical_sha256": "a" * 64},
            "frame": {
                "file": "frame.bin",
                "encoding": "canonical-row-major-two-4bit-codes-per-byte",
                "bytes": len(original),
                "sha256": hashlib.sha256(original).hexdigest(),
                "fnv1a": f"0x{fnv1a(original):08X}",
                "codes_sha256": hashlib.sha256(
                    tool.unpack_pixels(original, WIDTH, HEIGHT)
                ).hexdigest(),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "candidate"
            directory.mkdir()
            frame_path = directory / "frame.bin"
            frame_path.write_bytes(original)

            def validate(_path):
                # Simulate a valid same-size frame being exchanged after deep validation.
                frame_path.write_bytes(replacement)
                return manifest

            stderr = io.StringIO()
            with mock.patch.object(
                tool, "validate_candidate_directory", side_effect=validate
            ), mock.patch.object(tool, "perform_ingress") as ingress, contextlib.redirect_stderr(
                stderr
            ):
                status = tool.main(
                    ["--validate-dir", str(directory), "--url", "http://192.0.2.10"]
                )
            self.assertEqual(status, 2)
            ingress.assert_not_called()
            self.assertIn("do not match the validated manifest", stderr.getvalue())

    def test_generation_cli_rejects_url_until_a_bundle_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            stderr = io.StringIO()
            with mock.patch.object(tool, "build_candidate") as build, contextlib.redirect_stderr(stderr):
                status = tool.main(
                    ["--output-dir", str(output), "--url", "http://192.0.2.10"]
                )
            self.assertEqual(status, 2)
            build.assert_not_called()
            self.assertIn("frozen first", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
