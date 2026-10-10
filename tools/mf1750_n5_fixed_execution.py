#!/usr/bin/env python3
"""Compile, describe, execute, and deeply finalize frozen N5 actions.

``list`` and ``describe`` are strictly offline and side-effect free.  ``run``
is the only device-I/O command: it consumes one caller-selected workspace
claim before the first GET, permits exactly one frame POST, and never advances,
retries, recovers, or controls J2.  Manual measurements, action finalization,
and dependency-closed session bundles remain separate explicit commands.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CLAIM_ROOT = REPO_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import generate_fixture  # noqa: E402
import host.extended_color.execution as execution  # noqa: E402
from host.extended_color.execution import N5ExecutionError  # noqa: E402
from host.extended_color.offline import (  # noqa: E402
    COLOR_NAME_BY_CODE,
    COLOR_ORDER,
    build_artifact,
    generate_transition_matrix_frames,
)
from tools import mf1750_n5_measurement_campaign as campaign  # noqa: E402
from tools import mf1750_frame_tool as frame_tool  # noqa: E402


RESULT_MANIFEST_FILE = "N5-MANIFEST.json"
RESULT_CONTRACT_FILE = "N5-EXECUTION-CONTRACT.json"
RESULT_PROFILE_FILE = "N5-REVIEWED-LIMIT-PROFILE.json"
RESULT_SESSION_START_FILE = "N5-SESSION-START.json"
RESULT_AUTHORIZATION_FILE = "N5-EXTERNAL-AUTHORIZATION.json"
RESULT_RUNTIME_GATES_FILE = "N5-RUNTIME-GATES.json"
RESULT_PRIOR_FILE = "N5-IMMEDIATE-PRIOR.json"
RESULT_RECEIPT_FILE = "N5-PROTOCOL-RECEIPT.json"
RESULT_PROTOCOL_PASS_READY_FILE = "N5-PROTOCOL-PASS-READY.json"
RESULT_PROTOCOL_TERMINAL_READY_FILE = "N5-PROTOCOL-TERMINAL-READY.json"
RESULT_PROTOCOL_OUTCOME_COMMIT_FILE = "N5-PROTOCOL-OUTCOME-COMMIT.json"
RESULT_MANUAL_FILE = "N5-MANUAL-OBSERVATION.json"
RESULT_FINALIZATION_FILE = "N5-ACTION-FINALIZATION.json"
RESULT_P0_RESULT_FILE = "P0-ACTION-RESULT.json"
RESULT_ACTION_ITEM_FILE = "N5-FINALIZED-ACTION-ITEM.json"
RESULT_FINALIZED_COMMIT_FILE = "N5-FINALIZED-ACTION-COMMIT.json"
RESULT_RUN_SELECTION_FILE = "N5-RUN-SELECTION.json"
RESULT_CLAIM_COMMIT_UNKNOWN_FILE = "N5-CLAIM-COMMIT-UNKNOWN.json"
PROTOCOL_PASS_READY_KIND = "mf1750-n5-protocol-pass-ready"
PROTOCOL_TERMINAL_READY_KIND = "mf1750-n5-protocol-terminal-ready"
PROTOCOL_OUTCOME_COMMIT_KIND = "mf1750-n5-protocol-outcome-commit"
FINALIZED_ACTION_COMMIT_KIND = "mf1750-n5-finalized-action-commit"


EXPECTED_DEFAULT_EXECUTION_CONTRACT_CANONICAL_SHA256: Optional[str] = (
    "b14d0e8dd4dff16268e29eb557a5c85b310acc10d59731ba3f9d4accb5bc832c"
)
EXPECTED_DEFAULT_EXECUTION_CONTRACT_FILE_SHA256: Optional[str] = (
    "c02e9956f14ea9ea92283691d44b3971685cbd19a9670e2508aed36303da93eb"
)


class N5FixedExecutionToolError(ValueError):
    """The frozen N5 source, frame catalog, or offline input is invalid."""


def _strict_json_file(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N5FixedExecutionToolError(f"cannot read {label}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N5FixedExecutionToolError(
                    f"{label} contains duplicate key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N5FixedExecutionToolError(
                    f"{label} contains unsupported constant {token}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N5FixedExecutionToolError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N5FixedExecutionToolError(f"{label} must contain a JSON object")
    return value


def compile_default_execution_contract() -> dict[str, Any]:
    """Compile the checked-in default 22-action descriptive runner envelope."""

    manifest = campaign.compile_campaign_manifest()
    contract = execution.compile_execution_contract(manifest)
    canonical_sha = contract["integrity"]["canonical_sha256"]
    file_sha = execution.execution_contract_file_sha256(contract)
    if (
        EXPECTED_DEFAULT_EXECUTION_CONTRACT_CANONICAL_SHA256 is not None
        and canonical_sha != EXPECTED_DEFAULT_EXECUTION_CONTRACT_CANONICAL_SHA256
    ):
        raise N5FixedExecutionToolError("default N5 execution contract identity changed")
    if (
        EXPECTED_DEFAULT_EXECUTION_CONTRACT_FILE_SHA256 is not None
        and file_sha != EXPECTED_DEFAULT_EXECUTION_CONTRACT_FILE_SHA256
    ):
        raise N5FixedExecutionToolError("default N5 execution contract file SHA changed")
    return contract


def compile_materialized_execution_contract(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an externally materialized N5 manifest, then freeze its runner."""

    try:
        campaign.validate_compiled_manifest(manifest)
        contract = execution.compile_execution_contract(manifest)
        execution.validate_execution_contract(contract)
    except (campaign.N5CampaignError, N5ExecutionError) as error:
        raise N5FixedExecutionToolError(
            f"N5 materialized execution contract is invalid: {error}"
        ) from error
    return contract


