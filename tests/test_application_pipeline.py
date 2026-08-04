from __future__ import annotations

import importlib.util
import unittest

from host.application import (
    ApplicationArtifact,
    ApplicationError,
    FitPolicy,
    InputSource,
    PreparationPurpose,
    normalize_raster,
    prepare_image,
    validate_application_frame,
)
from host.color_pipeline import PipelineOptions, RasterImage
from host.epd_frame import FRAME_BYTES, HEIGHT, PHYSICAL_COLOR_CODES, WIDTH, unpack_pixels


class ApplicationPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # A fully transparent input exercises C2's linear-light white
        # composition and text mode keeps this full-panel regression fast.
        cls.raster = RasterImage(1, 1, "RGBA", bytes((0, 0, 0, 0)))
        cls.source = InputSource.from_bytes(
            "synthetic-transparent", "application/x-synthetic-rgba", cls.raster.pixels
        )
        cls.options = PipelineOptions(text_mode=True)
        cls.first = prepare_image(
            cls.raster,
            cls.source,
            fit=FitPolicy.STRETCH,
            options=cls.options,
            purpose=PreparationPurpose.OFFLINE_PREVIEW,
        )
        cls.second = prepare_image(
            cls.raster,
            cls.source,
            fit=FitPolicy.STRETCH,
            options=cls.options,
            purpose=PreparationPurpose.OFFLINE_PREVIEW,
        )

    def test_panel_output_is_exact_and_uses_only_physical_codes(self) -> None:
        self.assertEqual(len(self.first.frame), FRAME_BYTES)
        self.assertEqual(
            (self.first.report["output"]["width"], self.first.report["output"]["height"]),
            (WIDTH, HEIGHT),
        )
        self.assertEqual(set(unpack_pixels(self.first.frame)), {1})
        self.assertLessEqual(set(unpack_pixels(self.first.frame)), set(PHYSICAL_COLOR_CODES))
        self.assertEqual(
            [item["code"] for item in self.first.report["output"]["usage"]],
            sorted(PHYSICAL_COLOR_CODES),
        )

    def test_transparent_pixels_are_composited_to_white_by_c2(self) -> None:
        self.assertEqual(self.first.frame, bytes((0x11,)) * FRAME_BYTES)
        self.assertEqual(
            self.first.report["normalization"]["rgba_alpha_composition"],
            "C2 linear-light composition onto white",
        )

    def test_same_input_and_options_are_deterministic(self) -> None:
        self.assertEqual(self.first.frame, self.second.frame)
        self.assertEqual(self.first.preview_png, self.second.preview_png)
        self.assertEqual(
            self.first.report["output"]["sha256"], self.second.report["output"]["sha256"]
        )

    @unittest.skipUnless(importlib.util.find_spec("PIL") is not None, "optional Pillow missing")
    def test_optional_pillow_decoder_can_decode_generated_synthetic_png(self) -> None:
        from host.application import PillowImageDecoder

        decoded = PillowImageDecoder().decode(self.first.preview_png)
        self.assertEqual((decoded.width, decoded.height, decoded.mode), (WIDTH, HEIGHT, "RGB"))

    def test_reference_palette_is_offline_only_and_never_silently_authorized(self) -> None:
        self.assertFalse(self.first.upload_authorized)
        self.assertFalse(self.first.report["formal_upload_authorized"])
        self.assertFalse(self.first.report["palette_provenance"]["calibrated"])
        self.assertEqual(
            self.first.report["authorization_reason"],
            "reference_palette_offline_preview_only",
        )
        with self.assertRaisesRegex(ApplicationError, "calibrated palette"):
            prepare_image(
                self.raster,
                self.source,
                options=self.options,
                purpose=PreparationPurpose.FORMAL_UPLOAD,
            )

    def test_report_contains_required_scoped_evidence_and_hardware_false(self) -> None:
        report = self.first.report
        self.assertEqual(report["schema"], "mf1750-application-report")
        self.assertEqual(report["version"], 1)
        self.assertEqual(report["input"]["sha256"], self.source.sha256)
        self.assertIn("palette_provenance", report)
        self.assertIn("quantization_options", report)
        self.assertEqual(report["output"]["bytes"], FRAME_BYTES)
        self.assertTrue(report["offline_verified"])
        self.assertFalse(report["protocol_verified"])
        self.assertIs(report["hardware_tested"], False)
        self.assertEqual(
            set(report["manual_confirmation_required"]),
            {
                "full_panel_visual_result",
                "power_supply_cv",
                "power_supply_current",
                "L1_L2_temperature",
            },
        )
        self.assertTrue(
            all(value is False for value in report["manual_confirmation_required"].values())
        )

    def test_frame_validation_rejects_wrong_lengths_and_illegal_codes(self) -> None:
        for invalid in (
            self.first.frame[:-1],
            self.first.frame + b"\x11",
            bytes((0x44,)) * FRAME_BYTES,
        ):
            with self.subTest(length=len(invalid), first=invalid[0]):
                with self.assertRaisesRegex(ApplicationError, "invalid canonical"):
                    validate_application_frame(invalid)
                with self.assertRaises(ApplicationError):
                    ApplicationArtifact(invalid, b"", {}, False)

    def test_normalization_supports_contain_cover_and_stretch(self) -> None:
        source = RasterImage(
            2,
            1,
            "RGB",
            bytes((255, 0, 0, 0, 0, 255)),
        )
        contain = normalize_raster(source, FitPolicy.CONTAIN, target_width=4, target_height=4)
        cover = normalize_raster(source, FitPolicy.COVER, target_width=2, target_height=2)
        stretch = normalize_raster(source, FitPolicy.STRETCH, target_width=4, target_height=2)
        self.assertEqual(contain.pixels[:12], bytes((255, 255, 255)) * 4)
        self.assertEqual((cover.width, cover.height), (2, 2))
        self.assertEqual(cover.pixels[:6], bytes((255, 0, 0, 0, 0, 255)))
        self.assertEqual(stretch.pixels[:12], bytes((255, 0, 0)) * 2 + bytes((0, 0, 255)) * 2)


if __name__ == "__main__":
    unittest.main()
