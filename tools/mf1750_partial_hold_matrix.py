#!/usr/bin/env python3
"""Generate immutable identities for the MF-1750 PTLW HOLD campaigns.

This module is intentionally offline-only.  It has no serial, network, GPIO,
relay, flashing, reset, or display-refresh surface.  The generated fixtures
use factory-OTP colour codes and the fixed 1024x600 / dual-512x600 geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


WIDTH = 1024
HEIGHT = 600
CONTROLLER_WIDTH = 512
WHITE = 1
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193


@dataclass(frozen=True)
class Window:
    x: int
    y: int
    width: int
    height: int
    cs1_code: int
    cs2_code: int


@dataclass(frozen=True)
class Variant:
    index: int
    key: str
    description: str
    windows: tuple[Window, Window, Window]


VARIANTS = (
    Variant(
        0,
        "ACCUMULATE_OVERWRITE",
        "two disjoint windows followed by a nested overwrite",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 5, 5),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
    Variant(
        1,
        "EDGE_GEOMETRY",
        "left edge, right edge, and lower safe-bound windows",
        (
            Window(0, 32, 128, 128, 2, 2),
            Window(384, 232, 128, 128, 5, 5),
            Window(192, 440, 128, 144, 3, 3),
        ),
    ),
    Variant(
        2,
        "DUAL_CS_SPLIT",
        "matched windows with different fixed codes on CS1 and CS2",
        (
            Window(64, 64, 160, 128, 3, 5),
            Window(288, 236, 160, 128, 2, 6),
            Window(112, 408, 288, 128, 0, 3),
        ),
    ),
    Variant(
        3,
        "ACCUMULATE_VMIRROR",
        "CS1 original windows and CS2 vertically mirrored windows",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 5, 5),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
    Variant(
        4,
        "ACCUMULATE_SYMMETRIC_V2",
        "matched CS1/CS2 windows with separate 0x83 programming",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 5, 5),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
    Variant(
        5,
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE",
        "symmetric separate-CS control with y_end=y+h-1",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 5, 5),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
    Variant(
        6,
        "ACCUMULATE_SYMMETRIC_BLUE1",
        "symmetric separate-CS control with PATCH_B code4 Blue-1",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 4, 4),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
    Variant(
        7,
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1",
        "y-inclusive symmetric control with PATCH_B code4 Blue-1",
        (
            Window(48, 96, 160, 144, 3, 3),
            Window(304, 336, 160, 144, 4, 4),
            Window(80, 128, 96, 80, 6, 6),
        ),
    ),
)


def fnv1a(data: bytes) -> int:
    value = FNV_OFFSET
    for byte in data:
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFF
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def validate_window(window: Window) -> None:
    if window.x < 0 or window.y < 0:
        raise ValueError("negative PTLW coordinate")
    if window.width <= 0 or window.height <= 0:
        raise ValueError("empty PTLW window")
    if window.x % 2 or window.width % 2:
        raise ValueError("PTLW DTM must be packed-byte aligned")
    if window.x + window.width > CONTROLLER_WIDTH:
        raise ValueError("PTLW window exceeds controller width")
    # The cross-checked adjacent implementation sends ye=y+h (one more), so
    # keep that encoded value inside the 0..599 controller range.
    if window.y + window.height >= HEIGHT:
        raise ValueError("PTLW y+h one-more endpoint exceeds controller")
    if not 0 <= window.cs1_code <= 7 or not 0 <= window.cs2_code <= 7:
        raise ValueError("transport code outside 0..7")


def set_rect(
    frame: bytearray, window: Window, *, cs2_vertical_mirror: bool = False
) -> None:
    row_bytes = WIDTH // 2
    for controller, code in ((0, window.cs1_code), (1, window.cs2_code)):
        packed = (code << 4) | code
        x = controller * CONTROLLER_WIDTH + window.x
        y_start = (
            HEIGHT - (window.y + window.height)
            if controller == 1 and cs2_vertical_mirror
            else window.y
        )
        for y in range(y_start, y_start + window.height):
            start = y * row_bytes + x // 2
            frame[start : start + window.width // 2] = bytes([packed]) * (
                window.width // 2
            )


def histogram(frame: bytes) -> list[int]:
    result = [0] * 8
    for byte in frame:
        result[byte >> 4] += 1
        result[byte & 0x0F] += 1
    return result


def dtm_identity(window: Window | None, second: bool) -> dict[str, Any]:
    if window is None:
        data = bytes([0x11]) * (CONTROLLER_WIDTH * HEIGHT // 2)
    else:
        code = window.cs2_code if second else window.cs1_code
        data = bytes([(code << 4) | code]) * (
            window.width * window.height // 2
        )
    return {"bytes": len(data), "fnv1a": fnv1a(data), "sha256": sha256(data)}


def build_variant(variant: Variant) -> dict[str, Any]:
    for window in variant.windows:
        validate_window(window)
    cs2_vertical_mirror = variant.key == "ACCUMULATE_VMIRROR"
    # VMIRROR already used separate CS commands in its sealed V1 contract.
    # Only the new symmetric control needs this extra differentiating field.
    separate_cs_window_commands = variant.key in {
        "ACCUMULATE_SYMMETRIC_V2",
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE",
        "ACCUMULATE_SYMMETRIC_BLUE1",
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1",
    }
    ptlw_y_end_one_more = variant.key not in {
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE",
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1",
    }
    frame = bytearray([0x11]) * (WIDTH * HEIGHT // 2)
    roles: list[dict[str, Any]] = []
    role_names = ("WHITE_BASELINE", "PATCH_A", "PATCH_B", "PATCH_C")
    for role_index, role_name in enumerate(role_names):
        window = None if role_index == 0 else variant.windows[role_index - 1]
        if window is not None:
            set_rect(
                frame,
                window,
                cs2_vertical_mirror=cs2_vertical_mirror,
            )
        frame_bytes = bytes(frame)
        item = {
            "role_index": role_index,
            "role": role_name,
            "window": (
                {
                    **asdict(window),
                    **(
                        {
                            "cs2_y": HEIGHT - (window.y + window.height),
                            "cs2_vertical_mirror": True,
                        }
                        if cs2_vertical_mirror
                        else {}
                    ),
                }
                if window
                else None
            ),
            "frame": {
                "bytes": len(frame_bytes),
                "fnv1a": fnv1a(frame_bytes),
                "sha256": sha256(frame_bytes),
                "histogram": histogram(frame_bytes),
            },
            "cs1_dtm": dtm_identity(window, False),
            "cs2_dtm": dtm_identity(window, True),
        }
        descriptor_payload = {
            "schema": "mf1750-partial-hold-descriptor-v1",
            "variant": variant.key,
            **item,
        }
        item["descriptor_id"] = sha256(canonical(descriptor_payload))
        item["action_id"] = sha256(
            (
                "MF1750_PARTIAL_HOLD_ACTION_V1|"
                f"{variant.key}|{role_index + 1}|{item['descriptor_id']}"
            ).encode()
        )
        roles.append(item)

    white = roles[0]
    recovery = {
        **white,
        "role": "WHITE_RECOVERY",
        "role_index": 0,
        "descriptor_id": sha256(
            canonical(
                {
                    "schema": "mf1750-partial-hold-descriptor-v1",
                    "variant": variant.key,
                    "role": "WHITE_RECOVERY",
                    "frame": white["frame"],
                    "cs1_dtm": white["cs1_dtm"],
                    "cs2_dtm": white["cs2_dtm"],
                }
            )
        ),
    }
    recovery["action_id"] = sha256(
        (
            "MF1750_PARTIAL_HOLD_ACTION_V1|"
            f"{variant.key}|5|{recovery['descriptor_id']}"
        ).encode()
    )
    roles.append(recovery)
    contract_payload = {
        "schema": "mf1750-partial-hold-contract-v1",
        "variant": {
            **asdict(variant),
            **(
                {"cs2_vertical_mirror": True}
                if cs2_vertical_mirror
                else {}
            ),
            **(
                {"separate_cs_window_commands": True}
                if separate_cs_window_commands
                else {}
            ),
            **(
                {"ptlw_y_end_one_more": False}
                if not ptlw_y_end_one_more
                else {}
            ),
        },
        "actions": [
            {
                "ordinal": index + 1,
                "role": role["role"],
                "descriptor_id": role["descriptor_id"],
                "action_id": role["action_id"],
            }
            for index, role in enumerate(roles)
        ],
        "command": "0x83",
        "payload_bytes": 9,
        "factory_otp": True,
        "runtime_lut": False,
        "camera": False,
        "autochain": False,
        "retry": False,
    }
    return {
        "variant": {
            **asdict(variant),
            **(
                {"cs2_vertical_mirror": True}
                if cs2_vertical_mirror
                else {}
            ),
            **(
                {"separate_cs_window_commands": True}
                if separate_cs_window_commands
                else {}
            ),
            **(
                {"ptlw_y_end_one_more": False}
                if not ptlw_y_end_one_more
                else {}
            ),
        },
        "contract_id": sha256(canonical(contract_payload)),
        "actions": roles,
    }


def build_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-partial-hold-offline-fixture-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flushed": False,
        "display_refreshed": False,
        "variants": [build_variant(variant) for variant in VARIANTS],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build_report(),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
