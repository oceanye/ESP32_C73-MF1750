#!/usr/bin/env python3
"""Fail-closed exact-plan and finalized-bundle contract for N3.

The frozen N3A manifest is a decision tree, not an executable campaign.  An
N3A exact plan can only be compiled after the N2P analyzer has deep-validated
all eight finalized bundles and selected one unique winner; the caller then
chooses exactly one repeat count (2, 3, or 4).  N3B always selects the four
frozen Williams blocks (32 actions).  Neither path can turn the 72 N3A branch
actions into one serial campaign.

This module performs no HTTP, serial, GPIO, firmware, claim, authorization, or
device I/O.  It is the shared compiler/verifier used by the once runner and the
offline analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from host.epd_frame import ControllerMapping, controller_stream, fnv1a, validate_frame
from host.visible_refresh_campaign import (
    CLAIM_REGISTRY_ID,
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
    describe_action_offline,
    result_file_sha256,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
)
from tools import g1_s1_n3_campaign as planning
from tools import g1_s1_rc2g_map_baseline_once as _map
from tools import g1_s1_rc2g_n2_photo_campaign_analyzer as _n2_analyzer
from tools import g1_s1_rc2g_n2_photo_campaign_once as _n2_fixed
from tools import g1_s1_rc2g_quality_refresh_once as _quality


SCHEMA_VERSION = 1
PLAN_KIND = "mf1750-g1-s1-n3-exact-execution-plan"
RUNNER_KIND = "mf1750-g1-s1-rc2g-n3-fixed-action-runner"
CLAIM_KIND = "mf1750-visible-refresh-fixed-action-consumed-claim"
LOCK_KIND = "mf1750-g1-s1-rc2g-n3-fixed-action-lock"
EVIDENCE_KIND = "mf1750-g1-s1-rc2g-n3-action-evidence"
OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n3-action-observation"
FINALIZATION_KIND = "mf1750-g1-s1-rc2g-n3-action-finalization"
BUNDLE_KIND = "mf1750-g1-s1-rc2g-n3-finalized-action-bundle"

LOCK_FILENAME = "ATTEMPT-LOCK.json"
PROFILE_FILENAME = "REVIEWED-LIMIT-PROFILE.json"
EVIDENCE_FILENAME = "N3-ACTION-EVIDENCE.json"
OBSERVATION_FILENAME = "N3-ACTION-OBSERVATION.json"
FINALIZATION_FILENAME = "N3-ACTION-FINALIZATION.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
SESSION_OBSERVATION_FILENAME = "N3-SESSION-OBSERVATION.json"
CAMERA_CAPTURE_FILENAME = "N3-CAMERA-CAPTURE.bin"

AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N3_FIXED_ACTION__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PLAN_HASH_SCOPE = (
    "entire N3 exact execution plan excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)

EXPECTED_SOURCE_N3A_CANONICAL_SHA256 = (
    planning.EXPECTED_FROZEN_N3A_CANONICAL_SHA256
)
EXPECTED_SOURCE_N3A_FILE_SHA256 = planning.EXPECTED_FROZEN_N3A_FILE_SHA256
EXPECTED_SOURCE_N3B_CANONICAL_SHA256 = (
    planning.EXPECTED_FROZEN_N3B_CANONICAL_SHA256
)
EXPECTED_SOURCE_N3B_FILE_SHA256 = planning.EXPECTED_FROZEN_N3B_FILE_SHA256
EXPECTED_DEFAULT_N3B_PLAN_CANONICAL_SHA256 = (
    "1fdb1d32513383a34bfd589fe3ef3953619545b335a5078d8342755865f65de0"
)
EXPECTED_DEFAULT_N3B_PLAN_FILE_SHA256 = (
    "9bbcaddb27b1c4ddc22c898cc38872b3f07935b292710e95098f61c045fcdec8"
)

_BUNDLE_RECORDS = (
    "claim",
    "lock",
    "profile",
    "evidence",
    "observation",
    "finalization",
    "result",
)
TIMING_FIELDS = {
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
_VALIDATED_PLAN_CACHE: dict[str, tuple[bytes, Mapping[str, Any]]] = {}


class N3ExecutionContractError(ValueError):
    """An N3 exact plan or finalized evidence chain failed closed."""


@dataclass(frozen=True)
class N3ActionSnapshot:
    plan: Mapping[str, Any]
    key: str
    cell_id: str
    candidate_cell_id: str
    phase: str
    campaign: Mapping[str, Any]
    action: Mapping[str, Any]
    route: Mapping[str, Any]
    frame: bytes
    reference_preview: Mapping[str, Any]


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3ExecutionContractError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": PLAN_HASH_SCOPE,
    }


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N3ExecutionContractError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        extra = sorted(set(value) - keys)
        raise N3ExecutionContractError(
            f"{label} keys changed; missing={missing}, extra={extra}"
        )
    return value


def _require_sha256(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[str]:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        suffix = " or null" if nullable else ""
        raise N3ExecutionContractError(
            f"{label} must be 64 lowercase hexadecimal digits{suffix}"
        )
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
        raise N3ExecutionContractError(f"{label} must be a finite number{suffix}")
    result = float(value)
    if not math.isfinite(result):
        raise N3ExecutionContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N3ExecutionContractError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N3ExecutionContractError(f"{label} is above {maximum}")
    return result


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise N3ExecutionContractError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N3ExecutionContractError(f"{label} is not valid RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N3ExecutionContractError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def _frozen_n3a() -> Mapping[str, Any]:
    root = planning.compile_frozen_n3a_manifest()
    planning.validate_n3a_manifest(root)
    if (
        root["integrity"]["canonical_sha256"]
        != EXPECTED_SOURCE_N3A_CANONICAL_SHA256
        or _sha256(root) != EXPECTED_SOURCE_N3A_FILE_SHA256
    ):
        raise N3ExecutionContractError("frozen N3A planning identity changed")
    return _snapshot(root)


@lru_cache(maxsize=1)
def _frozen_n3b() -> Mapping[str, Any]:
    root = planning.compile_frozen_n3b_manifest()
    planning.validate_n3b_manifest(root)
    if (
        root["integrity"]["canonical_sha256"]
        != EXPECTED_SOURCE_N3B_CANONICAL_SHA256
        or _sha256(root) != EXPECTED_SOURCE_N3B_FILE_SHA256
    ):
        raise N3ExecutionContractError("frozen N3B planning identity changed")
    return _snapshot(root)


def _source_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": manifest["kind"],
        "canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "file_sha256": _sha256(manifest),
        "planning_tree_modified": False,
        "compiler_is_only_action_frame_job_source": True,
    }


def _campaign_contexts(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    if manifest["kind"] == planning.N3A_KIND:
        for branch in manifest["branches"]:
            for template in branch["repeat_templates"]:
                contexts.append(
                    {
                        "branch_id": branch["branch_id"],
                        "template_id": template["template_id"],
                        "repeat_count": template["repeat_count"],
                        "block_index": None,
                        "campaign": template["p0_campaign"],
                        "routes": template["routes"],
                    }
                )
    else:
        for branch in manifest["branches"]:
            contexts.append(
                {
                    "branch_id": branch["branch_id"],
                    "template_id": None,
                    "repeat_count": None,
                    "block_index": branch["block_index"],
                    "campaign": branch["p0_campaign"],
                    "routes": branch["routes"],
                }
            )
    return contexts


def _selected_contexts(
    manifest: Mapping[str, Any], selection: Mapping[str, Any]
) -> list[dict[str, Any]]:
    contexts = _campaign_contexts(manifest)
    if manifest["kind"] == planning.N3A_KIND:
        selected = [
            context
            for context in contexts
            if context["branch_id"] == selection["branch_id"]
            and context["template_id"] == selection["template_id"]
            and context["repeat_count"] == selection["repeat_count"]
        ]
        if len(selected) != 1:
            raise N3ExecutionContractError(
                "N3A selection does not identify exactly one repeat template"
            )
        return selected
    if len(contexts) != 4:
        raise N3ExecutionContractError("N3B exact plan requires four balanced blocks")
    return contexts


def _route_records(contexts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for context in contexts:
        campaign = validate_campaign_contract(context["campaign"])
        actions = {
            action["action_identity_sha256"]: action for action in campaign["actions"]
        }
        for route in context["routes"]:
            map_action = actions[route["map_action_identity_sha256"]]
            target_action = actions[route["target_action_identity_sha256"]]
            records.append(
                {
                    "branch_id": context["branch_id"],
                    "template_id": context["template_id"],
                    "repeat_count": context["repeat_count"],
                    "repeat_ordinal": route.get("repeat_ordinal"),
                    "block_index": context["block_index"],
                    "session_position": route.get("session_position"),
                    "candidate_cell_id": route.get(
                        "winner_cell_id", route.get("candidate_cell_id")
                    ),
                    "campaign_id": campaign["campaign_id"],
                    "p0_campaign_canonical_sha256": campaign["integrity"][
                        "canonical_sha256"
                    ],
                    "session_id": route["session_id"],
                    "cell_id": route["cell_id"],
                    "map_action_key": map_action["identity"]["action_id"],
                    "map_action_identity_sha256": map_action[
                        "action_identity_sha256"
                    ],
                    "target_action_key": target_action["identity"]["action_id"],
                    "target_action_identity_sha256": target_action[
                        "action_identity_sha256"
                    ],
                }
            )
    return records


def _fixed_actions(routes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for route in routes:
        for phase in ("map", "target"):
            key = route[f"{phase}_action_key"]
            result[key] = {
                "action_identity_sha256": route[
                    f"{phase}_action_identity_sha256"
                ],
                "phase": "map-primer" if phase == "map" else "target",
                "cell_id": route["cell_id"],
                "candidate_cell_id": route["candidate_cell_id"],
                "campaign_id": route["campaign_id"],
                "p0_campaign_canonical_sha256": route[
                    "p0_campaign_canonical_sha256"
                ],
                "prior_action_key": route["map_action_key"] if phase == "target" else None,
            }
    if len(result) != 2 * len(routes):
        raise N3ExecutionContractError("N3 exact plan action keys are not globally unique")
    return result


def _power_semantics() -> dict[str, Any]:
    return {
        "runner_controls_power_or_j2": False,
        "controller_fresh_boot_required_before_each_map": True,
        "ordinary_session_requires_j2_cycle": False,
        "j2_may_remain_on_between_sessions": True,
        "same_session_map_to_target_forbids": [
            "controller_reboot",
            "panel_power_cycle",
            "j2_disconnect",
            "other_visible_refresh",
        ],
        "power_off_only_at_campaign_end_abnormality_or_before_firmware_config_change": True,
    }


def _evidence_contract() -> dict[str, Any]:
    return {
        "workspace_global_claim_before_network": True,
        "maximum_post_requests_per_action": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "target_requires_same_route_finalized_map_pass": True,
        "target_binds_prior_result_and_finalization_whole_file_sha256": True,
        "manual_finalization_required": True,
        "visual_electrical_thermal_continuity_separate": True,
        "target_camera_capture_required": True,
        "analyzer_input": "deep-finalized-map-target-bundles-only",
    }


def _selection_from_n2_analysis(
    n2_analysis: Mapping[str, Any], repeat_count: int
) -> dict[str, Any]:
    if repeat_count not in planning.N3A_REPEAT_COUNTS:
        raise N3ExecutionContractError("N3A repeat_count must be exactly 2, 3, or 4")
    try:
        analysis = _n2_analyzer.validate_n2p_analysis(n2_analysis)
    except (ValueError, RuntimeError) as error:
        raise N3ExecutionContractError(
            f"N2 analyzer selection evidence is invalid: {error}"
        ) from error
    winner = analysis.get("selected_winner")
    gates = analysis.get("winner_gates")
    if (
        not isinstance(winner, Mapping)
        or not isinstance(gates, Mapping)
        or gates.get("all_pass") is not True
        or winner.get("cell_id") not in planning.N3_CELLS
        or winner.get("authorized_use") != "N3_branch_selection_only"
        or winner.get("algorithm_qualified") is not False
        or winner.get("population_inference") is not False
    ):
        raise N3ExecutionContractError(
            "N3A requires one deep-validated, unique, all-gates-PASS N2 winner"
        )
    cell = str(winner["cell_id"])
    return {
        "selection_type": "deep-n2-unique-winner-plus-manual-repeat-count",
        "winner_cell_id": cell,
        "winner_identity_sha256": winner["winner_identity_sha256"],
        "repeat_count": repeat_count,
        "branch_id": f"n3a-winner-{cell.lower()}",
        "template_id": f"n3a-{cell.lower()}-repeat{repeat_count}",
        "n2_analysis": _snapshot(analysis),
        "n2_analysis_file_sha256": _sha256(analysis),
        "n2_deep_bundle_validation_performed": True,
        "manual_repeat_selection_performed": True,
        "tie_or_null_winner_allowed": False,
    }


def _n3b_selection() -> dict[str, Any]:
    return {
        "selection_type": "frozen-four-block-williams-plan",
        "fixed_seed": planning.N3B_FIXED_SEED,
        "branch_ids": [f"n3b-balanced-block-{index}" for index in range(1, 5)],
        "block_count": 4,
        "route_count": 16,
        "action_count": 32,
        "all_blocks_required": True,
        "previous_target_used_as_prior": False,
        "direct_target_carryover_reserved_for": "N8",
    }


def _compile_plan(
    *,
    source: Mapping[str, Any],
    execution_manifest: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    contexts = _selected_contexts(execution_manifest, selection)
    routes = _route_records(contexts)
    actions = _fixed_actions(routes)
    study = execution_manifest["study"]
    plan_id = (
        f"g1-s1-n3a-{selection['winner_cell_id'].lower()}-repeat"
        f"{selection['repeat_count']}-exact-v1"
        if study == "N3A"
        else "g1-s1-n3b-four-block-williams-exact-v1"
    )
    asset_blockers = planning.measurement_asset_blockers(
        execution_manifest["measurement_asset_registry"]
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "plan_id": plan_id,
        "study": study,
        "source_manifest": _source_identity(source),
        "execution_manifest": _snapshot(execution_manifest),
        "execution_manifest_file_sha256": _sha256(execution_manifest),
        "selection": _snapshot(selection),
        "selected_routes": routes,
        "fixed_actions": actions,
        "power_semantics": _power_semantics(),
        "evidence_contract": _evidence_contract(),
        "readiness": {
            "exact_plan_compiled": True,
            "measurement_asset_blockers": asset_blockers,
            "measurement_assets_ready": not asset_blockers,
            "reviewed_limit_profiles_evaluated_at_runtime": False,
            "hardware_ready": False,
            "blockers": [
                *asset_blockers,
                "reviewed_supplier_limit_profile_not_evaluated",
                "current_runtime_gates_and_exact_authorization_not_evaluated",
            ],
        },
        "classification": {
            "offline_compiled": True,
            "software_ready": True,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "authorization_created": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    plan = {**unsigned, "integrity": _integrity(unsigned)}
    validate_n3_exact_plan(plan)
    return plan


def compile_n3a_exact_plan(
    *,
    n2_result_directories: Mapping[str, Path],
    repeat_count: int,
    measurement_assets: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Deep-analyze N2 bundles, then select exactly one N3A template."""

    try:
        n2_analysis = _n2_analyzer.analyze_n2p_campaign(n2_result_directories)
    except (ValueError, RuntimeError, OSError) as error:
        raise N3ExecutionContractError(
            f"N2 deep bundle analysis did not produce an N3A selection: {error}"
        ) from error
    return _compile_n3a_exact_plan_from_validated_analysis(
        n2_analysis=n2_analysis,
        repeat_count=repeat_count,
        measurement_assets=measurement_assets,
    )


