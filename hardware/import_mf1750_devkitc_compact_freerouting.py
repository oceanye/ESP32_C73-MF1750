"""Import a compact-carrier Freerouting session for KiCad DRC iteration."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_compact"

sys.path.insert(0, str(HARDWARE))
import prepare_mf1750_devkitc_compact_freerouting as prep  # noqa: E402


def restore_vddio_testpoint(board) -> None:
    """Reconnect TP7 after the Freerouting three-terminal-net workaround."""
    route = prep.route
    code = board.GetNetcodeFromNetname("/VDDIO")
    tp7 = board.FindFootprintByReference("TP7").FindPadByNumber("1")
    r7 = board.FindFootprintByReference("R7").FindPadByNumber("2")
    if not code or tp7 is None or r7 is None or r7.GetNetCode() != code:
        raise SystemExit("Cannot restore TP7 VDDIO branch")
    tp7.SetNetCode(code)

    def add_track(start, end, layer):
        track = route.pcbnew.PCB_TRACK(board)
        track.SetStart(route.pcbnew.VECTOR2I_MM(*start))
        track.SetEnd(route.pcbnew.VECTOR2I_MM(*end))
        track.SetLayer(layer)
        track.SetWidth(route.pcbnew.FromMM(0.20))
        track.SetNetCode(code)
        board.Add(track)

    # Join TP7 to the routed VDDIO pad at R7 through an otherwise empty lower
    # channel.  No extra via is needed, so the branch cannot hit the nearby
    # EPD_3V3/GND fan-in around x=27 mm.
    add_track((29.0, 41.0), (29.0, 46.8), route.pcbnew.B_Cu)
    add_track((29.0, 46.8), (23.325, 46.8), route.pcbnew.B_Cu)
    add_track((23.325, 46.8), (23.325, 44.0), route.pcbnew.B_Cu)
    via = route.pcbnew.PCB_VIA(board)
    via.SetPosition(route.pcbnew.VECTOR2I_MM(23.325, 44.0))
    via.SetWidth(route.pcbnew.FromMM(0.60))
    via.SetDrill(route.pcbnew.FromMM(0.30))
    via.SetNetCode(code)
    board.Add(via)
    return


def main() -> None:
    prep.configure_modules()
    route = prep.route
    seed = OUT / "freerouting_seed.kicad_pcb"
    session = OUT / "freerouting_result.ses"
    board = route.pcbnew.LoadBoard(str(seed))
    if board is None or not route.pcbnew.ImportSpecctraSES(board, str(session)):
        raise SystemExit("Cannot import compact Freerouting session")
    restore_vddio_testpoint(board)
    route.link_footprints_to_schematic(board)
    route.verify_board_pin_nets(board)
    output = OUT / "freerouting_imported.kicad_pcb"
    route.pcbnew.SaveBoard(str(output), board)
    print(output)


if __name__ == "__main__":
    main()
