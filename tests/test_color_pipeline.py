from __future__ import annotations

import binascii
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from host.color_pipeline import (
    CalibrationProvenance,
    ColorPipelineError,
    ColorValueError,
    DitherMode,
    Palette,
    PaletteEntry,
    PaletteError,
    PipelineOptions,
    RasterImage,
    delta_e_ciede2000,
    load_palette,
    palette_from_mapping,
    quantize_image,
    quantize_panel_image,
    reference_palette,
    srgb8_to_lab,
)
from host.color_pipeline import color as color_math
from host.color_pipeline.color import linear_channel_to_srgb, srgb_channel_to_linear
from host.color_pipeline.pipeline import _clamp_rgb, _edge_mask, _nearest_two, _pixel_linear
from host.epd_frame import FRAME_BYTES, HEIGHT, WIDTH, unpack_pixels


class ColorMathTests(unittest.TestCase):
    def test_srgb_transfer_and_primary_lab_vectors(self) -> None:
        self.assertEqual(srgb_channel_to_linear(0.0), 0.0)
        self.assertAlmostEqual(
            srgb_channel_to_linear(0.04045), 0.0031308049535603713, delta=1e-15
        )
        self.assertEqual(srgb_channel_to_linear(1.0), 1.0)
        self.assertAlmostEqual(
            srgb_channel_to_linear(128 / 255), 0.21586050011389926, delta=1e-15
        )
        vectors = {
            (0, 0, 0): (0.0, 0.0, 0.0),
            (255, 0, 0): (53.2407941413, 80.0924595964, 67.2031965159),
            (0, 255, 0): (87.7347223528, -86.1827164205, 83.1793205027),
            (0, 0, 255): (32.2970109329, 79.1875198451, -107.8601617541),
            (128, 128, 128): (53.5850157717, -0.00000999785, 0.00000399914),
        }
        for rgb, expected in vectors.items():
            actual = srgb8_to_lab(rgb)
            for component, target in zip(actual, expected):
                self.assertAlmostEqual(component, target, delta=1e-6)

    def test_ciede2000_sharma_34_pair_supplement(self) -> None:
        pairs = (
            ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
            ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
            ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
            ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
            ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
            ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
            ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
            ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
            ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
            ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
            ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
            ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
            ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
            ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
            ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
            ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
            ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
            ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
            ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
            ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
            ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
            ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
            ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
            ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
            ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
            ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
            ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
            ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
            ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
            ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
            ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
            ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
            ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
            ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
        )
        for first, second, expected in pairs:
            forward = delta_e_ciede2000(first, second)
            reverse = delta_e_ciede2000(second, first)
            self.assertAlmostEqual(forward, expected, delta=1e-4)
            self.assertAlmostEqual(reverse, expected, delta=1e-4)
            self.assertAlmostEqual(forward, reverse, delta=1e-12)
        self.assertEqual(delta_e_ciede2000((42, 1, -2), (42, 1, -2)), 0.0)

    def test_public_numeric_inputs_reject_bool_strings_and_nonfinite_values(self) -> None:
        for invalid in (True, "0.5", math.nan, math.inf, -math.inf):
            with self.subTest(channel=invalid):
                with self.assertRaises(ColorValueError):
                    srgb_channel_to_linear(invalid)  # type: ignore[arg-type]
                with self.assertRaises(ColorValueError):
                    linear_channel_to_srgb(invalid)  # type: ignore[arg-type]

        triple_functions = (
            color_math.linear_rgb_to_xyz,
            color_math.xyz_to_linear_rgb,
            color_math.xyz_to_lab,
            color_math.lab_to_xyz,
            color_math.linear_rgb_to_lab,
            color_math.lab_to_linear_rgb,
            color_math.lab_to_srgb8,
        )
        invalid_triples = (
            (True, 0.0, 0.0),
            ("0", 0.0, 0.0),
            (math.nan, 0.0, 0.0),
            (math.inf, 0.0, 0.0),
        )
        for function in triple_functions:
            for invalid in invalid_triples:
                with self.subTest(function=function.__name__, triple=invalid):
                    with self.assertRaises(ColorValueError):
                        function(invalid)  # type: ignore[arg-type]
        for invalid in invalid_triples:
            with self.assertRaises(ColorValueError):
                delta_e_ciede2000(invalid, (0.0, 0.0, 0.0))  # type: ignore[arg-type]
            with self.assertRaises(ColorValueError):
                color_math.srgb8_to_linear_rgb(invalid)  # type: ignore[arg-type]
            with self.assertRaises(ColorValueError):
                color_math.srgb8_to_lab(invalid)  # type: ignore[arg-type]

        self.assertEqual(linear_channel_to_srgb(-1.0), 0.0)
        self.assertAlmostEqual(linear_channel_to_srgb(2.0), 1.0)
        for invalid_clamp in (1, "yes", None):
            with self.assertRaisesRegex(ColorValueError, "clamp must be boolean"):
                color_math.lab_to_linear_rgb(
                    (0.0, 0.0, 0.0), clamp=invalid_clamp  # type: ignore[arg-type]
                )


