"""Build a four-layer Rev B1 candidate with one power-routing layer.

Rev B0 is immutable input.  In1.Cu is reserved as a full-board /GND plane;
all /3V3, /EPD_3V3, and /V_B distribution tracks are moved to In2.Cu.
Every SMD supply pin uses a short outer-layer dog-bone to a conventional
0.60/0.30 mm plated through via.  There are no blind, buried, micro, or
via-in-pad structures.

This is an engineering candidate, not a released manufacturing design.  A
fabricator stack-up and the exact socket/connector parts still require review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
B0_DIR = ROOT / "hardware" / "mf1750_devkitc_compact"
DEFAULT_INPUT = B0_DIR / "mf1750_devkitc_compact.kicad_pcb"
DEFAULT_OUT_DIR = ROOT / "hardware" / "mf1750_devkitc_b1_single_power_layer"
DEFAULT_OUTPUT = DEFAULT_OUT_DIR / "mf1750_devkitc_b1_single_power_layer.kicad_pcb"
DEFAULT_AUDIT = DEFAULT_OUT_DIR / "design_audit.json"

VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
TARGET_WIDTHS_MM = {"/3V3": 0.60, "/EPD_3V3": 0.60, "/V_B": 0.80}
GND_STITCHING_VIAS_MM = (
    (8.20, 1.80),
    (26.00, 10.00),
    (30.00, 11.00),
    (39.00, 11.00),
    (23.20, 29.00),
    (58.20, 27.525),
    (33.225, 30.40),
    (15.40, 44.00),
)

# Centres proven independently by the ordinary-through-via dog-bone probe.
VIA_POSITIONS_MM: dict[tuple[str, str], tuple[float, float]] = {
    ("L1", "1"): (8.475, 27.500),
    ("R4", "1"): (3.675, 42.500),
    ("R4", "2"): (4.325, 43.000),
    ("C3", "1"): (26.225, 43.000),
    ("C23", "1"): (9.525, 44.000),
    ("Q2", "2"): (37.8625, 28.450),
    ("R8", "1"): (8.675, 45.500),
    ("R8", "2"): (8.825, 43.000),
    ("C0", "1"): (5.500, 29.225),
    ("C22", "1"): (34.775, 28.200),
    ("R9", "2"): (41.500, 19.325),
    ("R7", "1"): (20.675, 44.000),
    ("R10", "2"): (44.000, 19.325),
    ("R6", "1"): (16.675, 44.000),
    ("TP1", "1"): (3.000, 48.000),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def point_mm(position: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)


def add_track(
    board: pcbnew.BOARD,
    netcode: int,
    layer: int,
    width_mm: float,
    start: pcbnew.VECTOR2I,
    end: pcbnew.VECTOR2I,
) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNetCode(netcode)
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width_mm))
    track.SetStart(start)
    track.SetEnd(end)
    board.Add(track)


def target_smd_pads(
    board: pcbnew.BOARD, netcodes: dict[str, int]
) -> list[tuple[str, str, str, pcbnew.PAD]]:
    names_by_code = {code: name for name, code in netcodes.items()}
    result: list[tuple[str, str, str, pcbnew.PAD]] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            netname = names_by_code.get(pad.GetNetCode())
            if netname is None or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            result.append((footprint.GetReference(), pad.GetNumber(), netname, pad))
    return result


def remove_b0_supply_routing(board: pcbnew.BOARD, netcodes: dict[str, int]) -> None:
    """Discard only B0 supply copper; all signal routing remains untouched."""
    target_codes = set(netcodes.values())
    doomed = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_TRACK" and item.GetNetCode() in target_codes
    ]
    for item in doomed:
        board.Delete(item)
    del doomed, item


def add_polyline(
    board: pcbnew.BOARD,
    netcode: int,
    width_mm: float,
    points_mm: list[tuple[float, float]],
) -> None:
    points = [pcbnew.VECTOR2I_MM(*point) for point in points_mm]
    for start, end in zip(points, points[1:], strict=False):
        add_track(board, netcode, pcbnew.In2_Cu, width_mm, start, end)


def add_supply_buses(board: pcbnew.BOARD, netcodes: dict[str, int]) -> None:
    """Build three spatially disjoint, reviewable In2 power trees."""
    code = netcodes["/3V3"]
    # J3 input fans left and under the FPC field at y=14.5.  The lower branch
    # stays above the EPD bus and exits R8 to the left of its /V_B dog-bone.
    add_polyline(
        board, code, 0.60, [(11.5, 1.8), (11.5, 8.0), (3.3, 10.0), (3.3, 14.5)]
    )
    add_polyline(board, code, 0.60, [(3.3, 14.5), (41.5, 14.5), (41.5, 19.325)])
    add_polyline(board, code, 0.60, [(41.5, 19.325), (44.0, 19.325)])
    add_polyline(
        board, code, 0.60, [(3.3, 14.5), (1.4, 19.0), (1.4, 40.5), (7.5, 40.5)]
    )
    add_polyline(board, code, 0.50, [(3.675, 42.5), (3.675, 40.5)])
    add_polyline(board, code, 0.60, [(8.675, 45.5), (7.5, 44.3), (7.5, 40.5)])
    add_polyline(board, code, 0.60, [(3.0, 48.0), (2.0, 48.0), (2.0, 40.5)])

    code = netcodes["/EPD_3V3"]
    # Keep the rail below the 3V3/V_B split at R4/R8, with vertical branches
    # to the three right-hand decoupling/load pads.
    add_polyline(board, code, 0.60, [(4.325, 43.0), (4.325, 46.5), (26.225, 46.5)])
    add_polyline(board, code, 0.60, [(16.675, 44.0), (16.675, 46.5)])
    add_polyline(board, code, 0.60, [(20.675, 44.0), (20.675, 46.5)])
    add_polyline(board, code, 0.60, [(26.225, 43.0), (26.225, 46.5)])

    code = netcodes["/V_B"]
    # The R8/C23 branch exits right of the 3V3 split, crosses left at y=39,
    # and passes the socket row in the clear corridor at x=2.6.  The upper
    # converter branch follows the B0-proven route with an In2 via detour.
    add_polyline(board, code, 0.80, [(8.825, 43.0), (11.0, 41.5)])
    add_polyline(
        board,
        code,
        0.80,
        [
            (9.525, 44.0),
            (11.0, 41.5),
            (11.0, 39.0),
            (2.6, 39.0),
            (2.6, 25.5),
            (8.475, 27.5),
        ],
    )
    add_polyline(board, code, 0.80, [(5.5, 29.225), (8.475, 27.5)])
    add_polyline(
        board,
        code,
        0.80,
        [
            (8.475, 27.5),
            (12.2761, 23.1756),
            (19.9561, 23.1756),
            (20.4003, 23.6198),
            (21.5, 24.25),
            (24.5, 24.25),
            (29.4788, 23.6198),
            (34.775, 28.2),
        ],
    )
    add_polyline(board, code, 0.80, [(34.775, 28.2), (37.8625, 28.45)])


def replace_supply_vias_and_add_dogbones(
    board: pcbnew.BOARD, netcodes: dict[str, int]
) -> dict[str, int]:
    target_codes = set(netcodes.values())
    doomed = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_VIA" and item.GetNetCode() in target_codes
    ]
    for item in doomed:
        board.Delete(item)
    del doomed, item

    counts = {name: 0 for name in netcodes}
    seen: set[tuple[str, str]] = set()
    pad_centres: set[tuple[int, int]] = set()
    via_centres: set[tuple[int, int]] = set()
    for reference, pad_number, netname, pad in target_smd_pads(board, netcodes):
        key = (reference, pad_number)
        if key not in VIA_POSITIONS_MM:
            raise SystemExit(f"Missing proven dog-bone centre for {key}")
        seen.add(key)
        counts[netname] += 1
        origin = pcbnew.VECTOR2I(pad.GetPosition())
        destination = pcbnew.VECTOR2I_MM(*VIA_POSITIONS_MM[key])
        pad_centres.add((origin.x, origin.y))
        via_centres.add((destination.x, destination.y))

        outer_layer = (
            pcbnew.F_Cu if pad.GetLayerSet().Contains(pcbnew.F_Cu) else pcbnew.B_Cu
        )
        bus_width = TARGET_WIDTHS_MM[netname]
        outer_width = 0.40 if bus_width <= 0.60 else 0.50
        add_track(
            board, pad.GetNetCode(), outer_layer, outer_width, origin, destination
        )

        via = pcbnew.PCB_VIA(board)
        via.SetPosition(destination)
        via.SetNetCode(pad.GetNetCode())
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
        via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)

    if seen != set(VIA_POSITIONS_MM):
        raise SystemExit(f"Unused dog-bone centres: {set(VIA_POSITIONS_MM) - seen}")
    if pad_centres & via_centres:
        raise SystemExit("Via-in-pad centre remains")
    return counts


def rebuild_zones(board: pcbnew.BOARD, netcodes: dict[str, int]) -> None:
    """Remove B0's partial supply pour and add one full-outline In1 GND plane."""
    for zone in list(board.Zones()):
        if zone.GetIsRuleArea():
            # A two-layer source can otherwise retain only the active layers.
            zone.SetLayerSet(pcbnew.LSET.AllCuMask())
            continue
        if zone.GetNetCode() in netcodes.values() or zone.GetLayer() == pcbnew.In1_Cu:
            board.Remove(zone)

    gnd = board.GetNetcodeFromNetname("/GND")
    if gnd <= 0:
        raise SystemExit("Missing /GND net")
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetNetCode(gnd)
    zone.SetZoneName("IN1_SOLID_GND_PLANE")
    zone.SetLocalClearance(pcbnew.FromMM(0.20))
    zone.SetMinThickness(pcbnew.FromMM(0.20))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetThermalReliefGap(pcbnew.FromMM(0.25))
    zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.30))
    outline = zone.Outline()
    polygon = outline.NewOutline()
    for x, y in ((0.65, 0.65), (61.35, 0.65), (61.35, 57.35), (0.65, 57.35)):
        outline.Append(pcbnew.VECTOR2I_MM(x, y), polygon)
    board.Add(zone)


