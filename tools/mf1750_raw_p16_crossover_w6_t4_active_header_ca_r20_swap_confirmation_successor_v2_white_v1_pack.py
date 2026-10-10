#!/usr/bin/env python3
"""Offline identities for W6 white paired only with the fresh T4 CA-R20 swap successor V2."""

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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as source,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as predecessor,
)


class W6PackError(RuntimeError):
    """Raised when W6 ceases to bind the exact fresh T4 successor V2 source."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = "w6-after-t4-active-header-ca-r20-swap-confirmation-successor-v2-white-v1"
    suffix: str = "W6_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE"
    nvs_namespace: str = "p16w6t4ca2_v1"
    nvs_key: str = "used_w6t4ca2"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W6_AFTER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V2_WHITE_V1_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-W6-AFTER-T4-ACTIVE-HEADER-CA-R20-SWAP-"
            "CONFIRMATION-SUCCESSOR-V2-WHITE-V1"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W6_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V2_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-w6-after-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v2-white-v1"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        # Keep the isolated PlatformIO environment intentionally short on
        # Windows so generated dependency-file paths stay below tool limits.
        return "ec5_p16_w6t4ca2_w1"

    @property
    def build_root(self) -> str:
        return "b-w6t4ca2-w1"


STAGE = "w6-after-t4-active-header-ca-r20-swap-confirmation-successor-v2-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_"
    "CONFIRMATION_SUCCESSOR_V2_WHITE_DEVICE_V1"
)
IDENTITY_REVISION = (
    "raw-p16-crossover-w6-t4-active-header-ca-r20-swap-confirmation-successor-v2-white-v1"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W6_AFTER_T4_ACTIVE_HEADER_CA_R20_"
    "SWAP_CONFIRMATION_SUCCESSOR_V2_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = legacy.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = legacy.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = legacy.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = legacy.FACTORY_WHITE_DTM_FNV1A

# Sealed after the isolated compile-only build was independently re-read.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_488,
        "bin_sha256": (
            "f87957cdb2c4ba472a7bf48bbec6db4334e03ccefe79af93de405ba09563e190"
        ),
        "elf_bytes": 13_215_008,
        "elf_sha256": (
            "78c2c873eeec08b690bc18d269501742a447c73380b9c27e6407b34f93ad7f8a"
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
        values["bin_bytes"] > 0
        and values["elf_bytes"] > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def _source_binding() -> dict[str, Any]:
    source_report = source.build_report()
    source_action = source_report["actions"][0]
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
        "v1_diagnostic_failure_authority": deepcopy(
            source_report["contract"]["v1_diagnostic_failure_authority"]
        ),
    }


def build_white_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    source_binding = _source_binding()
    action_seed = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "source_campaign_id": source_binding["campaign_id"],
        "source_contract_id": source_binding["contract_id"],
        "source_descriptor_id": source_binding["descriptor_id"],
        "source_action_id": source_binding["action_id"],
        "frame_sha256": FACTORY_WHITE_FRAME_SHA256,
        "cs1_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
        "cs2_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
    }
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-w6-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v2-white-descriptor-v1"
        ),
        "build_tag": CONFIG.build_tag,
        **action_seed,
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            f"CONFIRMATION_SUCCESSOR_V2_WHITE_ACTION_V1|{CONFIG.campaign_id}|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": (
            "mf1750-raw-p16-crossover-w6-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v2-white-contract-v1"
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
            "mf1750-raw-p16-crossover-w6-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v2-white-offline-identities-v1"
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
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W6_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        f"CONFIRMATION_SUCCESSOR_V2|SHA256={action['descriptor_id']}"
    )


def dry_validate(*, verify_source: bool = True) -> dict[str, Any]:
    if verify_source:
        source_validation = source.dry_validate()
        if source_validation.get("result") != "PASS":
            raise W6PackError("T4 source dry validation did not PASS")
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
        raise W6PackError("W6 source binding differs from exact T4")
    source_binding = report["contract"]["source"]
    v1_failure = source_binding["v1_diagnostic_failure_authority"]
    if (
        source_binding["stage"]
        != "t4-active-header-ca-r20-swap-confirmation-successor-v2"
        or source_binding["round"] != 4
        or source_binding["profile_id"]
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or source_binding["global_header"] != "active"
        or source_binding["waveform_binding"]["cs1"]["name"] != "commented"
        or source_binding["waveform_binding"]["cs2"]["name"] != "active"
        or v1_failure["outcome"] != "j2_off_diagnostic_failed_no_claim"
        or v1_failure["post"] != 0
        or v1_failure["permanent_claims_created"] != 0
        or v1_failure["visible_refreshes"] != 0
        or v1_failure["driver_calls"] != 0
        or v1_failure["terminal_state"] != "NOT_EXECUTED"
        or v1_failure["safe_to_supersede_without_containment"] is not True
    ):
        raise W6PackError("W6 T4 successor V2 source or V1 failure binding differs")
    prior_report = predecessor.build_white_report()
    prior_action = prior_report["action"]
    prior_values = {
        prior_report["contract_id"],
        prior_action["descriptor_id"],
        prior_action["action_id"],
        prior_report["contract"]["campaign_id"],
        prior_report["contract"]["test_id"],
        prior_report["contract"]["base_route"],
        prior_report["contract"]["nvs_namespace"],
    }
    fresh_values = {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        report["contract"]["campaign_id"],
        report["contract"]["test_id"],
        report["contract"]["base_route"],
        report["contract"]["nvs_namespace"],
    }
    if prior_values & fresh_values:
        raise W6PackError("W6 identity overlaps failed-source-era W5")
    if action["action_id"] in source.non_reusable_action_ids():
        raise W6PackError("W6 action reuses a predecessor action")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W6PackError("W6 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != (
        "/api/ec5/raw-p16-crossover-w6-after-t4-active-header-ca-r20-swap-"
        "confirmation-successor-v2-white-v1"
    ):
        raise W6PackError("W6 route differs")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w6-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v2-white-dry-validation"
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
        "source_t4_campaign_contract_descriptor_action_exact": True,
        "source_t4_v1_failed_no_claim_diagnostic_exact": True,
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
