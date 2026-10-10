#!/usr/bin/env python3
"""Offline identities for the five-action repeat-PTLW V2 campaign.

The two full-screen white actions use the validated factory-OTP 0x11 frame
path.  Only the three cropped actions load L535 and transport runtime codes
3, 5, and 6; runtime code 7 is never an executable action.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402


VARIANT_KEY = "L535_FACTORY_OTP_WHITE_REPEAT_PTLW_V2"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_2026-08-23"
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-REPEAT-PTLW-V2"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2"
NVS_NAMESPACE = "rlph_rptlw_v2"
NVS_KEY = "cursor_rptv2"
PROFILE_ID = base.PROFILE_ID
FACTORY_WHITE_CODE = 1
ANCHOR_MODEL_CODE = 7
WINDOWS = (
    base.Window(48, 64, 160, 120, 3, 3),
    base.Window(304, 240, 160, 120, 5, 5),
    base.Window(48, 416, 160, 120, 6, 6),
)
ROLES = (
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
    "PATCH_A",
    "PATCH_B",
    "PATCH_C",
    "FACTORY_OTP_WHITE_RECOVERY",
)
BRANCHES = (
    "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
    "L535_REPEAT_PTLW_AFTER_PON_CODE3_DARK_A",
    "L535_REPEAT_PTLW_AFTER_PON_CODE5_BLUE_B_HOLD_A",
    "L535_REPEAT_PTLW_AFTER_PON_CODE6_GREEN_C_HOLD_AB",
    "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
)
PARTIAL_REFRESH_SEQUENCE = (
    "PTLW_CS1_PRE_DTM",
    "PTLW_CS2_PRE_DTM",
    "CROPPED_DTM_CS1",
    "CROPPED_DTM_CS2",
    "CDI_FF_BOTH_PRE_PON_PRESERVED_FROM_V4",
    "PON_BUSY_COMPLETE_60S_GATE",
    "PTLW_CS1_REPEAT_POST_PON",
    "PTLW_CS2_REPEAT_POST_PON",
    "CDI_FF_BOTH",
    "BTST2",
    "DRF_BUSY_COMPLETE_60S_GATE",
    "POF_BUSY_COMPLETE_60S_GATE",
)
WHITE_REFRESH_SEQUENCE = (
    "FACTORY_OTP_PREPARE_CASCADE",
    "FULL_FRAME_0X11_DTM_CS1",
    "FULL_FRAME_0X11_DTM_CS2",
    "PON_BUSY_COMPLETE_60S_GATE",
    "BTST2",
    "DRF_BUSY_COMPLETE_60S_GATE",
    "POF_BUSY_COMPLETE_60S_GATE",
)


def _assert_disjoint_windows() -> None:
    for window in WINDOWS:
        base.validate_window(window)
    for left_index, left in enumerate(WINDOWS):
        for right in WINDOWS[left_index + 1 :]:
            disjoint = (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            )
            if not disjoint:
                raise ValueError("PTLW windows must be disjoint")


def build_report() -> dict[str, Any]:
    _assert_disjoint_windows()
    white_frame = bytes([0x11]) * (base.WIDTH * base.HEIGHT // 2)
    modeled_frame = bytearray(
        [(ANCHOR_MODEL_CODE << 4) | ANCHOR_MODEL_CODE]
    ) * (base.WIDTH * base.HEIGHT // 2)
    actions: list[dict[str, Any]] = []

    for ordinal, (role, branch) in enumerate(zip(ROLES, BRANCHES, strict=True), 1):
        is_white = ordinal in (1, 5)
        if is_white:
            frame_identity = base.frame_identity(white_frame)
            byte_count = base.CONTROLLER_WIDTH * base.HEIGHT // 2
            cs1_identity = base.uniform_identity(FACTORY_WHITE_CODE, byte_count)
            cs2_identity = base.uniform_identity(FACTORY_WHITE_CODE, byte_count)
            window = None
            dtm_transport = "FACTORY_OTP_PACKED_FULL_FRAME_0X11"
            refresh_sequence = list(WHITE_REFRESH_SEQUENCE)
            palette_source = "FACTORY_OTP"
        else:
            window = WINDOWS[ordinal - 2]
            base.set_rect(modeled_frame, window)
            byte_count = window.width * window.height // 2
            frame_identity = base.frame_identity(bytes(modeled_frame))
            cs1_identity = base.uniform_identity(window.cs1_code, byte_count)
            cs2_identity = base.uniform_identity(window.cs2_code, byte_count)
            dtm_transport = "UNIFORM_CROPPED_WINDOW"
            refresh_sequence = list(PARTIAL_REFRESH_SEQUENCE)
            palette_source = "L535_RUNTIME"

        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "palette_source": palette_source,
            "dtm_transport": dtm_transport,
            "ptlw_writes_per_controller": 0 if is_white else 2,
            "refresh_sequence": refresh_sequence,
            "frame": frame_identity,
            "cs1_dtm": cs1_identity,
            "cs2_dtm": cs2_identity,
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-repeat-ptlw-descriptor-v2",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_RUNTIME_LUT_REPEAT_PTLW_ACTION_V2|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        actions.append(item)

    profile = {
        "id": PROFILE_ID,
        "global_header": "active",
        "cs1_r20_prefix_bytes": 535,
        "cs1_r20_prefix_sha256": base.ACTIVE_R20_PREFIX_SHA256,
        "cs2_r20_prefix_bytes": 535,
        "cs2_r20_prefix_sha256": base.COMMENTED_R20_PREFIX_SHA256,
        "r21_bytes": 704,
        "r21_sha256": base.R21_SHA256,
    }
    contract = {
        "schema": "mf1750-runtime-lut-repeat-ptlw-contract-v2",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile": profile,
        "factory_otp_white": {
            "ordinals": [1, 5],
            "frame_fill_byte": "0x11",
            "frame_bytes": len(white_frame),
            "driver_entry": "epdDisplayCompiledFactoryOtpWhiteRecovery",
            "health_anchor_in_firmware": True,
            "final_recovery_in_firmware": True,
        },
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "controlled_repeat_delta": {
            "name": "REPEAT_IDENTICAL_PTLW_AFTER_PON_BUSY",
            "ptlw_writes_per_controller": 2,
            "pre_pon_cdi_ff_preserved": True,
            "post_pon_order": [
                "PTLW_CS1",
                "PTLW_CS2",
                "CDI_FF_BOTH",
                "BTST2",
                "DRF",
            ],
            "pon_timeout_ms": 60_000,
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
        "full_screen_factory_white_actions": True,
        "experimental_code7_action": False,
        "runtime_transport_codes": [3, 5, 6],
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
        "supersedes": None,
    }
    return {
        "schema_version": 2,
        "kind": "mf1750-runtime-lut-repeat-ptlw-v2-offline-identities",
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
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
