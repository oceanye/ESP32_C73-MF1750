#!/usr/bin/env python3
"""One-shot Phase-A live ``/version`` facade for the frozen V10 contract.

This module deliberately separates the reviewed network implementation from
the older offline Phase-A challenge.  A new sealed live-execution envelope
binds the complete offline authority, this module's exact source bytes, the V2
raw/exact validator, the one literal IPv4 origin, the exact request bytes, and
the three O_EXCL evidence paths.  The offline authorization phrase is therefore
never sufficient to enter this live runner.

Importing, preparing, or validating this module performs no socket operation.
The production CLI has one live command and exposes no host, port, timeout,
transport, requester, proxy, redirect, retry, or Phase-B override.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import socket
import stat
import time
from typing import Any, Final, Mapping, Protocol, Sequence

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract


SCHEMA_VERSION: Final = 1
LIVE_ENVELOPE_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-execution-envelope-v1"
)
LIVE_ENVELOPE_CLASSIFICATION: Final = (
    "SEALED_PHASE_A_LIVE_EXECUTION_ENVELOPE_REQUIRES_SEPARATE_EXACT_AUTHORIZATION"
)
SYNTHETIC_ENVELOPE_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-synthetic-test-envelope-v1"
)
SYNTHETIC_ENVELOPE_CLASSIFICATION: Final = (
    "SYNTHETIC_TEST_ONLY_ENVELOPE_NEVER_LIVE_OR_PHASE_B_ELIGIBLE"
)
LIVE_REGISTRY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-attempt-registry-v1"
)
LIVE_RECEIPT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-terminal-receipt-v1"
)
SYNTHETIC_REGISTRY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-synthetic-registry-v1"
)
SYNTHETIC_RECEIPT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-live-synthetic-receipt-v1"
)
LIVE_AUTHORIZATION_PREFIX: Final = (
    "AUTHORIZE_STAGE_B_PHASE_A_LIVE_ONE_VERSION_GET_RUNNER_BOUND"
)
SYNTHETIC_AUTHORIZATION_PREFIX: Final = (
    "SYNTHETIC_TEST_ONLY_STAGE_B_PHASE_A_ONE_VERSION_GET"
)

LITERAL_IPV4: Final = "192.168.1.7"
PORT: Final = 80
VERSION_PATH: Final = "/api/ec5/h3-matched-control-v2/version"
ABSOLUTE_URL: Final = f"http://{LITERAL_IPV4}{VERSION_PATH}"
CONNECT_TIMEOUT_MS: Final = 3_000
READ_TIMEOUT_MS: Final = 5_000
TOTAL_TIMEOUT_MS: Final = 8_000
MAX_STATUS_HEADER_BYTES: Final = 16_384
MAX_VERSION_ENTITY_BYTES: Final = 65_536
MAX_TERMINAL_RECEIPT_BYTES: Final = facade.MAX_JSON_BYTES
MAX_ERROR_TEXT_BYTES: Final = 4_096
MAX_HOST_NOW_SKEW_SECONDS: Final = 30
RECV_CHUNK_BYTES: Final = 4_096
MAX_BEYOND_CONTENT_LENGTH_EVIDENCE_BYTES: Final = RECV_CHUNK_BYTES
MAX_BOUNDED_RESPONSE_PREFIX_BYTES: Final = (
    MAX_STATUS_HEADER_BYTES + MAX_VERSION_ENTITY_BYTES + 1
)
REQUEST_WIRE_BYTES: Final = (
    f"GET {VERSION_PATH} HTTP/1.1\r\n"
    f"Host: {LITERAL_IPV4}\r\n"
    "Accept: application/json\r\n"
    "Accept-Encoding: identity\r\n"
    "Connection: close\r\n"
    "\r\n"
).encode("ascii")
HEADER_NAME = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
STATUS_LINE = re.compile(rb"^HTTP/1\.1 ([0-9]{3})(?: ([\x20-\x7e]*))?$")
ASCII_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PhaseALiveError(ValueError):
    """The live envelope, authorization, evidence, or one-shot policy differs."""


class PhaseALiveTransportError(PhaseALiveError):
    """A terminal one-shot transport or HTTP framing failure."""


@dataclass(frozen=True)
class _FileSnapshot:
    path: Path
    device: int
    inode: int
    size: int
    sha256: str
    label: str

    def assert_unchanged(self) -> None:
        current = _snapshot(self.path, label=self.label)
        if (
            (current.device, current.inode) != (self.device, self.inode)
            or current.size != self.size
            or current.sha256 != self.sha256
        ):
            raise PhaseALiveError(f"{self.label} identity or bytes changed")


@dataclass(frozen=True)
class _LiveBundle:
    envelope_path: Path
    envelope_payload: bytes
    envelope: Mapping[str, Any]
    envelope_binding: Mapping[str, Any]
    authority_path: Path
    authority_payload: bytes
    authority: Mapping[str, Any]
    authority_binding: Mapping[str, Any]
    v10_context: Any
    snapshots: tuple[_FileSnapshot, ...]
    synthetic_test_only: bool


@dataclass(frozen=True)
class _ParsedHTTPEnvelope:
    status: int
    headers: tuple[tuple[str, str], ...]
    content_length: int


@dataclass(frozen=True)
class _RawHTTPResponse:
    status_and_headers: bytes
    entity_body: bytes
    parsed: _ParsedHTTPEnvelope


class _UTCClock(Protocol):
    def wall_now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class _SystemUTCClock:
    def wall_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class _ScriptedUTCClock:
    """Exact private test clock; it is never accepted by the public executor."""

    def __init__(self, wall_values: Sequence[datetime]) -> None:
        if not wall_values or any(
            type(item) is not datetime
            or item.tzinfo is None
            or item.utcoffset() is None
            for item in wall_values
        ):
            raise PhaseALiveError("synthetic clock values must be zoned datetimes")
        self._values = tuple(item.astimezone(timezone.utc) for item in wall_values)
        self._ordinal = 0
        self._monotonic = 0.0

    def wall_now(self) -> datetime:
        index = min(self._ordinal, len(self._values) - 1)
        self._ordinal += 1
        return self._values[index]

    def monotonic(self) -> float:
        self._monotonic += 0.001
        return self._monotonic


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot(path: Path, *, label: str) -> _FileSnapshot:
    target = phase_a._safe_absolute(path, label=label)  # noqa: SLF001
    try:
        with target.open("rb", buffering=0) as handle:
            held_before = os.fstat(handle.fileno())
            path_before = target.lstat()
            payload = handle.read()
            held_after = os.fstat(handle.fileno())
            path_after = target.lstat()
    except OSError as error:
        raise PhaseALiveError(f"could not snapshot {label}: {error}") from error
    infos = (held_before, held_after, path_before, path_after)
    identity = (held_before.st_dev, held_before.st_ino)
    if any(
        stat.S_ISLNK(info.st_mode)
        or phase_a._is_reparse(info)  # noqa: SLF001
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or (info.st_dev, info.st_ino) != identity
        for info in infos
    ) or any(info.st_size != len(payload) for info in infos):
        raise PhaseALiveError(f"{label} is not one unlinked regular file")
    return _FileSnapshot(
        path=target,
        device=held_after.st_dev,
        inode=held_after.st_ino,
        size=held_after.st_size,
        sha256=contract.sha256(payload),
        label=label,
    )


def _directory_entry_exists(path: Path) -> bool:
    """Use lstat so broken links/reparse entries are not treated as absent."""

    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise PhaseALiveError(
            f"could not inspect evidence path entry: {error}"
        ) from error
    return True


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return phase_a._seal(unsigned)  # noqa: SLF001


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    try:
        return phase_a._validate_seal(root, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseALiveError(str(error)) from error


def _source_binding(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return phase_a._source_binding(path, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseALiveError(str(error)) from error


def _read_strict_json(
    path: Path, *, label: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    try:
        return facade._read_json(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseALiveError(str(error)) from error


def _require_canonical_artifact_bytes(
    payload: bytes, root: Mapping[str, Any], *, label: str
) -> None:
    if payload != contract.canonical_json_bytes(root) + b"\n":
        raise PhaseALiveError(f"{label} is not exact canonical JSON plus one LF")


def _authority_bundle(
    authority_file: Path, *, require_attempt_paths_absent: bool
) -> tuple[Path, bytes, Mapping[str, Any], dict[str, Any]]:
    authority_path, payload, authority = _read_strict_json(
        authority_file, label="offline Phase-A authority"
    )
    try:
        phase_a.validate_phase_a_authority(
            authority,
            require_attempt_paths_absent=require_attempt_paths_absent,
        )
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseALiveError(f"offline Phase-A authority differs: {error}") from error
    binding = {
        "path": str(authority_path),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": authority["integrity"]["canonical_sha256"],
        "authority_id": authority["authority_id"],
    }
    return authority_path, payload, authority, binding


def _gate_time(authority: Mapping[str, Any], *, now: datetime, label: str) -> str:
    gate = authority["fresh_phase_a_onsite_gate"]
    before = phase_a._zoned_datetime(  # noqa: SLF001
        str(gate["not_before_utc"]), label="Phase-A gate not-before"
    ).astimezone(timezone.utc)
    after = phase_a._zoned_datetime(  # noqa: SLF001
        str(gate["not_after_utc"]), label="Phase-A gate not-after"
    ).astimezone(timezone.utc)
    observed = now.astimezone(timezone.utc)
    if observed < before or observed >= after:
        raise PhaseALiveError(f"{label} is outside not_before <= now < not_after")
    return _utc_text(observed)


def _parse_zoned(value: str, *, label: str) -> datetime:
    try:
        return phase_a._zoned_datetime(value, label=label).astimezone(  # noqa: SLF001
            timezone.utc
        )
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseALiveError(str(error)) from error


def _parse_canonical_utc_text(value: Any, *, label: str) -> datetime:
    if type(value) is not str:
        raise PhaseALiveError(f"{label} type differs")
    parsed = _parse_zoned(value, label=label)
    if value != _utc_text(parsed):
        raise PhaseALiveError(f"{label} is not the exact generated UTC Z form")
    return parsed


def _transport_policy() -> dict[str, Any]:
    return {
        "application_transport_attempts_maximum": 1,
        "literal_ipv4": LITERAL_IPV4,
        "port": PORT,
        "socket_family": "AF_INET",
        "socket_type": "SOCK_STREAM",
        "socket_protocol": "IPPROTO_TCP",
        "connect_timeout_ms": CONNECT_TIMEOUT_MS,
        "read_timeout_ms": READ_TIMEOUT_MS,
        "total_timeout_ms": TOTAL_TIMEOUT_MS,
        "maximum_status_and_header_bytes": MAX_STATUS_HEADER_BYTES,
        "maximum_response_entity_bytes": MAX_VERSION_ENTITY_BYTES,
        "generic_json_decoder_limit_is_narrowed_for_version": True,
        "strict_terminal_receipt_loader_maximum_bytes": (MAX_TERMINAL_RECEIPT_BYTES),
        "dns_or_getaddrinfo": False,
        "proxy_or_environment_routing": False,
        "redirect": False,
        "fallback_or_scan": False,
        "application_retry": False,
        "connection_reuse_or_keepalive": False,
        "cookies_or_authorization_headers": False,
        "transfer_encoding": False,
        "content_encoding": False,
        "single_content_length_required": True,
        "connection_close_required": True,
        "post_content_length_eof_required_before_success": True,
        "delayed_close_or_close_timeout_is_fail_closed": True,
        "request_wire_bytes": len(REQUEST_WIRE_BYTES),
        "request_wire_sha256": contract.sha256(REQUEST_WIRE_BYTES),
        "request_wire_base64": base64.b64encode(REQUEST_WIRE_BYTES).decode("ascii"),
        "method": "GET",
        "path": VERSION_PATH,
        "absolute_url": ABSOLUTE_URL,
        "request_body_bytes": 0,
        "response_entity_bytes_are_not_raw_wire_bytes": True,
        "kernel_tcp_retransmission_may_occur_but_is_not_application_retry": True,
    }


def materialize_live_execution_envelope(
    *,
    phase_a_authority_file: Path,
    live_envelope_file: Path,
    built_at: str,
    _synthetic_test_only: bool = False,
    _synthetic_registry_file: Path | None = None,
    _synthetic_terminal_receipt_file: Path | None = None,
    _require_attempt_paths_absent: bool = True,
) -> dict[str, Any]:
    """Build a sealed runner-bound envelope without deriving a user token."""

    authority_path, authority_payload, authority, authority_binding = _authority_bundle(
        phase_a_authority_file,
        require_attempt_paths_absent=_require_attempt_paths_absent,
    )
    blueprint_path, blueprint_payload, blueprint = _read_strict_json(
        Path(str(authority["blueprint_binding"]["path"])),
        label="frozen Stage-B V2 blueprint",
    )
    try:
        blueprint_summary = facade.validate_blueprint(
            blueprint, require_live_output_absent=True
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseALiveError(f"frozen V2 blueprint differs: {error}") from error
    expected_blueprint = authority["blueprint_binding"]
    if (
        str(blueprint_path) != expected_blueprint["path"]
        or len(blueprint_payload) != expected_blueprint["bytes"]
        or contract.sha256(blueprint_payload) != expected_blueprint["sha256"]
        or blueprint_summary["canonical_sha256"]
        != expected_blueprint["canonical_sha256"]
        or blueprint_summary["blueprint_id"] != expected_blueprint["blueprint_id"]
    ):
        raise PhaseALiveError("frozen V2 blueprint whole-file binding differs")
    built = _parse_zoned(built_at, label="live envelope built-at")
    built_utc = _gate_time(authority, now=built, label="live envelope built-at")
    envelope_path = phase_a._safe_absolute(  # noqa: SLF001
        live_envelope_file, label="Phase-A live execution envelope"
    )
    attempt = authority["attempt"]
    if _synthetic_test_only:
        if _synthetic_registry_file is None or _synthetic_terminal_receipt_file is None:
            raise PhaseALiveError(
                "synthetic envelope requires two exact test-only paths"
            )
        registry_path = phase_a._safe_absolute(  # noqa: SLF001
            _synthetic_registry_file, label="synthetic Phase-A registry"
        )
        receipt_path = phase_a._safe_absolute(  # noqa: SLF001
            _synthetic_terminal_receipt_file, label="synthetic Phase-A receipt"
        )
        if not registry_path.name.endswith(
            ".synthetic-test-only.json"
        ) or not receipt_path.name.endswith(".synthetic-test-only.json"):
            raise PhaseALiveError("synthetic evidence paths need the test-only suffix")
    else:
        if (
            _synthetic_registry_file is not None
            or _synthetic_terminal_receipt_file is not None
        ):
            raise PhaseALiveError(
                "live envelope cannot override authority attempt paths"
            )
        registry_path = phase_a._safe_absolute(  # noqa: SLF001
            Path(str(attempt["registry_file"])), label="Phase-A live registry"
        )
        receipt_path = phase_a._safe_absolute(  # noqa: SLF001
            Path(str(attempt["terminal_receipt_file"])),
            label="Phase-A live terminal receipt",
        )
    original_final = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(attempt["original_plan_final_output"])),
        label="original plan final diagnostic output",
    )
    finalization_temp_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(f"{receipt_path}.finalize-o-excl.tmp"),
        label="Phase-A live finalization temp",
    )
    artifact_paths = {
        authority_path,
        envelope_path,
        registry_path,
        receipt_path,
        finalization_temp_path,
    }
    if len(artifact_paths) != 5:
        raise PhaseALiveError(
            "authority/envelope/registry/receipt/finalization paths must differ"
        )
    if finalization_temp_path.parent != receipt_path.parent:
        raise PhaseALiveError(
            "finalization temp and terminal output must share one directory"
        )
    if original_final in artifact_paths:
        raise PhaseALiveError(
            "Phase-A live artifacts must not occupy plan final output"
        )
    if _require_attempt_paths_absent:
        for label, path in (
            ("Phase-A live registry", registry_path),
            ("Phase-A live terminal receipt", receipt_path),
            ("Phase-A live finalization temp", finalization_temp_path),
        ):
            if _directory_entry_exists(path):
                raise PhaseALiveError(f"{label} already exists; attempt consumed")

    source_bindings = {
        "offline_phase_a_authority_module": _source_binding(
            Path(phase_a.__file__), label="offline Phase-A authority module"
        ),
        "v2_exact_surface_facade_module": _source_binding(
            Path(facade.__file__), label="V2 exact-surface facade"
        ),
        "phase_a_live_runner_module": _source_binding(
            Path(__file__), label="Phase-A live runner module"
        ),
        "matched_control_contract_module": _source_binding(
            Path(contract.__file__), label="matched-control canonical/seal module"
        ),
        "frozen_physical_validator_module": _source_binding(
            Path(str(blueprint["frozen_v10_validator_binding"]["path"])),
            label="frozen V10 physical validator module",
        ),
        "diagnostic_recovery_contract_module": _source_binding(
            Path(facade.recovery.__file__), label="diagnostic recovery contract module"
        ),
        "stage_a_receipt_contract_module": _source_binding(
            Path(facade.stage_a.__file__), label="Stage-A receipt contract module"
        ),
    }
    if not _strict_json_equal(
        source_bindings["offline_phase_a_authority_module"],
        authority["source_bindings"]["phase_a_authority_module"],
    ):
        raise PhaseALiveError("offline authority module source binding differs")
    if not _strict_json_equal(
        source_bindings["v2_exact_surface_facade_module"],
        authority["source_bindings"]["v2_exact_surface_facade_module"],
    ):
        raise PhaseALiveError("V2 exact-surface source binding differs")

    policy = _transport_policy()
    attempt_preimage = {
        "domain": (
            "MF1750_PHASE_A_LIVE_SYNTHETIC_TEST_ATTEMPT_V1"
            if _synthetic_test_only
            else "MF1750_PHASE_A_LIVE_ONE_VERSION_ATTEMPT_V1"
        ),
        "offline_authority_file_sha256": contract.sha256(authority_payload),
        "offline_authority_id": authority["authority_id"],
        "offline_attempt_id": attempt["attempt_id"],
        "runner_source_sha256": source_bindings["phase_a_live_runner_module"]["sha256"],
        "v2_validator_source_sha256": source_bindings["v2_exact_surface_facade_module"][
            "sha256"
        ],
        "all_bound_on_disk_python_source_files_sha256": contract.sha256(
            source_bindings
        ),
        "does_not_prove_loaded_bytecode_sitecustomize_or_process_integrity": True,
        "request_wire_sha256": policy["request_wire_sha256"],
        "registry_file": str(registry_path),
        "terminal_receipt_file": str(receipt_path),
        "finalization_temp_file": str(finalization_temp_path),
        "built_at_utc": built_utc,
    }
    live_attempt_id = contract.sha256(attempt_preimage)
    challenge = contract.sha256(
        {
            "domain": "MF1750_PHASE_A_RUNNER_BOUND_USER_CHALLENGE_V1",
            "live_attempt_id": live_attempt_id,
            "offline_authority_file_sha256": contract.sha256(authority_payload),
            "onsite_gate_canonical_sha256": authority["fresh_phase_a_onsite_gate"][
                "gate_canonical_sha256"
            ],
            "runner_source_sha256": source_bindings["phase_a_live_runner_module"][
                "sha256"
            ],
        }
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            SYNTHETIC_ENVELOPE_KIND if _synthetic_test_only else LIVE_ENVELOPE_KIND
        ),
        "classification": (
            SYNTHETIC_ENVELOPE_CLASSIFICATION
            if _synthetic_test_only
            else LIVE_ENVELOPE_CLASSIFICATION
        ),
        "synthetic_test_only": _synthetic_test_only,
        "live_envelope_file": str(envelope_path),
        "built_at_utc": built_utc,
        "offline_phase_a_authority_binding": authority_binding,
        "offline_phase_a_intent_remains_incomplete": True,
        "offline_phase_a_authorization_is_not_live_authorization": True,
        "source_bindings": source_bindings,
        "source_binding_boundary": {
            "on_disk_python_source_files_bound_and_rechecked": True,
            "loaded_bytecode_or_pyc_integrity_proven": False,
            "sitecustomize_or_interpreter_process_integrity_proven": False,
        },
        "candidate_origin": {
            "literal_ipv4": LITERAL_IPV4,
            "port": PORT,
            "absolute_url": ABSOLUTE_URL,
            "unverified_operator_selected_candidate": True,
            "trusted_or_device_identity_proven": False,
            "fresh_boot_or_active_app_proven": False,
        },
        "transport_policy": policy,
        "fresh_onsite_gate_binding": {
            "gate_canonical_sha256": authority["fresh_phase_a_onsite_gate"][
                "gate_canonical_sha256"
            ],
            "not_before_utc": authority["fresh_phase_a_onsite_gate"]["not_before_utc"],
            "not_after_utc": authority["fresh_phase_a_onsite_gate"]["not_after_utc"],
            "any_condition_change_invalidates": True,
            "must_be_rechecked_before_registry_and_before_connect": True,
        },
        "attempt": {
            "live_attempt_id": live_attempt_id,
            "offline_attempt_id": attempt["attempt_id"],
            "registry_file": str(registry_path),
            "terminal_receipt_file": str(receipt_path),
            "finalization_temp_file": str(finalization_temp_path),
            "original_plan_final_output": str(original_final),
            "registry_first_output_second_o_excl": True,
            "attempt_checkpoint_must_be_fsynced_before_socket": True,
            "final_receipt_temp_o_excl_then_atomic_replace": True,
            "finalization_temp_and_output_share_exact_parent_volume": True,
            "atomic_namespace_replace_no_copy_fallback": True,
            "registry_creation_permanently_consumes_authorization": True,
            "registry_immutable_after_initial_write": True,
            "registry_never_deleted_or_retried": True,
            "terminal_output_checkpoint_inode_is_superseded_by_final_receipt": True,
            "terminal_output_path_is_never_retried": True,
            "dual_file_reservation_is_not_atomic": True,
        },
        "authorization_challenge": {
            "phase_domain": "PHASE_A_LIVE_VERSION_ONLY_RUNNER_BOUND",
            "prefix": (
                SYNTHETIC_AUTHORIZATION_PREFIX
                if _synthetic_test_only
                else LIVE_AUTHORIZATION_PREFIX
            ),
            "challenge": challenge,
            "copyable_authorization_token_present": False,
            "must_bind_live_envelope_whole_file_sha256": True,
            "must_bind_live_runner_source_sha256": True,
            "must_bind_exact_request_wire_sha256": True,
            "must_be_byte_exact_case_exact": True,
            "old_offline_phase_a_token_accepted": False,
            "phase_b_token_accepted": False,
            "placeholder_grammar_not_a_token": (
                "{PREFIX}__LIVE_ENVELOPE_FILE_SHA256_{64_HEX_UPPER}"
                "__LIVE_ENVELOPE_ID_{64_HEX_UPPER}"
                "__OFFLINE_AUTHORITY_FILE_SHA256_{64_HEX_UPPER}"
                "__OFFLINE_AUTHORITY_ID_{64_HEX_UPPER}"
                "__LIVE_ATTEMPT_ID_{64_HEX_UPPER}"
                "__CHALLENGE_{64_HEX_UPPER}"
                "__RUNNER_SOURCE_SHA256_{64_HEX_UPPER}"
                "__REQUEST_WIRE_SHA256_{64_HEX_UPPER}"
                "__UNVERIFIED_HTTP_192_168_1_7_PORT_80"
                "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF"
                "__GET_1_POST_0_BODY_0"
                "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0"
                "__NO_RETRY_NO_FALLBACK_NO_RECOVERY_NO_AUTOCHAIN"
            ),
        },
        "success_boundary": {
            "classification_only": "V10_PROTOCOL_RESPONSE_CONFORMANCE",
            "responder_or_device_identity_proven": False,
            "trusted_ip_binding_proven": False,
            "fresh_post_reset_application_boot_proven": False,
            "active_application_or_ota_slot_proven": False,
            "phase_b_authority_or_token_generated": False,
            "phase_b_request_executed": False,
        },
        "terminal_evidence_contract": {
            "raw_status_and_headers_lossless_base64_length_sha256": True,
            "response_entity_lossless_base64_length_sha256": True,
            "strict_parsed_canonical_sha256": True,
            "wire_emission_and_peer_receipt_on_error": "UNKNOWN",
            "per_endpoint_gate_and_failure_stage": True,
            "synthetic_receipts_never_phase_b_eligible": True,
            "atomic_compare_and_swap_proven": False,
            "concurrent_privileged_path_or_parent_replacement": (
                "OUT_OF_SCOPE_NOT_PROVEN"
            ),
        },
        "execution_state": {
            "live_authorized": False,
            "execution_ready_without_separate_exact_user_phrase": False,
            "socket_opened_by_prepare_or_validate": False,
            "phase_b_implemented_or_generated": False,
        },
    }
    unsigned["live_envelope_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def _validate_live_envelope_root(
    root: Mapping[str, Any],
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-A live execution envelope")
    synthetic = root.get("synthetic_test_only")
    if type(synthetic) is not bool:
        raise PhaseALiveError("live envelope synthetic flag type differs")
    if synthetic and not allow_synthetic_test_only:
        raise PhaseALiveError("synthetic test envelope is not a live authority")
    expected_kind = SYNTHETIC_ENVELOPE_KIND if synthetic else LIVE_ENVELOPE_KIND
    expected_class = (
        SYNTHETIC_ENVELOPE_CLASSIFICATION if synthetic else LIVE_ENVELOPE_CLASSIFICATION
    )
    if (
        not _strict_json_equal(root.get("schema_version"), SCHEMA_VERSION)
        or not _strict_json_equal(root.get("kind"), expected_kind)
        or not _strict_json_equal(root.get("classification"), expected_class)
    ):
        raise PhaseALiveError("live execution envelope schema/kind differs")
    attempt = root["attempt"]
    rebuilt = materialize_live_execution_envelope(
        phase_a_authority_file=Path(
            str(root["offline_phase_a_authority_binding"]["path"])
        ),
        live_envelope_file=Path(str(root["live_envelope_file"])),
        built_at=str(root["built_at_utc"]),
        _synthetic_test_only=synthetic,
        _synthetic_registry_file=(
            Path(str(attempt["registry_file"])) if synthetic else None
        ),
        _synthetic_terminal_receipt_file=(
            Path(str(attempt["terminal_receipt_file"])) if synthetic else None
        ),
        _require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(rebuilt):
        raise PhaseALiveError("live envelope differs from deterministic reconstruction")
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"live_envelope_id", "integrity"}
        }
    )
    if root.get("live_envelope_id") != expected_id:
        raise PhaseALiveError("live envelope ID differs")
    return {
        "valid": True,
        "live_envelope_id": root["live_envelope_id"],
        "canonical_sha256": canonical,
        "synthetic_test_only": synthetic,
        "copyable_authorization_token_present": False,
        "socket_opened": False,
        "execution_ready": False,
    }


def validate_live_execution_envelope(
    root: Mapping[str, Any], *, require_attempt_paths_absent: bool = True
) -> dict[str, Any]:
    """Validate only a production envelope; synthetic envelopes are rejected."""

    return _validate_live_envelope_root(
        root,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=False,
    )


def write_new_live_execution_envelope(path: Path, root: Mapping[str, Any]) -> None:
    validate_live_execution_envelope(root, require_attempt_paths_absent=True)
    target = phase_a._safe_absolute(  # noqa: SLF001
        path, label="Phase-A live execution envelope"
    )
    if str(target) != str(root["live_envelope_file"]):
        raise PhaseALiveError("live envelope self-path differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(contract.canonical_json_bytes(root) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise PhaseALiveError("live envelope output already exists") from error
    except OSError as error:
        raise PhaseALiveError(f"could not write live envelope: {error}") from error


def load_live_execution_envelope(path: Path) -> Mapping[str, Any]:
    _, payload, root = _read_strict_json(path, label="Phase-A live execution envelope")
    _require_canonical_artifact_bytes(
        payload, root, label="Phase-A live execution envelope"
    )
    return root


def _authorization_phrase(
    envelope: Mapping[str, Any], *, envelope_file_sha256: str
) -> str:
    if HEX64.fullmatch(envelope_file_sha256) is None:
        raise PhaseALiveError("live envelope whole-file SHA-256 is invalid")
    source = envelope["source_bindings"]["phase_a_live_runner_module"]["sha256"]
    policy = envelope["transport_policy"]
    challenge = envelope["authorization_challenge"]
    authority = envelope["offline_phase_a_authority_binding"]
    prefix = (
        SYNTHETIC_AUTHORIZATION_PREFIX
        if envelope["synthetic_test_only"]
        else LIVE_AUTHORIZATION_PREFIX
    )
    return (
        f"{prefix}"
        f"__LIVE_ENVELOPE_FILE_SHA256_{envelope_file_sha256.upper()}"
        f"__LIVE_ENVELOPE_ID_{str(envelope['live_envelope_id']).upper()}"
        f"__OFFLINE_AUTHORITY_FILE_SHA256_{str(authority['sha256']).upper()}"
        f"__OFFLINE_AUTHORITY_ID_{str(authority['authority_id']).upper()}"
        f"__LIVE_ATTEMPT_ID_{str(envelope['attempt']['live_attempt_id']).upper()}"
        f"__CHALLENGE_{str(challenge['challenge']).upper()}"
        f"__RUNNER_SOURCE_SHA256_{str(source).upper()}"
        f"__REQUEST_WIRE_SHA256_{str(policy['request_wire_sha256']).upper()}"
        "__UNVERIFIED_HTTP_192_168_1_7_PORT_80"
        "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF"
        "__GET_1_POST_0_BODY_0"
        "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0"
        "__NO_RETRY_NO_FALLBACK_NO_RECOVERY_NO_AUTOCHAIN"
    )


def _required_authorization_for_file(
    envelope_file: Path, *, allow_synthetic_test_only: bool
) -> str:
    bundle = _load_live_bundle(
        envelope_file,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    return _authorization_phrase(
        bundle.envelope,
        envelope_file_sha256=str(bundle.envelope_binding["sha256"]),
    )


def _parse_status_and_headers(raw: bytes) -> _ParsedHTTPEnvelope:
    if type(raw) is not bytes:
        raise PhaseALiveTransportError("status/header evidence type differs")
    if len(raw) <= 4 or len(raw) > MAX_STATUS_HEADER_BYTES:
        raise PhaseALiveTransportError("status/header byte budget differs")
    if not raw.endswith(b"\r\n\r\n"):
        raise PhaseALiveTransportError("status/headers lack terminal CRLFCRLF")
    for index, octet in enumerate(raw):
        if octet == 0x0A and (index == 0 or raw[index - 1] != 0x0D):
            raise PhaseALiveTransportError("bare LF in status/headers")
        if octet == 0x0D and (index + 1 >= len(raw) or raw[index + 1] != 0x0A):
            raise PhaseALiveTransportError("bare CR in status/headers")
    lines = raw[:-4].split(b"\r\n")
    if not lines or not lines[0]:
        raise PhaseALiveTransportError("HTTP status line is absent")
    status_match = STATUS_LINE.fullmatch(lines[0])
    if status_match is None:
        raise PhaseALiveTransportError("HTTP status line differs from HTTP/1.1")
    status = int(status_match.group(1))
    if status != 200:
        raise PhaseALiveTransportError(f"HTTP status must equal 200, got {status}")
    headers: list[tuple[str, str]] = []
    lowered: dict[str, list[str]] = {}
    for raw_line in lines[1:]:
        if not raw_line:
            raise PhaseALiveTransportError("empty header line before terminator")
        if raw_line[:1] in {b" ", b"\t"}:
            raise PhaseALiveTransportError("obsolete folded header is forbidden")
        if b":" not in raw_line:
            raise PhaseALiveTransportError("header lacks colon")
        raw_name, raw_value = raw_line.split(b":", 1)
        if HEADER_NAME.fullmatch(raw_name) is None:
            raise PhaseALiveTransportError("HTTP header name token is invalid")
        if any(octet < 0x20 or octet > 0x7E for octet in raw_value):
            raise PhaseALiveTransportError("HTTP header value is not visible ASCII")
        try:
            name = raw_name.decode("ascii")
            value = raw_value.decode("ascii").strip(" ")
        except UnicodeDecodeError as error:
            raise PhaseALiveTransportError("HTTP headers are not ASCII") from error
        headers.append((name, value))
        lowered.setdefault(name.lower(), []).append(value)

    for forbidden in ("transfer-encoding", "content-encoding"):
        if forbidden in lowered:
            raise PhaseALiveTransportError(f"{forbidden} is forbidden")
    if len(lowered.get("content-length", [])) != 1:
        raise PhaseALiveTransportError("exactly one Content-Length is required")
    length_text = lowered["content-length"][0]
    if (
        len(length_text) > len(str(MAX_VERSION_ENTITY_BYTES))
        or ASCII_DECIMAL.fullmatch(length_text) is None
    ):
        raise PhaseALiveTransportError("Content-Length is not canonical ASCII decimal")
    content_length = int(length_text)
    if content_length <= 0 or content_length > MAX_VERSION_ENTITY_BYTES:
        raise PhaseALiveTransportError("Content-Length is outside the entity budget")
    if len(lowered.get("content-type", [])) != 1:
        raise PhaseALiveTransportError("exactly one Content-Type is required")
    content_type = lowered["content-type"][0].lower()
    if content_type not in {"application/json", "application/json; charset=utf-8"}:
        raise PhaseALiveTransportError("Content-Type is not exact JSON/UTF-8")
    if (
        len(lowered.get("connection", [])) != 1
        or lowered["connection"][0].lower() != "close"
    ):
        raise PhaseALiveTransportError("one Connection: close is required")
    return _ParsedHTTPEnvelope(
        status=status,
        headers=tuple(headers),
        content_length=content_length,
    )


class _SocketReader:
    def __init__(self, sock: socket.socket, deadline: float, clock: _UTCClock) -> None:
        self._sock = sock
        self._deadline = deadline
        self._clock = clock

    def recv(self, maximum: int) -> bytes:
        remaining = self._deadline - self._clock.monotonic()
        if remaining <= 0:
            raise PhaseALiveTransportError("total response deadline expired")
        self._sock.settimeout(min(READ_TIMEOUT_MS / 1000, remaining))
        try:
            return self._sock.recv(maximum)
        except (OSError, TimeoutError) as error:
            raise PhaseALiveTransportError(f"socket receive failed: {error}") from error


class _ScriptedReader:
    def __init__(
        self, chunks: tuple[bytes, ...], *, terminal_error: str | None
    ) -> None:
        if any(type(chunk) is not bytes for chunk in chunks):
            raise PhaseALiveError("synthetic response chunks must be exact bytes")
        self._chunks = list(chunks)
        self._terminal_error = terminal_error

    def recv(self, maximum: int) -> bytes:
        if self._chunks:
            chunk = self._chunks.pop(0)
            if len(chunk) > maximum:
                self._chunks.insert(0, chunk[maximum:])
                return chunk[:maximum]
            return chunk
        if self._terminal_error is not None:
            error = self._terminal_error
            self._terminal_error = None
            raise PhaseALiveTransportError(f"synthetic receive failed: {error}")
        return b""


def _read_exact_http_response(
    reader: _SocketReader | _ScriptedReader,
    *,
    endpoint: dict[str, Any],
) -> _RawHTTPResponse:
    if type(reader) not in {_SocketReader, _ScriptedReader}:
        raise PhaseALiveError("response reader type differs")
    buffer = bytearray()
    delimiter = -1
    while delimiter < 0:
        remaining = MAX_STATUS_HEADER_BYTES - len(buffer)
        if remaining <= 0:
            raise PhaseALiveTransportError("status and headers exceed byte budget")
        chunk = reader.recv(min(RECV_CHUNK_BYTES, remaining))
        if not chunk:
            raise PhaseALiveTransportError("EOF before complete status and headers")
        _append_observed_response(endpoint, chunk)
        buffer.extend(chunk)
        delimiter = buffer.find(b"\r\n\r\n")
        if delimiter < 0 and len(buffer) == MAX_STATUS_HEADER_BYTES:
            raise PhaseALiveTransportError("status and headers exceed byte budget")
    header_end = delimiter + 4
    status_and_headers = bytes(buffer[:header_end])
    endpoint["raw_status_and_header_bytes"] = len(status_and_headers)
    endpoint["raw_status_and_header_sha256"] = contract.sha256(status_and_headers)
    endpoint["raw_status_and_header_base64"] = base64.b64encode(
        status_and_headers
    ).decode("ascii")
    endpoint["last_completed_gate"] = "STATUS_HEADERS_RECEIVED"
    parsed = _parse_status_and_headers(status_and_headers)
    endpoint["last_completed_gate"] = "HTTP_ENVELOPE_VALIDATED"
    endpoint["http_status"] = parsed.status
    endpoint["response_headers"] = [list(item) for item in parsed.headers]

    entity = bytearray(buffer[header_end:])
    if len(entity) > parsed.content_length:
        endpoint["_partial_entity_buffer"] = bytearray(entity[: parsed.content_length])
        endpoint["_beyond_content_length_buffer"] = bytearray(
            entity[parsed.content_length :]
        )
        raise PhaseALiveTransportError("response contains bytes beyond Content-Length")
    endpoint["_partial_entity_buffer"] = entity
    while len(entity) < parsed.content_length:
        chunk = reader.recv(min(RECV_CHUNK_BYTES, parsed.content_length - len(entity)))
        if not chunk:
            raise PhaseALiveTransportError("EOF before complete response entity")
        _append_observed_response(endpoint, chunk)
        entity.extend(chunk)
    # Connection: close is part of the exact contract.  One additional read
    # must observe EOF; data is an overlong entity and timeout is not a close.
    extra = reader.recv(1)
    if extra:
        _append_observed_response(endpoint, extra)
        endpoint["_beyond_content_length_buffer"] = bytearray(extra)
        raise PhaseALiveTransportError("response contains bytes beyond Content-Length")
    body = bytes(entity)
    endpoint["last_completed_gate"] = "RESPONSE_ENTITY_RECEIVED"
    return _RawHTTPResponse(
        status_and_headers=status_and_headers,
        entity_body=body,
        parsed=parsed,
    )


def _new_endpoint(*, synthetic_test_only: bool) -> dict[str, Any]:
    return {
        "ordinal": 1,
        "name": "version",
        "method": "GET",
        "path": VERSION_PATH,
        "absolute_url": ABSOLUTE_URL,
        "attempt_checkpoint_persisted_before_socket": True,
        "last_completed_gate": "ATTEMPT_CHECKPOINT_PERSISTED",
        "failure_stage": None,
        "application_transport_attempts": 0,
        "socket_constructor_called": False,
        "socket_connect_called": False,
        "socket_connect_returned": False,
        "request_write_called": False,
        "request_write_completed": False,
        "request_bytes_expected": len(REQUEST_WIRE_BYTES),
        "request_wire_sha256": contract.sha256(REQUEST_WIRE_BYTES),
        "request_wire_base64": base64.b64encode(REQUEST_WIRE_BYTES).decode("ascii"),
        "request_bytes_handed_to_socket_api": 0,
        "request_wire_emitted": (
            "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY" if synthetic_test_only else "UNKNOWN"
        ),
        "peer_received_request": (
            "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY" if synthetic_test_only else "UNKNOWN"
        ),
        "kernel_tcp_retransmission_possible": not synthetic_test_only,
        "observed_response_octets_total": 0,
        "bounded_response_prefix_bytes": 0,
        "bounded_response_prefix_sha256": None,
        "bounded_response_prefix_base64": None,
        "bounded_response_prefix_truncated": False,
        "raw_status_and_header_bytes": None,
        "raw_status_and_header_sha256": None,
        "raw_status_and_header_base64": None,
        "http_status": None,
        "response_headers": None,
        "partial_response_entity_bytes": 0,
        "partial_response_entity_sha256": None,
        "partial_response_entity_base64": None,
        "beyond_content_length_bytes": 0,
        "beyond_content_length_sha256": None,
        "beyond_content_length_base64": None,
        "response_entity_body_bytes": None,
        "response_entity_body_sha256": None,
        "response_entity_body_base64": None,
        "strict_parsed_canonical_sha256": None,
        "validation_stack": [
            "raw_http_status_header_and_content_length_gate",
            "strict_utf8_duplicate_nan_trailing_root_gate",
            "source_pinned_exact_v10_version_surface",
        ],
        "validation_outcome": "STARTED",
    }


def _append_observed_response(endpoint: dict[str, Any], chunk: bytes) -> None:
    """Retain a capped lossless prefix before any receipt base64 expansion."""

    if type(chunk) is not bytes:
        raise PhaseALiveError("observed response chunk type differs")
    endpoint["observed_response_octets_total"] += len(chunk)
    prefix = endpoint.setdefault("_bounded_response_prefix_buffer", bytearray())
    if type(prefix) is not bytearray:
        raise PhaseALiveError("private response prefix accumulator differs")
    remaining = MAX_BOUNDED_RESPONSE_PREFIX_BYTES - len(prefix)
    if remaining > 0:
        prefix.extend(chunk[:remaining])
    if len(chunk) > remaining:
        endpoint["bounded_response_prefix_truncated"] = True


def _finalize_bounded_response_evidence(endpoint: dict[str, Any]) -> None:
    """Convert private bounded accumulators once, after success or failure."""

    prefix = endpoint.pop("_bounded_response_prefix_buffer", bytearray())
    if type(prefix) is not bytearray:
        raise PhaseALiveError("private response prefix accumulator differs")
    prefix_bytes = bytes(prefix)
    endpoint["bounded_response_prefix_bytes"] = len(prefix_bytes)
    if prefix_bytes:
        endpoint["bounded_response_prefix_sha256"] = contract.sha256(prefix_bytes)
        endpoint["bounded_response_prefix_base64"] = base64.b64encode(
            prefix_bytes
        ).decode("ascii")
    partial = endpoint.pop("_partial_entity_buffer", bytearray())
    if type(partial) is not bytearray:
        raise PhaseALiveError("private response entity accumulator differs")
    partial_bytes = bytes(partial)
    endpoint["partial_response_entity_bytes"] = len(partial_bytes)
    if partial_bytes:
        endpoint["partial_response_entity_sha256"] = contract.sha256(partial_bytes)
        endpoint["partial_response_entity_base64"] = base64.b64encode(
            partial_bytes
        ).decode("ascii")
    beyond = endpoint.pop("_beyond_content_length_buffer", bytearray())
    if type(beyond) is not bytearray:
        raise PhaseALiveError("private overlong entity accumulator differs")
    beyond_bytes = bytes(beyond)
    endpoint["beyond_content_length_bytes"] = len(beyond_bytes)
    if beyond_bytes:
        endpoint["beyond_content_length_sha256"] = contract.sha256(beyond_bytes)
        endpoint["beyond_content_length_base64"] = base64.b64encode(
            beyond_bytes
        ).decode("ascii")


class _RawIPv4SingleVersionTransport:
    """Production-only transport with no configurable origin or routing layer."""

    def perform(
        self, *, endpoint: dict[str, Any], clock: _UTCClock
    ) -> _RawHTTPResponse:
        if type(clock) is not _SystemUTCClock:
            raise PhaseALiveError("production transport requires the system UTC clock")
        endpoint["application_transport_attempts"] = 1
        endpoint["socket_constructor_called"] = True
        endpoint["last_completed_gate"] = "SOCKET_CONSTRUCTOR_CALLED"
        sock: socket.socket | None = None
        deadline = clock.monotonic() + TOTAL_TIMEOUT_MS / 1000
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            remaining = deadline - clock.monotonic()
            if remaining <= 0:
                raise PhaseALiveTransportError("total deadline expired before connect")
            sock.settimeout(min(CONNECT_TIMEOUT_MS / 1000, remaining))
            endpoint["socket_connect_called"] = True
            endpoint["last_completed_gate"] = "CONNECT_CALLED"
            try:
                sock.connect((LITERAL_IPV4, PORT))
            except (OSError, TimeoutError) as error:
                raise PhaseALiveTransportError(
                    f"literal IPv4 connect failed: {error}"
                ) from error
            endpoint["socket_connect_returned"] = True
            endpoint["last_completed_gate"] = "CONNECTED"
            endpoint["request_write_called"] = True
            endpoint["last_completed_gate"] = "REQUEST_WRITE_STARTED"
            view = memoryview(REQUEST_WIRE_BYTES)
            while view:
                remaining = deadline - clock.monotonic()
                if remaining <= 0:
                    raise PhaseALiveTransportError(
                        "total deadline expired during request write"
                    )
                sock.settimeout(min(READ_TIMEOUT_MS / 1000, remaining))
                try:
                    written = sock.send(view)
                except (OSError, TimeoutError) as error:
                    raise PhaseALiveTransportError(
                        f"request write failed: {error}"
                    ) from error
                if written <= 0:
                    raise PhaseALiveTransportError("request write returned no progress")
                endpoint["request_bytes_handed_to_socket_api"] += written
                view = view[written:]
            endpoint["request_write_completed"] = True
            endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
            return _read_exact_http_response(
                _SocketReader(sock, deadline, clock), endpoint=endpoint
            )
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    # A close error never replaces the first terminal outcome.
                    pass


class _BuiltInScriptedTestTransport:
    """Exact synthetic transport; no socket and no production CLI exposure."""

    def __init__(
        self,
        *,
        response_chunks: tuple[bytes, ...] = (),
        transport_error: str | None = None,
    ) -> None:
        if type(response_chunks) is not tuple or any(
            type(chunk) is not bytes for chunk in response_chunks
        ):
            raise PhaseALiveError("synthetic chunks type differs")
        if transport_error is not None and type(transport_error) is not str:
            raise PhaseALiveError("synthetic transport error type differs")
        self.response_chunks = response_chunks
        self.transport_error = transport_error
        self.calls = 0

    def perform(
        self, *, endpoint: dict[str, Any], clock: _UTCClock
    ) -> _RawHTTPResponse:
        if type(clock) is not _ScriptedUTCClock:
            raise PhaseALiveError("synthetic transport requires exact private clock")
        if self.calls:
            raise PhaseALiveError("synthetic transport exceeded one call")
        self.calls += 1
        endpoint["application_transport_attempts"] = 1
        endpoint["socket_constructor_called"] = False
        endpoint["socket_connect_called"] = False
        endpoint["socket_connect_returned"] = False
        endpoint["request_write_called"] = True
        endpoint["request_write_completed"] = True
        endpoint["request_bytes_handed_to_socket_api"] = len(REQUEST_WIRE_BYTES)
        endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
        if self.transport_error is not None:
            raise PhaseALiveTransportError(
                f"synthetic transport failed: {self.transport_error}"
            )
        return _read_exact_http_response(
            _ScriptedReader(self.response_chunks, terminal_error=None),
            endpoint=endpoint,
        )


def _load_live_bundle(
    envelope_file: Path,
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> _LiveBundle:
    """Complete every deep/source/release preflight before attempt reservation."""

    envelope_path, envelope_payload, envelope = _read_strict_json(
        envelope_file, label="Phase-A live execution envelope"
    )
    _require_canonical_artifact_bytes(
        envelope_payload, envelope, label="Phase-A live execution envelope"
    )
    sealed_envelope_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(envelope.get("live_envelope_file"))),
        label="sealed Phase-A live execution envelope path",
    )
    if envelope_path != sealed_envelope_path:
        raise PhaseALiveError("actual live envelope path differs from sealed self-path")
    envelope_snapshot = _snapshot(
        envelope_path, label="Phase-A live execution envelope"
    )
    if envelope_snapshot.sha256 != contract.sha256(
        envelope_payload
    ) or envelope_snapshot.size != len(envelope_payload):
        raise PhaseALiveError("live envelope changed between parse and snapshot")
    _validate_live_envelope_root(
        envelope,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    authority_path, authority_payload, authority, authority_binding = _authority_bundle(
        Path(str(envelope["offline_phase_a_authority_binding"]["path"])),
        require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if not _strict_json_equal(
        authority_binding, envelope["offline_phase_a_authority_binding"]
    ):
        raise PhaseALiveError("offline authority whole-file binding differs")
    authority_snapshot = _snapshot(authority_path, label="offline Phase-A authority")
    if authority_snapshot.sha256 != contract.sha256(
        authority_payload
    ) or authority_snapshot.size != len(authority_payload):
        raise PhaseALiveError("offline authority changed between parse and snapshot")

    blueprint_path, blueprint_payload, blueprint = _read_strict_json(
        Path(str(authority["blueprint_binding"]["path"])),
        label="frozen Stage-B V2 blueprint",
    )
    try:
        facade.validate_blueprint(blueprint, require_live_output_absent=True)
    except facade.StageBFacadeContractError as error:
        raise PhaseALiveError(f"frozen V2 blueprint differs: {error}") from error
    blueprint_snapshot = _snapshot(blueprint_path, label="frozen Stage-B V2 blueprint")
    if (
        blueprint_snapshot.sha256 != contract.sha256(blueprint_payload)
        or blueprint_snapshot.size != len(blueprint_payload)
        or blueprint_snapshot.sha256 != authority["blueprint_binding"]["sha256"]
    ):
        raise PhaseALiveError("frozen V2 blueprint changed or binding differs")

    release_path, release_payload, release_root = _read_strict_json(
        Path(str(blueprint["frozen_v10_validator_binding"]["release_file"])),
        label="frozen V10 release",
    )
    release_snapshot = _snapshot(release_path, label="frozen V10 release")
    if release_snapshot.sha256 != contract.sha256(
        release_payload
    ) or release_snapshot.size != len(release_payload):
        raise PhaseALiveError("frozen V10 release changed between parse and snapshot")
    v10_context = facade._load_frozen_v10_release(  # noqa: SLF001
        release_path
    )
    release_snapshot.assert_unchanged()
    if (
        release_root.get("release_id")
        != blueprint["frozen_v10_validator_binding"]["release_id"]
    ):
        raise PhaseALiveError("frozen V10 release ID binding differs")

    source_bindings = envelope["source_bindings"]
    source_snapshots: list[_FileSnapshot] = []
    for name, binding in source_bindings.items():
        if type(binding) is not dict:
            raise PhaseALiveError(f"source binding {name} type differs")
        snapshot = _snapshot(Path(str(binding["path"])), label=name)
        if snapshot.sha256 != binding["sha256"] or snapshot.size != binding["bytes"]:
            raise PhaseALiveError(f"source binding {name} changed or differs")
        source_snapshots.append(snapshot)
    for name, binding in blueprint["exact_response_surface_validation"][
        "source_bindings"
    ].items():
        if type(binding) is not dict:
            raise PhaseALiveError(f"V10 response source binding {name} type differs")
        snapshot = _snapshot(
            Path(str(binding["path"])), label=f"V10 response source {name}"
        )
        if snapshot.sha256 != binding["sha256"] or snapshot.size != binding["bytes"]:
            raise PhaseALiveError(
                f"V10 response source binding {name} changed or differs"
            )
        source_snapshots.append(snapshot)
    snapshots = tuple(
        {
            str(item.path): item
            for item in (
                envelope_snapshot,
                authority_snapshot,
                blueprint_snapshot,
                release_snapshot,
                *source_snapshots,
            )
        }.values()
    )
    envelope_binding = {
        "path": str(envelope_path),
        "bytes": len(envelope_payload),
        "sha256": contract.sha256(envelope_payload),
        "canonical_sha256": envelope["integrity"]["canonical_sha256"],
        "live_envelope_id": envelope["live_envelope_id"],
    }
    return _LiveBundle(
        envelope_path=envelope_path,
        envelope_payload=envelope_payload,
        envelope=envelope,
        envelope_binding=envelope_binding,
        authority_path=authority_path,
        authority_payload=authority_payload,
        authority=authority,
        authority_binding=authority_binding,
        v10_context=v10_context,
        snapshots=snapshots,
        synthetic_test_only=bool(envelope["synthetic_test_only"]),
    )


def _check_execution_time(
    bundle: _LiveBundle,
    *,
    clock: _UTCClock,
    label: str,
    synthetic_claimed_now: str | None,
) -> tuple[str, str]:
    host = clock.wall_now().astimezone(timezone.utc)
    observed = host
    if synthetic_claimed_now is not None:
        if type(clock) is not _ScriptedUTCClock:
            raise PhaseALiveError("production time may not be caller supplied")
        observed = _parse_zoned(
            synthetic_claimed_now, label="synthetic Phase-A execution now"
        )
        if abs((host - observed).total_seconds()) > MAX_HOST_NOW_SKEW_SECONDS:
            raise PhaseALiveError(
                f"{label} synthetic clock differs from claimed test time"
            )
        _gate_time(
            bundle.authority,
            now=observed,
            label=f"{label} synthetic claimed time",
        )
    _gate_time(bundle.authority, now=host, label=f"{label} host UTC")
    return _utc_text(observed), _utc_text(host)


def _assert_preloaded_sources_unchanged(bundle: _LiveBundle) -> None:
    for snapshot in bundle.snapshots:
        snapshot.assert_unchanged()


def _creation_identity(info: os.stat_result) -> dict[str, int]:
    return {
        "st_dev": int(info.st_dev),
        "st_ino": int(info.st_ino),
        "st_nlink": int(info.st_nlink),
    }


def _validate_creation_identity(value: Any, *, label: str) -> dict[str, int]:
    if type(value) is not dict or set(value) != {"st_dev", "st_ino", "st_nlink"}:
        raise PhaseALiveError(f"{label} exact key set differs")
    if any(type(value[key]) is not int or value[key] < 0 for key in value):
        raise PhaseALiveError(f"{label} integer fields differ")
    if value["st_nlink"] != 1:
        raise PhaseALiveError(f"{label} link count differs")
    return dict(value)


def _strict_json_equal(actual: Any, expected: Any) -> bool:
    """JSON equality with no Python bool/int aliasing at any nesting depth."""

    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(
            _strict_json_equal(actual[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _strict_json_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _require_distinct_creation_identities(
    *identities: Mapping[str, Any], label: str
) -> None:
    tokens = {(item["st_dev"], item["st_ino"]) for item in identities}
    if len(tokens) != len(identities):
        raise PhaseALiveError(f"{label} creation identities are not pairwise distinct")


def _registry_record(
    bundle: _LiveBundle,
    *,
    authorization_sha256: str,
    pre_registry_host_now_utc: str,
    creation_identity: Mapping[str, Any],
) -> dict[str, Any]:
    envelope = bundle.envelope
    attempt = envelope["attempt"]
    synthetic = bundle.synthetic_test_only
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": SYNTHETIC_REGISTRY_KIND if synthetic else LIVE_REGISTRY_KIND,
            "classification": (
                "SYNTHETIC_TEST_ONLY_PERMANENT_ATTEMPT_CONSUMPTION"
                if synthetic
                else "LIVE_PHASE_A_PERMANENT_ATTEMPT_CONSUMPTION"
            ),
            "state": "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_SOCKET",
            "synthetic_test_only": synthetic,
            "live_envelope_binding": dict(bundle.envelope_binding),
            "offline_authority_binding": dict(bundle.authority_binding),
            "live_envelope_id": envelope["live_envelope_id"],
            "live_attempt_id": attempt["live_attempt_id"],
            "offline_attempt_id": attempt["offline_attempt_id"],
            "authorization_phrase_sha256": authorization_sha256,
            "authorization_phrase_stored": False,
            "onsite_gate_canonical_sha256": bundle.authority[
                "fresh_phase_a_onsite_gate"
            ]["gate_canonical_sha256"],
            "gate_not_before_utc": bundle.authority["fresh_phase_a_onsite_gate"][
                "not_before_utc"
            ],
            "gate_not_after_utc": bundle.authority["fresh_phase_a_onsite_gate"][
                "not_after_utc"
            ],
            "pre_registry_system_utc": pre_registry_host_now_utc,
            "pre_registry_time_rule_satisfied": True,
            "creation_identity": dict(creation_identity),
            "creation_identity_is_local_filesystem_evidence_not_portable": True,
            "terminal_receipt_file": attempt["terminal_receipt_file"],
            "registry_created_before_output": True,
            "registry_created_before_socket": True,
            "immutable_after_initial_o_excl_write": True,
            "outcome_only_in_terminal_receipt": True,
            "network_requests_before_registry": 0,
            "socket_constructors_before_registry": 0,
            "retry_allowed": False,
            "registry_never_deleted": True,
            "terminal_output_checkpoint_may_be_atomically_superseded": True,
            "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        }
    )


def _reserve_registry_once(
    path: Path,
    *,
    bundle: _LiveBundle,
    authorization_sha256: str,
    pre_registry_host_now_utc: str,
) -> tuple[Any, dict[str, Any], bytes]:
    """O_EXCL-create and write the immutable registry exactly once.

    The creation identity is collected from the held descriptor before the
    record is constructed, so it is part of the only sealed payload ever
    written to this path.  A failed/partial write still consumes the path and
    is never repaired or retried.
    """

    target = phase_a._safe_absolute(path, label="Phase-A live attempt registry")  # noqa: SLF001
    target.parent.mkdir(parents=True, exist_ok=True)
    target = phase_a._safe_absolute(  # noqa: SLF001
        target, label="Phase-A live attempt registry"
    )
    handle: Any | None = None
    try:
        handle = target.open("xb+", buffering=0)
        created = os.fstat(handle.fileno())
        path_info = target.lstat()
    except FileExistsError as error:
        raise PhaseALiveError(
            "Phase-A live attempt registry already exists; no retry"
        ) from error
    except OSError as error:
        if handle is not None:
            handle.close()
        raise PhaseALiveError(
            f"could not reserve Phase-A live attempt registry: {error}"
        ) from error
    if (
        stat.S_ISLNK(path_info.st_mode)
        or phase_a._is_reparse(path_info)  # noqa: SLF001
        or not stat.S_ISREG(created.st_mode)
        or not stat.S_ISREG(path_info.st_mode)
        or created.st_nlink != 1
        or path_info.st_nlink != 1
        or (created.st_dev, created.st_ino) != (path_info.st_dev, path_info.st_ino)
    ):
        handle.close()
        raise PhaseALiveError("Phase-A live registry creation identity differs")
    identity = _creation_identity(created)
    record = _registry_record(
        bundle,
        authorization_sha256=authorization_sha256,
        pre_registry_host_now_utc=pre_registry_host_now_utc,
        creation_identity=identity,
    )
    payload = contract.canonical_json_bytes(record) + b"\n"
    sink = phase_a._EvidenceSink(  # noqa: SLF001
        path=target,
        handle=handle,
        identity=(created.st_dev, created.st_ino),
        label="Phase-A live attempt registry",
    )
    try:
        written = handle.write(payload)
        if written != len(payload):
            raise PhaseALiveError("Phase-A live registry write was partial")
        handle.flush()
        os.fsync(handle.fileno())
        sink.assert_identity()
        held = os.fstat(handle.fileno())
        if held.st_size != len(payload) or _creation_identity(held) != identity:
            raise PhaseALiveError(
                "Phase-A live registry durable identity/length differs"
            )
        handle.seek(0)
        if handle.read() != payload:
            raise PhaseALiveError("Phase-A live registry durable bytes differ")
        sink.parent_directory_fsync_status = phase_a._fsync_parent_directory(  # noqa: SLF001
            target
        )
    except BaseException:
        sink.close()
        raise
    return sink, record, payload


def _reserve_empty_sink(path: Path, *, label: str) -> tuple[Any, dict[str, int]]:
    """Reserve one evidence path without writing a placeholder payload."""

    target = phase_a._safe_absolute(path, label=label)  # noqa: SLF001
    target.parent.mkdir(parents=True, exist_ok=True)
    target = phase_a._safe_absolute(target, label=label)  # noqa: SLF001
    handle: Any | None = None
    try:
        handle = target.open("xb+", buffering=0)
        created = os.fstat(handle.fileno())
        path_info = target.lstat()
    except FileExistsError as error:
        raise PhaseALiveError(f"{label} already exists; no retry") from error
    except OSError as error:
        if handle is not None:
            handle.close()
        raise PhaseALiveError(f"could not reserve {label}: {error}") from error
    if (
        stat.S_ISLNK(path_info.st_mode)
        or phase_a._is_reparse(path_info)  # noqa: SLF001
        or not stat.S_ISREG(created.st_mode)
        or not stat.S_ISREG(path_info.st_mode)
        or created.st_nlink != 1
        or path_info.st_nlink != 1
        or (created.st_dev, created.st_ino) != (path_info.st_dev, path_info.st_ino)
    ):
        handle.close()
        raise PhaseALiveError(f"{label} creation identity differs")
    sink = phase_a._EvidenceSink(  # noqa: SLF001
        path=target,
        handle=handle,
        identity=(created.st_dev, created.st_ino),
        label=label,
    )
    sink.parent_directory_fsync_status = phase_a._fsync_parent_directory(target)  # noqa: SLF001
    return sink, _creation_identity(created)


def _receipt_root(
    bundle: _LiveBundle,
    *,
    state: str,
    authorization_sha256: str,
    registry_file: Path,
    registry_canonical_sha256: str,
    registry_whole_file_sha256: str,
    registry_creation_identity: Mapping[str, Any],
    registry_parent_fsync: str,
    output_parent_fsync: str,
    output_checkpoint_creation_identity: Mapping[str, Any],
    output_checkpoint_whole_file_bytes: int | None,
    output_checkpoint_whole_file_sha256: str | None,
    output_checkpoint_canonical_sha256: str | None,
    finalization_temp_creation_identity: Mapping[str, Any] | None,
    finalization_temp_parent_fsync: str,
    execution_observed_now_utc: str,
    pre_registry_host_now_utc: str,
    pre_connect_host_now_utc: str | None,
    endpoint: Mapping[str, Any] | None,
    success: bool,
    error: BaseException | None,
) -> dict[str, Any]:
    synthetic = bundle.synthetic_test_only
    endpoint_copy = [] if endpoint is None else [deepcopy(dict(endpoint))]
    endpoint_value = None if endpoint is None else dict(endpoint)
    application_attempts = (
        0
        if endpoint_value is None
        else endpoint_value["application_transport_attempts"]
    )
    request_write_calls = (
        0 if endpoint_value is None or not endpoint_value["request_write_called"] else 1
    )
    handed_bytes = (
        0
        if endpoint_value is None
        else endpoint_value["request_bytes_handed_to_socket_api"]
    )
    fully_written = (
        1
        if endpoint_value is not None and endpoint_value["request_write_completed"]
        else 0
    )
    responses_received = (
        1
        if endpoint_value is not None
        and endpoint_value["raw_status_and_header_bytes"] is not None
        else 0
    )
    error_text: str | None = None
    if error is not None:
        encoded_error = str(error).encode("utf-8", errors="replace")
        if not encoded_error:
            encoded_error = b"NO_EXCEPTION_MESSAGE_PROVIDED"
        if len(encoded_error) > MAX_ERROR_TEXT_BYTES:
            suffix = b" [TRUNCATED_TO_ERROR_EVIDENCE_BUDGET]"
            encoded_error = encoded_error[: MAX_ERROR_TEXT_BYTES - len(suffix)]
            while True:
                try:
                    error_text = encoded_error.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    encoded_error = encoded_error[:-1]
            error_text += suffix.decode("ascii")
        else:
            error_text = encoded_error.decode("utf-8")
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": SYNTHETIC_RECEIPT_KIND if synthetic else LIVE_RECEIPT_KIND,
        "classification": (
            "SYNTHETIC_TEST_ONLY_TERMINAL_RECEIPT_NEVER_PHASE_B_ELIGIBLE"
            if synthetic
            else "PHASE_A_LIVE_TERMINAL_RECEIPT_PROTOCOL_CONFORMANCE_ONLY"
        ),
        "state": state,
        "synthetic_test_only": synthetic,
        "live_envelope_binding": dict(bundle.envelope_binding),
        "offline_authority_binding": dict(bundle.authority_binding),
        "live_envelope_id": bundle.envelope["live_envelope_id"],
        "live_attempt_id": bundle.envelope["attempt"]["live_attempt_id"],
        "offline_attempt_id": bundle.envelope["attempt"]["offline_attempt_id"],
        "authorization_phrase_sha256": authorization_sha256,
        "authorization_phrase_stored": False,
        "onsite_gate_canonical_sha256": bundle.authority["fresh_phase_a_onsite_gate"][
            "gate_canonical_sha256"
        ],
        "execution_observed_now_utc": execution_observed_now_utc,
        "pre_registry_host_now_utc": pre_registry_host_now_utc,
        "pre_connect_host_now_utc": pre_connect_host_now_utc,
        "attempt_registry_file": str(registry_file),
        "registry_initial_canonical_sha256": registry_canonical_sha256,
        "registry_whole_file_sha256": registry_whole_file_sha256,
        "registry_creation_identity": dict(registry_creation_identity),
        "registry_is_immutable_o_excl_marker": True,
        "registry_parent_directory_fsync_status": registry_parent_fsync,
        "output_parent_directory_fsync_status": output_parent_fsync,
        "output_checkpoint_creation_identity": dict(
            output_checkpoint_creation_identity
        ),
        "output_checkpoint_whole_file_bytes": output_checkpoint_whole_file_bytes,
        "output_checkpoint_whole_file_sha256": (output_checkpoint_whole_file_sha256),
        "output_checkpoint_canonical_sha256": (output_checkpoint_canonical_sha256),
        "output_checkpoint_identity_and_hash_are_finalization_preconditions": True,
        "output_checkpoint_creation_identity_is_runtime_evidence_not_post_replace_replay_proof": True,
        "terminal_receipt_file": bundle.envelope["attempt"]["terminal_receipt_file"],
        "finalization_temp_file": bundle.envelope["attempt"]["finalization_temp_file"],
        "finalization_temp_creation_identity": (
            None
            if finalization_temp_creation_identity is None
            else dict(finalization_temp_creation_identity)
        ),
        "finalization_temp_parent_directory_fsync_status": (
            finalization_temp_parent_fsync
        ),
        "terminalization_policy_requires_temp_o_excl_then_atomic_replace": True,
        "atomic_replace_required_before_receipt_is_committed": True,
        "payload_does_not_self_assert_atomic_replace_commit": True,
        "atomic_compare_and_swap_proven": False,
        "concurrent_privileged_destination_replacement_between_final_check_and_replace": (
            "OUT_OF_SCOPE_NOT_PROVEN"
        ),
        "concurrent_privileged_parent_path_replacement": "OUT_OF_SCOPE_NOT_PROVEN",
        "post_replace_parent_directory_fsync_result_is_not_embedded": True,
        "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        "endpoint_outcomes": endpoint_copy,
        "maximum_application_transport_attempts": 1,
        "application_transport_attempts": application_attempts,
        "request_write_calls": request_write_calls,
        "request_bytes_handed_to_socket_api": handed_bytes,
        "fully_written_version_gets": fully_written,
        "http_responses_with_complete_status_headers": responses_received,
        "post_requests": 0,
        "request_bodies": 0,
        "device_api_claim_requests": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "dns_proxy_redirect_scan_fallback_or_application_retry_requests": 0,
        "serial_or_com_accesses": 0,
        "retry_allowed": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "original_plan_final_output_touched": False,
        "version_protocol_response_conformance": success,
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_post_reset_application_boot_proven": False,
        "active_application_or_ota_slot_proven": False,
        "phase_b_authority_generated": False,
        "phase_b_authorization_generated": False,
        "phase_b_requests": 0,
        "may_request_separate_phase_b_authority": False,
        "may_request_separate_phase_b_authority_only_after_committed_final_path_validation": (
            success and not synthetic
        ),
        "eligible_for_direct_phase_b_execution": False,
        "synthetic_receipt_never_phase_b_eligible": synthetic,
        "actual_device_or_background_side_effects": (
            "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
            if synthetic
            else "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
        ),
        "error_type": None if error is None else type(error).__name__,
        "error": error_text,
    }
    sealed = _seal(unsigned)
    if len(contract.canonical_json_bytes(sealed) + b"\n") > MAX_TERMINAL_RECEIPT_BYTES:
        raise PhaseALiveError("terminal receipt exceeds strict loader byte budget")
    return sealed


def _checkpoint_receipt(
    bundle: _LiveBundle,
    *,
    authorization_sha256: str,
    registry_file: Path,
    registry_canonical_sha256: str,
    registry_whole_file_sha256: str,
    registry_creation_identity: Mapping[str, Any],
    registry_parent_fsync: str,
    output_parent_fsync: str,
    output_checkpoint_creation_identity: Mapping[str, Any],
    execution_observed_now_utc: str,
    pre_registry_host_now_utc: str,
    endpoint: Mapping[str, Any] | None,
    state: str,
) -> dict[str, Any]:
    return _receipt_root(
        bundle,
        state=state,
        authorization_sha256=authorization_sha256,
        registry_file=registry_file,
        registry_canonical_sha256=registry_canonical_sha256,
        registry_whole_file_sha256=registry_whole_file_sha256,
        registry_creation_identity=registry_creation_identity,
        registry_parent_fsync=registry_parent_fsync,
        output_parent_fsync=output_parent_fsync,
        output_checkpoint_creation_identity=output_checkpoint_creation_identity,
        output_checkpoint_whole_file_bytes=None,
        output_checkpoint_whole_file_sha256=None,
        output_checkpoint_canonical_sha256=None,
        finalization_temp_creation_identity=None,
        finalization_temp_parent_fsync=("NOT_CREATED_BEFORE_TERMINAL_FINALIZATION"),
        execution_observed_now_utc=execution_observed_now_utc,
        pre_registry_host_now_utc=pre_registry_host_now_utc,
        pre_connect_host_now_utc=None,
        endpoint=endpoint,
        success=False,
        error=PhaseALiveError(
            "crash or process interruption after permanent attempt consumption"
        ),
    )


def _failure_stage(endpoint: Mapping[str, Any]) -> str:
    return {
        "ATTEMPT_CHECKPOINT_PERSISTED": "PRE_CONNECT_RECHECK",
        "SOCKET_CONSTRUCTOR_CALLED": "SOCKET_CONSTRUCTOR",
        "CONNECT_CALLED": "CONNECT",
        "CONNECTED": "PRE_REQUEST_WRITE",
        "REQUEST_WRITE_STARTED": "REQUEST_WRITE",
        "REQUEST_WRITE_COMPLETED": "RESPONSE_STATUS_HEADER_READ",
        "STATUS_HEADERS_RECEIVED": "HTTP_ENVELOPE_VALIDATION",
        "HTTP_ENVELOPE_VALIDATED": "RESPONSE_ENTITY_READ_OR_CONNECTION_CLOSE",
        "RESPONSE_ENTITY_RECEIVED": "STRICT_JSON_OR_EXACT_V10_VALIDATION",
        "EXACT_V10_VALIDATED": "POST_VALIDATION_EVIDENCE",
    }[str(endpoint["last_completed_gate"])]


def _decode_evidence_base64(
    *, value: Any, length: Any, sha256: Any, label: str, maximum: int
) -> bytes:
    if type(value) is not str or type(length) is not int or type(sha256) is not str:
        raise PhaseALiveError(f"{label} evidence bundle type differs")
    if length < 0 or length > maximum or HEX64.fullmatch(sha256) is None:
        raise PhaseALiveError(f"{label} evidence bounds/hash differ")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PhaseALiveError(f"{label} base64 is invalid") from error
    if len(decoded) != length or contract.sha256(decoded) != sha256:
        raise PhaseALiveError(f"{label} evidence length/hash differs")
    return decoded


def _finalize_response_and_validate(
    endpoint: dict[str, Any], response: _RawHTTPResponse, *, v10_context: Any
) -> None:
    body = response.entity_body
    if len(body) <= 0 or len(body) > MAX_VERSION_ENTITY_BYTES:
        raise PhaseALiveError("response entity size differs after HTTP parser")
    endpoint["response_entity_body_bytes"] = len(body)
    endpoint["response_entity_body_sha256"] = contract.sha256(body)
    endpoint["response_entity_body_base64"] = base64.b64encode(body).decode("ascii")
    try:
        parsed, _ = facade.decode_and_validate_v10_response_bytes(
            "version", body, v10_context
        )
    except RecursionError as error:
        raise PhaseALiveError(
            "version JSON nesting exceeds the strict decoder"
        ) from error
    endpoint["strict_parsed_canonical_sha256"] = contract.sha256(parsed)
    endpoint["validation_outcome"] = "PASS"
    endpoint["last_completed_gate"] = "EXACT_V10_VALIDATED"


def _assert_sink_exact(sink: Any, payload: bytes, *, label: str) -> str:
    expected_sha256 = contract.sha256(payload)
    sink.assert_identity()
    if sink.whole_file_sha256() != expected_sha256:
        raise PhaseALiveError(f"{label} bytes differ from their precomputed payload")
    held = os.fstat(sink.handle.fileno())
    if held.st_size != len(payload):
        raise PhaseALiveError(f"{label} length differs from its precomputed payload")
    return expected_sha256


def _prevalidate_terminal_candidate(
    root: Mapping[str, Any],
    *,
    bundle: _LiveBundle,
    terminal_success: bool,
) -> None:
    """Reject an unreachable candidate before any finalization bytes are written."""

    _validate_seal(root, label="in-memory Phase-A terminal candidate")
    expected_state = (
        "TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE"
        if terminal_success
        else "TERMINAL_FAILURE_NO_RETRY"
    )
    if root.get("state") != expected_state:
        raise PhaseALiveError("terminal candidate state differs")
    outcomes = root.get("endpoint_outcomes")
    if (
        type(outcomes) is not list
        or len(outcomes) != 1
        or type(outcomes[0]) is not dict
    ):
        raise PhaseALiveError("terminal candidate endpoint outcomes differ")
    endpoint = outcomes[0]
    _validate_endpoint_evidence(
        endpoint,
        bundle=bundle,
        terminal_success=terminal_success,
    )
    attempts = endpoint["application_transport_attempts"]
    if (root.get("pre_connect_host_now_utc") is None) is not (attempts == 0):
        raise PhaseALiveError("terminal candidate pre-connect/attempt state differs")
    if not bundle.synthetic_test_only and (
        root.get("execution_observed_now_utc") != root.get("pre_registry_host_now_utc")
    ):
        raise PhaseALiveError("production observed/pre-registry UTC differs")
    if terminal_success:
        if root.get("error_type") is not None or root.get("error") is not None:
            raise PhaseALiveError("terminal success candidate contains an error")
    elif (
        type(root.get("error_type")) is not str
        or type(root.get("error")) is not str
        or not root["error"]
    ):
        raise PhaseALiveError("terminal failure candidate lacks bounded error evidence")


def _execute_loaded_bundle(
    bundle: _LiveBundle,
    *,
    authorization: str,
    synthetic_now: str | None,
    clock: _SystemUTCClock | _ScriptedUTCClock,
    synthetic_transport: _BuiltInScriptedTestTransport | None,
) -> dict[str, Any]:
    synthetic = bundle.synthetic_test_only
    if synthetic:
        if (
            type(clock) is not _ScriptedUTCClock
            or type(synthetic_transport) is not _BuiltInScriptedTestTransport
        ):
            raise PhaseALiveError("synthetic execution requires exact private types")
        if type(synthetic_now) is not str:
            raise PhaseALiveError("synthetic execution requires private test time")
    elif type(clock) is not _SystemUTCClock or synthetic_transport is not None:
        raise PhaseALiveError("production execution rejects injected clock/transport")
    elif synthetic_now is not None:
        raise PhaseALiveError("production execution rejects caller-supplied time")
    envelope = bundle.envelope
    required = _authorization_phrase(
        envelope, envelope_file_sha256=bundle.envelope_binding["sha256"]
    )
    if type(authorization) is not str or authorization != required:
        raise PhaseALiveError("exact runner-bound Phase-A live authorization differs")
    try:
        authorization_ascii = authorization.encode("ascii")
    except UnicodeEncodeError as error:
        raise PhaseALiveError("authorization phrase is not exact ASCII") from error
    execution_observed_now_utc, pre_registry_host_now_utc = _check_execution_time(
        bundle,
        clock=clock,
        label="pre-registry",
        synthetic_claimed_now=synthetic_now,
    )
    _assert_preloaded_sources_unchanged(bundle)

    attempt = envelope["attempt"]
    registry_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(attempt["registry_file"])), label="Phase-A live registry"
    )
    output_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(attempt["terminal_receipt_file"])),
        label="Phase-A live terminal receipt",
    )
    temp_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(attempt["finalization_temp_file"])),
        label="Phase-A live finalization temp",
    )
    if _directory_entry_exists(registry_path):
        raise PhaseALiveError("Phase-A live registry exists; no retry")
    if _directory_entry_exists(output_path):
        raise PhaseALiveError(
            "Phase-A live output already exists before registry; zero-attempt stop"
        )
    if _directory_entry_exists(temp_path):
        raise PhaseALiveError(
            "Phase-A live finalization temp already exists before registry; "
            "zero-attempt stop"
        )
    authorization_sha256 = contract.sha256(authorization_ascii)
    registry, registry_initial, registry_payload = _reserve_registry_once(
        registry_path,
        bundle=bundle,
        authorization_sha256=authorization_sha256,
        pre_registry_host_now_utc=pre_registry_host_now_utc,
    )
    output: Any | None = None
    final_temp: Any | None = None
    try:
        registry_sha = contract.sha256(registry_payload)
        if registry.whole_file_sha256() != registry_sha:
            raise PhaseALiveError(
                "immutable registry differs from its precomputed initial payload"
            )
        registry_creation_identity = _validate_creation_identity(
            registry_initial["creation_identity"],
            label="registry creation identity",
        )
        output, output_creation_identity = _reserve_empty_sink(
            output_path, label="Phase-A live terminal receipt checkpoint"
        )
        _require_distinct_creation_identities(
            registry_creation_identity,
            output_creation_identity,
            label="pre-socket registry and output checkpoint",
        )
        endpoint = _new_endpoint(synthetic_test_only=synthetic)
        checkpoint = _checkpoint_receipt(
            bundle,
            authorization_sha256=authorization_sha256,
            registry_file=registry_path,
            registry_canonical_sha256=registry_initial["integrity"]["canonical_sha256"],
            registry_whole_file_sha256=registry_sha,
            registry_creation_identity=registry_creation_identity,
            registry_parent_fsync=registry.parent_directory_fsync_status,
            output_parent_fsync=output.parent_directory_fsync_status,
            output_checkpoint_creation_identity=output_creation_identity,
            execution_observed_now_utc=execution_observed_now_utc,
            pre_registry_host_now_utc=pre_registry_host_now_utc,
            endpoint=endpoint,
            state=(
                "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
                "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
            ),
        )
        checkpoint_payload = contract.canonical_json_bytes(checkpoint) + b"\n"
        output.replace(checkpoint)
        checkpoint_file_sha256 = _assert_sink_exact(
            output,
            checkpoint_payload,
            label="persisted attempt checkpoint",
        )
        _validate_indeterminate_checkpoint_file(
            output_path,
            bundle=bundle,
            registry_file=registry_path,
        )

        error: BaseException | None = None
        success = False
        pre_connect_host_now_utc: str | None = None
        try:
            registry.assert_identity()
            output.assert_identity()
            if registry.whole_file_sha256() != registry_sha:
                raise PhaseALiveError("immutable registry bytes changed before socket")
            if output.whole_file_sha256() != checkpoint_file_sha256:
                raise PhaseALiveError(
                    "persisted attempt checkpoint changed before socket"
                )
            _assert_preloaded_sources_unchanged(bundle)
            _, pre_connect_host_now_utc = _check_execution_time(
                bundle,
                clock=clock,
                label="pre-connect",
                synthetic_claimed_now=synthetic_now,
            )
            # The clock check is intentionally inside the no-network gap; do
            # one final exact byte/identity/source check after it so a change
            # during that check cannot become the socket baseline.
            registry.assert_identity()
            output.assert_identity()
            if registry.whole_file_sha256() != registry_sha:
                raise PhaseALiveError(
                    "immutable registry bytes changed at final pre-connect gate"
                )
            if output.whole_file_sha256() != checkpoint_file_sha256:
                raise PhaseALiveError(
                    "persisted checkpoint bytes changed at final pre-connect gate"
                )
            _assert_preloaded_sources_unchanged(bundle)
            if synthetic:
                if (
                    synthetic_transport is None
                ):  # exact type check above is authoritative
                    raise PhaseALiveError("synthetic transport is absent")
                response = synthetic_transport.perform(endpoint=endpoint, clock=clock)
            else:
                # The production socket object is not even constructed until
                # after registry, output, checkpoint fsync, identity, source,
                # authorization, and the second time-window check all pass.
                response = _RawIPv4SingleVersionTransport().perform(
                    endpoint=endpoint, clock=clock
                )
            _finalize_response_and_validate(
                endpoint, response, v10_context=bundle.v10_context
            )
            success = True
        except BaseException as caught:
            error = caught

        # Asynchronous process-control exceptions may land between paired
        # endpoint mutations.  Never overwrite the already strict checkpoint
        # with a possibly unreachable candidate; the attempt stays consumed
        # and its network outcome remains explicitly unknown.
        if error is not None and not isinstance(error, Exception):
            _validate_indeterminate_checkpoint_file(
                output_path,
                bundle=bundle,
                registry_file=registry_path,
            )
            raise error

        try:
            _finalize_bounded_response_evidence(endpoint)
            if not success:
                endpoint["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
                endpoint["failure_stage"] = _failure_stage(endpoint)
            # Validate the complete state machine before even reserving the
            # finalization temp.  Any internal inconsistency leaves the strict
            # checkpoint untouched.
            _validate_endpoint_evidence(
                endpoint,
                bundle=bundle,
                terminal_success=success,
            )
            if (pre_connect_host_now_utc is None) is not (
                endpoint["application_transport_attempts"] == 0
            ):
                raise PhaseALiveError(
                    "pre-connect time and endpoint attempt state differ"
                )
        except BaseException:
            _validate_indeterminate_checkpoint_file(
                output_path,
                bundle=bundle,
                registry_file=registry_path,
            )
            if error is not None:
                raise error
            raise

        final_temp, temp_creation_identity = _reserve_empty_sink(
            temp_path, label="Phase-A live finalization temp"
        )
        _require_distinct_creation_identities(
            registry_creation_identity,
            output_creation_identity,
            temp_creation_identity,
            label="registry/checkpoint/finalization temp",
        )
        if output_creation_identity["st_dev"] != temp_creation_identity["st_dev"]:
            raise PhaseALiveError(
                "checkpoint and finalization temp are not on one filesystem volume"
            )
        terminal = _receipt_root(
            bundle,
            state=(
                "TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE"
                if success
                else "TERMINAL_FAILURE_NO_RETRY"
            ),
            authorization_sha256=authorization_sha256,
            registry_file=registry_path,
            registry_canonical_sha256=registry_initial["integrity"]["canonical_sha256"],
            registry_whole_file_sha256=registry_sha,
            registry_creation_identity=registry_creation_identity,
            registry_parent_fsync=registry.parent_directory_fsync_status,
            output_parent_fsync=output.parent_directory_fsync_status,
            output_checkpoint_creation_identity=output_creation_identity,
            output_checkpoint_whole_file_bytes=len(checkpoint_payload),
            output_checkpoint_whole_file_sha256=checkpoint_file_sha256,
            output_checkpoint_canonical_sha256=checkpoint["integrity"][
                "canonical_sha256"
            ],
            finalization_temp_creation_identity=temp_creation_identity,
            finalization_temp_parent_fsync=(final_temp.parent_directory_fsync_status),
            execution_observed_now_utc=execution_observed_now_utc,
            pre_registry_host_now_utc=pre_registry_host_now_utc,
            pre_connect_host_now_utc=pre_connect_host_now_utc,
            endpoint=endpoint,
            success=success,
            error=error,
        )
        _prevalidate_terminal_candidate(
            terminal,
            bundle=bundle,
            terminal_success=success,
        )
        terminal_payload = contract.canonical_json_bytes(terminal) + b"\n"
        final_temp.replace(terminal)
        terminal_sha256 = _assert_sink_exact(
            final_temp,
            terminal_payload,
            label="uncommitted finalization temp",
        )
        temp_validation = _validate_terminal_receipt_file(
            temp_path,
            bundle=bundle,
            require_success=success,
            registry_file=registry_path,
            evidence_location="UNCOMMITTED_FINALIZATION_TEMP",
        )
        if temp_validation["terminal_outcome_committed"] is not False:
            raise PhaseALiveError("finalization temp was incorrectly promoted")

        # Windows requires both source and destination handles to be closed.
        # Verify held bytes first, close both, re-snapshot both exact paths,
        # then immediately perform the namespace replace.  This deliberately
        # does not claim an atomic compare-and-swap against a concurrent
        # privileged path replacement; that narrow race is sealed as out of
        # scope in every receipt.
        final_temp.close()
        final_temp = None
        registry.assert_identity()
        output.assert_identity()
        if registry.whole_file_sha256() != registry_sha:
            raise PhaseALiveError("immutable registry changed before final replace")
        if output.whole_file_sha256() != checkpoint_file_sha256:
            raise PhaseALiveError("attempt checkpoint changed before final replace")
        _assert_preloaded_sources_unchanged(bundle)
        output.close()
        checkpoint_snapshot = _snapshot(
            output_path, label="Phase-A live terminal receipt checkpoint"
        )
        if (
            checkpoint_snapshot.sha256 != checkpoint_file_sha256
            or {
                "st_dev": checkpoint_snapshot.device,
                "st_ino": checkpoint_snapshot.inode,
                "st_nlink": 1,
            }
            != output_creation_identity
        ):
            raise PhaseALiveError(
                "attempt checkpoint path identity/bytes changed before final replace"
            )
        temp_snapshot = _snapshot(temp_path, label="Phase-A live finalization temp")
        if (
            temp_snapshot.sha256 != terminal_sha256
            or {
                "st_dev": temp_snapshot.device,
                "st_ino": temp_snapshot.inode,
                "st_nlink": 1,
            }
            != temp_creation_identity
        ):
            raise PhaseALiveError("finalization temp changed before atomic replace")
        os.replace(temp_path, output_path)
        output = None
        if _directory_entry_exists(temp_path):
            raise PhaseALiveError("finalization temp still exists after atomic replace")
        phase_a._fsync_parent_directory(output_path)  # noqa: SLF001
        final_snapshot = _snapshot(output_path, label="Phase-A live terminal receipt")
        if (
            final_snapshot.sha256 != terminal_sha256
            or {
                "st_dev": final_snapshot.device,
                "st_ino": final_snapshot.inode,
                "st_nlink": 1,
            }
            != temp_creation_identity
        ):
            raise PhaseALiveError("atomic final receipt bytes/creation identity differ")
        validation = _validate_terminal_receipt_file(
            output_path,
            bundle=bundle,
            require_success=success,
            registry_file=registry_path,
            evidence_location="COMMITTED_TERMINAL_OUTPUT",
        )
        if validation["terminal_success"] is not success:
            raise PhaseALiveError("persisted terminal receipt state differs")
        return terminal
    finally:
        if final_temp is not None:
            final_temp.close()
        if output is not None:
            output.close()
        registry.close()


def execute_phase_a_live_once(
    envelope_file: Path, *, authorization: str
) -> dict[str, Any]:
    """Public one-shot executor; it has no injectable network or clock surface."""

    bundle = _load_live_bundle(
        envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=False,
    )
    return _execute_loaded_bundle(
        bundle,
        authorization=authorization,
        synthetic_now=None,
        clock=_SystemUTCClock(),
        synthetic_transport=None,
    )


def _execute_phase_a_synthetic_test_only(
    authority_file: Path,
    *,
    authorization: str,
    now: str,
    clock: _ScriptedUTCClock,
    transport: _BuiltInScriptedTestTransport,
    _preloaded_bundle: _LiveBundle | None = None,
) -> dict[str, Any]:
    """Private exact-type harness.  It cannot produce a live receipt kind."""

    bundle = _preloaded_bundle or _load_live_bundle(
        authority_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=True,
    )
    if not bundle.synthetic_test_only:
        raise PhaseALiveError("private synthetic executor rejects live envelopes")
    if bundle.envelope_path != phase_a._safe_absolute(  # noqa: SLF001
        authority_file, label="synthetic Phase-A envelope"
    ):
        raise PhaseALiveError("preloaded synthetic envelope path differs")
    return _execute_loaded_bundle(
        bundle,
        authorization=authorization,
        synthetic_now=now,
        clock=clock,
        synthetic_transport=transport,
    )


def _validate_registry_file(
    registry_file: Path,
    *,
    bundle: _LiveBundle,
    expected_authorization_sha256: str | None = None,
) -> tuple[Mapping[str, Any], bytes, dict[str, Any]]:
    resolved, payload, root = _read_strict_json(
        registry_file, label="Phase-A live attempt registry"
    )
    _require_canonical_artifact_bytes(
        payload, root, label="Phase-A live attempt registry"
    )
    _validate_seal(root, label="Phase-A live attempt registry")
    expected_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(bundle.envelope["attempt"]["registry_file"])),
        label="Phase-A live registry",
    )
    if resolved != expected_path:
        raise PhaseALiveError("Phase-A live registry path differs")
    authorization_sha256 = root.get("authorization_phrase_sha256")
    if (
        type(authorization_sha256) is not str
        or HEX64.fullmatch(authorization_sha256) is None
    ):
        raise PhaseALiveError("registry authorization hash differs")
    expected_phrase = _authorization_phrase(
        bundle.envelope,
        envelope_file_sha256=str(bundle.envelope_binding["sha256"]),
    )
    expected_phrase_sha256 = contract.sha256(expected_phrase.encode("ascii"))
    if authorization_sha256 != expected_phrase_sha256:
        raise PhaseALiveError("registry does not bind the exact required authorization")
    if (
        expected_authorization_sha256 is not None
        and authorization_sha256 != expected_authorization_sha256
    ):
        raise PhaseALiveError("registry authorization hash binding differs")
    pre_registry_time = root.get("pre_registry_system_utc")
    if type(pre_registry_time) is not str:
        raise PhaseALiveError("registry pre-registry system UTC differs")
    observed = _parse_canonical_utc_text(
        pre_registry_time, label="registry pre-registry system UTC"
    )
    _gate_time(
        bundle.authority,
        now=observed,
        label="registry pre-registry system UTC",
    )
    creation_identity = _validate_creation_identity(
        root.get("creation_identity"), label="registry creation identity"
    )
    expected = _registry_record(
        bundle,
        authorization_sha256=authorization_sha256,
        pre_registry_host_now_utc=pre_registry_time,
        creation_identity=creation_identity,
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(expected):
        raise PhaseALiveError("Phase-A live registry exact record differs")
    snapshot = _snapshot(resolved, label="Phase-A live attempt registry")
    if snapshot.size != len(payload) or snapshot.sha256 != contract.sha256(payload):
        raise PhaseALiveError("registry changed between parse and snapshot")
    if creation_identity != {
        "st_dev": snapshot.device,
        "st_ino": snapshot.inode,
        "st_nlink": 1,
    }:
        raise PhaseALiveError("registry no longer has its O_EXCL creation identity")
    return (
        root,
        payload,
        {
            "path": str(resolved),
            "bytes": len(payload),
            "sha256": snapshot.sha256,
            "canonical_sha256": root["integrity"]["canonical_sha256"],
            "authorization_phrase_sha256": authorization_sha256,
            "creation_identity": creation_identity,
            "_device": snapshot.device,
            "_inode": snapshot.inode,
        },
    )


def validate_phase_a_live_attempt_registry(
    registry_file: Path, *, live_envelope_file: Path
) -> dict[str, Any]:
    """Strictly validate an immutable production registry marker."""

    bundle = _load_live_bundle(
        live_envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=False,
    )
    _, _, binding = _validate_registry_file(registry_file, bundle=bundle)
    return {
        "valid": True,
        "kind": LIVE_REGISTRY_KIND,
        "live_attempt_id": bundle.envelope["attempt"]["live_attempt_id"],
        "whole_file_sha256": binding["sha256"],
        "immutable_attempt_consumed": True,
        "terminal_outcome_proven_by_registry_alone": False,
    }


def _validate_optional_evidence_bundle(
    endpoint: Mapping[str, Any],
    *,
    base_name: str,
    maximum: int,
) -> bytes:
    length = endpoint[f"{base_name}_bytes"]
    sha256 = endpoint[f"{base_name}_sha256"]
    encoded = endpoint[f"{base_name}_base64"]
    if type(length) is not int or length < 0 or length > maximum:
        raise PhaseALiveError(f"{base_name} byte length type/bounds differ")
    if length == 0:
        if sha256 is not None or encoded is not None:
            raise PhaseALiveError(f"{base_name} zero-length bundle has orphan evidence")
        return b""
    return _decode_evidence_base64(
        value=encoded,
        length=length,
        sha256=sha256,
        label=base_name,
        maximum=maximum,
    )


def _validate_endpoint_evidence(
    endpoint: Mapping[str, Any],
    *,
    bundle: _LiveBundle,
    terminal_success: bool,
) -> None:
    expected_keys = set(_new_endpoint(synthetic_test_only=bundle.synthetic_test_only))
    if set(endpoint) != expected_keys:
        raise PhaseALiveError("terminal endpoint exact key set differs")
    exact_static = {
        "ordinal": 1,
        "name": "version",
        "method": "GET",
        "path": VERSION_PATH,
        "absolute_url": ABSOLUTE_URL,
        "attempt_checkpoint_persisted_before_socket": True,
        "request_bytes_expected": len(REQUEST_WIRE_BYTES),
        "request_wire_sha256": contract.sha256(REQUEST_WIRE_BYTES),
        "request_wire_base64": base64.b64encode(REQUEST_WIRE_BYTES).decode("ascii"),
        "validation_stack": [
            "raw_http_status_header_and_content_length_gate",
            "strict_utf8_duplicate_nan_trailing_root_gate",
            "source_pinned_exact_v10_version_surface",
        ],
        "kernel_tcp_retransmission_possible": not bundle.synthetic_test_only,
    }
    for key, value in exact_static.items():
        if not _strict_json_equal(endpoint.get(key), value):
            raise PhaseALiveError(f"terminal endpoint {key} differs")
    if type(endpoint["application_transport_attempts"]) is not int or endpoint[
        "application_transport_attempts"
    ] not in {0, 1}:
        raise PhaseALiveError("application transport attempt count differs")
    for key in (
        "socket_constructor_called",
        "socket_connect_called",
        "socket_connect_returned",
        "request_write_called",
        "request_write_completed",
        "bounded_response_prefix_truncated",
    ):
        if type(endpoint[key]) is not bool:
            raise PhaseALiveError(f"terminal endpoint {key} type differs")
    handed = endpoint["request_bytes_handed_to_socket_api"]
    if type(handed) is not int or handed < 0 or handed > len(REQUEST_WIRE_BYTES):
        raise PhaseALiveError("request handed-to-socket byte count differs")
    if endpoint["request_write_completed"] is not (handed == len(REQUEST_WIRE_BYTES)):
        raise PhaseALiveError("request completion and byte count differ")

    gate_order = {
        "ATTEMPT_CHECKPOINT_PERSISTED": 0,
        "SOCKET_CONSTRUCTOR_CALLED": 1,
        "CONNECT_CALLED": 2,
        "CONNECTED": 3,
        "REQUEST_WRITE_STARTED": 4,
        "REQUEST_WRITE_COMPLETED": 5,
        "STATUS_HEADERS_RECEIVED": 6,
        "HTTP_ENVELOPE_VALIDATED": 7,
        "RESPONSE_ENTITY_RECEIVED": 8,
        "EXACT_V10_VALIDATED": 9,
    }
    gate = endpoint["last_completed_gate"]
    if type(gate) is not str or gate not in gate_order:
        raise PhaseALiveError("terminal endpoint gate differs")
    rank = gate_order[gate]
    if terminal_success:
        if endpoint["failure_stage"] is not None:
            raise PhaseALiveError("terminal success has a failure stage")
    elif endpoint["failure_stage"] != _failure_stage(endpoint):
        raise PhaseALiveError("failure stage is not reachable from the last gate")
    if not terminal_success and rank == 9:
        raise PhaseALiveError("exact V10 validation cannot be relabeled failure")

    attempts = endpoint["application_transport_attempts"]
    if attempts != (0 if rank == 0 else 1):
        raise PhaseALiveError("transport attempt count and last gate differ")
    if bundle.synthetic_test_only:
        if rank not in {0, 5, 6, 7, 8, 9}:
            raise PhaseALiveError("synthetic endpoint entered a live-only socket gate")
        expected_flags = {
            "socket_constructor_called": False,
            "socket_connect_called": False,
            "socket_connect_returned": False,
            "request_write_called": rank >= 5,
            "request_write_completed": rank >= 5,
        }
    else:
        expected_flags = {
            "socket_constructor_called": rank >= 1,
            "socket_connect_called": rank >= 2,
            "socket_connect_returned": rank >= 3,
            "request_write_called": rank >= 4,
            "request_write_completed": rank >= 5,
        }
    for key, expected in expected_flags.items():
        if endpoint[key] is not expected:
            raise PhaseALiveError(f"{key} is unreachable for the recorded gate")
    if rank < 4 and handed != 0:
        raise PhaseALiveError("request bytes exist before the write gate")
    if rank == 4 and handed >= len(REQUEST_WIRE_BYTES):
        raise PhaseALiveError("partial request gate contains a complete request")
    if rank >= 5 and handed != len(REQUEST_WIRE_BYTES):
        raise PhaseALiveError("post-write gate lacks the complete request bytes")
    expected_wire = (
        "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
        if bundle.synthetic_test_only
        else "UNKNOWN"
    )
    if (
        endpoint["request_wire_emitted"] != expected_wire
        or endpoint["peer_received_request"] != expected_wire
    ):
        raise PhaseALiveError("wire emission/peer receipt proof boundary differs")

    prefix = _validate_optional_evidence_bundle(
        endpoint,
        base_name="bounded_response_prefix",
        maximum=MAX_BOUNDED_RESPONSE_PREFIX_BYTES,
    )
    observed_total = endpoint["observed_response_octets_total"]
    if type(observed_total) is not int or observed_total < len(prefix):
        raise PhaseALiveError("observed response octet count differs")
    if endpoint["bounded_response_prefix_truncated"]:
        raise PhaseALiveError(
            "response prefix truncation is unreachable under exact caps"
        )
    if observed_total != len(prefix):
        raise PhaseALiveError("observed response count and bounded prefix differ")
    if rank < 5 and prefix:
        raise PhaseALiveError("response evidence exists before request completion")

    raw_length = endpoint["raw_status_and_header_bytes"]
    raw_sha = endpoint["raw_status_and_header_sha256"]
    raw_b64 = endpoint["raw_status_and_header_base64"]
    raw_headers = b""
    parsed_http: _ParsedHTTPEnvelope | None = None
    if raw_length is None:
        if raw_sha is not None or raw_b64 is not None:
            raise PhaseALiveError("raw status/header evidence has orphan fields")
        if rank >= 6:
            raise PhaseALiveError(
                "post-status-header gate lacks raw status/header evidence"
            )
        if rank == 5 and (
            len(prefix) > MAX_STATUS_HEADER_BYTES or b"\r\n\r\n" in prefix
        ):
            raise PhaseALiveError(
                "pre-header-completion prefix is unreachable for the read gate"
            )
    else:
        if rank <= 5:
            raise PhaseALiveError(
                "raw status/header evidence exists before its receive gate"
            )
        raw_headers = _decode_evidence_base64(
            value=raw_b64,
            length=raw_length,
            sha256=raw_sha,
            label="raw status and headers",
            maximum=MAX_STATUS_HEADER_BYTES,
        )
        first_delimiter = raw_headers.find(b"\r\n\r\n")
        if len(raw_headers) < 4 or first_delimiter != len(raw_headers) - 4:
            raise PhaseALiveError(
                "raw status/header evidence does not end at its first delimiter"
            )
        if not prefix.startswith(raw_headers):
            raise PhaseALiveError("raw status/header bytes differ from response prefix")
        if rank < 7:
            if rank == 6 and len(prefix) > MAX_STATUS_HEADER_BYTES:
                raise PhaseALiveError(
                    "failed HTTP envelope prefix exceeds the reachable parser read"
                )
            try:
                _parse_status_and_headers(raw_headers)
            except PhaseALiveTransportError:
                pass
            else:
                raise PhaseALiveError(
                    "valid HTTP envelope cannot remain before its validation gate"
                )
            if (
                endpoint["http_status"] is not None
                or endpoint["response_headers"] is not None
            ):
                raise PhaseALiveError("failed HTTP envelope has parsed fields")
        else:
            parsed_http = _parse_status_and_headers(raw_headers)
            if endpoint["http_status"] != parsed_http.status or endpoint[
                "response_headers"
            ] != [list(item) for item in parsed_http.headers]:
                raise PhaseALiveError("parsed HTTP evidence differs")
    if raw_length is None and (
        endpoint["http_status"] is not None or endpoint["response_headers"] is not None
    ):
        raise PhaseALiveError("parsed HTTP fields exist without raw evidence")

    partial_entity = _validate_optional_evidence_bundle(
        endpoint,
        base_name="partial_response_entity",
        maximum=MAX_VERSION_ENTITY_BYTES,
    )
    beyond_content_length = _validate_optional_evidence_bundle(
        endpoint,
        base_name="beyond_content_length",
        maximum=MAX_BEYOND_CONTENT_LENGTH_EVIDENCE_BYTES,
    )
    explained_prefix = raw_headers + partial_entity + beyond_content_length
    if raw_headers and not prefix.startswith(explained_prefix):
        raise PhaseALiveError("partial entity differs from bounded response prefix")
    if rank >= 7 and prefix != explained_prefix:
        raise PhaseALiveError("post-HTTP response prefix has unexplained bytes")
    if rank < 7 and partial_entity:
        raise PhaseALiveError("partial entity exists before HTTP envelope validation")
    if rank < 7 and beyond_content_length:
        raise PhaseALiveError("overlong entity evidence exists before HTTP validation")
    if beyond_content_length and rank != 7:
        raise PhaseALiveError("overlong entity evidence has an unreachable gate")
    if parsed_http is not None and len(partial_entity) > parsed_http.content_length:
        raise PhaseALiveError("partial entity exceeds the parsed Content-Length")
    if (
        beyond_content_length
        and parsed_http is not None
        and len(partial_entity) != parsed_http.content_length
    ):
        raise PhaseALiveError(
            "overlong evidence exists before the complete Content-Length entity"
        )
    body_length = endpoint["response_entity_body_bytes"]
    body_sha = endpoint["response_entity_body_sha256"]
    body_b64 = endpoint["response_entity_body_base64"]
    body: bytes | None = None
    if body_length is None:
        if body_sha is not None or body_b64 is not None:
            raise PhaseALiveError("complete entity evidence has orphan fields")
    else:
        body = _decode_evidence_base64(
            value=body_b64,
            length=body_length,
            sha256=body_sha,
            label="complete response entity",
            maximum=MAX_VERSION_ENTITY_BYTES,
        )
        if body != partial_entity:
            raise PhaseALiveError("complete and partial entity evidence differs")
        if parsed_http is None or parsed_http.content_length != len(body):
            raise PhaseALiveError("HTTP Content-Length and entity evidence differ")

    parsed_sha = endpoint["strict_parsed_canonical_sha256"]
    if parsed_sha is not None and (
        type(parsed_sha) is not str or HEX64.fullmatch(parsed_sha) is None
    ):
        raise PhaseALiveError("strict parsed canonical SHA differs")
    if terminal_success:
        if (
            endpoint["last_completed_gate"] != "EXACT_V10_VALIDATED"
            or endpoint["failure_stage"] is not None
            or endpoint["validation_outcome"] != "PASS"
            or endpoint["application_transport_attempts"] != 1
            or not endpoint["request_write_completed"]
            or body is None
            or parsed_sha is None
            or parsed_http is None
            or endpoint["bounded_response_prefix_truncated"]
            or beyond_content_length
        ):
            raise PhaseALiveError("terminal success endpoint state differs")
        if prefix != raw_headers + body or observed_total != len(raw_headers) + len(
            body
        ):
            raise PhaseALiveError("terminal success raw response prefix differs")
        parsed, _ = facade.decode_and_validate_v10_response_bytes(
            "version", body, bundle.v10_context
        )
        if contract.sha256(parsed) != parsed_sha:
            raise PhaseALiveError("terminal success parsed SHA differs")
    else:
        if (
            endpoint["validation_outcome"] != "FAILED_TERMINAL_NO_RETRY"
            or parsed_sha is not None
        ):
            raise PhaseALiveError("terminal failure endpoint state differs")
        if rank >= 8 and body is None:
            raise PhaseALiveError("post-entity failure lacks complete entity evidence")
        if rank < 8 and body is not None:
            raise PhaseALiveError("complete entity exists before its receive gate")
        if body is not None and parsed_http is not None:
            try:
                facade.decode_and_validate_v10_response_bytes(
                    "version", body, bundle.v10_context
                )
            except (facade.StageBFacadeContractError, ValueError, RecursionError):
                pass
            else:
                raise PhaseALiveError(
                    "valid exact V10 response cannot be relabeled terminal failure"
                )


def _validate_terminal_receipt_file(
    receipt_file: Path,
    *,
    bundle: _LiveBundle,
    require_success: bool | None,
    registry_file: Path,
    evidence_location: str = "COMMITTED_TERMINAL_OUTPUT",
) -> dict[str, Any]:
    resolved, payload, root = _read_strict_json(
        receipt_file, label="Phase-A live terminal receipt"
    )
    _require_canonical_artifact_bytes(
        payload, root, label="Phase-A live terminal receipt"
    )
    receipt_snapshot = _snapshot(resolved, label="Phase-A live terminal receipt")
    if receipt_snapshot.size != len(
        payload
    ) or receipt_snapshot.sha256 != contract.sha256(payload):
        raise PhaseALiveError("terminal receipt changed between parse and snapshot")
    if len(payload) > MAX_TERMINAL_RECEIPT_BYTES:
        raise PhaseALiveError("terminal receipt exceeds strict loader byte budget")
    canonical = _validate_seal(root, label="Phase-A live terminal receipt")
    location_fields = {
        "COMMITTED_TERMINAL_OUTPUT": "terminal_receipt_file",
        "UNCOMMITTED_FINALIZATION_TEMP": "finalization_temp_file",
    }
    if evidence_location not in location_fields:
        raise PhaseALiveError("terminal evidence location differs")
    expected_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(bundle.envelope["attempt"][location_fields[evidence_location]])),
        label="Phase-A live terminal evidence path",
    )
    if resolved != expected_path:
        raise PhaseALiveError("terminal receipt path differs")
    success_state = "TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE"
    failure_state = "TERMINAL_FAILURE_NO_RETRY"
    if root.get("state") not in {success_state, failure_state}:
        raise PhaseALiveError("receipt is not a sealed terminal outcome")
    terminal_success = root["state"] == success_state
    if require_success is not None and terminal_success is not require_success:
        raise PhaseALiveError("terminal receipt success requirement differs")
    if root.get("synthetic_test_only") is not bundle.synthetic_test_only:
        raise PhaseALiveError("terminal receipt synthetic boundary differs")

    dummy = _receipt_root(
        bundle,
        state=failure_state,
        authorization_sha256="0" * 64,
        registry_file=registry_file,
        registry_canonical_sha256="0" * 64,
        registry_whole_file_sha256="0" * 64,
        registry_creation_identity={"st_dev": 0, "st_ino": 0, "st_nlink": 1},
        registry_parent_fsync="DUMMY",
        output_parent_fsync="DUMMY",
        output_checkpoint_creation_identity={
            "st_dev": 0,
            "st_ino": 0,
            "st_nlink": 1,
        },
        output_checkpoint_whole_file_bytes=1,
        output_checkpoint_whole_file_sha256="0" * 64,
        output_checkpoint_canonical_sha256="0" * 64,
        finalization_temp_creation_identity={
            "st_dev": 0,
            "st_ino": 0,
            "st_nlink": 1,
        },
        finalization_temp_parent_fsync="DUMMY",
        execution_observed_now_utc="2026-08-15T00:00:00Z",
        pre_registry_host_now_utc="2026-08-15T00:00:00Z",
        pre_connect_host_now_utc=None,
        endpoint=None,
        success=False,
        error=PhaseALiveError("dummy"),
    )
    if set(root) != set(dummy):
        raise PhaseALiveError("terminal receipt exact root key set differs")
    expected_kind = (
        SYNTHETIC_RECEIPT_KIND if bundle.synthetic_test_only else LIVE_RECEIPT_KIND
    )
    expected_classification = (
        "SYNTHETIC_TEST_ONLY_TERMINAL_RECEIPT_NEVER_PHASE_B_ELIGIBLE"
        if bundle.synthetic_test_only
        else "PHASE_A_LIVE_TERMINAL_RECEIPT_PROTOCOL_CONFORMANCE_ONLY"
    )
    exact_values = {
        "schema_version": SCHEMA_VERSION,
        "kind": expected_kind,
        "classification": expected_classification,
        "live_envelope_binding": dict(bundle.envelope_binding),
        "offline_authority_binding": dict(bundle.authority_binding),
        "live_envelope_id": bundle.envelope["live_envelope_id"],
        "live_attempt_id": bundle.envelope["attempt"]["live_attempt_id"],
        "offline_attempt_id": bundle.envelope["attempt"]["offline_attempt_id"],
        "authorization_phrase_stored": False,
        "onsite_gate_canonical_sha256": bundle.authority["fresh_phase_a_onsite_gate"][
            "gate_canonical_sha256"
        ],
        "attempt_registry_file": str(
            phase_a._safe_absolute(  # noqa: SLF001
                registry_file, label="Phase-A live attempt registry"
            )
        ),
        "registry_is_immutable_o_excl_marker": True,
        "output_checkpoint_identity_and_hash_are_finalization_preconditions": True,
        "output_checkpoint_creation_identity_is_runtime_evidence_not_post_replace_replay_proof": True,
        "terminal_receipt_file": bundle.envelope["attempt"]["terminal_receipt_file"],
        "finalization_temp_file": bundle.envelope["attempt"]["finalization_temp_file"],
        "terminalization_policy_requires_temp_o_excl_then_atomic_replace": True,
        "atomic_replace_required_before_receipt_is_committed": True,
        "payload_does_not_self_assert_atomic_replace_commit": True,
        "atomic_compare_and_swap_proven": False,
        "concurrent_privileged_destination_replacement_between_final_check_and_replace": (
            "OUT_OF_SCOPE_NOT_PROVEN"
        ),
        "concurrent_privileged_parent_path_replacement": "OUT_OF_SCOPE_NOT_PROVEN",
        "post_replace_parent_directory_fsync_result_is_not_embedded": True,
        "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        "maximum_application_transport_attempts": 1,
        "post_requests": 0,
        "request_bodies": 0,
        "device_api_claim_requests": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "dns_proxy_redirect_scan_fallback_or_application_retry_requests": 0,
        "serial_or_com_accesses": 0,
        "retry_allowed": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "original_plan_final_output_touched": False,
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_post_reset_application_boot_proven": False,
        "active_application_or_ota_slot_proven": False,
        "phase_b_authority_generated": False,
        "phase_b_authorization_generated": False,
        "phase_b_requests": 0,
        "eligible_for_direct_phase_b_execution": False,
        "synthetic_receipt_never_phase_b_eligible": bundle.synthetic_test_only,
        "version_protocol_response_conformance": terminal_success,
        "may_request_separate_phase_b_authority": False,
        "may_request_separate_phase_b_authority_only_after_committed_final_path_validation": (
            terminal_success and not bundle.synthetic_test_only
        ),
        "actual_device_or_background_side_effects": (
            "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
            if bundle.synthetic_test_only
            else "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
        ),
    }
    for key, value in exact_values.items():
        if not _strict_json_equal(root.get(key), value):
            raise PhaseALiveError(f"terminal receipt {key} differs")
    authorization_hash = root["authorization_phrase_sha256"]
    if (
        type(authorization_hash) is not str
        or HEX64.fullmatch(authorization_hash) is None
    ):
        raise PhaseALiveError("terminal receipt authorization hash differs")
    registry_root, registry_payload, registry_binding = _validate_registry_file(
        registry_file,
        bundle=bundle,
        expected_authorization_sha256=authorization_hash,
    )
    if (
        root["registry_initial_canonical_sha256"]
        != registry_root["integrity"]["canonical_sha256"]
        or root["registry_whole_file_sha256"] != contract.sha256(registry_payload)
        or root["registry_whole_file_sha256"] != registry_binding["sha256"]
        or not _strict_json_equal(
            root["registry_creation_identity"],
            registry_binding["creation_identity"],
        )
    ):
        raise PhaseALiveError("terminal receipt registry whole-file binding differs")
    checkpoint_identity = _validate_creation_identity(
        root["output_checkpoint_creation_identity"],
        label="output checkpoint creation identity",
    )
    checkpoint_sha256 = root["output_checkpoint_whole_file_sha256"]
    checkpoint_bytes = root["output_checkpoint_whole_file_bytes"]
    checkpoint_canonical = root["output_checkpoint_canonical_sha256"]
    if (
        type(checkpoint_bytes) is not int
        or checkpoint_bytes <= 0
        or checkpoint_bytes > MAX_TERMINAL_RECEIPT_BYTES
        or type(checkpoint_sha256) is not str
        or HEX64.fullmatch(checkpoint_sha256) is None
        or type(checkpoint_canonical) is not str
        or HEX64.fullmatch(checkpoint_canonical) is None
    ):
        raise PhaseALiveError("terminal receipt checkpoint binding differs")
    reconstructed_checkpoint = _checkpoint_receipt(
        bundle,
        authorization_sha256=authorization_hash,
        registry_file=phase_a._safe_absolute(  # noqa: SLF001
            registry_file, label="Phase-A live attempt registry"
        ),
        registry_canonical_sha256=registry_root["integrity"]["canonical_sha256"],
        registry_whole_file_sha256=contract.sha256(registry_payload),
        registry_creation_identity=registry_binding["creation_identity"],
        registry_parent_fsync=root["registry_parent_directory_fsync_status"],
        output_parent_fsync=root["output_parent_directory_fsync_status"],
        output_checkpoint_creation_identity=checkpoint_identity,
        execution_observed_now_utc=root["execution_observed_now_utc"],
        pre_registry_host_now_utc=root["pre_registry_host_now_utc"],
        endpoint=_new_endpoint(synthetic_test_only=bundle.synthetic_test_only),
        state=(
            "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
            "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
        ),
    )
    reconstructed_payload = (
        contract.canonical_json_bytes(reconstructed_checkpoint) + b"\n"
    )
    if (
        checkpoint_bytes != len(reconstructed_payload)
        or checkpoint_sha256 != contract.sha256(reconstructed_payload)
        or checkpoint_canonical
        != reconstructed_checkpoint["integrity"]["canonical_sha256"]
    ):
        raise PhaseALiveError(
            "terminal receipt does not bind the unique reconstructed checkpoint"
        )
    if evidence_location == "UNCOMMITTED_FINALIZATION_TEMP":
        checkpoint_snapshot = _snapshot(
            Path(str(bundle.envelope["attempt"]["terminal_receipt_file"])),
            label="Phase-A live terminal receipt checkpoint",
        )
        if (
            checkpoint_snapshot.sha256 != checkpoint_sha256
            or {
                "st_dev": checkpoint_snapshot.device,
                "st_ino": checkpoint_snapshot.inode,
                "st_nlink": 1,
            }
            != checkpoint_identity
        ):
            raise PhaseALiveError(
                "uncommitted finalization temp checkpoint binding differs"
            )
    finalization_identity = _validate_creation_identity(
        root["finalization_temp_creation_identity"],
        label="finalization temp creation identity",
    )
    _require_distinct_creation_identities(
        registry_binding["creation_identity"],
        checkpoint_identity,
        finalization_identity,
        label="registry/checkpoint/finalization temp",
    )
    if checkpoint_identity["st_dev"] != finalization_identity["st_dev"]:
        raise PhaseALiveError(
            "checkpoint and finalization temp creation volumes differ"
        )
    if finalization_identity != {
        "st_dev": receipt_snapshot.device,
        "st_ino": receipt_snapshot.inode,
        "st_nlink": 1,
    }:
        raise PhaseALiveError(
            "terminal evidence no longer has the finalization temp creation identity"
        )
    if root["pre_registry_host_now_utc"] != registry_root["pre_registry_system_utc"]:
        raise PhaseALiveError("receipt and immutable registry time binding differs")
    for time_field in (
        "execution_observed_now_utc",
        "pre_registry_host_now_utc",
        "pre_connect_host_now_utc",
    ):
        value = root[time_field]
        if value is None:
            if time_field != "pre_connect_host_now_utc":
                raise PhaseALiveError(f"terminal receipt lacks {time_field}")
            if terminal_success:
                raise PhaseALiveError("terminal success lacks pre-connect time")
            continue
        observed = _parse_canonical_utc_text(value, label=f"receipt {time_field}")
        _gate_time(bundle.authority, now=observed, label=f"receipt {time_field}")
    if not bundle.synthetic_test_only and (
        root["execution_observed_now_utc"] != root["pre_registry_host_now_utc"]
    ):
        raise PhaseALiveError(
            "production execution observed UTC differs from pre-registry host UTC"
        )
    if (
        type(root["endpoint_outcomes"]) is not list
        or len(root["endpoint_outcomes"]) != 1
        or type(root["endpoint_outcomes"][0]) is not dict
    ):
        raise PhaseALiveError("terminal receipt endpoint outcomes differ")
    _validate_endpoint_evidence(
        root["endpoint_outcomes"][0],
        bundle=bundle,
        terminal_success=terminal_success,
    )
    endpoint = root["endpoint_outcomes"][0]
    aggregate_counts = {
        "application_transport_attempts": endpoint["application_transport_attempts"],
        "request_write_calls": 1 if endpoint["request_write_called"] else 0,
        "request_bytes_handed_to_socket_api": endpoint[
            "request_bytes_handed_to_socket_api"
        ],
        "fully_written_version_gets": (1 if endpoint["request_write_completed"] else 0),
        "http_responses_with_complete_status_headers": (
            1 if endpoint["raw_status_and_header_bytes"] is not None else 0
        ),
    }
    for key, value in aggregate_counts.items():
        if root[key] != value or type(root[key]) is not int:
            raise PhaseALiveError(f"terminal receipt aggregate {key} differs")
    if (root["pre_connect_host_now_utc"] is None) is not (
        endpoint["application_transport_attempts"] == 0
    ):
        raise PhaseALiveError("pre-connect time and transport attempt state differ")
    if terminal_success and (
        root["application_transport_attempts"] != 1
        or root["request_write_calls"] != 1
        or root["fully_written_version_gets"] != 1
        or root["http_responses_with_complete_status_headers"] != 1
    ):
        raise PhaseALiveError("terminal success exact request/response counts differ")
    if terminal_success:
        if root["error_type"] is not None or root["error"] is not None:
            raise PhaseALiveError("terminal success contains error evidence")
    elif (
        type(root["error_type"]) is not str
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", root["error_type"]) is None
        or type(root["error"]) is not str
        or not root["error"]
    ):
        raise PhaseALiveError("terminal failure lacks bounded error evidence")
    allowed_fsync = {
        "UNAVAILABLE_ON_THIS_PLATFORM_NOT_POWER_LOSS_DURABILITY_PROOF",
        "ATTEMPTED_FAILED_NOT_POWER_LOSS_DURABILITY_PROOF",
        "ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF",
    }
    if (
        root["registry_parent_directory_fsync_status"] not in allowed_fsync
        or root["output_parent_directory_fsync_status"] not in allowed_fsync
        or root["finalization_temp_parent_directory_fsync_status"] not in allowed_fsync
    ):
        raise PhaseALiveError("receipt directory fsync status differs")
    if (
        root["error"] is not None
        and len(root["error"].encode("utf-8")) > MAX_ERROR_TEXT_BYTES
    ):
        raise PhaseALiveError("terminal error evidence exceeds byte budget")
    receipt_snapshot.assert_unchanged()
    registry_end = _snapshot(registry_file, label="Phase-A live attempt registry")
    if (
        registry_end.sha256 != registry_binding["sha256"]
        or registry_end.size != registry_binding["bytes"]
        or registry_end.device != registry_binding["_device"]
        or registry_end.inode != registry_binding["_inode"]
    ):
        raise PhaseALiveError("registry identity or bytes changed during replay")
    _assert_preloaded_sources_unchanged(bundle)
    if evidence_location == "COMMITTED_TERMINAL_OUTPUT":
        finalization_temp_path = phase_a._safe_absolute(  # noqa: SLF001
            Path(str(bundle.envelope["attempt"]["finalization_temp_file"])),
            label="Phase-A live finalization temp",
        )
        if _directory_entry_exists(finalization_temp_path):
            raise PhaseALiveError(
                "committed terminal output has a surviving finalization temp entry"
            )
    return {
        "valid": True,
        "terminal_success": terminal_success,
        "terminal_outcome_committed": (
            evidence_location == "COMMITTED_TERMINAL_OUTPUT"
        ),
        "evidence_location": evidence_location,
        "synthetic_test_only": bundle.synthetic_test_only,
        "kind": expected_kind,
        "canonical_sha256": canonical,
        "whole_file_sha256": contract.sha256(payload),
        "version_protocol_response_conformance": terminal_success,
        "responder_or_device_identity_proven": False,
        "fresh_boot_or_active_application_proven": False,
        "phase_b_generated_or_executed": False,
        "may_request_separate_phase_b_authority": (
            terminal_success
            and not bundle.synthetic_test_only
            and evidence_location == "COMMITTED_TERMINAL_OUTPUT"
        ),
    }


def validate_phase_a_live_terminal_receipt(
    receipt_file: Path,
    *,
    live_envelope_file: Path,
    require_success: bool | None = None,
) -> dict[str, Any]:
    """Strictly replay a production receipt and its immutable registry."""

    bundle = _load_live_bundle(
        live_envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=False,
    )
    return _validate_terminal_receipt_file(
        receipt_file,
        bundle=bundle,
        require_success=require_success,
        registry_file=Path(str(bundle.envelope["attempt"]["registry_file"])),
    )


def validate_phase_a_live_uncommitted_finalization_temp(
    temp_file: Path,
    *,
    live_envelope_file: Path,
) -> dict[str, Any]:
    """Audit an orphaned final temp without treating it as a committed outcome."""

    bundle = _load_live_bundle(
        live_envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=False,
    )
    summary = _validate_terminal_receipt_file(
        temp_file,
        bundle=bundle,
        require_success=None,
        registry_file=Path(str(bundle.envelope["attempt"]["registry_file"])),
        evidence_location="UNCOMMITTED_FINALIZATION_TEMP",
    )
    if summary["terminal_outcome_committed"]:
        raise PhaseALiveError("finalization temp cannot be a committed outcome")
    return {
        **summary,
        "attempt_permanently_consumed": True,
        "terminal_outcome": "INDETERMINATE_PREPARED_NOT_ATOMICALLY_COMMITTED",
        "retry_allowed": False,
        "phase_b_eligible": False,
    }


def _validate_indeterminate_checkpoint_file(
    receipt_file: Path,
    *,
    bundle: _LiveBundle,
    registry_file: Path,
) -> dict[str, Any]:
    """Replay a crash checkpoint without promoting it to terminal success."""

    resolved, payload, root = _read_strict_json(
        receipt_file, label="Phase-A live indeterminate checkpoint"
    )
    _require_canonical_artifact_bytes(
        payload, root, label="Phase-A live indeterminate checkpoint"
    )
    snapshot = _snapshot(resolved, label="Phase-A live indeterminate checkpoint")
    if snapshot.size != len(payload) or snapshot.sha256 != contract.sha256(payload):
        raise PhaseALiveError("indeterminate checkpoint changed during parse")
    _validate_seal(root, label="Phase-A live indeterminate checkpoint")
    expected_path = phase_a._safe_absolute(  # noqa: SLF001
        Path(str(bundle.envelope["attempt"]["terminal_receipt_file"])),
        label="Phase-A live indeterminate checkpoint",
    )
    if resolved != expected_path:
        raise PhaseALiveError("indeterminate checkpoint path differs")
    states = {
        (
            "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
            "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
        ): True,
    }
    state = root.get("state")
    if state not in states:
        raise PhaseALiveError("receipt is not an exact indeterminate checkpoint")
    authorization_hash = root.get("authorization_phrase_sha256")
    if (
        type(authorization_hash) is not str
        or HEX64.fullmatch(authorization_hash) is None
    ):
        raise PhaseALiveError("checkpoint authorization hash differs")
    registry_root, registry_payload, registry_binding = _validate_registry_file(
        registry_file,
        bundle=bundle,
        expected_authorization_sha256=authorization_hash,
    )
    pre_registry = root.get("pre_registry_host_now_utc")
    observed_now = root.get("execution_observed_now_utc")
    if type(pre_registry) is not str or type(observed_now) is not str:
        raise PhaseALiveError("checkpoint time evidence differs")
    if pre_registry != registry_root["pre_registry_system_utc"]:
        raise PhaseALiveError("checkpoint and immutable registry time differ")
    for label, value in (
        ("checkpoint pre-registry time", pre_registry),
        ("checkpoint observed execution time", observed_now),
    ):
        _gate_time(
            bundle.authority,
            now=_parse_canonical_utc_text(value, label=label),
            label=label,
        )
    if not bundle.synthetic_test_only and observed_now != pre_registry:
        raise PhaseALiveError(
            "production checkpoint observed UTC differs from pre-registry host UTC"
        )
    checkpoint_has_endpoint = states[str(state)]
    expected_endpoint = (
        _new_endpoint(synthetic_test_only=bundle.synthetic_test_only)
        if checkpoint_has_endpoint
        else None
    )
    expected_output_fsync = (
        root.get("output_parent_directory_fsync_status")
        if checkpoint_has_endpoint
        else "NOT_AVAILABLE_UNTIL_OUTPUT_O_EXCL"
    )
    allowed_fsync = {
        "UNAVAILABLE_ON_THIS_PLATFORM_NOT_POWER_LOSS_DURABILITY_PROOF",
        "ATTEMPTED_FAILED_NOT_POWER_LOSS_DURABILITY_PROOF",
        "ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF",
    }
    if root.get("registry_parent_directory_fsync_status") not in allowed_fsync:
        raise PhaseALiveError("checkpoint registry directory fsync status differs")
    if checkpoint_has_endpoint and expected_output_fsync not in allowed_fsync:
        raise PhaseALiveError("checkpoint output directory fsync status differs")
    output_creation_identity = _validate_creation_identity(
        root.get("output_checkpoint_creation_identity"),
        label="checkpoint output creation identity",
    )
    expected = _checkpoint_receipt(
        bundle,
        authorization_sha256=authorization_hash,
        registry_file=phase_a._safe_absolute(  # noqa: SLF001
            registry_file, label="Phase-A live attempt registry"
        ),
        registry_canonical_sha256=registry_root["integrity"]["canonical_sha256"],
        registry_whole_file_sha256=contract.sha256(registry_payload),
        registry_creation_identity=registry_binding["creation_identity"],
        registry_parent_fsync=str(root.get("registry_parent_directory_fsync_status")),
        output_parent_fsync=str(expected_output_fsync),
        output_checkpoint_creation_identity=output_creation_identity,
        execution_observed_now_utc=observed_now,
        pre_registry_host_now_utc=pre_registry,
        endpoint=expected_endpoint,
        state=str(state),
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(expected):
        raise PhaseALiveError("indeterminate checkpoint exact evidence differs")
    if output_creation_identity != {
        "st_dev": snapshot.device,
        "st_ino": snapshot.inode,
        "st_nlink": 1,
    }:
        raise PhaseALiveError("checkpoint no longer has its O_EXCL creation identity")
    if root["version_protocol_response_conformance"] is not False:
        raise PhaseALiveError("indeterminate checkpoint cannot prove conformance")
    if root["may_request_separate_phase_b_authority"] is not False:
        raise PhaseALiveError("indeterminate checkpoint cannot unlock Phase B")
    snapshot.assert_unchanged()
    registry_end = _snapshot(registry_file, label="Phase-A live attempt registry")
    if (
        registry_end.sha256 != registry_binding["sha256"]
        or registry_end.size != registry_binding["bytes"]
        or registry_end.device != registry_binding["_device"]
        or registry_end.inode != registry_binding["_inode"]
    ):
        raise PhaseALiveError("registry changed during checkpoint replay")
    _assert_preloaded_sources_unchanged(bundle)
    return {
        "valid": True,
        "state": state,
        "terminal_success": False,
        "terminal_failure_finalized": False,
        "attempt_permanently_consumed": True,
        "network_outcome": "UNKNOWN_OR_NOT_STARTED",
        "retry_allowed": False,
        "phase_b_eligible": False,
        "synthetic_test_only": bundle.synthetic_test_only,
        "whole_file_sha256": contract.sha256(payload),
    }


def validate_phase_a_live_receipt_or_checkpoint(
    receipt_file: Path, *, live_envelope_file: Path
) -> dict[str, Any]:
    """Validate production final evidence or either durable crash checkpoint."""

    bundle = _load_live_bundle(
        live_envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=False,
    )
    _, _, root = _read_strict_json(
        receipt_file, label="Phase-A live receipt/checkpoint discriminator"
    )
    if str(root.get("state", "")).startswith("TERMINAL_INDETERMINATE_"):
        return _validate_indeterminate_checkpoint_file(
            receipt_file,
            bundle=bundle,
            registry_file=Path(str(bundle.envelope["attempt"]["registry_file"])),
        )
    return _validate_terminal_receipt_file(
        receipt_file,
        bundle=bundle,
        require_success=None,
        registry_file=Path(str(bundle.envelope["attempt"]["registry_file"])),
    )


def require_live_phase_a_success_for_future_phase_b(
    receipt_file: Path, *, live_envelope_file: Path
) -> dict[str, Any]:
    """Validate Phase-A evidence only; never build or authorize Phase B."""

    summary = validate_phase_a_live_terminal_receipt(
        receipt_file,
        live_envelope_file=live_envelope_file,
        require_success=True,
    )
    if summary["synthetic_test_only"]:
        raise PhaseALiveError("synthetic receipt is never Phase-B eligible")
    if (
        not summary["terminal_outcome_committed"]
        or not summary["may_request_separate_phase_b_authority"]
    ):
        raise PhaseALiveError(
            "only an atomically committed Phase-A success may request Phase B"
        )
    return {
        **summary,
        "may_only_request_separate_phase_b_authority": True,
        "phase_b_authority_generated": False,
        "phase_b_authorization_generated": False,
        "phase_b_executed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Runner-bound one-shot Phase-A /version facade"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare", help="seal a non-executing live envelope"
    )
    prepare.add_argument("--phase-a-authority", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--built-at", required=True)

    validate = subparsers.add_parser(
        "validate", help="deep-validate a production live envelope"
    )
    validate.add_argument("--authority", type=Path, required=True)

    execute = subparsers.add_parser(
        "execute-phase-a-live", help="consume one exact runner-bound authorization"
    )
    execute.add_argument("--authority", type=Path, required=True)
    execute.add_argument("--authorization", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        root = materialize_live_execution_envelope(
            phase_a_authority_file=args.phase_a_authority,
            live_envelope_file=args.output,
            built_at=args.built_at,
        )
        write_new_live_execution_envelope(args.output, root)
        summary = validate_live_execution_envelope(
            root, require_attempt_paths_absent=True
        )
        print(contract.canonical_json_bytes(summary).decode("utf-8"))
        return 0
    if args.command == "validate":
        bundle = _load_live_bundle(
            args.authority,
            require_attempt_paths_absent=True,
            allow_synthetic_test_only=False,
        )
        summary = {
            "valid": True,
            "live_envelope_id": bundle.envelope["live_envelope_id"],
            "canonical_sha256": bundle.envelope["integrity"]["canonical_sha256"],
            "synthetic_test_only": False,
            "copyable_authorization_token_present": False,
            "socket_opened": False,
            "execution_ready": False,
        }
        print(contract.canonical_json_bytes(summary).decode("utf-8"))
        return 0
    if args.command == "execute-phase-a-live":
        receipt = execute_phase_a_live_once(
            args.authority,
            authorization=args.authorization,
        )
        summary = {
            "state": receipt["state"],
            "kind": receipt["kind"],
            "version_protocol_response_conformance": receipt[
                "version_protocol_response_conformance"
            ],
            "responder_or_device_identity_proven": False,
            "phase_b_generated_or_executed": False,
        }
        print(contract.canonical_json_bytes(summary).decode("utf-8"))
        return 0 if receipt["version_protocol_response_conformance"] else 2
    raise PhaseALiveError("unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
