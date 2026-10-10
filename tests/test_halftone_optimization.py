from __future__ import annotations

import hashlib
import json
import struct
import unittest

from host.color_pipeline.palette import reference_palette
from host.color_pipeline.pipeline import RasterImage
from host.epd_frame import PHYSICAL_COLOR_CODES
from host.halftone_optimization import (
    ALLOWED_CODES,
    AREA_WEIGHTED_BLUE_NOISE_ALGORITHM,
    AREA_WEIGHTED_ORDERED_ALGORITHM,
    BLUE_NOISE_ALGORITHM,
    DBS_REPORT_SCHEMA_VERSION,
    DBSOptions,
    BlueNoiseError,
    BlueNoiseOptions,
    HalftoneModelError,
    HalftoneOptimizationError,
    OverlapObservationModel,
    SpatialKernel,
    box_blur_rgb,
    box_source_response,
    evaluate_halftone_loss,
    evaluate_structure_penalties,
    generate_blue_noise_thresholds,
    optimize_multicolor_dbs,
    quantize_area_weighted_blue_noise,
    quantize_area_weighted_ordered,
    quantize_blue_noise,
    validate_six_codes,
)
from host.halftone_optimization.optimizer import _ProposalCoverage


def _gradient(width: int = 8, height: int = 6) -> RasterImage:
    pixels = bytes(
        channel
        for y_value in range(height)
        for x_value in range(width)
        for channel in (
            x_value * 255 // max(1, width - 1),
            y_value * 255 // max(1, height - 1),
            (x_value * 29 + y_value * 47) & 0xFF,
        )
    )
    return RasterImage(width, height, "RGB", pixels)


def _brute_box(values, width: int, height: int, size: int):
    radius = size // 2
    result = []
    for y_value in range(height):
        for x_value in range(width):
            for channel in range(3):
                total = 0.0
                for dy in range(-radius, radius + 1):
                    sampled_y = min(height - 1, max(0, y_value + dy))
                    for dx in range(-radius, radius + 1):
                        sampled_x = min(width - 1, max(0, x_value + dx))
                        total += values[(sampled_y * width + sampled_x) * 3 + channel]
                result.append(total / (size * size))
    return result


class ModelTests(unittest.TestCase):
    def test_physical_code_validation_is_fail_closed(self) -> None:
        self.assertEqual(ALLOWED_CODES, (0, 1, 2, 3, 5, 6))
        self.assertEqual(validate_six_codes(bytes(ALLOWED_CODES), 6), bytes(ALLOWED_CODES))
        with self.assertRaisesRegex(HalftoneModelError, "non-physical"):
            validate_six_codes(bytes((0, 1, 4, 3, 5, 6)), 6)
        with self.assertRaisesRegex(HalftoneModelError, "expected 6"):
            validate_six_codes(bytes((0, 1)), 6)

    def test_spatial_kernel_normalizes_and_model_is_simulation_only(self) -> None:
        kernel = SpatialKernel.from_rows(((0, 1, 0), (1, 4, 1), (0, 1, 0)))
        self.assertAlmostEqual(sum(kernel.weights), 1.0)
        model = OverlapObservationModel.gaussian_simulation(size=3, sigma_x=0.7)
        metadata = model.metadata()
        self.assertEqual(metadata["calibration_state"], "simulation")
        self.assertFalse(metadata["hardware_qualified"])
        self.assertFalse(metadata["hardware_tested"])
        with self.assertRaisesRegex(HalftoneModelError, "simulation-only"):
            OverlapObservationModel(
                "invalid",
                tuple((code, kernel) for code in ALLOWED_CODES),
                hardware_qualified=True,
            )

    def test_uniform_mask_remains_uniform_at_edges(self) -> None:
        palette = reference_palette()
        model = OverlapObservationModel.gaussian_simulation()
        colour = palette.entry(3).diffusion_rgb
        rendered = model.render_linear_rgb(bytes((3,)) * 20, 5, 4, palette=palette)
        for pixel in range(20):
            for channel in range(3):
                self.assertAlmostEqual(rendered[pixel * 3 + channel], colour[channel], places=6)

    def test_box_blur_matches_brute_force_even_when_kernel_exceeds_image(self) -> None:
        width, height = 3, 2
        values = [float(index) / 17.0 for index in range(width * height * 3)]
        for size in (3, 7, 15):
            actual = box_blur_rgb(values, width, height, size)
            expected = _brute_box(values, width, height, size)
            for one, two in zip(actual, expected):
                self.assertAlmostEqual(one, two, places=6)

    def test_local_source_response_exactly_matches_full_rerender(self) -> None:
        width, height = 5, 4
        palette = reference_palette()
        model = OverlapObservationModel.gaussian_simulation()
        initial = bytes((1,)) * (width * height)
        changed = bytearray(initial)
        changed[0] = 3
        before = model.render_linear_rgb(initial, width, height, palette=palette)
        after = model.render_linear_rgb(changed, width, height, palette=palette)
        response_old = model.source_response(1, 0, 0, width, height)
        response_new = model.source_response(3, 0, 0, width, height)
        white = palette.entry(1).diffusion_rgb
        red = palette.entry(3).diffusion_rgb
        predicted_delta = [0.0] * len(before)
        for pixel, weight in response_old.items():
            for channel in range(3):
                predicted_delta[pixel * 3 + channel] -= weight * white[channel]
        for pixel, weight in response_new.items():
            for channel in range(3):
                predicted_delta[pixel * 3 + channel] += weight * red[channel]
        for index in range(len(before)):
            self.assertAlmostEqual(after[index] - before[index], predicted_delta[index], places=6)

    def test_box_source_response_matches_impulse_blur(self) -> None:
        width, height = 4, 3
        impulse = [0.0] * (width * height * 3)
        source_x, source_y = 0, 2
        impulse[(source_y * width + source_x) * 3] = 1.0
        for size in (3, 7, 15):
            blurred = box_blur_rgb(impulse, width, height, size)
            response = box_source_response(source_x, source_y, width, height, size)
            for pixel in range(width * height):
                self.assertAlmostEqual(
                    blurred[pixel * 3], response.get(pixel, 0.0), places=6
                )


class BlueNoiseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = BlueNoiseOptions(
            tile_width=8,
            tile_height=8,
            seed=12345,
            sigma=1.25,
            max_relaxation_moves=256,
        )

    def test_void_and_cluster_map_is_complete_deterministic_and_seeded(self) -> None:
        first = generate_blue_noise_thresholds(self.options)
        second = generate_blue_noise_thresholds(self.options)
        different = generate_blue_noise_thresholds(
            BlueNoiseOptions(
                tile_width=8,
                tile_height=8,
                seed=54321,
                sigma=1.25,
                max_relaxation_moves=256,
            )
        )
        self.assertEqual(first.ranks, second.ranks)
        self.assertNotEqual(first.ranks, different.ranks)
        self.assertEqual(set(first.ranks), set(range(64)))
        self.assertGreater(first.mean_nearest_distance, 1.5)
        self.assertIn(first.relaxation_stop_reason, {"stable_void_cluster", "relaxation_budget"})
        report = first.to_report()
        self.assertEqual(report["algorithm"], BLUE_NOISE_ALGORITHM)
        self.assertFalse(report["qualification"]["hardware_qualified"])
        unsigned = dict(report)
        integrity = unsigned.pop("report_integrity")
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(integrity["canonical_sha256"], hashlib.sha256(canonical).hexdigest())

    def test_thresholds_are_strict_uniform_ranks_not_coordinate_hashes(self) -> None:
        threshold_map = generate_blue_noise_thresholds(self.options)
        expected = tuple((rank + 0.5) / 64 for rank in range(64))
        self.assertEqual(tuple(sorted(threshold_map.thresholds)), expected)
        self.assertGreater(threshold_map.relaxation_moves, 0)
        self.assertGreaterEqual(threshold_map.low_frequency_energy, 0.0)

    def test_legacy_nearest_two_path_is_explicitly_labelled(self) -> None:
        result = quantize_blue_noise(_gradient(), options=self.options)
        self.assertFalse(set(result.codes).difference(PHYSICAL_COLOR_CODES))
        weights = result.report["mixing_weights"]
        self.assertTrue(weights["nearest_two_delta_e_ratio_used"])
        self.assertFalse(weights["g1_six_colour_area_weight_contract"])
        self.assertFalse(weights["recommended_for_new_area_weighted_pipeline"])
        self.assertEqual(len(result.threshold_maps), 1)
        self.assertTrue(result.preview_png().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_area_weighted_path_uses_all_six_weight_channels(self) -> None:
        width, height = 6, 2
        weights = []
        for _y in range(height):
            for x_value in range(width):
                weights.extend(1.0 if channel == x_value else 0.0 for channel in range(6))
        result = quantize_area_weighted_blue_noise(
            width,
            height,
            weights,
            options=self.options,
            solver_id="unit-test-six-weight-solver",
        )
        self.assertEqual(result.codes, bytes(ALLOWED_CODES) * height)
        self.assertEqual(len(result.threshold_maps), 6)
        self.assertEqual(len({item.seed for item in result.threshold_maps}), 6)
        self.assertEqual(result.report["algorithm"], AREA_WEIGHTED_BLUE_NOISE_ALGORITHM)
        self.assertFalse(
            result.report["area_weights"]["nearest_two_delta_e_ratio_used"]
        )
        self.assertTrue(result.report["assignment"]["decorrelated_channels"])
        self.assertFalse(result.report["qualification"]["hardware_qualified"])

    def test_area_weights_fail_closed_on_shape_range_and_sum(self) -> None:
        with self.assertRaisesRegex(BlueNoiseError, "expected 12"):
            quantize_area_weighted_blue_noise(2, 1, [1.0] * 6, options=self.options)
        invalid_range = [0.0] * 12
        invalid_range[0] = 1.1
        invalid_range[1] = -0.1
        invalid_range[6] = 1.0
        with self.assertRaisesRegex(BlueNoiseError, "in \[0, 1\]"):
            quantize_area_weighted_blue_noise(2, 1, invalid_range, options=self.options)
        invalid_sum = [0.0] * 12
        invalid_sum[0] = 0.5
        invalid_sum[1] = 0.4
        invalid_sum[6] = 1.0
        with self.assertRaisesRegex(BlueNoiseError, "sum to"):
            quantize_area_weighted_blue_noise(2, 1, invalid_sum, options=self.options)

    def test_area_weighted_assignment_is_byte_deterministic(self) -> None:
        width, height = 8, 4
        weights = [1.0 / 6.0] * (width * height * 6)
        first = quantize_area_weighted_blue_noise(
            width, height, weights, options=self.options, solver_id="balanced"
        )
        second = quantize_area_weighted_blue_noise(
            width, height, weights, options=self.options, solver_id="balanced"
        )
        self.assertEqual(first.codes, second.codes)
        self.assertEqual(first.report, second.report)
        self.assertGreaterEqual(len(set(first.codes)), 4)

    def test_area_weighted_ordered_uses_all_six_weights_and_bayer_ranks(self) -> None:
        width = height = 8
        weights = [1.0 / 6.0] * (width * height * 6)
        first = quantize_area_weighted_ordered(
            width, height, weights, seed=7, solver_id="balanced-six"
        )
        repeated = quantize_area_weighted_ordered(
            width, height, weights, seed=7, solver_id="balanced-six"
        )
        phased = quantize_area_weighted_ordered(
            width, height, weights, seed=8, solver_id="balanced-six"
        )
        self.assertEqual(first.codes, repeated.codes)
        self.assertEqual(first.report, repeated.report)
        self.assertNotEqual(first.codes, phased.codes)
        self.assertEqual(set(first.codes), set(ALLOWED_CODES))
        self.assertLessEqual(max(first.codes.count(code) for code in ALLOWED_CODES), 11)
        self.assertGreaterEqual(min(first.codes.count(code) for code in ALLOWED_CODES), 10)
        self.assertEqual(first.report["algorithm"], AREA_WEIGHTED_ORDERED_ALGORITHM)
        self.assertEqual(first.report["assignment"]["period_width"], 8)
        self.assertFalse(
            first.report["area_weights"]["nearest_two_delta_e_ratio_used"]
        )

    def test_area_weighted_ordered_honours_physical_code_constraints(self) -> None:
        weights = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0] * 4
        constraints = bytes((3, 255, 6, 255))
        result = quantize_area_weighted_ordered(
            4,
            1,
            weights,
            code_constraints=constraints,
            solver_id="constraint-test",
        )
        self.assertEqual(result.codes, bytes((3, 0, 6, 0)))
        self.assertEqual(result.report["code_constraints"]["locked_pixels"], 2)


