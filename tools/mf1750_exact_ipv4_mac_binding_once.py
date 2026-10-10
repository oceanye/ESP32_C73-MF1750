#!/usr/bin/env python3
"""Bind one literal IPv4 candidate to one expected MAC without device API I/O.

The helper is deliberately narrower than a reachability scanner.  It accepts a
single literal IPv4 address, rejects any address owned by the host, optionally
emits exactly one ICMP echo to refresh the Windows neighbour entry, and then
requires the resulting neighbour entry to match the expected MAC.  It never
uses DNS, enumerates candidate hosts, opens HTTP, or calls a device mutation
route.

The result is terminal and written with O_EXCL.  A failed result must not be
deleted and rerun; a later attempt needs a new output path and explicit
authority.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


MAC_RE = re.compile(r"^(?:[0-9A-F]{2}-){5}[0-9A-F]{2}$")
FRESH_NEIGHBOUR_STATES = frozenset({"REACHABLE", "DELAY", "PROBE", "PERMANENT"})
NUMERIC_NEIGHBOUR_STATES = {
    0: "UNREACHABLE",
    1: "INCOMPLETE",
    2: "PROBE",
    3: "DELAY",
    4: "STALE",
    5: "REACHABLE",
    6: "PERMANENT",
}


class BindingError(RuntimeError):
    """Raised when the one-candidate binding contract is violated."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], float], CommandResult]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _canonical_sha256(result),
    }
    return result


