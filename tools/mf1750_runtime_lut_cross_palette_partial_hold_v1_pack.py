#!/usr/bin/env python3
"""Offline identities for the five-action cross-palette local-HOLD probe.

The factory-OTP white actions bracket three disjoint cropped updates.  The
partial actions deliberately switch global-header profile A -> B -> A while
retaining earlier regions, so this contract tests palette switching and local
HOLD together without spatial dithering or a mid-refresh power cut.
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

from tools import mf1750_runtime_lut_cross_palette_v1_pack as cross  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402


VARIANT_KEY = "L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_BUSY_QUALIFIED_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_2026-08-24"
TEST_ID = "EC5-RUNTIME-LUT-CROSS-PALETTE-PARTIAL-HOLD-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1"
NVS_NAMESPACE = "rlxph_v1"
NVS_KEY = "cursor_cxph1"
PROFILE_ACTIVE = cross.PROFILE_ACTIVE
PROFILE_COMMENTED = cross.PROFILE_COMMENTED
PROFILE_ID = (
    "ACTIVE_CODE5_TO_COMMENTED_CODE6_TO_ACTIVE_CODE3__"
    "CS1_ACTIVE535__CS2_COMMENTED535"
)
CONTRACT_ID = base.sha256(
    b"contract:cross-palette-partial-hold-v1:2026-08-24"
)
FACTORY_WHITE_CODE = 1
ANCHOR_MODEL_CODE = 7
WINDOWS = (
    base.Window(48, 64, 160, 120, 5, 5),
    base.Window(304, 240, 160, 120, 6, 6),
    base.Window(48, 416, 160, 120, 3, 3),
)
ROLES = (
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
    "PATCH_A_ACTIVE_CODE5",
    "PATCH_B_COMMENTED_CODE6_HOLD_A",
    "PATCH_C_ACTIVE_CODE3_HOLD_AB",
    "FACTORY_OTP_WHITE_RECOVERY",
)
GLOBAL_HEADERS: tuple[str | None, ...] = (
    None,
    "active",
    "commented",
    "active",
    None,
)
BRANCHES = (
    "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
    "L535_ACTIVE_GLOBAL_REPEAT_PTLW_CODE5_ROI_A",
    "L535_COMMENTED_GLOBAL_REPEAT_PTLW_CODE6_ROI_B_HOLD_A",
    "L535_ACTIVE_GLOBAL_REPEAT_PTLW_CODE3_ROI_C_HOLD_AB",
    "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
)
_IDENTITY_SUFFIXES = (
    "factory-white-anchor",
    "patch-a-active-code5",
    "patch-b-commented-code6",
    "patch-c-active-code3",
    "factory-white-recovery",
)
DESCRIPTOR_IDS = tuple(
    base.sha256(f"descriptor:{suffix}".encode("utf-8"))
    for suffix in _IDENTITY_SUFFIXES
)
ACTION_IDS = tuple(
    base.sha256(f"action:{suffix}".encode("utf-8"))
    for suffix in _IDENTITY_SUFFIXES
)
PARTIAL_REFRESH_SEQUENCE = (
    "LOAD_SELECTED_GLOBAL_HEADER_AND_CONTROLLER_LUTS",
    "PTLW_CS1_PRE_DTM",
    "PTLW_CS2_PRE_DTM",
    "CROPPED_DTM_CS1",
    "CROPPED_DTM_CS2",
    "CDI_FF_BOTH_PRE_PON",
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
            if not (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            ):
                raise ValueError("cross-palette HOLD windows must be disjoint")


def build_report() -> dict[str, Any]:
    """Build immutable payload and action identities without device access."""

    _assert_disjoint_windows()
    white_frame = bytes([0x11]) * (base.WIDTH * base.HEIGHT // 2)
    modeled_frame = bytearray(
        [(ANCHOR_MODEL_CODE << 4) | ANCHOR_MODEL_CODE]
    ) * (base.WIDTH * base.HEIGHT // 2)
    actions: list[dict[str, Any]] = []

    for ordinal, (role, branch, header) in enumerate(
        zip(ROLES, BRANCHES, GLOBAL_HEADERS, strict=True), 1
    ):
        is_white = ordinal in (1, 5)
        if is_white:
            frame_identity = base.frame_identity(white_frame)
            byte_count = base.CONTROLLER_WIDTH * base.HEIGHT // 2
            cs1_identity = base.uniform_identity(FACTORY_WHITE_CODE, byte_count)
            cs2_identity = base.uniform_identity(FACTORY_WHITE_CODE, byte_count)
            window = None
            palette_source = "FACTORY_OTP"
            profile_id = None
            dtm_transport = "FACTORY_OTP_PACKED_FULL_FRAME_0X11"
            refresh_sequence = list(WHITE_REFRESH_SEQUENCE)
        else:
            window = WINDOWS[ordinal - 2]
            base.set_rect(modeled_frame, window)
            byte_count = window.width * window.height // 2
            frame_identity = base.frame_identity(bytes(modeled_frame))
            cs1_identity = base.uniform_identity(window.cs1_code, byte_count)
            cs2_identity = base.uniform_identity(window.cs2_code, byte_count)
            palette_source = "L535_RUNTIME"
            profile_id = cross.profile(header)["id"]
            dtm_transport = "UNIFORM_CROPPED_WINDOW"
            refresh_sequence = list(PARTIAL_REFRESH_SEQUENCE)

        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "palette_source": palette_source,
            "global_header": header,
            "profile_id": profile_id,
            "dtm_transport": dtm_transport,
            "ptlw_writes_per_controller": 0 if is_white else 2,
            "refresh_sequence": refresh_sequence,
            "frame": frame_identity,
            "cs1_dtm": cs1_identity,
            "cs2_dtm": cs2_identity,
        }
        # These IDs are bound to the independent firmware identity fixture.
        # Payload identities above remain recomputed here, while the frozen
        # descriptor/action IDs make accidental host/firmware drift fail shut.
        item["descriptor_id"] = DESCRIPTOR_IDS[ordinal - 1]
        item["action_id"] = ACTION_IDS[ordinal - 1]
        actions.append(item)

    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    contract = {
        "schema": "mf1750-runtime-lut-cross-palette-partial-hold-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profiles": profiles,
        "profile_sequence": [None, "active", "commented", "active", None],
        "factory_otp_white": {
            "ordinals": [1, 5],
            "frame_fill_byte": "0x11",
            "frame_bytes": len(white_frame),
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
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "palette_source": item["palette_source"],
                "global_header": item["global_header"],
                "profile_id": item["profile_id"],
                "dtm_transport": item["dtm_transport"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required_for_every_ordinal": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "runtime_lut": True,
        "factory_otp": True,
        "partial_refresh": True,
        "cross_palette_hold_probe": True,
        "same_palette_hold_probe": False,
        "full_screen_factory_white_actions": True,
        "experimental_code7_action": False,
        "runtime_transport_codes": [5, 6, 3],
        "spatial_dither": False,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-cross-palette-partial-hold-v1-offline-identities",
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
        "contract_id": CONTRACT_ID,
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
