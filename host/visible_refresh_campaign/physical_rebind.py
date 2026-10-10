"""Deterministic physical-panel rebinding for frozen refresh campaigns.

The ordinary campaign contract intentionally keeps the panel outside each
action identity.  Consequently, replacing only ``campaign.panel`` would leave
the old action hashes and workspace-global claim filenames reusable.  This
module provides the only safe mechanical operation for that transition: derive
a fresh campaign ID from real binding evidence and rebuild the complete action
DAG, sessions, priors, and claims.

There is deliberately no network, device, authorization, claim creation,
retry, recovery, or profile-approval implementation here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping
import uuid

from .contracts import (
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    seal_campaign_contract,
    validate_campaign_contract,
)
from .production_profile import ProductionProfileError, read_local_regular_file


SCHEMA_VERSION = 1
REBIND_KIND = "mf1750-visible-refresh-physical-campaign-rebind"
REBIND_HASH_SCOPE = (
    "entire physical campaign rebind excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
BINDING_HASH_SCOPE = (
    "entire physical campaign binding input; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_CAMPAIGN_JSON_BYTES = 16 * 1024 * 1024
MAX_BINDING_REVIEW_BYTES = 4 * 1024 * 1024
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
REBIND_MANIFEST_FILENAME = "PHYSICAL-CAMPAIGN-REBIND.json"

_NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}\Z")
_PLACEHOLDER_RE = re.compile(
    r"(?:^|[-_. ])(?:UNBOUND|UNKNOWN|PLACEHOLDER|DRAFT|TBD|NONE|NULL|TEST)"
    r"(?:$|[-_. ])",
    re.IGNORECASE,
)
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "namespace",
        "source",
        "physical_anchor",
        "binding",
        "action_identity_map",
        "physical_campaign",
        "classification",
        "integrity",
    }
)


class PhysicalCampaignRebindError(ValueError):
    """Raised when a campaign cannot be safely rebound to one real panel."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalCampaignRebindError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _record(campaign: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    payload = canonical_json_bytes(campaign)
    return {
        "role": role,
        "campaign_id": campaign["campaign_id"],
        "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "campaign_file_sha256": _sha256(payload),
        "panel": _snapshot(campaign["panel"]),
        "firmware": _snapshot(campaign["firmware"]),
    }


def _physical_panel(anchor: Mapping[str, Any]) -> Mapping[str, Any]:
    panel = anchor["panel"]
    for field in ("model", "serial", "board_id", "pcb_revision"):
        value = panel[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or _PLACEHOLDER_RE.search(value) is not None
        ):
            raise PhysicalCampaignRebindError(
                f"physical anchor panel.{field} is unbound or placeholder data"
            )
    return panel


def _validate_anchor_compatibility(
    source: Mapping[str, Any], anchor: Mapping[str, Any]
) -> None:
    physical_panel = _physical_panel(anchor)
    source_panel = source["panel"]
    for field in ("model", "board_id", "pcb_revision"):
        if source_panel[field] != physical_panel[field]:
            raise PhysicalCampaignRebindError(
                f"source panel.{field} differs from the physical anchor"
            )
    if source["firmware"] != anchor["firmware"]:
        raise PhysicalCampaignRebindError(
            "source firmware differs from the physical anchor firmware"
        )


