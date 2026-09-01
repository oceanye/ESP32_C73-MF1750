"""Fail-closed offline target and coverage planner for a 256-slot palette.

The default target is a planning grid, not a display-gamut claim.  It reserves
twelve named hue families (R, RO, O, Y, YG, G, T, C, B, I, V, M), two
chroma/sub-hue tracks per family, ten lightness ranks per track, and sixteen
neutral slots.  The two tracks are target alternatives inside one named hue
family; they are not represented as twenty-four independent pure hues.

Coverage is calculated independently for CS1 and CS2.  A partial family may
feed a limited controller-local photo chain, but only through its exact
qualified single-pixel slots.  Spatial dithering never counts as a colour.
Having the same slot ID on both controllers is only a comparison candidate:
full-panel admission additionally requires an independent optical-match
artifact bound to both exact recipes, the slot ID, and a passing Delta-E 2000
result.

This module performs no hardware, camera, relay, serial, network, flash,
reset, refresh, or LUT-write operation.  Its only optional filesystem action
is exporting a verified JSON report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    finite_triple,
    require_sha256,
    require_text,
    verify_integrity,
)
from .multi_lut_hold_schedule import Controller


SCHEMA_VERSION = 2
TARGET_KIND = "MF1750_STATIC_PHOTO_256_SLOT_PALETTE_TARGET"
COVERAGE_KIND = "MF1750_STATIC_PHOTO_PALETTE_TARGET_COVERAGE"
TARGET_ID = "MF1750-P256-H12-T2-L10-N16-V2"
FINAL_PALETTE_SLOT_COUNT = 256
HUE_FAMILY_IDS = ("R", "RO", "O", "Y", "YG", "G", "T", "C", "B", "I", "V", "M")
CHROMATIC_FAMILY_COUNT = len(HUE_FAMILY_IDS)
CHROMATIC_TRACK_IDS = ("T1", "T2")
CHROMATIC_TRACK_COUNT = len(CHROMATIC_TRACK_IDS)
LIGHTNESS_STEPS_PER_CHROMATIC_TRACK = 10
# Compatibility name retained for callers that interpret a family lightness
# ladder; each family now explicitly contains two such tracks.
LIGHTNESS_STEPS_PER_CHROMATIC_FAMILY = LIGHTNESS_STEPS_PER_CHROMATIC_TRACK
NEUTRAL_SLOT_COUNT = 16
CONTROLLERS = (Controller.CS1, Controller.CS2)
CHROMATIC_MILESTONE_RANKS = {
    3: (1, 5, 10),
    5: (1, 3, 5, 8, 10),
    10: tuple(range(1, 11)),
}
NEUTRAL_MILESTONE_RANKS = {
    3: (1, 8, 16),
    5: (1, 4, 8, 12, 16),
    10: (1, 2, 4, 6, 8, 10, 12, 14, 15, 16),
}


class PaletteTargetCoverageError(ValueError):
    """Raised when palette targets or qualified coverage are ambiguous."""


class SlotKind(str, Enum):
    CHROMATIC = "CHROMATIC"
    NEUTRAL = "NEUTRAL"


class QualificationState(str, Enum):
    PALETTE_READY = "PALETTE_READY"


def _text(value: object, label: str) -> str:
    try:
        return require_text(value, label)
    except StaticPhotoContractError as error:
        raise PaletteTargetCoverageError(str(error)) from error


def _sha256(value: object, label: str) -> str:
    try:
        return require_sha256(value, label)
    except StaticPhotoContractError as error:
        raise PaletteTargetCoverageError(str(error)) from error


def _controller(value: Controller | str) -> Controller:
    try:
        return value if isinstance(value, Controller) else Controller(value)
    except ValueError as error:
        raise PaletteTargetCoverageError("controller must be CS1 or CS2") from error


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaletteTargetCoverageError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise PaletteTargetCoverageError(f"{label} must be finite and non-negative")
    return result


@dataclass(frozen=True)
class QualifiedPaletteSlot:
    """One externally qualified recipe assigned to one controller-local slot."""

    controller: Controller
    target_slot_id: str
    recipe_id: str
    family_id: str
    lut_profile_id: str
    measured_lab: tuple[float, float, float]
    qualification_evidence_sha256: str
    qualification_state: QualificationState = QualificationState.PALETTE_READY
    single_pixel_pure: bool = True
    spatial_dithering_used: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "controller", _controller(self.controller))
        for field_name in (
            "target_slot_id",
            "recipe_id",
            "family_id",
            "lut_profile_id",
        ):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        try:
            state = (
                self.qualification_state
                if isinstance(self.qualification_state, QualificationState)
                else QualificationState(self.qualification_state)
            )
        except ValueError as error:
            raise PaletteTargetCoverageError(
                "qualification_state must be PALETTE_READY"
            ) from error
        object.__setattr__(self, "qualification_state", state)
        try:
            lab = finite_triple(self.measured_lab, "measured_lab")
        except StaticPhotoContractError as error:
            raise PaletteTargetCoverageError(str(error)) from error
        if not 0.0 <= lab[0] <= 100.0:
            raise PaletteTargetCoverageError("measured Lab L* must be in 0..100")
        object.__setattr__(self, "measured_lab", lab)
        object.__setattr__(
            self,
            "qualification_evidence_sha256",
            _sha256(
                self.qualification_evidence_sha256,
                "qualification_evidence_sha256",
            ),
        )
        if type(self.single_pixel_pure) is not bool:
            raise PaletteTargetCoverageError("single_pixel_pure must be boolean")
        if type(self.spatial_dithering_used) is not bool:
            raise PaletteTargetCoverageError("spatial_dithering_used must be boolean")
        if not self.single_pixel_pure or self.spatial_dithering_used:
            raise PaletteTargetCoverageError(
                "qualified palette slots must be single-pixel pure and must not use "
                "spatial dithering"
            )

    @property
    def key(self) -> tuple[Controller, str]:
        return self.controller, self.target_slot_id

    @property
    def recipe_key(self) -> tuple[Controller, str]:
        return self.controller, self.recipe_id

    def mapping(self) -> dict[str, Any]:
        return {
            "controller": self.controller.value,
            "target_slot_id": self.target_slot_id,
            "recipe_id": self.recipe_id,
            "family_id": self.family_id,
            "lut_profile_id": self.lut_profile_id,
            "measured_lab": list(self.measured_lab),
            "qualification_evidence_sha256": self.qualification_evidence_sha256,
            "qualification_state": self.qualification_state.value,
            "single_pixel_pure": True,
            "spatial_dithering_used": False,
        }


@dataclass(frozen=True)
class CrossControllerOpticalMatchEvidence:
    """Independent optical comparison for one exact CS1/CS2 slot pair."""

    target_slot_id: str
    cs1_recipe_id: str
    cs2_recipe_id: str
    delta_e00: float
    acceptance_threshold_delta_e00: float
    passed: bool
    optical_match_evidence_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("target_slot_id", "cs1_recipe_id", "cs2_recipe_id"):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self, "delta_e00", _finite_nonnegative(self.delta_e00, "delta_e00")
        )
        threshold = _finite_nonnegative(
            self.acceptance_threshold_delta_e00,
            "acceptance_threshold_delta_e00",
        )
        if threshold <= 0.0:
            raise PaletteTargetCoverageError(
                "acceptance_threshold_delta_e00 must be positive"
            )
        object.__setattr__(self, "acceptance_threshold_delta_e00", threshold)
        if type(self.passed) is not bool:
            raise PaletteTargetCoverageError("optical match passed must be boolean")
        if self.passed and self.delta_e00 > threshold:
            raise PaletteTargetCoverageError(
                "passing optical match exceeds its Delta-E 2000 threshold"
            )
        object.__setattr__(
            self,
            "optical_match_evidence_sha256",
            _sha256(
                self.optical_match_evidence_sha256,
                "optical_match_evidence_sha256",
            ),
        )

    def mapping(self) -> dict[str, Any]:
        return {
            "target_slot_id": self.target_slot_id,
            "cs1_recipe_id": self.cs1_recipe_id,
            "cs2_recipe_id": self.cs2_recipe_id,
            "delta_e00": self.delta_e00,
            "acceptance_threshold_delta_e00": self.acceptance_threshold_delta_e00,
            "passed": self.passed,
            "optical_match_evidence_sha256": self.optical_match_evidence_sha256,
        }


def _chromatic_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for family_ordinal, family_id in enumerate(HUE_FAMILY_IDS, start=1):
        for track_id in CHROMATIC_TRACK_IDS:
            series_id = f"{family_id}-{track_id}"
            for rank in range(1, LIGHTNESS_STEPS_PER_CHROMATIC_TRACK + 1):
                slots.append(
                    {
                        "slot_id": f"{series_id}-L{rank:02d}",
                        "kind": SlotKind.CHROMATIC.value,
                        "family_id": family_id,
                        "family_ordinal": family_ordinal,
                        "track_id": track_id,
                        "track_role": "CHROMA_OR_SUBHUE_TARGET_TRACK",
                        "lightness_series_id": series_id,
                        "lightness_rank": rank,
                        "target_lightness_lstar": rank * 10 - 5,
                        "target_only_not_measured": True,
                    }
                )
    return slots


def _neutral_slots() -> list[dict[str, Any]]:
    return [
        {
            "slot_id": f"N-L{rank:02d}",
            "kind": SlotKind.NEUTRAL.value,
            "family_id": "NEUTRAL",
            "family_ordinal": None,
            "track_id": None,
            "track_role": None,
            "lightness_series_id": "NEUTRAL",
            "lightness_rank": rank,
            "target_lightness_lstar": round(
                (rank - 1) * 100 / (NEUTRAL_SLOT_COUNT - 1), 6
            ),
            "target_only_not_measured": True,
        }
        for rank in range(1, NEUTRAL_SLOT_COUNT + 1)
    ]


def _target_unsigned() -> dict[str, Any]:
    slots = _chromatic_slots() + _neutral_slots()
    if len(slots) != FINAL_PALETTE_SLOT_COUNT:
        raise AssertionError("default target slot count differs")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": TARGET_KIND,
        "target_id": TARGET_ID,
        "status": "ASPIRATIONAL_TARGET_ONLY",
        "allocation": {
            "final_palette_slot_count": FINAL_PALETTE_SLOT_COUNT,
            "named_chromatic_hue_family_count": CHROMATIC_FAMILY_COUNT,
            "named_chromatic_hue_family_ids": list(HUE_FAMILY_IDS),
            "chroma_or_subhue_tracks_per_family": CHROMATIC_TRACK_COUNT,
            "chroma_or_subhue_track_ids": list(CHROMATIC_TRACK_IDS),
            "lightness_steps_per_track": LIGHTNESS_STEPS_PER_CHROMATIC_TRACK,
            "chromatic_lightness_series_count": (
                CHROMATIC_FAMILY_COUNT * CHROMATIC_TRACK_COUNT
            ),
            "chromatic_slot_count": (
                CHROMATIC_FAMILY_COUNT
                * CHROMATIC_TRACK_COUNT
                * LIGHTNESS_STEPS_PER_CHROMATIC_TRACK
            ),
            "neutral_slot_count": NEUTRAL_SLOT_COUNT,
            "formula": (
                "12 named hue families x 2 chroma/sub-hue tracks x 10 "
                "lightness ranks + 16 neutral slots = 256 total slots"
            ),
        },
        "interpretation": {
            "palette_size_is_total_slots": True,
            "not_256_hues_times_10_lightness_steps": True,
            "two_tracks_are_not_independent_pure_hues": True,
            "tracks_are_chroma_or_subhue_targets_within_named_family": True,
            "ten_lightness_steps_apply_to_each_track": True,
            "target_grid_is_not_a_physical_gamut_claim": True,
            "target_slot_is_not_a_qualified_colour": True,
        },
        "development_milestones": {
            "chromatic_lightness_step_order": [3, 5, 10],
            "chromatic_rank_sets": {
                str(count): list(ranks)
                for count, ranks in CHROMATIC_MILESTONE_RANKS.items()
            },
            "neutral_lightness_step_order": [3, 5, 10],
            "neutral_rank_sets": {
                str(count): list(ranks)
                for count, ranks in NEUTRAL_MILESTONE_RANKS.items()
            },
            "ten_step_claim_before_three_and_five_step_gates": False,
        },
        "slots": slots,
        "qualification_policy": {
            "controller_local": True,
            "controllers_pooled": False,
            "single_pixel_pure_required": True,
            "spatial_dithering_counts_as_colour": False,
            "external_palette_ready_evidence_required": True,
            "partial_ready_family_may_enter_controller_local_photo_chain": True,
            "only_exact_qualified_slots_may_enter_photo_chain": True,
            "missing_family_ranks_remain_excluded": True,
            "same_slot_on_both_controllers_is_not_optical_match": True,
            "panel_wide_admission_requires_cross_controller_optical_match": True,
        },
        "execution_boundary": {
            "offline_only": True,
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "relay_or_j2_operation_present": False,
            "flash_reset_refresh_operation_present": False,
            "live_authorization_generated": False,
            "hardware_action_ids": [],
        },
    }


def build_default_256_palette_target() -> dict[str, Any]:
    """Return the exact deterministic 12x2x10+16 target grid."""

    return attach_integrity(_target_unsigned())


def verify_palette_target(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Verify canonical integrity and the exact fixed target definition."""

    if not isinstance(mapping, Mapping):
        raise PaletteTargetCoverageError("palette target must be an object")
    try:
        unsigned = verify_integrity(mapping, "palette target")
    except StaticPhotoContractError as error:
        raise PaletteTargetCoverageError(str(error)) from error
    if unsigned != _target_unsigned():
        raise PaletteTargetCoverageError("palette target definition differs")
    return unsigned


