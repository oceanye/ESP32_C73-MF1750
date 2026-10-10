"""Bind the visible placement label to the reviewed B3 R2 board."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware" / "mf1750_wroom_b3_power_tf"
BOARD = OUT / "mf1750_wroom_b3_power_tf.kicad_pcb"
AUDIT = OUT / "placement_audit.json"
FROZEN_INPUT = "937583ad900f8a22aac68fbd63b2d13093d3806f4423ace56232223aaa3d69a8"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    result.update(path.read_bytes())
    return result.hexdigest()


def main() -> None:
    if list(OUT.glob("~*.lck")):
        raise SystemExit("Close KiCad before updating B3 silkscreen")
    if digest(BOARD) != FROZEN_INPUT:
        raise SystemExit("B3 R2 board input drift")
    board = pcbnew.LoadBoard(str(BOARD))
    matches = [
        item
        for item in board.GetDrawings()
        if isinstance(item, pcbnew.PCB_TEXT)
        and item.GetText() == "MF1750 B3 WROOM 4L PLACEMENT R1"
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected one R1 placement label, found {len(matches)}")
    matches[0].SetText("MF1750 B3 WROOM 4L PLACEMENT R2")
    pcbnew.SaveBoard(str(BOARD), board)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["artifacts"][BOARD.name] = {
        "bytes": BOARD.stat().st_size,
        "sha256": digest(BOARD),
    }
    audit["r2_changes"]["visible_revision_label"] = "R2"
    AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PASS board_sha256={digest(BOARD)}")


if __name__ == "__main__":
    main()