class PaletteTests(unittest.TestCase):
    def test_reference_palette_is_explicitly_uncalibrated_d65_2deg(self) -> None:
        palette = reference_palette()
        self.assertFalse(palette.calibrated)
        self.assertIsNone(palette.calibration)
        self.assertEqual(palette.canonical_mapping()["schema_version"], 2)
        self.assertIsNone(palette.canonical_mapping()["calibration"])
        self.assertEqual(palette.illuminant, "D65")
        self.assertEqual(palette.observer, "2deg")
        self.assertIn("not MF-1750", palette.source)
        self.assertEqual([entry.code for entry in palette.entries], [0, 1, 2, 3, 5, 6])

    def test_palette_loader_accepts_measured_profile_and_rejects_wrong_observer(self) -> None:
        reference = reference_palette()
        mapping = {
            "schema_version": 2,
            "palette_id": "measured-example",
            "calibrated": True,
            "source": "controlled patch measurement 2026-08-04",
            "illuminant": "D65",
            "observer": "2deg",
            "calibration": {
                "measurement_id": "mf1750-test-measurement-2026-08-04",
                "artifact_sha256": "a" * 64,
            },
            "entries": [
                {
                    "code": entry.code,
                    "name": entry.name,
                    "lab": list(entry.lab),
                    "preview_rgb": list(entry.preview_rgb),
                }
                for entry in reversed(reference.entries)
            ],
        }
        palette = palette_from_mapping(mapping)
        self.assertTrue(palette.calibrated)
        self.assertEqual([entry.code for entry in palette.entries], [0, 1, 2, 3, 5, 6])
        mapping["observer"] = "10deg"
        with self.assertRaisesRegex(PaletteError, "D65/2deg"):
            palette_from_mapping(mapping)

    def test_calibrated_palette_cannot_swap_physical_black_and_white_codes(self) -> None:
        reference = reference_palette()
        swapped_codes = {0: 1, 1: 0}
        mapping = {
            "schema_version": 2,
            "palette_id": "invalid-swapped-black-white",
            "calibrated": True,
            "source": "negative regression fixture",
            "illuminant": "D65",
            "observer": "2deg",
            "calibration": {
                "measurement_id": "invalid-swap",
                "artifact_sha256": "b" * 64,
            },
            "entries": [
                {
                    "code": swapped_codes.get(entry.code, entry.code),
                    "name": entry.name,
                    "lab": list(entry.lab),
                    "preview_rgb": list(entry.preview_rgb),
                }
                for entry in reference.entries
            ],
        }
        with self.assertRaisesRegex(
            PaletteError, "physical colour code [01] must be named"
        ):
            palette_from_mapping(mapping)

    def test_palette_rejects_lab_only_semantic_swaps(self) -> None:
        reference_mapping = reference_palette().canonical_mapping()
        cases = (
            (0, 1, "black Lab L\\* must be lower"),
            (3, 6, "red Lab a\\* must be greater"),
            (2, 5, "yellow Lab b\\* must be greater"),
        )
        for first_code, second_code, message in cases:
            mapping = copy.deepcopy(reference_mapping)
            mapping["palette_id"] = f"invalid-lab-swap-{first_code}-{second_code}"
            entries = {entry["code"]: entry for entry in mapping["entries"]}
            entries[first_code]["lab"], entries[second_code]["lab"] = (
                entries[second_code]["lab"],
                entries[first_code]["lab"],
            )
            with self.subTest(codes=(first_code, second_code)):
                with self.assertRaisesRegex(PaletteError, message):
                    palette_from_mapping(mapping)

    def test_palette_schema_v2_requires_structured_calibration_provenance(self) -> None:
        reference_mapping = reference_palette().canonical_mapping()
        for invalid_version in (True, 1.0, 2.0, 1):
            mapping = copy.deepcopy(reference_mapping)
            mapping["schema_version"] = invalid_version
            with self.subTest(schema_version=invalid_version):
                with self.assertRaisesRegex(PaletteError, "integer 2"):
                    palette_from_mapping(mapping)

        missing = copy.deepcopy(reference_mapping)
        del missing["calibration"]
        with self.assertRaisesRegex(PaletteError, "explicit calibration"):
            palette_from_mapping(missing)

        calibrated = copy.deepcopy(reference_mapping)
        calibrated["calibrated"] = True
        calibrated["source"] = "controlled test measurement"
        with self.assertRaisesRegex(PaletteError, "structured calibration"):
            palette_from_mapping(calibrated)
        calibrated["calibration"] = {
            "measurement_id": "mf1750-test-measurement",
            "artifact_sha256": "not-a-sha256",
        }
        with self.assertRaisesRegex(PaletteError, "64 hex digits"):
            palette_from_mapping(calibrated)
        calibrated["calibration"]["artifact_sha256"] = "C" * 64
        palette = palette_from_mapping(calibrated)
        self.assertTrue(palette.calibrated)
        self.assertEqual(
            palette.calibration,
            CalibrationProvenance("mf1750-test-measurement", "c" * 64),
        )

    def test_palette_file_errors_are_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(PaletteError, "cannot load"):
                load_palette(path)

    def test_public_palette_constructors_reject_invalid_values(self) -> None:
        with self.assertRaisesRegex(PaletteError, "lightness"):
            PaletteEntry(0, "black", (101.0, 0.0, 0.0), (0, 0, 0))
        with self.assertRaisesRegex(PaletteError, "finite"):
            PaletteEntry(0, "black", (0.0, math.nan, 0.0), (0, 0, 0))
        with self.assertRaisesRegex(PaletteError, "not boolean"):
            PaletteEntry(0, "black", (True, 0.0, 0.0), (0, 0, 0))
        with self.assertRaisesRegex(PaletteError, "integers"):
            PaletteEntry(0, "black", (0.0, 0.0, 0.0), (0, 0, 300))
        reference = reference_palette()
        with self.assertRaisesRegex(PaletteError, "calibrated"):
            Palette("bad", reference.entries, 1, "test")  # type: ignore[arg-type]
        with self.assertRaisesRegex(PaletteError, "exactly"):
            Palette("missing", reference.entries[:-1], False, "test")
        with self.assertRaisesRegex(PaletteError, "structured calibration"):
            Palette("missing-calibration", reference.entries, True, "test")
        with self.assertRaisesRegex(PaletteError, "not boolean"):
            reference.entry(True)
        with self.assertRaisesRegex(PaletteError, "numeric"):
            palette_from_mapping(
                {
                    "schema_version": 2,
                    "palette_id": "bad-lab-type",
                    "calibrated": False,
                    "source": "test",
                    "illuminant": "D65",
                    "observer": "2deg",
                    "calibration": None,
                    "entries": [
                        {
                            "code": entry.code,
                            "name": entry.name,
                            "lab": ["0", 0, 0] if entry.code == 0 else list(entry.lab),
                            "preview_rgb": list(entry.preview_rgb),
                        }
                        for entry in reference.entries
                    ],
                }
            )

    def test_equal_lab_tie_uses_lower_physical_code(self) -> None:
        reference = reference_palette()
        entries = tuple(
            PaletteEntry(entry.code, entry.name, (0.0, 0.0, 0.0), entry.preview_rgb)
            if entry.code == 2
            else entry
            for entry in reference.entries
        )
        tied = Palette("tie-test", entries, False, "deterministic tie test")
        for mode in DitherMode:
            result = quantize_image(
                RasterImage(8, 1, "RGB", bytes((0, 0, 0)) * 8),
                palette=tied,
                options=PipelineOptions(mode, preserve_edges=False),
            )
            self.assertEqual(result.codes, bytes((0,)) * 8)


