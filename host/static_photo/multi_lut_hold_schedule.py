"""Fail-closed offline scheduling for controller-specific multi-LUT photos.

The scheduler does not drive hardware.  It converts already-qualified,
single-pixel recipes into an ordered set of packed frames.  Pixels belonging
to the active LUT profile receive source/middle/target codes; every other
pixel receives that profile's qualified HOLD code.  Cross-profile ordering is
accepted only when the later profile explicitly retains every earlier one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any, Sequence

from host.epd_frame import HEIGHT, WIDTH, pack_pixels, validate_frame

from .common import attach_integrity
from .history_palette import QualificationLevel, TRANSPORT_CODES


class MultiLutScheduleError(ValueError):
    """Raised when a multi-LUT photo plan lacks qualified evidence."""


class Controller(str, Enum):
    CS1 = "CS1"
    CS2 = "CS2"


class PassPhase(str, Enum):
    SOURCE = "source"
    MIDDLE = "middle"
    TARGET = "target"
    TARGET_REPEAT = "target-repeat"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiLutScheduleError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise MultiLutScheduleError(f"{label} must be lowercase SHA-256")
    return text


def _code(value: object, label: str) -> int:
    if type(value) is not int or value not in TRANSPORT_CODES:
        raise MultiLutScheduleError(f"{label} must be an integer in 0..7")
    return value


@dataclass(frozen=True)
class MultiLutRecipe:
    """One controller-specific, physically qualified pixel history."""

    recipe_id: str
    controller: Controller
    lut_profile_id: str
    source_code: int
    middle_code: int | None
    target_code: int
    target_repeat_count: int
    qualification_level: QualificationLevel
    identical_target_repeat_qualified: bool
    local_hold_qualified: bool
    factory_white_recovery_qualified: bool
    measurement_artifact_sha256: str
    fresh_white_reconstruction_qualified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", _text(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self, "lut_profile_id", _text(self.lut_profile_id, "lut_profile_id")
        )
        try:
            controller = (
                self.controller
                if isinstance(self.controller, Controller)
                else Controller(self.controller)
            )
            qualification = (
                self.qualification_level
                if isinstance(self.qualification_level, QualificationLevel)
                else QualificationLevel(self.qualification_level)
            )
        except ValueError as error:
            raise MultiLutScheduleError(
                "controller or qualification level differs"
            ) from error
        object.__setattr__(self, "controller", controller)
        object.__setattr__(self, "qualification_level", qualification)
        object.__setattr__(self, "source_code", _code(self.source_code, "source_code"))
        if self.middle_code is not None:
            object.__setattr__(
                self, "middle_code", _code(self.middle_code, "middle_code")
            )
        object.__setattr__(self, "target_code", _code(self.target_code, "target_code"))
        if type(self.target_repeat_count) is not int or self.target_repeat_count < 1:
            raise MultiLutScheduleError("target_repeat_count must be positive")
        if type(self.local_hold_qualified) is not bool:
            raise MultiLutScheduleError("local_hold_qualified must be boolean")
        if type(self.identical_target_repeat_qualified) is not bool:
            raise MultiLutScheduleError(
                "identical_target_repeat_qualified must be boolean"
            )
        if type(self.fresh_white_reconstruction_qualified) is not bool:
            raise MultiLutScheduleError(
                "fresh_white_reconstruction_qualified must be boolean"
            )
        if (
            self.identical_target_repeat_qualified
            and self.fresh_white_reconstruction_qualified
        ):
            raise MultiLutScheduleError("recipe reproducibility mode is ambiguous")
        if self.fresh_white_reconstruction_qualified and self.target_repeat_count != 1:
            raise MultiLutScheduleError(
                "fresh-white reconstruction recipe requires one target per construction"
            )
        if type(self.factory_white_recovery_qualified) is not bool:
            raise MultiLutScheduleError(
                "factory_white_recovery_qualified must be boolean"
            )
        if qualification is QualificationLevel.QUALIFIED and (
            not (
                self.fresh_white_reconstruction_qualified
                or (
                    self.identical_target_repeat_qualified
                    and self.target_repeat_count >= 2
                )
            )
            or not self.local_hold_qualified
            or not self.factory_white_recovery_qualified
        ):
            raise MultiLutScheduleError(
                "qualified recipe requires fresh-white reconstruction or a valid "
                "identical-target repeat, plus local HOLD and factory-white "
                "recovery evidence"
            )
        object.__setattr__(
            self,
            "measurement_artifact_sha256",
            _sha256(
                self.measurement_artifact_sha256,
                "measurement_artifact_sha256",
            ),
        )


@dataclass(frozen=True)
class LutHoldCapability:
    """Qualified HOLD behavior for one paired CS1/CS2 LUT profile."""

    lut_profile_id: str
    cs1_hold_code: int
    cs2_hold_code: int
    baseline_hold_qualified: bool
    local_hold_qualified: bool
    retains_profile_ids: tuple[str, ...]
    qualification_artifact_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "lut_profile_id", _text(self.lut_profile_id, "lut_profile_id")
        )
        object.__setattr__(
            self, "cs1_hold_code", _code(self.cs1_hold_code, "cs1_hold_code")
        )
        object.__setattr__(
            self, "cs2_hold_code", _code(self.cs2_hold_code, "cs2_hold_code")
        )
        if type(self.baseline_hold_qualified) is not bool:
            raise MultiLutScheduleError("baseline_hold_qualified must be boolean")
        if type(self.local_hold_qualified) is not bool:
            raise MultiLutScheduleError("local_hold_qualified must be boolean")
        if not isinstance(self.retains_profile_ids, (tuple, list)):
            raise MultiLutScheduleError("retains_profile_ids must be a sequence")
        retained = tuple(
            _text(value, "retains_profile_ids item")
            for value in self.retains_profile_ids
        )
        if len(retained) != len(set(retained)) or self.lut_profile_id in retained:
            raise MultiLutScheduleError("retains_profile_ids are ambiguous")
        object.__setattr__(self, "retains_profile_ids", retained)
        object.__setattr__(
            self,
            "qualification_artifact_sha256",
            _sha256(
                self.qualification_artifact_sha256,
                "qualification_artifact_sha256",
            ),
        )

    def hold_code(self, controller: Controller) -> int:
        return (
            self.cs1_hold_code if controller is Controller.CS1 else self.cs2_hold_code
        )


@dataclass(frozen=True)
class ScheduledPass:
    ordinal: int
    lut_profile_id: str
    phase: PassPhase
    target_repeat_index: int | None
    active_pixel_count: int
    active_mask_sha256: str
    packed_frame: bytes
    packed_frame_sha256: str
    committed_profiles_before: tuple[str, ...]

    def mapping(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "lut_profile_id": self.lut_profile_id,
            "phase": self.phase.value,
            "target_repeat_index": self.target_repeat_index,
            "active_pixel_count": self.active_pixel_count,
            "active_mask_sha256": self.active_mask_sha256,
            "packed_frame_bytes": len(self.packed_frame),
            "packed_frame_sha256": self.packed_frame_sha256,
            "committed_profiles_before": list(self.committed_profiles_before),
        }


@dataclass(frozen=True)
class MultiLutHoldSchedule:
    width: int
    height: int
    profile_order: tuple[str, ...]
    passes: tuple[ScheduledPass, ...]
    recipes: tuple[MultiLutRecipe, ...]
    capabilities: tuple[LutHoldCapability, ...]
    recipe_assignment_sha256: str

    def mapping(self) -> dict[str, Any]:
        unsigned = {
            "schema_version": 1,
            "kind": "MF17506_OFFLINE_MULTI_LUT_LOCAL_HOLD_SCHEDULE",
            "width": self.width,
            "height": self.height,
            "profile_order": list(self.profile_order),
            "recipe_assignment_sha256": self.recipe_assignment_sha256,
            "recipes": [
                {
                    "recipe_id": item.recipe_id,
                    "controller": item.controller.value,
                    "lut_profile_id": item.lut_profile_id,
                    "source_code": item.source_code,
                    "middle_code": item.middle_code,
                    "target_code": item.target_code,
                    "target_repeat_count": item.target_repeat_count,
                    "qualification_level": item.qualification_level.value,
                    "identical_target_repeat_qualified": (
                        item.identical_target_repeat_qualified
                    ),
                    "fresh_white_reconstruction_qualified": (
                        item.fresh_white_reconstruction_qualified
                    ),
                    "local_hold_qualified": item.local_hold_qualified,
                    "factory_white_recovery_qualified": (
                        item.factory_white_recovery_qualified
                    ),
                    "measurement_artifact_sha256": (item.measurement_artifact_sha256),
                }
                for item in self.recipes
            ],
            "hold_capabilities": [
                {
                    "lut_profile_id": item.lut_profile_id,
                    "cs1_hold_code": item.cs1_hold_code,
                    "cs2_hold_code": item.cs2_hold_code,
                    "baseline_hold_qualified": item.baseline_hold_qualified,
                    "local_hold_qualified": item.local_hold_qualified,
                    "retains_profile_ids": list(item.retains_profile_ids),
                    "qualification_artifact_sha256": (
                        item.qualification_artifact_sha256
                    ),
                }
                for item in self.capabilities
            ],
            "passes": [item.mapping() for item in self.passes],
            "single_pixel_recipes_only": True,
            "spatial_dithering": False,
            "hardware_accessed": False,
            "live_authorized": False,
            "autochain_allowed": False,
            "independent_factory_otp_white_containment_required": True,
        }
        return attach_integrity(unsigned)


def _controller_for_pixel(pixel: int, width: int) -> Controller:
    return Controller.CS1 if pixel % width < width // 2 else Controller.CS2


def _frame_for_pass(
    recipes: Sequence[MultiLutRecipe],
    indices: bytes,
    capability: LutHoldCapability,
    profile_id: str,
    phase: PassPhase,
    repeat_index: int | None,
    *,
    width: int,
    height: int,
) -> tuple[bytes, bytes]:
    codes = bytearray(width * height)
    active = bytearray(width * height)
    for pixel, recipe_index in enumerate(indices):
        recipe = recipes[recipe_index]
        controller = _controller_for_pixel(pixel, width)
        codes[pixel] = capability.hold_code(controller)
        if recipe.lut_profile_id != profile_id:
            continue
        selected: int | None
        if phase is PassPhase.SOURCE:
            selected = recipe.source_code
        elif phase is PassPhase.MIDDLE:
            selected = recipe.middle_code
        elif phase is PassPhase.TARGET:
            selected = recipe.target_code
        else:
            selected = (
                recipe.target_code
                if repeat_index is not None
                and recipe.target_repeat_count >= repeat_index
                else None
            )
        if selected is not None:
            codes[pixel] = selected
            active[pixel] = 1
    if not any(active):
        raise MultiLutScheduleError("scheduled pass has no active pixels")
    frame = pack_pixels(codes, width, height, allowed_colors=TRANSPORT_CODES)
    validate_frame(frame, width, height, allowed_colors=TRANSPORT_CODES)
    return frame, bytes(active)


def build_multi_lut_hold_schedule(
    recipes: Sequence[MultiLutRecipe],
    recipe_indices: bytes | bytearray | memoryview | Sequence[int],
    capabilities: Sequence[LutHoldCapability],
    *,
    profile_order: Sequence[str],
    width: int = WIDTH,
    height: int = HEIGHT,
) -> MultiLutHoldSchedule:
    """Build an offline schedule or reject any unqualified HOLD assumption."""

    if width <= 0 or height <= 0 or width % 2:
        raise MultiLutScheduleError("width must be positive/even and height positive")
    if not recipes or not all(isinstance(item, MultiLutRecipe) for item in recipes):
        raise MultiLutScheduleError("recipes must contain MultiLutRecipe values")
    recipe_ids = [item.recipe_id for item in recipes]
    if len(recipe_ids) != len(set(recipe_ids)):
        raise MultiLutScheduleError("recipe IDs must be unique")
    indices = bytes(recipe_indices)
    if len(indices) != width * height:
        raise MultiLutScheduleError("recipe assignment size differs")
    if max(indices) >= len(recipes):
        raise MultiLutScheduleError("recipe assignment index is out of range")
    used_recipe_indices = set(indices)
    if any(
        recipes[index].qualification_level is not QualificationLevel.QUALIFIED
        or not recipes[index].local_hold_qualified
        for index in used_recipe_indices
    ):
        raise MultiLutScheduleError(
            "every scheduled recipe must be qualified for colour and local HOLD"
        )
    for pixel, recipe_index in enumerate(indices):
        expected = _controller_for_pixel(pixel, width)
        if recipes[recipe_index].controller is not expected:
            raise MultiLutScheduleError("recipe controller differs from pixel half")

    capability_by_id = {item.lut_profile_id: item for item in capabilities}
    if len(capability_by_id) != len(capabilities):
        raise MultiLutScheduleError("LUT capability IDs must be unique")
    used_profiles = {recipes[index].lut_profile_id for index in indices}
    order = tuple(_text(item, "profile_order item") for item in profile_order)
    if len(order) != len(set(order)) or set(order) != used_profiles:
        raise MultiLutScheduleError("profile_order must list every used profile once")
    if any(profile not in capability_by_id for profile in order):
        raise MultiLutScheduleError("a used LUT profile lacks HOLD capability")

    scheduled: list[ScheduledPass] = []
    committed: list[str] = []
    for profile in order:
        capability = capability_by_id[profile]
        if (
            not capability.baseline_hold_qualified
            or not capability.local_hold_qualified
        ):
            raise MultiLutScheduleError("LUT HOLD capability is not qualified")
        if not set(committed).issubset(capability.retains_profile_ids):
            raise MultiLutScheduleError(
                "later LUT profile is not qualified to retain every committed profile"
            )
        profile_recipe_indices = {
            index
            for index in used_recipe_indices
            if recipes[index].lut_profile_id == profile
        }
        profile_recipes = [recipes[index] for index in profile_recipe_indices]
        phases: list[tuple[PassPhase, int | None]] = [(PassPhase.SOURCE, None)]
        if any(item.middle_code is not None for item in profile_recipes):
            phases.append((PassPhase.MIDDLE, None))
        phases.append((PassPhase.TARGET, 1))
        maximum_repeat = max(item.target_repeat_count for item in profile_recipes)
        phases.extend(
            (PassPhase.TARGET_REPEAT, repeat) for repeat in range(2, maximum_repeat + 1)
        )
        for phase, repeat in phases:
            frame, active_mask = _frame_for_pass(
                recipes,
                indices,
                capability,
                profile,
                phase,
                repeat,
                width=width,
                height=height,
            )
            scheduled.append(
                ScheduledPass(
                    len(scheduled) + 1,
                    profile,
                    phase,
                    repeat,
                    sum(active_mask),
                    hashlib.sha256(active_mask).hexdigest(),
                    frame,
                    hashlib.sha256(frame).hexdigest(),
                    tuple(committed),
                )
            )
        committed.append(profile)
    ordered_capabilities = tuple(capability_by_id[profile] for profile in order)
    return MultiLutHoldSchedule(
        width,
        height,
        order,
        tuple(scheduled),
        tuple(recipes),
        ordered_capabilities,
        hashlib.sha256(indices).hexdigest(),
    )
