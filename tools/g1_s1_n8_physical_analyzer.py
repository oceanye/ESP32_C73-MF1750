#!/usr/bin/env python3
"""Deep, descriptive-only analysis for exactly fifteen physical N8 actions.

The analyzer accepts no loose measurements.  Each action must retain its
deeply validated production profile and complete finalized bundle.  Stored
file analysis additionally reloads the actual physical contract, firmware,
authority, usage, signed review, and trusted reviewer key bytes before any
descriptive result is built.  No claim, authorization, network, device,
firmware, reset, GPIO, or power I/O is performed here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    ResultState,
    ValidatedProductionProfile,
    canonical_json_bytes,
)
from tools import g1_s1_n8_analyzer as descriptive  # noqa: E402
from tools import g1_s1_n8_physical_execution as physical  # noqa: E402
from tools import g1_s1_rc2g_n8_physical_once as runner  # noqa: E402


SCHEMA_VERSION = 1
REPORT_KIND = "mf1750-g1-s1-n8-physical-deep-descriptive-analysis"
REPORT_HASH_SCOPE = (
    "entire physical N8 deep descriptive analysis excluding integrity; "
    "UTF-8 JSON with sorted keys, no whitespace, ensure_ascii=false, "
    "allow_nan=false"
)


class N8PhysicalAnalysisError(ValueError):
    """The physical N8 evidence set or derived report failed closed."""


@dataclass(frozen=True)
class N8PhysicalActionEvidence:
    bundle: Mapping[str, Any]
    production: ValidatedProductionProfile


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N8PhysicalAnalysisError(str(error)) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8PhysicalAnalysisError(str(error)) from error


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": REPORT_HASH_SCOPE,
    }


def _lineage(production: ValidatedProductionProfile) -> dict[str, Any]:
    try:
        return _snapshot(physical._production_semantic_lineage(production))
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalAnalysisError(str(error)) from error


def _profile_record(
    action_key: str, production: ValidatedProductionProfile
) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N8PhysicalAnalysisError(
            "physical N8 production profile lost review/key evidence"
        )
    return {
        "action_key": action_key,
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "firmware_binary_file_sha256": (
            production.inputs.firmware_binary.sha256
        ),
        "limit_authority_file_sha256": (
            production.inputs.limit_authority_file.sha256
        ),
        "usage_evidence_file_sha256": (
            production.inputs.usage_evidence_file.sha256
        ),
        "review_artifact_file_sha256": review.sha256,
        "reviewer_key_id": production.reviewer_key_id,
        "evaluated_at": production.report["evaluated_at"],
        "usage": _snapshot(production.profile["usage"]),
    }


def _derived_observation(
    context: physical.N8PhysicalContext,
    bundle: Mapping[str, Any],
    validated: Mapping[str, Any],
    production: ValidatedProductionProfile,
) -> dict[str, Any]:
    observation = validated["observation"]
    camera = observation["camera"]
    thermal = observation["external_temperature"]
    electrical = observation["electrical"]
    runtime_comparability = {
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "panel": context.physical_campaign["panel"],
        "firmware": context.physical_campaign["firmware"],
        "measurement_registry": context.contract["measurement_registry"],
        "temperature_bin_plan": context.contract["temperature_bin_plan"],
        "reviewed_schedule": context.contract["reviewed_schedule"],
        "production_static_lineage": _lineage(production),
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
        "artifact_severity_score": observation["visual"][
            "artifact_severity_score"
        ],
        "external_temperature": _snapshot(thermal),
        "electrical": _snapshot(electrical),
        "continuity": _snapshot(observation["continuity"]),
        "camera": {
            "capture_file_sha256": camera["capture_file_sha256"],
            "capture_evidence_sha256": camera["capture_evidence_sha256"],
            "body_asset_sha256": camera["body_asset_sha256"],
            "lens_asset_sha256": camera["lens_asset_sha256"],
            "mount_asset_sha256": camera["mount_asset_sha256"],
            "fixed_exposure_profile_sha256": camera[
                "fixed_exposure_profile_sha256"
            ],
            "crop_asset_sha256": camera["crop_asset_sha256"],
            "illumination_asset_sha256": camera[
                "illumination_asset_sha256"
            ],
        },
        "visual_pass": observation["visual_pass"],
        "electrical_pass": observation["electrical_pass"],
        "thermal_pass": observation["thermal_pass"],
        "temperature_bin_pass": observation["temperature_bin_pass"],
        "continuity_pass": observation["continuity_pass"],
        "execution_evidence_verified": True,
        "qualification_state": "NOT_QUALIFIED",
    }


def _validate_global_usage_chain(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(records) != 15:
        raise N8PhysicalAnalysisError(
            "physical N8 usage audit requires exactly fifteen actions"
        )
    baseline = records[0]["production"].profile["usage"][
        "cumulative_visible_refresh_count"
    ]
    previous_completed_at: Optional[str] = None
    for index, record in enumerate(records):
        validated = record["validated"]
        usage = record["production"].profile["usage"]
        if (
            usage["cumulative_visible_refresh_count"] != baseline + index
            or usage["session_visible_refresh_count"]
            != validated["ordinal"] - 1
            or usage["consecutive_visible_refresh_count"]
            != validated["ordinal"] - 1
        ):
            raise N8PhysicalAnalysisError(
                "physical N8 global usage counts do not match all 15 actions"
            )
        if index and usage["last_visible_refresh_completed_at"] != (
            previous_completed_at
        ):
            raise N8PhysicalAnalysisError(
                "physical N8 usage does not name the exact prior global result"
            )
        previous_completed_at = validated["result"]["completed_at"]
    return {
        "baseline_cumulative_visible_refresh_count": baseline,
        "final_completed_visible_refresh_count": baseline + 15,
        "all_15_actions_accounted_for_in_order": True,
        "within_session_usage_matches_action_ordinal": True,
        "each_action_after_first_names_prior_global_result_as_latest": True,
    }


def _uniqueness(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    fields = {
        "action": [
            record["validated"]["action_identity_sha256"] for record in records
        ],
        "attempt": [record["bundle"]["evidence"]["attempt_id"] for record in records],
        "claim": [record["validated"]["claim_file_sha256"] for record in records],
        "bundle": [_sha256(record["bundle"]) for record in records],
        "result": [
            record["validated"]["result_file_sha256"] for record in records
        ],
        "finalization": [
            record["validated"]["finalization_file_sha256"]
            for record in records
        ],
        "profile": [
            record["profile"]["profile_file_sha256"] for record in records
        ],
        "usage": [
            record["profile"]["usage_evidence_file_sha256"]
            for record in records
        ],
        "review": [
            record["profile"]["review_artifact_file_sha256"]
            for record in records
        ],
        "source_observation": [
            record["bundle"]["observation"][
                "source_observation_file_sha256"
            ]
            for record in records
        ],
        "camera": [
            record["bundle"]["observation"]["camera"][
                "capture_file_sha256"
            ]
            for record in records
        ],
        "camera_evidence": [
            record["bundle"]["observation"]["camera"][
                "capture_evidence_sha256"
            ]
            for record in records
        ],
    }
    for label, values in fields.items():
        if len(values) != 15 or len(set(values)) != 15:
            raise N8PhysicalAnalysisError(
                f"duplicate/replayed {label} evidence in physical N8"
            )
    return {
        f"unique_{label}_count": len(set(values))
        for label, values in fields.items()
    }


def _sequence_summaries(
    context: physical.N8PhysicalContext,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for sequence in context.contract["sequences"]:
        sequence_id = sequence["sequence_id"]
        selected = [
            item for item in observations if item["sequence_id"] == sequence_id
        ]
        expected = [
            row
            for row in context.contract["fixed_actions"]
            if row["sequence_id"] == sequence_id
        ]
        if (
            len(selected) != len(expected)
            or [item["action_key"] for item in selected]
            != [row["action_key"] for row in expected]
        ):
            raise N8PhysicalAnalysisError(
                "physical N8 sequence membership/order changed"
            )
        result[sequence_id] = {
            "power_mode": expected[0]["power_mode"],
            "temperature_bin_id": expected[0]["temperature_bin_id"],
            "action_keys": [item["action_key"] for item in selected],
            "verified_action_count": len(selected),
            "all_actions_pass": all(
                item["state"] == ResultState.PASS.value for item in selected
            ),
            "metric_summaries": descriptive._metric_summaries(selected),
            "aba_evidence": (
                descriptive._aba_evidence(selected)
                if sequence_id == context.contract["sequences"][0]["sequence_id"]
                else None
            ),
            "qualification_state": "NOT_QUALIFIED",
        }
    if len(result) != 5:
        raise N8PhysicalAnalysisError(
            "physical N8 analysis must contain exactly five sequences"
        )
    return result


def _analyze(
    context: physical.N8PhysicalContext,
    actions: Sequence[N8PhysicalActionEvidence],
) -> dict[str, Any]:
    try:
        physical.validate_n8_physical_execution_context(context)
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalAnalysisError(str(error)) from error
    rows = context.contract["fixed_actions"]
    if len(rows) != 15 or len(actions) != 15:
        raise N8PhysicalAnalysisError(
            "physical N8 analysis requires exactly fifteen ordered actions"
        )

    records: list[dict[str, Any]] = []
    prior_profiles: list[ValidatedProductionProfile] = []
    prior_sequence: Optional[str] = None
    lineage: Optional[dict[str, Any]] = None
    for index, (expected, action) in enumerate(zip(rows, actions), start=1):
        if not isinstance(action, N8PhysicalActionEvidence):
            raise N8PhysicalAnalysisError(
                f"physical N8 action {index} has the wrong evidence type"
            )
        if expected["sequence_id"] != prior_sequence:
            prior_profiles = []
            prior_sequence = expected["sequence_id"]
        try:
            validated = physical.validate_n8_physical_finalized_action_bundle(
                context,
                action.bundle,
                production_profile=action.production,
                prior_production_profiles=tuple(prior_profiles),
                expected_action_key=expected["action_key"],
            )
        except physical.N8PhysicalExecutionError as error:
            raise N8PhysicalAnalysisError(
                f"physical N8 action {index} deep validation failed: {error}"
            ) from error
        if (
            validated["action_identity_sha256"]
            != expected["action_identity_sha256"]
            or validated["sequence_id"] != expected["sequence_id"]
            or validated["ordinal"] != expected["ordinal"]
            or validated["state"] != ResultState.PASS.value
        ):
            raise N8PhysicalAnalysisError(
                "physical N8 actions are reordered, cross-bound, or not PASS"
            )
        current_lineage = _lineage(action.production)
        if lineage is None:
            lineage = current_lineage
        elif current_lineage != lineage:
            raise N8PhysicalAnalysisError(
                "physical N8 panel/firmware/authority/profile/key lineage changed"
            )
        profile = _profile_record(expected["action_key"], action.production)
        records.append(
            {
                "bundle": action.bundle,
                "production": action.production,
                "validated": validated,
                "profile": profile,
                "observation": _derived_observation(
                    context, action.bundle, validated, action.production
                ),
            }
        )
        prior_profiles.append(action.production)

    usage_chain = _validate_global_usage_chain(records)
    uniqueness = _uniqueness(records)
    observations = [record["observation"] for record in records]
    comparability = descriptive._comparability(observations)
    if not comparability["comparable"]:
        raise N8PhysicalAnalysisError(
            "fixed measurement assets or unique camera evidence are not comparable"
        )
    summaries = _sequence_summaries(context, observations)
    all_continuity_pass = all(item["continuity_pass"] for item in observations)
    warm_observations = [
        item
        for item in observations
        if item["sequence_id"]
        == next(
            row["sequence_id"]
            for row in rows
            if row["power_mode"] == "supervised_continuous"
        )
    ]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "physical_execution_contract_file_sha256": (
            physical.n8_physical_execution_contract_file_sha256(
                context.contract
            )
        ),
        "physical_campaign_canonical_sha256": context.contract[
            "p0_campaign_canonical_sha256"
        ],
        "panel": _snapshot(context.physical_campaign["panel"]),
        "firmware": _snapshot(context.physical_campaign["firmware"]),
        "binding_review_artifact_sha256": context.contract[
            "binding_review_artifact"
        ]["sha256"],
        "expected_action_count": 15,
        "verified_action_count": 15,
        "expected_sequence_count": 5,
        "verified_sequence_count": 5,
        "all_actions_pass": True,
        "analysis_ready": True,
        "production_static_lineage": lineage,
        "production_profile_records": [
            record["profile"] for record in records
        ],
        "global_usage_chain": usage_chain,
        "uniqueness": uniqueness,
        "action_bindings": [
            {
                "action_key": record["validated"]["action_key"],
                "action_identity_sha256": record["validated"][
                    "action_identity_sha256"
                ],
                "sequence_id": record["validated"]["sequence_id"],
                "ordinal": record["validated"]["ordinal"],
                "bundle_file_sha256": _sha256(record["bundle"]),
                "claim_file_sha256": record["validated"][
                    "claim_file_sha256"
                ],
                "result_file_sha256": record["validated"][
                    "result_file_sha256"
                ],
                "finalization_file_sha256": record["validated"][
                    "finalization_file_sha256"
                ],
                "profile_file_sha256": record["profile"][
                    "profile_file_sha256"
                ],
                "execution_evidence_verified": True,
            }
            for record in records
        ],
        "sequence_summaries": summaries,
        "overall_metric_summaries": descriptive._metric_summaries(
            observations
        ),
        "measurement_comparability": comparability,
        "continuity_summary": {
            "all_action_continuity_pass": all_continuity_pass,
            "warm_dynamic_baseline_action_keys": [
                item["action_key"] for item in warm_observations
            ],
            "warm_dynamic_baseline_chain_verified": len(warm_observations) == 5,
            "esp32_no_restart_continuity_verified": all(
                item["ordinal"] == 1
                or (
                    item["continuity"] is not None
                    and item["continuity"][
                        "controller_reboot_between_actions"
                    ]
                    is False
                )
                for item in observations
            ),
            "qualification_state": "NOT_QUALIFIED",
        },
        "temperature_bin_sessions": {
            sequence_id: {
                "temperature_bin_id": summary["temperature_bin_id"],
                "session_observation_count": 1,
                "population_inference_allowed": False,
            }
            for sequence_id, summary in summaries.items()
            if summary["temperature_bin_id"] is not None
        },
        "qualification_state": "NOT_QUALIFIED",
        "hardware_qualified": False,
        "algorithm_qualified": False,
        "inference_contract": {
            "descriptive_only": True,
            "population_inference_allowed": False,
            "causal_attribution_allowed": False,
            "p95_allowed_only_when_n_at_least_10": True,
            "p99_allowed_only_when_n_at_least_10": True,
            "visual_qualification_allowed": False,
            "electrical_qualification_allowed": False,
            "hardware_qualification_allowed": False,
        },
        "classification": {
            "offline_analysis": True,
            "exact_15_directories_required_for_file_api": True,
            "source_physical_evidence_deep_validated": True,
            "actual_authority_usage_review_and_key_bytes_revalidated": True,
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
        raise N8PhysicalAnalysisError("physical N8 report must be an object")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise N8PhysicalAnalysisError("physical N8 report integrity is invalid")
    if (
        report.get("schema_version") != SCHEMA_VERSION
        or report.get("kind") != REPORT_KIND
        or report.get("expected_action_count") != 15
        or report.get("verified_action_count") != 15
        or report.get("expected_sequence_count") != 5
        or report.get("verified_sequence_count") != 5
        or report.get("qualification_state") != "NOT_QUALIFIED"
        or report.get("hardware_qualified") is not False
        or report.get("algorithm_qualified") is not False
        or report.get("inference_contract", {}).get(
            "hardware_qualification_allowed"
        )
        is not False
    ):
        raise N8PhysicalAnalysisError(
            "physical N8 completeness/qualification invariant changed"
        )


def analyze_n8_physical_actions(
    context: physical.N8PhysicalContext,
    *,
    actions: Sequence[N8PhysicalActionEvidence],
) -> dict[str, Any]:
    """Deep-validate and analyze exactly 15 ordered physical actions."""

    return _analyze(context, actions)


def validate_n8_physical_analysis_report(
    report: Mapping[str, Any],
    context: physical.N8PhysicalContext,
    *,
    actions: Sequence[N8PhysicalActionEvidence],
) -> Mapping[str, Any]:
    """Recompute the complete report and require exact canonical equality."""

    expected = _analyze(context, actions)
    if report != expected:
        raise N8PhysicalAnalysisError(
            "physical N8 report differs from replayed deep evidence"
        )
    return report


def analyze_n8_physical_result_directories(
    *,
    plan_files: runner.N8PhysicalPlanFiles,
    reviewer_key_file: Path,
    result_directories: Sequence[Path],
) -> dict[str, Any]:
    """Reload exactly 15 stored directories and all deep production bytes."""

    if len(result_directories) != 15:
        raise N8PhysicalAnalysisError(
            "physical N8 file analysis requires exactly fifteen directories"
        )
    resolved: list[Path] = []
    for index, directory in enumerate(result_directories, start=1):
        if (
            not isinstance(directory, Path)
            or not directory.is_dir()
            or directory.is_symlink()
        ):
            raise N8PhysicalAnalysisError(
                f"physical N8 result directory {index} is invalid"
            )
        resolved.append(directory.resolve(strict=True))
    if len(set(resolved)) != 15:
        raise N8PhysicalAnalysisError(
            "physical N8 result directories contain a duplicate/replay"
        )
    try:
        context = physical.load_n8_physical_execution_context(
            contract_file=plan_files.contract,
            physical_campaign_file=plan_files.physical_campaign,
            binding_review_artifact_file=plan_files.binding_review_artifact,
            minimum_interval_seconds=plan_files.minimum_interval_seconds,
            planned_cooldown_seconds=plan_files.planned_cooldown_seconds,
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalAnalysisError(str(error)) from error

    actions: list[N8PhysicalActionEvidence] = []
    sequence_result_files: list[Path] = []
    previous_sequence: Optional[str] = None
    for index, (row, directory) in enumerate(
        zip(context.contract["fixed_actions"], resolved), start=1
    ):
        if row["sequence_id"] != previous_sequence:
            sequence_result_files = []
            previous_sequence = row["sequence_id"]
        result_file = directory / runner.P0_RESULT_FILENAME
        try:
            chain = runner.load_n8_physical_finalized_action_chain(
                result_file,
                reviewer_key_file=reviewer_key_file,
                prior_result_files=tuple(sequence_result_files),
            )
        except runner.N8PhysicalActionError as error:
            raise N8PhysicalAnalysisError(
                f"stored physical N8 directory {index} failed replay: {error}"
            ) from error
        if (
            chain.context.contract != context.contract
            or chain.validated["action_key"] != row["action_key"]
        ):
            raise N8PhysicalAnalysisError(
                f"stored physical N8 directory {index} is cross-contract/reordered"
            )
        actions.append(
            N8PhysicalActionEvidence(
                bundle=chain.bundle,
                production=chain.production,
            )
        )
        sequence_result_files.append(result_file)
    return analyze_n8_physical_actions(context, actions=actions)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-contract", type=Path, required=True)
    parser.add_argument("--physical-campaign", type=Path, required=True)
    parser.add_argument("--binding-review-artifact", type=Path, required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)
    parser.add_argument(
        "--result-directory", type=Path, action="append", required=True
    )
    args = parser.parse_args(argv)
    if len(args.result_directory) != 15:
        parser.error("exactly fifteen --result-directory values are required")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze_n8_physical_result_directories(
            plan_files=runner.N8PhysicalPlanFiles(
                contract=args.physical_contract,
                physical_campaign=args.physical_campaign,
                binding_review_artifact=args.binding_review_artifact,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
            ),
            reviewer_key_file=args.reviewer_key,
            result_directories=args.result_directory,
        )
    except (N8PhysicalAnalysisError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N8PhysicalActionEvidence",
    "N8PhysicalAnalysisError",
    "REPORT_KIND",
    "analyze_n8_physical_actions",
    "analyze_n8_physical_result_directories",
    "main",
    "parse_args",
    "validate_n8_physical_analysis_report",
]
