#!/usr/bin/env python3
"""Fresh offline identities for the position-balanced LUMA/GRAY mechanism V3.

This successor is deliberately narrow.  It starts from the completed stable-
code0 LUMA LATIN V3 factory-OTP-white successor, its permanent claim, exact
relay-OFF receipt, locked 48MP capture/JPEG, and camera-visible clean-white
review.  It evaluates sixteen *history recipes* only:

    active C7 source -> commented C0..C7 middle -> active C3/C7 target

Every recipe occurs four times on each controller.  CS2 uses the exact 180
degree semantic rotation of CS1.  G4 is a byte-identical repeat of G3 but is a
separate, manually selected action; nothing in this package chains it.

The terms LUMA and GRAY remain mechanism labels.  No colour, neutral-grey, or
brightness level is qualified by this offline package.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
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
    mf1750_stable_code0_luma_latin_v3_white_successor_v1_pack as source_white,
)


class LumaGrayMechanismV3PackError(RuntimeError):
    """Raised when a frozen identity, source gate, or payload differs."""


@dataclass(frozen=True)
class Config:
    stage: str = "luma-gray-mechanism-position-balanced-v3"
    variant_key: str = "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3"
    build_tag: str = "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_2026-09-01"
    test_id: str = "EC5-LUMA-GRAY-MECHANISM-POSITION-BALANCED-V3"
    campaign_id: str = "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3"
    route_slug: str = "luma-gray-mechanism-position-balanced-v3"
    environment: str = "ec5_luma_gray_mpb_v3"
    build_root: str = "b-luma-gray-mpb-v3"
    nvs_namespace: str = "lgmpb_v3"
    nvs_key: str = "cur_lgmpb3"
    nvs_boot_key: str = "boot_lgmpb3"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"


CONFIG = Config()
STAGE = CONFIG.stage
BUILD_TAG = CONFIG.build_tag
TEST_ID = CONFIG.test_id
CAMPAIGN_ID = CONFIG.campaign_id
NVS_NAMESPACE = CONFIG.nvs_namespace
NVS_KEY = CONFIG.nvs_key
NVS_BOOT_KEY = CONFIG.nvs_boot_key
VARIANT_KEY = CONFIG.variant_key
DEVICE_API_VERSION = "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_DEVICE_V3"
IDENTITY_REVISION = "luma-gray-mechanism-position-balanced-v3"
CLASSIFICATION = (
    "EXPERIMENTAL_HISTORY_MECHANISM_POSITION_BALANCED_CANDIDATES_"
    "ZERO_QUALIFIED_GRAY_OR_BRIGHTNESS_LEVELS"
)
ARM_INTENT = "ARM_ONE_FIXED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_ACTION"
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_ACTION_ONCE"
)

SOURCE_CODE = 7
MIDDLE_CODES = tuple(range(8))
TARGET_CODES = (3, 7)
BACKGROUND_CODE = 7
FACTORY_WHITE_FILL_BYTE = 0x11

GRID_ROWS = 8
GRID_COLUMNS = 8
CELL_WIDTH = 40
CELL_HEIGHT = 52
GAP_X = 8
GAP_Y = 8
GRID_X0 = (base.CONTROLLER_WIDTH - (GRID_COLUMNS * CELL_WIDTH + 7 * GAP_X)) // 2
GRID_Y0 = (base.HEIGHT - (GRID_ROWS * CELL_HEIGHT + 7 * GAP_Y)) // 2
GRID_X1_EXCLUSIVE = GRID_X0 + GRID_COLUMNS * CELL_WIDTH + 7 * GAP_X
GRID_Y1_EXCLUSIVE = GRID_Y0 + GRID_ROWS * CELL_HEIGHT + 7 * GAP_Y

# The four quadrant permutations are inherited only as placement mechanics.
# Each recipe occurs exactly once in every quadrant.
_PERMUTATIONS = (
    tuple(range(16)),
    tuple(((r * 4 + c + r) % 4) + r * 4 for r in range(4) for c in range(4)),
    tuple((((r + c) % 4) * 4 + c) for r in range(4) for c in range(4)),
    tuple((15 - (r * 4 + c)) for r in range(4) for c in range(4)),
)


def _position_balanced_map() -> tuple[int, ...]:
    cells = [0] * 64
    for quadrant, (row0, col0) in enumerate(((0, 0), (0, 4), (4, 0), (4, 4))):
        permutation = _PERMUTATIONS[quadrant]
        if sorted(permutation) != list(range(16)):
            raise LumaGrayMechanismV3PackError("quadrant map is not a permutation")
        for local, recipe in enumerate(permutation):
            row, column = divmod(local, 4)
            cells[(row0 + row) * 8 + col0 + column] = recipe
    if any(cells.count(recipe) != 4 for recipe in range(16)):
        raise LumaGrayMechanismV3PackError("recipe repeat count differs")
    return tuple(cells)


CS1_RECIPE_AT_CELL = _position_balanced_map()
CS2_RECIPE_AT_CELL = tuple(reversed(CS1_RECIPE_AT_CELL))

ROLES = (
    "G1_ACTIVE_C7_SOURCE",
    "G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
    "G3_ACTIVE_C3_C7_TARGET",
    "G4_ACTIVE_C3_C7_IDENTICAL_TARGET_REPEAT_MANUAL_ONLY",
)
DRIVER_ROLES = ("Source", "Mid", "Target", "ReverseSource")
GLOBAL_HEADERS = ("active", "commented", "active", "active")

SOURCE_ROOT = (
    ".test-output/hardware/"
    "MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_20260901_V1"
)
SOURCE_BINDINGS: dict[str, dict[str, int | str]] = {
    "completed_action": {
        "path": f"{SOURCE_ROOT}/action-01-factory-otp-white.json",
        "bytes": 36_987,
        "file_sha256": "9ebc3ca4f32ceba8cbb356aece938d28e922e016f875ab10aa082338993b509b",
        "canonical_integrity_sha256": "555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b",
    },
    "permanent_claim": {
        "path": (
            ".test-output/hardware/.mf1750_stable_code0_luma_latin_v3_"
            "white_successor_v1_claims/"
            "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f.json"
        ),
        "bytes": 3_541,
        "file_sha256": "0b02c61aad1793fedb40817464dc98aec72efb71e1370a140ed33256dd48d5eb",
        "canonical_integrity_sha256": "79ece6bd3defb0969554b2cf2c80f2e29bb4d28a6c28a22eda94431a75087834",
    },
    "relay_protective_off": {
        "path": f"{SOURCE_ROOT}/relay-post-white-off.json",
        "bytes": 1_803,
        "file_sha256": "1fa84d45b7374fce680bdadcde0edb2142adfa408b5511edfa75dd20f0b09626",
        "canonical_integrity_sha256": "5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400",
    },
    "capture_sidecar": {
        "path": f"{SOURCE_ROOT}/post-white-retained-camera-attempt-01-exposure-m4.capture.json",
        "bytes": 5_321,
        "file_sha256": "479c7451ca87c60cbef614895e3a3866a8415d0f3ccf3ad82668ae321bb459ae",
        "canonical_integrity_sha256": "7e9f7b6b9edb1e246da06316153e24e846761bc1c02fdf3a02fa5d1384ac7362",
    },
    "capture_jpeg": {
        "path": f"{SOURCE_ROOT}/post-white-retained-camera-attempt-01-exposure-m4.jpg",
        "bytes": 1_014_449,
        "file_sha256": "f04bc44ad4e92007f7ffd2a730a28fe602acf18d34b98d2540c5959c7a46d92a",
    },
    "camera_white_review": {
        "path": f"{SOURCE_ROOT}/post-white-retained-camera-attempt-01-exposure-m4.clean-white-review.json",
        "bytes": 4_367,
        "file_sha256": "50ce755e3ed04790819c326bbbb1e6a2fdc3c6b587899f02b00da588d5e2d625",
        "canonical_integrity_sha256": "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40",
    },
}

ZERO_SHA256 = "0" * 64
ARTIFACTS: dict[str, int | str] = {
    "bin_bytes": 801_168,
    "bin_sha256": "f19eca9e771dedb1c62c25ae017e602bf25ef31f0086aeb26f65bd4575353b22",
    "elf_bytes": 13_297_804,
    "elf_sha256": "6304c0fc2c08ed075bc3919a38a6c2bbedfd58961a1360ecee546b37321c230c",
}


def compiled_identity_marker(report: Mapping[str, Any] | None = None) -> str:
    """Return the one immutable marker required in the linked firmware."""

    selected = build_report() if report is None else report
    actions = selected["actions"]
    return (
        "MF1750_EC5_LGMPB3_COMPILED_IDENTITY_V1|"
        f"CONTRACT={selected['contract_id']}|"
        + "|".join(f"G{item['ordinal']}={item['action_id']}" for item in actions)
    )


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


def _read_bound_json(binding: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or path.is_symlink():
        raise LumaGrayMechanismV3PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if (
        len(payload) != binding["bytes"]
        or sha256_bytes(payload) != binding["file_sha256"]
    ):
        raise LumaGrayMechanismV3PackError(f"{label} file binding differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LumaGrayMechanismV3PackError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise LumaGrayMechanismV3PackError(f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = None
    if isinstance(integrity, Mapping):
        recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if (
        recorded != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != recorded
    ):
        raise LumaGrayMechanismV3PackError(f"{label} canonical binding differs")
    return value


def _read_bound_bytes(binding: Mapping[str, Any], label: str) -> bytes:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or path.is_symlink():
        raise LumaGrayMechanismV3PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if (
        len(payload) != binding["bytes"]
        or sha256_bytes(payload) != binding["file_sha256"]
    ):
        raise LumaGrayMechanismV3PackError(f"{label} file binding differs")
    return payload


@lru_cache(maxsize=1)
def validate_source_gate() -> dict[str, Any]:
    """Validate the exact current V3 white successor and retained review chain."""

    source_validation = source_white.dry_validate(verify_artifacts=True)
    source_report = source_white.build_report(verify_artifacts=True)
    source_action = source_report["action"]
    if (
        source_validation.get("result") != "PASS"
        or source_validation.get("artifacts_sealed") is not True
        or source_validation.get("compiled_identity_binary", {}).get("verified")
        is not True
    ):
        raise LumaGrayMechanismV3PackError("source white package validation differs")
    action = _read_bound_json(SOURCE_BINDINGS["completed_action"], "source action")
    claim = _read_bound_json(SOURCE_BINDINGS["permanent_claim"], "source claim")
    relay = _read_bound_json(
        SOURCE_BINDINGS["relay_protective_off"], "source relay OFF"
    )
    capture = _read_bound_json(
        SOURCE_BINDINGS["capture_sidecar"], "48MP capture sidecar"
    )
    jpeg = _read_bound_bytes(SOURCE_BINDINGS["capture_jpeg"], "48MP capture JPEG")
    review = _read_bound_json(
        SOURCE_BINDINGS["camera_white_review"], "clean-white review"
    )
    terminal = action.get("terminal_report")
    driver = terminal.get("driver") if isinstance(terminal, Mapping) else None
    expected_tuple = (
        source_white.CAMPAIGN_ID,
        source_report["contract_id"],
        source_report["descriptor_id"],
        source_report["action_id"],
    )
    observed_tuple = (
        terminal.get("campaign_id") if isinstance(terminal, Mapping) else None,
        terminal.get("contract_id") if isinstance(terminal, Mapping) else None,
        terminal.get("transaction_descriptor_sha256")
        if isinstance(terminal, Mapping)
        else None,
        terminal.get("action_id") if isinstance(terminal, Mapping) else None,
    )
    if (
        observed_tuple != expected_tuple
        or action.get("outcome") != "complete_pass"
        or action.get("claim_state") != "permanently_consumed_by_this_invocation"
        or action.get("visible_refreshes") != 1
        or action.get("no_retry") is not True
        or action.get("no_recovery") is not True
        or action.get("no_autochain") is not True
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("campaign_complete") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or not isinstance(driver, Mapping)
        or driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("timeout_stage") != "none"
    ):
        raise LumaGrayMechanismV3PackError("source COMPLETE terminal semantics differ")
    if (
        claim.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or claim.get("action") != source_action
        or claim.get("firmware_sha256") != source_white.FIRMWARE_BIN_SHA256
        or claim.get("boot_nonce") != action.get("boot_nonce")
        or claim.get("no_retry") is not True
        or claim.get("no_recovery") is not True
        or claim.get("no_autochain") is not True
    ):
        raise LumaGrayMechanismV3PackError("source permanent claim semantics differ")
    capture_photo = capture.get("photo")
    capture_coverage = capture.get("coverage")
    capture_camera = capture.get("camera")
    capture_action = capture.get("action_result")
    if (
        capture.get("kind") != "mf1750-camera-capture-evidence"
        or capture.get("campaign_id") != expected_tuple[0]
        or capture.get("contract_id") != expected_tuple[1]
        or capture.get("descriptor_id") != expected_tuple[2]
        or capture.get("action_id") != expected_tuple[3]
        or capture.get("ordinal") != 1
        or capture.get("role") != "FACTORY_OTP_WHITE_RECOVERY"
        or capture.get("firmware_sha256") != source_white.FIRMWARE_BIN_SHA256
        or capture.get("capture_binding") != "locked_retained_retrospective"
        or capture.get("capture_id")
        != "85d78b0fbcf78162e5c9a6a0c618e2ae8f9f815ade2e61d4ff481b80cef80e34"
        or not isinstance(capture_action, Mapping)
        or capture_action.get("file_sha256")
        != SOURCE_BINDINGS["completed_action"]["file_sha256"]
        or not isinstance(capture_camera, Mapping)
        or capture_camera.get("camera_id") != "48MP USB Camera"
        or "vid_32e4&pid_4801" not in str(capture_camera.get("instance_id", "")).lower()
        or not isinstance(capture_coverage, Mapping)
        or capture_coverage.get("scope") != "full_panel"
        or capture_coverage.get("full_panel_visible") is not True
        or capture_coverage.get("full_panel_uncropped") is not True
        or not isinstance(capture_photo, Mapping)
        or capture_photo.get("sha256") != sha256_bytes(jpeg)
        or capture_photo.get("bytes") != len(jpeg)
        or capture_photo.get("width") != 4000
        or capture_photo.get("height") != 3000
        or capture_photo.get("quality_metrics", {}).get("camera_relative_only")
        is not True
        or capture_photo.get("quality_metrics", {}).get("absolute_colour_qualification")
        is not False
    ):
        raise LumaGrayMechanismV3PackError("48MP capture/JPEG semantics differ")
    classification = review.get("classification")
    evidence = review.get("source_evidence")
    capture_binding = review.get("capture_binding")
    if (
        review.get("kind") != "mf1750-camera-visible-clean-white-review"
        or review.get("campaign_id") != expected_tuple[0]
        or review.get("contract_id") != expected_tuple[1]
        or review.get("descriptor_id") != expected_tuple[2]
        or review.get("action_id") != expected_tuple[3]
        or review.get("review_id")
        != "b0a62b0c7dbf178fa6a2763d0bebf417b61dda6bd86bab701c84f658ae2ba96f"
        or not isinstance(classification, Mapping)
        or classification.get("state") != "CAMERA_VISIBLE_CLEAN_WHITE_REVIEW"
        or classification.get("camera_visible_clean_white_review_passed") is not True
        or classification.get("camera_relative_only") is not True
        or classification.get("absolute_white_point_proven") is not False
        or classification.get("spatial_uniformity_proven") is not False
        or classification.get("retained_action_to_capture_continuity_proven")
        is not False
        or classification.get("qualified_white_or_gray_level") is not False
        or classification.get("qualified_level_count") != 0
        or not isinstance(capture_binding, Mapping)
        or capture_binding.get("camera_id") != "48MP USB Camera"
        or capture_binding.get("camera_relative_only") is not True
        or capture_binding.get("retained_action_to_capture_continuity_proven")
        is not False
        or not isinstance(evidence, Mapping)
        or evidence.get("action_result", {}).get("file_sha256")
        != SOURCE_BINDINGS["completed_action"]["file_sha256"]
        or evidence.get("relay_off_receipt", {}).get("file_sha256")
        != SOURCE_BINDINGS["relay_protective_off"]["file_sha256"]
        or evidence.get("capture_sidecar", {}).get("file_sha256")
        != SOURCE_BINDINGS["capture_sidecar"]["file_sha256"]
        or evidence.get("photo", {}).get("file_sha256")
        != SOURCE_BINDINGS["capture_jpeg"]["file_sha256"]
    ):
        raise LumaGrayMechanismV3PackError("clean-white review semantics differ")
    if (
        relay.get("commanded_state") != "OFF"
        or relay.get("target_state") != "OFF"
        or relay.get("off_gate_passed") is not True
        or relay.get("contact_path") != "COM1-NO1"
        or relay.get("electrical_state_proven") is not False
        or relay.get("automatic_retry_performed") is not False
        or relay.get("automatic_recovery_performed") is not False
    ):
        raise LumaGrayMechanismV3PackError("source relay-OFF semantics differ")
    return {
        "source_tuple": {
            "campaign_id": expected_tuple[0],
            "contract_id": expected_tuple[1],
            "descriptor_id": expected_tuple[2],
            "action_id": expected_tuple[3],
        },
        "terminal_state": "COMPLETE",
        "visible_refreshes": 1,
        "camera_visible_clean_white_containment_review": True,
        "camera_relative_only": True,
        "absolute_white_or_uniformity_qualified": False,
        "qualified_level_count": 0,
        "retained_action_to_capture_continuity_proven": False,
        "review_id": review["review_id"],
        "relay_commanded_off": True,
        "electrical_state_proven": False,
        "bindings": deepcopy(SOURCE_BINDINGS),
    }


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    return (
        GRID_X0 + column * (CELL_WIDTH + GAP_X),
        GRID_Y0 + row * (CELL_HEIGHT + GAP_Y),
        CELL_WIDTH,
        CELL_HEIGHT,
    )


def _set_cell(
    frame: bytearray, controller: int, row: int, column: int, code: int
) -> None:
    x, y, width, height = _cell_bounds(row, column)
    x += controller * base.CONTROLLER_WIDTH
    pair = (code << 4) | code
    row_bytes = base.WIDTH // 2
    for py in range(y, y + height):
        start = py * row_bytes + x // 2
        frame[start : start + width // 2] = bytes([pair]) * (width // 2)


@lru_cache(maxsize=4)
def _grid_frame(stage: str) -> bytes:
    frame = bytearray([(BACKGROUND_CODE << 4) | BACKGROUND_CODE]) * (
        base.WIDTH * base.HEIGHT // 2
    )
    for controller, mapping in enumerate((CS1_RECIPE_AT_CELL, CS2_RECIPE_AT_CELL)):
        for cell, recipe in enumerate(mapping):
            row, column = divmod(cell, GRID_COLUMNS)
            if stage == "source":
                code = SOURCE_CODE
            elif stage == "middle":
                code = MIDDLE_CODES[recipe % 8]
            elif stage in {"target", "repeat"}:
                code = TARGET_CODES[recipe // 8]
            else:
                raise LumaGrayMechanismV3PackError(f"unknown frame stage {stage}")
            _set_cell(frame, controller, row, column, code)
    return bytes(frame)


@lru_cache(maxsize=8)
def _payload_identity_cached(frame: bytes, controller: int) -> tuple[int, int, str]:
    value = cross.payload_identity(cross.controller_stream(frame, controller))
    return int(value["bytes"]), int(value["fnv1a"]), str(value["sha256"])


def _payload(frame: bytes, controller: int) -> dict[str, Any]:
    size, fnv1a, digest = _payload_identity_cached(frame, controller)
    return {"bytes": size, "fnv1a": fnv1a, "sha256": digest}


@lru_cache(maxsize=4)
def _frame_identity_cached(frame: bytes) -> tuple[int, int, str, tuple[int, ...]]:
    value = base.frame_identity(frame)
    return (
        int(value["bytes"]),
        int(value["fnv1a"]),
        str(value["sha256"]),
        tuple(int(item) for item in value["histogram"]),
    )


def _frame_identity(frame: bytes) -> dict[str, Any]:
    size, fnv1a, digest, histogram = _frame_identity_cached(frame)
    return {
        "bytes": size,
        "fnv1a": fnv1a,
        "sha256": digest,
        "histogram": list(histogram),
    }


def recipe_map() -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for recipe in range(16):
        positions: dict[str, list[dict[str, Any]]] = {"cs1": [], "cs2": []}
        for controller_name, mapping in (
            ("cs1", CS1_RECIPE_AT_CELL),
            ("cs2", CS2_RECIPE_AT_CELL),
        ):
            for cell, value in enumerate(mapping):
                if value != recipe:
                    continue
                row, column = divmod(cell, GRID_COLUMNS)
                positions[controller_name].append(
                    {
                        "row": row,
                        "column": column,
                        "local_roi": dict(
                            zip(
                                ("x", "y", "width", "height"),
                                _cell_bounds(row, column),
                                strict=True,
                            )
                        ),
                    }
                )
        recipes.append(
            {
                "recipe_id": (
                    f"LGMPB3-S{SOURCE_CODE}-M{recipe % 8}-T{TARGET_CODES[recipe // 8]}"
                ),
                "source": {"global_header": "active", "code": SOURCE_CODE},
                "middle": {"global_header": "commented", "code": recipe % 8},
                "target": {
                    "global_header": "active",
                    "code": TARGET_CODES[recipe // 8],
                },
                "positions": positions,
                "repeats_per_controller": 4,
                "spatial_dither": False,
            }
        )
    return recipes


def artifact_paths() -> tuple[Path, Path]:
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    return (
        int(ARTIFACTS["bin_bytes"]) > 0
        and int(ARTIFACTS["elf_bytes"]) > 0
        and ARTIFACTS["bin_sha256"] != ZERO_SHA256
        and ARTIFACTS["elf_sha256"] != ZERO_SHA256
    )


def _quoted_literals(source: str, name: str) -> list[str]:
    pattern = re.compile(
        rf"(?:static\s+constexpr\s+(?:const\s+)?char\s*\*?\s*{re.escape(name)}(?:\[\])?\s*=)"
        r"(?P<body>.*?);",
        re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        raise LumaGrayMechanismV3PackError(f"compiled identity {name} missing")
    values = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', match.group("body"))
    if not values:
        raise LumaGrayMechanismV3PackError(f"compiled identity {name} empty")
    return values


def _compiled_string(source: str, name: str) -> str:
    return "".join(
        bytes(value, "utf-8").decode("unicode_escape")
        for value in _quoted_literals(source, name)
    )


def validate_compiled_identity_source() -> dict[str, Any]:
    """Deeply bind Python identities to the exact compiled C++ action table."""

    report = build_report()
    actions = report["actions"]
    identity_path = (
        REPO_ROOT
        / "src/ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_identity.inc"
    )
    config_path = (
        REPO_ROOT
        / "src/ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_main_config.inc"
    )
    if any(
        not path.is_file() or path.is_symlink() for path in (identity_path, config_path)
    ):
        raise LumaGrayMechanismV3PackError("compiled identity source missing or unsafe")
    identity = identity_path.read_text(encoding="utf-8")
    config = config_path.read_text(encoding="utf-8")
    if (
        _compiled_string(identity, "kContractId") != report["contract_id"]
        or _compiled_string(identity, "kCampaignId") != CAMPAIGN_ID
        or _compiled_string(identity, "kVariantKey") != VARIANT_KEY
        or _compiled_string(identity, "kBuildTag") != BUILD_TAG
        or _compiled_string(identity, "kNvsNamespace") != NVS_NAMESPACE
        or _compiled_string(identity, "kNvsBootKey") != NVS_BOOT_KEY
        or _compiled_string(config, "kNvsKey") != NVS_KEY
        or _compiled_string(config, "kArmIntent") != ARM_INTENT
        or _compiled_string(config, "kExecuteIntent") != EXECUTE_INTENT
        or _compiled_string(config, "kCompiledIdentityMarker")
        != compiled_identity_marker(report)
    ):
        raise LumaGrayMechanismV3PackError("compiled campaign identity differs")

    macro_pattern = re.compile(
        r"LGMPB3_ACTION\(\s*(?P<ordinal>[1-4])\s*,.*?\n"
        r"\s*\"(?P<role>[^\"]+)\",\s*\n"
        r"\s*\"(?P<branch>[^\"]+)\",\s*\n"
        r"\s*\"(?P<descriptor>[0-9a-f]{64})\",\s*\n"
        r"\s*\"(?P<action>[0-9a-f]{64})\",\s*\n"
        r"\s*(?:nullptr|\"[0-9a-f]{64}\"),\s*\n"
        r"\s*\"(?P<frame>[0-9a-f]{64})\",\s*\n"
        r"\s*\"(?P<cs1>[0-9a-f]{64})\",\s*\n"
        r"\s*\"(?P<cs2>[0-9a-f]{64})\",\s*\n"
        r"\s*0x(?P<frame_fnv>[0-9A-Fa-f]{8})UL,\s*0x(?P<cs1_fnv>[0-9A-Fa-f]{8})UL,\s*0x(?P<cs2_fnv>[0-9A-Fa-f]{8})UL,",
        re.DOTALL,
    )
    observed = {
        int(match.group("ordinal")): match.groupdict()
        for match in macro_pattern.finditer(config)
    }
    if set(observed) != {1, 2, 3, 4}:
        raise LumaGrayMechanismV3PackError("compiled action table cardinality differs")
    for expected in actions:
        item = observed[expected["ordinal"]]
        wanted = {
            "role": expected["role"],
            "branch": expected["branch"],
            "descriptor": expected["descriptor_id"],
            "action": expected["action_id"],
            "frame": expected["frame"]["sha256"],
            "cs1": expected["cs1_dtm"]["sha256"],
            "cs2": expected["cs2_dtm"]["sha256"],
            "frame_fnv": f"{expected['frame']['fnv1a']:08X}",
            "cs1_fnv": f"{expected['cs1_dtm']['fnv1a']:08X}",
            "cs2_fnv": f"{expected['cs2_dtm']['fnv1a']:08X}",
        }
        if any(item[key].upper() != value.upper() for key, value in wanted.items()):
            raise LumaGrayMechanismV3PackError(
                f"compiled action identity differs at ordinal {expected['ordinal']}"
            )
    marker = compiled_identity_marker(report)
    if config.count(marker) != 1:
        raise LumaGrayMechanismV3PackError("compiled identity marker source differs")
    return {
        "verified": True,
        "identity_source": identity_path.relative_to(REPO_ROOT).as_posix(),
        "main_config_source": config_path.relative_to(REPO_ROOT).as_posix(),
        "contract_id": report["contract_id"],
        "action_ids": [item["action_id"] for item in actions],
        "marker": marker,
    }


def validate_compiled_identity_binary() -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise LumaGrayMechanismV3PackError("V3 artifacts are not sealed")
    marker = compiled_identity_marker().encode("ascii")
    firmware_bin, firmware_elf = artifact_paths()
    counts = {
        "bin": firmware_bin.read_bytes().count(marker),
        "elf": firmware_elf.read_bytes().count(marker),
    }
    if counts != {"bin": 1, "elf": 1}:
        raise LumaGrayMechanismV3PackError(
            f"compiled identity marker count differs: {counts}"
        )
    return {
        "verified": True,
        "marker_sha256": sha256_bytes(marker),
        "counts": counts,
    }


def build_report() -> dict[str, Any]:
    frames = (
        _grid_frame("source"),
        _grid_frame("middle"),
        _grid_frame("target"),
        _grid_frame("repeat"),
    )
    actions: list[dict[str, Any]] = []
    prior: str | None = None
    for ordinal, (role, driver_role, header, frame) in enumerate(
        zip(ROLES, DRIVER_ROLES, GLOBAL_HEADERS, frames, strict=True), 1
    ):
        item: dict[str, Any] = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "round": 1,
            "branch": f"{CONFIG.variant_key}_{role}",
            "palette_source": "L535_RUNTIME",
            "global_header": header,
            "effective_driver_profile": cross.profile(header),
            "frame": _frame_identity(frame),
            "cs1_dtm": _payload(frame, 0),
            "cs2_dtm": _payload(frame, 1),
            "prior_static_action_id": prior,
            "manual_or_host_selection_required": True,
            "automatic_chain_from_prior": False,
            "boot_admission": {
                "campaign_boot_binding_key": CONFIG.nvs_boot_key,
                "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                if ordinal == 1
                else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY",
                "required_prior_terminal_state": None if ordinal == 1 else "COMPLETE",
                "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
                "reboot_resume_allowed": False,
            },
        }
        if ordinal == 1:
            item["source_gate"] = validate_source_gate()
        if ordinal == 4:
            item["identical_target_repeat_of_ordinal"] = 3
            item["identical_target_repeat_of_action_id"] = actions[2]["action_id"]
            item["optional_terminal_branch"] = True
        descriptor = {
            "schema": "mf1750-luma-gray-mechanism-position-balanced-v3-action",
            "variant": CONFIG.variant_key,
            "build_tag": CONFIG.build_tag,
            **item,
        }
        item["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
        item["action_id"] = sha256_bytes(
            (
                "MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3|"
                f"{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior = item["action_id"]
        actions.append(item)

    source_gate = validate_source_gate()
    contract = {
        "schema": "mf1750-luma-gray-mechanism-position-balanced-contract-v3",
        "stage": STAGE,
        "variant_key": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        "test_id": CONFIG.test_id,
        "campaign_id": CONFIG.campaign_id,
        "base_route": CONFIG.base_route,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "classification": CLASSIFICATION,
        "nvs_namespace": CONFIG.nvs_namespace,
        "nvs_key": CONFIG.nvs_key,
        "nvs_boot_key": CONFIG.nvs_boot_key,
        "source_gate": source_gate,
        "geometry": {
            "controller_count": 2,
            "grid_rows_per_controller": GRID_ROWS,
            "grid_columns_per_controller": GRID_COLUMNS,
            "candidate_cells_per_controller": 64,
            "recipes": 16,
            "repeats_per_recipe_per_controller": 4,
            "required_valid_repeats": "4_of_4",
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "grid_x1_local_exclusive": GRID_X1_EXCLUSIVE,
            "grid_y1_exclusive": GRID_Y1_EXCLUSIVE,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "border_pixels": 0,
            "central_roi": True,
            "cs1_recipe_at_cell": list(CS1_RECIPE_AT_CELL),
            "cs2_recipe_at_cell": list(CS2_RECIPE_AT_CELL),
            "cs2_semantic_rotation_degrees": 180,
        },
        "mechanism": {
            "g1": {"global_header": "active", "source_code": SOURCE_CODE},
            "g2": {"global_header": "commented", "middle_codes": list(MIDDLE_CODES)},
            "g3": {"global_header": "active", "target_codes": list(TARGET_CODES)},
            "g4": {
                "global_header": "active",
                "target_codes": list(TARGET_CODES),
                "payload_byte_identical_to_g3": True,
                "independent_explicit_action": True,
                "optional": True,
                "automatic_chain": False,
                "effective_driver_profile_identical_to_g3": True,
            },
        },
        "profiles": {
            "active": cross.profile("active"),
            "commented": cross.profile("commented"),
        },
        "recipes": recipe_map(),
        "actions": actions,
        "action_count": 4,
        "required_core_action_ordinals": [1, 2, 3],
        "optional_repeat_action_ordinal": 4,
        "acceptable_terminal_for_white_successor_after_ordinal": [3, 4],
        "spatial_dither": False,
        "spatial_mixing": False,
        "cell_fill_uniform_code": True,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "candidate_only": True,
        "startup_refresh": False,
        "retry": False,
        "fallback": False,
        "automatic_recovery": False,
        "autochain": False,
        "independent_factory_otp_white_successor_required": True,
        "fresh_successor_of_campaign_id": source_gate["source_tuple"]["campaign_id"],
        "source_is_current_v3_factory_white_complete": True,
        "source_camera_relative_only": True,
        "source_absolute_white_or_uniformity_qualified": False,
        "source_qualified_level_count": 0,
        "source_retained_action_to_capture_continuity_proven": False,
        "old_v2_campaign_modified_or_replayed": False,
    }
    return {
        "schema_version": 2,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_gate": source_gate,
        "actions": actions,
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


def dry_validate(*, verify_artifacts: bool = False) -> dict[str, Any]:
    report = build_report()
    compiled_source = validate_compiled_identity_source()
    actions = report["actions"]
    if (
        len(actions) != 4
        or len(report["contract"]["recipes"]) != 16
        or any(CS1_RECIPE_AT_CELL.count(recipe) != 4 for recipe in range(16))
        or CS2_RECIPE_AT_CELL != tuple(reversed(CS1_RECIPE_AT_CELL))
        or actions[2]["frame"] != actions[3]["frame"]
        or actions[2]["cs1_dtm"] != actions[3]["cs1_dtm"]
        or actions[2]["cs2_dtm"] != actions[3]["cs2_dtm"]
        or actions[2]["effective_driver_profile"]
        != actions[3]["effective_driver_profile"]
        or actions[2]["effective_driver_profile"]["id"]
        != "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
        or actions[2]["action_id"] == actions[3]["action_id"]
        or report["contract"]["autochain"] is not False
    ):
        raise LumaGrayMechanismV3PackError("V3 placement/action invariant differs")
    if verify_artifacts:
        if not artifacts_are_sealed():
            raise LumaGrayMechanismV3PackError("V3 artifacts are not sealed")
        for path, prefix in zip(artifact_paths(), ("bin", "elf"), strict=True):
            payload = path.read_bytes()
            if (
                len(payload) != ARTIFACTS[f"{prefix}_bytes"]
                or sha256_bytes(payload) != ARTIFACTS[f"{prefix}_sha256"]
            ):
                raise LumaGrayMechanismV3PackError(f"V3 {prefix} artifact differs")
        compiled_binary = validate_compiled_identity_binary()
    else:
        compiled_binary = None
    return {
        "schema_version": 2,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "source_gate_verified": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "action_count": 4,
        "recipes": 16,
        "repeats_per_recipe_per_controller": 4,
        "cs2_semantic_rotation_degrees": 180,
        "g4_explicit_optional_no_autochain": True,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "no_retry": True,
        "no_fallback": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": artifacts_are_sealed(),
        "compiled_identity_source": compiled_source,
        "compiled_identity_binary": compiled_binary,
        "contract_id": report["contract_id"],
        "descriptor_ids": [item["descriptor_id"] for item in actions],
        "action_ids": [item["action_id"] for item in actions],
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
