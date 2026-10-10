#!/usr/bin/env python3
"""Offline identities for the fresh T4 matched A/C controller swap.

This stage is the causal counterpart to the completed T3 V2 action.  It keeps
the active global header, packed frame, DTM streams, geometry, and raw codes
byte-identical, and swaps only the complete 535-byte R20 profiles between
controllers: CS1 receives the commented profile and CS2 the active profile.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as source,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_v2_white_pack as white,
)


class T4MatchedSwapPackError(RuntimeError):
    """Raised when a frozen source, containment, or fresh identity differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t4-active-header-ca-r20-swap-confirmation-v1"
    suffix: str = "T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1"
    global_header: str = "active"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 4
    nvs_namespace: str = "p16t4ca_v1"
    nvs_key: str = "cur_t4ca1"
    nvs_boot_key: str = "boot_t4ca1"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_V1_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-SWAP-CONFIRMATION-V1"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1"

    @property
    def build_root(self) -> str:
        return "build-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1"


STAGE = "t4-active-header-ca-r20-swap-confirmation-v1"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_HUMAN_PRIMARY_MATCHED_R20_SWAP_CONFIRMATION_ONLY_"
    "ACTIVE_HEADER_CA_NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_"
    "ZERO_QUALIFIED_COLOURS"
)
FACTORY_WHITE_ANCHOR_ROLE = source.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_ACTION_ONCE"
)

CODE_ROWS = source.CODE_ROWS
GRID_Y_BY_ROW = source.GRID_Y_BY_ROW
PROFILE_ID = "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
GLOBAL_TUPLE_ID = hashlib.sha256(PROFILE_ID.encode("ascii")).hexdigest()
HUMAN_OBSERVATION_PLAN = {
    "primary_judgement": "HUMAN_VISUAL_MATCHED_R20_SWAP_CONFIRMATION_REVIEW",
    "operator_observation_required": True,
    "camera_required_for_decision": False,
    "camera_evidence_optional": True,
    "camera_evidence_only": True,
    "required_retained_camera_frame_count": 0,
    "absolute_colour_claimed": False,
    "stable_new_colour_claimed": False,
    "profile_following_proven_by_this_action": False,
    "matched_swap_confirmation_earned_before_observation": False,
    "qualified_colour_count": 0,
}

T3_ACTION_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2"
    / "action-01-position-balanced-atlas.json"
)
T3_ACTION_BYTES = 64_782
T3_ACTION_FILE_SHA256 = (
    "e7ba8d10f5428372e0462835274cfdebeef5f19d0b8ab354fdcdfadf534a4ec3"
)
T3_ACTION_CANONICAL_SHA256 = (
    "4070a4381d7641f98bef0c84ed2fc2f885a5795ba43599f62812d9e4918c2b4e"
)
W4_ACTION_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_WHITE_20260831_V1"
    / "action-01-factory-otp-white.json"
)
W4_ACTION_BYTES = 30_300
W4_ACTION_FILE_SHA256 = (
    "11196c4cc5dade801d99b647e08fcccee02521acfbe0d3785c77d05a4697fb98"
)
W4_ACTION_CANONICAL_SHA256 = (
    "74ff3af94ebb4c2f58270d7cd9672a359b2e21332149a8a422feaa3967fd753d"
)

