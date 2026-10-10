"""Widen the B3 placement board and clear the WROOM antenna/USB mechanics."""

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
FROZEN_R1_BOARD = (
    "6b91164b8a3c8355581d3e09e0a6c9acc783e6abe3af31065de17a005c68e993"
)
BOARD_WIDTH_MM = 72.0
BOARD_HEIGHT_MM = 105.0
POUR_INSET_MM = 0.65


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def set_zone_rectangle(
    zone: pcbnew.ZONE, rect: tuple[float, float, float, float]
) -> None:
    left, top, right, bottom = rect
    outline = zone.Outline()
    outline.RemoveAllContours()
    polygon = outline.NewOutline()
    for point in ((left, top), (right, top), (right, bottom), (left, bottom)):
        outline.Append(pcbnew.VECTOR2I_MM(*point), polygon)


def main() -> None:
    if list(OUT.glob("~*.lck")):
        raise SystemExit("Close KiCad before revising B3")
    actual = sha256(BOARD)
    if actual != FROZEN_R1_BOARD:
        raise SystemExit(
            f"R1 placement input drift: expected {FROZEN_R1_BOARD}, found {actual}"
        )
    board = pcbnew.LoadBoard(str(BOARD))
    if board is None:
        raise SystemExit("Unable to load B3 placement board")
    title = board.GetTitleBlock()
    title.SetRevision("B3-WROOM-POWER-TF-R2-PLACED")

    edges = [
        item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    ]
    if len(edges) != 1 or edges[0].GetShapeStr().casefold() != "rect":
        raise SystemExit("Expected one rectangular board outline")
    edges[0].SetStart(pcbnew.VECTOR2I_MM(0.0, 0.0))
    edges[0].SetEnd(pcbnew.VECTOR2I_MM(BOARD_WIDTH_MM, BOARD_HEIGHT_MM))

    edge_rectangles = {
        "EDGE_TOP_KEEP_OUT": (0.0, 0.0, BOARD_WIDTH_MM, POUR_INSET_MM),
        "EDGE_RIGHT_KEEP_OUT": (
            BOARD_WIDTH_MM - POUR_INSET_MM,
            0.0,
            BOARD_WIDTH_MM,
            BOARD_HEIGHT_MM,
        ),
        "EDGE_LEFT_KEEP_OUT": (0.0, 0.0, POUR_INSET_MM, BOARD_HEIGHT_MM),
        "EDGE_BOTTOM_KEEP_OUT": (
            0.0,
            BOARD_HEIGHT_MM - POUR_INSET_MM,
            BOARD_WIDTH_MM,
            BOARD_HEIGHT_MM,
        ),
    }
    for zone in board.Zones():
        name = zone.GetZoneName()
        if not zone.GetIsRuleArea() and zone.GetNetname() == "/GND":
            set_zone_rectangle(
                zone,
                (
                    POUR_INSET_MM,
                    POUR_INSET_MM,
                    BOARD_WIDTH_MM - POUR_INSET_MM,
                    BOARD_HEIGHT_MM - POUR_INSET_MM,
                ),
            )
        elif name in edge_rectangles:
            set_zone_rectangle(zone, edge_rectangles[name])

    placements = {
        "U1": (58.0, 81.0, 270.0),
        "J5": (5.2, 88.0, 90.0),
        "H4": (51.0, 101.0, 0.0),
    }
    for reference, (x, y, rotation) in placements.items():
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise SystemExit(f"Missing placement footprint {reference}")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        footprint.SetOrientationDegrees(rotation)

    text_updates = {
        "B3 EXTENSION": ("B3 EXTENSION", 10.0, 61.5, 0.0),
        "B2 DRIVER REGION PRESERVED": ("B2 DRIVER PRESERVED", 9.0, 55.5, 0.0),
        "WROOM ANTENNA -> RIGHT EDGE": (
            "WROOM ANTENNA -> RIGHT EDGE",
            68.5,
            95.0,
            90.0,
        ),
    }
    found: set[str] = set()
    for item in board.GetDrawings():
        if not isinstance(item, pcbnew.PCB_TEXT):
            continue
        old = item.GetText()
        if old not in text_updates:
            continue
        found.add(old)
        new, x, y, rotation = text_updates[old]
        item.SetText(new)
        item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        item.SetTextAngle(pcbnew.EDA_ANGLE(rotation, pcbnew.DEGREES_T))
        item.SetTextSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        item.SetTextThickness(pcbnew.FromMM(0.12))
    if found != set(text_updates):
        raise SystemExit(f"Placement text drift: found {sorted(found)}")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(BOARD), board)

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["revision"] = "B3-WROOM-POWER-TF-R2-PLACED"
    audit["details"]["board_mm"] = {
        "width": BOARD_WIDTH_MM,
        "height": BOARD_HEIGHT_MM,
    }
    audit["artifacts"][BOARD.name] = {
        "bytes": BOARD.stat().st_size,
        "sha256": sha256(BOARD),
    }
    audit["r2_changes"] = {
        "board_width_mm": BOARD_WIDTH_MM,
        "reason": "move WROOM antenna keepout clear of preserved J2 copper",
        "usb_c": "shifted inward so signal pads remain inside Edge.Cuts",
    }
    AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PASS board_sha256={sha256(BOARD)}")


if __name__ == "__main__":
    main()
