#!/usr/bin/env python3
"""Build immutable offline identities for the isolated warm PTLW session."""

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


VARIANT_KEY = "L535_ACTIVE_STRICT_PTLW_WARM_SESSION_V1"
BUILD_TAG = "MF1750_EC5_PARTIAL_HOLD_WARM_SESSION_V1_2026-08-23"
TEST_ID = "EC5-PARTIAL-HOLD-WARM-SESSION-V1"
CAMPAIGN_ID = "EC5_PARTIAL_HOLD_WARM_SESSION_V1"
NVS_NAMESPACE = "phwarm_v1"
PROFILE_ID = base.PROFILE_ID
WHITE_CODE = 7
WINDOWS = (
    base.Window(48, 64, 160, 120, 3, 3),
    base.Window(304, 240, 160, 120, 5, 5),
    base.Window(48, 416, 160, 120, 6, 6),
)
ROLES = (
    "WARM_WHITE_BASELINE",
    "WARM_RED_A",
    "WARM_BLUE_B_HOLD_A",
    "WARM_GREEN_C_HOLD_AB",
    "WARM_WHITE_RECOVERY_SAFE_POF",
)
BRANCHES = (
    "PREPARE_ONCE_L535_PACKED_CODE7_WHITE_PON_DRF_HOLD_POWER",
    "NO_RESET_NO_PREPARE_PTLW_CODE3_RED_A_DRF_ONLY_HOLD_POWER",
    "NO_RESET_NO_PREPARE_PTLW_CODE5_BLUE_B_DRF_ONLY_HOLD_POWER",
    "NO_RESET_NO_PREPARE_PTLW_CODE6_GREEN_C_DRF_ONLY_HOLD_POWER",
    "NO_RESET_NO_PREPARE_FULL_PTLW_PACKED_CODE7_WHITE_DRF_SAFE_POF",
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
            "session_phase": (
                "OPEN" if ordinal == 1 else "CLOSE" if ordinal == 5 else "WARM"
            ),
        }
        descriptor = {
            "schema": "mf1750-partial-hold-warm-session-descriptor-v1",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_PARTIAL_HOLD_WARM_SESSION_ACTION_V1|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        actions.append(item)

    contract = {
        "schema": "mf1750-partial-hold-warm-session-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile_id": PROFILE_ID,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_payload_bytes": 9,
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "session": {
            "prepare_count": 1,
            "hard_reset_count": 1,
            "runtime_lut_upload_count": 1,
            "pon_count": 1,
            "patch_drf_without_pon": 3,
            "final_white_full_window_ptlw": True,
            "pof_count_on_success": 1,
            "physical_power_control": False,
            "same_boot_required": True,
            "boot_resume": False,
            "unexpected_reboot_requires_physical_cut_before_recovery": True,
            "max_warm_gap_ms": 120000,
        },
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "dtm_transport": item["dtm_transport"],
                "session_phase": item["session_phase"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": False,
        "partial_refresh": True,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-partial-hold-warm-session-offline-identities",
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
