"""Build an ordinary-through-via Rev B1 dog-bone feasibility board.

The proven Rev B0 file is immutable input.  All three supply trees become
wide internal routing; each SMD supply pad reaches the tree using an explicit
short outer-layer dog-bone and a conventional 0.60/0.30 mm plated through via.
No via-in-pad, blind, buried, or microvia structures are used.

This remains a geometry/DRC probe until a fabricator stack-up is selected.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

import pcbnew

import probe_mf1750_devkitc_b1_four_layer as blind


ROOT = Path(__file__).resolve().parent.parent
B0_DIR = ROOT / "hardware" / "mf1750_devkitc_compact"
DEFAULT_INPUT = B0_DIR / "mf1750_devkitc_compact.kicad_pcb"
DEFAULT_OUTPUT = (
    Path(os.environ.get("TEMP", os.environ.get("TMP", ".")))
    / "mf1750_devkitc_b1_dogbone_probe.kicad_pcb"
)
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30

# Absolute centres obtained by per-pad KiCad DRC search.  Every annular ring is
# separated from its source SMD pad; the values are intentionally reviewable.
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


def replace_blind_fanouts(
    board: pcbnew.BOARD,
    netcodes: dict[str, int],
    targets: dict[str, tuple[int, float]],
) -> dict[str, int]:
    target_codes = set(netcodes.values())
    blind_vias = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_VIA" and item.GetNetCode() in target_codes
    ]
    for item in blind_vias:
        board.Remove(item)

    names_by_code = {code: name for name, code in netcodes.items()}
    seen: set[tuple[str, str]] = set()
    counts = {name: 0 for name in netcodes}
    pad_centres: set[tuple[int, int]] = set()
    via_centres: set[tuple[int, int]] = set()
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            name = names_by_code.get(pad.GetNetCode())
            if name is None or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            key = (footprint.GetReference(), pad.GetNumber())
            if key not in VIA_POSITIONS_MM:
                raise SystemExit(f"Missing dog-bone position for {key}")
            seen.add(key)
            counts[name] += 1
            origin = pcbnew.VECTOR2I(pad.GetPosition())
            destination = pcbnew.VECTOR2I_MM(*VIA_POSITIONS_MM[key])
            pad_centres.add((origin.x, origin.y))
            via_centres.add((destination.x, destination.y))

            outer = (
                pcbnew.F_Cu if pad.GetLayerSet().Contains(pcbnew.F_Cu) else pcbnew.B_Cu
            )
            inner, bus_width = targets[name]
            # R4's 1.65 mm pad pitch needs a 0.50 mm internal neck on the
            # input dog-bone; the rest of each distribution tree remains at
            # its audited 0.60/0.80 mm target width.
            inner_width = 0.50 if key == ("R4", "1") else bus_width
            dogbone_width = 0.40 if bus_width <= 0.60 else 0.50
            add_track(
                board, pad.GetNetCode(), outer, dogbone_width, origin, destination
            )
            add_track(board, pad.GetNetCode(), inner, inner_width, origin, destination)

            via = pcbnew.PCB_VIA(board)
            via.SetPosition(destination)
            via.SetNetCode(pad.GetNetCode())
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
            via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)

    if seen != set(VIA_POSITIONS_MM):
        raise SystemExit(f"Unused dog-bone entries: {set(VIA_POSITIONS_MM) - seen}")
    if pad_centres & via_centres:
        raise SystemExit("Via-in-pad centre remains")
    return counts


def audit(
    board: pcbnew.BOARD,
    netcodes: dict[str, int],
    expected_counts: dict[str, int],
    targets: dict[str, tuple[int, float]],
) -> dict[str, object]:
    if board.GetCopperLayerCount() != 4:
        raise SystemExit("Expected four copper layers")
    details: dict[str, object] = {}
    for name, (layer, width_mm) in targets.items():
        vias = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_VIA" and item.GetNetCode() == netcodes[name]
        ]
        if len(vias) != expected_counts[name]:
            raise SystemExit(f"{name}: wrong via count")
        if any(item.GetViaType() != pcbnew.VIATYPE_THROUGH for item in vias):
            raise SystemExit(f"{name}: non-through via remains")
        tracks = [
            item
            for item in board.GetTracks()
            if type(item).__name__ == "PCB_TRACK"
            and item.GetNetCode() == netcodes[name]
            and item.GetLayer() == layer
        ]
        widths = [pcbnew.ToMM(item.GetWidth()) for item in tracks]
        allowed_minimum = 0.50 if name == "/3V3" else width_mm
        if not tracks or min(widths) < allowed_minimum:
            raise SystemExit(f"{name}: internal bus width failed")
        details[name] = {
            "layer": board.GetLayerName(layer),
            "target_internal_bus_width_mm": width_mm,
            "minimum_local_neck_mm": min(widths),
            "ordinary_through_vias": len(vias),
        }
    return {
        "copper_layers": 4,
        "via_diameter_mm": VIA_DIAMETER_MM,
        "via_drill_mm": VIA_DRILL_MM,
        "via_in_pad": False,
        "blind_or_buried_vias": 0,
        "supplies": details,
    }


def mark_b1_identity(board: pcbnew.BOARD) -> None:
    """Make it impossible to mistake the promoted board for Rev B0."""
    replacements = {
        "MF1750 COMPACT B0": "MF1750 COMPACT B1",
    }
    changed = {key: 0 for key in replacements}
    for item in board.Drawings():
        if not isinstance(item, pcbnew.PCB_TEXT):
            continue
        replacement = replacements.get(item.GetText())
        if replacement is not None:
            item.SetText(replacement)
            changed[item.GetText().replace("B1", "B0")] += 1
    if changed["MF1750 COMPACT B0"] != 1:
        raise SystemExit(f"Unexpected B0 identity marker count: {changed}")


def expand_serialized_rule_areas(path: Path) -> None:
    """Expand five B0 keepouts after save, avoiding a KiCad 10 SWIG assertion."""
    text = path.read_text(encoding="utf-8")
    names = (
        "EDGE_TOP_KEEP_OUT",
        "EDGE_RIGHT_KEEP_OUT",
        "EDGE_LEFT_KEEP_OUT",
        "EDGE_BOTTOM_KEEP_OUT",
        "DEVKITC_ANTENNA_KEEP_OUT",
    )
    replacement = '"F.Cu" "In1.Cu" "In2.Cu" "B.Cu"'
    for name in names:
        pattern = re.compile(
            rf'(\(zone\s+\(layers )"F\.Cu" "B\.Cu"'
            rf'(?=[\s\S]{{0,180}}\(name "{re.escape(name)}"\))'
        )
        text, count = pattern.subn(rf"\g<1>{replacement}", text, count=1)
        if count != 1:
            raise SystemExit(f"Could not expand serialized rule area: {name}")
    path.write_text(text, encoding="utf-8")


def main_args(
    source_arg: Path, destination_arg: Path, *, copy_project: bool = True
) -> None:
    source = source_arg.resolve()
    destination = destination_arg.resolve()
    if source == destination:
        raise SystemExit("Refusing to overwrite Rev B0")
    destination.parent.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(source))
    netcodes = {name: board.GetNetcodeFromNetname(name) for name in blind.TARGETS}
    fanouts = blind.collect_smd_fanouts(board, netcodes)
    board.GetDesignSettings().SetCopperLayerCount(4)
    blind.migrate_supply_routing(board, netcodes)
    # R4 separates input /3V3 from output /EPD_3V3.  Keeping both rails on
    # In1 forces their 0.60 mm dog-bones to cross in the 1.65 mm pad pitch.
    # Move the complete EPD rail to In2; V_B already occupies In2 but is
    # spatially disjoint after the proven detours.
    epd_layer, epd_width = blind.TARGETS["/EPD_3V3"]
    if epd_layer != pcbnew.In1_Cu or epd_width != 0.60:
        raise SystemExit("Unexpected upstream EPD layer contract")
    for item in board.GetTracks():
        if (
            type(item).__name__ == "PCB_TRACK"
            and item.GetNetCode() == netcodes["/EPD_3V3"]
        ):
            item.SetLayer(pcbnew.In2_Cu)
    targets = dict(blind.TARGETS)
    targets["/EPD_3V3"] = (pcbnew.In2_Cu, epd_width)
    # Establish the known-good internal topology before replacing its HDI vias.
    blind.replace_target_vias(board, netcodes, fanouts)
    counts = replace_blind_fanouts(board, netcodes, targets)
    # Preserve track/via topology and regenerate fills later with KiCad CLI.
    # KiCad 10's Python zone filler asserts when a two-layer board's cached
    # multi-layer rule areas are converted to four copper layers.
    for zone in board.Zones():
        zone.UnFill()
    mark_b1_identity(board)
    result = audit(board, netcodes, counts, targets)
    pcbnew.SaveBoard(str(destination), board)
    expand_serialized_rule_areas(destination)
    source_project = B0_DIR / "mf1750_devkitc_compact.kicad_pro"
    if copy_project and source_project.exists():
        shutil.copyfile(source_project, destination.with_suffix(".kicad_pro"))
    result["board"] = str(destination)
    result["source_b0"] = str(source)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    main_args(args.input, args.output)


if __name__ == "__main__":
    main()
