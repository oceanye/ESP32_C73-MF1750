#!/usr/bin/env python3
"""Offline-only N4 V3 four-cell result ingestion and 2x2 analysis.

This module binds the frozen root-cause 2x2 V3 manifest, joint proof, exact
MAP/target P0 action identities, and strict previews.  It accepts only the
runner's deeply cross-bound claim/lock/profile/protocol/observation/
finalization/result bundles; visual, electrical, and thermal values are
derived from those validated bundles rather than accepted as a second loose
input.  It has no executor, network client, device path, claim writer,
authorization generator, retry path, or recovery path.

One observation per cell is descriptive only.  A complete four-cell evidence
chain is never a causal, population, visual-quality, electrical, or hardware
qualification.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence

from host.visible_refresh_campaign import (
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
)
from tools import g1_s1_root_cause_2x2_v3 as v3
from tools import g1_s1_n4_v3_execution_contract as execution_contract


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-g1-s1-n4-v3-offline-analysis-contract"
OBSERVATION_KIND = "mf1750-g1-s1-n4-v3-cell-observation"
REPORT_KIND = "mf1750-g1-s1-n4-v3-factorial-analysis"

CONTRACT_HASH_SCOPE = (
    "entire N4 V3 analysis contract excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
OBSERVATION_HASH_SCOPE = CONTRACT_HASH_SCOPE.replace(
    "analysis contract", "cell observation"
)
REPORT_HASH_SCOPE = CONTRACT_HASH_SCOPE.replace("analysis contract", "analysis report")

# Compile-time checks make later default-contract drift explicit.
EXPECTED_CONTRACT_CANONICAL_SHA256: Optional[str] = (
    "b370748008844dc5ece026ed44b4dda124da8f0f6c62caed70656bc118e4dae8"
)
EXPECTED_CONTRACT_FILE_SHA256: Optional[str] = (
    "d0d467348e7d60cc7f9ccbcf2eb1f58b027e5551a12e7f13c023d29e91ad98cb"
)

CELL_ORDER = tuple(v3.CAMPAIGN_CELL_ORDER)
FACTORIAL_CELLS = (
    "low-balanced",
    "low-unbalanced",
    "high-balanced",
    "high-unbalanced",
)
VISUAL_METRICS = (
    "fidelity_score",
    "ghosting_score",
    "artifact_severity_score",
)
ELECTRICAL_METRICS = (
    "map_peak_current_a",
    "target_peak_current_a",
    "map_job_duration_ms",
    "target_job_duration_ms",
    "session_max_temperature_c",
    "target_voltage_droop_v",
)
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
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
STRICT_PREVIEW_SHA256S = {
    "low-balanced": "bb5bb62286429217a65a85a9076418afaa6587b34f745e1ec3332bee10eacd15",
    "low-unbalanced": "c8a89c15b0d3300ff768629f5e846678f11f5e238f75acd16d3a1ea2486c835e",
    "high-balanced": "cf183f80631d10036faa1f9b5aa247a3a25e5e29b1a5a2fdd7de7c11658f1ad0",
    "high-unbalanced": "b20dfbc15e7e6393177d7a1793896fc6d7d66ab975fd325098be8d21ce4fb6fd",
}


class N4V3AnalysisError(ValueError):
    """An N4 V3 analysis contract, observation, or report failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N4V3AnalysisError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N4V3AnalysisError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise N4V3AnalysisError(f"{label} keys changed; missing={missing}, extra={extra}")
    return value


