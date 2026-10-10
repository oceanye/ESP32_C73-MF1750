from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import mf1750_n7_spi_sweep_campaign as campaign


def fake_firmware() -> bytes:
    return b"n7-test-prefix\0" + campaign.FIRMWARE_BUILD_TAG.encode("ascii") + b"\0suffix"


class N7SweepCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        firmware = fake_firmware()
        self.bytes_patch = mock.patch.object(
            campaign, "FIRMWARE_EXPECTED_BYTES", len(firmware)
        )
        self.sha_patch = mock.patch.object(
            campaign, "FIRMWARE_EXPECTED_SHA256", campaign.sha256(firmware)
        )
        self.bytes_patch.start()
        self.sha_patch.start()

    def tearDown(self) -> None:
        self.sha_patch.stop()
        self.bytes_patch.stop()

    def test_manifest_freezes_only_five_ordered_actions(self) -> None:
        document = campaign.build_campaign(
            fake_firmware(), created_at_utc="2026-08-07T12:00:00Z"
        )

        self.assertEqual(
            [action["frequency_hz"] for action in document["actions"]],
            list(campaign.FREQUENCIES),
        )
        self.assertEqual(
            [action["endpoint"] for action in document["actions"]],
            [campaign.ROUTES[frequency] for frequency in campaign.FREQUENCIES],
        )
        self.assertFalse(document["firmware"]["ordinary_frame_route_registered"])
        self.assertFalse(document["firmware"]["arbitrary_frequency_route_registered"])
        self.assertTrue(document["execution_contract"]["first_failure_stops_campaign"])
        self.assertFalse(document["execution_contract"]["automatic_retry"])
        self.assertFalse(document["execution_contract"]["automatic_recovery"])
        self.assertNotIn("AUTHORIZE_", campaign.canonical_json(document).decode("utf-8"))

    def test_each_action_is_a_fixed_single_post_and_hash_bound(self) -> None:
        document = campaign.build_campaign(
            fake_firmware(), created_at_utc="2026-08-07T12:00:00Z"
        )

        for index, action in enumerate(document["actions"]):
            self.assertEqual(action["method"], "POST")
            self.assertEqual(action["request_body"], "none")
            self.assertFalse(action["query_or_form_arguments_allowed"])
            self.assertEqual(action["maximum_visible_posts"], 1)
            self.assertEqual(action["visible_action_count"], 1)
            self.assertEqual(
                action["template_sha256"],
                campaign.sha256(
                    campaign.canonical_json(
                        {key: value for key, value in action.items() if key != "template_sha256"}
                    )
                ),
            )
            if index == 0:
                self.assertEqual(action["predecessor"]["kind"], "fresh-n7-firmware-boot")
            else:
                self.assertEqual(
                    action["predecessor"]["frequency_hz"],
                    campaign.FREQUENCIES[index - 1],
                )
                self.assertTrue(action["predecessor"]["esp32_reboot_forbidden"])

    def test_write_and_deep_validate_canonical_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "campaign"
            written = campaign.write_campaign_directory(
                destination,
                fake_firmware(),
                created_at_utc="2026-08-07T12:00:00Z",
            )

            validated = campaign.validate_campaign_directory(destination)
            self.assertEqual(validated, written)
            self.assertEqual(
                {path.name for path in destination.iterdir()}, campaign.REQUIRED_FILES
            )
            self.assertEqual(
                (destination / "campaign.json").read_bytes(),
                campaign.canonical_json(written) + b"\n",
            )

    def test_binary_tag_checksum_extra_file_and_manifest_tampering_fail_closed(self) -> None:
        mutators = {
            "binary": lambda root: (root / "firmware.bin").write_bytes(b"changed"),
            "checksum": lambda root: (root / "SHA256SUMS.txt").write_text(
                "0" * 64 + "  campaign.json\n", encoding="ascii"
            ),
            "extra": lambda root: (root / "extra.txt").write_text("x", encoding="utf-8"),
            "manifest": self._tamper_manifest,
        }
        for label, mutate in mutators.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "campaign"
                campaign.write_campaign_directory(
                    destination,
                    fake_firmware(),
                    created_at_utc="2026-08-07T12:00:00Z",
                )
                mutate(destination)
                with self.assertRaises(campaign.N7CampaignError):
                    campaign.validate_campaign_directory(destination)

    @staticmethod
    def _tamper_manifest(root: Path) -> None:
        path = root / "campaign.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(document)
        changed["actions"][2]["frequency_hz"] = 3_000_000
        payload = campaign.canonical_json(changed) + b"\n"
        path.write_bytes(payload)
        firmware = (root / "firmware.bin").read_bytes()
        (root / "SHA256SUMS.txt").write_bytes(
            campaign._checksum_payload(payload, firmware)
        )

    def test_compiler_rejects_non_n7_binary_and_implicit_timestamp(self) -> None:
        with self.assertRaisesRegex(campaign.N7CampaignError, "build tag"):
            campaign.build_campaign(b"ordinary-firmware", created_at_utc="2026-08-07T12:00:00Z")
        with self.assertRaisesRegex(campaign.N7CampaignError, "ending in Z"):
            campaign.build_campaign(fake_firmware(), created_at_utc="2026-08-07T12:00:00")

    def test_compiler_rejects_tagged_but_non_frozen_binary(self) -> None:
        with self.assertRaisesRegex(campaign.N7CampaignError, "bytes/SHA-256"):
            campaign.build_campaign(
                fake_firmware() + b"changed",
                created_at_utc="2026-08-07T12:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
