#!/usr/bin/env python3
"""Offline identities for the active-code0 red/pink history screen.

The selected transport code is evidence-bound, not guessed: under the active
global header, the current target-hue catalogue records code 0 as a direct red
endpoint candidate on CS2 and as olive/yellow-green on CS1.  Both controllers
still receive the same 64 source/middle/target recipes so the controller-
specific result remains visible instead of being hidden behind a colour-name
equivalence claim.

Runtime code 7 is only the grid separator/background transport code.  The
health anchor and final recovery are factory-OTP refreshes using the canonical
0x11 frame.  No frame contains spatial dithering.
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


VARIANT_KEY = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2"
BUILD_TAG = (
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_"
    "SINGLE_APP_BOOT_FLASH_VERIFY_V2_2026-08-27"
)
TEST_ID = "EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V2"
CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2"
NVS_NAMESPACE = "rlhbrp_v2"
NVS_KEY = "cursor_rpb2"
NVS_BOOT_KEY = "boot_rpb2"
PROFILE_ACTIVE = cross.PROFILE_ACTIVE
PROFILE_COMMENTED = cross.PROFILE_COMMENTED
PROFILE_ID = (
    "ACTIVE_SOURCE_TO_COMMENTED_MIDDLE_TO_ACTIVE_CODE0_TARGET__"
    "CS1_ACTIVE535__CS2_COMMENTED535"
)
TARGET_HUE_ID = (
    "ACTIVE_CODE0_CS2_RED_CS1_OLIVE_YELLOWGREEN_CONTROLLER_SPECIFIC_UNCALIBRATED"
)
TARGET_CODE = 0
SEPARATOR_CODE = 7
FACTORY_WHITE_FILL_BYTE = 0x11
TARGET_HUE_CATALOG_ID = (
    "94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8"
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

GLOBAL_HEADERS: tuple[str | None, ...] = (
    None,
    "active",
    "commented",
    "active",
    "active",
    None,
)
ROLES = (
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
    "REDPINK_SOURCE_GRID_ACTIVE",
    "REDPINK_MIDDLE_GRID_COMMENTED",
    "REDPINK_FIXED_TARGET_ACTIVE_CODE0",
    "REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0",
    "FACTORY_OTP_WHITE_RECOVERY",
)
DRIVER_ROLES = (
    "FactoryWhite",
    "Source",
    "Mid",
    "Target",
    "Target",
    "FactoryWhite",
)
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("red/pink brightness cell outside 8x8 grid")
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
        raise ValueError("red/pink grid violates packed 4bpp bounds")
    rectangles = [_cell_bounds(row, col) for row in range(8) for col in range(8)]
    for index, left in enumerate(rectangles):
        lx, ly, lw, lh = left
        for rx, ry, rw, rh in rectangles[index + 1 :]:
            if not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly):
                raise ValueError("red/pink brightness cells overlap")


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
        raise ValueError("unknown red/pink brightness stage")
    separator_pair = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray([separator_pair]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                code = column if stage == "source" else row
                if stage == "target":
                    code = TARGET_CODE
                _set_controller_cell(frame, controller, row, column, code)
    return bytes(frame)


def _factory_white_frame() -> bytes:
    return bytes([FACTORY_WHITE_FILL_BYTE]) * (base.WIDTH * base.HEIGHT // 2)


def _controller_stream(frame: bytes, controller: int) -> bytes:
    return cross.controller_stream(frame, controller)


def _payload_identity(data: bytes) -> dict[str, Any]:
    return cross.payload_identity(data)


def recipe_map() -> list[dict[str, Any]]:
    """Return the immutable 64-recipe map repeated on both controllers."""

    return [
        {
            "recipe_id": f"REDPINK-A{column}-B{row}-A{TARGET_CODE}",
            "row": row,
            "column": column,
            "local_roi": dict(
                zip(
                    ("x", "y", "width", "height"),
                    _cell_bounds(row, column),
                    strict=True,
                )
            ),
            "source": {"global_header": "active", "code": column},
            "middle": {"global_header": "commented", "code": row},
            "target": {"global_header": "active", "code": TARGET_CODE},
            "target_repeat": {"global_header": "active", "code": TARGET_CODE},
            "target_repeat_count": 2,
            "controller_repeats": [
                {
                    "controller": controller,
                    "profile_sequence": ["active", "commented", "active", "active"],
                    "source_code": column,
                    "middle_code": row,
                    "target_code": TARGET_CODE,
                    "repeat_count": 2,
                    "mirrored": False,
                }
                for controller in (0, 1)
            ],
            "spatial_dither": False,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]


def build_report() -> dict[str, Any]:
    """Build immutable frames, actions, and contract without device access."""

    _validate_geometry()
    factory_white = _factory_white_frame()
    source = _grid_frame("source")
    middle = _grid_frame("middle")
    target = _grid_frame("target")
    frames = (factory_white, source, middle, target, target, factory_white)

    actions: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True), 1
    ):
        factory_otp = header is None
        boot_admission = {
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
        }
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
            "boot_admission": boot_admission,
        }
        descriptor = {
            "schema": "mf1750-target-hue-redpink-brightness-action-descriptor-v3",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_ACTION_V2|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    recipes = recipe_map()
    contract = {
        "schema": "mf1750-target-hue-redpink-brightness-history-contract-v2",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile_id": PROFILE_ID,
        "target_hue_registry": {
            "selected": TARGET_HUE_ID,
            "target_global_header": "active",
            "target_transport_code": TARGET_CODE,
            "selection_not_guess": True,
            "target_hue_catalog_id": TARGET_HUE_CATALOG_ID,
            "selection_basis": [
                "catalog_R_direct_endpoint_candidate_CS2_active_code0_red",
                "STATUS_confirmed_visual_base_group_red",
                "active_L535_pure_field_atlas_CS2_code0_visual_red_candidate",
            ],
            "rejected_inference": (
                "factory_OTP_atlas_code3_red_and_code3_plus_code1_spatial_light_pink "
                "do_not_transfer_to_runtime_L535_transport semantics"
            ),
            "pink_candidates_not_selected": {
                "active_code1_CS2": "light_pink_search_seed_only",
                "active_code2_CS2": "salmon_multiple_uncalibrated_candidate",
            },
            "controller_observations": [
                {
                    "controller": 0,
                    "provisional_visual_name": "olive/yellow-green",
                    "evidence": "visual-candidate",
                    "colorimetrically_calibrated": False,
                },
                {
                    "controller": 1,
                    "provisional_visual_name": "red",
                    "evidence": "direct-endpoint-visual-candidate",
                    "colorimetrically_calibrated": False,
                },
            ],
            "controller_color_equivalence_claimed": False,
            "shared_red_or_pink_hue_claimed": False,
            "qualified_brightness_levels": 0,
        },
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "candidate_cells_per_controller": GRID_ROWS * GRID_COLUMNS,
            "candidate_cells_total_observations": 2 * GRID_ROWS * GRID_COLUMNS,
            "unique_recipes": GRID_ROWS * GRID_COLUMNS,
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
            "spatial_dither": False,
        },
        "axis_mapping": {
            "row": "commented_middle_code_0_to_7",
            "column": "active_source_code_0_to_7",
            "fixed_target": "active_code_0",
            "recipe": "active_source(column)->commented_middle(row)->active_target(code0)",
            "horizontal_comparison_group": (
                "eight adjacent source histories share one middle and fixed target code0"
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
                "prior_static_action_id": item["prior_static_action_id"],
                "boot_admission": item["boot_admission"],
            }
            for item in actions
        ],
        "factory_otp_white": {
            "ordinals": [1, 6],
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
        "history_brightness_screening": True,
        "target_repeat_stability_probe": True,
        "brightness_candidates_only": True,
        "qualified_brightness_levels": 0,
        "human_observation_gate_after_every_action": True,
        "target_repeat_decision": {
            "ordinal": 5,
            "separate_action": True,
            "ordinal4_clear_visible_hit_required": True,
            "operator_decision_required_before_arm": True,
            "automatic_dispatch": False,
            "skip_within_main_campaign_allowed": False,
            "ordinal4_no_visible_difference": (
                "seal_main_campaign_without_ordinals_5_or_6_then_relay_off_and_use_"
                "fresh_redpink_factory_otp_white_containment"
            ),
            "ordinal4_clear_visible_hit": (
                "operator_may_arm_ordinal5_repeat_then_only_after_acceptance_arm_"
                "ordinal6_main_factory_otp_white_recovery"
            ),
            "reason": "fail_closed_cursor_has_no_reviewed_skip_transition",
        },
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required_for_every_ordinal": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "strict_ordinal_progression": {
            "terminal_next_ordinal": 7,
            "same_boot_prior_complete_required": True,
            "device_enforced_same_boot": True,
            "campaign_boot_nonce_persisted_before_any_action": True,
            "campaign_boot_binding_key": NVS_BOOT_KEY,
            "arm_boot_binding_gate": True,
            "execute_boot_binding_gate": True,
            "dispatch_boot_binding_gate": True,
            "direct_exact_post_resume_after_reboot": False,
            "main_campaign_resume_after_containment": False,
            "skip_to_factory_white_allowed": False,
            "action6_requires_action5_complete": True,
            "if_target_repeat_declined": (
                "seal_main_campaign_and_use_a_separately_reviewed_factory_OTP_containment"
            ),
        },
        "boot_session_admission": {
            "schema": "mf1750-persisted-campaign-boot-binding-v1",
            "namespace": NVS_NAMESPACE,
            "cursor_key": NVS_KEY,
            "campaign_boot_key": NVS_BOOT_KEY,
            "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
            "initialize_only_when_cursor_key_absent_ready_ordinal1": True,
            "initialize_before_any_action": True,
            "readback_required": True,
            "current_boot_exact_match_required": True,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "boot_mismatch_fault_locked": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        },
        "ordinal4_fast_gate": {
            "observation_required": True,
            "if_no_visible_difference": {
                "seal_main_campaign": True,
                "arm_ordinal5": False,
                "arm_ordinal6": False,
                "relay_off_before_containment": True,
                "next_firmware": (
                    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT"
                ),
                "resume_main_after_containment": False,
                "then_continue_next_target": True,
            },
            "if_clear_visible_hit": {
                "operator_may_arm_ordinal5_repeat": True,
                "ordinal6_main_white_only_after_repeat_accepted": True,
            },
        },
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-target-hue-redpink-brightness-history-v2-offline-identities",
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
        "target_hue_id": TARGET_HUE_ID,
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
