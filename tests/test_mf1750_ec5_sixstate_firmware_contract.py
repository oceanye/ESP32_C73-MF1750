from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest

from tools import mf1750_ec5_sixstate_nodither as assets


REPO_ROOT = Path(__file__).resolve().parents[1]


def _section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*$\n(.*?)(?=^\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing PlatformIO section: {name}")
    return match.group(1)


def _function(text: str, name: str, next_name: str) -> str:
    match = re.search(
        rf"\b{re.escape(name)}\s*\([^)]*\)\s*\{{(.*?)(?=\n[^\n]*\b{re.escape(next_name)}\s*\()",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function: {name}")
    return match.group(1)


def _fnv_hex(value: int) -> str:
    return f"0x{value:08X}UL"


class Ec5SixStateFirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ini = (REPO_ROOT / "platformio.ini").read_text(encoding="utf-8")
        cls.main = (REPO_ROOT / "src/ec5_sixstate_main.cpp").read_text(
            encoding="utf-8"
        )
        cls.driver = (REPO_ROOT / "src/epd_driver.cpp").read_text(encoding="utf-8")
        cls.header = (REPO_ROOT / "src/epd_driver.h").read_text(encoding="utf-8")

    def test_sixstate_is_isolated_from_release_n7_and_pilot(self) -> None:
        for environment in (
            "env:esp32-s3-devkitc-1",
            "env:esp32-s3-devkitc-1-n7-spi-sweep",
            "env:esp32-s3-devkitc-1-ec5-u04",
            "env:esp32-s3-devkitc-1-ec5-u07",
        ):
            self.assertIn("-<ec5_sixstate_main.cpp>", _section(self.ini, environment))

        u04 = _section(self.ini, "env:esp32-s3-devkitc-1-ec5-sixstate-u04")
        u07 = _section(self.ini, "env:esp32-s3-devkitc-1-ec5-sixstate-u07")
        for section in (u04, u07):
            self.assertIn("+<ec5_sixstate_main.cpp>", section)
            self.assertIn("+<epd_driver.cpp>", section)
            self.assertIn("-<main.cpp>", section)
            self.assertIn("-<n7_main.cpp>", section)
            self.assertIn("-<ec5_unknown_probe_main.cpp>", section)
            self.assertIn("-D MF1750_ENABLE_SIXSTATE_PROBE=1", section)
            self.assertNotIn("MF1750_ENABLE_UNKNOWN_PROBE=1", section)
        self.assertIn("-D MF1750_UNKNOWN_PROBE_CODE=4", u04)
        self.assertNotIn("MF1750_UNKNOWN_PROBE_CODE=7", u04)
        self.assertIn("-D MF1750_UNKNOWN_PROBE_CODE=7", u07)
        self.assertNotIn("MF1750_UNKNOWN_PROBE_CODE=4", u07)

    def test_driver_api_is_compile_guarded_and_does_not_weaken_six_colour_guard(self) -> None:
        self.assertRegex(
            self.header,
            r"#ifndef MF1750_ENABLE_SIXSTATE_PROBE\s+"
            r"#define MF1750_ENABLE_SIXSTATE_PROBE 0",
        )
        self.assertIn("MF1750_ENABLE_UNKNOWN_PROBE && MF1750_ENABLE_SIXSTATE_PROBE", self.header)
        self.assertIn("bool epdValidateCompiledSixStateFixtures();", self.header)
        self.assertIn("bool epdDisplayCompiledSixState(EpdSixStateRole role);", self.header)
        self.assertIn("#if MF1750_ENABLE_SIXSTATE_PROBE", self.driver)
        for known in (
            "EPD_COLOR_BLACK",
            "EPD_COLOR_WHITE",
            "EPD_COLOR_YELLOW",
            "EPD_COLOR_RED",
            "EPD_COLOR_BLUE",
            "EPD_COLOR_GREEN",
        ):
            self.assertIn(f"case {known}:", self.driver)
        validator = _function(self.driver, "epdValidateFrameColors", "epdBegin")
        self.assertIn("epdIsSupportedColorCode(high)", validator)
        self.assertIn("epdIsSupportedColorCode(low)", validator)
        self.assertNotIn("SIXSTATE_CANDIDATE", validator)

    def test_asset_geometry_hashes_histograms_and_mapping_are_literal(self) -> None:
        for token in (
            '"EC5_SIXSTATE_MIRROR24_NODITHER_V1"',
            "SIXSTATE_ROI_SIDE = 24",
            "SIXSTATE_LEFT_X0 = 244",
            "SIXSTATE_RIGHT_X0 = 756",
            "{48, 144, 240, 336, 432, 528}",
            "SIXSTATE_ROI_COUNT = 12",
            "SIXSTATE_TARGET_PIXELS",
            "EPD_CS1_SOURCE_HALF == 0",
            "EPD_CS2_SOURCE_HALF == 1",
        ):
            self.assertIn(token, self.driver + self.main)

        for candidate in assets.CANDIDATES:
            for role in ("primer", "target"):
                identity = assets.FROZEN_IDENTITIES[candidate][role]
                for sha256, fnv in identity.values():
                    self.assertIn(f'"{sha256}"', self.main + self.driver)
                    self.assertIn(_fnv_hex(fnv), self.main + self.driver)
            histogram = assets.FROZEN_HISTOGRAMS[candidate]["target"]
            self.assertEqual(histogram[candidate], assets.CANDIDATE_PIXELS)

        for validation_token in (
            "sixStateExpectedPixel",
            "std::memcmp(histogram, identity->histogram",
            "fnv1a(frame, EPD_FRAME_BYTES)",
            "sixStateShaMatches(frame, EPD_FRAME_BYTES",
            "sixStateDtmMatches(frame, false",
            "sixStateDtmMatches(frame, true",
        ):
            self.assertIn(validation_token, self.driver)

    def test_exact_nine_action_ids_match_frozen_derivation(self) -> None:
        for candidate in assets.CANDIDATES:
            build = (
                f"MF1750_EC5_SIXSTATE_U0{candidate}_MIRROR24_NODITHER_V1_2026-08-09"
            )
            test_id = f"EC5-SIXSTATE-U0{candidate}-M24-NODITHER-V1"
            for ordinal in range(1, 10):
                role = ("primer", "target", "white")[(ordinal - 1) % 3]
                round_index = (ordinal - 1) // 3 + 1
                payload = (
                    f"{build}|{test_id}|ordinal={ordinal}|round={round_index}|"
                    f"role={role}|candidate=0x{candidate:x}"
                )
                action_id = hashlib.sha256(payload.encode("ascii")).hexdigest()
                self.assertEqual(self.main.count(f'"{action_id}"'), 1)

        self.assertIn("static constexpr const char *kActionIds[9]", self.main)
        self.assertIn("(ordinal - 1) / 3 + 1", self.main)
        self.assertIn("(ordinal - 1) % 3", self.main)

    def test_arm_execute_and_persistent_progress_precede_driver(self) -> None:
        for token in (
            '"X-EC5-Build-Tag"',
            '"X-EC5-Test-Id"',
            '"X-EC5-Action-Id"',
            '"X-EC5-Ordinal"',
            '"X-EC5-Boot-Nonce"',
            '"X-EC5-Arm-Nonce"',
            '"X-EC5-Intent"',
            "server.on(kArmRoute, HTTP_POST, handleArm)",
            "server.on(kExecuteRoute, HTTP_POST, handleExecute)",
        ):
            self.assertIn(token, self.main)

        arm = _function(self.main, "handleArm", "handleExecute")
        self.assertLess(
            arm.index("persistProgress(nextOrdinal, PendingPhase::Claimed)"),
            arm.index("deviceState = DeviceState::Armed"),
        )
        execute = _function(self.main, "handleExecute", "installRoutes")
        self.assertLess(
            execute.index("persistProgress(queuedOrdinal, PendingPhase::Consumed)"),
            execute.index("executePending = true"),
        )
        worker = _function(self.main, "executeQueuedAction", "updateCooldownState")
        self.assertLess(
            worker.index("progressStillIs(ordinal, PendingPhase::Consumed)"),
            worker.index("epdDisplayCompiledSixState(role)"),
        )
        self.assertLess(
            worker.index("epdDisplayCompiledSixState(role)"),
            worker.index("persistProgress(static_cast<uint8_t>(ordinal + 1)"),
        )
        self.assertIn("currentActionDriverCalled", worker)
        self.assertEqual(worker.count("epdDisplayCompiledSixState(role)"), 1)

    def test_claimed_or_consumed_reboot_and_any_bad_post_fail_locked(self) -> None:
        setup = _function(self.main, "setup", "loop")
        self.assertIn("pendingPhase != PendingPhase::Virgin", setup)
        self.assertIn('enterFault("pending_claim_seen_at_boot")', setup)
        self.assertIn("progressStore.getBool(kFaultLatchKey, false)", setup)
        self.assertIn('enterFault("persistent_fault_latch_seen_at_boot")', setup)
        fault = _function(self.main, "enterFault", "rejectMutation")
        self.assertIn("progressStore.putBool(kFaultLatchKey, true)", fault)
        self.assertIn("if (server.method() == HTTP_POST)", self.main)
        self.assertIn('rejectMutation(404, "unknown_mutation_route")', self.main)
        reject = _function(self.main, "rejectMutation", "sequenceJson")
        self.assertIn("enterFault(error)", reject)
        for forbidden in (
            "progressStore.clear(",
            "progressStore.remove(",
            "nvs_flash_erase",
            '"/api/ec5/sixstate/reset"',
            '"/api/ec5/sixstate/clear"',
            '"/api/frame"',
        ):
            self.assertNotIn(forbidden, self.main)

    def test_no_boot_refresh_raw_ingress_lut_retry_or_recovery(self) -> None:
        setup = _function(self.main, "setup", "loop")
        self.assertNotIn("epdDisplayCompiledSixState", setup)
        self.assertIn("epdValidateCompiledSixStateFixtures()", setup)
        for token in (
            r'\"startup_refresh\":false',
            r'\"raw_frame_ingress\":false',
            r'\"lut_modification\":false',
            r'\"retry\":false',
            r'\"recovery\":false',
            r'\"network_reset_clear_retry_recovery_routes\":false',
        ):
            self.assertIn(token, self.main)
        for forbidden in ("loadLut", "loadLUT", "loadWF", "0x20"):
            self.assertNotIn(forbidden, self.main)

    def test_cooldown_is_150_seconds_and_restarts_conservatively_after_reboot(self) -> None:
        self.assertIn("kCooldownMs = 150000UL", self.main)
        worker = _function(self.main, "executeQueuedAction", "updateCooldownState")
        self.assertIn("cooldownDeadlineMs = jobFinishedAtMs + kCooldownMs", worker)
        setup = _function(self.main, "setup", "loop")
        self.assertIn("cooldownDeadlineMs = millis() + kCooldownMs", setup)
        self.assertIn("if (nextOrdinal > kFirstOrdinal)", setup)
        arm = _function(self.main, "handleArm", "handleExecute")
        self.assertIn("!cooldownElapsed()", arm)

    def test_report_contains_complete_identity_busy_and_safe_finish_evidence(self) -> None:
        worker = _function(self.main, "executeQueuedAction", "updateCooldownState")
        for token in (
            r'\"ordinal\"',
            r'\"round\"',
            r'\"role\"',
            r'\"frame_sha256\"',
            r'\"cs1_dtm_sha256\"',
            r'\"cs2_dtm_sha256\"',
            r'\"driver_call_count_for_action\":1',
            "driverJson(driver)",
        ):
            self.assertIn(token, worker)
        driver_json = _function(self.main, "driverJson", "publishFault")
        for field in (
            "inputFrameFnv1a",
            "cs1DtmFnv1a",
            "cs2DtmFnv1a",
            "resetBusy",
            "ponBusy",
            "drfBusy",
            "pofBusy",
            "postPsrBusy",
            "safeFinishBusyBeforePinsLow",
            "safeFinishBusyAfterPinsLow",
            "safeFinishBusyAfter5Ms",
            "finalBusyLevel",
            "finalRstLevel",
            "finalCs1Level",
            "finalCs2Level",
        ):
            self.assertIn(field, driver_json)

        initial = _function(self.main, "publishNoExecuteReport", "requireReadOnly")
        for token in (
            "kBuildTag",
            "kTestId",
            "bootNonce()",
            "kCandidateCode",
            "actionIdForOrdinal(nextOrdinal)",
            r'\"terminal_state\":\"NOT_EXECUTED\"',
        ):
            self.assertIn(token, initial)
        execute = _function(self.main, "handleExecute", "installRoutes")
        for token in ("kBuildTag", "kTestId", "bootNonce()", "kCandidateCode"):
            self.assertIn(token, execute)

    def test_built_binaries_are_candidate_specific_when_present(self) -> None:
        binary_by_candidate: dict[int, bytes] = {}
        for candidate in assets.CANDIDATES:
            path = (
                REPO_ROOT
                / ".pio"
                / "build"
                / f"esp32-s3-devkitc-1-ec5-sixstate-u0{candidate}"
                / "firmware.bin"
            )
            if not path.is_file():
                self.skipTest("six-state firmware binaries have not been compiled")
            binary_by_candidate[candidate] = path.read_bytes()

        self.assertNotEqual(
            hashlib.sha256(binary_by_candidate[4]).digest(),
            hashlib.sha256(binary_by_candidate[7]).digest(),
        )
        for candidate, binary in binary_by_candidate.items():
            own = f"MF1750_EC5_SIXSTATE_U0{candidate}_MIRROR24_NODITHER_V1_2026-08-09"
            other = f"MF1750_EC5_SIXSTATE_U0{11-candidate}_MIRROR24_NODITHER_V1_2026-08-09"
            self.assertIn(own.encode("ascii"), binary)
            self.assertNotIn(other.encode("ascii"), binary)
            self.assertNotIn(b"/api/frame\0", binary)


if __name__ == "__main__":
    unittest.main()
