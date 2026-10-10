"""Fail-closed, read-only KiCad board preflight for a JLCPCB handoff.

Run with KiCad's bundled Python so that ``pcbnew`` is available::

    python audit_kicad_jlcpcb.py BOARD.kicad_pcb CONFIG.json OUTPUT.json

The board is loaded but never saved. A JSON report is written for both passing
and failing audits. Audit failures return 1; input/config/runtime errors return 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import pcbnew


class ConfigError(ValueError):
    """Raised when the audit configuration is incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _natural_ref_key(reference: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", reference)
    return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)


def _sorted_refs(references: Iterable[str]) -> list[str]:
    return sorted(references, key=_natural_ref_key)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a JSON object")
    return value


def _string_list(
    mapping: dict[str, Any], key: str, label: str, *, allow_empty: bool = True
) -> list[str]:
    if key not in mapping:
        raise ConfigError(f"{label}.{key} is required")
    value = mapping[key]
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ConfigError(f"{label}.{key} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise ConfigError(f"{label}.{key} must not be empty")
    if len(value) != len(set(value)):
        raise ConfigError(f"{label}.{key} contains duplicate values")
    return value


def _number(mapping: dict[str, Any], key: str, label: str) -> float:
    if key not in mapping:
        raise ConfigError(f"{label}.{key} is required")
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label}.{key} must be a number")
    return float(value)


def _integer(mapping: dict[str, Any], key: str, label: str) -> int:
    if key not in mapping:
        raise ConfigError(f"{label}.{key} is required")
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label}.{key} must be an integer")
    return value


