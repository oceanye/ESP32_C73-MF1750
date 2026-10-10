"""Narrow, immutable identity rebind for the no-iSerial MF17506 relay.

``build`` and ``validate`` are strictly local/offline operations.  The only
hardware-capable entry point is ``query-bound``: it deep-validates a sealed
rebind, passes that exact identity to ``connect(expected_identity)``, and sends
one state query.  This module deliberately exposes no relay ON/OFF command and
no panel, MCU, network, flash, reset, or refresh operation.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from .relay_contract import (
    RelayAdapter,
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)
from .relay_zave_ch340_2ch import (
    MODEL,
    NO_USB_SERIAL,
    PID,
    VID,
    ZaveCh340TwoChannelRelay,
    discover_present_bindings,
)


SCHEMA_VERSION = 1
KIND = "mf17506-zave-relay-narrow-rebind"
MANUAL_DECLARATION_KIND = "mf17506-zave-relay-manual-physical-declaration"
QUERY_RECEIPT_KIND = "mf17506-zave-relay-exact-bound-query-receipt"
OUTPUT_WRITE_CONTRACT = "O_EXCL"
MANUAL_SCOPE = "IDENTITY_REBIND_ONLY_NOT_CONTACT_ON_AUTHORITY"
INTEGRITY_SCOPE = (
    "entire document excluding integrity; UTF-8 JSON with sorted keys, no "
    "whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_INPUT_BYTES = 1024 * 1024

ADAPTER_SOURCE = Path(__file__).with_name("relay_zave_ch340_2ch.py").resolve()
CONTRACT_SOURCE = Path(__file__).with_name("relay_contract.py").resolve()

_IDENTITY_KEYS = frozenset(
    {
        "model",
        "vid",
        "pid",
        "serial_number",
        "port",
        "pnp_instance_id",
        "usb_location",
    }
)
_MANUAL_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "declaration_id",
        "declared_at",
        "operator_id",
        "same_physical_relay_confirmed",
        "channel",
        "contact_path",
        "channel_1_com1_no1_wiring_confirmed",
        "previous_usb_location",
        "current_usb_location",
        "scope",
        "on_authorized",
    }
)
_QUERY_KEYS = frozenset(
    {
        "identity",
        "channel",
        "commanded_state",
        "electrical_state_proven",
        "contact_switch_performed",
    }
)
_RECORD_KEYS = frozenset({"path", "bytes", "sha256"})
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "rebind_id",
        "created_at",
        "binding",
        "evidence",
        "manual_declaration",
        "software_binding",
        "observed_state",
        "authority_boundaries",
        "output_write_contract",
        "integrity",
    }
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_COM_RE = re.compile(r"COM[1-9][0-9]*\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class RelayRebindError(ValueError):
    """Raised when rebind evidence is incomplete, stale, or unsafe."""


@dataclass(frozen=True)
class ValidatedRelayRebind:
    seal: dict[str, Any]
    expected_identity: RelayIdentity


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RelayRebindError(f"value is not canonical JSON data: {error}") from error


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RelayRebindError(f"JSON key is duplicated: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise RelayRebindError(f"non-finite JSON number is forbidden: {value}")


def _parse_json(payload: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except RelayRebindError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RelayRebindError(f"{label} is not valid UTF-8 JSON: {error}") from error


def _mapping(value: Any, *, label: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise RelayRebindError(f"{label} keys differ")
    return value


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise RelayRebindError(f"{label} must be a non-placeholder identifier")
    return value


def _timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RelayRebindError(f"{label} must be a timezone-aware timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise RelayRebindError(f"{label} is not an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RelayRebindError(f"{label} must include a UTC offset")
    return value


def _read_regular_file(path: Path, *, label: str) -> bytes:
    source = path.resolve()
    try:
        before = source.lstat()
    except OSError as error:
        raise RelayRebindError(f"cannot stat {label}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RelayRebindError(f"{label} must be a local regular non-symlink file")
    if before.st_size < 1 or before.st_size > MAX_INPUT_BYTES:
        raise RelayRebindError(f"{label} size is outside the accepted range")
    try:
        payload = source.read_bytes()
        after = source.stat()
    except OSError as error:
        raise RelayRebindError(f"cannot read {label}: {error}") from error
    if (
        len(payload) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise RelayRebindError(f"{label} changed while it was read")
    return payload


def _record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _identity(value: Any, *, label: str) -> RelayIdentity:
    root = _mapping(value, label=label, keys=_IDENTITY_KEYS)
    try:
        identity = RelayIdentity(**dict(root))
    except (RelayContractError, TypeError) as error:
        raise RelayRebindError(f"{label} is invalid: {error}") from error
    if (
        identity.model != MODEL
        or identity.vid != VID
        or identity.pid != PID
        or identity.serial_number != NO_USB_SERIAL
    ):
        raise RelayRebindError(f"{label} device family differs")
    if _COM_RE.fullmatch(identity.port) is None:
        raise RelayRebindError(f"{label} port is not a canonical Windows COM port")
    if identity.pnp_instance_id is None or identity.usb_location is None:
        raise RelayRebindError(f"{label} lacks the no-iSerial physical binding")
    return identity


def _manual_declaration(
    value: Any,
    *,
    previous: RelayIdentity,
    current: RelayIdentity,
) -> dict[str, Any]:
    root = _mapping(value, label="manual declaration", keys=_MANUAL_KEYS)
    declaration_id = _identifier(root["declaration_id"], label="declaration_id")
    operator_id = _identifier(root["operator_id"], label="operator_id")
    declared_at = _timestamp(root["declared_at"], label="declared_at")
    if root["schema_version"] != 1 or root["kind"] != MANUAL_DECLARATION_KIND:
        raise RelayRebindError("manual declaration identity differs")
    if root["same_physical_relay_confirmed"] is not True:
        raise RelayRebindError("same physical relay confirmation is required")
    if root["channel"] != 1 or root["contact_path"] != "COM1-NO1":
        raise RelayRebindError("manual declaration must bind channel 1 COM1-NO1")
    if root["channel_1_com1_no1_wiring_confirmed"] is not True:
        raise RelayRebindError("channel 1 COM1-NO1 wiring confirmation is required")
    if (
        root["previous_usb_location"] != previous.usb_location
        or root["current_usb_location"] != current.usb_location
    ):
        raise RelayRebindError("manual declaration USB locations differ")
    if root["scope"] != MANUAL_SCOPE or root["on_authorized"] is not False:
        raise RelayRebindError("manual declaration must not authorize contact ON")
    return {
        **dict(root),
        "declaration_id": declaration_id,
        "operator_id": operator_id,
        "declared_at": declared_at,
    }


def _identity_delta(
    previous: RelayIdentity, current: RelayIdentity
) -> tuple[list[str], list[str]]:
    old = previous.mapping()
    new = current.mapping()
    changed = sorted(key for key in _IDENTITY_KEYS if old[key] != new[key])
    if changed != ["usb_location"]:
        raise RelayRebindError(
            "narrow relay rebind requires usb_location to be the only changed field"
        )
    invariants = sorted(_IDENTITY_KEYS - {"usb_location"})
    return changed, invariants


def _load_inputs(
    *,
    previous_identity_file: Path,
    discover_evidence_file: Path,
    query_evidence_file: Path,
    manual_declaration_file: Path,
    adapter_source: Path,
    contract_source: Path,
) -> dict[str, Any]:
    paths = {
        "previous_identity": previous_identity_file,
        "discover": discover_evidence_file,
        "query": query_evidence_file,
        "manual_declaration": manual_declaration_file,
        "adapter": adapter_source,
        "contract": contract_source,
    }
    payloads = {
        role: _read_regular_file(path, label=f"{role} evidence")
        for role, path in paths.items()
    }
    previous = _identity(
        _parse_json(payloads["previous_identity"], label="previous identity evidence"),
        label="previous identity",
    )
    discovered_root = _parse_json(payloads["discover"], label="discover evidence")
    if not isinstance(discovered_root, list) or len(discovered_root) != 1:
        raise RelayRebindError("discover evidence must contain exactly one identity")
    current = _identity(discovered_root[0], label="discovered current identity")
    query = _mapping(
        _parse_json(payloads["query"], label="query evidence"),
        label="query evidence",
        keys=_QUERY_KEYS,
    )
    queried_identity = _identity(query["identity"], label="queried current identity")
    if queried_identity != current:
        raise RelayRebindError("discover and query current identities differ")
    if (
        query["channel"] != 1
        or query["commanded_state"] != RelayCommandedState.OFF.value
        or query["electrical_state_proven"] is not False
        or query["contact_switch_performed"] is not False
    ):
        raise RelayRebindError(
            "query evidence must be channel 1 commanded OFF without a contact command"
        )
    changed_fields, invariant_fields = _identity_delta(previous, current)
    manual = _manual_declaration(
        _parse_json(payloads["manual_declaration"], label="manual declaration"),
        previous=previous,
        current=current,
    )
    return {
        "paths": paths,
        "payloads": payloads,
        "previous": previous,
        "current": current,
        "query": dict(query),
        "manual": manual,
        "changed_fields": changed_fields,
        "invariant_fields": invariant_fields,
    }


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(unsigned),
        "integrity": {
            "algorithm": "sha256",
            "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
            "scope": INTEGRITY_SCOPE,
        },
    }


def _assemble(inputs: Mapping[str, Any], *, created_at: str) -> dict[str, Any]:
    created_at = _timestamp(created_at, label="created_at")
    paths = inputs["paths"]
    payloads = inputs["payloads"]
    previous: RelayIdentity = inputs["previous"]
    current: RelayIdentity = inputs["current"]
    evidence = {
        role: _record(paths[role], payloads[role])
        for role in ("previous_identity", "discover", "query", "manual_declaration")
    }
    software_binding = {
        role: _record(paths[role], payloads[role]) for role in ("adapter", "contract")
    }
    identity_material = {
        "created_at": created_at,
        "previous_identity": previous.mapping(),
        "current_identity": current.mapping(),
        "evidence": evidence,
        "software_binding": software_binding,
        "manual_declaration": inputs["manual"],
    }
    rebind_id = (
        f"mf17506-relay-rebind-{_sha256(canonical_json_bytes(identity_material))}"
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "rebind_id": rebind_id,
        "created_at": created_at,
        "binding": {
            "channel": 1,
            "previous_identity": previous.mapping(),
            "current_identity": current.mapping(),
            "changed_fields": inputs["changed_fields"],
            "invariant_fields": inputs["invariant_fields"],
            "historical_previous_binding_preserved": True,
        },
        "evidence": evidence,
        "manual_declaration": inputs["manual"],
        "software_binding": software_binding,
        "observed_state": {
            "channel": 1,
            "commanded_state": RelayCommandedState.OFF.value,
            "electrical_state_proven": False,
            "contact_switch_performed": False,
        },
        "authority_boundaries": {
            "identity_rebind_only": True,
            "operator_same_physical_relay_declaration_bound": True,
            "on_authorized": False,
            "hardware_execution_authorized": False,
            "visible_refresh_authorized": False,
            "builder_device_io_performed": False,
            "builder_relay_io_performed": False,
            "automatic_retry_allowed": False,
        },
        "output_write_contract": OUTPUT_WRITE_CONTRACT,
    }
    return _seal(unsigned)


def build_rebind(
    *,
    previous_identity_file: Path,
    discover_evidence_file: Path,
    query_evidence_file: Path,
    manual_declaration_file: Path,
    created_at: str,
    adapter_source: Path = ADAPTER_SOURCE,
    contract_source: Path = CONTRACT_SOURCE,
) -> dict[str, Any]:
    """Build one offline-only narrow rebind from byte-backed inputs."""

    inputs = _load_inputs(
        previous_identity_file=previous_identity_file,
        discover_evidence_file=discover_evidence_file,
        query_evidence_file=query_evidence_file,
        manual_declaration_file=manual_declaration_file,
        adapter_source=adapter_source,
        contract_source=contract_source,
    )
    return _assemble(inputs, created_at=created_at)


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> None:
    integrity = _mapping(
        root.get("integrity"),
        label=f"{label} integrity",
        keys=frozenset({"algorithm", "canonical_sha256", "scope"}),
    )
    if integrity["algorithm"] != "sha256" or integrity["scope"] != INTEGRITY_SCOPE:
        raise RelayRebindError(f"{label} integrity contract differs")
    digest = integrity["canonical_sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise RelayRebindError(f"{label} integrity digest is invalid")
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    if _sha256(canonical_json_bytes(unsigned)) != digest:
        raise RelayRebindError(f"{label} canonical integrity differs")


def _record_path(value: Any, *, label: str) -> Path:
    record = _mapping(value, label=label, keys=_RECORD_KEYS)
    path = record["path"]
    if not isinstance(path, str) or not path:
        raise RelayRebindError(f"{label} path is invalid")
    payload = _read_regular_file(Path(path), label=label)
    if record["bytes"] != len(payload) or record["sha256"] != _sha256(payload):
        raise RelayRebindError(f"{label} byte identity differs")
    return Path(path)


def validate_rebind(value: Any) -> ValidatedRelayRebind:
    """Deep-validate the seal and every byte-backed source, then return identity."""

    root = _mapping(value, label="relay rebind", keys=_ROOT_KEYS)
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != KIND
        or root["output_write_contract"] != OUTPUT_WRITE_CONTRACT
    ):
        raise RelayRebindError("relay rebind root contract differs")
    _verify_integrity(root, label="relay rebind")
    evidence = _mapping(
        root["evidence"],
        label="relay rebind evidence",
        keys=frozenset(
            {"previous_identity", "discover", "query", "manual_declaration"}
        ),
    )
    software = _mapping(
        root["software_binding"],
        label="software binding",
        keys=frozenset({"adapter", "contract"}),
    )
    paths = {
        role: _record_path(evidence[role], label=f"{role} evidence")
        for role in evidence
    }
    paths.update(
        {
            role: _record_path(software[role], label=f"{role} source")
            for role in software
        }
    )
    rebuilt = build_rebind(
        previous_identity_file=paths["previous_identity"],
        discover_evidence_file=paths["discover"],
        query_evidence_file=paths["query"],
        manual_declaration_file=paths["manual_declaration"],
        created_at=root["created_at"],
        adapter_source=paths["adapter"],
        contract_source=paths["contract"],
    )
    if dict(root) != rebuilt:
        raise RelayRebindError("relay rebind reconstruction differs")
    expected = _identity(
        root["binding"]["current_identity"], label="expected current identity"
    )
    return ValidatedRelayRebind(seal=rebuilt, expected_identity=expected)


def load_and_validate_rebind(path: Path) -> ValidatedRelayRebind:
    payload = _read_regular_file(path, label="relay rebind seal")
    return validate_rebind(_parse_json(payload, label="relay rebind seal"))


def _write_exclusive(path: Path, payload: bytes) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(destination, flags, 0o444)
    except FileExistsError as error:
        raise RelayRebindError(
            f"exclusive output already exists: {destination}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise


def _reserve_exclusive_pair(first: Path, second: Path) -> list[tuple[Path, int]]:
    destinations = [first.resolve(), second.resolve()]
    if destinations[0] == destinations[1]:
        raise RelayRebindError("capture outputs must be two distinct paths")
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    reserved: list[tuple[Path, int]] = []
    try:
        for destination in destinations:
            descriptor = os.open(destination, flags, 0o444)
            reserved.append((destination, descriptor))
    except FileExistsError as error:
        for destination, descriptor in reserved:
            os.close(descriptor)
            try:
                os.chmod(destination, 0o666)
            except OSError:
                pass
            destination.unlink(missing_ok=True)
        raise RelayRebindError(
            f"exclusive capture output already exists: {error.filename}"
        ) from error
    except OSError as error:
        for destination, descriptor in reserved:
            os.close(descriptor)
            try:
                os.chmod(destination, 0o666)
            except OSError:
                pass
            destination.unlink(missing_ok=True)
        raise RelayRebindError(f"cannot reserve capture outputs: {error}") from error
    return reserved


def _commit_reserved_pair(
    reserved: list[tuple[Path, int]], payloads: list[bytes]
) -> None:
    if len(reserved) != 2 or len(payloads) != 2:
        raise RelayRebindError("capture commit requires exactly two outputs")
    open_descriptors = {descriptor for _, descriptor in reserved}
    try:
        for (_, descriptor), payload in zip(reserved, payloads, strict=True):
            with os.fdopen(descriptor, "wb") as stream:
                open_descriptors.remove(descriptor)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        for destination, _ in reserved:
            try:
                os.chmod(destination, 0o444)
            except OSError:
                pass
    except Exception:
        for descriptor in open_descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        for destination, _ in reserved:
            try:
                os.chmod(destination, 0o666)
            except OSError:
                pass
            destination.unlink(missing_ok=True)
        raise


def _discard_reserved_pair(reserved: list[tuple[Path, int]]) -> None:
    for destination, descriptor in reserved:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.chmod(destination, 0o666)
        except OSError:
            pass
        destination.unlink(missing_ok=True)


def publish_rebind(path: Path, value: Mapping[str, Any]) -> None:
    validate_rebind(value)
    _write_exclusive(path, canonical_json_bytes(value) + b"\n")


def capture_current(
    *,
    discover_output_file: Path,
    query_output_file: Path,
    port: str | None = None,
    discovery: Callable[[], list[RelayIdentity]] = discover_present_bindings,
    adapter_factory: Callable[..., RelayAdapter] = ZaveCh340TwoChannelRelay,
) -> dict[str, Any]:
    """Capture one discovery and one channel-1 query into two reserved files.

    Both O_EXCL paths are reserved before registry/serial access.  There is one
    actual discovery call and no retry.  The adapter's equality check receives
    a frozen one-item discovery function, so ``connect`` still enforces the
    exact identity without performing a second live enumeration.
    """

    wanted_port = port.upper() if port is not None else None
    if wanted_port is not None and _COM_RE.fullmatch(wanted_port) is None:
        raise RelayRebindError("capture port is not a canonical Windows COM port")
    reserved = _reserve_exclusive_pair(discover_output_file, query_output_file)
    adapter: RelayAdapter | None = None
    try:
        candidates = discovery()
        if wanted_port is not None:
            candidates = [item for item in candidates if item.port == wanted_port]
        if len(candidates) != 1:
            raise RelayRebindError(
                "capture discovery requires exactly one present matching relay; "
                f"found {len(candidates)}"
            )
        identity = _identity(candidates[0].mapping(), label="captured current identity")
        adapter = adapter_factory(
            channel=1,
            port=identity.port,
            discovery=lambda: [identity],
        )
        adapter.connect(identity)
        state = adapter.read_commanded_state()
        discover_value = [identity.mapping()]
        query_value = {
            "identity": identity.mapping(),
            "channel": 1,
            "commanded_state": state.value,
            "electrical_state_proven": False,
            "contact_switch_performed": False,
        }
        payloads = [
            canonical_json_bytes(discover_value) + b"\n",
            canonical_json_bytes(query_value) + b"\n",
        ]
        adapter.close()
        adapter = None
        _commit_reserved_pair(reserved, payloads)
    except Exception:
        if adapter is not None:
            adapter.close()
        _discard_reserved_pair(reserved)
        raise
    return {
        "identity": identity.mapping(),
        "channel": 1,
        "commanded_state": state.value,
        "electrical_state_proven": False,
        "contact_switch_performed": False,
        "automatic_retry_performed": False,
        "discover_call_count": 1,
        "query_call_count": 1,
        "discover_output": str(discover_output_file.resolve()),
        "query_output": str(query_output_file.resolve()),
        "output_write_contract": OUTPUT_WRITE_CONTRACT,
    }


def _query_receipt(
    *,
    rebind_path: Path,
    rebind_payload: bytes,
    validated: ValidatedRelayRebind,
    queried_at: str,
    state: RelayCommandedState,
) -> dict[str, Any]:
    queried_at = _timestamp(queried_at, label="queried_at")
    expected = validated.expected_identity
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": QUERY_RECEIPT_KIND,
        "queried_at": queried_at,
        "rebind": {
            "path": str(rebind_path.resolve()),
            "bytes": len(rebind_payload),
            "sha256": _sha256(rebind_payload),
            "rebind_id": validated.seal["rebind_id"],
            "canonical_sha256": validated.seal["integrity"]["canonical_sha256"],
        },
        "expected_identity": expected.mapping(),
        "channel": 1,
        "commanded_state": state.value,
        "off_gate_passed": state is RelayCommandedState.OFF,
        "electrical_state_proven": False,
        "contact_switch_performed": False,
        "on_authorized": False,
        "automatic_retry_performed": False,
        "output_write_contract": OUTPUT_WRITE_CONTRACT,
    }
    return _seal(unsigned)


def exact_bound_query(
    *,
    rebind_file: Path,
    output_file: Path,
    queried_at: str,
    adapter_factory: Callable[..., RelayAdapter] = ZaveCh340TwoChannelRelay,
) -> dict[str, Any]:
    """Perform exactly one query against the identity frozen by a valid seal."""

    rebind_payload = _read_regular_file(rebind_file, label="relay rebind seal")
    validated = validate_rebind(_parse_json(rebind_payload, label="relay rebind seal"))
    expected = validated.expected_identity
    adapter = adapter_factory(channel=1, port=expected.port)
    try:
        adapter.connect(expected)
        state = adapter.read_commanded_state()
    finally:
        adapter.close()
    receipt = _query_receipt(
        rebind_path=rebind_file,
        rebind_payload=rebind_payload,
        validated=validated,
        queried_at=queried_at,
        state=state,
    )
    _write_exclusive(output_file, canonical_json_bytes(receipt) + b"\n")
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", allow_abbrev=False)
    build.add_argument("--previous-identity", type=Path, required=True)
    build.add_argument("--discover-evidence", type=Path, required=True)
    build.add_argument("--query-evidence", type=Path, required=True)
    build.add_argument("--manual-declaration", type=Path, required=True)
    build.add_argument("--created-at", required=True)
    build.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--rebind-seal", type=Path, required=True)

    capture = subparsers.add_parser("capture-current", allow_abbrev=False)
    capture.add_argument("--port")
    capture.add_argument("--discover-output", type=Path, required=True)
    capture.add_argument("--query-output", type=Path, required=True)

    query = subparsers.add_parser("query-bound", allow_abbrev=False)
    query.add_argument("--rebind-seal", type=Path, required=True)
    query.add_argument("--queried-at", required=True)
    query.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            value = build_rebind(
                previous_identity_file=args.previous_identity,
                discover_evidence_file=args.discover_evidence,
                query_evidence_file=args.query_evidence,
                manual_declaration_file=args.manual_declaration,
                created_at=args.created_at,
            )
            publish_rebind(args.output, value)
            result = {
                "valid": True,
                "rebind_id": value["rebind_id"],
                "canonical_sha256": value["integrity"]["canonical_sha256"],
                "expected_identity": value["binding"]["current_identity"],
                "on_authorized": False,
                "output": str(args.output.resolve()),
            }
            exit_code = 0
        elif args.command == "validate":
            validated = load_and_validate_rebind(args.rebind_seal)
            result = {
                "valid": True,
                "rebind_id": validated.seal["rebind_id"],
                "canonical_sha256": validated.seal["integrity"]["canonical_sha256"],
                "expected_identity": validated.expected_identity.mapping(),
                "on_authorized": False,
            }
            exit_code = 0
        elif args.command == "capture-current":
            result = capture_current(
                discover_output_file=args.discover_output,
                query_output_file=args.query_output,
                port=args.port,
            )
            exit_code = 0
        else:
            receipt = exact_bound_query(
                rebind_file=args.rebind_seal,
                output_file=args.output,
                queried_at=args.queried_at,
            )
            result = receipt
            exit_code = 0 if receipt["off_gate_passed"] else 3
    except (RelayRebindError, RelayContractError, OSError) as error:
        print(f"relay rebind error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
