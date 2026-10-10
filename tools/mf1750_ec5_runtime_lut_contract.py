#!/usr/bin/env python3
"""Frozen host-only contract for two empirical SPD1657 H3 campaigns.

The module describes, but cannot authorize, a visible refresh.  Each selected
vendor profile has its own two-image campaign: a one-action runtime-H3 atlas
image followed by a different one-action factory-OTP white image.  Firmware
hashes are intentionally absent here and may only be added by the release
materializer after exact BIN/ELF validation.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Final, Mapping

from tools import mf1750_ec5_eightcode_atlas as atlas


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-empirical-h3-profile-contract"
CLASSIFICATION: Final = "EMPIRICAL_H3_REAL_PANEL_CAMPAIGN_NOT_LIVE_AUTHORIZATION"
DEVICE_API_VERSION: Final = "MF1750_EC5_EMPIRICAL_H3_DEVICE_V1"
PROFILES: Final = ("WF20_25", "WF23_25")
ROLE_RUNTIME: Final = "EMPIRICAL_H3_EIGHT_CODE_ATLAS"
ROLE_WHITE: Final = "FACTORY_OTP_WHITE_RECOVERY"
ROLES: Final = (ROLE_RUNTIME, ROLE_WHITE)
PRIOR_STATE_ID: Final = "J2_OFF_CLEAN_WHITE_2026_08_11"
OPERATOR_MONITORING_CONFIRMATION: Final = (
    "CURRENT_LIMIT_CURRENT_MONITOR_TEMPERATURE_MONITOR_PHYSICAL_CUTOFF_READY"
)
RECOVERY_TEMPERATURE_RECORD_RANGE_C: Final = (0.0, 37.0)
EMPIRICAL_ACCEPTANCE_PHRASE: Final = (
    "ACCEPT_U1_U7_EMPIRICAL_CROSS_VERSION_RISK__NO_PANEL_FPL_PROOF"
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]

_PROFILE_ROWS: Final[Mapping[str, Mapping[str, Any]]] = {
    "WF20_25": {
        "vendor_filename_numeric_tokens": [20, 25],
        "experimental_fixed_temperature_guard_c": [25.0, 25.0],
        "temperature_filename_semantics_proven": False,
        "temperature_compatibility_qualified": False,
        "temperature_guard_basis": (
            "adjacent_2020_E2801_E2802_fixed_selector_25_not_vendor_band"
        ),
        "generated_include": "src/generated/spd1657_wf20_25_empirical_h3.inc",
        "generated_include_sha256": (
            "8009f2c5523bd4c592474cc15e6b0b4a8b0a74053a09e69d4926d9f5abffb626"
        ),
        "r20_sha256": (
            "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26"
        ),
        "r21_sha256": (
            "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
        ),
        "runtime_environment": "ec5_runtime_lut_wf20_25",
        "recovery_environment": "ec5_otp_white_wf20_25",
        "runtime_nvs_namespace": "rlt_w20_v1",
        "recovery_nvs_namespace": "otpw_w20_v1",
        "requested_electrical_metadata": {
            "gate_positive_mv": 20000,
            "gate_negative_mv": -20000,
            "full_source_positive_mv": 15000,
            "full_source_negative_mv": -15000,
            "intermediate_source_mv": {
                "vsh_lv": 6500,
                "vsl_lv": -8200,
                "vsh_lv2": 8000,
                "vsl_lv2": -8800,
            },
            "frame_rate_hz": 43,
            "vcom_written_or_swept": False,
            "panel_fpl_or_film_lot_qualified": False,
        },
    },
    "WF23_25": {
        "vendor_filename_numeric_tokens": [23, 25],
        "experimental_fixed_temperature_guard_c": [25.0, 25.0],
        "temperature_filename_semantics_proven": False,
        "temperature_compatibility_qualified": False,
        "temperature_guard_basis": (
            "adjacent_2020_E2801_E2802_fixed_selector_25_not_vendor_band"
        ),
        "generated_include": "src/generated/spd1657_wf23_25_empirical_h3.inc",
        "generated_include_sha256": (
            "ee289bc89e9f76f936ca5f2dd0c503f8cc8c8d786c01fc26615c33b9251cb9ff"
        ),
        "r20_sha256": (
            "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb"
        ),
        "r21_sha256": (
            "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
        ),
        "runtime_environment": "ec5_runtime_lut_wf23_25",
        "recovery_environment": "ec5_otp_white_wf23_25",
        "runtime_nvs_namespace": "rlt_w23_v1",
        "recovery_nvs_namespace": "otpw_w23_v1",
        "requested_electrical_metadata": {
            "gate_positive_mv": 20000,
            "gate_negative_mv": -20000,
            "full_source_positive_mv": 15000,
            "full_source_negative_mv": -15000,
            "intermediate_source_mv": {
                "vsh_lv": 7200,
                "vsl_lv": -8400,
                "vsh_lv2": 8200,
                "vsl_lv2": -9800,
            },
            "frame_rate_hz": 43,
            "vcom_written_or_swept": False,
            "panel_fpl_or_film_lot_qualified": False,
        },
    },
}

_DEVICE_ROLE_ROWS: Final[Mapping[str, Mapping[str, str]]] = {
    ROLE_RUNTIME: {
        "kind_prefix": "mf1750-ec5-runtime-lut-empirical-h3",
        "test_id": "EC5-RUNTIME-LUT-EMPIRICAL-H3-V1",
        "base_route": "/api/ec5/runtime-lut-h3",
        "arm_intent": ("ARM_ONE_FIXED_EMPIRICAL_H3_ATLAS_NOT_HARDWARE_AUTHORIZATION"),
        "execute_intent": "EXECUTE_ONE_FIXED_EMPIRICAL_H3_ATLAS_ONCE",
    },
    ROLE_WHITE: {
        "kind_prefix": "mf1750-ec5-factory-otp-white-recovery",
        "test_id": "EC5-FACTORY-OTP-WHITE-RECOVERY-V1",
        "base_route": "/api/ec5/factory-otp-white",
        "arm_intent": ("ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"),
        "execute_intent": "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE",
    },
}

# These are the exact unresolved assumptions accepted by the build operator
# and again bound into each per-action authorization token.  They are risks,
# not statements that the sequence is proven safe or correct.
U1_U7: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "id": "U1",
        "statement": (
            "5F69->5FE9 bit-level derivation and the PSR insertion point are unproven"
        ),
    },
    {
        "id": "U2",
        "statement": (
            "mode0 header-to-PWR/PLL transfer into the 800-byte mode1 candidate, "
            "including replacement and relative ordering, is unproven"
        ),
    },
    {
        "id": "U3",
        "statement": (
            "hidden E9=01 semantics, dual-controller application, and BUSY semantics "
            "are unproven"
        ),
    },
    {
        "id": "U4",
        "statement": (
            "H3 20/799 + 21/704FF has only cross-generation direct evidence from the "
            "2020 IAR build"
        ),
    },
    {
        "id": "U5",
        "statement": (
            "sequential CS1->CS2 upload with no readback and one BUSY signal cannot "
            "prove that the secondary controller accepted the payload"
        ),
    },
    {
        "id": "U6",
        "statement": (
            "vendor filename numeric-token semantics and panel/FPL/film-lot "
            "temperature compatibility are unproven; the exact 25.0 C guard is "
            "only an adjacent-legacy experimental condition, not a qualified "
            "vendor band; VCOM must not be written or swept"
        ),
    },
    {
        "id": "U7",
        "statement": (
            "post-POF cleanup and runtime-to-OTP recovery are extrapolations only"
        ),
    },
)


class RuntimeLutContractError(ValueError):
    """The selected profile or frozen contract differs."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RuntimeLutContractError(
            "value is not canonical-JSON encodable"
        ) from error


