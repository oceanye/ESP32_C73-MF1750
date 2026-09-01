"""Build deterministic, offline-only fixed-frame execution bundles.

This module is the bridge between :class:`MultiLutHoldSchedule` and a future
fixed-firmware code generator.  It deliberately does not compile firmware and
contains no device, network, serial, relay, reset, flash, refresh, or runtime
LUT/payload entry point.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from host.epd_frame import validate_frame

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_json_bytes,
    canonical_sha256,
    prepare_empty_output_dir,
    require_exact_keys,
    require_sha256,
    require_text,
    verify_integrity,
)
from .history_palette import QualificationLevel, TRANSPORT_CODES
from .multi_lut_hold_schedule import (
    Controller,
    LutHoldCapability,
    MultiLutHoldSchedule,
    MultiLutRecipe,
    PassPhase,
    ScheduledPass,
)


SCHEMA_VERSION = 1
SOURCE_WHITE_KIND = "MF1750_SEALED_SOURCE_WHITE_AUTHORITY_SUMMARY"
WHITE_SUCCESSOR_KIND = "MF1750_INDEPENDENT_FACTORY_WHITE_SUCCESSOR_REQUIREMENT"
MANIFEST_KIND = "MF1750_F7_FIXED_STATIC_PHOTO_EXECUTION_BUNDLE"
DESCRIPTOR_KIND = "MF1750_F7_FIXED_STATIC_PHOTO_PASS_DESCRIPTOR"
ACTION_KIND = "MF1750_F7_MANUAL_ONE_SHOT_ACTION_IDENTITY"
CODEGEN_KIND = "MF1750_F7_FIXED_FRAME_CODEGEN_READY_METADATA"
_SAFE_SYMBOL = re.compile(r"[^A-Za-z0-9_]+")


class FixedPhotoExecutionError(ValueError):
    """Raised when a fixed-photo bundle boundary differs."""


def _contract_error(error: Exception) -> FixedPhotoExecutionError:
    return FixedPhotoExecutionError(str(error))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixedPhotoExecutionError(f"{label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    try:
        return require_text(value, label)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error


def _sha(value: object, label: str) -> str:
    try:
        return require_sha256(value, label)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return attach_integrity(unsigned)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error


def _verify_seal(mapping: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        return verify_integrity(mapping, label)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error


def _require_keys(mapping: Mapping[str, Any], expected: set[str], label: str) -> None:
    try:
        require_exact_keys(mapping, expected, label)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error


def _validate_source_white_unsigned(unsigned: Mapping[str, Any]) -> None:
    _require_keys(
        unsigned,
        {
            "schema_version",
            "kind",
            "authority_id",
            "source_action_id",
            "source_descriptor_id",
            "evidence_file_sha256",
            "controllers",
            "factory_otp_white_complete",
            "screen_clean_white_observed",
            "sealed_offline_evidence",
            "live_authority",
        },
        "source-white authority summary",
    )
    if (
        unsigned.get("schema_version") != SCHEMA_VERSION
        or unsigned.get("kind") != SOURCE_WHITE_KIND
    ):
        raise FixedPhotoExecutionError("source-white authority identity differs")
    _text(unsigned.get("authority_id"), "authority_id")
    _text(unsigned.get("source_action_id"), "source_action_id")
    _text(unsigned.get("source_descriptor_id"), "source_descriptor_id")
    _sha(unsigned.get("evidence_file_sha256"), "evidence_file_sha256")
    if unsigned.get("controllers") != [Controller.CS1.value, Controller.CS2.value]:
        raise FixedPhotoExecutionError(
            "source-white authority must cover CS1 and CS2 separately"
        )
    if (
        unsigned.get("factory_otp_white_complete") is not True
        or unsigned.get("screen_clean_white_observed") is not True
        or unsigned.get("sealed_offline_evidence") is not True
        or unsigned.get("live_authority") is not False
    ):
        raise FixedPhotoExecutionError("source-white authority gates differ")


def seal_source_white_authority_summary(
    unsigned_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and canonically seal a completed source-white evidence summary."""

    if "integrity" in unsigned_summary:
        raise FixedPhotoExecutionError("source-white summary is already sealed")
    _validate_source_white_unsigned(unsigned_summary)
    return _seal(unsigned_summary)


