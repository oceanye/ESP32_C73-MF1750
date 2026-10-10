#!/usr/bin/env python3
"""Freeze the one-action PON/POF, no-DRF power-qualification contract.

This module is intentionally offline-only.  It neither imports a transport
client nor exposes serial, relay, reset, flashing, or display operations.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


ENV_NAME = "ec5_power_qualifier_pon_pof_no_drf_v1"
VARIANT_KEY = "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V1"
BUILD_TAG = "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V1_2026-08-25"
TEST_ID = "EC5-POWER-QUALIFIER-PON-POF-NO-DRF-V1"
CAMPAIGN_ID = "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V1"
DEVICE_API_VERSION = "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_DEVICE_V1"
IDENTITY_REVISION = "power-qualifier-pon-pof-no-drf-v1"
CLASSIFICATION = "SUPERVISED_POWER_PATH_QUALIFIER_PON_POF_NO_DRF"
NVS_NAMESPACE = "epdponpof_v1"
NVS_KEY = "cursor_pp1"
PROBE_SPI_HZ = 1_000_000

RESET_QUALIFICATION_SEQUENCE = (
    "ONE_SHARED_RESET_LOW40_HIGH40_LOW40_HIGH",
    "BUSY_IDLE_HIGH_COMPLETE_GATE",
    "CS1_REV_0X70_READ_SAMPLE_1",
    "CS1_REV_0X70_READ_SAMPLE_2_WITHOUT_INTERMEDIATE_RESET",
    "CS2_REV_0X70_READ_SAMPLE_1",
    "CS2_REV_0X70_READ_SAMPLE_2_WITHOUT_INTERMEDIATE_RESET",
    "EACH_CONTROLLER_STABLE_AND_NONTRIVIAL",
    "BUSY_STABLE_HIGH",
    "QUALIFIED_POSTURE_RST_CS1_CS2_HIGH_SCK_DC_MOSI_LOW",
)
PROBE_SEQUENCE = (
    "PON_BUSY_ASSERT_THEN_IDLE_COMPLETE_60S_GATE",
    "POF_00_BUSY_ASSERT_THEN_IDLE_COMPLETE_60S_GATE",
)
FAILURE_CLEANUP_MATRIX = {
    "pon_not_sent": {
        "pof_cleanup_count": 0,
        "reason": "NO_HIGH_VOLTAGE_PATH_WAS_ENTERED",
    },
    "pon_sent_pof_not_sent": {
        "pof_cleanup_count": 1,
        "reason": "ONE_FAIL_SAFE_POF_IS_REQUIRED",
    },
    "pof_sent": {
        "additional_pof_cleanup_count": 0,
        "maximum_total_pof_count": 1,
        "reason": "A_SECOND_POF_IS_FORBIDDEN",
    },
}
FORBIDDEN_COMMANDS = (
    "DTM_0X10",
    "DTM_0X11",
    "DRF_0X12",
    "DTM_0X13",
    "LUT_R20",
    "LUT_R21",
    "PTLW_0X83",
    "COMMAND_0X86",
)

# The qualifier reads REV only.  The probe retains the already validated
# controller initialization because PON would otherwise not exercise the same
# high-voltage path as a real display operation.  There is deliberately no
# DTM, LUT, PTLW, or DRF command in this allow-list.
ALLOWED_COMMAND_PAYLOAD_SEQUENCE = (
    {"stage": "qualification", "operation": "shared_reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "qualification", "controller": "CS1", "command": "0x70", "operation": "read_revision", "repeat": 2},
    {"stage": "qualification", "controller": "CS2", "command": "0x70", "operation": "read_revision", "repeat": 2},
    {"stage": "qualification", "operation": "success_posture", "busy": 1, "rst": 1, "cs1": 1, "cs2": 1, "sck": 0, "dc": 0, "mosi": 0},
    {"stage": "probe_init", "operation": "shared_reset", "count": 1, "timing_ms": [40, 40, 40]},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0xAA", "payload_hex": "495520080918"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x01", "payload_hex": "3f", "name": "PWR"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x00", "payload_hex": "5f69", "name": "PSR"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x05", "payload_hex": "401f1f2c", "name": "BTST1"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x08", "payload_hex": "6f1f1f22", "name": "BTST3"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x06", "payload_hex": "6f1f1717", "name": "BTST2"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x03", "payload_hex": "00540044", "name": "POFS"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x60", "payload_hex": "0200", "name": "TCON"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x30", "payload_hex": "08", "name": "PLL"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x50", "payload_hex": "3f", "name": "CDI"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x61", "payload_hex": "02000258", "name": "TRES"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0xE3", "payload_hex": "2f", "name": "PWS"},
    {"stage": "probe_init", "controller": "CS1+CS2", "command": "0x84", "payload_hex": "01", "name": "T_VDCS"},
    {"stage": "probe_init", "controller": "CS1", "command": "0xE0", "payload_hex": "01", "name": "CCSET"},
    {"stage": "probe_init", "controller": "CS2", "command": "0xE0", "payload_hex": "01", "name": "CCSET"},
    {"stage": "probe", "operation": "explicit_dual_select", "before": "PON", "cs1": True, "cs2": True},
    {"stage": "probe", "controller": "CS1+CS2", "command": "0x04", "payload_hex": "", "name": "PON", "busy_gate": "assert_then_idle"},
    {"stage": "probe", "operation": "explicit_dual_select", "before": "POF", "cs1": True, "cs2": True},
    {"stage": "probe", "controller": "CS1+CS2", "command": "0x02", "payload_hex": "00", "name": "POF", "busy_gate": "assert_then_idle"},
    {"stage": "post_probe", "operation": "delay_ms", "value": 6000},
    {"stage": "post_probe", "operation": "explicit_dual_select", "before": "PSR", "cs1": True, "cs2": True},
    {"stage": "post_probe", "controller": "CS1+CS2", "command": "0x00", "payload_hex": "4f6e", "name": "PSR"},
    {"stage": "post_probe", "operation": "wait_idle"},
    {"stage": "post_probe", "operation": "delay_ms", "value": 1000},
    {"stage": "safe_finish", "operation": "panel_outputs_low"},
)

PROBE_COMMAND_TRACE = (
    0xAA, 0x01, 0x00, 0x05, 0x08, 0x06, 0x03, 0x60, 0x30,
    0x50, 0x61, 0xE3, 0x84, 0xE0, 0xE0, 0x04, 0x02, 0x00,
)


def _probe_wire_identity() -> tuple[int, int]:
    """FNV-1a over exact write events: controller-mask, DCX, value."""

    fnv = 0x811C9DC5
    count = 0
    masks = {"CS1": 1, "CS2": 2, "CS1+CS2": 3}
    for item in ALLOWED_COMMAND_PAYLOAD_SEQUENCE:
        if item.get("stage") == "qualification" or "command" not in item:
            continue
        mask = masks[str(item["controller"])]
        command = int(str(item["command"]), 16)
        events = [(mask, 0, command)]
        payload = bytes.fromhex(str(item.get("payload_hex", "")))
        events.extend((mask, 1, byte) for byte in payload)
        for event in events:
            for byte in event:
                fnv = ((fnv ^ byte) * 0x01000193) & 0xFFFFFFFF
            count += 1
    return count, fnv


PROBE_WIRE_EVENT_COUNT, PROBE_WIRE_FNV1A = _probe_wire_identity()


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
            "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_ACTION_V1|"
            f"{CAMPAIGN_ID}|1|{descriptor_id}"
        ).encode("ascii")
    )


def build_report() -> dict[str, Any]:
    """Return deterministic identities for the non-visible one-shot probe."""

    descriptor = {
        "schema": "mf1750-power-qualifier-pon-pof-no-drf-descriptor-v1",
        "variant": VARIANT_KEY,
        "ordinal": 1,
        "role": "PON_POF_NO_DRF_POWER_PATH_PROBE",
        "branch": "RESET_READINESS_THEN_PON_THEN_POF_NO_DRF",
        "prerequisite": {
            "sequence": list(RESET_QUALIFICATION_SEQUENCE),
            "raw_busy_zero_may_directly_arm": False,
            "qualified_busy_level": 1,
            "qualification_nonce_required": True,
            "same_boot_required": True,
            "fresh_requires_missing_nvs_key": True,
            "nonterminal_phase_seen_at_boot": "FAULT_NO_RESUME_NO_RETRY",
        },
        "probe_sequence": list(PROBE_SEQUENCE),
        "probe_spi_hz": PROBE_SPI_HZ,
        "pon_count": 1,
        "pof_count": 1,
        "drf_count": 0,
        "dtm_bytes": 0,
        "lut_bytes": 0,
        "ptlw_writes": 0,
        "visible_refresh_requests": 0,
        "allowed_command_payload_sequence": [dict(item) for item in ALLOWED_COMMAND_PAYLOAD_SEQUENCE],
        "probe_wire_event_count": PROBE_WIRE_EVENT_COUNT,
        "probe_wire_fnv1a": PROBE_WIRE_FNV1A,
        "failure_cleanup_matrix": deepcopy(FAILURE_CLEANUP_MATRIX),
        "forbidden_commands": list(FORBIDDEN_COMMANDS),
    }
    descriptor_canonical_sha256 = _descriptor_id(descriptor)
    descriptor_id = descriptor_canonical_sha256
    action = {
        "ordinal": 1,
        "descriptor_id": descriptor_id,
        "action_id": _action_id(descriptor_id),
        "prior_static_action_id": None,
        "role": descriptor["role"],
        "round": 1,
        "branch": descriptor["branch"],
    }
    contract = {
        "schema": "mf1750-power-qualifier-pon-pof-no-drf-contract-v1",
        "variant": VARIANT_KEY,
        "environment": ENV_NAME,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "classification": CLASSIFICATION,
        "nvs": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "terminal_next_ordinal": 2,
            "missing_key_is_fresh_only": True,
            "nonterminal_phase_on_boot": "FAULT_NO_RESUME_NO_RETRY",
        },
        "action_count": 1,
        "actions": [action],
        "reset_readiness_qualification": descriptor["prerequisite"],
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
        "allowed_command_payload_sequence": [dict(item) for item in ALLOWED_COMMAND_PAYLOAD_SEQUENCE],
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
    return {
        "schema_version": 1,
        "kind": "mf1750-power-qualifier-pon-pof-no-drf-v1-offline-pack",
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
        "descriptor_canonical_sha256": descriptor_canonical_sha256,
        "actions": [action],
        "contract": contract,
        "contract_canonical_sha256": sha256(canonical(contract)),
        "contract_id": sha256(canonical(contract)),
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
