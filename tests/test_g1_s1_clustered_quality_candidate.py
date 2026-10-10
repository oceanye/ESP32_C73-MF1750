from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock
import urllib.request

from host.epd_frame import unpack_pixels
from tools import g1_s1_clustered_quality_candidate as tool


EXPECTED_PRIOR_TO_CANDIDATE = [
    [108133, 58011, 15670, 28527, 20817, 15425],
    [98198, 11040, 6901, 8534, 8975, 10945],
    [4699, 16844, 6592, 8721, 6689, 6508],
    [3552, 40986, 6126, 6051, 5716, 4788],
    [13574, 10736, 7086, 8790, 6824, 7634],
    [19320, 5946, 6897, 6470, 5587, 7088],
]


class ClusteredQualityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.bundle = Path(cls.temporary.name) / "clustered"
        with mock.patch.object(
            tool.blue_noise,
            "validate_candidate_directory",
            wraps=tool.blue_noise.validate_candidate_directory,
        ) as base_validator, mock.patch.object(
            tool.low_spatial,
            "validate_diagnostic_directory",
            wraps=tool.low_spatial.validate_diagnostic_directory,
        ) as prior_validator:
            cls.manifest = tool.write_clustered_directory(cls.bundle)
            cls.base_validation_calls = base_validator.call_count
            cls.prior_validation_calls = prior_validator.call_count
        cls.frame = (cls.bundle / "frame.bin").read_bytes()
        cls.codes = unpack_pixels(cls.frame)
        cls.base_codes = unpack_pixels((tool.BASELINE_DIR / "frame.bin").read_bytes())
        cls.prior_codes = unpack_pixels((tool.PRIOR_DIR / "frame.bin").read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_generation_deep_validates_both_frozen_inputs(self) -> None:
        # write_clustered_directory builds once and then deeply regenerates once.
        self.assertGreaterEqual(self.base_validation_calls, 2)
        self.assertGreaterEqual(self.prior_validation_calls, 2)
        evidence = self.manifest["evidence"]
        self.assertEqual(
            evidence["baseline"]["manifest_canonical_sha256"],
            tool.BASELINE_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            evidence["true_screen_prior"]["frame_sha256"], tool.PRIOR_FRAME_SHA256
        )

    def test_fixed_output_identities_and_offline_classification(self) -> None:
        output = self.manifest["output"]
        self.assertEqual(output["frame"]["sha256"], tool.EXPECTED_FRAME_SHA256)
        self.assertEqual(output["frame"]["fnv1a"], tool.EXPECTED_FRAME_FNV1A)
        self.assertEqual(output["frame"]["codes_sha256"], tool.EXPECTED_CODES_SHA256)
        self.assertEqual(
            [controller["dtm_fnv1a"] for controller in output["controllers"]],
            ["0x8F6A1E39", "0xE220DBDB"],
        )
        self.assertEqual(
            [controller["dtm_sha256"] for controller in output["controllers"]],
            [
                "32b1d4fcfad0d2174bf29d4e7a5990ddbdd7add31b467740ba13854f69ae519c",
                "3ba18cac6685cf8963a9a94ea65c6ae95d2d30319f4d13b284a83dde87a91a6a",
            ],
        )
        self.assertEqual(
            self.manifest["classification"],
            {
                "experimental": True,
                "visual_risk_reduction_experiment": True,
                "simulation_only": True,
                "formal": False,
                "hardware_qualified": False,
                "hardware_tested": False,
                "upload_authorized": False,
            },
        )
        self.assertEqual(
            self.manifest["transport"],
            {
                "mode": "offline",
                "endpoint": None,
                "method": None,
                "device_io_performed": False,
                "network_io_performed": False,
                "refresh_runner_implemented": False,
                "hardware_tested": False,
                "upload_authorized": False,
            },
        )

    def test_hilbert_path_is_complete_continuous_and_fixed(self) -> None:
        path = tool.hilbert_path(tool.TILE_SIDE)
        self.assertEqual(len(path), tool.TILE_SIDE**2)
        self.assertEqual(len(set(path)), tool.TILE_SIDE**2)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (31, 0))
        self.assertTrue(
            all(
                abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
                for a, b in zip(path, path[1:])
            )
        )
        self.assertEqual(tool.CLUSTER_CODE_ORDER, (3, 2, 5, 6, 1, 0))

    def test_every_tile_and_prior_code_transition_histogram_is_preserved(self) -> None:
        self.assertEqual(
            tool._tile_histograms(self.codes, tool.TILE_SIDE),
            tool._tile_histograms(self.base_codes, tool.TILE_SIDE),
        )
        self.assertEqual(
            tool._tile_prior_transitions(
                self.prior_codes, self.codes, tool.TILE_SIDE
            ),
            tool._tile_prior_transitions(
                self.prior_codes, self.base_codes, tool.TILE_SIDE
            ),
        )
        records = self.manifest["algorithm"]["tile_histogram_records"]
        self.assertEqual(len(records), 32 * 19)
        self.assertEqual(records[-1]["height"], 24)

    def test_global_half_counts_and_prior_transition_are_exactly_preserved(self) -> None:
        counts = self.manifest["output"]["counts"]
        self.assertEqual(counts["global"], [247476, 143563, 49272, 67093, 54608, 52388])
        self.assertEqual(counts["left"], [134698, 78510, 44494, 43216, 2479, 3803])
        self.assertEqual(counts["right"], [112778, 65053, 4778, 23877, 52129, 48585])
        transition = self.manifest["output"]["transition_from_true_screen_prior"]
        baseline_transition = tool._transition_record(self.prior_codes, self.base_codes)
        self.assertEqual(transition["global"], EXPECTED_PRIOR_TO_CANDIDATE)
        self.assertEqual(transition["global"], baseline_transition["global"])
        self.assertEqual(transition["left"], baseline_transition["left"])
        self.assertEqual(transition["right"], baseline_transition["right"])
        self.assertEqual(transition["changed_pixels"], 468672)
        self.assertEqual(transition["unchanged_pixels"], 145728)
        self.assertEqual(transition["changed_ratio"], 468672 / 614400)
        self.assertIn(
            "The candidate exactly preserves the blue-noise baseline's global, logical-half, and per-tile-by-prior-code transition counts from the fixed current prior, while rearranging transition locations and spatial frequency.",
            self.manifest["limitations"],
        )
        self.assertIn(
            "Per-tile histograms and fixed-prior transition counts are preserved, but source pixel positions, edges, and text semantics inside each tile are rearranged.",
            self.manifest["limitations"],
        )
        self.assertIn(
            "Relative to the failed ordered reference, other variables remain different; one display result cannot isolate every causal factor.",
            self.manifest["limitations"],
        )
        self.assertFalse(
            any(
                "changes spatial frequency, half-screen transitions" in limitation
                or limitation.startswith("Only each tile histogram is preserved")
                for limitation in self.manifest["limitations"]
            )
        )

    def test_spatial_metrics_and_16px_counterfactual_are_frozen(self) -> None:
        metrics = self.manifest["output"]["spatial_metrics"]
        self.assertEqual(metrics["horizontal_internal"]["count"], 33530)
        self.assertEqual(metrics["controller_seam"]["count"], 394)
        self.assertEqual(metrics["vertical"]["count"], 27996)
        self.assertEqual(metrics["total_edges"]["count"], 61920)
        self.assertEqual(metrics["boundary_pixels"]["count"], 107470)
        counterfactual = self.manifest["comparisons"]["tile16_counterfactual_only"]
        self.assertFalse(counterfactual["generated_as_hardware_candidate"])
        self.assertEqual(
            counterfactual["spatial_metrics"]["total_edges"]["count"], 102363
        )
        self.assertGreater(
            counterfactual["spatial_metrics"]["total_edges"]["count"],
            metrics["total_edges"]["count"],
        )

    def test_previews_are_rebuilt_and_source_semantics_are_byte_identical(self) -> None:
        self.assertEqual(
            (self.bundle / "source.png").read_bytes(),
            (tool.BASELINE_DIR / "source.png").read_bytes(),
        )
        self.assertEqual(
            (self.bundle / "mapped.png").read_bytes(),
            (tool.BASELINE_DIR / "mapped.png").read_bytes(),
        )
        self.assertEqual(
            hashlib.sha256((self.bundle / "strict-final.png").read_bytes()).hexdigest(),
            "fa4002d3f25dff4a9b7344aef8660b39efbaef70e93e61fb0ccdabe5b277cc87",
        )
        self.assertEqual(
            hashlib.sha256((self.bundle / "model.png").read_bytes()).hexdigest(),
            "bec70ad1ec3be307295bf9b26f94c26bfb80dfabee733d6debf88d5807449456",
        )

    def test_manifest_is_canonical_and_file_set_is_exact(self) -> None:
        self.assertEqual(
            {path.name for path in self.bundle.iterdir()}, tool.REQUIRED_FILES
        )
        raw = (self.bundle / "manifest.json").read_bytes()
        self.assertEqual(raw, tool._canonical_json(json.loads(raw)))
        unsigned = dict(self.manifest)
        del unsigned["manifest_integrity"]
        self.assertEqual(
            self.manifest["manifest_integrity"]["canonical_sha256"],
            hashlib.sha256(tool._canonical_json(unsigned)).hexdigest(),
        )


class ClusteredQualitySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.artifacts = tool.build_clustered_artifacts()
        cls.bundle = cls.root / "original"
        cls.bundle.mkdir()
        for name, payload in cls.artifacts.files().items():
            (cls.bundle / name).write_bytes(payload)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_deep_validator_rejects_resigned_manifest_tamper(self) -> None:
        tampered = self.root / "resigned-tamper"
        shutil.copytree(self.bundle, tampered)
        manifest = json.loads((tampered / "manifest.json").read_bytes())
        manifest["limitations"][0] = "tampered"
        unsigned = dict(manifest)
        del unsigned["manifest_integrity"]
        manifest["manifest_integrity"] = {
            "canonical_sha256": hashlib.sha256(tool._canonical_json(unsigned)).hexdigest(),
            "canonical_sha256_scope": tool.MANIFEST_HASH_SCOPE,
        }
        (tampered / "manifest.json").write_bytes(tool._canonical_json(manifest))
        with self.assertRaisesRegex(tool.ClusteredCandidateError, "deep regeneration"):
            tool.validate_clustered_directory(tampered)

    def test_rejects_extra_file_and_existing_output(self) -> None:
        extra = self.root / "extra"
        shutil.copytree(self.bundle, extra)
        (extra / "unexpected.txt").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(tool.ClusteredCandidateError, "file set"):
            tool.validate_clustered_directory(extra)
        with self.assertRaisesRegex(tool.ClusteredCandidateError, "already exists"):
            tool.write_clustered_directory(self.bundle)

    def test_rejects_file_and_directory_symlinks(self) -> None:
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlinks unavailable")
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.bundle, target_is_directory=True)
        except OSError:
            self.skipTest("this account cannot create symlinks")
        with self.assertRaisesRegex(tool.ClusteredCandidateError, "symlink"):
            tool.validate_clustered_directory(alias)
        alias.unlink()
        linked = self.root / "linked-file"
        shutil.copytree(self.bundle, linked)
        source = linked / "source.png"
        saved = linked / "saved-source.png"
        source.rename(saved)
        source.symlink_to(saved.name)
        with self.assertRaisesRegex(tool.ClusteredCandidateError, "symlink"):
            tool.validate_clustered_directory(linked)

    def test_cli_exposes_only_generation_and_validation_paths(self) -> None:
        with self.assertRaises(SystemExit):
            tool.parse_args([])
        with self.assertRaises(SystemExit):
            tool.parse_args(["--output-dir", "a", "--validate-dir", "b"])
        for forbidden in ("--url", "--tile-side", "--force", "--refresh"):
            with self.assertRaises(SystemExit):
                tool.parse_args(["--output-dir", "a", forbidden, "x"])
        generated = tool.parse_args(["--output-dir", "a"])
        self.assertEqual(generated.output_dir, Path("a"))
        self.assertIsNone(generated.validate_dir)

    def test_module_reload_performs_no_network_or_device_action(self) -> None:
        with mock.patch.object(
            urllib.request.OpenerDirector,
            "open",
            side_effect=AssertionError("network access attempted"),
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("socket access attempted"),
        ), mock.patch("os.open", side_effect=AssertionError("device open attempted")):
            importlib.reload(tool)


if __name__ == "__main__":
    unittest.main()
