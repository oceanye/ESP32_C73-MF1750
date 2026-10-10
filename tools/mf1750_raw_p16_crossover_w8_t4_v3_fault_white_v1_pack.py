#!/usr/bin/env python3
"""Offline identities for the fresh W8 white containment after T4 V3 FAULT."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as source,
)
from tools import mf1750_raw_p16_crossover_t4_v3_terminal_salvage_once as salvage  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as w5,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack as w6,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_pack as w7,
)


class W8PackError(RuntimeError):
    """Raised when the W8 fault authority or fresh identity differs."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = "w8-after-t4-successor-v3-fault-white-v1"
    suffix: str = "W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE"
    nvs_namespace: str = "p16w8t4f_v1"
    nvs_key: str = "used_w8t4f"

    @property
    def build_tag(self) -> str:
        return "MF1750_EC5_RAW_P16_CROSSOVER_W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE_V1_2026-08-31"

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-W8-AFTER-T4-V3-FAULT-WHITE-V1"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_W8_AFTER_T4_SUCCESSOR_V3_FAULT_WHITE_V1"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-w8-after-t4-successor-v3-fault-white-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_w8t4f_w1"

    @property
    def build_root(self) -> str:
        return "b-w8t4f-w1"


STAGE = "w8-after-t4-successor-v3-fault-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-w8-t4-v3-fault-white-v1"
CLASSIFICATION = "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W8_AFTER_T4_V3_FAULT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FAULT_BOUND_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FAULT_BOUND_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = legacy.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = legacy.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = legacy.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = legacy.FACTORY_WHITE_DTM_FNV1A

# Filled only after a compile-only build is independently re-read.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_008,
        "bin_sha256": "a9c6103322ed0b348befeb2a1c6743c7b1a007debda63454873f812ddb89b658",
        "elf_bytes": 13_214_968,
        "elf_sha256": "031c46f47ab4a0f26bb7f8361cb45023c0d5db91d5de775db7d9a261c3ed91ec",
    }
}