def _gradient_image(width: int = 16, height: int = 12) -> RasterImage:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend(
                (
                    (x * 37 + y * 11) & 0xFF,
                    (x * 13 + y * 47) & 0xFF,
                    (x * 71 + y * 19) & 0xFF,
                )
            )
    return RasterImage(width, height, "RGB", bytes(pixels))


def _full_error_buffer_reference(
    image: RasterImage,
    mode: DitherMode,
    *,
    serpentine: bool,
) -> bytes:
    """Independent full-frame buffer oracle for the production ring buffer."""

    entries = reference_palette().entries
    diffusion_colours = tuple(entry.diffusion_rgb for entry in entries)
    width = image.width
    height = image.height
    errors = [[0.0] * (width * 3) for _ in range(height)]
    codes = bytearray(width * height)

    def add(target_x: int, target_y: int, residual: tuple[float, float, float], weight: float) -> None:
        if not (0 <= target_x < width and 0 <= target_y < height):
            return
        offset = target_x * 3
        errors[target_y][offset] += residual[0] * weight
        errors[target_y][offset + 1] += residual[1] * weight
        errors[target_y][offset + 2] += residual[2] * weight

    for y in range(height):
        direction = -1 if serpentine and (y & 1) else 1
        x_values = range(width - 1, -1, -1) if direction < 0 else range(width)
        for x in x_values:
            offset = x * 3
            source = _pixel_linear(image, y * width + x)[0]
            effective = _clamp_rgb(
                (
                    source[0] + errors[y][offset],
                    source[1] + errors[y][offset + 1],
                    source[2] + errors[y][offset + 2],
                )
            )
            selected = _nearest_two(effective, entries)[0]
            codes[y * width + x] = entries[selected].code
            palette_rgb = diffusion_colours[selected]
            residual = (
                effective[0] - palette_rgb[0],
                effective[1] - palette_rgb[1],
                effective[2] - palette_rgb[2],
            )
            if mode == DitherMode.FLOYD_STEINBERG:
                add(x + direction, y, residual, 7 / 16)
                add(x - direction, y + 1, residual, 3 / 16)
                add(x, y + 1, residual, 5 / 16)
                add(x + direction, y + 1, residual, 1 / 16)
            else:
                for target_x, target_y in (
                    (x + direction, y),
                    (x + 2 * direction, y),
                    (x - direction, y + 1),
                    (x, y + 1),
                    (x + direction, y + 1),
                    (x, y + 2),
                ):
                    add(target_x, target_y, residual, 1 / 8)
    return bytes(codes)


