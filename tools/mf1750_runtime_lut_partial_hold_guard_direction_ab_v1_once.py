#!/usr/bin/env python3
"""Fail-closed one-action runner for explicit guard-direction A/B V1.

The runner never flashes, resets, controls power, retries, recovers, skips an
ordinal, or chains actions.  Every ordinal requires raw BUSY=1.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_pack as pack,
)


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_endpoint_ab_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_guard_direction_ab_v1_private_endpoint_host", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load endpoint one-shot mechanics: {_BASE_PATH}")
endpoint = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(endpoint)
v3 = endpoint.v3
v2 = endpoint.v2
v1 = endpoint.v1
base = endpoint.base

REPORT = pack.build_report()
_BASE_DIAGNOSE_J2_OFF = base.runner.diagnose_j2_off
for module in (endpoint, v3, v2, base):
    module.pack = pack
endpoint.REPORT = REPORT
v3.REPORT = REPORT
v2.REPORT = REPORT
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

MAIN_BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-guard-direction-ab-v1"
    / "ec5_runtime_lut_partial_hold_guard_direction_ab_v1"
)
FIRMWARE_BIN = MAIN_BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = MAIN_BUILD_DIR / "firmware.elf"
FIRMWARE_BIN_BYTES = 797_168
FIRMWARE_BIN_SHA256 = "db5857e7926828cddb4fd9ac44ac860e275f5323060b7932ed429e2ab8d6e312"
FIRMWARE_ELF_BYTES = 13_291_304
FIRMWARE_ELF_SHA256 = "b285190f80318279d1460aefe263265f8fb0576f36f0f294c004a6f50f15a5f4"

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_DEVICE_V1"
)
base.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-guard-direction-ab-v1"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_EXPLICIT_8_ROW_GUARD_DIRECTION_"
    "CONTROLLER_SWAP_AB_BUSY_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-ptlw-guard-direction-ab-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-ptlw-guard-direction-ab-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
v3.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
v3.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-ptlw-guard-direction-ab-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_BUSY_QUALIFIED_FACTORY_WHITE_OR_EXPLICIT_GUARD_DIRECTION_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_BUSY_QUALIFIED_FACTORY_WHITE_OR_EXPLICIT_GUARD_DIRECTION_ACTION_ONCE"
)
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_ptlw_guard_direction_ab_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_20260824_V1"
)

_PROFILE_SOURCE = "factory_otp_white_plus_legacy_complete_535_reference_active_global"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_binding_status() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, path, byte_count, wanted in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = _sha256(path) if present else None
        result[key] = {
            "path": str(path),
            "present": present,
            "verified": bool(
                present and observed_bytes == byte_count and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
            "expected_bytes": byte_count,
            "expected_sha256": wanted,
        }
    return result


def _require_artifact_binding() -> None:
    if any(item["verified"] is not True for item in artifact_binding_status().values()):
        raise base.runner.RecheckError(
            "guard-direction A/B BIN/ELF binding differs; refusing device access"
        )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "same_palette_hold_probe",
        "explicit_guard_direction_probe",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "cross_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("guard-direction capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("guard-direction forbidden operation differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "profile_source": _PROFILE_SOURCE,
        "action_count": 5,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "automatic_execute": False,
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "electrical_parameter_write": False,
        "dither": False,
        "spatial_mixing": False,
        "retry": False,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"guard-direction version {key} differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != pack.NVS_NAMESPACE
        or nvs.get("key") != pack.NVS_KEY
        or nvs.get("terminal_next_ordinal") != 6
    ):
        raise base.runner.RecheckError("guard-direction NVS isolation differs")
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "profile_source": _PROFILE_SOURCE,
        "actions": list(base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"guard-direction manifest {key} differs")
    layout = value.get("history_layout", {})
    layout_exact = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_recovery_ordinal": 5,
        "runtime_transport_codes": [5, 7],
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_mode": 1,
        "ptlw_guard_contract": "EXPLICIT_DECLARED_ROWS_EQUAL_STREAMED_ROWS",
        "guard_matrix": [
            {"ordinal": 2, "cs1": "BOTTOM_8", "cs2": "TOP_8"},
            {"ordinal": 4, "cs1": "TOP_8", "cs2": "BOTTOM_8"},
        ],
        "target_roi": {"x": 176, "y": 240, "width": 160, "height": 120},
        "guard_rows": 8,
        "dtm_rows_per_controller": 128,
        "dtm_bytes_per_controller": 10240,
        "repeat_ptlw_after_pon_busy": True,
        "same_roi_crossover": True,
        "fresh_white_before_each_treatment": True,
        "runtime_code7_is_guard_not_recovery": True,
        "busy_idle_level_required": 1,
        "busy_zero_accepted": False,
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"guard-direction layout {key} differs")
    profile = REPORT["contract"]["profile"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != profile[key]:
            raise base.runner.RecheckError(f"guard-direction LUT {key} differs")
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _require_artifact_binding()
    return v3.run_once(*args, **kwargs)


def salvage_fault_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _require_artifact_binding()
    return v3.salvage_fault_once(*args, **kwargs)


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Any = base.runner._http_request,  # noqa: SLF001
) -> dict[str, Any]:
    """Perform exactly four direct GETs, with no claim, POST, or refresh."""

    if confirm_j2_off is not True:
        raise base.runner.RecheckError(
            "diagnose-j2-off requires explicit J2-OFF confirmation"
        )
    _require_artifact_binding()
    value = _BASE_DIAGNOSE_J2_OFF(
        base_url,
        output=output,
        requester=requester,
    )
    if value.get("network") != {"get": 4, "post": 0}:
        raise base.runner.RecheckError("J2-OFF diagnostic network count differs")
    return value


def describe() -> dict[str, Any]:
    value = v3.describe()
    value["variant"] = deepcopy(REPORT["contract"])
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "factory_otp_white_ordinals": [1, 3, 5],
        "runtime_lut_partial_ordinals": [2, 4],
        "runtime_lut_profile_id": pack.PROFILE_ID,
        "ptlw_command": "0x83",
        "ptlw_mode": 1,
        "target_roi": {"x": 176, "y": 240, "width": 160, "height": 120},
        "guard_rows": 8,
        "stream_rows_per_controller": 128,
        "stream_bytes_per_controller": 10240,
        "guard_matrix": deepcopy(REPORT["contract"]["controlled_delta"]),
        "ptlw_writes_per_controller_for_partial_actions": 2,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["artifact_binding_status"] = artifact_binding_status()
    value["evidence_boundary"] = deepcopy(REPORT["contract"]["evidence_boundary"])
    value["containment_required_after_abnormal_partial_action"] = True
    value["no_ordinal_skip_to_final_white"] = True
    return value


for module in (endpoint, v3, v2, base):
    module._validate_capabilities = _validate_capabilities
    module._validate_version = _validate_version
    module._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
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
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url, args.ordinal, claims=args.claims, output=args.output
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
        print(f"guard-direction A/B error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
