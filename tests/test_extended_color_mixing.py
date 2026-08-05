from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from host.color_pipeline import palette_from_mapping, reference_palette, srgb8_to_lab
from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    pixel_counts,
    validate_frame,
)
from host.extended_color import (
    COLOR_ORDER,
    AreaMixError,
    analyze_area_mixes,
    render_area_mix_tile,
    validate_area_mix_report,
)
from tools import mf1750_area_mix as tool


def calibrated_palette():
    reference = reference_palette()
    return palette_from_mapping(
        {
            "schema_version": 2,
            "palette_id": "measured-area-mix-test",
            "calibrated": True,
            "source": "deterministic unit-test measurement fixture",
            "illuminant": "D65",
            "observer": "2deg",
            "notes": "not hardware data",
            "calibration": {
                "measurement_id": "area-mix-unit-test",
                "artifact_sha256": "a" * 64,
            },
            "entries": [
                {
                    "code": entry.code,
                    "name": entry.name,
                    "lab": list(entry.lab),
                    "preview_rgb": list(entry.preview_rgb),
                }
                for entry in reference.entries
            ],
        }
    )


class AreaMixModelTests(unittest.TestCase):
    def test_uncalibrated_palette_requires_explicit_simulation_opt_in(self) -> None:
        palette = reference_palette()
        with self.assertRaisesRegex(AreaMixError, "calibrated"):
            analyze_area_mixes(palette, srgb8_to_lab((0, 255, 255)), tile_side=2)

        analysis = analyze_area_mixes(
            palette,
            srgb8_to_lab((0, 255, 255)),
            tile_side=2,
            limit=2,
            allow_uncalibrated_simulation=True,
            target_input_space="sRGB8",
            target_input_values=(0, 255, 255),
        )
        report = analysis.report()
        self.assertTrue(report["model"]["uncalibrated_simulation"])
        self.assertFalse(report["prediction_is_measurement"])
        self.assertFalse(report["hardware_tested"])
        self.assertFalse(report["device_io_performed"])
        self.assertFalse(report["network_io_performed"])
        self.assertFalse(report["waveform_changed"])
        self.assertTrue(report["formal_api_compatible"])
        self.assertEqual(report["model"]["model_version"], "xyz-area-v1")
        for field in (
            "measured_lab",
            "measured_delta_e00",
            "model_residual_delta_e00",
            "prediction_confidence",
            "transition_cost",
            "energy_j",
            "ghosting_metric",
        ):
            self.assertIsNone(report["candidates"][0][field])

    def test_pure_primary_target_has_exact_zero_distance_recipe(self) -> None:
        palette = calibrated_palette()
        target = palette.entry(0).lab
        analysis = analyze_area_mixes(palette, target, tile_side=2, limit=1)
        recipe = analysis.recipes[0]
        self.assertEqual(recipe.counts, (4, 0, 0, 0, 0, 0))
        self.assertAlmostEqual(recipe.delta_e00, 0.0, delta=1e-12)
        frame = recipe.frame()
        self.assertEqual(len(frame), FRAME_BYTES)
        validate_frame(frame)
        counts = pixel_counts(frame)
        self.assertEqual(counts[0], WIDTH * HEIGHT)
        self.assertEqual(sum(counts), WIDTH * HEIGHT)

    def test_four_by_four_search_is_complete_deterministic_and_formal(self) -> None:
        palette = calibrated_palette()
        target = srgb8_to_lab((35, 180, 190))
        first = analyze_area_mixes(palette, target, tile_side=4, limit=5)
        second = analyze_area_mixes(palette, target, tile_side=4, limit=5)
        self.assertEqual(first.recipe_space_size, 20349)
        self.assertEqual(first.recipes, second.recipes)
        for recipe in first.recipes:
            self.assertEqual(sum(recipe.counts), 16)
            self.assertTrue(set(recipe.tile) <= set(PHYSICAL_COLOR_CODES))
            validate_frame(recipe.frame())
        self.assertEqual(first.report(), second.report())

    def test_tile_layout_preserves_exact_counts_and_is_stable(self) -> None:
        counts = (2, 3, 4, 1, 3, 3)
        tile = render_area_mix_tile(4, counts)
        self.assertEqual(tile, render_area_mix_tile(4, counts))
        self.assertEqual(len(tile), 16)
        self.assertEqual(tuple(tile.count(code) for code in COLOR_ORDER), counts)
        self.assertTrue(set(tile) <= set(COLOR_ORDER))

    def test_bayer_layout_disperses_half_and_quarter_area_recipes(self) -> None:
        two_by_two = render_area_mix_tile(2, (2, 2, 0, 0, 0, 0))
        self.assertEqual(two_by_two, (0, 1, 1, 0))

        half = render_area_mix_tile(4, (8, 8, 0, 0, 0, 0))
        for y_value in range(4):
            for x_value in range(4):
                self.assertEqual(half[y_value * 4 + x_value], (x_value + y_value) % 2)

        quarters = render_area_mix_tile(4, (4, 4, 4, 4, 0, 0))
        for y_value in (0, 2):
            for x_value in (0, 2):
                block = {
                    quarters[(y_value + dy) * 4 + x_value + dx]
                    for dy in range(2)
                    for dx in range(2)
                }
                self.assertEqual(block, {0, 1, 2, 3})

    def test_invalid_model_inputs_fail_closed(self) -> None:
        palette = calibrated_palette()
        for target in (
            (-1, 0, 0),
            (101, 0, 0),
            (50, 201, 0),
            (50, 1e308, 0),
            (float("nan"), 0, 0),
            (True, 0, 0),
        ):
            with self.subTest(target=target):
                with self.assertRaises(AreaMixError):
                    analyze_area_mixes(palette, target, tile_side=2)  # type: ignore[arg-type]
        for side in (1, 3, 8, True):
            with self.subTest(side=side):
                with self.assertRaises(AreaMixError):
                    analyze_area_mixes(palette, (50, 0, 0), tile_side=side)  # type: ignore[arg-type]
        with self.assertRaises(AreaMixError):
            render_area_mix_tile(4, (16, 0, 0, 0, 0, 1))
        with self.assertRaisesRegex(AreaMixError, "do not reproduce"):
            analyze_area_mixes(
                palette,
                srgb8_to_lab((1, 2, 3)),
                tile_side=2,
                target_input_space="sRGB8",
                target_input_values=(3, 2, 1),
            )

    def test_report_schema_shape_is_self_contained_and_matches_generated_report(self) -> None:
        analysis = analyze_area_mixes(
            reference_palette(),
            srgb8_to_lab((20, 170, 180)),
            tile_side=2,
            limit=2,
            allow_uncalibrated_simulation=True,
            target_input_space="sRGB8",
            target_input_values=(20, 170, 180),
        )
        report = analysis.report()
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "extended_color"
            / "area_mix.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(set(report), set(schema["required"]))
        self.assertEqual(set(report), set(schema["properties"]))
        candidate_schema = schema["$defs"]["candidate"]
        self.assertEqual(set(report["candidates"][0]), set(candidate_schema["required"]))
        self.assertEqual(set(report["candidates"][0]), set(candidate_schema["properties"]))
        self.assertEqual(set(report["model"]), set(schema["properties"]["model"]["required"]))
        self.assertEqual(set(report["palette"]), set(schema["properties"]["palette"]["required"]))
        self.assertEqual(
            candidate_schema["properties"]["frame_identity"]["$ref"],
            "#/$defs/frame_identity",
        )
        refs = []

        def collect_refs(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    refs.append(value["$ref"])
                for child in value.values():
                    collect_refs(child)
            elif isinstance(value, list):
                for child in value:
                    collect_refs(child)

        collect_refs(schema)
        self.assertTrue(refs)
        self.assertTrue(all(reference.startswith("#/") for reference in refs))
        self.assertEqual(schema["$defs"]["sha256"]["type"], "string")

    def test_semantic_validator_rejects_inconsistent_or_rank_spoofed_reports(self) -> None:
        analysis = analyze_area_mixes(
            reference_palette(),
            srgb8_to_lab((20, 170, 180)),
            tile_side=2,
            limit=2,
            allow_uncalibrated_simulation=True,
            target_input_space="sRGB8",
            target_input_values=(20, 170, 180),
        )
        report = analysis.report()

        inconsistent_model = json.loads(json.dumps(report))
        inconsistent_model["model"]["tile_pixels"] = 16
        with self.assertRaisesRegex(AreaMixError, "tile_pixels"):
            validate_area_mix_report(inconsistent_model)

        duplicate = json.loads(json.dumps(report))
        duplicate["candidates"][1] = json.loads(json.dumps(duplicate["candidates"][0]))
        duplicate["candidates"][1]["rank"] = 2
        with self.assertRaisesRegex(AreaMixError, "unique"):
            validate_area_mix_report(duplicate)

        measured = json.loads(json.dumps(report))
        measured["candidates"][0]["measured_delta_e00"] = 0.0
        with self.assertRaisesRegex(AreaMixError, "must be null"):
            validate_area_mix_report(measured)

        bad_selection = json.loads(json.dumps(report))
        bad_selection["artifact_selection"]["frame_output_requested"] = True
        with self.assertRaisesRegex(AreaMixError, "artifact_selection"):
            validate_area_mix_report(bad_selection)


class AreaMixToolTests(unittest.TestCase):
    def test_palette_path_lexically_rejects_devices_and_network_paths(self) -> None:
        unsafe = [
            "COM8",
            "COM8.json",
            "COM8 .json",
            "NUL.txt",
            "NUL .txt",
            r"\\server\share\palette.json",
        ]
        for raw_path in unsafe:
            with self.subTest(raw_path=raw_path):
                with self.assertRaises(tool.OutputSafetyError):
                    tool.validate_palette_path(Path(raw_path))

    def test_cli_has_no_device_refresh_or_unknown_code_option(self) -> None:
        for forbidden in ("--url", "--serial", "--refresh", "--unknown-code", "--waveform"):
            with self.subTest(forbidden=forbidden):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        tool.parse_args(
                            [
                                "--target-srgb",
                                "0",
                                "200",
                                "200",
                                "--allow-uncalibrated-simulation",
                                forbidden,
                                "value",
                            ]
                        )
                self.assertEqual(raised.exception.code, 2)

    def test_cli_requires_calibration_unless_simulation_is_explicit(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = tool.main(["--target-srgb", "0", "200", "200", "--tile-side", "2"])
        self.assertEqual(result, 2)
        self.assertIn("calibrated", stderr.getvalue())

    def test_cli_extreme_finite_lab_fails_closed_without_traceback(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = tool.main(
                [
                    "--target-lab",
                    "50",
                    "1e308",
                    "0",
                    "--tile-side",
                    "2",
                    "--allow-uncalibrated-simulation",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("a* and b*", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_can_create_new_formal_frame_and_report_without_device_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            frame_path = root / "mix.frame"
            report_path = root / "mix.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = tool.main(
                    [
                        "--target-srgb",
                        "0",
                        "200",
                        "200",
                        "--tile-side",
                        "2",
                        "--limit",
                        "2",
                        "--allow-uncalibrated-simulation",
                        "--frame-output",
                        str(frame_path),
                        "--report-output",
                        str(report_path),
                    ]
                )
            self.assertEqual(result, 0)
            frame = frame_path.read_bytes()
            self.assertEqual(len(frame), FRAME_BYTES)
            validate_frame(frame)
            present = {
                index for index, count in enumerate(pixel_counts(frame)) if count
            }
            self.assertTrue(present <= set(COLOR_ORDER))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report, json.loads(stdout.getvalue()))
            self.assertEqual(report["color_codes"], list(COLOR_ORDER))
            self.assertFalse(report["hardware_tested"])
            self.assertFalse(report["device_io_performed"])
            self.assertFalse(report["network_io_performed"])
            selection = report["artifact_selection"]
            self.assertTrue(selection["frame_output_requested"])
            self.assertEqual(selection["rendered_candidate_rank"], 1)
            self.assertEqual(
                selection["selected_frame_identity"]["frame_sha256"],
                report["candidates"][0]["frame_identity"]["frame_sha256"],
            )
            validate_area_mix_report(report)

    def test_cli_frame_output_requires_persistent_report_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            frame_path = Path(directory_name) / "orphan.frame"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = tool.main(
                    [
                        "--target-srgb",
                        "0",
                        "200",
                        "200",
                        "--tile-side",
                        "2",
                        "--limit",
                        "1",
                        "--allow-uncalibrated-simulation",
                        "--frame-output",
                        str(frame_path),
                    ]
                )
            self.assertEqual(result, 2)
            self.assertFalse(frame_path.exists())
            self.assertIn("sidecar", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
