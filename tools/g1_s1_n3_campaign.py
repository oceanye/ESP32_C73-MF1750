#!/usr/bin/env python3
"""Compile offline-only N3 repeatability and balanced-order campaigns.

N3A repeats one selected N2 candidate two, three, or four times.  N3B uses a
fixed-seed four-treatment Williams design to separate candidate position from
candidate identity.  Every target action is immediately preceded by its own
MAP primer in the same P0 session.  Consequently N3B measures session-order
and position effects; it deliberately does not measure direct target-to-target
carryover, which remains an N8 concern.

This module only creates and validates canonical JSON data.  It has no network,
serial, GPIO, firmware-upload, claim-writing, authorization, retry, recovery,
or device-execution path.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    describe_action_offline,
    seal_campaign_contract,
    validate_campaign_contract,
)
from tools.g1_s1_rc2g_n2_photo_campaign import (  # noqa: E402
    EXPECTED_MANIFEST_CANONICAL_SHA256 as N2_CANONICAL_SHA256,
    EXPECTED_MANIFEST_FILE_SHA256 as N2_FILE_SHA256,
    Q3_Q4_DIFFERING_PIXELS,
    compile_campaign_manifest as compile_n2_manifest,
    validate_compiled_manifest as validate_n2_manifest,
)
from tools.g1_s1_rc2g_quality_refresh_once import (  # noqa: E402
    MAX_JOB_DRIVER_DURATION_DELTA_MS,
    MAX_QUEUE_DELAY_MS,
    NOMINAL_JOB_DURATION_MS,
    NOMINAL_STAGE_TIMING_MS,
)


SCHEMA_VERSION = 1
N3A_KIND = "mf1750-g1-s1-n3a-repeatability-offline-manifest"
N3B_KIND = "mf1750-g1-s1-n3b-balanced-order-offline-manifest"
N3_DESCRIPTION_KIND = "mf1750-g1-s1-n3-action-description"
SESSION_REGIME_KIND = "mf1750-g1-s1-n3-session-regime-profile"
ASSET_REGISTRY_KIND = "mf1750-g1-s1-n3-measurement-asset-registry"

N3A_HASH_SCOPE = (
    "entire N3A manifest excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
N3B_HASH_SCOPE = N3A_HASH_SCOPE.replace("N3A", "N3B")
N3_DESCRIPTION_HASH_SCOPE = N3A_HASH_SCOPE.replace("N3A manifest", "N3 description")

N3A_REPEAT_COUNTS = (2, 3, 4)
N3_CELLS = ("Q1", "Q2", "Q3", "Q4")
N3B_FIXED_SEED = "n3b-williams-order-20260808-v1"
N3B_ORDER_ALGORITHM = "sha256-sort-labels-then-even-williams-square-v1"

# These identities are for the default planning manifests: the frozen N2P P0
# placeholder panel/firmware, ordinary controller-fresh sessions, null draft
# measurement assets, and zero predeclared interval/cooldown.  A physical panel
# binding or reviewed schedule necessarily creates a different manifest SHA.
EXPECTED_FROZEN_N3A_CANONICAL_SHA256 = (
    "3bf68ebea4a647b27387adf94fd9a04765a34dad564b7786068a60e21df2d42f"
)
EXPECTED_FROZEN_N3A_FILE_SHA256 = (
    "9de5648c06aaf1d87c4187a49a5bfe9a6da6dae52e9439f7736c71ec10c5f75d"
)
EXPECTED_FROZEN_N3B_CANONICAL_SHA256 = (
    "bae2a6e874ed45e04e9d42051f1d06e788c3f81f26e98acc33b69fc15ae02483"
)
EXPECTED_FROZEN_N3B_FILE_SHA256 = (
    "c6e1d79227ba87ba5f0dc2dddce055e82235d6b3806c5911710ec428a2832996"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_P0_CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}


class N3CampaignError(ValueError):
    """An N3 offline campaign or description failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3CampaignError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise N3CampaignError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
    return value


