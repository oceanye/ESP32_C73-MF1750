"""Apply the reviewed R1 orientation/label cleanup to the B3 placement board."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware" / "mf1750_wroom_b3_power_tf"
PROJECT = "mf1750_wroom_b3_power_tf"
BOARD = OUT / f"{PROJECT}.kicad_pcb"
AUDIT = OUT / "placement_audit.json"
FROZEN_R0_BOARD = (
    "dda2ca8ec8985c54a590543c1a8a89fe4f8c66c3c573646c66f7fc1fa4fe844a"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    locks = list(OUT.glob("~*.lck"))
    if locks:
        raise SystemExit("Close KiCad first: " + ", ".join(map(str, locks)))
    actual = sha256(BOARD)
    if actual != FROZEN_R0_BOARD:
        raise SystemExit(
            f"R0 placement input drift: expected {FROZEN_R0_BOARD}, found {actual}"
        )
    board = pcbnew.LoadBoard(str(BOARD))
    if board is None:
        raise SystemExit("Unable to load B3 placement board")
    u1 = board.FindFootprintByReference("U1")
    j6 = board.FindFootprintByReference("J6")
    if u1 is None or j6 is None:
        raise SystemExit("Expected U1 and J6 placement footprints")
    u1.SetOrientationDegrees(270.0)
    j6.SetPosition(pcbnew.VECTOR2I_MM(14.0, 97.0))

    replacements = {
        "B3 NEW AREA": "B3 EXTENSION",
        "B2 VERIFIED DRIVER KEEP": "B2 DRIVER REGION PRESERVED",
        "TF INSERT FROM LOWER SIDE": "TF INSERT FROM LOWER SIDE",
        "WROOM ANTENNA -> RIGHT EDGE": "WROOM ANTENNA -> RIGHT EDGE",
        "MF1750 B3 WROOM 4L PLACEMENT R0": "MF1750 B3 WROOM 4L PLACEMENT R1",
    }
    positions = {
        "B3 NEW AREA": (32.5, 61.5, 0.0),
        "B2 VERIFIED DRIVER KEEP": (49.0, 58.0, 0.0),
        "TF INSERT FROM LOWER SIDE": (30.0, 90.5, 0.0),
        "WROOM ANTENNA -> RIGHT EDGE": (61.5, 95.0, 90.0),
        "MF1750 B3 WROOM 4L PLACEMENT R0": (31.0, 87.8, 0.0),
    }
    found: set[str] = set()
    for item in list(board.GetDrawings()):
        if not isinstance(item, pcbnew.PCB_TEXT):
            continue
        old = item.GetText()
        if old not in replacements:
            continue
        found.add(old)
        new = replacements[old]
        item.SetText(new)
        x, y, angle = positions[old]
        item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        item.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if found != set(replacements):
        raise SystemExit(f"Placement label contract drift: found {sorted(found)}")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(BOARD), board)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["revision"] = "B3-WROOM-POWER-TF-R1-PLACED"
    audit["artifacts"][BOARD.name] = {
        "bytes": BOARD.stat().st_size,
        "sha256": sha256(BOARD),
    }
    audit["r1_changes"] = {
        "wroom_antenna": "rotated toward right board edge",
        "battery_connector": "moved clear of lower mounting hole and USB-C",
        "silkscreen": "review labels deconflicted",
    }
    AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PASS board_sha256={sha256(BOARD)}")


if __name__ == "__main__":
    main()
