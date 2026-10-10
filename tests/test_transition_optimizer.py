from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from host.color_pipeline import (
    CalibrationProvenance,
    DitherMode,
    Palette,
    PipelineOptions,
    RasterImage,
    quantize_image,
    reference_palette,
)
from host.extended_color import build_empty_transition_profile
from host.transition_optimizer import (
    MissingProfileMode,
    TransitionInputBinding,
    TransitionOptimizationError,
    TransitionOptimizationOptions,
    UnknownCurrentMode,
    build_pareto_report,
    optimize_transition_aware,
    validate_pareto_report,
    validate_transition_optimization_report,
)
from tools.mf1750_transition_optimize import (
    TransitionArtifactError,
    build_offline_artifacts,
    parse_args,
    validate_offline_artifact_directory,
    write_offline_artifacts,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _palette() -> Palette:
    source = reference_palette()
    return Palette(
        palette_id="test-measured-six-colour-v1",
        entries=source.entries,
        calibrated=True,
        source="synthetic unit-test measurement; not a panel claim",
        illuminant="D65",
        observer="2deg",
        notes="test only",
        calibration=CalibrationProvenance("test-palette-measurement", _sha("palette")),
    )


def _measured_profile(palette: Palette) -> dict:
    profile = build_empty_transition_profile()
    profile.update(
        {
            "hardware_tested": True,
            "generated_at": "2026-08-08T00:00:00Z",
            "panel_serial": "UNIT-TEST-PANEL",
            "firmware_git_commit": "a" * 40,
            "firmware_binary_sha256": "b" * 64,
            "waveform_id": "fixed-global-unit-test-waveform",
            "waveform_sha256": "c" * 64,
            "environment": {
                "temperature_c": 25.0,
                "relative_humidity_percent": 45.0,
                "record_ref": "unit-test-environment",
            },
            "illuminant": "D65",
            "observer": "2deg",
            "geometry": "45/0",
        }
    )
    by_code = palette.by_code
    for index, cell in enumerate(profile["cells"]):
        old = cell["old_code"]
        new = cell["new_code"]
        changed = old != new
        cell.update(
            {
                "sample_count": 1,
                "initial_lab_mean": {
                    "l": by_code[old].lab[0],
                    "a": by_code[old].lab[1],
                    "b": by_code[old].lab[2],
                },
                "final_lab_mean": {
                    "l": by_code[new].lab[0],
                    "a": by_code[new].lab[1],
                    "b": by_code[new].lab[2],
                },
                "delta_e00_mean": 20.0 if changed else 0.0,
                "delta_e00_sd": 0.2,
                "cs1_minus_cs2_delta_e00": 0.0,
                "position_effect_delta_e00": 0.1,
                "ghosting_metric_mean": 1.0 if changed else 0.0,
                "busy_ms_mean": 35_010.0 if changed else 35_000.0,
                "peak_current_a_mean": 0.9 if changed else 0.1,
                "energy_j_mean": 1.5 if changed else 0.1,
                "temperature_rise_c_mean": 1.0 if changed else 0.0,
                "recovery_pass_rate": 0.95 if changed else 1.0,
                "source_run_sha256s": [_sha(f"run-{index}")],
                "asset_manifest_sha256s": [_sha(f"asset-{index}")],
                "authorization_ids": [f"unit-test-authorization-{index}"],
            }
        )
    return profile


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _binding(palette: Palette, profile: dict) -> TransitionInputBinding:
    assert palette.calibration is not None
    return TransitionInputBinding(
        binding_id="unit-test-cross-asset-review-v1",
        palette_canonical_sha256=palette.canonical_sha256,
        palette_calibration_artifact_sha256=palette.calibration.artifact_sha256,
        transition_profile_canonical_sha256=_canonical_sha(profile),
        panel_serial=profile["panel_serial"],
        firmware_binary_sha256=profile["firmware_binary_sha256"],
        waveform_sha256=profile["waveform_sha256"],
        review_artifact_sha256=_sha("cross-asset-review"),
    )


def _image(width: int = 8, height: int = 4) -> RasterImage:
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend(
                (
                    (x * 31 + y * 7) & 0xFF,
                    (255 - x * 19 + y * 3) & 0xFF,
                    (x * 11 + y * 53) & 0xFF,
                )
            )
    return RasterImage(width, height, "RGB", bytes(pixels))


def _pipeline_options() -> PipelineOptions:
    return PipelineOptions(
        dither=DitherMode.FLOYD_STEINBERG,
        serpentine=True,
        white_protection=False,
        preserve_edges=False,
    )


class TransitionOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.palette = _palette()
        cls.profile = _measured_profile(cls.palette)
        cls.binding = _binding(cls.palette, cls.profile)
        cls.image = _image()
        cls.current = bytes([0] * (cls.image.width * cls.image.height))

    def test_zero_transition_weights_exactly_degenerate_to_c2_quantizer(self) -> None:
        pipeline = _pipeline_options()
        ordinary = quantize_image(self.image, palette=self.palette, options=pipeline)
        result = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=self.current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=0,
                gamma=0,
                delta=0,
                pipeline_options=pipeline,
            ),
        )
        self.assertEqual(result.codes, ordinary.codes)
        self.assertEqual(result.frame, ordinary.frame)
        self.assertTrue(
            result.report["classification"]["ordinary_quantizer_exact_degeneration"]
        )
        self.assertEqual(
            result.report["execution_path"], "exact-ordinary-quantizer-degeneration"
        )

    def test_missing_profile_rejects_by_default_or_falls_back_explicitly(self) -> None:
        options = TransitionOptimizationOptions(
            alpha=1,
            beta=1,
            pipeline_options=_pipeline_options(),
        )
        with self.assertRaisesRegex(TransitionOptimizationError, "profile is required"):
            optimize_transition_aware(
                self.image,
                palette=self.palette,
                transition_profile=None,
                current_codes=self.current,
                options=options,
            )
        fallback = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=None,
            current_codes=self.current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=1,
                pipeline_options=_pipeline_options(),
                missing_profile_mode=MissingProfileMode.PERCEPTUAL_ONLY,
            ),
        )
        ordinary = quantize_image(
            self.image, palette=self.palette, options=_pipeline_options()
        )
        self.assertEqual(fallback.frame, ordinary.frame)
        self.assertTrue(fallback.report["classification"]["perceptual_only_fallback"])
        self.assertFalse(fallback.report["classification"]["formal_input_eligible"])

    def test_incomplete_profile_never_invents_transition_costs(self) -> None:
        empty = build_empty_transition_profile()
        with self.assertRaisesRegex(TransitionOptimizationError, "incomplete"):
            optimize_transition_aware(
                self.image,
                palette=self.palette,
                transition_profile=empty,
                current_codes=self.current,
                options=TransitionOptimizationOptions(
                    alpha=1,
                    beta=1,
                    pipeline_options=_pipeline_options(),
                ),
            )
        fallback = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=empty,
            current_codes=self.current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=1,
                pipeline_options=_pipeline_options(),
                missing_profile_mode=MissingProfileMode.PERCEPTUAL_ONLY,
            ),
        )
        self.assertIsNone(
            fallback.report["objectives"]["normalized_transition_cost_mean"]
        )

    def test_high_measured_change_cost_can_prefer_the_known_old_code(self) -> None:
        white = RasterImage(8, 2, "RGB", bytes([255, 255, 255] * 16))
        current = bytes([0] * 16)
        perceptual = optimize_transition_aware(
            white,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=0,
                gamma=0,
                delta=0,
                pipeline_options=_pipeline_options(),
            ),
        )
        conservative = optimize_transition_aware(
            white,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=200,
                gamma=200,
                delta=0,
                pipeline_options=_pipeline_options(),
            ),
        )
        self.assertGreater(perceptual.codes.count(1), 0)
        self.assertEqual(conservative.codes, current)
        self.assertEqual(conservative.report["objectives"]["changed_pixels"], 0)

    def test_unknown_current_state_has_explicit_conservative_semantics(self) -> None:
        options = TransitionOptimizationOptions(
            alpha=1,
            beta=2,
            gamma=1,
            pipeline_options=_pipeline_options(),
            unknown_current_mode=UnknownCurrentMode.CONSERVATIVE_WORST_CASE,
        )
        first = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=None,
            options=options,
        )
        second = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=None,
            options=options,
        )
        self.assertEqual(first.frame, second.frame)
        self.assertIsNone(first.report["output"]["transition_histogram"])
        self.assertIsNone(first.report["objectives"]["changed_pixels"])
        self.assertFalse(first.report["classification"]["formal_input_eligible"])

    def test_known_state_emits_exact_six_by_six_histogram(self) -> None:
        result = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=self.current,
            measurement_binding=self.binding,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=1,
                gamma=1,
                delta=0.2,
                pipeline_options=_pipeline_options(),
            ),
        )
        histogram = result.report["output"]["transition_histogram"]
        self.assertEqual(len(histogram), 6)
        self.assertTrue(all(len(row) == 6 for row in histogram))
        self.assertEqual(sum(map(sum, histogram)), self.image.width * self.image.height)
        self.assertEqual(
            result.report["output"]["transition_histogram_sum"],
            self.image.width * self.image.height,
        )
        self.assertTrue(result.report["classification"]["formal_input_eligible"])
        self.assertFalse(
            result.report["classification"]["busy_time_reduction_claim_allowed"]
        )

    def test_cross_asset_binding_is_required_and_mismatch_fails(self) -> None:
        without_binding = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=self.current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=1,
                pipeline_options=_pipeline_options(),
            ),
        )
        self.assertFalse(
            without_binding.report["classification"]["formal_input_eligible"]
        )
        invalid = TransitionInputBinding(
            **{
                **self.binding.to_dict(),
                "panel_serial": "ANOTHER-PANEL",
            }
        )
        with self.assertRaisesRegex(TransitionOptimizationError, "does not match"):
            optimize_transition_aware(
                self.image,
                palette=self.palette,
                transition_profile=self.profile,
                current_codes=self.current,
                measurement_binding=invalid,
                options=TransitionOptimizationOptions(
                    alpha=1,
                    beta=1,
                    pipeline_options=_pipeline_options(),
                ),
            )

    def test_integrity_and_safety_reject_tampering(self) -> None:
        result = optimize_transition_aware(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=self.current,
            options=TransitionOptimizationOptions(
                alpha=1,
                beta=1,
                pipeline_options=_pipeline_options(),
            ),
        )
        validate_transition_optimization_report(result.report)
        tampered = deepcopy(result.report)
        tampered["classification"]["busy_time_reduction_claim_allowed"] = True
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        payload = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        tampered["integrity"]["canonical_sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaisesRegex(TransitionOptimizationError, "classification"):
            validate_transition_optimization_report(tampered)

    def test_pareto_report_preserves_all_points_and_selects_no_single_best(self) -> None:
        option_grid = [
            TransitionOptimizationOptions(
                alpha=1,
                beta=0,
                gamma=0,
                delta=0,
                pipeline_options=_pipeline_options(),
            ),
            TransitionOptimizationOptions(
                alpha=1,
                beta=2,
                gamma=1,
                delta=0.1,
                pipeline_options=_pipeline_options(),
            ),
            TransitionOptimizationOptions(
                alpha=1,
                beta=20,
                gamma=20,
                delta=0.5,
                pipeline_options=_pipeline_options(),
            ),
        ]
        report = build_pareto_report(
            self.image,
            palette=self.palette,
            transition_profile=self.profile,
            current_codes=self.current,
            measurement_binding=self.binding,
            option_grid=option_grid,
        )
        validate_pareto_report(report)
        self.assertEqual(len(report["points"]), 3)
        self.assertGreaterEqual(len(report["nondominated_indices"]), 1)
        self.assertIsNone(report["selection"])
        self.assertFalse(report["classification"]["single_best_claimed"])
        with self.assertRaisesRegex(TransitionOptimizationError, "duplicate"):
            build_pareto_report(
                self.image,
                palette=self.palette,
                transition_profile=self.profile,
                current_codes=self.current,
                option_grid=[option_grid[0], option_grid[0]],
            )

    def test_offline_tool_writes_and_deep_validates_a_closed_artifact(self) -> None:
        options = TransitionOptimizationOptions(
            alpha=1,
            beta=1,
            gamma=0.5,
            pipeline_options=_pipeline_options(),
        )
        artifacts = build_offline_artifacts(
            self.image,
            source_record={
                "source_file_sha256": _sha("source"),
                "declared_media_type": "image/png",
                "decode_provenance": {"test_only": True},
            },
            palette=self.palette,
            palette_file_sha256=_sha("palette-file"),
            transition_profile=self.profile,
            transition_profile_file_sha256=_sha("profile-file"),
            current_codes=self.current,
            current_frame_file_sha256=_sha("current-frame"),
            measurement_binding=self.binding,
            measurement_binding_file_sha256=_sha("binding-file"),
            options=options,
            option_grid=[
                options,
                TransitionOptimizationOptions(
                    alpha=1,
                    beta=4,
                    gamma=2,
                    pipeline_options=_pipeline_options(),
                ),
            ],
        )
        self.assertFalse(artifacts.manifest["classification"]["device_io_performed"])
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=repo_root) as temporary:
            root = Path(temporary)
            destination = write_offline_artifacts(root / "artifact", artifacts)
            validated = validate_offline_artifact_directory(destination)
            self.assertEqual(validated, artifacts.manifest)
            frame_path = destination / "frame.bin"
            tampered = bytearray(frame_path.read_bytes())
            tampered[0] ^= 0x01
            frame_path.write_bytes(tampered)
            with self.assertRaisesRegex(TransitionArtifactError, "identity changed"):
                validate_offline_artifact_directory(destination)

    def test_offline_cli_has_no_device_destination_or_authorization_option(self) -> None:
        parsed = parse_args(["validate", "artifact"])
        self.assertEqual(parsed.command, "validate")
        help_text = Path(
            Path(__file__).resolve().parents[1] / "tools/mf1750_transition_optimize.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("--url", help_text)
        self.assertNotIn("--upload", help_text)
        self.assertNotIn("authorization_confirmation", help_text)


if __name__ == "__main__":
    unittest.main()