def sha256(value: bytes | Mapping[str, Any] | list[Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def profile_row(profile_id: str) -> dict[str, Any]:
    if profile_id not in _PROFILE_ROWS:
        raise RuntimeLutContractError(f"unsupported explicit profile {profile_id!r}")
    return deepcopy(dict(_PROFILE_ROWS[profile_id]))


def device_binding(profile_id: str, role: str) -> dict[str, str]:
    """Return exact HTTP/build identity without changing frozen action IDs."""

    profile_row(profile_id)
    if role not in _DEVICE_ROLE_ROWS:
        raise RuntimeLutContractError(f"unsupported device role {role!r}")
    short_profile = profile_id.upper()
    if role == ROLE_RUNTIME:
        build_tag = f"MF1750_EC5_RUNTIME_LUT_H3_{short_profile}_V1_2026-08-11"
    else:
        build_tag = f"MF1750_EC5_FACTORY_OTP_WHITE_{short_profile}_V1_2026-08-11"
    return {
        **dict(_DEVICE_ROLE_ROWS[role]),
        "build_tag": build_tag,
        "campaign_id": f"EC5_EMPIRICAL_H3_{profile_id}_V1",
    }


def assumption_acceptance() -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "kind": "mf1750-ec5-empirical-h3-u1-u7-acceptance",
        "acceptance_is_proof": False,
        "assumptions": deepcopy(list(U1_U7)),
        "required_exact_phrase": EMPIRICAL_ACCEPTANCE_PHRASE,
    }
    value["canonical_sha256"] = sha256(value)
    return value


def _payload_identity(role: str) -> dict[str, Any]:
    atlas_role = "atlas" if role == ROLE_RUNTIME else "white"
    frame = atlas.build_frame(atlas_role)
    return {
        "layout_id": atlas.LAYOUT_ID,
        "frame_bytes": len(frame),
        "frame_sha256": atlas.FROZEN_IDENTITIES[atlas_role]["frame"][0],
        "cs1_dtm_bytes": atlas.CONTROLLER_FRAME_BYTES,
        "cs1_dtm_sha256": atlas.FROZEN_IDENTITIES[atlas_role]["cs1"][0],
        "cs2_dtm_bytes": atlas.CONTROLLER_FRAME_BYTES,
        "cs2_dtm_sha256": atlas.FROZEN_IDENTITIES[atlas_role]["cs2"][0],
        "technical_codes_only": True,
        "physical_colour_claim": False,
    }


def transaction_descriptor(profile_id: str, role: str) -> dict[str, Any]:
    """Return the exact descriptor that firmware must compile into its ELF."""

    row = profile_row(profile_id)
    if role not in ROLES:
        raise RuntimeLutContractError(f"unsupported action role {role!r}")
    common: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-compiled-transaction-descriptor",
        "profile_id": profile_id,
        "role": role,
        "device_api_version": DEVICE_API_VERSION,
        "one_compiled_visible_action": True,
        "raw_payload_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "payload_identity": _payload_identity(role),
    }
    if role == ROLE_RUNTIME:
        common.update(
            {
                "environment": row["runtime_environment"],
                "nvs_namespace": row["runtime_nvs_namespace"],
                "nvs_key": "used_v1",
                "factory_otp_white_action_present": False,
                "runtime_payload_present": True,
                "generated_include_sha256": row["generated_include_sha256"],
                "requested_electrical_metadata": row["requested_electrical_metadata"],
                "command_contract": {
                    "initial_psr_hex": "5f69",
                    "empirical_runtime_psr_hex": "5fe9",
                    "tres_reissued_after_runtime_psr": True,
                    "power_and_pll_from_selected_800_byte_header": True,
                    "e9_payload_hex": "01",
                    "h3": {
                        "r20_bytes": 799,
                        "r20_sha256": row["r20_sha256"],
                        "r21_bytes": 704,
                        "r21_sha256": row["r21_sha256"],
                        "r21_all_ff": True,
                    },
                    "global_init_and_config_scope": "ToBoth",
                    "controller_upload_strategy": "sequential_CS1_then_CS2",
                    "controller_upload_order": ["CS1", "CS2"],
                    "strategy_switch_allowed": False,
                    "vcom_write_or_sweep": False,
                    "global_to_both_exact_order": [
                        "PSR_5FE9",
                        "PWR_FROM_SELECTED_HEADER",
                        "IDLE_GATE_AFTER_PWR",
                        "PLL_FROM_SELECTED_HEADER",
                        "TRES_512X600",
                    ],
                    "per_controller_exact_order": [
                        "E9_01",
                        "IDLE_GATE_AFTER_E9",
                        "R20_799",
                        "R21_704FF",
                    ],
                    "idle_gate_failure_stops_all_later_commands": True,
                    "direct_source_gate_evidence": {
                        "pwr_idle_gate": "vendor EDP_init.c:1169-1176",
                        "e9_idle_gate": "vendor EDP_init.c:1223-1227",
                    },
                },
            }
        )
    else:
        common.update(
            {
                "environment": row["recovery_environment"],
                "nvs_namespace": row["recovery_nvs_namespace"],
                "nvs_key": "used_v1",
                "factory_otp_white_action_present": True,
                "runtime_payload_present": False,
                "generated_include_sha256": None,
                "command_contract": {
                    "factory_otp_init": True,
                    "runtime_psr_present": False,
                    "e9_present": False,
                    "r20_present": False,
                    "r21_present": False,
                    "global_init_and_config_scope": "ToBoth",
                    "controller_upload_strategy": "sequential_CS1_then_CS2",
                    "controller_upload_order": ["CS1", "CS2"],
                    "strategy_switch_allowed": False,
                    "vcom_write_or_sweep": False,
                },
            }
        )
    return common


