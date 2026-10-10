#!/usr/bin/env python3
"""Fail-closed one-action runner for the red/pink P1 recipe permutation.

The host never flashes, resets, controls J2/power, retries, recovers, or
autochains.  Each invocation can consume exactly one of four immutable
ordinals.  Device access is refused unless the reviewed BIN and ELF identities
match the local clean build.  The required clean factory-OTP white baseline is
an external precondition and is never silently created by this campaign.
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

from tools import mf1750_runtime_lut_recipe_position_permutation_v1_pack as pack  # noqa: E402


_V3_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_recipe_position_permutation_v1_private_v3_host", _V3_PATH
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

DEVICE_API_VERSION = "MF1750_EC5_REDPINK_RECIPE_POSITION_PERMUTATION_DEVICE_V1"
IDENTITY_REVISION = (
    "runtime-lut-redpink-recipe-position-permutation-p1-single-app-boot-flash-verify-v1"
)
CLASSIFICATION = (
    "EXPERIMENTAL_REDPINK_RECIPE_POSITION_PERMUTATION_NOT_QUALIFIED_COLOURS"
)
KIND_PREFIX = "mf1750-ec5-redpink-recipe-position-permutation-v1"

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = KIND_PREFIX
base.runner.EVIDENCE_KIND_PREFIX = KIND_PREFIX
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY

FIRMWARE_SHA256 = "2a671646d73ee32d3c19184b4d3d2a02d8ab6b374fd11445d88baa66c05a9f65"
FIRMWARE_BYTES = 800_704
ELF_SHA256 = "8fe3017fba40875cb059b0a8b1be3dc4b925fb7a93180f48a4f7374d27adb70f"
ELF_BYTES = 13_296_988
BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-recipe-position-permutation-v1"
    / "ec5_runtime_lut_recipe_position_permutation_v1"
)
base.runner.FIRMWARE_SHA256 = FIRMWARE_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BYTES
base.runner.ENDPOINTS = {
    name: f"/api/ec5/redpink-recipe-permutation-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_REDPINK_RECIPE_POSITION_PERMUTATION_ACTION"
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_REDPINK_RECIPE_POSITION_PERMUTATION_ACTION_ONCE"
)


def _actions() -> tuple[dict[str, Any], ...]:
    actions = deepcopy(base._actions())
    if len(actions) != 4:
        raise base.runner.RecheckError("recipe-permutation action count differs")
    for action, source in zip(actions, REPORT["actions"], strict=True):
        factory_otp = source["palette_source"] == "FACTORY_OTP"
        action["palette_source"] = source["palette_source"]
        action["global_header"] = source["global_header"]
        action["boot_admission"] = deepcopy(source["boot_admission"])
        action["driver_entry"] = (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if factory_otp
            else "epdDisplayCompiledChromaGrid"
        )
    return tuple(actions)


base.runner.ACTIONS = _actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_redpink_recipe_position_permutation_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_REDPINK_RECIPE_POSITION_PERMUTATION_20260828_V1"
)

DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUT_NAMES = {
    1: "action-01-permuted-source-shift3.json",
    2: "action-02-permuted-middle-reverse.json",
    3: "action-03-permuted-target-code0.json",
    4: "action-04-factory-otp-white-recovery.json",
}
ACTION_OUTPUTS = {
    ordinal: base.runner.DEFAULT_OUTPUT / name
    for ordinal, name in ACTION_OUTPUT_NAMES.items()
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NONE_STAGE = "none"


def _firmware_binding() -> dict[str, Any]:
    return {
        "bound": (
            _SHA256_RE.fullmatch(FIRMWARE_SHA256) is not None
            and FIRMWARE_BYTES > 0
            and _SHA256_RE.fullmatch(ELF_SHA256) is not None
            and ELF_BYTES > 0
        ),
        "bin": {
            "path": BUILD_DIR.joinpath("firmware.bin")
            .relative_to(REPO_ROOT)
            .as_posix(),
            "bytes": FIRMWARE_BYTES,
            "sha256": FIRMWARE_SHA256,
        },
        "elf": {
            "path": BUILD_DIR.joinpath("firmware.elf")
            .relative_to(REPO_ROOT)
            .as_posix(),
            "bytes": ELF_BYTES,
            "sha256": ELF_SHA256,
        },
    }


def _verify_local_artifacts() -> None:
    if not _firmware_binding()["bound"]:
        raise base.runner.RecheckError(
            "recipe-permutation firmware binding is malformed"
        )
    for name, byte_count, sha256 in (
        ("firmware.bin", FIRMWARE_BYTES, FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        artifact = BUILD_DIR / name
        if not artifact.is_file():
            raise base.runner.RecheckError(f"reviewed artifact is missing: {artifact}")
        data = artifact.read_bytes()
        if len(data) != byte_count or hashlib.sha256(data).hexdigest() != sha256:
            raise base.runner.RecheckError(
                f"reviewed recipe-permutation artifact identity differs: {artifact}"
            )


def _repo_relative(path: Path) -> str:
    return Path(path).resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def _fixed_path(value: Path | None, expected: Path, *, label: str) -> Path:
    candidate = expected if value is None else Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if candidate.resolve() != expected.resolve():
        raise base.runner.RecheckError(
            f"{label} is fixed at {_repo_relative(expected)}"
        )
    return expected.resolve()


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "recipe_position_permutation",
        "recipe_linked_candidates_only",
        "human_observation_gate_after_every_action",
        "busy_qualified_arm_execute_dispatch",
        "external_factory_white_precondition_required",
        "one_visible_refresh_per_ordinal",
        "runtime_lut_write",
    )
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
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
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError(
            "recipe-permutation required capability contract differs"
        )
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "recipe-permutation forbidden capability contract differs"
        )


def _expected_nvs_contract() -> dict[str, Any]:
    return {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 5,
        "campaign_boot_key": pack.NVS_BOOT_KEY,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }


def _expected_baseline_contract() -> dict[str, Any]:
    return {
        "ordinal": None,
        "role": "VERIFIED_EXTERNAL_FACTORY_OTP_CLEAN_WHITE_PRECONDITION",
        "external_anchor_required": True,
        "one_visible_refresh_required": False,
        "host_preflight_must_verify_clean_white": True,
    }


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 4
        or value.get("nvs_contract") != _expected_nvs_contract()
        or value.get("baseline_contract") != _expected_baseline_contract()
    ):
        raise base.runner.RecheckError("recipe-permutation version contract differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if value.get("actions") != list(base.runner.ACTIONS):
        raise base.runner.RecheckError("recipe-permutation action manifest differs")
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "action_count": 4,
        "round_count": 1,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "synchronous_both_controllers": True,
        "one_driver_call_per_action": True,
        "automatic_chaining": False,
        "startup_refresh": False,
        "runtime_lut_write": True,
        "nvs_contract": _expected_nvs_contract(),
        "baseline_contract": _expected_baseline_contract(),
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"recipe-permutation manifest {key} differs")
    layout = value.get("history_layout")
    if not isinstance(layout, Mapping):
        raise base.runner.RecheckError("recipe-permutation layout is absent")
    expected_layout = {
        "permutation_id": "P1_SOURCE_SHIFT3_MIDDLE_REVERSE",
        "source_physical_to_code": "(column+3)%8",
        "middle_physical_to_code": "7-row",
        "fixed_target": "active_code_0",
        "candidate_cells_total_observations": 128,
        "unique_recipes": 64,
        "mixed_controller_r20_intentionally_preserved": True,
        "controller_color_equivalence_claimed": False,
        "external_factory_white_precondition_required": True,
        "factory_otp_white_ordinal": 4,
        "one_visible_refresh_per_ordinal": True,
        "active_global_header_sha256": cross_hash("active", "global_header_sha256"),
        "commented_global_header_sha256": cross_hash(
            "commented", "global_header_sha256"
        ),
        "cs1_r20_prefix_sha256": cross_hash("active", "cs1_r20_prefix_sha256"),
        "cs2_r20_prefix_sha256": cross_hash("active", "cs2_r20_prefix_sha256"),
        "r21_sha256": cross_hash("active", "r21_sha256"),
    }
    for key, wanted in expected_layout.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"recipe-permutation layout {key} differs")
    _validate_capabilities(value)


def cross_hash(profile: str, key: str) -> Any:
    return REPORT["contract"]["profiles"][profile][key]


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 4:
        raise base.runner.RecheckError("recipe-permutation runnable ordinal differs")
    if expected_busy != 1 or value.get("busy") != 1:
        raise base.runner.RecheckError(
            "recipe-permutation every ordinal requires raw ready BUSY=1"
        )
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=1
    )
    expected_count = ordinal - 1
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(
                f"recipe-permutation ready status {key} differs"
            )
    return nonce


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if not 1 <= ordinal <= 4:
        raise base.runner.RecheckError("recipe-permutation COMPLETE ordinal differs")
    action = base.runner.ACTIONS[ordinal - 1]
    source = REPORT["actions"][ordinal - 1]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 4,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"recipe-permutation COMPLETE {key} differs")
    driver = value.get("driver")
    if not isinstance(driver, Mapping):
        raise base.runner.RecheckError("recipe-permutation COMPLETE driver absent")
    driver_exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": _NONE_STAGE,
        "timeout_stage": _NONE_STAGE,
        "busy_missing_stage": _NONE_STAGE,
        "pre_command_busy_stage": _NONE_STAGE,
        "spi_hz": 1_000_000,
        "operation_id": ordinal,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "input_fnv1a": source["frame"]["fnv1a"],
        "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
        "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
    }
    for key, wanted in driver_exact.items():
        if driver.get(key) != wanted:
            raise base.runner.RecheckError(
                f"recipe-permutation COMPLETE driver {key} differs"
            )
    for key in ("pon_ms", "drf_ms", "pof_ms"):
        if not _positive_int(driver.get(key)):
            raise base.runner.RecheckError(
                f"recipe-permutation COMPLETE driver {key} is not positive"
            )

    safe_finish = driver.get("safe_finish")
    if not isinstance(safe_finish, Mapping) or any(
        safe_finish.get(key) != 1
        for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms")
    ):
        raise base.runner.RecheckError(
            "recipe-permutation COMPLETE safe-finish BUSY differs"
        )
    final_gpio = safe_finish.get("final_gpio")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != wanted
        for key, wanted in {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}.items()
    ):
        raise base.runner.RecheckError(
            "recipe-permutation COMPLETE final safe-finish GPIO differs"
        )


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError(
            "recipe-permutation prior terminal ordinal differs"
        )
    _validate_complete_report(value, ordinal - 1, boot_nonce)


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


def _write_staged_result(output: Path, staged: Path) -> None:
    value = json.loads(staged.read_text(encoding="utf-8"))
    ordinal = value.get("ordinal")
    if isinstance(ordinal, int) and not isinstance(ordinal, bool) and 1 <= ordinal <= 4:
        value["recipe_position_permutation_binding"] = {
            "layout_id": pack.VARIANT_KEY,
            "source_column_shift_mod8": pack.SOURCE_COLUMN_SHIFT,
            "middle_physical_row_to_code": pack.MIDDLE_ROW_TRANSFORM,
            "frame": REPORT["actions"][ordinal - 1]["frame"],
            "runtime_payload": {
                key: REPORT["actions"][ordinal - 1].get(key)
                for key in (
                    "global_header",
                    "global_header_sha256",
                    "cs1_r20_prefix_bytes",
                    "cs1_r20_prefix_sha256",
                    "cs2_r20_prefix_bytes",
                    "cs2_r20_prefix_sha256",
                    "r21_bytes",
                    "r21_sha256",
                )
            },
            "recipe_map": REPORT["contract"]["recipe_map"],
            "observation_map": REPORT["contract"]["observation_map"],
            "physical_to_recipe_map": REPORT["contract"]["physical_to_recipe_map"],
            "analysis_input_contract": REPORT["analysis_input_contract"],
        }
    value.pop("integrity", None)
    sealed = base.runner._seal(value)  # noqa: SLF001
    base.runner._write_new(output, sealed)  # noqa: SLF001
    staged.unlink()


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    external_clean_white_confirmed: bool = False,
) -> dict[str, Any]:
    """Consume exactly one action after all local and live gates pass."""

    _verify_local_artifacts()
    if ordinal not in ACTION_OUTPUTS:
        raise base.runner.RecheckError("run ordinal must be in 1..4")
    if ordinal == 1 and external_clean_white_confirmed is not True:
        raise base.runner.RecheckError(
            "ordinal 1 requires explicit verified external factory-OTP clean white"
        )
    if poll_seconds < base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS:
        raise base.runner.RecheckError("run requires poll_seconds >= 65")
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise base.runner.RecheckError("run requires poll_count >= 1")
    claims = _fixed_path(claims, base.runner.DEFAULT_CLAIMS, label="claims root")
    output = _fixed_path(output, ACTION_OUTPUTS[ordinal], label="action output")
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    staged = output.with_name(f".{output.name}.terminal-staging")
    if staged.exists():
        raise base.runner.RecheckError(f"refusing stale staging file {staged}")
    try:
        result = v1.run_once(
            base_url,
            ordinal,
            claims=claims,
            output=staged,
            requester=requester,
            poll_seconds=poll_seconds,
            poll_count=poll_count,
        )
    except base.runner.RecheckError:
        if staged.is_file():
            _write_staged_result(output, staged)
        raise
    try:
        _validate_complete_report(
            result["terminal_report"], ordinal, result["boot_nonce"]
        )
    except base.runner.RecheckError as error:
        claim_file = Path(result["claim_file"])
        claim = json.loads(claim_file.read_text(encoding="utf-8"))
        v1._write_consumed_failure_evidence(  # noqa: SLF001
            output=output,
            action=base.runner.ACTIONS[ordinal - 1],
            claim_file=claim_file,
            claim=claim,
            boot_nonce=result["boot_nonce"],
            transcript=result["transcript"],
            outcome="terminal_complete_rejected",
            error=str(error),
            terminal_report=result["terminal_report"],
        )
        staged.unlink()
        raise base.runner.RecheckError(
            "terminal COMPLETE rejected; raw evidence saved; action must not retry"
        ) from error
    _write_staged_result(output, staged)
    return result


def diagnose_j2_off(
    base_url: str, *, output: Path, requester: Any = None
) -> dict[str, Any]:
    _verify_local_artifacts()
    output = _fixed_path(output, DIAGNOSTIC_OUTPUT, label="diagnostic output")
    return base.runner.diagnose_j2_off(base_url, output=output, requester=requester)


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
) -> dict[str, Any]:
    _verify_local_artifacts()
    if ordinal not in ACTION_OUTPUTS:
        raise base.runner.RecheckError("salvage ordinal must be in 1..4")
    claims = _fixed_path(claims, base.runner.DEFAULT_CLAIMS, label="claims root")
    output = _fixed_path(output, ACTION_OUTPUTS[ordinal], label="action output")
    return v1.salvage_fault_once(
        base_url, ordinal, claims=claims, output=output, requester=requester
    )


def dry_validate() -> dict[str, Any]:
    _verify_local_artifacts()
    contract = REPORT["contract"]
    if (
        len(contract["recipe_map"]) != 64
        or len(contract["observation_map"]) != 128
        or len(contract["physical_to_recipe_map"]) != 128
        or len({item["recipe_id"] for item in contract["recipe_map"]}) != 64
        or len({item["observation_id"] for item in contract["observation_map"]}) != 128
    ):
        raise base.runner.RecheckError("recipe-permutation mapping cardinality differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-redpink-recipe-position-permutation-v1-dry-validation",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": REPORT["contract_id"],
        "firmware_binding": _firmware_binding(),
        "action_ids": list(base.runner.ACTION_IDS),
        "recipe_count": 64,
        "observation_count": 128,
        "physical_mapping_count": 128,
        "source_column_shift_mod8": pack.SOURCE_COLUMN_SHIFT,
        "middle_physical_row_to_code": pack.MIDDLE_ROW_TRANSFORM,
        "analysis_input_contract": REPORT["analysis_input_contract"],
        "claims_root": _repo_relative(base.runner.DEFAULT_CLAIMS),
        "diagnostic_output": _repo_relative(DIAGNOSTIC_OUTPUT),
        "action_outputs": {
            str(ordinal): _repo_relative(path)
            for ordinal, path in ACTION_OUTPUTS.items()
        },
    }


def describe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-redpink-recipe-position-permutation-v1-description",
        "variant": deepcopy(REPORT["contract"]),
        "firmware_binding": _firmware_binding(),
        "fixed_routes": deepcopy(base.runner.ENDPOINTS),
        "fixed_claims_root": _repo_relative(base.runner.DEFAULT_CLAIMS),
        "fixed_outputs": {
            "diagnostic": _repo_relative(DIAGNOSTIC_OUTPUT),
            "actions": {
                str(ordinal): _repo_relative(path)
                for ordinal, path in ACTION_OUTPUTS.items()
            },
        },
        "preflight": {
            "clean_factory_otp_white_external_precondition": True,
            "ordinal1_explicit_external_clean_white_confirmation_required": True,
            "raw_ready_busy": 1,
            "same_boot_prior_complete_required": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "analysis_input_contract": REPORT["analysis_input_contract"],
    }


# Rebind all dynamic validation points in the private runner facade.
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
    sub.add_parser("dry-validate")
    diagnostic = sub.add_parser("diagnose-j2-off")
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, default=DIAGNOSTIC_OUTPUT)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 5), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--confirm-external-clean-white", action="store_true")
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, choices=range(1, 5), required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(args.base_url, output=args.output)
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output or ACTION_OUTPUTS[args.ordinal],
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output or ACTION_OUTPUTS[args.ordinal],
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                external_clean_white_confirmed=args.confirm_external_clean_white,
            )
    except (base.runner.RecheckError, KeyError) as error:
        print(f"recipe-permutation V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
