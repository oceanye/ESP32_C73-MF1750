#!/usr/bin/env python3
"""Offline identities for one fresh AC profile-following review atlas.

The visible frame and controller DTMs stay byte-identical to the reviewed
RAW-P16 position-balanced sequence.  The waveform tuple is the reviewed AC
tuple (active global header, active CS1, commented CS2).  This is a new,
human-primary review campaign after the completed T2 V2 action and its exact
W3 clean-white containment; no predecessor action is executable here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
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
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as t2_v1,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as t2_v2,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_v1,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_v2,
)


class T3ProfileFollowingPackError(RuntimeError):
    """Raised when a frozen predecessor or fresh identity boundary differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t3-ac-profile-following-successor-v1"
    suffix: str = "T3_AC_PROFILE_FOLLOWING_SUCCESSOR"
    global_header: str = "active"
    cs1_profile: str = "active"
    cs2_profile: str = "commented"
    round: int = 3
    repeat_of: str = "t1-ac"
    nvs_namespace: str = "p16t3pf_v1"
    nvs_key: str = "cur_t3pf1"
    nvs_boot_key: str = "boot_t3pf1"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V1"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V1_2026-08-30"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T3-AC-PROFILE-FOLLOWING-SUCCESSOR-V1"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V1"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t3-ac-profile-following-successor-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_raw_p16_crossover_t3_ac_profile_following_successor_v1"

    @property
    def build_root(self) -> str:
        return "build-raw-p16-crossover-t3-ac-profile-following-successor-v1"


STAGE = "t3-ac-profile-following-successor-v1"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T3_PROFILE_FOLLOWING_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-t3-ac-profile-following-successor-v1"
CLASSIFICATION = (
    "EXPERIMENTAL_HUMAN_PRIMARY_PROFILE_FOLLOWING_REVIEW_ONLY_T3_AC_SWAP_"
    "NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_ZERO_QUALIFIED_COLOURS"
)
FACTORY_WHITE_ANCHOR_ROLE = "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED"
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_ARMED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_ACTION_ONCE"

CODE_ROWS = legacy.CODE_ROWS
GRID_Y_BY_ROW = legacy.GRID_Y_BY_ROW

HUMAN_OBSERVATION_PLAN = {
    "primary_judgement": "HUMAN_VISUAL_PROFILE_FOLLOWING_REVIEW",
    "operator_observation_required": True,
    "camera_required_for_decision": False,
    "camera_evidence_optional": True,
    "camera_evidence_only": True,
    "required_retained_camera_frame_count": 0,
    "absolute_colour_claimed": False,
    "stable_new_colour_claimed": False,
    "profile_following_proven_by_this_action": False,
    "qualified_colour_count": 0,
}

T2_V2_ACTION_EVIDENCE_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2"
    / "action-01-position-balanced-atlas.json"
)
T2_V2_ACTION_EVIDENCE_BYTES = 46_464
T2_V2_ACTION_EVIDENCE_FILE_SHA256 = (
    "490df32422ec362f20c09e40d60d1e86e3f8bb46e9820f624004a4f07d08a989"
)
T2_V2_ACTION_EVIDENCE_CANONICAL_SHA256 = (
    "a7fc644e46586a5ebe8a1d447062a0ad6b0db8b8c2121ca61c3d842980e6bbcb"
)

W3_CLEAN_WHITE_EVIDENCE_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1"
    / "action-01-factory-otp-white.json"
)
W3_CLEAN_WHITE_EVIDENCE_BYTES = 29_734
W3_CLEAN_WHITE_EVIDENCE_FILE_SHA256 = (
    "445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef"
)
W3_CLEAN_WHITE_EVIDENCE_CANONICAL_SHA256 = (
    "624df0db0c082a151f54a051ca45209f4114b67a1643c358269d3efe444d611f"
)

