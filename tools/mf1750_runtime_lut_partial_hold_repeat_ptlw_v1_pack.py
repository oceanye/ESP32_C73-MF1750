#!/usr/bin/env python3
"""Offline identities for the isolated post-PON repeat-PTLW boundary probe.

This module has no serial, network, relay, reset, flashing, or display-refresh
surface.  The physical campaign starts from an externally established factory
OTP clean-white anchor and contains exactly three cropped-DTM actions.
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


VARIANT_KEY = "L535_ACTIVE_GLOBAL_REPEAT_PTLW_AFTER_PON_EXTERNAL_ANCHOR_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_2026-08-23"
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-REPEAT-PTLW-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1"
NVS_NAMESPACE = "rlph_rptlw_v1"
PROFILE_ID = base.PROFILE_ID

# Code 7 is used only to model the already-observed external clean-white
# anchor in cumulative expected-frame identities.  No action transports it.
EXTERNAL_ANCHOR_MODEL_CODE = 7
WINDOWS = (
    base.Window(48, 64, 160, 120, 3, 3),
    base.Window(304, 240, 160, 120, 5, 5),
    base.Window(48, 416, 160, 120, 6, 6),
)
ROLES = ("PATCH_A", "PATCH_B", "PATCH_C")
BRANCHES = (
    "L535_REPEAT_PTLW_AFTER_PON_CODE3_DARK_A",
    "L535_REPEAT_PTLW_AFTER_PON_CODE5_BLUE_B_HOLD_A",
    "L535_REPEAT_PTLW_AFTER_PON_CODE6_GREEN_C_HOLD_AB",
)
REFRESH_SEQUENCE = (
    "PTLW_CS1_PRE_DTM",
    "PTLW_CS2_PRE_DTM",
    "CROPPED_DTM_CS1",
    "CROPPED_DTM_CS2",
    "CDI_FF_BOTH_PRE_PON_PRESERVED_FROM_V4",
    "PON_BUSY_COMPLETE",
    "PTLW_CS1_REPEAT_POST_PON",
    "PTLW_CS2_REPEAT_POST_PON",
    "CDI_FF_BOTH",
    "BTST2",
    "DRF_BUSY_COMPLETE",
    "POF_BUSY_COMPLETE",
)


def build_report() -> dict[str, Any]:
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

    frame = bytearray(
        [(EXTERNAL_ANCHOR_MODEL_CODE << 4) | EXTERNAL_ANCHOR_MODEL_CODE]
    ) * (base.WIDTH * base.HEIGHT // 2)
    actions: list[dict[str, Any]] = []
    for ordinal, (window, role, branch) in enumerate(
        zip(WINDOWS, ROLES, BRANCHES, strict=True), 1
    ):
        base.set_rect(frame, window)
        byte_count = window.width * window.height // 2
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window),
            "dtm_transport": "UNIFORM_CROPPED_WINDOW",
            "ptlw_writes_per_controller": 2,
            "refresh_sequence": list(REFRESH_SEQUENCE),
            "frame": base.frame_identity(bytes(frame)),
            "cs1_dtm": base.uniform_identity(window.cs1_code, byte_count),
            "cs2_dtm": base.uniform_identity(window.cs2_code, byte_count),
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-repeat-ptlw-descriptor-v1",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_RUNTIME_LUT_REPEAT_PTLW_ACTION_V1|"
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
        "schema": "mf1750-runtime-lut-repeat-ptlw-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile": profile,
        "external_anchor": {
            "required": True,
            "kind": "FACTORY_OTP_CLEAN_WHITE",
            "established_by_firmware": False,
            "model_code_not_transported": EXTERNAL_ANCHOR_MODEL_CODE,
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
        "controlled_delta_from_strict_v4": {
            "name": "REPEAT_IDENTICAL_PTLW_AFTER_PON_BUSY",
            "ptlw_writes_per_controller": 2,
            "pre_pon_cdi_ff_preserved": True,
            "post_pon_cdi_ff_companion_write": (
                "REQUIRED_AFTER_PER_CONTROLLER_PTLW_TO_RESELECT_BOTH_FOR_DRF"
            ),
            "post_pon_order": [
                "PTLW_CS1",
                "PTLW_CS2",
                "CDI_FF_BOTH",
                "BTST2",
                "DRF",
            ],
            "frozen_parameters": [
                "runtime_l535_payloads",
                "spi_1mhz",
                "window_geometry",
                "inclusive_endpoints",
                "pmode_1",
                "cropped_dtm_bytes",
                "codes_3_5_6",
                "pon_drf_pof_busy_gates",
                "btst2_payload",
            ],
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
        "full_screen_refresh_action": False,
        "experimental_code7_action": False,
        "recovery_action": False,
        "camera": False,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
        "supersedes": None,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-repeat-ptlw-offline-identities",
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
