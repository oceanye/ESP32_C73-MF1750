#!/usr/bin/env python3
"""Offline identities for the four-action same-R20 controller parity probe.

This module is deliberately offline-only.  It freezes two full-screen 2x4
code atlases and two factory-OTP white frames.  The AA action binds the active
global/PWR/PLL/R20/R21 tuple to both controllers; the CC action binds the
commented tuple to both controllers.  No action is retried, recovered, or
automatically chained.
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


VARIANT_KEY = "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1"
BUILD_TAG = "MF1750_EC5_SAME_R20_PARITY_2X4_V1_2026-08-28"
TEST_ID = "EC5-SAME-R20-PARITY-2X4-V1"
CAMPAIGN_ID = "EC5_SAME_R20_PARITY_2X4_V1"
NVS_NAMESPACE = "sr20p_v1"
NVS_KEY = "cursor_srp1"
NVS_BOOT_KEY = "boot_srp1"
DEVICE_API_VERSION = "MF1750_EC5_SAME_R20_PARITY_DEVICE_V1"
IDENTITY_REVISION = "same-r20-dual-controller-parity-v1"
CLASSIFICATION = "EXPERIMENTAL_SAME_R20_CONTROLLER_PARITY_NOT_COLOUR_QUALIFICATION"
BASE_ROUTE = "/api/ec5/same-r20-parity-v1"
EXTERNAL_WHITE_ANCHOR = {
    "campaign_id": "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_SUCCESSOR",
    "contract_id": "1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227",
    "action_id": "76517f9d6ba090cef2f4f3fd32bcda6a5466b41aeeef5ce31a5520ac1dbbceed",
    "firmware_bin_sha256": "3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb",
    "firmware_elf_sha256": "2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797",
    "required_outcome": "complete_pass",
    "required_clean_white_visual_gate": True,
    "resume_source_campaign": False,
    "evidence_path": (
        ".test-output/hardware/"
        "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_"
        "SUCCESSOR_20260828_V3/action-01-factory-otp-white.json"
    ),
}

FACTORY_WHITE_FILL_BYTE = 0x11
SEPARATOR_CODE = 7
GRID_ROWS = 2
GRID_COLUMNS = 4
GRID_X0 = 40
GRID_Y0 = 120
CELL_WIDTH = 96
CELL_HEIGHT = 120
GAP_X = 20
GAP_Y = 40
GRID_X1_EXCLUSIVE = GRID_X0 + GRID_COLUMNS * CELL_WIDTH + (GRID_COLUMNS - 1) * GAP_X
GRID_Y1_EXCLUSIVE = GRID_Y0 + GRID_ROWS * CELL_HEIGHT + (GRID_ROWS - 1) * GAP_Y

RUNTIME_PSR = bytes((0x5F, 0xE9))
CONTROLLER_TRES = bytes((0x02, 0x00, 0x02, 0x58))
HIDDEN_ENABLE = bytes((0x01,))

_PROFILE_CONSTANTS = {
    "active": {
        "global_header_sha256": "48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8",
        "power_payload_sha256": "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2",
        "pll_payload_sha256": "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986",
        "r20_prefix_sha256": base.ACTIVE_R20_PREFIX_SHA256,
    },
    "commented": {
        "global_header_sha256": "473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f",
        "power_payload_sha256": "e571c5cf13938b4f4e12b7152ef5ac7d4970ca1d7fd5aa5568b3bf5ab5b208c9",
        "pll_payload_sha256": "084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5",
        "r20_prefix_sha256": base.COMMENTED_R20_PREFIX_SHA256,
    },
}

ROLES = (
    "SAME_R20_ACTIVE_ACTIVE_ATLAS",
    "FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE",
    "SAME_R20_COMMENTED_COMMENTED_ATLAS",
    "FACTORY_OTP_WHITE_AFTER_COMMENTED_COMMENTED",
)
DRIVER_ROLES = ("Source", "FactoryWhite", "Mid", "FactoryWhite")
PROFILE_NAMES: tuple[str | None, ...] = ("active", None, "commented", None)
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def profile(name: str) -> dict[str, Any]:
    """Return the exact controller-symmetric runtime tuple identity."""

    if name not in _PROFILE_CONSTANTS:
        raise ValueError("same-R20 profile must be active or commented")
    values = _PROFILE_CONSTANTS[name]
    controller = {
        "r20_command": "0x20",
        "r20_prefix_bytes": 535,
        "r20_prefix_sha256": values["r20_prefix_sha256"],
        "r21_command": "0x21",
        "r21_bytes": 704,
        "r21_sha256": base.R21_SHA256,
    }
    return {
        "id": f"LEGACY_{name.upper()}_HEADER__CS1_{name.upper()}535__CS2_{name.upper()}535",
        "name": name,
        "global_header_sha256": values["global_header_sha256"],
        "runtime_psr_command": "0x00",
        "runtime_psr_bytes": len(RUNTIME_PSR),
        "runtime_psr_sha256": _sha(RUNTIME_PSR),
        "power_command": "0x01",
        "power_payload_bytes": 6,
        "power_payload_sha256": values["power_payload_sha256"],
        "pll_command": "0x30",
        "pll_payload_bytes": 1,
        "pll_payload_sha256": values["pll_payload_sha256"],
        "tres_command": "0x61",
        "tres_bytes": len(CONTROLLER_TRES),
        "tres_sha256": _sha(CONTROLLER_TRES),
        "hidden_enable_command": "0xe9",
        "hidden_enable_bytes": len(HIDDEN_ENABLE),
        "hidden_enable_sha256": _sha(HIDDEN_ENABLE),
        "cs1": dict(controller),
        "cs2": dict(controller),
        "controller_payloads_byte_identical": True,
        "global_tuple_id": _sha(
            _canonical(
                {
                    "name": name,
                    "global_header_sha256": values["global_header_sha256"],
                    "runtime_psr_sha256": _sha(RUNTIME_PSR),
                    "power_payload_sha256": values["power_payload_sha256"],
                    "pll_payload_sha256": values["pll_payload_sha256"],
                    "tres_sha256": _sha(CONTROLLER_TRES),
                    "hidden_enable_sha256": _sha(HIDDEN_ENABLE),
                    "controller": controller,
                }
            )
        ),
    }


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("same-R20 atlas cell outside 2x4 grid")
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
        raise ValueError("same-R20 2x4 atlas violates packed 4bpp bounds")


def _set_controller_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    if controller not in (0, 1) or not 0 <= code <= 7:
        raise ValueError("invalid controller or transport code")
    x, y, width, height = _cell_bounds(row, column)
    global_x = controller * base.CONTROLLER_WIDTH + x
    packed = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + global_x // 2
        frame[start : start + width // 2] = bytes((packed,)) * (width // 2)


def atlas_frame() -> bytes:
    """Return identical code0..7 2x4 DTM content on both controllers."""

    _validate_geometry()
    packed = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray((packed,)) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                _set_controller_cell(
                    frame, controller, row, column, row * GRID_COLUMNS + column
                )
    return bytes(frame)


def factory_white_frame() -> bytes:
    return bytes((FACTORY_WHITE_FILL_BYTE,)) * (base.WIDTH * base.HEIGHT // 2)


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
    return {"bytes": len(data), "fnv1a": base.fnv1a(data), "sha256": _sha(data)}


def build_report() -> dict[str, Any]:
    _validate_geometry()
    atlas = atlas_frame()
    white = factory_white_frame()
    frames = (atlas, white, atlas, white)
    profiles = {name: profile(name) for name in ("active", "commented")}

    actions: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, driver_role, profile_name, branch, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, PROFILE_NAMES, BRANCHES, frames, strict=True), 1
    ):
        cs1 = payload_identity(controller_stream(frame, 0))
        cs2 = payload_identity(controller_stream(frame, 1))
        waveform = profiles[profile_name] if profile_name else None
        item: dict[str, Any] = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "round": 1,
            "branch": branch,
            "palette_source": "L535_RUNTIME" if profile_name else "FACTORY_OTP",
            "global_header": profile_name,
            "profile_id": waveform["id"] if waveform else None,
            "global_tuple_id": waveform["global_tuple_id"] if waveform else None,
            "waveform_binding": waveform,
            "frame": base.frame_identity(frame),
            "cs1_dtm": cs1,
            "cs2_dtm": cs2,
            "controller_dtm_byte_identical": cs1 == cs2,
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
            "schema": "mf1750-same-r20-parity-action-descriptor-v1",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = _sha(_canonical(descriptor))
        item["action_id"] = _sha(
            (
                "MF1750_SAME_R20_PARITY_ACTION_V1|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    contract = {
        "schema": "mf1750-same-r20-parity-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profiles": profiles,
        "external_white_anchor": dict(EXTERNAL_WHITE_ANCHOR),
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "codes": list(range(8)),
            "cell_bounds_by_code": [
                {
                    "code": code,
                    "x": _cell_bounds(code // 4, code % 4)[0],
                    "y": _cell_bounds(code // 4, code % 4)[1],
                    "width": CELL_WIDTH,
                    "height": CELL_HEIGHT,
                }
                for code in range(8)
            ],
            "cs2_position_mirrored": False,
            "same_layout_both_controllers": True,
            "spatial_dither": False,
        },
        "actions": actions,
        "action_count": 4,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "factory_otp_white_ordinals": [2, 4],
        "runtime_lut_ordinals": [1, 3],
        "partial_refresh": False,
        "window_refresh": False,
        "local_hold_claimed": False,
        "controller_bus_capture_claimed": False,
        "controller_payload_source_identity_claimed": True,
        "colour_equivalence_claimed": False,
        "qualified_colours": 0,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-same-r20-parity-offline-identities-v1",
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
        "contract_id": _sha(_canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
