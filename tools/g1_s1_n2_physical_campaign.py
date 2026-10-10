#!/usr/bin/env python3
"""Materialize the frozen N2P candidates for one reviewed physical panel.

The original N2P compiler intentionally binds its campaign to the
``UNBOUND-N2P-OFFLINE`` placeholder.  This module never edits or reinterprets
that artifact.  It verifies the exact frozen source manifest and candidates,
binds them to one explicit physical-panel object plus the bytes of a local
binding-review artifact, and rebuilds every campaign/action/session identity.

Materialization performs no device or network I/O, creates no execution claim,
and grants no authorization.  Its bundled limit-profile object is deliberately
an unapproved, all-null draft that must be completed and reviewed separately.
"""

from __future__ import annotations

import argparse
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
    LIMIT_PROFILE_KIND,
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    seal_campaign_contract,
    seal_limit_profile,
    validate_campaign_contract,
    validate_limit_profile,
)
from tools import g1_s1_rc2g_n2_photo_campaign as frozen  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-rc2g-n2p-physical-bound-operator-manifest"
BINDING_KIND = "mf1750-g1-s1-rc2g-n2p-physical-panel-binding"
MANIFEST_HASH_SCOPE = (
    "entire physical-bound operator manifest excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
BINDING_HASH_SCOPE = (
    "entire physical-panel binding excluding integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
PHYSICAL_CAMPAIGN_ID_PREFIX = "g1-s1-rc2g-n2p-physical-"
OPERATOR_MANIFEST_ID_PREFIX = "g1-s1-rc2g-n2p-operator-"
PROFILE_DRAFT_ID_PREFIX = "n2p-physical-limit-draft-"
PROCESS_SCHEDULE_KIND = "mf1750-g1-s1-n2p-operator-process-schedule"
PROCESS_SCHEDULE_CLASSIFICATION = (
    "operator_selected_supervised_process_schedule_not_supplier_rating"
)
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
OPERATOR_MANIFEST_FILENAME = "PHYSICAL-OPERATOR-MANIFEST.json"

SOURCE_OUTER_CANONICAL_SHA256 = (
    "976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b"
)
SOURCE_OUTER_FILE_SHA256 = (
    "d7d55f62f6e2392d42dd8d65ea5cd5d7c0c5179b4cd51b9109666b420a21d687"
)
SOURCE_P0_CANONICAL_SHA256 = (
    "f23476c4c887057877e3f3f6c9315813bb761f6da57996b9eea538584a545cdb"
)
FIXED_ACTION_KEYS = tuple(
    f"q{cell}-{'map-primer' if phase == 'map-primer' else 'target'}"
    for cell in range(1, 5)
    for phase in ("map-primer", "target")
)

_PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "operator_manifest_id",
        "source",
        "physical_binding",
        "operator_process_schedule",
        "physical_campaign_file",
        "physical_campaign_contract",
        "fixed_actions",
        "execution_contract",
        "limit_profile_draft",
        "limit_profile_draft_notice",
        "classification",
        "integrity",
    }
)
_PROCESS_SCHEDULE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "classification",
        "not_a_supplier_rating",
        "minimum_interval_seconds",
        "planned_cooldown_seconds",
    }
)


class N2PhysicalCampaignError(RuntimeError):
    """Raised when physical materialization cannot remain exact and fail-closed."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _normalized_seconds(
    value: Any, *, label: str, strictly_positive: bool
) -> int | float:
    if type(value) is int:
        pass
    elif type(value) is float and math.isfinite(value):
        pass
    else:
        raise N2PhysicalCampaignError(f"{label} must be a finite number")
    if value < 0 or (strictly_positive and value == 0):
        qualifier = "positive" if strictly_positive else "nonnegative"
        raise N2PhysicalCampaignError(f"{label} must be {qualifier}")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _operator_process_schedule(
    minimum_interval_seconds: Any,
    planned_cooldown_seconds: Any,
) -> dict[str, Any]:
    """Normalize the operator's process schedule without treating it as a rating."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PROCESS_SCHEDULE_KIND,
        "classification": PROCESS_SCHEDULE_CLASSIFICATION,
        "not_a_supplier_rating": True,
        "minimum_interval_seconds": _normalized_seconds(
            minimum_interval_seconds,
            label="minimum_interval_seconds",
            strictly_positive=True,
        ),
        "planned_cooldown_seconds": _normalized_seconds(
            planned_cooldown_seconds,
            label="planned_cooldown_seconds",
            strictly_positive=False,
        ),
    }


