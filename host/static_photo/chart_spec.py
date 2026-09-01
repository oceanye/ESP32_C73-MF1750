"""Strict model for a photographed 24-patch colour chart."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    finite_triple,
    require_exact_keys,
    require_sha256,
    require_text,
    verify_integrity,
)


CHART_SPEC_SCHEMA_VERSION = 1


class ChartSpecError(StaticPhotoContractError):
    """Raised when a chart profile is incomplete or untraceable."""


class ReferenceGrade(str, Enum):
    LAYOUT_ONLY = "layout_only"
    VENDOR_REFERENCE = "vendor_reference"
    BATCH_MEASURED = "batch_measured"


@dataclass(frozen=True)
class ChartPatch:
    patch_id: str
    row: int
    column: int
    reference_lab: tuple[float, float, float] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", require_text(self.patch_id, "patch_id"))
        for label in ("row", "column"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ChartSpecError(f"patch {label} must be a non-negative integer")
        if self.reference_lab is not None:
            lab = finite_triple(
                self.reference_lab, f"patch {self.patch_id} reference_lab"
            )
            if not 0.0 <= lab[0] <= 100.0:
                raise ChartSpecError("reference Lab L* must be in [0, 100]")
            object.__setattr__(self, "reference_lab", lab)

    def mapping(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "row": self.row,
            "column": self.column,
            "reference_lab": (
                None if self.reference_lab is None else list(self.reference_lab)
            ),
        }


@dataclass(frozen=True)
class ChartSpec:
    chart_id: str
    brand: str
    model: str
    rows: int
    columns: int
    reference_grade: ReferenceGrade
    reference_source: str
    reference_artifact_sha256: str | None
    illuminant: str
    observer: str
    patch_inset_fraction: float
    patches: tuple[ChartPatch, ...]

    def __post_init__(self) -> None:
        for label in ("chart_id", "brand", "model", "reference_source"):
            object.__setattr__(self, label, require_text(getattr(self, label), label))
        for label in ("rows", "columns"):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise ChartSpecError(f"{label} must be a positive integer")
        if self.rows * self.columns != 24:
            raise ChartSpecError(
                "this implementation requires exactly 24 chart patches"
            )
        try:
            grade = (
                self.reference_grade
                if isinstance(self.reference_grade, ReferenceGrade)
                else ReferenceGrade(self.reference_grade)
            )
        except ValueError as error:
            raise ChartSpecError("reference_grade differs") from error
        object.__setattr__(self, "reference_grade", grade)
        if self.illuminant != "D65" or self.observer != "2deg":
            raise ChartSpecError("chart reference values must be adapted to D65/2deg")
        if not isinstance(self.patch_inset_fraction, (int, float)) or isinstance(
            self.patch_inset_fraction, bool
        ):
            raise ChartSpecError("patch_inset_fraction must be numeric")
        inset = float(self.patch_inset_fraction)
        if not 0.05 <= inset <= 0.4:
            raise ChartSpecError("patch_inset_fraction must be in [0.05, 0.4]")
        object.__setattr__(self, "patch_inset_fraction", inset)
        if not isinstance(self.patches, (tuple, list)) or not all(
            isinstance(patch, ChartPatch) for patch in self.patches
        ):
            raise ChartSpecError("patches must contain ChartPatch values")
        if len(self.patches) != 24:
            raise ChartSpecError("chart must contain exactly 24 patches")
        identities = [(patch.row, patch.column) for patch in self.patches]
        if len(set(identities)) != 24 or set(identities) != {
            (row, column) for row in range(self.rows) for column in range(self.columns)
        }:
            raise ChartSpecError("patch row/column coverage differs")
        patch_ids = [patch.patch_id for patch in self.patches]
        if len(set(patch_ids)) != 24:
            raise ChartSpecError("patch_id values must be unique")
        reference_count = sum(patch.reference_lab is not None for patch in self.patches)
        if grade is ReferenceGrade.LAYOUT_ONLY:
            if reference_count:
                raise ChartSpecError("layout_only chart must not contain reference Lab")
            if self.reference_artifact_sha256 is not None:
                raise ChartSpecError(
                    "layout_only chart must not bind a reference artifact"
                )
        else:
            if reference_count != 24:
                raise ChartSpecError("referenced chart requires Lab for all 24 patches")
            require_sha256(
                self.reference_artifact_sha256,
                "reference_artifact_sha256",
            )
        object.__setattr__(
            self,
            "patches",
            tuple(sorted(self.patches, key=lambda patch: (patch.row, patch.column))),
        )

    @property
    def has_reference_values(self) -> bool:
        return self.reference_grade is not ReferenceGrade.LAYOUT_ONLY

    def unsigned_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": CHART_SPEC_SCHEMA_VERSION,
            "kind": "MF17506_24_PATCH_CHART_SPEC",
            "chart_id": self.chart_id,
            "brand": self.brand,
            "model": self.model,
            "rows": self.rows,
            "columns": self.columns,
            "reference_grade": self.reference_grade.value,
            "reference_source": self.reference_source,
            "reference_artifact_sha256": self.reference_artifact_sha256,
            "illuminant": self.illuminant,
            "observer": self.observer,
            "patch_inset_fraction": self.patch_inset_fraction,
            "patches": [patch.mapping() for patch in self.patches],
        }

    def mapping(self) -> dict[str, Any]:
        return attach_integrity(self.unsigned_mapping())


def chart_spec_from_mapping(data: Mapping[str, Any]) -> ChartSpec:
    try:
        unsigned = verify_integrity(data, "chart spec")
        require_exact_keys(
            unsigned,
            {
                "schema_version",
                "kind",
                "chart_id",
                "brand",
                "model",
                "rows",
                "columns",
                "reference_grade",
                "reference_source",
                "reference_artifact_sha256",
                "illuminant",
                "observer",
                "patch_inset_fraction",
                "patches",
            },
            "chart spec",
        )
        if unsigned["schema_version"] != CHART_SPEC_SCHEMA_VERSION:
            raise ChartSpecError("chart spec schema_version differs")
        if unsigned["kind"] != "MF17506_24_PATCH_CHART_SPEC":
            raise ChartSpecError("chart spec kind differs")
        raw_patches = unsigned["patches"]
        if not isinstance(raw_patches, list):
            raise ChartSpecError("patches must be a list")
        patches = []
        for index, raw in enumerate(raw_patches):
            if not isinstance(raw, Mapping):
                raise ChartSpecError(f"patch {index} must be an object")
            require_exact_keys(
                raw,
                {"patch_id", "row", "column", "reference_lab"},
                f"patch {index}",
            )
            reference_lab = raw["reference_lab"]
            patches.append(
                ChartPatch(
                    raw["patch_id"],
                    raw["row"],
                    raw["column"],
                    None
                    if reference_lab is None
                    else finite_triple(reference_lab, f"patch {index} reference_lab"),
                )
            )
        return ChartSpec(
            unsigned["chart_id"],
            unsigned["brand"],
            unsigned["model"],
            unsigned["rows"],
            unsigned["columns"],
            ReferenceGrade(unsigned["reference_grade"]),
            unsigned["reference_source"],
            unsigned["reference_artifact_sha256"],
            unsigned["illuminant"],
            unsigned["observer"],
            unsigned["patch_inset_fraction"],
            tuple(patches),
        )
    except StaticPhotoContractError as error:
        if isinstance(error, ChartSpecError):
            raise
        raise ChartSpecError(str(error)) from error
    except (KeyError, TypeError, ValueError) as error:
        raise ChartSpecError(f"chart spec value differs: {error}") from error


def load_chart_spec(path: str | Path) -> ChartSpec:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ChartSpecError(f"cannot load chart spec: {error}") from error
    if not isinstance(raw, Mapping):
        raise ChartSpecError("chart spec must be an object")
    return chart_spec_from_mapping(raw)
