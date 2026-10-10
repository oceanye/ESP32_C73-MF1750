#!/usr/bin/env python3
"""Materialize the reviewed N5 science plan for one physical panel.

This module is deliberately offline.  It reads the real compile profile,
source manifest, physical campaign anchor, RC2G firmware binary, detached
science-review evidence, authenticated review approval, and trusted reviewer
key.  It then rebuilds every N5 action, prior, session, and claim identity for
an explicit operator-selected process schedule.

No function in this module creates an authorization or claim, contacts a
device, controls power, or performs network I/O.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.extended_color import execution  # noqa: E402
from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    PhysicalCampaignRebindError,
    ProductionProfileError,
    canonical_json_bytes,
    compile_physical_campaign_rebind,
    read_local_regular_file,
    validate_campaign_contract,
    validate_physical_campaign_rebind,
)
from tools import mf1750_n5_measurement_campaign as source_compiler  # noqa: E402


SCHEMA_VERSION = 1
PLAN_KIND = "mf1750-n5-production-physical-plan"
PLAN_HASH_SCOPE = (
    "entire N5 production physical plan excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
SCIENCE_REVIEW_KIND = "mf1750-n5-static-science-review-approval"
SCIENCE_REVIEW_ALGORITHM = "HMAC-SHA256"
SCIENCE_REVIEW_SIGNATURE_SCOPE = (
    "entire static science review approval excluding authentication.signature; "
    "canonical JSON"
)
PROCESS_SCHEDULE_KIND = "mf1750-n5-operator-process-schedule"
PROCESS_SCHEDULE_CLASSIFICATION = (
    "operator_selected_supervised_process_schedule_not_supplier_rating"
)
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_REVIEW_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_REVIEW_KEY_BYTES = 64 * 1024
PLAN_ID_PREFIX = "n5-production-physical-"

_NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_APPROVAL_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "decision",
        "reviewer_id",
        "reviewed_at",
        "science_review_evidence_file_sha256",
        "compile_profile_canonical_sha256",
        "compile_profile_file_sha256",
        "source_manifest_canonical_sha256",
        "source_manifest_file_sha256",
        "physical_anchor_campaign_canonical_sha256",
        "physical_anchor_campaign_file_sha256",
        "panel",
        "firmware",
        "firmware_binary_sha256",
        "operator_process_schedule",
        "authentication",
    }
)
_AUTHENTICATION_FIELDS = frozenset(
    {"algorithm", "key_id", "signature_scope", "signature"}
)


class N5PhysicalCampaignError(ValueError):
    """An N5 physical materialization input or replay failed closed."""


@dataclass(frozen=True)
class N5PhysicalCampaignInputs:
    compile_profile: Mapping[str, Any]
    compile_profile_bytes: bytes
    source_manifest: Mapping[str, Any]
    source_manifest_bytes: bytes
    physical_anchor: Mapping[str, Any]
    physical_anchor_bytes: bytes
    firmware_binary: bytes
    science_review_evidence: bytes
    science_review_approval: Mapping[str, Any]
    science_review_approval_bytes: bytes
    reviewer_key: bytes


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N5PhysicalCampaignError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _require_hash(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise N5PhysicalCampaignError(f"{label} must be lowercase SHA-256")
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise N5PhysicalCampaignError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N5PhysicalCampaignError(
            f"{label} must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N5PhysicalCampaignError(f"{label} must include a UTC offset")
    return parsed


def _seconds(
    value: Any, *, label: str, strictly_positive: bool
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N5PhysicalCampaignError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise N5PhysicalCampaignError(f"{label} must be finite and nonnegative")
    if strictly_positive and normalized <= 0:
        raise N5PhysicalCampaignError(f"{label} must be positive")
    return normalized


def operator_process_schedule(
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    """Return the explicit non-supplier N5 experimental process schedule."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PROCESS_SCHEDULE_KIND,
        "classification": PROCESS_SCHEDULE_CLASSIFICATION,
        "not_a_supplier_rating": True,
        "minimum_interval_seconds": _seconds(
            minimum_interval_seconds,
            label="minimum_interval_seconds",
            strictly_positive=True,
        ),
        "planned_cooldown_seconds": _seconds(
            planned_cooldown_seconds,
            label="planned_cooldown_seconds",
            strictly_positive=False,
        ),
    }


