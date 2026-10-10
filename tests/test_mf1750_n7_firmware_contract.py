from __future__ import annotations

from pathlib import Path
import re
import unittest

from tools import mf1750_n7_spi_sweep_campaign as campaign


REPO_ROOT = Path(__file__).resolve().parents[1]


class N7FirmwareContractTests(unittest.TestCase):
    def test_frozen_n7_binary_identity_matches_archived_output_when_present(self) -> None:
        archived = (
            REPO_ROOT
            / ".test-output"
            / "hardware"
            / "MF1750_N7_SPI_SWEEP_OFFLINE_20260808_V1"
            / "firmware.bin"
        )
        build = (
            REPO_ROOT
            / ".pio"
            / "build"
            / campaign.FIRMWARE_ENVIRONMENT
            / "firmware.bin"
        )
        binary = archived if archived.is_file() else build
        if not binary.is_file():
            self.skipTest("neither archived nor current N7 output is present")
        payload = binary.read_bytes()
        self.assertEqual(len(payload), campaign.FIRMWARE_EXPECTED_BYTES)
        self.assertEqual(campaign.sha256(payload), campaign.FIRMWARE_EXPECTED_SHA256)
        self.assertIn(campaign.FIRMWARE_BUILD_TAG.encode("ascii"), payload)
        self.assertNotIn(b"/api/frame\0", payload)
        self.assertNotIn(b"MF1750_DRIVER_RC2G_", payload)

    def test_changed_current_build_is_explicitly_classified_as_not_frozen(self) -> None:
        build = (
            REPO_ROOT
            / ".pio"
            / "build"
            / campaign.FIRMWARE_ENVIRONMENT
            / "firmware.bin"
        )
        if not build.is_file():
            self.skipTest("current N7 PlatformIO output is not present")
        digest = campaign.sha256(build.read_bytes())
        if digest == campaign.FIRMWARE_EXPECTED_SHA256:
            return
        status = (REPO_ROOT / "docs/STATUS_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn(digest, status)
        self.assertIn("当前源码新 build 不替代 8 月 8 日冻结 N7 artifact", status)

    def test_default_environment_and_rc2g_identity_remain_unchanged(self) -> None:
        ini = (REPO_ROOT / "platformio.ini").read_text(encoding="utf-8")
        source = (REPO_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        n7_source = (REPO_ROOT / "src" / "n7_main.cpp").read_text(encoding="utf-8")

        self.assertIn("default_envs = esp32-s3-devkitc-1", ini)
        self.assertIn("[env:esp32-s3-devkitc-1-n7-spi-sweep]", ini)
        self.assertIn("+<main.cpp>", ini)
        self.assertIn("-<n7_main.cpp>", ini)
        self.assertIn("+<n7_main.cpp>", ini)
        self.assertIn("-<main.cpp>", ini)
        self.assertIn(
            "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
            "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07",
            source,
        )
        self.assertNotIn(campaign.FIRMWARE_BUILD_TAG, source)
        self.assertIn(campaign.FIRMWARE_BUILD_TAG, n7_source)

    def test_n7_has_exactly_five_fixed_post_routes_and_no_frequency_argument(self) -> None:
        source = (REPO_ROOT / "src" / "n7_main.cpp").read_text(encoding="utf-8")
        routes = re.findall(r'server\.on\("([^"]+)",\s*HTTP_POST', source)

        self.assertEqual(routes, [campaign.ROUTES[frequency] for frequency in campaign.FREQUENCIES])
        self.assertNotIn('server.on("/api/frame"', source)
        self.assertIn("server.args() != 0", source)
        self.assertIn('server.hasArg("plain")', source)
        self.assertIn("n7_sweep_arguments_forbidden", source)

    def test_each_route_maps_to_one_compile_time_frequency(self) -> None:
        source = (REPO_ROOT / "src" / "n7_main.cpp").read_text(encoding="utf-8")
        constants = re.findall(
            r"N7_SPI_SWEEP_(1|2|4|8|10)MHZ\s*=\s*(\d+)UL", source
        )
        self.assertEqual(
            constants,
            [(str(frequency // 1_000_000), str(frequency)) for frequency in campaign.FREQUENCIES],
        )
        for mhz in (1, 2, 4, 8, 10):
            self.assertEqual(
                source.count(f"queueN7SpiSweepAndRespond(N7_SPI_SWEEP_{mhz}MHZ)"),
                1,
            )
        self.assertEqual(source.count("drawAndDisplayMapOrientV1(spiHz)"), 1)
        self.assertIn('"map_orient_v1_sweep"', source)


if __name__ == "__main__":
    unittest.main()
