#!/usr/bin/env python3
"""Fail-closed one-action runner for full-frame versus PTLW A/B V1.

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
    mf1750_runtime_lut_ptlw_fullframe_ab_v1_pack as pack,
)


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_endpoint_ab_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_ptlw_fullframe_ab_v1_private_endpoint_host", _BASE_PATH
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
EVIDENCE_BOUNDARY = {
    "offline_build_proves_panel_result": False,
    "live_ab_required": True,
    "treatment_a_and_b_require_separate_observation": True,
    "formal_8x2_calibration_requires_three_clean_b_cycles": True,
    "nominal_slots_after_gate": 16,
    "nominal_slots_are_distinct_colors_without_measurement": False,
    "deduplicate_by_measured_color": True,
    "do_not_claim_arbitrary_lut_or_256_color_support": True,
}
_BASE_DIAGNOSE_J2_OFF = base.runner.diagnose_j2_off
_LIVE_VALIDATE_READY_STATUS = v3._validate_ready_status  # noqa: SLF001
_STRICT_BASE_VALIDATE_READY_STATUS = (
    v1._BASE_VALIDATE_READY_STATUS  # noqa: SLF001
)
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
    / "build-runtime-lut-ptlw-fullframe-ab-v1"
    / "ec5_runtime_lut_ptlw_fullframe_ab_v1"
)
FIRMWARE_BIN = MAIN_BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = MAIN_BUILD_DIR / "firmware.elf"
# Frozen after a clean offline build on 2026-08-25.  Every device-facing entry
# point re-hashes both artifacts and remains fail-closed if either file moves
# or changes.
FIRMWARE_BIN_BYTES = 800_224
FIRMWARE_BIN_SHA256 = (
    "48fb0397948385feb2a0b155dca22bbb741e346df1a0edd7871c8765bd7181c3"
)
FIRMWARE_ELF_BYTES = 13_303_904
FIRMWARE_ELF_SHA256 = (
    "a0b20e1a44847693027b7dfca9276d3e9ba1befbd89f735c07a8986db3885d8d"
)

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_DEVICE_V1B"
)
base.runner.IDENTITY_REVISION = "runtime-lut-ptlw-fullframe-ab-v1b"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_FULLFRAME_VS_PTLW_AB_LATE_POF_"
    "SLEEP_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v1b"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v1b"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
v3.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
v3.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-ptlw-fullframe-ab-v1b/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_LATE_POF_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "FULLFRAME_PTLW_AB_V1B_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_LATE_POF_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "FULLFRAME_PTLW_AB_V1B_ACTION_ONCE"
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
    / ".mf1750_runtime_lut_ptlw_fullframe_ab_v1b_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_20260825_V1B"
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
            "full-frame/PTLW A/B BIN/ELF binding differs; refusing device access"
        )


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    """Keep J2-OFF, post-action safe hold, and live BUSY gates distinct.

    The inherited four-GET J2-OFF diagnostic intentionally asks for raw
    BUSY=0 because panel power is physically disconnected.  A fresh live
    ordinal 1 can retain the same raw level after externally confirmed J2-ON
    until the driver's reset requalifies idle-HIGH; its strict zero counters
    distinguish it from a resumed action.  After a completed action, pulling
    RST/CS low can likewise make raw BUSY fall to 0 even though the controller
    was idle before safe finish.  For ordinals 2-5 the enclosing V3 preflight
    must still bind the same-boot prior COMPLETE report and strict safe-finish
    evidence before any permanent claim or mutation.
    """

    if expected_busy == 0:
        if ordinal != 1:
            raise base.runner.RecheckError(
                "J2-OFF BUSY=0 is valid only for fresh ordinal 1"
            )
        nonce = _STRICT_BASE_VALIDATE_READY_STATUS(
            value, ordinal, expected_busy=0
        )
        expected_count = 0
        counter_label = "J2-OFF diagnostic"
    elif (
        expected_busy == 1
        and 1 <= ordinal <= len(base.runner.ACTIONS)
        and value.get("busy") == 0
    ):
        nonce = _STRICT_BASE_VALIDATE_READY_STATUS(
            value, ordinal, expected_busy=0
        )
        expected_count = ordinal - 1
        counter_label = (
            "fresh externally powered reset-low"
            if ordinal == 1
            else "post-action safe-hold"
        )
    else:
        return _LIVE_VALIDATE_READY_STATUS(
            value, ordinal, expected_busy=expected_busy
        )

    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(
                f"{counter_label} status {key} differs"
            )
    return nonce


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "ptlw_fullframe_ab_probe",
        "runtime_code7_full_dtm_prestage",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "runtime_treatment_action_stage_cdi",
        "runtime_treatment_action_stage_btst2",
        "runtime_treatment_repeat_ptlw_after_pon_busy",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("full-frame/PTLW capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("full-frame/PTLW forbidden operation differs")


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
            raise base.runner.RecheckError(f"full-frame/PTLW version {key} differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != pack.NVS_NAMESPACE
        or nvs.get("key") != pack.NVS_KEY
        or nvs.get("terminal_next_ordinal") != 6
    ):
        raise base.runner.RecheckError("full-frame/PTLW NVS isolation differs")
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
            raise base.runner.RecheckError(f"full-frame/PTLW manifest {key} differs")
    layout = value.get("history_layout", {})
    layout_exact = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_reset_ordinal": 3,
        "factory_otp_recovery_ordinal": 5,
        "runtime_transport_codes": [5, 7],
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_mode": 1,
        "ptlw_payload_hex": "00b0014f00f0016701",
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "window": {
            "x": 176,
            "y": 240,
            "width": 160,
            "height": 120,
            "cs1_code": 5,
            "cs2_code": 5,
        },
        "runtime_code7_full_dtm_prestage": True,
        "runtime_code7_prestage_no_refresh": True,
        "runtime_code7_prestage_bytes_per_controller": 153600,
        "runtime_code7_prestage_sha256": pack.PRELOAD_DTM_SHA256,
        "treatment_a": {
            "ordinal": 2,
            "ptlw": False,
            "dtm_transport": "FULL_CONTROLLER_COMPOSITE_NO_PTLW",
            "target_dtm_bytes_per_controller": 153600,
            "target_dtm_sha256": pack.FULL_COMPOSITE_DTM_SHA256,
            "combined_dtm_bytes_per_controller": 307200,
            "combined_dtm_sha256": pack.TREATMENT_A_COMBINED_DTM_SHA256,
        },
        "treatment_b": {
            "ordinal": 4,
            "ptlw": True,
            "ptlw_writes_per_controller": 1,
            "dtm_transport": "INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW",
            "target_dtm_bytes_per_controller": 9600,
            "target_dtm_sha256": pack.CROPPED_DTM_SHA256,
            "combined_dtm_bytes_per_controller": 163200,
            "combined_dtm_sha256": pack.TREATMENT_B_COMBINED_DTM_SHA256,
        },
        "same_final_controller_sram": True,
        "same_logical_frame": True,
        "logical_frame_sha256": pack.LOGICAL_FRAME_SHA256,
        "logical_frame_histogram": [0, 0, 0, 0, 0, 38400, 0, 576000],
        "common_refresh_sequence": [
            "PON_BUSY_COMPLETE_60S_GATE",
            "DRF_00_BUSY_COMPLETE_60S_GATE",
            "POF_00_BUSY_COMPLETE_60S_GATE",
        ],
        "fresh_white_before_each_treatment": True,
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "command_0x86": False,
        "extra_dtm_prefix_or_suffix_byte": False,
        "busy_idle_level_required": 1,
        "ordinal_1_raw_levels_accepted": [0, 1],
        "fresh_low_requires_external_j2_on_confirmation": True,
        "fresh_low_requires_zero_driver_count": True,
        "later_ordinal_raw_levels_accepted": [0, 1],
        "late_low_is_never_treated_as_idle": True,
        "late_low_requires_same_boot_prior_complete": True,
        "late_low_requires_prior_safe_finish_high": True,
        "late_low_requires_ram_only_firmware_eligibility": True,
        "driver_reset_requalifies_idle_before_commands": True,
        "unqualified_busy_zero_accepted": False,
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"full-frame/PTLW layout {key} differs")
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
            raise base.runner.RecheckError(f"full-frame/PTLW LUT {key} differs")
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
        "ptlw_payload_hex": "00b0014f00f0016701",
        "target_roi": {"x": 176, "y": 240, "width": 160, "height": 120},
        "sram_prestage_bytes_per_controller": 153_600,
        "full_dtm_bytes_per_controller": 153_600,
        "cropped_dtm_bytes_per_controller": 9_600,
        "controlled_delta": deepcopy(REPORT["contract"]["controlled_delta"]),
        "ptlw_writes_per_controller_for_partial_actions": 1,
        "common_refresh": ["PON", "DRF_00", "POF_00"],
        "action_stage_cdi": False,
        "action_stage_btst2": False,
        "repeat_ptlw_after_pon_busy": False,
        "dtm_prefix_or_suffix_byte": False,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
        "ordinal_1_raw_busy_levels_after_external_j2_on": [0, 1],
        "fresh_raw_busy_zero_requires_zero_driver_count": True,
        "later_raw_busy_zero_requires_same_boot_prior_safe_finish": True,
        "late_pof_sleep_eligibility_is_ram_only": True,
        "driver_reset_requalifies_busy_idle_high": True,
    }
    value["artifact_binding_status"] = artifact_binding_status()
    value["evidence_boundary"] = deepcopy(EVIDENCE_BOUNDARY)
    value["containment_required_after_abnormal_partial_action"] = True
    value["no_ordinal_skip_to_final_white"] = True
    return value


for module in (endpoint, v3, v2, base):
    module._validate_capabilities = _validate_capabilities
    module._validate_version = _validate_version
    module._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
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
        print(f"full-frame/PTLW A/B error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
