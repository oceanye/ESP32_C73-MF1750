#!/usr/bin/env python3
"""One-action runner for the fixed L535 runtime-LUT + PTLW HOLD probe.

The runner does not flash, reset, or control power.  Each invocation consumes
at most one immutable ARM/EXECUTE action and never retries or autochains.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as pack  # noqa: E402


_BASE_PATH = Path(__file__).with_name(
    "mf1750_ec5_otp_transition_matrix_recheck_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_partial_hold_runner_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_PATH}")
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)

_BASE_DESCRIBE = runner.describe
_BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 40.0
_REPORT = pack.build_report()


def _actions() -> tuple[dict[str, Any], ...]:
    source = _REPORT["actions"]
    action_ids = [item["action_id"] for item in source]
    return tuple(
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "prior_static_action_id": (
                None if item["ordinal"] == 1 else action_ids[item["ordinal"] - 2]
            ),
            "role": item["role"],
            "round": 1,
            "branch": item["branch"],
            "frame_sha256": item["frame"]["sha256"],
            "cs1_dtm_sha256": item["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": item["cs2_dtm"]["sha256"],
            "transport_code_histogram": item["frame"]["histogram"],
        }
        for item in source
    )


runner.BUILD_TAG = pack.BUILD_TAG
runner.TEST_ID = pack.TEST_ID
runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
runner.DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V1"
runner.IDENTITY_REVISION = "runtime-lut-partial-hold-v1"
runner.CONTRACT_ID = _REPORT["contract_id"]
runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_PTLW_LOCAL_HOLD_CANDIDATE"
)
runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-partial-hold"
runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-partial-hold-l535-active"
runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
runner.NVS_KEY = "cursor_v1"
runner.FIRMWARE_SHA256 = (
    "bcb52fe19f54e67ed8dee9f2d7692739d6cba059fc48bb07e0f60611987195f9"
)
runner.FIRMWARE_BYTES = 793312
runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-partial-hold/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
runner.ARM_INTENT = "ARM_ONE_FIXED_L535_RUNTIME_LUT_PTLW_ACTION"
runner.EXECUTE_INTENT = "EXECUTE_ARMED_L535_RUNTIME_LUT_PTLW_ACTION_ONCE"
runner.ACTIONS = _actions()
runner.DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in runner.ACTIONS)
runner.ACTION_IDS = tuple(item["action_id"] for item in runner.ACTIONS)
runner.DEFAULT_CLAIMS = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_partial_hold_l535_active_claims"
)
runner.DEFAULT_OUTPUT = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_20260822_V1"
)


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "same_palette_hold_probe",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "cross_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise runner.RecheckError("runtime-LUT PTLW capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise runner.RecheckError("runtime-LUT PTLW forbidden-operation contract differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    runner._identity(value, kind_suffix="version")
    expected_false = (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    )
    if value.get("action_count") != len(runner.ACTIONS):
        raise runner.RecheckError("device action count differs")
    if value.get("runtime_lut_write") is not True or any(
        value.get(key) is not False for key in expected_false
    ):
        raise runner.RecheckError("device runtime-LUT safety contract differs")
    nvs = value.get("nvs_contract", {})
    if nvs.get("namespace") != runner.NVS_NAMESPACE or nvs.get("key") != runner.NVS_KEY:
        raise runner.RecheckError("device NVS isolation differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    runner._identity(value, kind_suffix="manifest")
    if value.get("actions") != list(runner.ACTIONS):
        raise runner.RecheckError("device fixed action manifest differs")
    exact = {
        "action_count": len(runner.ACTIONS),
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise runner.RecheckError(f"device manifest {key} differs")
    layout = value.get("history_layout", {})
    if (
        layout.get("runtime_lut_profile_id") != pack.PROFILE_ID
        or layout.get("ptlw_endpoint_contract") != "xe=x+w-1;ye=y+h-1"
        or layout.get("windows_disjoint") is not True
        or layout.get("white_transport_code") != pack.WHITE_CODE
    ):
        raise runner.RecheckError("device runtime-LUT/PTLW layout differs")
    profile = _REPORT["contract"]["profile"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != profile[key]:
            raise runner.RecheckError(f"device LUT profile {key} differs")
    _validate_capabilities(value)


def describe() -> dict[str, Any]:
    value = _BASE_DESCRIBE()
    value["variant"] = _REPORT["contract"]
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_id": pack.PROFILE_ID,
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "cropped_dtm": True,
        "three_disjoint_windows": True,
        "blocking_refresh_first_poll_floor_seconds": (
            _BLOCKING_REFRESH_POLL_FLOOR_SECONDS
        ),
    }
    value["forbidden_operations"] = {
        "command_0x86": True,
        "cross_palette_switch": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    return value


runner._validate_version = _validate_version
runner._validate_manifest = _validate_manifest
runner.describe = describe


def _apply_poll_floor(argv: Sequence[str] | None) -> list[str]:
    arguments = list(argv or [])
    if arguments and arguments[0] == "run":
        for index, token in enumerate(arguments):
            if token == "--poll-seconds":
                if index + 1 >= len(arguments):
                    raise SystemExit("--poll-seconds requires a value")
                if float(arguments[index + 1]) < _BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
                    raise SystemExit("run requires --poll-seconds >= 40")
                break
            if token.startswith("--poll-seconds="):
                if float(token.partition("=")[2]) < _BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
                    raise SystemExit("run requires --poll-seconds >= 40")
                break
        else:
            arguments.extend(
                ["--poll-seconds", str(_BLOCKING_REFRESH_POLL_FLOOR_SECONDS)]
            )
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    return runner.main(_apply_poll_floor(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