def _validate_source_white(mapping: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = _verify_seal(mapping, "source-white authority summary")
    _validate_source_white_unsigned(unsigned)
    return unsigned


def _validate_successor_unsigned(unsigned: Mapping[str, Any]) -> None:
    _require_keys(
        unsigned,
        {
            "schema_version",
            "kind",
            "requirement_id",
            "required_successor_kind",
            "required",
            "independent",
            "must_follow_final_photo_pass",
            "identity_owner",
            "identity_status",
            "one_shot_required",
            "autochain_allowed",
            "live_authority",
        },
        "white-successor requirement",
    )
    if (
        unsigned.get("schema_version") != SCHEMA_VERSION
        or unsigned.get("kind") != WHITE_SUCCESSOR_KIND
        or unsigned.get("required_successor_kind")
        != "INDEPENDENT_FACTORY_OTP_WHITE_ONE_SHOT"
    ):
        raise FixedPhotoExecutionError("white-successor requirement identity differs")
    _text(unsigned.get("requirement_id"), "requirement_id")
    if (
        unsigned.get("required") is not True
        or unsigned.get("independent") is not True
        or unsigned.get("must_follow_final_photo_pass") is not True
        or unsigned.get("identity_owner") != "EXTERNAL_SUCCESSOR_MODULE"
        or unsigned.get("identity_status") != "REQUIRED_NOT_ASSIGNED_HERE"
        or unsigned.get("one_shot_required") is not True
        or unsigned.get("autochain_allowed") is not False
        or unsigned.get("live_authority") is not False
    ):
        raise FixedPhotoExecutionError("white-successor requirement gates differ")


def seal_white_successor_requirement(
    unsigned_requirement: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and seal an external, intentionally identity-free white gate."""

    if "integrity" in unsigned_requirement:
        raise FixedPhotoExecutionError("white-successor requirement is already sealed")
    _validate_successor_unsigned(unsigned_requirement)
    return _seal(unsigned_requirement)


def _validate_successor(mapping: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = _verify_seal(mapping, "white-successor requirement")
    _validate_successor_unsigned(unsigned)
    return unsigned


def _ready_recipe(recipe: MultiLutRecipe) -> bool:
    reproducible = recipe.fresh_white_reconstruction_qualified or (
        recipe.identical_target_repeat_qualified and recipe.target_repeat_count >= 2
    )
    return (
        recipe.qualification_level is QualificationLevel.QUALIFIED
        and reproducible
        and recipe.local_hold_qualified
        and recipe.factory_white_recovery_qualified
    )


def _phase_value(
    recipe: MultiLutRecipe, phase: PassPhase, repeat_index: int | None, hold: int
) -> int:
    if phase is PassPhase.SOURCE:
        return recipe.source_code
    if phase is PassPhase.MIDDLE:
        return recipe.middle_code if recipe.middle_code is not None else hold
    if phase is PassPhase.TARGET:
        return recipe.target_code
    if repeat_index is not None and recipe.target_repeat_count >= repeat_index:
        return recipe.target_code
    return hold


def _unpack_frame(frame: bytes, width: int, height: int) -> bytes:
    pixels = bytearray(width * height)
    target = 0
    for packed in frame:
        pixels[target] = packed >> 4
        pixels[target + 1] = packed & 0x0F
        target += 2
    return bytes(pixels)


def _pass_groups(
    schedule: MultiLutHoldSchedule,
) -> list[tuple[str, tuple[ScheduledPass, ...]]]:
    groups: list[tuple[str, tuple[ScheduledPass, ...]]] = []
    offset = 0
    for profile in schedule.profile_order:
        selected: list[ScheduledPass] = []
        while offset < len(schedule.passes):
            item = schedule.passes[offset]
            if item.lut_profile_id != profile:
                break
            selected.append(item)
            offset += 1
        if not selected:
            raise FixedPhotoExecutionError("profile has no scheduled passes")
        groups.append((profile, tuple(selected)))
    if offset != len(schedule.passes):
        raise FixedPhotoExecutionError("pass profile order differs from schedule")
    return groups


def _validate_phase_group(profile: str, passes: Sequence[ScheduledPass]) -> None:
    phases = [item.phase for item in passes]
    if not phases or phases[0] is not PassPhase.SOURCE:
        raise FixedPhotoExecutionError(f"{profile} must begin with source")
    cursor = 1
    if cursor < len(phases) and phases[cursor] is PassPhase.MIDDLE:
        cursor += 1
    if cursor >= len(phases) or phases[cursor] is not PassPhase.TARGET:
        raise FixedPhotoExecutionError(f"{profile} must contain one target pass")
    if passes[cursor].target_repeat_index != 1:
        raise FixedPhotoExecutionError("target pass repeat index differs")
    cursor += 1
    expected_repeat = 2
    while cursor < len(phases):
        if (
            phases[cursor] is not PassPhase.TARGET_REPEAT
            or passes[cursor].target_repeat_index != expected_repeat
        ):
            raise FixedPhotoExecutionError("target-repeat order differs")
        expected_repeat += 1
        cursor += 1
    for item in passes:
        if item.phase in {PassPhase.SOURCE, PassPhase.MIDDLE}:
            if item.target_repeat_index is not None:
                raise FixedPhotoExecutionError("non-target repeat index differs")


def _validate_pixel_histories(
    schedule: MultiLutHoldSchedule,
    profile: str,
    passes: Sequence[ScheduledPass],
    capability: LutHoldCapability,
) -> dict[int, int]:
    unpacked = [
        _unpack_frame(item.packed_frame, schedule.width, schedule.height)
        for item in passes
    ]
    selected_recipe_by_pixel: dict[int, int] = {}
    active_masks = [bytearray(schedule.width * schedule.height) for _ in passes]
    for controller in Controller:
        hold = capability.hold_code(controller)
        recipes = [
            (index, recipe)
            for index, recipe in enumerate(schedule.recipes)
            if recipe.controller is controller
            and recipe.lut_profile_id == profile
            and _ready_recipe(recipe)
        ]
        expected_patterns: dict[tuple[int, ...], list[tuple[int, tuple[int, ...]]]] = {}
        for recipe_index, recipe in recipes:
            pattern = tuple(
                _phase_value(recipe, item.phase, item.target_repeat_index, hold)
                for item in passes
            )
            activity = tuple(
                int(
                    item.phase is not PassPhase.MIDDLE or recipe.middle_code is not None
                )
                if item.phase is not PassPhase.TARGET_REPEAT
                else int(
                    item.target_repeat_index is not None
                    and recipe.target_repeat_count >= item.target_repeat_index
                )
                for item in passes
            )
            expected_patterns.setdefault(pattern, []).append((recipe_index, activity))
        hold_pattern = tuple(hold for _ in passes)
        x_range = (
            range(0, schedule.width // 2)
            if controller is Controller.CS1
            else range(schedule.width // 2, schedule.width)
        )
        for y in range(schedule.height):
            for x in x_range:
                pixel = y * schedule.width + x
                observed = tuple(frame[pixel] for frame in unpacked)
                matches = expected_patterns.get(observed, [])
                if observed == hold_pattern:
                    if matches:
                        raise FixedPhotoExecutionError(
                            "packed-frame history is ambiguous between READY recipe "
                            "and HOLD; assignment/hash cannot be verified"
                        )
                    continue
                if not matches:
                    raise FixedPhotoExecutionError(
                        "packed-frame history is not produced by a READY "
                        f"{controller.value}/{profile} recipe or HOLD"
                    )
                recipe_indices = {recipe_index for recipe_index, _ in matches}
                activity_patterns = {activity for _, activity in matches}
                if len(recipe_indices) != 1 or len(activity_patterns) != 1:
                    raise FixedPhotoExecutionError(
                        "packed-frame history maps to multiple READY recipes; "
                        "assignment/hash cannot be verified"
                    )
                recipe_index = next(iter(recipe_indices))
                activity = next(iter(activity_patterns))
                selected_recipe_by_pixel[pixel] = recipe_index
                for pass_index, active in enumerate(activity):
                    active_masks[pass_index][pixel] = active
    for item, active_mask in zip(passes, active_masks):
        if sum(active_mask) != item.active_pixel_count:
            raise FixedPhotoExecutionError(
                "active pixel count differs from packed history"
            )
        if hashlib.sha256(active_mask).hexdigest() != item.active_mask_sha256:
            raise FixedPhotoExecutionError(
                "active mask SHA-256 differs from packed history"
            )
    return selected_recipe_by_pixel


def _validate_schedule(schedule: MultiLutHoldSchedule) -> dict[str, Any]:
    if not isinstance(schedule, MultiLutHoldSchedule):
        raise FixedPhotoExecutionError(
            "schedule must be a MultiLutHoldSchedule produced offline"
        )
    if (
        type(schedule.width) is not int
        or type(schedule.height) is not int
        or schedule.width <= 0
        or schedule.height <= 0
        or schedule.width % 2
    ):
        raise FixedPhotoExecutionError("schedule geometry differs")
    _sha(schedule.recipe_assignment_sha256, "recipe_assignment_sha256")
    if not schedule.profile_order or len(schedule.profile_order) != len(
        set(schedule.profile_order)
    ):
        raise FixedPhotoExecutionError("schedule profile order differs")
    if not schedule.passes:
        raise FixedPhotoExecutionError("schedule contains no passes")
    if any(not isinstance(item, MultiLutRecipe) for item in schedule.recipes):
        raise FixedPhotoExecutionError("schedule recipes differ")
    if any(not isinstance(item, LutHoldCapability) for item in schedule.capabilities):
        raise FixedPhotoExecutionError("schedule capabilities differ")
    if tuple(item.lut_profile_id for item in schedule.capabilities) != tuple(
        schedule.profile_order
    ):
        raise FixedPhotoExecutionError("capability/profile order differs")
    capability_by_profile = {
        item.lut_profile_id: item for item in schedule.capabilities
    }
    committed: list[str] = []
    groups = _pass_groups(schedule)
    selected_recipe_by_pixel: dict[int, int] = {}
    for profile, passes in groups:
        capability = capability_by_profile[profile]
        if (
            not capability.baseline_hold_qualified
            or not capability.local_hold_qualified
            or not set(committed).issubset(capability.retains_profile_ids)
        ):
            raise FixedPhotoExecutionError("profile HOLD/retention gate differs")
        _validate_phase_group(profile, passes)
        for item in passes:
            if not isinstance(item, ScheduledPass):
                raise FixedPhotoExecutionError("schedule pass type differs")
            if item.ordinal < 1 or item.ordinal > len(schedule.passes):
                raise FixedPhotoExecutionError("schedule pass ordinal differs")
            if item.committed_profiles_before != tuple(committed):
                raise FixedPhotoExecutionError(
                    "schedule committed_profiles_before differs"
                )
            if type(item.packed_frame) is not bytes:
                raise FixedPhotoExecutionError("packed frame must be immutable bytes")
            try:
                validate_frame(
                    item.packed_frame,
                    schedule.width,
                    schedule.height,
                    allowed_colors=TRANSPORT_CODES,
                )
            except Exception as error:
                raise FixedPhotoExecutionError(
                    f"packed frame contract differs: {error}"
                ) from error
            if hashlib.sha256(item.packed_frame).hexdigest() != _sha(
                item.packed_frame_sha256, "packed_frame_sha256"
            ):
                raise FixedPhotoExecutionError("packed frame SHA-256 differs")
            _sha(item.active_mask_sha256, "active_mask_sha256")
            if (
                type(item.active_pixel_count) is not int
                or not 1 <= item.active_pixel_count <= schedule.width * schedule.height
            ):
                raise FixedPhotoExecutionError("active pixel count differs")
        selected = _validate_pixel_histories(schedule, profile, passes, capability)
        overlap = set(selected_recipe_by_pixel).intersection(selected)
        if overlap:
            raise FixedPhotoExecutionError(
                "one pixel selects READY recipes from multiple LUT profiles"
            )
        selected_recipe_by_pixel.update(selected)
        committed.append(profile)
    expected_pixel_count = schedule.width * schedule.height
    if set(selected_recipe_by_pixel) != set(range(expected_pixel_count)):
        raise FixedPhotoExecutionError(
            "packed histories do not reconstruct one READY recipe per pixel"
        )
    reconstructed_indices = bytes(
        selected_recipe_by_pixel[pixel] for pixel in range(expected_pixel_count)
    )
    if hashlib.sha256(reconstructed_indices).hexdigest() != (
        schedule.recipe_assignment_sha256
    ):
        raise FixedPhotoExecutionError(
            "recipe assignment SHA-256 differs from packed histories"
        )
    if [item.ordinal for item in schedule.passes] != list(
        range(1, len(schedule.passes) + 1)
    ):
        raise FixedPhotoExecutionError("schedule pass order differs")
    try:
        mapping = schedule.mapping()
    except Exception as error:
        raise FixedPhotoExecutionError(f"schedule mapping failed: {error}") from error
    unsigned = _verify_seal(mapping, "multi-LUT HOLD schedule")
    if (
        unsigned.get("kind") != "MF17506_OFFLINE_MULTI_LUT_LOCAL_HOLD_SCHEDULE"
        or unsigned.get("spatial_dithering") is not False
        or unsigned.get("hardware_accessed") is not False
        or unsigned.get("live_authorized") is not False
        or unsigned.get("autochain_allowed") is not False
        or unsigned.get("independent_factory_otp_white_containment_required")
        is not True
    ):
        raise FixedPhotoExecutionError("schedule safety boundary differs")
    return mapping


def _symbol(ordinal: int) -> str:
    raw = f"mf1750_f7_pass_{ordinal:04d}_frame"
    return _SAFE_SYMBOL.sub("_", raw)


def _controller_bindings(
    schedule: MultiLutHoldSchedule,
    profile: str,
    capability: LutHoldCapability,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for controller in Controller:
        eligible = sorted(
            recipe.recipe_id
            for recipe in schedule.recipes
            if recipe.controller is controller
            and recipe.lut_profile_id == profile
            and _ready_recipe(recipe)
        )
        result.append(
            {
                "controller": controller.value,
                "lut_profile_id": profile,
                "hold_code": capability.hold_code(controller),
                "eligible_ready_recipe_ids": eligible,
                "controllers_pooled": False,
            }
        )
    return result


def _descriptor(
    schedule: MultiLutHoldSchedule,
    schedule_sha256: str,
    source_white_sha256: str,
    successor_sha256: str,
    item: ScheduledPass,
    capability: LutHoldCapability,
    frame_file: str,
) -> dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTOR_KIND,
        "schedule_canonical_sha256": schedule_sha256,
        "recipe_assignment_sha256": schedule.recipe_assignment_sha256,
        "ordinal": item.ordinal,
        "lut_profile_id": item.lut_profile_id,
        "phase": item.phase.value,
        "target_repeat_index": item.target_repeat_index,
        "committed_profiles_before": list(item.committed_profiles_before),
        "active_pixel_count": item.active_pixel_count,
        "active_mask_sha256": item.active_mask_sha256,
        "fixed_frame": {
            "file": frame_file,
            "bytes": len(item.packed_frame),
            "sha256": item.packed_frame_sha256,
            "compile_time_constant": True,
        },
        "controller_bindings": _controller_bindings(
            schedule, item.lut_profile_id, capability
        ),
        "source_white_authority_canonical_sha256": source_white_sha256,
        "white_successor_requirement_canonical_sha256": successor_sha256,
        "spatial_dithering_used": False,
        "runtime_raw_frame_allowed": False,
        "runtime_lut_selection_allowed": False,
        "runtime_payload_allowed": False,
    }
    return _seal(unsigned)


def _action(
    descriptor: Mapping[str, Any],
    *,
    predecessor_action_id: str | None,
) -> dict[str, Any]:
    descriptor_sha = _sha(
        _mapping(descriptor.get("integrity"), "descriptor integrity").get(
            "canonical_sha256"
        ),
        "descriptor canonical_sha256",
    )
    identity_input = {
        "kind": "MF1750_F7_ACTION_ID_INPUT",
        "descriptor_canonical_sha256": descriptor_sha,
        "predecessor_action_id": predecessor_action_id,
        "manual_one_shot": True,
    }
    action_id = canonical_sha256(identity_input)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTION_KIND,
        "action_id": action_id,
        "descriptor_canonical_sha256": descriptor_sha,
        "predecessor_action_id": predecessor_action_id,
        "invocation": "EXPLICIT_MANUAL_ONE_SHOT",
        "driver_call_count": 1,
        "visible_refresh_request_count": 1,
        "retry_count": 0,
        "fallback_allowed": False,
        "recovery_embedded": False,
        "autochain_allowed": False,
        "network_allowed": False,
        "relay_or_j2_control_allowed": False,
        "flash_performed_by_bundle_builder": False,
        "live_authority": False,
    }
    return _seal(unsigned)


def _json_payload(mapping: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(mapping) + b"\n"


def _build_payloads(
    schedule: MultiLutHoldSchedule,
    schedule_mapping: Mapping[str, Any],
    source_white: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    schedule_sha = _sha(
        _mapping(schedule_mapping.get("integrity"), "schedule integrity").get(
            "canonical_sha256"
        ),
        "schedule canonical_sha256",
    )
    source_sha = _sha(
        _mapping(source_white.get("integrity"), "source-white integrity").get(
            "canonical_sha256"
        ),
        "source-white canonical_sha256",
    )
    successor_sha = _sha(
        _mapping(successor.get("integrity"), "successor integrity").get(
            "canonical_sha256"
        ),
        "successor canonical_sha256",
    )
    capabilities = {item.lut_profile_id: item for item in schedule.capabilities}
    payloads: dict[str, bytes] = {}
    pass_records: list[dict[str, Any]] = []
    predecessor: str | None = None
    for item in schedule.passes:
        base = f"pass-{item.ordinal:04d}"
        frame_file = f"frames/{base}.bin"
        descriptor_file = f"descriptors/{base}.json"
        action_file = f"actions/{base}.json"
        descriptor = _descriptor(
            schedule,
            schedule_sha,
            source_sha,
            successor_sha,
            item,
            capabilities[item.lut_profile_id],
            frame_file,
        )
        action = _action(descriptor, predecessor_action_id=predecessor)
        action_id = _text(action.get("action_id"), "action_id")
        descriptor_payload = _json_payload(descriptor)
        action_payload = _json_payload(action)
        payloads[frame_file] = item.packed_frame
        payloads[descriptor_file] = descriptor_payload
        payloads[action_file] = action_payload
        pass_records.append(
            {
                "ordinal": item.ordinal,
                "lut_profile_id": item.lut_profile_id,
                "phase": item.phase.value,
                "target_repeat_index": item.target_repeat_index,
                "committed_profiles_before": list(item.committed_profiles_before),
                "frame_file": frame_file,
                "frame_sha256": item.packed_frame_sha256,
                "descriptor_file": descriptor_file,
                "descriptor_file_sha256": hashlib.sha256(
                    descriptor_payload
                ).hexdigest(),
                "descriptor_id": descriptor["integrity"]["canonical_sha256"],
                "action_file": action_file,
                "action_file_sha256": hashlib.sha256(action_payload).hexdigest(),
                "action_id": action_id,
            }
        )
        predecessor = action_id
    manifest = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": MANIFEST_KIND,
            "schedule": {
                "canonical_sha256": schedule_sha,
                "recipe_assignment_sha256": schedule.recipe_assignment_sha256,
                "width": schedule.width,
                "height": schedule.height,
                "profile_order": list(schedule.profile_order),
                "pass_count": len(schedule.passes),
            },
            "source_white_authority": {
                "authority_id": source_white["authority_id"],
                "canonical_sha256": source_sha,
            },
            "ordered_passes": pass_records,
            "white_successor_gate": {
                "requirement_id": successor["requirement_id"],
                "canonical_sha256": successor_sha,
                "required_after_ordinal": len(schedule.passes),
                "identity_status": "REQUIRED_NOT_ASSIGNED_HERE",
                "bundle_may_invent_successor_identity": False,
                "live_execution_admitted": False,
            },
            "fixed_execution_contract": {
                "one_firmware_unit_per_pass": True,
                "manual_one_shot_per_pass": True,
                "driver_calls_per_pass": 1,
                "visible_refresh_requests_per_pass": 1,
                "retry_allowed": False,
                "fallback_allowed": False,
                "recovery_embedded": False,
                "autochain_allowed": False,
                "runtime_raw_frame_allowed": False,
                "runtime_lut_or_payload_allowed": False,
            },
            "qualification_boundary": {
                "only_ready_recipe_trajectories_allowed": True,
                "new_colour_claimed": False,
                "gray_or_lightness_claimed": False,
                "spatial_dithering_used": False,
            },
            "execution_boundary": {
                "firmware_compiled": False,
                "hardware_accessed": False,
                "network_accessed": False,
                "relay_or_j2_operated": False,
                "display_refresh_requested": False,
                "live_authority_generated": False,
            },
        }
    )
    manifest_payload = _json_payload(manifest)
    payloads["EXECUTION-MANIFEST.json"] = manifest_payload
    codegen = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CODEGEN_KIND,
            "status": "READY_FOR_FIXED_FIRMWARE_CODE_GENERATION",
            "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
            "manifest_file_sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "schedule_canonical_sha256": schedule_sha,
            "ordered_units": [
                {
                    "ordinal": record["ordinal"],
                    "symbol": _symbol(record["ordinal"]),
                    "fixed_frame_file": record["frame_file"],
                    "fixed_frame_sha256": record["frame_sha256"],
                    "descriptor_id": record["descriptor_id"],
                    "action_id": record["action_id"],
                    "lut_profile_id": record["lut_profile_id"],
                    "committed_profiles_before": record["committed_profiles_before"],
                }
                for record in pass_records
            ],
            "compile_time_fixed_frames_only": True,
            "runtime_raw_frame_entry": False,
            "runtime_lut_entry": False,
            "runtime_payload_entry": False,
            "live_execution_admitted": False,
            "required_external_successor_gate": successor_sha,
            "firmware_compiled": False,
        }
    )
    payloads["CODEGEN-READY.json"] = _json_payload(codegen)
    checksum_lines = [
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(payloads.items())
    ]
    payloads["SHA256SUMS.txt"] = "".join(checksum_lines).encode("ascii")
    return payloads, manifest


def _write_payloads(output: Path, payloads: Mapping[str, bytes]) -> None:
    try:
        for directory in ("frames", "descriptors", "actions"):
            (output / directory).mkdir()
        for relative, payload in sorted(payloads.items()):
            target = output / relative
            with target.open("xb") as stream:
                stream.write(payload)
    except OSError as error:
        raise FixedPhotoExecutionError(
            f"refused or failed to create fixed bundle file: {error}"
        ) from error


def _read_json(path: Path, label: str) -> dict[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise FixedPhotoExecutionError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise FixedPhotoExecutionError(f"{label} must contain an object")
    return value


def _verify_checksum_file(root: Path, expected_names: set[str]) -> None:
    try:
        lines = (root / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise FixedPhotoExecutionError(
            f"cannot read SHA256SUMS.txt: {error}"
        ) from error
    records: dict[str, str] = {}
    for line in lines:
        if len(line) < 67 or line[64:66] != "  ":
            raise FixedPhotoExecutionError("SHA256SUMS syntax differs")
        digest, name = line[:64], line[66:]
        _sha(digest, "SHA256SUMS digest")
        if not name or name in records or "\\" in name or name.startswith("/"):
            raise FixedPhotoExecutionError("SHA256SUMS path differs")
        records[name] = digest
    if set(records) != expected_names:
        raise FixedPhotoExecutionError("SHA256SUMS file set differs")
    for name, digest in records.items():
        try:
            payload = (root / name).read_bytes()
        except OSError as error:
            raise FixedPhotoExecutionError(
                f"cannot read bundle file {name}: {error}"
            ) from error
        if hashlib.sha256(payload).hexdigest() != digest:
            raise FixedPhotoExecutionError(f"bundle file SHA-256 differs: {name}")


def verify_fixed_photo_execution_bundle(
    bundle_dir: str | Path,
    schedule: MultiLutHoldSchedule,
    source_white_authority_summary: Mapping[str, Any],
    white_successor_requirement: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-verify a bundle against the exact schedule and sealed gate inputs."""

    schedule_mapping = _validate_schedule(schedule)
    source_white = _mapping(
        source_white_authority_summary, "source_white_authority_summary"
    )
    successor = _mapping(white_successor_requirement, "white_successor_requirement")
    _validate_source_white(source_white)
    _validate_successor(successor)
    expected_payloads, expected_manifest = _build_payloads(
        schedule, schedule_mapping, source_white, successor
    )
    root = Path(bundle_dir)
    if not root.is_dir() or root.is_symlink():
        raise FixedPhotoExecutionError("bundle directory boundary differs")
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    expected_files = set(expected_payloads)
    if actual_files != expected_files:
        raise FixedPhotoExecutionError("bundle file set differs")
    _verify_checksum_file(root, expected_files - {"SHA256SUMS.txt"})
    for name, expected in expected_payloads.items():
        try:
            actual = (root / name).read_bytes()
        except OSError as error:
            raise FixedPhotoExecutionError(
                f"cannot read bundle file {name}: {error}"
            ) from error
        if actual != expected:
            raise FixedPhotoExecutionError(f"bundle content differs: {name}")
    manifest = _read_json(root / "EXECUTION-MANIFEST.json", "execution manifest")
    unsigned_manifest = _verify_seal(manifest, "execution manifest")
    if unsigned_manifest.get("kind") != MANIFEST_KIND:
        raise FixedPhotoExecutionError("execution manifest kind differs")
    codegen = _read_json(root / "CODEGEN-READY.json", "codegen metadata")
    unsigned_codegen = _verify_seal(codegen, "codegen metadata")
    if (
        unsigned_codegen.get("kind") != CODEGEN_KIND
        or unsigned_codegen.get("runtime_raw_frame_entry") is not False
        or unsigned_codegen.get("runtime_lut_entry") is not False
        or unsigned_codegen.get("runtime_payload_entry") is not False
        or unsigned_codegen.get("live_execution_admitted") is not False
    ):
        raise FixedPhotoExecutionError("codegen safety boundary differs")
    return {
        "bundle_dir": str(root.resolve()),
        "pass_count": len(schedule.passes),
        "manifest_canonical_sha256": expected_manifest["integrity"]["canonical_sha256"],
        "schedule_canonical_sha256": schedule_mapping["integrity"]["canonical_sha256"],
        "sha256sums_file_sha256": hashlib.sha256(
            expected_payloads["SHA256SUMS.txt"]
        ).hexdigest(),
        "codegen_ready": True,
        "live_execution_admitted": False,
        "live_authority_generated": False,
    }


def build_fixed_photo_execution_bundle(
    schedule: MultiLutHoldSchedule,
    source_white_authority_summary: Mapping[str, Any],
    white_successor_requirement: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write a deterministic fixed-frame bundle to a new or empty directory."""

    schedule_mapping = _validate_schedule(schedule)
    source_white = _mapping(
        source_white_authority_summary, "source_white_authority_summary"
    )
    successor = _mapping(white_successor_requirement, "white_successor_requirement")
    _validate_source_white(source_white)
    _validate_successor(successor)
    payloads, _ = _build_payloads(schedule, schedule_mapping, source_white, successor)
    try:
        output = prepare_empty_output_dir(output_dir)
    except StaticPhotoContractError as error:
        raise _contract_error(error) from error
    _write_payloads(output, payloads)
    return verify_fixed_photo_execution_bundle(
        output, schedule, source_white, successor
    )
