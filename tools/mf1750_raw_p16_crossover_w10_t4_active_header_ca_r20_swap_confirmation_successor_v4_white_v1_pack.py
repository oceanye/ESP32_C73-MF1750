#!/usr/bin/env python3
"""Offline W10 factory-white identity pre-authorized for exact T4 V4.

The W10 firmware contains only one fixed factory-OTP white action.  This
offline pack binds the not-yet-executed T4 V4 identity while the live wrapper
separately requires a deeply authenticated COMPLETE terminal record before it
permits any W10 device request.  FAULT is reserved and fail-closed until a
reviewed V4 salvage/reconciliation producer exists.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as source,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_pack as w9,
)


class W10PackError(RuntimeError):
    """Raised when W10 ceases to bind the exact fresh T4 V4 lineage."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = (
        "w10-after-t4-active-header-ca-r20-swap-confirmation-successor-v4-white-v1"
    )
    suffix: str = (
        "W10_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_WHITE"
    )
    nvs_namespace: str = "p16w10t4ca4v1"
    nvs_key: str = "used_w10t4ca4"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W10_AFTER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V4_WHITE_V1_2026-09-01"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-W10-AFTER-T4-ACTIVE-HEADER-CA-R20-SWAP-"
            "CONFIRMATION-SUCCESSOR-V4-WHITE-V1"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W10_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V4_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-w10-after-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v4-white-v1"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_w10t4ca4_w1"

    @property
    def build_root(self) -> str:
        return "b-w10t4ca4-w1"


STAGE = "w10-after-t4-active-header-ca-r20-swap-confirmation-successor-v4-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W10_T4_ACTIVE_HEADER_CA_R20_SWAP_"
    "CONFIRMATION_SUCCESSOR_V4_WHITE_DEVICE_V1"
)
IDENTITY_REVISION = (
    "raw-p16-crossover-w10-t4-active-header-ca-r20-swap-confirmation-"
    "successor-v4-white-v1"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W10_AFTER_T4_ACTIVE_HEADER_CA_R20_"
    "SWAP_CONFIRMATION_SUCCESSOR_V4_COMPLETE_TERMINAL_CONTAINMENT_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
FAULT_POLICY = "FAULT_RESERVED_FAIL_CLOSED_NOT_CURRENTLY_ADMISSIBLE"
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = w9.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = w9.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = w9.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = w9.FACTORY_WHITE_DTM_FNV1A

# Sealed after the isolated build and an independent re-read.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_504,
        "bin_sha256": "2a017ee98ebddc05253629345efafd98faae4210c27b8d2bc657e87b88a05a97",
        "elf_bytes": 13_215_012,
        "elf_sha256": "f74955f062ae4a646c54e689e33be17997168910f1fb4c852f014fbb4cb7e3ca",
    }
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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


def shared_firmware_intents() -> dict[str, str]:
    path = REPO_ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    text = path.read_text(encoding="utf-8")
    patterns = {
        "arm": r'kArmIntent\s*=\s*\n\s*"([^"]+)";',
        "execute": r'kExecuteIntent\s*=\s*\n\s*"([^"]+)";',
    }
    values: dict[str, str] = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise W10PackError(f"shared firmware {name} intent cardinality differs")
        values[name] = matches[0]
    return values


def validate_intent_parity() -> dict[str, str]:
    device = shared_firmware_intents()
    expected = {"arm": WHITE_ARM_INTENT, "execute": WHITE_EXECUTE_INTENT}
    if device != expected:
        raise W10PackError("W10 host/device white intent literals differ")
    return device


