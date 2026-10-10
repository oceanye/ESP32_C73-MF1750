#!/usr/bin/env python3
"""Freeze the four-action true-R20 tuple-switch partial-HOLD V1 contract.

Unlike the historical cross-global-header experiment, every runtime action
selects one complete, controller-symmetric PWR/PLL/R20/R21 tuple.  The three
candidate codes are deliberately unnamed and remain blocked from live use
until a sealed Batch-1 same-R20 parity result confirms their mapping.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v1_pack as old  # noqa: E402
from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as clean  # noqa: E402


VARIANT_KEY = "L535_TRUE_R20_TUPLE_SWITCH_PARTIAL_HOLD_CLEAN_PTLW_V1"
BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_2026-08-28"
TEST_ID = "EC5-RUNTIME-LUT-TRUE-R20-PARTIAL-HOLD-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1"
NVS_NAMESPACE = "tr20ph_v1"
NVS_KEY = "cursor_tr20ph1"
ENV_NAME = "ec5_runtime_lut_true_r20_partial_hold_v1"
DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_DEVICE_V1"
IDENTITY_REVISION = "runtime-lut-true-r20-partial-hold-v1"
DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-true-r20-partial-hold-v1"
ENDPOINT_BASE = "/api/ec5/runtime-lut-true-r20-partial-hold-v1"
PROFILE_ID = (
    "ACTIVE_BOTH_CS_CODE0_TO_COMMENTED_BOTH_CS_CODE0_TO_"
    "ACTIVE_BOTH_CS_CODE2_CLEAN_PTLW_V1"
)

WIDTH = identity.WIDTH
HEIGHT = identity.HEIGHT
CONTROLLER_WIDTH = identity.CONTROLLER_WIDTH
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
WHITE_CODE = 7
FACTORY_WHITE_CODE = 1
TARGET_CODES = (0, 0, 2)
WINDOWS = (
    identity.Window(48, 64, 160, 120, 0, 0),
    identity.Window(304, 240, 160, 120, 0, 0),
    identity.Window(48, 416, 160, 120, 2, 2),
)
CROPPED_DTM_BYTES = tuple(window.width * window.height // 2 for window in WINDOWS)

QUALIFIER_V2_PREREQUISITE = deepcopy(clean.QUALIFIER_V2_PREREQUISITE)
QUALIFIER_V2_BUNDLE_ID = clean.QUALIFIER_V2_BUNDLE_ID
PER_ACTION_READINESS_QUALIFICATION = deepcopy(clean.PER_ACTION_READINESS_QUALIFICATION)
BUSY_ADMISSION_CONTRACT = deepcopy(clean.BUSY_ADMISSION_CONTRACT)

BATCH1_EVIDENCE_REQUIREMENTS = {
    "schema": "mf1750-stage3-same-r20-parity-prerequisite-v1",
    "campaign_id": "EC5_SAME_R20_PARITY_2X4_V1",
    "contract_schema": "mf1750-same-r20-parity-contract-v1",
    "contract_id": ("718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8"),
    "required_actions": [
        {
            "ordinal": 1,
            "role": "SAME_R20_ACTIVE_ACTIVE_ATLAS",
            "action_id": (
                "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4"
            ),
            "output_name": "action-01-active-active-atlas.json",
            "required_outcome": "complete_pass",
            "capture_binding": "live_synchronized",
            "coverage_scope": "full_panel",
            "full_panel_visible_required": True,
            "full_panel_uncropped_required": True,
            "action_result_file_sha256_required": True,
            "action_result_canonical_integrity_sha256_required": True,
            "photo_file_sha256_required": True,
            "capture_sidecar_file_sha256_required": True,
            "capture_sidecar_binds_action_result_sha256": True,
            "capture_sidecar_binds_photo_sha256": True,
        },
        {
            "ordinal": 2,
            "role": "FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE",
            "action_id": (
                "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816"
            ),
            "output_name": "action-02-factory-otp-white-after-aa.json",
            "required_outcome": "complete_pass",
            "required_clean_white_visual_outcome": "PASS",
            "capture_binding": "live_synchronized",
            "coverage_scope": "full_panel",
            "full_panel_visible_required": True,
            "full_panel_uncropped_required": True,
            "action_result_file_sha256_required": True,
            "action_result_canonical_integrity_sha256_required": True,
            "photo_file_sha256_required": True,
            "capture_sidecar_file_sha256_required": True,
            "capture_sidecar_binds_action_result_sha256": True,
            "capture_sidecar_binds_photo_sha256": True,
        },
        {
            "ordinal": 3,
            "role": "SAME_R20_COMMENTED_COMMENTED_ATLAS",
            "action_id": (
                "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381"
            ),
            "output_name": "action-03-commented-commented-atlas.json",
            "required_outcome": "complete_pass",
            "capture_binding": "live_synchronized",
            "coverage_scope": "full_panel",
            "full_panel_visible_required": True,
            "full_panel_uncropped_required": True,
            "action_result_file_sha256_required": True,
            "action_result_canonical_integrity_sha256_required": True,
            "photo_file_sha256_required": True,
            "capture_sidecar_file_sha256_required": True,
            "capture_sidecar_binds_action_result_sha256": True,
            "capture_sidecar_binds_photo_sha256": True,
        },
        {
            "ordinal": 4,
            "role": "FACTORY_OTP_WHITE_AFTER_COMMENTED_COMMENTED",
            "action_id": (
                "711ba3e2310347645f6734537041959eb6f6dd419d26882bdc4264ad66fdc717"
            ),
            "output_name": "action-04-factory-otp-white-after-cc.json",
            "required_outcome": "complete_pass",
            "required_clean_white_visual_outcome": "PASS",
            "capture_binding": "live_synchronized",
            "coverage_scope": "full_panel",
            "full_panel_visible_required": True,
            "full_panel_uncropped_required": True,
            "action_result_file_sha256_required": True,
            "action_result_canonical_integrity_sha256_required": True,
            "photo_file_sha256_required": True,
            "capture_sidecar_file_sha256_required": True,
            "capture_sidecar_binds_action_result_sha256": True,
            "capture_sidecar_binds_photo_sha256": True,
        },
    ],
    "active_global_tuple_id": (
        "4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820"
    ),
    "commented_global_tuple_id": (
        "1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038"
    ),
    "required_automatic_analysis": {
        "active_same_side_pass": True,
        "active_cross_side_pass": True,
        "commented_same_side_pass": True,
        "commented_cross_side_pass": True,
    },
    "fixed_capture_contract": {
        "capture_count": 4,
        "all_captures_live_synchronized": True,
        "all_captures_full_panel": True,
        "all_captures_full_panel_visible": True,
        "all_captures_full_panel_uncropped": True,
        "camera_identity_tuple_fields_required": [
            "camera_id",
            "instance_id",
            "index",
            "backend",
        ],
        "camera_identity_tuple_all_fields_present_required": True,
        "same_camera_identity_tuple_across_all_actions": True,
        "same_camera_signature_across_all_actions": True,
        "mount_id_required": True,
        "same_mount_id_across_all_actions": True,
        "camera_or_mount_move_between_actions_forbidden": True,
        "manual_controls": {
            "auto_exposure": False,
            "auto_white_balance": False,
            "autofocus": False,
            "manual_exposure_value_required": True,
            "manual_white_balance_value_required": True,
            "manual_focus_value_required": True,
            "control_readback_required": True,
            "same_control_readbacks_across_all_actions": True,
        },
        "per_action_action_result_and_photo_sha_binding_required": True,
    },
    "repeat_noise_report_contract": {
        "required": True,
        "report_file_sha256_required": True,
        "report_canonical_integrity_sha256_required": True,
        "repeat_noise_p95_de76_required": True,
        "finite_nonnegative_repeat_noise_required": True,
        "report_binds_camera_signature": True,
        "report_binds_mount_id": True,
        "report_binds_manual_exposure_white_balance_focus": True,
        "camera_signature_and_mount_id_must_exactly_match_all_four_captures": True,
        "top_level_evidence_bundle_binds_report_file_sha256": True,
        "top_level_evidence_bundle_binds_report_canonical_integrity_sha256": True,
        "analysis_reports_requiring_exact_repeat_noise_p95_match": [
            "aa_atlas",
            "white_after_aa",
            "cc_atlas",
            "white_after_cc",
        ],
        "all_four_analysis_repeat_noise_p95_values_equal_report": True,
        "capture_sidecars_do_not_bind_repeat_noise_report": True,
    },
    "required_outcome": "PASS",
    "same_r20_both_controllers_required": True,
    "active_and_commented_atlases_required": True,
    "terminal_factory_white_required": True,
    "candidate_codes": [0, 0, 2],
    "candidate_mapping_status": "FROZEN_CANDIDATES_PENDING_BATCH1_EVIDENCE",
    "forbid_position_or_colour_name_inference": True,
}
BATCH1_EVIDENCE_REQUIREMENTS_ID = identity.sha256(
    identity.canonical(BATCH1_EVIDENCE_REQUIREMENTS)
)


def _profile_tuple(name: str) -> dict[str, Any]:
    source = old.cross.profile(name)
    power_sha256 = (
        "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2"
        if name == "active"
        else "e571c5cf13938b4f4e12b7152ef5ac7d4970ca1d7fd5aa5568b3bf5ab5b208c9"
    )
    pll_sha256 = (
        "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
        if name == "active"
        else "084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5"
    )
    r20_sha256 = (
        identity.ACTIVE_R20_PREFIX_SHA256
        if name == "active"
        else identity.COMMENTED_R20_PREFIX_SHA256
    )
    value = {
        "name": name,
        "global_header_sha256": source["global_header_sha256"],
        "power_command": "0x01",
        "power_bytes": 6,
        "power_sha256": power_sha256,
        "pll_command": "0x30",
        "pll_bytes": 1,
        "pll_sha256": pll_sha256,
        "r20_command": "0x20",
        "r20_prefix_bytes": 535,
        "r20_prefix_sha256": r20_sha256,
        "r21_command": "0x21",
        "r21_bytes": 704,
        "r21_sha256": identity.R21_SHA256,
    }
    value["tuple_sha256"] = identity.sha256(identity.canonical(value))
    return value


PROFILE_ACTIVE = _profile_tuple("active")
PROFILE_COMMENTED = _profile_tuple("commented")
PROFILES = {"active": PROFILE_ACTIVE, "commented": PROFILE_COMMENTED}
PROFILE_SEQUENCE: tuple[str | None, ...] = (
    "active",
    "commented",
    "active",
    None,
)
ROLES = (
    "PATCH_A_ACTIVE_TUPLE_CANDIDATE_CODE0",
    "PATCH_B_COMMENTED_TUPLE_CANDIDATE_CODE0_HOLD_A",
    "PATCH_C_ACTIVE_TUPLE_CANDIDATE_CODE2_HOLD_AB",
    "FACTORY_OTP_WHITE_RECOVERY",
)
BRANCHES = (
    "TRUE_ACTIVE_PWR_PLL_R20_R21_BOTH_CS_CODE0_ROI_A",
    "TRUE_COMMENTED_PWR_PLL_R20_R21_BOTH_CS_CODE0_ROI_B_HOLD_A",
    "TRUE_ACTIVE_PWR_PLL_R20_R21_BOTH_CS_CODE2_ROI_C_HOLD_AB",
    "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
)
WHITE_REFRESH_SEQUENCE = old.WHITE_REFRESH_SEQUENCE
RUNTIME_REFRESH_SEQUENCE = (
    "LOAD_SELECTED_PWR_PLL_BROADCAST",
    "LOAD_SELECTED_R20_R21_CS1",
    "LOAD_SAME_SELECTED_R20_R21_CS2",
    "FULL_CODE7_DTM_PRESTAGE_CS1_NO_REFRESH",
    "FULL_CODE7_DTM_PRESTAGE_CS2_NO_REFRESH",
    "PTLW_CS1_INCLUSIVE_ONCE",
    "CROPPED_TARGET_DTM_CS1",
    "PTLW_CS2_INCLUSIVE_ONCE",
    "CROPPED_TARGET_DTM_CS2",
    "PON_BUSY_COMPLETE_60S_GATE",
    "DRF_00_BUSY_COMPLETE_60S_GATE",
    "POF_00_BUSY_COMPLETE_60S_GATE",
)

PRELOAD_DTM = bytes([0x77]) * CONTROLLER_DTM_BYTES
PRELOAD_DTM_SHA256 = identity.sha256(PRELOAD_DTM)
PRELOAD_DTM_FNV1A = identity.fnv1a(PRELOAD_DTM)
TARGET_DTMS = tuple(
    bytes([(code << 4) | code]) * byte_count
    for code, byte_count in zip(TARGET_CODES, CROPPED_DTM_BYTES, strict=True)
)
TARGET_DTM_SHA256 = tuple(identity.sha256(payload) for payload in TARGET_DTMS)
TARGET_DTM_FNV1A = tuple(identity.fnv1a(payload) for payload in TARGET_DTMS)
COMBINED_DTMS = tuple(PRELOAD_DTM + payload for payload in TARGET_DTMS)
COMBINED_DTM_SHA256 = tuple(identity.sha256(payload) for payload in COMBINED_DTMS)
COMBINED_DTM_FNV1A = tuple(identity.fnv1a(payload) for payload in COMBINED_DTMS)


def ptlw_payload(window: identity.Window) -> bytes:
    identity.validate_window(window)
    x_end = window.x + window.width - 1
    y_end = window.y + window.height - 1
    return bytes(
        (
            window.x >> 8,
            window.x & 0xFF,
            x_end >> 8,
            x_end & 0xFF,
            window.y >> 8,
            window.y & 0xFF,
            y_end >> 8,
            y_end & 0xFF,
            0x01,
        )
    )


PTLW_PAYLOADS = tuple(ptlw_payload(window) for window in WINDOWS)


def _assert_geometry() -> None:
    if TARGET_CODES != (0, 0, 2):
        raise RuntimeError("true-R20 candidate codes drifted")
    for window in WINDOWS:
        identity.validate_window(window)
    for left_index, left in enumerate(WINDOWS):
        for right in WINDOWS[left_index + 1 :]:
            if not (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            ):
                raise RuntimeError("true-R20 windows overlap")
    if any(value != 9_600 for value in CROPPED_DTM_BYTES):
        raise RuntimeError("true-R20 crop geometry drifted")
    if PRELOAD_DTM_SHA256 != clean.PRELOAD_DTM_SHA256:
        raise RuntimeError("clean PTLW code7 prestage identity drifted")
    if PROFILE_ACTIVE["tuple_sha256"] == PROFILE_COMMENTED["tuple_sha256"]:
        raise RuntimeError("active/commented complete tuples unexpectedly match")


def _descriptor(item: Mapping[str, Any]) -> str:
    value = {
        "schema": "mf1750-runtime-lut-true-r20-partial-hold-descriptor-v1",
        "variant": VARIANT_KEY,
        "profile_id": PROFILE_ID,
        "batch1_evidence_requirements_id": BATCH1_EVIDENCE_REQUIREMENTS_ID,
        "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
        "per_action_readiness_qualification": deepcopy(
            PER_ACTION_READINESS_QUALIFICATION
        ),
        "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
        **item,
    }
    return identity.sha256(identity.canonical(value))


def _action_id(ordinal: int, descriptor_id: str) -> str:
    return identity.sha256(
        (
            "MF1750_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_ACTION_V1|"
            f"{VARIANT_KEY}|{ordinal}|{descriptor_id}"
        ).encode("ascii")
    )


def _build_actions() -> list[dict[str, Any]]:
    _assert_geometry()
    white_frame = bytes([0x11]) * FRAME_BYTES
    logical_frame = bytearray([0x77]) * FRAME_BYTES
    actions: list[dict[str, Any]] = []
    for ordinal, (role, branch, profile_name) in enumerate(
        zip(ROLES, BRANCHES, PROFILE_SEQUENCE, strict=True), 1
    ):
        is_white = ordinal == 4
        if is_white:
            dtm = identity.uniform_identity(FACTORY_WHITE_CODE, CONTROLLER_DTM_BYTES)
            action: dict[str, Any] = {
                "ordinal": ordinal,
                "role": role,
                "branch": branch,
                "window": None,
                "candidate_code": None,
                "palette_source": "FACTORY_OTP",
                "tuple_name": None,
                "cs1_tuple_sha256": None,
                "cs2_tuple_sha256": None,
                "dtm_transport": "FACTORY_OTP_PACKED_FULL_FRAME_0X11",
                "ptlw_payload_hex": None,
                "ptlw_writes_per_controller": 0,
                "runtime_code7_prestage": False,
                "refresh_sequence": list(WHITE_REFRESH_SEQUENCE),
                "frame": identity.frame_identity(white_frame),
                "prestage_dtm": None,
                "target_dtm": deepcopy(dtm),
                "cs1_dtm": deepcopy(dtm),
                "cs2_dtm": deepcopy(dtm),
            }
        else:
            index = ordinal - 1
            window = WINDOWS[index]
            identity.set_rect(logical_frame, window)
            profile = PROFILES[str(profile_name)]
            prestage = {
                "bytes": CONTROLLER_DTM_BYTES,
                "fnv1a": PRELOAD_DTM_FNV1A,
                "sha256": PRELOAD_DTM_SHA256,
            }
            target = {
                "bytes": CROPPED_DTM_BYTES[index],
                "fnv1a": TARGET_DTM_FNV1A[index],
                "sha256": TARGET_DTM_SHA256[index],
            }
            combined = {
                "bytes": CONTROLLER_DTM_BYTES + CROPPED_DTM_BYTES[index],
                "fnv1a": COMBINED_DTM_FNV1A[index],
                "sha256": COMBINED_DTM_SHA256[index],
            }
            action = {
                "ordinal": ordinal,
                "role": role,
                "branch": branch,
                "window": asdict(window),
                "candidate_code": TARGET_CODES[index],
                "candidate_mapping_status": "REQUIRES_BATCH1_EVIDENCE",
                "palette_source": "L535_RUNTIME_COMPLETE_TUPLE",
                "tuple_name": profile_name,
                "cs1_tuple_sha256": profile["tuple_sha256"],
                "cs2_tuple_sha256": profile["tuple_sha256"],
                "complete_tuple": deepcopy(profile),
                "dtm_transport": (
                    "FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP"
                ),
                "ptlw_payload_hex": PTLW_PAYLOADS[index].hex(),
                "ptlw_writes_per_controller": 1,
                "runtime_code7_prestage": True,
                "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
                "frame": identity.frame_identity(bytes(logical_frame)),
                "prestage_dtm": prestage,
                "target_dtm": target,
                "cs1_dtm": deepcopy(combined),
                "cs2_dtm": deepcopy(combined),
            }
        descriptor_id = _descriptor(deepcopy(action))
        action["descriptor_id"] = descriptor_id
        action["action_id"] = _action_id(ordinal, descriptor_id)
        actions.append(action)
    return actions


def _action_summary(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "ordinal",
        "role",
        "palette_source",
        "tuple_name",
        "candidate_code",
        "cs1_tuple_sha256",
        "cs2_tuple_sha256",
        "dtm_transport",
        "descriptor_id",
        "action_id",
    )
    return [{key: item.get(key) for key in keys} for item in actions]


def build_report() -> dict[str, Any]:
    """Return immutable V1 action and contract identities without I/O."""

    actions = _build_actions()
    contract = {
        "schema": "mf1750-runtime-lut-true-r20-partial-hold-contract-v1",
        "variant": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profiles": deepcopy(PROFILES),
        "profile_sequence": list(PROFILE_SEQUENCE),
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "ptlw_command": "0x83",
            "ptlw_endpoint": "inclusive",
            "ptlw_mode": 1,
            "windows": [asdict(window) for window in WINDOWS],
            "ptlw_payloads_hex": [payload.hex() for payload in PTLW_PAYLOADS],
        },
        "actions": _action_summary(actions),
        "external_factory_white_anchor_required": True,
        "factory_otp_white_recovery_ordinal": 4,
        "batch1_evidence_requirements": deepcopy(BATCH1_EVIDENCE_REQUIREMENTS),
        "batch1_evidence_requirements_id": BATCH1_EVIDENCE_REQUIREMENTS_ID,
        "live_execution_blocked_without_batch1_evidence": True,
        "candidate_codes_are_not_colour_names": True,
        "historical_global_header_only_cross_lut": False,
        "complete_tuple_switched_per_runtime_action": True,
        "both_controllers_receive_same_tuple_per_runtime_action": True,
        "clean_ptlw_transport": {
            "mechanical_source_contract_id": clean.CONTRACT_ID,
            "runtime_code7_full_dtm_prestage": True,
            "runtime_code7_prestage_no_refresh": True,
            "runtime_code7_prestage_bytes_per_controller": CONTROLLER_DTM_BYTES,
            "runtime_code7_prestage_sha256": PRELOAD_DTM_SHA256,
            "ptlw_writes_per_controller_per_runtime_action": 1,
            "cropped_target_dtm_bytes_per_controller": list(CROPPED_DTM_BYTES),
            "target_dtm_sha256": list(TARGET_DTM_SHA256),
            "combined_dtm_sha256": list(COMBINED_DTM_SHA256),
            "refresh_sequence": list(RUNTIME_REFRESH_SEQUENCE),
            "action_stage_cdi": False,
            "action_stage_btst2": False,
            "repeat_ptlw_after_pon_busy": False,
            "command_0x86": False,
            "extra_dtm_prefix_or_suffix_byte": False,
        },
        "qualifier_v2_prerequisite": deepcopy(QUALIFIER_V2_PREREQUISITE),
        "qualifier_v2_prerequisite_bundle_id": QUALIFIER_V2_BUNDLE_ID,
        "per_action_readiness_qualification": deepcopy(
            PER_ACTION_READINESS_QUALIFICATION
        ),
        "busy_admission_contract": deepcopy(BUSY_ADMISSION_CONTRACT),
        "runtime_lut": True,
        "factory_otp": True,
        "partial_refresh": True,
        "cross_palette_hold_probe": True,
        "same_palette_hold_probe": False,
        "full_screen_factory_white_actions": True,
        "runtime_transport_codes": list(TARGET_CODES),
        "spatial_dither": False,
        "autochain": False,
        "retry": False,
        "automatic_recovery": False,
        "mid_refresh_power_cut": False,
    }
    contract_id = identity.sha256(identity.canonical(contract))
    return {
        "schema_version": 1,
        "kind": f"{DEVICE_KIND_PREFIX}-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "profile_id": PROFILE_ID,
        "contract_id": contract_id,
        "actions": actions,
        "contract": contract,
    }


CONTRACT_ID = "38698de14b6a2a7a96e072d4de025cb0708ae167b81c348f6c4337dc3654eb63"
DESCRIPTOR_IDS = (
    "4d317d9f0a96a85c8ba30fb52c3661d47fa7b7de3dcc7ef35fccd7dbd869e8a5",
    "07e0cdff9718da18f7dbfa084ce41b7af7b0b7a0c9591ca57453b962984f055e",
    "000f0991160242f035fee116b37342597b79f38d41cd2011e50cab40ce94aa14",
    "b86d3418fe0edda32b960b67eb56439ee7a0c392c40349eb0a9d960ab4365c20",
)
ACTION_IDS = (
    "9dde1d9805c5c08880a7cce3be4844faacdafe3e250de1a8dc8b2bbda8a17a48",
    "cef8f2bb0ddd3ec96c2929a754b22a403fcb38e34ff7278ef2fb4c83ea1ea29f",
    "ef7996a165effed3fff26dc1595b6a484f3abab06ed73ae4e9faeaeb72a56444",
    "fd50aee18578d0d91a542471728883b9c3a2df24f0ed35d2298dfda71bbcd6bf",
)
_REPORT = build_report()
if _REPORT["contract_id"] != CONTRACT_ID:
    raise RuntimeError("true-R20 contract identity drifted")
if tuple(item["descriptor_id"] for item in _REPORT["actions"]) != DESCRIPTOR_IDS:
    raise RuntimeError("true-R20 descriptor identities drifted")
if tuple(item["action_id"] for item in _REPORT["actions"]) != ACTION_IDS:
    raise RuntimeError("true-R20 action identities drifted")


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
