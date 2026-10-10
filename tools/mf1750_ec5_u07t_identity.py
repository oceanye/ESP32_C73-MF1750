#!/usr/bin/env python3
"""Frozen identity for the independent technical-only EC5 U07T action.

U07T intentionally uses the same no-dither 0x7 frame geometry as the formal
U07 candidate, but it has a different action identity, device API and NVS
namespace.  It can only produce descriptive technical evidence and is never a
substitute for the formal U07 qualification action.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


ACTION_IDENTITY_SCHEMA_VERSION = 1
ACTION_IDENTITY_KIND = "mf1750-ec5-u07t-technical-visible-action-identity"
ACTION_IDENTITY_HASH_SCOPE = (
    "SHA-256 of the complete action_identity_preimage encoded as UTF-8 JSON "
    "with sorted keys, separators=(',', ':'), ensure_ascii=false, "
    "allow_nan=false; no prefix and no trailing newline"
)
IDENTITY_REVISION = "u07t-technical-v1"
# This historical identity was invalidated before any U07T device access when
# the 23:14 U04/U05 comparison became an intervening visible refresh. Keep its
# canonical preimage reproducible for audit, but never execute it.
EXECUTION_ELIGIBLE = False
INVALIDATION_REASON = (
    "intervening_u04_u05_compare_70db_visible_refresh_after_bound_u04_white"
)
LAYOUT_ID = "EC5_MIRROR64_CENTER_V1"
DEVICE_API_VERSION = "MF1750_EC5_U07T_DEVICE_V1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
BUILD_TAG = "MF1750_EC5_U07T_MIRROR64_CENTER_TECHNICAL_V1_2026-08-09"
TEST_ID = "EC5-U07T-I01-P01-L64M1"
ENVIRONMENT = "esp32-s3-devkitc-1-ec5-u07t"

FRAME_SHA256 = "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e"
FRAME_FNV1A = 0xA1C5ADC5
DTM_SHA256 = "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac"
DTM_FNV1A = 0x97F125C5

FORMAL_NVS_NAMESPACE = "mf1750_ec5v2"
FORMAL_U04_NVS_KEY = "u04v2_phase"
FORMAL_U07_NVS_KEY = "u07v2_phase"
ACTIVE_NVS_NAMESPACE = "mf1750_ec5t"
ACTIVE_NVS_KEY = "u07t_phase"

CORRECTED_U04_ACTION_ID = (
    "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3"
)
FORMAL_U07_ACTION_ID = (
    "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae"
)
FORMAL_CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-physical-claim-registry-v1"
TECHNICAL_CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-u07t-technical-claims-v1"
CORRECTED_U04_RELEASE_CANONICAL_SHA256 = (
    "0c7fd578537177308398e973c794b895f929d16b785b8573e920f8f564b42183"
)
CORRECTED_U04_RESULT_FILE_SHA256 = (
    "005c2363d012b1985ca10bdff78a1266b2942bf70d273a1c2d151ec05a6ba4b7"
)
CORRECTED_U04_CLAIM_FILE_SHA256 = (
    "a9fdb2274cb3ba733aec48a5bd675a70e57d8f4c767c4c0975cd24dfe9ad0d3f"
)
U04_SHORT_HOLD_FILE_SHA256 = (
    "b8a4ca04cc3d3114c399596dce9b15296628a16dd4779ff4f4157427f5fb7b8f"
)
AFTER_U04_WHITE_ACTION_ID = (
    "f528dcbab32691a1faeca019d1845d032ed2d1936be7d496ef9acaec5be07c01"
)
AFTER_U04_WHITE_RESULT_FILE_SHA256 = (
    "234b34f67a1135ac3b89c7dc197f9b0a814c179996483c6f0bd28ff7d1c7fe83"
)
AFTER_U04_WHITE_CLAIM_FILE_SHA256 = (
    "51de68b5446f22212d808da9729af9e86d7a3dd6b288657aad651de257b962d9"
)
AFTER_U04_WHITE_OBSERVATION_FILE_SHA256 = (
    "d809844fe86801104f7835780e32d672bb678132470f6fd5ab11356a2d74bf4a"
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


_PREIMAGE: Mapping[str, Any] = {
    "schema_version": ACTION_IDENTITY_SCHEMA_VERSION,
    "kind": ACTION_IDENTITY_KIND,
    "identity_revision": IDENTITY_REVISION,
    "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
    "layout_id": LAYOUT_ID,
    "candidate_id": "U07T",
    "candidate_code": 7,
    "device_api_version": DEVICE_API_VERSION,
    "top_schema_version": TOP_SCHEMA_VERSION,
    "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
    "build_tag": BUILD_TAG,
    "test_id": TEST_ID,
    "frame_sha256": FRAME_SHA256,
    "frame_fnv1a": FRAME_FNV1A,
    "dtm_sha256": DTM_SHA256,
    "dtm_fnv1a": DTM_FNV1A,
    "background_code": 1,
    "candidate_pixel_count": 8192,
    "dithering_present": False,
    "spatial_mixing_present": False,
    "formal_nvs_namespace": FORMAL_NVS_NAMESPACE,
    "formal_u04_nvs_key": FORMAL_U04_NVS_KEY,
    "formal_u04_key_present_expected": True,
    "formal_u04_expected_phase": 2,
    "formal_u07_nvs_key": FORMAL_U07_NVS_KEY,
    "formal_u07_key_present_expected": False,
    "formal_u07_expected_phase": 0,
    "active_nvs_namespace": ACTIVE_NVS_NAMESPACE,
    "active_nvs_key": ACTIVE_NVS_KEY,
    "active_key_present_expected_before_arm": False,
    "active_expected_phase_before_arm": 0,
    "corrected_u04_action_id": CORRECTED_U04_ACTION_ID,
    "corrected_u04_release_canonical_sha256": (
        CORRECTED_U04_RELEASE_CANONICAL_SHA256
    ),
    "corrected_u04_result_file_sha256": CORRECTED_U04_RESULT_FILE_SHA256,
    "corrected_u04_claim_file_sha256": CORRECTED_U04_CLAIM_FILE_SHA256,
    "u04_short_hold_file_sha256": U04_SHORT_HOLD_FILE_SHA256,
    "u04_five_minute_observation_required": True,
    "u04_thirty_minute_observation_expected_status": "SKIPPED_BY_OPERATOR",
    "formal_u07_review_gate_expected_satisfied": False,
    "after_u04_white_action_id": AFTER_U04_WHITE_ACTION_ID,
    "after_u04_white_result_file_sha256": AFTER_U04_WHITE_RESULT_FILE_SHA256,
    "after_u04_white_claim_file_sha256": AFTER_U04_WHITE_CLAIM_FILE_SHA256,
    "after_u04_white_observation_file_sha256": (
        AFTER_U04_WHITE_OBSERVATION_FILE_SHA256
    ),
    "after_u04_white_expected_outcome": "complete_pass",
    "after_u04_white_expected_decision": "VISUAL_AND_ELECTRICAL_PASS",
    "maximum_arm_posts": 1,
    "maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "j2_off_diagnostic_get_requests": 4,
    "j2_off_diagnostic_post_requests": 0,
    "same_boot_nonce_required_for_visible_run": True,
    "formal_u07_action_must_remain_unclaimed": True,
    "formal_u07_action_id": FORMAL_U07_ACTION_ID,
    "formal_claim_registry_id": FORMAL_CLAIM_REGISTRY_ID,
    "technical_claim_registry_id": TECHNICAL_CLAIM_REGISTRY_ID,
    "formal_u07_claim_absence_checked_before_and_after_action": True,
    "technical_claim_registry_must_differ_from_formal_registry": True,
    "formal_u07_nvs_never_written_or_cleared": True,
    "visible_action_semantics": (
        "single_technical_u07_nodither_probe_after_exact_u04_short_hold_"
        "boundary_and_clean_white_recovery"
    ),
}

# Frozen after independent canonical derivation; see validate_frozen_identity().
FROZEN_ACTION_ID = "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310"


def action_identity_preimage() -> dict[str, Any]:
    return deepcopy(dict(_PREIMAGE))


def derive_action_id(preimage: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(preimage))).hexdigest()


def action_id() -> str:
    return derive_action_id(action_identity_preimage())


def nvs_contract() -> dict[str, Any]:
    return {
        "formal_u04": {
            "namespace": FORMAL_NVS_NAMESPACE,
            "key": FORMAL_U04_NVS_KEY,
            "expected_present": True,
            "expected_phase": 2,
            "read_only": True,
        },
        "formal_u07": {
            "namespace": FORMAL_NVS_NAMESPACE,
            "key": FORMAL_U07_NVS_KEY,
            "expected_present": False,
            "expected_phase": 0,
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
        "candidate_id": "U07T",
        "candidate_code": 7,
        "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
        "environment": ENVIRONMENT,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "action_id": action_id(),
        "identity_revision": IDENTITY_REVISION,
        "device_api_version": DEVICE_API_VERSION,
        "top_schema_version": TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "layout_id": LAYOUT_ID,
        "frame_sha256": FRAME_SHA256,
        "frame_fnv1a": FRAME_FNV1A,
        "dtm_sha256": DTM_SHA256,
        "dtm_fnv1a": DTM_FNV1A,
        "action_identity_preimage": action_identity_preimage(),
        "action_identity_sha256_scope": ACTION_IDENTITY_HASH_SCOPE,
        "nvs_contract": nvs_contract(),
        "firmware_file": "firmware-u07t.bin",
        "elf_file": "firmware-u07t.elf",
    }


def validate_frozen_identity() -> None:
    derived = action_id()
    if derived != FROZEN_ACTION_ID:
        raise RuntimeError(
            f"U07T action identity drift: expected {FROZEN_ACTION_ID}, got {derived}"
        )


validate_frozen_identity()
