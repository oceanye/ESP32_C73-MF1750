#!/usr/bin/env python3
"""Build the offline daylight camera-assist plan for the fresh T3/W4 pair.

This module is deliberately incapable of camera, network, serial, relay,
flashing, reset, or display I/O.  It binds the already frozen T3 atlas and W4
factory-white artifacts to a fail-closed observation sequence that can be
executed by the existing narrow live tools on a later, attended session.

The camera is a coarse evidence source only.  The plan never promotes its
result to absolute colour, a formal colour gate, or a qualified palette.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as t3,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as w4,
)


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-t3-camera-w4-daylight-plan-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-with-integrity-null"
PLAN_REVISION = "t3-daylight-camera-assist-w4-containment-v3-outcome-gated"
PARTIAL_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-w4-daylight-partial-dual-3x8-plan-v1"
)
PARTIAL_PLAN_REVISION = "t3-partial-dual-3x8-top-rows-v1"
PARTIAL_MODE = "PARTIAL_DUAL_3X8_TOP_ROWS_V1"
PARTIAL_OUTPUT_ROOT = (
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
    "CAMERA_PARTIAL_DUAL_3X8_V1"
)

TARGET_CAMERA = {
    "friendly_name": "48MP USB Camera",
    "logical_id": "USB_VID_32E4_PID_4801",
    "usb_vid": "32E4",
    "usb_pid": "4801",
    "directshow_usb_token": "vid_32e4&pid_4801",
    "excluded_camera": {
        "friendly_name": "dual-lens USB Camera",
        "usb_vid": "1BCF",
        "usb_pid": "0B15",
    },
    "identity_rule": (
        "EXACT_UNIQUE_DIRECTSHOW_VID_PID_AND_FRIENDLY_NAME_BEFORE_AND_AFTER_FRAME"
    ),
    "opencv_index_is_identity": False,
}

# README camera.md is the current project-level formal still-capture profile.
# The separate fresh-V2 exposure=-3 lock is intentionally not imported here:
# T3 has no such camera contract, and white/atlas evidence must not mix profiles.
CAMERA_PROFILE = {
    "fourcc": "MJPG",
    "frame_width": 4000,
    "frame_height": 3000,
    "fps": 15.0,
    "autofocus": 0.0,
    "focus": 79.0,
    "auto_exposure": 0.25,
    "exposure": -6.0,
    "auto_white_balance": 0.0,
    "white_balance_temperature": 4600.0,
    "warmup_frames": 8,
    "require_every_setting_write": True,
    "require_effective_settings_equal_before_after": True,
    "source": "README camera.md / MF1750 formal fixed still profile",
    "fresh_v2_exposure_minus_3_profile_permitted": False,
}

OUTPUT_ROOT = (
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_CAMERA_DAYLIGHT_V1"
)
W4_POST_WHITE_OUTPUT_ROOT = (
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
    "WHITE_CAMERA_DAYLIGHT_V1"
)
T3_CAPTURE_TOOL = "tools/mf1750_raw_p16_crossover_t3_camera_capture_pack.py"
W4_POST_WHITE_CAPTURE_TOOL = (
    "tools/mf1750_raw_p16_crossover_w4_post_white_camera_capture.py"
)
CAMERA_EVIDENCE_TOOL = "tools/mf1750_camera_capture_evidence.py"
CAMERA_OBSERVATION_TOOL = (
    "tools/mf1750_raw_p16_crossover_t3_profile_following_camera_observation.py"
)
HUMAN_OBSERVATION_TOOL = (
    "tools/mf1750_raw_p16_crossover_profile_following_human_observation.py"
)
CA_HUMAN_REFERENCE = (
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2/"
    "human-observation-ca-v2-v1.json"
)


class DaylightPlanError(RuntimeError):
    """Raised when the offline plan or a bound artifact is inconsistent."""


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(value)
    root["integrity"] = None
    digest = sha256_bytes(canonical_json(root))
    root["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": digest,
    }
    return root


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DaylightPlanError(f"{label} must be a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise DaylightPlanError(f"cannot read {label}: {error}") from error
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or after.st_size != len(payload):
        raise DaylightPlanError(f"{label} changed while being read")
    return payload


def _artifact_binding(
    path: Path, declared: Mapping[str, int | str], *, role: str
) -> dict[str, Any]:
    payload = _read_stable_regular(path, label=role)
    expected_bytes = int(declared[f"{role}_bytes"])
    expected_sha256 = str(declared[f"{role}_sha256"])
    if len(payload) != expected_bytes or sha256_bytes(payload) != expected_sha256:
        raise DaylightPlanError(f"{role} artifact differs from frozen declaration")
    return {
        "path": path.resolve().as_posix(),
        "bytes": len(payload),
        "sha256": expected_sha256,
        "verified_from_disk": True,
    }


def _source_binding(relative_path: str) -> dict[str, Any]:
    path = (REPO_ROOT / relative_path).resolve()
    payload = _read_stable_regular(path, label=f"source {relative_path}")
    return {
        "path": relative_path,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "verified_from_disk": True,
    }


def _ca_human_reference_binding() -> dict[str, Any]:
    """Deep-validate and bind the already sealed T2/CA human baseline."""

    path = (REPO_ROOT / CA_HUMAN_REFERENCE).resolve()
    payload = _read_stable_regular(path, label="T2/CA human reference")
    try:
        root, validated_payload = human.validate_observation(path)
    except human.HumanObservationError as error:
        raise DaylightPlanError(f"T2/CA human reference rejected: {error}") from error
    if validated_payload != payload:
        raise DaylightPlanError("T2/CA human reference changed during validation")
    derived = root.get("derived_observation")
    if not isinstance(derived, Mapping):
        raise DaylightPlanError("T2/CA human reference lacks derived observation")
    if (
        root.get("stage") != "t2-ca-coarse-discovery-successor-v2"
        or derived.get("reported_ca_baseline_match") is not True
        or derived.get("replicate_summary", {}).get(
            "all_four_replicates_consistent_and_stable"
        )
        is not True
        or derived.get("control_summary", {}).get("all_controls_pass") is not True
    ):
        raise DaylightPlanError("T2/CA human reference is not screening-ready")
    return {
        "path": CA_HUMAN_REFERENCE,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "canonical_integrity_sha256": root["integrity"]["sha256"],
        "stage": root["stage"],
        "profile_map": deepcopy(root["profile_map"]),
        "reported_ca_baseline_match": True,
        "four_replicates_consistent_and_stable": True,
        "controls_pass": True,
        "formal_comparison_ready": bool(derived.get("comparison_ready")),
        "human_screen_reference_ready": True,
        "verified_from_disk": True,
    }


def _firmware_binding(
    *,
    report: Mapping[str, Any],
    action: Mapping[str, Any],
    artifacts: Mapping[str, int | str],
    paths: tuple[Path, Path],
    role: str,
) -> dict[str, Any]:
    bin_path, elf_path = paths
    return {
        "role": role,
        "campaign_id": report["contract"]["campaign_id"],
        "test_id": report["contract"]["test_id"],
        "build_tag": report["contract"]["build_tag"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "base_route": report["contract"]["base_route"],
        "nvs_namespace": report["contract"]["nvs_namespace"],
        "nvs_key": report["contract"]["nvs_key"],
        "bin": _artifact_binding(bin_path, artifacts, role="bin"),
        "elf": _artifact_binding(elf_path, artifacts, role="elf"),
    }


def _steps() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": 1,
            "id": "SETUP_ONLY_CAMERA_VIEW_GATE",
            "kind": "CAMERA_READ_ONLY",
            "requires": [
                "J2_COMMANDED_OFF",
                "W3_CLEAN_WHITE_AUTHORITY_DEEP_VALID",
                "EXACT_48MP_CAMERA_ENUMERATED",
                "FULL_PANEL_VISIBLE_UNCROPPED",
            ],
            "success": "SETUP_FRAME_SHOWS_FULL_PANEL_AND_USABLE_ILLUMINATION",
            "maximum_attempts": 2,
            "formal_evidence": False,
            "consumes_formal_capture_attempt": False,
            "may_supply_formal_panel_corners": False,
            "failure": "STOP_WITH_J2_OFF_AND_RETAIN_WHITE",
        },
        {
            "ordinal": 2,
            "id": "ACQUIRE_W3_PRE_WHITE",
            "kind": "CAMERA_READ_ONLY_TWO_PHASE_ACQUIRE",
            "requires": [
                "J2_COMMANDED_OFF",
                "SETUP_VIEW_GATE_PASS",
                "CAMERA_MOUNT_AND_LIGHTING_FROZEN",
            ],
            "success": "ONE_W3_JPEG_AND_SIDECAR_IMMUTABLY_ACQUIRED_PENDING_ADMISSION",
            "maximum_attempts": 2,
            "attempt_claim_timing": "BEFORE_CAMERA_OPEN",
            "panel_corners_required_at_acquire": False,
            "automatic_retry": False,
            "failure": "STOP_WITH_J2_OFF_AND_RETAIN_WHITE",
        },
        {
            "ordinal": 3,
            "id": "ADMIT_W3_PRE_WHITE_FROM_SAME_JPEG",
            "kind": "OFFLINE_GEOMETRY_AND_WHITE_ADMISSION",
            "requires": [
                "W3_ACQUISITION_IMMUTABLY_SEALED",
                "TL_TR_BR_BL_READ_FROM_THAT_EXACT_JPEG",
            ],
            "success": "ONE_EXACT_48MP_PRE_WHITE_FRAME_ADMITTED",
            "camera_access": 0,
            "same_jpeg_corner_binding_required": True,
            "failure": "FORMAL_ATTEMPT_REJECTED_STOP_WITH_J2_OFF_NO_AUTO_RETRY",
        },
        {
            "ordinal": 4,
            "id": "INSTALL_AND_DIAGNOSE_T3",
            "kind": "APP_ONLY_FLASH_AND_GET_ONLY_DIAGNOSTIC",
            "requires": ["J2_COMMANDED_OFF", "PRE_WHITE_FRAME_ADMITTED"],
            "success": "T3_APP_VERIFY_AND_4_GET_DIAGNOSTIC_PASS",
            "mutation_budget": {
                "app_only_flash": 1,
                "write_before": "default_reset",
                "write_after": "no_reset",
                "verify_before": "no_reset",
                "verify_after": "hard_reset",
                "application_boot_after_write": 1,
                "extra_or_manual_reset": 0,
                "http_get": 4,
                "http_post": 0,
                "claim": 0,
                "visible_refresh": 0,
            },
            "failure": "STOP_WITH_J2_OFF",
        },
        {
            "ordinal": 5,
            "id": "EXECUTE_T3_ONCE",
            "kind": "ONE_VISIBLE_REFRESH",
            "requires": [
                "T3_DIAGNOSTIC_PASS",
                "RELAY_ON_EXACT_BOUND",
                "CURRENT_T3_RAW_BUSY_EQUALS_1_READ_ONLY",
            ],
            "busy_gate_placement": (
                "INSIDE_FROZEN_RUNNER_AFTER_EXACT_4_GET_AND_BEFORE_CLAIM_ARM_POST"
            ),
            "independent_pause_after_busy_gate_available": False,
            "success": "T3_COMPLETE_EXACTLY_ONE_DRIVER_AND_VISIBLE_REFRESH",
            "mutation_budget": {
                "arm": 1,
                "execute": 1,
                "driver": 1,
                "visible_refresh": 1,
                "retry": 0,
                "recovery": 0,
                "autochain": 0,
            },
            "failure": "PROTECTIVE_RELAY_OFF_AND_STOP",
        },
        {
            "ordinal": 6,
            "id": "POWER_OFF_AND_ENTER_T3_CAPTURE_HOLD",
            "kind": "EXACT_BOUND_RELAY_OFF_AND_RETAINED_STATE_GATE",
            "requires": ["T3_ACTION_COMPLETE"],
            "success": "T3_ATLAS_RETAINED_WITH_RELAY_COMMANDED_OFF",
            "camera_access": 0,
            "failure": "PROTECTIVE_RELAY_OFF_FAILED_STOP_NO_CAPTURE",
        },
        {
            "ordinal": 7,
            "id": "ACQUIRE_ADMIT_T3_SEQUENTIALLY",
            "kind": "REPEATED_TWO_PHASE_ACQUIRE_ADMIT_WITH_RELAY_OFF",
            "requires": [
                "T3_ATLAS_RETAINED",
                "RELAY_OFF_EXACT_BOUND",
            ],
            "success": "THREE_EXACT_48MP_T3_FRAMES_ADMITTED",
            "required_frames": 3,
            "maximum_capture_attempts": 5,
            "attempt_claim_timing": "BEFORE_EACH_CAMERA_OPEN",
            "panel_corners_required_at_acquire": False,
            "same_jpeg_corner_binding_required": True,
            "sequence_rule": (
                "EACH_ACQUIRE_MUST_REACH_ONE_TERMINAL_ADMIT_RESULT_BEFORE_"
                "THE_NEXT_ACQUIRE"
            ),
            "automatic_retry": False,
            "failure": (
                "KEEP_RELAY_OFF_RETAIN_ATLAS_DO_NOT_INSTALL_OR_EXECUTE_W4_ASK_OPERATOR"
            ),
        },
        {
            "ordinal": 8,
            "id": "SEAL_T3_CAPTURE_SET",
            "kind": "OFFLINE_VALIDATION",
            "requires": [
                "PRE_WHITE_FRAME_DEEP_VALID",
                "THREE_T3_FRAMES_DEEP_VALID",
                "SAME_EXACT_CAMERA_PATH_MOUNT_PROFILE_AND_4000X3000_GEOMETRY",
                "ALL_CAPTURE_OUTPUTS_O_EXCL",
            ],
            "success": "CAPTURE_BYTES_AND_SIDECARS_SEALED",
            "analysis_is_w4_gate": False,
            "failure": "KEEP_RELAY_OFF_RETAIN_ATLAS_ASK_OPERATOR",
        },
        {
            "ordinal": 9,
            "id": "SCREEN_T3_AND_BIND_HUMAN_DECISION_INPUT",
            "kind": "OFFLINE_CAMERA_SCREEN_WITH_CONDITIONAL_HUMAN_SEED",
            "requires": [
                "T3_CAPTURE_SET_SEALED",
                "T2_CA_HUMAN_SCREEN_REFERENCE_DEEP_VALID",
            ],
            "success": (
                "CAMERA_STABILITY_QUALITY_REPORT_WRITTEN_AND_IF_PRIMARY_"
                "PROFILE_DECISION_IS_REQUIRED_CURRENT_T3_HUMAN_SEED_SEALED"
            ),
            "camera_only_classification_ceiling_without_human_seed": (
                "HUMAN_CAMERA_SCREEN_REVIEW"
            ),
            "camera_only_may_decide_profile_vs_physical_side": False,
            "human_seed_may_be_completed_from": (
                "RETAINED_T3_ATLAS_OR_ITS_EXACT_SEALED_JPEGS"
            ),
            "w4_safety_containment_blocked_by_missing_human_seed": False,
            "failure": (
                "RECORD_REVIEW_KEEP_PRIMARY_DECISION_PENDING_THEN_ALLOW_"
                "EXPLICIT_W4_SAFETY_CONTAINMENT"
            ),
        },
        {
            "ordinal": 10,
            "id": "INSTALL_AND_DIAGNOSE_W4",
            "kind": "APP_ONLY_FLASH_AND_GET_ONLY_DIAGNOSTIC",
            "requires": [
                "J2_COMMANDED_OFF",
                "T3_CAPTURE_SET_SEALED",
                "W4_SOURCE_QUARTET_EQUALS_EXECUTED_T3",
            ],
            "success": "W4_APP_VERIFY_AND_4_GET_DIAGNOSTIC_PASS",
            "mutation_budget": {
                "app_only_flash": 1,
                "write_before": "default_reset",
                "write_after": "no_reset",
                "verify_before": "no_reset",
                "verify_after": "hard_reset",
                "application_boot_after_write": 1,
                "extra_or_manual_reset": 0,
                "http_get": 4,
                "http_post": 0,
                "claim": 0,
                "visible_refresh": 0,
            },
            "failure": "STOP_WITH_J2_OFF_ATLAS_RETAINED",
        },
        {
            "ordinal": 11,
            "id": "EXECUTE_W4_WHITE_ONCE",
            "kind": "ONE_VISIBLE_REFRESH",
            "requires": [
                "W4_DIAGNOSTIC_PASS",
                "RELAY_ON_EXACT_BOUND",
                "CURRENT_W4_RAW_BUSY_EQUALS_1_READ_ONLY",
            ],
            "busy_gate_placement": (
                "INSIDE_FROZEN_RUNNER_AFTER_EXACT_4_GET_AND_BEFORE_CLAIM_ARM_POST"
            ),
            "independent_pause_after_busy_gate_available": False,
            "success": "W4_COMPLETE_EXACTLY_ONE_FACTORY_OTP_WHITE_REFRESH",
            "mutation_budget": {
                "arm": 1,
                "execute": 1,
                "driver": 1,
                "visible_refresh": 1,
                "retry": 0,
                "recovery": 0,
                "autochain": 0,
            },
            "failure": "PROTECTIVE_RELAY_OFF_AND_STOP",
        },
        {
            "ordinal": 12,
            "id": "POWER_OFF_AND_ACQUIRE_W4_WHITE",
            "kind": "RELAY_OFF_THEN_CAMERA_READ_ONLY_TWO_PHASE_ACQUIRE",
            "requires": ["W4_ACTION_COMPLETE", "RELAY_OFF_EXACT_BOUND"],
            "success": "ONE_W4_WHITE_JPEG_AND_SIDECAR_IMMUTABLY_ACQUIRED",
            "maximum_attempts": 2,
            "attempt_claim_timing": "BEFORE_CAMERA_OPEN",
            "panel_corners_required_at_acquire": False,
            "automatic_retry": False,
            "failure": (
                "KEEP_RELAY_OFF_RECORD_CAMERA_FAILURE_AND_REQUEST_MANUAL_WHITE_CHECK"
            ),
        },
        {
            "ordinal": 13,
            "id": "ADMIT_AND_SEAL_W4_WHITE_FROM_SAME_JPEG",
            "kind": "OFFLINE_GEOMETRY_WHITE_AND_RESIDUAL_ADMISSION",
            "requires": [
                "W4_WHITE_ACQUISITION_IMMUTABLY_SEALED",
                "TL_TR_BR_BL_READ_FROM_THAT_EXACT_JPEG",
            ],
            "success": ("ONE_EXACT_48MP_POST_WHITE_FRAME_CLASSIFIED_PASS_AND_SEALED"),
            "camera_access": 0,
            "same_jpeg_corner_binding_required": True,
            "pass_only_admission_and_seal": True,
            "review_or_fail_terminal_state": "REJECTED",
            "review_or_fail_may_consume_explicit_second_attempt": True,
            "failure": (
                "KEEP_RELAY_OFF_USE_REMAINING_EXPLICIT_ATTEMPT_OR_REQUEST_"
                "MANUAL_WHITE_CHECK"
            ),
        },
        {
            "ordinal": 14,
            "id": "ANALYZE_AND_REPORT_OFFLINE",
            "kind": "OFFLINE_CAMERA_ASSIST",
            "requires": ["T3_CAPTURE_SET_SEALED"],
            "success": (
                "CAMERA_QUALITY_RESULT_AND_WHEN_T3_HUMAN_OBSERVATION_EXISTS_"
                "CA_VS_AC_HUMAN_PROFILE_SCREEN_RESULT"
            ),
            "may_run_after_w4": True,
            "camera_only_primary_profile_decision": "NOT_EARNED",
            "failure": "REPORT_REVIEW_NEVER_SYNTHESIZE_A_COLOUR_CLAIM",
        },
    ]


def build_plan() -> dict[str, Any]:
    """Build and deep-bind the deterministic offline execution plan."""

    t3_validation = t3.dry_validate(verify_authorities=True)
    w4_validation = w4.dry_validate(verify_source=True)
    if t3_validation.get("result") != "PASS" or w4_validation.get("result") != "PASS":
        raise DaylightPlanError("T3 or W4 offline validation did not PASS")

    t3_report = t3.build_report()
    t3_action = t3_report["actions"][0]
    w4_report = w4.build_white_report()
    w4_action = w4_report["action"]
    ca_human_reference = _ca_human_reference_binding()
    source_quartet = {
        "campaign_id": t3_report["contract"]["campaign_id"],
        "contract_id": t3_report["contract_id"],
        "descriptor_id": t3_action["descriptor_id"],
        "action_id": t3_action["action_id"],
    }
    w4_source_quartet = {
        "campaign_id": w4_action["source_campaign_id"],
        "contract_id": w4_action["source_contract_id"],
        "descriptor_id": w4_action["source_descriptor_id"],
        "action_id": w4_action["source_action_id"],
    }
    if source_quartet != w4_source_quartet:
        raise DaylightPlanError("W4 does not bind the exact T3 source quartet")

    t3_firmware = _firmware_binding(
        report=t3_report,
        action=t3_action,
        artifacts=t3.ARTIFACTS[t3.STAGE],
        paths=t3.artifact_paths(),
        role="T3_PROFILE_FOLLOWING_ATLAS",
    )
    w4_firmware = _firmware_binding(
        report=w4_report,
        action=w4_action,
        artifacts=w4.WHITE_ARTIFACTS[w4.STAGE],
        paths=w4.white_artifact_paths(),
        role="W4_FACTORY_OTP_WHITE",
    )
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "plan_revision": PLAN_REVISION,
        "offline_only": True,
        "hardware_accessed": False,
        "camera_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "current_inherited_state": {
            "j2_commanded": "OFF",
            "screen": "W3_CLEAN_WHITE_RETAINED",
            "electrical_state_proven": False,
            "operator_present": False,
            "offline_preparation_only": True,
        },
        "source_authorities": {
            "w3_clean_white_action": t3_report["contract"]["pre_white_action_evidence"],
            "w3_clean_white_human_authority": t3_report["contract"][
                "pre_white_authority"
            ],
            "t2_ca_human_screen_reference": ca_human_reference,
        },
        "firmware": {
            "t3": t3_firmware,
            "w4": w4_firmware,
            "w4_exact_t3_source_quartet": source_quartet,
        },
        "camera_contract": {
            # Never leak the mutable module-level declarations into a returned
            # plan.  Otherwise a caller could mutate one built plan and
            # silently change the reference used by a later deterministic
            # rebuild.
            "target": deepcopy(TARGET_CAMERA),
            "profile": deepcopy(CAMERA_PROFILE),
            "mount_id": "BOUND_AT_FIRST_PRE_WHITE_CAPTURE_AND_FROZEN_FOR_SESSION",
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "capture_binding": "locked_retained_two_phase_acquire_then_admit",
            "formal_capture_protocol": (
                "CLAIM_BEFORE_CAMERA_OPEN__ACQUIRE_IMMUTABLE_JPEG_SIDECAR__"
                "ADMIT_CORNERS_FROM_SAME_JPEG"
            ),
            "setup_only_view_gate": {
                "required_before_formal_w3": True,
                "formal_evidence": False,
                "may_supply_formal_corners": False,
                "maximum_attempts": 2,
            },
            "formal_attempt_claimed_before_camera_open": True,
            "panel_corners_bound_after_acquisition_to_same_photo": True,
            "pre_white_required_frames": 1,
            "t3_required_frames": 3,
            "post_white_required_frames": 1,
            "total_required_frames": 5,
            "output_write_contract": "O_EXCL",
            "output_root": OUTPUT_ROOT,
            "t3_capture_tool": T3_CAPTURE_TOOL,
            "post_white_output_root": W4_POST_WHITE_OUTPUT_ROOT,
            "post_white_capture_tool": W4_POST_WHITE_CAPTURE_TOOL,
            "implementation_sources": {
                "t3_capture_pack": _source_binding(T3_CAPTURE_TOOL),
                "w4_post_white_capture": _source_binding(W4_POST_WHITE_CAPTURE_TOOL),
                "camera_evidence": _source_binding(CAMERA_EVIDENCE_TOOL),
                "camera_observation": _source_binding(CAMERA_OBSERVATION_TOOL),
                "human_observation_and_comparison": _source_binding(
                    HUMAN_OBSERVATION_TOOL
                ),
            },
        },
        "state_machine": {
            "ordered": True,
            "automatic_chaining_between_visible_actions": False,
            "explicit_resume_required_before_each_visible_action": True,
            "total_visible_refresh_budget": 2,
            "t3_visible_refresh_budget": 1,
            "w4_visible_refresh_budget": 1,
            "visible_action_retry_budget": 0,
            "visible_action_recovery_budget": 0,
            "visible_action_autochain_budget": 0,
            "bounded_camera_attempts_are_read_only_not_action_retries": True,
            "capture_bytes_seal_required_before_w4": True,
            "camera_classification_required_before_w4": False,
            "human_profile_decision_required_before_w4": False,
            "failed_t3_capture_preserves_atlas_with_relay_off": True,
            "relay_off_receipt_is_electrical_state_proof": False,
            "runner_busy_gate": {
                "placement": (
                    "INSIDE_FROZEN_RUNNER_AFTER_EXACT_4_GET_AND_BEFORE_CLAIM_ARM_POST"
                ),
                "raw_busy_required": 1,
                "busy_zero_fails_before_claim_or_post": True,
                "independent_pause_subcommand_available": False,
            },
            "steps": _steps(),
        },
        "camera_screening": {
            "classification_vocabulary": [
                "HUMAN_CAMERA_SCREEN_PASS",
                "HUMAN_CAMERA_SCREEN_REVIEW",
                "HUMAN_CAMERA_SCREEN_FAIL",
            ],
            "low_confidence_result": "HUMAN_CAMERA_SCREEN_REVIEW",
            "camera_only_ceiling_without_truthful_t3_human_seed": (
                "HUMAN_CAMERA_SCREEN_REVIEW"
            ),
            "camera_only_may_answer_profile_vs_physical_side": False,
            "absolute_colour_claimed": False,
            "formal_colour_gate_evaluated": False,
            "qualified_colour_count": 0,
            "profile_following_proven": False,
            "required_checks": {
                "panel_geometry": "64_CELLS_AND_TWO_4X8_HALVES",
                "replicates": "FOUR_PER_CONTROLLER_CODE",
                "temporal_frames": 3,
                "controls": [2, 3, 5],
                "artifacts": [
                    "BOTTOM_EDGE_ANOMALY",
                    "STRIPE",
                    "RESIDUAL",
                    "SEAM",
                    "CLIPPING",
                    "FOCUS_OR_GEOMETRY_FAILURE",
                ],
            },
            "coarse_thresholds": {
                "white_reference_min_lstar": 25.0,
                "valid_replicates_per_group_per_frame": 3,
                "valid_frames_per_group": 2,
                "position_delta_e00_pass_max": 8.0,
                "position_delta_e00_review_max": 12.0,
                "temporal_delta_e76_pass_max": 3.0,
                "temporal_delta_e76_review_max": 6.0,
                "hue_span_degrees_pass_max": 35.0,
                "hue_span_degrees_review_max": 60.0,
                "bottom_edge_dark_excess_percentage_points": 15.0,
                "bottom_edge_longest_dark_run_fraction": 0.5,
            },
            "human_escalation": {
                "required_for_review": True,
                "required_for_primary_profile_vs_side_decision": True,
                "required_for_ambiguous_warm_colours": True,
                "required_for_any_absolute_colour_name": True,
                "camera_can_override_human_observation": False,
            },
        },
        "decision_objectives": {
            "primary_question": (
                "DO_REPRODUCIBLE_CODE_APPEARANCES_FOLLOW_PROFILE_A_OR_C_"
                "WHEN_THE_COMPLETE_PROFILES_SWAP_CONTROLLERS"
            ),
            "comparison_unit": (
                "CONTROLLER_PROFILE_CODE_WITH_FOUR_POSITION_REPLICATES_"
                "AND_THREE_TEMPORAL_FRAMES"
            ),
            "reference_t2_profile_assignment": "CS1_C__CS2_A",
            "candidate_t3_profile_assignment": "CS1_A__CS2_C",
            "earning_rule": (
                "CAMERA_ONLY_EARNS_STABILITY_AND_QUALITY__PROFILE_VS_SIDE_"
                "REQUIRES_CURRENT_T3_HUMAN_CATEGORICAL_OBSERVATION_COMPARED_"
                "WITH_BOUND_T2_CA_HUMAN_REFERENCE"
            ),
            "camera_only_primary_decision": "NOT_EARNED",
            "decision_branches": {
                "PROFILE_FOLLOWING_CANDIDATE": (
                    "APPEARANCES_MOVE_WITH_A_AND_C_AND_REPLICATES_ARE_STABLE"
                ),
                "PHYSICAL_SIDE_FOLLOWING": (
                    "APPEARANCES_REMAIN_WITH_CS1_OR_CS2_DESPITE_PROFILE_SWAP"
                ),
                "UNSTABLE_OR_CONFOUNDED": (
                    "REPLICATES_OR_TEMPORAL_FRAMES_FAIL_STABILITY_OR_QUALITY_GATES"
                ),
            },
            "secondary_quality_question": (
                "ARE_BOTTOM_EDGES_STRIPES_SEAMS_RESIDUALS_AND_GEOMETRY_ACCEPTABLE"
            ),
            "absolute_colour_or_palette_qualification_claimed": False,
            "qualified_colour_count": 0,
        },
        "tomorrow_terminal_conditions": {
            "normal": (
                "T3_EVIDENCE_SEALED_W4_ACTION_COMPLETE_AND_POST_WHITE_CAMERA_"
                "PASS_OR_EXPLICIT_MANUAL_CLEAN_WHITE_CONFIRMATION_RELAY_"
                "COMMANDED_OFF"
            ),
            "capture_failure": "T3_ATLAS_RETAINED_RELAY_COMMANDED_OFF_WAIT_OPERATOR",
            "action_fault": "RELAY_COMMANDED_OFF_STOP_NO_RETRY",
        },
        "validation": {
            "t3_offline_validation": t3_validation,
            "w4_offline_validation": w4_validation,
            "artifacts_rehashed_from_disk": True,
            "source_quartet_exact": True,
        },
        "integrity": None,
    }
    return _seal(root)


def build_partial_plan() -> dict[str, Any]:
    """Build the independent fixed-camera dual-side partial-ROI plan."""

    root = deepcopy(build_plan())
    legacy_coarse_thresholds = deepcopy(
        root["camera_screening"]["coarse_thresholds"]
    )
    root["integrity"] = None
    root["kind"] = PARTIAL_KIND
    root["plan_revision"] = PARTIAL_PLAN_REVISION
    root["mode"] = PARTIAL_MODE
    root["current_inherited_state"]["camera_position_change_required"] = False
    root["current_inherited_state"]["full_screen_framing_required"] = False

    camera_contract = root["camera_contract"]
    camera_contract.update(
        {
            "coverage_scope": "partial_panel",
            "full_panel_visible": False,
            "full_panel_uncropped": False,
            "fixed_camera_position_must_not_move": True,
            "geometry_mode": PARTIAL_MODE,
            "selected_controllers": ["CS1", "CS2"],
            "selected_rows": [0, 1, 2],
            "selected_columns": list(range(8)),
            "selected_cells_per_frame": 48,
            "replicates_per_code_per_controller_per_frame": 3,
            "full_panel_corners_required": False,
            "dual_controller_blocks_bound_after_acquisition_to_same_photo": True,
            "outside_selected_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "pre_white_required_frames": 1,
            "t3_required_frames": 3,
            "post_white_required_frames": 0,
            "total_required_frames": 4,
            "output_root": PARTIAL_OUTPUT_ROOT,
            "post_white_output_root": None,
            "post_white_capture_tool": None,
            "w4_post_white_camera_seal_authorized": False,
        }
    )
    camera_contract["setup_only_view_gate"] = {
        "required_before_partial_w3": False,
        "full_screen_test_required": False,
        "camera_reposition_permitted": False,
        "operator_may_choose_two_visible_local_blocks": True,
        "formal_evidence": False,
        "may_supply_partial_blocks": False,
        "maximum_attempts": 0,
    }
    camera_contract.pop("panel_corners_bound_after_acquisition_to_same_photo", None)

    state_machine = root["state_machine"]
    state_machine.update(
        {
            "partial_bundle_may_enable_safe_w4_white_containment_action": True,
            "partial_bundle_earns_w4_post_white_camera_seal": False,
            "w4_post_white_camera_capture_authorized": False,
            "partial_roi_may_be_promoted_to_full_panel_evidence": False,
        }
    )
    for step in state_machine["steps"]:
        step_id = step["id"]
        if step_id == "SETUP_ONLY_CAMERA_VIEW_GATE":
            step.update(
                {
                    "id": "SELECT_FIXED_DUAL_PARTIAL_ROIS_OFFLINE",
                    "kind": "OFFLINE_PARTIAL_ROI_SELECTION",
                    "requires": ["CAMERA_POSITION_FIXED_AND_UNCHANGED"],
                    "success": "BOTH_CONTROLLER_TOP_3X8_BLOCKS_VISIBLE",
                    "full_screen_test_required": False,
                    "camera_access": 0,
                    "failure": "STOP_IF_EITHER_CONTROLLER_3X8_BLOCK_IS_NOT_VISIBLE",
                }
            )
        elif step_id == "ACQUIRE_W3_PRE_WHITE":
            step.update(
                {
                    "success": "ONE_PARTIAL_W3_JPEG_SEALED_AWAITING_DUAL_BLOCKS",
                    "coverage_scope": "partial_panel",
                    "full_panel_required": False,
                }
            )
        elif step_id == "ADMIT_W3_PRE_WHITE_FROM_SAME_JPEG":
            step.update(
                {
                    "success": "ONE_W3_DUAL_3X8_PARTIAL_REFERENCE_ACCEPTED",
                    "geometry": "TWO_CURRENT_PHOTO_CONTROLLER_BLOCKS",
                    "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
                }
            )
        elif step_id == "ACQUIRE_ADMIT_T3_SEQUENTIALLY":
            step.update(
                {
                    "success": "THREE_T3_DUAL_3X8_PARTIAL_FRAMES_ACCEPTED",
                    "geometry": "TWO_CURRENT_PHOTO_CONTROLLER_BLOCKS_PER_FRAME",
                    "replicates_per_code_per_controller_per_frame": 3,
                }
            )
        elif step_id == "SEAL_T3_CAPTURE_SET":
            step.update(
                {
                    "success": "PARTIAL_T3_CAPTURE_SET_SEALED",
                    "formal_full_panel_evidence": False,
                    "profile_following_decision_earned": False,
                    "w4_post_white_camera_seal_earned": False,
                }
            )
        elif step_id == "SCREEN_T3_AND_BIND_HUMAN_DECISION_INPUT":
            step.update(
                {
                    "success": "PARTIAL_PROFILE_CODE_COMPARISON_REPORTED",
                    "formal_profile_following_decision": "NOT_EARNED",
                    "full_panel_screen": "NOT_EVALUATED",
                    "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
                }
            )
        elif step_id == "POWER_OFF_AND_ACQUIRE_W4_WHITE":
            step.update(
                {
                    "kind": "NOT_AUTHORIZED_IN_PARTIAL_MODE",
                    "authorized": False,
                    "camera_access": 0,
                    "success": "NOT_EARNED_IN_PARTIAL_MODE",
                    "failure": "NO_W4_POST_WHITE_CAMERA_CAPTURE_REQUESTED",
                }
            )
        elif step_id == "ADMIT_AND_SEAL_W4_WHITE_FROM_SAME_JPEG":
            step.update(
                {
                    "kind": "NOT_AUTHORIZED_IN_PARTIAL_MODE",
                    "authorized": False,
                    "camera_access": 0,
                    "success": "NOT_EARNED_IN_PARTIAL_MODE",
                    "failure": "NO_W4_POST_WHITE_CAMERA_SEAL_CREATED",
                    "pass_only_admission_and_seal": False,
                }
            )
        elif step_id == "ANALYZE_AND_REPORT_OFFLINE":
            step.update(
                {
                    "requires": ["PARTIAL_T3_CAPTURE_SET_SEALED"],
                    "success": "PARTIAL_CAMERA_PROFILE_CODE_SCREEN_REPORTED",
                    "camera_only_primary_profile_decision": "NOT_EARNED",
                }
            )

    root["camera_screening"] = {
        "mode": PARTIAL_MODE,
        "classification_vocabulary": [
            "PARTIAL_CAMERA_SCREEN_PASS",
            "PARTIAL_CAMERA_SCREEN_REVIEW",
            "PARTIAL_CAMERA_SCREEN_FAIL",
        ],
        "low_confidence_result": "PARTIAL_CAMERA_SCREEN_REVIEW",
        "camera_only_may_answer_profile_vs_physical_side": False,
        "profile_code_pair_comparison_available": True,
        "absolute_colour_claimed": False,
        "formal_colour_gate_evaluated": False,
        "formal_full_panel_evidence": False,
        "full_panel_geometry_evaluated": False,
        "profile_following_proven": False,
        "profile_following_decision_earned": False,
        "w4_post_white_full_screen_seal_earned": False,
        "qualified_colour_count": 0,
        "required_checks": {
            "panel_geometry": "TWO_CONTROLLER_TOP_3X8_BLOCKS",
            "selected_rows": [0, 1, 2],
            "selected_columns": list(range(8)),
            "selected_cell_count_per_frame": 48,
            "replicates": "THREE_PER_CONTROLLER_CODE_PER_FRAME",
            "temporal_frames": 3,
            "profile_code_pairs": list(range(8)),
            "normalization": "SAME_SIDE_SAME_CELL_W3_WHITE",
            "raw_cross_side_rgb_equality_gate": False,
            "bottom_edge": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "row_3": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
        },
        "geometry_gates": {
            "minimum_block_side_px": 240.0,
            "minimum_projected_cell_side_px": 24.0,
            "minimum_projected_cell_area_px2": 1500.0,
            "maximum_cross_capture_corner_rms_px": 8.0,
            "maximum_cross_capture_corner_px": 15.0,
            "automatic_roi_expansion": False,
        },
        "coarse_thresholds": legacy_coarse_thresholds,
        "evidence_boundary": {
            "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "partial_pass_is_descriptive_only": True,
            "partial_pass_may_not_be_promoted_to_formal_full_panel": True,
            "partial_pass_may_not_earn_profile_following": True,
            "partial_pass_may_not_earn_w4_camera_seal": True,
        },
    }
    root["camera_screening"]["coarse_thresholds"][
        "valid_replicates_per_group_per_frame"
    ] = 3

    root["decision_objectives"].update(
        {
            "comparison_unit": (
                "CONTROLLER_PROFILE_CODE_WITH_THREE_SELECTED_POSITION_REPLICATES_"
                "AND_THREE_TEMPORAL_FRAMES"
            ),
            "earning_rule": (
                "PARTIAL_CAMERA_DATA_MAY_REPORT_PROFILE_CODE_DIFFERENCES_ONLY__"
                "FORMAL_PROFILE_FOLLOWING_REQUIRES_A_SEPARATE_FULL_EVIDENCE_PATH"
            ),
            "camera_only_primary_decision": "NOT_EARNED",
            "formal_profile_following_decision": "NOT_EARNED_IN_PARTIAL_MODE",
            "full_panel_quality_question": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "absolute_colour_or_palette_qualification_claimed": False,
            "qualified_colour_count": 0,
        }
    )
    root["tomorrow_terminal_conditions"] = {
        "normal": (
            "PARTIAL_T3_EVIDENCE_SEALED_AND_OPTIONAL_SAFE_W4_WHITE_CONTAINMENT_"
            "ACTION_COMPLETE_RELAY_COMMANDED_OFF__NO_W4_CAMERA_SEAL_EARNED"
        ),
        "capture_failure": "T3_ATLAS_RETAINED_RELAY_COMMANDED_OFF_WAIT_OPERATOR",
        "action_fault": "RELAY_COMMANDED_OFF_STOP_NO_RETRY",
        "formal_full_panel_evidence": "NOT_EARNED",
        "profile_following_decision": "NOT_EARNED",
        "w4_post_white_camera_seal": "NOT_EARNED",
    }
    root["validation"]["partial_mode_contract"] = {
        "selected_rows": [0, 1, 2],
        "selected_columns": list(range(8)),
        "selected_cells_per_frame": 48,
        "replicates_per_code_per_controller_per_frame": 3,
        "full_panel_legacy_plan_mutated": False,
    }
    return _seal(root)


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-validate a plan against the current frozen offline sources."""

    expected = build_plan()
    if dict(value) != expected:
        raise DaylightPlanError("daylight plan differs from deterministic rebuild")
    return expected