def compiled_descriptor_marker(profile_id: str, role: str) -> str:
    digest = sha256(transaction_descriptor(profile_id, role))
    short_role = "RUNTIME" if role == ROLE_RUNTIME else "OTP_WHITE"
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|"
        f"PROFILE={profile_id}|ROLE={short_role}|SHA256={digest}"
    )


def _action(profile_id: str, ordinal: int, role: str) -> dict[str, Any]:
    row = profile_row(profile_id)
    descriptor = transaction_descriptor(profile_id, role)
    preimage = {
        "schema_version": 1,
        "kind": "mf1750-ec5-empirical-h3-visible-action",
        "campaign_id": f"EC5_EMPIRICAL_H3_{profile_id}_V1",
        "profile_id": profile_id,
        "ordinal": ordinal,
        "role": role,
        "environment": descriptor["environment"],
        "nvs_namespace": descriptor["nvs_namespace"],
        "transaction_descriptor_sha256": sha256(descriptor),
        "assumption_acceptance_sha256": assumption_acceptance()["canonical_sha256"],
        "temperature_policy": (
            {
                "kind": "experimental_fixed_25_from_adjacent_legacy_selector",
                "allowed_c": row["experimental_fixed_temperature_guard_c"],
                "guard_basis": row["temperature_guard_basis"],
                "vendor_filename_band_claim": False,
                "temperature_compatibility_qualified": False,
                "safety_proof": False,
            }
            if role == ROLE_RUNTIME
            else {
                "kind": "supervised_factory_otp_recovery_operator_record",
                "allowed_record_range_c": list(RECOVERY_TEMPERATURE_RECORD_RANGE_C),
                "upper_guard_basis": "existing_successful_factory_otp_white_observation",
                "inherits_selected_vendor_profile_band": False,
                "automatic_safe_temperature_claim": False,
                "device_temperature_specification_claim": False,
                "requires_current_limit_current_temperature_and_cutoff_monitoring": True,
            }
        ),
        "operator_monitoring_confirmation": OPERATOR_MONITORING_CONFIRMATION,
        "payload_identity": descriptor["payload_identity"],
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
    }
    return {**preimage, "hardware_action_id": sha256(preimage)}


