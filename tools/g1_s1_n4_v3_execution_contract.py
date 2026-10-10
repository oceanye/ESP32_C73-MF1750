#!/usr/bin/env python3
"""Frozen, zero-I/O execution envelope for the N4 V3 2x2 campaign.

The historical V3 compiler remains the only source of manifest, proof, frame,
action, and job identities.  This module makes one reviewed operational
change: the four session records are resealed with
``final_power_off_required=false``.  Nothing in an action identity changes.

This module has no HTTP client, device path, claim writer, authorization
generator, retry path, recovery path, or filesystem write path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from typing import Any, Mapping, Optional

from host.epd_frame import (
    ControllerMapping,
    controller_stream,
    fnv1a,
    generate_fixture,
    validate_frame,
)
from host.visible_refresh_campaign import (
    CLAIM_REGISTRY_ID,
    CampaignContractError,
    ResultState,
    build_session_contract,
    canonical_json_bytes,
    result_file_sha256,
    seal_campaign_contract,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
)
from tools import g1_s1_root_cause_2x2_v3 as v3
from tools import g1_s1_rc2g_map_baseline_once as _map
from tools import g1_s1_rc2g_quality_refresh_once as _quality
from tools.g1_s1_rc2g_n2_photo_campaign import FIRMWARE_CONTRACT, PANEL_CONTRACT


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-g1-s1-n4-v3-fixed-execution-contract"
CONTRACT_ID = "g1-s1-rc2g-n4-v3-fixed-execution-v1"
CAMPAIGN_ID = "n4-v3-selected-metric-2x2-v1"
RUNNER_KIND = "mf1750-g1-s1-rc2g-n4-v3-fixed-action-runner"
CLAIM_KIND = "mf1750-visible-refresh-fixed-action-consumed-claim"
LOCK_KIND = "mf1750-g1-s1-rc2g-n4-v3-fixed-action-lock"
EVIDENCE_KIND = "mf1750-g1-s1-rc2g-n4-v3-action-evidence"
OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n4-v3-action-observation"
FINALIZATION_KIND = "mf1750-g1-s1-rc2g-n4-v3-action-finalization"
BUNDLE_KIND = "mf1750-g1-s1-rc2g-n4-v3-finalized-action-bundle"

LOCK_FILENAME = "ATTEMPT-LOCK.json"
PROFILE_FILENAME = "REVIEWED-LIMIT-PROFILE.json"
EVIDENCE_FILENAME = "N4-V3-ACTION-EVIDENCE.json"
OBSERVATION_FILENAME = "N4-V3-ACTION-OBSERVATION.json"
FINALIZATION_FILENAME = "N4-V3-ACTION-FINALIZATION.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
CELL_OBSERVATION_FILENAME = "N4-V3-CELL-OBSERVATION.json"
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N4_V3_FIXED_ACTION__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
CONTRACT_HASH_SCOPE = (
    "entire N4 V3 fixed execution contract excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)

EXPECTED_SOURCE_P0_CAMPAIGN_CANONICAL_SHA256 = (
    "bc436f52fd561f669bac3d67dc45c55f8daaf886867fc79399351d2004ef96ab"
)
EXPECTED_SOURCE_P0_CAMPAIGN_FILE_SHA256 = (
    "7a1a2fe807912f410e382079ec5d02866d59466157c06b3bebb4f2b6d53aca28"
)
EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256 = (
    "458d3cd4ba2137f5993a34c491a0465fe0d32ef05d65888a063163bdb8416b4f"
)
EXPECTED_P0_CAMPAIGN_FILE_SHA256 = (
    "28f6b0fae4918486242b5b0c5f8d5846bf1de9c2a8195346d5df3aca22cf4f70"
)
EXPECTED_CONTRACT_CANONICAL_SHA256: Optional[str] = (
    "fc91f32ede1a9fbe073279e07e20fc7271bf715aae3c2ef953ed45e53874f2f0"
)
EXPECTED_CONTRACT_FILE_SHA256: Optional[str] = (
    "d088f72159baa0b18e57bef9c0a2d052b285aa713a5dc4a966843417303f88e0"
)

FIXED_ACTION_SHA256S = {
    "low-balanced-map-primer": (
        "7f1841c72a6e544f2828cd1ae4565296162a0f21b179965a6e5e913cd2113485"
    ),
    "low-balanced-target": (
        "761e7bdb89974d4d8be3fe866e7b85bc9d1a36a219d85c75a9ba7144a032e4e4"
    ),
    "low-unbalanced-map-primer": (
        "0ae3e936cd7a692fa0eaa916ca315f0b41f2f14247bab5cc2b4dd14693949998"
    ),
    "low-unbalanced-target": (
        "6574c0df52aa340e60a282ee36890afd76aaa6cfd1ebf1b47467d3b8ce6e92ec"
    ),
    "high-balanced-map-primer": (
        "e9f6f834f92cfd52c583cb4f1f82293d35a41cc132f17ea73ec1fb42ded711c4"
    ),
    "high-balanced-target": (
        "7e73464258ee2da1eac834c43f3bbbc9cfc6179f480f9f625495528a226d125b"
    ),
    "high-unbalanced-map-primer": (
        "65557023127297794dd7e9fd6882d08d702343f4db78fc47f19efd141a5cefad"
    ),
    "high-unbalanced-target": (
        "644a2ffd624e9482a8162c7e0d25039fb046b3deec39c66965bfbaa5f0499e05"
    ),
}
FIXED_ACTION_KEYS = tuple(FIXED_ACTION_SHA256S)


class N4V3ExecutionContractError(ValueError):
    """The frozen V3 source or reviewed execution envelope changed."""


@dataclass(frozen=True)
class N4V3ActionSnapshot:
    """Immutable compiler-to-runner boundary for one enumerated N4 action."""

    key: str
    cell_id: str
    phase: str
    campaign: Mapping[str, Any]
    action: Mapping[str, Any]
    frame: bytes
    reference_preview: Mapping[str, Any]


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N4V3ExecutionContractError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": CONTRACT_HASH_SCOPE,
    }


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise N4V3ExecutionContractError(
            f"{label} keys changed; missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _source_p0_campaign() -> Mapping[str, Any]:
    try:
        campaign = v3.compile_p0_campaign(
            panel=PANEL_CONTRACT,
            firmware=FIRMWARE_CONTRACT,
            minimum_interval_seconds=0,
            planned_cooldown_seconds=0,
            campaign_id=CAMPAIGN_ID,
        )
        root = validate_campaign_contract(campaign)
    except (CampaignContractError, v3.V3FactorialError) as error:
        raise N4V3ExecutionContractError(
            f"historical V3 P0 campaign validation failed: {error}"
        ) from error
    if (
        root["integrity"]["canonical_sha256"]
        != EXPECTED_SOURCE_P0_CAMPAIGN_CANONICAL_SHA256
        or _sha256(root) != EXPECTED_SOURCE_P0_CAMPAIGN_FILE_SHA256
    ):
        raise N4V3ExecutionContractError("historical V3 P0 campaign identity changed")
    return root


def _execution_sessions(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    sessions = []
    for old in source["sessions"]:
        session = build_session_contract(
            session_id=old["session_id"],
            cell_id=old["cell_id"],
            power_mode=old["power_mode"],
            planned_cooldown_seconds=old["planned_cooldown_seconds"],
            final_power_off_required=False,
            action_identity_sha256s=old["action_identity_sha256s"],
        )
        changed = {key for key in old if old[key] != session[key]}
        if changed != {"final_power_off_required", "integrity"}:
            raise N4V3ExecutionContractError(
                "execution session changed fields beyond the reviewed power flag"
            )
        if (
            session["power_mode"] != "controller_fresh_boot"
            or session["requires_controller_fresh_boot"] is not True
            or session["requires_panel_power_cycle"] is not False
            or session["j2_may_remain_on_before_session"] is not True
            or session["final_power_off_required"] is not False
            or session["automatic_advance"] is not False
        ):
            raise N4V3ExecutionContractError("execution session power semantics changed")
        sessions.append(session)
    return sessions


def _execution_p0_campaign(source: Mapping[str, Any]) -> Mapping[str, Any]:
    unsigned = {key: _snapshot(value) for key, value in source.items() if key != "integrity"}
    unsigned["sessions"] = _execution_sessions(source)
    try:
        campaign = seal_campaign_contract(unsigned)
        root = validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N4V3ExecutionContractError(
            f"N4 V3 execution P0 campaign validation failed: {error}"
        ) from error
    if (
        root["integrity"]["canonical_sha256"]
        != EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
        or _sha256(root) != EXPECTED_P0_CAMPAIGN_FILE_SHA256
    ):
        raise N4V3ExecutionContractError("N4 V3 execution P0 identity changed")
    return root


def _actual_action_sha256s(campaign: Mapping[str, Any]) -> dict[str, str]:
    actual = {}
    for action in campaign["actions"]:
        identity = action["identity"]
        actual[f"{identity['cell_id']}-{identity['phase']}"] = action[
            "action_identity_sha256"
        ]
    return actual


def _power_semantics() -> dict[str, Any]:
    return {
        "historical_source_session_final_power_off_required": True,
        "execution_session_final_power_off_required": False,
        "superseded_source_fields": [
            "sessions[*].final_power_off_required",
            "sessions[*].integrity",
            "campaign.integrity",
        ],
        "action_identities_changed": False,
        "controller_fresh_boot_required_before_each_map_primer": True,
        "same_cell_map_to_target_controller_continuity_required": True,
        "same_cell_panel_power_cycle_forbidden": True,
        "same_cell_j2_disconnect_forbidden": True,
        "other_visible_refresh_between_same_cell_actions_forbidden": True,
        "j2_may_remain_on_between_cells": True,
        "power_off_required_after_campaign_or_abnormality": True,
        "power_off_required_before_firmware_or_configuration_change": True,
        "runner_controls_j2_or_power": False,
    }


def _evidence_contract() -> dict[str, Any]:
    visual_protocol = {
        "protocol_id": "n4-v3-standardized-cell-visual-observation-v1",
        "full_panel_inspection_required": True,
        "strict_target_preview_required": True,
        "map_fidelity_checked_before_target": True,
        "orientation_and_center_seam_checked": True,
        "fixed_camera_optional": True,
        "fidelity_score": {
            "minimum": 0,
            "maximum": 1,
            "direction": "higher_is_better",
        },
        "ghosting_score": {
            "minimum": 0,
            "maximum": None,
            "direction": "lower_is_better",
        },
        "artifact_severity_score": {
            "minimum": 0,
            "maximum": None,
            "direction": "lower_is_better",
        },
        "scores_are_descriptive_only": True,
        "visual_electrical_thermal_assessed_separately": True,
    }
    return {
        "runner_kind": RUNNER_KIND,
        "claim_kind": CLAIM_KIND,
        "lock_kind": LOCK_KIND,
        "evidence_kind": EVIDENCE_KIND,
        "observation_kind": OBSERVATION_KIND,
        "finalization_kind": FINALIZATION_KIND,
        "bundle_kind": BUNDLE_KIND,
        "filenames": {
            "lock": LOCK_FILENAME,
            "profile": PROFILE_FILENAME,
            "evidence": EVIDENCE_FILENAME,
            "observation": OBSERVATION_FILENAME,
            "finalization": FINALIZATION_FILENAME,
            "result": P0_RESULT_FILENAME,
            "cell_observation_for_target": CELL_OBSERVATION_FILENAME,
        },
        "workspace_global_claim_before_network": True,
        "maximum_post_requests_per_action": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "result_evidence_manifest_is_finalization_whole_file_sha256": True,
        "target_requires_exact_same_cell_map_result_and_finalization": True,
        "authorization_prefix": AUTHORIZATION_PREFIX,
        "authorization_suffix": AUTHORIZATION_SUFFIX,
        "visual_observation_protocol": visual_protocol,
        "visual_observation_protocol_sha256": _sha256(visual_protocol),
    }


@lru_cache(maxsize=1)
def _compile_cached() -> Mapping[str, Any]:
    source = _source_p0_campaign()
    execution = _execution_p0_campaign(source)
    source_actions = _actual_action_sha256s(source)
    execution_actions = _actual_action_sha256s(execution)
    if source_actions != FIXED_ACTION_SHA256S or execution_actions != FIXED_ACTION_SHA256S:
        raise N4V3ExecutionContractError("N4 V3 eight-action allowlist changed")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": CONTRACT_ID,
        "source_v3": {
            "manifest_kind": v3.MANIFEST_KIND,
            "manifest_canonical_sha256": v3.EXPECTED_MANIFEST_CANONICAL_SHA256,
            "manifest_file_sha256": v3.EXPECTED_MANIFEST_FILE_SHA256,
            "proof_kind": v3.PROOF_KIND,
            "proof_canonical_sha256": v3.EXPECTED_PROOF_CANONICAL_SHA256,
            "proof_file_sha256": v3.EXPECTED_PROOF_FILE_SHA256,
        },
        "source_p0_campaign": _snapshot(source),
        "source_p0_campaign_canonical_sha256": source["integrity"][
            "canonical_sha256"
        ],
        "source_p0_campaign_file_sha256": _sha256(source),
        "p0_campaign": _snapshot(execution),
        "p0_campaign_canonical_sha256": execution["integrity"]["canonical_sha256"],
        "p0_campaign_file_sha256": _sha256(execution),
        "fixed_actions": dict(FIXED_ACTION_SHA256S),
        "power_semantics": _power_semantics(),
        "evidence_contract": _evidence_contract(),
        "classification": {
            "offline_compiled": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    return {**unsigned, "integrity": _integrity(unsigned)}


def compile_n4_v3_execution_contract() -> dict[str, Any]:
    """Compile and deep-validate the frozen zero-I/O execution contract."""

    contract = _snapshot(_compile_cached())
    validate_n4_v3_execution_contract(contract)
    return contract


def validate_n4_v3_execution_contract(
    contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    root = _exact(
        contract,
        label="N4 V3 execution contract",
        keys={
            "schema_version",
            "kind",
            "contract_id",
            "source_v3",
            "source_p0_campaign",
            "source_p0_campaign_canonical_sha256",
            "source_p0_campaign_file_sha256",
            "p0_campaign",
            "p0_campaign_canonical_sha256",
            "p0_campaign_file_sha256",
            "fixed_actions",
            "power_semantics",
            "evidence_contract",
            "classification",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != CONTRACT_KIND
        or root["contract_id"] != CONTRACT_ID
    ):
        raise N4V3ExecutionContractError("N4 V3 execution contract identity changed")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned):
        raise N4V3ExecutionContractError("N4 V3 execution contract integrity is invalid")
    expected = _compile_cached()
    if root != expected:
        raise N4V3ExecutionContractError("N4 V3 execution contract contents changed")
    canonical_sha = root["integrity"]["canonical_sha256"]
    file_sha = _sha256(root)
    if (
        EXPECTED_CONTRACT_CANONICAL_SHA256 is not None
        and canonical_sha != EXPECTED_CONTRACT_CANONICAL_SHA256
    ):
        raise N4V3ExecutionContractError("frozen execution contract SHA changed")
    if EXPECTED_CONTRACT_FILE_SHA256 is not None and file_sha != EXPECTED_CONTRACT_FILE_SHA256:
        raise N4V3ExecutionContractError("frozen execution contract file SHA changed")
    return root


def execution_contract_file_sha256(contract: Mapping[str, Any]) -> str:
    return _sha256(validate_n4_v3_execution_contract(contract))


@lru_cache(maxsize=1)
def _frozen_source_artifacts() -> v3.V3Artifacts:
    try:
        artifacts = v3.build_v3_artifacts()
        v3.validate_strict_manifests(artifacts.manifest, artifacts.proof)
    except v3.V3FactorialError as error:
        raise N4V3ExecutionContractError(
            f"frozen N4 V3 source artifact validation failed: {error}"
        ) from error
    if (
        _sha256(artifacts.manifest_bytes) != v3.EXPECTED_MANIFEST_FILE_SHA256
        or artifacts.manifest["manifest_integrity"]["canonical_sha256"]
        != v3.EXPECTED_MANIFEST_CANONICAL_SHA256
        or _sha256(artifacts.proof_bytes) != v3.EXPECTED_PROOF_FILE_SHA256
        or artifacts.proof["proof_integrity"]["canonical_sha256"]
        != v3.EXPECTED_PROOF_CANONICAL_SHA256
    ):
        raise N4V3ExecutionContractError("frozen N4 V3 manifest/proof identity changed")
    return artifacts


def load_n4_v3_action_snapshot(action_key: str) -> N4V3ActionSnapshot:
    """Load one of exactly eight V3 actions; no caller-controlled identity fields."""

    if action_key not in FIXED_ACTION_SHA256S:
        raise N4V3ExecutionContractError(
            "action_key is not one of the eight frozen N4 V3 actions"
        )
    contract = compile_n4_v3_execution_contract()
    campaign = contract["p0_campaign"]
    action_sha = FIXED_ACTION_SHA256S[action_key]
    matches = [
        action
        for action in campaign["actions"]
        if action["action_identity_sha256"] == action_sha
    ]
    if len(matches) != 1:
        raise N4V3ExecutionContractError("selected N4 action is not unique")
    action = matches[0]
    identity = action["identity"]
    cell_id = identity["cell_id"]
    phase = identity["phase"]
    artifacts = _frozen_source_artifacts()
    if phase == "map-primer":
        frame = generate_fixture("map-orient-v1")
        reference_preview = {
            "kind": "map_fixture_frame",
            "bundle_filename": None,
            "sha256": identity["frame"]["sha256"],
        }
    elif phase == "target":
        variant = artifacts.variants.get(cell_id)
        manifest_variant = artifacts.manifest["variants"].get(cell_id)
        if variant is None or not isinstance(manifest_variant, Mapping):
            raise N4V3ExecutionContractError("selected N4 target cell is missing")
        frame = variant.frame
        reference_preview = {
            "kind": "n4_v3_strict_final_png",
            "bundle_filename": f"{cell_id}.strict-final.png",
            "sha256": manifest_variant["strict_preview"]["sha256"],
        }
        if _sha256(variant.strict_png) != reference_preview["sha256"]:
            raise N4V3ExecutionContractError("N4 target strict preview identity changed")
    else:  # pragma: no cover - campaign validator and fixed allowlist preclude this
        raise N4V3ExecutionContractError("selected N4 action phase changed")
    try:
        validate_frame(frame)
    except ValueError as error:
        raise N4V3ExecutionContractError(
            f"selected N4 frame validation failed: {error}"
        ) from error
    frame_record = identity["frame"]
    actual_controllers = []
    for controller in frame_record["controllers"]:
        mapping = controller["mapping"]
        # Keep the controller order/mapping anchored in the P0 record itself.
        stream = controller_stream(
            frame,
            ControllerMapping(
                source_half=mapping["source_half"],
                flip_x=mapping["flip_x"],
                flip_y=mapping["flip_y"],
                nibble_swap=mapping["nibble_swap"],
            ),
        )
        actual_controllers.append(
            {
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    if (
        _sha256(frame) != frame_record["sha256"]
        or f"0x{fnv1a(frame):08X}" != frame_record["fnv1a"]
        or actual_controllers
        != [
            {
                "dtm_sha256": controller["dtm_sha256"],
                "dtm_fnv1a": controller["dtm_fnv1a"],
            }
            for controller in frame_record["controllers"]
        ]
    ):
        raise N4V3ExecutionContractError("selected N4 frame/DTM identity changed")
    return N4V3ActionSnapshot(
        key=action_key,
        cell_id=cell_id,
        phase=phase,
        campaign=campaign,
        action=action,
        frame=frame,
        reference_preview=reference_preview,
    )


def build_n4_v3_target_protocol_contract(
    snapshot: N4V3ActionSnapshot,
) -> _quality._RunContract:
    """Build the audited RC2G validator contract for one frozen target."""

    if snapshot.phase != "target":
        raise N4V3ExecutionContractError("target protocol contract requested for MAP")
    actions = {
        action["action_identity_sha256"]: action
        for action in snapshot.campaign["actions"]
    }
    prior_sha = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    prior_action = actions.get(prior_sha)
    if prior_action is None:
        raise N4V3ExecutionContractError("N4 V3 target prior action is missing")
    prior_frame = prior_action["identity"]["frame"]
    frame_record = snapshot.action["identity"]["frame"]
    source = compile_n4_v3_execution_contract()["source_v3"]
    candidate = _quality._CandidateSnapshot(
        directory=v3.REPO_ROOT,
        manifest={
            "kind": "mf1750-g1-s1-root-cause-2x2-v3-runtime-snapshot",
            "cell_id": snapshot.cell_id,
        },
        manifest_bytes=b"",
        manifest_file_sha256=source["manifest_file_sha256"],
        manifest_canonical_sha256=source["manifest_canonical_sha256"],
        algorithm=v3.ALGORITHM_ID,
        frame=snapshot.frame,
        frame_sha256=frame_record["sha256"],
        frame_fnv1a=int(frame_record["fnv1a"], 16),
        controllers=tuple(frame_record["controllers"]),
    )
    return _quality._RunContract(
        snapshot=candidate,
        expected_prior_job_id=1,
        expected_prior_operation_id=1,
        expected_prior_frame_sha256=prior_frame["sha256"],
        expected_prior_frame_fnv1a=int(prior_frame["fnv1a"], 16),
        expected_prior_cs1_dtm_fnv1a=int(
            prior_frame["controllers"][0]["dtm_fnv1a"], 16
        ),
        expected_prior_cs2_dtm_fnv1a=int(
            prior_frame["controllers"][1]["dtm_fnv1a"], 16
        ),
        expected_target_job_id=2,
        expected_target_operation_id=2,
        action_identity=snapshot.action["identity"],
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        required_authorization_confirmation="bound-by-N4-runner-not-protocol-validator",
    )


def validate_n4_v3_protocol_evidence(
    evidence: Mapping[str, Any],
    *,
    snapshot: N4V3ActionSnapshot,
    prior_bundle: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    """Replay the audited RC2G protocol validators over stored evidence only."""

    protocol = evidence.get("protocol_evidence")
    if not isinstance(protocol, Mapping):
        raise N4V3ExecutionContractError("N4 V3 protocol evidence is missing")
    try:
        if snapshot.phase == "map-primer":
            root = _exact(
                protocol,
                label="N4 V3 MAP protocol evidence",
                keys={"fresh_boot_preflight", "completed_map_evidence"},
            )
            fresh = _exact(
                root["fresh_boot_preflight"],
                label="N4 V3 fresh boot evidence",
                keys={
                    "version",
                    "job_raw",
                    "diagnostic_raw",
                    "gpio_status_raw",
                    "busy_after_rst_low_is_informational",
                },
            )
            _map._validate_version(fresh["version"], label="N4 V3 stored fresh boot")
            if fresh["job_raw"] != {
                "job_id": 0,
                "action": "none",
                "state": "idle",
                "result": None,
                "queued_at_ms": 0,
                "started_at_ms": 0,
                "finished_at_ms": 0,
                "frame_fnv1a": 0,
            } or fresh["diagnostic_raw"] != {
                "schema_version": 2,
                "valid": False,
                "error": "no_completed_job_report",
            }:
                raise N4V3ExecutionContractError(
                    "N4 V3 stored preflight is not fresh job0/operation0"
                )
            _map._validate_gpio_snapshot(
                fresh["gpio_status_raw"], label="N4 V3 stored fresh-boot GPIO"
            )
            if fresh["busy_after_rst_low_is_informational"] is not True:
                raise N4V3ExecutionContractError(
                    "N4 V3 stored fresh-boot BUSY interpretation changed"
                )
            completed = root["completed_map_evidence"]
            if not isinstance(completed, Mapping):
                raise N4V3ExecutionContractError(
                    "N4 V3 completed MAP evidence is missing"
                )
            rebuilt = _map._validate_completed_map_evidence(
                completed.get("network_report"),
                completed.get("job_raw"),
                completed.get("diagnostic_raw"),
                completed.get("gpio_status_raw"),
                snapshot.frame,
            )
            if rebuilt != completed:
                raise N4V3ExecutionContractError(
                    "N4 V3 stored MAP protocol derived fields changed"
                )
            if prior_bundle is not None:
                raise N4V3ExecutionContractError("N4 V3 MAP protocol must not bind prior")
            return root

        root = _exact(
            protocol,
            label="N4 V3 target protocol evidence",
            keys={
                "same_cell_primer_live_preflight",
                "network_report",
                "target_job_raw",
                "target_diagnostic_raw",
                "target_diagnostic_validated",
                "post_refresh_gpio_status_raw",
            },
        )
        if prior_bundle is None:
            raise N4V3ExecutionContractError(
                "N4 V3 target protocol requires exact stored MAP bundle"
            )
        prior_evidence = prior_bundle.get("evidence")
        if not isinstance(prior_evidence, Mapping):
            raise N4V3ExecutionContractError("N4 V3 MAP bundle evidence is missing")
        prior_protocol = prior_evidence.get("protocol_evidence")
        if not isinstance(prior_protocol, Mapping):
            raise N4V3ExecutionContractError("N4 V3 MAP protocol is missing")
        completed_map = prior_protocol.get("completed_map_evidence")
        if not isinstance(completed_map, Mapping):
            raise N4V3ExecutionContractError("N4 V3 completed MAP evidence is missing")
        run_contract = build_n4_v3_target_protocol_contract(snapshot)
        live = _exact(
            root["same_cell_primer_live_preflight"],
            label="N4 V3 target live MAP preflight",
            keys={
                "version",
                "job",
                "diagnostic_raw",
                "nested_busy_trace",
                "gpio",
                "expected_identity",
            },
        )
        _quality._validate_version(live["version"], label="N4 V3 stored target prior")
        if (
            live["job"] != completed_map.get("job_raw")
            or live["diagnostic_raw"] != completed_map.get("diagnostic_raw")
            or live["expected_identity"] != snapshot.action["identity"]["prior"]
        ):
            raise N4V3ExecutionContractError(
                "N4 V3 target live prior is not the exact stored same-cell MAP"
            )
        trace = _quality._validate_prior_raw_diagnostic(
            live["diagnostic_raw"], live["job"], run_contract
        )
        if live["nested_busy_trace"] != trace:
            raise N4V3ExecutionContractError("N4 V3 target prior BUSY trace changed")
        gpio = live["gpio"]
        if not isinstance(gpio, Mapping) or set(gpio) != {
            "raw",
            "panel_outputs_low_verified",
            "busy_level",
            "busy_after_rst_low_is_informational",
            "busy_interpretation",
        }:
            raise N4V3ExecutionContractError("N4 V3 target prior GPIO evidence changed")
        raw_gpio = _quality._validate_gpio_snapshot(
            gpio["raw"], label="N4 V3 stored target prior GPIO"
        )
        if _quality._gpio_evidence(raw_gpio) != gpio:
            raise N4V3ExecutionContractError(
                "N4 V3 target prior GPIO derived fields changed"
            )
        report = root["network_report"]
        _quality._validate_network_report(report, run_contract)
        if root["target_job_raw"] != report.get("job"):
            raise N4V3ExecutionContractError("N4 V3 target immutable job changed")
        normalized = _quality._validate_target_raw_diagnostic(
            root["target_diagnostic_raw"], report, run_contract
        )
        if normalized != root["target_diagnostic_validated"]:
            raise N4V3ExecutionContractError(
                "N4 V3 target diagnostic derived fields changed"
            )
        gpio_raw = _quality._validate_gpio_snapshot(
            root["post_refresh_gpio_status_raw"],
            label="N4 V3 stored target post-refresh GPIO",
        )
        if gpio_raw != root["post_refresh_gpio_status_raw"]:
            raise N4V3ExecutionContractError("N4 V3 target GPIO normalization changed")
        return root
    except (_map.Rc2gMapBaselineError, _quality.Rc2gQualityRefreshError) as error:
        raise N4V3ExecutionContractError(
            f"N4 V3 stored protocol failed audited replay: {error}"
        ) from error


_BUNDLE_RECORDS = (
    "claim",
    "lock",
    "profile",
    "evidence",
    "observation",
    "finalization",
    "result",
)
_TIMING_FIELDS = {
    "queue_delay_ms",
    "job_duration_ms",
    "driver_total_ms",
    "cs1_upload_ms",
    "cs2_upload_ms",
    "pon_ms",
    "drf_ms",
    "pof_ms",
    "post_psr_ms",
}


def _require_sha256(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        suffix = " or null" if nullable else ""
        raise N4V3ExecutionContractError(
            f"{label} must be 64 lowercase hexadecimal digits{suffix}"
        )
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N4V3ExecutionContractError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise N4V3ExecutionContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N4V3ExecutionContractError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N4V3ExecutionContractError(f"{label} is above {maximum}")
    return result


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise N4V3ExecutionContractError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N4V3ExecutionContractError(f"{label} is not valid RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N4V3ExecutionContractError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_action_observation(
    observation: Mapping[str, Any],
    *,
    snapshot: N4V3ActionSnapshot,
    contract: Mapping[str, Any],
    attempt_id: str,
    profile: Mapping[str, Any],
) -> Mapping[str, Any]:
    root = _exact(
        observation,
        label="N4 V3 stored action observation",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "attempt_id",
            "action_key",
            "cell_id",
            "phase",
            "action_identity_sha256",
            "observed_at",
            "reference_preview_sha256",
            "visual",
            "electrical",
            "thermal",
            "continuity",
            "camera",
            "source_observation_file_sha256",
            "visual_pass",
            "electrical_pass",
            "thermal_pass",
            "continuity_pass",
            "overall_state",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != OBSERVATION_KIND
        or root["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or root["attempt_id"] != attempt_id
        or root["action_key"] != snapshot.key
        or root["cell_id"] != snapshot.cell_id
        or root["phase"] != snapshot.phase
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or not isinstance(root["observed_at"], str)
        or not root["observed_at"]
        or root["reference_preview_sha256"]
        != snapshot.reference_preview["sha256"]
    ):
        raise N4V3ExecutionContractError("N4 V3 action observation binding changed")
    _require_sha256(
        root["source_observation_file_sha256"], label="source observation file"
    )

    if snapshot.phase == "map-primer":
        visual = _exact(
            root["visual"],
            label="N4 V3 MAP visual observation",
            keys={
                "map_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "all_six_colors_present",
                "no_retained_old_regions",
            },
        )
        if any(type(value) is not bool for value in visual.values()):
            raise N4V3ExecutionContractError("N4 V3 MAP visual flags must be boolean")
        visual_pass = all(visual.values())
    else:
        visual = _exact(
            root["visual"],
            label="N4 V3 target visual observation",
            keys={
                "protocol_sha256",
                "observation_evidence_sha256",
                "roi_definition_sha256",
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
                "fidelity_score",
                "ghosting_score",
                "artifact_severity_score",
            },
        )
        for field in (
            "protocol_sha256",
            "observation_evidence_sha256",
            "roi_definition_sha256",
        ):
            _require_sha256(visual[field], label=f"target visual {field}")
        if (
            visual["protocol_sha256"]
            != contract["evidence_contract"]["visual_observation_protocol_sha256"]
            or visual["observation_evidence_sha256"]
            != root["source_observation_file_sha256"]
        ):
            raise N4V3ExecutionContractError(
                "N4 V3 target visual protocol/evidence binding changed"
            )
        for field in (
            "target_fidelity_pass",
            "orientation_pass",
            "seam_assessment_pass",
            "full_panel_inspected",
            "no_retained_old_regions",
        ):
            if type(visual[field]) is not bool:
                raise N4V3ExecutionContractError(
                    f"target visual {field} must be boolean"
                )
        _number(visual["fidelity_score"], label="fidelity_score", minimum=0, maximum=1)
        _number(visual["ghosting_score"], label="ghosting_score", minimum=0)
        _number(
            visual["artifact_severity_score"],
            label="artifact_severity_score",
            minimum=0,
        )
        visual_pass = all(
            visual[field]
            for field in (
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
            )
        )

    electrical = _exact(
        root["electrical"],
        label="N4 V3 action electrical observation",
        keys={
            "meter_asset_sha256",
            "clock_asset_sha256",
            "pre_voltage_v",
            "pre_idle_current_a",
            "post_voltage_v",
            "post_idle_current_a",
            "peak_current_a",
            "constant_voltage_mode",
            "timing_ms",
            "reviewed_limits_pass",
        },
    )
    _require_sha256(electrical["meter_asset_sha256"], label="meter asset")
    _require_sha256(electrical["clock_asset_sha256"], label="clock asset")
    for field in (
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
    ):
        _number(electrical[field], label=f"electrical.{field}", minimum=0)
    if (
        type(electrical["constant_voltage_mode"]) is not bool
        or type(electrical["reviewed_limits_pass"]) is not bool
    ):
        raise N4V3ExecutionContractError("N4 V3 electrical pass fields must be boolean")
    timing = _exact(
        electrical["timing_ms"],
        label="N4 V3 action timing",
        keys=_TIMING_FIELDS,
    )
    for field, value in timing.items():
        _number(value, label=f"timing_ms.{field}", minimum=0)
    electrical_pass = bool(
        electrical["constant_voltage_mode"] and electrical["reviewed_limits_pass"]
    )

    thermal = _exact(
        root["thermal"],
        label="N4 V3 action thermal observation",
        keys={
            "pre_action_c",
            "post_action_c",
            "session_max_c",
            "uncertainty_u95_c",
            "sensor_asset_sha256",
            "calibration_artifact_sha256",
            "measurement_evidence_sha256",
            "uncertainty_evidence_sha256",
        },
    )
    pre_temperature = _number(thermal["pre_action_c"], label="thermal.pre_action_c")
    post_temperature = _number(thermal["post_action_c"], label="thermal.post_action_c")
    session_max = _number(thermal["session_max_c"], label="thermal.session_max_c")
    if session_max < max(pre_temperature, post_temperature):
        raise N4V3ExecutionContractError(
            "N4 V3 session maximum is below an action temperature sample"
        )
    _number(
        thermal["uncertainty_u95_c"], label="thermal.uncertainty_u95_c", minimum=0
    )
    for field in (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "measurement_evidence_sha256",
        "uncertainty_evidence_sha256",
    ):
        _require_sha256(thermal[field], label=f"thermal.{field}")
    maximum_temperature = profile["limits"]["maximum_post_refresh_temperature_c"]
    if maximum_temperature is None:
        raise N4V3ExecutionContractError("reviewed profile lacks maximum temperature")
    thermal_pass = post_temperature <= maximum_temperature and session_max <= maximum_temperature

    if snapshot.phase == "map-primer":
        if root["continuity"] is not None:
            raise N4V3ExecutionContractError("MAP observation continuity must be null")
        continuity_pass = True
    else:
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
            raise N4V3ExecutionContractError("N4 V3 continuity fields must be boolean")
        continuity_pass = not any(continuity.values())

    camera = _exact(
        root["camera"],
        label="N4 V3 camera binding",
        keys={
            "observation_kind",
            "observer_or_camera_asset_sha256",
            "capture_file_sha256",
            "fixed_exposure_profile_sha256",
            "copied_file",
            "bytes",
            "decoded_format",
            "width",
            "height",
        },
    )
    if camera["observation_kind"] not in {"standardized-manual", "fixed-camera"}:
        raise N4V3ExecutionContractError("N4 V3 camera observation kind is invalid")
    _require_sha256(
        camera["observer_or_camera_asset_sha256"],
        label="observer or camera asset",
    )
    if camera["observation_kind"] == "standardized-manual":
        if any(
            camera[field] is not None
            for field in (
                "capture_file_sha256",
                "fixed_exposure_profile_sha256",
                "copied_file",
                "bytes",
                "decoded_format",
                "width",
                "height",
            )
        ):
            raise N4V3ExecutionContractError(
                "manual observation must not imply camera evidence"
            )
    else:
        _require_sha256(camera["capture_file_sha256"], label="camera capture")
        _require_sha256(
            camera["fixed_exposure_profile_sha256"], label="fixed exposure profile"
        )
        if (
            not isinstance(camera["copied_file"], str)
            or not camera["copied_file"]
            or type(camera["bytes"]) is not int
            or camera["bytes"] < 1
            or not isinstance(camera["decoded_format"], str)
            or not camera["decoded_format"]
            or type(camera["width"]) is not int
            or camera["width"] < 1
            or type(camera["height"]) is not int
            or camera["height"] < 1
        ):
            raise N4V3ExecutionContractError("fixed-camera binding is incomplete")

    expected_state = (
        ResultState.PASS.value
        if visual_pass and electrical_pass and thermal_pass and continuity_pass
        else ResultState.FAIL.value
    )
    if (
        root["visual_pass"] is not visual_pass
        or root["electrical_pass"] is not electrical_pass
        or root["thermal_pass"] is not thermal_pass
        or root["continuity_pass"] is not continuity_pass
        or root["overall_state"] != expected_state
    ):
        raise N4V3ExecutionContractError("N4 V3 observation derived verdict changed")
    return root


def _record_and_sha(
    bundle: Mapping[str, Any], name: str
) -> tuple[Mapping[str, Any], str]:
    record = bundle[name]
    if not isinstance(record, Mapping):
        raise N4V3ExecutionContractError(f"bundle {name} must be an object")
    declared = _require_sha256(
        bundle[f"{name}_file_sha256"], label=f"bundle {name} whole-file SHA-256"
    )
    actual = _sha256(record)
    if declared != actual:
        raise N4V3ExecutionContractError(
            f"bundle {name} whole-file SHA-256 does not match canonical bytes"
        )
    return record, actual


def _frozen_contract_snapshot_loader(
    _contract: Mapping[str, Any], action_key: str
) -> N4V3ActionSnapshot:
    """Default snapshot seam retained for the frozen legacy contract."""

    return load_n4_v3_action_snapshot(action_key)


def _frozen_authorization_confirmation(
    _contract: Mapping[str, Any], snapshot: N4V3ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def validate_n4_v3_finalized_action_bundle(
    contract: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    expected_action_key: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    _contract_validator: Any = validate_n4_v3_execution_contract,
    _snapshot_loader: Any = _frozen_contract_snapshot_loader,
    _contract_file_sha256: Any = execution_contract_file_sha256,
    _authorization_confirmation: Any = _frozen_authorization_confirmation,
    _record_extra_keys: Optional[Mapping[str, set[str] | frozenset[str]]] = None,
    _record_extension_validator: Any = None,
) -> dict[str, Any]:
    """Deep-validate one canonical runner chain without performing any I/O.

    The underscored callables are an internal, fail-closed adapter seam for a
    separately validated physical-bound contract.  Public callers retain the
    exact frozen validators by default; no legacy identity can be overridden.
    """

    root_contract = _contract_validator(contract)
    extra_keys = _record_extra_keys or {}
    root = _exact(
        bundle,
        label="N4 V3 finalized action bundle",
        keys={
            "schema_version",
            "kind",
            *(
                item
                for name in _BUNDLE_RECORDS
                for item in (name, f"{name}_file_sha256")
            ),
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != BUNDLE_KIND:
        raise N4V3ExecutionContractError("N4 V3 finalized bundle identity changed")
    records = {name: _record_and_sha(root, name) for name in _BUNDLE_RECORDS}
    claim, claim_sha = records["claim"]
    lock, lock_sha = records["lock"]
    profile, profile_sha = records["profile"]
    evidence, evidence_sha = records["evidence"]
    observation, observation_sha = records["observation"]
    finalization, finalization_sha = records["finalization"]
    result, result_sha = records["result"]

    evidence_root = _exact(
        evidence,
        label="N4 V3 protocol evidence",
        keys={
            "schema_version",
            "kind",
            "runner_kind",
            "attempt_id",
            "recorded_at",
            "action_key",
            "cell_id",
            "phase",
            "action_identity_sha256",
            "execution_contract_canonical_sha256",
            "execution_contract_file_sha256",
            "p0_campaign_canonical_sha256",
            "source_manifest_canonical_sha256",
            "source_proof_canonical_sha256",
            "frame_sha256",
            "reference_preview",
            "claim",
            "profile_canonical_sha256",
            "profile_file_sha256",
            "profile_evaluated_at",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "start_temperature_c",
            "maximum_post_requests",
            "automatic_retry_count",
            "retry_allowed",
            "recovery_performed",
            "outcome",
            "protocol_verified",
            "protocol_completed_at",
            "protocol_evidence",
            "request_audit",
            "error",
        }
        | set(extra_keys.get("evidence", set())),
    )
    action_key = evidence_root["action_key"]
    if expected_action_key is not None and action_key != expected_action_key:
        raise N4V3ExecutionContractError("bundle is not the expected N4 action")
    snapshot = _snapshot_loader(root_contract, str(action_key))
    attempt_id = evidence_root["attempt_id"]
    if not isinstance(attempt_id, str) or not attempt_id:
        raise N4V3ExecutionContractError("N4 V3 attempt_id is invalid")
    recorded_at = _timestamp(evidence_root["recorded_at"], label="evidence.recorded_at")
    evaluated_at = _timestamp(
        evidence_root["profile_evaluated_at"], label="evidence.profile_evaluated_at"
    )
    protocol_completed_at = _timestamp(
        evidence_root["protocol_completed_at"],
        label="evidence.protocol_completed_at",
    )
    if evaluated_at > recorded_at or protocol_completed_at < recorded_at:
        raise N4V3ExecutionContractError(
            "N4 V3 profile/claim/protocol timestamp order changed"
        )
    if (
        evidence_root["schema_version"] != SCHEMA_VERSION
        or evidence_root["kind"] != EVIDENCE_KIND
        or evidence_root["runner_kind"] != RUNNER_KIND
        or evidence_root["cell_id"] != snapshot.cell_id
        or evidence_root["phase"] != snapshot.phase
        or evidence_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or evidence_root["execution_contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or evidence_root["execution_contract_file_sha256"]
        != _contract_file_sha256(root_contract)
        or evidence_root["p0_campaign_canonical_sha256"]
        != root_contract["p0_campaign_canonical_sha256"]
        or evidence_root["source_manifest_canonical_sha256"]
        != root_contract["source_v3"]["manifest_canonical_sha256"]
        or evidence_root["source_proof_canonical_sha256"]
        != root_contract["source_v3"]["proof_canonical_sha256"]
        or evidence_root["frame_sha256"]
        != snapshot.action["identity"]["frame"]["sha256"]
        or evidence_root["reference_preview"] != snapshot.reference_preview
        or evidence_root["maximum_post_requests"] != 1
        or evidence_root["automatic_retry_count"] != 0
        or evidence_root["retry_allowed"] is not False
        or evidence_root["recovery_performed"] is not False
        or evidence_root["outcome"] != "protocol_verified_observation_pending"
        or evidence_root["protocol_verified"] is not True
        or not isinstance(evidence_root["protocol_evidence"], Mapping)
        or evidence_root["error"] is not None
    ):
        raise N4V3ExecutionContractError("N4 V3 protocol evidence binding changed")

    try:
        validated_profile = validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N4V3ExecutionContractError(f"N4 V3 profile is invalid: {error}") from error
    if (
        validated_profile["panel"] != root_contract["p0_campaign"]["panel"]
        or validated_profile["firmware"] != root_contract["p0_campaign"]["firmware"]
        or evidence_root["profile_file_sha256"] != profile_sha
        or evidence_root["profile_canonical_sha256"]
        != validated_profile["integrity"]["canonical_sha256"]
    ):
        raise N4V3ExecutionContractError("N4 V3 reviewed profile binding changed")

    claim_root = _exact(
        claim,
        label="N4 V3 workspace-global claim",
        keys={
            "schema_version",
            "kind",
            "registry_id",
            "action_key",
            "action_identity_sha256",
            "execution_contract_canonical_sha256",
            "p0_campaign_canonical_sha256",
            "attempt_id",
            "claimed_at",
            "state",
            "authorization_consumed_permanently",
            "authorization_confirmation_sha256",
            "profile_canonical_sha256",
            "profile_file_sha256",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "start_temperature_c",
            "confirmations",
            "result_directory",
            "maximum_post_requests",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
        }
        | set(extra_keys.get("claim", set())),
    )
    expected_claim_state = "authorization_permanently_consumed_do_not_rerun"
    claimed_at = _timestamp(claim_root["claimed_at"], label="claim.claimed_at")
    confirmation_sha = _require_sha256(
        claim_root["authorization_confirmation_sha256"],
        label="claim authorization confirmation",
    )
    expected_confirmation = _authorization_confirmation(root_contract, snapshot)
    expected_confirmation_sha = _sha256(expected_confirmation.encode("ascii"))
    expected_confirmation_keys = {
        "reviewed_panel_and_build",
        "supervised_supply_cv_current_normal",
        "physical_cutoff_available",
        "single_visible_refresh",
        *(
            {"controller_fresh_boot"}
            if snapshot.phase == "map-primer"
            else {
                "map_fidelity_from_same_cell_primer",
                "esp32_not_restarted_since_primer",
                "no_j2_disconnect_since_primer",
                "no_panel_power_cycle_since_primer",
                "no_other_visible_refresh_since_primer",
            }
        ),
    }
    confirmations = _exact(
        claim_root["confirmations"],
        label="N4 V3 physical confirmations",
        keys=expected_confirmation_keys,
    )
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N4V3ExecutionContractError(
            "N4 V3 all action-specific physical confirmations must be true"
        )
    if (
        claim_root["schema_version"] != SCHEMA_VERSION
        or claim_root["kind"] != CLAIM_KIND
        or claim_root["registry_id"] != CLAIM_REGISTRY_ID
        or claim_root["action_key"] != action_key
        or claim_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or claim_root["execution_contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or claim_root["p0_campaign_canonical_sha256"]
        != root_contract["p0_campaign_canonical_sha256"]
        or claim_root["attempt_id"] != attempt_id
        or claimed_at != recorded_at
        or claim_root["state"] != expected_claim_state
        or claim_root["authorization_consumed_permanently"] is not True
        or claim_root["profile_canonical_sha256"]
        != validated_profile["integrity"]["canonical_sha256"]
        or claim_root["profile_file_sha256"] != profile_sha
        or confirmation_sha != expected_confirmation_sha
        or claim_root["maximum_post_requests"] != 1
        or claim_root["automatic_retry_authorized"] is not False
        or claim_root["automatic_recovery_authorized"] is not False
    ):
        raise N4V3ExecutionContractError("N4 V3 consumed claim binding changed")
    claim_reference = _exact(
        evidence_root["claim"],
        label="N4 V3 claim reference",
        keys={
            "registry_id",
            "filename",
            "file_sha256",
            "attempt_id",
            "action_identity_sha256",
            "state",
        },
    )
    if claim_reference != {
        "registry_id": CLAIM_REGISTRY_ID,
        "filename": f"{snapshot.action['action_identity_sha256']}.json",
        "file_sha256": claim_sha,
        "attempt_id": attempt_id,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "state": expected_claim_state,
    }:
        raise N4V3ExecutionContractError("N4 V3 claim reference changed")

    lock_root = _exact(
        lock,
        label="N4 V3 action lock",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "attempt_id",
            "action_key",
            "action_identity_sha256",
            "claim",
            "confirmations",
            "authorization_confirmation_sha256",
            "state",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
        }
        | set(extra_keys.get("lock", set())),
    )
    if (
        lock_root["schema_version"] != SCHEMA_VERSION
        or lock_root["kind"] != LOCK_KIND
        or lock_root["execution_contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or lock_root["attempt_id"] != attempt_id
        or lock_root["action_key"] != action_key
        or lock_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or lock_root["claim"] != claim_reference
        or lock_root["confirmations"] != claim_root["confirmations"]
        or lock_root["authorization_confirmation_sha256"]
        != claim_root["authorization_confirmation_sha256"]
        or lock_root["state"] != expected_claim_state
        or lock_root["automatic_retry_authorized"] is not False
        or lock_root["automatic_recovery_authorized"] is not False
    ):
        raise N4V3ExecutionContractError("N4 V3 action lock binding changed")
    _require_sha256(
        lock_root["authorization_confirmation_sha256"],
        label="lock authorization confirmation",
    )

    audit = _exact(
        evidence_root["request_audit"],
        label="N4 V3 request audit",
        keys={"post_attempt_count", "post_issued_count", "calls"},
    )
    calls = audit["calls"]
    if (
        audit["post_attempt_count"] != 1
        or audit["post_issued_count"] != 1
        or not isinstance(calls, list)
    ):
        raise N4V3ExecutionContractError("N4 V3 request audit POST count changed")
    posts = [
        call
        for call in calls
        if isinstance(call, Mapping) and call.get("method") == "POST"
    ]
    if (
        len(posts) != 1
        or posts[0].get("endpoint") != "/api/frame"
        or posts[0].get("request_sha256")
        != snapshot.action["identity"]["frame"]["sha256"]
        or any(
            not isinstance(call, Mapping)
            or (call.get("method"), call.get("endpoint"))
            not in {
                ("GET", "/api/version"),
                ("GET", "/api/job"),
                ("GET", "/api/diagnostic/report"),
                ("GET", "/api/diagnostic/status"),
                ("POST", "/api/frame"),
            }
            for call in calls
        )
    ):
        raise N4V3ExecutionContractError("N4 V3 request audit route/frame changed")

    observation_root = _validate_action_observation(
        observation,
        snapshot=snapshot,
        contract=root_contract,
        attempt_id=attempt_id,
        profile=validated_profile,
    )
    if _timestamp(
        observation_root["observed_at"], label="observation.observed_at"
    ) < protocol_completed_at:
        raise N4V3ExecutionContractError(
            "N4 V3 observation predates protocol completion"
        )
    finalization_root = _exact(
        finalization,
        label="N4 V3 action finalization",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "attempt_id",
            "action_key",
            "cell_id",
            "phase",
            "action_identity_sha256",
            "state",
            "claim_file_sha256",
            "lock_file_sha256",
            "protocol_evidence_file_sha256",
            "action_observation_file_sha256",
            "profile_file_sha256",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "visual_pass",
            "electrical_pass",
            "thermal_pass",
            "continuity_pass",
            "post_refresh_temperature_c",
            "session_max_temperature_c",
            "camera_capture_file_sha256",
            "visual_electrical_thermal_assessed_separately",
            "automatic_retry_count",
            "retry_allowed",
            "recovery_performed",
        }
        | set(extra_keys.get("finalization", set())),
    )
    if (
        finalization_root["schema_version"] != SCHEMA_VERSION
        or finalization_root["kind"] != FINALIZATION_KIND
        or finalization_root["execution_contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or finalization_root["attempt_id"] != attempt_id
        or finalization_root["action_key"] != action_key
        or finalization_root["cell_id"] != snapshot.cell_id
        or finalization_root["phase"] != snapshot.phase
        or finalization_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or finalization_root["state"] != observation_root["overall_state"]
        or finalization_root["claim_file_sha256"] != claim_sha
        or finalization_root["lock_file_sha256"] != lock_sha
        or finalization_root["protocol_evidence_file_sha256"] != evidence_sha
        or finalization_root["action_observation_file_sha256"] != observation_sha
        or finalization_root["profile_file_sha256"] != profile_sha
        or finalization_root["visual_pass"] is not observation_root["visual_pass"]
        or finalization_root["electrical_pass"]
        is not observation_root["electrical_pass"]
        or finalization_root["thermal_pass"] is not observation_root["thermal_pass"]
        or finalization_root["continuity_pass"]
        is not observation_root["continuity_pass"]
        or float(finalization_root["post_refresh_temperature_c"])
        != float(observation_root["thermal"]["post_action_c"])
        or float(finalization_root["session_max_temperature_c"])
        != float(observation_root["thermal"]["session_max_c"])
        or finalization_root["camera_capture_file_sha256"]
        != observation_root["camera"]["capture_file_sha256"]
        or finalization_root["visual_electrical_thermal_assessed_separately"]
        is not True
        or finalization_root["automatic_retry_count"] != 0
        or finalization_root["retry_allowed"] is not False
        or finalization_root["recovery_performed"] is not False
    ):
        raise N4V3ExecutionContractError("N4 V3 finalization binding changed")

    try:
        validated_result = validate_result_record(result)
    except CampaignContractError as error:
        raise N4V3ExecutionContractError(f"N4 V3 P0 result is invalid: {error}") from error
    if (
        result_file_sha256(validated_result) != result_sha
        or validated_result["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or validated_result["state"] != finalization_root["state"]
        or _timestamp(validated_result["completed_at"], label="result.completed_at")
        != _timestamp(observation_root["observed_at"], label="observation.observed_at")
        or validated_result["evidence_manifest_sha256"] != finalization_sha
        or validated_result["post_request_count"] != 1
    ):
        raise N4V3ExecutionContractError("N4 V3 P0 result/finalization binding changed")

    if snapshot.phase == "map-primer":
        if prior_bundle is not None or any(
            value is not None
            for value in (
                claim_root["prior_result_file_sha256"],
                claim_root["prior_finalization_file_sha256"],
                evidence_root["prior_result_file_sha256"],
                evidence_root["prior_finalization_file_sha256"],
                finalization_root["prior_result_file_sha256"],
                finalization_root["prior_finalization_file_sha256"],
            )
        ):
            raise N4V3ExecutionContractError("N4 V3 MAP action must not bind a prior")
        prior_result_sha = None
        prior_finalization_sha = None
    else:
        if prior_bundle is None:
            raise N4V3ExecutionContractError(
                "N4 V3 target requires the exact same-cell MAP finalized bundle"
            )
        prior = validate_n4_v3_finalized_action_bundle(
            root_contract,
            prior_bundle,
            expected_action_key=f"{snapshot.cell_id}-map-primer",
            _contract_validator=_contract_validator,
            _snapshot_loader=_snapshot_loader,
            _contract_file_sha256=_contract_file_sha256,
            _authorization_confirmation=_authorization_confirmation,
            _record_extra_keys=_record_extra_keys,
            _record_extension_validator=_record_extension_validator,
        )
        if prior["state"] != ResultState.PASS.value:
            raise N4V3ExecutionContractError("N4 V3 target prior MAP result is not PASS")
        prior_result_sha = prior["result_file_sha256"]
        prior_finalization_sha = prior["finalization_file_sha256"]
        if any(
            value != expected
            for value, expected in (
                (claim_root["prior_result_file_sha256"], prior_result_sha),
                (
                    claim_root["prior_finalization_file_sha256"],
                    prior_finalization_sha,
                ),
                (evidence_root["prior_result_file_sha256"], prior_result_sha),
                (
                    evidence_root["prior_finalization_file_sha256"],
                    prior_finalization_sha,
                ),
                (finalization_root["prior_result_file_sha256"], prior_result_sha),
                (
                    finalization_root["prior_finalization_file_sha256"],
                    prior_finalization_sha,
                ),
            )
        ):
            raise N4V3ExecutionContractError(
                "N4 V3 target does not bind the exact MAP result/finalization"
            )

    validate_n4_v3_protocol_evidence(
        evidence_root,
        snapshot=snapshot,
        prior_bundle=prior_bundle,
    )

    if _record_extension_validator is not None:
        _record_extension_validator(
            root_contract,
            snapshot,
            {
                "claim": claim_root,
                "lock": lock_root,
                "evidence": evidence_root,
                "finalization": finalization_root,
            },
        )

    return {
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "attempt_id": attempt_id,
        "state": validated_result["state"],
        "claim_file_sha256": claim_sha,
        "lock_file_sha256": lock_sha,
        "profile_file_sha256": profile_sha,
        "evidence_file_sha256": evidence_sha,
        "observation_file_sha256": observation_sha,
        "finalization_file_sha256": finalization_sha,
        "result_file_sha256": result_sha,
        "prior_result_file_sha256": prior_result_sha,
        "prior_finalization_file_sha256": prior_finalization_sha,
        "result": _snapshot(validated_result),
        "observation": _snapshot(observation_root),
        "execution_evidence_verified": True,
    }


__all__ = [
    "BUNDLE_KIND",
    "CAMPAIGN_ID",
    "CELL_OBSERVATION_FILENAME",
    "CLAIM_KIND",
    "CONTRACT_ID",
    "CONTRACT_KIND",
    "EVIDENCE_FILENAME",
    "EVIDENCE_KIND",
    "EXPECTED_CONTRACT_CANONICAL_SHA256",
    "EXPECTED_CONTRACT_FILE_SHA256",
    "EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256",
    "EXPECTED_P0_CAMPAIGN_FILE_SHA256",
    "EXPECTED_SOURCE_P0_CAMPAIGN_CANONICAL_SHA256",
    "EXPECTED_SOURCE_P0_CAMPAIGN_FILE_SHA256",
    "FIXED_ACTION_KEYS",
    "FIXED_ACTION_SHA256S",
    "FINALIZATION_FILENAME",
    "FINALIZATION_KIND",
    "LOCK_FILENAME",
    "LOCK_KIND",
    "N4V3ExecutionContractError",
    "N4V3ActionSnapshot",
    "OBSERVATION_FILENAME",
    "OBSERVATION_KIND",
    "P0_RESULT_FILENAME",
    "PROFILE_FILENAME",
    "RUNNER_KIND",
    "compile_n4_v3_execution_contract",
    "build_n4_v3_target_protocol_contract",
    "execution_contract_file_sha256",
    "load_n4_v3_action_snapshot",
    "validate_n4_v3_finalized_action_bundle",
    "validate_n4_v3_protocol_evidence",
    "validate_n4_v3_execution_contract",
]
