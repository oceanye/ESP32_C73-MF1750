#!/usr/bin/env python3
"""Seal and compare blind human observations for the CA->AC crossover.

This tool is deliberately offline-only.  It never opens a camera, device,
relay, serial port, or network connection.  A sealed observation binds one
operator input file to one exact completed atlas action-result, preserves the
operator's words, checks all 64 cells, derives four-replicate consistency and
control gates, and writes with O_EXCL.  A comparison is permitted only between
the exact consumed CA V2 baseline and the fresh AC profile-following stage.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as legacy,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as ca_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)
from tools.mf17506_stage23 import relay_exact_bound_switch as relay_switch  # noqa: E402


SCHEMA_VERSION = 1
INPUT_KIND = "mf1750-raw-p16-crossover-profile-following-human-observation-input-v1"
COMPACT_INPUT_KIND = "mf1750-raw-p16-crossover-profile-following-human-compact-input-v1"
OBSERVATION_KIND = "mf1750-raw-p16-crossover-profile-following-human-observation-v1"
COMPARISON_KIND = "mf1750-raw-p16-crossover-profile-following-human-comparison-v1"
WHITE_INPUT_KIND = "mf1750-raw-p16-crossover-clean-white-human-observation-input-v1"
WHITE_OBSERVATION_KIND = "mf1750-raw-p16-crossover-clean-white-human-observation-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

CA_STAGE = ca_pack.STAGE
AC_STAGE = "t3-ac-profile-following-successor-v1"
STAGES = (CA_STAGE, AC_STAGE)
AC_PACK_MODULE = "tools.mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack"
AC_V2_STAGE = "t3-ac-profile-following-successor-v2"
AC_V2_PACK_MODULE = (
    "tools.mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack"
)

CODE_ROWS = (
    (0, 1, 2, 3, 4, 5, 6, 7),
    (6, 7, 0, 1, 2, 3, 4, 5),
    (5, 4, 7, 6, 1, 0, 3, 2),
    (3, 2, 5, 4, 7, 6, 1, 0),
)
CONTROLLERS = ("CS1", "CS2")
CANDIDATE_CODES = (0, 1, 4, 6, 7)
CONTROL_CODES = (2, 3, 5)
CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW", "NOT_REPORTED")
ARTIFACT_FIELDS = (
    "edge_anomaly",
    "horizontal_stripe",
    "vertical_stripe",
    "residual_or_ghosting",
    "flicker_or_instability",
)

EXPECTED_PROFILES = {
    CA_STAGE: {
        "global_header": "commented",
        "CS1": "commented",
        "CS2": "active",
        "round": 2,
    },
    AC_STAGE: {
        "global_header": "active",
        "CS1": "active",
        "CS2": "commented",
        "round": 3,
    },
    AC_V2_STAGE: {
        "global_header": "active",
        "CS1": "active",
        "CS2": "commented",
        "round": 3,
    },
}

CA_REPORTED_LABELS = {
    "CS1": {
        0: "橄榄",
        1: "黑",
        2: "绿",
        3: "白",
        4: "浅黄",
        5: "蓝",
        6: "黄",
        7: "黑",
    },
    "CS2": {
        0: "红",
        1: "粉",
        2: "绿",
        3: "白",
        4: "棕",
        5: "蓝",
        6: "深粉",
        7: "深蓝",
    },
}

# The CA baseline was already consumed and observed.  Requiring the complete
# result bytes prevents a later look-alike result from replacing that baseline.
CA_ACTION_RESULT_BYTES = 46_464
CA_ACTION_RESULT_FILE_SHA256 = (
    "490df32422ec362f20c09e40d60d1e86e3f8bb46e9820f624004a4f07d08a989"
)
CA_ACTION_RESULT_CANONICAL_SHA256 = (
    "a7fc644e46586a5ebe8a1d447062a0ad6b0db8b8c2121ca61c3d842980e6bbcb"
)

W3_STAGE = w3_pack.STAGE
W3_CLEAN_WHITE_VERBATIM = "白屏，干净"
W3_ACTION_RESULT_BYTES = 29_734
W3_ACTION_RESULT_FILE_SHA256 = (
    "445181448ab4ff7bdd19d646cff24f3dd8fec89b329512b9f90ad6c3b2d257ef"
)
W3_ACTION_RESULT_CANONICAL_SHA256 = (
    "624df0db0c082a151f54a051ca45209f4114b67a1643c358269d3efe444d611f"
)
W3_FINAL_RELAY_OFF_RECEIPT_BYTES = 1_807
W3_FINAL_RELAY_OFF_RECEIPT_FILE_SHA256 = (
    "febbab71fcbca53130179424775caf6245990d6098f4fab8a1478474b537bae1"
)
W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256 = (
    "7ec1be01d29a543962db54f18037e09c9f52f060f62ef115fc0e830a5989c3ad"
)
T3_EXACT_CAMPAIGN_ID = "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V1"
T3_EXACT_CONTRACT_ID = (
    "714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19"
)
T3_EXACT_DESCRIPTOR_ID = (
    "52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9"
)
T3_EXACT_ACTION_ID = "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104"
T3_EXACT_BIN_SHA256 = "05c00d71a163ecfc22d0d333404ac8967eaa06b929003ce0c28dda7499615760"
T3_EXACT_ELF_SHA256 = "89d20faec2d5bde42915a5fe30515c917f722ca06777b016a75c38020e83a56e"
T3_V2_EXACT_CAMPAIGN_ID = (
    "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2"
)
T3_V2_EXACT_CONTRACT_ID = (
    "cc33b55a64fc2d54884f9c6ca65e117d6767fab0f0c60c3e5f55fac3554e5729"
)
T3_V2_EXACT_DESCRIPTOR_ID = (
    "c2e40c4c59cf6cca3f6ff4fd8c568a5ddee59e8c2100a9cf5d50c007317a148a"
)
T3_V2_EXACT_ACTION_ID = (
    "73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5"
)
T3_V2_EXACT_BIN_SHA256 = (
    "94ea921532d44009c8e6aef645a51bd1a1f0386fb7d86ca8da115ad8c0fb2578"
)
T3_V2_EXACT_ELF_SHA256 = (
    "bda4c0bdce15a5deefcb394ef10d021c542c0bdd2163989ae0f2f4607e8ae981"
)

INPUT_KEYS = {
    "schema_version",
    "kind",
    "stage",
    "observed_at",
    "operator",
    "supervision",
    "controls_verbatim",
    "artifacts",
    "cells",
}
OPERATOR_KEYS = {"operator_id", "operator_verbatim"}
SUPERVISION_KEYS = {
    "supervisor_id",
    "continuous_supervision",
    "action_complete_reviewed",
    "no_intervening_visible_refresh",
    "ambient_light_stable",
    "viewing_angle_stable",
    "display_stable_through_observation",
    "four_replicates_checked",
    "electrical_state_normal",
    "esp32_restart_observed",
    "j2_state_during_observation",
    "supervision_verbatim",
}
CELL_KEYS = {
    "controller",
    "row",
    "column",
    "code",
    "label_verbatim",
    "confidence",
    "stable",
}
WHITE_INPUT_KEYS = {
    "schema_version",
    "kind",
    "stage",
    "reported_at",
    "operator_id",
    "operator_verbatim",
}
COMPACT_INPUT_KEYS = (INPUT_KEYS - {"cells"}) | {"controllers"}
COMPACT_CONTROLLER_KEYS = {
    "code_labels_verbatim",
    "all_four_replicates_consistent",
    "four_replicates_consistent_by_code",
    "all_labels_stable",
    "stable_by_code",
}


class HumanObservationError(RuntimeError):
    """Raised when observation evidence is incomplete, mutable, or mismatched."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HumanObservationError(message)


