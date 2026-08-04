from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from tools.check_repo_contract import (
    CheckResult,
    check_driver_frame_contract,
    check_manifest,
    check_public_driver_header,
    check_upload_contract,
    run_checks,
)
from tools.mf1750_frame_tool import (
    ALLOWED_BUILD_TAGS,
    REQUIRED_DRIVER_API,
    REQUIRED_REFRESH_SPI_HZ,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class CurrentRepositoryTests(unittest.TestCase):
    def test_current_repository_contract_passes(self) -> None:
        report = run_checks(REPO_ROOT)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["hardware_tested"])
        self.assertEqual(len(report["checks"]), 6)


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

    def test_default_frozen_manifest_cannot_be_rewritten_with_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "changed.gbr"
            artifact.write_bytes(b"coordinated change")
            manifest_path = root / "manufacturing_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "file": artifact.name,
                                "bytes": artifact.stat().st_size,
                                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = check_manifest(root)
            self.assertFalse(result.passed)
            self.assertTrue(any("manifest fingerprint changed" in error for error in result.errors))

    def test_default_frozen_directory_rejects_unlisted_files(self) -> None:
        from tools.check_repo_contract import PRODUCTION_RELATIVE

        with tempfile.TemporaryDirectory() as temporary:
            source = REPO_ROOT / PRODUCTION_RELATIVE
            root = Path(temporary)
            for source_path in source.rglob("*"):
                if not source_path.is_file():
                    continue
                relative = source_path.relative_to(source)
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source_path.read_bytes())
            (root / "unexpected.tmp").write_text("not frozen", encoding="utf-8")
            result = check_manifest(root)
            self.assertFalse(result.passed)
            self.assertTrue(any("unlisted file" in error for error in result.errors))


