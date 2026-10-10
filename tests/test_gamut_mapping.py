from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from host.color_pipeline import (
    DitherMode,
    PipelineOptions,
    RasterImage,
    palette_from_mapping,
    quantize_image,
    reference_palette,
    srgb8_to_lab,
)
from host.gamut_mapping import (
    AREA_WEIGHT_REPORT_KIND,
    GAMUT_PROFILE_SCHEMA_VERSION,
    MAPPED_RASTER_ENCODING,
    SOFT_PROOF_WARNING,
    THREE_STAGE_PREVIEW_KIND,
    AreaWeightError,
    AreaWeightOptions,
    AreaWeightSolver,
    GamutMapper,
    GamutMappingError,
    GamutProfileError,
    MappingMode,
    MappingOptions,
    RenderingIntent,
    build_synthetic_reference_profile,
    build_three_stage_preview,
    gamut_profile_from_mapping,
    load_gamut_profile,
    map_lightness,
    map_raster,
    seal_profile_mapping,
    solve_area_weights,
    validate_mapping_report,
    validate_mapping_result,
)
from host.epd_frame import PHYSICAL_COLOR_CODES


class GamutProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = reference_palette()
        self.profile = build_synthetic_reference_profile(self.palette)

    def _payload(self) -> dict:
        return copy.deepcopy(self.profile.canonical_payload_mapping())

    def _parse(self, payload: dict):
        return gamut_profile_from_mapping(seal_profile_mapping(payload), self.palette)

    def test_synthetic_profile_is_versioned_bound_and_fail_closed(self) -> None:
        self.assertEqual(GAMUT_PROFILE_SCHEMA_VERSION, 1)
        self.assertEqual(self.profile.palette_id, self.palette.palette_id)
        self.assertEqual(
            self.profile.palette_canonical_sha256, self.palette.canonical_sha256
        )
        self.assertEqual(self.profile.characterization_level, "reference")
        self.assertTrue(self.profile.approximation)
        self.assertTrue(self.profile.is_simulation)
        self.assertFalse(self.profile.provenance_complete_for_formal_use)
        self.assertFalse(self.profile.hardware_formal_qualified)
        self.assertEqual(
            hashlib.sha256(self.profile.canonical_bytes()).hexdigest(),
            self.profile.canonical_sha256,
        )

    def test_dataclass_replacement_cannot_bypass_profile_identity(self) -> None:
        with self.assertRaisesRegex(GamutProfileError, "canonical_sha256"):
            replace(self.profile, profile_id="synthetic-tampered-profile")

    def test_profile_has_three_versioned_intents_and_aliases(self) -> None:
        self.assertEqual(self.profile.preset("faithful").intent, "relative-colorimetric")
        self.assertEqual(self.profile.preset("photographic").intent, "perceptual")
        self.assertEqual(self.profile.preset("vivid").intent, "saturation")
        for intent in ("relative-colorimetric", "perceptual", "saturation"):
            self.assertRegex(self.profile.preset(intent).version, r"^\d+\.\d+\.\d+$")

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        payload = self._payload()
        payload["unknown"] = True
        with self.assertRaisesRegex(GamutProfileError, "keys differ"):
            self._parse(payload)
        payload = self._payload()
        del payload["measurement"]["backing"]
        with self.assertRaisesRegex(GamutProfileError, "keys differ"):
            self._parse(payload)

    def test_hash_mismatch_is_rejected(self) -> None:
        document = self.profile.canonical_mapping()
        document["trust"]["source_statement"] += " tampered"
        with self.assertRaisesRegex(GamutProfileError, "canonical_sha256"):
            gamut_profile_from_mapping(document, self.palette)

    def test_nan_infinity_boolean_and_invalid_type_are_rejected(self) -> None:
        payload = self._payload()
        payload["rendering_presets"]["perceptual"]["tone_gamma"] = math.nan
        with self.assertRaises(GamutProfileError):
            seal_profile_mapping(payload)
        payload = self._payload()
        payload["rendering_presets"]["perceptual"]["tone_gamma"] = math.inf
        with self.assertRaises(GamutProfileError):
            seal_profile_mapping(payload)
        payload = self._payload()
        payload["rendering_presets"]["perceptual"]["tone_gamma"] = True
        with self.assertRaisesRegex(GamutProfileError, "not boolean"):
            self._parse(payload)

    def test_palette_hash_mismatch_is_rejected(self) -> None:
        alternate = self.palette.canonical_mapping()
        alternate["notes"] += " distinct identity"
        alternate_palette = palette_from_mapping(alternate)
        with self.assertRaisesRegex(GamutProfileError, "does not match"):
            gamut_profile_from_mapping(
                self.profile.canonical_mapping(), alternate_palette
            )

    def test_duplicate_sample_id_is_rejected(self) -> None:
        payload = self._payload()
        payload["model"]["pure_sample_refs"][1]["sample_id"] = payload["model"][
            "pure_sample_refs"
        ][0]["sample_id"]
        with self.assertRaisesRegex(GamutProfileError, "sample IDs"):
            self._parse(payload)

    def test_reference_profile_cannot_smuggle_measurement(self) -> None:
        payload = self._payload()
        payload["measurement"]["measurement_id"] = "fabricated"
        with self.assertRaisesRegex(GamutProfileError, "explicitly null"):
            self._parse(payload)

    def test_mixture_fraction_semantics_are_strict(self) -> None:
        payload = self._payload()
        payload["model"]["characterization_level"] = "measured_mixtures"
        payload["model"]["kind"] = "measured_point_cloud_v1"
        payload["model"]["mixture_samples"] = [
            {
                "sample_id": "mix-1",
                "mask_id": "checker-2x2",
                "area_fractions": [
                    {"code": 2, "fraction": 0.25},
                    {"code": 6, "fraction": 0.25},
                ],
                "xyz": [0.4, 0.5, 0.2],
                "artifact_sha256": "1" * 64,
            }
        ]
        with self.assertRaisesRegex(GamutProfileError, "sum to one"):
            self._parse(payload)

    def test_load_rejects_non_json_constants(self) -> None:
        document = self.profile.canonical_mapping()
        text = json.dumps(document).replace('"tone_gamma": 0.92', '"tone_gamma": NaN')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(GamutProfileError, "not permitted"):
                load_gamut_profile(path, self.palette)

    def test_json_schema_is_strict_and_versioned(self) -> None:
        schema_path = (
            Path(__file__).parents[1]
            / "host"
            / "gamut_mapping"
            / "gamut_profile.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("canonical_sha256", schema["required"])

    def test_bundled_synthetic_fixture_matches_builder(self) -> None:
        fixture = (
            Path(__file__).parents[1]
            / "host"
            / "gamut_mapping"
            / "profiles"
            / "synthetic_reference_linear_xyz_v1.json"
        )
        loaded = load_gamut_profile(fixture, self.palette)
        self.assertEqual(loaded.canonical_mapping(), self.profile.canonical_mapping())


class GamutMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = reference_palette()
        self.profile = build_synthetic_reference_profile(self.palette)
        self.mapper = GamutMapper(self.palette, self.profile)

    def test_tone_curve_is_monotonic_and_has_endpoints(self) -> None:
        for intent in ("relative-colorimetric", "perceptual", "saturation"):
            preset = self.profile.preset(intent)
            values = [
                map_lightness(
                    lightness,
                    10.0,
                    90.0,
                    tone_gamma=preset.tone_gamma,
                    strength=1.0,
                )
                for lightness in range(101)
            ]
            self.assertAlmostEqual(values[0], 10.0)
            self.assertAlmostEqual(values[-1], 90.0)
            self.assertTrue(all(left <= right for left, right in zip(values, values[1:])))

    def test_relative_colorimetric_preserves_reference_primaries(self) -> None:
        for entry in self.palette.entries:
            mapped = self.mapper.map_lab(entry.lab, intent="faithful")
            for expected, actual in zip(entry.lab, mapped.mapped_lab):
                self.assertAlmostEqual(expected, actual, places=6)
            self.assertTrue(mapped.in_gamut_after_tone)

    def test_neutral_axis_remains_neutral(self) -> None:
        for lightness in (0.0, 20.0, 50.0, 80.0, 100.0):
            mapped = self.mapper.map_lab(
                (lightness, 0.0, 0.0), intent="photographic"
            )
            self.assertAlmostEqual(mapped.mapped_lab[1], 0.0, places=7)
            self.assertAlmostEqual(mapped.mapped_lab[2], 0.0, places=7)

    def test_out_of_gamut_is_bounded_for_all_intents(self) -> None:
        source = (60.0, 90.0, -80.0)
        for intent in ("relative-colorimetric", "perceptual", "saturation"):
            mapped = self.mapper.map_lab(source, intent=intent)
            self.assertFalse(mapped.in_gamut_after_tone)
            self.assertTrue(self.mapper.contains_xyz(mapped.mapped_xyz, tolerance=2e-9))
            self.assertLessEqual(mapped.applied_scale, mapped.boundary_scale + 1e-12)

    def test_extreme_synthetic_grid_always_maps_inside_declared_3d_model(self) -> None:
        for lightness in (0.0, 25.0, 50.0, 75.0, 100.0):
            for a_value in (-150.0, 0.0, 150.0):
                for b_value in (-150.0, 0.0, 150.0):
                    for intent in RenderingIntent:
                        mapped = self.mapper.map_lab(
                            (lightness, a_value, b_value), intent=intent
                        )
                        self.assertTrue(
                            self.mapper.contains_xyz(mapped.mapped_xyz, tolerance=2e-9)
                        )

    def test_intents_have_distinct_versioned_behavior(self) -> None:
        source = srgb8_to_lab((210, 80, 110))
        faithful = self.mapper.map_lab(source, intent="faithful")
        photographic = self.mapper.map_lab(source, intent="photographic")
        vivid = self.mapper.map_lab(source, intent="vivid")
        rounded = {
            tuple(round(value, 6) for value in item.mapped_lab)
            for item in (faithful, photographic, vivid)
        }
        self.assertGreaterEqual(len(rounded), 2)

    def test_unqualified_mapping_fails_closed_without_opt_in(self) -> None:
        image = RasterImage(2, 1, "RGB", bytes((255, 0, 255, 20, 30, 40)))
        with self.assertRaisesRegex(GamutMappingError, "simulation"):
            map_raster(image, palette=self.palette, profile=self.profile)

    def test_legacy_none_is_byte_for_byte_and_mode_preserving(self) -> None:
        pixels = bytes((10, 20, 30, 0, 40, 50, 60, 255))
        image = RasterImage(2, 1, "RGBA", pixels)
        for mode in ("none", "legacy", MappingMode.NONE):
            result = map_raster(image, options=MappingOptions(mode=mode))
            self.assertEqual(result.mapped_image.mode, "RGBA")
            self.assertEqual(result.mapped_image.pixels, pixels)
            self.assertEqual(result.mapped_linear_u16be, b"")
            report = result.report.to_dict()
            self.assertFalse(report["qualification"]["formal_upload_authorized"])

    def test_legacy_path_keeps_existing_c2_output_byte_for_byte(self) -> None:
        pixels = bytes((
            1, 2, 3, 255, 255, 255, 240, 30, 80, 20, 200, 30,
            1, 2, 3, 255, 255, 255, 240, 30, 80, 20, 200, 30,
        ))
        image = RasterImage(4, 2, "RGB", pixels)
        options = PipelineOptions(dither=DitherMode.FLOYD_STEINBERG)
        baseline = quantize_image(image, palette=self.palette, options=options)
        legacy = map_raster(image, options=MappingOptions(mode="legacy"))
        repeated = quantize_image(
            legacy.mapped_image, palette=self.palette, options=options
        )
        self.assertEqual(repeated.frame, baseline.frame)
        self.assertEqual(repeated.codes, baseline.codes)
        self.assertEqual(repeated.preview_rgb(), baseline.preview_rgb())
        self.assertEqual(repeated.report.to_dict(), baseline.report.to_dict())

    def test_mapped_raster_and_identity_are_deterministic(self) -> None:
        pixels = bytes((255, 0, 255, 128, 128, 128, 255, 0, 255, 1, 2, 3))
        image = RasterImage(4, 1, "RGB", pixels)
        options = MappingOptions(intent="photographic", cache_entries=2)
        first = map_raster(
            image,
            palette=self.palette,
            profile=self.profile,
            options=options,
            allow_unqualified_simulation=True,
        )
        second = map_raster(
            image,
            palette=self.palette,
            profile=self.profile,
            options=options,
            allow_unqualified_simulation=True,
        )
        self.assertEqual(first.mapped_image, second.mapped_image)
        self.assertEqual(first.mapped_linear_u16be, second.mapped_linear_u16be)
        self.assertEqual(first.report.to_dict(), second.report.to_dict())
        self.assertEqual(len(first.mapped_linear_u16be), 4 * 6)
        self.assertEqual(
            first.mapped_raster_identity["encoding"], MAPPED_RASTER_ENCODING
        )

    def test_report_is_strict_simulation_and_tamper_detecting(self) -> None:
        image = RasterImage(2, 1, "RGB", bytes((255, 0, 255, 1, 2, 3)))
        result = map_raster(
            image,
            palette=self.palette,
            profile=self.profile,
            allow_unqualified_simulation=True,
        )
        report = result.report.to_dict()
        self.assertTrue(report["qualification"]["simulation"])
        self.assertFalse(report["qualification"]["artifact_hardware_qualified"])
        self.assertFalse(report["qualification"]["formal_upload_authorized"])
        self.assertFalse(report["hardware_tested"])
        self.assertIn(SOFT_PROOF_WARNING, report["warnings"])
        validate_mapping_report(report)
        report["statistics"]["pixels"] += 1
        with self.assertRaisesRegex(GamutMappingError, "integrity"):
            validate_mapping_report(report)

    def test_result_revalidation_detects_low_level_byte_tampering(self) -> None:
        image = RasterImage(2, 1, "RGB", bytes((255, 0, 255, 1, 2, 3)))
        result = map_raster(
            image,
            palette=self.palette,
            profile=self.profile,
            allow_unqualified_simulation=True,
        )
        validate_mapping_result(result)
        report_copy = result.report.payload
        report_copy["statistics"]["pixels"] = 999
        self.assertNotEqual(result.report.payload["statistics"]["pixels"], 999)
        object.__setattr__(result, "mapped_linear_u16be", b"\0" * 12)
        with self.assertRaisesRegex(GamutMappingError, "derive from mapped Q16"):
            validate_mapping_result(result)

    def test_options_reject_nonfinite_and_invalid_cache(self) -> None:
        with self.assertRaises(GamutMappingError):
            MappingOptions(strength=math.nan)
        with self.assertRaises(GamutMappingError):
            MappingOptions(strength=True)
        with self.assertRaises(GamutMappingError):
            MappingOptions(cache_entries=-1)


class AreaWeightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = reference_palette()
        self.profile = build_synthetic_reference_profile(self.palette)

    def test_solver_requires_explicit_simulation_opt_in(self) -> None:
        with self.assertRaisesRegex(AreaWeightError, "simulation"):
            AreaWeightSolver(self.palette, self.profile)

    def test_primary_target_has_exact_single_colour_recipe(self) -> None:
        target = self.palette.entry(3).lab
        solution = solve_area_weights(
            target,
            palette=self.palette,
            profile=self.profile,
            allow_unqualified_simulation=True,
        )
        red_index = tuple(sorted(PHYSICAL_COLOR_CODES)).index(3)
        self.assertEqual(solution.counts[red_index], 4)
        self.assertEqual(sum(solution.counts), 4)
        self.assertAlmostEqual(sum(solution.weights), 1.0)
        self.assertAlmostEqual(solution.delta_e00, 0.0, places=9)

    def test_canonical_srgb_white_tolerance_is_normalized(self) -> None:
        solution = solve_area_weights(
            srgb8_to_lab((255, 255, 255)),
            palette=self.palette,
            profile=self.profile,
            allow_unqualified_simulation=True,
        )
        white_index = tuple(sorted(PHYSICAL_COLOR_CODES)).index(1)
        self.assertEqual(solution.counts[white_index], 4)
        self.assertEqual(solution.target_lab[0], 100.0)

    def test_weights_are_nonnegative_normalized_and_deterministic(self) -> None:
        solver = AreaWeightSolver(
            self.palette,
            self.profile,
            options=AreaWeightOptions(intent="vivid", tile_side=2),
            allow_unqualified_simulation=True,
        )
        first = solver.solve((62.0, 12.0, 42.0))
        second = solver.solve((62.0, 12.0, 42.0))
        self.assertIs(first, second)
        self.assertTrue(all(weight >= 0.0 for weight in first.weights))
        self.assertAlmostEqual(sum(first.weights), 1.0)
        self.assertEqual(sum(first.counts), 4)
        self.assertTrue(all(code in PHYSICAL_COLOR_CODES for code in first.tile))

    def test_objective_reports_distinct_colour_and_texture_terms(self) -> None:
        solution = solve_area_weights(
            (55.0, 20.0, 30.0),
            palette=self.palette,
            profile=self.profile,
            options=AreaWeightOptions(intent="photographic"),
            allow_unqualified_simulation=True,
        )
        report = solution.to_report()
        self.assertEqual(report["kind"], AREA_WEIGHT_REPORT_KIND)
        for field in (
            "delta_e00",
            "lightness_error",
            "chroma_error",
            "hue_error_degrees",
            "grain_penalty",
            "color_count_penalty",
        ):
            self.assertIn(field, report["objective"])
        self.assertTrue(report["qualification"]["simulation"])
        self.assertFalse(report["qualification"]["hardware_formal_qualified"])
        self.assertFalse(report["hardware_tested"])

    def test_recipe_spaces_are_fixed_and_bounded(self) -> None:
        two = AreaWeightSolver(
            self.palette,
            self.profile,
            options=AreaWeightOptions(tile_side=2),
            allow_unqualified_simulation=True,
        )
        four = AreaWeightSolver(
            self.palette,
            self.profile,
            options=AreaWeightOptions(tile_side=4),
            allow_unqualified_simulation=True,
        )
        self.assertEqual(two.recipe_space_size, 126)
        self.assertEqual(four.recipe_space_size, 20349)


class ThreeStagePreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = reference_palette()
        self.profile = build_synthetic_reference_profile(self.palette)
        self.source = RasterImage(
            4,
            2,
            "RGB",
            bytes(
                (
                    255,
                    0,
                    255,
                    255,
                    255,
                    255,
                    0,
                    0,
                    0,
                    0,
                    255,
                    0,
                )
                * 2
            ),
        )

    def _mapped(self):
        return map_raster(
            self.source,
            palette=self.palette,
            profile=self.profile,
            allow_unqualified_simulation=True,
        )

    def test_three_stage_preview_binds_actual_mapped_and_code_stream(self) -> None:
        mapped = self._mapped()
        quantized = quantize_image(
            mapped.mapped_image,
            palette=self.palette,
            options=PipelineOptions(dither=DitherMode.ATKINSON),
        )
        proof = build_three_stage_preview(mapped, quantized)
        report = proof.report
        self.assertEqual(report["kind"], THREE_STAGE_PREVIEW_KIND)
        self.assertEqual([stage["order"] for stage in report["stages"]], [1, 2, 3])
        self.assertEqual(
            report["stages"][2]["codes_sha256"],
            hashlib.sha256(quantized.codes).hexdigest(),
        )
        self.assertEqual(proof.final_rgb, quantized.preview_rgb())
        self.assertTrue(report["simulation"])
        self.assertFalse(report["hardware_tested"])

    def test_mismatched_quantization_is_rejected(self) -> None:
        mapped = self._mapped()
        other = RasterImage(4, 2, "RGB", bytes((0, 0, 0) * 8))
        quantized = quantize_image(other, palette=self.palette)
        with self.assertRaisesRegex(GamutMappingError, "not bound"):
            build_three_stage_preview(mapped, quantized)


if __name__ == "__main__":
    unittest.main()
