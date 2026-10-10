#!/usr/bin/env python3
"""Frozen offline contract for the EC5 factory-OTP dither colour atlas."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from host import dither_color_atlas as atlas


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-dither-color-atlas-offline-campaign-contract"
CLASSIFICATION = "FACTORY_OTP_SPATIAL_DITHER_ATLAS_EXPERIMENT_NO_RUNTIME_LUT"
CAMPAIGN_ID = "EC5_DITHER_COLOR_ATLAS_CAMPAIGN_V1"
BUILD_TAG = "MF1750_EC5_DITHER_COLOR_ATLAS_V1_2026-08-10"
TEST_ID = "EC5-DITHER-COLOR-ATLAS-V1"
DEVICE_API_VERSION = "MF1750_EC5_DITHER_COLOR_ATLAS_DEVICE_V1"
IDENTITY_REVISION = "dither-color-atlas-v1"
LAYOUT_ID = "dual-controller-identical-7x5-two-colour-quarter-step-v1"
TOP_SCHEMA_VERSION = 3
DRIVER_EVIDENCE_SCHEMA_VERSION = 2
EXECUTION_ELIGIBLE = False
NVS_NAMESPACE = "mf1750_dca"
NVS_KEY = "cursor_v1"

ROLE_ATLAS = "OTP_DITHER_COLOR_ATLAS"
ROLE_WHITE = "OTP_WHITE_RECOVERY"
ROLES = (ROLE_ATLAS, ROLE_WHITE)

# Compatibility aliases used only by the audited COLOR_LAB transport engine
# while process-locally rebound by the dedicated physical adapter.
ROLE_U04_PRIMER = ROLE_ATLAS
ROLE_U04_TARGET = "UNUSED_DITHER_ATLAS_U04_TARGET"
ROLE_U07_PRIMER = "UNUSED_DITHER_ATLAS_U07_PRIMER"
ROLE_U07_TARGET = "UNUSED_DITHER_ATLAS_U07_TARGET"
ROLE_U07_ISOLATED = "UNUSED_DITHER_ATLAS_U07_ISOLATED"


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
    fnv = atlas.fnv1a(payload)
    return {
        "bytes": len(payload),
        "sha256": sha256(payload),
        "fnv1a_u32": fnv,
        "fnv1a_hex": f"0x{fnv:08x}",
    }


def role_frame(role: str) -> bytes:
    if role == ROLE_ATLAS:
        return atlas.build_frame("atlas")
    if role == ROLE_WHITE:
        return atlas.build_frame("white")
    raise ValueError(f"unknown dither colour-atlas role {role}")


def generated_role_identity(role: str) -> dict[str, Any]:
    frame = role_frame(role)
    return {
        "role": role,
        "frame": _payload_identity(frame),
        "cs1_dtm": _payload_identity(atlas.controller_stream(frame, 0)),
        "cs2_dtm": _payload_identity(atlas.controller_stream(frame, 1)),
    }


ROLE_IDENTITIES: Mapping[str, Mapping[str, Any]] = {
    role: generated_role_identity(role) for role in ROLES
}

FROZEN_ROLE_SHA256: Mapping[str, tuple[str, str, str]] = {
    ROLE_ATLAS: (
        "3b65803a558e91ad2112a75b158a1b696666c015829ce9fd0bce401ba96a44b7",
        "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
        "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
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
            "exact_otp_matrix_final_clean_white_result_observation_and_claim",
            "same_boot_j2_off_diagnostic_after_new_firmware_flash",
            "operator_electrical_temperature_and_physical_cutoff_ready",
            "reviewed_strict_preview_and_operator_card",
            "explicit_single_action_authorization",
        ]
    return [
        "exact_previous_dither_atlas_result_and_manual_observation",
        "same_boot_nonce",
        "no_intervening_visible_refresh",
        "operator_accepts_factory_otp_white_recovery_action",
        "explicit_single_action_authorization",
    ]


def _sequence_rows() -> tuple[tuple[str, str], ...]:
    return (
        (ROLE_ATLAS, "FACTORY_OTP_SPATIAL_DITHER_COLOR_ATLAS"),
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
            "kind": "mf1750-ec5-dither-color-atlas-action-descriptor",
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
            "kind": "mf1750-ec5-dither-color-atlas-visible-action-identity",
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
    layout = atlas.layout_manifest()
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
        "profile_source": atlas.PROFILE_SOURCE,
        "custom_lut_or_waveform": atlas.CUSTOM_LUT_OR_WAVEFORM,
        "nvs_contract": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
            "initial_key_present": False,
            "initial_value": 1,
        },
        "descriptors": deepcopy(list(DESCRIPTORS)),
        "roles": deepcopy(dict(ROLE_IDENTITIES)),
        "dither_layout": {
            "controller_count": 2,
            "rows": atlas.GRID_ROWS,
            "columns": atlas.GRID_COLUMNS,
            "rois_per_controller": atlas.GRID_ROWS * atlas.GRID_COLUMNS,
            "roi_count": len(atlas.atlas_rois()),
            "controller_halves_semantically_identical": True,
            "controller_pattern_phase_identical": True,
            "mask": "bayer-2x2-quarter-area",
            "middle_column": "one-pixel-50-50-checkerboard",
            "appearance_names_are_hypotheses": True,
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
            "blocked_until_exact_firmware_release_same_boot_preflight_and_"
            "per_action_manual_authorization_are_materialized"
        ),
    }
    root["contract_id"] = sha256(canonical_json_bytes(root))
    return root


def validate_contract() -> None:
    if len(DESCRIPTORS) != 2:
        raise RuntimeError("dither colour-atlas descriptor count drifted")
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
    if len(set(action_ids)) != 2 or len(set(descriptor_ids)) != 2:
        raise RuntimeError("dither colour-atlas identities are not unique")
    for index, descriptor in enumerate(DESCRIPTORS):
        expected_prior = None if index == 0 else action_ids[index - 1]
        if (
            descriptor["action_identity_preimage"]["prior_static_action_id"]
            != expected_prior
        ):
            raise RuntimeError("dither colour-atlas static prior chain drifted")
    manifest = campaign_manifest()
    if manifest["custom_lut_or_waveform"] is not False:
        raise RuntimeError("factory-OTP atlas was mislabeled as a custom waveform")
    if manifest["single_pixel_multi_pigment_claim"] is not False:
        raise RuntimeError("spatial atlas was mislabeled as a per-pixel mixture")


validate_contract()
