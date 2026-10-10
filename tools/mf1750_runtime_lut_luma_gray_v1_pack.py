#!/usr/bin/env python3
"""Offline identities for LUMA-GRAY-V1 (no hardware access).

This is an exploratory history screen, not a calibrated greyscale.  The
publicly evidenced factory-OTP path cannot assign black/white source states
per cell, so the requested black/white source endpoints are conservatively
replaced by the reproducible active-L535 transport anchors code 3 and code 7.
Neither anchor is named black or white.  Each of the 16 anchor/middle recipes
is repeated once in each quadrant; page 1 ends at active code 3 and page 2 at
active code 7.  CS1 and CS2 are evaluated independently.
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

VARIANT_KEY = "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1"
BUILD_TAG = "MF1750_EC5_LUMA_GRAY_EXPLORATORY_2PAGE_V1_2026-08-28"
TEST_ID = "EC5-LUMA-GRAY-EXPLORATORY-2PAGE-V1"
CAMPAIGN_ID = "EC5_LUMA_GRAY_EXPLORATORY_2PAGE_V1"
NVS_NAMESPACE = "rllg_v1"
NVS_KEY = "cursor_lg1"
NVS_BOOT_KEY = "boot_lg1"
SOURCE_ANCHOR_CODES = (3, 7)
TARGET_CODES = (3, 7)
SEPARATOR_CODE = 7
FACTORY_WHITE_FILL_BYTE = 0x11

GRID_ROWS = 8
GRID_COLUMNS = 8
GRID_X0 = 20
GRID_Y0 = 40
CELL_WIDTH = 52
CELL_HEIGHT = 58
GAP_X = 8
GAP_Y = 8

# Four 4x4 Latin/permutation placements.  Every recipe 0..15 occurs exactly
# once per quadrant, which prevents a single edge/centre position becoming the
# recipe identity.
_PERMUTATIONS = (
    tuple(range(16)),
    tuple(((r * 4 + c + r) % 4) + r * 4 for r in range(4) for c in range(4)),
    tuple((((r + c) % 4) * 4 + c) for r in range(4) for c in range(4)),
    tuple((15 - (r * 4 + c)) for r in range(4) for c in range(4)),
)


def recipe_at_cell() -> tuple[int, ...]:
    cells = [0] * 64
    for quadrant, (row0, col0) in enumerate(((0, 0), (0, 4), (4, 0), (4, 4))):
        perm = _PERMUTATIONS[quadrant]
        if sorted(perm) != list(range(16)):
            raise ValueError("quadrant mapping is not a permutation")
        for local in range(16):
            row, col = divmod(local, 4)
            cells[(row0 + row) * 8 + col0 + col] = perm[local]
    if any(cells.count(recipe) != 4 for recipe in range(16)):
        raise ValueError("each recipe must have exactly four positions")
    return tuple(cells)


RECIPE_AT_CELL = recipe_at_cell()
GLOBAL_HEADERS: tuple[str | None, ...] = (
    None,
    "active",
    "commented",
    "active",
    None,
    "active",
    "commented",
    "active",
)
ROLES = (
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
    "PAGE1_ACTIVE_SOURCE_ANCHORS_3_7",
    "PAGE1_COMMENTED_MIDDLE_CODES_0_7",
    "PAGE1_ACTIVE_TARGET_CODE3",
    "FACTORY_OTP_WHITE_PAGE_SEPARATOR",
    "PAGE2_ACTIVE_SOURCE_ANCHORS_3_7",
    "PAGE2_COMMENTED_MIDDLE_CODES_0_7",
    "PAGE2_ACTIVE_TARGET_CODE7",
)
DRIVER_ROLES = (
    "FactoryWhite",
    "Source",
    "Mid",
    "Target",
    "FactoryWhite",
    "Source",
    "Mid",
    "ReverseSource",
)


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    return (
        GRID_X0 + column * (CELL_WIDTH + GAP_X),
        GRID_Y0 + row * (CELL_HEIGHT + GAP_Y),
        CELL_WIDTH,
        CELL_HEIGHT,
    )


def _set_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    x, y, width, height = _cell_bounds(row, column)
    x += controller * base.CONTROLLER_WIDTH
    pair = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + x // 2
        frame[start : start + width // 2] = bytes([pair]) * (width // 2)


def _grid_frame(stage: str, target: int = 3) -> bytes:
    frame = bytearray([(SEPARATOR_CODE << 4) | SEPARATOR_CODE]) * (
        base.WIDTH * base.HEIGHT // 2
    )
    for controller in (0, 1):
        for cell, recipe in enumerate(RECIPE_AT_CELL):
            row, column = divmod(cell, 8)
            if stage == "source":
                code = SOURCE_ANCHOR_CODES[recipe // 8]
            elif stage == "middle":
                code = recipe % 8
            elif stage == "target":
                code = target
            else:
                raise ValueError("unknown stage")
            _set_cell(frame, controller, row, column, code)
    return bytes(frame)


def _factory_white_frame() -> bytes:
    return bytes([FACTORY_WHITE_FILL_BYTE]) * (base.WIDTH * base.HEIGHT // 2)


def _payload(frame: bytes, controller: int) -> dict[str, Any]:
    return cross.payload_identity(cross.controller_stream(frame, controller))


def recipe_map() -> list[dict[str, Any]]:
    out = []
    for page, target in enumerate(TARGET_CODES, 1):
        for recipe in range(16):
            positions = []
            for cell, value in enumerate(RECIPE_AT_CELL):
                if value == recipe:
                    row, col = divmod(cell, 8)
                    positions.append(
                        {
                            "row": row,
                            "column": col,
                            "local_roi": dict(
                                zip(
                                    ("x", "y", "width", "height"),
                                    _cell_bounds(row, col),
                                    strict=True,
                                )
                            ),
                        }
                    )
            out.append(
                {
                    "recipe_id": f"LG-P{page}-S{SOURCE_ANCHOR_CODES[recipe // 8]}-M{recipe % 8}-T{target}",
                    "page": page,
                    "source": {
                        "global_header": "active",
                        "code": SOURCE_ANCHOR_CODES[recipe // 8],
                        "semantic": "runtime_transport_anchor_not_black_or_white",
                    },
                    "middle": {"global_header": "commented", "code": recipe % 8},
                    "target": {"global_header": "active", "code": target},
                    "positions": positions,
                    "repeats_per_controller": 4,
                    "controller_evaluation": "independent",
                    "spatial_dither": False,
                }
            )
    return out


def build_report() -> dict[str, Any]:
    white = _factory_white_frame()
    source = _grid_frame("source")
    middle = _grid_frame("middle")
    target3 = _grid_frame("target", 3)
    target7 = _grid_frame("target", 7)
    frames = (white, source, middle, target3, white, source, middle, target7)
    actions: list[dict[str, Any]] = []
    prior: str | None = None
    for ordinal, (role, driver_role, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, GLOBAL_HEADERS, frames, strict=True), 1
    ):
        item: dict[str, Any] = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "branch": f"{VARIANT_KEY}_{role}",
            "palette_source": "FACTORY_OTP" if header is None else "L535_RUNTIME",
            "global_header": header,
            "frame": base.frame_identity(frame),
            "cs1_dtm": _payload(frame, 0),
            "cs2_dtm": _payload(frame, 1),
            "prior_static_action_id": prior,
        }
        descriptor = {
            "schema": "mf1750-luma-gray-v1-action-descriptor",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            f"MF1750_LUMA_GRAY_V1|{ordinal}|{item['descriptor_id']}".encode("ascii")
        )
        prior = item["action_id"]
        actions.append(item)

    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    contract = {
        "schema": "mf1750-luma-gray-exploratory-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "requested_factory_otp_black_white_per_cell_source": False,
        "source_model_change": "factory_OTP_per_cell_black_white_not_proven_or_implemented; replaced_by_active_L535_code3_and_code7_transport_anchors",
        "source_anchor_codes": list(SOURCE_ANCHOR_CODES),
        "source_anchor_colour_names_claimed": False,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "candidate_only": True,
        "controller_results_must_be_evaluated_independently": True,
        "controller_colour_equivalence_claimed": False,
        "position_acceptance": {
            "minimum_valid_repeats_per_recipe_per_controller": 4,
            "required_valid_repeats": "4_of_4",
            "max_within_recipe_position_dispersion_p95_delta_e76": 6.6032,
            "camera_relative_gray_candidate_only_without_coplanar_neutral_card": True,
            "gray_candidate_relative_neutral_locus_ab_distance_max": 8.0,
            "gray_candidate_min_repeats_passing": "3_of_4",
            "gray_candidate_lstar_range": [15.0, 85.0],
            "minimum_adjacent_candidate_delta_lstar": 8.0,
            "monotonic_lightness_required_for_level_claim": True,
            "automatic_qualification": False,
        },
        "qualification_stage_not_this_campaign": {
            "relative_neutral_locus_ab_distance_max": 5.0,
            "target_repeat_delta_e76_max": 6.6032,
            "fresh_run_count": 3,
            "observation_times_seconds": [5, 60, 600],
            "qualified_by_this_campaign": False,
        },
        "geometry": {
            "grid_rows": 8,
            "grid_columns_per_controller": 8,
            "recipes_per_page": 16,
            "repeats_per_recipe_per_controller": 4,
            "candidate_cells_per_controller": 64,
            "controller_count": 2,
            "recipe_at_cell": list(RECIPE_AT_CELL),
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "spatial_dither": False,
        },
        "pages": [
            {
                "page": 1,
                "target": {"global_header": "active", "code": 3},
                "recipe_count": 16,
            },
            {
                "page": 2,
                "target": {"global_header": "active", "code": 7},
                "recipe_count": 16,
            },
        ],
        "profiles": profiles,
        "recipes": recipe_map(),
        "global_header_sequence": list(GLOBAL_HEADERS),
        "actions": [
            {
                k: item[k]
                for k in (
                    "ordinal",
                    "role",
                    "driver_role",
                    "branch",
                    "palette_source",
                    "global_header",
                    "descriptor_id",
                    "action_id",
                    "prior_static_action_id",
                )
            }
            for item in actions
        ],
        "factory_otp_white_ordinals": [1, 5],
        "independent_fresh_factory_otp_white_containment_required": True,
        "main_campaign_contains_final_recovery": False,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "spatial_mixing": False,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-v1-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
