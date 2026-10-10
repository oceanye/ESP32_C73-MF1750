"""Fail-closed semantic validators for extended-colour machine records.

JSON Schema freezes the serialized shape.  These validators additionally
enforce cross-field identity, authorization, time, evidence and finite-number
rules that JSON Schema cannot express reliably by itself.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping


class ExtendedColorRecordError(ValueError):
    """Raised when a machine record is structurally or semantically unsafe."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_FNV_HEX = re.compile(r"^0x[0-9A-F]{8}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_EVIDENCE_STATUSES = frozenset({"not_run", "partial", "complete", "invalid"})
_TERMINAL_RUN_STATUSES = frozenset({"completed", "aborted", "fault_locked"})
_AUTHORIZATION_KEYS = (
    "flash_com8",
    "power_off_confirmed",
    "power_on",
    "power_normal_confirmed",
    "send_frame",
    "post_refresh_confirmed",
    "final_power_off_tp1_confirmed",
)
_CORE_HARDWARE_AUTHORIZATIONS = (
    "power_off_confirmed",
    "power_on",
    "power_normal_confirmed",
    "send_frame",
)
_FORMAL_CODES = frozenset({0, 1, 2, 3, 5, 6})
_COMPLETE_EVENT_SEQUENCE = (
    "power_off_confirmed",
    "power_on_authorized",
    "power_normal_confirmed",
    "frame_authorized",
    "pon",
    "drf",
    "pof",
    "operator_observation",
    "power_off_authorized",
    "tp1_zero_confirmed",
)


