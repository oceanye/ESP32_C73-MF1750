#!/usr/bin/env python3
"""Build the MF1750 B3 R6 SI-placement-remediation staging candidate.

This is a placement-only REVISION from the exact reviewed R4 candidate.  It
moves only the explicitly reviewed decoupling, termination, protection and
test-point footprints, preserves every source track/via and every zone
UUID/outline/setting, and writes only a distinct staging output.  The formal
PCB, schematic, project, R3, R4 and all R5 artifacts are protected by hashes.

No routing is added here.  R5 routing must be replayed against this candidate
only after its pad contract is regenerated; in particular the old U6.19
EPD_BUF_OE_N escape through (38.2, 63.225) is incompatible with remediated C45.
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
except Exception as exc:  # pragma: no cover - evaluated under KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb"
SOURCE_SHA256 = "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r6_si_placement_remediated.kicad_pcb"
REPORT_JSON = STAGING / "r6_si_placement_remediation_report.json"
SOURCE_DRC_JSON = STAGING / "r6_si_placement_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r6_si_placement_candidate_drc.json"
VERIFIER_JSON = STAGING / "r6_si_placement_board_verifier.json"
PREVIEW_DIR = STAGING / "r6_si_placement_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_si_placement_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r6_si_placement_bottom.png"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
R3_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"
R4_BOARD = SOURCE_BOARD
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"

PROTECTED_HASHES = {
    FORMAL_BOARD: "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7",
    FORMAL_SCHEMATIC: "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0",
    FORMAL_PROJECT: "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c",
    R3_BOARD: "c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb",
    R4_BOARD: SOURCE_SHA256,
}

BOARD_WIDTH_MM = 80.0
BOARD_HEIGHT_MM = 125.0
EDGE_CLEARANCE_MM = 0.50
CRITICAL_TP_COPPER_DIAMETER_MM = 1.00
CRITICAL_TP_COURTYARD_OUTER_DIAMETER_MM = 1.10
CRITICAL_TP_COURTYARD_LINE_WIDTH_MM = 0.05
CRITICAL_TP_COURTYARD_CENTERLINE_RADIUS_MM = (
    CRITICAL_TP_COURTYARD_OUTER_DIAMETER_MM
    - CRITICAL_TP_COURTYARD_LINE_WIDTH_MM
) / 2.0

# (x-mm, y-mm, rotation-deg, side).  TP21 is the sole documented coordinate
# adjustment from the initial review map: (39, 67.125) would be only 0.65 mm
# centre-to-centre from the future /BUSY_N 0.20 mm route and therefore fail the
# required 0.80 mm copper separation.  The replacement sits by R59.1 /SI0.
PLACEMENTS: dict[str, tuple[float, float, float, str]] = {
    "C45": (40.000, 62.500, 0.0, "F"),
    "C41": (53.900, 78.100, 90.0, "F"),
    "C42": (56.000, 78.300, 90.0, "F"),
    "R19": (35.500, 79.500, 0.0, "F"),
    "R20": (35.500, 82.000, 0.0, "F"),
    "R48": (43.000, 77.200, 90.0, "F"),
    "R46": (46.000, 77.200, 90.0, "F"),
    "R45": (49.000, 77.200, 90.0, "F"),
    "R47": (30.500, 104.500, -90.0, "F"),
    "R41": (32.000, 101.000, 0.0, "F"),
    "R40": (35.500, 101.000, 0.0, "F"),
    "R43": (39.000, 101.000, 0.0, "F"),
    "R42": (33.500, 104.500, 0.0, "F"),
    "R39": (37.000, 104.500, 0.0, "F"),
    "R44": (40.500, 104.500, 0.0, "F"),
    "U9": (27.500, 108.800, 90.0, "F"),
    "U10": (32.000, 108.800, 90.0, "F"),
    "U11": (36.500, 108.800, 90.0, "F"),
    "C43": (31.305, 121.400, 90.0, "B"),
    "C44": (28.800, 121.200, 90.0, "B"),
    "TP20": (40.000, 75.000, 0.0, "F"),
    "TP21": (33.500, 69.800, 0.0, "F"),
    "TP22": (48.500, 79.500, 0.0, "F"),
    "TP23": (46.500, 79.500, 0.0, "F"),
    "TP24": (45.000, 79.500, 0.0, "F"),
    "TP25": (43.500, 79.500, 0.0, "F"),
    "TP26": (37.800, 79.500, 0.0, "F"),
    "TP27": (37.800, 82.000, 0.0, "F"),
}

SLOW_TP_REFS = tuple(
    [f"TP{index}" for index in range(11, 20)]
    + [f"TP{index}" for index in range(28, 34)]
)
SLOW_TP_COORDINATES = tuple(
    (x, y, 0.0, "F")
    for y in (116.5, 120.0, 123.0)
    for x in (45.0, 49.0, 53.0, 57.0, 61.0)
)
PLACEMENTS.update(dict(zip(SLOW_TP_REFS, SLOW_TP_COORDINATES, strict=True)))

CRITICAL_TP_REFS = frozenset(f"TP{index}" for index in range(20, 28))
FLIPPED_REFS = frozenset({"C43", "C44"})
ALLOWED_REFS = frozenset(PLACEMENTS)

FATAL_DRC_TYPES = frozenset(
    {
        "clearance",
        "copper_edge_clearance",
        "copper_sliver",
        "courtyards_overlap",
        "hole_clearance",
        "hole_to_hole",
        "item_on_disabled_layer",
        "items_not_allowed",
        "shorting_items",
        "solder_mask_bridge",
        "track_not_centered_on_via",
        "tracks_crossing",
    }
)


class RemediationError(RuntimeError):
    """Fail-closed staging builder error."""


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(token) if token.isdigit() else token.casefold()
        for token in re.split(r"(\d+)", value)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    )
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )


def find_tool(candidates: Iterable[str | Path | None]) -> Path:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise RemediationError("required KiCad tool was not found")


def find_kicad_cli() -> Path:
    return find_tool(
        (
            shutil.which("kicad-cli"),
            r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
        )
    )


def find_kicad_python() -> Path:
    return find_tool(
        (
            r"C:\Program Files\KiCad\10.0\bin\python.exe",
            shutil.which("python"),
        )
    )


def run_command(
    command: list[str], cwd: Path, *, timeout_seconds: int = 300
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
    except subprocess.TimeoutExpired as exc:
        raise RemediationError(
            f"command timed out after {timeout_seconds}s: {command!r}"
        ) from exc


def item_uuid(item) -> str:
    return str(item.m_Uuid.AsString())


def point_tuple(point) -> tuple[int, int]:
    return int(point.x), int(point.y)


def footprint_state(footprint) -> tuple[object, ...]:
    position = footprint.GetPosition()
    return (
        item_uuid(footprint),
        footprint.GetReference(),
        footprint.GetFPID().GetUniStringLibId(),
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
    )


def pad_immutable_signature(pad) -> tuple[object, ...]:
    relative = pad.GetFPRelativePosition()
    size = pad.GetSize()
    drill = pad.GetDrillSize()
    offset = pad.GetOffset()
    return (
        item_uuid(pad),
        pad.GetNumber(),
        pad.GetNetname(),
        int(pad.GetAttribute()),
        int(pad.GetShape()),
        int(relative.x),
        int(relative.y),
        int(size.x),
        int(size.y),
        int(drill.x),
        int(drill.y),
        int(offset.x),
        int(offset.y),
    )


def track_signature(item) -> tuple[object, ...]:
    start = item.GetStart()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            item_uuid(item),
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
        item_uuid(item),
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
                point_tuple(contour.CPoint(point))
                for point in range(contour.PointCount())
            )
        )
    return tuple(contours)


def zone_signature(zone) -> tuple[object, ...]:
    return (
        item_uuid(zone),
        zone.GetZoneName(),
        zone.GetNetname(),
        int(zone.GetLayer()),
        tuple(int(layer) for layer in zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        polygon_points(zone.Outline()),
    )


def copper_uuid_audit(board) -> dict[str, object]:
    counts = collections.Counter(item_uuid(item) for item in board.GetTracks())
    duplicates = sorted((uuid, count) for uuid, count in counts.items() if count != 1)
    return {
        "passed": not duplicates,
        "copper_item_count": sum(counts.values()),
        "unique_uuid_count": len(counts),
        "duplicate_uuid_count": sum(count - 1 for _, count in duplicates),
        "duplicate_uuid_sample": [
            {"uuid": uuid, "multiplicity": count}
            for uuid, count in duplicates[:20]
        ],
    }


def child_uuid_state(board) -> dict[str, dict[str, tuple[str, ...]]]:
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for footprint in board.GetFootprints():
        result[footprint.GetReference()] = {
            "pads": tuple(sorted(item_uuid(pad) for pad in footprint.Pads())),
            "graphics": tuple(
                sorted(item_uuid(item) for item in footprint.GraphicalItems())
            ),
            "zones": tuple(sorted(item_uuid(zone) for zone in footprint.Zones())),
        }
    return result


def board_state(board) -> dict[str, object]:
    footprints = {
        footprint.GetReference(): footprint_state(footprint)
        for footprint in board.GetFootprints()
    }
    pads = {
        footprint.GetReference(): tuple(
            sorted(
                (pad_immutable_signature(pad) for pad in footprint.Pads()),
                key=lambda value: (natural_key(str(value[1])), str(value[0])),
            )
        )
        for footprint in board.GetFootprints()
    }
    tracks = {item_uuid(item): track_signature(item) for item in board.GetTracks()}
    zones = {item_uuid(zone): zone_signature(zone) for zone in board.Zones()}
    return {
        "footprints": footprints,
        "pads": pads,
        "children": child_uuid_state(board),
        "tracks": tracks,
        "zones": zones,
        "copper_uuid_audit": copper_uuid_audit(board),
    }


def assert_protected_hashes() -> dict[str, str]:
    actual: dict[str, str] = {}
    for path, expected in PROTECTED_HASHES.items():
        if not path.is_file():
            raise RemediationError(f"protected input is missing: {path}")
        digest = sha256_file(path)
        actual[str(path.resolve())] = digest
        if digest.casefold() != expected.casefold():
            raise RemediationError(
                f"protected hash mismatch for {path}: {digest} != {expected}"
            )
    return actual


def r5_artifact_paths() -> tuple[Path, ...]:
    candidates = set(HARDWARE.glob("*r5*.py"))
    candidates.update(path for path in STAGING.rglob("*r5*") if path.is_file())
    return tuple(sorted((path.resolve() for path in candidates), key=str))


def snapshot_paths(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): sha256_file(path) for path in paths}


def assert_snapshot_unchanged(expected: dict[str, str], label: str) -> None:
    current = snapshot_paths(Path(path) for path in expected)
    if current != expected:
        missing = sorted(set(expected) - set(current))
        changed = sorted(
            path
            for path in set(expected) & set(current)
            if expected[path] != current[path]
        )
        raise RemediationError(
            f"{label} changed unexpectedly: missing={missing}, changed={changed}"
        )


def set_footprint_placement(footprint, target) -> None:
    x_mm, y_mm, rotation_deg, side = target
    wants_bottom = side == "B"
    if wants_bottom != bool(footprint.IsFlipped()):
        footprint.Flip(footprint.GetPosition(), False)
    footprint.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
    footprint.SetOrientationDegrees(rotation_deg)


def shrink_critical_testpoint(footprint) -> dict[str, object]:
    courtyard = [
        item
        for item in footprint.GraphicalItems()
        if item.GetLayer() == pcbnew.F_CrtYd
        and item.GetShape() == pcbnew.SHAPE_T_CIRCLE
    ]
    silk = [
        item
        for item in footprint.GraphicalItems()
        if item.GetLayer() == pcbnew.F_SilkS
        and item.GetShape() == pcbnew.SHAPE_T_CIRCLE
    ]
    pads = list(footprint.Pads())
    if len(courtyard) != 1 or len(silk) != 1 or len(pads) != 1:
        raise RemediationError(
            f"{footprint.GetReference()} critical TP geometry contract changed"
        )
    pad = pads[0]
    size = pad.GetSize()
    if (
        round(pcbnew.ToMM(size.x), 6),
        round(pcbnew.ToMM(size.y), 6),
    ) != (
        CRITICAL_TP_COPPER_DIAMETER_MM,
        CRITICAL_TP_COPPER_DIAMETER_MM,
    ):
        raise RemediationError(
            f"{footprint.GetReference()} no longer has 1.0 mm copper"
        )
    circle = courtyard[0]
    center = circle.GetCenter()
    circle.SetEnd(
        pcbnew.VECTOR2I(
            center.x
            + pcbnew.FromMM(CRITICAL_TP_COURTYARD_CENTERLINE_RADIUS_MM),
            center.y,
        )
    )
    moved_silk_uuid = item_uuid(silk[0])
    courtyard_uuid = item_uuid(circle)
    # KiCad 10's SWIG FOOTPRINT.Remove() invalidates subsequent footprint
    # graphical-item iterators.  Move this circle off the production silk
    # instead; its UUID and geometry remain auditable on F.Fab.
    silk[0].SetLayer(pcbnew.F_Fab)
    return {
        "ref": footprint.GetReference(),
        "courtyard_uuid": courtyard_uuid,
        "moved_silk_uuid": moved_silk_uuid,
    }


def apply_remediation(board) -> list[dict[str, object]]:
    footprints = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    missing = sorted(ALLOWED_REFS - set(footprints), key=natural_key)
    if missing:
        raise RemediationError(f"placement refs missing: {missing}")
    for ref in sorted(PLACEMENTS, key=natural_key):
        set_footprint_placement(footprints[ref], PLACEMENTS[ref])
    critical_changes = [
        shrink_critical_testpoint(footprints[ref])
        for ref in sorted(CRITICAL_TP_REFS, key=natural_key)
    ]
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return critical_changes


def courtyard_polygon(footprint):
    copper_layer = pcbnew.B_Cu if footprint.IsFlipped() else pcbnew.F_Cu
    polygon = footprint.GetCourtyard(copper_layer)
    if polygon.OutlineCount() == 0:
        raise RemediationError(
            f"{footprint.GetReference()} has no {'B' if footprint.IsFlipped() else 'F'}.CrtYd"
        )
    return pcbnew.SHAPE_POLY_SET(polygon)


def polygon_area_intersection(first, second) -> float:
    intersection = pcbnew.SHAPE_POLY_SET(first)
    intersection.BooleanIntersection(second)
    return abs(float(intersection.Area()))


def bbox_mm(polygon) -> list[float]:
    box = polygon.BBox()
    return [
        round(pcbnew.ToMM(box.GetX()), 6),
        round(pcbnew.ToMM(box.GetY()), 6),
        round(pcbnew.ToMM(box.GetRight()), 6),
        round(pcbnew.ToMM(box.GetBottom()), 6),
    ]


def audit_courtyards(board) -> dict[str, object]:
    footprints = sorted(
        board.GetFootprints(), key=lambda footprint: natural_key(footprint.GetReference())
    )
    polygons = {
        footprint.GetReference(): courtyard_polygon(footprint)
        for footprint in footprints
    }
    footprint_by_ref = {footprint.GetReference(): footprint for footprint in footprints}
    intersections: list[dict[str, object]] = []
    for index, footprint in enumerate(footprints):
        first_ref = footprint.GetReference()
        for other in footprints[index + 1 :]:
            if footprint.IsFlipped() != other.IsFlipped():
                continue
            second_ref = other.GetReference()
            area = polygon_area_intersection(
                polygons[first_ref], polygons[second_ref]
            )
            if area != 0.0:
                intersections.append(
                    {
                        "refs": [first_ref, second_ref],
                        "side": "B" if footprint.IsFlipped() else "F",
                        "intersection_area_iu2": area,
                    }
                )

    u1 = footprint_by_ref["U1"]
    keepouts = [zone for zone in u1.Zones() if zone.GetIsRuleArea()]
    if len(keepouts) != 1:
        raise RemediationError("U1 must expose exactly one antenna rule area")
    keepout = keepouts[0]
    antenna_intrusions = []
    for ref in sorted(ALLOWED_REFS, key=natural_key):
        area = polygon_area_intersection(polygons[ref], keepout.Outline())
        if area != 0.0:
            antenna_intrusions.append(
                {"ref": ref, "intersection_area_iu2": area}
            )

    board_outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(board_outline, True):
        raise RemediationError("could not build the board outline polygon")
    outside_board = []
    edge_clearance_failures = []
    for ref in sorted(ALLOWED_REFS, key=natural_key):
        outside = pcbnew.SHAPE_POLY_SET(polygons[ref])
        outside.BooleanSubtract(board_outline)
        outside_area = abs(float(outside.Area()))
        if outside_area != 0.0:
            outside_board.append(
                {"ref": ref, "outside_area_iu2": outside_area}
            )
        box = bbox_mm(polygons[ref])
        if (
            box[0] < EDGE_CLEARANCE_MM
            or box[1] < EDGE_CLEARANCE_MM
            or box[2] > BOARD_WIDTH_MM - EDGE_CLEARANCE_MM
            or box[3] > BOARD_HEIGHT_MM - EDGE_CLEARANCE_MM
        ):
            edge_clearance_failures.append({"ref": ref, "courtyard_mm": box})

    critical_boxes = {
        ref: bbox_mm(polygons[ref])
        for ref in sorted(CRITICAL_TP_REFS, key=natural_key)
    }
    return {
        "passed": not intersections
        and not antenna_intrusions
        and not outside_board
        and not edge_clearance_failures,
        "actual_polygon_intersections": intersections,
        "antenna_keepout_bbox_mm": bbox_mm(keepout.Outline()),
        "antenna_intrusions": antenna_intrusions,
        "outside_board": outside_board,
        "edge_clearance_failures": edge_clearance_failures,
        "critical_tp_courtyard_bbox_mm": critical_boxes,
    }


def critical_tp_geometry(board) -> dict[str, object]:
    footprints = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    details = []
    passed = True
    for ref in sorted(CRITICAL_TP_REFS, key=natural_key):
        footprint = footprints[ref]
        circles = [
            item
            for item in footprint.GraphicalItems()
            if item.GetLayer() == pcbnew.F_CrtYd
            and item.GetShape() == pcbnew.SHAPE_T_CIRCLE
        ]
        silk_circles = [
            item
            for item in footprint.GraphicalItems()
            if item.GetLayer() == pcbnew.F_SilkS
            and item.GetShape() == pcbnew.SHAPE_T_CIRCLE
        ]
        pads = list(footprint.Pads())
        courtyard_box = bbox_mm(courtyard_polygon(footprint))
        if len(circles) == 1:
            center = circles[0].GetCenter()
            end = circles[0].GetEnd()
            radius_mm = pcbnew.ToMM(
                round(((end.x - center.x) ** 2 + (end.y - center.y) ** 2) ** 0.5)
            )
            line_width_mm = pcbnew.ToMM(circles[0].GetWidth())
            graphical_outer_diameter_mm = round(
                2.0 * radius_mm + line_width_mm, 6
            )
        else:
            graphical_outer_diameter_mm = -1.0
        pad_size = [
            round(pcbnew.ToMM(pads[0].GetSize().x), 6),
            round(pcbnew.ToMM(pads[0].GetSize().y), 6),
        ] if len(pads) == 1 else []
        checks = {
            "one_circular_f_courtyard": len(circles) == 1,
            "courtyard_outer_diameter_1p10_mm": graphical_outer_diameter_mm
            == 1.10,
            "copper_pad_1p00_mm": pad_size == [1.0, 1.0],
            "silk_circle_moved_off_f_silk": not silk_circles,
            "front_side": not footprint.IsFlipped(),
        }
        passed = passed and all(checks.values())
        details.append(
            {
                "ref": ref,
                "checks": checks,
                "courtyard_bbox_mm": courtyard_box,
                "graphical_outer_diameter_mm": graphical_outer_diameter_mm,
                "pad_size_mm": pad_size,
            }
        )
    return {"passed": passed, "details": details}


def placement_evidence(board) -> dict[str, object]:
    footprints = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    details: dict[str, object] = {}
    passed = True
    for ref in sorted(PLACEMENTS, key=natural_key):
        footprint = footprints[ref]
        position = footprint.GetPosition()
        actual = (
            round(pcbnew.ToMM(position.x), 6),
            round(pcbnew.ToMM(position.y), 6),
            round(float(footprint.GetOrientationDegrees()), 6),
            "B" if footprint.IsFlipped() else "F",
        )
        expected = PLACEMENTS[ref]
        matches = actual == expected
        passed = passed and matches
        details[ref] = {"expected": expected, "actual": actual, "matches": matches}
    return {"passed": passed, "details": details}


def audit_candidate(board, before: dict[str, object]) -> dict[str, object]:
    after = board_state(board)
    source_refs = set(before["footprints"])
    candidate_refs = set(after["footprints"])
    changed_refs = sorted(
        (
            ref
            for ref in source_refs & candidate_refs
            if before["footprints"][ref] != after["footprints"][ref]
        ),
        key=natural_key,
    )
    missing_refs = sorted(source_refs - candidate_refs, key=natural_key)
    extra_refs = sorted(candidate_refs - source_refs, key=natural_key)
    frozen_drift = sorted(set(changed_refs) - ALLOWED_REFS, key=natural_key)

    source_tracks = before["tracks"]
    candidate_tracks = after["tracks"]
    missing_tracks = sorted(set(source_tracks) - set(candidate_tracks))
    extra_tracks = sorted(set(candidate_tracks) - set(source_tracks))
    changed_tracks = sorted(
        uuid
        for uuid in set(source_tracks) & set(candidate_tracks)
        if source_tracks[uuid] != candidate_tracks[uuid]
    )
    source_zones = before["zones"]
    candidate_zones = after["zones"]
    missing_zones = sorted(set(source_zones) - set(candidate_zones))
    extra_zones = sorted(set(candidate_zones) - set(source_zones))
    changed_zones = sorted(
        uuid
        for uuid in set(source_zones) & set(candidate_zones)
        if source_zones[uuid] != candidate_zones[uuid]
    )

    pad_drift = sorted(
        (
            ref
            for ref in source_refs & candidate_refs
            if before["pads"][ref] != after["pads"][ref]
            and ref not in FLIPPED_REFS
        ),
        key=natural_key,
    )
    source_children = before["children"]
    candidate_children = after["children"]
    child_failures = []
    for ref in sorted(source_refs & candidate_refs, key=natural_key):
        source_child = source_children[ref]
        candidate_child = candidate_children[ref]
        if source_child != candidate_child:
            child_failures.append(ref)

    placements = placement_evidence(board)
    critical = critical_tp_geometry(board)
    courtyards = audit_courtyards(board)
    checks = {
        "same_footprint_reference_set": not missing_refs and not extra_refs,
        "only_allowlisted_footprint_state_changes": not frozen_drift
        and set(changed_refs) == set(ALLOWED_REFS),
        "all_nonflipped_pad_geometry_immutable": not pad_drift,
        "all_source_footprint_child_uuids_preserved": not child_failures,
        "all_source_track_via_uuid_geometry_exact": not missing_tracks
        and not extra_tracks
        and not changed_tracks,
        "all_source_zone_uuid_outline_settings_exact": not missing_zones
        and not extra_zones
        and not changed_zones,
        "source_copper_uuid_unique": bool(before["copper_uuid_audit"]["passed"]),
        "candidate_copper_uuid_unique": bool(after["copper_uuid_audit"]["passed"]),
        "exact_target_placements": bool(placements["passed"]),
        "critical_tp_geometry_exact": bool(critical["passed"]),
        "actual_polygon_courtyard_edge_antenna_gate": bool(courtyards["passed"]),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "changed_footprints": changed_refs,
        "missing_footprints": missing_refs,
        "extra_footprints": extra_refs,
        "frozen_footprint_drift": frozen_drift,
        "pad_drift": pad_drift,
        "child_failures": child_failures,
        "source_copper_uuid_audit": before["copper_uuid_audit"],
        "candidate_copper_uuid_audit": after["copper_uuid_audit"],
        "source_copper_count": len(source_tracks),
        "candidate_copper_count": len(candidate_tracks),
        "missing_source_copper": missing_tracks,
        "extra_copper": extra_tracks,
        "changed_source_copper": changed_tracks,
        "missing_zones": missing_zones,
        "extra_zones": extra_zones,
        "changed_zones": changed_zones,
        "placements": placements,
        "critical_testpoints": critical,
        "courtyards": courtyards,
    }


def build_once(source: Path, destination: Path, before: dict[str, object]) -> dict[str, object]:
    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise RemediationError(f"KiCad could not load source: {source}")
    critical_changes = apply_remediation(board)
    pcbnew.SaveBoard(str(destination), board)
    reloaded = pcbnew.LoadBoard(str(destination))
    if reloaded is None:
        raise RemediationError("saved remediation candidate does not reload")
    audit = audit_candidate(reloaded, before)
    if not audit["passed"]:
        raise RemediationError(
            "candidate audit failed: " + json.dumps(audit, ensure_ascii=False)
        )
    return {
        "path": str(destination.resolve()),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "critical_changes": critical_changes,
        "audit": audit,
    }


def prepare_validation_context(temp_dir: Path, board_source: Path) -> tuple[Path, Path]:
    stem = "mf1750_wroom_b3_power_tf"
    board_path = temp_dir / f"{stem}.kicad_pcb"
    shutil.copy2(board_source, board_path)
    shutil.copy2(FORMAL_SCHEMATIC, temp_dir / f"{stem}.kicad_sch")
    shutil.copy2(FORMAL_PROJECT, temp_dir / f"{stem}.kicad_pro")
    for table_name in ("fp-lib-table", "sym-lib-table"):
        source = B3_DIR / table_name
        if source.is_file():
            shutil.copy2(source, temp_dir / table_name)
    for library_name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        source = B3_DIR / library_name
        if source.is_file():
            shutil.copy2(source, temp_dir / library_name)
    for directory_name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / directory_name
        if source.is_dir():
            shutil.copytree(source, temp_dir / directory_name)
    return board_path, temp_dir / "drc.json"


def run_drc(kicad_cli: Path, board_source: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mf1750-r6-si-drc-") as directory:
        board_path, report_path = prepare_validation_context(Path(directory), board_source)
        command = [
            str(kicad_cli),
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--schematic-parity",
            "--refill-zones",
            "--output",
            str(report_path),
            str(board_path),
        ]
        completed = run_command(command, board_path.parent, timeout_seconds=300)
        if completed.returncode != 0 or not report_path.is_file():
            raise RemediationError(
                "KiCad DRC failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    categories = collections.Counter(
        str(item.get("type")) for item in raw.get("violations", [])
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "kicad_version": raw.get("kicad_version"),
        "violation_count": len(raw.get("violations", [])),
        "violation_categories": dict(sorted(categories.items())),
        "unconnected_count": len(raw.get("unconnected_items", [])),
        "schematic_parity_count": len(raw.get("schematic_parity", [])),
        "schematic_parity_sample": raw.get("schematic_parity", [])[:10],
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "raw": raw,
    }


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    fatal = {
        name: int(candidate_categories.get(name, 0))
        for name in sorted(FATAL_DRC_TYPES)
    }
    deltas = {
        name: int(candidate_categories.get(name, 0) - source_categories.get(name, 0))
        for name in sorted(set(source_categories) | set(candidate_categories))
        if candidate_categories.get(name, 0) != source_categories.get(name, 0)
    }
    checks = {
        "source_schematic_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "all_fatal_geometry_categories_zero": not any(fatal.values()),
        "placement_only_unconnected_count_unchanged": candidate["unconnected_count"]
        == source["unconnected_count"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "fatal_category_counts": fatal,
        "category_count_deltas": deltas,
        "unconnected_delta": candidate["unconnected_count"]
        - source["unconnected_count"],
    }


def run_board_verifier(kicad_python: Path, board: Path) -> dict[str, object]:
    board_hash_before = sha256_file(board)
    command = [
        str(kicad_python),
        str(BOARD_VERIFIER),
        str(board.resolve()),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = run_command(command, ROOT, timeout_seconds=300)
    if completed.returncode != 0:
        raise RemediationError(
            "board verifier failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RemediationError("board verifier did not return JSON") from exc
    summary = report.get("summary", {})
    if (
        report.get("passed") is not True
        or summary.get("total") != 13
        or summary.get("passed") != 13
        or summary.get("failed") != 0
    ):
        raise RemediationError("board verifier was not 13/13 PASS")
    for flag in ("hardware_accessed", "boards_modified", "schematics_modified"):
        if report.get(flag) is not False:
            raise RemediationError(f"board verifier flag {flag} is not false")
    selected = report.get("inputs", {}).get("staging_r3_pcb", {})
    if (
        Path(str(selected.get("path", ""))).resolve() != board.resolve()
        or str(selected.get("sha256", "")).casefold() != board_hash_before
    ):
        raise RemediationError("board verifier evidence is not bound to the output")
    board_hash_after = sha256_file(board)
    if board_hash_after != board_hash_before:
        raise RemediationError("board verifier changed the candidate")
    atomic_write_json(VERIFIER_JSON, report)
    return {
        "passed": True,
        "command": command,
        "summary": summary,
        "board_sha256_before": board_hash_before,
        "board_sha256_after": board_hash_after,
        "report_path": str(VERIFIER_JSON.resolve()),
        "report_sha256": sha256_file(VERIFIER_JSON),
    }


def render_preview(
    kicad_cli: Path, board: Path, output: Path, side: str, temp_dir: Path
) -> dict[str, object]:
    board_copy = temp_dir / f"render_{side}.kicad_pcb"
    rendered = temp_dir / output.name
    shutil.copy2(board, board_copy)
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
        str(rendered),
        str(board_copy),
    ]
    completed = run_command(command, temp_dir, timeout_seconds=300)
    if completed.returncode != 0 or not rendered.is_file() or rendered.stat().st_size == 0:
        raise RemediationError(
            f"{side} preview failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    atomic_write_bytes(output, rendered.read_bytes())
    return {
        "side": side,
        "path": str(output.resolve()),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "command": command,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_BOARD)
    parser.add_argument(
        "--source-sha256",
        help="explicit source hash; the only accepted content is the reviewed R4 SHA",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.resolve()
    report: dict[str, object]
    previous_output = OUTPUT_BOARD.read_bytes() if OUTPUT_BOARD.is_file() else None
    output_published = False
    protected_before: dict[str, str] = {}
    r5_before: dict[str, str] = {}
    try:
        if pcbnew is None:
            raise RemediationError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RemediationError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if source != SOURCE_BOARD.resolve():
            raise RemediationError("R6 placement source must be the fixed R4 staging path")
        if not source.is_file():
            raise RemediationError(f"R4 source is missing: {source}")
        source_hash = sha256_file(source)
        supplied_hash = args.source_sha256.casefold() if args.source_sha256 else SOURCE_SHA256
        if supplied_hash != SOURCE_SHA256 or source_hash != SOURCE_SHA256:
            raise RemediationError(
                f"R4 source hash mismatch: supplied={supplied_hash}, actual={source_hash}"
            )
        locks = list(B3_DIR.glob("~*.lck")) + list(STAGING.glob("~*.lck"))
        if locks:
            raise RemediationError("close KiCad first: " + ", ".join(map(str, locks)))
        protected_before = assert_protected_hashes()
        r5_before = snapshot_paths(r5_artifact_paths())
        kicad_cli = find_kicad_cli()
        kicad_python = find_kicad_python()

        source_board = pcbnew.LoadBoard(str(source))
        if source_board is None:
            raise RemediationError("KiCad could not parse the R4 source")
        before = board_state(source_board)
        if not before["copper_uuid_audit"]["passed"]:
            raise RemediationError("R4 source contains duplicate track/via UUIDs")

        STAGING.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="mf1750-r6-si-place-", dir=STAGING
        ) as directory:
            temp_dir = Path(directory)
            run1_path = temp_dir / "candidate_run1.kicad_pcb"
            run2_path = temp_dir / "candidate_run2.kicad_pcb"
            run1 = build_once(source, run1_path, before)
            run2 = build_once(source, run2_path, before)
            deterministic = run1["sha256"] == run2["sha256"]
            if not deterministic:
                raise RemediationError(
                    f"non-deterministic board hashes: {run1['sha256']} != {run2['sha256']}"
                )

            source_drc = run_drc(kicad_cli, source)
            candidate_drc = run_drc(kicad_cli, run1_path)
            gate = drc_gate(source_drc, candidate_drc)
            if not gate["passed"]:
                raise RemediationError(
                    "DRC gate failed: " + json.dumps(gate, ensure_ascii=False)
                )

            assert_protected_hashes()
            assert_snapshot_unchanged(r5_before, "R5 artifacts")
            atomic_write_bytes(OUTPUT_BOARD, run1_path.read_bytes())
            output_published = True
            if sha256_file(OUTPUT_BOARD) != run1["sha256"]:
                raise RemediationError("published output hash differs from deterministic run")

            verifier = run_board_verifier(kicad_python, OUTPUT_BOARD)
            top = render_preview(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top", temp_dir)
            bottom = render_preview(
                kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom", temp_dir
            )
            atomic_write_json(SOURCE_DRC_JSON, source_drc)
            atomic_write_json(CANDIDATE_DRC_JSON, candidate_drc)

            protected_after = assert_protected_hashes()
            assert_snapshot_unchanged(r5_before, "R5 artifacts")
            final_hash = sha256_file(OUTPUT_BOARD)
            if final_hash != run1["sha256"]:
                raise RemediationError("output changed after final verification")

            report = {
                "schema": 1,
                "tool": Path(__file__).name,
                "script_sha256": sha256_file(Path(__file__)),
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R6_SI_PLACEMENT_REMEDIATED_NOT_ROUTED",
                "overall_status": "HOLD",
                "operation_completed": True,
                "locally_verified": True,
                "hardware_accessed": False,
                "inputs": {
                    "r4": {"path": str(source), "sha256": source_hash},
                    "protected_before": protected_before,
                    "protected_after": protected_after,
                },
                "output": {
                    "path": str(OUTPUT_BOARD.resolve()),
                    "sha256": final_hash,
                    "bytes": OUTPUT_BOARD.stat().st_size,
                },
                "determinism": {
                    "passed": deterministic,
                    "run1_sha256": run1["sha256"],
                    "run2_sha256": run2["sha256"],
                    "run1_bytes": run1["bytes"],
                    "run2_bytes": run2["bytes"],
                },
                "placement": {
                    "allowed_refs": sorted(ALLOWED_REFS, key=natural_key),
                    "target_map": {
                        ref: PLACEMENTS[ref]
                        for ref in sorted(PLACEMENTS, key=natural_key)
                    },
                    "documented_coordinate_adjustment": {
                        "ref": "TP21",
                        "initial_xy_mm": [39.0, 67.125],
                        "final_xy_mm": [33.5, 69.8],
                        "reason": "clear future /BUSY_N and /SCL copper while keeping an /SI0-local tee at R59.1",
                    },
                    "critical_tp_courtyard_outer_diameter_mm": CRITICAL_TP_COURTYARD_OUTER_DIAMETER_MM,
                    "critical_tp_copper_diameter_mm": CRITICAL_TP_COPPER_DIAMETER_MM,
                    "critical_tp_silk_circle_moved_to_f_fab": True,
                },
                "audit": run1["audit"],
                "drc": {
                    "source": {
                        "path": str(SOURCE_DRC_JSON.resolve()),
                        "sha256": sha256_file(SOURCE_DRC_JSON),
                        "summary": {
                            key: value for key, value in source_drc.items() if key != "raw"
                        },
                    },
                    "candidate": {
                        "path": str(CANDIDATE_DRC_JSON.resolve()),
                        "sha256": sha256_file(CANDIDATE_DRC_JSON),
                        "summary": {
                            key: value for key, value in candidate_drc.items() if key != "raw"
                        },
                    },
                    "gate": gate,
                },
                "project_board_verifier": verifier,
                "previews": {"top": top, "bottom": bottom},
                "r5_artifact_count_protected": len(r5_before),
                "r5_artifacts_unchanged": True,
                "holds": [
                    "placement-only candidate; all new schematic nets remain unrouted",
                    "R5 route builders must regenerate pad contracts from this R6 placement",
                    "do not replay the old U6.19-to-(38.2,63.225) EPD_BUF_OE_N escape through C45",
                    "USB differential impedance and TF single-ended SI remain HOLD pending stackup/field solving",
                    "C43/C44 bottom-side assembly Z-envelope remains a mechanical HOLD",
                    "J6 battery connector/pack/NTC/HOLD contract remains HOLD",
                ],
            }
    except Exception as exc:
        if output_published:
            if previous_output is None:
                if OUTPUT_BOARD.is_file():
                    OUTPUT_BOARD.unlink()
            else:
                atomic_write_bytes(OUTPUT_BOARD, previous_output)
        report = {
            "schema": 1,
            "tool": Path(__file__).name,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "state": "HOLD_R6_SI_PLACEMENT_REMEDIATION_FAILED",
            "overall_status": "FAIL",
            "operation_completed": False,
            "locally_verified": False,
            "hardware_accessed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "output": str(OUTPUT_BOARD.resolve()),
            "protected_before": protected_before,
            "r5_artifact_count_protected": len(r5_before),
        }
    atomic_write_json(REPORT_JSON, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
