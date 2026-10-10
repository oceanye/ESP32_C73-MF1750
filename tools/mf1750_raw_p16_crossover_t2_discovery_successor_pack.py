#!/usr/bin/env python3
"""Offline identity pack for the fresh RAW-P16 T2 CA coarse discovery.

The visible payload is byte-identical to the reviewed position-balanced T2-CA
atlas.  Only campaign identity and the discovery-only evidence boundary are
new.  This module never accesses a device, network, serial port, relay, or
camera.
"""

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
    mf1750_raw_p16_crossover_position_balanced_pack as base,
)


class DiscoveryPackError(RuntimeError):
    """Raised when the coarse-screen authority or successor contract differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t2-ca-coarse-discovery-successor"
    suffix: str = "T2_CA_COARSE_DISCOVERY_SUCCESSOR"
    global_header: str = "commented"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 1
    repeat_of: None = None
    nvs_namespace: str = "p16t2d_v1"
    nvs_key: str = "cur_t2d1"
    nvs_boot_key: str = "boot_t2d1"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_"
            "SUCCESSOR_V1_2026-08-30"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T2-CA-COARSE-DISCOVERY-SUCCESSOR-V1"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t2-ca-coarse-discovery-successor-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_raw_p16_crossover_t2_ca_coarse_discovery_successor_v1"

    @property
    def build_root(self) -> str:
        return "build-raw-p16-crossover-t2-ca-coarse-discovery-successor-v1"


STAGE = "t2-ca-coarse-discovery-successor"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T2_DISCOVERY_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-t2-ca-coarse-discovery-successor-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_COARSE_DISCOVERY_ONLY_T2_CA_PROFILE_SWAP_"
    "NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_ZERO_QUALIFIED_COLOURS"
)
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T2_CA_COARSE_DISCOVERY_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_ARMED_RAW_P16_T2_CA_COARSE_DISCOVERY_ACTION_ONCE"

CODE_ROWS = base.CODE_ROWS
GRID_Y_BY_ROW = base.GRID_Y_BY_ROW

COARSE_AUTHORITY_PATH = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T1_AC_20260830_V1"
    / "T1.white-normalized-coarse-screen-v1.json"
)
COARSE_AUTHORITY_BYTES = 293_550
COARSE_AUTHORITY_FILE_SHA256 = (
    "4abbcf56bfb390e8cfb394f67eb8d6209fc35d845d1b096b096234973f4f50ea"
)
COARSE_AUTHORITY_CANONICAL_SHA256 = (
    "3b080f2288c45f0ac5cdba9023b90a4f320d4b514bedece2372b72cf6b39d8ad"
)

ARTIFACTS = {
    STAGE: {
        "bin_bytes": 800_320,
        "bin_sha256": (
            "40c709929f5a7a8531ba2f07a3cea8eb8a60680855500df30b74f9de95d5593d"
        ),
        "elf_bytes": 13_294_820,
        "elf_sha256": (
            "649207981331df200180f5956233304935c7a49fc088bfedb036c67ebc467680"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def coarse_authority_binding() -> dict[str, Any]:
    return {
        "kind": "mf1750-raw-p16-crossover-t1-white-normalized-coarse-screen-v1",
        "path": str(COARSE_AUTHORITY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "bytes": COARSE_AUTHORITY_BYTES,
        "file_sha256": COARSE_AUTHORITY_FILE_SHA256,
        "canonical_integrity_sha256": COARSE_AUTHORITY_CANONICAL_SHA256,
        "screening_only": True,
        "eligible_for_t2_discovery": True,
        "formal_gate_evaluated": False,
        "formal_advance_to_t2_permitted": False,
        "qualified_colour_count": 0,
        "does_not_reverse_consumed_t1": True,
    }


def validate_coarse_authority(path: Path = COARSE_AUTHORITY_PATH) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise DiscoveryPackError(f"coarse-screen authority missing: {candidate}")
    payload = candidate.read_bytes()
    if len(payload) != COARSE_AUTHORITY_BYTES:
        raise DiscoveryPackError("coarse-screen authority byte count differs")
    if sha256_bytes(payload) != COARSE_AUTHORITY_FILE_SHA256:
        raise DiscoveryPackError("coarse-screen authority file SHA-256 differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryPackError("coarse-screen authority is not valid JSON") from error
    if not isinstance(value, dict):
        raise DiscoveryPackError("coarse-screen authority root is not an object")
    integrity = value.get("integrity")
    if not isinstance(integrity, dict):
        raise DiscoveryPackError("coarse-screen authority integrity is absent")
    unsigned = deepcopy(value)
    unsigned.pop("integrity", None)
    if (
        integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != COARSE_AUTHORITY_CANONICAL_SHA256
        or sha256_bytes(canonical_json(unsigned)) != COARSE_AUTHORITY_CANONICAL_SHA256
    ):
        raise DiscoveryPackError("coarse-screen canonical integrity differs")
    required = coarse_authority_binding()
    observed = {
        "kind": value.get("kind"),
        "screening_only": value.get("screening_only"),
        "eligible_for_t2_discovery": value.get("eligible_for_t2_discovery"),
        "formal_gate_evaluated": value.get("formal_gate_evaluated"),
        "formal_advance_to_t2_permitted": value.get("formal_advance_to_t2_permitted"),
        "qualified_colour_count": value.get("qualified_colour_count"),
        "does_not_reverse_consumed_t1": value.get("summary", {}).get(
            "does_not_reverse_consumed_t1"
        ),
    }
    for key in (
        "kind",
        "screening_only",
        "eligible_for_t2_discovery",
        "formal_gate_evaluated",
        "formal_advance_to_t2_permitted",
        "qualified_colour_count",
        "does_not_reverse_consumed_t1",
    ):
        if observed[key] != required[key]:
            raise DiscoveryPackError(f"coarse-screen authority {key} differs")
    return value


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    source = base.build_report("t2-ca")
    source_action = source["actions"][0]
    action = deepcopy(source_action)
    action.update(
        {
            "ordinal": 1,
            "role": "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ATLAS",
            "driver_role": "Source",
            "round": 1,
            "branch": (
                f"{CONFIG.variant_key}_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ATLAS"
            ),
            "prior_static_action_id": None,
            "repeat_of_stage": None,
            "boot_admission": {
                "campaign_boot_binding_key": CONFIG.nvs_boot_key,
                "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
                "required_prior_terminal_state": None,
                "required_prior_ordinal": None,
                "firmware_arm_gate": True,
                "firmware_execute_gate": True,
                "firmware_dispatch_gate": True,
                "reboot_resume_allowed": False,
                "post_containment_resume_allowed": False,
            },
        }
    )
    action.pop("descriptor_id", None)
    action.pop("action_id", None)
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-action-v1",
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "coarse_discovery_authority": coarse_authority_binding(),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ACTION_V1|"
            f"{CONFIG.variant_key}|1|{action['descriptor_id']}"
        ).encode("ascii")
    )

    source_contract = source["contract"]
    contract = deepcopy(source_contract)
    contract.update(
        {
            "schema": "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-contract-v1",
            "stage": STAGE,
            "variant_key": CONFIG.variant_key,
            "build_tag": CONFIG.build_tag,
            "test_id": CONFIG.test_id,
            "campaign_id": CONFIG.campaign_id,
            "base_route": CONFIG.base_route,
            "nvs_namespace": CONFIG.nvs_namespace,
            "nvs_key": CONFIG.nvs_key,
            "nvs_boot_key": CONFIG.nvs_boot_key,
            "classification": CLASSIFICATION,
            "actions": [action],
            "action_count": 1,
            "screening_only": True,
            "discovery_only": True,
            "formal_gate_evaluated": False,
            "formal_advance_to_t2_permitted": False,
            "qualified_colours": 0,
            "coarse_discovery_authority": coarse_authority_binding(),
        }
    )
    contract["analysis_priority"]["absolute_colour_claimed"] = False
    contract["analysis_priority"]["stable_new_colour_claimed"] = False
    contract["automatic_chaining"] = False
    contract["retry"] = False
    contract["recovery"] = False
    report = {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_stage": "t2-ca",
        "source_contract_id": source["contract_id"],
        "coarse_discovery_authority": coarse_authority_binding(),
        "actions": [action],
        "contract": contract,
    }
    report["contract_id"] = sha256_bytes(canonical_json(contract))
    return report


def dry_validate(*, verify_authority: bool = True) -> dict[str, Any]:
    if verify_authority:
        validate_coarse_authority()
    report = build_report()
    source = base.build_report("t2-ca")
    action = report["actions"][0]
    source_action = source["actions"][0]
    if action["frame"] != source_action["frame"]:
        raise DiscoveryPackError("successor frame differs from reviewed T2-CA")
    if action["cs1_dtm"] != source_action["cs1_dtm"]:
        raise DiscoveryPackError("successor CS1 DTM differs from reviewed T2-CA")
    if action["cs2_dtm"] != source_action["cs2_dtm"]:
        raise DiscoveryPackError("successor CS2 DTM differs from reviewed T2-CA")
    if action["waveform_binding"] != source_action["waveform_binding"]:
        raise DiscoveryPackError("successor CA waveform differs from reviewed T2-CA")
    legacy_ids = {
        source["contract_id"],
        source_action["descriptor_id"],
        source_action["action_id"],
        source["contract"]["campaign_id"],
        source["contract"]["test_id"],
        source["contract"]["base_route"],
        source["contract"]["nvs_namespace"],
    }
    fresh_ids = {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        report["contract"]["campaign_id"],
        report["contract"]["test_id"],
        report["contract"]["base_route"],
        report["contract"]["nvs_namespace"],
    }
    if legacy_ids & fresh_ids:
        raise DiscoveryPackError("successor identity overlaps reviewed T2-CA")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "authority_verified": verify_authority,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "same_frame_dtm_and_ca_waveform_as_reviewed_t2": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "screening_only": True,
        "eligible_for_t2_discovery": True,
        "formal_gate_evaluated": False,
        "formal_advance_to_t2_permitted": False,
        "qualified_colour_count": 0,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "coarse_discovery_authority": coarse_authority_binding(),
    }