def _milestone_state(
    target_slots: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, QualifiedPaletteSlot],
    milestone_ranks: Mapping[int, Sequence[int]],
) -> dict[str, Any]:
    slot_by_rank = {
        int(slot["lightness_rank"]): str(slot["slot_id"]) for slot in target_slots
    }
    qualified_ids = set(assignments)
    milestones: list[dict[str, Any]] = []
    achieved = 0
    next_step: int | None = None
    next_missing: list[str] = []
    for count, ranks in milestone_ranks.items():
        required = [slot_by_rank[rank] for rank in ranks]
        missing = [slot_id for slot_id in required if slot_id not in qualified_ids]
        passed = not missing
        if passed:
            achieved = count
        elif next_step is None:
            next_step = count
            next_missing = missing
        milestones.append(
            {
                "step_count": count,
                "required_slot_ids": required,
                "missing_slot_ids": missing,
                "status": "PASS" if passed else "PENDING",
            }
        )
    return {
        "achieved_step_count": achieved,
        "next_step_count": next_step,
        "next_step_missing_slot_ids": next_missing,
        "milestones": milestones,
    }


def _series_summary(
    series_id: str,
    target_slots: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, QualifiedPaletteSlot],
) -> dict[str, Any]:
    target_ids = [str(slot["slot_id"]) for slot in target_slots]
    qualified_ids = [slot_id for slot_id in target_ids if slot_id in assignments]
    missing_ids = [slot_id for slot_id in target_ids if slot_id not in assignments]
    if not qualified_ids:
        status = "EMPTY"
    elif missing_ids:
        status = "PARTIAL_READY"
    else:
        status = "COMPLETE"
    milestone = _milestone_state(
        target_slots,
        {slot_id: assignments[slot_id] for slot_id in qualified_ids},
        CHROMATIC_MILESTONE_RANKS,
    )
    first = target_slots[0]
    return {
        "lightness_series_id": series_id,
        "family_id": first["family_id"],
        "track_id": first["track_id"],
        "kind": SlotKind.CHROMATIC.value,
        "target_slot_count": len(target_ids),
        "qualified_slot_count": len(qualified_ids),
        "missing_slot_count": len(missing_ids),
        "qualified_slot_ids": qualified_ids,
        "missing_slot_ids": missing_ids,
        "status": status,
        "lightness_milestone": milestone,
        "photo_chain_subset_admitted": bool(qualified_ids),
        "all_missing_slots_excluded": True,
    }


