"""Exact-bound one-command relay switch with an immutable receipt.

This is the contact-command companion to :mod:`relay_rebind`.  It accepts only
the relay identity frozen by a deeply validated narrow-rebind seal, reserves
the receipt path with ``O_EXCL`` *before* device I/O, issues exactly one
feedback command, and then issues exactly one independent state query.

There is no retry, fallback, recovery, panel, ESP32, network, flash, reset, or
refresh operation here.  An ON command additionally requires an explicit
caller assertion that the current user authorized ON for the enclosing live
operation.  The assertion is recorded as an assertion; it is not represented
as cryptographic proof of the conversation that supplied the authority.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, BinaryIO

from .relay_contract import RelayAdapter, RelayCommandedState, RelayContractError
from .relay_rebind import (
    INTEGRITY_SCOPE,
    ValidatedRelayRebind,
    canonical_json_bytes,
    validate_rebind,
)
from .relay_zave_ch340_2ch import ZaveCh340TwoChannelRelay


SCHEMA_VERSION = 1
KIND = "mf17506-zave-relay-exact-bound-switch-receipt"
OUTPUT_WRITE_CONTRACT = "O_EXCL_PRE_RESERVED_BEFORE_DEVICE_IO"
CONTACT_PATH = "COM1-NO1"
MAX_INPUT_BYTES = 1024 * 1024
SWITCH_SOURCE = Path(__file__).resolve()

_AUTHORITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "switched_at",
        "rebind",
        "expected_identity",
        "channel",
        "contact_path",
        "target_state",
        "commanded_state",
        "target_gate_passed",
        "off_gate_passed",
        "electrical_state_proven",
        "contact_switch_performed",
        "feedback_command_count",
        "independent_query_count",
        "automatic_retry_performed",
        "automatic_recovery_performed",
        "authority",
        "software_binding",
        "output_write_contract",
        "integrity",
    }
)


class RelayExactBoundSwitchError(ValueError):
    """Raised before, during, or after an unsafe exact-bound switch attempt."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RelayExactBoundSwitchError(f"{label} must be a timezone-aware timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise RelayExactBoundSwitchError(
            f"{label} is not an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RelayExactBoundSwitchError(f"{label} must include a UTC offset")
    return value


def _authority_id(value: Any) -> str:
    if not isinstance(value, str) or _AUTHORITY_RE.fullmatch(value) is None:
        raise RelayExactBoundSwitchError(
            "authorization_id must be a non-placeholder identifier"
        )
    return value


def _read_regular_file(path: Path, *, label: str) -> bytes:
    source = path.resolve()
    try:
        before = source.lstat()
    except OSError as error:
        raise RelayExactBoundSwitchError(f"cannot stat {label}: {error}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RelayExactBoundSwitchError(
            f"{label} must be a local regular non-symlink file"
        )
    if before.st_size < 1 or before.st_size > MAX_INPUT_BYTES:
        raise RelayExactBoundSwitchError(f"{label} size is outside the accepted range")
    try:
        payload = source.read_bytes()
        after = source.stat()
    except OSError as error:
        raise RelayExactBoundSwitchError(f"cannot read {label}: {error}") from error
    if (
        len(payload) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise RelayExactBoundSwitchError(f"{label} changed while it was read")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RelayExactBoundSwitchError(f"JSON key is duplicated: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RelayExactBoundSwitchError(f"non-finite JSON number is forbidden: {value}")


def _parse_json(payload: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except RelayExactBoundSwitchError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RelayExactBoundSwitchError(
            f"{label} is not valid UTF-8 JSON: {error}"
        ) from error


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(unsigned),
        "integrity": {
            "algorithm": "sha256",
            "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
            "scope": INTEGRITY_SCOPE,
        },
    }


def _reserve_exclusive(path: Path) -> tuple[Path, BinaryIO]:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(destination, flags, 0o444)
    except FileExistsError as error:
        raise RelayExactBoundSwitchError(
            f"exclusive output already exists: {destination}"
        ) from error
    return destination, os.fdopen(descriptor, "wb")


def _discard_reservation(destination: Path, stream: BinaryIO) -> None:
    try:
        stream.close()
    finally:
        try:
            os.chmod(destination, stat.S_IWRITE)
            destination.unlink()
        except OSError:
            pass


def _commit_reservation(stream: BinaryIO, payload: bytes) -> None:
    stream.write(payload)
    stream.flush()
    os.fsync(stream.fileno())
    stream.close()


def _load_rebind(path: Path) -> tuple[bytes, ValidatedRelayRebind]:
    payload = _read_regular_file(path, label="relay rebind seal")
    parsed = _parse_json(payload, label="relay rebind seal")
    return payload, validate_rebind(parsed)


def _authority(
    *,
    target: RelayCommandedState,
    authorization_id: str | None,
    current_user_authorized_on: bool,
) -> dict[str, Any]:
    if target is RelayCommandedState.ON:
        if not current_user_authorized_on:
            raise RelayExactBoundSwitchError(
                "ON requires --confirm-current-user-authorized-on"
            )
        return {
            "basis": "CURRENT_USER_EXPLICIT_ON_AUTHORITY_ASSERTED_BY_CALLER",
            "authorization_id": _authority_id(authorization_id),
            "on_authorized": True,
            "caller_assertion_only_not_conversation_cryptographic_proof": True,
        }
    if current_user_authorized_on or authorization_id is not None:
        raise RelayExactBoundSwitchError(
            "OFF forbids ON authorization arguments; use protective OFF authority"
        )
    return {
        "basis": "PROTECTIVE_OFF",
        "authorization_id": None,
        "on_authorized": False,
        "caller_assertion_only_not_conversation_cryptographic_proof": False,
    }


def _receipt(
    *,
    rebind_path: Path,
    rebind_payload: bytes,
    validated: ValidatedRelayRebind,
    switch_source_payload: bytes,
    switched_at: str,
    target: RelayCommandedState,
    observed: RelayCommandedState,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "switched_at": _timestamp(switched_at, label="switched_at"),
            "rebind": {
                "path": str(rebind_path.resolve()),
                "bytes": len(rebind_payload),
                "sha256": _sha256(rebind_payload),
                "rebind_id": validated.seal["rebind_id"],
                "canonical_sha256": validated.seal["integrity"]["canonical_sha256"],
            },
            "expected_identity": validated.expected_identity.mapping(),
            "channel": 1,
            "contact_path": CONTACT_PATH,
            "target_state": target.value,
            "commanded_state": observed.value,
            "target_gate_passed": observed is target,
            "off_gate_passed": observed is RelayCommandedState.OFF,
            "electrical_state_proven": False,
            "contact_switch_performed": True,
            "feedback_command_count": 1,
            "independent_query_count": 1,
            "automatic_retry_performed": False,
            "automatic_recovery_performed": False,
            "authority": dict(authority),
            "software_binding": {
                "switch_source": {
                    "path": str(SWITCH_SOURCE),
                    "bytes": len(switch_source_payload),
                    "sha256": _sha256(switch_source_payload),
                }
            },
            "output_write_contract": OUTPUT_WRITE_CONTRACT,
        }
    )


def exact_bound_switch(
    *,
    rebind_file: Path,
    output_file: Path,
    switched_at: str,
    target: RelayCommandedState,
    authorization_id: str | None = None,
    current_user_authorized_on: bool = False,
    adapter_factory: Callable[..., RelayAdapter] = ZaveCh340TwoChannelRelay,
) -> dict[str, Any]:
    """Issue one exact-bound command and one query, then commit one receipt."""

    if target not in (RelayCommandedState.OFF, RelayCommandedState.ON):
        raise RelayExactBoundSwitchError("target must be ON or OFF")
    switched_at = _timestamp(switched_at, label="switched_at")
    operation_authority = _authority(
        target=target,
        authorization_id=authorization_id,
        current_user_authorized_on=current_user_authorized_on,
    )
    rebind_payload, validated = _load_rebind(rebind_file)
    switch_source_payload = _read_regular_file(
        SWITCH_SOURCE, label="exact-bound switch source"
    )
    destination, stream = _reserve_exclusive(output_file)
    adapter = adapter_factory(channel=1, port=validated.expected_identity.port)
    committed = False
    try:
        adapter.connect(validated.expected_identity)
        if target is RelayCommandedState.ON:
            adapter.command_on()
        else:
            adapter.command_off()
        observed = adapter.read_commanded_state()
        receipt = _receipt(
            rebind_path=rebind_file,
            rebind_payload=rebind_payload,
            validated=validated,
            switch_source_payload=switch_source_payload,
            switched_at=switched_at,
            target=target,
            observed=observed,
            authority=operation_authority,
        )
        _commit_reservation(stream, canonical_json_bytes(receipt) + b"\n")
        committed = True
        return receipt
    finally:
        adapter.close()
        if not committed:
            _discard_reservation(destination, stream)


def validate_receipt(value: Any) -> dict[str, Any]:
    """Validate the canonical integrity and invariant safety fields of a receipt."""

    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise RelayExactBoundSwitchError("switch receipt keys differ")
    root = dict(value)
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != KIND
        or root["output_write_contract"] != OUTPUT_WRITE_CONTRACT
    ):
        raise RelayExactBoundSwitchError("switch receipt root contract differs")
    integrity = root["integrity"]
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "algorithm",
        "canonical_sha256",
        "scope",
    }:
        raise RelayExactBoundSwitchError("switch receipt integrity keys differ")
    digest = integrity["canonical_sha256"]
    if (
        integrity["algorithm"] != "sha256"
        or integrity["scope"] != INTEGRITY_SCOPE
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
    ):
        raise RelayExactBoundSwitchError("switch receipt integrity differs")
    unsigned = {key: item for key, item in root.items() if key != "integrity"}
    if _sha256(canonical_json_bytes(unsigned)) != digest:
        raise RelayExactBoundSwitchError("switch receipt canonical integrity differs")
    if (
        root["channel"] != 1
        or root["contact_path"] != CONTACT_PATH
        or root["electrical_state_proven"] is not False
        or root["contact_switch_performed"] is not True
        or root["feedback_command_count"] != 1
        or root["independent_query_count"] != 1
        or root["automatic_retry_performed"] is not False
        or root["automatic_recovery_performed"] is not False
    ):
        raise RelayExactBoundSwitchError("switch receipt command contract differs")
    target = RelayCommandedState(root["target_state"])
    observed = RelayCommandedState(root["commanded_state"])
    if root["target_gate_passed"] is not (target is observed):
        raise RelayExactBoundSwitchError("switch receipt target gate differs")
    if root["off_gate_passed"] is not (observed is RelayCommandedState.OFF):
        raise RelayExactBoundSwitchError("switch receipt OFF gate differs")
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("off-bound", "on-bound"):
        command = subparsers.add_parser(name, allow_abbrev=False)
        command.add_argument("--rebind-seal", type=Path, required=True)
        command.add_argument("--switched-at", required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "on-bound":
            command.add_argument("--authorization-id", required=True)
            command.add_argument(
                "--confirm-current-user-authorized-on", action="store_true"
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target = (
        RelayCommandedState.ON
        if args.command == "on-bound"
        else RelayCommandedState.OFF
    )
    try:
        receipt = exact_bound_switch(
            rebind_file=args.rebind_seal,
            output_file=args.output,
            switched_at=args.switched_at,
            target=target,
            authorization_id=getattr(args, "authorization_id", None),
            current_user_authorized_on=getattr(
                args, "confirm_current_user_authorized_on", False
            ),
        )
    except (RelayExactBoundSwitchError, RelayContractError, OSError) as error:
        print(f"relay exact-bound switch error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["target_gate_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
