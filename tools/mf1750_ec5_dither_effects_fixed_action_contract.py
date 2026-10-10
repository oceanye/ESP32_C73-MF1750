#!/usr/bin/env python3
"""Historical P0 non-live RC2G transport-candidate contract.

The contract binds exact frame bytes and a previously hardware-proven RC2G
firmware binary as a *transport candidate*.  It intentionally contains no
socket, serial, flash, claim, or execution entry point.  A dedicated adapter
and materialized release must still be independently reviewed before any live
action can be authorized.  The fixed-compiled V2 path now supersedes this P0;
this module remains unchanged at the data level only so its sealed V1 readiness
artifact can still be replayed as historical evidence.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from host import dither_effects_suite as suite


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-dither-effects-extension-fixed-action-contract"
CLASSIFICATION = "FACTORY_OTP_SPATIAL_DITHER_EFFECTS_NO_RUNTIME_LUT"
CAMPAIGN_ID = "EC5_DITHER_EFFECTS_EXTENSION_CAMPAIGN_V1"
BUILD_TAG = "MF1750_EC5_DITHER_EFFECTS_EXTENSION_V1_2026-08-17"
TRANSPORT_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
TRANSPORT_DRIVER_API = "MF1750_R16_CASCADE_V3"
TRANSPORT_FIRMWARE_BYTES = 815_664
TRANSPORT_FIRMWARE_SHA256 = (
    "9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772"
)
SOURCE_BUNDLE_MANIFEST_FILE_SHA256 = (
    "30c5b81c9f9f806e9c7fc9e69b4f925be147ccde61cc163b16f373066234a983"
)
SOURCE_BUNDLE_MANIFEST_CANONICAL_SHA256 = (
    "78c5397d1cb596cfb864875bdf0884f3fee5e118415df3d7655301e17b070e94"
)

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


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def _required_gates(ordinal: int) -> list[str]:
    if ordinal == 1:
        return [
            "exact_existing_dither_block_white_result_observation_claim_or_equivalent_clean_white_anchor",
            "j2_off_app_only_flash_and_writeback_hash_of_bound_transport_firmware",
            "fresh_boot_j2_off_read_only_rc2g_diagnostic",
            "operator_electrical_temperature_and_physical_cutoff_ready",
            "reviewed_exact_pair_gradient_preview",
            "explicit_single_action_authorization",
        ]
    previous_role = ROLES[ordinal - 2]
    gates = [
        f"exact_previous_{previous_role.lower()}_result_observation_and_claim",
        "no_intervening_visible_refresh",
        "j2_off_app_only_flash_and_writeback_hash_of_bound_transport_firmware",
        "fresh_boot_j2_off_read_only_rc2g_diagnostic",
        "operator_electrical_temperature_and_physical_cutoff_ready",
        "explicit_single_action_authorization",
    ]
    if ordinal in (3,):
        gates.append("previous_factory_otp_white_recovery_is_clean")
    return gates


def action_descriptors() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    prior_action_id: str | None = None
    for ordinal, role in enumerate(ROLES, start=1):
        frame_role = FRAME_ROLE_BY_ACTION_ROLE[role]
        identity = suite.frame_identity(frame_role)
        recovery = frame_role == suite.ROLE_WHITE
        descriptor_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-dither-effects-action-descriptor",
            "campaign_id": CAMPAIGN_ID,
            "build_tag": BUILD_TAG,
            "ordinal": ordinal,
            "role": role,
            "frame_role": frame_role,
            "prior_static_action_id": prior_action_id,
            "frame": identity.frame.to_dict(),
            "cs1_dtm": identity.cs1_dtm.to_dict(),
            "cs2_dtm": identity.cs2_dtm.to_dict(),
            "histogram_codes_0_to_7": list(identity.histogram),
            "required_host_gates": _required_gates(ordinal),
            "request": {
                "method": "POST",
                "endpoint": "/api/frame",
                "body": "exact-contract-bound-canonical-frame-bytes",
                "maximum_posts": 1,
            },
            "fresh_app_boot_required": True,
            "recovery_action": recovery,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        }
        descriptor_id = sha256(descriptor_preimage)
        action_preimage = {
            "schema_version": 1,
            "kind": "mf1750-ec5-dither-effects-visible-action-identity",
            "campaign_id": CAMPAIGN_ID,
            "ordinal": ordinal,
            "role": role,
            "descriptor_id": descriptor_id,
            "prior_static_action_id": prior_action_id,
            "frame_sha256": identity.frame.sha256,
            "cs1_dtm_sha256": identity.cs1_dtm.sha256,
            "cs2_dtm_sha256": identity.cs2_dtm.sha256,
            "transport_firmware_sha256": TRANSPORT_FIRMWARE_SHA256,
            "request_method": "POST",
            "request_endpoint": "/api/frame",
            "maximum_posts": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        }
        action_id = sha256(action_preimage)
        result.append(
            {
                **descriptor_preimage,
                "descriptor_id": descriptor_id,
                "hardware_action_id": action_id,
                "action_identity_preimage": action_preimage,
                "execution_eligible": False,
                "live_authorized": False,
            }
        )
        prior_action_id = action_id
    return result


DESCRIPTORS = tuple(action_descriptors())


def contract_manifest() -> dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "campaign_id": CAMPAIGN_ID,
        "build_tag": BUILD_TAG,
        "profile_source": "factory_otp",
        "spatial_mixing_only": True,
        "runtime_lut_or_waveform_write": False,
        "single_pixel_multi_pigment_claim": False,
        "source_bundle": {
            "manifest_file_sha256": SOURCE_BUNDLE_MANIFEST_FILE_SHA256,
            "manifest_canonical_sha256": (SOURCE_BUNDLE_MANIFEST_CANONICAL_SHA256),
            "layout_canonical_sha256": suite.layout_manifest()["integrity"][
                "canonical_sha256"
            ],
        },
        "transport_candidate": {
            "build_tag": TRANSPORT_BUILD_TAG,
            "driver_api": TRANSPORT_DRIVER_API,
            "firmware_bytes": TRANSPORT_FIRMWARE_BYTES,
            "firmware_sha256": TRANSPORT_FIRMWARE_SHA256,
            "historically_hardware_proven": True,
            "dedicated_extension_adapter_materialized": False,
            "extension_release_materialized": False,
            "transport_candidate_is_live_authorization": False,
        },
        "descriptors": deepcopy(list(DESCRIPTORS)),
        "action_count": len(DESCRIPTORS),
        "target_count": 2,
        "white_recovery_count": 2,
        "first_safe_stop_ordinal": 2,
        "safe_stop_ordinals": [2, 4],
        "execution_eligible": False,
        "live_authorized": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "hardware_gate": (
            "blocked_until_dedicated_fixed_frame_adapter_compiled_release_"
            "fresh_diagnostic_and_per_action_exact_authorization"
        ),
    }
    root = deepcopy(unsigned)
    root["contract_id"] = sha256(unsigned)
    return root


def validate_contract() -> None:
    if len(DESCRIPTORS) != 4:
        raise RuntimeError("dither effects descriptor count drifted")
    action_ids = [item["hardware_action_id"] for item in DESCRIPTORS]
    descriptor_ids = [item["descriptor_id"] for item in DESCRIPTORS]
    if len(set(action_ids)) != 4 or len(set(descriptor_ids)) != 4:
        raise RuntimeError("dither effects action identities are not unique")
    for index, descriptor in enumerate(DESCRIPTORS):
        expected_prior = None if index == 0 else action_ids[index - 1]
        if descriptor["prior_static_action_id"] != expected_prior:
            raise RuntimeError("dither effects prior chain drifted")
        if descriptor["execution_eligible"] or descriptor["live_authorized"]:
            raise RuntimeError("offline dither effects action became live")
        if descriptor["request"] != {
            "method": "POST",
            "endpoint": "/api/frame",
            "body": "exact-contract-bound-canonical-frame-bytes",
            "maximum_posts": 1,
        }:
            raise RuntimeError("dither effects request surface drifted")
    manifest = contract_manifest()
    if manifest["execution_eligible"] or manifest["live_authorized"]:
        raise RuntimeError("dither effects contract became executable")
    if manifest["runtime_lut_or_waveform_write"]:
        raise RuntimeError("dither effects contract was mislabeled as waveform")


validate_contract()
