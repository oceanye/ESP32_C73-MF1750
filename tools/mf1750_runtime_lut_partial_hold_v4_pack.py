#!/usr/bin/env python3
"""Immutable V4 identities for photo-mapped L535/PTLW packed-white control."""

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


WHITE_CODE = 7
VARIANT_KEY = "L535_ACTIVE_GLOBAL_Y_INCLUSIVE_CODE7_PACKED_BASELINE_V4"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V4_2026-08-23"
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V4"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V4"
NVS_NAMESPACE = "rlph_l535a_v4"
PROFILE_ID = base.PROFILE_ID
WINDOWS = (
    base.Window(48, 64, 160, 120, 3, 3),
    base.Window(304, 240, 160, 120, 5, 5),
    base.Window(48, 416, 160, 120, 6, 6),
)
ROLES = base.ROLES
BRANCHES = (
    "L535_ACTIVE_GLOBAL_PACKED_FRAME_CODE7_WHITE",
    "L535_ACTIVE_GLOBAL_PTLW_CODE3_DARK_A",
    "L535_ACTIVE_GLOBAL_PTLW_CODE5_BLUE_B_HOLD_A",
    "L535_ACTIVE_GLOBAL_PTLW_CODE6_GREEN_C_HOLD_AB",
    "L535_ACTIVE_GLOBAL_PACKED_FRAME_CODE7_WHITE_RECOVERY",
)


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        base.validate_window(window)
    frame = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch) in enumerate(zip(ROLES, BRANCHES), 1):
        full_frame = ordinal in (1, 5)
        if full_frame:
            frame = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
            window = None
            byte_count = base.CONTROLLER_WIDTH * base.HEIGHT // 2
            cs1_code = WHITE_CODE
            cs2_code = WHITE_CODE
            dtm_transport = "PACKED_FRAME_CONTROLLER"
        else:
            window = WINDOWS[ordinal - 2]
            base.set_rect(frame, window)
            byte_count = window.width * window.height // 2
            cs1_code = window.cs1_code
            cs2_code = window.cs2_code
            dtm_transport = "UNIFORM_CROPPED_WINDOW"
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "dtm_transport": dtm_transport,
            "frame": base.frame_identity(bytes(frame)),
            "cs1_dtm": base.uniform_identity(cs1_code, byte_count),
            "cs2_dtm": base.uniform_identity(cs2_code, byte_count),
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-partial-hold-descriptor-v4",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_RUNTIME_LUT_PARTIAL_HOLD_ACTION_V4|"
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
        "schema": "mf1750-runtime-lut-partial-hold-contract-v4",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile": profile,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "photo_mapped_code_roles": {
            "evidence_photo_sha256": (
                "679e47694956c3ead0146b6115ac4e21ffc56d0315172bd508fdf67a94c517c2"
            ),
            "shared_white": 7,
            "shared_blue": 5,
            "shared_green": 6,
            "near_dark_not_proven_same": 3,
            "controller_dependent": [0, 1, 2, 4],
        },
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "dtm_transport": item["dtm_transport"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": False,
        "partial_refresh": True,
        "cross_palette": False,
        "camera": False,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
        "supersedes": {
            "build_tag": (
                "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V3_2026-08-23"
            ),
            "reason": (
                "V3 uniform full-controller DTM produced a split field while the "
                "controller-code atlas independently mapped code7 to white on both "
                "controllers; V4 uses the atlas-proven packed-frame transport for "
                "both full-white actions"
            ),
        },
    }
    return {
        "schema_version": 4,
        "kind": "mf1750-runtime-lut-partial-hold-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flushed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
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
