#!/usr/bin/env python3
"""Frozen host-only C-first contract for the matched no-R20/R21 H3 control.

This campaign is deliberately separate from the empirical-H3 campaign.  It
repeats the selected WF20_25 initialization, electrical configuration, E9
sequence, atlas DTM bytes, and visible refresh while omitting command writes
to registers 0x20 and 0x21.  A second, independently flashed factory-OTP
white image is reserved for recovery.  Nothing in this module authorizes or
performs hardware, serial, upload, or network I/O.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Final, Mapping

from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_ec5_runtime_lut_contract as h3_contract


SCHEMA_VERSION: Final = 2
KIND: Final = "mf1750-ec5-h3-matched-no-r20-r21-c-first-profile-contract"
CLASSIFICATION: Final = "MATCHED_NO_R20_R21_ATTRIBUTION_CONTROL_NOT_LIVE_AUTHORIZATION"
CONTROL_DESIGN: Final = "E9_ONLY_NO_R20_R21_COMMAND_STREAM_AND_DURATION_CONTROL"
DEVICE_API_VERSION: Final = "MF1750_EC5_H3_MATCHED_CONTROL_DEVICE_V2"
PROFILE_ID: Final = "WF20_25"
PROFILES: Final = (PROFILE_ID,)
CAMPAIGN_ID: Final = "EC5_H3_MATCHED_NO_R20_R21_WF20_25_C_FIRST_V2"
ROLE_CONTROL: Final = "H3_MATCHED_NO_R20_R21_EIGHT_CODE_ATLAS"
ROLE_WHITE: Final = "H3_MATCHED_CONTROL_FACTORY_OTP_WHITE_RECOVERY"
ROLES: Final = (ROLE_CONTROL, ROLE_WHITE)
OPERATOR_MONITORING_CONFIRMATION: Final = h3_contract.OPERATOR_MONITORING_CONFIRMATION
RECOVERY_TEMPERATURE_RECORD_RANGE_C: Final = (
    h3_contract.RECOVERY_TEMPERATURE_RECORD_RANGE_C
)
CONTROL_ACCEPTANCE_PHRASE: Final = (
    "ACCEPT_C1_C8_C_FIRST_NO_R20_R21_CONTROL__ATTRIBUTION_NOT_PROVEN"
)
INITIAL_PRECONDITION_PHRASE: Final = (
    "CONFIRM_INITIAL_CLEAN_WHITE_J2_OFF_ELECTRICAL_NORMAL_MONITORED__"
    "NOT_TREATMENT_FINALIZED_EVIDENCE"
)
CONTROL_RECOVERY_FINALIZATION_PHRASE: Final = (
    "FINALIZE_C_LEG_AFTER_CONTROL_SUCCESS_AND_CLEAN_RECOVERY__"
    "ALLOW_SEPARATE_TREATMENT_PREPARATION"
)
PAIR_FINALIZATION_PHRASE: Final = (
    "FINALIZE_C_FIRST_MATCHED_PAIR_AFTER_C_RECOVERY_AND_T_RECOVERY_SUCCESS"
)
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PINNED_TREATMENT_RELEASE_ID: Final = (
    "52553c37d47198a7bd1604915c142ac4f7eb33d4ca59064340c0a25a5d9f837e"
)
PINNED_TREATMENT_RELEASE_CANONICAL_SHA256: Final = (
    "91a498788b074c0d8619e666df0e8c96fc8868e6c9fbee024b97ad8ad183d92e"
)
PINNED_TREATMENT_RELEASE_FILE_SHA256: Final = (
    "323edaf20ddc60e1302b7df7217320ddb19c2c3ab47cad14409888469ec4809e"
)
PINNED_TREATMENT_RUNTIME_BINARY_SHA256: Final = (
    "53d3abf2319761f282c518ebd6fd606f8efdfe0b1a869a1dcf61c04adbdecc06"
)
PINNED_TREATMENT_RUNTIME_ELF_SHA256: Final = (
    "63add1a2eb9c12a03be7d179c64ae48b26a3e2551ff3b7bfebccd133a28891df"
)
PINNED_TREATMENT_RECOVERY_BINARY_SHA256: Final = (
    "6a50b2bf287f3d6fd688c9cdfa2052ddc7db3d86c2f2ac9157585cdafd0766d2"
)
PINNED_TREATMENT_RECOVERY_ELF_SHA256: Final = (
    "0c8c82c35b46c69742f27a28c6fdce0ac2d003b3b0dd8a8b7b80152a608d9924"
)
SUPERSEDED_V1_ACTION_IDS: Final = (
    "17731f05726b3e3e218d070b2b9f8738d8738da45dc11108ea38532274df6e66",
    "0f9263be507628db9203892641f0169c80e50a07034e573495e583951b435398",
)
SUPERSEDED_V1_NVS_NAMESPACES: Final = ("h3ctl_w20_v1", "h3crw20_v1")

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
    "control_environment": "ec5_h3_matched_no_r20_r21_wf20_25",
    "control_nvs_namespace": "h3ctl_w20_v2",
    "recovery_environment": "ec5_h3_matched_control_otp_white_wf20_25",
    "recovery_nvs_namespace": "h3crw20_v2",
}

_DEVICE_ROLE_ROWS: Final[Mapping[str, Mapping[str, str]]] = {
    ROLE_CONTROL: {
        "kind_prefix": "mf1750-ec5-h3-matched-no-r20-r21",
        "test_id": "EC5-H3-MATCHED-NO-R20-R21-C-FIRST-V2",
        "base_route": "/api/ec5/h3-matched-control-v2",
        "build_tag": "MF1750_EC5_H3_MATCHED_NO_R20_R21_WF20_25_C_FIRST_V2_2026-08-11",
        "arm_intent": "ARM_ONE_MATCHED_NO_R20_R21_ATLAS_NOT_AUTHORIZATION",
        "execute_intent": "EXECUTE_ONE_MATCHED_NO_R20_R21_ATLAS_ONCE",
    },
    ROLE_WHITE: {
        "kind_prefix": "mf1750-ec5-h3-matched-control-otp-white",
        "test_id": "EC5-H3-MATCHED-CONTROL-OTP-WHITE-C-FIRST-V2",
        "base_route": "/api/ec5/h3-matched-control-white-v2",
        "build_tag": (
            "MF1750_EC5_H3_MATCHED_CONTROL_OTP_WHITE_WF20_25_C_FIRST_V2_2026-08-11"
        ),
        "arm_intent": "ARM_ONE_MATCHED_CONTROL_FACTORY_OTP_WHITE_NOT_AUTHORIZATION",
        "execute_intent": "EXECUTE_ONE_MATCHED_CONTROL_FACTORY_OTP_WHITE_ONCE",
    },
}

# These are unresolved risks, not safety or causality findings.  They must be
# reaccepted after each fresh J2-OFF diagnostic.
C1_C8: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "id": "C1",
        "statement": (
            "the control's factory init, 5F69->5FE9 transition, PWR, PLL, TRES, "
            "idle gates, and ordering are matched by compiled contract, not by "
            "controller readback"
        ),
    },
    {
        "id": "C2",
        "statement": (
            "source and dedicated descriptor omit 0x20/0x21 command writes, but "
            "arbitrary firmware-byte absence is neither required nor meaningful"
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
            "WF20_25 numeric filename-token semantics, panel/FPL/film-lot temperature "
            "compatibility, and electrical limits are unproven; exact 25.0 C is only "
            "an adjacent-legacy experimental guard; VCOM must not be written or swept"
        ),
    },
    {
        "id": "C6",
        "statement": (
            "the initial clean-white, electrical-normal, temperature, and J2-OFF "
            "preconditions are operator observations, not independent instrument proof"
        ),
    },
    {
        "id": "C7",
        "statement": (
            "a visually clean control recovery plus power/balance interval cannot "
            "prove an identical latent particle state before the later treatment"
        ),
    },
    {
        "id": "C8",
        "statement": (
            "this delete-only control is shorter by 1505 SPI bytes/edges and five "
            "cooperative yields per controller; it is not a strict payload-only or "
            "time-matched control and cannot prove R20/R21 acceptance or a general LUT ABI"
        ),
    },
)


class MatchedControlContractError(ValueError):
    """The frozen matched-control contract differs."""


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
        raise MatchedControlContractError(
            "value is not canonical-JSON encodable"
        ) from error


def sha256(value: bytes | Mapping[str, Any] | list[Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def profile_row(profile_id: str = PROFILE_ID) -> dict[str, Any]:
    if profile_id != PROFILE_ID:
        raise MatchedControlContractError(
            f"unsupported explicit matched-control profile {profile_id!r}"
        )
    return deepcopy(dict(_ROW))


def device_binding(profile_id: str, role: str) -> dict[str, str]:
    profile_row(profile_id)
    if role not in ROLES:
        raise MatchedControlContractError(f"unsupported device role {role!r}")
    return {**dict(_DEVICE_ROLE_ROWS[role]), "campaign_id": CAMPAIGN_ID}


def risk_acceptance() -> dict[str, Any]:
    value = {
        "schema_version": 2,
        "kind": "mf1750-ec5-h3-matched-control-c-first-c1-c8-acceptance-v2",
        "acceptance_is_proof": False,
        "risks": deepcopy(list(C1_C8)),
        "required_exact_phrase": CONTROL_ACCEPTANCE_PHRASE,
    }
    value["canonical_sha256"] = sha256(value)
    return value


def payload_identity(role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise MatchedControlContractError(f"unsupported action role {role!r}")
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
        raise MatchedControlContractError(f"unsupported action role {role!r}")
    common: dict[str, Any] = {
        "schema_version": 2,
        "kind": (
            "mf1750-ec5-h3-matched-control-c-first-compiled-transaction-descriptor-v2"
        ),
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
                    "per_controller_removed_from_h3": {
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
                    "power_and_pll_equal_selected_h3_header_values": True,
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
                        "PWR_MATCHED_TO_SELECTED_H3_HEADER",
                        "IDLE_GATE_AFTER_PWR",
                        "PLL_MATCHED_TO_SELECTED_H3_HEADER",
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
        "MF1750_EC5_H3_MATCHED_CONTROL_TX_DESCRIPTOR_V2|"
        f"PROFILE={profile_id}|ROLE={short_role}|SHA256={digest}"
    )


def command_audit_marker(profile_id: str, role: str) -> str:
    """Return the dedicated compiled command-surface assertion marker."""

    profile_row(profile_id)
    if role == ROLE_CONTROL:
        detail = (
            "R20_COMMAND_WRITES=0|R21_COMMAND_WRITES=0|R20_BYTES=0|R21_BYTES=0|"
            "DESIGN=E9_ONLY_DELETE_ONLY_NOT_TIME_MATCHED"
        )
    elif role == ROLE_WHITE:
        detail = "FACTORY_OTP_ONLY=1|CONTROL_SEQUENCE=0|RUNTIME_PAYLOAD=0"
    else:
        raise MatchedControlContractError(f"unsupported action role {role!r}")
    return f"MF1750_EC5_H3_MATCHED_CONTROL_COMMAND_AUDIT_V2|{detail}"


def _action(profile_id: str, ordinal: int, role: str) -> dict[str, Any]:
    row = profile_row(profile_id)
    descriptor = transaction_descriptor(profile_id, role)
    preimage = {
        "schema_version": 2,
        "kind": "mf1750-ec5-h3-matched-control-c-first-visible-action-v2",
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
                "kind": "initial_control_at_experimental_fixed_25_guard",
                "allowed_c": row["experimental_fixed_temperature_guard_c"],
                "guard_basis": row["temperature_guard_basis"],
                "vendor_filename_band_claim": False,
                "temperature_compatibility_qualified": False,
                "establishes_pair_temperature_for_later_treatment": True,
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
            "treatment_result_not_required_to_materialize_control_release": True,
        },
        "interpretation_contract": {
            "control_design": CONTROL_DESIGN,
            "strict_payload_only_or_time_matched": False,
            "if_treatment_differs_from_control": (
                "DETECTABLE_INCREMENTAL_EFFECT_COMPATIBLE_WITH_R20_R21_CONTRIBUTION_"
                "NOT_ACCEPTANCE_OR_ABI_PROOF"
            ),
            "if_treatment_equals_control": "NO_DETECTABLE_INCREMENTAL_EFFECT",
            "forbidden_zero_difference_conclusions": [
                "HIDDEN_FALLBACK_PROVEN",
                "R20_R21_WRITES_IGNORED_PROVEN",
                "R20_R21_WRITES_REJECTED_PROVEN",
                "RUNTIME_LUT_ABI_DISPROVEN",
            ],
        },
        "c_first_pair_sequence": {
            "order_is_normative": True,
            "stages": [
                {
                    "pair_ordinal": 1,
                    "stage": "C_MATCHED_NO_R20_R21_ONCE",
                    "release_action_ordinal": 1,
                    "independent_flash_diagnostic_authorization_claim": True,
                },
                {
                    "pair_ordinal": 2,
                    "stage": "C_FACTORY_OTP_WHITE_RECOVERY_ONCE",
                    "release_action_ordinal": 2,
                    "independent_flash_diagnostic_authorization_claim": True,
                },
                {
                    "pair_ordinal": 3,
                    "stage": "T_PINNED_H3_V7_RUNTIME_ONCE",
                    "pinned_treatment_action_ordinal": 1,
                    "requires_finalized_control_leg": True,
                    "requires_fresh_j2_off_diagnostic": True,
                    "requires_exact_control_temperature": True,
                },
                {
                    "pair_ordinal": 4,
                    "stage": "T_PINNED_H3_V7_FACTORY_OTP_WHITE_RECOVERY_ONCE",
                    "pinned_treatment_action_ordinal": 2,
                    "requires_treatment_claim": True,
                    "requires_independent_authorization": True,
                },
            ],
            "initial_clean_white_is_treatment_finalized_evidence": False,
            "control_leg_finalization_requires_both_success_results": True,
            "treatment_gate_requires_control_leg_finalization": True,
            "pair_finalization_requires_all_four_success_results": True,
            "fault_or_unknown_blocks_later_experimental_stage": True,
            "recovery_after_claim_is_containment_exception_only": True,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
        },
        "initial_live_preconditions": {
            "fresh_control_firmware_j2_off_diagnostic_required": True,
            "operator_clean_white_required": True,
            "operator_electrical_normal_required": True,
            "operator_monitoring_required": True,
            "operator_temperature_record_required": True,
            "initial_clean_white_is_prior_treatment_finalized": False,
            "operator_observations_are_independent_proof": False,
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
            "claim_before_first_run_invocation_network_request": True,
            "separate_authorization_per_action": True,
            "maximum_arm_posts_per_action": 1,
            "maximum_execute_posts_per_action": 1,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
            "profile_switch": False,
            "recovery_after_claim_is_containment_only": True,
            "recovery_success_does_not_auto_authorize_treatment": True,
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
        raise MatchedControlContractError("action order drifted")
    if [item["role"] for item in actions] != list(ROLES):
        raise MatchedControlContractError("action roles drifted")
    if len({item["hardware_action_id"] for item in actions}) != 2:
        raise MatchedControlContractError("matched-control action IDs collide")
    row = profile_row(profile_id)
    h3 = h3_contract.validate_contract(profile_id)
    h3_actions = {item["hardware_action_id"] for item in h3["actions"]}
    h3_namespaces = {item["nvs_namespace"] for item in h3["actions"]}
    if any(item["hardware_action_id"] in h3_actions for item in actions):
        raise MatchedControlContractError("matched-control action reuses H3 action")
    if any(item["hardware_action_id"] in SUPERSEDED_V1_ACTION_IDS for item in actions):
        raise MatchedControlContractError("C-first action reuses superseded V1 action")
    if any(item["nvs_namespace"] in h3_namespaces for item in actions):
        raise MatchedControlContractError("matched-control NVS reuses H3 namespace")
    if any(item["nvs_namespace"] in SUPERSEDED_V1_NVS_NAMESPACES for item in actions):
        raise MatchedControlContractError("C-first NVS reuses superseded V1 namespace")
    if row["control_nvs_namespace"] == row["recovery_nvs_namespace"]:
        raise MatchedControlContractError("control and recovery NVS collide")
    if any(
        len(value) > 15
        for value in (row["control_nvs_namespace"], row["recovery_nvs_namespace"])
    ):
        raise MatchedControlContractError("ESP-IDF NVS namespace exceeds 15 chars")
    include = REPO_ROOT / row["reference_generated_include"]
    if (
        not include.is_file()
        or sha256(include.read_bytes()) != row["reference_generated_include_sha256"]
    ):
        raise MatchedControlContractError("reference H3 include identity differs")
    if [item["id"] for item in C1_C8] != [f"C{index}" for index in range(1, 9)]:
        raise MatchedControlContractError("C1-C8 risk identifiers drifted")
    stages = root["c_first_pair_sequence"]["stages"]
    if [item["pair_ordinal"] for item in stages] != [1, 2, 3, 4]:
        raise MatchedControlContractError("C-first pair stage order drifted")
    treatment = root["pinned_treatment_reference"]
    if treatment["release_id"] != PINNED_TREATMENT_RELEASE_ID:
        raise MatchedControlContractError("pinned treatment release drifted")
    return root


validate_contract()