def _neutral_summary(
    target_slots: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, QualifiedPaletteSlot],
) -> dict[str, Any]:
    target_ids = [str(slot["slot_id"]) for slot in target_slots]
    qualified_ids = [slot_id for slot_id in target_ids if slot_id in assignments]
    missing_ids = [slot_id for slot_id in target_ids if slot_id not in assignments]
    if not qualified_ids:
        status = "EMPTY"
    elif missing_ids:
        status = "PARTIAL_READY"
    else:
        status = "COMPLETE"
    return {
        "family_id": "NEUTRAL",
        "kind": SlotKind.NEUTRAL.value,
        "target_slot_count": len(target_ids),
        "qualified_slot_count": len(qualified_ids),
        "missing_slot_count": len(missing_ids),
        "qualified_slot_ids": qualified_ids,
        "missing_slot_ids": missing_ids,
        "status": status,
        "lightness_milestone": _milestone_state(
            target_slots,
            {slot_id: assignments[slot_id] for slot_id in qualified_ids},
            NEUTRAL_MILESTONE_RANKS,
        ),
        "photo_chain_subset_admitted": bool(qualified_ids),
        "all_missing_slots_excluded": True,
    }


def _controller_summary(
    controller: Controller,
    slots: Sequence[Mapping[str, Any]],
    assignments: Sequence[QualifiedPaletteSlot],
) -> dict[str, Any]:
    by_slot = {item.target_slot_id: item for item in assignments}
    series: list[dict[str, Any]] = []
    for family_id in HUE_FAMILY_IDS:
        for track_id in CHROMATIC_TRACK_IDS:
            series_id = f"{family_id}-{track_id}"
            series.append(
                _series_summary(
                    series_id,
                    [
                        slot
                        for slot in slots
                        if slot["lightness_series_id"] == series_id
                    ],
                    by_slot,
                )
            )
    named_families = []
    for family_id in HUE_FAMILY_IDS:
        family_series = [item for item in series if item["family_id"] == family_id]
        named_families.append(
            {
                "family_id": family_id,
                "track_ids": list(CHROMATIC_TRACK_IDS),
                "target_slot_count": sum(
                    item["target_slot_count"] for item in family_series
                ),
                "qualified_slot_count": sum(
                    item["qualified_slot_count"] for item in family_series
                ),
                "complete_ten_step_track_count": sum(
                    item["lightness_milestone"]["achieved_step_count"] == 10
                    for item in family_series
                ),
                "track_statuses": {
                    str(item["track_id"]): item["status"] for item in family_series
                },
            }
        )
    neutral = _neutral_summary(
        [slot for slot in slots if slot["family_id"] == "NEUTRAL"], by_slot
    )
    qualified_ids = sorted(by_slot)
    missing_ids = sorted(
        str(slot["slot_id"]) for slot in slots if str(slot["slot_id"]) not in by_slot
    )
    ready_series = [item for item in series if item["qualified_slot_count"] > 0]
    complete_series = [
        item
        for item in series
        if item["lightness_milestone"]["achieved_step_count"] == 10
    ]
    return {
        "controller": controller.value,
        "target_slot_count": FINAL_PALETTE_SLOT_COUNT,
        "qualified_slot_count": len(qualified_ids),
        "missing_slot_count": len(missing_ids),
        "coverage_percent": round(
            len(qualified_ids) * 100 / FINAL_PALETTE_SLOT_COUNT, 6
        ),
        "qualified_slot_ids": qualified_ids,
        "missing_slot_ids": missing_ids,
        "named_chromatic_hue_families": named_families,
        "chromatic_lightness_series": series,
        "neutral_axis": neutral,
        "ready_chromatic_lightness_series_count": len(ready_series),
        "complete_ten_step_chromatic_series_count": len(complete_series),
        "complete_ten_step_chromatic_series_ids": [
            item["lightness_series_id"] for item in complete_series
        ],
        "photo_chain_admission": {
            "admitted": bool(qualified_ids),
            "mode": (
                "QUALIFIED_CONTROLLER_LOCAL_SUBSET_ONLY"
                if qualified_ids
                else "BLOCKED_NO_QUALIFIED_SLOT"
            ),
            "admitted_slot_ids": qualified_ids,
            "unqualified_slot_ids_excluded": missing_ids,
            "partial_ready_family_allowed": True,
            "all_ten_ranks_required_for_partial_admission": False,
            "controllers_pooled": False,
        },
    }


