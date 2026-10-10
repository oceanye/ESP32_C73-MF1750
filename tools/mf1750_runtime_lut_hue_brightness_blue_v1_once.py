#!/usr/bin/env python3
"""Fail-closed one-action runner for the blue hue brightness candidates.

This runner never flashes, resets, controls J2/power, retries, recovers, or
autochains.  It verifies the reviewed local BIN/ELF before any device request,
requires raw BUSY=1 for every ordinal, and accepts only strict terminal BUSY
evidence.  A visual failure before ordinal 6 must use the independent fresh-
identity factory-OTP white containment firmware; campaign ordinals cannot be
skipped.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_hue_brightness_blue_v1_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_hue_brightness_blue_v1_private_v3_host", _V3_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load BUSY-qualified host mechanics: {_V3_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)
v1 = v3.v1
base = v3.base

REPORT = pack.build_report()
v3.pack = pack
v3.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_DEVICE_V1"
base.runner.IDENTITY_REVISION = "runtime-lut-target-hue-blue-brightness-v1"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_L535_BLUE_HUE_HISTORY_BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-target-hue-blue-brightness-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-target-hue-blue-brightness-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "afc978e1b9ed3ccd240302a8848c2bcc4f8727f68ec70c52b026934116a93d56"
FIRMWARE_BYTES = 795_376
ELF_SHA256 = "d1cddb1ce07aa427f24b188a43390117dcf806321b6fe4f5aed87520fc3ee8e7"
ELF_BYTES = 13_280_776
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-hue-brightness-blue-v1"
    / "ec5_runtime_lut_hue_brightness_blue_v1"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/target-hue-blue-brightness-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_BLUE_HUE_BRIGHTNESS_CANDIDATE_ACTION"
base.runner.EXECUTE_INTENT = "EXECUTE_ARMED_BLUE_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE"
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_target_hue_blue_brightness_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_TARGET_HUE_BLUE_BRIGHTNESS_20260824_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_WHITE_BASELINE_ROLE = "RUNTIME_LUT_WHITE_BASELINE"
_CONTAINMENT = REPORT["contract"]["strict_ordinal_progression"]["failure_containment"]


def _firmware_binding() -> dict[str, Any]:
    return {
        "bound": (
            _SHA256_RE.fullmatch(FIRMWARE_SHA256) is not None
            and FIRMWARE_BYTES > 0
            and _SHA256_RE.fullmatch(ELF_SHA256) is not None
            and ELF_BYTES > 0
        ),
        "bin": {"bytes": FIRMWARE_BYTES, "sha256": FIRMWARE_SHA256},
        "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
    }


def _verify_local_artifacts() -> None:
    if not _firmware_binding()["bound"]:
        raise base.runner.RecheckError(
            "blue brightness firmware binding is malformed; refusing device access"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(
                f"reviewed blue brightness artifact is missing: {artifact}"
            )
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed blue brightness artifact identity differs: {artifact}"
            )
    try:
        pack.containment.build_report(verify_artifacts=True)
    except ValueError as error:
        raise base.runner.RecheckError(
            "dedicated brightness white-containment artifact binding differs; "
            "refusing device access"
        ) from error


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "history_brightness_screening",
        "target_repeat_stability_probe",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("blue brightness capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "blue brightness forbidden capability contract differs"
        )


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError("blue brightness layout identity differs")
    if value.get("action_count") != 6 or value.get("runtime_lut_write") is not True:
        raise base.runner.RecheckError(
            "blue brightness action/runtime contract differs"
        )
    for key in (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(f"blue brightness safety {key} differs")
    if value.get("nvs_contract") != {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 7,
    }:
        raise base.runner.RecheckError("blue brightness NVS isolation differs")
    if value.get("baseline_contract") != {
        "ordinal": 1,
        "role": _RUNTIME_WHITE_BASELINE_ROLE,
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }:
        raise base.runner.RecheckError("blue brightness runtime-white baseline differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": list(base.runner.ACTIONS),
        "action_count": 6,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"blue brightness manifest {key} differs")
    layout = value.get("history_layout", {})
    expected_layout = {
        "candidate_cells_per_controller": 64,
        "candidate_cells_total_observations": 128,
        "unique_recipes": 64,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "cs2_position_mirrored": False,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "row_axis": "commented_middle_code_0_to_7",
        "column_axis": "active_source_code_0_to_7",
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_transport_code": pack.TARGET_CODE,
        "target_repeat_count": 2,
        "qualified_brightness_levels": 0,
        "brightness_candidates_only": True,
        "spatial_dither": False,
        "white_gutter_history_interaction_qualified": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "strict_same_boot_prior_complete_required": True,
        "skip_to_white_recovery_allowed": False,
        "failure_containment_firmware_sha256": _CONTAINMENT["firmware_sha256"],
        "failure_containment_contract_id": _CONTAINMENT["contract_id"],
        "failure_containment_nvs_namespace": _CONTAINMENT["nvs_namespace"],
        "failure_containment_campaign_nvs_dependency": False,
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(
                f"blue brightness history layout {key} differs"
            )
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != REPORT["contract"]["profiles"]["active"][key]:
            raise base.runner.RecheckError(f"blue brightness LUT {key} differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 6 or expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError(
            "blue brightness every ordinal requires raw ready BUSY=1"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=1
    )
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != ordinal - 1:
            raise base.runner.RecheckError(
                f"blue brightness ready status {key} differs"
            )
    return nonce


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("blue brightness prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001
    if ordinal == 2 and value.get("role") != _RUNTIME_WHITE_BASELINE_ROLE:
        raise base.runner.RecheckError(
            "blue brightness ordinal 2 requires runtime-code7 visual-white COMPLETE"
        )


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url,
        ordinal,
        expected_busy=expected_busy,
        requester=requester,
    )
    if ordinal == 1:
        v1._validate_fresh_no_execute_report(report, boot_nonce)  # noqa: SLF001
    else:
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    _verify_local_artifacts()
    return v3.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
) -> dict[str, Any]:
    _verify_local_artifacts()
    return v3.salvage_fault_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
    )


def describe() -> dict[str, Any]:
    value = deepcopy(v3.describe())
    value["variant"] = deepcopy(REPORT["contract"])
    value["firmware_binding"] = _firmware_binding()
    value["artifact_preflight_required_before_device_access"] = True
    value["preflight_busy_contract"] = {
        "ordinals_1_to_6": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_sequence": list(pack.GLOBAL_HEADERS),
        "packed_full_frame_per_controller": True,
        "ptlw_command_issued": False,
        "partial_refresh": False,
        "spatial_dither": False,
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_code": pack.TARGET_CODE,
        "candidate_recipes": 64,
        "physical_observations": 128,
        "qualified_brightness_levels": 0,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "skip_to_runtime_white_recovery": False,
        "ordinal_6_requires_ordinal_5_complete": True,
        "visual_fail_containment": deepcopy(_CONTAINMENT),
    }
    value["ordinal_progression"]["visual_fail_containment"][
        "artifact_binding_status"
    ] = pack.containment.artifact_binding_status()
    value["evidence_boundary"] = {
        "brightness_candidates_not_levels": True,
        "controller_repeats_not_additional_unique_colours": True,
        "controller_colour_equivalence_not_claimed": True,
        "white_gutters_not_measurement_regions": True,
        "local_hold_not_tested_or_claimed": True,
    }
    return value


# Rebind all dynamic points in the isolated host stack.
v3._validate_capabilities = _validate_capabilities
v3._validate_version = _validate_version
v3._validate_manifest = _validate_manifest
v3._validate_ready_status = _validate_ready_status
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._preflight = _preflight
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"blue brightness candidate V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
