from __future__ import annotations

"""Import the completed Freerouting session and build production outputs.

Run this with KiCad's bundled Python after ``prepare_mf1750_freerouting_seed.py``
and Freerouting have produced ``freerouting_result.ses``.
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_mf1750_production_v1 as route


def remove_redundant_single_layer_vias(board: route.pcbnew.BOARD) -> int:
    """Remove fanout vias which Freerouting legitimately bypassed on one layer."""
    tracks = list(board.GetTracks())
    removed = 0
    for item in tracks:
        if not isinstance(item, route.pcbnew.PCB_VIA):
            continue
        position = item.GetPosition()
        touched_layers: set[int] = set()
        for track in tracks:
            if isinstance(track, route.pcbnew.PCB_VIA) or track.GetNetCode() != item.GetNetCode():
                continue
            start = track.GetStart()
            end = track.GetEnd()
            if ((start.x == position.x and start.y == position.y)
                    or (end.x == position.x and end.y == position.y)):
                touched_layers.add(track.GetLayer())
        if len(touched_layers) <= 1:
            board.Remove(item)
            removed += 1
    return removed


def add_power_ground_stitching(board: route.pcbnew.BOARD) -> None:
    """Give both converter stages explicit low-impedance local plane access."""
    specs = (
        ("C0", "2", 5.225, 48.0),
        ("R1", "2", 17.0, 54.5),
        ("C2", "2", 33.0, 44.0),
        ("C22", "2", 40.0, 48.0),
        ("R3", "2", 58.0, 62.0),
        ("C6", "2", 68.0, 49.0),
    )
    gnd = board.GetNetcodeFromNetname("/GND")
    for ref, pin, x, y in specs:
        pad = board.FindFootprintByReference(ref).FindPadByNumber(pin)
        if pad is None or pad.GetNetCode() != gnd:
            raise SystemExit(f"Ground-stitch endpoint mismatch: {ref}:{pin}")
        point = route.pcbnew.VECTOR2I(route.pcbnew.FromMM(x), route.pcbnew.FromMM(y))
        track = route.pcbnew.PCB_TRACK(board)
        track.SetStart(pad.GetPosition())
        track.SetEnd(point)
        track.SetLayer(route.pcbnew.F_Cu)
        track.SetWidth(route.pcbnew.FromMM(0.50))
        track.SetNetCode(gnd)
        board.Add(track)
        via = route.pcbnew.PCB_VIA(board)
        via.SetPosition(point)
        via.SetWidth(route.pcbnew.FromMM(0.60))
        via.SetDrill(route.pcbnew.FromMM(0.30))
        via.SetNetCode(gnd)
        board.Add(via)


def export_cleaned_board(cleaned: Path) -> None:
    board = route.pcbnew.LoadBoard(str(cleaned))
    if board is None:
        raise SystemExit(f"Cannot reload {cleaned}")
    for zone in list(board.Zones()):
        board.Remove(zone)
    add_power_ground_stitching(board)
    route.add_ground_zones(board)
    route.pcbnew.SaveBoard(str(route.BOARD_PATH), board)

    route.configure_drc_severities()
    route.export_manufacturing()
    print(route.PRODUCTION)


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--from-clean":
        export_cleaned_board(Path(sys.argv[2]))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--cleanup-vias":
        replaced = Path(sys.argv[2])
        board = route.pcbnew.LoadBoard(str(replaced))
        if board is None:
            raise SystemExit(f"Cannot reload {replaced}")
        removed = remove_redundant_single_layer_vias(board)
        print(f"Removed {removed} redundant single-layer fanout vias")
        cleaned = route.OUT / "freerouting_clean.kicad_pcb"
        route.pcbnew.SaveBoard(str(cleaned), board)
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--from-clean", str(cleaned)],
            check=False,
        )
        if completed.returncode:
            raise SystemExit(completed.returncode)
        return

    seed = route.OUT / "freerouting_seed.kicad_pcb"
    session = route.OUT / "freerouting_result.ses"
    if not seed.exists() or not session.exists():
        raise SystemExit("Missing Freerouting seed or result session")

    board = route.pcbnew.LoadBoard(str(seed))
    if board is None:
        raise SystemExit(f"Cannot load {seed}")
    if not route.pcbnew.ImportSpecctraSES(board, str(session)):
        raise SystemExit(f"Cannot import {session}")

    route.link_footprints_to_schematic(board)
    route.verify_board_pin_nets(board)
    replaced = route.OUT / "freerouting_imported.kicad_pcb"
    route.pcbnew.SaveBoard(str(replaced), board)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--cleanup-vias", str(replaced)],
        check=False,
    )
    if completed.returncode:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