W3_HUMAN_CLEAN_WHITE_AUTHORITY_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1"
    / "human-clean-white-authority-v1.json"
)
W3_HUMAN_CLEAN_WHITE_AUTHORITY_BYTES = 4_072
W3_HUMAN_CLEAN_WHITE_AUTHORITY_FILE_SHA256 = (
    "5f5ff9d0c6bc023c461038e17fbc92b0fda5b475d52019bf736b91d745d5582b"
)
W3_HUMAN_CLEAN_WHITE_AUTHORITY_CANONICAL_SHA256 = (
    "2fceccd9cac4af23ffc0d27f7d14a546920d586cc0efd72f0799037cdb5b614f"
)
W3_FINAL_RELAY_OFF_RECEIPT_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1"
    / "relay-post-action-protective-off-20260830-204303.json"
)
W3_FINAL_RELAY_OFF_RECEIPT_BYTES = 1_807
W3_FINAL_RELAY_OFF_RECEIPT_FILE_SHA256 = (
    "febbab71fcbca53130179424775caf6245990d6098f4fab8a1478474b537bae1"
)
W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256 = (
    "7ec1be01d29a543962db54f18037e09c9f52f060f62ef115fc0e830a5989c3ad"
)

ARTIFACTS = {
    STAGE: {
        "bin_bytes": 805_232,
        "bin_sha256": (
            "05c00d71a163ecfc22d0d333404ac8967eaa06b929003ce0c28dda7499615760"
        ),
        "elf_bytes": 13_299_376,
        "elf_sha256": (
            "89d20faec2d5bde42915a5fe30515c917f722ca06777b016a75c38020e83a56e"
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


def completed_t2_v2_action_binding() -> dict[str, Any]:
    report = t2_v2.build_report()
    action = report["actions"][0]
    return {
        "kind": "mf1750-ec5-raw-p16-crossover-t2-ca-coarse-discovery-successor-v2-result",
        "path": _repo_relative(T2_V2_ACTION_EVIDENCE_PATH),
        "bytes": T2_V2_ACTION_EVIDENCE_BYTES,
        "file_sha256": T2_V2_ACTION_EVIDENCE_FILE_SHA256,
        "canonical_integrity_sha256": T2_V2_ACTION_EVIDENCE_CANONICAL_SHA256,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "outcome": "complete_pass",
        "terminal_state": "COMPLETE",
        "round": 2,
        "visible_refreshes": 1,
    }


def completed_w3_white_action_binding() -> dict[str, Any]:
    report = w3_v2.build_white_report()
    action = report["action"]
    return {
        "kind": "mf1750-raw-p16-crossover-w3-t2-discovery-successor-v2-white-result",
        "path": _repo_relative(W3_CLEAN_WHITE_EVIDENCE_PATH),
        "bytes": W3_CLEAN_WHITE_EVIDENCE_BYTES,
        "file_sha256": W3_CLEAN_WHITE_EVIDENCE_FILE_SHA256,
        "canonical_integrity_sha256": W3_CLEAN_WHITE_EVIDENCE_CANONICAL_SHA256,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source_action_id": action["source_action_id"],
        "outcome": "complete_pass",
        "terminal_state": "COMPLETE",
        "visible_refreshes": 1,
    }


def pre_white_authority_binding() -> dict[str, Any]:
    action = completed_w3_white_action_binding()
    return {
        "kind": "mf1750-raw-p16-crossover-clean-white-human-observation-v1",
        "path": _repo_relative(W3_HUMAN_CLEAN_WHITE_AUTHORITY_PATH),
        "bytes": W3_HUMAN_CLEAN_WHITE_AUTHORITY_BYTES,
        "file_sha256": W3_HUMAN_CLEAN_WHITE_AUTHORITY_FILE_SHA256,
        "canonical_integrity_sha256": (W3_HUMAN_CLEAN_WHITE_AUTHORITY_CANONICAL_SHA256),
        "stage": "w3-after-t2-coarse-discovery-successor-v2",
        "action_result_binding": {
            "campaign_id": action["campaign_id"],
            "contract_id": action["contract_id"],
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "source_action_id": action["source_action_id"],
            "bytes": action["bytes"],
            "file_sha256": action["file_sha256"],
            "canonical_integrity_sha256": action["canonical_integrity_sha256"],
        },
        "raw_operator_report": {"operator_verbatim": "白屏，干净"},
        "authority": {
            "operator_reported_clean_white": True,
            "action_complete_exactly_bound": True,
            "final_relay_commanded_off_exactly_bound": True,
            "final_relay_off_is_command_query_not_load_voltage_proof": True,
            "operator_verbatim_preserved": True,
            "automatic_next_action_authorized": False,
            "camera_confirmation_claimed": False,
            "colorimeter_confirmation_claimed": False,
            "formal_colour_gate_evaluated": False,
        },
        "final_relay_off_receipt_binding": {
            "path": _repo_relative(W3_FINAL_RELAY_OFF_RECEIPT_PATH),
            "bytes": W3_FINAL_RELAY_OFF_RECEIPT_BYTES,
            "file_sha256": W3_FINAL_RELAY_OFF_RECEIPT_FILE_SHA256,
            "canonical_integrity_sha256": (W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256),
            "commanded_state": "OFF",
            "target_state": "OFF",
            "off_gate_passed": True,
            "electrical_state_proven": False,
        },
        "output_write_contract": "O_EXCL",
        "offline_execution": {
            "camera_accessed": False,
            "display_refreshed": False,
            "firmware_flashed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "relay_accessed": False,
            "serial_or_com_accessed": False,
        },
    }


@lru_cache(maxsize=1)
def non_reusable_action_ids() -> tuple[str, ...]:
    values = [
        *(
            legacy.build_report(stage)["actions"][0]["action_id"]
            for stage in legacy.STAGES
        ),
        *(
            legacy.build_white_report(stage)["action"]["action_id"]
            for stage in legacy.WHITES
        ),
        t2_v1.build_report()["actions"][0]["action_id"],
        w2_v1.build_white_report()["action"]["action_id"],
        t2_v2.build_report()["actions"][0]["action_id"],
        w3_v2.build_white_report()["action"]["action_id"],
    ]
    if len(values) != len(set(values)):
        raise T3ProfileFollowingPackError("predecessor action registry overlaps")
    return tuple(values)


def _load_bound_evidence(
    path: Path,
    *,
    byte_count: int,
    file_sha256: str,
    canonical_sha256: str,
    label: str,
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise T3ProfileFollowingPackError(f"{label} evidence missing: {candidate}")
    payload = candidate.read_bytes()
    if len(payload) != byte_count:
        raise T3ProfileFollowingPackError(f"{label} evidence byte count differs")
    if sha256_bytes(payload) != file_sha256:
        raise T3ProfileFollowingPackError(f"{label} evidence file SHA-256 differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T3ProfileFollowingPackError(
            f"{label} evidence is not valid JSON"
        ) from error
    if not isinstance(value, dict):
        raise T3ProfileFollowingPackError(f"{label} evidence root differs")
    integrity = value.get("integrity")
    unsigned = deepcopy(value)
    unsigned.pop("integrity", None)
    if (
        not isinstance(integrity, dict)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != canonical_sha256
        or sha256_bytes(canonical_json(unsigned)) != canonical_sha256
    ):
        raise T3ProfileFollowingPackError(
            f"{label} evidence canonical integrity differs"
        )
    return value


def _load_bound_relay_receipt(
    path: Path = W3_FINAL_RELAY_OFF_RECEIPT_PATH,
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise T3ProfileFollowingPackError(
            f"W3 final relay-OFF receipt missing: {candidate}"
        )
    payload = candidate.read_bytes()
    if len(payload) != W3_FINAL_RELAY_OFF_RECEIPT_BYTES:
        raise T3ProfileFollowingPackError(
            "W3 final relay-OFF receipt byte count differs"
        )
    if sha256_bytes(payload) != W3_FINAL_RELAY_OFF_RECEIPT_FILE_SHA256:
        raise T3ProfileFollowingPackError(
            "W3 final relay-OFF receipt file SHA-256 differs"
        )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T3ProfileFollowingPackError(
            "W3 final relay-OFF receipt is not valid JSON"
        ) from error
    if not isinstance(value, dict):
        raise T3ProfileFollowingPackError("W3 final relay-OFF receipt root differs")
    integrity = value.get("integrity")
    unsigned = deepcopy(value)
    unsigned.pop("integrity", None)
    if (
        not isinstance(integrity, dict)
        or integrity.get("algorithm") != "sha256"
        or integrity.get("canonical_sha256")
        != W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256
        or sha256_bytes(canonical_json(unsigned))
        != W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256
    ):
        raise T3ProfileFollowingPackError(
            "W3 final relay-OFF receipt canonical integrity differs"
        )
    if (
        value.get("kind") != "mf17506-zave-relay-exact-bound-switch-receipt"
        or value.get("commanded_state") != "OFF"
        or value.get("target_state") != "OFF"
        or value.get("off_gate_passed") is not True
        or value.get("target_gate_passed") is not True
        or value.get("electrical_state_proven") is not False
    ):
        raise T3ProfileFollowingPackError(
            "W3 final relay-OFF receipt semantic boundary differs"
        )
    return value


def validate_completed_t2_v2_action(
    path: Path = T2_V2_ACTION_EVIDENCE_PATH,
) -> dict[str, Any]:
    value = _load_bound_evidence(
        path,
        byte_count=T2_V2_ACTION_EVIDENCE_BYTES,
        file_sha256=T2_V2_ACTION_EVIDENCE_FILE_SHA256,
        canonical_sha256=T2_V2_ACTION_EVIDENCE_CANONICAL_SHA256,
        label="completed T2 V2 action",
    )
    expected = completed_t2_v2_action_binding()
    action = value.get("action")
    terminal = value.get("terminal_report")
    if not isinstance(action, dict) or not isinstance(terminal, dict):
        raise T3ProfileFollowingPackError("completed T2 V2 action body differs")
    observed = {
        "kind": value.get("kind"),
        "campaign_id": terminal.get("campaign_id"),
        "contract_id": terminal.get("contract_id"),
        "descriptor_id": action.get("descriptor_id"),
        "action_id": action.get("action_id"),
        "outcome": value.get("outcome"),
        "terminal_state": terminal.get("terminal_state"),
        "round": action.get("round"),
        "visible_refreshes": value.get("visible_refreshes"),
    }
    for key in observed:
        if observed[key] != expected[key]:
            raise T3ProfileFollowingPackError(f"completed T2 V2 action {key} differs")
    if (
        terminal.get("result") is not True
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise T3ProfileFollowingPackError(
            "completed T2 V2 action success boundary differs"
        )
    return value


def validate_completed_w3_white_action(
    path: Path = W3_CLEAN_WHITE_EVIDENCE_PATH,
) -> dict[str, Any]:
    value = _load_bound_evidence(
        path,
        byte_count=W3_CLEAN_WHITE_EVIDENCE_BYTES,
        file_sha256=W3_CLEAN_WHITE_EVIDENCE_FILE_SHA256,
        canonical_sha256=W3_CLEAN_WHITE_EVIDENCE_CANONICAL_SHA256,
        label="W3 clean-white",
    )
    expected = completed_w3_white_action_binding()
    action = value.get("action")
    terminal = value.get("terminal_report")
    if not isinstance(action, dict) or not isinstance(terminal, dict):
        raise T3ProfileFollowingPackError("W3 clean-white action body differs")
    observed = {
        "kind": value.get("kind"),
        "campaign_id": terminal.get("campaign_id"),
        "contract_id": terminal.get("contract_id"),
        "descriptor_id": action.get("descriptor_id"),
        "action_id": action.get("action_id"),
        "source_action_id": action.get("source_action_id"),
        "outcome": value.get("outcome"),
        "terminal_state": terminal.get("terminal_state"),
        "visible_refreshes": value.get("visible_refreshes"),
    }
    for key in observed:
        if observed[key] != expected[key]:
            raise T3ProfileFollowingPackError(f"W3 clean-white {key} differs")
    if (
        terminal.get("result") is not True
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise T3ProfileFollowingPackError("W3 clean-white success boundary differs")
    return value


def validate_pre_white_authority(
    path: Path = W3_HUMAN_CLEAN_WHITE_AUTHORITY_PATH,
    *,
    relay_receipt_path: Path = W3_FINAL_RELAY_OFF_RECEIPT_PATH,
) -> dict[str, Any]:
    completed_action = validate_completed_w3_white_action()
    relay_receipt = _load_bound_relay_receipt(relay_receipt_path)
    value = _load_bound_evidence(
        path,
        byte_count=W3_HUMAN_CLEAN_WHITE_AUTHORITY_BYTES,
        file_sha256=W3_HUMAN_CLEAN_WHITE_AUTHORITY_FILE_SHA256,
        canonical_sha256=W3_HUMAN_CLEAN_WHITE_AUTHORITY_CANONICAL_SHA256,
        label="W3 human clean-white authority",
    )
    expected = pre_white_authority_binding()
    action_binding = value.get("action_result_binding")
    operator_report = value.get("raw_operator_report")
    authority = value.get("authority")
    relay_binding = value.get("final_relay_off_receipt_binding")
    offline = value.get("offline_execution")
    if not all(
        isinstance(item, dict)
        for item in (
            action_binding,
            operator_report,
            authority,
            relay_binding,
            offline,
        )
    ):
        raise T3ProfileFollowingPackError("W3 human clean-white authority body differs")
    action_expected = expected["action_result_binding"]
    action_observed = {
        key: action_binding.get(key)
        for key in (
            "campaign_id",
            "contract_id",
            "descriptor_id",
            "action_id",
            "source_action_id",
            "bytes",
            "file_sha256",
            "canonical_integrity_sha256",
        )
    }
    if action_observed != action_expected:
        raise T3ProfileFollowingPackError(
            "W3 human clean-white action-result binding differs"
        )
    if (
        action_binding.get("file_sha256")
        != sha256_bytes(W3_CLEAN_WHITE_EVIDENCE_PATH.read_bytes())
        or action_binding.get("action_id") != completed_action["action"]["action_id"]
    ):
        raise T3ProfileFollowingPackError(
            "W3 human clean-white action-result evidence differs"
        )
    if (
        value.get("kind") != expected["kind"]
        or value.get("stage") != expected["stage"]
        or value.get("output_write_contract") != "O_EXCL"
        or operator_report.get("operator_verbatim") != "白屏，干净"
    ):
        raise T3ProfileFollowingPackError(
            "W3 human clean-white operator authority differs"
        )
    for key, wanted in expected["authority"].items():
        if authority.get(key) is not wanted:
            raise T3ProfileFollowingPackError(
                f"W3 human clean-white authority {key} differs"
            )
    relay_expected = expected["final_relay_off_receipt_binding"]
    for key in (
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "commanded_state",
        "target_state",
        "off_gate_passed",
        "electrical_state_proven",
    ):
        if relay_binding.get(key) != relay_expected[key]:
            raise T3ProfileFollowingPackError(
                f"W3 human clean-white relay binding {key} differs"
            )
    if (
        relay_binding.get("file_sha256")
        != sha256_bytes(Path(relay_receipt_path).read_bytes())
        or relay_receipt.get("commanded_state") != relay_binding.get("commanded_state")
        or relay_receipt.get("target_state") != relay_binding.get("target_state")
        or relay_receipt.get("off_gate_passed")
        is not relay_binding.get("off_gate_passed")
        or relay_receipt.get("electrical_state_proven")
        is not relay_binding.get("electrical_state_proven")
    ):
        raise T3ProfileFollowingPackError(
            "W3 human clean-white bound relay receipt differs"
        )
    if offline != expected["offline_execution"]:
        raise T3ProfileFollowingPackError(
            "W3 human clean-white offline execution boundary differs"
        )
    return value


def validate_authorities() -> dict[str, dict[str, Any]]:
    return {
        "completed_t2_v2_action": validate_completed_t2_v2_action(),
        "completed_w3_white_action": validate_completed_w3_white_action(),
        "pre_white_human_authority": validate_pre_white_authority(),
    }


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = ARTIFACTS[STAGE]
    return (
        values["bin_bytes"] > 0
        and values["elf_bytes"] > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def external_containment_contract() -> dict[str, Any]:
    return {
        "outside_campaign": True,
        "factory_otp_white_before_required": True,
        "factory_otp_white_after_required": True,
        "off_white_photos_before_atlas_required": 0,
        "off_retained_atlas_photos_required": 0,
        "camera_evidence_optional": True,
        "post_white_clean_visual_gate_required": True,
        "human_observation_required": True,
        "white_actions_in_campaign": 0,
    }


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    legacy_ac = legacy.build_report("t3-ac-repeat")
    legacy_action = legacy_ac["actions"][0]
    source = t2_v2.build_report()
    source_action = source["actions"][0]
    profile = legacy.waveform_profile(legacy.STAGES["t3-ac-repeat"])

    action = deepcopy(legacy_action)
    action.update(
        {
            "ordinal": 1,
            "role": "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_ATLAS",
            "driver_role": "Source",
            "round": 3,
            "branch": (
                f"{CONFIG.variant_key}_"
                "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_ATLAS"
            ),
            "global_header": "active",
            "profile_id": profile["id"],
            "global_tuple_id": profile["global_tuple_id"],
            "waveform_binding": profile,
            "prior_static_action_id": source_action["action_id"],
            "repeat_of_stage": "t1-ac",
            "supersedes_static_action_id": legacy_action["action_id"],
            "source_action_authority": completed_t2_v2_action_binding(),
            "pre_white_action_evidence": completed_w3_white_action_binding(),
            "pre_white_authority": pre_white_authority_binding(),
            "human_observation_plan": deepcopy(HUMAN_OBSERVATION_PLAN),
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
            "mf1750-raw-p16-crossover-t3-ac-profile-following-successor-action-v1"
        ),
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "non_reusable_action_ids": list(non_reusable_action_ids()),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_"
            f"SUCCESSOR_ACTION_V1|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )

    contract = {
        "schema": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-successor-contract-v1"
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
        "profile": profile,
        "geometry": deepcopy(legacy_ac["contract"]["geometry"]),
        "analysis_priority": deepcopy(legacy_ac["contract"]["analysis_priority"]),
        "actions": [action],
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "full_screen_global_refresh": True,
        "external_containment": external_containment_contract(),
        "source_action_authority": completed_t2_v2_action_binding(),
        "pre_white_action_evidence": completed_w3_white_action_binding(),
        "pre_white_authority": pre_white_authority_binding(),
        "human_observation_plan": deepcopy(HUMAN_OBSERVATION_PLAN),
        "non_reusable_action_ids": list(non_reusable_action_ids()),
        "screening_only": True,
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "human_observation_gate_after_every_action": True,
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
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-"
            "successor-offline-identities-v1"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": completed_t2_v2_action_binding(),
        "pre_white_action_evidence": completed_w3_white_action_binding(),
        "pre_white_authority": pre_white_authority_binding(),
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


@lru_cache(maxsize=1)
def _prior_identity_values() -> frozenset[str]:
    reports = [legacy.build_report(stage) for stage in legacy.STAGES]
    white_reports = [legacy.build_white_report(stage) for stage in legacy.WHITES]
    reports.extend((t2_v1.build_report(), t2_v2.build_report()))
    white_reports.extend((w2_v1.build_white_report(), w3_v2.build_white_report()))
    values: set[str] = set()
    for report in reports:
        action = report["actions"][0]
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
    for report in white_reports:
        action = report["action"]
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
    legacy_ac = legacy.build_report("t3-ac-repeat")["actions"][0]
    t2_action = t2_v2.build_report()["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm"):
        if action[key] != legacy_ac[key] or action[key] != t2_action[key]:
            raise T3ProfileFollowingPackError(f"T3 AC {key} differs")
    if action["waveform_binding"] != legacy_ac["waveform_binding"]:
        raise T3ProfileFollowingPackError("T3 AC waveform tuple differs")
    if (
        action["global_header"] != "active"
        or action["waveform_binding"]["cs1"]["name"] != "active"
        or action["waveform_binding"]["cs2"]["name"] != "commented"
        or action["round"] != 3
    ):
        raise T3ProfileFollowingPackError("T3 AC profile swap differs")
    if action["action_id"] in non_reusable_action_ids():
        raise T3ProfileFollowingPackError("fresh action reuses a predecessor ID")
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
        raise T3ProfileFollowingPackError("fresh identity overlaps a predecessor")
    if len(CONFIG.nvs_namespace) > 15:
        raise T3ProfileFollowingPackError("NVS namespace exceeds ESP32 limit")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-successor-dry-validation"
        ),
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
        "predecessor_actions_non_reusable": True,
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "profile_tuple": "ACTIVE_GLOBAL__CS1_ACTIVE535__CS2_COMMENTED535",
        "round": 3,
        "screening_only": True,
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "source_action_authority": completed_t2_v2_action_binding(),
        "pre_white_action_evidence": completed_w3_white_action_binding(),
        "pre_white_authority": pre_white_authority_binding(),
        "human_observation_plan": deepcopy(HUMAN_OBSERVATION_PLAN),
        "artifacts_sealed": artifacts_are_sealed(),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
