#!/usr/bin/env python3
"""Build fresh Fullframe-vs-PTLW V2 identities without device access.

The five visible actions, A/B geometry, and payload identities are mechanical
copies of the sealed V1B design.  Every descriptor/action/contract identity is
new.  Admission is also bound to the independently sealed PON->POF qualifier
V2 success receipt; this module only freezes that evidence and never reads it.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1_pack as v1b  # noqa: E402


VARIANT_KEY = "L535_FACTORY_WHITE_PTLW_FULLFRAME_AB_V2"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_2026-08-26"
TEST_ID = "EC5-RUNTIME-LUT-PTLW-FULLFRAME-AB-V2"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2"
NVS_NAMESPACE = "rlpffab_v2"
NVS_KEY = "cursor_ab2"
ENV_NAME = "ec5_runtime_lut_ptlw_fullframe_ab_v2"
DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_DEVICE_V2"
IDENTITY_REVISION = "runtime-lut-ptlw-fullframe-ab-v2"
DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v2"
ENDPOINT_BASE = "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2"
PROFILE_ID = v1b.PROFILE_ID

MECHANICAL_SOURCE_V1_CONTRACT_ID = (
    "9e7414f483174cc74fa8adca9c1c2ea4c23c3250f84882969f34e87efb25a8fa"
)
MECHANICAL_SOURCE_V1B_CONTRACT_ID = (
    "e6e8802a3fd93f1f867c20f1e2013dc4ade410881b2ade46d1e1fb60d9821cb5"
)
MECHANICAL_SOURCE_V1B_ACTION_IDS = (
    "bd6b07ebd793837c5cc134531b474d01bc9d8ebb62807ffd5c49ae92d090907c",
    "eb3d8a9e5d2d0b7145c1e1054c080201e063d4bc888695454e1db797bee98b28",
    "0048aebdd000d3e632a8279c488759f63b5b3b4c156c443d63d0a1ee10efd072",
    "496980867ca16d703087c05f7863f6e344e4a2e025b70e63c4efd54ee2b92535",
    "2116066fb9263866f3e709ff586e811df0db79226366d713964736658e5a9e17",
)

WIDTH = v1b.WIDTH
HEIGHT = v1b.HEIGHT
CONTROLLER_WIDTH = v1b.CONTROLLER_WIDTH
FRAME_BYTES = v1b.FRAME_BYTES
CONTROLLER_DTM_BYTES = v1b.CONTROLLER_DTM_BYTES
WHITE_CODE = v1b.WHITE_CODE
BLUE_CODE = v1b.BLUE_CODE
WINDOW = v1b.WINDOW
CROPPED_DTM_BYTES = v1b.CROPPED_DTM_BYTES
PTLW_PAYLOAD = v1b.PTLW_PAYLOAD

PRELOAD_DTM_SHA256 = v1b.PRELOAD_DTM_SHA256
PRELOAD_DTM_FNV1A = v1b.PRELOAD_DTM_FNV1A
FULL_COMPOSITE_DTM_SHA256 = v1b.FULL_COMPOSITE_DTM_SHA256
FULL_COMPOSITE_DTM_FNV1A = v1b.FULL_COMPOSITE_DTM_FNV1A
CROPPED_DTM_SHA256 = v1b.CROPPED_DTM_SHA256
CROPPED_DTM_FNV1A = v1b.CROPPED_DTM_FNV1A
TREATMENT_A_COMBINED_DTM_SHA256 = v1b.TREATMENT_A_COMBINED_DTM_SHA256
TREATMENT_A_COMBINED_DTM_FNV1A = v1b.TREATMENT_A_COMBINED_DTM_FNV1A
TREATMENT_B_COMBINED_DTM_SHA256 = v1b.TREATMENT_B_COMBINED_DTM_SHA256
TREATMENT_B_COMBINED_DTM_FNV1A = v1b.TREATMENT_B_COMBINED_DTM_FNV1A
LOGICAL_FRAME_SHA256 = v1b.LOGICAL_FRAME_SHA256
LOGICAL_FRAME_FNV1A = v1b.LOGICAL_FRAME_FNV1A
WHITE_REFRESH_SEQUENCE = v1b.WHITE_REFRESH_SEQUENCE
COMMON_RUNTIME_REFRESH_SEQUENCE = v1b.COMMON_RUNTIME_REFRESH_SEQUENCE

QUALIFIER_V2_PREREQUISITE = {
    "schema": "mf1750-power-qualifier-pon-pof-no-drf-v2-prerequisite-v1",
    "firmware": {
        "bin": {
            "relative_path": (
                ".pio/build-power-qualifier-pon-pof-no-drf-v2/"
                "ec5_power_qualifier_pon_pof_no_drf_v2/firmware.bin"
            ),
            "bytes": 788_736,
            "sha256": (
                "0af84715f1e040883aa270fb365b1bd833e6fbf2192d57c8d06e67b56467fdec"
            ),
        },
        "elf": {
            "relative_path": (
                ".pio/build-power-qualifier-pon-pof-no-drf-v2/"
                "ec5_power_qualifier_pon_pof_no_drf_v2/firmware.elf"
            ),
            "bytes": 13_119_644,
            "sha256": (
                "5b4149b8952d1d1f5d19d7cac9928aa9cf53f4f16c7a0f94f66ae1b853fb7f4b"
            ),
        },
    },
    "identity": {
        "build_tag": "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2_2026-08-25",
        "test_id": "EC5-POWER-QUALIFIER-PON-POF-NO-DRF-V2",
        "campaign_id": "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2",
        "descriptor_id": (
            "aa2fedbb8db8c6c4706a0fe5300bafe9ef5a8265e7b91b8bc23712d725c5de30"
        ),
        "action_id": (
            "e6c73eb7ba9b6fd5b2af89cd51fe9422a5e34434f93379b53b9f2280025f1c6e"
        ),
        "contract_id": (
            "d1ae9cc592536a42ff5b611bb4580be25bc126087946a24f82a6cc0c3c04208f"
        ),
    },
    "boot_nonce": "abd7b455cbaf8671",
    "qualification_nonce": "a1b8192e130130d1",
    "evidence": {
        "diagnostic": {
            "relative_path": (
                ".test-output/hardware/"
                "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_20260825/"
                "j2-off-diagnostic.json"
            ),
            "bytes": 12_671,
            "sha256": (
                "b57dd4158bc23dc5e912c80b4cd2a0080a353c0ccc1fa549855187e1bef09b61"
            ),
            "canonical_sha256": (
                "cfe88f77ec2421018e902dbaedc32c3a75868f64ebb2a608c532abdb839c6558"
            ),
        },
        "result": {
            "relative_path": (
                ".test-output/hardware/"
                "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_20260825/"
                "power-probe.json"
            ),
            "bytes": 45_075,
            "sha256": (
                "7a1bc71821a1b0e919d63ef9ea7f9730873eb784e180ffa942cdf80aa3564435"
            ),
            "canonical_sha256": (
                "38c4e7e0677357558ef0a30961fbd29c8dccb293898b11f95d01ec4b5739f0d1"
            ),
        },
        "claim": {
            "relative_path": (
                ".test-output/hardware/"
                ".mf1750_power_qualifier_pon_pof_no_drf_v2_claims/"
                "e6c73eb7ba9b6fd5b2af89cd51fe9422a5e34434f93379b53b9f2280025f1c6e.json"
            ),
            "bytes": 1_092,
            "sha256": (
                "e7467daf95053e5faf8a5873e1f63c4c98a472aa4bbf1ec194c27d2b3ee04cf6"
            ),
            "canonical_sha256": (
                "f5a4d5c0fc650c896ef9ac06f1a125a9c7db746c5f32f1ae91ad1759448b6a76"
            ),
        },
        "attempt": {
            "relative_path": (
                ".test-output/hardware/"
                ".mf1750_power_qualifier_pon_pof_no_drf_v2_claims/"
                "e6c73eb7ba9b6fd5b2af89cd51fe9422a5e34434f93379b53b9f2280025f1c6e."
                "qualification-attempt.json"
            ),
            "bytes": 983,
            "sha256": (
                "c758ff547e8d5d22a5c897d328925b827d6257c3aee407ea3eb282b6d3b048a4"
            ),
            "canonical_sha256": (
                "c61b6c65aa535b91d0f7665ba0e2250d575cecb6e1308d44400b1b004106ab5d"
            ),
        },
        "reservation": {
            "relative_path": (
                ".test-output/hardware/"
                "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_20260825/"
                "power-probe.json.reserve"
            ),
            "bytes": 503,
            "sha256": (
                "cd2c147c0daff518f2ec4992e12235e3a18aab5b91d3d356a003a61b585266e8"
            ),
            "canonical_sha256": (
                "02f77920703c2ea4980dc3be2f28288f08f8cfe71b2686bda37754b8dfce992b"
            ),
        },
    },
    "required_facts": {
        "diagnostic": {
            "$.j2_confirmed_off": True,
            "$.network": {"get": 4, "post": 0},
            "$.probe_driver_calls": 0,
            "$.visible_refresh_requests": 0,
            "$.transcript[2].response.gpio.busy": 0,
        },
        "result": {
            "$.outcome": "complete_pass",
            "$.network.arm_post": 1,
            "$.network.execute_post": 1,
            "$.network.qualify_post": 1,
            "$.terminal_mismatches": [],
            "$.terminal_report.valid": True,
            "$.terminal_report.result": True,
            "$.terminal_report.terminal_state": "COMPLETE",
            "$.terminal_report.phase_name": "COMPLETE",
            "$.terminal_report.driver_called": True,
            "$.terminal_report.driver_call_count_for_action": 1,
            "$.terminal_report.total_driver_call_count": 1,
            "$.terminal_report.qualifier_call_count": 1,
            "$.terminal_report.probe_call_count": 1,
            "$.terminal_report.readiness.cs1.sample1.bytes": [1, 1, 4],
            "$.terminal_report.readiness.cs1.sample1.idle": True,
            "$.terminal_report.readiness.cs1.sample2.bytes": [1, 1, 4],
            "$.terminal_report.readiness.cs1.sample2.idle": True,
            "$.terminal_report.readiness.cs2.sample1.bytes": [1, 1, 4],
            "$.terminal_report.readiness.cs2.sample1.idle": True,
            "$.terminal_report.readiness.cs2.sample2.bytes": [1, 1, 4],
            "$.terminal_report.readiness.cs2.sample2.idle": True,
            "$.terminal_report.readiness.cs1.stable": True,
            "$.terminal_report.readiness.cs1.exact_010104": True,
            "$.terminal_report.readiness.cs2.stable": True,
            "$.terminal_report.readiness.cs2.exact_010104": True,
            "$.terminal_report.readiness.revision_command_trace": [
                112,
                112,
                112,
                112,
            ],
            "$.terminal_report.readiness.all_revision_samples_exact_010104": True,
            "$.terminal_report.readiness.valid": True,
            "$.terminal_report.readiness.qualified": True,
            "$.terminal_report.readiness.failure_stage": "none",
            "$.terminal_report.readiness.entry_busy": 1,
            "$.terminal_report.readiness.reset_count": 5,
            "$.terminal_report.readiness.revision_read_count": 4,
            "$.terminal_report.readiness.final_busy": 1,
            "$.terminal_report.readiness.final_high_stable_ms": 50,
            "$.terminal_report.readiness.final_gpio": {
                "cs1": 1,
                "cs2": 1,
                "dc": 0,
                "mosi": 0,
                "rst": 1,
                "sck": 0,
            },
            "$.terminal_report.probe.pon_gate_entry": 1,
            "$.terminal_report.probe.pof_gate_entry": 1,
            "$.terminal_report.probe.valid": True,
            "$.terminal_report.probe.sequence_ok": True,
            "$.terminal_report.probe.wait_timeout": False,
            "$.terminal_report.probe.busy_assertion_missing": False,
            "$.terminal_report.probe.pre_command_idle_failure": False,
            "$.terminal_report.probe.pre_command_busy_stage": "none",
            "$.terminal_report.probe.timeout_stage": "none",
            "$.terminal_report.probe.busy_missing_stage": "none",
            "$.terminal_report.probe.failure_stage": "none",
            "$.terminal_report.probe.pon_busy_seen": True,
            "$.terminal_report.probe.pon_idle_completed": True,
            "$.terminal_report.probe.pof_busy_seen": True,
            "$.terminal_report.probe.pof_idle_completed": True,
            "$.terminal_report.probe.pon_ms": 180,
            "$.terminal_report.probe.pof_ms": 210,
            "$.terminal_report.probe.post_psr_command_sent": True,
            "$.terminal_report.probe.post_psr_payload_hex": "4f6e",
            "$.terminal_report.probe.command_counts": {
                "command_0x86": 0,
                "drf": 0,
                "dtm": 0,
                "lut": 0,
                "pof": 1,
                "pon": 1,
                "ptlw": 0,
                "visible_refresh_requests": 0,
            },
            "$.terminal_report.probe.forbidden_commands": {
                "command_0x86": False,
                "drf": False,
                "dtm": False,
                "lut": False,
                "ptlw": False,
            },
            "$.terminal_report.probe.wire_event_count": 58,
            "$.terminal_report.probe.wire_fnv1a": 3_240_907_477,
            "$.terminal_report.probe.safe_finish.busy_before_pins_low": 1,
            "$.terminal_report.probe.safe_finish.busy_after_pins_low": 1,
            "$.terminal_report.probe.safe_finish.busy_after_5ms": 1,
            "$.terminal_report.probe.safe_finish.final_gpio": {
                "busy": 1,
                "cs1": 0,
                "cs2": 0,
                "dc": 0,
                "mosi": 0,
                "rst": 0,
                "sck": 0,
            },
        },
        "cross_file": {
            "same_boot_nonce": True,
            "same_qualifier_identity": True,
            "initial_raw_busy": 1,
            "claim_and_attempt_permanently_consumed": True,
        },
        "claim": {
            "$.state": "claimed_after_qualification_before_arm",
            "$.initial_busy": 1,
            "$.qualified_busy": 1,
            "$.no_retry": True,
            "$.no_recovery": True,
            "$.no_autochain": True,
        },
        "attempt": {
            "$.state": "reserved_before_qualify_post",
            "$.initial_busy": 1,
            "$.no_automatic_retry": True,
        },
        "reservation": {
            "$.kind": (
                "mf1750-power-qualifier-pon-pof-no-drf-v2-output-reservation"
            ),
        },
    },
}
QUALIFIER_V2_BUNDLE_ID = identity.sha256(
    identity.canonical(QUALIFIER_V2_PREREQUISITE)
)

PER_ACTION_READINESS_QUALIFICATION = {
    "after_durable_execute_consumed": True,
    "required_before_panel_payload_or_power_commands": True,
    "driver_call_count_before_qualification": 0,
    "reset_before_each_revision_sample": True,
    "revision_sample_order": ["CS1", "CS1", "CS2", "CS2"],
    "revision_read_count": 4,
    "reset_count_including_final_posture_reset": 5,
    "all_samples_exact": [1, 1, 4],
    "final_posture_reset": True,
    "final_busy_high_stable_ms": 50,
    "qualification_success_precedes_driver_call_increment": True,
    "failure_before_visible_refresh_is_fault_locked": True,
    "failure_command_counts": {
        "command_0x86": 0,
        "lut": 0,
        "dtm": 0,
        "ptlw": 0,
        "pon": 0,
        "pof": 0,
        "drf": 0,
        "visible_refresh_requests": 0,
    },
}

BUSY_ADMISSION_CONTRACT = {
    "device_gate_order": ["ARM", "EXECUTE", "DISPATCH"],
    "snapshot_fields": [
        "captured",
        "raw_busy",
        "allowed",
        "raw1_direct",
        "raw0_same_boot_prior_complete_ram_eligibility_used",
        "late_pof_sleep_low_eligible_before_gate",
    ],
    "uncaptured_snapshot": {
        "captured": False,
        "raw_busy": None,
        "allowed": False,
        "raw1_direct": False,
        "raw0_same_boot_prior_complete_ram_eligibility_used": False,
        "late_pof_sleep_low_eligible_before_gate": False,
    },
    "fresh_ordinal_1_requires_raw1_at_all_three_gates": True,
    "fresh_ordinal_1_raw0_eligibility_forbidden": True,
    "later_raw0_requires_same_boot_prior_complete_ram_eligibility": True,
    "dispatch_records_eligibility_before_consuming_it": True,
    "qualification_readiness_entry_busy_is_independent": True,
}


def _descriptor(item: Mapping[str, Any]) -> str:
    value = {
        "schema": "mf1750-runtime-lut-ptlw-fullframe-ab-descriptor-v2",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
        "per_action_readiness_qualification": deepcopy(
            PER_ACTION_READINESS_QUALIFICATION
        ),
        "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
        **item,
    }
    return identity.sha256(identity.canonical(value))


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return identity.sha256(
        (
            "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_ACTION_V2|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def _fresh_actions(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for old in source:
        item = deepcopy(old)
        item.pop("descriptor_id")
        item.pop("action_id")
        descriptor_id = _descriptor(item)
        item["descriptor_id"] = descriptor_id
        item["action_id"] = _action_id(item["ordinal"], descriptor_id)
        result.append(item)
    return result


def _action_summary(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": item["ordinal"],
            "role": item["role"],
            "palette_source": item["palette_source"],
            "dtm_transport": item["dtm_transport"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
        }
        for item in actions
    ]


def _validate_mechanical_source(old: Mapping[str, Any]) -> None:
    expected_payloads = {
        "window": {
            "x": 176,
            "y": 240,
            "width": 160,
            "height": 120,
            "cs1_code": 5,
            "cs2_code": 5,
        },
        "ptlw_payload_hex": "00b0014f00f0016701",
        "preload_sha256": (
            "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd"
        ),
        "full_composite_sha256": (
            "352e61d15eb963fe2e1b37a07664be885ec6c8a0e1383bb3e96869fe517ca3ed"
        ),
        "cropped_sha256": (
            "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3"
        ),
        "logical_frame_sha256": (
            "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576"
        ),
    }
    observed_actions = tuple(item["action_id"] for item in old["actions"])
    observed_payloads = {
        "window": old["actions"][1]["target_window"],
        "ptlw_payload_hex": old["actions"][3]["ptlw_payload_hex"],
        "preload_sha256": old["actions"][1]["prestage_dtm"]["sha256"],
        "full_composite_sha256": old["actions"][1]["target_dtm"]["sha256"],
        "cropped_sha256": old["actions"][3]["target_dtm"]["sha256"],
        "logical_frame_sha256": old["actions"][1]["frame"]["sha256"],
    }
    if old["contract_id"] != MECHANICAL_SOURCE_V1B_CONTRACT_ID:
        raise RuntimeError("sealed V1B mechanical contract drifted")
    if observed_actions != MECHANICAL_SOURCE_V1B_ACTION_IDS:
        raise RuntimeError("sealed V1B mechanical action identities drifted")
    if observed_payloads != expected_payloads:
        raise RuntimeError("sealed V1B mechanical payloads drifted")


def build_report() -> dict[str, Any]:
    """Return the five fresh identities and their frozen prerequisite."""

    old = v1b.build_report()
    _validate_mechanical_source(old)
    actions = _fresh_actions(old["actions"])
    contract = deepcopy(old["contract"])
    contract.update(
        {
            "schema": "mf1750-runtime-lut-ptlw-fullframe-ab-contract-v2",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "campaign_id": CAMPAIGN_ID,
            "nvs_namespace": NVS_NAMESPACE,
            "nvs_key": NVS_KEY,
            "actions": _action_summary(actions),
            "mechanical_source": {
                "variant": old["variant_key"],
                "mechanically_reused": [
                    "five_action_roles_and_order",
                    "a_b_geometry",
                    "ptlw_payload",
                    "frame_and_dtm_payload_identities",
                    "refresh_sequences",
                ],
                "replay_or_resume": False,
            },
            "supersedes_campaign_contract_ids": [
                MECHANICAL_SOURCE_V1_CONTRACT_ID,
                MECHANICAL_SOURCE_V1B_CONTRACT_ID,
            ],
            "supersedes_action_ids_by_ordinal": {
                str(item["ordinal"]): item["action_id"] for item in old["actions"]
            },
            "legacy_action_identity_collision": {
                "v1_and_v1b_shared_action_ids": True,
                "both_campaign_contracts_are_explicitly_superseded": True,
            },
            "qualifier_v2_prerequisite": deepcopy(QUALIFIER_V2_PREREQUISITE),
            "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
            "busy_qualification": {
                "raw_idle_level": 1,
                "ordinal_1_raw_levels_accepted": [1],
                "fresh_ordinal_1_requires_raw_busy_high": True,
                "later_ordinal_raw_levels_accepted": [0, 1],
                "late_low_is_never_treated_as_idle": True,
                "late_low_requires_same_boot_prior_complete": True,
                "late_low_requires_prior_safe_finish_high": True,
                "late_low_requires_ram_only_firmware_eligibility": True,
                "firmware_arm_required": True,
                "firmware_execute_required": True,
                "firmware_dispatch_required": True,
                "unqualified_busy_zero_accepted": False,
            },
            "per_action_readiness_qualification": deepcopy(
                PER_ACTION_READINESS_QUALIFICATION
            ),
            "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
            "autochain": False,
            "retry": False,
            "automatic_recovery": False,
        }
    )
    contract_id = identity.sha256(identity.canonical(contract))
    return {
        "schema_version": 2,
        "kind": "mf1750-runtime-lut-ptlw-fullframe-ab-v2-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile_id": PROFILE_ID,
        "contract_id": contract_id,
        "actions": actions,
        "contract": contract,
    }


_FROZEN_CONTRACT_ID = (
    "8ca2c5df3f293a237a299a06ca48d643c154285dcfb4e22192745dfbc2267111"
)
_FROZEN_DESCRIPTOR_IDS = (
    "dfb473d1b8c9718b5b5ed01998e032cc600298689f227e5465031e79b3ae7947",
    "71ac9664e43d630243fc0675e1b6a41ad3fea90ec789d86a6b607934f7c70f0b",
    "8f8e72b28dfb3d841ba948e11b07bce1e16b531cc2e38c10bcf70cccac58db09",
    "cd758ace217487557d8edf193c5b1e547a040f77eab954cfc6f3bd37760f8767",
    "4ccbb0ab883826dc36a6bb002d521a24e0e1cd68bbebfe237e4d6f037c86b73a",
)
_FROZEN_ACTION_IDS = (
    "0abe5067ebcc7771684a148da4eb8b1e8cf202dbbea63961e48d7436965f5359",
    "4fd836603acaf06d28985b96049fa3b0753c02373b35dbc6ebcabc5d12ee6ad1",
    "08da585051415b36c628e49c946e13a2a463213d0e251214f21ebc17e922db30",
    "15bf776e63b37cedd86a5d92e0886cd635de03aa4db6d8e679964bd17f9b57fb",
    "88e5a34985f651c01243c78698b267710efa5e77a191d28d2f4c1f89e0d23682",
)

_REPORT = build_report()
_DERIVED_DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in _REPORT["actions"]
)
_DERIVED_ACTION_IDS = tuple(item["action_id"] for item in _REPORT["actions"])
if (
    _REPORT["contract_id"] != _FROZEN_CONTRACT_ID
    or _DERIVED_DESCRIPTOR_IDS != _FROZEN_DESCRIPTOR_IDS
    or _DERIVED_ACTION_IDS != _FROZEN_ACTION_IDS
):
    raise RuntimeError("Fullframe/PTLW V2 frozen canonical identities drifted")
CONTRACT_ID = _FROZEN_CONTRACT_ID
DESCRIPTOR_IDS = _FROZEN_DESCRIPTOR_IDS
ACTION_IDS = _FROZEN_ACTION_IDS


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