def validate_partial_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-validate the independent partial plan."""

    expected = build_partial_plan()
    if dict(value) != expected:
        raise DaylightPlanError(
            "partial daylight plan differs from deterministic rebuild"
        )
    return expected


def load_and_validate(path: Path) -> dict[str, Any]:
    payload = _read_stable_regular(path, label="daylight plan")
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise DaylightPlanError(
            f"daylight plan is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise DaylightPlanError("daylight plan root must be an object")
    return validate_plan(value)


def load_and_validate_partial(path: Path) -> dict[str, Any]:
    payload = _read_stable_regular(path, label="partial daylight plan")
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise DaylightPlanError(
            f"partial daylight plan is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise DaylightPlanError("partial daylight plan root must be an object")
    return validate_partial_plan(value)


def write_plan(path: Path) -> dict[str, Any]:
    value = build_plan()
    payload = (
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        )
    except FileExistsError as error:
        raise DaylightPlanError(
            f"refusing to overwrite existing plan: {path}"
        ) from error
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return load_and_validate(path)


def write_partial_plan(path: Path) -> dict[str, Any]:
    value = build_partial_plan()
    payload = (
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        )
    except FileExistsError as error:
        raise DaylightPlanError(
            f"refusing to overwrite existing partial plan: {path}"
        ) from error
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return load_and_validate_partial(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    write = commands.add_parser("write")
    write.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    commands.add_parser("describe-partial")
    write_partial = commands.add_parser("write-partial")
    write_partial.add_argument("--output", type=Path, required=True)
    validate_partial = commands.add_parser("validate-partial")
    validate_partial.add_argument("--plan", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            value = build_plan()
        elif args.command == "write":
            value = write_plan(args.output)
        elif args.command == "validate":
            value = load_and_validate(args.plan)
        elif args.command == "describe-partial":
            value = build_partial_plan()
        elif args.command == "write-partial":
            value = write_partial_plan(args.output)
        else:
            value = load_and_validate_partial(args.plan)
    except DaylightPlanError as error:
        print(
            json.dumps(
                {
                    "kind": "mf1750-t3-camera-w4-daylight-plan-error",
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
