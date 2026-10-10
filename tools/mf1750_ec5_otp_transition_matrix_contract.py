#!/usr/bin/env python3
"""Frozen offline contract for the factory-OTP 8x8 transition matrix.

This contract describes three explicit visible actions: establish all eight
old transport states, apply all eight new transport states, and return to the
known factory-OTP white state.  It changes neither the panel LUT nor any
electrical parameter and contains no device, network, serial, or refresh path.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from host import otp_transition_matrix as matrix


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-otp-transition-matrix-offline-campaign-contract"
CAMPAIGN_ID = "EC5_OTP_TRANSITION_MATRIX_CAMPAIGN_V1"
BUILD_TAG = "MF1750_EC5_OTP_TRANSITION_MATRIX_V1_2026-08-10"
TEST_ID = "EC5-OTP-TRANSITION-MATRIX-V1"
DEVICE_API_VERSION = "MF1750_EC5_OTP_TRANSITION_MATRIX_DEVICE_V1"
IDENTITY_REVISION = "otp-transition-matrix-v1"
LAYOUT_ID = "dual-controller-mirrored-8x8-old-to-new-v1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
EXECUTION_ELIGIBLE = False
NVS_NAMESPACE = "mf1750_otpm8"
NVS_KEY = "cursor_v1"

ROLE_PRIMER = "OTP_8X8_TRANSITION_PRIMER"
ROLE_TARGET = "OTP_8X8_TRANSITION_TARGET"
ROLE_WHITE = "OTP_WHITE_RECOVERY"
ROLES = (ROLE_PRIMER, ROLE_TARGET, ROLE_WHITE)

# Compatibility names used only when the audited COLOR_LAB transport engine is
# process-locally rebound by the dedicated physical adapter.  They do not
# change the role strings carried by this campaign.
ROLE_U04_PRIMER = ROLE_PRIMER
ROLE_U04_TARGET = ROLE_TARGET
ROLE_U07_PRIMER = "UNUSED_OTP_MATRIX_U07_PRIMER"
ROLE_U07_TARGET = "UNUSED_OTP_MATRIX_U07_TARGET"
ROLE_U07_ISOLATED = "UNUSED_OTP_MATRIX_U07_ISOLATED"
ROLE_ATLAS = "UNUSED_OTP_MATRIX_ATLAS"


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _payload_identity(payload: bytes) -> dict[str, Any]:
    fnv = matrix.fnv1a(payload)
    return {
        "bytes": len(payload),
        "sha256": sha256(payload),
        "fnv1a_u32": fnv,
        "fnv1a_hex": f"0x{fnv:08x}",
    }


def role_frame(role: str) -> bytes:
    if role == ROLE_PRIMER:
        return matrix.build_frame("primer")
    if role == ROLE_TARGET:
        return matrix.build_frame("target")
    if role == ROLE_WHITE:
        return b"\x11" * matrix.FRAME_BYTES
    raise ValueError(f"unknown OTP transition-matrix role {role}")


def generated_role_identity(role: str) -> dict[str, Any]:
    frame = role_frame(role)
    return {
        "role": role,
        "frame": _payload_identity(frame),
        "cs1_dtm": _payload_identity(matrix.controller_stream(frame, 0)),
        "cs2_dtm": _payload_identity(matrix.controller_stream(frame, 1)),
    }


ROLE_IDENTITIES: Mapping[str, Mapping[str, Any]] = {
    role: generated_role_identity(role) for role in ROLES
}

FROZEN_ROLE_SHA256: Mapping[str, tuple[str, str, str]] = {
    ROLE_PRIMER: (
        "01529ea97197e5435370a0eb77a9cabff167c129237952b7a627a0f4903744dc",
        "208c3d8e03329bbba08bb54cb5f84a9568349295ed750c749aad0e29f259017f",
        "d66c999e89ace23dd3a112c53e9ca1f7bbbc984772e08af4359dcd843740cb1c",
    ),
    ROLE_TARGET: (
        "e3f476f24176e4b5d0f196e6c3d912dabf5044f2cbac0a59bf63806d8d051a38",
        "4a980b33107b1d0c1da6282952d5adf8c32334af46be8f2e82aceb4c30a94387",
        "70d4f642ec98bb034de65fb350d51285e7f644dd42c5aa3e89de5b607f4643c3",
    ),
    ROLE_WHITE: (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    ),
}


def _required_gates(ordinal: int) -> list[str]:
    if ordinal == 1:
        return [
            "exact_ordinal11_clean_white_result_observation_and_claim",
            "same_boot_j2_off_diagnostic_after_new_firmware_flash",
            "operator_electrical_temperature_and_physical_cutoff_ready",
            "explicit_single_action_authorization",
        ]
    gates = [
        "exact_previous_matrix_result_and_manual_observation",
        "same_boot_nonce",
        "no_intervening_visible_refresh",
        "explicit_single_action_authorization",
    ]
    if ordinal == 3:
        gates.append("operator_accepts_factory_otp_white_recovery_action")
    return gates


def _sequence_rows() -> tuple[tuple[str, str], ...]:
    return (
        (ROLE_PRIMER, "FACTORY_OTP_8X8_OLD_STATE_PRIMER"),
        (ROLE_TARGET, "FACTORY_OTP_8X8_OLD_TO_NEW_TARGET"),
        (ROLE_WHITE, "FACTORY_OTP_WHITE_RECOVERY"),
    )


def action_descriptors() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, (role, branch) in enumerate(_sequence_rows(), start=1):
        identity = ROLE_IDENTITIES[role]
        prior = result[-1] if result else None
        descriptor_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-otp-transition-matrix-action-descriptor",
            "campaign_id": CAMPAIGN_ID,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "device_api_version": DEVICE_API_VERSION,
            "identity_revision": IDENTITY_REVISION,
            "ordinal": ordinal,
            "role": role,
            "round": 1,
            "branch": branch,
            "expected_prior_ordinal": None if prior is None else prior["ordinal"],
            "expected_prior_role": None if prior is None else prior["role"],
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "required_host_gates": _required_gates(ordinal),
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": role == ROLE_WHITE,
            "automatic_chaining": False,
        }
        descriptor_id = sha256(canonical_json_bytes(descriptor_preimage))
        action_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-otp-transition-matrix-visible-action-identity",
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
            "round": 1,
            "branch": branch,
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "prior_static_action_id": prior_action_id,
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": role == ROLE_WHITE,
            "automatic_chaining": False,
            "visible_action_semantics": (
                "one_explicitly_armed_fixed_compiled_factory_otp_frame_refresh"
            ),
        }
        action_id = sha256(canonical_json_bytes(action_preimage))
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
        "profile_source": matrix.PROFILE_SOURCE,
        "custom_lut_or_waveform": matrix.CUSTOM_LUT_OR_WAVEFORM,
        "nvs_contract": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
            "initial_key_present": False,
            "initial_value": 1,
        },
        "descriptors": deepcopy(list(DESCRIPTORS)),
        "roles": deepcopy(dict(ROLE_IDENTITIES)),
        "transition_layout": {
            "controller_count": 2,
            "pairs_per_controller": 64,
            "roi_count": 128,
            "old_axis": "row",
            "new_axis": "column",
            "cs2_axes_reversed": True,
        },
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": False,
        "electrical_parameter_write": False,
        "dithering_present": False,
        "spatial_mixing_present": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "normal_step_requires_reflash_reset_or_j2_cycle": False,
        "hardware_gate": (
            "blocked_until_exact_firmware_release_same_boot_preflight_and_"
            "per_action_manual_authorization_are_materialized"
        ),
    }
    root["contract_id"] = sha256(canonical_json_bytes(root))
    return root


def validate_contract() -> None:
    if len(DESCRIPTORS) != 3:
        raise RuntimeError("OTP transition-matrix descriptor count drifted")
    for role, expected in FROZEN_ROLE_SHA256.items():
        generated = ROLE_IDENTITIES[role]
        actual = (
            generated["frame"]["sha256"],
            generated["cs1_dtm"]["sha256"],
            generated["cs2_dtm"]["sha256"],
        )
        if actual != expected:
            raise RuntimeError(f"{role} compiled identity drifted")
    action_ids = [item["hardware_action_id"] for item in DESCRIPTORS]
    descriptor_ids = [item["descriptor_id"] for item in DESCRIPTORS]
    if len(set(action_ids)) != 3 or len(set(descriptor_ids)) != 3:
        raise RuntimeError("OTP transition-matrix identities are not unique")
    for index, descriptor in enumerate(DESCRIPTORS):
        expected_prior = None if index == 0 else action_ids[index - 1]
        if (
            descriptor["action_identity_preimage"]["prior_static_action_id"]
            != expected_prior
        ):
            raise RuntimeError("OTP transition-matrix static prior chain drifted")
    if campaign_manifest()["custom_lut_or_waveform"] is not False:
        raise RuntimeError("factory-OTP campaign was mislabeled as a custom waveform")


validate_contract()

