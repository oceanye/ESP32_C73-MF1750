#!/usr/bin/env python3
"""Deep-validate finalized N8 bundles and produce descriptive-only analysis.

No loose photo/temperature/electrical dictionaries are accepted.  Every
input must be a production-format finalized action bundle whose claim, lock,
runtime manifest, reviewed profile, protocol, manual observation,
finalization, result, request audit, camera capture identity, and recursive
prior chain pass the N8 execution validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
)
from tools import g1_s1_n8_execution_contract as execution  # noqa: E402
from tools.g1_s1_n8_carryover_campaign import (  # noqa: E402
    CAMPAIGN_ID,
    N8_SEQUENCE_IDS,
)
from tools.g1_s1_rc2g_n2_photo_campaign_once import (  # noqa: E402
    N2PFixedActionError,
    _strict_json_file,
)


SCHEMA_VERSION = 1
LEDGER_KIND = "mf1750-g1-s1-n8-deep-bundle-sequence-ledger"
REPORT_KIND = "mf1750-g1-s1-n8-deep-bundle-descriptive-analysis"
LEDGER_HASH_SCOPE = (
    "entire N8 deep-bundle sequence ledger excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
REPORT_HASH_SCOPE = LEDGER_HASH_SCOPE.replace("sequence ledger", "descriptive analysis")

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
ELECTRICAL_FIELDS = (
    "pre_voltage_v",
    "pre_idle_current_a",
    "post_voltage_v",
    "post_idle_current_a",
    "peak_current_a",
)


class N8AnalysisError(ValueError):
    """Finalized N8 evidence or a derived report failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8AnalysisError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {"canonical_sha256": _sha256(unsigned), "canonical_sha256_scope": scope}


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise N8AnalysisError(
            f"{label} keys changed; missing={sorted(keys - actual)}, extra={sorted(actual - keys)}"
        )
    return value


