#!/usr/bin/env python3
"""Offline identity pack for the post-G3 position-balanced HOLD successor.

The two visible actions are H1/H2 only.  The source is the exact COMPLETE G3
result of EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3.  A G4 result is a hard
conflict: this successor must never be used after the optional repeat.
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
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as source_pack,
)


class PositionBalancedGrayHoldPackError(RuntimeError):
    """Raised when a frozen identity or source gate differs."""


VARIANT_KEY = "POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1"
BUILD_TAG = "MF1750_EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_2026-09-01"
TEST_ID = "EC5-POSITION-BALANCED-GRAY-HOLD-SUCCESSOR-V1"
CAMPAIGN_ID = "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1"
DEVICE_API_VERSION = "MF1750_EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_DEVICE_V1"
IDENTITY_REVISION = "position-balanced-gray-hold-successor-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_F1_G3_CANDIDATE_SPECIFIC_CLEAN_PTLW_LOCAL_HOLD_QUALIFICATION_ONLY"
)
ENVIRONMENT = "ec5_position_balanced_gray_hold_successor_v1"
BUILD_ROOT = "b-position-balanced-gray-hold-successor-v1"
BASE_ROUTE = "/api/ec5/position-balanced-gray-hold-successor-v1"
NVS_NAMESPACE = "pbghs_v1"
NVS_KEY = "cur_pbghs1"
NVS_BOOT_KEY = "boot_pbg1"
ARM_INTENT = "ARM_ONE_FIXED_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_ACTION_ONCE"

SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_CONTRACT_ID = "a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88"
SOURCE_G3_DESCRIPTOR_ID = (
    "094f11ac566bf1f2d4fd0105ad52f1b463cb85605a41c1969b560dcb1982d775"
)
SOURCE_G3_ACTION_ID = "f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee"
SOURCE_G4_DESCRIPTOR_ID = (
    "6e76dfed0d2dc2f5c4dfbb82db5f44a918fdaacdf099e03e66b3fcfe8276d9f1"
)
SOURCE_G4_ACTION_ID = "a7d2d3390c6c0803eb5f4098592022c344f49c06141ca798f97fcb40ef1c3947"
SOURCE_OUTPUT_ROOT = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_20260901_V3"
)
SOURCE_G3_PATH = SOURCE_OUTPUT_ROOT / "action-03-g3-active-c3-c7-target.json"
SOURCE_G4_PATH = (
    SOURCE_OUTPUT_ROOT / "action-04-g4-active-c3-c7-identical-target-repeat.json"
)

WIDTH = 1024
HEIGHT = 600
CONTROLLER_WIDTH = 512
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
GRID_X0 = source_pack.GRID_X0
GRID_Y0 = source_pack.GRID_Y0
GRID_X1_EXCLUSIVE = source_pack.GRID_X1_EXCLUSIVE
GRID_Y1_EXCLUSIVE = source_pack.GRID_Y1_EXCLUSIVE
GRID_ROWS = source_pack.GRID_ROWS
GRID_COLUMNS = source_pack.GRID_COLUMNS
CELL_WIDTH = source_pack.CELL_WIDTH
CELL_HEIGHT = source_pack.CELL_HEIGHT
GAP_X = source_pack.GAP_X
GAP_Y = source_pack.GAP_Y
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


# Preserve all 128 G3 candidates.  The probes occupy top/bottom white bands,
# stay within local x<400, and retain packed-4bpp byte alignment.
H1_WINDOW = Window(64, 8, 320, 24, 5, 5)
H2_WINDOW = Window(64, 568, 320, 24, 6, 6)
HOLD_WINDOWS = (H1_WINDOW, H2_WINDOW)
HOLD_CODES = (5, 6)
GLOBAL_HEADERS = ("active", "commented")
ROLES = (
    "H1_ACTIVE_CODE5_TOP_WHITE_BAND_HOLD_RETAIN_ALL_G3",
    "H2_COMMENTED_CODE6_BOTTOM_WHITE_BAND_HOLD_RETAIN_ALL_G3_AND_H1",
)
DRIVER_ROLES = ("ReverseSource", "ReverseTarget")
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

ARTIFACTS: dict[str, int | str] = {
    "bin_bytes": 800_864,
    "bin_sha256": "5a0d80b7391ae8f171747a1505521ff7193757bef86bf5e34bfb1f5be2d95db8",
    "elf_bytes": 13_307_848,
    "elf_sha256": "c7c5f1467afef0d496327ea2b086daf6a455e5de174e071f34b4f4d7ee6fecf1",
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


def ptlw_payload(window: Window) -> bytes:
    xe = window.x + window.width - 1
    ye = window.y + window.height - 1
    return bytes(
        (
            window.x >> 8,
            window.x & 0xFF,
            xe >> 8,
            xe & 0xFF,
            window.y >> 8,
            window.y & 0xFF,
            ye >> 8,
            ye & 0xFF,
            0x01,
        )
    )


PTLW_PAYLOADS = tuple(ptlw_payload(item) for item in HOLD_WINDOWS)
CROPPED_DTM_BYTES = tuple(item.width * item.height // 2 for item in HOLD_WINDOWS)
TARGET_DTMS = tuple(
    bytes([(code << 4) | code]) * byte_count
    for code, byte_count in zip(HOLD_CODES, CROPPED_DTM_BYTES, strict=True)
)
TARGET_DTM_SHA256 = tuple(identity.sha256(item) for item in TARGET_DTMS)
TARGET_DTM_FNV1A = tuple(identity.fnv1a(item) for item in TARGET_DTMS)
COMBINED_DTMS = tuple(PRELOAD_DTM + item for item in TARGET_DTMS)
COMBINED_DTM_SHA256 = tuple(identity.sha256(item) for item in COMBINED_DTMS)
COMBINED_DTM_FNV1A = tuple(identity.fnv1a(item) for item in COMBINED_DTMS)


def _set_rect(frame: bytearray, window: Window) -> None:
    row_bytes = WIDTH // 2
    pairs = (
        (window.cs1_code << 4) | window.cs1_code,
        (window.cs2_code << 4) | window.cs2_code,
    )
    for controller, pair in enumerate(pairs):
        x = controller * CONTROLLER_WIDTH + window.x
        for y in range(window.y, window.y + window.height):
            start = y * row_bytes + x // 2
            frame[start : start + window.width // 2] = bytes([pair]) * (
                window.width // 2
            )


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


def _frames() -> tuple[bytes, bytes]:
    g3 = source_pack._grid_frame("target")  # noqa: SLF001
    h1 = bytearray(g3)
    _set_rect(h1, H1_WINDOW)
    h2 = bytearray(h1)
    _set_rect(h2, H2_WINDOW)
    return bytes(h1), bytes(h2)


def _descriptor(item: Mapping[str, Any]) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "schema": "mf1750-position-balanced-gray-hold-successor-descriptor-v1",
                "variant": VARIANT_KEY,
                **item,
            }
        )
    )


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return sha256_bytes(
        (
            "MF1750_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def _build_actions() -> list[dict[str, Any]]:
    frames = _frames()
    prior = SOURCE_G3_ACTION_ID
    actions: list[dict[str, Any]] = []
    for index, (role, driver_role, branch, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, BRANCHES, GLOBAL_HEADERS, frames, strict=True)
    ):
        target = _dtm_identity(TARGET_DTMS[index])
        combined = _dtm_identity(COMBINED_DTMS[index])
        action: dict[str, Any] = {
            "ordinal": index + 1,
            "role": role,
            "driver_role": driver_role,
            "branch": branch,
            "global_header": header,
            "profile_id": clean.PROFILES[header]["id"],
            "frame": _frame_identity(frame),
            "transport": {
                "kind": "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP",
                "prestage_dtm": _dtm_identity(PRELOAD_DTM),
                "target_dtm": target,
                "ptlw_payload_hex": PTLW_PAYLOADS[index].hex(),
                "ptlw_writes_per_controller": 1,
                "cs1_dtm": deepcopy(combined),
                "cs2_dtm": deepcopy(combined),
            },
            "source_g3_external": index == 0,
            "prior_action_id": prior,
            "visible_refresh_requests": 1,
            "retry": False,
            "fallback": False,
            "recovery": False,
            "autochain": False,
        }
        descriptor_id = _descriptor(deepcopy(action))
        action["descriptor_id"] = descriptor_id
        action_id = _action_id(index + 1, descriptor_id)
        action["action_id"] = action_id
        prior = action_id
        actions.append(action)
    return actions


def _assert_geometry() -> None:
    if (
        GRID_X0,
        GRID_Y0,
        GRID_X1_EXCLUSIVE,
        GRID_Y1_EXCLUSIVE,
        CELL_WIDTH,
        CELL_HEIGHT,
    ) != (68, 64, 444, 536, 40, 52):
        raise PositionBalancedGrayHoldPackError("source G3 grid geometry drifted")
    for window in HOLD_WINDOWS:
        if (
            window.x % 2
            or window.width % 2
            or window.x < 0
            or window.y < 0
            or window.x + window.width > 400
            or window.y + window.height > HEIGHT
        ):
            raise PositionBalancedGrayHoldPackError("HOLD white-band geometry differs")
    overlap = not (
        H1_WINDOW.x + H1_WINDOW.width <= H2_WINDOW.x
        or H2_WINDOW.x + H2_WINDOW.width <= H1_WINDOW.x
        or H1_WINDOW.y + H1_WINDOW.height <= H2_WINDOW.y
        or H2_WINDOW.y + H2_WINDOW.height <= H1_WINDOW.y
    )
    if overlap:
        raise PositionBalancedGrayHoldPackError("H1/H2 windows overlap")
    for window in HOLD_WINDOWS:
        overlaps_grid = not (
            window.x + window.width <= GRID_X0
            or GRID_X1_EXCLUSIVE <= window.x
            or window.y + window.height <= GRID_Y0
            or GRID_Y1_EXCLUSIVE <= window.y
        )
        if overlaps_grid:
            raise PositionBalancedGrayHoldPackError("HOLD probe overlaps G3 candidates")
    if PRELOAD_DTM_SHA256 != clean.PRELOAD_DTM_SHA256:
        raise PositionBalancedGrayHoldPackError("clean code7 preload drifted")


def source_authority_surface() -> dict[str, Any]:
    return {
        "kind": "EXACT_V3_G3_COMPLETE_AND_G4_ABSENT",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_contract_id": SOURCE_CONTRACT_ID,
        "required_source_ordinal": 3,
        "required_source_descriptor_id": SOURCE_G3_DESCRIPTOR_ID,
        "required_source_action_id": SOURCE_G3_ACTION_ID,
        "required_source_path": SOURCE_G3_PATH.relative_to(REPO_ROOT).as_posix(),
        "forbidden_g4_descriptor_id": SOURCE_G4_DESCRIPTOR_ID,
        "forbidden_g4_action_id": SOURCE_G4_ACTION_ID,
        "forbidden_g4_path": SOURCE_G4_PATH.relative_to(REPO_ROOT).as_posix(),
        "g4_presence_is_hard_failure": True,
        "deep_terminal_validation_required_before_any_device_request": True,
        "source_optical_state_preserved_by_j2_off_app_only_flash": True,
        "source_live_evidence_present": SOURCE_G3_PATH.is_file(),
        "forbidden_g4_present": SOURCE_G4_PATH.exists(),
        "camera_relative_only": True,
        "absolute_white_point_proven": False,
        "qualified_gray_levels_before_hold": 0,
    }


def validate_source_authority(*, require_live: bool) -> dict[str, Any]:
    package = source_pack.dry_validate(verify_artifacts=True)
    report = source_pack.build_report()
    if (
        package.get("result") != "PASS"
        or report.get("contract_id") != SOURCE_CONTRACT_ID
        or report["actions"][2]["descriptor_id"] != SOURCE_G3_DESCRIPTOR_ID
        or report["actions"][2]["action_id"] != SOURCE_G3_ACTION_ID
        or report["actions"][3]["descriptor_id"] != SOURCE_G4_DESCRIPTOR_ID
        or report["actions"][3]["action_id"] != SOURCE_G4_ACTION_ID
    ):
        raise PositionBalancedGrayHoldPackError("source V3 package identity differs")
    if SOURCE_G4_PATH.exists():
        raise PositionBalancedGrayHoldPackError(
            "forbidden G4 result exists; H1/H2 successor requires exact G3 optical state"
        )
    if not SOURCE_G3_PATH.is_file():
        if require_live:
            raise PositionBalancedGrayHoldPackError(
                "exact G3 COMPLETE evidence is not present"
            )
        return {
            **source_authority_surface(),
            "state": "PENDING_EXACT_G3_COMPLETE",
            "live_gate_passed": False,
            "network_accessed": False,
            "hardware_accessed": False,
        }
    if SOURCE_G3_PATH.is_symlink():
        raise PositionBalancedGrayHoldPackError("G3 source path must not be a symlink")
    from tools import (  # noqa: PLC0415
        mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_once as source_once,
    )

    try:
        terminal = source_once.validate_terminal_evidence(SOURCE_G3_PATH)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
        raise PositionBalancedGrayHoldPackError(
            "G3 terminal deep validation failed"
        ) from error
    if (
        terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("campaign_id") != SOURCE_CAMPAIGN_ID
        or terminal.get("contract_id") != SOURCE_CONTRACT_ID
        or terminal.get("ordinal") != 3
        or terminal.get("descriptor_id") != SOURCE_G3_DESCRIPTOR_ID
        or terminal.get("action_id") != SOURCE_G3_ACTION_ID
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("visible_refreshes") != 1
    ):
        raise PositionBalancedGrayHoldPackError("G3 terminal lineage differs")
    return {
        **source_authority_surface(),
        "state": "DEEPLY_VALIDATED_G3_COMPLETE_WITH_G4_ABSENT",
        "live_gate_passed": True,
        "selected_terminal": terminal,
        "source_file_sha256": sha256_bytes(SOURCE_G3_PATH.read_bytes()),
        "network_accessed": False,
        "hardware_accessed": False,
    }


def build_report() -> dict[str, Any]:
    _assert_geometry()
    actions = _build_actions()
    contract = {
        "schema": "mf1750-position-balanced-gray-hold-successor-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "action_order": list(ROLES),
        "source_authority": source_authority_surface(),
        "source_action_replayed": False,
        "g1_g2_g3_embedded_or_replayed": False,
        "accepted_source_ordinals": [3],
        "g4_accepted": False,
        "g4_presence_is_hard_failure": True,
        "j2_off_app_only_flash_required": True,
        "boot_auto_action": False,
        "startup_refresh": False,
        "hold_windows": [asdict(item) for item in HOLD_WINDOWS],
        "windows_outside_candidate_grid": True,
        "windows_nonoverlapping": True,
        "g3_candidate_cells_retained": 128,
        "all_g3_candidate_replicas_intended_to_be_retained": True,
        "clean_ptlw_transport": {
            "mechanical_source_contract_id": clean.CONTRACT_ID,
            "full_code7_prestage_bytes_per_controller": CONTROLLER_DTM_BYTES,
            "full_code7_prestage_sha256": PRELOAD_DTM_SHA256,
            "one_inclusive_ptlw_per_controller": True,
            "ptlw_command": 0x83,
            "ptlw_mode": 1,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_payloads_hex": [item.hex() for item in PTLW_PAYLOADS],
            "cropped_dtm_bytes_per_controller": list(CROPPED_DTM_BYTES),
            "target_codes": list(HOLD_CODES),
            "target_dtm_sha256": list(TARGET_DTM_SHA256),
            "combined_dtm_sha256": list(COMBINED_DTM_SHA256),
            "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
            "post_pon_ptlw": False,
            "post_pon_cdi": False,
            "post_pon_btst2": False,
            "command_0x86": False,
        },
        "factory_otp_white_successor_embedded": False,
        "independent_factory_otp_white_successor_required": True,
        "spatial_dither": False,
        "qualified_hold_colours": 0,
        "qualified_gray_levels": 0,
        "controller_color_equivalence_claimed": False,
        "autochain": False,
        "retry": False,
        "fallback": False,
        "automatic_recovery": False,
    }
    contract_id = sha256_bytes(canonical_json(contract))
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-hold-successor-v1-offline-identities",
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


def compiled_identity_marker(report: Mapping[str, Any] | None = None) -> str:
    selected = build_report() if report is None else report
    return (
        "MF1750_EC5_PBGHS1_COMPILED_IDENTITY_V1|"
        f"CONTRACT={selected['contract_id']}|"
        + "|".join(
            f"H{item['ordinal']}={item['action_id']}" for item in selected["actions"]
        )
    )


def identity_path() -> Path:
    return REPO_ROOT / "src/ec5_position_balanced_gray_hold_successor_v1_identity.inc"


def main_config_path() -> Path:
    return (
        REPO_ROOT / "src/ec5_position_balanced_gray_hold_successor_v1_main_config.inc"
    )


def driver_path() -> Path:
    return REPO_ROOT / "src/ec5_position_balanced_gray_hold_successor_v1_driver.inc"


def artifact_dir() -> Path:
    return REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT


def artifacts_are_sealed() -> bool:
    return (
        isinstance(ARTIFACTS["bin_bytes"], int)
        and ARTIFACTS["bin_bytes"] > 0
        and isinstance(ARTIFACTS["elf_bytes"], int)
        and ARTIFACTS["elf_bytes"] > 0
        and all(
            isinstance(ARTIFACTS[key], str)
            and len(ARTIFACTS[key]) == 64
            and set(ARTIFACTS[key]) <= set("0123456789abcdef")
            and ARTIFACTS[key] != "0" * 64
            for key in ("bin_sha256", "elf_sha256")
        )
    )


def validate_artifacts() -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise PositionBalancedGrayHoldPackError("firmware artifacts are unsealed")
    checked: dict[str, Any] = {}
    for stem in ("bin", "elf"):
        path = artifact_dir() / f"firmware.{stem}"
        payload = path.read_bytes()
        if (
            len(payload) != ARTIFACTS[f"{stem}_bytes"]
            or sha256_bytes(payload) != ARTIFACTS[f"{stem}_sha256"]
        ):
            raise PositionBalancedGrayHoldPackError(f"firmware.{stem} differs")
        checked[stem] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
    return checked


def validate_compiled_identity_binary() -> dict[str, Any]:
    payload = (artifact_dir() / "firmware.bin").read_bytes()
    marker = compiled_identity_marker().encode("ascii")
    if payload.count(marker) != 1:
        raise PositionBalancedGrayHoldPackError(
            "compiled identity marker missing or duplicated"
        )
    return {"verified": True, "marker": marker.decode("ascii"), "count": 1}


def dry_validate(
    *, require_live_source: bool = False, verify_artifacts: bool = False
) -> dict[str, Any]:
    report = build_report()
    source = validate_source_authority(require_live=require_live_source)
    actions = report["actions"]
    if (
        [item["ordinal"] for item in actions] != [1, 2]
        or [item["driver_role"] for item in actions]
        != ["ReverseSource", "ReverseTarget"]
        or actions[0]["prior_action_id"] != SOURCE_G3_ACTION_ID
        or actions[1]["prior_action_id"] != actions[0]["action_id"]
    ):
        raise PositionBalancedGrayHoldPackError("two-action lineage differs")
    artifacts = validate_artifacts() if verify_artifacts else None
    compiled_identity = (
        validate_compiled_identity_binary() if verify_artifacts else None
    )
    return {
        "kind": "mf1750-position-balanced-gray-hold-successor-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "network_accessed": False,
        "source_authority": source,
        "contract_id": report["contract_id"],
        "descriptor_ids": [item["descriptor_id"] for item in actions],
        "action_ids": [item["action_id"] for item in actions],
        "artifacts_verified": verify_artifacts,
        "artifacts": artifacts,
        "compiled_identity_binary": compiled_identity,
    }


_REPORT = build_report()
CONTRACT_ID = _REPORT["contract_id"]
DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in _REPORT["actions"])
ACTION_IDS = tuple(item["action_id"] for item in _REPORT["actions"])


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
