"""Qualification-bound N5 palette and 6x6 transition aggregation.

The builders and aggregators operate on caller-supplied records only.  They
perform no acquisition, claim, authorization, network, serial, GPIO, or device
I/O.  A measured palette/profile is emitted only when every preregistered slot,
qualified instrument field, authoritative spectral input, and shared physical
context is complete.  Blocked reports contain no measured artifact that could
be promoted by changing a boolean flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence

from host.color_pipeline import PaletteError, delta_e_ciede2000, palette_from_mapping

from .offline import COLOR_NAME_BY_CODE, COLOR_ORDER
from .profile import build_empty_transition_profile, validate_transition_profile
from .spectral import (
    SpectralContractError,
    canonical_json_bytes,
    spectral_report_file_sha256,
    validate_authoritative_standard_table,
    validate_reflectance_record,
    validate_spectral_report,
)


SCHEMA_VERSION = 1
INSTRUMENT_KIND = "mf1750-n5-optical-instrument-qualification"
PALETTE_PLAN_KIND = "mf1750-n5-formal-palette-measurement-plan"
TRANSITION_PLAN_KIND = "mf1750-n5-descriptive-transition-atlas-plan"
TRANSITION_FORMAL_PLAN_KIND = "mf1750-n5-formal-transition-measurement-plan"
PALETTE_OBSERVATION_KIND = "mf1750-n5-palette-observation"
TRANSITION_OBSERVATION_KIND = "mf1750-n5-transition-observation"
PALETTE_AGGREGATE_KIND = "mf1750-n5-measured-palette-aggregate"
TRANSITION_AGGREGATE_KIND = "mf1750-n5-transition-profile-aggregate"

CANONICAL_HASH_SCOPE = (
    "entire document excluding integrity; UTF-8 JSON sorted keys, no whitespace, "
    "ensure_ascii=false, allow_nan=false"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


class MeasurementAggregationError(ValueError):
    """An N5 qualification, plan, observation, or aggregate failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (SpectralContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MeasurementAggregationError(f"value is not canonical JSON: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": CANONICAL_HASH_SCOPE,
    }


def _mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeasurementAggregationError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise MeasurementAggregationError(
            f"{label} keys differ from contract; missing={missing}, extra={extra}"
        )
    return value


def _text(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        suffix = " or null" if nullable else ""
        raise MeasurementAggregationError(f"{label} must be non-empty text{suffix}")
    if any(ord(character) < 0x20 for character in value):
        raise MeasurementAggregationError(f"{label} contains control characters")
    return value


def _hash(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise MeasurementAggregationError(f"{label} must be a lowercase SHA-256{suffix}")
    if value == "0" * 64:
        raise MeasurementAggregationError(f"{label} must not be a placeholder SHA-256")
    return value


def _hex40(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HEX40_RE.fullmatch(value) is None:
        raise MeasurementAggregationError(f"{label} must be 40 lowercase hex digits")
    if value == "0" * 40:
        raise MeasurementAggregationError(f"{label} must not be a placeholder identity")
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    nullable: bool = False,
) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise MeasurementAggregationError(f"{label} must be finite{suffix}")
    result = float(value)
    if not math.isfinite(result):
        raise MeasurementAggregationError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise MeasurementAggregationError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise MeasurementAggregationError(f"{label} is above {maximum}")
    return result


def _timestamp(value: Any, *, label: str, nullable: bool = False) -> Optional[datetime]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise MeasurementAggregationError(f"{label} must be strict RFC3339{suffix}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MeasurementAggregationError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MeasurementAggregationError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_integrity(document: Mapping[str, Any], *, label: str) -> None:
    unsigned = dict(document)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise MeasurementAggregationError(f"{label} canonical integrity is invalid")


def seal_instrument_qualification(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a draft or complete optical-instrument qualification."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise MeasurementAggregationError("instrument qualification payload must omit integrity")
    unsigned = _snapshot(payload)
    result = {**unsigned, "integrity": _integrity(unsigned)}
    validate_instrument_qualification(result)
    return result


def validate_instrument_qualification(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        record,
        label="instrument qualification",
        keys={
            "schema_version",
            "kind",
            "qualification_id",
            "qualified",
            "instrument",
            "calibration",
            "optical_geometry",
            "repeatability",
            "review",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != INSTRUMENT_KIND:
        raise MeasurementAggregationError("instrument qualification schema or kind is invalid")
    _text(root["qualification_id"], label="qualification_id")
    if type(root["qualified"]) is not bool:
        raise MeasurementAggregationError("instrument qualified must be boolean")
    instrument = _mapping(
        root["instrument"],
        label="qualified instrument",
        keys={
            "category",
            "manufacturer",
            "model",
            "serial_number",
            "firmware_version",
            "configuration_sha256",
        },
    )
    calibration = _mapping(
        root["calibration"],
        label="instrument calibration",
        keys={
            "certificate_id",
            "calibration_lab",
            "calibrated_at",
            "calibration_due_at",
            "certificate_artifact_sha256",
            "traceability",
            "expanded_uncertainty_delta_e00",
        },
    )
    geometry = _mapping(
        root["optical_geometry"],
        label="instrument optical geometry",
        keys={
            "geometry",
            "spectral_start_nm",
            "spectral_end_nm",
            "spectral_interval_nm",
            "aperture_mm",
            "panel_normal_error_deg",
            "fixture_review_artifact_sha256",
        },
    )
    repeatability = _mapping(
        root["repeatability"],
        label="instrument repeatability",
        keys={
            "stationary_sample_count",
            "repositioned_sample_count",
            "session_count",
            "passed",
            "report_artifact_sha256",
        },
    )
    review = _mapping(
        root["review"],
        label="instrument review",
        keys={"approved", "reviewer_id", "reviewed_at", "review_artifact_sha256"},
    )
    if type(repeatability["passed"]) is not bool or type(review["approved"]) is not bool:
        raise MeasurementAggregationError("instrument repeatability/review flags must be boolean")
    nullable = not root["qualified"]
    for field in ("category", "manufacturer", "model", "serial_number", "firmware_version"):
        _text(instrument[field], label=f"instrument.{field}", nullable=nullable)
    _hash(
        instrument["configuration_sha256"],
        label="instrument.configuration_sha256",
        nullable=nullable,
    )
    for field in ("certificate_id", "calibration_lab", "traceability"):
        _text(calibration[field], label=f"calibration.{field}", nullable=nullable)
    calibrated_at = _timestamp(
        calibration["calibrated_at"], label="calibration.calibrated_at", nullable=nullable
    )
    due_at = _timestamp(
        calibration["calibration_due_at"],
        label="calibration.calibration_due_at",
        nullable=nullable,
    )
    if calibrated_at is not None and due_at is not None and due_at <= calibrated_at:
        raise MeasurementAggregationError("instrument calibration validity interval is empty")
    _hash(
        calibration["certificate_artifact_sha256"],
        label="calibration certificate artifact",
        nullable=nullable,
    )
    _number(
        calibration["expanded_uncertainty_delta_e00"],
        label="calibration expanded uncertainty",
        minimum=0,
        nullable=nullable,
    )
    _text(geometry["geometry"], label="optical geometry", nullable=nullable)
    for field in ("spectral_start_nm", "spectral_end_nm", "spectral_interval_nm"):
        value = geometry[field]
        if value is None and nullable:
            continue
        if type(value) is not int or value <= 0:
            raise MeasurementAggregationError(f"optical_geometry.{field} must be positive integer")
    _number(geometry["aperture_mm"], label="optical aperture", minimum=0.000001, nullable=nullable)
    _number(
        geometry["panel_normal_error_deg"],
        label="panel normal error",
        minimum=0,
        nullable=nullable,
    )
    _hash(
        geometry["fixture_review_artifact_sha256"],
        label="fixture review artifact",
        nullable=nullable,
    )
    for field in ("stationary_sample_count", "repositioned_sample_count", "session_count"):
        value = repeatability[field]
        if value is None and nullable:
            continue
        if type(value) is not int or value < 0:
            raise MeasurementAggregationError(f"repeatability.{field} must be nonnegative integer")
    _hash(
        repeatability["report_artifact_sha256"],
        label="repeatability report artifact",
        nullable=nullable,
    )
    _text(review["reviewer_id"], label="instrument reviewer", nullable=nullable)
    _timestamp(review["reviewed_at"], label="instrument reviewed_at", nullable=nullable)
    _hash(
        review["review_artifact_sha256"],
        label="instrument review artifact",
        nullable=nullable,
    )
    if root["qualified"] and instrument_qualification_blockers(root):
        raise MeasurementAggregationError(
            "qualified instrument record does not satisfy every qualification gate"
        )
    _validate_integrity(root, label="instrument qualification")
    return root


def instrument_qualification_blockers(
    record: Mapping[str, Any],
    *,
    captured_at: Optional[str] = None,
    standard_table: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    """Evaluate qualification completeness without promoting a draft flag."""

    # This helper is also called during validation before integrity is checked.
    root = record
    blockers: list[str] = []
    if root.get("qualified") is not True:
        blockers.append("instrument_qualification_not_qualified")
    instrument = root.get("instrument", {})
    if instrument.get("category") not in {"spectrophotometer", "spectroradiometer"}:
        blockers.append("instrument_category_not_spectral")
    if any(instrument.get(field) is None for field in instrument):
        blockers.append("instrument_identity_or_configuration_missing")
    calibration = root.get("calibration", {})
    if any(calibration.get(field) is None for field in calibration):
        blockers.append("instrument_calibration_evidence_missing")
    geometry = root.get("optical_geometry", {})
    if geometry.get("geometry") != "45/0":
        blockers.append("optical_geometry_not_45_0")
    normal_error = geometry.get("panel_normal_error_deg")
    if (
        isinstance(normal_error, bool)
        or not isinstance(normal_error, (int, float))
        or not math.isfinite(float(normal_error))
        or float(normal_error) > 2
    ):
        blockers.append("panel_normal_error_not_within_2deg")
    if geometry.get("aperture_mm") is None:
        blockers.append("instrument_aperture_missing")
    if geometry.get("fixture_review_artifact_sha256") is None:
        blockers.append("optical_fixture_review_missing")
    repeatability = root.get("repeatability", {})
    stationary_count = repeatability.get("stationary_sample_count")
    repositioned_count = repeatability.get("repositioned_sample_count")
    session_count = repeatability.get("session_count")
    if (
        type(stationary_count) is not int
        or stationary_count < 10
        or type(repositioned_count) is not int
        or repositioned_count < 10
        or type(session_count) is not int
        or session_count < 2
        or repeatability.get("passed") is not True
        or repeatability.get("report_artifact_sha256") is None
    ):
        blockers.append("instrument_repeatability_or_reproducibility_not_qualified")
    review = root.get("review", {})
    if (
        review.get("approved") is not True
        or any(
            review.get(field) is None
            for field in ("reviewer_id", "reviewed_at", "review_artifact_sha256")
        )
    ):
        blockers.append("instrument_qualification_review_incomplete")
    if captured_at is not None:
        captured = _timestamp(captured_at, label="captured_at")
        calibrated = _timestamp(
            calibration.get("calibrated_at"),
            label="calibration calibrated_at",
            nullable=True,
        )
        due = _timestamp(
            calibration.get("calibration_due_at"),
            label="calibration due_at",
            nullable=True,
        )
        if calibrated is None or due is None or captured is None or not calibrated <= captured < due:
            blockers.append("instrument_calibration_not_valid_at_capture")
    if standard_table is not None:
        table = validate_authoritative_standard_table(standard_table)
        grid = table["grid"]
        if (
            geometry.get("spectral_start_nm") is None
            or geometry["spectral_start_nm"] > grid["start_nm"]
            or geometry.get("spectral_end_nm") is None
            or geometry["spectral_end_nm"] < grid["end_nm"]
            or geometry.get("spectral_interval_nm") is None
            or geometry["spectral_interval_nm"] > grid["interval_nm"]
        ):
            blockers.append("instrument_spectral_grid_does_not_cover_standard_table")
    return list(dict.fromkeys(blockers))


def _validate_panel(value: Any) -> Mapping[str, Any]:
    panel = _mapping(
        value,
        label="measurement panel",
        keys={"model", "serial", "board_id", "pcb_revision"},
    )
    for field in panel:
        _text(panel[field], label=f"panel.{field}")
    return panel


def _validate_firmware(value: Any) -> Mapping[str, Any]:
    firmware = _mapping(
        value,
        label="measurement firmware",
        keys={"source_commit", "build_tag", "binary_sha256", "driver_api"},
    )
    _hex40(firmware["source_commit"], label="firmware.source_commit")
    _text(firmware["build_tag"], label="firmware.build_tag")
    _hash(firmware["binary_sha256"], label="firmware.binary_sha256")
    _text(firmware["driver_api"], label="firmware.driver_api")
    return firmware


def _validate_context(value: Any) -> Mapping[str, Any]:
    context = _mapping(
        value,
        label="measurement context",
        keys={"panel", "firmware", "waveform", "environment", "condition"},
    )
    _validate_panel(context["panel"])
    _validate_firmware(context["firmware"])
    waveform = _mapping(
        context["waveform"],
        label="measurement waveform",
        keys={"waveform_id", "waveform_sha256"},
    )
    _text(waveform["waveform_id"], label="waveform_id", nullable=True)
    _hash(waveform["waveform_sha256"], label="waveform_sha256", nullable=True)
    environment = _mapping(
        context["environment"],
        label="measurement environment",
        keys={"temperature_c", "relative_humidity_percent", "record_sha256"},
    )
    _number(
        environment["temperature_c"],
        label="environment.temperature_c",
        minimum=-100,
        maximum=200,
        nullable=True,
    )
    _number(
        environment["relative_humidity_percent"],
        label="environment.relative_humidity_percent",
        minimum=0,
        maximum=100,
        nullable=True,
    )
    _hash(environment["record_sha256"], label="environment.record_sha256", nullable=True)
    condition = _mapping(
        context["condition"],
        label="measurement condition",
        keys={
            "geometry",
            "illuminant",
            "observer",
            "standard_table_canonical_sha256",
            "instrument_qualification_canonical_sha256",
            "pixel_pitch_review_artifact_sha256",
            "roi_aperture_fit_review_artifact_sha256",
        },
    )
    if condition["geometry"] != "45/0" or condition["illuminant"] != "D65" or condition[
        "observer"
    ] != "2deg":
        raise MeasurementAggregationError("measurement condition must be D65/2deg at 45/0")
    for field in (
        "standard_table_canonical_sha256",
        "instrument_qualification_canonical_sha256",
        "pixel_pitch_review_artifact_sha256",
        "roi_aperture_fit_review_artifact_sha256",
    ):
        _hash(condition[field], label=f"condition.{field}", nullable=True)
    return context


def measurement_context_blockers(context: Mapping[str, Any]) -> list[str]:
    root = _validate_context(context)
    blockers: list[str] = []
    panel = root["panel"]
    if panel["model"] != "MF-17506-M009F-T":
        blockers.append("physical_panel_model_not_mf17506_m009f_t")
    for field, value in panel.items():
        if value.upper().startswith(("UNBOUND", "UNKNOWN", "TBD", "MISSING", "PLACEHOLDER")):
            blockers.append(f"panel.{field}_not_bound")
    firmware = root["firmware"]
    for field in ("build_tag", "driver_api"):
        if firmware[field].upper().startswith(
            ("UNBOUND", "UNKNOWN", "TBD", "MISSING", "PLACEHOLDER")
        ):
            blockers.append(f"firmware.{field}_not_bound")
    for field, value in root["waveform"].items():
        if value is None:
            blockers.append(f"waveform.{field}_missing")
    for field, value in root["environment"].items():
        if value is None:
            blockers.append(f"environment.{field}_missing")
    for field, value in root["condition"].items():
        if field in {"geometry", "illuminant", "observer"}:
            continue
        if value is None:
            blockers.append(f"condition.{field}_missing")
    return list(dict.fromkeys(blockers))


def _validate_roi(value: Any, *, controller: str, label: str) -> Mapping[str, Any]:
    roi = _mapping(
        value,
        label=label,
        keys={"x0", "y0", "x1", "y1", "width", "height", "guard_pixels"},
    )
    for field in ("x0", "y0", "x1", "y1", "width", "height", "guard_pixels"):
        if type(roi[field]) is not int:
            raise MeasurementAggregationError(f"{label}.{field} must be integer")
    if not (0 <= roi["x0"] < roi["x1"] <= 1024 and 0 <= roi["y0"] < roi["y1"] <= 600):
        raise MeasurementAggregationError(f"{label} is outside the panel")
    if roi["width"] != roi["x1"] - roi["x0"] or roi["height"] != roi["y1"] - roi["y0"]:
        raise MeasurementAggregationError(f"{label} dimensions are inconsistent")
    if roi["guard_pixels"] < 0:
        raise MeasurementAggregationError(f"{label} guard must be nonnegative")
    if (controller == "CS1" and roi["x1"] > 512) or (controller == "CS2" and roi["x0"] < 512):
        raise MeasurementAggregationError(f"{label} crosses the controller seam")
    return roi


def _validate_palette_design(value: Any) -> tuple[Mapping[str, Any], list[str]]:
    design = _mapping(
        value,
        label="formal palette design",
        keys={
            "fixture_orientations",
            "pilot_sequence",
            "pilot_excluded_from_formal_n",
            "formal_runs_per_orientation",
            "formal_run_sequence",
            "readings_per_run",
            "measurement_code_order",
            "controller_assignment_by_orientation",
            "acquisition_window_after_pof_busy_high_seconds",
            "aggregation",
        },
    )
    expected_sequence = [
        "vertical-pilot",
        "horizontal-pilot",
        "vertical-formal-01",
        "horizontal-formal-01",
        "vertical-formal-02",
        "horizontal-formal-02",
        "vertical-formal-03",
        "horizontal-formal-03",
    ]
    if (
        design["fixture_orientations"] != ["vertical", "horizontal"]
        or design["pilot_sequence"] != expected_sequence[:2]
        or design["pilot_excluded_from_formal_n"] is not True
        or design["formal_runs_per_orientation"] != 3
        or design["formal_run_sequence"] != expected_sequence[2:]
        or design["readings_per_run"] != 6
        or design["measurement_code_order"] != [1, 0, 3, 2, 5, 6]
    ):
        raise MeasurementAggregationError("formal palette run/order contract changed")
    expected_assignment = {
        "vertical": {
            "1": "CS1",
            "0": "CS1",
            "3": "CS1",
            "2": "CS2",
            "5": "CS2",
            "6": "CS2",
        },
        "horizontal": {
            "1": "CS2",
            "0": "CS2",
            "3": "CS2",
            "2": "CS1",
            "5": "CS1",
            "6": "CS1",
        },
    }
    if design["controller_assignment_by_orientation"] != expected_assignment:
        raise MeasurementAggregationError(
            "formal palette controller assignment differs from frozen fixture ROIs"
        )
    window = _mapping(
        design["acquisition_window_after_pof_busy_high_seconds"],
        label="formal palette acquisition window",
        keys={"minimum", "maximum", "anchor"},
    )
    if window != {
        "minimum": 55.0,
        "maximum": 65.0,
        "anchor": "POF_BUSY_N_low_to_high",
    }:
        raise MeasurementAggregationError("formal palette acquisition window must be 60+/-5 s")
    aggregation = _mapping(
        design["aggregation"],
        label="formal palette aggregation contract",
        keys={
            "orientation_weights",
            "controller_weights_by_code",
            "run_level_method",
            "between_run_method",
            "missing_value_rule",
            "outlier_rule",
            "u95_method",
            "orientation_bias_max_delta_e00",
            "u95_max_delta_e00",
            "acceptance_span_delta_e00",
            "gage_rr_max_percent_of_acceptance_span",
            "acceptance_review_artifact_sha256",
            "acquisition_feasibility_review_artifact_sha256",
        },
    )
    if aggregation["orientation_weights"] != {"vertical": 0.5, "horizontal": 0.5}:
        raise MeasurementAggregationError("formal palette orientation weights changed")
    controller_weights = aggregation["controller_weights_by_code"]
    expected_controller_weights = {
        str(code): {"CS1": 0.5, "CS2": 0.5} for code in COLOR_ORDER
    }
    if controller_weights != expected_controller_weights:
        raise MeasurementAggregationError("formal palette controller weights changed")
    if aggregation["run_level_method"] != (
        "arithmetic mean of three preregistered runs within each orientation/code"
    ) or aggregation["between_run_method"] != (
        "equal-weight mean of vertical and horizontal orientation means"
    ):
        raise MeasurementAggregationError("formal palette hierarchical aggregation changed")
    if aggregation["missing_value_rule"] != "reject-entire-palette-no-imputation" or aggregation[
        "outlier_rule"
    ] != "report-all-preregistered-observations-never-delete":
        raise MeasurementAggregationError("formal palette missing/outlier rule changed")
    if aggregation["u95_method"] != (
        "k=2*sqrt((instrument_expanded_uncertainty_delta_e00/2)^2+"
        "sample_sd_delta_e00_about_final_mean^2)"
    ):
        raise MeasurementAggregationError("formal palette U95 method changed")
    for field in (
        "orientation_bias_max_delta_e00",
        "u95_max_delta_e00",
        "acceptance_span_delta_e00",
    ):
        _number(
            aggregation[field],
            label=f"formal palette aggregation.{field}",
            minimum=0.000001,
            nullable=True,
        )
    if aggregation["gage_rr_max_percent_of_acceptance_span"] != 10.0:
        raise MeasurementAggregationError("formal palette Gage R&R threshold changed")
    for field in (
        "acceptance_review_artifact_sha256",
        "acquisition_feasibility_review_artifact_sha256",
    ):
        _hash(
            aggregation[field],
            label=f"formal palette aggregation.{field}",
            nullable=True,
        )
    blockers = [
        f"formal_palette.{field}_missing"
        for field in (
            "orientation_bias_max_delta_e00",
            "u95_max_delta_e00",
            "acceptance_span_delta_e00",
            "acceptance_review_artifact_sha256",
            "acquisition_feasibility_review_artifact_sha256",
        )
        if aggregation[field] is None
    ]
    return design, blockers


def _validate_transition_design(
    value: Any, *, formal: bool
) -> tuple[Mapping[str, Any], list[str]]:
    design = _mapping(
        value,
        label="transition design",
        keys={
            "evidence_level",
            "pilot_required",
            "pilot_repeats_per_pair",
            "pilot_excluded_from_formal_n",
            "formal_repeats",
            "rotation_algorithm",
            "recovery_actions_per_formal_repeat",
            "recovery_sequence",
            "recovery_profile_canonical_sha256",
            "recovery_profile_review_artifact_sha256",
        },
    )
    expected_level = "formal-profile" if formal else "descriptive-pilot-only"
    expected_repeats = 5 if formal else 1
    if (
        design["evidence_level"] != expected_level
        or design["pilot_required"] is not True
        or design["pilot_repeats_per_pair"] not in {2, 3}
        or design["pilot_excluded_from_formal_n"] is not True
        or design["formal_repeats"] != expected_repeats
        or design["rotation_algorithm"]
        != "opposed-cyclic-old-and-target-orders-repetition-offset-v1"
    ):
        raise MeasurementAggregationError("transition repeat/rotation contract changed")
    blockers: list[str] = []
    if formal:
        if design["recovery_actions_per_formal_repeat"] != 4 or design[
            "recovery_sequence"
        ] != ["solid-black", "solid-white", "solid-black", "solid-white"]:
            raise MeasurementAggregationError("formal transition recovery template changed")
        for field in (
            "recovery_profile_canonical_sha256",
            "recovery_profile_review_artifact_sha256",
        ):
            _hash(design[field], label=f"transition design.{field}", nullable=True)
            if design[field] is None:
                blockers.append(f"formal_transition.{field}_missing")
    elif (
        design["recovery_actions_per_formal_repeat"] != 0
        or design["recovery_sequence"] != []
        or design["recovery_profile_canonical_sha256"] is not None
        or design["recovery_profile_review_artifact_sha256"] is not None
    ):
        raise MeasurementAggregationError("descriptive transition plan must not claim recovery")
    return design, blockers


def seal_measurement_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise MeasurementAggregationError("measurement plan payload must omit integrity")
    unsigned = _snapshot(payload)
    plan = {**unsigned, "integrity": _integrity(unsigned)}
    validate_measurement_plan(plan)
    return plan


def validate_measurement_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        plan,
        label="measurement plan",
        keys={
            "schema_version",
            "kind",
            "plan_id",
            "context",
            "design",
            "required_samples_per_cell",
            "expected_slots",
            "readiness",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] not in {
        PALETTE_PLAN_KIND,
        TRANSITION_PLAN_KIND,
        TRANSITION_FORMAL_PLAN_KIND,
    }:
        raise MeasurementAggregationError("measurement plan schema or kind is invalid")
    _text(root["plan_id"], label="measurement plan_id")
    context = _validate_context(root["context"])
    if root["kind"] == PALETTE_PLAN_KIND:
        _, design_blockers = _validate_palette_design(root["design"])
        expected_per_cell = 6
    else:
        formal_transition = root["kind"] == TRANSITION_FORMAL_PLAN_KIND
        _, design_blockers = _validate_transition_design(
            root["design"], formal=formal_transition
        )
        expected_per_cell = 10 if formal_transition else 2
    if type(root["required_samples_per_cell"]) is not int or root[
        "required_samples_per_cell"
    ] != expected_per_cell:
        raise MeasurementAggregationError(
            f"N5 {root['kind']} requires {expected_per_cell} raw samples per cell"
        )
    slots = root["expected_slots"]
    expected_count = {
        PALETTE_PLAN_KIND: 36,
        TRANSITION_PLAN_KIND: 72,
        TRANSITION_FORMAL_PLAN_KIND: 360,
    }[root["kind"]]
    if not isinstance(slots, list) or len(slots) != expected_count:
        raise MeasurementAggregationError(
            f"measurement plan must contain exactly {expected_count} slots"
        )
    seen_ids: set[str] = set()
    keys = {
        "slot_id",
        "controller",
        "roi",
        "primer_action_identity_sha256",
        "target_action_identity_sha256",
    }
    if root["kind"] == PALETTE_PLAN_KIND:
        keys.update(
            {
                "code",
                "orientation",
                "formal_run",
                "measurement_order",
                "orientation_weight",
                "controller_weight",
            }
        )
    else:
        keys.update({"old_code", "new_code"})
        if root["kind"] == TRANSITION_FORMAL_PLAN_KIND:
            keys.add("formal_repeat")
    for index, value in enumerate(slots):
        slot = _mapping(value, label=f"measurement slot {index}", keys=keys)
        slot_id = _text(slot["slot_id"], label=f"slot {index} id")
        if slot_id in seen_ids:
            raise MeasurementAggregationError("measurement plan slot_id is duplicated")
        seen_ids.add(str(slot_id))
        controller = slot["controller"]
        if controller not in {"CS1", "CS2"}:
            raise MeasurementAggregationError("measurement plan controller is invalid")
        _validate_roi(slot["roi"], controller=controller, label=f"slot {index} ROI")
        _hash(slot["primer_action_identity_sha256"], label=f"slot {index} primer action")
        _hash(slot["target_action_identity_sha256"], label=f"slot {index} target action")
        code_fields = ("code",) if root["kind"] == PALETTE_PLAN_KIND else ("old_code", "new_code")
        for field in code_fields:
            if type(slot[field]) is not int or slot[field] not in COLOR_ORDER:
                raise MeasurementAggregationError(f"slot {index} {field} is not a physical code")
    if root["kind"] == PALETTE_PLAN_KIND:
        for index, slot in enumerate(slots):
            if slot["orientation"] not in {"vertical", "horizontal"}:
                raise MeasurementAggregationError(f"palette slot {index} orientation is invalid")
            if type(slot["formal_run"]) is not int or not 1 <= slot["formal_run"] <= 3:
                raise MeasurementAggregationError(f"palette slot {index} formal_run is invalid")
            if type(slot["measurement_order"]) is not int or not 1 <= slot[
                "measurement_order"
            ] <= 6:
                raise MeasurementAggregationError(
                    f"palette slot {index} measurement_order is invalid"
                )
            if slot["orientation_weight"] != 0.5 or slot["controller_weight"] != 0.5:
                raise MeasurementAggregationError(f"palette slot {index} weights changed")
            expected_controller = root["design"][
                "controller_assignment_by_orientation"
            ][slot["orientation"]][str(slot["code"])]
            if slot["controller"] != expected_controller:
                raise MeasurementAggregationError(
                    "palette slot samples the non-colour half of a frozen fixture"
                )
        expected = {
            (code, orientation, formal_run)
            for code in COLOR_ORDER
            for orientation in ("vertical", "horizontal")
            for formal_run in range(1, 4)
        }
        observed = {
            (slot["code"], slot["orientation"], slot["formal_run"])
            for slot in slots
        }
        for code in COLOR_ORDER:
            controllers = [slot["controller"] for slot in slots if slot["code"] == code]
            if controllers.count("CS1") != 3 or controllers.count("CS2") != 3:
                raise MeasurementAggregationError(
                    "formal palette must give every code equal CS1/CS2 weight"
                )
        code_order = root["design"]["measurement_code_order"]
        for orientation in ("vertical", "horizontal"):
            for formal_run in range(1, 4):
                group = sorted(
                    (
                        slot
                        for slot in slots
                        if slot["orientation"] == orientation
                        and slot["formal_run"] == formal_run
                    ),
                    key=lambda slot: slot["measurement_order"],
                )
                if [slot["measurement_order"] for slot in group] != list(range(1, 7)) or [
                    slot["code"] for slot in group
                ] != code_order:
                    raise MeasurementAggregationError(
                        "formal palette measurement order differs from preregistration"
                    )
    else:
        if root["kind"] == TRANSITION_FORMAL_PLAN_KIND:
            for index, slot in enumerate(slots):
                if type(slot["formal_repeat"]) is not int or not 1 <= slot[
                    "formal_repeat"
                ] <= 5:
                    raise MeasurementAggregationError(
                        f"transition slot {index} formal_repeat is invalid"
                    )
            expected = {
                (old, new, controller, repeat)
                for old in COLOR_ORDER
                for new in COLOR_ORDER
                for controller in ("CS1", "CS2")
                for repeat in range(1, 6)
            }
            observed = {
                (
                    slot["old_code"],
                    slot["new_code"],
                    slot["controller"],
                    slot["formal_repeat"],
                )
                for slot in slots
            }
        else:
            expected = {
                (old, new, controller)
                for old in COLOR_ORDER
                for new in COLOR_ORDER
                for controller in ("CS1", "CS2")
            }
            observed = {
                (slot["old_code"], slot["new_code"], slot["controller"])
                for slot in slots
            }
    if observed != expected:
        raise MeasurementAggregationError("measurement plan does not cover each required mirrored cell")
    readiness = _mapping(
        root["readiness"],
        label="measurement plan readiness",
        keys={"measurement_ready", "blockers"},
    )
    blockers = [*measurement_context_blockers(context), *design_blockers]
    if root["kind"] == TRANSITION_PLAN_KIND:
        blockers.append("descriptive_transition_atlas_cannot_emit_measured_profile")
    if readiness != {"measurement_ready": not blockers, "blockers": blockers}:
        raise MeasurementAggregationError("measurement plan readiness is inconsistent")
    _validate_integrity(root, label="measurement plan")
    return root


def _validate_common_observation(
    observation: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    expected_kind: str,
) -> Mapping[str, Any]:
    if observation["schema_version"] != SCHEMA_VERSION or observation["kind"] != expected_kind:
        raise MeasurementAggregationError("observation schema or kind is invalid")
    if observation["plan_canonical_sha256"] != plan["integrity"]["canonical_sha256"]:
        raise MeasurementAggregationError("observation belongs to another measurement plan")
    _hash(
        observation["execution_contract_canonical_sha256"],
        label="observation execution contract canonical SHA-256",
    )
    _hash(
        observation["finalized_bundle_canonical_sha256"],
        label="observation finalized bundle canonical SHA-256",
    )
    slots = [slot for slot in plan["expected_slots"] if slot["slot_id"] == observation["slot_id"]]
    if len(slots) != 1:
        raise MeasurementAggregationError("observation slot is not unique in plan")
    slot = slots[0]
    if observation["context"] != plan["context"]:
        raise MeasurementAggregationError("observation panel/build/waveform/environment context changed")
    captured = _timestamp(observation["captured_at"], label="observation captured_at")
    assert captured is not None
    for field in (
        "source_run_sha256",
        "asset_manifest_sha256",
        "primer_result_file_sha256",
        "target_result_file_sha256",
    ):
        _hash(observation[field], label=f"observation {field}")
    if (
        observation["primer_action_identity_sha256"]
        != slot["primer_action_identity_sha256"]
        or observation["target_action_identity_sha256"]
        != slot["target_action_identity_sha256"]
    ):
        raise MeasurementAggregationError("observation replays another action/prior route")
    return slot


def _validate_execution_bundle_for_plan(
    *,
    plan: Mapping[str, Any],
    execution_contract: Optional[Mapping[str, Any]],
    finalized_bundle: Optional[Mapping[str, Any]],
    require_strict_rc2g: bool = False,
) -> Mapping[str, Any]:
    """Validate offline structure or the explicit production strict boundary."""

    if execution_contract is None or finalized_bundle is None:
        raise MeasurementAggregationError(
            "formal observations require an N5 execution contract and finalized bundle"
        )
    # Lazy import keeps the measurement-plan compiler independent from the
    # execution layer while making aggregation use its full evidence validator.
    from .execution import N5ExecutionError, validate_execution_contract, validate_finalized_bundle

    try:
        contract = validate_execution_contract(execution_contract)
    except N5ExecutionError as error:
        raise MeasurementAggregationError(
            f"N5 finalized execution bundle is invalid: {error}"
        ) from error
    if require_strict_rc2g:
        from .n5_rc2g_protocol import (
            N5Rc2gProtocolError,
            validate_strict_finalized_bundle,
        )

        try:
            summary = validate_strict_finalized_bundle(contract, finalized_bundle)
        except (N5ExecutionError, N5Rc2gProtocolError) as error:
            raise MeasurementAggregationError(
                f"N5 finalized execution bundle is invalid: {error}"
            ) from error
    else:
        # Explicit structural/offline research path.  Production callers use
        # the named wrappers below and cannot reach this weaker gate.
        try:
            summary = validate_finalized_bundle(contract, finalized_bundle)
        except N5ExecutionError as error:
            raise MeasurementAggregationError(
                f"N5 finalized execution bundle is invalid: {error}"
            ) from error
    if summary["state"] != "normal":
        raise MeasurementAggregationError(
            "abnormally terminated N5 execution is ineligible for formal aggregation"
        )
    plan_class = (
        "formal_palette"
        if plan["kind"] == PALETTE_PLAN_KIND
        else (
            "formal_transition"
            if plan["kind"] == TRANSITION_FORMAL_PLAN_KIND
            else "descriptive"
        )
    )
    binding = contract["plan_bindings"][plan_class]
    if (
        binding["materialized"] is not True
        or binding["measurement_plan_canonical_sha256"]
        != plan["integrity"]["canonical_sha256"]
        or (
            require_strict_rc2g
            and binding.get("measurement_eligible_for_formal_aggregation") is not True
        )
    ):
        raise MeasurementAggregationError(
            "measurement plan is not the one frozen by the execution contract"
        )
    if require_strict_rc2g:
        strict_actions = summary.get("strict_actions_by_sha")
        core_actions = summary.get("actions_by_sha")
        if (
            summary.get("strict_rc2g_verified") is not True
            or not isinstance(strict_actions, Mapping)
            or not isinstance(core_actions, Mapping)
            or set(strict_actions) != set(core_actions)
            or any(
                not isinstance(item, Mapping)
                or item.get("strict_rc2g_verified") is not True
                or item.get("state") != "PASS"
                for item in strict_actions.values()
            )
        ):
            raise MeasurementAggregationError(
                "production formal aggregation requires strict RC2G replay of every action"
            )
    return summary


def _bind_common_execution_evidence(
    observation: Mapping[str, Any],
    *,
    execution_contract: Mapping[str, Any],
    bundle_summary: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if (
        observation["execution_contract_canonical_sha256"]
        != execution_contract["integrity"]["canonical_sha256"]
        or observation["finalized_bundle_canonical_sha256"]
        != bundle_summary["bundle_canonical_sha256"]
    ):
        raise MeasurementAggregationError(
            "observation execution-contract/finalized-bundle identity changed"
        )
    actions = bundle_summary["actions_by_sha"]
    primer = actions.get(observation["primer_action_identity_sha256"])
    target = actions.get(observation["target_action_identity_sha256"])
    if (
        not isinstance(primer, Mapping)
        or not isinstance(target, Mapping)
        or primer["state"] != "PASS"
        or target["state"] != "PASS"
        or primer["result_file_sha256"]
        != observation["primer_result_file_sha256"]
        or target["result_file_sha256"]
        != observation["target_result_file_sha256"]
        or target["authorization_id"] != observation["authorization_id"]
    ):
        raise MeasurementAggregationError(
            "observation result/authorization is not bound to finalized PASS actions"
        )
    return primer, target


def seal_palette_observation(
    payload: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise MeasurementAggregationError("palette observation payload must omit integrity")
    unsigned = _snapshot(payload)
    record = {**unsigned, "integrity": _integrity(unsigned)}
    validate_palette_observation(
        record,
        plan=plan,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
    )
    return record


def validate_palette_observation(
    observation: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
) -> Mapping[str, Any]:
    root = _mapping(
        observation,
        label="palette observation",
        keys={
            "schema_version",
            "kind",
            "plan_canonical_sha256",
            "execution_contract_canonical_sha256",
            "finalized_bundle_canonical_sha256",
            "slot_id",
            "context",
            "captured_at",
            "seconds_after_pof_busy_high",
            "source_run_sha256",
            "asset_manifest_sha256",
            "authorization_id",
            "primer_action_identity_sha256",
            "target_action_identity_sha256",
            "primer_result_file_sha256",
            "target_result_file_sha256",
            "reflectance_record",
            "spectral_report",
            "spectral_report_file_sha256",
            "integrity",
        },
    )
    plan_root = validate_measurement_plan(plan)
    if plan_root["kind"] != PALETTE_PLAN_KIND:
        raise MeasurementAggregationError("palette observation requires a palette plan")
    slot = _validate_common_observation(
        root, plan=plan_root, expected_kind=PALETTE_OBSERVATION_KIND
    )
    window = plan_root["design"]["acquisition_window_after_pof_busy_high_seconds"]
    _number(
        root["seconds_after_pof_busy_high"],
        label="palette seconds_after_pof_busy_high",
        minimum=window["minimum"],
        maximum=window["maximum"],
    )
    _text(root["authorization_id"], label="palette authorization_id")
    table = validate_authoritative_standard_table(standard_table)
    qualification = validate_instrument_qualification(instrument_qualification)
    blockers = instrument_qualification_blockers(
        qualification,
        captured_at=root["captured_at"],
        standard_table=table,
    )
    if blockers:
        raise MeasurementAggregationError(
            f"palette observation instrument is not qualified: {blockers}"
        )
    condition = plan_root["context"]["condition"]
    if (
        condition["standard_table_canonical_sha256"]
        != table["integrity"]["canonical_sha256"]
        or condition["instrument_qualification_canonical_sha256"]
        != qualification["integrity"]["canonical_sha256"]
    ):
        raise MeasurementAggregationError("palette plan table/instrument identity mismatch")
    reflectance = validate_reflectance_record(root["reflectance_record"])
    if (
        reflectance["instrument_qualification_sha256"]
        != qualification["integrity"]["canonical_sha256"]
    ):
        raise MeasurementAggregationError("reflectance record uses another instrument qualification")
    try:
        validate_spectral_report(
            root["spectral_report"],
            standard_table=table,
            reflectance_record=reflectance,
        )
    except SpectralContractError as error:
        raise MeasurementAggregationError(f"palette spectral report is invalid: {error}") from error
    if root["spectral_report_file_sha256"] != spectral_report_file_sha256(
        root["spectral_report"]
    ):
        raise MeasurementAggregationError("palette spectral report whole-file SHA is invalid")
    if slot["code"] not in COLOR_ORDER:
        raise MeasurementAggregationError("palette slot code is invalid")
    _validate_integrity(root, label="palette observation")
    return root


def seal_transition_observation(
    payload: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise MeasurementAggregationError("transition observation payload must omit integrity")
    unsigned = _snapshot(payload)
    record = {**unsigned, "integrity": _integrity(unsigned)}
    validate_transition_observation(
        record,
        plan=plan,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
    )
    return record


def validate_transition_observation(
    observation: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
) -> Mapping[str, Any]:
    root = _mapping(
        observation,
        label="transition observation",
        keys={
            "schema_version",
            "kind",
            "plan_canonical_sha256",
            "execution_contract_canonical_sha256",
            "finalized_bundle_canonical_sha256",
            "slot_id",
            "context",
            "captured_at",
            "source_run_sha256",
            "asset_manifest_sha256",
            "authorization_id",
            "primer_action_identity_sha256",
            "target_action_identity_sha256",
            "primer_result_file_sha256",
            "target_result_file_sha256",
            "initial_reflectance_record",
            "initial_spectral_report",
            "initial_spectral_report_file_sha256",
            "final_reflectance_record",
            "final_spectral_report",
            "final_spectral_report_file_sha256",
            "metrics",
            "integrity",
        },
    )
    plan_root = validate_measurement_plan(plan)
    if plan_root["kind"] not in {TRANSITION_PLAN_KIND, TRANSITION_FORMAL_PLAN_KIND}:
        raise MeasurementAggregationError("transition observation requires a transition plan")
    _validate_common_observation(
        root, plan=plan_root, expected_kind=TRANSITION_OBSERVATION_KIND
    )
    _text(root["authorization_id"], label="transition authorization_id")
    table = validate_authoritative_standard_table(standard_table)
    qualification = validate_instrument_qualification(instrument_qualification)
    blockers = instrument_qualification_blockers(
        qualification,
        captured_at=root["captured_at"],
        standard_table=table,
    )
    if blockers:
        raise MeasurementAggregationError(
            f"transition observation instrument is not qualified: {blockers}"
        )
    condition = plan_root["context"]["condition"]
    if (
        condition["standard_table_canonical_sha256"]
        != table["integrity"]["canonical_sha256"]
        or condition["instrument_qualification_canonical_sha256"]
        != qualification["integrity"]["canonical_sha256"]
    ):
        raise MeasurementAggregationError("transition plan table/instrument identity mismatch")
    for phase in ("initial", "final"):
        reflectance = validate_reflectance_record(root[f"{phase}_reflectance_record"])
        if (
            reflectance["instrument_qualification_sha256"]
            != qualification["integrity"]["canonical_sha256"]
        ):
            raise MeasurementAggregationError(
                f"transition {phase} reflectance uses another instrument"
            )
        try:
            validate_spectral_report(
                root[f"{phase}_spectral_report"],
                standard_table=table,
                reflectance_record=reflectance,
            )
        except SpectralContractError as error:
            raise MeasurementAggregationError(
                f"transition {phase} spectral report is invalid: {error}"
            ) from error
        if root[f"{phase}_spectral_report_file_sha256"] != spectral_report_file_sha256(
            root[f"{phase}_spectral_report"]
        ):
            raise MeasurementAggregationError(
                f"transition {phase} spectral report whole-file SHA is invalid"
            )
    metrics = _mapping(
        root["metrics"],
        label="transition metrics",
        keys={
            "uniformity_delta_e00",
            "ghosting_metric",
            "busy_ms",
            "peak_current_a",
            "energy_j",
            "temperature_rise_c",
            "recovery_pass",
        },
    )
    for field in (
        "uniformity_delta_e00",
        "ghosting_metric",
        "busy_ms",
        "peak_current_a",
        "energy_j",
    ):
        _number(metrics[field], label=f"transition metrics.{field}", minimum=0)
    _number(
        metrics["temperature_rise_c"],
        label="transition metrics.temperature_rise_c",
        minimum=-200,
        maximum=200,
    )
    if type(metrics["recovery_pass"]) is not bool:
        raise MeasurementAggregationError("transition metrics.recovery_pass must be boolean")
    _validate_integrity(root, label="transition observation")
    return root


def _validate_palette_execution_binding(
    observation: Mapping[str, Any],
    *,
    execution_contract: Mapping[str, Any],
    bundle_summary: Mapping[str, Any],
) -> None:
    from .execution import N5ExecutionError, measurement_binding_for_slot

    _primer, target = _bind_common_execution_evidence(
        observation,
        execution_contract=execution_contract,
        bundle_summary=bundle_summary,
    )
    try:
        binding = measurement_binding_for_slot(
            bundle_summary,
            action_identity_sha256=target["action_identity_sha256"],
            slot_id=observation["slot_id"],
            measurement_phase="palette",
        )
    except N5ExecutionError as error:
        raise MeasurementAggregationError(
            f"palette finalized measurement binding is invalid: {error}"
        ) from error
    reflectance = observation["reflectance_record"]
    if (
        binding["source_run_sha256"] != observation["source_run_sha256"]
        or binding["asset_manifest_sha256"] != observation["asset_manifest_sha256"]
        or binding["measurement_record_sha256"]
        != reflectance["measurement_record_sha256"]
        or binding["raw_spectrum_artifact_sha256"]
        != reflectance["raw_spectrum_artifact_sha256"]
        or binding["spectral_report_file_sha256"]
        != observation["spectral_report_file_sha256"]
        or binding["metrics_sha256"] is not None
    ):
        raise MeasurementAggregationError(
            "palette observation differs from finalized manual measurement evidence"
        )


def _validate_transition_execution_binding(
    observation: Mapping[str, Any],
    *,
    execution_contract: Mapping[str, Any],
    bundle_summary: Mapping[str, Any],
) -> None:
    from .execution import N5ExecutionError, measurement_binding_for_slot

    primer, target = _bind_common_execution_evidence(
        observation,
        execution_contract=execution_contract,
        bundle_summary=bundle_summary,
    )
    try:
        initial = measurement_binding_for_slot(
            bundle_summary,
            action_identity_sha256=primer["action_identity_sha256"],
            slot_id=observation["slot_id"],
            measurement_phase="transition_initial",
        )
        final = measurement_binding_for_slot(
            bundle_summary,
            action_identity_sha256=target["action_identity_sha256"],
            slot_id=observation["slot_id"],
            measurement_phase="transition_final",
        )
    except N5ExecutionError as error:
        raise MeasurementAggregationError(
            f"transition finalized measurement binding is invalid: {error}"
        ) from error
    initial_reflectance = observation["initial_reflectance_record"]
    final_reflectance = observation["final_reflectance_record"]
    common = (
        initial["source_run_sha256"] == observation["source_run_sha256"]
        and final["source_run_sha256"] == observation["source_run_sha256"]
        and initial["asset_manifest_sha256"] == observation["asset_manifest_sha256"]
        and final["asset_manifest_sha256"] == observation["asset_manifest_sha256"]
    )
    if (
        not common
        or initial["measurement_record_sha256"]
        != initial_reflectance["measurement_record_sha256"]
        or initial["raw_spectrum_artifact_sha256"]
        != initial_reflectance["raw_spectrum_artifact_sha256"]
        or initial["spectral_report_file_sha256"]
        != observation["initial_spectral_report_file_sha256"]
        or initial["metrics_sha256"] is not None
        or final["measurement_record_sha256"]
        != final_reflectance["measurement_record_sha256"]
        or final["raw_spectrum_artifact_sha256"]
        != final_reflectance["raw_spectrum_artifact_sha256"]
        or final["spectral_report_file_sha256"]
        != observation["final_spectral_report_file_sha256"]
        or final["metrics_sha256"] != _sha256(observation["metrics"])
    ):
        raise MeasurementAggregationError(
            "transition observation differs from finalized manual measurement evidence"
        )


def summarize_numeric(values: Sequence[int | float]) -> dict[str, Any]:
    numbers = [float(_number(value, label=f"summary[{index}]")) for index, value in enumerate(values)]
    if not numbers:
        return {
            "n": 0,
            "minimum": None,
            "maximum_observed": None,
            "mean": None,
            "sample_standard_deviation": None,
            "standard_uncertainty_of_mean": None,
            "coverage_factor": None,
            "u95": None,
            "p95": None,
            "p99": None,
            "extreme_reporting": "no-observations",
        }
    count = len(numbers)
    mean = math.fsum(numbers) / count
    sd = None
    if count >= 2:
        sd = math.sqrt(math.fsum((value - mean) ** 2 for value in numbers) / (count - 1))
    standard_uncertainty = None if sd is None else sd / math.sqrt(count)
    coverage_factor = None if sd is None else 2.0
    u95 = None if sd is None else coverage_factor * standard_uncertainty
    ordered = sorted(numbers)
    if count < 10:
        p95 = None
        p99 = None
        extreme = "maximum-observed-only-n-less-than-10"
    else:
        p95 = ordered[math.ceil(0.95 * count) - 1]
        p99 = ordered[math.ceil(0.99 * count) - 1]
        extreme = "maximum-observed-and-nearest-rank-percentiles"
    return {
        "n": count,
        "minimum": ordered[0],
        "maximum_observed": ordered[-1],
        "mean": mean,
        "sample_standard_deviation": sd,
        "standard_uncertainty_of_mean": standard_uncertainty,
        "coverage_factor": coverage_factor,
        "u95": u95,
        "p95": p95,
        "p99": p99,
        "extreme_reporting": extreme,
    }


def _paired_controller_diagnostic(values: Sequence[int | float]) -> dict[str, Any]:
    summary = summarize_numeric(values)
    summary.update(
        {
            "p95": None,
            "p99": None,
            "extreme_reporting": "paired-controller-descriptive-no-population-percentiles",
        }
    )
    return summary


def _aggregate_classification(*, measured: bool) -> dict[str, bool]:
    return {
        "measured": measured,
        "calibrated": measured,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def _lab_tuple(report: Mapping[str, Any]) -> tuple[float, float, float]:
    lab = report["lab"]
    return float(lab["l"]), float(lab["a"]), float(lab["b"])


def _latest_timestamp(records: Sequence[Mapping[str, Any]]) -> str:
    latest = max(
        _timestamp(record["captured_at"], label="observation captured_at")
        for record in records
    )
    assert latest is not None
    return latest.isoformat().replace("+00:00", "Z")


def _require_unique_evidence(
    identities: Sequence[str], *, label: str
) -> None:
    if len(identities) != len(set(identities)):
        raise MeasurementAggregationError(f"{label} evidence is replayed across slots")


def _require_constant_group_evidence(
    records: Sequence[Mapping[str, Any]], *, fields: Sequence[str], label: str
) -> None:
    for field in fields:
        if len({record[field] for record in records}) > 1:
            raise MeasurementAggregationError(
                f"{label} must share one {field} identity across its preregistered ROIs"
            )


def aggregate_measured_palette(
    plan: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Optional[Mapping[str, Any]],
    instrument_qualification: Optional[Mapping[str, Any]],
    execution_contract: Optional[Mapping[str, Any]] = None,
    finalized_bundle: Optional[Mapping[str, Any]] = None,
    _require_strict_rc2g: bool = False,
) -> dict[str, Any]:
    """Offline/structural palette aggregation; use the production wrapper live."""

    plan_root = validate_measurement_plan(plan)
    if plan_root["kind"] != PALETTE_PLAN_KIND:
        raise MeasurementAggregationError("palette aggregator requires a palette plan")
    blockers = list(plan_root["readiness"]["blockers"])
    if standard_table is None:
        blockers.append("authoritative_standard_table_missing")
        table = None
    else:
        table = validate_authoritative_standard_table(standard_table)
    if instrument_qualification is None:
        blockers.append("instrument_qualification_missing")
        qualification = None
    else:
        qualification = validate_instrument_qualification(instrument_qualification)
        blockers.extend(
            instrument_qualification_blockers(qualification, standard_table=table)
        )
    records: list[Mapping[str, Any]] = []
    if observations and (table is None or qualification is None):
        raise MeasurementAggregationError(
            "palette observations cannot be accepted without table and instrument qualification"
        )
    bundle_summary = None
    if observations:
        bundle_summary = _validate_execution_bundle_for_plan(
            plan=plan_root,
            execution_contract=execution_contract,
            finalized_bundle=finalized_bundle,
            require_strict_rc2g=_require_strict_rc2g,
        )
    for observation in observations:
        assert table is not None and qualification is not None
        record = validate_palette_observation(
            observation,
            plan=plan_root,
            standard_table=table,
            instrument_qualification=qualification,
        )
        assert execution_contract is not None and bundle_summary is not None
        _validate_palette_execution_binding(
            record,
            execution_contract=execution_contract,
            bundle_summary=bundle_summary,
        )
        records.append(record)
    slot_ids = [record["slot_id"] for record in records]
    if len(slot_ids) != len(set(slot_ids)):
        raise MeasurementAggregationError("palette observation slot replay is duplicated")
    _require_unique_evidence(
        [record["reflectance_record"]["measurement_id"] for record in records],
        label="palette measurement_id",
    )
    _require_unique_evidence(
        [
            record["reflectance_record"]["measurement_record_sha256"]
            for record in records
        ],
        label="palette measurement-record SHA-256",
    )
    _require_unique_evidence(
        [
            record["reflectance_record"]["raw_spectrum_artifact_sha256"]
            for record in records
        ],
        label="palette raw-spectrum SHA-256",
    )
    expected_ids = [slot["slot_id"] for slot in plan_root["expected_slots"]]
    missing = [slot_id for slot_id in expected_ids if slot_id not in slot_ids]
    if missing:
        blockers.append("palette_required_samples_incomplete")
    extra = sorted(set(slot_ids) - set(expected_ids))
    if extra:
        raise MeasurementAggregationError("palette observations contain unexpected slots")
    slot_by_id = {slot["slot_id"]: slot for slot in plan_root["expected_slots"]}
    palette_run_groups = []
    for orientation in ("vertical", "horizontal"):
        for formal_run in range(1, 4):
            run_group = [
                record
                for record in records
                if slot_by_id[record["slot_id"]]["orientation"] == orientation
                and slot_by_id[record["slot_id"]]["formal_run"] == formal_run
            ]
            if run_group:
                _require_constant_group_evidence(
                    run_group,
                    fields=(
                        "source_run_sha256",
                        "asset_manifest_sha256",
                        "authorization_id",
                        "primer_result_file_sha256",
                        "target_result_file_sha256",
                    ),
                    label=f"palette {orientation} formal run {formal_run}",
                )
                palette_run_groups.append(run_group)
    for field in ("source_run_sha256", "authorization_id", "target_result_file_sha256"):
        _require_unique_evidence(
            [group[0][field] for group in palette_run_groups],
            label=f"palette formal-run {field}",
        )
    summaries: dict[str, Any] = {}
    palette_mapping: Optional[dict[str, Any]] = None
    final_labs: dict[int, list[float]] = {}
    if records:
        for orientation in ("vertical", "horizontal"):
            for formal_run in range(1, 4):
                run_group = sorted(
                    (
                        record
                        for record in records
                        if slot_by_id[record["slot_id"]]["orientation"] == orientation
                        and slot_by_id[record["slot_id"]]["formal_run"] == formal_run
                    ),
                    key=lambda record: slot_by_id[record["slot_id"]]["measurement_order"],
                )
                times = [record["seconds_after_pof_busy_high"] for record in run_group]
                if any(right <= left for left, right in zip(times, times[1:])):
                    raise MeasurementAggregationError(
                        "palette acquisition timestamps violate preregistered serial order"
                    )
    if records:
        for code in COLOR_ORDER:
            group = [record for record in records if slot_by_id[record["slot_id"]]["code"] == code]
            for component in ("l", "a", "b"):
                summaries[f"code-{code}.{component}"] = summarize_numeric(
                    [record["spectral_report"]["lab"][component] for record in group]
                )
            if len(group) == 6:
                orientation_means = {
                    orientation: [
                        math.fsum(
                            record["spectral_report"]["lab"][component]
                            for record in group
                            if slot_by_id[record["slot_id"]]["orientation"] == orientation
                        )
                        / 3
                        for component in ("l", "a", "b")
                    ]
                    for orientation in ("vertical", "horizontal")
                }
                final_lab = [
                    0.5
                    * (
                        orientation_means["vertical"][component]
                        + orientation_means["horizontal"][component]
                    )
                    for component in range(3)
                ]
                final_labs[code] = final_lab
                orientation_bias = delta_e_ciede2000(
                    orientation_means["vertical"], orientation_means["horizontal"]
                )
                residual_delta_e = [
                    delta_e_ciede2000(_lab_tuple(record["spectral_report"]), final_lab)
                    for record in group
                ]
                residual_summary = summarize_numeric(residual_delta_e)
                residual_sd = residual_summary["sample_standard_deviation"] or 0.0
                if qualification is None:
                    instrument_u95 = None
                    combined_u95 = None
                    gage_rr_percent = None
                else:
                    instrument_u95 = float(
                        qualification["calibration"]["expanded_uncertainty_delta_e00"]
                    )
                    combined_u95 = 2 * math.sqrt((instrument_u95 / 2) ** 2 + residual_sd**2)
                    acceptance_span = plan_root["design"]["aggregation"][
                        "acceptance_span_delta_e00"
                    ]
                    gage_rr_percent = (
                        None
                        if acceptance_span is None
                        else 100 * instrument_u95 / float(acceptance_span)
                    )
                summaries[f"code-{code}.orientation_means"] = orientation_means
                summaries[f"code-{code}.orientation_bias_delta_e00"] = orientation_bias
                summaries[f"code-{code}.residual_delta_e00"] = residual_summary
                summaries[f"code-{code}.combined_u95_delta_e00"] = combined_u95
                summaries[f"code-{code}.gage_rr_percent_of_acceptance_span"] = (
                    gage_rr_percent
                )
                acceptance = plan_root["design"]["aggregation"]
                orientation_limit = acceptance["orientation_bias_max_delta_e00"]
                u95_limit = acceptance["u95_max_delta_e00"]
                if orientation_limit is not None and orientation_bias > orientation_limit:
                    blockers.append(f"palette_orientation_bias_exceeded:code-{code}")
                if u95_limit is not None and combined_u95 is not None and combined_u95 > u95_limit:
                    blockers.append(f"palette_u95_exceeded:code-{code}")
                if (
                    gage_rr_percent is not None
                    and gage_rr_percent
                    > acceptance["gage_rr_max_percent_of_acceptance_span"]
                ):
                    blockers.append(f"palette_gage_rr_exceeded:code-{code}")
    if not blockers and len(records) == len(expected_ids):
        entries = []
        for code in COLOR_ORDER:
            lab = final_labs[code]
            entries.append({"code": code, "name": COLOR_NAME_BY_CODE[code], "lab": lab})
        evidence_set = {
            "plan_canonical_sha256": plan_root["integrity"]["canonical_sha256"],
            "observation_canonical_sha256s": sorted(
                record["integrity"]["canonical_sha256"] for record in records
            ),
        }
        candidate = {
            "schema_version": 2,
            "palette_id": f"n5-measured-{plan_root['plan_id']}",
            "calibrated": True,
            "source": (
                "N5 qualified D65/2deg 45/0 spectral aggregate "
                f"{plan_root['integrity']['canonical_sha256']}"
            ),
            "illuminant": "D65",
            "observer": "2deg",
            "notes": (
                "vertical and horizontal fixtures, three independent formal panel-cold "
                "runs per orientation; pilots excluded; equal orientation/controller weights"
            ),
            "calibration": {
                "measurement_id": plan_root["plan_id"],
                "artifact_sha256": _sha256(evidence_set),
            },
            "entries": entries,
        }
        try:
            palette = palette_from_mapping(candidate)
        except PaletteError as error:
            blockers.append(f"measured_palette_semantic_gate_failed:{error}")
        else:
            palette_mapping = palette.canonical_mapping()
    measured = not blockers and palette_mapping is not None
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PALETTE_AGGREGATE_KIND,
        "plan_kind": plan_root["kind"],
        "plan_canonical_sha256": plan_root["integrity"]["canonical_sha256"],
        "expected_sample_count": len(expected_ids),
        "accepted_sample_count": len(records),
        "missing_slot_ids": missing,
        "blockers": list(dict.fromkeys(blockers)),
        "statistics": summaries,
        "percentile_rule": "n<10 uses maximum_observed plus U95; P95/P99 are null",
        "palette": palette_mapping,
        "classification": _aggregate_classification(measured=measured),
    }
    result = {**unsigned, "integrity": _integrity(unsigned)}
    validate_palette_aggregate(result)
    return result


def _mean_lab(records: Sequence[Mapping[str, Any]], report_field: str) -> dict[str, float]:
    return {
        component: math.fsum(record[report_field]["lab"][component] for record in records)
        / len(records)
        for component in ("l", "a", "b")
    }


def aggregate_transition_profile(
    plan: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Optional[Mapping[str, Any]],
    instrument_qualification: Optional[Mapping[str, Any]],
    execution_contract: Optional[Mapping[str, Any]] = None,
    finalized_bundle: Optional[Mapping[str, Any]] = None,
    _require_strict_rc2g: bool = False,
) -> dict[str, Any]:
    """Offline/structural transition aggregation; use production wrapper live."""

    plan_root = validate_measurement_plan(plan)
    if plan_root["kind"] not in {TRANSITION_PLAN_KIND, TRANSITION_FORMAL_PLAN_KIND}:
        raise MeasurementAggregationError("transition aggregator requires a transition plan")
    blockers = list(plan_root["readiness"]["blockers"])
    table = None if standard_table is None else validate_authoritative_standard_table(standard_table)
    qualification = (
        None
        if instrument_qualification is None
        else validate_instrument_qualification(instrument_qualification)
    )
    if table is None:
        blockers.append("authoritative_standard_table_missing")
    if qualification is None:
        blockers.append("instrument_qualification_missing")
    else:
        blockers.extend(
            instrument_qualification_blockers(qualification, standard_table=table)
        )
    if observations and (table is None or qualification is None):
        raise MeasurementAggregationError(
            "transition observations require table and instrument qualification"
        )
    bundle_summary = None
    if observations:
        bundle_summary = _validate_execution_bundle_for_plan(
            plan=plan_root,
            execution_contract=execution_contract,
            finalized_bundle=finalized_bundle,
            require_strict_rc2g=_require_strict_rc2g,
        )
    records: list[Mapping[str, Any]] = []
    for observation in observations:
        assert table is not None and qualification is not None
        record = validate_transition_observation(
            observation,
            plan=plan_root,
            standard_table=table,
            instrument_qualification=qualification,
        )
        assert execution_contract is not None and bundle_summary is not None
        _validate_transition_execution_binding(
            record,
            execution_contract=execution_contract,
            bundle_summary=bundle_summary,
        )
        records.append(record)
    slot_ids = [record["slot_id"] for record in records]
    if len(slot_ids) != len(set(slot_ids)):
        raise MeasurementAggregationError("transition observation slot replay is duplicated")
    reflectance_records = [
        record[f"{phase}_reflectance_record"]
        for record in records
        for phase in ("initial", "final")
    ]
    _require_unique_evidence(
        [record["measurement_id"] for record in reflectance_records],
        label="transition measurement_id",
    )
    _require_unique_evidence(
        [record["measurement_record_sha256"] for record in reflectance_records],
        label="transition measurement-record SHA-256",
    )
    _require_unique_evidence(
        [record["raw_spectrum_artifact_sha256"] for record in reflectance_records],
        label="transition raw-spectrum SHA-256",
    )
    expected_ids = [slot["slot_id"] for slot in plan_root["expected_slots"]]
    missing = [slot_id for slot_id in expected_ids if slot_id not in slot_ids]
    if missing:
        blockers.append("transition_required_samples_incomplete")
    if set(slot_ids) - set(expected_ids):
        raise MeasurementAggregationError("transition observations contain unexpected slots")
    slot_by_id = {slot["slot_id"]: slot for slot in plan_root["expected_slots"]}
    if plan_root["kind"] == TRANSITION_FORMAL_PLAN_KIND:
        transition_run_groups = [
            [
                record
                for record in records
                if slot_by_id[record["slot_id"]]["formal_repeat"] == repeat
            ]
            for repeat in range(1, 6)
        ]
    else:
        transition_run_groups = [records]
    nonempty_transition_runs = []
    for run_index, run_group in enumerate(transition_run_groups, start=1):
        if not run_group:
            continue
        _require_constant_group_evidence(
            run_group,
            fields=(
                "source_run_sha256",
                "asset_manifest_sha256",
                "authorization_id",
                "primer_result_file_sha256",
                "target_result_file_sha256",
            ),
            label=f"transition run {run_index}",
        )
        nonempty_transition_runs.append(run_group)
    for field in ("source_run_sha256", "authorization_id", "target_result_file_sha256"):
        _require_unique_evidence(
            [group[0][field] for group in nonempty_transition_runs],
            label=f"transition formal-run {field}",
        )
    statistics: dict[str, Any] = {}
    measured_profile: Optional[dict[str, Any]] = None
    if records:
        for old in COLOR_ORDER:
            for new in COLOR_ORDER:
                group = [
                    record
                    for record in records
                    if (
                        slot_by_id[record["slot_id"]]["old_code"],
                        slot_by_id[record["slot_id"]]["new_code"],
                    )
                    == (old, new)
                ]
                raw_delta_values = [
                    delta_e_ciede2000(
                        _lab_tuple(record["initial_spectral_report"]),
                        _lab_tuple(record["final_spectral_report"]),
                    )
                    for record in group
                ]
                metric_fields = (
                    "uniformity_delta_e00",
                    "ghosting_metric",
                    "busy_ms",
                    "peak_current_a",
                    "energy_j",
                    "temperature_rise_c",
                )
                if plan_root["kind"] == TRANSITION_FORMAL_PLAN_KIND:
                    repeat_delta_values = []
                    repeat_metric_values = {field: [] for field in metric_fields}
                    for repeat in range(1, 6):
                        repeat_group = [
                            record
                            for record in group
                            if slot_by_id[record["slot_id"]]["formal_repeat"]
                            == repeat
                        ]
                        if len(repeat_group) != 2:
                            continue
                        repeat_delta_values.append(
                            math.fsum(
                                delta_e_ciede2000(
                                    _lab_tuple(record["initial_spectral_report"]),
                                    _lab_tuple(record["final_spectral_report"]),
                                )
                                for record in repeat_group
                            )
                            / 2
                        )
                        for field in metric_fields:
                            repeat_metric_values[field].append(
                                math.fsum(
                                    record["metrics"][field]
                                    for record in repeat_group
                                )
                                / 2
                            )
                    statistics[f"{old}->{new}.delta_e00"] = summarize_numeric(
                        repeat_delta_values
                    )
                    statistics[
                        f"{old}->{new}.paired_controller_diagnostics.delta_e00"
                    ] = _paired_controller_diagnostic(raw_delta_values)
                    for field in metric_fields:
                        statistics[f"{old}->{new}.{field}"] = summarize_numeric(
                            repeat_metric_values[field]
                        )
                        statistics[
                            f"{old}->{new}.paired_controller_diagnostics.{field}"
                        ] = _paired_controller_diagnostic(
                            [record["metrics"][field] for record in group]
                        )
                else:
                    statistics[f"{old}->{new}.delta_e00"] = summarize_numeric(
                        raw_delta_values
                    )
                    for field in metric_fields:
                        statistics[f"{old}->{new}.{field}"] = summarize_numeric(
                            [record["metrics"][field] for record in group]
                        )
    if not blockers and len(records) == len(expected_ids):
        profile = build_empty_transition_profile()
        context = plan_root["context"]
        profile.update(
            {
                "hardware_tested": True,
                "generated_at": _latest_timestamp(records),
                "panel_serial": context["panel"]["serial"],
                "firmware_git_commit": context["firmware"]["source_commit"],
                "firmware_binary_sha256": context["firmware"]["binary_sha256"],
                "waveform_id": context["waveform"]["waveform_id"],
                "waveform_sha256": context["waveform"]["waveform_sha256"],
                "environment": {
                    "temperature_c": context["environment"]["temperature_c"],
                    "relative_humidity_percent": context["environment"][
                        "relative_humidity_percent"
                    ],
                    "record_ref": context["environment"]["record_sha256"],
                },
                "illuminant": "D65",
                "observer": "2deg",
                "geometry": "45/0",
            }
        )
        for cell in profile["cells"]:
            old = cell["old_code"]
            new = cell["new_code"]
            group = [
                record
                for record in records
                if (
                    slot_by_id[record["slot_id"]]["old_code"],
                    slot_by_id[record["slot_id"]]["new_code"],
                )
                == (old, new)
            ]
            initial_lab = _mean_lab(group, "initial_spectral_report")
            final_lab = _mean_lab(group, "final_spectral_report")
            repeat_groups = {
                repeat: [
                    record
                    for record in group
                    if slot_by_id[record["slot_id"]]["formal_repeat"] == repeat
                ]
                for repeat in range(1, 6)
            }
            repeat_delta_values = [
                math.fsum(
                    delta_e_ciede2000(
                        _lab_tuple(record["initial_spectral_report"]),
                        _lab_tuple(record["final_spectral_report"]),
                    )
                    for record in repeat_groups[repeat]
                )
                / 2
                for repeat in range(1, 6)
            ]
            delta_summary = summarize_numeric(repeat_delta_values)
            controller_delta_values = []
            aggregate_bindings = []
            for repeat in range(1, 6):
                repeat_group = repeat_groups[repeat]
                cs1 = next(
                    record
                    for record in repeat_group
                    if slot_by_id[record["slot_id"]]["controller"] == "CS1"
                )
                cs2 = next(
                    record
                    for record in repeat_group
                    if slot_by_id[record["slot_id"]]["controller"] == "CS2"
                )
                controller_delta_values.append(
                    delta_e_ciede2000(
                        _lab_tuple(cs1["final_spectral_report"]),
                        _lab_tuple(cs2["final_spectral_report"]),
                    )
                )
                aggregate_bindings.append(
                    {
                        "old_code": old,
                        "new_code": new,
                        "formal_repeat": repeat,
                        "observation_canonical_sha256s": sorted(
                            record["integrity"]["canonical_sha256"]
                            for record in repeat_group
                        ),
                        "source_run_sha256s": sorted(
                            record["source_run_sha256"] for record in repeat_group
                        ),
                        "asset_manifest_sha256s": sorted(
                            record["asset_manifest_sha256"] for record in repeat_group
                        ),
                        "authorization_ids": sorted(
                            record["authorization_id"] for record in repeat_group
                        ),
                    }
                )
            controller_delta = math.fsum(controller_delta_values) / len(
                controller_delta_values
            )
            aggregate_sample_shas = [
                _sha256(binding) for binding in aggregate_bindings
            ]
            metric_map = {
                "ghosting_metric_mean": "ghosting_metric",
                "busy_ms_mean": "busy_ms",
                "peak_current_a_mean": "peak_current_a",
                "energy_j_mean": "energy_j",
                "temperature_rise_c_mean": "temperature_rise_c",
            }
            cell.update(
                {
                    # Each profile sample is one formal repeat aggregated from
                    # its two mirrored raw controller observations.  Five such
                    # independent repeats are mandatory.
                    "sample_count": 5,
                    "initial_lab_mean": initial_lab,
                    "final_lab_mean": final_lab,
                    "delta_e00_mean": delta_summary["mean"],
                    "delta_e00_sd": delta_summary["sample_standard_deviation"],
                    "cs1_minus_cs2_delta_e00": controller_delta,
                    "position_effect_delta_e00": controller_delta,
                    "recovery_pass_rate": math.fsum(
                        1.0
                        if all(
                            record["metrics"]["recovery_pass"]
                            for record in repeat_groups[repeat]
                        )
                        else 0.0
                        for repeat in range(1, 6)
                    )
                    / 5,
                    "source_run_sha256s": aggregate_sample_shas,
                    "asset_manifest_sha256s": [
                        _sha256(
                            {
                                "kind": "n5-repeat-aggregate-asset-evidence-set",
                                "binding": binding,
                            }
                        )
                        for binding in aggregate_bindings
                    ],
                    "authorization_ids": [
                        f"n5-mirrored-aggregate-{identity[:32]}"
                        for identity in aggregate_sample_shas
                    ],
                }
            )
            for output_field, input_field in metric_map.items():
                cell[output_field] = math.fsum(
                    math.fsum(
                        record["metrics"][input_field]
                        for record in repeat_groups[repeat]
                    )
                    / 2
                    for repeat in range(1, 6)
                ) / 5
            cell["position_effect_delta_e00"] = controller_delta
        try:
            validate_transition_profile(profile)
        except ValueError as error:
            blockers.append(f"transition_profile_semantic_gate_failed:{error}")
        else:
            measured_profile = profile
    measured = not blockers and measured_profile is not None
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": TRANSITION_AGGREGATE_KIND,
        "plan_kind": plan_root["kind"],
        "plan_canonical_sha256": plan_root["integrity"]["canonical_sha256"],
        "expected_sample_count": len(expected_ids),
        "accepted_sample_count": len(records),
        "missing_slot_ids": missing,
        "blockers": list(dict.fromkeys(blockers)),
        "statistics": statistics,
        "percentile_rule": "n<10 uses maximum_observed plus U95; P95/P99 are null",
        "profile_cell_sample_semantics": (
            "five formal aggregate samples per old/new pair; each is derived from "
            "required mirrored CS1 and CS2 raw observations"
        ),
        "unmeasured_scaffold": build_empty_transition_profile(),
        "measured_profile": measured_profile,
        "classification": _aggregate_classification(measured=measured),
    }
    result = {**unsigned, "integrity": _integrity(unsigned)}
    validate_transition_aggregate(result)
    return result


def aggregate_production_measured_palette(
    plan: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Optional[Mapping[str, Any]],
    instrument_qualification: Optional[Mapping[str, Any]],
    execution_contract: Mapping[str, Any],
    finalized_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Production palette entry: strict RC2G replay is mandatory."""

    return aggregate_measured_palette(
        plan,
        observations,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
        execution_contract=execution_contract,
        finalized_bundle=finalized_bundle,
        _require_strict_rc2g=True,
    )


def aggregate_production_transition_profile(
    plan: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Optional[Mapping[str, Any]],
    instrument_qualification: Optional[Mapping[str, Any]],
    execution_contract: Mapping[str, Any],
    finalized_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Production transition entry: strict RC2G replay is mandatory."""

    return aggregate_transition_profile(
        plan,
        observations,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
        execution_contract=execution_contract,
        finalized_bundle=finalized_bundle,
        _require_strict_rc2g=True,
    )


def _validate_small_sample_summaries(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        if {"n", "p95", "p99", "extreme_reporting"}.issubset(value):
            count = value["n"]
            if type(count) is not int or count < 0:
                raise MeasurementAggregationError(f"{path}.n is invalid")
            if count < 10 and (
                value["p95"] is not None
                or value["p99"] is not None
                or value["extreme_reporting"]
                not in {
                    "no-observations",
                    "maximum-observed-only-n-less-than-10",
                    "paired-controller-descriptive-no-population-percentiles",
                }
            ):
                raise MeasurementAggregationError(f"{path} labels P95/P99 with n<10")
            if value["extreme_reporting"] == (
                "paired-controller-descriptive-no-population-percentiles"
            ) and (value["p95"] is not None or value["p99"] is not None):
                raise MeasurementAggregationError(
                    f"{path} gives paired diagnostics population percentiles"
                )
            if count < 2:
                if any(
                    value.get(field) is not None
                    for field in (
                        "standard_uncertainty_of_mean",
                        "coverage_factor",
                        "u95",
                    )
                ):
                    raise MeasurementAggregationError(
                        f"{path} reports U95 without two independent values"
                    )
            elif (
                value.get("coverage_factor") != 2.0
                or isinstance(value.get("u95"), bool)
                or not isinstance(value.get("u95"), (int, float))
                or not math.isfinite(float(value["u95"]))
            ):
                raise MeasurementAggregationError(f"{path} U95 contract is invalid")
        for key, item in value.items():
            _validate_small_sample_summaries(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_small_sample_summaries(item, path=f"{path}[{index}]")


def _validate_aggregate_common(
    root: Mapping[str, Any], *, expected_sample_count: int, label: str
) -> bool:
    _hash(root["plan_canonical_sha256"], label=f"{label} plan identity")
    if root["expected_sample_count"] != expected_sample_count:
        raise MeasurementAggregationError(
            f"{label} expected_sample_count must be {expected_sample_count}"
        )
    accepted = root["accepted_sample_count"]
    if type(accepted) is not int or not 0 <= accepted <= expected_sample_count:
        raise MeasurementAggregationError(f"{label} accepted_sample_count is invalid")
    missing = root["missing_slot_ids"]
    if not isinstance(missing, list):
        raise MeasurementAggregationError(f"{label} missing_slot_ids must be a list")
    for index, slot_id in enumerate(missing):
        _text(slot_id, label=f"{label} missing_slot_ids[{index}]")
    if len(missing) != len(set(missing)):
        raise MeasurementAggregationError(f"{label} missing_slot_ids contains duplicates")
    if len(missing) != expected_sample_count - accepted:
        raise MeasurementAggregationError(f"{label} sample counts and missing slots disagree")
    blockers = root["blockers"]
    if not isinstance(blockers, list):
        raise MeasurementAggregationError(f"{label} blockers must be a list")
    for index, blocker in enumerate(blockers):
        _text(blocker, label=f"{label} blockers[{index}]")
    if len(blockers) != len(set(blockers)):
        raise MeasurementAggregationError(f"{label} blockers contains duplicates")
    if accepted < expected_sample_count and not any(
        "required_samples_incomplete" in blocker for blocker in blockers
    ):
        raise MeasurementAggregationError(f"{label} omits the incomplete-sample blocker")
    if not isinstance(root["statistics"], Mapping):
        raise MeasurementAggregationError(f"{label} statistics must be an object")
    if root["percentile_rule"] != (
        "n<10 uses maximum_observed plus U95; P95/P99 are null"
    ):
        raise MeasurementAggregationError(f"{label} percentile rule changed")
    classification = root["classification"]
    if not isinstance(classification, Mapping):
        raise MeasurementAggregationError(f"{label} classification must be an object")
    measured = classification.get("measured") is True
    if classification != _aggregate_classification(measured=measured):
        raise MeasurementAggregationError(f"{label} classification is not canonical")
    return measured


def validate_palette_aggregate(report: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        report,
        label="palette aggregate",
        keys={
            "schema_version",
            "kind",
            "plan_kind",
            "plan_canonical_sha256",
            "expected_sample_count",
            "accepted_sample_count",
            "missing_slot_ids",
            "blockers",
            "statistics",
            "percentile_rule",
            "palette",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PALETTE_AGGREGATE_KIND:
        raise MeasurementAggregationError("palette aggregate schema or kind is invalid")
    if root["plan_kind"] != PALETTE_PLAN_KIND:
        raise MeasurementAggregationError("palette aggregate does not use the formal plan")
    measured = _validate_aggregate_common(
        root, expected_sample_count=36, label="palette aggregate"
    )
    if measured != (root["palette"] is not None and not root["blockers"]):
        raise MeasurementAggregationError("palette measured classification is inconsistent")
    if measured and root["accepted_sample_count"] != root["expected_sample_count"]:
        raise MeasurementAggregationError("measured palette does not contain every slot")
    if root["palette"] is not None:
        try:
            palette_from_mapping(root["palette"])
        except PaletteError as error:
            raise MeasurementAggregationError(f"palette aggregate palette is invalid: {error}") from error
    _validate_small_sample_summaries(root["statistics"], path="palette.statistics")
    _validate_integrity(root, label="palette aggregate")
    return root


def validate_transition_aggregate(report: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(
        report,
        label="transition aggregate",
        keys={
            "schema_version",
            "kind",
            "plan_kind",
            "plan_canonical_sha256",
            "expected_sample_count",
            "accepted_sample_count",
            "missing_slot_ids",
            "blockers",
            "statistics",
            "percentile_rule",
            "profile_cell_sample_semantics",
            "unmeasured_scaffold",
            "measured_profile",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != TRANSITION_AGGREGATE_KIND:
        raise MeasurementAggregationError("transition aggregate schema or kind is invalid")
    if root["plan_kind"] not in {TRANSITION_PLAN_KIND, TRANSITION_FORMAL_PLAN_KIND}:
        raise MeasurementAggregationError("transition aggregate plan kind is invalid")
    expected_count = 360 if root["plan_kind"] == TRANSITION_FORMAL_PLAN_KIND else 72
    measured = _validate_aggregate_common(
        root, expected_sample_count=expected_count, label="transition aggregate"
    )
    if root["profile_cell_sample_semantics"] != (
        "five formal aggregate samples per old/new pair; each is derived from "
        "required mirrored CS1 and CS2 raw observations"
    ):
        raise MeasurementAggregationError("transition profile sample semantics changed")
    if root["unmeasured_scaffold"] != build_empty_transition_profile():
        raise MeasurementAggregationError("transition unmeasured scaffold is not all-null")
    try:
        validate_transition_profile(root["unmeasured_scaffold"])
        if root["measured_profile"] is not None:
            validate_transition_profile(root["measured_profile"])
    except ValueError as error:
        raise MeasurementAggregationError(f"transition aggregate profile is invalid: {error}") from error
    if measured != (root["measured_profile"] is not None and not root["blockers"]):
        raise MeasurementAggregationError("transition measured classification is inconsistent")
    if measured and root["accepted_sample_count"] != root["expected_sample_count"]:
        raise MeasurementAggregationError("measured transition profile lacks required slots")
    if measured and root["plan_kind"] != TRANSITION_FORMAL_PLAN_KIND:
        raise MeasurementAggregationError("descriptive transition plan cannot be measured")
    if measured and any(
        cell["sample_count"] != 5 for cell in root["measured_profile"]["cells"]
    ):
        raise MeasurementAggregationError("transition profile cells must be mirrored aggregates")
    _validate_small_sample_summaries(root["statistics"], path="transition.statistics")
    _validate_integrity(root, label="transition aggregate")
    return root


__all__ = [
    "INSTRUMENT_KIND",
    "MeasurementAggregationError",
    "PALETTE_AGGREGATE_KIND",
    "PALETTE_OBSERVATION_KIND",
    "PALETTE_PLAN_KIND",
    "TRANSITION_AGGREGATE_KIND",
    "TRANSITION_OBSERVATION_KIND",
    "TRANSITION_FORMAL_PLAN_KIND",
    "TRANSITION_PLAN_KIND",
    "aggregate_measured_palette",
    "aggregate_production_measured_palette",
    "aggregate_production_transition_profile",
    "aggregate_transition_profile",
    "instrument_qualification_blockers",
    "measurement_context_blockers",
    "seal_instrument_qualification",
    "seal_measurement_plan",
    "seal_palette_observation",
    "seal_transition_observation",
    "summarize_numeric",
    "validate_instrument_qualification",
    "validate_measurement_plan",
    "validate_palette_aggregate",
    "validate_palette_observation",
    "validate_transition_aggregate",
    "validate_transition_observation",
]
