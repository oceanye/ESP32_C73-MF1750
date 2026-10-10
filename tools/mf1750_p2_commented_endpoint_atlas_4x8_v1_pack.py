#!/usr/bin/env python3
"""Offline authority for one fresh commented/commented 4x8 endpoint atlas."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as geometry  # noqa: E402
from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as profiles  # noqa: E402


VARIANT_KEY = "P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1"
BUILD_TAG = "MF1750_EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_2026-09-03"
TEST_ID = "EC5-P2-COMMENTED-ENDPOINT-ATLAS-4X8-V1"
CAMPAIGN_ID = "EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1"
NVS_NAMESPACE = "p2ce4x8v1"
NVS_KEY = "cursor_p2c"
NVS_BOOT_KEY = "boot_p2c"
DEVICE_API_VERSION = "MF1750_EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_DEVICE_V1"
IDENTITY_REVISION = "p2-commented-endpoint-atlas-4x8-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_FRESH_ONE_SHOT_COMPLETE_COMMENTED_PROFILE_ENDPOINT_"
    "CANDIDATES_ZERO_QUALIFIED_COLOURS"
)
BASE_ROUTE = "/api/ec5/p2-commented-endpoint-atlas-4x8-v1"

BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-p2-commented-endpoint-atlas-4x8-v1"
    / "ec5_p2_commented_endpoint_atlas_4x8_v1"
)
ARTIFACTS: dict[str, dict[str, Any]] = {
    "firmware.bin": {
        "path": BUILD_DIR / "firmware.bin",
        "bytes": 798_496,
        "sha256": "61d7704f4dfbcfd3b2ec21aa1eb571b400bf5ee391ababe6e4da1dc54010935d",
    },
    "firmware.elf": {
        "path": BUILD_DIR / "firmware.elf",
        "bytes": 13_286_496,
        "sha256": "451b7663aabd40a0771161c334c41f1f9be39ff0d47b2b7a7342b4edda9f7ac1",
    },
}

ROLE = "P2_COMMENTED_COMPLETE_PROFILE_POSITION_BALANCED_4X8_ENDPOINT_ATLAS"
BRANCH = "P2_FRESH_ONE_SHOT_COMMENTED_COMMENTED_ENDPOINT_ATLAS_4X8_V1"
DRIVER_ROLE = "Source"
SEPARATOR_CODE = geometry.SEPARATOR_CODE
GRID_ROWS = geometry.GRID_ROWS
GRID_COLUMNS = geometry.GRID_COLUMNS
GRID_X0 = geometry.GRID_X0
GRID_Y_BY_ROW = geometry.GRID_Y_BY_ROW
CELL_WIDTH = geometry.CELL_WIDTH
CELL_HEIGHT = geometry.CELL_HEIGHT
GAP_X = geometry.GAP_X
GAP_Y = geometry.GAP_Y
GRID_X1_EXCLUSIVE = geometry.GRID_X1_EXCLUSIVE
GRID_Y1_EXCLUSIVE = geometry.GRID_Y1_EXCLUSIVE
CODE_ROWS = geometry.CODE_ROWS

# The offline build/audit seal binds every executable authority layer that can
# change the meaning of a P2 evidence record.  Keep this list explicit and
# repository-relative: neither generated binaries nor the report that records
# these hashes belong in the list (doing so would create a self-referential
# seal).  The firmware template/configuration inputs are included alongside
# the Python runner, builder, audit, and retained-review recorder.
AUTHORITY_SOURCE_RELATIVE_PATHS = (
    "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_once.py",
    "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_build.py",
    "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_audit.py",
    "tools/mf1750_p2_retained_clean_white_human_review.py",
    "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_pack.py",
    "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_codegen.py",
    "platformio.p2_commented_endpoint_atlas_4x8_v1.ini",
    "src/ec5_p1_active_endpoint_atlas_4x8_v1_program.inc",
    "src/ec5_p1_active_endpoint_atlas_4x8_v1_driver.inc",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authority_source_hashes() -> dict[str, dict[str, Any]]:
    """Return deterministic byte and SHA-256 bindings for authority sources.

    This helper is deliberately read-only.  It is used by the offline build
    and independent audit to prove that the runner, its builder/auditor, the
    strong review recorder, and the firmware inputs were all sealed together.
    """

    result: dict[str, dict[str, Any]] = {}
    for relative in AUTHORITY_SOURCE_RELATIVE_PATHS:
        path = REPO_ROOT / relative
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise ValueError(f"P2 authority source is unreadable: {relative}") from error
        if not payload or path.is_symlink() or not path.is_file():
            raise ValueError(f"P2 authority source is missing or unsafe: {relative}")
        result[Path(relative).name] = {
            "path": relative,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
    return result


def authority_source_seal(
    sources: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a canonical, non-self-referential authority-source seal."""

    bound = authority_source_hashes() if sources is None else deepcopy(sources)
    return {
        "algorithm": "sha256-canonical-json-authority-sources-v1",
        "sha256": sha256_bytes(canonical_json(bound)),
        "sources": bound,
    }


def commented_profile() -> dict[str, Any]:
    result = deepcopy(profiles.profile("commented"))
    result["complete_profile_tuple"] = True
    return result