# Sealed after a clean compile-only build and independent artifact readback.
ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 803_680,
        "bin_sha256": (
            "fa6eb4a8c974b0316d0ab541cde22112645f1848e6d762b39d06ddfc9c3a0936"
        ),
        "elf_bytes": 13_299_712,
        "elf_sha256": (
            "6d30d491e669c00069f5e0ae3348501a2814e657b986dd0eea435c73e0a06ccf"
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


def _repo_relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _read_exact_json(
    path: Path,
    *,
    byte_count: int,
    file_sha256: str,
    canonical_sha256: str,
    label: str,
) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise T4MatchedSwapPackError(f"{label} is missing or not regular")
    payload = path.read_bytes()
    if len(payload) != byte_count or sha256_bytes(payload) != file_sha256:
        raise T4MatchedSwapPackError(f"{label} file binding differs")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4MatchedSwapPackError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise T4MatchedSwapPackError(f"{label} root differs")
    body = dict(value)
    integrity = body.pop("integrity", None)
    if not isinstance(integrity, Mapping):
        raise T4MatchedSwapPackError(f"{label} integrity missing")
    observed = sha256_bytes(canonical_json(body))
    recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if observed != canonical_sha256 or recorded != canonical_sha256:
        raise T4MatchedSwapPackError(f"{label} canonical binding differs")
    return value


@lru_cache(maxsize=1)
def _source_report() -> dict[str, Any]:
    return source.build_report()


@lru_cache(maxsize=1)
def _white_report() -> dict[str, Any]:
    return white.build_white_report()


def completed_t3_v2_action_binding() -> dict[str, Any]:
    report = _source_report()
    action = report["actions"][0]
    return {
        "kind": "mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v2-result",
        "path": _repo_relative(T3_ACTION_PATH),
        "bytes": T3_ACTION_BYTES,
        "file_sha256": T3_ACTION_FILE_SHA256,
        "canonical_integrity_sha256": T3_ACTION_CANONICAL_SHA256,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "profile_id": action["profile_id"],
        "global_header": action["global_header"],
        "cs1_profile": action["waveform_binding"]["cs1"]["name"],
        "cs2_profile": action["waveform_binding"]["cs2"]["name"],
        "outcome": "complete_pass",
        "terminal_state": "COMPLETE",
        "visible_refreshes": 1,
    }


def completed_w4_white_action_binding() -> dict[str, Any]:
    report = _white_report()
    action = report["action"]
    return {
        "kind": "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-successor-v2-white-result",
        "path": _repo_relative(W4_ACTION_PATH),
        "bytes": W4_ACTION_BYTES,
        "file_sha256": W4_ACTION_FILE_SHA256,
        "canonical_integrity_sha256": W4_ACTION_CANONICAL_SHA256,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source_action_id": action["source_action_id"],
        "outcome": "complete_pass",
        "terminal_state": "COMPLETE",
        "visible_refreshes": 1,
        "formal_full_panel_white_evidence": False,
        "fresh_operator_clean_white_confirmation_required": True,
    }


def validate_completed_t3_v2_action() -> dict[str, Any]:
    value = _read_exact_json(
        T3_ACTION_PATH,
        byte_count=T3_ACTION_BYTES,
        file_sha256=T3_ACTION_FILE_SHA256,
        canonical_sha256=T3_ACTION_CANONICAL_SHA256,
        label="completed T3 V2 action",
    )
    expected = completed_t3_v2_action_binding()
    action = value.get("action", {})
    terminal = value.get("terminal_report", {})
    if (
        value.get("kind") != expected["kind"]
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or action.get("action_id") != expected["action_id"]
        or action.get("descriptor_id") != expected["descriptor_id"]
        or action.get("profile_id") != expected["profile_id"]
        or action.get("global_header") != "active"
        or action.get("waveform_binding", {}).get("cs1", {}).get("name") != "active"
        or action.get("waveform_binding", {}).get("cs2", {}).get("name") != "commented"
        or terminal.get("campaign_id") != expected["campaign_id"]
        or terminal.get("contract_id") != expected["contract_id"]
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("campaign_complete") is not True
    ):
        raise T4MatchedSwapPackError("completed T3 V2 action semantics differ")
    return {"binding": expected, "validated": True}


def validate_completed_w4_white_action() -> dict[str, Any]:
    value = _read_exact_json(
        W4_ACTION_PATH,
        byte_count=W4_ACTION_BYTES,
        file_sha256=W4_ACTION_FILE_SHA256,
        canonical_sha256=W4_ACTION_CANONICAL_SHA256,
        label="completed W4 white action",
    )
    expected = completed_w4_white_action_binding()
    action = value.get("action", {})
    terminal = value.get("terminal_report", {})
    if (
        value.get("kind") != expected["kind"]
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or action.get("action_id") != expected["action_id"]
        or action.get("descriptor_id") != expected["descriptor_id"]
        or action.get("source_action_id") != expected["source_action_id"]
        or terminal.get("campaign_id") != expected["campaign_id"]
        or terminal.get("contract_id") != expected["contract_id"]
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("campaign_complete") is not True
    ):
        raise T4MatchedSwapPackError("completed W4 white action semantics differ")
    return {"binding": expected, "validated": True}


def validate_authorities() -> dict[str, Any]:
    return {
        "predecessor_chain": source.validate_authorities(),
        "completed_t3_v2_action": validate_completed_t3_v2_action(),
        "completed_w4_white_action": validate_completed_w4_white_action(),
    }


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (
        *source.non_reusable_action_ids(),
        _source_report()["actions"][0]["action_id"],
        _white_report()["action"]["action_id"],
    )
    if len(values) != len(set(values)):
        raise T4MatchedSwapPackError("predecessor action registry overlaps")
    return values


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = ARTIFACTS[STAGE]
    return (
        int(values["bin_bytes"]) > 0
        and int(values["elf_bytes"]) > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def external_containment_contract() -> dict[str, Any]:
    return {
        "outside_campaign": True,
        "factory_otp_white_before_required": True,
        "factory_otp_white_after_required": True,
        "completed_w4_machine_white_anchor_present": True,
        "fresh_operator_clean_white_confirmation_required": True,
        "formal_full_panel_white_evidence": False,
        "human_observation_required": True,
        "white_actions_in_campaign": 0,
    }


def _swapped_profile() -> dict[str, Any]:
    source_profile = deepcopy(_source_report()["actions"][0]["waveform_binding"])
    source_profile["cs1"], source_profile["cs2"] = (
        source_profile["cs2"],
        source_profile["cs1"],
    )
    source_profile["id"] = PROFILE_ID
    source_profile["global_header"] = "active"
    source_profile["global_tuple_id"] = GLOBAL_TUPLE_ID
    return source_profile


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    source_report = _source_report()
    source_action = source_report["actions"][0]
    profile = _swapped_profile()
    source_binding = completed_t3_v2_action_binding()
    white_binding = completed_w4_white_action_binding()

    action = deepcopy(source_action)
    for key in (
        "descriptor_id",
        "action_id",
        "supersedes_failed_unmutated_v1_action_id",
        "v1_terminal_failure_authority",
        "address_resolution_boundary",
    ):
        action.pop(key, None)
    action.update(
        {
            "ordinal": 1,
            "role": "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_ATLAS",
            "driver_role": "Source",
            "round": 4,
            "branch": (
                f"{CONFIG.variant_key}_"
                "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_ATLAS"
            ),
            "global_header": "active",
            "profile_id": PROFILE_ID,
            "global_tuple_id": GLOBAL_TUPLE_ID,
            "waveform_binding": profile,
            "prior_static_action_id": source_action["action_id"],
            "repeat_of_stage": source.STAGE,
            "matched_swap_of_action_id": source_action["action_id"],
            "source_action_authority": source_binding,
            "pre_white_action_evidence": white_binding,
            "human_observation_plan": deepcopy(HUMAN_OBSERVATION_PLAN),
            "boot_admission": {
                "campaign_boot_binding_key": CONFIG.nvs_boot_key,
                "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
                "firmware_arm_gate": True,
                "firmware_execute_gate": True,
                "firmware_dispatch_gate": True,
                "reboot_resume_allowed": False,
                "post_containment_resume_allowed": False,
            },
        }
    )
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-action-v1",
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "non_reusable_action_ids": list(non_reusable_action_ids()),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            f"CONFIRMATION_ACTION_V1|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )

    contract = {
        "schema": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-contract-v1",
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
        "profile": profile,
        "geometry": deepcopy(source_report["contract"]["geometry"]),
        "analysis_priority": deepcopy(source_report["contract"]["analysis_priority"]),
        "actions": [action],
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "external_containment": external_containment_contract(),
        "source_action_authority": source_binding,
        "pre_white_action_evidence": white_binding,
        "human_observation_plan": deepcopy(HUMAN_OBSERVATION_PLAN),
        "non_reusable_action_ids": list(non_reusable_action_ids()),
        "matched_swap_confirmation_only": True,
        "same_global_header_as_source": True,
        "same_layout_frame_and_dtm_as_source": True,
        "only_controller_r20_assignment_swapped": True,
        "profile_following_proven": False,
        "formal_gate_evaluated": False,
        "colour_qualification": False,
        "qualified_colours": 0,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "mid_refresh_power_cut": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": source_binding,
        "pre_white_action_evidence": white_binding,
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


@lru_cache(maxsize=1)
def _prior_identity_values() -> frozenset[str]:
    values = set(source._prior_identity_values())  # noqa: SLF001
    for report, action_key in (
        (_source_report(), "actions"),
        (_white_report(), "action"),
    ):
        action = (
            report[action_key][0] if action_key == "actions" else report[action_key]
        )
        values.update(
            {
                report["contract_id"],
                action["descriptor_id"],
                action["action_id"],
                report["contract"]["campaign_id"],
                report["contract"]["test_id"],
                report["contract"]["base_route"],
                report["contract"]["nvs_namespace"],
            }
        )
    return frozenset(values)


def dry_validate(*, verify_authorities: bool = True) -> dict[str, Any]:
    if verify_authorities:
        validate_authorities()
    report = build_report()
    action = report["actions"][0]
    source_action = _source_report()["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm"):
        if action[key] != source_action[key]:
            raise T4MatchedSwapPackError(f"T4 matched {key} differs")
    profile = action["waveform_binding"]
    source_profile = source_action["waveform_binding"]
    if (
        action["global_header"] != "active"
        or profile["global_header"] != source_profile["global_header"]
        or profile["cs1"] != source_profile["cs2"]
        or profile["cs2"] != source_profile["cs1"]
        or profile["cs1"]["name"] != "commented"
        or profile["cs2"]["name"] != "active"
        or action["round"] != 4
    ):
        raise T4MatchedSwapPackError("T4 matched CA tuple differs")
    if action["action_id"] in non_reusable_action_ids():
        raise T4MatchedSwapPackError("T4 action reuses a consumed action")
    fresh_values = {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        report["contract"]["campaign_id"],
        report["contract"]["test_id"],
        report["contract"]["base_route"],
        report["contract"]["nvs_namespace"],
    }
    if fresh_values & _prior_identity_values():
        raise T4MatchedSwapPackError("T4 identity overlaps a predecessor")
    if len(CONFIG.nvs_namespace) > 15:
        raise T4MatchedSwapPackError("T4 NVS namespace exceeds ESP32 limit")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-dry-validation-v1",
        "result": "PASS",
        "offline_only": True,
        "authority_verified": verify_authorities,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "consumed_actions_non_reusable": True,
        "profile_tuple": "ACTIVE_GLOBAL__CS1_COMMENTED535__CS2_ACTIVE535",
        "same_layout_frame_and_dtm_as_t3_v2": True,
        "only_controller_r20_assignment_swapped": True,
        "round": 4,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source_action_authority": completed_t3_v2_action_binding(),
        "pre_white_action_evidence": completed_w4_white_action_binding(),
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "artifacts_sealed": artifacts_are_sealed(),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