def _compile_n3a_exact_plan_from_validated_analysis(
    *,
    n2_analysis: Mapping[str, Any],
    repeat_count: int,
    measurement_assets: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Internal seam used after the mandatory N2 deep analyzer returns."""

    source = _frozen_n3a()
    selection = _selection_from_n2_analysis(n2_analysis, repeat_count)
    execution_manifest = planning.compile_n3a_manifest(
        panel=source["panel"],
        firmware=source["firmware"],
        measurement_assets=(
            source["measurement_asset_registry"]
            if measurement_assets is None
            else measurement_assets
        ),
    )
    return _compile_plan(
        source=source,
        execution_manifest=execution_manifest,
        selection=selection,
    )


def compile_n3b_exact_plan(
    *, measurement_assets: Optional[Mapping[str, Any]] = None
) -> dict[str, Any]:
    """Compile the exact four-block/32-action N3B plan."""

    source = _frozen_n3b()
    execution_manifest = planning.compile_n3b_manifest(
        panel=source["panel"],
        firmware=source["firmware"],
        measurement_assets=(
            source["measurement_asset_registry"]
            if measurement_assets is None
            else measurement_assets
        ),
    )
    return _compile_plan(
        source=source,
        execution_manifest=execution_manifest,
        selection=_n3b_selection(),
    )


def validate_n3_exact_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        input_payload = canonical_json_bytes(plan)
    except CampaignContractError as error:
        raise N3ExecutionContractError(f"N3 exact plan is not canonical data: {error}") from error
    input_digest = _sha256(input_payload)
    cached = _VALIDATED_PLAN_CACHE.get(input_digest)
    if cached is not None and cached[0] == input_payload:
        return _snapshot(cached[1])
    root = _exact(
        plan,
        label="N3 exact execution plan",
        keys={
            "schema_version",
            "kind",
            "plan_id",
            "study",
            "source_manifest",
            "execution_manifest",
            "execution_manifest_file_sha256",
            "selection",
            "selected_routes",
            "fixed_actions",
            "power_semantics",
            "evidence_contract",
            "readiness",
            "classification",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != PLAN_KIND
        or root["study"] not in {"N3A", "N3B"}
        or not isinstance(root["plan_id"], str)
        or not root["plan_id"]
    ):
        raise N3ExecutionContractError("N3 exact plan identity is invalid")
    source = _frozen_n3a() if root["study"] == "N3A" else _frozen_n3b()
    if root["source_manifest"] != _source_identity(source):
        raise N3ExecutionContractError("N3 exact plan source identity changed")
    manifest = root["execution_manifest"]
    try:
        if root["study"] == "N3A":
            planning.validate_n3a_manifest(manifest)
        else:
            planning.validate_n3b_manifest(manifest)
    except planning.N3CampaignError as error:
        raise N3ExecutionContractError(f"N3 execution manifest is invalid: {error}") from error
    if (
        root["execution_manifest_file_sha256"] != _sha256(manifest)
        or manifest["panel"] != source["panel"]
        or manifest["firmware"] != source["firmware"]
        or manifest["session_regime"] != source["session_regime"]
        or manifest["schedule"] != source["schedule"]
    ):
        raise N3ExecutionContractError("N3 execution manifest binding changed")
    # Measurement assets are the only permitted outer-manifest substitution.
    expected_manifest = (
        planning.compile_n3a_manifest(
            panel=source["panel"],
            firmware=source["firmware"],
            measurement_assets=manifest["measurement_asset_registry"],
        )
        if root["study"] == "N3A"
        else planning.compile_n3b_manifest(
            panel=source["panel"],
            firmware=source["firmware"],
            measurement_assets=manifest["measurement_asset_registry"],
        )
    )
    if manifest != expected_manifest:
        raise N3ExecutionContractError(
            "N3 execution manifest changed outside measurement asset registration"
        )
    selection = root["selection"]
    if root["study"] == "N3A":
        expected_selection = _selection_from_n2_analysis(
            selection.get("n2_analysis"), selection.get("repeat_count")
        )
    else:
        expected_selection = _n3b_selection()
    if selection != expected_selection:
        raise N3ExecutionContractError("N3 exact plan selection evidence changed")
    routes = _route_records(_selected_contexts(manifest, selection))
    actions = _fixed_actions(routes)
    expected_plan_id = (
        f"g1-s1-n3a-{selection['winner_cell_id'].lower()}-repeat"
        f"{selection['repeat_count']}-exact-v1"
        if root["study"] == "N3A"
        else "g1-s1-n3b-four-block-williams-exact-v1"
    )
    if (
        root["plan_id"] != expected_plan_id
        or root["selected_routes"] != routes
        or root["fixed_actions"] != actions
        or root["power_semantics"] != _power_semantics()
        or root["evidence_contract"] != _evidence_contract()
    ):
        raise N3ExecutionContractError("N3 selected route/action contract changed")
    asset_blockers = planning.measurement_asset_blockers(
        manifest["measurement_asset_registry"]
    )
    expected_readiness = {
        "exact_plan_compiled": True,
        "measurement_asset_blockers": asset_blockers,
        "measurement_assets_ready": not asset_blockers,
        "reviewed_limit_profiles_evaluated_at_runtime": False,
        "hardware_ready": False,
        "blockers": [
            *asset_blockers,
            "reviewed_supplier_limit_profile_not_evaluated",
            "current_runtime_gates_and_exact_authorization_not_evaluated",
        ],
    }
    expected_classification = {
        "offline_compiled": True,
        "software_ready": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if (
        root["readiness"] != expected_readiness
        or root["classification"] != expected_classification
        or integrity != _integrity(unsigned)
    ):
        raise N3ExecutionContractError("N3 plan readiness/classification/integrity changed")
    if (
        root["study"] == "N3B"
        and manifest["measurement_asset_registry"]
        == source["measurement_asset_registry"]
        and (
            root["integrity"]["canonical_sha256"]
            != EXPECTED_DEFAULT_N3B_PLAN_CANONICAL_SHA256
            or _sha256(root) != EXPECTED_DEFAULT_N3B_PLAN_FILE_SHA256
        )
    ):
        raise N3ExecutionContractError("default N3B exact plan identity changed")
    validated = _snapshot(root)
    _VALIDATED_PLAN_CACHE[input_digest] = (input_payload, validated)
    return _snapshot(validated)


def exact_plan_file_sha256(plan: Mapping[str, Any]) -> str:
    return _sha256(validate_n3_exact_plan(plan))


def _campaign_for_action(
    plan: Mapping[str, Any], action_record: Mapping[str, Any]
) -> Mapping[str, Any]:
    matches = [
        context["campaign"]
        for context in _campaign_contexts(plan["execution_manifest"])
        if context["campaign"]["campaign_id"] == action_record["campaign_id"]
    ]
    if len(matches) != 1:
        raise N3ExecutionContractError("N3 action campaign is not unique")
    campaign = validate_campaign_contract(matches[0])
    if (
        campaign["integrity"]["canonical_sha256"]
        != action_record["p0_campaign_canonical_sha256"]
    ):
        raise N3ExecutionContractError("N3 action P0 campaign binding changed")
    return campaign


@lru_cache(maxsize=5)
def _source_action_snapshot(source_key: str) -> Any:
    try:
        return _n2_fixed._load_action_snapshot(source_key)
    except (ValueError, RuntimeError, OSError) as error:
        raise N3ExecutionContractError(
            f"frozen N2 frame source validation failed: {error}"
        ) from error


def load_n3_action_snapshot(
    plan: Mapping[str, Any], action_key: str
) -> N3ActionSnapshot:
    root = validate_n3_exact_plan(plan)
    if not isinstance(action_key, str) or action_key not in root["fixed_actions"]:
        raise N3ExecutionContractError("action_key is not in the exact N3 plan")
    fixed = root["fixed_actions"][action_key]
    campaign = _campaign_for_action(root, fixed)
    matches = [
        action
        for action in campaign["actions"]
        if action["action_identity_sha256"] == fixed["action_identity_sha256"]
    ]
    if len(matches) != 1:
        raise N3ExecutionContractError("selected N3 action is not unique")
    action = matches[0]
    route_matches = [
        route
        for route in root["selected_routes"]
        if action_key in {route["map_action_key"], route["target_action_key"]}
    ]
    if len(route_matches) != 1:
        raise N3ExecutionContractError("selected N3 action route is not unique")
    route = route_matches[0]
    source_key = (
        "q1-map-primer"
        if fixed["phase"] == "map-primer"
        else f"{fixed['candidate_cell_id'].lower()}-target"
    )
    source = _source_action_snapshot(source_key)
    frame = source.frame
    frame_record = action["identity"]["frame"]
    actual_controllers = []
    for controller in frame_record["controllers"]:
        mapping = controller["mapping"]
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
    try:
        validate_frame(frame)
    except ValueError as error:
        raise N3ExecutionContractError(f"selected N3 frame is invalid: {error}") from error
    if (
        _sha256(frame) != frame_record["sha256"]
        or f"0x{fnv1a(frame):08X}" != frame_record["fnv1a"]
        or actual_controllers
        != [
            {
                "dtm_sha256": item["dtm_sha256"],
                "dtm_fnv1a": item["dtm_fnv1a"],
            }
            for item in frame_record["controllers"]
        ]
    ):
        raise N3ExecutionContractError("selected N3 frame/DTM identity changed")
    return N3ActionSnapshot(
        plan=root,
        key=action_key,
        cell_id=fixed["cell_id"],
        candidate_cell_id=fixed["candidate_cell_id"],
        phase=fixed["phase"],
        campaign=campaign,
        action=action,
        route=route,
        frame=frame,
        reference_preview=_snapshot(source.reference_preview),
    )


def build_n3_target_protocol_contract(snapshot: N3ActionSnapshot) -> _quality._RunContract:
    if snapshot.phase != "target":
        raise N3ExecutionContractError("target protocol contract requested for MAP")
    actions = {
        action["action_identity_sha256"]: action
        for action in snapshot.campaign["actions"]
    }
    prior_sha = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    prior = actions.get(prior_sha)
    if prior is None:
        raise N3ExecutionContractError("N3 target prior MAP action is missing")
    prior_frame = prior["identity"]["frame"]
    target_frame = snapshot.action["identity"]["frame"]
    candidate = _quality._CandidateSnapshot(
        directory=Path.cwd(),
        manifest={
            "kind": "mf1750-g1-s1-n3-runtime-snapshot",
            "plan_id": snapshot.plan["plan_id"],
            "action_key": snapshot.key,
        },
        manifest_bytes=b"",
        manifest_file_sha256=snapshot.plan["execution_manifest_file_sha256"],
        manifest_canonical_sha256=snapshot.plan["execution_manifest"]["integrity"][
            "canonical_sha256"
        ],
        algorithm=str(snapshot.candidate_cell_id),
        frame=snapshot.frame,
        frame_sha256=target_frame["sha256"],
        frame_fnv1a=int(target_frame["fnv1a"], 16),
        controllers=tuple(target_frame["controllers"]),
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
        required_authorization_confirmation="bound-by-N3-runner-not-protocol-validator",
    )


def validate_n3_protocol_evidence(
    evidence: Mapping[str, Any],
    *,
    snapshot: N3ActionSnapshot,
    prior_bundle: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    """Replay the audited RC2G validators over stored protocol evidence."""

    protocol = evidence.get("protocol_evidence")
    if not isinstance(protocol, Mapping):
        raise N3ExecutionContractError("N3 protocol evidence is missing")
    try:
        if snapshot.phase == "map-primer":
            root = _exact(
                protocol,
                label="N3 MAP protocol evidence",
                keys={"fresh_boot_preflight", "completed_map_evidence"},
            )
            fresh = _exact(
                root["fresh_boot_preflight"],
                label="N3 MAP fresh-boot evidence",
                keys={
                    "version",
                    "job_raw",
                    "diagnostic_raw",
                    "gpio_status_raw",
                    "busy_after_rst_low_is_informational",
                },
            )
            _map._validate_version(fresh["version"], label="N3 stored fresh boot")
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
                raise N3ExecutionContractError(
                    "N3 stored preflight is not fresh job0/operation0"
                )
            _map._validate_gpio_snapshot(
                fresh["gpio_status_raw"], label="N3 stored fresh-boot GPIO"
            )
            if fresh["busy_after_rst_low_is_informational"] is not True:
                raise N3ExecutionContractError(
                    "N3 stored fresh-boot BUSY interpretation changed"
                )
            completed = root["completed_map_evidence"]
            if not isinstance(completed, Mapping):
                raise N3ExecutionContractError("N3 completed MAP evidence is missing")
            rebuilt = _map._validate_completed_map_evidence(
                completed.get("network_report"),
                completed.get("job_raw"),
                completed.get("diagnostic_raw"),
                completed.get("gpio_status_raw"),
                snapshot.frame,
            )
            if rebuilt != completed:
                raise N3ExecutionContractError(
                    "N3 stored MAP protocol derived fields changed"
                )
            if prior_bundle is not None:
                raise N3ExecutionContractError("N3 MAP protocol must not bind a prior")
            return root

        root = _exact(
            protocol,
            label="N3 target protocol evidence",
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
            raise N3ExecutionContractError(
                "N3 target protocol requires the exact stored MAP bundle"
            )
        prior_evidence = prior_bundle.get("evidence")
        if not isinstance(prior_evidence, Mapping):
            raise N3ExecutionContractError("N3 MAP bundle evidence is missing")
        prior_protocol = prior_evidence.get("protocol_evidence")
        if not isinstance(prior_protocol, Mapping):
            raise N3ExecutionContractError("N3 MAP protocol is missing")
        completed_map = prior_protocol.get("completed_map_evidence")
        if not isinstance(completed_map, Mapping):
            raise N3ExecutionContractError("N3 completed MAP evidence is missing")
        run_contract = build_n3_target_protocol_contract(snapshot)
        live = _exact(
            root["same_cell_primer_live_preflight"],
            label="N3 target live MAP preflight",
            keys={
                "version",
                "job",
                "diagnostic_raw",
                "nested_busy_trace",
                "gpio",
                "expected_identity",
            },
        )
        _quality._validate_version(live["version"], label="N3 stored target prior")
        if (
            live["job"] != completed_map.get("job_raw")
            or live["diagnostic_raw"] != completed_map.get("diagnostic_raw")
            or live["expected_identity"] != snapshot.action["identity"]["prior"]
        ):
            raise N3ExecutionContractError(
                "N3 target live prior is not the exact stored same-session MAP"
            )
        trace = _quality._validate_prior_raw_diagnostic(
            live["diagnostic_raw"], live["job"], run_contract
        )
        if live["nested_busy_trace"] != trace:
            raise N3ExecutionContractError("N3 target prior BUSY trace changed")
        gpio = _exact(
            live["gpio"],
            label="N3 target prior GPIO evidence",
            keys={
                "raw",
                "panel_outputs_low_verified",
                "busy_level",
                "busy_after_rst_low_is_informational",
                "busy_interpretation",
            },
        )
        raw_gpio = _quality._validate_gpio_snapshot(
            gpio["raw"], label="N3 stored target prior GPIO"
        )
        if _quality._gpio_evidence(raw_gpio) != gpio:
            raise N3ExecutionContractError(
                "N3 target prior GPIO derived fields changed"
            )
        report = root["network_report"]
        _quality._validate_network_report(report, run_contract)
        if root["target_job_raw"] != report.get("job"):
            raise N3ExecutionContractError("N3 target immutable job changed")
        normalized = _quality._validate_target_raw_diagnostic(
            root["target_diagnostic_raw"], report, run_contract
        )
        if normalized != root["target_diagnostic_validated"]:
            raise N3ExecutionContractError(
                "N3 target diagnostic derived fields changed"
            )
        gpio_raw = _quality._validate_gpio_snapshot(
            root["post_refresh_gpio_status_raw"],
            label="N3 stored target post-refresh GPIO",
        )
        if gpio_raw != root["post_refresh_gpio_status_raw"]:
            raise N3ExecutionContractError("N3 target GPIO normalization changed")
        return root
    except (_map.Rc2gMapBaselineError, _quality.Rc2gQualityRefreshError) as error:
        raise N3ExecutionContractError(
            f"N3 stored protocol failed audited replay: {error}"
        ) from error


def _registered_asset_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    registry = plan["execution_manifest"]["measurement_asset_registry"]
    return {
        "registry_sha256": plan["execution_manifest"][
            "measurement_asset_registry_sha256"
        ],
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
        "camera_capture_config_sha256": registry["camera"][
            "capture_config_sha256"
        ],
        "camera_crop_asset_sha256": registry["camera"]["crop_asset_sha256"],
        "illumination_asset_sha256": registry["camera"][
            "illumination_asset_sha256"
        ],
    }


def _validate_action_observation(
    observation: Mapping[str, Any],
    *,
    snapshot: N3ActionSnapshot,
    attempt_id: str,
    profile: Mapping[str, Any],
) -> Mapping[str, Any]:
    plan = snapshot.plan
    root = _exact(
        observation,
        label="N3 stored action observation",
        keys={
            "schema_version",
            "kind",
            "plan_canonical_sha256",
            "attempt_id",
            "action_key",
            "cell_id",
            "candidate_cell_id",
            "phase",
            "action_identity_sha256",
            "observed_at",
            "reference_preview_sha256",
            "measurement_assets",
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
        or root["plan_canonical_sha256"]
        != plan["integrity"]["canonical_sha256"]
        or root["attempt_id"] != attempt_id
        or root["action_key"] != snapshot.key
        or root["cell_id"] != snapshot.cell_id
        or root["candidate_cell_id"] != snapshot.candidate_cell_id
        or root["phase"] != snapshot.phase
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or root["reference_preview_sha256"] != snapshot.reference_preview["sha256"]
        or root["measurement_assets"] != _registered_asset_identity(plan)
    ):
        raise N3ExecutionContractError("N3 action observation binding changed")
    _timestamp(root["observed_at"], label="observation.observed_at")
    _require_sha256(
        root["source_observation_file_sha256"], label="source observation file"
    )
    for field, value in root["measurement_assets"].items():
        _require_sha256(value, label=f"N3 registered asset {field}")

    if snapshot.phase == "map-primer":
        visual = _exact(
            root["visual"],
            label="N3 MAP visual observation",
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
            raise N3ExecutionContractError("N3 MAP visual flags must be boolean")
        visual_pass = all(visual.values())
    else:
        visual = _exact(
            root["visual"],
            label="N3 target visual observation",
            keys={
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
                "photo_difference_score",
                "photo_luminance_mean",
                "photo_luminance_standard_deviation",
            },
        )
        for field in (
            "target_fidelity_pass",
            "orientation_pass",
            "seam_assessment_pass",
            "full_panel_inspected",
            "no_retained_old_regions",
        ):
            if type(visual[field]) is not bool:
                raise N3ExecutionContractError(f"N3 target visual {field} must be boolean")
        _number(
            visual["photo_difference_score"],
            label="visual.photo_difference_score",
            minimum=0,
            nullable=True,
        )
        for field in (
            "photo_luminance_mean",
            "photo_luminance_standard_deviation",
        ):
            _number(
                visual[field],
                label=f"visual.{field}",
                minimum=0,
                maximum=255,
                nullable=True,
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
        label="N3 electrical observation",
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
    _require_sha256(electrical["meter_asset_sha256"], label="N3 meter asset")
    if (
        electrical["clock_asset_sha256"]
        != root["measurement_assets"]["timing_clock_asset_sha256"]
    ):
        raise N3ExecutionContractError("N3 timing clock differs from registered asset")
    for field in (
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
    ):
        _number(electrical[field], label=f"electrical.{field}", minimum=0)
    if any(
        type(electrical[field]) is not bool
        for field in ("constant_voltage_mode", "reviewed_limits_pass")
    ):
        raise N3ExecutionContractError("N3 electrical pass flags must be boolean")
    timing = _exact(
        electrical["timing_ms"], label="N3 action timing", keys=TIMING_FIELDS
    )
    for field, value in timing.items():
        _number(value, label=f"timing_ms.{field}", minimum=0)
    electrical_pass = bool(
        electrical["constant_voltage_mode"] and electrical["reviewed_limits_pass"]
    )

    thermal = _exact(
        root["thermal"],
        label="N3 thermal observation",
        keys={
            "pre_action_c",
            "post_action_c",
            "session_max_c",
            "uncertainty_u95_c",
            "sensor_asset_sha256",
            "calibration_artifact_sha256",
            "measurement_location_asset_sha256",
            "measurement_evidence_sha256",
            "uncertainty_evidence_sha256",
        },
    )
    pre_temperature = _number(thermal["pre_action_c"], label="thermal.pre_action_c")
    post_temperature = _number(
        thermal["post_action_c"], label="thermal.post_action_c"
    )
    session_max = _number(thermal["session_max_c"], label="thermal.session_max_c")
    assert pre_temperature is not None
    assert post_temperature is not None
    assert session_max is not None
    if session_max < max(pre_temperature, post_temperature):
        raise N3ExecutionContractError(
            "N3 session maximum is below an action temperature sample"
        )
    _number(thermal["uncertainty_u95_c"], label="thermal.uncertainty_u95_c", minimum=0)
    expected_thermal_assets = {
        "sensor_asset_sha256": "temperature_sensor_asset_sha256",
        "calibration_artifact_sha256": "temperature_calibration_asset_sha256",
        "measurement_location_asset_sha256": "temperature_location_asset_sha256",
    }
    for field, registered in expected_thermal_assets.items():
        if thermal[field] != root["measurement_assets"][registered]:
            raise N3ExecutionContractError(
                f"N3 thermal {field} differs from registered asset"
            )
    for field in ("measurement_evidence_sha256", "uncertainty_evidence_sha256"):
        _require_sha256(thermal[field], label=f"thermal.{field}")
    maximum_temperature = profile["limits"]["maximum_post_refresh_temperature_c"]
    if maximum_temperature is None:
        raise N3ExecutionContractError("reviewed profile lacks maximum temperature")
    thermal_pass = (
        post_temperature <= maximum_temperature
        and session_max <= maximum_temperature
    )

    if snapshot.phase == "map-primer":
        if root["continuity"] is not None:
            raise N3ExecutionContractError("N3 MAP observation continuity must be null")
        continuity_pass = True
    else:
        continuity = _exact(
            root["continuity"],
            label="N3 MAP-target continuity",
            keys={
                "controller_reboot_between_actions",
                "panel_power_cycle_between_actions",
                "j2_disconnect_between_actions",
                "other_visible_refresh_between_actions",
            },
        )
        if any(type(value) is not bool for value in continuity.values()):
            raise N3ExecutionContractError("N3 continuity fields must be boolean")
        continuity_pass = not any(continuity.values())

    camera = _exact(
        root["camera"],
        label="N3 camera binding",
        keys={
            "capture_performed",
            "capture_file_sha256",
            "copied_file",
            "bytes",
            "decoded_format",
            "width",
            "height",
        },
    )
    if snapshot.phase == "target":
        if camera["capture_performed"] is not True:
            raise N3ExecutionContractError("N3 target requires a registered camera capture")
        _require_sha256(camera["capture_file_sha256"], label="N3 camera capture")
        if (
            camera["copied_file"] != CAMERA_CAPTURE_FILENAME
            or type(camera["bytes"]) is not int
            or camera["bytes"] < 1
            or not isinstance(camera["decoded_format"], str)
            or not camera["decoded_format"]
            or type(camera["width"]) is not int
            or camera["width"] < 1
            or type(camera["height"]) is not int
            or camera["height"] < 1
        ):
            raise N3ExecutionContractError("N3 target camera binding is incomplete")
    elif camera != {
        "capture_performed": False,
        "capture_file_sha256": None,
        "copied_file": None,
        "bytes": None,
        "decoded_format": None,
        "width": None,
        "height": None,
    }:
        raise N3ExecutionContractError("N3 MAP must not imply target camera evidence")

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
        raise N3ExecutionContractError("N3 observation derived verdict changed")
    return root


def _record_and_sha(
    bundle: Mapping[str, Any], name: str
) -> tuple[Mapping[str, Any], str]:
    record = bundle[name]
    if not isinstance(record, Mapping):
        raise N3ExecutionContractError(f"bundle {name} must be an object")
    declared = _require_sha256(
        bundle[f"{name}_file_sha256"], label=f"bundle {name} whole-file SHA-256"
    )
    actual = _sha256(record)
    if declared != actual:
        raise N3ExecutionContractError(
            f"bundle {name} whole-file SHA-256 does not match canonical bytes"
        )
    return record, actual


def _frozen_plan_snapshot_loader(
    plan: Mapping[str, Any], action_key: str
) -> N3ActionSnapshot:
    """Default snapshot seam retained for the frozen legacy exact plan."""

    return load_n3_action_snapshot(plan, action_key)


def _frozen_authorization_confirmation(
    _plan: Mapping[str, Any], snapshot: N3ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def validate_n3_finalized_action_bundle(
    plan: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    expected_action_key: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    _plan_validator: Any = validate_n3_exact_plan,
    _snapshot_loader: Any = _frozen_plan_snapshot_loader,
    _plan_file_sha256: Any = exact_plan_file_sha256,
    _authorization_confirmation: Any = _frozen_authorization_confirmation,
    _record_extra_keys: Optional[Mapping[str, set[str] | frozenset[str]]] = None,
    _record_extension_validator: Any = None,
) -> dict[str, Any]:
    """Deep-validate one canonical N3 runner chain without performing I/O.

    The underscored callables form a fail-closed adapter seam for a separately
    validated physical-bound plan.  Public callers retain the exact frozen
    validators by default.
    """

    root_plan = _plan_validator(plan)
    extra_keys = _record_extra_keys or {}
    root = _exact(
        bundle,
        label="N3 finalized action bundle",
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
        raise N3ExecutionContractError("N3 finalized bundle identity changed")
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
        label="N3 action protocol evidence",
        keys={
            "schema_version",
            "kind",
            "runner_kind",
            "attempt_id",
            "recorded_at",
            "protocol_completed_at",
            "action_key",
            "cell_id",
            "candidate_cell_id",
            "phase",
            "action_identity_sha256",
            "plan_id",
            "plan_canonical_sha256",
            "plan_file_sha256",
            "execution_manifest_canonical_sha256",
            "p0_campaign_canonical_sha256",
            "source_manifest_canonical_sha256",
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
            "protocol_evidence",
            "request_audit",
            "error",
        }
        | set(extra_keys.get("evidence", set())),
    )
    action_key = evidence_root["action_key"]
    if expected_action_key is not None and action_key != expected_action_key:
        raise N3ExecutionContractError("bundle is not the expected N3 action")
    snapshot = _snapshot_loader(root_plan, str(action_key))
    attempt_id = evidence_root["attempt_id"]
    if not isinstance(attempt_id, str) or not attempt_id:
        raise N3ExecutionContractError("N3 attempt_id is invalid")
    recorded_at = _timestamp(evidence_root["recorded_at"], label="evidence.recorded_at")
    evaluated_at = _timestamp(
        evidence_root["profile_evaluated_at"], label="evidence.profile_evaluated_at"
    )
    protocol_completed_at = _timestamp(
        evidence_root["protocol_completed_at"],
        label="evidence.protocol_completed_at",
    )
    if evaluated_at > recorded_at or protocol_completed_at < recorded_at:
        raise N3ExecutionContractError("N3 profile/claim/protocol timestamp order changed")
    if (
        evidence_root["schema_version"] != SCHEMA_VERSION
        or evidence_root["kind"] != EVIDENCE_KIND
        or evidence_root["runner_kind"] != RUNNER_KIND
        or evidence_root["cell_id"] != snapshot.cell_id
        or evidence_root["candidate_cell_id"] != snapshot.candidate_cell_id
        or evidence_root["phase"] != snapshot.phase
        or evidence_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or evidence_root["plan_id"] != root_plan["plan_id"]
        or evidence_root["plan_canonical_sha256"]
        != root_plan["integrity"]["canonical_sha256"]
        or evidence_root["plan_file_sha256"] != _plan_file_sha256(root_plan)
        or evidence_root["execution_manifest_canonical_sha256"]
        != root_plan["execution_manifest"]["integrity"]["canonical_sha256"]
        or evidence_root["p0_campaign_canonical_sha256"]
        != snapshot.campaign["integrity"]["canonical_sha256"]
        or evidence_root["source_manifest_canonical_sha256"]
        != root_plan["source_manifest"]["canonical_sha256"]
        or evidence_root["frame_sha256"]
        != snapshot.action["identity"]["frame"]["sha256"]
        or evidence_root["reference_preview"] != snapshot.reference_preview
        or evidence_root["maximum_post_requests"] != 1
        or evidence_root["automatic_retry_count"] != 0
        or evidence_root["retry_allowed"] is not False
        or evidence_root["recovery_performed"] is not False
        or evidence_root["outcome"] != "protocol_verified_observation_pending"
        or evidence_root["protocol_verified"] is not True
        or evidence_root["error"] is not None
    ):
        raise N3ExecutionContractError("N3 protocol evidence binding changed")

    try:
        validated_profile = validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N3ExecutionContractError(f"N3 reviewed profile is invalid: {error}") from error
    if (
        validated_profile["panel"] != snapshot.campaign["panel"]
        or validated_profile["firmware"] != snapshot.campaign["firmware"]
        or evidence_root["profile_file_sha256"] != profile_sha
        or evidence_root["profile_canonical_sha256"]
        != validated_profile["integrity"]["canonical_sha256"]
    ):
        raise N3ExecutionContractError("N3 reviewed profile binding changed")

    expected_claim_state = "authorization_permanently_consumed_do_not_rerun"
    claim_root = _exact(
        claim,
        label="N3 workspace-global claim",
        keys={
            "schema_version",
            "kind",
            "registry_id",
            "plan_id",
            "plan_canonical_sha256",
            "plan_file_sha256",
            "action_key",
            "action_identity_sha256",
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
    claimed_at = _timestamp(claim_root["claimed_at"], label="claim.claimed_at")
    confirmation_text = _authorization_confirmation(root_plan, snapshot)
    expected_confirmation_sha = _sha256(confirmation_text.encode("ascii"))
    confirmation_keys = {
        "reviewed_panel_build_and_exact_plan",
        "registered_measurement_assets_present",
        "supervised_supply_cv_current_normal",
        "physical_cutoff_available",
        "single_visible_refresh",
        *(
            {"controller_fresh_boot"}
            if snapshot.phase == "map-primer"
            else {
                "map_fidelity_from_same_session_primer",
                "esp32_not_restarted_since_primer",
                "no_j2_disconnect_since_primer",
                "no_panel_power_cycle_since_primer",
                "no_other_visible_refresh_since_primer",
            }
        ),
    }
    confirmations = _exact(
        claim_root["confirmations"],
        label="N3 action physical confirmations",
        keys=confirmation_keys,
    )
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N3ExecutionContractError("all N3 action confirmations must be true")
    if (
        claim_root["schema_version"] != SCHEMA_VERSION
        or claim_root["kind"] != CLAIM_KIND
        or claim_root["registry_id"] != CLAIM_REGISTRY_ID
        or claim_root["plan_id"] != root_plan["plan_id"]
        or claim_root["plan_canonical_sha256"]
        != root_plan["integrity"]["canonical_sha256"]
        or claim_root["plan_file_sha256"] != _plan_file_sha256(root_plan)
        or claim_root["action_key"] != action_key
        or claim_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or claim_root["p0_campaign_canonical_sha256"]
        != snapshot.campaign["integrity"]["canonical_sha256"]
        or claim_root["attempt_id"] != attempt_id
        or claimed_at != recorded_at
        or claim_root["state"] != expected_claim_state
        or claim_root["authorization_consumed_permanently"] is not True
        or claim_root["authorization_confirmation_sha256"]
        != expected_confirmation_sha
        or claim_root["profile_canonical_sha256"]
        != validated_profile["integrity"]["canonical_sha256"]
        or claim_root["profile_file_sha256"] != profile_sha
        or claim_root["maximum_post_requests"] != 1
        or claim_root["automatic_retry_authorized"] is not False
        or claim_root["automatic_recovery_authorized"] is not False
    ):
        raise N3ExecutionContractError("N3 consumed claim binding changed")
    claim_reference = _exact(
        evidence_root["claim"],
        label="N3 claim reference",
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
        "filename": snapshot.action["claim"]["filename"],
        "file_sha256": claim_sha,
        "attempt_id": attempt_id,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "state": expected_claim_state,
    }:
        raise N3ExecutionContractError("N3 claim reference changed")

    lock_root = _exact(
        lock,
        label="N3 action lock",
        keys={
            "schema_version",
            "kind",
            "plan_id",
            "plan_canonical_sha256",
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
        or lock_root["plan_id"] != root_plan["plan_id"]
        or lock_root["plan_canonical_sha256"]
        != root_plan["integrity"]["canonical_sha256"]
        or lock_root["attempt_id"] != attempt_id
        or lock_root["action_key"] != action_key
        or lock_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or lock_root["claim"] != claim_reference
        or lock_root["confirmations"] != confirmations
        or lock_root["authorization_confirmation_sha256"]
        != expected_confirmation_sha
        or lock_root["state"] != expected_claim_state
        or lock_root["automatic_retry_authorized"] is not False
        or lock_root["automatic_recovery_authorized"] is not False
    ):
        raise N3ExecutionContractError("N3 action lock binding changed")

    audit = _exact(
        evidence_root["request_audit"],
        label="N3 request audit",
        keys={"post_attempt_count", "post_issued_count", "calls"},
    )
    calls = audit["calls"]
    posts = (
        [call for call in calls if isinstance(call, Mapping) and call.get("method") == "POST"]
        if isinstance(calls, list)
        else []
    )
    if (
        audit["post_attempt_count"] != 1
        or audit["post_issued_count"] != 1
        or len(posts) != 1
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
        raise N3ExecutionContractError("N3 request audit route/frame/count changed")

    if snapshot.phase == "map-primer":
        if prior_bundle is not None:
            raise N3ExecutionContractError("N3 MAP action must not receive a prior bundle")
        prior_result_sha = None
        prior_finalization_sha = None
        prior_result = None
    else:
        if prior_bundle is None:
            raise N3ExecutionContractError(
                "N3 target requires the exact same-session MAP finalized bundle"
            )
        prior = validate_n3_finalized_action_bundle(
            root_plan,
            prior_bundle,
            expected_action_key=snapshot.route["map_action_key"],
            _plan_validator=_plan_validator,
            _snapshot_loader=_snapshot_loader,
            _plan_file_sha256=_plan_file_sha256,
            _authorization_confirmation=_authorization_confirmation,
            _record_extra_keys=_record_extra_keys,
            _record_extension_validator=_record_extension_validator,
        )
        if prior["state"] != ResultState.PASS.value:
            raise N3ExecutionContractError("N3 target prior MAP is not finalized PASS")
        prior_result_sha = prior["result_file_sha256"]
        prior_finalization_sha = prior["finalization_file_sha256"]
        prior_result = prior_bundle["result"]
    for record in (claim_root, evidence_root):
        if (
            record["prior_result_file_sha256"] != prior_result_sha
            or record["prior_finalization_file_sha256"] != prior_finalization_sha
        ):
            raise N3ExecutionContractError(
                "N3 target/MAP prior result-finalization binding changed"
            )

    try:
        description = describe_action_offline(
            snapshot.campaign,
            action_identity_sha256=snapshot.action["action_identity_sha256"],
            limit_profile=validated_profile,
            evaluated_at=evidence_root["profile_evaluated_at"],
            prior_result=prior_result,
            prior_result_sha256=prior_result_sha,
        )
    except CampaignContractError as error:
        raise N3ExecutionContractError(
            f"N3 stored profile/prior no longer passes P0 describe: {error}"
        ) from error
    if description["contract_ready"] is not True:
        raise N3ExecutionContractError(
            "N3 finalized action was not ready under its stored reviewed profile"
        )
    validate_n3_protocol_evidence(
        evidence_root, snapshot=snapshot, prior_bundle=prior_bundle
    )

    observation_root = _validate_action_observation(
        observation,
        snapshot=snapshot,
        attempt_id=attempt_id,
        profile=validated_profile,
    )
    if _timestamp(
        observation_root["observed_at"], label="observation.observed_at"
    ) < protocol_completed_at:
        raise N3ExecutionContractError("N3 observation predates protocol completion")
    finalization_root = _exact(
        finalization,
        label="N3 action finalization",
        keys={
            "schema_version",
            "kind",
            "plan_id",
            "plan_canonical_sha256",
            "attempt_id",
            "action_key",
            "cell_id",
            "candidate_cell_id",
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
            "visual_electrical_thermal_continuity_assessed_separately",
            "automatic_retry_count",
            "retry_allowed",
            "recovery_performed",
        }
        | set(extra_keys.get("finalization", set())),
    )
    if (
        finalization_root["schema_version"] != SCHEMA_VERSION
        or finalization_root["kind"] != FINALIZATION_KIND
        or finalization_root["plan_id"] != root_plan["plan_id"]
        or finalization_root["plan_canonical_sha256"]
        != root_plan["integrity"]["canonical_sha256"]
        or finalization_root["attempt_id"] != attempt_id
        or finalization_root["action_key"] != action_key
        or finalization_root["cell_id"] != snapshot.cell_id
        or finalization_root["candidate_cell_id"] != snapshot.candidate_cell_id
        or finalization_root["phase"] != snapshot.phase
        or finalization_root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or finalization_root["state"] != observation_root["overall_state"]
        or finalization_root["claim_file_sha256"] != claim_sha
        or finalization_root["lock_file_sha256"] != lock_sha
        or finalization_root["protocol_evidence_file_sha256"] != evidence_sha
        or finalization_root["action_observation_file_sha256"] != observation_sha
        or finalization_root["profile_file_sha256"] != profile_sha
        or finalization_root["prior_result_file_sha256"] != prior_result_sha
        or finalization_root["prior_finalization_file_sha256"]
        != prior_finalization_sha
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
        or finalization_root[
            "visual_electrical_thermal_continuity_assessed_separately"
        ]
        is not True
        or finalization_root["automatic_retry_count"] != 0
        or finalization_root["retry_allowed"] is not False
        or finalization_root["recovery_performed"] is not False
    ):
        raise N3ExecutionContractError("N3 finalization binding changed")

    try:
        validated_result = validate_result_record(result)
    except CampaignContractError as error:
        raise N3ExecutionContractError(f"N3 P0 result is invalid: {error}") from error
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
        raise N3ExecutionContractError("N3 P0 result/finalization binding changed")

    if _record_extension_validator is not None:
        _record_extension_validator(
            root_plan,
            snapshot,
            {
                "claim": claim_root,
                "lock": lock_root,
                "evidence": evidence_root,
                "finalization": finalization_root,
            },
        )

    return {
        "plan_id": root_plan["plan_id"],
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "cell_id": snapshot.cell_id,
        "candidate_cell_id": snapshot.candidate_cell_id,
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
    "AUTHORIZATION_PREFIX",
    "AUTHORIZATION_SUFFIX",
    "BUNDLE_KIND",
    "CAMERA_CAPTURE_FILENAME",
    "CLAIM_KIND",
    "EVIDENCE_FILENAME",
    "EVIDENCE_KIND",
    "EXPECTED_DEFAULT_N3B_PLAN_CANONICAL_SHA256",
    "EXPECTED_DEFAULT_N3B_PLAN_FILE_SHA256",
    "FINALIZATION_FILENAME",
    "FINALIZATION_KIND",
    "LOCK_FILENAME",
    "LOCK_KIND",
    "N3ActionSnapshot",
    "N3ExecutionContractError",
    "OBSERVATION_FILENAME",
    "OBSERVATION_KIND",
    "P0_RESULT_FILENAME",
    "PLAN_KIND",
    "PROFILE_FILENAME",
    "RUNNER_KIND",
    "SCHEMA_VERSION",
    "SESSION_OBSERVATION_FILENAME",
    "TIMING_FIELDS",
    "build_n3_target_protocol_contract",
    "compile_n3a_exact_plan",
    "compile_n3b_exact_plan",
    "exact_plan_file_sha256",
    "load_n3_action_snapshot",
    "validate_n3_exact_plan",
    "validate_n3_finalized_action_bundle",
    "validate_n3_protocol_evidence",
]