def _require_sha256(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise N4V3AnalysisError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
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
        raise N4V3AnalysisError(f"{label} must be a finite number{suffix}")
    result = float(value)
    if not math.isfinite(result):
        raise N4V3AnalysisError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N4V3AnalysisError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N4V3AnalysisError(f"{label} is above {maximum}")
    return result


@lru_cache(maxsize=1)
def _execution_bundle_bytes() -> bytes:
    try:
        contract = execution_contract.compile_n4_v3_execution_contract()
        execution_contract.validate_n4_v3_execution_contract(contract)
    except execution_contract.N4V3ExecutionContractError as error:
        raise N4V3AnalysisError(
            f"shared N4 V3 execution contract is invalid: {error}"
        ) from error
    payload = canonical_json_bytes(contract)
    if hashlib.sha256(payload).hexdigest() != execution_contract.EXPECTED_CONTRACT_FILE_SHA256:
        raise N4V3AnalysisError("shared N4 V3 execution contract file identity changed")
    return payload


def _execution_bundle() -> Mapping[str, Any]:
    return json.loads(_execution_bundle_bytes().decode("utf-8"))


def _preregistration() -> dict[str, Any]:
    return {
        "design": "complete-2x2-one-independent-map-target-session-per-cell",
        "cell_order": list(CELL_ORDER),
        "factor_A": {
            "name": "controller_internal_spatial_frequency",
            "low_level": "low",
            "high_level": "high",
            "main_effect": "mean(high)-mean(low)",
        },
        "factor_B": {
            "name": "left_right_pigment_transition_load",
            "low_level": "balanced",
            "high_level": "unbalanced",
            "main_effect": "mean(unbalanced)-mean(balanced)",
        },
        "interaction": {
            "name": "spatial_frequency_x_half_load",
            "effect": (
                "mean(high-unbalanced,low-balanced)-"
                "mean(high-balanced,low-unbalanced)"
            ),
            "difference_of_differences": (
                "(high-unbalanced-high-balanced)-"
                "(low-unbalanced-low-balanced)"
            ),
        },
        "outcome_groups": {
            "visual": list(VISUAL_METRICS),
            "electrical": list(ELECTRICAL_METRICS),
            "joint_visual_electrical_score_defined": False,
        },
        "cross_cell_comparability": {
            "visual_observation_kind_fixed": True,
            "visual_protocol_fixed": True,
            "observer_or_camera_asset_fixed": True,
            "fixed_exposure_profile_fixed_when_camera": True,
            "roi_definition_fixed": True,
            "meter_asset_fixed": True,
            "clock_asset_fixed": True,
            "temperature_sensor_and_calibration_fixed": True,
            "temperature_uncertainty_contract_fixed": True,
            "per_cell_observation_evidence_must_be_distinct": True,
            "per_cell_temperature_evidence_must_be_distinct": True,
            "per_cell_camera_capture_must_be_distinct_when_camera": True,
        },
        "sample_contract": {
            "observations_per_cell": 1,
            "total_observations": 4,
            "descriptive_only": True,
            "p95_allowed": False,
            "p99_allowed": False,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "qualification_state": "NOT_QUALIFIED",
        },
        "terminal_contract": {
            "any_abnormality": ResultState.UNKNOWN_DO_NOT_RETRY.value,
            "stop_remaining_cells": True,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }


def _cell_contracts(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    campaign = bundle["p0_campaign"]
    source_campaign = bundle["source_p0_campaign"]
    actions = campaign["actions"]
    sessions = campaign["sessions"]
    source_sessions = source_campaign["sessions"]
    result = []
    for index, cell_name in enumerate(CELL_ORDER):
        primer, target = actions[2 * index : 2 * index + 2]
        session = sessions[index]
        source_session = source_sessions[index]
        spatial_frequency, half_load = cell_name.split("-", maxsplit=1)
        if (
            primer["action_identity_sha256"]
            != bundle["fixed_actions"][f"{cell_name}-map-primer"]
            or target["action_identity_sha256"]
            != bundle["fixed_actions"][f"{cell_name}-target"]
        ):
            raise N4V3AnalysisError("N4 V3 fixed action order/identity changed")
        result.append(
            {
                "ordinal": index + 1,
                "cell_id": cell_name,
                "factors": {
                    "controller_internal_spatial_frequency": spatial_frequency,
                    "left_right_pigment_transition_load": half_load,
                },
                "frame_sha256": target["identity"]["frame"]["sha256"],
                "strict_preview_sha256": STRICT_PREVIEW_SHA256S[cell_name],
                "source_session_canonical_sha256": source_session["integrity"][
                    "canonical_sha256"
                ],
                "session_canonical_sha256": session["integrity"]["canonical_sha256"],
                "map_action_identity_sha256": primer["action_identity_sha256"],
                "target_action_identity_sha256": target["action_identity_sha256"],
                "target_requires_map_pass": True,
                "target_requires_map_result_file_sha256": True,
                "independent_session": True,
                "controller_fresh_boot_required": True,
                "own_map_primer_required": True,
                "j2_disconnect_after_nominal_cell_required": False,
                "other_cell_result_accepted": False,
            }
        )
    return result


def compile_n4_v3_analysis_contract(
    *, p0_campaign: Optional[Mapping[str, Any]] = None
) -> dict[str, Any]:
    """Bind the shared frozen execution envelope into an analysis contract."""

    bundle = _execution_bundle()
    selected_campaign = bundle["p0_campaign"]
    if p0_campaign is not None and _snapshot(p0_campaign) != selected_campaign:
        raise N4V3AnalysisError(
            "N4 V3 analyzer accepts only the shared frozen execution P0 campaign"
        )
    source_v3 = {
        **bundle["source_v3"],
        "strict_selected_metric_orthogonality_proven": True,
        "all_reported_spatial_metrics_orthogonality_proven": False,
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": "n4-v3-four-cell-results-analysis-v1",
        "source_v3": source_v3,
        "execution_contract_canonical_sha256": bundle["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": execution_contract.execution_contract_file_sha256(
            bundle
        ),
        "source_p0_campaign": _snapshot(bundle["source_p0_campaign"]),
        "source_p0_campaign_canonical_sha256": bundle[
            "source_p0_campaign_canonical_sha256"
        ],
        "source_p0_campaign_file_sha256": bundle[
            "source_p0_campaign_file_sha256"
        ],
        "p0_campaign": _snapshot(selected_campaign),
        "p0_campaign_canonical_sha256": bundle["p0_campaign_canonical_sha256"],
        "p0_campaign_file_sha256": bundle["p0_campaign_file_sha256"],
        "power_semantics": _snapshot(bundle["power_semantics"]),
        "runner_evidence_contract": _snapshot(bundle["evidence_contract"]),
        "cell_contracts": _cell_contracts(bundle),
        "preregistration": _preregistration(),
        "classification": {
            "offline_compiled": True,
            "software_ready": True,
            "hardware_ready": False,
            "hardware_qualified": False,
            "qualification_state": "NOT_QUALIFIED",
            "runner_evidence_deep_validation_required": True,
            "result_record_alone_accepted": False,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
        "compiler_effects": {
            "source_files_written": 0,
            "result_files_written": 0,
            "claims_created": 0,
            "authorizations_created": 0,
            "network_requests": 0,
            "device_operations": 0,
            "visible_refreshes": 0,
        },
    }
    contract = {**unsigned, "integrity": _integrity(unsigned, CONTRACT_HASH_SCOPE)}
    validate_n4_v3_analysis_contract(contract)
    canonical_sha = contract["integrity"]["canonical_sha256"]
    file_sha = _sha256(contract)
    if (
        EXPECTED_CONTRACT_CANONICAL_SHA256 is not None
        and canonical_sha != EXPECTED_CONTRACT_CANONICAL_SHA256
    ):
        raise N4V3AnalysisError("frozen N4 V3 analysis contract identity changed")
    if (
        EXPECTED_CONTRACT_FILE_SHA256 is not None
        and file_sha != EXPECTED_CONTRACT_FILE_SHA256
    ):
        raise N4V3AnalysisError("frozen N4 V3 analysis contract file identity changed")
    return contract


def validate_n4_v3_analysis_contract(
    contract: Mapping[str, Any]
) -> Mapping[str, Any]:
    root = _exact(
        contract,
        label="N4 V3 analysis contract",
        keys={
            "schema_version",
            "kind",
            "contract_id",
            "source_v3",
            "execution_contract_canonical_sha256",
            "execution_contract_file_sha256",
            "source_p0_campaign",
            "source_p0_campaign_canonical_sha256",
            "source_p0_campaign_file_sha256",
            "p0_campaign",
            "p0_campaign_canonical_sha256",
            "p0_campaign_file_sha256",
            "power_semantics",
            "runner_evidence_contract",
            "cell_contracts",
            "preregistration",
            "classification",
            "compiler_effects",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != CONTRACT_KIND
        or root["contract_id"] != "n4-v3-four-cell-results-analysis-v1"
    ):
        raise N4V3AnalysisError("N4 V3 analysis contract schema/kind/ID changed")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, CONTRACT_HASH_SCOPE):
        raise N4V3AnalysisError("N4 V3 analysis contract integrity is invalid")
    bundle = _execution_bundle()
    expected_source = {
        **bundle["source_v3"],
        "strict_selected_metric_orthogonality_proven": True,
        "all_reported_spatial_metrics_orthogonality_proven": False,
    }
    if root["source_v3"] != expected_source:
        raise N4V3AnalysisError("N4 V3 manifest/proof binding changed")
    expected_execution_file_sha = execution_contract.execution_contract_file_sha256(
        bundle
    )
    if (
        root["execution_contract_canonical_sha256"]
        != bundle["integrity"]["canonical_sha256"]
        or root["execution_contract_file_sha256"] != expected_execution_file_sha
        or root["source_p0_campaign"] != bundle["source_p0_campaign"]
        or root["source_p0_campaign_canonical_sha256"]
        != bundle["source_p0_campaign_canonical_sha256"]
        or root["source_p0_campaign_file_sha256"]
        != bundle["source_p0_campaign_file_sha256"]
        or root["p0_campaign"] != bundle["p0_campaign"]
        or root["p0_campaign_canonical_sha256"]
        != bundle["p0_campaign_canonical_sha256"]
        or root["p0_campaign_file_sha256"] != bundle["p0_campaign_file_sha256"]
        or root["power_semantics"] != bundle["power_semantics"]
        or root["runner_evidence_contract"] != bundle["evidence_contract"]
    ):
        raise N4V3AnalysisError("N4 V3 shared source/execution envelope binding changed")
    if root["cell_contracts"] != _cell_contracts(bundle):
        raise N4V3AnalysisError("N4 V3 cell/frame/preview/action binding changed")
    if root["preregistration"] != _preregistration():
        raise N4V3AnalysisError("N4 V3 factorial preregistration changed")
    if root["classification"] != {
        "offline_compiled": True,
        "software_ready": True,
        "hardware_ready": False,
        "hardware_qualified": False,
        "qualification_state": "NOT_QUALIFIED",
        "runner_evidence_deep_validation_required": True,
        "result_record_alone_accepted": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }:
        raise N4V3AnalysisError("N4 V3 offline classification changed")
    if root["compiler_effects"] != {
        "source_files_written": 0,
        "result_files_written": 0,
        "claims_created": 0,
        "authorizations_created": 0,
        "network_requests": 0,
        "device_operations": 0,
        "visible_refreshes": 0,
    }:
        raise N4V3AnalysisError("N4 V3 compiler side-effect accounting changed")
    return root


def contract_file_sha256(contract: Mapping[str, Any]) -> str:
    return _sha256(validate_n4_v3_analysis_contract(contract))


def frozen_contract_bytes() -> bytes:
    contract = compile_n4_v3_analysis_contract()
    payload = canonical_json_bytes(contract)
    if _sha256(payload) != EXPECTED_CONTRACT_FILE_SHA256:
        raise N4V3AnalysisError("frozen N4 V3 contract whole-file identity changed")
    round_trip = json.loads(payload.decode("utf-8"))
    validate_n4_v3_analysis_contract(round_trip)
    if canonical_json_bytes(round_trip) != payload:
        raise N4V3AnalysisError("frozen N4 V3 contract is not byte-stable")
    return payload


def _cell_context(
    contract: Mapping[str, Any], cell_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    matches = [value for value in contract["cell_contracts"] if value["cell_id"] == cell_id]
    if len(matches) != 1:
        raise N4V3AnalysisError("cell is not uniquely bound to the N4 V3 contract")
    cell = matches[0]
    actions = {
        action["action_identity_sha256"]: action
        for action in contract["p0_campaign"]["actions"]
    }
    return (
        cell,
        actions[cell["map_action_identity_sha256"]],
        actions[cell["target_action_identity_sha256"]],
    )


def _validate_visual(value: Any, *, strict_preview_sha256: str) -> Mapping[str, Any]:
    root = _exact(
        value,
        label="N4 V3 standardized visual observation",
        keys={
            "observation_kind",
            "protocol_sha256",
            "observation_evidence_sha256",
            "reference_preview_sha256",
            "observer_or_camera_asset_sha256",
            "capture_file_sha256",
            "fixed_exposure_profile_sha256",
            "roi_definition_sha256",
            "map_fidelity_pass",
            "target_fidelity_pass",
            "orientation_pass",
            "seam_assessment_pass",
            "fidelity_score",
            "ghosting_score",
            "artifact_severity_score",
        },
    )
    if root["observation_kind"] not in {"standardized-manual", "fixed-camera"}:
        raise N4V3AnalysisError("N4 V3 visual observation kind is invalid")
    for field in (
        "protocol_sha256",
        "observation_evidence_sha256",
        "reference_preview_sha256",
        "observer_or_camera_asset_sha256",
        "roi_definition_sha256",
    ):
        _require_sha256(root[field], label=f"visual {field}")
    if root["reference_preview_sha256"] != strict_preview_sha256:
        raise N4V3AnalysisError("visual observation references another cell preview")
    capture_sha = _require_sha256(
        root["capture_file_sha256"], label="visual capture file", nullable=True
    )
    exposure_sha = _require_sha256(
        root["fixed_exposure_profile_sha256"],
        label="visual fixed exposure profile",
        nullable=True,
    )
    if root["observation_kind"] == "fixed-camera":
        if capture_sha is None or exposure_sha is None:
            raise N4V3AnalysisError("fixed-camera observation requires capture and exposure SHA")
    elif capture_sha is not None or exposure_sha is not None:
        raise N4V3AnalysisError("standardized-manual observation must not imply camera evidence")
    for field in (
        "map_fidelity_pass",
        "target_fidelity_pass",
        "orientation_pass",
        "seam_assessment_pass",
    ):
        if type(root[field]) is not bool:
            raise N4V3AnalysisError(f"visual {field} must be boolean")
    _number(root["fidelity_score"], label="visual fidelity_score", minimum=0, maximum=1)
    _number(root["ghosting_score"], label="visual ghosting_score", minimum=0)
    _number(
        root["artifact_severity_score"],
        label="visual artifact_severity_score",
        minimum=0,
    )
    return root


def _validate_timing(value: Any, *, label: str) -> Mapping[str, Any]:
    root = _exact(value, label=label, keys=set(TIMING_FIELDS))
    for field in TIMING_FIELDS:
        _number(root[field], label=f"{label}.{field}", minimum=0)
    return root


def _validate_action_electrical(value: Any, *, label: str) -> Mapping[str, Any]:
    root = _exact(
        value,
        label=label,
        keys={
            "pre_voltage_v",
            "pre_idle_current_a",
            "post_voltage_v",
            "post_idle_current_a",
            "peak_current_a",
            "constant_voltage_mode",
            "timing_ms",
        },
    )
    for field in (
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
    ):
        _number(root[field], label=f"{label}.{field}", minimum=0)
    if type(root["constant_voltage_mode"]) is not bool:
        raise N4V3AnalysisError(f"{label}.constant_voltage_mode must be boolean")
    _validate_timing(root["timing_ms"], label=f"{label}.timing_ms")
    return root


def _validate_external_temperature(value: Any) -> Mapping[str, Any]:
    root = _exact(
        value,
        label="N4 V3 external temperature evidence",
        keys={
            "pre_map_c",
            "post_map_c",
            "pre_target_c",
            "post_target_c",
            "session_max_c",
            "uncertainty_u95_c",
            "sensor_asset_sha256",
            "calibration_artifact_sha256",
            "map_measurement_evidence_sha256",
            "target_measurement_evidence_sha256",
            "uncertainty_evidence_sha256",
        },
    )
    values = []
    for field in (
        "pre_map_c",
        "post_map_c",
        "pre_target_c",
        "post_target_c",
        "session_max_c",
    ):
        parsed = _number(root[field], label=f"external temperature {field}")
        assert parsed is not None
        values.append(parsed)
    if values[-1] < max(values[:-1]):
        raise N4V3AnalysisError("external session maximum is below a sampled temperature")
    _number(
        root["uncertainty_u95_c"],
        label="external temperature uncertainty U95",
        minimum=0,
    )
    for field in (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "map_measurement_evidence_sha256",
        "target_measurement_evidence_sha256",
        "uncertainty_evidence_sha256",
    ):
        _require_sha256(root[field], label=f"external temperature {field}")
    return root


def _validate_electrical(value: Any) -> Mapping[str, Any]:
    root = _exact(
        value,
        label="N4 V3 electrical observation",
        keys={
            "meter_asset_sha256",
            "clock_asset_sha256",
            "map",
            "target",
            "external_temperature",
            "reviewed_limits_pass",
            "thermal_limits_pass",
            "continuity",
        },
    )
    _require_sha256(root["meter_asset_sha256"], label="electrical meter asset")
    _require_sha256(root["clock_asset_sha256"], label="electrical clock asset")
    _validate_action_electrical(root["map"], label="electrical.map")
    _validate_action_electrical(root["target"], label="electrical.target")
    _validate_external_temperature(root["external_temperature"])
    if type(root["reviewed_limits_pass"]) is not bool:
        raise N4V3AnalysisError("electrical reviewed_limits_pass must be boolean")
    if type(root["thermal_limits_pass"]) is not bool:
        raise N4V3AnalysisError("electrical thermal_limits_pass must be boolean")
    continuity = _exact(
        root["continuity"],
        label="N4 V3 MAP-target continuity",
        keys={
            "controller_reboot_between_actions",
            "panel_power_cycle_between_actions",
            "j2_disconnect_between_actions",
            "other_visible_refresh_between_actions",
        },
    )
    if any(type(value) is not bool for value in continuity.values()):
        raise N4V3AnalysisError("N4 V3 continuity fields must be boolean")
    return root


def _abnormal_reasons(
    *,
    map_result: Mapping[str, Any],
    target_result: Mapping[str, Any],
    visual: Mapping[str, Any],
    electrical: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    protocol_reasons = []
    visual_reasons = []
    electrical_reasons = []
    if map_result["state"] != ResultState.PASS.value:
        protocol_reasons.append(f"map_result_state:{map_result['state']}")
    if target_result["state"] != ResultState.PASS.value:
        protocol_reasons.append(f"target_result_state:{target_result['state']}")
    for field in (
        "map_fidelity_pass",
        "target_fidelity_pass",
        "orientation_pass",
        "seam_assessment_pass",
    ):
        if visual[field] is not True:
            visual_reasons.append(f"visual_not_pass:{field}")
    for phase in ("map", "target"):
        if electrical[phase]["constant_voltage_mode"] is not True:
            electrical_reasons.append(f"constant_voltage_not_pass:{phase}")
    if electrical["reviewed_limits_pass"] is not True:
        electrical_reasons.append("reviewed_electrical_limits_not_pass")
    if electrical["thermal_limits_pass"] is not True:
        electrical_reasons.append("reviewed_temperature_limits_not_pass")
    for field, happened in electrical["continuity"].items():
        if happened:
            electrical_reasons.append(f"map_target_continuity_broken:{field}")
    return protocol_reasons, visual_reasons, electrical_reasons


_EXECUTION_SUMMARY_KEYS = (
    "action_key",
    "action_identity_sha256",
    "cell_id",
    "phase",
    "attempt_id",
    "state",
    "claim_file_sha256",
    "lock_file_sha256",
    "profile_file_sha256",
    "evidence_file_sha256",
    "observation_file_sha256",
    "finalization_file_sha256",
    "result_file_sha256",
    "prior_result_file_sha256",
    "prior_finalization_file_sha256",
    "execution_evidence_verified",
)


def _execution_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {field: _snapshot(value[field]) for field in _EXECUTION_SUMMARY_KEYS}


def _validated_finalized_cell_bundles(
    contract: Mapping[str, Any],
    cell: Mapping[str, Any],
    *,
    map_bundle: Mapping[str, Any],
    target_bundle: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    shared = _execution_bundle()
    try:
        validated_map = execution_contract.validate_n4_v3_finalized_action_bundle(
            shared,
            map_bundle,
            expected_action_key=f"{cell['cell_id']}-map-primer",
        )
        validated_target = execution_contract.validate_n4_v3_finalized_action_bundle(
            shared,
            target_bundle,
            expected_action_key=f"{cell['cell_id']}-target",
            prior_bundle=map_bundle,
        )
    except execution_contract.N4V3ExecutionContractError as error:
        raise N4V3AnalysisError(
            f"N4 V3 finalized runner evidence is invalid: {error}"
        ) from error
    if (
        contract["execution_contract_canonical_sha256"]
        != shared["integrity"]["canonical_sha256"]
        or validated_map["action_identity_sha256"]
        != cell["map_action_identity_sha256"]
        or validated_target["action_identity_sha256"]
        != cell["target_action_identity_sha256"]
        or validated_map["cell_id"] != cell["cell_id"]
        or validated_target["cell_id"] != cell["cell_id"]
        or validated_map["phase"] != "map-primer"
        or validated_target["phase"] != "target"
        or validated_map["execution_evidence_verified"] is not True
        or validated_target["execution_evidence_verified"] is not True
        or validated_map["attempt_id"] == validated_target["attempt_id"]
        or validated_target["prior_result_file_sha256"]
        != validated_map["result_file_sha256"]
        or validated_target["prior_finalization_file_sha256"]
        != validated_map["finalization_file_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 finalized MAP-target evidence binding changed")
    return validated_map, validated_target


def _derived_cell_measurements(
    cell: Mapping[str, Any],
    validated_map: Mapping[str, Any],
    validated_target: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    map_observation = validated_map["observation"]
    target_observation = validated_target["observation"]
    if target_observation["reference_preview_sha256"] != cell["strict_preview_sha256"]:
        raise N4V3AnalysisError("N4 V3 target strict-preview binding changed")
    map_camera = map_observation["camera"]
    target_camera = target_observation["camera"]
    camera_fixed_fields = (
        "observation_kind",
        "observer_or_camera_asset_sha256",
        "fixed_exposure_profile_sha256",
    )
    if any(map_camera[field] != target_camera[field] for field in camera_fixed_fields):
        raise N4V3AnalysisError("N4 V3 MAP-target observation method/assets changed")
    if (
        target_camera["observation_kind"] == "fixed-camera"
        and map_camera["capture_file_sha256"]
        == target_camera["capture_file_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 MAP and target reused one camera capture")

    map_electrical = map_observation["electrical"]
    target_electrical = target_observation["electrical"]
    if any(
        map_electrical[field] != target_electrical[field]
        for field in ("meter_asset_sha256", "clock_asset_sha256")
    ):
        raise N4V3AnalysisError("N4 V3 MAP-target electrical assets changed")
    map_thermal = map_observation["thermal"]
    target_thermal = target_observation["thermal"]
    thermal_fixed_fields = (
        "uncertainty_u95_c",
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "uncertainty_evidence_sha256",
    )
    if any(map_thermal[field] != target_thermal[field] for field in thermal_fixed_fields):
        raise N4V3AnalysisError("N4 V3 MAP-target temperature method changed")
    if (
        map_thermal["measurement_evidence_sha256"]
        == target_thermal["measurement_evidence_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 MAP and target reused temperature evidence")

    map_visual = map_observation["visual"]
    target_visual = target_observation["visual"]
    visual = {
        "observation_kind": target_camera["observation_kind"],
        "protocol_sha256": target_visual["protocol_sha256"],
        "observation_evidence_sha256": target_visual[
            "observation_evidence_sha256"
        ],
        "reference_preview_sha256": cell["strict_preview_sha256"],
        "observer_or_camera_asset_sha256": target_camera[
            "observer_or_camera_asset_sha256"
        ],
        "capture_file_sha256": target_camera["capture_file_sha256"],
        "fixed_exposure_profile_sha256": target_camera[
            "fixed_exposure_profile_sha256"
        ],
        "roi_definition_sha256": target_visual["roi_definition_sha256"],
        "map_fidelity_pass": map_visual["map_fidelity_pass"],
        "target_fidelity_pass": target_visual["target_fidelity_pass"],
        "orientation_pass": bool(
            map_visual["orientation_pass"] and target_visual["orientation_pass"]
        ),
        "seam_assessment_pass": bool(
            map_visual["seam_assessment_pass"]
            and target_visual["seam_assessment_pass"]
        ),
        "fidelity_score": target_visual["fidelity_score"],
        "ghosting_score": target_visual["ghosting_score"],
        "artifact_severity_score": target_visual["artifact_severity_score"],
    }

    def action_electrical(value: Mapping[str, Any]) -> dict[str, Any]:
        return {
            field: _snapshot(value[field])
            for field in (
                "pre_voltage_v",
                "pre_idle_current_a",
                "post_voltage_v",
                "post_idle_current_a",
                "peak_current_a",
                "constant_voltage_mode",
                "timing_ms",
            )
        }

    electrical = {
        "meter_asset_sha256": target_electrical["meter_asset_sha256"],
        "clock_asset_sha256": target_electrical["clock_asset_sha256"],
        "map": action_electrical(map_electrical),
        "target": action_electrical(target_electrical),
        "external_temperature": {
            "pre_map_c": map_thermal["pre_action_c"],
            "post_map_c": map_thermal["post_action_c"],
            "pre_target_c": target_thermal["pre_action_c"],
            "post_target_c": target_thermal["post_action_c"],
            "session_max_c": max(
                float(map_thermal["session_max_c"]),
                float(target_thermal["session_max_c"]),
            ),
            "uncertainty_u95_c": target_thermal["uncertainty_u95_c"],
            "sensor_asset_sha256": target_thermal["sensor_asset_sha256"],
            "calibration_artifact_sha256": target_thermal[
                "calibration_artifact_sha256"
            ],
            "map_measurement_evidence_sha256": map_thermal[
                "measurement_evidence_sha256"
            ],
            "target_measurement_evidence_sha256": target_thermal[
                "measurement_evidence_sha256"
            ],
            "uncertainty_evidence_sha256": target_thermal[
                "uncertainty_evidence_sha256"
            ],
        },
        "reviewed_limits_pass": bool(
            map_electrical["reviewed_limits_pass"]
            and target_electrical["reviewed_limits_pass"]
        ),
        "thermal_limits_pass": bool(
            map_observation["thermal_pass"] and target_observation["thermal_pass"]
        ),
        "continuity": _snapshot(target_observation["continuity"]),
    }
    return (
        _validate_visual(visual, strict_preview_sha256=cell["strict_preview_sha256"]),
        _validate_electrical(electrical),
    )


def build_n4_v3_cell_observation(
    contract: Mapping[str, Any],
    *,
    cell_id: str,
    map_bundle: Mapping[str, Any],
    target_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep-validate and seal one runner-produced MAP->target evidence chain."""

    root = validate_n4_v3_analysis_contract(contract)
    cell, map_action, target_action = _cell_context(root, cell_id)
    validated_map, validated_target = _validated_finalized_cell_bundles(
        root,
        cell,
        map_bundle=map_bundle,
        target_bundle=target_bundle,
    )
    validated_visual, validated_electrical = _derived_cell_measurements(
        cell,
        validated_map,
        validated_target,
    )
    map_result = validated_map["result"]
    target_result = validated_target["result"]
    protocol_reasons, visual_reasons, electrical_reasons = _abnormal_reasons(
        map_result=map_result,
        target_result=target_result,
        visual=validated_visual,
        electrical=validated_electrical,
    )
    abnormal = bool(protocol_reasons or visual_reasons or electrical_reasons)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "contract_canonical_sha256": root["integrity"]["canonical_sha256"],
        "cell_id": cell_id,
        "ordinal": cell["ordinal"],
        "factors": _snapshot(cell["factors"]),
        "frame_sha256": cell["frame_sha256"],
        "strict_preview_sha256": cell["strict_preview_sha256"],
        "map_action_identity_sha256": map_action["action_identity_sha256"],
        "target_action_identity_sha256": target_action["action_identity_sha256"],
        "map_finalized_action_bundle": _snapshot(map_bundle),
        "target_finalized_action_bundle": _snapshot(target_bundle),
        "map_execution_evidence": _execution_summary(validated_map),
        "target_execution_evidence": _execution_summary(validated_target),
        "map_result": _snapshot(map_result),
        "map_result_file_sha256": validated_map["result_file_sha256"],
        "map_finalization_file_sha256": validated_map[
            "finalization_file_sha256"
        ],
        "target_result": _snapshot(target_result),
        "target_result_file_sha256": validated_target["result_file_sha256"],
        "target_finalization_file_sha256": validated_target[
            "finalization_file_sha256"
        ],
        "target_prior_result_file_sha256": validated_target[
            "prior_result_file_sha256"
        ],
        "target_prior_finalization_file_sha256": validated_target[
            "prior_finalization_file_sha256"
        ],
        "visual": _snapshot(validated_visual),
        "electrical": _snapshot(validated_electrical),
        "execution_evidence_verified": True,
        "protocol_abnormal_reasons": protocol_reasons,
        "visual_abnormal_reasons": visual_reasons,
        "electrical_abnormal_reasons": electrical_reasons,
        "observation_state": (
            ResultState.UNKNOWN_DO_NOT_RETRY.value
            if abnormal
            else "CELL_EVIDENCE_COMPLETE_DESCRIPTIVE_ONLY"
        ),
        "qualification_state": "NOT_QUALIFIED",
        "stop_remaining_cells": abnormal,
        "automatic_retry": False,
        "automatic_recovery": False,
        "analyzer_effects": {
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "visible_refreshes": 0,
        },
    }
    observation = {
        **unsigned,
        "integrity": _integrity(unsigned, OBSERVATION_HASH_SCOPE),
    }
    validate_n4_v3_cell_observation(observation, root)
    return observation


def validate_n4_v3_cell_observation(
    observation: Mapping[str, Any], contract: Mapping[str, Any]
) -> Mapping[str, Any]:
    root_contract = validate_n4_v3_analysis_contract(contract)
    root = _exact(
        observation,
        label="N4 V3 cell observation",
        keys={
            "schema_version",
            "kind",
            "contract_canonical_sha256",
            "cell_id",
            "ordinal",
            "factors",
            "frame_sha256",
            "strict_preview_sha256",
            "map_action_identity_sha256",
            "target_action_identity_sha256",
            "map_finalized_action_bundle",
            "target_finalized_action_bundle",
            "map_execution_evidence",
            "target_execution_evidence",
            "map_result",
            "map_result_file_sha256",
            "map_finalization_file_sha256",
            "target_result",
            "target_result_file_sha256",
            "target_finalization_file_sha256",
            "target_prior_result_file_sha256",
            "target_prior_finalization_file_sha256",
            "visual",
            "electrical",
            "execution_evidence_verified",
            "protocol_abnormal_reasons",
            "visual_abnormal_reasons",
            "electrical_abnormal_reasons",
            "observation_state",
            "qualification_state",
            "stop_remaining_cells",
            "automatic_retry",
            "automatic_recovery",
            "analyzer_effects",
            "integrity",
        },
    )
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, OBSERVATION_HASH_SCOPE):
        raise N4V3AnalysisError("N4 V3 observation canonical integrity is invalid")
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != OBSERVATION_KIND
        or root["contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 observation schema/contract binding changed")
    cell, map_action, target_action = _cell_context(root_contract, root["cell_id"])
    if (
        root["ordinal"] != cell["ordinal"]
        or root["factors"] != cell["factors"]
        or root["frame_sha256"] != cell["frame_sha256"]
        or root["strict_preview_sha256"] != cell["strict_preview_sha256"]
        or root["map_action_identity_sha256"] != map_action["action_identity_sha256"]
        or root["target_action_identity_sha256"]
        != target_action["action_identity_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 observation cell/frame/action binding changed")
    validated_map, validated_target = _validated_finalized_cell_bundles(
        root_contract,
        cell,
        map_bundle=root["map_finalized_action_bundle"],
        target_bundle=root["target_finalized_action_bundle"],
    )
    map_result = validated_map["result"]
    target_result = validated_target["result"]
    visual, electrical = _derived_cell_measurements(
        cell,
        validated_map,
        validated_target,
    )
    if (
        root["map_execution_evidence"] != _execution_summary(validated_map)
        or root["target_execution_evidence"]
        != _execution_summary(validated_target)
        or root["map_result"] != map_result
        or root["target_result"] != target_result
        or root["map_result_file_sha256"] != validated_map["result_file_sha256"]
        or root["map_finalization_file_sha256"]
        != validated_map["finalization_file_sha256"]
        or root["target_result_file_sha256"]
        != validated_target["result_file_sha256"]
        or root["target_finalization_file_sha256"]
        != validated_target["finalization_file_sha256"]
        or root["target_prior_result_file_sha256"]
        != validated_map["result_file_sha256"]
        or root["target_prior_finalization_file_sha256"]
        != validated_map["finalization_file_sha256"]
        or root["visual"] != visual
        or root["electrical"] != electrical
        or root["execution_evidence_verified"] is not True
    ):
        raise N4V3AnalysisError(
            "N4 V3 observation runner evidence or derived measurement binding changed"
        )
    protocol_reasons, visual_reasons, electrical_reasons = _abnormal_reasons(
        map_result=map_result,
        target_result=target_result,
        visual=visual,
        electrical=electrical,
    )
    abnormal = bool(protocol_reasons or visual_reasons or electrical_reasons)
    expected_state = (
        ResultState.UNKNOWN_DO_NOT_RETRY.value
        if abnormal
        else "CELL_EVIDENCE_COMPLETE_DESCRIPTIVE_ONLY"
    )
    if (
        root["protocol_abnormal_reasons"] != protocol_reasons
        or root["visual_abnormal_reasons"] != visual_reasons
        or root["electrical_abnormal_reasons"] != electrical_reasons
        or root["observation_state"] != expected_state
        or root["qualification_state"] != "NOT_QUALIFIED"
        or root["stop_remaining_cells"] is not abnormal
        or root["automatic_retry"] is not False
        or root["automatic_recovery"] is not False
        or root["analyzer_effects"]
        != {
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "visible_refreshes": 0,
        }
    ):
        raise N4V3AnalysisError("N4 V3 observation terminal/offline state changed")
    return root


def _factorial_effect(values: Mapping[str, float]) -> dict[str, Any]:
    if set(values) != set(FACTORIAL_CELLS):
        raise N4V3AnalysisError("factorial outcome does not contain the exact four cells")
    lb = float(values["low-balanced"])
    lu = float(values["low-unbalanced"])
    hb = float(values["high-balanced"])
    hu = float(values["high-unbalanced"])
    a_effect = ((hb + hu) / 2) - ((lb + lu) / 2)
    b_effect = ((lu + hu) / 2) - ((lb + hb) / 2)
    interaction = ((hu + lb) / 2) - ((hb + lu) / 2)
    difference_of_differences = (hu - hb) - (lu - lb)
    return {
        "cell_values": {cell: float(values[cell]) for cell in FACTORIAL_CELLS},
        "n_per_cell": 1,
        "total_n": 4,
        "spatial_frequency_main_effect_high_minus_low": a_effect,
        "half_load_main_effect_unbalanced_minus_balanced": b_effect,
        "interaction_effect_coded_level_means": interaction,
        "interaction_difference_of_differences": difference_of_differences,
        "interaction_scaling_check": math.isclose(
            difference_of_differences,
            2 * interaction,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ),
        "descriptive_only": True,
        "p95": None,
        "p99": None,
        "qualification_state": "NOT_QUALIFIED",
    }


def _visual_values(observation: Mapping[str, Any]) -> dict[str, float]:
    return {
        metric: float(observation["visual"][metric]) for metric in VISUAL_METRICS
    }


def _electrical_values(observation: Mapping[str, Any]) -> dict[str, float]:
    electrical = observation["electrical"]
    target = electrical["target"]
    return {
        "map_peak_current_a": float(electrical["map"]["peak_current_a"]),
        "target_peak_current_a": float(target["peak_current_a"]),
        "map_job_duration_ms": float(electrical["map"]["timing_ms"]["job_duration_ms"]),
        "target_job_duration_ms": float(target["timing_ms"]["job_duration_ms"]),
        "session_max_temperature_c": float(
            electrical["external_temperature"]["session_max_c"]
        ),
        "target_voltage_droop_v": float(target["pre_voltage_v"])
        - float(target["post_voltage_v"]),
    }


def _analysis_group(
    observations: Mapping[str, Mapping[str, Any]],
    *,
    metrics: Sequence[str],
    extractor: Any,
) -> dict[str, Any]:
    result = {}
    extracted = {cell: extractor(observation) for cell, observation in observations.items()}
    for metric in metrics:
        result[metric] = _factorial_effect(
            {cell: values[metric] for cell, values in extracted.items()}
        )
    return result


def _validate_complete_cross_cell_comparability(
    observations: Sequence[Mapping[str, Any]],
) -> None:
    """Reject method drift and evidence replay before descriptive 2x2 arithmetic."""

    if len(observations) != 4:
        raise N4V3AnalysisError("cross-cell comparability requires exactly four cells")

    visual_fixed = (
        "observation_kind",
        "protocol_sha256",
        "observer_or_camera_asset_sha256",
        "fixed_exposure_profile_sha256",
        "roi_definition_sha256",
    )
    electrical_fixed = ("meter_asset_sha256", "clock_asset_sha256")
    temperature_fixed = (
        "uncertainty_u95_c",
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "uncertainty_evidence_sha256",
    )
    first = observations[0]
    for item in observations[1:]:
        if any(item["visual"][field] != first["visual"][field] for field in visual_fixed):
            raise N4V3AnalysisError(
                "N4 V3 visual method/assets changed across factorial cells"
            )
        if any(
            item["electrical"][field] != first["electrical"][field]
            for field in electrical_fixed
        ):
            raise N4V3AnalysisError(
                "N4 V3 electrical method/assets changed across factorial cells"
            )
        item_temperature = item["electrical"]["external_temperature"]
        first_temperature = first["electrical"]["external_temperature"]
        if any(
            item_temperature[field] != first_temperature[field]
            for field in temperature_fixed
        ):
            raise N4V3AnalysisError(
                "N4 V3 temperature method/uncertainty changed across factorial cells"
            )

    distinct_fields = (
        [item["visual"]["observation_evidence_sha256"] for item in observations],
        [
            item["electrical"]["external_temperature"][
                "map_measurement_evidence_sha256"
            ]
            for item in observations
        ],
        [
            item["electrical"]["external_temperature"][
                "target_measurement_evidence_sha256"
            ]
            for item in observations
        ],
    )
    if any(len(set(values)) != 4 for values in distinct_fields):
        raise N4V3AnalysisError("N4 V3 per-cell observation evidence was replayed")
    if first["visual"]["observation_kind"] == "fixed-camera":
        captures = [item["visual"]["capture_file_sha256"] for item in observations]
        if len(set(captures)) != 4:
            raise N4V3AnalysisError("N4 V3 per-cell camera capture was replayed")


def analyze_n4_v3(
    contract: Mapping[str, Any],
    *,
    observations: Sequence[Mapping[str, Any]],
    _skip_validation: bool = False,
) -> dict[str, Any]:
    """Analyze four complete cells, or adjudicate one terminal abnormal prefix."""

    root = validate_n4_v3_analysis_contract(contract)
    if len(observations) > 4:
        raise N4V3AnalysisError("N4 V3 analysis contains more than four observations")
    validated: list[Mapping[str, Any]] = []
    seen_cells: set[str] = set()
    seen_actions: set[str] = set()
    seen_result_files: set[str] = set()
    seen_execution_files: set[str] = set()
    seen_attempts: set[str] = set()
    seen_source_observations: set[str] = set()
    seen_camera_captures: set[str] = set()
    abnormal_seen = False
    for index, observation in enumerate(observations):
        item = validate_n4_v3_cell_observation(observation, root)
        expected_cell = CELL_ORDER[index]
        if item["cell_id"] != expected_cell or item["ordinal"] != index + 1:
            raise N4V3AnalysisError("N4 V3 observations are not the exact campaign-order prefix")
        if abnormal_seen:
            raise N4V3AnalysisError("N4 V3 observation exists after an abnormal terminal cell")
        action_ids = {
            item["map_action_identity_sha256"],
            item["target_action_identity_sha256"],
        }
        result_ids = {
            item["map_result_file_sha256"],
            item["target_result_file_sha256"],
        }
        execution_ids = {
            summary[field]
            for summary in (
                item["map_execution_evidence"],
                item["target_execution_evidence"],
            )
            for field in (
                "claim_file_sha256",
                "lock_file_sha256",
                "evidence_file_sha256",
                "observation_file_sha256",
                "finalization_file_sha256",
                "result_file_sha256",
            )
        }
        attempts = {
            item["map_execution_evidence"]["attempt_id"],
            item["target_execution_evidence"]["attempt_id"],
        }
        source_observations = {
            bundle["observation"]["source_observation_file_sha256"]
            for bundle in (
                item["map_finalized_action_bundle"],
                item["target_finalized_action_bundle"],
            )
        }
        camera_captures = {
            capture
            for bundle in (
                item["map_finalized_action_bundle"],
                item["target_finalized_action_bundle"],
            )
            if (capture := bundle["observation"]["camera"]["capture_file_sha256"])
            is not None
        }
        if (
            item["cell_id"] in seen_cells
            or seen_actions.intersection(action_ids)
            or seen_result_files.intersection(result_ids)
            or seen_execution_files.intersection(execution_ids)
            or seen_attempts.intersection(attempts)
            or seen_source_observations.intersection(source_observations)
            or seen_camera_captures.intersection(camera_captures)
        ):
            raise N4V3AnalysisError(
                "N4 V3 cell/action/execution-evidence replay was detected"
            )
        seen_cells.add(item["cell_id"])
        seen_actions.update(action_ids)
        seen_result_files.update(result_ids)
        seen_execution_files.update(execution_ids)
        seen_attempts.update(attempts)
        seen_source_observations.update(source_observations)
        seen_camera_captures.update(camera_captures)
        validated.append(item)
        abnormal_seen = item["observation_state"] == ResultState.UNKNOWN_DO_NOT_RETRY.value
    if abnormal_seen and len(validated) != len(observations):
        raise N4V3AnalysisError("N4 V3 abnormal cell must be the final observation")
    if not abnormal_seen and len(validated) != 4:
        missing = list(CELL_ORDER[len(validated) :])
        raise N4V3AnalysisError(f"N4 V3 complete analysis is missing cells: {missing}")

    complete = len(validated) == 4 and not abnormal_seen
    if complete:
        _validate_complete_cross_cell_comparability(validated)
    by_cell = {item["cell_id"]: item for item in validated}
    visual_analysis = (
        _analysis_group(by_cell, metrics=VISUAL_METRICS, extractor=_visual_values)
        if complete
        else None
    )
    electrical_analysis = (
        _analysis_group(
            by_cell,
            metrics=ELECTRICAL_METRICS,
            extractor=_electrical_values,
        )
        if complete
        else None
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "contract_canonical_sha256": root["integrity"]["canonical_sha256"],
        "execution_contract_canonical_sha256": root[
            "execution_contract_canonical_sha256"
        ],
        "execution_contract_file_sha256": root["execution_contract_file_sha256"],
        "source_manifest_canonical_sha256": root["source_v3"][
            "manifest_canonical_sha256"
        ],
        "source_proof_canonical_sha256": root["source_v3"][
            "proof_canonical_sha256"
        ],
        "source_p0_campaign_canonical_sha256": root[
            "source_p0_campaign_canonical_sha256"
        ],
        "p0_campaign_canonical_sha256": root["p0_campaign_canonical_sha256"],
        "observations": _snapshot(validated),
        "observation_integrity_bindings": {
            item["cell_id"]: item["integrity"]["canonical_sha256"]
            for item in validated
        },
        "observed_cell_count": len(validated),
        "verified_visible_action_count": 2 * len(validated),
        "execution_evidence_verified": all(
            item["execution_evidence_verified"] is True for item in validated
        ),
        "complete": complete,
        "terminal_state": (
            ResultState.UNKNOWN_DO_NOT_RETRY.value
            if abnormal_seen
            else "EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY"
        ),
        "stop_remaining_cells": abnormal_seen,
        "visual_analysis": visual_analysis,
        "electrical_analysis": electrical_analysis,
        "visual_electrical_joint_conclusion": None,
        "qualification_state": "NOT_QUALIFIED",
        "inference_contract": {
            "observations_per_cell": 1 if complete else None,
            "p95_reported": False,
            "p99_reported": False,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "visual_qualification_allowed": False,
            "electrical_qualification_allowed": False,
            "hardware_qualification_allowed": False,
        },
        "classification": {
            "offline_analysis": True,
            "source_execution_evidence_deep_validated": True,
            "analyzer_hardware_execution_authorized": False,
            "analyzer_claim_created": False,
            "analyzer_authorization_created": False,
            "analyzer_network_io_performed": False,
            "analyzer_device_io_performed": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    report = {**unsigned, "integrity": _integrity(unsigned, REPORT_HASH_SCOPE)}
    if not _skip_validation:
        validate_n4_v3_report(report, root)
    return report


def validate_n4_v3_report(
    report: Mapping[str, Any], contract: Mapping[str, Any]
) -> Mapping[str, Any]:
    root_contract = validate_n4_v3_analysis_contract(contract)
    root = _exact(
        report,
        label="N4 V3 analysis report",
        keys={
            "schema_version",
            "kind",
            "contract_canonical_sha256",
            "execution_contract_canonical_sha256",
            "execution_contract_file_sha256",
            "source_manifest_canonical_sha256",
            "source_proof_canonical_sha256",
            "source_p0_campaign_canonical_sha256",
            "p0_campaign_canonical_sha256",
            "observations",
            "observation_integrity_bindings",
            "observed_cell_count",
            "verified_visible_action_count",
            "execution_evidence_verified",
            "complete",
            "terminal_state",
            "stop_remaining_cells",
            "visual_analysis",
            "electrical_analysis",
            "visual_electrical_joint_conclusion",
            "qualification_state",
            "inference_contract",
            "classification",
            "integrity",
        },
    )
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned, REPORT_HASH_SCOPE):
        raise N4V3AnalysisError("N4 V3 report canonical integrity is invalid")
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != REPORT_KIND
        or root["contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or root["execution_contract_canonical_sha256"]
        != root_contract["execution_contract_canonical_sha256"]
        or root["execution_contract_file_sha256"]
        != root_contract["execution_contract_file_sha256"]
        or root["source_manifest_canonical_sha256"]
        != root_contract["source_v3"]["manifest_canonical_sha256"]
        or root["source_proof_canonical_sha256"]
        != root_contract["source_v3"]["proof_canonical_sha256"]
        or root["source_p0_campaign_canonical_sha256"]
        != root_contract["source_p0_campaign_canonical_sha256"]
        or root["p0_campaign_canonical_sha256"]
        != root_contract["p0_campaign_canonical_sha256"]
    ):
        raise N4V3AnalysisError("N4 V3 report source/contract binding changed")
    rebuilt = analyze_n4_v3(
        root_contract,
        observations=root["observations"],
        _skip_validation=True,
    )
    if rebuilt != root:
        raise N4V3AnalysisError("N4 V3 report derived fields changed")
    return root
