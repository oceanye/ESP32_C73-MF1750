from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import canonical_json_bytes
from tools import mf1750_n7_physical_campaign as physical
from tools import mf1750_n7_spi_sweep_campaign as frozen
from tests.test_mf1750_n7_spi_sweep_campaign import fake_firmware


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-M009F-BARCODE-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}


class N7PhysicalCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        firmware = fake_firmware()
        self.bytes_patch = mock.patch.object(
            frozen, "FIRMWARE_EXPECTED_BYTES", len(firmware)
        )
        self.sha_patch = mock.patch.object(
            frozen, "FIRMWARE_EXPECTED_SHA256", frozen.sha256(firmware)
        )
        self.bytes_patch.start()
        self.sha_patch.start()
        self.source = self.root / "source"
        frozen.write_campaign_directory(
            self.source,
            firmware,
            created_at_utc="2026-08-08T00:00:00Z",
        )
        self.panel = self.root / "panel.json"
        self.panel.write_bytes(canonical_json_bytes(PANEL))
        self.review = self.root / "binding-review.bin"
        self.review.write_bytes(b"reviewed physical N7 panel binding\n")

    def tearDown(self) -> None:
        self.sha_patch.stop()
        self.bytes_patch.stop()
        self.temporary.cleanup()

    def compile(self, **overrides: object) -> dict[str, object]:
        arguments = {
            "minimum_interval_seconds": 150,
            "planned_cooldown_seconds": 150,
            **overrides,
        }
        return physical.compile_physical_manifest(
            self.source,
            self.panel,
            self.review,
            **arguments,
        )

    def test_exact_five_actions_bind_panel_firmware_schedule_and_driver_cold(self) -> None:
        manifest = self.compile()
        campaign = manifest["physical_campaign"]
        self.assertEqual(campaign["panel"], PANEL)
        self.assertEqual(
            campaign["firmware"]["binary_sha256"], frozen.FIRMWARE_EXPECTED_SHA256
        )
        self.assertEqual(
            [action["identity"]["request"]["endpoint"] for action in campaign["actions"]],
            [frozen.ROUTES[value] for value in frozen.FREQUENCIES],
        )
        self.assertEqual(
            [action["identity"]["request"]["body"] for action in campaign["actions"]],
            ["none"] * 5,
        )
        self.assertEqual(
            [session["power_mode"] for session in campaign["sessions"]],
            ["panel_cold_driver_only"] * 5,
        )
        self.assertTrue(
            all(not session["requires_controller_fresh_boot"] for session in campaign["sessions"])
        )
        self.assertTrue(
            all(session["requires_panel_power_cycle"] for session in campaign["sessions"])
        )
        self.assertTrue(
            all(session["minimum_panel_power_off_seconds"] == 150 for session in campaign["sessions"])
        )
        identities = [action["action_identity_sha256"] for action in campaign["actions"]]
        claims = [action["claim"]["filename"] for action in campaign["actions"]]
        self.assertEqual(len(set(identities)), 5)
        self.assertEqual(len(set(claims)), 5)
        self.assertIsNone(campaign["actions"][0]["identity"]["prior"])
        for prior, action in zip(campaign["actions"], campaign["actions"][1:]):
            self.assertEqual(
                action["identity"]["prior"]["action_identity_sha256"],
                prior["action_identity_sha256"],
            )
            self.assertEqual(
                action["identity"]["schedule"]["minimum_interval_since_prior_seconds"],
                150,
            )
        self.assertEqual(manifest["classification"]["qualification_state"], "NOT_QUALIFIED")

    def test_panel_review_and_schedule_each_rotate_all_actions(self) -> None:
        baseline = self.compile()
        baseline_ids = set(baseline["fixed_actions"].values())

        changed_panel = dict(PANEL)
        changed_panel["serial"] = "MF1750-M009F-BARCODE-0002"
        self.panel.write_bytes(canonical_json_bytes(changed_panel))
        panel_ids = set(self.compile()["fixed_actions"].values())
        self.assertTrue(baseline_ids.isdisjoint(panel_ids))

        self.panel.write_bytes(canonical_json_bytes(PANEL))
        self.review.write_bytes(b"different reviewed binding bytes\n")
        review_ids = set(self.compile()["fixed_actions"].values())
        self.assertTrue(baseline_ids.isdisjoint(review_ids))

        self.review.write_bytes(b"reviewed physical N7 panel binding\n")
        schedule_ids = set(
            self.compile(
                minimum_interval_seconds=151,
                planned_cooldown_seconds=151,
            )["fixed_actions"].values()
        )
        self.assertTrue(baseline_ids.isdisjoint(schedule_ids))

    def test_placeholder_and_unsafe_schedule_fail_closed(self) -> None:
        invalid = dict(PANEL)
        invalid["serial"] = "UNBOUND"
        self.panel.write_bytes(canonical_json_bytes(invalid))
        with self.assertRaisesRegex(physical.N7PhysicalCampaignError, "placeholder"):
            self.compile()

        self.panel.write_bytes(canonical_json_bytes(PANEL))
        with self.assertRaisesRegex(physical.N7PhysicalCampaignError, "at least"):
            self.compile(minimum_interval_seconds=0)
        with self.assertRaisesRegex(physical.N7PhysicalCampaignError, "at least"):
            self.compile(planned_cooldown_seconds=9.999)

    def test_publish_read_and_cross_file_tamper_fail_closed(self) -> None:
        bundle = self.root / "physical"
        written = physical.publish_physical_bundle(
            self.source,
            self.panel,
            self.review,
            bundle,
            minimum_interval_seconds=150,
            planned_cooldown_seconds=150,
        )
        loaded = physical.read_physical_bundle(
            bundle,
            self.source,
            self.panel,
            self.review,
            minimum_interval_seconds=150,
            planned_cooldown_seconds=150,
        )
        self.assertEqual(loaded, written)
        self.assertEqual(
            {path.name for path in bundle.iterdir()},
            {physical.PHYSICAL_CAMPAIGN_FILENAME, physical.MANIFEST_FILENAME},
        )

        campaign_path = bundle / physical.PHYSICAL_CAMPAIGN_FILENAME
        changed = deepcopy(written["physical_campaign"])
        changed["panel"]["serial"] = "MF1750-M009F-BARCODE-9999"
        campaign_path.write_bytes(canonical_json_bytes(changed))
        with self.assertRaisesRegex(
            physical.N7PhysicalCampaignError, "differs from manifest"
        ):
            physical.read_physical_bundle(
                bundle,
                self.source,
                self.panel,
                self.review,
                minimum_interval_seconds=150,
                planned_cooldown_seconds=150,
            )

    def test_manifest_reseal_cannot_hide_actual_input_change(self) -> None:
        manifest = self.compile()
        changed = deepcopy(manifest)
        changed["physical_binding"]["panel_binding_review_artifact"]["sha256"] = "0" * 64
        unsigned = dict(changed)
        unsigned.pop("integrity")
        changed["integrity"] = {
            "canonical_sha256": physical._sha256(unsigned),
            "canonical_sha256_scope": physical.HASH_SCOPE,
        }
        with self.assertRaisesRegex(
            physical.N7PhysicalCampaignError, "actual source inputs"
        ):
            physical.validate_physical_manifest(
                changed,
                self.source,
                self.panel,
                self.review,
                minimum_interval_seconds=150,
                planned_cooldown_seconds=150,
            )


if __name__ == "__main__":
    unittest.main()