def _validate_config(raw: Any) -> dict[str, Any]:
    config = _mapping(raw, "config")
    schema = config.get("schema", 1)
    if schema != 1:
        raise ConfigError(f"config.schema must be 1, got {schema!r}")

    if "copper_layers" not in config:
        raise ConfigError("config.copper_layers is required")
    copper_layers = config["copper_layers"]
    if isinstance(copper_layers, bool) or not isinstance(copper_layers, (int, list)):
        raise ConfigError(
            "config.copper_layers must be a positive count or an ordered layer-name array"
        )
    if isinstance(copper_layers, int):
        if copper_layers <= 0:
            raise ConfigError("config.copper_layers must be positive")
    elif (
        not copper_layers
        or any(not isinstance(item, str) or not item.strip() for item in copper_layers)
        or len(copper_layers) != len(set(copper_layers))
    ):
        raise ConfigError(
            "config.copper_layers must be a non-empty array of unique layer names"
        )

    paste = _mapping(config.get("paste"), "config.paste")
    required_paste_layers = _string_list(
        paste, "required_layers", "config.paste", allow_empty=False
    )
    unsupported_paste_layers = set(required_paste_layers) - {"F.Paste", "B.Paste"}
    if unsupported_paste_layers:
        raise ConfigError(
            "config.paste.required_layers contains unsupported names: "
            + ", ".join(sorted(unsupported_paste_layers))
        )

    edge = _mapping(config.get("edge_cuts"), "config.edge_cuts")
    width = _number(edge, "width_mm", "config.edge_cuts")
    height = _number(edge, "height_mm", "config.edge_cuts")
    tolerance = _number(edge, "tolerance_mm", "config.edge_cuts")
    if width <= 0 or height <= 0:
        raise ConfigError("config.edge_cuts width_mm and height_mm must be positive")
    if tolerance < 0:
        raise ConfigError("config.edge_cuts.tolerance_mm must be non-negative")

    assembly = _mapping(config.get("assembly"), "config.assembly")
    manual_refs = _string_list(assembly, "manual_refs", "config.assembly")
    nonassembly_refs = _string_list(assembly, "nonassembly_refs", "config.assembly")
    fit_smt_refs = _string_list(assembly, "fit_smt_refs", "config.assembly")
    dnp_refs = _string_list(assembly, "dnp_refs", "config.assembly")
    fit_refs = _string_list(assembly, "fit_refs", "config.assembly")
    allowed_smt_layers = assembly.get("allowed_smt_layers", ["F.Cu"])
    if (
        not isinstance(allowed_smt_layers, list)
        or not allowed_smt_layers
        or any(
            not isinstance(item, str) or not item.strip() for item in allowed_smt_layers
        )
        or len(allowed_smt_layers) != len(set(allowed_smt_layers))
    ):
        raise ConfigError(
            "config.assembly.allowed_smt_layers must be a non-empty array of unique layer names"
        )
    if set(manual_refs) & set(nonassembly_refs):
        raise ConfigError(
            "config.assembly manual_refs and nonassembly_refs must be disjoint"
        )
    excluded_or_dnp = set(manual_refs) | set(nonassembly_refs) | set(dnp_refs)
    overlap = set(fit_smt_refs) & excluded_or_dnp
    if overlap:
        raise ConfigError(
            "config.assembly.fit_smt_refs overlap excluded/DNP refs: "
            + ", ".join(_sorted_refs(overlap))
        )
    overlap = set(fit_refs) & set(dnp_refs)
    if overlap:
        raise ConfigError(
            "config.assembly.fit_refs overlap dnp_refs: "
            + ", ".join(_sorted_refs(overlap))
        )

    fab_courtyard = _mapping(config.get("fab_courtyard"), "config.fab_courtyard")
    minimum_clearance = _number(
        fab_courtyard, "minimum_clearance_mm", "config.fab_courtyard"
    )
    if minimum_clearance < 0:
        raise ConfigError(
            "config.fab_courtyard.minimum_clearance_mm must be non-negative"
        )

    body_edge = _mapping(config.get("body_edge"), "config.body_edge")
    body_edge_clearance = _number(body_edge, "minimum_clearance_mm", "config.body_edge")
    if body_edge_clearance < 0:
        raise ConfigError("config.body_edge.minimum_clearance_mm must be non-negative")

    courtyard_edge_clearance: float | None = None
    if "courtyard_edge" in config:
        courtyard_edge = _mapping(config.get("courtyard_edge"), "config.courtyard_edge")
        courtyard_edge_clearance = _number(
            courtyard_edge, "minimum_clearance_mm", "config.courtyard_edge"
        )
        if courtyard_edge_clearance < 0:
            raise ConfigError(
                "config.courtyard_edge.minimum_clearance_mm must be non-negative"
            )

    vias = _mapping(config.get("vias"), "config.vias")
    allowed_via_types = _string_list(
        vias, "allowed_types", "config.vias", allow_empty=False
    )
    known_via_types = {"through", "blind", "buried", "microvia", "not_defined"}
    unknown_via_types = set(allowed_via_types) - known_via_types
    if unknown_via_types:
        raise ConfigError(
            "config.vias.allowed_types contains unsupported names: "
            + ", ".join(sorted(unknown_via_types))
        )

    rule_areas = _mapping(config.get("rule_areas"), "config.rule_areas")
    required_rule_layers = _string_list(
        rule_areas,
        "required_copper_layers",
        "config.rule_areas",
        allow_empty=False,
    )
    minimum_rule_areas = _integer(rule_areas, "minimum_count", "config.rule_areas")
    if minimum_rule_areas < 0:
        raise ConfigError("config.rule_areas.minimum_count must be non-negative")
    expected_rule_names: list[str] | None = None
    if "expected_names" in rule_areas:
        expected_rule_names = _string_list(
            rule_areas, "expected_names", "config.rule_areas"
        )

    return {
        "schema": 1,
        "copper_layers": copper_layers,
        "paste": {"required_layers": required_paste_layers},
        "edge_cuts": {
            "width_mm": width,
            "height_mm": height,
            "tolerance_mm": tolerance,
        },
        "assembly": {
            "manual_refs": manual_refs,
            "nonassembly_refs": nonassembly_refs,
            "fit_smt_refs": fit_smt_refs,
            "dnp_refs": dnp_refs,
            "fit_refs": fit_refs,
            "allowed_smt_layers": allowed_smt_layers,
        },
        "fab_courtyard": {"minimum_clearance_mm": minimum_clearance},
        "body_edge": {"minimum_clearance_mm": body_edge_clearance},
        "courtyard_edge": (
            {"minimum_clearance_mm": courtyard_edge_clearance}
            if courtyard_edge_clearance is not None
            else None
        ),
        "vias": {"allowed_types": allowed_via_types},
        "rule_areas": {
            "required_copper_layers": required_rule_layers,
            "minimum_count": minimum_rule_areas,
            "expected_names": expected_rule_names,
        },
    }


