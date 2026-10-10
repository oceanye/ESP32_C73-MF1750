#!/usr/bin/env python3
"""Offline identities for W4 white paired only with the fresh T3 V2 atlas."""

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
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as source,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as predecessor,
)


class W4V2PackError(RuntimeError):
    """Raised when W4 V2 ceases to bind the exact fresh T3 V2 source."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = "w4-after-t3-ac-profile-following-successor-v2-white-v1"
    suffix: str = "W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE"
    nvs_namespace: str = "p16w4pf2_v1"
    nvs_key: str = "used_w4pf21"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2_WHITE_V1_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-W4-AFTER-T3-AC-PROFILE-FOLLOWING-"
            "SUCCESSOR-V2-WHITE-V1"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-w4-after-t3-ac-profile-following-"
            "successor-v2-white-v1"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return (
            "ec5_raw_p16_crossover_w4_after_t3_ac_profile_following_"
            "successor_v2_white_v1"
        )

    @property
    def build_root(self) -> str:
        return (
            "build-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-v2-white-v1"
        )


STAGE = "w4-after-t3-ac-profile-following-successor-v2-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
    "SUCCESSOR_V2_WHITE_DEVICE_V1"
)
IDENTITY_REVISION = (
    "raw-p16-crossover-w4-t3-ac-profile-following-successor-v2-white-v1"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
    "SUCCESSOR_V2_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = legacy.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = legacy.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = legacy.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = legacy.FACTORY_WHITE_DTM_FNV1A

# Sealed from the isolated compile-only build and then re-read from disk.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_296,
        "bin_sha256": "311c30e3e3541108292bd135716d398e22942c34b7b2f25eaa90dcf486215093",
        "elf_bytes": 13_214_980,
        "elf_sha256": "9e6190de7783a32564120ed03edbde815fb60ccb30a3fafb140f19ffd3a7e487",
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
        "waveform_binding": deepcopy(source_action["waveform_binding"]),
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
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-v2-white-descriptor-v1"
        ),
        "build_tag": CONFIG.build_tag,
        **action_seed,
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
            f"SUCCESSOR_V2_WHITE_ACTION_V1|{CONFIG.campaign_id}|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": (
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-v2-white-contract-v1"
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
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-v2-white-offline-identities-v1"
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
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
        f"SUCCESSOR_V2|SHA256={action['descriptor_id']}"
    )


def dry_validate(*, verify_source: bool = True) -> dict[str, Any]:
    if verify_source:
        source_validation = source.dry_validate()
        if source_validation.get("result") != "PASS":
            raise W4V2PackError("T3 V2 source dry validation did not PASS")
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
        raise W4V2PackError("W4 V2 source binding differs from exact T3 V2")
    source_binding = report["contract"]["source"]
    if (
        source_binding["stage"] != "t3-ac-profile-following-successor-v2"
        or source_binding["round"] != 3
        or source_binding["profile_id"]
        != "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
        or source_binding["waveform_binding"]["cs1"]["name"] != "active"
        or source_binding["waveform_binding"]["cs2"]["name"] != "commented"
    ):
        raise W4V2PackError("W4 V2 source profile tuple differs")
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
        raise W4V2PackError("W4 V2 identity overlaps W4 V1")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W4V2PackError("W4 V2 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != (
        "/api/ec5/raw-p16-crossover-w4-after-t3-ac-profile-following-"
        "successor-v2-white-v1"
    ):
        raise W4V2PackError("W4 V2 route differs")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-v2-white-dry-validation"
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
        "source_t3_v2_campaign_contract_descriptor_action_exact": True,
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
