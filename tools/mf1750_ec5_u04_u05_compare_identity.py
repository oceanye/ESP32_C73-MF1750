#!/usr/bin/env python3
"""Frozen identity and frame for the fixed EC5 0x4-vs-0x5 comparison.

The visible action ID is the SHA-256 of the complete canonical preimage below.
The fixture is deliberately small and unambiguous: a white background with two
vertically aligned 64x64 patches on each controller half.  CS1 is U04 over U05;
CS2 is U05 over U04.  No dithering or spatial mixing is present.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from host.epd_frame import (
    HEIGHT,
    ROW_BYTES,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    pixel_counts,
    validate_frame,
)


ACTION_IDENTITY_SCHEMA_VERSION = 1
ACTION_IDENTITY_KIND = "mf1750-ec5-u04-u05-compare-visible-action-identity"
IDENTITY_REVISION = "u04-u05-compare-v1"
LAYOUT_ID = "EC5_U04_U05_QUAD64_DIAGONAL_V1"
DEVICE_API_VERSION = "MF1750_EC5_U04_U05_COMPARE_DEVICE_V1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
BUILD_TAG = "MF1750_EC5_U04_U05_QUAD64_DIAGONAL_V1_2026-08-09"
TEST_ID = "EC5-U04-U05-Q64-DIAGONAL-V1"
ENVIRONMENT = "esp32-s3-devkitc-1-ec5-u04-u05-compare"
LEGACY_NVS_NAMESPACE = "mf1750_ec5v2"
LEGACY_NVS_KEY = "u04v2_phase"
ACTIVE_NVS_NAMESPACE = "mf1750_ec5cmp"
ACTIVE_NVS_KEY = "u45cmp_phase"
CORRECTED_U04_ACTION_ID = (
    "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3"
)
AFTER_U04_WHITE_ACTION_ID = (
    "f528dcbab32691a1faeca019d1845d032ed2d1936be7d496ef9acaec5be07c01"
)
ACTION_IDENTITY_HASH_SCOPE = (
    "SHA-256 of the complete action_identity_preimage encoded as UTF-8 JSON "
    "with sorted keys, separators=(',', ':'), ensure_ascii=false, "
    "allow_nan=false; no prefix and no trailing newline"
)

ROIS = (
    {
        "roi_id": "CS1_TOP_U04",
        "controller": "CS1",
        "vertical_position": "top",
        "code": 4,
        "x0": 224,
        "x1": 288,
        "y0": 188,
        "y1": 252,
    },
    {
        "roi_id": "CS1_BOTTOM_U05",
        "controller": "CS1",
        "vertical_position": "bottom",
        "code": 5,
        "x0": 224,
        "x1": 288,
        "y0": 348,
        "y1": 412,
    },
    {
        "roi_id": "CS2_TOP_U05",
        "controller": "CS2",
        "vertical_position": "top",
        "code": 5,
        "x0": 736,
        "x1": 800,
        "y0": 188,
        "y1": 252,
    },
    {
        "roi_id": "CS2_BOTTOM_U04",
        "controller": "CS2",
        "vertical_position": "bottom",
        "code": 4,
        "x0": 736,
        "x1": 800,
        "y0": 348,
        "y1": 412,
    },
)

FRAME_SHA256 = "c3f1d19adb80169339d32a7e7e61bb5f3a0db9e2e823080412ea91227eaa310d"
FRAME_FNV1A = 2_591_702_469
CS1_DTM_SHA256 = "583a45a83f38139ea823294a1a0d6f4175bed44876ec94d883fcc04329dfdb50"
CS1_DTM_FNV1A = 1_706_167_749
CS2_DTM_SHA256 = "a9c4ced54fc456f424f615c6885dd661517ebdc8a12ee9581d1420e1a9996ad3"
CS2_DTM_FNV1A = 3_652_324_805


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def generate_frame() -> bytes:
    frame = bytearray(b"\x11" * (WIDTH * HEIGHT // 2))
    for roi in ROIS:
        x0 = int(roi["x0"])
        x1 = int(roi["x1"])
        code = int(roi["code"])
        pair = bytes(((code << 4) | code,))
        for y in range(int(roi["y0"]), int(roi["y1"])):
            start = y * ROW_BYTES + x0 // 2
            end = y * ROW_BYTES + x1 // 2
            frame[start:end] = pair * (end - start)
    result = bytes(frame)
    validate_frame(result, allowed_colors=(1, 4, 5))
    return result


def controller_streams(frame: bytes | None = None) -> tuple[bytes, bytes]:
    source = generate_frame() if frame is None else bytes(frame)
    validate_exact_frame(source)
    return (
        controller_stream(
            source, ControllerMapping(0), allowed_colors=(1, 4, 5)
        ),
        controller_stream(
            source, ControllerMapping(1), allowed_colors=(1, 4, 5)
        ),
    )


def validate_exact_frame(frame: bytes) -> None:
    view = validate_frame(frame, allowed_colors=(1, 4, 5))
    if bytes(view) != generate_frame():
        raise ValueError("frame differs from the frozen U04/U05 comparison")
    counts = pixel_counts(frame, allowed_colors=(1, 4, 5))
    if counts[1] != 598_016 or counts[4] != 8_192 or counts[5] != 8_192:
        raise ValueError("comparison frame histogram differs")


def generated_identity() -> dict[str, Any]:
    frame = generate_frame()
    cs1 = controller_stream(
        frame, ControllerMapping(0), allowed_colors=(1, 4, 5)
    )
    cs2 = controller_stream(
        frame, ControllerMapping(1), allowed_colors=(1, 4, 5)
    )
    return {
        "frame_bytes": len(frame),
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "frame_fnv1a": fnv1a(frame),
        "cs1_dtm_bytes": len(cs1),
        "cs1_dtm_sha256": hashlib.sha256(cs1).hexdigest(),
        "cs1_dtm_fnv1a": fnv1a(cs1),
        "cs2_dtm_bytes": len(cs2),
        "cs2_dtm_sha256": hashlib.sha256(cs2).hexdigest(),
        "cs2_dtm_fnv1a": fnv1a(cs2),
        "histogram": {"white": 598_016, "u04": 8_192, "u05": 8_192},
    }


_PREIMAGE: Mapping[str, Any] = {
    "schema_version": ACTION_IDENTITY_SCHEMA_VERSION,
    "kind": ACTION_IDENTITY_KIND,
    "identity_revision": IDENTITY_REVISION,
    "layout_id": LAYOUT_ID,
    "device_api_version": DEVICE_API_VERSION,
    "top_schema_version": TOP_SCHEMA_VERSION,
    "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
    "build_tag": BUILD_TAG,
    "test_id": TEST_ID,
    "frame_sha256": FRAME_SHA256,
    "frame_fnv1a": FRAME_FNV1A,
    "cs1_dtm_sha256": CS1_DTM_SHA256,
    "cs1_dtm_fnv1a": CS1_DTM_FNV1A,
    "cs2_dtm_sha256": CS2_DTM_SHA256,
    "cs2_dtm_fnv1a": CS2_DTM_FNV1A,
    "background_code": 1,
    "u04_pixel_count": 8_192,
    "u05_pixel_count": 8_192,
    "legacy_nvs_namespace": LEGACY_NVS_NAMESPACE,
    "legacy_nvs_key": LEGACY_NVS_KEY,
    "legacy_key_present_expected": True,
    "legacy_expected_phase": 2,
    "active_nvs_namespace": ACTIVE_NVS_NAMESPACE,
    "active_nvs_key": ACTIVE_NVS_KEY,
    "active_key_present_expected_before_arm": False,
    "maximum_arm_posts": 1,
    "maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "j2_off_diagnostic_get_requests": 4,
    "j2_off_diagnostic_post_requests": 0,
    "same_boot_nonce_required_for_visible_run": True,
    "corrected_u04_action_id": CORRECTED_U04_ACTION_ID,
    "after_u04_white_action_id": AFTER_U04_WHITE_ACTION_ID,
    "thirty_minute_hold_required": False,
    "operator_short_hold_skip_boundary_required": True,
    "visible_action_semantics": (
        "single_fixed_u04_vs_u05_nodither_diagonal_crossover_after_deep_"
        "validated_u04_and_white_recovery"
    ),
}

FROZEN_ACTION_ID = "70db952b1d708511e1fdcb166b43cd5828fe232562b14d341d848942787d1700"


def action_identity_preimage() -> dict[str, Any]:
    return deepcopy(dict(_PREIMAGE))


def derive_action_id(preimage: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(preimage))).hexdigest()


def action_id() -> str:
    return derive_action_id(action_identity_preimage())


def nvs_contract() -> dict[str, Any]:
    return {
        "legacy": {
            "namespace": LEGACY_NVS_NAMESPACE,
            "key": LEGACY_NVS_KEY,
            "expected_present": True,
            "expected_phase": 2,
            "read_only": True,
        },
        "active": {
            "namespace": ACTIVE_NVS_NAMESPACE,
            "key": ACTIVE_NVS_KEY,
            "expected_present": False,
            "expected_phase": 0,
            "read_only": False,
        },
    }


def variant() -> dict[str, Any]:
    return {
        "comparison_id": "U04_U05",
        "environment": ENVIRONMENT,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "action_id": action_id(),
        "identity_revision": IDENTITY_REVISION,
        "device_api_version": DEVICE_API_VERSION,
        "top_schema_version": TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "layout_id": LAYOUT_ID,
        **generated_identity(),
        "rois": deepcopy(list(ROIS)),
        "action_identity_preimage": action_identity_preimage(),
        "action_identity_sha256_scope": ACTION_IDENTITY_HASH_SCOPE,
        "nvs_contract": nvs_contract(),
        "firmware_file": "firmware-u04-u05-compare.bin",
        "elf_file": "firmware-u04-u05-compare.elf",
    }


def validate_frozen_identity() -> None:
    generated = generated_identity()
    expected = {
        "frame_sha256": FRAME_SHA256,
        "frame_fnv1a": FRAME_FNV1A,
        "cs1_dtm_sha256": CS1_DTM_SHA256,
        "cs1_dtm_fnv1a": CS1_DTM_FNV1A,
        "cs2_dtm_sha256": CS2_DTM_SHA256,
        "cs2_dtm_fnv1a": CS2_DTM_FNV1A,
    }
    for key, value in expected.items():
        if generated[key] != value:
            raise RuntimeError(f"comparison {key} drifted")
    if action_id() != FROZEN_ACTION_ID:
        raise RuntimeError("comparison action identity drifted")


validate_frozen_identity()
