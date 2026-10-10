#!/usr/bin/env python3
"""Freeze the one-refresh RAW-P16 L535 active endpoint gallery.

The pack contains sixteen endpoint observations: transport codes 0..7 once
on each controller.  It does not assert sixteen unique or qualified colours.
Runtime code 7 is only an endpoint/background code; factory-OTP containment
is a different firmware and campaign.
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
from tools import (  # noqa: E402
    mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_pack as pre_white,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_endpoint_gallery_v1_white_containment_pack as containment,
)
from tools import mf1750_runtime_lut_cross_palette_v1_pack as cross  # noqa: E402

ACTIVE_R20_SHA256 = base.ACTIVE_R20_PREFIX_SHA256
COMMENTED_R20_SHA256 = base.COMMENTED_R20_PREFIX_SHA256
PRE_WHITE_CAMPAIGN_ID = pre_white.CAMPAIGN_ID
PRE_WHITE_CONTRACT_ID = pre_white.CONTRACT_ID
PRE_WHITE_NVS_NAMESPACE = pre_white.NVS_NAMESPACE
CONTAINMENT_CAMPAIGN_ID = containment.CAMPAIGN_ID
CONTAINMENT_CONTRACT_ID = containment.CONTRACT_ID
CONTAINMENT_NVS_NAMESPACE = containment.NVS_NAMESPACE

VARIANT_KEY = "L535_ACTIVE_RAW_P16_ENDPOINT_GALLERY_2X4_V1"
BUILD_TAG = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_V1_2026-08-28"
TEST_ID = "EC5-RAW-P16-ENDPOINT-GALLERY-V1"
CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_V1"
NVS_NAMESPACE = "rp16g_v1"
NVS_KEY = "cursor_p16g"
NVS_BOOT_KEY = "boot_p16g"
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-endpoint-gallery-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_L535_ACTIVE_RAW_ENDPOINT_OBSERVATIONS_NOT_UNIQUE_OR_QUALIFIED_COLOURS"
)
BASE_ROUTE = "/api/ec5/raw-p16-endpoint-gallery-v1"
FIRMWARE_BIN = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-v1/"
    "ec5_raw_p16_endpoint_gallery_v1/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-v1/"
    "ec5_raw_p16_endpoint_gallery_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 797_712
FIRMWARE_BIN_SHA256 = "1cd68a43b8398e76636ebc80123e13aecb4edc6db4d0e7d927e7bcfc84680bef"
FIRMWARE_ELF_BYTES = 13_282_824
FIRMWARE_ELF_SHA256 = "a1d1ad39460ba494f981b20a5d4f169792e2956749611a58b8b6037e2a639b4d"

SUPERSEDED_UNFLASHED_MAIN = {
    "contract_id": "5d4d608449f078e8cedb2a781baccc9d0ee9105aefd980bb5ef1f4275f16185c",
    "firmware_bin_bytes": 797_712,
    "firmware_bin_sha256": (
        "6aa3660d4be506ca9b3a5100688b0a02ee28108292895b7040091f0fce551f75"
    ),
    "firmware_elf_bytes": 13_282_824,
    "firmware_elf_sha256": (
        "587ae58627e48f5f98e13595f0c6b093a58c78e1ccf661fcd7e2c89f41a914b0"
    ),
    "status": "OFFLINE_SUPERSEDED_NEVER_FLASHED",
    "reason": "pre_white_binding_replaced_by_fresh_successor_v1b",
}

SEPARATOR_CODE = 7
GRID_ROWS = 4
GRID_COLUMNS = 2
GRID_X_BY_COLUMN = (36, 276)
GRID_Y_BY_ROW = (36, 180, 324, 468)
CELL_WIDTH = 200
CELL_HEIGHT = 96
GAP_X = 40
GAP_Y = 48
GRID_X0 = GRID_X_BY_COLUMN[0]
GRID_Y0 = GRID_Y_BY_ROW[0]
GRID_X1_EXCLUSIVE = GRID_X_BY_COLUMN[-1] + CELL_WIDTH
GRID_Y1_EXCLUSIVE = GRID_Y_BY_ROW[-1] + CELL_HEIGHT
CODE_ROWS = ((0, 1), (2, 3), (4, 5), (6, 7))


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active_profile() -> dict[str, Any]:
    """Return the already observed active-global/mixed-R20 tuple."""

    profile = dict(cross.profile("active"))
    profile["name"] = "active"
    profile["controller_r20_payloads_byte_identical"] = False
    profile["global_tuple_id"] = sha256(canonical(profile))
    return profile


def cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("RAW-P16 cell outside 2x4 controller grid")
    return GRID_X_BY_COLUMN[column], GRID_Y_BY_ROW[row], CELL_WIDTH, CELL_HEIGHT


def validate_geometry() -> None:
    flat = [code for row in CODE_ROWS for code in row]
    if flat != list(range(8)):
        raise ValueError("RAW-P16 endpoint order must be exact code0..7")
    if (
        GRID_X1_EXCLUSIVE > base.CONTROLLER_WIDTH
        or GRID_Y1_EXCLUSIVE > base.HEIGHT
        or any(value % 2 for value in (*GRID_X_BY_COLUMN, CELL_WIDTH, GAP_X))
        or GRID_X_BY_COLUMN[1] - GRID_X_BY_COLUMN[0] != CELL_WIDTH + GAP_X
        or any(
            b - a != CELL_HEIGHT + GAP_Y
            for a, b in zip(GRID_Y_BY_ROW, GRID_Y_BY_ROW[1:])
        )
    ):
        raise ValueError("RAW-P16 atlas violates packed 4bpp geometry")


def _set_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    x, y, width, height = cell_bounds(row, column)
    global_x = controller * base.CONTROLLER_WIDTH + x
    packed = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + global_x // 2
        frame[start : start + width // 2] = bytes((packed,)) * (width // 2)


def atlas_frame() -> bytes:
    validate_geometry()
    frame = bytearray(((SEPARATOR_CODE << 4) | SEPARATOR_CODE,)) * (
        base.WIDTH * base.HEIGHT // 2
    )
    for controller in (0, 1):
        for row, codes in enumerate(CODE_ROWS):
            for column, code in enumerate(codes):
                _set_cell(frame, controller, row, column, code)
    return bytes(frame)


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != base.WIDTH * base.HEIGHT // 2:
        raise ValueError("invalid RAW-P16 controller stream")
    row_bytes = base.WIDTH // 2
    half = base.CONTROLLER_WIDTH // 2
    offset = controller * half
    return b"".join(
        frame[y * row_bytes + offset : y * row_bytes + offset + half]
        for y in range(base.HEIGHT)
    )


def identity(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "fnv1a": base.fnv1a(data), "sha256": sha256(data)}


def artifact_binding_status() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, path, byte_count, wanted in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = sha256(path.read_bytes()) if present else None
        result[key] = {
            "present": present,
            "verified": bool(
                present and observed_bytes == byte_count and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    validate_geometry()
    artifact_status = artifact_binding_status()
    pre_white_status = pre_white.artifact_binding_status()
    containment_status = containment.artifact_binding_status()
    if verify_artifacts and (
        any(item["verified"] is not True for item in artifact_status.values())
        or any(item["verified"] is not True for item in pre_white_status.values())
        or any(item["verified"] is not True for item in containment_status.values())
    ):
        raise ValueError("RAW-P16 gallery or containment artifact binding differs")
    frame = atlas_frame()
    cs1 = identity(controller_stream(frame, 0))
    cs2 = identity(controller_stream(frame, 1))
    waveform = active_profile()
    action: dict[str, Any] = {
        "ordinal": 1,
        "role": "RAW_P16_ACTIVE_ENDPOINT_GALLERY",
        "driver_role": "Source",
        "round": 1,
        "branch": f"{VARIANT_KEY}_ACTIVE_GLOBAL_CODE0_TO_7_BOTH_CONTROLLERS",
        "palette_source": "L535_RUNTIME",
        "global_header": "active",
        "profile_id": waveform["id"],
        "global_tuple_id": waveform["global_tuple_id"],
        "waveform_binding": waveform,
        "frame": base.frame_identity(frame),
        "cs1_dtm": cs1,
        "cs2_dtm": cs2,
        "controller_dtm_byte_identical": cs1 == cs2,
        "prior_static_action_id": None,
        "boot_admission": {
            "campaign_boot_binding_key": NVS_BOOT_KEY,
            "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
            "required_prior_terminal_state": None,
            "required_prior_ordinal": None,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        },
    }
    descriptor = {
        "schema": "mf1750-raw-p16-endpoint-gallery-action-descriptor-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        **action,
    }
    action["descriptor_id"] = sha256(canonical(descriptor))
    action["action_id"] = sha256(
        f"MF1750_RAW_P16_ENDPOINT_GALLERY_ACTION_V1|{action['descriptor_id']}".encode()
    )
    positions = [
        {
            "row": row,
            "column": column,
            "code": CODE_ROWS[row][column],
            "x": cell_bounds(row, column)[0],
            "y": cell_bounds(row, column)[1],
            "width": CELL_WIDTH,
            "height": CELL_HEIGHT,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]
    contract = {
        "schema": "mf1750-raw-p16-endpoint-gallery-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile": waveform,
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "row_codes": [list(row) for row in CODE_ROWS],
            "positions": positions,
            "endpoint_observations_per_controller": 8,
            "endpoint_observations_total": 16,
            "unique_transport_codes": 8,
            "background_code": SEPARATOR_CODE,
            "border": False,
            "same_layout_both_controllers": True,
            "controller_dtm_byte_identical": True,
            "spatial_dither": False,
        },
        "actions": [action],
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "external_factory_otp_white_precondition": {
            "required": True,
            "clean_white_operator_or_camera_gate": True,
            "runtime_code7_accepted_as_white_anchor": False,
            "outside_campaign": True,
            "campaign_id": pre_white.CAMPAIGN_ID,
            "contract_id": pre_white.CONTRACT_ID,
            "factory_otp_white_only": True,
            "independent_nvs_namespace": pre_white.NVS_NAMESPACE,
            "automatic": False,
        },
        "post_gallery_containment": {
            "outside_campaign": True,
            "campaign_id": containment.CAMPAIGN_ID,
            "contract_id": containment.CONTRACT_ID,
            "factory_otp_white_only": True,
            "independent_nvs_namespace": containment.NVS_NAMESPACE,
            "automatic": False,
        },
        "runtime_code7_is_factory_white": False,
        "endpoint_observations": 16,
        "unique_colours_claimed": 0,
        "qualified_colours": 0,
        "colour_family_labels": "UNQUALIFIED_OBSERVATION_ONLY",
        "classification_ambiguity": ["cyan_teal", "violet_magenta", "brown_orange"],
        "partial_refresh": False,
        "window_refresh": False,
        "local_hold_claimed": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-endpoint-gallery-offline-identities-v1",
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
        "contract_id": sha256(canonical(contract)),
        "supersedes_offline_unflashed_main_artifact": dict(SUPERSEDED_UNFLASHED_MAIN),
        "actions": [action],
        "contract": contract,
        "artifacts": {
            "firmware_bin": {
                "path": str(FIRMWARE_BIN),
                "bytes": FIRMWARE_BIN_BYTES,
                "sha256": FIRMWARE_BIN_SHA256,
            },
            "firmware_elf": {
                "path": str(FIRMWARE_ELF),
                "bytes": FIRMWARE_ELF_BYTES,
                "sha256": FIRMWARE_ELF_SHA256,
            },
        },
        "artifact_binding_status": artifact_status,
        "pre_white_artifact_binding_status": pre_white_status,
        "containment_artifact_binding_status": containment_status,
    }


def main() -> int:
    print(
        json.dumps(
            build_report(verify_artifacts=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
