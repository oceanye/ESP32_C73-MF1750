#!/usr/bin/env python3
"""Offline identities for W7 white after the exact completed T4 successor V3."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_pack as legacy,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as source,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as w5,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack as w6,
)


class W7PackError(RuntimeError):
    """Raised when W7 ceases to bind the exact completed T4 V3 source."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = (
        "w7-after-t4-active-header-ca-r20-swap-confirmation-successor-v3-white-v1"
    )
    suffix: str = (
        "W7_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_WHITE"
    )
    nvs_namespace: str = "p16w7t4ca3_v1"
    nvs_key: str = "used_w7t4ca3"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W7_AFTER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V3_WHITE_V1_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-W7-AFTER-T4-ACTIVE-HEADER-CA-R20-SWAP-"
            "CONFIRMATION-SUCCESSOR-V3-WHITE-V1"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W7_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V3_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-w7-after-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-v1"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_w7t4ca3_w1"

    @property
    def build_root(self) -> str:
        return "b-w7t4ca3-w1"


STAGE = "w7-after-t4-active-header-ca-r20-swap-confirmation-successor-v3-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_"
    "CONFIRMATION_SUCCESSOR_V3_WHITE_DEVICE_V1"
)
IDENTITY_REVISION = (
    "raw-p16-crossover-w7-t4-active-header-ca-r20-swap-confirmation-"
    "successor-v3-white-v1"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W7_AFTER_T4_ACTIVE_HEADER_CA_R20_"
    "SWAP_CONFIRMATION_SUCCESSOR_V3_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = legacy.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = legacy.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = legacy.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = legacy.FACTORY_WHITE_DTM_FNV1A

# Sealed only after the isolated compile-only build is independently re-read.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_488,
        "bin_sha256": (
            "295bb8020cb4ecfab2338a981c5c6c6bd4dad0932ca5345d9ef76cb5f929cbe3"
        ),
        "elf_bytes": 13_215_008,
        "elf_sha256": (
            "b9daa5f580e89724d89f497ba61ece345f7d327308653ba34fad1739bf3c4322"
        ),
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


def _failure_authorities(source_report: dict[str, Any]) -> dict[str, Any]:
    contract = source_report["contract"]
    return {
        "v1": deepcopy(contract["v1_diagnostic_failure_authority"]),
        "v2": deepcopy(contract["v2_diagnostic_failure_authority"]),
    }


def _source_binding() -> dict[str, Any]:
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    failures = _failure_authorities(source_report)
    return {
        "stage": source.STAGE,
        "campaign_id": source_report["contract"]["campaign_id"],
        "test_id": source_report["contract"]["test_id"],
        "build_tag": source_report["contract"]["build_tag"],
        "contract_id": source_report["contract_id"],
        "descriptor_id": source_action["descriptor_id"],
        "action_id": source_action["action_id"],
        "frame_sha256": source_action["frame"]["sha256"],
        "cs1_dtm_sha256": source_action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": source_action["cs2_dtm"]["sha256"],
        "round": source_action["round"],
        "profile_id": source_action["profile_id"],
        "global_header": source_action["global_header"],
        "waveform_binding": deepcopy(source_action["waveform_binding"]),
        "v1_diagnostic_failure_authority": failures["v1"],
        "v2_diagnostic_failure_authority": failures["v2"],
        "completion_requirement": {
            "evidence_file_required_before_live_white": True,
            "ordinal": 1,
            "action_id": source_action["action_id"],
            "terminal_state": "COMPLETE",
            "result": True,
            "campaign_complete": True,
            "visible_refreshes": 1,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": 1,
        },
    }


def _obsolete_white_actions() -> tuple[str, str]:
    return (
        w5.build_white_report()["action"]["action_id"],
        w6.build_white_report()["action"]["action_id"],
    )


def build_white_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    source_binding = _source_binding()
    failed_actions = (
        source_binding["v1_diagnostic_failure_authority"]["action_id"],
        source_binding["v2_diagnostic_failure_authority"]["action_id"],
    )
    obsolete_white_actions = _obsolete_white_actions()
    action_seed = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "source_campaign_id": source_binding["campaign_id"],
        "source_contract_id": source_binding["contract_id"],
        "source_descriptor_id": source_binding["descriptor_id"],
        "source_action_id": source_binding["action_id"],
        "source_completion_required": True,
        "frame_sha256": FACTORY_WHITE_FRAME_SHA256,
        "cs1_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
        "cs2_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
    }
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-descriptor-v1"
        ),
        "build_tag": CONFIG.build_tag,
        **action_seed,
        "rejected_failed_source_action_ids": list(failed_actions),
        "rejected_obsolete_white_action_ids": list(obsolete_white_actions),
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            f"CONFIRMATION_SUCCESSOR_V3_WHITE_ACTION_V1|{CONFIG.campaign_id}|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-contract-v1"
        ),
        "white_stage": STAGE,
        "build_tag": CONFIG.build_tag,
        "test_id": CONFIG.test_id,
        "campaign_id": CONFIG.campaign_id,
        "source": source_binding,
        "source_campaign_id": source_binding["campaign_id"],
        "source_contract_id": source_binding["contract_id"],
        "source_descriptor_id": source_binding["descriptor_id"],
        "source_action_id": source_binding["action_id"],
        "source_completion_evidence_required_before_live_white": True,
        "source_completion_requirement": deepcopy(
            source_binding["completion_requirement"]
        ),
        "rejected_failed_source_action_ids": list(failed_actions),
        "rejected_obsolete_white_action_ids": list(obsolete_white_actions),
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
        "manual_profile_following_observation_required_before_white": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-offline-identities-v1"
        ),
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
    action = build_white_report()["action"]
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        f"CONFIRMATION_SUCCESSOR_V3|SHA256={action['descriptor_id']}"
    )


