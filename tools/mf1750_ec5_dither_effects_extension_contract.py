#!/usr/bin/env python3
"""Frozen offline contract for the EC5 factory-OTP dither-effects extension.

This module contains no device, serial, network, upload, or visible-refresh
path.  It binds four fixed compiled actions: pair gradients, white recovery,
an effects chart, and final white recovery.  Perceived mixed colours are only
spatial mixtures of already accepted factory-OTP pixel codes.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from host import dither_effects_suite as suite


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-dither-effects-extension-offline-campaign-contract"
CLASSIFICATION = "FACTORY_OTP_SPATIAL_DITHER_EFFECTS_NO_RUNTIME_LUT"
CAMPAIGN_ID = "EC5_DITHER_EFFECTS_EXTENSION_CAMPAIGN_V1"
BUILD_TAG = "MF1750_EC5_DITHER_EFFECTS_EXTENSION_V1_2026-08-17"
TEST_ID = "EC5-DITHER-EFFECTS-EXTENSION-V1"
DEVICE_API_VERSION = "MF1750_EC5_DITHER_EFFECTS_EXTENSION_DEVICE_V1"
IDENTITY_REVISION = "dither-effects-extension-v1"
LAYOUT_ID = "dual-controller-identical-ordered-gradient-effects-v1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
EXECUTION_ELIGIBLE = False
NVS_NAMESPACE = "mf1750_dee"
NVS_KEY = "cursor_v1"

ROLE_PAIR_GRADIENTS = "OTP_DITHER_PAIR_GRADIENTS"
ROLE_WHITE_AFTER_GRADIENTS = "OTP_WHITE_AFTER_GRADIENTS"
ROLE_EFFECTS_CHART = "OTP_DITHER_EFFECTS_CHART"
ROLE_WHITE_AFTER_EFFECTS = "OTP_WHITE_AFTER_EFFECTS"
ROLES = (
    ROLE_PAIR_GRADIENTS,
    ROLE_WHITE_AFTER_GRADIENTS,
    ROLE_EFFECTS_CHART,
    ROLE_WHITE_AFTER_EFFECTS,
)
FRAME_ROLE_BY_ACTION_ROLE = {
    ROLE_PAIR_GRADIENTS: suite.ROLE_PAIR_GRADIENTS,
    ROLE_WHITE_AFTER_GRADIENTS: suite.ROLE_WHITE,
    ROLE_EFFECTS_CHART: suite.ROLE_EFFECTS_CHART,
    ROLE_WHITE_AFTER_EFFECTS: suite.ROLE_WHITE,
}
BRANCH_BY_ROLE = {
    ROLE_PAIR_GRADIENTS: "FACTORY_OTP_SPATIAL_DITHER_PAIR_GRADIENTS",
    ROLE_WHITE_AFTER_GRADIENTS: "FACTORY_OTP_WHITE_RECOVERY_AFTER_PAIR_GRADIENTS",
    ROLE_EFFECTS_CHART: "FACTORY_OTP_SPATIAL_DITHER_EFFECTS_CHART",
    ROLE_WHITE_AFTER_EFFECTS: "FACTORY_OTP_WHITE_RECOVERY_AFTER_EFFECTS_CHART",
}

PREDECESSOR_CAMPAIGN_ID = "EC5_DITHER_COLOR_ATLAS_CAMPAIGN_V1"
PREDECESSOR_ORDINAL = 2
PREDECESSOR_ROLE = "OTP_WHITE_RECOVERY"
PREDECESSOR_ACTION_ID = (
    "35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3"
)


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256(payload: bytes | Mapping[str, Any]) -> str:
    value = canonical_json_bytes(payload) if isinstance(payload, Mapping) else payload
    return hashlib.sha256(value).hexdigest()


def role_frame_identity(role: str) -> dict[str, Any]:
    try:
        frame_role = FRAME_ROLE_BY_ACTION_ROLE[role]
    except KeyError as error:
        raise ValueError(f"unknown dither-effects role {role!r}") from error
    return suite.frame_identity(frame_role).to_dict()


def role_frame(role: str) -> bytes:
    """Return the canonical frame for one visible action role."""

    try:
        frame_role = FRAME_ROLE_BY_ACTION_ROLE[role]
    except KeyError as error:
        raise ValueError(f"unknown dither-effects role {role!r}") from error
    return suite.build_frame(frame_role)


ROLE_IDENTITIES: Mapping[str, Mapping[str, Any]] = {
    role: role_frame_identity(role) for role in ROLES
}


def _required_gates(ordinal: int) -> list[str]:
    if ordinal == 1:
        return [
            "exact_dither_atlas_ordinal_2_clean_white_result_observation_and_claim",
            "same_boot_j2_off_diagnostic_after_new_firmware_flash",
            "operator_electrical_temperature_and_physical_cutoff_ready",
            "reviewed_exact_pair_gradient_preview_and_operator_card",
            "explicit_single_action_authorization",
        ]
    previous = ROLES[ordinal - 2]
    gates = [
        f"exact_previous_{previous.lower()}_result_and_manual_observation",
        "same_boot_nonce",
        "no_intervening_visible_refresh",
        "operator_electrical_temperature_and_physical_cutoff_ready",
        "explicit_single_action_authorization",
    ]
    if ordinal == 3:
        gates.append("previous_factory_otp_white_recovery_is_clean")
    return gates


def action_descriptors() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, role in enumerate(ROLES, start=1):
        identity = ROLE_IDENTITIES[role]
        prior = result[-1] if result else None
        recovery = FRAME_ROLE_BY_ACTION_ROLE[role] == suite.ROLE_WHITE
        descriptor_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-dither-effects-extension-action-descriptor",
            "campaign_id": CAMPAIGN_ID,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "device_api_version": DEVICE_API_VERSION,
            "identity_revision": IDENTITY_REVISION,
            "ordinal": ordinal,
            "role": role,
            "round": 1,
            "branch": BRANCH_BY_ROLE[role],
            "expected_prior_ordinal": None if prior is None else prior["ordinal"],
            "expected_prior_role": None if prior is None else prior["role"],
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "required_host_gates": _required_gates(ordinal),
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": recovery,
            "automatic_chaining": False,
        }
        descriptor_id = sha256(descriptor_preimage)
        action_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-dither-effects-extension-visible-action-identity",
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
            "branch": BRANCH_BY_ROLE[role],
            "frame_sha256": identity["frame"]["sha256"],
            "cs1_dtm_sha256": identity["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": identity["cs2_dtm"]["sha256"],
            "prior_static_action_id": prior_action_id,
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "retry_allowed": False,
            "recovery_included": recovery,
            "automatic_chaining": False,
            "visible_action_semantics": (
                "one_explicitly_armed_fixed_compiled_factory_otp_frame_refresh"
            ),
        }
        action_id = sha256(action_preimage)
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
    layout = suite.layout_manifest()
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "campaign_id": CAMPAIGN_ID,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "layout_id": LAYOUT_ID,
        "layout_canonical_sha256": layout["integrity"]["canonical_sha256"],
        "top_schema_version": TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "execution_eligible": EXECUTION_ELIGIBLE,
        "profile_source": suite.PROFILE_SOURCE,
        "custom_lut_or_waveform": suite.CUSTOM_LUT_OR_WAVEFORM,
        "nvs_contract": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
            "initial_key_present": False,
            "initial_value": 1,
        },
        "external_clean_white_anchor": {
            "campaign_id": PREDECESSOR_CAMPAIGN_ID,
            "ordinal": PREDECESSOR_ORDINAL,
            "role": PREDECESSOR_ROLE,
            "action_id": PREDECESSOR_ACTION_ID,
            "evidence_bound_at_release_materialization": True,
            "validated_by_device": False,
            "required_host_gate_for_ordinal_1": True,
        },
        "descriptors": deepcopy(list(DESCRIPTORS)),
        "roles": deepcopy(dict(ROLE_IDENTITIES)),
        "dither_layout": {
            "ordered_mask": deepcopy(dict(layout["ordered_mask"])),
            "pair_gradients": deepcopy(dict(layout["pair_gradients"])),
            "effects_chart": deepcopy(dict(layout["effects_chart"])),
            "controller_halves_are_semantically_identical": True,
            "controller_pattern_phase_is_identical": True,
        },
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": False,
        "electrical_parameter_write": False,
        "dithering_present": True,
        "spatial_mixing_present": True,
        "single_pixel_multi_pigment_claim": False,
        "physical_colour_claim": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "normal_step_requires_reflash_reset_or_j2_cycle": False,
        "hardware_gate": (
            "blocked_until_exact_firmware_release_predecessor_evidence_same_boot_"
            "preflight_and_per_action_manual_authorization_are_materialized"
        ),
    }
    root["contract_id"] = sha256(root)
    return root


def validate_contract() -> None:
    if len(DESCRIPTORS) != 4:
        raise RuntimeError("dither-effects descriptor count drifted")
    action_ids = [item["hardware_action_id"] for item in DESCRIPTORS]
    descriptor_ids = [item["descriptor_id"] for item in DESCRIPTORS]
    if len(set(action_ids)) != 4 or len(set(descriptor_ids)) != 4:
        raise RuntimeError("dither-effects identities are not unique")
    for index, descriptor in enumerate(DESCRIPTORS):
        expected_prior = None if index == 0 else action_ids[index - 1]
        if (
            descriptor["action_identity_preimage"]["prior_static_action_id"]
            != expected_prior
        ):
            raise RuntimeError("dither-effects static prior chain drifted")
        frame_role = FRAME_ROLE_BY_ACTION_ROLE[str(descriptor["role"])]
        expected = suite.FROZEN_ROLE_SHA256[frame_role]
        actual = tuple(
            str(descriptor[field])
            for field in ("frame_sha256", "cs1_dtm_sha256", "cs2_dtm_sha256")
        )
        if actual != expected:
            raise RuntimeError("dither-effects frame identity drifted")
    manifest = campaign_manifest()
    if manifest["custom_lut_or_waveform"] is not False:
        raise RuntimeError("factory-OTP effects were mislabeled as waveform")
    if manifest["single_pixel_multi_pigment_claim"] is not False:
        raise RuntimeError("spatial effects were mislabeled as per-pixel mixture")
    if manifest["execution_eligible"] is not False:
        raise RuntimeError("offline contract became execution eligible")


validate_contract()
