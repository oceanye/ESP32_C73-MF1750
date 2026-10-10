#!/usr/bin/env python3
"""Fail-closed one-action runner for true complete-R20 partial HOLD V1.

The host never flashes, resets, controls J2/power, retries, recovers, or
chains actions.  A live mutation is additionally impossible until a sealed
Batch-1 same-R20 parity evidence bundle is supplied and exactly validated.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_pack as pack  # noqa: E402
from tools import (  # noqa: E402
    mf1750_recipe_position_permutation_batch3_prerequisite as batch2_prerequisite,
)


_HOST_PATH = Path(__file__).with_name("mf1750_runtime_lut_ptlw_fullframe_ab_v2_once.py")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_true_r20_partial_hold_v1_private_clean_ptlw_host",
    _HOST_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load clean-PTLW host mechanics: {_HOST_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)

REPORT = pack.build_report()
base = host.base
v1b = host.v1b
endpoint = host.endpoint
v3 = host.v3
v2 = host.v2
v1 = host.v1

for module in (v1b, endpoint, v3, v2, base):
    module.pack = pack
host.pack = pack
host.REPORT = REPORT
v1b.REPORT = REPORT
endpoint.REPORT = REPORT
v3.REPORT = REPORT
v2.REPORT = REPORT
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

MAIN_BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-true-r20-partial-hold-v1"
    / "ec5_runtime_lut_true_r20_partial_hold_v1"
)
FIRMWARE_BIN = MAIN_BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = MAIN_BUILD_DIR / "firmware.elf"
FIRMWARE_BIN_BYTES: int | None = 816_736
FIRMWARE_BIN_SHA256: str | None = (
    "458fff47291319e9ec4cf5ceec2ef855551a82792d765055400bceb2c9d6a89f"
)
FIRMWARE_ELF_BYTES: int | None = 13_371_716
FIRMWARE_ELF_SHA256: str | None = (
    "8aaefd61977fea24e17c3b716efbfbf7b93a546eed386887c713ceeb43085eb8"
)

host.MAIN_BUILD_DIR = MAIN_BUILD_DIR
host.FIRMWARE_BIN = FIRMWARE_BIN
host.FIRMWARE_ELF = FIRMWARE_ELF
host.FIRMWARE_BIN_BYTES = FIRMWARE_BIN_BYTES
host.FIRMWARE_BIN_SHA256 = FIRMWARE_BIN_SHA256
host.FIRMWARE_ELF_BYTES = FIRMWARE_ELF_BYTES
host.FIRMWARE_ELF_SHA256 = FIRMWARE_ELF_SHA256

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = pack.CONTRACT_ID
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_TRUE_COMPLETE_R20_TUPLE_SWITCH_"
    "PARTIAL_HOLD_CLEAN_PTLW_V1_BATCH1_EVIDENCE_GATED"
)
base.runner.DEVICE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.EVIDENCE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
v3.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
v3.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
base.runner.ENDPOINTS = {
    name: f"{pack.ENDPOINT_BASE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_BATCH1_EVIDENCE_GATED_TRUE_R20_PARTIAL_HOLD_V1_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_BATCH1_EVIDENCE_GATED_TRUE_R20_PARTIAL_HOLD_V1_ACTION_ONCE"
)
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_true_r20_partial_hold_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_20260828_V1"
)

_PROFILE_SOURCE = (
    "batch1_prerequisite_gated_factory_white_plus_legacy_active_and_commented_"
    "complete_535_tuples"
)
host._PROFILE_SOURCE = _PROFILE_SOURCE

BATCH1_CAMPAIGN_ID = "EC5_SAME_R20_PARITY_2X4_V1"
BATCH1_CONTRACT_SCHEMA = "mf1750-same-r20-parity-contract-v1"
BATCH1_CONTRACT_ID = "718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8"
BATCH1_ACTION_IDS = (
    "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4",
    "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816",
    "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381",
    "711ba3e2310347645f6734537041959eb6f6dd419d26882bdc4264ad66fdc717",
)
BATCH1_ACTION_OUTPUTS = (
    "action-01-active-active-atlas.json",
    "action-02-factory-otp-white-after-aa.json",
    "action-03-commented-commented-atlas.json",
    "action-04-factory-otp-white-after-cc.json",
)
BATCH1_ACTIVE_GLOBAL_TUPLE_ID = (
    "4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820"
)
BATCH1_COMMENTED_GLOBAL_TUPLE_ID = (
    "1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038"
)
BATCH1_EVIDENCE_KIND = "mf1750-same-r20-parity-evidence-bundle-v1"
BATCH2_EVIDENCE_KIND = batch2_prerequisite.KIND
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _expect(value: Mapping[str, Any], exact: Mapping[str, Any], label: str) -> None:
    host._expect(value, exact, label)


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "cross_palette_hold_probe",
        "true_complete_r20_tuple_switch",
        "runtime_code7_full_dtm_prestage",
        "batch1_evidence_gate_required",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "historical_global_header_only_cross_lut",
        "runtime_treatment_action_stage_cdi",
        "runtime_treatment_action_stage_btst2",
        "runtime_treatment_repeat_ptlw_after_pon_busy",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("true-R20 required capability differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("true-R20 forbidden capability differs")


def _validate_baseline(value: Mapping[str, Any]) -> None:
    baseline = value.get("baseline_contract")
    if not isinstance(baseline, Mapping):
        raise base.runner.RecheckError("true-R20 baseline contract is absent")
    _expect(
        baseline,
        {
            "ordinal": None,
            "role": "EXTERNAL_BATCH1_TERMINAL_FACTORY_WHITE",
            "external_anchor_required": True,
            "anchor_established_by_firmware": False,
            "one_visible_refresh_required": False,
            "runtime_code7_action_reachable": False,
            "factory_otp_recovery_ordinal": 4,
        },
        "true-R20 baseline",
    )


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    _expect(
        value,
        {
            "layout_id": pack.VARIANT_KEY,
            "profile_source": _PROFILE_SOURCE,
            "action_count": 4,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
            "automatic_execute": False,
            "automatic_chaining": False,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "electrical_parameter_write": False,
            "dither": False,
            "spatial_mixing": False,
            "retry": False,
            "recovery": False,
            "per_action_readiness_qualification_required": True,
            "three_gate_busy_admission_evidence_required": True,
            "qualifier_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        },
        "true-R20 version",
    )
    nvs = value.get("nvs_contract")
    if not isinstance(nvs, Mapping):
        raise base.runner.RecheckError("true-R20 NVS contract is absent")
    _expect(
        nvs,
        {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 5,
            "initial_key_present": False,
            "initial_value": 1,
            "initial_next_ordinal": 1,
        },
        "true-R20 NVS",
    )
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    _expect(
        value,
        {
            "layout_id": pack.VARIANT_KEY,
            "profile_source": _PROFILE_SOURCE,
            "actions": list(base.runner.ACTIONS),
            "action_count": 4,
            "one_driver_call_per_action": True,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
            "automatic_chaining": False,
            "startup_refresh": False,
            "retry": False,
            "recovery": False,
            "per_action_readiness_qualification": (
                host._expected_qualification_contract()
            ),
            "busy_admission_contract": pack.BUSY_ADMISSION_CONTRACT,
        },
        "true-R20 manifest",
    )
    layout = value.get("history_layout")
    if not isinstance(layout, Mapping):
        raise base.runner.RecheckError("true-R20 history layout is absent")
    exact = {
        "external_factory_white_anchor_required": True,
        "anchor_established_by_firmware": False,
        "factory_otp_recovery_ordinal": 4,
        "batch1_evidence_requirements_id": (pack.BATCH1_EVIDENCE_REQUIREMENTS_ID),
        "candidate_codes": [0, 0, 2],
        "candidate_codes_are_not_colour_names": True,
        "candidate_mapping_status": "REQUIRES_BATCH1_EVIDENCE",
        "historical_global_header_only_cross_lut": False,
        "complete_tuple_switched_per_runtime_action": True,
        "both_controllers_receive_same_tuple_per_runtime_action": True,
        "runtime_code7_full_dtm_prestage": True,
        "runtime_code7_prestage_no_refresh": True,
        "runtime_code7_prestage_bytes_per_controller": 153_600,
        "runtime_code7_prestage_sha256": pack.PRELOAD_DTM_SHA256,
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_mode": 1,
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "ptlw_payloads_hex": [payload.hex() for payload in pack.PTLW_PAYLOADS],
        "windows": [
            {
                "x": window.x,
                "y": window.y,
                "width": window.width,
                "height": window.height,
                "cs1_code": window.cs1_code,
                "cs2_code": window.cs2_code,
            }
            for window in pack.WINDOWS
        ],
        "windows_disjoint": True,
        "runtime_target_dtm_bytes_per_controller": 9_600,
        "runtime_combined_dtm_bytes_per_controller": 163_200,
        "runtime_dtm_transport": (
            "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP"
        ),
        "complete_tuple_profile_sequence": [
            "active",
            "commented",
            "active",
            None,
        ],
        "active_tuple_sha256": pack.PROFILE_ACTIVE["tuple_sha256"],
        "commented_tuple_sha256": pack.PROFILE_COMMENTED["tuple_sha256"],
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "command_0x86": False,
        "extra_dtm_prefix_or_suffix_byte": False,
    }
    for key, wanted in exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"true-R20 history layout {key} differs")
    runtime_actions = layout.get("runtime_actions")
    if not isinstance(runtime_actions, list) or len(runtime_actions) != 3:
        raise base.runner.RecheckError("true-R20 runtime actions differ")
    for index, item in enumerate(runtime_actions):
        profile = pack.PROFILES[("active", "commented", "active")[index]]
        _expect(
            item,
            {
                "ordinal": index + 1,
                "tuple": ("active", "commented", "active")[index],
                "code": pack.TARGET_CODES[index],
                "cs1_tuple_sha256": profile["tuple_sha256"],
                "cs2_tuple_sha256": profile["tuple_sha256"],
            },
            f"true-R20 runtime action {index + 1}",
        )
    _validate_capabilities(value)
    _validate_baseline(value)


def _expected_action_stage_counts(ordinal: int) -> dict[str, int]:
    if ordinal in (1, 2, 3):
        dtm_bytes, lut_bytes, ptlw_writes = 326_400, 2_478, 2
    elif ordinal == 4:
        dtm_bytes, lut_bytes, ptlw_writes = 307_200, 0, 0
    else:
        raise base.runner.RecheckError("true-R20 action-stage ordinal differs")
    return {
        "pon": 1,
        "pof": 1,
        "drf": 1,
        "dtm_bytes": dtm_bytes,
        "lut_bytes": lut_bytes,
        "ptlw_writes": ptlw_writes,
        "command_0x86": 0,
        "visible_refresh_requests": 1,
    }


host._validate_capabilities = _validate_capabilities
host._validate_version = _validate_version
host._validate_manifest = _validate_manifest
host._expected_action_stage_counts = _expected_action_stage_counts
for module in (v1b, endpoint, v3, v2, base):
    module._validate_capabilities = _validate_capabilities
    module._validate_version = _validate_version
    module._validate_manifest = _validate_manifest
base.runner._validate_capabilities = _validate_capabilities
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = host._validate_ready_status
base.runner._preflight = host._preflight
base.runner._request = host._request_with_busy_evidence
base.runner._write_new = host._write_new_bound
v1._validate_fresh_no_execute_report = host._validate_fresh_no_execute_report
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._validate_ready_status = host._validate_ready_status
v1._validate_fault_status = host._validate_fault_status
v1._validate_fault_report = host._validate_fault_report
v1._load_permanent_claim = host._load_permanent_claim
v1._preflight = host._preflight
v2._validate_ready_status = host._validate_ready_status
v2._preflight = host._preflight
v3._validate_ready_status = host._validate_ready_status
v3._validate_complete_report = host._validate_complete_report
v3._validate_prior_terminal_report = host._validate_prior_terminal_report_bound
v3._preflight = host._preflight

_BASE_HEADERS = base.runner._headers


def _headers(action: Mapping[str, Any], boot_nonce: str, intent: str) -> dict[str, str]:
    value = _BASE_HEADERS(action, boot_nonce, intent)
    value["X-EC5-Batch1-Evidence-Requirements-Id"] = (
        pack.BATCH1_EVIDENCE_REQUIREMENTS_ID
    )
    return value


base.runner._headers = _headers


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _batch1_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"Batch-1 {label} differs")
    return value


def _batch1_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise base.runner.RecheckError(f"Batch-1 {label} SHA differs")
    return value


def _batch1_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise base.runner.RecheckError(f"Batch-1 {label} differs")
    return value


def _batch1_number(value: Any, label: str) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise base.runner.RecheckError(f"Batch-1 {label} differs")
    return float(value)


def _validate_batch1_camera_and_analysis_bindings(
    value: Mapping[str, Any], action_results: Sequence[Mapping[str, Any]]
) -> None:
    if (
        value.get("capture_evidence_complete") is not True
        or value.get("repeat_noise_evidence_complete") is not True
    ):
        raise base.runner.RecheckError("Batch-1 synchronized evidence differs")

    noise = _batch1_mapping(value.get("repeat_noise_baseline"), "repeat-noise baseline")
    required_noise_keys = {
        "path",
        "file_sha256",
        "canonical_integrity_sha256",
        "baseline_id",
        "reference_geometry_sha256",
        "capture_count",
        "repeat_noise_p95_de76",
        "camera_signature",
    }
    if set(noise) != required_noise_keys:
        raise base.runner.RecheckError("Batch-1 repeat-noise schema differs")
    _batch1_text(noise.get("path"), "repeat-noise path")
    for field in (
        "file_sha256",
        "canonical_integrity_sha256",
        "baseline_id",
        "reference_geometry_sha256",
    ):
        _batch1_sha(noise.get(field), f"repeat-noise {field}")
    capture_count = noise.get("capture_count")
    if type(capture_count) is not int or capture_count < 3:
        raise base.runner.RecheckError("Batch-1 repeat-noise capture count differs")
    repeat_noise = _batch1_number(
        noise.get("repeat_noise_p95_de76"), "repeat-noise p95"
    )
    noise_camera = _batch1_mapping(
        noise.get("camera_signature"), "repeat-noise camera signature"
    )

    camera_lock = _batch1_mapping(value.get("camera_lock"), "camera lock")
    required_camera_keys = {
        "camera_id",
        "instance_id",
        "index",
        "backend",
        "mount_id",
        "requested_settings",
        "effective_settings",
        "photo_width",
        "photo_height",
        "boot_nonce",
        "manual_controls_required",
        "same_signature_all_four_captures",
        "strictly_increasing_capture_times",
    }
    if set(camera_lock) != required_camera_keys:
        raise base.runner.RecheckError("Batch-1 camera lock schema differs")
    for field in ("camera_id", "backend", "mount_id", "boot_nonce"):
        _batch1_text(camera_lock.get(field), f"camera lock {field}")
    instance_id = camera_lock.get("instance_id")
    if instance_id is not None:
        _batch1_text(instance_id, "camera lock instance_id")
    if type(camera_lock.get("index")) is not int or camera_lock["index"] < 0:
        raise base.runner.RecheckError("Batch-1 camera index differs")
    for field in ("photo_width", "photo_height"):
        if type(camera_lock.get(field)) is not int or camera_lock[field] < 1:
            raise base.runner.RecheckError(f"Batch-1 camera {field} differs")
    requested = _batch1_mapping(
        camera_lock.get("requested_settings"), "requested camera settings"
    )
    effective = _batch1_mapping(
        camera_lock.get("effective_settings"), "effective camera settings"
    )
    manual = _batch1_mapping(
        camera_lock.get("manual_controls_required"), "manual camera controls"
    )
    expected_manual = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
    }
    if dict(manual) != expected_manual:
        raise base.runner.RecheckError("Batch-1 manual camera contract differs")
    for field, wanted in expected_manual.items():
        if type(requested.get(field)) not in (int, float) or float(
            requested[field]
        ) != float(wanted):
            raise base.runner.RecheckError(f"Batch-1 requested camera {field} differs")
    for field in ("focus", "exposure", "white_balance_temperature"):
        if type(requested.get(field)) not in (int, float) or type(
            effective.get(field)
        ) not in (int, float):
            raise base.runner.RecheckError(f"Batch-1 manual camera {field} differs")
    if (
        camera_lock.get("same_signature_all_four_captures") is not True
        or camera_lock.get("strictly_increasing_capture_times") is not True
    ):
        raise base.runner.RecheckError("Batch-1 camera continuity differs")
    comparable_camera = {
        key: camera_lock[key]
        for key in (
            "camera_id",
            "instance_id",
            "index",
            "backend",
            "mount_id",
            "requested_settings",
            "effective_settings",
        )
    }
    if dict(noise_camera) != comparable_camera:
        raise base.runner.RecheckError("Batch-1 repeat-noise camera signature differs")

    captures = value.get("capture_bindings")
    if not isinstance(captures, list) or len(captures) != 4:
        raise base.runner.RecheckError("Batch-1 capture bindings differ")
    capture_photos: list[str] = []
    required_capture_keys = {
        "ordinal",
        "path",
        "sidecar_file_sha256",
        "canonical_integrity_sha256",
        "capture_id",
        "captured_at",
        "action_id",
        "descriptor_id",
        "action_result_sha256",
        "photo_sha256",
        "capture_binding",
        "coverage_scope",
    }
    for ordinal, (capture, action_result, action_id) in enumerate(
        zip(captures, action_results, BATCH1_ACTION_IDS, strict=True), 1
    ):
        item = _batch1_mapping(capture, f"capture ordinal {ordinal}")
        if set(item) != required_capture_keys:
            raise base.runner.RecheckError(
                f"Batch-1 capture ordinal {ordinal} schema differs"
            )
        if (
            item.get("ordinal") != ordinal
            or item.get("action_id") != action_id
            or item.get("action_result_sha256") != action_result.get("output_sha256")
            or item.get("capture_binding") != "live_synchronized"
            or item.get("coverage_scope") != "full_panel"
        ):
            raise base.runner.RecheckError(
                f"Batch-1 capture ordinal {ordinal} identity differs"
            )
        _batch1_text(item.get("path"), f"capture ordinal {ordinal} path")
        _batch1_text(item.get("captured_at"), f"capture ordinal {ordinal} timestamp")
        for field in (
            "sidecar_file_sha256",
            "canonical_integrity_sha256",
            "capture_id",
            "descriptor_id",
            "action_result_sha256",
            "photo_sha256",
        ):
            _batch1_sha(item.get(field), f"capture ordinal {ordinal} {field}")
        capture_photos.append(str(item["photo_sha256"]))

    analyses = _batch1_mapping(value.get("analysis_bindings"), "analysis bindings")
    expected_analysis_names = (
        "aa_atlas",
        "white_after_aa",
        "cc_atlas",
        "white_after_cc",
    )
    if set(analyses) != set(expected_analysis_names):
        raise base.runner.RecheckError("Batch-1 analysis binding names differ")
    for index, name in enumerate(expected_analysis_names):
        analysis = _batch1_mapping(analyses.get(name), f"analysis {name}")
        required = {
            "path",
            "file_sha256",
            "canonical_integrity_sha256",
            "source_photo_sha256",
            "reference_geometry_sha256",
            "repeat_noise_p95_de76",
        }
        if name in {"aa_atlas", "cc_atlas"}:
            required.add("interpretation")
        if set(analysis) != required:
            raise base.runner.RecheckError(f"Batch-1 analysis {name} schema differs")
        _batch1_text(analysis.get("path"), f"analysis {name} path")
        for field in (
            "file_sha256",
            "canonical_integrity_sha256",
            "source_photo_sha256",
            "reference_geometry_sha256",
        ):
            _batch1_sha(analysis.get(field), f"analysis {name} {field}")
        if (
            analysis.get("source_photo_sha256") != capture_photos[index]
            or analysis.get("reference_geometry_sha256")
            != noise.get("reference_geometry_sha256")
            or _batch1_number(
                analysis.get("repeat_noise_p95_de76"),
                f"analysis {name} repeat-noise p95",
            )
            != repeat_noise
        ):
            raise base.runner.RecheckError(f"Batch-1 analysis {name} binding differs")

    comparison = _batch1_mapping(value.get("aa_cc_comparison"), "AA-vs-CC comparison")
    required_comparison_keys = {
        "path",
        "file_sha256",
        "canonical_integrity_sha256",
        "comparison_id",
        "classification_state",
        "classification_counts",
        "absolute_colour_proven",
        "qualified_new_colour",
    }
    if set(comparison) != required_comparison_keys:
        raise base.runner.RecheckError("Batch-1 AA-vs-CC comparison schema differs")
    _batch1_text(comparison.get("path"), "AA-vs-CC comparison path")
    for field in ("file_sha256", "canonical_integrity_sha256", "comparison_id"):
        _batch1_sha(comparison.get(field), f"AA-vs-CC comparison {field}")
    if comparison.get("classification_state") not in {
        "CONTROLLER_INCONSISTENT_CODES_PRESENT",
        "R20_LINKED_EXPLORATORY_EFFECT_CODES_PRESENT",
        "NO_RESOLVED_AA_TO_CC_EFFECT",
    }:
        raise base.runner.RecheckError("Batch-1 AA-vs-CC classification differs")
    comparison_counts = _batch1_mapping(
        comparison.get("classification_counts"), "AA-vs-CC classification counts"
    )
    if (
        set(comparison_counts)
        != {
            "R20_LINKED_EXPLORATORY_EFFECT",
            "NO_RESOLVED_EFFECT",
            "CONTROLLER_INCONSISTENT",
        }
        or any(type(item) is not int or item < 0 for item in comparison_counts.values())
        or sum(item for item in comparison_counts.values() if type(item) is int) != 8
        or comparison.get("absolute_colour_proven") is not False
        or comparison.get("qualified_new_colour") is not False
    ):
        raise base.runner.RecheckError("Batch-1 AA-vs-CC evidence boundary differs")


def _load_batch1_evidence(path: Path) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError("Batch-1 evidence is absent or a symlink")
    payload = path.read_bytes()
    if len(payload) > base.runner._MAX_JSON_BYTES:  # noqa: SLF001
        raise base.runner.RecheckError("Batch-1 evidence is too large")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError("Batch-1 evidence is not UTF-8 JSON") from error
    if not isinstance(raw, Mapping):
        raise base.runner.RecheckError("Batch-1 evidence root differs")
    value = deepcopy(dict(raw))
    integrity = value.pop("integrity", None)
    expected_integrity = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha256(base.runner._canonical(value)),  # noqa: SLF001
    }
    if integrity != expected_integrity:
        raise base.runner.RecheckError("Batch-1 evidence canonical seal differs")
    exact = {
        "schema_version": 1,
        "kind": BATCH1_EVIDENCE_KIND,
        "campaign_id": BATCH1_CAMPAIGN_ID,
        "contract_schema": BATCH1_CONTRACT_SCHEMA,
        "contract_id": BATCH1_CONTRACT_ID,
        "action_ids": list(BATCH1_ACTION_IDS),
        "active_global_tuple_id": BATCH1_ACTIVE_GLOBAL_TUPLE_ID,
        "commented_global_tuple_id": BATCH1_COMMENTED_GLOBAL_TUPLE_ID,
        "outcome": "PASS",
        "active_same_r20_both_controllers": True,
        "commented_same_r20_both_controllers": True,
        "aa_left_right_parity_pass": True,
        "cc_left_right_parity_pass": True,
        "terminal_factory_white_clean_pass": True,
        "candidate_transport_codes_authorized": [0, 0, 2],
        "candidate_codes_are_not_colour_names": True,
        "terminal_factory_white_is_latest_bound_batch1_capture": True,
        "clean_white_visual_outcomes": {
            "ordinal_2": "PASS",
            "ordinal_4": "PASS",
        },
        "automatic_analysis": {
            "active_same_side": "PASS",
            "active_cross_side": "PASS",
            "commented_same_side": "PASS",
            "commented_cross_side": "PASS",
        },
    }
    _expect(value, exact, "Batch-1 evidence")
    if value.get("output_write_contract") != "O_EXCL":
        raise base.runner.RecheckError("Batch-1 output write contract differs")
    boundaries = _batch1_mapping(
        value.get("evidence_boundaries"), "evidence boundaries"
    )
    required_boundaries = {
        "camera_relative_de76_not_calibrated_de00": True,
        "compiled_payload_identity_not_bus_capture": True,
        "every_analysis_photo_bound_to_live_synchronized_action_capture": True,
        "full_panel_camera_coverage_required": True,
        "manual_camera_controls_and_mount_locked_across_batch": True,
        "analysis_threshold_bound_to_sealed_repeat_noise_report": True,
        "aa_cc_comparison_is_exploratory_not_causal": True,
        "external_refresh_after_last_bound_capture_not_proven": True,
        "candidate_codes_are_transport_codes_only": True,
        "no_absolute_colour_or_new_colour_claim": True,
        "device_io_performed_by_bundle_builder": False,
    }
    if any(
        boundaries.get(key) is not wanted for key, wanted in required_boundaries.items()
    ):
        raise base.runner.RecheckError("Batch-1 evidence boundaries differ")
    action_results = value.get("action_results")
    if not isinstance(action_results, list) or len(action_results) != 4:
        raise base.runner.RecheckError("Batch-1 action evidence differs")
    for ordinal, (item, action_id, output_name) in enumerate(
        zip(
            action_results,
            BATCH1_ACTION_IDS,
            BATCH1_ACTION_OUTPUTS,
            strict=True,
        ),
        1,
    ):
        if not isinstance(item, Mapping):
            raise base.runner.RecheckError("Batch-1 action evidence differs")
        _expect(
            item,
            {
                "ordinal": ordinal,
                "action_id": action_id,
                "output_name": output_name,
                "outcome": "complete_pass",
            },
            f"Batch-1 action evidence ordinal {ordinal}",
        )
        output_sha256 = item.get("output_sha256")
        if (
            not isinstance(output_sha256, str)
            or _SHA256.fullmatch(output_sha256) is None
        ):
            raise base.runner.RecheckError(
                f"Batch-1 action evidence ordinal {ordinal} output SHA differs"
            )
    _validate_batch1_camera_and_analysis_bindings(value, action_results)
    value["integrity"] = integrity
    return value, _sha256(payload)


def _load_batch2_evidence(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return batch2_prerequisite.validate(Path(path))
    except batch2_prerequisite.Batch3PrerequisiteError as exc:
        raise base.runner.RecheckError(f"Batch-2 evidence differs: {exc}") from exc


def _validate_batch_prerequisite_continuity(
    batch1: Mapping[str, Any], batch2_binding: Mapping[str, Any]
) -> None:
    batch1_noise = _batch1_mapping(
        batch1.get("repeat_noise_baseline"), "repeat-noise baseline"
    )
    batch2_analysis = _batch1_mapping(
        batch2_binding.get("shared_analysis_bindings"),
        "Batch-2 shared analysis",
    )
    batch2_noise = _batch1_mapping(
        batch2_analysis.get("repeat_noise_baseline"),
        "Batch-2 repeat-noise baseline",
    )
    for field in (
        "file_sha256",
        "canonical_integrity_sha256",
        "baseline_id",
        "reference_geometry_sha256",
        "repeat_noise_p95_de76",
        "camera_signature",
    ):
        if batch2_noise.get(field) != batch1_noise.get(field):
            raise base.runner.RecheckError(
                f"Batch-1/Batch-2 repeat-noise {field} differs"
            )
    if batch2_analysis.get("reference_geometry_sha256") != batch1_noise.get(
        "reference_geometry_sha256"
    ) or batch2_analysis.get("repeat_noise_p95_de76") != batch1_noise.get(
        "repeat_noise_p95_de76"
    ):
        raise base.runner.RecheckError("Batch-1/Batch-2 geometry or noise differs")

    batch1_camera = _batch1_mapping(batch1.get("camera_lock"), "camera lock")
    comparable_batch1 = {
        key: deepcopy(batch1_camera[key])
        for key in (
            "camera_id",
            "instance_id",
            "index",
            "backend",
            "mount_id",
            "requested_settings",
            "effective_settings",
        )
    }
    if batch2_binding.get("shared_camera_lock") != comparable_batch1:
        raise base.runner.RecheckError(
            "Batch-1/Batch-2 camera, mount, or manual readback differs"
        )
    terminal = _batch1_mapping(
        batch2_binding.get("terminal_white_prerequisite"),
        "Batch-2 terminal white prerequisite",
    )
    if (
        terminal.get("eligible") is not True
        or terminal.get("patch_count") != 60
        or terminal.get("classification_state")
        != "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
        or terminal.get("reference_geometry_sha256")
        != batch1_noise.get("reference_geometry_sha256")
        or terminal.get("repeat_noise_p95_de76")
        != batch1_noise.get("repeat_noise_p95_de76")
    ):
        raise base.runner.RecheckError("Batch-2 terminal 60-patch white anchor differs")


_ACTIVE_BATCH1_EVIDENCE_BINDING: dict[str, Any] | None = None
_ACTIVE_BATCH2_EVIDENCE_BINDING: dict[str, Any] | None = None
_BASE_SEAL_WITH_PREREQUISITE = host._seal_with_prerequisite


def _seal_with_batch1_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    document = deepcopy(dict(value))
    kind = document.get("kind")
    if isinstance(kind, str) and kind.startswith(pack.DEVICE_KIND_PREFIX):
        if _ACTIVE_BATCH1_EVIDENCE_BINDING is None:
            raise base.runner.RecheckError(
                "true-R20 evidence cannot be sealed outside Batch-1 context"
            )
        if _ACTIVE_BATCH2_EVIDENCE_BINDING is None:
            raise base.runner.RecheckError(
                "true-R20 evidence cannot be sealed outside Batch-2 context"
            )
        document["batch1_evidence_binding"] = deepcopy(_ACTIVE_BATCH1_EVIDENCE_BINDING)
        document["batch2_evidence_binding"] = deepcopy(_ACTIVE_BATCH2_EVIDENCE_BINDING)
    return _BASE_SEAL_WITH_PREREQUISITE(document)


host._seal_with_prerequisite = _seal_with_batch1_evidence
base.runner._seal = _seal_with_batch1_evidence


_BASE_RUN_ONCE = host.run_once


def run_once(
    base_url: str,
    ordinal: int,
    *,
    batch1_evidence: Path | None,
    batch2_evidence: Path | None = None,
    claims: Path,
    output: Path,
    prior_result: Path | None = None,
    confirm_j2_on: bool,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    global _ACTIVE_BATCH1_EVIDENCE_BINDING, _ACTIVE_BATCH2_EVIDENCE_BINDING
    if batch1_evidence is None:
        raise base.runner.RecheckError(
            "sealed Batch-1 same-R20 evidence is required before live run"
        )
    evidence, evidence_file_sha256 = _load_batch1_evidence(batch1_evidence)
    if batch2_evidence is None:
        raise base.runner.RecheckError(
            "sealed Batch-2 terminal-white evidence is required before live run"
        )
    _batch2_root, batch2_binding = _load_batch2_evidence(batch2_evidence)
    _validate_batch_prerequisite_continuity(evidence, batch2_binding)
    batch1_binding = {
        "input_file": str(Path(batch1_evidence).resolve()),
        "file_sha256": evidence_file_sha256,
        "integrity": evidence["integrity"],
        "requirements_id": pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
        "campaign_id": BATCH1_CAMPAIGN_ID,
        "contract_id": BATCH1_CONTRACT_ID,
        "action_results": deepcopy(evidence["action_results"]),
        "capture_bindings": deepcopy(evidence["capture_bindings"]),
        "repeat_noise_baseline": deepcopy(evidence["repeat_noise_baseline"]),
        "analysis_bindings": deepcopy(evidence["analysis_bindings"]),
        "aa_cc_comparison": deepcopy(evidence["aa_cc_comparison"]),
    }
    if (
        _ACTIVE_BATCH1_EVIDENCE_BINDING is not None
        or _ACTIVE_BATCH2_EVIDENCE_BINDING is not None
    ):
        raise base.runner.RecheckError(
            "prerequisite evidence context is already active"
        )
    _ACTIVE_BATCH1_EVIDENCE_BINDING = batch1_binding
    _ACTIVE_BATCH2_EVIDENCE_BINDING = deepcopy(batch2_binding)
    try:
        result = _BASE_RUN_ONCE(
            base_url,
            ordinal,
            claims=claims,
            output=output,
            prior_result=prior_result,
            confirm_j2_on=confirm_j2_on,
            poll_seconds=poll_seconds,
            poll_count=poll_count,
        )
    finally:
        _ACTIVE_BATCH1_EVIDENCE_BINDING = None
        _ACTIVE_BATCH2_EVIDENCE_BINDING = None
    if result.get("batch1_evidence_binding") != batch1_binding:
        raise base.runner.RecheckError("sealed Batch-1 result binding differs")
    if result.get("batch2_evidence_binding") != batch2_binding:
        raise base.runner.RecheckError("sealed Batch-2 result binding differs")
    return result


base.runner.run_once = run_once


def describe() -> dict[str, Any]:
    value = host.describe()
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "external_factory_white_anchor_required": True,
        "factory_otp_white_recovery_ordinal": 4,
        "runtime_lut_partial_ordinals": [1, 2, 3],
        "candidate_codes": list(pack.TARGET_CODES),
        "candidate_codes_are_not_colour_names": True,
        "complete_tuple_sequence": ["active", "commented", "active"],
        "both_controllers_receive_same_tuple_per_action": True,
        "historical_global_header_only_cross_lut": False,
        "active_tuple_sha256": pack.PROFILE_ACTIVE["tuple_sha256"],
        "commented_tuple_sha256": pack.PROFILE_COMMENTED["tuple_sha256"],
        "full_code7_prestage_bytes_per_controller": pack.CONTROLLER_DTM_BYTES,
        "target_crop_bytes_per_controller": list(pack.CROPPED_DTM_BYTES),
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "ptlw_mode": 1,
        "ptlw_writes_per_controller_for_partial_actions": 1,
        "repeat_ptlw_after_pon_busy": False,
        "action_stage_cdi": False,
        "action_stage_btst2": False,
        "command_0x86": False,
        "refresh_sequence": ["PON", "DRF_00", "POF_00"],
        "blocking_refresh_first_poll_floor_seconds": 65.0,
    }
    value["variant"] = deepcopy(REPORT["contract"])
    value["action_order"] = list(pack.ROLES)
    value["batch1_evidence_gate"] = {
        "required": True,
        "requirements_id": pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
        "batch1_contract_frozen": True,
        "live_blocked_until_frozen_and_validated": True,
    }
    value["batch2_evidence_gate"] = {
        "required": True,
        "kind": BATCH2_EVIDENCE_KIND,
        "deep_terminal_white_camera_noise_geometry_validation": True,
        "live_blocked_until_frozen_and_validated": True,
    }
    value["automatic_camera_gate_after_each_action"] = True
    value["live_authorized"] = False
    return value


base.runner.describe = describe


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnose = sub.add_parser("diagnose-j2-off")
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnose.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--batch1-evidence", type=Path, required=True)
    run.add_argument("--batch2-evidence", type=Path, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--prior-result", type=Path)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument("--confirm-j2-off", action="store_true", required=True)
    salvage.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    salvage.add_argument("--prior-result", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = host.dry_validate()
            if value.get("verified") is not True:
                print(json.dumps(value, ensure_ascii=False, sort_keys=True))
                return 2
        elif args.command == "diagnose-j2-off":
            value = host.diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "salvage-fault":
            value = host.salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                batch1_evidence=args.batch1_evidence,
                batch2_evidence=args.batch2_evidence,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"true-R20 partial-HOLD V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
