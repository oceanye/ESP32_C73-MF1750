from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tools.mf1750_n5_measurement_campaign import (
    EXPECTED_DEFAULT_MANIFEST_CANONICAL_SHA256,
    EXPECTED_DEFAULT_MANIFEST_FILE_SHA256,
    compile_campaign_manifest,
    manifest_file_sha256,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
N5_SOURCES = (
    REPO_ROOT / "host" / "extended_color" / "spectral.py",
    REPO_ROOT / "host" / "extended_color" / "aggregation.py",
    REPO_ROOT / "tools" / "mf1750_n5_measurement_campaign.py",
)


class N5RepositoryContractTests(unittest.TestCase):
    def test_required_source_test_and_handoff_files_exist(self) -> None:
        required = (
            *N5_SOURCES,
            REPO_ROOT / "tests" / "test_extended_color_spectral.py",
            REPO_ROOT / "tests" / "test_extended_color_aggregation.py",
            REPO_ROOT / "tests" / "test_n5_measurement_campaign.py",
            REPO_ROOT / "docs" / "N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md",
        )
        self.assertTrue(all(path.is_file() for path in required))

    def test_default_manifest_identity_is_frozen(self) -> None:
        self.assertIsNotNone(EXPECTED_DEFAULT_MANIFEST_CANONICAL_SHA256)
        self.assertIsNotNone(EXPECTED_DEFAULT_MANIFEST_FILE_SHA256)
        manifest = compile_campaign_manifest()
        self.assertEqual(
            manifest["integrity"]["canonical_sha256"],
            EXPECTED_DEFAULT_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            manifest_file_sha256(manifest), EXPECTED_DEFAULT_MANIFEST_FILE_SHA256
        )

    def test_n5_modules_have_no_network_device_or_executor_imports(self) -> None:
        forbidden_roots = {
            "requests",
            "httpx",
            "socket",
            "serial",
            "pyserial",
            "gpiozero",
            "RPi",
            "esptool",
        }
        for path in N5_SOURCES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertEqual(imported & forbidden_roots, set(), path.name)

    def test_no_cie_standard_sample_table_is_bundled(self) -> None:
        extensions = {".csv", ".tsv", ".dat"}
        bundled = [
            path
            for path in (REPO_ROOT / "host" / "extended_color").iterdir()
            if path.suffix.lower() in extensions
        ]
        self.assertEqual(bundled, [])

    def test_handoff_freezes_counts_and_power_exception(self) -> None:
        handoff = (
            REPO_ROOT / "docs" / "N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md"
        ).read_text(encoding="utf-8")
        for required_text in (
            "11 sessions / 22 actions",
            "8 sessions / 9 actions",
            "7 sessions / 42 actions",
            "轮内 6 个",
            "J2 保持接通",
            "6 codes × 2 orientations × 3 runs = 36",
            "36 pairs × 5 repeats × 2 controllers = 360",
            "paired_controller_diagnostics",
        ):
            self.assertIn(required_text, handoff)


if __name__ == "__main__":
    unittest.main()
