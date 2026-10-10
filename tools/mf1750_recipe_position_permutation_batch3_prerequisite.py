#!/usr/bin/env python3
"""Deep-validate the sealed Batch-2 prerequisite consumed by Batch-3.

This module is intentionally read-only and offline.  It validates the exact
Batch-2 aggregate schema, compiled campaign identities, all four action and
capture bindings, the locked camera/mount signature, the sealed repeat-noise
and geometry bindings, and the terminal 60-patch white prerequisite.  It does
not access the display, camera, relay, serial port, or network.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from tools import mf1750_factory_white_repeat_noise_report as noise_report
from tools import mf1750_recipe_position_permutation_evidence_bundle as batch2


SCHEMA_VERSION = 1
KIND = "mf1750-recipe-position-permutation-evidence-bundle-v1"
EXPECTED_CLASSIFICATIONS = {
    "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE": (
        "RECIPE_LINKED_EXPLORATORY_CANDIDATE",
        2,
    ),
    "ONE_CONTROLLER_RECIPE_LINKED_CANDIDATE": (
        "CONTROLLER_INCONSISTENT_EXPLORATORY_RESULT",
        1,
    ),
    "NO_RECIPE_LINKED_CANDIDATE": (
        "NO_RECIPE_LINKED_EXPLORATORY_EFFECT",
        0,
    ),
}


class Batch3PrerequisiteError(RuntimeError):
    """Raised when the Batch-2 aggregate is not a valid Batch-3 anchor."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Batch3PrerequisiteError(f"non-canonical JSON value: {exc}") from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Batch3PrerequisiteError(f"{label} must be an object")
    return value


