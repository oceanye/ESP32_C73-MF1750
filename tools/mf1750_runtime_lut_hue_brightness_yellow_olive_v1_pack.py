#!/usr/bin/env python3
"""Offline identities for the first target-hue brightness-history ladder.

Each controller repeats the same 8x8 recipe grid. Column selects the active
profile source code, row selects the commented profile middle code, and every
cell then receives active-profile transport code 2 as the fixed candidate.
Cells are spatially uniform; runtime code 7 is only a separator/background,
never a white claim. Both visible white actions use factory OTP.
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
    mf1750_runtime_lut_hue_brightness_yellow_olive_v1_white_containment_pack as containment,
)


VARIANT_KEY = "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1"
BUILD_TAG = "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_8X8_ABA_V1_2026-08-26"
TEST_ID = "EC5-TARGET-HUE-YELLOW-OLIVE-BRIGHTNESS-8X8-ABA-V1"
CAMPAIGN_ID = "EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_8X8_ABA_V1"
NVS_NAMESPACE = "rlhyob_v1"
NVS_KEY = "cursor_yob1"
BOOT_BINDING_NVS_KEY = "boot_yob1"
PROFILE_ACTIVE = cross.PROFILE_ACTIVE
PROFILE_COMMENTED = cross.PROFILE_COMMENTED
PROFILE_ID = (
    "FACTORY_WHITE_TO_ACTIVE_SOURCE_TO_COMMENTED_MIDDLE_TO_ACTIVE_CODE2_TARGET__"
    "CS1_ACTIVE535__CS2_COMMENTED535"
)
TARGET_HUE_ID = "Y_ACTIVE_CODE2_CS1_YELLOW_OLIVE_CANDIDATE_UNCALIBRATED"
TARGET_HUE_CATALOG_ID = (
    "94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8"
)
TARGET_HUE_CATALOG_SOURCE = "host/extended_color/mf1750_target_hues.py"
TARGET_CODE = 2
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
    "YELLOW_OLIVE_LADDER_SOURCE_GRID_ACTIVE",
    "YELLOW_OLIVE_LADDER_MIDDLE_GRID_COMMENTED",
    "YELLOW_OLIVE_LADDER_FIXED_TARGET_ACTIVE_CODE2",
    "YELLOW_OLIVE_LADDER_FIXED_TARGET_REPEAT_ACTIVE_CODE2",
    "FACTORY_OTP_WHITE_RECOVERY",
)
DRIVER_ROLES = ("FactoryWhite", "Source", "Mid", "Target", "Target", "FactoryWhite")
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("brightness ladder cell outside 8x8 grid")
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
        raise ValueError("brightness ladder geometry violates packed 4bpp bounds")
    rectangles = [_cell_bounds(row, column) for row in range(8) for column in range(8)]
    for index, left in enumerate(rectangles):
        lx, ly, lw, lh = left
        for rx, ry, rw, rh in rectangles[index + 1 :]:
            if not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly):
                raise ValueError("brightness ladder cells overlap")


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
        raise ValueError("unknown brightness ladder stage")
    separator_pair = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray([separator_pair]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                # Eight source histories for the same target are adjacent in
                # every row, which keeps the first visual comparison local.
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
    """Return the immutable per-controller cell recipe map."""

    return [
        {
            "recipe_id": f"YELLOW_OLIVE-A{column}-B{row}-A{TARGET_CODE}",
            "row": row,
            "column": column,
            "local_roi": {
                "x": _cell_bounds(row, column)[0],
                "y": _cell_bounds(row, column)[1],
                "width": CELL_WIDTH,
                "height": CELL_HEIGHT,
            },
            "source": {"global_header": "active", "code": column},
            "middle": {"global_header": "commented", "code": row},
            "target": {"global_header": "active", "code": TARGET_CODE},
            "target_repeat": {"global_header": "active", "code": TARGET_CODE},
            "target_repeat_count": 2,
            "controller_repeats": [
                {
                    "controller": 0,
                    "profile_sequence": ["active", "commented", "active", "active"],
                    "source_code": column,
                    "middle_code": row,
                    "target_code": TARGET_CODE,
                    "repeat_count": 2,
                    "mirrored": False,
                },
                {
                    "controller": 1,
                    "profile_sequence": ["active", "commented", "active", "active"],
                    "source_code": column,
                    "middle_code": row,
                    "target_code": TARGET_CODE,
                    "repeat_count": 2,
                    "mirrored": False,
                },
            ],
            "spatial_dither": False,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]


def build_report() -> dict[str, Any]:
    """Build all frame/action identities without device or network access."""

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
            "device_same_boot_binding_required": True,
            "boot_binding_nvs_key": BOOT_BINDING_NVS_KEY,
            "boot_binding_gate_points": ["arm", "execute", "dispatch"],
            "negative_observation_seals_campaign": ordinal == 4,
            "visible_candidate_confirmation_required": ordinal == 5,
            "main_resume_after_containment": False,
        }
        descriptor = {
            "schema": "mf1750-target-hue-brightness-action-descriptor-v2",
            "variant": VARIANT_KEY,
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_TARGET_HUE_BRIGHTNESS_ACTION_V2|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    recipes = recipe_map()
    contract = {
        "schema": "mf1750-target-hue-brightness-history-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "boot_binding_nvs_key": BOOT_BINDING_NVS_KEY,
        "target_hue_registry": {
            "selected": TARGET_HUE_ID,
            "catalog_id": TARGET_HUE_CATALOG_ID,
            "catalog_source": TARGET_HUE_CATALOG_SOURCE,
            "target_global_header": "active",
            "target_transport_code": TARGET_CODE,
            "evidence_level": "visual-candidate-not-colorimetrically-calibrated",
            "qualified_hue_name": None,
            "qualified_brightness_levels": 0,
            "controller_observations": [
                {
                    "controller": 0,
                    "controller_name": "CS1",
                    "provisional_visual_name": "yellow/olive-yellow",
                    "catalog_evidence": "Y seed CS1 active/code2 黄/橄榄黄",
                    "colorimetrically_calibrated": False,
                },
                {
                    "controller": 1,
                    "controller_name": "CS2",
                    "provisional_visual_name": "salmon-pink",
                    "catalog_evidence": "RO seed CS2 active/code2 鲑粉",
                    "colorimetrically_calibrated": False,
                },
            ],
            "controller_color_equivalence_claimed": False,
            "selection_rationale": (
                "code2 is the catalogue's sole direct Y seed on CS1 and the "
                "planning table labels it 黄/橄榄黄; code0/code4 are broader YG "
                "alternatives, so neither is substituted"
            ),
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
            "fixed_target": f"active_code_{TARGET_CODE}",
            "recipe": (
                "active_source(column)->commented_middle(row)->active_target(code2)"
            ),
            "horizontal_comparison_group": (
                "eight adjacent source histories share one middle code and target code2"
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
                "device_same_boot_binding_required": item[
                    "device_same_boot_binding_required"
                ],
                "boot_binding_nvs_key": item["boot_binding_nvs_key"],
                "boot_binding_gate_points": item["boot_binding_gate_points"],
                "negative_observation_seals_campaign": item[
                    "negative_observation_seals_campaign"
                ],
                "visible_candidate_confirmation_required": item[
                    "visible_candidate_confirmation_required"
                ],
                "main_resume_after_containment": item["main_resume_after_containment"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": True,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "spatial_dither": False,
        "history_brightness_screening": True,
        "busy_qualified_arm_execute_dispatch": True,
        "device_enforced_same_boot": {
            "binding": "uint64_first_fresh_setup_boot_nonce",
            "nvs_namespace": NVS_NAMESPACE,
            "nvs_key": BOOT_BINDING_NVS_KEY,
            "initialize_only_when": (
                "cursor_key_absent_and_ready_ordinal1_before_network_routes"
            ),
            "gate_points": ["setup", "arm", "execute", "dispatch"],
            "reboot_policy": "fault_lock_before_epd_begin_or_any_panel_io",
            "missing_or_mismatch_policy": "terminal_fault_no_retry_no_resume",
            "containment_then_main_policy": (
                "preserved_main_boot_binding_mismatch_fault_locks_reflashed_main"
            ),
        },
        "brightness_candidates_only": True,
        "qualified_brightness_levels": 0,
        "target_repeat_stability_probe": True,
        "factory_otp_white": {
            "ordinals": [1, 6],
            "frame_fill_byte": "0x11",
            "runtime_code7_used_as_white": False,
            "health_anchor": True,
            "recovery": True,
        },
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "strict_ordinal_progression": {
            "terminal_next_ordinal": 7,
            "skip_to_white_recovery_allowed": False,
            "action6_requires_action5_complete": True,
            "ordinal4_human_gate": {
                "no_clear_same_row_same_target_difference": (
                    "seal_main_skip_ordinals5_and6_then_fresh_containment"
                ),
                "clear_candidate": "allow_ordinal5_repeat_after_explicit_confirmation",
                "relay_off_before_containment_flash": True,
                "negative_seal_main_resume": False,
            },
            "ordinal5_requires_visible_candidate_confirmation": True,
            "failure_containment": {
                "kind": "independent_fresh_identity_factory_otp_white",
                "source_campaign_id": containment.SOURCE_CAMPAIGN_ID,
                "test_id": containment.TEST_ID,
                "campaign_id": containment.CAMPAIGN_ID,
                "contract_id": containment.CONTRACT_ID,
                "platformio_config": (
                    "platformio.runtime_lut_hue_brightness_yellow_olive_v1_"
                    "white_containment.ini"
                ),
                "runner": (
                    "tools/mf1750_runtime_lut_hue_brightness_yellow_olive_v1_"
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
                "required_after_any_visual_or_terminal_failure": True,
                "main_campaign_resume_after_containment": False,
                "main_campaign_resume_device_blocked_by_boot_binding": True,
            },
        },
        "artifact_identity_boundary": {
            "device_running_app_elf_sha256_source": (
                "esp_ota_get_app_description.app_elf_sha256"
            ),
            "host_requires_running_app_elf_sha256_equals_reviewed_elf": True,
            "host_verifies_local_bin_and_elf_before_device_access": True,
            "device_reports_complete_dependency_manifest": False,
            "complete_dependency_claim": None,
            "dependency_evidence_scope": (
                "separate_offline_platformio_config_resolved_packages_and_link_map"
            ),
        },
        "white_gutter_history_interaction": (
            "not_qualified; judge candidate colour from each uniform cell interior, "
            "never from gutter, boundary, or adjacent-strip blending"
        ),
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-target-hue-yellow-olive-brightness-history-v1-offline-identities",
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
        "boot_binding_nvs_key": BOOT_BINDING_NVS_KEY,
        "target_hue_id": TARGET_HUE_ID,
        "target_hue_catalog_id": TARGET_HUE_CATALOG_ID,
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
