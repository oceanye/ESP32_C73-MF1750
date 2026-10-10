#!/usr/bin/env python3
"""Offline identities for the controller-swapped PTLW Y-endpoint A/B probe.

This module has no device, serial, relay, reset, flashing, or network surface.
It freezes one code-5 ROI and swaps ``ye=y+h-1`` and the adjacent-reference
experimental ``ye=y+h`` comparator between CS1 and CS2 after independent
factory-white anchors.  Every cropped DTM remains exactly 120 rows, so the
PTLW Y-end field is the only treatment delta; ``y+h`` is not claimed safe or
equivalent because it declares 121 rows for a 120-row DTM stream.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
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


VARIANT_KEY = "L535_FACTORY_WHITE_PTLW_YEND_CONTROLLER_SWAP_AB_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PTLW_YEND_AB_V1_2026-08-24"
TEST_ID = "EC5-RUNTIME-LUT-PTLW-YEND-AB-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_YEND_AB_V1"
NVS_NAMESPACE = "rlph_yeab_v1"
NVS_KEY = "cursor_yeab1"
PROFILE_ID = v3.PROFILE_ID
WHITE_CODE = 7
BLUE_CODE = 5


@dataclass(frozen=True)
class EndpointWindow:
    x: int
    y: int
    width: int
    height: int
    cs1_code: int
    cs2_code: int
    cs1_y_end_one_more: bool
    cs2_y_end_one_more: bool


WINDOWS = (
    EndpointWindow(176, 240, 160, 120, 5, 5, False, True),
    EndpointWindow(176, 240, 160, 120, 5, 5, True, False),
)

PARTIAL_ROLES = ("PATCH_A", "PATCH_B")
PARTIAL_BRANCHES = (
    "CODE5_BLUE_CS1_YH_MINUS1_CS2_YH_SWAP_A",
    "CODE5_BLUE_CS1_YH_CS2_YH_MINUS1_SWAP_B",
)


def _base_window(window: EndpointWindow) -> identity.Window:
    return identity.Window(
        window.x,
        window.y,
        window.width,
        window.height,
        window.cs1_code,
        window.cs2_code,
    )


def _partial_action(
    *,
    ordinal: int,
    role: str,
    branch: str,
    window: EndpointWindow,
    frame: bytearray,
) -> dict[str, Any]:
    wire_window = _base_window(window)
    identity.set_rect(frame, wire_window)
    dtm_bytes = window.width * window.height // 2
    item: dict[str, Any] = {
        "ordinal": ordinal,
        "role": role,
        "branch": branch,
        "window": asdict(window),
        "palette_source": "L535_RUNTIME",
        "dtm_transport": "UNIFORM_CROPPED_WINDOW_120_ROWS",
        "dtm_rows_per_controller": window.height,
        "ptlw_writes_per_controller": 2,
        "ptlw_endpoint_treatment": {
            "cs1": "ye=y+h" if window.cs1_y_end_one_more else "ye=y+h-1",
            "cs2": "ye=y+h" if window.cs2_y_end_one_more else "ye=y+h-1",
        },
        "refresh_sequence": [
            "PTLW_CS1_PRE_DTM",
            "PTLW_CS2_PRE_DTM",
            "CROPPED_DTM_120_ROWS_CS1",
            "CROPPED_DTM_120_ROWS_CS2",
            "CDI_FF_BOTH_PRE_PON",
            "PON_BUSY_COMPLETE_60S_GATE",
            "PTLW_CS1_REPEAT_POST_PON",
            "PTLW_CS2_REPEAT_POST_PON",
            "CDI_FF_BOTH_POST_PON",
            "BTST2",
            "DRF_BUSY_COMPLETE_60S_GATE",
            "POF_BUSY_COMPLETE_60S_GATE",
        ],
        "frame": identity.frame_identity(bytes(frame)),
        "cs1_dtm": identity.uniform_identity(window.cs1_code, dtm_bytes),
        "cs2_dtm": identity.uniform_identity(window.cs2_code, dtm_bytes),
    }
    descriptor = {
        "schema": "mf1750-runtime-lut-ptlw-yend-ab-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        **item,
    }
    item["descriptor_id"] = identity.sha256(identity.canonical(descriptor))
    item["action_id"] = identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_YEND_AB_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
        ).encode("ascii")
    )
    return item


def _white_action(
    *, ordinal: int, role: str, branch: str, frame: bytes
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ordinal": ordinal,
        "role": role,
        "branch": branch,
        "window": None,
        "palette_source": "FACTORY_OTP",
        "dtm_transport": "FACTORY_OTP_PACKED_FULL_FRAME_0X11",
        "dtm_rows_per_controller": 600,
        "ptlw_writes_per_controller": 0,
        "ptlw_endpoint_treatment": None,
        "refresh_sequence": [
            "FACTORY_OTP_PREPARE_CASCADE",
            "FULL_FRAME_0X11_DTM_CS1",
            "FULL_FRAME_0X11_DTM_CS2",
            "PON_BUSY_COMPLETE_60S_GATE",
            "BTST2",
            "DRF_BUSY_COMPLETE_60S_GATE",
            "POF_BUSY_COMPLETE_60S_GATE",
        ],
        "frame": identity.frame_identity(frame),
        "cs1_dtm": identity.uniform_identity(1, 512 * 600 // 2),
        "cs2_dtm": identity.uniform_identity(1, 512 * 600 // 2),
    }
    descriptor = {
        "schema": "mf1750-runtime-lut-ptlw-yend-ab-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        **item,
    }
    item["descriptor_id"] = identity.sha256(identity.canonical(descriptor))
    item["action_id"] = identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_YEND_AB_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
        ).encode("ascii")
    )
    return item


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        identity.validate_window(_base_window(window))
        declared_cs1_rows = window.height + int(window.cs1_y_end_one_more)
        declared_cs2_rows = window.height + int(window.cs2_y_end_one_more)
        if declared_cs1_rows not in (120, 121) or declared_cs2_rows not in (120, 121):
            raise ValueError("unexpected PTLW declared row count")
    if len({(w.x, w.y, w.width, w.height) for w in WINDOWS}) != 1:
        raise ValueError("endpoint A/B must use the exact same ROI")

    white = bytes([0x11]) * (1024 * 600 // 2)
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    actions = [
        _white_action(
            ordinal=1,
            role="FACTORY_OTP_WHITE_HEALTH_ANCHOR",
            branch="FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
            frame=white,
        )
    ]
    actions.append(
        _partial_action(
            ordinal=2,
            role=PARTIAL_ROLES[0],
            branch=PARTIAL_BRANCHES[0],
            window=WINDOWS[0],
            frame=frame,
        )
    )
    actions.append(
        _white_action(
            ordinal=3,
            role="FACTORY_OTP_WHITE_CROSSOVER_RESET",
            branch="FACTORY_OTP_FULL_FRAME_0X11_CROSSOVER_RESET",
            frame=white,
        )
    )
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    actions.append(
        _partial_action(
            ordinal=4,
            role=PARTIAL_ROLES[1],
            branch=PARTIAL_BRANCHES[1],
            window=WINDOWS[1],
            frame=frame,
        )
    )
    actions.append(
        _white_action(
            ordinal=5,
            role="FACTORY_OTP_WHITE_RECOVERY",
            branch="FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
            frame=white,
        )
    )

    profile = deepcopy(v3.build_report()["contract"]["profile"])
    contract = {
        "schema": "mf1750-runtime-lut-ptlw-yend-ab-contract-v1",
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
            "frame_bytes": len(white),
            "driver_entry": "epdDisplayCompiledFactoryOtpWhiteRecovery",
        },
        "geometry": {
            "width": 1024,
            "height": 600,
            "controller_width": 512,
            "ptlw_command": "0x83",
            "ptlw_mode": 1,
            "dtm_rows_fixed": 120,
            "dtm_bytes_fixed_per_controller": 9600,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "controlled_delta": {
            "independent_variable": "PTLW_Y_END_ENDPOINT_ONLY",
            "a": {"ordinal": 2, "cs1": "ye=y+h-1", "cs2": "ye=y+h"},
            "b": {"ordinal": 4, "cs1": "ye=y+h", "cs2": "ye=y+h-1"},
            "fresh_white_before_each_treatment": True,
            "crossover_reset_ordinal": 3,
            "code_both_controllers": BLUE_CODE,
            "same_controller_local_x": 176,
            "same_width": 160,
            "same_height": 120,
            "same_dtm_bytes": 9600,
            "repeat_identical_ptlw_after_pon_busy": True,
            "pre_pon_cdi_ff_preserved": True,
        },
        "evidence_boundary": {
            "exact_spd1657a_local_manual_contract": "ye=y+h-1",
            "adjacent_gx_reference_workaround": "ye=y+h",
            "sources_conflict": True,
            "y_plus_h_status": "ADJACENT_REFERENCE_EXPERIMENTAL_COMPARATOR",
            "predicted_fix": False,
            "physical_bottom_equals_logical_y_end_proven": False,
            "observation_must_record": [
                "FPC_DIRECTION",
                "PHYSICAL_ANOMALY_EDGE",
                "MAPPED_LOGICAL_EDGE_IF_KNOWN",
                "CS1_VS_CS2",
            ],
            "acceptance_rule": (
                "only conclude from whether the physical edge anomaly follows "
                "the endpoint treatment after the controller swap"
            ),
            "declared_vs_stream_mismatch": (
                "the y+h comparator declares 121 PTLW rows while streaming "
                "the same 120 DTM rows; this is experimental and is not a "
                "safe-equivalence claim"
            ),
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
        "endpoint_controller_swap": True,
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required_for_every_ordinal": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-ptlw-yend-ab-v1-offline-identities",
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
        "nvs_key": NVS_KEY,
        "contract_id": identity.sha256(identity.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