def validate_identity_source() -> dict[str, str]:
    """Require the C++ identity include to match the derived V4-bound report."""

    path = (
        REPO_ROOT
        / "src/ec5_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v4_white_v1_identity.inc"
    )
    text = path.read_text(encoding="utf-8")
    report = build_white_report()
    source_binding = report["contract"]["source"]
    expected_by_symbol = {
        "kCampaignId": CONFIG.campaign_id,
        "kSourceCampaignId": source_binding["campaign_id"],
        "kSourceContractId": source_binding["contract_id"],
        "kSourceDescriptorId": source_binding["descriptor_id"],
        "kSourceActionId": source_binding["action_id"],
        "kBuildTag": CONFIG.build_tag,
        "kContractId": report["contract_id"],
        "kDescriptorId": report["action"]["descriptor_id"],
        "kActionId": report["action"]["action_id"],
    }
    if "0" * 64 in text:
        raise W10PackError("W10 identity source still contains a zero scaffold")
    for symbol, value in expected_by_symbol.items():
        pattern = (
            rf"static\s+constexpr\s+const\s+char\s*\*\s*{re.escape(symbol)}\s*="
            rf'\s*"([^"]*)"\s*;'
        )
        matches = re.findall(pattern, text)
        if matches != [value]:
            raise W10PackError(f"W10 identity source {symbol} differs")

    marker_matches = re.findall(r'\.asciz\s+\\"([^"\\]*)\\"', text)
    expected_marker = marker()
    if marker_matches != [expected_marker]:
        raise W10PackError("W10 identity source descriptor marker differs")

    return {
        "campaign_id": expected_by_symbol["kCampaignId"],
        "source_campaign_id": expected_by_symbol["kSourceCampaignId"],
        "source_contract_id": expected_by_symbol["kSourceContractId"],
        "source_descriptor_id": expected_by_symbol["kSourceDescriptorId"],
        "source_action_id": expected_by_symbol["kSourceActionId"],
        "build_tag": expected_by_symbol["kBuildTag"],
        "contract_id": expected_by_symbol["kContractId"],
        "descriptor_id": expected_by_symbol["kDescriptorId"],
        "action_id": expected_by_symbol["kActionId"],
        "marker": expected_marker,
    }


def _source_binding() -> dict[str, Any]:
    report = source.build_report()
    action = report["actions"][0]
    artifacts = source.ARTIFACTS[source.STAGE]
    return {
        "stage": source.STAGE,
        "campaign_id": report["contract"]["campaign_id"],
        "test_id": report["contract"]["test_id"],
        "build_tag": report["contract"]["build_tag"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "frame_sha256": action["frame"]["sha256"],
        "cs1_dtm_sha256": action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": action["cs2_dtm"]["sha256"],
        "round": action["round"],
        "profile_id": action["profile_id"],
        "global_header": action["global_header"],
        "waveform_binding": deepcopy(action["waveform_binding"]),
        "firmware": deepcopy(artifacts),
        "terminal_policy": {
            "evidence_required_before_any_w10_device_request": True,
            "accepted_terminal_states": ["COMPLETE"],
            "complete_requires_result_true": True,
            "fault_policy": FAULT_POLICY,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": 1,
            "source_action_permanently_consumed": True,
            "fault_must_not_be_described_as_success": True,
        },
    }


def _obsolete_white_action_ids() -> list[str]:
    prior = {
        *w9.build_white_report()["contract"]["rejected_obsolete_white_action_ids"],
        w9.build_white_report()["action"]["action_id"],
    }
    return sorted(prior)


def _obsolete_experimental_action_ids() -> list[str]:
    report = source.build_report()
    return sorted({*source.non_reusable_action_ids(), report["actions"][0]["action_id"]})


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
    obsolete_white = _obsolete_white_action_ids()
    obsolete_experimental = _obsolete_experimental_action_ids()
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-w10-t4-v4-white-descriptor-v1",
        "build_tag": CONFIG.build_tag,
        **action_seed,
        "source_terminal_policy": deepcopy(bound["terminal_policy"]),
        "rejected_obsolete_white_action_ids": obsolete_white,
        "rejected_obsolete_experimental_action_ids": obsolete_experimental,
        "host_device_intent_parity_required": True,
        "arm_intent": WHITE_ARM_INTENT,
        "execute_intent": WHITE_EXECUTE_INTENT,
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W10_T4_V4_COMPLETE_TERMINAL_WHITE_ACTION_V1|"
            f"{CONFIG.campaign_id}|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-raw-p16-crossover-w10-t4-v4-white-contract-v1",
        "white_stage": STAGE,
        "build_tag": CONFIG.build_tag,
        "test_id": CONFIG.test_id,
        "campaign_id": CONFIG.campaign_id,
        "source": bound,
        "source_campaign_id": bound["campaign_id"],
        "source_contract_id": bound["contract_id"],
        "source_descriptor_id": bound["descriptor_id"],
        "source_action_id": bound["action_id"],
        "source_terminal_evidence_required_before_any_live_request": True,
        "source_terminal_policy": deepcopy(bound["terminal_policy"]),
        "accepted_source_terminal_states": ["COMPLETE"],
        "source_fault_policy": FAULT_POLICY,
        "source_fault_is_not_success": True,
        "source_action_must_not_be_retried": True,
        "rejected_obsolete_white_action_ids": obsolete_white,
        "rejected_obsolete_experimental_action_ids": obsolete_experimental,
        "obsolete_action_execution_forbidden": True,
        "profile_id": "WF23_25",
        "base_route": CONFIG.base_route,
        "nvs_namespace": CONFIG.nvs_namespace,
        "nvs_key": CONFIG.nvs_key,
        "classification": CLASSIFICATION,
        "arm_intent": WHITE_ARM_INTENT,
        "execute_intent": WHITE_EXECUTE_INTENT,
        "action": action,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "runtime_lut_write": False,
        "custom_waveform_write": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w10-t4-v4-white-offline-identities-v1",
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
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W10_T4_V4_COMPLETE_TERMINAL|"
        f"SHA256={build_white_report()['action']['descriptor_id']}"
    )


