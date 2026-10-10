"""Reproducibly derive the 65.0 x 60.5 mm B2 PCBA-margin board from B1.

The verified B1 board is immutable input.  All existing board objects are moved
rigidly by (+0.5, +2.5) mm.  Only the finished outline, the three GND pour
outlines, the four named edge rule areas, the antenna rule-area extent, revision
identity, and one non-geometric silkscreen cleanup are changed afterward.  The
J2 "ANTENNA" mechanical label keeps its exact position but moves from F.SilkS
to F.Fab because the enlarged edge would otherwise clip fabricated silkscreen.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B1_DIR = HARDWARE / "mf1750_devkitc_b1_single_power_layer"
B1_PROJECT = "mf1750_devkitc_b1_single_power_layer"
B1_BOARD = B1_DIR / f"{B1_PROJECT}.kicad_pcb"
B1_SCHEMATIC = B1_DIR / f"{B1_PROJECT}.kicad_sch"
B1_PRO = B1_DIR / f"{B1_PROJECT}.kicad_pro"

B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_PROJECT = "mf1750_devkitc_b2_pcba_margin"
B2_BOARD = B2_DIR / f"{B2_PROJECT}.kicad_pcb"
B2_SCHEMATIC = B2_DIR / f"{B2_PROJECT}.kicad_sch"
B2_PRO = B2_DIR / f"{B2_PROJECT}.kicad_pro"
B2_AUDIT = B2_DIR / "derivation_audit.json"

FROZEN_B1_SHA256 = {
    B1_BOARD.name: "d44afcd28056045aa19c875d424b6ad7d9e84712e238ee2340f6d087da62fde3",
    B1_SCHEMATIC.name: "ccb8ad72021231ce9768b86800a8536fc4d18ffc8e3edf8822c5b3040c757d95",
    B1_PRO.name: "ba26af897f39a3eda18448233faf9f247d78da2c3c19595577e3e1df6f9e40f3",
}

DX_MM = 0.5
DY_MM = 2.5
BOARD_WIDTH_MM = 65.0
BOARD_HEIGHT_MM = 60.5
POUR_INSET_MM = 0.65

EXPECTED_COUNTS = {
    "footprints": 61,
    "tracks": 629,
    "vias": 75,
    "zones": 8,
    "drawings": 20,
    "nets": 89,
}

GND_ZONE_KEYS = {
    ("GND_PLANE", "F.Cu"),
    ("GND_PLANE", "B.Cu"),
    ("IN1_SOLID_GND_PLANE", "In1.Cu"),
}
EDGE_RULE_RECTS = {
    "EDGE_TOP_KEEP_OUT": (0.0, 0.0, 65.0, 0.65),
    "EDGE_RIGHT_KEEP_OUT": (64.35, 0.0, 65.0, 60.5),
    "EDGE_LEFT_KEEP_OUT": (0.0, 0.0, 0.65, 60.5),
    "EDGE_BOTTOM_KEEP_OUT": (0.0, 59.85, 65.0, 60.5),
}
ANTENNA_RECT = (60.6, 34.1, 65.0, 59.85)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_frozen_b1() -> None:
    locks = list(B1_DIR.glob("~*.lck")) + list(B2_DIR.glob("~*.lck"))
    if locks:
        raise SystemExit(
            "Close KiCad before deriving B2: " + ", ".join(map(str, locks))
        )
    for path in (B1_BOARD, B1_SCHEMATIC, B1_PRO):
        actual = sha256(path)
        expected = FROZEN_B1_SHA256[path.name]
        if actual != expected:
            raise SystemExit(
                f"Frozen B1 input drift: {path} expected {expected}, found {actual}"
            )


def counts(board: pcbnew.BOARD) -> dict[str, int]:
    tracks = list(board.GetTracks())
    return {
        "footprints": len(board.GetFootprints()),
        "tracks": sum(type(item) is pcbnew.PCB_TRACK for item in tracks),
        "vias": sum(isinstance(item, pcbnew.PCB_VIA) for item in tracks),
        "zones": len(board.Zones()),
        "drawings": len(board.GetDrawings()),
        "nets": len(board.GetNetsByNetcode()),
    }


def rect_bounds(item: object) -> tuple[float, float, float, float]:
    start = item.GetStart()
    end = item.GetEnd()
    return (
        min(pcbnew.ToMM(start.x), pcbnew.ToMM(end.x)),
        min(pcbnew.ToMM(start.y), pcbnew.ToMM(end.y)),
        max(pcbnew.ToMM(start.x), pcbnew.ToMM(end.x)),
        max(pcbnew.ToMM(start.y), pcbnew.ToMM(end.y)),
    )


def require_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 1e-6:
        raise SystemExit(f"{label}: expected {expected:.6f}, found {actual:.6f}")


def require_rect(
    actual: tuple[float, ...], expected: tuple[float, ...], label: str
) -> None:
    for index, (found, wanted) in enumerate(zip(actual, expected, strict=True)):
        require_close(found, wanted, f"{label}[{index}]")


def set_zone_rectangle(
    zone: pcbnew.ZONE, rect: tuple[float, float, float, float]
) -> None:
    left, top, right, bottom = rect
    outline = zone.Outline()
    outline.RemoveAllContours()
    polygon = outline.NewOutline()
    for point in ((left, top), (right, top), (right, bottom), (left, bottom)):
        outline.Append(pcbnew.VECTOR2I_MM(*point), polygon)


def zone_bounds(zone: pcbnew.ZONE) -> tuple[float, float, float, float]:
    box = zone.GetBoundingBox()
    return (
        pcbnew.ToMM(box.GetX()),
        pcbnew.ToMM(box.GetY()),
        pcbnew.ToMM(box.GetX() + box.GetWidth()),
        pcbnew.ToMM(box.GetY() + box.GetHeight()),
    )


def validate_b1_geometry(board: pcbnew.BOARD) -> None:
    if counts(board) != EXPECTED_COUNTS:
        raise SystemExit(f"B1 semantic-count drift: {counts(board)}")
    edges = [
        item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    ]
    if len(edges) != 1 or edges[0].GetShapeStr().casefold() != "rect":
        raise SystemExit("B1 must contain one rectangular Edge.Cuts object")
    require_rect(rect_bounds(edges[0]), (0.0, 0.0, 62.0, 58.0), "B1 Edge.Cuts")

    zones = list(board.Zones())
    actual_gnd = {
        (zone.GetZoneName(), board.GetLayerName(zone.GetLayer()))
        for zone in zones
        if not zone.GetIsRuleArea()
    }
    if actual_gnd != GND_ZONE_KEYS:
        raise SystemExit(f"Unexpected B1 copper-zone contract: {sorted(actual_gnd)}")
    rules = {zone.GetZoneName() for zone in zones if zone.GetIsRuleArea()}
    expected_rules = set(EDGE_RULE_RECTS) | {"DEVKITC_ANTENNA_KEEP_OUT"}
    if rules != expected_rules:
        raise SystemExit(f"Unexpected B1 rule-area contract: {sorted(rules)}")


def derive_board() -> dict[str, object]:
    board = pcbnew.LoadBoard(str(B1_BOARD))
    if board is None:
        raise SystemExit(f"Cannot load {B1_BOARD}")
    validate_b1_geometry(board)

    board.Move(pcbnew.VECTOR2I_MM(DX_MM, DY_MM))

    edge = next(
        item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    )
    edge.SetStart(pcbnew.VECTOR2I_MM(0.0, 0.0))
    edge.SetEnd(pcbnew.VECTOR2I_MM(BOARD_WIDTH_MM, BOARD_HEIGHT_MM))

    rewritten: dict[str, list[float]] = {}
    for zone in board.Zones():
        name = zone.GetZoneName()
        layer_name = board.GetLayerName(zone.GetLayer())
        key = (name, layer_name)
        if key in GND_ZONE_KEYS:
            rect = (
                POUR_INSET_MM,
                POUR_INSET_MM,
                BOARD_WIDTH_MM - POUR_INSET_MM,
                BOARD_HEIGHT_MM - POUR_INSET_MM,
            )
            set_zone_rectangle(zone, rect)
            rewritten[f"{name}@{layer_name}"] = list(rect)
        elif name in EDGE_RULE_RECTS:
            rect = EDGE_RULE_RECTS[name]
            set_zone_rectangle(zone, rect)
            rewritten[name] = list(rect)
        elif name == "DEVKITC_ANTENNA_KEEP_OUT":
            set_zone_rectangle(zone, ANTENNA_RECT)
            rewritten[name] = list(ANTENNA_RECT)
        else:
            raise SystemExit(f"Refusing to leave unclassified zone unchanged: {name}")

    title = board.GetTitleBlock()
    title.SetTitle("MF1750 + ESP32-S3-DevKitC compact carrier")
    title.SetRevision("B2-4L-PCBA-EDGE")
    version_texts = [
        item
        for item in board.GetDrawings()
        if isinstance(item, pcbnew.PCB_TEXT)
        and item.GetText() == "MF1750 COMPACT B1 4L"
    ]
    if len(version_texts) != 1:
        raise SystemExit("Expected exactly one B1 board-version silkscreen text")
    version_texts[0].SetText("MF1750 B2 4L 65x60.5")

    j2 = board.FindFootprintByReference("J2")
    antenna_labels = (
        [
            item
            for item in j2.GraphicalItems()
            if isinstance(item, pcbnew.PCB_TEXT)
            and item.GetText() == "ANTENNA"
            and item.GetLayer() == pcbnew.F_SilkS
        ]
        if j2 is not None
        else []
    )
    if len(antenna_labels) != 1:
        raise SystemExit("Expected one J2 ANTENNA mechanical label on F.SilkS")
    antenna_labels[0].SetLayer(pcbnew.F_Fab)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    B2_DIR.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(B2_BOARD), board)

    reloaded = pcbnew.LoadBoard(str(B2_BOARD))
    if reloaded is None:
        raise SystemExit("KiCad could not reload the derived B2 board")
    if counts(reloaded) != EXPECTED_COUNTS:
        raise SystemExit(f"B2 semantic-count drift after reload: {counts(reloaded)}")
    edge2 = next(
        item for item in reloaded.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    )
    require_rect(
        rect_bounds(edge2),
        (0.0, 0.0, BOARD_WIDTH_MM, BOARD_HEIGHT_MM),
        "B2 Edge.Cuts",
    )

    for zone in reloaded.Zones():
        name = zone.GetZoneName()
        layer_name = reloaded.GetLayerName(zone.GetLayer())
        key = f"{name}@{layer_name}" if (name, layer_name) in GND_ZONE_KEYS else name
        if key not in rewritten:
            raise SystemExit(f"Unverified B2 zone after reload: {key}")
        require_rect(zone_bounds(zone), tuple(rewritten[key]), f"B2 zone {key}")

    return {
        "schema": 1,
        "derivation": "rigid_translation_plus_named_boundary_rewrite",
        "source_b1": str(B1_BOARD),
        "source_b1_sha256": FROZEN_B1_SHA256[B1_BOARD.name],
        "translation_mm": {"x": DX_MM, "y": DY_MM},
        "finished_outline_mm": {"width": BOARD_WIDTH_MM, "height": BOARD_HEIGHT_MM},
        "semantic_counts": counts(reloaded),
        "rewritten_zone_rectangles_mm": rewritten,
        "revision": "B2-4L-PCBA-EDGE",
        "silkscreen_cleanup": {
            "reference": "J2",
            "text": "ANTENNA",
            "from_layer": "F.SilkS",
            "to_layer": "F.Fab",
            "position_changed": False,
            "reason": "prevent fabricated silkscreen clipping at enlarged functional edge",
        },
    }


def copy_project_files() -> None:
    shutil.copyfile(B1_SCHEMATIC, B2_SCHEMATIC)
    schematic = B2_SCHEMATIC.read_text(encoding="utf-8")
    replacements = {
        'title "MF-1750 DevKitC Compact Carrier Rev B1 4L"': (
            'title "MF-1750 DevKitC Compact Carrier Rev B2 PCBA Edge Margin"'
        ),
        'company "62 x 58 mm engineering layout; R16 independent CS"': (
            'company "65 x 60.5 mm engineering layout; R16 independent CS"'
        ),
    }
    for old, new in replacements.items():
        if schematic.count(old) != 1:
            raise SystemExit(f"Unexpected schematic identity marker count: {old}")
        schematic = schematic.replace(old, new)
    B2_SCHEMATIC.write_text(schematic, encoding="utf-8")

    shutil.copyfile(B1_PRO, B2_PRO)
    project = json.loads(B2_PRO.read_text(encoding="utf-8"))
    project.setdefault("meta", {})["filename"] = B2_PRO.name
    B2_PRO.write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for filename in ("sym-lib-table", "mf1750_local.kicad_sym"):
        shutil.copyfile(B1_DIR / filename, B2_DIR / filename)
    shutil.copytree(
        B1_DIR / "MF1750_Compact.pretty",
        B2_DIR / "MF1750_Compact.pretty",
        dirs_exist_ok=True,
    )
    production = HARDWARE / "mf1750_production_v1" / "MF1750_Production.pretty"
    shutil.copytree(production, B2_DIR / "MF1750_Production.pretty", dirs_exist_ok=True)
    table = (B1_DIR / "fp-lib-table").read_text(encoding="utf-8")
    old_uri = "${KIPRJMOD}/../mf1750_production_v1/MF1750_Production.pretty"
    new_uri = "${KIPRJMOD}/MF1750_Production.pretty"
    if table.count(old_uri) != 1:
        raise SystemExit("Unexpected MF1750_Production library-table URI")
    (B2_DIR / "fp-lib-table").write_text(
        table.replace(old_uri, new_uri), encoding="utf-8"
    )


def main() -> None:
    require_frozen_b1()
    audit = derive_board()
    copy_project_files()
    require_frozen_b1()
    audit["artifacts"] = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in (B2_BOARD, B2_SCHEMATIC, B2_PRO)
    }
    B2_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
