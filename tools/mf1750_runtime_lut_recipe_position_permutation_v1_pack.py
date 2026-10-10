#!/usr/bin/env python3
"""Offline identities for the red/pink P1 recipe-position permutation.

This is a new campaign, not a replay or continuation of the sealed red/pink
brightness V2 campaign.  It starts from an externally verified factory-OTP
white state and exposes four separately armed actions:

1. active-global source frame with physical column c carrying (c + 3) mod 8;
2. commented-global middle frame with physical row r carrying 7 - r;
3. active-global fixed target code 0;
4. factory-OTP white recovery.

The legacy mixed controller payload remains intentionally frozen: CS1 receives
the active-535 R20 prefix and CS2 receives the commented-535 R20 prefix.  The
experiment changes only recipe placement, so it cannot establish controller
colour equivalence or common-LUT parity.
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


VARIANT_KEY = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1"
BUILD_TAG = (
    "MF1750_EC5_REDPINK_RECIPE_POSITION_PERMUTATION_P1_8X8_ACA_"
    "SINGLE_APP_BOOT_FLASH_VERIFY_V1_2026-08-28"
)
TEST_ID = "EC5-REDPINK-RECIPE-POSITION-PERMUTATION-P1-8X8-ACA-V1"
CAMPAIGN_ID = "EC5_REDPINK_RECIPE_POSITION_PERMUTATION_P1_8X8_ACA_V1"
NVS_NAMESPACE = "rppp1"
NVS_KEY = "cursor_rpp1"
NVS_BOOT_KEY = "boot_rpp1"
PROFILE_ID = (
    "ACTIVE_SOURCE_TO_COMMENTED_MIDDLE_TO_ACTIVE_CODE0_TARGET__"
    "CS1_ACTIVE535__CS2_COMMENTED535__P1_POSITION_PERMUTATION"
)
TARGET_CODE = 0
SEPARATOR_CODE = 7
FACTORY_WHITE_FILL_BYTE = 0x11
SOURCE_COLUMN_SHIFT = 3
MIDDLE_ROW_TRANSFORM = "7-r"

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

GLOBAL_HEADERS: tuple[str | None, ...] = ("active", "commented", "active", None)
ROLES = (
    "PERMUTED_SOURCE_GRID_ACTIVE_SHIFT3",
    "PERMUTED_MIDDLE_GRID_COMMENTED_REVERSE",
    "PERMUTED_FIXED_TARGET_ACTIVE_CODE0",
    "FACTORY_OTP_WHITE_RECOVERY",
)
DRIVER_ROLES = ("Source", "Mid", "Target", "FactoryWhite")
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("recipe-permutation cell outside 8x8 grid")
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
        raise ValueError("recipe-permutation grid violates packed 4bpp bounds")
    rectangles = [_cell_bounds(row, col) for row in range(8) for col in range(8)]
    for index, left in enumerate(rectangles):
        lx, ly, lw, lh = left
        for rx, ry, rw, rh in rectangles[index + 1 :]:
            if not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly):
                raise ValueError("recipe-permutation cells overlap")


def source_code_at_physical_column(column: int) -> int:
    if not 0 <= column < GRID_COLUMNS:
        raise ValueError("source physical column outside 0..7")
    return (column + SOURCE_COLUMN_SHIFT) % GRID_COLUMNS


def middle_code_at_physical_row(row: int) -> int:
    if not 0 <= row < GRID_ROWS:
        raise ValueError("middle physical row outside 0..7")
    return GRID_ROWS - 1 - row


def physical_column_for_source_code(source: int) -> int:
    if not 0 <= source < GRID_COLUMNS:
        raise ValueError("source code outside 0..7")
    return (source - SOURCE_COLUMN_SHIFT) % GRID_COLUMNS


def physical_row_for_middle_code(middle: int) -> int:
    if not 0 <= middle < GRID_ROWS:
        raise ValueError("middle code outside 0..7")
    return GRID_ROWS - 1 - middle


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


def _grid_frame(stage: str) -> bytes:
    if stage not in ("source", "middle", "target"):
        raise ValueError("unknown recipe-permutation stage")
    separator_pair = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray([separator_pair]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                if stage == "source":
                    code = source_code_at_physical_column(column)
                elif stage == "middle":
                    code = middle_code_at_physical_row(row)
                else:
                    code = TARGET_CODE
                _set_controller_cell(frame, controller, row, column, code)
    return bytes(frame)


def _factory_white_frame() -> bytes:
    return bytes([FACTORY_WHITE_FILL_BYTE]) * (base.WIDTH * base.HEIGHT // 2)


def _controller_stream(frame: bytes, controller: int) -> bytes:
    return cross.controller_stream(frame, controller)


def _payload_identity(data: bytes) -> dict[str, Any]:
    return cross.payload_identity(data)


def _roi(row: int, column: int) -> dict[str, int]:
    return dict(
        zip(
            ("x", "y", "width", "height"),
            _cell_bounds(row, column),
            strict=True,
        )
    )


def recipe_map() -> list[dict[str, Any]]:
    """Return 64 recipe identities with their P0 and P1 physical positions."""

    records: list[dict[str, Any]] = []
    for middle in range(GRID_ROWS):
        for source in range(GRID_COLUMNS):
            p1_row = physical_row_for_middle_code(middle)
            p1_column = physical_column_for_source_code(source)
            records.append(
                {
                    "recipe_id": f"REDPINK-A{source}-B{middle}-A{TARGET_CODE}",
                    "source": {"global_header": "active", "code": source},
                    "middle": {"global_header": "commented", "code": middle},
                    "target": {"global_header": "active", "code": TARGET_CODE},
                    "p0_physical": {
                        "row": middle,
                        "column": source,
                        "local_roi": _roi(middle, source),
                    },
                    "p1_physical": {
                        "row": p1_row,
                        "column": p1_column,
                        "local_roi": _roi(p1_row, p1_column),
                    },
                    "spatial_dither": False,
                }
            )
    return records


def observation_map() -> list[dict[str, Any]]:
    """Return the deterministic 128 controller-observation P0/P1 map."""

    observations: list[dict[str, Any]] = []
    for controller in (0, 1):
        controller_x_offset = controller * base.CONTROLLER_WIDTH
        for recipe in recipe_map():
            p0 = recipe["p0_physical"]
            p1 = recipe["p1_physical"]
            p0_roi = dict(p0["local_roi"])
            p1_roi = dict(p1["local_roi"])
            p0_roi["global_x"] = controller_x_offset + p0_roi["x"]
            p1_roi["global_x"] = controller_x_offset + p1_roi["x"]
            observations.append(
                {
                    "observation_id": f"CS{controller + 1}-{recipe['recipe_id']}",
                    "controller": controller,
                    "controller_label": f"CS{controller + 1}",
                    "recipe_id": recipe["recipe_id"],
                    "source_code": recipe["source"]["code"],
                    "middle_code": recipe["middle"]["code"],
                    "target_code": TARGET_CODE,
                    "p0_physical": {
                        "row": p0["row"],
                        "column": p0["column"],
                        "roi": p0_roi,
                    },
                    "p1_physical": {
                        "row": p1["row"],
                        "column": p1["column"],
                        "roi": p1_roi,
                    },
                }
            )
    return observations


def physical_to_recipe_map() -> list[dict[str, Any]]:
    """Return P1 physical-cell order for direct camera-grid indexing."""

    mapping: list[dict[str, Any]] = []
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                source = source_code_at_physical_column(column)
                middle = middle_code_at_physical_row(row)
                mapping.append(
                    {
                        "controller": controller,
                        "controller_label": f"CS{controller + 1}",
                        "physical_row": row,
                        "physical_column": column,
                        "recipe_id": f"REDPINK-A{source}-B{middle}-A{TARGET_CODE}",
                        "source_code": source,
                        "middle_code": middle,
                        "target_code": TARGET_CODE,
                        "local_roi": _roi(row, column),
                    }
                )
    return mapping


def _runtime_binding(header: str | None) -> dict[str, Any]:
    if header is None:
        return {
            "palette_source": "FACTORY_OTP",
            "global_header": None,
            "global_header_sha256": None,
            "cs1_r20_prefix_bytes": 0,
            "cs1_r20_prefix_sha256": None,
            "cs2_r20_prefix_bytes": 0,
            "cs2_r20_prefix_sha256": None,
            "r21_bytes": 0,
            "r21_sha256": None,
        }
    profile = cross.profile(header)
    return {
        "palette_source": "L535_RUNTIME",
        "global_header": header,
        "profile_id": profile["id"],
        "global_header_sha256": profile["global_header_sha256"],
        "cs1_r20_prefix_bytes": profile["cs1_r20_prefix_bytes"],
        "cs1_r20_prefix_sha256": profile["cs1_r20_prefix_sha256"],
        "cs2_r20_prefix_bytes": profile["cs2_r20_prefix_bytes"],
        "cs2_r20_prefix_sha256": profile["cs2_r20_prefix_sha256"],
        "r21_bytes": profile["r21_bytes"],
        "r21_sha256": profile["r21_sha256"],
    }


def build_report() -> dict[str, Any]:
    """Build immutable frames, actions, mapping, and analysis contract offline."""

    _validate_geometry()
    source = _grid_frame("source")
    middle = _grid_frame("middle")
    target = _grid_frame("target")
    factory_white = _factory_white_frame()
    frames = (source, middle, target, factory_white)

    actions: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True), 1
    ):
        binding = _runtime_binding(header)
        item = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "branch": branch,
            **binding,
            "frame": base.frame_identity(frame),
            "cs1_dtm": _payload_identity(_controller_stream(frame, 0)),
            "cs2_dtm": _payload_identity(_controller_stream(frame, 1)),
            "prior_static_action_id": prior_action_id,
            "boot_admission": {
                "campaign_boot_binding_key": NVS_BOOT_KEY,
                "admission": (
                    "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                    if ordinal == 1
                    else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY"
                ),
                "required_prior_terminal_state": None if ordinal == 1 else "COMPLETE",
                "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
                "firmware_arm_gate": True,
                "firmware_execute_gate": True,
                "firmware_dispatch_gate": True,
                "reboot_resume_allowed": False,
                "post_containment_resume_allowed": False,
            },
        }
        descriptor = {
            "schema": "mf1750-redpink-recipe-position-permutation-action-descriptor-v1",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_REDPINK_RECIPE_POSITION_PERMUTATION_ACTION_V1|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    recipes = recipe_map()
    observations = observation_map()
    physical_mapping = physical_to_recipe_map()
    analysis_input_contract = {
        "schema": "mf1750-redpink-recipe-position-permutation-analysis-input-v1",
        "reference_layout": "P0_ACTION4_SEALED_ORIGINAL_LAYOUT",
        "candidate_layout": "P1_SOURCE_SHIFT3_MIDDLE_REVERSE",
        "source_transform": {
            "physical_to_code": "source=(physical_column+3)%8",
            "code_to_physical": "physical_column=(source-3)%8",
        },
        "middle_transform": {
            "physical_to_code": "middle=7-physical_row",
            "code_to_physical": "physical_row=7-middle",
        },
        "fixed_target_code": TARGET_CODE,
        "expected_observations": 128,
        "expected_unique_recipes": 64,
        "controller_analysis": "independent_then_reported_together",
        "required_camera_cell_fields": [
            "controller",
            "physical_row",
            "physical_column",
            "lab_l",
            "lab_a",
            "lab_b",
        ],
        "join_key": ["controller", "physical_row", "physical_column"],
        "inverse_recipe_join_source": "observation_map[].p1_physical",
        "comparison_outputs": [
            "recipe_aligned_lab_correlation",
            "recipe_aligned_lstar_correlation",
            "physical_position_lab_correlation",
            "physical_position_lstar_correlation",
            "recipe_minus_physical_correlation",
            "row_effect",
            "column_effect",
            "illumination_plane_residual",
            "colour_family_label",
        ],
        "exploratory_gate": {
            "recipe_correlation_min": 0.80,
            "recipe_minus_physical_correlation_min": 0.25,
            "pass_label": "RECIPE_LINKED_CANDIDATE_ONLY",
            "not_a_qualified_new_colour": True,
        },
        "qualification_limits": {
            "single_permutation_cannot_qualify": True,
            "fixed_camera_position_confound_must_be_reported": True,
            "controller_colour_equivalence_not_claimed": True,
            "new_colour_count_not_inferred_from_recipe_count": True,
        },
    }

    contract = {
        "schema": "mf1750-redpink-recipe-position-permutation-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile_id": PROFILE_ID,
        "precondition": {
            "required_display_state": "VERIFIED_FACTORY_OTP_CLEAN_WHITE",
            "white_anchor_is_external_predecessor": True,
            "old_redpink_v2_action_replayed": False,
            "old_redpink_v2_identity_reused": False,
            "old_redpink_v2_output_reused": False,
        },
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "candidate_cells_per_controller": GRID_ROWS * GRID_COLUMNS,
            "candidate_cells_total_observations": len(observations),
            "unique_recipes": len(recipes),
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "grid_x1_local_exclusive": GRID_X1_EXCLUSIVE,
            "grid_y1_exclusive": GRID_Y1_EXCLUSIVE,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "duplicate_recipe_across_controllers": True,
            "controller_color_equivalence_claimed": False,
            "spatial_dither": False,
        },
        "permutation": {
            "id": "P1_SOURCE_SHIFT3_MIDDLE_REVERSE",
            "source_column_shift_mod8": SOURCE_COLUMN_SHIFT,
            "middle_physical_row_to_code": MIDDLE_ROW_TRANSFORM,
            "bijective": True,
            "p0_to_p1_has_no_fixed_cells": all(
                recipe["p0_physical"]["row"] != recipe["p1_physical"]["row"]
                or recipe["p0_physical"]["column"] != recipe["p1_physical"]["column"]
                for recipe in recipes
            ),
        },
        "axis_mapping": {
            "physical_column": "active_source_code_(column+3)_mod_8",
            "physical_row": "commented_middle_code_(7-row)",
            "fixed_target": "active_code_0",
            "recipe": (
                "active_source((physical_column+3)%8)->"
                "commented_middle(7-physical_row)->active_target(code0)"
            ),
        },
        "profiles": {name: cross.profile(name) for name in ("active", "commented")},
        "global_header_sequence": list(GLOBAL_HEADERS),
        "recipe_map": recipes,
        "observation_map": observations,
        "physical_to_recipe_map": physical_mapping,
        "analysis_input_contract": analysis_input_contract,
        "actions": [
            {
                key: item[key]
                for key in (
                    "ordinal",
                    "role",
                    "driver_role",
                    "palette_source",
                    "global_header",
                    "profile_id",
                    "global_header_sha256",
                    "cs1_r20_prefix_bytes",
                    "cs1_r20_prefix_sha256",
                    "cs2_r20_prefix_bytes",
                    "cs2_r20_prefix_sha256",
                    "r21_bytes",
                    "r21_sha256",
                    "descriptor_id",
                    "action_id",
                    "prior_static_action_id",
                    "boot_admission",
                )
                if key in item
            }
            for item in actions
        ],
        "factory_otp_white": {
            "ordinal": 4,
            "frame_fill_byte": "0x11",
            "frame_bytes": len(factory_white),
            "runtime_code7_used_as_white": False,
        },
        "runtime_payload_binding": {
            "cs1_r20": "active_535_prefix",
            "cs2_r20": "commented_535_prefix",
            "r21": "shared_all_ff_704",
            "mixed_controller_r20_intentionally_preserved": True,
            "same_r20_controller_parity_test": False,
        },
        "runtime_lut": True,
        "factory_otp": True,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "spatial_dither": False,
        "recipe_position_permutation": True,
        "human_observation_gate_after_every_action": True,
        "strict_ordinal_progression": {
            "terminal_next_ordinal": 5,
            "same_boot_prior_complete_required": True,
            "device_enforced_same_boot": True,
            "campaign_boot_nonce_persisted_before_any_action": True,
            "campaign_boot_binding_key": NVS_BOOT_KEY,
            "arm_boot_binding_gate": True,
            "execute_boot_binding_gate": True,
            "dispatch_boot_binding_gate": True,
            "direct_exact_post_resume_after_reboot": False,
            "skip_to_factory_white_allowed": False,
        },
        "one_visible_refresh_per_ordinal": True,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-redpink-recipe-position-permutation-v1-offline-identities",
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
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile_id": PROFILE_ID,
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "analysis_input_contract": analysis_input_contract,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
