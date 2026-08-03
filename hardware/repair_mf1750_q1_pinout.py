from __future__ import annotations

"""Apply the Rev A1 Q1/D2 electrical corrections and re-export production data.

The original Rev A prototype assigned Q1 pads as 1=S, 2=G, 3=D.  Vishay's
Si1308EDL is 1=G, 2=S, 3=D.  The original D2 polarity also opposed the A1
negative charge-pump reference.  This deterministic repair preserves the
routed board, corrects those pad nets/orientations, replaces only the short
local Q1 routes, and then runs the normal ERC/DRC/parity/export pipeline.
"""

from pathlib import Path

import generate_mf1750_production_v1 as design
import route_mf1750_production_v1 as route


def mm(x: float, y: float) -> route.pcbnew.VECTOR2I:
    return route.pcbnew.VECTOR2I(route.pcbnew.FromMM(x), route.pcbnew.FromMM(y))


def add_track(
    board: route.pcbnew.BOARD,
    net_code: int,
    start: route.pcbnew.VECTOR2I,
    end: route.pcbnew.VECTOR2I,
    width_mm: float,
) -> None:
    track = route.pcbnew.PCB_TRACK(board)
    track.SetStart(start)
    track.SetEnd(end)
    track.SetLayer(route.pcbnew.F_Cu)
    track.SetWidth(route.pcbnew.FromMM(width_mm))
    track.SetNetCode(net_code)
    board.Add(track)


def same_point(a: route.pcbnew.VECTOR2I, b: route.pcbnew.VECTOR2I) -> bool:
    return a.x == b.x and a.y == b.y


def segment_matches(
    track: route.pcbnew.PCB_TRACK,
    a: route.pcbnew.VECTOR2I,
    b: route.pcbnew.VECTOR2I,
) -> bool:
    return (
        same_point(track.GetStart(), a) and same_point(track.GetEnd(), b)
    ) or (
        same_point(track.GetStart(), b) and same_point(track.GetEnd(), a)
    )


def refresh_generated_schematic_files() -> None:
    design.patch_base_globals()
    design.FPC_LIB_DIR.mkdir(parents=True, exist_ok=True)
    (design.OUT / "mf1750_local.kicad_sym").write_text(
        design.base.make_local_symbol_lib(), encoding="utf-8"
    )
    (design.OUT / f"{design.PROJECT}.kicad_sch").write_text(
        design.make_schematic(), encoding="utf-8"
    )
    (design.OUT / "bom_reference.csv").write_text(
        design.make_reference_bom(), encoding="utf-8"
    )
    (design.OUT / "mf1750_fpc_pinmap.csv").write_text(
        design.base.make_pinmap(), encoding="utf-8"
    )
    (design.OUT / "README.md").write_text(design.make_readme(), encoding="utf-8")


def repair_board() -> None:
    board = route.pcbnew.LoadBoard(str(route.BOARD_PATH))
    if board is None:
        raise SystemExit(f"Cannot load {route.BOARD_PATH}")

    q1 = board.FindFootprintByReference("Q1")
    r1 = board.FindFootprintByReference("R1")
    if q1 is None or r1 is None:
        raise SystemExit("Q1 or R1 footprint missing")

    pad1 = q1.FindPadByNumber("1")
    pad2 = q1.FindPadByNumber("2")
    r1_pad1 = r1.FindPadByNumber("1")
    if pad1 is None or pad2 is None or r1_pad1 is None:
        raise SystemExit("Q1/R1 pad missing")

    gdrh = board.GetNetcodeFromNetname("/GDRH")
    reseh = board.GetNetcodeFromNetname("/RESEH")
    if gdrh <= 0 or reseh <= 0:
        raise SystemExit("GDRH or RESEH net missing")

    old_pad1 = pad1.GetPosition()
    old_pad2 = pad2.GetPosition()
    gdrh_join = mm(19.6717, 48.4092)
    reseh_via = mm(17.2155, 49.3875)

    # Remove the old local Q1 connections, plus Rev A1 connections on a rerun.
    candidates = (
        (gdrh, old_pad1, gdrh_join),
        (gdrh, old_pad2, gdrh_join),
        (reseh, reseh_via, old_pad1),
        (reseh, reseh_via, r1_pad1.GetPosition()),
        (reseh, old_pad1, r1_pad1.GetPosition()),
        (reseh, old_pad2, r1_pad1.GetPosition()),
    )
    for item in list(board.GetTracks()):
        if isinstance(item, route.pcbnew.PCB_VIA) or item.GetLayer() != route.pcbnew.F_Cu:
            continue
        for net_code, a, b in candidates:
            if item.GetNetCode() == net_code and segment_matches(item, a, b):
                board.Remove(item)
                break

    pad1.SetNetCode(gdrh)  # Si1308EDL pin 1 = Gate
    pad2.SetNetCode(reseh)  # Si1308EDL pin 2 = Source

    add_track(board, gdrh, pad1.GetPosition(), gdrh_join, 0.25)
    add_track(board, reseh, reseh_via, r1_pad1.GetPosition(), 0.50)
    add_track(board, reseh, pad2.GetPosition(), r1_pad1.GetPosition(), 0.50)

    # D2 is the clamp diode of the negative pump: anode=NEG_PUMP_H,
    # cathode=GND. Rotating the footprint preserves the existing copper while
    # placing the newly corrected pin 1/K on the old GND endpoint.
    d2 = board.FindFootprintByReference("D2")
    if d2 is None:
        raise SystemExit("D2 footprint missing")
    d2.SetOrientationDegrees(180.0)
    d2_pad1 = d2.FindPadByNumber("1")
    d2_pad2 = d2.FindPadByNumber("2")
    if d2_pad1 is None or d2_pad2 is None:
        raise SystemExit("D2 pad missing")
    gnd = board.GetNetcodeFromNetname("/GND")
    neg_pump = board.GetNetcodeFromNetname("/NEG_PUMP_H")
    d2_pad1.SetNetCode(gnd)
    d2_pad2.SetNetCode(neg_pump)

    for drawing in board.GetDrawings():
        if isinstance(drawing, route.pcbnew.PCB_TEXT) and drawing.GetText() == "MF1750 REV A":
            drawing.SetText("MF1750 REV A1")
    title = board.GetTitleBlock()
    title.SetRevision("A1")
    board.SetTitleBlock(title)

    route.pcbnew.SaveBoard(str(route.BOARD_PATH), board)


def main() -> None:
    refresh_generated_schematic_files()
    repair_board()
    board = route.pcbnew.LoadBoard(str(route.BOARD_PATH))
    if board is None:
        raise SystemExit("Cannot reload repaired board")
    route.verify_board_pin_nets(board)
    route.configure_drc_severities()
    route.export_manufacturing()
    print(route.PRODUCTION)


if __name__ == "__main__":
    main()
