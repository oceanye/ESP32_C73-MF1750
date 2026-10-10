#!/usr/bin/env python3
"""One-shot fail-closed host for fresh cross-palette HOLD white containment.

This runner exposes one fixed factory-OTP white action.  It does not flash,
reset, control power, skip an ordinal, retry, recover, or chain another action.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_pack as pack,
)


class ContainmentError(ValueError):
    """A pre-mutation contract mismatch; no visible action is accepted."""


class ContainmentConsumedError(ContainmentError):
    """The permanent claim exists or a post-claim result is uncertain."""


Requester = Callable[
    [str, str],
    tuple[int, Mapping[str, Any]],
]
NONCE = re.compile(r"^[0-9a-f]{16}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REPORT = pack.build_report(verify_artifacts=False)
ACTION = REPORT["action"]
ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
DEFAULT_CLAIMS = Path(
    ".test-output/hardware/.mf1750_cross_palette_partial_hold_"
    "white_containment_v1_claims"
)
DEFAULT_OUTPUT = Path(
    ".test-output/hardware/"
    "MF1750_CROSS_PALETTE_PARTIAL_HOLD_WHITE_CONTAINMENT_20260824_V1"
)
BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS = 65.0


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(value)
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }
    data = json.dumps(
        body, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def _create_claim(claims: Path) -> Path:
    claim = Path(claims) / f"{pack.ACTION_ID}.json"
    value = {
        "schema_version": 1,
        "kind": getattr(
            pack,
            "CLAIM_KIND",
            "mf1750-cross-palette-partial-hold-white-containment-claim",
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "action": ACTION,
        "state": "claimed_before_first_network_request",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    try:
        _write_new(claim, value)
    except FileExistsError as exc:
        raise ContainmentConsumedError(
            "containment action is permanently claimed; retry is forbidden"
        ) from exc
    return claim


def _default_requester(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    request = urllib_request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers=dict(headers or {}),
        data=None,
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status = response.status
            payload = response.read()
    except urllib_error.HTTPError as exc:
        status = exc.code
        payload = exc.read()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainmentConsumedError("device response is not UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ContainmentConsumedError("device response root is not an object")
    return status, value


def _get(
    requester: Any, base_url: str, name: str, timeout: float
) -> Mapping[str, Any]:
    status, value = requester(
        base_url,
        ENDPOINTS[name],
        method="GET",
        headers=None,
        timeout=timeout,
    )
    if status != 200:
        raise ContainmentConsumedError(f"GET {name} returned HTTP {status}")
    return value


def _identity(value: Mapping[str, Any], *, running_sha: str) -> None:
    exact = {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "profile_id": pack.PROFILE_ID,
        "environment": pack.ENVIRONMENT,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "contract_id": pack.CONTRACT_ID,
        "transaction_descriptor_sha256": pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": pack.DESCRIPTOR_MARKER,
        "running_app_elf_sha256": running_sha,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"device identity {key} differs")


def _validate_version(value: Mapping[str, Any]) -> str:
    running_sha = value.get("running_app_elf_sha256")
    if not isinstance(running_sha, str) or SHA256.fullmatch(running_sha) is None:
        raise ContainmentConsumedError("running app ELF identity is malformed")
    _identity(value, running_sha=running_sha)
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-version",
        "classification": pack.CLASSIFICATION,
        "action_count": 1,
        "startup_refresh": False,
        "raw_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "profile_switch": False,
        "runtime_payload_present": False,
        "live_authorized": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"version {key} differs")
    return running_sha


def _validate_manifest(value: Mapping[str, Any], running_sha: str) -> None:
    _identity(value, running_sha=running_sha)
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
        "classification": pack.CLASSIFICATION,
        "action_count": 1,
        "one_driver_call_per_action": True,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "raw_lut_ingress": False,
        "electrical_parameter_ingress": False,
        "timing_parameter_ingress": False,
        "runtime_payload_present": False,
        "generated_include": None,
        "runtime_psr_present": False,
        "hidden_lut_command_present": False,
        "r20_present": False,
        "r21_present": False,
        "vcom_write_or_sweep": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "requires_new_exact_authorization": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"manifest {key} differs")
    if value.get("actions") != [ACTION]:
        raise ContainmentConsumedError("manifest action differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != pack.NVS_NAMESPACE
        or nvs.get("key") != pack.NVS_KEY
        or nvs.get("initial_cursor") != 1
        or nvs.get("terminal_cursor") != 2
        or nvs.get("clear_route") is not False
        or nvs.get("persistent_across_reboot") is not True
    ):
        raise ContainmentConsumedError("manifest NVS contract differs")


def _validate_fresh_status(value: Mapping[str, Any], running_sha: str) -> str:
    _identity(value, running_sha=running_sha)
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or NONCE.fullmatch(nonce) is None:
        raise ContainmentConsumedError("fresh status boot nonce is malformed")
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 1,
        "next_ordinal": 1,
        "campaign_complete": False,
        "cursor_valid": True,
        "persistent_key_present": False,
        "fixture_self_check_passed": True,
        "execute_pending": False,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
        "gpio_initialized": True,
        "busy": 1,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"fresh status {key} differs")
    return nonce


def _validate_fresh_report(value: Mapping[str, Any], running_sha: str) -> None:
    _identity(value, running_sha=running_sha)
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        "valid": False,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"fresh report {key} differs")
    if "driver" in value or "action_id" in value:
        raise ContainmentConsumedError("fresh report contains terminal evidence")


def _headers(boot_nonce: str, intent: str, arm_nonce: str | None = None) -> dict[str, str]:
    value = {
        "X-EC5-Build-Tag": pack.BUILD_TAG,
        "X-EC5-Test-Id": pack.TEST_ID,
        "X-EC5-Campaign-Id": pack.CAMPAIGN_ID,
        "X-EC5-Action-Id": pack.ACTION_ID,
        "X-EC5-Ordinal": "1",
        "X-EC5-Descriptor-Id": pack.DESCRIPTOR_ID,
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        value["X-EC5-Arm-Nonce"] = arm_nonce
    return value


def _validate_terminal_driver(driver: Any) -> None:
    if not isinstance(driver, Mapping):
        raise ContainmentConsumedError("terminal driver evidence is absent")
    exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "pre_command_idle_failure": False,
        "input_fnv1a": pack.FRAME_FNV1A,
        "cs1_dtm_fnv1a": pack.DTM_FNV1A,
        "cs2_dtm_fnv1a": pack.DTM_FNV1A,
    }
    for key, wanted in exact.items():
        if driver.get(key) != wanted:
            raise ContainmentConsumedError(f"terminal driver {key} differs")
    busy_trace = driver.get("busy_trace", {})
    safe = busy_trace.get("safe_finish", {}) if isinstance(busy_trace, Mapping) else {}
    final = busy_trace.get("final_gpio", {}) if isinstance(busy_trace, Mapping) else {}
    if (
        busy_trace.get("idle_level") != 1
        or safe.get("busy_after_pins_low") != 1
        or safe.get("busy_after_5ms") != 1
        or final
        != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0, "sck": 0, "dc": 0, "mosi": 0}
    ):
        raise ContainmentConsumedError("terminal BUSY/safe GPIO evidence differs")


def _validate_complete(value: Mapping[str, Any], running_sha: str) -> None:
    _identity(value, running_sha=running_sha)
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        "valid": True,
        "profile_id": pack.PROFILE_ID,
        "ordinal": 1,
        "action_id": pack.ACTION_ID,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentConsumedError(f"terminal report {key} differs")
    _validate_terminal_driver(value.get("driver"))


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    requester: Any = _default_requester,
    timeout: float = 10.0,
    poll_seconds: float = BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    poll_count: int = 20,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Consume the one fresh containment action; any uncertainty forbids retry."""

    pack.build_report(verify_artifacts=True)
    if not isinstance(poll_count, int) or isinstance(poll_count, bool) or poll_count < 1:
        raise ContainmentError("poll_count must be a positive integer")
    if not isinstance(poll_seconds, (int, float)) or not (
        BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS <= poll_seconds <= 300
    ):
        raise ContainmentError("poll_seconds must be in 65..300")
    output = Path(output)
    if output.exists():
        raise ContainmentError(f"refusing to overwrite {output}")
    claim = _create_claim(Path(claims))
    transcript: list[dict[str, Any]] = []

    def get(name: str) -> Mapping[str, Any]:
        value = _get(requester, base_url, name, timeout)
        transcript.append({"method": "GET", "endpoint": name, "status": 200, "body": value})
        return value

    version = get("version")
    running_sha = _validate_version(version)
    _validate_manifest(get("manifest"), running_sha)
    boot_nonce = _validate_fresh_status(get("status"), running_sha)
    _validate_fresh_report(get("report"), running_sha)

    status, arm = requester(
        base_url,
        ENDPOINTS["arm"],
        method="POST",
        headers=_headers(boot_nonce, pack.ARM_INTENT),
        timeout=timeout,
    )
    transcript.append({"method": "POST", "endpoint": "arm", "status": status, "body": arm})
    arm_nonce = arm.get("arm_nonce")
    _identity(arm, running_sha=running_sha)
    if (
        status != 201
        or arm.get("accepted") is not True
        or arm.get("armed") is not True
        or arm.get("ordinal") != 1
        or arm.get("action_id") != pack.ACTION_ID
        or arm.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or NONCE.fullmatch(arm_nonce) is None
    ):
        raise ContainmentConsumedError("ARM response differs; retry is forbidden")

    status, execute = requester(
        base_url,
        ENDPOINTS["execute"],
        method="POST",
        headers=_headers(boot_nonce, pack.EXECUTE_INTENT, arm_nonce),
        timeout=timeout,
    )
    transcript.append({"method": "POST", "endpoint": "execute", "status": status, "body": execute})
    _identity(execute, running_sha=running_sha)
    if (
        status != 202
        or execute.get("accepted") is not True
        or execute.get("job_id") != 1
        or execute.get("action_id") != pack.ACTION_ID
        or execute.get("execute_consumed") is not True
        or execute.get("no_retry") is not True
    ):
        raise ContainmentConsumedError("EXECUTE response differs; retry is forbidden")

    terminal: Mapping[str, Any] | None = None
    for _ in range(poll_count):
        sleeper(float(poll_seconds))
        observed = get("report")
        state = observed.get("terminal_state")
        if state == "COMPLETE":
            _validate_complete(observed, running_sha)
            terminal = observed
            break
        if state == "FAULT":
            raise ContainmentConsumedError("device reported FAULT; retry is forbidden")
    if terminal is None:
        raise ContainmentConsumedError("terminal report was not observed; retry is forbidden")

    result = {
        "schema_version": 1,
        "kind": getattr(
            pack,
            "RESULT_KIND",
            "mf1750-cross-palette-partial-hold-white-containment-result",
        ),
        "outcome": "complete_pass",
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "claim_file": str(claim),
        "boot_nonce": boot_nonce,
        "action": ACTION,
        "visible_refreshes": 1,
        "network": {"get": sum(x["method"] == "GET" for x in transcript), "post": 2},
        "transcript": transcript,
        "terminal_report": terminal,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    _write_new(output, result)
    return result


def describe() -> dict[str, Any]:
    value = pack.build_report(verify_artifacts=False)
    return {
        **value,
        "purpose": "independent_fresh_factory_otp_white_fault_containment",
        "firmware_busy_gates": ["ARM", "EXECUTE", "DISPATCH"],
        "host_preflight_busy": "RAW_READY_BUSY_1_ONLY",
        "blocking_refresh_first_poll_floor_seconds": (
            BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS
        ),
        "network_requests": 0,
        "visible_refreshes": 0,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "ordinal_skip": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=10.0)
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    )
    run.add_argument("--poll-count", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        else:
            value = run_once(
                args.base_url,
                claims=args.claims,
                output=args.output,
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except ContainmentError as exc:
        print(f"white containment error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
