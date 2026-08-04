from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from host.epd_frame import FRAME_BYTES, ControllerMapping, fnv1a as frame_fnv1a
from host.partial_update import (
    PartialUpdateContractError,
    build_transition_plan,
    fnv1a as partial_fnv1a,
)
from host.partial_update.planner import MAX_NEIGHBOR_RADIUS
from tools.mf1750_partial_plan import main as partial_plan_main


def pack(pixels: list[int]) -> bytes:
    return bytes(
        (pixels[index] << 4) | pixels[index + 1]
        for index in range(0, len(pixels), 2)
    )


def trusted_plan(old_frame: bytes, new_frame: bytes, **kwargs: object):
    return build_transition_plan(
        old_frame,
        new_frame,
        last_success_operation_id="display-op-17",
        last_success_frame_fnv1a=frame_fnv1a(old_frame),
        last_success_trusted=True,
        **kwargs,
    )


class TransitionPlanTests(unittest.TestCase):
    def test_identical_trusted_frames_have_no_update_region(self) -> None:
        frame = pack([1] * 32)
        plan = trusted_plan(frame, frame, width=8, height=4)
        self.assertTrue(plan.old_frame_supplied)
        self.assertTrue(plan.transition_comparison_performed)
        self.assertEqual(plan.changed_pixels, 0)
        self.assertEqual(plan.protected_pixels, 0)
        self.assertIsNone(plan.bounding_box)
        self.assertEqual(plan.logical_half_regions, ())
        self.assertEqual(plan.transition_histogram[1][1], 32)

    def test_single_pixel_change_expands_neighbors_and_byte_alignment(self) -> None:
        old_pixels = [1] * 32
        new_pixels = list(old_pixels)
        new_pixels[1 * 8 + 3] = 0
        plan = trusted_plan(
            pack(old_pixels),
            pack(new_pixels),
            width=8,
            height=4,
            neighbor_radius=1,
        )
        self.assertEqual(plan.changed_pixels, 1)
        self.assertEqual(plan.protected_pixels, 5)
        self.assertEqual(plan.bounding_box, (2, 0, 6, 3))
        self.assertEqual(len(plan.logical_half_regions), 2)
        left, right = plan.logical_half_regions
        self.assertEqual((left.logical_half, left.global_x0, left.global_x1), (0, 2, 4))
        self.assertEqual((right.logical_half, right.global_x0, right.global_x1), (1, 4, 6))
        self.assertEqual((right.logical_local_x0, right.logical_local_x1), (0, 2))
        self.assertEqual(plan.transition_histogram[1][0], 1)
        self.assertEqual(plan.transition_histogram[1][1], 31)

    def test_seam_changes_are_split_into_logical_half_regions(self) -> None:
        old_pixels = [1] * 16
        new_pixels = list(old_pixels)
        new_pixels[3] = 3
        new_pixels[4] = 5
        plan = trusted_plan(
            pack(old_pixels),
            pack(new_pixels),
            width=8,
            height=2,
            neighbor_radius=0,
        )
        self.assertEqual(plan.bounding_box, (2, 0, 6, 1))
        self.assertEqual(len(plan.logical_half_regions), 2)
        left, right = plan.logical_half_regions
        self.assertEqual(
            (left.logical_half, left.logical_local_x0, left.logical_local_x1),
            (0, 2, 4),
        )
        self.assertEqual(
            (right.logical_half, right.logical_local_x0, right.logical_local_x1),
            (1, 0, 2),
        )

    def test_missing_old_frame_is_conservative_and_does_not_invent_transitions(self) -> None:
        new_frame = pack([1] * 16)
        plan = build_transition_plan(None, new_frame, width=8, height=2)
        self.assertFalse(plan.old_frame_supplied)
        self.assertFalse(plan.transition_comparison_performed)
        self.assertIsNone(plan.changed_pixels)
        self.assertIsNone(plan.unchanged_pixels)
        self.assertEqual(plan.protected_pixels, 16)
        self.assertEqual(plan.bounding_box, (0, 0, 8, 2))
        self.assertIsNone(plan.transition_histogram)
        self.assertIsNone(plan.supplied_old_frame_fnv1a)

    def test_old_frame_without_trusted_provenance_remains_conservative(self) -> None:
        old_frame = pack([1] * 16)
        new_frame = pack([1] * 16)
        plan = build_transition_plan(
            old_frame,
            new_frame,
            width=8,
            height=2,
            last_success_operation_id="untrusted-record",
            last_success_frame_fnv1a=frame_fnv1a(old_frame),
        )
        self.assertTrue(plan.old_frame_supplied)
        self.assertTrue(plan.last_success_matches_old_frame)
        self.assertFalse(plan.last_success_trusted)
        self.assertFalse(plan.transition_comparison_performed)
        self.assertIsNone(plan.changed_pixels)
        self.assertIsNone(plan.unchanged_pixels)
        self.assertIsNone(plan.transition_histogram)

        report = plan.to_dict()
        self.assertFalse(report["changed_pixels_known"])
        self.assertIsNone(report["changed_fraction"])

    def test_json_contract_records_provenance_and_uses_logical_regions(self) -> None:
        old_frame = pack([1] * 16)
        new_pixels = [1] * 16
        new_pixels[0] = 0
        report = trusted_plan(
            old_frame,
            pack(new_pixels),
            width=8,
            height=2,
            neighbor_radius=0,
        ).to_dict()
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(report["old_frame_supplied"])
        self.assertTrue(report["transition_comparison_performed"])
        self.assertEqual(report["planning_mode"], "trusted_transition")
        self.assertEqual(report["last_success_provenance"]["operation_id"], "display-op-17")
        self.assertTrue(report["last_success_provenance"]["trusted"])
        self.assertIn("logical_half_regions", report)
        self.assertNotIn("controller_regions", report)
        self.assertNotIn("old_state_known", report)
        self.assertNotIn("physical_controller", report["logical_half_regions"][0])
        self.assertFalse(report["hardware_tested"])
        self.assertFalse(report["controller_commands_generated"])
        self.assertTrue(report["requires_vendor_partial_update_definition"])

    def test_explicit_frozen_swap_and_flips_add_physical_coordinates(self) -> None:
        old_pixels = [1] * 32
        new_pixels = list(old_pixels)
        new_pixels[1] = 0  # logical half 0, x=1, y=0 -> aligned x=[0,2)
        mappings = (
            ControllerMapping(source_half=1),
            ControllerMapping(source_half=0, flip_x=True, flip_y=True, nibble_swap=True),
        )
        plan = trusted_plan(
            pack(old_pixels),
            pack(new_pixels),
            width=8,
            height=4,
            neighbor_radius=0,
            frozen_controller_mappings=mappings,
        )
        self.assertTrue(plan.physical_mapping_supplied)
        self.assertEqual(len(plan.logical_half_regions), 1)
        region = plan.logical_half_regions[0]
        self.assertEqual(region.logical_half, 0)
        self.assertEqual(region.physical_controller, 2)
        self.assertEqual(
            (
                region.physical_local_x0,
                region.physical_local_y0,
                region.physical_local_x1,
                region.physical_local_y1,
            ),
            (2, 3, 4, 4),
        )
        serialized = region.to_dict()
        self.assertEqual(serialized["physical_mapping"]["source_half"], 0)
        self.assertTrue(serialized["physical_mapping"]["flip_x"])
        self.assertTrue(serialized["physical_mapping"]["flip_y"])

    def test_full_screen_transition_bypasses_mask_dilation(self) -> None:
        old_frame = pack([1] * 32)
        new_frame = pack([0] * 32)
        with patch(
            "host.partial_update.planner._dilate_cardinal",
            side_effect=AssertionError("full-screen path must not dilate"),
        ):
            plan = trusted_plan(
                old_frame,
                new_frame,
                width=8,
                height=4,
                neighbor_radius=MAX_NEIGHBOR_RADIUS,
            )
        self.assertEqual(plan.changed_pixels, 32)
        self.assertEqual(plan.protected_pixels, 32)
        self.assertEqual(plan.bounding_box, (0, 0, 8, 4))
        self.assertEqual(len(plan.logical_half_regions), 2)


