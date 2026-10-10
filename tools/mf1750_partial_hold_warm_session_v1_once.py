#!/usr/bin/env python3
"""Fail-closed one-action runner for the same-boot warm PTLW experiment.

The runner never flashes, resets, or controls relay power.  A campaign starts
with J2 OFF diagnosis, then requires one externally supervised J2-ON session.
Each invocation can consume exactly one immutable ARM/EXECUTE action.  It has
no mutation retry, fallback, recovery, or automatic action chaining.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_partial_hold_warm_session_v1_pack as pack  # noqa: E402


_WIRE_PATH = Path(__file__).with_name(
    "mf1750_ec5_otp_transition_matrix_recheck_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_partial_hold_warm_session_v1_wire", _WIRE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load fixed-action wire helper: {_WIRE_PATH}")
wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wire)


REPORT = pack.build_report()
BUILD_TAG = pack.BUILD_TAG
TEST_ID = pack.TEST_ID
CAMPAIGN_ID = pack.CAMPAIGN_ID
CONTRACT_ID = REPORT["contract_id"]
CLASSIFICATION = "EXPERIMENTAL_SPD1657_L535_STRICT_PTLW_WARM_SESSION"
DEVICE_API_VERSION = "MF1750_EC5_PARTIAL_HOLD_WARM_SESSION_DEVICE_V1"
IDENTITY_REVISION = "partial-hold-warm-session-v1"
NVS_NAMESPACE = pack.NVS_NAMESPACE
NVS_KEY = "cursor_v1"
FIRMWARE_BIN = (
    REPO_ROOT
    / ".pio"
    / "build-partial-hold-warm-session-v1"
    / "ec5_partial_hold_warm_session_v1"
    / "firmware.bin"
)
FIRMWARE_ELF = FIRMWARE_BIN.with_name("firmware.elf")
FIRMWARE_BIN_BYTES = 785136
FIRMWARE_ELF_BYTES = 13256644
FIRMWARE_BIN_SHA256 = (
    "1fedf38a1a79f1099bbc04d359de9ea1433131e82fabc80a1b161252538602d5"
)
FIRMWARE_ELF_SHA256 = (
    "0049b0bfe140fcc1e49cb8f3fc2d5cafd0f81aecbca8047dc1401666d778c227"
)
ENDPOINTS = {
    name: f"/api/ec5/partial-hold-warm-session-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
ARM_INTENT = "ARM_ONE_FIXED_WARM_SESSION_PTLW_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_WARM_SESSION_PTLW_ACTION_ONCE"
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_partial_hold_warm_session_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_PARTIAL_HOLD_WARM_SESSION_V1_20260823"
)


def _actions() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "ordinal": item["ordinal"],
            "role": item["role"],
            "branch": item["branch"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "prior_action_id": (
                None if item["ordinal"] == 1 else REPORT["actions"][item["ordinal"] - 2]["action_id"]
            ),
            "frame_sha256": item["frame"]["sha256"],
            "cs1_dtm_sha256": item["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": item["cs2_dtm"]["sha256"],
        }
        for item in REPORT["actions"]
    )


ACTIONS = _actions()
ACTION_IDS = tuple(item["action_id"] for item in ACTIONS)
WARM_STATE_BEFORE = (
    "cold",
    "warm_expect_red",
    "warm_expect_blue",
    "warm_expect_green",
    "warm_expect_white_recovery",
    "closed_safe_pof",
)
WARM_STATE_AFTER = WARM_STATE_BEFORE[1:]


class WarmSessionError(ValueError):
    """The device, artifact, sequence, or response differs."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_artifacts() -> None:
    exact = (
        (FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256, "BIN"),
        (FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256, "ELF"),
    )
    for path, wanted_bytes, wanted_sha, label in exact:
        if not path.is_file() or path.is_symlink():
            raise WarmSessionError(f"warm-session {label} is absent or unsafe")
        if path.stat().st_size != wanted_bytes or _sha256(path) != wanted_sha:
            raise WarmSessionError(f"warm-session {label} identity differs")


