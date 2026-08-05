from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    ROW_BYTES,
    WIDTH,
    FrameContractError,
    controller_stream,
    fnv1a,
    pixel_counts,
    validate_frame,
)
from host.extended_color import (
    COLOR_ORDER,
    DEFAULT_CONTROLLER_MAPPINGS,
    PANEL_PIXELS,
    PATTERN_NAMES,
    UNKNOWN_AREA_FRACTION,
    UNKNOWN_CODES,
    UNKNOWN_TOTAL_PIXELS,
    ExtendedColorContractError,
    build_artifact,
    deterministic_test_id,
    frame_identity,
    generate_large_blocks_frame,
    generate_solid_frame,
    generate_transition_matrix_frames,
    generate_unknown_probe_frame,
    known_pixel_counts,
    transition_color_orders,
    transition_rois,
    unknown_probe_rois,
    validate_unknown_probe_frame,
)
from tools import mf1750_extended_color as tool


FIXED_IDENTITIES = {
    "transition-initial": {
        "frame_sha256": "db4c425ebed64e5f5bf3b5322d5afa1af2670f854626115cb8b7df55d5b64820",
        "frame_fnv1a": 0x7FD055C5,
        "cs1_sha256": "17f2a7cf4e142c2afe1b5e6f2abcf0bc5c714ec0385a84ef3af22b2065128896",
        "cs1_fnv1a": 0xC5D679C5,
        "cs2_sha256": "17f2a7cf4e142c2afe1b5e6f2abcf0bc5c714ec0385a84ef3af22b2065128896",
        "cs2_fnv1a": 0xC5D679C5,
        "test_id": "MF1750-EC4-TRANSITION-INITIAL-R001-D7D89A7AD2F8",
    },
    "transition-target": {
        "frame_sha256": "7a3546d06ffb3afc155abfc459bb587f4c45b9c857272069f2c39f57799624a0",
        "frame_fnv1a": 0x4D617455,
        "cs1_sha256": "1003a5217a32f71fb191911046e142f15ed9f24a43cd98afae3a6209a3b7fb0d",
        "cs1_fnv1a": 0xECD8CE45,
        "cs2_sha256": "e5f68d6a5c801858bc6e4935db5921dd18f0e20d32cb4f301c6944cd101805e2",
        "cs2_fnv1a": 0xB77D4AA5,
        "test_id": "MF1750-EC4-TRANSITION-TARGET-R001-9220A55614EF",
    },
    "unknown-0x4": {
        "frame_sha256": "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e",
        "frame_fnv1a": 0x68533DC5,
        "cs1_sha256": "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
        "cs1_fnv1a": 0x15B7EDC5,
        "cs2_sha256": "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
        "cs2_fnv1a": 0x15B7EDC5,
        "test_id": "MF1750-EC5-DESIGN-UNKNOWN-0X4-R001-30A04E369EE5",
    },
    "unknown-0x7": {
        "frame_sha256": "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
        "frame_fnv1a": 0xA1C5ADC5,
        "cs1_sha256": "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        "cs1_fnv1a": 0x97F125C5,
        "cs2_sha256": "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        "cs2_fnv1a": 0x97F125C5,
        "test_id": "MF1750-EC5-DESIGN-UNKNOWN-0X7-R001-7C9ACFC07E38",
    },
}


def frame_pixel(frame: bytes, x: int, y: int) -> int:
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0xF if x & 1 else value >> 4


