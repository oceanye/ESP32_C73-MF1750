"""Fail-closed execution evidence for the three N5 plan classes.

The compiler and validators in this module are pure.  The only mutating API is
``execute_fixed_action_once`` and it requires an explicit atomic claim store,
an external authorization record, and an injected protocol driver.  It runs
one selected action only; it never advances, retries, recovers, controls J2,
or creates an authorization.

The finalized bundle is deliberately verbose.  Aggregation accepts a hardware
observation only after this module has rebound the source P0 action, external
authorization, atomically consumed claim, audited protocol, manual measurement
observation, action finalization, and immutable P0 result by whole-record
SHA-256.  A standalone ``PASS`` flag is therefore insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Optional, Sequence

from host.visible_refresh_campaign import (
    CLAIM_REGISTRY_ID,
    CLAIM_REGISTRY_RELATIVE_PATH,
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    describe_action_offline,
    result_file_sha256,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
    workspace_global_claim_declaration,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-n5-optical-atlas-campaign-manifest"
CONTRACT_KIND = "mf1750-n5-fixed-execution-contract"
CONTRACT_ID = "mf1750-n5-three-plan-fixed-execution-v1"
DESCRIPTION_KIND = "mf1750-n5-fixed-execution-description"
AUTHORIZATION_KIND = "mf1750-n5-external-one-action-authorization"
SESSION_START_KIND = "mf1750-n5-manual-session-start-observation"
CLAIM_KIND = "mf1750-n5-workspace-global-consumed-claim"
PROTOCOL_KIND = "mf1750-n5-fixed-action-protocol-evidence"
PROTOCOL_RECEIPT_KIND = "mf1750-n5-fixed-action-protocol-receipt"
MANUAL_OBSERVATION_KIND = "mf1750-n5-manual-action-measurement-observation"
ACTION_FINALIZATION_KIND = "mf1750-n5-action-finalization"
SESSION_FINALIZATION_KIND = "mf1750-n5-session-finalization"
BUNDLE_KIND = "mf1750-n5-finalized-execution-bundle"

CONTRACT_HASH_SCOPE = (
    "entire N5 fixed execution contract excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
RECORD_HASH_SCOPE = (
    "entire N5 execution record excluding integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
BUNDLE_HASH_SCOPE = RECORD_HASH_SCOPE.replace("execution record", "execution bundle")

PLAN_CLASSES = ("descriptive", "formal_palette", "formal_transition")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_ALLOWED_GET_ENDPOINTS = {
    "/api/version",
    "/api/job",
    "/api/diagnostic/report",
    "/api/diagnostic/status",
}


class N5ExecutionError(ValueError):
    """An N5 execution contract or evidence chain is invalid."""


class N5ClaimConsumedError(N5ExecutionError):
    """The workspace-global action claim already exists and is permanent."""


class N5PostClaimUnknown(N5ExecutionError):
    """Execution failed after claim consumption; retry/recovery are forbidden."""

    def __init__(self, message: str, *, receipt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.receipt = receipt


@dataclass(frozen=True)
class ActionSnapshot:
    key: str
    plan_class: str
    order: int
    action: Mapping[str, Any]
    session: Mapping[str, Any]
    measurement_slots: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class AtomicWorkspaceClaimStore:
    """Exclusive-create claim writer rooted at an explicit workspace path."""

    workspace_root: Path

    def commit(self, action: Mapping[str, Any], record: Mapping[str, Any]) -> str:
        declaration = action["claim"]
        expected = workspace_global_claim_declaration(
            str(action["action_identity_sha256"])
        )
        if declaration != expected:
            raise N5ExecutionError("action workspace-global claim declaration changed")
        root = self.workspace_root.resolve()
        registry = (root / CLAIM_REGISTRY_RELATIVE_PATH).resolve()
        try:
            registry.relative_to(root)
        except ValueError as error:
            raise N5ExecutionError("workspace-global claim registry escapes workspace") from error
        registry.mkdir(parents=True, exist_ok=True)
        destination = registry / declaration["filename"]
        payload = canonical_json_bytes(record)
        try:
            with destination.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise N5ClaimConsumedError(
                "this exact N5 action claim is permanently consumed; do not retry"
            ) from error
        except OSError as error:
            if destination.exists():
                raise N5PostClaimUnknown(
                    "claim state is unknown after exclusive-create failure; do not retry",
                    receipt={"claim_path": str(destination)},
                ) from error
            raise N5ExecutionError(f"could not atomically create N5 claim: {error}") from error
        return _sha256(record)


class AuditedTransport:
    """Route guard enforcing at most one exact visible POST for one action."""

    def __init__(
        self,
        transport: Callable[[str, str, Optional[bytes]], Any],
        *,
        endpoint: str,
        frame_sha256: str,
    ) -> None:
        self._transport = transport
        self._endpoint = endpoint
        self._frame_sha256 = frame_sha256
        self.calls: list[dict[str, Any]] = []
        self.post_attempt_count = 0
        self.post_issued_count = 0

    def request(
        self, method: str, endpoint: str, data: Optional[bytes] = None
    ) -> Any:
        normalized = method.upper()
        if normalized == "POST":
            if (
                self.post_attempt_count >= 1
                or endpoint != self._endpoint
                or data is None
                or hashlib.sha256(data).hexdigest() != self._frame_sha256
            ):
                raise N5ExecutionError("audited transport blocked a non-exact or second POST")
            self.post_attempt_count += 1
        elif normalized != "GET" or endpoint not in _ALLOWED_GET_ENDPOINTS or data is not None:
            raise N5ExecutionError("audited transport blocked a route outside the fixed allowlist")
        call = {
            "sequence": len(self.calls) + 1,
            "method": normalized,
            "endpoint": endpoint,
            "request_body_sha256": (
                None if data is None else hashlib.sha256(data).hexdigest()
            ),
        }
        self.calls.append(call)
        if normalized == "POST":
            self.post_issued_count += 1
        return self._transport(normalized, endpoint, data)

    def snapshot(self) -> dict[str, Any]:
        return {
            "post_attempt_count": self.post_attempt_count,
            "post_issued_count": self.post_issued_count,
            "calls": _snapshot(self.calls),
        }


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N5ExecutionError(f"value is not canonical JSON data: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _hash(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise N5ExecutionError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise N5ExecutionError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N5ExecutionError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N5ExecutionError(f"{label} must include a UTC offset")
    return parsed


def _number(value: Any, *, label: str, minimum: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N5ExecutionError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise N5ExecutionError(f"{label} is outside the permitted range")
    return result


def _exact(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise N5ExecutionError(
            f"{label} keys changed; missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _integrity(unsigned: Mapping[str, Any], scope: str = RECORD_HASH_SCOPE) -> dict[str, str]:
    return {"canonical_sha256": _sha256(unsigned), "canonical_sha256_scope": scope}


def _seal(payload: Mapping[str, Any], *, scope: str = RECORD_HASH_SCOPE) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise N5ExecutionError("record payload must be an object without integrity")
    unsigned = _snapshot(payload)
    return {**unsigned, "integrity": _integrity(unsigned, scope)}


def _check_integrity(record: Mapping[str, Any], *, label: str, scope: str = RECORD_HASH_SCOPE) -> None:
    unsigned = dict(record)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned, scope):
        raise N5ExecutionError(f"{label} canonical integrity is invalid")


def _plan_class(action_id: str) -> str:
    if action_id.startswith("n5-palette-"):
        return "formal_palette"
    if action_id.startswith(("n5-transition-pilot-", "n5-transition-formal-")):
        return "formal_transition"
    return "descriptive"


def _measurement_slot_index(manifest: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    palette = manifest.get("formal_palette_plan")
    if isinstance(palette, Mapping):
        for slot in palette.get("expected_slots", []):
            target = str(slot["target_action_identity_sha256"])
            result.setdefault(target, []).append(
                {"slot_id": str(slot["slot_id"]), "measurement_phase": "palette"}
            )
    transition = manifest.get("formal_transition_plan")
    if isinstance(transition, Mapping):
        for slot in transition.get("expected_slots", []):
            initial = str(slot["primer_action_identity_sha256"])
            target = str(slot["target_action_identity_sha256"])
            result.setdefault(initial, []).append(
                {"slot_id": str(slot["slot_id"]), "measurement_phase": "transition_initial"}
            )
            result.setdefault(target, []).append(
                {"slot_id": str(slot["slot_id"]), "measurement_phase": "transition_final"}
            )
    for values in result.values():
        values.sort(key=lambda item: (item["measurement_phase"], item["slot_id"]))
    return result


def _derive_action_index(
    p0: Mapping[str, Any], measurement_slots: Mapping[str, Sequence[Mapping[str, str]]]
) -> list[dict[str, Any]]:
    session_by_id = {session["session_id"]: session for session in p0["sessions"]}
    result = []
    for order, action in enumerate(p0["actions"], start=1):
        identity = action["identity"]
        action_id = identity["action_id"]
        result.append(
            {
                "action_key": action_id,
                "action_identity_sha256": action["action_identity_sha256"],
                "order": order,
                "plan_class": _plan_class(action_id),
                "session_id": identity["session_id"],
                "cell_id": identity["cell_id"],
                "phase": identity["phase"],
                "frame_sha256": identity["frame"]["sha256"],
                "immediate_prior_action_identity_sha256": (
                    None
                    if identity["prior"] is None
                    else identity["prior"]["action_identity_sha256"]
                ),
                "measurement_slots": _snapshot(
                    measurement_slots.get(action["action_identity_sha256"], [])
                ),
                "session_power_mode": session_by_id[identity["session_id"]][
                    "power_mode"
                ],
            }
        )
    return result


def _derive_session_index(p0: Mapping[str, Any]) -> list[dict[str, Any]]:
    action_by_sha = {
        action["action_identity_sha256"]: action for action in p0["actions"]
    }
    result = []
    for order, session in enumerate(p0["sessions"], start=1):
        classes = {
            _plan_class(action_by_sha[sha]["identity"]["action_id"])
            for sha in session["action_identity_sha256s"]
        }
        if len(classes) != 1:
            raise N5ExecutionError("one N5 session crosses plan classes")
        result.append(
            {
                "session_id": session["session_id"],
                "order": order,
                "plan_class": next(iter(classes)),
                "power_mode": session["power_mode"],
                "minimum_panel_power_off_seconds": session[
                    "minimum_panel_power_off_seconds"
                ],
                "final_power_off_required": session["final_power_off_required"],
                "action_identity_sha256s": list(
                    session["action_identity_sha256s"]
                ),
                "automatic_advance": False,
            }
        )
    return result


def compile_execution_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze one already-compiled N5 manifest into a zero-I/O runner contract."""

    root = _snapshot(manifest)
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != MANIFEST_KIND:
        raise N5ExecutionError("source is not an N5 campaign manifest")
    if not isinstance(root.get("integrity"), Mapping):
        raise N5ExecutionError("N5 source manifest lacks integrity")
    unsigned_manifest = dict(root)
    source_integrity = unsigned_manifest.pop("integrity")
    if source_integrity.get("canonical_sha256") != _sha256(unsigned_manifest):
        raise N5ExecutionError("N5 source manifest canonical integrity is invalid")
    try:
        p0 = validate_campaign_contract(root["shared_p0"])
    except (KeyError, CampaignContractError) as error:
        raise N5ExecutionError(f"N5 source P0 is invalid: {error}") from error

    slots = _measurement_slot_index(root)
    actions = _derive_action_index(p0, slots)
    sessions = _derive_session_index(p0)
    materialized = {
        "descriptive": True,
        "formal_palette": isinstance(root.get("formal_palette_plan"), Mapping),
        "formal_transition": isinstance(root.get("formal_transition_plan"), Mapping),
    }
    plan_bindings = {
        "descriptive": {
            "materialized": True,
            "measurement_plan_canonical_sha256": root["descriptive_transition_plan"][
                "integrity"
            ]["canonical_sha256"],
            "measurement_eligible_for_formal_aggregation": False,
        },
        "formal_palette": {
            "materialized": materialized["formal_palette"],
            "measurement_plan_canonical_sha256": (
                None
                if not materialized["formal_palette"]
                else root["formal_palette_plan"]["integrity"]["canonical_sha256"]
            ),
            "cold_profile_review_artifact_sha256": (
                None
                if root.get("session_profiles", {}).get("formal_palette_cold") is None
                else root["session_profiles"]["formal_palette_cold"][
                    "review_artifact_sha256"
                ]
            ),
            "measurement_eligible_for_formal_aggregation": materialized[
                "formal_palette"
            ],
        },
        "formal_transition": {
            "materialized": materialized["formal_transition"],
            "measurement_plan_canonical_sha256": (
                None
                if not materialized["formal_transition"]
                else root["formal_transition_plan"]["integrity"]["canonical_sha256"]
            ),
            "recovery_profile_canonical_sha256": (
                None
                if root.get("formal_transition_recovery_profile") is None
                else root["formal_transition_recovery_profile"]["integrity"][
                    "canonical_sha256"
                ]
            ),
            "power_profile_review_artifact_sha256": (
                None
                if root.get("formal_transition_power_profile") is None
                else root["formal_transition_power_profile"][
                    "review_artifact_sha256"
                ]
            ),
            "measurement_eligible_for_formal_aggregation": materialized[
                "formal_transition"
            ],
        },
    }
    blockers = [
        "canonical_reviewed_limit_profile_not_supplied_at_compile_time",
        "runtime_measurements_and_exact_external_authorizations_not_supplied",
    ]
    if not materialized["formal_palette"]:
        blockers.append("formal_palette_reviewed_cold_profile_and_plan_missing")
    if not materialized["formal_transition"]:
        blockers.append("formal_transition_reviewed_recovery_power_profiles_and_plan_missing")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": CONTRACT_ID,
        "source_manifest": {
            "kind": root["kind"],
            "campaign_id": root["campaign_id"],
            "canonical_sha256": source_integrity["canonical_sha256"],
            "file_sha256": _sha256(root),
        },
        "p0_campaign": _snapshot(p0),
        "p0_campaign_canonical_sha256": p0["integrity"]["canonical_sha256"],
        "p0_campaign_file_sha256": _sha256(p0),
        "plan_bindings": plan_bindings,
        "actions": actions,
        "sessions": sessions,
        "safety": {
            "workspace_global_atomic_claim_before_any_transport": True,
            "maximum_post_requests_per_action": 1,
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "immediate_prior_pass_whole_file_result_required": True,
            "abnormal_termination_ineligibilizes_remaining_plan_actions": True,
            "runner_controls_j2_or_power": False,
            "formal_transition_one_cold_start_per_repeat": True,
            "formal_transition_j2_remains_on_across_six_actions": True,
            "formal_transition_manual_j2_cut_after_target": True,
        },
        "readiness": {"hardware_ready": False, "blockers": blockers},
        "classification": {
            "offline_compiled": True,
            "hardware_execution_authorized": False,
            "authorization_created": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    contract = {**payload, "integrity": _integrity(payload, CONTRACT_HASH_SCOPE)}
    validate_execution_contract(contract)
    return contract


def validate_execution_contract(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        contract,
        label="N5 execution contract",
        keys={
            "schema_version",
            "kind",
            "contract_id",
            "source_manifest",
            "p0_campaign",
            "p0_campaign_canonical_sha256",
            "p0_campaign_file_sha256",
            "plan_bindings",
            "actions",
            "sessions",
            "safety",
            "readiness",
            "classification",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != CONTRACT_KIND
        or root["contract_id"] != CONTRACT_ID
    ):
        raise N5ExecutionError("N5 execution contract identity changed")
    _check_integrity(root, label="N5 execution contract", scope=CONTRACT_HASH_SCOPE)
    try:
        p0 = validate_campaign_contract(root["p0_campaign"])
    except CampaignContractError as error:
        raise N5ExecutionError(f"N5 execution P0 is invalid: {error}") from error
    if (
        root["p0_campaign_canonical_sha256"] != p0["integrity"]["canonical_sha256"]
        or root["p0_campaign_file_sha256"] != _sha256(p0)
    ):
        raise N5ExecutionError("N5 execution P0 whole-file binding changed")
    source = _exact(
        root["source_manifest"],
        label="N5 execution source manifest binding",
        keys={"kind", "campaign_id", "canonical_sha256", "file_sha256"},
    )
    if source["kind"] != MANIFEST_KIND or source["campaign_id"] != p0["campaign_id"]:
        raise N5ExecutionError("N5 source manifest/P0 binding changed")
    _hash(source["canonical_sha256"], label="source manifest canonical SHA-256")
    _hash(source["file_sha256"], label="source manifest whole-file SHA-256")

    bindings = _exact(
        root["plan_bindings"], label="N5 plan bindings", keys=set(PLAN_CLASSES)
    )
    materialized: dict[str, bool] = {}
    for plan_class in PLAN_CLASSES:
        binding = bindings[plan_class]
        if not isinstance(binding, Mapping) or type(binding.get("materialized")) is not bool:
            raise N5ExecutionError(f"{plan_class} plan binding is invalid")
        materialized[plan_class] = binding["materialized"]
    if not materialized["descriptive"]:
        raise N5ExecutionError("descriptive N5 plan must remain materialized")

    action_slots = {
        entry["action_identity_sha256"]: entry.get("measurement_slots", [])
        for entry in root["actions"]
        if isinstance(entry, Mapping)
    }
    expected_actions = _derive_action_index(p0, action_slots)
    # _derive_action_index consumes the already-declared slot lists.  The
    # remaining explicit comparisons prevent callers from changing any action
    # or class field while preserving a superficially plausible index.
    if root["actions"] != expected_actions:
        raise N5ExecutionError("N5 execution action index changed")
    expected_sessions = _derive_session_index(p0)
    if root["sessions"] != expected_sessions:
        raise N5ExecutionError("N5 execution session index changed")
    keys = [entry["action_key"] for entry in root["actions"]]
    shas = [entry["action_identity_sha256"] for entry in root["actions"]]
    if len(keys) != len(set(keys)) or len(shas) != len(set(shas)):
        raise N5ExecutionError("N5 execution action keys or identities are duplicated")
    for entry in root["actions"]:
        if entry["plan_class"] != "descriptive" and not materialized[entry["plan_class"]]:
            raise N5ExecutionError("an action exists for an unmaterialized N5 plan")
        for slot in entry["measurement_slots"]:
            _exact(
                slot,
                label="N5 action measurement slot",
                keys={"slot_id", "measurement_phase"},
            )
            if slot["measurement_phase"] not in {
                "palette",
                "transition_initial",
                "transition_final",
            }:
                raise N5ExecutionError("N5 action measurement phase is invalid")
    expected_safety = {
        "workspace_global_atomic_claim_before_any_transport": True,
        "maximum_post_requests_per_action": 1,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "immediate_prior_pass_whole_file_result_required": True,
        "abnormal_termination_ineligibilizes_remaining_plan_actions": True,
        "runner_controls_j2_or_power": False,
        "formal_transition_one_cold_start_per_repeat": True,
        "formal_transition_j2_remains_on_across_six_actions": True,
        "formal_transition_manual_j2_cut_after_target": True,
    }
    if root["safety"] != expected_safety:
        raise N5ExecutionError("N5 execution safety contract changed")
    if root["readiness"].get("hardware_ready") is not False:
        raise N5ExecutionError("compiled N5 execution contract cannot claim hardware readiness")
    fixed_false = (
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
    )
    if root["classification"].get("offline_compiled") is not True or any(
        root["classification"].get(field) is not False for field in fixed_false
    ):
        raise N5ExecutionError("N5 execution compiler side-effect classification changed")
    return root


def execution_contract_file_sha256(contract: Mapping[str, Any]) -> str:
    return _sha256(validate_execution_contract(contract))


def load_action_snapshot(contract: Mapping[str, Any], action_key: str) -> ActionSnapshot:
    root = validate_execution_contract(contract)
    matches = [entry for entry in root["actions"] if entry["action_key"] == action_key]
    if len(matches) != 1:
        raise N5ExecutionError("action_key is not unique in the frozen N5 contract")
    entry = matches[0]
    action_matches = [
        action
        for action in root["p0_campaign"]["actions"]
        if action["action_identity_sha256"] == entry["action_identity_sha256"]
    ]
    session_matches = [
        session
        for session in root["p0_campaign"]["sessions"]
        if session["session_id"] == entry["session_id"]
    ]
    if len(action_matches) != 1 or len(session_matches) != 1:
        raise N5ExecutionError("N5 action snapshot P0 binding is not unique")
    return ActionSnapshot(
        key=action_key,
        plan_class=entry["plan_class"],
        order=entry["order"],
        action=_snapshot(action_matches[0]),
        session=_snapshot(session_matches[0]),
        measurement_slots=tuple(_snapshot(entry["measurement_slots"])),
    )


def validate_authorization(
    record: Mapping[str, Any], *, contract: Mapping[str, Any], snapshot: ActionSnapshot
) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="external N5 authorization",
        keys={
            "schema_version",
            "kind",
            "authorization_id",
            "action_identity_sha256",
            "execution_contract_canonical_sha256",
            "session_start_file_sha256",
            "issued_at",
            "expires_at",
            "operator_id",
            "authorization_artifact_sha256",
            "confirmation_sha256",
            "maximum_post_requests",
            "automatic_advance_authorized",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != AUTHORIZATION_KIND
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or root["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or not isinstance(root["authorization_id"], str)
        or not root["authorization_id"]
        or not isinstance(root["operator_id"], str)
        or not root["operator_id"]
        or root["maximum_post_requests"] != 1
        or type(root["maximum_post_requests"]) is not int
        or root["automatic_advance_authorized"] is not False
        or root["automatic_retry_authorized"] is not False
        or root["automatic_recovery_authorized"] is not False
    ):
        raise N5ExecutionError("external N5 authorization binding changed")
    for field in (
        "session_start_file_sha256",
        "authorization_artifact_sha256",
        "confirmation_sha256",
    ):
        _hash(root[field], label=f"authorization {field}")
    issued = _timestamp(root["issued_at"], label="authorization issued_at")
    expires = _timestamp(root["expires_at"], label="authorization expires_at")
    if expires <= issued:
        raise N5ExecutionError("external authorization validity interval is empty")
    _check_integrity(root, label="external N5 authorization")
    return root


def validate_session_start(
    record: Mapping[str, Any], *, snapshot: ActionSnapshot
) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N5 session-start observation",
        keys={
            "schema_version",
            "kind",
            "session_id",
            "observed_at",
            "power_mode",
            "j2_initially_off",
            "measured_panel_power_off_seconds",
            "controller_fresh_boot_observed",
            "j2_on_before_first_action",
            "supply_cv_current_normal",
            "temperature_normal",
            "physical_cutoff_available",
            "observation_artifact_sha256",
            "integrity",
        },
    )
    session = snapshot.session
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != SESSION_START_KIND
        or root["session_id"] != session["session_id"]
        or root["power_mode"] != session["power_mode"]
        or root["j2_on_before_first_action"] is not True
        or root["supply_cv_current_normal"] is not True
        or root["temperature_normal"] is not True
        or root["physical_cutoff_available"] is not True
    ):
        raise N5ExecutionError("N5 session-start binding or safety gate changed")
    _timestamp(root["observed_at"], label="session start observed_at")
    _hash(root["observation_artifact_sha256"], label="session start observation artifact")
    if session["power_mode"] == "panel_cold_cycle":
        measured = _number(
            root["measured_panel_power_off_seconds"],
            label="measured panel power-off seconds",
            minimum=0,
        )
        if (
            root["j2_initially_off"] is not True
            or root["controller_fresh_boot_observed"] is not True
            or measured < float(session["minimum_panel_power_off_seconds"])
        ):
            raise N5ExecutionError("reviewed panel-cold start was not observed")
    else:
        if (
            root["j2_initially_off"] is not False
            or root["measured_panel_power_off_seconds"] is not None
            or root["controller_fresh_boot_observed"] is not False
        ):
            raise N5ExecutionError("continuous N5 session falsely claims a cold start")
    _check_integrity(root, label="N5 session-start observation")
    return root


def seal_session_start(payload: Mapping[str, Any], *, snapshot: ActionSnapshot) -> dict[str, Any]:
    record = _seal(payload)
    validate_session_start(record, snapshot=snapshot)
    return record


def _validate_runtime_gates(
    gates: Mapping[str, Any], *, profile: Mapping[str, Any]
) -> Mapping[str, Any]:
    root = _exact(
        gates,
        label="N5 runtime gates",
        keys={
            "observed_at",
            "start_temperature_c",
            "supply_cv_current_normal",
            "j2_on",
            "physical_cutoff_available",
            "operator_advance_artifact_sha256",
            "runtime_evidence_sha256",
        },
    )
    _timestamp(root["observed_at"], label="runtime gates observed_at")
    start = _number(root["start_temperature_c"], label="runtime start temperature")
    limits = profile["limits"]
    if not float(limits["minimum_start_temperature_c"]) <= start <= float(
        limits["maximum_start_temperature_c"]
    ):
        raise N5ExecutionError("runtime start temperature is outside reviewed limits")
    if any(
        root[field] is not True
        for field in (
            "supply_cv_current_normal",
            "j2_on",
            "physical_cutoff_available",
        )
    ):
        raise N5ExecutionError("N5 runtime electrical/operator gates are not all true")
    _hash(
        root["operator_advance_artifact_sha256"],
        label="operator advance artifact",
    )
    _hash(root["runtime_evidence_sha256"], label="runtime evidence")
    return root


def _prior_from_bundle_summary(
    contract: Mapping[str, Any],
    snapshot: ActionSnapshot,
    prior_bundle: Optional[Mapping[str, Any]],
) -> tuple[Optional[Mapping[str, Any]], Optional[str], Optional[str]]:
    prior_decl = snapshot.action["identity"]["prior"]
    if prior_decl is None:
        if prior_bundle is not None:
            raise N5ExecutionError("root N5 action must not receive a prior bundle")
        return None, None, None
    if prior_bundle is None:
        return None, None, None
    expected_sha = prior_decl["action_identity_sha256"]
    if prior_bundle.get("kind") == BUNDLE_KIND:
        summary = validate_finalized_bundle(contract, prior_bundle)
        action = summary["actions_by_sha"].get(expected_sha)
    else:
        # During a six-action session the session bundle cannot be finalized
        # until its target completes.  The next manually invoked action may
        # therefore bind the immediately preceding finalized action item.
        action = _validate_action_item(contract, prior_bundle)
        if action["action_identity_sha256"] != expected_sha:
            action = None
    if action is None or action["state"] != ResultState.PASS.value:
        raise N5ExecutionError("immediate prior action is absent or not PASS")
    return action["result"], action["result_file_sha256"], action[
        "finalization_file_sha256"
    ]


def describe_fixed_action(
    contract: Mapping[str, Any],
    action_key: str,
    *,
    limit_profile: Optional[Mapping[str, Any]] = None,
    evaluated_at: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Describe one action without claim, authorization, filesystem, or device I/O."""

    root = validate_execution_contract(contract)
    snapshot = load_action_snapshot(root, action_key)
    blockers: list[str] = []
    p0_description = None
    prior_result, prior_result_sha, _prior_finalization_sha = _prior_from_bundle_summary(
        root, snapshot, prior_bundle
    )
    if limit_profile is None:
        blockers.append("canonical_reviewed_limit_profile_missing")
    if evaluated_at is None:
        blockers.append("explicit_profile_evaluation_time_missing")
    if snapshot.action["identity"]["prior"] is not None and prior_result is None:
        blockers.append("immediate_prior_finalized_pass_bundle_missing")
    if limit_profile is not None and evaluated_at is not None:
        try:
            p0_description = describe_action_offline(
                root["p0_campaign"],
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=limit_profile,
                evaluated_at=evaluated_at,
                prior_result=prior_result,
                prior_result_sha256=prior_result_sha,
            )
        except CampaignContractError as error:
            raise N5ExecutionError(f"N5 P0 action description failed: {error}") from error
        blockers.extend(
            blocker
            for blocker in p0_description["blockers"]
            if blocker != "current_runtime_gates_and_exact_authorization_not_evaluated"
        )
    blockers.extend(
        [
            "current_runtime_gates_not_observed",
            "external_exact_one_action_authorization_not_supplied",
        ]
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "execution_contract_canonical_sha256": root["integrity"]["canonical_sha256"],
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "plan_class": snapshot.plan_class,
        "session_id": snapshot.session["session_id"],
        "power_mode": snapshot.session["power_mode"],
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "p0_description": p0_description,
        "contract_ready": not [
            blocker
            for blocker in blockers
            if blocker
            not in {
                "current_runtime_gates_not_observed",
                "external_exact_one_action_authorization_not_supplied",
            }
        ],
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "blockers": list(dict.fromkeys(blockers)),
    }
    return _seal(payload)


def _validate_profile_for_action(
    contract: Mapping[str, Any],
    snapshot: ActionSnapshot,
    profile: Mapping[str, Any],
    *,
    evaluated_at: str,
    prior_result: Optional[Mapping[str, Any]],
    prior_result_sha256: Optional[str],
) -> Mapping[str, Any]:
    try:
        validated = validate_limit_profile(profile)
        description = describe_action_offline(
            contract["p0_campaign"],
            action_identity_sha256=snapshot.action["action_identity_sha256"],
            limit_profile=validated,
            evaluated_at=evaluated_at,
            prior_result=prior_result,
            prior_result_sha256=prior_result_sha256,
        )
    except CampaignContractError as error:
        raise N5ExecutionError(f"reviewed N5 limit profile is invalid: {error}") from error
    if not description["contract_ready"]:
        raise N5ExecutionError(
            "reviewed N5 limit profile/action is blocked: "
            + ", ".join(description["blockers"])
        )
    return validated


def _claim_record(
    contract: Mapping[str, Any],
    snapshot: ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    authorization: Mapping[str, Any],
    authorization_sha256: str,
    session_start_sha256: str,
    profile: Mapping[str, Any],
    profile_sha256: str,
    evaluated_at: str,
    prior_result_sha256: Optional[str],
    prior_finalization_sha256: Optional[str],
    runtime_gates: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "workspace_relative_registry": CLAIM_REGISTRY_RELATIVE_PATH,
        "filename": f"{snapshot.action['action_identity_sha256']}.json",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": contract["integrity"]["canonical_sha256"],
        "p0_campaign_canonical_sha256": contract["p0_campaign_canonical_sha256"],
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_id": authorization["authorization_id"],
        "authorization_file_sha256": authorization_sha256,
        "session_start_file_sha256": session_start_sha256,
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_sha256,
        "profile_evaluated_at": evaluated_at,
        "prior_result_file_sha256": prior_result_sha256,
        "prior_finalization_file_sha256": prior_finalization_sha256,
        "runtime_gates": _snapshot(runtime_gates),
        "atomic_create_mode": "exclusive-create-before-any-transport",
        "maximum_post_requests": 1,
        "automatic_advance_authorized": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def execute_fixed_action_once(
    contract: Mapping[str, Any],
    action_key: str,
    frame: bytes,
    *,
    limit_profile: Mapping[str, Any],
    profile_evaluated_at: str,
    authorization: Mapping[str, Any],
    session_start: Mapping[str, Any],
    runtime_gates: Mapping[str, Any],
    prior_bundle: Optional[Mapping[str, Any]],
    attempt_id: str,
    claimed_at: str,
    protocol_completed_at: str,
    claim_store: AtomicWorkspaceClaimStore,
    transport: Callable[[str, str, Optional[bytes]], Any],
    protocol_driver: Callable[[AuditedTransport, bytes], Mapping[str, Any]],
) -> dict[str, Any]:
    """Consume one global claim, then run exactly one caller-selected action."""

    root = validate_execution_contract(contract)
    snapshot = load_action_snapshot(root, action_key)
    if not isinstance(frame, bytes) or hashlib.sha256(frame).hexdigest() != snapshot.action[
        "identity"
    ]["frame"]["sha256"]:
        raise N5ExecutionError("caller-supplied frame bytes differ from frozen action")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise N5ExecutionError("attempt_id must be supplied by the caller")
    claimed_time = _timestamp(claimed_at, label="claimed_at")
    completed_time = _timestamp(protocol_completed_at, label="protocol_completed_at")
    if completed_time < claimed_time:
        raise N5ExecutionError("protocol completion precedes claim")
    session_root = validate_session_start(session_start, snapshot=snapshot)
    session_sha = _sha256(session_root)
    authorization_root = validate_authorization(
        authorization, contract=root, snapshot=snapshot
    )
    if authorization_root["session_start_file_sha256"] != session_sha:
        raise N5ExecutionError("authorization is bound to another session-start record")
    session_observed_time = _timestamp(
        session_root["observed_at"], label="session start observed_at"
    )
    authorization_issued_time = _timestamp(
        authorization_root["issued_at"], label="authorization issued_at"
    )
    profile_evaluated_time = _timestamp(
        profile_evaluated_at, label="profile_evaluated_at"
    )
    if not (
        session_observed_time
        <= authorization_issued_time
        <= claimed_time
        < _timestamp(authorization_root["expires_at"], label="authorization expires_at")
    ):
        raise N5ExecutionError("external authorization is not valid at claim time")
    if not session_observed_time <= profile_evaluated_time <= claimed_time:
        raise N5ExecutionError("N5 limit profile evaluation is outside session/claim order")
    prior_result, prior_result_sha, prior_finalization_sha = _prior_from_bundle_summary(
        root, snapshot, prior_bundle
    )
    if snapshot.action["identity"]["prior"] is not None and prior_result is None:
        raise N5ExecutionError("dependent action lacks its immediate prior PASS bundle")
    profile = _validate_profile_for_action(
        root,
        snapshot,
        limit_profile,
        evaluated_at=profile_evaluated_at,
        prior_result=prior_result,
        prior_result_sha256=prior_result_sha,
    )
    gates = _validate_runtime_gates(runtime_gates, profile=profile)
    gates_observed_time = _timestamp(
        gates["observed_at"], label="runtime gates observed_at"
    )
    if not session_observed_time <= gates_observed_time <= claimed_time:
        raise N5ExecutionError("N5 runtime gates are outside session/claim order")
    authorization_sha = _sha256(authorization_root)
    profile_sha = _sha256(profile)
    claim = _claim_record(
        root,
        snapshot,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        authorization=authorization_root,
        authorization_sha256=authorization_sha,
        session_start_sha256=session_sha,
        profile=profile,
        profile_sha256=profile_sha,
        evaluated_at=profile_evaluated_at,
        prior_result_sha256=prior_result_sha,
        prior_finalization_sha256=prior_finalization_sha,
        runtime_gates=gates,
    )
    # This is the only pre-transport mutation.  Any later error is terminal.
    claim_sha = claim_store.commit(snapshot.action, claim)
    audited = AuditedTransport(
        transport,
        endpoint=snapshot.action["identity"]["request"]["endpoint"],
        frame_sha256=snapshot.action["identity"]["frame"]["sha256"],
    )
    device_evidence: Optional[Mapping[str, Any]] = None
    error_record: Optional[dict[str, str]] = None
    outcome = ResultState.UNKNOWN_DO_NOT_RETRY.value
    protocol_verified = False
    try:
        device_evidence = protocol_driver(audited, frame)
        if not isinstance(device_evidence, Mapping):
            raise N5ExecutionError("protocol driver must return an evidence object")
        audit = audited.snapshot()
        if audit["post_attempt_count"] != 1 or audit["post_issued_count"] != 1:
            raise N5ExecutionError("N5 action did not issue exactly one visible POST")
        protocol_verified = True
        outcome = ResultState.PASS.value
    except BaseException as error:
        audit = audited.snapshot()
        error_record = {"type": type(error).__name__, "message": str(error)}
    protocol_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROTOCOL_KIND,
        "attempt_id": attempt_id,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": root["integrity"]["canonical_sha256"],
        "claim_file_sha256": claim_sha,
        "session_start_file_sha256": session_sha,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "prior_result_file_sha256": prior_result_sha,
        "prior_finalization_file_sha256": prior_finalization_sha,
        "recorded_at": protocol_completed_at,
        "outcome": outcome,
        "protocol_verified": protocol_verified,
        "device_evidence": None if device_evidence is None else _snapshot(device_evidence),
        "device_evidence_sha256": (
            None if device_evidence is None else _sha256(device_evidence)
        ),
        "request_audit": audit,
        "maximum_post_requests": 1,
        "automatic_advance": False,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
        "error": error_record,
    }
    protocol = _seal(protocol_payload)
    receipt_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROTOCOL_RECEIPT_KIND,
        "authorization": _snapshot(authorization_root),
        "authorization_file_sha256": authorization_sha,
        "session_start": _snapshot(session_root),
        "session_start_file_sha256": session_sha,
        "profile": _snapshot(profile),
        "profile_file_sha256": profile_sha,
        "claim": claim,
        "claim_file_sha256": claim_sha,
        "protocol_evidence": protocol,
        "protocol_evidence_file_sha256": _sha256(protocol),
    }
    receipt = _seal(receipt_payload)
    if not protocol_verified:
        raise N5PostClaimUnknown(
            "N5 action is UNKNOWN_DO_NOT_RETRY after permanent claim consumption",
            receipt=receipt,
        )
    return receipt


_MEASUREMENT_BINDING_KEYS = {
    "slot_id",
    "measurement_phase",
    "source_run_sha256",
    "asset_manifest_sha256",
    "measurement_record_sha256",
    "raw_spectrum_artifact_sha256",
    "spectral_report_file_sha256",
    "metrics_sha256",
}


def validate_manual_observation(
    record: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    snapshot: ActionSnapshot,
    attempt_id: str,
    protocol_evidence_file_sha256: str,
) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N5 manual measurement observation",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "attempt_id",
            "action_key",
            "action_identity_sha256",
            "protocol_evidence_file_sha256",
            "observed_at",
            "source_observation_artifact_sha256",
            "visual_pass",
            "electrical_pass",
            "thermal_pass",
            "measurement_pass",
            "continuity",
            "measurement_bindings",
            "notes",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != MANUAL_OBSERVATION_KIND
        or root["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or root["attempt_id"] != attempt_id
        or root["action_key"] != snapshot.key
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or root["protocol_evidence_file_sha256"]
        != protocol_evidence_file_sha256
    ):
        raise N5ExecutionError("N5 manual observation binding changed")
    _timestamp(root["observed_at"], label="manual observation observed_at")
    _hash(
        root["source_observation_artifact_sha256"],
        label="manual source observation artifact",
    )
    for field in ("visual_pass", "electrical_pass", "thermal_pass", "measurement_pass"):
        if type(root[field]) is not bool:
            raise N5ExecutionError(f"manual observation {field} must be boolean")
    all_manual_gates_pass = all(
        root[field]
        for field in (
            "visual_pass",
            "electrical_pass",
            "thermal_pass",
            "measurement_pass",
        )
    )
    continuity = _exact(
        root["continuity"],
        label="N5 action continuity",
        keys={
            "controller_restarted_since_prior",
            "j2_disconnected_since_prior",
            "panel_power_cycled_since_prior",
            "other_visible_refresh_since_prior",
        },
    )
    prior_sha = snapshot.action["identity"]["prior"]
    if prior_sha is None:
        if any(value is not None for value in continuity.values()):
            raise N5ExecutionError("root N5 action continuity fields must be null")
    else:
        if any(type(value) is not bool for value in continuity.values()):
            raise N5ExecutionError(
                "dependent N5 action continuity fields must be boolean"
            )
        actions = {
            action["action_identity_sha256"]: action
            for action in contract["p0_campaign"]["actions"]
        }
        prior_action = actions[prior_sha["action_identity_sha256"]]
        same_session = (
            prior_action["identity"]["session_id"]
            == snapshot.action["identity"]["session_id"]
        )
        expected = (
            {
                "controller_restarted_since_prior": False,
                "j2_disconnected_since_prior": False,
                "panel_power_cycled_since_prior": False,
                "other_visible_refresh_since_prior": False,
            }
            if same_session
            else {
                "controller_restarted_since_prior": (
                    snapshot.session["power_mode"] == "panel_cold_cycle"
                ),
                "j2_disconnected_since_prior": (
                    snapshot.session["power_mode"] == "panel_cold_cycle"
                ),
                "panel_power_cycled_since_prior": (
                    snapshot.session["power_mode"] == "panel_cold_cycle"
                ),
                "other_visible_refresh_since_prior": False,
            }
        )
        if all_manual_gates_pass and continuity != expected:
            raise N5ExecutionError("N5 action continuity contradicts session power semantics")
    bindings = root["measurement_bindings"]
    if not isinstance(bindings, list):
        raise N5ExecutionError("N5 measurement bindings must be a list")
    expected_slots = [
        (slot["slot_id"], slot["measurement_phase"])
        for slot in snapshot.measurement_slots
    ]
    observed_slots: list[tuple[str, str]] = []
    seen_slots: set[tuple[str, str]] = set()
    for binding in bindings:
        item = _exact(
            binding,
            label="N5 measurement binding",
            keys=_MEASUREMENT_BINDING_KEYS,
        )
        key = (item["slot_id"], item["measurement_phase"])
        if key in seen_slots:
            raise N5ExecutionError("N5 measurement binding slot is duplicated")
        seen_slots.add(key)
        observed_slots.append(key)
        if item["measurement_phase"] not in {
            "palette",
            "transition_initial",
            "transition_final",
        }:
            raise N5ExecutionError("N5 measurement binding phase is invalid")
        for field in (
            "source_run_sha256",
            "asset_manifest_sha256",
            "measurement_record_sha256",
            "raw_spectrum_artifact_sha256",
            "spectral_report_file_sha256",
        ):
            _hash(item[field], label=f"measurement binding {field}")
        metrics = _hash(item["metrics_sha256"], label="measurement metrics", nullable=True)
        if (item["measurement_phase"] == "transition_final") != (metrics is not None):
            raise N5ExecutionError("only transition-final bindings require metrics SHA-256")
    if root["measurement_pass"] is True and observed_slots != expected_slots:
        raise N5ExecutionError(
            "measurement PASS does not bind every frozen measurement slot in order"
        )
    if root["measurement_pass"] is False and observed_slots != expected_slots[: len(observed_slots)]:
        raise N5ExecutionError(
            "terminal FAIL/UNKNOWN measurement bindings must be a frozen ordered prefix"
        )
    if root["notes"] is not None and not isinstance(root["notes"], str):
        raise N5ExecutionError("manual observation notes must be text or null")
    if not all_manual_gates_pass and (
        not isinstance(root["notes"], str) or not root["notes"].strip()
    ):
        raise N5ExecutionError(
            "terminal FAIL/UNKNOWN observation requires a non-empty operator note"
        )
    _check_integrity(root, label="N5 manual measurement observation")
    return root


def seal_manual_observation(
    payload: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    action_key: str,
    attempt_id: str,
    protocol_evidence_file_sha256: str,
) -> dict[str, Any]:
    root = validate_execution_contract(contract)
    snapshot = load_action_snapshot(root, action_key)
    record = _seal(payload)
    validate_manual_observation(
        record,
        contract=root,
        snapshot=snapshot,
        attempt_id=attempt_id,
        protocol_evidence_file_sha256=protocol_evidence_file_sha256,
    )
    return record


def _validate_request_audit(
    audit: Any, *, snapshot: ActionSnapshot, pass_required: bool
) -> Mapping[str, Any]:
    root = _exact(
        audit,
        label="N5 request audit",
        keys={"post_attempt_count", "post_issued_count", "calls"},
    )
    for field in ("post_attempt_count", "post_issued_count"):
        if type(root[field]) is not int or root[field] not in {0, 1}:
            raise N5ExecutionError("N5 request audit POST count must be zero or one")
    if root["post_issued_count"] > root["post_attempt_count"]:
        raise N5ExecutionError("N5 issued POST count exceeds attempts")
    if pass_required and (
        root["post_attempt_count"] != 1 or root["post_issued_count"] != 1
    ):
        raise N5ExecutionError("PASS N5 protocol requires exactly one POST")
    if not isinstance(root["calls"], list):
        raise N5ExecutionError("N5 request audit calls must be a list")
    posts = []
    for index, call in enumerate(root["calls"], start=1):
        item = _exact(
            call,
            label="N5 audited request",
            keys={"sequence", "method", "endpoint", "request_body_sha256"},
        )
        if item["sequence"] != index:
            raise N5ExecutionError("N5 request audit sequence is not contiguous")
        if item["method"] == "POST":
            posts.append(item)
        elif (
            item["method"] != "GET"
            or item["endpoint"] not in _ALLOWED_GET_ENDPOINTS
            or item["request_body_sha256"] is not None
        ):
            raise N5ExecutionError("N5 request audit contains an unapproved route")
    if len(posts) != root["post_attempt_count"]:
        raise N5ExecutionError("N5 request audit POST list/count differs")
    for post in posts:
        if (
            post["endpoint"] != snapshot.action["identity"]["request"]["endpoint"]
            or post["request_body_sha256"]
            != snapshot.action["identity"]["frame"]["sha256"]
        ):
            raise N5ExecutionError("N5 request audit POST endpoint/frame changed")
    return root


def _validate_action_item(
    contract: Mapping[str, Any], item: Mapping[str, Any]
) -> dict[str, Any]:
    root = _exact(
        item,
        label="N5 finalized action item",
        keys={
            "action_key",
            "action_identity_sha256",
            "authorization",
            "authorization_file_sha256",
            "profile",
            "profile_file_sha256",
            "claim",
            "claim_file_sha256",
            "protocol_evidence",
            "protocol_evidence_file_sha256",
            "manual_observation",
            "manual_observation_file_sha256",
            "finalization",
            "finalization_file_sha256",
            "result",
            "result_file_sha256",
        },
    )
    snapshot = load_action_snapshot(contract, str(root["action_key"]))
    action_sha = snapshot.action["action_identity_sha256"]
    if root["action_identity_sha256"] != action_sha:
        raise N5ExecutionError("N5 action item identity changed")
    records = {}
    for name in (
        "authorization",
        "profile",
        "claim",
        "protocol_evidence",
        "manual_observation",
        "finalization",
        "result",
    ):
        record = root[name]
        if not isinstance(record, Mapping):
            raise N5ExecutionError(f"N5 action item {name} must be an object")
        declared = _hash(root[f"{name}_file_sha256"], label=f"{name} whole-file SHA-256")
        actual = _sha256(record)
        if declared != actual:
            raise N5ExecutionError(f"N5 action item {name} whole-file SHA-256 changed")
        records[name] = record
    authorization = validate_authorization(
        records["authorization"], contract=contract, snapshot=snapshot
    )
    try:
        profile = validate_limit_profile(records["profile"])
    except CampaignContractError as error:
        raise N5ExecutionError(f"N5 action profile is invalid: {error}") from error
    claim = _exact(
        records["claim"],
        label="N5 consumed claim",
        keys={
            "schema_version",
            "kind",
            "registry_id",
            "workspace_relative_registry",
            "filename",
            "action_key",
            "action_identity_sha256",
            "execution_contract_canonical_sha256",
            "p0_campaign_canonical_sha256",
            "attempt_id",
            "claimed_at",
            "state",
            "authorization_consumed_permanently",
            "authorization_id",
            "authorization_file_sha256",
            "session_start_file_sha256",
            "profile_canonical_sha256",
            "profile_file_sha256",
            "profile_evaluated_at",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "runtime_gates",
            "atomic_create_mode",
            "maximum_post_requests",
            "automatic_advance_authorized",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
        },
    )
    expected_claim = workspace_global_claim_declaration(action_sha)
    if (
        claim["schema_version"] != SCHEMA_VERSION
        or claim["kind"] != CLAIM_KIND
        or claim["registry_id"] != expected_claim["registry_id"]
        or claim["workspace_relative_registry"]
        != expected_claim["workspace_relative_registry"]
        or claim["filename"] != expected_claim["filename"]
        or claim["action_key"] != snapshot.key
        or claim["action_identity_sha256"] != action_sha
        or claim["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or claim["p0_campaign_canonical_sha256"]
        != contract["p0_campaign_canonical_sha256"]
        or claim["state"] != "authorization_permanently_consumed_do_not_rerun"
        or claim["authorization_consumed_permanently"] is not True
        or claim["authorization_id"] != authorization["authorization_id"]
        or claim["authorization_file_sha256"] != root["authorization_file_sha256"]
        or claim["session_start_file_sha256"]
        != authorization["session_start_file_sha256"]
        or claim["profile_canonical_sha256"] != profile["integrity"]["canonical_sha256"]
        or claim["profile_file_sha256"] != root["profile_file_sha256"]
        or claim["atomic_create_mode"] != "exclusive-create-before-any-transport"
        or claim["maximum_post_requests"] != 1
        or claim["automatic_advance_authorized"] is not False
        or claim["automatic_retry_authorized"] is not False
        or claim["automatic_recovery_authorized"] is not False
    ):
        raise N5ExecutionError("N5 consumed claim binding changed")
    claimed_time = _timestamp(claim["claimed_at"], label="claim claimed_at")
    profile_evaluated_time = _timestamp(
        claim["profile_evaluated_at"], label="claim profile_evaluated_at"
    )
    if not (
        _timestamp(authorization["issued_at"], label="authorization issued_at")
        <= _timestamp(claim["claimed_at"], label="claim claimed_at")
        < _timestamp(authorization["expires_at"], label="authorization expires_at")
    ):
        raise N5ExecutionError("N5 claim falls outside external authorization validity")
    if profile_evaluated_time > claimed_time:
        raise N5ExecutionError("N5 profile evaluation follows claim consumption")
    _hash(claim["session_start_file_sha256"], label="claim session start")
    gates = _validate_runtime_gates(claim["runtime_gates"], profile=profile)
    if _timestamp(gates["observed_at"], label="runtime gates observed_at") > claimed_time:
        raise N5ExecutionError("N5 runtime gates follow claim consumption")

    protocol = _exact(
        records["protocol_evidence"],
        label="N5 protocol evidence",
        keys={
            "schema_version",
            "kind",
            "attempt_id",
            "action_key",
            "action_identity_sha256",
            "execution_contract_canonical_sha256",
            "claim_file_sha256",
            "session_start_file_sha256",
            "frame_sha256",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "recorded_at",
            "outcome",
            "protocol_verified",
            "device_evidence",
            "device_evidence_sha256",
            "request_audit",
            "maximum_post_requests",
            "automatic_advance",
            "automatic_retry_count",
            "retry_allowed",
            "recovery_performed",
            "error",
            "integrity",
        },
    )
    pass_protocol = protocol["outcome"] == ResultState.PASS.value
    if (
        protocol["schema_version"] != SCHEMA_VERSION
        or protocol["kind"] != PROTOCOL_KIND
        or protocol["attempt_id"] != claim["attempt_id"]
        or protocol["action_key"] != snapshot.key
        or protocol["action_identity_sha256"] != action_sha
        or protocol["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or protocol["claim_file_sha256"] != root["claim_file_sha256"]
        or protocol["session_start_file_sha256"] != claim["session_start_file_sha256"]
        or protocol["frame_sha256"] != snapshot.action["identity"]["frame"]["sha256"]
        or protocol["prior_result_file_sha256"] != claim["prior_result_file_sha256"]
        or protocol["prior_finalization_file_sha256"]
        != claim["prior_finalization_file_sha256"]
        or protocol["maximum_post_requests"] != 1
        or protocol["automatic_advance"] is not False
        or protocol["automatic_retry_count"] != 0
        or protocol["retry_allowed"] is not False
        or protocol["recovery_performed"] is not False
        or protocol["outcome"] not in {
            ResultState.PASS.value,
            ResultState.UNKNOWN_DO_NOT_RETRY.value,
        }
    ):
        raise N5ExecutionError("N5 protocol evidence binding changed")
    protocol_time = _timestamp(protocol["recorded_at"], label="protocol recorded_at")
    if protocol_time < claimed_time:
        raise N5ExecutionError("N5 protocol evidence precedes claim consumption")
    if pass_protocol:
        if (
            protocol["protocol_verified"] is not True
            or not isinstance(protocol["device_evidence"], Mapping)
            or protocol["device_evidence_sha256"] != _sha256(protocol["device_evidence"])
            or protocol["error"] is not None
        ):
            raise N5ExecutionError("PASS N5 protocol lacks immutable device evidence")
    elif protocol["protocol_verified"] is not False or protocol["error"] is None:
        raise N5ExecutionError("UNKNOWN N5 protocol evidence is inconsistent")
    _validate_request_audit(
        protocol["request_audit"], snapshot=snapshot, pass_required=pass_protocol
    )
    _check_integrity(protocol, label="N5 protocol evidence")

    manual = validate_manual_observation(
        records["manual_observation"],
        contract=contract,
        snapshot=snapshot,
        attempt_id=str(claim["attempt_id"]),
        protocol_evidence_file_sha256=str(root["protocol_evidence_file_sha256"]),
    )
    manual_time = _timestamp(manual["observed_at"], label="manual observation observed_at")
    if manual_time < protocol_time:
        raise N5ExecutionError("N5 manual observation precedes protocol evidence")
    finalization = _exact(
        records["finalization"],
        label="N5 action finalization",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "attempt_id",
            "action_key",
            "action_identity_sha256",
            "state",
            "authorization_file_sha256",
            "claim_file_sha256",
            "protocol_evidence_file_sha256",
            "manual_observation_file_sha256",
            "profile_file_sha256",
            "prior_result_file_sha256",
            "prior_finalization_file_sha256",
            "completed_at",
            "automatic_advance",
            "automatic_retry_count",
            "retry_allowed",
            "recovery_performed",
            "integrity",
        },
    )
    derived_state = (
        ResultState.UNKNOWN_DO_NOT_RETRY.value
        if not pass_protocol
        else (
            ResultState.PASS.value
            if all(
                manual[field]
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "thermal_pass",
                    "measurement_pass",
                )
            )
            else ResultState.FAIL.value
        )
    )
    if (
        finalization["schema_version"] != SCHEMA_VERSION
        or finalization["kind"] != ACTION_FINALIZATION_KIND
        or finalization["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or finalization["attempt_id"] != claim["attempt_id"]
        or finalization["action_key"] != snapshot.key
        or finalization["action_identity_sha256"] != action_sha
        or finalization["state"] != derived_state
        or finalization["authorization_file_sha256"] != root["authorization_file_sha256"]
        or finalization["claim_file_sha256"] != root["claim_file_sha256"]
        or finalization["protocol_evidence_file_sha256"]
        != root["protocol_evidence_file_sha256"]
        or finalization["manual_observation_file_sha256"]
        != root["manual_observation_file_sha256"]
        or finalization["profile_file_sha256"] != root["profile_file_sha256"]
        or finalization["prior_result_file_sha256"] != claim["prior_result_file_sha256"]
        or finalization["prior_finalization_file_sha256"]
        != claim["prior_finalization_file_sha256"]
        or finalization["automatic_advance"] is not False
        or finalization["automatic_retry_count"] != 0
        or finalization["retry_allowed"] is not False
        or finalization["recovery_performed"] is not False
    ):
        raise N5ExecutionError("N5 action finalization binding changed")
    completed_time = _timestamp(
        finalization["completed_at"], label="action finalization completed_at"
    )
    if completed_time < manual_time:
        raise N5ExecutionError("N5 action finalization precedes manual observation")
    _check_integrity(finalization, label="N5 action finalization")
    try:
        result = validate_result_record(records["result"])
    except CampaignContractError as error:
        raise N5ExecutionError(f"N5 P0 result is invalid: {error}") from error
    if (
        result_file_sha256(result) != root["result_file_sha256"]
        or result["action_identity_sha256"] != action_sha
        or result["state"] != derived_state
        or result["evidence_manifest_sha256"] != root["finalization_file_sha256"]
        or result["post_request_count"] != protocol["request_audit"]["post_issued_count"]
        or result["completed_at"] != finalization["completed_at"]
    ):
        raise N5ExecutionError("N5 result/finalization whole-file binding changed")
    return {
        "action_key": snapshot.key,
        "action_identity_sha256": action_sha,
        "plan_class": snapshot.plan_class,
        "session_id": snapshot.session["session_id"],
        "order": snapshot.order,
        "state": derived_state,
        "authorization_id": authorization["authorization_id"],
        "profile": _snapshot(profile),
        "profile_evaluated_at": claim["profile_evaluated_at"],
        "claimed_at": claim["claimed_at"],
        "protocol_recorded_at": protocol["recorded_at"],
        "manual_observed_at": manual["observed_at"],
        "completed_at": finalization["completed_at"],
        "session_start_file_sha256": claim["session_start_file_sha256"],
        "prior_result_file_sha256": claim["prior_result_file_sha256"],
        "prior_finalization_file_sha256": claim["prior_finalization_file_sha256"],
        "result": _snapshot(result),
        "result_file_sha256": root["result_file_sha256"],
        "finalization_file_sha256": root["finalization_file_sha256"],
        "manual_observation": _snapshot(manual),
    }


def finalize_protocol_receipt(
    contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manual_observation: Mapping[str, Any],
    *,
    completed_at: str,
) -> dict[str, Any]:
    """Combine protocol and manual records into one terminal action item."""

    root_contract = validate_execution_contract(contract)
    receipt_root = _exact(
        receipt,
        label="N5 protocol receipt",
        keys={
            "schema_version",
            "kind",
            "authorization",
            "authorization_file_sha256",
            "session_start",
            "session_start_file_sha256",
            "profile",
            "profile_file_sha256",
            "claim",
            "claim_file_sha256",
            "protocol_evidence",
            "protocol_evidence_file_sha256",
            "integrity",
        },
    )
    if receipt_root["schema_version"] != SCHEMA_VERSION or receipt_root["kind"] != PROTOCOL_RECEIPT_KIND:
        raise N5ExecutionError("N5 protocol receipt identity changed")
    _check_integrity(receipt_root, label="N5 protocol receipt")
    for name in ("authorization", "session_start", "profile", "claim", "protocol_evidence"):
        if receipt_root[f"{name}_file_sha256"] != _sha256(receipt_root[name]):
            raise N5ExecutionError(f"N5 receipt {name} whole-file SHA-256 changed")
    claim = receipt_root["claim"]
    snapshot = load_action_snapshot(root_contract, str(claim["action_key"]))
    protocol = receipt_root["protocol_evidence"]
    manual = validate_manual_observation(
        manual_observation,
        contract=root_contract,
        snapshot=snapshot,
        attempt_id=str(claim["attempt_id"]),
        protocol_evidence_file_sha256=str(receipt_root["protocol_evidence_file_sha256"]),
    )
    pass_protocol = protocol["outcome"] == ResultState.PASS.value
    state = (
        ResultState.UNKNOWN_DO_NOT_RETRY.value
        if not pass_protocol
        else (
            ResultState.PASS.value
            if all(
                manual[field]
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "thermal_pass",
                    "measurement_pass",
                )
            )
            else ResultState.FAIL.value
        )
    )
    _timestamp(completed_at, label="action completed_at")
    manual_sha = _sha256(manual)
    finalization = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": ACTION_FINALIZATION_KIND,
            "execution_contract_canonical_sha256": root_contract["integrity"][
                "canonical_sha256"
            ],
            "attempt_id": claim["attempt_id"],
            "action_key": snapshot.key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "state": state,
            "authorization_file_sha256": receipt_root["authorization_file_sha256"],
            "claim_file_sha256": receipt_root["claim_file_sha256"],
            "protocol_evidence_file_sha256": receipt_root[
                "protocol_evidence_file_sha256"
            ],
            "manual_observation_file_sha256": manual_sha,
            "profile_file_sha256": receipt_root["profile_file_sha256"],
            "prior_result_file_sha256": claim["prior_result_file_sha256"],
            "prior_finalization_file_sha256": claim[
                "prior_finalization_file_sha256"
            ],
            "completed_at": completed_at,
            "automatic_advance": False,
            "automatic_retry_count": 0,
            "retry_allowed": False,
            "recovery_performed": False,
        }
    )
    finalization_sha = _sha256(finalization)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=state,
        completed_at=completed_at,
        evidence_manifest_sha256=finalization_sha,
        post_request_count=protocol["request_audit"]["post_issued_count"],
        details="N5 protocol and manual measurement finalized; no retry or recovery",
    )
    item = {
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "authorization": _snapshot(receipt_root["authorization"]),
        "authorization_file_sha256": receipt_root["authorization_file_sha256"],
        "profile": _snapshot(receipt_root["profile"]),
        "profile_file_sha256": receipt_root["profile_file_sha256"],
        "claim": _snapshot(claim),
        "claim_file_sha256": receipt_root["claim_file_sha256"],
        "protocol_evidence": _snapshot(protocol),
        "protocol_evidence_file_sha256": receipt_root[
            "protocol_evidence_file_sha256"
        ],
        "manual_observation": _snapshot(manual),
        "manual_observation_file_sha256": manual_sha,
        "finalization": finalization,
        "finalization_file_sha256": finalization_sha,
        "result": result,
        "result_file_sha256": result_file_sha256(result),
    }
    _validate_action_item(root_contract, item)
    return item


def _expected_continuity(
    contract: Mapping[str, Any], snapshot: ActionSnapshot
) -> dict[str, Optional[bool]]:
    prior = snapshot.action["identity"]["prior"]
    if prior is None:
        return {
            "controller_restarted_since_prior": None,
            "j2_disconnected_since_prior": None,
            "panel_power_cycled_since_prior": None,
            "other_visible_refresh_since_prior": None,
        }
    action_by_sha = {
        action["action_identity_sha256"]: action
        for action in contract["p0_campaign"]["actions"]
    }
    prior_action = action_by_sha[prior["action_identity_sha256"]]
    same_session = prior_action["identity"]["session_id"] == snapshot.session["session_id"]
    cold = snapshot.session["power_mode"] == "panel_cold_cycle"
    return {
        "controller_restarted_since_prior": False if same_session else cold,
        "j2_disconnected_since_prior": False if same_session else cold,
        "panel_power_cycled_since_prior": False if same_session else cold,
        "other_visible_refresh_since_prior": False,
    }


def expected_continuity(contract: Mapping[str, Any], action_key: str) -> dict[str, Optional[bool]]:
    """Return the frozen manual continuity fields for one action."""

    root = validate_execution_contract(contract)
    return _expected_continuity(root, load_action_snapshot(root, action_key))


def build_finalized_bundle(
    contract: Mapping[str, Any],
    action_items: Sequence[Mapping[str, Any]],
    session_starts: Sequence[Mapping[str, Any]],
    *,
    finalized_at: str,
    j2_cut_session_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Seal a dependency-closed action/session bundle; performs no I/O."""

    root = validate_execution_contract(contract)
    bundle_finalized_time = _timestamp(finalized_at, label="bundle finalized_at")
    summaries = [_validate_action_item(root, item) for item in action_items]
    action_orders = [summary["order"] for summary in summaries]
    if action_orders != sorted(action_orders) or len(set(action_orders)) != len(
        action_orders
    ):
        raise N5ExecutionError(
            "N5 action items must be supplied once in strict execution-contract order"
        )
    if any(
        _timestamp(summary["completed_at"], label="action completed_at")
        > bundle_finalized_time
        for summary in summaries
    ):
        raise N5ExecutionError(
            "bundle/session finalization or manual J2 cut precedes an included action"
        )
    starts_by_session: dict[str, Mapping[str, Any]] = {}
    for start in session_starts:
        session_id = start.get("session_id") if isinstance(start, Mapping) else None
        action = next(
            (
                summary
                for summary in summaries
                if summary["session_id"] == session_id
            ),
            None,
        )
        if action is None:
            raise N5ExecutionError("session-start record has no finalized action")
        snapshot = load_action_snapshot(root, action["action_key"])
        validated = validate_session_start(start, snapshot=snapshot)
        if session_id in starts_by_session:
            raise N5ExecutionError("N5 session-start record is duplicated")
        starts_by_session[str(session_id)] = validated
    cut_values = list(j2_cut_session_ids)
    cut_set = set(cut_values)
    if len(cut_set) != len(cut_values):
        raise N5ExecutionError("manual J2-cut session id is duplicated")
    session_records = []
    session_index = {entry["session_id"]: entry for entry in root["sessions"]}
    included_session_ids = {summary["session_id"] for summary in summaries}
    unknown_cut_ids = cut_set - set(session_index)
    if unknown_cut_ids:
        raise N5ExecutionError("manual J2 cut names an unknown N5 session")
    extra_cut_ids = cut_set - included_session_ids
    if extra_cut_ids:
        raise N5ExecutionError(
            "manual J2 cut names a session absent from this finalized bundle"
        )
    for session_id in sorted(
        included_session_ids,
        key=lambda value: session_index[value]["order"],
    ):
        session = session_index[session_id]
        start = starts_by_session.get(session_id)
        if start is None:
            raise N5ExecutionError("finalized N5 session lacks its start observation")
        group = sorted(
            [summary for summary in summaries if summary["session_id"] == session_id],
            key=lambda summary: summary["order"],
        )
        expected = session["action_identity_sha256s"]
        actual = [summary["action_identity_sha256"] for summary in group]
        first_nonpass = next(
            (summary for summary in group if summary["state"] != ResultState.PASS.value),
            None,
        )
        required_prefix = expected if first_nonpass is None else expected[: len(actual)]
        if actual != required_prefix or (first_nonpass is None and actual != expected):
            raise N5ExecutionError("N5 session actions are not an exact terminal prefix")
        if first_nonpass is not None and group[-1] is not first_nonpass:
            raise N5ExecutionError("N5 session continued after an abnormal action")
        state = ResultState.PASS.value if first_nonpass is None else first_nonpass["state"]
        requires_cut = state != ResultState.PASS.value or (
            session["plan_class"] == "formal_transition"
            and len(actual) == len(expected)
        )
        cut = session_id in cut_set
        if cut != requires_cut:
            raise N5ExecutionError(
                "manual J2 cut must occur after any abnormal terminal action or "
                "a complete formal-transition target only"
            )
        cut_reason = (
            "abnormal_terminal"
            if state != ResultState.PASS.value
            else ("formal_transition_target" if requires_cut else None)
        )
        finalization = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": SESSION_FINALIZATION_KIND,
                "execution_contract_canonical_sha256": root["integrity"][
                    "canonical_sha256"
                ],
                "session_id": session_id,
                "plan_class": session["plan_class"],
                "state": state,
                "session_start_file_sha256": _sha256(start),
                "ordered_action_identity_sha256s": actual,
                "ordered_action_result_file_sha256s": [
                    summary["result_file_sha256"] for summary in group
                ],
                "manual_j2_cut_after_terminal_action": cut,
                "j2_cut_reason": cut_reason,
                "j2_state_after_finalization": "off" if cut else "on",
                "finalized_at": finalized_at,
                "automatic_advance": False,
                "automatic_retry": False,
                "automatic_recovery": False,
            }
        )
        session_records.append(
            {
                "session_start": _snapshot(start),
                "session_start_file_sha256": _sha256(start),
                "finalization": finalization,
                "finalization_file_sha256": _sha256(finalization),
            }
        )
    nonpass = [summary for summary in summaries if summary["state"] != ResultState.PASS.value]
    if len(nonpass) > 1:
        raise N5ExecutionError("N5 bundle contains more than one abnormal terminal action")
    if nonpass:
        terminal = nonpass[0]
        ineligible = [
            entry["action_identity_sha256"]
            for entry in root["actions"]
            if entry["plan_class"] == terminal["plan_class"]
            and entry["order"] > terminal["order"]
        ]
        included_action_ids = {
            summary["action_identity_sha256"] for summary in summaries
        }
        if included_action_ids.intersection(ineligible):
            raise N5ExecutionError(
                "N5 bundle contains an action made ineligible by an earlier abnormal stop"
            )
        termination = {
            "state": "abnormal-stop",
            "terminal_action_identity_sha256": terminal["action_identity_sha256"],
            "ineligible_action_identity_sha256s": ineligible,
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    else:
        termination = {
            "state": "normal",
            "terminal_action_identity_sha256": None,
            "ineligible_action_identity_sha256s": [],
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "execution_contract_canonical_sha256": root["integrity"]["canonical_sha256"],
        "execution_contract_file_sha256": execution_contract_file_sha256(root),
        "p0_campaign_canonical_sha256": root["p0_campaign_canonical_sha256"],
        "actions": [_snapshot(item) for item in action_items],
        "sessions": session_records,
        "termination": termination,
        "finalized_at": finalized_at,
    }
    bundle = {**payload, "integrity": _integrity(payload, BUNDLE_HASH_SCOPE)}
    validate_finalized_bundle(root, bundle)
    return bundle


def validate_finalized_bundle(
    contract: Mapping[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Pure, deep validator used as the only N5 formal aggregation gate."""

    root_contract = validate_execution_contract(contract)
    root = _exact(
        bundle,
        label="N5 finalized execution bundle",
        keys={
            "schema_version",
            "kind",
            "execution_contract_canonical_sha256",
            "execution_contract_file_sha256",
            "p0_campaign_canonical_sha256",
            "actions",
            "sessions",
            "termination",
            "finalized_at",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != BUNDLE_KIND
        or root["execution_contract_canonical_sha256"]
        != root_contract["integrity"]["canonical_sha256"]
        or root["execution_contract_file_sha256"]
        != execution_contract_file_sha256(root_contract)
        or root["p0_campaign_canonical_sha256"]
        != root_contract["p0_campaign_canonical_sha256"]
    ):
        raise N5ExecutionError("N5 finalized bundle contract/P0 binding changed")
    bundle_finalized_time = _timestamp(
        root["finalized_at"], label="bundle finalized_at"
    )
    _check_integrity(root, label="N5 finalized bundle", scope=BUNDLE_HASH_SCOPE)
    if not isinstance(root["actions"], list) or not root["actions"]:
        raise N5ExecutionError("N5 finalized bundle must contain actions")
    summaries = [_validate_action_item(root_contract, item) for item in root["actions"]]
    action_orders = [summary["order"] for summary in summaries]
    if action_orders != sorted(action_orders) or len(set(action_orders)) != len(
        action_orders
    ):
        raise N5ExecutionError(
            "N5 finalized bundle actions are not in strict contract order"
        )
    if any(
        _timestamp(summary["completed_at"], label="action completed_at")
        > bundle_finalized_time
        for summary in summaries
    ):
        raise N5ExecutionError(
            "bundle/session finalization or manual J2 cut precedes an included action"
        )
    by_sha: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        if summary["action_identity_sha256"] in by_sha:
            raise N5ExecutionError("N5 finalized action is duplicated")
        by_sha[summary["action_identity_sha256"]] = summary
    declaration_by_sha = {
        action["action_identity_sha256"]: action
        for action in root_contract["p0_campaign"]["actions"]
    }
    for summary in summaries:
        declaration = declaration_by_sha[summary["action_identity_sha256"]]
        prior = declaration["identity"]["prior"]
        if prior is None:
            if (
                summary["prior_result_file_sha256"] is not None
                or summary["prior_finalization_file_sha256"] is not None
            ):
                raise N5ExecutionError("root N5 action falsely binds a prior result")
            predecessor = None
        else:
            predecessor = by_sha.get(prior["action_identity_sha256"])
            if predecessor is None:
                raise N5ExecutionError("N5 finalized bundle is not dependency-closed")
            if predecessor["state"] != ResultState.PASS.value:
                raise N5ExecutionError("N5 action advanced from a non-PASS predecessor")
            if (
                summary["prior_result_file_sha256"]
                != predecessor["result_file_sha256"]
                or summary["prior_finalization_file_sha256"]
                != predecessor["finalization_file_sha256"]
            ):
                raise N5ExecutionError(
                    "N5 action does not bind the immediate prior PASS whole-file result"
                )
        snapshot = load_action_snapshot(root_contract, summary["action_key"])
        _validate_profile_for_action(
            root_contract,
            snapshot,
            summary["profile"],
            evaluated_at=summary["profile_evaluated_at"],
            prior_result=None if predecessor is None else predecessor["result"],
            prior_result_sha256=(
                None if predecessor is None else predecessor["result_file_sha256"]
            ),
        )
    if not isinstance(root["sessions"], list):
        raise N5ExecutionError("N5 finalized sessions must be a list")
    session_by_id = {entry["session_id"]: entry for entry in root_contract["sessions"]}
    seen_sessions: set[str] = set()
    seen_session_order: list[str] = []
    for item in root["sessions"]:
        session_record = _exact(
            item,
            label="N5 finalized session item",
            keys={
                "session_start",
                "session_start_file_sha256",
                "finalization",
                "finalization_file_sha256",
            },
        )
        start = session_record["session_start"]
        finalization = session_record["finalization"]
        if not isinstance(start, Mapping) or not isinstance(finalization, Mapping):
            raise N5ExecutionError("N5 finalized session records must be objects")
        if session_record["session_start_file_sha256"] != _sha256(start) or session_record[
            "finalization_file_sha256"
        ] != _sha256(finalization):
            raise N5ExecutionError("N5 finalized session whole-file SHA changed")
        session_id = finalization.get("session_id")
        if session_id not in session_by_id or session_id in seen_sessions:
            raise N5ExecutionError("N5 finalized session is unknown or duplicated")
        seen_sessions.add(str(session_id))
        seen_session_order.append(str(session_id))
        session = session_by_id[str(session_id)]
        group = sorted(
            [summary for summary in summaries if summary["session_id"] == session_id],
            key=lambda summary: summary["order"],
        )
        if not group:
            raise N5ExecutionError("N5 finalized session contains no action")
        snapshot = load_action_snapshot(root_contract, group[0]["action_key"])
        validate_session_start(start, snapshot=snapshot)
        if any(summary["session_start_file_sha256"] != _sha256(start) for summary in group):
            raise N5ExecutionError("N5 actions do not share their exact session-start record")
        final_root = _exact(
            finalization,
            label="N5 session finalization",
            keys={
                "schema_version",
                "kind",
                "execution_contract_canonical_sha256",
                "session_id",
                "plan_class",
                "state",
                "session_start_file_sha256",
                "ordered_action_identity_sha256s",
                "ordered_action_result_file_sha256s",
                "manual_j2_cut_after_terminal_action",
                "j2_cut_reason",
                "j2_state_after_finalization",
                "finalized_at",
                "automatic_advance",
                "automatic_retry",
                "automatic_recovery",
                "integrity",
            },
        )
        expected_ids = session["action_identity_sha256s"]
        actual_ids = [summary["action_identity_sha256"] for summary in group]
        first_nonpass = next(
            (summary for summary in group if summary["state"] != ResultState.PASS.value),
            None,
        )
        expected_state = ResultState.PASS.value if first_nonpass is None else first_nonpass[
            "state"
        ]
        if (
            final_root["schema_version"] != SCHEMA_VERSION
            or final_root["kind"] != SESSION_FINALIZATION_KIND
            or final_root["execution_contract_canonical_sha256"]
            != root_contract["integrity"]["canonical_sha256"]
            or final_root["session_id"] != session_id
            or final_root["plan_class"] != session["plan_class"]
            or final_root["state"] != expected_state
            or final_root["session_start_file_sha256"] != _sha256(start)
            or final_root["ordered_action_identity_sha256s"] != actual_ids
            or final_root["ordered_action_result_file_sha256s"]
            != [summary["result_file_sha256"] for summary in group]
            or final_root["automatic_advance"] is not False
            or final_root["automatic_retry"] is not False
            or final_root["automatic_recovery"] is not False
        ):
            raise N5ExecutionError("N5 session finalization binding changed")
        session_finalized_time = _timestamp(
            final_root["finalized_at"], label="session finalized_at"
        )
        if (
            final_root["finalized_at"] != root["finalized_at"]
            or any(
                _timestamp(summary["completed_at"], label="action completed_at")
                > session_finalized_time
                for summary in group
            )
        ):
            raise N5ExecutionError(
                "session finalization/manual J2-cut time precedes its action completion"
            )
        if first_nonpass is None:
            if actual_ids != expected_ids:
                raise N5ExecutionError("PASS N5 session is not complete")
        else:
            if actual_ids != expected_ids[: len(actual_ids)] or group[-1] is not first_nonpass:
                raise N5ExecutionError("N5 session continued after abnormal termination")
        requires_cut = first_nonpass is not None or (
            session["plan_class"] == "formal_transition"
            and first_nonpass is None
        )
        expected_cut_reason = (
            "abnormal_terminal"
            if first_nonpass is not None
            else ("formal_transition_target" if requires_cut else None)
        )
        if (
            final_root["manual_j2_cut_after_terminal_action"] is not requires_cut
            or final_root["j2_cut_reason"] != expected_cut_reason
            or final_root["j2_state_after_finalization"]
            != ("off" if requires_cut else "on")
        ):
            raise N5ExecutionError("N5 session final J2 semantics changed")
        _check_integrity(final_root, label="N5 session finalization")
    expected_session_ids = {summary["session_id"] for summary in summaries}
    if seen_sessions != expected_session_ids:
        raise N5ExecutionError("not every N5 action belongs to one finalized session")
    expected_session_order = [
        entry["session_id"]
        for entry in sorted(root_contract["sessions"], key=lambda value: value["order"])
        if entry["session_id"] in expected_session_ids
    ]
    if seen_session_order != expected_session_order:
        raise N5ExecutionError(
            "N5 finalized bundle sessions are not in strict contract order"
        )

    termination = _exact(
        root["termination"],
        label="N5 bundle termination",
        keys={
            "state",
            "terminal_action_identity_sha256",
            "ineligible_action_identity_sha256s",
            "automatic_advance",
            "automatic_retry",
            "automatic_recovery",
        },
    )
    nonpass = [summary for summary in summaries if summary["state"] != ResultState.PASS.value]
    if len(nonpass) > 1:
        raise N5ExecutionError("N5 bundle contains multiple abnormal terminal actions")
    if nonpass:
        terminal = nonpass[0]
        expected_ineligible = [
            entry["action_identity_sha256"]
            for entry in root_contract["actions"]
            if entry["plan_class"] == terminal["plan_class"]
            and entry["order"] > terminal["order"]
        ]
        if set(by_sha).intersection(expected_ineligible):
            raise N5ExecutionError(
                "N5 bundle contains an action made ineligible by an earlier abnormal stop"
            )
        expected_termination = {
            "state": "abnormal-stop",
            "terminal_action_identity_sha256": terminal["action_identity_sha256"],
            "ineligible_action_identity_sha256s": expected_ineligible,
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    else:
        expected_termination = {
            "state": "normal",
            "terminal_action_identity_sha256": None,
            "ineligible_action_identity_sha256s": [],
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    if termination != expected_termination:
        raise N5ExecutionError("N5 abnormal-stop/ineligibility contract changed")
    return {
        "bundle_canonical_sha256": root["integrity"]["canonical_sha256"],
        "bundle_file_sha256": _sha256(root),
        "state": termination["state"],
        "actions_by_sha": by_sha,
        "session_ids": sorted(seen_sessions),
        "execution_evidence_verified": True,
    }


def measurement_binding_for_slot(
    validated_bundle: Mapping[str, Any],
    *,
    action_identity_sha256: str,
    slot_id: str,
    measurement_phase: str,
) -> Mapping[str, Any]:
    """Return one unique deeply validated measurement binding."""

    actions = validated_bundle.get("actions_by_sha")
    if not isinstance(actions, Mapping):
        raise N5ExecutionError("validated finalized-bundle summary is required")
    action = actions.get(action_identity_sha256)
    if not isinstance(action, Mapping) or action.get("state") != ResultState.PASS.value:
        raise N5ExecutionError("measurement action is absent or not PASS")
    matches = [
        binding
        for binding in action["manual_observation"]["measurement_bindings"]
        if binding["slot_id"] == slot_id
        and binding["measurement_phase"] == measurement_phase
    ]
    if len(matches) != 1:
        raise N5ExecutionError("measurement slot binding is absent or duplicated")
    return matches[0]


__all__ = [
    "ACTION_FINALIZATION_KIND",
    "AUTHORIZATION_KIND",
    "AtomicWorkspaceClaimStore",
    "AuditedTransport",
    "BUNDLE_KIND",
    "CLAIM_KIND",
    "CONTRACT_ID",
    "CONTRACT_KIND",
    "DESCRIPTION_KIND",
    "MANUAL_OBSERVATION_KIND",
    "N5ClaimConsumedError",
    "N5ExecutionError",
    "N5PostClaimUnknown",
    "PLAN_CLASSES",
    "PROTOCOL_KIND",
    "PROTOCOL_RECEIPT_KIND",
    "SESSION_FINALIZATION_KIND",
    "SESSION_START_KIND",
    "ActionSnapshot",
    "build_finalized_bundle",
    "compile_execution_contract",
    "describe_fixed_action",
    "execute_fixed_action_once",
    "execution_contract_file_sha256",
    "expected_continuity",
    "finalize_protocol_receipt",
    "load_action_snapshot",
    "measurement_binding_for_slot",
    "seal_manual_observation",
    "seal_session_start",
    "validate_authorization",
    "validate_execution_contract",
    "validate_finalized_bundle",
    "validate_manual_observation",
    "validate_session_start",
]
