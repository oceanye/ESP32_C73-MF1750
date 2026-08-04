from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
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
from host.color_pipeline import (
    CalibrationProvenance,
    Palette,
    PipelineOptions,
    RasterImage,
    reference_palette,
)
from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    fnv1a,
    unpack_pixels,
)


def _resign_c2_report(report: dict[str, object]) -> None:
    unsigned = copy.deepcopy(report)
    del unsigned["report_integrity"]
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_integrity"]["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()  # type: ignore[index]


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
        self.assertIn("quantization_report", report)
        self.assertEqual(report["quantization_report"]["schema_version"], 2)
        self.assertEqual(
            report["quantization_report"]["frame_sha256"],
            report["output"]["sha256"],
        )
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

    def test_artifact_snapshots_mutable_buffers_report_and_identity(self) -> None:
        frame = bytearray(self.first.frame)
        preview = bytearray(self.first.preview_png)
        report = self.first.report
        artifact = ApplicationArtifact(frame, preview, report, False)
        original_frame = artifact.frame
        original_preview = artifact.preview_png
        original_report_hash = artifact.identity["report_sha256"]

        frame[0] = 0x00
        preview[0] ^= 0xFF
        report["output"]["sha256"] = "0" * 64
        exposed_report = artifact.report
        exposed_report["output"]["sha256"] = "f" * 64
        exposed_identity = artifact.identity
        exposed_identity["frame_fnv1a"] = 0

        self.assertIs(type(artifact.frame), bytes)
        self.assertIs(type(artifact.preview_png), bytes)
        self.assertEqual(artifact.frame, original_frame)
        self.assertEqual(artifact.preview_png, original_preview)
        self.assertEqual(
            artifact.report["output"]["sha256"], hashlib.sha256(original_frame).hexdigest()
        )
        self.assertEqual(artifact.identity["frame_fnv1a"], fnv1a(original_frame))
        self.assertEqual(artifact.identity["report_sha256"], original_report_hash)

    def test_application_and_c2_frame_hash_mismatches_are_rejected(self) -> None:
        application_sha = self.first.report
        application_sha["output"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ApplicationError, "output hash"):
            ApplicationArtifact(self.first.frame, b"", application_sha, False)

        application_fnv = self.first.report
        application_fnv["output"]["fnv1a"] = "0x00000000"
        with self.assertRaisesRegex(ApplicationError, "output fnv1a"):
            ApplicationArtifact(self.first.frame, b"", application_fnv, False)

        c2_sha = self.first.report
        c2_sha["quantization_report"]["frame_sha256"] = "0" * 64
        _resign_c2_report(c2_sha["quantization_report"])
        with self.assertRaisesRegex(ApplicationError, "quantization report frame sha256"):
            ApplicationArtifact(self.first.frame, b"", c2_sha, False)

        c2_fnv = self.first.report
        c2_fnv["quantization_report"]["frame_fnv1a"] = "0x00000000"
        _resign_c2_report(c2_fnv["quantization_report"])
        with self.assertRaisesRegex(ApplicationError, "quantization report frame fnv1a"):
            ApplicationArtifact(self.first.frame, b"", c2_fnv, False)

    def test_tampered_c2_integrity_palette_hash_and_provenance_are_rejected(self) -> None:
        integrity = self.first.report
        integrity["quantization_report"]["options"]["seed"] ^= 1
        with self.assertRaisesRegex(ApplicationError, "integrity hash"):
            ApplicationArtifact(self.first.frame, b"", integrity, False)

        palette_hash = self.first.report
        palette_hash["quantization_report"]["palette"]["canonical_sha256"] = "0" * 64
        _resign_c2_report(palette_hash["quantization_report"])
        palette_hash["palette_provenance"] = copy.deepcopy(
            palette_hash["quantization_report"]["palette"]
        )
        with self.assertRaisesRegex(ApplicationError, "palette canonical hash"):
            ApplicationArtifact(self.first.frame, b"", palette_hash, False)

        forged = self.first.report
        c2 = forged["quantization_report"]
        c2["palette"]["calibrated"] = True
        c2["palette"]["calibration"] = {
            "measurement_id": "claimed-without-a-valid-artifact",
            "artifact_sha256": "not-a-sha256",
        }
        c2["safety"].update(
            {
                "palette_calibrated": True,
                "allow_uncalibrated_palette": False,
                "authorization_reason": "calibrated_palette",
            }
        )
        _resign_c2_report(c2)
        forged["palette_provenance"] = copy.deepcopy(c2["palette"])
        forged["purpose"] = PreparationPurpose.FORMAL_UPLOAD.value
        forged["formal_upload_authorized"] = True
        forged["authorization_reason"] = "calibrated_palette"
        with self.assertRaisesRegex(ApplicationError, "64 hex digits"):
            ApplicationArtifact(self.first.frame, b"", forged, True)

    def test_formal_upload_requires_formal_purpose_and_complete_calibrated_c2_report(self) -> None:
        reference = reference_palette()
        calibrated = Palette(
            "application-formal-test",
            reference.entries,
            True,
            "controlled application test measurement",
            calibration=CalibrationProvenance("application-test-run", "a" * 64),
        )
        preview_only = prepare_image(
            self.raster,
            self.source,
            fit=FitPolicy.STRETCH,
            palette=calibrated,
            options=self.options,
            purpose=PreparationPurpose.OFFLINE_PREVIEW,
        )
        formal = prepare_image(
            self.raster,
            self.source,
            fit=FitPolicy.STRETCH,
            palette=calibrated,
            options=self.options,
            purpose=PreparationPurpose.FORMAL_UPLOAD,
        )
        self.assertFalse(preview_only.upload_authorized)
        self.assertEqual(
            preview_only.report["authorization_reason"],
            "calibrated_palette_offline_preview_only",
        )
        self.assertTrue(formal.upload_authorized)
        self.assertEqual(formal.report["purpose"], "formal_upload")
        self.assertEqual(
            formal.report["quantization_report"]["palette"]["calibration"],
            {
                "measurement_id": "application-test-run",
                "artifact_sha256": "a" * 64,
            },
        )
        self.assertEqual(
            set(formal.identity),
            {"frame_sha256", "frame_fnv1a", "frame_bytes", "report_sha256"},
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
