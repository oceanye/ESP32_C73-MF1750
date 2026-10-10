#!/usr/bin/env python3
"""Frozen host-only WF23 C23/T23 matched-control contract.

C23 repeats the WF23_25 prefix-derived PWR/PLL setup and the existing atlas
transaction while deleting every R20/R21 command span.  T23 remains the
complete, identity-pinned WF23 empirical-H3 V7 treatment.  The pair therefore
controls the WF23 header separately from the already-sealed WF20 C20/T20 pair.

This module performs no hardware, serial, upload, network, or display I/O and
does not authorize either visible action.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final, Mapping

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_eightcode_atlas as atlas  # noqa: E402
from tools import mf1750_ec5_runtime_lut_contract as h3_contract  # noqa: E402


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c23-matched-no-r20-r21-profile-contract"
CLASSIFICATION: Final = "WF23_HEADER_MATCHED_DELETE_ONLY_CONTROL_NOT_AUTHORIZATION"
CONTROL_DESIGN: Final = "WF23_E9_ONLY_NO_R20_R21_DELETE_ONLY_NOT_TIME_MATCHED"
DEVICE_API_VERSION: Final = "MF1750_EC5_H3_C23_MATCHED_CONTROL_DEVICE_V1"
PROFILE_ID: Final = "WF23_25"
PROFILES: Final = (PROFILE_ID,)
CAMPAIGN_ID: Final = "EC5_H3_C23_MATCHED_NO_R20_R21_WF23_25_V1"
ROLE_CONTROL: Final = "H3_C23_MATCHED_NO_R20_R21_EIGHT_CODE_ATLAS"
ROLE_WHITE: Final = "H3_C23_MATCHED_CONTROL_FACTORY_OTP_WHITE_RECOVERY"
ROLES: Final = (ROLE_CONTROL, ROLE_WHITE)
CONTROL_ACCEPTANCE_PHRASE: Final = (
    "ACCEPT_C23_C1_C8_NO_R20_R21_CONTROL__ATTRIBUTION_NOT_PROVEN"
)
INITIAL_PRECONDITION_PHRASE: Final = (
    "CONFIRM_C23_INITIAL_CLEAN_WHITE_J2_OFF_ELECTRICAL_NORMAL_MONITORED__"
    "NOT_T23_FINALIZED_EVIDENCE"
)
CONTROL_RECOVERY_FINALIZATION_PHRASE: Final = (
    "FINALIZE_C23_AFTER_CONTROL_AND_CLEAN_RECOVERY__ALLOW_T23_PREPARATION"
)
PAIR_FINALIZATION_PHRASE: Final = "FINALIZE_C23_T23_PAIR_AFTER_BOTH_RECOVERIES_SUCCESS"

PINNED_TREATMENT_RELEASE_ID: Final = (
    "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4"
)
PINNED_TREATMENT_RELEASE_CANONICAL_SHA256: Final = (
    "0f5dfeb8359abea5d0d4b5b800958737f161f78ca81ec3515877920fcd759b7a"
)
PINNED_TREATMENT_RELEASE_FILE_SHA256: Final = (
    "c06ebabb7096ba848d9635c02609f86f0cc97302ae83cade3b315b6ab6346f3b"
)
PINNED_TREATMENT_RUNTIME_BINARY_SHA256: Final = (
    "6eb9115ef143142de801c96fe31c8b9898455f550a52a85c51cfa7a2026698e2"
)
PINNED_TREATMENT_RUNTIME_ELF_SHA256: Final = (
    "d385b01ffcee182d9614d9462489c44628990a576c54979cc9254c8fc3824aa1"
)
PINNED_TREATMENT_RECOVERY_BINARY_SHA256: Final = (
    "2712984d39f1c295841a4b9994c72ee13f6c6935e514ce918648cce2a6159e7c"
)
PINNED_TREATMENT_RECOVERY_ELF_SHA256: Final = (
    "9c3587285d2b4748ca1594dffbc0848dd394d48c74bd205d6d7ce90699bd3939"
)

OPERATOR_MONITORING_CONFIRMATION: Final = h3_contract.OPERATOR_MONITORING_CONFIRMATION
RECOVERY_TEMPERATURE_RECORD_RANGE_C: Final = (
    h3_contract.RECOVERY_TEMPERATURE_RECORD_RANGE_C
)

_H3_ROW: Final[Mapping[str, Any]] = h3_contract.profile_row(PROFILE_ID)
_ROW: Final[Mapping[str, Any]] = {
    "vendor_filename_numeric_tokens": deepcopy(
        _H3_ROW["vendor_filename_numeric_tokens"]
    ),
    "experimental_fixed_temperature_guard_c": deepcopy(
        _H3_ROW["experimental_fixed_temperature_guard_c"]
    ),
    "temperature_filename_semantics_proven": _H3_ROW[
        "temperature_filename_semantics_proven"
    ],
    "temperature_compatibility_qualified": _H3_ROW[
        "temperature_compatibility_qualified"
    ],
    "temperature_guard_basis": _H3_ROW["temperature_guard_basis"],
    "reference_generated_include": _H3_ROW["generated_include"],
    "reference_generated_include_sha256": _H3_ROW["generated_include_sha256"],
    "reference_r20_sha256": _H3_ROW["r20_sha256"],
    "reference_r21_sha256": _H3_ROW["r21_sha256"],
    "requested_electrical_metadata": deepcopy(_H3_ROW["requested_electrical_metadata"]),
    "control_environment": "ec5_h3_c23_matched_no_r20_r21_wf23_25",
    "control_nvs_namespace": "h3c23ctl_v1",
    "recovery_environment": "ec5_h3_c23_matched_control_otp_white_wf23_25",
    "recovery_nvs_namespace": "h3c23rw_v1",
}

_DEVICE_ROLE_ROWS: Final[Mapping[str, Mapping[str, str]]] = {
    ROLE_CONTROL: {
        "kind_prefix": "mf1750-ec5-h3-c23-matched-no-r20-r21",
        "test_id": "EC5-H3-C23-MATCHED-NO-R20-R21-V1",
        "base_route": "/api/ec5/h3-c23-control-v1",
        "build_tag": "MF1750_EC5_H3_C23_NO_R20_R21_WF23_25_V1_2026-08-13",
        "arm_intent": "ARM_ONE_C23_NO_R20_R21_ATLAS_NOT_AUTHORIZATION",
        "execute_intent": "EXECUTE_ONE_C23_NO_R20_R21_ATLAS_ONCE",
    },
    ROLE_WHITE: {
        "kind_prefix": "mf1750-ec5-h3-c23-control-otp-white",
        "test_id": "EC5-H3-C23-CONTROL-OTP-WHITE-V1",
        "base_route": "/api/ec5/h3-c23-white-v1",
        "build_tag": "MF1750_EC5_H3_C23_OTP_WHITE_WF23_25_V1_2026-08-13",
        "arm_intent": "ARM_ONE_C23_FACTORY_OTP_WHITE_NOT_AUTHORIZATION",
        "execute_intent": "EXECUTE_ONE_C23_FACTORY_OTP_WHITE_ONCE",
    },
}

# These remain unresolved risks.  Acceptance is not proof and must be fresh
# for the exact C23 boot/action if the release later becomes executable.
C1_C8: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "id": "C1",
        "statement": (
            "C23 factory init, 5F69-to-5FE9 transition, WF23-derived PWR/PLL, "
            "TRES, idle gates, and ordering are compiled assertions without "
            "controller readback"
        ),
    },
    {
        "id": "C2",
        "statement": (
            "the dedicated C23 source and descriptor omit R20/R21 command writes; "
            "arbitrary whole-firmware byte absence is not required or meaningful"
        ),
    },
    {
        "id": "C3",
        "statement": (
            "whether omitted or rejected SRAM LUT writes select a hidden fallback "
            "waveform is unproven for SPD1657/E2802"
        ),
    },
    {
        "id": "C4",
        "statement": (
            "E9=01 semantics, sequential CS1 then CS2 application, single BUSY, "
            "and secondary-controller acceptance remain unproven"
        ),
    },
    {
        "id": "C5",
        "statement": (
            "WF23_25 filename-token semantics, panel/FPL/film-lot qualification, "
            "and electrical limits are unproven; exact 25.0 C is only an "
            "adjacent-legacy experimental guard and VCOM must not be swept"
        ),
    },
    {
        "id": "C6",
        "statement": (
            "clean-white, electrical-normal, temperature, monitoring, and J2-OFF "
            "preconditions are operator observations rather than independent proof"
        ),
    },
    {
        "id": "C7",
        "statement": (
            "a clean C23 recovery cannot prove an identical latent particle state "
            "before the later T23 action"
        ),
    },
    {
        "id": "C8",
        "statement": (
            "C23 is delete-only and removes 3010 aggregate SPI bytes plus ten "
            "cooperative yields, so a visible difference is not payload-only proof"
        ),
    },
)


class C23MatchedControlContractError(ValueError):
    """The frozen WF23 C23 matched-control contract failed closed."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise C23MatchedControlContractError(
            "value is not canonical-JSON encodable"
        ) from error