SOURCE_FAILURE_BINDING = {
    "path": str(salvage.SOURCE_FAILURE),
    "bytes": 43_486,
    "file_sha256": "3efd366a3da763ce2dfaa144f9a15debea0c31826025808772982d668932d4dc",
    "canonical_integrity_sha256": "7d418afd3651a22f3f19b3471fe973c08d0b8a21bd399a6a18fb8a49b7ffc99e",
    "outcome": "terminal_report_read_error",
}
CLAIM_BINDING = {
    "path": str(salvage.CLAIM_FILE),
    "bytes": 4_178,
    "file_sha256": "e6fa56a132e65733e2987b3bac9e98bead4ee2098954d11e95c6d7201676499e",
    "canonical_integrity_sha256": "d8a0b9b6dc0bf42cfc58c5ae3a1383d2e748efde5c1835128fd67f42b48e60ba",
}
RAW_SALVAGE_BINDING = {
    "path": str(salvage.SALVAGE_OUTPUT),
    "bytes": 47_443,
    "file_sha256": "48a809eaad5e0660a4a1474b051d9ed7d732f390b429a41f23c6299ea4d788a4",
    "canonical_integrity_sha256": "3b6550c35f0c9459c8cbbdfec1482625d57170efdef84042a0f353f5d1cfd459",
    "outcome": "terminal_salvage_failed_read_only",
}
FAULT_RECONCILIATION_BINDING = {
    "path": str(salvage.RECONCILED_OUTPUT),
    "bytes": 54_647,
    "file_sha256": "d1c5b1dbdc67712703dd64bbdff7ebc9c9d862789f6db398714c4b0d7cc28e5c",
    "canonical_integrity_sha256": "3c59ad53160a85cf6d9a4493e909d2f0d2507940b6e859a587fb06df3a6bfe79",
    "outcome": "fault_salvaged_read_only",
}
RELAY_OFF_QUERY_BINDING = {
    "path": str(
        salvage.RECONCILED_OUTPUT.parent
        / "relay-user-gnd-check-query-20260831-225829014.json"
    ),
    "bytes": 1_243,
    "file_sha256": "7758876ce52fb63237fbaf1627959b70aab4753c7310ef3b2fb23ad82784b063",
    "canonical_integrity_sha256": "c7e573f23ddde6d3642ed3f96358e3e88bd4c47af77f7794b23811dc8bcbea5c",
}
LATEST_REPOWER_ON_BINDING = {
    "path": str(
        salvage.RECONCILED_OUTPUT.parent
        / "relay-user-gnd-confirmed-repower-on-20260831-230549647.json"
    ),
    "bytes": 1_870,
    "file_sha256": "322dee410a333d35152fa8024c3122827881600a8879726727b157c04ec5c021",
    "canonical_integrity_sha256": "98db9c7cd1a5a1b3be4e14a130b132a45442d46d8dc8819318a067b1f579c31d",
    "switched_at": "2026-08-31T15:05:49.647Z",
}
PROTECTIVE_OFF_BINDING = {
    "path": str(
        salvage.RECONCILED_OUTPUT.parent
        / "relay-post-gnd-check-protective-off-20260831-230749859.json"
    ),
    "bytes": 1_802,
    "file_sha256": "d50c961594bb518b73461057d6b2a490c73d04e6847885be17272736af4f3bc9",
    "canonical_integrity_sha256": "020e807a2a0cd313db1f678a89aa18657b84831502cf95e5893be89df22cc7ff",
    "switched_at": "2026-08-31T15:07:49.860Z",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def white_artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = WHITE_ARTIFACTS[STAGE]
    return (
        int(values["bin_bytes"]) > 0
        and int(values["elf_bytes"]) > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def _verify_fixed_file(binding: Mapping[str, Any], *, label: str) -> None:
    path = Path(str(binding["path"])).resolve()
    if not path.is_file() or path.is_symlink():
        raise W8PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise W8PackError(f"{label} sealed file binding differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W8PackError(f"{label} is not JSON") from error
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != binding["canonical_integrity_sha256"]
    ):
        raise W8PackError(f"{label} canonical integrity differs")


def _verify_relay_off_query() -> dict[str, Any]:
    binding = RELAY_OFF_QUERY_BINDING
    path = Path(str(binding["path"])).resolve()
    if not path.is_file() or path.is_symlink():
        raise W8PackError("fixed relay OFF query missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise W8PackError("fixed relay OFF query sealed file binding differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W8PackError("fixed relay OFF query is not JSON") from error
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256"
        or integrity.get("canonical_sha256") != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != binding["canonical_integrity_sha256"]
        or value.get("kind") != "mf17506-zave-relay-exact-bound-query-receipt"
        or value.get("channel") != 1
        or value.get("commanded_state") != "OFF"
        or value.get("off_gate_passed") is not True
        or value.get("contact_switch_performed") is not False
        or value.get("electrical_state_proven") is not False
        or value.get("on_authorized") is not False
        or value.get("automatic_retry_performed") is not False
        or value.get("expected_identity") != {
            "model": "ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z",
            "pid": "7523",
            "pnp_instance_id": "USB\\VID_1A86&PID_7523\\5&230B5917&0&4",
            "port": "COM14",
            "serial_number": "ABSENT-CH340-NO-ISERIAL",
            "usb_location": "Port_#0004.Hub_#0002",
            "vid": "1A86",
        }
    ):
        raise W8PackError("fixed relay OFF query semantics differ")
    return value


def _verify_relay_switch_receipt(
    binding: Mapping[str, Any], *, state: str
) -> dict[str, Any]:
    path = Path(str(binding["path"])).resolve()
    if not path.is_file() or path.is_symlink():
        raise W8PackError(f"fixed relay {state} receipt missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise W8PackError(f"fixed relay {state} receipt file binding differs")
    value = json.loads(payload)
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256"
        or integrity.get("canonical_sha256") != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != binding["canonical_integrity_sha256"]
        or value.get("kind") != "mf17506-zave-relay-exact-bound-switch-receipt"
        or value.get("channel") != 1
        or value.get("commanded_state") != state
        or value.get("target_state") != state
        or value.get("target_gate_passed") is not True
        or value.get("contact_switch_performed") is not True
        or value.get("electrical_state_proven") is not False
        or value.get("automatic_retry_performed") is not False
        or value.get("automatic_recovery_performed") is not False
        or value.get("feedback_command_count") != 1
        or value.get("independent_query_count") != 1
        or value.get("output_write_contract") != "O_EXCL_PRE_RESERVED_BEFORE_DEVICE_IO"
        or value.get("switched_at") != binding["switched_at"]
        or value.get("expected_identity") != {
            "model": "ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z",
            "pid": "7523",
            "pnp_instance_id": "USB\\VID_1A86&PID_7523\\5&230B5917&0&4",
            "port": "COM14",
            "serial_number": "ABSENT-CH340-NO-ISERIAL",
            "usb_location": "Port_#0004.Hub_#0002",
            "vid": "1A86",
        }
        or (state == "OFF" and value.get("off_gate_passed") is not True)
    ):
        raise W8PackError(f"fixed relay {state} receipt semantics differ")
    return value


def validate_fault_authority() -> dict[str, Any]:
    """Deep-validate and independently hash the immutable four-file FAULT chain."""

    for label, binding in (
        ("T4 V3 consumed failure", SOURCE_FAILURE_BINDING),
        ("T4 V3 permanent claim", CLAIM_BINDING),
        ("T4 V3 raw four-GET salvage", RAW_SALVAGE_BINDING),
        ("T4 V3 offline FAULT reconciliation", FAULT_RECONCILIATION_BINDING),
    ):
        _verify_fixed_file(binding, label=label)
    _verify_relay_off_query()
    _verify_relay_switch_receipt(LATEST_REPOWER_ON_BINDING, state="ON")
    protective_off = _verify_relay_switch_receipt(PROTECTIVE_OFF_BINDING, state="OFF")
    if protective_off["switched_at"] <= LATEST_REPOWER_ON_BINDING["switched_at"]:
        raise W8PackError("protective OFF does not postdate latest repower ON")
    value, _payload = salvage.validate_fault_reconciliation()
    raw_value = json.loads(Path(RAW_SALVAGE_BINDING["path"]).read_bytes())
    terminal = value.get("terminal_report")
    driver = terminal.get("driver") if isinstance(terminal, Mapping) else None
    transcript = raw_value.get("transcript")
    status = value.get("status")
    if (
        value.get("outcome") != "fault_salvaged_read_only"
        or value.get("terminal_state") != "FAULT"
        or value.get("source_consumed_failure_binding") != SOURCE_FAILURE_BINDING
        or value.get("claim_binding") != CLAIM_BINDING
        or value.get("raw_salvage_binding") != RAW_SALVAGE_BINDING
        or value.get("_validated_file_binding") != {
            "path": FAULT_RECONCILIATION_BINDING["path"],
            "bytes": FAULT_RECONCILIATION_BINDING["bytes"],
            "file_sha256": FAULT_RECONCILIATION_BINDING["file_sha256"],
            "canonical_integrity_sha256": FAULT_RECONCILIATION_BINDING["canonical_integrity_sha256"],
        }
        or value.get("boot_nonce") != "63f251f6a2ed5fc1"
        or value.get("driver_called") is not True
        or value.get("driver_call_count_for_action") != 1
        or value.get("total_driver_call_count") != 1
        or value.get("partial_visible_panel_mutation_possible") is not True
        or value.get("panel_state_qualified") is not False
        or value.get("matched_swap_complete") is not False
        or value.get("human_profile_following_decision_allowed") is not False
        or value.get("fresh_fault_bound_white_containment_required") is not True
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        != [("GET", "version", 200), ("GET", "manifest", 200), ("GET", "status", 200), ("GET", "report", 200)]
        or value.get("historical_transcript") != transcript
        or value.get("status") != transcript[2].get("response")
        or terminal != transcript[3].get("response")
        or not isinstance(status, Mapping)
        or status.get("arm_request_count") != 1
        or status.get("execute_request_count") != 1
        or status.get("total_driver_call_count") != 1
        or not isinstance(driver, Mapping)
        or driver.get("drf_ms") != 60_001
        or driver.get("wait_timeout") is not True
        or driver.get("timeout_stage") != "DRF"
        or driver.get("sequence_ok") is not False
    ):
        raise W8PackError("T4 V3 FAULT authority semantics differ")
    return deepcopy(value)


def _source_binding() -> dict[str, Any]:
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    return {
        "stage": source.STAGE,
        "campaign_id": source_report["contract"]["campaign_id"],
        "contract_id": source_report["contract_id"],
        "descriptor_id": source_action["descriptor_id"],
        "action_id": source_action["action_id"],
        "round": source_action["round"],
        "profile_id": source_action["profile_id"],
        "global_header": source_action["global_header"],
        "waveform_binding": deepcopy(source_action["waveform_binding"]),
    }


def _obsolete_white_actions() -> list[str]:
    return [
        w5.build_white_report()["action"]["action_id"],
        w6.build_white_report()["action"]["action_id"],
        w7.build_white_report()["action"]["action_id"],
    ]


def build_white_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    bound = _source_binding()
    action_seed = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "source_campaign_id": bound["campaign_id"],
        "source_contract_id": bound["contract_id"],
        "source_descriptor_id": bound["descriptor_id"],
        "source_action_id": bound["action_id"],
        "frame_sha256": FACTORY_WHITE_FRAME_SHA256,
        "cs1_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
        "cs2_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
    }
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-descriptor-v1",
        "build_tag": CONFIG.build_tag,
        **action_seed,
        "fault_authority": {
            "source_failure": deepcopy(SOURCE_FAILURE_BINDING),
            "claim": deepcopy(CLAIM_BINDING),
            "raw_salvage": deepcopy(RAW_SALVAGE_BINDING),
            "reconciliation": deepcopy(FAULT_RECONCILIATION_BINDING),
            "relay_off_query": deepcopy(RELAY_OFF_QUERY_BINDING),
            "latest_repower_on": deepcopy(LATEST_REPOWER_ON_BINDING),
            "protective_off": deepcopy(PROTECTIVE_OFF_BINDING),
        },
        "rejected_obsolete_white_action_ids": _obsolete_white_actions(),
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        f"MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_ACTION_V1|{CONFIG.campaign_id}|{action['descriptor_id']}".encode("ascii")
    )
    contract = {
        "schema": "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-contract-v1",
        "white_stage": STAGE,
        "build_tag": CONFIG.build_tag,
        "test_id": CONFIG.test_id,
        "campaign_id": CONFIG.campaign_id,
        "source": bound,
        "source_campaign_id": bound["campaign_id"],
        "source_contract_id": bound["contract_id"],
        "source_descriptor_id": bound["descriptor_id"],
        "source_action_id": bound["action_id"],
        "fault_authority": deepcopy(descriptor["fault_authority"]),
        "source_terminal_state_required": "FAULT",
        "source_driver_called_required": True,
        "source_driver_call_count_required": 1,
        "source_drf_timeout_ms": 60_001,
        "partial_visible_panel_mutation_possible": True,
        "panel_state_qualified": False,
        "matched_swap_complete": False,
        "human_profile_following_decision_allowed": False,
        "fresh_fault_bound_white_containment_required": True,
        "relay_off_query_is_commanded_state_only": True,
        "relay_electrical_state_proven": False,
        "protective_off_switch_receipt_required_before_live": True,
        "protective_off_postdates_latest_repower_on": True,
        "fresh_user_physical_gnd_confirmation_required_before_j2_on": True,
        "operator_reported_physical_observation": "GND_WAS_DISCONNECTED_THEN_REINSERTED",
        "operator_reported_gnd_fault_is_highly_plausible_root_cause": True,
        "operator_report_does_not_retroactively_qualify_t4": True,
        "fresh_user_gnd_confirmation_recorded_by_repower_authority": True,
        "source_action_must_not_be_retried": True,
        "source_complete_path_forbidden": True,
        "rejected_obsolete_white_action_ids": _obsolete_white_actions(),
        "obsolete_white_execution_forbidden": True,
        "profile_id": "WF23_25",
        "base_route": CONFIG.base_route,
        "nvs_namespace": CONFIG.nvs_namespace,
        "nvs_key": CONFIG.nvs_key,
        "classification": CLASSIFICATION,
        "action": action,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "white_stage": STAGE,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "action": action,
        "contract": contract,
    }


