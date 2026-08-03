from __future__ import annotations

import unittest

from host.partial_update import (
    PartialUpdateContractError,
    build_transition_plan,
)


def pack(pixels: list[int]) -> bytes:
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, len(pixels), 2))


class TransitionPlanTests(unittest.TestCase):
    def test_identical_frames_have_no_update_region(self) -> None:
        frame = pack([1] * 32)
        plan = build_transition_plan(frame, frame, width=8, height=4)
        self.assertEqual(plan.changed_pixels, 0)
        self.assertEqual(plan.protected_pixels, 0)
        self.assertEqual(plan.bounding_box, None)
        self.assertEqual(plan.controller_regions, ())
        self.assertEqual(plan.transition_histogram[1][1], 32)

    def test_single_pixel_change_expands_cardinal_neighbors_and_byte_alignment(self) -> None:
        old_pixels = [1] * 32
        new_pixels = list(old_pixels)
        new_pixels[1 * 8 + 3] = 0
        plan = build_transition_plan(
            pack(old_pixels), pack(new_pixels), width=8, height=4, neighbor_radius=1
        )
        self.assertEqual(plan.changed_pixels, 1)
        self.assertEqual(plan.protected_pixels, 5)
        self.assertEqual(plan.bounding_box, (2, 0, 6, 3))
        self.assertEqual(len(plan.controller_regions), 2)
        self.assertEqual(plan.controller_regions[0].global_x0, 2)
        self.assertEqual(plan.controller_regions[0].global_x1, 4)
        self.assertEqual(plan.controller_regions[1].global_x0, 4)
        self.assertEqual(plan.controller_regions[1].local_x0, 0)
        self.assertEqual(plan.transition_histogram[1][0], 1)
        self.assertEqual(plan.transition_histogram[1][1], 31)

    def test_seam_changes_are_split_into_controller_local_regions(self) -> None:
        old_pixels = [1] * 16
        new_pixels = list(old_pixels)
        new_pixels[3] = 3
        new_pixels[4] = 5
        plan = build_transition_plan(
            pack(old_pixels), pack(new_pixels), width=8, height=2, neighbor_radius=0
        )
        self.assertEqual(plan.bounding_box, (2, 0, 6, 1))
        self.assertEqual(len(plan.controller_regions), 2)
        cs1, cs2 = plan.controller_regions
        self.assertEqual((cs1.controller, cs1.local_x0, cs1.local_x1), (1, 2, 4))
        self.assertEqual((cs2.controller, cs2.local_x0, cs2.local_x1), (2, 0, 2))

    def test_unknown_old_state_is_conservative_and_does_not_invent_transitions(self) -> None:
        new_frame = pack([1] * 16)
        plan = build_transition_plan(None, new_frame, width=8, height=2)
        self.assertFalse(plan.old_state_known)
        self.assertEqual(plan.changed_pixels, 16)
        self.assertEqual(plan.protected_pixels, 16)
        self.assertEqual(plan.bounding_box, (0, 0, 8, 2))
        self.assertIsNone(plan.transition_histogram)
        self.assertIsNone(plan.old_frame_fnv1a)

    def test_json_contract_never_claims_commands_or_hardware(self) -> None:
        frame = pack([1] * 16)
        report = build_transition_plan(frame, frame, width=8, height=2).to_dict()
        self.assertFalse(report["hardware_tested"])
        self.assertFalse(report["controller_commands_generated"])
        self.assertTrue(report["requires_vendor_partial_update_definition"])


class ValidationTests(unittest.TestCase):
    def test_frame_length_is_validated(self) -> None:
        with self.assertRaisesRegex(PartialUpdateContractError, "expected 8"):
            build_transition_plan(b"\x11", b"\x11", width=8, height=2)

    def test_illegal_color_is_rejected(self) -> None:
        with self.assertRaisesRegex(PartialUpdateContractError, "unsupported color"):
            build_transition_plan(b"\x11\x11\x11\x11", b"\x14\x11\x11\x11", width=8, height=1)

    def test_width_and_radius_are_validated(self) -> None:
        with self.assertRaisesRegex(PartialUpdateContractError, "divisible by 4"):
            build_transition_plan(None, b"\x11\x11\x11", width=6, height=1)
        with self.assertRaisesRegex(PartialUpdateContractError, "cannot be negative"):
            build_transition_plan(None, b"\x11\x11\x11\x11", width=8, height=1, neighbor_radius=-1)


if __name__ == "__main__":
    unittest.main()

