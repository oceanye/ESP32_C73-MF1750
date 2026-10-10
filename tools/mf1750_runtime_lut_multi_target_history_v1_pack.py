#!/usr/bin/env python3
"""Offline identities for the bidirectional multi-target history screen.

The fixed nine-action campaign brackets two independent 8x8 runtime-LUT
history screens with factory-OTP white.  In each direction, column selects
the source code and row selects the target code, so eight adjacent cells in a
row share one target while retaining eight different source histories.

Runtime transport code 7 is only an unqualified separator/background code.
It is never described as white; every white anchor and recovery uses the
factory-OTP 0x11 frame and the dedicated factory refresh path.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_v1_pack as cross  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402
from tools import (  # noqa: E402
    mf1750_runtime_lut_multi_target_history_v1_white_containment_pack as containment,
)


VARIANT_KEY = "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1"
BUILD_TAG = "MF1750_EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_2026-08-24"
TEST_ID = "EC5-MULTI-TARGET-HISTORY-8X8-AB-BA-V1"
CAMPAIGN_ID = "EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1"
NVS_NAMESPACE = "rlmth_v1"
NVS_KEY = "cursor_mth1"
PROFILE_ACTIVE = cross.PROFILE_ACTIVE
PROFILE_COMMENTED = cross.PROFILE_COMMENTED
PROFILE_ID = (
    "ACTIVE_SOURCE_COLUMNS_TO_COMMENTED_TARGET_ROWS__FACTORY_OTP_WHITE__"
    "COMMENTED_SOURCE_COLUMNS_TO_ACTIVE_TARGET_ROWS"
)

GRID_ROWS = 8
GRID_COLUMNS = 8
GRID_X0 = 20
GRID_Y0 = 40
CELL_WIDTH = 52
CELL_HEIGHT = 58
GAP_X = 8
GAP_Y = 8
GRID_X1_EXCLUSIVE = GRID_X0 + GRID_COLUMNS * CELL_WIDTH + (GRID_COLUMNS - 1) * GAP_X
GRID_Y1_EXCLUSIVE = GRID_Y0 + GRID_ROWS * CELL_HEIGHT + (GRID_ROWS - 1) * GAP_Y
SEPARATOR_CODE = 7

GLOBAL_HEADERS: tuple[str | None, ...] = (
    None,
    "active",
    "commented",
    "commented",
    None,
    "commented",
    "active",
    "active",
    None,
)
ROLES = (
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
    "AB_ACTIVE_SOURCE_COLUMNS",
    "AB_COMMENTED_TARGET_ROWS",
    "AB_COMMENTED_TARGET_ROWS_IDENTICAL_REPEAT",
    "FACTORY_OTP_WHITE_DIRECTION_SEPARATOR",
    "BA_COMMENTED_SOURCE_COLUMNS",
    "BA_ACTIVE_TARGET_ROWS",
    "BA_ACTIVE_TARGET_ROWS_IDENTICAL_REPEAT",
    "FACTORY_OTP_WHITE_RECOVERY",
)
DRIVER_ROLES = (
    "FactoryWhite",
    "Source",
    "Mid",
    "Target",
    "FactoryWhite",
    "ReverseSource",
    "ReverseTarget",
    "ReverseTarget",
    "FactoryWhite",
)
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("multi-target cell outside 8x8 grid")
    return (
        GRID_X0 + column * (CELL_WIDTH + GAP_X),
        GRID_Y0 + row * (CELL_HEIGHT + GAP_Y),
        CELL_WIDTH,
        CELL_HEIGHT,
    )


def _validate_geometry() -> None:
    if (
        GRID_X0 < 0
        or GRID_Y0 < 0
        or GRID_X1_EXCLUSIVE > base.CONTROLLER_WIDTH
        or GRID_Y1_EXCLUSIVE > base.HEIGHT
        or GRID_X0 % 2
        or CELL_WIDTH % 2
        or GAP_X % 2
    ):
        raise ValueError("multi-target geometry violates packed 4bpp bounds")
    rectangles = [
        _cell_bounds(row, column)
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]
    for index, left in enumerate(rectangles):
        lx, ly, lw, lh = left
        for rx, ry, rw, rh in rectangles[index + 1 :]:
            if not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly):
                raise ValueError("multi-target cells overlap")


def _set_controller_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    if controller not in (0, 1) or not 0 <= code <= 7:
        raise ValueError("invalid controller or transport code")
    x, y, width, height = _cell_bounds(row, column)
    global_x = controller * base.CONTROLLER_WIDTH + x
    pair = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + global_x // 2
        frame[start : start + width // 2] = bytes([pair]) * (width // 2)


def _grid_frame(axis: str) -> bytes:
    if axis not in ("source_columns", "target_rows"):
        raise ValueError("unknown multi-target grid axis")
    pair = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray([pair]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                code = column if axis == "source_columns" else row
                _set_controller_cell(frame, controller, row, column, code)
    return bytes(frame)


def _factory_white_frame() -> bytes:
    return bytes([0x11]) * (base.WIDTH * base.HEIGHT // 2)


def _controller_stream(frame: bytes, controller: int) -> bytes:
    return cross.controller_stream(frame, controller)


def _payload_identity(data: bytes) -> dict[str, Any]:
    return cross.payload_identity(data)


def recipe_map() -> list[dict[str, Any]]:
    """Return 64 AB plus 64 BA directional histories per controller."""

    recipes: list[dict[str, Any]] = []
    for direction, source_profile, target_profile in (
        ("AB", "active", "commented"),
        ("BA", "commented", "active"),
    ):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                recipes.append(
                    {
                        "recipe_id": f"{direction}-{column}-TO-{row}",
                        "direction": direction,
                        "row": row,
                        "column": column,
                        "local_roi": dict(
                            zip(
                                ("x", "y", "width", "height"),
                                _cell_bounds(row, column),
                                strict=True,
                            )
                        ),
                        "source": {
                            "global_header": source_profile,
                            "code": column,
                        },
                        "target": {
                            "global_header": target_profile,
                            "code": row,
                        },
                        "target_repeat": {
                            "global_header": target_profile,
                            "code": row,
                        },
                        "controller_repeats": [
                            {
                                "controller": controller,
                                "source_code": column,
                                "target_code": row,
                                "profile_sequence": [
                                    source_profile,
                                    target_profile,
                                    target_profile,
                                ],
                                "mirrored": False,
                            }
                            for controller in (0, 1)
                        ],
                        "spatial_dither": False,
                    }
                )
    return recipes


def build_report() -> dict[str, Any]:
    """Build immutable frames, actions, and contract without device access."""

    _validate_geometry()
    factory_white = _factory_white_frame()
    source_columns = _grid_frame("source_columns")
    target_rows = _grid_frame("target_rows")
    frames = (
        factory_white,
        source_columns,
        target_rows,
        target_rows,
        factory_white,
        source_columns,
        target_rows,
        target_rows,
        factory_white,
    )
    actions: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True),
        1,
    ):
        factory_otp = header is None
        item = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "branch": branch,
            "palette_source": "FACTORY_OTP" if factory_otp else "L535_RUNTIME",
            "global_header": header,
            "profile_id": None if factory_otp else cross.profile(header)["id"],
            "frame": base.frame_identity(frame),
            "cs1_dtm": _payload_identity(_controller_stream(frame, 0)),
            "cs2_dtm": _payload_identity(_controller_stream(frame, 1)),
            "prior_static_action_id": prior_action_id,
        }
        descriptor = {
            "schema": "mf1750-multi-target-history-action-descriptor-v1",
            "variant": VARIANT_KEY,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_MULTI_TARGET_HISTORY_ACTION_V1|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    recipes = recipe_map()
    contract = {
        "schema": "mf1750-multi-target-history-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile_id": PROFILE_ID,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "cells_per_controller_per_direction": GRID_ROWS * GRID_COLUMNS,
            "directional_recipes": 2 * GRID_ROWS * GRID_COLUMNS,
            "total_controller_observations": 4 * GRID_ROWS * GRID_COLUMNS,
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "grid_x1_local_exclusive": GRID_X1_EXCLUSIVE,
            "grid_y1_exclusive": GRID_Y1_EXCLUSIVE,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "cs2_position_mirrored": False,
            "duplicate_recipe_across_controllers": True,
            "controller_color_equivalence_claimed": False,
            "paired_controller_observations_not_waveform_identical": True,
            "controller_payload_binding": ("CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED"),
            "spatial_dither": False,
        },
        "axis_mapping": {
            "row": "target_code_0_to_7",
            "column": "source_code_0_to_7",
            "horizontal_comparison_group": (
                "eight adjacent cells share one target code and differ only in source code"
            ),
        },
        "profiles": profiles,
        "global_header_sequence": list(GLOBAL_HEADERS),
        "recipes": recipes,
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "driver_role": item["driver_role"],
                "palette_source": item["palette_source"],
                "global_header": item["global_header"],
                "profile_id": item["profile_id"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "factory_otp_white": {
            "ordinals": [1, 5, 9],
            "frame_fill_byte": "0x11",
            "frame_bytes": len(factory_white),
            "runtime_code7_used_as_white": False,
        },
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "runtime_lut": True,
        "factory_otp": True,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "unknown_commands": False,
        "local_hold_claimed": False,
        "spatial_dither": False,
        "multi_target_history_screening": True,
        "target_repeat_stability_probe": True,
        "brightness_candidates_only": True,
        "qualified_colours": 0,
        "human_observation_gate_after_every_action": True,
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required_for_every_ordinal": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "strict_ordinal_progression": {
            "terminal_next_ordinal": 10,
            "same_boot_prior_complete_required": True,
            "skip_to_factory_white_allowed": False,
            "failure_containment": {
                "kind": "independent_fresh_identity_factory_otp_white",
                "source_campaign_id": containment.SOURCE_CAMPAIGN_ID,
                "test_id": containment.TEST_ID,
                "campaign_id": containment.CAMPAIGN_ID,
                "contract_id": containment.CONTRACT_ID,
                "platformio_config": (
                    "platformio.runtime_lut_multi_target_history_v1_"
                    "white_containment.ini"
                ),
                "runner": (
                    "tools/mf1750_runtime_lut_multi_target_history_v1_"
                    "white_containment_once.py"
                ),
                "firmware_bytes": containment.FIRMWARE_BIN_BYTES,
                "firmware_sha256": containment.FIRMWARE_BIN_SHA256,
                "elf_bytes": containment.FIRMWARE_ELF_BYTES,
                "elf_sha256": containment.FIRMWARE_ELF_SHA256,
                "nvs_namespace": containment.NVS_NAMESPACE,
                "nvs_key": containment.NVS_KEY,
                "base_route": containment.BASE_ROUTE,
                "descriptor_id": containment.DESCRIPTOR_ID,
                "action_id": containment.ACTION_ID,
                "claim_kind": containment.CLAIM_KIND,
                "campaign_nvs_dependency": False,
                "independent_permanent_claim": True,
                "automatic_dispatch": False,
                "main_campaign_resume_after_containment": False,
                "required_after_any_visual_or_terminal_failure": True,
            },
        },
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-multi-target-history-v1-offline-identities",
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
