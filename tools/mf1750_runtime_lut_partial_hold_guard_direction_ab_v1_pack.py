#!/usr/bin/env python3
"""Offline identities for the explicit 8-row guard-direction crossover.

No hardware, network, serial, relay, reset, flashing, or live authorization
surface is present.  Both partial arms declare and stream exactly 128 rows:
one arm protects logical +Y with eight code-7 rows, and the other protects
logical -Y.  The treatments swap controllers after a factory-OTP white reset.
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


VARIANT_KEY = "L535_FACTORY_WHITE_PTLW_GUARD_DIRECTION_CONTROLLER_SWAP_AB_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_V1_2026-08-24"
TEST_ID = "EC5-RUNTIME-LUT-PTLW-GUARD-DIRECTION-AB-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_V1"
NVS_NAMESPACE = "rlph_gdab_v1"
NVS_KEY = "cursor_gdab1"
PROFILE_ID = v3.PROFILE_ID
WHITE_CODE = 7
BLUE_CODE = 5
ROW_BYTES = 160 // 2
TARGET_ROWS = 120
GUARD_ROWS = 8
STREAM_ROWS = TARGET_ROWS + GUARD_ROWS
STREAM_BYTES = STREAM_ROWS * ROW_BYTES


@dataclass(frozen=True)
class GuardWindow:
    x: int
    target_y: int
    width: int
    target_height: int
    cs1_code: int
    cs2_code: int
    cs1_guard: str
    cs2_guard: str


WINDOWS = (
    GuardWindow(176, 240, 160, 120, 5, 5, "BOTTOM_8", "TOP_8"),
    GuardWindow(176, 240, 160, 120, 5, 5, "TOP_8", "BOTTOM_8"),
)

PARTIAL_ROLES = ("PATCH_A", "PATCH_B")
PARTIAL_BRANCHES = (
    "CODE5_BLUE_CS1_BOTTOM8_CS2_TOP8_SWAP_A",
    "CODE5_BLUE_CS1_TOP8_CS2_BOTTOM8_SWAP_B",
)


def _base_window(window: GuardWindow) -> identity.Window:
    return identity.Window(
        window.x,
        window.target_y,
        window.width,
        window.target_height,
        window.cs1_code,
        window.cs2_code,
    )


def _guard_bytes(code: int, guard: str) -> bytes:
    if code not in range(8) or guard not in {"TOP_8", "BOTTOM_8"}:
        raise ValueError("invalid fixed guard stream")
    target = bytes([(code << 4) | code]) * (TARGET_ROWS * ROW_BYTES)
    white = bytes([(WHITE_CODE << 4) | WHITE_CODE]) * (GUARD_ROWS * ROW_BYTES)
    return white + target if guard == "TOP_8" else target + white


def _stream_identity(code: int, guard: str) -> dict[str, Any]:
    data = _guard_bytes(code, guard)
    return {
        "bytes": len(data),
        "sha256": identity.sha256(data),
        "fnv1a": identity.fnv1a(data),
        "target_rows": TARGET_ROWS,
        "guard_rows": GUARD_ROWS,
        "guard_position": guard,
    }


def _ptlw(guard: str) -> dict[str, Any]:
    if guard == "BOTTOM_8":
        y_start, y_end = 240, 367
    elif guard == "TOP_8":
        y_start, y_end = 232, 359
    else:
        raise ValueError("invalid guard position")
    payload = bytes(
        [
            0x00,
            0xB0,
            0x01,
            0x4F,
            y_start >> 8,
            y_start & 0xFF,
            y_end >> 8,
            y_end & 0xFF,
            0x01,
        ]
    )
    return {
        "x_start": 176,
        "x_end": 335,
        "y_start": y_start,
        "y_end": y_end,
        "declared_rows": y_end - y_start + 1,
        "payload_hex": payload.hex(),
    }


def _partial_action(
    *, ordinal: int, role: str, branch: str, window: GuardWindow, frame: bytearray
) -> dict[str, Any]:
    identity.set_rect(frame, _base_window(window))
    item: dict[str, Any] = {
        "ordinal": ordinal,
        "role": role,
        "branch": branch,
        "window": asdict(window),
        "palette_source": "L535_RUNTIME",
        "dtm_transport": "EXPLICIT_GUARDED_CROPPED_WINDOW_128_ROWS",
        "dtm_rows_per_controller": STREAM_ROWS,
        "dtm_bytes_per_controller": STREAM_BYTES,
        "ptlw_writes_per_controller": 2,
        "ptlw": {
            "cs1": _ptlw(window.cs1_guard),
            "cs2": _ptlw(window.cs2_guard),
        },
        "refresh_sequence": [
            "PTLW_CS1_PRE_DTM",
            "PTLW_CS2_PRE_DTM",
            "EXPLICIT_GUARDED_DTM_128_ROWS_CS1",
            "EXPLICIT_GUARDED_DTM_128_ROWS_CS2",
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
        "cs1_dtm": _stream_identity(window.cs1_code, window.cs1_guard),
        "cs2_dtm": _stream_identity(window.cs2_code, window.cs2_guard),
    }
    descriptor = {
        "schema": "mf1750-runtime-lut-ptlw-guard-direction-ab-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        **item,
    }
    item["descriptor_id"] = identity.sha256(identity.canonical(descriptor))
    item["action_id"] = identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_ACTION_V1|"
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
        "ptlw": None,
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
        "schema": "mf1750-runtime-lut-ptlw-guard-direction-ab-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        **item,
    }
    item["descriptor_id"] = identity.sha256(identity.canonical(descriptor))
    item["action_id"] = identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
        ).encode("ascii")
    )
    return item


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        identity.validate_window(_base_window(window))
        for guard in (window.cs1_guard, window.cs2_guard):
            ptlw = _ptlw(guard)
            if ptlw["declared_rows"] != STREAM_ROWS:
                raise ValueError("PTLW and DTM row counts differ")
            if len(_guard_bytes(BLUE_CODE, guard)) != STREAM_BYTES:
                raise ValueError("guard DTM byte count differs")
    if len({(w.x, w.target_y, w.width, w.target_height) for w in WINDOWS}) != 1:
        raise ValueError("guard crossover must keep one target ROI")

    white = bytes([0x11]) * (1024 * 600 // 2)
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    actions = [
        _white_action(
            ordinal=1,
            role="FACTORY_OTP_WHITE_HEALTH_ANCHOR",
            branch="FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
            frame=white,
        ),
        _partial_action(
            ordinal=2,
            role=PARTIAL_ROLES[0],
            branch=PARTIAL_BRANCHES[0],
            window=WINDOWS[0],
            frame=frame,
        ),
        _white_action(
            ordinal=3,
            role="FACTORY_OTP_WHITE_CROSSOVER_RESET",
            branch="FACTORY_OTP_FULL_FRAME_0X11_CROSSOVER_RESET",
            frame=white,
        ),
    ]
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    actions.extend(
        [
            _partial_action(
                ordinal=4,
                role=PARTIAL_ROLES[1],
                branch=PARTIAL_BRANCHES[1],
                window=WINDOWS[1],
                frame=frame,
            ),
            _white_action(
                ordinal=5,
                role="FACTORY_OTP_WHITE_RECOVERY",
                branch="FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
                frame=white,
            ),
        ]
    )

    profile = deepcopy(v3.build_report()["contract"]["profile"])
    contract = {
        "schema": "mf1750-runtime-lut-ptlw-guard-direction-ab-contract-v1",
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
            "target_roi": {"x": 176, "y": 240, "width": 160, "height": 120},
            "guard_rows": GUARD_ROWS,
            "dtm_rows_fixed": STREAM_ROWS,
            "dtm_bytes_fixed_per_controller": STREAM_BYTES,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "controlled_delta": {
            "independent_variable": "WHITE_GUARD_DIRECTION_ONLY",
            "a": {"ordinal": 2, "cs1": "BOTTOM_8", "cs2": "TOP_8"},
            "b": {"ordinal": 4, "cs1": "TOP_8", "cs2": "BOTTOM_8"},
            "fresh_white_before_each_treatment": True,
            "crossover_reset_ordinal": 3,
            "code_both_controllers": BLUE_CODE,
            "white_guard_code": WHITE_CODE,
            "same_target_roi": True,
            "same_dtm_rows_and_bytes": True,
            "repeat_identical_ptlw_after_pon_busy": True,
            "pre_pon_cdi_ff_preserved": True,
        },
        "evidence_boundary": {
            "explicit_declared_rows_equal_streamed_rows": True,
            "runtime_code7_is_guard_of_factory_white_not_white_recovery": True,
            "guard_width_pixels": GUARD_ROWS,
            "guard_refinement_only_after_hit": [4, 2, 1],
            "physical_bottom_equals_logical_y_end_proven": False,
            "predicted_fix": False,
            "observation_must_record": [
                "FPC_DIRECTION",
                "PHYSICAL_ANOMALY_EDGE",
                "TARGET_LAST_ROW_VS_GUARD_VS_OUTSIDE",
                "MAPPED_LOGICAL_EDGE_IF_KNOWN",
                "CS1_VS_CS2",
            ],
            "acceptance_rule": (
                "only conclude from whether edge quality follows the explicit "
                "top/bottom guard direction after controller swap"
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
        "guard_direction_controller_swap": True,
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
        "kind": "mf1750-runtime-lut-ptlw-guard-direction-ab-v1-offline-identities",
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
        "contract_id": identity.sha256(identity.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
