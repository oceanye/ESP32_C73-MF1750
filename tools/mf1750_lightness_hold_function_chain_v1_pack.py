#!/usr/bin/env python3
"""Freeze the five-action lightness-construction/local-HOLD V1 campaign.

This module is deliberately offline.  L1--L3 are byte-identical to the
sealed stable-code0 Latin V3 packed frames.  H1/H2 use the live-reviewed
clean-PTLW V2 transport: full code-7 SRAM prestage, one inclusive PTLW per
controller, one uniform cropped DTM, then PON/DRF00/POF00.

The source authority binds the current V3 white-successor COMPLETE action,
retained -4 capture/photo, protective relay-OFF receipt, and independent
camera-visible clean-white review.  Absolute white point and spatial
uniformity remain explicitly unproven.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v2_pack as clean  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import mf1750_stable_code0_luma_latin_v3_pack as v3  # noqa: E402


VARIANT_KEY = "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1"
BUILD_TAG = "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_2026-09-01"
TEST_ID = "EC5-LIGHTNESS-HOLD-FUNCTION-CHAIN-V1"
CAMPAIGN_ID = "EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1"
DEVICE_API_VERSION = "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_DEVICE_V1"
IDENTITY_REVISION = "lightness-hold-function-chain-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_STABLE_CODE0_LATIN_CONSTRUCTION_PLUS_CLEAN_PTLW_"
    "CROSS_LUT_LOCAL_HOLD_CANDIDATES_ONLY"
)
ENVIRONMENT = "ec5_lightness_hold_function_chain_v1"
BUILD_ROOT = "b-lightness-hold-function-chain-v1"
BASE_ROUTE = "/api/ec5/lightness-hold-function-chain-v1"
NVS_NAMESPACE = "lhfc_v1"
NVS_KEY = "cur_lhfc1"
NVS_BOOT_KEY = "boot_lh1"
ARM_INTENT = "ARM_ONE_FIXED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_ACTION_ONCE"

ARTIFACTS = {
    VARIANT_KEY: {
        "bin_bytes": 803_712,
        "bin_sha256": (
            "3f49ba07e497443813f4fb3f5281ed510953ffcfdb8db8a73c4d9466551e30ff"
        ),
        "elf_bytes": 13_312_748,
        "elf_sha256": (
            "ded43d84b5897b5793e3f25c84bf96d2118ae775b71bf8a61d5cbe1c1502fd45"
        ),
    }
}

WIDTH = v3.base.WIDTH
HEIGHT = v3.base.HEIGHT
CONTROLLER_WIDTH = v3.base.CONTROLLER_WIDTH
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
GRID_X0 = v3.GRID_X0
GRID_Y0 = v3.GRID_Y0
GRID_X1_EXCLUSIVE = v3.GRID_X1_EXCLUSIVE
GRID_Y1_EXCLUSIVE = v3.GRID_Y1_EXCLUSIVE
GRID_ROWS = v3.GRID_ROWS
GRID_COLUMNS = v3.GRID_COLUMNS
CELL_WIDTH = v3.CELL_WIDTH
CELL_HEIGHT = v3.CELL_HEIGHT
GAP_X = v3.GAP_X
GAP_Y = v3.GAP_Y
PRELOAD_CODE = 7
PRELOAD_DTM = bytes([0x77]) * CONTROLLER_DTM_BYTES
PRELOAD_DTM_SHA256 = identity.sha256(PRELOAD_DTM)
PRELOAD_DTM_FNV1A = identity.fnv1a(PRELOAD_DTM)


@dataclass(frozen=True)
class Window:
    x: int
    y: int
    width: int
    height: int
    cs1_code: int
    cs2_code: int


# The candidate grid occupies y=[40,560).  Both probes are strictly in the
# remaining white side bands and use even x/width for packed 4-bpp transport.
H1_WINDOW = Window(64, 8, 384, 24, 5, 5)
H2_WINDOW = Window(64, 568, 384, 24, 6, 6)
HOLD_WINDOWS = (H1_WINDOW, H2_WINDOW)
HOLD_GLOBAL_HEADERS = ("active", "commented")
HOLD_CODES = (5, 6)

ROLES = (
    "L1_FIXED_ACTIVE_SOURCE_CODE7",
    "L2_COMMENTED_MIDDLE_LATIN_C0_C7",
    "L3_FIXED_ACTIVE_TARGET_CODE0",
    "H1_ACTIVE_CODE5_TOP_PROBE_HOLD_GRID",
    "H2_COMMENTED_CODE6_BOTTOM_PROBE_HOLD_GRID_AND_H1",
)
DRIVER_ROLES = ("Source", "Mid", "Target", "ReverseSource", "ReverseTarget")
GLOBAL_HEADERS = ("active", "commented", "active", "active", "commented")
BRANCHES = tuple(f"{VARIANT_KEY}_{role}" for role in ROLES)

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

SOURCE_ROOT = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_20260901_V1"
)
SOURCE_BINDINGS: dict[str, dict[str, Any]] = {
    "white_action": {
        "path": "action-01-factory-otp-white.json",
        "bytes": 36_987,
        "sha256": "9ebc3ca4f32ceba8cbb356aece938d28e922e016f875ab10aa082338993b509b",
        "canonical_sha256": (
            "555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b"
        ),
    },
    "retained_capture": {
        "path": "post-white-retained-camera-attempt-01-exposure-m4.capture.json",
        "bytes": 5_321,
        "sha256": "479c7451ca87c60cbef614895e3a3866a8415d0f3ccf3ad82668ae321bb459ae",
        "canonical_sha256": (
            "7e9f7b6b9edb1e246da06316153e24e846761bc1c02fdf3a02fa5d1384ac7362"
        ),
    },
    "retained_photo": {
        "path": "post-white-retained-camera-attempt-01-exposure-m4.jpg",
        "bytes": 1_014_449,
        "sha256": "f04bc44ad4e92007f7ffd2a730a28fe602acf18d34b98d2540c5959c7a46d92a",
        "canonical_sha256": None,
    },
    "relay_off": {
        "path": "relay-post-white-off.json",
        "bytes": 1_803,
        "sha256": "1fa84d45b7374fce680bdadcde0edb2142adfa408b5511edfa75dd20f0b09626",
        "canonical_sha256": (
            "5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400"
        ),
    },
    "clean_white_review": {
        "path": "post-white-retained-camera-attempt-01-exposure-m4.clean-white-review.json",
        "bytes": 4_367,
        "sha256": "50ce755e3ed04790819c326bbbb1e6a2fdc3c6b587899f02b00da588d5e2d625",
        "canonical_sha256": (
            "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40"
        ),
    },
}
SOURCE_WHITE_ACTION_ID = (
    "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f"
)
SOURCE_WHITE_CONTRACT_ID = (
    "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377"
)
SOURCE_CAPTURE_ID = (
    "85d78b0fbcf78162e5c9a6a0c618e2ae8f9f815ade2e61d4ff481b80cef80e34"
)
SOURCE_REVIEW_ID = (
    "b0a62b0c7dbf178fa6a2763d0bebf417b61dda6bd86bab701c84f658ae2ba96f"
)

# These hashes are an explicit non-regression boundary.  The new pack imports
# V3 behavior; it never edits or regenerates the V3 authority sources.
V3_FROZEN_SOURCE_SHA256 = {
    "tools/mf1750_stable_code0_luma_latin_v3_pack.py": (
        "f791c6310a0481d5f499df0b49dc7cf6f74df5957195d96f29ccd91b57b05436"
    ),
    "src/ec5_stable_code0_luma_latin_v3_identity.inc": (
        "71dfbafa1b40f17524d51a81879358ea4c97d204535734e2f77f61eec58f01ce"
    ),
    "src/ec5_stable_code0_luma_latin_v3_main_config.inc": (
        "dca1869ed1fec2c0579a8ef6d5bbb16bbe919a369a164ea69d2baaf10c6a4fe4"
    ),
    "src/ec5_stable_code0_luma_latin_v3_driver.inc": (
        "1d4e2154f8e2d9092dd45fcdc347e10cd3bc283f7e8731ddb1e361f0805594a7"
    ),
    "src/ec5_stable_code0_luma_latin_v3_main.cpp": (
        "740572e13a6d9fc9ff8291ce49d91a50fb434814135e6e35d0520c2fef14f906"
    ),
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def ptlw_payload(window: Window) -> bytes:
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


PTLW_PAYLOADS = tuple(ptlw_payload(window) for window in HOLD_WINDOWS)
CROPPED_DTM_BYTES = tuple(
    window.width * window.height // 2 for window in HOLD_WINDOWS
)
TARGET_DTMS = tuple(
    bytes([(code << 4) | code]) * byte_count
    for code, byte_count in zip(HOLD_CODES, CROPPED_DTM_BYTES, strict=True)
)
TARGET_DTM_SHA256 = tuple(identity.sha256(value) for value in TARGET_DTMS)
TARGET_DTM_FNV1A = tuple(identity.fnv1a(value) for value in TARGET_DTMS)
COMBINED_DTMS = tuple(PRELOAD_DTM + value for value in TARGET_DTMS)
COMBINED_DTM_SHA256 = tuple(identity.sha256(value) for value in COMBINED_DTMS)
COMBINED_DTM_FNV1A = tuple(identity.fnv1a(value) for value in COMBINED_DTMS)


def _set_rect(frame: bytearray, window: Window) -> None:
    row_bytes = WIDTH // 2
    pair_by_controller = (
        (window.cs1_code << 4) | window.cs1_code,
        (window.cs2_code << 4) | window.cs2_code,
    )
    for controller, pair in enumerate(pair_by_controller):
        global_x = controller * CONTROLLER_WIDTH + window.x
        for y in range(window.y, window.y + window.height):
            start = y * row_bytes + global_x // 2
            frame[start : start + window.width // 2] = bytes([pair]) * (
                window.width // 2
            )


def _controller_stream(frame: bytes, controller: int) -> bytes:
    return v3._controller_stream(frame, controller)  # noqa: SLF001


def _histogram(frame: bytes) -> list[int]:
    counts = [0] * 8
    for value in frame:
        counts[value >> 4] += 1
        counts[value & 0x0F] += 1
    return counts


def _frame_identity(frame: bytes) -> dict[str, Any]:
    return {
        "bytes": len(frame),
        "sha256": sha256_bytes(frame),
        "fnv1a": identity.fnv1a(frame),
        "histogram": _histogram(frame),
    }


def _dtm_identity(payload: bytes) -> dict[str, Any]:
    return {
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "fnv1a": identity.fnv1a(payload),
    }


def _frames() -> tuple[bytes, ...]:
    l1 = v3._grid_frame("source")  # noqa: SLF001
    l2 = v3._grid_frame("middle")  # noqa: SLF001
    l3 = v3._grid_frame("target")  # noqa: SLF001
    h1 = bytearray(l3)
    _set_rect(h1, H1_WINDOW)
    h2 = bytearray(h1)
    _set_rect(h2, H2_WINDOW)
    return l1, l2, l3, bytes(h1), bytes(h2)


def _descriptor(item: Mapping[str, Any]) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "schema": "mf1750-lightness-hold-function-chain-descriptor-v1",
                "variant": VARIANT_KEY,
                **item,
            }
        )
    )


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return sha256_bytes(
        (
            "MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def source_authority_surface() -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name, binding in SOURCE_BINDINGS.items():
        path = SOURCE_ROOT / str(binding["path"])
        files[name] = {
            **deepcopy(binding),
            "repo_relative_path": path.relative_to(REPO_ROOT).as_posix(),
            "present": path.is_file(),
        }
    review = files["clean_white_review"]
    sealed = all(item["present"] for item in files.values())
    missing = [name for name, item in files.items() if not item["present"]]
    return {
        "authority_kind": (
            "V3_WHITE_SUCCESSOR_COMPLETE_CAPTURE_RELAY_OFF_PLUS_"
            "INDEPENDENT_CLEAN_WHITE_REVIEW"
        ),
        "required_before_any_device_request": True,
        "sealed": sealed,
        "state": "SEALED" if sealed else "UNSEALED_MISSING_CLEAN_WHITE_REVIEW",
        "missing_requirements": missing,
        "source_campaign_id": (
            "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1"
        ),
        "source_contract_id": SOURCE_WHITE_CONTRACT_ID,
        "source_action_id": SOURCE_WHITE_ACTION_ID,
        "source_capture_id": SOURCE_CAPTURE_ID,
        "source_review_id": SOURCE_REVIEW_ID,
        "camera_relative_only": True,
        "absolute_white_point_proven": False,
        "spatial_uniformity_proven": False,
        "files": files,
        "review_digest_invented": False,
        "review_binding": {
            "path": review["repo_relative_path"],
            "bytes": review["bytes"],
            "sha256": review["sha256"],
        },
    }


def _build_actions() -> list[dict[str, Any]]:
    frames = _frames()
    prior: str | None = None
    actions: list[dict[str, Any]] = []
    for index, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True)
    ):
        ordinal = index + 1
        if ordinal <= 3:
            cs1 = _dtm_identity(_controller_stream(frame, 0))
            cs2 = _dtm_identity(_controller_stream(frame, 1))
            transport: dict[str, Any] = {
                "kind": "V3_EXACT_PACKED_FULL_FRAME_PER_CONTROLLER",
                "prestage_dtm": None,
                "target_dtm": None,
                "ptlw_payload_hex": None,
                "ptlw_writes_per_controller": 0,
                "cs1_dtm": cs1,
                "cs2_dtm": cs2,
            }
        else:
            hold_index = ordinal - 4
            target = _dtm_identity(TARGET_DTMS[hold_index])
            combined = _dtm_identity(COMBINED_DTMS[hold_index])
            transport = {
                "kind": "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP",
                "prestage_dtm": _dtm_identity(PRELOAD_DTM),
                "target_dtm": target,
                "ptlw_payload_hex": PTLW_PAYLOADS[hold_index].hex(),
                "ptlw_writes_per_controller": 1,
                "cs1_dtm": deepcopy(combined),
                "cs2_dtm": deepcopy(combined),
            }
        action: dict[str, Any] = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "branch": branch,
            "global_header": header,
            "profile_id": (
                clean.PROFILES[header]["id"]
                if header in clean.PROFILES
                else None
            ),
            "frame": _frame_identity(frame),
            "transport": transport,
            "prior_action_id": prior,
            "visible_refresh_requests": 1,
            "retry": False,
            "recovery": False,
            "autochain": False,
        }
        descriptor_source = deepcopy(action)
        descriptor_id = _descriptor(descriptor_source)
        action["descriptor_id"] = descriptor_id
        action_id = _action_id(ordinal, descriptor_id)
        action["action_id"] = action_id
        prior = action_id
        actions.append(action)
    return actions


def _assert_geometry() -> None:
    if (GRID_X0, GRID_Y0, GRID_X1_EXCLUSIVE, GRID_Y1_EXCLUSIVE) != (
        20,
        40,
        492,
        560,
    ):
        raise RuntimeError("V3 packed-grid geometry drifted")
    for window in HOLD_WINDOWS:
        if (
            window.x < 0
            or window.y < 0
            or window.width <= 0
            or window.height <= 0
            or window.x % 2
            or window.width % 2
            or window.x + window.width > CONTROLLER_WIDTH
            or window.y + window.height > HEIGHT
        ):
            raise RuntimeError("HOLD probe geometry invalid")
        overlaps_grid = not (
            window.x + window.width <= GRID_X0
            or GRID_X1_EXCLUSIVE <= window.x
            or window.y + window.height <= GRID_Y0
            or GRID_Y1_EXCLUSIVE <= window.y
        )
        if overlaps_grid:
            raise RuntimeError("HOLD probe overlaps V3 candidate grid")
    if H1_WINDOW.y + H1_WINDOW.height > GRID_Y0:
        raise RuntimeError("H1 is not confined to the top white band")
    if H2_WINDOW.y < GRID_Y1_EXCLUSIVE:
        raise RuntimeError("H2 is not confined to the bottom white band")
    if PRELOAD_DTM_SHA256 != clean.PRELOAD_DTM_SHA256:
        raise RuntimeError("clean-PTLW code7 prestage identity drifted")


def build_report() -> dict[str, Any]:
    _assert_geometry()
    actions = _build_actions()
    source = source_authority_surface()
    contract = {
        "schema": "mf1750-lightness-hold-function-chain-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "action_order": list(ROLES),
        "global_header_sequence": list(GLOBAL_HEADERS),
        "candidate_grid": {
            "rows": GRID_ROWS,
            "columns_per_controller": GRID_COLUMNS,
            "x0_local": GRID_X0,
            "y0": GRID_Y0,
            "x1_local_exclusive": GRID_X1_EXCLUSIVE,
            "y1_exclusive": GRID_Y1_EXCLUSIVE,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "cells_total": 128,
        },
        "hold_probes": [asdict(window) for window in HOLD_WINDOWS],
        "hold_probe_nonoverlap_with_grid": True,
        "clean_ptlw_transport": {
            "mechanical_source_contract_id": clean.CONTRACT_ID,
            "full_code7_prestage_bytes_per_controller": CONTROLLER_DTM_BYTES,
            "full_code7_prestage_sha256": PRELOAD_DTM_SHA256,
            "ptlw_command": 0x83,
            "ptlw_mode": 1,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_payloads_hex": [value.hex() for value in PTLW_PAYLOADS],
            "cropped_dtm_bytes_per_controller": list(CROPPED_DTM_BYTES),
            "target_dtm_sha256": list(TARGET_DTM_SHA256),
            "combined_dtm_sha256": list(COMBINED_DTM_SHA256),
            "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
            "repeat_ptlw_after_pon_busy": False,
            "action_stage_cdi": False,
            "action_stage_btst2": False,
            "command_0x86": False,
        },
        "source_authority": source,
        "source_authority_sealed": source["sealed"],
        "live_authorized": source["sealed"],
        "factory_white_successor_embedded": False,
        "spatial_dither": False,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "controller_color_equivalence_claimed": False,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
    }
    contract_id = sha256_bytes(canonical_json(contract))
    return {
        "schema_version": 1,
        "kind": "mf1750-lightness-hold-function-chain-v1-offline-identities",
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
        "contract_id": contract_id,
        "actions": actions,
        "contract": contract,
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise RuntimeError(f"authority file is not an object: {path}")
    return value


def validate_v3_non_regression() -> dict[str, Any]:
    checked: dict[str, str] = {}
    for relative, wanted in V3_FROZEN_SOURCE_SHA256.items():
        path = REPO_ROOT / relative
        actual = sha256_bytes(path.read_bytes())
        if actual != wanted:
            raise RuntimeError(f"frozen V3 source differs: {relative}")
        checked[relative] = actual
    original = v3.build_report()["actions"][:3]
    current = _build_actions()[:3]
    for old, new in zip(original, current, strict=True):
        for key in ("frame", "cs1_dtm", "cs2_dtm"):
            new_value = (
                new["frame"] if key == "frame" else new["transport"][key]
            )
            if old[key] != new_value:
                raise RuntimeError(f"new L{old['ordinal']} {key} differs from V3")
    return {"verified": True, "source_sha256": checked, "exact_l1_l3": True}


def validate_source_authority(*, require_sealed: bool = True) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    missing: list[str] = []
    for name, binding in SOURCE_BINDINGS.items():
        path = SOURCE_ROOT / str(binding["path"])
        if not path.is_file():
            missing.append(name)
            continue
        payload = path.read_bytes()
        if binding["bytes"] is None or binding["sha256"] is None:
            raise RuntimeError(f"unsealed authority file unexpectedly exists: {name}")
        if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["sha256"]:
            raise RuntimeError(f"source authority file identity differs: {name}")
        verified[name] = {
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }

    action = _load_json(SOURCE_ROOT / SOURCE_BINDINGS["white_action"]["path"])
    capture = _load_json(SOURCE_ROOT / SOURCE_BINDINGS["retained_capture"]["path"])
    relay = _load_json(SOURCE_ROOT / SOURCE_BINDINGS["relay_off"]["path"])
    review = _load_json(
        SOURCE_ROOT / SOURCE_BINDINGS["clean_white_review"]["path"]
    )
    canonical_values = {
        "white_action": action.get("integrity", {}).get("sha256"),
        "retained_capture": capture.get("integrity", {}).get("sha256"),
        "relay_off": relay.get("integrity", {}).get("canonical_sha256"),
        "clean_white_review": review.get("integrity", {}).get("sha256"),
    }
    for name, actual in canonical_values.items():
        wanted = SOURCE_BINDINGS[name]["canonical_sha256"]
        if actual != wanted:
            raise RuntimeError(f"source authority canonical identity differs: {name}")
        verified[name]["canonical_sha256"] = actual
    if (
        action.get("outcome") != "complete_pass"
        or action.get("visible_refreshes") != 1
        or action.get("terminal_report", {}).get("valid") is not True
        or action.get("terminal_report", {}).get("result") is not True
        or action.get("terminal_report", {}).get("driver_call_count_for_action")
        != 1
        or action.get("action", {}).get("action_id") != SOURCE_WHITE_ACTION_ID
    ):
        raise RuntimeError("source white action is not the exact COMPLETE result")
    if (
        capture.get("action_id") != SOURCE_WHITE_ACTION_ID
        or capture.get("capture_id") != SOURCE_CAPTURE_ID
        or capture.get("contract_id") != SOURCE_WHITE_CONTRACT_ID
        or capture.get("photo", {}).get("sha256")
        != SOURCE_BINDINGS["retained_photo"]["sha256"]
        or capture.get("camera", {}).get("effective_settings_after_frame", {}).get(
            "exposure"
        )
        != -4
    ):
        raise RuntimeError("source retained capture binding differs")
    if (
        relay.get("commanded_state") != "OFF"
        or relay.get("off_gate_passed") is not True
        or relay.get("contact_switch_performed") is not True
    ):
        raise RuntimeError("source protective relay-OFF receipt differs")

    sealed = not missing
    if sealed:
        if (
            review.get("classification", {}).get("state")
            != "CAMERA_VISIBLE_CLEAN_WHITE_CONTAINMENT_REVIEW"
            and review.get("classification", {}).get("state")
            != "CAMERA_VISIBLE_CLEAN_WHITE_REVIEW"
        ):
            raise RuntimeError("clean-white review state differs")
        if (
            review.get("classification", {}).get("verdict") != "PASS"
            or review.get("capture_id") != SOURCE_CAPTURE_ID
            or review.get("review_id") != SOURCE_REVIEW_ID
            or review.get("action_id") != SOURCE_WHITE_ACTION_ID
            or review.get("integrity", {}).get("sha256")
            != "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40"
        ):
            raise RuntimeError("clean-white review does not authorize a fresh source")
    if require_sealed and not sealed:
        raise RuntimeError(
            "source authority is unsealed: missing independent clean-white review"
        )
    return {
        "verified_existing_files": verified,
        "sealed": sealed,
        "state": "SEALED" if sealed else "UNSEALED_MISSING_CLEAN_WHITE_REVIEW",
        "missing": missing,
        "network_accessed": False,
        "hardware_accessed": False,
    }


def identity_path() -> Path:
    return REPO_ROOT / "src/ec5_lightness_hold_function_chain_v1_identity.inc"


def main_config_path() -> Path:
    return REPO_ROOT / "src/ec5_lightness_hold_function_chain_v1_main_config.inc"


def driver_path() -> Path:
    return REPO_ROOT / "src/ec5_lightness_hold_function_chain_v1_driver.inc"


def artifact_dir() -> Path:
    return REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT


def artifacts_are_sealed() -> bool:
    binding = ARTIFACTS[VARIANT_KEY]
    return all(
        isinstance(binding[key], int) and binding[key] > 0
        if key.endswith("_bytes")
        else isinstance(binding[key], str)
        and len(binding[key]) == 64
        and set(binding[key]) <= set("0123456789abcdef")
        for key in ("bin_bytes", "bin_sha256", "elf_bytes", "elf_sha256")
    )


def validate_artifacts() -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise RuntimeError("lightness-HOLD V1 artifact identities are unsealed")
    binding = ARTIFACTS[VARIANT_KEY]
    checked: dict[str, Any] = {}
    for stem in ("bin", "elf"):
        path = artifact_dir() / f"firmware.{stem}"
        payload = path.read_bytes()
        if (
            len(payload) != binding[f"{stem}_bytes"]
            or sha256_bytes(payload) != binding[f"{stem}_sha256"]
        ):
            raise RuntimeError(f"lightness-HOLD V1 firmware.{stem} differs")
        checked[stem] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
    return checked


def dry_validate(
    *, require_source_sealed: bool = False, verify_artifacts: bool = False
) -> dict[str, Any]:
    report = build_report()
    v3_boundary = validate_v3_non_regression()
    authority = validate_source_authority(require_sealed=require_source_sealed)
    if report["contract"]["source_authority_sealed"] is not authority["sealed"]:
        raise RuntimeError("compiled source-authority seal state differs")
    if [item["ordinal"] for item in report["actions"]] != [1, 2, 3, 4, 5]:
        raise RuntimeError("five-action order differs")
    artifacts = validate_artifacts() if verify_artifacts else None
    return {
        "kind": "mf1750-lightness-hold-function-chain-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "network_accessed": False,
        "source_authority": authority,
        "v3_non_regression": v3_boundary,
        "contract_id": report["contract_id"],
        "descriptor_ids": [item["descriptor_id"] for item in report["actions"]],
        "action_ids": [item["action_id"] for item in report["actions"]],
        "artifacts_verified": verify_artifacts,
        "artifacts": artifacts,
    }


_REPORT = build_report()
CONTRACT_ID = "ad14f5394a5c6e284885aa504ea0d99fec0ccb1dcf8053759dba025b8606f3e3"
DESCRIPTOR_IDS = (
    "db65ab65f9f32e1070af5c21c3d6f45d94dcd1bf7b7055732ded454c5e0bea47",
    "3bbeb6a06d2ec9bbb50b28c798414d2db1d624710ce394376326b578fe46b4d3",
    "7fc5609667d673d59051fe08e6fec08fe92e91d87e6920f3897a35229913276f",
    "af5bbbc6cfacb06b0f6ed3acb98e327723d4b60f8f69bac0002a2c2f4389a182",
    "4a55af059f6abad6f55bd7647068cd55e5962dac60cc9f9ef8246b4fdeff6407",
)
ACTION_IDS = (
    "d21f725a283b7f6cb33f8ee8b8e0351e8d1698addf90b7431ce205eff83caf60",
    "221cd4c242a37fde29dfb7b98066973523be041dddff015f4094e87d8be887fa",
    "af6aa5c8a62d212da2a53d440c1798aa82dbc0dae45a47767bb791a2ef49d32f",
    "69f639ae9523cb0d656c56adea605b32ee1adf5634014b4f0b90d89e4d579156",
    "3e9b5a096ee556caf8cb7c87df7a2c7fb94f9e53621d03c93fd013cc6fa41e7a",
)
if _REPORT["contract_id"] != CONTRACT_ID:
    raise RuntimeError("lightness-HOLD V1 contract identity drifted")
if tuple(item["descriptor_id"] for item in _REPORT["actions"]) != DESCRIPTOR_IDS:
    raise RuntimeError("lightness-HOLD V1 descriptor identities drifted")
if tuple(item["action_id"] for item in _REPORT["actions"]) != ACTION_IDS:
    raise RuntimeError("lightness-HOLD V1 action identities drifted")


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
