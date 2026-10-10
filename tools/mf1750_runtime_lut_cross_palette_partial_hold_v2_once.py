#!/usr/bin/env python3
"""Fail-closed one-action runner for clean-PTLW cross-palette HOLD V2.

This host never flashes, resets, controls J2/power, retries, recovers, or
chains actions.  It reuses the sealed Fullframe/PTLW V2 evidence mechanics,
including output reservation, permanent claims, recursive prior-result binding,
three BUSY admission snapshots, and the per-action exact dual-REV qualifier.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_cross_palette_partial_hold_v2_pack as pack,
)


_HOST_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_ptlw_fullframe_ab_v2_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_cross_palette_partial_hold_v2_private_clean_ptlw_host",
    _HOST_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load clean-PTLW V2 host mechanics: {_HOST_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)

REPORT = pack.build_report()
base = host.base
v1b = host.v1b
endpoint = host.endpoint
v3 = host.v3
v2 = host.v2
v1 = host.v1

for module in (v1b, endpoint, v3, v2, base):
    module.pack = pack
host.pack = pack
host.REPORT = REPORT
v1b.REPORT = REPORT
endpoint.REPORT = REPORT
v3.REPORT = REPORT
v2.REPORT = REPORT
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

MAIN_BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-cross-palette-partial-hold-v2"
    / "ec5_runtime_lut_cross_palette_partial_hold_v2"
)
FIRMWARE_BIN = MAIN_BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = MAIN_BUILD_DIR / "firmware.elf"
FIRMWARE_BIN_BYTES: int | None = 816_656
FIRMWARE_BIN_SHA256: str | None = (
    "9139c4d243287caba125a87d57a83684bd10647a5107c476b45aab36f7ae060a"
)
FIRMWARE_ELF_BYTES: int | None = 13_368_436
FIRMWARE_ELF_SHA256: str | None = (
    "683f4578a7e853bb72a704cb465a89546ae4f4f0118fbc59bde30ce74c7015ce"
)

host.MAIN_BUILD_DIR = MAIN_BUILD_DIR
host.FIRMWARE_BIN = FIRMWARE_BIN
host.FIRMWARE_ELF = FIRMWARE_ELF
host.FIRMWARE_BIN_BYTES = FIRMWARE_BIN_BYTES
host.FIRMWARE_BIN_SHA256 = FIRMWARE_BIN_SHA256
host.FIRMWARE_ELF_BYTES = FIRMWARE_ELF_BYTES
host.FIRMWARE_ELF_SHA256 = FIRMWARE_ELF_SHA256

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_"
    "CLEAN_PTLW_V2_PER_ACTION_EXACT_DUAL_REV_QUALIFIED_WITH_"
    "FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.EVIDENCE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
v3.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
v3.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
base.runner.ENDPOINTS = {
    name: f"{pack.ENDPOINT_BASE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "CROSS_PALETTE_PARTIAL_HOLD_V2_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "CROSS_PALETTE_PARTIAL_HOLD_V2_ACTION_ONCE"
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
    / ".mf1750_runtime_lut_cross_palette_partial_hold_v2_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_20260826_V2"
)

_PROFILE_SOURCE = (
    "factory_otp_white_plus_legacy_complete_535_reference_"
    "active_and_commented_globals"
)
host._PROFILE_SOURCE = _PROFILE_SOURCE


def _expect(value: Mapping[str, Any], exact: Mapping[str, Any], label: str) -> None:
    host._expect(value, exact, label)


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "cross_palette_hold_probe",
        "runtime_code7_full_dtm_prestage",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "ptlw_fullframe_ab_probe",
        "runtime_treatment_action_stage_cdi",
        "runtime_treatment_action_stage_btst2",
        "runtime_treatment_repeat_ptlw_after_pon_busy",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("cross-HOLD V2 capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("cross-HOLD V2 forbidden capability differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    _expect(
        value,
        {
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
            "per_action_readiness_qualification_required": True,
            "three_gate_busy_admission_evidence_required": True,
            "qualifier_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        },
        "cross-HOLD V2 version",
    )
    nvs = value.get("nvs_contract")
    if not isinstance(nvs, Mapping):
        raise base.runner.RecheckError("cross-HOLD V2 NVS contract is absent")
    _expect(
        nvs,
        {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 6,
            "initial_key_present": False,
            "initial_value": 1,
            "initial_next_ordinal": 1,
        },
        "cross-HOLD V2 NVS",
    )
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    _expect(
        value,
        {
            "layout_id": pack.VARIANT_KEY,
            "profile_source": _PROFILE_SOURCE,
            "actions": list(base.runner.ACTIONS),
            "action_count": 5,
            "one_driver_call_per_action": True,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
            "automatic_chaining": False,
            "startup_refresh": False,
            "retry": False,
            "recovery": False,
            "per_action_readiness_qualification": (
                host._expected_qualification_contract()
            ),
            "busy_admission_contract": pack.BUSY_ADMISSION_CONTRACT,
        },
        "cross-HOLD V2 manifest",
    )
    layout = value.get("history_layout")
    if not isinstance(layout, Mapping):
        raise base.runner.RecheckError("cross-HOLD V2 history layout is absent")
    wanted_layout = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_recovery_ordinal": 5,
        "runtime_transport_codes": [5, 6, 3],
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_mode": 1,
        "ptlw_payloads_hex": [payload.hex() for payload in pack.PTLW_PAYLOADS],
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "windows": [
            {
                "x": window.x,
                "y": window.y,
                "width": window.width,
                "height": window.height,
                "cs1_code": window.cs1_code,
                "cs2_code": window.cs2_code,
            }
            for window in pack.WINDOWS
        ],
        "windows_disjoint": True,
        "runtime_code7_full_dtm_prestage": True,
        "runtime_code7_prestage_no_refresh": True,
        "runtime_code7_prestage_bytes_per_controller": 153_600,
        "runtime_code7_prestage_sha256": pack.PRELOAD_DTM_SHA256,
        "runtime_target_dtm_bytes_per_controller": 9_600,
        "runtime_combined_dtm_bytes_per_controller": 163_200,
        "runtime_dtm_transport": (
            "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP"
        ),
        "global_header_profile_sequence": [
            None,
            "active",
            "commented",
            "active",
            None,
        ],
        "global_header_switching": True,
        "common_runtime_refresh_sequence": [
            "PON_BUSY_COMPLETE_60S_GATE",
            "DRF_00_BUSY_COMPLETE_60S_GATE",
            "POF_00_BUSY_COMPLETE_60S_GATE",
        ],
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "command_0x86": False,
        "extra_dtm_prefix_or_suffix_byte": False,
        "sequential_hold_observation_required": True,
        "human_observation_gate_after_each_action": True,
        "busy_idle_level_required": 1,
        "ordinal_1_raw_levels_accepted": [1],
        "fresh_low_admission_forbidden": True,
        "j2_off_raw0_allowed_only_on_read_only_get_diagnostic": True,
        "later_ordinal_raw_levels_accepted": [0, 1],
        "late_low_is_never_treated_as_idle": True,
        "late_low_requires_same_boot_prior_complete": True,
        "late_low_requires_prior_safe_finish_high": True,
        "late_low_requires_ram_only_firmware_eligibility": True,
        "late_pof_sleep_low_eligible_boot_default": False,
        "late_pof_sleep_low_eligible_consumed_before_qualification": True,
        "per_action_revision_qualifier_required": True,
        "unqualified_busy_zero_accepted": False,
    }
    for key, wanted in wanted_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(
                f"cross-HOLD V2 history layout {key} differs"
            )
    runtime_actions = layout.get("runtime_actions")
    if not isinstance(runtime_actions, list) or len(runtime_actions) != 3:
        raise base.runner.RecheckError("cross-HOLD V2 runtime actions differ")
    for index, item in enumerate(runtime_actions):
        expected = {
            "ordinal": index + 2,
            "global_header": ("active", "commented", "active")[index],
            "code": pack.TARGET_CODES[index],
            "ptlw_writes_per_controller": 1,
            "target_dtm_sha256": pack.TARGET_DTM_SHA256[index],
            "combined_dtm_sha256": pack.COMBINED_DTM_SHA256[index],
        }
        if item != expected:
            raise base.runner.RecheckError(
                f"cross-HOLD V2 runtime action {index + 2} differs"
            )
    active = REPORT["contract"]["profiles"]["active"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != active[key]:
            raise base.runner.RecheckError(
                f"cross-HOLD V2 LUT profile {key} differs"
            )
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


def _expected_action_stage_counts(ordinal: int) -> dict[str, int]:
    if ordinal in (1, 5):
        dtm_bytes, lut_bytes, ptlw_writes = 307_200, 0, 0
    elif ordinal in (2, 3, 4):
        dtm_bytes, lut_bytes, ptlw_writes = 326_400, 2_478, 2
    else:
        raise base.runner.RecheckError("cross-HOLD V2 action-stage ordinal differs")
    return {
        "pon": 1,
        "pof": 1,
        "drf": 1,
        "dtm_bytes": dtm_bytes,
        "lut_bytes": lut_bytes,
        "ptlw_writes": ptlw_writes,
        "command_0x86": 0,
        "visible_refresh_requests": 1,
    }


host._validate_capabilities = _validate_capabilities
host._validate_version = _validate_version
host._validate_manifest = _validate_manifest
host._expected_action_stage_counts = _expected_action_stage_counts

for module in (v1b, endpoint, v3, v2, base):
    module._validate_capabilities = _validate_capabilities
    module._validate_version = _validate_version
    module._validate_manifest = _validate_manifest
base.runner._validate_capabilities = _validate_capabilities
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = host._validate_ready_status
base.runner._preflight = host._preflight
base.runner._request = host._request_with_busy_evidence
base.runner._write_new = host._write_new_bound
base.runner.run_once = host.run_once
v1._validate_fresh_no_execute_report = host._validate_fresh_no_execute_report
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._validate_ready_status = host._validate_ready_status
v1._validate_fault_status = host._validate_fault_status
v1._validate_fault_report = host._validate_fault_report
v1._load_permanent_claim = host._load_permanent_claim
v1._preflight = host._preflight
v2._validate_ready_status = host._validate_ready_status
v2._preflight = host._preflight
v3._validate_ready_status = host._validate_ready_status
v3._validate_complete_report = host._validate_complete_report
v3._validate_prior_terminal_report = host._validate_prior_terminal_report_bound
v3._preflight = host._preflight


def describe() -> dict[str, Any]:
    value = host.describe()
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "factory_otp_white_ordinals": [1, 5],
        "runtime_lut_partial_ordinals": [2, 3, 4],
        "runtime_lut_codes": list(pack.TARGET_CODES),
        "runtime_global_headers": ["active", "commented", "active"],
        "runtime_lut_profile_id": pack.PROFILE_ID,
        "full_code7_prestage_bytes_per_controller": pack.CONTROLLER_DTM_BYTES,
        "target_crop_bytes_per_controller": list(pack.CROPPED_DTM_BYTES),
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "ptlw_mode": 1,
        "ptlw_writes_per_controller_for_partial_actions": 1,
        "repeat_ptlw_after_pon_busy": False,
        "action_stage_cdi": False,
        "action_stage_btst2": False,
        "command_0x86": False,
        "refresh_sequence": ["PON", "DRF_00", "POF_00"],
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["variant"] = deepcopy(REPORT["contract"])
    value["action_order"] = [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "PATCH_A_ACTIVE_CODE5",
        "PATCH_B_COMMENTED_CODE6_HOLD_A",
        "PATCH_C_ACTIVE_CODE3_HOLD_AB",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]
    value["human_observation_gate_after_each_action"] = True
    value["live_authorized"] = False
    return value


base.runner.describe = describe


def _parse_args(argv: Sequence[str] | None) -> Any:
    return host._parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = host.dry_validate()
            if value.get("verified") is not True:
                print(json.dumps(value, ensure_ascii=False, sort_keys=True))
                return 2
        elif args.command == "diagnose-j2-off":
            value = host.diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "salvage-fault":
            value = host.salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = host.run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"clean-PTLW cross-HOLD V2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
