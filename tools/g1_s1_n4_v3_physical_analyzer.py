#!/usr/bin/env python3
"""Offline physical-aware analysis for the complete N4 V3 2x2 campaign.

This adapter leaves the frozen legacy analyzer unchanged.  It consumes exactly
four physical cell observations plus their eight deeply authenticated action
bundles, replays every action through the public physical validator, and then
computes only the preregistered descriptive 2x2 effects.  It performs no claim,
authorization, network, device, firmware, reset, or power I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from host.visible_refresh_campaign import (
    CampaignContractError,
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    read_local_regular_file,
)
from tools import g1_s1_n4_v3_analyzer as legacy_analyzer
from tools import g1_s1_n4_v3_physical_execution as physical
from tools import g1_s1_rc2g_n4_v3_physical_once as runner


SCHEMA_VERSION = 1
REPORT_KIND = "mf1750-g1-s1-n4-v3-physical-factorial-analysis"
REPORT_HASH_SCOPE = (
    "entire N4 V3 physical analysis report excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_CELL_OBSERVATION_BYTES = 1024 * 1024


class N4V3PhysicalAnalysisError(ValueError):
    """The physical N4 evidence set or derived report failed closed."""


@dataclass(frozen=True)
class N4V3PhysicalCellEvidence:
    map_bundle: Mapping[str, Any]
    target_bundle: Mapping[str, Any]
    map_production: ValidatedProductionProfile
    target_production: ValidatedProductionProfile
    physical_cell_observation: Mapping[str, Any]


@dataclass(frozen=True)
class N4V3PhysicalCellResultFiles:
    map_result_file: Path
    target_result_file: Path


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N4V3PhysicalAnalysisError(str(error)) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N4V3PhysicalAnalysisError(str(error)) from error


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": REPORT_HASH_SCOPE,
    }


def _read_canonical_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        artifact = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_CELL_OBSERVATION_BYTES
        )
        value = json.loads(artifact.payload.decode("utf-8"))
    except (ProductionProfileError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N4V3PhysicalAnalysisError(f"{label} is invalid: {error}") from error
    if not isinstance(value, Mapping) or artifact.payload != _canonical(value):
        raise N4V3PhysicalAnalysisError(f"{label} must be canonical JSON")
    return value


def _validate_cell_observation(
    context: physical.N4PhysicalContext,
    cell_id: str,
    value: Mapping[str, Any],
    map_validated: Mapping[str, Any],
    target_validated: Mapping[str, Any],
) -> Mapping[str, Any]:
    expected_unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": runner.CELL_OBSERVATION_KIND,
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "cell_id": cell_id,
        "map_action_identity_sha256": map_validated["action_identity_sha256"],
        "map_result_file_sha256": map_validated["result_file_sha256"],
        "map_finalization_file_sha256": map_validated[
            "finalization_file_sha256"
        ],
        "target_action_identity_sha256": target_validated[
            "action_identity_sha256"
        ],
        "target_result_file_sha256": target_validated["result_file_sha256"],
        "target_finalization_file_sha256": target_validated[
            "finalization_file_sha256"
        ],
        "target_state": target_validated["state"],
        "map_and_target_deep_validated": True,
        "automatic_inference": False,
    }
    expected = {
        **expected_unsigned,
        "integrity": {
            "canonical_sha256": _sha256(expected_unsigned),
            "canonical_sha256_scope": (
                "entire physical N4 cell observation excluding integrity; "
                "canonical JSON"
            ),
        },
    }
    if value != expected:
        raise N4V3PhysicalAnalysisError(
            "physical N4 cell observation does not match the deep pair"
        )
    return value


def _authority_identity(authority: Mapping[str, Any]) -> dict[str, Any]:
    if "policy_id" in authority:
        return {
            "issuer": authority["issuer"],
            "authority_id": authority["policy_id"],
        }
    return {
        "issuer": authority["supplier_id"],
        "authority_id": authority["document_id"],
    }


def _lineage(production: ValidatedProductionProfile) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None:
        raise N4V3PhysicalAnalysisError("production lineage lost review artifact")
    return {
        "panel": _snapshot(production.profile["panel"]),
        "firmware": _snapshot(production.profile["firmware"]),
        "firmware_binary_sha256": production.inputs.firmware_binary.sha256,
        "limit_authority_kind": production.report["limit_authority_kind"],
        "limit_authority_classification": production.report[
            "limit_authority_classification"
        ],
        "limit_authority_file_sha256": production.inputs.limit_authority_file.sha256,
        "limit_authority_identity": _authority_identity(
            production.inputs.limit_authority
        ),
        "profile_id": production.profile["profile_id"],
        "profile_version": production.profile["profile_version"],
        "reviewer_id": production.profile["review"]["reviewer_id"],
        "reviewer_key_id": production.reviewer_key_id,
    }


def _profile_record(
    action_key: str, production: ValidatedProductionProfile
) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None:
        raise N4V3PhysicalAnalysisError("production profile lost review artifact")
    return {
        "action_key": action_key,
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "usage_evidence_file_sha256": production.inputs.usage_evidence_file.sha256,
        "review_artifact_file_sha256": review.sha256,
        "evaluated_at": production.report["evaluated_at"],
        "usage": _snapshot(production.profile["usage"]),
    }


def _validate_usage_chain(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    baseline = records[0]["map_production"].profile["usage"][
        "cumulative_visible_refresh_count"
    ]
    previous_target_completed_at = None
    for index, record in enumerate(records):
        map_usage = record["map_production"].profile["usage"]
        target_usage = record["target_production"].profile["usage"]
        expected_map_count = baseline + 2 * index
        if (
            map_usage["cumulative_visible_refresh_count"] != expected_map_count
            or map_usage["session_visible_refresh_count"] != 0
            or map_usage["consecutive_visible_refresh_count"] != 0
            or target_usage["cumulative_visible_refresh_count"]
            != expected_map_count + 1
            or target_usage["session_visible_refresh_count"] != 1
            or target_usage["consecutive_visible_refresh_count"] != 1
            or target_usage["last_visible_refresh_completed_at"]
            != record["map_validated"]["result"]["completed_at"]
        ):
            raise N4V3PhysicalAnalysisError(
                "physical N4 usage counts do not form one exact action sequence"
            )
        if previous_target_completed_at is not None and (
            map_usage["last_visible_refresh_completed_at"]
            != previous_target_completed_at
        ):
            raise N4V3PhysicalAnalysisError(
                "physical N4 next cell does not name the prior target as latest"
            )
        previous_target_completed_at = record["target_validated"]["result"][
            "completed_at"
        ]
    return {
        "baseline_cumulative_visible_refresh_count": baseline,
        "final_completed_visible_refresh_count": baseline + 8,
        "all_eight_actions_accounted_for_in_order": True,
        "each_target_usage_names_own_map_as_latest": True,
        "each_later_map_usage_names_prior_target_as_latest": True,
    }


def _analyze(
    context: physical.N4PhysicalContext,
    cells: Sequence[N4V3PhysicalCellEvidence],
) -> dict[str, Any]:
    try:
        contract = physical.validate_n4_physical_execution_context(context)
    except physical.N4PhysicalExecutionError as error:
        raise N4V3PhysicalAnalysisError(str(error)) from error
    cell_order = tuple(legacy_analyzer.CELL_ORDER)
    if len(cells) != 4:
        raise N4V3PhysicalAnalysisError(
            "physical N4 analysis requires exactly four cells"
        )
    deep_records: list[dict[str, Any]] = []
    derived: list[Mapping[str, Any]] = []
    lineage: dict[str, Any] | None = None
    profiles: list[dict[str, Any]] = []
    uniqueness: dict[str, set[str]] = {
        "action": set(),
        "attempt": set(),
        "result": set(),
        "finalization": set(),
        "profile": set(),
        "usage": set(),
        "review": set(),
        "source_observation": set(),
        "camera": set(),
    }
    for index, (cell_id, evidence) in enumerate(zip(cell_order, cells)):
        if not isinstance(evidence, N4V3PhysicalCellEvidence):
            raise N4V3PhysicalAnalysisError(
                f"cell {index + 1} is not N4V3PhysicalCellEvidence"
            )
        map_key = f"{cell_id}-map-primer"
        target_key = f"{cell_id}-target"
        try:
            map_validated = physical.validate_n4_physical_finalized_action_bundle(
                context,
                evidence.map_bundle,
                production_profile=evidence.map_production,
                expected_action_key=map_key,
            )
            target_validated = physical.validate_n4_physical_finalized_action_bundle(
                context,
                evidence.target_bundle,
                production_profile=evidence.target_production,
                expected_action_key=target_key,
                prior_bundle=evidence.map_bundle,
                prior_production_profile=evidence.map_production,
            )
            target_snapshot = physical.load_n4_physical_action_snapshot(
                context, target_key
            )
        except physical.N4PhysicalExecutionError as error:
            raise N4V3PhysicalAnalysisError(
                f"cell {cell_id} deep validation failed: {error}"
            ) from error
        _validate_cell_observation(
            context,
            cell_id,
            evidence.physical_cell_observation,
            map_validated,
            target_validated,
        )
        cell_contract = {
            "strict_preview_sha256": target_snapshot.reference_preview["sha256"]
        }
        try:
            visual, electrical = legacy_analyzer._derived_cell_measurements(
                cell_contract, map_validated, target_validated
            )
        except legacy_analyzer.N4V3AnalysisError as error:
            raise N4V3PhysicalAnalysisError(
                f"cell {cell_id} derived measurement failed: {error}"
            ) from error
        factors = cell_id.split("-", maxsplit=1)
        derived.append(
            {
                "cell_id": cell_id,
                "factors": {
                    "controller_internal_spatial_frequency": factors[0],
                    "left_right_pigment_transition_load": factors[1],
                },
                "visual": visual,
                "electrical": electrical,
            }
        )
        for item in (_lineage(evidence.map_production), _lineage(evidence.target_production)):
            if lineage is None:
                lineage = item
            elif item != lineage:
                raise N4V3PhysicalAnalysisError(
                    "physical N4 panel/firmware/authority/profile lineage changed"
                )
        for action_key, production_profile in (
            (map_key, evidence.map_production),
            (target_key, evidence.target_production),
        ):
            profile = _profile_record(action_key, production_profile)
            profiles.append(profile)
            for key, value in (
                ("profile", profile["profile_file_sha256"]),
                ("usage", profile["usage_evidence_file_sha256"]),
                ("review", profile["review_artifact_file_sha256"]),
            ):
                if value in uniqueness[key]:
                    raise N4V3PhysicalAnalysisError(
                        f"duplicate {key} evidence replay in physical N4"
                    )
                uniqueness[key].add(value)
        for key, values in (
            (
                "action",
                {
                    map_validated["action_identity_sha256"],
                    target_validated["action_identity_sha256"],
                },
            ),
            (
                "attempt",
                {map_validated["attempt_id"], target_validated["attempt_id"]},
            ),
            (
                "result",
                {
                    map_validated["result_file_sha256"],
                    target_validated["result_file_sha256"],
                },
            ),
            (
                "finalization",
                {
                    map_validated["finalization_file_sha256"],
                    target_validated["finalization_file_sha256"],
                },
            ),
            (
                "source_observation",
                {
                    evidence.map_bundle["observation"][
                        "source_observation_file_sha256"
                    ],
                    evidence.target_bundle["observation"][
                        "source_observation_file_sha256"
                    ],
                },
            ),
        ):
            if len(values) != 2 or uniqueness[key].intersection(values):
                raise N4V3PhysicalAnalysisError(
                    f"duplicate/cross-cell {key} evidence in physical N4"
                )
            uniqueness[key].update(values)
        for bundle in (evidence.map_bundle, evidence.target_bundle):
            capture = bundle["observation"]["camera"]["capture_file_sha256"]
            if capture is not None:
                if capture in uniqueness["camera"]:
                    raise N4V3PhysicalAnalysisError(
                        "duplicate camera capture replay in physical N4"
                    )
                uniqueness["camera"].add(capture)
        deep_records.append(
            {
                "cell_id": cell_id,
                "map_validated": map_validated,
                "target_validated": target_validated,
                "map_production": evidence.map_production,
                "target_production": evidence.target_production,
                "physical_cell_observation": _snapshot(
                    evidence.physical_cell_observation
                ),
            }
        )
    assert lineage is not None
    if (
        lineage["panel"] != context.physical_campaign["panel"]
        or lineage["firmware"] != context.physical_campaign["firmware"]
    ):
        raise N4V3PhysicalAnalysisError(
            "production lineage differs from the physical N4 panel/firmware"
        )
    try:
        legacy_analyzer._validate_complete_cross_cell_comparability(derived)
    except legacy_analyzer.N4V3AnalysisError as error:
        raise N4V3PhysicalAnalysisError(
            f"physical N4 cross-cell comparability failed: {error}"
        ) from error
    usage_chain = _validate_usage_chain(deep_records)
    by_cell = {item["cell_id"]: item for item in derived}
    visual_analysis = legacy_analyzer._analysis_group(
        by_cell,
        metrics=legacy_analyzer.VISUAL_METRICS,
        extractor=legacy_analyzer._visual_values,
    )
    electrical_analysis = legacy_analyzer._analysis_group(
        by_cell,
        metrics=legacy_analyzer.ELECTRICAL_METRICS,
        extractor=legacy_analyzer._electrical_values,
    )
    abnormal_cells: dict[str, Any] = {}
    for item, record in zip(derived, deep_records):
        protocol, visual, electrical = legacy_analyzer._abnormal_reasons(
            map_result=record["map_validated"]["result"],
            target_result=record["target_validated"]["result"],
            visual=item["visual"],
            electrical=item["electrical"],
        )
        if protocol or visual or electrical:
            abnormal_cells[item["cell_id"]] = {
                "protocol": protocol,
                "visual": visual,
                "electrical": electrical,
            }
    observation_kind = derived[0]["visual"]["observation_kind"]
    fixed_camera = observation_kind == "fixed-camera"
    expected_capture_count = 8 if fixed_camera else 0
    if len(uniqueness["camera"]) != expected_capture_count:
        raise N4V3PhysicalAnalysisError(
            "physical N4 camera capture count differs from the registered method"
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "physical_execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "physical_execution_contract_file_sha256": (
            physical.n4_physical_execution_contract_file_sha256(contract)
        ),
        "physical_rebind_canonical_sha256": context.rebind_manifest["integrity"][
            "canonical_sha256"
        ],
        "physical_panel": _snapshot(context.physical_campaign["panel"]),
        "physical_firmware": _snapshot(context.physical_campaign["firmware"]),
        "reviewed_process_schedule": _snapshot(
            context.rebind_manifest["binding"]["reviewed_schedule"]
        ),
        "production_lineage": lineage,
        "action_profile_lineage_records": profiles,
        "usage_chain": usage_chain,
        "preregistered_design": {
            "design": "complete-2x2-one-independent-map-target-session-per-cell",
            "cell_order": list(cell_order),
            "observations_per_cell": 1,
            "visual_metrics": list(legacy_analyzer.VISUAL_METRICS),
            "electrical_metrics": list(legacy_analyzer.ELECTRICAL_METRICS),
            "visual_electrical_joint_score_defined": False,
        },
        "expected_cell_count": 4,
        "verified_cell_count": 4,
        "expected_visible_action_count": 8,
        "verified_visible_action_count": 8,
        "cell_chains": [
            {
                "cell_id": record["cell_id"],
                "ordinal": index + 1,
                "map_action_identity_sha256": record["map_validated"][
                    "action_identity_sha256"
                ],
                "map_result_file_sha256": record["map_validated"][
                    "result_file_sha256"
                ],
                "map_finalization_file_sha256": record["map_validated"][
                    "finalization_file_sha256"
                ],
                "target_action_identity_sha256": record["target_validated"][
                    "action_identity_sha256"
                ],
                "target_result_file_sha256": record["target_validated"][
                    "result_file_sha256"
                ],
                "target_finalization_file_sha256": record["target_validated"][
                    "finalization_file_sha256"
                ],
                "physical_cell_observation_canonical_sha256": record[
                    "physical_cell_observation"
                ]["integrity"]["canonical_sha256"],
                "deep_physical_validation_passed": True,
            }
            for index, record in enumerate(deep_records)
        ],
        "complete_evidence_set": True,
        "analysis_ready": not abnormal_cells,
        "abnormal_cells": abnormal_cells,
        "visual_analysis": visual_analysis,
        "electrical_analysis": electrical_analysis,
        "visual_electrical_joint_conclusion": None,
        "camera_comparability": {
            "observation_kind": observation_kind,
            "fixed_method_assets_equal_across_cells": True,
            "camera_capture_comparison_applicable": fixed_camera,
            "expected_camera_capture_count": expected_capture_count,
            "camera_capture_count": len(uniqueness["camera"]),
            "all_present_camera_captures_distinct": True,
            "capture_hashes_establish_content_identity_only": True,
            "photometric_or_visual_qualification_established": False,
            "state": (
                "FIXED_CAMERA_METHOD_AND_DISTINCT_CAPTURES_ONLY_NOT_QUALIFIED"
                if fixed_camera
                else "STANDARDIZED_MANUAL_OBSERVATION_NO_CAMERA_COMPARISON"
            ),
        },
        "qualification_state": "NOT_QUALIFIED",
        "inference_contract": {
            "descriptive_only": True,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "p95_reported": False,
            "p99_reported": False,
            "visual_qualification_allowed": False,
            "electrical_qualification_allowed": False,
            "hardware_qualification_allowed": False,
        },
        "classification": {
            "offline_analysis": True,
            "source_physical_evidence_deep_validated": True,
            "physical_cell_observations_consumed": True,
            "analyzer_hardware_execution_authorized": False,
            "analyzer_claim_created": False,
            "analyzer_network_io_performed": False,
            "analyzer_device_io_performed": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    report = {**unsigned, "integrity": _integrity(unsigned)}
    _validate_report_invariants(report)
    return report


def _validate_report_invariants(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise N4V3PhysicalAnalysisError("physical N4 report must be an object")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise N4V3PhysicalAnalysisError("physical N4 report integrity is invalid")
    if (
        report.get("schema_version") != SCHEMA_VERSION
        or report.get("kind") != REPORT_KIND
        or report.get("qualification_state") != "NOT_QUALIFIED"
        or report.get("verified_cell_count") != 4
        or report.get("verified_visible_action_count") != 8
        or report.get("visual_electrical_joint_conclusion") is not None
        or report.get("inference_contract", {}).get(
            "hardware_qualification_allowed"
        )
        is not False
    ):
        raise N4V3PhysicalAnalysisError(
            "physical N4 report completeness/qualification invariant changed"
        )


def analyze_n4_v3_physical_cells(
    context: physical.N4PhysicalContext,
    *,
    cells: Sequence[N4V3PhysicalCellEvidence],
) -> dict[str, Any]:
    """Deep-validate exactly four physical cells and analyze the 2x2."""

    return _analyze(context, cells)


def validate_n4_v3_physical_analysis_report(
    report: Mapping[str, Any],
    context: physical.N4PhysicalContext,
    *,
    cells: Sequence[N4V3PhysicalCellEvidence],
) -> Mapping[str, Any]:
    """Recompute the full deep analysis and require exact canonical equality."""

    expected = _analyze(context, cells)
    if report != expected:
        raise N4V3PhysicalAnalysisError(
            "physical N4 report differs from replayed deep evidence"
        )
    return report


def analyze_n4_v3_physical_result_files(
    *,
    binding_files: runner.N4PhysicalBindingFiles,
    reviewer_key_file: Path,
    cells: Sequence[N4V3PhysicalCellResultFiles],
) -> dict[str, Any]:
    """Load four stored cells without claim, network, device, or power I/O."""

    if len(cells) != 4:
        raise N4V3PhysicalAnalysisError(
            "physical N4 file analysis requires exactly four cells"
        )
    try:
        context = physical.load_n4_physical_execution_context(
            rebind_manifest_file=binding_files.rebind_manifest,
            physical_campaign_file=binding_files.physical_campaign,
            physical_anchor_campaign_file=binding_files.physical_anchor_campaign,
            binding_review_artifact_file=binding_files.binding_review_artifact,
            minimum_interval_seconds=binding_files.minimum_interval_seconds,
            planned_cooldown_seconds=binding_files.planned_cooldown_seconds,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4V3PhysicalAnalysisError(str(error)) from error
    loaded: list[N4V3PhysicalCellEvidence] = []
    for index, files in enumerate(cells, start=1):
        try:
            map_chain = runner.load_n4_v3_physical_finalized_action_chain(
                files.map_result_file,
                reviewer_key_file=reviewer_key_file,
            )
            target_chain = runner.load_n4_v3_physical_finalized_action_chain(
                files.target_result_file,
                reviewer_key_file=reviewer_key_file,
                primer_result_file=files.map_result_file,
            )
        except runner.N4PhysicalActionError as error:
            raise N4V3PhysicalAnalysisError(
                f"stored cell {index} failed replay: {error}"
            ) from error
        if (
            map_chain.context.contract != context.contract
            or target_chain.context.contract != context.contract
        ):
            raise N4V3PhysicalAnalysisError(
                f"stored cell {index} belongs to another physical contract"
            )
        cell_observation = _read_canonical_json(
            files.target_result_file.parent / runner.CELL_OBSERVATION_FILENAME,
            label=f"physical N4 cell {index} observation",
        )
        loaded.append(
            N4V3PhysicalCellEvidence(
                map_bundle=map_chain.bundle,
                target_bundle=target_chain.bundle,
                map_production=map_chain.production,
                target_production=target_chain.production,
                physical_cell_observation=cell_observation,
            )
        )
    return analyze_n4_v3_physical_cells(context, cells=loaded)


__all__ = [
    "N4V3PhysicalAnalysisError",
    "N4V3PhysicalCellEvidence",
    "N4V3PhysicalCellResultFiles",
    "REPORT_KIND",
    "analyze_n4_v3_physical_cells",
    "analyze_n4_v3_physical_result_files",
    "validate_n4_v3_physical_analysis_report",
]