class KnownPatternTests(unittest.TestCase):
    def test_all_solid_frames_have_one_formal_color_and_canonical_size(self) -> None:
        for code in COLOR_ORDER:
            with self.subTest(code=code):
                frame = generate_solid_frame(code)
                counts = known_pixel_counts(frame)
                self.assertEqual(len(frame), FRAME_BYTES)
                self.assertEqual(counts[code], PANEL_PIXELS)
                self.assertEqual(sum(counts), PANEL_PIXELS)
                validate_frame(frame)

    def test_large_blocks_cover_six_colors_and_repeat_at_matching_half_coordinates(self) -> None:
        for orientation in ("horizontal", "vertical-mirrored"):
            with self.subTest(orientation=orientation):
                frame = generate_large_blocks_frame(orientation)
                counts = known_pixel_counts(frame)
                self.assertEqual({index for index, count in enumerate(counts) if count}, set(COLOR_ORDER))
                if orientation == "horizontal":
                    for y in range(HEIGHT):
                        row_start = y * ROW_BYTES
                        self.assertEqual(
                            frame[row_start : row_start + ROW_BYTES // 2],
                            frame[row_start + ROW_BYTES // 2 : row_start + ROW_BYTES],
                        )
                else:
                    self.assertNotEqual(
                        frame[: ROW_BYTES // 2],
                        frame[ROW_BYTES // 2 : ROW_BYTES],
                    )
                    for x in range(WIDTH // 2):
                        self.assertEqual(frame_pixel(frame, x, 0), frame_pixel(frame, WIDTH - 1 - x, 0))

    def test_invalid_known_patterns_fail_closed(self) -> None:
        for code in (True, False, -1, 4, 7, 15, "1"):
            with self.subTest(code=code):
                with self.assertRaisesRegex(ExtendedColorContractError, "formal physical"):
                    generate_solid_frame(code)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ExtendedColorContractError, "orientation"):
            generate_large_blocks_frame("diagonal")


class TransitionMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = generate_transition_matrix_frames()

    def test_old_horizontal_and_target_vertical_cover_all_transitions_twice(self) -> None:
        rois = transition_rois()
        self.assertEqual(rois, self.matrix.rois)
        self.assertEqual(len(rois), 72)
        for controller in ("CS1", "CS2"):
            transitions = {
                (roi.old_code, roi.target_code)
                for roi in rois
                if roi.controller == controller
            }
            self.assertEqual(transitions, {(old, new) for old in COLOR_ORDER for new in COLOR_ORDER})

        for roi in rois:
            x = (roi.measurement.x0 + roi.measurement.x1) // 2
            y = (roi.measurement.y0 + roi.measurement.y1) // 2
            self.assertEqual(roi.measurement.width, 64)
            self.assertEqual(roi.measurement.height, 64)
            self.assertEqual(frame_pixel(self.matrix.initial, x, y), roi.old_code)
            self.assertEqual(frame_pixel(self.matrix.target, x, y), roi.target_code)

    def test_transition_layout_is_mirrored_by_local_half_coordinate(self) -> None:
        left = [roi for roi in self.matrix.rois if roi.logical_half == 0]
        right = [roi for roi in self.matrix.rois if roi.logical_half == 1]
        self.assertEqual(len(left), 36)
        self.assertEqual(len(right), 36)
        for left_roi, right_roi in zip(left, right):
            self.assertEqual(
                (left_roi.old_code, left_roi.target_code),
                (right_roi.old_code, right_roi.target_code),
            )
            self.assertEqual(right_roi.cell.x0, WIDTH - left_roi.cell.x1)
            self.assertEqual(right_roi.cell.x1, WIDTH - left_roi.cell.x0)
            self.assertEqual(
                right_roi.measurement.x0,
                WIDTH - left_roi.measurement.x1,
            )
            self.assertEqual(
                right_roi.measurement.x1,
                WIDTH - left_roi.measurement.x0,
            )
            self.assertEqual(right_roi.measurement.y0, left_roi.measurement.y0)

        for x in range(WIDTH // 2):
            self.assertEqual(
                frame_pixel(self.matrix.target, x, 0),
                frame_pixel(self.matrix.target, WIDTH - 1 - x, 0),
            )

    def test_repetition_rotates_both_axes_and_preserves_36_by_2_coverage(self) -> None:
        initial_hashes = set()
        target_hashes = set()
        for repetition in range(1, 7):
            with self.subTest(repetition=repetition):
                matrix = generate_transition_matrix_frames(repetition)
                expected_old, expected_target = transition_color_orders(repetition)
                self.assertEqual(matrix.old_order, expected_old)
                self.assertEqual(matrix.target_order, expected_target)
                initial_hashes.add(hashlib.sha256(matrix.initial).hexdigest())
                target_hashes.add(hashlib.sha256(matrix.target).hexdigest())
                for controller in ("CS1", "CS2"):
                    self.assertEqual(
                        {
                            (roi.old_code, roi.target_code)
                            for roi in matrix.rois
                            if roi.controller == controller
                        },
                        {(old, new) for old in COLOR_ORDER for new in COLOR_ORDER},
                    )
                for roi in matrix.rois:
                    x = (roi.measurement.x0 + roi.measurement.x1) // 2
                    y = (roi.measurement.y0 + roi.measurement.y1) // 2
                    self.assertEqual(frame_pixel(matrix.initial, x, y), roi.old_code)
                    self.assertEqual(frame_pixel(matrix.target, x, y), roi.target_code)
                report = build_artifact("transition-target", repetition).report()[
                    "transition_matrix"
                ]
                self.assertEqual(report["old_order_top_to_bottom"], list(expected_old))
                self.assertEqual(
                    report["target_order_cs1_left_to_right"],
                    list(expected_target),
                )
                self.assertEqual(
                    report["target_order_cs2_left_to_right"],
                    list(reversed(expected_target)),
                )
        self.assertEqual(len(initial_hashes), 6)
        self.assertEqual(len(target_hashes), 6)
        self.assertEqual(
            generate_transition_matrix_frames(7).initial,
            generate_transition_matrix_frames(1).initial,
        )

    def test_transition_frames_remain_formal_six_color_frames(self) -> None:
        validate_frame(self.matrix.initial)
        validate_frame(self.matrix.target)
        self.assertEqual(len(self.matrix.initial), FRAME_BYTES)
        self.assertEqual(len(self.matrix.target), FRAME_BYTES)


class IdentityTests(unittest.TestCase):
    def test_frame_and_both_dtm_hashes_are_recomputed_from_bytes(self) -> None:
        artifact = build_artifact("transition-target")
        identity = artifact.identity
        self.assertEqual(identity.frame_sha256, hashlib.sha256(artifact.frame).hexdigest())
        self.assertEqual(identity.frame_fnv1a, fnv1a(artifact.frame))
        self.assertEqual([entry.controller for entry in identity.controllers], ["CS1", "CS2"])
        for entry, mapping in zip(identity.controllers, DEFAULT_CONTROLLER_MAPPINGS):
            stream = controller_stream(artifact.frame, mapping)
            self.assertEqual(entry.mapping, mapping)
            self.assertEqual(entry.dtm_sha256, hashlib.sha256(stream).hexdigest())
            self.assertEqual(entry.dtm_fnv1a, fnv1a(stream))

    def test_research_pattern_hashes_and_ids_are_frozen(self) -> None:
        for pattern, expected in FIXED_IDENTITIES.items():
            with self.subTest(pattern=pattern):
                artifact = build_artifact(pattern)
                self.assertEqual(artifact.identity.frame_sha256, expected["frame_sha256"])
                self.assertEqual(artifact.identity.frame_fnv1a, expected["frame_fnv1a"])
                for index, controller in enumerate(artifact.identity.controllers, start=1):
                    self.assertEqual(controller.dtm_sha256, expected[f"cs{index}_sha256"])
                    self.assertEqual(controller.dtm_fnv1a, expected[f"cs{index}_fnv1a"])
                self.assertEqual(artifact.test_id, expected["test_id"])

    def test_test_id_is_deterministic_and_repetition_sensitive(self) -> None:
        first = build_artifact("solid-white", 1)
        repeated = build_artifact("solid-white", 2)
        self.assertEqual(first.test_id, build_artifact("solid-white", 1).test_id)
        self.assertNotEqual(first.test_id, repeated.test_id)
        self.assertEqual(
            first.test_id,
            deterministic_test_id("EC2", "solid-white", 1, first.identity.canonical_sha256),
        )

    def test_bad_test_identity_inputs_are_rejected(self) -> None:
        digest = "0" * 64
        for stage, case, repetition, fingerprint in (
            ("bad stage", "case", 1, digest),
            ("EC2", "bad_case", 1, digest),
            ("EC2", "case", 0, digest),
            ("EC2", "case", True, digest),
            ("EC2", "case", 1, "A" * 64),
        ):
            with self.subTest(stage=stage, case=case, repetition=repetition):
                with self.assertRaises(ExtendedColorContractError):
                    deterministic_test_id(stage, case, repetition, fingerprint)  # type: ignore[arg-type]


class UnknownProbeTests(unittest.TestCase):
    def test_only_0x4_and_0x7_have_the_exact_two_roi_layout(self) -> None:
        for code in UNKNOWN_CODES:
            with self.subTest(code=code):
                frame = generate_unknown_probe_frame(code)
                rois = unknown_probe_rois(code)
                counts = pixel_counts(frame, allowed_colors=(*COLOR_ORDER, code))
                self.assertEqual(len(rois), 2)
                self.assertEqual(
                    [roi.measurement.to_dict() for roi in rois],
                    [
                        {"x0": 224, "y0": 268, "x1": 288, "y1": 332, "width": 64, "height": 64, "pixels": 4096},
                        {"x0": 736, "y0": 268, "x1": 800, "y1": 332, "width": 64, "height": 64, "pixels": 4096},
                    ],
                )
                self.assertEqual(
                    [roi.guard_outer.to_dict() for roi in rois],
                    [
                        {"x0": 192, "y0": 236, "x1": 320, "y1": 364, "width": 128, "height": 128, "pixels": 16384},
                        {"x0": 704, "y0": 236, "x1": 832, "y1": 364, "width": 128, "height": 128, "pixels": 16384},
                    ],
                )
                self.assertEqual(counts[code], UNKNOWN_TOTAL_PIXELS)
                self.assertEqual(counts[1], PANEL_PIXELS - UNKNOWN_TOTAL_PIXELS)
                self.assertEqual(sum(counts), PANEL_PIXELS)
                self.assertAlmostEqual(UNKNOWN_AREA_FRACTION, 0.013333333333333334)
                self.assertEqual(frame_pixel(frame, 224, 268), code)
                self.assertEqual(frame_pixel(frame, 736, 268), code)
                self.assertEqual(frame_pixel(frame, 223, 268), 1)
                self.assertEqual(frame_pixel(frame, 288, 268), 1)
                self.assertEqual(frame_pixel(frame, 224, 267), 1)
                self.assertEqual(frame_pixel(frame, 224, 332), 1)
                validate_unknown_probe_frame(frame, code)

    def test_formal_guard_still_rejects_every_unknown_probe(self) -> None:
        for code in UNKNOWN_CODES:
            frame = generate_unknown_probe_frame(code)
            with self.subTest(code=code):
                with self.assertRaisesRegex(FrameContractError, "unsupported physical"):
                    validate_frame(frame)
                with self.assertRaisesRegex(ExtendedColorContractError, "identity input"):
                    frame_identity(frame)
                report = build_artifact(f"unknown-0x{code:X}".lower()).report()
                self.assertFalse(report["safety"]["formal_api_compatible"])
                self.assertFalse(report["unknown_probe"]["release_build_enabled"])
                self.assertFalse(report["unknown_probe"]["arbitrary_raw_unknown_frame_accepted"])

    def test_unknown_code_and_arbitrary_layout_negatives_fail_closed(self) -> None:
        for code in (True, False, -1, 0, 1, 5, 8, 15, "4"):
            with self.subTest(code=code):
                with self.assertRaisesRegex(ExtendedColorContractError, "exactly 0x4 or 0x7"):
                    generate_unknown_probe_frame(code)  # type: ignore[arg-type]

        frame = bytearray(generate_unknown_probe_frame(4))
        frame[0] = 0x00
        with self.assertRaisesRegex(ExtendedColorContractError, "fixed layout"):
            validate_unknown_probe_frame(bytes(frame), 4)
        with self.assertRaisesRegex(ExtendedColorContractError, "invalid|fixed layout"):
            validate_unknown_probe_frame(generate_unknown_probe_frame(7), 4)


class ArtifactReportTests(unittest.TestCase):
    def test_every_named_pattern_has_an_offline_non_hardware_report(self) -> None:
        for pattern in PATTERN_NAMES:
            with self.subTest(pattern=pattern):
                artifact = build_artifact(pattern)
                report = artifact.report()
                self.assertEqual(report["pattern"], pattern)
                self.assertFalse(report["hardware_tested"])
                self.assertTrue(report["offline_only"])
                self.assertFalse(report["device_io_performed"])
                self.assertFalse(report["network_io_performed"])
                self.assertFalse(report["safety"]["device_refresh_capability"])
                self.assertEqual(report["identity"]["frame_sha256"], artifact.identity.frame_sha256)

    def test_unknown_pattern_and_bad_repetition_are_rejected(self) -> None:
        with self.assertRaisesRegex(ExtendedColorContractError, "unknown pattern"):
            build_artifact("unknown-0x8")
        for repetition in (0, 1000, True, "1"):
            with self.subTest(repetition=repetition):
                with self.assertRaisesRegex(ExtendedColorContractError, "repetition"):
                    build_artifact("solid-white", repetition)  # type: ignore[arg-type]


class OfflineCliTests(unittest.TestCase):
    def test_cli_writes_new_frame_and_report_but_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame_path = root / "matrix.bin"
            report_path = root / "matrix.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = tool.main(
                    [
                        "--pattern",
                        "transition-target",
                        "--output",
                        str(frame_path),
                        "--report-output",
                        str(report_path),
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(frame_path.read_bytes(), build_artifact("transition-target").frame)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["pattern"], "transition-target")
            self.assertEqual(json.loads(stdout.getvalue()), report)

            original_frame = frame_path.read_bytes()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = tool.main(
                    ["--pattern", "solid-black", "--output", str(frame_path)]
                )
            self.assertEqual(status, 2)
            self.assertIn("overwrite is not supported", stderr.getvalue())
            self.assertEqual(frame_path.read_bytes(), original_frame)

    def test_cli_has_no_network_or_arbitrary_unknown_code_option(self) -> None:
        for forbidden in ("--url", "--refresh", "--unknown-code"):
            with self.subTest(forbidden=forbidden):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        tool.parse_args(["--pattern", "solid-white", forbidden, "value"])
                self.assertEqual(raised.exception.code, 2)

    def test_output_safety_rejects_protected_missing_and_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(tool.OutputSafetyError, r"\.test-output"):
                tool.validate_output_path(root / ".test-output" / "frame.bin")
            with self.assertRaisesRegex(tool.OutputSafetyError, "parent directory"):
                tool.validate_output_path(root / "missing" / "frame.bin")

            same = root / "same.bin"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = tool.main(
                    [
                        "--pattern",
                        "solid-white",
                        "--output",
                        str(same),
                        "--report-output",
                        str(same),
                    ]
                )
            self.assertEqual(status, 2)
            self.assertFalse(same.exists())

        protected = tool.FROZEN_PRODUCTION_DIR / "extended-color-test.bin"
        with self.assertRaisesRegex(tool.OutputSafetyError, "frozen production"):
            tool.validate_output_path(protected)


if __name__ == "__main__":
    unittest.main()
