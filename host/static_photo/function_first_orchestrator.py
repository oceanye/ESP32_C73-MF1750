"""Fail-closed offline orchestration for the MF1750 photo function chain.

This module keeps development ordered by capability rather than by the number
of visually different swatches.  It consumes an already verified stable-base
lightness-family plan and records the remaining *offline artifact* gates from
qualified recipe inventory through a fixed-photo execution bundle.

It never touches a camera, device, relay, network, serial port, GPIO, reset,
flash, refresh, or LUT writer.  It also never turns a candidate, camera review,
or spatial mixture into a qualified single-pixel colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    require_sha256,
    verify_integrity,
)
from .lightness_family_plan import (
    GATE_ORDER,
    LightnessFamilyPlanError,
    verify_lightness_family_plan,
)


SCHEMA_VERSION = 1
PLAN_KIND = "MF1750_FUNCTION_FIRST_STATIC_PHOTO_CHAIN"


class FunctionFirstChainError(ValueError):
    """Raised when a downstream function is asserted before its prerequisite."""


@dataclass(frozen=True)
class PhotoChainArtifacts:
    """Externally verified downstream artifacts, in strict dependency order.

    Each value is the SHA-256 of a distinct, sealed artifact.  Supplying a hash
    records lineage only; this class does not qualify the referenced evidence.
    """

    qualified_palette_inventory_sha256: str | None = None
    photo_pixel_mapping_sha256: str | None = None
    multi_lut_hold_schedule_sha256: str | None = None
    source_white_authority_sha256: str | None = None
    fixed_photo_execution_bundle_sha256: str | None = None

    def __post_init__(self) -> None:
        present: list[str] = []
        for field_name in (
            "qualified_palette_inventory_sha256",
            "photo_pixel_mapping_sha256",
            "multi_lut_hold_schedule_sha256",
            "source_white_authority_sha256",
            "fixed_photo_execution_bundle_sha256",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            try:
                validated = require_sha256(value, field_name)
            except StaticPhotoContractError as error:
                raise FunctionFirstChainError(str(error)) from error
            object.__setattr__(self, field_name, validated)
            present.append(validated)
        if len(present) != len(set(present)):
            raise FunctionFirstChainError(
                "each function-chain artifact must have a distinct SHA-256"
            )

    def mapping(self) -> dict[str, str | None]:
        return {
            "qualified_palette_inventory_sha256": (
                self.qualified_palette_inventory_sha256
            ),
            "photo_pixel_mapping_sha256": self.photo_pixel_mapping_sha256,
            "multi_lut_hold_schedule_sha256": (self.multi_lut_hold_schedule_sha256),
            "source_white_authority_sha256": self.source_white_authority_sha256,
            "fixed_photo_execution_bundle_sha256": (
                self.fixed_photo_execution_bundle_sha256
            ),
        }


def _next_family_gate(families: object) -> dict[str, Any] | None:
    if not isinstance(families, list):
        raise FunctionFirstChainError("lightness-family records differ")
    pending: list[dict[str, Any]] = []
    for family in families:
        if not isinstance(family, Mapping):
            raise FunctionFirstChainError("lightness-family record differs")
        gates = family.get("gates")
        if not isinstance(gates, list):
            raise FunctionFirstChainError("lightness-family gates differ")
        for gate in gates:
            if not isinstance(gate, Mapping):
                raise FunctionFirstChainError("lightness-family gate differs")
            status = gate.get("status")
            if status != "PASS":
                pending.append(
                    {
                        "family_id": family.get("family_id"),
                        "controller": family.get("controller"),
                        "gate": gate.get("gate"),
                        "status": status,
                    }
                )
                break
    if not pending:
        return None
    gate_rank = {gate.value: index for index, gate in enumerate(GATE_ORDER)}
    pending.sort(
        key=lambda item: (
            gate_rank.get(str(item["gate"]), len(gate_rank)),
            str(item["controller"]),
            str(item["family_id"]),
        )
    )
    return pending[0]


def _require_downstream_order(
    ready_family_count: int, artifacts: PhotoChainArtifacts
) -> None:
    values = artifacts.mapping()
    order = (
        "qualified_palette_inventory_sha256",
        "photo_pixel_mapping_sha256",
        "multi_lut_hold_schedule_sha256",
    )
    if not ready_family_count and any(values[name] is not None for name in order):
        raise FunctionFirstChainError(
            "downstream photo artifacts require at least one PALETTE_READY family"
        )
    for index, name in enumerate(order):
        if values[name] is None:
            if any(values[later] is not None for later in order[index + 1 :]):
                raise FunctionFirstChainError(
                    f"{order[index + 1]} cannot precede {name}"
                )
            break
    fixed = values["fixed_photo_execution_bundle_sha256"]
    source_white = values["source_white_authority_sha256"]
    schedule = values["multi_lut_hold_schedule_sha256"]
    if fixed is not None and (schedule is None or source_white is None):
        raise FunctionFirstChainError(
            "fixed-photo bundle requires a multi-LUT schedule and source-white authority"
        )
    if source_white is not None and schedule is None:
        raise FunctionFirstChainError(
            "source-white authority is recorded only after the photo schedule is sealed"
        )


def build_function_first_chain(
    lightness_family_plan: Mapping[str, Any],
    artifacts: PhotoChainArtifacts | None = None,
) -> dict[str, Any]:
    """Build a deterministic offline status and next-gate projection.

    One ready lightness family is sufficient to unlock a limited photo palette;
    unready families remain excluded.  Broader hue enumeration and long-duration
    reliability are deliberately outside the active path.
    """

    try:
        family = verify_lightness_family_plan(lightness_family_plan)
    except LightnessFamilyPlanError as error:
        raise FunctionFirstChainError(str(error)) from error
    artifact_set = artifacts or PhotoChainArtifacts()
    admission = family.get("photo_schedule_admission")
    if not isinstance(admission, Mapping):
        raise FunctionFirstChainError("lightness-family admission differs")
    ready_ids = admission.get("ready_family_ids")
    if not isinstance(ready_ids, list) or any(
        not isinstance(value, str) or not value for value in ready_ids
    ):
        raise FunctionFirstChainError("ready family identities differ")
    ready_family_count = len(ready_ids)
    _require_downstream_order(ready_family_count, artifact_set)

    values = artifact_set.mapping()
    family_next = _next_family_gate(family.get("families"))
    if ready_family_count == 0:
        next_gate = {
            "capability": "STABLE_BASE_LIGHTNESS_FAMILY",
            "operation": "COLLECT_OR_REVIEW_FAMILY_GATE_EVIDENCE",
            "family_gate": family_next,
        }
    elif values["qualified_palette_inventory_sha256"] is None:
        next_gate = {
            "capability": "USABLE_CONTROLLER_PALETTE",
            "operation": "BUILD_QUALIFIED_PALETTE_INVENTORY",
        }
    elif values["photo_pixel_mapping_sha256"] is None:
        next_gate = {
            "capability": "PHOTO_PIXEL_MAPPING",
            "operation": "MAP_PIXELS_TO_READY_FAMILY_SUBSET",
        }
    elif values["multi_lut_hold_schedule_sha256"] is None:
        next_gate = {
            "capability": "MULTI_LUT_LOCAL_HOLD_SCHEDULE",
            "operation": "SEAL_DIRECTIONAL_HOLD_SCHEDULE",
        }
    elif values["source_white_authority_sha256"] is None:
        next_gate = {
            "capability": "SOURCE_WHITE_AUTHORITY",
            "operation": "BIND_INDEPENDENT_SOURCE_WHITE",
        }
    elif values["fixed_photo_execution_bundle_sha256"] is None:
        next_gate = {
            "capability": "FIXED_STATIC_PHOTO_EXECUTION",
            "operation": "BUILD_FIXED_PHOTO_BUNDLE",
        }
    else:
        next_gate = {
            "capability": "FUNCTION_PATH_COMPLETE",
            "operation": "SEPARATELY_PLAN_MORE_HUES_OR_RELIABILITY",
        }

    stages = [
        {
            "stage": "STABLE_BASE_LIGHTNESS_FAMILY",
            "status": ("PARTIAL_READY" if ready_family_count else "EVIDENCE_PENDING"),
            "ready_family_count": ready_family_count,
            "ready_family_ids": sorted(ready_ids),
            "unready_families_excluded": True,
        },
        {
            "stage": "USABLE_CONTROLLER_PALETTE",
            "status": (
                "SEALED"
                if values["qualified_palette_inventory_sha256"]
                else ("READY_TO_BUILD" if ready_family_count else "BLOCKED")
            ),
        },
        {
            "stage": "PHOTO_PIXEL_MAPPING",
            "status": (
                "SEALED"
                if values["photo_pixel_mapping_sha256"]
                else (
                    "READY_TO_BUILD"
                    if values["qualified_palette_inventory_sha256"]
                    else "BLOCKED"
                )
            ),
        },
        {
            "stage": "MULTI_LUT_LOCAL_HOLD_SCHEDULE",
            "status": (
                "SEALED"
                if values["multi_lut_hold_schedule_sha256"]
                else (
                    "READY_TO_BUILD"
                    if values["photo_pixel_mapping_sha256"]
                    else "BLOCKED"
                )
            ),
        },
        {
            "stage": "FIXED_STATIC_PHOTO_EXECUTION",
            "status": (
                "SEALED"
                if values["fixed_photo_execution_bundle_sha256"]
                else (
                    "READY_TO_BUILD"
                    if values["multi_lut_hold_schedule_sha256"]
                    and values["source_white_authority_sha256"]
                    else "BLOCKED"
                )
            ),
        },
    ]
    complete = values["fixed_photo_execution_bundle_sha256"] is not None
    source_plan_integrity = lightness_family_plan.get("integrity")
    if not isinstance(source_plan_integrity, Mapping):
        raise FunctionFirstChainError("lightness-family integrity differs")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "status": (
            "OFFLINE_FUNCTION_PATH_COMPLETE"
            if complete
            else "OFFLINE_FUNCTION_PATH_IN_PROGRESS"
        ),
        "source_lightness_family_plan": {
            "plan_id": family.get("plan_id"),
            "canonical_sha256": source_plan_integrity.get("canonical_sha256"),
        },
        "artifacts": values,
        "stages": stages,
        "next_gate": next_gate,
        "policy": {
            "function_expansion_before_more_hues": True,
            "one_ready_family_unlocks_limited_palette_subset": True,
            "all_families_required_before_photo_mapping": False,
            "controllers_pooled": False,
            "spatial_dithering_as_single_pixel_colour": False,
            "automatic_colour_qualification": False,
            "broader_hue_enumeration": (
                "ELIGIBLE_FOR_SEPARATE_PLANNING" if complete else "DEFERRED"
            ),
            "third_repeat_and_long_reliability": (
                "ELIGIBLE_FOR_SEPARATE_PLANNING" if complete else "DEFERRED"
            ),
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
    return attach_integrity(unsigned)


def verify_function_first_chain(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Verify canonical integrity and the immutable offline boundary."""

    if not isinstance(mapping, Mapping):
        raise FunctionFirstChainError("function-first chain must be an object")
    try:
        unsigned = verify_integrity(mapping, "function-first chain")
    except StaticPhotoContractError as error:
        raise FunctionFirstChainError(str(error)) from error
    if unsigned.get("schema_version") != SCHEMA_VERSION:
        raise FunctionFirstChainError("function-first schema version differs")
    if unsigned.get("kind") != PLAN_KIND:
        raise FunctionFirstChainError("function-first kind differs")
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
    }:
        raise FunctionFirstChainError("function-first execution boundary differs")
    return unsigned


def export_function_first_chain(
    mapping: Mapping[str, Any], path: str | Path, *, overwrite: bool = False
) -> Path:
    """Export a verified function-chain projection without overwriting by default."""

    verify_function_first_chain(mapping)
    output = Path(path)
    if output.exists() and not overwrite:
        raise FunctionFirstChainError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