def _milestone_experiment(
    controller: str,
    series: Mapping[str, Any],
) -> dict[str, Any]:
    milestone = series["lightness_milestone"]
    if not isinstance(milestone, Mapping):
        raise AssertionError("lightness milestone differs")
    step_count = milestone["next_step_count"]
    if step_count == 3:
        kind = "COMPLETE_CURRENT_3_STEP_LIGHTNESS_LADDER"
    elif step_count == 5:
        kind = "EXPAND_CURRENT_LIGHTNESS_LADDER_TO_5_STEPS"
    elif step_count == 10:
        kind = "EXPAND_CURRENT_LIGHTNESS_LADDER_TO_10_STEPS"
    else:
        raise AssertionError("next lightness milestone differs")
    return {
        "controller": controller,
        "experiment_kind": kind,
        "family_id": series["family_id"],
        "track_id": series["track_id"],
        "target_step_count": step_count,
        "target_slot_ids": milestone["next_step_missing_slot_ids"],
        "reason": (
            "advance the most mature stable-base lightness path through the "
            "mandatory 3-to-5-to-10 milestone order"
        ),
    }


def _neutral_milestone_experiment(
    controller: str, neutral: Mapping[str, Any]
) -> dict[str, Any]:
    milestone = neutral["lightness_milestone"]
    if not isinstance(milestone, Mapping):
        raise AssertionError("neutral lightness milestone differs")
    step_count = milestone["next_step_count"]
    if step_count == 3:
        kind = "ESTABLISH_NEUTRAL_3_STEP_LIGHTNESS_LADDER"
    elif step_count == 5:
        kind = "EXPAND_NEUTRAL_LIGHTNESS_LADDER_TO_5_STEPS"
    elif step_count == 10:
        kind = "EXPAND_NEUTRAL_LIGHTNESS_LADDER_TO_10_STEPS"
    else:
        raise AssertionError("next neutral milestone differs")
    return {
        "controller": controller,
        "experiment_kind": kind,
        "family_id": "NEUTRAL",
        "track_id": None,
        "target_step_count": step_count,
        "target_slot_ids": milestone["next_step_missing_slot_ids"],
        "reason": "advance the gray/lightness function before broader hue search",
    }


