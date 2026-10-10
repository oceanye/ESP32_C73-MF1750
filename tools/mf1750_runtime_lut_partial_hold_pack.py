#!/usr/bin/env python3
"""Build immutable identities for the L535 runtime-LUT + PTLW HOLD probe.

Offline-only: this module has no serial, network, relay, reset, flashing, or
display-refresh surface.  It freezes the exact successful active-header 535
profile, three disjoint inclusive PTLW windows, and five one-shot actions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


WIDTH = 1024
HEIGHT = 600
CONTROLLER_WIDTH = 512
WHITE_CODE = 3
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193

VARIANT_KEY = "L535_ACTIVE_GLOBAL_DISJOINT_Y_INCLUSIVE"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V1_2026-08-22"
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V1"
NVS_NAMESPACE = "rlph_l535a_v1"
PROFILE_ID = "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
ACTIVE_R20_PREFIX_SHA256 = (
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
)
COMMENTED_R20_PREFIX_SHA256 = (
    "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"
)
R21_SHA256 = (
    "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
)


@dataclass(frozen=True)
class Window:
    x: int
    y: int
    width: int
    height: int
    cs1_code: int
    cs2_code: int


WINDOWS = (
    Window(48, 64, 160, 120, 0, 0),
    Window(304, 240, 160, 120, 5, 5),
    Window(48, 416, 160, 120, 6, 6),
)

ROLES = (
    "RUNTIME_LUT_WHITE_BASELINE",
    "PATCH_A",
    "PATCH_B",
    "PATCH_C",
    "RUNTIME_LUT_WHITE_RECOVERY",
)

BRANCHES = (
    "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE3",
    "L535_ACTIVE_GLOBAL_PTLW_CODE0_A",
    "L535_ACTIVE_GLOBAL_PTLW_CODE5_B_HOLD_A",
    "L535_ACTIVE_GLOBAL_PTLW_CODE6_C_HOLD_AB",
    "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE3_RECOVERY",
)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fnv1a(data: bytes) -> int:
    value = FNV_OFFSET
    for byte in data:
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFF
    return value


def validate_window(window: Window) -> None:
    if window.x < 0 or window.y < 0:
        raise ValueError("negative PTLW coordinate")
    if window.width <= 0 or window.height <= 0:
        raise ValueError("empty PTLW window")
    if window.x % 2 or window.width % 2:
        raise ValueError("packed DTM requires even x and width")
    if window.x + window.width > CONTROLLER_WIDTH:
        raise ValueError("PTLW window exceeds controller width")
    if window.y + window.height > HEIGHT:
        raise ValueError("PTLW inclusive window exceeds controller height")
    if not 0 <= window.cs1_code <= 7 or not 0 <= window.cs2_code <= 7:
        raise ValueError("transport code outside 0..7")


def set_rect(frame: bytearray, window: Window) -> None:
    row_bytes = WIDTH // 2
    for controller, code in ((0, window.cs1_code), (1, window.cs2_code)):
        packed = (code << 4) | code
        global_x = controller * CONTROLLER_WIDTH + window.x
        row = bytes([packed]) * (window.width // 2)
        for y in range(window.y, window.y + window.height):
            start = y * row_bytes + global_x // 2
            frame[start : start + len(row)] = row


def histogram(frame: bytes) -> list[int]:
    result = [0] * 8
    for value in frame:
        result[value >> 4] += 1
        result[value & 0x0F] += 1
    return result


def uniform_identity(code: int, byte_count: int) -> dict[str, Any]:
    packed = (code << 4) | code
    data = bytes([packed]) * byte_count
    return {
        "bytes": len(data),
        "fnv1a": fnv1a(data),
        "sha256": sha256(data),
    }


def frame_identity(frame: bytes) -> dict[str, Any]:
    return {
        "bytes": len(frame),
        "fnv1a": fnv1a(frame),
        "sha256": sha256(frame),
        "histogram": histogram(frame),
    }


def build_report() -> dict[str, Any]:
    for window in WINDOWS:
        validate_window(window)
    if len({(w.x, w.y, w.width, w.height) for w in WINDOWS}) != len(WINDOWS):
        raise ValueError("PTLW windows must be distinct")
    for left_index, left in enumerate(WINDOWS):
        for right in WINDOWS[left_index + 1 :]:
            disjoint = (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            )
            if not disjoint:
                raise ValueError("PTLW windows must not overlap")

    frame = bytearray([0x33]) * (WIDTH * HEIGHT // 2)
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch) in enumerate(zip(ROLES, BRANCHES), 1):
        if ordinal in (1, 5):
            frame = bytearray([0x33]) * (WIDTH * HEIGHT // 2)
            window = None
            byte_count = CONTROLLER_WIDTH * HEIGHT // 2
            cs1_code = WHITE_CODE
            cs2_code = WHITE_CODE
        else:
            window = WINDOWS[ordinal - 2]
            set_rect(frame, window)
            byte_count = window.width * window.height // 2
            cs1_code = window.cs1_code
            cs2_code = window.cs2_code
        item = {
            "ordinal": ordinal,
            "role": role,
            "branch": branch,
            "window": asdict(window) if window else None,
            "frame": frame_identity(bytes(frame)),
            "cs1_dtm": uniform_identity(cs1_code, byte_count),
            "cs2_dtm": uniform_identity(cs2_code, byte_count),
        }
        descriptor_payload = {
            "schema": "mf1750-runtime-lut-partial-hold-descriptor-v1",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = sha256(canonical(descriptor_payload))
        item["action_id"] = sha256(
            (
                "MF1750_RUNTIME_LUT_PARTIAL_HOLD_ACTION_V1|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        actions.append(item)

    contract = {
        "schema": "mf1750-runtime-lut-partial-hold-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile": {
            "id": PROFILE_ID,
            "global_header": "active",
            "cs1_r20_prefix_bytes": 535,
            "cs1_r20_prefix_sha256": ACTIVE_R20_PREFIX_SHA256,
            "cs2_r20_prefix_bytes": 535,
            "cs2_r20_prefix_sha256": COMMENTED_R20_PREFIX_SHA256,
            "r21_bytes": 704,
            "r21_sha256": R21_SHA256,
        },
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
        },
        "actions": [
            {
                "ordinal": item["ordinal"],
                "role": item["role"],
                "descriptor_id": item["descriptor_id"],
                "action_id": item["action_id"],
            }
            for item in actions
        ],
        "runtime_lut": True,
        "factory_otp": False,
        "partial_refresh": True,
        "cross_palette": False,
        "camera": False,
        "autochain": False,
        "retry": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-lut-partial-hold-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flushed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "profile_id": PROFILE_ID,
        "contract_id": sha256(canonical(contract)),
        "actions": actions,
        "contract": contract,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