class ValidationTests(unittest.TestCase):
    def test_frame_validation_is_reused_from_epd_frame_contract(self) -> None:
        self.assertIs(partial_fnv1a, frame_fnv1a)
        with self.assertRaisesRegex(PartialUpdateContractError, "expected 8"):
            build_transition_plan(b"\x11", b"\x11", width=8, height=2)
        with self.assertRaisesRegex(PartialUpdateContractError, "unsupported physical color"):
            build_transition_plan(b"\x11\x11\x11\x11", b"\x14\x11\x11\x11", width=8, height=1)

    def test_width_and_radius_are_bounded(self) -> None:
        with self.assertRaisesRegex(PartialUpdateContractError, "divisible by 4"):
            build_transition_plan(None, b"\x11\x11\x11", width=6, height=1)
        with self.assertRaisesRegex(PartialUpdateContractError, "cannot be negative"):
            build_transition_plan(None, b"\x11\x11\x11\x11", width=8, height=1, neighbor_radius=-1)
        with self.assertRaisesRegex(PartialUpdateContractError, "cannot exceed 32"):
            build_transition_plan(
                None,
                b"\x11\x11\x11\x11",
                width=8,
                height=1,
                neighbor_radius=MAX_NEIGHBOR_RADIUS + 1,
            )
        plan = build_transition_plan(
            None,
            b"\x11\x11\x11\x11",
            width=8,
            height=1,
            neighbor_radius=MAX_NEIGHBOR_RADIUS,
        )
        self.assertEqual(plan.neighbor_radius, MAX_NEIGHBOR_RADIUS)

    def test_trusted_provenance_requires_old_frame_id_and_matching_hash(self) -> None:
        frame = pack([1] * 16)
        hash_value = frame_fnv1a(frame)
        with self.assertRaisesRegex(PartialUpdateContractError, "requires old_frame"):
            build_transition_plan(
                None,
                frame,
                width=8,
                height=2,
                last_success_operation_id="op",
                last_success_frame_fnv1a=hash_value,
                last_success_trusted=True,
            )
        with self.assertRaisesRegex(PartialUpdateContractError, "requires last_success_operation_id"):
            build_transition_plan(
                frame,
                frame,
                width=8,
                height=2,
                last_success_frame_fnv1a=hash_value,
                last_success_trusted=True,
            )
        with self.assertRaisesRegex(PartialUpdateContractError, "does not match"):
            build_transition_plan(
                frame,
                frame,
                width=8,
                height=2,
                last_success_operation_id="op",
                last_success_frame_fnv1a=hash_value ^ 1,
                last_success_trusted=True,
            )

    def test_mapping_must_be_complete_bijection(self) -> None:
        frame = pack([1] * 16)
        with self.assertRaisesRegex(PartialUpdateContractError, "exactly once"):
            build_transition_plan(
                None,
                frame,
                width=8,
                height=2,
                frozen_controller_mappings=(ControllerMapping(0), ControllerMapping(0)),
            )
        with self.assertRaisesRegex(PartialUpdateContractError, "two ControllerMapping"):
            build_transition_plan(
                None,
                frame,
                width=8,
                height=2,
                frozen_controller_mappings=(ControllerMapping(0),),
            )


