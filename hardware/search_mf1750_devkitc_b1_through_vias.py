"""Search ordinary through-via fanout positions for the Rev B1 probe.

The search copies Rev B0 into a temporary directory and never writes to its
source tree.  Each candidate replaces one known-good blind via with a normal
through via, then runs KiCad DRC.  Results are ranked by electrical DRC count.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pcbnew

import probe_mf1750_devkitc_b1_four_layer as blind


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "hardware" / "mf1750_devkitc_compact"
SOURCE_BOARD = SOURCE_DIR / "mf1750_devkitc_compact.kicad_pcb"
SOURCE_PROJECT = SOURCE_DIR / "mf1750_devkitc_compact.kicad_pro"
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
TARGET_REFS = {
    ("L1", "1"),
    ("R4", "1"),
    ("R4", "2"),
    ("C3", "1"),
    ("C23", "1"),
    ("Q2", "2"),
    ("R8", "1"),
    ("R8", "2"),
    ("C0", "1"),
    ("C22", "1"),
    ("R9", "2"),
    ("R7", "1"),
    ("R10", "2"),
    ("R6", "1"),
    ("TP1", "1"),
}
IGNORED_CATEGORIES = {
    "lib_footprint_issues",
    "lib_footprint_mismatch",
    "silk_over_copper",
    "silk_overlap",
}


def pad_lookup(board: pcbnew.BOARD) -> dict[tuple[str, str], pcbnew.PAD]:
    return {
        (footprint.GetReference(), pad.GetNumber()): pad
        for footprint in board.GetFootprints()
        for pad in footprint.Pads()
        if (footprint.GetReference(), pad.GetNumber()) in TARGET_REFS
    }


def make_blind_base() -> pcbnew.BOARD:
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    netcodes = {name: board.GetNetcodeFromNetname(name) for name in blind.TARGETS}
    fanouts = blind.collect_smd_fanouts(board, netcodes)
    board.GetDesignSettings().SetCopperLayerCount(4)
    blind.migrate_supply_routing(board, netcodes)
    blind.replace_target_vias(board, netcodes, fanouts)
    blind.migrate_supply_zone(board, netcodes["/3V3"])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return board


def candidate_offsets(
    pad: pcbnew.PAD, radius_mm: float, step_mm: float
) -> list[tuple[float, float]]:
    half_x = pcbnew.ToMM(pad.GetSize().x) / 2
    half_y = pcbnew.ToMM(pad.GetSize().y) / 2
    minimum_gap = 0.16
    via_radius = 0.30
    result = []
    steps = round(radius_mm / step_mm)
    for ix in range(-steps, steps + 1):
        for iy in range(-steps, steps + 1):
            dx = ix * step_mm
            dy = iy * step_mm
            if dx == 0 and dy == 0:
                continue
            if math.hypot(dx, dy) > radius_mm + 1e-6:
                continue
            # Annular ring must be separated from the SMD copper to avoid
            # solder-wicking via-in-pad geometry.
            outside_x = max(abs(dx) - half_x, 0.0)
            outside_y = max(abs(dy) - half_y, 0.0)
            if math.hypot(outside_x, outside_y) < via_radius + minimum_gap:
                continue
            result.append((dx, dy))
    return sorted(result, key=lambda value: (math.hypot(*value), value))


def add_track(
    board: pcbnew.BOARD,
    pad: pcbnew.PAD,
    layer: int,
    width_mm: float,
    destination: pcbnew.VECTOR2I,
) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetNetCode(pad.GetNetCode())
    track.SetLayer(layer)
    track.SetWidth(pcbnew.FromMM(width_mm))
    track.SetStart(pad.GetPosition())
    track.SetEnd(destination)
    board.Add(track)


def make_candidate(
    base_path: Path,
    key: tuple[str, str],
    offset: tuple[float, float],
    output: Path,
) -> None:
    board = pcbnew.LoadBoard(str(base_path))
    pad = pad_lookup(board)[key]
    origin = pad.GetPosition()
    netname = pad.GetNetname()
    target_layer, target_width = blind.TARGETS[netname]
    blind_vias = [
        item
        for item in board.GetTracks()
        if type(item).__name__ == "PCB_VIA"
        and item.GetNetCode() == pad.GetNetCode()
        and item.GetPosition() == origin
        and item.GetViaType() == pcbnew.VIATYPE_BLIND
    ]
    if len(blind_vias) != 1:
        raise RuntimeError(f"{key}: expected one source blind via, got {len(blind_vias)}")
    board.Remove(blind_vias[0])
    destination = pcbnew.VECTOR2I_MM(
        pcbnew.ToMM(origin.x) + offset[0], pcbnew.ToMM(origin.y) + offset[1]
    )
    outer_layer = (
        pcbnew.F_Cu if pad.GetLayerSet().Contains(pcbnew.F_Cu) else pcbnew.B_Cu
    )
    outer_width = 0.40 if target_width <= 0.60 else 0.50
    add_track(board, pad, outer_layer, outer_width, destination)
    add_track(board, pad, target_layer, target_width, destination)

    via = pcbnew.PCB_VIA(board)
    via.SetPosition(destination)
    via.SetNetCode(pad.GetNetCode())
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(pcbnew.FromMM(0.60))
    via.SetDrill(pcbnew.FromMM(0.30))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(output), board)


def electrical_violations(report: Path) -> tuple[int, list[str]]:
    categories = re.findall(r"^\[([^]]+)\]", report.read_text("utf-8"), re.MULTILINE)
    relevant = [item for item in categories if item not in IGNORED_CATEGORIES]
    return len(relevant), relevant


def run_drc(board_path: Path) -> tuple[int, list[str]]:
    project_path = board_path.with_suffix(".kicad_pro")
    shutil.copyfile(SOURCE_PROJECT, project_path)
    report = board_path.with_suffix(".rpt")
    subprocess.run(
        [
            str(KICAD_CLI),
            "pcb",
            "drc",
            "--severity-all",
            "--output",
            str(report),
            str(board_path),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return electrical_violations(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Limit search to one reference")
    parser.add_argument("--pad", help="Limit search to one pad number")
    parser.add_argument("--radius", type=float, default=2.5)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--keep", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    base = make_blind_base()
    pads = pad_lookup(base)
    selected = [
        key
        for key in sorted(TARGET_REFS)
        if (not args.ref or key[0] == args.ref)
        and (not args.pad or key[1] == args.pad)
    ]
    if not selected:
        raise SystemExit("No pads selected")

    run_dir = Path(tempfile.mkdtemp(prefix="mf1750_b1_through_search_"))
    base_path = run_dir / "base.kicad_pcb"
    pcbnew.SaveBoard(str(base_path), base)
    jobs: list[tuple[tuple[str, str], tuple[float, float], Path]] = []
    for key in selected:
        for index, offset in enumerate(
            candidate_offsets(pads[key], args.radius, args.step)
        ):
            path = run_dir / f"{key[0]}_{key[1]}_{index:03d}.kicad_pcb"
            make_candidate(base_path, key, offset, path)
            jobs.append((key, offset, path))

    results: dict[str, list[dict[str, object]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(run_drc, path): (key, offset) for key, offset, path in jobs}
        for future in concurrent.futures.as_completed(future_map):
            key, offset = future_map[future]
            count, categories = future.result()
            name = f"{key[0]}.{key[1]}"
            results.setdefault(name, []).append(
                {"offset_mm": offset, "violations": count, "categories": categories}
            )
    for entries in results.values():
        entries.sort(key=lambda item: (item["violations"], math.hypot(*item["offset_mm"])))
        del entries[args.keep :]

    payload = {"run_dir": str(run_dir), "results": results}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
