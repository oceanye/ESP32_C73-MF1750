#!/usr/bin/env python3
"""Freeze the single-action, position-balanced same-R20 4x8 atlas.

This module is offline-only.  The campaign contains exactly one visible
runtime-LUT atlas refresh.  Factory-OTP white before and after the atlas are
independent containment campaigns and are intentionally not encoded as V2
actions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402


VARIANT_KEY = "L535_SAME_R20_DUAL_CONTROLLER_PARITY_4X8_V2"
BUILD_TAG = "MF1750_EC5_SAME_R20_PARITY_4X8_V2_2026-08-28"
TEST_ID = "EC5-SAME-R20-PARITY-4X8-V2"
CAMPAIGN_ID = "EC5_SAME_R20_PARITY_4X8_V2"
NVS_NAMESPACE = "sr20p4v2"
NVS_KEY = "cursor_s4v2"
NVS_BOOT_KEY = "boot_s4v2"
DEVICE_API_VERSION = "MF1750_EC5_SAME_R20_PARITY_4X8_DEVICE_V2"
IDENTITY_REVISION = "same-r20-dual-controller-position-balanced-4x8-v2"
CLASSIFICATION = (
    "EXPERIMENTAL_POSITION_BALANCED_SAME_R20_CONTROLLER_PARITY_"
    "NOT_ABSOLUTE_COLOUR_QUALIFICATION"
)
BASE_ROUTE = "/api/ec5/same-r20-parity-4x8-v2"

SEPARATOR_CODE = 7
GRID_ROWS = 4
GRID_COLUMNS = 8
GRID_X0 = 20
GRID_Y_BY_ROW = (44, 180, 316, 452)
CELL_WIDTH = 52
CELL_HEIGHT = 100
GAP_X = 8
GAP_Y = 36
GRID_X1_EXCLUSIVE = GRID_X0 + GRID_COLUMNS * CELL_WIDTH + (GRID_COLUMNS - 1) * GAP_X
GRID_Y1_EXCLUSIVE = GRID_Y_BY_ROW[-1] + CELL_HEIGHT
CODE_ROWS = (
    (0, 1, 2, 3, 4, 5, 6, 7),
    (6, 7, 0, 1, 2, 3, 4, 5),
    (5, 4, 7, 6, 1, 0, 3, 2),
    (3, 2, 5, 4, 7, 6, 1, 0),
)

RUNTIME_PSR = bytes((0x5F, 0xE9))
CONTROLLER_TRES = bytes((0x02, 0x00, 0x02, 0x58))
HIDDEN_ENABLE = bytes((0x01,))

_ACTIVE_CONSTANTS = {
    "global_header_sha256": (
        "48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8"
    ),
    "power_payload_sha256": (
        "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2"
    ),
    "pll_payload_sha256": (
        "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
    ),
    "r20_prefix_sha256": base.ACTIVE_R20_PREFIX_SHA256,
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active_profile() -> dict[str, Any]:
    """Return the byte-identical active tuple bound to both controllers."""

    controller = {
        "r20_command": "0x20",
        "r20_prefix_bytes": 535,
        "r20_prefix_sha256": _ACTIVE_CONSTANTS["r20_prefix_sha256"],
        "r21_command": "0x21",
        "r21_bytes": 704,
        "r21_sha256": base.R21_SHA256,
    }
    tuple_seed = {
        "name": "active",
        "global_header_sha256": _ACTIVE_CONSTANTS["global_header_sha256"],
        "runtime_psr_sha256": sha256_bytes(RUNTIME_PSR),
        "power_payload_sha256": _ACTIVE_CONSTANTS["power_payload_sha256"],
        "pll_payload_sha256": _ACTIVE_CONSTANTS["pll_payload_sha256"],
        "tres_sha256": sha256_bytes(CONTROLLER_TRES),
        "hidden_enable_sha256": sha256_bytes(HIDDEN_ENABLE),
        "controller": controller,
    }
    return {
        "id": "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535",
        "name": "active",
        "global_header_sha256": _ACTIVE_CONSTANTS["global_header_sha256"],
        "runtime_psr_command": "0x00",
        "runtime_psr_bytes": len(RUNTIME_PSR),
        "runtime_psr_sha256": sha256_bytes(RUNTIME_PSR),
        "power_command": "0x01",
        "power_payload_bytes": 6,
        "power_payload_sha256": _ACTIVE_CONSTANTS["power_payload_sha256"],
        "pll_command": "0x30",
        "pll_payload_bytes": 1,
        "pll_payload_sha256": _ACTIVE_CONSTANTS["pll_payload_sha256"],
        "tres_command": "0x61",
        "tres_bytes": len(CONTROLLER_TRES),
        "tres_sha256": sha256_bytes(CONTROLLER_TRES),
        "hidden_enable_command": "0xe9",
        "hidden_enable_bytes": len(HIDDEN_ENABLE),
        "hidden_enable_sha256": sha256_bytes(HIDDEN_ENABLE),
        "cs1": dict(controller),
        "cs2": dict(controller),
        "controller_payloads_byte_identical": True,
        "global_tuple_id": sha256_bytes(canonical_json(tuple_seed)),
    }


def cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("same-R20 4x8 cell is outside the grid")
    return (
        GRID_X0 + column * (CELL_WIDTH + GAP_X),
        GRID_Y_BY_ROW[row],
        CELL_WIDTH,
        CELL_HEIGHT,
    )


def validate_geometry() -> None:
    if (
        GRID_X0 < 0
        or GRID_Y_BY_ROW[0] < 0
        or GRID_X1_EXCLUSIVE > base.CONTROLLER_WIDTH
        or GRID_Y1_EXCLUSIVE > base.HEIGHT
        or GRID_X0 % 2
        or CELL_WIDTH % 2
        or GAP_X % 2
        or tuple(b - a for a, b in zip(GRID_Y_BY_ROW, GRID_Y_BY_ROW[1:]))
        != (CELL_HEIGHT + GAP_Y,) * 3
    ):
        raise ValueError("same-R20 4x8 atlas violates packed 4bpp geometry")
    flat = [code for row in CODE_ROWS for code in row]
    if sorted(flat) != [code for code in range(8) for _ in range(4)]:
        raise ValueError("each transport code must occupy four positions")


def _set_controller_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    if controller not in (0, 1) or not 0 <= code <= 7:
        raise ValueError("invalid controller or transport code")
    x, y, width, height = cell_bounds(row, column)
    global_x = controller * base.CONTROLLER_WIDTH + x
    packed = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + global_x // 2
        frame[start : start + width // 2] = bytes((packed,)) * (width // 2)


def atlas_frame() -> bytes:
    """Return byte-identical position-balanced 4x8 DTM on both sides."""

    validate_geometry()
    packed = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray((packed,)) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row, codes in enumerate(CODE_ROWS):
            for column, code in enumerate(codes):
                _set_controller_cell(frame, controller, row, column, code)
    return bytes(frame)


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != base.WIDTH * base.HEIGHT // 2:
        raise ValueError("invalid controller stream request")
    row_bytes = base.WIDTH // 2
    half = base.CONTROLLER_WIDTH // 2
    offset = controller * half
    return b"".join(
        frame[y * row_bytes + offset : y * row_bytes + offset + half]
        for y in range(base.HEIGHT)
    )


def payload_identity(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "fnv1a": base.fnv1a(data), "sha256": sha256_bytes(data)}


def build_report() -> dict[str, Any]:
    validate_geometry()
    frame = atlas_frame()
    cs1 = payload_identity(controller_stream(frame, 0))
    cs2 = payload_identity(controller_stream(frame, 1))
    waveform = active_profile()
    action_seed: dict[str, Any] = {
        "ordinal": 1,
        "role": "SAME_R20_ACTIVE_ACTIVE_POSITION_BALANCED_4X8_ATLAS",
        "driver_role": "Source",
        "round": 1,
        "branch": f"{VARIANT_KEY}_ACTIVE_ACTIVE_POSITION_BALANCED_ATLAS",
        "palette_source": "L535_RUNTIME",
        "global_header": "active",
        "profile_id": waveform["id"],
        "global_tuple_id": waveform["global_tuple_id"],
        "waveform_binding": waveform,
        "frame": base.frame_identity(frame),
        "cs1_dtm": cs1,
        "cs2_dtm": cs2,
        "controller_dtm_byte_identical": cs1 == cs2,
        "prior_static_action_id": None,
        "boot_admission": {
            "campaign_boot_binding_key": NVS_BOOT_KEY,
            "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
            "required_prior_terminal_state": None,
            "required_prior_ordinal": None,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        },
    }
    descriptor = {
        "schema": "mf1750-same-r20-parity-4x8-action-descriptor-v2",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        **action_seed,
    }
    action_seed["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action_seed["action_id"] = sha256_bytes(
        (
            "MF1750_SAME_R20_PARITY_4X8_ACTION_V2|"
            f"{VARIANT_KEY}|1|{action_seed['descriptor_id']}"
        ).encode("ascii")
    )
    positions = [
        {
            "row": row,
            "column": column,
            "code": CODE_ROWS[row][column],
            "x": cell_bounds(row, column)[0],
            "y": cell_bounds(row, column)[1],
            "width": CELL_WIDTH,
            "height": CELL_HEIGHT,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]
    contract = {
        "schema": "mf1750-same-r20-parity-4x8-contract-v2",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile": waveform,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "row_codes": [list(row) for row in CODE_ROWS],
            "positions": positions,
            "samples_per_code_per_controller_per_frame": 4,
            "required_retained_atlas_frames": 3,
            "required_samples_per_code_per_controller": 12,
            "background_code": SEPARATOR_CODE,
            "border": False,
            "cs2_position_mirrored": False,
            "same_layout_both_controllers": True,
            "controller_dtm_byte_identical": True,
            "spatial_dither": False,
        },
        "actions": [action_seed],
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "external_containment": {
            "outside_campaign": True,
            "factory_otp_white_before_required": True,
            "factory_otp_white_after_required": True,
            "off_white_photos_before_atlas_required": 3,
            "off_retained_atlas_photos_required": 3,
            "post_white_clean_visual_gate_required": True,
            "white_actions_in_campaign": 0,
        },
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "partial_refresh": False,
        "window_refresh": False,
        "local_hold_claimed": False,
        "controller_bus_capture_claimed": False,
        "controller_payload_source_identity_claimed": True,
        "colour_equivalence_claimed": False,
        "absolute_colour_claimed": False,
        "qualified_colours": 0,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 2,
        "kind": "mf1750-same-r20-parity-4x8-offline-identities-v2",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "actions": [action_seed],
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