class QuantizationTests(unittest.TestCase):
    def test_exact_reference_colours_pack_through_c1_contract(self) -> None:
        palette = reference_palette()
        rgb = b"".join(bytes(entry.preview_rgb) for entry in palette.entries)
        image = RasterImage(6, 1, "RGB", rgb)
        result = quantize_image(
            image,
            palette=palette,
            options=PipelineOptions(dither=DitherMode.NONE, preserve_edges=False),
        )
        self.assertEqual(result.codes, bytes((0, 1, 2, 3, 5, 6)))
        self.assertEqual(unpack_pixels(result.frame, 6, 1), result.codes)

    def test_rgba_is_straight_alpha_composited_over_white(self) -> None:
        image = RasterImage(
            4,
            1,
            "RGBA",
            bytes((255, 0, 0, 0, 0, 0, 0, 0, 255, 0, 0, 255, 0, 0, 0, 255)),
        )
        result = quantize_image(
            image,
            options=PipelineOptions(dither=DitherMode.NONE, preserve_edges=False),
        )
        self.assertEqual(result.codes, bytes((1, 1, 3, 0)))
        half_black = RasterImage(2, 1, "RGBA", bytes((0, 0, 0, 128)) * 2)
        linear, alpha = _pixel_linear(half_black, 0)
        self.assertAlmostEqual(alpha, 128 / 255)
        for component in linear:
            self.assertAlmostEqual(component, 127 / 255)
        input_report = result.report.to_dict()["input_raster"]
        self.assertEqual(input_report["mode"], "RGBA")
        self.assertEqual(input_report["alpha"]["representation"], "straight")
        self.assertEqual(
            input_report["alpha"]["background_srgb8"],
            [255, 255, 255],
        )
        self.assertEqual(input_report["alpha"]["compositing_space"], "linear-light")
        self.assertTrue(input_report["alpha"]["applied"])
        self.assertTrue(input_report["caller_declaration"]["decoded_srgb8"])
        self.assertTrue(
            input_report["caller_declaration"]["rgba_alpha_is_straight"]
        )

    def test_report_v2_canonical_hash_and_palette_fingerprint_are_frozen(self) -> None:
        image = RasterImage(
            2,
            1,
            "RGBA",
            bytes((255, 0, 0, 128, 0, 0, 255, 0)),
        )
        result = quantize_image(
            image,
            options=PipelineOptions(DitherMode.NONE, preserve_edges=False),
        )
        report = result.report.to_dict()
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["pipeline"]["version"], "2.0.0")
        self.assertEqual(
            report["pipeline"]["build_id"],
            "mf1750-color-pipeline-v2-2026-08-04",
        )
        self.assertEqual(
            report["palette"]["canonical_sha256"],
            "181770a2de3bb23bcc31666573279c8cde8225d2f4c27a24c9c1345dba54965e",
        )
        self.assertEqual(
            report["palette"]["fingerprint_trust"],
            "audit fingerprint only; not a digital signature or trust-store decision",
        )
        integrity = report["report_integrity"]
        self.assertEqual(
            integrity["canonical_sha256"],
            "eb89dfe7edd0fe9cb1a3949de95bfaa5723ec7a63274fbfbed12fa5740c64cd1",
        )
        self.assertEqual(
            integrity["canonical_sha256_scope"],
            "entire report object excluding report_integrity; UTF-8 JSON with sorted "
            "keys, no whitespace, ensure_ascii=false, allow_nan=false",
        )
        unsigned_report = copy.deepcopy(report)
        del unsigned_report["report_integrity"]
        canonical_bytes = json.dumps(
            unsigned_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(canonical_bytes).hexdigest(),
        )

    def test_white_protection_and_text_mode(self) -> None:
        whiteish = RasterImage(4, 1, "RGB", bytes((250, 250, 250)) * 4)
        for mode in DitherMode:
            protected = quantize_image(
                whiteish,
                options=PipelineOptions(dither=mode, preserve_edges=False),
            )
            self.assertEqual(protected.codes, bytes((1, 1, 1, 1)))
        unprotected = quantize_image(
            whiteish,
            options=PipelineOptions(
                dither=DitherMode.ORDERED_BAYER,
                white_protection=False,
                preserve_edges=False,
            ),
        )
        self.assertNotEqual(unprotected.codes, bytes((1, 1, 1, 1)))
        grayscale = RasterImage(
            4, 1, "RGB", bytes((0, 0, 0, 80, 80, 80, 190, 190, 190, 255, 255, 255))
        )
        text = quantize_image(
            grayscale,
            options=PipelineOptions(
                dither=DitherMode.ATKINSON,
                text_mode=True,
                text_luminance_threshold=0.4,
            ),
        )
        self.assertEqual(text.codes, bytes((0, 0, 1, 1)))
        text_options = text.report.to_dict()["options"]
        self.assertEqual(text_options["dither"], DitherMode.NONE.value)
        self.assertEqual(text_options["requested_dither"], DitherMode.ATKINSON.value)
        self.assertFalse(text_options["edge_preservation"])
        self.assertTrue(text_options["requested_edge_preservation"])

    def test_all_modes_are_deterministic_and_report_usage(self) -> None:
        image = _gradient_image()
        for mode in DitherMode:
            options = PipelineOptions(mode, seed=12345, preserve_edges=False)
            first = quantize_image(image, options=options)
            second = quantize_image(image, options=options)
            self.assertEqual(first.frame, second.frame)
            self.assertEqual(first.preview_png(), second.preview_png())
            report = first.report.to_dict()
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["pipeline"]["version"], "2.0.0")
            self.assertEqual(
                report["pipeline"]["build_id"],
                "mf1750-color-pipeline-v2-2026-08-04",
            )
            self.assertEqual(report["input_raster"]["mode"], "RGB")
            self.assertEqual(report["input_raster"]["pixel_bytes"], len(image.pixels))
            self.assertEqual(
                report["input_raster"]["sha256"],
                hashlib.sha256(image.pixels).hexdigest(),
            )
            self.assertEqual(
                report["input_raster"]["transfer_function"],
                "IEC 61966-2-1 sRGB",
            )
            self.assertTrue(
                report["input_raster"]["caller_declaration"]["decoded_srgb8"]
            )
            self.assertIsNone(
                report["input_raster"]["caller_declaration"][
                    "rgba_alpha_is_straight"
                ]
            )
            self.assertEqual(report["input_raster"]["alpha"]["representation"], "absent")
            self.assertFalse(report["input_raster"]["alpha"]["applied"])
            self.assertFalse(report["safety"]["canonical_panel_dimensions"])
            self.assertFalse(report["safety"]["panel_frame_bytes_output"])
            self.assertFalse(report["safety"]["allow_uncalibrated_palette"])
            self.assertEqual(
                report["safety"]["authorization_reason"],
                "offline_non_panel_frame",
            )
            self.assertNotIn("panel_palette_authorized", report["safety"])
            self.assertFalse(report["hardware_tested"])
            self.assertEqual(report["palette"]["schema_version"], 2)
            self.assertFalse(report["palette"]["calibrated"])
            self.assertEqual(sum(item["count"] for item in report["usage"]), 16 * 12)
            self.assertAlmostEqual(sum(item["ratio"] for item in report["usage"]), 1.0)
            self.assertEqual(report["frame_sha256"], hashlib.sha256(first.frame).hexdigest())
            self.assertEqual(len(report["palette"]["entries"]), 6)
            self.assertEqual(report["options"]["white_luminance_threshold"], 0.95)

    def test_hashed_threshold_seed_changes_output_only_for_seeded_mode(self) -> None:
        image = _gradient_image(32, 16)
        first = quantize_image(
            image,
            options=PipelineOptions(DitherMode.HASHED_THRESHOLD, seed=1, preserve_edges=False),
        )
        second = quantize_image(
            image,
            options=PipelineOptions(DitherMode.HASHED_THRESHOLD, seed=2, preserve_edges=False),
        )
        self.assertNotEqual(first.frame, second.frame)
        ordered_one = quantize_image(
            image,
            options=PipelineOptions(DitherMode.ORDERED_BAYER, seed=1, preserve_edges=False),
        )
        ordered_two = quantize_image(
            image,
            options=PipelineOptions(DitherMode.ORDERED_BAYER, seed=2, preserve_edges=False),
        )
        self.assertEqual(ordered_one.frame, ordered_two.frame)

    def test_edge_preservation_keeps_exact_high_contrast_boundary(self) -> None:
        pixels = bytes((255, 0, 0)) * 8 + bytes((0, 255, 0)) * 8
        image = RasterImage(16, 1, "RGB", pixels)
        result = quantize_image(
            image,
            options=PipelineOptions(DitherMode.FLOYD_STEINBERG, preserve_edges=True),
        )
        self.assertEqual(result.codes, bytes((3,)) * 8 + bytes((6,)) * 8)

    def test_edge_mask_detects_similar_luminance_different_hues(self) -> None:
        # A luminance-only mask misses this boundary, while the linear-RGB
        # maximum-channel metric intentionally protects it.
        image = RasterImage(2, 1, "RGB", bytes((255, 0, 0, 0, 148, 0)))
        self.assertEqual(_edge_mask(image, 0.18), bytearray((1, 1)))

    def test_edge_preservation_switch_changes_boundary_diffusion(self) -> None:
        image = RasterImage(
            16,
            1,
            "RGB",
            bytes((240, 40, 40)) * 8 + bytes((0, 148, 0)) * 8,
        )
        protected = quantize_image(
            image,
            options=PipelineOptions(
                DitherMode.FLOYD_STEINBERG,
                white_protection=False,
                preserve_edges=True,
            ),
        )
        unprotected = quantize_image(
            image,
            options=PipelineOptions(
                DitherMode.FLOYD_STEINBERG,
                white_protection=False,
                preserve_edges=False,
            ),
        )
        self.assertNotEqual(protected.codes, unprotected.codes)
        self.assertEqual(protected.codes[7:10], bytes((3, 6, 6)))
        self.assertEqual(unprotected.codes[7:10], bytes((3, 6, 0)))

    def test_diffusion_ring_buffer_matches_independent_full_frame_oracle(self) -> None:
        image = _gradient_image(8, 7)
        for mode in (DitherMode.FLOYD_STEINBERG, DitherMode.ATKINSON):
            for serpentine in (False, True):
                result = quantize_image(
                    image,
                    options=PipelineOptions(
                        mode,
                        serpentine=serpentine,
                        white_protection=False,
                        preserve_edges=False,
                    ),
                )
                expected = _full_error_buffer_reference(
                    image, mode, serpentine=serpentine
                )
                self.assertEqual(result.codes, expected)

    def test_small_fixture_hashes_are_frozen_for_every_mode(self) -> None:
        expected = {
            # Filled from the deterministic implementation and reviewed as a
            # byte-level regression contract, not as a hardware colour claim.
            DitherMode.NONE: "8bff42b2d5b663203ef2ba84ce9924deb1358f0170a63a2532c08b471702ef62",
            DitherMode.FLOYD_STEINBERG: "661ecc4aa2fd6ad9647fa5d8f3d40349f9c7029cac302e72e602a1514aa32ce5",
            DitherMode.ATKINSON: "a35874b4dd5d1461fc98213456baa943419ce5e73b27bb580511027d7799d2fd",
            DitherMode.ORDERED_BAYER: "f4796bc5e2ad3a15a2d8abd3501492e316a5703afea0c6098aac7b7d233fdb80",
            DitherMode.HASHED_THRESHOLD: "0f053a4876b0e9e5f3b5075f6c8557276bc909a5852a918b2c9f79a38ae879fd",
        }
        image = _gradient_image()
        for mode, expected_hash in expected.items():
            result = quantize_image(
                image,
                options=PipelineOptions(mode, seed=0x12345678, preserve_edges=False),
            )
            self.assertEqual(hashlib.sha256(result.frame).hexdigest(), expected_hash)

    def test_panel_entry_returns_exact_307200_byte_white_frame(self) -> None:
        image = RasterImage(WIDTH, HEIGHT, "RGB", bytes((255, 255, 255)) * WIDTH * HEIGHT)
        for entry_point in (quantize_image, quantize_panel_image):
            with self.assertRaisesRegex(
                ColorPipelineError, "allow_uncalibrated_palette=True"
            ):
                entry_point(
                    image,
                    options=PipelineOptions(DitherMode.NONE, preserve_edges=False),
                )
        result = quantize_panel_image(
            image,
            options=PipelineOptions(DitherMode.NONE, preserve_edges=False),
            allow_uncalibrated_palette=True,
        )
        self.assertEqual(len(result.frame), FRAME_BYTES)
        self.assertEqual(result.frame, bytes((0x11,)) * FRAME_BYTES)
        safety = result.report.to_dict()["safety"]
        self.assertTrue(safety["canonical_panel_dimensions"])
        self.assertTrue(safety["panel_frame_bytes_output"])
        self.assertTrue(safety["allow_uncalibrated_palette"])
        self.assertEqual(
            safety["authorization_reason"],
            "explicit_uncalibrated_palette_opt_in",
        )
        self.assertNotIn("panel_palette_authorized", safety)

    def test_calibrated_panel_records_measurement_and_authorization_reason(self) -> None:
        image = RasterImage(WIDTH, HEIGHT, "RGB", bytes((255, 255, 255)) * WIDTH * HEIGHT)
        reference = reference_palette()
        calibrated = Palette(
            "controlled-test-palette",
            reference.entries,
            True,
            "controlled test measurement",
            calibration=CalibrationProvenance("test-measurement", "d" * 64),
        )
        result = quantize_panel_image(
            image,
            palette=calibrated,
            options=PipelineOptions(DitherMode.NONE, preserve_edges=False),
        )
        report = result.report.to_dict()
        self.assertEqual(
            report["safety"]["authorization_reason"], "calibrated_palette"
        )
        self.assertFalse(report["safety"]["allow_uncalibrated_palette"])
        self.assertEqual(
            report["palette"]["calibration"],
            {
                "measurement_id": "test-measurement",
                "artifact_sha256": "d" * 64,
            },
        )