def _next_controller_experiment(summary: Mapping[str, Any]) -> dict[str, Any]:
    controller = str(summary["controller"])
    series = summary["chromatic_lightness_series"]
    if not isinstance(series, list):
        raise AssertionError("chromatic lightness series summary differs")
    complete = [
        item
        for item in series
        if item["lightness_milestone"]["achieved_step_count"] == 10
    ]
    if not complete:
        active = [item for item in series if item["qualified_slot_count"] > 0]
        if not active:
            return {
                "controller": controller,
                "experiment_kind": (
                    "ESTABLISH_FIRST_STABLE_BASE_3_STEP_LIGHTNESS_LADDER"
                ),
                "family_id": None,
                "track_id": None,
                "target_step_count": 3,
                "target_slot_ids": [],
                "reason": (
                    "no qualified chromatic lightness path exists; choose one "
                    "stable base and establish only the 3-step gate first"
                ),
            }
        active.sort(
            key=lambda item: (
                -int(item["lightness_milestone"]["achieved_step_count"]),
                -int(item["qualified_slot_count"]),
                item["lightness_series_id"],
            )
        )
        return _milestone_experiment(controller, active[0])

    neutral = summary["neutral_axis"]
    if not isinstance(neutral, Mapping):
        raise AssertionError("neutral summary differs")
    neutral_achieved = neutral["lightness_milestone"]["achieved_step_count"]
    if neutral_achieved < 10:
        return _neutral_milestone_experiment(controller, neutral)

    return {
        "controller": controller,
        "experiment_kind": "VALIDATE_LIMITED_PHOTO_CHAIN_WITH_READY_SUBSET",
        "family_id": None,
        "track_id": None,
        "target_step_count": None,
        "target_slot_ids": summary["qualified_slot_ids"],
        "reason": (
            "exercise palette mapping and local-HOLD composition before adding hues"
        ),
    }


def _bind_optical_matches(
    evidence: Sequence[CrossControllerOpticalMatchEvidence],
    assignment_by_key: Mapping[tuple[Controller, str], QualifiedPaletteSlot],
) -> list[CrossControllerOpticalMatchEvidence]:
    by_slot: dict[str, CrossControllerOpticalMatchEvidence] = {}
    for item in evidence:
        if not isinstance(item, CrossControllerOpticalMatchEvidence):
            raise PaletteTargetCoverageError(
                "every optical match must be CrossControllerOpticalMatchEvidence"
            )
        if item.target_slot_id in by_slot:
            raise PaletteTargetCoverageError(
                f"duplicate optical match for slot {item.target_slot_id}"
            )
        cs1 = assignment_by_key.get((Controller.CS1, item.target_slot_id))
        cs2 = assignment_by_key.get((Controller.CS2, item.target_slot_id))
        if cs1 is None or cs2 is None:
            raise PaletteTargetCoverageError(
                f"optical match {item.target_slot_id} requires qualified CS1 and CS2 slots"
            )
        if item.cs1_recipe_id != cs1.recipe_id or item.cs2_recipe_id != cs2.recipe_id:
            raise PaletteTargetCoverageError(
                f"optical match {item.target_slot_id} recipe binding differs"
            )
        if item.optical_match_evidence_sha256 in {
            cs1.qualification_evidence_sha256,
            cs2.qualification_evidence_sha256,
        }:
            raise PaletteTargetCoverageError(
                f"optical match {item.target_slot_id} requires independent evidence"
            )
        by_slot[item.target_slot_id] = item
    return [by_slot[slot_id] for slot_id in sorted(by_slot)]


