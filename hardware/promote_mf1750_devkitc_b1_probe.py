"""Promote a verified four-layer B1 probe into an independent review project.

This preserves Rev B0 as immutable input.  Rev B1 remains an engineering
review candidate: the script copies the matching schematic, local libraries,
BOM and pin map, then builds the ordinary-through-via PCB from the B0 board.
No Gerbers or production-release declaration are generated.
"""

from __future__ import annotations

import shutil
import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B0 = HARDWARE / "mf1750_devkitc_compact"
B1 = HARDWARE / "mf1750_devkitc_compact_b1"
PROJECT = "mf1750_devkitc_compact_b1"

sys.path.insert(0, str(HARDWARE))
import build_mf1750_devkitc_b1_dogbone_probe as build  # noqa: E402


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"Missing B0 source artifact: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"Missing B0 source directory: {source}")
    shutil.copytree(source, destination, dirs_exist_ok=True)


def main() -> None:
    B1.mkdir(parents=True, exist_ok=True)
    board = B1 / f"{PROJECT}.kicad_pcb"
    build.main_args(
        B0 / "mf1750_devkitc_compact.kicad_pcb",
        board,
        copy_project=False,
    )
    copy_file(
        B0 / "mf1750_devkitc_compact.kicad_sch",
        B1 / f"{PROJECT}.kicad_sch",
    )
    copy_file(
        B0 / "mf1750_devkitc_compact.kicad_pro",
        B1 / f"{PROJECT}.kicad_pro",
    )
    schematic = B1 / f"{PROJECT}.kicad_sch"
    schematic_text = schematic.read_text(encoding="utf-8")
    marker = "MF-1750 DevKitC Compact Carrier Rev B0"
    if schematic_text.count(marker) != 1:
        raise SystemExit("Unexpected B0 schematic title marker count")
    schematic.write_text(
        schematic_text.replace(marker, marker[:-2] + "B1"), encoding="utf-8"
    )
    project_file = B1 / f"{PROJECT}.kicad_pro"
    project_data = json.loads(project_file.read_text(encoding="utf-8"))
    project_data.setdefault("meta", {})["filename"] = project_file.name
    project_file.write_text(json.dumps(project_data, indent=2) + "\n", encoding="utf-8")
    for name in (
        "fp-lib-table",
        "sym-lib-table",
        "mf1750_local.kicad_sym",
        "bom_reference.csv",
        "mf1750_fpc_pinmap.csv",
    ):
        copy_file(B0 / name, B1 / name)
    copy_tree(B0 / "MF1750_Compact.pretty", B1 / "MF1750_Compact.pretty")
    print(board)


if __name__ == "__main__":
    main()
