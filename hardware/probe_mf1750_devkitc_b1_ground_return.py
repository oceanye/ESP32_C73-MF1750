"""Probe Rev B1 ground-return stitching and switch-node plane voids.

The canonical Rev B1 board is read-only input.  This tool writes a disposable
probe board, adds conventional 0.60/0.30 mm through GND stitching vias, and can
add copper-pour-only rule areas beneath the two switch nodes on In1/In2.

KiCad's bundled Python is required::

    & 'C:\\Program Files\\KiCad\\10.0\\bin\\python.exe' `
      hardware\\probe_mf1750_devkitc_b1_ground_return.py --inspect
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT
    / "hardware"
    / "mf1750_devkitc_b1_single_power_layer"
    / "mf1750_devkitc_b1_single_power_layer.kicad_pcb"
)
DEFAULT_OUTPUT = (
    ROOT
    / "hardware"
    / "mf1750_devkitc_b1_ground_return_probes"
    / "ground_return_probe.kicad_pcb"
)

# Initial candidates are intentionally outside component courtyards wherever
# practical.  They are screened by strict DRC before promotion.
STITCHING_CANDIDATES_MM: dict[str, tuple[float, float]] = {
    "J3_GND": (8.20, 1.80),
    "FPC_STITCH_LEFT": (26.00, 10.00),
    "FPC_STITCH_MID": (30.00, 11.00),
    "FPC_STITCH_RIGHT": (39.00, 11.00),
    # C0 already has a 0.60/0.30 GND via at (4.1781, 30.1458) in Rev B0/B1;
    # do not add a duplicate there.
    "C2_GND": (23.20, 29.00),
    "C6_GND": (58.20, 27.525),
    "C22_GND": (33.225, 30.40),
    "C23_GND": (15.40, 44.00),
}

# Conservative rectangles around only the switching copper itself.  These
# rule areas prohibit pours on In1/In2 but do not prohibit tracks or vias.
# Coordinates are refined after inspecting the actual SW_H/SW_C geometry.
SWITCH_VOID_RECTS_MM: dict[str, tuple[float, float, float, float]] = {
    "SW_H_PLANE_VOID": (10.75, 23.40, 16.95, 30.10),
    "SW_C_PLANE_VOID": (39.20, 25.50, 52.40, 30.30),
}


def point_mm(position: pcbnew.VECTOR2I) -> tuple[float, float]:
    return (round(pcbnew.ToMM(position.x), 4), round(pcbnew.ToMM(position.y), 4))


def add_gnd_via(board: pcbnew.BOARD, x_mm: float, y_mm: float) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
    via.SetNetCode(board.GetNetcodeFromNetname("/GND"))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(pcbnew.FromMM(0.60))
    via.SetDrill(pcbnew.FromMM(0.30))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)


def add_plane_void(
    board: pcbnew.BOARD,
    name: str,
    bounds_mm: tuple[float, float, float, float],
) -> None:
    x1, y1, x2, y2 = bounds_mm
    area = pcbnew.ZONE(board)
    area.SetIsRuleArea(True)
    area.SetZoneName(name)
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.In1_Cu)
    layers.AddLayer(pcbnew.In2_Cu)
    area.SetLayerSet(layers)
    area.SetDoNotAllowCopperPour(True)
    area.SetDoNotAllowTracks(False)
    area.SetDoNotAllowVias(False)
    area.SetDoNotAllowPads(False)
    outline = area.Outline()
    polygon = outline.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        outline.Append(pcbnew.VECTOR2I_MM(x, y), polygon)
    board.Add(area)


def describe(board: pcbnew.BOARD) -> dict[str, object]:
    refs = {"J3", "C0", "C2", "C6", "C22", "C23", "L1", "L2", "U1", "U2"}
    footprints: dict[str, object] = {}
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        if reference not in refs and not reference.startswith("J"):
            continue
        pads = []
        for pad in footprint.Pads():
            pads.append(
                {
                    "number": pad.GetNumber(),
                    "net": pad.GetNetname(),
                    "position_mm": point_mm(pad.GetPosition()),
                    "size_mm": point_mm(pad.GetSize()),
                    "layer": board.GetLayerName(pad.GetLayer()),
                }
            )
        footprints[reference] = {
            "position_mm": point_mm(footprint.GetPosition()),
            "pads": pads,
        }

    switch_tracks: dict[str, list[object]] = {"/SW_H": [], "/SW_C": []}
    for item in board.GetTracks():
        if type(item).__name__ != "PCB_TRACK" or item.GetNetname() not in switch_tracks:
            continue
        switch_tracks[item.GetNetname()].append(
            {
                "start_mm": point_mm(item.GetStart()),
                "end_mm": point_mm(item.GetEnd()),
                "width_mm": round(pcbnew.ToMM(item.GetWidth()), 3),
                "layer": board.GetLayerName(item.GetLayer()),
            }
        )

    zones = []
    for zone in board.Zones():
        layers = [
            board.GetLayerName(layer)
            for layer in range(pcbnew.PCB_LAYER_ID_COUNT)
            if zone.GetLayerSet().Contains(layer)
        ]
        filled = {}
        for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            if not zone.GetLayerSet().Contains(layer):
                continue
            polys = zone.GetFilledPolysList(layer)
            filled[board.GetLayerName(layer)] = {
                "outline_count": polys.OutlineCount(),
                "outlines": [
                    {
                        "points": polys.COutline(index).PointCount(),
                        "bbox_mm": tuple(
                            round(pcbnew.ToMM(value), 4)
                            for value in (
                                polys.COutline(index).BBox().GetX(),
                                polys.COutline(index).BBox().GetY(),
                                polys.COutline(index).BBox().GetWidth(),
                                polys.COutline(index).BBox().GetHeight(),
                            )
                        ),
                    }
                    for index in range(polys.OutlineCount())
                ],
            }
        zones.append(
            {
                "name": zone.GetZoneName(),
                "net": zone.GetNetname(),
                "rule_area": zone.GetIsRuleArea(),
                "layers": layers,
                "filled_outline_count": filled,
            }
        )

    switch_pads: dict[str, list[object]] = {"/SW_H": [], "/SW_C": []}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() not in switch_pads:
                continue
            switch_pads[pad.GetNetname()].append(
                {
                    "reference": footprint.GetReference(),
                    "number": pad.GetNumber(),
                    "position_mm": point_mm(pad.GetPosition()),
                    "size_mm": point_mm(pad.GetSize()),
                    "layer": board.GetLayerName(pad.GetLayer()),
                }
            )

    return {
        "board": str(board.GetFileName()),
        "footprints": footprints,
        "switch_tracks": switch_tracks,
        "switch_pads": switch_pads,
        "zones": zones,
        "stitching_candidates_mm": STITCHING_CANDIDATES_MM,
        "switch_void_rects_mm": SWITCH_VOID_RECTS_MM,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--no-vias", action="store_true")
    parser.add_argument(
        "--vias",
        help="comma-separated candidate labels; defaults to all candidates",
    )
    parser.add_argument("--voids", action="store_true")
    parser.add_argument(
        "--solid-in1",
        action="store_true",
        help="use solid pad connections on the inner GND plane",
    )
    args = parser.parse_args()

    source = args.input.resolve()
    destination = args.output.resolve()
    if source == destination:
        raise SystemExit("Probe refuses to overwrite its input board")
    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise SystemExit(f"Cannot load {source}")
    if args.inspect:
        print(json.dumps(describe(board), indent=2, ensure_ascii=False, sort_keys=True))
        return

    if args.solid_in1:
        plane = [
            zone
            for zone in board.Zones()
            if zone.GetZoneName() == "IN1_SOLID_GND_PLANE"
        ]
        if len(plane) != 1:
            raise SystemExit("Expected exactly one IN1_SOLID_GND_PLANE")
        plane[0].SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)

    selected = list(STITCHING_CANDIDATES_MM)
    if args.vias:
        selected = [label.strip() for label in args.vias.split(",") if label.strip()]
        unknown = set(selected) - set(STITCHING_CANDIDATES_MM)
        if unknown:
            raise SystemExit(f"Unknown via candidate labels: {sorted(unknown)}")
    if not args.no_vias:
        for label in selected:
            x_mm, y_mm = STITCHING_CANDIDATES_MM[label]
            add_gnd_via(board, x_mm, y_mm)
    if args.voids:
        for name, bounds in SWITCH_VOID_RECTS_MM.items():
            add_plane_void(board, name, bounds)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    destination.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(destination), board)
    print(json.dumps(describe(board), indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