def sha256(value: bytes | Mapping[str, Any] | list[Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def profile_row(profile_id: str = PROFILE_ID) -> dict[str, Any]:
    if profile_id != PROFILE_ID:
        raise C23MatchedControlContractError(
            f"unsupported explicit C23 profile {profile_id!r}"
        )
    return deepcopy(dict(_ROW))


def device_binding(profile_id: str, role: str) -> dict[str, str]:
    profile_row(profile_id)
    if role not in ROLES:
        raise C23MatchedControlContractError(f"unsupported C23 role {role!r}")
    return {**dict(_DEVICE_ROLE_ROWS[role]), "campaign_id": CAMPAIGN_ID}


def risk_acceptance() -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-h3-c23-c1-c8-acceptance",
        "acceptance_is_proof": False,
        "risks": deepcopy(list(C1_C8)),
        "required_exact_phrase": CONTROL_ACCEPTANCE_PHRASE,
    }
    value["canonical_sha256"] = sha256(value)
    return value


def payload_identity(role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise C23MatchedControlContractError(f"unsupported C23 role {role!r}")
    atlas_role = "atlas" if role == ROLE_CONTROL else "white"
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
    row = profile_row(profile_id)
    if role not in ROLES:
        raise C23MatchedControlContractError(f"unsupported C23 role {role!r}")
    common: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-h3-c23-compiled-transaction-descriptor",
        "profile_id": profile_id,
        "campaign_id": CAMPAIGN_ID,
        "role": role,
        "device_api_version": DEVICE_API_VERSION,
        "one_compiled_visible_action": True,
        "raw_payload_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "payload_identity": payload_identity(role),
    }
    if role == ROLE_CONTROL:
        common.update(
            {
                "environment": row["control_environment"],
                "nvs_namespace": row["control_nvs_namespace"],
                "nvs_key": "used_v2",
                "factory_otp_white_action_present": False,
                "runtime_lut_payload_present": False,
                "reference_generated_include_compiled": False,
                "reference_generated_include_sha256": row[
                    "reference_generated_include_sha256"
                ],
                "reference_r20_sha256": row["reference_r20_sha256"],
                "reference_r21_sha256": row["reference_r21_sha256"],
                "requested_electrical_metadata": row["requested_electrical_metadata"],
                "control_design": {
                    "classification": CONTROL_DESIGN,
                    "strict_payload_only_control": False,
                    "time_matched_control": False,
                    "dummy_clocks_inserted": False,
                    "empty_r20_or_r21_commands_inserted": False,
                    "per_controller_removed_from_t23": {
                        "command_spans": ["R20_799", "R21_704FF"],
                        "span_count": 2,
                        "spi_bytes_and_edges": 1505,
                        "cooperative_yields": 5,
                    },
                    "dual_controller_total_removed": {
                        "command_spans": 4,
                        "spi_bytes_and_edges": 3010,
                        "cooperative_yields": 10,
                    },
                },
                "command_contract": {
                    "factory_initialization_before_matched_override": True,
                    "initial_psr_hex": "5f69",
                    "matched_runtime_psr_hex": "5fe9",
                    "tres_reissued_after_matched_psr": True,
                    "power_and_pll_equal_selected_t23_header_values": True,
                    "e9_payload_hex": "01",
                    "r20_command_writes": 0,
                    "r21_command_writes": 0,
                    "r20_payload_bytes": 0,
                    "r21_payload_bytes": 0,
                    "dummy_spi_bytes_or_edges": 0,
                    "empty_r20_or_r21_commands": 0,
                    "global_init_and_config_scope": "ToBoth",
                    "controller_strategy": "sequential_CS1_then_CS2",
                    "controller_order": ["CS1", "CS2"],
                    "strategy_switch_allowed": False,
                    "vcom_write_or_sweep": False,
                    "global_to_both_exact_order": [
                        "FACTORY_INIT_PSR_5F69",
                        "PSR_5FE9",
                        "PWR_MATCHED_TO_WF23_HEADER",
                        "IDLE_GATE_AFTER_PWR",
                        "PLL_MATCHED_TO_WF23_HEADER",
                        "TRES_512X600",
                    ],
                    "per_controller_exact_order": [
                        "E9_01",
                        "IDLE_GATE_AFTER_E9",
                        "NO_R20",
                        "NO_R21",
                    ],
                    "atlas_dtm_and_refresh_after_both_controller_sequences": True,
                    "idle_gate_failure_stops_all_later_commands": True,
                },
            }
        )
    else:
        common.update(
            {
                "environment": row["recovery_environment"],
                "nvs_namespace": row["recovery_nvs_namespace"],
                "nvs_key": "used_v2",
                "factory_otp_white_action_present": True,
                "runtime_lut_payload_present": False,
                "matched_control_action_present": False,
                "command_contract": {
                    "factory_otp_init": True,
                    "runtime_psr_present": False,
                    "e9_present": False,
                    "r20_present": False,
                    "r21_present": False,
                    "global_init_and_config_scope": "ToBoth",
                    "controller_strategy": "sequential_CS1_then_CS2",
                    "controller_order": ["CS1", "CS2"],
                    "strategy_switch_allowed": False,
                    "vcom_write_or_sweep": False,
                },
            }
        )
    return common


def compiled_descriptor_marker(profile_id: str, role: str) -> str:
    digest = sha256(transaction_descriptor(profile_id, role))
    short_role = "NO_R20_R21" if role == ROLE_CONTROL else "OTP_WHITE"
    return (
        "MF1750_EC5_H3_C23_TX_DESCRIPTOR_V1|"
        f"PROFILE={profile_id}|ROLE={short_role}|SHA256={digest}"
    )


def command_audit_marker(profile_id: str, role: str) -> str:
    profile_row(profile_id)
    if role == ROLE_CONTROL:
        detail = (
            "R20_COMMAND_WRITES=0|R21_COMMAND_WRITES=0|R20_BYTES=0|R21_BYTES=0|"
            "DESIGN=WF23_E9_ONLY_DELETE_ONLY_NOT_TIME_MATCHED"
        )
    elif role == ROLE_WHITE:
        detail = "FACTORY_OTP_ONLY=1|CONTROL_SEQUENCE=0|RUNTIME_PAYLOAD=0"
    else:
        raise C23MatchedControlContractError(f"unsupported C23 role {role!r}")
    return f"MF1750_EC5_H3_C23_COMMAND_AUDIT_V1|{detail}"


def _action(profile_id: str, ordinal: int, role: str) -> dict[str, Any]:
    row = profile_row(profile_id)
    descriptor = transaction_descriptor(profile_id, role)
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-h3-c23-visible-action",
        "campaign_id": CAMPAIGN_ID,
        "profile_id": profile_id,
        "ordinal": ordinal,
        "role": role,
        "environment": descriptor["environment"],
        "nvs_namespace": descriptor["nvs_namespace"],
        "transaction_descriptor_sha256": sha256(descriptor),
        "c1_c8_acceptance_sha256": risk_acceptance()["canonical_sha256"],
        "temperature_policy": (
            {
                "kind": "c23_initial_control_exact_25_guard",
                "allowed_c": row["experimental_fixed_temperature_guard_c"],
                "guard_basis": row["temperature_guard_basis"],
                "vendor_filename_band_claim": False,
                "temperature_compatibility_qualified": False,
                "establishes_pair_temperature_for_t23": True,
                "temperature_is_live_operator_observation": True,
                "safety_proof": False,
            }
            if role == ROLE_CONTROL
            else {
                "kind": "supervised_factory_otp_recovery_operator_record",
                "allowed_record_range_c": list(RECOVERY_TEMPERATURE_RECORD_RANGE_C),
                "automatic_safe_temperature_claim": False,
                "requires_monitoring": True,
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


def profile_contract(profile_id: str = PROFILE_ID) -> dict[str, Any]:
    row = profile_row(profile_id)
    actions = [
        _action(profile_id, 1, ROLE_CONTROL),
        _action(profile_id, 2, ROLE_WHITE),
    ]
    root: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "campaign_id": CAMPAIGN_ID,
        "profile_id": profile_id,
        "profile_auto_selection": False,
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
        "pinned_treatment_reference": {
            "campaign_kind": h3_contract.KIND,
            "profile_id": profile_id,
            "release_id": PINNED_TREATMENT_RELEASE_ID,
            "release_canonical_sha256": PINNED_TREATMENT_RELEASE_CANONICAL_SHA256,
            "release_file_sha256": PINNED_TREATMENT_RELEASE_FILE_SHA256,
            "runtime_binary_sha256": PINNED_TREATMENT_RUNTIME_BINARY_SHA256,
            "runtime_elf_sha256": PINNED_TREATMENT_RUNTIME_ELF_SHA256,
            "recovery_binary_sha256": PINNED_TREATMENT_RECOVERY_BINARY_SHA256,
            "recovery_elf_sha256": PINNED_TREATMENT_RECOVERY_ELF_SHA256,
            "generated_include": row["reference_generated_include"],
            "generated_include_sha256": row["reference_generated_include_sha256"],
            "r20_sha256": row["reference_r20_sha256"],
            "r21_sha256": row["reference_r21_sha256"],
            "requested_electrical_metadata": row["requested_electrical_metadata"],
            "payload_is_reference_only_not_compiled_into_control": True,
            "release_deep_validation_required": True,
            "whole_file_sha256_binding_required": True,
        },
        "interpretation_contract": {
            "control_design": CONTROL_DESIGN,
            "strict_payload_only_or_time_matched": False,
            "if_t23_differs_from_c23": (
                "DETECTABLE_INCREMENTAL_EFFECT_COMPATIBLE_WITH_R20_R21_"
                "CONTRIBUTION_NOT_ACCEPTANCE_OR_ABI_PROOF"
            ),
            "if_t23_equals_c23": "NO_DETECTABLE_INCREMENTAL_EFFECT",
            "forbidden_zero_difference_conclusions": [
                "HIDDEN_FALLBACK_PROVEN",
                "R20_R21_WRITES_IGNORED_PROVEN",
                "R20_R21_WRITES_REJECTED_PROVEN",
                "RUNTIME_LUT_ABI_DISPROVEN",
            ],
        },
        "pair_sequence": {
            "order_is_normative": True,
            "stages": [
                {"ordinal": 1, "stage": "C23_NO_R20_R21_ONCE"},
                {"ordinal": 2, "stage": "C23_FACTORY_OTP_WHITE_ONCE"},
                {
                    "ordinal": 3,
                    "stage": "T23_PINNED_H3_V7_RUNTIME_ONCE",
                    "requires_finalized_c23": True,
                    "requires_fresh_j2_off_diagnostic": True,
                    "requires_exact_c23_temperature": True,
                },
                {
                    "ordinal": 4,
                    "stage": "T23_PINNED_H3_V7_FACTORY_OTP_WHITE_ONCE",
                    "requires_independent_authorization": True,
                },
            ],
            "c23_finalization_requires_both_control_results": True,
            "t23_gate_requires_c23_finalization": True,
            "pair_finalization_requires_all_four_success_results": True,
            "fault_or_unknown_blocks_later_stage": True,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
        },
        "cross_profile_effect_comparison": {
            "compare_t20_minus_c20_and_t23_minus_c23_separately": True,
            "direct_t20_minus_t23_is_body_only_attribution": False,
            "profile_hybrid_or_record_splice_allowed": False,
            "primary_observable": "same_atlas_position_hue_or_color_class_change",
            "brightness_only_counts_as_new_color": False,
        },
        "initial_live_preconditions": {
            "fresh_c23_firmware_j2_off_diagnostic_required": True,
            "operator_clean_white_required": True,
            "operator_electrical_normal_required": True,
            "operator_monitoring_required": True,
            "operator_exact_25_temperature_required": True,
            "required_exact_phrase": INITIAL_PRECONDITION_PHRASE,
            "satisfied_at_contract_materialization": False,
        },
        "risk_acceptance": risk_acceptance(),
        "firmware_separation": {
            "binary_count": 2,
            "environment_count": 2,
            "nvs_namespace_count": 2,
            "control_environment": row["control_environment"],
            "control_nvs_namespace": row["control_nvs_namespace"],
            "control_binary_action_count": 1,
            "control_binary_contains_recovery": False,
            "recovery_environment": row["recovery_environment"],
            "recovery_nvs_namespace": row["recovery_nvs_namespace"],
            "recovery_binary_action_count": 1,
            "recovery_binary_contains_control": False,
            "same_binary": False,
        },
        "actions": actions,
        "runner_policy": {
            "default_mode": "offline_describe",
            "separate_app_only_flash_before_each_action": True,
            "fresh_j2_off_diagnostic_before_each_action": True,
            "diagnostic_http_methods": ["GET"],
            "diagnostic_get_requests_before_claim": 4,
            "diagnostic_mutation_requests_before_claim": 0,
            "claim_before_first_network_mutation": True,
            "separate_authorization_per_action": True,
            "maximum_arm_posts_per_action": 1,
            "maximum_execute_posts_per_action": 1,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
            "profile_switch": False,
        },
        "firmware_identities_materialized": False,
        "pinned_treatment_identity_materialized": False,
        "execution_eligible": False,
        "live_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "visible_refreshes": 0,
    }
    root["contract_id"] = sha256(root)
    return root


def validate_contract(profile_id: str = PROFILE_ID) -> dict[str, Any]:
    root = profile_contract(profile_id)
    actions = root["actions"]
    if [item["ordinal"] for item in actions] != [1, 2]:
        raise C23MatchedControlContractError("C23 action order drifted")
    if [item["role"] for item in actions] != list(ROLES):
        raise C23MatchedControlContractError("C23 action roles drifted")
    if len({item["hardware_action_id"] for item in actions}) != 2:
        raise C23MatchedControlContractError("C23 action IDs collide")
    row = profile_row(profile_id)
    h3 = h3_contract.validate_contract(profile_id)
    h3_actions = {item["hardware_action_id"] for item in h3["actions"]}
    h3_namespaces = {item["nvs_namespace"] for item in h3["actions"]}
    if any(item["hardware_action_id"] in h3_actions for item in actions):
        raise C23MatchedControlContractError("C23 action reuses T23 action")
    if any(item["nvs_namespace"] in h3_namespaces for item in actions):
        raise C23MatchedControlContractError("C23 NVS reuses T23 namespace")
    if row["control_nvs_namespace"] == row["recovery_nvs_namespace"]:
        raise C23MatchedControlContractError("C23 control/recovery NVS collide")
    if any(
        len(value) > 15
        for value in (row["control_nvs_namespace"], row["recovery_nvs_namespace"])
    ):
        raise C23MatchedControlContractError("C23 NVS namespace exceeds 15 chars")
    include = REPO_ROOT / row["reference_generated_include"]
    if (
        not include.is_file()
        or sha256(include.read_bytes()) != row["reference_generated_include_sha256"]
    ):
        raise C23MatchedControlContractError("WF23 reference include differs")
    if [item["id"] for item in C1_C8] != [f"C{index}" for index in range(1, 9)]:
        raise C23MatchedControlContractError("C23 risk identifiers drifted")
    if root["pinned_treatment_reference"]["release_id"] != (
        PINNED_TREATMENT_RELEASE_ID
    ):
        raise C23MatchedControlContractError("T23 release identity drifted")
    return root


validate_contract()


def main() -> int:
    print(
        json.dumps(
            validate_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