def _common_identity(value: Mapping[str, Any], *, kind: str) -> None:
    exact = {
        "kind": kind,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "contract_id": CONTRACT_ID,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise WarmSessionError(f"device {kind} {key} differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _common_identity(value, kind="mf1750-partial-hold-warm-session-version")
    exact = {
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "spi_hz": 1_000_000,
        "startup_refresh": False,
        "boot_resume": False,
        "retry": False,
        "autochain": False,
        "physical_power_control": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise WarmSessionError(f"device version {key} differs")


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _common_identity(value, kind="mf1750-partial-hold-warm-session-manifest")
    exact = {
        "classification": CLASSIFICATION,
        "action_count": 5,
        "actions": list(ACTIONS),
        "one_driver_call_per_action": True,
        "same_boot_required": True,
        "boot_resume": False,
        "unexpected_reboot_requires_physical_cut_before_recovery": True,
        "prepare_count": 1,
        "hard_reset_count": 1,
        "runtime_lut_upload_count": 1,
        "pon_count": 1,
        "patch_drf_without_pon_count": 3,
        "success_pof_count": 1,
        "max_warm_gap_ms": 120000,
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "cropped_dtm": True,
        "cdi": 0xFF,
        "partial_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "retry": False,
        "autochain": False,
        "physical_power_control": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise WarmSessionError(f"device manifest {key} differs")


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_boot: str | None = None
) -> str:
    _common_identity(value, kind="mf1750-partial-hold-warm-session-status")
    terminal = len(ACTIONS) + 1
    expected = {
        "state": "complete" if ordinal == terminal else "ready",
        "warm_state": WARM_STATE_BEFORE[ordinal - 1],
        "phase": 0,
        "next_ordinal": ordinal,
        "next_action_id": None if ordinal == terminal else ACTION_IDS[ordinal - 1],
        "arm_nonce": None,
        "fixture_self_check_passed": True,
        "no_retry": True,
        "no_autochain": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise WarmSessionError(f"device ready status {key} differs")
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or wire._NONCE.fullmatch(nonce) is None:  # noqa: SLF001
        raise WarmSessionError("device boot nonce is malformed")
    if expected_boot is not None and nonce != expected_boot:
        raise WarmSessionError("same-boot warm-session evidence differs")
    remaining = value.get("warm_remaining_ms")
    if ordinal in (2, 3, 4, 5):
        if not isinstance(remaining, int) or not 0 < remaining <= 120000:
            raise WarmSessionError("warm-session lease is not active")
    elif remaining != 0:
        raise WarmSessionError("cold/closed state reports a warm lease")
    return nonce


def _request(
    requester: Any,
    transcript: list[dict[str, Any]],
    origin: str,
    endpoint: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    path = ENDPOINTS[endpoint]
    url = origin + path
    status, value = requester(method, url, dict(headers or {}), None)
    transcript.append(
        {
            "method": method,
            "path": path,
            "status": status,
            "response": dict(value),
        }
    )
    if not 200 <= status < 300:
        raise WarmSessionError(f"{method} {endpoint} returned HTTP {status}")
    return value


def _validate_prior_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    _common_identity(value, kind="mf1750-partial-hold-warm-session-report")
    if value.get("boot_nonce") != boot_nonce:
        raise WarmSessionError("device report boot nonce differs")
    if ordinal == 1:
        expected = {
            "valid": False,
            "terminal_state": "NOT_EXECUTED",
            "result": False,
            "driver_called": False,
            "error": "not_executed",
            "next_ordinal": 1,
        }
    else:
        prior = ACTIONS[ordinal - 2]
        expected = {
            "valid": True,
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "ordinal": ordinal - 1,
            "action_id": prior["action_id"],
            "next_ordinal": ordinal,
            "campaign_complete": False,
            "warm_state": WARM_STATE_BEFORE[ordinal - 1],
            "no_retry": True,
            "no_autochain": True,
        }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise WarmSessionError(f"device prior report {key} differs")


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    requester: Any,
    expected_boot: str | None = None,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    origin = wire._origin(base_url)  # noqa: SLF001
    transcript: list[dict[str, Any]] = []
    version = _request(requester, transcript, origin, "version")
    manifest = _request(requester, transcript, origin, "manifest")
    status = _request(requester, transcript, origin, "status")
    report = _request(requester, transcript, origin, "report")
    _validate_version(version)
    _validate_manifest(manifest)
    boot_nonce = _validate_ready_status(status, ordinal, expected_boot=expected_boot)
    _validate_prior_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


def _headers(action: Mapping[str, Any], boot_nonce: str, intent: str) -> dict[str, str]:
    return {
        "X-EC5-Build-Tag": BUILD_TAG,
        "X-EC5-Test-Id": TEST_ID,
        "X-EC5-Campaign-Id": CAMPAIGN_ID,
        "X-EC5-Action-Id": str(action["action_id"]),
        "X-EC5-Ordinal": str(action["ordinal"]),
        "X-EC5-Descriptor-Id": str(action["descriptor_id"]),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }


def describe() -> dict[str, Any]:
    _require_artifacts()
    return {
        "schema_version": 1,
        "kind": "mf1750-partial-hold-warm-session-v1-description",
        "build_tag": BUILD_TAG,
        "campaign_id": CAMPAIGN_ID,
        "contract_id": CONTRACT_ID,
        "firmware": {
            "bin": {
                "path": str(FIRMWARE_BIN.relative_to(REPO_ROOT)),
                "bytes": FIRMWARE_BIN_BYTES,
                "sha256": FIRMWARE_BIN_SHA256,
            },
            "elf": {
                "path": str(FIRMWARE_ELF.relative_to(REPO_ROOT)),
                "bytes": FIRMWARE_ELF_BYTES,
                "sha256": FIRMWARE_ELF_SHA256,
            },
        },
        "nvs": {"namespace": NVS_NAMESPACE, "key": NVS_KEY},
        "actions": list(ACTIONS),
        "visible_actions": 5,
        "same_boot_required": True,
        "max_warm_gap_ms": 120000,
        "startup_refresh": False,
        "firmware_flash_performed_by_runner": False,
        "relay_control_performed_by_runner": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "live_authorized": False,
    }


def diagnose_j2_off(
    base_url: str, *, output: Path, requester: Any = wire._http_request  # noqa: SLF001
) -> dict[str, Any]:
    _require_artifacts()
    boot_nonce, transcript, report = _preflight(
        base_url, 1, requester=requester
    )
    evidence = wire._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-partial-hold-warm-session-v1-j2-off-diagnostic",
            "created_at": wire._now(),  # noqa: SLF001
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "next_ordinal": 1,
            "report": dict(report),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "visible_refreshes": 0,
        }
    )
    wire._write_new(output, evidence)  # noqa: SLF001
    return evidence


def _validate_terminal_report(
    report: Mapping[str, Any], action: Mapping[str, Any], boot_nonce: str
) -> None:
    ordinal = int(action["ordinal"])
    _common_identity(report, kind="mf1750-partial-hold-warm-session-report")
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "ordinal": ordinal,
        "action_id": action["action_id"],
        "role": action["role"],
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == len(ACTIONS),
        "warm_state": WARM_STATE_AFTER[ordinal - 1],
        "no_retry": True,
        "no_autochain": True,
    }
    for key, wanted in exact.items():
        if report.get(key) != wanted:
            raise WarmSessionError(f"terminal report {key} differs")
    driver = report.get("driver", {})
    driver_exact = {
        "valid": True,
        "sequence_ok": True,
        "spi_hz": 1_000_000,
        "drf_busy_seen": True,
        "pon_busy_seen": ordinal == 1,
        "pof_busy_seen": ordinal == len(ACTIONS),
        "failure_stage": "none",
    }
    for key, wanted in driver_exact.items():
        if driver.get(key) != wanted:
            raise WarmSessionError(f"terminal driver {key} differs")


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = wire._http_request,  # noqa: SLF001
    first_poll_seconds: float | None = None,
    poll_count: int = 3,
    following_poll_seconds: float = 3.0,
) -> dict[str, Any]:
    _require_artifacts()
    if ordinal < 1 or ordinal > len(ACTIONS):
        raise WarmSessionError("ordinal must be between 1 and 5")
    action = ACTIONS[ordinal - 1]
    claims = Path(claims)
    claim_file = claims / f"{action['action_id']}.json"
    if claim_file.exists():
        raise WarmSessionError(f"action {ordinal} was already permanently claimed")
    if ordinal > 1 and not (claims / f"{ACTION_IDS[ordinal - 2]}.json").is_file():
        raise WarmSessionError(f"action {ordinal} requires the local prior claim")

    origin = wire._origin(base_url)  # noqa: SLF001
    boot_nonce, transcript, _ = _preflight(
        origin, ordinal, requester=requester
    )
    claim = wire._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-partial-hold-warm-session-v1-permanent-claim",
            "created_at": wire._now(),  # noqa: SLF001
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "action": dict(action),
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    wire._write_new(claim_file, claim)  # noqa: SLF001

    arm = _request(
        requester,
        transcript,
        origin,
        "arm",
        method="POST",
        headers=_headers(action, boot_nonce, ARM_INTENT),
    )
    arm_nonce = arm.get("arm_nonce")
    if (
        arm.get("accepted") is not True
        or arm.get("armed") is not True
        or arm.get("action_id") != action["action_id"]
        or arm.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or wire._NONCE.fullmatch(arm_nonce) is None  # noqa: SLF001
    ):
        raise WarmSessionError("ARM response differs; claim remains consumed")

    execute_headers = _headers(action, boot_nonce, EXECUTE_INTENT)
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    execute = _request(
        requester,
        transcript,
        origin,
        "execute",
        method="POST",
        headers=execute_headers,
    )
    if (
        execute.get("accepted") is not True
        or execute.get("execute_consumed") is not True
        or execute.get("action_id") != action["action_id"]
    ):
        raise WarmSessionError("EXECUTE response differs; claim remains consumed")

    delay = (55.0 if ordinal == 1 else 22.0) if first_poll_seconds is None else first_poll_seconds
    terminal: Mapping[str, Any] | None = None
    for index in range(poll_count):
        if delay > 0:
            time.sleep(delay)
        report = _request(requester, transcript, origin, "report")
        if report.get("ordinal") == ordinal and report.get("terminal_state") in (
            "COMPLETE",
            "FAULT",
        ):
            terminal = report
            break
        delay = following_poll_seconds
    if terminal is None:
        raise WarmSessionError("terminal report not observed; action must not be retried")
    _validate_terminal_report(terminal, action, boot_nonce)

    result = wire._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-partial-hold-warm-session-v1-result",
            "created_at": wire._now(),  # noqa: SLF001
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "action": dict(action),
            "claim_file": str(claim_file.resolve()),
            "terminal_report": dict(terminal),
            "transcript": transcript,
            "network": {
                "get": sum(item["method"] == "GET" for item in transcript),
                "arm_post": 1,
                "execute_post": 1,
            },
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    wire._write_new(output, result)  # noqa: SLF001
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    diagnose = sub.add_parser("diagnose-j2-off")
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnose.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--first-poll-seconds", type=float)
    run.add_argument("--poll-count", type=int, default=3)
    run.add_argument("--following-poll-seconds", type=float, default=3.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(args.base_url, output=args.output)
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                first_poll_seconds=args.first_poll_seconds,
                poll_count=args.poll_count,
                following_poll_seconds=args.following_poll_seconds,
            )
    except (WarmSessionError, OSError, ValueError) as error:
        print(f"warm-session error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
