from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    seal_campaign_contract,
    validate_campaign_contract,
)
from host.visible_refresh_campaign import physical_rebind as rebind


FIRMWARE = {
    "source_commit": "1" * 40,
    "build_tag": "rc2g-physical-rebind-test",
    "binary_sha256": "2" * 64,
    "driver_api": "mf1750-http-v1",
}
SOURCE_PANEL = {
    "model": "MF1750-C73",
    "serial": "UNBOUND-N3-OFFLINE",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
PHYSICAL_PANEL = {
    **SOURCE_PANEL,
    "serial": "MF1750-LAB-PANEL-0001",
}
CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}
REVIEW_BYTES = b"reviewed N3/N4 to N2 physical panel binding\n"
REVIEWED_SCHEDULE = {
    "minimum_interval_seconds": 150,
    "planned_cooldown_seconds": 150,
}


def _frame(seed: int) -> dict[str, object]:
    digits = "0123456789abcdef"
    return {
        "width": 1024,
        "height": 600,
        "bits_per_pixel": 4,
        "bytes": 307200,
        "sha256": digits[seed % 16] * 64,
        "fnv1a": f"0x{seed:08X}",
        "controllers": [
            {
                "controller": "CS1",
                "mapping": {
                    "source_half": 0,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": digits[(seed + 1) % 16] * 64,
                "dtm_fnv1a": f"0x{seed + 1:08X}",
            },
            {
                "controller": "CS2",
                "mapping": {
                    "source_half": 1,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": digits[(seed + 2) % 16] * 64,
                "dtm_fnv1a": f"0x{seed + 2:08X}",
            },
        ],
    }


def _campaign(
    *, campaign_id: str, panel: dict[str, str], firmware=FIRMWARE
) -> dict[str, object]:
    primer = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id="session-1",
        cell_id="cell-1",
        action_id="cell-1-map-primer",
        phase="map-primer",
        frame=_frame(1),
    )
    target = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id="session-1",
        cell_id="cell-1",
        action_id="cell-1-target",
        phase="target",
        frame=_frame(4),
        prior_action_identity_sha256=primer["action_identity_sha256"],
        prior_scope="same_cell",
        minimum_interval_since_prior_seconds=30,
    )
    session = build_session_contract(
        session_id="session-1",
        cell_id="cell-1",
        power_mode="controller_fresh_boot",
        planned_cooldown_seconds=60,
        final_power_off_required=False,
        action_identity_sha256s=[
            primer["action_identity_sha256"],
            target["action_identity_sha256"],
        ],
    )
    return seal_campaign_contract(
        {
            "schema_version": 1,
            "kind": CAMPAIGN_KIND,
            "campaign_id": campaign_id,
            "panel": panel,
            "firmware": firmware,
            "actions": [primer, target],
            "sessions": [session],
            "classification": CLASSIFICATION,
        }
    )


class PhysicalCampaignRebindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _campaign(campaign_id="n3-offline-source", panel=SOURCE_PANEL)
        self.anchor = _campaign(campaign_id="n2-physical-anchor", panel=PHYSICAL_PANEL)

    def _compile(self, *, review: bytes = REVIEW_BYTES):
        return rebind.compile_physical_campaign_rebind(
            self.source,
            self.anchor,
            namespace="n3a-winner-repeat2",
            binding_review_bytes=review,
            **REVIEWED_SCHEDULE,
        )

    def test_rebuilds_campaign_actions_priors_sessions_and_claims(self) -> None:
        manifest = self._compile()
        physical = manifest["physical_campaign"]
        validate_campaign_contract(physical)
        self.assertEqual(physical["panel"], PHYSICAL_PANEL)
        self.assertEqual(physical["firmware"], FIRMWARE)
        self.assertNotEqual(physical["campaign_id"], self.source["campaign_id"])

        old_by_id = {
            action["identity"]["action_id"]: action for action in self.source["actions"]
        }
        new_by_id = {
            action["identity"]["action_id"]: action for action in physical["actions"]
        }
        self.assertEqual(set(old_by_id), set(new_by_id))
        self.assertTrue(
            {action["action_identity_sha256"] for action in old_by_id.values()}.isdisjoint(
                {action["action_identity_sha256"] for action in new_by_id.values()}
            )
        )
        self.assertTrue(
            {action["claim"]["filename"] for action in old_by_id.values()}.isdisjoint(
                {action["claim"]["filename"] for action in new_by_id.values()}
            )
        )
        self.assertEqual(
            new_by_id["cell-1-target"]["identity"]["prior"][
                "action_identity_sha256"
            ],
            new_by_id["cell-1-map-primer"]["action_identity_sha256"],
        )
        self.assertEqual(
            physical["sessions"][0]["action_identity_sha256s"],
            [
                new_by_id["cell-1-map-primer"]["action_identity_sha256"],
                new_by_id["cell-1-target"]["action_identity_sha256"],
            ],
        )
        self.assertEqual(len(manifest["action_identity_map"]), 2)
        self.assertFalse(manifest["classification"]["hardware_execution_authorized"])
        self.assertEqual(
            new_by_id["cell-1-target"]["identity"]["schedule"][
                "minimum_interval_since_prior_seconds"
            ],
            150,
        )
        self.assertEqual(physical["sessions"][0]["planned_cooldown_seconds"], 150)
        self.assertEqual(manifest["binding"]["reviewed_schedule"], {
            "classification": "operator_selected_experimental_process_schedule",
            "not_a_supplier_rating": True,
            "minimum_interval_seconds": 150.0,
            "planned_cooldown_seconds": 150.0,
        })

    def test_same_bytes_are_deterministic_and_real_review_change_rotates_all_ids(self) -> None:
        first = self._compile()
        self.assertEqual(first, self._compile())
        revised = self._compile(review=REVIEW_BYTES + b"revision 2\n")
        self.assertNotEqual(first["binding"], revised["binding"])
        self.assertNotEqual(
            first["physical_campaign"]["campaign_id"],
            revised["physical_campaign"]["campaign_id"],
        )
        self.assertTrue(
            {
                action["action_identity_sha256"]
                for action in first["physical_campaign"]["actions"]
            }.isdisjoint(
                {
                    action["action_identity_sha256"]
                    for action in revised["physical_campaign"]["actions"]
                }
            )
        )
        rescheduled = rebind.compile_physical_campaign_rebind(
            self.source,
            self.anchor,
            namespace="n3a-winner-repeat2",
            binding_review_bytes=REVIEW_BYTES,
            minimum_interval_seconds=151,
            planned_cooldown_seconds=150,
        )
        self.assertNotEqual(first["binding"], rescheduled["binding"])
        self.assertTrue(
            {
                action["action_identity_sha256"]
                for action in first["physical_campaign"]["actions"]
            }.isdisjoint(
                {
                    action["action_identity_sha256"]
                    for action in rescheduled["physical_campaign"]["actions"]
                }
            )
        )
        self.assertTrue(
            {
                action["claim"]["filename"]
                for action in first["physical_campaign"]["actions"]
            }.isdisjoint(
                {
                    action["claim"]["filename"]
                    for action in rescheduled["physical_campaign"]["actions"]
                }
            )
        )

    def test_validator_requires_actual_review_bytes_and_reconstructs_everything(self) -> None:
        manifest = self._compile()
        with self.assertRaisesRegex(
            rebind.PhysicalCampaignRebindError,
            "actual review artifact bytes",
        ):
            rebind.validate_physical_campaign_rebind(
                manifest,
                source_campaign=self.source,
                physical_anchor_campaign=self.anchor,
                binding_review_bytes=b"not the reviewed file",
                **REVIEWED_SCHEDULE,
            )
        tampered = deepcopy(manifest)
        tampered["physical_campaign"]["actions"][0]["identity"]["phase"] = "target"
        with self.assertRaises(rebind.PhysicalCampaignRebindError):
            rebind.validate_physical_campaign_rebind(
                tampered,
                source_campaign=self.source,
                physical_anchor_campaign=self.anchor,
                binding_review_bytes=REVIEW_BYTES,
                **REVIEWED_SCHEDULE,
            )

    def test_rejects_placeholder_anchor_and_wrong_hardware_or_firmware(self) -> None:
        unbound_anchor = _campaign(
            campaign_id="unbound-anchor",
            panel={**PHYSICAL_PANEL, "serial": "UNBOUND-PANEL"},
        )
        with self.assertRaisesRegex(
            rebind.PhysicalCampaignRebindError, "unbound or placeholder"
        ):
            rebind.compile_physical_campaign_rebind(
                self.source,
                unbound_anchor,
                namespace="n4-v3",
                binding_review_bytes=REVIEW_BYTES,
                **REVIEWED_SCHEDULE,
            )

        wrong_board = _campaign(
            campaign_id="wrong-board-anchor",
            panel={**PHYSICAL_PANEL, "board_id": "OTHER-BOARD"},
        )
        with self.assertRaisesRegex(
            rebind.PhysicalCampaignRebindError, "panel.board_id differs"
        ):
            rebind.compile_physical_campaign_rebind(
                self.source,
                wrong_board,
                namespace="n4-v3",
                binding_review_bytes=REVIEW_BYTES,
                **REVIEWED_SCHEDULE,
            )

        wrong_firmware = _campaign(
            campaign_id="wrong-firmware-anchor",
            panel=PHYSICAL_PANEL,
            firmware={**FIRMWARE, "binary_sha256": "3" * 64},
        )
        with self.assertRaisesRegex(
            rebind.PhysicalCampaignRebindError, "source firmware differs"
        ):
            rebind.compile_physical_campaign_rebind(
                self.source,
                wrong_firmware,
                namespace="n4-v3",
                binding_review_bytes=REVIEW_BYTES,
                **REVIEWED_SCHEDULE,
            )

    def test_file_api_hashes_real_bytes_and_rejects_noncanonical_or_redirected_input(self) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            source_file = root / "source.json"
            anchor_file = root / "anchor.json"
            review_file = root / "review.bin"
            source_file.write_bytes(canonical_json_bytes(self.source))
            anchor_file.write_bytes(canonical_json_bytes(self.anchor))
            review_file.write_bytes(REVIEW_BYTES)
            manifest = rebind.compile_physical_campaign_rebind_from_files(
                source_file,
                anchor_file,
                review_file,
                namespace="n4-v3",
                **REVIEWED_SCHEDULE,
            )
            self.assertEqual(
                manifest["binding"]["binding_review_artifact"]["sha256"],
                rebind._sha256(REVIEW_BYTES),
            )

            source_file.write_text(
                canonical_json_bytes(self.source).decode("utf-8") + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                rebind.PhysicalCampaignRebindError, "canonical JSON bytes"
            ):
                rebind.compile_physical_campaign_rebind_from_files(
                    source_file,
                    anchor_file,
                    review_file,
                    namespace="n4-v3",
                    **REVIEWED_SCHEDULE,
                )

            source_file.write_bytes(canonical_json_bytes(self.source))
            link = root / "review-link.bin"
            try:
                link.symlink_to(review_file)
            except OSError:
                return
            with self.assertRaisesRegex(
                rebind.PhysicalCampaignRebindError, "symlink|reparse"
            ):
                rebind.compile_physical_campaign_rebind_from_files(
                    source_file,
                    anchor_file,
                    link,
                    namespace="n4-v3",
                    **REVIEWED_SCHEDULE,
                )

    def test_exclusive_bundle_publish_emits_standalone_canonical_campaign(self) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            source_file = root / "source.json"
            anchor_file = root / "anchor.json"
            review_file = root / "review.bin"
            output = root / "published"
            source_file.write_bytes(canonical_json_bytes(self.source))
            anchor_file.write_bytes(canonical_json_bytes(self.anchor))
            review_file.write_bytes(REVIEW_BYTES)

            manifest = rebind.publish_physical_campaign_rebind_bundle(
                source_file,
                anchor_file,
                review_file,
                output,
                namespace="n4-v3",
                **REVIEWED_SCHEDULE,
            )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {
                    rebind.PHYSICAL_CAMPAIGN_FILENAME,
                    rebind.REBIND_MANIFEST_FILENAME,
                },
            )
            campaign_file = output / rebind.PHYSICAL_CAMPAIGN_FILENAME
            self.assertEqual(
                campaign_file.read_bytes(),
                canonical_json_bytes(manifest["physical_campaign"]),
            )
            self.assertEqual(
                rebind.read_standalone_physical_campaign(campaign_file),
                manifest["physical_campaign"],
            )
            with self.assertRaisesRegex(
                rebind.PhysicalCampaignRebindError, "already exists"
            ):
                rebind.publish_physical_campaign_rebind_bundle(
                    source_file,
                    anchor_file,
                    review_file,
                    output,
                    namespace="n4-v3",
                    **REVIEWED_SCHEDULE,
                )

    def test_reviewed_schedule_is_explicit_and_rejects_bool_zero_or_negative(self) -> None:
        with self.assertRaises(TypeError):
            rebind.compile_physical_campaign_rebind(
                self.source,
                self.anchor,
                namespace="missing-schedule",
                binding_review_bytes=REVIEW_BYTES,
            )
        cases = (
            (True, 150),
            (0, 150),
            (-1, 150),
            (150, True),
            (150, -1),
        )
        for interval, cooldown in cases:
            with self.subTest(interval=interval, cooldown=cooldown):
                with self.assertRaises(rebind.PhysicalCampaignRebindError):
                    rebind.compile_physical_campaign_rebind(
                        self.source,
                        self.anchor,
                        namespace="invalid-schedule",
                        binding_review_bytes=REVIEW_BYTES,
                        minimum_interval_seconds=interval,
                        planned_cooldown_seconds=cooldown,
                    )


if __name__ == "__main__":
    unittest.main()
