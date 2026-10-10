#!/usr/bin/env python3
"""Compile one offline-only physical N3A exact plan.

The legacy N3 exact-plan compiler consumes the legacy, unbound N2 analyzer.
This module is the separate physical boundary.  An analysis JSON is never a
standalone authority: every public compile/read/validate/publish/describe path
must replay exactly eight finalized physical N2 result directories with the
trusted reviewer key.  The replayed snapshot must exactly equal the supplied
or embedded analysis before its unique winner may select one repeat-2/3/4 N3A
source template.  Every campaign/action/prior/session/claim rewrite is then
delegated to ``physical_rebind``.

Compilation and publication are deliberately offline.  This module contains
no device, HTTP, authorization, claim, retry, recovery, or live-runner path.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    canonical_json_bytes,
    validate_campaign_contract,
)
from host.visible_refresh_campaign import physical_rebind as rebind  # noqa: E402
from host.visible_refresh_campaign import production_profile as production  # noqa: E402
from tools import g1_s1_n2_physical_campaign as n2_physical  # noqa: E402
from tools import g1_s1_n3_campaign as planning  # noqa: E402
from tools import g1_s1_rc2g_n2_physical_analyzer as n2_analyzer  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
PLAN_KIND = "mf1750-g1-s1-n3a-physical-exact-plan"
PLAN_HASH_SCOPE = (
    "entire N3A physical exact plan excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
PLAN_MANIFEST_FILENAME = "N3A-PHYSICAL-PLAN.json"
PHYSICAL_CAMPAIGN_FILENAME = rebind.PHYSICAL_CAMPAIGN_FILENAME
MAX_PLAN_JSON_BYTES = 64 * 1024 * 1024
MAX_INPUT_JSON_BYTES = 32 * 1024 * 1024
MAX_BINDING_REVIEW_BYTES = rebind.MAX_BINDING_REVIEW_BYTES

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "plan_id",
        "study",
        "n2_physical_analysis",
        "n2_physical_provenance",
        "physical_operator_manifest",
        "selection",
        "source_n3a_manifest",
        "source_n3a_manifest_file_sha256",
        "selected_source",
        "physical_rebind",
        "physical_campaign_file",
        "selected_routes",
        "fixed_actions",
        "measurement_asset_registry",
        "measurement_asset_contract",
        "process_schedule",
        "identity_rebind_contract",
        "power_semantics",
        "evidence_contract",
        "readiness",
        "classification",
        "integrity",
    }
)
_ASSET_PATHS = (
    ("timing", "clock_asset_sha256"),
    ("temperature", "sensor_asset_sha256"),
    ("temperature", "calibration_asset_sha256"),
    ("temperature", "measurement_location_asset_sha256"),
    ("camera", "body_asset_sha256"),
    ("camera", "lens_asset_sha256"),
    ("camera", "mount_asset_sha256"),
    ("camera", "capture_config_sha256"),
    ("camera", "crop_asset_sha256"),
    ("camera", "illumination_asset_sha256"),
)

_VALIDATED_OPERATOR_CACHE: dict[str, tuple[bytes, Mapping[str, Any]]] = {}
_SOURCE_MANIFEST_CACHE: dict[str, tuple[bytes, Mapping[str, Any]]] = {}


class N3APhysicalPlanError(ValueError):
    """A physical N3A selection, lineage, plan, or publication failed closed."""


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3APhysicalPlanError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3APhysicalPlanError(
            f"value could not be snapshotted as canonical JSON: {error}"
        ) from error


def _exact(value: Any, *, label: str, keys: set[str] | frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N3APhysicalPlanError(f"{label} must be an object")
    if set(value) != set(keys):
        missing = sorted(set(keys) - set(value))
        extra = sorted(set(value) - set(keys))
        raise N3APhysicalPlanError(
            f"{label} fields changed; missing={missing}, extra={extra}"
        )
    return value


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": PLAN_HASH_SCOPE,
    }


def _schedule_values(
    minimum_interval_seconds: Any, planned_cooldown_seconds: Any
) -> tuple[float, float]:
    for value, label in (
        (minimum_interval_seconds, "minimum_interval_seconds"),
        (planned_cooldown_seconds, "planned_cooldown_seconds"),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise N3APhysicalPlanError(
                f"{label} must be an explicit finite numeric operator input"
            )
    interval = float(minimum_interval_seconds)
    cooldown = float(planned_cooldown_seconds)
    if interval <= 0:
        raise N3APhysicalPlanError(
            "minimum_interval_seconds must be an explicit positive finite number"
        )
    if cooldown < 0:
        raise N3APhysicalPlanError(
            "planned_cooldown_seconds must be an explicit non-negative finite number"
        )
    return interval, cooldown


def _replay_n2_physical_analysis(
    result_directories: Mapping[str, Path], *, reviewer_key_file: Path
) -> Mapping[str, Any]:
    """Replay all eight finalized chains; never trust an analysis seal alone."""

    if not isinstance(result_directories, Mapping) or set(result_directories) != set(
        n2_analyzer.EXPECTED_RESULT_KEYS
    ):
        raise N3APhysicalPlanError(
            "N3A provenance requires exactly the eight finalized physical N2 "
            "result directories"
        )
    if not isinstance(reviewer_key_file, Path):
        raise N3APhysicalPlanError("trusted reviewer_key_file must be pathlib.Path")
    try:
        replayed = n2_analyzer.analyze_n2p_physical_campaign(
            result_directories,
            reviewer_key_file=reviewer_key_file,
        )
    except (n2_analyzer.N2PhysicalAnalysisError, ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalPlanError(
            f"finalized physical N2 evidence replay failed: {error}"
        ) from error
    analysis = _snapshot(replayed)
    if any(
        analysis[field] is not False
        for field in (
            "hardware_io_performed",
            "network_io_performed",
            "claim_created",
            "authorization_created",
        )
    ):
        raise N3APhysicalPlanError(
            "physical N2 evidence replay reported a forbidden side effect"
        )
    return analysis


def _require_exact_replayed_analysis(
    provided: Mapping[str, Any], replayed: Mapping[str, Any], *, label: str
) -> Mapping[str, Any]:
    if _canonical(provided) != _canonical(replayed):
        raise N3APhysicalPlanError(
            f"{label} does not exactly match the analysis rebuilt from all eight "
            "finalized physical N2 result directories"
        )
    # Only the analyzer return value crosses the trust boundary.  The supplied
    # JSON is used for byte equality and is never re-read as selection input.
    return _snapshot(replayed)


def _n2_physical_provenance(analysis: Mapping[str, Any]) -> dict[str, Any]:
    source = analysis["source_binding"]
    lineage = source["profile_lineage"]
    chains = []
    for expected_key, chain in zip(
        n2_analyzer.EXPECTED_RESULT_KEYS, analysis["validated_chains"]
    ):
        if chain["action_key"] != expected_key:
            raise N3APhysicalPlanError(
                "replayed physical N2 chain order differs from the exact eight-action set"
            )
        profile = chain["profile_state"]
        chains.append(
            {
                "action_key": expected_key,
                "action_identity_sha256": chain["action_identity_sha256"],
                "result_file_sha256": chain["result_file_sha256"],
                "claim_filename": chain["claim_filename"],
                "claim_file_sha256": chain["claim_file_sha256"],
                "attempt_id": chain["attempt_id"],
                "profile_canonical_sha256": profile[
                    "profile_canonical_sha256"
                ],
                "profile_file_sha256": profile["profile_file_sha256"],
                "profile_review_artifact_file_sha256": profile[
                    "profile_review_artifact_file_sha256"
                ],
                "limit_authority_file_sha256": profile[
                    "limit_authority_file_sha256"
                ],
                "usage_evidence_file_sha256": profile[
                    "usage_evidence_file_sha256"
                ],
            }
        )
    if len(chains) != 8:
        raise N3APhysicalPlanError(
            "replayed physical N2 provenance does not contain eight finalized chains"
        )
    lineage_hashes = {
        "profile_identity_policy": lineage["profile_identity_policy"],
        "profile_validity_policy": lineage["profile_validity_policy"],
        "limit_authority_identity_policy": lineage[
            "limit_authority_identity_policy"
        ],
        "limit_authority_safety_contract_sha256": lineage[
            "limit_authority_safety_contract_sha256"
        ],
        "reviewer_id": lineage["reviewer_id"],
        "reviewer_key_id": lineage["reviewer_key_id"],
        "panel_canonical_sha256": _sha256(lineage["panel"]),
        "firmware_canonical_sha256": _sha256(lineage["firmware"]),
        "action_allowlist_canonical_sha256": _sha256(lineage["action_allowlist"]),
        "limits_canonical_sha256": _sha256(lineage["limits"]),
        "per_action_profile_set_canonical_sha256": _sha256(
            [
                {
                    "action_key": chain["action_key"],
                    "profile_id": chain["profile_state"]["profile_id"],
                    "profile_version": chain["profile_state"]["profile_version"],
                    "valid_from": chain["profile_state"]["valid_from"],
                    "expires_at": chain["profile_state"]["expires_at"],
                    "profile_canonical_sha256": chain["profile_state"][
                        "profile_canonical_sha256"
                    ],
                }
                for chain in analysis["validated_chains"]
            ]
        ),
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-n3a-replayed-n2-physical-provenance",
        "replay_analyzer": (
            "tools.g1_s1_rc2g_n2_physical_analyzer."
            "analyze_n2p_physical_campaign"
        ),
        "public_deep_validator_required_per_directory": True,
        "require_finalized": True,
        "trusted_reviewer_key_required": True,
        "result_directory_count": 8,
        "result_directory_paths_persisted_or_trusted": False,
        "content_hashes_bound_instead_of_mutable_paths": True,
        "analysis_json_alone_is_authority": False,
        "analysis_canonical_sha256": analysis["integrity"]["canonical_sha256"],
        "analysis_file_sha256": _sha256(analysis),
        "operator_manifest_canonical_sha256": source[
            "operator_manifest_canonical_sha256"
        ],
        "operator_manifest_file_sha256": source["operator_manifest_file_sha256"],
        "campaign_canonical_sha256": source["campaign_canonical_sha256"],
        "campaign_file_sha256": source["campaign_file_sha256"],
        "profile_lineage_hashes": lineage_hashes,
        "finalized_chains": chains,
        "claim_created_during_replay": False,
        "network_io_performed_during_replay": False,
        "device_io_performed_during_replay": False,
    }
    return {
        **unsigned,
        "canonical_sha256": _sha256(unsigned),
    }


def _validated_operator(value: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _canonical(value)
    digest = _sha256(payload)
    cached = _VALIDATED_OPERATOR_CACHE.get(digest)
    if cached is not None and cached[0] == payload:
        return _snapshot(cached[1])
    try:
        validated = n2_physical.validate_physical_manifest(value)
    except (n2_physical.N2PhysicalCampaignError, ValueError, RuntimeError) as error:
        raise N3APhysicalPlanError(
            f"physical N2 operator manifest failed deep validation: {error}"
        ) from error
    result = _snapshot(validated)
    _VALIDATED_OPERATOR_CACHE[digest] = (payload, result)
    return _snapshot(result)


def _winner_and_anchor(
    replayed_analysis: Mapping[str, Any], operator_value: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    analysis = _snapshot(replayed_analysis)
    operator = _validated_operator(operator_value)
    source = analysis["source_binding"]
    campaign = operator["physical_campaign_contract"]
    try:
        anchor = validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N3APhysicalPlanError(
            f"physical N2 anchor campaign is invalid: {error}"
        ) from error

    expected_source = {
        "operator_manifest_id": operator["operator_manifest_id"],
        "operator_manifest_canonical_sha256": operator["integrity"][
            "canonical_sha256"
        ],
        "operator_manifest_file_sha256": _sha256(operator),
        "physical_binding_canonical_sha256": operator["physical_binding"][
            "integrity"
        ]["canonical_sha256"],
        "campaign_id": anchor["campaign_id"],
        "campaign_canonical_sha256": anchor["integrity"]["canonical_sha256"],
        "campaign_file_sha256": _sha256(anchor),
        "panel": anchor["panel"],
        "firmware": anchor["firmware"],
    }
    if any(source[field] != expected for field, expected in expected_source.items()):
        raise N3APhysicalPlanError(
            "physical N2 analysis and operator are not the same exact "
            "operator/campaign/panel/firmware lineage"
        )
    if (
        source["profile_lineage"]["panel"] != anchor["panel"]
        or source["profile_lineage"]["firmware"] != anchor["firmware"]
    ):
        raise N3APhysicalPlanError(
            "physical N2 profile lineage crosses the selected panel or firmware"
        )

    winner = analysis["selected_winner"]
    gates = analysis["winner_gates"]
    tie = analysis["tie_state"]
    if (
        not isinstance(winner, Mapping)
        or gates.get("all_pass") is not True
        or gates.get("unique_top_total") is not True
        or tie.get("top_tie") is not False
        or tie.get("top_tied_cell_ids") != [winner.get("cell_id")]
        or winner.get("cell_id") not in planning.N3_CELLS
        or winner.get("authorized_use") != "N3_branch_selection_only"
        or winner.get("algorithm_qualified") is not False
        or winner.get("population_inference") is not False
    ):
        raise N3APhysicalPlanError(
            "N3A requires one unique, non-null, all-gates-PASS physical N2 "
            "winner authorized only for N3 branch selection"
        )

    action_key = winner["action_key"]
    action_sha = operator["fixed_actions"].get(action_key)
    actions = [
        action
        for action in anchor["actions"]
        if action["action_identity_sha256"] == action_sha
    ]
    candidates = [
        candidate
        for candidate in operator["source"]["candidate_bindings"]
        if candidate["cell_id"] == winner["cell_id"]
    ]
    if len(actions) != 1 or len(candidates) != 1:
        raise N3APhysicalPlanError(
            "physical N2 selected action or candidate binding is not unique"
        )
    action = actions[0]
    candidate = candidates[0]
    if (
        action["identity"]["phase"] != "target"
        or action["identity"]["cell_id"] != winner["cell_id"]
        or action["identity"]["frame"]["sha256"] != winner["frame_sha256"]
        or action["action_identity_sha256"] != winner["action_identity_sha256"]
        or candidate["algorithm"] != winner["algorithm"]
        or candidate["frame_sha256"] != winner["frame_sha256"]
    ):
        raise N3APhysicalPlanError(
            "physical N2 winner crosses its operator action/candidate binding"
        )
    return analysis, operator, anchor, winner


@lru_cache(maxsize=1)
def _frozen_n3a() -> Mapping[str, Any]:
    try:
        manifest = planning.compile_frozen_n3a_manifest()
        planning.validate_n3a_manifest(manifest)
    except (planning.N3CampaignError, ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalPlanError(
            f"frozen N3A source manifest is invalid: {error}"
        ) from error
    if (
        manifest["integrity"]["canonical_sha256"]
        != planning.EXPECTED_FROZEN_N3A_CANONICAL_SHA256
        or _sha256(manifest) != planning.EXPECTED_FROZEN_N3A_FILE_SHA256
    ):
        raise N3APhysicalPlanError("frozen N3A source identity changed")
    return _snapshot(manifest)


def _source_manifest(
    measurement_assets: Optional[Mapping[str, Any]],
    *,
    minimum_interval_seconds: float,
    planned_cooldown_seconds: float,
) -> Mapping[str, Any]:
    frozen = _frozen_n3a()
    assets = _snapshot(
        frozen["measurement_asset_registry"]
        if measurement_assets is None
        else measurement_assets
    )
    try:
        planning.measurement_asset_blockers(assets)
    except (planning.N3CampaignError, ValueError, RuntimeError) as error:
        raise N3APhysicalPlanError(
            f"N3A ten-item measurement asset registry is invalid: {error}"
        ) from error
    cache_input = {
        "measurement_asset_registry": assets,
        "minimum_interval_seconds": minimum_interval_seconds,
        "planned_cooldown_seconds": planned_cooldown_seconds,
    }
    payload = _canonical(cache_input)
    digest = _sha256(payload)
    cached = _SOURCE_MANIFEST_CACHE.get(digest)
    if cached is not None and cached[0] == payload:
        return _snapshot(cached[1])
    try:
        manifest = planning.compile_n3a_manifest(
            panel=frozen["panel"],
            firmware=frozen["firmware"],
            session_regime=frozen["session_regime"],
            measurement_assets=assets,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
        planning.validate_n3a_manifest(manifest)
    except (planning.N3CampaignError, ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalPlanError(
            f"N3A scientific source compilation failed: {error}"
        ) from error
    for field in (
        "study",
        "purpose",
        "source_n2",
        "panel",
        "firmware",
        "session_regime",
        "repeat_contract",
        "classification",
    ):
        if manifest[field] != frozen[field]:
            raise N3APhysicalPlanError(
                f"N3A scientific source contract changed at {field}"
            )
    if manifest["schedule"] != {
        "minimum_interval_since_map_seconds": minimum_interval_seconds,
        "planned_cooldown_after_session_seconds": planned_cooldown_seconds,
        "automatic_advance": False,
    }:
        raise N3APhysicalPlanError(
            "N3A source compiler did not freeze the explicit operator schedule"
        )
    result = _snapshot(manifest)
    _SOURCE_MANIFEST_CACHE[digest] = (payload, result)
    return _snapshot(result)


def _selected_source(
    manifest: Mapping[str, Any],
    winner: Mapping[str, Any],
    repeat_count: int,
) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any]]:
    cell = winner["cell_id"]
    branches = [branch for branch in manifest["branches"] if branch["winner_cell_id"] == cell]
    if len(branches) != 1:
        raise N3APhysicalPlanError("N3A winner does not identify one source branch")
    branch = branches[0]
    templates = [
        template
        for template in branch["repeat_templates"]
        if template["repeat_count"] == repeat_count
    ]
    if len(templates) != 1:
        raise N3APhysicalPlanError("N3A repeat count does not identify one template")
    template = templates[0]
    campaign = template["p0_campaign"]
    try:
        validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N3APhysicalPlanError(
            f"selected N3A source campaign is invalid: {error}"
        ) from error
    if (
        branch["algorithm"] != winner["algorithm"]
        or branch["candidate"]["frame"]["sha256"] != winner["frame_sha256"]
        or any(route["winner_cell_id"] != cell for route in template["routes"])
    ):
        raise N3APhysicalPlanError(
            "physical N2 winner differs from the frozen N3A source branch"
        )
    record = {
        "branch_id": branch["branch_id"],
        "template_id": template["template_id"],
        "winner_cell_id": cell,
        "algorithm": branch["algorithm"],
        "winner_frame_sha256": winner["frame_sha256"],
        "repeat_count": repeat_count,
        "campaign_id": campaign["campaign_id"],
        "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "campaign_file_sha256": _sha256(campaign),
        "routes": _snapshot(template["routes"]),
    }
    return campaign, template, record


def _asset_contract(registry: Mapping[str, Any]) -> dict[str, Any]:
    try:
        blockers = planning.measurement_asset_blockers(registry)
    except (planning.N3CampaignError, ValueError, RuntimeError) as error:
        raise N3APhysicalPlanError(
            f"N3A ten-item measurement asset registry is invalid: {error}"
        ) from error
    values = [registry[group][field] for group, field in _ASSET_PATHS]
    registered = sum(value is not None for value in values)
    return {
        "registry_canonical_sha256": _sha256(registry),
        "identity_field_count": len(_ASSET_PATHS),
        "registered_identity_count": registered,
        "all_identities_registered": registered == len(_ASSET_PATHS),
        "blockers": blockers,
        "scientific_registry_validator": (
            "tools.g1_s1_n3_campaign.measurement_asset_blockers"
        ),
    }


def _physical_routes_and_actions(
    *,
    template: Mapping[str, Any],
    source_campaign: Mapping[str, Any],
    physical_campaign: Mapping[str, Any],
    rebind_manifest: Mapping[str, Any],
    selected_source: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_by_sha = {
        action["action_identity_sha256"]: action
        for action in source_campaign["actions"]
    }
    physical_by_id = {
        action["identity"]["action_id"]: action
        for action in physical_campaign["actions"]
    }
    physical_sessions = {
        session["session_id"]: session for session in physical_campaign["sessions"]
    }
    identity_map = {
        row["source_action_identity_sha256"]: row
        for row in rebind_manifest["action_identity_map"]
    }
    routes: list[dict[str, Any]] = []
    fixed_actions: dict[str, Any] = {}
    for source_route in template["routes"]:
        old_map_sha = source_route["map_action_identity_sha256"]
        old_target_sha = source_route["target_action_identity_sha256"]
        old_map = source_by_sha[old_map_sha]
        old_target = source_by_sha[old_target_sha]
        map_action = physical_by_id[old_map["identity"]["action_id"]]
        target_action = physical_by_id[old_target["identity"]["action_id"]]
        map_sha = map_action["action_identity_sha256"]
        target_sha = target_action["action_identity_sha256"]
        session = physical_sessions.get(source_route["session_id"])
        if (
            identity_map[old_map_sha]["physical_action_identity_sha256"] != map_sha
            or identity_map[old_target_sha]["physical_action_identity_sha256"]
            != target_sha
            or session is None
            or session["action_identity_sha256s"] != [map_sha, target_sha]
            or target_action["identity"]["prior"]
            != {
                "action_identity_sha256": map_sha,
                "scope": "same_cell",
                "required_result_state": "PASS",
            }
        ):
            raise N3APhysicalPlanError(
                "physical N3A route/session/prior identity reconstruction changed"
            )
        route = {
            "branch_id": selected_source["branch_id"],
            "template_id": selected_source["template_id"],
            "repeat_count": selected_source["repeat_count"],
            "repeat_ordinal": source_route["repeat_ordinal"],
            "winner_cell_id": selected_source["winner_cell_id"],
            "campaign_id": physical_campaign["campaign_id"],
            "campaign_canonical_sha256": physical_campaign["integrity"][
                "canonical_sha256"
            ],
            "session_id": source_route["session_id"],
            "cell_id": source_route["cell_id"],
            "map_action_key": map_action["identity"]["action_id"],
            "source_map_action_identity_sha256": old_map_sha,
            "map_action_identity_sha256": map_sha,
            "target_action_key": target_action["identity"]["action_id"],
            "source_target_action_identity_sha256": old_target_sha,
            "target_action_identity_sha256": target_sha,
        }
        routes.append(route)
        for phase, action, old_action in (
            ("map", map_action, old_map),
            ("target", target_action, old_target),
        ):
            key = action["identity"]["action_id"]
            if key in fixed_actions:
                raise N3APhysicalPlanError(
                    "physical N3A action key is not globally unique"
                )
            fixed_actions[key] = {
                "action_identity_sha256": action["action_identity_sha256"],
                "source_action_identity_sha256": old_action[
                    "action_identity_sha256"
                ],
                "claim_filename": action["claim"]["filename"],
                "source_claim_filename": old_action["claim"]["filename"],
                "phase": "map-primer" if phase == "map" else "target",
                "cell_id": source_route["cell_id"],
                "winner_cell_id": selected_source["winner_cell_id"],
                "campaign_id": physical_campaign["campaign_id"],
                "campaign_canonical_sha256": physical_campaign["integrity"][
                    "canonical_sha256"
                ],
                "prior_action_key": (
                    map_action["identity"]["action_id"] if phase == "target" else None
                ),
            }
    if len(routes) != selected_source["repeat_count"] or len(fixed_actions) != 2 * len(routes):
        raise N3APhysicalPlanError("physical N3A route/action count changed")
    return routes, fixed_actions


def _identity_contract(
    source_campaign: Mapping[str, Any],
    physical_campaign: Mapping[str, Any],
    anchor: Mapping[str, Any],
) -> dict[str, Any]:
    old_hashes = {
        action["action_identity_sha256"] for action in source_campaign["actions"]
    }
    new_hashes = {
        action["action_identity_sha256"] for action in physical_campaign["actions"]
    }
    anchor_hashes = {action["action_identity_sha256"] for action in anchor["actions"]}
    old_claims = {action["claim"]["filename"] for action in source_campaign["actions"]}
    new_claims = {action["claim"]["filename"] for action in physical_campaign["actions"]}
    anchor_claims = {action["claim"]["filename"] for action in anchor["actions"]}
    source_sessions = {
        session["session_id"]: tuple(session["action_identity_sha256s"])
        for session in source_campaign["sessions"]
    }
    physical_sessions = {
        session["session_id"]: tuple(session["action_identity_sha256s"])
        for session in physical_campaign["sessions"]
    }
    all_sessions_rebound = (
        set(source_sessions) == set(physical_sessions)
        and all(source_sessions[key] != physical_sessions[key] for key in source_sessions)
    )
    source_new_disjoint = old_hashes.isdisjoint(new_hashes)
    source_claims_disjoint = old_claims.isdisjoint(new_claims)
    anchor_new_disjoint = anchor_hashes.isdisjoint(new_hashes)
    anchor_claims_disjoint = anchor_claims.isdisjoint(new_claims)
    if not all(
        (
            source_new_disjoint,
            source_claims_disjoint,
            anchor_new_disjoint,
            anchor_claims_disjoint,
            all_sessions_rebound,
        )
    ):
        raise N3APhysicalPlanError(
            "physical N3A did not produce a globally fresh identity set"
        )
    return {
        "source_action_count": len(old_hashes),
        "physical_action_count": len(new_hashes),
        "session_count": len(physical_sessions),
        "all_action_identities_rebuilt": True,
        "all_prior_identities_rebuilt": True,
        "all_session_action_identity_vectors_rebuilt": all_sessions_rebound,
        "all_workspace_global_claim_filenames_rebuilt": True,
        "source_and_physical_action_identities_disjoint": source_new_disjoint,
        "source_and_physical_claim_filenames_disjoint": source_claims_disjoint,
        "n2_anchor_and_n3_action_identities_disjoint": anchor_new_disjoint,
        "n2_anchor_and_n3_claim_filenames_disjoint": anchor_claims_disjoint,
        "old_claims_reusable": False,
    }


def _process_schedule(
    *,
    source_campaign: Mapping[str, Any],
    physical_campaign: Mapping[str, Any],
    minimum_interval_seconds: float,
    planned_cooldown_seconds: float,
) -> dict[str, Any]:
    for campaign, label in (
        (source_campaign, "source"),
        (physical_campaign, "physical"),
    ):
        targets = [
            action
            for action in campaign["actions"]
            if action["identity"]["phase"] == "target"
        ]
        maps = [
            action
            for action in campaign["actions"]
            if action["identity"]["phase"] == "map-primer"
        ]
        if (
            not targets
            or len(targets) != len(maps)
            or any(
                action["identity"]["schedule"][
                    "minimum_interval_since_prior_seconds"
                ]
                != minimum_interval_seconds
                for action in targets
            )
            or any(
                action["identity"]["schedule"][
                    "minimum_interval_since_prior_seconds"
                ]
                != 0.0
                for action in maps
            )
            or any(
                session["planned_cooldown_seconds"] != planned_cooldown_seconds
                for session in campaign["sessions"]
            )
        ):
            raise N3APhysicalPlanError(
                f"{label} N3A campaign did not freeze the explicit operator schedule"
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-n3a-operator-process-schedule",
        "classification": "operator_selected_experimental_process_schedule",
        "not_a_supplier_rating": True,
        "operator_input_required": True,
        "minimum_interval_seconds": minimum_interval_seconds,
        "planned_cooldown_seconds": planned_cooldown_seconds,
        "minimum_interval_must_be_positive": True,
        "planned_cooldown_must_be_nonnegative": True,
        "boolean_values_allowed": False,
        "frozen_zero_defaults_inherited": False,
        "map_minimum_interval_since_prior_seconds": 0.0,
        "target_minimum_interval_since_map_seconds": minimum_interval_seconds,
        "session_planned_cooldown_seconds": planned_cooldown_seconds,
        "source_campaign_schedule_verified": True,
        "physical_campaign_schedule_verified": True,
    }


def _selection(
    *,
    analysis: Mapping[str, Any],
    operator: Mapping[str, Any],
    anchor: Mapping[str, Any],
    winner: Mapping[str, Any],
    repeat_count: int,
    process_schedule: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    cell = winner["cell_id"]
    return {
        "selection_type": (
            "deep-physical-n2-unique-winner-plus-explicit-repeat-count"
        ),
        "winner": _snapshot(winner),
        "winner_cell_id": cell,
        "winner_identity_sha256": winner["winner_identity_sha256"],
        "authorized_use": "N3_branch_selection_only",
        "repeat_count": repeat_count,
        "process_schedule": _snapshot(process_schedule),
        "branch_id": f"n3a-winner-{cell.lower()}",
        "template_id": f"n3a-{cell.lower()}-repeat{repeat_count}",
        "n2_physical_analysis_canonical_sha256": analysis["integrity"][
            "canonical_sha256"
        ],
        "n2_physical_analysis_file_sha256": _sha256(analysis),
        "n2_physical_provenance_canonical_sha256": provenance[
            "canonical_sha256"
        ],
        "physical_operator_manifest_id": operator["operator_manifest_id"],
        "physical_operator_manifest_canonical_sha256": operator["integrity"][
            "canonical_sha256"
        ],
        "physical_operator_manifest_file_sha256": _sha256(operator),
        "physical_source_campaign_id": anchor["campaign_id"],
        "physical_source_campaign_canonical_sha256": anchor["integrity"][
            "canonical_sha256"
        ],
        "physical_source_campaign_file_sha256": _sha256(anchor),
        "deep_n2_physical_analysis_validated": True,
        "eight_finalized_result_directories_replayed": True,
        "trusted_reviewer_key_used_for_replay": True,
        "analysis_json_alone_accepted": False,
        "same_operator_campaign_panel_firmware_validated": True,
        "manual_repeat_selection_performed": True,
        "tie_or_null_winner_allowed": False,
        "cross_campaign_selection_allowed": False,
        "algorithm_qualified": False,
        "population_inference": False,
    }


def _power_semantics() -> dict[str, Any]:
    return {
        "runner_controls_power_or_j2": False,
        "physical_panel_instance_bound": True,
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
        "source_action_identities_executable": False,
        "source_claims_reusable": False,
    }


def _evidence_contract() -> dict[str, Any]:
    return {
        "plan_only_no_live_runner": True,
        "analysis_json_alone_must_never_authorize_plan_consumption": True,
        "exactly_eight_finalized_n2_physical_result_directories_required": True,
        "trusted_reviewer_key_required_for_every_public_consumer": True,
        "n2_physical_analyzer_replayed_on_every_public_consumer": True,
        "embedded_analysis_must_equal_replayed_analysis_canonical_bytes": True,
        "future_live_runner_must_repeat_raw_evidence_replay": True,
        "mutable_result_directory_paths_are_not_persisted_as_authority": True,
        "result_claim_action_and_profile_lineage_hashes_bound_in_plan": True,
        "standalone_physical_campaign_required": True,
        "workspace_global_claim_before_network": True,
        "maximum_post_requests_per_action": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "target_requires_same_route_finalized_map_pass": True,
        "target_binds_prior_result_and_finalization_whole_file_sha256": True,
        "manual_finalization_required": True,
        "visual_electrical_thermal_continuity_separate": True,
        "target_camera_capture_required": True,
        "reviewed_limit_profile_required_before_any_future_execution": True,
        "current_runtime_gates_required_before_any_future_execution": True,
    }


def _classification() -> dict[str, Any]:
    return {
        "offline_compiled": True,
        "physical_panel_instance_bound": True,
        "n2_physical_winner_selection_only": True,
        "live_runner_included": False,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "visible_refreshes_performed": 0,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "algorithm_qualified": False,
        "population_inference": False,
    }


def _physical_campaign_file_record(campaign: Mapping[str, Any]) -> dict[str, Any]:
    payload = _canonical(campaign)
    return {
        "filename": PHYSICAL_CAMPAIGN_FILENAME,
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "exact_root_kind": campaign["kind"],
    }


def _assemble_plan(
    replayed_n2_physical_analysis: Mapping[str, Any],
    physical_operator_manifest: Mapping[str, Any],
    *,
    repeat_count: int,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    binding_review_bytes: bytes,
    measurement_assets: Optional[Mapping[str, Any]],
    namespace: Optional[str],
) -> dict[str, Any]:
    if type(repeat_count) is not int or repeat_count not in planning.N3A_REPEAT_COUNTS:
        raise N3APhysicalPlanError(
            "N3A physical repeat_count must be exactly integer 2, 3, or 4"
        )
    interval, cooldown = _schedule_values(
        minimum_interval_seconds, planned_cooldown_seconds
    )
    if not isinstance(binding_review_bytes, bytes) or not binding_review_bytes:
        raise N3APhysicalPlanError(
            "non-empty physical N3A binding review artifact bytes are required"
        )
    if len(binding_review_bytes) > MAX_BINDING_REVIEW_BYTES:
        raise N3APhysicalPlanError(
            "physical N3A binding review artifact exceeds the safety limit"
        )
    analysis, operator, anchor, winner = _winner_and_anchor(
        replayed_n2_physical_analysis, physical_operator_manifest
    )
    provenance = _n2_physical_provenance(analysis)
    source_manifest = _source_manifest(
        measurement_assets,
        minimum_interval_seconds=interval,
        planned_cooldown_seconds=cooldown,
    )
    source_campaign, template, selected_source = _selected_source(
        source_manifest, winner, repeat_count
    )
    selected_namespace = (
        f"n3a-{winner['cell_id'].lower()}-repeat{repeat_count}"
        if namespace is None
        else namespace
    )
    try:
        rebound = rebind.compile_physical_campaign_rebind(
            source_campaign,
            anchor,
            namespace=selected_namespace,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=interval,
            planned_cooldown_seconds=cooldown,
        )
        rebind.validate_physical_campaign_rebind(
            rebound,
            source_campaign=source_campaign,
            physical_anchor_campaign=anchor,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=interval,
            planned_cooldown_seconds=cooldown,
        )
    except rebind.PhysicalCampaignRebindError as error:
        raise N3APhysicalPlanError(
            f"physical N3A identity rebind failed: {error}"
        ) from error
    physical_campaign = rebound["physical_campaign"]
    if (
        physical_campaign["panel"] != analysis["source_binding"]["panel"]
        or physical_campaign["firmware"] != analysis["source_binding"]["firmware"]
    ):
        raise N3APhysicalPlanError(
            "rebound N3A campaign crossed the physical N2 panel or firmware"
        )
    routes, fixed_actions = _physical_routes_and_actions(
        template=template,
        source_campaign=source_campaign,
        physical_campaign=physical_campaign,
        rebind_manifest=rebound,
        selected_source=selected_source,
    )
    assets = source_manifest["measurement_asset_registry"]
    asset_contract = _asset_contract(assets)
    identity_contract = _identity_contract(source_campaign, physical_campaign, anchor)
    process_schedule = _process_schedule(
        source_campaign=source_campaign,
        physical_campaign=physical_campaign,
        minimum_interval_seconds=interval,
        planned_cooldown_seconds=cooldown,
    )
    selection = _selection(
        analysis=analysis,
        operator=operator,
        anchor=anchor,
        winner=winner,
        repeat_count=repeat_count,
        process_schedule=process_schedule,
        provenance=provenance,
    )
    plan_id = (
        f"g1-s1-n3a-{winner['cell_id'].lower()}-repeat{repeat_count}-physical-"
        f"{rebound['binding']['canonical_sha256']}"
    )
    blockers = [
        *asset_contract["blockers"],
        "live_physical_runner_not_part_of_this_plan",
        "reviewed_limit_authority_profile_not_evaluated",
        "current_runtime_gates_and_exact_authorization_not_evaluated",
    ]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "plan_id": plan_id,
        "study": "N3A",
        "n2_physical_analysis": _snapshot(analysis),
        "n2_physical_provenance": provenance,
        "physical_operator_manifest": _snapshot(operator),
        "selection": selection,
        "source_n3a_manifest": _snapshot(source_manifest),
        "source_n3a_manifest_file_sha256": _sha256(source_manifest),
        "selected_source": selected_source,
        "physical_rebind": _snapshot(rebound),
        "physical_campaign_file": _physical_campaign_file_record(physical_campaign),
        "selected_routes": routes,
        "fixed_actions": fixed_actions,
        "measurement_asset_registry": _snapshot(assets),
        "measurement_asset_contract": asset_contract,
        "process_schedule": process_schedule,
        "identity_rebind_contract": identity_contract,
        "power_semantics": _power_semantics(),
        "evidence_contract": _evidence_contract(),
        "readiness": {
            "exact_physical_plan_compiled": True,
            "deep_n2_physical_analysis_validated": True,
            "eight_finalized_n2_result_directories_replayed": True,
            "trusted_reviewer_key_used": True,
            "embedded_analysis_matches_replay": True,
            "analysis_json_alone_sufficient": False,
            "future_live_runner_raw_evidence_replay_required": True,
            "unique_n2_winner_selected": True,
            "same_operator_campaign_panel_firmware_validated": True,
            "all_physical_identities_rebuilt": True,
            "measurement_asset_blockers": asset_contract["blockers"],
            "measurement_assets_ready": asset_contract[
                "all_identities_registered"
            ],
            "future_live_execution_ready": False,
            "hardware_ready": False,
            "blockers": blockers,
        },
        "classification": _classification(),
    }
    return {**unsigned, "integrity": _integrity(unsigned)}


def compile_n3a_physical_plan(
    n2_physical_analysis: Mapping[str, Any],
    physical_operator_manifest: Mapping[str, Any],
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    repeat_count: int,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    binding_review_bytes: bytes,
    measurement_assets: Optional[Mapping[str, Any]] = None,
    namespace: Optional[str] = None,
) -> dict[str, Any]:
    """Compile one deterministic offline physical N3A exact plan.

    The eight result directories and trusted reviewer key are mandatory even
    when ``n2_physical_analysis`` has a valid self-integrity seal.  Selection
    uses only the snapshot returned by that live replay after exact equality.
    ``binding_review_bytes`` are the actual bytes reviewing this N3A-to-N2
    physical binding.  Both schedule values are mandatory operator-selected
    experimental process parameters, not supplier ratings.
    """

    replayed = _replay_n2_physical_analysis(
        n2_result_directories,
        reviewer_key_file=reviewer_key_file,
    )
    trusted_analysis = _require_exact_replayed_analysis(
        n2_physical_analysis,
        replayed,
        label="provided physical N2 analysis",
    )
    plan = _assemble_plan(
        trusted_analysis,
        physical_operator_manifest,
        repeat_count=repeat_count,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        binding_review_bytes=binding_review_bytes,
        measurement_assets=measurement_assets,
        namespace=namespace,
    )
    # Assembly already deep-validates every input and the generic rebind.  A
    # cheap final seal check avoids repeating the expensive frozen compilers.
    unsigned = dict(plan)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned):  # pragma: no cover - construction guard
        raise N3APhysicalPlanError("constructed N3A physical plan seal changed")
    return plan


def validate_n3a_physical_plan(
    plan: Mapping[str, Any],
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    n2_physical_analysis: Optional[Mapping[str, Any]] = None,
    physical_operator_manifest: Optional[Mapping[str, Any]] = None,
    repeat_count: Optional[int] = None,
    namespace: Optional[str] = None,
) -> Mapping[str, Any]:
    """Deep-validate and deterministically reconstruct one physical N3A plan.

    Optional expected inputs bind a stored plan to the caller's original
    analysis/operator/repeat/namespace rather than merely validating its
    embedded snapshots.
    """

    replayed = _replay_n2_physical_analysis(
        n2_result_directories,
        reviewer_key_file=reviewer_key_file,
    )
    root = _exact(plan, label="N3A physical plan", keys=_ROOT_KEYS)
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != PLAN_KIND
        or root["study"] != "N3A"
        or not isinstance(root["plan_id"], str)
        or not root["plan_id"]
        or integrity != _integrity(unsigned)
    ):
        raise N3APhysicalPlanError(
            "N3A physical plan identity or canonical integrity is invalid"
        )
    if not isinstance(binding_review_bytes, bytes) or not binding_review_bytes:
        raise N3APhysicalPlanError(
            "non-empty physical N3A binding review artifact bytes are required"
        )
    if len(binding_review_bytes) > MAX_BINDING_REVIEW_BYTES:
        raise N3APhysicalPlanError(
            "physical N3A binding review artifact exceeds the safety limit"
        )
    embedded_analysis = root["n2_physical_analysis"]
    embedded_operator = root["physical_operator_manifest"]
    trusted_analysis = _require_exact_replayed_analysis(
        embedded_analysis,
        replayed,
        label="embedded physical N2 analysis",
    )
    if n2_physical_analysis is not None and _canonical(
        n2_physical_analysis
    ) != _canonical(trusted_analysis):
        raise N3APhysicalPlanError(
            "expected N2 physical analysis differs from the eight-directory replay"
        )
    if (
        physical_operator_manifest is not None
        and _canonical(physical_operator_manifest) != _canonical(embedded_operator)
    ):
        raise N3APhysicalPlanError(
            "N3A physical plan differs from the expected physical operator manifest"
        )
    selection = root["selection"]
    if not isinstance(selection, Mapping):
        raise N3APhysicalPlanError("N3A physical selection is missing")
    embedded_repeat = selection.get("repeat_count")
    interval, cooldown = _schedule_values(
        minimum_interval_seconds, planned_cooldown_seconds
    )
    if root["process_schedule"] != selection.get("process_schedule"):
        raise N3APhysicalPlanError(
            "N3A selection and root process_schedule differ"
        )
    if (
        not isinstance(root["process_schedule"], Mapping)
        or root["process_schedule"].get("minimum_interval_seconds") != interval
        or root["process_schedule"].get("planned_cooldown_seconds") != cooldown
    ):
        raise N3APhysicalPlanError(
            "N3A physical plan differs from the explicit operator schedule"
        )
    embedded_namespace = (
        root["physical_rebind"].get("namespace")
        if isinstance(root["physical_rebind"], Mapping)
        else None
    )
    if repeat_count is not None and embedded_repeat != repeat_count:
        raise N3APhysicalPlanError(
            "N3A physical plan differs from the expected repeat_count"
        )
    if namespace is not None and embedded_namespace != namespace:
        raise N3APhysicalPlanError(
            "N3A physical plan differs from the expected namespace"
        )
    embedded_review = (
        root["physical_rebind"].get("binding", {}).get(
            "binding_review_artifact"
        )
        if isinstance(root["physical_rebind"], Mapping)
        else None
    )
    if embedded_review != {
        "bytes": len(binding_review_bytes),
        "sha256": _sha256(binding_review_bytes),
        "actual_bytes_hashed": True,
    }:
        raise N3APhysicalPlanError(
            "N3A physical plan does not match the actual binding review artifact bytes"
        )
    expected = _assemble_plan(
        trusted_analysis,
        embedded_operator,
        repeat_count=embedded_repeat,
        minimum_interval_seconds=interval,
        planned_cooldown_seconds=cooldown,
        binding_review_bytes=binding_review_bytes,
        measurement_assets=root["measurement_asset_registry"],
        namespace=embedded_namespace,
    )
    if root != expected:
        raise N3APhysicalPlanError(
            "N3A physical plan differs from deterministic deep reconstruction"
        )
    return _snapshot(root)


def physical_plan_file_sha256(
    plan: Mapping[str, Any],
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> str:
    """Return the canonical whole-file identity after deep validation."""

    return _sha256(
        validate_n3a_physical_plan(
            plan,
            n2_result_directories=n2_result_directories,
            reviewer_key_file=reviewer_key_file,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise N3APhysicalPlanError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_json_file(
    path: Path, *, label: str, maximum_bytes: int
) -> tuple[Mapping[str, Any], bytes]:
    try:
        snapshot = production.read_local_regular_file(
            path, label=label, maximum_bytes=maximum_bytes
        )
    except production.ProductionProfileError as error:
        raise N3APhysicalPlanError(str(error)) from error
    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N3APhysicalPlanError(f"{label} contains forbidden number {token}")
            ),
        )
    except N3APhysicalPlanError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3APhysicalPlanError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N3APhysicalPlanError(f"{label} JSON root must be an object")
    if snapshot.payload != _canonical(value):
        raise N3APhysicalPlanError(f"{label} must use canonical JSON bytes")
    return value, snapshot.payload


def _read_review(path: Path) -> bytes:
    try:
        snapshot = production.read_local_regular_file(
            path,
            label="physical N3A binding review artifact",
            maximum_bytes=MAX_BINDING_REVIEW_BYTES,
        )
    except production.ProductionProfileError as error:
        raise N3APhysicalPlanError(str(error)) from error
    if not snapshot.payload:
        raise N3APhysicalPlanError(
            "physical N3A binding review artifact must not be empty"
        )
    return snapshot.payload


def compile_n3a_physical_plan_from_files(
    n2_physical_analysis_file: Path,
    physical_operator_manifest_file: Path,
    binding_review_artifact_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    repeat_count: int,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    measurement_assets_file: Optional[Path] = None,
    namespace: Optional[str] = None,
) -> dict[str, Any]:
    """Read immutable canonical inputs once and compile one physical plan."""

    analysis, _analysis_payload = _read_json_file(
        n2_physical_analysis_file,
        label="physical N2 analysis",
        maximum_bytes=MAX_INPUT_JSON_BYTES,
    )
    operator, _operator_payload = _read_json_file(
        physical_operator_manifest_file,
        label="physical N2 operator manifest",
        maximum_bytes=MAX_INPUT_JSON_BYTES,
    )
    assets = None
    if measurement_assets_file is not None:
        assets, _assets_payload = _read_json_file(
            measurement_assets_file,
            label="N3A measurement asset registry",
            maximum_bytes=MAX_INPUT_JSON_BYTES,
        )
    review = _read_review(binding_review_artifact_file)
    return compile_n3a_physical_plan(
        analysis,
        operator,
        n2_result_directories=n2_result_directories,
        reviewer_key_file=reviewer_key_file,
        repeat_count=repeat_count,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        binding_review_bytes=review,
        measurement_assets=assets,
        namespace=namespace,
    )


def _reject_reparse_chain(path: Path, *, label: str) -> None:
    try:
        lexical = path.absolute()
    except OSError as error:
        raise N3APhysicalPlanError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise N3APhysicalPlanError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise N3APhysicalPlanError(
                f"{label} must not contain a symlink or Windows reparse point"
            )


def _bundle_destination(path: Path) -> Path:
    try:
        require_local_regular_path_syntax(path, label="N3A physical plan output")
    except LocalPathSafetyError as error:
        raise N3APhysicalPlanError(str(error)) from error
    _reject_reparse_chain(path, label="N3A physical plan output")
    if os.path.lexists(path):
        raise N3APhysicalPlanError(
            "N3A physical plan output already exists; refusing overwrite"
        )
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N3APhysicalPlanError(
            f"N3A physical plan output parent is unavailable: {error}"
        ) from error
    _reject_reparse_chain(parent, label="N3A physical plan output parent")
    if not parent.is_dir():
        raise N3APhysicalPlanError(
            "N3A physical plan output parent must be a directory"
        )
    return parent / path.name


def _write_staged(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise N3APhysicalPlanError(f"could not stage {path.name}: {error}") from error


def publish_n3a_physical_plan_bundle(
    n2_physical_analysis_file: Path,
    physical_operator_manifest_file: Path,
    binding_review_artifact_file: Path,
    output_directory: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    repeat_count: int,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    measurement_assets_file: Optional[Path] = None,
    namespace: Optional[str] = None,
) -> dict[str, Any]:
    """Exclusively publish exactly ``PHYSICAL-CAMPAIGN.json`` plus the plan."""

    destination = _bundle_destination(output_directory)
    plan = compile_n3a_physical_plan_from_files(
        n2_physical_analysis_file,
        physical_operator_manifest_file,
        binding_review_artifact_file,
        n2_result_directories=n2_result_directories,
        reviewer_key_file=reviewer_key_file,
        repeat_count=repeat_count,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        measurement_assets_file=measurement_assets_file,
        namespace=namespace,
    )
    campaign = plan["physical_rebind"]["physical_campaign"]
    campaign_payload = _canonical(campaign)
    plan_payload = _canonical(plan)
    staging = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    published = False
    try:
        staging.mkdir()
        campaign_file = staging / PHYSICAL_CAMPAIGN_FILENAME
        plan_file = staging / PLAN_MANIFEST_FILENAME
        _write_staged(campaign_file, campaign_payload)
        _write_staged(plan_file, plan_payload)
        if (
            campaign_file.read_bytes() != campaign_payload
            or plan_file.read_bytes() != plan_payload
        ):
            raise N3APhysicalPlanError("staged N3A physical plan bytes changed")
        if os.path.lexists(destination):
            raise N3APhysicalPlanError(
                "N3A physical plan output appeared; refusing overwrite"
            )
        os.rename(staging, destination)
        published = True
    except N3APhysicalPlanError:
        raise
    except OSError as error:
        raise N3APhysicalPlanError(
            f"could not atomically publish N3A physical plan: {error}"
        ) from error
    finally:
        if not published:
            for filename in (PHYSICAL_CAMPAIGN_FILENAME, PLAN_MANIFEST_FILENAME):
                try:
                    (staging / filename).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass
    return plan


def _bundle_paths(directory: Path) -> tuple[Path, Path]:
    try:
        require_local_regular_path_syntax(directory, label="N3A physical plan bundle")
    except LocalPathSafetyError as error:
        raise N3APhysicalPlanError(str(error)) from error
    _reject_reparse_chain(directory, label="N3A physical plan bundle")
    try:
        bundle = directory.resolve(strict=True)
        entries = tuple(bundle.iterdir())
    except OSError as error:
        raise N3APhysicalPlanError(
            f"N3A physical plan bundle is unavailable: {error}"
        ) from error
    expected = {PHYSICAL_CAMPAIGN_FILENAME, PLAN_MANIFEST_FILENAME}
    if (
        not bundle.is_dir()
        or {entry.name for entry in entries} != expected
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise N3APhysicalPlanError(
            "N3A physical plan bundle must contain exactly the canonical "
            "physical campaign and plan files"
        )
    return bundle / PHYSICAL_CAMPAIGN_FILENAME, bundle / PLAN_MANIFEST_FILENAME


def read_n3a_physical_plan(
    path: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    binding_review_artifact_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    """Read canonical plan bytes and replay full validation with review bytes."""

    value, _payload = _read_json_file(
        path, label="N3A physical plan", maximum_bytes=MAX_PLAN_JSON_BYTES
    )
    return validate_n3a_physical_plan(
        value,
        n2_result_directories=n2_result_directories,
        reviewer_key_file=reviewer_key_file,
        binding_review_bytes=_read_review(binding_review_artifact_file),
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


def validate_n3a_physical_plan_bundle(
    directory: Path,
    binding_review_artifact_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    n2_physical_analysis_file: Optional[Path] = None,
    physical_operator_manifest_file: Optional[Path] = None,
) -> Mapping[str, Any]:
    """Validate the exclusive two-file bundle and optional original inputs."""

    campaign_file, plan_file = _bundle_paths(directory)
    plan_value, _plan_payload = _read_json_file(
        plan_file, label="N3A physical plan", maximum_bytes=MAX_PLAN_JSON_BYTES
    )
    expected_analysis = None
    if n2_physical_analysis_file is not None:
        expected_analysis, _payload = _read_json_file(
            n2_physical_analysis_file,
            label="expected physical N2 analysis",
            maximum_bytes=MAX_INPUT_JSON_BYTES,
        )
    expected_operator = None
    if physical_operator_manifest_file is not None:
        expected_operator, _payload = _read_json_file(
            physical_operator_manifest_file,
            label="expected physical N2 operator manifest",
            maximum_bytes=MAX_INPUT_JSON_BYTES,
        )
    plan = validate_n3a_physical_plan(
        plan_value,
        n2_result_directories=n2_result_directories,
        reviewer_key_file=reviewer_key_file,
        binding_review_bytes=_read_review(binding_review_artifact_file),
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        n2_physical_analysis=expected_analysis,
        physical_operator_manifest=expected_operator,
    )
    try:
        campaign = rebind.read_standalone_physical_campaign(campaign_file)
    except rebind.PhysicalCampaignRebindError as error:
        raise N3APhysicalPlanError(
            f"standalone N3A physical campaign is invalid: {error}"
        ) from error
    if (
        campaign != plan["physical_rebind"]["physical_campaign"]
        or plan["physical_campaign_file"] != _physical_campaign_file_record(campaign)
    ):
        raise N3APhysicalPlanError(
            "standalone physical campaign differs from the N3A plan"
        )
    return plan


def _description(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "kind": plan["kind"],
        "plan_id": plan["plan_id"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": _sha256(plan),
        "winner_cell_id": plan["selection"]["winner_cell_id"],
        "repeat_count": plan["selection"]["repeat_count"],
        "physical_campaign_id": plan["physical_rebind"]["physical_campaign"][
            "campaign_id"
        ],
        "panel": _snapshot(plan["physical_rebind"]["physical_campaign"]["panel"]),
        "action_count": len(plan["fixed_actions"]),
        "session_count": plan["identity_rebind_contract"]["session_count"],
        "measurement_assets_ready": plan["readiness"][
            "measurement_assets_ready"
        ],
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def describe_n3a_physical_plan(
    plan: Mapping[str, Any],
    *,
    n2_result_directories: Mapping[str, Path],
    reviewer_key_file: Path,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    n2_physical_analysis: Optional[Mapping[str, Any]] = None,
    physical_operator_manifest: Optional[Mapping[str, Any]] = None,
    repeat_count: Optional[int] = None,
    namespace: Optional[str] = None,
) -> dict[str, Any]:
    """Replay raw N2 evidence, deep-validate the plan, then summarize it."""

    validated = validate_n3a_physical_plan(
        plan,
        n2_result_directories=n2_result_directories,
        reviewer_key_file=reviewer_key_file,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        n2_physical_analysis=n2_physical_analysis,
        physical_operator_manifest=physical_operator_manifest,
        repeat_count=repeat_count,
        namespace=namespace,
    )
    return _description(validated)


def _add_n2_replay_inputs(parser: argparse.ArgumentParser) -> None:
    for key in n2_analyzer.EXPECTED_RESULT_KEYS:
        parser.add_argument(f"--{key}-dir", type=Path, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)


def _n2_result_directories_from_args(
    args: argparse.Namespace,
) -> dict[str, Path]:
    return {
        key: getattr(args, key.replace("-", "_") + "_dir")
        for key in n2_analyzer.EXPECTED_RESULT_KEYS
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile", allow_abbrev=False)
    compile_parser.add_argument("--n2-analysis", type=Path, required=True)
    compile_parser.add_argument("--physical-operator-manifest", type=Path, required=True)
    compile_parser.add_argument("--binding-review-artifact", type=Path, required=True)
    compile_parser.add_argument("--repeat-count", type=int, choices=(2, 3, 4), required=True)
    compile_parser.add_argument(
        "--minimum-interval-seconds", type=float, required=True
    )
    compile_parser.add_argument(
        "--planned-cooldown-seconds", type=float, required=True
    )
    compile_parser.add_argument("--measurement-assets", type=Path)
    compile_parser.add_argument("--namespace")
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    _add_n2_replay_inputs(compile_parser)
    validate_parser = commands.add_parser("validate", allow_abbrev=False)
    validate_parser.add_argument("--bundle-dir", type=Path, required=True)
    validate_parser.add_argument("--binding-review-artifact", type=Path, required=True)
    validate_parser.add_argument(
        "--minimum-interval-seconds", type=float, required=True
    )
    validate_parser.add_argument(
        "--planned-cooldown-seconds", type=float, required=True
    )
    validate_parser.add_argument("--n2-analysis", type=Path)
    validate_parser.add_argument("--physical-operator-manifest", type=Path)
    _add_n2_replay_inputs(validate_parser)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result_directories = _n2_result_directories_from_args(args)
    try:
        if args.command == "compile":
            plan = publish_n3a_physical_plan_bundle(
                args.n2_analysis,
                args.physical_operator_manifest,
                args.binding_review_artifact,
                args.output_dir,
                n2_result_directories=result_directories,
                reviewer_key_file=args.reviewer_key,
                repeat_count=args.repeat_count,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
                measurement_assets_file=args.measurement_assets,
                namespace=args.namespace,
            )
        else:
            plan = validate_n3a_physical_plan_bundle(
                args.bundle_dir,
                args.binding_review_artifact,
                n2_result_directories=result_directories,
                reviewer_key_file=args.reviewer_key,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
                n2_physical_analysis_file=args.n2_analysis,
                physical_operator_manifest_file=args.physical_operator_manifest,
            )
    except (N3APhysicalPlanError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(_description(plan), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MAX_BINDING_REVIEW_BYTES",
    "MAX_INPUT_JSON_BYTES",
    "MAX_PLAN_JSON_BYTES",
    "N3APhysicalPlanError",
    "PHYSICAL_CAMPAIGN_FILENAME",
    "PLAN_HASH_SCOPE",
    "PLAN_KIND",
    "PLAN_MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "compile_n3a_physical_plan",
    "compile_n3a_physical_plan_from_files",
    "describe_n3a_physical_plan",
    "main",
    "parse_args",
    "physical_plan_file_sha256",
    "publish_n3a_physical_plan_bundle",
    "read_n3a_physical_plan",
    "validate_n3a_physical_plan",
    "validate_n3a_physical_plan_bundle",
]
