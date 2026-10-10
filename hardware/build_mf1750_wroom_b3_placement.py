"""Build the MF1750 WROOM B3 mechanical placement candidate.

This is intentionally a PLACED_CANDIDATE, not a routed or fabrication-ready
board.  It preserves the verified B2 display-driver geometry and extends the
board downward for an ESP32-S3-WROOM-1-N16R8, battery/PowerPath circuitry,
microSD, USB-C and controls.  New electrical connectivity is not yet captured
in the copied B2 schematic, so schematic parity is expected to fail until the
B3 hierarchical sheets are completed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_PROJECT = "mf1750_devkitc_b2_pcba_margin"
OUT = HARDWARE / "mf1750_wroom_b3_power_tf"
PROJECT = "mf1750_wroom_b3_power_tf"
KICAD_SHARE = Path(r"C:\Program Files\KiCad\10.0\share\kicad")
FP_ROOT = KICAD_SHARE / "footprints"

B2_FILES = {
    f"{B2_PROJECT}.kicad_pro": (
        "fcd393069f22846615113f8296d6553c5ffeee8ba507b7475f81baae9fe4aa27"
    ),
    f"{B2_PROJECT}.kicad_sch": (
        "bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb"
    ),
    f"{B2_PROJECT}.kicad_pcb": (
        "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
    ),
}

BOARD_WIDTH_MM = 72.0
BOARD_HEIGHT_MM = 105.0
ORIGINAL_B2_HEIGHT_MM = 60.5
POUR_INSET_MM = 0.65


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_inputs() -> None:
    locks = list(B2_DIR.glob("~*.lck")) + list(OUT.glob("~*.lck"))
    if locks:
        raise SystemExit("Close KiCad first: " + ", ".join(map(str, locks)))
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing B3 candidate: {OUT}")
    for name, expected in B2_FILES.items():
        actual = sha256(B2_DIR / name)
        if actual != expected:
            raise SystemExit(
                f"Frozen B2 input drift: {name}: expected {expected}, found {actual}"
            )


def set_zone_rectangle(
    zone: pcbnew.ZONE, rect: tuple[float, float, float, float]
) -> None:
    left, top, right, bottom = rect
    outline = zone.Outline()
    outline.RemoveAllContours()
    polygon = outline.NewOutline()
    for point in ((left, top), (right, top), (right, bottom), (left, bottom)):
        outline.Append(pcbnew.VECTOR2I_MM(*point), polygon)


def load_footprint(library: str, name: str) -> pcbnew.FOOTPRINT:
    footprint = pcbnew.FootprintLoad(str(FP_ROOT / f"{library}.pretty"), name)
    if footprint is None:
        raise SystemExit(f"Unable to load KiCad footprint {library}:{name}")
    return footprint


def add_footprint(
    board: pcbnew.BOARD,
    library: str,
    name: str,
    reference: str,
    value: str,
    x: float,
    y: float,
    rotation: float = 0.0,
    dnp: bool = False,
) -> pcbnew.FOOTPRINT:
    footprint = load_footprint(library, name)
    footprint.SetReference(reference)
    footprint.SetValue(value)
    footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    footprint.SetOrientationDegrees(rotation)
    footprint.SetDNP(dnp)
    board.Add(footprint)
    return footprint


def add_text(
    board: pcbnew.BOARD,
    text: str,
    x: float,
    y: float,
    size: float = 1.0,
    layer: int = pcbnew.F_SilkS,
    rotation: float = 0.0,
) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(layer)
    item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    item.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    item.SetTextThickness(pcbnew.FromMM(max(0.12, size * 0.15)))
    item.SetTextAngle(pcbnew.EDA_ANGLE(rotation, pcbnew.DEGREES_T))
    board.Add(item)


def add_rect(
    board: pcbnew.BOARD,
    left: float,
    top: float,
    right: float,
    bottom: float,
    layer: int = pcbnew.F_SilkS,
    width: float = 0.2,
) -> None:
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_RECT)
    item.SetLayer(layer)
    item.SetStart(pcbnew.VECTOR2I_MM(left, top))
    item.SetEnd(pcbnew.VECTOR2I_MM(right, bottom))
    item.SetWidth(pcbnew.FromMM(width))
    board.Add(item)


def derive_board(board_path: Path) -> dict[str, object]:
    board = pcbnew.LoadBoard(str(B2_DIR / f"{B2_PROJECT}.kicad_pcb"))
    if board is None:
        raise SystemExit("Unable to load frozen B2 board")

    edges = [
        item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    ]
    if len(edges) != 1 or edges[0].GetShapeStr().casefold() != "rect":
        raise SystemExit("B2 must contain exactly one rectangular Edge.Cuts item")
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

    title = board.GetTitleBlock()
    title.SetTitle("MF1750 WROOM battery + TF integrated carrier")
    title.SetRevision("B3-WROOM-POWER-TF-R0-PLACED")

    j2 = board.FindFootprintByReference("J2")
    if j2 is None:
        raise SystemExit("Frozen B2 DevKitC socket J2 is missing")
    j2.SetDNP(True)
    j2.SetValue("DEVKITC DEBUG SOCKET - DNP WITH U1")

    add_footprint(
        board,
        "RF_Module",
        "ESP32-S3-WROOM-1",
        "U1",
        "ESP32-S3-WROOM-1-N16R8 / C2913202",
        58.0,
        81.0,
        270.0,
    )
    add_footprint(
        board,
        "Connector_Card",
        "microSD_HC_Molex_104031-0811",
        "J4",
        "Molex 1040310811 / C585350",
        30.0,
        98.5,
        180.0,
    )
    add_footprint(
        board,
        "Connector_USB",
        "USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        "J5",
        "TYPE-C-31-M-12 / C165948 CHARGE+USB",
        5.2,
        88.0,
        90.0,
    )
    add_footprint(
        board,
        "Connector_JST",
        "JST_PH_B3B-PH-K_1x03_P2.00mm_Vertical",
        "J6",
        "BAT+ BAT- NTC / MPN HOLD",
        14.0,
        97.0,
        180.0,
    )

    add_footprint(
        board,
        "Package_DFN_QFN",
        "VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
        "U2",
        "BQ24074RGTR / C54313",
        11.0,
        65.5,
    )
    add_footprint(
        board,
        "Package_DFN_QFN",
        "TDFN-12_2x3mm_P0.5mm",
        "U3",
        "STM6600CS25DM6F / C443976",
        20.0,
        65.5,
    )
    add_footprint(
        board,
        "Package_TO_SOT_SMD",
        "TSOT-23-6",
        "U5",
        "TPS22950CQDDCRQ1 / C17349276",
        35.0,
        66.0,
    )
    for reference, x in (("U6", 11.5), ("U7", 25.0)):
        add_footprint(
            board,
            "Package_SO",
            "TSSOP-14_4.4x5mm_P0.65mm",
            reference,
            "SN74LVC125APWR / C7813",
            x,
            77.0,
        )

    for reference, x, y in (("H3", 4.0, 101.0), ("H4", 51.0, 101.0)):
        add_footprint(
            board,
            "MountingHole",
            "MountingHole_2.5mm",
            reference,
            "M2.5_NPTH",
            x,
            y,
        )

    # RNM0015A and SKSCLDE010 need project-owned verified footprints.  Draw
    # explicit placement envelopes instead of silently substituting a package.
    add_rect(board, 27.5, 63.0, 32.5, 68.0)
    add_text(board, "U4 TPS63070", 30.0, 61.8, 0.65)
    add_text(board, "RNM FP HOLD", 30.0, 69.0, 0.55)
    for label, y in (("PWR", 66.0), ("USER1", 73.0), ("USER2", 80.0)):
        add_rect(board, 0.65, y - 2.2, 5.2, y + 2.2)
        add_text(board, label, 7.8, y, 0.65)
    add_rect(board, 7.0, 71.0, 38.0, 84.0, pcbnew.Dwgs_User, 0.15)
    add_text(board, "POWER / 3V3 / IO ISOLATION", 22.5, 82.8, 0.75)
    add_text(board, "B3 EXTENSION", 10.0, 61.5, 0.8)
    add_text(board, "TF INSERT FROM LOWER SIDE", 30.0, 90.5, 0.7)
    add_text(board, "WROOM ANTENNA -> RIGHT EDGE", 68.5, 95.0, 0.55, rotation=90)
    add_text(board, "MF1750 B3 WROOM 4L PLACEMENT R0", 31.0, 87.8, 0.65)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(board_path), board)

    reloaded = pcbnew.LoadBoard(str(board_path))
    if reloaded is None:
        raise SystemExit("KiCad failed to reload B3 placement board")
    return {
        "board_mm": {"width": BOARD_WIDTH_MM, "height": BOARD_HEIGHT_MM},
        "preserved_b2_region_mm": {
            "left": 0.0,
            "top": 0.0,
            "right": BOARD_WIDTH_MM,
            "bottom": ORIGINAL_B2_HEIGHT_MM,
        },
        "new_major_footprints": [
            "U1 ESP32-S3-WROOM-1-N16R8",
            "J4 Molex 1040310811 microSD",
            "J5 TYPE-C-31-M-12",
            "J6 3-wire battery connector candidate",
            "U2 BQ24074RGTR",
            "U3 STM6600CS25DM6F",
            "U5 TPS22950CQDDCRQ1",
            "U6/U7 SN74LVC125APWR",
        ],
        "footprint_holds": [
            "U4 TPS63070 RNM0015A project footprint",
            "SW1/SW2/SW3 Alps SKSCLDE010 project footprint",
        ],
        "state": "PLACED_CANDIDATE_NOT_ROUTED_NOT_SCHEMATIC_PARITY",
    }


def copy_project_files(temp_out: Path) -> None:
    shutil.copyfile(
        B2_DIR / f"{B2_PROJECT}.kicad_sch", temp_out / f"{PROJECT}.kicad_sch"
    )
    schematic = (temp_out / f"{PROJECT}.kicad_sch").read_text(encoding="utf-8")
    old_title = 'title "MF-1750 DevKitC Compact Carrier Rev B2 PCBA Edge Margin"'
    new_title = 'title "MF1750 WROOM B3 placement; electrical expansion pending"'
    if schematic.count(old_title) != 1:
        raise SystemExit("Unexpected B2 schematic title marker")
    (temp_out / f"{PROJECT}.kicad_sch").write_text(
        schematic.replace(old_title, new_title), encoding="utf-8"
    )

    project = json.loads(
        (B2_DIR / f"{B2_PROJECT}.kicad_pro").read_text(encoding="utf-8")
    )
    project.setdefault("meta", {})["filename"] = f"{PROJECT}.kicad_pro"
    (temp_out / f"{PROJECT}.kicad_pro").write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for filename in (
        "fp-lib-table",
        "sym-lib-table",
        "mf1750_local.kicad_sym",
    ):
        shutil.copyfile(B2_DIR / filename, temp_out / filename)
    for directory in ("MF1750_Compact.pretty", "MF1750_Production.pretty"):
        shutil.copytree(B2_DIR / directory, temp_out / directory)


def main() -> None:
    require_inputs()
    with tempfile.TemporaryDirectory(prefix="mf1750_b3_", dir=HARDWARE) as temp:
        temp_out = Path(temp)
        copy_project_files(temp_out)
        details = derive_board(temp_out / f"{PROJECT}.kicad_pcb")
        readme = f"""# MF1750 WROOM B3 placement candidate

State: `PLACED_CANDIDATE_NOT_ROUTED_NOT_SCHEMATIC_PARITY`

This board preserves the verified B2 display-driver region and extends the
outline downward.  It is a mechanical/component placement review artifact.
The copied B2 schematic does **not** yet contain the WROOM, PowerPath, TF,
buttons or signal-isolation sheets.  Do not use this revision for fabrication.

Board: {BOARD_WIDTH_MM:.1f} x {BOARD_HEIGHT_MM:.1f} mm, four layers.
TF card entry: lower board edge, card travels from outside toward the board.
"""
        (temp_out / "README.md").write_text(readme, encoding="utf-8")
        audit = {
            "schema": 1,
            "revision": "B3-WROOM-POWER-TF-R0-PLACED",
            "source_b2_sha256": B2_FILES,
            "details": details,
            "artifacts": {
                path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in (
                    temp_out / f"{PROJECT}.kicad_pro",
                    temp_out / f"{PROJECT}.kicad_sch",
                    temp_out / f"{PROJECT}.kicad_pcb",
                    temp_out / "README.md",
                )
            },
        }
        (temp_out / "placement_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_out.replace(OUT)
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