class StaticContractTests(unittest.TestCase):
    def test_formal_frame_tool_preflight_matches_firmware_constants(self) -> None:
        main_cpp = (REPO_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        driver_header = (REPO_ROOT / "src" / "epd_driver.h").read_text(
            encoding="utf-8"
        )
        config_header = (REPO_ROOT / "src" / "epd_config.h").read_text(
            encoding="utf-8"
        )

        build_match = re.search(
            r'FW_BUILD_TAG\s*=\s*"([^"]+)"\s*;', main_cpp, flags=re.MULTILINE
        )
        api_match = re.search(
            r'EPD_DRIVER_API_VERSION\s*=\s*"([^"]+)"\s*;', driver_header
        )
        spi_match = re.search(
            r"EPD_SPI_DEFAULT_HZ\s*=\s*(\d+)\s*;", config_header
        )

        self.assertIsNotNone(build_match)
        self.assertIsNotNone(api_match)
        self.assertIsNotNone(spi_match)
        self.assertEqual(ALLOWED_BUILD_TAGS, frozenset({build_match.group(1)}))
        self.assertEqual(REQUIRED_DRIVER_API, api_match.group(1))
        self.assertEqual(REQUIRED_REFRESH_SPI_HZ, int(spi_match.group(1)))

    def test_public_header_rejects_legacy_diagnostic_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            header = Path(temporary) / "epd_driver.h"
            header.write_text("void epdDiagnosticBars512();\n", encoding="utf-8")
            result = check_public_driver_header(header)
            self.assertFalse(result.passed)
            self.assertTrue(any("legacy/diagnostic" in error for error in result.errors))

    def test_public_header_operation_id_is_u32(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.h").read_text(encoding="utf-8")
        source = source.replace(
            "uint32_t operationId = 0;",
            "uint64_t operationId = 0;",
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            header = Path(temporary) / "epd_driver.h"
            header.write_text(source, encoding="utf-8")
            result = check_public_driver_header(header)
        self.assertFalse(result.passed)
        self.assertTrue(any("host u32 contract" in error for error in result.errors))

    def test_upload_contract_rejects_string_handling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            main_cpp = Path(temporary) / "main.cpp"
            main_cpp.write_text("strlen(raw.buf);\n", encoding="utf-8")
            result = check_upload_contract(main_cpp)
            self.assertFalse(result.passed)
            self.assertTrue(any("C string" in error for error in result.errors))

    def test_upload_contract_requires_device_side_colour_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            main_cpp = Path(temporary) / "main.cpp"
            main_cpp.write_text(
                '\n'.join(
                    (
                        'contentType.startsWith("application/octet-stream")',
                        "server.clientContentLength() != static_cast<int>(EPD_FRAME_BYTES)",
                        "offset + raw.currentSize > EPD_FRAME_BYTES",
                        "raw.totalSize == EPD_FRAME_BYTES",
                        "memcpy(frameBuffer + offset, raw.buf, raw.currentSize)",
                        'server.on("/api/frame", HTTP_POST',
                        'server.send(202, "application/json"',
                    )
                ),
                encoding="utf-8",
            )
            result = check_upload_contract(main_cpp)
            self.assertFalse(result.passed)
            self.assertTrue(any("physical color validation" in error for error in result.errors))

    def test_upload_contract_requires_completed_job_report_correlation(self) -> None:
        source = (REPO_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        source = source.replace(
            "epdPublishedReportJson = completedJobSnapshot;",
            "// completed report snapshot publish removed",
        )
        with tempfile.TemporaryDirectory() as temporary:
            main_cpp = Path(temporary) / "main.cpp"
            main_cpp.write_text(source, encoding="utf-8")
            result = check_upload_contract(main_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("atomic completed report publish" in error for error in result.errors))

    def test_diagnostic_get_must_not_read_live_driver_report(self) -> None:
        source = (REPO_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        source = source.replace(
            "return epdPublishedReportJson;",
            "return epdDiagnosticReportJson();",
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            main_cpp = Path(temporary) / "main.cpp"
            main_cpp.write_text(source, encoding="utf-8")
            result = check_upload_contract(main_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("mutable live driver report" in error for error in result.errors))

    def test_public_driver_must_validate_colours_before_panel_io(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(
                "bool epdDisplayFrameAtFrequency() { epdPrepareCascade(spiHz); }\n",
                encoding="utf-8",
            )
            result = check_driver_frame_contract(driver_cpp)
            self.assertFalse(result.passed)
            self.assertTrue(any("packed color validator" in error for error in result.errors))

    def test_driver_contract_requires_per_stage_busy_evidence(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace(
            "recordWaitEvidence(stage, elapsed, sawBusy)",
            "// wait evidence removed",
        )
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("wait evidence recorder" in error for error in result.errors))

    def test_driver_contract_rejects_non_strict_drf_wait(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace(
            'epdWaitBusyThenIdle("DRF")',
            'epdWaitIdle("DRF")',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("DRF strict BUSY wait" in error for error in result.errors))

    def test_driver_contract_requires_operation_id_json(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace('\\"operation_id\\":', '\\"removed_id\\":', 1)
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("operation id report" in error for error in result.errors))

    def test_solid_diagnostic_must_start_fresh_report(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        solid_start = source.index("bool epdDiagnosticSolid(")
        begin = source.index("epdBeginOperation(spiHz)", solid_start)
        source = source[:begin] + "millis()" + source[begin + len("epdBeginOperation(spiHz)") :]
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("must begin a fresh operation" in error for error in result.errors))


class FingerprintTests(unittest.TestCase):
    def test_text_fingerprint_accepts_lf_and_crlf_checkout_forms(self) -> None:
        from tools.check_repo_contract import _matches_fingerprint

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frozen.csv"
            crlf = b"name,value\r\nalpha,1\r\n"
            expected_bytes = len(crlf)
            expected_sha256 = hashlib.sha256(crlf).hexdigest()

            path.write_bytes(crlf)
            self.assertTrue(_matches_fingerprint(path, expected_bytes, expected_sha256))
            path.write_bytes(crlf.replace(b"\r\n", b"\n"))
            self.assertTrue(_matches_fingerprint(path, expected_bytes, expected_sha256))
            path.write_bytes(b"name,value\nalpha,2\n")
            self.assertFalse(_matches_fingerprint(path, expected_bytes, expected_sha256))

            lf = crlf.replace(b"\r\n", b"\n")
            expected_bytes = len(lf)
            expected_sha256 = hashlib.sha256(lf).hexdigest()
            path.write_bytes(crlf)
            self.assertTrue(_matches_fingerprint(path, expected_bytes, expected_sha256))

    def test_binary_fingerprint_never_normalizes_line_endings(self) -> None:
        from tools.check_repo_contract import _matches_fingerprint

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frozen.zip"
            expected = b"binary\r\npayload\r\n"
            path.write_bytes(expected.replace(b"\r\n", b"\n"))
            self.assertFalse(
                _matches_fingerprint(
                    path,
                    len(expected),
                    hashlib.sha256(expected).hexdigest(),
                )
            )


if __name__ == "__main__":
    unittest.main()
