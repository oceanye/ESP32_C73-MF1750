#!/usr/bin/env python3
"""Fail-closed one-action runner for the D1-512 single-pixel cube.

The runner owns no power, relay, serial, flashing, reset, refresh-retry, or
recovery control.  Every invocation may consume at most one fixed firmware
action through one ARM followed by one EXECUTE request.  The checked-in
identity below is bound to the isolated offline build and is not live
authorization.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


# Load a private copy: configuring this campaign must not mutate the generic
# runner module when both are imported by the same test or audit process.
_BASE_RUNNER_PATH = Path(__file__).with_name(
    "mf1750_ec5_otp_transition_matrix_recheck_once.py"
)
_BASE_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_ec5_single_pixel_cube_runner_base", _BASE_RUNNER_PATH
)
if _BASE_RUNNER_SPEC is None or _BASE_RUNNER_SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_RUNNER_PATH}")
runner = importlib.util.module_from_spec(_BASE_RUNNER_SPEC)
_BASE_RUNNER_SPEC.loader.exec_module(runner)


runner.__doc__ = (
    "Fail-closed one-action runner for the D1-512 single-pixel cube. "
    "It never controls power or firmware installation and never retries, "
    "recovers, or chains a visible action."
)
runner.BUILD_TAG = "MF1750_EC5_SINGLE_PIXEL_CUBE_V1_2026-08-21"
runner.TEST_ID = "EC5-SINGLE-PIXEL-CUBE-V1"
runner.CAMPAIGN_ID = "EC5_SINGLE_PIXEL_CUBE_V1"
runner.DEVICE_API_VERSION = "MF1750_EC5_SINGLE_PIXEL_CUBE_DEVICE_V1"
runner.IDENTITY_REVISION = "single-pixel-cube-v1"
runner.CONTRACT_ID = (
    "ddbf5b9b108de76cd02a82d21a3551036c1cb71d4ff45d0b8ee5eb2337c32d2a"
)
runner.CLASSIFICATION = (
    "FACTORY_OTP_FULL_SCREEN_8_CUBED_SINGLE_PIXEL_HISTORY_NO_DITHER"
)
runner.DEVICE_KIND_PREFIX = "mf1750-ec5-single-pixel-cube"
runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-single-pixel-cube"
runner.NVS_NAMESPACE = "mf1750_spc1"
runner.NVS_KEY = "cursor_v1"

# Exact output of the isolated PlatformIO build.  The binding gate still
# fails closed if either value is absent or malformed; this identity does not
# install firmware or authorize a visible action.
runner.FIRMWARE_SHA256 = (
    "ffa6e082c3763dc22207a2565b1b47f81014d5fd93b8c5cd1a60636ea362b59b"
)
runner.FIRMWARE_BYTES = 789456

runner.ENDPOINTS = {
    name: f"/api/ec5/single-pixel-cube/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
runner.ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_SINGLE_PIXEL_CUBE_ACTION"
runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_FACTORY_OTP_SINGLE_PIXEL_CUBE_ACTION_ONCE"
)

runner.DESCRIPTOR_IDS = (
    "032ca22f88ab82e8c6088750194b2539779f0ced441ae0ef4fdcb16a7cc91623",
    "a32a48b92524a4efa92a992c285816d45964061c8be627737e39c483661f5c6b",
    "0a031f82f6ce05f7c0e697146cea296e77e6a0f7258a0f492f7ff8f18f537fc8",
    "de6644ce43368a6e1726ec31cf0bf68b189596092a4bbe90b6e5d4b56fe57b2f",
    "ce8e2decf94bc71d715115a23d7b907d19550963d7e7c63ed50aecac53116091",
)
runner.ACTION_IDS = (
    "61f446dddce6754274ed350ff2932fba424919e386cdc1ce7d52689015fa3742",
    "a219d8c626ffb6bf04774b65be366165831c71eca66410d905286b5e8133c077",
    "ce498fb534cddbe4ff8e30d5730d7ff05dc4ddf4f36e909052e73692bf3eb99c",
    "ed5264575256d0270f83dd90e493ed7b67387a934aade778fdd2cccd877ccf31",
    "414fc723670328c798867505c06c0247fc810d13a85d39bb8e171e7238f2d435",
)

_WHITE_FRAME = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
_WHITE_DTM = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
_CUBE_HISTOGRAM = [58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080]

runner.ACTIONS = (
    {
        "ordinal": 1,
        "descriptor_id": runner.DESCRIPTOR_IDS[0],
        "action_id": runner.ACTION_IDS[0],
        "prior_static_action_id": None,
        "role": "SINGLE_PIXEL_CUBE_WHITE_BASELINE",
        "round": 1,
        "branch": "FACTORY_OTP_WHITE_BASELINE",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": [0, 614400, 0, 0, 0, 0, 0, 0],
    },
    {
        "ordinal": 2,
        "descriptor_id": runner.DESCRIPTOR_IDS[1],
        "action_id": runner.ACTION_IDS[1],
        "prior_static_action_id": runner.ACTION_IDS[0],
        "role": "SINGLE_PIXEL_CUBE_SOURCE",
        "round": 1,
        "branch": "ALL_8_CUBED_SOURCE_CODES_UNIFORM_ROI",
        "frame_sha256": (
            "f472140380c1ab2630bc888d9ab0cb5e7d1f55c66f2be43b1ca89be3749927f6"
        ),
        "cs1_dtm_sha256": (
            "eda5cc0e7bc4a947b5186f13ce6bebced9e0e3ac0b5b49c5c27cf70c44a407d4"
        ),
        "cs2_dtm_sha256": (
            "eda5cc0e7bc4a947b5186f13ce6bebced9e0e3ac0b5b49c5c27cf70c44a407d4"
        ),
        "transport_code_histogram": list(_CUBE_HISTOGRAM),
    },
    {
        "ordinal": 3,
        "descriptor_id": runner.DESCRIPTOR_IDS[2],
        "action_id": runner.ACTION_IDS[2],
        "prior_static_action_id": runner.ACTION_IDS[1],
        "role": "SINGLE_PIXEL_CUBE_MID",
        "round": 1,
        "branch": "ALL_8_CUBED_MID_CODES_UNIFORM_ROI",
        "frame_sha256": (
            "0387640a8bf2ec344199b3602580aafa29a67f5c3e830fc9101251280e8fd28a"
        ),
        "cs1_dtm_sha256": (
            "21c6eced681bc5b6068aadfd7a3fb77cc58ebcb65b161f7d8bcc61f33003c8da"
        ),
        "cs2_dtm_sha256": (
            "21c6eced681bc5b6068aadfd7a3fb77cc58ebcb65b161f7d8bcc61f33003c8da"
        ),
        "transport_code_histogram": list(_CUBE_HISTOGRAM),
    },
    {
        "ordinal": 4,
        "descriptor_id": runner.DESCRIPTOR_IDS[3],
        "action_id": runner.ACTION_IDS[3],
        "prior_static_action_id": runner.ACTION_IDS[2],
        "role": "SINGLE_PIXEL_CUBE_TARGET",
        "round": 1,
        "branch": "ALL_8_CUBED_TARGET_CODES_UNIFORM_ROI",
        "frame_sha256": (
            "f5a8a0add6fb9f955b14165ae529176512d01c99c4607d8ea2a242b56c0b0254"
        ),
        "cs1_dtm_sha256": (
            "0ac4db5cd20921c99cf87b0cbcc526a067af716d8ef805f8583d5f80d027085d"
        ),
        "cs2_dtm_sha256": (
            "5ecd431192b23f7f3d74a03b72fc436a01906db24b74c486b17091602a7136c5"
        ),
        "transport_code_histogram": list(_CUBE_HISTOGRAM),
    },
    {
        "ordinal": 5,
        "descriptor_id": runner.DESCRIPTOR_IDS[4],
        "action_id": runner.ACTION_IDS[4],
        "prior_static_action_id": runner.ACTION_IDS[3],
        "role": "SINGLE_PIXEL_CUBE_WHITE_RECOVERY",
        "round": 1,
        "branch": "FACTORY_OTP_WHITE_RECOVERY",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": [0, 614400, 0, 0, 0, 0, 0, 0],
    },
)

runner.DEFAULT_CLAIMS = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_single_pixel_cube_claims"
)
runner.DEFAULT_OUTPUT = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_SINGLE_PIXEL_CUBE_20260821_V1"
)

_BASE_DESCRIBE = runner.describe
_BASE_DIAGNOSE_J2_OFF = runner.diagnose_j2_off
_BASE_RUN_ONCE = runner.run_once
_BASE_VALIDATE_VERSION = runner._validate_version
_BASE_VALIDATE_MANIFEST = runner._validate_manifest
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_VERSION_FLAGS = (
    "partial_refresh",
    "window_refresh",
    "command_0x86",
    "mid_refresh_power_cut",
    "spi_frequency_sweep",
)


def firmware_is_bound() -> bool:
    """Return whether an exact, non-placeholder firmware identity is present."""

    return (
        isinstance(runner.FIRMWARE_SHA256, str)
        and _SHA256.fullmatch(runner.FIRMWARE_SHA256) is not None
        and isinstance(runner.FIRMWARE_BYTES, int)
        and runner.FIRMWARE_BYTES > 0
    )


def _require_firmware_binding() -> None:
    if not firmware_is_bound():
        raise runner.RecheckError(
            "single-pixel-cube runner is offline-only until firmware SHA-256 "
            "and byte count are bound"
        )


def _validate_version(value: Mapping[str, Any]) -> None:
    _BASE_VALIDATE_VERSION(value)
    if any(value.get(key) is not False for key in _FORBIDDEN_VERSION_FLAGS):
        raise runner.RecheckError("device version forbidden-operation contract differs")
    if value.get("full_screen_global_refresh") is not True:
        raise runner.RecheckError("device version full-screen refresh contract differs")


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _BASE_VALIDATE_MANIFEST(value)
    if any(value.get(key) is not False for key in _FORBIDDEN_VERSION_FLAGS):
        raise runner.RecheckError("device manifest forbidden-operation contract differs")
    if value.get("full_screen_global_refresh") is not True:
        raise runner.RecheckError("device manifest full-screen refresh contract differs")


def describe() -> dict[str, Any]:
    value = _BASE_DESCRIBE()
    value["firmware"] = {
        "bound": firmware_is_bound(),
        "bytes": runner.FIRMWARE_BYTES,
        "sha256": runner.FIRMWARE_SHA256,
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "full_screen_global_refresh": True,
    }
    value["forbidden_operations"] = {
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x86": True,
        "mid_refresh_power_cut": True,
        "runtime_lut_write": True,
        "spi_frequency_sweep": True,
    }
    value["single_pixel_history"] = {
        "codes": 8,
        "unique_source_mid_target_recipes": 512,
        "uniform_transport_code_per_roi": True,
        "spatial_mixing": False,
        "visible_actions": 5,
    }
    return value


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    requester: runner.Requester = runner._http_request,
) -> dict[str, Any]:
    _require_firmware_binding()
    return _BASE_DIAGNOSE_J2_OFF(base_url, output=output, requester=requester)


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: runner.Requester = runner._http_request,
    poll_seconds: float = 2.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    _require_firmware_binding()
    return _BASE_RUN_ONCE(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


# The reused command parser and preflight call these module globals.  Rebind
# them so CLI use receives the same binding gate and stricter campaign checks.
runner._validate_version = _validate_version
runner._validate_manifest = _validate_manifest
runner.describe = describe
runner.diagnose_j2_off = diagnose_j2_off
runner.run_once = run_once


def main(argv: Sequence[str] | None = None) -> int:
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
