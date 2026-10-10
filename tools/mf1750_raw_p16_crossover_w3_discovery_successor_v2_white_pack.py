#!/usr/bin/env python3
"""Offline identity pack for W3 after the exposure-corrected T2 V2 atlas."""

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
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as source,
)


class W3PackError(RuntimeError):
    """Raised when W3 ceases to bind the exact fresh T2 V2 source."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = "w3-after-t2-coarse-discovery-successor-v2"
    suffix: str = "W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2"
    nvs_namespace: str = "p16w3d_v1"
    nvs_key: str = "used_w3d1"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_"
            "SUCCESSOR_V2_WHITE_V1_2026-08-30"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-W3-AFTER-T2-COARSE-DISCOVERY-"
            "SUCCESSOR-V2-WHITE-V1"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_"
            "SUCCESSOR_V2_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-w3-after-t2-coarse-discovery-"
            "successor-v2-white-v1"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return (
            "ec5_raw_p16_crossover_w3_after_t2_coarse_discovery_"
            "successor_v2_white_v1"
        )

    @property
    def build_root(self) -> str:
        return (
            "build-raw-p16-crossover-w3-t2-discovery-"
            "successor-v2-white-v1"
        )


STAGE = "w3-after-t2-coarse-discovery-successor-v2"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2_WHITE_DEVICE_V1"
)
IDENTITY_REVISION = "raw-p16-crossover-w3-discovery-successor-v2-white-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W3_AFTER_T2_DISCOVERY_"
    "SUCCESSOR_V2_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = legacy.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = legacy.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = legacy.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = legacy.FACTORY_WHITE_DTM_FNV1A

WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_200,
        "bin_sha256": (
            "40c4be2f1213b61e68482e94d482217e8e4f8db4c7102074575a9da81a3f0ee2"
        ),
        "elf_bytes": 13_214_964,
        "elf_sha256": (
            "84c593afa474fbe8facdb78a5f4db6f88f96807c835bad0e60d21962c0bf3ecd"
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
        "coarse_discovery_authority": source.coarse_authority_binding(),
        "repeat_authority": source.repeat_authority_binding(),
        "capture_plan": deepcopy(source.CAPTURE_PLAN),
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
            "mf1750-raw-p16-crossover-w3-discovery-successor-v2-"
            "white-descriptor-v1"
        ),
        "build_tag": CONFIG.build_tag,
        **action_seed,
    }
    action = {
        **action_seed,
        "descriptor_id": sha256_bytes(canonical_json(descriptor)),
    }
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2_"
            f"WHITE_ACTION_V1|{CONFIG.campaign_id}|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": (
            "mf1750-raw-p16-crossover-w3-discovery-successor-v2-"
            "white-contract-v1"
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
        "camera_relative_screening_only": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w3-discovery-successor-v2-"
            "white-offline-identities-v1"
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
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2|"
        f"SHA256={action['descriptor_id']}"
    )


def dry_validate(
    *, verify_source_authority: bool = True, verify_repeat_authority: bool = True
) -> dict[str, Any]:
    if verify_source_authority:
        source.validate_coarse_authority()
    if verify_repeat_authority:
        source.validate_repeat_authority()
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
        raise W3PackError("W3 source binding differs from exact T2 V2")
    frozen_source = source.frozen.build_report()
    frozen_action = frozen_source["actions"][0]
    frozen_values = {
        frozen_source["contract_id"],
        frozen_action["descriptor_id"],
        frozen_action["action_id"],
        frozen_source["contract"]["campaign_id"],
        frozen_source["contract"]["test_id"],
        frozen_source["contract"]["base_route"],
        frozen_source["contract"]["nvs_namespace"],
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
    if frozen_values & fresh_values:
        raise W3PackError("W3 identity overlaps consumed discovery V1")
    if len(CONFIG.nvs_namespace) > 15:
        raise W3PackError("NVS namespace exceeds ESP32 limit")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w3-discovery-successor-v2-"
            "white-dry-validation"
        ),
        "result": "PASS",
        "offline_only": True,
        "source_authority_verified": verify_source_authority,
        "repeat_authority_verified": verify_repeat_authority,
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
        "source_t2_v2_campaign_contract_descriptor_action_exact": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source": deepcopy(report["contract"]["source"]),
    }


def main() -> int:
    print(json.dumps(build_white_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