def _check(details: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    return {"status": "PASS" if not errors else "FAIL", **details, "errors": errors}


def _audit_copper(board: pcbnew.BOARD, expected: int | list[str]) -> dict[str, Any]:
    actual = [board.GetLayerName(layer) for layer in board.GetEnabledLayers().CuStack()]
    errors: list[str] = []
    if isinstance(expected, int):
        if len(actual) != expected:
            errors.append(f"expected {expected} copper layers, found {len(actual)}")
    elif actual != expected:
        errors.append(f"expected copper stack {expected}, found {actual}")
    return _check(
        {"expected": expected, "actual": actual, "count": len(actual)}, errors
    )


def _audit_paste(board: pcbnew.BOARD, required_layers: list[str]) -> dict[str, Any]:
    states = {
        "F.Paste": bool(board.IsLayerEnabled(pcbnew.F_Paste)),
        "B.Paste": bool(board.IsLayerEnabled(pcbnew.B_Paste)),
    }
    errors = [
        f"required paste layer {name} is not enabled"
        for name in required_layers
        if not states[name]
    ]
    return _check({"required_layers": required_layers, "enabled": states}, errors)


def _rect_from_edge_drawings(
    drawings: list[Any],
) -> tuple[tuple[float, float, float, float] | None, str, list[str]]:
    errors: list[str] = []
    if len(drawings) == 1 and drawings[0].GetShapeStr().casefold() == "rect":
        start = drawings[0].GetStart()
        end = drawings[0].GetEnd()
        xs = sorted((pcbnew.ToMM(start.x), pcbnew.ToMM(end.x)))
        ys = sorted((pcbnew.ToMM(start.y), pcbnew.ToMM(end.y)))
        return (xs[0], ys[0], xs[1], ys[1]), "single_rect", errors

    if len(drawings) != 4 or any(
        drawing.GetShapeStr().casefold() not in {"line", "segment"}
        for drawing in drawings
    ):
        errors.append(
            "Edge.Cuts must be one rectangle or exactly four straight segments"
        )
        return None, "unsupported", errors

    segments: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    points: set[tuple[int, int]] = set()
    for drawing in drawings:
        start = (drawing.GetStart().x, drawing.GetStart().y)
        end = (drawing.GetEnd().x, drawing.GetEnd().y)
        if start == end or (start[0] != end[0] and start[1] != end[1]):
            errors.append(
                "four-segment Edge.Cuts contains a zero-length or diagonal side"
            )
            return None, "four_segments", errors
        points.update((start, end))
        segments.add(tuple(sorted((start, end))))

    xs = sorted({point[0] for point in points})
    ys = sorted({point[1] for point in points})
    if len(xs) != 2 or len(ys) != 2:
        errors.append("four-segment Edge.Cuts is not an axis-aligned rectangle")
        return None, "four_segments", errors
    corners = {(x, y) for x in xs for y in ys}
    expected_segments = {
        tuple(sorted(((xs[0], ys[0]), (xs[1], ys[0])))),
        tuple(sorted(((xs[1], ys[0]), (xs[1], ys[1])))),
        tuple(sorted(((xs[1], ys[1]), (xs[0], ys[1])))),
        tuple(sorted(((xs[0], ys[1]), (xs[0], ys[0])))),
    }
    if points != corners or segments != expected_segments:
        errors.append("four-segment Edge.Cuts does not form one closed rectangle")
        return None, "four_segments", errors
    return (
        (
            pcbnew.ToMM(xs[0]),
            pcbnew.ToMM(ys[0]),
            pcbnew.ToMM(xs[1]),
            pcbnew.ToMM(ys[1]),
        ),
        "four_segments",
        errors,
    )


def _audit_edge_cuts(
    board: pcbnew.BOARD, config: dict[str, float]
) -> tuple[dict[str, Any], tuple[float, float, float, float] | None]:
    drawings = [
        drawing
        for drawing in board.GetDrawings()
        if drawing.GetLayer() == pcbnew.Edge_Cuts
    ]
    bounds, representation, errors = _rect_from_edge_drawings(drawings)
    width = bounds[2] - bounds[0] if bounds is not None else None
    height = bounds[3] - bounds[1] if bounds is not None else None
    tolerance = config["tolerance_mm"]
    if width is not None and abs(width - config["width_mm"]) > tolerance:
        errors.append(
            f"Edge.Cuts width {width:.6f} mm differs from expected "
            f"{config['width_mm']:.6f} mm by more than {tolerance:.6f} mm"
        )
    if height is not None and abs(height - config["height_mm"]) > tolerance:
        errors.append(
            f"Edge.Cuts height {height:.6f} mm differs from expected "
            f"{config['height_mm']:.6f} mm by more than {tolerance:.6f} mm"
        )
    check = _check(
        {
            "representation": representation,
            "drawing_count": len(drawings),
            "expected_width_mm": config["width_mm"],
            "expected_height_mm": config["height_mm"],
            "tolerance_mm": tolerance,
            "actual_width_mm": width,
            "actual_height_mm": height,
            "bounds_mm": (
                {
                    "left": bounds[0],
                    "top": bounds[1],
                    "right": bounds[2],
                    "bottom": bounds[3],
                }
                if bounds is not None
                else None
            ),
        },
        errors,
    )
    return check, bounds


def _footprints_by_reference(
    board: pcbnew.BOARD,
) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {}
    duplicates: list[str] = []
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        if reference in result:
            duplicates.append(reference)
        else:
            result[reference] = footprint
    return result, duplicates


def _audit_assembly(
    board: pcbnew.BOARD, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    footprints, duplicates = _footprints_by_reference(board)
    errors = [
        f"duplicate footprint reference: {ref}" for ref in _sorted_refs(duplicates)
    ]
    known_refs = set(footprints)
    manual_refs = set(config["manual_refs"])
    nonassembly_refs = set(config["nonassembly_refs"])
    expected_fit_smt = set(config["fit_smt_refs"])
    expected_dnp = set(config["dnp_refs"])
    required_fit = set(config["fit_refs"])

    for category, references in (
        ("manual_refs", manual_refs),
        ("nonassembly_refs", nonassembly_refs),
        ("fit_smt_refs", expected_fit_smt),
        ("dnp_refs", expected_dnp),
        ("fit_refs", required_fit),
    ):
        unknown = references - known_refs
        if unknown:
            errors.append(
                f"{category} contains unknown footprint refs: "
                + ", ".join(_sorted_refs(unknown))
            )

    actual_dnp = {ref for ref, footprint in footprints.items() if footprint.IsDNP()}
    missing_dnp = expected_dnp - actual_dnp
    unexpected_dnp = actual_dnp - expected_dnp
    if missing_dnp:
        errors.append(
            "configured DNP refs are FIT on the board: "
            + ", ".join(_sorted_refs(missing_dnp))
        )
    if unexpected_dnp:
        errors.append(
            "board has unconfigured DNP refs: "
            + ", ".join(_sorted_refs(unexpected_dnp))
        )
    wrongly_dnp_fit = required_fit & actual_dnp
    if wrongly_dnp_fit:
        errors.append(
            "configured FIT refs are marked DNP: "
            + ", ".join(_sorted_refs(wrongly_dnp_fit))
        )

    excluded = manual_refs | nonassembly_refs
    actual_fit_smt: dict[str, Any] = {}
    for ref, footprint in footprints.items():
        pad_attributes = [pad.GetAttribute() for pad in footprint.Pads()]
        has_smd = pcbnew.PAD_ATTRIB_SMD in pad_attributes
        has_through_hole = pcbnew.PAD_ATTRIB_PTH in pad_attributes
        if (
            not footprint.IsDNP()
            and ref not in excluded
            and has_smd
            and not has_through_hole
        ):
            actual_fit_smt[ref] = footprint

    actual_fit_set = set(actual_fit_smt)
    missing_fit_smt = expected_fit_smt - actual_fit_set
    unexpected_fit_smt = actual_fit_set - expected_fit_smt
    if missing_fit_smt:
        errors.append(
            "configured FIT SMT refs are not eligible fitted SMT footprints: "
            + ", ".join(_sorted_refs(missing_fit_smt))
        )
    if unexpected_fit_smt:
        errors.append(
            "unconfigured FIT SMT footprints remain after manual/nonassembly exclusions: "
            + ", ".join(_sorted_refs(unexpected_fit_smt))
        )

    allowed_layers = set(config["allowed_smt_layers"])
    layer_by_ref = {
        ref: board.GetLayerName(footprint.GetLayer())
        for ref, footprint in actual_fit_smt.items()
    }
    invalid_sides = {
        ref: layer for ref, layer in layer_by_ref.items() if layer not in allowed_layers
    }
    if invalid_sides:
        errors.append(
            "FIT SMT footprints on disallowed layers: "
            + ", ".join(
                f"{ref}={invalid_sides[ref]}" for ref in _sorted_refs(invalid_sides)
            )
        )

    details = {
        "manual_refs": _sorted_refs(manual_refs),
        "nonassembly_refs": _sorted_refs(nonassembly_refs),
        "expected_fit_smt_refs": _sorted_refs(expected_fit_smt),
        "actual_fit_smt_refs": _sorted_refs(actual_fit_set),
        "fit_smt_count": len(actual_fit_set),
        "expected_dnp_refs": _sorted_refs(expected_dnp),
        "actual_dnp_refs": _sorted_refs(actual_dnp),
        "required_fit_refs": _sorted_refs(required_fit),
        "allowed_smt_layers": config["allowed_smt_layers"],
        "actual_smt_layers": {
            ref: layer_by_ref[ref] for ref in _sorted_refs(layer_by_ref)
        },
    }
    return _check(details, errors), actual_fit_smt


def _shape_bounds(
    footprint: Any, layer: int
) -> tuple[float, float, float, float] | None:
    boxes = [
        item.GetBoundingBox()
        for item in footprint.GraphicalItems()
        if isinstance(item, pcbnew.PCB_SHAPE) and item.GetLayer() == layer
    ]
    if not boxes:
        return None
    left = min(box.GetX() for box in boxes)
    top = min(box.GetY() for box in boxes)
    right = max(box.GetX() + box.GetWidth() for box in boxes)
    bottom = max(box.GetY() + box.GetHeight() for box in boxes)
    return tuple(pcbnew.ToMM(value) for value in (left, top, right, bottom))


_SIDE_GEOMETRY = {
    int(pcbnew.F_Cu): {
        "footprint_layer": "F.Cu",
        "fab_layer": int(pcbnew.F_Fab),
        "fab_layer_name": "F.Fab",
        "courtyard_layer": int(pcbnew.F_CrtYd),
        "courtyard_layer_name": "F.CrtYd",
    },
    int(pcbnew.B_Cu): {
        "footprint_layer": "B.Cu",
        "fab_layer": int(pcbnew.B_Fab),
        "fab_layer_name": "B.Fab",
        "courtyard_layer": int(pcbnew.B_CrtYd),
        "courtyard_layer_name": "B.CrtYd",
    },
}


def _side_geometry(footprint: Any) -> dict[str, Any] | None:
    return _SIDE_GEOMETRY.get(int(footprint.GetLayer()))


def _footprint_layer_name(footprint: Any) -> str:
    layer = int(footprint.GetLayer())
    try:
        return pcbnew.LayerName(layer)
    except Exception:
        return f"unknown:{layer}"


def _audit_layer_edge_clearance(
    fit_smt: dict[str, Any],
    edge_bounds: tuple[float, float, float, float] | None,
    geometry_kind: str,
    minimum_clearance_mm: float,
) -> dict[str, Any]:
    if geometry_kind not in {"fab", "courtyard"}:
        raise ValueError(f"unsupported geometry kind: {geometry_kind}")
    errors: list[str] = []
    per_reference: dict[str, Any] = {}
    failed_references: set[str] = set()
    observed: list[tuple[float, str, str]] = []
    if edge_bounds is None:
        errors.append(
            "rectangular Edge.Cuts bounds are unavailable; edge clearance is unproven"
        )
    else:
        edge_left, edge_top, edge_right, edge_bottom = edge_bounds

    for ref in _sorted_refs(fit_smt):
        footprint = fit_smt[ref]
        side = _side_geometry(footprint)
        footprint_layer = _footprint_layer_name(footprint)
        if side is None:
            failed_references.add(ref)
            errors.append(
                f"{ref} is on unsupported footprint layer {footprint_layer}; "
                "only F.Cu and B.Cu are auditable"
            )
            per_reference[ref] = {
                "status": "FAIL",
                "footprint_layer": footprint_layer,
                "geometry_layer": None,
                "error": "unsupported footprint layer",
            }
            continue

        geometry_layer = side[f"{geometry_kind}_layer"]
        geometry_layer_name = side[f"{geometry_kind}_layer_name"]
        if edge_bounds is None:
            failed_references.add(ref)
            per_reference[ref] = {
                "status": "FAIL",
                "footprint_layer": side["footprint_layer"],
                "geometry_layer": geometry_layer_name,
                "error": "rectangular Edge.Cuts bounds unavailable",
            }
            continue

        geometry = _shape_bounds(footprint, geometry_layer)
        if geometry is None:
            failed_references.add(ref)
            errors.append(f"{ref} lacks PCB_SHAPE geometry on {geometry_layer_name}")
            per_reference[ref] = {
                "status": "FAIL",
                "footprint_layer": side["footprint_layer"],
                "geometry_layer": geometry_layer_name,
                "missing_layer": geometry_layer_name,
            }
            continue

        left, top, right, bottom = geometry
        clearances = {
            "left": left - edge_left,
            "top": top - edge_top,
            "right": edge_right - right,
            "bottom": edge_bottom - bottom,
        }
        failed_sides = [
            side
            for side, clearance in clearances.items()
            if clearance + 1e-9 < minimum_clearance_mm
        ]
        for clearance_side, clearance in clearances.items():
            observed.append((clearance, ref, clearance_side))
        if failed_sides:
            failed_references.add(ref)
            errors.append(
                f"{ref} {geometry_layer_name}-to-Edge.Cuts clearance below "
                f"{minimum_clearance_mm:.6f} mm on: "
                + ", ".join(
                    f"{side}={clearances[side]:.6f} mm" for side in failed_sides
                )
            )
        per_reference[ref] = {
            "status": "FAIL" if failed_sides else "PASS",
            "footprint_layer": side["footprint_layer"],
            "geometry_layer": geometry_layer_name,
            "clearance_mm": {
                side: round(value, 6) for side, value in clearances.items()
            },
            "minimum_clearance_mm": round(min(clearances.values()), 6),
            "geometry_bounds_mm": {
                "left": round(left, 6),
                "top": round(top, 6),
                "right": round(right, 6),
                "bottom": round(bottom, 6),
            },
        }

    minimum_observed: float | None = None
    minimum_location: dict[str, str] | None = None
    if observed:
        minimum_observed, reference, side = min(observed)
        minimum_location = {"reference": reference, "side": side}
    return _check(
        {
            "geometry_kind": geometry_kind,
            "geometry_layers_by_side": {
                "F.Cu": "F.Fab" if geometry_kind == "fab" else "F.CrtYd",
                "B.Cu": "B.Fab" if geometry_kind == "fab" else "B.CrtYd",
            },
            "required_minimum_clearance_mm": minimum_clearance_mm,
            "edge_bounds_mm": (
                {
                    "left": edge_bounds[0],
                    "top": edge_bounds[1],
                    "right": edge_bounds[2],
                    "bottom": edge_bounds[3],
                }
                if edge_bounds is not None
                else None
            ),
            "observed_minimum_clearance_mm": (
                round(minimum_observed, 6) if minimum_observed is not None else None
            ),
            "observed_minimum_location": minimum_location,
            "failed_references": _sorted_refs(failed_references),
            "per_reference": per_reference,
        },
        errors,
    )


def _audit_fab_courtyard(
    fit_smt: dict[str, Any], minimum_clearance_mm: float
) -> dict[str, Any]:
    errors: list[str] = []
    per_reference: dict[str, Any] = {}
    observed: list[tuple[float, str, str]] = []
    for ref in _sorted_refs(fit_smt):
        footprint = fit_smt[ref]
        side = _side_geometry(footprint)
        footprint_layer = _footprint_layer_name(footprint)
        if side is None:
            errors.append(
                f"{ref} is on unsupported footprint layer {footprint_layer}; "
                "only F.Cu and B.Cu are auditable"
            )
            per_reference[ref] = {
                "status": "FAIL",
                "footprint_layer": footprint_layer,
                "fab_layer": None,
                "courtyard_layer": None,
                "error": "unsupported footprint layer",
            }
            continue

        fab_layer_name = side["fab_layer_name"]
        courtyard_layer_name = side["courtyard_layer_name"]
        fab = _shape_bounds(footprint, side["fab_layer"])
        courtyard = _shape_bounds(footprint, side["courtyard_layer"])
        if fab is None or courtyard is None:
            missing = []
            if fab is None:
                missing.append(fab_layer_name)
            if courtyard is None:
                missing.append(courtyard_layer_name)
            errors.append(f"{ref} lacks PCB_SHAPE geometry on {', '.join(missing)}")
            per_reference[ref] = {
                "status": "FAIL",
                "footprint_layer": side["footprint_layer"],
                "fab_layer": fab_layer_name,
                "courtyard_layer": courtyard_layer_name,
                "missing_layers": missing,
            }
            continue

        fab_left, fab_top, fab_right, fab_bottom = fab
        ctyd_left, ctyd_top, ctyd_right, ctyd_bottom = courtyard
        clearances = {
            "left": fab_left - ctyd_left,
            "right": ctyd_right - fab_right,
            "top": fab_top - ctyd_top,
            "bottom": ctyd_bottom - fab_bottom,
        }
        failed_sides = [
            side
            for side, clearance in clearances.items()
            if clearance + 1e-9 < minimum_clearance_mm
        ]
        for clearance_side, clearance in clearances.items():
            observed.append((clearance, ref, clearance_side))
        if failed_sides:
            errors.append(
                f"{ref} {fab_layer_name}-to-{courtyard_layer_name} clearance below "
                f"{minimum_clearance_mm:.6f} mm on: "
                + ", ".join(
                    f"{side}={clearances[side]:.6f} mm" for side in failed_sides
                )
            )
        per_reference[ref] = {
            "status": "FAIL" if failed_sides else "PASS",
            "footprint_layer": side["footprint_layer"],
            "fab_layer": fab_layer_name,
            "courtyard_layer": courtyard_layer_name,
            "clearance_mm": {
                side: round(value, 6) for side, value in clearances.items()
            },
            "minimum_clearance_mm": round(min(clearances.values()), 6),
        }

    minimum_observed: float | None = None
    minimum_location: dict[str, str] | None = None
    if observed:
        minimum_observed, reference, side = min(observed)
        minimum_location = {"reference": reference, "side": side}
    return _check(
        {
            "geometry_layers_by_side": {
                "F.Cu": {"fab": "F.Fab", "courtyard": "F.CrtYd"},
                "B.Cu": {"fab": "B.Fab", "courtyard": "B.CrtYd"},
            },
            "required_minimum_clearance_mm": minimum_clearance_mm,
            "observed_minimum_clearance_mm": (
                round(minimum_observed, 6) if minimum_observed is not None else None
            ),
            "observed_minimum_location": minimum_location,
            "per_reference": per_reference,
        },
        errors,
    )


def _via_type_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for constant, name in (
        ("VIATYPE_NOT_DEFINED", "not_defined"),
        ("VIATYPE_MICROVIA", "microvia"),
        ("VIATYPE_BLIND", "blind"),
        ("VIATYPE_BURIED", "buried"),
        ("VIATYPE_THROUGH", "through"),
    ):
        if hasattr(pcbnew, constant):
            names[int(getattr(pcbnew, constant))] = name
    return names


def _audit_vias(board: pcbnew.BOARD, allowed_types: list[str]) -> dict[str, Any]:
    type_names = _via_type_names()
    counts: dict[str, int] = {}
    invalid: list[str] = []
    vias = [item for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)]
    for index, via in enumerate(vias, start=1):
        raw_type = int(via.GetViaType())
        name = type_names.get(raw_type, f"unknown:{raw_type}")
        counts[name] = counts.get(name, 0) + 1
        if name not in allowed_types:
            position = via.GetPosition()
            invalid.append(
                f"via #{index} at ({pcbnew.ToMM(position.x):.6f}, "
                f"{pcbnew.ToMM(position.y):.6f}) mm has disallowed type {name}"
            )
    return _check(
        {
            "allowed_types": allowed_types,
            "total_count": len(vias),
            "counts_by_type": dict(sorted(counts.items())),
        },
        invalid,
    )


def _audit_rule_areas(board: pcbnew.BOARD, config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required_names = config["required_copper_layers"]
    layer_ids: dict[str, int] = {}
    enabled_copper_ids = set(board.GetEnabledLayers().CuStack())
    for name in required_names:
        layer = int(board.GetLayerID(name))
        if layer < 0:
            errors.append(f"unknown configured rule-area layer: {name}")
        elif layer not in enabled_copper_ids:
            errors.append(f"configured rule-area layer is not enabled copper: {name}")
        else:
            layer_ids[name] = layer

    zones = [zone for zone in board.Zones() if zone.GetIsRuleArea()]
    if len(zones) < config["minimum_count"]:
        errors.append(
            f"expected at least {config['minimum_count']} rule areas, found {len(zones)}"
        )
    actual_names = [zone.GetZoneName() for zone in zones]
    expected_names = config["expected_names"]
    if expected_names is not None and sorted(actual_names) != sorted(expected_names):
        errors.append(
            f"expected rule-area names {sorted(expected_names)}, found {sorted(actual_names)}"
        )

    area_details: list[dict[str, Any]] = []
    for index, zone in enumerate(zones, start=1):
        missing = [
            name
            for name, layer in layer_ids.items()
            if not zone.GetLayerSet().Contains(layer)
        ]
        name = zone.GetZoneName() or f"<unnamed #{index}>"
        if missing:
            errors.append(
                f"rule area {name} does not cover copper layers: {', '.join(missing)}"
            )
        area_details.append(
            {
                "name": zone.GetZoneName(),
                "covers_required_layers": not missing,
                "missing_required_layers": missing,
            }
        )
    return _check(
        {
            "required_copper_layers": required_names,
            "minimum_count": config["minimum_count"],
            "expected_names": expected_names,
            "actual_count": len(zones),
            "areas": area_details,
        },
        errors,
    )


def _run_audit(board_path: Path, config_path: Path) -> dict[str, Any]:
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    config = _validate_config(raw_config)
    board = pcbnew.LoadBoard(str(board_path))
    if board is None:
        raise RuntimeError(f"KiCad could not load board: {board_path}")

    checks: dict[str, Any] = {}
    checks["copper_layers"] = _audit_copper(board, config["copper_layers"])
    checks["paste_layers"] = _audit_paste(board, config["paste"]["required_layers"])
    edge_check, edge_bounds = _audit_edge_cuts(board, config["edge_cuts"])
    checks["edge_cuts"] = edge_check
    assembly_check, fit_smt = _audit_assembly(board, config["assembly"])
    checks["assembly"] = assembly_check
    checks["fab_courtyard"] = _audit_fab_courtyard(
        fit_smt, config["fab_courtyard"]["minimum_clearance_mm"]
    )
    checks["body_edge"] = _audit_layer_edge_clearance(
        fit_smt,
        edge_bounds,
        "fab",
        config["body_edge"]["minimum_clearance_mm"],
    )
    if config["courtyard_edge"] is not None:
        checks["courtyard_edge"] = _audit_layer_edge_clearance(
            fit_smt,
            edge_bounds,
            "courtyard",
            config["courtyard_edge"]["minimum_clearance_mm"],
        )
    checks["vias"] = _audit_vias(board, config["vias"]["allowed_types"])
    checks["rule_areas"] = _audit_rule_areas(board, config["rule_areas"])

    failures = [name for name, check in checks.items() if check["status"] != "PASS"]
    errors = [
        {"check": name, "message": message}
        for name in failures
        for message in checks[name]["errors"]
    ]
    return {
        "schema": 1,
        "status": "PASS" if not failures else "FAIL",
        "board": str(board_path),
        "config": str(config_path),
        "board_sha256": _sha256(board_path),
        "kicad_version": pcbnew.Version(),
        "checks": checks,
        "failed_checks": failures,
        "errors": errors,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only KiCad/JLCPCB board preflight; run with KiCad Python."
    )
    parser.add_argument("board", type=Path, help="input .kicad_pcb file")
    parser.add_argument("config", type=Path, help="audit configuration JSON")
    parser.add_argument("output", type=Path, help="output audit report JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    board_path = args.board.resolve()
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    if output_path in {board_path, config_path}:
        print(
            "ERROR: output JSON must not overwrite the board or config", file=sys.stderr
        )
        return 2

    try:
        if not board_path.is_file():
            raise FileNotFoundError(f"board does not exist: {board_path}")
        if board_path.suffix.casefold() != ".kicad_pcb":
            raise ConfigError(f"board must have .kicad_pcb suffix: {board_path}")
        if not config_path.is_file():
            raise FileNotFoundError(f"config does not exist: {config_path}")
        report = _run_audit(board_path, config_path)
        exit_code = 0 if report["status"] == "PASS" else 1
    except Exception as exc:  # Report malformed input and pcbnew failures as JSON too.
        report = {
            "schema": 1,
            "status": "ERROR",
            "board": str(board_path),
            "config": str(config_path),
            "checks": {},
            "failed_checks": ["runtime"],
            "errors": [
                {
                    "check": "runtime",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
        exit_code = 2

    try:
        _write_report(output_path, report)
    except Exception as exc:
        print(f"ERROR: could not write report {output_path}: {exc}", file=sys.stderr)
        return 2
    print(f"{report['status']} board={board_path} report={output_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
