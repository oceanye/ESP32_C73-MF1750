"""Non-production Rev B1 four-layer routing feasibility probe.

This script never overwrites the Rev B0 source board.  It converts a copy to
four copper layers, moves /3V3 and /EPD_3V3 to In1.Cu at 0.60 mm, moves /V_B
to In2.Cu at 0.80 mm, and uses sequential blind vias for SMD fanout.

The result proves only KiCad geometric/DRC feasibility.  It does not define a
fabricator-qualified stackup, impedance, dielectric, HDI build-up, current
capacity, thermal performance, or electrical qualification.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT / "hardware" / "mf1750_devkitc_compact" / "mf1750_devkitc_compact.kicad_pcb"
)
DEFAULT_OUTPUT = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", ".")))
    / "mf1750_devkitc_b1_four_layer_probe.kicad_pcb"
)
TARGETS = {
    "/3V3": (pcbnew.In1_Cu, 0.60),
    "/EPD_3V3": (pcbnew.In1_Cu, 0.60),
    "/V_B": (pcbnew.In2_Cu, 0.80),
}
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30


def point_mm(vector: pcbnew.VECTOR2I) -> tuple[float, float]:
    return (pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y))


def near_point(
    actual: tuple[float, float], expected: tuple[float, float], tolerance: float = 0.01
) -> bool:
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected, strict=True))


def add_track(
    board: pcbnew.BOARD,
    netcode: int,
    layer: int,
    width_mm: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNetCode(netcode)
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width_mm))
    track.SetStart(pcbnew.VECTOR2I_MM(*start))
    track.SetEnd(pcbnew.VECTOR2I_MM(*end))
    board.Add(track)


def reroute_3v3_trunk(board: pcbnew.BOARD, netcode: int) -> None:
    """Detour the B0 horizontal trunk below the FPC through-via field."""
    candidates = [
        track
        for track in board.GetTracks()
        if type(track).__name__ == "PCB_TRACK"
        and track.GetNetCode() == netcode
        and pcbnew.ToMM(track.GetLength()) > 30.0
    ]
    if len(candidates) != 1:
        raise SystemExit(f"Expected one /3V3 long trunk, found {len(candidates)}")
    track = candidates[0]
    start = point_mm(track.GetStart())
    end = point_mm(track.GetEnd())
    expected = {(3.8668, 18.4777), (41.6527, 18.4777)}
    if not all(
        any(near_point(point, item) for item in expected) for point in (start, end)
    ):
        raise SystemExit(f"Unexpected /3V3 trunk endpoints: {start}, {end}")
    track.SetEnd(pcbnew.VECTOR2I_MM(start[0], 14.5))
    add_track(board, netcode, pcbnew.In1_Cu, 0.60, (start[0], 14.5), (end[0], 14.5))
    add_track(board, netcode, pcbnew.In1_Cu, 0.60, (end[0], 14.5), end)


def reroute_epd_3v3(board: pcbnew.BOARD, netcode: int) -> None:
    """Detour In1 around the legacy /SL_CSB through-via at (5.7931, 42.3473)."""
    first = None
    second = None
    for track in board.GetTracks():
        if type(track).__name__ != "PCB_TRACK" or track.GetNetCode() != netcode:
            continue
        endpoints = (point_mm(track.GetStart()), point_mm(track.GetEnd()))
        if any(near_point(item, (4.8250, 42.4646)) for item in endpoints) and any(
            near_point(item, (5.5440, 41.7456)) for item in endpoints
        ):
            first = track
        if any(near_point(item, (5.5440, 41.7456)) for item in endpoints) and any(
            near_point(item, (6.6958, 41.7456)) for item in endpoints
        ):
            second = track
    if first is None or second is None:
        raise SystemExit("Expected /EPD_3V3 segments beside /SL_CSB were not found")
    first.SetStart(pcbnew.VECTOR2I_MM(4.8250, 42.4646))
    first.SetEnd(pcbnew.VECTOR2I_MM(4.8250, 41.1))
    second.SetStart(pcbnew.VECTOR2I_MM(6.6958, 41.1))
    second.SetEnd(pcbnew.VECTOR2I_MM(6.6958, 41.7456))
    add_track(board, netcode, pcbnew.In1_Cu, 0.60, (4.8250, 41.1), (6.6958, 41.1))


def reroute_v_b(board: pcbnew.BOARD, netcode: int) -> None:
    """Detour In2 around the legacy /RESEC through-via at (23.1150, 23.0181)."""
    candidates = [
        track
        for track in board.GetTracks()
        if type(track).__name__ == "PCB_TRACK"
        and track.GetNetCode() == netcode
        and 9.0 < pcbnew.ToMM(track.GetLength()) < 9.2
    ]
    if len(candidates) != 1:
        raise SystemExit(f"Expected one /V_B crossing segment, found {len(candidates)}")
    track = candidates[0]
    endpoints = sorted((point_mm(track.GetStart()), point_mm(track.GetEnd())))
    left, right = endpoints
    if not near_point(left, (20.4003, 23.6198)) or not near_point(
        right, (29.4788, 23.6198)
    ):
        raise SystemExit(f"Unexpected /V_B crossing endpoints: {left}, {right}")
    track.SetStart(pcbnew.VECTOR2I_MM(*left))
    track.SetEnd(pcbnew.VECTOR2I_MM(21.5, 24.25))
    add_track(board, netcode, pcbnew.In2_Cu, 0.80, (21.5, 24.25), (24.5, 24.25))
    add_track(board, netcode, pcbnew.In2_Cu, 0.80, (24.5, 24.25), right)


def collect_smd_fanouts(
    board: pcbnew.BOARD, netcodes: dict[str, int]
) -> dict[str, list[tuple[pcbnew.VECTOR2I, int]]]:
    result: dict[str, list[tuple[pcbnew.VECTOR2I, int]]] = {
        name: [] for name in netcodes
    }
    names_by_code = {code: name for name, code in netcodes.items()}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            name = names_by_code.get(pad.GetNetCode())
            if name is None or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            layer_set = pad.GetLayerSet()
            outer = pcbnew.F_Cu if layer_set.Contains(pcbnew.F_Cu) else pcbnew.B_Cu
            result[name].append((pcbnew.VECTOR2I(pad.GetPosition()), outer))
    return result


def replace_target_vias(
    board: pcbnew.BOARD,
    netcodes: dict[str, int],
    fanouts: dict[str, list[tuple[pcbnew.VECTOR2I, int]]],
) -> None:
    doomed = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_VIA" and item.GetNetCode() in netcodes.values()
    ]
    for item in doomed:
        board.Remove(item)
    del doomed, item
    for name, pads in fanouts.items():
        internal_layer = TARGETS[name][0]
        for position, outer_layer in pads:
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(position)
            via.SetNetCode(netcodes[name])
            via.SetViaType(pcbnew.VIATYPE_BLIND)
            via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
            via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
            via.SetLayerPair(outer_layer, internal_layer)
            board.Add(via)


def migrate_supply_routing(board: pcbnew.BOARD, netcodes: dict[str, int]) -> None:
    for name, (layer, width_mm) in TARGETS.items():
        for item in board.GetTracks():
            if (
                type(item).__name__ == "PCB_TRACK"
                and item.GetNetCode() == netcodes[name]
            ):
                item.SetLayer(layer)
                item.SetWidth(pcbnew.FromMM(width_mm))
    reroute_3v3_trunk(board, netcodes["/3V3"])
    reroute_epd_3v3(board, netcodes["/EPD_3V3"])
    reroute_v_b(board, netcodes["/V_B"])


def migrate_supply_zone(board: pcbnew.BOARD, netcode_3v3: int) -> None:
    matches = [
        zone
        for zone in board.Zones()
        if not zone.GetIsRuleArea() and zone.GetNetCode() == netcode_3v3
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected one /3V3 reinforcement zone, found {len(matches)}")
    matches[0].SetLayer(pcbnew.In1_Cu)


def audit(board: pcbnew.BOARD, netcodes: dict[str, int]) -> None:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit(
            f"Expected four copper layers, got {board.GetCopperLayerCount()}"
        )
    expected_vias = {"/3V3": 5, "/EPD_3V3": 4, "/V_B": 6}
    for name, (layer, min_width) in TARGETS.items():
        tracks = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_TRACK"
            and item.GetNetCode() == netcodes[name]
        ]
        vias = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_VIA" and item.GetNetCode() == netcodes[name]
        ]
        if not tracks or any(item.GetLayer() != layer for item in tracks):
            raise SystemExit(
                f"{name} was not wholly moved to {board.GetLayerName(layer)}"
            )
        if min(pcbnew.ToMM(item.GetWidth()) for item in tracks) < min_width:
            raise SystemExit(
                f"{name} still contains a track narrower than {min_width} mm"
            )
        if len(vias) != expected_vias[name]:
            raise SystemExit(
                f"{name} expected {expected_vias[name]} blind vias, found {len(vias)}"
            )
        if any(item.GetViaType() != pcbnew.VIATYPE_BLIND for item in vias):
            raise SystemExit(f"{name} contains a non-blind via")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.input.resolve()
    destination = args.output.resolve()
    if source == destination:
        raise SystemExit("Refusing to overwrite the source Rev B0 board")
    destination.parent.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise SystemExit(f"Cannot load {source}")
    netcodes = {name: board.GetNetcodeFromNetname(name) for name in TARGETS}
    if any(code <= 0 for code in netcodes.values()):
        raise SystemExit(f"Missing target net: {netcodes}")
    fanouts = collect_smd_fanouts(board, netcodes)

    board.GetDesignSettings().SetCopperLayerCount(4)
    migrate_supply_routing(board, netcodes)
    replace_target_vias(board, netcodes, fanouts)
    migrate_supply_zone(board, netcodes["/3V3"])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    audit(board, netcodes)
    pcbnew.SaveBoard(str(destination), board)
    print(destination)
    print("probe only: 4 layers; /3V3=0.60 In1; /EPD_3V3=0.60 In1; /V_B=0.80 In2")


if __name__ == "__main__":
    main()