class DBSTests(unittest.TestCase):
    def test_direction_and_periodic_penalties_detect_stripes(self) -> None:
        width = height = 18
        stripes = bytes(
            0 if (y_value & 1) == 0 else 1
            for y_value in range(height)
            for _x in range(width)
        )
        modular = bytes(
            ALLOWED_CODES[(x_value + 2 * y_value) % 6]
            for y_value in range(height)
            for x_value in range(width)
        )
        stripe_loss = evaluate_structure_penalties(stripes, width, height)
        modular_loss = evaluate_structure_penalties(modular, width, height)
        self.assertGreater(stripe_loss["direction"], modular_loss["direction"])
        self.assertGreater(stripe_loss["periodic"], modular_loss["periodic"])

    def test_single_pixel_recolour_is_controlled_and_improves_loss(self) -> None:
        palette = reference_palette()
        image = RasterImage(1, 1, "RGB", bytes(palette.entry(3).preview_rgb))
        options = DBSOptions(
            seed=1,
            max_evaluations=5,
            max_accepted_moves=1,
            stagnation_evaluations=5,
            swap_probability=0.0,
        )
        result = optimize_multicolor_dbs(image, bytes((5,)), options=options)
        self.assertEqual(result.codes, bytes((3,)))
        self.assertEqual(result.report["search"]["accepted_recolours"], 1)
        self.assertEqual(result.report["search"]["accepted_swaps"], 0)
        self.assertGreater(result.report["loss"]["improvement"], 0.0)

    def test_pair_swap_changes_topology_without_changing_colour_counts(self) -> None:
        palette = reference_palette()
        pixels = bytes(palette.entry(3).preview_rgb + palette.entry(6).preview_rgb)
        image = RasterImage(2, 1, "RGB", pixels)
        options = DBSOptions(
            seed=1,
            max_evaluations=1,
            max_accepted_moves=1,
            stagnation_evaluations=1,
            swap_probability=1.0,
            swap_radius=1,
        )
        result = optimize_multicolor_dbs(image, bytes((6, 3)), options=options)
        self.assertEqual(result.codes, bytes((3, 6)))
        self.assertEqual(result.report["search"]["accepted_swaps"], 1)
        self.assertEqual(sorted(result.codes), [3, 6])

    def test_multiscale_local_updates_match_full_loss_recomputation(self) -> None:
        image = _gradient()
        blue = quantize_blue_noise(
            image,
            options=BlueNoiseOptions(
                tile_width=8,
                tile_height=8,
                seed=777,
                max_relaxation_moves=128,
            ),
        )
        options = DBSOptions(
            seed=99,
            max_evaluations=80,
            max_accepted_moves=20,
            stagnation_evaluations=80,
            swap_probability=0.5,
        )
        result = optimize_multicolor_dbs(image, blue.codes, options=options)
        recomputed = evaluate_halftone_loss(image, result.codes, options=options)
        self.assertAlmostEqual(
            result.report["loss"]["final"]["total"], recomputed.total, places=8
        )
        self.assertLessEqual(
            result.report["loss"]["final"]["total"],
            result.report["loss"]["initial"]["total"],
        )
        self.assertFalse(set(result.codes).difference(PHYSICAL_COLOR_CODES))
        self.assertEqual(result.report["loss_contract"]["scales"], [3, 7, 15])
        self.assertIn("direction", result.report["loss"]["final"])
        self.assertIn("periodic", result.report["loss"]["final"])

    def test_seeded_search_and_report_are_deterministic(self) -> None:
        image = _gradient(6, 4)
        initial = bytes((0, 1, 2, 3, 5, 6)) * 4
        options = DBSOptions(
            seed=20260806,
            max_evaluations=30,
            max_accepted_moves=10,
            stagnation_evaluations=30,
            swap_probability=0.4,
        )
        first = optimize_multicolor_dbs(image, initial, options=options)
        second = optimize_multicolor_dbs(image, initial, options=options)
        self.assertEqual(first.codes, second.codes)
        self.assertEqual(first.report, second.report)

    def test_proposal_coverage_is_model_independent_and_bounded(self) -> None:
        image = _gradient(6, 4)
        initial = bytes((0, 1, 2, 3, 5, 6)) * 4
        options = DBSOptions(
            seed=20260807,
            max_evaluations=30,
            max_accepted_moves=30,
            stagnation_evaluations=30,
            swap_probability=0.45,
        )
        identity_kernel = SpatialKernel(1, 1, (1.0,))
        identity = OverlapObservationModel(
            "test-identity-v1",
            tuple((code, identity_kernel) for code in ALLOWED_CODES),
        )
        identity_result = optimize_multicolor_dbs(
            image, initial, model=identity, options=options
        )
        overlap_result = optimize_multicolor_dbs(
            image,
            initial,
            model=OverlapObservationModel.gaussian_simulation(),
            options=options,
        )
        self.assertEqual(identity_result.report["schema_version"], DBS_REPORT_SCHEMA_VERSION)
        self.assertEqual(DBS_REPORT_SCHEMA_VERSION, 2)
        identity_search = identity_result.report["search"]
        overlap_search = overlap_result.report["search"]
        self.assertEqual(identity_search["evaluations"], overlap_search["evaluations"])
        self.assertEqual(identity_search["proposals"], overlap_search["proposals"])
        self.assertEqual(identity_search["coverage"], overlap_search["coverage"])

        coverage = identity_search["coverage"]
        proposals = identity_search["proposals"]
        self.assertEqual(coverage["unlocked_pixels"], image.width * image.height)
        self.assertLessEqual(coverage["unique_primary_pixels"], proposals)
        self.assertGreaterEqual(
            coverage["unique_touched_pixels"], coverage["unique_primary_pixels"]
        )
        self.assertLessEqual(
            coverage["unique_touched_pixels"], coverage["unlocked_pixels"]
        )
        self.assertEqual(
            coverage["primary_coverage_ratio"],
            coverage["unique_primary_pixels"] / coverage["unlocked_pixels"],
        )
        self.assertEqual(
            coverage["horizontal_split"]["left_proposals"]
            + coverage["horizontal_split"]["right_proposals"],
            proposals,
        )
        grid = coverage["tile_grid"]
        self.assertEqual((grid["columns"], grid["rows"]), (6, 4))
        self.assertFalse(grid["panel_1024x600_exact_64x60"])
        self.assertEqual(len(grid["proposal_counts"]), 24)
        self.assertEqual(sum(grid["proposal_counts"]), proposals)
        self.assertRegex(coverage["proposal_trace_sha256"], r"^[0-9a-f]{64}$")

    def test_proposal_schedule_is_a_budget_prefix(self) -> None:
        image = _gradient(6, 4)
        initial = bytes((0, 1, 2, 3, 5, 6)) * 4
        short = optimize_multicolor_dbs(
            image,
            initial,
            options=DBSOptions(
                seed=991,
                max_evaluations=10,
                max_accepted_moves=10,
                stagnation_evaluations=10,
                swap_probability=0.0,
            ),
        )
        long = optimize_multicolor_dbs(
            image,
            initial,
            options=DBSOptions(
                seed=991,
                max_evaluations=30,
                max_accepted_moves=30,
                stagnation_evaluations=30,
                swap_probability=0.0,
            ),
        )
        short_coverage = short.report["search"]["coverage"]
        long_coverage = long.report["search"]["coverage"]
        short_samples = short_coverage["proposal_trace_samples"]
        self.assertEqual(len(short_samples), short.report["search"]["proposals"])
        self.assertEqual(
            short_samples,
            long_coverage["proposal_trace_samples"][: len(short_samples)],
        )
        digest = hashlib.sha256()
        sentinel = 0xFFFFFFFFFFFFFFFF
        for sample in short_samples:
            pixels = sample["pixels"]
            digest.update(
                struct.pack(
                    ">QBQQ",
                    sample["proposal"],
                    int(sample["operation"] == "pair-swap"),
                    pixels[0],
                    pixels[1] if len(pixels) == 2 else sentinel,
                )
            )
        self.assertEqual(digest.hexdigest(), short_coverage["proposal_trace_sha256"])

    def test_proposal_coverage_handles_an_all_protected_raster(self) -> None:
        image = _gradient(2, 2)
        initial = bytes((0, 1, 2, 3))
        result = optimize_multicolor_dbs(
            image,
            initial,
            options=DBSOptions(
                max_evaluations=4,
                max_accepted_moves=4,
                stagnation_evaluations=4,
            ),
            code_constraints=initial,
        )
        coverage = result.report["search"]["coverage"]
        self.assertEqual(result.report["budget"]["stop_reason"], "all_pixels_protected")
        self.assertEqual(result.report["search"]["proposals"], 0)
        self.assertEqual(coverage["unlocked_pixels"], 0)
        self.assertEqual(coverage["unique_primary_pixels"], 0)
        self.assertEqual(coverage["unique_touched_pixels"], 0)
        self.assertEqual(coverage["primary_coverage_ratio"], 0.0)
        self.assertEqual(
            coverage["proposal_trace_sha256"], hashlib.sha256(b"").hexdigest()
        )
        self.assertFalse(any(coverage["tile_grid"]["proposal_counts"]))

    def test_panel_proposal_grid_is_exactly_sixteen_by_ten_64px_tiles(self) -> None:
        tracker = _ProposalCoverage(1024, 600, 1024 * 600)
        tracker.record(1, "single-recolour", 0, None)
        tracker.record(2, "pair-swap", 60 * 1024 + 64, 60 * 1024 + 65)
        tracker.record(3, "single-recolour", 599 * 1024 + 1023, None)
        coverage = tracker.to_mapping(3)
        grid = coverage["tile_grid"]
        self.assertEqual((grid["columns"], grid["rows"]), (16, 10))
        self.assertTrue(grid["panel_1024x600_exact_64x60"])
        self.assertEqual((grid["exact_tile_width"], grid["exact_tile_height"]), (64, 60))
        self.assertEqual(len(grid["proposal_counts"]), 160)
        self.assertEqual(grid["proposal_counts"][0], 1)
        self.assertEqual(grid["proposal_counts"][17], 1)
        self.assertEqual(grid["proposal_counts"][159], 1)
        self.assertEqual(coverage["unique_primary_pixels"], 3)
        self.assertEqual(coverage["unique_touched_pixels"], 4)

    def test_evaluation_budget_is_a_hard_bound(self) -> None:
        image = _gradient(4, 3)
        options = DBSOptions(
            seed=2,
            max_evaluations=7,
            max_accepted_moves=7,
            stagnation_evaluations=7,
            swap_probability=0.0,
        )
        result = optimize_multicolor_dbs(image, bytes((1,)) * 12, options=options)
        self.assertLessEqual(result.report["search"]["evaluations"], 7)
        self.assertIn(
            result.report["budget"]["stop_reason"],
            {"evaluation_budget", "accepted_move_budget", "stagnation"},
        )

    def test_cooperative_cancellation_returns_traceable_unchanged_result(self) -> None:
        image = _gradient(4, 3)
        initial = bytes((1,)) * 12
        options = DBSOptions(
            seed=2,
            max_evaluations=20,
            max_accepted_moves=10,
            stagnation_evaluations=20,
        )
        result = optimize_multicolor_dbs(
            image, initial, options=options, cancel_check=lambda: True
        )
        self.assertEqual(result.codes, initial)
        self.assertEqual(result.report["budget"]["stop_reason"], "cancelled")
        self.assertEqual(result.report["search"]["evaluations"], 0)
        self.assertTrue(result.report["determinism"]["cancelled"])

    def test_reports_never_claim_hardware_qualification_or_device_access(self) -> None:
        image = _gradient(2, 2)
        options = DBSOptions(
            max_evaluations=1,
            max_accepted_moves=1,
            stagnation_evaluations=1,
        )
        result = optimize_multicolor_dbs(image, bytes((1,)) * 4, options=options)
        qualification = result.report["qualification"]
        self.assertTrue(qualification["simulation_only"])
        self.assertFalse(qualification["hardware_tested"])
        self.assertFalse(qualification["hardware_qualified"])
        self.assertFalse(qualification["device_accessed"])
        self.assertTrue(result.preview_png().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_options_and_code_inputs_reject_invalid_values(self) -> None:
        with self.assertRaisesRegex(HalftoneOptimizationError, "sum to 1"):
            DBSOptions(multiscale_weights=(0.5, 0.5, 0.5))
        with self.assertRaisesRegex(HalftoneOptimizationError, "positive integer"):
            DBSOptions(max_evaluations=0)
        image = _gradient(2, 2)
        with self.assertRaisesRegex(HalftoneModelError, "non-physical"):
            optimize_multicolor_dbs(image, bytes((1, 1, 1, 4)))


if __name__ == "__main__":
    unittest.main()
