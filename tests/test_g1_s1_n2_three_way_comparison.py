from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from host.epd_frame import HEIGHT, WIDTH, unpack_pixels
from tools import g1_s1_n2_three_way_comparison as comparison


class ThreeWayComparisonTests(unittest.TestCase):
    def test_build_is_exact_same_crop_one_to_one(self) -> None:
        payloads = comparison.compile_bundle()
        manifest = json.loads(payloads["manifest.json"])
        self.assertEqual(len(payloads["frame.bin"]), WIDTH * HEIGHT // 2)
        self.assertEqual(manifest["legend"], [
            "left=Q1 Atkinson",
            "middle=Q3 multicolor DBS",
            "right=Q4 overlap-aware DBS",
        ])
        self.assertFalse(manifest["scope"]["device_io_performed"])
        self.assertFalse(manifest["scope"]["visible_refresh_authorized"])

        output_codes = unpack_pixels(payloads["frame.bin"], WIDTH, HEIGHT)
        for spec in comparison.SOURCE_SPECS:
            source = unpack_pixels(
                (comparison._source_dir(spec) / "frame.bin").read_bytes(), WIDTH, HEIGHT
            )
            destination_x = spec["destination_x"]
            for y in (0, HEIGHT // 2, HEIGHT - 1):
                source_start = y * WIDTH + comparison.CROP_X
                destination_start = y * WIDTH + destination_x
                self.assertEqual(
                    output_codes[
                        destination_start : destination_start + comparison.CROP_WIDTH
                    ],
                    source[
                        source_start : source_start + comparison.CROP_WIDTH
                    ],
                )

    def test_written_bundle_deep_validates_and_tamper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "comparison"
            result = comparison.write_bundle(output)
            self.assertTrue(result["valid"])
            frame_path = output / "frame.bin"
            frame = bytearray(frame_path.read_bytes())
            frame[0] ^= 0x10
            frame_path.write_bytes(frame)
            with self.assertRaisesRegex(
                comparison.ThreeWayComparisonError,
                "frame.bin differs from deep regeneration",
            ):
                comparison.validate_bundle(output)


if __name__ == "__main__":
    unittest.main()
