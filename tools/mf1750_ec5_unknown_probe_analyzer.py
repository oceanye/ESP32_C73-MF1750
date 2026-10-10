#!/usr/bin/env python3
"""Analyze one fixed EC5 U04 manual observation without device access.

The analyzer verifies the campaign and every observation lineage field from
local immutable files.  Its verdict is descriptive only: it cannot qualify an
unknown code, infer a waveform change, authorize retry/recovery, or advance to
U07.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_unknown_probe_campaign as campaign_tool  # noqa: E402


SCHEMA_VERSION = 1
OBSERVATION_KIND = "mf1750-ec5-u04-white-pilot-manual-observation"
ANALYSIS_KIND = "mf1750-ec5-u04-white-pilot-descriptive-analysis"
HASH_SCOPE = (
    "entire EC5 U04 descriptive analysis excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,127})\Z")
_OBSERVATION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "observation_id",
        "observed_at",
        "test_id",
        "candidate_code",
        "intended_initial_code",
        "campaign_canonical_sha256",
        "action_identity_sha256",
        "manual_observation_contract_sha256",
        "lineage",
        "roi_observations",
        "hold",
        "electrical",
        "temperature",
        "esp_continuity",
        "anomaly_review",
        "notes",
    }
)
_LINEAGE_KEYS = frozenset(
    {
        "panel_file_sha256",
        "build_sidecar_sha256",
        "firmware_binary_sha256",
        "fixture_manifest_payload_sha256",
        "measured_initial_record_id",
        "measured_initial_record_sha256",
        "measurement_setup_sha256",
        "cold_start_evidence_id",
        "user_authorization_id",
        "device_report_id",
        "device_report_sha256",
    }
)
_ROI_KEYS = frozenset(
    {
        "roi_id",
        "controller",
        "classification",
        "stable_for_entire_observation",
        "notes",
    }
)
_HOLD_KEYS = frozenset(
    {"start_at", "end_at", "duration_seconds", "continuous_observation"}
)
_ELECTRICAL_KEYS = frozenset(
    {
        "psu_mode",
        "idle_current_a",
        "peak_current_a",
        "current_within_reviewed_gate",
        "rails_within_reviewed_gate",
        "cutoff_available",
        "abnormal_event_observed",
        "notes",
    }
)
_TEMPERATURE_KEYS = frozenset(
    {
        "start_c",
        "max_c",
        "end_c",
        "within_reviewed_gate",
        "unexplained_hotspot",
        "notes",
    }
)
_ESP_KEYS = frozenset(
    {
        "boot_id_before",
        "boot_id_after",
        "reset_observed",
        "same_boot_continuity",
        "job_continuity_observed",
        "notes",
    }
)
_ANOMALY_KEYS = frozenset(
    {
        "visual_damage_or_crack",
        "controller_divergence_worsening",
        "busy_anomaly",
        "odor_smoke_arc_or_noise",
        "evidence_missing",
        "notes",
    }
)
_ANALYSIS_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "campaign_binding",
        "observation_binding",
        "panel",
        "firmware_build",
        "roi_summary",
        "hold_summary",
        "safety_review",
        "verdict",
        "progression_gate",
        "classification",
        "integrity",
    }
)


class EC5AnalyzerError(ValueError):
    """The U04 observation or its descriptive analysis failed closed."""


def _exact(value: Any, *, label: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise EC5AnalyzerError(f"{label} fields differ from contract")
    return value


def _token(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise EC5AnalyzerError(f"{label} must be a non-placeholder token")
    if value.upper() in {"UNKNOWN", "TBD", "NONE", "NULL", "TEST"}:
        raise EC5AnalyzerError(f"{label} must not be a placeholder")
    return value


def _digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EC5AnalyzerError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _notes(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(ord(character) < 0x20 and character not in "\n\t" for character in value)
    ):
        raise EC5AnalyzerError(f"{label} must be bounded human-readable text")
    return value


def _boolean(value: Any, *, label: str) -> bool:
    if type(value) is not bool:
        raise EC5AnalyzerError(f"{label} must be boolean")
    return value


def _finite(
    value: Any, *, label: str, minimum: Optional[float] = None
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EC5AnalyzerError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise EC5AnalyzerError(f"{label} is outside the accepted numeric domain")
    return result


def _rfc3339(value: Any, *, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EC5AnalyzerError(f"{label} must be RFC3339 text")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise EC5AnalyzerError(f"{label} must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EC5AnalyzerError(f"{label} must include a UTC offset")
    return value, parsed


def _load_validated_campaign(
    campaign_file: Path,
    panel_file: Path,
    build_sidecar_file: Path,
    firmware_binary_file: Path,
) -> tuple[Mapping[str, Any], bytes]:
    try:
        value, payload = campaign_tool.read_strict_json(
            campaign_file, label="EC5 campaign"
        )
        campaign_tool.validate_campaign(
            value,
            panel_file,
            build_sidecar_file,
            firmware_binary_file,
        )
    except campaign_tool.EC5CampaignError as error:
        raise EC5AnalyzerError(f"EC5 campaign failed deep validation: {error}") from error
    return value, payload


def _validate_lineage(
    value: Any, campaign: Mapping[str, Any]
) -> dict[str, str]:
    lineage = _exact(value, label="observation lineage", keys=_LINEAGE_KEYS)
    binding = campaign["physical_binding"]
    fixture = campaign["fixture_manifest"]
    expected = {
        "panel_file_sha256": binding["panel_file_sha256"],
        "build_sidecar_sha256": binding["build_sidecar_sha256"],
        "firmware_binary_sha256": binding["firmware_binary_sha256"],
        "fixture_manifest_payload_sha256": fixture["manifest_payload_sha256"],
    }
    for field, expected_value in expected.items():
        if _digest(lineage[field], label=f"lineage.{field}") != expected_value:
            raise EC5AnalyzerError(f"lineage.{field} differs from campaign")
    for field in (
        "measured_initial_record_sha256",
        "measurement_setup_sha256",
        "device_report_sha256",
    ):
        _digest(lineage[field], label=f"lineage.{field}")
    for field in (
        "measured_initial_record_id",
        "cold_start_evidence_id",
        "user_authorization_id",
        "device_report_id",
    ):
        _token(lineage[field], label=f"lineage.{field}")
    return dict(lineage)


def _validate_rois(
    value: Any, campaign: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != 2:
        raise EC5AnalyzerError("exactly two ordered ROI observations are required")
    contract = campaign["manual_observation_contract"]["contract"]
    allowed = set(contract["allowed_roi_classifications"])
    result: list[dict[str, Any]] = []
    for index, (item, expected) in enumerate(zip(value, contract["roi_order"])):
        roi = _exact(item, label=f"roi_observations[{index}]", keys=_ROI_KEYS)
        if roi["roi_id"] != expected["roi_id"] or roi["controller"] != expected[
            "controller"
        ]:
            raise EC5AnalyzerError("ROI observation order or controller changed")
        if roi["classification"] not in allowed:
            raise EC5AnalyzerError("ROI observation classification is unsupported")
        _boolean(
            roi["stable_for_entire_observation"],
            label=f"roi_observations[{index}].stable_for_entire_observation",
        )
        _notes(roi["notes"], label=f"roi_observations[{index}].notes")
        result.append(dict(roi))
    return result


def _validate_hold(value: Any) -> dict[str, Any]:
    hold = _exact(value, label="hold observation", keys=_HOLD_KEYS)
    start_text, start = _rfc3339(hold["start_at"], label="hold.start_at")
    end_text, end = _rfc3339(hold["end_at"], label="hold.end_at")
    duration = _finite(
        hold["duration_seconds"], label="hold.duration_seconds", minimum=0.0
    )
    actual = (end - start).total_seconds()
    if actual < 0 or not math.isclose(duration, actual, abs_tol=1e-6):
        raise EC5AnalyzerError("hold duration does not match its timestamps")
    return {
        "start_at": start_text,
        "end_at": end_text,
        "duration_seconds": duration,
        "continuous_observation": _boolean(
            hold["continuous_observation"], label="hold.continuous_observation"
        ),
    }


def _validate_electrical(value: Any) -> dict[str, Any]:
    electrical = _exact(value, label="electrical observation", keys=_ELECTRICAL_KEYS)
    if electrical["psu_mode"] not in {"CV", "CC", "OFF", "UNKNOWN"}:
        raise EC5AnalyzerError("electrical.psu_mode is unsupported")
    idle = _finite(
        electrical["idle_current_a"], label="electrical.idle_current_a", minimum=0.0
    )
    peak = _finite(
        electrical["peak_current_a"], label="electrical.peak_current_a", minimum=0.0
    )
    if peak < idle:
        raise EC5AnalyzerError("peak current must not be below idle current")
    result = dict(electrical)
    result["idle_current_a"] = idle
    result["peak_current_a"] = peak
    for field in (
        "current_within_reviewed_gate",
        "rails_within_reviewed_gate",
        "cutoff_available",
        "abnormal_event_observed",
    ):
        result[field] = _boolean(electrical[field], label=f"electrical.{field}")
    result["notes"] = _notes(electrical["notes"], label="electrical.notes")
    return result


def _validate_temperature(value: Any) -> dict[str, Any]:
    temperature = _exact(value, label="temperature observation", keys=_TEMPERATURE_KEYS)
    result = dict(temperature)
    for field in ("start_c", "max_c", "end_c"):
        result[field] = _finite(temperature[field], label=f"temperature.{field}")
    if result["max_c"] < max(result["start_c"], result["end_c"]):
        raise EC5AnalyzerError("temperature.max_c is below a boundary measurement")
    for field in ("within_reviewed_gate", "unexplained_hotspot"):
        result[field] = _boolean(temperature[field], label=f"temperature.{field}")
    result["notes"] = _notes(temperature["notes"], label="temperature.notes")
    return result


def _validate_esp(value: Any) -> dict[str, Any]:
    esp = _exact(value, label="ESP continuity observation", keys=_ESP_KEYS)
    before = _token(esp["boot_id_before"], label="esp_continuity.boot_id_before")
    after = _token(esp["boot_id_after"], label="esp_continuity.boot_id_after")
    reset = _boolean(esp["reset_observed"], label="esp_continuity.reset_observed")
    same = _boolean(
        esp["same_boot_continuity"], label="esp_continuity.same_boot_continuity"
    )
    job = _boolean(
        esp["job_continuity_observed"],
        label="esp_continuity.job_continuity_observed",
    )
    if same != (before == after and not reset):
        raise EC5AnalyzerError("ESP boot IDs/reset flag contradict same-boot continuity")
    return {
        "boot_id_before": before,
        "boot_id_after": after,
        "reset_observed": reset,
        "same_boot_continuity": same,
        "job_continuity_observed": job,
        "notes": _notes(esp["notes"], label="esp_continuity.notes"),
    }


def _validate_anomalies(value: Any) -> dict[str, Any]:
    anomaly = _exact(value, label="anomaly review", keys=_ANOMALY_KEYS)
    result = dict(anomaly)
    for field in _ANOMALY_KEYS - {"notes"}:
        result[field] = _boolean(anomaly[field], label=f"anomaly_review.{field}")
    result["notes"] = _notes(anomaly["notes"], label="anomaly_review.notes")
    return result


def validate_observation(
    value: Mapping[str, Any], campaign: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one exact manual observation and all campaign bindings."""

    observation = _exact(value, label="manual observation", keys=_OBSERVATION_KEYS)
    action = campaign["actions"][0]
    contract_sha = campaign["manual_observation_contract"]["canonical_sha256"]
    if (
        observation["schema_version"] != SCHEMA_VERSION
        or observation["kind"] != OBSERVATION_KIND
        or observation["test_id"] != campaign_tool.TEST_ID
        or observation["candidate_code"] != campaign_tool.U04_CODE
        or observation["intended_initial_code"] != campaign_tool.WHITE_CODE
        or observation["campaign_canonical_sha256"]
        != campaign["integrity"]["canonical_sha256"]
        or observation["action_identity_sha256"]
        != action["action_identity_sha256"]
        or observation["manual_observation_contract_sha256"] != contract_sha
    ):
        raise EC5AnalyzerError("manual observation identity differs from campaign")
    _token(observation["observation_id"], label="observation_id")
    _rfc3339(observation["observed_at"], label="observed_at")
    lineage = _validate_lineage(observation["lineage"], campaign)
    rois = _validate_rois(observation["roi_observations"], campaign)
    hold = _validate_hold(observation["hold"])
    electrical = _validate_electrical(observation["electrical"])
    temperature = _validate_temperature(observation["temperature"])
    esp = _validate_esp(observation["esp_continuity"])
    anomalies = _validate_anomalies(observation["anomaly_review"])
    _notes(observation["notes"], label="observation.notes")
    normalized = dict(observation)
    normalized.update(
        {
            "lineage": lineage,
            "roi_observations": rois,
            "hold": hold,
            "electrical": electrical,
            "temperature": temperature,
            "esp_continuity": esp,
            "anomaly_review": anomalies,
        }
    )
    return json.loads(campaign_tool.canonical_json_bytes(normalized).decode("utf-8"))