def _number(value: Any, *, label: str, minimum: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N8AnalysisError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise N8AnalysisError(f"{label} is outside the finite range")
    return result


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise N8AnalysisError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def summarize_numeric(
    values: Sequence[int | float],
    *,
    u95_values: Optional[Sequence[int | float]] = None,
    u95_evidence_sha256s: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Summarize observations; n<10 never receives a P95/P99 label."""

    numeric = [_number(value, label=f"summary value {index}") for index, value in enumerate(values)]
    if not numeric:
        raise N8AnalysisError("cannot summarize an empty sample")
    if (u95_values is None) != (u95_evidence_sha256s is None):
        raise N8AnalysisError("U95 values and exact evidence SHAs must be supplied together")
    u95: Optional[list[float]] = None
    evidence: Optional[list[str]] = None
    if u95_values is not None and u95_evidence_sha256s is not None:
        if len(u95_values) != len(numeric) or len(u95_evidence_sha256s) != len(numeric):
            raise N8AnalysisError("U95 evidence count differs from sample count")
        u95 = [_number(value, label=f"summary U95 {index}", minimum=0) for index, value in enumerate(u95_values)]
        evidence = [_require_sha256(value, label=f"summary U95 evidence {index}") for index, value in enumerate(u95_evidence_sha256s)]
    maximum_index = max(range(len(numeric)), key=numeric.__getitem__)
    maximum = numeric[maximum_index]
    small = len(numeric) < 10
    ordered = sorted(numeric)

    def nearest_rank(proportion: float) -> float:
        rank = math.ceil(proportion * len(ordered))
        return ordered[max(0, rank - 1)]

    return {
        "n": len(numeric),
        "minimum_observed": min(numeric),
        "mean": sum(numeric) / len(numeric),
        "maximum_observed": maximum,
        "maximum_observed_u95": u95[maximum_index] if u95 is not None else None,
        "maximum_plus_u95": maximum + u95[maximum_index] if u95 is not None else None,
        "u95_evidence_sha256": evidence[maximum_index] if evidence is not None else None,
        "u95_reported_only_with_exact_evidence": True,
        "p95": None if small else nearest_rank(0.95),
        "p99": None if small else nearest_rank(0.99),
        "percentile_method": None if small else "nearest-rank-ceiling-v1",
        "extreme_reporting": (
            "maximum-observed-plus-u95-if-evidenced-n-less-than-10"
            if small else "nearest-rank-percentiles"
        ),
    }


def validate_n8_action_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the one accepted analyzer input boundary."""

    try:
        return execution.validate_n8_finalized_action_bundle(
            execution.compile_n8_execution_contract(), bundle
        )
    except execution.N8ExecutionContractError as error:
        raise N8AnalysisError(f"N8 finalized bundle failed deep validation: {error}") from error


def _derived_observation(bundle: Mapping[str, Any], validated: Mapping[str, Any]) -> dict[str, Any]:
    observation = validated["observation"]
    camera = observation["camera"]
    thermal = observation["external_temperature"]
    electrical = observation["electrical"]
    manifest = bundle["manifest"]
    profile = bundle["profile"]
    runtime_comparability = {
        "panel": manifest["panel"],
        "firmware": manifest["firmware"],
        "binding_registry": manifest["binding_registry"],
        "measurement_registry": manifest["measurement_registry"],
        "temperature_bin_plan": manifest["temperature_bin_plan"],
        "reviewed_profile_static": {
            key: value
            for key, value in profile.items()
            if key not in {"usage", "integrity"}
        },
    }
    return {
        "action_key": validated["action_key"],
        "action_identity_sha256": validated["action_identity_sha256"],
        "sequence_id": validated["sequence_id"],
        "ordinal": validated["ordinal"],
        "role": validated["role"],
        "state": validated["state"],
        "bundle_file_sha256": _sha256(bundle),
        "result_file_sha256": validated["result_file_sha256"],
        "finalization_file_sha256": validated["finalization_file_sha256"],
        "prior_bundle_file_sha256": validated["prior_bundle_file_sha256"],
        "completed_job_id": validated["completed_job_id"],
        "completed_operation_id": validated["completed_operation_id"],
        "runtime_comparability_sha256": _sha256(runtime_comparability),
        "ghosting_score": observation["visual"]["ghosting_score"],
        "artifact_severity_score": observation["visual"]["artifact_severity_score"],
        "external_temperature": _snapshot(thermal),
        "electrical": _snapshot(electrical),
        "camera": {
            "capture_file_sha256": camera["capture_file_sha256"],
            "capture_evidence_sha256": camera["capture_evidence_sha256"],
            "body_asset_sha256": camera["body_asset_sha256"],
            "lens_asset_sha256": camera["lens_asset_sha256"],
            "mount_asset_sha256": camera["mount_asset_sha256"],
            "fixed_exposure_profile_sha256": camera["fixed_exposure_profile_sha256"],
            "crop_asset_sha256": camera["crop_asset_sha256"],
            "illumination_asset_sha256": camera["illumination_asset_sha256"],
        },
        "visual_pass": observation["visual_pass"],
        "electrical_pass": observation["electrical_pass"],
        "thermal_pass": observation["thermal_pass"],
        "temperature_bin_pass": observation["temperature_bin_pass"],
        "continuity_pass": observation["continuity_pass"],
        "execution_evidence_verified": True,
        "qualification_state": "NOT_QUALIFIED",
    }


def _metric_summaries(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summaries = {
        "visual.ghosting_score": summarize_numeric([item["ghosting_score"] for item in observations]),
        "visual.artifact_severity_score": summarize_numeric([item["artifact_severity_score"] for item in observations]),
        "external_temperature.session_max_c": summarize_numeric(
            [item["external_temperature"]["session_max_c"] for item in observations],
            u95_values=[item["external_temperature"]["uncertainty_u95_c"] for item in observations],
            u95_evidence_sha256s=[item["external_temperature"]["uncertainty_evidence_sha256"] for item in observations],
        ),
    }
    for field in ELECTRICAL_FIELDS:
        summaries[f"electrical.{field}"] = summarize_numeric(
            [item["electrical"][field] for item in observations]
        )
    for field in TIMING_FIELDS:
        summaries[f"timing.{field}"] = summarize_numeric(
            [item["electrical"]["timing_ms"][field] for item in observations]
        )
    return summaries


def _aba_evidence(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_role = {item["role"]: item for item in observations}

    def evidence(role: str) -> Optional[dict[str, Any]]:
        item = by_role.get(role)
        if item is None:
            return None
        return {
            "action_identity_sha256": item["action_identity_sha256"],
            "bundle_file_sha256": item["bundle_file_sha256"],
            "capture_file_sha256": item["camera"]["capture_file_sha256"],
            "fixed_exposure_profile_sha256": item["camera"]["fixed_exposure_profile_sha256"],
            "crop_asset_sha256": item["camera"]["crop_asset_sha256"],
            "ghosting_score": item["ghosting_score"],
        }

    a1, b, a2 = evidence("A1"), evidence("B"), evidence("A2")
    present = a1 is not None and b is not None and a2 is not None
    same_exposure = bool(
        present
        and a1["fixed_exposure_profile_sha256"]
        == b["fixed_exposure_profile_sha256"]
        == a2["fixed_exposure_profile_sha256"]
    )
    same_crop = bool(
        present
        and a1["crop_asset_sha256"] == b["crop_asset_sha256"] == a2["crop_asset_sha256"]
    )
    comparable = present and same_exposure and same_crop
    return {
        "primer_role": "MAP",
        "primer_is_carryover_target": False,
        "direct_visible_history_role": "B",
        "comparison_roles": ["A1", "A2"],
        "A1": a1,
        "B": b,
        "A2": a2,
        "same_fixed_exposure": same_exposure,
        "same_crop": same_crop,
        "comparable": comparable,
        "a2_minus_a1_ghosting_score": (
            float(a2["ghosting_score"]) - float(a1["ghosting_score"])
            if comparable else None
        ),
        "qualification_state": "NOT_QUALIFIED",
    }


def _comparability(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    camera_fields = (
        "body_asset_sha256",
        "lens_asset_sha256",
        "mount_asset_sha256",
        "fixed_exposure_profile_sha256",
        "crop_asset_sha256",
        "illumination_asset_sha256",
    )
    camera_assets = {
        field: sorted({item["camera"][field] for item in observations})
        for field in camera_fields
    }
    temperature_fields = (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "measurement_location_sha256",
        "uncertainty_u95_c",
    )
    temperature_assets = {
        field: sorted({item["external_temperature"][field] for item in observations})
        for field in temperature_fields
    }
    captures = [item["camera"]["capture_file_sha256"] for item in observations]
    capture_evidence = [item["camera"]["capture_evidence_sha256"] for item in observations]
    meter_assets = sorted({item["electrical"]["meter_asset_sha256"] for item in observations})
    clock_assets = sorted({item["electrical"]["clock_asset_sha256"] for item in observations})
    runtime_bindings = sorted(
        {item["runtime_comparability_sha256"] for item in observations}
    )
    fixed = (
        all(len(values) == 1 for values in camera_assets.values())
        and all(len(values) == 1 for values in temperature_assets.values())
        and len(meter_assets) == 1
        and len(clock_assets) == 1
        and len(runtime_bindings) == 1
    )
    unique = len(captures) == len(set(captures)) and len(capture_evidence) == len(set(capture_evidence))
    return {
        "camera_assets": camera_assets,
        "external_temperature_assets": temperature_assets,
        "electrical_meter_asset_sha256s": meter_assets,
        "timing_clock_asset_sha256s": clock_assets,
        "runtime_panel_firmware_profile_and_method_binding_sha256s": runtime_bindings,
        "raw_capture_count": len(captures),
        "unique_raw_capture_file_count": len(set(captures)),
        "unique_capture_evidence_count": len(set(capture_evidence)),
        "fixed_measurement_assets": fixed,
        "no_capture_or_capture_evidence_replay": unique,
        "comparable": fixed and unique,
    }


def build_n8_sequence_ledger(
    *, sequence_id: str, bundles: Sequence[Mapping[str, Any]], _skip_validation: bool = False
) -> dict[str, Any]:
    """Build one exact sequence prefix exclusively from deep bundles."""

    if sequence_id not in N8_SEQUENCE_IDS:
        raise N8AnalysisError("unknown N8 sequence")
    contract = execution.compile_n8_execution_contract()
    expected_rows = [item for item in contract["fixed_actions"] if item["sequence_id"] == sequence_id]
    if len(bundles) > len(expected_rows):
        raise N8AnalysisError("sequence has more bundles than frozen actions")
    observations: list[dict[str, Any]] = []
    abnormal_seen = False
    for index, bundle in enumerate(bundles):
        if abnormal_seen:
            raise N8AnalysisError("sequence contains an action after finalized FAIL")
        validated = validate_n8_action_bundle(bundle)
        expected = expected_rows[index]
        if (
            validated["action_key"] != expected["action_key"]
            or validated["sequence_id"] != sequence_id
            or validated["ordinal"] != index + 1
        ):
            raise N8AnalysisError("bundles are not the exact ordered sequence prefix")
        if index == 0:
            if validated["prior_bundle_file_sha256"] is not None:
                raise N8AnalysisError("sequence root unexpectedly binds prior bundle")
        elif validated["prior_bundle_file_sha256"] != observations[-1]["bundle_file_sha256"]:
            raise N8AnalysisError("target-to-target finalized bundle SHA chain is broken")
        observation = _derived_observation(bundle, validated)
        observations.append(observation)
        abnormal_seen = validated["state"] != ResultState.PASS.value
    complete = len(observations) == len(expected_rows) and not abnormal_seen
    next_action = None if abnormal_seen or complete else expected_rows[len(observations)]["action_identity_sha256"]
    remaining = [] if abnormal_seen else [item["action_identity_sha256"] for item in expected_rows[len(observations):]]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": LEDGER_KIND,
        "campaign_id": CAMPAIGN_ID,
        "sequence_id": sequence_id,
        "power_mode": expected_rows[0]["power_mode"],
        "temperature_bin_id": expected_rows[0]["temperature_bin_id"],
        "bundle_bindings": [
            {
                "action_identity_sha256": item["action_identity_sha256"],
                "bundle_file_sha256": item["bundle_file_sha256"],
                "result_file_sha256": item["result_file_sha256"],
                "finalization_file_sha256": item["finalization_file_sha256"],
                "execution_evidence_verified": True,
            }
            for item in observations
        ],
        "derived_observations": observations,
        "observed_action_count": len(observations),
        "planned_action_count": len(expected_rows),
        "complete": complete,
        "terminal_state": (
            "FINALIZED_FAIL_STOP_NO_RETRY" if abnormal_seen
            else "EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY" if complete
            else None
        ),
        "qualification_state": "NOT_QUALIFIED",
        "next_action_identity_sha256": next_action,
        "remaining_action_identity_sha256s": remaining,
        "stop_remaining_actions": abnormal_seen,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "metric_summaries": _metric_summaries(observations) if observations else None,
        "aba_evidence": _aba_evidence(observations) if sequence_id == N8_SEQUENCE_IDS[0] else None,
    }
    ledger = {**unsigned, "integrity": _integrity(unsigned, LEDGER_HASH_SCOPE)}
    if not _skip_validation:
        validate_n8_sequence_ledger(ledger, bundles=bundles)
    return ledger


def validate_n8_sequence_ledger(
    ledger: Mapping[str, Any], *, bundles: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    root = _exact(
        ledger, label="N8 sequence ledger",
        keys={"schema_version", "kind", "campaign_id", "sequence_id", "power_mode", "temperature_bin_id", "bundle_bindings", "derived_observations", "observed_action_count", "planned_action_count", "complete", "terminal_state", "qualification_state", "next_action_identity_sha256", "remaining_action_identity_sha256s", "stop_remaining_actions", "automatic_advance", "automatic_retry", "automatic_recovery", "metric_summaries", "aba_evidence", "integrity"},
    )
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, LEDGER_HASH_SCOPE):
        raise N8AnalysisError("N8 ledger canonical integrity changed")
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != LEDGER_KIND or root["campaign_id"] != CAMPAIGN_ID or root["qualification_state"] != "NOT_QUALIFIED":
        raise N8AnalysisError("N8 ledger identity or qualification changed")
    rebuilt = build_n8_sequence_ledger(
        sequence_id=root["sequence_id"], bundles=bundles, _skip_validation=True
    )
    if rebuilt != root:
        raise N8AnalysisError("N8 ledger derived content changed")
    return root


def analyze_n8_bundles(
    *, bundles: Sequence[Mapping[str, Any]], _skip_validation: bool = False
) -> dict[str, Any]:
    """Analyze exact finalized bundles; campaign qualification always remains false."""

    validated_pairs = [(bundle, validate_n8_action_bundle(bundle)) for bundle in bundles]
    action_shas = [item[1]["action_identity_sha256"] for item in validated_pairs]
    if len(action_shas) != len(set(action_shas)):
        raise N8AnalysisError("analysis contains a duplicate/replayed action bundle")
    grouped: dict[str, list[Mapping[str, Any]]] = {sequence_id: [] for sequence_id in N8_SEQUENCE_IDS}
    for bundle, validated in validated_pairs:
        grouped[validated["sequence_id"]].append(bundle)
    ledgers = []
    for sequence_id in N8_SEQUENCE_IDS:
        sequence_bundles = sorted(
            grouped[sequence_id],
            key=lambda item: int(item["evidence"]["ordinal"]),
        )
        if sequence_bundles:
            ledgers.append(build_n8_sequence_ledger(sequence_id=sequence_id, bundles=sequence_bundles))
    observations = [item for ledger in ledgers for item in ledger["derived_observations"]]
    any_abnormal = any(ledger["stop_remaining_actions"] for ledger in ledgers)
    complete = len(ledgers) == 5 and all(ledger["complete"] for ledger in ledgers)
    comparability = _comparability(observations) if observations else None
    if comparability is not None and not comparability["comparable"]:
        raise N8AnalysisError("fixed measurement assets or unique camera evidence are not comparable")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "campaign_id": CAMPAIGN_ID,
        "execution_contract_canonical_sha256": execution.compile_n8_execution_contract()["integrity"]["canonical_sha256"],
        "bundle_count": len(validated_pairs),
        "sequence_ledger_count": len(ledgers),
        "complete": complete,
        "analysis_ready": complete and not any_abnormal and bool(comparability and comparability["comparable"]),
        "terminal_state": (
            "FINALIZED_FAIL_STOP_NO_RETRY" if any_abnormal
            else "EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY" if complete
            else None
        ),
        "qualification_state": "NOT_QUALIFIED",
        "hardware_qualified": False,
        "algorithm_qualified": False,
        "stop_remaining_actions": any_abnormal,
        "bundle_bindings": {
            validated["action_identity_sha256"]: _sha256(bundle)
            for bundle, validated in validated_pairs
        },
        "ledger_bindings": {
            ledger["sequence_id"]: ledger["integrity"]["canonical_sha256"]
            for ledger in ledgers
        },
        "sequence_summaries": {
            ledger["sequence_id"]: {
                "complete": ledger["complete"],
                "terminal_state": ledger["terminal_state"],
                "observed_action_count": ledger["observed_action_count"],
                "metric_summaries": ledger["metric_summaries"],
                "aba_evidence": ledger["aba_evidence"],
            }
            for ledger in ledgers
        },
        "overall_metric_summaries": _metric_summaries(observations) if observations else None,
        "measurement_comparability": comparability,
        "temperature_bin_sessions": {
            sequence_id: {
                "temperature_bin_id": next(
                    ledger["temperature_bin_id"] for ledger in ledgers
                    if ledger["sequence_id"] == sequence_id
                ),
                "session_observation_count": 1,
                "population_inference_allowed": False,
            }
            for sequence_id in N8_SEQUENCE_IDS[2:]
            if any(ledger["sequence_id"] == sequence_id for ledger in ledgers)
        },
        "interpretation": {
            "descriptive_only": True,
            "causal_carryover_qualified": False,
            "aba_map_is_primer_not_carryover_target": True,
            "aba_b_is_direct_visible_history_for_a2": True,
            "temperature_observations_per_bin": 1,
            "population_inference_allowed": False,
            "causal_threshold_conclusion_allowed": False,
            "small_sample_rule": "n<10: no P95/P99; max plus U95 only with exact U95 evidence",
        },
        "classification": {
            "offline_analysis": True,
            "input_requires_deep_verified_finalized_bundles": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    report = {**unsigned, "integrity": _integrity(unsigned, REPORT_HASH_SCOPE)}
    if not _skip_validation:
        validate_n8_report(report, bundles=bundles)
    return report


def validate_n8_report(
    report: Mapping[str, Any], *, bundles: Sequence[Mapping[str, Any]], _skip_rebuild: bool = False
) -> Mapping[str, Any]:
    root = _exact(
        report, label="N8 analysis report",
        keys={"schema_version", "kind", "campaign_id", "execution_contract_canonical_sha256", "bundle_count", "sequence_ledger_count", "complete", "analysis_ready", "terminal_state", "qualification_state", "hardware_qualified", "algorithm_qualified", "stop_remaining_actions", "bundle_bindings", "ledger_bindings", "sequence_summaries", "overall_metric_summaries", "measurement_comparability", "temperature_bin_sessions", "interpretation", "classification", "integrity"},
    )
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, REPORT_HASH_SCOPE):
        raise N8AnalysisError("N8 report canonical integrity changed")
    if (
        root["schema_version"] != SCHEMA_VERSION or root["kind"] != REPORT_KIND
        or root["campaign_id"] != CAMPAIGN_ID or root["qualification_state"] != "NOT_QUALIFIED"
        or root["hardware_qualified"] is not False or root["algorithm_qualified"] is not False
        or root["interpretation"]["descriptive_only"] is not True
        or root["classification"]["input_requires_deep_verified_finalized_bundles"] is not True
    ):
        raise N8AnalysisError("N8 report identity/qualification policy changed")
    if not _skip_rebuild:
        rebuilt = analyze_n8_bundles(bundles=bundles, _skip_validation=True)
        if rebuilt != root:
            raise N8AnalysisError("N8 report derived content changed")
    return root


def load_bundle_file(path: Path) -> Mapping[str, Any]:
    try:
        bundle, payload = _strict_json_file(path, label="N8 analyzer bundle")
    except N2PFixedActionError as error:
        raise N8AnalysisError(str(error)) from error
    if payload != canonical_json_bytes(bundle):
        raise N8AnalysisError("N8 analyzer input bundle is not canonical JSON bytes")
    validate_n8_action_bundle(bundle)
    return bundle


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, action="append", required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    report = analyze_n8_bundles(bundles=[load_bundle_file(path) for path in args.bundle])
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
