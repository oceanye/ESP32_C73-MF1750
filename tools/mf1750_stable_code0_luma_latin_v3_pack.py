#!/usr/bin/env python3
"""Offline identities for the stable active-code0 luma Latin V3 screen.

This campaign is deliberately narrow.  It does not search more hues.  Every
cell starts at active code 7, receives exactly one commented-header middle
code from an 8x8 Latin square, and ends at active code 0.  A fourth, separately
armed action repeats the exact active-code0 target frame.  CS2 is the red-family
primary observation surface.  CS1 is a controller-specific internal control;
the contract never claims that equal transport codes imply equal colours.

All functions in this module are offline-only.  No network, serial, camera,
relay, flash, reset, or display operation is performed here.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_v1_pack as cross  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as base  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_successor_v5_white_v1_pack as w11_pack,
)


class StableCode0LumaLatinV3PackError(RuntimeError):
    """Raised when a frozen offline identity or authority differs."""


VARIANT_KEY = "STABLE_CODE0_LUMA_LATIN_V3"
BUILD_TAG = "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_2026-09-01"
TEST_ID = "EC5-STABLE-CODE0-LUMA-LATIN-V3"
CAMPAIGN_ID = "EC5_STABLE_CODE0_LUMA_LATIN_V3"
DEVICE_API_VERSION = "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_DEVICE_V3"
IDENTITY_REVISION = "stable-code0-luma-latin-v3"
CLASSIFICATION = (
    "EXPERIMENTAL_STABLE_ACTIVE_CODE0_HISTORY_LUMA_CANDIDATES_"
    "CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_CONTROL"
)
ENVIRONMENT = "ec5_stable_c0_luma_lat_v3"
BUILD_ROOT = "b-stable-c0-luma-lat-v3"
BASE_ROUTE = "/api/ec5/stable-code0-luma-latin-v3"
NVS_NAMESPACE = "scllat_v3"
NVS_KEY = "cur_scl3"
NVS_BOOT_KEY = "boot_scl3"

PROFILE_ACTIVE = cross.PROFILE_ACTIVE
PROFILE_COMMENTED = cross.PROFILE_COMMENTED
PROFILE_ID = (
    "ACTIVE_SOURCE_C7_TO_COMMENTED_LATIN_C0_C7_TO_ACTIVE_TARGET_C0__"
    "CS1_ACTIVE535__CS2_COMMENTED535"
)
TARGET_HUE_ID = (
    "ACTIVE_CODE0_CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_"
    "INTERNAL_CONTROL_UNCALIBRATED"
)
SOURCE_CODE = 7
TARGET_CODE = 0
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

GLOBAL_HEADERS = ("active", "commented", "active", "active")
ROLES = (
    "L1_FIXED_ACTIVE_SOURCE_CODE7",
    "L2_COMMENTED_MIDDLE_LATIN_C0_C7",
    "L3_FIXED_ACTIVE_TARGET_CODE0",
    "L4_IDENTICAL_ACTIVE_TARGET_CODE0_REPEAT",
)
DRIVER_ROLES = ("Source", "Mid", "Target", "Target")
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)
ARM_INTENT = "ARM_ONE_FIXED_STABLE_CODE0_LUMA_LATIN_V3_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_STABLE_CODE0_LUMA_LATIN_V3_ACTION_ONCE"

SOURCE_ROOT = (
    REPO_ROOT
    / ".test-output/hardware"
    / (
        "MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1"
    )
)
SOURCE_ACTION_PATH = SOURCE_ROOT / "action-01-factory-otp-white.json"
SOURCE_CLAIM_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / (
        ".mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v5_white_v1_claims"
    )
    / (
        "80a9fd85ff4b93ce365b699f1caa8d7835cbeeeaf738194f70cccc0f7500b595"
        ".json"
    )
)
SOURCE_CAMERA_REVIEW_PATH = (
    SOURCE_ROOT
    / "post-white-retained-camera-attempt-01.camera-visible-clean-white-review.json"
)
SOURCE_CAPTURE_PATH = SOURCE_ROOT / "post-white-retained-camera-attempt-01.capture.json"
SOURCE_PHOTO_PATH = SOURCE_ROOT / "post-white-retained-camera-attempt-01.jpg"
SOURCE_RELAY_OFF_PATH = SOURCE_ROOT / "relay-post-action-protective-off.json"

SOURCE_FILE_BINDINGS: dict[str, dict[str, Any]] = {
    "w11_complete": {
        "path": SOURCE_ACTION_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 30_937,
        "file_sha256": "e48ee37c34e6984f15656267e8d915a8552b210f8dd465610ca1c438ee79c3b0",
        "canonical_integrity_sha256": "42271e6b8d705366be1decf070b5a9d0fb1515f5b9136ebc1e33a79a33401a11",
    },
    "w11_claim": {
        "path": SOURCE_CLAIM_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 1_885,
        "file_sha256": "6e61b9f62fdb7dd39909845ad31adbc0be313dac81d9a85d1e3fc659449a7849",
        "canonical_integrity_sha256": "92b001a4ab1ea79826b644bd0737afecf185241946f310c6168edc2741a48c97",
    },
    "camera_visible_clean_white_review": {
        "path": SOURCE_CAMERA_REVIEW_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 6_352,
        "file_sha256": "c88d22d8ab241daeccb28e01a722c166fdc07bef50f7c55024ba57204008d9a9",
        "canonical_integrity_sha256": "617201f980461d76864be7199f50c5878747ccf777349286ffbe78699da34d7d",
    },
    "capture_sidecar": {
        "path": SOURCE_CAPTURE_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 5_467,
        "file_sha256": "11cb4d77bab294f11bbc8a2496ca98fb7813c07a33b526054a3887258c589aa4",
        "canonical_integrity_sha256": "b47580dc1aaef3d824205ed3a34c3ebdd6f02dd2c92edd8f67374f4ed57110ac",
    },
    "photo": {
        "path": SOURCE_PHOTO_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 638_038,
        "file_sha256": "0dc805e0014d0092e7d032b467eccd2d11490cec97ea6b280594fa25550d7816",
    },
    "relay_protective_off": {
        "path": SOURCE_RELAY_OFF_PATH.relative_to(REPO_ROOT).as_posix(),
        "bytes": 1_798,
        "file_sha256": "d5ef48f419ef7977d4d30c52033ba6fb06820c227d625321f9c8bedbe437e486",
        "canonical_integrity_sha256": "bdf099a39053af84deb8aca7d842cb83b8373da151ea3271b242b3039fccc09e",
    },
}

ZERO_SHA256 = "0" * 64
ARTIFACTS: dict[str, dict[str, int | str]] = {
    VARIANT_KEY: {
        "bin_bytes": 799_792,
        "bin_sha256": "16f63947918d244e27edd0a7f3d0c3f4ff895fa02cbc26c31461c9d91ea7b737",
        "elf_bytes": 13_286_636,
        "elf_sha256": "c3e763105daeec2bc610daef2aad7e4b8c138d3c95cf414fa343aa067adcdcdb",
    }
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fnv1a(payload: bytes) -> int:
    value = 0x811C9DC5
    for byte in payload:
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def artifact_paths() -> tuple[Path, Path]:
    root = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    value = ARTIFACTS[VARIANT_KEY]
    return (
        int(value["bin_bytes"]) > 0
        and int(value["elf_bytes"]) > 0
        and value["bin_sha256"] != ZERO_SHA256
        and value["elf_sha256"] != ZERO_SHA256
    )


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    if not 0 <= row < GRID_ROWS or not 0 <= column < GRID_COLUMNS:
        raise ValueError("stable-code0 cell outside 8x8 grid")
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
        raise StableCode0LumaLatinV3PackError("packed grid geometry differs")
    rectangles = [_cell_bounds(row, col) for row in range(8) for col in range(8)]
    for index, left in enumerate(rectangles):
        lx, ly, lw, lh = left
        for rx, ry, rw, rh in rectangles[index + 1 :]:
            if not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly):
                raise StableCode0LumaLatinV3PackError("candidate cells overlap")


def middle_code(controller: int, row: int, column: int) -> int:
    """Return the decodable Latin-square middle code for one physical cell."""

    if controller == 0:
        return (row + column) % 8
    if controller == 1:
        # Physical 180-degree rotation of the CS1 Latin square.
        return (6 - row - column) % 8
    raise ValueError("controller must be 0 or 1")


def decode_cs2_cell(row: int, column: int) -> dict[str, int]:
    logical_row = 7 - row
    logical_column = 7 - column
    return {
        "logical_row": logical_row,
        "logical_column": logical_column,
        "middle_code": (logical_row + logical_column) % 8,
    }


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
        raise ValueError("unknown stable-code0 stage")
    separator_pair = (SEPARATOR_CODE << 4) | SEPARATOR_CODE
    frame = bytearray([separator_pair]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in (0, 1):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                if stage == "source":
                    code = SOURCE_CODE
                elif stage == "middle":
                    code = middle_code(controller, row, column)
                else:
                    code = TARGET_CODE
                _set_controller_cell(frame, controller, row, column, code)
    return bytes(frame)


def _factory_white_frame() -> bytes:
    return bytes([FACTORY_WHITE_FILL_BYTE]) * (base.WIDTH * base.HEIGHT // 2)


def _controller_stream(frame: bytes, controller: int) -> bytes:
    return cross.controller_stream(frame, controller)


def _payload_identity(data: bytes) -> dict[str, Any]:
    return cross.payload_identity(data)


def _histogram(frame: bytes) -> list[int]:
    counts = [0] * 8
    for byte in frame:
        high, low = byte >> 4, byte & 0x0F
        if high > 7 or low > 7:
            raise StableCode0LumaLatinV3PackError("frame contains code above 7")
        counts[high] += 1
        counts[low] += 1
    return counts


def recipe_map() -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for controller in (0, 1):
        for row in range(8):
            for column in range(8):
                code = middle_code(controller, row, column)
                decoder: dict[str, Any]
                if controller == 0:
                    decoder = {
                        "transform": "identity",
                        "logical_row": row,
                        "logical_column": column,
                        "formula": "(row+column)%8",
                    }
                else:
                    decoder = {
                        "transform": "rotate_180_from_cs1",
                        **decode_cs2_cell(row, column),
                        "formula": "((7-row)+(7-column))%8",
                    }
                recipes.append(
                    {
                        "recipe_id": f"SCL3-CS{controller + 1}-R{row}-C{column}-M{code}",
                        "controller": controller,
                        "controller_name": f"CS{controller + 1}",
                        "controller_role": (
                            "CONTROLLER_SPECIFIC_INTERNAL_CONTROL"
                            if controller == 0
                            else "RED_FAMILY_PRIMARY_OBSERVATION"
                        ),
                        "physical_row": row,
                        "physical_column": column,
                        "local_roi": dict(
                            zip(
                                ("x", "y", "width", "height"),
                                _cell_bounds(row, column),
                                strict=True,
                            )
                        ),
                        "source": {"global_header": "active", "code": SOURCE_CODE},
                        "middle": {"global_header": "commented", "code": code},
                        "target": {"global_header": "active", "code": TARGET_CODE},
                        "target_repeat": {
                            "global_header": "active",
                            "code": TARGET_CODE,
                            "identical_frame": True,
                        },
                        "decoder": decoder,
                        "spatial_dither": False,
                    }
                )
    return recipes


def _boot_admission(ordinal: int) -> dict[str, Any]:
    return {
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


def source_authority_surface() -> dict[str, Any]:
    w11 = w11_pack.build_white_report()
    return {
        "authority_kind": "W11_COMPLETE_PLUS_CAMERA_VISIBLE_CLEAN_WHITE_REVIEW",
        "w11": {
            "campaign_id": w11["contract"]["campaign_id"],
            "contract_id": w11["contract_id"],
            "descriptor_id": w11["action"]["descriptor_id"],
            "action_id": w11["action"]["action_id"],
            "firmware": deepcopy(w11_pack.WHITE_ARTIFACTS[w11_pack.STAGE]),
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_call_count_for_action": 1,
            "visible_refreshes": 1,
            "action_must_not_be_retried": True,
        },
        "camera_review": {
            "kind": "mf1750-w11-post-white-retained-camera-visible-clean-white-review",
            "classification_state": "CAMERA_VISIBLE_CLEAN_WHITE_CONTAINMENT_REVIEW",
            "outcome": (
                "PASS_NO_OBVIOUS_V5_RESIDUAL_OR_GROSS_SCREEN_DEFECT_IN_THIS_"
                "RETAINED_FRAME"
            ),
            "camera_visible_clean_white_containment_review_passed": True,
            "camera_relative_only": True,
            "absolute_white_point_proven": False,
            "spatial_uniformity_proven": False,
            "qualified_white_or_gray_level": False,
        },
        "files": deepcopy(SOURCE_FILE_BINDINGS),
        "required_before_any_device_request": True,
        "required_before_claim_or_arm": True,
        "schedule_policy": {
            "branch": "ALTERNATIVE_FIRST_EXPERIMENT_AFTER_W11_WHITE_ONLY",
            "no_intervening_panel_refresh_since_w11_white_required": True,
            "not_sequential_after_luma_gray_mechanism_v2": True,
            "if_another_campaign_ran": (
                "REQUIRE_FRESH_INDEPENDENT_FACTORY_OTP_WHITE_AND_NEW_SUCCESSOR_BINDING"
            ),
            "operator_reconfirmation_required_before_diagnostic_and_run": True,
        },
    }


def build_report() -> dict[str, Any]:
    _validate_geometry()
    source_frame = _grid_frame("source")
    middle_frame = _grid_frame("middle")
    target_frame = _grid_frame("target")
    frames = (source_frame, middle_frame, target_frame, target_frame)
    actions: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True), 1
    ):
        item = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "branch": branch,
            "palette_source": "L535_RUNTIME",
            "global_header": header,
            "profile_id": cross.profile(header)["id"],
            "frame": base.frame_identity(frame),
            "cs1_dtm": _payload_identity(_controller_stream(frame, 0)),
            "cs2_dtm": _payload_identity(_controller_stream(frame, 1)),
            "transport_code_histogram": _histogram(frame),
            "prior_static_action_id": prior_action_id,
            "boot_admission": _boot_admission(ordinal),
            "automatic_dispatch": False,
        }
        descriptor = {
            "schema": "mf1750-stable-code0-luma-latin-action-descriptor-v3",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
        item["action_id"] = sha256_bytes(
            (
                "MF1750_STABLE_CODE0_LUMA_LATIN_ACTION_V3|"
                f"{VARIANT_KEY}|{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior_action_id = item["action_id"]
        actions.append(item)

    recipes = recipe_map()
    profiles = {name: cross.profile(name) for name in ("active", "commented")}
    source_authority = source_authority_surface()
    contract = {
        "schema": "mf1750-stable-code0-luma-latin-contract-v3",
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "base_route": BASE_ROUTE,
        "environment": ENVIRONMENT,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "profile_id": PROFILE_ID,
        "target_hue_registry": {
            "selected": TARGET_HUE_ID,
            "source_global_header": "active",
            "source_transport_code": SOURCE_CODE,
            "middle_global_header": "commented",
            "middle_transport_codes": list(range(8)),
            "target_global_header": "active",
            "target_transport_code": TARGET_CODE,
            "cs2_role": "RED_FAMILY_PRIMARY_OBSERVATION",
            "cs1_role": "CONTROLLER_SPECIFIC_INTERNAL_CONTROL",
            "controller_color_equivalence_claimed": False,
            "qualified_brightness_levels": 0,
        },
        "geometry": {
            "width": base.WIDTH,
            "height": base.HEIGHT,
            "controller_width": base.CONTROLLER_WIDTH,
            "grid_rows": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "candidate_cells_per_controller": 64,
            "candidate_cells_total_observations": 128,
            "middle_repeat_count_per_controller": 8,
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "grid_x1_local_exclusive": GRID_X1_EXCLUSIVE,
            "grid_y1_exclusive": GRID_Y1_EXCLUSIVE,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "cs1_layout": "latin_code=(row+column)%8",
            "cs2_layout": "rotate_180_of_cs1",
            "cs2_decoder": "logical=(7-row,7-column); code=(logical_row+logical_column)%8",
            "controller_color_equivalence_claimed": False,
            "spatial_dither": False,
        },
        "profiles": profiles,
        "profile_sequence": list(GLOBAL_HEADERS),
        "recipes": recipes,
        "actions": [
            {
                key: deepcopy(item[key])
                for key in (
                    "ordinal",
                    "role",
                    "driver_role",
                    "branch",
                    "palette_source",
                    "global_header",
                    "profile_id",
                    "descriptor_id",
                    "action_id",
                    "prior_static_action_id",
                    "boot_admission",
                    "automatic_dispatch",
                )
            }
            for item in actions
        ],
        "source_authority": source_authority,
        "source_gate_required_before_any_device_request": True,
        "action_count": 4,
        "one_driver_call_per_action": True,
        "one_visible_refresh_per_action": True,
        "l1_l2_l3_explicit_actions": True,
        "l4_identical_target_repeat": {
            "separate_action": True,
            "source_ordinal": 3,
            "repeat_ordinal": 4,
            "identical_frame_sha256": True,
            "identical_cs1_dtm_sha256": True,
            "identical_cs2_dtm_sha256": True,
            "automatic_dispatch": False,
            "autochain": False,
        },
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "unknown_commands": False,
        "local_hold_claimed": False,
        "spatial_dither": False,
        "runtime_lut": True,
        "factory_otp_in_main_campaign": False,
        "independent_factory_otp_white_containment_required": True,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "electrical_parameter_write": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
        "same_boot_prior_complete_required": True,
        "device_enforced_same_boot": True,
        "reboot_resume_allowed": False,
        "skip_ordinal_allowed": False,
        "arm_intent": ARM_INTENT,
        "execute_intent": EXECUTE_INTENT,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "camera_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "actions": actions,
        "contract": contract,
    }


def _read_bound_file(name: str) -> tuple[bytes, dict[str, Any] | None]:
    binding = SOURCE_FILE_BINDINGS[name]
    path = REPO_ROOT / binding["path"]
    if not path.is_file() or path.is_symlink():
        raise StableCode0LumaLatinV3PackError(f"source {name} missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise StableCode0LumaLatinV3PackError(f"source {name} file identity differs")
    if name == "photo":
        return payload, None
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StableCode0LumaLatinV3PackError(f"source {name} is not JSON") from error
    if not isinstance(value, dict):
        raise StableCode0LumaLatinV3PackError(f"source {name} root differs")
    canonical_wanted = binding.get("canonical_integrity_sha256")
    if canonical_wanted is not None:
        body = deepcopy(value)
        integrity = body.pop("integrity", None)
        if not isinstance(integrity, Mapping):
            raise StableCode0LumaLatinV3PackError(f"source {name} integrity missing")
        recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
        actual = sha256_bytes(canonical_json(body))
        if recorded != canonical_wanted or actual != canonical_wanted:
            raise StableCode0LumaLatinV3PackError(f"source {name} canonical identity differs")
    return payload, value


def validate_source_authority() -> dict[str, Any]:
    loaded: dict[str, dict[str, Any] | None] = {}
    for name in SOURCE_FILE_BINDINGS:
        _payload, loaded[name] = _read_bound_file(name)
    action = loaded["w11_complete"]
    claim = loaded["w11_claim"]
    review = loaded["camera_visible_clean_white_review"]
    capture = loaded["capture_sidecar"]
    relay = loaded["relay_protective_off"]
    if not all(isinstance(item, Mapping) for item in (action, claim, review, capture, relay)):
        raise StableCode0LumaLatinV3PackError("source JSON evidence set differs")
    expected = w11_pack.build_white_report()
    expected_action = expected["action"]
    terminal = action.get("terminal_report")
    driver = terminal.get("driver") if isinstance(terminal, Mapping) else None
    if (
        action.get("action") != expected_action
        or action.get("outcome") != "complete_pass"
        or action.get("claim_state") != "permanently_consumed_by_this_invocation"
        or action.get("visible_refreshes") != 1
        or action.get("network") != {"get": 5, "post": 2}
        or action.get("no_retry") is not True
        or action.get("no_recovery") is not True
        or action.get("no_autochain") is not True
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("campaign_complete") is not True
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("campaign_id") != expected["contract"]["campaign_id"]
        or terminal.get("contract_id") != expected["contract_id"]
        or terminal.get("transaction_descriptor_sha256")
        != expected_action["descriptor_id"]
        or terminal.get("action_id") != expected_action["action_id"]
        or not isinstance(driver, Mapping)
        or driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("pon_busy_seen") is not True
        or driver.get("drf_busy_seen") is not True
        or driver.get("pof_busy_seen") is not True
        or driver.get("operation_id") != 1
    ):
        raise StableCode0LumaLatinV3PackError("W11 COMPLETE deep semantics differ")
    if (
        claim.get("action") != expected_action
        or claim.get("boot_nonce") != action.get("boot_nonce")
        or claim.get("firmware_sha256") != action.get("firmware_sha256")
        or claim.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or claim.get("no_retry") is not True
        or claim.get("no_recovery") is not True
        or claim.get("no_autochain") is not True
    ):
        raise StableCode0LumaLatinV3PackError("W11 permanent claim differs")
    classification = review.get("classification")
    source_evidence = review.get("source_evidence")
    action_binding = review.get("action_binding")
    capture_binding = review.get("capture_binding")
    offline_review = review.get("offline_visual_review")
    if (
        review.get("kind")
        != "mf1750-w11-post-white-retained-camera-visible-clean-white-review"
        or review.get("campaign_id") != expected["contract"]["campaign_id"]
        or review.get("contract_id") != expected["contract_id"]
        or review.get("descriptor_id") != expected_action["descriptor_id"]
        or review.get("action_id") != expected_action["action_id"]
        or not isinstance(classification, Mapping)
        or classification.get("state")
        != "CAMERA_VISIBLE_CLEAN_WHITE_CONTAINMENT_REVIEW"
        or classification.get("camera_visible_clean_white_containment_review_passed")
        is not True
        or classification.get("absolute_white_point_proven") is not False
        or classification.get("spatial_uniformity_proven") is not False
        or classification.get("qualified_white_or_gray_level") is not False
        or not isinstance(action_binding, Mapping)
        or action_binding.get("terminal_state") != "COMPLETE"
        or action_binding.get("driver_call_count_for_action") != 1
        or action_binding.get("visible_refreshes") != 1
        or not isinstance(capture_binding, Mapping)
        or capture_binding.get("camera_relative_only") is not True
        or capture_binding.get("scope") != "full_panel"
        or not isinstance(offline_review, Mapping)
        or offline_review.get("camera_visible_white_field") is not True
        or offline_review.get("v5_4x8_colour_atlas_blocks_still_visible") is not False
        or not isinstance(source_evidence, Mapping)
    ):
        raise StableCode0LumaLatinV3PackError("camera-visible white review differs")
    for review_key, binding_key in (
        ("action_result", "w11_complete"),
        ("capture_sidecar", "capture_sidecar"),
        ("photo", "photo"),
        ("relay_post_action_protective_off", "relay_protective_off"),
    ):
        observed = source_evidence.get(review_key)
        expected_file = SOURCE_FILE_BINDINGS[binding_key]
        if (
            not isinstance(observed, Mapping)
            or observed.get("bytes") != expected_file["bytes"]
            or observed.get("file_sha256") != expected_file["file_sha256"]
        ):
            raise StableCode0LumaLatinV3PackError(
                f"camera review {review_key} binding differs"
            )
    if (
        relay.get("commanded_state") != "OFF"
        or relay.get("target_state") != "OFF"
        or relay.get("off_gate_passed") is not True
    ):
        raise StableCode0LumaLatinV3PackError("protective relay OFF differs")
    return {
        "verified": True,
        "w11_terminal_state": "COMPLETE",
        "w11_action_id": expected_action["action_id"],
        "camera_review_state": classification["state"],
        "camera_relative_only": True,
        "absolute_white_point_proven": False,
        "spatial_uniformity_proven": False,
        "schedule_policy": deepcopy(source_authority_surface()["schedule_policy"]),
        "files": deepcopy(SOURCE_FILE_BINDINGS),
    }


def identity_path() -> Path:
    return REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_identity.inc"


def main_config_path() -> Path:
    return REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_main_config.inc"


def driver_path() -> Path:
    return REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_driver.inc"


def _validate_compiled_sources(actions: list[dict[str, Any]]) -> str:
    """Bind all four host actions to the compiled C++ identity surface."""

    identity = identity_path().read_text(encoding="utf-8")
    main_config = main_config_path().read_text(encoding="utf-8")
    driver = driver_path().read_text(encoding="utf-8")
    required_identity = {
        CAMPAIGN_ID,
        BUILD_TAG,
        build_report()["contract_id"],
        "CS1_ACTIVE535__CS2_COMMENTED535",
        "ACTIVE_CODE0_CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_",
        "INTERNAL_CONTROL_UNCALIBRATED",
        *(item["descriptor_id"] for item in actions),
        *(item["action_id"] for item in actions),
        *(item["frame"]["sha256"] for item in actions),
        *(item["cs1_dtm"]["sha256"] for item in actions),
        *(item["cs2_dtm"]["sha256"] for item in actions),
        "ACTIVE_GLOBAL__CS1_ACTIVE535__CS2_COMMENTED535",
    }
    if not all(token in identity for token in required_identity):
        raise StableCode0LumaLatinV3PackError("compiled identity source differs")

    blocks = {
        int(match.group(1)): match.group(2)
        for match in re.finditer(
            r"SCL3_ACTION\(\s*(\d+),(.*?)(?=\n\s*SCL3_ACTION\(|\n};)",
            main_config,
            re.DOTALL,
        )
    }
    if set(blocks) != {1, 2, 3, 4}:
        raise StableCode0LumaLatinV3PackError("compiled action block set differs")
    for action in actions:
        block = blocks[action["ordinal"]]
        required = {
            f"EpdChromaGridRole::{action['driver_role']}",
            action["role"],
            action["branch"],
        }
        if action["ordinal"] == 4:
            required.update(
                {
                    "scl3::kL4DescriptorId",
                    "scl3::kL4ActionId",
                    "scl3::kL4PriorActionId",
                    "scl3::kL4FrameSha256",
                    "scl3::kL4Cs1DtmSha256",
                    "scl3::kL4Cs2DtmSha256",
                    "scl3::kL4FrameFnv1a",
                    "scl3::kL4Cs1DtmFnv1a",
                    "scl3::kL4Cs2DtmFnv1a",
                }
            )
        else:
            required.update(
                {
                    action["descriptor_id"],
                    action["action_id"],
                    action["frame"]["sha256"],
                    action["cs1_dtm"]["sha256"],
                    action["cs2_dtm"]["sha256"],
                    f"0x{action['frame']['fnv1a']:08X}UL",
                    f"0x{action['cs1_dtm']['fnv1a']:08X}UL",
                    f"0x{action['cs2_dtm']['fnv1a']:08X}UL",
                }
            )
            prior = action["prior_static_action_id"]
            required.add("nullptr" if prior is None else prior)
        if not all(token in block for token in required):
            raise StableCode0LumaLatinV3PackError(
                f"compiled action {action['ordinal']} binding differs"
            )
    if any(actions[2][key] != actions[3][key] for key in ("profile_id", "global_header", "driver_role")):
        raise StableCode0LumaLatinV3PackError("compiled L3/L4 effective profile differs")
    driver_markers = (
        "if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;",
        "if (secondController) {",
        "ph_lut::commented::kR20Payload",
        "ph_lut::commented::kTransmittedR20PrefixBytes",
        "ph_lut::active::kR20Payload",
        "ph_lut::active::kTransmittedR20PrefixBytes",
        "ph_lut::active::kTransmittedR20PrefixBytes == 535",
        "ph_lut::commented::kTransmittedR20PrefixBytes == 535",
    )
    if not all(marker in driver for marker in driver_markers):
        raise StableCode0LumaLatinV3PackError("compiled profile upload binding differs")
    return "FINAL_ALL_L1_L4_BOUND"


def artifacts_verified() -> bool:
    if not artifacts_are_sealed():
        return False
    expected = ARTIFACTS[VARIANT_KEY]
    for path, prefix in zip(artifact_paths(), ("bin", "elf"), strict=True):
        if not path.is_file() or path.is_symlink():
            return False
        payload = path.read_bytes()
        if (
            len(payload) != expected[f"{prefix}_bytes"]
            or sha256_bytes(payload) != expected[f"{prefix}_sha256"]
        ):
            return False
    return True


def dry_validate(*, verify_source: bool = True, verify_artifacts: bool = True) -> dict[str, Any]:
    report = build_report()
    contract = report["contract"]
    actions = report["actions"]
    if len(actions) != 4 or [item["ordinal"] for item in actions] != [1, 2, 3, 4]:
        raise StableCode0LumaLatinV3PackError("action sequence differs")
    if [item["global_header"] for item in actions] != list(GLOBAL_HEADERS):
        raise StableCode0LumaLatinV3PackError("global header sequence differs")
    if [item["driver_role"] for item in actions] != list(DRIVER_ROLES):
        raise StableCode0LumaLatinV3PackError("driver role sequence differs")
    if any(item["automatic_dispatch"] for item in actions):
        raise StableCode0LumaLatinV3PackError("automatic action dispatch leaked")
    if any(actions[index]["prior_static_action_id"] != actions[index - 1]["action_id"] for index in range(1, 4)):
        raise StableCode0LumaLatinV3PackError("static prior action chain differs")
    for controller in (0, 1):
        rows = [[middle_code(controller, row, col) for col in range(8)] for row in range(8)]
        if any(sorted(row_values) != list(range(8)) for row_values in rows):
            raise StableCode0LumaLatinV3PackError("Latin row permutation differs")
        if any(sorted(rows[row][col] for row in range(8)) != list(range(8)) for col in range(8)):
            raise StableCode0LumaLatinV3PackError("Latin column permutation differs")
        counts = [sum(value == code for row_values in rows for value in row_values) for code in range(8)]
        if counts != [8] * 8:
            raise StableCode0LumaLatinV3PackError("middle repeats per controller differ")
    if any(
        actions[2][key] != actions[3][key]
        for key in ("frame", "cs1_dtm", "cs2_dtm", "transport_code_histogram")
    ):
        raise StableCode0LumaLatinV3PackError("L4 target payload is not exact L3 repeat")
    if actions[2]["action_id"] == actions[3]["action_id"] or actions[2]["descriptor_id"] == actions[3]["descriptor_id"]:
        raise StableCode0LumaLatinV3PackError("L4 identity did not rotate")
    if (
        contract["target_hue_registry"]["cs2_role"] != "RED_FAMILY_PRIMARY_OBSERVATION"
        or contract["target_hue_registry"]["cs1_role"]
        != "CONTROLLER_SPECIFIC_INTERNAL_CONTROL"
        or contract["target_hue_registry"]["controller_color_equivalence_claimed"]
        is not False
    ):
        raise StableCode0LumaLatinV3PackError("controller interpretation differs")
    if any(
        contract[key] is not False
        for key in ("partial_refresh", "window_refresh", "local_hold_claimed", "spatial_dither", "retry", "automatic_recovery", "autochain")
    ):
        raise StableCode0LumaLatinV3PackError("forbidden capability leaked")
    authority = validate_source_authority() if verify_source else None
    compiled_paths = (identity_path(), main_config_path(), driver_path())
    identity_state = "MISSING"
    if all(path.is_file() for path in compiled_paths):
        identity_state = _validate_compiled_sources(actions)
    sealed = artifacts_are_sealed()
    verified_artifacts = artifacts_verified() if verify_artifacts and sealed else False
    if verify_artifacts and sealed and not verified_artifacts:
        raise StableCode0LumaLatinV3PackError("sealed artifacts differ")
    return {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-dry-validation",
        "result": (
            "PASS"
            if identity_state == "FINAL_ALL_L1_L4_BOUND"
            else "WAITING_FOR_IDENTITY"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "camera_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "source_authority": authority,
        "source_gate_required_before_any_device_request": True,
        "identity_state": identity_state,
        "action_count": 4,
        "l4_exact_payload_repeat": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": sealed,
        "artifacts_verified": verified_artifacts,
        "contract_id": report["contract_id"],
        "descriptor_ids": [item["descriptor_id"] for item in actions],
        "action_ids": [item["action_id"] for item in actions],
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