def _validate_operator_process_schedule(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PROCESS_SCHEDULE_KEYS:
        raise N2PhysicalCampaignError("operator process schedule fields changed")
    expected = _operator_process_schedule(
        value.get("minimum_interval_seconds"),
        value.get("planned_cooldown_seconds"),
    )
    if dict(value) != expected:
        raise N2PhysicalCampaignError(
            "operator process schedule classification or values changed"
        )
    return expected


def manifest_file_sha256(manifest: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical whole-file manifest bytes."""

    return _sha256(canonical_json_bytes(manifest))


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    try:
        lexical = path.absolute()
    except OSError as error:
        raise N2PhysicalCampaignError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise N2PhysicalCampaignError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise N2PhysicalCampaignError(
                f"{label} leaf and ancestors must not be a symlink or reparse point"
            )


def _safe_existing_file(path: Path, *, label: str) -> Path:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise N2PhysicalCampaignError(str(error)) from error
    _reject_reparse_path_chain(path, label=label)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise N2PhysicalCampaignError(f"{label} does not resolve locally: {error}") from error
    if path.is_symlink() or resolved.is_symlink() or not resolved.is_file():
        raise N2PhysicalCampaignError(f"{label} must be a real local regular file")
    return resolved


def _safe_bundle_directory(path: Path, *, must_exist: bool) -> Path:
    label = "physical-bound N2P bundle directory"
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise N2PhysicalCampaignError(str(error)) from error
    _reject_reparse_path_chain(path, label=label)
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise N2PhysicalCampaignError(f"{label} does not exist: {error}") from error
        if path.is_symlink() or resolved.is_symlink() or not resolved.is_dir():
            raise N2PhysicalCampaignError(f"{label} must be a real local directory")
        return resolved
    if os.path.lexists(path):
        raise N2PhysicalCampaignError(f"{label} already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N2PhysicalCampaignError(f"{label} parent does not exist: {error}") from error
    if path.parent.is_symlink() or not parent.is_dir():
        raise N2PhysicalCampaignError(f"{label} parent must be a real local directory")
    destination = parent / path.name
    if os.path.lexists(destination):
        raise N2PhysicalCampaignError(f"{label} already exists; refusing overwrite")
    return destination


def _strict_json_object_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    if not isinstance(path, Path):
        raise N2PhysicalCampaignError(f"{label} path must be pathlib.Path")
    resolved = _safe_existing_file(path, label=label)
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise N2PhysicalCampaignError(f"could not read {label}: {error}") from error

    def reject_constant(token: str) -> None:
        raise ValueError(f"forbidden JSON constant {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise N2PhysicalCampaignError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(parsed, Mapping):
        raise N2PhysicalCampaignError(f"{label} root must be an object")
    if payload != canonical_json_bytes(parsed):
        raise N2PhysicalCampaignError(f"{label} must use exact canonical JSON bytes")
    return parsed, payload


def _read_review_artifact(path: Path) -> bytes:
    resolved = _safe_existing_file(path, label="physical binding review artifact")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise N2PhysicalCampaignError(
            f"could not read physical binding review artifact: {error}"
        ) from error
    if not payload:
        raise N2PhysicalCampaignError("physical binding review artifact must not be empty")
    return payload


def _validate_panel(panel: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(panel, Mapping) or set(panel) != _PANEL_KEYS:
        raise N2PhysicalCampaignError("physical panel must contain the four exact panel fields")
    normalized: dict[str, str] = {}
    for field in ("model", "serial", "board_id", "pcb_revision"):
        value = panel[field]
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 256
            or any(ord(character) < 0x20 for character in value)
        ):
            raise N2PhysicalCampaignError(
                f"physical panel.{field} must be non-empty normalized text"
            )
        normalized[field] = value
    source_panel = frozen.PANEL_CONTRACT
    for field in ("model", "board_id", "pcb_revision"):
        if normalized[field] != source_panel[field]:
            raise N2PhysicalCampaignError(
                f"physical panel.{field} does not match the frozen candidate hardware"
            )
    if (
        normalized["serial"] == source_panel["serial"]
        or "UNBOUND" in normalized["serial"].upper()
    ):
        raise N2PhysicalCampaignError(
            "physical panel.serial must identify one real non-UNBOUND panel instance"
        )
    return normalized


def _review_artifact_record(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload:
        raise N2PhysicalCampaignError("physical binding review artifact bytes are required")
    return {
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "content_addressed": True,
        "local_path_not_trusted_after_materialization": True,
    }


def _load_frozen_source_manifest(path: Path) -> Mapping[str, Any]:
    source, payload = _strict_json_object_file(path, label="frozen N2P source manifest")
    try:
        frozen.validate_compiled_manifest(source)
        freshly_compiled = frozen.compile_campaign_manifest()
    except (
        CampaignContractError,
        frozen.N2PhotoCampaignError,
        OSError,
        ValueError,
    ) as error:
        raise N2PhysicalCampaignError(f"frozen N2P source validation failed: {error}") from error
    if (
        frozen.EXPECTED_MANIFEST_CANONICAL_SHA256 != SOURCE_OUTER_CANONICAL_SHA256
        or frozen.EXPECTED_MANIFEST_FILE_SHA256 != SOURCE_OUTER_FILE_SHA256
        or source["manifest_integrity"]["canonical_sha256"]
        != SOURCE_OUTER_CANONICAL_SHA256
        or _sha256(payload) != SOURCE_OUTER_FILE_SHA256
        or source["p0_campaign_contract"]["integrity"]["canonical_sha256"]
        != SOURCE_P0_CANONICAL_SHA256
        or source != freshly_compiled
        or payload != canonical_json_bytes(freshly_compiled)
    ):
        raise N2PhysicalCampaignError(
            "source manifest is not the exact freshly revalidated frozen N2P candidate set"
        )
    return source


def _fresh_frozen_source() -> Mapping[str, Any]:
    try:
        source = frozen.compile_campaign_manifest()
        frozen.validate_compiled_manifest(source)
    except (
        CampaignContractError,
        frozen.N2PhotoCampaignError,
        OSError,
        ValueError,
    ) as error:
        raise N2PhysicalCampaignError(f"frozen N2P source validation failed: {error}") from error
    if (
        source["manifest_integrity"]["canonical_sha256"]
        != SOURCE_OUTER_CANONICAL_SHA256
        or manifest_file_sha256(source) != SOURCE_OUTER_FILE_SHA256
        or source["p0_campaign_contract"]["integrity"]["canonical_sha256"]
        != SOURCE_P0_CANONICAL_SHA256
    ):
        raise N2PhysicalCampaignError("freshly compiled N2P source identity changed")
    return source


def _action_key(action: Mapping[str, Any]) -> str:
    identity = action["identity"]
    phase = identity["phase"]
    if phase not in {"map-primer", "target"}:
        raise N2PhysicalCampaignError("frozen N2P action phase is unsupported")
    return f"{str(identity['cell_id']).lower()}-{phase}"


def _source_record(source: Mapping[str, Any]) -> dict[str, Any]:
    candidate_bindings = []
    for cell in source["cells"]:
        candidate = cell["candidate"]
        artifact = candidate["artifact"]
        frame = candidate["frame"]
        candidate_bindings.append(
            {
                "cell_id": cell["cell_id"],
                "algorithm": cell["algorithm"],
                "artifact_manifest_canonical_sha256": artifact[
                    "manifest_canonical_sha256"
                ],
                "artifact_manifest_file_sha256": artifact["manifest_file_sha256"],
                "frame_sha256": frame["sha256"],
                "frame_fnv1a": frame["fnv1a"],
                "codes_sha256": frame["codes_sha256"],
            }
        )
    return {
        "compiler_module": "tools.g1_s1_rc2g_n2_photo_campaign",
        "outer_manifest_kind": frozen.MANIFEST_KIND,
        "outer_manifest_canonical_sha256": SOURCE_OUTER_CANONICAL_SHA256,
        "outer_manifest_file_sha256": SOURCE_OUTER_FILE_SHA256,
        "p0_campaign_canonical_sha256": SOURCE_P0_CANONICAL_SHA256,
        "campaign_id": frozen.CAMPAIGN_ID,
        "offline_panel": dict(frozen.PANEL_CONTRACT),
        "candidate_bindings": candidate_bindings,
    }


def _physical_binding(
    source: Mapping[str, Any],
    panel: Mapping[str, str],
    review_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": BINDING_KIND,
        "source_outer_manifest_canonical_sha256": source["manifest_integrity"][
            "canonical_sha256"
        ],
        "source_p0_campaign_canonical_sha256": source["p0_campaign_contract"][
            "integrity"
        ]["canonical_sha256"],
        "panel": dict(panel),
        "binding_review_artifact": dict(review_artifact),
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": BINDING_HASH_SCOPE,
        },
    }


def _materialize_campaign(
    source: Mapping[str, Any],
    panel: Mapping[str, str],
    materialization_sha256: str,
    process_schedule: Mapping[str, Any],
) -> Mapping[str, Any]:
    source_campaign = source["p0_campaign_contract"]
    campaign_id = f"{PHYSICAL_CAMPAIGN_ID_PREFIX}{materialization_sha256}"
    source_actions = {
        action["action_identity_sha256"]: action for action in source_campaign["actions"]
    }
    materialized_actions: list[Mapping[str, Any]] = []
    materialized_sessions: list[Mapping[str, Any]] = []
    replacement_by_source_sha: dict[str, Mapping[str, Any]] = {}

    for source_session in source_campaign["sessions"]:
        replacement_hashes: list[str] = []
        for source_sha in source_session["action_identity_sha256s"]:
            source_action = source_actions[source_sha]
            identity = source_action["identity"]
            prior = identity["prior"]
            replacement_prior_sha: Optional[str] = None
            replacement_prior_scope: Optional[str] = None
            if prior is not None:
                replacement_prior = replacement_by_source_sha.get(
                    prior["action_identity_sha256"]
                )
                if replacement_prior is None:
                    raise N2PhysicalCampaignError(
                        "source action prior is not ordered before its dependent action"
                    )
                replacement_prior_sha = replacement_prior["action_identity_sha256"]
                replacement_prior_scope = prior["scope"]
            replacement = build_fixed_action_declaration(
                campaign_id=campaign_id,
                session_id=identity["session_id"],
                cell_id=identity["cell_id"],
                action_id=identity["action_id"],
                phase=identity["phase"],
                frame=identity["frame"],
                endpoint=identity["request"]["endpoint"],
                prior_action_identity_sha256=replacement_prior_sha,
                prior_scope=replacement_prior_scope,
                minimum_interval_since_prior_seconds=(
                    0
                    if prior is None
                    else process_schedule["minimum_interval_seconds"]
                ),
            )
            replacement_by_source_sha[source_sha] = replacement
            materialized_actions.append(replacement)
            replacement_hashes.append(replacement["action_identity_sha256"])
        materialized_sessions.append(
            build_session_contract(
                session_id=source_session["session_id"],
                cell_id=source_session["cell_id"],
                power_mode=source_session["power_mode"],
                planned_cooldown_seconds=process_schedule[
                    "planned_cooldown_seconds"
                ],
                final_power_off_required=source_session["final_power_off_required"],
                action_identity_sha256s=replacement_hashes,
                minimum_panel_power_off_seconds=source_session[
                    "minimum_panel_power_off_seconds"
                ],
            )
        )
    try:
        return seal_campaign_contract(
            {
                "schema_version": 1,
                "kind": source_campaign["kind"],
                "campaign_id": campaign_id,
                "panel": dict(panel),
                "firmware": dict(source_campaign["firmware"]),
                "actions": materialized_actions,
                "sessions": materialized_sessions,
                "classification": dict(source_campaign["classification"]),
            }
        )
    except CampaignContractError as error:
        raise N2PhysicalCampaignError(
            f"physical-bound N2P campaign validation failed: {error}"
        ) from error


def _fixed_actions(campaign: Mapping[str, Any]) -> dict[str, str]:
    actions = {_action_key(action): action["action_identity_sha256"] for action in campaign["actions"]}
    if tuple(actions) != FIXED_ACTION_KEYS:
        raise N2PhysicalCampaignError("physical campaign action order or membership changed")
    return actions


def _physical_campaign_file_record(campaign: Mapping[str, Any]) -> dict[str, Any]:
    payload = canonical_json_bytes(campaign)
    return {
        "filename": PHYSICAL_CAMPAIGN_FILENAME,
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "exact_root_kind": campaign["kind"],
    }


def _action_allowlist(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    allowlist = []
    for action in campaign["actions"]:
        identity = action["identity"]
        allowlist.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": identity["request"]["method"],
                "endpoint": identity["request"]["endpoint"],
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    return allowlist


def _limit_profile_draft(
    campaign: Mapping[str, Any], binding_sha256: str
) -> Mapping[str, Any]:
    try:
        return seal_limit_profile(
            {
                "schema_version": 1,
                "kind": LIMIT_PROFILE_KIND,
                "profile_id": f"{PROFILE_DRAFT_ID_PREFIX}{binding_sha256}",
                "profile_version": "0.0.0",
                "panel": dict(campaign["panel"]),
                "firmware": dict(campaign["firmware"]),
                "action_allowlist": _action_allowlist(campaign),
                "limits": {
                    "maximum_campaign_visible_refreshes": None,
                    "maximum_session_visible_refreshes": None,
                    "maximum_consecutive_visible_refreshes": None,
                    "minimum_interval_seconds": None,
                    "minimum_cooldown_seconds": None,
                    "minimum_start_temperature_c": None,
                    "maximum_start_temperature_c": None,
                    "maximum_post_refresh_temperature_c": None,
                },
                "usage": {
                    "cumulative_visible_refresh_count": None,
                    "session_visible_refresh_count": None,
                    "consecutive_visible_refresh_count": None,
                    "last_visible_refresh_completed_at": None,
                    "snapshot_at": None,
                    "evidence_sha256": None,
                },
                "validity": {"valid_from": None, "expires_at": None},
                "review": {
                    "approved": False,
                    "reviewer_id": None,
                    "reviewed_at": None,
                    "review_artifact_sha256": None,
                },
            }
        )
    except CampaignContractError as error:
        raise N2PhysicalCampaignError(f"unapproved profile draft is invalid: {error}") from error


def _execution_contract() -> dict[str, Any]:
    return {
        "selection_mode": "exact_eight_action_enum_from_physical_manifest",
        "physical_binding_required": True,
        "legacy_unbound_action_identities_executable": False,
        "reviewed_limit_profile_required": True,
        "profile_panel_firmware_and_action_allowlist_must_exactly_match": True,
        "operator_process_schedule_required": True,
        "operator_process_schedule_is_limit_authority": False,
        "operator_process_schedule_is_supplier_rating": False,
        "workspace_global_claim_key": "action_identity_sha256",
        "maximum_post_requests_per_action": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _profile_notice() -> dict[str, Any]:
    return {
        "purpose": "field-completion-template-only",
        "approved": False,
        "execution_eligible": False,
        "reviewed_profile_materialized": False,
        "must_be_completed_reviewed_and_resealed_separately": True,
        "must_not_be_presented_as_reviewed_evidence": True,
    }


def _classification() -> dict[str, Any]:
    return {
        "frozen_offline_candidates_unchanged": True,
        "physical_panel_instance_bound": True,
        "binding_review_artifact_bytes_hashed": True,
        "operator_process_schedule_bound": True,
        "operator_process_schedule_is_supplier_rating": False,
        "hardware_execution_authorized": False,
        "reviewed_limit_profile_present": False,
        "reviewed_limit_profile_fabricated": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "visible_refreshes_performed": 0,
    }


def _assemble_manifest(
    source: Mapping[str, Any],
    panel: Mapping[str, str],
    review_artifact: Mapping[str, Any],
    process_schedule: Mapping[str, Any],
) -> dict[str, Any]:
    schedule = _validate_operator_process_schedule(process_schedule)
    binding = _physical_binding(source, panel, review_artifact)
    binding_sha = binding["integrity"]["canonical_sha256"]
    materialization_sha = _sha256(
        canonical_json_bytes(
            {
                "physical_binding_canonical_sha256": binding_sha,
                "operator_process_schedule": schedule,
            }
        )
    )
    campaign = _materialize_campaign(
        source, panel, materialization_sha, schedule
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "operator_manifest_id": f"{OPERATOR_MANIFEST_ID_PREFIX}{materialization_sha}",
        "source": _source_record(source),
        "physical_binding": binding,
        "operator_process_schedule": schedule,
        "physical_campaign_file": _physical_campaign_file_record(campaign),
        "physical_campaign_contract": campaign,
        "fixed_actions": _fixed_actions(campaign),
        "execution_contract": _execution_contract(),
        "limit_profile_draft": _limit_profile_draft(campaign, materialization_sha),
        "limit_profile_draft_notice": _profile_notice(),
        "classification": _classification(),
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
            "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
        },
    }


def _validate_lineage(
    manifest: Mapping[str, Any], source: Mapping[str, Any]
) -> None:
    campaign = manifest["physical_campaign_contract"]
    process_schedule = _validate_operator_process_schedule(
        manifest["operator_process_schedule"]
    )
    try:
        validate_campaign_contract(campaign)
        validate_limit_profile(manifest["limit_profile_draft"])
    except CampaignContractError as error:
        raise N2PhysicalCampaignError(
            f"materialized campaign/profile contract failed: {error}"
        ) from error
    source_campaign = source["p0_campaign_contract"]
    if campaign["campaign_id"] == source_campaign["campaign_id"]:
        raise N2PhysicalCampaignError("physical campaign reused the offline campaign_id")
    if campaign["panel"] == source_campaign["panel"] or "UNBOUND" in campaign["panel"][
        "serial"
    ].upper():
        raise N2PhysicalCampaignError("physical campaign retained an unbound panel")
    source_by_key = {_action_key(action): action for action in source_campaign["actions"]}
    physical_by_key = {_action_key(action): action for action in campaign["actions"]}
    if tuple(source_by_key) != FIXED_ACTION_KEYS or tuple(physical_by_key) != FIXED_ACTION_KEYS:
        raise N2PhysicalCampaignError("source/physical eight-action membership changed")
    source_hashes = {action["action_identity_sha256"] for action in source_by_key.values()}
    physical_hashes = {
        action["action_identity_sha256"] for action in physical_by_key.values()
    }
    if source_hashes & physical_hashes:
        raise N2PhysicalCampaignError("physical campaign reused an offline action identity")
    source_claims = {action["claim"]["filename"] for action in source_by_key.values()}
    physical_claims = {action["claim"]["filename"] for action in physical_by_key.values()}
    if source_claims & physical_claims:
        raise N2PhysicalCampaignError("physical campaign reused an offline claim filename")
    for key in FIXED_ACTION_KEYS:
        old = source_by_key[key]
        new = physical_by_key[key]
        old_identity = old["identity"]
        new_identity = new["identity"]
        expected_schedule = dict(old_identity["schedule"])
        expected_schedule["minimum_interval_since_prior_seconds"] = (
            0
            if old_identity["prior"] is None
            else process_schedule["minimum_interval_seconds"]
        )
        if (
            new_identity["campaign_id"] != campaign["campaign_id"]
            or new_identity["session_id"] != old_identity["session_id"]
            or new_identity["cell_id"] != old_identity["cell_id"]
            or new_identity["action_id"] != old_identity["action_id"]
            or new_identity["phase"] != old_identity["phase"]
            or new_identity["frame"] != old_identity["frame"]
            or new_identity["request"] != old_identity["request"]
            or new_identity["schedule"] != expected_schedule
        ):
            raise N2PhysicalCampaignError(f"{key} changed frozen action semantics")
        old_prior = old_identity["prior"]
        new_prior = new_identity["prior"]
        if old_prior is None:
            if new_prior is not None:
                raise N2PhysicalCampaignError(f"{key} unexpectedly gained a prior")
        else:
            old_prior_key = next(
                candidate_key
                for candidate_key, candidate in source_by_key.items()
                if candidate["action_identity_sha256"]
                == old_prior["action_identity_sha256"]
            )
            if (
                new_prior is None
                or new_prior["action_identity_sha256"]
                != physical_by_key[old_prior_key]["action_identity_sha256"]
                or new_prior["scope"] != old_prior["scope"]
                or new_prior["required_result_state"]
                != old_prior["required_result_state"]
            ):
                raise N2PhysicalCampaignError(f"{key} prior was not rebuilt in the new identity set")
    source_sessions = {
        session["session_id"]: session for session in source_campaign["sessions"]
    }
    if len(campaign["sessions"]) != len(source_sessions):
        raise N2PhysicalCampaignError("physical campaign session membership changed")
    for session in campaign["sessions"]:
        source_session = source_sessions.get(session["session_id"])
        if source_session is None:
            raise N2PhysicalCampaignError("physical campaign gained an unknown session")
        if (
            session["cell_id"] != source_session["cell_id"]
            or session["power_mode"] != source_session["power_mode"]
            or session["planned_cooldown_seconds"]
            != process_schedule["planned_cooldown_seconds"]
            or session["final_power_off_required"]
            != source_session["final_power_off_required"]
            or session["minimum_panel_power_off_seconds"]
            != source_session["minimum_panel_power_off_seconds"]
        ):
            raise N2PhysicalCampaignError(
                "physical campaign session/process schedule changed"
            )
    draft = manifest["limit_profile_draft"]
    if (
        draft["panel"] != campaign["panel"]
        or draft["firmware"] != campaign["firmware"]
        or draft["action_allowlist"] != _action_allowlist(campaign)
        or draft["review"]
        != {
            "approved": False,
            "reviewer_id": None,
            "reviewed_at": None,
            "review_artifact_sha256": None,
        }
        or any(value is not None for value in draft["limits"].values())
        or any(value is not None for value in draft["usage"].values())
        or any(value is not None for value in draft["validity"].values())
    ):
        raise N2PhysicalCampaignError("limit profile draft is not exact, null, and unapproved")


def _validate_against_source(
    manifest: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    review_artifact_payload: Optional[bytes] = None,
) -> Mapping[str, Any]:
    if not isinstance(manifest, Mapping) or set(manifest) != _ROOT_KEYS:
        raise N2PhysicalCampaignError("physical operator manifest fields changed")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["kind"] != MANIFEST_KIND:
        raise N2PhysicalCampaignError("physical operator manifest identity changed")
    binding = manifest["physical_binding"]
    if not isinstance(binding, Mapping):
        raise N2PhysicalCampaignError("physical binding is missing")
    panel = _validate_panel(binding.get("panel"))
    process_schedule = _validate_operator_process_schedule(
        manifest.get("operator_process_schedule")
    )
    review_record = binding.get("binding_review_artifact")
    if not isinstance(review_record, Mapping) or set(review_record) != {
        "bytes",
        "sha256",
        "content_addressed",
        "local_path_not_trusted_after_materialization",
    }:
        raise N2PhysicalCampaignError("binding review artifact record changed")
    if (
        type(review_record["bytes"]) is not int
        or review_record["bytes"] <= 0
        or not isinstance(review_record["sha256"], str)
        or len(review_record["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in review_record["sha256"])
        or review_record["content_addressed"] is not True
        or review_record["local_path_not_trusted_after_materialization"] is not True
    ):
        raise N2PhysicalCampaignError("binding review artifact record is invalid")
    if (
        review_artifact_payload is not None
        and dict(review_record) != _review_artifact_record(review_artifact_payload)
    ):
        raise N2PhysicalCampaignError("binding review artifact bytes/hash no longer match")
    expected = _assemble_manifest(source, panel, review_record, process_schedule)
    if manifest != expected:
        raise N2PhysicalCampaignError(
            "physical operator manifest differs from exact deterministic materialization"
        )
    _validate_lineage(manifest, source)
    return manifest


def compile_physical_manifest(
    source_manifest_file: Path,
    panel: Mapping[str, Any],
    binding_review_artifact_file: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Build one canonical physical-bound manifest entirely in memory."""

    source = _load_frozen_source_manifest(source_manifest_file)
    physical_panel = _validate_panel(panel)
    artifact_payload = _read_review_artifact(binding_review_artifact_file)
    process_schedule = _operator_process_schedule(
        minimum_interval_seconds, planned_cooldown_seconds
    )
    manifest = _assemble_manifest(
        source,
        physical_panel,
        _review_artifact_record(artifact_payload),
        process_schedule,
    )
    _validate_against_source(
        manifest, source, review_artifact_payload=artifact_payload
    )
    return manifest


def compile_physical_manifest_from_files(
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Strict file-input wrapper around :func:`compile_physical_manifest`."""

    panel, _payload = _strict_json_object_file(panel_file, label="physical panel object")
    return compile_physical_manifest(
        source_manifest_file,
        panel,
        binding_review_artifact_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


def validate_physical_manifest(
    manifest: Mapping[str, Any],
    *,
    binding_review_artifact_payload: Optional[bytes] = None,
) -> Mapping[str, Any]:
    """Deep-validate a manifest against a fresh frozen-candidate compilation."""

    source = _fresh_frozen_source()
    return _validate_against_source(
        manifest,
        source,
        review_artifact_payload=binding_review_artifact_payload,
    )


def read_physical_manifest(
    path: Path,
    *,
    binding_review_artifact_file: Optional[Path] = None,
) -> Mapping[str, Any]:
    """Read canonical manifest bytes and optionally re-hash the review artifact."""

    manifest, _payload = _strict_json_object_file(
        path, label="physical-bound N2P operator manifest"
    )
    review_payload = (
        _read_review_artifact(binding_review_artifact_file)
        if binding_review_artifact_file is not None
        else None
    )
    return validate_physical_manifest(
        manifest, binding_review_artifact_payload=review_payload
    )


def validate_physical_manifest_file(
    manifest_file: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
) -> Mapping[str, Any]:
    """Revalidate a stored operator manifest against all original local inputs."""

    manifest, _manifest_payload = _strict_json_object_file(
        manifest_file, label="physical-bound N2P operator manifest"
    )
    source = _load_frozen_source_manifest(source_manifest_file)
    panel, _panel_payload = _strict_json_object_file(
        panel_file, label="physical panel object"
    )
    physical_panel = _validate_panel(panel)
    artifact_payload = _read_review_artifact(binding_review_artifact_file)
    validated = _validate_against_source(
        manifest, source, review_artifact_payload=artifact_payload
    )
    if validated["physical_binding"]["panel"] != physical_panel:
        raise N2PhysicalCampaignError("panel file differs from the materialized panel")
    return validated


def _write_staged_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise N2PhysicalCampaignError(f"could not stage {path.name}: {error}") from error


def publish_physical_bundle(
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
    output_directory: Path,
    *,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Compile and atomically publish the exact campaign/operator file pair."""

    destination = _safe_bundle_directory(
        output_directory, must_exist=False
    )
    manifest = compile_physical_manifest_from_files(
        source_manifest_file,
        panel_file,
        binding_review_artifact_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    campaign_payload = canonical_json_bytes(manifest["physical_campaign_contract"])
    manifest_payload = canonical_json_bytes(manifest)
    staging = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    published = False
    try:
        staging.mkdir()
        campaign_staging = staging / PHYSICAL_CAMPAIGN_FILENAME
        manifest_staging = staging / OPERATOR_MANIFEST_FILENAME
        _write_staged_file(campaign_staging, campaign_payload)
        _write_staged_file(manifest_staging, manifest_payload)
        if (
            campaign_staging.read_bytes() != campaign_payload
            or manifest_staging.read_bytes() != manifest_payload
        ):
            raise N2PhysicalCampaignError("staged physical bundle bytes changed")
        if os.path.lexists(destination):
            raise N2PhysicalCampaignError(
                "physical-bound N2P bundle directory appeared; refusing overwrite"
            )
        os.rename(staging, destination)
        published = True
    except OSError as error:
        raise N2PhysicalCampaignError(
            f"could not atomically publish physical-bound N2P bundle: {error}"
        ) from error
    finally:
        if not published:
            for name in (PHYSICAL_CAMPAIGN_FILENAME, OPERATOR_MANIFEST_FILENAME):
                try:
                    (staging / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass
    return manifest


def read_physical_campaign(path: Path) -> Mapping[str, Any]:
    """Read one standalone canonical campaign suitable for profile tooling."""

    campaign, _payload = _strict_json_object_file(
        path, label="standalone physical N2P campaign"
    )
    try:
        validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N2PhysicalCampaignError(f"standalone physical campaign is invalid: {error}") from error
    _validate_panel(campaign["panel"])
    return campaign


def _bundle_paths(directory: Path) -> tuple[Path, Path]:
    bundle = _safe_bundle_directory(directory, must_exist=True)
    try:
        entries = tuple(bundle.iterdir())
    except OSError as error:
        raise N2PhysicalCampaignError(f"could not enumerate physical bundle: {error}") from error
    expected = {PHYSICAL_CAMPAIGN_FILENAME, OPERATOR_MANIFEST_FILENAME}
    if {entry.name for entry in entries} != expected or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise N2PhysicalCampaignError(
            "physical bundle must contain exactly the canonical campaign and operator files"
        )
    return bundle / PHYSICAL_CAMPAIGN_FILENAME, bundle / OPERATOR_MANIFEST_FILENAME


def _bind_standalone_campaign(
    manifest: Mapping[str, Any], campaign: Mapping[str, Any]
) -> None:
    if (
        campaign != manifest["physical_campaign_contract"]
        or manifest["physical_campaign_file"]
        != _physical_campaign_file_record(campaign)
    ):
        raise N2PhysicalCampaignError(
            "standalone physical campaign does not exactly match the operator manifest"
        )


def read_physical_bundle(
    directory: Path,
    *,
    binding_review_artifact_file: Optional[Path] = None,
) -> Mapping[str, Any]:
    """Read and bind the two canonical bundle files without original-path trust."""

    campaign_file, manifest_file = _bundle_paths(directory)
    manifest = read_physical_manifest(
        manifest_file,
        binding_review_artifact_file=binding_review_artifact_file,
    )
    campaign = read_physical_campaign(campaign_file)
    _bind_standalone_campaign(manifest, campaign)
    return manifest


def validate_physical_bundle(
    directory: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
) -> Mapping[str, Any]:
    """Deep-bind both stored files to every original materialization input."""

    campaign_file, manifest_file = _bundle_paths(directory)
    manifest = validate_physical_manifest_file(
        manifest_file,
        source_manifest_file,
        panel_file,
        binding_review_artifact_file,
    )
    campaign = read_physical_campaign(campaign_file)
    _bind_standalone_campaign(manifest, campaign)
    return manifest


def _description(manifest: Mapping[str, Any], *, mode: str) -> dict[str, Any]:
    campaign = manifest["physical_campaign_contract"]
    return {
        "ok": True,
        "mode": mode,
        "kind": manifest["kind"],
        "operator_manifest_id": manifest["operator_manifest_id"],
        "operator_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "operator_manifest_file_sha256": manifest_file_sha256(manifest),
        "physical_binding_canonical_sha256": manifest["physical_binding"][
            "integrity"
        ]["canonical_sha256"],
        "physical_campaign_id": campaign["campaign_id"],
        "physical_campaign_canonical_sha256": campaign["integrity"][
            "canonical_sha256"
        ],
        "physical_campaign_file": dict(manifest["physical_campaign_file"]),
        "panel": dict(campaign["panel"]),
        "operator_process_schedule": dict(manifest["operator_process_schedule"]),
        "fixed_actions": dict(manifest["fixed_actions"]),
        "all_action_identities_and_claims_new": True,
        "limit_profile_draft_approved": False,
        "reviewed_limit_profile_present": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def describe_physical_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a zero-I/O description after full in-memory validation."""

    validated = validate_physical_manifest(manifest)
    return _description(validated, mode="describe-only")


def describe_physical_bundle(
    directory: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
) -> dict[str, Any]:
    validated = validate_physical_bundle(
        directory,
        source_manifest_file,
        panel_file,
        binding_review_artifact_file,
    )
    return _description(validated, mode="describe-only")


def _add_original_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--panel-file", type=Path, required=True)
    parser.add_argument("--binding-review-artifact", type=Path, required=True)


def _seconds_argument(value: str, *, strictly_positive: bool) -> int | float:
    try:
        parsed = json.loads(
            value,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"forbidden number {token}")
            ),
        )
        return _normalized_seconds(
            parsed,
            label="seconds argument",
            strictly_positive=strictly_positive,
        )
    except (json.JSONDecodeError, N2PhysicalCampaignError, ValueError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile", allow_abbrev=False)
    _add_original_inputs(compile_parser)
    compile_parser.add_argument(
        "--minimum-interval-seconds",
        type=lambda value: _seconds_argument(value, strictly_positive=True),
        required=True,
    )
    compile_parser.add_argument(
        "--planned-cooldown-seconds",
        type=lambda value: _seconds_argument(value, strictly_positive=False),
        required=True,
    )
    compile_parser.add_argument("--output-dir", type=Path, required=True)
    for command in ("validate", "describe"):
        subparser = commands.add_parser(command, allow_abbrev=False)
        subparser.add_argument("--bundle-dir", type=Path, required=True)
        _add_original_inputs(subparser)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "compile":
            manifest = publish_physical_bundle(
                args.source_manifest,
                args.panel_file,
                args.binding_review_artifact,
                args.output_dir,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
            )
            result = _description(manifest, mode="compiled-and-published")
        else:
            manifest = validate_physical_bundle(
                args.bundle_dir,
                args.source_manifest,
                args.panel_file,
                args.binding_review_artifact,
            )
            result = _description(
                manifest,
                mode="validated" if args.command == "validate" else "describe-only",
            )
    except (N2PhysicalCampaignError, CampaignContractError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
