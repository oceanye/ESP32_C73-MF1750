#!/usr/bin/env python3
"""Offline identity pack for an exposure-corrected T2 discovery repeat.

The visible frame, controller DTMs, and CA waveform are frozen to the consumed
T2 discovery-successor V1.  V2 exists only because the V1 camera normalization
was underexposed; it is a fresh one-action discovery campaign, not a retry of a
consumed action and not a formal colour-qualification gate.
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
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as frozen,
)


class DiscoveryV2PackError(RuntimeError):
    """Raised when the frozen V1 lineage or V2 contract differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t2-ca-coarse-discovery-successor-v2"
    suffix: str = "T2_CA_COARSE_DISCOVERY_SUCCESSOR_V2"
    global_header: str = "commented"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 2
    repeat_of: str = frozen.STAGE
    nvs_namespace: str = "p16t2d_v2"
    nvs_key: str = "cur_t2d2"
    nvs_boot_key: str = "boot_t2d2"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V2"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_"
            "SUCCESSOR_V2_2026-08-30"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T2-CA-COARSE-DISCOVERY-SUCCESSOR-V2"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V2"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t2-ca-coarse-discovery-successor-v2"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_raw_p16_crossover_t2_ca_coarse_discovery_successor_v2"

    @property
    def build_root(self) -> str:
        return "build-raw-p16-crossover-t2-ca-coarse-discovery-successor-v2"


STAGE = "t2-ca-coarse-discovery-successor-v2"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T2_DISCOVERY_DEVICE_V2"
IDENTITY_REVISION = "raw-p16-crossover-t2-ca-coarse-discovery-successor-v2"
CLASSIFICATION = (
    "EXPERIMENTAL_EXPOSURE_CORRECTED_COARSE_DISCOVERY_ONLY_T2_CA_REPEAT_"
    "NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_ZERO_QUALIFIED_COLOURS"
)
FACTORY_WHITE_ANCHOR_ROLE = (
    "EXTERNAL_EXPOSURE_MINUS3_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED"
)
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T2_CA_COARSE_DISCOVERY_V2_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_ARMED_RAW_P16_T2_CA_COARSE_DISCOVERY_V2_ACTION_ONCE"

CODE_ROWS = frozen.CODE_ROWS
GRID_Y_BY_ROW = frozen.GRID_Y_BY_ROW

REPEAT_AUTHORITY_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V1"
    / "T2.white-normalized-coarse-screen-v1.json"
)
REPEAT_AUTHORITY_BYTES = 187_744
REPEAT_AUTHORITY_FILE_SHA256 = (
    "de4e790fd3ccb23314eec977b404eee74e7b937dc7522f195bcf07114ef2e856"
)
REPEAT_AUTHORITY_CANONICAL_SHA256 = (
    "8e55cc7910c8b879abb050be97f84acf94b8a9e5c345f2537dd47a715daf4c4d"
)

CAPTURE_PLAN = {
    "camera_logical_id": "USB_VID_32E4_PID_4801",
    "camera_friendly_name": "48MP USB Camera",
    "exposure": -3,
    "frame_width": 4000,
    "frame_height": 3000,
    "retained_atlas_frame_count": 3,
    "pre_white_reference_required": True,
    "post_white_reference_required": True,
    "white_reference_min_lstar": 25.0,
    "automatic_threshold_relaxation": False,
    "camera_relative_screening_only": True,
}

