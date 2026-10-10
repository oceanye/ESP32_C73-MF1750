from __future__ import annotations

import importlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
from typing import Mapping
import unittest
from unittest import mock
import urllib.request

from tools import g1_s1_root_cause_2x2_candidate as tool


class RootCause2x2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = tool.build_factorial_artifacts()
        cls.manifest = cls.artifacts.manifest

    def test_frozen_manifest_and_all_cell_identities(self) -> None:
        self.assertEqual(
            tool._sha256(self.artifacts.manifest_bytes),
            tool.EXPECTED_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            self.manifest["manifest_integrity"]["canonical_sha256"],
            tool.EXPECTED_MANIFEST_CANONICAL_SHA256,
        )
        for name in tool.VARIANT_NAMES:
            with self.subTest(name=name):
                expected = tool.EXPECTED_VARIANTS[name]
                artifacts = self.artifacts.variants[name]
                record = self.manifest["variants"][name]
                self.assertEqual(tool._sha256(artifacts.codes), expected["codes_sha256"])
                self.assertEqual(tool._sha256(artifacts.frame), expected["frame_sha256"])
                self.assertEqual(record["frame"]["fnv1a"], expected["frame_fnv1a"])
                self.assertEqual(tool._sha256(artifacts.strict_png), expected["strict_sha256"])
                self.assertEqual(
                    tuple(
                        item["total_internal_edges"]["different"]
                        for item in record["spatial_metrics"]["controllers"]
                    ),
                    expected["controller_internal_edges"],
                )
                self.assertEqual(
                    record["spatial_metrics"]["controller_seam"]["different"],
                    expected["controller_seam"],
                )
                self.assertEqual(
                    record["spatial_metrics"]["total_four_neighbour_edges"]["different"],
                    expected["total_edges"],
                )

    def test_global_histogram_and_transition_are_exactly_identical(self) -> None:
        global_matrix = tool._matrix_record(tool.GLOBAL_TRANSITION_MATRIX)
        for name in tool.VARIANT_NAMES:
            record = self.manifest["variants"][name]
            self.assertEqual(record["counts"]["global"], list(tool.GLOBAL_COUNTS))
            self.assertEqual(
                record["transitions_from_map_prior"]["global"], global_matrix
            )
            self.assertEqual(
                record["transitions_from_map_prior"]["changed_pixels"],
                tool.EXPECTED_CHANGED_PIXELS,
            )
        self.assertTrue(
            self.manifest["design"]["exact_shared_invariants"][
                "global_histogram_exactly_equal"
            ]
            if "global_histogram_exactly_equal"
            in self.manifest["design"]["exact_shared_invariants"]
            else self.manifest["design"]["orthogonality_audit"][
                "global_histogram_exactly_equal"
            ]
        )

    def test_half_load_factor_is_exact_and_independent_of_A(self) -> None:
        for spatial in ("high", "low"):
            balanced = self.manifest["variants"][f"{spatial}-balanced"]
            unbalanced = self.manifest["variants"][f"{spatial}-unbalanced"]
            self.assertEqual(balanced["counts"]["left"], list(tool.BALANCED_LEFT_COUNTS))
            self.assertEqual(balanced["counts"]["right"], list(tool.BALANCED_RIGHT_COUNTS))
            self.assertEqual(balanced["counts"]["half_imbalance_l1"], 4)
            self.assertEqual(
                balanced["transitions_from_map_prior"]["left"],
                tool._matrix_record(tool.BALANCED_LEFT_MATRIX),
            )
            self.assertEqual(unbalanced["counts"]["left"], list(tool.UNBALANCED_LEFT_COUNTS))
            self.assertEqual(unbalanced["counts"]["right"], list(tool.UNBALANCED_RIGHT_COUNTS))
            self.assertEqual(unbalanced["counts"]["half_imbalance_l1"], 186_896)
            self.assertEqual(
                unbalanced["transitions_from_map_prior"]["left"],
                tool._matrix_record(tool.UNBALANCED_LEFT_MATRIX),
            )

    def test_spatial_factor_has_large_separation_and_reports_residuals(self) -> None:
        checks = self.manifest["design"]["manipulation_checks"]
        self.assertGreater(checks["minimum_high_to_maximum_low_edge_ratio"], 19.0)
        for load in ("balanced", "unbalanced"):
            high = checks["total_edges"][f"high-{load}"]
            low = checks["total_edges"][f"low-{load}"]
            self.assertGreater(high, 10 * low)
        audit = self.manifest["design"]["orthogonality_audit"]
        self.assertTrue(audit["algebraic_2x2_crossing_proven"])
        self.assertTrue(audit["global_histogram_exactly_equal"])
        self.assertTrue(audit["global_transition_matrix_exactly_equal"])
        self.assertFalse(audit["exact_spatial_metric_match_within_each_A_level"])
        self.assertFalse(audit["exact_seam_match_across_cells"])
        self.assertEqual(
            audit["status"],
            "bounded_residual_covariates_not_strict_metric_orthogonality",
        )

    def test_existing_candidate_audit_eligibility_is_fail_closed(self) -> None:
        audited = self.manifest["audited_existing_candidates"]
        self.assertTrue(audited["failed_ordered"]["deep_validated"])
        self.assertTrue(audited["low_spatial"]["deep_validated"])
        self.assertTrue(audited["failed_ordered"]["eligible_as_constraint_reference"])
        self.assertTrue(audited["low_spatial"]["eligible_as_constraint_reference"])
        self.assertFalse(audited["clustered"]["eligible_as_constraint_reference"])
        self.assertFalse(audited["macro4"]["eligible_as_constraint_reference"])
        self.assertFalse(audited["failed_ordered"]["raster_identical_to_generated_cell"])
        self.assertIsNone(audited["failed_ordered"]["generated_cell_identity"])
        self.assertTrue(audited["low_spatial"]["raster_identical_to_generated_cell"])
        self.assertEqual(audited["low_spatial"]["generated_cell_identity"], "low-balanced")
        self.assertIn(
            "not any generated 2x2 cell",
            audited["failed_ordered"]["constraint_reference_reason"],
        )
        self.assertIn(
            "different global transition",
            audited["clustered"]["constraint_reference_reason"],
        )
        self.assertIn(
            "different global histogram",
            audited["macro4"]["constraint_reference_reason"],
        )

    def test_classification_and_transport_are_offline_only(self) -> None:
        classification = self.manifest["classification"]
        self.assertTrue(classification["experimental"])
        self.assertTrue(classification["simulation_only"])
        self.assertFalse(classification["formal"])
        self.assertFalse(classification["hardware_qualified"])
        self.assertFalse(classification["hardware_tested"])
        self.assertFalse(classification["upload_authorized"])
        self.assertFalse(classification["causal_attribution_authorized"])
        self.assertFalse(classification["strict_metric_orthogonality_proven"])
        self.assertEqual(
            self.manifest["transport"],
            {
                "mode": "offline",
                "endpoint": None,
                "method": None,
                "device_io_performed": False,
                "network_io_performed": False,
                "refresh_runner_implemented": False,
                "upload_authorized": False,
            },
        )

    def test_impossible_algebra_fails_before_raster_generation(self) -> None:
        changed = list(tool.GLOBAL_TRANSITION_MATRIX)
        first = list(changed[0])
        first[0] += 1
        changed[0] = tuple(first)
        with mock.patch.object(tool, "GLOBAL_TRANSITION_MATRIX", tuple(changed)):
            with self.assertRaisesRegex(tool.FactorialCandidateError, "global transition rows"):
                tool.validate_algebraic_contract()

    def test_argument_validation_rejects_unfrozen_factor_values(self) -> None:
        prior, _ = tool.low_spatial.generate_diagnostic_codes()
        with self.assertRaisesRegex(tool.FactorialCandidateError, "spatial factor"):
            tool.generate_variant_codes(prior, spatial="medium", load="balanced")
        with self.assertRaisesRegex(tool.FactorialCandidateError, "load factor"):
            tool.generate_variant_codes(prior, spatial="low", load="approximate")


