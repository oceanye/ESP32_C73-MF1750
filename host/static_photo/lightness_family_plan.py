"""Offline plan for generalizing a lightness mechanism over stable endpoints.

The module deliberately stops before any camera or hardware action.  It turns
controller-specific evidence into position-balanced batch *specifications* and
models the evidence gates that must be closed before a static-photo scheduler
may consume those specifications.

No function in this module opens a device, emits a live action, creates an
authorization token, or treats spatial dithering as a colour mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    require_sha256,
    require_text,
    verify_integrity,
)
from .multi_lut_hold_schedule import Controller


SCHEMA_VERSION = 1
PLAN_KIND = "MF1750_STABLE_BASE_LIGHTNESS_FAMILY_OFFLINE_PLAN"
TRANSPORT_CODES = tuple(range(8))
REPLICAS_PER_RECIPE = 4
GRID_ROWS = 4
GRID_COLUMNS = 8

# Each middle code occurs once per row.  Within the top two and bottom two
# rows, it occurs once in each horizontal half.  Thus every recipe has one
# replica in each top-left/top-right/bottom-left/bottom-right quadrant.
POSITION_BALANCED_ROW_SHIFTS = (0, 4, 1, 5)


class LightnessFamilyPlanError(ValueError):
    """Raised when the lightness-family evidence boundary is ambiguous."""


class MechanismMaturity(str, Enum):
    """External assessment of the source-middle-target mechanism."""

    NO_HIT_YET = "NO_HIT_YET"
    CANDIDATE = "CANDIDATE"
    PROVEN = "PROVEN"


class FamilyGate(str, Enum):
    """Required gate order before a batch may enter photo scheduling."""

    SCREEN = "SCREEN"
    LOCAL_HOLD = "LOCAL_HOLD"
    FRESH_WHITE_RECONSTRUCTION = "FRESH_WHITE_RECONSTRUCTION"
    FACTORY_WHITE_RECOVERY = "FACTORY_WHITE_RECOVERY"
    CROSS_LUT_RETENTION = "CROSS_LUT_RETENTION"
    PALETTE_READY = "PALETTE_READY"


GATE_ORDER = tuple(FamilyGate)


class GateResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


def _controller(value: Controller | str, label: str) -> Controller:
    try:
        return value if isinstance(value, Controller) else Controller(value)
    except ValueError as error:
        raise LightnessFamilyPlanError(f"{label} must be CS1 or CS2") from error


def _code(value: object, label: str) -> int:
    if type(value) is not int or value not in TRANSPORT_CODES:
        raise LightnessFamilyPlanError(f"{label} must be an integer in 0..7")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise LightnessFamilyPlanError(f"{label} must be boolean")
    return value


def _text(value: object, label: str) -> str:
    try:
        return require_text(value, label)
    except StaticPhotoContractError as error:
        raise LightnessFamilyPlanError(str(error)) from error


def _sha256(value: object, label: str) -> str:
    try:
        return require_sha256(value, label)
    except StaticPhotoContractError as error:
        raise LightnessFamilyPlanError(str(error)) from error


@dataclass(frozen=True)
class StableEndpoint:
    """One externally evidenced, single-pixel stable base endpoint."""

    endpoint_id: str
    controller: Controller
    code: int
    profile_id: str
    evidence_sha256: str
    single_pixel_pure: bool = True
    spatial_dithering_used: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint_id", _text(self.endpoint_id, "endpoint_id"))
        object.__setattr__(
            self, "controller", _controller(self.controller, "endpoint controller")
        )
        object.__setattr__(self, "code", _code(self.code, "endpoint code"))
        object.__setattr__(self, "profile_id", _text(self.profile_id, "profile_id"))
        object.__setattr__(
            self,
            "evidence_sha256",
            _sha256(self.evidence_sha256, "endpoint evidence_sha256"),
        )
        pure = _boolean(self.single_pixel_pure, "endpoint single_pixel_pure")
        dither = _boolean(
            self.spatial_dithering_used, "endpoint spatial_dithering_used"
        )
        if not pure or dither:
            raise LightnessFamilyPlanError(
                "stable endpoint must be single-pixel pure and must not use spatial dithering"
            )

    def mapping(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "controller": self.controller.value,
            "code": self.code,
            "profile_id": self.profile_id,
            "evidence_sha256": self.evidence_sha256,
            "single_pixel_pure": True,
            "spatial_dithering_used": False,
        }


@dataclass(frozen=True)
class LightnessMechanism:
    """Controller-local source-(C0..C7)-target mechanism evidence."""

    mechanism_id: str
    controller: Controller
    source_profile_id: str
    middle_profile_id: str
    target_profile_id: str
    source_code: int
    target_code: int
    maturity: MechanismMaturity
    evidence_sha256: str
    single_pixel_pure: bool = True
    spatial_dithering_used: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "mechanism_id", _text(self.mechanism_id, "mechanism_id")
        )
        object.__setattr__(
            self, "controller", _controller(self.controller, "mechanism controller")
        )
        for field_name in (
            "source_profile_id",
            "middle_profile_id",
            "target_profile_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), f"mechanism {field_name}"),
            )
        object.__setattr__(
            self, "source_code", _code(self.source_code, "mechanism source_code")
        )
        object.__setattr__(
            self, "target_code", _code(self.target_code, "mechanism target_code")
        )
        try:
            maturity = (
                self.maturity
                if isinstance(self.maturity, MechanismMaturity)
                else MechanismMaturity(self.maturity)
            )
        except ValueError as error:
            raise LightnessFamilyPlanError("mechanism maturity differs") from error
        object.__setattr__(self, "maturity", maturity)
        object.__setattr__(
            self,
            "evidence_sha256",
            _sha256(self.evidence_sha256, "mechanism evidence_sha256"),
        )
        pure = _boolean(self.single_pixel_pure, "mechanism single_pixel_pure")
        dither = _boolean(
            self.spatial_dithering_used, "mechanism spatial_dithering_used"
        )
        if not pure or dither:
            raise LightnessFamilyPlanError(
                "lightness mechanism must be single-pixel pure and must not use spatial dithering"
            )

    def mapping(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "controller": self.controller.value,
            "source": {
                "profile_id": self.source_profile_id,
                "code": self.source_code,
            },
            "middle": {
                "profile_id": self.middle_profile_id,
                "enumerated_codes": list(TRANSPORT_CODES),
            },
            "target": {
                "profile_id": self.target_profile_id,
                "code": self.target_code,
            },
            "maturity": self.maturity.value,
            "evidence_sha256": self.evidence_sha256,
            "single_pixel_pure": True,
            "spatial_dithering_used": False,
        }


@dataclass(frozen=True)
class LightnessFamilySeed:
    """Exact stable endpoint and mechanism pair for one family batch."""

    endpoint: StableEndpoint
    mechanism: LightnessMechanism

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, StableEndpoint):
            raise LightnessFamilyPlanError("seed endpoint type differs")
        if not isinstance(self.mechanism, LightnessMechanism):
            raise LightnessFamilyPlanError("seed mechanism type differs")
        if self.endpoint.controller is not self.mechanism.controller:
            raise LightnessFamilyPlanError(
                "stable endpoint and mechanism controllers must match"
            )
        if self.endpoint.profile_id != self.mechanism.target_profile_id:
            raise LightnessFamilyPlanError(
                "stable endpoint profile must match mechanism target profile"
            )
        if self.endpoint.code != self.mechanism.target_code:
            raise LightnessFamilyPlanError(
                "stable endpoint code must match mechanism target code"
            )
        if self.endpoint.evidence_sha256 == self.mechanism.evidence_sha256:
            raise LightnessFamilyPlanError(
                "stable endpoint and mechanism require independent evidence artifacts"
            )

    @property
    def key(self) -> tuple[Controller, str, str]:
        return (
            self.endpoint.controller,
            self.endpoint.endpoint_id,
            self.mechanism.mechanism_id,
        )

    @property
    def family_id(self) -> str:
        identity = {
            "endpoint": self.endpoint.mapping(),
            "mechanism": self.mechanism.mapping(),
        }
        return f"LF-{canonical_sha256(identity)[:20]}"


@dataclass(frozen=True)
class FamilyGateEvidence:
    """One independently hashed result for one post-screen family gate."""

    controller: Controller
    endpoint_id: str
    mechanism_id: str
    gate: FamilyGate
    result: GateResult
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "controller", _controller(self.controller, "gate controller")
        )
        object.__setattr__(self, "endpoint_id", _text(self.endpoint_id, "endpoint_id"))
        object.__setattr__(
            self, "mechanism_id", _text(self.mechanism_id, "mechanism_id")
        )
        try:
            gate = (
                self.gate
                if isinstance(self.gate, FamilyGate)
                else FamilyGate(self.gate)
            )
            result = (
                self.result
                if isinstance(self.result, GateResult)
                else GateResult(self.result)
            )
        except ValueError as error:
            raise LightnessFamilyPlanError("gate or result differs") from error
        if gate is FamilyGate.SCREEN:
            raise LightnessFamilyPlanError(
                "SCREEN is bound to mechanism maturity/evidence and cannot be supplied again"
            )
        object.__setattr__(self, "gate", gate)
        object.__setattr__(self, "result", result)
        object.__setattr__(
            self,
            "evidence_sha256",
            _sha256(self.evidence_sha256, "gate evidence_sha256"),
        )

    @property
    def family_key(self) -> tuple[Controller, str, str]:
        return self.controller, self.endpoint_id, self.mechanism_id

    def mapping(self) -> dict[str, Any]:
        return {
            "controller": self.controller.value,
            "endpoint_id": self.endpoint_id,
            "mechanism_id": self.mechanism_id,
            "gate": self.gate.value,
            "result": self.result.value,
            "evidence_sha256": self.evidence_sha256,
        }


def _position_balanced_cells() -> tuple[dict[str, Any], ...]:
    cells: list[dict[str, Any]] = []
    for row, shift in enumerate(POSITION_BALANCED_ROW_SHIFTS):
        for column in range(GRID_COLUMNS):
            middle_code = (column + shift) % len(TRANSPORT_CODES)
            cells.append(
                {
                    "cell_index": row * GRID_COLUMNS + column,
                    "row": row,
                    "column": column,
                    "vertical_half": "TOP" if row < GRID_ROWS // 2 else "BOTTOM",
                    "horizontal_half": (
                        "LEFT" if column < GRID_COLUMNS // 2 else "RIGHT"
                    ),
                    "middle_code": middle_code,
                    "replica_ordinal": row + 1,
                }
            )

    for code in TRANSPORT_CODES:
        selected = [cell for cell in cells if cell["middle_code"] == code]
        if len(selected) != REPLICAS_PER_RECIPE:
            raise AssertionError("position-balanced replica count differs")
        quadrants = {
            (cell["vertical_half"], cell["horizontal_half"]) for cell in selected
        }
        if len(quadrants) != REPLICAS_PER_RECIPE:
            raise AssertionError("position-balanced quadrant coverage differs")
    return tuple(cells)


POSITION_BALANCED_CELLS = _position_balanced_cells()


def _batch(seed: LightnessFamilySeed, *, photo_ready: bool) -> dict[str, Any]:
    recipes: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for middle_code in TRANSPORT_CODES:
        recipe_id = f"{seed.family_id}-M{middle_code}"
        selected_cells = tuple(
            cell
            for cell in POSITION_BALANCED_CELLS
            if cell["middle_code"] == middle_code
        )
        recipes.append(
            {
                "recipe_id": recipe_id,
                "controller": seed.endpoint.controller.value,
                "source": {
                    "profile_id": seed.mechanism.source_profile_id,
                    "code": seed.mechanism.source_code,
                },
                "middle": {
                    "profile_id": seed.mechanism.middle_profile_id,
                    "code": middle_code,
                },
                "target": {
                    "profile_id": seed.endpoint.profile_id,
                    "code": seed.endpoint.code,
                },
                "replica_count": REPLICAS_PER_RECIPE,
                "cell_indices": [cell["cell_index"] for cell in selected_cells],
                "spatial_dithering_used": False,
                "automatic_colour_or_gray_claim": False,
            }
        )
        cells.extend({**cell, "recipe_id": recipe_id} for cell in selected_cells)

    cells.sort(key=lambda item: item["cell_index"])
    batch_identity = {
        "family_id": seed.family_id,
        "controller": seed.endpoint.controller.value,
        "endpoint_evidence_sha256": seed.endpoint.evidence_sha256,
        "mechanism_evidence_sha256": seed.mechanism.evidence_sha256,
        "recipes": recipes,
        "cells": cells,
    }
    return {
        "batch_id": f"LFB-{canonical_sha256(batch_identity)[:20]}",
        "family_id": seed.family_id,
        "controller": seed.endpoint.controller.value,
        "controller_local_only": True,
        "controllers_merged": False,
        "stable_endpoint": seed.endpoint.mapping(),
        "mechanism": seed.mechanism.mapping(),
        "geometry": {
            "rows": GRID_ROWS,
            "columns": GRID_COLUMNS,
            "cell_count": GRID_ROWS * GRID_COLUMNS,
            "row_shifts": list(POSITION_BALANCED_ROW_SHIFTS),
            "position_balance": (
                "each M0..M7 appears once per row and once in each quadrant"
            ),
        },
        "recipe_count": len(TRANSPORT_CODES),
        "replicas_per_recipe": REPLICAS_PER_RECIPE,
        "recipes": recipes,
        "cells": cells,
        "photo_schedule_eligible": photo_ready,
        "hardware_action_specification": None,
        "hardware_authorization": None,
    }


def _gate_states(
    seed: LightnessFamilySeed,
    evidence_by_gate: Mapping[FamilyGate, FamilyGateEvidence],
) -> tuple[list[dict[str, Any]], bool]:
    mechanism = seed.mechanism
    screen_passed = mechanism.maturity in {
        MechanismMaturity.CANDIDATE,
        MechanismMaturity.PROVEN,
    }
    states: list[dict[str, Any]] = [
        {
            "order": 1,
            "gate": FamilyGate.SCREEN.value,
            "status": "PASS" if screen_passed else "NO_HIT_YET",
            "evidence_sha256": mechanism.evidence_sha256,
            "derived_from": "mechanism_maturity",
        }
    ]
    previous_passed = screen_passed
    blocking_gate = None if previous_passed else FamilyGate.SCREEN
    used_hashes = {seed.endpoint.evidence_sha256, mechanism.evidence_sha256}

    for order, gate in enumerate(GATE_ORDER[1:], start=2):
        evidence = evidence_by_gate.get(gate)
        if evidence is not None and evidence.evidence_sha256 in used_hashes:
            raise LightnessFamilyPlanError(
                f"{seed.family_id} reuses an evidence artifact at {gate.value}"
            )
        if evidence is not None:
            used_hashes.add(evidence.evidence_sha256)

        if not previous_passed:
            if evidence is not None:
                assert blocking_gate is not None
                raise LightnessFamilyPlanError(
                    f"{seed.family_id} supplies {gate.value} before "
                    f"{blocking_gate.value} passed"
                )
            states.append(
                {
                    "order": order,
                    "gate": gate.value,
                    "status": "BLOCKED",
                    "evidence_sha256": None,
                    "blocked_by": blocking_gate.value if blocking_gate else None,
                }
            )
            continue

        if evidence is None:
            previous_passed = False
            blocking_gate = gate
            states.append(
                {
                    "order": order,
                    "gate": gate.value,
                    "status": "PENDING",
                    "evidence_sha256": None,
                    "blocked_by": None,
                }
            )
            continue

        if gate is FamilyGate.PALETTE_READY and (
            mechanism.maturity is not MechanismMaturity.PROVEN
        ):
            raise LightnessFamilyPlanError(
                f"{seed.family_id} cannot pass PALETTE_READY with an unproven mechanism"
            )
        passed = evidence.result is GateResult.PASS
        states.append(
            {
                "order": order,
                "gate": gate.value,
                "status": evidence.result.value,
                "evidence_sha256": evidence.evidence_sha256,
                "blocked_by": None,
            }
        )
        previous_passed = passed
        if not passed:
            blocking_gate = gate

    photo_ready = previous_passed and all(
        item["status"] == GateResult.PASS.value for item in states
    )
    return states, photo_ready


def build_lightness_family_plan(
    seeds: Sequence[LightnessFamilySeed],
    gate_evidence: Sequence[FamilyGateEvidence] = (),
) -> dict[str, Any]:
    """Build a deterministic, non-executable stable-base family plan.

    A ``NO_HIT_YET`` mechanism is intentionally accepted so callers can freeze
    the future batch geometry.  Such a batch remains
    ``PREPARED_NOT_LIVE_ADMITTED`` and cannot accept any downstream evidence.
    ``CANDIDATE`` mechanisms may progress through evidence collection but can
    never pass ``PALETTE_READY``.  Only an externally ``PROVEN`` mechanism with
    every gate passed is eligible for a separate photo scheduler.
    """

    if not isinstance(seeds, (list, tuple)) or not seeds:
        raise LightnessFamilyPlanError("seeds must be a non-empty sequence")
    if not isinstance(gate_evidence, (list, tuple)):
        raise LightnessFamilyPlanError("gate_evidence must be a sequence")
    if any(not isinstance(seed, LightnessFamilySeed) for seed in seeds):
        raise LightnessFamilyPlanError("every seed must be LightnessFamilySeed")
    if any(not isinstance(item, FamilyGateEvidence) for item in gate_evidence):
        raise LightnessFamilyPlanError(
            "every gate_evidence item must be FamilyGateEvidence"
        )

    seed_by_key: dict[tuple[Controller, str, str], LightnessFamilySeed] = {}
    endpoint_keys: set[tuple[Controller, str]] = set()
    for seed in seeds:
        if seed.key in seed_by_key:
            raise LightnessFamilyPlanError("duplicate family seed")
        endpoint_key = (seed.endpoint.controller, seed.endpoint.endpoint_id)
        if endpoint_key in endpoint_keys:
            raise LightnessFamilyPlanError(
                "one stable endpoint must not be paired with multiple mechanisms"
            )
        endpoint_keys.add(endpoint_key)
        seed_by_key[seed.key] = seed

    evidence_by_family: dict[
        tuple[Controller, str, str], dict[FamilyGate, FamilyGateEvidence]
    ] = {key: {} for key in seed_by_key}
    for item in gate_evidence:
        if item.family_key not in seed_by_key:
            raise LightnessFamilyPlanError(
                "gate evidence is not bound to an exact family seed"
            )
        by_gate = evidence_by_family[item.family_key]
        if item.gate in by_gate:
            raise LightnessFamilyPlanError("duplicate gate evidence for family")
        by_gate[item.gate] = item

    family_records: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    sorted_seeds = sorted(
        seeds,
        key=lambda item: (
            item.endpoint.controller.value,
            item.endpoint.endpoint_id,
            item.mechanism.mechanism_id,
        ),
    )
    for seed in sorted_seeds:
        states, photo_ready = _gate_states(seed, evidence_by_family[seed.key])
        batch = _batch(seed, photo_ready=photo_ready)
        batches.append(batch)
        family_records.append(
            {
                "family_id": seed.family_id,
                "controller": seed.endpoint.controller.value,
                "status": (
                    FamilyGate.PALETTE_READY.value
                    if photo_ready
                    else "PREPARED_NOT_LIVE_ADMITTED"
                ),
                "gate_order": [gate.value for gate in GATE_ORDER],
                "gates": states,
                "photo_schedule_admitted": photo_ready,
                "batch_id": batch["batch_id"],
            }
        )

    ready_family_ids = [
        record["family_id"]
        for record in family_records
        if record["photo_schedule_admitted"]
    ]
    all_ready = len(ready_family_ids) == len(family_records)
    any_ready = bool(ready_family_ids)
    identity = {
        "seeds": [
            {
                "endpoint": seed.endpoint.mapping(),
                "mechanism": seed.mechanism.mapping(),
            }
            for seed in sorted_seeds
        ],
        "gate_evidence": [
            item.mapping()
            for item in sorted(
                gate_evidence,
                key=lambda item: (
                    item.controller.value,
                    item.endpoint_id,
                    item.mechanism_id,
                    GATE_ORDER.index(item.gate),
                ),
            )
        ],
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "plan_id": f"LFP-{canonical_sha256(identity)[:24]}",
        "status": (
            FamilyGate.PALETTE_READY.value
            if all_ready
            else (
                "PARTIAL_PALETTE_READY" if any_ready else "PREPARED_NOT_LIVE_ADMITTED"
            )
        ),
        "offline_only": True,
        "gate_state_machine": {
            "order": [gate.value for gate in GATE_ORDER],
            "no_gate_may_be_skipped": True,
            "all_families_must_pass_before_photo_scheduling": False,
            "only_ready_families_may_be_scheduled": True,
        },
        "families": family_records,
        "batch_count": len(batches),
        "batches": batches,
        "photo_schedule_admission": {
            "admitted": any_ready,
            "ready_family_count": len(ready_family_ids),
            "ready_family_ids": ready_family_ids,
            "unready_families_excluded": True,
            "scope": "OFFLINE_STATIC_PHOTO_SCHEDULER_INPUT_ONLY",
            "requires_separate_hardware_authority": True,
            "hardware_action_ids": [],
        },
        "qualification_boundary": {
            "controllers_pooled": False,
            "cs1_cs2_batches_merged": False,
            "spatial_dithering_allowed": False,
            "automatic_new_colour_claim": False,
            "automatic_gray_level_claim": False,
            "automatic_lightness_level_claim": False,
            "qualified_new_colour_count_created_by_plan": 0,
            "qualified_gray_level_count_created_by_plan": 0,
            "qualified_lightness_level_count_created_by_plan": 0,
            "endpoint_and_mechanism_evidence_imported_not_created": True,
        },
        "execution_boundary": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "live_admitted": False,
            "live_authorization_generated": False,
            "executable_hardware_plan_generated": False,
            "relay_or_j2_operation_present": False,
            "flash_reset_refresh_operation_present": False,
        },
        "priority": {
            "stable_base_lightness_family_generalization": "ACTIVE",
            "broader_hue_search": "DEFERRED",
            "long_duration_reliability": "DEFERRED",
        },
        "documentation_projection": {
            "feature_path": "STABLE_BASE_HUE_LIGHTNESS_FAMILY_GENERALIZATION",
            "canonical_mapping_available": True,
            "gate_order": [gate.value for gate in GATE_ORDER],
            "status": (
                FamilyGate.PALETTE_READY.value
                if all_ready
                else (
                    "PARTIAL_PALETTE_READY"
                    if any_ready
                    else "PREPARED_NOT_LIVE_ADMITTED"
                )
            ),
        },
    }
    return attach_integrity(unsigned)


def verify_lightness_family_plan(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Verify canonical integrity and the immutable non-execution boundary."""

    if not isinstance(mapping, Mapping):
        raise LightnessFamilyPlanError("plan must be an object")
    try:
        unsigned = verify_integrity(mapping, "lightness family plan")
    except StaticPhotoContractError as error:
        raise LightnessFamilyPlanError(str(error)) from error
    if unsigned.get("schema_version") != SCHEMA_VERSION:
        raise LightnessFamilyPlanError("plan schema version differs")
    if unsigned.get("kind") != PLAN_KIND:
        raise LightnessFamilyPlanError("plan kind differs")
    machine = unsigned.get("gate_state_machine")
    if not isinstance(machine, Mapping) or machine.get("order") != [
        gate.value for gate in GATE_ORDER
    ]:
        raise LightnessFamilyPlanError("plan gate order differs")
    boundary = unsigned.get("execution_boundary")
    if not isinstance(boundary, Mapping) or any(
        boundary.get(key) is not False
        for key in (
            "hardware_accessed",
            "camera_accessed",
            "network_accessed",
            "live_admitted",
            "live_authorization_generated",
            "executable_hardware_plan_generated",
            "relay_or_j2_operation_present",
            "flash_reset_refresh_operation_present",
        )
    ):
        raise LightnessFamilyPlanError("plan execution boundary differs")
    return unsigned


def export_lightness_family_plan(
    mapping: Mapping[str, Any],
    path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a verified plan as stable, human-reviewable JSON."""

    verify_lightness_family_plan(mapping)
    output = Path(path)
    if output.exists() and not overwrite:
        raise LightnessFamilyPlanError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            mapping,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


__all__ = [
    "FamilyGate",
    "FamilyGateEvidence",
    "GATE_ORDER",
    "GateResult",
    "LightnessFamilyPlanError",
    "LightnessFamilySeed",
    "LightnessMechanism",
    "MechanismMaturity",
    "POSITION_BALANCED_CELLS",
    "REPLICAS_PER_RECIPE",
    "StableEndpoint",
    "build_lightness_family_plan",
    "export_lightness_family_plan",
    "verify_lightness_family_plan",
]