class PreviewTests(unittest.TestCase):
    def test_preview_png_dimensions_pixels_and_crc_structure(self) -> None:
        image = RasterImage(2, 1, "RGB", bytes((255, 0, 0, 0, 0, 255)))
        result = quantize_image(
            image,
            options=PipelineOptions(DitherMode.NONE, preserve_edges=False),
        )
        png = result.preview_png()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        position = 8
        chunks = []
        while position < len(png):
            length = struct.unpack(">I", png[position : position + 4])[0]
            kind = png[position + 4 : position + 8]
            payload = png[position + 8 : position + 8 + length]
            expected_crc = struct.unpack(
                ">I", png[position + 8 + length : position + 12 + length]
            )[0]
            actual_crc = binascii.crc32(kind)
            actual_crc = binascii.crc32(payload, actual_crc) & 0xFFFFFFFF
            self.assertEqual(actual_crc, expected_crc)
            chunks.append((kind, payload))
            position += 12 + length
        self.assertEqual([kind for kind, _ in chunks], [b"IHDR", b"IDAT", b"IEND"])
        self.assertEqual(struct.unpack(">II", chunks[0][1][:8]), (2, 1))
        scanline = zlib.decompress(chunks[1][1])
        self.assertEqual(scanline, b"\x00" + bytes((255, 0, 0, 0, 0, 255)))


