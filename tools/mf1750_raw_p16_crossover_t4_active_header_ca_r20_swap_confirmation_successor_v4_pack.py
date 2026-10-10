#!/usr/bin/env python3
"""Fresh T4 V4 after the V3 terminal FAULT and completed W9 containment.

V4 changes live identities and predecessor authorities only.  The experimental
frame, both controller DTM streams, active global header, and CA R20 assignment
remain byte-identical to V3.
"""

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

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as v3,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_pack as w9,
)


class T4MatchedSwapSuccessorV4PackError(RuntimeError):
    """Raised when a V4 identity, authority, or frozen payload differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t4-active-header-ca-r20-swap-confirmation-successor-v4"
    suffix: str = "T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4"
    global_header: str = "active"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 4
    nvs_namespace: str = "p16t4ca_v4"
    nvs_key: str = "cur_t4ca4"
    nvs_boot_key: str = "boot_t4ca4"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4"

    @property
    def build_tag(self) -> str:
        return "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_2026-09-01"

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-SWAP-CONFIRMATION-SUCCESSOR-V4"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v4"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_t4ca4"

    @property
    def build_root(self) -> str:
        return "b-t4ca4"


STAGE = "t4-active-header-ca-r20-swap-confirmation-successor-v4"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V4"
IDENTITY_REVISION = STAGE
CLASSIFICATION = v3.CLASSIFICATION
FACTORY_WHITE_ANCHOR_ROLE = v3.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_ACTION_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_ACTION_ONCE"
CODE_ROWS = v3.CODE_ROWS
GRID_Y_BY_ROW = v3.GRID_Y_BY_ROW
PROFILE_ID = v3.PROFILE_ID
GLOBAL_TUPLE_ID = v3.GLOBAL_TUPLE_ID
HUMAN_OBSERVATION_PLAN = deepcopy(v3.HUMAN_OBSERVATION_PLAN)

V3_ACTION_ID = v3.build_report()["actions"][0]["action_id"]
W8_ACTION_ID = "46f0ee263d7d6e2759d0078ba523878f29bf095bab4f9928288c9ccf76d1c348"
W9_ACTION_ID = "72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910"

V3_FAULT_BINDING = {
    "path": ".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V3/action-01-terminal-read-only-salvage-reconciled.json",
    "bytes": 54_647,
    "file_sha256": "d1c5b1dbdc67712703dd64bbdff7ebc9c9d862789f6db398714c4b0d7cc28e5c",
    "canonical_integrity_sha256": "3c59ad53160a85cf6d9a4493e909d2f0d2507940b6e859a587fb06df3a6bfe79",
}
W9_ACTION_BINDING = {
    "path": ".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_20260831_V1/action-01-factory-otp-white.json",
    "bytes": 29_040,
    "file_sha256": "26ef448478d5680a19869ffbb0982cfb65db14e6bd20880961eb021a0d90097a",
    "canonical_integrity_sha256": "2c6c818300dc0f72f01607fefaae2467d816ff449c64daa3c8eadb26510bd350",
}
W9_CLAIM_BINDING = {
    "path": ".test-output/hardware/.mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_claims/72c7ab97a607aacf42c2bbe3bc8f5ac121489cfc3e47ca0fb978f04f698f5910.json",
    "bytes": 1_834,
    "file_sha256": "beabfecebc4afbe7411eda1bfc088b0e7537b87a997e9da7db33129cc0d4b708",
    "canonical_integrity_sha256": "77f8a337b5197b89e8d78dc6b205f620fa0da80aff5f37a39064a161be27e80c",
}
W9_POST_OFF_BINDING = {
    "path": ".test-output/hardware/MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_20260831_V1/relay-post-white-protective-off.json",
    "bytes": 1_802,
    "file_sha256": "0af2b5b0725d0eb0bb3738882a0b772165a1cf17f45599d19d92976679f41033",
    "canonical_integrity_sha256": "488533e223ac2f9021368f9762c1bf05c393f5bb47be706af882fb3fb57ea368",
}
OPERATOR_GND_ASSERTION = {
    "kind": "mf1750-operator-gnd-reseat-assertion-v1",
    "fault_cause_verbatim": "果然是GND掉了",
    "reseat_and_repower_verbatim": "插座gnd都ok，重新上电检查一下",
    "post_reseat_normal_verbatim": "是的，一切正常",
    "gnd_reseated_and_powered_check_reported_normal": True,
    "conversation_assertion_only": True,
    "cryptographic_evidence": False,
    "electrical_state_proven": False,
    "does_not_reclassify_t4_v3_fault": True,
}

ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 806416,
        "bin_sha256": "2b7ed3e0b1da3cd44bdd89450857911ea62dfdcc6d54a9d4dc94d77005f17a42",
        "elf_bytes": 13304784,
        "elf_sha256": "0c04ef30f5b7b41336040c9adc6a5c329433875696c49f4c75946f1ca0b9264d",
    }
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_bound(binding: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or path.is_symlink():
        raise T4MatchedSwapSuccessorV4PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise T4MatchedSwapSuccessorV4PackError(f"{label} file binding differs")
    value = json.loads(payload)
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256", integrity.get("canonical_sha256")) if isinstance(integrity, Mapping) else None
    if recorded != binding["canonical_integrity_sha256"] or sha256_bytes(canonical_json(body)) != recorded:
        raise T4MatchedSwapSuccessorV4PackError(f"{label} canonical binding differs")
    return value


def v3_terminal_fault_binding() -> dict[str, Any]:
    value = _read_bound(V3_FAULT_BINDING, "T4 V3 terminal FAULT")
    if value.get("terminal_state") != "FAULT" or value.get("outcome") != "fault_salvaged_read_only" or value.get("driver_call_count_for_action") != 1 or value.get("partial_visible_panel_mutation_possible") is not True or value.get("action_must_not_be_retried") is not True:
        raise T4MatchedSwapSuccessorV4PackError("T4 V3 terminal FAULT semantics differ")
    return {**deepcopy(V3_FAULT_BINDING), "action_id": V3_ACTION_ID, "outcome": "fault_salvaged_read_only", "terminal_state": "FAULT", "driver_calls": 1, "retry_forbidden": True}


def completed_w9_white_action_binding() -> dict[str, Any]:
    value = _read_bound(W9_ACTION_BINDING, "W9 completed white")
    report = w9.build_white_report()
    if value.get("outcome") != "complete_pass" or value.get("visible_refreshes") != 1 or value.get("action") != report["action"] or value.get("terminal_report", {}).get("terminal_state") != "COMPLETE" or value.get("terminal_report", {}).get("campaign_complete") is not True:
        raise T4MatchedSwapSuccessorV4PackError("W9 completed white semantics differ")
    action = report["action"]
    return {"kind": value["kind"], **deepcopy(W9_ACTION_BINDING), "campaign_id": report["contract"]["campaign_id"], "contract_id": report["contract_id"], "descriptor_id": action["descriptor_id"], "action_id": action["action_id"], "outcome": "complete_pass", "terminal_state": "COMPLETE", "visible_refreshes": 1}


def completed_w9_white_claim_binding() -> dict[str, Any]:
    value = _read_bound(W9_CLAIM_BINDING, "W9 permanent claim")
    report = w9.build_white_report()
    action = report["action"]
    if (
        value.get("kind")
        != "mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-v1-claim"
        or value.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or value.get("write_contract") != "O_EXCL"
        or value.get("action") != action
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise T4MatchedSwapSuccessorV4PackError("W9 permanent claim semantics differ")
    return {
        **deepcopy(W9_CLAIM_BINDING),
        "action_id": action["action_id"],
        "state": value["state"],
        "write_contract": "O_EXCL",
        "permanently_consumed": True,
    }


def w9_post_off_binding() -> dict[str, Any]:
    value = _read_bound(W9_POST_OFF_BINDING, "W9 post-white protective OFF")
    if value.get("commanded_state") != "OFF" or value.get("target_state") != "OFF" or value.get("off_gate_passed") is not True or value.get("electrical_state_proven") is not False:
        raise T4MatchedSwapSuccessorV4PackError("W9 protective OFF semantics differ")
    return {**deepcopy(W9_POST_OFF_BINDING), "commanded_state": "OFF", "target_state": "OFF", "off_gate_passed": True, "electrical_state_proven": False}


def completed_t3_v2_action_binding() -> dict[str, Any]:
    return v3.completed_t3_v2_action_binding()


def completed_w4_white_action_binding() -> dict[str, Any]:
    """Compatibility name required by the inherited T4 host mechanics."""
    return completed_w9_white_action_binding()


def external_containment_contract() -> dict[str, Any]:
    return {"outside_campaign": True, "factory_otp_white_before_required": True, "factory_otp_white_after_required": True, "completed_w9_machine_white_anchor_present": True, "fresh_operator_clean_white_confirmation_required": True, "formal_full_panel_white_evidence": False, "human_observation_required": True, "white_actions_in_campaign": 0, "post_t4_v4_fresh_white_successor_required": True}


def validate_authorities() -> dict[str, Any]:
    return {"predecessor_chain": v3.validate_authorities(), "t4_v3_terminal_fault": v3_terminal_fault_binding(), "w9_complete_white": completed_w9_white_action_binding(), "w9_permanent_claim": completed_w9_white_claim_binding(), "w9_post_white_protective_off": w9_post_off_binding(), "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION)}


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (*v3.non_reusable_action_ids(), V3_ACTION_ID, W8_ACTION_ID, W9_ACTION_ID)
    if len(values) != 18 or len(values) != len(set(values)):
        raise T4MatchedSwapSuccessorV4PackError("V4 tombstone registry differs")
    return values


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    item = ARTIFACTS[STAGE]
    return int(item["bin_bytes"]) > 0 and int(item["elf_bytes"]) > 0 and item["bin_sha256"] != "0" * 64 and item["elf_sha256"] != "0" * 64


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    old_report = v3.build_report()
    old = old_report["actions"][0]
    action = deepcopy(old)
    for key in ("descriptor_id", "action_id"):
        action.pop(key, None)
    action.update({"role": "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_ATLAS", "branch": f"{CONFIG.variant_key}_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_ATLAS", "pre_white_action_evidence": completed_w9_white_action_binding(), "pre_white_permanent_claim": completed_w9_white_claim_binding(), "supersedes_failed_faulted_v3_action_id": V3_ACTION_ID, "v3_terminal_fault_authority": v3_terminal_fault_binding(), "w9_post_white_protective_off": w9_post_off_binding(), "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION), "boot_admission": {"campaign_boot_binding_key": CONFIG.nvs_boot_key, "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY", "required_prior_terminal_state": None, "required_prior_ordinal": None, "firmware_arm_gate": True, "firmware_execute_gate": True, "firmware_dispatch_gate": True, "reboot_resume_allowed": False, "post_containment_resume_allowed": False}})
    descriptor = {"schema": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-action-v4", "variant": CONFIG.variant_key, "build_tag": CONFIG.build_tag, **action, "non_reusable_action_ids": list(non_reusable_action_ids())}
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(f"MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_ACTION_V4|{CONFIG.variant_key}|1|{action['descriptor_id']}".encode())
    contract = deepcopy(old_report["contract"])
    contract.update({"schema": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-contract-v4", "stage": STAGE, "variant_key": CONFIG.variant_key, "build_tag": CONFIG.build_tag, "test_id": CONFIG.test_id, "campaign_id": CONFIG.campaign_id, "base_route": CONFIG.base_route, "nvs_namespace": CONFIG.nvs_namespace, "nvs_key": CONFIG.nvs_key, "nvs_boot_key": CONFIG.nvs_boot_key, "external_containment": external_containment_contract(), "pre_white_action_evidence": completed_w9_white_action_binding(), "pre_white_permanent_claim": completed_w9_white_claim_binding(), "actions": [action], "v3_terminal_fault_authority": v3_terminal_fault_binding(), "w9_post_white_protective_off": w9_post_off_binding(), "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION), "failed_v3_action_terminal_fault": True, "minimal_successor_fix": "FRESH_IDENTITY_AFTER_GND_RESEAT_AND_W9_WHITE_CONTAINMENT", "non_reusable_action_ids": list(non_reusable_action_ids())})
    return {"schema_version": 4, "kind": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-offline-identities-v4", "offline_only": True, "hardware_accessed": False, "device_network_accessed": False, "serial_or_com_accessed": False, "relay_accessed": False, "firmware_flashed": False, "display_refreshed": False, "stage": STAGE, "source_action_authority": completed_t3_v2_action_binding(), "pre_white_action_evidence": completed_w9_white_action_binding(), "pre_white_permanent_claim": completed_w9_white_claim_binding(), "v3_terminal_fault_authority": v3_terminal_fault_binding(), "w9_post_white_protective_off": w9_post_off_binding(), "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION), "actions": [action], "contract": contract, "contract_id": sha256_bytes(canonical_json(contract))}


def dry_validate(*, verify_authorities: bool = True) -> dict[str, Any]:
    if verify_authorities:
        validate_authorities()
    report = build_report()
    action = report["actions"][0]
    old = v3.build_report()["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding", "profile_id", "global_header", "global_tuple_id", "round"):
        if action[key] != old[key]:
            raise T4MatchedSwapSuccessorV4PackError(f"V4 payload field {key} differs")
    if non_reusable_action_ids()[-3:] != (V3_ACTION_ID, W8_ACTION_ID, W9_ACTION_ID) or action["action_id"] in non_reusable_action_ids() or len(CONFIG.nvs_namespace) > 15:
        raise T4MatchedSwapSuccessorV4PackError("V4 freshness gate differs")
    return {"schema_version": 4, "kind": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-dry-validation-v4", "result": "PASS", "offline_only": True, "authority_verified": verify_authorities, "hardware_accessed": False, "network_requests": 0, "serial_or_com_accessed": False, "relay_accessed": False, "firmware_flashed": False, "display_refreshed": False, "experimental_payload_byte_identical_to_v3": True, "fresh_campaign_test_contract_descriptor_action_route_nvs": True, "action_count": 1, "no_retry": True, "no_recovery": True, "no_autochain": True, "contract_id": report["contract_id"], "descriptor_id": action["descriptor_id"], "action_id": action["action_id"], "non_reusable_action_count": len(non_reusable_action_ids()), "artifacts_sealed": artifacts_are_sealed()}


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
