#!/usr/bin/env python3
"""Immutable V2 identities for L535 + PTLW, correcting white to code 1."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as v1  # noqa: E402


WHITE_CODE = 1
VARIANT_KEY = "L535_ACTIVE_GLOBAL_DISJOINT_Y_INCLUSIVE_CODE1_WHITE"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V2_2026-08-23"
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V2"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V2"
NVS_NAMESPACE = "rlph_l535a_v2"
PROFILE_ID = v1.PROFILE_ID
WINDOWS = v1.WINDOWS
ROLES = v1.ROLES
BRANCHES = (
    "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE1",
    v1.BRANCHES[1],
    v1.BRANCHES[2],
    v1.BRANCHES[3],
    "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE1_RECOVERY",
)


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        v1.validate_window(window)
    frame = bytearray([0x11]) * (v1.WIDTH * v1.HEIGHT // 2)
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch) in enumerate(zip(ROLES, BRANCHES), 1):
        if ordinal in (1, 5):
            frame = bytearray([0x11]) * (v1.WIDTH * v1.HEIGHT // 2)
            window = None
            byte_count = v1.CONTROLLER_WIDTH * v1.HEIGHT // 2
            cs1_code = WHITE_CODE
            cs2_code = WHITE_CODE
        else:
            window = WINDOWS[ordinal - 2]
            v1.set_rect(frame, window)
            byte_count = window.width * window.height // 2
            cs1_code = window.cs1_code
            cs2_code = window.cs2_code
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "frame": v1.frame_identity(bytes(frame)),
            "cs1_dtm": v1.uniform_identity(cs1_code, byte_count),
            "cs2_dtm": v1.uniform_identity(cs2_code, byte_count),
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-partial-hold-descriptor-v2",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = v1.sha256(v1.canonical(descriptor))
        item["action_id"] = v1.sha256(
            (
                "MF1750_RUNTIME_LUT_PARTIAL_HOLD_ACTION_V2|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        actions.append(item)

    profile = {
        "id": PROFILE_ID,
        "global_header": "active",
        "cs1_r20_prefix_bytes": 535,
        "cs1_r20_prefix_sha256": v1.ACTIVE_R20_PREFIX_SHA256,
        "cs2_r20_prefix_bytes": 535,
        "cs2_r20_prefix_sha256": v1.COMMENTED_R20_PREFIX_SHA256,
        "r21_bytes": 704,
        "r21_sha256": v1.R21_SHA256,
    }
    contract = {
        "schema": "mf1750-runtime-lut-partial-hold-contract-v2",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile": profile,
        "geometry": {
            "width": v1.WIDTH,
            "height": v1.HEIGHT,
            "controller_width": v1.CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
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
        "partial_refresh": True,
        "cross_palette": False,
        "camera": False,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
        "supersedes": {
            "build_tag": v1.BUILD_TAG,
            "reason": "V1 code3 baseline observed full black",
        },
    }
    return {
        "schema_version": 2,
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
        "contract_id": v1.sha256(v1.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
