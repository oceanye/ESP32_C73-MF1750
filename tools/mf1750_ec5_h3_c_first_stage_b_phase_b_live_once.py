#!/usr/bin/env python3
"""One-shot Phase-B ``manifest -> status -> report`` live runner.

Importing, reviewing, preparing, or validating this module performs no device
I/O.  Production execution is possible only through a fresh Phase-B authority,
a runner-source-bound live envelope, and a later byte-exact user phrase.  The
public live surface has one fixed literal IPv4 origin, three bodyless GETs, no
retry/fallback/recovery/autochain, and no visible-refresh operation.

The committed Phase-A receipt is replayed through the sealed offline Phase-B
gate before any attempt path is reserved.  The Phase-B registry is O_EXCL and
durable before the output checkpoint; the checkpoint is durable before the
first socket.  A terminal receipt is written to a distinct O_EXCL temporary
file and atomically replaces the checkpoint on the same volume.
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
import socket
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_live_once as phase_a_live
from tools import mf1750_ec5_h3_c_first_stage_b_phase_b_offline_gate as offline_gate
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical


SCHEMA_VERSION: Final = 1
RUNNER_REVIEW_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-live-runner-review-v1"
)
RUNNER_REVIEW_CLASSIFICATION: Final = (
    "OFFLINE_HASH_FROZEN_PHASE_B_RUNNER_REVIEW_NOT_AUTHORITY"
)
LIVE_AUTHORITY_KIND: Final = "mf1750-ec5-h3-c-first-stage-b-phase-b-live-authority-v1"
LIVE_AUTHORITY_CLASSIFICATION: Final = (
    "FRESH_PHASE_B_AUTHORITY_CHALLENGE_NOT_EXECUTION_AUTHORIZATION"
)
SYNTHETIC_AUTHORITY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-synthetic-authority-v1"
)
SYNTHETIC_AUTHORITY_CLASSIFICATION: Final = (
    "SYNTHETIC_TEST_ONLY_PHASE_B_AUTHORITY_NEVER_LIVE_ELIGIBLE"
)
LIVE_ENVELOPE_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-live-execution-envelope-v1"
)
LIVE_ENVELOPE_CLASSIFICATION: Final = (
    "SEALED_PHASE_B_RUNNER_BOUND_ENVELOPE_REQUIRES_BYTE_EXACT_AUTHORIZATION"
)
SYNTHETIC_ENVELOPE_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-synthetic-envelope-v1"
)
SYNTHETIC_ENVELOPE_CLASSIFICATION: Final = (
    "SYNTHETIC_TEST_ONLY_PHASE_B_ENVELOPE_NEVER_LIVE_ELIGIBLE"
)
LIVE_REGISTRY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-live-attempt-registry-v1"
)
SYNTHETIC_REGISTRY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-synthetic-registry-v1"
)
LIVE_RECEIPT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-live-terminal-receipt-v1"
)
SYNTHETIC_RECEIPT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-synthetic-receipt-v1"
)
LIVE_AUTHORIZATION_PREFIX: Final = (
    "AUTHORIZE_STAGE_B_PHASE_B_LIVE_MANIFEST_STATUS_REPORT_GETS_RUNNER_BOUND"
)
SYNTHETIC_AUTHORIZATION_PREFIX: Final = (
    "SYNTHETIC_TEST_ONLY_STAGE_B_PHASE_B_THREE_GETS_RUNNER_BOUND"
)

LITERAL_IPV4: Final = offline_gate.EXPECTED_IPV4
PORT: Final = offline_gate.EXPECTED_PORT
BASE_URL: Final = offline_gate.EXPECTED_BASE_URL
ENDPOINT_NAMES: Final = tuple(offline_gate.PHASE_B_ENDPOINT_NAMES)
SUCCESS_CLASSIFICATION: Final = offline_gate.SUCCESS_CLASSIFICATION
CONNECT_TIMEOUT_MS: Final = 3_000
READ_TIMEOUT_MS: Final = 5_000
PER_ENDPOINT_TOTAL_TIMEOUT_MS: Final = 8_000
MAX_RESPONSE_ENTITY_BYTES: Final = phase_a_live.MAX_VERSION_ENTITY_BYTES
MAX_TERMINAL_RECEIPT_BYTES: Final = facade.MAX_JSON_BYTES
MAX_ERROR_TEXT_BYTES: Final = 4_096
MAX_HOST_NOW_SKEW_SECONDS: Final = 30
HEX64 = phase_a.HEX64


class PhaseBLiveError(ValueError):
    """A Phase-B authority, envelope, state machine, or receipt differs."""


class PhaseBLiveTransportError(PhaseBLiveError):
    """A terminal Phase-B transport/framing failure."""


@dataclass(frozen=True)
class _PhaseBBundle:
    envelope_path: Path
    envelope_payload: bytes
    envelope: Mapping[str, Any]
    envelope_binding: Mapping[str, Any]
    authority_path: Path
    authority_payload: bytes
    authority: Mapping[str, Any]
    authority_binding: Mapping[str, Any]
    gate_path: Path
    gate_payload: bytes
    gate: Mapping[str, Any]
    gate_binding: Mapping[str, Any]
    v10_context: Any
    snapshots: tuple[Any, ...]
    synthetic_test_only: bool


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return phase_a._seal(unsigned)  # noqa: SLF001


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    try:
        return phase_a._validate_seal(root, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBLiveError(str(error)) from error


def _safe_absolute(path: Path, *, label: str) -> Path:
    try:
        return phase_a._safe_absolute(path, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBLiveError(str(error)) from error


def _source_binding(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return phase_a._source_binding(path, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBLiveError(str(error)) from error


def _read_json(path: Path, *, label: str) -> tuple[Path, bytes, Mapping[str, Any]]:
    try:
        resolved, payload, root = facade._read_json(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseBLiveError(str(error)) from error
    if payload != contract.canonical_json_bytes(root) + b"\n":
        raise PhaseBLiveError(f"{label} is not canonical JSON plus one LF")
    return resolved, payload, root


def _write_new_json(path: Path, root: Mapping[str, Any], *, label: str) -> None:
    target = _safe_absolute(path, label=label)
    try:
        parent = facade._assert_directory_chain(  # noqa: SLF001
            target.parent, create=True, label=label
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseBLiveError(str(error)) from error
    target = parent / target.name
    payload = contract.canonical_json_bytes(root) + b"\n"
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        phase_a._fsync_parent_directory(target)  # noqa: SLF001
    except FileExistsError as error:
        raise PhaseBLiveError(f"{label} already exists") from error
    except OSError as error:
        raise PhaseBLiveError(f"could not write {label}: {error}") from error


def _strict_json_equal(actual: Any, expected: Any) -> bool:
    return phase_a_live._strict_json_equal(actual, expected)  # noqa: SLF001


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_zoned(value: str, *, label: str) -> datetime:
    try:
        return phase_a._zoned_datetime(value, label=label).astimezone(  # noqa: SLF001
            timezone.utc
        )
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBLiveError(str(error)) from error


def _directory_entry_exists(path: Path) -> bool:
    try:
        return phase_a_live._directory_entry_exists(path)  # noqa: SLF001
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _gate_binding(
    path: Path, payload: bytes, root: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "offline_gate_id": root["offline_gate_id"],
    }


def _validate_offline_gate_bound(
    root: Mapping[str, Any], *, require_attempt_paths_absent: bool
) -> dict[str, Any]:
    if require_attempt_paths_absent:
        try:
            return offline_gate.validate_phase_b_offline_gate(
                root, require_planned_paths_absent=True
            )
        except offline_gate.PhaseBOfflineGateError as error:
            raise PhaseBLiveError(f"offline Phase-B gate differs: {error}") from error

    canonical = _validate_seal(root, label="offline Phase-B gate")
    if (
        root.get("schema_version") != offline_gate.SCHEMA_VERSION
        or root.get("kind") != offline_gate.KIND
        or root.get("classification") != offline_gate.CLASSIFICATION
    ):
        raise PhaseBLiveError("offline Phase-B gate schema/kind differs")
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"offline_gate_id", "integrity"}
        }
    )
    if root.get("offline_gate_id") != expected_id:
        raise PhaseBLiveError("offline Phase-B gate ID differs")

    predecessor = root["phase_a_predecessor"]
    facade_binding = root["exact_surface_facade_binding"]
    facade_path, facade_payload, facade_root = _read_json(
        Path(facade_binding["path"]), label="exact-surface facade blueprint"
    )
    try:
        facade_summary = facade.validate_blueprint(
            facade_root, require_live_output_absent=False
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseBLiveError(
            f"exact-surface facade replay differs: {error}"
        ) from error
    expected_facade_binding = {
        "path": str(facade_path),
        "bytes": len(facade_payload),
        "sha256": contract.sha256(facade_payload),
        "blueprint_id": facade_root["blueprint_id"],
        "canonical_sha256": facade_summary["canonical_sha256"],
        "classification": facade_root["classification"],
    }
    if not _strict_json_equal(facade_binding, expected_facade_binding):
        raise PhaseBLiveError("offline gate facade whole-file binding differs")

    def bound_json(
        binding: Mapping[str, Any], *, label: str
    ) -> tuple[Path, bytes, Mapping[str, Any]]:
        path, payload, value = _read_json(Path(binding["path"]), label=label)
        _validate_seal(value, label=label)
        expected = {
            "path": str(path),
            "bytes": len(payload),
            "sha256": contract.sha256(payload),
            "canonical_sha256": value["integrity"]["canonical_sha256"],
        }
        for key, observed in expected.items():
            if binding.get(key) != observed:
                raise PhaseBLiveError(f"{label} whole-file binding differs")
        return path, payload, value

    envelope_path, envelope_payload, phase_a_envelope = bound_json(
        predecessor["live_envelope"], label="committed Phase-A live envelope"
    )
    if predecessor["live_envelope"].get("live_envelope_id") != phase_a_envelope.get(
        "live_envelope_id"
    ):
        raise PhaseBLiveError("committed Phase-A envelope ID differs")
    authority_path, authority_payload, phase_a_authority = bound_json(
        predecessor["offline_authority"], label="committed Phase-A authority"
    )
    if predecessor["offline_authority"].get("authority_id") != phase_a_authority.get(
        "authority_id"
    ):
        raise PhaseBLiveError("committed Phase-A authority ID differs")
    registry_path, registry_payload, phase_a_registry = bound_json(
        predecessor["immutable_registry"], label="committed Phase-A registry"
    )
    receipt_path, receipt_payload, phase_a_receipt = bound_json(
        predecessor["committed_terminal_receipt"],
        label="committed Phase-A terminal receipt",
    )
    if (
        phase_a_receipt.get("state")
        != "TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE"
        or phase_a_receipt.get("version_protocol_response_conformance") is not True
        or phase_a_receipt.get("phase_b_authority_generated") is not False
        or phase_a_receipt.get("phase_b_authorization_generated") is not False
        or phase_a_receipt.get("phase_b_requests") != 0
        or phase_a_receipt.get("attempt_registry_file") != str(registry_path)
        or phase_a_receipt.get("registry_whole_file_sha256")
        != contract.sha256(registry_payload)
        or phase_a_envelope["attempt"]["terminal_receipt_file"] != str(receipt_path)
        or phase_a_envelope["offline_phase_a_authority_binding"]["sha256"]
        != contract.sha256(authority_payload)
    ):
        raise PhaseBLiveError("committed Phase-A terminal boundary differs")
    phase_a_predecessor = offline_gate._PhaseAPredecessor(  # noqa: SLF001
        envelope_path=envelope_path,
        envelope_payload=envelope_payload,
        envelope=phase_a_envelope,
        authority_path=authority_path,
        authority_payload=authority_payload,
        authority=phase_a_authority,
        registry_path=registry_path,
        registry_payload=registry_payload,
        registry=phase_a_registry,
        receipt_path=receipt_path,
        receipt_payload=receipt_payload,
        receipt=phase_a_receipt,
        validation_summary={"post_phase_b_static_replay": True},
    )
    try:
        replay = offline_gate._replay_phase_a_version(  # noqa: SLF001
            phase_a_predecessor, facade_blueprint=facade_root
        )
        requests = offline_gate._phase_b_requests(facade_root)  # noqa: SLF001
    except offline_gate.PhaseBOfflineGateError as error:
        raise PhaseBLiveError(
            f"offline Phase-B response replay differs: {error}"
        ) from error
    if not _strict_json_equal(root.get("phase_a_version_raw_replay"), replay):
        raise PhaseBLiveError("offline gate Phase-A version replay differs")
    if not _strict_json_equal(
        root.get("phase_b_state_machine", {}).get("ordered_requests"), requests
    ):
        raise PhaseBLiveError("offline gate Phase-B request set differs")
    current_sources = {
        "phase_b_offline_gate_module": _source_binding(
            Path(offline_gate.__file__), label="Phase-B offline gate module"
        ),
        "phase_a_live_validator_module": _source_binding(
            Path(phase_a_live.__file__), label="Phase-A live validator module"
        ),
        "exact_surface_facade_module": _source_binding(
            Path(facade.__file__), label="exact-surface facade module"
        ),
    }
    if not _strict_json_equal(root.get("source_bindings"), current_sources):
        raise PhaseBLiveError("offline Phase-B gate source bindings changed")
    return {
        "valid": True,
        "offline_gate_id": root["offline_gate_id"],
        "canonical_sha256": canonical,
        "phase_a_predecessor_committed_success": True,
        "phase_a_raw_version_replayed": True,
        "phase_b_endpoints": list(ENDPOINT_NAMES),
        "phase_b_repeats_version": False,
    }


def _load_offline_gate(
    path: Path, *, require_attempt_paths_absent: bool
) -> tuple[Path, bytes, Mapping[str, Any], dict[str, Any]]:
    gate_path, gate_payload, gate = _read_json(path, label="offline Phase-B gate")
    _validate_offline_gate_bound(
        gate, require_attempt_paths_absent=require_attempt_paths_absent
    )
    return gate_path, gate_payload, gate, _gate_binding(gate_path, gate_payload, gate)


def _request_set(gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    requests = deepcopy(gate["phase_b_state_machine"]["ordered_requests"])
    if type(requests) is not list or len(requests) != 3:
        raise PhaseBLiveError("Phase-B request count differs")
    for ordinal, (name, request) in enumerate(
        zip(ENDPOINT_NAMES, requests, strict=True), start=1
    ):
        if (
            type(request) is not dict
            or request.get("phase_b_ordinal") != ordinal
            or request.get("full_diagnostic_ordinal") != ordinal + 1
            or request.get("name") != name
            or request.get("method") != "GET"
            or request.get("absolute_url") != f"{BASE_URL}{request.get('path')}"
            or request.get("request_wire_ascii") is None
        ):
            raise PhaseBLiveError(f"Phase-B {name} request binding differs")
        try:
            wire = request["request_wire_ascii"].encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise PhaseBLiveError(
                f"Phase-B {name} request wire is not ASCII"
            ) from error
        if (
            len(wire) != request["request_wire_bytes"]
            or contract.sha256(wire) != request["request_wire_sha256"]
            or request["request_headers"]
            != {
                "Host": LITERAL_IPV4,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            }
        ):
            raise PhaseBLiveError(f"Phase-B {name} request wire differs")
    return requests


def _source_bindings(*, gate: Mapping[str, Any]) -> dict[str, Any]:
    bindings = {
        "phase_b_live_runner_module": _source_binding(
            Path(__file__), label="Phase-B live runner module"
        ),
        "phase_b_offline_gate_module": _source_binding(
            Path(offline_gate.__file__), label="Phase-B offline gate module"
        ),
        "phase_a_live_predecessor_module": _source_binding(
            Path(phase_a_live.__file__), label="Phase-A live predecessor module"
        ),
        "phase_a_authority_module": _source_binding(
            Path(phase_a.__file__), label="Phase-A authority module"
        ),
        "exact_surface_facade_module": _source_binding(
            Path(facade.__file__), label="exact-surface facade module"
        ),
        "matched_control_contract_module": _source_binding(
            Path(contract.__file__), label="matched-control contract module"
        ),
        "frozen_physical_validator_module": _source_binding(
            Path(physical.__file__), label="frozen physical validator module"
        ),
    }
    gate_bindings = gate["source_bindings"]
    comparisons = {
        "phase_b_offline_gate_module": "phase_b_offline_gate_module",
        "phase_a_live_predecessor_module": "phase_a_live_validator_module",
        "exact_surface_facade_module": "exact_surface_facade_module",
    }
    for current_name, gate_name in comparisons.items():
        if not _strict_json_equal(bindings[current_name], gate_bindings[gate_name]):
            raise PhaseBLiveError(f"source binding {current_name} differs from P0 gate")
    return bindings


def materialize_runner_review(
    *, offline_gate_file: Path, runner_review_file: Path, test_file: Path
) -> dict[str, Any]:
    """Seal a non-executable review of the final runner and its tests."""

    gate_path, gate_payload, gate, gate_binding = _load_offline_gate(
        offline_gate_file, require_attempt_paths_absent=True
    )
    output = _safe_absolute(runner_review_file, label="Phase-B runner review")
    test_binding = _source_binding(test_file, label="Phase-B live runner tests")
    sources = _source_bindings(gate=gate)
    requests = _request_set(gate)
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": RUNNER_REVIEW_KIND,
        "classification": RUNNER_REVIEW_CLASSIFICATION,
        "runner_review_file": str(output),
        "offline_gate_binding": gate_binding,
        "source_bindings": sources,
        "test_binding": test_binding,
        "reviewed_network_surface": {
            "literal_ipv4": LITERAL_IPV4,
            "port": PORT,
            "ordered_endpoint_names": list(ENDPOINT_NAMES),
            "request_set_sha256": contract.sha256(requests),
            "request_wire_sha256s": [
                request["request_wire_sha256"] for request in requests
            ],
            "maximum_gets": 3,
            "post_body_claim_mutation_visible_refresh_requests": 0,
            "retry_fallback_recovery_autochain": False,
            "maximum_response_entity_bytes_per_endpoint": (MAX_RESPONSE_ENTITY_BYTES),
            "p0_maximum_is_narrowed": (
                MAX_RESPONSE_ENTITY_BYTES
                < gate["response_validation_contract"]["maximum_response_entity_bytes"]
            ),
        },
        "reviewed_evidence_surface": {
            "registry_o_excl_before_output_and_socket": True,
            "output_checkpoint_o_excl_and_fsync_before_socket": True,
            "one_new_connection_per_endpoint": True,
            "validate_each_response_before_next_socket": True,
            "terminal_temp_o_excl_then_same_volume_atomic_replace": True,
            "transport_error_wire_emission_and_peer_receipt": "UNKNOWN",
            "process_control_exception_leaves_indeterminate_checkpoint": True,
        },
        "authority_boundary": {
            "fresh_phase_b_onsite_gate_present": False,
            "production_authority_present": False,
            "live_envelope_present": False,
            "copyable_authorization_phrase_present": False,
            "execution_ready": False,
            "live_authorized": False,
        },
        "device_io_performed": False,
        "gate_path_replayed": str(gate_path),
        "gate_whole_file_bytes_replayed": len(gate_payload),
    }
    unsigned["runner_review_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_runner_review(root: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-B runner review")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != RUNNER_REVIEW_KIND
        or root.get("classification") != RUNNER_REVIEW_CLASSIFICATION
    ):
        raise PhaseBLiveError("Phase-B runner review schema/kind differs")
    rebuilt = materialize_runner_review(
        offline_gate_file=Path(root["offline_gate_binding"]["path"]),
        runner_review_file=Path(root["runner_review_file"]),
        test_file=Path(root["test_binding"]["path"]),
    )
    if not _strict_json_equal(root, rebuilt):
        raise PhaseBLiveError("Phase-B runner review reconstruction differs")
    return {
        "valid": True,
        "runner_review_id": root["runner_review_id"],
        "canonical_sha256": canonical,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
    }


def write_new_runner_review(path: Path, root: Mapping[str, Any]) -> None:
    validate_runner_review(root)
    if _safe_absolute(path, label="Phase-B runner review") != Path(
        root["runner_review_file"]
    ):
        raise PhaseBLiveError("Phase-B runner review self-path differs")
    _write_new_json(path, root, label="Phase-B runner review")


def _fresh_phase_b_gate(
    *,
    observed_at: str,
    prepared_at: str,
    current_reading_a: str,
    locator_selection_phrase: str,
    j2_off: bool,
    screen_clean_white: bool,
    esp32_usb_connected: bool,
    supply_3v3_cv_normal: bool,
    temperature_exact_25c: bool,
    current_limit_exact_1a: bool,
    current_and_temperature_monitors_ready: bool,
    physical_cutoff_ready: bool,
    no_reset_since_stage_a: bool,
    no_flash_since_stage_a: bool,
    no_refresh_since_stage_a: bool,
    no_rewire_since_stage_a: bool,
    phase_a_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        gate = phase_a._onsite_gate(  # noqa: SLF001
            observed_at=observed_at,
            prepared_at=prepared_at,
            current_reading_a=current_reading_a,
            locator_selection_phrase=locator_selection_phrase,
            j2_off=j2_off,
            screen_clean_white=screen_clean_white,
            esp32_usb_connected=esp32_usb_connected,
            supply_3v3_cv_normal=supply_3v3_cv_normal,
            temperature_exact_25c=temperature_exact_25c,
            current_limit_exact_1a=current_limit_exact_1a,
            current_and_temperature_monitors_ready=(
                current_and_temperature_monitors_ready
            ),
            physical_cutoff_ready=physical_cutoff_ready,
            no_reset_since_stage_a=no_reset_since_stage_a,
            no_flash_since_stage_a=no_flash_since_stage_a,
            no_refresh_since_stage_a=no_refresh_since_stage_a,
            no_rewire_since_stage_a=no_rewire_since_stage_a,
        )
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBLiveError(str(error)) from error
    observed = _parse_zoned(observed_at, label="Phase-B onsite observed-at")
    phase_a_execution = _parse_zoned(
        str(phase_a_receipt["execution_observed_now_utc"]),
        label="committed Phase-A execution time",
    )
    if observed <= phase_a_execution:
        raise PhaseBLiveError("fresh Phase-B onsite observation is not after Phase-A")
    renamed = deepcopy(gate)
    renamed["fresh_after_committed_phase_a_terminal"] = True
    renamed["committed_phase_a_execution_utc"] = _utc_text(phase_a_execution)
    renamed["phase_a_gate_is_not_reused"] = True
    renamed["broad_or_prior_authorization_is_not_phase_b_authorization"] = True
    renamed["gate_canonical_sha256"] = contract.sha256(
        {key: value for key, value in renamed.items() if key != "gate_canonical_sha256"}
    )
    return renamed


def _planned_paths(
    gate: Mapping[str, Any],
    *,
    synthetic_test_only: bool,
    synthetic_registry_file: Path | None,
    synthetic_terminal_receipt_file: Path | None,
) -> tuple[Path, Path, Path]:
    planned = gate["planned_production_artifacts"]
    if synthetic_test_only:
        if synthetic_registry_file is None or synthetic_terminal_receipt_file is None:
            raise PhaseBLiveError("synthetic authority requires two test-only paths")
        registry = _safe_absolute(
            synthetic_registry_file, label="synthetic Phase-B registry"
        )
        receipt = _safe_absolute(
            synthetic_terminal_receipt_file, label="synthetic Phase-B receipt"
        )
        if not registry.name.endswith(
            ".synthetic-test-only.json"
        ) or not receipt.name.endswith(".synthetic-test-only.json"):
            raise PhaseBLiveError("synthetic evidence paths need test-only suffixes")
    else:
        if (
            synthetic_registry_file is not None
            or synthetic_terminal_receipt_file is not None
        ):
            raise PhaseBLiveError(
                "production authority rejects synthetic path overrides"
            )
        registry = _safe_absolute(
            Path(planned["phase_b_attempt_registry"]["path"]),
            label="planned Phase-B registry",
        )
        receipt = _safe_absolute(
            Path(planned["phase_b_terminal_receipt"]["path"]),
            label="planned Phase-B terminal receipt",
        )
    temp = _safe_absolute(
        receipt.with_name(receipt.name + ".phase-b-finalize-o-excl.tmp"),
        label="Phase-B finalization temp",
    )
    if receipt.parent != temp.parent or len({registry, receipt, temp}) != 3:
        raise PhaseBLiveError(
            "Phase-B evidence paths are not distinct/same-volume planned"
        )
    return registry, receipt, temp


def materialize_phase_b_live_authority(
    *,
    offline_gate_file: Path,
    live_authority_file: Path,
    observed_at: str,
    prepared_at: str,
    current_reading_a: str,
    locator_selection_phrase: str,
    j2_off: bool,
    screen_clean_white: bool,
    esp32_usb_connected: bool,
    supply_3v3_cv_normal: bool,
    temperature_exact_25c: bool,
    current_limit_exact_1a: bool,
    current_and_temperature_monitors_ready: bool,
    physical_cutoff_ready: bool,
    no_reset_since_stage_a: bool,
    no_flash_since_stage_a: bool,
    no_refresh_since_stage_a: bool,
    no_rewire_since_stage_a: bool,
    _synthetic_test_only: bool = False,
    _synthetic_registry_file: Path | None = None,
    _synthetic_terminal_receipt_file: Path | None = None,
    _require_attempt_paths_absent: bool = True,
) -> dict[str, Any]:
    """Build a fresh challenge; this does not authorize or execute Phase-B."""

    gate_path, gate_payload, gate, gate_binding = _load_offline_gate(
        offline_gate_file,
        require_attempt_paths_absent=(
            _require_attempt_paths_absent and not _synthetic_test_only
        ),
    )
    requests = _request_set(gate)
    phase_a_receipt_path = Path(
        gate["phase_a_predecessor"]["committed_terminal_receipt"]["path"]
    )
    _, _, phase_a_receipt = _read_json(
        phase_a_receipt_path, label="committed Phase-A receipt"
    )
    fresh_gate = _fresh_phase_b_gate(
        observed_at=observed_at,
        prepared_at=prepared_at,
        current_reading_a=current_reading_a,
        locator_selection_phrase=locator_selection_phrase,
        j2_off=j2_off,
        screen_clean_white=screen_clean_white,
        esp32_usb_connected=esp32_usb_connected,
        supply_3v3_cv_normal=supply_3v3_cv_normal,
        temperature_exact_25c=temperature_exact_25c,
        current_limit_exact_1a=current_limit_exact_1a,
        current_and_temperature_monitors_ready=(current_and_temperature_monitors_ready),
        physical_cutoff_ready=physical_cutoff_ready,
        no_reset_since_stage_a=no_reset_since_stage_a,
        no_flash_since_stage_a=no_flash_since_stage_a,
        no_refresh_since_stage_a=no_refresh_since_stage_a,
        no_rewire_since_stage_a=no_rewire_since_stage_a,
        phase_a_receipt=phase_a_receipt,
    )
    authority_path = _safe_absolute(live_authority_file, label="Phase-B live authority")
    registry, receipt, temp = _planned_paths(
        gate,
        synthetic_test_only=_synthetic_test_only,
        synthetic_registry_file=_synthetic_registry_file,
        synthetic_terminal_receipt_file=_synthetic_terminal_receipt_file,
    )
    if len({gate_path, authority_path, registry, receipt, temp}) != 5:
        raise PhaseBLiveError("Phase-B gate/authority/evidence paths collide")
    if _require_attempt_paths_absent:
        for label, path in (
            ("Phase-B registry", registry),
            ("Phase-B terminal receipt", receipt),
            ("Phase-B finalization temp", temp),
        ):
            if _directory_entry_exists(path):
                raise PhaseBLiveError(f"{label} already exists; no retry")

    source_bindings = _source_bindings(gate=gate)
    request_set_sha256 = contract.sha256(requests)
    attempt_preimage = {
        "domain": (
            "MF1750_PHASE_B_SYNTHETIC_ATTEMPT_V1"
            if _synthetic_test_only
            else "MF1750_PHASE_B_LIVE_ATTEMPT_V1"
        ),
        "offline_gate_file_sha256": contract.sha256(gate_payload),
        "offline_gate_id": gate["offline_gate_id"],
        "fresh_gate_canonical_sha256": fresh_gate["gate_canonical_sha256"],
        "request_set_sha256": request_set_sha256,
        "runner_source_sha256": source_bindings["phase_b_live_runner_module"]["sha256"],
        "registry_file": str(registry),
        "terminal_receipt_file": str(receipt),
        "finalization_temp_file": str(temp),
    }
    attempt_id = contract.sha256(attempt_preimage)
    challenge = contract.sha256(
        {
            "domain": "MF1750_PHASE_B_FRESH_AUTHORITY_CHALLENGE_V1",
            "attempt_id": attempt_id,
            "offline_gate_id": gate["offline_gate_id"],
            "fresh_gate_canonical_sha256": fresh_gate["gate_canonical_sha256"],
            "request_set_sha256": request_set_sha256,
            "runner_source_sha256": source_bindings["phase_b_live_runner_module"][
                "sha256"
            ],
        }
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            SYNTHETIC_AUTHORITY_KIND if _synthetic_test_only else LIVE_AUTHORITY_KIND
        ),
        "classification": (
            SYNTHETIC_AUTHORITY_CLASSIFICATION
            if _synthetic_test_only
            else LIVE_AUTHORITY_CLASSIFICATION
        ),
        "synthetic_test_only": _synthetic_test_only,
        "live_authority_file": str(authority_path),
        "offline_gate_binding": gate_binding,
        "committed_phase_a_predecessor": deepcopy(gate["phase_a_predecessor"]),
        "phase_a_version_raw_replay": deepcopy(gate["phase_a_version_raw_replay"]),
        "fresh_phase_b_onsite_gate": fresh_gate,
        "candidate_origin": deepcopy(gate["candidate_origin"]),
        "ordered_requests": requests,
        "request_set_sha256": request_set_sha256,
        "source_bindings": source_bindings,
        "attempt": {
            "attempt_id": attempt_id,
            "registry_file": str(registry),
            "terminal_receipt_file": str(receipt),
            "finalization_temp_file": str(temp),
            "registry_o_excl_before_output_and_socket": True,
            "output_checkpoint_o_excl_and_fsync_before_socket": True,
            "registry_creation_permanently_consumes_authorization": True,
            "temp_o_excl_then_same_volume_atomic_replace": True,
            "registry_and_output_are_never_deleted_or_retried": True,
        },
        "authorization_challenge": {
            "prefix": (
                SYNTHETIC_AUTHORIZATION_PREFIX
                if _synthetic_test_only
                else LIVE_AUTHORIZATION_PREFIX
            ),
            "challenge": challenge,
            "copyable_authorization_phrase_present": False,
            "prior_or_broad_authorization_accepted": False,
            "must_bind_future_envelope_file_hash_id_attempt_challenge_runner_and_requests": True,
            "must_be_later_byte_exact_case_exact": True,
        },
        "transport_limits": {
            "literal_ipv4": LITERAL_IPV4,
            "port": PORT,
            "ordered_endpoint_names": list(ENDPOINT_NAMES),
            "maximum_gets": 3,
            "maximum_application_transport_attempts": 3,
            "maximum_response_entity_bytes_per_endpoint": (MAX_RESPONSE_ENTITY_BYTES),
            "connect_timeout_ms_per_endpoint": CONNECT_TIMEOUT_MS,
            "read_timeout_ms_per_endpoint": READ_TIMEOUT_MS,
            "total_timeout_ms_per_endpoint": PER_ENDPOINT_TOTAL_TIMEOUT_MS,
            "post_body_claim_mutation_visible_refresh_requests": 0,
            "dns_proxy_redirect_scan_retry_fallback_recovery_autochain": False,
        },
        "success_boundary": {
            "classification_only": SUCCESS_CLASSIFICATION,
            "responder_or_device_identity_proven": False,
            "trusted_ip_binding_proven": False,
            "fresh_boot_or_active_slot_proven": False,
            "visible_action_authorized": False,
        },
        "execution_state": {
            "live_envelope_present": False,
            "copyable_authorization_phrase_present": False,
            "registry_or_receipt_created": False,
            "execution_ready": False,
            "live_authorized": False,
            "device_io_performed": False,
        },
    }
    unsigned["authority_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def _validate_authority_root(
    root: Mapping[str, Any],
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-B live authority")
    synthetic = root.get("synthetic_test_only")
    if type(synthetic) is not bool:
        raise PhaseBLiveError("Phase-B authority synthetic flag differs")
    if synthetic and not allow_synthetic_test_only:
        raise PhaseBLiveError("synthetic Phase-B authority is not live authority")
    expected_kind = SYNTHETIC_AUTHORITY_KIND if synthetic else LIVE_AUTHORITY_KIND
    expected_class = (
        SYNTHETIC_AUTHORITY_CLASSIFICATION
        if synthetic
        else LIVE_AUTHORITY_CLASSIFICATION
    )
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != expected_kind
        or root.get("classification") != expected_class
    ):
        raise PhaseBLiveError("Phase-B authority schema/kind differs")
    gate = root["fresh_phase_b_onsite_gate"]
    attempt = root["attempt"]
    rebuilt = materialize_phase_b_live_authority(
        offline_gate_file=Path(root["offline_gate_binding"]["path"]),
        live_authority_file=Path(root["live_authority_file"]),
        observed_at=str(gate["observed_at"]),
        prepared_at=str(gate["prepared_at"]),
        current_reading_a=str(gate["current_reading_a"]),
        locator_selection_phrase=str(gate["candidate_selection_phrase"]),
        j2_off=gate["j2_off"],
        screen_clean_white=gate["screen_clean_white"],
        esp32_usb_connected=gate["esp32_usb_connected"],
        supply_3v3_cv_normal=gate["supply_3v3_cv_normal"],
        temperature_exact_25c=gate["temperature_exact_25c"],
        current_limit_exact_1a=gate["current_limit_exact_1a"],
        current_and_temperature_monitors_ready=gate[
            "current_and_temperature_monitors_ready"
        ],
        physical_cutoff_ready=gate["physical_cutoff_ready"],
        no_reset_since_stage_a=gate["no_reset_since_stage_a"],
        no_flash_since_stage_a=gate["no_flash_since_stage_a"],
        no_refresh_since_stage_a=gate["no_refresh_since_stage_a"],
        no_rewire_since_stage_a=gate["no_rewire_since_stage_a"],
        _synthetic_test_only=synthetic,
        _synthetic_registry_file=(
            Path(attempt["registry_file"]) if synthetic else None
        ),
        _synthetic_terminal_receipt_file=(
            Path(attempt["terminal_receipt_file"]) if synthetic else None
        ),
        _require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if not _strict_json_equal(root, rebuilt):
        raise PhaseBLiveError("Phase-B authority reconstruction differs")
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"authority_id", "integrity"}
        }
    )
    if root.get("authority_id") != expected_id:
        raise PhaseBLiveError("Phase-B authority ID differs")
    return {
        "valid": True,
        "authority_id": root["authority_id"],
        "canonical_sha256": canonical,
        "synthetic_test_only": synthetic,
        "copyable_authorization_phrase_present": False,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
    }


def validate_phase_b_live_authority(
    root: Mapping[str, Any], *, require_attempt_paths_absent: bool = True
) -> dict[str, Any]:
    return _validate_authority_root(
        root,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=False,
    )


def write_new_phase_b_live_authority(path: Path, root: Mapping[str, Any]) -> None:
    validate_phase_b_live_authority(root, require_attempt_paths_absent=True)
    if _safe_absolute(path, label="Phase-B live authority") != Path(
        root["live_authority_file"]
    ):
        raise PhaseBLiveError("Phase-B live authority self-path differs")
    _write_new_json(path, root, label="Phase-B live authority")


def _authority_bundle(
    path: Path,
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> tuple[Path, bytes, Mapping[str, Any], dict[str, Any]]:
    authority_path, payload, root = _read_json(path, label="Phase-B live authority")
    _validate_authority_root(
        root,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    binding = {
        "path": str(authority_path),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "authority_id": root["authority_id"],
    }
    return authority_path, payload, root, binding


def _gate_time(authority: Mapping[str, Any], *, now: datetime, label: str) -> str:
    gate = authority["fresh_phase_b_onsite_gate"]
    before = _parse_zoned(str(gate["not_before_utc"]), label="gate not-before")
    after = _parse_zoned(str(gate["not_after_utc"]), label="gate not-after")
    observed = now.astimezone(timezone.utc)
    if observed < before or observed >= after:
        raise PhaseBLiveError(f"{label} is outside not_before <= now < not_after")
    return _utc_text(observed)


def materialize_phase_b_live_execution_envelope(
    *,
    live_authority_file: Path,
    live_envelope_file: Path,
    built_at: str,
    _allow_synthetic_test_only: bool = False,
    _require_attempt_paths_absent: bool = True,
) -> dict[str, Any]:
    """Build a source-bound envelope; it still does not authorize execution."""

    authority_path, authority_payload, authority, authority_binding = _authority_bundle(
        live_authority_file,
        require_attempt_paths_absent=_require_attempt_paths_absent,
        allow_synthetic_test_only=_allow_synthetic_test_only,
    )
    synthetic = bool(authority["synthetic_test_only"])
    built = _parse_zoned(built_at, label="Phase-B envelope built-at")
    built_utc = _gate_time(authority, now=built, label="Phase-B envelope built-at")
    envelope_path = _safe_absolute(
        live_envelope_file, label="Phase-B live execution envelope"
    )
    attempt = authority["attempt"]
    registry = Path(attempt["registry_file"])
    receipt = Path(attempt["terminal_receipt_file"])
    temp = Path(attempt["finalization_temp_file"])
    if len({authority_path, envelope_path, registry, receipt, temp}) != 5:
        raise PhaseBLiveError("Phase-B authority/envelope/evidence paths collide")
    if _require_attempt_paths_absent:
        for label, path in (
            ("Phase-B registry", registry),
            ("Phase-B terminal receipt", receipt),
            ("Phase-B finalization temp", temp),
        ):
            if _directory_entry_exists(path):
                raise PhaseBLiveError(f"{label} already exists; no retry")

    requests = deepcopy(authority["ordered_requests"])
    sources = deepcopy(authority["source_bindings"])
    current_runner = _source_binding(Path(__file__), label="Phase-B live runner")
    if not _strict_json_equal(current_runner, sources["phase_b_live_runner_module"]):
        raise PhaseBLiveError("Phase-B runner changed since authority preparation")
    request_wire_set_sha256 = contract.sha256(
        [request["request_wire_sha256"] for request in requests]
    )
    live_attempt_preimage = {
        "domain": (
            "MF1750_PHASE_B_SYNTHETIC_RUNNER_ATTEMPT_V1"
            if synthetic
            else "MF1750_PHASE_B_LIVE_RUNNER_ATTEMPT_V1"
        ),
        "authority_file_sha256": contract.sha256(authority_payload),
        "authority_id": authority["authority_id"],
        "authority_attempt_id": attempt["attempt_id"],
        "runner_source_sha256": current_runner["sha256"],
        "request_set_sha256": authority["request_set_sha256"],
        "request_wire_set_sha256": request_wire_set_sha256,
        "registry_file": str(registry),
        "terminal_receipt_file": str(receipt),
        "finalization_temp_file": str(temp),
        "built_at_utc": built_utc,
    }
    live_attempt_id = contract.sha256(live_attempt_preimage)
    challenge = contract.sha256(
        {
            "domain": "MF1750_PHASE_B_RUNNER_BOUND_USER_CHALLENGE_V1",
            "live_attempt_id": live_attempt_id,
            "authority_file_sha256": contract.sha256(authority_payload),
            "authority_id": authority["authority_id"],
            "fresh_gate_canonical_sha256": authority["fresh_phase_b_onsite_gate"][
                "gate_canonical_sha256"
            ],
            "runner_source_sha256": current_runner["sha256"],
            "request_set_sha256": authority["request_set_sha256"],
            "request_wire_set_sha256": request_wire_set_sha256,
        }
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": SYNTHETIC_ENVELOPE_KIND if synthetic else LIVE_ENVELOPE_KIND,
        "classification": (
            SYNTHETIC_ENVELOPE_CLASSIFICATION
            if synthetic
            else LIVE_ENVELOPE_CLASSIFICATION
        ),
        "synthetic_test_only": synthetic,
        "live_envelope_file": str(envelope_path),
        "built_at_utc": built_utc,
        "live_authority_binding": authority_binding,
        "offline_gate_binding": deepcopy(authority["offline_gate_binding"]),
        "fresh_onsite_gate_binding": {
            "gate_canonical_sha256": authority["fresh_phase_b_onsite_gate"][
                "gate_canonical_sha256"
            ],
            "not_before_utc": authority["fresh_phase_b_onsite_gate"]["not_before_utc"],
            "not_after_utc": authority["fresh_phase_b_onsite_gate"]["not_after_utc"],
            "must_be_rechecked_before_registry_and_each_socket": True,
            "any_condition_change_invalidates": True,
        },
        "source_bindings": sources,
        "source_binding_boundary": {
            "on_disk_source_files_bound_and_rechecked": True,
            "loaded_bytecode_sitecustomize_interpreter_integrity_proven": False,
        },
        "candidate_origin": deepcopy(authority["candidate_origin"]),
        "ordered_requests": requests,
        "request_set_sha256": authority["request_set_sha256"],
        "request_wire_set_sha256": request_wire_set_sha256,
        "transport_policy": deepcopy(authority["transport_limits"]),
        "attempt": {
            "live_attempt_id": live_attempt_id,
            "authority_attempt_id": attempt["attempt_id"],
            "registry_file": str(registry),
            "terminal_receipt_file": str(receipt),
            "finalization_temp_file": str(temp),
            "registry_first_output_second_o_excl": True,
            "checkpoint_fsynced_before_first_socket": True,
            "one_connection_per_endpoint": True,
            "response_validated_before_next_connection": True,
            "final_receipt_temp_o_excl_then_atomic_replace": True,
            "attempt_permanently_consumed_at_registry_creation": True,
            "retry_allowed": False,
        },
        "authorization_challenge": {
            "prefix": (
                SYNTHETIC_AUTHORIZATION_PREFIX
                if synthetic
                else LIVE_AUTHORIZATION_PREFIX
            ),
            "challenge": challenge,
            "copyable_authorization_phrase_present": False,
            "must_bind_envelope_file_hash_id_authority_attempt_runner_and_requests": True,
            "must_be_received_later_byte_exact_case_exact_within_fresh_gate": True,
            "prior_phase_a_or_broad_authorization_accepted": False,
        },
        "terminal_evidence_contract": deepcopy(authority["offline_gate_binding"]),
        "success_boundary": deepcopy(authority["success_boundary"]),
        "execution_state": {
            "copyable_authorization_phrase_present": False,
            "registry_or_receipt_created": False,
            "execution_ready_without_later_exact_phrase": False,
            "live_authorized": False,
            "device_io_performed": False,
        },
    }
    unsigned["live_envelope_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def _validate_envelope_root(
    root: Mapping[str, Any],
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-B live envelope")
    synthetic = root.get("synthetic_test_only")
    if type(synthetic) is not bool:
        raise PhaseBLiveError("Phase-B envelope synthetic flag differs")
    if synthetic and not allow_synthetic_test_only:
        raise PhaseBLiveError("synthetic Phase-B envelope is not live authority")
    expected_kind = SYNTHETIC_ENVELOPE_KIND if synthetic else LIVE_ENVELOPE_KIND
    expected_class = (
        SYNTHETIC_ENVELOPE_CLASSIFICATION if synthetic else LIVE_ENVELOPE_CLASSIFICATION
    )
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != expected_kind
        or root.get("classification") != expected_class
    ):
        raise PhaseBLiveError("Phase-B envelope schema/kind differs")
    rebuilt = materialize_phase_b_live_execution_envelope(
        live_authority_file=Path(root["live_authority_binding"]["path"]),
        live_envelope_file=Path(root["live_envelope_file"]),
        built_at=str(root["built_at_utc"]),
        _allow_synthetic_test_only=synthetic,
        _require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if not _strict_json_equal(root, rebuilt):
        raise PhaseBLiveError("Phase-B live envelope reconstruction differs")
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"live_envelope_id", "integrity"}
        }
    )
    if root.get("live_envelope_id") != expected_id:
        raise PhaseBLiveError("Phase-B live envelope ID differs")
    return {
        "valid": True,
        "live_envelope_id": root["live_envelope_id"],
        "canonical_sha256": canonical,
        "synthetic_test_only": synthetic,
        "copyable_authorization_phrase_present": False,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
    }


def validate_phase_b_live_execution_envelope(
    root: Mapping[str, Any], *, require_attempt_paths_absent: bool = True
) -> dict[str, Any]:
    return _validate_envelope_root(
        root,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=False,
    )


def write_new_phase_b_live_execution_envelope(
    path: Path, root: Mapping[str, Any]
) -> None:
    validate_phase_b_live_execution_envelope(root, require_attempt_paths_absent=True)
    if _safe_absolute(path, label="Phase-B live envelope") != Path(
        root["live_envelope_file"]
    ):
        raise PhaseBLiveError("Phase-B live envelope self-path differs")
    _write_new_json(path, root, label="Phase-B live envelope")


def _authorization_phrase(
    envelope: Mapping[str, Any], *, envelope_file_sha256: str
) -> str:
    if HEX64.fullmatch(envelope_file_sha256) is None:
        raise PhaseBLiveError("Phase-B envelope whole-file SHA-256 is invalid")
    authority = envelope["live_authority_binding"]
    runner_sha = envelope["source_bindings"]["phase_b_live_runner_module"]["sha256"]
    prefix = (
        SYNTHETIC_AUTHORIZATION_PREFIX
        if envelope["synthetic_test_only"]
        else LIVE_AUTHORIZATION_PREFIX
    )
    return (
        f"{prefix}"
        f"__LIVE_ENVELOPE_FILE_SHA256_{envelope_file_sha256.upper()}"
        f"__LIVE_ENVELOPE_ID_{str(envelope['live_envelope_id']).upper()}"
        f"__LIVE_AUTHORITY_FILE_SHA256_{str(authority['sha256']).upper()}"
        f"__LIVE_AUTHORITY_ID_{str(authority['authority_id']).upper()}"
        f"__LIVE_ATTEMPT_ID_{str(envelope['attempt']['live_attempt_id']).upper()}"
        f"__CHALLENGE_{str(envelope['authorization_challenge']['challenge']).upper()}"
        f"__RUNNER_SOURCE_SHA256_{str(runner_sha).upper()}"
        f"__ENDPOINT_SET_SHA256_{str(envelope['request_set_sha256']).upper()}"
        f"__REQUEST_WIRE_SET_SHA256_{str(envelope['request_wire_set_sha256']).upper()}"
        "__UNVERIFIED_HTTP_192_168_1_7_PORT_80"
        "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF"
        "__ORDER_MANIFEST_STATUS_REPORT__GET_3_POST_0_BODY_0"
        "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0"
        "__NO_RETRY_NO_FALLBACK_NO_RECOVERY_NO_AUTOCHAIN"
    )


def _snapshot(path: Path, *, label: str) -> Any:
    try:
        return phase_a_live._snapshot(path, label=label)  # noqa: SLF001
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _load_bundle(
    envelope_file: Path,
    *,
    require_attempt_paths_absent: bool,
    allow_synthetic_test_only: bool,
) -> _PhaseBBundle:
    envelope_path, envelope_payload, envelope = _read_json(
        envelope_file, label="Phase-B live envelope"
    )
    if envelope_path != _safe_absolute(
        Path(envelope["live_envelope_file"]), label="sealed Phase-B envelope path"
    ):
        raise PhaseBLiveError("actual Phase-B envelope path differs from self-path")
    _validate_envelope_root(
        envelope,
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    envelope_snapshot = _snapshot(envelope_path, label="Phase-B live envelope")
    if envelope_snapshot.sha256 != contract.sha256(envelope_payload):
        raise PhaseBLiveError("Phase-B envelope changed during load")

    authority_path, authority_payload, authority, authority_binding = _authority_bundle(
        Path(envelope["live_authority_binding"]["path"]),
        require_attempt_paths_absent=require_attempt_paths_absent,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    if not _strict_json_equal(authority_binding, envelope["live_authority_binding"]):
        raise PhaseBLiveError("Phase-B authority whole-file binding differs")
    authority_snapshot = _snapshot(authority_path, label="Phase-B live authority")
    if authority_snapshot.sha256 != contract.sha256(authority_payload):
        raise PhaseBLiveError("Phase-B authority changed during load")

    gate_path, gate_payload, gate, gate_binding = _load_offline_gate(
        Path(authority["offline_gate_binding"]["path"]),
        require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if not _strict_json_equal(gate_binding, authority["offline_gate_binding"]):
        raise PhaseBLiveError("offline Phase-B gate whole-file binding differs")
    gate_snapshot = _snapshot(gate_path, label="offline Phase-B gate")
    if gate_snapshot.sha256 != contract.sha256(gate_payload):
        raise PhaseBLiveError("offline Phase-B gate changed during load")

    facade_path, facade_payload, facade_root = _read_json(
        Path(gate["exact_surface_facade_binding"]["path"]),
        label="exact-surface facade blueprint",
    )
    try:
        facade.validate_blueprint(facade_root, require_live_output_absent=False)
    except facade.StageBFacadeContractError as error:
        raise PhaseBLiveError(f"exact-surface facade differs: {error}") from error
    facade_snapshot = _snapshot(facade_path, label="exact-surface facade blueprint")
    if (
        facade_snapshot.sha256 != contract.sha256(facade_payload)
        or facade_snapshot.sha256 != gate["exact_surface_facade_binding"]["sha256"]
    ):
        raise PhaseBLiveError("exact-surface facade binding differs")
    release_path = Path(facade_root["frozen_v10_validator_binding"]["release_file"])
    v10_context = physical.load_release(release_path)
    release_snapshot = _snapshot(release_path, label="frozen V10 release")

    source_snapshots: list[Any] = []
    for name, binding in envelope["source_bindings"].items():
        snapshot = _snapshot(Path(binding["path"]), label=name)
        if snapshot.sha256 != binding["sha256"] or snapshot.size != binding["bytes"]:
            raise PhaseBLiveError(f"source binding {name} changed")
        source_snapshots.append(snapshot)
    for name, binding in facade_root["exact_response_surface_validation"][
        "source_bindings"
    ].items():
        snapshot = _snapshot(Path(binding["path"]), label=f"response source {name}")
        if snapshot.sha256 != binding["sha256"] or snapshot.size != binding["bytes"]:
            raise PhaseBLiveError(f"response source binding {name} changed")
        source_snapshots.append(snapshot)
    snapshots = tuple(
        {
            str(item.path): item
            for item in (
                envelope_snapshot,
                authority_snapshot,
                gate_snapshot,
                facade_snapshot,
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
    return _PhaseBBundle(
        envelope_path=envelope_path,
        envelope_payload=envelope_payload,
        envelope=envelope,
        envelope_binding=envelope_binding,
        authority_path=authority_path,
        authority_payload=authority_payload,
        authority=authority,
        authority_binding=authority_binding,
        gate_path=gate_path,
        gate_payload=gate_payload,
        gate=gate,
        gate_binding=gate_binding,
        v10_context=v10_context,
        snapshots=snapshots,
        synthetic_test_only=bool(envelope["synthetic_test_only"]),
    )


def required_phase_b_live_authorization(envelope_file: Path) -> str:
    """Derive but do not execute the later exact runner-bound phrase."""

    bundle = _load_bundle(
        envelope_file,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=False,
    )
    return _authorization_phrase(
        bundle.envelope,
        envelope_file_sha256=bundle.envelope_binding["sha256"],
    )


def _assert_sources_unchanged(bundle: _PhaseBBundle) -> None:
    for snapshot in bundle.snapshots:
        try:
            snapshot.assert_unchanged()
        except phase_a_live.PhaseALiveError as error:
            raise PhaseBLiveError(str(error)) from error


def _check_time(
    bundle: _PhaseBBundle,
    *,
    clock: Any,
    label: str,
) -> str:
    if type(clock) not in {
        phase_a_live._SystemUTCClock,  # noqa: SLF001
        phase_a_live._ScriptedUTCClock,  # noqa: SLF001
    }:
        raise PhaseBLiveError("Phase-B clock type differs")
    return _gate_time(bundle.authority, now=clock.wall_now(), label=label)


def _new_endpoint(
    request: Mapping[str, Any], *, synthetic_test_only: bool
) -> dict[str, Any]:
    wire = request["request_wire_ascii"].encode("ascii")
    return {
        "phase_b_ordinal": request["phase_b_ordinal"],
        "full_diagnostic_ordinal": request["full_diagnostic_ordinal"],
        "name": request["name"],
        "method": "GET",
        "path": request["path"],
        "absolute_url": request["absolute_url"],
        "attempt_checkpoint_persisted_before_socket": True,
        "last_completed_gate": "ATTEMPT_CHECKPOINT_PERSISTED",
        "failure_stage": None,
        "application_transport_attempts": 0,
        "socket_constructor_called": False,
        "socket_connect_called": False,
        "socket_connect_returned": False,
        "request_write_called": False,
        "request_write_completed": False,
        "request_bytes_expected": len(wire),
        "request_wire_sha256": contract.sha256(wire),
        "request_wire_base64": base64.b64encode(wire).decode("ascii"),
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
        "status_boot_nonce": None,
        "validation_stack": [
            "raw_http_status_header_content_length_and_close_gate",
            "strict_utf8_duplicate_nan_trailing_root_gate",
            f"source_pinned_exact_v10_{request['name']}_surface",
        ],
        "validation_outcome": "STARTED",
    }


class _RawIPv4PhaseBTransport:
    """Fixed production transport; it has no configurable origin."""

    def perform(
        self,
        *,
        request: Mapping[str, Any],
        endpoint: dict[str, Any],
        clock: Any,
    ) -> Any:
        if type(clock) is not phase_a_live._SystemUTCClock:  # noqa: SLF001
            raise PhaseBLiveError("production Phase-B transport requires system clock")
        wire = request["request_wire_ascii"].encode("ascii")
        endpoint["application_transport_attempts"] = 1
        endpoint["socket_constructor_called"] = True
        endpoint["last_completed_gate"] = "SOCKET_CONSTRUCTOR_CALLED"
        sock: socket.socket | None = None
        deadline = clock.monotonic() + PER_ENDPOINT_TOTAL_TIMEOUT_MS / 1000
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            remaining = deadline - clock.monotonic()
            if remaining <= 0:
                raise PhaseBLiveTransportError("deadline expired before connect")
            sock.settimeout(min(CONNECT_TIMEOUT_MS / 1000, remaining))
            endpoint["socket_connect_called"] = True
            endpoint["last_completed_gate"] = "CONNECT_CALLED"
            try:
                sock.connect((LITERAL_IPV4, PORT))
            except (OSError, TimeoutError) as error:
                raise PhaseBLiveTransportError(
                    f"literal IPv4 connect failed: {error}"
                ) from error
            endpoint["socket_connect_returned"] = True
            endpoint["last_completed_gate"] = "CONNECTED"
            endpoint["request_write_called"] = True
            endpoint["last_completed_gate"] = "REQUEST_WRITE_STARTED"
            view = memoryview(wire)
            while view:
                remaining = deadline - clock.monotonic()
                if remaining <= 0:
                    raise PhaseBLiveTransportError("deadline expired during write")
                sock.settimeout(min(READ_TIMEOUT_MS / 1000, remaining))
                try:
                    written = sock.send(view)
                except (OSError, TimeoutError) as error:
                    raise PhaseBLiveTransportError(
                        f"request write failed: {error}"
                    ) from error
                if written <= 0:
                    raise PhaseBLiveTransportError("request write made no progress")
                endpoint["request_bytes_handed_to_socket_api"] += written
                view = view[written:]
            endpoint["request_write_completed"] = True
            endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
            try:
                return phase_a_live._read_exact_http_response(  # noqa: SLF001
                    phase_a_live._SocketReader(sock, deadline, clock),  # noqa: SLF001
                    endpoint=endpoint,
                )
            except phase_a_live.PhaseALiveError as error:
                raise PhaseBLiveTransportError(str(error)) from error
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


class _ScriptedPhaseBTransport:
    """Private exact synthetic transport with no socket capability."""

    def __init__(self, script: Sequence[tuple[str, bytes | Exception]]) -> None:
        if type(script) not in {list, tuple} or len(script) > 3:
            raise PhaseBLiveError("synthetic Phase-B script shape differs")
        self.script: list[tuple[str, bytes | Exception]] = []
        for name, result in script:
            if name not in ENDPOINT_NAMES or not (
                type(result) is bytes or isinstance(result, Exception)
            ):
                raise PhaseBLiveError("synthetic Phase-B script item differs")
            self.script.append((name, result))
        self.calls: list[str] = []

    def perform(
        self,
        *,
        request: Mapping[str, Any],
        endpoint: dict[str, Any],
        clock: Any,
    ) -> Any:
        if type(clock) is not phase_a_live._ScriptedUTCClock:  # noqa: SLF001
            raise PhaseBLiveError("synthetic Phase-B transport requires test clock")
        index = len(self.calls)
        if index >= len(self.script):
            raise PhaseBLiveError("synthetic Phase-B transport exceeded script")
        expected_name, result = self.script[index]
        if request["name"] != expected_name:
            raise PhaseBLiveError("synthetic Phase-B endpoint order differs")
        self.calls.append(expected_name)
        wire = request["request_wire_ascii"].encode("ascii")
        endpoint["application_transport_attempts"] = 1
        endpoint["request_write_called"] = True
        endpoint["request_write_completed"] = True
        endpoint["request_bytes_handed_to_socket_api"] = len(wire)
        endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
        if isinstance(result, Exception):
            raise result
        try:
            return phase_a_live._read_exact_http_response(  # noqa: SLF001
                phase_a_live._ScriptedReader((result,), terminal_error=None),  # noqa: SLF001
                endpoint=endpoint,
            )
        except phase_a_live.PhaseALiveError as error:
            raise PhaseBLiveTransportError(str(error)) from error


def _finalize_response(
    endpoint: dict[str, Any], response: Any, *, context: Any
) -> None:
    body = response.entity_body
    if not 0 < len(body) <= MAX_RESPONSE_ENTITY_BYTES:
        raise PhaseBLiveError("Phase-B response entity exceeds runner budget")
    endpoint["response_entity_body_bytes"] = len(body)
    endpoint["response_entity_body_sha256"] = contract.sha256(body)
    endpoint["response_entity_body_base64"] = base64.b64encode(body).decode("ascii")
    try:
        parsed, boot_nonce = facade.decode_and_validate_v10_response_bytes(
            str(endpoint["name"]), body, context
        )
    except (facade.StageBFacadeContractError, RecursionError) as error:
        raise PhaseBLiveError(
            f"{endpoint['name']} exact V10 response validation failed: {error}"
        ) from error
    endpoint["strict_parsed_canonical_sha256"] = contract.sha256(parsed)
    endpoint["status_boot_nonce"] = boot_nonce
    endpoint["validation_outcome"] = "PASS"
    endpoint["last_completed_gate"] = "EXACT_V10_VALIDATED"


def _failure_stage(endpoint: Mapping[str, Any]) -> str:
    stages = {
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
    }
    try:
        return stages[str(endpoint["last_completed_gate"])]
    except KeyError as error:
        raise PhaseBLiveError("Phase-B endpoint last gate differs") from error


def _creation_identity(value: Any, *, label: str) -> dict[str, int]:
    try:
        return phase_a_live._validate_creation_identity(value, label=label)  # noqa: SLF001
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _reserve_sink(path: Path, *, label: str) -> tuple[Any, dict[str, int]]:
    try:
        return phase_a_live._reserve_empty_sink(path, label=label)  # noqa: SLF001
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _require_distinct(*identities: Mapping[str, Any], label: str) -> None:
    try:
        phase_a_live._require_distinct_creation_identities(  # noqa: SLF001
            *identities, label=label
        )
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _sink_exact(sink: Any, payload: bytes, *, label: str) -> str:
    try:
        return phase_a_live._assert_sink_exact(sink, payload, label=label)  # noqa: SLF001
    except phase_a_live.PhaseALiveError as error:
        raise PhaseBLiveError(str(error)) from error


def _bounded_error(error: BaseException | None) -> tuple[str | None, str | None]:
    if error is None:
        return None, None
    payload = str(error).encode("utf-8", errors="replace") or b"NO_EXCEPTION_MESSAGE"
    if len(payload) > MAX_ERROR_TEXT_BYTES:
        suffix = b" [TRUNCATED]"
        payload = payload[: MAX_ERROR_TEXT_BYTES - len(suffix)]
        while True:
            try:
                text = payload.decode("utf-8")
                break
            except UnicodeDecodeError:
                payload = payload[:-1]
        text += suffix.decode("ascii")
    else:
        text = payload.decode("utf-8")
    return type(error).__name__, text


def _registry_root(
    bundle: _PhaseBBundle,
    *,
    authorization_sha256: str,
    pre_registry_utc: str,
    creation_identity: Mapping[str, Any],
) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": (
                SYNTHETIC_REGISTRY_KIND
                if bundle.synthetic_test_only
                else LIVE_REGISTRY_KIND
            ),
            "classification": (
                "SYNTHETIC_TEST_ONLY_PHASE_B_ATTEMPT_CONSUMPTION"
                if bundle.synthetic_test_only
                else "LIVE_PHASE_B_PERMANENT_ATTEMPT_CONSUMPTION"
            ),
            "state": "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_SOCKET",
            "synthetic_test_only": bundle.synthetic_test_only,
            "live_envelope_binding": dict(bundle.envelope_binding),
            "live_authority_binding": dict(bundle.authority_binding),
            "offline_gate_binding": dict(bundle.gate_binding),
            "live_attempt_id": bundle.envelope["attempt"]["live_attempt_id"],
            "authority_attempt_id": bundle.envelope["attempt"]["authority_attempt_id"],
            "authorization_phrase_sha256": authorization_sha256,
            "authorization_phrase_stored": False,
            "fresh_gate_canonical_sha256": bundle.authority[
                "fresh_phase_b_onsite_gate"
            ]["gate_canonical_sha256"],
            "pre_registry_system_utc": pre_registry_utc,
            "creation_identity": dict(creation_identity),
            "terminal_receipt_file": bundle.envelope["attempt"][
                "terminal_receipt_file"
            ],
            "registry_created_before_output": True,
            "registry_created_before_socket": True,
            "immutable_after_initial_o_excl_write": True,
            "network_requests_before_registry": 0,
            "socket_constructors_before_registry": 0,
            "retry_allowed": False,
            "registry_never_deleted": True,
            "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        }
    )


def _receipt_root(
    bundle: _PhaseBBundle,
    *,
    state: str,
    authorization_sha256: str,
    registry_path: Path,
    registry_sha256: str,
    registry_canonical_sha256: str,
    registry_creation_identity: Mapping[str, Any],
    registry_parent_fsync: str,
    output_creation_identity: Mapping[str, Any],
    output_parent_fsync: str,
    checkpoint_bytes: int | None,
    checkpoint_sha256: str | None,
    checkpoint_canonical_sha256: str | None,
    temp_creation_identity: Mapping[str, Any] | None,
    temp_parent_fsync: str,
    execution_observed_utc: str,
    pre_registry_utc: str,
    pre_connect_times: Sequence[str],
    endpoint_outcomes: Sequence[Mapping[str, Any]],
    success: bool,
    error: BaseException | None,
) -> dict[str, Any]:
    error_type, error_text = _bounded_error(error)
    endpoints = deepcopy(list(endpoint_outcomes))
    attempts = sum(item["application_transport_attempts"] for item in endpoints)
    write_calls = sum(bool(item["request_write_called"]) for item in endpoints)
    complete_gets = sum(bool(item["request_write_completed"]) for item in endpoints)
    handed = sum(item["request_bytes_handed_to_socket_api"] for item in endpoints)
    responses = sum(
        item["raw_status_and_header_bytes"] is not None for item in endpoints
    )
    validated = [
        item["name"] for item in endpoints if item["validation_outcome"] == "PASS"
    ]
    status_nonce = next(
        (item["status_boot_nonce"] for item in endpoints if item["name"] == "status"),
        None,
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            SYNTHETIC_RECEIPT_KIND if bundle.synthetic_test_only else LIVE_RECEIPT_KIND
        ),
        "classification": (
            "SYNTHETIC_TEST_ONLY_PHASE_B_RECEIPT_NEVER_LIVE_EVIDENCE"
            if bundle.synthetic_test_only
            else "PHASE_B_READ_ONLY_PROTOCOL_RESPONSE_CONFORMANCE_ONLY"
        ),
        "state": state,
        "synthetic_test_only": bundle.synthetic_test_only,
        "live_envelope_binding": dict(bundle.envelope_binding),
        "live_authority_binding": dict(bundle.authority_binding),
        "offline_gate_binding": dict(bundle.gate_binding),
        "live_attempt_id": bundle.envelope["attempt"]["live_attempt_id"],
        "authorization_phrase_sha256": authorization_sha256,
        "authorization_phrase_stored": False,
        "fresh_gate_canonical_sha256": bundle.authority["fresh_phase_b_onsite_gate"][
            "gate_canonical_sha256"
        ],
        "execution_observed_utc": execution_observed_utc,
        "pre_registry_system_utc": pre_registry_utc,
        "pre_connect_system_utc": list(pre_connect_times),
        "attempt_registry_file": str(registry_path),
        "registry_whole_file_sha256": registry_sha256,
        "registry_canonical_sha256": registry_canonical_sha256,
        "registry_creation_identity": dict(registry_creation_identity),
        "registry_parent_directory_fsync_status": registry_parent_fsync,
        "output_creation_identity": dict(output_creation_identity),
        "output_parent_directory_fsync_status": output_parent_fsync,
        "checkpoint_whole_file_bytes": checkpoint_bytes,
        "checkpoint_whole_file_sha256": checkpoint_sha256,
        "checkpoint_canonical_sha256": checkpoint_canonical_sha256,
        "finalization_temp_creation_identity": (
            None if temp_creation_identity is None else dict(temp_creation_identity)
        ),
        "finalization_temp_parent_directory_fsync_status": temp_parent_fsync,
        "terminal_receipt_file": bundle.envelope["attempt"]["terminal_receipt_file"],
        "finalization_temp_file": bundle.envelope["attempt"]["finalization_temp_file"],
        "terminalization_requires_temp_o_excl_then_atomic_replace": True,
        "payload_does_not_self_assert_atomic_replace_commit": True,
        "atomic_compare_and_swap_proven": False,
        "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        "phase_a_version_replayed_offline_before_registry": True,
        "phase_a_version_requested_again": False,
        "endpoint_outcomes": endpoints,
        "validated_response_names": validated,
        "status_boot_nonce": status_nonce,
        "status_boot_nonce_correlated_to_phase_a": False,
        "maximum_application_transport_attempts": 3,
        "application_transport_attempts": attempts,
        "request_write_calls": write_calls,
        "request_bytes_handed_to_socket_api": handed,
        "fully_written_gets": complete_gets,
        "http_responses_with_complete_status_headers": responses,
        "post_requests": 0,
        "request_bodies": 0,
        "device_api_claim_requests": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "dns_proxy_redirect_scan_fallback_retry_requests": 0,
        "serial_or_com_accesses": 0,
        "retry_allowed": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "manifest_status_report_protocol_response_conformance": success,
        "success_classification": SUCCESS_CLASSIFICATION if success else None,
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_post_reset_application_boot_proven": False,
        "active_application_or_ota_slot_proven": False,
        "visible_action_authorized": False,
        "visible_authority_token_or_claim_generated": False,
        "actual_device_or_background_side_effects": (
            "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
            if bundle.synthetic_test_only
            else "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
        ),
        "error_type": error_type,
        "error": error_text,
    }
    sealed = _seal(unsigned)
    if len(contract.canonical_json_bytes(sealed) + b"\n") > MAX_TERMINAL_RECEIPT_BYTES:
        raise PhaseBLiveError("Phase-B terminal receipt exceeds loader budget")
    return sealed


def _decode_bundle(
    *, value: Any, length: Any, sha256: Any, label: str, maximum: int
) -> bytes:
    if type(value) is not str or type(length) is not int or type(sha256) is not str:
        raise PhaseBLiveError(f"{label} evidence type differs")
    if length < 0 or length > maximum or HEX64.fullmatch(sha256) is None:
        raise PhaseBLiveError(f"{label} evidence bounds/hash differs")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PhaseBLiveError(f"{label} base64 differs") from error
    if len(decoded) != length or contract.sha256(decoded) != sha256:
        raise PhaseBLiveError(f"{label} evidence length/hash differs")
    return decoded


def _validate_optional_bundle(
    endpoint: Mapping[str, Any], *, prefix: str, maximum: int
) -> bytes:
    length = endpoint[f"{prefix}_bytes"]
    sha = endpoint[f"{prefix}_sha256"]
    encoded = endpoint[f"{prefix}_base64"]
    if length == 0:
        if sha is not None or encoded is not None:
            raise PhaseBLiveError(f"{prefix} empty evidence differs")
        return b""
    return _decode_bundle(
        value=encoded,
        length=length,
        sha256=sha,
        label=prefix,
        maximum=maximum,
    )


def _validate_endpoint(
    endpoint: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    context: Any,
    terminal_success: bool,
) -> None:
    if type(endpoint) is not dict:
        raise PhaseBLiveError("Phase-B endpoint evidence type differs")
    for key in endpoint:
        if key.startswith("_"):
            raise PhaseBLiveError("private endpoint accumulator escaped receipt")
    fixed = {
        "phase_b_ordinal": request["phase_b_ordinal"],
        "full_diagnostic_ordinal": request["full_diagnostic_ordinal"],
        "name": request["name"],
        "method": "GET",
        "path": request["path"],
        "absolute_url": request["absolute_url"],
        "attempt_checkpoint_persisted_before_socket": True,
        "request_bytes_expected": request["request_wire_bytes"],
        "request_wire_sha256": request["request_wire_sha256"],
    }
    if any(
        not _strict_json_equal(endpoint.get(key), value) for key, value in fixed.items()
    ):
        raise PhaseBLiveError(f"{request['name']} fixed endpoint evidence differs")
    wire = _decode_bundle(
        value=endpoint["request_wire_base64"],
        length=endpoint["request_bytes_expected"],
        sha256=endpoint["request_wire_sha256"],
        label=f"{request['name']} request wire",
        maximum=1024,
    )
    if wire != request["request_wire_ascii"].encode("ascii"):
        raise PhaseBLiveError(f"{request['name']} request wire bytes differ")
    if endpoint["application_transport_attempts"] not in {0, 1}:
        raise PhaseBLiveError("endpoint application attempt count differs")
    handed = endpoint["request_bytes_handed_to_socket_api"]
    if type(handed) is not int or not 0 <= handed <= len(wire):
        raise PhaseBLiveError("endpoint handed byte count differs")
    if endpoint["request_write_completed"] is True and handed != len(wire):
        raise PhaseBLiveError("completed request did not hand all bytes")
    if endpoint["request_wire_emitted"] not in {
        "UNKNOWN",
        "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY",
    } or endpoint["peer_received_request"] not in {
        "UNKNOWN",
        "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY",
    }:
        raise PhaseBLiveError("wire/peer uncertainty evidence differs")
    prefix = _validate_optional_bundle(
        endpoint,
        prefix="bounded_response_prefix",
        maximum=phase_a_live.MAX_BOUNDED_RESPONSE_PREFIX_BYTES,
    )
    partial = _validate_optional_bundle(
        endpoint,
        prefix="partial_response_entity",
        maximum=MAX_RESPONSE_ENTITY_BYTES,
    )
    beyond = _validate_optional_bundle(
        endpoint,
        prefix="beyond_content_length",
        maximum=phase_a_live.MAX_BEYOND_CONTENT_LENGTH_EVIDENCE_BYTES,
    )
    if len(prefix) > endpoint["observed_response_octets_total"]:
        raise PhaseBLiveError("bounded response prefix exceeds observed octets")
    if beyond and endpoint["validation_outcome"] == "PASS":
        raise PhaseBLiveError("successful endpoint contains overlong evidence")

    raw_headers: bytes | None = None
    if endpoint["raw_status_and_header_bytes"] is None:
        if any(
            endpoint[key] is not None
            for key in (
                "raw_status_and_header_sha256",
                "raw_status_and_header_base64",
                "http_status",
                "response_headers",
            )
        ):
            raise PhaseBLiveError("absent raw header evidence is inconsistent")
    else:
        raw_headers = _decode_bundle(
            value=endpoint["raw_status_and_header_base64"],
            length=endpoint["raw_status_and_header_bytes"],
            sha256=endpoint["raw_status_and_header_sha256"],
            label=f"{request['name']} raw status/headers",
            maximum=phase_a_live.MAX_STATUS_HEADER_BYTES,
        )
        try:
            parsed_http = phase_a_live._parse_status_and_headers(raw_headers)  # noqa: SLF001
        except phase_a_live.PhaseALiveError as error:
            raise PhaseBLiveError(str(error)) from error
        if endpoint["http_status"] != 200 or endpoint["response_headers"] != [
            list(item) for item in parsed_http.headers
        ]:
            raise PhaseBLiveError("parsed HTTP evidence differs")

    passed = endpoint["validation_outcome"] == "PASS"
    if passed:
        if not terminal_success and endpoint["failure_stage"] is not None:
            raise PhaseBLiveError("passed prefix endpoint has failure stage")
        if endpoint["last_completed_gate"] != "EXACT_V10_VALIDATED":
            raise PhaseBLiveError("passed endpoint last gate differs")
        if endpoint["failure_stage"] is not None or raw_headers is None:
            raise PhaseBLiveError("passed endpoint evidence is incomplete")
        body = _decode_bundle(
            value=endpoint["response_entity_body_base64"],
            length=endpoint["response_entity_body_bytes"],
            sha256=endpoint["response_entity_body_sha256"],
            label=f"{request['name']} response entity",
            maximum=MAX_RESPONSE_ENTITY_BYTES,
        )
        if partial != body or prefix != raw_headers + body:
            raise PhaseBLiveError("passed endpoint lossless response evidence differs")
        try:
            parsed, nonce = facade.decode_and_validate_v10_response_bytes(
                request["name"], body, context
            )
        except facade.StageBFacadeContractError as error:
            raise PhaseBLiveError(
                f"persisted exact V10 replay failed: {error}"
            ) from error
        if (
            endpoint["strict_parsed_canonical_sha256"] != contract.sha256(parsed)
            or endpoint["status_boot_nonce"] != nonce
        ):
            raise PhaseBLiveError("persisted parsed response evidence differs")
    else:
        if endpoint["validation_outcome"] != "FAILED_TERMINAL_NO_RETRY":
            raise PhaseBLiveError("failed endpoint outcome differs")
        if type(endpoint["failure_stage"]) is not str:
            raise PhaseBLiveError("failed endpoint lacks failure stage")


def _validate_receipt_root(
    root: Mapping[str, Any],
    *,
    bundle: _PhaseBBundle,
    terminal_success: bool,
) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-B terminal receipt")
    synthetic = bundle.synthetic_test_only
    if root.get("synthetic_test_only") is not synthetic:
        raise PhaseBLiveError("receipt synthetic flag differs")
    expected_kind = SYNTHETIC_RECEIPT_KIND if synthetic else LIVE_RECEIPT_KIND
    expected_state = (
        "TERMINAL_SUCCESS_V10_MANIFEST_STATUS_REPORT_PROTOCOL_RESPONSE_CONFORMANCE"
        if terminal_success
        else "TERMINAL_FAILURE_NO_RETRY"
    )
    if root.get("kind") != expected_kind or root.get("state") != expected_state:
        raise PhaseBLiveError("Phase-B receipt kind/state differs")
    for key, expected in (
        ("live_envelope_binding", bundle.envelope_binding),
        ("live_authority_binding", bundle.authority_binding),
        ("offline_gate_binding", bundle.gate_binding),
    ):
        if not _strict_json_equal(root.get(key), expected):
            raise PhaseBLiveError(f"receipt {key} differs")
    endpoints = root.get("endpoint_outcomes")
    if type(endpoints) is not list or len(endpoints) > 3:
        raise PhaseBLiveError("receipt endpoint count differs")
    requests = bundle.envelope["ordered_requests"]
    passed_names: list[str] = []
    saw_failure = False
    for endpoint, request in zip(endpoints, requests, strict=False):
        passed = endpoint.get("validation_outcome") == "PASS"
        if saw_failure:
            raise PhaseBLiveError("endpoint exists after a terminal failure")
        _validate_endpoint(
            endpoint,
            request=request,
            context=bundle.v10_context,
            terminal_success=terminal_success,
        )
        if passed:
            passed_names.append(request["name"])
        else:
            saw_failure = True
    if terminal_success:
        if len(endpoints) != 3 or passed_names != list(ENDPOINT_NAMES):
            raise PhaseBLiveError("terminal success lacks three validated endpoints")
        if root.get("error_type") is not None or root.get("error") is not None:
            raise PhaseBLiveError("terminal success contains an error")
    else:
        if len(endpoints) == 3 and passed_names == list(ENDPOINT_NAMES):
            raise PhaseBLiveError("terminal failure contains full conformance")
        if (
            type(root.get("error_type")) is not str
            or type(root.get("error")) is not str
        ):
            raise PhaseBLiveError("terminal failure lacks bounded error")
    if root.get("validated_response_names") != passed_names:
        raise PhaseBLiveError("validated endpoint name summary differs")
    attempts = sum(item["application_transport_attempts"] for item in endpoints)
    handed = sum(item["request_bytes_handed_to_socket_api"] for item in endpoints)
    if (
        root.get("application_transport_attempts") != attempts
        or root.get("request_bytes_handed_to_socket_api") != handed
    ):
        raise PhaseBLiveError("receipt transport summary differs")
    exact_zero = (
        "post_requests",
        "request_bodies",
        "device_api_claim_requests",
        "client_mutation_requests",
        "client_visible_refresh_requests",
        "dns_proxy_redirect_scan_fallback_retry_requests",
        "serial_or_com_accesses",
    )
    if any(root.get(key) != 0 for key in exact_zero):
        raise PhaseBLiveError("receipt zero-operation boundary differs")
    if any(
        root.get(key) is not False
        for key in (
            "responder_or_device_identity_proven",
            "trusted_ip_binding_proven",
            "fresh_post_reset_application_boot_proven",
            "active_application_or_ota_slot_proven",
            "visible_action_authorized",
            "visible_authority_token_or_claim_generated",
            "retry_allowed",
            "automatic_recovery",
            "automatic_chaining",
        )
    ):
        raise PhaseBLiveError("receipt proof/authority boundary differs")
    if (
        root.get("manifest_status_report_protocol_response_conformance")
        is not terminal_success
    ):
        raise PhaseBLiveError("receipt success boolean differs")
    return {
        "valid": True,
        "canonical_sha256": canonical,
        "terminal_success": terminal_success,
        "validated_response_names": passed_names,
        "application_transport_attempts": attempts,
        "visible_action_authorized": False,
        "responder_or_device_identity_proven": False,
    }


def _execute_loaded_bundle(
    bundle: _PhaseBBundle,
    *,
    authorization: str,
    clock: Any,
    synthetic_transport: _ScriptedPhaseBTransport | None,
) -> dict[str, Any]:
    synthetic = bundle.synthetic_test_only
    if synthetic:
        if (
            type(clock) is not phase_a_live._ScriptedUTCClock  # noqa: SLF001
            or type(synthetic_transport) is not _ScriptedPhaseBTransport
        ):
            raise PhaseBLiveError("synthetic Phase-B execution requires private types")
    elif (
        type(clock) is not phase_a_live._SystemUTCClock  # noqa: SLF001
        or synthetic_transport is not None
    ):
        raise PhaseBLiveError("production Phase-B rejects injected clock/transport")
    required = _authorization_phrase(
        bundle.envelope,
        envelope_file_sha256=bundle.envelope_binding["sha256"],
    )
    if type(authorization) is not str or authorization != required:
        raise PhaseBLiveError("exact runner-bound Phase-B authorization differs")
    try:
        authorization_ascii = authorization.encode("ascii")
    except UnicodeEncodeError as error:
        raise PhaseBLiveError("Phase-B authorization is not ASCII") from error

    execution_observed_utc = _check_time(
        bundle, clock=clock, label="pre-registry Phase-B time"
    )
    pre_registry_utc = execution_observed_utc
    _assert_sources_unchanged(bundle)
    attempt = bundle.envelope["attempt"]
    registry_path = _safe_absolute(
        Path(attempt["registry_file"]), label="Phase-B registry"
    )
    output_path = _safe_absolute(
        Path(attempt["terminal_receipt_file"]), label="Phase-B terminal receipt"
    )
    temp_path = _safe_absolute(
        Path(attempt["finalization_temp_file"]), label="Phase-B finalization temp"
    )
    for label, path in (
        ("Phase-B registry", registry_path),
        ("Phase-B terminal receipt", output_path),
        ("Phase-B finalization temp", temp_path),
    ):
        if _directory_entry_exists(path):
            raise PhaseBLiveError(f"{label} already exists; no retry")

    auth_sha = contract.sha256(authorization_ascii)
    registry, registry_identity = _reserve_sink(
        registry_path, label="Phase-B immutable registry"
    )
    output: Any | None = None
    final_temp: Any | None = None
    try:
        registry_root = _registry_root(
            bundle,
            authorization_sha256=auth_sha,
            pre_registry_utc=pre_registry_utc,
            creation_identity=registry_identity,
        )
        registry_payload = contract.canonical_json_bytes(registry_root) + b"\n"
        registry.replace(registry_root)
        registry_sha = _sink_exact(
            registry, registry_payload, label="Phase-B immutable registry"
        )
        output, output_identity = _reserve_sink(
            output_path, label="Phase-B output checkpoint"
        )
        _require_distinct(
            registry_identity,
            output_identity,
            label="Phase-B registry/output checkpoint",
        )
        checkpoint = _receipt_root(
            bundle,
            state=(
                "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
                "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
            ),
            authorization_sha256=auth_sha,
            registry_path=registry_path,
            registry_sha256=registry_sha,
            registry_canonical_sha256=registry_root["integrity"]["canonical_sha256"],
            registry_creation_identity=registry_identity,
            registry_parent_fsync=registry.parent_directory_fsync_status,
            output_creation_identity=output_identity,
            output_parent_fsync=output.parent_directory_fsync_status,
            checkpoint_bytes=None,
            checkpoint_sha256=None,
            checkpoint_canonical_sha256=None,
            temp_creation_identity=None,
            temp_parent_fsync="NOT_CREATED_BEFORE_TERMINAL_FINALIZATION",
            execution_observed_utc=execution_observed_utc,
            pre_registry_utc=pre_registry_utc,
            pre_connect_times=[],
            endpoint_outcomes=[],
            success=False,
            error=PhaseBLiveError(
                "crash or process interruption after permanent Phase-B consumption"
            ),
        )
        checkpoint_payload = contract.canonical_json_bytes(checkpoint) + b"\n"
        output.replace(checkpoint)
        checkpoint_sha = _sink_exact(
            output, checkpoint_payload, label="Phase-B persisted checkpoint"
        )

        outcomes: list[dict[str, Any]] = []
        pre_connect_times: list[str] = []
        success = False
        error: BaseException | None = None
        try:
            for request in bundle.envelope["ordered_requests"]:
                registry.assert_identity()
                output.assert_identity()
                if registry.whole_file_sha256() != registry_sha:
                    raise PhaseBLiveError("Phase-B registry changed before socket")
                if output.whole_file_sha256() != checkpoint_sha:
                    raise PhaseBLiveError("Phase-B checkpoint changed before socket")
                _assert_sources_unchanged(bundle)
                pre_connect_times.append(
                    _check_time(
                        bundle,
                        clock=clock,
                        label=f"pre-connect {request['name']} Phase-B time",
                    )
                )
                registry.assert_identity()
                output.assert_identity()
                _assert_sources_unchanged(bundle)
                endpoint = _new_endpoint(request, synthetic_test_only=synthetic)
                outcomes.append(endpoint)
                if synthetic:
                    if synthetic_transport is None:
                        raise PhaseBLiveError("synthetic Phase-B transport is absent")
                    response = synthetic_transport.perform(
                        request=request, endpoint=endpoint, clock=clock
                    )
                else:
                    response = _RawIPv4PhaseBTransport().perform(
                        request=request, endpoint=endpoint, clock=clock
                    )
                _finalize_response(endpoint, response, context=bundle.v10_context)
            success = True
        except BaseException as caught:
            error = caught

        if error is not None and not isinstance(error, Exception):
            raise error
        try:
            for endpoint in outcomes:
                phase_a_live._finalize_bounded_response_evidence(endpoint)  # noqa: SLF001
            if error is not None and outcomes:
                failed = outcomes[-1]
                if failed["validation_outcome"] != "PASS":
                    failed["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
                    failed["failure_stage"] = _failure_stage(failed)
            state = (
                "TERMINAL_SUCCESS_V10_MANIFEST_STATUS_REPORT_PROTOCOL_RESPONSE_CONFORMANCE"
                if success
                else "TERMINAL_FAILURE_NO_RETRY"
            )
            candidate = _receipt_root(
                bundle,
                state=state,
                authorization_sha256=auth_sha,
                registry_path=registry_path,
                registry_sha256=registry_sha,
                registry_canonical_sha256=registry_root["integrity"][
                    "canonical_sha256"
                ],
                registry_creation_identity=registry_identity,
                registry_parent_fsync=registry.parent_directory_fsync_status,
                output_creation_identity=output_identity,
                output_parent_fsync=output.parent_directory_fsync_status,
                checkpoint_bytes=len(checkpoint_payload),
                checkpoint_sha256=checkpoint_sha,
                checkpoint_canonical_sha256=checkpoint["integrity"]["canonical_sha256"],
                temp_creation_identity=None,
                temp_parent_fsync="PENDING_O_EXCL_FINALIZATION_TEMP",
                execution_observed_utc=execution_observed_utc,
                pre_registry_utc=pre_registry_utc,
                pre_connect_times=pre_connect_times,
                endpoint_outcomes=outcomes,
                success=success,
                error=error,
            )
            _validate_receipt_root(candidate, bundle=bundle, terminal_success=success)
        except BaseException:
            if error is not None:
                raise error
            raise

        final_temp, temp_identity = _reserve_sink(
            temp_path, label="Phase-B finalization temp"
        )
        _require_distinct(
            registry_identity,
            output_identity,
            temp_identity,
            label="Phase-B registry/checkpoint/temp",
        )
        if output_identity["st_dev"] != temp_identity["st_dev"]:
            raise PhaseBLiveError("Phase-B output/temp are not on one volume")
        terminal = _receipt_root(
            bundle,
            state=state,
            authorization_sha256=auth_sha,
            registry_path=registry_path,
            registry_sha256=registry_sha,
            registry_canonical_sha256=registry_root["integrity"]["canonical_sha256"],
            registry_creation_identity=registry_identity,
            registry_parent_fsync=registry.parent_directory_fsync_status,
            output_creation_identity=output_identity,
            output_parent_fsync=output.parent_directory_fsync_status,
            checkpoint_bytes=len(checkpoint_payload),
            checkpoint_sha256=checkpoint_sha,
            checkpoint_canonical_sha256=checkpoint["integrity"]["canonical_sha256"],
            temp_creation_identity=temp_identity,
            temp_parent_fsync=final_temp.parent_directory_fsync_status,
            execution_observed_utc=execution_observed_utc,
            pre_registry_utc=pre_registry_utc,
            pre_connect_times=pre_connect_times,
            endpoint_outcomes=outcomes,
            success=success,
            error=error,
        )
        _validate_receipt_root(terminal, bundle=bundle, terminal_success=success)
        terminal_payload = contract.canonical_json_bytes(terminal) + b"\n"
        final_temp.replace(terminal)
        terminal_sha = _sink_exact(
            final_temp, terminal_payload, label="Phase-B uncommitted terminal temp"
        )
        final_temp.close()
        final_temp = None
        registry.assert_identity()
        output.assert_identity()
        if registry.whole_file_sha256() != registry_sha:
            raise PhaseBLiveError("Phase-B registry changed before atomic replace")
        if output.whole_file_sha256() != checkpoint_sha:
            raise PhaseBLiveError("Phase-B checkpoint changed before atomic replace")
        _assert_sources_unchanged(bundle)
        output.close()
        output = None
        checkpoint_snapshot = _snapshot(output_path, label="Phase-B checkpoint")
        temp_snapshot = _snapshot(temp_path, label="Phase-B finalization temp")
        if (
            checkpoint_snapshot.sha256 != checkpoint_sha
            or temp_snapshot.sha256 != terminal_sha
        ):
            raise PhaseBLiveError("Phase-B pre-replace path bytes differ")
        os.replace(temp_path, output_path)
        if _directory_entry_exists(temp_path):
            raise PhaseBLiveError("Phase-B temp remains after atomic replace")
        phase_a._fsync_parent_directory(output_path)  # noqa: SLF001
        final_snapshot = _snapshot(output_path, label="Phase-B terminal receipt")
        if final_snapshot.sha256 != terminal_sha:
            raise PhaseBLiveError("Phase-B committed receipt bytes differ")
        return terminal
    finally:
        if final_temp is not None:
            final_temp.close()
        if output is not None:
            output.close()
        registry.close()


def execute_phase_b_live_once(
    envelope_file: Path, *, authorization: str
) -> dict[str, Any]:
    """Public fixed three-GET executor with no injectable network surface."""

    bundle = _load_bundle(
        envelope_file,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=False,
    )
    return _execute_loaded_bundle(
        bundle,
        authorization=authorization,
        clock=phase_a_live._SystemUTCClock(),  # noqa: SLF001
        synthetic_transport=None,
    )


def _execute_phase_b_synthetic_test_only(
    envelope_file: Path,
    *,
    authorization: str,
    clock: Any,
    transport: _ScriptedPhaseBTransport,
) -> dict[str, Any]:
    bundle = _load_bundle(
        envelope_file,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=True,
    )
    if not bundle.synthetic_test_only:
        raise PhaseBLiveError("private synthetic executor rejects production envelope")
    return _execute_loaded_bundle(
        bundle,
        authorization=authorization,
        clock=clock,
        synthetic_transport=transport,
    )


def _validate_registry_file(
    path: Path, *, bundle: _PhaseBBundle
) -> tuple[Mapping[str, Any], bytes]:
    registry_path, payload, root = _read_json(path, label="Phase-B registry")
    _validate_seal(root, label="Phase-B registry")
    expected_kind = (
        SYNTHETIC_REGISTRY_KIND if bundle.synthetic_test_only else LIVE_REGISTRY_KIND
    )
    if root.get("kind") != expected_kind or root.get("state") != (
        "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_SOCKET"
    ):
        raise PhaseBLiveError("Phase-B registry kind/state differs")
    if registry_path != Path(bundle.envelope["attempt"]["registry_file"]):
        raise PhaseBLiveError("Phase-B registry path differs")
    for key, expected in (
        ("live_envelope_binding", bundle.envelope_binding),
        ("live_authority_binding", bundle.authority_binding),
        ("offline_gate_binding", bundle.gate_binding),
    ):
        if not _strict_json_equal(root.get(key), expected):
            raise PhaseBLiveError(f"Phase-B registry {key} differs")
    _creation_identity(root["creation_identity"], label="registry creation identity")
    return root, payload


def _validate_terminal_file(
    envelope_file: Path,
    *,
    require_success: bool | None,
    allow_synthetic_test_only: bool,
) -> dict[str, Any]:
    bundle = _load_bundle(
        envelope_file,
        require_attempt_paths_absent=False,
        allow_synthetic_test_only=allow_synthetic_test_only,
    )
    registry_path = Path(bundle.envelope["attempt"]["registry_file"])
    output_path = Path(bundle.envelope["attempt"]["terminal_receipt_file"])
    temp_path = Path(bundle.envelope["attempt"]["finalization_temp_file"])
    registry, registry_payload = _validate_registry_file(registry_path, bundle=bundle)
    _, output_payload, root = _read_json(output_path, label="Phase-B terminal receipt")
    success = root.get("state") == (
        "TERMINAL_SUCCESS_V10_MANIFEST_STATUS_REPORT_PROTOCOL_RESPONSE_CONFORMANCE"
    )
    if require_success is not None and success is not require_success:
        raise PhaseBLiveError("Phase-B terminal success requirement differs")
    summary = _validate_receipt_root(root, bundle=bundle, terminal_success=success)
    if (
        root["registry_whole_file_sha256"] != contract.sha256(registry_payload)
        or root["registry_canonical_sha256"]
        != registry["integrity"]["canonical_sha256"]
    ):
        raise PhaseBLiveError("Phase-B receipt registry binding differs")
    if _directory_entry_exists(temp_path):
        raise PhaseBLiveError("Phase-B committed receipt still has temp path")
    summary.update(
        {
            "terminal_outcome_committed": True,
            "terminal_receipt_file_sha256": contract.sha256(output_payload),
            "attempt_permanently_consumed": True,
            "retry_allowed": False,
            "phase_a_version_repeated": False,
            "post_body_claim_mutation_visible_refresh_requests": 0,
        }
    )
    return summary


def validate_phase_b_live_terminal_receipt(
    envelope_file: Path, *, require_success: bool | None = None
) -> dict[str, Any]:
    """Deep-validate one committed production terminal receipt."""

    return _validate_terminal_file(
        envelope_file,
        require_success=require_success,
        allow_synthetic_test_only=False,
    )


def _add_fresh_gate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--prepared-at", required=True)
    parser.add_argument("--current-reading-a", required=True)
    parser.add_argument("--locator-selection-phrase", required=True)
    for name in (
        "j2-off",
        "screen-clean-white",
        "esp32-usb-connected",
        "supply-3v3-cv-normal",
        "temperature-exact-25c",
        "current-limit-exact-1a",
        "current-and-temperature-monitors-ready",
        "physical-cutoff-ready",
        "no-reset-since-stage-a",
        "no-flash-since-stage-a",
        "no-refresh-since-stage-a",
        "no-rewire-since-stage-a",
    ):
        parser.add_argument(f"--confirm-{name}", action="store_true", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("build-review")
    review.add_argument("--offline-gate", type=Path, required=True)
    review.add_argument("--test-file", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    validate_review = sub.add_parser("validate-review")
    validate_review.add_argument("review", type=Path)

    authority = sub.add_parser("prepare-authority")
    authority.add_argument("--offline-gate", type=Path, required=True)
    authority.add_argument("--output", type=Path, required=True)
    _add_fresh_gate_args(authority)
    validate_authority = sub.add_parser("validate-authority")
    validate_authority.add_argument("authority", type=Path)

    envelope = sub.add_parser("prepare-envelope")
    envelope.add_argument("--authority", type=Path, required=True)
    envelope.add_argument("--output", type=Path, required=True)
    envelope.add_argument("--built-at", required=True)
    validate_envelope = sub.add_parser("validate-envelope")
    validate_envelope.add_argument("envelope", type=Path)

    execute = sub.add_parser("execute")
    execute.add_argument("--envelope", type=Path, required=True)
    execute.add_argument("--authorization", required=True)
    validate_receipt = sub.add_parser("validate-receipt")
    validate_receipt.add_argument("envelope", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build-review":
            root = materialize_runner_review(
                offline_gate_file=args.offline_gate,
                runner_review_file=args.output,
                test_file=args.test_file,
            )
            write_new_runner_review(args.output, root)
            result: Mapping[str, Any] = validate_runner_review(root)
        elif args.command == "validate-review":
            _, _, root = _read_json(args.review, label="Phase-B runner review")
            result = validate_runner_review(root)
        elif args.command == "prepare-authority":
            root = materialize_phase_b_live_authority(
                offline_gate_file=args.offline_gate,
                live_authority_file=args.output,
                observed_at=args.observed_at,
                prepared_at=args.prepared_at,
                current_reading_a=args.current_reading_a,
                locator_selection_phrase=args.locator_selection_phrase,
                j2_off=args.confirm_j2_off,
                screen_clean_white=args.confirm_screen_clean_white,
                esp32_usb_connected=args.confirm_esp32_usb_connected,
                supply_3v3_cv_normal=args.confirm_supply_3v3_cv_normal,
                temperature_exact_25c=args.confirm_temperature_exact_25c,
                current_limit_exact_1a=args.confirm_current_limit_exact_1a,
                current_and_temperature_monitors_ready=(
                    args.confirm_current_and_temperature_monitors_ready
                ),
                physical_cutoff_ready=args.confirm_physical_cutoff_ready,
                no_reset_since_stage_a=args.confirm_no_reset_since_stage_a,
                no_flash_since_stage_a=args.confirm_no_flash_since_stage_a,
                no_refresh_since_stage_a=args.confirm_no_refresh_since_stage_a,
                no_rewire_since_stage_a=args.confirm_no_rewire_since_stage_a,
            )
            write_new_phase_b_live_authority(args.output, root)
            result = validate_phase_b_live_authority(root)
        elif args.command == "validate-authority":
            _, _, root = _read_json(args.authority, label="Phase-B live authority")
            result = validate_phase_b_live_authority(root)
        elif args.command == "prepare-envelope":
            root = materialize_phase_b_live_execution_envelope(
                live_authority_file=args.authority,
                live_envelope_file=args.output,
                built_at=args.built_at,
            )
            write_new_phase_b_live_execution_envelope(args.output, root)
            result = validate_phase_b_live_execution_envelope(root)
        elif args.command == "validate-envelope":
            _, _, root = _read_json(args.envelope, label="Phase-B live envelope")
            result = validate_phase_b_live_execution_envelope(root)
        elif args.command == "execute":
            result = execute_phase_b_live_once(
                args.envelope, authorization=args.authorization
            )
        elif args.command == "validate-receipt":
            result = validate_phase_b_live_terminal_receipt(args.envelope)
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (PhaseBLiveError, OSError) as error:
        print(contract.canonical_json_bytes({"error": str(error)}).decode("utf-8"))
        return 1
    print(contract.canonical_json_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
