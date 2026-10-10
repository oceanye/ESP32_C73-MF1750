"""Prepare the independent DevKitC compact carrier for Freerouting.

This deliberately imports the proven Rev A1 routing primitives without
changing the released Rev A1 sources or outputs.  The 0.5 mm FPC is escaped to
a 1.0 mm via row first; Freerouting then handles the compact two-layer field.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_compact"
PROJECT = "mf1750_devkitc_compact"

sys.path.insert(0, str(HARDWARE))
import generate_mf1750_devkitc_compact as design  # noqa: E402
import route_mf1750_production_v1 as route  # noqa: E402


def configure_modules() -> None:
    design.patch_base_globals()
    route.OUT = OUT
    route.PROJECT = PROJECT
    route.BOARD_PATH = OUT / "unrouted_source.kicad_pcb"
    route.SCH_PATH = OUT / f"{PROJECT}.kicad_sch"
    route.design = design
    route.BOARD_W_MM = design.BOARD_W_MM
    route.BOARD_H_MM = design.BOARD_H_MM
    route.FPC_CENTER_X_MM = design.FPC_X_MM
    route.FPC_FANOUT_Y_MM = 20.25
    route.FPC_GENERAL_MIN_Y_MM = 20.25
    route.FPC_HIGH_PIN_ROUTE_Y_MM = 20.25
    # Pins 37..50 terminate in the nearby right-side capacitor bank; letting
    # the global router escape these avoids an unnecessary fixed via fence.
    route.FPC_UNROUTED_HIGH_PINS = {37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 49, 50}
    route.FPC_EARLY_VIA_POINTS = {}


def configure_netclasses(board: route.pcbnew.BOARD) -> None:
    settings = board.GetDesignSettings().m_NetSettings
    default = settings.GetDefaultNetclass()
    # 0.20/0.20 mm is required to escape the native 0.5 mm FPC pitch without
    # colliding with the deliberately nearby panel-support capacitors.
    default.SetTrackWidth(route.pcbnew.FromMM(0.20))
    default.SetClearance(route.pcbnew.FromMM(0.20))
    default.SetViaDiameter(route.pcbnew.FromMM(0.60))
    default.SetViaDrill(route.pcbnew.FromMM(0.30))

    # Route every net at 0.20 mm first.  Assigning a wide class to an entire
    # cross-board power net prevents the dense FPC escape from converging.
    # The finalizer widens only the short switching-current segments next to
    # L1/Q1/D1 and Q2/L2/D4, then reruns DRC.
    settings.RecomputeEffectiveNetclasses()


def add_antenna_keepout(board: route.pcbnew.BOARD) -> None:
    """Reserve both copper layers below the overhanging WROOM antenna end."""
    keepout = route.pcbnew.ZONE(board)
    keepout.SetIsRuleArea(True)
    keepout.SetLayerSet(route.pcbnew.LSET.AllCuMask())
    keepout.SetDoNotAllowTracks(True)
    keepout.SetDoNotAllowVias(True)
    keepout.SetDoNotAllowZoneFills(True)
    keepout.SetDoNotAllowPads(False)
    keepout.SetDoNotAllowFootprints(False)
    keepout.SetZoneName("DEVKITC_ANTENNA_KEEP_OUT")
    outline = keepout.Outline()
    polygon = outline.NewOutline()
    # The socket's right-hand row is centred at x=58.84 mm and its rotated
    # oval pads extend to x=59.84 mm.  Start at 60.1 mm so pad 23 (GND) has a
    # legal escape while the carrier area below the overhanging antenna stays
    # free of tracks, vias, and pours.
    # The rotated module/antenna envelope reaches y=31.64..57.50 mm.  Reserve
    # the full carrier overlap (to the bottom-edge keepout at y=57.35), not
    # merely the socket-pad span.
    for x, y in ((60.1, 31.6), (62.0, 31.6), (62.0, 57.35), (60.1, 57.35)):
        outline.Append(route.pcbnew.VECTOR2I_MM(x, y), polygon)
    board.Add(keepout)


def add_edge_copper_keepouts(board: route.pcbnew.BOARD) -> None:
    """Keep routed copper far enough from the milled 62 x 58 mm outline."""
    rectangles = {
        "EDGE_TOP_KEEP_OUT": ((0.0, 0.0), (62.0, 0.65)),
        "EDGE_BOTTOM_KEEP_OUT": ((0.0, 57.35), (62.0, 58.0)),
        "EDGE_LEFT_KEEP_OUT": ((0.0, 0.0), (0.65, 58.0)),
        "EDGE_RIGHT_KEEP_OUT": ((61.35, 0.0), (62.0, 58.0)),
    }
    for name, ((x0, y0), (x1, y1)) in rectangles.items():
        keepout = route.pcbnew.ZONE(board)
        keepout.SetIsRuleArea(True)
        keepout.SetLayerSet(route.pcbnew.LSET.AllCuMask())
        keepout.SetDoNotAllowTracks(True)
        keepout.SetDoNotAllowVias(True)
        keepout.SetDoNotAllowZoneFills(True)
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)
        keepout.SetZoneName(name)
        outline = keepout.Outline()
        polygon = outline.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            outline.Append(route.pcbnew.VECTOR2I_MM(x, y), polygon)
        board.Add(keepout)


def protect_switching_loops(board: route.pcbnew.BOARD) -> None:
    """Pre-route only local high-current paths before global optimization."""
    route.WIDE_NETS["RESEH"] = 0.40
    router = route.GridRouter(board)
    # Local endpoint pairs; do not reuse Rev A1's board-spanning V_B branch,
    # whose fixed bends cross the compact socket row.
    pairs = (
        ("V_B", "C0", "1", "L1", "1"),
        ("RESEH", "Q1", "2", "R1", "1"),
        ("VPH", "D1", "1", "C2", "1"),
        ("NEG_PUMP_H", "C4", "2", "D2", "2"),
        ("PREVGL", "D3", "2", "C5", "1"),
        ("RESEC", "L2", "2", "R3", "1"),
    )
    for netname, a_ref, a_number, b_ref, b_number in pairs:
        a = board.FindFootprintByReference(a_ref).FindPadByNumber(a_number)
        b = board.FindFootprintByReference(b_ref).FindPadByNumber(b_number)
        start = next(iter(router._pad_nodes(a)))
        end = next(iter(router._pad_nodes(b)))
        bend = route.Node(end.x, start.y, 0)
        if not router.commit_direct(start, bend, a.GetNetCode(), netname):
            raise SystemExit(f"{netname} protected first segment failed")
        if not router.commit_direct(bend, end, a.GetNetCode(), netname):
            raise SystemExit(f"{netname} protected second segment failed")
    # VPC endpoints face one another but C6 is rotated; a short lower lane
    # clears both the diode and capacitor courtyard/pads.
    d4 = board.FindFootprintByReference("D4").FindPadByNumber("2")
    c6 = board.FindFootprintByReference("C6").FindPadByNumber("1")
    start = next(iter(router._pad_nodes(d4)))
    end = next(iter(router._pad_nodes(c6)))
    lane = route.Node(start.x, route.mm_to_grid(30.75), 0)
    lane_end = route.Node(end.x, lane.y, 0)
    for a, b in ((start, lane), (lane, lane_end), (lane_end, end)):
        if not router.commit_direct(a, b, d4.GetNetCode(), "VPC"):
            raise SystemExit("VPC protected branch failed")
    # The longer SW_H-to-C4 branch remains global.  Freerouting 2.2.4 has a
    # known recursive trace-combine failure on this pre-routed multi-bend path;
    # the short L1/Q1/D1 core is already protected by placement.


def coalesce_collinear_tracks(board: route.pcbnew.BOARD) -> None:
    """Merge touching collinear seed tracks before Specctra export.

    Freerouting 2.2.4 recursively combines chains of coincident track ends and
    overflows its Java stack on generated multi-segment direct routes.  KiCad
    does not require those artificial segment boundaries, so remove them.
    """
    while True:
        tracks = [
            item
            for item in board.GetTracks()
            if isinstance(item, route.pcbnew.PCB_TRACK)
        ]
        merged = False
        for index, first in enumerate(tracks):
            for second in tracks[index + 1 :]:
                if (
                    first.GetNetCode() != second.GetNetCode()
                    or first.GetLayer() != second.GetLayer()
                    or first.GetWidth() != second.GetWidth()
                ):
                    continue
                common = None
                for point in (first.GetStart(), first.GetEnd()):
                    if point == second.GetStart() or point == second.GetEnd():
                        common = point
                        break
                if common is None:
                    continue
                a = first.GetEnd() if first.GetStart() == common else first.GetStart()
                b = (
                    second.GetEnd()
                    if second.GetStart() == common
                    else second.GetStart()
                )
                cross = (common.x - a.x) * (b.y - common.y) - (common.y - a.y) * (
                    b.x - common.x
                )
                if cross:
                    continue
                first.SetStart(a)
                first.SetEnd(b)
                board.Remove(second)
                merged = True
                break
            if merged:
                break
        if not merged:
            return


def main() -> None:
    configure_modules()
    board = route.pcbnew.LoadBoard(str(route.BOARD_PATH))
    if board is None:
        raise SystemExit(f"Cannot load {route.BOARD_PATH}")
    for item in list(board.GetTracks()):
        board.Remove(item)
    for zone in list(board.Zones()):
        if not zone.GetIsRuleArea():
            board.Remove(zone)
    if not any(zone.GetIsRuleArea() for zone in board.Zones()):
        add_antenna_keepout(board)
        add_edge_copper_keepouts(board)

    route.link_footprints_to_schematic(board)
    route.verify_board_pin_nets(board)
    # Freerouting 2.2.4 repeatedly declares this three-terminal net complete
    # while omitting J1-40 from the SES.  Route the functional J1-40/R7 pair
    # here and restore TP7 after import; TP7's short local branch has a fixed,
    # DRC-checked path beside R7 and does not influence the global topology.
    tp7 = board.FindFootprintByReference("TP7").FindPadByNumber("1")
    if tp7 is None or tp7.GetNetname() != "/VDDIO":
        raise SystemExit("TP7 VDDIO identity mismatch")
    tp7.SetNetCode(0)
    # Freerouting 2.2.4 recursively overflows on long generated pre-routes.
    # Export a clean ratsnest; local power loops are protected by placement and
    # checked after session import.

    # Freerouting owns the FPC escape in this compact placement.  The Rev A1
    # fixed fanout extends through y=20.25 mm and would cross the deliberately
    # close panel-support capacitor bank in this stacked design.
    configure_netclasses(board)

    seed = OUT / "freerouting_seed.kicad_pcb"
    dsn = OUT / "freerouting_seed.dsn"
    route.pcbnew.SaveBoard(str(seed), board)
    if not route.pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("Specctra DSN export failed")
    print(dsn)


if __name__ == "__main__":
    main()