def build_palette_target_coverage(
    target: Mapping[str, Any],
    qualified_slots: Sequence[QualifiedPaletteSlot] = (),
    cross_controller_matches: Sequence[CrossControllerOpticalMatchEvidence] = (),
) -> dict[str, Any]:
    """Compute controller-local coverage and evidence-gated panel admission."""

    unsigned_target = verify_palette_target(target)
    if not isinstance(qualified_slots, (list, tuple)):
        raise PaletteTargetCoverageError("qualified_slots must be a sequence")
    if any(not isinstance(item, QualifiedPaletteSlot) for item in qualified_slots):
        raise PaletteTargetCoverageError(
            "every qualified slot must be QualifiedPaletteSlot"
        )
    if not isinstance(cross_controller_matches, (list, tuple)):
        raise PaletteTargetCoverageError("cross_controller_matches must be a sequence")
    target_slots = unsigned_target["slots"]
    if not isinstance(target_slots, list):
        raise PaletteTargetCoverageError("target slots differ")
    slot_by_id = {str(slot["slot_id"]): slot for slot in target_slots}

    assignment_by_key: dict[tuple[Controller, str], QualifiedPaletteSlot] = {}
    recipe_keys: set[tuple[Controller, str]] = set()
    for assignment in qualified_slots:
        slot = slot_by_id.get(assignment.target_slot_id)
        if slot is None:
            raise PaletteTargetCoverageError(
                f"unknown target slot {assignment.target_slot_id}"
            )
        if assignment.family_id != slot["family_id"]:
            raise PaletteTargetCoverageError(
                f"{assignment.target_slot_id} family binding differs"
            )
        if assignment.key in assignment_by_key:
            raise PaletteTargetCoverageError(
                f"duplicate controller target slot {assignment.target_slot_id}"
            )
        if assignment.recipe_key in recipe_keys:
            raise PaletteTargetCoverageError(
                f"recipe {assignment.recipe_id} is assigned to multiple target slots "
                f"on {assignment.controller.value}"
            )
        assignment_by_key[assignment.key] = assignment
        recipe_keys.add(assignment.recipe_key)

    ordered_assignments = sorted(
        qualified_slots,
        key=lambda item: (item.controller.value, item.target_slot_id, item.recipe_id),
    )
    ordered_matches = _bind_optical_matches(cross_controller_matches, assignment_by_key)
    summaries = [
        _controller_summary(
            controller,
            target_slots,
            [item for item in ordered_assignments if item.controller is controller],
        )
        for controller in CONTROLLERS
    ]
    qualified_sets = {
        str(summary["controller"]): set(summary["qualified_slot_ids"])
        for summary in summaries
    }
    cs1_slots = qualified_sets[Controller.CS1.value]
    cs2_slots = qualified_sets[Controller.CS2.value]
    same_slot_candidates = sorted(cs1_slots & cs2_slots)
    match_by_slot = {item.target_slot_id: item for item in ordered_matches}
    optically_matched = sorted(
        slot_id
        for slot_id in same_slot_candidates
        if slot_id in match_by_slot and match_by_slot[slot_id].passed
    )
    failed_matches = sorted(
        slot_id
        for slot_id in same_slot_candidates
        if slot_id in match_by_slot and not match_by_slot[slot_id].passed
    )
    no_passing_evidence = sorted(set(same_slot_candidates) - set(optically_matched))
    priorities = [
        {"priority": index, **_next_controller_experiment(summary)}
        for index, summary in enumerate(summaries, start=1)
    ]
    panel_next_gate = (
        {
            "experiment_kind": "COLLECT_CROSS_CONTROLLER_OPTICAL_MATCH_EVIDENCE",
            "target_slot_ids": no_passing_evidence,
            "reason": (
                "same slot IDs on CS1 and CS2 are not panel-wide colours until "
                "independent recipe-bound Delta-E 2000 evidence passes"
            ),
        }
        if no_passing_evidence
        else (
            {
                "experiment_kind": "PANEL_WIDE_MATCHED_SUBSET_READY",
                "target_slot_ids": optically_matched,
                "reason": "all same-slot comparison candidates have passing evidence",
            }
            if optically_matched
            else {
                "experiment_kind": "WAIT_FOR_COMMON_CONTROLLER_LOCAL_SLOT",
                "target_slot_ids": [],
                "reason": "no slot is independently qualified on both controllers",
            }
        )
    )
    target_integrity = target.get("integrity")
    if not isinstance(target_integrity, Mapping):
        raise PaletteTargetCoverageError("target integrity differs")
    identity = {
        "target": target_integrity.get("canonical_sha256"),
        "assignments": [item.mapping() for item in ordered_assignments],
        "cross_controller_matches": [item.mapping() for item in ordered_matches],
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": COVERAGE_KIND,
        "coverage_id": f"PCOV-{canonical_sha256(identity)[:20]}",
        "status": (
            "NO_QUALIFIED_SLOTS"
            if not ordered_assignments
            else (
                "PANEL_TARGET_COMPLETE"
                if len(optically_matched) == FINAL_PALETTE_SLOT_COUNT
                else (
                    "CONTROLLER_TARGET_COMPLETE_PANEL_MATCH_PENDING"
                    if all(
                        int(summary["qualified_slot_count"])
                        == FINAL_PALETTE_SLOT_COUNT
                        for summary in summaries
                    )
                    else "PARTIAL_QUALIFIED_COVERAGE"
                )
            )
        ),
        "source_target": {
            "target_id": TARGET_ID,
            "canonical_sha256": target_integrity.get("canonical_sha256"),
        },
        "qualified_assignments": [item.mapping() for item in ordered_assignments],
        "cross_controller_optical_matches": [
            item.mapping() for item in ordered_matches
        ],
        "controllers": summaries,
        "panel_wide_intersection": {
            "same_target_slot_candidate_count": len(same_slot_candidates),
            "same_target_slot_candidate_ids": same_slot_candidates,
            "optically_matched_slot_count": len(optically_matched),
            "optically_matched_slot_ids": optically_matched,
            "failed_optical_match_slot_ids": failed_matches,
            "slot_ids_without_passing_optical_evidence": no_passing_evidence,
            "cs1_only_slot_ids": sorted(cs1_slots - cs2_slots),
            "cs2_only_slot_ids": sorted(cs2_slots - cs1_slots),
            "full_panel_limited_photo_chain_admitted": bool(optically_matched),
            "same_target_slot_is_not_sufficient": True,
            "cross_controller_optical_match_required": True,
            "controller_recipes_remain_independent": True,
            "next_gate": panel_next_gate,
        },
        "next_priority_function_experiments": priorities,
        "policy": {
            "function_paths_before_broader_hue_enumeration": True,
            "lightness_milestone_order": [3, 5, 10],
            "ten_step_claim_before_three_and_five_step_gates": False,
            "broad_hue_enumeration_deferred": True,
            "long_duration_reliability_deferred": True,
            "controller_local_coverage_only": True,
            "controllers_pooled": False,
            "spatial_dithering_counts_as_colour": False,
            "automatic_colour_or_gray_claim": False,
            "partial_ready_family_enters_controller_local_photo_chain": True,
            "photo_chain_uses_exact_qualified_subset_only": True,
            "same_slot_intersection_grants_panel_admission": False,
            "passing_cross_controller_optical_match_required": True,
        },
        "execution_boundary": {
            "offline_only": True,
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "relay_or_j2_operation_present": False,
            "flash_reset_refresh_operation_present": False,
            "live_authorization_generated": False,
            "hardware_action_ids": [],
            "executable_hardware_plan_generated": False,
        },
    }
    return attach_integrity(unsigned)


