"""Adapt V3 camera analysis into a fail-closed lightness evidence workflow.

The V3 photo analyzer reports one record per physical cell.  This adapter
regroups those cells by physical controller and middle transport code, feeds
the resulting eight-position replicas into :mod:`lightness_screen`, and emits
an unqualified shortlist plus a HOLD -> independent factory-white baseline ->
fresh reconstruction -> final factory-white containment plan.

Nothing in this module accesses a camera, device, relay, serial port, network,
or filesystem.  A camera-relative REVIEW result is never converted into
qualified colour evidence.  CS1 and CS2 are never pooled, spatial dithering is
forbidden, and hue enumeration remains explicitly deferred.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Mapping

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    finite_triple,
    require_exact_keys,
    require_sha256,
    require_text,
)
from .controller_palette_inventory import (
    candidate_from_lightness_screen,
)
from .lightness_screen import (
    LightnessMeasurement,
    MeasurementPhase,
    screen_lightness_ladders,
)
from .multi_lut_hold_schedule import Controller


class V3LightnessWorkflowError(ValueError):
    """Raised when V3 analysis cannot be safely adapted."""


V3_CAMERA_ANALYSIS_KIND = (
    "mf1750-stable-code0-luma-latin-v3-camera-relative-photo-analysis"
)
V3_REPEAT_COMPARISON_KIND = (
    "mf1750-stable-code0-luma-latin-v3-l3-l4-camera-relative-repeat-comparison"
)
V3_CAMPAIGN_ID = "EC5_STABLE_CODE0_LUMA_LATIN_V3"
V3_TEST_ID = "EC5-STABLE-CODE0-LUMA-LATIN-V3"
V3_CONTRACT_ID = "472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302"
V3_TARGET_LUT_PROFILE_ID = "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
V3_SOURCE_CODE = 7
V3_TARGET_CODE = 0
PROJECT_CAMERA_USB_ID = "VID_32E4:PID_4801"
EXPECTED_REPLICAS_PER_RECIPE = 8

_LEGACY_REPEAT_COMPARABILITY_KEYS = {
    "analysis_method_equal",
    "analysis_thresholds_equal",
    "camera_exposure_equal",
    "camera_settings_except_exposure_equal",
    "controller_local_centered_lightness_comparison_used",
    "cross_controller_comparison_used",
    "l3_requested_exposure",
    "l4_requested_exposure",
    "raw_absolute_lab_repeat_comparable",
}
_SAME_EXPOSURE_REPEAT_COMPARABILITY_KEYS = _LEGACY_REPEAT_COMPARABILITY_KEYS | {
    "camera_settings_exactly_equal",
    "exact_by_field",
    "except_exposure_equal_by_field",
    "exposure_equal_by_field",
}
_SETTINGS_COMPARISON_FIELDS = {
    "requested_settings",
    "effective_settings_before_frame",
    "effective_settings_after_frame",
}
_REPEAT_QUALIFICATION_BOUNDARY_KEYS = {
    "absolute_colour_claimed",
    "cross_controller_equivalence_claimed",
    "persistence_proven",
    "qualified_colour_count",
    "qualified_gray_levels",
    "repeatable_signal_is_not_a_qualified_gray_level",
    "same_exposure_repeat_proven",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise V3LightnessWorkflowError(f"{label} must be an object")
    return value


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise V3LightnessWorkflowError(
            f"{label} must be an integer in {minimum}..{maximum}"
        )
    return value


def _finite_nonnegative(value: object, label: str) -> float:
    try:
        result = finite_triple((value, 0.0, 0.0), label)[0]
    except StaticPhotoContractError as error:
        raise V3LightnessWorkflowError(str(error)) from error
    if result < 0.0:
        raise V3LightnessWorkflowError(f"{label} must be non-negative")
    return result


def _finite_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise V3LightnessWorkflowError(f"{label} must be a finite number")
    return float(value)


def _capture_exposure_binding(sidecar: Mapping[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for field in sorted(_SETTINGS_COMPARISON_FIELDS):
        settings = _mapping(sidecar.get(field), f"analysis.sidecar.{field}")
        values[field] = _finite_number(
            settings.get("exposure"), f"analysis.sidecar.{field}.exposure"
        )
    if len(set(values.values())) != 1:
        raise V3LightnessWorkflowError(
            "analysis requested/effective exposure binding differs"
        )
    return values


def _verify_analyzer_integrity(
    value: Mapping[str, Any], label: str
) -> tuple[dict[str, Any], str]:
    integrity = _mapping(value.get("integrity"), f"{label}.integrity")
    try:
        require_exact_keys(integrity, {"algorithm", "sha256"}, f"{label}.integrity")
        expected = require_sha256(integrity.get("sha256"), f"{label}.integrity.sha256")
    except StaticPhotoContractError as error:
        raise V3LightnessWorkflowError(str(error)) from error
    if integrity.get("algorithm") != "sha256-canonical-json-without-integrity":
        raise V3LightnessWorkflowError(f"{label} integrity algorithm differs")
    unsigned = dict(value)
    unsigned.pop("integrity", None)
    if canonical_sha256(unsigned) != expected:
        raise V3LightnessWorkflowError(f"{label} canonical SHA-256 differs")
    return unsigned, expected


def _validate_root_identity(value: Mapping[str, Any], *, kind: str, label: str) -> None:
    expected = {
        "schema_version": 1,
        "kind": kind,
        "campaign_id": V3_CAMPAIGN_ID,
        "test_id": V3_TEST_ID,
        "contract_id": V3_CONTRACT_ID,
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise V3LightnessWorkflowError(f"{label} identity or offline boundary differs")


def _validate_zero_qualification_boundary(
    value: Mapping[str, Any],
    *,
    label: str,
    require_camera_relative: bool = True,
    cross_controller_key: str = "cross_controller_equivalence_proven",
) -> None:
    boundary = _mapping(value.get("qualification_boundary"), f"{label}.boundary")
    if (
        boundary.get("qualified_colour_count") != 0
        or boundary.get("qualified_gray_levels") != 0
    ):
        raise V3LightnessWorkflowError(
            f"{label} contains an earned qualification claim"
        )
    if require_camera_relative and boundary.get("camera_relative_only") is not True:
        raise V3LightnessWorkflowError(f"{label} is not camera-relative only")
    if boundary.get(cross_controller_key) is not False:
        raise V3LightnessWorkflowError(
            f"{label} cross-controller equivalence boundary differs"
        )


def _analysis_quality_pass(value: Mapping[str, Any]) -> bool:
    quality = _mapping(value.get("capture_quality"), "analysis.capture_quality")
    required = (
        "both_controller_rois_visible",
        "exposure_usable",
        "focus_usable",
        "glare_not_material",
    )
    for key in required:
        if quality.get(key) not in ("PASS", "FAIL", "UNKNOWN"):
            raise V3LightnessWorkflowError(f"analysis capture quality {key} differs")
    if type(quality.get("single_pixel_fill_coarse_uniformity_pass")) is not bool:
        raise V3LightnessWorkflowError(
            "analysis single-pixel coarse-uniformity flag differs"
        )
    return all(quality[key] == "PASS" for key in required) and bool(
        quality["single_pixel_fill_coarse_uniformity_pass"]
    )


def _validate_analysis(
    report: Mapping[str, Any], *, report_file_sha256: str
) -> tuple[
    dict[str, Any],
    str,
    tuple[LightnessMeasurement, ...],
    dict[str, int],
    dict[str, float],
]:
    file_sha = require_sha256(report_file_sha256, "analysis_file_sha256")
    unsigned, analysis_canonical = _verify_analyzer_integrity(report, "analysis")
    _validate_root_identity(unsigned, kind=V3_CAMERA_ANALYSIS_KIND, label="analysis")
    if unsigned.get("stage") != "L3":
        raise V3LightnessWorkflowError(
            "only an L3 camera analysis can seed a shortlist"
        )
    _validate_zero_qualification_boundary(unsigned, label="analysis")

    method = _mapping(unsigned.get("method"), "analysis.method")
    if (
        method.get("controllers_pooled") is not False
        or method.get("cs1_cs2_colour_equivalence_claimed") is not False
        or method.get("absolute_colour_claimed") is not False
    ):
        raise V3LightnessWorkflowError("analysis controller or colour boundary differs")
    if method.get("spatial_dithering_used") is True:
        raise V3LightnessWorkflowError("spatial dithering is forbidden")

    sidecar = _mapping(
        unsigned.get("source_capture_sidecar"), "analysis.source_capture_sidecar"
    )
    if sidecar.get("camera_usb_identity") != PROJECT_CAMERA_USB_ID:
        raise V3LightnessWorkflowError("analysis camera USB identity differs")
    if sidecar.get("capture_binding") != "live_synchronized":
        raise V3LightnessWorkflowError("analysis capture binding differs")
    exposure_binding = _capture_exposure_binding(sidecar)
    global_quality_pass = _analysis_quality_pass(unsigned)

    thresholds = _mapping(unsigned.get("quality_thresholds"), "analysis.thresholds")
    maximum_low_clip = _finite_nonnegative(
        thresholds.get("maximum_all_channels_low_clip_fraction"),
        "maximum_all_channels_low_clip_fraction",
    )
    maximum_high_clip = _finite_nonnegative(
        thresholds.get("maximum_any_channel_high_clip_fraction"),
        "maximum_any_channel_high_clip_fraction",
    )
    maximum_rgb_mad = _finite_nonnegative(
        thresholds.get("maximum_center_rgb_mad"), "maximum_center_rgb_mad"
    )

    controller_results = _mapping(
        unsigned.get("controller_results"), "analysis.controller_results"
    )
    if set(controller_results) != {item.value for item in Controller}:
        raise V3LightnessWorkflowError("analysis controller result set differs")
    for controller in Controller:
        result = _mapping(
            controller_results[controller.value],
            f"analysis.controller_results.{controller.value}",
        )
        if (
            result.get("controller") != controller.value
            or result.get("controller_local_only") is not True
        ):
            raise V3LightnessWorkflowError(
                f"analysis {controller.value} controller-local boundary differs"
            )

    cells = unsigned.get("cells")
    if not isinstance(cells, list) or len(cells) != 128:
        raise V3LightnessWorkflowError("analysis must contain exactly 128 cells")
    identities: set[tuple[str, int, int]] = set()
    logical_identities: set[tuple[str, int, int]] = set()
    middle_counts: Counter[tuple[str, int]] = Counter()
    measurements: list[LightnessMeasurement] = []
    middle_by_recipe: dict[str, int] = {}
    for index, raw_cell in enumerate(cells):
        cell = _mapping(raw_cell, f"analysis.cells[{index}]")
        try:
            controller = Controller(cell.get("controller"))
        except ValueError as error:
            raise V3LightnessWorkflowError(
                "analysis cell controller differs"
            ) from error
        row = _integer(cell.get("physical_row"), "physical_row", minimum=0, maximum=7)
        column = _integer(
            cell.get("physical_column"), "physical_column", minimum=0, maximum=7
        )
        logical_row = _integer(
            cell.get("logical_row"), "logical_row", minimum=0, maximum=7
        )
        logical_column = _integer(
            cell.get("logical_column"), "logical_column", minimum=0, maximum=7
        )
        identity = (controller.value, row, column)
        logical_identity = (controller.value, logical_row, logical_column)
        if identity in identities or logical_identity in logical_identities:
            raise V3LightnessWorkflowError("analysis cell coordinate is duplicated")
        identities.add(identity)
        logical_identities.add(logical_identity)
        middle_code = _integer(
            cell.get("middle_code"), "middle_code", minimum=0, maximum=7
        )
        middle_counts[(controller.value, middle_code)] += 1
        recipe_id = f"V3-{controller.value}-M{middle_code}"
        middle_by_recipe[recipe_id] = middle_code
        try:
            lab = finite_triple(
                cell.get("illumination_normalized_camera_relative_lab"),
                "illumination_normalized_camera_relative_lab",
            )
        except StaticPhotoContractError as error:
            raise V3LightnessWorkflowError(str(error)) from error
        if not 0.0 <= lab[0] <= 100.0:
            raise V3LightnessWorkflowError("analysis cell L* is outside 0..100")
        stripe = cell.get("bottom_edge_stripe")
        if stripe not in ("CLEAR", "PRESENT", "UNCERTAIN"):
            raise V3LightnessWorkflowError("analysis bottom-edge state differs")
        if cell.get("spatial_dithering_used") is True:
            raise V3LightnessWorkflowError("spatial dithering is forbidden")
        center_mad = finite_triple(cell.get("center_rgb_mad"), "center_rgb_mad")
        if any(value < 0.0 for value in center_mad):
            raise V3LightnessWorkflowError("center_rgb_mad must be non-negative")
        low_clip = _finite_nonnegative(
            cell.get("center_all_channels_low_clip_fraction"),
            "center_all_channels_low_clip_fraction",
        )
        high_clip = _finite_nonnegative(
            cell.get("center_any_channel_high_clip_fraction"),
            "center_any_channel_high_clip_fraction",
        )
        cell_quality_pass = (
            global_quality_pass
            and stripe == "CLEAR"
            and low_clip <= maximum_low_clip
            and high_clip <= maximum_high_clip
            and max(center_mad) <= maximum_rgb_mad
        )
        measurements.append(
            LightnessMeasurement(
                controller=controller,
                lut_profile_id=V3_TARGET_LUT_PROFILE_ID,
                target_code=V3_TARGET_CODE,
                recipe_id=recipe_id,
                replica_id=f"physical-r{row}-c{column}",
                phase=MeasurementPhase.TARGET,
                measured_lab=lab,
                single_pixel_pure=cell_quality_pass,
                boundary_clean=cell_quality_pass and stripe == "CLEAR",
                measurement_artifact_sha256=file_sha,
            )
        )
    expected_identities = {
        (controller.value, row, column)
        for controller in Controller
        for row in range(8)
        for column in range(8)
    }
    if identities != expected_identities or logical_identities != expected_identities:
        raise V3LightnessWorkflowError("analysis cell coverage differs")
    expected_middle_counts = {
        (controller.value, code): EXPECTED_REPLICAS_PER_RECIPE
        for controller in Controller
        for code in range(8)
    }
    if dict(middle_counts) != expected_middle_counts:
        raise V3LightnessWorkflowError("analysis Latin middle-code balance differs")
    return (
        unsigned,
        analysis_canonical,
        tuple(measurements),
        middle_by_recipe,
        exposure_binding,
    )


def _validate_repeat_comparison(
    report: Mapping[str, Any],
    *,
    report_file_sha256: str,
    analysis_file_sha256: str,
    analysis_canonical_sha256: str,
    analysis_exposure_binding: Mapping[str, float],
) -> tuple[dict[Controller, bool], dict[str, Any]]:
    repeat_file_sha = require_sha256(
        report_file_sha256, "repeat_comparison_file_sha256"
    )
    unsigned, repeat_canonical = _verify_analyzer_integrity(report, "repeat_comparison")
    _validate_root_identity(
        unsigned, kind=V3_REPEAT_COMPARISON_KIND, label="repeat_comparison"
    )
    _validate_zero_qualification_boundary(
        unsigned,
        label="repeat_comparison",
        require_camera_relative=False,
        cross_controller_key="cross_controller_equivalence_claimed",
    )
    repeat_boundary = _mapping(
        unsigned.get("qualification_boundary"), "repeat_comparison.boundary"
    )
    try:
        require_exact_keys(
            repeat_boundary,
            _REPEAT_QUALIFICATION_BOUNDARY_KEYS,
            "repeat_comparison.boundary",
        )
    except StaticPhotoContractError as error:
        raise V3LightnessWorkflowError(str(error)) from error
    if (
        repeat_boundary.get("repeatable_signal_is_not_a_qualified_gray_level")
        is not True
        or repeat_boundary.get("absolute_colour_claimed") is not False
        or repeat_boundary.get("persistence_proven") is not False
    ):
        raise V3LightnessWorkflowError(
            "repeat comparison qualification boundary differs"
        )
    comparability = _mapping(
        unsigned.get("comparability"), "repeat_comparison.comparability"
    )
    comparability_keys = set(comparability)
    if comparability_keys == _LEGACY_REPEAT_COMPARABILITY_KEYS:
        comparison_mode = "UNEQUAL_EXPOSURE_CONTROLLER_CENTERED_ONLY"
    elif comparability_keys == _SAME_EXPOSURE_REPEAT_COMPARABILITY_KEYS:
        comparison_mode = "SAME_EXPOSURE_RAW_AND_CONTROLLER_CENTERED"
    else:
        raise V3LightnessWorkflowError("repeat comparison comparability schema differs")
    if (
        comparability.get("analysis_method_equal") is not True
        or comparability.get("analysis_thresholds_equal") is not True
        or comparability.get("camera_settings_except_exposure_equal") is not True
        or comparability.get("controller_local_centered_lightness_comparison_used")
        is not True
        or comparability.get("cross_controller_comparison_used") is not False
    ):
        raise V3LightnessWorkflowError("repeat comparison boundary differs")
    l3_exposure = _finite_number(
        comparability.get("l3_requested_exposure"),
        "repeat comparison L3 requested exposure",
    )
    l4_exposure = _finite_number(
        comparability.get("l4_requested_exposure"),
        "repeat comparison L4 requested exposure",
    )
    if any(value != l3_exposure for value in analysis_exposure_binding.values()):
        raise V3LightnessWorkflowError(
            "repeat comparison L3 requested exposure differs from source analysis"
        )
    if comparison_mode == "UNEQUAL_EXPOSURE_CONTROLLER_CENTERED_ONLY":
        if (
            comparability.get("camera_exposure_equal") is not False
            or comparability.get("raw_absolute_lab_repeat_comparable") is not False
            or l3_exposure == l4_exposure
            or repeat_boundary.get("same_exposure_repeat_proven") is not False
        ):
            raise V3LightnessWorkflowError(
                "unequal-exposure repeat comparison boundary differs"
            )
    else:
        for field in (
            "exact_by_field",
            "except_exposure_equal_by_field",
            "exposure_equal_by_field",
        ):
            by_field = _mapping(comparability.get(field), f"repeat comparison {field}")
            if set(by_field) != _SETTINGS_COMPARISON_FIELDS or any(
                by_field[item] is not True for item in _SETTINGS_COMPARISON_FIELDS
            ):
                raise V3LightnessWorkflowError(
                    f"same-exposure repeat comparison {field} differs"
                )
        if (
            comparability.get("camera_settings_exactly_equal") is not True
            or comparability.get("camera_exposure_equal") is not True
            or comparability.get("raw_absolute_lab_repeat_comparable") is not True
            or l3_exposure != l4_exposure
            or repeat_boundary.get("same_exposure_repeat_proven") is not True
        ):
            raise V3LightnessWorkflowError(
                "same-exposure repeat comparison boundary differs"
            )
    source_l3 = _mapping(
        _mapping(unsigned.get("source_reports"), "repeat source reports").get("L3"),
        "repeat source L3",
    )
    source_reports = _mapping(unsigned.get("source_reports"), "repeat source reports")
    if set(source_reports) != {"L3", "L4"}:
        raise V3LightnessWorkflowError("repeat comparison source report set differs")
    for stage in ("L3", "L4"):
        source = _mapping(source_reports[stage], f"repeat source {stage}")
        try:
            require_exact_keys(
                source,
                {"path", "bytes", "sha256", "canonical_integrity_sha256"},
                f"repeat source {stage}",
            )
            require_text(source.get("path"), f"repeat source {stage} path")
            require_sha256(source.get("sha256"), f"repeat source {stage} sha256")
            require_sha256(
                source.get("canonical_integrity_sha256"),
                f"repeat source {stage} canonical sha256",
            )
        except StaticPhotoContractError as error:
            raise V3LightnessWorkflowError(str(error)) from error
        if type(source.get("bytes")) is not int or source["bytes"] <= 0:
            raise V3LightnessWorkflowError(f"repeat source {stage} byte count differs")
    if (
        source_l3.get("sha256") != analysis_file_sha256
        or source_l3.get("canonical_integrity_sha256") != analysis_canonical_sha256
    ):
        raise V3LightnessWorkflowError("repeat comparison L3 source binding differs")
    if (
        type(unsigned.get("quality_gate_pass")) is not bool
        or type(unsigned.get("bottom_edge_clear_in_both_captures")) is not bool
    ):
        raise V3LightnessWorkflowError("repeat comparison gate schema differs")
    quality_pass = unsigned["quality_gate_pass"]
    edge_pass = unsigned["bottom_edge_clear_in_both_captures"]
    raw_results = _mapping(
        unsigned.get("controller_results"), "repeat controller results"
    )
    if set(raw_results) != {item.value for item in Controller}:
        raise V3LightnessWorkflowError("repeat controller result set differs")
    gates: dict[Controller, bool] = {}
    for controller in Controller:
        item = _mapping(raw_results[controller.value], f"repeat {controller.value}")
        if (
            item.get("controller") != controller.value
            or item.get("controller_local_only") is not True
            or item.get("raw_absolute_lab_repeat_claimed") is not False
            or type(item.get("centered_lightness_repeat_gate_pass")) is not bool
        ):
            raise V3LightnessWorkflowError(
                f"repeat {controller.value} controller-local boundary differs"
            )
        gates[controller] = bool(
            quality_pass and edge_pass and item["centered_lightness_repeat_gate_pass"]
        )
    return gates, {
        "file_sha256": repeat_file_sha,
        "canonical_sha256": repeat_canonical,
        "decision": require_text(unsigned.get("decision"), "repeat decision"),
        "comparison_mode": comparison_mode,
        "l3_requested_exposure": l3_exposure,
        "l4_requested_exposure": l4_exposure,
        "quality_gate_pass": quality_pass,
        "bottom_edge_clear_in_both_captures": edge_pass,
        "controller_local_repeat_screen_pass": {
            controller.value: gates[controller] for controller in Controller
        },
    }


def _candidate_inventory_preview(candidates: list[Any]) -> dict[str, Any]:
    candidate_records = [
        {
            "controller": candidate.controller.value,
            "candidate": candidate.unsigned_mapping(),
            "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
            "qualification_state": "COARSE_CANDIDATE_ONLY",
            "blocking_reasons": [
                "pending:controller-local-hold",
                "pending:independent-factory-otp-white-baseline",
                "pending:fresh-white-reconstruction-repeat",
                "pending:final-factory-otp-white-containment",
            ],
        }
        for candidate in candidates
    ]
    candidate_records.sort(
        key=lambda item: (
            item["controller"],
            item["candidate"]["candidate_id"],
        )
    )
    return attach_integrity(
        {
            "schema_version": 1,
            "kind": "MF1750_V3_UNQUALIFIED_CONTROLLER_PALETTE_CANDIDATE_PREVIEW",
            "candidate_count": len(candidate_records),
            "controller_local_qualified_recipe_count": 0,
            "candidates": candidate_records,
            "evidence_boundaries": {
                "coarse_candidate_automatically_promoted": False,
                "controllers_pooled": False,
                "spatial_dithering_counts_as_colour": False,
                "legacy_identical_target_repeat_qualification_path_used": False,
                "v3_identical_target_repeat_collapse_respected": True,
                "hardware_accessed": False,
                "live_authorized": False,
            },
        }
    )


def build_v3_lightness_hold_repeat_white_workflow(
    analysis: Mapping[str, Any],
    *,
    analysis_file_sha256: str,
    repeat_comparison: Mapping[str, Any] | None = None,
    repeat_comparison_file_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a controller-local shortlist and non-executable evidence plan.

    The optional repeat comparison is a screening gate only.  Even a passing
    comparison cannot qualify a candidate.  V3 showed that refreshing the
    same target after HOLD collapses the intended history, so this plan never
    performs an in-place identical-target repeat.  A shortlisted candidate
    instead requires HOLD validation, an independent factory-white baseline,
    reconstruction from that fresh white anchor, and final factory-white
    containment.
    """

    if not isinstance(analysis, Mapping):
        raise V3LightnessWorkflowError("analysis must be an object")
    try:
        (
            analysis_unsigned,
            analysis_canonical,
            measurements,
            middle_by_recipe,
            analysis_exposure_binding,
        ) = _validate_analysis(
            analysis,
            report_file_sha256=analysis_file_sha256,
        )
    except StaticPhotoContractError as error:
        raise V3LightnessWorkflowError(str(error)) from error
    if (repeat_comparison is None) != (repeat_comparison_file_sha256 is None):
        raise V3LightnessWorkflowError(
            "repeat comparison and its file SHA-256 must be supplied together"
        )

    lightness_report = screen_lightness_ladders(
        measurements,
        minimum_replicas=EXPECTED_REPLICAS_PER_RECIPE,
    )
    repeat_gates: dict[Controller, bool] | None = None
    repeat_summary: dict[str, Any] | None = None
    if repeat_comparison is not None and repeat_comparison_file_sha256 is not None:
        repeat_gates, repeat_summary = _validate_repeat_comparison(
            repeat_comparison,
            report_file_sha256=repeat_comparison_file_sha256,
            analysis_file_sha256=analysis_file_sha256,
            analysis_canonical_sha256=analysis_canonical,
            analysis_exposure_binding=analysis_exposure_binding,
        )

    group_by_controller = {
        group["controller"]: group for group in lightness_report["groups"]
    }
    candidates = []
    excluded_after_repeat: dict[str, list[str]] = {
        controller.value: [] for controller in Controller
    }
    for controller in Controller:
        group = group_by_controller.get(controller.value)
        if not isinstance(group, Mapping):
            raise V3LightnessWorkflowError("lightness screen controller group differs")
        pair_members = sorted(
            {
                recipe_id
                for pair in group["candidate_pairs"]
                for recipe_id in (
                    pair["darker_recipe_id"],
                    pair["lighter_recipe_id"],
                )
            }
        )
        if repeat_gates is not None and not repeat_gates[controller]:
            excluded_after_repeat[controller.value].extend(pair_members)
            continue
        for recipe_id in pair_members:
            candidates.append(
                candidate_from_lightness_screen(
                    lightness_report,
                    controller=controller,
                    lut_profile_id=V3_TARGET_LUT_PROFILE_ID,
                    target_code=V3_TARGET_CODE,
                    recipe_id=recipe_id,
                    source_code=V3_SOURCE_CODE,
                    middle_code=middle_by_recipe[recipe_id],
                    target_repeat_count=1,
                    report_file_sha256=analysis_file_sha256,
                )
            )

    inventory = _candidate_inventory_preview(candidates)
    inventory_by_key = {
        (
            item["controller"],
            item["candidate"]["candidate_id"],
        ): item
        for item in inventory["candidates"]
    }
    shortlist_by_controller: dict[str, list[dict[str, Any]]] = {
        controller.value: [] for controller in Controller
    }
    for candidate in candidates:
        record = inventory_by_key[(candidate.controller.value, candidate.candidate_id)]
        shortlist_by_controller[candidate.controller.value].append(
            {
                "candidate": candidate.unsigned_mapping(),
                "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
                "qualification_state": record["qualification_state"],
                "blocking_reasons": record["blocking_reasons"],
                "repeat_comparison_screen_pass": (
                    None if repeat_gates is None else repeat_gates[candidate.controller]
                ),
            }
        )
    for values in shortlist_by_controller.values():
        values.sort(key=lambda item: item["candidate"]["candidate_id"])

    shortlist_count = len(candidates)
    candidate_refs = {
        controller.value: [
            item["candidate_fingerprint_sha256"]
            for item in shortlist_by_controller[controller.value]
        ]
        for controller in Controller
    }
    has_shortlist = shortlist_count > 0
    plan_steps = [
        {
            "order": 1,
            "role": "CONTROLLER_LOCAL_HOLD_VALIDATION",
            "status": "REQUIRED" if has_shortlist else "SKIPPED_EMPTY_SHORTLIST",
            "candidate_fingerprints_by_controller": candidate_refs,
            "must_preserve_other_controller_and_non_target_pixels": True,
            "spatial_dithering_allowed": False,
            "qualification_evidence_created_by_plan": False,
        },
        {
            "order": 2,
            "role": "INDEPENDENT_FACTORY_OTP_WHITE_BASELINE",
            "status": (
                "BLOCKED_UNTIL_HOLD_PASS"
                if has_shortlist
                else "SKIPPED_EMPTY_SHORTLIST"
            ),
            "candidate_fingerprints_by_controller": candidate_refs,
            "prior_hold_pass_required": True,
            "must_capture_independent_factory_white_anchor": True,
            "hold_observation_must_be_closed_before_white_baseline": True,
            "qualification_evidence_created_by_plan": False,
        },
        {
            "order": 3,
            "role": "FRESH_WHITE_RECONSTRUCTION_REPEAT",
            "status": (
                "BLOCKED_UNTIL_INDEPENDENT_WHITE_BASELINE_PASS"
                if has_shortlist
                else "SKIPPED_EMPTY_SHORTLIST"
            ),
            "candidate_fingerprints_by_controller": candidate_refs,
            "must_start_from_independent_factory_otp_white_baseline": True,
            "reexecute_full_colour_construction_chain": True,
            "in_place_identical_target_repeat_allowed": False,
            "original_candidate_overwrite_allowed": False,
            "fresh_reconstruction_artifact_required": True,
            "qualification_evidence_created_by_plan": False,
        },
        {
            "order": 4,
            "role": "FINAL_FACTORY_OTP_WHITE_CONTAINMENT",
            "status": "REQUIRED_CAMPAIGN_CONTAINMENT",
            "independent_successor_required": True,
            "required_even_when_shortlist_empty": True,
            "qualification_evidence_created_by_plan": False,
        },
    ]
    unsigned = {
        "schema_version": 1,
        "kind": "MF1750_V3_CAMERA_LIGHTNESS_TO_HOLD_REPEAT_WHITE_WORKFLOW",
        "campaign_id": V3_CAMPAIGN_ID,
        "test_id": V3_TEST_ID,
        "contract_id": V3_CONTRACT_ID,
        "source_analysis": {
            "file_sha256": require_sha256(analysis_file_sha256, "analysis_file_sha256"),
            "canonical_sha256": analysis_canonical,
            "decision": require_text(
                analysis_unsigned.get("decision"), "analysis decision"
            ),
            "camera_usb_identity": PROJECT_CAMERA_USB_ID,
            "camera_relative_only": True,
        },
        "repeat_comparison": repeat_summary,
        "controller_local_lightness_screen": lightness_report,
        "shortlist": {
            "status": (
                "COARSE_CONTROLLER_LOCAL_SHORTLIST_PENDING_EVIDENCE"
                if has_shortlist
                else "EMPTY_NO_CONTROLLER_LOCAL_LIGHTNESS_CANDIDATE"
            ),
            "candidate_count": shortlist_count,
            "by_controller": shortlist_by_controller,
            "excluded_after_repeat_screen_by_controller": excluded_after_repeat,
            "qualified_colour_count": 0,
            "qualified_gray_level_count": 0,
            "qualified_lightness_level_count": 0,
            "automatic_promotion_forbidden": True,
        },
        "candidate_inventory_preview": inventory,
        "evidence_plan": {
            "status": (
                "SHORTLIST_REQUIRES_HOLD_WHITE_BASELINE_FRESH_RECONSTRUCTION_FINAL_WHITE"
                if has_shortlist
                else "NO_SHORTLIST_WHITE_CONTAINMENT_ONLY"
            ),
            "ordered_roles": [
                "CONTROLLER_LOCAL_HOLD_VALIDATION",
                "INDEPENDENT_FACTORY_OTP_WHITE_BASELINE",
                "FRESH_WHITE_RECONSTRUCTION_REPEAT",
                "FINAL_FACTORY_OTP_WHITE_CONTAINMENT",
            ],
            "steps": plan_steps,
            "autochain_allowed": False,
            "live_authorized": False,
            "hardware_action_ids_allocated": False,
        },
        "feature_priority": {
            "lightness_and_gray_function_path": "ACTIVE",
            "hue_enumeration": "DEFERRED",
            "hue_enumeration_deferred": True,
            "reason": (
                "Complete controller-local HOLD, independent white baseline, "
                "fresh reconstruction, and final white containment before "
                "expanding hue search."
            ),
        },
        "evidence_boundaries": {
            "controllers_pooled": False,
            "cross_controller_difference_counts_as_lightness": False,
            "spatial_dithering_counts_as_colour": False,
            "camera_is_colorimeter": False,
            "review_or_zero_qualified_input_auto_promoted": False,
            "repeat_comparison_auto_creates_qualification_evidence": False,
            "identical_target_repeat_after_hold_planned": False,
            "fresh_white_reconstruction_is_in_place_target_repeat": False,
            "v3_identical_target_repeat_collapse_respected": True,
            "qualified_palette_recipe_count": 0,
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
            "live_authorized": False,
        },
    }
    return attach_integrity(unsigned)


__all__ = [
    "PROJECT_CAMERA_USB_ID",
    "V3LightnessWorkflowError",
    "build_v3_lightness_hold_repeat_white_workflow",
]
