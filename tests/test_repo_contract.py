from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_repo_contract import (
    CheckResult,
    check_manifest,
    check_public_driver_header,
    check_upload_contract,
    run_checks,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class CurrentRepositoryTests(unittest.TestCase):
    def test_current_repository_contract_passes(self) -> None:
        report = run_checks(REPO_ROOT)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["hardware_tested"])
        self.assertEqual(len(report["checks"]), 5)


class ManifestTests(unittest.TestCase):
    def test_manifest_detects_hash_corruption_and_wrong_entry_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "frozen.bin"
            artifact.write_bytes(b"correct")
            manifest = {
                "files": [
                    {
                        "file": "frozen.bin",
                        "bytes": 7,
                        "sha256": hashlib.sha256(b"different").hexdigest(),
                    }
                ]
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = check_manifest(root, manifest_path)
            self.assertFalse(result.passed)
            self.assertTrue(any("fingerprint mismatch" in error for error in result.errors))
            self.assertTrue(any("28 entries" in error for error in result.errors))

    def test_manifest_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps({"files": [{"file": "../escape", "bytes": 0, "sha256": ""}]}),
                encoding="utf-8",
            )
            result = check_manifest(root, manifest_path)
            self.assertTrue(any("escapes" in error for error in result.errors))


class StaticContractTests(unittest.TestCase):
    def test_public_header_rejects_legacy_diagnostic_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            header = Path(temporary) / "epd_driver.h"
            header.write_text("void epdDiagnosticBars512();\n", encoding="utf-8")
            result = check_public_driver_header(header)
            self.assertFalse(result.passed)
            self.assertTrue(any("legacy/diagnostic" in error for error in result.errors))

    def test_upload_contract_rejects_string_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            main_cpp = Path(temporary) / "main.cpp"
            main_cpp.write_text("strlen(raw.buf);\n", encoding="utf-8")
            result = check_upload_contract(main_cpp)
            self.assertFalse(result.passed)
            self.assertTrue(any("C string" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
