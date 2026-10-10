#!/usr/bin/env python3
"""Frozen offline contract for the blocked single-flash EC5 COLOR_LAB.

This module composes existing, byte-audited Stage-A/Stage-B fixtures with the
balanced 0x0..0x7 atlas. It supplies 23 deterministic static offline action
identities, but no executable/materialized hardware authorization, and it
performs no I/O. ``EXECUTION_ELIGIBLE`` remains false.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_ec5_sixstate_nodither as sixstate


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-color-lab-offline-campaign-contract"
CAMPAIGN_ID = "EC5_COLOR_LAB_CAMPAIGN_V1"
BUILD_TAG = "MF1750_EC5_COLOR_LAB_V1_2026-08-09"
TEST_ID = "EC5-COLOR-LAB-V1"
DEVICE_API_VERSION = "MF1750_EC5_COLOR_LAB_DEVICE_V1"
IDENTITY_REVISION = "color-lab-v1"
LAYOUT_ID = "EC5_COLOR_LAB_COMPOSED_FIXED_FRAMES_V1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
EXECUTION_ELIGIBLE = False
NVS_NAMESPACE = "mf1750_ec5cl"
NVS_KEY = "cursor"
MAX_ROUNDS = 3
ROUND_ONE_STOP_ORDINAL = 11

ROLE_WHITE = "WHITE"
ROLE_U07_ISOLATED = "U07_ISOLATED"
ROLE_ATLAS = "ATLAS_0_7"
ROLE_U04_PRIMER = "U04_SIXSTATE_PRIMER"
ROLE_U04_TARGET = "U04_SIXSTATE_TARGET"
ROLE_U07_PRIMER = "U07_SIXSTATE_PRIMER"
ROLE_U07_TARGET = "U07_SIXSTATE_TARGET"
ROLES = (
    ROLE_WHITE,
    ROLE_U07_ISOLATED,
    ROLE_ATLAS,
    ROLE_U04_PRIMER,
    ROLE_U04_TARGET,
    ROLE_U07_PRIMER,
    ROLE_U07_TARGET,
)


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _set_pixel(frame: bytearray, x: int, y: int, code: int) -> None:
    offset = y * atlas.ROW_BYTES + x // 2
    if x & 1:
        frame[offset] = (frame[offset] & 0xF0) | code
    else:
        frame[offset] = (frame[offset] & 0x0F) | (code << 4)


def _u07_isolated_frame() -> bytes:
    frame = bytearray(b"\x11" * atlas.FRAME_BYTES)
    for x0 in (224, 736):
        for y in range(268, 332):
            for x in range(x0, x0 + 64):
                _set_pixel(frame, x, y, 7)
    return bytes(frame)


def role_frame(role: str) -> bytes:
    if role == ROLE_WHITE:
        return atlas.build_frame("white")
    if role == ROLE_U07_ISOLATED:
        return _u07_isolated_frame()
    if role == ROLE_ATLAS:
        return atlas.build_frame("atlas")
    if role == ROLE_U04_PRIMER:
        return sixstate.build_frames(4)[0]
    if role == ROLE_U04_TARGET:
        return sixstate.build_frames(4)[1]
    if role == ROLE_U07_PRIMER:
        return sixstate.build_frames(7)[0]
    if role == ROLE_U07_TARGET:
        return sixstate.build_frames(7)[1]
    raise ValueError(f"unknown COLOR_LAB role {role}")


def _controller_stream(frame: bytes, half: int) -> bytes:
    return atlas.controller_stream(frame, half)


def _identity(payload: bytes) -> dict[str, Any]:
    fnv = _fnv1a(payload)
    return {
        "bytes": len(payload),
        "sha256": _sha(payload),
        "fnv1a_u32": fnv,
        "fnv1a_hex": f"0x{fnv:08x}",
    }


def generated_role_identity(role: str) -> dict[str, Any]:
    frame = role_frame(role)
    return {
        "role": role,
        "frame": _identity(frame),
        "cs1_dtm": _identity(_controller_stream(frame, 0)),
        "cs2_dtm": _identity(_controller_stream(frame, 1)),
    }


ROLE_IDENTITIES: Mapping[str, Mapping[str, Any]] = {
    role: generated_role_identity(role) for role in ROLES
}

FROZEN_ROLE_SHA256: Mapping[str, tuple[str, str, str]] = {
    ROLE_WHITE: (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    ),
    ROLE_U07_ISOLATED: (
        "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
        "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
    ),
    ROLE_ATLAS: (
        "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b",
        "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7",
        "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943",
    ),
    ROLE_U04_PRIMER: (
        "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
        "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
        "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
    ),
    ROLE_U04_TARGET: (
        "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6",
        "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
        "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
    ),
    ROLE_U07_PRIMER: (
        "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
        "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
        "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
    ),
    ROLE_U07_TARGET: (
        "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21",
        "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
        "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
    ),
}


def _required_gates(role: str, ordinal: int) -> list[str]:
    if ordinal == 1:
        return [
            "u04_u05_compare_complete_pass_result_claim_and_observation",
            "fresh_formal_u07_claim_absence",
            "operator_electrical_and_physical_cutoff_ready",
        ]
    gates = [
        "exact_previous_color_lab_result_and_manual_observation",
        "same_boot_nonce",
        "fresh_formal_u07_claim_absence",
    ]
    if role == ROLE_ATLAS:
        gates += [
            "isolated_u07_action_complete_pass_and_technical_claim",
            "isolated_u07_manual_observation",
            "immediately_preceding_clean_white_result_and_observation",
        ]
    if role == ROLE_U07_TARGET:
        gates.append("u07_primer_map_fidelity_manual_pass")
    if role == ROLE_U04_TARGET:
        gates.append("u04_primer_map_fidelity_manual_pass")
    return gates


def _sequence_rows() -> list[tuple[str, int, str]]:
    rows = [
        (ROLE_WHITE, 0, "COMPARE_AFTER_WHITE"),
        (ROLE_U07_ISOLATED, 0, "ISOLATED_U07"),
        (ROLE_WHITE, 0, "AFTER_ISOLATED_U07_WHITE"),
        (ROLE_ATLAS, 0, "BALANCED_EIGHTCODE_ATLAS"),
        (ROLE_WHITE, 0, "AFTER_ATLAS_WHITE"),
    ]
    for round_index in range(1, MAX_ROUNDS + 1):
        rows += [
            (ROLE_U04_PRIMER, round_index, "U04_SIXSTATE"),
            (ROLE_U04_TARGET, round_index, "U04_SIXSTATE"),
            (ROLE_WHITE, round_index, "AFTER_U04_SIXSTATE_WHITE"),
            (ROLE_U07_PRIMER, round_index, "U07_SIXSTATE"),
            (ROLE_U07_TARGET, round_index, "U07_SIXSTATE"),
            (ROLE_WHITE, round_index, "AFTER_U07_SIXSTATE_WHITE"),
        ]
    return rows


def action_descriptors() -> list[dict[str, Any]]:
    rows = _sequence_rows()
    result: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, round_index, branch) in enumerate(rows, start=1):
        identity = ROLE_IDENTITIES[role]
        prior = result[-1] if result else None
        descriptor_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-color-lab-action-descriptor",
            "campaign_id": CAMPAIGN_ID,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "device_api_version": DEVICE_API_VERSION,
            "identity_revision": IDENTITY_REVISION,
            "ordinal": ordinal,
            "role": role,
            "round": round_index,
            "branch": branch,
            "expected_prior_ordinal": None if prior is None else prior["ordinal"],
            "expected_prior_role": None if prior is None else prior["role"],
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "required_host_gates": _required_gates(role, ordinal),
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": False,
            "automatic_chaining": False,
        }
        descriptor_id = hashlib.sha256(
            canonical_json_bytes(descriptor_preimage)
        ).hexdigest()
        action_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-color-lab-visible-action-identity",
            "campaign_id": CAMPAIGN_ID,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "device_api_version": DEVICE_API_VERSION,
            "identity_revision": IDENTITY_REVISION,
            "nvs_namespace": NVS_NAMESPACE,
            "nvs_key": NVS_KEY,
            "ordinal": ordinal,
            "descriptor_id": descriptor_id,
            "role": role,
            "round": round_index,
            "branch": branch,
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "prior_static_action_id": prior_action_id,
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": False,
            "automatic_chaining": False,
            "visible_action_semantics": (
                "one_explicitly_armed_fixed_compiled_frame_refresh"
            ),
        }
        action_id = hashlib.sha256(canonical_json_bytes(action_preimage)).hexdigest()
        result.append(
            {
                **descriptor_preimage,
                "descriptor_id": descriptor_id,
                "hardware_action_id": action_id,
                "action_identity_preimage": action_preimage,
                "execution_eligible": False,
            }
        )
        prior_action_id = action_id
    return result


DESCRIPTORS = tuple(action_descriptors())


def campaign_manifest() -> dict[str, Any]:
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": CAMPAIGN_ID,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "layout_id": LAYOUT_ID,
        "top_schema_version": TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "execution_eligible": EXECUTION_ELIGIBLE,
        "nvs_contract": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
            "initial_key_present": False,
            "initial_value": 1,
        },
        "maximum_rounds": MAX_ROUNDS,
        "round_one_safe_stop_completed_ordinal": ROUND_ONE_STOP_ORDINAL,
        "round_one_safe_stop_next_ordinal": ROUND_ONE_STOP_ORDINAL + 1,
        "descriptors": deepcopy(list(DESCRIPTORS)),
        "roles": deepcopy(dict(ROLE_IDENTITIES)),
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "dithering_present": False,
        "spatial_mixing_present": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "normal_step_requires_reflash_reset_or_j2_cycle": False,
        "hardware_gate": (
            "blocked_until_current_real_host_evidence_and_per_action_manual_"
            "authorization_are_materialized"
        ),
    }
    root["contract_id"] = hashlib.sha256(canonical_json_bytes(root)).hexdigest()
    return root


def validate_contract() -> None:
    if len(DESCRIPTORS) != 23:
        raise RuntimeError("COLOR_LAB descriptor count drifted")
    if DESCRIPTORS[ROUND_ONE_STOP_ORDINAL - 1]["role"] != ROLE_WHITE:
        raise RuntimeError("round-one stop is not after authoritative white")
    if ROLE_IDENTITIES[ROLE_WHITE]["frame"]["sha256"] != FROZEN_ROLE_SHA256[
        ROLE_WHITE
    ][0]:
        raise RuntimeError("authoritative white frame drifted")
    for role, expected in FROZEN_ROLE_SHA256.items():
        generated = ROLE_IDENTITIES[role]
        actual = (
            generated["frame"]["sha256"],
            generated["cs1_dtm"]["sha256"],
            generated["cs2_dtm"]["sha256"],
        )
        if actual != expected:
            raise RuntimeError(f"{role} compiled role identity drifted")
    if len({item["descriptor_id"] for item in DESCRIPTORS}) != len(DESCRIPTORS):
        raise RuntimeError("COLOR_LAB descriptor IDs are not unique")
    action_ids = [item["hardware_action_id"] for item in DESCRIPTORS]
    if len(set(action_ids)) != len(action_ids):
        raise RuntimeError("COLOR_LAB action IDs are not unique")
    for index, descriptor in enumerate(DESCRIPTORS):
        expected_prior = None if index == 0 else action_ids[index - 1]
        if descriptor["action_identity_preimage"]["prior_static_action_id"] != expected_prior:
            raise RuntimeError("COLOR_LAB static prior action chain drifted")


validate_contract()