def _binding_record(
    *,
    namespace: str,
    source: Mapping[str, Any],
    anchor: Mapping[str, Any],
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    if not isinstance(binding_review_bytes, bytes) or not binding_review_bytes:
        raise PhysicalCampaignRebindError(
            "non-empty physical binding review artifact bytes are required"
        )
    if len(binding_review_bytes) > MAX_BINDING_REVIEW_BYTES:
        raise PhysicalCampaignRebindError(
            "physical binding review artifact exceeds the safety limit"
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "namespace": namespace,
        "source_campaign_canonical_sha256": source["integrity"][
            "canonical_sha256"
        ],
        "physical_anchor_campaign_canonical_sha256": anchor["integrity"][
            "canonical_sha256"
        ],
        "panel": _snapshot(anchor["panel"]),
        "firmware": _snapshot(anchor["firmware"]),
        "binding_review_artifact": {
            "bytes": len(binding_review_bytes),
            "sha256": _sha256(binding_review_bytes),
            "actual_bytes_hashed": True,
        },
        "reviewed_schedule": _reviewed_schedule(
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        ),
    }
    return {
        **unsigned,
        "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
        "canonical_sha256_scope": BINDING_HASH_SCOPE,
    }


def _new_campaign_id(namespace: str, binding_sha256: str) -> str:
    # At most 114 characters, below the campaign token's 128-character limit.
    return f"physical-{namespace}-{binding_sha256}"


def _reviewed_schedule(
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    values = (
        (minimum_interval_seconds, "minimum_interval_seconds", True),
        (planned_cooldown_seconds, "planned_cooldown_seconds", False),
    )
    result: dict[str, Any] = {
        "classification": "operator_selected_experimental_process_schedule",
        "not_a_supplier_rating": True,
    }
    for value, label, strictly_positive in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PhysicalCampaignRebindError(
                f"reviewed {label} must be a finite number"
            )
        normalized = float(value)
        if not math.isfinite(normalized) or normalized < 0:
            raise PhysicalCampaignRebindError(
                f"reviewed {label} must be finite and non-negative"
            )
        if strictly_positive and normalized <= 0:
            raise PhysicalCampaignRebindError(
                "reviewed minimum_interval_seconds must be positive"
            )
        result[label] = normalized
    return result


def _rebuild_campaign(
    source: Mapping[str, Any],
    *,
    panel: Mapping[str, Any],
    campaign_id: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    schedule = _reviewed_schedule(
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    source_actions = {
        action["action_identity_sha256"]: action for action in source["actions"]
    }
    replacement_by_source_sha: dict[str, Mapping[str, Any]] = {}
    actions: list[Mapping[str, Any]] = []
    sessions: list[Mapping[str, Any]] = []
    identity_map: list[dict[str, Any]] = []

    # validate_campaign_contract guarantees that session order is a topological
    # order over the action DAG.  Rebuild in that same order so every prior has
    # already received its new identity.
    for source_session in source["sessions"]:
        new_session_actions: list[str] = []
        for old_sha in source_session["action_identity_sha256s"]:
            old_action = source_actions[old_sha]
            old_identity = old_action["identity"]
            old_prior = old_identity["prior"]
            new_prior_sha = None
            new_prior_scope = None
            if old_prior is not None:
                new_prior = replacement_by_source_sha.get(
                    old_prior["action_identity_sha256"]
                )
                if new_prior is None:  # pragma: no cover - source validator guards this
                    raise PhysicalCampaignRebindError(
                        "source prior was not ordered before its dependent action"
                    )
                new_prior_sha = new_prior["action_identity_sha256"]
                new_prior_scope = old_prior["scope"]
            try:
                new_action = build_fixed_action_declaration(
                    campaign_id=campaign_id,
                    session_id=old_identity["session_id"],
                    cell_id=old_identity["cell_id"],
                    action_id=old_identity["action_id"],
                    phase=old_identity["phase"],
                    frame=old_identity["frame"],
                    endpoint=old_identity["request"]["endpoint"],
                    prior_action_identity_sha256=new_prior_sha,
                    prior_scope=new_prior_scope,
                    minimum_interval_since_prior_seconds=(
                        schedule["minimum_interval_seconds"]
                        if old_prior is not None
                        else old_identity["schedule"][
                            "minimum_interval_since_prior_seconds"
                        ]
                    ),
                )
            except CampaignContractError as error:
                raise PhysicalCampaignRebindError(
                    f"could not rebuild action {old_identity['action_id']}: {error}"
                ) from error
            new_sha = new_action["action_identity_sha256"]
            replacement_by_source_sha[old_sha] = new_action
            new_session_actions.append(new_sha)
            actions.append(new_action)
            identity_map.append(
                {
                    "action_id": old_identity["action_id"],
                    "session_id": old_identity["session_id"],
                    "cell_id": old_identity["cell_id"],
                    "phase": old_identity["phase"],
                    "source_action_identity_sha256": old_sha,
                    "physical_action_identity_sha256": new_sha,
                    "source_claim_filename": old_action["claim"]["filename"],
                    "physical_claim_filename": new_action["claim"]["filename"],
                }
            )
        try:
            sessions.append(
                build_session_contract(
                    session_id=source_session["session_id"],
                    cell_id=source_session["cell_id"],
                    power_mode=source_session["power_mode"],
                    planned_cooldown_seconds=schedule[
                        "planned_cooldown_seconds"
                    ],
                    final_power_off_required=source_session[
                        "final_power_off_required"
                    ],
                    action_identity_sha256s=new_session_actions,
                    minimum_panel_power_off_seconds=source_session[
                        "minimum_panel_power_off_seconds"
                    ],
                )
            )
        except CampaignContractError as error:
            raise PhysicalCampaignRebindError(
                f"could not rebuild session {source_session['session_id']}: {error}"
            ) from error

    try:
        campaign = seal_campaign_contract(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": source["kind"],
                "campaign_id": campaign_id,
                "panel": _snapshot(panel),
                "firmware": _snapshot(source["firmware"]),
                "actions": actions,
                "sessions": sessions,
                "classification": _snapshot(source["classification"]),
            }
        )
    except CampaignContractError as error:
        raise PhysicalCampaignRebindError(
            f"physical campaign validation failed: {error}"
        ) from error
    return campaign, identity_map


def _classification() -> dict[str, Any]:
    return {
        "offline_materialized": True,
        "physical_panel_instance_bound": True,
        "all_action_identities_rebuilt": True,
        "all_prior_identities_rebuilt": True,
        "all_session_identities_rebuilt": True,
        "all_claim_filenames_rebuilt": True,
        "reviewed_limit_profile_present": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def compile_physical_campaign_rebind(
    source_campaign: Mapping[str, Any],
    physical_anchor_campaign: Mapping[str, Any],
    *,
    namespace: str,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Rebind one validated source campaign to a physical campaign anchor.

    ``physical_anchor_campaign`` is normally the N2 physical-bound campaign.
    It supplies the exact physical panel and firmware identities shared by
    later N3/N4 work.  The returned artifact is offline-only and does not
    manufacture a production limit profile.
    """

    if not isinstance(namespace, str) or _NAMESPACE_RE.fullmatch(namespace) is None:
        raise PhysicalCampaignRebindError(
            "namespace must be a 1..40 character stable token"
        )
    try:
        source = validate_campaign_contract(source_campaign)
        anchor = validate_campaign_contract(physical_anchor_campaign)
    except CampaignContractError as error:
        raise PhysicalCampaignRebindError(f"campaign validation failed: {error}") from error
    _validate_anchor_compatibility(source, anchor)
    binding = _binding_record(
        namespace=namespace,
        source=source,
        anchor=anchor,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    campaign_id = _new_campaign_id(namespace, binding["canonical_sha256"])
    if campaign_id in {source["campaign_id"], anchor["campaign_id"]}:
        raise PhysicalCampaignRebindError("derived physical campaign_id was not fresh")
    campaign, identity_map = _rebuild_campaign(
        source,
        panel=anchor["panel"],
        campaign_id=campaign_id,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": REBIND_KIND,
        "namespace": namespace,
        "source": _record(source, role="frozen-offline-source"),
        "physical_anchor": _record(anchor, role="physical-panel-firmware-anchor"),
        "binding": binding,
        "action_identity_map": identity_map,
        "physical_campaign": campaign,
        "classification": _classification(),
    }
    manifest = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": REBIND_HASH_SCOPE,
        },
    }
    validate_physical_campaign_rebind(
        manifest,
        source_campaign=source,
        physical_anchor_campaign=anchor,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    return manifest


def _validate_lineage(
    manifest: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    anchor: Mapping[str, Any],
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> None:
    schedule = _reviewed_schedule(
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    physical = validate_campaign_contract(manifest["physical_campaign"])
    if physical["panel"] != anchor["panel"] or physical["firmware"] != anchor["firmware"]:
        raise PhysicalCampaignRebindError(
            "physical campaign does not exactly match the anchor panel and firmware"
        )
    if physical["campaign_id"] in {source["campaign_id"], anchor["campaign_id"]}:
        raise PhysicalCampaignRebindError("physical campaign reused an old campaign_id")

    old_by_id = {action["identity"]["action_id"]: action for action in source["actions"]}
    new_by_id = {action["identity"]["action_id"]: action for action in physical["actions"]}
    if set(old_by_id) != set(new_by_id):
        raise PhysicalCampaignRebindError("physical action membership changed")
    old_hashes = {action["action_identity_sha256"] for action in old_by_id.values()}
    new_hashes = {action["action_identity_sha256"] for action in new_by_id.values()}
    old_claims = {action["claim"]["filename"] for action in old_by_id.values()}
    new_claims = {action["claim"]["filename"] for action in new_by_id.values()}
    if old_hashes & new_hashes or old_claims & new_claims:
        raise PhysicalCampaignRebindError(
            "physical campaign reused an offline action identity or claim"
        )

    old_key_by_sha = {
        action["action_identity_sha256"]: action_id
        for action_id, action in old_by_id.items()
    }
    expected_map = []
    for old_action in source["actions"]:
        action_id = old_action["identity"]["action_id"]
        new_action = new_by_id[action_id]
        old_identity = old_action["identity"]
        new_identity = new_action["identity"]
        for field in ("session_id", "cell_id", "action_id", "phase", "frame", "request"):
            if new_identity[field] != old_identity[field]:
                raise PhysicalCampaignRebindError(
                    f"physical action {action_id} changed frozen {field} semantics"
                )
        old_prior = old_identity["prior"]
        new_prior = new_identity["prior"]
        expected_action_schedule = {
            **old_identity["schedule"],
            "minimum_interval_since_prior_seconds": (
                schedule["minimum_interval_seconds"]
                if old_prior is not None
                else old_identity["schedule"][
                    "minimum_interval_since_prior_seconds"
                ]
            ),
        }
        if new_identity["schedule"] != expected_action_schedule:
            raise PhysicalCampaignRebindError(
                f"physical action {action_id} reviewed schedule changed"
            )
        if old_prior is None:
            if new_prior is not None:
                raise PhysicalCampaignRebindError(
                    f"physical action {action_id} unexpectedly gained a prior"
                )
        else:
            prior_id = old_key_by_sha[old_prior["action_identity_sha256"]]
            if (
                new_prior is None
                or new_prior["action_identity_sha256"]
                != new_by_id[prior_id]["action_identity_sha256"]
                or new_prior["scope"] != old_prior["scope"]
                or new_prior["required_result_state"]
                != old_prior["required_result_state"]
            ):
                raise PhysicalCampaignRebindError(
                    f"physical action {action_id} prior was not rebuilt"
                )
        expected_map.append(
            {
                "action_id": action_id,
                "session_id": old_identity["session_id"],
                "cell_id": old_identity["cell_id"],
                "phase": old_identity["phase"],
                "source_action_identity_sha256": old_action[
                    "action_identity_sha256"
                ],
                "physical_action_identity_sha256": new_action[
                    "action_identity_sha256"
                ],
                "source_claim_filename": old_action["claim"]["filename"],
                "physical_claim_filename": new_action["claim"]["filename"],
            }
        )
    if manifest["action_identity_map"] != expected_map:
        raise PhysicalCampaignRebindError("action identity map is not exact")

    old_sessions = {session["session_id"]: session for session in source["sessions"]}
    new_sessions = {session["session_id"]: session for session in physical["sessions"]}
    if set(old_sessions) != set(new_sessions):
        raise PhysicalCampaignRebindError("physical session membership changed")
    for session_id, old_session in old_sessions.items():
        new_session = new_sessions[session_id]
        for field in (
            "cell_id",
            "power_mode",
            "requires_controller_fresh_boot",
            "requires_panel_power_cycle",
            "minimum_panel_power_off_seconds",
            "j2_may_remain_on_before_session",
            "final_power_off_required",
            "automatic_advance",
        ):
            if new_session[field] != old_session[field]:
                raise PhysicalCampaignRebindError(
                    f"physical session {session_id} changed {field} semantics"
                )
        if (
            new_session["planned_cooldown_seconds"]
            != schedule["planned_cooldown_seconds"]
        ):
            raise PhysicalCampaignRebindError(
                f"physical session {session_id} reviewed cooldown changed"
            )
        expected_shas = [
            new_by_id[old_by_id_sha["identity"]["action_id"]][
                "action_identity_sha256"
            ]
            for old_sha in old_session["action_identity_sha256s"]
            for old_by_id_sha in (next(
                action
                for action in source["actions"]
                if action["action_identity_sha256"] == old_sha
            ),)
        ]
        if new_session["action_identity_sha256s"] != expected_shas:
            raise PhysicalCampaignRebindError(
                f"physical session {session_id} action identities were not rebuilt"
            )


def validate_physical_campaign_rebind(
    manifest: Mapping[str, Any],
    *,
    source_campaign: Mapping[str, Any],
    physical_anchor_campaign: Mapping[str, Any],
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    """Deep-validate one rebind artifact against all original input bytes."""

    if not isinstance(manifest, Mapping) or set(manifest) != set(_ROOT_KEYS):
        raise PhysicalCampaignRebindError("physical campaign rebind fields changed")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["kind"] != REBIND_KIND:
        raise PhysicalCampaignRebindError("physical campaign rebind identity changed")
    namespace = manifest["namespace"]
    if not isinstance(namespace, str) or _NAMESPACE_RE.fullmatch(namespace) is None:
        raise PhysicalCampaignRebindError("physical campaign namespace is invalid")
    try:
        source = validate_campaign_contract(source_campaign)
        anchor = validate_campaign_contract(physical_anchor_campaign)
    except CampaignContractError as error:
        raise PhysicalCampaignRebindError(f"campaign validation failed: {error}") from error
    _validate_anchor_compatibility(source, anchor)
    expected_binding = _binding_record(
        namespace=namespace,
        source=source,
        anchor=anchor,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    if manifest["source"] != _record(source, role="frozen-offline-source"):
        raise PhysicalCampaignRebindError("source campaign record changed")
    if manifest["physical_anchor"] != _record(
        anchor, role="physical-panel-firmware-anchor"
    ):
        raise PhysicalCampaignRebindError("physical anchor campaign record changed")
    if manifest["binding"] != expected_binding:
        raise PhysicalCampaignRebindError(
            "binding does not match the actual review artifact bytes"
        )
    expected_campaign, expected_map = _rebuild_campaign(
        source,
        panel=anchor["panel"],
        campaign_id=_new_campaign_id(namespace, expected_binding["canonical_sha256"]),
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    if (
        manifest["physical_campaign"] != expected_campaign
        or manifest["action_identity_map"] != expected_map
        or manifest["classification"] != _classification()
    ):
        raise PhysicalCampaignRebindError(
            "physical campaign differs from deterministic reconstruction"
        )
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    expected_integrity = {
        "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
        "canonical_sha256_scope": REBIND_HASH_SCOPE,
    }
    if integrity != expected_integrity:
        raise PhysicalCampaignRebindError("physical campaign rebind integrity is invalid")
    _validate_lineage(
        manifest,
        source=source,
        anchor=anchor,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    return manifest


def _strict_campaign_file(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        snapshot = read_local_regular_file(
            path, label=label, maximum_bytes=MAX_CAMPAIGN_JSON_BYTES
        )
    except ProductionProfileError as error:
        raise PhysicalCampaignRebindError(str(error)) from error
    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                PhysicalCampaignRebindError(
                    f"{label} contains forbidden number {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalCampaignRebindError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise PhysicalCampaignRebindError(f"{label} JSON root must be an object")
    if snapshot.payload != canonical_json_bytes(value):
        raise PhysicalCampaignRebindError(f"{label} must use canonical JSON bytes")
    try:
        return validate_campaign_contract(value)
    except CampaignContractError as error:
        raise PhysicalCampaignRebindError(f"{label} is invalid: {error}") from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PhysicalCampaignRebindError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def read_standalone_physical_campaign(path: Path) -> Mapping[str, Any]:
    """Read one canonical, non-placeholder campaign for production tooling."""

    campaign = _strict_campaign_file(path, label="standalone physical campaign")
    _physical_panel(campaign)
    return campaign


def read_physical_campaign_rebind_manifest(path: Path) -> Mapping[str, Any]:
    """Read one canonical rebind manifest and verify its self-integrity.

    Full lineage validation still requires :func:`validate_physical_campaign_rebind`
    with the source, anchor, and actual review bytes.
    """

    try:
        snapshot = read_local_regular_file(
            path,
            label="physical campaign rebind manifest",
            maximum_bytes=MAX_CAMPAIGN_JSON_BYTES,
        )
    except ProductionProfileError as error:
        raise PhysicalCampaignRebindError(str(error)) from error
    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                PhysicalCampaignRebindError(
                    "physical campaign rebind manifest contains forbidden "
                    f"number {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalCampaignRebindError(
            f"physical campaign rebind manifest is invalid UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, Mapping) or set(value) != set(_ROOT_KEYS):
        raise PhysicalCampaignRebindError("physical campaign rebind fields changed")
    if snapshot.payload != canonical_json_bytes(value):
        raise PhysicalCampaignRebindError(
            "physical campaign rebind manifest must use canonical JSON bytes"
        )
    unsigned = dict(value)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
        "canonical_sha256_scope": REBIND_HASH_SCOPE,
    }:
        raise PhysicalCampaignRebindError(
            "physical campaign rebind manifest integrity is invalid"
        )
    return value


def _reject_reparse_chain(path: Path, *, label: str) -> None:
    try:
        lexical = path.absolute()
    except OSError as error:
        raise PhysicalCampaignRebindError(
            f"{label} cannot be made absolute: {error}"
        ) from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise PhysicalCampaignRebindError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise PhysicalCampaignRebindError(
                f"{label} must not contain a symlink or Windows reparse point"
            )


def _bundle_destination(path: Path) -> Path:
    _reject_reparse_chain(path, label="physical rebind bundle output")
    if os.path.lexists(path):
        raise PhysicalCampaignRebindError(
            "physical rebind bundle output already exists; refusing overwrite"
        )
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise PhysicalCampaignRebindError(
            f"physical rebind bundle parent is unavailable: {error}"
        ) from error
    _reject_reparse_chain(parent, label="physical rebind bundle parent")
    if not parent.is_dir():
        raise PhysicalCampaignRebindError(
            "physical rebind bundle parent must be a directory"
        )
    return parent / path.name


def _write_staged(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise PhysicalCampaignRebindError(
            f"could not stage {path.name}: {error}"
        ) from error


def publish_physical_campaign_rebind_bundle(
    source_campaign_file: Path,
    physical_anchor_campaign_file: Path,
    binding_review_artifact_file: Path,
    output_directory: Path,
    *,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Atomically publish a manifest plus standalone production campaign.

    The destination directory itself is created by one exclusive rename.  An
    existing destination is never merged with or overwritten.
    """

    destination = _bundle_destination(output_directory)
    manifest = compile_physical_campaign_rebind_from_files(
        source_campaign_file,
        physical_anchor_campaign_file,
        binding_review_artifact_file,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    campaign_payload = canonical_json_bytes(manifest["physical_campaign"])
    manifest_payload = canonical_json_bytes(manifest)
    staging = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    published = False
    try:
        staging.mkdir()
        campaign_staging = staging / PHYSICAL_CAMPAIGN_FILENAME
        manifest_staging = staging / REBIND_MANIFEST_FILENAME
        _write_staged(campaign_staging, campaign_payload)
        _write_staged(manifest_staging, manifest_payload)
        if (
            campaign_staging.read_bytes() != campaign_payload
            or manifest_staging.read_bytes() != manifest_payload
        ):
            raise PhysicalCampaignRebindError("staged physical rebind bytes changed")
        if os.path.lexists(destination):
            raise PhysicalCampaignRebindError(
                "physical rebind bundle output appeared; refusing overwrite"
            )
        os.rename(staging, destination)
        published = True
    except PhysicalCampaignRebindError:
        raise
    except OSError as error:
        raise PhysicalCampaignRebindError(
            f"could not atomically publish physical rebind bundle: {error}"
        ) from error
    finally:
        if not published:
            for name in (PHYSICAL_CAMPAIGN_FILENAME, REBIND_MANIFEST_FILENAME):
                try:
                    (staging / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass
    return manifest


def compile_physical_campaign_rebind_from_files(
    source_campaign_file: Path,
    physical_anchor_campaign_file: Path,
    binding_review_artifact_file: Path,
    *,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Safely read real local inputs once, then compile one rebind artifact."""

    source = _strict_campaign_file(source_campaign_file, label="source campaign")
    anchor = _strict_campaign_file(
        physical_anchor_campaign_file, label="physical anchor campaign"
    )
    try:
        review = read_local_regular_file(
            binding_review_artifact_file,
            label="physical binding review artifact",
            maximum_bytes=MAX_BINDING_REVIEW_BYTES,
        )
    except ProductionProfileError as error:
        raise PhysicalCampaignRebindError(str(error)) from error
    return compile_physical_campaign_rebind(
        source,
        anchor,
        namespace=namespace,
        binding_review_bytes=review.payload,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


__all__ = [
    "BINDING_HASH_SCOPE",
    "MAX_BINDING_REVIEW_BYTES",
    "MAX_CAMPAIGN_JSON_BYTES",
    "PHYSICAL_CAMPAIGN_FILENAME",
    "PhysicalCampaignRebindError",
    "REBIND_HASH_SCOPE",
    "REBIND_KIND",
    "REBIND_MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "compile_physical_campaign_rebind",
    "compile_physical_campaign_rebind_from_files",
    "publish_physical_campaign_rebind_bundle",
    "read_physical_campaign_rebind_manifest",
    "read_standalone_physical_campaign",
    "validate_physical_campaign_rebind",
]
