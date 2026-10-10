#!/usr/bin/env python3
"""Offline identities for bidirectional 8x8 cross-palette history screens."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402


Direction = Literal["ab", "ba"]
WHITE_CODE = 7
ROW_HEIGHT = 75
COLUMN_WIDTH = 64
PROFILE_ACTIVE = "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
PROFILE_COMMENTED = "LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"


def constants(direction: Direction) -> dict[str, str]:
    suffix = direction.upper()
    return {
        "variant_key": f"L535_CROSS_PALETTE_8X8_{suffix}_V1",
        "build_tag": f"MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_{suffix}_V1_2026-08-23",
        "test_id": f"EC5-RUNTIME-LUT-CROSS-PALETTE-{suffix}-V1",
        "campaign_id": f"EC5_RUNTIME_LUT_CROSS_PALETTE_{suffix}_V1",
        "nvs_namespace": f"rlx535{direction}_v1",
    }


def profile(global_header: str) -> dict[str, Any]:
    if global_header not in ("active", "commented"):
        raise ValueError("unknown global header")
    return {
        "id": PROFILE_ACTIVE if global_header == "active" else PROFILE_COMMENTED,
        "global_header": global_header,
        "global_header_sha256": (
            "48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8"
            if global_header == "active"
            else "473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f"
        ),
        "cs1_r20_prefix_bytes": 535,
        "cs1_r20_prefix_sha256": base.ACTIVE_R20_PREFIX_SHA256,
        "cs2_r20_prefix_bytes": 535,
        "cs2_r20_prefix_sha256": base.COMMENTED_R20_PREFIX_SHA256,
        "r21_bytes": 704,
        "r21_sha256": base.R21_SHA256,
    }


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != base.WIDTH * base.HEIGHT // 2:
        raise ValueError("invalid cross-palette controller stream request")
    row_bytes = base.WIDTH // 2
    half_row_bytes = base.CONTROLLER_WIDTH // 2
    offset = controller * half_row_bytes
    return b"".join(
        frame[y * row_bytes + offset : y * row_bytes + offset + half_row_bytes]
        for y in range(base.HEIGHT)
    )


def payload_identity(data: bytes) -> dict[str, Any]:
    return {
        "bytes": len(data),
        "fnv1a": base.fnv1a(data),
        "sha256": base.sha256(data),
    }


def white_frame() -> bytes:
    return bytes([0x77]) * (base.WIDTH * base.HEIGHT // 2)


def source_rows_frame() -> bytes:
    frame = bytearray(len(white_frame()))
    row_bytes = base.WIDTH // 2
    for y in range(base.HEIGHT):
        code = y // ROW_HEIGHT
        frame[y * row_bytes : (y + 1) * row_bytes] = (
            bytes([(code << 4) | code]) * row_bytes
        )
    return bytes(frame)


def target_columns_frame() -> bytes:
    frame = bytearray(len(white_frame()))
    row_bytes = base.WIDTH // 2
    half_row_bytes = base.CONTROLLER_WIDTH // 2
    row = bytearray(row_bytes)
    for controller in (0, 1):
        offset = controller * half_row_bytes
        for local_byte in range(half_row_bytes):
            local_x = local_byte * 2
            code = local_x // COLUMN_WIDTH
            row[offset + local_byte] = (code << 4) | code
    for y in range(base.HEIGHT):
        frame[y * row_bytes : (y + 1) * row_bytes] = row
    return bytes(frame)


def build_report(direction: Direction) -> dict[str, Any]:
    values = constants(direction)
    source_header = "active" if direction == "ab" else "commented"
    target_header = "commented" if direction == "ab" else "active"
    frames = (
        white_frame(),
        source_rows_frame(),
        target_columns_frame(),
        target_columns_frame(),
        white_frame(),
    )
    roles = (
        "RUNTIME_LUT_WHITE_BASELINE",
        "CROSS_PALETTE_SOURCE_ROWS",
        "CROSS_PALETTE_TARGET_COLUMNS",
        "CROSS_PALETTE_TARGET_REPEAT",
        "RUNTIME_LUT_WHITE_RECOVERY",
    )
    headers = ("active", source_header, target_header, target_header, "active")
    actions: list[dict[str, Any]] = []
    for ordinal, (role, header, frame) in enumerate(zip(roles, headers, frames), 1):
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": f"{values['variant_key']}_{role}_{header.upper()}",
            "global_header": header,
            "profile_id": profile(header)["id"],
            "frame": base.frame_identity(frame),
            "cs1_dtm": payload_identity(controller_stream(frame, 0)),
            "cs2_dtm": payload_identity(controller_stream(frame, 1)),
        }
        descriptor = {
            "schema": "mf1750-runtime-lut-cross-palette-descriptor-v1",
            "variant": values["variant_key"],
            **item,
        }
        item["descriptor_id"] = base.sha256(base.canonical(descriptor))
        item["action_id"] = base.sha256(
            (
                "MF1750_RUNTIME_LUT_CROSS_PALETTE_ACTION_V1|"
                f"{values['variant_key']}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        actions.append(item)

    profiles = {name: profile(name) for name in ("active", "commented")}
    contract = {
        "schema": "mf1750-runtime-lut-cross-palette-contract-v1",
        "direction": direction,
        **values,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "source_rows": 8,
            "source_row_height": ROW_HEIGHT,
            "target_columns_per_controller": 8,
            "target_column_width": COLUMN_WIDTH,
            "history_cells_per_controller": 64,
            "history_cells_total": 128,
            "spatial_dither": False,
        },
        "profiles": profiles,
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "global_header": item["global_header"],
                "profile_id": item["profile_id"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "partial_refresh": False,
        "full_screen_global_refresh": True,
        "cross_palette_hold_probe": True,
        "target_repeat_stability_probe": True,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-cross-palette-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flushed": False,
        "display_refreshed": False,
        **values,
        "direction": direction,
        "contract_id": base.sha256(base.canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(
        json.dumps(
            {direction: build_report(direction) for direction in ("ab", "ba")},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
