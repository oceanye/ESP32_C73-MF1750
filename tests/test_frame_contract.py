from __future__ import annotations

import itertools
import unittest

from host.epd_frame import (
    CONTROLLER_FRAME_BYTES,
    CONTROLLER_ROW_BYTES,
    EXPECTED_FIXTURE_HASHES,
    FIXTURE_NAMES,
    FRAME_BYTES,
    MAP_ORIENT_V1_PIXEL_COUNTS,
    ROW_BYTES,
    ControllerMapping,
    FrameContractError,
    controller_stream,
    controller_stream_reference,
    fnv1a,
    generate_fixture,
    iter_controller_rows,
    pack_pixels,
    pixel_counts,
    split_controller_rows,
    split_controllers,
    unpack_pixels,
    validate_frame,
    verify_fixture,
)


class PackingTests(unittest.TestCase):
    def test_even_x_is_high_nibble_and_odd_x_is_low_nibble(self) -> None:
        pixels = bytes((0, 1, 2, 3, 5, 6, 1, 0))
        packed = pack_pixels(pixels, width=4, height=2)
        self.assertEqual(packed, bytes((0x01, 0x23, 0x56, 0x10)))
        self.assertEqual(unpack_pixels(packed, width=4, height=2), pixels)

    def test_fnv1a_known_vector(self) -> None:
        self.assertEqual(fnv1a(b""), 0x811C9DC5)
        self.assertEqual(fnv1a(b"hello"), 0x4F9F2CAB)

    def test_validate_frame_returns_zero_copy_view(self) -> None:
        packed = bytearray((0x01, 0x23))
        view = validate_frame(packed, width=4, height=1)
        packed[0] = 0x10
        self.assertEqual(view[0], 0x10)


class SplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pack_pixels(
            (0, 1, 2, 3, 5, 6, 1, 0, 3, 2, 6, 5, 0, 1, 2, 3),
            width=8,
            height=2,
        )

    def test_split_rows_preserves_row_boundaries(self) -> None:
        rows = list(split_controller_rows(self.frame, width=8, height=2))
        self.assertEqual(rows, [(b"\x01\x23", b"\x56\x10"), (b"\x32\x65", b"\x01\x23")])

    def test_split_complete_controller_streams(self) -> None:
        left, right = split_controllers(self.frame, width=8, height=2)
        self.assertEqual(left, b"\x01\x23\x32\x65")
        self.assertEqual(right, b"\x56\x10\x01\x23")

    def test_iterated_default_mapping_matches_logical_split(self) -> None:
        left, right = split_controllers(self.frame, width=8, height=2)
        self.assertEqual(
            b"".join(iter_controller_rows(self.frame, ControllerMapping(0), width=8, height=2)),
            left,
        )
        self.assertEqual(
            b"".join(iter_controller_rows(self.frame, ControllerMapping(1), width=8, height=2)),
            right,
        )


class FixtureTests(unittest.TestCase):
    def test_all_fixtures_have_frozen_hashes(self) -> None:
        for name in FIXTURE_NAMES:
            with self.subTest(name=name):
                frame = generate_fixture(name)
                report = verify_fixture(name, frame)
                self.assertEqual(len(frame), FRAME_BYTES)
                self.assertEqual(
                    (report.full_fnv1a, report.cs1_fnv1a, report.cs2_fnv1a),
                    EXPECTED_FIXTURE_HASHES[name],
                )
                self.assertTrue(report.verified)

    def test_map_orient_v1_pixel_counts(self) -> None:
        frame = generate_fixture("map-orient-v1")
        self.assertEqual(pixel_counts(frame), MAP_ORIENT_V1_PIXEL_COUNTS)

    def test_fixture_dimensions_match_controller_contract(self) -> None:
        frame = generate_fixture("global-v-bars")
        left, right = split_controllers(frame)
        self.assertEqual(len(left), CONTROLLER_FRAME_BYTES)
        self.assertEqual(len(right), CONTROLLER_FRAME_BYTES)
        rows = list(split_controller_rows(frame))
        self.assertEqual(len(rows), 600)
        self.assertTrue(all(len(left_row) == CONTROLLER_ROW_BYTES for left_row, _ in rows))
        self.assertTrue(all(len(right_row) == CONTROLLER_ROW_BYTES for _, right_row in rows))
        self.assertEqual(ROW_BYTES, CONTROLLER_ROW_BYTES * 2)


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frame = generate_fixture("map-orient-v1")

    def test_byte_algorithm_matches_independent_pixel_reference_for_all_16_combinations(self) -> None:
        for source_half, flip_x, flip_y, nibble_swap in itertools.product(
            (0, 1), (False, True), (False, True), (False, True)
        ):
            mapping = ControllerMapping(source_half, flip_x, flip_y, nibble_swap)
            with self.subTest(mapping=mapping):
                self.assertEqual(
                    controller_stream(self.frame, mapping),
                    controller_stream_reference(self.frame, mapping),
                )

    def test_flip_x_and_nibble_swap_compose_with_xor(self) -> None:
        frame = pack_pixels((0, 1, 2, 3, 5, 6, 1, 0), width=8, height=1)
        self.assertEqual(controller_stream(frame, ControllerMapping(0), width=8, height=1), b"\x01\x23")
        self.assertEqual(
            controller_stream(frame, ControllerMapping(0, flip_x=True), width=8, height=1),
            b"\x32\x10",
        )
        self.assertEqual(
            controller_stream(
                frame, ControllerMapping(0, flip_x=True, nibble_swap=True), width=8, height=1
            ),
            b"\x23\x01",
        )


class ValidationTests(unittest.TestCase):
    def test_odd_width_is_rejected(self) -> None:
        with self.assertRaisesRegex(FrameContractError, "even width"):
            pack_pixels((0, 1, 2), width=3, height=1)

    def test_controller_width_not_divisible_by_four_is_rejected(self) -> None:
        frame = pack_pixels((0, 1, 2, 3, 5, 6), width=6, height=1)
        with self.assertRaisesRegex(FrameContractError, "divisible by 4"):
            split_controllers(frame, width=6, height=1)

    def test_short_and_long_pixel_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(FrameContractError, "ended before"):
            pack_pixels((0, 1, 2), width=4, height=1)
        with self.assertRaisesRegex(FrameContractError, "more than"):
            pack_pixels((0, 1, 2, 3, 5), width=4, height=1)

    def test_illegal_color_codes_are_rejected_on_pack_and_unpack(self) -> None:
        with self.assertRaisesRegex(FrameContractError, "unsupported physical color"):
            pack_pixels((0, 1, 4, 3), width=4, height=1)
        with self.assertRaisesRegex(FrameContractError, "unsupported physical color"):
            unpack_pixels(b"\x01\x47", width=4, height=1)

    def test_truncated_and_oversized_frames_are_rejected(self) -> None:
        with self.assertRaisesRegex(FrameContractError, "expected 4"):
            validate_frame(b"\x01\x23\x56", width=4, height=2)
        with self.assertRaisesRegex(FrameContractError, "expected 4"):
            validate_frame(b"\x01\x23\x56\x10\x01", width=4, height=2)

    def test_invalid_source_half_is_rejected(self) -> None:
        with self.assertRaisesRegex(FrameContractError, "source_half"):
            ControllerMapping(2)

    def test_unknown_fixture_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fixture"):
            generate_fixture("not-a-fixture")


if __name__ == "__main__":
    unittest.main()