ARTIFACTS = {
    STAGE: {
        "bin_bytes": 801_088,
        "bin_sha256": (
            "ce8e85b7d88fc25bb41a04a08b6b29c6227396890aee53244e5033f9df8bbed8"
        ),
        "elf_bytes": 13_294_940,
        "elf_sha256": (
            "05b25c8699a861e301367a77e53f9a39de57d97a140f8609b5f2935c381d8f1d"
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
    """Retain the frozen T1 authority interface expected by the host adapter."""

    return frozen.coarse_authority_binding()


def validate_coarse_authority(path: Path = frozen.COARSE_AUTHORITY_PATH) -> dict[str, Any]:
    return frozen.validate_coarse_authority(path)


def repeat_authority_binding() -> dict[str, Any]:
    source_report = frozen.build_report()
    source_action = source_report["actions"][0]
    return {
        "kind": (
            "mf1750-raw-p16-crossover-t2-discovery-successor-"
            "white-normalized-coarse-screen-v1"
        ),
        "path": str(REPEAT_AUTHORITY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "bytes": REPEAT_AUTHORITY_BYTES,
        "file_sha256": REPEAT_AUTHORITY_FILE_SHA256,
        "canonical_integrity_sha256": REPEAT_AUTHORITY_CANONICAL_SHA256,
        "source_campaign_id": source_report["contract"]["campaign_id"],
        "source_contract_id": source_report["contract_id"],
        "source_descriptor_id": source_action["descriptor_id"],
        "source_action_id": source_action["action_id"],
        "state": "T2_SUCCESSOR_COARSE_SCREEN_NOT_ALL_PASS",
        "classification_counts": {"PASS": 0, "REVIEW": 0, "FAIL": 16},
        "coarse_profile_comparison_ready": False,
        "diagnostic_reason": "INSUFFICIENT_VALID_WHITE_REFERENCE_COVERAGE",
        "white_reference_min_lstar": 25.0,
        "underexposed_measurement_only": True,
        "visible_payload_failure_claimed": False,
        "authorizes_fresh_discovery_repeat_only": True,
        "formal_gate_evaluated": False,
        "formal_gate_changed": False,
        "qualified_colour_count": 0,
    }


def validate_repeat_authority(
    path: Path = REPEAT_AUTHORITY_PATH,
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise DiscoveryV2PackError(f"repeat authority missing: {candidate}")
    payload = candidate.read_bytes()
    if len(payload) != REPEAT_AUTHORITY_BYTES:
        raise DiscoveryV2PackError("repeat authority byte count differs")
    if sha256_bytes(payload) != REPEAT_AUTHORITY_FILE_SHA256:
        raise DiscoveryV2PackError("repeat authority file SHA-256 differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryV2PackError("repeat authority is not valid JSON") from error
    if not isinstance(value, dict):
        raise DiscoveryV2PackError("repeat authority root is not an object")
    integrity = value.get("integrity")
    unsigned = deepcopy(value)
    unsigned.pop("integrity", None)
    if (
        not isinstance(integrity, dict)
        or integrity.get("algorithm")
        != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != REPEAT_AUTHORITY_CANONICAL_SHA256
        or sha256_bytes(canonical_json(unsigned))
        != REPEAT_AUTHORITY_CANONICAL_SHA256
    ):
        raise DiscoveryV2PackError("repeat authority canonical integrity differs")
    summary = value.get("summary")
    if not isinstance(summary, dict):
        raise DiscoveryV2PackError("repeat authority summary is absent")
    expected = repeat_authority_binding()
    observed = {
        "kind": value.get("kind"),
        "state": summary.get("state"),
        "classification_counts": summary.get("classification_counts"),
        "coarse_profile_comparison_ready": value.get(
            "coarse_profile_comparison_ready"
        ),
        "formal_gate_evaluated": value.get("formal_gate_evaluated"),
        "formal_gate_changed": value.get("formal_gate_changed"),
        "qualified_colour_count": value.get("qualified_colour_count"),
    }
    for key in (
        "kind",
        "state",
        "classification_counts",
        "coarse_profile_comparison_ready",
        "formal_gate_evaluated",
        "formal_gate_changed",
        "qualified_colour_count",
    ):
        if observed[key] != expected[key]:
            raise DiscoveryV2PackError(f"repeat authority {key} differs")
    reasons = {
        item.get("diagnostic_reason")
        for item in value.get("group_results", [])
        if isinstance(item, dict)
    }
    if reasons != {expected["diagnostic_reason"]}:
        raise DiscoveryV2PackError("repeat authority diagnostic reason differs")
    return value


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    source = frozen.build_report()
    source_action = source["actions"][0]
    action = deepcopy(source_action)
    action.update(
        {
            "ordinal": 1,
            "role": "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_V2_ATLAS",
            "driver_role": "Source",
            "round": 2,
            "branch": (
                f"{CONFIG.variant_key}_"
                "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_V2_ATLAS"
            ),
            "prior_static_action_id": source_action["action_id"],
            "repeat_of_stage": frozen.STAGE,
            "repeat_of_campaign_id": source["contract"]["campaign_id"],
            "repeat_of_contract_id": source["contract_id"],
            "repeat_authority": repeat_authority_binding(),
            "capture_plan": deepcopy(CAPTURE_PLAN),
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
        "schema": (
            "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-"
            "successor-v2-action-v1"
        ),
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "coarse_discovery_authority": coarse_authority_binding(),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_"
            f"SUCCESSOR_V2_ACTION_V1|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )

    contract = deepcopy(source["contract"])
    contract.update(
        {
            "schema": (
                "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-"
                "successor-v2-contract-v1"
            ),
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
            "exposure_corrected_repeat": True,
            "formal_gate_evaluated": False,
            "formal_advance_to_t2_permitted": False,
            "qualified_colours": 0,
            "coarse_discovery_authority": coarse_authority_binding(),
            "repeat_authority": repeat_authority_binding(),
            "capture_plan": deepcopy(CAPTURE_PLAN),
            "repeat_of": {
                "stage": frozen.STAGE,
                "campaign_id": source["contract"]["campaign_id"],
                "contract_id": source["contract_id"],
                "descriptor_id": source_action["descriptor_id"],
                "action_id": source_action["action_id"],
            },
        }
    )
    contract["analysis_priority"]["absolute_colour_claimed"] = False
    contract["analysis_priority"]["stable_new_colour_claimed"] = False
    contract["automatic_chaining"] = False
    contract["retry"] = False
    contract["recovery"] = False
    report = {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-"
            "successor-v2-offline-identities-v1"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_stage": frozen.STAGE,
        "source_contract_id": source["contract_id"],
        "coarse_discovery_authority": coarse_authority_binding(),
        "repeat_authority": repeat_authority_binding(),
        "capture_plan": deepcopy(CAPTURE_PLAN),
        "actions": [action],
        "contract": contract,
    }
    report["contract_id"] = sha256_bytes(canonical_json(contract))
    return report


def dry_validate(
    *, verify_authority: bool = True, verify_repeat_authority: bool = True
) -> dict[str, Any]:
    if verify_authority:
        validate_coarse_authority()
    if verify_repeat_authority:
        validate_repeat_authority()
    report = build_report()
    source = frozen.build_report()
    action = report["actions"][0]
    source_action = source["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding"):
        if action[key] != source_action[key]:
            raise DiscoveryV2PackError(f"V2 {key} differs from frozen T2 V1")
    frozen_ids = {
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
    if frozen_ids & fresh_ids:
        raise DiscoveryV2PackError("V2 identity overlaps consumed T2 V1")
    if len(CONFIG.nvs_namespace) > 15:
        raise DiscoveryV2PackError("NVS namespace exceeds ESP32 limit")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-"
            "successor-v2-dry-validation"
        ),
        "result": "PASS",
        "offline_only": True,
        "authority_verified": verify_authority,
        "repeat_authority_verified": verify_repeat_authority,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "same_frame_dtm_and_ca_waveform_as_consumed_t2_v1": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "screening_only": True,
        "exposure_corrected_repeat": True,
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
        "repeat_authority": repeat_authority_binding(),
        "capture_plan": deepcopy(CAPTURE_PLAN),
    }
