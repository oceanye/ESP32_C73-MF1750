#!/usr/bin/env python3
"""Fail-closed one-action runner for the fixed PTLW HOLD builds.

This runner never controls power, relay, serial, flashing, reset, retry,
recovery, or action chaining.  Select one immutable firmware variant, then
consume at most one fixed ARM/EXECUTE action per invocation.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from tools import mf1750_partial_hold_matrix as matrix


_BASE_PATH = Path(__file__).with_name(
    "mf1750_ec5_otp_transition_matrix_recheck_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_partial_hold_runner_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_PATH}")
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)

_BASE_DESCRIBE = runner.describe
_BASE_VALIDATE_VERSION = runner._validate_version
_BASE_VALIDATE_MANIFEST = runner._validate_manifest
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 40.0

_VARIANT_ALIASES = {
    "accumulate": 0,
    "edges": 1,
    "cs-split": 2,
    "accumulate-vmirror": 3,
    "accumulate-symmetric-v2": 4,
    "accumulate-symmetric-y-inclusive": 5,
    "accumulate-symmetric-blue1": 6,
    "accumulate-symmetric-y-inclusive-blue1": 7,
}
_BUILD_BINDINGS = {
    0: {
        "build_tag": "MF1750_EC5_PARTIAL_HOLD_ACCUMULATE_V1_2026-08-22",
        "test_id": "EC5-PARTIAL-HOLD-ACCUMULATE-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_ACCUMULATE_V1",
        "nvs": "phold_acc_v1",
        "firmware_bytes": 788080,
        "firmware_sha256": (
            "b59b8da904a62049e14a133b5d6ecf8d60d86d0a8b11aa815096ff6373e50eba"
        ),
    },
    1: {
        "build_tag": "MF1750_EC5_PARTIAL_HOLD_EDGES_V1_2026-08-22",
        "test_id": "EC5-PARTIAL-HOLD-EDGES-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_EDGES_V1",
        "nvs": "phold_edge_v1",
        "firmware_bytes": 788048,
        "firmware_sha256": (
            "7729107335a98f4746be8e6ba72f815aa4efdf45a70d5b261fd1c6320a9c4542"
        ),
    },
    2: {
        "build_tag": "MF1750_EC5_PARTIAL_HOLD_CS_SPLIT_V1_2026-08-22",
        "test_id": "EC5-PARTIAL-HOLD-CS-SPLIT-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_CS_SPLIT_V1",
        "nvs": "phold_split_v1",
        "firmware_bytes": 788256,
        "firmware_sha256": (
            "9a74b75816bfe05667f5f929054e42afb311073c7425803b2c4a70063aee6889"
        ),
    },
    3: {
        "build_tag": "MF1750_EC5_PARTIAL_HOLD_ACC_VMIRROR_V1_2026-08-22",
        "test_id": "EC5-PARTIAL-HOLD-ACC-VMIRROR-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_ACC_VMIRROR_V1",
        "nvs": "phold_vmir_v1",
        "firmware_bytes": 788176,
        "firmware_sha256": (
            "5af06182af1bc372495c668a2594b8d7011ae6d8b4ba7948a6eb23f381948cc7"
        ),
    },
    4: {
        "build_tag": "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_V2_2026-08-22",
        "test_id": "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-V2",
        "campaign_id": "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_V2",
        "nvs": "phold_sym_v2",
        "firmware_bytes": 788176,
        "firmware_sha256": (
            "f0b949500e8ee67c9a51d2f874d257fe338570138a39e857c16dbad581817e69"
        ),
    },
    5: {
        "build_tag": (
            "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_V1_2026-08-22"
        ),
        "test_id": "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-Y-INCLUSIVE-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_V1",
        "nvs": "phold_yinc_v1",
        "firmware_bytes": 788224,
        "firmware_sha256": (
            "503519a1b9a9a66f1b845b5da8ef0d83b03e923ba747596e8ef311e6cb73fdd9"
        ),
    },
    6: {
        "build_tag": (
            "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_BLUE1_V1_2026-08-22"
        ),
        "test_id": "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-BLUE1-V1",
        "campaign_id": "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_BLUE1_V1",
        "nvs": "phold_b1_v1",
        "firmware_bytes": 788176,
        "firmware_sha256": (
            "0ef453400cf78c9a7fb2de2a26283670de218e834994da2a2f5f4de7fe1a1769"
        ),
    },
    7: {
        "build_tag": (
            "MF1750_EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_BLUE1_V1_2026-08-22"
        ),
        "test_id": (
            "EC5-PARTIAL-HOLD-ACC-SYMMETRIC-Y-INCLUSIVE-BLUE1-V1"
        ),
        "campaign_id": (
            "EC5_PARTIAL_HOLD_ACC_SYMMETRIC_Y_INCLUSIVE_BLUE1_V1"
        ),
        "nvs": "ph_yinc_b1_v1",
        "firmware_bytes": 788256,
        "firmware_sha256": (
            "64a6102e53abaf010ad0ea7b5679c62fc17e627251a8a649b8d0540779dda71a"
        ),
    },
}
_BRANCHES = {
    0: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_DISJOINT_A",
        "PTLW_BLUE_DISJOINT_B_HOLD_A",
        "PTLW_GREEN_NESTED_OVERWRITE_HOLD_B",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    1: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_LEFT_EDGE_YELLOW",
        "PTLW_RIGHT_EDGE_BLUE_HOLD_A",
        "PTLW_LOWER_RED_HOLD_AB",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    2: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_CS1_RED_CS2_BLUE",
        "PTLW_CS1_YELLOW_CS2_GREEN_HOLD_A",
        "PTLW_CS1_BLACK_CS2_RED_HOLD_AB",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    3: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_A_CS2_VMIRROR",
        "PTLW_BLUE_B_CS2_VMIRROR_HOLD_A",
        "PTLW_GREEN_C_CS2_VMIRROR_HOLD_AB",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    4: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_A_SYMMETRIC_SEPARATE_CS",
        "PTLW_BLUE_B_SYMMETRIC_SEPARATE_CS_HOLD_A",
        "PTLW_GREEN_C_SYMMETRIC_SEPARATE_CS_HOLD_AB",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    5: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_A_SYMMETRIC_Y_INCLUSIVE",
        "PTLW_BLUE2_B_SYMMETRIC_Y_INCLUSIVE_HOLD_A",
        "PTLW_GREEN_C_SYMMETRIC_Y_INCLUSIVE_HOLD_AB",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    6: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_A_SYMMETRIC_BLUE1_CONTROL",
        "PTLW_BLUE1_B_SYMMETRIC_HOLD_A",
        "PTLW_GREEN_C_SYMMETRIC_HOLD_BLUE1",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
    7: (
        "FACTORY_OTP_FULL_WHITE",
        "PTLW_RED_A_SYMMETRIC_Y_INCLUSIVE_BLUE1_CONTROL",
        "PTLW_BLUE1_B_SYMMETRIC_Y_INCLUSIVE_HOLD_A",
        "PTLW_GREEN_C_SYMMETRIC_Y_INCLUSIVE_HOLD_BLUE1",
        "FACTORY_OTP_FULL_WHITE_RECOVERY",
    ),
}

_active_variant = 0


def _actions(index: int) -> tuple[dict[str, Any], ...]:
    generated = matrix.build_report()["variants"][index]["actions"]
    action_ids = [item["action_id"] for item in generated]
    return tuple(
        {
            "ordinal": ordinal,
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "prior_static_action_id": (
                None if ordinal == 1 else action_ids[ordinal - 2]
            ),
            "role": item["role"],
            "round": 1,
            "branch": _BRANCHES[index][ordinal - 1],
            "frame_sha256": item["frame"]["sha256"],
            "cs1_dtm_sha256": item["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": item["cs2_dtm"]["sha256"],
            "transport_code_histogram": item["frame"]["histogram"],
        }
        for ordinal, item in enumerate(generated, 1)
    )


def configure_variant(value: str | int) -> None:
    """Bind the shared runner to one exact firmware variant."""

    global _active_variant
    index = _VARIANT_ALIASES[value] if isinstance(value, str) else value
    if index not in _BUILD_BINDINGS:
        raise ValueError("unknown partial-HOLD variant")
    _active_variant = index
    binding = _BUILD_BINDINGS[index]
    generated = matrix.build_report()["variants"][index]
    runner.BUILD_TAG = binding["build_tag"]
    runner.TEST_ID = binding["test_id"]
    runner.CAMPAIGN_ID = binding["campaign_id"]
    runner.DEVICE_API_VERSION = "MF1750_EC5_PARTIAL_HOLD_DEVICE_V1"
    runner.IDENTITY_REVISION = "partial-hold-v1"
    runner.CONTRACT_ID = generated["contract_id"]
    runner.CLASSIFICATION = (
        "EXPERIMENTAL_SPD1657_PTLW_FACTORY_OTP_LOCAL_HOLD_CANDIDATE"
    )
    runner.DEVICE_KIND_PREFIX = "mf1750-ec5-partial-hold"
    runner.EVIDENCE_KIND_PREFIX = (
        f"mf1750-ec5-partial-hold-{generated['variant']['key'].lower()}"
    )
    runner.NVS_NAMESPACE = binding["nvs"]
    runner.NVS_KEY = "cursor_v1"
    runner.FIRMWARE_SHA256 = binding["firmware_sha256"]
    runner.FIRMWARE_BYTES = binding["firmware_bytes"]
    runner.ENDPOINTS = {
        name: f"/api/ec5/partial-hold/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    runner.ARM_INTENT = "ARM_ONE_FIXED_EXPERIMENTAL_PTLW_ACTION"
    runner.EXECUTE_INTENT = "EXECUTE_ARMED_EXPERIMENTAL_PTLW_ACTION_ONCE"
    runner.ACTIONS = _actions(index)
    runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in runner.ACTIONS
    )
    runner.ACTION_IDS = tuple(item["action_id"] for item in runner.ACTIONS)
    variant_name = next(
        name for name, candidate in _VARIANT_ALIASES.items() if candidate == index
    )
    runner.DEFAULT_CLAIMS = (
        runner.REPO_ROOT
        / ".test-output"
        / "hardware"
        / f".mf1750_partial_hold_{variant_name}_claims"
    )
    runner.DEFAULT_OUTPUT = (
        runner.REPO_ROOT
        / ".test-output"
        / "hardware"
        / f"MF1750_PARTIAL_HOLD_{variant_name.upper()}_20260822_V1"
    )


def firmware_is_bound() -> bool:
    return (
        isinstance(runner.FIRMWARE_SHA256, str)
        and _SHA256.fullmatch(runner.FIRMWARE_SHA256) is not None
        and isinstance(runner.FIRMWARE_BYTES, int)
        and runner.FIRMWARE_BYTES > 0
    )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = ("partial_refresh", "window_refresh", "command_0x83")
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
    )
    if any(value.get(key) is not True for key in required_true):
        raise runner.RecheckError("device PTLW capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise runner.RecheckError("device forbidden-operation contract differs")
    if value.get("full_screen_global_refresh") is not True:
        raise runner.RecheckError("device synchronized refresh contract differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _BASE_VALIDATE_VERSION(value)
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _BASE_VALIDATE_MANIFEST(value)
    _validate_capabilities(value)


def describe() -> dict[str, Any]:
    value = _BASE_DESCRIBE()
    generated = matrix.build_report()["variants"][_active_variant]["variant"]
    value["variant"] = generated
    value["firmware"]["bound"] = firmware_is_bound()
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "ptlw_command": "0x83",
        "ptlw_payload_bytes": 9,
        "cropped_dtm": True,
        "synchronized_dual_controller_refresh": True,
        "blocking_refresh_first_poll_floor_seconds": (
            _BLOCKING_REFRESH_POLL_FLOOR_SECONDS
        ),
    }
    value["forbidden_operations"] = {
        "command_0x86": True,
        "runtime_lut_write": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    return value


configure_variant(0)
runner._validate_version = _validate_version
runner._validate_manifest = _validate_manifest
runner.describe = describe


def _parse_wrapper(argv: Sequence[str] | None) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--variant", choices=tuple(_VARIANT_ALIASES), required=True)
    args, remaining = parser.parse_known_args(argv)
    return args.variant, remaining


def _apply_blocking_refresh_poll_floor(arguments: Sequence[str]) -> list[str]:
    remaining = list(arguments)
    if remaining and remaining[0] == "run":
        poll_token = next(
            (
                (index, token)
                for index, token in enumerate(remaining)
                if token == "--poll-seconds"
                or token.startswith("--poll-seconds=")
            ),
            None,
        )
        if poll_token is None:
            remaining.extend(
                ["--poll-seconds", str(_BLOCKING_REFRESH_POLL_FLOOR_SECONDS)]
            )
        else:
            poll_index, token = poll_token
            if token == "--poll-seconds":
                if poll_index + 1 >= len(remaining):
                    raise SystemExit("--poll-seconds requires a value")
                raw_poll = remaining[poll_index + 1]
            else:
                raw_poll = token.partition("=")[2]
            try:
                requested_poll = float(raw_poll)
            except ValueError as error:
                raise SystemExit("--poll-seconds must be numeric") from error
            if requested_poll < _BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
                raise SystemExit(
                    "partial-HOLD run requires --poll-seconds >= "
                    f"{_BLOCKING_REFRESH_POLL_FLOOR_SECONDS:g}"
                )
    return remaining


def main(argv: Sequence[str] | None = None) -> int:
    variant, remaining = _parse_wrapper(argv)
    configure_variant(variant)
    remaining = _apply_blocking_refresh_poll_floor(remaining)
    return runner.main(remaining)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