def _sha(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise Batch3PrerequisiteError(f"{label} must be lowercase SHA-256")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise Batch3PrerequisiteError(f"{label} must be non-empty text")
    return value


def _number(value: Any, *, label: str, nonnegative: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise Batch3PrerequisiteError(f"{label} must be a finite number")
    result = float(value)
    if nonnegative and result < 0:
        raise Batch3PrerequisiteError(f"{label} must be nonnegative")
    return result


def _time(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise Batch3PrerequisiteError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Batch3PrerequisiteError(f"{label} must include a UTC offset")
    return parsed


def _validate_campaign(value: Mapping[str, Any]) -> str:
    required = {
        "campaign_id",
        "test_id",
        "layout_id",
        "contract_id",
        "firmware_sha256",
        "firmware_bytes",
        "campaign_boot_nonce",
        "action_ids",
        "action_count",
        "visible_refresh_count",
        "no_retry",
        "no_recovery",
        "no_autochain",
    }
    if set(value) != required:
        raise Batch3PrerequisiteError("Batch-2 campaign identity keys differ")
    expected = batch2.once.base.runner
    boot_nonce = _text(
        value.get("campaign_boot_nonce"), label="Batch-2 campaign boot nonce"
    )
    if (
        value.get("campaign_id") != batch2.pack.CAMPAIGN_ID
        or value.get("test_id") != batch2.pack.TEST_ID
        or value.get("layout_id") != batch2.P1_LAYOUT_ID
        or value.get("contract_id") != expected.CONTRACT_ID
        or value.get("firmware_sha256") != batch2.once.FIRMWARE_SHA256
        or value.get("firmware_bytes") != batch2.once.FIRMWARE_BYTES
        or value.get("action_ids") != list(expected.ACTION_IDS)
        or value.get("action_count") != 4
        or value.get("visible_refresh_count") != 4
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise Batch3PrerequisiteError("Batch-2 campaign identity differs")
    return boot_nonce


def _validate_actions(
    values: Any, *, boot_nonce: str
) -> tuple[list[dict[str, Any]], list[datetime]]:
    if not isinstance(values, list) or len(values) != 4:
        raise Batch3PrerequisiteError("Batch-2 must contain four action results")
    required = {
        "ordinal",
        "path",
        "file_sha256",
        "canonical_integrity_sha256",
        "created_at",
        "action_id",
        "descriptor_id",
        "role",
        "outcome",
        "visible_refreshes",
        "frame_sha256",
        "frame_fnv1a",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
        "global_header",
        "global_header_sha256",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_sha256",
        "r21_sha256",
    }
    compiled = batch2.pack.build_report()["actions"]
    expected_actions = batch2.once.base.runner.ACTIONS
    records: list[dict[str, Any]] = []
    times: list[datetime] = []
    del boot_nonce  # Boot continuity is represented at campaign/capture level.
    for ordinal, raw in enumerate(values, 1):
        item = _mapping(raw, label=f"Batch-2 action {ordinal}")
        if set(item) != required:
            raise Batch3PrerequisiteError(f"Batch-2 action {ordinal} keys differ")
        expected = expected_actions[ordinal - 1]
        artifact = compiled[ordinal - 1]
        for field in (
            "file_sha256",
            "canonical_integrity_sha256",
            "frame_sha256",
            "cs1_dtm_sha256",
            "cs2_dtm_sha256",
        ):
            _sha(item.get(field), label=f"Batch-2 action {ordinal} {field}")
        for field in (
            "global_header_sha256",
            "cs1_r20_prefix_sha256",
            "cs2_r20_prefix_sha256",
            "r21_sha256",
        ):
            wanted = artifact[field]
            if wanted is None:
                if item.get(field) is not None:
                    raise Batch3PrerequisiteError(
                        f"Batch-2 action {ordinal} {field} must be null"
                    )
            else:
                _sha(item.get(field), label=f"Batch-2 action {ordinal} {field}")
        created = _time(
            item.get("created_at"), label=f"Batch-2 action {ordinal} created_at"
        )
        if times and created <= times[-1]:
            raise Batch3PrerequisiteError(
                "Batch-2 action timestamps are not strictly increasing"
            )
        if (
            item.get("ordinal") != ordinal
            or item.get("action_id") != expected["action_id"]
            or item.get("descriptor_id") != expected["descriptor_id"]
            or item.get("role") != expected["role"]
            or item.get("outcome") != "complete_pass"
            or item.get("visible_refreshes") != 1
            or item.get("frame_sha256") != artifact["frame"]["sha256"]
            or item.get("frame_fnv1a") != artifact["frame"]["fnv1a"]
            or item.get("cs1_dtm_sha256") != artifact["cs1_dtm"]["sha256"]
            or item.get("cs2_dtm_sha256") != artifact["cs2_dtm"]["sha256"]
            or item.get("global_header") != artifact["global_header"]
            or item.get("global_header_sha256") != artifact["global_header_sha256"]
            or item.get("cs1_r20_prefix_sha256") != artifact["cs1_r20_prefix_sha256"]
            or item.get("cs2_r20_prefix_sha256") != artifact["cs2_r20_prefix_sha256"]
            or item.get("r21_sha256") != artifact["r21_sha256"]
        ):
            raise Batch3PrerequisiteError(
                f"Batch-2 action {ordinal} compiled binding differs"
            )
        _text(item.get("path"), label=f"Batch-2 action {ordinal} path")
        records.append(dict(item))
        times.append(created)
    return records, times


def _validate_captures(
    values: Any,
    *,
    actions: list[dict[str, Any]],
    action_times: list[datetime],
) -> tuple[list[dict[str, Any]], list[datetime]]:
    if not isinstance(values, list) or len(values) != 4:
        raise Batch3PrerequisiteError("Batch-2 must contain four captures")
    required = {
        "ordinal",
        "path",
        "sidecar_file_sha256",
        "canonical_integrity_sha256",
        "capture_id",
        "captured_at",
        "action_id",
        "descriptor_id",
        "action_result_sha256",
        "photo_sha256",
        "capture_binding",
        "coverage_scope",
    }
    records: list[dict[str, Any]] = []
    times: list[datetime] = []
    expected_actions = batch2.once.base.runner.ACTIONS
    for ordinal, raw in enumerate(values, 1):
        item = _mapping(raw, label=f"Batch-2 capture {ordinal}")
        if set(item) != required:
            raise Batch3PrerequisiteError(f"Batch-2 capture {ordinal} keys differ")
        for field in (
            "sidecar_file_sha256",
            "canonical_integrity_sha256",
            "capture_id",
            "action_result_sha256",
            "photo_sha256",
        ):
            _sha(item.get(field), label=f"Batch-2 capture {ordinal} {field}")
        captured = _time(
            item.get("captured_at"), label=f"Batch-2 capture {ordinal} captured_at"
        )
        expected = expected_actions[ordinal - 1]
        if (
            item.get("ordinal") != ordinal
            or item.get("action_id") != expected["action_id"]
            or item.get("descriptor_id") != expected["descriptor_id"]
            or item.get("action_result_sha256") != actions[ordinal - 1]["file_sha256"]
            or item.get("capture_binding") != "live_synchronized"
            or item.get("coverage_scope") != "full_panel"
            or captured <= action_times[ordinal - 1]
            or (times and captured <= times[-1])
        ):
            raise Batch3PrerequisiteError(
                f"Batch-2 capture {ordinal} action/full-panel/timing differs"
            )
        _text(item.get("path"), label=f"Batch-2 capture {ordinal} path")
        records.append(dict(item))
        times.append(captured)
    return records, times


def _validate_camera_lock(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "camera_id",
        "instance_id",
        "index",
        "backend",
        "mount_id",
        "requested_settings",
        "effective_settings",
        "photo_width",
        "photo_height",
        "manual_controls_required",
        "g1_and_all_four_live_captures_same_signature",
        "all_effective_before_after_readbacks_equal",
        "all_four_live_captures_same_boot",
        "strictly_increasing_action_and_capture_timeline",
        "g1_captured_at",
        "live_capture_times",
    }
    if set(value) != required:
        raise Batch3PrerequisiteError("Batch-2 shared camera lock keys differ")
    for field in ("camera_id", "instance_id", "backend", "mount_id"):
        _text(value.get(field), label=f"Batch-2 camera {field}")
    if type(value.get("index")) is not int or value["index"] < 0:
        raise Batch3PrerequisiteError("Batch-2 camera index differs")
    for field in ("photo_width", "photo_height"):
        if type(value.get(field)) is not int or value[field] < 1:
            raise Batch3PrerequisiteError(f"Batch-2 camera {field} differs")
    requested = _mapping(value.get("requested_settings"), label="requested settings")
    effective = _mapping(value.get("effective_settings"), label="effective settings")
    try:
        noise_report._require_locked_settings(  # noqa: SLF001
            requested,
            effective,
            backend=value.get("backend"),
            label="Batch-2 camera",
        )
    except noise_report.FactoryWhiteRepeatNoiseReportError as exc:
        raise Batch3PrerequisiteError(str(exc)) from exc
    manual = _mapping(
        value.get("manual_controls_required"), label="Batch-2 manual controls"
    )
    if dict(manual) != dict(batch2.REQUIRED_MANUAL_CAMERA_SETTINGS):
        raise Batch3PrerequisiteError("Batch-2 manual camera contract differs")
    for field in (
        "g1_and_all_four_live_captures_same_signature",
        "all_effective_before_after_readbacks_equal",
        "all_four_live_captures_same_boot",
        "strictly_increasing_action_and_capture_timeline",
    ):
        if value.get(field) is not True:
            raise Batch3PrerequisiteError(f"Batch-2 camera flag {field} differs")
    _time(value.get("g1_captured_at"), label="Batch-2 G-1 capture time")
    live_times = value.get("live_capture_times")
    if not isinstance(live_times, list) or len(live_times) != 4:
        raise Batch3PrerequisiteError("Batch-2 live camera timeline differs")
    parsed = [
        _time(item, label=f"Batch-2 live camera time {index}")
        for index, item in enumerate(live_times, 1)
    ]
    if any(current <= previous for previous, current in zip(parsed, parsed[1:])):
        raise Batch3PrerequisiteError("Batch-2 live camera timeline is not increasing")
    return {
        key: deepcopy(value[key])
        for key in (
            "camera_id",
            "instance_id",
            "index",
            "backend",
            "mount_id",
            "requested_settings",
            "effective_settings",
        )
    }


def _validate_analysis(
    value: Mapping[str, Any], *, camera_signature: Mapping[str, Any]
) -> tuple[dict[str, Any], float, str]:
    required = {
        "repeat_noise_baseline",
        "reference_geometry_sha256",
        "repeat_noise_p95_de76",
        "p0_grid_from_g1_anchor_file_sha256",
        "p0_grid_from_g1_anchor_canonical_integrity_sha256",
        "p1_grid_file_sha256",
        "p1_grid_canonical_integrity_sha256",
        "comparison_binds_exact_g1_p0_and_ordinal3_p1",
        "terminal_white_gate_binds_ordinal4_photo",
        "terminal_white_gate_binds_repeat_noise_geometry",
    }
    if set(value) != required:
        raise Batch3PrerequisiteError("Batch-2 shared analysis keys differ")
    noise = _mapping(value.get("repeat_noise_baseline"), label="repeat-noise baseline")
    required_noise = {
        "path",
        "file_sha256",
        "canonical_integrity_sha256",
        "baseline_id",
        "reference_geometry_sha256",
        "capture_count",
        "repeat_noise_p95_de76",
        "camera_signature",
    }
    if set(noise) != required_noise:
        raise Batch3PrerequisiteError("Batch-2 repeat-noise binding keys differ")
    for field in (
        "file_sha256",
        "canonical_integrity_sha256",
        "baseline_id",
        "reference_geometry_sha256",
    ):
        _sha(noise.get(field), label=f"Batch-2 repeat-noise {field}")
    geometry = _sha(
        value.get("reference_geometry_sha256"),
        label="Batch-2 reference geometry",
    )
    p95 = _number(
        value.get("repeat_noise_p95_de76"),
        label="Batch-2 repeat-noise p95",
        nonnegative=True,
    )
    noise_p95 = _number(
        noise.get("repeat_noise_p95_de76"),
        label="Batch-2 bound repeat-noise p95",
        nonnegative=True,
    )
    capture_count = noise.get("capture_count")
    if (
        type(capture_count) is not int
        or capture_count < 3
        or noise.get("reference_geometry_sha256") != geometry
        or noise_p95 != p95
        or dict(_mapping(noise.get("camera_signature"), label="noise camera"))
        != dict(camera_signature)
        or any(
            value.get(field) is not True
            for field in (
                "comparison_binds_exact_g1_p0_and_ordinal3_p1",
                "terminal_white_gate_binds_ordinal4_photo",
                "terminal_white_gate_binds_repeat_noise_geometry",
            )
        )
    ):
        raise Batch3PrerequisiteError(
            "Batch-2 repeat-noise/camera/geometry binding differs"
        )
    for field in (
        "p0_grid_from_g1_anchor_file_sha256",
        "p0_grid_from_g1_anchor_canonical_integrity_sha256",
        "p1_grid_file_sha256",
        "p1_grid_canonical_integrity_sha256",
    ):
        _sha(value.get(field), label=f"Batch-2 analysis {field}")
    return deepcopy(dict(noise)), p95, geometry


def _validate_terminal(
    value: Mapping[str, Any],
    *,
    actions: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    boot_nonce: str,
    repeat_noise_p95_de76: float,
    geometry_sha256: str,
) -> dict[str, Any]:
    evidence_keys = {
        "ordinal",
        "action_result_file_sha256",
        "action_result_canonical_integrity_sha256",
        "capture_sidecar_file_sha256",
        "capture_canonical_integrity_sha256",
        "capture_id",
        "captured_at",
        "photo_sha256",
        "white_gate_file_sha256",
        "white_gate_canonical_integrity_sha256",
        "white_gate_analysis_id",
        "reference_geometry_sha256",
        "repeat_noise_p95_de76",
        "patch_count",
        "campaign_boot_nonce",
    }
    required = evidence_keys | {
        "prerequisite_id",
        "eligible",
        "classification_state",
        "terminal_is_latest_bound_batch2_capture",
        "external_refresh_after_terminal_capture_not_proven",
        "batch3_binding_contract",
    }
    if set(value) != required:
        raise Batch3PrerequisiteError("Batch-2 terminal prerequisite keys differ")
    terminal_evidence = {key: deepcopy(value[key]) for key in evidence_keys}
    for field in (
        "action_result_file_sha256",
        "action_result_canonical_integrity_sha256",
        "capture_sidecar_file_sha256",
        "capture_canonical_integrity_sha256",
        "capture_id",
        "photo_sha256",
        "white_gate_file_sha256",
        "white_gate_canonical_integrity_sha256",
        "white_gate_analysis_id",
        "reference_geometry_sha256",
    ):
        _sha(value.get(field), label=f"Batch-2 terminal {field}")
    _time(value.get("captured_at"), label="Batch-2 terminal captured_at")
    binding_contract = _mapping(
        value.get("batch3_binding_contract"), label="Batch-2 Batch-3 binding contract"
    )
    expected_contract = {
        "bind_bundle_kind": KIND,
        "bind_bundle_schema_version": SCHEMA_VERSION,
        "bind_bundle_id": "bundle_id",
        "bind_bundle_file_sha256": "whole bundle file bytes",
        "bind_bundle_canonical_integrity_sha256": "integrity.sha256",
        "bind_prerequisite_id": "terminal_white_prerequisite.prerequisite_id",
        "require_eligible_true": True,
        "deep_verify_terminal_subobject": True,
    }
    terminal_action = actions[3]
    terminal_capture = captures[3]
    terminal_noise = _number(
        value.get("repeat_noise_p95_de76"),
        label="Batch-2 terminal repeat-noise p95",
        nonnegative=True,
    )
    if (
        value.get("prerequisite_id")
        != _sha256_bytes(_canonical_json(terminal_evidence))
        or value.get("eligible") is not True
        or value.get("ordinal") != 4
        or value.get("action_result_file_sha256") != terminal_action["file_sha256"]
        or value.get("action_result_canonical_integrity_sha256")
        != terminal_action["canonical_integrity_sha256"]
        or value.get("capture_sidecar_file_sha256")
        != terminal_capture["sidecar_file_sha256"]
        or value.get("capture_canonical_integrity_sha256")
        != terminal_capture["canonical_integrity_sha256"]
        or value.get("capture_id") != terminal_capture["capture_id"]
        or value.get("captured_at") != terminal_capture["captured_at"]
        or value.get("photo_sha256") != terminal_capture["photo_sha256"]
        or value.get("reference_geometry_sha256") != geometry_sha256
        or terminal_noise != repeat_noise_p95_de76
        or value.get("patch_count") != 60
        or value.get("campaign_boot_nonce") != boot_nonce
        or value.get("classification_state")
        != "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
        or value.get("terminal_is_latest_bound_batch2_capture") is not True
        or value.get("external_refresh_after_terminal_capture_not_proven") is not True
        or dict(binding_contract) != expected_contract
    ):
        raise Batch3PrerequisiteError(
            "Batch-2 terminal 60-patch white prerequisite differs"
        )
    return deepcopy(dict(value))


def validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the validated root and a compact immutable Batch-3 binding."""

    path = Path(path)
    try:
        payload, root, canonical_sha = batch2._load_sealed(  # noqa: SLF001
            path, label="Batch-2 prerequisite bundle"
        )
    except batch2.RecipePositionPermutationEvidenceBundleError as exc:
        raise Batch3PrerequisiteError(str(exc)) from exc
    expected_keys = {
        "schema_version",
        "kind",
        "bundle_id",
        "campaign_identity",
        "action_results",
        "captures",
        "p0_g_minus_1_anchor",
        "p1_ordinal3_grid_analysis",
        "recipe_comparison",
        "terminal_white_prerequisite",
        "shared_camera_lock",
        "shared_analysis_bindings",
        "classification",
        "evidence_boundaries",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_keys:
        raise Batch3PrerequisiteError("Batch-2 top-level keys differ")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise Batch3PrerequisiteError("Batch-2 schema/write identity differs")
    campaign = _mapping(root.get("campaign_identity"), label="Batch-2 campaign")
    boot_nonce = _validate_campaign(campaign)
    actions, action_times = _validate_actions(
        root.get("action_results"), boot_nonce=boot_nonce
    )
    captures, capture_times = _validate_captures(
        root.get("captures"), actions=actions, action_times=action_times
    )
    camera_lock = _mapping(root.get("shared_camera_lock"), label="Batch-2 camera")
    camera_signature = _validate_camera_lock(camera_lock)
    if camera_lock.get("live_capture_times") != [
        item["captured_at"] for item in captures
    ] or any(capture_times[index] <= action_times[index] for index in range(4)):
        raise Batch3PrerequisiteError("Batch-2 shared camera timeline differs")
    shared_analysis = _mapping(
        root.get("shared_analysis_bindings"), label="Batch-2 analysis"
    )
    noise_binding, repeat_noise, geometry = _validate_analysis(
        shared_analysis, camera_signature=camera_signature
    )
    terminal = _validate_terminal(
        _mapping(root.get("terminal_white_prerequisite"), label="Batch-2 terminal"),
        actions=actions,
        captures=captures,
        boot_nonce=boot_nonce,
        repeat_noise_p95_de76=repeat_noise,
        geometry_sha256=geometry,
    )

    classification = _mapping(
        root.get("classification"), label="Batch-2 classification"
    )
    recipe_state = classification.get("recipe_comparison_state")
    expected_classification = EXPECTED_CLASSIFICATIONS.get(recipe_state)
    if (
        expected_classification is None
        or classification.get("state") != expected_classification[0]
        or classification.get("recipe_linked_controller_count")
        != expected_classification[1]
        or classification.get("recipe_linked_exploratory_only") is not True
        or classification.get("qualified_new_colour") is not False
        or classification.get("qualified_brightness_level") is not False
        or classification.get("absolute_colour_proven") is not False
    ):
        raise Batch3PrerequisiteError("Batch-2 classification boundary differs")
    boundaries = _mapping(root.get("evidence_boundaries"), label="Batch-2 boundaries")
    required_boundaries = {
        "g1_is_zero_refresh_retrospective_geometry_and_p0_anchor_only": True,
        "g1_is_not_live_action_evidence": True,
        "camera_relative_only": True,
        "recipe_linkage_is_exploratory": True,
        "one_permutation_cannot_qualify_a_new_colour": True,
        "absolute_colour_or_new_colour_not_proven": True,
        "compiled_payload_identity_not_bus_capture": True,
        "all_four_batch2_captures_live_synchronized_and_full_panel": True,
        "external_refresh_after_terminal_capture_not_proven": True,
        "device_io_performed_by_bundle_builder": False,
    }
    if dict(boundaries) != required_boundaries:
        raise Batch3PrerequisiteError("Batch-2 evidence boundaries differ")

    input_hashes = {
        "actions": [item["file_sha256"] for item in actions],
        "captures": [item["sidecar_file_sha256"] for item in captures],
        "repeat_noise": noise_binding["file_sha256"],
        "g1_anchor": _mapping(
            root.get("p0_g_minus_1_anchor"), label="Batch-2 G-1 anchor"
        ).get("file_sha256"),
        "p1_grid": _mapping(
            root.get("p1_ordinal3_grid_analysis"), label="Batch-2 P1 grid"
        ).get("file_sha256"),
        "comparison": _mapping(
            root.get("recipe_comparison"), label="Batch-2 comparison"
        ).get("file_sha256"),
        "terminal_white_gate": terminal["white_gate_file_sha256"],
    }
    for field in ("g1_anchor", "p1_grid", "comparison"):
        _sha(input_hashes[field], label=f"Batch-2 {field} file SHA")
    expected_bundle_id = _sha256_bytes(
        _canonical_json({"kind": KIND, "inputs": input_hashes})
    )
    if root.get("bundle_id") != expected_bundle_id:
        raise Batch3PrerequisiteError("Batch-2 bundle_id differs")
    return dict(root), {
        "input_file": str(path.resolve()),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": canonical_sha,
        "bundle_id": expected_bundle_id,
        "campaign_identity": deepcopy(dict(campaign)),
        "terminal_white_prerequisite": terminal,
        "shared_camera_lock": camera_signature,
        "shared_analysis_bindings": {
            "repeat_noise_baseline": noise_binding,
            "reference_geometry_sha256": geometry,
            "repeat_noise_p95_de76": repeat_noise,
        },
    }