def _exact_keys(value: Any, keys: set[str], *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    _require(set(value) == keys, f"{label} keys differ")
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    _require(isinstance(value, str), f"{label} must be text")
    _require(bool(value.strip()), f"{label} must not be blank")
    _require(len(value) <= maximum, f"{label} is too long")
    return value


def _rfc3339(value: Any, *, label: str) -> str:
    text = _text(value, label=label, maximum=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise HumanObservationError(f"{label} is not RFC3339") from error
    _require(parsed.tzinfo is not None, f"{label} must include a timezone")
    return text


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        return strict._load_json(Path(path), label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise HumanObservationError(str(error)) from error


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    try:
        return strict._verify_integrity(root, label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise HumanObservationError(str(error)) from error


def _file_reference(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": Path(path).resolve().as_posix(),
        "bytes": len(payload),
        "file_sha256": strict.sha256_bytes(payload),
    }


def _stage_contract(stage: str) -> dict[str, Any]:
    if stage == CA_STAGE:
        pack = ca_pack
    elif stage in (AC_STAGE, AC_V2_STAGE):
        module_name = AC_PACK_MODULE if stage == AC_STAGE else AC_V2_PACK_MODULE
        try:
            pack = importlib.import_module(module_name)
        except (ImportError, AttributeError) as error:
            raise HumanObservationError(
                "fresh AC pack is unavailable; observation cannot be bound"
            ) from error
    else:
        raise HumanObservationError(f"unknown observation stage {stage!r}")

    _require(getattr(pack, "STAGE", None) == stage, f"{stage} pack stage differs")
    try:
        report = pack.build_report()
        action = report["actions"][0]
        cfg = pack.CONFIG
        artifacts = pack.ARTIFACTS[stage]
    except (AttributeError, KeyError, TypeError, IndexError) as error:
        raise HumanObservationError(f"{stage} pack interface differs") from error
    expected_profile = EXPECTED_PROFILES[stage]
    waveform = action.get("waveform_binding", {})
    _require(
        action.get("round") == expected_profile["round"],
        f"{stage} action round differs",
    )
    _require(
        action.get("global_header") == expected_profile["global_header"],
        f"{stage} global header differs",
    )
    _require(
        waveform.get("cs1", {}).get("name") == expected_profile["CS1"]
        and waveform.get("cs2", {}).get("name") == expected_profile["CS2"],
        f"{stage} controller profile map differs",
    )
    _require(
        tuple(tuple(row) for row in pack.CODE_ROWS) == CODE_ROWS,
        f"{stage} code layout differs",
    )
    _require(
        action.get("frame", {}).get("sha256")
        == "1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23"
        and action.get("cs1_dtm", {}).get("sha256")
        == "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb"
        and action.get("cs2_dtm", {}).get("sha256")
        == "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb",
        f"{stage} frame or DTM differs from the matched crossover atlas",
    )
    firmware_sha = artifacts.get("bin_sha256")
    _require(
        isinstance(firmware_sha, str)
        and len(firmware_sha) == 64
        and set(firmware_sha) <= set("0123456789abcdef")
        and firmware_sha != "0" * 64,
        f"{stage} final firmware SHA-256 is not sealed",
    )
    if stage in (AC_STAGE, AC_V2_STAGE):
        if stage == AC_STAGE:
            exact = (
                T3_EXACT_CAMPAIGN_ID,
                T3_EXACT_CONTRACT_ID,
                T3_EXACT_DESCRIPTOR_ID,
                T3_EXACT_ACTION_ID,
                T3_EXACT_BIN_SHA256,
                T3_EXACT_ELF_SHA256,
            )
        else:
            exact = (
                T3_V2_EXACT_CAMPAIGN_ID,
                T3_V2_EXACT_CONTRACT_ID,
                T3_V2_EXACT_DESCRIPTOR_ID,
                T3_V2_EXACT_ACTION_ID,
                T3_V2_EXACT_BIN_SHA256,
                T3_V2_EXACT_ELF_SHA256,
            )
        _require(
            cfg.campaign_id == exact[0]
            and report.get("contract_id") == exact[1]
            and action.get("descriptor_id") == exact[2]
            and action.get("action_id") == exact[3]
            and artifacts.get("bin_sha256") == exact[4]
            and artifacts.get("elf_sha256") == exact[5],
            "fresh AC final campaign/contract/action/artifact identity differs",
        )
    return {
        "stage": stage,
        "pack": pack,
        "report": report,
        "action": action,
        "config": cfg,
        "firmware_sha256": firmware_sha,
        "profile_map": {
            "global_header": expected_profile["global_header"],
            "CS1": expected_profile["CS1"],
            "CS2": expected_profile["CS2"],
        },
    }


def _expected_runtime_action(action: Mapping[str, Any]) -> dict[str, Any]:
    expected = legacy._runtime_action(action)  # noqa: SLF001
    expected["round"] = action["round"]
    expected["transport_code_histogram"] = action["frame"]["histogram"]
    return expected


def _validate_action_result(path: Path, *, stage: str) -> dict[str, Any]:
    resolved = Path(path).resolve()
    payload, root = _read_json(resolved, label=f"{stage} action result")
    canonical_sha = _verify_integrity(root, label=f"{stage} action result")
    if stage == CA_STAGE:
        _require(
            len(payload) == CA_ACTION_RESULT_BYTES, "CA action-result bytes differ"
        )
        _require(
            strict.sha256_bytes(payload) == CA_ACTION_RESULT_FILE_SHA256,
            "CA action-result file SHA-256 differs",
        )
        _require(
            canonical_sha == CA_ACTION_RESULT_CANONICAL_SHA256,
            "CA action-result canonical SHA-256 differs",
        )

    contract = _stage_contract(stage)
    expected_action = contract["action"]
    cfg = contract["config"]
    action = root.get("action")
    terminal = root.get("terminal_report")
    _require(isinstance(action, Mapping), f"{stage} result.action is missing")
    _require(isinstance(terminal, Mapping), f"{stage} terminal report is missing")
    for field, expected in _expected_runtime_action(expected_action).items():
        _require(action.get(field) == expected, f"{stage} action {field} differs")
    if stage in (AC_STAGE, AC_V2_STAGE) and "prior_static_action_id" in expected_action:
        _require(
            action.get("prior_static_action_id")
            == expected_action["prior_static_action_id"],
            f"{stage} action prior_static_action_id differs",
        )
    _require(
        root.get("schema_version") == 1
        and root.get("kind") == f"mf1750-ec5-{cfg.route_slug}-result"
        and root.get("outcome") == "complete_pass"
        and root.get("visible_refreshes") == 1
        and root.get("firmware_sha256") == contract["firmware_sha256"]
        and root.get("no_autochain") is True
        and root.get("no_retry") is True
        and root.get("no_recovery") is True,
        f"{stage} action-result envelope differs",
    )
    report = contract["report"]
    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "build_tag": cfg.build_tag,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "ordinal": 1,
        "role": expected_action["role"],
        "round": expected_action["round"],
        "profile_id": expected_action["profile_id"],
        "global_header": expected_action["global_header"],
        "global_tuple_id": expected_action["global_tuple_id"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
    }
    for field, expected in terminal_expected.items():
        _require(terminal.get(field) == expected, f"{stage} terminal {field} differs")
    driver = terminal.get("driver")
    _require(isinstance(driver, Mapping), f"{stage} terminal driver is missing")
    _require(
        driver.get("valid") is True
        and driver.get("sequence_ok") is True
        and driver.get("wait_timeout") is False
        and driver.get("failure_stage") == "none",
        f"{stage} terminal driver evidence differs",
    )
    result = _file_reference(resolved, payload)
    result.update(
        {
            "canonical_integrity_sha256": canonical_sha,
            "stage": stage,
            "campaign_id": cfg.campaign_id,
            "test_id": cfg.test_id,
            "contract_id": report["contract_id"],
            "descriptor_id": expected_action["descriptor_id"],
            "action_id": expected_action["action_id"],
            "role": expected_action["role"],
            "round": expected_action["round"],
            "firmware_sha256": contract["firmware_sha256"],
            "frame_sha256": expected_action["frame"]["sha256"],
            "cs1_dtm_sha256": expected_action["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": expected_action["cs2_dtm"]["sha256"],
            "profile_id": expected_action["profile_id"],
            "global_tuple_id": expected_action["global_tuple_id"],
            "profile_map": contract["profile_map"],
        }
    )
    return result


def _validate_w3_white_action_result(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    payload, root = _read_json(resolved, label="W3 clean-white action result")
    canonical_sha = _verify_integrity(root, label="W3 clean-white action result")
    _require(
        len(payload) == W3_ACTION_RESULT_BYTES,
        "W3 clean-white action-result bytes differ",
    )
    _require(
        strict.sha256_bytes(payload) == W3_ACTION_RESULT_FILE_SHA256,
        "W3 clean-white action-result file SHA-256 differs",
    )
    _require(
        canonical_sha == W3_ACTION_RESULT_CANONICAL_SHA256,
        "W3 clean-white action-result canonical SHA-256 differs",
    )
    report = w3_pack.build_white_report()
    expected_action = report["action"]
    action = root.get("action")
    terminal = root.get("terminal_report")
    _require(isinstance(action, Mapping), "W3 clean-white result.action is missing")
    _require(
        isinstance(terminal, Mapping),
        "W3 clean-white terminal report is missing",
    )
    for field, expected in expected_action.items():
        _require(
            action.get(field) == expected, f"W3 clean-white action {field} differs"
        )
    artifacts = w3_pack.WHITE_ARTIFACTS[W3_STAGE]
    config = w3_pack.CONFIG
    _require(
        root.get("schema_version") == 1
        and root.get("kind")
        == "mf1750-raw-p16-crossover-w3-t2-discovery-successor-v2-white-result"
        and root.get("outcome") == "complete_pass"
        and root.get("visible_refreshes") == 1
        and root.get("firmware_sha256") == artifacts["bin_sha256"]
        and root.get("running_app_elf_sha256") == artifacts["elf_sha256"]
        and root.get("claim_state") == "permanently_consumed_by_this_invocation"
        and root.get("no_autochain") is True
        and root.get("no_retry") is True
        and root.get("no_recovery") is True,
        "W3 clean-white action-result envelope differs",
    )
    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_complete": True,
        "campaign_id": config.campaign_id,
        "test_id": config.test_id,
        "contract_id": report["contract_id"],
        "build_tag": config.build_tag,
        "action_id": expected_action["action_id"],
        "ordinal": 1,
        "profile_id": "WF23_25",
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "running_app_elf_sha256": artifacts["elf_sha256"],
    }
    for field, expected in terminal_expected.items():
        _require(
            terminal.get(field) == expected,
            f"W3 clean-white terminal {field} differs",
        )
    driver = terminal.get("driver")
    _require(isinstance(driver, Mapping), "W3 clean-white terminal driver is missing")
    _require(
        driver.get("valid") is True
        and driver.get("sequence_ok") is True
        and driver.get("wait_timeout") is False
        and driver.get("failure_stage") == "none",
        "W3 clean-white terminal driver evidence differs",
    )
    return {
        **_file_reference(resolved, payload),
        "canonical_integrity_sha256": canonical_sha,
        "stage": W3_STAGE,
        "campaign_id": config.campaign_id,
        "test_id": config.test_id,
        "contract_id": report["contract_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "action_id": expected_action["action_id"],
        "role": expected_action["role"],
        "firmware_sha256": artifacts["bin_sha256"],
        "running_app_elf_sha256": artifacts["elf_sha256"],
        "source_campaign_id": expected_action["source_campaign_id"],
        "source_contract_id": expected_action["source_contract_id"],
        "source_descriptor_id": expected_action["source_descriptor_id"],
        "source_action_id": expected_action["source_action_id"],
    }


def _validate_w3_final_relay_off_receipt(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    payload, root = _read_json(resolved, label="W3 final relay-OFF receipt")
    _require(
        len(payload) == W3_FINAL_RELAY_OFF_RECEIPT_BYTES,
        "W3 final relay-OFF receipt bytes differ",
    )
    _require(
        strict.sha256_bytes(payload) == W3_FINAL_RELAY_OFF_RECEIPT_FILE_SHA256,
        "W3 final relay-OFF receipt file SHA-256 differs",
    )
    try:
        receipt = relay_switch.validate_receipt(root)
    except (relay_switch.RelayExactBoundSwitchError, ValueError) as error:
        raise HumanObservationError(str(error)) from error
    canonical_sha = receipt["integrity"]["canonical_sha256"]
    _require(
        canonical_sha == W3_FINAL_RELAY_OFF_RECEIPT_CANONICAL_SHA256,
        "W3 final relay-OFF receipt canonical SHA-256 differs",
    )
    _require(
        receipt["target_state"] == "OFF"
        and receipt["commanded_state"] == "OFF"
        and receipt["off_gate_passed"] is True
        and receipt["target_gate_passed"] is True
        and receipt["electrical_state_proven"] is False
        and receipt["automatic_retry_performed"] is False
        and receipt["automatic_recovery_performed"] is False,
        "W3 final relay-OFF safety fields differ",
    )
    return {
        **_file_reference(resolved, payload),
        "canonical_integrity_sha256": canonical_sha,
        "switched_at": receipt["switched_at"],
        "target_state": "OFF",
        "commanded_state": "OFF",
        "off_gate_passed": True,
        "electrical_state_proven": False,
        "receipt_kind": receipt["kind"],
        "relay_rebind_id": receipt["rebind"]["rebind_id"],
    }


def _validate_white_operator_input(root: Mapping[str, Any]) -> dict[str, Any]:
    source = _exact_keys(root, WHITE_INPUT_KEYS, label="clean-white operator input")
    _require(source["schema_version"] == SCHEMA_VERSION, "white input schema differs")
    _require(source["kind"] == WHITE_INPUT_KIND, "white input kind differs")
    _require(source["stage"] == W3_STAGE, "white input stage differs")
    if source["reported_at"] is not None:
        _rfc3339(source["reported_at"], label="reported_at")
    _text(source["operator_id"], label="operator_id", maximum=128)
    operator_verbatim = _text(
        source["operator_verbatim"],
        label="operator_verbatim",
    )
    _require(
        operator_verbatim == W3_CLEAN_WHITE_VERBATIM,
        "W3 clean-white operator verbatim differs from the reported fact",
    )
    return dict(source)


def seal_clean_white_observation(
    *,
    action_result_path: Path,
    relay_off_receipt_path: Path,
    operator_input_path: Path,
) -> dict[str, Any]:
    """Seal the already-reported W3 clean-white fact without hardware I/O."""

    action_binding = _validate_w3_white_action_result(action_result_path)
    relay_binding = _validate_w3_final_relay_off_receipt(relay_off_receipt_path)
    input_path = Path(operator_input_path).resolve()
    input_payload, input_root = _read_json(
        input_path, label="clean-white operator input"
    )
    source = _validate_white_operator_input(input_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": WHITE_OBSERVATION_KIND,
        "stage": W3_STAGE,
        "action_result_binding": action_binding,
        "final_relay_off_receipt_binding": relay_binding,
        "operator_input_binding": _file_reference(input_path, input_payload),
        "raw_operator_report": deepcopy(source),
        "authority": {
            "operator_verbatim_preserved": True,
            "operator_reported_clean_white": True,
            "action_complete_exactly_bound": True,
            "final_relay_commanded_off_exactly_bound": True,
            "final_relay_off_is_command_query_not_load_voltage_proof": True,
            "camera_confirmation_claimed": False,
            "colorimeter_confirmation_claimed": False,
            "edge_stripe_or_residual_separately_enumerated": False,
            "formal_colour_gate_evaluated": False,
            "automatic_next_action_authorized": False,
        },
        "offline_execution": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_clean_white_observation(path: Path) -> tuple[dict[str, Any], bytes]:
    payload, root = _read_json(Path(path), label="sealed clean-white observation")
    _verify_integrity(root, label="sealed clean-white observation")
    _require(
        root.get("schema_version") == SCHEMA_VERSION
        and root.get("kind") == WHITE_OBSERVATION_KIND,
        "sealed clean-white observation schema or kind differs",
    )
    recomputed = seal_clean_white_observation(
        action_result_path=Path(root["action_result_binding"]["path"]),
        relay_off_receipt_path=Path(root["final_relay_off_receipt_binding"]["path"]),
        operator_input_path=Path(root["operator_input_binding"]["path"]),
    )
    _require(
        recomputed == root,
        "sealed clean-white observation differs from source recomputation",
    )
    return root, payload


def _validate_operator_input(
    root: Mapping[str, Any], *, expected_stage: str
) -> dict[str, Any]:
    source = _exact_keys(root, INPUT_KEYS, label="operator observation input")
    _require(source["schema_version"] == SCHEMA_VERSION, "input schema differs")
    _require(source["kind"] == INPUT_KIND, "input kind differs")
    _require(source["stage"] == expected_stage, "input stage differs")
    if source["observed_at"] is not None:
        _rfc3339(source["observed_at"], label="observed_at")

    operator = _exact_keys(source["operator"], OPERATOR_KEYS, label="operator")
    _text(operator["operator_id"], label="operator.operator_id", maximum=128)
    _text(operator["operator_verbatim"], label="operator.operator_verbatim")
    _text(source["controls_verbatim"], label="controls_verbatim")

    supervision = _exact_keys(
        source["supervision"], SUPERVISION_KEYS, label="supervision"
    )
    _text(supervision["supervisor_id"], label="supervision.supervisor_id", maximum=128)
    _text(
        supervision["supervision_verbatim"],
        label="supervision.supervision_verbatim",
    )
    for field in SUPERVISION_KEYS - {
        "supervisor_id",
        "j2_state_during_observation",
        "supervision_verbatim",
    }:
        _require(
            type(supervision[field]) is bool or supervision[field] is None,
            f"supervision.{field} must be boolean or null",
        )
    _require(
        supervision["j2_state_during_observation"] in {"ON", "OFF", "UNKNOWN"},
        "supervision.j2_state_during_observation differs",
    )

    artifacts = _exact_keys(
        source["artifacts"], set(ARTIFACT_FIELDS), label="artifacts"
    )
    for field in ARTIFACT_FIELDS:
        item = _exact_keys(
            artifacts[field],
            {"observed", "operator_verbatim"},
            label=f"artifacts.{field}",
        )
        _require(
            type(item["observed"]) is bool or item["observed"] is None,
            f"artifacts.{field}.observed must be boolean or null",
        )
        _text(
            item["operator_verbatim"],
            label=f"artifacts.{field}.operator_verbatim",
        )

    cells = source["cells"]
    _require(isinstance(cells, list), "cells must be an array")
    _require(len(cells) == 64, "exactly 64 controller cells are required")
    seen: set[tuple[str, int, int]] = set()
    for index, value in enumerate(cells):
        cell = _exact_keys(value, CELL_KEYS, label=f"cells[{index}]")
        controller = cell["controller"]
        row = cell["row"]
        column = cell["column"]
        _require(controller in CONTROLLERS, f"cells[{index}].controller differs")
        _require(type(row) is int and 0 <= row < 4, f"cells[{index}].row differs")
        _require(
            type(column) is int and 0 <= column < 8,
            f"cells[{index}].column differs",
        )
        _require(
            type(cell["code"]) is int and cell["code"] == CODE_ROWS[row][column],
            f"cells[{index}].code differs from the fixed layout",
        )
        key = (controller, row, column)
        _require(key not in seen, f"duplicate controller cell {key}")
        seen.add(key)
        _text(
            cell["label_verbatim"],
            label=f"cells[{index}].label_verbatim",
            maximum=128,
        )
        _require(
            cell["confidence"] in CONFIDENCE_LEVELS,
            f"cells[{index}].confidence differs",
        )
        _require(type(cell["stable"]) is bool, f"cells[{index}].stable must be boolean")
    expected = {
        (controller, row, column)
        for controller in CONTROLLERS
        for row in range(4)
        for column in range(8)
    }
    _require(seen == expected, "controller cell coverage differs")
    return dict(source)


def _compact_true_flags(*, total: Any, by_code: Any, label: str) -> list[bool]:
    _require(
        (total is None) != (by_code is None),
        f"{label} requires exactly one of total or by-code confirmation",
    )
    if total is not None:
        _require(type(total) is bool, f"{label} total must be boolean or null")
        _require(
            total is True,
            f"{label} is not uniformly true; use the expanded 64-cell input",
        )
        return [True] * 8
    _require(
        isinstance(by_code, list) and len(by_code) == 8,
        f"{label} by-code confirmation must contain eight booleans",
    )
    _require(
        all(type(value) is bool for value in by_code),
        f"{label} by-code confirmation must contain booleans",
    )
    _require(
        all(by_code),
        f"{label} has a false code; use the expanded 64-cell input",
    )
    return list(by_code)


def _expand_compact_operator_input(
    root: Mapping[str, Any], *, expected_stage: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    compact = _exact_keys(root, COMPACT_INPUT_KEYS, label="compact operator input")
    _require(compact["schema_version"] == SCHEMA_VERSION, "compact schema differs")
    _require(compact["kind"] == COMPACT_INPUT_KIND, "compact kind differs")
    _require(compact["stage"] == expected_stage, "compact stage differs")
    controllers = _exact_keys(
        compact["controllers"], set(CONTROLLERS), label="compact controllers"
    )
    cells = []
    expansion = {}
    for controller in CONTROLLERS:
        item = _exact_keys(
            controllers[controller],
            COMPACT_CONTROLLER_KEYS,
            label=f"compact controllers.{controller}",
        )
        labels = item["code_labels_verbatim"]
        _require(
            isinstance(labels, list) and len(labels) == 8,
            f"compact controllers.{controller}.code_labels_verbatim differs",
        )
        for code, value in enumerate(labels):
            _text(
                value,
                label=(
                    f"compact controllers.{controller}.code_labels_verbatim[{code}]"
                ),
                maximum=128,
            )
        consistent = _compact_true_flags(
            total=item["all_four_replicates_consistent"],
            by_code=item["four_replicates_consistent_by_code"],
            label=f"compact controllers.{controller} four-replicate consistency",
        )
        stable = _compact_true_flags(
            total=item["all_labels_stable"],
            by_code=item["stable_by_code"],
            label=f"compact controllers.{controller} stability",
        )
        for row, codes in enumerate(CODE_ROWS):
            for column, code in enumerate(codes):
                cells.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "code": code,
                        "label_verbatim": labels[code],
                        "confidence": "NOT_REPORTED",
                        "stable": stable[code],
                    }
                )
        expansion[controller] = {
            "code_count": 8,
            "expanded_cell_count": 32,
            "four_replicates_consistent_by_code": consistent,
            "stable_by_code": stable,
        }
    expanded = {
        key: deepcopy(value) for key, value in compact.items() if key != "controllers"
    }
    expanded["kind"] = INPUT_KIND
    expanded["cells"] = cells
    validated = _validate_operator_input(expanded, expected_stage=expected_stage)
    return validated, {
        "source_kind": COMPACT_INPUT_KIND,
        "expansion_rule": "FIXED_CODE_ROWS_FOUR_REPLICATES_PER_CONTROLLER_CODE",
        "expanded_cell_count": 64,
        "confidence_derived_as": "NOT_REPORTED",
        "controllers": expansion,
    }


def known_ca_operator_input() -> dict[str, Any]:
    """Return only the CA facts reported in this session; unknowns stay explicit."""

    cells = []
    for controller in CONTROLLERS:
        for row, codes in enumerate(CODE_ROWS):
            for column, code in enumerate(codes):
                cells.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "code": code,
                        "label_verbatim": CA_REPORTED_LABELS[controller][code],
                        "confidence": "NOT_REPORTED",
                        "stable": True,
                    }
                )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": INPUT_KIND,
        "stage": CA_STAGE,
        "observed_at": None,
        "operator": {
            "operator_id": "conversation-user",
            "operator_verbatim": (
                "CS1=C=[橄榄,黑,绿,白,浅黄,蓝,黄,黑]；"
                "CS2=A=[红,粉,绿,白,棕,蓝,深粉,深蓝]。"
                "每侧4行颜色集合相同、仅顺序不同，颜色稳定。"
            ),
        },
        "supervision": {
            "supervisor_id": "NOT_REPORTED",
            "continuous_supervision": None,
            "action_complete_reviewed": None,
            "no_intervening_visible_refresh": None,
            "ambient_light_stable": None,
            "viewing_angle_stable": None,
            "display_stable_through_observation": True,
            "four_replicates_checked": True,
            "electrical_state_normal": None,
            "esp32_restart_observed": None,
            "j2_state_during_observation": "UNKNOWN",
            "supervision_verbatim": "NOT_REPORTED",
        },
        "controls_verbatim": "controls 2,3,5两侧分别绿/白/蓝一致。",
        "artifacts": {
            field: {"observed": None, "operator_verbatim": "NOT_REPORTED"}
            for field in ARTIFACT_FIELDS
        },
        "cells": cells,
    }


def _normalized_label(value: str) -> str:
    return value.strip().casefold()


def _derive(root: Mapping[str, Any], *, stage: str) -> dict[str, Any]:
    contract = _stage_contract(stage)
    by_key = {
        (cell["controller"], cell["row"], cell["column"]): cell
        for cell in root["cells"]
    }
    groups: list[dict[str, Any]] = []
    by_group: dict[tuple[str, int], dict[str, Any]] = {}
    confidence_rank = {"NOT_REPORTED": -1, "LOW": 0, "MEDIUM": 1, "HIGH": 2}
    for controller in CONTROLLERS:
        for code in range(8):
            positions = [
                (row, column)
                for row in range(4)
                for column in range(8)
                if CODE_ROWS[row][column] == code
            ]
            samples = [by_key[(controller, row, column)] for row, column in positions]
            labels = [_normalized_label(sample["label_verbatim"]) for sample in samples]
            counts = Counter(labels)
            consistent = len(counts) == 1
            all_stable = all(sample["stable"] is True for sample in samples)
            consensus = samples[0]["label_verbatim"] if consistent else None
            result = {
                "controller": controller,
                "profile": contract["profile_map"][controller],
                "code": code,
                "role": "CONTROL" if code in CONTROL_CODES else "CANDIDATE",
                "replicate_count": 4,
                "positions": [
                    {
                        "row": sample["row"],
                        "column": sample["column"],
                        "label_verbatim": sample["label_verbatim"],
                        "confidence": sample["confidence"],
                        "stable": sample["stable"],
                    }
                    for sample in samples
                ],
                "normalized_label_counts": dict(sorted(counts.items())),
                "four_replicates_label_consistent": consistent,
                "all_replicates_stable": all_stable,
                "consensus_label_verbatim": consensus,
                "minimum_confidence": min(
                    (sample["confidence"] for sample in samples),
                    key=confidence_rank.get,
                ),
                "eligible_for_comparison": consistent and all_stable,
            }
            if stage == CA_STAGE:
                result["matches_reported_ca_baseline"] = (
                    consistent
                    and _normalized_label(str(consensus))
                    == _normalized_label(CA_REPORTED_LABELS[controller][code])
                )
            groups.append(result)
            by_group[(controller, code)] = result

    controls = []
    for code in CONTROL_CODES:
        left = by_group[("CS1", code)]
        right = by_group[("CS2", code)]
        equal = (
            left["eligible_for_comparison"]
            and right["eligible_for_comparison"]
            and _normalized_label(left["consensus_label_verbatim"])
            == _normalized_label(right["consensus_label_verbatim"])
        )
        controls.append(
            {
                "code": code,
                "cs1_consensus_label_verbatim": left["consensus_label_verbatim"],
                "cs2_consensus_label_verbatim": right["consensus_label_verbatim"],
                "four_replicates_consistent_both_controllers": (
                    left["eligible_for_comparison"] and right["eligible_for_comparison"]
                ),
                "cross_controller_labels_equal": equal,
                "pass": equal,
            }
        )
    supervision = root["supervision"]
    supervision_pass = (
        all(
            supervision[field] is True
            for field in (
                "continuous_supervision",
                "action_complete_reviewed",
                "no_intervening_visible_refresh",
                "ambient_light_stable",
                "viewing_angle_stable",
                "display_stable_through_observation",
                "four_replicates_checked",
                "electrical_state_normal",
            )
        )
        and supervision["esp32_restart_observed"] is False
    )
    artifact_states = [
        root["artifacts"][field]["observed"] for field in ARTIFACT_FIELDS
    ]
    artifacts_explicit = all(type(state) is bool for state in artifact_states)
    any_artifact = any(state is True for state in artifact_states)
    all_groups_eligible = all(item["eligible_for_comparison"] for item in groups)
    ca_reference_match = (
        all(item["matches_reported_ca_baseline"] for item in groups)
        if stage == CA_STAGE
        else None
    )
    control_pass = all(item["pass"] for item in controls)
    ready = (
        all_groups_eligible
        and control_pass
        and supervision_pass
        and artifacts_explicit
        and not any_artifact
        and ca_reference_match is not False
    )
    return {
        "controller_code_groups": groups,
        "replicate_summary": {
            "nominal_replicates_per_controller_code": 4,
            "eligible_group_count": sum(
                item["eligible_for_comparison"] for item in groups
            ),
            "group_count": 16,
            "all_four_replicates_consistent_and_stable": all_groups_eligible,
        },
        "control_summary": {
            "codes": list(CONTROL_CODES),
            "operator_verbatim": root["controls_verbatim"],
            "results": controls,
            "all_controls_pass": control_pass,
        },
        "artifact_summary": {
            "any_artifact_observed": any_artifact,
            "edge_stripe_residual_and_instability_all_explicit": artifacts_explicit,
        },
        "supervision_summary": {
            "gate_pass": supervision_pass,
            "j2_state_recorded": supervision["j2_state_during_observation"],
        },
        "reported_ca_baseline_match": ca_reference_match,
        "comparison_ready": ready,
    }


def seal_observation(
    *, stage: str, action_result_path: Path, operator_input_path: Path
) -> dict[str, Any]:
    """Build one sealed observation in memory without any hardware I/O."""

    _require(stage in STAGES, f"unknown observation stage {stage!r}")
    action_binding = _validate_action_result(action_result_path, stage=stage)
    input_path = Path(operator_input_path).resolve()
    input_payload, input_root = _read_json(input_path, label="operator input")
    compact_source: dict[str, Any] | None = None
    compact_expansion: dict[str, Any] | None = None
    if input_root.get("kind") == COMPACT_INPUT_KIND:
        source, compact_expansion = _expand_compact_operator_input(
            input_root,
            expected_stage=stage,
        )
        compact_source = deepcopy(input_root)
    else:
        source = _validate_operator_input(input_root, expected_stage=stage)
    derived = _derive(source, stage=stage)
    input_binding = _file_reference(input_path, input_payload)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "stage": stage,
        "profile_map": action_binding["profile_map"],
        "layout": {
            "controller_count": 2,
            "rows": 4,
            "columns_per_controller": 8,
            "row_codes": [list(row) for row in CODE_ROWS],
            "replicates_per_controller_code": 4,
            "candidate_codes": list(CANDIDATE_CODES),
            "control_codes": list(CONTROL_CODES),
        },
        "action_result_binding": action_binding,
        "operator_input_binding": input_binding,
        "raw_observation": deepcopy(source),
        "derived_observation": derived,
        "classification_boundary": {
            "human_categorical_observation_only": True,
            "physical_colour_calibrated": False,
            "absolute_colour_claimed": False,
            "formal_gate_evaluated": False,
            "qualified_colour_count": 0,
            "automatic_next_action_authorized": False,
        },
        "offline_execution": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    if compact_source is not None:
        report["compact_operator_input_preserved"] = compact_source
        report["compact_input_expansion"] = compact_expansion
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_observation(path: Path) -> tuple[dict[str, Any], bytes]:
    """Deep-recompute a sealed observation from its two bound source files."""

    payload, root = _read_json(Path(path), label="sealed human observation")
    _verify_integrity(root, label="sealed human observation")
    _require(
        root.get("schema_version") == SCHEMA_VERSION
        and root.get("kind") == OBSERVATION_KIND,
        "sealed observation schema or kind differs",
    )
    recomputed = seal_observation(
        stage=root["stage"],
        action_result_path=Path(root["action_result_binding"]["path"]),
        operator_input_path=Path(root["operator_input_binding"]["path"]),
    )
    _require(recomputed == root, "sealed observation differs from source recomputation")
    return root, payload


def _cell_index(observation: Mapping[str, Any]) -> dict[tuple[str, int, int], str]:
    return {
        (cell["controller"], cell["row"], cell["column"]): cell["label_verbatim"]
        for cell in observation["raw_observation"]["cells"]
    }


def _position_classification(
    *, ca_left: str, ca_right: str, ac_left: str, ac_right: str
) -> str:
    values = tuple(
        _normalized_label(value) for value in (ca_left, ca_right, ac_left, ac_right)
    )
    profile_following = values[2] == values[1] and values[3] == values[0]
    physical_following = values[2] == values[0] and values[3] == values[1]
    if profile_following and physical_following:
        return "NON_DISCRIMINATING"
    if profile_following:
        return "PROFILE_FOLLOWING"
    if physical_following:
        return "PHYSICAL_SIDE_FOLLOWING"
    return "MIXED_OR_UNMATCHED"


def compare_observations(ca_path: Path, ac_path: Path) -> dict[str, Any]:
    """Compare exact CA and AC observations without performing display I/O."""

    ca_root, ca_payload = validate_observation(Path(ca_path))
    ac_root, ac_payload = validate_observation(Path(ac_path))
    _require(ca_root["stage"] == CA_STAGE, "CA observation stage differs")
    _require(ac_root["stage"] == AC_STAGE, "AC observation stage differs")
    ca_action = ca_root["action_result_binding"]
    ac_action = ac_root["action_result_binding"]
    _require(
        ca_action["frame_sha256"] == ac_action["frame_sha256"]
        and ca_action["cs1_dtm_sha256"] == ac_action["cs1_dtm_sha256"]
        and ca_action["cs2_dtm_sha256"] == ac_action["cs2_dtm_sha256"],
        "CA/AC frame or DTM differs",
    )
    ca_ids = {
        ca_action["campaign_id"],
        ca_action["contract_id"],
        ca_action["descriptor_id"],
        ca_action["action_id"],
    }
    ac_ids = {
        ac_action["campaign_id"],
        ac_action["contract_id"],
        ac_action["descriptor_id"],
        ac_action["action_id"],
    }
    _require(not ca_ids & ac_ids, "fresh AC identity overlaps consumed CA")

    ca_cells = _cell_index(ca_root)
    ac_cells = _cell_index(ac_root)
    code_results = []
    for code in range(8):
        positions = [
            (row, column)
            for row in range(4)
            for column in range(8)
            if CODE_ROWS[row][column] == code
        ]
        position_results = []
        for row, column in positions:
            ca_left = ca_cells[("CS1", row, column)]
            ca_right = ca_cells[("CS2", row, column)]
            ac_left = ac_cells[("CS1", row, column)]
            ac_right = ac_cells[("CS2", row, column)]
            position_results.append(
                {
                    "row": row,
                    "column": column,
                    "ca_cs1_c_label_verbatim": ca_left,
                    "ca_cs2_a_label_verbatim": ca_right,
                    "ac_cs1_a_label_verbatim": ac_left,
                    "ac_cs2_c_label_verbatim": ac_right,
                    "classification": _position_classification(
                        ca_left=ca_left,
                        ca_right=ca_right,
                        ac_left=ac_left,
                        ac_right=ac_right,
                    ),
                }
            )
        counts = Counter(item["classification"] for item in position_results)
        if counts["PROFILE_FOLLOWING"] >= 3 and counts["PHYSICAL_SIDE_FOLLOWING"] == 0:
            classification = "PROFILE_FOLLOWING"
        elif (
            counts["PHYSICAL_SIDE_FOLLOWING"] >= 3 and counts["PROFILE_FOLLOWING"] == 0
        ):
            classification = "PHYSICAL_SIDE_FOLLOWING"
        elif counts["NON_DISCRIMINATING"] == 4:
            classification = "NON_DISCRIMINATING_CONTROL"
        else:
            classification = "INCONCLUSIVE_MIXED"
        code_results.append(
            {
                "code": code,
                "role": "CONTROL" if code in CONTROL_CODES else "CANDIDATE",
                "position_results": position_results,
                "position_classification_counts": {
                    key: counts[key]
                    for key in (
                        "PROFILE_FOLLOWING",
                        "PHYSICAL_SIDE_FOLLOWING",
                        "NON_DISCRIMINATING",
                        "MIXED_OR_UNMATCHED",
                    )
                },
                "classification": classification,
            }
        )

    candidate_results = [
        item for item in code_results if item["code"] in CANDIDATE_CODES
    ]
    control_results = [item for item in code_results if item["code"] in CONTROL_CODES]
    candidate_counts = Counter(item["classification"] for item in candidate_results)
    controls_pass = all(
        item["classification"] == "NON_DISCRIMINATING_CONTROL"
        for item in control_results
    )
    inputs_ready = (
        ca_root["derived_observation"]["comparison_ready"] is True
        and ac_root["derived_observation"]["comparison_ready"] is True
    )
    if inputs_ready and controls_pass:
        if candidate_counts["PROFILE_FOLLOWING"] == 5:
            input_gate_classification = "PROFILE_FOLLOWING_STRONG"
        elif (
            candidate_counts["PROFILE_FOLLOWING"] >= 4
            and candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 0
        ):
            input_gate_classification = "PROFILE_FOLLOWING_SUPPORTED"
        elif candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 5:
            input_gate_classification = "PHYSICAL_SIDE_FOLLOWING_STRONG"
        elif (
            candidate_counts["PHYSICAL_SIDE_FOLLOWING"] >= 4
            and candidate_counts["PROFILE_FOLLOWING"] == 0
        ):
            input_gate_classification = "PHYSICAL_SIDE_FOLLOWING_SUPPORTED"
        else:
            input_gate_classification = "INCONCLUSIVE_MIXED"
    else:
        input_gate_classification = "INCONCLUSIVE_INPUT_OR_CONTROL_GATE"

    # The already-reported CA baseline lacks formal supervision metadata, but
    # it does contain stable four-replicate labels for every fixed code.  Keep
    # the formal gate closed while still allowing the explicitly narrower
    # human screen to answer the profile-vs-side design question once AC is
    # fully observed.
    ca_derived = ca_root["derived_observation"]
    ac_derived = ac_root["derived_observation"]
    screening_inputs_ready = (
        ca_derived["reported_ca_baseline_match"] is True
        and ca_derived["replicate_summary"]["all_four_replicates_consistent_and_stable"]
        is True
        and ca_derived["control_summary"]["all_controls_pass"] is True
        and ac_derived["comparison_ready"] is True
    )
    if screening_inputs_ready and controls_pass:
        if candidate_counts["PROFILE_FOLLOWING"] == 5:
            screening_classification = "HUMAN_SCREEN_PROFILE_FOLLOWING_STRONG"
        elif (
            candidate_counts["PROFILE_FOLLOWING"] >= 4
            and candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 0
        ):
            screening_classification = "HUMAN_SCREEN_PROFILE_FOLLOWING_SUPPORTED"
        elif candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 5:
            screening_classification = "HUMAN_SCREEN_PHYSICAL_SIDE_FOLLOWING_STRONG"
        elif (
            candidate_counts["PHYSICAL_SIDE_FOLLOWING"] >= 4
            and candidate_counts["PROFILE_FOLLOWING"] == 0
        ):
            screening_classification = "HUMAN_SCREEN_PHYSICAL_SIDE_FOLLOWING_SUPPORTED"
        else:
            screening_classification = "HUMAN_SCREEN_INCONCLUSIVE_MIXED"
    else:
        screening_classification = "HUMAN_SCREEN_INCONCLUSIVE_INPUT_OR_CONTROL_GATE"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "method_id": "blind-ca-v2-vs-fresh-ac-four-replicate-human-crossover-v1",
        "input_bindings": {
            "ca_observation": {
                **_file_reference(Path(ca_path).resolve(), ca_payload),
                "canonical_integrity_sha256": ca_root["integrity"]["sha256"],
                "action_id": ca_action["action_id"],
            },
            "ac_observation": {
                **_file_reference(Path(ac_path).resolve(), ac_payload),
                "canonical_integrity_sha256": ac_root["integrity"]["sha256"],
                "action_id": ac_action["action_id"],
            },
        },
        "matched_payload": {
            "frame_sha256": ca_action["frame_sha256"],
            "cs1_dtm_sha256": ca_action["cs1_dtm_sha256"],
            "cs2_dtm_sha256": ca_action["cs2_dtm_sha256"],
            "row_codes": [list(row) for row in CODE_ROWS],
            "fresh_action_identities_distinct": True,
        },
        "candidate_codes": list(CANDIDATE_CODES),
        "control_codes": list(CONTROL_CODES),
        "code_results": code_results,
        "summary": {
            "classification": screening_classification,
            "human_screening_classification": screening_classification,
            "formal_classification": "FORMAL_NOT_EVALUATED",
            "full_supervision_input_gate_classification": input_gate_classification,
            "candidate_classification_counts": {
                key: candidate_counts[key]
                for key in (
                    "PROFILE_FOLLOWING",
                    "PHYSICAL_SIDE_FOLLOWING",
                    "INCONCLUSIVE_MIXED",
                )
            },
            "controls_pass": controls_pass,
            "both_observations_comparison_ready": inputs_ready,
            "human_screening_inputs_ready": screening_inputs_ready,
        },
        "evidence_boundaries": {
            "human_categorical_profile_following_screen_only": True,
            "complete_ac_ca_tuple_not_r20_only": True,
            "global_header_is_part_of_the_swapped_tuple": True,
            "physical_colour_calibrated": False,
            "absolute_colour_claimed": False,
            "formal_gate_evaluated": False,
            "qualified_colour_count": 0,
            "automatic_action_authorized": False,
            "hardware_io_performed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_comparison(path: Path) -> tuple[dict[str, Any], bytes]:
    payload, root = _read_json(Path(path), label="human profile comparison")
    _verify_integrity(root, label="human profile comparison")
    _require(
        root.get("schema_version") == SCHEMA_VERSION
        and root.get("kind") == COMPARISON_KIND,
        "human comparison schema or kind differs",
    )
    recomputed = compare_observations(
        Path(root["input_bindings"]["ca_observation"]["path"]),
        Path(root["input_bindings"]["ac_observation"]["path"]),
    )
    _require(recomputed == root, "human comparison differs from source recomputation")
    return root, payload


def _serialize(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(Path(path), flags, 0o600)
    except FileExistsError as error:
        raise HumanObservationError(f"refusing to overwrite output: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            Path(path).unlink()
        except OSError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    known_ca = commands.add_parser("write-known-ca-input", allow_abbrev=False)
    known_ca.add_argument("--output", type=Path, required=True)
    seal = commands.add_parser("seal", allow_abbrev=False)
    seal.add_argument("--stage", choices=STAGES, required=True)
    seal.add_argument("--action-result", type=Path, required=True)
    seal.add_argument("--input", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--observation", type=Path, required=True)
    seal_white = commands.add_parser("seal-clean-white", allow_abbrev=False)
    seal_white.add_argument("--action-result", type=Path, required=True)
    seal_white.add_argument("--relay-off-receipt", type=Path, required=True)
    seal_white.add_argument("--input", type=Path, required=True)
    seal_white.add_argument("--output", type=Path, required=True)
    validate_white = commands.add_parser("validate-clean-white", allow_abbrev=False)
    validate_white.add_argument("--observation", type=Path, required=True)
    compare = commands.add_parser("compare", allow_abbrev=False)
    compare.add_argument("--ca-observation", type=Path, required=True)
    compare.add_argument("--ac-observation", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    validate_comparison_parser = commands.add_parser(
        "validate-comparison", allow_abbrev=False
    )
    validate_comparison_parser.add_argument("--comparison", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "write-known-ca-input":
            value = known_ca_operator_input()
            _validate_operator_input(value, expected_stage=CA_STAGE)
            payload = _serialize(value)
            write_exclusive(args.output, payload)
        elif args.command == "seal":
            value = seal_observation(
                stage=args.stage,
                action_result_path=args.action_result,
                operator_input_path=args.input,
            )
            payload = _serialize(value)
            write_exclusive(args.output, payload)
        elif args.command == "validate":
            value, payload = validate_observation(args.observation)
        elif args.command == "seal-clean-white":
            value = seal_clean_white_observation(
                action_result_path=args.action_result,
                relay_off_receipt_path=args.relay_off_receipt,
                operator_input_path=args.input,
            )
            payload = _serialize(value)
            write_exclusive(args.output, payload)
        elif args.command == "validate-clean-white":
            value, payload = validate_clean_white_observation(args.observation)
        elif args.command == "compare":
            value = compare_observations(args.ca_observation, args.ac_observation)
            payload = _serialize(value)
            write_exclusive(args.output, payload)
        else:
            value, payload = validate_comparison(args.comparison)
    except HumanObservationError as error:
        print(f"profile-following human-observation error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