def _require_nonnegative_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N3CampaignError(f"{label} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise N3CampaignError(f"{label} must be a non-negative finite number")
    return result


def _require_exact_keys(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N3CampaignError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise N3CampaignError(f"{label} keys changed; missing={missing}, extra={extra}")
    return value


@lru_cache(maxsize=1)
def _n2_manifest_bytes() -> bytes:
    manifest = compile_n2_manifest()
    validate_n2_manifest(manifest)
    payload = canonical_json_bytes(manifest)
    if N2_CANONICAL_SHA256 is None or N2_FILE_SHA256 is None:
        raise N3CampaignError("the natural-photo N2 source manifest is not frozen yet")
    if (
        manifest["manifest_integrity"]["canonical_sha256"]
        != N2_CANONICAL_SHA256
        or _sha256(payload) != N2_FILE_SHA256
    ):
        raise N3CampaignError("the frozen N2 source manifest identity changed")
    return payload


def _n2_manifest() -> Mapping[str, Any]:
    return json.loads(_n2_manifest_bytes().decode("utf-8"))


def _source_record(n2: Mapping[str, Any]) -> dict[str, Any]:
    q3 = next(cell for cell in n2["cells"] if cell["cell_id"] == "Q3")
    q4 = next(cell for cell in n2["cells"] if cell["cell_id"] == "Q4")
    q3_budget = q3["candidate"]["options"]["value"]["budget"]
    q4_budget = q4["candidate"]["options"]["value"]["budget"]
    gate = n2["scientific_gate"]
    shared_schedule = gate["shared_schedule"]
    coverage = gate["coverage"]
    readiness = n2["readiness"]
    if (
        n2["classification"]["natural_photo_input"] is not True
        or n2["classification"]["candidate_set_ready"] is not True
        or gate["scientific_gate_pass"] is not True
        or gate["pixel_difference"]["differing_pixels"] != Q3_Q4_DIFFERING_PIXELS
        or q3_budget != q4_budget
        or shared_schedule["budget"] != q3_budget
        or q3_budget.get("max_evaluations") != 262_144
        or q3_budget.get("wall_clock_deadline_used") is not False
        or coverage["minimum_required_ratio"] != 0.10
        or coverage["observed_primary_ratio"] < 0.10
        or coverage["tile_count"] != 160
        or coverage["nonempty_tiles"] != 160
        or coverage["pass"] is not True
        or not 0.45 <= coverage["left_ratio"] <= 0.55
        or not 0.45 <= coverage["right_ratio"] <= 0.55
        or gate["loss_matrix"]["diagonal_dominance_pass"] is not True
        or gate["initializer_improvement"]["Q3"]["pass"] is not True
        or gate["initializer_improvement"]["Q4"]["pass"] is not True
        or gate["pixel_difference"]["required_as_sole_scientific_gate"] is not False
        or readiness["candidate_set_ready"] is not True
        or any(
            readiness[field] is not False
            for field in (
                "hardware_ready",
                "execution_runner_present",
                "reviewed_limit_profile_present",
                "scoring_contract_present",
                "hardware_execution_authorized",
                "upload_authorized",
            )
        )
    ):
        raise N3CampaignError("natural-photo N2 scientific/budget gate changed")
    return {
        "kind": n2["kind"],
        "campaign_id": n2["campaign_id"],
        "canonical_sha256": N2_CANONICAL_SHA256,
        "file_sha256": N2_FILE_SHA256,
        "candidate_cells": list(N3_CELLS),
        "natural_photo_input": True,
        "candidate_set_ready": True,
        "scientific_separation_gate_pass": True,
        "scientific_gate_canonical_sha256": _sha256(gate),
        "shared_schedule_canonical_sha256": _sha256(shared_schedule),
        "q3_q4_deterministic_max_evaluations": 262_144,
        "q3_q4_shared_seed": shared_schedule["seed"],
        "q3_q4_proposal_trace_sha256": shared_schedule["proposal_trace_sha256"],
        "q3_q4_coverage_canonical_sha256": shared_schedule[
            "coverage_canonical_sha256"
        ],
        "q3_q4_coverage_ratio": coverage["observed_primary_ratio"],
        "q3_q4_coverage_nonempty_tiles": 160,
        "q3_q4_left_ratio": coverage["left_ratio"],
        "q3_q4_right_ratio": coverage["right_ratio"],
        "q3_q4_diagonal_dominance_pass": True,
        "q3_q4_initializer_improvement_pass": True,
        "q3_q4_differing_pixels": Q3_Q4_DIFFERING_PIXELS,
        "pixel_difference_is_sole_gate": False,
        "winner_selection_performed": False,
        "winner_selection_authorized_by_compiler": False,
    }


def _p0_frame_from_map(n2: Mapping[str, Any]) -> dict[str, Any]:
    return _snapshot(n2["shared_evidence"]["map_primer"]["frame"])


def _p0_frame_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    frame = candidate["frame"]
    return {
        "width": frame["width"],
        "height": frame["height"],
        "bits_per_pixel": frame["bits_per_pixel"],
        "bytes": frame["bytes"],
        "sha256": frame["sha256"],
        "fnv1a": frame["fnv1a"],
        "controllers": _snapshot(frame["controllers"]),
    }


def _driver_timing_contract() -> dict[str, Any]:
    return {
        "job_duration_ms": list(NOMINAL_JOB_DURATION_MS),
        "maximum_queue_delay_ms": MAX_QUEUE_DELAY_MS,
        "maximum_job_driver_duration_delta_ms": MAX_JOB_DRIVER_DURATION_DELTA_MS,
        "stages_ms": {
            name: list(bounds) for name, bounds in NOMINAL_STAGE_TIMING_MS.items()
        },
    }


def ordinary_session_regime() -> dict[str, Any]:
    """Return the default N3 regime: controller fresh boot, no J2 cycle."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_REGIME_KIND,
        "profile_id": "n3-controller-fresh-own-map-j2-retained-v1",
        "controller": {"fresh_boot_required": True},
        "visible_prior": {
            "own_map_required": True,
            "scope": "same_cell",
            "target_requires_map_pass_result": True,
        },
        "panel_j2": {
            "cold_cycle_required": False,
            "minimum_measured_off_seconds": None,
            "profile_review_artifact_sha256": None,
            "may_remain_on_before_session": True,
        },
    }


def panel_cold_session_regime(
    *, minimum_measured_off_seconds: int | float, review_artifact_sha256: str
) -> dict[str, Any]:
    """Return a panel-cold regime only when an explicit reviewed profile exists."""

    off_seconds = _require_nonnegative_number(
        minimum_measured_off_seconds,
        label="minimum_measured_off_seconds",
    )
    if off_seconds <= 0:
        raise N3CampaignError("panel-cold dwell must be positive")
    review_sha = _require_sha256(
        review_artifact_sha256,
        label="review_artifact_sha256",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_REGIME_KIND,
        "profile_id": "n3-controller-fresh-own-map-panel-cold-reviewed-v1",
        "controller": {"fresh_boot_required": True},
        "visible_prior": {
            "own_map_required": True,
            "scope": "same_cell",
            "target_requires_map_pass_result": True,
        },
        "panel_j2": {
            "cold_cycle_required": True,
            "minimum_measured_off_seconds": off_seconds,
            "profile_review_artifact_sha256": review_sha,
            "may_remain_on_before_session": False,
        },
    }


def _validate_session_regime(value: Any) -> Mapping[str, Any]:
    root = _require_exact_keys(
        value,
        label="session regime",
        keys={
            "schema_version",
            "kind",
            "profile_id",
            "controller",
            "visible_prior",
            "panel_j2",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != SESSION_REGIME_KIND:
        raise N3CampaignError("session regime schema or kind is invalid")
    if not isinstance(root["profile_id"], str) or not root["profile_id"]:
        raise N3CampaignError("session regime profile_id is invalid")
    controller = _require_exact_keys(
        root["controller"],
        label="session regime controller",
        keys={"fresh_boot_required"},
    )
    if controller["fresh_boot_required"] is not True:
        raise N3CampaignError("N3 sessions require a controller fresh boot")
    prior = _require_exact_keys(
        root["visible_prior"],
        label="session regime visible prior",
        keys={"own_map_required", "scope", "target_requires_map_pass_result"},
    )
    if prior != {
        "own_map_required": True,
        "scope": "same_cell",
        "target_requires_map_pass_result": True,
    }:
        raise N3CampaignError("N3 target prior must be its own same-cell MAP PASS")
    panel = _require_exact_keys(
        root["panel_j2"],
        label="session regime panel/J2",
        keys={
            "cold_cycle_required",
            "minimum_measured_off_seconds",
            "profile_review_artifact_sha256",
            "may_remain_on_before_session",
        },
    )
    if type(panel["cold_cycle_required"]) is not bool:
        raise N3CampaignError("panel cold-cycle flag must be boolean")
    if panel["cold_cycle_required"]:
        dwell = _require_nonnegative_number(
            panel["minimum_measured_off_seconds"],
            label="panel-cold minimum measured off seconds",
        )
        if dwell <= 0 or panel["may_remain_on_before_session"] is not False:
            raise N3CampaignError("panel-cold session requires a positive dwell and J2 off")
        _require_sha256(
            panel["profile_review_artifact_sha256"],
            label="panel-cold profile review artifact",
        )
    elif panel != {
        "cold_cycle_required": False,
        "minimum_measured_off_seconds": None,
        "profile_review_artifact_sha256": None,
        "may_remain_on_before_session": True,
    }:
        raise N3CampaignError("ordinary N3 session must not require or imply a J2 cycle")
    return root


def build_measurement_asset_registry(
    *,
    timing_clock_asset_sha256: Optional[str] = None,
    temperature_sensor_asset_sha256: Optional[str] = None,
    temperature_calibration_asset_sha256: Optional[str] = None,
    temperature_location_asset_sha256: Optional[str] = None,
    camera_body_asset_sha256: Optional[str] = None,
    camera_lens_asset_sha256: Optional[str] = None,
    camera_mount_asset_sha256: Optional[str] = None,
    camera_capture_config_sha256: Optional[str] = None,
    camera_crop_asset_sha256: Optional[str] = None,
    illumination_asset_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Build an asset registry; null identities are valid but hardware-blocking."""

    _n2_manifest()
    timing_contract = _driver_timing_contract()
    registry = {
        "schema_version": SCHEMA_VERSION,
        "kind": ASSET_REGISTRY_KIND,
        "timing": {
            "driver_timing_contract": timing_contract,
            "driver_timing_contract_sha256": _sha256(timing_contract),
            "clock_asset_sha256": timing_clock_asset_sha256,
            "required_fields": [
                "queue_delay_ms",
                "job_duration_ms",
                "driver_total_ms",
                "cs1_upload_ms",
                "cs2_upload_ms",
                "pon_ms",
                "drf_ms",
                "pof_ms",
                "post_psr_ms",
            ],
        },
        "temperature": {
            "units": "degC",
            "sensor_asset_sha256": temperature_sensor_asset_sha256,
            "calibration_asset_sha256": temperature_calibration_asset_sha256,
            "measurement_location_asset_sha256": temperature_location_asset_sha256,
            "required_sample_points": ["pre_map", "post_map", "post_target", "session_max"],
        },
        "camera": {
            "fixed_across_campaign": True,
            "raw_capture_required": True,
            "manual_exposure_required": True,
            "manual_white_balance_required": True,
            "body_asset_sha256": camera_body_asset_sha256,
            "lens_asset_sha256": camera_lens_asset_sha256,
            "mount_asset_sha256": camera_mount_asset_sha256,
            "capture_config_sha256": camera_capture_config_sha256,
            "crop_asset_sha256": camera_crop_asset_sha256,
            "illumination_asset_sha256": illumination_asset_sha256,
        },
    }
    _validate_asset_registry(registry)
    return registry


def _validate_asset_registry(value: Any) -> Mapping[str, Any]:
    root = _require_exact_keys(
        value,
        label="measurement asset registry",
        keys={"schema_version", "kind", "timing", "temperature", "camera"},
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != ASSET_REGISTRY_KIND:
        raise N3CampaignError("measurement asset registry schema or kind is invalid")
    timing = _require_exact_keys(
        root["timing"],
        label="measurement timing registry",
        keys={
            "driver_timing_contract",
            "driver_timing_contract_sha256",
            "clock_asset_sha256",
            "required_fields",
        },
    )
    _n2_manifest()
    if timing["driver_timing_contract"] != _driver_timing_contract():
        raise N3CampaignError("measurement timing contract differs from frozen RC2G")
    if timing["driver_timing_contract_sha256"] != _sha256(
        timing["driver_timing_contract"]
    ):
        raise N3CampaignError("measurement timing contract identity is invalid")
    _require_sha256(timing["clock_asset_sha256"], label="timing clock asset", nullable=True)
    expected_timing_fields = [
        "queue_delay_ms",
        "job_duration_ms",
        "driver_total_ms",
        "cs1_upload_ms",
        "cs2_upload_ms",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
    ]
    if timing["required_fields"] != expected_timing_fields:
        raise N3CampaignError("measurement timing fields changed")
    temperature = _require_exact_keys(
        root["temperature"],
        label="temperature asset registry",
        keys={
            "units",
            "sensor_asset_sha256",
            "calibration_asset_sha256",
            "measurement_location_asset_sha256",
            "required_sample_points",
        },
    )
    if temperature["units"] != "degC" or temperature["required_sample_points"] != [
        "pre_map",
        "post_map",
        "post_target",
        "session_max",
    ]:
        raise N3CampaignError("temperature measurement contract changed")
    for field in (
        "sensor_asset_sha256",
        "calibration_asset_sha256",
        "measurement_location_asset_sha256",
    ):
        _require_sha256(temperature[field], label=f"temperature {field}", nullable=True)
    camera = _require_exact_keys(
        root["camera"],
        label="camera asset registry",
        keys={
            "fixed_across_campaign",
            "raw_capture_required",
            "manual_exposure_required",
            "manual_white_balance_required",
            "body_asset_sha256",
            "lens_asset_sha256",
            "mount_asset_sha256",
            "capture_config_sha256",
            "crop_asset_sha256",
            "illumination_asset_sha256",
        },
    )
    for field in (
        "fixed_across_campaign",
        "raw_capture_required",
        "manual_exposure_required",
        "manual_white_balance_required",
    ):
        if camera[field] is not True:
            raise N3CampaignError(f"camera {field} must remain true")
    for field in (
        "body_asset_sha256",
        "lens_asset_sha256",
        "mount_asset_sha256",
        "capture_config_sha256",
        "crop_asset_sha256",
        "illumination_asset_sha256",
    ):
        _require_sha256(camera[field], label=f"camera {field}", nullable=True)
    return root


def measurement_asset_blockers(registry: Mapping[str, Any]) -> list[str]:
    """Return missing registration identities without treating software as unready."""

    root = _validate_asset_registry(registry)
    blockers: list[str] = []
    if root["timing"]["clock_asset_sha256"] is None:
        blockers.append("missing_asset:timing.clock_asset_sha256")
    for field in (
        "sensor_asset_sha256",
        "calibration_asset_sha256",
        "measurement_location_asset_sha256",
    ):
        if root["temperature"][field] is None:
            blockers.append(f"missing_asset:temperature.{field}")
    for field in (
        "body_asset_sha256",
        "lens_asset_sha256",
        "mount_asset_sha256",
        "capture_config_sha256",
        "crop_asset_sha256",
        "illumination_asset_sha256",
    ):
        if root["camera"][field] is None:
            blockers.append(f"missing_asset:camera.{field}")
    return blockers


def _power_mode(regime: Mapping[str, Any]) -> tuple[str, Optional[float]]:
    panel = regime["panel_j2"]
    if panel["cold_cycle_required"]:
        return "panel_cold_cycle", float(panel["minimum_measured_off_seconds"])
    return "controller_fresh_boot", None


def _build_pair(
    *,
    campaign_id: str,
    session_id: str,
    cell_id: str,
    action_prefix: str,
    map_frame: Mapping[str, Any],
    target_frame: Mapping[str, Any],
    regime: Mapping[str, Any],
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    map_action = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id=f"{action_prefix}-map",
        phase="map-primer",
        frame=map_frame,
    )
    target_action = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id=f"{action_prefix}-target",
        phase="target",
        frame=target_frame,
        prior_action_identity_sha256=map_action["action_identity_sha256"],
        prior_scope="same_cell",
        minimum_interval_since_prior_seconds=minimum_interval_seconds,
    )
    power_mode, dwell = _power_mode(regime)
    session = build_session_contract(
        session_id=session_id,
        cell_id=cell_id,
        power_mode=power_mode,
        planned_cooldown_seconds=planned_cooldown_seconds,
        final_power_off_required=False,
        action_identity_sha256s=[
            map_action["action_identity_sha256"],
            target_action["action_identity_sha256"],
        ],
        minimum_panel_power_off_seconds=dwell,
    )
    route = {
        "session_id": session_id,
        "cell_id": cell_id,
        "map_action_identity_sha256": map_action["action_identity_sha256"],
        "target_action_identity_sha256": target_action["action_identity_sha256"],
    }
    return [map_action, target_action], session, route


def _seal_p0_campaign(
    *,
    campaign_id: str,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    actions: Sequence[Mapping[str, Any]],
    sessions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return seal_campaign_contract(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "mf1750-visible-refresh-campaign-contract",
            "campaign_id": campaign_id,
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "actions": _snapshot(actions),
            "sessions": _snapshot(sessions),
            "classification": dict(_P0_CLASSIFICATION),
        }
    )


def _base_contract(
    *,
    n2: Mapping[str, Any],
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    regime: Mapping[str, Any],
    assets: Mapping[str, Any],
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    _validate_session_regime(regime)
    _validate_asset_registry(assets)
    interval = _require_nonnegative_number(
        minimum_interval_seconds,
        label="minimum_interval_seconds",
    )
    cooldown = _require_nonnegative_number(
        planned_cooldown_seconds,
        label="planned_cooldown_seconds",
    )
    return {
        "source_n2": _source_record(n2),
        "panel": _snapshot(panel),
        "firmware": _snapshot(firmware),
        "session_regime": _snapshot(regime),
        "measurement_asset_registry": _snapshot(assets),
        "measurement_asset_registry_sha256": _sha256(assets),
        "schedule": {
            "minimum_interval_since_map_seconds": interval,
            "planned_cooldown_after_session_seconds": cooldown,
            "automatic_advance": False,
        },
        "classification": {
            "offline_compiled": True,
            "software_ready": True,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "authorization_created": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
        "hardware_readiness": {
            "ready": False,
            "asset_blockers": measurement_asset_blockers(assets),
            "limit_profile_evaluated": False,
            "runtime_gates_evaluated": False,
            "blockers": [
                *measurement_asset_blockers(assets),
                "n2_winner_or_n3b_block_not_selected_for_execution",
                "reviewed_supplier_limit_profile_not_evaluated",
                "current_runtime_gates_and_exact_authorization_not_evaluated",
            ],
        },
    }


def _candidate_by_cell(n2: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cells = {cell["cell_id"]: cell for cell in n2["cells"]}
    if tuple(cells) != N3_CELLS:
        raise N3CampaignError("N2 candidate cells changed")
    if any(
        cell["candidate"]["classification"]["natural_photo_input"] is not True
        for cell in cells.values()
    ):
        raise N3CampaignError("N3 candidate branch is not natural-photo input")
    return cells


def _is_frozen_default(manifest: Mapping[str, Any]) -> bool:
    n2 = _n2_manifest()
    p0 = n2["p0_campaign_contract"]
    return (
        manifest.get("panel") == p0["panel"]
        and manifest.get("firmware") == p0["firmware"]
        and manifest.get("session_regime") == ordinary_session_regime()
        and manifest.get("measurement_asset_registry")
        == build_measurement_asset_registry()
        and manifest.get("schedule")
        == {
            "minimum_interval_since_map_seconds": 0.0,
            "planned_cooldown_after_session_seconds": 0.0,
            "automatic_advance": False,
        }
    )


def _validate_frozen_default_identity(manifest: Mapping[str, Any]) -> None:
    if not _is_frozen_default(manifest):
        return
    if manifest["kind"] == N3A_KIND:
        canonical = EXPECTED_FROZEN_N3A_CANONICAL_SHA256
        file_sha = EXPECTED_FROZEN_N3A_FILE_SHA256
    else:
        canonical = EXPECTED_FROZEN_N3B_CANONICAL_SHA256
        file_sha = EXPECTED_FROZEN_N3B_FILE_SHA256
    if (
        manifest["integrity"]["canonical_sha256"] != canonical
        or _sha256(canonical_json_bytes(manifest)) != file_sha
    ):
        raise N3CampaignError("frozen default N3 manifest identity changed")


def compile_frozen_n3a_manifest() -> dict[str, Any]:
    """Compile the SHA-frozen default N3A planning manifest."""

    p0 = _n2_manifest()["p0_campaign_contract"]
    return compile_n3a_manifest(panel=p0["panel"], firmware=p0["firmware"])


def compile_frozen_n3b_manifest() -> dict[str, Any]:
    """Compile the SHA-frozen default N3B planning manifest."""

    p0 = _n2_manifest()["p0_campaign_contract"]
    return compile_n3b_manifest(panel=p0["panel"], firmware=p0["firmware"])


def compile_n3a_manifest(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    session_regime: Optional[Mapping[str, Any]] = None,
    measurement_assets: Optional[Mapping[str, Any]] = None,
    minimum_interval_seconds: int | float = 0,
    planned_cooldown_seconds: int | float = 0,
) -> dict[str, Any]:
    """Compile all Q1--Q4 winner branches and repeat-2/3/4 templates."""

    n2 = _n2_manifest()
    regime = _snapshot(session_regime or ordinary_session_regime())
    assets = _snapshot(measurement_assets or build_measurement_asset_registry())
    base = _base_contract(
        n2=n2,
        panel=panel,
        firmware=firmware,
        regime=regime,
        assets=assets,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    map_frame = _p0_frame_from_map(n2)
    cells = _candidate_by_cell(n2)
    branches: list[dict[str, Any]] = []
    for winner_cell_id in N3_CELLS:
        n2_cell = cells[winner_cell_id]
        target_frame = _p0_frame_from_candidate(n2_cell["candidate"])
        templates: list[dict[str, Any]] = []
        for repeat_count in N3A_REPEAT_COUNTS:
            branch_slug = winner_cell_id.lower()
            campaign_id = f"g1-s1-n3a-{branch_slug}-repeat{repeat_count}-v1"
            actions: list[dict[str, Any]] = []
            sessions: list[dict[str, Any]] = []
            routes: list[dict[str, Any]] = []
            for ordinal in range(1, repeat_count + 1):
                session_id = f"n3a-{branch_slug}-r{repeat_count}-session{ordinal}"
                cell_id = f"n3a-{branch_slug}-r{repeat_count}-repeat{ordinal}"
                prefix = f"n3a-{branch_slug}-r{repeat_count}-repeat{ordinal}"
                pair, session, route = _build_pair(
                    campaign_id=campaign_id,
                    session_id=session_id,
                    cell_id=cell_id,
                    action_prefix=prefix,
                    map_frame=map_frame,
                    target_frame=target_frame,
                    regime=regime,
                    minimum_interval_seconds=minimum_interval_seconds,
                    planned_cooldown_seconds=planned_cooldown_seconds,
                )
                actions.extend(pair)
                sessions.append(session)
                routes.append(
                    {
                        **route,
                        "repeat_ordinal": ordinal,
                        "winner_cell_id": winner_cell_id,
                    }
                )
            campaign = _seal_p0_campaign(
                campaign_id=campaign_id,
                panel=panel,
                firmware=firmware,
                actions=actions,
                sessions=sessions,
            )
            templates.append(
                {
                    "template_id": f"n3a-{branch_slug}-repeat{repeat_count}",
                    "repeat_count": repeat_count,
                    "routes": routes,
                    "p0_campaign": campaign,
                }
            )
        branches.append(
            {
                "branch_id": f"n3a-winner-{winner_cell_id.lower()}",
                "winner_cell_id": winner_cell_id,
                "algorithm": n2_cell["algorithm"],
                "candidate": _snapshot(n2_cell["candidate"]),
                "natural_photo_input": True,
                "repeat_templates": templates,
            }
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": N3A_KIND,
        "study": "N3A",
        "purpose": "winner-repeatability-after-independent-own-map-priors",
        **base,
        "repeat_contract": {
            "winner_branch_count": 4,
            "repeat_counts": list(N3A_REPEAT_COUNTS),
            "own_map_before_every_target": True,
            "cross_branch_replay_allowed": False,
            "cross_repeat_template_replay_allowed": False,
            "cross_repeat_ordinal_replay_allowed": False,
            "percentile_rule": "n-less-than-10-report-maximum-observed-not-p95-or-p99",
        },
        "branches": branches,
    }
    manifest = {**unsigned, "integrity": _integrity(unsigned, N3A_HASH_SCOPE)}
    validate_n3a_manifest(manifest)
    return manifest


def _seeded_labels(seed: str) -> list[str]:
    return sorted(N3_CELLS, key=lambda label: hashlib.sha256(f"{seed}:{label}".encode()).digest())


def balanced_orders(seed: str = N3B_FIXED_SEED) -> list[list[str]]:
    """Return a deterministic even-Williams square for the four N2 cells."""

    if not isinstance(seed, str) or not seed:
        raise N3CampaignError("N3B order seed must be a non-empty string")
    labels = _seeded_labels(seed)
    base_offsets = (0, 1, 3, 2)
    return [
        [labels[(offset + row) % 4] for offset in base_offsets]
        for row in range(4)
    ]


def _balance_evidence(orders: Sequence[Sequence[str]]) -> dict[str, Any]:
    position_counts = {
        cell: [sum(order[position] == cell for order in orders) for position in range(4)]
        for cell in N3_CELLS
    }
    pairs = [
        f"{order[index]}->{order[index + 1]}"
        for order in orders
        for index in range(3)
    ]
    pair_counts = {pair: pairs.count(pair) for pair in sorted(set(pairs))}
    expected_pairs = {f"{left}->{right}" for left in N3_CELLS for right in N3_CELLS if left != right}
    if (
        any(counts != [1, 1, 1, 1] for counts in position_counts.values())
        or set(pair_counts) != expected_pairs
        or any(count != 1 for count in pair_counts.values())
    ):
        raise N3CampaignError("N3B fixed order is not position/predecessor balanced")
    return {
        "position_counts_by_candidate": position_counts,
        "administrative_predecessor_pair_counts": pair_counts,
        "position_balanced": True,
        "administrative_predecessor_balanced": True,
        "direct_target_carryover_measured": False,
        "direct_target_carryover_reserved_for": "N8",
    }


def compile_n3b_manifest(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    session_regime: Optional[Mapping[str, Any]] = None,
    measurement_assets: Optional[Mapping[str, Any]] = None,
    minimum_interval_seconds: int | float = 0,
    planned_cooldown_seconds: int | float = 0,
    order_seed: str = N3B_FIXED_SEED,
) -> dict[str, Any]:
    """Compile four fixed-seed balanced blocks with an own MAP per target."""

    if order_seed != N3B_FIXED_SEED:
        raise N3CampaignError("N3B order seed is frozen; alternate seeds require a new schema")
    n2 = _n2_manifest()
    regime = _snapshot(session_regime or ordinary_session_regime())
    assets = _snapshot(measurement_assets or build_measurement_asset_registry())
    base = _base_contract(
        n2=n2,
        panel=panel,
        firmware=firmware,
        regime=regime,
        assets=assets,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    map_frame = _p0_frame_from_map(n2)
    cells = _candidate_by_cell(n2)
    orders = balanced_orders(order_seed)
    branches: list[dict[str, Any]] = []
    for block_index, order in enumerate(orders, start=1):
        campaign_id = f"g1-s1-n3b-balanced-block{block_index}-v1"
        actions: list[dict[str, Any]] = []
        sessions: list[dict[str, Any]] = []
        routes: list[dict[str, Any]] = []
        for position, candidate_cell_id in enumerate(order, start=1):
            target_frame = _p0_frame_from_candidate(cells[candidate_cell_id]["candidate"])
            session_id = f"n3b-block{block_index}-position{position}"
            cell_id = f"n3b-b{block_index}-p{position}-{candidate_cell_id.lower()}"
            prefix = f"n3b-b{block_index}-p{position}-{candidate_cell_id.lower()}"
            pair, session, route = _build_pair(
                campaign_id=campaign_id,
                session_id=session_id,
                cell_id=cell_id,
                action_prefix=prefix,
                map_frame=map_frame,
                target_frame=target_frame,
                regime=regime,
                minimum_interval_seconds=minimum_interval_seconds,
                planned_cooldown_seconds=planned_cooldown_seconds,
            )
            actions.extend(pair)
            sessions.append(session)
            routes.append(
                {
                    **route,
                    "session_position": position,
                    "candidate_cell_id": candidate_cell_id,
                    "previous_target_used_as_prior": False,
                }
            )
        branches.append(
            {
                "branch_id": f"n3b-balanced-block-{block_index}",
                "block_index": block_index,
                "candidate_order": list(order),
                "routes": routes,
                "p0_campaign": _seal_p0_campaign(
                    campaign_id=campaign_id,
                    panel=panel,
                    firmware=firmware,
                    actions=actions,
                    sessions=sessions,
                ),
            }
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": N3B_KIND,
        "study": "N3B",
        "purpose": "balanced-session-order-effect-with-own-map-prior-per-target",
        **base,
        "order_contract": {
            "fixed_seed": order_seed,
            "algorithm": N3B_ORDER_ALGORITHM,
            "block_count": 4,
            "candidate_count_per_block": 4,
            "orders": orders,
            "own_map_before_every_target": True,
            "previous_target_as_prior": False,
            "cross_block_replay_allowed": False,
            "cross_position_replay_allowed": False,
            "carryover_interpretation": "not-tested-because-own-map-intervenes",
            "carryover_followup": "N8",
            "balance_evidence": _balance_evidence(orders),
        },
        "branches": branches,
    }
    manifest = {**unsigned, "integrity": _integrity(unsigned, N3B_HASH_SCOPE)}
    validate_n3b_manifest(manifest)
    return manifest


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _validate_integrity(root: Mapping[str, Any], *, scope: str, label: str) -> None:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise N3CampaignError(f"{label} integrity is missing")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned, scope):
        raise N3CampaignError(f"{label} canonical integrity is invalid")


def _validate_base(root: Mapping[str, Any]) -> None:
    source = root.get("source_n2")
    if source != _source_record(_n2_manifest()):
        raise N3CampaignError("N3 source N2 identity is invalid")
    _validate_session_regime(root.get("session_regime"))
    assets = _validate_asset_registry(root.get("measurement_asset_registry"))
    if root.get("measurement_asset_registry_sha256") != _sha256(assets):
        raise N3CampaignError("N3 measurement asset registry identity is invalid")
    schedule = root.get("schedule")
    if not isinstance(schedule, Mapping) or set(schedule) != {
        "minimum_interval_since_map_seconds",
        "planned_cooldown_after_session_seconds",
        "automatic_advance",
    }:
        raise N3CampaignError("N3 schedule shape is invalid")
    _require_nonnegative_number(
        schedule["minimum_interval_since_map_seconds"],
        label="N3 minimum interval",
    )
    _require_nonnegative_number(
        schedule["planned_cooldown_after_session_seconds"],
        label="N3 planned cooldown",
    )
    if schedule["automatic_advance"] is not False:
        raise N3CampaignError("N3 automatic advance must remain disabled")
    expected_classification = {
        "offline_compiled": True,
        "software_ready": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    if root.get("classification") != expected_classification:
        raise N3CampaignError("N3 offline classification changed")
    readiness = root.get("hardware_readiness")
    if not isinstance(readiness, Mapping) or readiness.get("ready") is not False:
        raise N3CampaignError("N3 manifest must not claim hardware readiness")
    if readiness.get("asset_blockers") != measurement_asset_blockers(assets):
        raise N3CampaignError("N3 asset blocker list is inconsistent")
    blockers = readiness.get("blockers")
    if not isinstance(blockers, list) or not {
        "reviewed_supplier_limit_profile_not_evaluated",
        "current_runtime_gates_and_exact_authorization_not_evaluated",
    }.issubset(blockers):
        raise N3CampaignError("N3 readiness blockers are incomplete")


def _validate_route_campaign(
    *,
    campaign: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    regime: Mapping[str, Any],
    expected_map_frame: Mapping[str, Any],
    expected_target_cells: Sequence[str],
    cells: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    try:
        root = validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N3CampaignError(f"embedded P0 campaign is invalid: {error}") from error
    if len(root["actions"]) != 2 * len(routes) or len(root["sessions"]) != len(routes):
        raise N3CampaignError("N3 routes and embedded P0 campaign counts differ")
    actions = {action["action_identity_sha256"]: action for action in root["actions"]}
    sessions = {session["session_id"]: session for session in root["sessions"]}
    global_shas: list[str] = []
    global_ids: list[str] = []
    global_claims: list[str] = []
    power_mode, dwell = _power_mode(regime)
    for route, expected_cell_id in zip(routes, expected_target_cells):
        if not isinstance(route, Mapping):
            raise N3CampaignError("N3 route must be an object")
        map_sha = route.get("map_action_identity_sha256")
        target_sha = route.get("target_action_identity_sha256")
        if map_sha not in actions or target_sha not in actions or map_sha == target_sha:
            raise N3CampaignError("N3 route action binding is invalid")
        map_action = actions[map_sha]
        target_action = actions[target_sha]
        session = sessions.get(route.get("session_id"))
        if session is None or session["cell_id"] != route.get("cell_id"):
            raise N3CampaignError("N3 route session binding is invalid")
        if session["action_identity_sha256s"] != [map_sha, target_sha]:
            raise N3CampaignError("N3 route must be exactly MAP then target")
        if (
            session["power_mode"] != power_mode
            or session["minimum_panel_power_off_seconds"] != dwell
            or session["final_power_off_required"] is not False
        ):
            raise N3CampaignError("N3 route power regime is inconsistent")
        map_identity = map_action["identity"]
        target_identity = target_action["identity"]
        if (
            map_identity["phase"] != "map-primer"
            or map_identity["frame"] != expected_map_frame
            or target_identity["phase"] != "target"
            or target_identity["prior"]
            != {
                "action_identity_sha256": map_sha,
                "scope": "same_cell",
                "required_result_state": "PASS",
            }
        ):
            raise N3CampaignError("N3 own-MAP prior contract is invalid")
        expected_target_frame = _p0_frame_from_candidate(cells[expected_cell_id]["candidate"])
        if target_identity["frame"] != expected_target_frame:
            raise N3CampaignError("N3 route targets the wrong N2 candidate")
        for action in (map_action, target_action):
            global_shas.append(action["action_identity_sha256"])
            global_ids.append(action["identity"]["action_id"])
            global_claims.append(action["claim"]["filename"])
    return global_shas, global_ids, global_claims


def _require_global_uniqueness(
    shas: Sequence[str], ids: Sequence[str], claims: Sequence[str]
) -> None:
    if not (len(shas) == len(ids) == len(claims)):
        raise N3CampaignError("N3 action uniqueness lists differ in size")
    if not (
        len(set(shas)) == len(shas)
        and len(set(ids)) == len(ids)
        and len(set(claims)) == len(claims)
    ):
        raise N3CampaignError("N3 action replay identity is duplicated across a branch or repeat")


def validate_n3a_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _require_exact_keys(
        manifest,
        label="N3A manifest",
        keys={
            "schema_version",
            "kind",
            "study",
            "purpose",
            "source_n2",
            "panel",
            "firmware",
            "session_regime",
            "measurement_asset_registry",
            "measurement_asset_registry_sha256",
            "schedule",
            "classification",
            "hardware_readiness",
            "repeat_contract",
            "branches",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != N3A_KIND or root["study"] != "N3A":
        raise N3CampaignError("N3A schema, kind, or study is invalid")
    _validate_base(root)
    branches = root["branches"]
    if not isinstance(branches, list) or len(branches) != 4:
        raise N3CampaignError("N3A must contain four winner branches")
    cells = _candidate_by_cell(_n2_manifest())
    map_frame = _p0_frame_from_map(_n2_manifest())
    shas: list[str] = []
    ids: list[str] = []
    claims: list[str] = []
    for branch, winner_cell in zip(branches, N3_CELLS):
        if (
            branch.get("branch_id") != f"n3a-winner-{winner_cell.lower()}"
            or branch.get("winner_cell_id") != winner_cell
            or branch.get("algorithm") != cells[winner_cell]["algorithm"]
            or branch.get("candidate") != cells[winner_cell]["candidate"]
            or branch.get("natural_photo_input") is not True
        ):
            raise N3CampaignError("N3A winner branch identity is invalid")
        templates = branch.get("repeat_templates")
        if not isinstance(templates, list) or len(templates) != 3:
            raise N3CampaignError("N3A branch must contain repeat-2/3/4 templates")
        for template, count in zip(templates, N3A_REPEAT_COUNTS):
            if (
                template.get("template_id") != f"n3a-{winner_cell.lower()}-repeat{count}"
                or template.get("repeat_count") != count
            ):
                raise N3CampaignError("N3A repeat template identity is invalid")
            routes = template.get("routes")
            if not isinstance(routes, list) or len(routes) != count:
                raise N3CampaignError("N3A route count differs from repeat count")
            if [route.get("repeat_ordinal") for route in routes] != list(range(1, count + 1)):
                raise N3CampaignError("N3A repeat ordinals are invalid")
            if any(route.get("winner_cell_id") != winner_cell for route in routes):
                raise N3CampaignError("N3A route crosses a winner branch")
            found = _validate_route_campaign(
                campaign=template.get("p0_campaign"),
                routes=routes,
                regime=root["session_regime"],
                expected_map_frame=map_frame,
                expected_target_cells=[winner_cell] * count,
                cells=cells,
            )
            shas.extend(found[0])
            ids.extend(found[1])
            claims.extend(found[2])
    _require_global_uniqueness(shas, ids, claims)
    contract = root["repeat_contract"]
    if not isinstance(contract, Mapping) or contract.get("repeat_counts") != [2, 3, 4]:
        raise N3CampaignError("N3A repeat contract changed")
    _validate_integrity(root, scope=N3A_HASH_SCOPE, label="N3A manifest")
    _validate_frozen_default_identity(root)
    return root


def validate_n3b_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _require_exact_keys(
        manifest,
        label="N3B manifest",
        keys={
            "schema_version",
            "kind",
            "study",
            "purpose",
            "source_n2",
            "panel",
            "firmware",
            "session_regime",
            "measurement_asset_registry",
            "measurement_asset_registry_sha256",
            "schedule",
            "classification",
            "hardware_readiness",
            "order_contract",
            "branches",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != N3B_KIND or root["study"] != "N3B":
        raise N3CampaignError("N3B schema, kind, or study is invalid")
    _validate_base(root)
    order_contract = root["order_contract"]
    if not isinstance(order_contract, Mapping):
        raise N3CampaignError("N3B order contract is missing")
    orders = balanced_orders()
    if (
        order_contract.get("fixed_seed") != N3B_FIXED_SEED
        or order_contract.get("algorithm") != N3B_ORDER_ALGORITHM
        or order_contract.get("orders") != orders
        or order_contract.get("previous_target_as_prior") is not False
        or order_contract.get("carryover_followup") != "N8"
        or order_contract.get("balance_evidence") != _balance_evidence(orders)
    ):
        raise N3CampaignError("N3B frozen order/carryover contract changed")
    branches = root["branches"]
    if not isinstance(branches, list) or len(branches) != 4:
        raise N3CampaignError("N3B must contain four balanced blocks")
    cells = _candidate_by_cell(_n2_manifest())
    map_frame = _p0_frame_from_map(_n2_manifest())
    shas: list[str] = []
    ids: list[str] = []
    claims: list[str] = []
    for index, (branch, order) in enumerate(zip(branches, orders), start=1):
        if (
            branch.get("branch_id") != f"n3b-balanced-block-{index}"
            or branch.get("block_index") != index
            or branch.get("candidate_order") != order
        ):
            raise N3CampaignError("N3B balanced-block identity is invalid")
        routes = branch.get("routes")
        if not isinstance(routes, list) or len(routes) != 4:
            raise N3CampaignError("N3B block must contain four routes")
        if [route.get("session_position") for route in routes] != [1, 2, 3, 4]:
            raise N3CampaignError("N3B session positions are invalid")
        if [route.get("candidate_cell_id") for route in routes] != order:
            raise N3CampaignError("N3B route order differs from frozen block")
        if any(route.get("previous_target_used_as_prior") is not False for route in routes):
            raise N3CampaignError("N3B must not use a previous target as prior")
        found = _validate_route_campaign(
            campaign=branch.get("p0_campaign"),
            routes=routes,
            regime=root["session_regime"],
            expected_map_frame=map_frame,
            expected_target_cells=order,
            cells=cells,
        )
        shas.extend(found[0])
        ids.extend(found[1])
        claims.extend(found[2])
    _require_global_uniqueness(shas, ids, claims)
    _validate_integrity(root, scope=N3B_HASH_SCOPE, label="N3B manifest")
    _validate_frozen_default_identity(root)
    return root


def _action_route_matches(
    manifest: Mapping[str, Any], action_identity_sha256: str
) -> list[tuple[Mapping[str, Any], Mapping[str, Any], str]]:
    matches: list[tuple[Mapping[str, Any], Mapping[str, Any], str]] = []
    if manifest["kind"] == N3A_KIND:
        for branch in manifest["branches"]:
            for template in branch["repeat_templates"]:
                for route in template["routes"]:
                    if action_identity_sha256 in {
                        route["map_action_identity_sha256"],
                        route["target_action_identity_sha256"],
                    }:
                        matches.append((template["p0_campaign"], route, branch["branch_id"]))
    else:
        for branch in manifest["branches"]:
            for route in branch["routes"]:
                if action_identity_sha256 in {
                    route["map_action_identity_sha256"],
                    route["target_action_identity_sha256"],
                }:
                    matches.append((branch["p0_campaign"], route, branch["branch_id"]))
    return matches


def describe_n3_action(
    manifest: Mapping[str, Any],
    *,
    action_identity_sha256: str,
    limit_profile: Mapping[str, Any],
    evaluated_at: str,
    prior_result: Optional[Mapping[str, Any]] = None,
    prior_result_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Describe one selected action with zero I/O, claim, or authorization."""

    if manifest.get("kind") == N3A_KIND:
        root = validate_n3a_manifest(manifest)
    elif manifest.get("kind") == N3B_KIND:
        root = validate_n3b_manifest(manifest)
    else:
        raise N3CampaignError("unsupported N3 manifest kind")
    requested_sha = _require_sha256(
        action_identity_sha256,
        label="N3 requested action identity",
    )
    matches = _action_route_matches(root, str(requested_sha))
    if len(matches) != 1:
        raise N3CampaignError("requested action is not unique in this N3 manifest")
    campaign, route, branch_id = matches[0]
    try:
        p0_description = describe_action_offline(
            campaign,
            action_identity_sha256=str(requested_sha),
            limit_profile=limit_profile,
            evaluated_at=evaluated_at,
            prior_result=prior_result,
            prior_result_sha256=prior_result_sha256,
        )
    except CampaignContractError as error:
        raise N3CampaignError(f"P0 describe rejected the N3 action: {error}") from error
    asset_blockers = measurement_asset_blockers(root["measurement_asset_registry"])
    blockers = list(
        dict.fromkeys(
            [
                *asset_blockers,
                *p0_description["blockers"],
            ]
        )
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": N3_DESCRIPTION_KIND,
        "mode": "describe-only",
        "study": root["study"],
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "branch_id": branch_id,
        "route": _snapshot(route),
        "software_ready": True,
        "measurement_assets_ready": not asset_blockers,
        "contract_ready": not asset_blockers and p0_description["contract_ready"],
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
        "p0_description": p0_description,
    }
    description = {
        **unsigned,
        "integrity": _integrity(unsigned, N3_DESCRIPTION_HASH_SCOPE),
    }
    validate_n3_description(description)
    return description


def validate_n3_description(description: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _require_exact_keys(
        description,
        label="N3 description",
        keys={
            "schema_version",
            "kind",
            "mode",
            "study",
            "manifest_canonical_sha256",
            "branch_id",
            "route",
            "software_ready",
            "measurement_assets_ready",
            "contract_ready",
            "hardware_ready",
            "hardware_execution_authorized",
            "authorization_created",
            "claim_created",
            "network_io_performed",
            "device_io_performed",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
            "blockers",
            "p0_description",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != N3_DESCRIPTION_KIND
        or root["mode"] != "describe-only"
        or root["study"] not in {"N3A", "N3B"}
        or root["software_ready"] is not True
    ):
        raise N3CampaignError("N3 description identity is invalid")
    _require_sha256(root["manifest_canonical_sha256"], label="N3 manifest identity")
    fixed_false = (
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
    )
    if any(root[field] is not False for field in fixed_false):
        raise N3CampaignError("N3 describe-only flags must remain false")
    if not isinstance(root["blockers"], list) or len(root["blockers"]) != len(
        set(root["blockers"])
    ):
        raise N3CampaignError("N3 description blockers are invalid")
    p0 = root["p0_description"]
    if not isinstance(p0, Mapping) or any(
        p0.get(field) is not False
        for field in (
            "hardware_ready",
            "hardware_execution_authorized",
            "authorization_created",
            "claim_created",
            "network_io_performed",
            "device_io_performed",
        )
    ):
        raise N3CampaignError("embedded P0 description is not offline-only")
    expected_contract = root["measurement_assets_ready"] and p0.get("contract_ready") is True
    if root["contract_ready"] != expected_contract:
        raise N3CampaignError("N3 description readiness is inconsistent")
    _validate_integrity(root, scope=N3_DESCRIPTION_HASH_SCOPE, label="N3 description")
    return root


__all__ = [
    "ASSET_REGISTRY_KIND",
    "N3A_KIND",
    "N3A_REPEAT_COUNTS",
    "N3B_FIXED_SEED",
    "N3B_KIND",
    "EXPECTED_FROZEN_N3A_CANONICAL_SHA256",
    "EXPECTED_FROZEN_N3A_FILE_SHA256",
    "EXPECTED_FROZEN_N3B_CANONICAL_SHA256",
    "EXPECTED_FROZEN_N3B_FILE_SHA256",
    "N3CampaignError",
    "balanced_orders",
    "build_measurement_asset_registry",
    "compile_n3a_manifest",
    "compile_n3b_manifest",
    "compile_frozen_n3a_manifest",
    "compile_frozen_n3b_manifest",
    "describe_n3_action",
    "measurement_asset_blockers",
    "ordinary_session_regime",
    "panel_cold_session_regime",
    "validate_n3_description",
    "validate_n3a_manifest",
    "validate_n3b_manifest",
]
