#!/usr/bin/env python3
"""Fail-closed one-action runner for yellow/olive code2 brightness candidates.

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

from tools import mf1750_runtime_lut_hue_brightness_yellow_olive_v1_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_hue_brightness_yellow_olive_v1_private_v3_host", _V3_PATH
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
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_DEVICE_V1"
)
base.runner.IDENTITY_REVISION = (
    "runtime-lut-target-hue-yellow-olive-brightness-factory-white-v1"
)
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_L535_YELLOW_OLIVE_CODE2_HISTORY_"
    "BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-target-hue-yellow-olive-brightness-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-target-hue-yellow-olive-brightness-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "7e45f52dcafdea3c5f9962631a8c1b13bc0390131e3bebc0f5accecd8c5a8563"
FIRMWARE_BYTES = 802_208
ELF_SHA256 = "5a8fabd61f3230d640323873f29b055acb0eef5197769efded3ce114f0615ae5"
ELF_BYTES = 13_299_612
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-hue-brightness-yellow-olive-v1"
    / "ec5_runtime_lut_hue_brightness_yellow_olive_v1"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/target-hue-yellow-olive-brightness-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_YELLOW_OLIVE_CODE2_BRIGHTNESS_CANDIDATE_ACTION"
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_YELLOW_OLIVE_CODE2_BRIGHTNESS_CANDIDATE_ACTION_ONCE"
)


def _actions() -> tuple[dict[str, Any], ...]:
    """Mirror the six compiled actions including factory/runtime dispatch."""

    return tuple(
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "prior_static_action_id": item["prior_static_action_id"],
            "role": item["role"],
            "round": 1,
            "branch": item["branch"],
            "palette_source": item["palette_source"],
            "global_header": item["global_header"],
            "driver_entry": (
                "epdDisplayCompiledFactoryOtpWhiteRecovery"
                if item["palette_source"] == "FACTORY_OTP"
                else "epdDisplayCompiledChromaGrid"
            ),
            "frame_sha256": item["frame"]["sha256"],
            "cs1_dtm_sha256": item["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": item["cs2_dtm"]["sha256"],
            "transport_code_histogram": item["frame"]["histogram"],
        }
        for item in REPORT["actions"]
    )


base.runner.ACTIONS = _actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_target_hue_yellow_olive_brightness_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_20260826_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACTORY_WHITE_BASELINE_ROLE = "FACTORY_OTP_WHITE_HEALTH_ANCHOR"
_CONTAINMENT = REPORT["contract"]["strict_ordinal_progression"]["failure_containment"]
_BASE_IDENTITY = base.runner._identity  # noqa: SLF001
_BASE_VALIDATE_COMPLETE_REPORT = v3._validate_complete_report  # noqa: SLF001


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
            "yellow_olive brightness firmware binding is malformed; refusing device access"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(
                f"reviewed yellow_olive brightness artifact is missing: {artifact}"
            )
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed yellow_olive brightness artifact identity differs: {artifact}"
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
        "device_enforced_same_boot_nvs_binding",
        "negative_early_seal_after_ordinal4",
        "ordinal5_requires_visible_candidate_confirmation",
        "running_app_elf_sha256_reported",
        "human_observation_gate_after_target",
        "factory_otp_white_anchor_and_recovery",
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
        "unknown_commands",
        "runtime_code7_used_as_white",
        "local_hold_claimed",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError(
            "yellow_olive brightness capability contract differs"
        )
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "yellow_olive brightness forbidden capability contract differs"
        )


def _identity(value: Mapping[str, Any], *, kind_suffix: str) -> None:
    _BASE_IDENTITY(value, kind_suffix=kind_suffix)
    if value.get("running_app_elf_sha256") != ELF_SHA256:
        raise base.runner.RecheckError(
            f"device {kind_suffix} running_app_elf_sha256 differs"
        )


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if value.get("layout_id") != pack.VARIANT_KEY:
        raise base.runner.RecheckError(
            "yellow_olive brightness layout identity differs"
        )
    if value.get("action_count") != 6 or value.get("runtime_lut_write") is not True:
        raise base.runner.RecheckError(
            "yellow_olive brightness action/runtime contract differs"
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
            raise base.runner.RecheckError(
                f"yellow_olive brightness safety {key} differs"
            )
    if value.get("nvs_contract") != {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "boot_binding_key": pack.BOOT_BINDING_NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "boot_binding_encoding": "uint64 high32_low32 first_fresh_setup_boot_nonce",
        "boot_binding_initialize_only_when": (
            "cursor_key_absent_and_ready_ordinal1_before_network_routes"
        ),
        "boot_binding_gate_points": ["setup", "arm", "execute", "dispatch"],
        "boot_binding_reboot_policy": "fault_lock_before_epd_begin_or_any_panel_io",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_boot_binding_key_present": False,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 7,
    }:
        raise base.runner.RecheckError("yellow_olive brightness NVS isolation differs")
    if value.get("baseline_contract") != {
        "ordinal": 1,
        "role": _FACTORY_WHITE_BASELINE_ROLE,
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }:
        raise base.runner.RecheckError(
            "yellow/olive brightness factory-white baseline differs"
        )
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": list(base.runner.ACTIONS),
        "action_count": 6,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(
                f"yellow_olive brightness manifest {key} differs"
            )
    layout = value.get("history_layout", {})
    expected_layout = {
        "candidate_cells_per_controller": 64,
        "candidate_cells_total_observations": 128,
        "unique_recipes": 64,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "paired_controller_observations_not_colour_equivalent": True,
        "controller_payload_binding": "CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED",
        "cs2_position_mirrored": False,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "row_axis": "commented_middle_code_0_to_7",
        "column_axis": "active_source_code_0_to_7",
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_hue_catalog_id": pack.TARGET_HUE_CATALOG_ID,
        "target_transport_code": pack.TARGET_CODE,
        "target_repeat_count": 2,
        "qualified_brightness_levels": 0,
        "brightness_candidates_only": True,
        "spatial_dither": False,
        "white_gutter_history_interaction_qualified": False,
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "runtime_code7_used_as_white": False,
        "factory_otp_white_ordinals": [1, 6],
        "factory_otp_white_fill_byte": 17,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "palette_source_sequence": [
            "FACTORY_OTP",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "FACTORY_OTP",
        ],
        "strict_same_boot_prior_complete_required": True,
        "device_same_boot_binding": "uint64_first_fresh_setup_boot_nonce",
        "device_same_boot_binding_nvs_key": pack.BOOT_BINDING_NVS_KEY,
        "device_same_boot_gate_points": ["setup", "arm", "execute", "dispatch"],
        "reboot_fault_lock_before_epd_begin": True,
        "skip_to_factory_white_recovery_allowed": False,
        "ordinal4_no_difference_early_seal": ("skip_5_and_6_then_fresh_containment"),
        "ordinal5_requires_visible_candidate_confirmation": True,
        "failure_containment_firmware_bytes": _CONTAINMENT["firmware_bytes"],
        "failure_containment_kind": "independent_fresh_identity_factory_otp_white",
        "failure_containment_firmware_sha256": _CONTAINMENT["firmware_sha256"],
        "failure_containment_elf_bytes": _CONTAINMENT["elf_bytes"],
        "failure_containment_elf_sha256": _CONTAINMENT["elf_sha256"],
        "failure_containment_contract_id": _CONTAINMENT["contract_id"],
        "failure_containment_nvs_namespace": _CONTAINMENT["nvs_namespace"],
        "failure_containment_nvs_key": _CONTAINMENT["nvs_key"],
        "failure_containment_base_route": _CONTAINMENT["base_route"],
        "failure_containment_descriptor_id": _CONTAINMENT["descriptor_id"],
        "failure_containment_action_id": _CONTAINMENT["action_id"],
        "failure_containment_campaign_nvs_dependency": False,
        "main_campaign_resume_device_blocked_by_boot_binding": True,
        "main_campaign_resume_after_containment": False,
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(
                f"yellow_olive brightness history layout {key} differs"
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
            raise base.runner.RecheckError(f"yellow_olive brightness LUT {key} differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 6 or expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError(
            "yellow_olive brightness every ordinal requires raw ready BUSY=1"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=1
    )
    if (
        value.get("campaign_boot_binding_key_present") is not True
        or value.get("campaign_boot_binding_matches_current") is not True
    ):
        raise base.runner.RecheckError(
            "yellow_olive brightness device same-boot binding differs"
        )
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != ordinal - 1:
            raise base.runner.RecheckError(
                f"yellow_olive brightness ready status {key} differs"
            )
    return nonce


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    _BASE_VALIDATE_COMPLETE_REPORT(value, ordinal, boot_nonce)
    if (
        value.get("campaign_boot_binding_key_present") is not True
        or value.get("campaign_boot_binding_matches_current") is not True
    ):
        raise base.runner.RecheckError(
            "yellow_olive brightness COMPLETE same-boot binding differs"
        )


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("yellow_olive brightness prior ordinal differs")
    v3._validate_complete_report(value, ordinal - 1, boot_nonce)  # noqa: SLF001
    if ordinal == 2 and value.get("role") != _FACTORY_WHITE_BASELINE_ROLE:
        raise base.runner.RecheckError(
            "yellow/olive brightness ordinal 2 requires factory-OTP white COMPLETE"
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
        if (
            report.get("campaign_boot_binding_key_present") is not True
            or report.get("campaign_boot_binding_matches_current") is not True
        ):
            raise base.runner.RecheckError(
                "yellow_olive brightness fresh same-boot binding differs"
            )
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
    visible_candidate_confirmed: bool = False,
) -> dict[str, Any]:
    if ordinal == 5 and not visible_candidate_confirmed:
        raise base.runner.RecheckError(
            "ordinal 5 requires explicit visible candidate confirmation after ordinal 4"
        )
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
    value["device_enforced_same_boot"] = deepcopy(
        REPORT["contract"]["device_enforced_same_boot"]
    )
    value["running_elf_identity_boundary"] = {
        "device_source": "esp_ota_get_app_description.app_elf_sha256",
        "must_equal_reviewed_local_elf_sha256": ELF_SHA256,
        "host_local_elf_verified_before_device_access": True,
    }
    value["dependency_manifest_boundary"] = deepcopy(
        REPORT["contract"]["artifact_identity_boundary"]
    )
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "factory_otp_white_ordinals": [1, 6],
        "runtime_code7_used_as_white": False,
        "profile_sequence": list(pack.GLOBAL_HEADERS),
        "packed_full_frame_per_controller": True,
        "ptlw_command_issued": False,
        "partial_refresh": False,
        "spatial_dither": False,
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_hue_catalog_id": pack.TARGET_HUE_CATALOG_ID,
        "target_code": pack.TARGET_CODE,
        "candidate_recipes": 64,
        "physical_observations": 128,
        "qualified_brightness_levels": 0,
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["ordinal_progression"] = {
        "strict_same_boot_prior_complete_required": True,
        "skip_to_factory_white_recovery": False,
        "ordinal_6_requires_ordinal_5_complete": True,
        "ordinal_4_no_clear_difference": (
            "seal_main_skip_5_and_6_relay_off_then_fresh_containment"
        ),
        "ordinal_5_requires_explicit_visible_candidate_confirmation": True,
        "negative_early_seal_main_resume": False,
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
v3._validate_complete_report = _validate_complete_report
v3._validate_version = _validate_version
v3._validate_manifest = _validate_manifest
v3._validate_ready_status = _validate_ready_status
v3._validate_prior_terminal_report = _validate_prior_terminal_report
v3._preflight = _preflight
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._identity = _identity  # noqa: SLF001
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
    run.add_argument("--confirm-visible-candidate-after-ordinal4", action="store_true")
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
                visible_candidate_confirmed=(
                    args.confirm_visible_candidate_after_ordinal4
                ),
            )
    except base.runner.RecheckError as error:
        print(f"yellow_olive brightness candidate V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
