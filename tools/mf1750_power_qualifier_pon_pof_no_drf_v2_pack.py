#!/usr/bin/env python3
"""Freeze the V2 per-sample-reset PON/POF qualification contract."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as v1


ENV_NAME = "ec5_power_qualifier_pon_pof_no_drf_v2"
VARIANT_KEY = "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2"
BUILD_TAG = "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2_2026-08-25"
TEST_ID = "EC5-POWER-QUALIFIER-PON-POF-NO-DRF-V2"
CAMPAIGN_ID = "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2"
DEVICE_API_VERSION = "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_DEVICE_V2"
IDENTITY_REVISION = "power-qualifier-pon-pof-no-drf-v2"
CLASSIFICATION = v1.CLASSIFICATION
NVS_NAMESPACE = "epdponpof_v2"
NVS_KEY = "cursor_pp2"
PROBE_SPI_HZ = v1.PROBE_SPI_HZ
EXPECTED_REVISION = [0x01, 0x01, 0x04]
FORBIDDEN_COMMANDS = v1.FORBIDDEN_COMMANDS
PROBE_SEQUENCE = v1.PROBE_SEQUENCE
FAILURE_CLEANUP_MATRIX = deepcopy(v1.FAILURE_CLEANUP_MATRIX)
PROBE_COMMAND_TRACE = v1.PROBE_COMMAND_TRACE
PROBE_WIRE_EVENT_COUNT = v1.PROBE_WIRE_EVENT_COUNT
PROBE_WIRE_FNV1A = v1.PROBE_WIRE_FNV1A

RESET_QUALIFICATION_SEQUENCE = (
    "CS1_SAMPLE1_RESET_LOW40_HIGH40_LOW40_HIGH_THEN_REV_0X70_READ",
    "CS1_SAMPLE2_RESET_LOW40_HIGH40_LOW40_HIGH_THEN_REV_0X70_READ",
    "CS2_SAMPLE1_RESET_LOW40_HIGH40_LOW40_HIGH_THEN_REV_0X70_READ",
    "CS2_SAMPLE2_RESET_LOW40_HIGH40_LOW40_HIGH_THEN_REV_0X70_READ",
    "ALL_FOUR_REVISION_SAMPLES_EXACT_01_01_04",
    "FINAL_RESET_LOW40_HIGH40_LOW40_HIGH",
    "BUSY_STABLE_HIGH_50MS",
    "QUALIFIED_POSTURE_RST_CS1_CS2_HIGH_SCK_DC_MOSI_LOW",
)

QUALIFICATION_ALLOWED_SEQUENCE = (
    {"stage": "qualification", "sample": "CS1_SAMPLE1", "operation": "reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "sample": "CS1_SAMPLE1", "controller": "CS1", "command": "0x70", "operation": "read_revision", "expected_hex": "010104"},
    {"stage": "qualification", "sample": "CS1_SAMPLE2", "operation": "reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "sample": "CS1_SAMPLE2", "controller": "CS1", "command": "0x70", "operation": "read_revision", "expected_hex": "010104"},
    {"stage": "qualification", "sample": "CS2_SAMPLE1", "operation": "reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "sample": "CS2_SAMPLE1", "controller": "CS2", "command": "0x70", "operation": "read_revision", "expected_hex": "010104"},
    {"stage": "qualification", "sample": "CS2_SAMPLE2", "operation": "reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "sample": "CS2_SAMPLE2", "controller": "CS2", "command": "0x70", "operation": "read_revision", "expected_hex": "010104"},
    {"stage": "qualification", "sample": "FINAL_POSTURE", "operation": "reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "operation": "success_posture", "busy": 1, "stable_high_ms": 50, "rst": 1, "cs1": 1, "cs2": 1, "sck": 0, "dc": 0, "mosi": 0},
)
ALLOWED_COMMAND_PAYLOAD_SEQUENCE = QUALIFICATION_ALLOWED_SEQUENCE + tuple(
    deepcopy(item)
    for item in v1.ALLOWED_COMMAND_PAYLOAD_SEQUENCE
    if item.get("stage") != "qualification"
)


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _descriptor_id(descriptor: Mapping[str, Any]) -> str:
    return sha256(canonical(descriptor))


def _action_id(descriptor_id: str) -> str:
    return sha256(
        (
            "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_ACTION_V2|"
            f"{CAMPAIGN_ID}|1|{descriptor_id}"
        ).encode("ascii")
    )


def build_report() -> dict[str, Any]:
    prerequisite = {
        "sequence": list(RESET_QUALIFICATION_SEQUENCE),
        "reset_count": 5,
        "reset_before_each_revision_sample": True,
        "final_posture_reset": True,
        "single_variable_change": "PER_SAMPLE_RESET_ONLY",
        "exact_historical_transaction_reproduction": False,
        "legacy_mosi_high_before_reset_restored": False,
        "legacy_post_reset_tail_2us_restored": False,
        "segmented_cs_framing_changed": False,
        "expected_revision_bytes": list(EXPECTED_REVISION),
        "all_four_samples_exact_required": True,
        "raw_busy_zero_may_directly_arm": False,
        "qualified_busy_level": 1,
        "qualified_busy_stable_ms": 50,
        "qualification_nonce_required": True,
        "same_boot_required": True,
        "fresh_requires_missing_nvs_key": True,
        "nonterminal_phase_seen_at_boot": "FAULT_NO_RESUME_NO_RETRY",
        "zero_revision_result": "STOP_BEFORE_PON_AND_DEFER_LEGACY_TRANSACTION_TO_V3",
    }
    descriptor = {
        "schema": "mf1750-power-qualifier-pon-pof-no-drf-descriptor-v2",
        "variant": VARIANT_KEY,
        "ordinal": 1,
        "role": "PON_POF_NO_DRF_POWER_PATH_PROBE",
        "branch": "PER_SAMPLE_RESET_EXACT_REV_READINESS_THEN_PON_THEN_POF_NO_DRF",
        "prerequisite": prerequisite,
        "probe_sequence": list(PROBE_SEQUENCE),
        "probe_spi_hz": PROBE_SPI_HZ,
        "pon_count": 1,
        "pof_count": 1,
        "drf_count": 0,
        "dtm_bytes": 0,
        "lut_bytes": 0,
        "ptlw_writes": 0,
        "visible_refresh_requests": 0,
        "allowed_command_payload_sequence": [
            deepcopy(item) for item in ALLOWED_COMMAND_PAYLOAD_SEQUENCE
        ],
        "probe_wire_event_count": PROBE_WIRE_EVENT_COUNT,
        "probe_wire_fnv1a": PROBE_WIRE_FNV1A,
        "failure_cleanup_matrix": deepcopy(FAILURE_CLEANUP_MATRIX),
        "forbidden_commands": list(FORBIDDEN_COMMANDS),
    }
    descriptor_id = _descriptor_id(descriptor)
    action = {
        "ordinal": 1,
        "descriptor_id": descriptor_id,
        "action_id": _action_id(descriptor_id),
        "prior_static_action_id": v1.ACTION_ID,
        "role": descriptor["role"],
        "round": 1,
        "branch": descriptor["branch"],
    }
    contract = {
        "schema": "mf1750-power-qualifier-pon-pof-no-drf-contract-v2",
        "variant": VARIANT_KEY,
        "environment": ENV_NAME,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "classification": CLASSIFICATION,
        "supersedes_fault_locked_action_id": v1.ACTION_ID,
        "residual_differences_from_historical_helper": {
            "mosi_high_before_reset": "NOT_RESTORED_IN_V2",
            "post_reset_tail_2us": "NOT_RESTORED_IN_V2",
            "classification": "V2_IS_PER_SAMPLE_RESET_ONLY_NOT_EXACT_LEGACY_TRANSACTION",
            "v2_zero_revision_disposition": "STOP_BEFORE_PON_AND_CREATE_FRESH_V3",
        },
        "nvs": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "terminal_next_ordinal": 2,
            "missing_key_is_fresh_only": True,
            "nonterminal_phase_on_boot": "FAULT_NO_RESUME_NO_RETRY",
            "v1_namespace_and_key_must_not_be_erased": True,
        },
        "action_count": 1,
        "actions": [action],
        "reset_readiness_qualification": prerequisite,
        "probe": {
            "sequence": list(PROBE_SEQUENCE),
            "spi_hz": PROBE_SPI_HZ,
            "exactly_one_pon": True,
            "exactly_one_pof": True,
            "drf": False,
            "dtm": False,
            "runtime_lut": False,
            "ptlw": False,
            "visible_refresh": False,
            "exact_probe_command_trace": list(PROBE_COMMAND_TRACE),
            "wire_event_count": PROBE_WIRE_EVENT_COUNT,
            "wire_fnv1a": PROBE_WIRE_FNV1A,
            "failure_cleanup_matrix": deepcopy(FAILURE_CLEANUP_MATRIX),
        },
        "forbidden_commands": list(FORBIDDEN_COMMANDS),
        "allowed_command_payload_sequence": [
            deepcopy(item) for item in ALLOWED_COMMAND_PAYLOAD_SEQUENCE
        ],
        "transport": {
            "http_direct_no_proxy": True,
            "j2_off_diagnostic_gets": 4,
            "j2_off_diagnostic_posts": 0,
            "live_prequalification_gets": 4,
            "reset_qualification_posts": 1,
            "postqualification_gets": 4,
            "arm_posts": 1,
            "execute_posts": 1,
        },
        "safety": {
            "startup_action": False,
            "automatic_execute": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
            "mid_refresh_power_cut": False,
            "raw_busy_zero_direct_arm": False,
            "permanent_claim_before_arm": True,
        },
    }
    contract_id = sha256(canonical(contract))
    return {
        "schema_version": 2,
        "kind": "mf1750-power-qualifier-pon-pof-no-drf-v2-offline-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "environment": ENV_NAME,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "descriptor": descriptor,
        "descriptor_canonical_sha256": descriptor_id,
        "actions": [action],
        "contract": contract,
        "contract_canonical_sha256": contract_id,
        "contract_id": contract_id,
    }


_IDENTITY_REPORT = build_report()
DESCRIPTOR_ID = _IDENTITY_REPORT["actions"][0]["descriptor_id"]
ACTION_ID = _IDENTITY_REPORT["actions"][0]["action_id"]
CONTRACT_ID = _IDENTITY_REPORT["contract_id"]
assert _IDENTITY_REPORT["descriptor_canonical_sha256"] == DESCRIPTOR_ID
assert _action_id(DESCRIPTOR_ID) == ACTION_ID
assert _IDENTITY_REPORT["contract_canonical_sha256"] == CONTRACT_ID


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
