#!/usr/bin/env python3
"""Offline N3 deep-bundle validation and descriptive analysis.

The analyzer accepts only an exact execution plan plus finalized MAP/target
bundle pairs.  It replays the shared claim/profile/protocol/observation/
finalization/result validators before deriving session observations.  It
performs no device, network, claim, or authorization I/O.  Samples smaller
than ten report the maximum observed value and never label P95 or P99.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Optional, Sequence

from host.visible_refresh_campaign import (
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
    result_file_sha256,
    validate_result_record,
)
from tools.g1_s1_n3_campaign import (
    N3A_KIND,
    N3B_KIND,
    N3CampaignError,
    measurement_asset_blockers,
    validate_n3a_manifest,
    validate_n3b_manifest,
)
from tools import g1_s1_n3_execution_contract as execution


SCHEMA_VERSION = 1
OBSERVATION_KIND = "mf1750-g1-s1-n3-session-observation"
N3A_REPORT_KIND = "mf1750-g1-s1-n3a-repeatability-analysis"
N3B_REPORT_KIND = "mf1750-g1-s1-n3b-balanced-order-analysis"

OBSERVATION_HASH_SCOPE = (
    "entire N3 observation excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
REPORT_HASH_SCOPE = OBSERVATION_HASH_SCOPE.replace("observation", "analysis report")

TIMING_FIELDS = (
    "queue_delay_ms",
    "job_duration_ms",
    "driver_total_ms",
    "cs1_upload_ms",
    "cs2_upload_ms",
    "pon_ms",
    "drf_ms",
    "pof_ms",
    "post_psr_ms",
)
TEMPERATURE_FIELDS = ("pre_map", "post_map", "post_target", "session_max")
VISUAL_FIELDS = (
    "photo_difference_score",
    "photo_luminance_mean",
    "photo_luminance_standard_deviation",
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class N3AnalysisError(ValueError):
    """An N3 observation or analysis report failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3AnalysisError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _require_sha256(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise N3AnalysisError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
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
        raise N3AnalysisError(f"{label} must be a finite number{suffix}")
    result = float(value)
    if not math.isfinite(result):
        raise N3AnalysisError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N3AnalysisError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N3AnalysisError(f"{label} is above {maximum}")
    return result


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise N3AnalysisError(f"{label} must be an RFC3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise N3AnalysisError(f"{label} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise N3AnalysisError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _manifest_root(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        if manifest.get("kind") == N3A_KIND:
            return validate_n3a_manifest(manifest)
        if manifest.get("kind") == N3B_KIND:
            return validate_n3b_manifest(manifest)
    except N3CampaignError as error:
        raise N3AnalysisError(f"N3 manifest is invalid: {error}") from error
    raise N3AnalysisError("unsupported N3 manifest kind")


def _route_contexts(manifest: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    if manifest["kind"] == N3A_KIND:
        for branch in manifest["branches"]:
            for template in branch["repeat_templates"]:
                for route in template["routes"]:
                    yield {
                        "study": "N3A",
                        "branch_id": branch["branch_id"],
                        "template_id": template["template_id"],
                        "repeat_count": template["repeat_count"],
                        "repeat_ordinal": route["repeat_ordinal"],
                        "block_index": None,
                        "session_position": None,
                        "candidate_cell_id": route["winner_cell_id"],
                        "route": route,
                        "campaign": template["p0_campaign"],
                    }
    else:
        for branch in manifest["branches"]:
            for route in branch["routes"]:
                yield {
                    "study": "N3B",
                    "branch_id": branch["branch_id"],
                    "template_id": None,
                    "repeat_count": None,
                    "repeat_ordinal": None,
                    "block_index": branch["block_index"],
                    "session_position": route["session_position"],
                    "candidate_cell_id": route["candidate_cell_id"],
                    "route": route,
                    "campaign": branch["p0_campaign"],
                }


def _context_by_target(
    manifest: Mapping[str, Any], target_action_identity_sha256: str
) -> dict[str, Any]:
    matches = [
        context
        for context in _route_contexts(manifest)
        if context["route"]["target_action_identity_sha256"]
        == target_action_identity_sha256
    ]
    if len(matches) != 1:
        raise N3AnalysisError(
            "target action is not uniquely bound to one N3 branch/template/position"
        )
    return matches[0]


def _registered_assets(manifest: Mapping[str, Any]) -> dict[str, Any]:
    registry = manifest["measurement_asset_registry"]
    return {
        "registry_sha256": manifest["measurement_asset_registry_sha256"],
        "timing_clock_asset_sha256": registry["timing"]["clock_asset_sha256"],
        "temperature_sensor_asset_sha256": registry["temperature"][
            "sensor_asset_sha256"
        ],
        "temperature_calibration_asset_sha256": registry["temperature"][
            "calibration_asset_sha256"
        ],
        "temperature_location_asset_sha256": registry["temperature"][
            "measurement_location_asset_sha256"
        ],
        "camera_body_asset_sha256": registry["camera"]["body_asset_sha256"],
        "camera_lens_asset_sha256": registry["camera"]["lens_asset_sha256"],
        "camera_mount_asset_sha256": registry["camera"]["mount_asset_sha256"],
        "camera_capture_config_sha256": registry["camera"]["capture_config_sha256"],
        "camera_crop_asset_sha256": registry["camera"]["crop_asset_sha256"],
        "illumination_asset_sha256": registry["camera"]["illumination_asset_sha256"],
    }


def _validate_timing(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(TIMING_FIELDS):
        raise N3AnalysisError(f"{label} timing fields differ from the fixed registry")
    for field in TIMING_FIELDS:
        _number(value[field], label=f"{label}.{field}", minimum=0)
    return value


def _validate_temperature(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(TEMPERATURE_FIELDS):
        raise N3AnalysisError("temperature fields differ from the fixed registry")
    for field in TEMPERATURE_FIELDS:
        _number(
            value[field],
            label=f"temperature.{field}",
            minimum=-100,
            maximum=200,
        )
    if value["session_max"] < max(
        value["pre_map"], value["post_map"], value["post_target"]
    ):
        raise N3AnalysisError("session_max is lower than a recorded temperature sample")
    return value


def _validate_visual(value: Any) -> Mapping[str, Any]:
    expected = {
        "map_fidelity_pass",
        "target_fidelity_pass",
        *VISUAL_FIELDS,
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise N3AnalysisError("visual measurement fields differ from the fixed contract")
    for field in ("map_fidelity_pass", "target_fidelity_pass"):
        if type(value[field]) is not bool:
            raise N3AnalysisError(f"visual.{field} must be boolean")
    _number(
        value["photo_difference_score"],
        label="visual.photo_difference_score",
        minimum=0,
        nullable=True,
    )
    for field in ("photo_luminance_mean", "photo_luminance_standard_deviation"):
        _number(
            value[field],
            label=f"visual.{field}",
            minimum=0,
            maximum=255,
            nullable=True,
        )
    return value


def _pair_state(
    map_result: Mapping[str, Any],
    target_result: Mapping[str, Any],
    visual: Mapping[str, Any],
    continuity: Mapping[str, Any],
) -> str:
    if (
        map_result["state"] == ResultState.PASS.value
        and target_result["state"] == ResultState.PASS.value
        and visual["map_fidelity_pass"] is True
        and visual["target_fidelity_pass"] is True
        and all(value is False for value in continuity.values())
    ):
        return "complete-pass-pair"
    return "terminal-not-usable"


def _build_n3_observation_records(
    manifest: Mapping[str, Any],
    *,
    target_action_identity_sha256: str,
    map_result: Mapping[str, Any],
    target_result: Mapping[str, Any],
    map_timing: Mapping[str, Any],
    target_timing: Mapping[str, Any],
    temperature: Mapping[str, Any],
    capture_asset_sha256: str,
    map_fidelity_pass: bool,
    target_fidelity_pass: bool,
    controller_reboot_between_map_and_target: bool,
    panel_power_cycle_between_map_and_target: bool,
    j2_disconnect_between_map_and_target: bool,
    other_visible_refresh_between_map_and_target: bool,
    photo_difference_score: Optional[float] = None,
    photo_luminance_mean: Optional[float] = None,
    photo_luminance_standard_deviation: Optional[float] = None,
) -> dict[str, Any]:
    """Build one sealed observation from already deep-validated records."""

    root = _manifest_root(manifest)
    target_sha = _require_sha256(
        target_action_identity_sha256,
        label="target action identity",
    )
    context = _context_by_target(root, str(target_sha))
    try:
        map_root = validate_result_record(map_result)
        target_root = validate_result_record(target_result)
    except CampaignContractError as error:
        raise N3AnalysisError(f"P0 result is invalid: {error}") from error
    route = context["route"]
    if map_root["action_identity_sha256"] != route["map_action_identity_sha256"]:
        raise N3AnalysisError("MAP result belongs to another branch/prior/repeat")
    if target_root["action_identity_sha256"] != route["target_action_identity_sha256"]:
        raise N3AnalysisError("target result belongs to another branch/repeat/position")
    visual = {
        "map_fidelity_pass": map_fidelity_pass,
        "target_fidelity_pass": target_fidelity_pass,
        "photo_difference_score": photo_difference_score,
        "photo_luminance_mean": photo_luminance_mean,
        "photo_luminance_standard_deviation": photo_luminance_standard_deviation,
    }
    continuity = {
        "controller_reboot_between_map_and_target": controller_reboot_between_map_and_target,
        "panel_power_cycle_between_map_and_target": panel_power_cycle_between_map_and_target,
        "j2_disconnect_between_map_and_target": j2_disconnect_between_map_and_target,
        "other_visible_refresh_between_map_and_target": other_visible_refresh_between_map_and_target,
    }
    if any(type(value) is not bool for value in continuity.values()):
        raise N3AnalysisError("MAP-to-target continuity observations must be boolean")
    _validate_timing(map_timing, label="MAP")
    _validate_timing(target_timing, label="target")
    _validate_temperature(temperature)
    _validate_visual(visual)
    capture_sha = _require_sha256(capture_asset_sha256, label="camera capture asset")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "study": context["study"],
        "manifest_canonical_sha256": root["integrity"]["canonical_sha256"],
        "branch_id": context["branch_id"],
        "template_id": context["template_id"],
        "repeat_count": context["repeat_count"],
        "repeat_ordinal": context["repeat_ordinal"],
        "block_index": context["block_index"],
        "session_position": context["session_position"],
        "candidate_cell_id": context["candidate_cell_id"],
        "session_id": route["session_id"],
        "map_action_identity_sha256": route["map_action_identity_sha256"],
        "target_action_identity_sha256": route["target_action_identity_sha256"],
        "map_result": _snapshot(map_root),
        "map_result_file_sha256": result_file_sha256(map_root),
        "target_result": _snapshot(target_root),
        "target_result_file_sha256": result_file_sha256(target_root),
        "registered_assets": _registered_assets(root),
        "capture_asset_sha256": capture_sha,
        "timing": {
            "map": _snapshot(map_timing),
            "target": _snapshot(target_timing),
        },
        "temperature": _snapshot(temperature),
        "visual": visual,
        "continuity": continuity,
        "pair_state": _pair_state(map_root, target_root, visual, continuity),
        "classification": {
            "offline_record": True,
            "hardware_qualified": False,
            "network_io_performed_by_builder": False,
            "device_io_performed_by_builder": False,
            "retry_or_recovery_performed_by_builder": False,
        },
    }
    observation = {
        **unsigned,
        "integrity": _integrity(unsigned, OBSERVATION_HASH_SCOPE),
    }
    validate_n3_observation(root, observation)
    return observation


def build_n3_session_observation(
    plan: Mapping[str, Any],
    *,
    map_bundle: Mapping[str, Any],
    target_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep-validate one exact MAP/target bundle pair and derive its observation."""

    try:
        root_plan = execution.validate_n3_exact_plan(plan)
        target_action = target_bundle.get("evidence", {}).get("action_key")
        if not isinstance(target_action, str):
            raise N3AnalysisError("target bundle action key is missing")
        target_snapshot = execution.load_n3_action_snapshot(root_plan, target_action)
        if target_snapshot.phase != "target":
            raise N3AnalysisError("target_bundle does not contain a target action")
        map_validated = execution.validate_n3_finalized_action_bundle(
            root_plan,
            map_bundle,
            expected_action_key=target_snapshot.route["map_action_key"],
        )
        target_validated = execution.validate_n3_finalized_action_bundle(
            root_plan,
            target_bundle,
            expected_action_key=target_snapshot.key,
            prior_bundle=map_bundle,
        )
    except execution.N3ExecutionContractError as error:
        raise N3AnalysisError(f"N3 finalized bundle pair is invalid: {error}") from error
    map_observation = map_validated["observation"]
    target_observation = target_validated["observation"]
    continuity = target_observation["continuity"]
    if not isinstance(continuity, Mapping):
        raise N3AnalysisError("N3 target bundle continuity evidence is missing")
    return _build_n3_observation_records(
        root_plan["execution_manifest"],
        target_action_identity_sha256=target_validated["action_identity_sha256"],
        map_result=map_validated["result"],
        target_result=target_validated["result"],
        map_timing=map_observation["electrical"]["timing_ms"],
        target_timing=target_observation["electrical"]["timing_ms"],
        temperature={
            "pre_map": map_observation["thermal"]["pre_action_c"],
            "post_map": map_observation["thermal"]["post_action_c"],
            "post_target": target_observation["thermal"]["post_action_c"],
            "session_max": max(
                map_observation["thermal"]["session_max_c"],
                target_observation["thermal"]["session_max_c"],
            ),
        },
        capture_asset_sha256=target_observation["camera"][
            "capture_file_sha256"
        ],
        map_fidelity_pass=map_observation["visual"]["map_fidelity_pass"],
        target_fidelity_pass=target_observation["visual"][
            "target_fidelity_pass"
        ],
        controller_reboot_between_map_and_target=continuity[
            "controller_reboot_between_actions"
        ],
        panel_power_cycle_between_map_and_target=continuity[
            "panel_power_cycle_between_actions"
        ],
        j2_disconnect_between_map_and_target=continuity[
            "j2_disconnect_between_actions"
        ],
        other_visible_refresh_between_map_and_target=continuity[
            "other_visible_refresh_between_actions"
        ],
        photo_difference_score=target_observation["visual"][
            "photo_difference_score"
        ],
        photo_luminance_mean=target_observation["visual"][
            "photo_luminance_mean"
        ],
        photo_luminance_standard_deviation=target_observation["visual"][
            "photo_luminance_standard_deviation"
        ],
    )


def validate_n3_observation(
    manifest: Mapping[str, Any], observation: Mapping[str, Any]
) -> Mapping[str, Any]:
    root = _manifest_root(manifest)
    expected_keys = {
        "schema_version",
        "kind",
        "study",
        "manifest_canonical_sha256",
        "branch_id",
        "template_id",
        "repeat_count",
        "repeat_ordinal",
        "block_index",
        "session_position",
        "candidate_cell_id",
        "session_id",
        "map_action_identity_sha256",
        "target_action_identity_sha256",
        "map_result",
        "map_result_file_sha256",
        "target_result",
        "target_result_file_sha256",
        "registered_assets",
        "capture_asset_sha256",
        "timing",
        "temperature",
        "visual",
        "continuity",
        "pair_state",
        "classification",
        "integrity",
    }
    if not isinstance(observation, Mapping) or set(observation) != expected_keys:
        raise N3AnalysisError("N3 observation fields differ from the fixed contract")
    record = observation
    if (
        record["schema_version"] != SCHEMA_VERSION
        or record["kind"] != OBSERVATION_KIND
        or record["study"] != root["study"]
        or record["manifest_canonical_sha256"]
        != root["integrity"]["canonical_sha256"]
    ):
        raise N3AnalysisError("N3 observation manifest identity is invalid")
    target_sha = _require_sha256(
        record["target_action_identity_sha256"],
        label="observation target action identity",
    )
    context = _context_by_target(root, str(target_sha))
    route = context["route"]
    expected_context = {
        "branch_id": context["branch_id"],
        "template_id": context["template_id"],
        "repeat_count": context["repeat_count"],
        "repeat_ordinal": context["repeat_ordinal"],
        "block_index": context["block_index"],
        "session_position": context["session_position"],
        "candidate_cell_id": context["candidate_cell_id"],
        "session_id": route["session_id"],
        "map_action_identity_sha256": route["map_action_identity_sha256"],
    }
    if any(record[field] != value for field, value in expected_context.items()):
        raise N3AnalysisError("N3 observation replays another branch/prior/repeat route")
    try:
        map_result = validate_result_record(record["map_result"])
        target_result = validate_result_record(record["target_result"])
    except CampaignContractError as error:
        raise N3AnalysisError(f"observation P0 result is invalid: {error}") from error
    if map_result["action_identity_sha256"] != route["map_action_identity_sha256"]:
        raise N3AnalysisError("observation MAP result is cross-route replay")
    if target_result["action_identity_sha256"] != target_sha:
        raise N3AnalysisError("observation target result is cross-route replay")
    if record["map_result_file_sha256"] != result_file_sha256(map_result):
        raise N3AnalysisError("observation MAP whole-file result SHA is invalid")
    if record["target_result_file_sha256"] != result_file_sha256(target_result):
        raise N3AnalysisError("observation target whole-file result SHA is invalid")
    map_completed = _timestamp(map_result["completed_at"], label="MAP result completed_at")
    target_completed = _timestamp(
        target_result["completed_at"], label="target result completed_at"
    )
    if target_completed <= map_completed:
        raise N3AnalysisError("target result does not occur after its own MAP result")
    target_action = next(
        action
        for action in context["campaign"]["actions"]
        if action["action_identity_sha256"] == target_sha
    )
    minimum_interval = target_action["identity"]["schedule"][
        "minimum_interval_since_prior_seconds"
    ]
    if (target_completed - map_completed).total_seconds() < minimum_interval:
        raise N3AnalysisError("MAP-to-target result interval is shorter than preregistered")
    if record["registered_assets"] != _registered_assets(root):
        raise N3AnalysisError("observation registered assets differ from the N3 manifest")
    for field, value in record["registered_assets"].items():
        _require_sha256(value, label=f"registered asset {field}", nullable=True)
    _require_sha256(record["capture_asset_sha256"], label="observation capture asset")
    timing = record["timing"]
    if not isinstance(timing, Mapping) or set(timing) != {"map", "target"}:
        raise N3AnalysisError("observation timing envelope is invalid")
    _validate_timing(timing["map"], label="MAP")
    _validate_timing(timing["target"], label="target")
    _validate_temperature(record["temperature"])
    visual = _validate_visual(record["visual"])
    continuity = record["continuity"]
    expected_continuity_keys = {
        "controller_reboot_between_map_and_target",
        "panel_power_cycle_between_map_and_target",
        "j2_disconnect_between_map_and_target",
        "other_visible_refresh_between_map_and_target",
    }
    if (
        not isinstance(continuity, Mapping)
        or set(continuity) != expected_continuity_keys
        or any(type(value) is not bool for value in continuity.values())
    ):
        raise N3AnalysisError("observation MAP-to-target continuity evidence is invalid")
    if record["pair_state"] != _pair_state(
        map_result, target_result, visual, continuity
    ):
        raise N3AnalysisError("observation pair state is inconsistent")
    if record["classification"] != {
        "offline_record": True,
        "hardware_qualified": False,
        "network_io_performed_by_builder": False,
        "device_io_performed_by_builder": False,
        "retry_or_recovery_performed_by_builder": False,
    }:
        raise N3AnalysisError("observation offline classification changed")
    unsigned = dict(record)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, OBSERVATION_HASH_SCOPE):
        raise N3AnalysisError("observation canonical integrity is invalid")
    return record


def _nearest_rank(values: Sequence[float], proportion: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(proportion * len(ordered)))
    return ordered[rank - 1]


def summarize_numeric(values: Sequence[int | float]) -> dict[str, Any]:
    """Return deterministic descriptive statistics with the n<10 guardrail."""

    numbers = [
        float(_number(value, label=f"summary value {index}"))
        for index, value in enumerate(values)
    ]
    if not numbers:
        return {
            "n": 0,
            "minimum": None,
            "maximum_observed": None,
            "mean": None,
            "sample_standard_deviation": None,
            "range": None,
            "p95": None,
            "p99": None,
            "extreme_reporting": "no-observations",
            "percentile_method": None,
            "uncertainty_statement": "no usable observations",
        }
    count = len(numbers)
    mean = math.fsum(numbers) / count
    sample_sd = None
    if count >= 2:
        sample_sd = math.sqrt(math.fsum((value - mean) ** 2 for value in numbers) / (count - 1))
    minimum = min(numbers)
    maximum = max(numbers)
    if count < 10:
        p95 = None
        p99 = None
        extreme_reporting = "maximum-observed-only-n-less-than-10"
        percentile_method = None
        uncertainty = (
            "descriptive-only small sample; report maximum observed and do not label "
            "P95 or P99"
        )
    else:
        p95 = _nearest_rank(numbers, 0.95)
        p99 = _nearest_rank(numbers, 0.99)
        extreme_reporting = "maximum-observed-and-nearest-rank-percentiles"
        percentile_method = "nearest-rank-ceiling-v1"
        uncertainty = "descriptive empirical sample; no population confidence claim"
    return {
        "n": count,
        "minimum": minimum,
        "maximum_observed": maximum,
        "mean": mean,
        "sample_standard_deviation": sample_sd,
        "range": maximum - minimum,
        "p95": p95,
        "p99": p99,
        "extreme_reporting": extreme_reporting,
        "percentile_method": percentile_method,
        "uncertainty_statement": uncertainty,
    }


def _timing_checks(observation: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, bool]:
    contract = manifest["measurement_asset_registry"]["timing"]["driver_timing_contract"]
    target = observation["timing"]["target"]
    stages = contract["stages_ms"]
    checks = {
        "queue_delay_within_maximum": target["queue_delay_ms"]
        <= contract["maximum_queue_delay_ms"],
        "job_duration_within_nominal": contract["job_duration_ms"][0]
        <= target["job_duration_ms"]
        <= contract["job_duration_ms"][1],
        "job_driver_duration_delta_within_maximum": abs(
            target["job_duration_ms"] - target["driver_total_ms"]
        )
        <= contract["maximum_job_driver_duration_delta_ms"],
    }
    field_to_stage = {
        "driver_total_ms": "total_ms",
        "cs1_upload_ms": "cs1_upload_ms",
        "cs2_upload_ms": "cs2_upload_ms",
        "pon_ms": "pon_ms",
        "drf_ms": "drf_ms",
        "pof_ms": "pof_ms",
        "post_psr_ms": "post_psr_ms",
    }
    for field, stage in field_to_stage.items():
        checks[f"{field}_within_stage_bounds"] = (
            stages[stage][0] <= target[field] <= stages[stage][1]
        )
    return checks


def _metric_values(observations: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    metrics: dict[str, list[float]] = {}
    for observation in observations:
        for phase in ("map", "target"):
            for field in TIMING_FIELDS:
                metrics.setdefault(f"timing.{phase}.{field}", []).append(
                    float(observation["timing"][phase][field])
                )
        for field in TEMPERATURE_FIELDS:
            metrics.setdefault(f"temperature.{field}", []).append(
                float(observation["temperature"][field])
            )
        for field in VISUAL_FIELDS:
            value = observation["visual"][field]
            if value is not None:
                metrics.setdefault(f"visual.{field}", []).append(float(value))
    return metrics


def _summaries(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        name: summarize_numeric(values)
        for name, values in sorted(_metric_values(observations).items())
    }


def _validate_observation_set(
    manifest: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    records = [validate_n3_observation(manifest, record) for record in observations]
    target_actions = [record["target_action_identity_sha256"] for record in records]
    map_actions = [record["map_action_identity_sha256"] for record in records]
    map_results = [record["map_result_file_sha256"] for record in records]
    target_results = [record["target_result_file_sha256"] for record in records]
    captures = [record["capture_asset_sha256"] for record in records]
    for label, values in (
        ("target action", target_actions),
        ("MAP action", map_actions),
        ("MAP result", map_results),
        ("target result", target_results),
        ("camera capture", captures),
    ):
        if len(values) != len(set(values)):
            raise N3AnalysisError(f"duplicate {label} replay in N3 observations")
    return records


def _validate_session_bundle_set(
    plan: Mapping[str, Any],
    session_bundles: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    """Accept only exact two-bundle session envelopes and deep-validate each."""

    if not isinstance(session_bundles, Sequence) or isinstance(
        session_bundles, (str, bytes, bytearray)
    ):
        raise N3AnalysisError("session_bundles must be a sequence of deep bundle pairs")
    observations: list[Mapping[str, Any]] = []
    chains: list[dict[str, Any]] = []
    for index, pair in enumerate(session_bundles):
        if not isinstance(pair, Mapping) or set(pair) != {
            "map_bundle",
            "target_bundle",
        }:
            raise N3AnalysisError(
                f"session_bundles[{index}] must contain exactly map_bundle/target_bundle"
            )
        observation = build_n3_session_observation(
            plan,
            map_bundle=pair["map_bundle"],
            target_bundle=pair["target_bundle"],
        )
        observations.append(observation)
        map_bundle = pair["map_bundle"]
        target_bundle = pair["target_bundle"]
        chains.append(
            {
                "map_action_identity_sha256": observation[
                    "map_action_identity_sha256"
                ],
                "target_action_identity_sha256": observation[
                    "target_action_identity_sha256"
                ],
                "map_result_file_sha256": map_bundle["result_file_sha256"],
                "map_finalization_file_sha256": map_bundle[
                    "finalization_file_sha256"
                ],
                "target_result_file_sha256": target_bundle[
                    "result_file_sha256"
                ],
                "target_finalization_file_sha256": target_bundle[
                    "finalization_file_sha256"
                ],
                "capture_asset_sha256": observation["capture_asset_sha256"],
                "execution_evidence_verified": True,
            }
        )
    records = _validate_observation_set(plan["execution_manifest"], observations)
    if len({_sha256(chain) for chain in chains}) != len(chains):
        raise N3AnalysisError("duplicate deep bundle chain replay in N3 analyzer input")
    return records, chains


def _common_report_fields(
    manifest: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    expected_target_shas: Sequence[str],
    *,
    plan: Mapping[str, Any],
    validated_chains: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observed_shas = [record["target_action_identity_sha256"] for record in observations]
    unexpected = sorted(set(observed_shas) - set(expected_target_shas))
    if unexpected:
        raise N3AnalysisError("observations contain a target from another selected branch/template")
    missing = [sha for sha in expected_target_shas if sha not in observed_shas]
    usable = [record for record in observations if record["pair_state"] == "complete-pass-pair"]
    unusable = [
        record["target_action_identity_sha256"]
        for record in observations
        if record["pair_state"] != "complete-pass-pair"
    ]
    asset_blockers = measurement_asset_blockers(manifest["measurement_asset_registry"])
    timing_checks = {
        record["target_action_identity_sha256"]: _timing_checks(record, manifest)
        for record in observations
    }
    timing_failures = {
        sha: sorted(name for name, passed in checks.items() if not passed)
        for sha, checks in timing_checks.items()
        if not all(checks.values())
    }
    complete = not missing and not unusable and not asset_blockers
    blockers = [
        *asset_blockers,
        *(["missing_planned_observations"] if missing else []),
        *(["terminal_or_fidelity_failed_pairs_present"] if unusable else []),
        *(["timing_contract_deviations_present"] if timing_failures else []),
    ]
    return {
        "exact_plan_id": plan["plan_id"],
        "exact_plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "expected_observation_count": len(expected_target_shas),
        "observed_observation_count": len(observations),
        "usable_observation_count": len(usable),
        "missing_target_action_identity_sha256s": missing,
        "unusable_target_action_identity_sha256s": unusable,
        "measurement_asset_blockers": asset_blockers,
        "timing_contract_failures": timing_failures,
        "complete": complete,
        "analysis_ready": complete and not timing_failures,
        "hardware_qualified": False,
        "blockers": blockers,
        "validated_bundle_chains": _snapshot(validated_chains),
        "analyzer_accepts_deep_bundles_only": True,
        "usable_observations": usable,
        "classification": {
            "offline_analysis": True,
            "descriptive_only": True,
            "hardware_execution_authorized": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }


def analyze_n3a(
    plan: Mapping[str, Any],
    *,
    session_bundles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Analyze the one N2-selected N3A template from deep bundle pairs."""

    try:
        root_plan = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3AnalysisError(f"N3A exact plan is invalid: {error}") from error
    if root_plan["study"] != "N3A":
        raise N3AnalysisError("N3A analyzer requires an exact N3A plan")
    root = _manifest_root(root_plan["execution_manifest"])
    if root["kind"] != N3A_KIND:
        raise N3AnalysisError("N3A analyzer requires an N3A manifest")
    selection = root_plan["selection"]
    branch_id = selection["branch_id"]
    repeat_count = selection["repeat_count"]
    matches = [branch for branch in root["branches"] if branch["branch_id"] == branch_id]
    if len(matches) != 1:
        raise N3AnalysisError("N3A branch_id is not unique")
    branch = matches[0]
    templates = [
        template
        for template in branch["repeat_templates"]
        if template["repeat_count"] == repeat_count
    ]
    if len(templates) != 1:
        raise N3AnalysisError("N3A repeat template is not unique")
    template = templates[0]
    expected = [route["target_action_identity_sha256"] for route in template["routes"]]
    records, chains = _validate_session_bundle_set(root_plan, session_bundles)
    common = _common_report_fields(
        root,
        records,
        expected,
        plan=root_plan,
        validated_chains=chains,
    )
    usable = common.pop("usable_observations")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": N3A_REPORT_KIND,
        "study": "N3A",
        "branch_id": branch_id,
        "winner_cell_id": branch["winner_cell_id"],
        "template_id": template["template_id"],
        "repeat_count": repeat_count,
        **common,
        "metric_summaries": _summaries(usable),
        "small_sample_rule": {
            "threshold": 10,
            "when_n_is_less_than_threshold": "maximum-observed-only",
            "p95_label_allowed": False,
            "p99_label_allowed": False,
        },
        "interpretation": {
            "repeatability_claim": "descriptive-only",
            "population_percentile_claim": False,
            "direct_target_carryover_claim": False,
        },
    }
    report = {**unsigned, "integrity": _integrity(unsigned, REPORT_HASH_SCOPE)}
    validate_n3_report(report, plan=root_plan)
    return report


def _additive_effects(
    observations: Sequence[Mapping[str, Any]], metric_name: str
) -> dict[str, Any]:
    values = _metric_values(observations).get(metric_name, [])
    if len(values) != len(observations):
        return {
            "available": False,
            "reason": "metric_missing_from_one_or_more_usable_observations",
            "grand_mean": None,
            "candidate_effects": {},
            "position_effects": {},
            "inference_authorized": False,
        }
    grand = math.fsum(values) / len(values) if values else None
    candidate_effects: dict[str, float] = {}
    position_effects: dict[str, float] = {}
    if grand is not None:
        for cell in ("Q1", "Q2", "Q3", "Q4"):
            group = [
                value
                for value, record in zip(values, observations)
                if record["candidate_cell_id"] == cell
            ]
            if group:
                candidate_effects[cell] = math.fsum(group) / len(group) - grand
        for position in (1, 2, 3, 4):
            group = [
                value
                for value, record in zip(values, observations)
                if record["session_position"] == position
            ]
            if group:
                position_effects[str(position)] = math.fsum(group) / len(group) - grand
    return {
        "available": grand is not None,
        "reason": None if grand is not None else "no_usable_observations",
        "grand_mean": grand,
        "candidate_effects": candidate_effects,
        "position_effects": position_effects,
        "inference_authorized": False,
    }


def analyze_n3b(
    plan: Mapping[str, Any],
    *,
    session_bundles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Analyze all four exact N3B blocks from deep bundle pairs."""

    try:
        root_plan = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3AnalysisError(f"N3B exact plan is invalid: {error}") from error
    if root_plan["study"] != "N3B":
        raise N3AnalysisError("N3B analyzer requires an exact N3B plan")
    root = _manifest_root(root_plan["execution_manifest"])
    if root["kind"] != N3B_KIND:
        raise N3AnalysisError("N3B analyzer requires an N3B manifest")
    expected = [
        route["target_action_identity_sha256"]
        for branch in root["branches"]
        for route in branch["routes"]
    ]
    records, chains = _validate_session_bundle_set(root_plan, session_bundles)
    common = _common_report_fields(
        root,
        records,
        expected,
        plan=root_plan,
        validated_chains=chains,
    )
    usable = common.pop("usable_observations")
    by_candidate = {
        cell: _summaries([record for record in usable if record["candidate_cell_id"] == cell])
        for cell in ("Q1", "Q2", "Q3", "Q4")
    }
    by_position = {
        str(position): _summaries(
            [record for record in usable if record["session_position"] == position]
        )
        for position in (1, 2, 3, 4)
    }
    key_metrics = (
        "timing.target.job_duration_ms",
        "temperature.session_max",
        "visual.photo_difference_score",
        "visual.photo_luminance_mean",
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": N3B_REPORT_KIND,
        "study": "N3B",
        **common,
        "overall_metric_summaries": _summaries(usable),
        "metric_summaries_by_candidate": by_candidate,
        "metric_summaries_by_session_position": by_position,
        "descriptive_additive_effects": {
            metric: _additive_effects(usable, metric) for metric in key_metrics
        },
        "small_sample_rule": {
            "threshold": 10,
            "groups_below_threshold_use": "maximum-observed-only",
            "p95_or_p99_label_for_group_below_threshold": False,
        },
        "interpretation": {
            "balanced_position_effect_claim": "descriptive-only",
            "direct_target_carryover_measured": False,
            "direct_target_carryover_claim": False,
            "direct_target_carryover_followup": "N8",
            "reason": "every target has an intervening own MAP prior",
        },
    }
    report = {**unsigned, "integrity": _integrity(unsigned, REPORT_HASH_SCOPE)}
    validate_n3_report(report, plan=root_plan)
    return report


def validate_n3_report(
    report: Mapping[str, Any], *, plan: Optional[Mapping[str, Any]] = None
) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise N3AnalysisError("N3 report must be an object")
    if report.get("schema_version") != SCHEMA_VERSION or report.get("kind") not in {
        N3A_REPORT_KIND,
        N3B_REPORT_KIND,
    }:
        raise N3AnalysisError("N3 report schema or kind is invalid")
    classification = report.get("classification")
    if classification != {
        "offline_analysis": True,
        "descriptive_only": True,
        "hardware_execution_authorized": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }:
        raise N3AnalysisError("N3 report classification changed")
    if report.get("hardware_qualified") is not False:
        raise N3AnalysisError("offline N3 report must not claim hardware qualification")
    if (
        report.get("analyzer_accepts_deep_bundles_only") is not True
        or not isinstance(report.get("validated_bundle_chains"), list)
        or len(report["validated_bundle_chains"])
        != report.get("observed_observation_count")
    ):
        raise N3AnalysisError("N3 report deep-bundle evidence is invalid")
    for chain in report["validated_bundle_chains"]:
        expected_chain_keys = {
            "map_action_identity_sha256",
            "target_action_identity_sha256",
            "map_result_file_sha256",
            "map_finalization_file_sha256",
            "target_result_file_sha256",
            "target_finalization_file_sha256",
            "capture_asset_sha256",
            "execution_evidence_verified",
        }
        if not isinstance(chain, Mapping) or set(chain) != expected_chain_keys:
            raise N3AnalysisError("N3 report validated bundle chain fields changed")
        for field in expected_chain_keys - {"execution_evidence_verified"}:
            _require_sha256(chain[field], label=f"validated bundle chain {field}")
        if chain["execution_evidence_verified"] is not True:
            raise N3AnalysisError("N3 report includes an unverified execution chain")
    if len(
        {chain["target_result_file_sha256"] for chain in report["validated_bundle_chains"]}
    ) != len(report["validated_bundle_chains"]):
        raise N3AnalysisError("N3 report replays a target bundle chain")
    if plan is not None:
        try:
            exact_plan = execution.validate_n3_exact_plan(plan)
        except execution.N3ExecutionContractError as error:
            raise N3AnalysisError(f"N3 report exact plan is invalid: {error}") from error
        if (
            report.get("exact_plan_id") != exact_plan["plan_id"]
            or report.get("exact_plan_canonical_sha256")
            != exact_plan["integrity"]["canonical_sha256"]
            or report.get("manifest_canonical_sha256")
            != exact_plan["execution_manifest"]["integrity"]["canonical_sha256"]
            or report.get("study") != exact_plan["study"]
        ):
            raise N3AnalysisError("N3 report exact plan binding changed")
    if type(report.get("complete")) is not bool or type(report.get("analysis_ready")) is not bool:
        raise N3AnalysisError("N3 report readiness fields must be boolean")

    def validate_small_sample_summaries(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            summary_keys = {
                "n",
                "maximum_observed",
                "p95",
                "p99",
                "extreme_reporting",
            }
            if summary_keys.issubset(value):
                count = value["n"]
                if type(count) is not int or count < 0:
                    raise N3AnalysisError(f"{path}.n is invalid")
                if count < 10 and (
                    value["p95"] is not None
                    or value["p99"] is not None
                    or value["extreme_reporting"]
                    not in {"no-observations", "maximum-observed-only-n-less-than-10"}
                ):
                    raise N3AnalysisError(
                        f"{path} labels a P95/P99 value with fewer than ten samples"
                    )
            for key, item in value.items():
                validate_small_sample_summaries(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                validate_small_sample_summaries(item, f"{path}[{index}]")

    validate_small_sample_summaries(report, "report")
    integrity = report.get("integrity")
    unsigned = dict(report)
    unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned, REPORT_HASH_SCOPE):
        raise N3AnalysisError("N3 report canonical integrity is invalid")
    return report


def analyze_n3_exact_plan(
    plan: Mapping[str, Any],
    *,
    session_bundles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Dispatch one exact plan without exposing a loose-observation API."""

    try:
        root = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3AnalysisError(f"N3 exact plan is invalid: {error}") from error
    if root["study"] == "N3A":
        return analyze_n3a(root, session_bundles=session_bundles)
    return analyze_n3b(root, session_bundles=session_bundles)


def write_n3_report(report: Mapping[str, Any], output_file: Path) -> None:
    """Exclusive-create one canonical report; never overwrite evidence."""

    validate_n3_report(report)
    if not isinstance(output_file, Path):
        raise N3AnalysisError("N3 report output must be pathlib.Path")
    from tools import g1_s1_rc2g_n3_once as runner

    try:
        runner._fixed.require_local_regular_path_syntax(
            output_file, label="N3 analysis output"
        )
        runner._fixed._reject_reparse_path_chain(
            output_file, label="N3 analysis output"
        )
        output_file.parent.resolve(strict=True)
    except (ValueError, RuntimeError, OSError) as error:
        raise N3AnalysisError(f"N3 analysis output path is unsafe: {error}") from error
    payload = canonical_json_bytes(report)
    try:
        descriptor = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise N3AnalysisError("N3 analysis output already exists") from error
    except OSError as error:
        raise N3AnalysisError(f"could not write N3 analysis output: {error}") from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument(
        "--session",
        nargs=2,
        action="append",
        metavar=("MAP_RESULT", "TARGET_RESULT"),
        type=Path,
        required=True,
        help="repeat once per exact plan route",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    from tools import g1_s1_rc2g_n3_once as runner

    try:
        plan, _plan_sha = runner.load_n3_exact_plan_file(args.plan_file)
        pairs = [
            {
                "map_bundle": runner._load_bundle_from_result_file(map_path),
                "target_bundle": runner._load_bundle_from_result_file(target_path),
            }
            for map_path, target_path in args.session
        ]
        report = analyze_n3_exact_plan(plan, session_bundles=pairs)
        if args.output is not None:
            write_n3_report(report, args.output)
    except (N3AnalysisError, runner.N3FixedActionError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


__all__ = [
    "N3A_REPORT_KIND",
    "N3B_REPORT_KIND",
    "N3AnalysisError",
    "OBSERVATION_KIND",
    "TIMING_FIELDS",
    "analyze_n3_exact_plan",
    "analyze_n3a",
    "analyze_n3b",
    "build_n3_session_observation",
    "main",
    "parse_args",
    "summarize_numeric",
    "validate_n3_observation",
    "validate_n3_report",
    "write_n3_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
