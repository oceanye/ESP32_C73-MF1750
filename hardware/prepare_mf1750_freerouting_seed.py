"""Create the Specctra seed used for the final MF-1750 rip-up/retry route."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_mf1750_production_v1 as route  # noqa: E402


def configure_netclasses(board: route.pcbnew.BOARD) -> None:
    settings = board.GetDesignSettings().m_NetSettings
    default = settings.GetDefaultNetclass()
    default.SetTrackWidth(route.pcbnew.FromMM(0.25))
    default.SetClearance(route.pcbnew.FromMM(0.20))
    default.SetViaDiameter(route.pcbnew.FromMM(0.60))
    default.SetViaDrill(route.pcbnew.FromMM(0.30))

    by_width: dict[float, list[str]] = {}
    for name, width in route.WIDE_NETS.items():
        by_width.setdefault(width, []).append(name)
    for width, names in sorted(by_width.items()):
        class_name = f"W{round(width * 1000):03d}"
        netclass = route.pcbnew.NETCLASS(class_name)
        netclass.SetTrackWidth(route.pcbnew.FromMM(width))
        netclass.SetClearance(route.pcbnew.FromMM(0.20))
        netclass.SetViaDiameter(route.pcbnew.FromMM(0.60))
        netclass.SetViaDrill(route.pcbnew.FromMM(0.30))
        settings.SetNetclass(class_name, netclass)
        for name in names:
            settings.SetNetclassPatternAssignment(f"/{name}", class_name)
    settings.RecomputeEffectiveNetclasses()


def main() -> None:
    board = route.pcbnew.LoadBoard(str(route.BOARD_PATH))
    if board is None:
        raise SystemExit(f"Cannot load {route.BOARD_PATH}")
    for item in list(board.GetTracks()):
        board.Remove(item)
    for zone in list(board.Zones()):
        board.Remove(zone)
    route.link_footprints_to_schematic(board)
    route.verify_board_pin_nets(board)
    router = route.GridRouter(board)
    route.fanout_fpc_doubled(router, board)
    by_net = route.all_pads_by_net(board)
    route.route_bias_bundle_direct(router, by_net)
    # The final compact placement naturally produces short power paths.
    # Optional net names are accepted only for routing experiments; the
    # production seed intentionally has no protected power-loop traces.
    requested_power_nets = set(sys.argv[1:])
    if requested_power_nets:
        route.route_power_loops_direct(router, board, requested_power_nets)
    configure_netclasses(board)

    seed = route.OUT / "freerouting_seed.kicad_pcb"
    dsn = route.OUT / "freerouting_seed.dsn"
    route.pcbnew.SaveBoard(str(seed), board)
    if not route.pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("Specctra DSN export failed")
    print(dsn)


if __name__ == "__main__":
    main()
