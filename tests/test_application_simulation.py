from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import unittest

from host.application.simulation import (
    SIMULATION_REPORT_HASH_SCOPE,
    SimulationAlgorithm,
    SimulationBudget,
    SimulationError,
    SimulationOptions,
    simulate_panel,
    simulate_raster,
    validate_simulation_report,
)
from host.application import InputSource, prepare_simulation_artifact
from host.color_pipeline import RasterImage, reference_palette
from host.epd_frame import HEIGHT, PHYSICAL_COLOR_CODES, WIDTH, unpack_pixels
from host.gamut_mapping import MappingOptions, build_synthetic_reference_profile


def _resign(report: dict[str, object]) -> None:
    unsigned = copy.deepcopy(report)
    del unsigned["report_integrity"]
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "canonical_sha256_scope": SIMULATION_REPORT_HASH_SCOPE,
    }


def _resign_nested(report: dict[str, object]) -> None:
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


class ApplicationSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.palette = reference_palette()
        cls.profile = build_synthetic_reference_profile(cls.palette)
        pixels = bytes(
            channel
            for y_value in range(8)
            for x_value in range(8)
            for channel in (
                (x_value * 31 + y_value * 7) & 0xFF,
                (x_value * 11 + y_value * 29) & 0xFF,
                (x_value * 19 + y_value * 13) & 0xFF,
            )
        )
        cls.image = RasterImage(8, 8, "RGB", pixels)

    def options(self, algorithm: SimulationAlgorithm | str) -> SimulationOptions:
        selected = SimulationAlgorithm(algorithm)
        budget = (
            SimulationBudget(16, 4, 8)
            if selected in {
                SimulationAlgorithm.MULTICOLOR_DBS,
                SimulationAlgorithm.OVERLAP_AWARE_DBS,
            }
            else None
        )
        return SimulationOptions(
            algorithm=selected,
            mapping=MappingOptions(),
            seed=123,
            budget=budget,
        )

    def test_all_ten_algorithms_produce_bound_six_code_soft_proofs(self) -> None:
        for algorithm in SimulationAlgorithm:
            with self.subTest(algorithm=algorithm.value):
                result = simulate_raster(
                    self.image,
                    palette=self.palette,
                    profile=self.profile,
                    options=self.options(algorithm),
                )
                self.assertLessEqual(set(result.codes), set(PHYSICAL_COLOR_CODES))
                self.assertEqual(unpack_pixels(result.frame, 8, 8), result.codes)
                self.assertEqual(set(result.previews), {"source", "mapped", "final", "model"})
                self.assertFalse(result.report["qualification"]["formal_upload_authorized"])
                self.assertIs(result.report["hardware_tested"], False)
                self.assertIs(result.report["device_io_performed"], False)
                result.validated_snapshot()

    def test_area_weighted_blue_noise_uses_six_weight_contract(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE),
        )
        halftone = result.report["halftone"]
        self.assertEqual(halftone["area_weights"]["physical_code_order"], [0, 1, 2, 3, 5, 6])
        self.assertFalse(halftone["report"]["area_weights"]["nearest_two_delta_e_ratio_used"])

    def test_area_weighted_ordered_is_a_distinct_six_weight_contract(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.AREA_WEIGHTED_ORDERED),
        )
        halftone = result.report["halftone"]
        self.assertEqual(
            halftone["report"]["assignment"]["threshold_algorithm"],
            "phase-seeded-bayer-8x8-rank-map-v1",
        )
        self.assertFalse(
            halftone["report"]["area_weights"]["nearest_two_delta_e_ratio_used"]
        )

    def test_all_algorithms_honour_text_protection_constraints(self) -> None:
        text_image = RasterImage(4, 2, "RGB", bytes((32, 100, 220, 220, 30, 50) * 4))
        for algorithm in SimulationAlgorithm:
            with self.subTest(algorithm=algorithm.value):
                base = self.options(algorithm)
                result = simulate_raster(
                    text_image,
                    palette=self.palette,
                    profile=self.profile,
                    options=replace(base, text_mode=True),
                )
                self.assertLessEqual(set(result.codes), {0, 1})
                self.assertEqual(
                    result.report["protections"]["locked_pixels"], 8
                )

    def test_area_weighted_pure_white_accepts_canonical_srgb_tolerance(self) -> None:
        white = RasterImage(2, 1, "RGB", bytes((255, 255, 255)) * 2)
        for algorithm in (
            SimulationAlgorithm.AREA_WEIGHTED_ORDERED,
            SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
        ):
            result = simulate_raster(
                white,
                palette=self.palette,
                profile=self.profile,
                options=self.options(algorithm),
            )
            self.assertEqual(result.codes, bytes((1, 1)))

    def test_dbs_budget_is_deterministic_and_never_time_limited(self) -> None:
        options = self.options(SimulationAlgorithm.OVERLAP_AWARE_DBS)
        first = simulate_raster(
            self.image, palette=self.palette, profile=self.profile, options=options
        )
        second = simulate_raster(
            self.image, palette=self.palette, profile=self.profile, options=options
        )
        self.assertEqual(first.frame, second.frame)
        self.assertEqual(first.report, second.report)
        self.assertFalse(first.report["halftone"]["budget"]["wall_clock_deadline_used"])
        self.assertIsNone(
            first.report["halftone"]["report"]["budget"]["time_limit_seconds"]
        )

    def test_dbs_v2_coverage_and_legacy_v1_reports_are_both_valid(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.OVERLAP_AWARE_DBS),
        )
        dbs_report = result.report["halftone"]["report"]
        self.assertEqual(dbs_report["schema_version"], 2)
        self.assertIn("coverage", dbs_report["search"])
        result.validated_snapshot()

        legacy = copy.deepcopy(result.report)
        legacy_dbs = legacy["halftone"]["report"]
        legacy_dbs["schema_version"] = 1
        del legacy_dbs["search"]["coverage"]
        _resign_nested(legacy_dbs)
        _resign(legacy)
        validate_simulation_report(
            legacy,
            frame=result.frame,
            previews=result.previews,
        )

    def test_resigned_dbs_v2_coverage_tampering_is_rejected(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.MULTICOLOR_DBS),
        )
        tampered = copy.deepcopy(result.report)
        dbs_report = tampered["halftone"]["report"]
        coverage = dbs_report["search"]["coverage"]
        coverage["unique_primary_pixels"] = coverage["unlocked_pixels"] + 1
        _resign_nested(dbs_report)
        _resign(tampered)
        with self.assertRaisesRegex(SimulationError, "unique proposal coverage"):
            validate_simulation_report(
                tampered,
                frame=result.frame,
                previews=result.previews,
            )

    def test_report_and_preview_tampering_are_rejected(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.ATKINSON),
        )
        tampered = copy.deepcopy(result.report)
        tampered["halftone"]["report"]["options"]["seed"] ^= 1
        _resign(tampered)
        with self.assertRaisesRegex(SimulationError, "halftone report integrity"):
            validate_simulation_report(tampered, frame=result.frame, previews=result.previews)

        previews = result.previews
        previews["final"] += b"tamper"
        with self.assertRaisesRegex(SimulationError, "preview final"):
            validate_simulation_report(result.report, frame=result.frame, previews=previews)

    def test_resigned_cross_layer_inconsistencies_are_rejected(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.ATKINSON),
        )
        mismatched = copy.deepcopy(result.report)
        mismatched["halftone"]["report"]["frame_sha256"] = "0" * 64
        _resign_nested(mismatched["halftone"]["report"])
        _resign(mismatched)
        with self.assertRaisesRegex(SimulationError, "C2 halftone output"):
            validate_simulation_report(
                mismatched, frame=result.frame, previews=result.previews
            )

        usage = copy.deepcopy(result.report)
        usage["output"]["usage"][0]["count"] += 1
        _resign(usage)
        with self.assertRaisesRegex(SimulationError, "usage"):
            validate_simulation_report(usage, frame=result.frame, previews=result.previews)

    def test_result_snapshot_binds_dimensions_and_palette(self) -> None:
        result = simulate_raster(
            self.image,
            palette=self.palette,
            profile=self.profile,
            options=self.options(SimulationAlgorithm.NONE),
        )
        with self.assertRaisesRegex(SimulationError, "dimensions differ"):
            replace(result, width=4, height=16).validated_snapshot()

    def test_budget_and_panel_entry_fail_closed(self) -> None:
        with self.assertRaises(SimulationError):
            SimulationBudget(0, 1, 1)
        with self.assertRaisesRegex(SimulationError, "require.*Budget"):
            SimulationOptions(
                algorithm=SimulationAlgorithm.MULTICOLOR_DBS,
                mapping=MappingOptions(),
            )
        with self.assertRaisesRegex(SimulationError, "1024x600"):
            simulate_panel(
                self.image,
                palette=self.palette,
                profile=self.profile,
                options=self.options(SimulationAlgorithm.ATKINSON),
            )

    def test_real_panel_simulation_wraps_as_offline_v2_artifact(self) -> None:
        panel = RasterImage(
            WIDTH,
            HEIGHT,
            "RGB",
            bytes((255, 255, 255)) * (WIDTH * HEIGHT),
        )
        simulation = simulate_panel(
            panel,
            palette=self.palette,
            options=SimulationOptions(
                algorithm=SimulationAlgorithm.NONE,
                mapping=MappingOptions(mode="none"),
                text_mode=True,
                preserve_edges=False,
            ),
        )
        source_bytes = b"synthetic-panel-wrapper-source"
        artifact = prepare_simulation_artifact(
            simulation,
            InputSource.from_bytes("unit-panel", "image/png", source_bytes),
            decode_provenance={
                "declared_media_type": "image/png",
                "formal_colour_eligible": False,
                "hardware_tested": False,
            },
        )
        self.assertEqual(artifact.report["version"], 2)
        self.assertFalse(artifact.upload_authorized)
        self.assertFalse(artifact.report["hardware_tested"])
        self.assertEqual(artifact.source_preview_png, simulation.source_png)
        self.assertEqual(artifact.mapped_preview_png, simulation.mapped_png)
        self.assertEqual(artifact.preview_png, simulation.final_png)
        self.assertEqual(artifact.model_preview_png, simulation.model_png)


if __name__ == "__main__":
    unittest.main()
