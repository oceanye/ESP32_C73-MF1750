#!/usr/bin/env python3
"""Deep offline analysis for one complete physical N3A repeat branch.

The analyzer accepts exactly the repeat-2, repeat-3, or repeat-4 session set
selected by the physical plan.  Every MAP and target result is replayed by the
public production validator, which in turn replays the eight physical N2
source results with the trusted N2 reviewer key.  Statistics are descriptive
only and the report is always ``NOT_QUALIFIED``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    read_local_regular_file,
)
from tools import g1_s1_n3_analyzer as statistics  # noqa: E402
from tools import g1_s1_n3a_physical_execution as physical  # noqa: E402
from tools import g1_s1_rc2g_n2_physical_analyzer as n2_analyzer  # noqa: E402
from tools import g1_s1_rc2g_n3a_physical_once as runner  # noqa: E402


SCHEMA_VERSION = 1
REPORT_KIND = "mf1750-g1-s1-n3a-physical-repeatability-analysis"
REPORT_HASH_SCOPE = (
    "entire N3A physical repeatability report excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_SESSION_OBSERVATION_BYTES = 1024 * 1024

METRIC_PATHS = {
    **{
        f"timing.map.{field}": ("map", "electrical", "timing_ms", field)
        for field in statistics.TIMING_FIELDS
    },
    **{
        f"timing.target.{field}": ("target", "electrical", "timing_ms", field)
        for field in statistics.TIMING_FIELDS
    },
    "temperature.pre_map_c": ("map", "thermal", "pre_action_c"),
    "temperature.post_map_c": ("map", "thermal", "post_action_c"),
    "temperature.post_target_c": ("target", "thermal", "post_action_c"),
    "temperature.session_max_c": ("derived", "session_max_c"),
    "visual.photo_difference_score": (
        "target",
        "visual",
        "photo_difference_score",
    ),
    "visual.photo_luminance_mean": (
        "target",
        "visual",
        "photo_luminance_mean",
    ),
    "visual.photo_luminance_standard_deviation": (
        "target",
        "visual",
        "photo_luminance_standard_deviation",
    ),
}


class N3APhysicalAnalysisError(ValueError):
    """The physical repeatability evidence or report failed closed."""


@dataclass(frozen=True)
class N3APhysicalSessionEvidence:
    map_bundle: Mapping[str, Any]
    target_bundle: Mapping[str, Any]
    map_production: ValidatedProductionProfile
    target_production: ValidatedProductionProfile
    physical_session_observation: Mapping[str, Any]


@dataclass(frozen=True)
class N3APhysicalSessionResultFiles:
    map_result_file: Path
    target_result_file: Path


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3APhysicalAnalysisError(str(error)) from error


def _sha256(value: Any) -> str:
    return physical._sha256(value)


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3APhysicalAnalysisError(str(error)) from error


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
        raise N3APhysicalAnalysisError(f"{label} is invalid: {error}") from error
    if not isinstance(value, Mapping) or artifact.payload != _canonical(value):
        raise N3APhysicalAnalysisError(f"{label} must be canonical JSON")
    return value


def _expected_session_observation(
    context: physical.N3APhysicalContext,
    route: Mapping[str, Any],
    map_validated: Mapping[str, Any],
    target_validated: Mapping[str, Any],
) -> Mapping[str, Any]:
    plan = physical.validate_n3a_physical_execution_context(context)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": runner.SESSION_KIND,
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "winner_cell_id": plan["selection"]["winner_cell_id"],
        "repeat_count": plan["selection"]["repeat_count"],
        "repeat_ordinal": route["repeat_ordinal"],
        "session_id": route["session_id"],
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
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": (
                "entire physical N3A session observation excluding integrity; "
                "canonical JSON"
            ),
        },
    }


def _authority_lineage(production: ValidatedProductionProfile) -> dict[str, Any]:
    authority = production.inputs.limit_authority
    if "policy_id" in authority:
        identity = {
            "issuer": authority["issuer"],
            "authority_id": authority["policy_id"],
        }
    else:
        identity = {
            "issuer": authority["supplier_id"],
            "authority_id": authority["document_id"],
        }
    return {
        "kind": production.report["limit_authority_kind"],
        "classification": production.report["limit_authority_classification"],
        "identity": identity,
        "panel_model": authority["panel_model"],
        "limits": _snapshot(authority["limits"]),
        "field_provenance": _snapshot(authority.get("field_provenance")),
        "not_a_supplier_rating": authority.get("not_a_supplier_rating", False),
    }


def _production_lineage(production: ValidatedProductionProfile) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None:
        raise N3APhysicalAnalysisError("production lineage lost review artifact")
    return {
        "panel": _snapshot(production.profile["panel"]),
        "firmware": _snapshot(production.profile["firmware"]),
        "firmware_binary_sha256": production.inputs.firmware_binary.sha256,
        "campaign_canonical_sha256": production.inputs.campaign["integrity"][
            "canonical_sha256"
        ],
        "authority_lineage": _authority_lineage(production),
        "profile_id": production.profile["profile_id"],
        "reviewer_id": production.profile["review"]["reviewer_id"],
        "reviewer_key_id": production.reviewer_key_id,
    }


def _profile_record(
    action_key: str, production: ValidatedProductionProfile
) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None:
        raise N3APhysicalAnalysisError("production profile lost review artifact")
    return {
        "action_key": action_key,
        "profile_id": production.profile["profile_id"],
        "profile_version": production.profile["profile_version"],
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "usage_evidence_file_sha256": production.inputs.usage_evidence_file.sha256,
        "review_artifact_file_sha256": review.sha256,
        "limit_authority_file_sha256": production.inputs.limit_authority_file.sha256,
        "evaluated_at": production.report["evaluated_at"],
        "usage": _snapshot(production.profile["usage"]),
    }


def _metric_value(
    path: Sequence[str],
    map_observation: Mapping[str, Any],
    target_observation: Mapping[str, Any],
) -> float:
    source = path[0]
    if source == "derived":
        value: Any = max(
            map_observation["thermal"]["session_max_c"],
            target_observation["thermal"]["session_max_c"],
        )
    else:
        value = map_observation if source == "map" else target_observation
        for key in path[1:]:
            value = value[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N3APhysicalAnalysisError("physical N3A metric is not numeric")
    return float(value)


def _metric_series(records: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    return {
        metric: [
            _metric_value(
                path,
                record["map_validated"]["observation"],
                record["target_validated"]["observation"],
            )
            for record in records
        ]
        for metric, path in METRIC_PATHS.items()
    }


def _drift(values: Sequence[float]) -> dict[str, Any]:
    adjacent = [second - first for first, second in zip(values, values[1:])]
    return {
        "first": values[0],
        "last": values[-1],
        "last_minus_first": values[-1] - values[0],
        "observed_minimum": min(values),
        "observed_maximum": max(values),
        "observed_range": max(values) - min(values),
        "adjacent_differences": adjacent,
        "maximum_absolute_adjacent_difference": (
            max(abs(value) for value in adjacent) if adjacent else None
        ),
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
            raise N3APhysicalAnalysisError(
                "physical N3A usage counts do not form the exact repeat sequence"
            )
        if previous_target_completed_at is not None and map_usage[
            "last_visible_refresh_completed_at"
        ] != previous_target_completed_at:
            raise N3APhysicalAnalysisError(
                "physical N3A next MAP does not name the prior target as latest"
            )
        previous_target_completed_at = record["target_validated"]["result"][
            "completed_at"
        ]
    visible_count = 2 * len(records)
    return {
        "baseline_cumulative_visible_refresh_count": baseline,
        "final_completed_visible_refresh_count": baseline + visible_count,
        "all_visible_actions_accounted_for_in_order": True,
        "each_target_usage_names_own_map_as_latest": True,
        "each_later_map_usage_names_prior_target_as_latest": True,
    }


def _analyze(
    context: physical.N3APhysicalContext,
    sessions: Sequence[N3APhysicalSessionEvidence],
) -> dict[str, Any]:
    try:
        plan = physical.validate_n3a_physical_execution_context(context)
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalAnalysisError(str(error)) from error
    routes = plan["selected_routes"]
    repeat_count = plan["selection"]["repeat_count"]
    if repeat_count not in (2, 3, 4) or len(routes) != repeat_count or len(
        sessions
    ) != repeat_count:
        raise N3APhysicalAnalysisError(
            "physical N3A requires exactly its selected repeat-2/3/4 session set"
        )
    records: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    common_lineage: Optional[dict[str, Any]] = None
    uniqueness: dict[str, set[str]] = {
        key: set()
        for key in (
            "action",
            "attempt",
            "result",
            "finalization",
            "profile",
            "usage",
            "review",
            "source_observation",
            "camera",
        )
    }
    for index, (route, session) in enumerate(zip(routes, sessions), start=1):
        if not isinstance(session, N3APhysicalSessionEvidence):
            raise N3APhysicalAnalysisError(
                f"session {index} is not N3APhysicalSessionEvidence"
            )
        try:
            map_validated = physical.validate_n3a_physical_finalized_action_bundle(
                context,
                session.map_bundle,
                production_profile=session.map_production,
                expected_action_key=route["map_action_key"],
            )
            target_validated = physical.validate_n3a_physical_finalized_action_bundle(
                context,
                session.target_bundle,
                production_profile=session.target_production,
                expected_action_key=route["target_action_key"],
                prior_bundle=session.map_bundle,
                prior_production_profile=session.map_production,
            )
        except physical.N3APhysicalExecutionError as error:
            raise N3APhysicalAnalysisError(
                f"session {index} deep validation failed: {error}"
            ) from error
        if session.physical_session_observation != _expected_session_observation(
            context, route, map_validated, target_validated
        ):
            raise N3APhysicalAnalysisError(
                f"session {index} physical pair observation changed"
            )
        for action_key, production in (
            (route["map_action_key"], session.map_production),
            (route["target_action_key"], session.target_production),
        ):
            lineage = _production_lineage(production)
            if common_lineage is None:
                common_lineage = lineage
            elif lineage != common_lineage:
                raise N3APhysicalAnalysisError(
                    "physical N3A panel/firmware/authority/profile lineage changed"
                )
            profile = _profile_record(action_key, production)
            profiles.append(profile)
            for key, field in (
                ("profile", "profile_file_sha256"),
                ("usage", "usage_evidence_file_sha256"),
                ("review", "review_artifact_file_sha256"),
            ):
                value = profile[field]
                if value in uniqueness[key]:
                    raise N3APhysicalAnalysisError(
                        f"duplicate {key} evidence replay in physical N3A"
                    )
                uniqueness[key].add(value)
        pairs = {
            "action": {
                map_validated["action_identity_sha256"],
                target_validated["action_identity_sha256"],
            },
            "attempt": {map_validated["attempt_id"], target_validated["attempt_id"]},
            "result": {
                map_validated["result_file_sha256"],
                target_validated["result_file_sha256"],
            },
            "finalization": {
                map_validated["finalization_file_sha256"],
                target_validated["finalization_file_sha256"],
            },
            "source_observation": {
                session.map_bundle["observation"]["source_observation_file_sha256"],
                session.target_bundle["observation"][
                    "source_observation_file_sha256"
                ],
            },
        }
        for key, values in pairs.items():
            if len(values) != 2 or uniqueness[key].intersection(values):
                raise N3APhysicalAnalysisError(
                    f"duplicate/cross-session {key} evidence in physical N3A"
                )
            uniqueness[key].update(values)
        camera = session.target_bundle["observation"]["camera"][
            "capture_file_sha256"
        ]
        if not isinstance(camera, str) or camera in uniqueness["camera"]:
            raise N3APhysicalAnalysisError(
                "missing or replayed target camera capture in physical N3A"
            )
        uniqueness["camera"].add(camera)
        continuity = target_validated["observation"]["continuity"]
        pair_pass = (
            map_validated["state"] == "PASS"
            and target_validated["state"] == "PASS"
            and all(value is False for value in continuity.values())
        )
        records.append(
            {
                "route": _snapshot(route),
                "map_validated": map_validated,
                "target_validated": target_validated,
                "map_production": session.map_production,
                "target_production": session.target_production,
                "physical_session_observation": _snapshot(
                    session.physical_session_observation
                ),
                "pair_state": "complete-pass-pair" if pair_pass else "finalized-nonpass-pair",
            }
        )
    assert common_lineage is not None
    campaign = plan["physical_rebind"]["physical_campaign"]
    if (
        common_lineage["panel"] != campaign["panel"]
        or common_lineage["firmware"] != campaign["firmware"]
    ):
        raise N3APhysicalAnalysisError(
            "production lineage differs from physical N3A panel/firmware"
        )
    usage_chain = _validate_usage_chain(records)
    usable = [record for record in records if record["pair_state"] == "complete-pass-pair"]
    series = _metric_series(usable) if usable else {}
    summaries = {
        metric: statistics.summarize_numeric(values)
        for metric, values in series.items()
    }
    drift = {metric: _drift(values) for metric, values in series.items()}
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "study": "N3A",
        "physical_plan_id": plan["plan_id"],
        "physical_plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "physical_plan_file_sha256": _sha256(plan),
        "n2_physical_provenance_canonical_sha256": plan[
            "n2_physical_provenance"
        ]["canonical_sha256"],
        "eight_n2_finalized_result_directories_replayed": True,
        "physical_panel": _snapshot(campaign["panel"]),
        "physical_firmware": _snapshot(campaign["firmware"]),
        "winner_cell_id": plan["selection"]["winner_cell_id"],
        "winner_algorithm": plan["selection"]["winner"]["algorithm"],
        "repeat_count": repeat_count,
        "reviewed_process_schedule": _snapshot(plan["process_schedule"]),
        "production_lineage": common_lineage,
        "action_profile_lineage_records": profiles,
        "usage_chain": usage_chain,
        "expected_session_count": repeat_count,
        "verified_session_count": len(records),
        "expected_visible_action_count": 2 * repeat_count,
        "verified_visible_action_count": 2 * len(records),
        "session_chains": [
            {
                "repeat_ordinal": record["route"]["repeat_ordinal"],
                "session_id": record["route"]["session_id"],
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
                "physical_session_observation_canonical_sha256": record[
                    "physical_session_observation"
                ]["integrity"]["canonical_sha256"],
                "pair_state": record["pair_state"],
                "deep_physical_validation_passed": True,
            }
            for record in records
        ],
        "complete_evidence_set": True,
        "usable_session_count": len(usable),
        "analysis_ready": len(usable) == repeat_count,
        "metric_summaries": summaries,
        "ordered_repeat_drift": drift,
        "small_sample_contract": {
            "sample_size": len(usable),
            "p95_and_p99_must_be_null_when_n_less_than_10": True,
            "all_p95_null": all(item["p95"] is None for item in summaries.values()),
            "all_p99_null": all(item["p99"] is None for item in summaries.values()),
            "population_inference_allowed": False,
        },
        "camera_comparability": {
            "registered_camera_method_assets_bound_by_plan": True,
            "target_capture_count": repeat_count,
            "distinct_target_capture_count": len(uniqueness["camera"]),
            "all_target_captures_distinct": len(uniqueness["camera"]) == repeat_count,
            "capture_hashes_establish_content_identity_only": True,
            "photometric_or_visual_qualification_established": False,
            "state": "REGISTERED_METHOD_AND_DISTINCT_CAPTURES_ONLY_NOT_QUALIFIED",
        },
        "qualification_state": "NOT_QUALIFIED",
        "inference_contract": {
            "descriptive_repeatability_only": True,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "algorithm_qualification_allowed": False,
            "visual_qualification_allowed": False,
            "electrical_qualification_allowed": False,
            "hardware_qualification_allowed": False,
        },
        "classification": {
            "offline_analysis": True,
            "source_physical_evidence_deep_validated": True,
            "raw_n2_evidence_replayed": True,
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
        raise N3APhysicalAnalysisError("physical N3A report must be an object")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity", None)
    repeat_count = report.get("repeat_count")
    if (
        integrity != _integrity(unsigned)
        or report.get("schema_version") != SCHEMA_VERSION
        or report.get("kind") != REPORT_KIND
        or repeat_count not in (2, 3, 4)
        or report.get("expected_session_count") != repeat_count
        or report.get("verified_session_count") != repeat_count
        or report.get("verified_visible_action_count") != 2 * repeat_count
        or report.get("qualification_state") != "NOT_QUALIFIED"
        or report.get("inference_contract", {}).get(
            "hardware_qualification_allowed"
        )
        is not False
    ):
        raise N3APhysicalAnalysisError(
            "physical N3A report integrity/completeness invariant changed"
        )


def analyze_n3a_physical_sessions(
    context: physical.N3APhysicalContext,
    *,
    sessions: Sequence[N3APhysicalSessionEvidence],
) -> dict[str, Any]:
    return _analyze(context, sessions)


def validate_n3a_physical_analysis_report(
    report: Mapping[str, Any],
    context: physical.N3APhysicalContext,
    *,
    sessions: Sequence[N3APhysicalSessionEvidence],
) -> Mapping[str, Any]:
    expected = _analyze(context, sessions)
    if report != expected:
        raise N3APhysicalAnalysisError(
            "physical N3A report differs from replayed deep evidence"
        )
    return report


def analyze_n3a_physical_result_files(
    *,
    plan_files: runner.N3APhysicalPlanFiles,
    profile_reviewer_key_file: Path,
    sessions: Sequence[N3APhysicalSessionResultFiles],
) -> dict[str, Any]:
    try:
        context = physical.load_n3a_physical_execution_context(
            plan_file=plan_files.plan,
            binding_review_artifact_file=plan_files.binding_review_artifact,
            minimum_interval_seconds=plan_files.minimum_interval_seconds,
            planned_cooldown_seconds=plan_files.planned_cooldown_seconds,
            n2_result_directories=plan_files.n2_result_directories,
            n2_reviewer_key_file=plan_files.n2_reviewer_key,
        )
        plan = physical.validate_n3a_physical_execution_context(context)
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalAnalysisError(str(error)) from error
    if len(sessions) != plan["selection"]["repeat_count"]:
        raise N3APhysicalAnalysisError(
            "physical N3A file analysis session count differs from selected repeat"
        )
    loaded: list[N3APhysicalSessionEvidence] = []
    seen_directories: set[Path] = set()
    for index, files in enumerate(sessions, start=1):
        directories = {
            files.map_result_file.parent.resolve(),
            files.target_result_file.parent.resolve(),
        }
        if len(directories) != 2 or seen_directories.intersection(directories):
            raise N3APhysicalAnalysisError(
                "duplicate result directory supplied to physical N3A analyzer"
            )
        seen_directories.update(directories)
        try:
            map_chain = runner.load_n3a_physical_finalized_action_chain(
                files.map_result_file,
                n2_result_directories=plan_files.n2_result_directories,
                n2_reviewer_key_file=plan_files.n2_reviewer_key,
                profile_reviewer_key_file=profile_reviewer_key_file,
            )
            target_chain = runner.load_n3a_physical_finalized_action_chain(
                files.target_result_file,
                n2_result_directories=plan_files.n2_result_directories,
                n2_reviewer_key_file=plan_files.n2_reviewer_key,
                profile_reviewer_key_file=profile_reviewer_key_file,
                primer_result_file=files.map_result_file,
            )
        except runner.N3APhysicalActionError as error:
            raise N3APhysicalAnalysisError(
                f"stored session {index} failed replay: {error}"
            ) from error
        if map_chain.context.plan != plan or target_chain.context.plan != plan:
            raise N3APhysicalAnalysisError(
                f"stored session {index} belongs to another physical plan"
            )
        session_observation = _read_canonical_json(
            files.target_result_file.parent / runner.SESSION_OBSERVATION_FILENAME,
            label=f"physical N3A session {index} observation",
        )
        loaded.append(
            N3APhysicalSessionEvidence(
                map_bundle=map_chain.bundle,
                target_bundle=target_chain.bundle,
                map_production=map_chain.production,
                target_production=target_chain.production,
                physical_session_observation=session_observation,
            )
        )
    return analyze_n3a_physical_sessions(context, sessions=loaded)


def validate_n3a_physical_analysis_result_files(
    report: Mapping[str, Any],
    *,
    plan_files: runner.N3APhysicalPlanFiles,
    profile_reviewer_key_file: Path,
    sessions: Sequence[N3APhysicalSessionResultFiles],
) -> Mapping[str, Any]:
    """Re-read every actual file, recompute the report, and require equality."""

    expected = analyze_n3a_physical_result_files(
        plan_files=plan_files,
        profile_reviewer_key_file=profile_reviewer_key_file,
        sessions=sessions,
    )
    if report != expected:
        raise N3APhysicalAnalysisError(
            "stored physical N3A report differs from actual deep evidence replay"
        )
    return report


def _positive(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not number > 0 or number != number or number in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return number


def _nonnegative(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if number < 0 or number != number or number in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("value must be non-negative and finite")
    return number


def _n2_directories(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, path = value.partition("=")
        if not separator or key in result or key not in n2_analyzer.EXPECTED_RESULT_KEYS:
            raise N3APhysicalAnalysisError(
                "--n2-result must be one unique exact ACTION_KEY=PATH"
            )
        result[key] = Path(path)
    if set(result) != set(n2_analyzer.EXPECTED_RESULT_KEYS):
        raise N3APhysicalAnalysisError("exactly eight --n2-result values are required")
    return result


def _session_files(values: Sequence[str]) -> list[N3APhysicalSessionResultFiles]:
    result = []
    for value in values:
        map_file, separator, target_file = value.partition(",")
        if not separator or not map_file or not target_file:
            raise N3APhysicalAnalysisError(
                "--session must be MAP_RESULT_FILE,TARGET_RESULT_FILE"
            )
        result.append(N3APhysicalSessionResultFiles(Path(map_file), Path(target_file)))
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--physical-plan", type=Path, required=True)
    parser.add_argument("--binding-review-artifact", type=Path, required=True)
    parser.add_argument("--minimum-interval-seconds", type=_positive, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=_nonnegative, required=True)
    parser.add_argument("--n2-result", action="append", default=[])
    parser.add_argument("--n2-reviewer-key", type=Path, required=True)
    parser.add_argument("--profile-reviewer-key", type=Path, required=True)
    parser.add_argument("--session", action="append", default=[])
    parser.add_argument("--validate-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        args.n2_result_directories = _n2_directories(args.n2_result)
        args.sessions = _session_files(args.session)
    except N3APhysicalAnalysisError as error:
        parser.error(str(error))
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        expected = analyze_n3a_physical_result_files(
            plan_files=runner.N3APhysicalPlanFiles(
                plan=args.physical_plan,
                binding_review_artifact=args.binding_review_artifact,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
                n2_result_directories=args.n2_result_directories,
                n2_reviewer_key=args.n2_reviewer_key,
            ),
            profile_reviewer_key_file=args.profile_reviewer_key,
            sessions=args.sessions,
        )
        if args.validate_report is not None:
            report = _read_canonical_json(
                args.validate_report, label="stored physical N3A analysis report"
            )
            if report != expected:
                raise N3APhysicalAnalysisError(
                    "stored physical N3A report differs from actual deep evidence replay"
                )
        else:
            report = expected
        payload = _canonical(report)
        if args.output is not None:
            if os.path.lexists(args.output):
                raise N3APhysicalAnalysisError("output already exists; refusing overwrite")
            with args.output.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if args.output.read_bytes() != payload:
                raise N3APhysicalAnalysisError("written analysis bytes changed")
    except (N3APhysicalAnalysisError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N3APhysicalAnalysisError",
    "N3APhysicalSessionEvidence",
    "N3APhysicalSessionResultFiles",
    "REPORT_KIND",
    "analyze_n3a_physical_result_files",
    "analyze_n3a_physical_sessions",
    "main",
    "parse_args",
    "validate_n3a_physical_analysis_report",
    "validate_n3a_physical_analysis_result_files",
]