def verify_palette_target_coverage(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Verify canonical integrity and immutable offline/qualification boundaries."""

    if not isinstance(mapping, Mapping):
        raise PaletteTargetCoverageError("palette coverage must be an object")
    try:
        unsigned = verify_integrity(mapping, "palette coverage")
    except StaticPhotoContractError as error:
        raise PaletteTargetCoverageError(str(error)) from error
    if unsigned.get("schema_version") != SCHEMA_VERSION:
        raise PaletteTargetCoverageError("palette coverage schema version differs")
    if unsigned.get("kind") != COVERAGE_KIND:
        raise PaletteTargetCoverageError("palette coverage kind differs")
    boundary = unsigned.get("execution_boundary")
    if not isinstance(boundary, Mapping) or boundary != {
        "offline_only": True,
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_accessed": False,
        "relay_or_j2_operation_present": False,
        "flash_reset_refresh_operation_present": False,
        "live_authorization_generated": False,
        "hardware_action_ids": [],
        "executable_hardware_plan_generated": False,
    }:
        raise PaletteTargetCoverageError("palette coverage execution boundary differs")
    policy = unsigned.get("policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not False
        for key in (
            "controllers_pooled",
            "spatial_dithering_counts_as_colour",
            "automatic_colour_or_gray_claim",
            "same_slot_intersection_grants_panel_admission",
            "ten_step_claim_before_three_and_five_step_gates",
        )
    ):
        raise PaletteTargetCoverageError(
            "palette coverage qualification policy differs"
        )
    panel = unsigned.get("panel_wide_intersection")
    if not isinstance(panel, Mapping):
        raise PaletteTargetCoverageError("panel-wide intersection differs")

    raw_assignments = unsigned.get("qualified_assignments")
    if not isinstance(raw_assignments, list):
        raise PaletteTargetCoverageError("qualified assignments differ")
    assignment_by_key: dict[tuple[Controller, str], Mapping[str, Any]] = {}
    for raw in raw_assignments:
        if not isinstance(raw, Mapping):
            raise PaletteTargetCoverageError("qualified assignment differs")
        controller = _controller(raw.get("controller"))
        slot_id = _text(raw.get("target_slot_id"), "target_slot_id")
        recipe_id = _text(raw.get("recipe_id"), "recipe_id")
        _sha256(
            raw.get("qualification_evidence_sha256"),
            "qualification_evidence_sha256",
        )
        if raw.get("qualification_state") != QualificationState.PALETTE_READY.value:
            raise PaletteTargetCoverageError("qualified assignment state differs")
        if (
            raw.get("single_pixel_pure") is not True
            or raw.get("spatial_dithering_used") is not False
        ):
            raise PaletteTargetCoverageError(
                "qualified assignment single-pixel boundary differs"
            )
        key = (controller, slot_id)
        if key in assignment_by_key:
            raise PaletteTargetCoverageError("qualified assignment key is duplicated")
        assignment_by_key[key] = {**raw, "recipe_id": recipe_id}

    raw_matches = unsigned.get("cross_controller_optical_matches")
    if not isinstance(raw_matches, list):
        raise PaletteTargetCoverageError("cross-controller optical matches differ")
    passing_slots: list[str] = []
    failed_slots: list[str] = []
    seen_match_slots: set[str] = set()
    for raw in raw_matches:
        if not isinstance(raw, Mapping):
            raise PaletteTargetCoverageError("cross-controller optical match differs")
        slot_id = _text(raw.get("target_slot_id"), "optical target_slot_id")
        if slot_id in seen_match_slots:
            raise PaletteTargetCoverageError("optical match slot is duplicated")
        seen_match_slots.add(slot_id)
        cs1 = assignment_by_key.get((Controller.CS1, slot_id))
        cs2 = assignment_by_key.get((Controller.CS2, slot_id))
        if cs1 is None or cs2 is None:
            raise PaletteTargetCoverageError(
                "optical match lacks both controller-local assignments"
            )
        if (
            raw.get("cs1_recipe_id") != cs1["recipe_id"]
            or raw.get("cs2_recipe_id") != cs2["recipe_id"]
        ):
            raise PaletteTargetCoverageError("optical match recipe binding differs")
        evidence_hash = _sha256(
            raw.get("optical_match_evidence_sha256"),
            "optical_match_evidence_sha256",
        )
        if evidence_hash in {
            cs1["qualification_evidence_sha256"],
            cs2["qualification_evidence_sha256"],
        }:
            raise PaletteTargetCoverageError(
                "optical match evidence is not independent"
            )
        delta_e00 = _finite_nonnegative(raw.get("delta_e00"), "delta_e00")
        threshold = _finite_nonnegative(
            raw.get("acceptance_threshold_delta_e00"),
            "acceptance_threshold_delta_e00",
        )
        passed = raw.get("passed")
        if type(passed) is not bool or threshold <= 0.0:
            raise PaletteTargetCoverageError("optical match result differs")
        if passed and delta_e00 > threshold:
            raise PaletteTargetCoverageError(
                "passing optical match exceeds its Delta-E 2000 threshold"
            )
        (passing_slots if passed else failed_slots).append(slot_id)

    cs1_slots = {
        slot_id
        for controller, slot_id in assignment_by_key
        if controller is Controller.CS1
    }
    cs2_slots = {
        slot_id
        for controller, slot_id in assignment_by_key
        if controller is Controller.CS2
    }
    same_slot_candidates = sorted(cs1_slots & cs2_slots)
    matched = sorted(passing_slots)
    if panel.get("same_target_slot_candidate_ids") != same_slot_candidates:
        raise PaletteTargetCoverageError("panel-wide same-slot candidates differ")
    if panel.get("optically_matched_slot_ids") != matched:
        raise PaletteTargetCoverageError("panel-wide optical matches differ")
    if panel.get("failed_optical_match_slot_ids") != sorted(failed_slots):
        raise PaletteTargetCoverageError("panel-wide failed optical matches differ")
    if panel.get("slot_ids_without_passing_optical_evidence") != sorted(
        set(same_slot_candidates) - set(matched)
    ):
        raise PaletteTargetCoverageError("panel-wide optical evidence gaps differ")
    if panel.get("full_panel_limited_photo_chain_admitted") is not bool(matched):
        raise PaletteTargetCoverageError("panel-wide optical admission differs")
    return unsigned


def export_palette_target_coverage(
    mapping: Mapping[str, Any],
    path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a verified coverage report without overwriting by default."""

    verify_palette_target_coverage(mapping)
    output = Path(path)
    if output.exists() and not overwrite:
        raise PaletteTargetCoverageError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


__all__ = [
    "CHROMATIC_FAMILY_COUNT",
    "CHROMATIC_TRACK_COUNT",
    "CHROMATIC_TRACK_IDS",
    "CrossControllerOpticalMatchEvidence",
    "FINAL_PALETTE_SLOT_COUNT",
    "HUE_FAMILY_IDS",
    "LIGHTNESS_STEPS_PER_CHROMATIC_FAMILY",
    "LIGHTNESS_STEPS_PER_CHROMATIC_TRACK",
    "NEUTRAL_SLOT_COUNT",
    "PaletteTargetCoverageError",
    "QualificationState",
    "QualifiedPaletteSlot",
    "SlotKind",
    "build_default_256_palette_target",
    "build_palette_target_coverage",
    "export_palette_target_coverage",
    "verify_palette_target",
    "verify_palette_target_coverage",
]
