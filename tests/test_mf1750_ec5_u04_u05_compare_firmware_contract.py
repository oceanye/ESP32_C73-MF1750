from __future__ import annotations

import os
from pathlib import Path
import re
import unittest

from tools import mf1750_ec5_u04_u05_compare_identity as identity


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSOLETE_HORIZONTAL_ACTION = (
    "45f212f9ac38b7a9117e312868abdad8cc67e95329698924cd08743b36609897"
)


def _section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*$\n(.*?)(?=^\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing PlatformIO section: {name}")
    return match.group(1)


def _function(text: str, name: str, next_name: str | None = None) -> str:
    suffix = (
        rf"(?=\n[^\n]*\b{re.escape(next_name)}\s*\()"
        if next_name is not None
        else r"(?=\Z)"
    )
    match = re.search(
        rf"\b{re.escape(name)}\s*\([^)]*\)\s*\{{(.*?){suffix}",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function: {name}")
    return match.group(1)


def _compare_driver_section(text: str) -> str:
    match = re.search(
        r"#if MF1750_ENABLE_U04_U05_COMPARE\s+(.*?)"
        r"#endif  // MF1750_ENABLE_U04_U05_COMPARE",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("missing comparison driver section")
    return match.group(1)


def _byte_array(text: str, symbol: str) -> bytes:
    match = re.search(
        rf"static const uint8_t {re.escape(symbol)}\[32\]\s*=\s*\{{(.*?)\}};",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing byte array: {symbol}")
    values = bytes(int(item, 16) for item in re.findall(r"0x([0-9A-Fa-f]{2})", match.group(1)))
    if len(values) != 32:
        raise AssertionError(f"{symbol} must contain exactly 32 bytes")
    return values


class Ec5U04U05CompareFirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ini = (REPO_ROOT / "platformio.ini").read_text(encoding="utf-8")
        cls.main = (REPO_ROOT / "src/ec5_u04_u05_compare_main.cpp").read_text(
            encoding="utf-8"
        )
        cls.driver = (REPO_ROOT / "src/epd_driver.cpp").read_text(
            encoding="utf-8"
        )
        cls.header = (REPO_ROOT / "src/epd_driver.h").read_text(
            encoding="utf-8"
        )
        cls.compare_driver = _compare_driver_section(cls.driver)

    def test_platformio_environment_is_dedicated_and_all_others_exclude_it(self) -> None:
        compare = _section(
            self.ini, "env:esp32-s3-devkitc-1-ec5-u04-u05-compare"
        )
        for token in (
            "+<epd_driver.cpp>",
            "+<ec5_u04_u05_compare_main.cpp>",
            "-<main.cpp>",
            "-<n7_main.cpp>",
            "-<ec5_unknown_probe_main.cpp>",
            "-<ec5_sixstate_main.cpp>",
            "-D MF1750_ENABLE_U04_U05_COMPARE=1",
        ):
            self.assertIn(token, compare)
        self.assertNotIn("MF1750_UNKNOWN_PROBE_CODE", compare)
        self.assertNotIn("MF1750_ENABLE_UNKNOWN_PROBE=1", compare)
        self.assertNotIn("MF1750_ENABLE_SIXSTATE_PROBE=1", compare)

        for environment in (
            "env:esp32-s3-devkitc-1",
            "env:esp32-s3-devkitc-1-n7-spi-sweep",
            "env:esp32-s3-devkitc-1-ec5-u04",
            "env:esp32-s3-devkitc-1-ec5-u07",
            "env:esp32-s3-devkitc-1-ec5-sixstate-u04",
            "env:esp32-s3-devkitc-1-ec5-sixstate-u07",
        ):
            self.assertIn(
                "-<ec5_u04_u05_compare_main.cpp>",
                _section(self.ini, environment),
            )

    def test_driver_api_is_compile_guarded_without_weakening_public_colours(self) -> None:
        for token in (
            "MF1750_ENABLE_U04_U05_COMPARE",
            "bool epdValidateCompiledU04U05CompareFixture();",
            "bool epdDisplayCompiledU04U05Compare();",
        ):
            self.assertIn(token, self.header)
        self.assertIn(
            "MF1750_ENABLE_U04_U05_COMPARE &&", self.header
        )
        validator = _function(self.driver, "epdValidateFrameColors", "epdBegin")
        self.assertIn("epdIsSupportedColorCode(high)", validator)
        self.assertIn("epdIsSupportedColorCode(low)", validator)
        self.assertNotIn("COMPARE_U04_CODE", validator)
        supported = _function(
            self.driver, "epdIsSupportedColorCode", "epdValidateFrameColors"
        )
        self.assertNotIn("case 0x4", supported)
        self.assertNotIn("COMPARE_U04_CODE", supported)

    def test_diagonal_geometry_is_balanced_and_old_horizontal_action_is_absent(self) -> None:
        expected_tokens = (
            '"EC5_U04_U05_QUAD64_DIAGONAL_V1"',
            "COMPARE_TOP_Y0 = 188",
            "COMPARE_TOP_Y1 = 252",
            "COMPARE_BOTTOM_Y0 = 348",
            "COMPARE_BOTTOM_Y1 = 412",
            "COMPARE_CS1_X0 = 224",
            "COMPARE_CS1_X1 = 288",
            "COMPARE_CS2_X0 = 736",
            "COMPARE_CS2_X1 = 800",
        )
        for token in expected_tokens:
            self.assertIn(token, self.main + self.compare_driver)
        for roi in identity.ROIS:
            self.assertEqual(int(roi["x1"]) - int(roi["x0"]), 64)
            self.assertEqual(int(roi["y1"]) - int(roi["y0"]), 64)
        self.assertEqual(
            {(roi["controller"], roi["vertical_position"], roi["code"]) for roi in identity.ROIS},
            {
                ("CS1", "top", 4),
                ("CS1", "bottom", 5),
                ("CS2", "top", 5),
                ("CS2", "bottom", 4),
            },
        )
        self.assertNotIn(OBSOLETE_HORIZONTAL_ACTION, self.main + self.driver)

    def test_independent_frame_hashes_histogram_and_runtime_arrays_match(self) -> None:
        generated = identity.generated_identity()
        expected = {
            "frame_sha256": identity.FRAME_SHA256,
            "frame_fnv1a": identity.FRAME_FNV1A,
            "cs1_dtm_sha256": identity.CS1_DTM_SHA256,
            "cs1_dtm_fnv1a": identity.CS1_DTM_FNV1A,
            "cs2_dtm_sha256": identity.CS2_DTM_SHA256,
            "cs2_dtm_fnv1a": identity.CS2_DTM_FNV1A,
        }
        for key, value in expected.items():
            self.assertEqual(generated[key], value)
        self.assertEqual(generated["histogram"], {"white": 598016, "u04": 8192, "u05": 8192})
        self.assertNotEqual(identity.CS1_DTM_SHA256, identity.CS2_DTM_SHA256)

        arrays = {
            "frame_sha256": _byte_array(self.compare_driver, "EC5_FRAME_SHA256"),
            "cs1_dtm_sha256": _byte_array(
                self.compare_driver, "EC5_CS1_DTM_SHA256"
            ),
            "cs2_dtm_sha256": _byte_array(
                self.compare_driver, "EC5_CS2_DTM_SHA256"
            ),
        }
        for key, payload in arrays.items():
            self.assertEqual(payload.hex(), expected[key])
        for token in (
            '"c3f1d19adb80169339d32a7e7e61bb5f3a0db9e2e823080412ea91227eaa310d"',
            '"583a45a83f38139ea823294a1a0d6f4175bed44876ec94d883fcc04329dfdb50"',
            '"a9c4ced54fc456f424f615c6885dd661517ebdc8a12ee9581d1420e1a9996ad3"',
            "0x9A7A3DC5UL",
            "0x65B20DC5UL",
            "0xD9B20DC5UL",
        ):
            self.assertIn(token, self.main + self.compare_driver)

    def test_frame_validator_is_exact_and_checks_only_1_4_5(self) -> None:
        build = _function(
            self.compare_driver,
            "compareBuildAndValidateFrame",
            "compareComputeDtmIdentity",
        )
        for token in (
            "compareExpectedCode(x, y)",
            "compareExpectedCode(static_cast<uint16_t>(x + 1), y)",
            "histogram[EPD_COLOR_WHITE] == COMPARE_WHITE_PIXELS",
            "histogram[COMPARE_U04_CODE] == COMPARE_PIXELS_PER_CODE",
            "histogram[COMPARE_U05_CODE] == COMPARE_PIXELS_PER_CODE",
            "*frameFnv1a == COMPARE_FRAME_FNV1A",
        ):
            self.assertIn(token, build)
        self.assertIn("histogram[0] + histogram[2] + histogram[3]", build)
        validation = _function(
            self.compare_driver,
            "compareValidateFixture",
            "epdValidateCompiledU04U05CompareFixture",
        )
        for token in (
            "mbedtls_sha256_ret(frame, EPD_FRAME_BYTES",
            "EC5_FRAME_SHA256",
            "compareComputeDtmIdentity(frame, false",
            "compareComputeDtmIdentity(frame, true",
            "compareIdentityMatches(validation->cs1, false)",
            "compareIdentityMatches(validation->cs2, true)",
        ):
            self.assertIn(token, validation)

    def test_boot_and_action_share_exact_no_io_guard_and_streams_precede_pon(self) -> None:
        setup = _function(self.main, "setup", "loop")
        self.assertIn(
            "driverFixtureGuardPassed = epdValidateCompiledU04U05CompareFixture()",
            setup,
        )
        self.assertLess(
            setup.index("epdValidateCompiledU04U05CompareFixture()"),
            setup.index("epdBegin()"),
        )
        guard = _function(
            self.compare_driver,
            "epdValidateCompiledU04U05CompareFixture",
            "epdDisplayCompiledU04U05Compare",
        )
        self.assertIn("compareValidateFixture(frame, &validation)", guard)
        for forbidden in (
            "epdBegin(",
            "epdPrepareCascade(",
            "epdCommand(",
            "epdData(",
            "digitalWrite(",
        ):
            self.assertNotIn(forbidden, guard)

        action = _function(self.compare_driver, "epdDisplayCompiledU04U05Compare")
        self.assertLess(
            action.index("compareValidateFixture(frame, &validation)"),
            action.index("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)"),
        )
        self.assertLess(
            action.index("epdStreamPackedFrameController(frame, false)"),
            action.index("epdSecondSettingAndRefresh()"),
        )
        self.assertLess(
            action.index("epdStreamPackedFrameController(frame, true)"),
            action.index("epdSecondSettingAndRefresh()"),
        )
        self.assertIn(
            "diagnosticReport.cs1DtmFnv1a != COMPARE_CS1_DTM_FNV1A",
            action,
        )
        self.assertIn(
            "diagnosticReport.cs2DtmFnv1a != COMPARE_CS2_DTM_FNV1A",
            action,
        )

    def test_prior_corrected_u04_is_read_only_and_comparison_nvs_is_independent(self) -> None:
        for token in (
            'kPriorU04Namespace = "mf1750_ec5v2"',
            'kPriorU04Key = "u04v2_phase"',
            'kActiveClaimNamespace = "mf1750_ec5cmp"',
            'kActiveClaimKey = "u45cmp_phase"',
            "priorU04Phase == kPersistentConsumed",
            "priorU04Store.begin(kPriorU04Namespace, true /* readOnly */)",
            "activeClaimStore.begin(kActiveClaimNamespace, false /* readOnly */)",
        ):
            self.assertIn(token, self.main)
        persist = _function(self.main, "persistPhase", "persistentPhaseIs")
        self.assertIn("activeClaimStore.putUChar", persist)
        self.assertNotIn("priorU04Store.put", persist)
        for forbidden in (
            "priorU04Store.put",
            "priorU04Store.clear(",
            "priorU04Store.remove(",
            "activeClaimStore.clear(",
            "activeClaimStore.remove(",
            "nvs_flash_erase",
        ):
            self.assertNotIn(forbidden, self.main)

    def test_arm_execute_is_one_shot_persisted_before_driver(self) -> None:
        arm = _function(self.main, "handleArm", "handleExecute")
        self.assertLess(
            arm.index("persistPhase(kPersistentClaimed)"),
            arm.index("compareState = CompareState::Armed"),
        )
        execute = _function(self.main, "handleExecute", "installRoutes")
        self.assertLess(
            execute.index("persistPhase(kPersistentConsumed)"),
            execute.index("executePending = true"),
        )
        worker = _function(
            self.main, "executePendingComparison", "setup"
        )
        self.assertLess(
            worker.index("persistentPhaseIs(kPersistentConsumed)"),
            worker.index("epdDisplayCompiledU04U05Compare()"),
        )
        self.assertEqual(worker.count("epdDisplayCompiledU04U05Compare()"), 1)
        for error in (
            "arm_duplicate_or_not_virgin",
            "execute_duplicate_stale_or_not_armed",
            "body_or_arguments_forbidden",
            "boot_nonce_missing_or_stale",
            "arm_nonce_missing_or_stale",
            "unknown_mutation_route",
        ):
            self.assertIn(error, self.main)

    def test_no_startup_refresh_raw_ingress_dither_retry_recovery_or_lut(self) -> None:
        setup = _function(self.main, "setup", "loop")
        self.assertNotIn("epdDisplayCompiledU04U05Compare", setup)
        for token in (
            r'\"startup_refresh\":false',
            r'\"raw_frame_ingress\":false',
            r'\"dither\":false',
            r'\"lut_modification\":false',
            r'\"retry\":false',
            r'\"recovery\":false',
        ):
            self.assertIn(token, self.main)
        for forbidden in (
            '"/api/frame"',
            '"/api/ec5/reset"',
            '"/api/ec5/retry"',
            '"/api/ec5/recovery"',
            "loadLut",
            "loadLUT",
        ):
            self.assertNotIn(forbidden, self.main + self.compare_driver)

    def test_four_get_contract_and_typed_report_fields_are_published(self) -> None:
        for route in ("version", "manifest", "status", "report"):
            self.assertIn(f'"/api/ec5/{route}"', self.main)
        for token in (
            '"MF1750_EC5_U04_U05_COMPARE_DEVICE_V1"',
            '"u04-u05-compare-v1"',
            identity.BUILD_TAG,
            identity.TEST_ID,
            identity.FROZEN_ACTION_ID,
            r'\"schema_version\":3',
            r'\"driver_evidence_schema_version\":2',
            r'\"layout_id\"',
            r'\"rois\"',
            r'\"histogram\"',
            r'\"nvs_contract\"',
            r'\"driver_fixture_guard_passed\"',
            r'\"persistent_phase\"',
        ):
            self.assertIn(token, self.main)
        driver_json = _function(
            self.main, "driverEvidenceJson", "publishNoExecuteReport"
        )
        for field in (
            "failureStage",
            "failureCode",
            "inputFrameFnv1a",
            "cs1DtmFnv1a",
            "cs2DtmFnv1a",
            "safeFinishBusyBeforePinsLow",
            "finalBusyLevel",
            "finalRstLevel",
            "finalCs1Level",
            "finalCs2Level",
        ):
            self.assertIn(field, driver_json)

    @unittest.skipUnless(
        os.environ.get("MF1750_REQUIRE_BUILT_EC5_COMPARE_ARTIFACTS") == "1",
        "set after a clean comparison build",
    )
    def test_clean_built_artifacts_bind_only_the_diagonal_identity(self) -> None:
        build = (
            REPO_ROOT
            / ".pio/build/esp32-s3-devkitc-1-ec5-u04-u05-compare"
        )
        elf = (build / "firmware.elf").read_bytes()
        binary = (build / "firmware.bin").read_bytes()
        for payload in (elf, binary):
            self.assertIn(identity.BUILD_TAG.encode("ascii"), payload)
            self.assertIn(identity.TEST_ID.encode("ascii"), payload)
            self.assertIn(identity.FROZEN_ACTION_ID.encode("ascii"), payload)
            self.assertNotIn(OBSOLETE_HORIZONTAL_ACTION.encode("ascii"), payload)
            self.assertNotIn(b"/api/frame\0", payload)
        for digest in (
            bytes.fromhex(identity.FRAME_SHA256),
            bytes.fromhex(identity.CS1_DTM_SHA256),
            bytes.fromhex(identity.CS2_DTM_SHA256),
        ):
            self.assertGreaterEqual(elf.count(digest), 1)
            self.assertGreaterEqual(binary.count(digest), 1)


if __name__ == "__main__":
    unittest.main()
