from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import g1_s1_low_spatial_diagnostic as diagnostic


class LowSpatialContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = diagnostic.build_diagnostic_artifacts()

    def test_frozen_matrix_constraints_and_objective(self) -> None:
        diagnostic.validate_frozen_contract()
        self.assertEqual(
            tuple(map(sum, diagnostic.GLOBAL_TRANSITION_MATRIX)),
            tuple(
                left + right
                for left, right in zip(
                    diagnostic.OLD_LEFT_CAPACITIES,
                    diagnostic.OLD_RIGHT_CAPACITIES,
                )
            ),
        )
        self.assertEqual(
            tuple(
                sum(diagnostic.GLOBAL_TRANSITION_MATRIX[row][column] for row in range(6))
                for column in range(6)
            ),
            diagnostic.TARGET_TOTAL_COUNTS,
        )
        self.assertEqual(diagnostic.split_objective(), 48_106_656)

    def test_odd_count_split_is_theoretical_minimum(self) -> None:
        differences = tuple(
            left - right
            for left, right in zip(
                diagnostic.TARGET_LEFT_COUNTS,
                diagnostic.TARGET_RIGHT_COUNTS,
            )
        )
        self.assertEqual(differences, (1, -1, 1, -1, 0, 0))
        self.assertLessEqual(max(map(abs, differences)), 1)
        self.assertEqual(
            tuple(total & 1 for total in diagnostic.TARGET_TOTAL_COUNTS),
            (1, 1, 1, 1, 0, 0),
        )

    def test_exact_code_frame_and_controller_identities(self) -> None:
        prior, codes = diagnostic.generate_diagnostic_codes()
        frame = self.artifacts.frame
        self.assertEqual(len(prior), 1024 * 600)
        self.assertEqual(hashlib.sha256(codes).hexdigest(), diagnostic.EXPECTED_CODES_SHA256)
        self.assertEqual(hashlib.sha256(frame).hexdigest(), diagnostic.EXPECTED_FRAME_SHA256)
        self.assertEqual(self.artifacts.manifest["diagnostic"]["frame"]["fnv1a"], "0xA9641618")
        controllers = self.artifacts.manifest["diagnostic"]["controllers"]
        self.assertEqual(controllers[0]["dtm_sha256"], diagnostic.EXPECTED_CS1_DTM_SHA256)
        self.assertEqual(controllers[0]["dtm_fnv1a"], "0xCB085C03")
        self.assertEqual(controllers[1]["dtm_sha256"], diagnostic.EXPECTED_CS2_DTM_SHA256)
        self.assertEqual(controllers[1]["dtm_fnv1a"], "0x9ABD749A")

    def test_counts_transitions_and_spatial_metrics_are_exact(self) -> None:
        manifest = self.artifacts.manifest
        counts = manifest["diagnostic"]["counts"]
        self.assertEqual(tuple(counts["total"]), diagnostic.TARGET_TOTAL_COUNTS)
        self.assertEqual(tuple(counts["left"]), diagnostic.TARGET_LEFT_COUNTS)
        self.assertEqual(tuple(counts["right"]), diagnostic.TARGET_RIGHT_COUNTS)
        transitions = manifest["diagnostic"]["transitions"]
        self.assertEqual(tuple(map(tuple, transitions["global"])), diagnostic.GLOBAL_TRANSITION_MATRIX)
        self.assertEqual(tuple(map(tuple, transitions["left"])), diagnostic.LEFT_TRANSITION_MATRIX)
        self.assertEqual(tuple(map(tuple, transitions["right"])), diagnostic.RIGHT_TRANSITION_MATRIX)
        spatial = manifest["diagnostic"]["spatial_metrics"]
        self.assertEqual(spatial["horizontal_internal"]["different"], 13_462)
        self.assertEqual(spatial["horizontal_full_including_seam"]["different"], 13_922)
        self.assertEqual(spatial["controller_seam"]["different"], 460)
        self.assertEqual(spatial["vertical"]["different"], 15_643)
        self.assertEqual(spatial["total_four_neighbour_edges"]["different"], 29_565)
        self.assertEqual(spatial["boundary_pixels"]["count"], 52_072)
        self.assertLess(spatial["horizontal_internal"]["ratio"], 0.05)
        self.assertLess(spatial["vertical"]["ratio"], 0.05)

    def test_manifest_is_explicitly_offline_and_nonqualified(self) -> None:
        manifest = self.artifacts.manifest
        self.assertEqual(
            manifest["classification"],
            {
                "experimental": True,
                "formal": False,
                "hardware_qualified": False,
                "hardware_tested": False,
                "simulation_only": True,
                "upload_authorized": False,
            },
        )
        self.assertEqual(
            manifest["transport"],
            {
                "mode": "offline",
                "device_io_performed": False,
                "network_io_performed": False,
                "ingress_performed": False,
                "endpoint": None,
                "method": None,
                "upload_authorized": False,
            },
        )
        limitations = " ".join(manifest["interpretation"]["limitations"])
        self.assertIn("cannot separate", limitations)
        self.assertIn("seam", limitations)

    def test_three_previews_are_png_and_transition_legend_has_36_classes(self) -> None:
        self.assertTrue(self.artifacts.strict_final_png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(self.artifacts.transition_map_png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(self.artifacts.model_png.startswith(b"\x89PNG\r\n\x1a\n"))
        legend = self.artifacts.manifest["previews"]["transition_map"]["legend"]
        self.assertEqual(len(legend), 36)
        self.assertEqual(len({tuple(record["rgb"]) for record in legend}), 36)

    def test_generation_is_byte_deterministic(self) -> None:
        repeated = diagnostic.build_diagnostic_artifacts()
        self.assertEqual(repeated.files(), self.artifacts.files())
        self.assertEqual(repeated.manifest, self.artifacts.manifest)


class LowSpatialBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = diagnostic.build_diagnostic_artifacts()

    def _write_bundle(self, parent: Path, name: str = "bundle") -> Path:
        destination = parent / name
        destination.mkdir()
        for filename, payload in self.artifacts.files().items():
            (destination / filename).write_bytes(payload)
        return destination

    def test_writer_and_deep_validator_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "generated"
            manifest = diagnostic.write_diagnostic_directory(destination)
            self.assertEqual(set(path.name for path in destination.iterdir()), diagnostic.REQUIRED_FILES)
            self.assertEqual(diagnostic.validate_diagnostic_directory(destination), manifest)

    def test_existing_output_is_rejected_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "existing"
            destination.mkdir()
            marker = destination / "owner.txt"
            marker.write_text("user", encoding="utf-8")
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "already exists"):
                diagnostic.write_diagnostic_directory(destination)
            self.assertEqual(marker.read_text(encoding="utf-8"), "user")

    def test_tampered_frame_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._write_bundle(Path(temporary))
            frame = bytearray((bundle / "frame.bin").read_bytes())
            frame[123] ^= 0x10
            (bundle / "frame.bin").write_bytes(frame)
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "frame.bin"):
                diagnostic.validate_diagnostic_directory(bundle)

    def test_tampered_preview_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._write_bundle(Path(temporary))
            preview = bytearray((bundle / "model.png").read_bytes())
            preview[-1] ^= 1
            (bundle / "model.png").write_bytes(preview)
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "model.png"):
                diagnostic.validate_diagnostic_directory(bundle)

    def test_tampered_canonical_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._write_bundle(Path(temporary))
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            manifest["classification"]["hardware_tested"] = True
            unsigned = dict(manifest)
            unsigned.pop("manifest_integrity")
            manifest["manifest_integrity"]["canonical_sha256"] = hashlib.sha256(
                diagnostic._canonical_json(unsigned)
            ).hexdigest()
            (bundle / "manifest.json").write_bytes(diagnostic._canonical_json(manifest))
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "deep regeneration"):
                diagnostic.validate_diagnostic_directory(bundle)

    def test_extra_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = self._write_bundle(Path(temporary))
            (bundle / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "file set"):
                diagnostic.validate_diagnostic_directory(bundle)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support unavailable")
    def test_symlinked_bundle_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._write_bundle(root)
            target = root / "external.bin"
            target.write_bytes((bundle / "frame.bin").read_bytes())
            (bundle / "frame.bin").unlink()
            try:
                os.symlink(target, bundle / "frame.bin")
            except OSError as error:
                self.skipTest(f"symlink creation not permitted: {error}")
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "symlink"):
                diagnostic.validate_diagnostic_directory(bundle)


class LowSpatialOfflineSurfaceTests(unittest.TestCase):
    def test_cli_has_only_mutually_exclusive_local_modes(self) -> None:
        parser = diagnostic._build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--output-dir", option_strings)
        self.assertIn("--validate-dir", option_strings)
        for forbidden in ("--url", "--requester", "--registry", "--frame", "--endpoint"):
            self.assertNotIn(forbidden, option_strings)
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--output-dir", "one", "--validate-dir", "two"])

    def test_module_imports_no_network_or_device_client(self) -> None:
        source_path = Path(diagnostic.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        forbidden_roots = {"urllib", "requests", "http", "socket", "ftplib", "telnetlib"}
        self.assertFalse({name.split(".", 1)[0] for name in imports} & forbidden_roots)
        self.assertNotIn("tools.mf1750_frame_tool", imports)
        self.assertNotIn("host.application.device", imports)


if __name__ == "__main__":
    unittest.main()