def _run(command: Sequence[str], timeout: float) -> CommandResult:
    completed = subprocess.run(  # noqa: S603
        list(command), capture_output=True, check=False, timeout=timeout
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _summary(result: CommandResult) -> dict[str, Any]:
    return {
        "returncode": result.returncode,
        "stdout_bytes": len(result.stdout),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stdout_utf8": result.stdout.decode("utf-8", errors="replace"),
        "stderr_bytes": len(result.stderr),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "stderr_utf8": result.stderr.decode("utf-8", errors="replace"),
    }


def _normalise_mac(value: str) -> str:
    normalised = value.strip().upper().replace(":", "-")
    if MAC_RE.fullmatch(normalised) is None:
        raise BindingError("expected MAC must contain six hexadecimal octets")
    return normalised


def _literal_ipv4(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError as error:
        raise BindingError("candidate must be one literal IPv4 address") from error
    if not isinstance(parsed, ipaddress.IPv4Address):
        raise BindingError("candidate must be IPv4")
    if parsed.is_unspecified or parsed.is_multicast or parsed.is_loopback:
        raise BindingError("candidate IPv4 class is not eligible")
    return str(parsed)


def _neighbour_state(value: Any) -> str:
    if isinstance(value, int):
        return NUMERIC_NEIGHBOUR_STATES.get(value, f"UNKNOWN_NUMERIC_{value}")
    text = str(value).strip().upper()
    if text.isdigit():
        return NUMERIC_NEIGHBOUR_STATES.get(int(text), f"UNKNOWN_NUMERIC_{text}")
    return text


def _powershell_json(script: str, *, runner: Runner, timeout: float) -> Any:
    utf8_script = (
        "$OutputEncoding=[Console]::OutputEncoding="
        "[System.Text.UTF8Encoding]::new($false);" + script
    )
    result = runner(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            utf8_script,
        ],
        timeout,
    )
    if result.returncode != 0:
        raise BindingError(
            "PowerShell evidence query failed: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    text = result.stdout.decode("utf-8-sig", errors="strict").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise BindingError("PowerShell evidence query returned invalid JSON") from error


def _as_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    if not all(isinstance(item, dict) for item in items):
        raise BindingError("PowerShell evidence JSON has an unexpected shape")
    return items


def bind_once(
    *,
    candidate_ip: str,
    expected_mac: str,
    output: Path,
    active_probe: bool,
    confirm_single_candidate: bool,
    runner: Runner = _run,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Run one fail-closed literal IPv4-to-MAC binding attempt."""

    if not confirm_single_candidate:
        raise BindingError("--confirm-single-candidate is required")
    if timeout <= 0:
        raise BindingError("timeout must be positive")
    ip = _literal_ipv4(candidate_ip)
    mac = _normalise_mac(expected_mac)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise BindingError(f"refusing to overwrite terminal output: {output}") from error

    started_at = _now()
    record: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-exact-ipv4-mac-binding-attempt-v1",
        "started_at": started_at,
        "finished_at": None,
        "candidate_ipv4": ip,
        "expected_mac": mac,
        "active_probe_authorized": active_probe,
        "single_candidate_confirmed": True,
        "outcome": "running",
        "binding_passed": False,
        "fresh_binding_passed": False,
        "device_application_identity_proven": False,
        "http_requests": 0,
        "device_api_requests": 0,
        "mutation_requests": 0,
        "visible_refresh_requests": 0,
        "candidate_count": 1,
        "retry": False,
        "fallback": False,
        "scan": False,
        "output_file": str(output),
        "output_contract": "O_EXCL_TERMINAL",
    }
    try:
        try:
            local_script = (
                "@(Get-NetIPAddress -AddressFamily IPv4 | "
                "Select-Object InterfaceAlias,InterfaceIndex,IPAddress,PrefixLength) "
                "| ConvertTo-Json -Compress"
            )
            local_items = _as_items(
                _powershell_json(local_script, runner=runner, timeout=timeout)
            )
            record["local_ipv4"] = local_items
            if any(str(item.get("IPAddress", "")) == ip for item in local_items):
                raise BindingError("candidate IPv4 belongs to this host")

            if active_probe:
                probe = runner(["ping.exe", "-n", "1", "-w", "1000", ip], timeout)
                record["active_probe"] = {
                    "kind": "one_icmp_echo_to_exact_literal_ipv4",
                    "attempts": 1,
                    **_summary(probe),
                }
                if probe.returncode != 0:
                    raise BindingError("the single exact-candidate ICMP probe failed")
            else:
                record["active_probe"] = {
                    "kind": "none_passive_neighbour_snapshot_only",
                    "attempts": 0,
                }

            neighbour_script = (
                f"@(Get-NetNeighbor -AddressFamily IPv4 -IPAddress '{ip}' "
                "-ErrorAction SilentlyContinue | "
                "Select-Object ifIndex,IPAddress,LinkLayerAddress,State) "
                "| ConvertTo-Json -Compress"
            )
            neighbours = _as_items(
                _powershell_json(neighbour_script, runner=runner, timeout=timeout)
            )
            record["neighbour_entries"] = neighbours
            exact = [
                item
                for item in neighbours
                if str(item.get("IPAddress", "")) == ip
                and _normalise_mac(str(item.get("LinkLayerAddress", ""))) == mac
            ]
            if len(exact) != 1:
                raise BindingError("candidate does not have one exact expected-MAC entry")
            state = _neighbour_state(exact[0].get("State", ""))
            record["observed_state"] = state
            record["network_layer_mac_binding_observed"] = True
            if active_probe and state not in FRESH_NEIGHBOUR_STATES:
                raise BindingError("post-probe neighbour state is not fresh enough")
            record["binding_passed"] = True
            record["fresh_binding_passed"] = active_probe
            record["outcome"] = (
                "active_exact_mac_binding_pass"
                if active_probe
                else "passive_exact_mac_binding_observed_not_freshness_proof"
            )
        except Exception as error:
            record["outcome"] = "terminal_binding_failure_no_retry"
            record["error"] = {"type": type(error).__name__, "message": str(error)}
        record["finished_at"] = _now()
        sealed = _seal(record)
        payload = (
            json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
        return sealed
    finally:
        os.close(fd)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate-ip", required=True)
    parser.add_argument("--expected-mac", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--active-probe", action="store_true")
    parser.add_argument("--confirm-single-candidate", action="store_true", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = bind_once(
            candidate_ip=args.candidate_ip,
            expected_mac=args.expected_mac,
            output=args.output,
            active_probe=args.active_probe,
            confirm_single_candidate=args.confirm_single_candidate,
            timeout=args.timeout,
        )
    except BindingError as error:
        print(f"exact IPv4/MAC binding error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["binding_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
