#!/usr/bin/env python3
"""One-action fail-closed runner for the L535 cumulative full-frame fallback."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cumulative_v1_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name("mf1750_runtime_lut_partial_hold_once.py")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_cumulative_v1_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

_BASE_VALIDATE_READY_STATUS = base.runner._validate_ready_status  # noqa: SLF001
_BASE_PREFLIGHT = base.runner._preflight  # noqa: SLF001

REPORT = pack.build_report()
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 55.0
base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_CUMULATIVE_DEVICE_V1"
base.runner.IDENTITY_REVISION = "runtime-lut-cumulative-v1"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = "EXPERIMENTAL_L535_CUMULATIVE_FULL_FRAME_REDRAW_CONTROL"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = "cursor_v1"
base.runner.ARM_INTENT = "ARM_ONE_FIXED_L535_RUNTIME_LUT_CUMULATIVE_ACTION"
base.runner.EXECUTE_INTENT = "EXECUTE_ARMED_L535_RUNTIME_LUT_CUMULATIVE_ACTION_ONCE"
base.runner.FIRMWARE_SHA256 = (
    "fdb9852a4414f7a50e09dd6088debc95a92fecf067562504ccdadbac34841068"
)
base.runner.FIRMWARE_BYTES = 793264
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_cumulative_l535_active_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_CUMULATIVE_L535_ACTIVE_20260823_V1"
)


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = ("full_screen_global_refresh", "full_frame_cumulative_redraw")
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("cumulative redraw capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "cumulative redraw forbidden-operation contract differs"
        )


def _validate_version(value: Mapping[str, Any]) -> None:
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
        raise base.runner.RecheckError("device cumulative safety contract differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != base.runner.NVS_NAMESPACE
        or nvs.get("key") != base.runner.NVS_KEY
    ):
        raise base.runner.RecheckError("device NVS isolation differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
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
    if (
        layout.get("runtime_lut_profile_id") != pack.PROFILE_ID
        or layout.get("ptlw_command_issued") is not False
        or layout.get("cropped_dtm") is not False
        or layout.get("all_action_dtm_transport") != "packed_frame_per_controller"
        or layout.get("full_frame_cumulative_redraw") is not True
        or layout.get("white_transport_code") != pack.WHITE_CODE
    ):
        raise base.runner.RecheckError("device cumulative transport layout differs")
    profile = REPORT["contract"]["profile"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != profile[key]:
            raise base.runner.RecheckError(f"device LUT profile {key} differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    """Accept V5's post-POF late BUSY-low state without weakening GPIO gates.

    Every cumulative action ends in ``epdPostDisplayPowerCut()``: the terminal
    driver report samples BUSY idle-HIGH before/after holding all panel-facing
    outputs LOW, while a later status read can observe BUSY LOW with RST still
    asserted.  The next action resets the controllers before its first BUSY
    idle gate.  Only later ordinals may use this alternative; the matching
    prior terminal safe-finish report is checked by ``_preflight`` below.
    """

    observed_busy = value.get("busy")
    accepted_busy = expected_busy
    if expected_busy == 1 and ordinal > 1 and observed_busy == 0:
        accepted_busy = 0
    return _BASE_VALIDATE_READY_STATUS(value, ordinal, expected_busy=accepted_busy)


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    prior = base.runner.ACTIONS[ordinal - 2]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "ordinal": ordinal - 1,
        "action_id": prior["action_id"],
        "next_ordinal": ordinal,
        "campaign_complete": False,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device prior report {key} differs")

    driver = value.get("driver")
    safe_finish = driver.get("safe_finish") if isinstance(driver, Mapping) else None
    final_gpio = (
        safe_finish.get("final_gpio") if isinstance(safe_finish, Mapping) else None
    )
    if not isinstance(driver, Mapping) or any(
        driver.get(key) != wanted
        for key, wanted in {
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "spi_hz": 1_000_000,
        }.items()
    ):
        raise base.runner.RecheckError("device prior terminal driver differs")
    if not isinstance(safe_finish, Mapping) or any(
        safe_finish.get(key) != 1
        for key in (
            "busy_before_pins_low",
            "busy_after_pins_low",
            "busy_after_5ms",
        )
    ):
        raise base.runner.RecheckError("device prior safe-finish BUSY differs")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != wanted
        for key, wanted in {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}.items()
    ):
        raise base.runner.RecheckError("device prior safe-finish GPIO differs")


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = _BASE_PREFLIGHT(
        base_url,
        ordinal,
        expected_busy=expected_busy,
        requester=requester,
    )
    if expected_busy == 1 and ordinal > 1:
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight


def describe() -> dict[str, Any]:
    value = base._BASE_DESCRIBE()
    value["variant"] = REPORT["contract"]
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_id": pack.PROFILE_ID,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "packed_full_frame_per_controller": True,
        "full_frame_cumulative_redraw": True,
        "blocking_refresh_first_poll_floor_seconds": (
            base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS
        ),
    }
    value["forbidden_operations"] = {
        "partial_window": True,
        "command_0x83": True,
        "command_0x86": True,
        "cross_palette_switch": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    return value


base.runner.describe = describe
base.describe = describe


def main(argv: Sequence[str] | None = None) -> int:
    if base.runner.FIRMWARE_SHA256 is None or base.runner.FIRMWARE_BYTES is None:
        raise SystemExit("cumulative runner is not bound to a built firmware")
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
