#!/usr/bin/env python3
"""Fail-closed one-action runner for cross-palette local-HOLD V1.

The five immutable actions are factory white, active-header patch A,
commented-header patch B while A is held, active-header patch C while A/B are
held, and factory-white recovery.  This host never flashes, resets, controls
power, retries, recovers automatically, or chains actions.
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
    mf1750_runtime_lut_cross_palette_partial_hold_v1_pack as pack,
)


# Reuse the audited permanent-claim, terminal-staging and fault-salvage
# mechanics through a private module so public runner globals are untouched.
_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_cross_palette_partial_hold_v1_private_v3_host", _V3_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load BUSY-qualified host mechanics: {_V3_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)
v1 = v3.v1
base = v3.base
_V3_VALIDATE_COMPLETE_REPORT = v3._validate_complete_report  # noqa: SLF001

REPORT = pack.build_report()
v3.pack = pack
v3.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_DEVICE_V1"
)
base.runner.IDENTITY_REVISION = "runtime-lut-cross-palette-partial-hold-v1"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_"
    "BUSY_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = (
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v1"
)
base.runner.EVIDENCE_KIND_PREFIX = (
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v1"
)
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

# Filled only after a reviewed clean PlatformIO build.  Every device-facing
# entry point fails closed while either value remains absent or malformed.
FIRMWARE_SHA256: str | None = (
    "7f5870b065b72d865a42bb90887a160940ccfd572576f2fc6c12d652943cd79e"
)
FIRMWARE_BYTES: int | None = 797_152
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES

base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-cross-palette-partial-hold-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_BUSY_QUALIFIED_FACTORY_WHITE_OR_L535_CROSS_PROFILE_"
    "PARTIAL_HOLD_V1_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_BUSY_QUALIFIED_FACTORY_WHITE_OR_L535_CROSS_PROFILE_"
    "PARTIAL_HOLD_V1_ACTION_ONCE"
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
    / ".mf1750_runtime_lut_cross_palette_partial_hold_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_20260824_V1"
)

_FIRMWARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_HEALTH_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"
_PROFILE_SOURCE = (
    "factory_otp_white_plus_legacy_complete_535_reference_"
    "active_and_commented_globals"
)


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
            "cross-palette local-HOLD V1 firmware is not bound; refusing device access"
        )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "cross_palette_hold_probe",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("cross-palette local-HOLD capability differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "cross-palette local-HOLD forbidden capability differs"
        )


def _validate_baseline(value: Mapping[str, Any]) -> None:
    expected = {
        "ordinal": 1,
        "role": _FACTORY_HEALTH_ROLE,
        "external_anchor_required": False,
        "anchor_established_by_firmware": True,
        "one_visible_refresh_required": True,
        "runtime_code7_action_reachable": False,
        "factory_otp_recovery_ordinal": 5,
    }
    if value.get("baseline_contract") != expected:
        raise base.runner.RecheckError("factory-white anchor contract differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    expected_false = (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    )
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("profile_source") != _PROFILE_SOURCE
        or value.get("action_count") != 5
        or value.get("factory_otp") is not True
        or value.get("custom_lut_or_waveform") is not True
        or value.get("runtime_lut_write") is not True
        or any(value.get(key) is not False for key in expected_false)
    ):
        raise base.runner.RecheckError("device cross-palette local-HOLD safety differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != base.runner.NVS_NAMESPACE
        or nvs.get("key") != base.runner.NVS_KEY
        or nvs.get("terminal_next_ordinal") != 6
    ):
        raise base.runner.RecheckError("device NVS isolation differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if value.get("actions") != list(base.runner.ACTIONS):
        raise base.runner.RecheckError("device five-action manifest differs")
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "profile_source": _PROFILE_SOURCE,
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device manifest {key} differs")

    layout = value.get("history_layout", {})
    layout_exact = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_recovery_ordinal": 5,
        "factory_otp_white_frame_fill_byte": 0x11,
        "factory_otp_white_frame_bytes": 307_200,
        "anchor_established_by_firmware": True,
        "external_factory_white_anchor_required": False,
        "runtime_code7_action_reachable": False,
        "runtime_transport_codes": [5, 6, 3],
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "ptlw_mode": 1,
        "ptlw_writes_per_controller": 2,
        "initial_ptlw_before_cropped_dtm": True,
        "repeat_ptlw_after_pon_busy": True,
        "pre_pon_cdi_ff_preserved": True,
        "post_pon_sequence": [
            "PTLW_CS1",
            "PTLW_CS2",
            "CDI_FF_BOTH",
            "BTST2",
            "DRF",
        ],
        "pon_timeout_ms": 60_000,
        "cropped_dtm": True,
        "packed_bpp": 4,
        "windows_disjoint": True,
        "cs2_position_mirrored": False,
        "runtime_lut_profile_id": pack.PROFILE_ID,
        "global_header_profile_sequence": [
            None,
            "active",
            "commented",
            "active",
            None,
        ],
        "global_header_switching": True,
        "sequential_hold_observation_required": True,
        "camera_required": False,
        "busy_idle_level_required": 1,
        "busy_zero_accepted": False,
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"device layout {key} differs")
    fixed_profile = REPORT["contract"]["profiles"]["active"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != fixed_profile[key]:
            raise base.runner.RecheckError(f"device LUT profile {key} differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= len(base.runner.ACTIONS):
        raise base.runner.RecheckError("runnable ordinal differs")
    if expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError("every ordinal requires raw ready BUSY=1")
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
            raise base.runner.RecheckError(f"ready status {key} differs")
    return nonce


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    # The inherited validator is already strict about action identity, all
    # three BUSY observations, positive timings, FNV identities and safe GPIO.
    _V3_VALIDATE_COMPLETE_REPORT(value, ordinal, boot_nonce)


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("prior terminal ordinal differs")
    _validate_complete_report(value, ordinal - 1, boot_nonce)
    if ordinal == 2 and value.get("role") != _FACTORY_HEALTH_ROLE:
        raise base.runner.RecheckError(
            "ordinal 2 requires prior factory-white health COMPLETE"
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
    """Consume exactly one action and strictly validate terminal evidence."""

    _require_firmware_binding()
    if poll_seconds < base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
        raise base.runner.RecheckError("run requires poll_seconds >= 65")
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise base.runner.RecheckError("run requires poll_count >= 1")
    output = Path(output)
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    staged = output.with_name(f".{output.name}.cross-hold-v1-terminal-staging")
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
            "terminal COMPLETE failed strict cross-palette HOLD validation; "
            "raw observation saved; action must not be retried"
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
    value = v3.v2.describe()
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["device_access_fail_closed_until_firmware_bound"] = True
    value["preflight_busy_contract"] = {
        "ordinals_1_to_5": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "factory_otp_white_ordinals": [1, 5],
        "cross_palette_partial_ordinals": [2, 3, 4],
        "profile_sequence": [None, "active", "commented", "active", None],
        "runtime_transport_codes": [5, 6, 3],
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "ptlw_mode": 1,
        "ptlw_writes_per_controller_for_partial_actions": 2,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
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
    value["forbidden_operations"] = {
        "runtime_code7_action": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "skip_to_factory_white_recovery": False,
        "ordinal_5_requires_ordinal_4_complete": True,
        "fault_containment_requires_separate_fresh_firmware": True,
    }
    return value


# Rebind every dynamic validation point in the private facade.
v3._validate_capabilities = _validate_capabilities
v3._validate_version = _validate_version
v3._validate_manifest = _validate_manifest
v3._validate_ready_status = _validate_ready_status
v3._validate_complete_report = _validate_complete_report
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._preflight = _preflight
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
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
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
        print(f"cross-palette local-HOLD V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
