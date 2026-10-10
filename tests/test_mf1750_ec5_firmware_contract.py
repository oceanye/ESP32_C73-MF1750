from __future__ import annotations

import os
from pathlib import Path
import re
import unittest


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


def _function(text: str, name: str, next_name: str | None = None) -> str:
    suffix = rf"(?=\n[^\n]*\b{next_name}\s*\()" if next_name else r"\Z"
    match = re.search(
        rf"\b{re.escape(name)}\s*\([^)]*\)\s*\{{(.*?){suffix}",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function: {name}")
    return match.group(1)


def _cpp_byte_arrays(text: str, name: str) -> list[bytes]:
    bodies = re.findall(
        rf"static constexpr uint8_t {re.escape(name)}\[32\]\s*=\s*\{{(.*?)\}};",
        text,
        flags=re.DOTALL,
    )
    arrays: list[bytes] = []
    for body in bodies:
        values = [int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", body)]
        if len(values) != 32:
            raise AssertionError(f"{name} does not contain exactly 32 bytes")
        arrays.append(bytes(values))
    return arrays


class Ec5FirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.platformio = (REPO_ROOT / "platformio.ini").read_text(encoding="utf-8")
        cls.main = (REPO_ROOT / "src/ec5_unknown_probe_main.cpp").read_text(
            encoding="utf-8"
        )
        cls.driver_header = (REPO_ROOT / "src/epd_driver.h").read_text(
            encoding="utf-8"
        )
        cls.driver = (REPO_ROOT / "src/epd_driver.cpp").read_text(encoding="utf-8")
        cls.physical_once = (
            REPO_ROOT / "tools/mf1750_ec5_physical_once.py"
        ).read_text(encoding="utf-8")
        cls.release_tool = (REPO_ROOT / "tools/mf1750_ec5_release.py").read_text(
            encoding="utf-8"
        )
        cls.stage_a_identity = (
            REPO_ROOT / "tools/mf1750_ec5_stage_a_v2_identity.py"
        ).read_text(encoding="utf-8")

    def test_release_and_n7_exclude_ec5_source(self) -> None:
        release = _section(self.platformio, "env:esp32-s3-devkitc-1")
        n7 = _section(self.platformio, "env:esp32-s3-devkitc-1-n7-spi-sweep")
        self.assertIn("-<ec5_unknown_probe_main.cpp>", release)
        self.assertIn("-D EPD_ENABLE_TEST_PATTERN=0", release)
        self.assertIn("-<ec5_unknown_probe_main.cpp>", n7)
        self.assertNotIn("MF1750_ENABLE_UNKNOWN_PROBE=1", release)
        self.assertRegex(
            self.driver_header,
            r"#ifndef MF1750_ENABLE_UNKNOWN_PROBE\s+"
            r"#define MF1750_ENABLE_UNKNOWN_PROBE 0",
        )

    def test_u04_and_u07_are_separate_compile_time_candidates(self) -> None:
        u04 = _section(self.platformio, "env:esp32-s3-devkitc-1-ec5-u04")
        u07 = _section(self.platformio, "env:esp32-s3-devkitc-1-ec5-u07")
        for section in (u04, u07):
            self.assertIn("+<ec5_unknown_probe_main.cpp>", section)
            self.assertIn("-<main.cpp>", section)
            self.assertIn("-<n7_main.cpp>", section)
            self.assertIn("-D MF1750_ENABLE_UNKNOWN_PROBE=1", section)
        self.assertIn("-D MF1750_UNKNOWN_PROBE_CODE=4", u04)
        self.assertNotIn("MF1750_UNKNOWN_PROBE_CODE=7", u04)
        self.assertIn("-D MF1750_UNKNOWN_PROBE_CODE=7", u07)
        self.assertNotIn("MF1750_UNKNOWN_PROBE_CODE=4", u07)

        for token in (
            'static constexpr const char *kLegacyClaimKey = "u04_phase";',
            'static constexpr const char *kActiveClaimKey = "u04v2_phase";',
            'static constexpr const char *kLegacyClaimKey = "u07_phase";',
            'static constexpr const char *kActiveClaimKey = "u07v2_phase";',
            "MF1750_EC5_U04_MIRROR64_CENTER_V2_CORRECTED_2026-08-09",
            "MF1750_EC5_U07_MIRROR64_CENTER_V2_CORRECTED_2026-08-09",
            "EC5-U04-I02-P01-L64M1",
            "EC5-U07-I02-P01-L64M1",
            "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3",
            "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae",
        ):
            self.assertEqual(self.main.count(token), 1)

        for stale_v1_identity in (
            "MF1750_EC5_U04_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
            "MF1750_EC5_U07_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
            "EC5-U04-I01-P01-L64M1",
            "EC5-U07-I01-P01-L64M1",
            "bf2fcbcb29a35cf0a7915c67b48468aca26f7a35aef20e9ff68c9d60a37d0df5",
            "8568ba9cb5dd933d8c1f9a4028fffbd27f37aacf2017cb92f27c423b5cfa48e4",
        ):
            self.assertNotIn(stale_v1_identity, self.main)

    def test_no_startup_refresh_raw_ingress_retry_or_recovery(self) -> None:
        self.assertIn('#error "EC5 must never refresh during boot"', self.main)
        for token in (
            r'\"automatic_execute\":false',
            r'\"startup_refresh\":false',
            r'\"raw_frame_ingress\":false',
            r'\"retry\":false',
            r'\"recovery\":false',
        ):
            self.assertIn(token, self.main)
        for forbidden in ('"/api/frame"', '"/api/ec5/reset"', '"/api/ec5/clear"'):
            self.assertNotIn(forbidden, self.main)

        setup = _function(self.main, "setup", "loop")
        self.assertNotIn("epdDisplayCompiledUnknownProbe", setup)
        self.assertEqual(self.main.count("epdDisplayCompiledUnknownProbe()"), 1)

    def test_exact_two_stage_request_contract_is_frozen(self) -> None:
        self.assertEqual(
            self.main.count("server.on(kArmRoute, HTTP_POST, handleArm)"), 1
        )
        self.assertEqual(
            self.main.count("server.on(kExecuteRoute, HTTP_POST, handleExecute)"),
            1,
        )
        for token in (
            '"X-EC5-Build-Tag"',
            '"X-EC5-Test-Id"',
            '"X-EC5-Action-Id"',
            '"X-EC5-Boot-Nonce"',
            '"X-EC5-Arm-Nonce"',
            '"X-EC5-Intent"',
            "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION",
            "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION",
            "accidental_post_interlock_not_hardware_authorization",
            "case ProbeState::Armed:",
        ):
            self.assertIn(token, self.main)

        validator = _function(self.main, "validateIdentityContract", "versionJson")
        for exact_identity in (
            "kBuildHeader",
            "kBuildTag",
            "kTestHeader",
            "kTestId",
            "kActionHeader",
            "kActionId",
            "kBootNonceHeader",
            "bootNonce()",
            "kIntentHeader",
            "expectedIntent",
        ):
            self.assertIn(exact_identity, validator)
        execute = _function(self.main, "handleExecute", "installRoutes")
        self.assertIn("exactHeader(kArmNonceHeader, armNonce())", execute)
        self.assertIn("validateIdentityContract(kExecuteIntent)", execute)
        arm = _function(self.main, "handleArm", "handleExecute")
        self.assertIn("validateIdentityContract(kArmIntent)", arm)

    def test_corrected_v2_nvs_migration_is_read_only_then_active_only(self) -> None:
        self.assertIn("#include <Preferences.h>", self.main)
        for token in (
            "Preferences legacyClaimStore;",
            "Preferences activeClaimStore;",
            'kLegacyClaimNamespace = "mf1750_ec5"',
            'kActiveClaimNamespace = "mf1750_ec5v2"',
            'kLegacyClaimKey = "u04_phase"',
            'kLegacyClaimKey = "u07_phase"',
            'kActiveClaimKey = "u04v2_phase"',
            'kActiveClaimKey = "u07v2_phase"',
            "kLegacyExpectedPresent = true",
            "kLegacyExpectedPresent = false",
            "kLegacyExpectedPhase = 2",
            "kLegacyExpectedPhase = 0",
        ):
            self.assertIn(token, self.main)
        for definition in (
            "kPersistentVirgin = 0",
            "kPersistentClaimed = 1",
            "kPersistentConsumed = 2",
            "kPersistentFault = 3",
        ):
            self.assertIn(definition, self.main)
        self.assertNotRegex(
            self.main,
            r"legacyClaimStore\.(?:put\w*|clear|remove)\s*\(",
        )
        self.assertEqual(
            re.findall(r"\b(\w+)\.putUChar\(([^)]*)\)", self.main),
            [("activeClaimStore", "kActiveClaimKey, phase")],
        )
        self.assertIn(
            "legacyClaimStore.getUChar(kLegacyClaimKey, kPersistentVirgin)",
            self.main,
        )
        self.assertIn(
            "activeClaimStore.getUChar(kActiveClaimKey, kPersistentVirgin)",
            self.main,
        )

        setup = _function(self.main, "setup", "loop")
        ordered_boot_steps = (
            "epdValidateCompiledUnknownProbeFixture()",
            "legacyClaimStore.begin(kLegacyClaimNamespace, true /* readOnly */)",
            "legacyClaimStore.getUChar(kLegacyClaimKey, kPersistentVirgin)",
            "activeClaimStore.begin(kActiveClaimNamespace, false /* readOnly */)",
            "refreshNvsEvidence()",
            "bootMigrationValidated = migrationReady",
            "!legacyMatch",
            "!activeVirgin",
            "epdBegin()",
        )
        positions = [setup.index(token) for token in ordered_boot_steps]
        self.assertEqual(positions, sorted(positions))
        for error in (
            'enterReadOnlyFault("compiled_fixture_self_check_failed")',
            'enterReadOnlyFault("legacy_claim_store_open_failed")',
            'enterReadOnlyFault("active_claim_store_open_failed")',
            'enterReadOnlyFault("legacy_migration_mismatch")',
            'enterReadOnlyFault("active_v2_not_virgin")',
        ):
            self.assertIn(error, setup)
        self.assertNotIn("enterPersistentFault(", setup)

        arm = _function(self.main, "handleArm", "handleExecute")
        self.assertLess(arm.index("refreshNvsEvidence()"), arm.index("legacyMatch"))
        self.assertIn("!migrationReady || !legacyMatch || !activeVirgin", arm)
        self.assertLess(
            arm.index("persistPhase(kPersistentClaimed)"),
            arm.index("probeState = ProbeState::Armed"),
        )
        execute = _function(self.main, "handleExecute", "installRoutes")
        self.assertLess(
            execute.index("refreshNvsEvidence()"), execute.index("legacyMatch")
        )
        self.assertIn("!migrationReady || !legacyMatch || !activeKeyPresent", execute)
        self.assertLess(
            execute.index("persistPhase(kPersistentConsumed)"),
            execute.index("executePending = true"),
        )
        worker = _function(self.main, "executePendingProbe", "setup")
        self.assertLess(
            worker.index("persistentPhaseIs(kPersistentConsumed)"),
            worker.index("epdDisplayCompiledUnknownProbe()"),
        )
        self.assertIn(
            'enterReadOnlyFault("runtime_claim_readback_failed")', worker
        )

    def test_malformed_stale_duplicate_and_unknown_posts_fail_closed(self) -> None:
        for error in (
            "body_or_arguments_forbidden",
            "build_tag_missing_or_mismatch",
            "test_id_missing_or_mismatch",
            "action_id_missing_or_mismatch",
            "boot_nonce_missing_or_stale",
            "intent_missing_or_mismatch",
            "arm_nonce_missing_or_stale",
            "arm_duplicate_or_not_virgin",
            "execute_duplicate_stale_or_not_armed",
            "unknown_mutation_route",
        ):
            self.assertIn(error, self.main)

        reject = _function(self.main, "rejectMutation", "handleArm")
        self.assertIn("enterPersistentFault(error)", reject)
        self.assertIn("enterReadOnlyFault(error)", reject)
        self.assertIn("!bootMigrationValidated", reject)
        self.assertIn("!migrationReady", reject)
        fault = _function(self.main, "enterPersistentFault", "enterReadOnlyFault")
        self.assertIn("persistPhase(kPersistentFault)", fault)
        self.assertIn("probeState = ProbeState::FaultLocked", fault)
        read_only_fault = _function(
            self.main, "enterReadOnlyFault", "rejectMutation"
        )
        self.assertNotIn("persistPhase(", read_only_fault)
        self.assertNotIn("putUChar(", read_only_fault)
        self.assertIn("probeState = ProbeState::FaultLocked", read_only_fault)
        self.assertIn("if (server.method() == HTTP_POST)", self.main)

        # A network client can only move the state forward; it cannot erase NVS.
        for forbidden in (
            "legacyClaimStore.clear(",
            "legacyClaimStore.remove(",
            "activeClaimStore.clear(",
            "activeClaimStore.remove(",
            "nvs_flash_erase",
        ):
            self.assertNotIn(forbidden, self.main)

    def test_manifest_and_status_publish_host_verification_fields(self) -> None:
        for token in (
            'kDeviceApiVersion = "MF1750_EC5_DEVICE_V3"',
            'kIdentityRevision = "corrected-v2"',
            r'\"schema_version\":3',
            r'\"device_api_version\"',
            r'\"identity_revision\"',
            r'\"build_tag\":\"',
            r'\"action_id\":\"',
            r'\"mutation_contract\"',
            r'\"exact_build_test_action_boot_nonce\":true',
            r'\"arm_nonce_required_for_execute\":true',
            r'\"not_hardware_authorization\":true',
            r'\"claim_store_ready\"',
            r'\"persistent_phase\"',
            r'\"arm_request_count\"',
            r'\"execute_request_count\"',
            r'\"driver_fixture_guard_passed\"',
            r'\"nvs_contract\"',
            r'\"legacy_key_present\"',
            r'\"legacy_phase\"',
            r'\"legacy_match\"',
            r'\"active_key_present\"',
            r'\"active_phase\"',
            r'\"active_virgin\"',
            r'\"migration_ready\"',
        ):
            self.assertIn(token, self.main)
        self.assertNotIn(r'\"schema_version\":1', self.main)
        self.assertNotIn('kDeviceApiVersion = "MF1750_EC5_DEVICE_V2"', self.main)

        nvs_contract = _function(self.main, "nvsContractJson", "nvsEvidenceJson")
        for token in (
            "kLegacyClaimNamespace",
            "kLegacyClaimKey",
            "kLegacyExpectedPresent",
            "kLegacyExpectedPhase",
            r'\"read_only\":true',
            "kActiveClaimNamespace",
            "kActiveClaimKey",
            r'\"expected_present\":false',
            r'\"expected_phase\":0',
            r'\"read_only\":false',
        ):
            self.assertIn(token, nvs_contract)
        nvs_evidence = _function(self.main, "nvsEvidenceJson", "requestHasBodyOrArguments")
        for token in (
            "legacyKeyPresent",
            "legacyPhase",
            "legacyMatch",
            "activeKeyPresent",
            "activePhase",
            "activeVirgin",
            "migrationReady",
        ):
            self.assertIn(token, nvs_evidence)

        status = _function(self.main, "statusJson", "driverEvidenceJson")
        for token in ("bootNonce()", "kBuildTag", "kTestId", "kActionId"):
            self.assertIn(token, status)
        report = _function(self.main, "executePendingProbe", "setup")
        for token in (
            "kBuildTag",
            "kTestId",
            "kActionId",
            "bootNonce()",
            "kCandidateCode",
            r'\"driver_call_count\":1',
            r'\"persistent_phase\":2',
            "driverEvidenceJson(driver)",
        ):
            self.assertIn(token, report)
        for endpoint in (
            _function(self.main, "manifestJson", "gpioJson"),
            status,
            report,
            _function(
                self.main, "publishNoExecuteReport", "publishRejectedMutation"
            ),
            _function(
                self.main, "publishRejectedMutation", "enterPersistentFault"
            ),
        ):
            self.assertIn("kIdentityRevision", endpoint)
            self.assertIn("nvsContractJson()", endpoint)
            self.assertIn("nvsEvidenceJson()", endpoint)
        initial_report = _function(
            self.main, "publishNoExecuteReport", "publishRejectedMutation"
        )
        for token in (
            "kBuildTag",
            "kTestId",
            "kActionId",
            "bootNonce()",
            "kCandidateCode",
            r'\"terminal_state\":\"NOT_EXECUTED\"',
        ):
            self.assertIn(token, initial_report)
        driver = _function(self.main, "driverEvidenceJson", "publishNoExecuteReport")
        for token in (
            "inputFrameFnv1a",
            "cs1DtmFnv1a",
            "cs2DtmFnv1a",
            "sequenceOk",
            "ponBusySeen",
            "drfBusySeen",
            "pofBusySeen",
            "safeFinishBusyBeforePinsLow",
            "finalBusyLevel",
        ):
            self.assertIn(token, driver)

    def test_fixture_identities_are_frozen_for_both_candidates(self) -> None:
        expected = (
            "EC5-U04-I02-P01-L64M1",
            "EC5-U07-I02-P01-L64M1",
            "MF1750_EC5_U04_MIRROR64_CENTER_V2_CORRECTED_2026-08-09",
            "MF1750_EC5_U07_MIRROR64_CENTER_V2_CORRECTED_2026-08-09",
            "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3",
            "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae",
            "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e",
            "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
            "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
            "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        )
        for token in expected:
            self.assertEqual(self.main.count(token), 1)

    def test_compiled_digest_bytes_match_manifest_and_host_byte_for_byte(self) -> None:
        expected_frame = [
            "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e",
            "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
        ]
        expected_dtm = [
            "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
            "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        ]
        self.assertEqual(
            [value.hex() for value in _cpp_byte_arrays(self.driver, "EC5_FRAME_SHA256")],
            expected_frame,
        )
        self.assertEqual(
            [value.hex() for value in _cpp_byte_arrays(self.driver, "EC5_DTM_SHA256")],
            expected_dtm,
        )
        for candidate in ("U04", "U07"):
            self.assertIn(
                f'"{candidate} compiled DTM SHA-256 bytes differ from the frozen host identity"',
                self.driver,
            )
        self.assertEqual(
            re.findall(
                r'kFrameSha256\s*=\s*\n?\s*"([0-9a-f]{64})";', self.main
            ),
            expected_frame,
        )
        self.assertEqual(
            re.findall(r'kDtmSha256\s*=\s*\n?\s*"([0-9a-f]{64})";', self.main),
            expected_dtm,
        )
        for digest in (*expected_frame, *expected_dtm):
            self.assertIn(digest, self.stage_a_identity)
        self.assertIn("stage_a_v2_identity as stage_a_identity", self.physical_once)
        self.assertIn("mf1750_ec5_stage_a_v2_identity", self.release_tool)

    @unittest.skipUnless(
        os.environ.get("MF1750_REQUIRE_BUILT_EC5_ARTIFACTS") == "1",
        "set MF1750_REQUIRE_BUILT_EC5_ARTIFACTS=1 after clean U04/U07 builds",
    )
    def test_built_elf_and_bin_contain_only_the_selected_raw_dtm_digest(self) -> None:
        expected = {
            "U04": (
                "esp32-s3-devkitc-1-ec5-u04",
                bytes.fromhex(
                    "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00"
                ),
            ),
            "U07": (
                "esp32-s3-devkitc-1-ec5-u07",
                bytes.fromhex(
                    "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac"
                ),
            ),
        }
        old_u04_nibble_shift = bytes.fromhex(
            "a8056cdd450f70709ec75a0a0400dfbfb1f06000ae596420902156bec7bab00d"
        )
        for candidate, (environment, selected_digest) in expected.items():
            other_digest = expected["U07" if candidate == "U04" else "U04"][1]
            for filename in ("firmware.elf", "firmware.bin"):
                artifact = REPO_ROOT / ".pio" / "build" / environment / filename
                self.assertTrue(artifact.is_file(), f"missing built artifact: {artifact}")
                payload = artifact.read_bytes()
                self.assertGreaterEqual(payload.count(selected_digest), 1)
                self.assertEqual(payload.count(other_digest), 0)
                self.assertEqual(payload.count(old_u04_nibble_shift), 0)
                self.assertEqual(payload.count(b"MF1750_EC5_DEVICE_V3"), 1)

    def test_exact_driver_guard_is_shared_by_boot_and_action_without_panel_io(self) -> None:
        setup = _function(self.main, "setup", "loop")
        self.assertIn(
            "driverFixtureGuardPassed = epdValidateCompiledUnknownProbeFixture()",
            setup,
        )
        self.assertIn("fixtureSelfCheckPassed = driverFixtureGuardPassed", setup)
        self.assertNotIn("generateAndValidateFixture", self.main)
        self.assertLess(
            setup.index("epdValidateCompiledUnknownProbeFixture()"),
            setup.index("epdBegin()"),
        )

        guard = _function(
            self.driver,
            "epdValidateCompiledUnknownProbeFixture",
            "epdDisplayCompiledUnknownProbe",
        )
        self.assertIn("ec5ValidateFixture(frame, &validation)", guard)
        for forbidden in (
            "epdBegin(",
            "epdPrepareCascade(",
            "epdCommand(",
            "epdData(",
            "epdStartHardwareSpi(",
            "digitalWrite(",
        ):
            self.assertNotIn(forbidden, guard)

        action = _function(self.driver, "epdDisplayCompiledUnknownProbe")
        self.assertIn("ec5ValidateFixture(frame, &validation)", action)
        self.assertLess(
            action.index("ec5ValidateFixture(frame, &validation)"),
            action.index("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)"),
        )
        for published in (
            r'\"boot_fixture_guard\":\"exact_driver_action_validator\"',
            r'\"exact_driver_fixture_guard_required\":true',
            r'\"driver_fixture_guard_passed\"',
        ):
            self.assertIn(published, self.main)

    def test_pre_panel_failures_are_typed_and_use_one_safe_finish(self) -> None:
        for field in (
            'char failureStage[32] = "none";',
            "int32_t failureCode = 0;",
            "uint32_t freePsramBefore = 0;",
            "uint32_t largestPsramBlockBefore = 0;",
        ):
            self.assertIn(field, self.driver_header)

        for stage in (
            "allocation",
            "frame_build",
            "full_sha",
            "cs1_compute",
            "cs2_compute",
            "cs1_identity",
            "cs2_identity",
            "cascade_prepare",
            "stream_identity",
            "refresh_sequence",
        ):
            self.assertEqual(self.driver.count(f'EC5_FAILURE_{stage.upper()} = "{stage}"'), 1)

        validation = _function(
            self.driver, "ec5ValidateFixture", "epdValidateCompiledUnknownProbeFixture"
        )
        for constant in (
            "EC5_FAILURE_FRAME_BUILD",
            "EC5_FAILURE_FULL_SHA",
            "EC5_FAILURE_CS1_COMPUTE",
            "EC5_FAILURE_CS2_COMPUTE",
            "EC5_FAILURE_CS1_IDENTITY",
            "EC5_FAILURE_CS2_IDENTITY",
        ):
            self.assertIn(f"validation->failureStage = {constant}", validation)

        action = _function(self.driver, "epdDisplayCompiledUnknownProbe")
        self.assertIn(
            "epdRejectBeforePanelIo(started, EC5_FAILURE_ALLOCATION)", action
        )
        self.assertIn(
            "epdRejectBeforePanelIo(started, validation.failureStage", action
        )
        safe_finish = _function(
            self.driver, "epdFinishFailedOperationSafe", "epdRejectBeforePanelIo"
        )
        for required in (
            "epdRecordFailure(failureStage, failureCode)",
            "epdStopHardwareSpi()",
            "epdHoldPanelPinsLow()",
            "safeFinishBusyBeforePinsLow",
            "safeFinishBusyAfterPinsLow",
            "safeFinishBusyAfter5Ms",
        ):
            self.assertIn(required, safe_finish)
        for forbidden in ("epdCommand(", "epdData(", "epdReset("):
            self.assertNotIn(forbidden, safe_finish)
        pre_panel_wrapper = _function(
            self.driver, "epdRejectBeforePanelIo", "epdWrite9"
        )
        self.assertIn("epdFinishFailedOperationSafe", pre_panel_wrapper)
        for forbidden in ("epdCommand(", "epdData(", "epdReset("):
            self.assertNotIn(forbidden, pre_panel_wrapper)

        driver_json = _function(
            self.main, "driverEvidenceJson", "publishNoExecuteReport"
        )
        self.assertIn(r'\"driver_evidence_schema_version\":2', driver_json)
        for field in (
            "failureStage",
            "failureCode",
            "freePsramBefore",
            "largestPsramBlockBefore",
        ):
            self.assertIn(field, driver_json)


if __name__ == "__main__":
    unittest.main()