def _decode_canonical_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N5PhysicalCampaignError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N5PhysicalCampaignError(
                    f"{label} contains unsupported constant {token}"
                )
            ),
        )
    except N5PhysicalCampaignError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N5PhysicalCampaignError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N5PhysicalCampaignError(f"{label} must contain a JSON object")
    try:
        canonical = canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N5PhysicalCampaignError(f"{label} is not canonical JSON: {error}") from error
    if payload != canonical:
        raise N5PhysicalCampaignError(f"{label} must be stored as exact canonical JSON")
    return value


def _read_bytes(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    try:
        artifact = read_local_regular_file(
            path, label=label, maximum_bytes=maximum_bytes
        )
    except ProductionProfileError as error:
        raise N5PhysicalCampaignError(str(error)) from error
    return artifact.payload


def _read_json(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    payload = _read_bytes(path, label=label, maximum_bytes=MAX_JSON_BYTES)
    return _decode_canonical_json(payload, label=label), payload


def _approval_unsigned_bytes(approval: Mapping[str, Any]) -> bytes:
    unsigned = _snapshot(approval)
    authentication = unsigned.get("authentication")
    if not isinstance(authentication, dict):
        raise N5PhysicalCampaignError("science review authentication is missing")
    authentication.pop("signature", None)
    return canonical_json_bytes(unsigned)


def _approval_payload(
    *,
    reviewer_id: str,
    reviewed_at: str,
    science_review_evidence: bytes,
    compile_profile: Mapping[str, Any],
    compile_profile_bytes: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_bytes: bytes,
    physical_anchor: Mapping[str, Any],
    physical_anchor_bytes: bytes,
    firmware_binary: bytes,
    schedule: Mapping[str, Any],
    reviewer_key: bytes,
) -> dict[str, Any]:
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise N5PhysicalCampaignError("reviewer_id must be non-empty")
    _timestamp(reviewed_at, label="reviewed_at")
    if not science_review_evidence:
        raise N5PhysicalCampaignError("actual science review evidence bytes are required")
    if not reviewer_key:
        raise N5PhysicalCampaignError("trusted reviewer key bytes are required")
    key_id = _sha256(reviewer_key)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": SCIENCE_REVIEW_KIND,
        "decision": "approved",
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
        "science_review_evidence_file_sha256": _sha256(
            science_review_evidence
        ),
        "compile_profile_canonical_sha256": compile_profile["integrity"][
            "canonical_sha256"
        ],
        "compile_profile_file_sha256": _sha256(compile_profile_bytes),
        "source_manifest_canonical_sha256": source_manifest["integrity"][
            "canonical_sha256"
        ],
        "source_manifest_file_sha256": _sha256(source_manifest_bytes),
        "physical_anchor_campaign_canonical_sha256": physical_anchor[
            "integrity"
        ]["canonical_sha256"],
        "physical_anchor_campaign_file_sha256": _sha256(
            physical_anchor_bytes
        ),
        "panel": _snapshot(physical_anchor["panel"]),
        "firmware": _snapshot(physical_anchor["firmware"]),
        "firmware_binary_sha256": _sha256(firmware_binary),
        "operator_process_schedule": _snapshot(schedule),
        "authentication": {
            "algorithm": SCIENCE_REVIEW_ALGORITHM,
            "key_id": key_id,
            "signature_scope": SCIENCE_REVIEW_SIGNATURE_SCOPE,
        },
    }
    signature = hmac.new(
        reviewer_key, canonical_json_bytes(unsigned), hashlib.sha256
    ).hexdigest()
    return {
        **unsigned,
        "authentication": {
            **unsigned["authentication"],
            "signature": signature,
        },
    }


def create_static_science_review_approval(
    *,
    reviewer_id: str,
    reviewed_at: str,
    science_review_evidence: bytes,
    compile_profile: Mapping[str, Any],
    compile_profile_bytes: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_bytes: bytes,
    physical_anchor: Mapping[str, Any],
    physical_anchor_bytes: bytes,
    firmware_binary: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    reviewer_key: bytes,
) -> dict[str, Any]:
    """Create a detached canonical HMAC approval for actual input bytes."""

    source_compiler.validate_compile_profile(compile_profile)
    source_compiler.validate_compiled_manifest(source_manifest)
    validate_campaign_contract(physical_anchor)
    schedule = operator_process_schedule(
        minimum_interval_seconds, planned_cooldown_seconds
    )
    _validate_source_inputs(
        compile_profile=compile_profile,
        compile_profile_bytes=compile_profile_bytes,
        source_manifest=source_manifest,
        source_manifest_bytes=source_manifest_bytes,
        physical_anchor=physical_anchor,
        physical_anchor_bytes=physical_anchor_bytes,
        firmware_binary=firmware_binary,
    )
    return _approval_payload(
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        science_review_evidence=science_review_evidence,
        compile_profile=compile_profile,
        compile_profile_bytes=compile_profile_bytes,
        source_manifest=source_manifest,
        source_manifest_bytes=source_manifest_bytes,
        physical_anchor=physical_anchor,
        physical_anchor_bytes=physical_anchor_bytes,
        firmware_binary=firmware_binary,
        schedule=schedule,
        reviewer_key=reviewer_key,
    )


def _validate_source_inputs(
    *,
    compile_profile: Mapping[str, Any],
    compile_profile_bytes: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_bytes: bytes,
    physical_anchor: Mapping[str, Any],
    physical_anchor_bytes: bytes,
    firmware_binary: bytes,
) -> None:
    try:
        profile = source_compiler.validate_compile_profile(compile_profile)
        source = source_compiler.validate_compiled_manifest(source_manifest)
        anchor = validate_campaign_contract(physical_anchor)
    except (source_compiler.N5CampaignError, CampaignContractError) as error:
        raise N5PhysicalCampaignError(f"N5 physical source input is invalid: {error}") from error
    if compile_profile_bytes != canonical_json_bytes(profile):
        raise N5PhysicalCampaignError("compile profile actual bytes are not canonical/exact")
    if source_manifest_bytes != canonical_json_bytes(source):
        raise N5PhysicalCampaignError("source manifest actual bytes are not canonical/exact")
    if physical_anchor_bytes != canonical_json_bytes(anchor):
        raise N5PhysicalCampaignError("physical anchor actual bytes are not canonical/exact")
    expected_source = source_compiler.compile_manifest_from_profile(profile)
    if source != expected_source or source_manifest_bytes != canonical_json_bytes(
        expected_source
    ):
        raise N5PhysicalCampaignError(
            "source manifest is not the exact deterministic projection of the compile profile"
        )
    if source["shared_p0"]["panel"] != anchor["panel"]:
        raise N5PhysicalCampaignError(
            "compile profile/source panel is not the exact physical anchor panel"
        )
    if source["shared_p0"]["firmware"] != anchor["firmware"]:
        raise N5PhysicalCampaignError(
            "compile profile/source firmware descriptor differs from the physical anchor"
        )
    if not isinstance(firmware_binary, bytes) or not firmware_binary:
        raise N5PhysicalCampaignError("actual RC2G firmware bytes are required")
    expected_firmware_sha = anchor["firmware"]["binary_sha256"]
    if _sha256(firmware_binary) != expected_firmware_sha:
        raise N5PhysicalCampaignError(
            "actual RC2G firmware bytes do not match the physical anchor"
        )
    if len(source["shared_p0"]["actions"]) != 73 or len(
        source["shared_p0"]["sessions"]
    ) != 26:
        raise N5PhysicalCampaignError("physical N5 source must contain 73 actions/26 sessions")


def validate_static_science_review_approval(
    approval: Mapping[str, Any],
    *,
    approval_bytes: bytes,
    science_review_evidence: bytes,
    compile_profile: Mapping[str, Any],
    compile_profile_bytes: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_bytes: bytes,
    physical_anchor: Mapping[str, Any],
    physical_anchor_bytes: bytes,
    firmware_binary: bytes,
    schedule: Mapping[str, Any],
    reviewer_key: bytes,
) -> Mapping[str, Any]:
    """Authenticate the detached review and every physical compiler input."""

    if not isinstance(approval, Mapping) or set(approval) != _APPROVAL_FIELDS:
        raise N5PhysicalCampaignError("static science review approval fields changed")
    if approval_bytes != canonical_json_bytes(approval):
        raise N5PhysicalCampaignError(
            "static science review approval actual bytes are not canonical/exact"
        )
    authentication = approval.get("authentication")
    if not isinstance(authentication, Mapping) or set(authentication) != _AUTHENTICATION_FIELDS:
        raise N5PhysicalCampaignError("static science review authentication fields changed")
    if (
        approval["schema_version"] != SCHEMA_VERSION
        or approval["kind"] != SCIENCE_REVIEW_KIND
        or approval["decision"] != "approved"
        or authentication["algorithm"] != SCIENCE_REVIEW_ALGORITHM
        or authentication["signature_scope"] != SCIENCE_REVIEW_SIGNATURE_SCOPE
    ):
        raise N5PhysicalCampaignError("static science review approval identity changed")
    if not isinstance(approval["reviewer_id"], str) or not approval["reviewer_id"].strip():
        raise N5PhysicalCampaignError("static science reviewer_id is invalid")
    _timestamp(approval["reviewed_at"], label="science review reviewed_at")
    if not reviewer_key:
        raise N5PhysicalCampaignError("trusted reviewer key bytes are required")
    for field in (
        "science_review_evidence_file_sha256",
        "compile_profile_canonical_sha256",
        "compile_profile_file_sha256",
        "source_manifest_canonical_sha256",
        "source_manifest_file_sha256",
        "physical_anchor_campaign_canonical_sha256",
        "physical_anchor_campaign_file_sha256",
        "firmware_binary_sha256",
    ):
        _require_hash(approval[field], label=f"science review {field}")
    _require_hash(authentication["key_id"], label="science review key_id")
    _require_hash(authentication["signature"], label="science review signature")
    expected_key_id = _sha256(reviewer_key)
    if not hmac.compare_digest(str(authentication["key_id"]), expected_key_id):
        raise N5PhysicalCampaignError(
            "science review is not authenticated by the trusted reviewer key"
        )
    expected_signature = hmac.new(
        reviewer_key, _approval_unsigned_bytes(approval), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(
        str(authentication["signature"]), expected_signature
    ):
        raise N5PhysicalCampaignError("static science review HMAC is invalid")
    expected = _approval_payload(
        reviewer_id=str(approval["reviewer_id"]),
        reviewed_at=str(approval["reviewed_at"]),
        science_review_evidence=science_review_evidence,
        compile_profile=compile_profile,
        compile_profile_bytes=compile_profile_bytes,
        source_manifest=source_manifest,
        source_manifest_bytes=source_manifest_bytes,
        physical_anchor=physical_anchor,
        physical_anchor_bytes=physical_anchor_bytes,
        firmware_binary=firmware_binary,
        schedule=schedule,
        reviewer_key=reviewer_key,
    )
    if approval != expected:
        raise N5PhysicalCampaignError(
            "static science review does not bind the exact physical compiler inputs"
        )
    return approval


def _rebind_tree(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        transformed = {
            key: _rebind_tree(item, replacements)
            for key, item in value.items()
            if key != "integrity"
        }
        integrity = value.get("integrity")
        if integrity is not None:
            if not isinstance(integrity, Mapping) or set(integrity) != {
                "canonical_sha256",
                "canonical_sha256_scope",
            }:
                raise N5PhysicalCampaignError(
                    "embedded integrity record cannot be safely rebound"
                )
            transformed["integrity"] = {
                "canonical_sha256": _sha256(transformed),
                "canonical_sha256_scope": integrity["canonical_sha256_scope"],
            }
        return transformed
    if isinstance(value, list):
        return [_rebind_tree(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def _runtime_manifest(
    source_manifest: Mapping[str, Any],
    physical_rebind: Mapping[str, Any],
) -> dict[str, Any]:
    physical_campaign = physical_rebind["physical_campaign"]
    replacements: dict[str, str] = {}
    for item in physical_rebind["action_identity_map"]:
        replacements[item["source_action_identity_sha256"]] = item[
            "physical_action_identity_sha256"
        ]
        replacements[item["source_claim_filename"]] = item[
            "physical_claim_filename"
        ]
    unsigned = {
        key: _rebind_tree(value, replacements)
        for key, value in source_manifest.items()
        if key not in {"integrity", "shared_p0", "campaign_id"}
    }
    unsigned["campaign_id"] = physical_campaign["campaign_id"]
    unsigned["shared_p0"] = _snapshot(physical_campaign)
    readiness = unsigned.get("readiness")
    if isinstance(readiness, dict) and isinstance(readiness.get("blockers"), list):
        readiness["blockers"] = [
            (
                "reviewed_limit_authority_profile_missing"
                if blocker == "reviewed_supplier_limit_profile_missing"
                else blocker
            )
            for blocker in readiness["blockers"]
        ]
    # Recreate the original top-level order so non-canonical pretty printers do
    # not obscure review, then seal over the complete object.
    runtime_unsigned = {
        key: (
            unsigned["campaign_id"]
            if key == "campaign_id"
            else unsigned["shared_p0"]
            if key == "shared_p0"
            else unsigned[key]
        )
        for key in source_manifest
        if key != "integrity"
    }
    return {
        **runtime_unsigned,
        "integrity": {
            "canonical_sha256": _sha256(runtime_unsigned),
            "canonical_sha256_scope": source_manifest["integrity"][
                "canonical_sha256_scope"
            ],
        },
    }


def _binding_review_bytes(
    science_review_evidence: bytes, science_review_approval_bytes: bytes
) -> bytes:
    return canonical_json_bytes(
        {
            "science_review_evidence_file_sha256": _sha256(
                science_review_evidence
            ),
            "science_review_approval_file_sha256": _sha256(
                science_review_approval_bytes
            ),
        }
    )


def _compile_unvalidated(
    inputs: N5PhysicalCampaignInputs,
    *,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    if not isinstance(namespace, str) or _NAMESPACE_RE.fullmatch(namespace) is None:
        raise N5PhysicalCampaignError(
            "namespace must be a 1..32 character stable token"
        )
    schedule = operator_process_schedule(
        minimum_interval_seconds, planned_cooldown_seconds
    )
    _validate_source_inputs(
        compile_profile=inputs.compile_profile,
        compile_profile_bytes=inputs.compile_profile_bytes,
        source_manifest=inputs.source_manifest,
        source_manifest_bytes=inputs.source_manifest_bytes,
        physical_anchor=inputs.physical_anchor,
        physical_anchor_bytes=inputs.physical_anchor_bytes,
        firmware_binary=inputs.firmware_binary,
    )
    validate_static_science_review_approval(
        inputs.science_review_approval,
        approval_bytes=inputs.science_review_approval_bytes,
        science_review_evidence=inputs.science_review_evidence,
        compile_profile=inputs.compile_profile,
        compile_profile_bytes=inputs.compile_profile_bytes,
        source_manifest=inputs.source_manifest,
        source_manifest_bytes=inputs.source_manifest_bytes,
        physical_anchor=inputs.physical_anchor,
        physical_anchor_bytes=inputs.physical_anchor_bytes,
        firmware_binary=inputs.firmware_binary,
        schedule=schedule,
        reviewer_key=inputs.reviewer_key,
    )
    binding_bytes = _binding_review_bytes(
        inputs.science_review_evidence,
        inputs.science_review_approval_bytes,
    )
    try:
        rebound = compile_physical_campaign_rebind(
            inputs.source_manifest["shared_p0"],
            inputs.physical_anchor,
            namespace=f"n5-{namespace}",
            binding_review_bytes=binding_bytes,
            minimum_interval_seconds=schedule["minimum_interval_seconds"],
            planned_cooldown_seconds=schedule["planned_cooldown_seconds"],
        )
    except PhysicalCampaignRebindError as error:
        raise N5PhysicalCampaignError(f"N5 physical identity rebuild failed: {error}") from error
    runtime_manifest = _runtime_manifest(inputs.source_manifest, rebound)
    try:
        contract = execution.compile_execution_contract(runtime_manifest)
        execution.validate_execution_contract(contract)
    except execution.N5ExecutionError as error:
        raise N5PhysicalCampaignError(
            f"rebuilt N5 execution contract is invalid: {error}"
        ) from error
    class_counts = {
        plan_class: sum(
            action["plan_class"] == plan_class for action in contract["actions"]
        )
        for plan_class in ("descriptive", "formal_palette", "formal_transition")
    }
    slot_counts = {
        plan_class: sum(
            len(action["measurement_slots"])
            for action in contract["actions"]
            if action["plan_class"] == plan_class
        )
        for plan_class in ("descriptive", "formal_palette", "formal_transition")
    }
    if (
        len(contract["actions"]) != 73
        or len(contract["sessions"]) != 26
        or class_counts
        != {"descriptive": 22, "formal_palette": 9, "formal_transition": 42}
        or slot_counts
        != {"descriptive": 0, "formal_palette": 36, "formal_transition": 720}
    ):
        raise N5PhysicalCampaignError("rebuilt N5 contract count changed")
    plan_id_seed = {
        "namespace": namespace,
        "physical_rebind_canonical_sha256": rebound["integrity"][
            "canonical_sha256"
        ],
        "science_review_approval_file_sha256": _sha256(
            inputs.science_review_approval_bytes
        ),
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "plan_id": PLAN_ID_PREFIX + _sha256(plan_id_seed),
        "namespace": namespace,
        "source": {
            "compile_profile_canonical_sha256": inputs.compile_profile[
                "integrity"
            ]["canonical_sha256"],
            "compile_profile_file_sha256": _sha256(
                inputs.compile_profile_bytes
            ),
            "source_manifest_canonical_sha256": inputs.source_manifest[
                "integrity"
            ]["canonical_sha256"],
            "source_manifest_file_sha256": _sha256(inputs.source_manifest_bytes),
            "physical_anchor_campaign_canonical_sha256": inputs.physical_anchor[
                "integrity"
            ]["canonical_sha256"],
            "physical_anchor_campaign_file_sha256": _sha256(
                inputs.physical_anchor_bytes
            ),
            "firmware_binary_sha256": _sha256(inputs.firmware_binary),
        },
        "static_science_review": {
            "reviewer_id": inputs.science_review_approval["reviewer_id"],
            "reviewed_at": inputs.science_review_approval["reviewed_at"],
            "science_review_evidence_file_sha256": _sha256(
                inputs.science_review_evidence
            ),
            "science_review_approval_file_sha256": _sha256(
                inputs.science_review_approval_bytes
            ),
            "trusted_reviewer_key_id": _sha256(inputs.reviewer_key),
            "canonical_hmac_authenticated": True,
        },
        "operator_process_schedule": schedule,
        "physical_rebind": rebound,
        "runtime_manifest": runtime_manifest,
        "execution_contract": contract,
        "counts": {
            "actions": 73,
            "sessions": 26,
            "descriptive_actions": 22,
            "formal_palette_actions": 9,
            "formal_transition_actions": 42,
        },
        "classification": {
            "offline_materialized": True,
            "physical_panel_instance_bound": True,
            "actual_firmware_bytes_bound": True,
            "authenticated_static_science_review": True,
            "operator_schedule_not_supplier_rating": True,
            "all_action_prior_session_claim_identities_rebuilt": True,
            "reviewed_production_limit_profile_present": False,
            "hardware_execution_authorized": False,
            "authorization_created": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": PLAN_HASH_SCOPE,
        },
    }


def validate_n5_physical_plan(
    plan: Mapping[str, Any],
    inputs: N5PhysicalCampaignInputs,
    *,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    """Full replay: the supplied plan must equal a fresh reconstruction."""

    if not isinstance(plan, Mapping):
        raise N5PhysicalCampaignError("N5 physical plan must be an object")
    expected = _compile_unvalidated(
        inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    if plan != expected or canonical_json_bytes(plan) != canonical_json_bytes(expected):
        raise N5PhysicalCampaignError(
            "N5 physical plan differs from full trusted-input replay"
        )
    try:
        validate_physical_campaign_rebind(
            plan["physical_rebind"],
            source_campaign=inputs.source_manifest["shared_p0"],
            physical_anchor_campaign=inputs.physical_anchor,
            binding_review_bytes=_binding_review_bytes(
                inputs.science_review_evidence,
                inputs.science_review_approval_bytes,
            ),
            minimum_interval_seconds=float(minimum_interval_seconds),
            planned_cooldown_seconds=float(planned_cooldown_seconds),
        )
        contract = execution.validate_execution_contract(plan["execution_contract"])
    except (PhysicalCampaignRebindError, execution.N5ExecutionError) as error:
        raise N5PhysicalCampaignError(f"N5 physical plan replay failed: {error}") from error
    physical = plan["physical_rebind"]["physical_campaign"]
    old_actions = {
        action["action_identity_sha256"]
        for action in inputs.source_manifest["shared_p0"]["actions"]
    }
    new_actions = {
        action["action_identity_sha256"] for action in physical["actions"]
    }
    old_claims = {
        action["claim"]["filename"]
        for action in inputs.source_manifest["shared_p0"]["actions"]
    }
    new_claims = {
        action["claim"]["filename"] for action in physical["actions"]
    }
    if (
        len(new_actions) != 73
        or len(physical["sessions"]) != 26
        or old_actions & new_actions
        or old_claims & new_claims
        or contract["p0_campaign"] != physical
    ):
        raise N5PhysicalCampaignError(
            "N5 physical action/session/claim identity closure is invalid"
        )
    return plan


def compile_n5_physical_plan(
    inputs: N5PhysicalCampaignInputs,
    *,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    plan = _compile_unvalidated(
        inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    validate_n5_physical_plan(
        plan,
        inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    return plan


def load_n5_physical_inputs(
    *,
    compile_profile_file: Path,
    source_manifest_file: Path,
    physical_anchor_campaign_file: Path,
    firmware_binary_file: Path,
    science_review_evidence_file: Path,
    science_review_approval_file: Path,
    reviewer_key_file: Path,
) -> N5PhysicalCampaignInputs:
    profile, profile_bytes = _read_json(
        compile_profile_file, label="N5 compile profile"
    )
    source, source_bytes = _read_json(
        source_manifest_file, label="N5 source manifest"
    )
    anchor, anchor_bytes = _read_json(
        physical_anchor_campaign_file, label="N5 physical anchor campaign"
    )
    approval, approval_bytes = _read_json(
        science_review_approval_file,
        label="N5 static science review approval",
    )
    firmware = _read_bytes(
        firmware_binary_file,
        label="actual RC2G firmware binary",
        maximum_bytes=MAX_JSON_BYTES,
    )
    evidence = _read_bytes(
        science_review_evidence_file,
        label="actual N5 science review evidence",
        maximum_bytes=MAX_REVIEW_EVIDENCE_BYTES,
    )
    key = _read_bytes(
        reviewer_key_file,
        label="trusted N5 science reviewer key",
        maximum_bytes=MAX_REVIEW_KEY_BYTES,
    )
    return N5PhysicalCampaignInputs(
        compile_profile=profile,
        compile_profile_bytes=profile_bytes,
        source_manifest=source,
        source_manifest_bytes=source_bytes,
        physical_anchor=anchor,
        physical_anchor_bytes=anchor_bytes,
        firmware_binary=firmware,
        science_review_evidence=evidence,
        science_review_approval=approval,
        science_review_approval_bytes=approval_bytes,
        reviewer_key=key,
    )


def compile_n5_physical_plan_from_files(
    *,
    compile_profile_file: Path,
    source_manifest_file: Path,
    physical_anchor_campaign_file: Path,
    firmware_binary_file: Path,
    science_review_evidence_file: Path,
    science_review_approval_file: Path,
    reviewer_key_file: Path,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> dict[str, Any]:
    inputs = load_n5_physical_inputs(
        compile_profile_file=compile_profile_file,
        source_manifest_file=source_manifest_file,
        physical_anchor_campaign_file=physical_anchor_campaign_file,
        firmware_binary_file=firmware_binary_file,
        science_review_evidence_file=science_review_evidence_file,
        science_review_approval_file=science_review_approval_file,
        reviewer_key_file=reviewer_key_file,
    )
    return compile_n5_physical_plan(
        inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


def load_validated_n5_physical_plan(
    plan_file: Path,
    *,
    inputs: N5PhysicalCampaignInputs,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> Mapping[str, Any]:
    plan, payload = _read_json(plan_file, label="N5 production physical plan")
    if payload != canonical_json_bytes(plan):  # pragma: no cover - _read_json guards
        raise N5PhysicalCampaignError("N5 physical plan bytes changed")
    return validate_n5_physical_plan(
        plan,
        inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    try:
        source_compiler._publish_new_bytes(path, payload)
    except source_compiler.N5CampaignError as error:
        raise N5PhysicalCampaignError(str(error)) from error


def _add_common_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--compile-profile", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--physical-anchor", type=Path, required=True)
    parser.add_argument("--firmware-binary", type=Path, required=True)
    parser.add_argument("--science-review-evidence", type=Path, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    approve = subparsers.add_parser(
        "approve-science-review", help="create one detached canonical HMAC approval"
    )
    _add_common_inputs(approve)
    approve.add_argument("--reviewer-id", required=True)
    approve.add_argument("--reviewed-at", required=True)
    approve.add_argument("--output", type=Path, required=True)
    compile_parser = subparsers.add_parser(
        "compile", help="materialize one authenticated physical N5 plan"
    )
    _add_common_inputs(compile_parser)
    compile_parser.add_argument("--science-review-approval", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        if args.command == "approve-science-review":
            profile, profile_bytes = _read_json(
                args.compile_profile, label="N5 compile profile"
            )
            source, source_bytes = _read_json(
                args.source_manifest, label="N5 source manifest"
            )
            anchor, anchor_bytes = _read_json(
                args.physical_anchor, label="N5 physical anchor campaign"
            )
            firmware = _read_bytes(
                args.firmware_binary,
                label="actual RC2G firmware binary",
                maximum_bytes=MAX_JSON_BYTES,
            )
            evidence = _read_bytes(
                args.science_review_evidence,
                label="actual N5 science review evidence",
                maximum_bytes=MAX_REVIEW_EVIDENCE_BYTES,
            )
            key = _read_bytes(
                args.reviewer_key,
                label="trusted N5 science reviewer key",
                maximum_bytes=MAX_REVIEW_KEY_BYTES,
            )
            output = create_static_science_review_approval(
                reviewer_id=args.reviewer_id,
                reviewed_at=args.reviewed_at,
                science_review_evidence=evidence,
                compile_profile=profile,
                compile_profile_bytes=profile_bytes,
                source_manifest=source,
                source_manifest_bytes=source_bytes,
                physical_anchor=anchor,
                physical_anchor_bytes=anchor_bytes,
                firmware_binary=firmware,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
                reviewer_key=key,
            )
        else:
            output = compile_n5_physical_plan_from_files(
                compile_profile_file=args.compile_profile,
                source_manifest_file=args.source_manifest,
                physical_anchor_campaign_file=args.physical_anchor,
                firmware_binary_file=args.firmware_binary,
                science_review_evidence_file=args.science_review_evidence,
                science_review_approval_file=args.science_review_approval,
                reviewer_key_file=args.reviewer_key,
                namespace=args.namespace,
                minimum_interval_seconds=args.minimum_interval_seconds,
                planned_cooldown_seconds=args.planned_cooldown_seconds,
            )
        _write_new_json(args.output, output)
    except (
        N5PhysicalCampaignError,
        source_compiler.N5CampaignError,
        CampaignContractError,
        PhysicalCampaignRebindError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "file_sha256": _sha256(canonical_json_bytes(output)),
                "kind": output["kind"],
                "network_io_performed": False,
                "device_io_performed": False,
                "claim_created": False,
                "authorization_created": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MAX_JSON_BYTES",
    "N5PhysicalCampaignError",
    "N5PhysicalCampaignInputs",
    "PLAN_KIND",
    "PROCESS_SCHEDULE_CLASSIFICATION",
    "PROCESS_SCHEDULE_KIND",
    "SCIENCE_REVIEW_KIND",
    "compile_n5_physical_plan",
    "compile_n5_physical_plan_from_files",
    "create_static_science_review_approval",
    "load_n5_physical_inputs",
    "load_validated_n5_physical_plan",
    "operator_process_schedule",
    "validate_n5_physical_plan",
    "validate_static_science_review_approval",
]
