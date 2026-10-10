#!/usr/bin/env python3
"""Fail-closed one-action host runner for repeat-PTLW V2.

V2 contains five immutable actions: factory-OTP white health, three disjoint
L535 cropped patches, and factory-OTP white recovery.  This module never
flashes, resets, controls power, retries, recovers automatically, or chains
actions.  Live/read-only device commands remain disabled until a reviewed V2
firmware binary is bound below by byte count and SHA-256.
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
    mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_pack as pack,
)


# Load the enhanced V1 one-shot mechanics into a private module.  Its base
# runner is private too, so rebinding V2 identities cannot alter the public V1
# module when both runners are imported by the same host process.
_V1_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_repeat_ptlw_v2_private_v1_host", _V1_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load enhanced one-shot base: {_V1_PATH}")
v1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v1)
base = v1.base

REPORT = pack.build_report()
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V2"
)
base.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-repeat-ptlw-v2"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_REPEAT_PTLW_WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw-v2"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw-v2"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

# Bound to the reviewed final Carson build.  All device-facing entry points
# still call _require_firmware_binding() before the first GET or POST so a
# future accidental removal/malformed replacement fails closed.
FIRMWARE_SHA256: str | None = (
    "c1e6851f42156ec0f34b98036ae8b89e29ebf5176dac0f8d930605178391cdef"
)
FIRMWARE_BYTES: int | None = 796_160
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES

base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-repeat-ptlw-v2/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_FACTORY_WHITE_OR_L535_REPEAT_PTLW_V2_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_FACTORY_WHITE_OR_L535_REPEAT_PTLW_V2_ACTION_ONCE"
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
    / ".mf1750_runtime_lut_repeat_ptlw_v2_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_REPEAT_PTLW_20260823_V2"
)

_FIRMWARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_HEALTH_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"
_PROFILE_SOURCE = (
    "factory_otp_white_plus_legacy_complete_535_reference_active_global"
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
            "V2 firmware SHA-256/byte count is not bound; refusing device access"
        )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "same_palette_hold_probe",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "cross_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("V2 capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("V2 forbidden-operation contract differs")


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
        raise base.runner.RecheckError("V2 factory-white health contract differs")


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
    if value.get("action_count") != 5:
        raise base.runner.RecheckError("device V2 action count differs")
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("profile_source") != _PROFILE_SOURCE
        or value.get("factory_otp") is not True
        or value.get("custom_lut_or_waveform") is not True
        or value.get("runtime_lut_write") is not True
        or any(value.get(key) is not False for key in expected_false)
    ):
        raise base.runner.RecheckError("device V2 safety contract differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != base.runner.NVS_NAMESPACE
        or nvs.get("key") != base.runner.NVS_KEY
        or nvs.get("terminal_next_ordinal") != 6
    ):
        raise base.runner.RecheckError("device V2 NVS isolation differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if value.get("actions") != list(base.runner.ACTIONS):
        raise base.runner.RecheckError("device five-action V2 manifest differs")
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
            raise base.runner.RecheckError(f"device V2 manifest {key} differs")

    profile = REPORT["contract"]["profile"]
    layout = value.get("history_layout", {})
    layout_exact = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_recovery_ordinal": 5,
        "factory_otp_white_frame_fill_byte": 0x11,
        "factory_otp_white_frame_bytes": 307_200,
        "anchor_established_by_firmware": True,
        "external_factory_white_anchor_required": False,
        "runtime_code7_action_reachable": False,
        "runtime_transport_codes": [3, 5, 6],
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
        "global_header_profile": "legacy_active",
        "sequential_hold_observation_required": True,
        "camera_required": False,
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"device V2 layout {key} differs")
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != profile[key]:
            raise base.runner.RecheckError(f"device V2 LUT profile {key} differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= len(base.runner.ACTIONS):
        raise base.runner.RecheckError("V2 runnable ordinal differs")
    observed_busy = value.get("busy")
    if ordinal == 1:
        if base.runner.ACTIONS[0].get("role") != _FACTORY_HEALTH_ROLE:
            raise base.runner.RecheckError(
                "V2 ordinal 1 is not the factory-white health action"
            )
        accepted_busy = 0 if expected_busy == 1 and observed_busy == 0 else 1
    else:
        if observed_busy != 1:
            raise base.runner.RecheckError(
                "V2 ordinal 2-5 requires ready BUSY=1"
            )
        accepted_busy = 1
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=accepted_busy
    )
    expected_count = ordinal - 1
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"device V2 ready status {key} differs")
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    v1._validate_prior_terminal_report(value, ordinal, boot_nonce)  # noqa: SLF001
    if ordinal == 2:
        prior = base.runner.ACTIONS[0]
        if (
            prior.get("role") != _FACTORY_HEALTH_ROLE
            or value.get("role") != _FACTORY_HEALTH_ROLE
        ):
            raise base.runner.RecheckError(
                "V2 ordinal 2 requires prior factory-white health COMPLETE"
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


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 2.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    _require_firmware_binding()
    return v1.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


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
    value = v1._BASE_DESCRIBE()  # noqa: SLF001
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["device_access_fail_closed_until_firmware_bound"] = True
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "factory_otp_white_ordinals": [1, 5],
        "runtime_lut_partial_ordinals": [2, 3, 4],
        "runtime_lut_profile_id": pack.PROFILE_ID,
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "ptlw_mode": 1,
        "ptlw_writes_per_controller_for_partial_actions": 2,
        "blocking_refresh_first_poll_floor_seconds": (
            base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS
        ),
    }
    value["preflight_busy_contract"] = {
        "ordinal_1": "BUSY_0_OR_1_STRICT_FRESH_FACTORY_WHITE_HEALTH_ONLY",
        "ordinals_2_to_5": (
            "BUSY_1_AND_SAME_BOOT_PRIOR_COMPLETE_SAFE_FINISH_1_1_1"
        ),
    }
    value["forbidden_operations"] = {
        "runtime_code7_action": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    value["read_only_fault_salvage"] = {
        "command": "salvage-fault",
        "requires_bound_firmware": True,
        "requires_existing_permanent_claim": True,
        "requires_same_boot_fault_status_and_report": True,
        "network": {"get": 4, "post": 0},
        "action_must_not_be_retried": True,
    }
    value["consumed_failure_persistence"] = {
        "terminal_fault": True,
        "terminal_report_read_error": True,
        "terminal_poll_exhaustion": True,
        "automatic_retry": False,
    }
    return value


# Rebind every dynamically looked-up validation point in the private facade.
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
            if args.poll_seconds < base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
                raise base.runner.RecheckError(
                    "V2 run requires --poll-seconds >= 65"
                )
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"repeat-PTLW V2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