def atlas_frame() -> bytes:
    return geometry.atlas_frame()


def controller_stream(frame: bytes, controller: int) -> bytes:
    return geometry.controller_stream(frame, controller)


def payload_identity(data: bytes) -> dict[str, Any]:
    return geometry.payload_identity(data)


def validate_artifacts() -> dict[str, dict[str, Any]]:
    verified: dict[str, dict[str, Any]] = {}
    for name, expected in ARTIFACTS.items():
        if not expected["bytes"] or len(str(expected["sha256"])) != 64:
            raise ValueError(f"P2-C {name} has not been sealed")
        path = Path(expected["path"])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"sealed P2-C artifact missing: {path}")
        payload = path.read_bytes()
        observed = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
        if observed != {"bytes": expected["bytes"], "sha256": expected["sha256"]}:
            raise ValueError(f"sealed P2-C artifact identity differs: {path}")
        verified[name] = {
            **observed,
            "path": path.relative_to(REPO_ROOT).as_posix(),
        }
    return verified


def artifacts_are_sealed() -> bool:
    try:
        validate_artifacts()
    except (OSError, ValueError):
        return False
    return True


def build_report() -> dict[str, Any]:
    geometry.validate_geometry()
    frame = atlas_frame()
    cs1 = payload_identity(controller_stream(frame, 0))
    cs2 = payload_identity(controller_stream(frame, 1))
    waveform = commented_profile()
    action_seed: dict[str, Any] = {
        "ordinal": 1,
        "role": ROLE,
        "driver_role": DRIVER_ROLE,
        "round": 1,
        "branch": BRANCH,
        "palette_source": "L535_RUNTIME",
        "global_header": "commented",
        "profile_id": waveform["id"],
        "global_tuple_id": waveform["global_tuple_id"],
        "waveform_binding": waveform,
        "frame": geometry.base.frame_identity(frame),
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
        "schema": "mf1750-p2-commented-endpoint-atlas-action-descriptor-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        **action_seed,
    }
    action_seed["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action_seed["action_id"] = sha256_bytes(
        (
            "MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_ACTION_V1|"
            f"{VARIANT_KEY}|1|{action_seed['descriptor_id']}"
        ).encode("ascii")
    )
    positions = [
        {
            "row": row,
            "column": column,
            "code": CODE_ROWS[row][column],
            "x": geometry.cell_bounds(row, column)[0],
            "y": geometry.cell_bounds(row, column)[1],
            "width": CELL_WIDTH,
            "height": CELL_HEIGHT,
        }
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]
    contract = {
        "schema": "mf1750-p2-commented-endpoint-atlas-4x8-contract-v1",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile": waveform,
        "geometry": {
            "width": geometry.base.WIDTH,
            "height": geometry.base.HEIGHT,
            "controller_width": geometry.base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "row_codes": [list(row) for row in CODE_ROWS],
            "positions": positions,
            "samples_per_code_per_controller_per_frame": 4,
            "background_code": SEPARATOR_CODE,
            "border": False,
            "cs2_position_mirrored": False,
            "same_layout_both_controllers": True,
            "controller_dtm_byte_identical": True,
            "spatial_dither": False,
        },
        "actions": [action_seed],
        "action_count": 1,
        "one_driver_call_per_action": True,
        "one_visible_refresh_per_action": True,
        "complete_busy_required": True,
        "fresh_one_shot": True,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "full_screen_global_refresh": True,
        "external_containment": {
            "outside_campaign": True,
            "factory_otp_white_before_required": True,
            "factory_otp_white_after_required": True,
            "successor_identity_bound_after_main_artifact_seal": True,
            "post_white_clean_visual_gate_required": True,
            "white_actions_in_campaign": 0,
        },
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "partial_refresh": False,
        "window_refresh": False,
        "local_hold_claimed": False,
        "controller_bus_capture_claimed": False,
        "controller_payload_source_identity_claimed": True,
        "colour_equivalence_claimed": False,
        "absolute_colour_claimed": False,
        "qualified_colours": 0,
        "qualified_lightness_levels": 0,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "firmware_descriptor": {
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "campaign_id": CAMPAIGN_ID,
            "device_api_version": DEVICE_API_VERSION,
            "identity_revision": IDENTITY_REVISION,
        },
        "action_descriptor": descriptor,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "actions": [action_seed],
        "contract": contract,
    }


REPORT = build_report()
ACTION_DESCRIPTOR = REPORT["action_descriptor"]
FIRMWARE_DESCRIPTOR = REPORT["firmware_descriptor"]
ACTION_DESCRIPTOR_SHA256 = REPORT["actions"][0]["descriptor_id"]
ACTION_SHA256 = REPORT["actions"][0]["action_id"]
CONTRACT_SHA256 = REPORT["contract_id"]
FRAME_SHA256 = REPORT["actions"][0]["frame"]["sha256"]
CONTROLLER_DTM_SHA256 = REPORT["actions"][0]["cs1_dtm"]["sha256"]


if __name__ == "__main__":
    print(json.dumps(REPORT, ensure_ascii=False, indent=2, sort_keys=True))