class ValidationTests(unittest.TestCase):
    def test_raster_shape_mode_and_output_width_are_validated(self) -> None:
        with self.assertRaisesRegex(ColorPipelineError, "RGB or RGBA"):
            RasterImage(2, 1, "BGR", bytes(6))
        with self.assertRaisesRegex(ColorPipelineError, "expected 6"):
            RasterImage(2, 1, "RGB", bytes(5))
        with self.assertRaisesRegex(ColorPipelineError, "contiguous"):
            RasterImage(2, 1, "RGB", memoryview(bytearray(12))[::2])
        with self.assertRaisesRegex(ColorPipelineError, "even"):
            quantize_image(RasterImage(1, 1, "RGB", bytes(3)))
        with self.assertRaisesRegex(ColorPipelineError, "1024x600"):
            quantize_panel_image(RasterImage(2, 1, "RGB", bytes(6)))

    def test_options_reject_unknown_modes_and_nonfinite_thresholds(self) -> None:
        with self.assertRaisesRegex(ColorPipelineError, "unknown dither"):
            PipelineOptions("not-a-mode")
        with self.assertRaisesRegex(ColorPipelineError, "finite"):
            PipelineOptions(edge_threshold=math.nan)
        with self.assertRaisesRegex(ColorPipelineError, "0xffffffff"):
            PipelineOptions(seed=-1)
        with self.assertRaisesRegex(ColorPipelineError, "not boolean"):
            PipelineOptions(edge_threshold=True)
        with self.assertRaisesRegex(ColorPipelineError, "must be boolean"):
            quantize_image(
                RasterImage(2, 1, "RGB", bytes(6)),
                allow_uncalibrated_palette=1,  # type: ignore[arg-type]
            )

    def test_palette_and_options_require_exact_public_types(self) -> None:
        image = RasterImage(2, 1, "RGB", bytes(6))
        with self.assertRaisesRegex(ColorPipelineError, "palette must be a Palette"):
            quantize_image(image, palette=False)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ColorPipelineError, "options must be a PipelineOptions"):
            quantize_image(image, options=False)  # type: ignore[arg-type]

    def test_noncanonical_dimensions_cannot_alias_panel_frame_byte_count(self) -> None:
        pixels = bytes(WIDTH * HEIGHT * 3)
        for width, height in ((2048, 300), (512, 1200)):
            image = RasterImage(width, height, "RGB", pixels)
            with self.subTest(dimensions=(width, height)):
                with self.assertRaisesRegex(
                    ColorPipelineError,
                    f"{FRAME_BYTES}-byte output is reserved for canonical",
                ):
                    quantize_image(image, allow_uncalibrated_palette=True)


if __name__ == "__main__":
    unittest.main()