def _safety_review(observation: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    electrical = observation["electrical"]
    temperature = observation["temperature"]
    esp = observation["esp_continuity"]
    anomaly = observation["anomaly_review"]
    checks = {
        "psu_in_cv": electrical["psu_mode"] == "CV",
        "current_within_reviewed_gate": electrical["current_within_reviewed_gate"],
        "rails_within_reviewed_gate": electrical["rails_within_reviewed_gate"],
        "cutoff_available": electrical["cutoff_available"],
        "no_electrical_abnormal_event": not electrical["abnormal_event_observed"],
        "temperature_within_reviewed_gate": temperature["within_reviewed_gate"],
        "no_unexplained_hotspot": not temperature["unexplained_hotspot"],
        "same_esp_boot": esp["same_boot_continuity"],
        "job_continuity_observed": esp["job_continuity_observed"],
        "no_esp_reset": not esp["reset_observed"],
        "no_visual_damage_or_crack": not anomaly["visual_damage_or_crack"],
        "no_worsening_controller_divergence": not anomaly[
            "controller_divergence_worsening"
        ],
        "no_busy_anomaly": not anomaly["busy_anomaly"],
        "no_odor_smoke_arc_or_noise": not anomaly["odor_smoke_arc_or_noise"],
        "evidence_complete": not anomaly["evidence_missing"],
    }
    reasons = [name for name, passed in checks.items() if not passed]
    return {
        "checks": checks,
        "all_recorded_checks_pass": not reasons,
        "classification": (
            "RECORDED_WITHOUT_STOP_CONDITION"
            if not reasons
            else "STOP_AND_REVIEW_DO_NOT_RETRY"
        ),
    }, reasons


def analyze_observation(
    campaign_file: Path,
    panel_file: Path,
    build_sidecar_file: Path,
    firmware_binary_file: Path,
    observation_file: Path,
) -> dict[str, Any]:
    """Create a descriptive-only verdict from one manual observation file."""

    campaign, campaign_payload = _load_validated_campaign(
        campaign_file, panel_file, build_sidecar_file, firmware_binary_file
    )
    try:
        raw_observation, observation_payload = campaign_tool.read_strict_json(
            observation_file, label="EC5 manual observation"
        )
    except campaign_tool.EC5CampaignError as error:
        raise EC5AnalyzerError(str(error)) from error
    observation = validate_observation(raw_observation, campaign)
    safety, stop_reasons = _safety_review(observation)
    roi_classes = [item["classification"] for item in observation["roi_observations"]]
    roi_unresolved = any(
        item in {"mixed-or-unstable", "not-observed"} for item in roi_classes
    ) or not all(
        item["stable_for_entire_observation"]
        for item in observation["roi_observations"]
    )
    if stop_reasons:
        verdict_code = "DESCRIPTIVE_STOP_AND_REVIEW"
        interpretation: Optional[str] = None
        reasons = stop_reasons
    elif roi_unresolved:
        verdict_code = "DESCRIPTIVE_INCONCLUSIVE"
        interpretation = (
            "One or both fixed ROIs were manually recorded as unresolved; no alias "
            "or safety meaning is inferred."
        )
        reasons = ["roi_observation_unresolved"]
    else:
        verdict_code = "DESCRIPTIVE_OBSERVATION_RECORDED"
        interpretation = (
            "The two fixed ROI labels are a manual description of this one bound "
            "U04/white pilot only."
        )
        reasons = []
    binding = campaign["physical_binding"]
    build = binding["build_sidecar"]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "campaign_binding": {
            "campaign_file_sha256": campaign_tool.sha256(campaign_payload),
            "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
            "action_identity_sha256": campaign["actions"][0][
                "action_identity_sha256"
            ],
            "test_id": campaign_tool.TEST_ID,
            "candidate_code": campaign_tool.U04_CODE,
            "intended_initial_code": campaign_tool.WHITE_CODE,
            "frame_sha256": campaign_tool.U04_FRAME_SHA256,
            "cs1_dtm_sha256": campaign_tool.U04_DTM_SHA256,
            "cs2_dtm_sha256": campaign_tool.U04_DTM_SHA256,
        },
        "observation_binding": {
            "observation_id": observation["observation_id"],
            "observation_file_sha256": campaign_tool.sha256(observation_payload),
            "observed_at": observation["observed_at"],
            "lineage": observation["lineage"],
        },
        "panel": dict(binding["panel"]),
        "firmware_build": {
            "build_tag": build["build_tag"],
            "firmware_commit": build["firmware_commit"],
            "binary_sha256": build["binary_sha256"],
            "config_sha256": build["config_sha256"],
            "manifest_payload_sha256": build["manifest_payload_sha256"],
            "candidate_id": build["candidate_id"],
            "candidate_code": build["candidate_code"],
        },
        "roi_summary": {
            "ordered_observations": observation["roi_observations"],
            "classifications_match": roi_classes[0] == roi_classes[1],
            "both_stable_for_entire_observation": all(
                item["stable_for_entire_observation"]
                for item in observation["roi_observations"]
            ),
            "descriptive_interpretation": interpretation,
        },
        "hold_summary": {
            **observation["hold"],
            "hold_qualification_claimed": False,
        },
        "safety_review": safety,
        "verdict": {
            "code": verdict_code,
            "reasons": reasons,
            "descriptive_only": True,
            "qualification_state": "NOT_QUALIFIED",
        },
        "progression_gate": {
            "u04_other_initial_states_authorized": False,
            "u04_repeats_authorized": False,
            "u04_hold_study_authorized": False,
            "u07_build_or_action_authorized": False,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "separate_review_and_new_authorization_required": True,
            "do_not_retry_this_test_id": True,
        },
        "classification": {
            "offline_analysis": True,
            "manual_hardware_observation_recorded": True,
            "hardware_io_performed_by_analyzer": False,
            "network_io_performed_by_analyzer": False,
            "serial_io_performed_by_analyzer": False,
            "descriptive_single_pilot_only": True,
            "unknown_code_safe_claimed": False,
            "physical_color_alias_claimed": False,
            "waveform_modification_claimed": False,
            "repeatability_claimed": False,
            "hold_behavior_qualified": False,
            "recovery_qualified": False,
            "u07_qualified": False,
            "production_qualification_claimed": False,
            "qualification_state": "NOT_QUALIFIED",
        },
    }
    result = {
        **unsigned,
        "integrity": {
            "canonical_sha256": campaign_tool.sha256(unsigned),
            "canonical_sha256_scope": HASH_SCOPE,
        },
    }
    return dict(
        validate_analysis(
            result,
            campaign_file,
            panel_file,
            build_sidecar_file,
            firmware_binary_file,
            observation_file,
            reanalyze=False,
        )
    )