def profile_contract(profile_id: str) -> dict[str, Any]:
    row = profile_row(profile_id)
    actions = [
        _action(profile_id, 1, ROLE_RUNTIME),
        _action(profile_id, 2, ROLE_WHITE),
    ]
    root: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "campaign_id": f"EC5_EMPIRICAL_H3_{profile_id}_V1",
        "profile_id": profile_id,
        "profile_auto_selection": False,
        "profile_priority_resolved": False,
        "vendor_filename_numeric_tokens": row["vendor_filename_numeric_tokens"],
        "temperature_filename_semantics_proven": row[
            "temperature_filename_semantics_proven"
        ],
        "experimental_fixed_temperature_guard_c": row[
            "experimental_fixed_temperature_guard_c"
        ],
        "temperature_guard_basis": row["temperature_guard_basis"],
        "temperature_compatibility_qualified": row[
            "temperature_compatibility_qualified"
        ],
        "temperature_is_operator_supplied_per_action": True,
        "generated_include": {
            "relative_path": row["generated_include"],
            "sha256": row["generated_include_sha256"],
        },
        "requested_electrical_metadata": row["requested_electrical_metadata"],
        "assumption_acceptance": assumption_acceptance(),
        "current_prior": {
            "prior_state_id": PRIOR_STATE_ID,
            "j2": "OFF",
            "screen": "clean_white",
            "hardware_access_used_to_create_this_contract": False,
        },
        "firmware_separation": {
            "binary_count": 2,
            "environment_count": 2,
            "nvs_namespace_count": 2,
            "runtime_environment": row["runtime_environment"],
            "runtime_nvs_namespace": row["runtime_nvs_namespace"],
            "runtime_binary_action_count": 1,
            "runtime_binary_contains_recovery": False,
            "recovery_environment": row["recovery_environment"],
            "recovery_nvs_namespace": row["recovery_nvs_namespace"],
            "recovery_binary_action_count": 1,
            "recovery_binary_contains_runtime_payload": False,
            "same_binary_for_runtime_and_recovery": False,
        },
        "actions": actions,
        "runner_policy": {
            "default_mode": "offline_describe",
            "diagnostic_http_methods": ["GET"],
            "mutation_requires_exact_one_shot_authorization": True,
            "claim_before_first_network_request": True,
            "maximum_arm_posts_per_action": 1,
            "maximum_execute_posts_per_action": 1,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
            "profile_switch": False,
            "runtime_failure_next_steps": [
                "J2_OFF",
                "flash_exact_recovery_environment",
                "new_read_only_J2_OFF_diagnostic",
                "new_independent_white_authorization",
            ],
        },
        "firmware_identities_materialized": False,
        "execution_eligible": False,
        "live_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refreshes": 0,
    }
    root["contract_id"] = sha256(root)
    return root


def validate_contract(profile_id: str) -> dict[str, Any]:
    root = profile_contract(profile_id)
    if [item["ordinal"] for item in root["actions"]] != [1, 2]:
        raise RuntimeLutContractError("action order drifted")
    if [item["role"] for item in root["actions"]] != list(ROLES):
        raise RuntimeLutContractError("action roles drifted")
    separation = root["firmware_separation"]
    if (
        separation["runtime_environment"] == separation["recovery_environment"]
        or separation["runtime_nvs_namespace"] == separation["recovery_nvs_namespace"]
    ):
        raise RuntimeLutContractError(
            "runtime and recovery identities are not separate"
        )
    include = REPO_ROOT / root["generated_include"]["relative_path"]
    if (
        not include.is_file()
        or sha256(include.read_bytes()) != root["generated_include"]["sha256"]
    ):
        raise RuntimeLutContractError("generated profile include identity differs")
    if [item["id"] for item in U1_U7] != [f"U{index}" for index in range(1, 8)]:
        raise RuntimeLutContractError("U1-U7 assumption identifiers drifted")
    return root


for _profile_id in PROFILES:
    validate_contract(_profile_id)
