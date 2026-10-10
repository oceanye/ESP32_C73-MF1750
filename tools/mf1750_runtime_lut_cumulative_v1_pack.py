#!/usr/bin/env python3
"""Immutable identities for the L535 cumulative full-frame fallback.

This is an offline-only generator.  Every visible action restreams the whole
1024x600 cumulative frame; it never emits PTLW and therefore does not claim
local refresh or HOLD.  It exists to separate palette stability from window
transport behavior during the same evening session.
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


WHITE_CODE = 7
VARIANT_KEY = "L535_ACTIVE_GLOBAL_CUMULATIVE_PACKED_FRAME_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_CUMULATIVE_L535_ACTIVE_V1_2026-08-23"
TEST_ID = "EC5-RUNTIME-LUT-CUMULATIVE-L535-ACTIVE-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_CUMULATIVE_L535_ACTIVE_V1"
NVS_NAMESPACE = "rlcum535_v1"
PROFILE_ID = base.PROFILE_ID
WINDOWS = (
    base.Window(48, 64, 160, 120, 3, 3),
    base.Window(304, 240, 160, 120, 5, 5),
    base.Window(48, 416, 160, 120, 6, 6),
)
ROLES = base.ROLES
BRANCHES = (
    "L535_ACTIVE_GLOBAL_CUMULATIVE_CODE7_WHITE",
    "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A",
    "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A_CODE5_B",
    "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A_CODE5_B_CODE6_C",
    "L535_ACTIVE_GLOBAL_CUMULATIVE_CODE7_WHITE_RECOVERY",
)


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != base.WIDTH * base.HEIGHT // 2:
        raise ValueError("invalid cumulative controller stream request")
    row_bytes = base.WIDTH // 2
    half_row_bytes = base.CONTROLLER_WIDTH // 2
    offset = controller * half_row_bytes
    return b"".join(
        frame[y * row_bytes + offset : y * row_bytes + offset + half_row_bytes]
        for y in range(base.HEIGHT)
    )


def payload_identity(data: bytes) -> dict[str, Any]:
    return {
        "bytes": len(data),
        "fnv1a": base.fnv1a(data),
        "sha256": base.sha256(data),
    }


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        base.validate_window(window)
    frame = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch) in enumerate(zip(ROLES, BRANCHES), 1):
        if ordinal in (1, 5):
            frame = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
            window = None
        else:
            window = WINDOWS[ordinal - 2]
            base.set_rect(frame, window)
        frozen_frame = bytes(frame)
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "dtm_transport": "PACKED_FULL_FRAME_PER_CONTROLLER",
            "frame": base.frame_identity(frozen_frame),
            "cs1_dtm": payload_identity(controller_stream(frozen_frame, 0)),
            "cs2_dtm": payload_identity(controller_stream(frozen_frame, 1)),
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-cumulative-descriptor-v1",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_RUNTIME_LUT_CUMULATIVE_ACTION_V1|"
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
        "schema": "mf1750-runtime-lut-cumulative-contract-v1",
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
            "ptlw_command_issued": False,
            "windows_are_visual_rois_only": True,
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
        },
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": False,
        "partial_refresh": False,
        "full_frame_cumulative_redraw": True,
        "cross_palette": False,
        "camera": False,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-cumulative-offline-identities",
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
