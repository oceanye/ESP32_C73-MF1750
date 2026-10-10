#!/usr/bin/env python3
"""Read-only R14 audit of the already-present In1.Cu GND reference plane.

Operating mode: REVISION, staging evidence only.  The SHA-bound R13 button
mainline is the sole PCB input.  Audit found that it already contains the
required single, filled, explicitly antenna-notched In1.Cu GND zone, so this
script deliberately creates no PCB candidate and consumes no UUID.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated.kicad_pcb"
SOURCE_SHA256 = "4cccd877a42f0e787af73183fa70548f64ac2bb00d7461cede542bc1f840d19a"
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"

REPORT_JSON = STAGING / "r14_in1_gnd_plane_readonly_audit.json"
DRC_JSON = STAGING / "r14_in1_gnd_plane_readonly_drc.json"
VERIFIER_JSON = STAGING / "r14_in1_gnd_plane_readonly_board_verifier.json"
PREVIEW_DIR = STAGING / "r14_in1_gnd_plane_readonly_preview"
TOP_PNG = PREVIEW_DIR / "r14_in1_gnd_plane_source_top.png"
BOTTOM_PNG = PREVIEW_DIR / "r14_in1_gnd_plane_source_bottom.png"
ISO_PNG = PREVIEW_DIR / "r14_in1_gnd_plane_source_iso.png"
IN1_SVG = PREVIEW_DIR / "r14_in1_gnd_plane_source_In1_Cu.svg"

ROUTING_UUID_SEED = 1750941
EXPECTED_ZONE_UUID = "6f4fa8e6-1a4e-4009-8d6c-7ea7912652e9"
EXPECTED_OUTLINE_MM = (
    (0.65, 0.65),
    (79.35, 0.65),
    (79.35, 65.70),
    (58.45, 65.70),
    (58.45, 114.30),
    (79.35, 114.30),
    (79.35, 124.35),
    (0.65, 124.35),
)
EXPECTED_ANTENNA_BBOX_MM = (58.75, 66.00, 79.75, 114.00)
EXPECTED_DRC_FINGERPRINT_SHA256 = "cdec11fa2ac02e7ee4459976e4006827356172bed506c38504eb4073f2dbccd5"
EXPECTED_DRC_CATEGORIES = {"drill_out_of_range": 12, "track_dangling": 1}
EXPECTED_UNCONNECTED = 106
EXPECTED_GND_UNCONNECTED = 1


class AuditError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def point_mm(point: Any) -> tuple[float, float]:
    return (round(float(pcbnew.ToMM(point.x)), 6), round(float(pcbnew.ToMM(point.y)), 6))


def item_uuid(item: Any) -> str:
    value = item.m_Uuid.AsString()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise AuditError(f"invalid KiCad UUID: {value!r}")
    return value


def polygon_points(zone: Any) -> tuple[tuple[float, float], ...]:
    outline = zone.Outline()
    if outline.OutlineCount() != 1:
        raise AuditError(f"zone {zone.GetZoneName()} does not have one outline")
    contour = outline.Outline(0)
    return tuple(point_mm(contour.CPoint(index)) for index in range(contour.PointCount()))


def canonical_polygon(points: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    variants: list[tuple[tuple[float, float], ...]] = []
    for sequence in (points, tuple(reversed(points))):
        variants.extend(sequence[index:] + sequence[:index] for index in range(len(sequence)))
    return min(variants)


def bbox_mm(shape: Any) -> tuple[float, float, float, float]:
    box = shape.GetBoundingBox()
    return tuple(
        round(float(pcbnew.ToMM(value)), 6)
        for value in (box.GetX(), box.GetY(), box.GetRight(), box.GetBottom())
    )


def zone_signature(board: Any, zone: Any) -> tuple[Any, ...]:
    return (
        item_uuid(zone),
        zone.GetZoneName(),
        zone.GetNetname(),
        board.GetLayerName(zone.GetLayer()),
        tuple(board.GetLayerName(layer) for layer in zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        int(zone.GetPadConnection()),
        bool(zone.GetDoNotAllowZoneFills()),
        bool(zone.GetDoNotAllowTracks()),
        bool(zone.GetDoNotAllowVias()),
        bool(zone.GetDoNotAllowPads()),
        bool(zone.GetDoNotAllowFootprints()),
        polygon_points(zone),
    )


def track_signature(board: Any, item: Any) -> tuple[Any, ...]:
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            item_uuid(item), "via", item.GetNetname(), point_mm(item.GetPosition()),
            round(float(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu))), 6),
            round(float(pcbnew.ToMM(item.GetDrillValue())), 6),
            board.GetLayerName(item.TopLayer()), board.GetLayerName(item.BottomLayer()),
        )
    return (
        item_uuid(item), "track", item.GetNetname(), board.GetLayerName(item.GetLayer()),
        point_mm(item.GetStart()), point_mm(item.GetEnd()),
        round(float(pcbnew.ToMM(item.GetWidth())), 6),
    )


def footprint_signature(board: Any, footprint: Any) -> tuple[Any, ...]:
    pads = []
    for pad in footprint.Pads():
        pads.append(
            (
                item_uuid(pad), pad.GetNumber(), pad.GetNetname(), point_mm(pad.GetPosition()),
                round(float(pad.GetOrientationDegrees()), 6),
                tuple(board.GetLayerName(layer) for layer in pad.GetLayerSet().Seq()),
                point_mm(pad.GetSize()), point_mm(pad.GetDrillSize()), int(pad.GetShape()),
            )
        )
    return (
        footprint.GetReference(), footprint.GetValue(), footprint.GetFPID().GetUniStringLibId(),
        point_mm(footprint.GetPosition()), round(float(footprint.GetOrientationDegrees()), 6),
        board.GetLayerName(footprint.GetLayer()), bool(footprint.IsFlipped()), bool(footprint.IsDNP()),
        int(footprint.GetAttributes()), footprint.GetPath().AsString(), tuple(sorted(pads, key=repr)),
    )


def geometry_state(board: Any) -> dict[str, Any]:
    footprints = sorted((footprint_signature(board, fp) for fp in board.GetFootprints()), key=repr)
    copper = sorted((track_signature(board, item) for item in board.GetTracks()), key=repr)
    zones = sorted((zone_signature(board, zone) for zone in board.Zones()), key=repr)
    return {
        "footprint_count": len(footprints), "footprints_sha256": json_digest(footprints),
        "copper_count": len(copper), "copper_sha256": json_digest(copper),
        "zone_count": len(zones), "zones_sha256": json_digest(zones),
    }


def audit_plane(board: Any) -> dict[str, Any]:
    ground_by_layer: dict[str, list[Any]] = collections.defaultdict(list)
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and zone.GetNetname() == "GND":
            ground_by_layer[board.GetLayerName(zone.GetLayer())].append(zone)
    matches = ground_by_layer.get("In1.Cu", [])
    if len(matches) != 1:
        raise AuditError(f"expected one In1.Cu GND zone, found {len(matches)}")
    zone = matches[0]
    filled = zone.GetFilledPolysList(pcbnew.In1_Cu)
    u1 = board.FindFootprintByReference("U1")
    keepouts = [item for item in u1.Zones() if item.GetIsRuleArea()] if u1 is not None else []
    if len(keepouts) != 1:
        raise AuditError(f"expected one embedded U1 keepout, found {len(keepouts)}")
    keepout = keepouts[0]
    outline_intersection = pcbnew.SHAPE_POLY_SET(zone.Outline())
    outline_intersection.BooleanIntersection(keepout.Outline())
    fill_intersection = pcbnew.SHAPE_POLY_SET(filled)
    fill_intersection.BooleanIntersection(keepout.Outline())
    points = polygon_points(zone)
    layer_counts = {name: len(items) for name, items in sorted(ground_by_layer.items())}
    keepout_layers = tuple(board.GetLayerName(layer) for layer in keepout.GetLayerSet().Seq())
    signal_tracks_on_in1 = [
        item_uuid(item) for item in board.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA) and item.GetLayer() == pcbnew.In1_Cu
    ]
    checks = {
        "zone_uuid_exact": item_uuid(zone) == EXPECTED_ZONE_UUID,
        "zone_name_exact": zone.GetZoneName() == "IN1_SOLID_GND_PLANE",
        "zone_net_exact": zone.GetNetname() == "GND",
        "single_layer_in1_exact": tuple(board.GetLayerName(layer) for layer in zone.GetLayerSet().Seq()) == ("In1.Cu",),
        "per_layer_gnd_zone_contract_exactly_one_f_in1_b": layer_counts == {"B.Cu": 1, "F.Cu": 1, "In1.Cu": 1},
        "outline_eight_vertices_exact": canonical_polygon(points) == canonical_polygon(EXPECTED_OUTLINE_MM),
        "board_edge_inset_bbox_exact": bbox_mm(zone) == (0.65, 0.65, 79.35, 124.35),
        "zone_filled": bool(zone.IsFilled()) and not bool(zone.NeedRefill()),
        "filled_single_connected_outline": filled.OutlineCount() == 1,
        "filled_outline_has_no_holes_after_kicad_fracture": filled.HoleCount(0) == 0 if filled.OutlineCount() else False,
        "solid_pad_connection": int(zone.GetPadConnection()) == int(pcbnew.ZONE_CONNECTION_FULL),
        "clearance_0p20_mm": int(zone.GetLocalClearance()) == int(pcbnew.FromMM(0.20)),
        "min_thickness_0p20_mm": int(zone.GetMinThickness()) == int(pcbnew.FromMM(0.20)),
        "u1_keepout_all_four_copper_layers": keepout_layers == ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu"),
        "u1_keepout_bbox_exact": bbox_mm(keepout) == EXPECTED_ANTENNA_BBOX_MM,
        "u1_keepout_forbids_zone_fills": bool(keepout.GetDoNotAllowZoneFills()),
        "explicit_zone_outline_notch_has_zero_keepout_intersection": float(outline_intersection.Area()) == 0.0,
        "filled_plane_has_zero_keepout_intersection": float(fill_intersection.Area()) == 0.0,
        "no_signal_tracks_on_in1": not signal_tracks_on_in1,
    }
    return {
        "passed": all(checks.values()), "checks": checks,
        "zone": {
            "uuid": item_uuid(zone), "name": zone.GetZoneName(), "net": zone.GetNetname(),
            "layer": board.GetLayerName(zone.GetLayer()),
            "layer_set": [board.GetLayerName(layer) for layer in zone.GetLayerSet().Seq()],
            "outline_vertices_mm": [list(point) for point in points], "outline_vertex_count": len(points),
            "bbox_mm": list(bbox_mm(zone)), "clearance_mm": float(pcbnew.ToMM(zone.GetLocalClearance())),
            "min_thickness_mm": float(pcbnew.ToMM(zone.GetMinThickness())),
            "pad_connection": "FULL", "is_filled": bool(zone.IsFilled()), "needs_refill": bool(zone.NeedRefill()),
            "filled_outline_count": filled.OutlineCount(),
            "filled_hole_count": filled.HoleCount(0) if filled.OutlineCount() else None,
            "filled_vertex_count": filled.VertexCount(),
            "filled_area_mm2": round(float(filled.Area()) / 1_000_000_000_000.0, 6),
        },
        "ground_zone_count_by_layer": layer_counts,
        "antenna_keepout": {
            "bbox_mm": list(bbox_mm(keepout)), "layer_set": list(keepout_layers),
            "notch_margin_mm": 0.30,
            "derived_notch": {"left_mm": 58.45, "top_mm": 65.70, "bottom_mm": 114.30},
            "outline_intersection_area_iu2": float(outline_intersection.Area()),
            "filled_intersection_area_iu2": float(fill_intersection.Area()),
        },
        "signal_track_uuids_on_in1": signal_tracks_on_in1,
    }


def prepare_context(directory: Path) -> Path:
    stem = "mf1750_wroom_b3_power_tf"
    board = directory / f"{stem}.kicad_pcb"
    shutil.copy2(SOURCE_BOARD, board)
    shutil.copy2(FORMAL_SCHEMATIC, directory / f"{stem}.kicad_sch")
    shutil.copy2(FORMAL_PROJECT, directory / f"{stem}.kicad_pro")
    for name in ("fp-lib-table", "sym-lib-table", "b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        source = B3_DIR / name
        if source.is_file():
            shutil.copy2(source, directory / name)
    for name in ("b3_wroom_footprints.pretty", "MF1750_Compact.pretty", "MF1750_Production.pretty"):
        source = B3_DIR / name
        if not source.is_dir():
            raise AuditError(f"missing local footprint library: {source}")
        shutil.copytree(source, directory / name)
    return board


def violation_fingerprints(raw: dict[str, Any]) -> list[tuple[Any, ...]]:
    result = []
    for violation in raw.get("violations", []):
        items = []
        for item in violation.get("items", []):
            pos = item.get("pos", {})
            items.append((str(item.get("uuid", "")), round(float(pos.get("x", 0.0)), 6), round(float(pos.get("y", 0.0)), 6)))
        result.append((str(violation.get("type", "")), tuple(sorted(items))))
    return sorted(result, key=repr)


def unconnected_by_net(raw: dict[str, Any]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names: list[str] = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(filter(None, names))
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def run_drc(kicad_cli: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mf1750-r14-in1-drc-") as name:
        directory = Path(name)
        board = prepare_context(directory)
        output = directory / "drc.json"
        command = [
            str(kicad_cli), "pcb", "drc", "--format", "json", "--severity-all",
            "--schematic-parity", "--refill-zones", "--output", str(output), str(board),
        ]
        completed = subprocess.run(command, cwd=directory, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
        if completed.returncode != 0 or not output.is_file():
            raise AuditError("KiCad DRC failed: " + (completed.stderr.strip() or completed.stdout.strip()))
        raw = json.loads(output.read_text(encoding="utf-8"))
    fingerprints = violation_fingerprints(raw)
    categories = dict(sorted(collections.Counter(str(item.get("type", "")) for item in raw.get("violations", [])).items()))
    nets = unconnected_by_net(raw)
    return {
        "kicad_version": raw.get("kicad_version"), "schema": raw.get("$schema"),
        "violation_count": len(raw.get("violations", [])), "violation_categories": categories,
        "violation_fingerprints": fingerprints, "violation_fingerprint_sha256": json_digest(fingerprints),
        "unconnected_count": len(raw.get("unconnected_items", [])), "unconnected_by_net": nets,
        "gnd_unconnected_count": nets.get("GND", 0),
        "schematic_parity_count": len(raw.get("schematic_parity", [])),
        "ignored_check_keys": sorted(str(item.get("key")) for item in raw.get("ignored_checks", [])),
    }


def run_verifier(kicad_python: Path) -> dict[str, Any]:
    command = [str(kicad_python), str(BOARD_VERIFIER), str(SOURCE_BOARD), "--allow-board-only", "H3", "--allow-board-only", "H4"]
    completed = subprocess.run(command, cwd=ROOT, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode != 0:
        raise AuditError("project verifier failed: " + (completed.stderr.strip() or completed.stdout[-2000:]))
    raw = json.loads(completed.stdout)
    return {
        "tool": raw.get("tool"), "mode": raw.get("mode"), "result": raw.get("result"),
        "passed": raw.get("passed"), "summary": raw.get("summary"),
        "verified_board": raw.get("inputs", {}).get("staging_r3_pcb"),
        "check_status": {name: item.get("status") for name, item in sorted(raw.get("checks", {}).items())},
        "wroom_antenna_evidence": raw.get("checks", {}).get("wroom_antenna_rule_area", {}).get("evidence"),
        "hardware_accessed": raw.get("hardware_accessed"), "boards_modified": raw.get("boards_modified"),
        "schematics_modified": raw.get("schematics_modified"),
    }


def run_command(command: list[str], output: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=B3_DIR, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise AuditError("preview generation failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    # KiCad's 3-D renderer and SVG exporter may embed or produce run-variant
    # bytes.  The images are human-review evidence, not a determinism gate;
    # keep volatile byte counts/hashes out of the canonical JSON report.
    return {
        "path": str(output.resolve()),
        "classification": "VISUAL_EVIDENCE_ONLY_BYTES_NOT_A_DETERMINISM_GATE",
    }


def render_previews(kicad_cli: Path) -> dict[str, Any]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    common = [str(kicad_cli), "pcb", "render", "--background", "opaque", "--quality", "high", "--width", "1400", "--height", "1800"]
    top = run_command(common + ["--side", "top", "--output", str(TOP_PNG), str(SOURCE_BOARD)], TOP_PNG)
    bottom = run_command(common + ["--side", "bottom", "--output", str(BOTTOM_PNG), str(SOURCE_BOARD)], BOTTOM_PNG)
    iso = run_command(common + ["--side", "top", "--perspective", "--rotate", "-35,0,35", "--output", str(ISO_PNG), str(SOURCE_BOARD)], ISO_PNG)
    svg_command = [
        str(kicad_cli), "pcb", "export", "svg", "--mode-single", "--fit-page-to-board",
        "--exclude-drawing-sheet", "--check-zones", "--layers", "In1.Cu,Edge.Cuts",
        "--output", str(IN1_SVG), str(SOURCE_BOARD),
    ]
    in1 = run_command(svg_command, IN1_SVG)
    return {"top": top, "bottom": bottom, "isometric": iso, "in1_svg": in1}


def parse_write_determinism() -> dict[str, Any]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if source is None:
        raise AuditError("KiCad could not parse source")
    source_state = geometry_state(source)
    with tempfile.TemporaryDirectory(prefix="mf1750-r14-in1-roundtrip-") as name:
        first_path = Path(name) / "first.kicad_pcb"
        second_path = Path(name) / "second.kicad_pcb"
        first = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
        second = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
        if not pcbnew.SaveBoard(str(first_path), first) or not pcbnew.SaveBoard(str(second_path), second):
            raise AuditError("temporary KiCad parse/write failed")
        first_sha = sha256_file(first_path)
        second_sha = sha256_file(second_path)
        reloaded = pcbnew.LoadBoard(str(first_path))
        reloaded_state = geometry_state(reloaded)
        return {
            "temporary_only_no_candidate_published": True,
            "double_temporary_save_byte_identical": first_path.read_bytes() == second_path.read_bytes(),
            "first_sha256": first_sha, "second_sha256": second_sha,
            "source_geometry": source_state, "reloaded_geometry": reloaded_state,
            "footprints_copper_existing_zones_exact_after_roundtrip": source_state == reloaded_state,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-python", type=Path, default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"))
    args = parser.parse_args()
    if pcbnew is None:
        raise AuditError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
    if str(pcbnew.GetBuildVersion()) != "10.0.3":
        raise AuditError(f"KiCad 10.0.3 required, found {pcbnew.GetBuildVersion()}")
    locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
    if locks:
        raise AuditError("close KiCad first: " + ", ".join(str(path) for path in locks))
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise AuditError("frozen R13 source is missing or hash-mismatched")
    kicad_cli = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
    if not kicad_cli.is_file():
        raise AuditError("KiCad CLI not found")
    protected = {path: sha256_file(path) for path in (SOURCE_BOARD, FORMAL_BOARD, FORMAL_SCHEMATIC, FORMAL_PROJECT)}
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    plane = audit_plane(board)
    roundtrip = parse_write_determinism()
    drc_first, drc_second = run_drc(kicad_cli), run_drc(kicad_cli)
    verifier_first, verifier_second = run_verifier(args.kicad_python), run_verifier(args.kicad_python)
    drc_checks = {
        "two_runs_canonical_identical": drc_first == drc_second,
        "violations_exactly_13": drc_first["violation_count"] == 13,
        "categories_exact": drc_first["violation_categories"] == EXPECTED_DRC_CATEGORIES,
        "inherited_violation_fingerprint_exact": drc_first["violation_fingerprint_sha256"] == EXPECTED_DRC_FINGERPRINT_SHA256,
        "unconnected_exactly_106": drc_first["unconnected_count"] == EXPECTED_UNCONNECTED,
        "gnd_unconnected_exactly_1_no_change": drc_first["gnd_unconnected_count"] == EXPECTED_GND_UNCONNECTED,
        "schematic_parity_zero": drc_first["schematic_parity_count"] == 0,
    }
    verifier_checks = {
        "two_runs_canonical_identical": verifier_first == verifier_second,
        "verifier_13_of_13": verifier_first.get("summary") == {"total": 13, "passed": 13, "failed": 0},
        "passed_true": verifier_first.get("passed") is True,
        "read_only_flags": all(verifier_first.get(key) is False for key in ("hardware_accessed", "boards_modified", "schematics_modified")),
    }
    if not plane["passed"] or not all(drc_checks.values()) or not all(verifier_checks.values()):
        raise AuditError("plane, DRC, or verifier gate failed")
    if not roundtrip["double_temporary_save_byte_identical"] or not roundtrip["footprints_copper_existing_zones_exact_after_roundtrip"]:
        raise AuditError("temporary parse/write determinism gate failed")
    STAGING.mkdir(parents=True, exist_ok=True)
    DRC_JSON.write_text(json.dumps(drc_first, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    VERIFIER_JSON.write_text(json.dumps(verifier_first, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    previews = render_previews(kicad_cli)
    protected_after = {path: sha256_file(path) for path in protected}
    if protected != protected_after:
        raise AuditError("source or formal design changed during read-only audit")
    report = {
        "operating_mode": "REVISION",
        "mode": "STAGING_ONLY_READ_ONLY_IN1_GND_PLANE_AUDIT",
        "revision": "R14_IN1_GND_PLANE_READONLY_AUDIT",
        "state": "NO_CHANGE_REQUIREMENT_ALREADY_SATISFIED",
        "overall_status": "NO_CHANGE_REQUIREMENT_ALREADY_SATISFIED",
        "operation_completed": True,
        "locally_verified": False,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "network_accessed": False,
        "pcb_candidate_created": False,
        "uuid_seed": {"reserved": ROUTING_UUID_SEED, "consumed": False, "reason": "no new zone or PCB object created"},
        "source": {"path": str(SOURCE_BOARD.resolve()), "sha256": SOURCE_SHA256, "bytes": SOURCE_BOARD.stat().st_size},
        "builder": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__))},
        "conclusion": "The frozen R13 source already has the required unique, filled, continuous In1.Cu GND reference plane with an explicit antenna notch; adding a second overlapping zone would be redundant and violate the per-layer exactly-one contract.",
        "plane_audit": plane,
        "parse_write_determinism": roundtrip,
        "drc": {**drc_first, "checks": drc_checks, "passed": all(drc_checks.values())},
        "board_verifier": {**verifier_first, "checks": verifier_checks, "gate_passed": all(verifier_checks.values())},
        "protected_sources": {"unchanged": True, "hashes": {str(path.resolve()): value for path, value in protected.items()}},
        "artifacts": {
            "drc_json": {"path": str(DRC_JSON.resolve()), "sha256": sha256_file(DRC_JSON)},
            "board_verifier_json": {"path": str(VERIFIER_JSON.resolve()), "sha256": sha256_file(VERIFIER_JSON)},
            "previews": previews,
        },
        "holds": ["Whole-board routing remains incomplete; this read-only plane audit is not a manufacturing release."],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "source_sha256": SOURCE_SHA256, "zone_uuid": plane["zone"]["uuid"], "drc": drc_first["violation_count"], "open": drc_first["unconnected_count"], "gnd_open": drc_first["gnd_unconnected_count"], "parity": drc_first["schematic_parity_count"], "verifier": verifier_first["summary"], "report": str(REPORT_JSON.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