def _compile_production_execution_contract(
    manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    contract = compile_materialized_execution_contract(manifest)
    counts = {
        plan_class: sum(
            action["plan_class"] == plan_class for action in contract["actions"]
        )
        for plan_class in execution.PLAN_CLASSES
    }
    palette = manifest.get("formal_palette_plan")
    transition = manifest.get("formal_transition_plan")
    if (
        len(contract["actions"]) != 73
        or len(contract["sessions"]) != 26
        or counts
        != {"descriptive": 22, "formal_palette": 9, "formal_transition": 42}
        or not isinstance(palette, Mapping)
        or not isinstance(transition, Mapping)
        or palette.get("readiness", {}).get("measurement_ready") is not True
        or transition.get("readiness", {}).get("measurement_ready") is not True
    ):
        raise N5FixedExecutionToolError(
            "production N5 requires the fully reviewed 73-action/26-session manifest"
        )
    return contract


@lru_cache(maxsize=1)
def _frame_catalog() -> dict[str, bytes]:
    frames = [
        generate_fixture("map-orient-v1"),
        generate_fixture("global-v-bars"),
        generate_fixture("global-h-bars"),
        *(build_artifact(f"solid-{COLOR_NAME_BY_CODE[code]}").frame for code in COLOR_ORDER),
        *(campaign._generate_mix_frame(index) for index in range(3)),
        campaign._generate_kernel_frame(),
    ]
    for repeat in range(1, 6):
        matrix = generate_transition_matrix_frames(repeat)
        frames.extend((matrix.initial, matrix.target))
    return {campaign._sha256(frame): frame for frame in frames}


def load_action_frame(contract: Mapping[str, Any], action_key: str) -> bytes:
    """Regenerate and rebind the exact immutable frame for one frozen action."""

    snapshot = execution.load_action_snapshot(contract, action_key)
    expected = snapshot.action["identity"]["frame"]
    frame = _frame_catalog().get(expected["sha256"])
    if frame is None or campaign._frame_record(frame) != expected:
        raise N5FixedExecutionToolError(
            "frozen N5 action frame is absent from or differs from the deterministic catalog"
        )
    return frame


def action_list(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = execution.validate_execution_contract(contract)
    return [
        {
            "order": entry["order"],
            "action_key": entry["action_key"],
            "action_identity_sha256": entry["action_identity_sha256"],
            "plan_class": entry["plan_class"],
            "session_id": entry["session_id"],
            "phase": entry["phase"],
            "frame_sha256": entry["frame_sha256"],
            "immediate_prior_action_identity_sha256": entry[
                "immediate_prior_action_identity_sha256"
            ],
            "measurement_slot_count": len(entry["measurement_slots"]),
        }
        for entry in root["actions"]
    ]


def _load_contract(path: Optional[Path]) -> Mapping[str, Any]:
    if path is None:
        return compile_default_execution_contract()
    return compile_materialized_execution_contract(
        _strict_json_file(path, label="N5 materialized manifest")
    )


def _required_materialized_manifest(path: Optional[Path]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if path is None:
        raise N5FixedExecutionToolError(
            "this command requires an external --manifest; the default compiler is offline only"
        )
    manifest = _strict_json_file(path, label="N5 materialized manifest")
    contract = _compile_production_execution_contract(manifest)
    return manifest, contract


def _publish_json(path: Path, value: Mapping[str, Any]) -> str:
    payload = execution.canonical_json_bytes(value)
    try:
        campaign._publish_new_bytes(path, payload)
    except campaign.N5CampaignError as error:
        raise N5FixedExecutionToolError(str(error)) from error
    stored = _strict_json_file(path, label=path.name)
    if stored != value or path.read_bytes() != payload:
        raise N5FixedExecutionToolError(f"stored {path.name} differs after publication")
    return hashlib.sha256(payload).hexdigest()


def _publish_bytes(path: Path, payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise N5FixedExecutionToolError(f"{path.name} payload must be bytes")
    try:
        campaign._publish_new_bytes(path, payload)
    except campaign.N5CampaignError as error:
        raise N5FixedExecutionToolError(str(error)) from error
    if path.read_bytes() != payload:
        raise N5FixedExecutionToolError(f"stored {path.name} bytes changed")
    return hashlib.sha256(payload).hexdigest()


def _publish_or_verify_same(path: Path, value: Mapping[str, Any]) -> str:
    """Idempotently complete one immutable file without permitting overwrite."""

    payload = execution.canonical_json_bytes(value)
    expected_sha = hashlib.sha256(payload).hexdigest()
    if path.exists():
        stored = _strict_json_file(path, label=path.name)
        if stored != value or path.read_bytes() != payload:
            raise N5FixedExecutionToolError(
                f"existing {path.name} differs; refusing identity drift"
            )
        return expected_sha
    return _publish_json(path, value)


def _build_protocol_pass_ready(receipt: Mapping[str, Any]) -> dict[str, Any]:
    claim = receipt.get("claim")
    protocol = receipt.get("protocol_evidence")
    audit = protocol.get("request_audit") if isinstance(protocol, Mapping) else None
    if (
        receipt.get("kind") != execution.PROTOCOL_RECEIPT_KIND
        or not isinstance(claim, Mapping)
        or not isinstance(protocol, Mapping)
        or not isinstance(audit, Mapping)
        or protocol.get("outcome") != "PASS"
        or protocol.get("protocol_verified") is not True
        or type(audit.get("post_attempt_count")) is not int
        or audit.get("post_attempt_count") != 1
        or type(audit.get("post_issued_count")) is not int
        or audit.get("post_issued_count") != 1
    ):
        raise N5FixedExecutionToolError(
            "only an exact one-POST PASS receipt can create protocol-ready state"
        )
    return execution._seal(
        {
            "schema_version": 1,
            "kind": PROTOCOL_PASS_READY_KIND,
            "state": "PROTOCOL_PASS_READY_FOR_MANUAL_FINALIZATION",
            "action_key": claim["action_key"],
            "action_identity_sha256": claim["action_identity_sha256"],
            "attempt_id": claim["attempt_id"],
            "execution_contract_canonical_sha256": claim[
                "execution_contract_canonical_sha256"
            ],
            "protocol_receipt_file_sha256": execution._sha256(receipt),
            "authorization_file_sha256": receipt["authorization_file_sha256"],
            "session_start_file_sha256": receipt["session_start_file_sha256"],
            "profile_file_sha256": receipt["profile_file_sha256"],
            "claim_file_sha256": receipt["claim_file_sha256"],
            "protocol_evidence_file_sha256": receipt[
                "protocol_evidence_file_sha256"
            ],
            "protocol_recorded_at": protocol["recorded_at"],
            "post_request_count": 1,
            "automatic_advance": False,
            "retry_allowed": False,
            "recovery_allowed": False,
        }
    )


def _build_protocol_terminal_ready(receipt: Mapping[str, Any]) -> dict[str, Any]:
    claim = receipt.get("claim")
    protocol = receipt.get("protocol_evidence")
    audit = protocol.get("request_audit") if isinstance(protocol, Mapping) else None
    if (
        receipt.get("kind") != execution.PROTOCOL_RECEIPT_KIND
        or not isinstance(claim, Mapping)
        or not isinstance(protocol, Mapping)
        or not isinstance(audit, Mapping)
        or protocol.get("outcome") != "UNKNOWN_DO_NOT_RETRY"
        or protocol.get("protocol_verified") is not False
        or not isinstance(protocol.get("error"), Mapping)
        or type(audit.get("post_attempt_count")) is not int
        or audit.get("post_attempt_count") not in {0, 1}
        or type(audit.get("post_issued_count")) is not int
        or audit.get("post_issued_count") not in {0, 1}
        or audit["post_issued_count"] > audit["post_attempt_count"]
    ):
        raise N5FixedExecutionToolError(
            "only a core-validated UNKNOWN receipt can create terminal-ready state"
        )
    return execution._seal(
        {
            "schema_version": 1,
            "kind": PROTOCOL_TERMINAL_READY_KIND,
            "state": "PROTOCOL_UNKNOWN_READY_FOR_TERMINAL_FINALIZATION",
            "action_key": claim["action_key"],
            "action_identity_sha256": claim["action_identity_sha256"],
            "attempt_id": claim["attempt_id"],
            "execution_contract_canonical_sha256": claim[
                "execution_contract_canonical_sha256"
            ],
            "protocol_receipt_file_sha256": execution._sha256(receipt),
            "authorization_file_sha256": receipt["authorization_file_sha256"],
            "session_start_file_sha256": receipt["session_start_file_sha256"],
            "profile_file_sha256": receipt["profile_file_sha256"],
            "claim_file_sha256": receipt["claim_file_sha256"],
            "protocol_evidence_file_sha256": receipt[
                "protocol_evidence_file_sha256"
            ],
            "protocol_recorded_at": protocol["recorded_at"],
            "post_request_count": audit["post_issued_count"],
            "manual_finalization_can_only_preserve_unknown": True,
            "automatic_advance": False,
            "retry_allowed": False,
            "recovery_allowed": False,
        }
    )


def _build_protocol_outcome_commit(
    receipt: Mapping[str, Any], ready: Mapping[str, Any]
) -> dict[str, Any]:
    """Commit one exact READY view before manual finalization can observe it.

    READY publication and its post-write verification are separate failure
    points.  A READY file without this independent commit is deliberately
    non-finalizable, even when every byte in that orphan READY happens to be
    valid.  This closes the write-succeeded/readback-raised ambiguity window.
    """

    protocol = receipt.get("protocol_evidence")
    outcome = protocol.get("outcome") if isinstance(protocol, Mapping) else None
    if outcome == "PASS":
        expected = _build_protocol_pass_ready(receipt)
        ready_filename = RESULT_PROTOCOL_PASS_READY_FILE
    elif outcome == "UNKNOWN_DO_NOT_RETRY":
        expected = _build_protocol_terminal_ready(receipt)
        ready_filename = RESULT_PROTOCOL_TERMINAL_READY_FILE
    else:
        raise N5FixedExecutionToolError(
            "protocol receipt has no commit-ready outcome"
        )
    if ready != expected:
        raise N5FixedExecutionToolError(
            "protocol READY view differs before outcome commit"
        )
    return execution._seal(
        {
            "schema_version": 1,
            "kind": PROTOCOL_OUTCOME_COMMIT_KIND,
            "state": "PROTOCOL_OUTCOME_COMMITTED_FOR_MANUAL_FINALIZATION",
            "action_key": ready["action_key"],
            "action_identity_sha256": ready["action_identity_sha256"],
            "attempt_id": ready["attempt_id"],
            "protocol_outcome": outcome,
            "protocol_receipt_file_sha256": execution._sha256(receipt),
            "protocol_ready_filename": ready_filename,
            "protocol_ready_file_sha256": execution._sha256(ready),
            "claim_file_sha256": ready["claim_file_sha256"],
            "post_request_count": ready["post_request_count"],
            "manual_finalization_explicitly_required": True,
            "automatic_advance": False,
            "retry_allowed": False,
            "recovery_allowed": False,
        }
    )


def _validate_protocol_ready(
    directory: Path, receipt: Mapping[str, Any]
) -> tuple[Mapping[str, Any], str]:
    protocol = receipt.get("protocol_evidence")
    outcome = protocol.get("outcome") if isinstance(protocol, Mapping) else None
    pass_path = directory / RESULT_PROTOCOL_PASS_READY_FILE
    terminal_path = directory / RESULT_PROTOCOL_TERMINAL_READY_FILE
    if pass_path.exists() and terminal_path.exists():
        raise N5FixedExecutionToolError(
            "both PASS-ready and terminal-ready commits exist; refusing ambiguity"
        )
    if outcome == "PASS":
        ready_path = pass_path
        expected = _build_protocol_pass_ready(receipt)
    elif outcome == "UNKNOWN_DO_NOT_RETRY":
        ready_path = terminal_path
        expected = _build_protocol_terminal_ready(receipt)
    else:
        raise N5FixedExecutionToolError("protocol receipt has no finalizable outcome")
    if not ready_path.is_file():
        raise N5FixedExecutionToolError(
            "protocol outcome-ready commit is absent; finalization is permanently forbidden"
        )
    ready = _strict_json_file(ready_path, label="N5 protocol outcome-ready commit")
    if ready != expected or ready_path.read_bytes() != execution.canonical_json_bytes(
        expected
    ):
        raise N5FixedExecutionToolError(
            "protocol outcome-ready commit differs from receipt/claim evidence"
        )
    ready_sha = execution._sha256(ready)
    outcome_commit_path = directory / RESULT_PROTOCOL_OUTCOME_COMMIT_FILE
    if not outcome_commit_path.is_file():
        raise N5FixedExecutionToolError(
            "protocol outcome transaction commit is absent; finalization is "
            "permanently forbidden"
        )
    outcome_commit = _strict_json_file(
        outcome_commit_path, label="N5 protocol outcome transaction commit"
    )
    expected_outcome_commit = _build_protocol_outcome_commit(receipt, ready)
    if (
        outcome_commit != expected_outcome_commit
        or outcome_commit_path.read_bytes()
        != execution.canonical_json_bytes(expected_outcome_commit)
    ):
        raise N5FixedExecutionToolError(
            "protocol outcome transaction commit differs from receipt/READY"
        )
    return ready, ready_sha


def _build_finalized_action_commit(
    item: Mapping[str, Any], *, protocol_outcome_ready_file_sha256: str
) -> dict[str, Any]:
    return execution._seal(
        {
            "schema_version": 1,
            "kind": FINALIZED_ACTION_COMMIT_KIND,
            "state": item["result"]["state"],
            "action_key": item["action_key"],
            "action_identity_sha256": item["action_identity_sha256"],
            "protocol_outcome_ready_file_sha256": protocol_outcome_ready_file_sha256,
            "finalized_action_item_file_sha256": execution._sha256(item),
            "manual_observation_file_sha256": item[
                "manual_observation_file_sha256"
            ],
            "finalization_file_sha256": item["finalization_file_sha256"],
            "result_file_sha256": item["result_file_sha256"],
            "automatic_advance": False,
            "retry_allowed": False,
            "recovery_allowed": False,
        }
    )


def _publish_finalized_action_files(
    destination: Path,
    item: Mapping[str, Any],
    *,
    protocol_outcome_ready_file_sha256: str,
) -> dict[str, str]:
    """Recoverably publish views, then bind them to READY with a final commit."""

    final_commit = _build_finalized_action_commit(
        item,
        protocol_outcome_ready_file_sha256=protocol_outcome_ready_file_sha256,
    )
    records = {
        RESULT_ACTION_ITEM_FILE: item,
        RESULT_MANUAL_FILE: item["manual_observation"],
        RESULT_FINALIZATION_FILE: item["finalization"],
        RESULT_P0_RESULT_FILE: item["result"],
        RESULT_FINALIZED_COMMIT_FILE: final_commit,
    }
    # Reject mismatched remnants before publishing the complete action item.
    # The separate commit record is deliberately published last.
    for filename, value in records.items():
        path = destination / filename
        if path.exists():
            _publish_or_verify_same(path, value)
    hashes = {
        RESULT_ACTION_ITEM_FILE: _publish_or_verify_same(
            destination / RESULT_ACTION_ITEM_FILE, item
        )
    }
    for filename in (
        RESULT_MANUAL_FILE,
        RESULT_FINALIZATION_FILE,
        RESULT_P0_RESULT_FILE,
    ):
        hashes[filename] = _publish_or_verify_same(
            destination / filename, records[filename]
        )
    hashes[RESULT_FINALIZED_COMMIT_FILE] = _publish_or_verify_same(
        destination / RESULT_FINALIZED_COMMIT_FILE, final_commit
    )
    return hashes


def _initialize_result_dir(path: Path) -> Path:
    destination = path.resolve()
    if not destination.parent.is_dir():
        raise N5FixedExecutionToolError("result directory parent does not exist")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise N5FixedExecutionToolError(
            "result directory already exists; refusing reuse or overwrite"
        ) from error
    except OSError as error:
        raise N5FixedExecutionToolError(f"cannot create result directory: {error}") from error
    return destination


def _claim_destination(snapshot: execution.ActionSnapshot, claim_root: Path) -> Path:
    declaration = snapshot.action["claim"]
    return (
        claim_root.resolve()
        / execution.CLAIM_REGISTRY_RELATIVE_PATH
        / str(declaration["filename"])
    )


def _terminal_unknown_summary(
    destination: Path,
    snapshot: execution.ActionSnapshot,
    *,
    stage: str,
    error: BaseException,
    receipt: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Best-effort durable incident record; this helper itself never raises."""

    try:
        receipt_sha = None if receipt is None else execution._sha256(receipt)
    except BaseException:
        receipt_sha = None
    incident = {
        "state": "UNKNOWN_DO_NOT_RETRY",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "stage": stage,
        "error_type": type(error).__name__,
        "error": str(error),
        "receipt_kind": None if receipt is None else receipt.get("kind"),
        "receipt_file_sha256": receipt_sha,
        "claim_permanent": True,
        "retry_allowed": False,
        "recovery_allowed": False,
        "automatic_advance": False,
    }
    persisted = False
    persistence_error: Optional[str] = None
    try:
        _publish_or_verify_same(
            destination / RESULT_CLAIM_COMMIT_UNKNOWN_FILE, incident
        )
        persisted = True
    except BaseException as incident_error:  # terminal state must still reach exit 3
        persistence_error = f"{type(incident_error).__name__}: {incident_error}"
    return {
        **incident,
        "result_dir": str(destination),
        "terminal_incident_persisted": persisted,
        "terminal_incident_persistence_error": persistence_error,
    }


def _reject_terminal_incident(directory: Path) -> None:
    marker = directory / RESULT_CLAIM_COMMIT_UNKNOWN_FILE
    if marker.exists():
        # The marker is monotonic.  Even malformed/tampered marker bytes cannot
        # relax the terminal state or permit a later PASS finalization.
        raise N5FixedExecutionToolError(
            "result directory is permanently UNKNOWN_DO_NOT_RETRY; "
            "finalization/bundling is forbidden"
        )


def _load_finalized_action_item(path: Path) -> Mapping[str, Any]:
    directory = path.resolve().parent
    _reject_terminal_incident(directory)
    receipt = _strict_json_file(
        directory / RESULT_RECEIPT_FILE, label="N5 protocol receipt"
    )
    ready, ready_sha = _validate_protocol_ready(directory, receipt)
    item = _strict_json_file(path, label="finalized N5 action item")
    if (
        item.get("action_key") != ready["action_key"]
        or item.get("action_identity_sha256")
        != ready["action_identity_sha256"]
        or item.get("authorization_file_sha256")
        != ready["authorization_file_sha256"]
        or item.get("profile_file_sha256") != ready["profile_file_sha256"]
        or item.get("claim_file_sha256") != ready["claim_file_sha256"]
        or item.get("protocol_evidence_file_sha256")
        != ready["protocol_evidence_file_sha256"]
    ):
        raise N5FixedExecutionToolError(
            "finalized action item is not bound to its protocol outcome-ready commit"
        )
    commit_path = directory / RESULT_FINALIZED_COMMIT_FILE
    commit = _strict_json_file(
        commit_path, label="N5 finalized action transaction commit"
    )
    expected_commit = _build_finalized_action_commit(
        item, protocol_outcome_ready_file_sha256=ready_sha
    )
    if commit != expected_commit or commit_path.read_bytes() != execution.canonical_json_bytes(
        expected_commit
    ):
        raise N5FixedExecutionToolError(
            "finalized action transaction commit differs from READY/action item"
        )
    return item


def _verify_permanent_claim(
    receipt: Mapping[str, Any], *, claim_root: Path
) -> Mapping[str, Any]:
    claim = receipt.get("claim")
    declared_sha = receipt.get("claim_file_sha256")
    if not isinstance(claim, Mapping) or not isinstance(declared_sha, str):
        raise N5FixedExecutionToolError("protocol receipt lacks a complete consumed claim")
    root = claim_root.resolve()
    registry = (root / execution.CLAIM_REGISTRY_RELATIVE_PATH).resolve()
    try:
        registry.relative_to(root)
    except ValueError as error:
        raise N5FixedExecutionToolError("claim registry escapes the external claim root") from error
    claim_path = (registry / str(claim.get("filename"))).resolve()
    try:
        claim_path.relative_to(registry)
    except ValueError as error:
        raise N5FixedExecutionToolError("claim filename escapes the claim registry") from error
    stored = _strict_json_file(claim_path, label="permanent N5 claim")
    if stored != claim or execution._sha256(stored) != declared_sha:
        raise N5FixedExecutionToolError(
            "disk claim differs from the immutable protocol receipt; do not finalize"
        )
    if claim_path.read_bytes() != execution.canonical_json_bytes(stored):
        raise N5FixedExecutionToolError("disk claim is not stored as exact canonical JSON")
    return stored


def _prior_action_item(
    contract: Mapping[str, Any], action_key: str, prior: Optional[Mapping[str, Any]]
) -> Optional[Mapping[str, Any]]:
    snapshot = execution.load_action_snapshot(contract, action_key)
    declaration = snapshot.action["identity"]["prior"]
    if declaration is None:
        return None
    if prior is None:
        raise N5FixedExecutionToolError("dependent action lacks its immediate prior item")
    if prior.get("kind") == execution.BUNDLE_KIND:
        execution.validate_finalized_bundle(contract, prior)
        matches = [
            item
            for item in prior["actions"]
            if item.get("action_identity_sha256")
            == declaration["action_identity_sha256"]
        ]
        if len(matches) != 1:
            raise N5FixedExecutionToolError(
                "prior bundle lacks the exact immediate predecessor action item"
            )
        return matches[0]
    if prior.get("action_identity_sha256") != declaration["action_identity_sha256"]:
        raise N5FixedExecutionToolError("prior item is not the immediate predecessor")
    return prior


def _run_fixed_action_core(
    manifest: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    action_key: str,
    limit_profile: Mapping[str, Any],
    profile_evaluated_at: str,
    authorization: Mapping[str, Any],
    session_start: Mapping[str, Any],
    runtime_gates: Mapping[str, Any],
    prior_bundle: Optional[Mapping[str, Any]],
    attempt_id: str,
    claimed_at: str,
    protocol_completed_at: str,
    claim_root: Path,
    result_dir: Path,
    base_url: str,
    transport: Optional[Any] = None,
    protocol_driver: Optional[Any] = None,
    preclaim_records: Optional[Mapping[str, Mapping[str, Any]]] = None,
    preclaim_artifacts: Optional[Mapping[str, bytes]] = None,
) -> dict[str, Any]:
    """Internal one-POST engine for a previously deep-validated contract."""

    try:
        execution.validate_execution_contract(contract)
    except N5ExecutionError as error:
        raise N5FixedExecutionToolError(
            f"N5 internal execution contract is invalid: {error}"
        ) from error
    normalized_url = frame_tool._normalize_base_url(base_url)
    snapshot = execution.load_action_snapshot(contract, action_key)
    frame = load_action_frame(contract, action_key)
    # All external records are validated again by the core before claim commit.
    execution.validate_session_start(session_start, snapshot=snapshot)
    execution.validate_authorization(authorization, contract=contract, snapshot=snapshot)
    execution.describe_fixed_action(
        contract,
        action_key,
        limit_profile=limit_profile,
        evaluated_at=profile_evaluated_at,
        prior_bundle=prior_bundle,
    )
    destination = _initialize_result_dir(result_dir)
    _publish_json(destination / RESULT_MANIFEST_FILE, manifest)
    _publish_json(destination / RESULT_CONTRACT_FILE, contract)
    _publish_json(destination / RESULT_PROFILE_FILE, limit_profile)
    _publish_json(destination / RESULT_SESSION_START_FILE, session_start)
    _publish_json(destination / RESULT_AUTHORIZATION_FILE, authorization)
    _publish_json(destination / RESULT_RUNTIME_GATES_FILE, runtime_gates)
    if prior_bundle is not None:
        _publish_json(destination / RESULT_PRIOR_FILE, prior_bundle)
    _publish_json(
        destination / RESULT_RUN_SELECTION_FILE,
        {
            "action_key": action_key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "attempt_id": attempt_id,
            "profile_evaluated_at": profile_evaluated_at,
            "claimed_at": claimed_at,
            "protocol_completed_at": protocol_completed_at,
            "base_url": normalized_url,
            "claim_root": str(claim_root.resolve()),
            "maximum_post_requests": 1,
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    )
    reserved = {
        RESULT_MANIFEST_FILE,
        RESULT_CONTRACT_FILE,
        RESULT_PROFILE_FILE,
        RESULT_SESSION_START_FILE,
        RESULT_AUTHORIZATION_FILE,
        RESULT_RUNTIME_GATES_FILE,
        RESULT_PRIOR_FILE,
        RESULT_RUN_SELECTION_FILE,
        RESULT_RECEIPT_FILE,
        RESULT_PROTOCOL_PASS_READY_FILE,
        RESULT_PROTOCOL_TERMINAL_READY_FILE,
        RESULT_PROTOCOL_OUTCOME_COMMIT_FILE,
        RESULT_MANUAL_FILE,
        RESULT_FINALIZATION_FILE,
        RESULT_P0_RESULT_FILE,
        RESULT_ACTION_ITEM_FILE,
        RESULT_FINALIZED_COMMIT_FILE,
        RESULT_CLAIM_COMMIT_UNKNOWN_FILE,
    }
    extras = {
        **({} if preclaim_records is None else dict(preclaim_records)),
        **({} if preclaim_artifacts is None else dict(preclaim_artifacts)),
    }
    if len(extras) != len(
        ({} if preclaim_records is None else preclaim_records)
    ) + len(({} if preclaim_artifacts is None else preclaim_artifacts)):
        raise N5FixedExecutionToolError("preclaim record/artifact filename is duplicated")
    for filename in extras:
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename in reserved
        ):
            raise N5FixedExecutionToolError(
                "preclaim record/artifact filename is unsafe or reserved"
            )
    for filename, record in (
        {} if preclaim_records is None else preclaim_records
    ).items():
        _publish_json(destination / filename, record)
    for filename, payload in (
        {} if preclaim_artifacts is None else preclaim_artifacts
    ).items():
        _publish_bytes(destination / filename, payload)
    if transport is None or protocol_driver is None:
        from host.extended_color import n5_rc2g_protocol

        if transport is None:
            transport = n5_rc2g_protocol.make_http_transport(normalized_url)
        if protocol_driver is None:
            protocol_driver = n5_rc2g_protocol.make_protocol_driver(
                contract,
                action_key,
                prior_bundle,
                base_url=normalized_url,
            )
    claim_destination = _claim_destination(snapshot, claim_root)
    try:
        receipt = execution.execute_fixed_action_once(
            contract,
            action_key,
            frame,
            limit_profile=limit_profile,
            profile_evaluated_at=profile_evaluated_at,
            authorization=authorization,
            session_start=session_start,
            runtime_gates=runtime_gates,
            prior_bundle=prior_bundle,
            attempt_id=attempt_id,
            claimed_at=claimed_at,
            protocol_completed_at=protocol_completed_at,
            claim_store=execution.AtomicWorkspaceClaimStore(claim_root),
            transport=transport,
            protocol_driver=protocol_driver,
        )
    except execution.N5PostClaimUnknown as error:
        receipt = error.receipt
        try:
            if receipt.get("kind") == execution.PROTOCOL_RECEIPT_KIND:
                _verify_permanent_claim(receipt, claim_root=claim_root)
                receipt_sha = _publish_json(
                    destination / RESULT_RECEIPT_FILE, receipt
                )
                terminal_ready = _build_protocol_terminal_ready(receipt)
                terminal_ready_sha = _publish_json(
                    destination / RESULT_PROTOCOL_TERMINAL_READY_FILE,
                    terminal_ready,
                )
                outcome_commit = _build_protocol_outcome_commit(
                    receipt, terminal_ready
                )
                outcome_commit_sha = _publish_json(
                    destination / RESULT_PROTOCOL_OUTCOME_COMMIT_FILE,
                    outcome_commit,
                )
            else:
                return _terminal_unknown_summary(
                    destination,
                    snapshot,
                    stage="claim-commit-state-unknown",
                    error=error,
                    receipt=receipt,
                )
        except BaseException as persistence_error:
            return _terminal_unknown_summary(
                destination,
                snapshot,
                stage="unknown-receipt-publication-failed",
                error=persistence_error,
                receipt=receipt,
            )
        return {
            "state": "UNKNOWN_DO_NOT_RETRY",
            "action_key": action_key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "protocol_receipt_file_sha256": receipt_sha,
            "protocol_outcome_ready_file_sha256": terminal_ready_sha,
            "protocol_outcome_commit_file_sha256": outcome_commit_sha,
            "result_dir": str(destination),
            "claim_permanent": True,
            "retry_allowed": False,
            "recovery_allowed": False,
        }
    except execution.N5ClaimConsumedError:
        raise
    except BaseException as error:
        if claim_destination.exists():
            return _terminal_unknown_summary(
                destination,
                snapshot,
                stage="post-claim-core-evidence-failed",
                error=error,
            )
        raise
    try:
        _verify_permanent_claim(receipt, claim_root=claim_root)
        receipt_sha = _publish_json(destination / RESULT_RECEIPT_FILE, receipt)
        ready = _build_protocol_pass_ready(receipt)
        ready_sha = _publish_json(
            destination / RESULT_PROTOCOL_PASS_READY_FILE, ready
        )
        outcome_commit = _build_protocol_outcome_commit(receipt, ready)
        outcome_commit_sha = _publish_json(
            destination / RESULT_PROTOCOL_OUTCOME_COMMIT_FILE,
            outcome_commit,
        )
    except BaseException as error:
        return _terminal_unknown_summary(
            destination,
            snapshot,
            stage="post-claim-receipt-or-claim-verification-failed",
            error=error,
            receipt=receipt,
        )
    return {
        "state": "PROTOCOL_PASS_AWAITING_MANUAL_FINALIZATION",
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "protocol_receipt_file_sha256": receipt_sha,
        "protocol_outcome_ready_file_sha256": ready_sha,
        "protocol_outcome_commit_file_sha256": outcome_commit_sha,
        "post_request_count": receipt["protocol_evidence"]["request_audit"][
            "post_issued_count"
        ],
        "result_dir": str(destination),
        "claim_permanent": True,
        "automatic_advance": False,
        "retry_allowed": False,
        "recovery_allowed": False,
    }


def run_fixed_action(
    manifest: Mapping[str, Any],
    *,
    action_key: str,
    limit_profile: Mapping[str, Any],
    profile_evaluated_at: str,
    authorization: Mapping[str, Any],
    session_start: Mapping[str, Any],
    runtime_gates: Mapping[str, Any],
    prior_bundle: Optional[Mapping[str, Any]],
    attempt_id: str,
    claimed_at: str,
    protocol_completed_at: str,
    claim_root: Path,
    result_dir: Path,
    base_url: str,
    transport: Optional[Any] = None,
    protocol_driver: Optional[Any] = None,
) -> dict[str, Any]:
    """Hard-block the superseded self-sealed live boundary before any claim/I/O."""

    del (
        manifest,
        action_key,
        limit_profile,
        profile_evaluated_at,
        authorization,
        session_start,
        runtime_gates,
        prior_bundle,
        attempt_id,
        claimed_at,
        protocol_completed_at,
        claim_root,
        result_dir,
        base_url,
        transport,
        protocol_driver,
    )
    raise N5FixedExecutionToolError(
        "legacy N5 live execution is disabled before claim/network; use "
        "mf1750_n5_physical_execution with an authenticated physical plan and "
        "deep production profile"
    )


def _finalize_fixed_action_core(
    *,
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    result_dir: Path,
    manual_observation_payload: Mapping[str, Any],
    completed_at: str,
    claim_root: Path,
) -> dict[str, Any]:
    """Finalize one receipt against an already deep-validated contract."""

    destination = result_dir.resolve()
    _reject_terminal_incident(destination)
    try:
        execution.validate_execution_contract(contract)
    except N5ExecutionError as error:
        raise N5FixedExecutionToolError(
            f"N5 internal finalization contract is invalid: {error}"
        ) from error
    stored_manifest = _strict_json_file(
        destination / RESULT_MANIFEST_FILE, label="stored N5 manifest"
    )
    stored_contract = _strict_json_file(
        destination / RESULT_CONTRACT_FILE, label="stored N5 execution contract"
    )
    if stored_manifest != manifest or stored_contract != contract:
        raise N5FixedExecutionToolError("result directory is bound to another manifest")
    receipt = _strict_json_file(
        destination / RESULT_RECEIPT_FILE, label="N5 protocol receipt"
    )
    _ready, ready_sha = _validate_protocol_ready(destination, receipt)
    _verify_permanent_claim(receipt, claim_root=claim_root)
    if "integrity" in manual_observation_payload:
        raise N5FixedExecutionToolError(
            "external manual observation must be an unsigned payload; finalize seals it"
        )
    claim = receipt["claim"]
    manual = execution.seal_manual_observation(
        manual_observation_payload,
        contract=contract,
        action_key=str(claim["action_key"]),
        attempt_id=str(claim["attempt_id"]),
        protocol_evidence_file_sha256=str(receipt["protocol_evidence_file_sha256"]),
    )
    item = execution.finalize_protocol_receipt(
        contract, receipt, manual, completed_at=completed_at
    )
    prior = None
    prior_path = destination / RESULT_PRIOR_FILE
    if prior_path.exists():
        prior = _strict_json_file(prior_path, label="stored immediate prior")
    prior_item = _prior_action_item(contract, str(claim["action_key"]), prior)
    from host.extended_color import n5_rc2g_protocol

    n5_rc2g_protocol.validate_strict_action_item(
        contract, item, prior_item=prior_item
    )
    published = _publish_finalized_action_files(
        destination,
        item,
        protocol_outcome_ready_file_sha256=ready_sha,
    )
    return {
        "state": item["result"]["state"],
        "action_key": claim["action_key"],
        "action_identity_sha256": claim["action_identity_sha256"],
        "manual_observation_file_sha256": published[RESULT_MANUAL_FILE],
        "finalization_file_sha256": published[RESULT_FINALIZATION_FILE],
        "result_file_sha256": published[RESULT_P0_RESULT_FILE],
        "action_item_file_sha256": published[RESULT_ACTION_ITEM_FILE],
        "finalized_action_commit_file_sha256": published[
            RESULT_FINALIZED_COMMIT_FILE
        ],
        "result_dir": str(destination),
        "transaction_commit_file": RESULT_FINALIZED_COMMIT_FILE,
        "idempotent_completion": True,
        "automatic_advance": False,
        "retry_allowed": False,
        "recovery_allowed": False,
    }


def finalize_fixed_action(
    *,
    manifest: Mapping[str, Any],
    result_dir: Path,
    manual_observation_payload: Mapping[str, Any],
    completed_at: str,
    claim_root: Path,
) -> dict[str, Any]:
    """Finalize legacy receipts without reopening the disabled live entry."""

    return _finalize_fixed_action_core(
        manifest=manifest,
        contract=_compile_production_execution_contract(manifest),
        result_dir=result_dir,
        manual_observation_payload=manual_observation_payload,
        completed_at=completed_at,
        claim_root=claim_root,
    )


def build_session_bundle_file(
    manifest: Mapping[str, Any],
    *,
    action_items: Sequence[Mapping[str, Any]],
    session_starts: Sequence[Mapping[str, Any]],
    finalized_at: str,
    j2_cut_session_ids: Sequence[str],
    output: Path,
) -> dict[str, Any]:
    """Build and exclusively publish one deeply validated dependency-closed bundle."""

    contract = _compile_production_execution_contract(manifest)
    bundle = execution.build_finalized_bundle(
        contract,
        action_items,
        session_starts,
        finalized_at=finalized_at,
        j2_cut_session_ids=j2_cut_session_ids,
    )
    from host.extended_color import n5_rc2g_protocol

    summary = n5_rc2g_protocol.validate_strict_finalized_bundle(contract, bundle)
    file_sha = _publish_json(output, bundle)
    stored = _strict_json_file(output, label="stored N5 finalized session bundle")
    stored_summary = n5_rc2g_protocol.validate_strict_finalized_bundle(
        contract, stored
    )
    if stored_summary != summary:
        raise N5FixedExecutionToolError("stored N5 bundle validation summary changed")
    return {
        "bundle_canonical_sha256": bundle["integrity"]["canonical_sha256"],
        "bundle_file_sha256": file_sha,
        "action_count": len(bundle["actions"]),
        "session_count": len(bundle["sessions"]),
        "output": str(output.resolve()),
        "deep_validation_passed": True,
    }


def validate_session_bundle_file(
    manifest: Mapping[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    contract = _compile_production_execution_contract(manifest)
    from host.extended_color import n5_rc2g_protocol

    summary = n5_rc2g_protocol.validate_strict_finalized_bundle(contract, bundle)
    return {
        "valid": True,
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "bundle_canonical_sha256": bundle["integrity"]["canonical_sha256"],
        "bundle_file_sha256": execution._sha256(bundle),
        "action_count": len(bundle["actions"]),
        "session_count": len(bundle["sessions"]),
        "strict_protocol_summary": summary,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="optional previously compiled/materialized N5 manifest JSON",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list frozen actions; no side effects")
    describe = subparsers.add_parser(
        "describe", help="describe one action; no claim or authorization"
    )
    describe.add_argument("--action", required=True)
    describe.add_argument("--limit-profile", type=Path)
    describe.add_argument("--evaluated-at")
    describe.add_argument("--prior-bundle", type=Path)
    run = subparsers.add_parser(
        "run", help="consume one claim and execute exactly one strict RC2G refresh"
    )
    run.add_argument("--action", required=True)
    run.add_argument("--limit-profile", type=Path, required=True)
    run.add_argument("--profile-evaluated-at", required=True)
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--session-start", type=Path, required=True)
    run.add_argument("--runtime-gates", type=Path, required=True)
    run.add_argument("--prior-bundle", type=Path)
    run.add_argument("--attempt-id", required=True)
    run.add_argument("--claimed-at", required=True)
    run.add_argument("--protocol-completed-at", required=True)
    run.add_argument("--result-dir", type=Path, required=True)
    run.add_argument("--url", required=True)
    finalize = subparsers.add_parser(
        "finalize", help="seal manual measurements for one completed protocol receipt"
    )
    finalize.add_argument("--result-dir", type=Path, required=True)
    finalize.add_argument("--manual-observation", type=Path, required=True)
    finalize.add_argument("--completed-at", required=True)
    bundle = subparsers.add_parser(
        "build-session-bundle",
        help="seal a dependency-closed action/session bundle without device I/O",
    )
    bundle.add_argument("--action-item", type=Path, action="append", required=True)
    bundle.add_argument("--session-start", type=Path, action="append", required=True)
    bundle.add_argument("--finalized-at", required=True)
    bundle.add_argument("--j2-cut-session-id", action="append", default=[])
    bundle.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser(
        "validate", help="deeply replay one finalized bundle without device I/O"
    )
    validate.add_argument("--bundle", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        if args.command in {"list", "describe"}:
            contract = _load_contract(args.manifest)
            if args.command == "list":
                output = {
                    "execution_contract_canonical_sha256": contract["integrity"][
                        "canonical_sha256"
                    ],
                    "execution_contract_file_sha256": execution.execution_contract_file_sha256(
                        contract
                    ),
                    "actions": action_list(contract),
                    "classification": {
                        "mode": "describe-only",
                        "authorization_created": False,
                        "claim_created": False,
                        "network_io_performed": False,
                        "device_io_performed": False,
                    },
                }
            else:
                profile = (
                    None
                    if args.limit_profile is None
                    else _strict_json_file(
                        args.limit_profile, label="reviewed limit profile"
                    )
                )
                prior = (
                    None
                    if args.prior_bundle is None
                    else _strict_json_file(
                        args.prior_bundle, label="prior finalized bundle"
                    )
                )
                output = execution.describe_fixed_action(
                    contract,
                    args.action,
                    limit_profile=profile,
                    evaluated_at=args.evaluated_at,
                    prior_bundle=prior,
                )
        else:
            manifest, _contract = _required_materialized_manifest(args.manifest)
            if args.command == "run":
                prior = (
                    None
                    if args.prior_bundle is None
                    else _strict_json_file(
                        args.prior_bundle, label="immediate prior finalized evidence"
                    )
                )
                output = run_fixed_action(
                    manifest,
                    action_key=args.action,
                    limit_profile=_strict_json_file(
                        args.limit_profile, label="reviewed limit profile"
                    ),
                    profile_evaluated_at=args.profile_evaluated_at,
                    authorization=_strict_json_file(
                        args.authorization, label="external one-action authorization"
                    ),
                    session_start=_strict_json_file(
                        args.session_start, label="manual session-start observation"
                    ),
                    runtime_gates=_strict_json_file(
                        args.runtime_gates, label="manual runtime gates"
                    ),
                    prior_bundle=prior,
                    attempt_id=args.attempt_id,
                    claimed_at=args.claimed_at,
                    protocol_completed_at=args.protocol_completed_at,
                    claim_root=PRODUCTION_CLAIM_ROOT,
                    result_dir=args.result_dir,
                    base_url=args.url,
                )
            elif args.command == "finalize":
                output = finalize_fixed_action(
                    manifest=manifest,
                    result_dir=args.result_dir,
                    manual_observation_payload=_strict_json_file(
                        args.manual_observation,
                        label="external manual measurement observation",
                    ),
                    completed_at=args.completed_at,
                    claim_root=PRODUCTION_CLAIM_ROOT,
                )
            elif args.command == "build-session-bundle":
                output = build_session_bundle_file(
                    manifest,
                    action_items=[
                        _load_finalized_action_item(path)
                        for path in args.action_item
                    ],
                    session_starts=[
                        _strict_json_file(path, label="N5 session-start observation")
                        for path in args.session_start
                    ],
                    finalized_at=args.finalized_at,
                    j2_cut_session_ids=args.j2_cut_session_id,
                    output=args.output,
                )
            else:
                bundle = _strict_json_file(
                    args.bundle, label="finalized N5 execution bundle"
                )
                output = validate_session_bundle_file(manifest, bundle)
    except execution.N5ClaimConsumedError as error:
        print(
            json.dumps(
                {
                    "state": "CLAIM_ALREADY_CONSUMED_DO_NOT_RETRY",
                    "error": str(error),
                    "retry_allowed": False,
                    "recovery_allowed": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
        )
        return 3
    except (
        N5FixedExecutionToolError,
        N5ExecutionError,
        campaign.N5CampaignError,
        frame_tool.FrameToolError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    if output.get("state") == "UNKNOWN_DO_NOT_RETRY":
        if output.get("terminal_incident_persisted") is False:
            print(
                "TERMINAL UNKNOWN_DO_NOT_RETRY: claim is permanent and the incident "
                "record could not be persisted; do not rerun or recover",
                file=sys.stderr,
            )
        return 3
    if output.get("state") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_DEFAULT_EXECUTION_CONTRACT_CANONICAL_SHA256",
    "EXPECTED_DEFAULT_EXECUTION_CONTRACT_FILE_SHA256",
    "N5FixedExecutionToolError",
    "action_list",
    "build_session_bundle_file",
    "compile_default_execution_contract",
    "compile_materialized_execution_contract",
    "finalize_fixed_action",
    "load_action_frame",
    "main",
    "parse_args",
    "run_fixed_action",
    "validate_session_bundle_file",
]