def _mapping(
    value: Any,
    *,
    label: str,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExtendedColorRecordError(f"{label} must be an object")
    keys = set(value)
    missing = set(required) - keys
    unknown = keys - set(required) - set(optional)
    if missing or unknown:
        raise ExtendedColorRecordError(
            f"{label} has missing keys {sorted(missing)} or unknown keys {sorted(unknown)}"
        )
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExtendedColorRecordError(f"{label} must be an array")
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ExtendedColorRecordError(
            f"{label} must be a non-empty string of at most {maximum} characters"
        )
    return value


def _nullable_text(value: Any, *, label: str, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    return _text(value, label=label, maximum=maximum)


def _boolean(value: Any, *, label: str) -> bool:
    if type(value) is not bool:
        raise ExtendedColorRecordError(f"{label} must be a boolean")
    return value


def _integer(
    value: Any,
    *,
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise ExtendedColorRecordError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ExtendedColorRecordError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ExtendedColorRecordError(f"{label} must be at most {maximum}")
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtendedColorRecordError(f"{label} must be a JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ExtendedColorRecordError(f"{label} must be finite")
    if minimum is not None and numeric < minimum:
        raise ExtendedColorRecordError(f"{label} must be at least {minimum}")
    if maximum is not None and numeric > maximum:
        raise ExtendedColorRecordError(f"{label} must be at most {maximum}")
    return numeric


def _nullable_number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _number(value, label=label, minimum=minimum, maximum=maximum)


def _timestamp(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label, maximum=64)
    if _RFC3339.fullmatch(text) is None:
        raise ExtendedColorRecordError(f"{label} must be a strict RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExtendedColorRecordError(f"{label} must be a valid RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExtendedColorRecordError(f"{label} must include a UTC offset")
    return parsed


def _nullable_timestamp(value: Any, *, label: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, label=label)


def _hash(value: Any, *, label: str, required: bool) -> str | None:
    if value is None:
        if required:
            raise ExtendedColorRecordError(f"{label} is required for hardware evidence")
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ExtendedColorRecordError(f"{label} must be a lowercase SHA-256")
    return value


def _lab(value: Any, *, label: str, required: bool) -> Mapping[str, Any] | None:
    if value is None:
        if required:
            raise ExtendedColorRecordError(f"{label} is required")
        return None
    lab = _mapping(value, label=label, required={"l", "a", "b"})
    _number(lab["l"], label=f"{label}.l", minimum=0.0, maximum=100.0)
    _number(lab["a"], label=f"{label}.a", minimum=-200.0, maximum=200.0)
    _number(lab["b"], label=f"{label}.b", minimum=-200.0, maximum=200.0)
    return lab


def _record_header(record: Mapping[str, Any], *, label: str, kind: str) -> tuple[bool, str]:
    if record["schema_version"] != 2 or record["kind"] != kind:
        raise ExtendedColorRecordError(f"{label} identity is invalid")
    _text(record["run_id"], label=f"{label}.run_id", maximum=128)
    hardware_tested = _boolean(record["hardware_tested"], label=f"{label}.hardware_tested")
    status = record["evidence_status"]
    if status not in _EVIDENCE_STATUSES:
        raise ExtendedColorRecordError(f"{label}.evidence_status is invalid")
    reason = record["null_reason"]
    generated_at = record["generated_at"]
    if not hardware_tested:
        if status != "not_run":
            raise ExtendedColorRecordError(
                f"{label} without hardware evidence must have evidence_status=not_run"
            )
        _text(reason, label=f"{label}.null_reason")
        if generated_at is not None:
            raise ExtendedColorRecordError(
                f"{label}.generated_at must be null when hardware_tested is false"
            )
    else:
        if status == "not_run":
            raise ExtendedColorRecordError(
                f"{label} hardware evidence cannot have evidence_status=not_run"
            )
        _timestamp(generated_at, label=f"{label}.generated_at")
        if status == "complete":
            if reason is not None:
                raise ExtendedColorRecordError(
                    f"{label}.null_reason must be null for complete evidence"
                )
        else:
            _text(reason, label=f"{label}.null_reason")
    return hardware_tested, status


def _authorization(value: Any, *, label: str) -> tuple[bool, datetime | None]:
    authorization = _mapping(
        value,
        label=label,
        required={"authorized", "authorization_id", "recorded_at"},
    )
    authorized = _boolean(authorization["authorized"], label=f"{label}.authorized")
    if authorized:
        _text(authorization["authorization_id"], label=f"{label}.authorization_id")
        recorded_at = _timestamp(
            authorization["recorded_at"], label=f"{label}.recorded_at"
        )
    elif authorization["authorization_id"] is not None or authorization["recorded_at"] is not None:
        raise ExtendedColorRecordError(
            f"{label} must keep identity and time null when not authorized"
        )
    else:
        recorded_at = None
    return authorized, recorded_at


def _frame_identity(value: Any, *, require_hashes: bool) -> None:
    identity = _mapping(
        value,
        label="run.frame_identity",
        required={
            "width",
            "height",
            "bits_per_pixel",
            "frame_bytes",
            "frame_sha256",
            "frame_fnv1a",
            "frame_fnv1a_hex",
            "controllers",
            "canonical_sha256",
            "canonical_sha256_scope",
        },
    )
    constants = {
        "width": 1024,
        "height": 600,
        "bits_per_pixel": 4,
        "frame_bytes": 307200,
        "canonical_sha256_scope": (
            "canonical JSON of frame byte/hash fields and ordered CS1/CS2 DTM identities"
        ),
    }
    for key, expected in constants.items():
        if identity[key] != expected:
            raise ExtendedColorRecordError(f"run.frame_identity.{key} is invalid")
    frame_sha256 = _hash(
        identity["frame_sha256"],
        label="run.frame_identity.frame_sha256",
        required=require_hashes,
    )
    canonical_sha256 = _hash(
        identity["canonical_sha256"],
        label="run.frame_identity.canonical_sha256",
        required=require_hashes,
    )
    frame_fnv = _integer(
        identity["frame_fnv1a"],
        label="run.frame_identity.frame_fnv1a",
        minimum=0,
        maximum=0xFFFFFFFF,
    )
    if not isinstance(identity["frame_fnv1a_hex"], str) or _FNV_HEX.fullmatch(
        identity["frame_fnv1a_hex"]
    ) is None:
        raise ExtendedColorRecordError("run.frame_identity.frame_fnv1a_hex is invalid")
    if identity["frame_fnv1a_hex"] != f"0x{frame_fnv:08X}":
        raise ExtendedColorRecordError("run frame FNV integer and hex identities disagree")

    controllers = _list(identity["controllers"], label="run.frame_identity.controllers")
    if len(controllers) != 2:
        raise ExtendedColorRecordError("run.frame_identity.controllers must contain CS1 and CS2")
    canonical_controllers: list[dict[str, Any]] = []
    for index, expected_controller in enumerate(("CS1", "CS2")):
        controller = _mapping(
            controllers[index],
            label=f"run.frame_identity.controllers[{index}]",
            required={
                "controller",
                "mapping",
                "dtm_bytes",
                "dtm_sha256",
                "dtm_fnv1a",
                "dtm_fnv1a_hex",
            },
        )
        if controller["controller"] != expected_controller or controller["dtm_bytes"] != 153600:
            raise ExtendedColorRecordError(f"run {expected_controller} identity is invalid")
        mapping = _mapping(
            controller["mapping"],
            label=f"run {expected_controller} mapping",
            required={"source_half", "flip_x", "flip_y", "nibble_swap"},
        )
        expected_mapping = {
            "source_half": index,
            "flip_x": False,
            "flip_y": False,
            "nibble_swap": False,
        }
        _integer(
            mapping["source_half"],
            label=f"run {expected_controller} mapping.source_half",
            minimum=index,
            maximum=index,
        )
        for flag in ("flip_x", "flip_y", "nibble_swap"):
            _boolean(mapping[flag], label=f"run {expected_controller} mapping.{flag}")
        if dict(mapping) != expected_mapping:
            raise ExtendedColorRecordError(f"run {expected_controller} mapping is invalid")
        dtm_sha256 = _hash(
            controller["dtm_sha256"],
            label=f"run {expected_controller}.dtm_sha256",
            required=require_hashes,
        )
        dtm_fnv = _integer(
            controller["dtm_fnv1a"],
            label=f"run {expected_controller}.dtm_fnv1a",
            minimum=0,
            maximum=0xFFFFFFFF,
        )
        if controller["dtm_fnv1a_hex"] != f"0x{dtm_fnv:08X}":
            raise ExtendedColorRecordError(
                f"run {expected_controller} FNV integer and hex identities disagree"
            )
        canonical_controllers.append(
            {
                "controller": expected_controller,
                "mapping": expected_mapping,
                "dtm_bytes": 153600,
                "dtm_sha256": dtm_sha256,
                "dtm_fnv1a": dtm_fnv,
                "dtm_fnv1a_hex": f"0x{dtm_fnv:08X}",
            }
        )

    canonical_inputs = (frame_sha256, *(item["dtm_sha256"] for item in canonical_controllers))
    if canonical_sha256 is not None:
        if any(item is None for item in canonical_inputs):
            raise ExtendedColorRecordError(
                "run canonical frame identity cannot be present with null component hashes"
            )
        frame_document = {
            "frame_bytes": 307200,
            "frame_sha256": frame_sha256,
            "frame_fnv1a": frame_fnv,
            "controllers": canonical_controllers,
        }
        expected_canonical = hashlib.sha256(
            json.dumps(
                frame_document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if canonical_sha256 != expected_canonical:
            raise ExtendedColorRecordError(
                "run.frame_identity.canonical_sha256 does not bind the frame/DTM identities"
            )


def validate_run_record(record: Mapping[str, Any]) -> None:
    """Validate one run identity, authorization and timing record."""

    record = _mapping(
        record,
        label="run",
        required={
            "schema_version",
            "kind",
            "test_id",
            "run_id",
            "stage",
            "status",
            "evidence_status",
            "null_reason",
            "hardware_tested",
            "generated_at",
            "asset_manifest_sha256",
            "panel",
            "authorization",
            "authorization_scope",
            "firmware",
            "frame_identity",
            "environment",
            "started_at",
            "finished_at",
        },
        optional={"candidate_code", "initial_color_code", "abort_reason", "notes"},
    )
    hardware_tested, evidence_status = _record_header(
        record, label="run", kind="mf1750-extended-color-run"
    )
    _text(record["test_id"], label="run.test_id", maximum=96)
    if record["stage"] not in {"D", "E", "G", "H", "I"}:
        raise ExtendedColorRecordError("run.stage is invalid")
    run_status = record["status"]
    if run_status not in {"planned", "authorized", "running", *_TERMINAL_RUN_STATUSES}:
        raise ExtendedColorRecordError("run.status is invalid")
    if "candidate_code" in record and record["candidate_code"] is not None:
        _integer(record["candidate_code"], label="run.candidate_code", minimum=0, maximum=15)
    if "initial_color_code" in record and record["initial_color_code"] is not None:
        code = _integer(record["initial_color_code"], label="run.initial_color_code")
        if code not in _FORMAL_CODES:
            raise ExtendedColorRecordError("run.initial_color_code is invalid")

    panel = _mapping(
        record["panel"],
        label="run.panel",
        required={
            "model",
            "serial",
            "pcb_revision",
            "controller",
            "controller_revision",
            "r15",
            "r16_ohm",
        },
    )
    panel_constants = {
        "model": "MF-17506-M009F-T",
        "pcb_revision": "MF1750 Rev A1",
        "controller": "SPD1657B",
        "controller_revision": "0x04",
        "r15": "removed",
    }
    if any(panel[key] != expected for key, expected in panel_constants.items()):
        raise ExtendedColorRecordError("run.panel frozen identity is invalid")
    _integer(panel["r16_ohm"], label="run.panel.r16_ohm", minimum=0, maximum=0)
    if hardware_tested:
        _text(panel["serial"], label="run.panel.serial")
    else:
        _nullable_text(panel["serial"], label="run.panel.serial")

    authorizations = _mapping(
        record["authorization"],
        label="run.authorization",
        required=set(_AUTHORIZATION_KEYS),
    )
    authorization_results = {
        key: _authorization(authorizations[key], label=f"run.authorization.{key}")
        for key in _AUTHORIZATION_KEYS
    }

    authorization_scope = _mapping(
        record["authorization_scope"],
        label="run.authorization_scope",
        required={"test_id", "frame_sha256", "canonical_sha256"},
    )

    firmware = _mapping(
        record["firmware"],
        label="run.firmware",
        required={"git_commit", "build_tag", "binary_sha256", "release_unknown_code_disabled"},
    )
    if firmware["git_commit"] is not None and (
        not isinstance(firmware["git_commit"], str)
        or _HEX40.fullmatch(firmware["git_commit"]) is None
    ):
        raise ExtendedColorRecordError("run.firmware.git_commit is invalid")
    _text(firmware["build_tag"], label="run.firmware.build_tag")
    _hash(
        firmware["binary_sha256"],
        label="run.firmware.binary_sha256",
        required=hardware_tested,
    )
    if firmware["release_unknown_code_disabled"] is not True:
        raise ExtendedColorRecordError("run release unknown-code guard must remain enabled")
    if hardware_tested and firmware["git_commit"] is None:
        raise ExtendedColorRecordError("run.firmware.git_commit is required for hardware evidence")

    _frame_identity(record["frame_identity"], require_hashes=hardware_tested)
    scope_test_id = authorization_scope["test_id"]
    scope_frame_sha256 = authorization_scope["frame_sha256"]
    scope_canonical_sha256 = authorization_scope["canonical_sha256"]
    scope_values = (scope_test_id, scope_frame_sha256, scope_canonical_sha256)
    if any(value is not None for value in scope_values):
        if any(value is None for value in scope_values):
            raise ExtendedColorRecordError(
                "run.authorization_scope fields must be all null or all present"
            )
        _text(scope_test_id, label="run.authorization_scope.test_id", maximum=96)
        _hash(
            scope_frame_sha256,
            label="run.authorization_scope.frame_sha256",
            required=True,
        )
        _hash(
            scope_canonical_sha256,
            label="run.authorization_scope.canonical_sha256",
            required=True,
        )
        if scope_test_id != record["test_id"]:
            raise ExtendedColorRecordError("run authorization scope test_id disagrees")
        if scope_frame_sha256 != record["frame_identity"]["frame_sha256"]:
            raise ExtendedColorRecordError("run authorization scope frame SHA-256 disagrees")
        expected_scope_sha256 = hashlib.sha256(
            json.dumps(
                {"frame_sha256": scope_frame_sha256, "test_id": scope_test_id},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if scope_canonical_sha256 != expected_scope_sha256:
            raise ExtendedColorRecordError("run authorization scope canonical SHA-256 disagrees")
    if hardware_tested and any(value is None for value in scope_values):
        raise ExtendedColorRecordError("hardware run requires an exact authorization scope")
    asset_manifest_sha256 = _hash(
        record["asset_manifest_sha256"],
        label="run.asset_manifest_sha256",
        required=hardware_tested,
    )
    if any(result[0] for result in authorization_results.values()) and any(
        value is None for value in scope_values
    ):
        raise ExtendedColorRecordError(
            "authorized run actions require an exact test/frame authorization scope"
        )

    environment = _mapping(
        record["environment"],
        label="run.environment",
        required={"temperature_c", "relative_humidity_percent", "record_ref"},
    )
    temperature = _nullable_number(
        environment["temperature_c"], label="run.environment.temperature_c", minimum=-100, maximum=200
    )
    humidity = _nullable_number(
        environment["relative_humidity_percent"],
        label="run.environment.relative_humidity_percent",
        minimum=0,
        maximum=100,
    )
    record_ref = _nullable_text(environment["record_ref"], label="run.environment.record_ref")

    started_at = _nullable_timestamp(record["started_at"], label="run.started_at")
    finished_at = _nullable_timestamp(record["finished_at"], label="run.finished_at")
    if started_at is not None and finished_at is not None and finished_at < started_at:
        raise ExtendedColorRecordError("run.finished_at must not precede started_at")

    abort_reason = record.get("abort_reason")
    if run_status in {"aborted", "fault_locked"}:
        _text(abort_reason, label="run.abort_reason")
    elif abort_reason is not None:
        raise ExtendedColorRecordError("run.abort_reason is only valid for aborted/fault_locked runs")
    if "notes" in record:
        _nullable_text(record["notes"], label="run.notes")

    if not hardware_tested:
        if run_status not in {"planned", "authorized"} or started_at is not None or finished_at is not None:
            raise ExtendedColorRecordError(
                "run without hardware evidence must remain planned/authorized with null run times"
            )
        if temperature is not None or humidity is not None or record_ref is not None:
            raise ExtendedColorRecordError(
                "run without hardware evidence must keep environment measurements null"
            )
        if asset_manifest_sha256 is not None:
            raise ExtendedColorRecordError(
                "run without hardware evidence must keep asset_manifest_sha256 null"
            )
        return

    generated_at = _timestamp(record["generated_at"], label="run.generated_at")
    if run_status not in {"running", *_TERMINAL_RUN_STATUSES} or started_at is None:
        raise ExtendedColorRecordError("hardware-tested run requires a running/terminal status and start time")
    if run_status in _TERMINAL_RUN_STATUSES and finished_at is None:
        raise ExtendedColorRecordError("terminal hardware run requires finished_at")
    if run_status == "running" and finished_at is not None:
        raise ExtendedColorRecordError("running hardware run must keep finished_at null")
    if temperature is None or humidity is None or record_ref is None:
        raise ExtendedColorRecordError("hardware-tested run requires complete environment evidence")

    authorization_flags = {
        key: value[0] for key, value in authorization_results.items()
    }
    authorization_times = {
        key: value[1] for key, value in authorization_results.items()
    }
    if authorization_flags["power_on"] and not authorization_flags["power_off_confirmed"]:
        raise ExtendedColorRecordError("power-on evidence requires prior power-off confirmation")
    if authorization_flags["power_normal_confirmed"] and not authorization_flags["power_on"]:
        raise ExtendedColorRecordError("power-normal evidence requires power-on evidence")
    if authorization_flags["send_frame"] and not authorization_flags["power_normal_confirmed"]:
        raise ExtendedColorRecordError("frame authorization requires normal-power confirmation")
    if authorization_flags["post_refresh_confirmed"] and not authorization_flags["send_frame"]:
        raise ExtendedColorRecordError("post-refresh confirmation requires a sent frame")

    pre_start_keys = (
        "flash_com8",
        "power_off_confirmed",
        "power_on",
        "power_normal_confirmed",
        "send_frame",
    )
    for key in pre_start_keys:
        recorded_at = authorization_times[key]
        if recorded_at is not None and recorded_at > started_at:
            raise ExtendedColorRecordError(
                f"run.authorization.{key} must not be recorded after started_at"
            )
    if finished_at is not None:
        for key, recorded_at in authorization_times.items():
            if recorded_at is not None and recorded_at > finished_at:
                raise ExtendedColorRecordError(
                    f"run.authorization.{key} must not be recorded after finished_at"
                )
        if generated_at < finished_at:
            raise ExtendedColorRecordError("run.generated_at must not precede finished_at")
    elif generated_at < started_at:
        raise ExtendedColorRecordError("run.generated_at must not precede started_at")

    if run_status == "running":
        for key in _CORE_HARDWARE_AUTHORIZATIONS:
            if not authorization_flags[key]:
                raise ExtendedColorRecordError(f"running hardware run lacks {key} evidence")
    if run_status == "completed":
        for key in (*_CORE_HARDWARE_AUTHORIZATIONS, "post_refresh_confirmed", "final_power_off_tp1_confirmed"):
            if not authorization_flags[key]:
                raise ExtendedColorRecordError(f"completed run lacks {key} evidence")
    if evidence_status == "complete":
        if run_status != "completed":
            raise ExtendedColorRecordError("complete evidence requires run.status=completed")
    elif evidence_status == "invalid" and run_status not in {"aborted", "fault_locked"}:
        raise ExtendedColorRecordError("invalid evidence requires aborted/fault_locked run status")


_MEASUREMENT_KEYS = frozenset(
    {
        "roi_id",
        "controller",
        "x0",
        "y0",
        "x1",
        "y1",
        "intended_initial_code",
        "measured_initial_lab",
        "target_code",
        "measured_final_lab",
        "delta_e00",
        "uniformity_delta_e00",
        "ghosting_metric",
    }
)


def validate_optical_record(record: Mapping[str, Any]) -> None:
    """Validate optical provenance, ROI geometry and measured values."""

    record = _mapping(
        record,
        label="optical",
        required={
            "schema_version",
            "kind",
            "run_id",
            "hardware_tested",
            "evidence_status",
            "null_reason",
            "generated_at",
            "source_run_sha256",
            "asset_manifest_sha256",
            "authorization_id",
            "timepoint",
            "timepoint_basis",
            "geometry",
            "illuminant",
            "observer",
            "aperture_mm",
            "instrument_id",
            "raw_capture_ref",
            "raw_capture_sha256",
            "measurements",
        },
        optional={"notes"},
    )
    hardware_tested, evidence_status = _record_header(
        record, label="optical", kind="mf1750-extended-color-optical"
    )
    if record["timepoint"] not in {"t0", "10min", "1h", "24h", "72h", "other"}:
        raise ExtendedColorRecordError("optical.timepoint is invalid")
    if record["timepoint_basis"] != "POF BUSY_N low-to-high + 60 s for t0":
        raise ExtendedColorRecordError("optical.timepoint_basis is invalid")
    if record["geometry"] != "45/0" or record["illuminant"] != "D65":
        raise ExtendedColorRecordError("optical geometry or illuminant is invalid")
    if record["observer"] != "2deg":
        raise ExtendedColorRecordError("optical observer is invalid")
    aperture = _nullable_number(record["aperture_mm"], label="optical.aperture_mm", minimum=0.000001)
    instrument = _nullable_text(record["instrument_id"], label="optical.instrument_id")
    raw_ref = _nullable_text(record["raw_capture_ref"], label="optical.raw_capture_ref")
    raw_capture_sha256 = _hash(
        record["raw_capture_sha256"],
        label="optical.raw_capture_sha256",
        required=hardware_tested,
    )
    source_run_sha256 = _hash(
        record["source_run_sha256"],
        label="optical.source_run_sha256",
        required=hardware_tested,
    )
    asset_manifest_sha256 = _hash(
        record["asset_manifest_sha256"],
        label="optical.asset_manifest_sha256",
        required=hardware_tested,
    )
    authorization_id = _nullable_text(record["authorization_id"], label="optical.authorization_id")
    if "notes" in record:
        _nullable_text(record["notes"], label="optical.notes")

    measurements = _list(record["measurements"], label="optical.measurements")
    seen_roi: set[str] = set()
    for index, value in enumerate(measurements):
        measurement = _mapping(
            value,
            label=f"optical.measurements[{index}]",
            required=set(_MEASUREMENT_KEYS),
        )
        roi_id = _text(measurement["roi_id"], label=f"optical.measurements[{index}].roi_id")
        if roi_id in seen_roi:
            raise ExtendedColorRecordError(f"optical duplicate roi_id {roi_id}")
        seen_roi.add(roi_id)
        controller = measurement["controller"]
        if controller not in {"CS1", "CS2"}:
            raise ExtendedColorRecordError(f"optical measurement {index} controller is invalid")
        x0 = _integer(measurement["x0"], label=f"optical measurement {index}.x0", minimum=0, maximum=1023)
        y0 = _integer(measurement["y0"], label=f"optical measurement {index}.y0", minimum=0, maximum=599)
        x1 = _integer(measurement["x1"], label=f"optical measurement {index}.x1", minimum=1, maximum=1024)
        y1 = _integer(measurement["y1"], label=f"optical measurement {index}.y1", minimum=1, maximum=600)
        if x0 >= x1 or y0 >= y1:
            raise ExtendedColorRecordError(f"optical measurement {index} ROI is empty or inverted")
        if (controller == "CS1" and x1 > 512) or (controller == "CS2" and x0 < 512):
            raise ExtendedColorRecordError(f"optical measurement {index} crosses controller boundary")
        initial_code = _integer(
            measurement["intended_initial_code"],
            label=f"optical measurement {index}.intended_initial_code",
        )
        if initial_code not in _FORMAL_CODES:
            raise ExtendedColorRecordError(f"optical measurement {index} initial code is invalid")
        _integer(
            measurement["target_code"],
            label=f"optical measurement {index}.target_code",
            minimum=0,
            maximum=15,
        )
        complete = evidence_status == "complete"
        _lab(
            measurement["measured_initial_lab"],
            label=f"optical measurement {index}.measured_initial_lab",
            required=complete,
        )
        _lab(
            measurement["measured_final_lab"],
            label=f"optical measurement {index}.measured_final_lab",
            required=complete,
        )
        for field in ("delta_e00", "uniformity_delta_e00", "ghosting_metric"):
            result = _nullable_number(
                measurement[field],
                label=f"optical measurement {index}.{field}",
                minimum=0,
            )
            if complete and result is None:
                raise ExtendedColorRecordError(
                    f"complete optical evidence requires measurement {index}.{field}"
                )

    if not hardware_tested:
        if any(value is not None for value in (aperture, instrument, raw_ref, authorization_id)):
            raise ExtendedColorRecordError("not-run optical record must keep acquisition metadata null")
        if measurements:
            raise ExtendedColorRecordError("not-run optical record must have no measurements")
        if any(
            value is not None
            for value in (raw_capture_sha256, source_run_sha256, asset_manifest_sha256)
        ):
            raise ExtendedColorRecordError("not-run optical record must keep evidence hashes null")
        return
    if aperture is None or instrument is None or raw_ref is None or authorization_id is None:
        raise ExtendedColorRecordError("hardware optical record lacks instrument/capture/authorization evidence")
    if not measurements:
        raise ExtendedColorRecordError("hardware optical record requires at least one ROI measurement")


def _rail(
    value: Any,
    *,
    label: str,
    polarity: str,
    enforce_polarity: bool,
) -> None:
    rail = _mapping(
        value,
        label=label,
        required={
            "minimum_v",
            "maximum_v",
            "plateau_v",
            "rise_ms",
            "release_ms",
            "absolute_limit_known",
            "absolute_limit_reason",
        },
    )
    minimum_v = _nullable_number(rail["minimum_v"], label=f"{label}.minimum_v")
    maximum_v = _nullable_number(rail["maximum_v"], label=f"{label}.maximum_v")
    plateau_v = _nullable_number(rail["plateau_v"], label=f"{label}.plateau_v")
    _nullable_number(rail["rise_ms"], label=f"{label}.rise_ms", minimum=0)
    _nullable_number(rail["release_ms"], label=f"{label}.release_ms", minimum=0)
    absolute_known = _boolean(rail["absolute_limit_known"], label=f"{label}.absolute_limit_known")
    reason = rail["absolute_limit_reason"]
    if absolute_known:
        raise ExtendedColorRecordError(
            f"{label}.absolute_limit_known cannot be true in schema v2; no qualified limit profile is allowlisted"
        )
    _text(reason, label=f"{label}.absolute_limit_reason")
    if minimum_v is not None and maximum_v is not None and minimum_v > maximum_v:
        raise ExtendedColorRecordError(f"{label}.minimum_v must not exceed maximum_v")
    if (
        plateau_v is not None
        and minimum_v is not None
        and maximum_v is not None
        and not minimum_v <= plateau_v <= maximum_v
    ):
        raise ExtendedColorRecordError(f"{label}.plateau_v must be inside its measured envelope")
    measured_voltages = tuple(
        item for item in (minimum_v, maximum_v, plateau_v) if item is not None
    )
    if enforce_polarity and polarity == "positive" and any(
        item < 0 for item in measured_voltages
    ):
        raise ExtendedColorRecordError(f"{label} must remain a nonnegative rail")
    if enforce_polarity and polarity == "negative" and any(
        item > 0 for item in measured_voltages
    ):
        raise ExtendedColorRecordError(f"{label} must remain a nonpositive rail")
    if enforce_polarity and plateau_v is not None:
        if polarity == "positive" and plateau_v <= 0:
            raise ExtendedColorRecordError(f"{label}.plateau_v must be positive")
        if polarity == "negative" and plateau_v >= 0:
            raise ExtendedColorRecordError(f"{label}.plateau_v must be negative")


def validate_electrical_record(record: Mapping[str, Any]) -> None:
    """Validate synchronized electrical/thermal evidence and interlocks."""

    record = _mapping(
        record,
        label="electrical",
        required={
            "schema_version",
            "kind",
            "run_id",
            "hardware_tested",
            "evidence_status",
            "null_reason",
            "generated_at",
            "source_run_sha256",
            "asset_manifest_sha256",
            "authorization_id",
            "limit_profile",
            "acquisition",
            "busy",
            "input_power",
            "rails",
            "temperatures",
            "interlocks",
        },
        optional={"notes"},
    )
    hardware_tested, evidence_status = _record_header(
        record, label="electrical", kind="mf1750-extended-color-electrical"
    )
    complete = evidence_status == "complete"
    if complete:
        raise ExtendedColorRecordError(
            "complete electrical evidence is unavailable in schema v2 until a reviewed absolute-limit profile is frozen in code"
        )
    source_run_sha256 = _hash(
        record["source_run_sha256"],
        label="electrical.source_run_sha256",
        required=hardware_tested,
    )
    asset_manifest_sha256 = _hash(
        record["asset_manifest_sha256"],
        label="electrical.asset_manifest_sha256",
        required=hardware_tested,
    )
    authorization_id = _nullable_text(
        record["authorization_id"], label="electrical.authorization_id"
    )

    limit_profile = _mapping(
        record["limit_profile"],
        label="electrical.limit_profile",
        required={
            "profile_id",
            "profile_version",
            "profile_sha256",
            "source_ref",
            "qualified",
        },
    )
    limit_profile_id = _nullable_text(
        limit_profile["profile_id"], label="electrical.limit_profile.profile_id"
    )
    limit_profile_version = limit_profile["profile_version"]
    if limit_profile_version is not None:
        limit_profile_version = _integer(
            limit_profile_version,
            label="electrical.limit_profile.profile_version",
            minimum=1,
        )
    limit_profile_sha256 = _hash(
        limit_profile["profile_sha256"],
        label="electrical.limit_profile.profile_sha256",
        required=False,
    )
    limit_profile_source = _nullable_text(
        limit_profile["source_ref"], label="electrical.limit_profile.source_ref"
    )
    limit_profile_qualified = _boolean(
        limit_profile["qualified"], label="electrical.limit_profile.qualified"
    )
    limit_identity = (
        limit_profile_id,
        limit_profile_version,
        limit_profile_sha256,
        limit_profile_source,
    )
    if any(item is not None for item in limit_identity) and any(
        item is None for item in limit_identity
    ):
        raise ExtendedColorRecordError(
            "electrical.limit_profile identity/version/hash/source must be all null or all present"
        )
    if limit_profile_qualified:
        raise ExtendedColorRecordError(
            "electrical.limit_profile.qualified must remain false; schema v2 has no reviewed allowlist"
        )
    if "notes" in record:
        _nullable_text(record["notes"], label="electrical.notes")

    acquisition = _mapping(
        record["acquisition"],
        label="electrical.acquisition",
        required={
            "instrument_ids",
            "sample_rate_sps",
            "bandwidth_hz",
            "clock_alignment_ms",
            "raw_trace_refs",
            "raw_trace_sha256",
        },
    )
    instrument_ids = _list(acquisition["instrument_ids"], label="electrical.instrument_ids")
    for index, value in enumerate(instrument_ids):
        _text(value, label=f"electrical.instrument_ids[{index}]")
    if len(set(instrument_ids)) != len(instrument_ids):
        raise ExtendedColorRecordError("electrical.instrument_ids must be unique")
    sample_rate = _nullable_number(
        acquisition["sample_rate_sps"], label="electrical.sample_rate_sps", minimum=0.000001
    )
    bandwidth = _nullable_number(
        acquisition["bandwidth_hz"], label="electrical.bandwidth_hz", minimum=0.000001
    )
    alignment = _nullable_number(
        acquisition["clock_alignment_ms"], label="electrical.clock_alignment_ms", minimum=0
    )
    trace_refs = _list(acquisition["raw_trace_refs"], label="electrical.raw_trace_refs")
    trace_hashes = _list(acquisition["raw_trace_sha256"], label="electrical.raw_trace_sha256")
    if len(trace_refs) != len(trace_hashes):
        raise ExtendedColorRecordError("electrical trace references and hashes must have equal length")
    for index, (reference, digest) in enumerate(zip(trace_refs, trace_hashes)):
        _text(reference, label=f"electrical.raw_trace_refs[{index}]")
        _hash(digest, label=f"electrical.raw_trace_sha256[{index}]", required=True)
    if len(set(trace_refs)) != len(trace_refs):
        raise ExtendedColorRecordError("electrical.raw_trace_refs must be unique")

    busy = _mapping(
        record["busy"],
        label="electrical.busy",
        required={"pon_ms", "pon_asserted", "drf_ms", "drf_asserted", "pof_ms", "pof_asserted", "timeout"},
    )
    for field in ("pon_ms", "drf_ms", "pof_ms"):
        value = _nullable_number(busy[field], label=f"electrical.busy.{field}", minimum=0)
        if complete and value is None:
            raise ExtendedColorRecordError(f"complete electrical evidence requires busy.{field}")
    for field in ("pon_asserted", "drf_asserted", "pof_asserted", "timeout"):
        value = busy[field]
        if value is not None:
            _boolean(value, label=f"electrical.busy.{field}")
        if complete and value is None:
            raise ExtendedColorRecordError(f"complete electrical evidence requires busy.{field}")
    if complete and (not all(busy[field] is True for field in ("pon_asserted", "drf_asserted", "pof_asserted")) or busy["timeout"] is not False):
        raise ExtendedColorRecordError("complete electrical evidence requires all BUSY assertions and no timeout")

    input_power = _mapping(
        record["input_power"],
        label="electrical.input_power",
        required={
            "peak_current_a",
            "mean_current_a",
            "rms_current_a",
            "energy_j",
            "tp1_min_v",
            "droop_v",
            "supply_cc_or_trip",
        },
    )
    power_values: dict[str, float | None] = {}
    for field in ("peak_current_a", "mean_current_a", "rms_current_a", "energy_j", "droop_v"):
        power_values[field] = _nullable_number(
            input_power[field], label=f"electrical.input_power.{field}", minimum=0
        )
    power_values["tp1_min_v"] = _nullable_number(
        input_power["tp1_min_v"], label="electrical.input_power.tp1_min_v", minimum=0, maximum=10
    )
    trip = input_power["supply_cc_or_trip"]
    if trip is not None:
        _boolean(trip, label="electrical.input_power.supply_cc_or_trip")
    if complete and (any(value is None for value in power_values.values()) or trip is None):
        raise ExtendedColorRecordError("complete electrical evidence requires all input-power metrics")
    mean = power_values["mean_current_a"]
    rms = power_values["rms_current_a"]
    peak = power_values["peak_current_a"]
    if mean is not None and rms is not None and peak is not None and not mean <= rms <= peak:
        raise ExtendedColorRecordError("electrical current metrics must satisfy mean <= RMS <= peak")
    if complete and trip is not False:
        raise ExtendedColorRecordError("complete electrical evidence cannot include a supply trip")

    rails = _mapping(
        record["rails"],
        label="electrical.rails",
        required={"tp3_vph", "tp5_prevgl", "tp6_vpc"},
    )
    for key, polarity in (
        ("tp3_vph", "positive"),
        ("tp5_prevgl", "negative"),
        ("tp6_vpc", "negative"),
    ):
        _rail(
            rails[key],
            label=f"electrical.rails.{key}",
            polarity=polarity,
            enforce_polarity=evidence_status != "invalid",
        )

    temperatures = _mapping(
        record["temperatures"],
        label="electrical.temperatures",
        required={"panel_c", "controller_1_c", "controller_2_c", "q1_c", "q2_c", "l1_c", "l2_c"},
    )
    for field, value in temperatures.items():
        measured = _nullable_number(
            value, label=f"electrical.temperatures.{field}", minimum=-100, maximum=250
        )
        if complete and measured is None:
            raise ExtendedColorRecordError(f"complete electrical evidence requires temperature {field}")

    interlocks = _mapping(
        record["interlocks"],
        label="electrical.interlocks",
        required={"estop_armed", "hardware_current_limit_armed", "j2_1_latched_switch_armed", "triggered"},
    )
    for field, value in interlocks.items():
        if value is not None:
            _boolean(value, label=f"electrical.interlocks.{field}")
        if complete and value is None:
            raise ExtendedColorRecordError(f"complete electrical evidence requires interlock {field}")
    if complete and (
        not all(interlocks[field] is True for field in ("estop_armed", "hardware_current_limit_armed", "j2_1_latched_switch_armed"))
        or interlocks["triggered"] is not False
    ):
        raise ExtendedColorRecordError("complete electrical evidence requires armed, untriggered interlocks")

    if not hardware_tested:
        if source_run_sha256 is not None or asset_manifest_sha256 is not None:
            raise ExtendedColorRecordError(
                "not-run electrical record must keep evidence hashes null"
            )
        if any(item is not None for item in limit_identity) or limit_profile_qualified:
            raise ExtendedColorRecordError("not-run electrical record must keep limit profile null")
        if authorization_id is not None or instrument_ids or trace_refs:
            raise ExtendedColorRecordError("not-run electrical record must keep acquisition evidence empty")
        if any(value is not None for value in (sample_rate, bandwidth, alignment)):
            raise ExtendedColorRecordError("not-run electrical record must keep acquisition values null")
        if any(value is not None for value in busy.values()):
            raise ExtendedColorRecordError("not-run electrical record must keep BUSY evidence null")
        if any(value is not None for value in input_power.values()):
            raise ExtendedColorRecordError("not-run electrical record must keep power evidence null")
        if any(value is not None for value in temperatures.values()):
            raise ExtendedColorRecordError("not-run electrical record must keep temperatures null")
        if any(value is not None for value in interlocks.values()):
            raise ExtendedColorRecordError("not-run electrical record must keep interlocks null")
        for rail_name, rail_value in rails.items():
            if any(
                rail_value[field] is not None
                for field in ("minimum_v", "maximum_v", "plateau_v", "rise_ms", "release_ms")
            ):
                raise ExtendedColorRecordError(
                    f"not-run electrical record must keep {rail_name} measurements null"
                )
        return
    if authorization_id is None or not instrument_ids or not trace_refs:
        raise ExtendedColorRecordError("hardware electrical record lacks authorization/instrument/trace evidence")
    if any(value is None for value in (sample_rate, bandwidth, alignment)):
        raise ExtendedColorRecordError("hardware electrical record lacks acquisition timing metadata")


_EVENT_NAMES = frozenset(
    {
        "power_off_confirmed",
        "flash_authorized",
        "flashed",
        "power_on_authorized",
        "power_normal_confirmed",
        "frame_authorized",
        "pon",
        "drf",
        "pof",
        "operator_observation",
        "fault",
        "recovery_authorized",
        "recovery_frame",
        "recovery_confirmed",
        "power_off_authorized",
        "tp1_zero_confirmed",
    }
)
_EVENTS_REQUIRING_AUTHORIZATION_ID = frozenset(
    {
        "flash_authorized",
        "flashed",
        "power_on_authorized",
        "frame_authorized",
        "recovery_authorized",
        "recovery_frame",
        "power_off_authorized",
    }
)


def validate_event_recovery_record(record: Mapping[str, Any]) -> None:
    """Validate ordered events, no-retry policy, recovery and safe power-off evidence."""

    record = _mapping(
        record,
        label="event_recovery",
        required={
            "schema_version",
            "kind",
            "run_id",
            "hardware_tested",
            "evidence_status",
            "null_reason",
            "generated_at",
            "source_run_sha256",
            "asset_manifest_sha256",
            "authorization_id",
            "events",
            "abnormality",
            "automatic_retry_count",
            "recovery",
            "final_power_state",
        },
    )
    hardware_tested, evidence_status = _record_header(
        record, label="event_recovery", kind="mf1750-extended-color-event-recovery"
    )
    complete = evidence_status == "complete"
    source_run_sha256 = _hash(
        record["source_run_sha256"],
        label="event_recovery.source_run_sha256",
        required=hardware_tested,
    )
    asset_manifest_sha256 = _hash(
        record["asset_manifest_sha256"],
        label="event_recovery.asset_manifest_sha256",
        required=hardware_tested,
    )
    authorization_id = _nullable_text(
        record["authorization_id"], label="event_recovery.authorization_id"
    )
    if record["automatic_retry_count"] != 0 or type(record["automatic_retry_count"]) is not int:
        raise ExtendedColorRecordError("event_recovery.automatic_retry_count must be integer zero")

    events = _list(record["events"], label="event_recovery.events")
    previous_timestamp: datetime | None = None
    event_rows: list[tuple[str, str, str | None, datetime | None]] = []
    for index, value in enumerate(events):
        event = _mapping(
            value,
            label=f"event_recovery.events[{index}]",
            required={"sequence", "timestamp", "event", "authorization_id", "result", "details"},
        )
        if _integer(event["sequence"], label=f"event {index}.sequence", minimum=0) != index:
            raise ExtendedColorRecordError("event sequences must be contiguous and start at zero")
        timestamp = _nullable_timestamp(event["timestamp"], label=f"event {index}.timestamp")
        if hardware_tested and timestamp is None:
            raise ExtendedColorRecordError("hardware events require timestamps")
        if previous_timestamp is not None and timestamp is not None and timestamp < previous_timestamp:
            raise ExtendedColorRecordError("event timestamps must be nondecreasing")
        if timestamp is not None:
            previous_timestamp = timestamp
        event_name = event["event"]
        if event_name not in _EVENT_NAMES:
            raise ExtendedColorRecordError(f"event {index} name is invalid")
        event_authorization = _nullable_text(
            event["authorization_id"], label=f"event {index}.authorization_id"
        )
        if event_name in _EVENTS_REQUIRING_AUTHORIZATION_ID and event_authorization is None:
            raise ExtendedColorRecordError(f"event {index} requires an authorization_id")
        if event["result"] not in {"pending", "pass", "fail", "not_run"}:
            raise ExtendedColorRecordError(f"event {index} result is invalid")
        if hardware_tested and event["result"] == "not_run":
            raise ExtendedColorRecordError("hardware event cannot be marked not_run")
        if complete and event["result"] == "pending":
            raise ExtendedColorRecordError("complete event record cannot contain pending events")
        _nullable_text(event["details"], label=f"event {index}.details")
        event_rows.append((event_name, event["result"], event_authorization, timestamp))

    abnormality = _mapping(
        record["abnormality"],
        label="event_recovery.abnormality",
        required={"observed", "category", "description", "fault_locked"},
    )
    observed = _boolean(abnormality["observed"], label="event_recovery.abnormality.observed")
    fault_locked = _boolean(
        abnormality["fault_locked"], label="event_recovery.abnormality.fault_locked"
    )
    category = abnormality["category"]
    if category not in {"busy", "current", "voltage", "temperature", "visual", "instrument", "data", "other", None}:
        raise ExtendedColorRecordError("event_recovery abnormality category is invalid")
    description = _nullable_text(
        abnormality["description"], label="event_recovery.abnormality.description"
    )
    if observed:
        if category is None or description is None:
            raise ExtendedColorRecordError("observed abnormality requires category and description")
    elif category is not None or description is not None or fault_locked:
        raise ExtendedColorRecordError("unobserved abnormality must keep details empty and unlocked")
    if fault_locked and not observed:
        raise ExtendedColorRecordError("fault lock requires an observed abnormality")

    recovery = _mapping(
        record["recovery"],
        label="event_recovery.recovery",
        required={
            "authorized",
            "authorization_id",
            "attempted",
            "sequence",
            "passed",
            "final_white_delta_e00",
            "raw_ghosting_metric",
        },
    )
    recovery_authorized = _boolean(
        recovery["authorized"], label="event_recovery.recovery.authorized"
    )
    recovery_authorization = _nullable_text(
        recovery["authorization_id"], label="event_recovery.recovery.authorization_id"
    )
    if recovery_authorized != (recovery_authorization is not None):
        raise ExtendedColorRecordError("recovery authorization boolean and identity disagree")
    attempted = _boolean(recovery["attempted"], label="event_recovery.recovery.attempted")
    if recovery["sequence"] != [0, 1, 0, 1]:
        raise ExtendedColorRecordError("recovery sequence must remain black-white-black-white")
    passed = recovery["passed"]
    if passed is not None:
        _boolean(passed, label="event_recovery.recovery.passed")
    final_delta = _nullable_number(
        recovery["final_white_delta_e00"],
        label="event_recovery.recovery.final_white_delta_e00",
        minimum=0,
    )
    ghosting = _nullable_number(
        recovery["raw_ghosting_metric"],
        label="event_recovery.recovery.raw_ghosting_metric",
        minimum=0,
    )
    if attempted and not recovery_authorized:
        raise ExtendedColorRecordError("recovery attempt requires separate authorization")
    if attempted and passed is None:
        raise ExtendedColorRecordError("recovery attempt requires an explicit pass/fail result")
    if not attempted and any(value is not None for value in (passed, final_delta, ghosting)):
        raise ExtendedColorRecordError("unattempted recovery must keep results null")
    if complete and attempted and (final_delta is None or ghosting is None):
        raise ExtendedColorRecordError("complete attempted recovery requires optical recovery metrics")

    final_power = _mapping(
        record["final_power_state"],
        label="event_recovery.final_power_state",
        required={"j2_1_off_confirmed", "tp1_v", "tp1_at_or_below_0_10_v_for_5s"},
    )
    off_confirmed = final_power["j2_1_off_confirmed"]
    below_threshold = final_power["tp1_at_or_below_0_10_v_for_5s"]
    if off_confirmed is not None:
        _boolean(off_confirmed, label="event_recovery.final_power_state.j2_1_off_confirmed")
    if below_threshold is not None:
        _boolean(
            below_threshold,
            label="event_recovery.final_power_state.tp1_at_or_below_0_10_v_for_5s",
        )
    tp1_v = _nullable_number(
        final_power["tp1_v"],
        label="event_recovery.final_power_state.tp1_v",
        minimum=0,
        maximum=10,
    )

    if not hardware_tested:
        if source_run_sha256 is not None or asset_manifest_sha256 is not None:
            raise ExtendedColorRecordError(
                "not-run event record must keep evidence hashes null"
            )
        if authorization_id is not None or events:
            raise ExtendedColorRecordError("not-run event record must keep authorization/events empty")
        if observed or recovery_authorized or attempted:
            raise ExtendedColorRecordError("not-run event record cannot claim abnormalities or recovery")
        if any(value is not None for value in (off_confirmed, below_threshold, tp1_v)):
            raise ExtendedColorRecordError("not-run event record must keep final power evidence null")
        return
    if authorization_id is None or not events:
        raise ExtendedColorRecordError("hardware event record lacks authorization or event evidence")

    generated_at = _timestamp(record["generated_at"], label="event_recovery.generated_at")
    if previous_timestamp is not None and generated_at < previous_timestamp:
        raise ExtendedColorRecordError(
            "event_recovery.generated_at must not precede the final event"
        )

    event_names = [row[0] for row in event_rows]
    event_results = [row[1] for row in event_rows]

    flash_authorized_indexes = [
        index for index, name in enumerate(event_names) if name == "flash_authorized"
    ]
    flashed_indexes = [index for index, name in enumerate(event_names) if name == "flashed"]
    if bool(flash_authorized_indexes) != bool(flashed_indexes):
        raise ExtendedColorRecordError(
            "flash_authorized and flashed events must occur as a pair"
        )
    if flash_authorized_indexes:
        if len(flash_authorized_indexes) != 1 or len(flashed_indexes) != 1:
            raise ExtendedColorRecordError("flash authorization and action must each occur once")
        authorized_index = flash_authorized_indexes[0]
        flashed_index = flashed_indexes[0]
        if authorized_index >= flashed_index:
            raise ExtendedColorRecordError("flash authorization must precede flashing")
        if event_rows[authorized_index][2] != event_rows[flashed_index][2]:
            raise ExtendedColorRecordError("flash action must use its authorization identity")

    recovery_event_indexes = [
        index
        for index, name in enumerate(event_names)
        if name in {"recovery_authorized", "recovery_frame", "recovery_confirmed"}
    ]
    if recovery_event_indexes and (not recovery_authorized or not attempted):
        raise ExtendedColorRecordError(
            "recovery events require an authorized, attempted recovery record"
        )
    if attempted and not recovery_event_indexes:
        raise ExtendedColorRecordError("attempted recovery requires recovery events")
    for index in recovery_event_indexes:
        name, _, event_authorization, _ = event_rows[index]
        if name in {"recovery_authorized", "recovery_frame"} and (
            event_authorization != recovery_authorization
        ):
            raise ExtendedColorRecordError(
                "recovery event authorization does not match recovery.authorization_id"
            )

    if complete:
        if observed:
            raise ExtendedColorRecordError("record with an abnormality cannot be complete evidence")
        if "fault" in event_names:
            raise ExtendedColorRecordError("complete event record cannot contain a fault event")
        if any(result != "pass" for result in event_results):
            raise ExtendedColorRecordError("complete event record requires every event to pass")
        mandatory_indexes: list[int] = []
        for required_name in _COMPLETE_EVENT_SEQUENCE:
            matches = [
                index for index, name in enumerate(event_names) if name == required_name
            ]
            if len(matches) != 1:
                raise ExtendedColorRecordError(
                    f"complete event record requires exactly one {required_name} event"
                )
            mandatory_indexes.append(matches[0])
        if mandatory_indexes != sorted(mandatory_indexes):
            raise ExtendedColorRecordError(
                "complete event record does not follow the frozen refresh/power-off order"
            )
        mandatory_positions = dict(zip(_COMPLETE_EVENT_SEQUENCE, mandatory_indexes))
        if flash_authorized_indexes and not (
            mandatory_positions["power_off_confirmed"]
            < flash_authorized_indexes[0]
            < flashed_indexes[0]
            < mandatory_positions["power_on_authorized"]
        ):
            raise ExtendedColorRecordError(
                "complete flash events must occur after power-off confirmation and before power-on authorization"
            )
        if event_names[-1] != "tp1_zero_confirmed":
            raise ExtendedColorRecordError(
                "tp1_zero_confirmed must be the final event in a complete record"
            )
        if recovery_event_indexes:
            recovery_authorized_matches = [
                index
                for index, name in enumerate(event_names)
                if name == "recovery_authorized"
            ]
            recovery_frames = [
                index for index, name in enumerate(event_names) if name == "recovery_frame"
            ]
            recovery_confirmed_matches = [
                index
                for index, name in enumerate(event_names)
                if name == "recovery_confirmed"
            ]
            if (
                len(recovery_authorized_matches) != 1
                or len(recovery_frames) != 4
                or len(recovery_confirmed_matches) != 1
            ):
                raise ExtendedColorRecordError(
                    "complete recovery requires one authorization, four frames and one confirmation"
                )
            recovery_order = (
                recovery_authorized_matches[0],
                *recovery_frames,
                recovery_confirmed_matches[0],
            )
            if tuple(sorted(recovery_order)) != recovery_order:
                raise ExtendedColorRecordError("complete recovery events are out of order")
            if not (
                mandatory_positions["operator_observation"]
                < recovery_order[0]
                and recovery_order[-1]
                < mandatory_positions["power_off_authorized"]
            ):
                raise ExtendedColorRecordError(
                    "complete recovery must occur after observation and before final power-off authorization"
                )
            if recovery_order != tuple(range(recovery_order[0], recovery_order[-1] + 1)):
                raise ExtendedColorRecordError(
                    "complete recovery authorization, frames and confirmation must be contiguous"
                )
            if passed is not True:
                raise ExtendedColorRecordError("complete recovery evidence requires recovery pass")
        elif recovery_authorized or attempted or passed is not None:
            raise ExtendedColorRecordError(
                "complete record without recovery events must keep recovery unused"
            )
        if off_confirmed is not True or below_threshold is not True or tp1_v is None or tp1_v > 0.10:
            raise ExtendedColorRecordError("complete event record requires safe final power-off evidence")


__all__ = [
    "ExtendedColorRecordError",
    "validate_electrical_record",
    "validate_event_recovery_record",
    "validate_optical_record",
    "validate_run_record",
]
