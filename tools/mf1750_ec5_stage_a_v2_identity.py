#!/usr/bin/env python3
"""Single source of truth for corrected Stage-A V2 action identities.

The visible ``action_id`` is the SHA-256 of the exact canonical JSON preimage
returned by :func:`action_identity_preimage`.  No domain prefix, newline, or
excluded field is involved.  Firmware constants, release construction, and the
physical runner must all consume this module (or generated values checked
against it) instead of maintaining independent literals.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


ACTION_IDENTITY_SCHEMA_VERSION = 1
ACTION_IDENTITY_KIND = "mf1750-ec5-stage-a-v2-visible-action-identity"
ACTION_IDENTITY_HASH_SCOPE = (
    "SHA-256 of the complete action_identity_preimage encoded as UTF-8 JSON "
    "with sorted keys, separators=(',', ':'), ensure_ascii=false, "
    "allow_nan=false; no prefix and no trailing newline"
)
IDENTITY_REVISION = "corrected-v2"
LAYOUT_ID = "EC5_MIRROR64_CENTER_V1"
DEVICE_API_VERSION = "MF1750_EC5_DEVICE_V3"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
LEGACY_NVS_NAMESPACE = "mf1750_ec5"
ACTIVE_NVS_NAMESPACE = "mf1750_ec5v2"

_COMMON_PREIMAGE: Mapping[str, Any] = {
    "schema_version": ACTION_IDENTITY_SCHEMA_VERSION,
    "kind": ACTION_IDENTITY_KIND,
    "identity_revision": IDENTITY_REVISION,
    "layout_id": LAYOUT_ID,
    "device_api_version": DEVICE_API_VERSION,
    "maximum_arm_posts": 1,
    "maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "visible_action_semantics": (
        "single_unknown_code_probe_after_get_only_driver_guard_preflight"
    ),
    "active_nvs_namespace": ACTIVE_NVS_NAMESPACE,
    "active_key_present_expected_before_arm": False,
}

_CANDIDATE_PREIMAGE: Mapping[str, Mapping[str, Any]] = {
    "U04": {
        "candidate_id": "U04",
        "candidate_code": 4,
        "build_tag": (
            "MF1750_EC5_U04_MIRROR64_CENTER_V2_CORRECTED_2026-08-09"
        ),
        "test_id": "EC5-U04-I02-P01-L64M1",
        "frame_sha256": (
            "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e"
        ),
        "dtm_sha256": (
            "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00"
        ),
        "legacy_nvs_namespace": LEGACY_NVS_NAMESPACE,
        "legacy_nvs_key": "u04_phase",
        "legacy_key_present_expected": True,
        "legacy_expected_phase": 2,
        "active_nvs_key": "u04v2_phase",
    },
    "U07": {
        "candidate_id": "U07",
        "candidate_code": 7,
        "build_tag": (
            "MF1750_EC5_U07_MIRROR64_CENTER_V2_CORRECTED_2026-08-09"
        ),
        "test_id": "EC5-U07-I02-P01-L64M1",
        "frame_sha256": (
            "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e"
        ),
        "dtm_sha256": (
            "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac"
        ),
        "legacy_nvs_namespace": LEGACY_NVS_NAMESPACE,
        "legacy_nvs_key": "u07_phase",
        "legacy_key_present_expected": False,
        "legacy_expected_phase": 0,
        "active_nvs_key": "u07v2_phase",
    },
}

FROZEN_ACTION_IDS: Mapping[str, str] = {
    "U04": "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3",
    "U07": "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae",
}

FRAME_FNV1A: Mapping[str, int] = {
    "U04": 0x68533DC5,
    "U07": 0xA1C5ADC5,
}
DTM_FNV1A: Mapping[str, int] = {
    "U04": 0x15B7EDC5,
    "U07": 0x97F125C5,
}

V1_BINARY_IDENTITY_TOKENS = (
    "MF1750_EC5_U04_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
    "MF1750_EC5_U07_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
    "EC5-U04-I01-P01-L64M1",
    "EC5-U07-I01-P01-L64M1",
    "bf2fcbcb29a35cf0a7915c67b48468aca26f7a35aef20e9ff68c9d60a37d0df5",
    "8568ba9cb5dd933d8c1f9a4028fffbd27f37aacf2017cb92f27c423b5cfa48e4",
)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode the exact action-identity canonical JSON byte stream."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _candidate(candidate_id: str) -> str:
    normalized = candidate_id.upper()
    if normalized not in _CANDIDATE_PREIMAGE:
        raise ValueError("candidate_id must be U04 or U07")
    return normalized


def action_identity_preimage(candidate_id: str) -> dict[str, Any]:
    """Return an independent copy of the frozen canonical preimage."""

    candidate = _candidate(candidate_id)
    return deepcopy(dict(_COMMON_PREIMAGE) | dict(_CANDIDATE_PREIMAGE[candidate]))


def derive_action_id(preimage: Mapping[str, Any]) -> str:
    """Derive one action ID without silently filling or removing fields."""

    return hashlib.sha256(canonical_json_bytes(dict(preimage))).hexdigest()


def action_id(candidate_id: str) -> str:
    return derive_action_id(action_identity_preimage(candidate_id))


def nvs_contract(candidate_id: str) -> dict[str, Any]:
    preimage = action_identity_preimage(candidate_id)
    return {
        "legacy": {
            "namespace": preimage["legacy_nvs_namespace"],
            "key": preimage["legacy_nvs_key"],
            "expected_present": preimage["legacy_key_present_expected"],
            "expected_phase": preimage["legacy_expected_phase"],
            "read_only": True,
        },
        "active": {
            "namespace": preimage["active_nvs_namespace"],
            "key": preimage["active_nvs_key"],
            "expected_present": preimage[
                "active_key_present_expected_before_arm"
            ],
            "expected_phase": 0,
            "read_only": False,
        },
    }


def variant(candidate_id: str) -> dict[str, Any]:
    """Return release-facing values derived from the same frozen preimage."""

    candidate = _candidate(candidate_id)
    preimage = action_identity_preimage(candidate)
    return {
        "candidate_id": candidate,
        "candidate_code": preimage["candidate_code"],
        "environment": f"esp32-s3-devkitc-1-ec5-{candidate.lower()}",
        "build_tag": preimage["build_tag"],
        "test_id": preimage["test_id"],
        "action_id": action_id(candidate),
        "identity_revision": IDENTITY_REVISION,
        "device_api_version": DEVICE_API_VERSION,
        "top_schema_version": TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "layout_id": LAYOUT_ID,
        "frame_sha256": preimage["frame_sha256"],
        "frame_fnv1a": FRAME_FNV1A[candidate],
        "dtm_sha256": preimage["dtm_sha256"],
        "dtm_fnv1a": DTM_FNV1A[candidate],
        "action_identity_preimage": preimage,
        "action_identity_sha256_scope": ACTION_IDENTITY_HASH_SCOPE,
        "nvs_contract": nvs_contract(candidate),
        "firmware_file": f"firmware-{candidate.lower()}.bin",
        "elf_file": f"firmware-{candidate.lower()}.elf",
    }


VARIANTS: Mapping[str, Mapping[str, Any]] = {
    candidate: variant(candidate) for candidate in ("U04", "U07")
}


def validate_frozen_identities() -> None:
    for candidate, frozen in FROZEN_ACTION_IDS.items():
        derived = action_id(candidate)
        if derived != frozen:
            raise RuntimeError(
                f"{candidate} action identity drift: expected {frozen}, got {derived}"
            )
        if VARIANTS[candidate]["action_id"] != frozen:
            raise RuntimeError(f"{candidate} release variant action identity drift")


validate_frozen_identities()