def marker() -> str:
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W8_T4_V3_FAULT|"
        f"SHA256={build_white_report()['action']['descriptor_id']}"
    )


def dry_validate(*, verify_source: bool = True, verify_authority: bool = True) -> dict[str, Any]:
    if verify_source and source.dry_validate().get("result") != "PASS":
        raise W8PackError("T4 V3 source dry validation did not PASS")
    authority = validate_fault_authority() if verify_authority else None
    report = build_white_report()
    action = report["action"]
    expected_action_keys = {
        "ordinal", "role", "source_campaign_id", "source_contract_id",
        "source_descriptor_id", "source_action_id", "descriptor_id", "action_id",
        "frame_sha256", "cs1_dtm_sha256", "cs2_dtm_sha256",
    }
    if set(action) != expected_action_keys:
        raise W8PackError("W8 wire action shape differs")
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    if (
        action["source_campaign_id"] != source_report["contract"]["campaign_id"]
        or action["source_contract_id"] != source_report["contract_id"]
        or action["source_descriptor_id"] != source_action["descriptor_id"]
        or action["source_action_id"] != source_action["action_id"]
        or action["source_action_id"] != "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee"
    ):
        raise W8PackError("W8 exact T4 V3 source tuple differs")
    obsolete = set(_obsolete_white_actions())
    if len(obsolete) != 3 or action["action_id"] in obsolete:
        raise W8PackError("W8 reuses an obsolete W5/W6/W7 action")
    if report["contract"]["rejected_obsolete_white_action_ids"] != _obsolete_white_actions():
        raise W8PackError("W8 obsolete white registry differs")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W8PackError("W8 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != "/api/ec5/raw-p16-crossover-w8-after-t4-successor-v3-fault-white-v1":
        raise W8PackError("W8 route differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "source_validation_required": verify_source,
        "fault_authority_required": verify_authority,
        "fault_authority_verified": verify_authority,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "factory_otp_white_only": True,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "source_terminal_fault_exact": True,
        "partial_visible_panel_mutation_possible": True,
        "panel_state_qualified": False,
        "obsolete_w5_w6_w7_permanently_rejected": True,
        "source_action_retry_forbidden": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": artifacts_are_sealed(),
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "authority_terminal_state": None if authority is None else authority["terminal_state"],
    }


def main() -> int:
    print(json.dumps(build_white_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