def validate_analysis(
    analysis: Mapping[str, Any],
    campaign_file: Path,
    panel_file: Path,
    build_sidecar_file: Path,
    firmware_binary_file: Path,
    observation_file: Path,
    *,
    reanalyze: bool = True,
) -> Mapping[str, Any]:
    """Validate an analysis and, by default, replay it from all local inputs."""

    _exact(analysis, label="EC5 analysis", keys=_ANALYSIS_KEYS)
    unsigned = dict(analysis)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": campaign_tool.sha256(unsigned),
        "canonical_sha256_scope": HASH_SCOPE,
    }:
        raise EC5AnalyzerError("EC5 analysis integrity is invalid")
    classification = analysis["classification"]
    progression = analysis["progression_gate"]
    verdict = analysis["verdict"]
    if (
        analysis["schema_version"] != SCHEMA_VERSION
        or analysis["kind"] != ANALYSIS_KIND
        or not isinstance(classification, Mapping)
        or classification.get("descriptive_single_pilot_only") is not True
        or classification.get("unknown_code_safe_claimed") is not False
        or classification.get("physical_color_alias_claimed") is not False
        or classification.get("waveform_modification_claimed") is not False
        or classification.get("production_qualification_claimed") is not False
        or classification.get("qualification_state") != "NOT_QUALIFIED"
        or not isinstance(progression, Mapping)
        or any(
            progression.get(field) is not False
            for field in (
                "u04_other_initial_states_authorized",
                "u04_repeats_authorized",
                "u04_hold_study_authorized",
                "u07_build_or_action_authorized",
                "automatic_retry_authorized",
                "automatic_recovery_authorized",
            )
        )
        or not isinstance(verdict, Mapping)
        or verdict.get("descriptive_only") is not True
        or verdict.get("qualification_state") != "NOT_QUALIFIED"
    ):
        raise EC5AnalyzerError("EC5 analysis widened a descriptive-only boundary")
    if reanalyze:
        expected = analyze_observation(
            campaign_file,
            panel_file,
            build_sidecar_file,
            firmware_binary_file,
            observation_file,
        )
        if analysis != expected:
            raise EC5AnalyzerError("EC5 analysis differs from its actual evidence")
    return analysis


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze", allow_abbrev=False)
    validate_parser = subparsers.add_parser("validate", allow_abbrev=False)
    for current in (analyze_parser, validate_parser):
        current.add_argument("--campaign", type=Path, required=True)
        current.add_argument("--panel", type=Path, required=True)
        current.add_argument("--build-sidecar", type=Path, required=True)
        current.add_argument("--firmware-binary", type=Path, required=True)
        current.add_argument("--observation", type=Path, required=True)
    analyze_parser.add_argument("--output", type=Path, required=True)
    validate_parser.add_argument("--analysis", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        common = (
            args.campaign,
            args.panel,
            args.build_sidecar,
            args.firmware_binary,
            args.observation,
        )
        if args.command == "analyze":
            result = analyze_observation(*common)
            campaign_tool.publish_new_json(
                args.output, result, label="EC5 descriptive analysis output"
            )
        else:
            value, _payload = campaign_tool.read_strict_json(
                args.analysis, label="EC5 descriptive analysis"
            )
            result = validate_analysis(value, *common)
    except (EC5AnalyzerError, campaign_tool.EC5CampaignError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ANALYSIS_KIND",
    "EC5AnalyzerError",
    "OBSERVATION_KIND",
    "analyze_observation",
    "validate_analysis",
    "validate_observation",
]