class CliTests(unittest.TestCase):
    def test_documented_direct_script_help_resolves_host_package(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/mf1750_partial_plan.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--trust-last-success", completed.stdout)

    def test_cli_requires_explicit_trust_and_accepts_frozen_mapping(self) -> None:
        old_frame = b"\x11" * FRAME_BYTES
        new_frame = b"\x01" + old_frame[1:]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_path = root / "old.bin"
            new_path = root / "new.bin"
            old_path.write_bytes(old_frame)
            new_path.write_bytes(new_frame)
            output = io.StringIO()
            with patch("sys.stdout", output):
                result = partial_plan_main(
                    [
                        str(new_path),
                        "--old-frame",
                        str(old_path),
                        "--last-success-operation-id",
                        "op-cli",
                        "--last-success-frame-fnv1a",
                        hex(frame_fnv1a(old_frame)),
                        "--trust-last-success",
                        "--frozen-controller-mapping",
                        "1,0,0,0",
                        "--frozen-controller-mapping",
                        "0,1,1,0",
                    ]
                )
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["planning_mode"], "trusted_transition")
        self.assertTrue(report["physical_mapping_supplied"])
        self.assertEqual(report["logical_half_regions"][0]["physical_controller"], 2)


if __name__ == "__main__":
    unittest.main()