class RootCause2x2SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = getattr(RootCause2x2ContractTests, "artifacts", None)
        if cls.artifacts is None:
            cls.artifacts = tool.build_factorial_artifacts()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        for filename, payload in self.artifacts.files().items():
            (self.bundle / filename).write_bytes(payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _validate_cached(self) -> Mapping[str, object]:
        with mock.patch.object(tool, "build_factorial_artifacts", return_value=self.artifacts):
            return tool.validate_factorial_directory(self.bundle)

    def test_exact_file_set_and_cached_deep_regeneration(self) -> None:
        manifest = self._validate_cached()
        self.assertEqual(manifest, self.artifacts.manifest)
        self.assertEqual({path.name for path in self.bundle.iterdir()}, tool.REQUIRED_FILES)

    def test_tampered_and_resigned_manifest_is_rejected(self) -> None:
        manifest = json.loads((self.bundle / "manifest.json").read_text("utf-8"))
        manifest["classification"]["causal_attribution_authorized"] = True
        manifest.pop("manifest_integrity")
        manifest["manifest_integrity"] = {
            "canonical_sha256": tool._sha256(tool._canonical_json(manifest)),
            "canonical_sha256_scope": tool.MANIFEST_HASH_SCOPE,
        }
        (self.bundle / "manifest.json").write_bytes(tool._canonical_json(manifest))
        with mock.patch.object(tool, "build_factorial_artifacts", return_value=self.artifacts):
            with self.assertRaisesRegex(tool.FactorialCandidateError, "deep regeneration"):
                tool.validate_factorial_directory(self.bundle)

    def test_frame_tamper_and_extra_file_are_rejected(self) -> None:
        frame_path = self.bundle / "high-balanced.frame.bin"
        payload = bytearray(frame_path.read_bytes())
        payload[0] ^= 0x11
        frame_path.write_bytes(payload)
        with mock.patch.object(tool, "build_factorial_artifacts", return_value=self.artifacts):
            with self.assertRaisesRegex(tool.FactorialCandidateError, "differs from regeneration"):
                tool.validate_factorial_directory(self.bundle)
        frame_path.write_bytes(self.artifacts.files()["high-balanced.frame.bin"])
        (self.bundle / "extra.txt").write_text("no", encoding="utf-8")
        with self.assertRaisesRegex(tool.FactorialCandidateError, "file set"):
            tool.validate_factorial_directory(self.bundle)

    def test_existing_output_is_never_overwritten(self) -> None:
        with self.assertRaisesRegex(tool.FactorialCandidateError, "already exists"):
            tool.write_factorial_directory(self.bundle)

    def test_directory_and_file_symlinks_are_rejected(self) -> None:
        link = self.root / "bundle-link"
        try:
            link.symlink_to(self.bundle, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        with self.assertRaises(tool.FactorialCandidateError):
            tool.validate_factorial_directory(link)
        link.unlink()
        target = self.bundle / "high-balanced.frame.bin"
        payload = target.read_bytes()
        target.unlink()
        external = self.root / "external.bin"
        external.write_bytes(payload)
        target.symlink_to(external)
        with self.assertRaisesRegex(tool.FactorialCandidateError, "symlinks"):
            tool.validate_factorial_directory(self.bundle)

    def test_cli_has_no_network_device_refresh_or_variant_surface(self) -> None:
        for forbidden in ("--url", "--refresh", "--runner", "--force", "--variant"):
            with self.subTest(forbidden=forbidden):
                with mock.patch("sys.stderr", new=io.StringIO()):
                    with self.assertRaises(SystemExit):
                        tool.parse_args([forbidden, "x"])
        self.assertEqual(
            tool.parse_args(["--validate-dir", os.fspath(self.bundle)]).validate_dir,
            self.bundle,
        )

    def test_import_reload_performs_no_network_or_device_open(self) -> None:
        with mock.patch.object(socket, "socket", side_effect=AssertionError("socket used")), mock.patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("urlopen used")
        ), mock.patch.object(
            urllib.request, "build_opener", side_effect=AssertionError("opener used")
        ):
            reloaded = importlib.reload(tool)
        self.assertEqual(reloaded.MANIFEST_KIND, tool.MANIFEST_KIND)


if __name__ == "__main__":
    unittest.main()