def _failure_is_safe(authority: dict[str, Any]) -> bool:
    return (
        authority["outcome"] == "j2_off_diagnostic_failed_no_claim"
        and authority["get"] == 4
        and authority["post"] == 0
        and authority["permanent_claims_created"] == 0
        and authority["visible_refreshes"] == 0
        and authority["driver_calls"] == 0
        and authority["terminal_state"] == "NOT_EXECUTED"
        and authority["safe_to_supersede_without_containment"] is True
    )


def _identity_values(report: dict[str, Any]) -> set[str]:
    action = report["action"]
    contract = report["contract"]
    return {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        contract["campaign_id"],
        contract["test_id"],
        contract["base_route"],
        contract["nvs_namespace"],
    }


def dry_validate(*, verify_source: bool = True) -> dict[str, Any]:
    if verify_source:
        source_validation = source.dry_validate()
        if source_validation.get("result") != "PASS":
            raise W7PackError("T4 V3 source dry validation did not PASS")
    report = build_white_report()
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    action = report["action"]
    expected_source = {
        "campaign_id": source_report["contract"]["campaign_id"],
        "contract_id": source_report["contract_id"],
        "descriptor_id": source_action["descriptor_id"],
        "action_id": source_action["action_id"],
    }
    observed_source = {
        "campaign_id": action["source_campaign_id"],
        "contract_id": action["source_contract_id"],
        "descriptor_id": action["source_descriptor_id"],
        "action_id": action["source_action_id"],
    }
    if observed_source != expected_source:
        raise W7PackError("W7 source binding differs from exact T4 V3")
    source_binding = report["contract"]["source"]
    failures = (
        source_binding["v1_diagnostic_failure_authority"],
        source_binding["v2_diagnostic_failure_authority"],
    )
    if (
        source_binding["stage"]
        != "t4-active-header-ca-r20-swap-confirmation-successor-v3"
        or source_binding["round"] != 4
        or source_binding["profile_id"]
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or source_binding["global_header"] != "active"
        or source_binding["waveform_binding"]["cs1"]["name"] != "commented"
        or source_binding["waveform_binding"]["cs2"]["name"] != "active"
        or not all(_failure_is_safe(item) for item in failures)
    ):
        raise W7PackError("W7 T4 V3 source or failed-attempt binding differs")
    failed_actions = tuple(item["action_id"] for item in failures)
    if len(set(failed_actions)) != 2:
        raise W7PackError("W7 failed T4 action registry overlaps")
    non_reusable = set(source.non_reusable_action_ids())
    if not set(failed_actions).issubset(non_reusable):
        raise W7PackError("W7 failed T4 actions are not permanently non-reusable")
    prior_reports = (w5.build_white_report(), w6.build_white_report())
    prior_values = set().union(*(_identity_values(item) for item in prior_reports))
    if _identity_values(report) & prior_values:
        raise W7PackError("W7 identity overlaps obsolete W5/W6")
    obsolete_white_actions = set(_obsolete_white_actions())
    if set(report["contract"]["rejected_obsolete_white_action_ids"]) != (
        obsolete_white_actions
    ):
        raise W7PackError("W7 obsolete white rejection registry differs")
    if action["action_id"] in non_reusable or action["action_id"] in (
        obsolete_white_actions
    ):
        raise W7PackError("W7 action reuses a predecessor action")
    completion = source_binding["completion_requirement"]
    if (
        completion["action_id"] != source_action["action_id"]
        or completion["terminal_state"] != "COMPLETE"
        or completion["result"] is not True
        or completion["campaign_complete"] is not True
        or completion["visible_refreshes"] != 1
        or completion["driver_called"] is not True
        or completion["driver_call_count_for_action"] != 1
        or completion["total_driver_call_count"] != 1
    ):
        raise W7PackError("W7 exact source completion requirement differs")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W7PackError("W7 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != (
        "/api/ec5/raw-p16-crossover-w7-after-t4-active-header-ca-r20-swap-"
        "confirmation-successor-v3-white-v1"
    ):
        raise W7PackError("W7 route differs")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-dry-validation"
        ),
        "result": "PASS",
        "offline_only": True,
        "source_validation_required": verify_source,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "factory_otp_white_only": True,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "source_t4_v3_campaign_contract_descriptor_action_exact": True,
        "source_t4_v1_v2_failed_no_claim_diagnostics_exact": True,
        "source_complete_evidence_required_before_live_white": True,
        "obsolete_w5_w6_permanently_rejected": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": artifacts_are_sealed(),
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source": deepcopy(source_binding),
    }


def main() -> int:
    print(
        json.dumps(build_white_report(), ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
