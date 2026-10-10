#!/usr/bin/env python3
"""Generate fail-closed JLCPCB BOM/CPL files from a KiCad PCB and mapping CSV.

Run with KiCad's bundled Python.  The mapping CSV must contain Designator,
Value, Footprint, and LCSC Part #.  Generation is by PCB population state;
DNP, through-hole, manual, and non-assembly references are excluded.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pcbnew


REQUIRED_MAPPING_COLUMNS = {"Designator", "Value", "Footprint", "LCSC Part #"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(reference: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)(.*)", reference)
    if not match:
        return reference, -1, ""
    return match.group(1), int(match.group(2)), match.group(3)


def load_mapping(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_MAPPING_COLUMNS.issubset(
            reader.fieldnames
        ):
            raise SystemExit(
                f"Mapping columns must include {sorted(REQUIRED_MAPPING_COLUMNS)}"
            )
        rows = list(reader)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        refs = [item.strip() for item in row["Designator"].split(",")]
        if not refs or any(not item for item in refs):
            raise SystemExit(f"Invalid mapping Designator: {row['Designator']!r}")
        for reference in refs:
            if reference in result:
                raise SystemExit(f"Duplicate mapping for {reference}")
            result[reference] = row
    return result


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(rows)


def fitted_smt_footprints(
    board: pcbnew.BOARD, config: dict[str, object]
) -> dict[str, pcbnew.FOOTPRINT]:
    manual = set(config.get("manual_refs", []))
    nonassembly = set(config.get("nonassembly_refs", []))
    excluded = manual | nonassembly
    require_top_only = bool(config.get("require_top_only", True))
    result: dict[str, pcbnew.FOOTPRINT] = {}
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        pads = list(footprint.Pads())
        if (
            reference in excluded
            or footprint.IsDNP()
            or footprint.HasThroughHolePads()
            or not pads
        ):
            continue
        if footprint.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
            raise SystemExit(f"Unsupported SMT layer for {reference}")
        if require_top_only and footprint.GetLayer() != pcbnew.F_Cu:
            raise SystemExit(
                f"Bottom SMT {reference} requires an explicit rotation/origin review"
            )
        result[reference] = footprint
    if not result:
        raise SystemExit("No fitted SMT footprints found")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcb", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bom", required=True, type=Path)
    parser.add_argument("--cpl", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(args.pcb.resolve()))
    if board is None:
        raise SystemExit(f"Cannot load PCB: {args.pcb}")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    mapping = load_mapping(args.mapping)
    footprints = fitted_smt_footprints(board, config)

    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    expanded_rows = []
    for reference in sorted(footprints, key=natural_key):
        row = mapping.get(reference)
        if row is None:
            raise SystemExit(f"Missing mapping for fitted SMT reference {reference}")
        lcsc = row["LCSC Part #"].strip()
        if not re.fullmatch(str(config.get("lcsc_pattern", r"C\d+")), lcsc):
            raise SystemExit(f"Invalid LCSC Part # for {reference}: {lcsc!r}")
        footprint_id = footprints[reference].GetFPID().GetUniStringLibId()
        if row["Footprint"].strip() != footprint_id:
            raise SystemExit(
                f"Footprint mapping drift for {reference}: "
                f"mapping={row['Footprint']!r}, PCB={footprint_id!r}"
            )
        if row.get("DNP", "No").strip().casefold() in {"yes", "true", "1"}:
            raise SystemExit(f"Fitted SMT mapping marks {reference} DNP")
        key = (row["Value"].strip(), footprint_id, lcsc)
        groups[key].append(reference)
        expanded_rows.append(
            {
                "reference": reference,
                "value": key[0],
                "footprint": footprint_id,
                "lcsc": lcsc,
            }
        )

    bom_rows = [["Comment", "Designator", "Footprint", "LCSC Part #"]]
    for (value, footprint_id, lcsc), references in sorted(
        groups.items(),
        key=lambda item: natural_key(sorted(item[1], key=natural_key)[0]),
    ):
        ordered = sorted(references, key=natural_key)
        bom_rows.append([value, ",".join(ordered), footprint_id, lcsc])
    write_csv(args.bom, bom_rows)

    origin = config.get("cpl_origin_mm", [0.0, 0.0])
    if not isinstance(origin, list) or len(origin) != 2:
        raise SystemExit("cpl_origin_mm must be [x, y]")
    origin_x, origin_y = (float(origin[0]), float(origin[1]))
    negate_y = bool(config.get("cpl_negate_y", True))
    suffix = "mm" if bool(config.get("cpl_mm_suffix", True)) else ""
    cpl_rows = [["Designator", "Mid X", "Mid Y", "Rotation", "Layer"]]
    for reference in sorted(footprints, key=natural_key):
        footprint = footprints[reference]
        position = footprint.GetPosition()
        x_mm = pcbnew.ToMM(position.x) - origin_x
        y_mm = pcbnew.ToMM(position.y) - origin_y
        if negate_y:
            y_mm = -y_mm
        layer = "Top" if footprint.GetLayer() == pcbnew.F_Cu else "Bottom"
        cpl_rows.append(
            [
                reference,
                f"{x_mm:.4f}{suffix}",
                f"{y_mm:.4f}{suffix}",
                f"{footprint.GetOrientationDegrees() % 360.0:.2f}",
                layer,
            ]
        )
    write_csv(args.cpl, cpl_rows)

    bom_refs = {
        reference
        for row in bom_rows[1:]
        for reference in row[1].split(",")
        if reference
    }
    cpl_refs = {row[0] for row in cpl_rows[1:]}
    if bom_refs != cpl_refs or bom_refs != set(footprints):
        raise SystemExit("BOM/CPL/PCB fitted SMT reference sets differ")

    audit = {
        "schema": 1,
        "status": "PASS",
        "pcb": str(args.pcb.resolve()),
        "pcb_sha256": sha256(args.pcb),
        "mapping_sha256": sha256(args.mapping),
        "fit_smt_count": len(footprints),
        "unique_lcsc_count": len({row["lcsc"] for row in expanded_rows}),
        "bom_group_count": len(groups),
        "bom_cpl_reference_sets_identical": True,
        "fit_smt_refs": sorted(footprints, key=natural_key),
        "expanded": expanded_rows,
        "coordinate_contract": {
            "origin_mm": [origin_x, origin_y],
            "negate_y": negate_y,
            "footprint_origin": True,
        },
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
