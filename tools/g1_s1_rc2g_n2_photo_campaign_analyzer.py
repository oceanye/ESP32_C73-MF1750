#!/usr/bin/env python3
"""Offline analyzer for the four finalized N2P primer/target result pairs.

The analyzer performs no device, network, claim, authorization, or firmware
I/O.  It independently re-binds each finalized directory to the frozen N2P
compiler, P0 action, consumed workspace claim, reviewed profile, protocol
evidence, observation, and terminal result.  It then applies one frozen
six-dimension ranking rule.  Equal top totals are a tie and never produce an
arbitrary winner.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
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
    ResultState,
    canonical_json_bytes,
    describe_action_offline,
    result_file_sha256,
    validate_limit_profile,
    validate_result_record,
)
from tools import g1_s1_rc2g_n2_photo_campaign_once as fixed  # noqa: E402
from tools.g1_s1_rc2g_n2_photo_campaign import (  # noqa: E402
    compile_campaign_manifest,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
ANALYSIS_KIND = "mf1750-g1-s1-rc2g-n2p-four-cell-analysis"
ANALYSIS_HASH_SCOPE = (
    "entire analysis excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
EXPECTED_RESULT_KEYS = tuple(
    f"q{cell}-{phase}"
    for cell in range(1, 5)
    for phase in ("map-primer", "target")
)
SCORE_DIMENSIONS = (
    "detail",
    "tone",
    "gradients",
    "texture",
    "artifacts",
    "source_fidelity",
)

ANALYZER_CONTRACT = {
    "schema_version": 1,
    "contract_id": "n2p-four-cell-offline-ranking-v1",
    "required_result_keys": list(EXPECTED_RESULT_KEYS),
    "required_terminal_chains": 8,
    "score_dimensions_in_frozen_order": list(SCORE_DIMENSIONS),
    "score_source": "finalized_manual_target_observation",
    "selection_scope": "exact_frozen_N2P_campaign_only",
    "observations_per_target_candidate": 1,
    "primary_sort": "six_dimension_integer_total_descending",
    "reported_secondary_statistic": "arithmetic_mean",
    "tie_policy": "equal_top_total_is_explicit_tie_no_selected_winner",
    "winner_gates": [
        "all_four_primer_chains_are_PASS_with_full_MAP_fidelity",
        "all_four_target_chains_are_PASS",
        "all_target_visual_electrical_and_post_temperature_gates_pass",
        "all_target_results_bind_their_same_cell_primer_result_file_sha256",
        "one_unique_highest_six_dimension_total",
    ],
    "camera_policy": {
        "not_required_for_single_action_or_manual_score_winner": True,
        "comparable_only_if_all_four_targets_have_verified_captures": True,
        "same_camera_and_fixed_settings_required": True,
        "missing_or_mismatched_capture_never_silently_claimed_comparable": True,
    },
    "visual_electrical_separation": True,
    "interpretation": {
        "algorithm_qualified": False,
        "population_inference": False,
        "selected_winner_use": "N3_branch_selection_only",
        "general_algorithm_superiority_claim": False,
    },
    "network_io": False,
    "claim_creation": False,
    "authorization_creation": False,
}
ANALYZER_CONTRACT_SHA256 = (
    "3638e26f80c8e0a9da81760c3ca3d177d7a43591a813f030446100ec87fb7a86"
)


class N2PCampaignAnalysisError(RuntimeError):
    """One result chain is missing, tampered, replayed, or inconsistent."""


@dataclass(frozen=True)
class _FinalizedBundle:
    key: str
    directory: Path
    snapshot: fixed._ActionSnapshot
    lock: Mapping[str, Any]
    profile: Mapping[str, Any]
    evidence: Mapping[str, Any]
    observation: Mapping[str, Any]
    finalization: Mapping[str, Any]
    result: Mapping[str, Any]
    result_file_sha256: str
    score_total: Optional[int]
    score_mean: Optional[float]
    camera_signature: Optional[tuple[Any, ...]]


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise N2PCampaignAnalysisError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if _sha256(_canonical(ANALYZER_CONTRACT)) != ANALYZER_CONTRACT_SHA256:
    raise RuntimeError("frozen N2P analyzer/ranking contract changed")


def _safe_result_directory(path: Path, *, label: str) -> Path:
    if not isinstance(path, Path):
        raise N2PCampaignAnalysisError(f"{label} must be pathlib.Path")
    try:
        require_local_regular_path_syntax(path, label=label)
        fixed._reject_reparse_path_chain(path, label=label)
        resolved = path.resolve(strict=True)
        require_local_regular_path_syntax(resolved, label=f"resolved {label}")
    except (LocalPathSafetyError, fixed.N2PFixedActionError, OSError) as error:
        raise N2PCampaignAnalysisError(f"{label} is unsafe or unavailable: {error}") from error
    if resolved.is_symlink() or not resolved.is_dir():
        raise N2PCampaignAnalysisError(f"{label} must resolve to a regular local directory")
    return resolved


def _read(directory: Path, filename: str, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        return fixed._strict_json_file(directory / filename, label=label)
    except fixed.N2PFixedActionError as error:
        raise N2PCampaignAnalysisError(str(error)) from error


def _stored_observation_input(observation: Mapping[str, Any]) -> dict[str, Any]:
    added = {
        "visual_pass",
        "electrical_pass",
        "post_refresh_temperature_pass",
        "overall_state",
        "scoring_contract_sha256",
        "camera_observation_contract_sha256",
        "source_observation_file_sha256",
        "verified_camera_evidence",
    }
    if not added.issubset(observation):
        raise N2PCampaignAnalysisError("stored observation finalizer fields are incomplete")
    raw = {key: value for key, value in observation.items() if key not in added}
    return raw


def _camera_signature(
    directory: Path,
    raw_observation: Mapping[str, Any],
    stored_observation: Mapping[str, Any],
    finalization: Mapping[str, Any],
) -> Optional[tuple[Any, ...]]:
    camera = raw_observation["camera"]
    if camera["capture_performed"] is not True:
        if (
            stored_observation["verified_camera_evidence"] is not None
            or finalization.get("camera_capture_present_for_this_action") is not False
            or finalization.get("camera_capture_file_sha256") is not None
            or os.path.lexists(directory / fixed.CAMERA_CAPTURE_FILENAME)
        ):
            raise N2PCampaignAnalysisError("uncaptured target gained camera evidence")
        return None
    binding = stored_observation["verified_camera_evidence"]
    if not isinstance(binding, Mapping):
        raise N2PCampaignAnalysisError("captured target lacks verified camera binding")
    try:
        capture = fixed._safe_regular_file(
            directory / fixed.CAMERA_CAPTURE_FILENAME,
            label="copied N2P camera evidence",
        )
        payload = capture.read_bytes()
    except (fixed.N2PFixedActionError, OSError) as error:
        raise N2PCampaignAnalysisError(f"camera evidence is unavailable: {error}") from error
    sha = _sha256(payload)
    if (
        binding.get("copied_file") != fixed.CAMERA_CAPTURE_FILENAME
        or binding.get("bytes") != len(payload)
        or binding.get("sha256") != sha
        or camera.get("sha256") != sha
        or finalization.get("camera_capture_present_for_this_action") is not True
        or finalization.get("camera_capture_file_sha256") != sha
    ):
        raise N2PCampaignAnalysisError("camera evidence byte/finalization binding changed")
    return (
        camera["camera_id"],
        camera["tripod_position_id"],
        camera["lighting_setup_id"],
        camera["exposure_mode"],
        camera["white_balance_mode"],
        camera["focus_mode"],
        camera["image_processing"],
        binding.get("decoded_format"),
        binding.get("width"),
        binding.get("height"),
    )


def _load_finalized_bundle(
    key: str,
    path: Path,
    snapshot: fixed._ActionSnapshot,
    *,
    primer: Optional[_FinalizedBundle],
) -> _FinalizedBundle:
    directory = _safe_result_directory(path, label=f"{key} result directory")
    lock, _lock_payload = _read(
        directory, fixed.LOCK_FILENAME, label=f"{key} attempt lock"
    )
    profile, profile_payload = _read(
        directory, fixed.PROFILE_FILENAME, label=f"{key} reviewed limit profile"
    )
    evidence, evidence_payload = _read(
        directory, fixed.EVIDENCE_FILENAME, label=f"{key} protocol evidence"
    )
    observation, observation_payload = _read(
        directory, fixed.OBSERVATION_FILENAME, label=f"{key} observation"
    )
    finalization, finalization_payload = _read(
        directory, fixed.FINALIZATION_FILENAME, label=f"{key} finalization"
    )
    result, result_payload = _read(
        directory, fixed.P0_RESULT_FILENAME, label=f"{key} P0 result"
    )
    try:
        validate_limit_profile(profile)
        validate_result_record(result)
    except CampaignContractError as error:
        raise N2PCampaignAnalysisError(f"{key} P0/profile validation failed: {error}") from error
    action_sha = snapshot.action["action_identity_sha256"]
    actual_result_sha = _sha256(result_payload)
    if result_file_sha256(result) != actual_result_sha:
        raise N2PCampaignAnalysisError(f"{key} result whole-file identity changed")
    if (
        evidence.get("kind") != fixed.EVIDENCE_KIND
        or evidence.get("action_key") != key
        or evidence.get("cell_id") != snapshot.cell_id
        or evidence.get("phase") != snapshot.phase
        or evidence.get("action_identity_sha256") != action_sha
        or evidence.get("campaign_canonical_sha256")
        != fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or evidence.get("p0_campaign_canonical_sha256")
        != fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
        or evidence.get("execution_supplement_file_sha256")
        != fixed.EXECUTION_SUPPLEMENT_FILE_SHA256
        or evidence.get("frame_sha256")
        != snapshot.action["identity"]["frame"]["sha256"]
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("request_audit", {}).get("post_attempt_count") != 1
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("maximum_post_requests") != 1
        or evidence.get("automatic_retry_count") != 0
        or evidence.get("retry_allowed") is not False
        or evidence.get("recovery_performed") is not False
    ):
        raise N2PCampaignAnalysisError(f"{key} protocol/action binding is invalid")
    protocol = evidence.get("protocol_evidence")
    if not isinstance(protocol, Mapping):
        raise N2PCampaignAnalysisError(f"{key} protocol evidence is missing")
    if snapshot.phase == "map-primer":
        completed = protocol.get("completed_map_evidence")
        if (
            set(protocol) != {"fresh_boot_preflight", "completed_map_evidence"}
            or not isinstance(completed, Mapping)
            or completed.get("job_raw", {}).get("job_id") != 1
            or completed.get("diagnostic_raw", {}).get("operation_id") != 1
        ):
            raise N2PCampaignAnalysisError(f"{key} is not the frozen job1/op1 MAP proof")
    else:
        if primer is None:
            raise N2PCampaignAnalysisError(f"{key} target lacks its same-cell primer")
        if (
            evidence.get("prior_result_file_sha256") != primer.result_file_sha256
            or not {
                "same_cell_primer_live_preflight",
                "network_report",
                "target_job_raw",
                "target_diagnostic_raw",
                "target_diagnostic_validated",
                "post_refresh_gpio_status_raw",
            }.issubset(protocol)
            or protocol.get("target_job_raw", {}).get("job_id") != 2
            or protocol.get("target_diagnostic_raw", {}).get("operation_id") != 2
        ):
            raise N2PCampaignAnalysisError(f"{key} target/prior job2-op2 binding is invalid")
    try:
        claim_record = fixed._validate_consumed_claim_reference(
            action_sha, evidence.get("claim")
        )
    except fixed.N2PFixedActionError as error:
        raise N2PCampaignAnalysisError(f"{key} consumed claim is invalid: {error}") from error
    if (
        claim_record.get("action_key") != key
        or claim_record.get("campaign_canonical_sha256")
        != fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or claim_record.get("p0_campaign_canonical_sha256")
        != fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
        or claim_record.get("execution_supplement_file_sha256")
        != fixed.EXECUTION_SUPPLEMENT_FILE_SHA256
        or claim_record.get("profile_canonical_sha256")
        != evidence.get("profile_canonical_sha256")
        or claim_record.get("profile_file_sha256")
        != evidence.get("profile_file_sha256")
        or claim_record.get("prior_result_file_sha256")
        != evidence.get("prior_result_file_sha256")
        or claim_record.get("attempt_id") != evidence.get("attempt_id")
        or claim_record.get("maximum_post_requests") != 1
        or claim_record.get("automatic_retry_authorized") is not False
        or claim_record.get("automatic_recovery_authorized") is not False
    ):
        raise N2PCampaignAnalysisError(f"{key} consumed claim payload binding changed")
    if (
        lock.get("kind") != fixed.LOCK_KIND
        or lock.get("action_key") != key
        or lock.get("action_identity_sha256") != action_sha
        or lock.get("claim") != evidence.get("claim")
        or lock.get("attempt_id") != evidence.get("attempt_id")
        or lock.get("state") != "authorization_permanently_consumed_do_not_rerun"
        or lock.get("automatic_retry_authorized") is not False
        or lock.get("automatic_recovery_authorized") is not False
    ):
        raise N2PCampaignAnalysisError(f"{key} attempt lock binding changed")
    if (
        evidence.get("profile_file_sha256") != _sha256(profile_payload)
        or evidence.get("profile_canonical_sha256")
        != profile["integrity"]["canonical_sha256"]
        or evidence.get("reference_preview") != snapshot.reference_preview
        or evidence.get("scoring_contract_sha256")
        != fixed.SCORING_CONTRACT_SHA256
        or evidence.get("camera_observation_contract_sha256")
        != fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
    ):
        raise N2PCampaignAnalysisError(f"{key} reviewed profile binding changed")
    try:
        p0_description = describe_action_offline(
            snapshot.campaign,
            action_identity_sha256=action_sha,
            limit_profile=profile,
            evaluated_at=str(evidence["profile_evaluated_at"]),
            prior_result=primer.result if primer else None,
            prior_result_sha256=primer.result_file_sha256 if primer else None,
        )
    except (CampaignContractError, KeyError) as error:
        raise N2PCampaignAnalysisError(f"{key} historical P0 decision is invalid: {error}") from error
    if p0_description["contract_ready"] is not True:
        raise N2PCampaignAnalysisError(
            f"{key} historical reviewed limit/prior gates were not ready"
        )
    if (
        finalization.get("kind") != fixed.FINALIZATION_KIND
        or finalization.get("action_key") != key
        or finalization.get("action_identity_sha256") != action_sha
        or finalization.get("protocol_evidence_file_sha256")
        != _sha256(evidence_payload)
        or finalization.get("observation_file_sha256")
        != _sha256(observation_payload)
        or finalization.get("profile_file_sha256") != _sha256(profile_payload)
        or finalization.get("scoring_contract_sha256")
        != fixed.SCORING_CONTRACT_SHA256
        or finalization.get("camera_observation_contract_sha256")
        != fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
        or finalization.get("visual_and_electrical_assessed_separately") is not True
        or finalization.get("post_refresh_temperature_c")
        != observation.get("post_refresh_temperature_c")
        or finalization.get("cross_candidate_camera_comparability")
        != (
            "not_established_by_single_action; requires verified fixed-camera "
            "captures for all four N2P targets"
        )
    ):
        raise N2PCampaignAnalysisError(f"{key} finalization hash/contract changed")
    if (
        result["action_identity_sha256"] != action_sha
        or result["state"] != finalization.get("state")
        or result["evidence_manifest_sha256"] != _sha256(finalization_payload)
        or result["post_request_count"] != 1
        or result["completed_at"] != observation.get("observed_at")
    ):
        raise N2PCampaignAnalysisError(f"{key} terminal result binding changed")
    try:
        protocol_completed_at = fixed._rfc3339(
            evidence.get("protocol_completed_at"), label=f"{key} protocol_completed_at"
        )
        raw_observation = _stored_observation_input(observation)
        raw_for_validation = dict(raw_observation)
        raw_for_validation["camera"] = dict(raw_observation["camera"])
        if raw_for_validation["camera"]["capture_performed"] is True:
            raw_for_validation["camera"]["file"] = fixed.CAMERA_CAPTURE_FILENAME
        validation = fixed._validate_observation(
            raw_for_validation,
            snapshot,
            profile,
            camera_base_directory=directory,
            minimum_observed_at=protocol_completed_at,
        )
    except (fixed.N2PFixedActionError, KeyError, TypeError) as error:
        raise N2PCampaignAnalysisError(f"{key} stored observation is invalid: {error}") from error
    visual_pass, electrical_pass, thermal_pass = validation[:3]
    expected_state = (
        ResultState.PASS.value
        if visual_pass and electrical_pass and thermal_pass
        else ResultState.FAIL.value
    )
    if (
        observation.get("visual_pass") is not visual_pass
        or observation.get("electrical_pass") is not electrical_pass
        or observation.get("post_refresh_temperature_pass") is not thermal_pass
        or observation.get("overall_state") != expected_state
        or observation.get("scoring_contract_sha256")
        != fixed.SCORING_CONTRACT_SHA256
        or observation.get("camera_observation_contract_sha256")
        != fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
        or finalization.get("visual_pass") is not visual_pass
        or finalization.get("electrical_pass") is not electrical_pass
        or finalization.get("post_refresh_temperature_pass") is not thermal_pass
        or finalization.get("state") != expected_state
    ):
        raise N2PCampaignAnalysisError(f"{key} recomputed verdict differs from finalization")
    camera_signature = _camera_signature(
        directory, raw_observation, observation, finalization
    )
    score_total: Optional[int] = None
    score_mean: Optional[float] = None
    if snapshot.phase == "target":
        visual = raw_observation["visual"]
        scores = [visual[dimension] for dimension in SCORE_DIMENSIONS]
        score_total = sum(scores)
        score_mean = score_total / len(scores)
    return _FinalizedBundle(
        key=key,
        directory=directory,
        snapshot=snapshot,
        lock=lock,
        profile=profile,
        evidence=evidence,
        observation=observation,
        finalization=finalization,
        result=result,
        result_file_sha256=actual_result_sha,
        score_total=score_total,
        score_mean=score_mean,
        camera_signature=camera_signature,
    )


def analyze_n2p_campaign(
    result_directories: Mapping[str, Path],
) -> dict[str, Any]:
    """Deep-validate all eight chains and return one sealed offline analysis."""

    if not isinstance(result_directories, Mapping) or set(result_directories) != set(
        EXPECTED_RESULT_KEYS
    ):
        raise N2PCampaignAnalysisError(
            "result_directories must contain exactly the eight frozen action keys"
        )
    manifest = compile_campaign_manifest()
    snapshots = {
        key: fixed._load_action_snapshot(key, _validated_manifest=manifest)
        for key in EXPECTED_RESULT_KEYS
    }
    bundles: dict[str, _FinalizedBundle] = {}
    for cell in range(1, 5):
        primer_key = f"q{cell}-map-primer"
        target_key = f"q{cell}-target"
        primer = _load_finalized_bundle(
            primer_key,
            result_directories[primer_key],
            snapshots[primer_key],
            primer=None,
        )
        target = _load_finalized_bundle(
            target_key,
            result_directories[target_key],
            snapshots[target_key],
            primer=primer,
        )
        bundles[primer_key] = primer
        bundles[target_key] = target
    directories = [bundle.directory for bundle in bundles.values()]
    result_shas = [bundle.result_file_sha256 for bundle in bundles.values()]
    attempts = [str(bundle.evidence.get("attempt_id")) for bundle in bundles.values()]
    if (
        len(set(directories)) != 8
        or len(set(result_shas)) != 8
        or len(set(attempts)) != 8
    ):
        raise N2PCampaignAnalysisError(
            "result directory/result/attempt replay detected across frozen actions"
        )

    targets = [bundles[f"q{cell}-target"] for cell in range(1, 5)]
    scorecard = []
    for target in targets:
        visual = target.observation["visual"]
        assert target.score_total is not None and target.score_mean is not None
        scorecard.append(
            {
                "cell_id": target.snapshot.cell_id,
                "action_key": target.key,
                "action_identity_sha256": target.snapshot.action[
                    "action_identity_sha256"
                ],
                "algorithm": target.snapshot.cell["algorithm"],
                "frame_sha256": target.snapshot.action["identity"]["frame"][
                    "sha256"
                ],
                "target_result_file_sha256": target.result_file_sha256,
                "scores": {dimension: visual[dimension] for dimension in SCORE_DIMENSIONS},
                "score_total": target.score_total,
                "score_mean": target.score_mean,
                "visual_pass": target.observation["visual_pass"],
                "electrical_pass": target.observation["electrical_pass"],
                "post_refresh_temperature_pass": target.observation[
                    "post_refresh_temperature_pass"
                ],
                "camera_capture_verified": target.camera_signature is not None,
            }
        )
    totals = sorted({int(row["score_total"]) for row in scorecard}, reverse=True)
    rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
    ranking = sorted(
        (
            {
                "rank": rank_by_total[int(row["score_total"])],
                **row,
            }
            for row in scorecard
        ),
        key=lambda row: (row["rank"], row["cell_id"]),
    )
    highest = totals[0]
    top = [row for row in ranking if row["score_total"] == highest]
    top_tie = len(top) != 1

    primer_pass = all(
        bundles[f"q{cell}-map-primer"].result["state"] == ResultState.PASS.value
        and bundles[f"q{cell}-map-primer"].observation["visual_pass"] is True
        for cell in range(1, 5)
    )
    targets_pass = all(
        target.result["state"] == ResultState.PASS.value for target in targets
    )
    separated_gates_pass = all(
        target.observation["visual_pass"] is True
        and target.observation["electrical_pass"] is True
        and target.observation["post_refresh_temperature_pass"] is True
        for target in targets
    )
    winner_gates_pass = primer_pass and targets_pass and separated_gates_pass and not top_tie

    signatures = [target.camera_signature for target in targets]
    all_captured = all(signature is not None for signature in signatures)
    same_signature = all_captured and len(set(signatures)) == 1
    camera_comparable = bool(all_captured and same_signature)
    camera_reasons = []
    if not all_captured:
        camera_reasons.append("verified_target_capture_missing")
    elif not same_signature:
        camera_reasons.append("camera_or_fixed_settings_differ_across_targets")

    selected_winner: Optional[dict[str, Any]] = None
    if winner_gates_pass:
        winner = top[0]
        selected_winner = {
            "cell_id": winner["cell_id"],
            "algorithm": winner["algorithm"],
            "action_key": winner["action_key"],
            "action_identity_sha256": winner["action_identity_sha256"],
            "frame_sha256": winner["frame_sha256"],
            "target_result_file_sha256": winner["target_result_file_sha256"],
            "score_total": winner["score_total"],
            "score_mean": winner["score_mean"],
            "selection_basis": "unique_highest_preregistered_six_dimension_total",
            "authorized_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
        }
        selected_winner["winner_identity_sha256"] = _sha256(
            _canonical(selected_winner)
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "mode": "offline-read-only-analysis",
        "analyzer_contract_sha256": ANALYZER_CONTRACT_SHA256,
        "selection_interpretation": {
            "selection_scope": "exact_frozen_N2P_campaign_only",
            "target_candidate_count": 4,
            "observations_per_target_candidate": 1,
            "score_type": "single_supervised_manual_observation",
            "selected_winner_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
            "general_algorithm_superiority_claim": False,
        },
        "classification": {
            "experimental": True,
            "formal": False,
            "algorithm_qualified": False,
            "population_inference": False,
            "scientific_algorithm_qualification_pass": False,
        },
        "source_campaign": {
            "outer_manifest_canonical_sha256": fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
            "outer_manifest_file_sha256": fixed.EXPECTED_CAMPAIGN_FILE_SHA256,
            "p0_campaign_canonical_sha256": fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
            "execution_supplement_file_sha256": fixed.EXECUTION_SUPPLEMENT_FILE_SHA256,
            "scoring_contract_sha256": fixed.SCORING_CONTRACT_SHA256,
            "camera_observation_contract_sha256": (
                fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
            ),
        },
        "validated_chains": [
            {
                "action_key": key,
                "cell_id": bundles[key].snapshot.cell_id,
                "phase": bundles[key].snapshot.phase,
                "action_identity_sha256": bundles[key].snapshot.action[
                    "action_identity_sha256"
                ],
                "result_file_sha256": bundles[key].result_file_sha256,
                "state": bundles[key].result["state"],
                "visual_pass": bundles[key].observation["visual_pass"],
                "electrical_pass": bundles[key].observation["electrical_pass"],
                "post_refresh_temperature_pass": bundles[key].observation[
                    "post_refresh_temperature_pass"
                ],
            }
            for key in EXPECTED_RESULT_KEYS
        ],
        "scorecard": scorecard,
        "ranking": ranking,
        "tie_state": {
            "top_score_total": highest,
            "top_tie": top_tie,
            "top_tied_cell_ids": [row["cell_id"] for row in top],
            "arbitrary_tie_break_performed": False,
        },
        "camera_comparability": {
            "comparable": camera_comparable,
            "verified_target_capture_count": sum(
                signature is not None for signature in signatures
            ),
            "same_camera_and_fixed_settings": bool(same_signature),
            "reasons": camera_reasons,
            "affects_manual_score_winner": False,
        },
        "winner_gates": {
            "all_primer_map_pass": primer_pass,
            "all_target_results_pass": targets_pass,
            "visual_electrical_temperature_gates_pass": separated_gates_pass,
            "unique_top_total": not top_tie,
            "all_pass": winner_gates_pass,
        },
        "selected_winner": selected_winner,
        "hardware_io_performed": False,
        "network_io_performed": False,
        "claim_created": False,
        "authorization_created": False,
    }
    analysis = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(_canonical(unsigned)),
            "canonical_sha256_scope": ANALYSIS_HASH_SCOPE,
        },
    }
    validate_n2p_analysis(analysis)
    return analysis


def validate_n2p_analysis(analysis: Mapping[str, Any]) -> Mapping[str, Any]:
    """Independently validate a sealed analyzer output without result I/O."""

    expected_keys = {
        "schema_version",
        "kind",
        "mode",
        "analyzer_contract_sha256",
        "selection_interpretation",
        "classification",
        "source_campaign",
        "validated_chains",
        "scorecard",
        "ranking",
        "tie_state",
        "camera_comparability",
        "winner_gates",
        "selected_winner",
        "hardware_io_performed",
        "network_io_performed",
        "claim_created",
        "authorization_created",
        "integrity",
    }
    if not isinstance(analysis, Mapping) or set(analysis) != expected_keys:
        raise N2PCampaignAnalysisError("analysis fields differ from the frozen contract")
    unsigned = dict(analysis)
    integrity = unsigned.pop("integrity")
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("canonical_sha256") != _sha256(_canonical(unsigned))
        or integrity.get("canonical_sha256_scope") != ANALYSIS_HASH_SCOPE
    ):
        raise N2PCampaignAnalysisError("analysis canonical integrity is invalid")
    expected_interpretation = {
        "selection_scope": "exact_frozen_N2P_campaign_only",
        "target_candidate_count": 4,
        "observations_per_target_candidate": 1,
        "score_type": "single_supervised_manual_observation",
        "selected_winner_use": "N3_branch_selection_only",
        "algorithm_qualified": False,
        "population_inference": False,
        "general_algorithm_superiority_claim": False,
    }
    expected_classification = {
        "experimental": True,
        "formal": False,
        "algorithm_qualified": False,
        "population_inference": False,
        "scientific_algorithm_qualification_pass": False,
    }
    expected_source = {
        "outer_manifest_canonical_sha256": fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "outer_manifest_file_sha256": fixed.EXPECTED_CAMPAIGN_FILE_SHA256,
        "p0_campaign_canonical_sha256": fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
        "execution_supplement_file_sha256": fixed.EXECUTION_SUPPLEMENT_FILE_SHA256,
        "scoring_contract_sha256": fixed.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
    }
    if (
        analysis["schema_version"] != SCHEMA_VERSION
        or analysis["kind"] != ANALYSIS_KIND
        or analysis["mode"] != "offline-read-only-analysis"
        or analysis["analyzer_contract_sha256"] != ANALYZER_CONTRACT_SHA256
        or analysis["selection_interpretation"] != expected_interpretation
        or analysis["classification"] != expected_classification
        or analysis["source_campaign"] != expected_source
        or any(
            analysis[field] is not False
            for field in (
                "hardware_io_performed",
                "network_io_performed",
                "claim_created",
                "authorization_created",
            )
        )
    ):
        raise N2PCampaignAnalysisError("analysis identity/classification changed")
    chains = analysis["validated_chains"]
    if not isinstance(chains, list) or len(chains) != 8:
        raise N2PCampaignAnalysisError("analysis must contain eight validated chains")
    chain_by_key: dict[str, Mapping[str, Any]] = {}
    for expected_key, chain in zip(EXPECTED_RESULT_KEYS, chains):
        if (
            not isinstance(chain, Mapping)
            or set(chain)
            != {
                "action_key",
                "cell_id",
                "phase",
                "action_identity_sha256",
                "result_file_sha256",
                "state",
                "visual_pass",
                "electrical_pass",
                "post_refresh_temperature_pass",
            }
            or chain.get("action_key") != expected_key
            or chain.get("cell_id") != expected_key[:2].upper()
            or chain.get("phase")
            != ("map-primer" if expected_key.endswith("map-primer") else "target")
            or chain.get("action_identity_sha256")
            != fixed.FIXED_ACTION_SHA256S[expected_key]
            or chain.get("state") not in {ResultState.PASS.value, ResultState.FAIL.value}
            or any(
                type(chain.get(field)) is not bool
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "post_refresh_temperature_pass",
                )
            )
        ):
            raise N2PCampaignAnalysisError("validated chain identity/verdict changed")
        result_sha = chain.get("result_file_sha256")
        if (
            not isinstance(result_sha, str)
            or len(result_sha) != 64
            or any(character not in "0123456789abcdef" for character in result_sha)
        ):
            raise N2PCampaignAnalysisError("validated chain result SHA-256 is invalid")
        chain_by_key[expected_key] = chain
    if len({chain["result_file_sha256"] for chain in chains}) != 8:
        raise N2PCampaignAnalysisError("validated result replay appears in analysis")
    scorecard = analysis["scorecard"]
    if not isinstance(scorecard, list) or len(scorecard) != 4:
        raise N2PCampaignAnalysisError("analysis scorecard must contain four targets")
    normalized_rows: list[dict[str, Any]] = []
    for cell, row in enumerate(scorecard, start=1):
        key = f"q{cell}-target"
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "cell_id",
                "action_key",
                "action_identity_sha256",
                "algorithm",
                "frame_sha256",
                "target_result_file_sha256",
                "scores",
                "score_total",
                "score_mean",
                "visual_pass",
                "electrical_pass",
                "post_refresh_temperature_pass",
                "camera_capture_verified",
            }
            or row.get("cell_id") != f"Q{cell}"
            or row.get("action_key") != key
            or row.get("action_identity_sha256") != fixed.FIXED_ACTION_SHA256S[key]
            or row.get("target_result_file_sha256")
            != chain_by_key[key]["result_file_sha256"]
            or not isinstance(row.get("algorithm"), str)
            or not row.get("algorithm")
            or any(
                type(row.get(field)) is not bool
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "post_refresh_temperature_pass",
                    "camera_capture_verified",
                )
            )
        ):
            raise N2PCampaignAnalysisError("scorecard target identity changed")
        scores = row.get("scores")
        if not isinstance(scores, Mapping) or list(scores) != list(SCORE_DIMENSIONS):
            raise N2PCampaignAnalysisError("scorecard dimensions/order changed")
        values = list(scores.values())
        if any(type(score) is not int or not 1 <= score <= 5 for score in values):
            raise N2PCampaignAnalysisError("scorecard values must be integer 1..5")
        total = sum(values)
        if row.get("score_total") != total or row.get("score_mean") != total / 6:
            raise N2PCampaignAnalysisError("scorecard total/mean changed")
        normalized_rows.append(dict(row))
    totals = sorted({int(row["score_total"]) for row in normalized_rows}, reverse=True)
    rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
    expected_ranking = sorted(
        (
            {"rank": rank_by_total[int(row["score_total"])], **row}
            for row in normalized_rows
        ),
        key=lambda row: (row["rank"], row["cell_id"]),
    )
    if analysis["ranking"] != expected_ranking:
        raise N2PCampaignAnalysisError("analysis ranking is not the frozen total rule")
    highest = totals[0]
    top = [row for row in expected_ranking if row["score_total"] == highest]
    top_tie = len(top) != 1
    expected_tie = {
        "top_score_total": highest,
        "top_tie": top_tie,
        "top_tied_cell_ids": [row["cell_id"] for row in top],
        "arbitrary_tie_break_performed": False,
    }
    if analysis["tie_state"] != expected_tie:
        raise N2PCampaignAnalysisError("analysis tie state changed")
    primer_pass = all(
        chain_by_key[f"q{cell}-map-primer"]["state"] == ResultState.PASS.value
        and chain_by_key[f"q{cell}-map-primer"]["visual_pass"] is True
        for cell in range(1, 5)
    )
    targets_pass = all(
        chain_by_key[f"q{cell}-target"]["state"] == ResultState.PASS.value
        for cell in range(1, 5)
    )
    separated = all(
        row["visual_pass"] is True
        and row["electrical_pass"] is True
        and row["post_refresh_temperature_pass"] is True
        for row in normalized_rows
    )
    gates = {
        "all_primer_map_pass": primer_pass,
        "all_target_results_pass": targets_pass,
        "visual_electrical_temperature_gates_pass": separated,
        "unique_top_total": not top_tie,
        "all_pass": primer_pass and targets_pass and separated and not top_tie,
    }
    if analysis["winner_gates"] != gates:
        raise N2PCampaignAnalysisError("analysis winner gates changed")
    camera = analysis["camera_comparability"]
    captured = sum(row["camera_capture_verified"] is True for row in normalized_rows)
    if (
        not isinstance(camera, Mapping)
        or camera.get("verified_target_capture_count") != captured
        or camera.get("affects_manual_score_winner") is not False
        or type(camera.get("comparable")) is not bool
        or type(camera.get("same_camera_and_fixed_settings")) is not bool
        or not isinstance(camera.get("reasons"), list)
        or (camera["comparable"] and (captured != 4 or not camera["same_camera_and_fixed_settings"]))
    ):
        raise N2PCampaignAnalysisError("analysis camera-comparability claim changed")
    winner = analysis["selected_winner"]
    if not gates["all_pass"]:
        if winner is not None:
            raise N2PCampaignAnalysisError("analysis selected a winner while gates failed")
    else:
        expected_row = top[0]
        expected_winner = {
            "cell_id": expected_row["cell_id"],
            "algorithm": expected_row["algorithm"],
            "action_key": expected_row["action_key"],
            "action_identity_sha256": expected_row["action_identity_sha256"],
            "frame_sha256": expected_row["frame_sha256"],
            "target_result_file_sha256": expected_row[
                "target_result_file_sha256"
            ],
            "score_total": expected_row["score_total"],
            "score_mean": expected_row["score_mean"],
            "selection_basis": "unique_highest_preregistered_six_dimension_total",
            "authorized_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
        }
        expected_winner["winner_identity_sha256"] = _sha256(
            _canonical(expected_winner)
        )
        if winner != expected_winner:
            raise N2PCampaignAnalysisError("selected N3 branch identity changed")
    return analysis


def write_n2p_analysis(
    result_directories: Mapping[str, Path], output_file: Path
) -> Mapping[str, Any]:
    analysis = analyze_n2p_campaign(result_directories)
    if not isinstance(output_file, Path):
        raise N2PCampaignAnalysisError("output_file must be pathlib.Path")
    try:
        require_local_regular_path_syntax(output_file, label="N2P analysis output")
        if os.path.lexists(output_file):
            raise N2PCampaignAnalysisError("analysis output already exists")
        fixed._reject_reparse_path_chain(
            output_file.parent, label="N2P analysis output parent"
        )
        parent = output_file.parent.resolve(strict=True)
    except N2PCampaignAnalysisError:
        raise
    except (LocalPathSafetyError, fixed.N2PFixedActionError, OSError) as error:
        raise N2PCampaignAnalysisError(f"analysis output path is unsafe: {error}") from error
    try:
        fixed._atomic_commit(
            parent / output_file.name,
            canonical_json_bytes(analysis),
            unknown_after_commit=False,
        )
    except fixed.N2PFixedActionError as error:
        raise N2PCampaignAnalysisError(str(error)) from error
    return analysis


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for key in EXPECTED_RESULT_KEYS:
        parser.add_argument(f"--{key}-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    directories = {
        key: getattr(args, key.replace("-", "_") + "_dir")
        for key in EXPECTED_RESULT_KEYS
    }
    try:
        analysis = (
            write_n2p_analysis(directories, args.output)
            if args.output is not None
            else analyze_n2p_campaign(directories)
        )
    except N2PCampaignAnalysisError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
