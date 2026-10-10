#!/usr/bin/env python3
"""Build offline identities for the L535 full-frame versus PTLW A/B probe.

This module has no device, serial, relay, reset, flashing, or network surface.
It freezes two treatments that leave the controller SRAM and logical frame in
the same state.  Both first stage a full controller plane of runtime code 7
without refreshing.  Treatment A then uploads a full composite controller
plane without PTLW; treatment B selects one inclusive PTLW window and uploads
only its code-5 crop.  Both use the same ordinary PON/DRF/POF refresh sequence.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_pack as v3,
)


VARIANT_KEY = "L535_FACTORY_WHITE_PTLW_FULLFRAME_AB_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1B_2026-08-25"
TEST_ID = "EC5-RUNTIME-LUT-PTLW-FULLFRAME-AB-V1B"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1B"
NVS_NAMESPACE = "rlpffab_v1b"
NVS_KEY = "cursor_ffab1b"
PROFILE_ID = v3.PROFILE_ID

WIDTH = identity.WIDTH
HEIGHT = identity.HEIGHT
CONTROLLER_WIDTH = identity.CONTROLLER_WIDTH
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
WHITE_CODE = 7
BLUE_CODE = 5
WINDOW = identity.Window(176, 240, 160, 120, BLUE_CODE, BLUE_CODE)
CROPPED_DTM_BYTES = WINDOW.width * WINDOW.height // 2
PTLW_PAYLOAD = bytes.fromhex("00b0014f00f0016701")

PRELOAD_DTM_SHA256 = (
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd"
)
PRELOAD_DTM_FNV1A = 0x285715C5
FULL_COMPOSITE_DTM_SHA256 = (
    "352e61d15eb963fe2e1b37a07664be885ec6c8a0e1383bb3e96869fe517ca3ed"
)
FULL_COMPOSITE_DTM_FNV1A = 0x2FA81DC5
CROPPED_DTM_SHA256 = (
    "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3"
)
CROPPED_DTM_FNV1A = 0x77244145
TREATMENT_A_COMBINED_DTM_SHA256 = (
    "5f592d3f581cddb9b625a17a1507b7df4a01e16da8e8fefc94783910a33bc190"
)
TREATMENT_A_COMBINED_DTM_FNV1A = 0x83E295C5
TREATMENT_B_COMBINED_DTM_SHA256 = (
    "a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f"
)
TREATMENT_B_COMBINED_DTM_FNV1A = 0xD92EB945
LOGICAL_FRAME_SHA256 = (
    "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576"
)
LOGICAL_FRAME_FNV1A = 0x2E339DC5

WHITE_REFRESH_SEQUENCE = (
    "FACTORY_OTP_PREPARE_CASCADE",
    "FULL_FRAME_0X11_DTM_CS1",
    "FULL_FRAME_0X11_DTM_CS2",
    "PON_BUSY_COMPLETE_60S_GATE",
    "BTST2",
    "DRF_00_BUSY_COMPLETE_60S_GATE",
    "POF_00_BUSY_COMPLETE_60S_GATE",
)
COMMON_RUNTIME_REFRESH_SEQUENCE = (
    "PON_BUSY_COMPLETE_60S_GATE",
    "DRF_00_BUSY_COMPLETE_60S_GATE",
    "POF_00_BUSY_COMPLETE_60S_GATE",
)


def _controller_composite() -> bytes:
    data = bytearray([0x77]) * CONTROLLER_DTM_BYTES
    row_bytes = CONTROLLER_WIDTH // 2
    fill = bytes([0x55]) * (WINDOW.width // 2)
    for y in range(WINDOW.y, WINDOW.y + WINDOW.height):
        start = y * row_bytes + WINDOW.x // 2
        data[start : start + len(fill)] = fill
    return bytes(data)


def _logical_frame() -> bytes:
    frame = bytearray([0x77]) * FRAME_BYTES
    identity.set_rect(frame, WINDOW)
    return bytes(frame)


def _descriptor(item: dict[str, Any]) -> str:
    value = {
        "schema": "mf1750-runtime-lut-ptlw-fullframe-ab-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        **item,
    }
    return identity.sha256(identity.canonical(value))


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def _finish_action(item: dict[str, Any]) -> dict[str, Any]:
    item["descriptor_id"] = _descriptor(item)
    item["action_id"] = _action_id(item["ordinal"], item["descriptor_id"])
    return item


def _white_action(
    *, ordinal: int, role: str, branch: str, white_frame: bytes
) -> dict[str, Any]:
    white_dtm = identity.uniform_identity(1, CONTROLLER_DTM_BYTES)
    return _finish_action(
        {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "palette_source": "FACTORY_OTP",
            "runtime_profile_id": None,
            "target_window": None,
            "ptlw_payload_hex": None,
            "ptlw_writes_per_controller": 0,
            "dtm_transport": "FACTORY_OTP_PACKED_FULL_FRAME_0X11",
            "prestage_dtm": None,
            "sram_sequence": list(WHITE_REFRESH_SEQUENCE[:3]),
            "refresh_sequence": list(WHITE_REFRESH_SEQUENCE[3:]),
            "forbidden_action_stage_commands": [
                "CDI",
                "REPEAT_PTLW_AFTER_PON",
                "0x86",
            ],
            "frame": identity.frame_identity(white_frame),
            "cs1_dtm": white_dtm,
            "cs2_dtm": white_dtm,
        }
    )


def _runtime_action(
    *,
    ordinal: int,
    role: str,
    branch: str,
    treatment: str,
    logical_frame: bytes,
    preload: dict[str, Any],
    full_composite: dict[str, Any],
    cropped: dict[str, Any],
    combined_a: dict[str, Any],
    combined_b: dict[str, Any],
) -> dict[str, Any]:
    is_fullframe = treatment == "A"
    target_dtm = full_composite if is_fullframe else cropped
    combined_dtm = combined_a if is_fullframe else combined_b
    sram_sequence = [
        "FULL_CODE7_PRESTAGE_DTM_CS1_NO_REFRESH",
        "FULL_CODE7_PRESTAGE_DTM_CS2_NO_REFRESH",
    ]
    if is_fullframe:
        sram_sequence.extend(
            ["FULL_COMPOSITE_DTM_CS1", "FULL_COMPOSITE_DTM_CS2"]
        )
    else:
        sram_sequence.extend(
            [
                "INCLUSIVE_PTLW_CS1_PRE_DTM",
                "INCLUSIVE_PTLW_CS2_PRE_DTM",
                "CROPPED_CODE5_DTM_CS1",
                "CROPPED_CODE5_DTM_CS2",
            ]
        )
    return _finish_action(
        {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "treatment": treatment,
            "palette_source": "L535_RUNTIME",
            "runtime_profile_id": PROFILE_ID,
            "target_window": asdict(WINDOW),
            "ptlw_payload_hex": None if is_fullframe else PTLW_PAYLOAD.hex(),
            "ptlw_writes_per_controller": 0 if is_fullframe else 1,
            "dtm_transport": (
                "FULL_CONTROLLER_COMPOSITE_NO_PTLW"
                if is_fullframe
                else "INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW"
            ),
            "prestage_dtm": preload,
            "target_dtm": target_dtm,
            "sram_sequence": sram_sequence,
            "refresh_sequence": list(COMMON_RUNTIME_REFRESH_SEQUENCE),
            "forbidden_action_stage_commands": [
                "CDI",
                "BTST2",
                "REPEAT_PTLW_AFTER_PON",
                "0x86",
            ],
            "frame": identity.frame_identity(logical_frame),
            "cs1_dtm": combined_dtm,
            "cs2_dtm": combined_dtm,
        }
    )


def _require_identity(
    value: dict[str, Any], *, byte_count: int, sha256: str, fnv1a: int
) -> None:
    if value != {"bytes": byte_count, "fnv1a": fnv1a, "sha256": sha256}:
        raise ValueError("computed payload identity differs from frozen contract")


def build_report() -> dict[str, Any]:
    """Build the five immutable action identities without hardware access."""

    identity.validate_window(WINDOW)
    if PTLW_PAYLOAD != bytes(
        [0x00, 0xB0, 0x01, 0x4F, 0x00, 0xF0, 0x01, 0x67, 0x01]
    ):
        raise ValueError("inclusive PTLW payload changed")

    preload_payload = bytes([0x77]) * CONTROLLER_DTM_BYTES
    preload = identity.uniform_identity(WHITE_CODE, CONTROLLER_DTM_BYTES)
    full_composite_payload = _controller_composite()
    full_composite = {
        "bytes": len(full_composite_payload),
        "fnv1a": identity.fnv1a(full_composite_payload),
        "sha256": identity.sha256(full_composite_payload),
    }
    cropped = identity.uniform_identity(BLUE_CODE, CROPPED_DTM_BYTES)
    cropped_payload = bytes([0x55]) * CROPPED_DTM_BYTES
    combined_a_payload = preload_payload + full_composite_payload
    combined_b_payload = preload_payload + cropped_payload
    combined_a = {
        "bytes": len(combined_a_payload),
        "fnv1a": identity.fnv1a(combined_a_payload),
        "sha256": identity.sha256(combined_a_payload),
    }
    combined_b = {
        "bytes": len(combined_b_payload),
        "fnv1a": identity.fnv1a(combined_b_payload),
        "sha256": identity.sha256(combined_b_payload),
    }
    logical_frame = _logical_frame()
    logical_frame_identity = identity.frame_identity(logical_frame)
    _require_identity(
        preload,
        byte_count=CONTROLLER_DTM_BYTES,
        sha256=PRELOAD_DTM_SHA256,
        fnv1a=PRELOAD_DTM_FNV1A,
    )
    _require_identity(
        full_composite,
        byte_count=CONTROLLER_DTM_BYTES,
        sha256=FULL_COMPOSITE_DTM_SHA256,
        fnv1a=FULL_COMPOSITE_DTM_FNV1A,
    )
    _require_identity(
        cropped,
        byte_count=CROPPED_DTM_BYTES,
        sha256=CROPPED_DTM_SHA256,
        fnv1a=CROPPED_DTM_FNV1A,
    )
    _require_identity(
        combined_a,
        byte_count=CONTROLLER_DTM_BYTES * 2,
        sha256=TREATMENT_A_COMBINED_DTM_SHA256,
        fnv1a=TREATMENT_A_COMBINED_DTM_FNV1A,
    )
    _require_identity(
        combined_b,
        byte_count=CONTROLLER_DTM_BYTES + CROPPED_DTM_BYTES,
        sha256=TREATMENT_B_COMBINED_DTM_SHA256,
        fnv1a=TREATMENT_B_COMBINED_DTM_FNV1A,
    )
    if logical_frame_identity != {
        "bytes": FRAME_BYTES,
        "fnv1a": LOGICAL_FRAME_FNV1A,
        "sha256": LOGICAL_FRAME_SHA256,
        "histogram": [0, 0, 0, 0, 0, 38400, 0, 576000],
    }:
        raise ValueError("computed logical frame differs from frozen contract")

    white_frame = bytes([0x11]) * FRAME_BYTES
    actions = [
        _white_action(
            ordinal=1,
            role="FACTORY_OTP_WHITE_HEALTH_ANCHOR",
            branch="FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
            white_frame=white_frame,
        ),
        _runtime_action(
            ordinal=2,
            role="TREATMENT_A_FULLFRAME_COMPOSITE",
            branch="L535_CODE7_PRESTAGE_THEN_FULLFRAME_COMPOSITE_NO_PTLW",
            treatment="A",
            logical_frame=logical_frame,
            preload=preload,
            full_composite=full_composite,
            cropped=cropped,
            combined_a=combined_a,
            combined_b=combined_b,
        ),
        _white_action(
            ordinal=3,
            role="FACTORY_OTP_WHITE_CROSSOVER_RESET",
            branch="FACTORY_OTP_FULL_FRAME_0X11_CROSSOVER_RESET",
            white_frame=white_frame,
        ),
        _runtime_action(
            ordinal=4,
            role="TREATMENT_B_INCLUSIVE_PTLW_CROP",
            branch="L535_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_CODE5_CROP",
            treatment="B",
            logical_frame=logical_frame,
            preload=preload,
            full_composite=full_composite,
            cropped=cropped,
            combined_a=combined_a,
            combined_b=combined_b,
        ),
        _white_action(
            ordinal=5,
            role="FACTORY_OTP_WHITE_RECOVERY",
            branch="FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
            white_frame=white_frame,
        ),
    ]

    profile = deepcopy(v3.build_report()["contract"]["profile"])
    contract = {
        "schema": "mf1750-runtime-lut-ptlw-fullframe-ab-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile": profile,
        "factory_otp_white": {
            "ordinals": [1, 3, 5],
            "frame_fill_byte": "0x11",
            "frame_bytes": FRAME_BYTES,
            "fresh_white_before_each_treatment": True,
        },
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "window": asdict(WINDOW),
            "ptlw_command": "0x83",
            "ptlw_payload_hex": PTLW_PAYLOAD.hex(),
            "ptlw_payload_bytes": len(PTLW_PAYLOAD),
            "ptlw_endpoint": "inclusive",
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_mode": 1,
        },
        "controlled_delta": {
            "independent_variable": "SRAM_ADDRESSING_TRANSPORT",
            "a": {
                "ordinal": 2,
                "ptlw": False,
                "target_dtm": "FULL_CONTROLLER_COMPOSITE",
                "target_dtm_bytes_per_controller": CONTROLLER_DTM_BYTES,
            },
            "b": {
                "ordinal": 4,
                "ptlw": True,
                "target_dtm": "UNIFORM_CROPPED_WINDOW",
                "target_dtm_bytes_per_controller": CROPPED_DTM_BYTES,
            },
            "common_code7_prestage_bytes_per_controller": (
                CONTROLLER_DTM_BYTES
            ),
            "common_code7_prestage_no_refresh": True,
            "same_final_controller_sram": True,
            "same_logical_frame": True,
            "same_runtime_lut_profile": True,
            "same_refresh_sequence": list(COMMON_RUNTIME_REFRESH_SEQUENCE),
            "runtime_treatment_action_stage_cdi": False,
            "runtime_treatment_action_stage_btst2": False,
            "runtime_treatment_repeat_ptlw_after_pon": False,
            "command_0x86": False,
            "extra_dtm_prefix_or_suffix_byte": False,
        },
        "payload_identities": {
            "prestage_code7_per_controller": preload,
            "full_composite_per_controller": full_composite,
            "cropped_code5_per_controller": cropped,
            "treatment_a_combined_stream_per_controller": combined_a,
            "treatment_b_combined_stream_per_controller": combined_b,
            "logical_frame": logical_frame_identity,
        },
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "palette_source": item["palette_source"],
                "dtm_transport": item["dtm_transport"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": True,
        "partial_refresh": True,
        "fullframe_vs_ptlw_ab": True,
        "busy_qualification": {
            "raw_idle_level": 1,
            "ordinal_1_raw_levels_accepted": [0, 1],
            "fresh_low_requires_external_j2_on_confirmation": True,
            "fresh_low_requires_zero_driver_count": True,
            "later_ordinal_raw_levels_accepted": [0, 1],
            "late_low_is_never_treated_as_idle": True,
            "late_low_requires_same_boot_prior_complete": True,
            "late_low_requires_prior_safe_finish_high": True,
            "late_low_requires_ram_only_firmware_eligibility": True,
            "driver_reset_requalifies_idle_before_commands": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "unqualified_busy_zero_accepted": False,
        },
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-ptlw-fullframe-ab-v1-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile_id": PROFILE_ID,
        "contract_id": identity.sha256(identity.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
