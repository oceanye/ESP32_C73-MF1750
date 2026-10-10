#!/usr/bin/env python3
"""Frozen identity for the U04-vs-U05 comparison white recovery.

This is a new, independent host action.  It reuses only the already proven
RC2G firmware and solid-white frame bytes.  It does not reuse any baseline,
after-U04, or formal after-U07 white action/claim identity.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u04-u05-compare-white-action-identity"
IDENTITY_REVISION = "compare-white-v1"
STAGE = "after-u04-u05-compare"

COMPARE_ACTION_ID = (
    "70db952b1d708511e1fdcb166b43cd5828fe232562b14d341d848942787d1700"
)
COMPARE_RELEASE_CANONICAL_SHA256 = (
    "d871869e14e4df3fb2e5f0ed7188588d0ed4548f102c5572ebca4a6a991f7fa5"
)
COMPARE_RELEASE_FILE_SHA256 = (
    "ef7a31ef85a7fbc5ba770d8076af0d2577bb0817336cd5afa71e219b69fd2ee9"
)
COMPARE_RESULT_FILE_SHA256 = (
    "5d1c07fee3e8cf2d662f4a5346595694dff3491784bc27326ab6d222c48b423b"
)
COMPARE_RESULT_INTEGRITY_SHA256 = (
    "45c6b502a766911846b24a248e834c6c030484c61abac3f6bf13fd33722842b0"
)
COMPARE_CLAIM_FILE_SHA256 = (
    "39c3f1e50cc88b85729ec88041992a6b92da11928c937e80c70c874ac4796efc"
)
COMPARE_OBSERVATION_FILE_SHA256 = (
    "2f45f458c5e2b3ec08d991e16b4ebfea536205cf92a1bdefcbbe662221288a6f"
)

RC2G_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_"
    "WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
RC2G_BINARY_BYTES = 815_664
RC2G_BINARY_SHA256 = (
    "9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772"
)
WHITE_FRAME_SHA256 = (
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
)
WHITE_FRAME_FNV1A = 0x13340DC5
WHITE_DTM_FNV1A = 0xB7A855C5

CLAIM_REGISTRY_ID = (
    "workspace-mf1750-ec5-u04-u05-compare-white-claims-v1"
)
FORMAL_WHITE_ACTION_IDS = {
    "baseline": "aace554437b5377138825a473dbb0be1591fc472424c446d77e148bae9eeded7",
    "after_u04": "f528dcbab32691a1faeca019d1845d032ed2d1936be7d496ef9acaec5be07c01",
    "after_u07": "feb0a26499921516473ca68d10ed6a51e1ffd5672f29bae67b46590d3b7f9cf4",
}

HASH_SCOPE = (
    "SHA-256 of the complete action preimage encoded as canonical UTF-8 JSON "
    "with sorted keys, separators=(',', ':'), ensure_ascii=false and "
    "allow_nan=false; no prefix and no trailing newline"
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
    "schema_version": SCHEMA_VERSION,
    "kind": KIND,
    "identity_revision": IDENTITY_REVISION,
    "stage": STAGE,
    "compare_action_id": COMPARE_ACTION_ID,
    "compare_release_canonical_sha256": COMPARE_RELEASE_CANONICAL_SHA256,
    "compare_release_file_sha256": COMPARE_RELEASE_FILE_SHA256,
    "compare_result_file_sha256": COMPARE_RESULT_FILE_SHA256,
    "compare_result_integrity_sha256": COMPARE_RESULT_INTEGRITY_SHA256,
    "compare_claim_file_sha256": COMPARE_CLAIM_FILE_SHA256,
    "compare_observation_file_sha256": COMPARE_OBSERVATION_FILE_SHA256,
    "compare_observation_required_before_recovery": True,
    "rc2g_build_tag": RC2G_BUILD_TAG,
    "rc2g_binary_bytes": RC2G_BINARY_BYTES,
    "rc2g_binary_sha256": RC2G_BINARY_SHA256,
    "white_frame_sha256": WHITE_FRAME_SHA256,
    "white_frame_fnv1a": WHITE_FRAME_FNV1A,
    "white_dtm_fnv1a": WHITE_DTM_FNV1A,
    "claim_registry_id": CLAIM_REGISTRY_ID,
    "formal_white_action_ids_forbidden": deepcopy(FORMAL_WHITE_ACTION_IDS),
    "j2_off_flash_gate_required": True,
    "j2_off_gate_network_requests": 0,
    "j2_off_gate_claim_created": False,
    "j2_on_get_only_preflight_requests": 4,
    "claim_created_before_first_post": True,
    "maximum_frame_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "visible_action_semantics": (
        "one_exact_rc2g_solid_white_refresh_after_deep_validated_"
        "u04_u05_comparison_and_blind_manual_observation"
    ),
}

# Frozen after independent canonical derivation and authoritative white-frame
# replay.  Any later evidence change therefore creates a different action.
FROZEN_ACTION_ID = (
    "f9d41bfcd55558391cf189da2ffbe4606f4c81fa1edd896c0b59e227e9ec1f36"
)


def action_preimage() -> dict[str, Any]:
    return deepcopy(dict(_PREIMAGE))


def derive_action_id(preimage: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(preimage))).hexdigest()


def action_id() -> str:
    return derive_action_id(action_preimage())


def validate_frozen_identity() -> None:
    derived = action_id()
    if derived != FROZEN_ACTION_ID:
        raise RuntimeError(
            f"compare-white action drift: expected {FROZEN_ACTION_ID}, got {derived}"
        )


validate_frozen_identity()
