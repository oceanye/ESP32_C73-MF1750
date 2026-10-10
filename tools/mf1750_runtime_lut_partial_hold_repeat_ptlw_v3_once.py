#!/usr/bin/env python3
"""Fail-closed one-action host runner for BUSY-qualified repeat-PTLW V3.

V3 contains five immutable actions: factory-OTP white health, three disjoint
L535 cropped patches, and factory-OTP white recovery.  Every action requires
raw ready BUSY=1.  This module never flashes, resets, controls power, retries,
recovers automatically, or chains actions.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_pack as pack,
)


# Use an isolated V2 facade so importing this module cannot rewrite the public
# V2 runner's globals, identities, routes, or validators in the same process.
_V2_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_repeat_ptlw_v3_private_v2_host", _V2_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load V2 one-shot mechanics: {_V2_PATH}")
v2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v2)
v1 = v2.v1
base = v2.base

_V2_VALIDATE_CAPABILITIES = v2._validate_capabilities  # noqa: SLF001
_V2_VALIDATE_VERSION = v2._validate_version  # noqa: SLF001
_V2_VALIDATE_MANIFEST = v2._validate_manifest  # noqa: SLF001

REPORT = pack.build_report()
v2.pack = pack
v2.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V3"
)
base.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-repeat-ptlw-v3"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_REPEAT_PTLW_BUSY_QUALIFIED_"
    "WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw-v3"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw-v3"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

# Reviewed final PlatformIO V3 build.  Device access fails closed if either
# value is removed or malformed.
FIRMWARE_SHA256: str | None = (
    "81a0e6ac8a106a10338cf7045b185b17d11fa913ce0949893ff6de31cea57da4"
)
FIRMWARE_BYTES: int | None = 796_496
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES

base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-repeat-ptlw-v3/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_BUSY_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "REPEAT_PTLW_V3_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_BUSY_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "REPEAT_PTLW_V3_ACTION_ONCE"
)
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_repeat_ptlw_v3_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_REPEAT_PTLW_20260823_V3"
)

_FIRMWARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_HEALTH_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"
_PROFILE_SOURCE = v2._PROFILE_SOURCE  # noqa: SLF001
_NONE_STAGE = "none"


def _firmware_binding() -> dict[str, Any]:
    sha256 = base.runner.FIRMWARE_SHA256
    byte_count = base.runner.FIRMWARE_BYTES
    bound = (
        isinstance(sha256, str)
        and _FIRMWARE_SHA256_RE.fullmatch(sha256) is not None
        and isinstance(byte_count, int)
        and not isinstance(byte_count, bool)
        and byte_count > 0
    )
    return {"bound": bound, "bytes": byte_count, "sha256": sha256}


def _require_firmware_binding() -> None:
    if not _firmware_binding()["bound"]:
        raise base.runner.RecheckError(
            "V3 firmware SHA-256/byte count is not bound; refusing device access"
        )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    _V2_VALIDATE_CAPABILITIES(value)
    if value.get("busy_qualified_arm_execute_dispatch") is not True:
        raise base.runner.RecheckError("device V3 BUSY capability differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _V2_VALIDATE_VERSION(value)
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError("device V3 layout identity differs")


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _V2_VALIDATE_MANIFEST(value)
    layout = value.get("history_layout", {})
    if (
        layout.get("busy_idle_level_required") != 1
        or layout.get("busy_zero_accepted") is not False
    ):
        raise base.runner.RecheckError("device V3 BUSY layout contract differs")


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= len(base.runner.ACTIONS):
        raise base.runner.RecheckError("V3 runnable ordinal differs")
    if expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError(
            "V3 every ordinal requires raw ready BUSY=1"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=1
    )
    expected_count = ordinal - 1
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"device V3 ready status {key} differs")
    return nonce


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    """Validate all immediate terminal evidence before accepting COMPLETE."""

    if not 1 <= ordinal <= len(base.runner.ACTIONS):
        raise base.runner.RecheckError("device V3 COMPLETE ordinal differs")
    action = base.runner.ACTIONS[ordinal - 1]
    source = REPORT["actions"][ordinal - 1]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == len(base.runner.ACTIONS),
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device V3 COMPLETE {key} differs")

    driver = value.get("driver")
    if not isinstance(driver, Mapping):
        raise base.runner.RecheckError("device V3 COMPLETE driver is absent")
    driver_exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": _NONE_STAGE,
        "timeout_stage": _NONE_STAGE,
        "busy_missing_stage": _NONE_STAGE,
        "pre_command_busy_stage": _NONE_STAGE,
        "spi_hz": 1_000_000,
        "operation_id": ordinal,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "input_fnv1a": source["frame"]["fnv1a"],
        "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
        "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
    }
    for key, wanted in driver_exact.items():
        if driver.get(key) != wanted:
            raise base.runner.RecheckError(
                f"device V3 COMPLETE driver {key} differs"
            )
    for key in ("pon_ms", "drf_ms", "pof_ms"):
        if not _positive_int(driver.get(key)):
            raise base.runner.RecheckError(
                f"device V3 COMPLETE driver {key} is not positive"
            )

    safe_finish = driver.get("safe_finish")
    if not isinstance(safe_finish, Mapping) or any(
        safe_finish.get(key) != 1
        for key in (
            "busy_before_pins_low",
            "busy_after_pins_low",
            "busy_after_5ms",
        )
    ):
        raise base.runner.RecheckError(
            "device V3 COMPLETE safe-finish BUSY differs"
        )
    final_gpio = safe_finish.get("final_gpio")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != wanted
        for key, wanted in {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}.items()
    ):
        raise base.runner.RecheckError(
            "device V3 COMPLETE final safe-finish GPIO differs"
        )


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("V3 prior terminal ordinal differs")
    _validate_complete_report(value, ordinal - 1, boot_nonce)
    if ordinal == 2 and value.get("role") != _FACTORY_HEALTH_ROLE:
        raise base.runner.RecheckError(
            "V3 ordinal 2 requires prior factory-white health COMPLETE"
        )


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url,
        ordinal,
        expected_busy=expected_busy,
        requester=requester,
    )
    if ordinal == 1:
        v1._validate_fresh_no_execute_report(report, boot_nonce)  # noqa: SLF001
    else:
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


def _write_staged_result(output: Path, staged: Path) -> None:
    value = json.loads(staged.read_text(encoding="utf-8"))
    base.runner._write_new(output, value)  # noqa: SLF001
    staged.unlink()


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    """Consume one action and accept COMPLETE only after strict V3 checks."""

    _require_firmware_binding()
    if poll_seconds < base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
        raise base.runner.RecheckError("V3 run requires poll_seconds >= 65")
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise base.runner.RecheckError("V3 run requires poll_count >= 1")
    output = Path(output)
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    staged = output.with_name(f".{output.name}.v3-terminal-staging")
    if staged.exists():
        raise base.runner.RecheckError(f"refusing stale staging file {staged}")

    try:
        result = v1.run_once(
            base_url,
            ordinal,
            claims=claims,
            output=staged,
            requester=requester,
            poll_seconds=poll_seconds,
            poll_count=poll_count,
        )
    except base.runner.RecheckError:
        if staged.is_file():
            _write_staged_result(output, staged)
        raise

    terminal_report = result["terminal_report"]
    try:
        _validate_complete_report(terminal_report, ordinal, result["boot_nonce"])
    except base.runner.RecheckError as error:
        claim_file = Path(result["claim_file"])
        claim = json.loads(claim_file.read_text(encoding="utf-8"))
        v1._write_consumed_failure_evidence(  # noqa: SLF001
            output=output,
            action=base.runner.ACTIONS[ordinal - 1],
            claim_file=claim_file,
            claim=claim,
            boot_nonce=result["boot_nonce"],
            transcript=result["transcript"],
            outcome="terminal_complete_rejected",
            error=str(error),
            terminal_report=terminal_report,
        )
        staged.unlink()
        raise base.runner.RecheckError(
            "terminal COMPLETE failed strict V3 validation; raw observation "
            "saved; action must not be retried"
        ) from error

    _write_staged_result(output, staged)
    return result


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
) -> dict[str, Any]:
    _require_firmware_binding()
    return v1.salvage_fault_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
    )


def describe() -> dict[str, Any]:
    value = v2.describe()
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["device_access_fail_closed_until_firmware_bound"] = True
    value["preflight_busy_contract"] = {
        "ordinals_1_to_5": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["terminal_complete_contract"] = {
        "immediate_strict_validation": True,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_seen": ["PON", "DRF", "POF"],
        "positive_wait_ms": ["PON", "DRF", "POF"],
        "stage_sentinels": "none",
        "safe_finish_busy": [1, 1, 1],
        "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
        "fnv1a": ["input", "cs1_dtm", "cs2_dtm"],
        "one_driver_call_per_action": True,
    }
    value["fixed_transport"]["blocking_refresh_first_poll_floor_seconds"] = 65.0
    return value


# Rebind every dynamic validation point in the isolated facade.
v2._validate_capabilities = _validate_capabilities
v2._validate_version = _validate_version
v2._validate_manifest = _validate_manifest
v2._validate_ready_status = _validate_ready_status
v2._validate_prior_terminal_report = _validate_prior_terminal_report
v2._preflight = _preflight
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS,
    )
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument(
        "--claims", type=Path, default=base.runner.DEFAULT_CLAIMS
    )
    salvage.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"repeat-PTLW V3 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
