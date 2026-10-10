#!/usr/bin/env python3
"""Offline physical-aware analysis for the complete N3B Williams campaign.

The legacy N3 analyzer is intentionally unchanged.  This adapter accepts only
the rebuilt 32-action physical plan and exactly sixteen finalized MAP/target
session chains.  Every action is replayed through the public physical deep
validator before descriptive statistics are computed.  It performs no claim,
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
from tools import g1_s1_n3_analyzer as legacy_analyzer
from tools import g1_s1_n3b_physical_execution as physical
from tools import g1_s1_rc2g_n3b_physical_once as runner


SCHEMA_VERSION = 1
REPORT_KIND = "mf1750-g1-s1-n3b-physical-balanced-order-analysis"
REPORT_HASH_SCOPE = (
    "entire N3B physical analysis report excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_SESSION_OBSERVATION_BYTES = 1024 * 1024

KEY_METRICS = (
    "timing.target.job_duration_ms",
    "temperature.session_max",
    "visual.photo_difference_score",
    "visual.photo_luminance_mean",
)


class N3BPhysicalAnalysisError(ValueError):
    """The physical N3B evidence set or derived report failed closed."""


@dataclass(frozen=True)
class N3BPhysicalSessionEvidence:
    map_bundle: Mapping[str, Any]
    target_bundle: Mapping[str, Any]
    map_production: ValidatedProductionProfile
    target_production: ValidatedProductionProfile
    physical_session_observation: Mapping[str, Any]


@dataclass(frozen=True)
class N3BPhysicalSessionResultFiles:
    map_result_file: Path
    target_result_file: Path


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3BPhysicalAnalysisError(str(error)) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3BPhysicalAnalysisError(str(error)) from error


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": REPORT_HASH_SCOPE,
    }


def _read_canonical_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        artifact = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_SESSION_OBSERVATION_BYTES
        )
        value = json.loads(artifact.payload.decode("utf-8"))
    except (ProductionProfileError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3BPhysicalAnalysisError(f"{label} is invalid: {error}") from error
    if not isinstance(value, Mapping) or artifact.payload != _canonical(value):
        raise N3BPhysicalAnalysisError(f"{label} must be canonical JSON")
    return value


def _validate_session_observation(
    context: physical.N3BPhysicalContext,
    route: Mapping[str, Any],
    value: Mapping[str, Any],
    map_validated: Mapping[str, Any],
    target_validated: Mapping[str, Any],
) -> Mapping[str, Any]:
    expected_unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": runner.SESSION_KIND,
        "plan_canonical_sha256": context.plan["integrity"]["canonical_sha256"],
        "session_id": route["session_id"],
        "cell_id": route["cell_id"],
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
        "map_target_continuity_deep_validated": True,
        "automatic_inference": False,
    }
    expected = {
        **expected_unsigned,
        "integrity": {
            "canonical_sha256": _sha256(expected_unsigned),
            "canonical_sha256_scope": (
                "entire physical N3B session observation excluding integrity; "
                "canonical JSON"
            ),
        },
    }
    if value != expected:
        raise N3BPhysicalAnalysisError(
            "physical N3B session observation does not match the deep pair"
        )
    return value


def _derived_observation(
    context: physical.N3BPhysicalContext,
    map_validated: Mapping[str, Any],
    target_validated: Mapping[str, Any],
) -> Mapping[str, Any]:
    map_observation = map_validated["observation"]
    target_observation = target_validated["observation"]
    continuity = target_observation["continuity"]
    if not isinstance(continuity, Mapping):
        raise N3BPhysicalAnalysisError("target continuity evidence is missing")
    try:
        observation = legacy_analyzer._build_n3_observation_records(
            context.plan["execution_manifest"],
            target_action_identity_sha256=target_validated[
                "action_identity_sha256"
            ],
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
        return legacy_analyzer.validate_n3_observation(
            context.plan["execution_manifest"], observation
        )
    except legacy_analyzer.N3AnalysisError as error:
        raise N3BPhysicalAnalysisError(
            f"physical N3B derived observation is invalid: {error}"
        ) from error


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
        raise N3BPhysicalAnalysisError("production lineage lost review artifact")
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
        raise N3BPhysicalAnalysisError("production profile lost review artifact")
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


def _validate_usage_chain(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    first_map = records[0]["map_production"].profile["usage"]
    baseline = first_map["cumulative_visible_refresh_count"]
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
            raise N3BPhysicalAnalysisError(
                "physical N3B usage counts do not form one exact action sequence"
            )
        if previous_target_completed_at is not None and (
            map_usage["last_visible_refresh_completed_at"]
            != previous_target_completed_at
        ):
            raise N3BPhysicalAnalysisError(
                "physical N3B next session does not name the prior target as latest"
            )
        previous_target_completed_at = record["target_validated"]["result"][
            "completed_at"
        ]
    return {
        "baseline_cumulative_visible_refresh_count": baseline,
        "final_completed_visible_refresh_count": baseline + 32,
        "all_32_actions_accounted_for_in_order": True,
        "each_target_usage_names_own_map_as_latest": True,
        "each_later_map_usage_names_prior_target_as_latest": True,
    }


def _williams_balance(routes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    block_orders: dict[str, list[str]] = {}
    position_counts: dict[str, dict[str, int]] = {
        cell: {str(position): 0 for position in range(1, 5)}
        for cell in ("Q1", "Q2", "Q3", "Q4")
    }
    predecessors: dict[str, int] = {}
    for block in range(1, 5):
        selected = [route for route in routes if route["block_index"] == block]
        if [route["session_position"] for route in selected] != [1, 2, 3, 4]:
            raise N3BPhysicalAnalysisError(
                "N3B block does not contain positions 1..4 in exact order"
            )
        order = [route["candidate_cell_id"] for route in selected]
        if set(order) != {"Q1", "Q2", "Q3", "Q4"}:
            raise N3BPhysicalAnalysisError(
                "N3B block does not contain each candidate exactly once"
            )
        block_orders[str(block)] = order
        for position, cell in enumerate(order, start=1):
            position_counts[cell][str(position)] += 1
        for first, second in zip(order, order[1:]):
            key = f"{first}->{second}"
            predecessors[key] = predecessors.get(key, 0) + 1
    if any(count != 1 for counts in position_counts.values() for count in counts.values()):
        raise N3BPhysicalAnalysisError(
            "N3B candidates are not balanced exactly once per position"
        )
    expected_predecessors = {
        f"{first}->{second}"
        for first in ("Q1", "Q2", "Q3", "Q4")
        for second in ("Q1", "Q2", "Q3", "Q4")
        if first != second
    }
    if set(predecessors) != expected_predecessors or any(
        count != 1 for count in predecessors.values()
    ):
        raise N3BPhysicalAnalysisError(
            "N3B Williams immediate-predecessor balance changed"
        )
    return {
        "design": "four-block-four-treatment-Williams-balanced-order",
        "block_orders": block_orders,
        "candidate_position_counts": position_counts,
        "ordered_immediate_predecessor_counts": dict(sorted(predecessors.items())),
        "each_candidate_once_per_block": True,
        "each_candidate_once_per_position": True,
        "each_ordered_immediate_predecessor_once": True,
    }


def _summaries_by(
    observations: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    field: str,
    values: Sequence[Any],
) -> dict[str, Any]:
    labels = list(dict.fromkeys(str(route[field]) for route in routes))
    return {
        label: legacy_analyzer._summaries(
            [
                observation
                for observation, value in zip(observations, values)
                if str(value) == label
            ]
        )
        for label in labels
    }


def _analyze(
    context: physical.N3BPhysicalContext,
    sessions: Sequence[N3BPhysicalSessionEvidence],
) -> dict[str, Any]:
    try:
        plan = physical.validate_n3b_physical_execution_context(context)
    except physical.N3BPhysicalExecutionError as error:
        raise N3BPhysicalAnalysisError(str(error)) from error
    routes = plan["selected_routes"]
    if len(routes) != 16 or len(sessions) != 16:
        raise N3BPhysicalAnalysisError(
            "physical N3B analysis requires exactly sixteen sessions"
        )
    deep_records: list[dict[str, Any]] = []
    observations: list[Mapping[str, Any]] = []
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
    for index, (route, session) in enumerate(zip(routes, sessions)):
        if not isinstance(session, N3BPhysicalSessionEvidence):
            raise N3BPhysicalAnalysisError(
                f"session {index + 1} is not N3BPhysicalSessionEvidence"
            )
        try:
            map_validated = physical.validate_n3b_physical_finalized_action_bundle(
                context,
                session.map_bundle,
                production_profile=session.map_production,
                expected_action_key=route["map_action_key"],
            )
            target_validated = (
                physical.validate_n3b_physical_finalized_action_bundle(
                    context,
                    session.target_bundle,
                    production_profile=session.target_production,
                    expected_action_key=route["target_action_key"],
                    prior_bundle=session.map_bundle,
                    prior_production_profile=session.map_production,
                )
            )
        except physical.N3BPhysicalExecutionError as error:
            raise N3BPhysicalAnalysisError(
                f"session {index + 1} deep validation failed: {error}"
            ) from error
        _validate_session_observation(
            context,
            route,
            session.physical_session_observation,
            map_validated,
            target_validated,
        )
        observation = _derived_observation(context, map_validated, target_validated)
        observations.append(observation)
        pair_lineage = [_lineage(session.map_production), _lineage(session.target_production)]
        for item in pair_lineage:
            if lineage is None:
                lineage = item
            elif item != lineage:
                raise N3BPhysicalAnalysisError(
                    "physical N3B panel/firmware/authority/profile lineage changed"
                )
        for action_key, production_profile in (
            (route["map_action_key"], session.map_production),
            (route["target_action_key"], session.target_production),
        ):
            profile = _profile_record(action_key, production_profile)
            profiles.append(profile)
            for key, value in (
                ("profile", profile["profile_file_sha256"]),
                ("usage", profile["usage_evidence_file_sha256"]),
                ("review", profile["review_artifact_file_sha256"]),
            ):
                if value in uniqueness[key]:
                    raise N3BPhysicalAnalysisError(
                        f"duplicate {key} evidence replay in physical N3B"
                    )
                uniqueness[key].add(value)
        action_values = {
            map_validated["action_identity_sha256"],
            target_validated["action_identity_sha256"],
        }
        attempt_values = {
            map_validated["attempt_id"],
            target_validated["attempt_id"],
        }
        result_values = {
            map_validated["result_file_sha256"],
            target_validated["result_file_sha256"],
        }
        finalization_values = {
            map_validated["finalization_file_sha256"],
            target_validated["finalization_file_sha256"],
        }
        source_observation_values = {
            session.map_bundle["observation"]["source_observation_file_sha256"],
            session.target_bundle["observation"]["source_observation_file_sha256"],
        }
        camera_value = session.target_bundle["observation"]["camera"][
            "capture_file_sha256"
        ]
        for key, values in (
            ("action", action_values),
            ("attempt", attempt_values),
            ("result", result_values),
            ("finalization", finalization_values),
            ("source_observation", source_observation_values),
        ):
            if len(values) != 2 or uniqueness[key].intersection(values):
                raise N3BPhysicalAnalysisError(
                    f"duplicate/cross-session {key} evidence in physical N3B"
                )
            uniqueness[key].update(values)
        if not isinstance(camera_value, str) or camera_value in uniqueness["camera"]:
            raise N3BPhysicalAnalysisError(
                "missing or duplicate target camera capture in physical N3B"
            )
        uniqueness["camera"].add(camera_value)
        deep_records.append(
            {
                "route": _snapshot(route),
                "physical_session_observation": _snapshot(
                    session.physical_session_observation
                ),
                "map_validated": map_validated,
                "target_validated": target_validated,
                "map_production": session.map_production,
                "target_production": session.target_production,
            }
        )
    assert lineage is not None
    expected_panel = plan["execution_manifest"]["panel"]
    expected_firmware = plan["execution_manifest"]["firmware"]
    if lineage["panel"] != expected_panel or lineage["firmware"] != expected_firmware:
        raise N3BPhysicalAnalysisError(
            "production lineage differs from the physical N3B panel/firmware"
        )
    usage_chain = _validate_usage_chain(deep_records)
    williams = _williams_balance(routes)
    usable = [
        observation
        for observation in observations
        if observation["pair_state"] == "complete-pass-pair"
    ]
    block_values = [route["block_index"] for route in routes]
    position_values = [route["session_position"] for route in routes]
    candidate_values = [route["candidate_cell_id"] for route in routes]
    additive = {
        metric: legacy_analyzer._additive_effects(usable, metric)
        for metric in KEY_METRICS
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "study": "N3B",
        "physical_plan_id": plan["plan_id"],
        "physical_plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "physical_plan_file_sha256": physical.n3b_physical_plan_file_sha256(plan),
        "physical_panel": _snapshot(expected_panel),
        "physical_firmware": _snapshot(expected_firmware),
        "reviewed_process_schedule": _snapshot(plan["process_schedule"]),
        "production_lineage": lineage,
        "action_profile_lineage_records": profiles,
        "usage_chain": usage_chain,
        "williams_design": williams,
        "expected_block_count": 4,
        "verified_block_count": 4,
        "expected_session_count": 16,
        "verified_session_count": len(deep_records),
        "expected_visible_action_count": 32,
        "verified_visible_action_count": 32,
        "session_chains": [
            {
                "block_index": item["route"]["block_index"],
                "session_position": item["route"]["session_position"],
                "candidate_cell_id": item["route"]["candidate_cell_id"],
                "session_id": item["route"]["session_id"],
                "map_action_identity_sha256": item["map_validated"][
                    "action_identity_sha256"
                ],
                "map_result_file_sha256": item["map_validated"][
                    "result_file_sha256"
                ],
                "map_finalization_file_sha256": item["map_validated"][
                    "finalization_file_sha256"
                ],
                "target_action_identity_sha256": item["target_validated"][
                    "action_identity_sha256"
                ],
                "target_result_file_sha256": item["target_validated"][
                    "result_file_sha256"
                ],
                "target_finalization_file_sha256": item["target_validated"][
                    "finalization_file_sha256"
                ],
                "physical_session_observation_canonical_sha256": item[
                    "physical_session_observation"
                ]["integrity"]["canonical_sha256"],
                "pair_state": observations[index]["pair_state"],
                "deep_physical_validation_passed": True,
            }
            for index, item in enumerate(deep_records)
        ],
        "complete_evidence_set": True,
        "usable_session_count": len(usable),
        "analysis_ready": len(usable) == 16,
        "overall_metric_summaries": legacy_analyzer._summaries(usable),
        "metric_summaries_by_block": _summaries_by(
            usable,
            [route for route, observation in zip(routes, observations) if observation in usable],
            "block_index",
            [
                value
                for value, observation in zip(block_values, observations)
                if observation in usable
            ],
        ),
        "metric_summaries_by_candidate": _summaries_by(
            usable,
            [route for route, observation in zip(routes, observations) if observation in usable],
            "candidate_cell_id",
            [
                value
                for value, observation in zip(candidate_values, observations)
                if observation in usable
            ],
        ),
        "metric_summaries_by_session_position": _summaries_by(
            usable,
            [route for route, observation in zip(routes, observations) if observation in usable],
            "session_position",
            [
                value
                for value, observation in zip(position_values, observations)
                if observation in usable
            ],
        ),
        "descriptive_additive_effects": additive,
        "camera_comparability": {
            "registered_camera_method_assets_bound_by_plan": True,
            "target_capture_count": 16,
            "distinct_target_capture_count": len(uniqueness["camera"]),
            "all_target_captures_distinct": len(uniqueness["camera"]) == 16,
            "capture_hashes_establish_content_identity_only": True,
            "photometric_or_visual_qualification_established": False,
            "state": (
                "REGISTERED_METHOD_AND_DISTINCT_CAPTURES_ONLY_NOT_QUALIFIED"
            ),
        },
        "qualification_state": "NOT_QUALIFIED",
        "inference_contract": {
            "descriptive_only": True,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "p95_reported_for_groups_with_n_less_than_10": False,
            "p99_reported_for_groups_with_n_less_than_10": False,
            "visual_qualification_allowed": False,
            "electrical_qualification_allowed": False,
            "hardware_qualification_allowed": False,
        },
        "classification": {
            "offline_analysis": True,
            "source_physical_evidence_deep_validated": True,
            "physical_session_observations_consumed": True,
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
        raise N3BPhysicalAnalysisError("physical N3B report must be an object")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise N3BPhysicalAnalysisError("physical N3B report integrity is invalid")
    if (
        report.get("schema_version") != SCHEMA_VERSION
        or report.get("kind") != REPORT_KIND
        or report.get("qualification_state") != "NOT_QUALIFIED"
        or report.get("expected_session_count") != 16
        or report.get("verified_session_count") != 16
        or report.get("verified_visible_action_count") != 32
        or report.get("inference_contract", {}).get(
            "hardware_qualification_allowed"
        )
        is not False
    ):
        raise N3BPhysicalAnalysisError(
            "physical N3B report completeness/qualification invariant changed"
        )


def analyze_n3b_physical_sessions(
    context: physical.N3BPhysicalContext,
    *,
    sessions: Sequence[N3BPhysicalSessionEvidence],
) -> dict[str, Any]:
    """Deep-validate exactly sixteen physical sessions and analyze them."""

    return _analyze(context, sessions)


def validate_n3b_physical_analysis_report(
    report: Mapping[str, Any],
    context: physical.N3BPhysicalContext,
    *,
    sessions: Sequence[N3BPhysicalSessionEvidence],
) -> Mapping[str, Any]:
    """Recompute the full deep analysis and require exact canonical equality."""

    expected = _analyze(context, sessions)
    if report != expected:
        raise N3BPhysicalAnalysisError(
            "physical N3B report differs from replayed deep evidence"
        )
    return report


def analyze_n3b_physical_result_files(
    *,
    plan_files: runner.N3BPhysicalPlanFiles,
    reviewer_key_file: Path,
    sessions: Sequence[N3BPhysicalSessionResultFiles],
) -> dict[str, Any]:
    """Load sixteen stored pairs without claim, network, device, or power I/O."""

    if len(sessions) != 16:
        raise N3BPhysicalAnalysisError(
            "physical N3B file analysis requires exactly sixteen sessions"
        )
    try:
        context = physical.load_n3b_physical_execution_context(
            plan_file=plan_files.plan,
            binding_review_artifact_file=plan_files.binding_review_artifact,
            minimum_interval_seconds=plan_files.minimum_interval_seconds,
            planned_cooldown_seconds=plan_files.planned_cooldown_seconds,
        )
    except physical.N3BPhysicalExecutionError as error:
        raise N3BPhysicalAnalysisError(str(error)) from error
    loaded: list[N3BPhysicalSessionEvidence] = []
    for index, files in enumerate(sessions, start=1):
        try:
            map_chain = runner.load_n3b_physical_finalized_action_chain(
                files.map_result_file,
                reviewer_key_file=reviewer_key_file,
            )
            target_chain = runner.load_n3b_physical_finalized_action_chain(
                files.target_result_file,
                reviewer_key_file=reviewer_key_file,
                primer_result_file=files.map_result_file,
            )
        except runner.N3BPhysicalActionError as error:
            raise N3BPhysicalAnalysisError(
                f"stored session {index} failed replay: {error}"
            ) from error
        if map_chain.context.plan != context.plan or target_chain.context.plan != context.plan:
            raise N3BPhysicalAnalysisError(
                f"stored session {index} belongs to another physical plan"
            )
        session_observation = _read_canonical_json(
            files.target_result_file.parent / runner.SESSION_OBSERVATION_FILENAME,
            label=f"physical N3B session {index} observation",
        )
        loaded.append(
            N3BPhysicalSessionEvidence(
                map_bundle=map_chain.bundle,
                target_bundle=target_chain.bundle,
                map_production=map_chain.production,
                target_production=target_chain.production,
                physical_session_observation=session_observation,
            )
        )
    return analyze_n3b_physical_sessions(context, sessions=loaded)


__all__ = [
    "N3BPhysicalAnalysisError",
    "N3BPhysicalSessionEvidence",
    "N3BPhysicalSessionResultFiles",
    "REPORT_KIND",
    "analyze_n3b_physical_result_files",
    "analyze_n3b_physical_sessions",
    "validate_n3b_physical_analysis_report",
]