def add_ground_stitching_vias(board: pcbnew.BOARD) -> None:
    """Add the DRC-proven J3/FPC/decoupling return-via set."""
    gnd = board.GetNetcodeFromNetname("/GND")
    if gnd <= 0:
        raise SystemExit("Missing /GND net")
    for x_mm, y_mm in GND_STITCHING_VIAS_MM:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
        via.SetNetCode(gnd)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(pcbnew.FromMM(0.60))
        via.SetDrill(pcbnew.FromMM(0.30))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)


def audit_design(
    board: pcbnew.BOARD,
    netcodes: dict[str, int],
    expected_vias: dict[str, int],
) -> dict[str, object]:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit("B1 candidate is not four-layer")
    if not board.IsLayerEnabled(pcbnew.F_Paste) or not board.IsLayerEnabled(
        pcbnew.B_Paste
    ):
        raise SystemExit("B1 fabrication layer table must enable F.Paste/B.Paste")

    in1_tracks = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_TRACK" and item.GetLayer() == pcbnew.In1_Cu
    ]
    if in1_tracks:
        raise SystemExit(f"In1 is not plane-only: {len(in1_tracks)} tracks remain")

    in1_zones = [
        zone
        for zone in board.Zones()
        if not zone.GetIsRuleArea() and zone.GetLayer() == pcbnew.In1_Cu
    ]
    if len(in1_zones) != 1 or in1_zones[0].GetNetname() != "/GND":
        raise SystemExit("In1 must contain exactly one /GND zone")
    if in1_zones[0].GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL:
        raise SystemExit("In1 /GND plane must use solid pad connections")
    filled = in1_zones[0].GetFilledPolysList(pcbnew.In1_Cu)
    if filled.OutlineCount() != 1:
        raise SystemExit("In1 /GND fill must be one continuous outline")
    filled_area_mm2 = filled.COutline(0).Area() / pcbnew.FromMM(1.0) ** 2
    if filled_area_mm2 < 3_000:
        raise SystemExit("In1 /GND filled outline is unexpectedly small")

    all_vias = [item for item in board.GetTracks() if type(item).__name__ == "PCB_VIA"]
    if any(item.GetViaType() != pcbnew.VIATYPE_THROUGH for item in all_vias):
        raise SystemExit("A blind, buried, or microvia remains on B1")
    gnd_code = board.GetNetcodeFromNetname("/GND")
    stitching_vias = []
    for x_mm, y_mm in GND_STITCHING_VIAS_MM:
        expected = pcbnew.VECTOR2I_MM(x_mm, y_mm)
        matches = [
            item
            for item in all_vias
            if item.GetNetCode() == gnd_code
            and item.GetPosition().x == expected.x
            and item.GetPosition().y == expected.y
        ]
        if len(matches) != 1:
            raise SystemExit(f"Missing unique GND stitching via at {(x_mm, y_mm)}")
        via = matches[0]
        if (
            pcbnew.ToMM(via.GetWidth(pcbnew.F_Cu)) < VIA_DIAMETER_MM
            or pcbnew.ToMM(via.GetDrill()) < VIA_DRILL_MM
        ):
            raise SystemExit(f"Undersized GND stitching via at {(x_mm, y_mm)}")
        stitching_vias.append({"x_mm": x_mm, "y_mm": y_mm})

    antenna = [
        zone
        for zone in board.Zones()
        if zone.GetIsRuleArea() and zone.GetZoneName() == "DEVKITC_ANTENNA_KEEP_OUT"
    ]
    if len(antenna) != 1:
        raise SystemExit("Exactly one antenna keepout is required")
    if not all(
        antenna[0].GetLayerSet().Contains(layer)
        for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    ):
        raise SystemExit("Antenna keepout does not cover all four copper layers")

    supply_results: dict[str, object] = {}
    for netname, netcode in netcodes.items():
        tracks = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_TRACK" and item.GetNetCode() == netcode
        ]
        inner = [item for item in tracks if item.GetLayer() == pcbnew.In2_Cu]
        other = [item for item in tracks if item.GetLayer() != pcbnew.In2_Cu]
        vias = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_VIA" and item.GetNetCode() == netcode
        ]
        allowed_minimum = 0.50 if netname == "/3V3" else TARGET_WIDTHS_MM[netname]
        if (
            not inner
            or min(pcbnew.ToMM(item.GetWidth()) for item in inner) < allowed_minimum
        ):
            raise SystemExit(f"{netname}: In2 bus is below its width contract")
        if any(item.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu) for item in other):
            raise SystemExit(f"{netname}: a dog-bone escaped onto an invalid layer")
        if len(vias) != expected_vias[netname]:
            raise SystemExit(f"{netname}: unexpected ordinary-via count")
        if any(item.GetViaType() != pcbnew.VIATYPE_THROUGH for item in vias):
            raise SystemExit(f"{netname}: blind/buried via remains")
        supply_results[netname] = {
            "in2_tracks": len(inner),
            "minimum_in2_width_mm": min(pcbnew.ToMM(item.GetWidth()) for item in inner),
            "outer_dogbones": len(other),
            "ordinary_through_vias": len(vias),
        }

    return {
        "copper_layers": 4,
        "paste_layers_enabled": ["F.Paste", "B.Paste"],
        "layer_contract": {
            "F.Cu": "components, signal routing, local supply dog-bones",
            "In1.Cu": "full-outline /GND plane; zero tracks",
            "In2.Cu": "all three supply buses",
            "B.Cu": "signal routing and local supply dog-bones",
        },
        "in1_track_count": 0,
        "in1_zone": "IN1_SOLID_GND_PLANE",
        "in1_gnd_filled_outlines": 1,
        "in1_gnd_filled_area_mm2": filled_area_mm2,
        "in1_gnd_pad_connection": "solid",
        "antenna_keepout_all_four_copper_layers": True,
        "total_ordinary_through_vias": len(all_vias),
        "added_gnd_stitching_vias": stitching_vias,
        "via_diameter_mm": VIA_DIAMETER_MM,
        "via_drill_mm": VIA_DRILL_MM,
        "via_in_pad": False,
        "blind_or_buried_vias": 0,
        "supplies": supply_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    source = args.input.resolve()
    destination = args.output.resolve()
    audit_path = args.audit.resolve()
    if source == destination:
        raise SystemExit("Refusing to overwrite Rev B0")
    destination.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise SystemExit(f"Cannot load {source}")
    netcodes = {
        netname: board.GetNetcodeFromNetname(netname) for netname in TARGET_WIDTHS_MM
    }
    if any(code <= 0 for code in netcodes.values()):
        raise SystemExit(f"Missing target supply net: {netcodes}")

    board.GetDesignSettings().SetCopperLayerCount(4)
    # B0's generated layer table omitted paste layers even though its SMD pads
    # carry F.Paste apertures.  Enable both explicitly so the B1 fabrication
    # contract can export a real top stencil Gerber and can prove that the
    # bottom stencil is intentionally empty.
    enabled_layers = board.GetEnabledLayers()
    enabled_layers.AddLayer(pcbnew.F_Paste)
    enabled_layers.AddLayer(pcbnew.B_Paste)
    board.SetEnabledLayers(enabled_layers)
    remove_b0_supply_routing(board, netcodes)
    expected_vias = replace_supply_vias_and_add_dogbones(board, netcodes)
    add_supply_buses(board, netcodes)
    rebuild_zones(board, netcodes)
    add_ground_stitching_vias(board)
    title_block = board.GetTitleBlock()
    title_block.SetTitle("MF1750 + ESP32-S3-DevKitC compact carrier")
    title_block.SetRevision("B1-4L-ENG")
    for drawing in board.GetDrawings():
        if (
            type(drawing).__name__ == "PCB_TEXT"
            and drawing.GetText() == "MF1750 COMPACT B0"
        ):
            drawing.SetText("MF1750 COMPACT B1 4L")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    result = audit_design(board, netcodes, expected_vias)
    result["board"] = str(destination)
    result["source_b0"] = str(source)
    result["source_b0_sha256"] = sha256(source)
    pcbnew.SaveBoard(str(destination), board)
    result["board_sha256"] = sha256(destination)

    source_project = B0_DIR / "mf1750_devkitc_compact.kicad_pro"
    project = destination.with_suffix(".kicad_pro")
    if source_project.exists():
        shutil.copyfile(source_project, project)
        project_data = json.loads(project.read_text(encoding="utf-8"))
        project_data.setdefault("meta", {})["filename"] = project.name
        project.write_text(
            json.dumps(project_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    source_schematic = B0_DIR / "mf1750_devkitc_compact.kicad_sch"
    if source_schematic.exists():
        schematic = destination.with_suffix(".kicad_sch")
        shutil.copyfile(source_schematic, schematic)
        schematic_text = schematic.read_text(encoding="utf-8")
        marker = "MF-1750 DevKitC Compact Carrier Rev B0"
        if schematic_text.count(marker) != 1:
            raise SystemExit("Unexpected B0 schematic title marker count")
        schematic.write_text(
            schematic_text.replace(marker, "MF-1750 DevKitC Compact Carrier Rev B1 4L"),
            encoding="utf-8",
        )
    for filename in ("fp-lib-table", "sym-lib-table", "mf1750_local.kicad_sym"):
        source_file = B0_DIR / filename
        if source_file.exists():
            shutil.copyfile(source_file, destination.parent / filename)
    source_pretty = B0_DIR / "MF1750_Compact.pretty"
    if source_pretty.exists():
        shutil.copytree(
            source_pretty,
            destination.parent / source_pretty.name,
            dirs_exist_ok=True,
        )
    audit_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
