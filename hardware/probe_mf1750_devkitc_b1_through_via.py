"""Build a non-production four-layer, through-via Rev B1 feasibility probe.

The released compact Rev B0 board is read-only input.  This script removes
only the three Rev B0 supply routes (/3V3, /EPD_3V3, and /V_B) from a loaded
copy, rebuilds them as wide In2.Cu trunks with ordinary F.Cu-to-B.Cu plated
through vias, and adds an uninterrupted In1.Cu GND reference plane.

The output proves KiCad connectivity and geometric/DRC feasibility only.  It
does not qualify a fabricator stack-up, current capacity, high-voltage spacing,
thermal performance, via-in-pad processing, or the unknown panel electrical
limits.  The default output is in the system temporary directory, so running
the probe cannot overwrite Rev B0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
B0_DIR = ROOT / "hardware" / "mf1750_devkitc_compact"
DEFAULT_INPUT = B0_DIR / "mf1750_devkitc_compact.kicad_pcb"
DEFAULT_OUTPUT = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", ".")))
    / "mf1750_devkitc_b1_through_via_probe.kicad_pcb"
)

SUPPLY_NAMES = ("/3V3", "/EPD_3V3", "/V_B")
VIA_DIAMETER_MM = 0.65
VIA_DRILL_MM = 0.30


def vector(point: tuple[float, float]) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(*point)


def add_track(
    board: pcbnew.BOARD,
    netcode: int,
    layer: int,
    width_mm: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> pcbnew.PCB_TRACK:
    track = pcbnew.PCB_TRACK(board)
    track.SetNetCode(netcode)
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width_mm))
    track.SetStart(vector(start))
    track.SetEnd(vector(end))
    board.Add(track)
    return track


def add_polyline(
    board: pcbnew.BOARD,
    netcode: int,
    layer: int,
    width_mm: float,
    points: tuple[tuple[float, float], ...],
) -> None:
    for start, end in zip(points, points[1:]):
        add_track(board, netcode, layer, width_mm, start, end)


def add_through_via(
    board: pcbnew.BOARD, netcode: int, point: tuple[float, float]
) -> pcbnew.PCB_VIA:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vector(point))
    via.SetNetCode(netcode)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
    via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)
    return via


def add_zone(
    board: pcbnew.BOARD, netcode: int, layer: int, name: str
) -> pcbnew.ZONE:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNetCode(netcode)
    zone.SetZoneName(name)
    zone.SetLocalClearance(pcbnew.FromMM(0.20))
    zone.SetMinThickness(pcbnew.FromMM(0.20))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetThermalReliefGap(pcbnew.FromMM(0.25))
    zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.30))
    outline = zone.Outline()
    polygon = outline.NewOutline()
    for point in ((0.65, 0.65), (61.35, 0.65), (61.35, 57.35), (0.65, 57.35)):
        outline.Append(vector(point), polygon)
    board.Add(zone)
    return zone


def configure_four_layers(board: pcbnew.BOARD) -> None:
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
    all_copper = pcbnew.LSET()
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        all_copper.AddLayer(layer)
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            # Rule areas have no filled polygons to migrate.  KiCad 10's
            # SetLayerSetAndRemoveUnusedFills asserts when newly enabled inner
            # layers do not yet own a fill cache, so use the plain layer-set
            # setter here.
            zone.SetLayerSet(all_copper)


def remove_all_copper_zones(board: pcbnew.BOARD) -> None:
    """Discard copied B0 fills; B1 planes are rebuilt after route validation."""
    doomed = [zone for zone in board.Zones() if not zone.GetIsRuleArea()]
    for zone in doomed:
        board.Delete(zone)
    del zone, doomed


def remove_b0_supply_copper(
    board: pcbnew.BOARD, netcodes: dict[str, int]
) -> None:
    target_codes = set(netcodes.values())
    doomed_tracks = [
        item for item in board.GetTracks() if item.GetNetCode() in target_codes
    ]
    for item in doomed_tracks:
        board.Delete(item)
    del item, doomed_tracks
    doomed_zones = [
        zone
        for zone in board.Zones()
        if not zone.GetIsRuleArea() and zone.GetNetCode() in target_codes
    ]
    for zone in doomed_zones:
        board.Delete(zone)
    del doomed_zones


def route_3v3(board: pcbnew.BOARD, netcode: int) -> list[tuple[float, float]]:
    layer = pcbnew.In2_Cu
    # Load-bearing J3-to-R4/R8 trunk.  The left lane avoids the socket and all
    # pre-existing signal vias; the top branch supplies only R9/R10 pull-ups.
    add_polyline(
        board,
        netcode,
        layer,
        1.20,
        ((11.50, 1.80), (11.50, 14.50), (1.15, 18.50), (1.15, 42.50), (2.90, 43.00)),
    )
    add_polyline(
        board,
        netcode,
        layer,
        0.50,
        ((11.50, 14.50), (46.00, 14.50)),
    )
    add_track(board, netcode, layer, 0.50, (42.50, 14.50), (42.50, 20.05))
    add_track(board, netcode, layer, 0.50, (46.00, 14.50), (46.00, 20.05))
    add_polyline(
        board,
        netcode,
        layer,
        0.50,
        ((2.90, 43.00), (2.90, 44.80)),
    )

    vias = [
        (2.90, 44.80),
        (8.80, 44.80),
        (42.50, 20.05),
        (46.00, 20.05),
        (3.20, 48.00),
    ]
    for point in vias:
        add_through_via(board, netcode, point)

    # F.Cu dogbones to the fitted distribution links and pull-ups.
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (3.175, 44.00), (2.90, 44.80))
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (7.175, 44.00), (8.80, 44.80))
    add_polyline(board, netcode, layer, 1.20, ((2.90, 44.80), (8.80, 44.80)))
    add_track(board, netcode, pcbnew.F_Cu, 0.50, (42.50, 19.325), (42.50, 20.05))
    add_track(board, netcode, pcbnew.F_Cu, 0.50, (46.00, 19.325), (46.00, 20.05))
    # TP1 is a bottom-side measurement pad.
    add_track(board, netcode, pcbnew.B_Cu, 0.40, (3.20, 48.00), (4.00, 48.00))
    add_track(board, netcode, layer, 0.50, (2.90, 44.80), (3.20, 48.00))
    return vias


def route_epd_3v3(
    board: pcbnew.BOARD, netcode: int
) -> list[tuple[float, float]]:
    layer = pcbnew.In2_Cu
    vias = [(4.45, 44.80), (17.475, 43.20), (21.475, 43.20), (26.025, 43.20)]
    add_polyline(
        board,
        netcode,
        layer,
        1.00,
        ((4.45, 44.80), (4.45, 42.00), (26.025, 42.00), (26.025, 43.20)),
    )
    for point in vias[1:-1]:
        add_track(board, netcode, layer, 1.00, (point[0], 42.00), point)
    for point in vias:
        add_through_via(board, netcode, point)
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (4.825, 44.00), vias[0])
    for pad, point in zip(
        ((17.675, 44.00), (21.675, 44.00), (26.225, 44.00)),
        vias[1:],
        strict=True,
    ):
        add_track(board, netcode, pcbnew.F_Cu, 0.40, pad, point)
    return vias


def route_v_b(board: pcbnew.BOARD, netcode: int) -> list[tuple[float, float]]:
    layer = pcbnew.In2_Cu
    # Source cluster below R8/C23.
    source_vias = ((10.00, 43.20), (11.00, 43.20))
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (8.825, 44.00), source_vias[0])
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (11.525, 44.00), source_vias[1])

    # Left converter input cluster, joined locally on F.Cu.
    left_vias = ((5.30, 29.125),)
    add_track(board, netcode, pcbnew.F_Cu, 0.40, (3.50, 27.725), left_vias[0])
    for point in left_vias:
        add_track(board, netcode, pcbnew.F_Cu, 0.40, (3.50, 27.725), point)

    # Right converter input cluster, also joined locally on F.Cu.
    right_vias = ((35.575, 29.20),)
    for point in right_vias:
        add_track(board, netcode, pcbnew.F_Cu, 0.40, (34.775, 29.20), point)

    add_track(board, netcode, layer, 1.20, source_vias[0], source_vias[1])
    add_polyline(
        board,
        netcode,
        layer,
        1.20,
        (
            (10.50, 43.20),
            (10.50, 40.50),
            (3.00, 40.50),
            (3.00, 32.00),
            (5.30, 29.125),
            (10.60, 21.50),
            (29.50, 21.50),
            (35.575, 29.20),
        ),
    )
    vias = [*source_vias, *left_vias, *right_vias]
    for point in vias:
        add_through_via(board, netcode, point)
    return vias


def add_inner_ground_planes(board: pcbnew.BOARD, gnd_code: int) -> None:
    # In1 is intentionally a single-net reference plane.  In2 is filled with
    # GND only in the area left after the three wide power trunks are routed.
    add_zone(board, gnd_code, pcbnew.In1_Cu, "B1_GND_REFERENCE")
    add_zone(board, gnd_code, pcbnew.In2_Cu, "B1_GND_RETURN")


def audit(
    board: pcbnew.BOARD,
    netcodes: dict[str, int],
    expected_vias: dict[str, list[tuple[float, float]]],
    require_reference_plane: bool,
) -> dict[str, object]:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit(f"Expected four copper layers, got {board.GetCopperLayerCount()}")

    in1_non_ground = [
        item.GetNetname()
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_TRACK"
        and item.GetLayer() == pcbnew.In1_Cu
        and item.GetNetname() != "/GND"
    ]
    if in1_non_ground:
        raise SystemExit(f"In1 contains non-GND tracks: {sorted(set(in1_non_ground))}")

    target_codes = set(netcodes.values())
    target_vias = [
        item
        for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA) and item.GetNetCode() in target_codes
    ]
    if any(item.GetViaType() != pcbnew.VIATYPE_THROUGH for item in target_vias):
        raise SystemExit("A target supply contains a non-through via")

    for name, points in expected_vias.items():
        found = [item for item in target_vias if item.GetNetCode() == netcodes[name]]
        if len(found) != len(points):
            raise SystemExit(f"{name}: expected {len(points)} through vias, found {len(found)}")

    for switch_name in ("/SW_H", "/SW_C"):
        code = board.GetNetcodeFromNetname(switch_name)
        invalid = [
            item
            for item in board.GetTracks()
            if item.GetNetCode() == code
            and (
                isinstance(item, pcbnew.PCB_VIA)
                or item.GetLayer() != pcbnew.F_Cu
            )
        ]
        if invalid:
            raise SystemExit(f"{switch_name} left F.Cu or contains a via")

    reference = [
        zone
        for zone in board.Zones()
        if zone.GetZoneName() == "B1_GND_REFERENCE"
        and zone.GetLayer() == pcbnew.In1_Cu
        and zone.GetNetname() == "/GND"
    ]
    if require_reference_plane and len(reference) != 1:
        raise SystemExit("Missing the single In1 /GND reference plane")

    return {
        "copper_layers": board.GetCopperLayerCount(),
        "in1_non_ground_track_count": len(in1_non_ground),
        "ordinary_through_vias": {
            name: len(points) for name, points in expected_vias.items()
        },
        "switch_nodes_f_cu_only": True,
        "in1_ground_plane_present": len(reference) == 1,
    }


def copy_project_settings(destination: Path) -> None:
    source = B0_DIR / "mf1750_devkitc_compact.kicad_pro"
    target = destination.with_suffix(".kicad_pro")
    if source.exists() and source.resolve() != target.resolve():
        shutil.copyfile(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--track-via-only",
        action="store_true",
        help="omit all copper zones to isolate track/via DRC feasibility",
    )
    args = parser.parse_args()
    source = args.input.resolve()
    destination = args.output.resolve()
    if source == destination:
        raise SystemExit("Refusing to overwrite the Rev B0 source board")
    destination.parent.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise SystemExit(f"Cannot load {source}")
    netcodes = {name: board.GetNetcodeFromNetname(name) for name in SUPPLY_NAMES}
    if any(code <= 0 for code in netcodes.values()):
        raise SystemExit(f"Missing target net: {netcodes}")
    gnd_code = board.GetNetcodeFromNetname("/GND")
    if gnd_code <= 0:
        raise SystemExit("Missing /GND net")

    configure_four_layers(board)
    remove_all_copper_zones(board)
    remove_b0_supply_copper(board, netcodes)
    expected_vias = {
        "/3V3": route_3v3(board, netcodes["/3V3"]),
        "/EPD_3V3": route_epd_3v3(board, netcodes["/EPD_3V3"]),
        "/V_B": route_v_b(board, netcodes["/V_B"]),
    }
    if not args.track_via_only:
        add_inner_ground_planes(board, gnd_code)
    result = audit(
        board,
        netcodes,
        expected_vias,
        require_reference_plane=not args.track_via_only,
    )
    pcbnew.SaveBoard(str(destination), board)
    copy_project_settings(destination)
    result["board"] = str(destination)
    result["source_b0_unchanged"] = str(source)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
