#!/usr/bin/env python3
"""Private factory for the fail-closed cross-palette AB/BA runners."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Literal, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_v1_pack as pack  # noqa: E402


Direction = Literal["ab", "ba"]
_BASE_PATH = Path(__file__).with_name("mf1750_runtime_lut_partial_hold_once.py")
_FIRMWARE = {
    "ab": {
        "sha256": "e56649be80b67602d6b1da46e6a0ca1f6ff295e1fa601e9d1b9291902f4573ca",
        "bytes": 793840,
    },
    "ba": {
        "sha256": "fc328a5bbb7d723b6b1e4ccc0cacec6c574041f4b67b9dd84c7351fcf18bc646",
        "bytes": 793824,
    },
}


def configure(direction: Direction):
    """Return an isolated, direction-bound runner module."""
    if direction not in ("ab", "ba"):
        raise ValueError("direction must be ab or ba")
    spec = importlib.util.spec_from_file_location(
        f"_mf1750_runtime_lut_cross_palette_{direction}_private_base", _BASE_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load runner base: {_BASE_PATH}")
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)

    report = pack.build_report(direction)
    values = pack.constants(direction)
    base.pack = pack
    base._REPORT = report
    base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 55.0
    base.runner.BUILD_TAG = values["build_tag"]
    base.runner.TEST_ID = values["test_id"]
    base.runner.CAMPAIGN_ID = values["campaign_id"]
    base.runner.DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_DEVICE_V1"
    base.runner.IDENTITY_REVISION = "runtime-lut-cross-palette-v1"
    base.runner.CONTRACT_ID = report["contract_id"]
    base.runner.CLASSIFICATION = (
        "EXPERIMENTAL_L535_BIDIRECTIONAL_8X8_CROSS_PALETTE_HOLD_SEARCH"
    )
    base.runner.EVIDENCE_KIND_PREFIX = (
        f"mf1750-ec5-runtime-lut-cross-palette-{direction}-v1"
    )
    base.runner.NVS_NAMESPACE = values["nvs_namespace"]
    base.runner.NVS_KEY = "cursor_v1"
    base.runner.ARM_INTENT = "ARM_ONE_FIXED_L535_RUNTIME_LUT_CROSS_PALETTE_ACTION"
    base.runner.EXECUTE_INTENT = (
        "EXECUTE_ARMED_L535_RUNTIME_LUT_CROSS_PALETTE_ACTION_ONCE"
    )
    base.runner.FIRMWARE_SHA256 = _FIRMWARE[direction]["sha256"]
    base.runner.FIRMWARE_BYTES = _FIRMWARE[direction]["bytes"]
    base.runner.ACTIONS = base._actions()
    base.runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in base.runner.ACTIONS
    )
    base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
    base.runner.DEFAULT_CLAIMS = (
        base.runner.REPO_ROOT
        / ".test-output"
        / "hardware"
        / f".mf1750_runtime_lut_cross_palette_{direction}_v1_claims"
    )
    base.runner.DEFAULT_OUTPUT = (
        base.runner.REPO_ROOT
        / ".test-output"
        / "hardware"
        / f"MF1750_RUNTIME_LUT_CROSS_PALETTE_{direction.upper()}_20260823_V1"
    )

    source_header = "active" if direction == "ab" else "commented"
    target_header = "commented" if direction == "ab" else "active"
    action_headers = ["active", source_header, target_header, target_header, "active"]
    source_profile = pack.profile(source_header)["id"]
    target_profile = pack.profile(target_header)["id"]

    def validate_capabilities(value: Mapping[str, Any]) -> None:
        required_true = (
            "full_screen_global_refresh",
            "cross_palette_hold_probe",
            "target_repeat_stability_probe",
        )
        required_false = (
            "partial_refresh",
            "window_refresh",
            "command_0x83",
            "command_0x86",
            "mid_refresh_power_cut",
            "spi_frequency_sweep",
            "same_palette_hold_probe",
            "full_frame_cumulative_redraw",
        )
        if any(value.get(key) is not True for key in required_true):
            raise base.runner.RecheckError("cross-palette capability contract differs")
        if any(value.get(key) is not False for key in required_false):
            raise base.runner.RecheckError(
                "cross-palette forbidden-operation contract differs"
            )

    def validate_version(value: Mapping[str, Any]) -> None:
        base.runner._identity(value, kind_suffix="version")
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
        if value.get("action_count") != len(base.runner.ACTIONS):
            raise base.runner.RecheckError("device action count differs")
        if value.get("runtime_lut_write") is not True or any(
            value.get(key) is not False for key in expected_false
        ):
            raise base.runner.RecheckError("device cross-palette safety differs")
        nvs = value.get("nvs_contract", {})
        if (
            nvs.get("namespace") != base.runner.NVS_NAMESPACE
            or nvs.get("key") != base.runner.NVS_KEY
        ):
            raise base.runner.RecheckError("device NVS isolation differs")
        validate_capabilities(value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        base.runner._identity(value, kind_suffix="manifest")
        if value.get("actions") != list(base.runner.ACTIONS):
            raise base.runner.RecheckError("device fixed action manifest differs")
        exact = {
            "action_count": len(base.runner.ACTIONS),
            "one_driver_call_per_action": True,
            "factory_otp": False,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
        }
        for key, wanted in exact.items():
            if value.get(key) != wanted:
                raise base.runner.RecheckError(f"device manifest {key} differs")
        layout = value.get("history_layout", {})
        expected_profile = f"{source_profile}_TO_{target_profile}"
        if (
            layout.get("cross_palette_direction") != direction
            or layout.get("action_global_headers") != action_headers
            or layout.get("source_profile_id") != source_profile
            or layout.get("target_profile_id") != target_profile
            or layout.get("runtime_lut_profile_id") != expected_profile
            or layout.get("ptlw_command_issued") is not False
            or layout.get("cropped_dtm") is not False
            or layout.get("all_action_dtm_transport") != "packed_frame_per_controller"
            or layout.get("source_rows") != 8
            or layout.get("target_columns_per_controller") != 8
            or layout.get("history_cells_per_controller") != 64
            or layout.get("history_cells_total") != 128
            or layout.get("target_repeat_stability_probe") is not True
            or layout.get("white_transport_code") != pack.WHITE_CODE
        ):
            raise base.runner.RecheckError("device cross-palette layout differs")
        fixed_profile = pack.profile(source_header)
        for key in (
            "cs1_r20_prefix_bytes",
            "cs1_r20_prefix_sha256",
            "cs2_r20_prefix_bytes",
            "cs2_r20_prefix_sha256",
            "r21_bytes",
            "r21_sha256",
        ):
            if layout.get(key) != fixed_profile[key]:
                raise base.runner.RecheckError(f"device LUT profile {key} differs")
        validate_capabilities(value)

    def describe() -> dict[str, Any]:
        value = base._BASE_DESCRIBE()
        value["variant"] = report["contract"]
        value["fixed_transport"] = {
            "spi_hz": 1_000_000,
            "runtime_lut": True,
            "direction": direction,
            "source_profile_id": source_profile,
            "target_profile_id": target_profile,
            "ptlw_command_issued": False,
            "cropped_dtm": False,
            "packed_full_frame_per_controller": True,
            "source_rows": 8,
            "target_columns_per_controller": 8,
            "history_cells_total": 128,
            "target_repeat_stability_probe": True,
            "blocking_refresh_first_poll_floor_seconds": (
                base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS
            ),
        }
        value["forbidden_operations"] = {
            "partial_window": True,
            "command_0x83": True,
            "command_0x86": True,
            "mid_refresh_power_cut": True,
            "spi_frequency_sweep": True,
            "automatic_retry": True,
            "automatic_recovery": True,
            "automatic_chaining": True,
        }
        return value

    base._validate_version = validate_version
    base._validate_manifest = validate_manifest
    base.runner._validate_version = validate_version
    base.runner._validate_manifest = validate_manifest
    base.runner.describe = describe
    base.describe = describe
    base.cross_direction = direction
    base.cross_report = report
    return base


def run(direction: Direction, argv: Sequence[str] | None = None) -> int:
    """Run one exact direction; no flash, relay, reset, retry, or autochain."""
    configured = configure(direction)
    return configured.main(argv)