def dry_validate(*, verify_source: bool = True) -> dict[str, Any]:
    if verify_source and source.dry_validate().get("result") != "PASS":
        raise W10PackError("T4 V4 source dry validation did not PASS")
    intents = validate_intent_parity()
    compiled_identity = validate_identity_source()
    report = build_white_report()
    action = report["action"]
    contract = report["contract"]
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    observed = (
        action["source_campaign_id"],
        action["source_contract_id"],
        action["source_descriptor_id"],
        action["source_action_id"],
    )
    expected = (
        source_report["contract"]["campaign_id"],
        source_report["contract_id"],
        source_action["descriptor_id"],
        source_action["action_id"],
    )
    if observed != expected:
        raise W10PackError("W10 source tuple differs from exact T4 V4")
    bound = contract["source"]
    if (
        bound["stage"] != source.STAGE
        or bound["round"] != 4
        or bound["profile_id"]
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or bound["global_header"] != "active"
        or bound["waveform_binding"]["cs1"]["name"] != "commented"
        or bound["waveform_binding"]["cs2"]["name"] != "active"
        or contract["accepted_source_terminal_states"] != ["COMPLETE"]
        or contract["source_fault_policy"] != FAULT_POLICY
        or contract["source_fault_is_not_success"] is not True
    ):
        raise W10PackError("W10 T4 V4 source or terminal policy differs")
    old_white = contract["rejected_obsolete_white_action_ids"]
    old_experimental = contract["rejected_obsolete_experimental_action_ids"]
    if (
        len(old_white) != len(set(old_white))
        or len(old_experimental) != len(set(old_experimental))
        or w9.build_white_report()["action"]["action_id"] not in old_white
        or source_action["action_id"] not in old_experimental
        or action["action_id"] in {*old_white, *old_experimental}
    ):
        raise W10PackError("W10 obsolete action tombstones differ")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W10PackError("W10 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != (
        "/api/ec5/raw-p16-crossover-w10-after-t4-active-header-ca-r20-"
        "swap-confirmation-successor-v4-white-v1"
    ):
        raise W10PackError("W10 route differs")
    if not (
        contract["factory_otp_white_only"] is True
        and contract["runtime_payload"] is False
        and contract["runtime_lut_write"] is False
        and contract["action_count"] == 1
        and contract["one_visible_refresh_per_action"] is True
    ):
        raise W10PackError("W10 fixed factory-white-only contract differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w10-t4-v4-white-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "source_validation_required": verify_source,
        "source_identity_preauthorized": True,
        "source_terminal_evidence_checked_offline": False,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "factory_otp_white_only": True,
        "runtime_lut_present": False,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "accepted_source_terminal_states": ["COMPLETE"],
        "source_fault_policy": FAULT_POLICY,
        "source_fault_is_not_success": True,
        "obsolete_actions_tombstoned": True,
        "host_device_intent_parity": intents,
        "compiled_identity_source": compiled_identity,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": artifacts_are_sealed(),
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source": deepcopy(bound),
    }


def main() -> int:
    print(json.dumps(build_white_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
