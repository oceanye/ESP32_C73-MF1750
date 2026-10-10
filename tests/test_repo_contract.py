from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from tools.check_repo_contract import (
    LEGACY_LIVE_BLOCK_MARKERS,
    N6_PHYSICAL_OPERATOR_ENTRYPOINT_MARKERS,
    PHYSICAL_PRODUCTION_ENTRYPOINT_MARKERS,
    check_driver_frame_contract,
    check_n6_physical_operator_closure,
    check_manifest,
    check_n3_fixed_execution_contract,
    check_n2p_fixed_execution_contract,
    check_n4_v3_fixed_execution_contract,
    check_physical_production_entrypoints,
    check_public_driver_header,
    check_upload_contract,
    run_checks,
)
from tools.mf1750_frame_tool import (
    ALLOWED_BUILD_TAGS,
    BUSY_TRACE_BUILD_TAGS,
    REQUIRED_DRIVER_API,
    REQUIRED_REFRESH_SPI_HZ,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class CurrentRepositoryTests(unittest.TestCase):
    def test_current_repository_contract_passes(self) -> None:
        report = run_checks(REPO_ROOT)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["hardware_tested"])
        self.assertEqual(len(report["checks"]), 11)


class PhysicalProductionEntrypointTests(unittest.TestCase):
    def test_completed_physical_entrypoints_and_legacy_blocks_pass(self) -> None:
        result = check_physical_production_entrypoints(REPO_ROOT)
        self.assertTrue(result.passed, result)
        self.assertEqual(
            result.checked_items,
            len(PHYSICAL_PRODUCTION_ENTRYPOINT_MARKERS)
            + len(LEGACY_LIVE_BLOCK_MARKERS),
        )

    def test_missing_legacy_public_hard_block_fails_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contracts = {
                **PHYSICAL_PRODUCTION_ENTRYPOINT_MARKERS,
                **LEGACY_LIVE_BLOCK_MARKERS,
            }
            for relative in contracts:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    (REPO_ROOT / relative).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            victim = root / "tools/g1_s1_rc2g_n8_once.py"
            victim.write_text(
                victim.read_text(encoding="utf-8").replace(
                    "raise N8FixedActionError(LEGACY_LIVE_BLOCK_MESSAGE)",
                    "# removed legacy public hard block",
                    1,
                ),
                encoding="utf-8",
            )
            result = check_physical_production_entrypoints(root)
        self.assertFalse(result.passed)
        self.assertTrue(
            any(
                "legacy live block tools/g1_s1_rc2g_n8_once.py missing marker"
                in error
                for error in result.errors
            )
        )

    def test_completed_n6_physical_operator_contract_passes(self) -> None:
        result = check_n6_physical_operator_closure(REPO_ROOT)
        self.assertTrue(result.passed, result)
        self.assertEqual(result.name, "n6_physical_operator_closure")
        self.assertEqual(
            result.checked_items, len(N6_PHYSICAL_OPERATOR_ENTRYPOINT_MARKERS)
        )
        self.assertFalse(result.warnings)

    def test_absent_completed_n6_files_fail_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = check_n6_physical_operator_closure(Path(temporary))
        self.assertFalse(result.passed, result)
        for relative in N6_PHYSICAL_OPERATOR_ENTRYPOINT_MARKERS:
            self.assertTrue(
                any(relative.as_posix() in error for error in result.errors),
                relative,
            )


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
    def test_n3_shared_plan_runner_and_analyzer_contract_passes(self) -> None:
        result = check_n3_fixed_execution_contract(REPO_ROOT)
        self.assertTrue(result.passed, result.errors)

    def test_n4_v3_shared_runner_and_analyzer_contract_passes(self) -> None:
        result = check_n4_v3_fixed_execution_contract(REPO_ROOT)
        self.assertTrue(result.passed, result.errors)

    def test_n2p_execution_supplement_rejects_byte_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "tools").mkdir()
            source_supplement = (
                REPO_ROOT / "docs" / "N2P_RC2G_FIXED_EXECUTION_SUPPLEMENT_V2.json"
            )
            source_runner = (
                REPO_ROOT / "tools" / "g1_s1_rc2g_n2_photo_campaign_once.py"
            )
            payload = source_supplement.read_bytes().replace(
                b'"maximum_post_requests_per_action":1',
                b'"maximum_post_requests_per_action":2',
                1,
            )
            (root / "docs" / source_supplement.name).write_bytes(payload)
            (root / "tools" / source_runner.name).write_bytes(
                source_runner.read_bytes()
            )
            result = check_n2p_fixed_execution_contract(root)
        self.assertFalse(result.passed)
        self.assertTrue(any("SHA-256 changed" in error for error in result.errors))

    def test_driver_api_reference_matches_registered_routes_and_identity(self) -> None:
        api_reference = (REPO_ROOT / "docs" / "MF1750_DRIVER_API.md").read_text(
            encoding="utf-8"
        )
        main_cpp = "\n".join(
            (REPO_ROOT / "src" / name).read_text(encoding="utf-8")
            for name in ("main.cpp", "n7_main.cpp")
        )
        registered_routes = {
            (method, route)
            for route, method in re.findall(
                r'server\.on\("([^"]+)",\s*HTTP_(GET|POST)', main_cpp
            )
            if route.startswith("/api/")
        }
        documented_routes = {
            (method, route)
            for method, route in re.findall(
                r"\|\s*(GET|POST)\s*\|\s*`(/api/[^`]+)`", api_reference
            )
        }
        documented_routes.update(
            re.findall(r"`(GET|POST) (/api/[^`]+)`", api_reference)
        )

        self.assertEqual(documented_routes, registered_routes)
        for build_tag in ALLOWED_BUILD_TAGS:
            self.assertIn(build_tag, api_reference)
        self.assertIn(REQUIRED_DRIVER_API, api_reference)
        self.assertIn("精确 `307200`", api_reference)
        self.assertIn("`0x0` | 黑", api_reference)
        self.assertIn("`0x6` | 绿", api_reference)
        for public_function in (
            "epdBegin",
            "epdReadBusy",
            "epdGetLastOperationReport",
            "epdIsSupportedColorCode",
            "epdValidateFrameColors",
            "epdDisplayFrame",
            "epdDisplayFrameAtFrequency",
            "epdClearWhite",
            "epdClearBlack",
        ):
            self.assertIn(f"{public_function}(", api_reference)

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
        current_build_tag = build_match.group(1)
        self.assertIn(current_build_tag, ALLOWED_BUILD_TAGS)
        self.assertEqual(BUSY_TRACE_BUILD_TAGS, frozenset({current_build_tag}))
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

    def test_driver_contract_requires_pre_command_idle_gate(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace(
            'epdRequireIdleBeforeCommand("DRF")',
            'true /* removed DRF pre-command idle gate */',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("DRF pre-command idle gate" in error for error in result.errors))

    def test_driver_contract_requires_busy_trace_schema(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace(
            '\\"busy_trace_schema_version\\":1',
            '\\"removed_busy_trace_schema_version\\":1',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(any("BUSY trace schema report" in error for error in result.errors))

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

    def test_driver_contract_rejects_strict_post_psr_busy_wait(self) -> None:
        source = (REPO_ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
        source = source.replace(
            'epdWaitIdle("post-display PSR")',
            'epdWaitBusyThenIdle("post-display PSR")',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            driver_cpp = Path(temporary) / "epd_driver.cpp"
            driver_cpp.write_text(source, encoding="utf-8")
            result = check_driver_frame_contract(driver_cpp)
        self.assertFalse(result.passed)
        self.assertTrue(
            any("must not require a BUSY assertion" in error for error in result.errors)
        )

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
