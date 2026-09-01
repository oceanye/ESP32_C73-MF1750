"""Fail-closed bridge from coarse swatches to controller-specific palettes.

The coarse lightness screen deliberately does not qualify colours.  This
module is the missing evidence boundary between that screen, the multi-LUT
local-HOLD scheduler, and a future controller-aware photo quantizer.

Candidates remain candidates until independent reproducibility, local-HOLD,
and factory-white-recovery evidence is bound to the exact candidate
fingerprint.  Reproducibility is explicit: a direct target may use an
identical-target repeat, while a history-conditioned lightness recipe must be
rebuilt from a fresh factory-white baseline.  A multi-LUT export additionally
requires directional cross-profile retention evidence for *each* controller.
CS1 and CS2 are never pooled, and spatial dithering is never accepted as
colour evidence.

This module performs no hardware, camera, relay, network, or filesystem I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from host.color_pipeline.color import lab_to_srgb8

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    finite_triple,
    verify_integrity,
)
from .history_palette import QualificationLevel, TRANSPORT_CODES
from .multi_lut_hold_schedule import (
    Controller,
    LutHoldCapability,
    MultiLutRecipe,
)


class ControllerPaletteInventoryError(ValueError):
    """Raised when candidate identity or qualification evidence is unsafe."""


class CandidateKind(str, Enum):
    COARSE_COLOR = "COARSE_COLOR_CANDIDATE"
    COARSE_LIGHTNESS = "COARSE_LIGHTNESS_CANDIDATE"


class ReproducibilityMode(str, Enum):
    IDENTICAL_TARGET_REPEAT = "identical-target-repeat"
    FRESH_WHITE_RECONSTRUCTION = "fresh-white-reconstruction"


class QualificationEvidenceRole(str, Enum):
    IDENTICAL_TARGET_REPEAT = "identical-target-repeat"
    FRESH_WHITE_RECONSTRUCTION = "fresh-white-reconstruction"
    LOCAL_HOLD = "local-hold"
    FACTORY_WHITE_RECOVERY = "factory-white-recovery"


COMMON_REQUIRED_RECIPE_EVIDENCE_ROLES = frozenset(
    {
        QualificationEvidenceRole.LOCAL_HOLD,
        QualificationEvidenceRole.FACTORY_WHITE_RECOVERY,
    }
)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControllerPaletteInventoryError(f"{label} must be non-empty text")
    result = value.strip()
    if any(ord(character) < 0x20 for character in result):
        raise ControllerPaletteInventoryError(f"{label} must not contain controls")
    return result


def _sha256(value: object, label: str) -> str:
    result = _text(value, label).lower()
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ControllerPaletteInventoryError(f"{label} must be lowercase SHA-256")
    return result


def _code(value: object, label: str) -> int:
    if type(value) is not int or value not in TRANSPORT_CODES:
        raise ControllerPaletteInventoryError(f"{label} must be an integer in 0..7")
    return value


def _controller(value: Controller | str) -> Controller:
    try:
        return value if isinstance(value, Controller) else Controller(value)
    except ValueError as error:
        raise ControllerPaletteInventoryError("controller differs") from error


@dataclass(frozen=True)
class ControllerPaletteCandidate:
    """One unqualified single-pixel swatch on one physical controller."""

    candidate_id: str
    controller: Controller
    lut_profile_id: str
    kind: CandidateKind
    source_code: int
    middle_code: int | None
    target_code: int
    target_repeat_count: int
    measured_lab: tuple[float, float, float]
    preview_rgb: tuple[int, int, int] | None
    single_pixel_pure: bool
    spatial_dithering_used: bool
    coarse_screen_artifact_sha256: str
    coarse_screen_canonical_sha256: str
    reproducibility_mode: ReproducibilityMode = (
        ReproducibilityMode.IDENTICAL_TARGET_REPEAT
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _text(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "lut_profile_id", _text(self.lut_profile_id, "lut_profile_id")
        )
        object.__setattr__(self, "controller", _controller(self.controller))
        try:
            kind = (
                self.kind
                if isinstance(self.kind, CandidateKind)
                else CandidateKind(self.kind)
            )
        except ValueError as error:
            raise ControllerPaletteInventoryError("candidate kind differs") from error
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "source_code", _code(self.source_code, "source_code"))
        if self.middle_code is not None:
            object.__setattr__(
                self, "middle_code", _code(self.middle_code, "middle_code")
            )
        object.__setattr__(self, "target_code", _code(self.target_code, "target_code"))
        if type(self.target_repeat_count) is not int or self.target_repeat_count < 1:
            raise ControllerPaletteInventoryError(
                "target_repeat_count must be a positive integer"
            )
        try:
            reproducibility_mode = (
                self.reproducibility_mode
                if isinstance(self.reproducibility_mode, ReproducibilityMode)
                else ReproducibilityMode(self.reproducibility_mode)
            )
        except ValueError as error:
            raise ControllerPaletteInventoryError(
                "candidate reproducibility_mode differs"
            ) from error
        object.__setattr__(self, "reproducibility_mode", reproducibility_mode)
        lab = finite_triple(self.measured_lab, "measured_lab")
        if not 0.0 <= lab[0] <= 100.0:
            raise ControllerPaletteInventoryError("measured Lab L* must be in 0..100")
        object.__setattr__(self, "measured_lab", lab)
        preview = lab_to_srgb8(lab) if self.preview_rgb is None else self.preview_rgb
        if (
            not isinstance(preview, (tuple, list))
            or len(preview) != 3
            or any(type(value) is not int or not 0 <= value <= 255 for value in preview)
        ):
            raise ControllerPaletteInventoryError(
                "preview_rgb must contain three integers in 0..255"
            )
        object.__setattr__(self, "preview_rgb", tuple(preview))
        if type(self.single_pixel_pure) is not bool:
            raise ControllerPaletteInventoryError("single_pixel_pure must be boolean")
        if type(self.spatial_dithering_used) is not bool:
            raise ControllerPaletteInventoryError(
                "spatial_dithering_used must be boolean"
            )
        object.__setattr__(
            self,
            "coarse_screen_artifact_sha256",
            _sha256(
                self.coarse_screen_artifact_sha256,
                "coarse_screen_artifact_sha256",
            ),
        )
        object.__setattr__(
            self,
            "coarse_screen_canonical_sha256",
            _sha256(
                self.coarse_screen_canonical_sha256,
                "coarse_screen_canonical_sha256",
            ),
        )

    @property
    def key(self) -> tuple[Controller, str]:
        return self.controller, self.candidate_id

    def unsigned_mapping(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "controller": self.controller.value,
            "lut_profile_id": self.lut_profile_id,
            "kind": self.kind.value,
            "source_code": self.source_code,
            "middle_code": self.middle_code,
            "target_code": self.target_code,
            "target_repeat_count": self.target_repeat_count,
            "measured_lab": list(self.measured_lab),
            "preview_rgb": list(self.preview_rgb or ()),
            "single_pixel_pure": self.single_pixel_pure,
            "spatial_dithering_used": self.spatial_dithering_used,
            "coarse_screen_artifact_sha256": self.coarse_screen_artifact_sha256,
            "coarse_screen_canonical_sha256": self.coarse_screen_canonical_sha256,
            "reproducibility_mode": self.reproducibility_mode.value,
        }

    @property
    def fingerprint_sha256(self) -> str:
        return canonical_sha256(self.unsigned_mapping())


@dataclass(frozen=True)
class ControllerPaletteEvidence:
    """One independently captured proof bound to an exact candidate."""

    role: QualificationEvidenceRole
    controller: Controller
    candidate_id: str
    lut_profile_id: str
    candidate_fingerprint_sha256: str
    artifact_sha256: str
    passed: bool
    single_pixel_pure: bool
    spatial_dithering_used: bool
    observed_target_repeat_count: int | None = None
    hold_code: int | None = None
    baseline_hold_passed: bool | None = None
    fresh_white_reconstruction_count: int | None = None

    def __post_init__(self) -> None:
        try:
            role = (
                self.role
                if isinstance(self.role, QualificationEvidenceRole)
                else QualificationEvidenceRole(self.role)
            )
        except ValueError as error:
            raise ControllerPaletteInventoryError("evidence role differs") from error
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "controller", _controller(self.controller))
        object.__setattr__(
            self, "candidate_id", _text(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "lut_profile_id", _text(self.lut_profile_id, "lut_profile_id")
        )
        object.__setattr__(
            self,
            "candidate_fingerprint_sha256",
            _sha256(
                self.candidate_fingerprint_sha256,
                "candidate_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self, "artifact_sha256", _sha256(self.artifact_sha256, "artifact_sha256")
        )
        for label in ("passed", "single_pixel_pure", "spatial_dithering_used"):
            if type(getattr(self, label)) is not bool:
                raise ControllerPaletteInventoryError(f"{label} must be boolean")
        if role is QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT:
            if (
                type(self.observed_target_repeat_count) is not int
                or self.observed_target_repeat_count < 2
            ):
                raise ControllerPaletteInventoryError(
                    "repeat evidence requires at least two observed targets"
                )
            if self.hold_code is not None:
                raise ControllerPaletteInventoryError(
                    "repeat evidence must not carry a HOLD code"
                )
            if self.baseline_hold_passed is not None:
                raise ControllerPaletteInventoryError(
                    "repeat evidence must not carry a baseline-HOLD result"
                )
            if self.fresh_white_reconstruction_count is not None:
                raise ControllerPaletteInventoryError(
                    "repeat evidence must not carry a fresh-white reconstruction count"
                )
        elif role is QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION:
            if (
                type(self.fresh_white_reconstruction_count) is not int
                or self.fresh_white_reconstruction_count < 2
            ):
                raise ControllerPaletteInventoryError(
                    "fresh-white reconstruction evidence requires at least two runs"
                )
            if self.observed_target_repeat_count is not None:
                raise ControllerPaletteInventoryError(
                    "fresh-white reconstruction evidence must not carry a target-repeat count"
                )
            if self.hold_code is not None or self.baseline_hold_passed is not None:
                raise ControllerPaletteInventoryError(
                    "fresh-white reconstruction evidence must not carry HOLD fields"
                )
        elif role is QualificationEvidenceRole.LOCAL_HOLD:
            object.__setattr__(self, "hold_code", _code(self.hold_code, "hold_code"))
            if (
                self.observed_target_repeat_count is not None
                or self.fresh_white_reconstruction_count is not None
            ):
                raise ControllerPaletteInventoryError(
                    "local-HOLD evidence must not carry a reproducibility count"
                )
            if type(self.baseline_hold_passed) is not bool:
                raise ControllerPaletteInventoryError(
                    "local-HOLD evidence requires an explicit baseline-HOLD result"
                )
        elif (
            self.observed_target_repeat_count is not None
            or self.fresh_white_reconstruction_count is not None
            or self.hold_code is not None
            or self.baseline_hold_passed is not None
        ):
            raise ControllerPaletteInventoryError(
                "white-recovery evidence has no repeat count or HOLD fields"
            )

    @property
    def key(self) -> tuple[Controller, str]:
        return self.controller, self.candidate_id

    def mapping(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "controller": self.controller.value,
            "candidate_id": self.candidate_id,
            "lut_profile_id": self.lut_profile_id,
            "candidate_fingerprint_sha256": self.candidate_fingerprint_sha256,
            "artifact_sha256": self.artifact_sha256,
            "passed": self.passed,
            "single_pixel_pure": self.single_pixel_pure,
            "spatial_dithering_used": self.spatial_dithering_used,
            "observed_target_repeat_count": self.observed_target_repeat_count,
            "fresh_white_reconstruction_count": (self.fresh_white_reconstruction_count),
            "hold_code": self.hold_code,
            "baseline_hold_passed": self.baseline_hold_passed,
        }


@dataclass(frozen=True)
class CrossProfileRetentionEvidence:
    """Directional, controller-local proof that a later LUT retained an earlier one."""

    controller: Controller
    active_lut_profile_id: str
    retained_lut_profile_id: str
    hold_code: int
    artifact_sha256: str
    passed: bool
    retained_pixels_unchanged: bool
    single_pixel_pure: bool
    spatial_dithering_used: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "controller", _controller(self.controller))
        object.__setattr__(
            self,
            "active_lut_profile_id",
            _text(self.active_lut_profile_id, "active_lut_profile_id"),
        )
        object.__setattr__(
            self,
            "retained_lut_profile_id",
            _text(self.retained_lut_profile_id, "retained_lut_profile_id"),
        )
        if self.active_lut_profile_id == self.retained_lut_profile_id:
            raise ControllerPaletteInventoryError(
                "cross-profile evidence must name two different profiles"
            )
        object.__setattr__(self, "hold_code", _code(self.hold_code, "hold_code"))
        object.__setattr__(
            self, "artifact_sha256", _sha256(self.artifact_sha256, "artifact_sha256")
        )
        for label in (
            "passed",
            "retained_pixels_unchanged",
            "single_pixel_pure",
            "spatial_dithering_used",
        ):
            if type(getattr(self, label)) is not bool:
                raise ControllerPaletteInventoryError(f"{label} must be boolean")

    @property
    def key(self) -> tuple[Controller, str, str]:
        return (
            self.controller,
            self.active_lut_profile_id,
            self.retained_lut_profile_id,
        )

    def mapping(self) -> dict[str, Any]:
        return {
            "controller": self.controller.value,
            "active_lut_profile_id": self.active_lut_profile_id,
            "retained_lut_profile_id": self.retained_lut_profile_id,
            "hold_code": self.hold_code,
            "artifact_sha256": self.artifact_sha256,
            "passed": self.passed,
            "retained_pixels_unchanged": self.retained_pixels_unchanged,
            "single_pixel_pure": self.single_pixel_pure,
            "spatial_dithering_used": self.spatial_dithering_used,
        }


def candidate_from_lightness_screen(
    report: Mapping[str, Any],
    *,
    controller: Controller | str,
    lut_profile_id: str,
    target_code: int,
    recipe_id: str,
    source_code: int,
    middle_code: int | None,
    target_repeat_count: int,
    report_file_sha256: str,
) -> ControllerPaletteCandidate:
    """Bind one recipe from a verified coarse lightness *pair* as a candidate.

    Even when the coarse report contains repeat measurements, this function
    returns only ``ControllerPaletteCandidate``.  Independent qualification
    evidence is still mandatory in ``ControllerPaletteInventory``.
    """

    if target_repeat_count != 1:
        raise ControllerPaletteInventoryError(
            "history lightness candidate requires one target per fresh-white construction"
        )
    try:
        unsigned = verify_integrity(report, "lightness screen report")
    except StaticPhotoContractError as error:
        raise ControllerPaletteInventoryError(str(error)) from error
    if unsigned.get("kind") != "MF1750_SINGLE_PIXEL_LIGHTNESS_COARSE_SCREEN":
        raise ControllerPaletteInventoryError("lightness screen report kind differs")
    selected_controller = _controller(controller)
    selected_profile = _text(lut_profile_id, "lut_profile_id")
    selected_target = _code(target_code, "target_code")
    selected_recipe = _text(recipe_id, "recipe_id")
    groups = unsigned.get("groups")
    if not isinstance(groups, list):
        raise ControllerPaletteInventoryError("lightness screen groups differ")
    matching_groups = [
        group
        for group in groups
        if isinstance(group, Mapping)
        and group.get("controller") == selected_controller.value
        and group.get("lut_profile_id") == selected_profile
        and group.get("target_code") == selected_target
    ]
    if len(matching_groups) != 1:
        raise ControllerPaletteInventoryError(
            "lightness candidate controller/profile/target group is not unique"
        )
    group = matching_groups[0]
    pairs = group.get("candidate_pairs")
    recipes = group.get("recipes")
    if not isinstance(pairs, list) or not isinstance(recipes, list):
        raise ControllerPaletteInventoryError("lightness candidate lists differ")
    member_pairs = [
        pair
        for pair in pairs
        if isinstance(pair, Mapping)
        and pair.get("classification") == CandidateKind.COARSE_LIGHTNESS.value
        and selected_recipe
        in (pair.get("darker_recipe_id"), pair.get("lighter_recipe_id"))
    ]
    if not member_pairs:
        raise ControllerPaletteInventoryError(
            "recipe is not a coarse lightness candidate-pair member"
        )
    matching_recipes = [
        recipe
        for recipe in recipes
        if isinstance(recipe, Mapping) and recipe.get("recipe_id") == selected_recipe
    ]
    if len(matching_recipes) != 1:
        raise ControllerPaletteInventoryError(
            "lightness candidate recipe is not unique"
        )
    recipe = matching_recipes[0]
    if (
        recipe.get("position_stable") is not True
        or recipe.get("single_pixel_purity_and_boundary_pass") is not True
    ):
        raise ControllerPaletteInventoryError(
            "lightness candidate lacks position-stable single-pixel evidence"
        )
    lab = finite_triple(recipe.get("median_target_lab"), "median_target_lab")
    boundaries = unsigned.get("evidence_boundaries")
    if not isinstance(boundaries, Mapping) or (
        boundaries.get("controllers_pooled") is not False
        or boundaries.get("spatial_dither_counts_as_colour") is not False
        or boundaries.get("automatic_colour_qualification") is not False
    ):
        raise ControllerPaletteInventoryError(
            "lightness screen evidence boundaries differ"
        )
    integrity = report.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ControllerPaletteInventoryError("lightness screen integrity differs")
    canonical = integrity.get("canonical_sha256")
    return ControllerPaletteCandidate(
        candidate_id=selected_recipe,
        controller=selected_controller,
        lut_profile_id=selected_profile,
        kind=CandidateKind.COARSE_LIGHTNESS,
        source_code=source_code,
        middle_code=middle_code,
        target_code=selected_target,
        target_repeat_count=target_repeat_count,
        measured_lab=lab,
        preview_rgb=None,
        single_pixel_pure=True,
        spatial_dithering_used=False,
        coarse_screen_artifact_sha256=report_file_sha256,
        coarse_screen_canonical_sha256=_sha256(
            canonical, "lightness screen canonical_sha256"
        ),
        reproducibility_mode=ReproducibilityMode.FRESH_WHITE_RECONSTRUCTION,
    )


@dataclass(frozen=True)
class QualifiedControllerPaletteRecipe:
    """Evidence-complete recipe; construction is internal to the inventory."""

    candidate: ControllerPaletteCandidate
    evidence: tuple[ControllerPaletteEvidence, ...]
    qualification_manifest_sha256: str

    def to_multi_lut_recipe(self) -> MultiLutRecipe:
        identical_repeat = (
            self.candidate.reproducibility_mode
            is ReproducibilityMode.IDENTICAL_TARGET_REPEAT
        )
        fresh_reconstruction = (
            self.candidate.reproducibility_mode
            is ReproducibilityMode.FRESH_WHITE_RECONSTRUCTION
        )
        return MultiLutRecipe(
            recipe_id=f"{self.candidate.controller.value}:{self.candidate.candidate_id}",
            controller=self.candidate.controller,
            lut_profile_id=self.candidate.lut_profile_id,
            source_code=self.candidate.source_code,
            middle_code=self.candidate.middle_code,
            target_code=self.candidate.target_code,
            target_repeat_count=self.candidate.target_repeat_count,
            qualification_level=QualificationLevel.QUALIFIED,
            identical_target_repeat_qualified=identical_repeat,
            local_hold_qualified=True,
            factory_white_recovery_qualified=True,
            measurement_artifact_sha256=self.qualification_manifest_sha256,
            fresh_white_reconstruction_qualified=fresh_reconstruction,
        )


@dataclass(frozen=True)
class ControllerPaletteScheduleInputs:
    """Qualified inputs accepted by ``build_multi_lut_hold_schedule``."""

    recipes: tuple[MultiLutRecipe, ...]
    capabilities: tuple[LutHoldCapability, ...]
    profile_order: tuple[str, ...]
    recipe_index_by_controller_candidate: dict[tuple[Controller, str], int]
    qualification_manifest_sha256: str


@dataclass(frozen=True)
class ControllerPaletteInventory:
    """Inventory that records candidates without silently promoting them."""

    inventory_id: str
    candidates: tuple[ControllerPaletteCandidate, ...]
    evidence: tuple[ControllerPaletteEvidence, ...]
    cross_profile_evidence: tuple[CrossProfileRetentionEvidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inventory_id", _text(self.inventory_id, "inventory_id")
        )
        if not isinstance(self.candidates, (tuple, list)) or not self.candidates:
            raise ControllerPaletteInventoryError("inventory requires candidates")
        if not all(
            isinstance(item, ControllerPaletteCandidate) for item in self.candidates
        ):
            raise ControllerPaletteInventoryError(
                "candidates must contain ControllerPaletteCandidate values"
            )
        if not isinstance(self.evidence, (tuple, list)) or not all(
            isinstance(item, ControllerPaletteEvidence) for item in self.evidence
        ):
            raise ControllerPaletteInventoryError(
                "evidence must contain ControllerPaletteEvidence values"
            )
        if not isinstance(self.cross_profile_evidence, (tuple, list)) or not all(
            isinstance(item, CrossProfileRetentionEvidence)
            for item in self.cross_profile_evidence
        ):
            raise ControllerPaletteInventoryError(
                "cross_profile_evidence contains an invalid value"
            )
        candidates = tuple(self.candidates)
        evidence = tuple(self.evidence)
        cross = tuple(self.cross_profile_evidence)
        candidate_by_key = {item.key: item for item in candidates}
        if len(candidate_by_key) != len(candidates):
            raise ControllerPaletteInventoryError(
                "candidate IDs must be unique within each controller"
            )
        evidence_identities = [(item.key, item.role) for item in evidence]
        if len(evidence_identities) != len(set(evidence_identities)):
            raise ControllerPaletteInventoryError(
                "a candidate has duplicate evidence for one role"
            )
        for item in evidence:
            candidate = candidate_by_key.get(item.key)
            if candidate is None:
                raise ControllerPaletteInventoryError(
                    "qualification evidence references an unknown candidate"
                )
            if (
                item.lut_profile_id != candidate.lut_profile_id
                or item.candidate_fingerprint_sha256 != candidate.fingerprint_sha256
            ):
                raise ControllerPaletteInventoryError(
                    "qualification evidence binding differs from candidate"
                )
        profiles_by_controller = {
            controller: {
                candidate.lut_profile_id
                for candidate in candidates
                if candidate.controller is controller
            }
            for controller in Controller
        }
        cross_keys = [item.key for item in cross]
        if len(cross_keys) != len(set(cross_keys)):
            raise ControllerPaletteInventoryError(
                "cross-profile evidence identity is duplicated"
            )
        for item in cross:
            profiles = profiles_by_controller[item.controller]
            if (
                item.active_lut_profile_id not in profiles
                or item.retained_lut_profile_id not in profiles
            ):
                raise ControllerPaletteInventoryError(
                    "cross-profile evidence references a profile absent on its controller"
                )
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "cross_profile_evidence", cross)

    def _evidence_for(
        self, candidate: ControllerPaletteCandidate
    ) -> tuple[ControllerPaletteEvidence, ...]:
        return tuple(item for item in self.evidence if item.key == candidate.key)

    def _blocking_reasons(
        self, candidate: ControllerPaletteCandidate
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        proof = self._evidence_for(candidate)
        by_role = {item.role: item for item in proof}
        reproducibility_role = (
            QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT
            if candidate.reproducibility_mode
            is ReproducibilityMode.IDENTICAL_TARGET_REPEAT
            else QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION
        )
        required_roles = COMMON_REQUIRED_RECIPE_EVIDENCE_ROLES | {reproducibility_role}
        missing = required_roles - set(by_role)
        reasons.extend(f"missing:{role.value}" for role in sorted(missing, key=str))
        unexpected_reproducibility_roles = {
            QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT,
            QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION,
        } - {reproducibility_role}
        reasons.extend(
            f"unexpected:{role.value}"
            for role in sorted(unexpected_reproducibility_roles & set(by_role), key=str)
        )
        if not candidate.single_pixel_pure:
            reasons.append("candidate:not-single-pixel-pure")
        if candidate.spatial_dithering_used:
            reasons.append("candidate:spatial-dithering-used")
        if (
            candidate.reproducibility_mode
            is ReproducibilityMode.IDENTICAL_TARGET_REPEAT
            and candidate.target_repeat_count < 2
        ):
            reasons.append("candidate:target-repeat-count-below-two")
        proof_hashes = [item.artifact_sha256 for item in proof]
        if len(proof_hashes) != len(set(proof_hashes)):
            reasons.append("evidence:not-independent")
        if candidate.coarse_screen_artifact_sha256 in proof_hashes:
            reasons.append("evidence:reuses-coarse-screen-artifact")
        for item in proof:
            if not item.passed:
                reasons.append(f"failed:{item.role.value}")
            if not item.single_pixel_pure:
                reasons.append(f"not-single-pixel-pure:{item.role.value}")
            if item.spatial_dithering_used:
                reasons.append(f"spatial-dither:{item.role.value}")
            if (
                item.role is QualificationEvidenceRole.LOCAL_HOLD
                and not item.baseline_hold_passed
            ):
                reasons.append("failed:baseline-hold")
        repeat = by_role.get(QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT)
        if (
            repeat is not None
            and repeat.observed_target_repeat_count is not None
            and repeat.observed_target_repeat_count < candidate.target_repeat_count
        ):
            reasons.append("repeat:evidence-count-below-candidate-count")
        reconstruction = by_role.get(
            QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION
        )
        if (
            reconstruction is not None
            and reconstruction.fresh_white_reconstruction_count is not None
            and reconstruction.fresh_white_reconstruction_count < 2
        ):
            reasons.append("reconstruction:evidence-count-below-two")
        return tuple(sorted(set(reasons)))

    def qualified_entries(
        self, controller: Controller | str
    ) -> tuple[QualifiedControllerPaletteRecipe, ...]:
        """Return only one controller's evidence-complete recipes."""

        selected = _controller(controller)
        result: list[QualifiedControllerPaletteRecipe] = []
        for candidate in self.candidates:
            if candidate.controller is not selected or self._blocking_reasons(
                candidate
            ):
                continue
            proof = tuple(
                sorted(self._evidence_for(candidate), key=lambda item: item.role.value)
            )
            manifest = {
                "kind": "MF17506_CONTROLLER_PALETTE_RECIPE_QUALIFICATION",
                "inventory_id": self.inventory_id,
                "candidate": candidate.unsigned_mapping(),
                "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
                "evidence": [item.mapping() for item in proof],
                "controllers_pooled": False,
                "spatial_dithering_counts_as_colour": False,
            }
            result.append(
                QualifiedControllerPaletteRecipe(
                    candidate,
                    proof,
                    canonical_sha256(manifest),
                )
            )
        return tuple(sorted(result, key=lambda item: item.candidate.candidate_id))

    def quantization_entries(
        self, controller: Controller | str
    ) -> tuple[QualifiedControllerPaletteRecipe, ...]:
        """Controller-scoped swatches for a future controller-aware quantizer.

        Returning a controller is mandatory.  The legacy ``HistoryPalette``
        adapter is intentionally not used because its schema cannot preserve
        the CS1/CS2 evidence boundary.
        """

        return self.qualified_entries(controller)

    def multi_lut_schedule_inputs(
        self, *, profile_order: Sequence[str]
    ) -> ControllerPaletteScheduleInputs:
        """Export a cross-LUT schedule bridge only after all directional gates."""

        order = tuple(_text(item, "profile_order item") for item in profile_order)
        if len(order) < 2 or len(order) != len(set(order)):
            raise ControllerPaletteInventoryError(
                "cross-LUT profile_order requires at least two unique profiles"
            )
        qualified = {
            controller: self.qualified_entries(controller) for controller in Controller
        }
        all_entries = tuple(
            entry for controller in Controller for entry in qualified[controller]
        )
        used_profiles = {entry.candidate.lut_profile_id for entry in all_entries}
        if set(order) != used_profiles:
            raise ControllerPaletteInventoryError(
                "profile_order must list every and only qualified profile"
            )
        for profile in order:
            if any(
                not any(
                    entry.candidate.lut_profile_id == profile
                    for entry in qualified[controller]
                )
                for controller in Controller
            ):
                raise ControllerPaletteInventoryError(
                    "every profile requires qualified CS1 and CS2 recipes"
                )

        capability_values: list[LutHoldCapability] = []
        cross_by_key = {item.key: item for item in self.cross_profile_evidence}
        all_recipe_artifacts = {
            proof.artifact_sha256 for entry in all_entries for proof in entry.evidence
        }
        for profile_index, profile in enumerate(order):
            hold_codes: dict[Controller, int] = {}
            local_artifacts: set[str] = set()
            for controller in Controller:
                profile_entries = tuple(
                    entry
                    for entry in qualified[controller]
                    if entry.candidate.lut_profile_id == profile
                )
                local_proofs = tuple(
                    proof
                    for entry in profile_entries
                    for proof in entry.evidence
                    if proof.role is QualificationEvidenceRole.LOCAL_HOLD
                )
                codes = {proof.hold_code for proof in local_proofs}
                if len(codes) != 1 or None in codes:
                    raise ControllerPaletteInventoryError(
                        "controller/profile local-HOLD code is ambiguous"
                    )
                hold_codes[controller] = next(iter(codes))  # type: ignore[arg-type]
                local_artifacts.update(proof.artifact_sha256 for proof in local_proofs)

            retained_profiles = order[:profile_index]
            cross_artifacts: set[str] = set()
            for retained in retained_profiles:
                for controller in Controller:
                    item = cross_by_key.get((controller, profile, retained))
                    if item is None:
                        raise ControllerPaletteInventoryError(
                            "missing controller-specific cross-profile retention evidence"
                        )
                    if (
                        not item.passed
                        or not item.retained_pixels_unchanged
                        or not item.single_pixel_pure
                        or item.spatial_dithering_used
                        or item.hold_code != hold_codes[controller]
                    ):
                        raise ControllerPaletteInventoryError(
                            "cross-profile retention evidence did not pass"
                        )
                    if item.artifact_sha256 in all_recipe_artifacts:
                        raise ControllerPaletteInventoryError(
                            "cross-profile evidence is not independent of recipe evidence"
                        )
                    cross_artifacts.add(item.artifact_sha256)
            capability_manifest = {
                "kind": "MF17506_CONTROLLER_SPECIFIC_LUT_HOLD_QUALIFICATION",
                "inventory_id": self.inventory_id,
                "lut_profile_id": profile,
                "cs1_hold_code": hold_codes[Controller.CS1],
                "cs2_hold_code": hold_codes[Controller.CS2],
                "retains_profile_ids": list(retained_profiles),
                "local_hold_artifact_sha256s": sorted(local_artifacts),
                "cross_profile_artifact_sha256s": sorted(cross_artifacts),
                "controllers_pooled": False,
                "spatial_dithering_counts_as_colour": False,
            }
            capability_values.append(
                LutHoldCapability(
                    lut_profile_id=profile,
                    cs1_hold_code=hold_codes[Controller.CS1],
                    cs2_hold_code=hold_codes[Controller.CS2],
                    baseline_hold_qualified=True,
                    local_hold_qualified=True,
                    retains_profile_ids=tuple(retained_profiles),
                    qualification_artifact_sha256=canonical_sha256(capability_manifest),
                )
            )

        ordered_entries = tuple(
            sorted(
                all_entries,
                key=lambda entry: (
                    order.index(entry.candidate.lut_profile_id),
                    entry.candidate.controller.value,
                    entry.candidate.candidate_id,
                ),
            )
        )
        recipes = tuple(entry.to_multi_lut_recipe() for entry in ordered_entries)
        index = {
            entry.candidate.key: recipe_index
            for recipe_index, entry in enumerate(ordered_entries)
        }
        bridge_manifest = {
            "kind": "MF17506_CONTROLLER_PALETTE_TO_MULTI_LUT_BRIDGE",
            "inventory_canonical_sha256": self.mapping()["integrity"][
                "canonical_sha256"
            ],
            "profile_order": list(order),
            "recipe_qualification_sha256s": [
                entry.qualification_manifest_sha256 for entry in ordered_entries
            ],
            "capability_qualification_sha256s": [
                item.qualification_artifact_sha256 for item in capability_values
            ],
        }
        return ControllerPaletteScheduleInputs(
            recipes,
            tuple(capability_values),
            order,
            index,
            canonical_sha256(bridge_manifest),
        )

    def mapping(self) -> dict[str, Any]:
        records = []
        qualified_count = 0
        for candidate in sorted(
            self.candidates,
            key=lambda item: (item.controller.value, item.candidate_id),
        ):
            reasons = self._blocking_reasons(candidate)
            qualified = not reasons
            qualified_count += int(qualified)
            records.append(
                {
                    "candidate": candidate.unsigned_mapping(),
                    "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
                    "qualification_state": (
                        "CONTROLLER_LOCAL_RECIPE_QUALIFIED"
                        if qualified
                        else "COARSE_CANDIDATE_ONLY"
                    ),
                    "blocking_reasons": list(reasons),
                    "evidence": [
                        item.mapping()
                        for item in sorted(
                            self._evidence_for(candidate),
                            key=lambda item: item.role.value,
                        )
                    ],
                }
            )
        unsigned = {
            "schema_version": 1,
            "kind": "MF17506_CONTROLLER_SPECIFIC_PALETTE_QUALIFICATION_INVENTORY",
            "inventory_id": self.inventory_id,
            "candidate_count": len(self.candidates),
            "controller_local_qualified_recipe_count": qualified_count,
            "candidates": records,
            "cross_profile_evidence": [
                item.mapping()
                for item in sorted(
                    self.cross_profile_evidence,
                    key=lambda item: (
                        item.controller.value,
                        item.active_lut_profile_id,
                        item.retained_lut_profile_id,
                    ),
                )
            ],
            "evidence_boundaries": {
                "coarse_candidate_automatically_promoted": False,
                "controllers_pooled": False,
                "spatial_dithering_counts_as_colour": False,
                "legacy_history_palette_export_allowed": False,
                "history_lightness_requires_fresh_white_reconstruction": True,
                "identical_target_repeat_is_not_universal": True,
                "cross_lut_requires_both_controllers": True,
                "hardware_accessed": False,
                "live_authorized": False,
                "autochain_allowed": False,
            },
        }
        return attach_integrity(unsigned)
