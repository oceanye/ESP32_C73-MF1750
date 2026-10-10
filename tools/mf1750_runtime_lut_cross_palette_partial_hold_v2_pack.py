#!/usr/bin/env python3
"""Freeze offline identities for the clean-PTLW cross-palette HOLD V2.

The five actions are immutable: factory white, active/code5 ROI-A,
commented/code6 ROI-B while A is held, active/code3 ROI-C while A/B are held,
and factory-white recovery.  Every runtime action mechanically reuses the
live-proven Fullframe/PTLW V2 transport: complete code-7 SRAM prestage, one
inclusive PTLW per controller, one cropped target DTM, then PON/DRF00/POF00.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v1_pack as old  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as clean  # noqa: E402


VARIANT_KEY = "L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_CLEAN_PTLW_V2"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_2026-08-26"
TEST_ID = "EC5-RUNTIME-LUT-CROSS-PALETTE-PARTIAL-HOLD-V2"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2"
NVS_NAMESPACE = "rlxph_v2"
NVS_KEY = "cursor_cxph2"
ENV_NAME = "ec5_runtime_lut_cross_palette_partial_hold_v2"
DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_DEVICE_V2"
)
IDENTITY_REVISION = "runtime-lut-cross-palette-partial-hold-v2"
DEVICE_KIND_PREFIX = (
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v2"
)
ENDPOINT_BASE = "/api/ec5/runtime-lut-cross-palette-partial-hold-v2"
PROFILE_ID = (
    "ACTIVE_CODE5_TO_COMMENTED_CODE6_TO_ACTIVE_CODE3__"
    "CS1_ACTIVE535__CS2_COMMENTED535__CLEAN_PTLW_V2"
)

WIDTH = identity.WIDTH
HEIGHT = identity.HEIGHT
CONTROLLER_WIDTH = identity.CONTROLLER_WIDTH
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
WHITE_CODE = 7
FACTORY_WHITE_CODE = 1
WINDOWS = old.WINDOWS
TARGET_CODES = tuple(window.cs1_code for window in WINDOWS)
CROPPED_DTM_BYTES = tuple(
    window.width * window.height // 2 for window in WINDOWS
)

QUALIFIER_V2_PREREQUISITE = deepcopy(clean.QUALIFIER_V2_PREREQUISITE)
QUALIFIER_V2_BUNDLE_ID = clean.QUALIFIER_V2_BUNDLE_ID
PER_ACTION_READINESS_QUALIFICATION = deepcopy(
    clean.PER_ACTION_READINESS_QUALIFICATION
)
BUSY_ADMISSION_CONTRACT = deepcopy(clean.BUSY_ADMISSION_CONTRACT)

PROFILE_ACTIVE = deepcopy(old.cross.profile("active"))
PROFILE_COMMENTED = deepcopy(old.cross.profile("commented"))
PROFILES = {
    "active": PROFILE_ACTIVE,
    "commented": PROFILE_COMMENTED,
}
PROFILE_SEQUENCE: tuple[str | None, ...] = (
    None,
    "active",
    "commented",
    "active",
    None,
)
ROLES = old.ROLES
GLOBAL_HEADERS = old.GLOBAL_HEADERS
BRANCHES = (
    "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
    "L535_ACTIVE_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE5_ROI_A",
    "L535_COMMENTED_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE6_ROI_B_HOLD_A",
    "L535_ACTIVE_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE3_ROI_C_HOLD_AB",
    "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
)
WHITE_REFRESH_SEQUENCE = old.WHITE_REFRESH_SEQUENCE
RUNTIME_REFRESH_SEQUENCE = (
    "LOAD_SELECTED_GLOBAL_HEADER_AND_CONTROLLER_LUTS",
    "FULL_CODE7_DTM_PRESTAGE_CS1_NO_REFRESH",
    "FULL_CODE7_DTM_PRESTAGE_CS2_NO_REFRESH",
    "PTLW_CS1_INCLUSIVE_ONCE",
    "CROPPED_TARGET_DTM_CS1",
    "PTLW_CS2_INCLUSIVE_ONCE",
    "CROPPED_TARGET_DTM_CS2",
    "PON_BUSY_COMPLETE_60S_GATE",
    "DRF_00_BUSY_COMPLETE_60S_GATE",
    "POF_00_BUSY_COMPLETE_60S_GATE",
)

PRELOAD_DTM = bytes([0x77]) * CONTROLLER_DTM_BYTES
PRELOAD_DTM_SHA256 = identity.sha256(PRELOAD_DTM)
PRELOAD_DTM_FNV1A = identity.fnv1a(PRELOAD_DTM)
TARGET_DTMS = tuple(
    bytes([(code << 4) | code]) * byte_count
    for code, byte_count in zip(TARGET_CODES, CROPPED_DTM_BYTES, strict=True)
)
TARGET_DTM_SHA256 = tuple(identity.sha256(payload) for payload in TARGET_DTMS)
TARGET_DTM_FNV1A = tuple(identity.fnv1a(payload) for payload in TARGET_DTMS)
COMBINED_DTMS = tuple(PRELOAD_DTM + payload for payload in TARGET_DTMS)
COMBINED_DTM_SHA256 = tuple(
    identity.sha256(payload) for payload in COMBINED_DTMS
)
COMBINED_DTM_FNV1A = tuple(identity.fnv1a(payload) for payload in COMBINED_DTMS)


def ptlw_payload(window: identity.Window) -> bytes:
    """Return the frozen 9-byte inclusive 0x83 payload for one ROI."""

    identity.validate_window(window)
    x_end = window.x + window.width - 1
    y_end = window.y + window.height - 1
    return bytes(
        (
            window.x >> 8,
            window.x & 0xFF,
            x_end >> 8,
            x_end & 0xFF,
            window.y >> 8,
            window.y & 0xFF,
            y_end >> 8,
            y_end & 0xFF,
            0x01,
        )
    )


PTLW_PAYLOADS = tuple(ptlw_payload(window) for window in WINDOWS)


def _assert_geometry() -> None:
    for window in WINDOWS:
        identity.validate_window(window)
    for left_index, left in enumerate(WINDOWS):
        for right in WINDOWS[left_index + 1 :]:
            if not (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            ):
                raise RuntimeError("clean-PTLW V2 windows overlap")
    if TARGET_CODES != (5, 6, 3):
        raise RuntimeError("clean-PTLW V2 target codes drifted")
    if any(value != 9_600 for value in CROPPED_DTM_BYTES):
        raise RuntimeError("clean-PTLW V2 crop geometry drifted")
    if PRELOAD_DTM_SHA256 != clean.PRELOAD_DTM_SHA256:
        raise RuntimeError("live-proven code7 prestage identity drifted")


def _descriptor(item: Mapping[str, Any]) -> str:
    value = {
        "schema": "mf1750-runtime-lut-cross-palette-partial-hold-descriptor-v2",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
        "per_action_readiness_qualification": deepcopy(
            PER_ACTION_READINESS_QUALIFICATION
        ),
        "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
        **item,
    }
    return identity.sha256(identity.canonical(value))


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return identity.sha256(
        (
            "MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_ACTION_V2|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def _build_actions() -> list[dict[str, Any]]:
    _assert_geometry()
    white_frame = bytes([0x11]) * FRAME_BYTES
    logical_frame = bytearray([0x77]) * FRAME_BYTES
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch, global_header) in enumerate(
        zip(ROLES, BRANCHES, GLOBAL_HEADERS, strict=True), 1
    ):
        is_white = ordinal in (1, 5)
        if is_white:
            frame = identity.frame_identity(white_frame)
            dtm = identity.uniform_identity(
                FACTORY_WHITE_CODE, CONTROLLER_DTM_BYTES
            )
            action: dict[str, Any] = {
                "ordinal": ordinal,
                "role": role,
                "branch": branch,
                "window": None,
                "palette_source": "FACTORY_OTP",
                "global_header": None,
                "profile_id": None,
                "dtm_transport": "FACTORY_OTP_PACKED_FULL_FRAME_0X11",
                "ptlw_payload_hex": None,
                "ptlw_writes_per_controller": 0,
                "runtime_code7_prestage": False,
                "refresh_sequence": list(WHITE_REFRESH_SEQUENCE),
                "frame": frame,
                "prestage_dtm": None,
                "target_dtm": deepcopy(dtm),
                "cs1_dtm": deepcopy(dtm),
                "cs2_dtm": deepcopy(dtm),
            }
        else:
            index = ordinal - 2
            window = WINDOWS[index]
            identity.set_rect(logical_frame, window)
            frame = identity.frame_identity(bytes(logical_frame))
            prestage = {
                "bytes": CONTROLLER_DTM_BYTES,
                "fnv1a": PRELOAD_DTM_FNV1A,
                "sha256": PRELOAD_DTM_SHA256,
            }
            target = {
                "bytes": CROPPED_DTM_BYTES[index],
                "fnv1a": TARGET_DTM_FNV1A[index],
                "sha256": TARGET_DTM_SHA256[index],
            }
            combined = {
                "bytes": CONTROLLER_DTM_BYTES + CROPPED_DTM_BYTES[index],
                "fnv1a": COMBINED_DTM_FNV1A[index],
                "sha256": COMBINED_DTM_SHA256[index],
            }
            profile = PROFILES[str(global_header)]
            action = {
                "ordinal": ordinal,
                "role": role,
                "branch": branch,
                "window": asdict(window),
                "palette_source": "L535_RUNTIME",
                "global_header": global_header,
                "profile_id": profile["id"],
                "dtm_transport": (
                    "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP"
                ),
                "ptlw_payload_hex": PTLW_PAYLOADS[index].hex(),
                "ptlw_writes_per_controller": 1,
                "runtime_code7_prestage": True,
                "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
                "frame": frame,
                "prestage_dtm": prestage,
                "target_dtm": target,
                "cs1_dtm": deepcopy(combined),
                "cs2_dtm": deepcopy(combined),
            }
        descriptor_source = deepcopy(action)
        descriptor_id = _descriptor(descriptor_source)
        action["descriptor_id"] = descriptor_id
        action["action_id"] = _action_id(ordinal, descriptor_id)
        actions.append(action)
    return actions


def _action_summary(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": item["ordinal"],
            "role": item["role"],
            "palette_source": item["palette_source"],
            "global_header": item["global_header"],
            "profile_id": item["profile_id"],
            "dtm_transport": item["dtm_transport"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
        }
        for item in actions
    ]


def build_report() -> dict[str, Any]:
    """Return immutable V2 action and contract identities without I/O."""

    actions = _build_actions()
    contract = {
        "schema": "mf1750-runtime-lut-cross-palette-partial-hold-contract-v2",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profiles": deepcopy(PROFILES),
        "profile_sequence": list(PROFILE_SEQUENCE),
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
            "ptlw_payloads_hex": [payload.hex() for payload in PTLW_PAYLOADS],
        },
        "actions": _action_summary(actions),
        "clean_ptlw_transport": {
            "mechanical_source_contract_id": clean.CONTRACT_ID,
            "runtime_code7_full_dtm_prestage": True,
            "runtime_code7_prestage_no_refresh": True,
            "runtime_code7_prestage_bytes_per_controller": (
                CONTROLLER_DTM_BYTES
            ),
            "runtime_code7_prestage_sha256": PRELOAD_DTM_SHA256,
            "ptlw_writes_per_controller_per_runtime_action": 1,
            "cropped_target_dtm_bytes_per_controller": list(
                CROPPED_DTM_BYTES
            ),
            "target_dtm_sha256": list(TARGET_DTM_SHA256),
            "combined_dtm_sha256": list(COMBINED_DTM_SHA256),
            "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
            "action_stage_cdi": False,
            "action_stage_btst2": False,
            "repeat_ptlw_after_pon_busy": False,
            "command_0x86": False,
            "extra_dtm_prefix_or_suffix_byte": False,
        },
        "qualifier_v2_prerequisite": deepcopy(QUALIFIER_V2_PREREQUISITE),
        "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
        "per_action_readiness_qualification": deepcopy(
            PER_ACTION_READINESS_QUALIFICATION
        ),
        "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
        "runtime_lut": True,
        "factory_otp": True,
        "partial_refresh": True,
        "cross_palette_hold_probe": True,
        "same_palette_hold_probe": False,
        "full_screen_factory_white_actions": True,
        "runtime_transport_codes": list(TARGET_CODES),
        "spatial_dither": False,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    contract_id = identity.sha256(identity.canonical(contract))
    return {
        "schema_version": 2,
        "kind": (
            "mf1750-runtime-lut-cross-palette-partial-hold-v2-"
            "offline-identities"
        ),
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
        "contract_id": contract_id,
        "actions": actions,
        "contract": contract,
    }


_REPORT = build_report()
# Literal release identities make any later contract drift fail at import,
# before a runner can reserve evidence or contact a device.
CONTRACT_ID = "d9059cd99c9442fcf5ad4d74c360aaa6f6f18737cd9d090e4fa21b53ad06948b"
DESCRIPTOR_IDS = (
    "87e3cdb030c71be006e54ff4663bf55d854d2acf9f3b06edc8846e91e01d3de5",
    "65706e2e0c9cafafdbc68bae63c34666dae31f8fe576cb172d80382125c9f4c6",
    "55d682b82b0cd9c99a63543f56fcaab66289c81c3b5461394d375f7bfaaae641",
    "a75380aa3d67794c497f0b798bc04e5ded9b9de690dccddaaeb489a584d6ee63",
    "ab913fc1d92e65b08a4b9919d036105d78446cc54256d3462a404393b0ff756f",
)
ACTION_IDS = (
    "21c44e19182683611ece953b1744012319ad6570540eff583d1ca3cac187068f",
    "6ae993bbb78b2e2a6fc46a3d08ff139cf9df62c9e9b1c2ff31f1c98063851fb9",
    "c2f74440be76c1a660551771df21d15b6d5a2d610ac378d3a22acbff00f20014",
    "e34c0e25c0e27e63fcdade01b10b619676fa429967042c70b29cd9d6daa3deff",
    "5097983e4887425fb4a1ca9932a5d43fa59ae323b779876c04d81844b50f2c61",
)
if _REPORT["contract_id"] != CONTRACT_ID:
    raise RuntimeError("clean-PTLW V2 contract identity drifted")
if tuple(item["descriptor_id"] for item in _REPORT["actions"]) != DESCRIPTOR_IDS:
    raise RuntimeError("clean-PTLW V2 descriptor identities drifted")
if tuple(item["action_id"] for item in _REPORT["actions"]) != ACTION_IDS:
    raise RuntimeError("clean-PTLW V2 action identities drifted")


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
