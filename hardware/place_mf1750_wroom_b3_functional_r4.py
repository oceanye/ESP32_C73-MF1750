#!/usr/bin/env python3
"""Create the MF1750 WROOM B3 R4 functional-placement staging candidate.

This is a placement-only REVISION.  It loads the verified R3 placed staging
PCB, preserves all B2 footprints except removed J3 plus every pre-existing
track/via/zone, and moves only R3-added schematic footprints into reviewable
functional clusters.  It never routes and never writes the formal B3 PCB.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
B2_SHA256 = "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
R3_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"
R4_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb"
PREVIEW_DIR = STAGING / "r4_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r4_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r4_bottom.png"
REPORT_PATH = STAGING / "r4_functional_placement_report.json"
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
KICAD_SHARE = Path(r"C:\Program Files\KiCad\10.0\share\kicad")

BOARD_WIDTH_MM = 80.0
BOARD_HEIGHT_MM = 125.0
BOARD_EDGE_CLEARANCE_MM = 0.50
B2_BOTTOM_MM = 60.5

# Coordinates are review placements, not routed/fabrication authority.
PLACEMENTS: dict[str, tuple[float, float, float]] = {
    # Edge mechanics and controls.
    "SW1": (2.0, 64.5, 90.0),
    "SW2": (2.0, 72.5, 90.0),
    "SW3": (2.0, 80.5, 90.0),
    "SW4": (2.0, 88.5, 90.0),
    "SW5": (2.0, 96.5, 90.0),
    "J5": (5.5, 109.0, 90.0),
    "J6": (16.5, 120.0, 180.0),
    # Bottom-entry TF edge connector.  Keep the vendor-derived edge alignment
    # until the Molex card/enclosure insertion envelope is mechanically frozen.
    "J4": (31.5, 118.4, 180.0),
    "U1": (52.0, 90.0, 270.0),
    # EPD load switch next to the frozen TP1 boundary.
    "U5": (8.0, 64.2, 0.0),
    "C39": (13.0, 63.1, 0.0),
    "C40": (13.0, 66.6, 0.0),
    "R33": (17.0, 62.8, 0.0),
    "R34": (17.0, 65.3, 0.0),
    "R35": (17.0, 67.8, 0.0),
    # Seven-line bidirectional isolation at the B2 signal-anchor edge.
    "U6": (34.0, 65.5, 0.0),
    "C45": (27.5, 62.5, 0.0),
    "Q3": (27.0, 66.0, 0.0),
    "R36": (23.0, 62.5, 0.0),
    "R54": (23.0, 65.0, 0.0),
    "R55": (23.0, 67.5, 0.0),
    "R56": (23.0, 70.0, 0.0),
    "R57": (26.5, 70.5, 0.0),
    "R58": (30.0, 71.5, 0.0),
    "R59": (33.5, 71.5, 0.0),
    "R60": (36.8, 71.5, 0.0),
    "R62": (30.0, 74.2, 0.0),
    "R63": (33.5, 74.2, 0.0),
    # STM6600 and local timing/decoupling.
    "U3": (11.0, 78.5, 0.0),
    "C28": (16.0, 77.0, 0.0),
    "C29": (16.0, 80.0, 0.0),
    "C30": (20.0, 77.0, 0.0),
    "R28": (20.0, 80.0, 0.0),
    "R51": (7.0, 76.5, 0.0),
    "R52": (7.0, 82.5, 0.0),
    # Compact TPS63070 power island.
    "R61": (27.0, 77.0, 0.0),
    "C38": (20.15, 86.25, 180.0),
    "R29": (20.15, 84.2, 0.0),
    "R30": (31.5, 80.5, 0.0),
    "U4": (24.0, 85.5, 0.0),
    # TI TPS63070 Rev.B 11.1 local 0603 HF capacitors.  Keep C46 at VIN/GND
    # and C47 at VOUT/GND; the larger C31-C37 parts remain bulk storage.
    "C46": (24.0, 82.15, 180.0),
    "C47": (25.2, 89.6, 270.0),
    "L3": (28.7, 85.5, 270.0),
    "C31": (15.5, 84.0, 180.0),
    "C32": (15.5, 87.0, 180.0),
    "C33": (15.5, 90.0, 180.0),
    "R31": (20.9, 89.6, 90.0),
    "R32": (23.15, 89.6, 270.0),
    "C34": (14.0, 93.5, 180.0),
    "C35": (19.5, 93.5, 180.0),
    "C36": (25.0, 93.5, 180.0),
    "C37": (30.0, 93.5, 180.0),
    # WROOM-side decoupling, reset/boot and USB series termination.
    "R27": (36.0, 76.5, 0.0),
    "C48": (36.8, 74.0, 0.0),
    "R19": (36.0, 79.5, 0.0),
    "R20": (36.0, 82.0, 0.0),
    "C41": (36.0, 85.0, 0.0),
    "C42": (36.0, 88.0, 0.0),
    "R53": (36.0, 96.5, 0.0),
    # USB-C protection and BQ24074/PowerPath cluster.
    "F1": (8.5, 99.0, 0.0),
    "D5": (14.0, 100.0, 0.0),
    "C24": (19.0, 100.0, 0.0),
    "C50": (8.5, 102.0, 0.0),
    "R64": (12.0, 103.5, 0.0),
    "R65": (15.5, 103.5, 0.0),
    "U8": (12.5, 108.4, 90.0),
    "R17": (12.0, 111.8, 0.0),
    "R18": (15.5, 111.8, 0.0),
    "U2": (18.0, 107.0, 0.0),
    "R21": (18.0, 96.8, 0.0),
    "R22": (21.5, 96.8, 0.0),
    "R24": (25.0, 96.8, 0.0),
    "R25": (26.5, 105.0, 0.0),
    "R26": (21.5, 102.5, 0.0),
    "C25": (23.0, 105.0, 0.0),
    "C26": (23.0, 108.0, 0.0),
    "C27": (19.0, 111.0, 0.0),
    "R49": (20.8, 113.5, 0.0),
    "R50": (20.8, 116.0, 0.0),
    "C49": (22.8, 119.0, 0.0),
    # microSD card-side ESD, pulls, damping and local decoupling.
    "R39": (23.0, 99.4, 0.0),
    "R40": (26.5, 99.4, 0.0),
    "R41": (30.0, 99.4, 0.0),
    "R42": (33.5, 99.4, 0.0),
    "R43": (36.8, 99.4, 0.0),
    "R44": (36.8, 101.0, 0.0),
    "R45": (25.5, 103.0, 0.0),
    "R46": (29.0, 103.0, 0.0),
    "R47": (32.5, 103.0, 0.0),
    "R48": (36.0, 103.0, 0.0),
    "C43": (31.5, 106.0, 0.0),
    "C44": (36.0, 106.0, 0.0),
    "U9": (27.5, 109.5, 90.0),
    "U10": (32.0, 109.5, 90.0),
    "U11": (36.5, 109.5, 90.0),
}

EDGE_ACCESS_REFS = frozenset({"J4", "J5", "U1", "SW1", "SW2", "SW3", "SW4", "SW5"})
HOLE_PLACEMENTS = {"H3": (5.0, 120.0, 0.0), "H4": (75.0, 120.0, 0.0)}
MECHANICAL_UUID_SEED = 17503


class PlacementError(RuntimeError):
    pass


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    )


def find_kicad_cli() -> Path:
    candidates = [
        shutil.which("kicad-cli"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise PlacementError("KiCad 10 kicad-cli was not found")


def footprint_state(footprint) -> tuple[object, ...]:
    position = footprint.GetPosition()
    return (
        footprint.GetFPID().GetUniStringLibId(),
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
    )


def track_signature(item) -> tuple[object, ...]:
    start = item.GetStart()
    uuid = item.m_Uuid.AsString()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            uuid,
            item.GetNetname(),
            int(start.x),
            int(start.y),
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    end = item.GetEnd()
    return (
        "track",
        uuid,
        item.GetNetname(),
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


def polygon_points(poly_set) -> tuple[tuple[tuple[int, int], ...], ...]:
    contours = []
    for index in range(poly_set.OutlineCount()):
        contour = poly_set.COutline(index)
        contours.append(
            tuple(
                (int(contour.CPoint(point).x), int(contour.CPoint(point).y))
                for point in range(contour.PointCount())
            )
        )
    return tuple(contours)


def zone_signature(zone) -> tuple[object, ...]:
    return (
        zone.m_Uuid.AsString(),
        zone.GetZoneName(),
        zone.GetNetname(),
        int(zone.GetLayer()),
        tuple(zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        polygon_points(zone.Outline()),
    )


def bbox_mm(box) -> tuple[float, float, float, float]:
    return (
        pcbnew.ToMM(box.GetX()),
        pcbnew.ToMM(box.GetY()),
        pcbnew.ToMM(box.GetRight()),
        pcbnew.ToMM(box.GetBottom()),
    )


def courtyard_bbox(footprint) -> tuple[float, float, float, float]:
    courtyard = footprint.GetCourtyard(pcbnew.F_Cu)
    if courtyard.OutlineCount() == 0:
        raise PlacementError(f"{footprint.GetReference()} has no F.CrtYd")
    return bbox_mm(courtyard.BBox())


def pad_bbox(footprint) -> tuple[float, float, float, float]:
    pads = list(footprint.Pads())
    if not pads:
        return courtyard_bbox(footprint)
    boxes = [bbox_mm(pad.GetBoundingBox()) for pad in pads]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def boxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


def add_mounting_hole(board, footprint_io, ref: str, placement) -> None:
    library = KICAD_SHARE / "footprints" / "MountingHole.pretty"
    footprint = footprint_io.FootprintLoad(str(library), "MountingHole_3.2mm_M3", False)
    if not isinstance(footprint, pcbnew.FOOTPRINT):
        raise PlacementError(f"failed to load M3 mounting hole for {ref}")
    footprint.SetFPIDAsString("MountingHole:MountingHole_3.2mm_M3")
    footprint.SetReference(ref)
    footprint.SetValue("M3_NPTH_BOARD_ONLY")
    footprint.SetBoardOnly(True)
    footprint.SetAttributes(
        footprint.GetAttributes()
        | pcbnew.FP_EXCLUDE_FROM_BOM
        | pcbnew.FP_EXCLUDE_FROM_POS_FILES
    )
    x, y, rotation = placement
    footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    footprint.SetOrientationDegrees(rotation)
    board.Add(footprint)


def run_drc(kicad_cli: Path, board_path: Path, report_path: Path) -> dict[str, object]:
    command = [
        str(kicad_cli),
        "pcb",
        "drc",
        "--format",
        "json",
        "--severity-all",
        "--output",
        str(report_path),
        str(board_path),
    ]
    completed = subprocess.run(
        command,
        cwd=B3_DIR,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    if completed.returncode != 0 or not report_path.is_file():
        raise PlacementError(completed.stderr.strip() or completed.stdout.strip())
    data = json.loads(report_path.read_text(encoding="utf-8"))
    violations = data.get("violations", [])
    categories = collections.Counter(str(item.get("type")) for item in violations)
    return {
        "returncode": completed.returncode,
        "kicad_version": data.get("kicad_version"),
        "violations": len(violations),
        "unconnected": len(data.get("unconnected_items", [])),
        "schematic_parity": len(data.get("schematic_parity", [])),
        "categories": dict(
            sorted(categories.items(), key=lambda item: (-item[1], item[0]))
        ),
        "items_not_allowed": categories.get("items_not_allowed", 0),
        "courtyard_overlaps": categories.get("courtyards_overlap", 0),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def render(
    kicad_cli: Path, board_path: Path, output: Path, side: str
) -> dict[str, object]:
    command = [
        str(kicad_cli),
        "pcb",
        "render",
        "--side",
        side,
        "--background",
        "opaque",
        "--quality",
        "high",
        "--width",
        "1800",
        "--height",
        "1600",
        "--output",
        str(output),
        str(board_path),
    ]
    completed = subprocess.run(
        command,
        cwd=B3_DIR,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise PlacementError(
            f"{side} render failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    return {"side": side, "bytes": output.stat().st_size, "command": command}


def audit_geometry(
    board,
    b2_states: dict[str, tuple[object, ...]],
    source_tracks: collections.Counter[tuple[object, ...]],
    source_zones: collections.Counter[tuple[object, ...]],
    movable_refs: set[str],
) -> dict[str, object]:
    footprints = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    frozen_drift = [
        ref
        for ref, expected in b2_states.items()
        if ref not in footprints or footprint_state(footprints[ref]) != expected
    ]
    actual_tracks = collections.Counter(
        track_signature(item) for item in board.GetTracks()
    )
    actual_zones = collections.Counter(zone_signature(zone) for zone in board.Zones())
    missing_tracks = list((source_tracks - actual_tracks).elements())
    extra_tracks = list((actual_tracks - source_tracks).elements())
    missing_zones = list((source_zones - actual_zones).elements())
    extra_zones = list((actual_zones - source_zones).elements())

    relevant = movable_refs | set(HOLE_PLACEMENTS)
    boxes = {
        ref: courtyard_bbox(footprints[ref])
        for ref in sorted(relevant, key=natural_key)
        if ref in footprints
    }
    overlap_pairs: list[list[str]] = []
    refs = sorted(boxes, key=natural_key)
    for index, ref in enumerate(refs):
        for other in refs[index + 1 :]:
            if boxes_overlap(boxes[ref], boxes[other]):
                overlap_pairs.append([ref, other])

    u1 = footprints["U1"]
    if len(u1.Zones()) != 1 or not u1.Zones()[0].GetIsRuleArea():
        raise PlacementError("U1 official antenna keepout is missing")
    antenna_box = bbox_mm(u1.Zones()[0].GetBoundingBox())
    antenna_intrusions = [
        ref
        for ref, box in boxes.items()
        if ref != "U1" and boxes_overlap(box, antenna_box)
    ]

    edge_failures: list[dict[str, object]] = []
    for ref in sorted(movable_refs | set(HOLE_PLACEMENTS), key=natural_key):
        footprint = footprints[ref]
        courtyard = courtyard_bbox(footprint)
        pads = pad_bbox(footprint)
        if ref not in EDGE_ACCESS_REFS:
            if (
                courtyard[0] < BOARD_EDGE_CLEARANCE_MM
                or courtyard[1] < BOARD_EDGE_CLEARANCE_MM
                or courtyard[2] > BOARD_WIDTH_MM - BOARD_EDGE_CLEARANCE_MM
                or courtyard[3] > BOARD_HEIGHT_MM - BOARD_EDGE_CLEARANCE_MM
            ):
                edge_failures.append({"ref": ref, "courtyard_mm": courtyard})
        if ref == "J5" and pads[0] < BOARD_EDGE_CLEARANCE_MM:
            edge_failures.append({"ref": ref, "pad_bbox_mm": pads})
        if ref == "J4" and pads[3] > BOARD_HEIGHT_MM - BOARD_EDGE_CLEARANCE_MM:
            edge_failures.append({"ref": ref, "pad_bbox_mm": pads})
        if ref.startswith("SW") and pads[0] < BOARD_EDGE_CLEARANCE_MM:
            edge_failures.append({"ref": ref, "pad_bbox_mm": pads})

    checks = {
        "b2_all_minus_j3_geometry_preserved": not frozen_drift,
        "existing_tracks_vias_exact": not missing_tracks and not extra_tracks,
        "existing_board_zones_exact": not missing_zones and not extra_zones,
        "all_movable_refs_present": set(PLACEMENTS) <= set(footprints),
        "h3_h4_added": set(HOLE_PLACEMENTS) <= set(footprints),
        "no_courtyard_overlap": not overlap_pairs,
        "no_antenna_keepout_intrusion": not antenna_intrusions,
        "board_edge_contract": not edge_failures,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "frozen_b2_ref_count": len(b2_states),
        "frozen_drift": frozen_drift,
        "source_copper_items": sum(source_tracks.values()),
        "missing_copper_count": len(missing_tracks),
        "extra_copper_count": len(extra_tracks),
        "source_board_zones": sum(source_zones.values()),
        "missing_zone_count": len(missing_zones),
        "extra_zone_count": len(extra_zones),
        "courtyard_overlap_pairs": overlap_pairs,
        "antenna_keepout_bbox_mm": antenna_box,
        "antenna_intrusions": antenna_intrusions,
        "edge_failures": edge_failures,
        "key_boundaries": {
            "U1_courtyard_mm": boxes["U1"],
            "J4_pad_bbox_mm": pad_bbox(footprints["J4"]),
            "J5_pad_bbox_mm": pad_bbox(footprints["J5"]),
            "H3_courtyard_mm": boxes.get("H3"),
            "H4_courtyard_mm": boxes.get("H4"),
        },
    }


def testpoint_placements() -> dict[str, tuple[float, float, float]]:
    result = {}
    refs = [f"TP{index}" for index in range(11, 34)]
    columns = [42.0, 46.0, 50.0, 54.0, 58.0, 62.0, 66.0, 69.0]
    rows = [116.5, 120.0, 123.0]
    coordinates = [(x, y) for y in rows for x in columns][: len(refs)]
    for ref, (x, y) in zip(refs, coordinates, strict=True):
        result[ref] = (x, y, 0.0)
    return result


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=R3_BOARD)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.resolve()
    report: dict[str, object]
    candidate: Path | None = None
    try:
        if pcbnew is None:
            raise PlacementError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise PlacementError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not source.is_file() or not B2_BOARD.is_file():
            raise PlacementError("R3 source or frozen B2 board is missing")
        if sha256_file(B2_BOARD) != B2_SHA256:
            raise PlacementError("frozen B2 board hash mismatch")
        locks = list(STAGING.glob("~*.lck")) + list(B3_DIR.glob("~*.lck"))
        if locks:
            raise PlacementError("close KiCad first: " + ", ".join(map(str, locks)))
        kicad_cli = find_kicad_cli()
        formal_before = sha256_file(FORMAL_BOARD) if FORMAL_BOARD.is_file() else None

        b2 = pcbnew.LoadBoard(str(B2_BOARD))
        board = pcbnew.LoadBoard(str(source))
        if b2 is None or board is None:
            raise PlacementError("KiCad could not parse an input PCB")
        b2_refs = {footprint.GetReference() for footprint in b2.GetFootprints()} - {
            "J3"
        }
        footprints = {
            footprint.GetReference(): footprint for footprint in board.GetFootprints()
        }
        b2_states = {ref: footprint_state(footprints[ref]) for ref in b2_refs}
        movable_refs = set(footprints) - b2_refs
        placement_map = {**PLACEMENTS, **testpoint_placements()}
        if movable_refs != set(placement_map):
            raise PlacementError(
                "R3-added ref/placement mismatch: "
                + repr(
                    {
                        "missing": sorted(
                            movable_refs - set(placement_map), key=natural_key
                        ),
                        "extra": sorted(
                            set(placement_map) - movable_refs, key=natural_key
                        ),
                    }
                )
            )
        source_tracks = collections.Counter(
            track_signature(item) for item in board.GetTracks()
        )
        source_zones = collections.Counter(
            zone_signature(zone) for zone in board.Zones()
        )

        for ref, (x, y, rotation) in placement_map.items():
            footprint = footprints[ref]
            if footprint.IsFlipped():
                raise PlacementError(
                    f"R3-added footprint unexpectedly on bottom: {ref}"
                )
            footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            footprint.SetOrientationDegrees(rotation)

        footprint_io = pcbnew.PCB_IO_KICAD_SEXPR()
        # FootprintLoad allocates fresh KIID values.  Seed only this final,
        # board-only addition so H3/H4 and their children are reproducible
        # across clean rebuilds instead of changing the candidate hash on
        # every invocation.
        pcbnew.KIID.SeedGenerator(MECHANICAL_UUID_SEED)
        for ref, placement in HOLE_PLACEMENTS.items():
            if ref in footprints:
                raise PlacementError(f"board-only hole ref already exists: {ref}")
            add_mounting_hole(board, footprint_io, ref, placement)

        title = board.GetTitleBlock()
        title.SetTitle("MF1750 WROOM B3 R4 functional placement candidate")
        title.SetRevision("B3-WROOM-POWER-TF-R4-FUNCTIONAL-PLACED")
        title.SetComment(0, "PLACEMENT ONLY; NO NEW ROUTING; NOT MANUFACTURING READY")

        STAGING.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="mf1750-r4-place-", dir=STAGING
        ) as temp_name:
            temp_dir = Path(temp_name)
            candidate = STAGING / (
                f".{R4_BOARD.stem}.{os.getpid()}.{secrets.token_hex(6)}.kicad_pcb"
            )
            top_temp = temp_dir / TOP_PREVIEW.name
            bottom_temp = temp_dir / BOTTOM_PREVIEW.name
            drc_preflight_temp = temp_dir / "drc_preflight.json"
            drc_fixed_temp = temp_dir / "drc_fixed.json"
            previous_board = temp_dir / "previous_r4.kicad_pcb"

            # The R3 zones intentionally retain their outline/settings, but their
            # cached fills are stale after moving the R3-added footprints.  Refill
            # before save so placement DRC measures real copper clearance rather
            # than the pre-placement fill geometry.
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(str(candidate), board)
            reloaded = pcbnew.LoadBoard(str(candidate))
            if reloaded is None:
                raise PlacementError("saved R4 candidate does not reload")
            audit = audit_geometry(
                reloaded, b2_states, source_tracks, source_zones, movable_refs
            )
            if not audit["passed"]:
                raise PlacementError("geometry audit failed: " + json.dumps(audit))
            render_top = render(kicad_cli, candidate, top_temp, "top")
            render_bottom = render(kicad_cli, candidate, bottom_temp, "bottom")
            drc_preflight = run_drc(kicad_cli, candidate, drc_preflight_temp)
            if (
                drc_preflight["items_not_allowed"]
                or drc_preflight["courtyard_overlaps"]
            ):
                raise PlacementError(
                    "fatal placement DRC class: " + json.dumps(drc_preflight)
                )

            previous_sha = sha256_file(R4_BOARD) if R4_BOARD.is_file() else None
            if R4_BOARD.is_file():
                shutil.copy2(R4_BOARD, previous_board)
            os.replace(candidate, R4_BOARD)
            candidate = None
            try:
                # A fixed-path run is authoritative because KiCad can resolve
                # sibling project context differently for a temporary filename.
                drc = run_drc(kicad_cli, R4_BOARD, drc_fixed_temp)
                if drc["items_not_allowed"] or drc["courtyard_overlaps"]:
                    raise PlacementError(
                        "fatal fixed-path placement DRC class: " + json.dumps(drc)
                    )
                os.replace(top_temp, TOP_PREVIEW)
                os.replace(bottom_temp, BOTTOM_PREVIEW)
            except Exception:
                if previous_board.is_file():
                    os.replace(previous_board, R4_BOARD)
                elif R4_BOARD.is_file():
                    R4_BOARD.unlink()
                raise
            formal_after = sha256_file(FORMAL_BOARD) if FORMAL_BOARD.is_file() else None
            if formal_after != formal_before:
                raise PlacementError("formal B3 PCB changed unexpectedly")
            report = {
                "schema": 1,
                "tool": Path(__file__).name,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R4_FUNCTIONAL_PLACED_CANDIDATE_NOT_ROUTED",
                "overall_status": "HOLD",
                "operation_completed": True,
                "placement_checks_passed": True,
                "locally_verified": False,
                "inputs": {
                    "r3": {"path": str(source), "sha256": sha256_file(source)},
                    "b2": {"path": str(B2_BOARD), "sha256": sha256_file(B2_BOARD)},
                },
                "output": {
                    "path": str(R4_BOARD),
                    "previous_sha256": previous_sha,
                    "sha256": sha256_file(R4_BOARD),
                    "bytes": R4_BOARD.stat().st_size,
                },
                "previews": {
                    "top": {
                        **render_top,
                        "path": str(TOP_PREVIEW),
                        "sha256": sha256_file(TOP_PREVIEW),
                    },
                    "bottom": {
                        **render_bottom,
                        "path": str(BOTTOM_PREVIEW),
                        "sha256": sha256_file(BOTTOM_PREVIEW),
                    },
                },
                "audit": audit,
                "drc": {
                    "authoritative_context": "fixed_staging_output_path",
                    "fixed_output": drc,
                    "temporary_candidate_preflight": drc_preflight,
                },
                "placement": {
                    "moved_r3_schematic_footprints": len(movable_refs),
                    "board_only_holes_added": HOLE_PLACEMENTS,
                    "existing_zone_outlines_and_settings_preserved": True,
                    "existing_zones_refilled_after_placement": True,
                    "clusters": [
                        "EPD_U5_U6",
                        "TPS63070",
                        "BQ_STM",
                        "USB",
                        "TF",
                        "WROOM",
                        "BUTTONS",
                    ],
                },
                "holds": [
                    "R4 is placement-only and all new nets remain unrouted",
                    "power-loop, USB impedance, thermal and enclosure verification remain HOLD",
                    "J6 connector/pack contract remains HOLD",
                ],
                "formal_b3_sha256": formal_after,
                "formal_b3_modified": False,
                "hardware_accessed": False,
            }
    except Exception as exc:
        report = {
            "schema": 1,
            "tool": Path(__file__).name,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "state": "HOLD_R4_PLACEMENT_FAILED",
            "overall_status": "FAIL",
            "operation_completed": False,
            "placement_checks_passed": False,
            "locally_verified": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "output": str(R4_BOARD),
            "formal_b3_modified": False,
            "hardware_accessed": False,
        }
    finally:
        if candidate is not None and candidate.exists():
            if candidate.parent.resolve() != STAGING.resolve():
                raise PlacementError(f"refusing cleanup outside staging: {candidate}")
            candidate.unlink()
    write_json_atomic(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
