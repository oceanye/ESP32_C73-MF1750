from __future__ import annotations

"""Generate the MF-1750 production prototype KiCad project.

This generator intentionally keeps the generated artefacts reproducible.  The
electrical baseline is the MF-1750/M009F-T A1 page-10 reference circuit.  Two
small but important bring-up options are added:

* R15 links CSB to SL_CSB by default, matching the InkCubic E2802 cascade
  adapter's J4 link.  R16 can instead route SL_CSB to an independent CS2 pin.
* BS0/BS1 default low for 4-wire SPI per the MF-1750 interface table, while
  DNP pull-up positions retain a reversible mode option.

The generated PCB is an 80 mm x 75 mm, two-layer bring-up board.  Routing and
manufacturing exports are completed by ``route_mf1750_production_v1.py``.
"""

import csv
import json
import re
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_production_v1"
PROJECT = "mf1750_production_v1"
KICAD = Path(r"C:\Program Files\KiCad\10.0\share\kicad")

sys.path.insert(0, str(HARDWARE))
import generate_mf1750_kicad_project as base  # noqa: E402


_ORIGINAL_FOOTPRINT_NAME_FOR_PART2 = base.footprint_name_for_part2
_ORIGINAL_FOOTPRINT_PATH_FOR_PART2 = base.footprint_path_for_part2
_ORIGINAL_PATCH_FOOTPRINT = base.patch_footprint


FPC_FOOTPRINT_NAME = "MF1750_Production:XUNPU_FPC-05FB-50PH20_1x50_P0.5mm_DualContact"
FPC_LIB_DIR = OUT / "MF1750_Production.pretty"
FPC_FOOTPRINT = FPC_LIB_DIR / "XUNPU_FPC-05FB-50PH20_1x50_P0.5mm_DualContact.kicad_mod"
INDUCTOR_FOOTPRINT_NAME = "MF1750_Production:SXN_SMMS0650_7.1x6.6mm"
INDUCTOR_FOOTPRINT = FPC_LIB_DIR / "SXN_SMMS0650_7.1x6.6mm.kicad_mod"
SC70_FOOTPRINT_NAME = "Package_TO_SOT_SMD:SOT-323_SC-70"
SC70_FOOTPRINT = KICAD / "footprints" / "Package_TO_SOT_SMD.pretty" / "SOT-323_SC-70.kicad_mod"
SOT23_FOOTPRINT_NAME = "Package_TO_SOT_SMD:SOT-23-3"
SOT23_FOOTPRINT = KICAD / "footprints" / "Package_TO_SOT_SMD.pretty" / "SOT-23-3.kicad_mod"
MOUNTING_HOLE = KICAD / "footprints" / "MountingHole.pretty" / "MountingHole_2.5mm.kicad_mod"


FPC_PINS: list[base.Pin] = [
    base.Pin(1, "NC", None, "Per I/O and mechanical pin tables; page-10 VPP label is not used"),
    base.Pin(2, "TFT_VCOM", "TFT_VCOM"),
    base.Pin(3, "FPL_VCOM", "FPL_VCOM"),
    base.Pin(4, "SL_CSB", "SL_CSB", "Slave controller select; default linked to CSB through R15"),
    base.Pin(5, "GDRH", "GDRH"),
    base.Pin(6, "RESEH", "RESEH"),
    base.Pin(7, "GDRL", None, "Reserved"),
    base.Pin(8, "RESEL", "RESEL"),
    base.Pin(9, "GDRC", "GDRC"),
    base.Pin(10, "RESEC", "RESEC"),
    base.Pin(11, "VPC", "VPC"),
    base.Pin(12, "GND", "GND"),
    base.Pin(13, "VGL", "PREVGL"),
    base.Pin(14, "VPH", "VPH"),
    base.Pin(15, "VSH", "VSH"),
    base.Pin(16, "VSH_LV", "VSH_LV"),
    base.Pin(17, "VSH_LV2", "VSH_LV2"),
    base.Pin(18, "VSL", "VSL"),
    base.Pin(19, "VSL_LV", "VSL_LV"),
    base.Pin(20, "VSL_LV2", "VSL_LV2"),
    base.Pin(21, "GNDA", "GND"),
    base.Pin(22, "REFN", "REFN"),
    base.Pin(23, "REFP", "REFP"),
    base.Pin(24, "TSCL", "TSCL"),
    base.Pin(25, "TSDA", "TSDA"),
    base.Pin(26, "BS0", "BS0"),
    base.Pin(27, "BS1", "BS1"),
    base.Pin(28, "RST_N", "RST_N"),
    base.Pin(29, "BUSY_N", "BUSY_N"),
    base.Pin(30, "DC", "DC"),
    base.Pin(31, "CSB", "CSB"),
    base.Pin(32, "SCL", "SCL"),
    base.Pin(33, "SI0", "SI0"),
    base.Pin(34, "SI1", None, "Reserved in 4-wire SPI"),
    base.Pin(35, "SI2", None, "Reserved in 4-wire SPI"),
    base.Pin(36, "SI3", None, "Reserved in 4-wire SPI"),
    base.Pin(37, "VDDD", "VDDD"),
    base.Pin(38, "VDD", "VDD"),
    base.Pin(39, "GND", "GND"),
    base.Pin(40, "VDDIO", "VDDIO"),
    base.Pin(41, "VCP2", "VCP2"),
    base.Pin(42, "CP2N", "CP2N"),
    base.Pin(43, "CP2P", "CP2P"),
    base.Pin(44, "VCP1", "VCP1"),
    base.Pin(45, "CP1N", "CP1N"),
    base.Pin(46, "CP1P", "CP1P"),
    base.Pin(47, "CGH1N", None, "Reserved"),
    base.Pin(48, "CGH1P", None, "Reserved"),
    base.Pin(49, "VGH", "PREVGH"),
    base.Pin(50, "VCOMBD", "VCOMBD"),
]


# Pins 1..8 retain the DESPI-C73 cable order.  Pins 9 and 10 add the optional
# independent slave select without breaking existing eight-wire harnesses.
MCU_PINS: list[base.Pin] = [
    base.Pin(1, "3V3", "3V3"),
    base.Pin(2, "GND", "GND"),
    base.Pin(3, "SDI/SI0", "SI0"),
    base.Pin(4, "SCLK/SCL", "SCL"),
    base.Pin(5, "CSB", "CSB"),
    base.Pin(6, "D/C", "DC"),
    base.Pin(7, "RES/RST_N", "RST_N"),
    base.Pin(8, "BUSY_N", "BUSY_N"),
    base.Pin(9, "CS2 optional", "CS2"),
    base.Pin(10, "GND", "GND"),
]


PARTS_2PIN: list[base.Part2] = [
    base.Part2("C0", "C", "4.7uF/25V/0603", "V_B", "GND"),
    base.Part2("L1", "L", "15uH/3.1A SMMS0650", "V_B", "SW_H"),
    base.Part2("D1", "D_SCH", "MBR0530", "VPH", "SW_H", note="pad1/K=VPH; pad2/A=SW_H"),
    base.Part2("C2", "C", "10uF/25V/1210", "VPH", "GND"),
    base.Part2("R5", "R", "0R", "VPH", "PREVGH"),
    base.Part2("C4", "C", "10uF/25V/1210", "SW_H", "NEG_PUMP_H"),
    base.Part2("D2", "D_SCH", "MBR0530", "GND", "NEG_PUMP_H", note="pad1/K=GND; pad2/A=NEG_PUMP_H"),
    base.Part2("D3", "D_SCH", "MBR0530", "NEG_PUMP_H", "PREVGL", note="pad1/K=NEG_PUMP_H; pad2/A=PREVGL"),
    base.Part2("C5", "C", "10uF/25V/1210", "PREVGL", "GND"),
    base.Part2("R1", "R", "0.2R 0.2W 1%", "RESEH", "GND"),
    base.Part2("C22", "C", "4.7uF/25V/0603", "V_B", "GND"),
    base.Part2("L2", "L", "15uH/3.1A SMMS0650", "SW_C", "RESEC"),
    base.Part2("D4", "D_SCH", "MBR0530", "SW_C", "VPC", note="pad1/K=SW_C; pad2/A=VPC"),
    base.Part2("C6", "C", "10uF/25V/1210", "VPC", "GND"),
    base.Part2("R3", "R", "0.22R 0.2W 1%", "RESEC", "GND"),
    base.Part2("R4", "R", "0R", "3V3", "EPD_3V3"),
    base.Part2("R8", "R", "0R", "3V3", "V_B"),
    base.Part2("C23", "C", "10uF/25V/1210", "V_B", "GND"),
    base.Part2("R6", "R", "0R", "EPD_3V3", "VDD"),
    base.Part2("R7", "R", "0R", "EPD_3V3", "VDDIO"),
    base.Part2("C3", "C", "0.1uF/50V/0603", "EPD_3V3", "GND"),
    base.Part2("R9", "R", "4.7k 1%", "TSCL", "3V3"),
    base.Part2("R10", "R", "4.7k 1%", "TSDA", "3V3"),
    base.Part2("R12", "R", "0R", "GND", "BS0", note="populate: BS0 low, 4-wire"),
    base.Part2("R13", "R", "0R", "GND", "BS1", note="populate: BS1 low, 4-wire"),
    base.Part2("C13", "C", "4.7uF/10V/0805", "TFT_VCOM", "GND"),
    base.Part2("C14", "C", "0.47uF/50V/1210", "FPL_VCOM", "GND"),
    base.Part2("R2", "R", "0R", "RESEL", "GND"),
    base.Part2("C7", "C", "10uF/25V/1210", "VSH", "GND"),
    base.Part2("C8", "C", "10uF/25V/1210", "VSH_LV", "GND"),
    base.Part2("C9", "C", "10uF/25V/1210", "VSH_LV2", "GND"),
    base.Part2("C10", "C", "10uF/25V/1210", "VSL", "GND"),
    base.Part2("C11", "C", "10uF/25V/1210", "VSL_LV", "GND"),
    base.Part2("C12", "C", "10uF/25V/1210", "VSL_LV2", "GND"),
    base.Part2("C21", "C", "1uF/50V/0805", "REFN", "GND"),
    base.Part2("C20", "C", "1uF/50V/0805", "REFP", "GND"),
    base.Part2("C1", "C", "2.2uF/25V/0603", "VDDD", "GND"),
    base.Part2("C19", "C", "1uF/50V/0805", "VCP2", "GND"),
    base.Part2("C18", "C", "1uF/50V/0805", "CP2N", "CP2P"),
    base.Part2("C17", "C", "1uF/50V/0805", "VCP1", "GND"),
    base.Part2("C16", "C", "1uF/50V/0805", "CP1N", "CP1P"),
    base.Part2("C15", "C", "0.47uF/50V/1210", "VCOMBD", "GND"),
    base.Part2("R15", "R", "0R", "CSB", "SL_CSB", note="populate: cascade CS link"),
    base.Part2("R16", "R", "0R DNP", "CS2", "SL_CSB", note="fit only after removing R15"),
]


PARTS_3PIN: list[base.Part3] = [
    base.Part3(
        "Q1",
        "NMOS",
        "Si1308EDL",
        (("1", "G", "GDRH"), ("2", "S", "RESEH"), ("3", "D", "SW_H")),
        footprint=SC70_FOOTPRINT_NAME,
        note="Vishay Si1308EDL SC-70 top view: pin1=G, pin2=S, pin3=D",
    ),
    base.Part3(
        "Q2",
        "PMOS",
        "AO3401A",
        (("1", "G", "GDRC"), ("2", "S", "V_B"), ("3", "D", "SW_C")),
        footprint=SOT23_FOOTPRINT_NAME,
        note="SOT-23: pin1=G, pin2=S, pin3=D",
    ),
]


TESTPOINT_NETS = ["3V3", "GND", "VPH", "PREVGH", "PREVGL", "VPC", "VDDIO", "CSB", "SL_CSB", "BUSY_N"]


SCHEMATIC_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PROJECT}/root-sheet"))
SCHEMATIC_REFS = ["J1", "J2"] + [part.ref for part in PARTS_2PIN] + [part.ref for part in PARTS_3PIN]
SCHEMATIC_REFS += [f"TP{idx}" for idx in range(1, len(TESTPOINT_NETS) + 1)]
SYMBOL_UUIDS = {
    ref: str(uuid.uuid5(uuid.NAMESPACE_URL, f"{PROJECT}/symbol/{ref}")) for ref in SCHEMATIC_REFS
}


def production_symbol_instance(
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    pins: list[str],
    dnp: bool = False,
) -> str:
    """Create a symbol whose UUID is also used by its PCB footprint path."""
    sid = SYMBOL_UUIDS[ref]
    lines = [
        "\t(symbol",
        f'\t\t(lib_id "{base.q(lib_id)}")',
        f"\t\t(at {x:.2f} {y:.2f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        f"\t\t(in_bom {'no' if ref.startswith('TP') else 'yes'})",
        "\t\t(on_board yes)",
        f"\t\t(dnp {'yes' if dnp else 'no'})",
        f'\t\t(uuid "{sid}")',
        base.prop("Reference", ref, x, y - 4.0),
        base.prop("Value", value, x, y + 3.5),
        base.prop("Footprint", footprint, x, y, True),
        base.prop("Datasheet", "", x, y, True),
        base.prop("Description", "", x, y, True),
    ]
    for pin in pins:
        lines += [f'\t\t(pin "{pin}"', f'\t\t\t(uuid "{base.uid()}")', "\t\t)"]
    lines += [
        "\t\t(instances",
        f'\t\t\t(project "{PROJECT}"',
        f'\t\t\t\t(path "/{SCHEMATIC_UUID}"',
        f'\t\t\t\t\t(reference "{ref}")',
        "\t\t\t\t\t(unit 1)",
        "\t\t\t\t)",
        "\t\t\t)",
        "\t\t)",
        "\t)",
    ]
    return "\n".join(lines)


def footprint_name_for_part2(part: base.Part2) -> str:
    if part.kind == "L":
        return INDUCTOR_FOOTPRINT_NAME
    return _ORIGINAL_FOOTPRINT_NAME_FOR_PART2(part)


def footprint_path_for_part2(part: base.Part2) -> Path:
    if part.kind == "L":
        return INDUCTOR_FOOTPRINT
    return _ORIGINAL_FOOTPRINT_PATH_FOR_PART2(part)


def production_patch_footprint(
    source: Path,
    footprint_id: str,
    ref: str,
    value: str,
    at_x: float,
    at_y: float,
    rot: float,
    pad_nets: dict[str, str],
) -> str:
    # Schematic linkage is applied through pcbnew after the text board loads.
    # KiCad 10 rejects hand-injected legacy ``(path ...)`` tokens in a board
    # using the 2024 UUID-based footprint syntax.
    effective_nets = dict(pad_nets)
    if ref == "J1":
        for pin in FPC_PINS:
            if pin.net is None:
                effective_nets[str(pin.number)] = f"unconnected-(J1-{pin.name}-Pad{pin.number})"
    text = _ORIGINAL_PATCH_FOOTPRINT(source, footprint_id, ref, value, at_x, at_y, rot, effective_nets)
    for net_name, net_code in base.NETS.items():
        if net_name.startswith("unconnected-"):
            continue
        text = text.replace(f'(net {net_code} "{net_name}")', f'(net {net_code} "/{net_name}")')
    return text


def make_fpc_footprint() -> str:
    """Return the official JLC/EasyEDA C2856838 land pattern in KiCad form.

    EasyEDA's source geometry is in 10 mil units.  It resolves to 0.30 x
    1.20 mm signal pads at 0.50 mm pitch, 2.00 x 1.80 mm hold-down pads,
    and a 28.50 x 4.90 mm body.  Pin 1 is at +X in top view.
    """
    lines = [
        f'(footprint "{FPC_FOOTPRINT_NAME.split(":", 1)[1]}"',
        "\t(version 20260206)",
        '\t(generator "pcbnew")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        '\t(descr "XUNPU FPC-05FB-50PH20, C2856838, 50 pin, 0.5 mm pitch, 0.3 mm FPC, dual contact")',
        '\t(tags "XUNPU C2856838 dual contact 50 pin FPC")',
        '\t(property "Reference" "REF**" (at 0 -4.0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
        '\t(property "Value" "FPC-05FB-50PH20" (at 0 5.1 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
        "\t(attr smd)",
        '\t(fp_line (start -14.25 -1.38) (end -14.25 0.45) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        '\t(fp_line (start -14.25 2.80) (end -14.25 3.53) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        '\t(fp_line (start -14.25 3.53) (end 14.25 3.53) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        '\t(fp_line (start 14.25 3.53) (end 14.25 2.80) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        '\t(fp_line (start 14.25 0.45) (end 14.25 -1.38) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))',
        '\t(fp_rect (start -15.00 -2.40) (end 15.00 4.10) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
        '\t(fp_rect (start -14.25 -1.38) (end 14.25 3.53) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
        '\t(fp_poly (pts (xy 11.85 -2.55) (xy 12.25 -3.15) (xy 12.65 -2.55)) (stroke (width 0.1) (type solid)) (fill solid) (layer "F.SilkS"))',
    ]
    for number in range(1, 51):
        x = 12.25 - (number - 1) * 0.5
        lines.extend(
            [
                f'\t(pad "{number}" smd rect',
                f"\t\t(at {x:.2f} -1.625)",
                "\t\t(size 0.30 1.20)",
                '\t\t(layers "F.Cu" "F.Mask" "F.Paste")',
                "\t)",
            ]
        )
    lines.extend(
        [
            '\t(pad "MP1" smd rect (at -13.80 1.625) (size 2.00 1.80) (layers "F.Cu" "F.Mask" "F.Paste"))',
            '\t(pad "MP2" smd rect (at 13.80 1.625) (size 2.00 1.80) (layers "F.Cu" "F.Mask" "F.Paste"))',
            "\t(embedded_fonts no)",
            ")",
        ]
    )
    return "\n".join(lines) + "\n"


def make_inductor_footprint() -> str:
    """Return the official JLC/EasyEDA C149585 SMMS0650 land pattern."""
    return """(footprint "SXN_SMMS0650_7.1x6.6mm"
\t(version 20260206)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(layer "F.Cu")
\t(descr "SXN SMMS0650-150M C149585; official 7.1 x 6.6 mm land pattern")
\t(tags "SMMS0650 C149585 15uH")
\t(property "Reference" "REF**" (at 0 -4.25 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
\t(property "Value" "SMMS0650-150M" (at 0 4.25 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
\t(attr smd)
\t(fp_line (start -3.55 -3.30) (end 3.55 -3.30) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_line (start 3.55 -3.30) (end 3.55 -2.05) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_line (start 3.55 2.05) (end 3.55 3.30) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_line (start 3.55 3.30) (end -3.55 3.30) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_line (start -3.55 3.30) (end -3.55 2.05) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_line (start -3.55 -2.05) (end -3.55 -3.30) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
\t(fp_rect (start -4.45 -3.65) (end 4.45 3.65) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
\t(fp_rect (start -3.55 -3.30) (end 3.55 3.30) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))
\t(pad "1" smd rect
\t\t(at -3.025 0)
\t\t(size 2.35 3.50)
\t\t(layers "F.Cu" "F.Mask" "F.Paste")
\t)
\t(pad "2" smd rect
\t\t(at 3.025 0)
\t\t(size 2.35 3.50)
\t\t(layers "F.Cu" "F.Mask" "F.Paste")
\t)
\t(embedded_fonts no)
)
"""


def fet_symbol(name: str, footprint: str) -> str:
    # Both selected MOSFETs use the standard 1=G, 2=S, 3=D pin order.
    pins = [
        '\t\t\t\t(pin input line (at -5.08 0 0) (length 2.54) (name "G") (number "1"))',
        '\t\t\t\t(pin passive line (at 5.08 -2.54 180) (length 2.54) (name "S") (number "2"))',
        '\t\t\t\t(pin passive line (at 5.08 2.54 180) (length 2.54) (name "D") (number "3"))',
    ]
    return "\n".join(
        [
            f'\t\t(symbol "Local:{name}"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            f'\t\t\t(property "Reference" "Q" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Value" "{name}" (at 0 5.08 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'\t\t\t(symbol "{name}_0_1"',
            "\t\t\t\t(rectangle (start -2.54 -3.81) (end 2.54 3.81) (stroke (width 0.2) (type default)) (fill (type none)))",
            "\t\t\t)",
            f'\t\t\t(symbol "{name}_1_1"',
            *pins,
            "\t\t\t)",
            "\t\t)",
        ]
    )


def local_symbol_defs() -> list[str]:
    return [
        base.symbol_lib_connector("MF1750_FPC50", FPC_PINS, 25, FPC_FOOTPRINT_NAME),
        base.symbol_lib_connector("ESP32_SPI_10PIN", MCU_PINS, 10, base.MCU_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("R", "R", base.R_0603_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("C", "C", base.C_0603_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("L", "L", INDUCTOR_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("D_SCH", "D", base.D_SOD123_FOOTPRINT_NAME, "K", "A"),
        fet_symbol("NMOS", SC70_FOOTPRINT_NAME),
        fet_symbol("PMOS", SOT23_FOOTPRINT_NAME),
        base.symbol_lib_testpoint(),
    ]


def footprint_name_for_part3(part: base.Part3) -> str:
    return SC70_FOOTPRINT_NAME if part.ref == "Q1" else SOT23_FOOTPRINT_NAME


def footprint_path_for_part3(part: base.Part3) -> Path:
    return SC70_FOOTPRINT if part.ref == "Q1" else SOT23_FOOTPRINT


def place_part3(lines: list[str], part: base.Part3, x: float, y: float) -> None:
    x = base.grid(x)
    y = base.grid(y)
    lines.append(
        base.symbol_instance(
            f"Local:{part.kind}", part.ref, part.value, footprint_name_for_part3(part), x, y, [p for p, _, _ in part.pins]
        )
    )
    points = {"1": (x - 5.08, y, "left"), "2": (x + 5.08, y + 2.54, "right"), "3": (x + 5.08, y - 2.54, "right")}
    for pin_num, _pin_name, net in part.pins:
        px, py, side = points[pin_num]
        base.connect_pin_to_label(lines, px, py, net, side)
    lines.append(base.text_note(part.note, x - 9.0, y + 8.0, 0.85))


def patch_base_globals() -> None:
    base.OUT = OUT
    base.PROJECT = PROJECT
    base.FPC_FOOTPRINT = FPC_FOOTPRINT
    base.FPC_FOOTPRINT_NAME = FPC_FOOTPRINT_NAME
    base.FPC_PINS = FPC_PINS
    base.MCU_PINS = MCU_PINS
    base.PARTS_2PIN = PARTS_2PIN
    base.PARTS_3PIN = PARTS_3PIN
    base.TESTPOINT_NETS = TESTPOINT_NETS
    base.RESERVED_TEST_NETS = []
    base.symbol_instance = production_symbol_instance
    base.footprint_name_for_part2 = footprint_name_for_part2
    base.footprint_path_for_part2 = footprint_path_for_part2
    base.footprint_name_for_part3 = footprint_name_for_part3
    base.footprint_path_for_part3 = footprint_path_for_part3
    base.local_symbol_defs = local_symbol_defs
    base.place_part3 = place_part3
    base.patch_footprint = production_patch_footprint
    base.NETS = base.all_nets()
    for pin in FPC_PINS:
        if pin.net is None:
            name = f"unconnected-(J1-{pin.name}-Pad{pin.number})"
            base.NETS[name] = len(base.NETS) + 1


PART_POSITIONS: dict[str, tuple[float, float, float]] = {
    "C13": (13.0, 11.5, 270), "C14": (17.0, 11.5, 270), "R2": (21.0, 11.5, 270),
    # FPC bias pins 15..20 fan out monotonically from left to right.
    "C7": (25.0, 14.0, 270), "C8": (29.0, 14.0, 270), "C9": (33.0, 14.0, 270),
    "C10": (37.0, 14.0, 270), "C11": (41.0, 14.0, 270), "C12": (45.0, 14.0, 270),
    # Reference, touch and bootstrap configuration follow the same ordering.
    "C21": (33.0, 22.0, 270), "C20": (37.0, 22.0, 270),
    "R9": (27.0, 20.0, 270), "R10": (29.0, 20.0, 270),
    # BS0/BS1 straps continue the first row to the right of the bias capacitors.
    "R12": (47.0, 18.0, 0), "R13": (50.0, 18.0, 0),
    # Charge-pump pins 37..50 stay directly below their doubled-pitch escapes.
    "C1": (48.0, 10.0, 270), "C19": (49.0, 5.0, 270), "C18": (42.7, 1.0, 0),
    "C17": (52.0, 5.0, 270), "C16": (46.3, 1.0, 0), "C15": (56.0, 5.0, 270),
    "R15": (70.0, 40.0, 0), "R16": (74.0, 40.0, 0),
    "C0": (6.0, 31.0, 180), "L1": (13.0, 31.0, 0), "D1": (25.0, 31.0, 180),
    "C2": (31.0, 31.0, 0), "R5": (35.5, 31.0, 90), "C4": (24.0, 37.0, 0),
    "D2": (29.0, 37.0, 180), "D3": (35.0, 37.0, 0), "C5": (40.0, 40.0, 0),
    "R1": (19.35, 38.0, 270), "C22": (42.0, 35.0, 180), "L2": (53.0, 39.0, 0),
    "D4": (57.5, 34.0, 0), "C6": (65.0, 34.0, 0), "R3": (56.0, 45.0, 270),
    "R4": (7.0, 51.0, 0), "R8": (11.0, 51.0, 0), "C23": (16.0, 51.0, 0),
    "R6": (22.0, 51.0, 0), "R7": (26.0, 51.0, 0), "C3": (30.0, 51.0, 0),
}

Q_POSITIONS = {"Q1": (20.0, 33.5, 90), "Q2": (46.0, 39.0, 0)}
TP_POSITIONS = {
    "TP1": (4.5, 55.5, 0), "TP2": (9.0, 55.5, 0), "TP3": (27.0, 27.0, 0),
    "TP4": (38.0, 33.0, 0), "TP5": (36.0, 42.0, 0), "TP6": (70.0, 33.0, 0),
    "TP7": (31.0, 55.5, 0), "TP8": (36.0, 55.5, 0), "TP9": (41.0, 55.5, 0),
    "TP10": (76.0, 45.0, 0),
}

# Keep a component-free fanout field below the 0.5 mm-pitch FPC.  The routing
# stage expands the connector to a 1.0 mm-pitch via row before entering the
# component area, so every non-connector footprint is shifted together.
FANOUT_FIELD_SHIFT_Y = 15.0
PART_POSITIONS = {
    ref: (x, y + FANOUT_FIELD_SHIFT_Y, rotation)
    for ref, (x, y, rotation) in PART_POSITIONS.items()
}
Q_POSITIONS = {
    ref: (x, y + FANOUT_FIELD_SHIFT_Y, rotation)
    for ref, (x, y, rotation) in Q_POSITIONS.items()
}
TP_POSITIONS = {
    ref: (x, y + FANOUT_FIELD_SHIFT_Y, rotation)
    for ref, (x, y, rotation) in TP_POSITIONS.items()
}


def mark_dnp(footprint_text: str, dnp: bool) -> str:
    if not dnp:
        return footprint_text
    return footprint_text.replace("(attr smd)", "(attr smd dnp)", 1)


def make_board_unrouted() -> str:
    nets = ['\t(net 0 "")'] + [
        f'\t(net {idx} "{name if name.startswith("unconnected-") else "/" + name}")'
        for name, idx in sorted(base.NETS.items(), key=lambda x: x[1])
    ]
    footprints: list[str] = []
    footprints.append(
        base.patch_footprint(
            FPC_FOOTPRINT, FPC_FOOTPRINT_NAME, "J1", "FPC-05FB-50PH20", 35.0, 5.0, 180,
            {str(pin.number): pin.net for pin in FPC_PINS if pin.net},
        )
    )
    footprints.append(
        base.patch_footprint(
            base.MCU_FOOTPRINT, base.MCU_FOOTPRINT_NAME, "J2", "HOST_10PIN_C73_COMPAT", 76.0, 27.0, 0,
            {str(pin.number): pin.net for pin in MCU_PINS if pin.net},
        )
    )
    for part in PARTS_2PIN:
        text = base.patch_footprint(
            base.footprint_path_for_part2(part), base.footprint_name_for_part2(part), part.ref, part.value,
            *PART_POSITIONS[part.ref], {"1": part.net1, "2": part.net2},
        )
        footprints.append(mark_dnp(text, "DNP" in part.value or part.value == "NC"))
    for part in PARTS_3PIN:
        x, y, rot = Q_POSITIONS[part.ref]
        footprints.append(
            base.patch_footprint(
                footprint_path_for_part3(part), footprint_name_for_part3(part), part.ref, part.value, x, y, rot,
                {number: net for number, _name, net in part.pins},
            )
        )
    for idx, net in enumerate(TESTPOINT_NETS, start=1):
        ref = f"TP{idx}"
        footprints.append(
            base.patch_footprint(
                base.TP_FOOTPRINT, base.TP_FOOTPRINT_NAME, ref, net, *TP_POSITIONS[ref], {"1": net},
            )
        )
    for ref, x, y in [("H1", 3.5, 3.5), ("H2", 76.5, 71.5)]:
        mounting = base.patch_footprint(MOUNTING_HOLE, "MountingHole:MountingHole_2.5mm", ref, "M2.5_NPTH", x, y, 0, {})
        mounting = mounting.replace("(attr exclude_from_pos_files exclude_from_bom)", "(attr board_only exclude_from_pos_files exclude_from_bom)")
        footprints.append(mounting)

    return (
        "(kicad_pcb\n"
        "\t(version 20241229)\n"
        '\t(generator "pcbnew")\n'
        '\t(generator_version "10.0")\n'
        "\t(general (thickness 1.6) (legacy_teardrops no))\n"
        '\t(paper "A4")\n'
        "\t(layers\n"
        '\t\t(0 "F.Cu" signal)\n\t\t(2 "B.Cu" signal)\n\t\t(5 "F.SilkS" user "Top Silkscreen")\n\t\t(7 "B.SilkS" user "Bottom Silkscreen")\n'
        '\t\t(1 "F.Mask" user)\n\t\t(3 "B.Mask" user)\n\t\t(25 "Edge.Cuts" user)\n'
        '\t\t(31 "F.CrtYd" user)\n\t\t(29 "B.CrtYd" user)\n\t\t(35 "F.Fab" user)\n\t\t(33 "B.Fab" user)\n\t)\n'
        "\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))\n"
        + "\n".join(nets) + "\n"
        + '\t(gr_rect (start 0 0) (end 80 75) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts"))\n'
        + '\t(gr_text "MF1750 REV A1" (at 20 73.5 0) (layer "F.SilkS") (effects (font (size 1.0 1.0) (thickness 0.15))))\n'
        + '\t(gr_text "PIN1 >" (at 19 8.3 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        + '\t(gr_text "FPC ENTRY" (at 35 0.8 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        + '\t(gr_text "R15 LINK / R16 CS2" (at 60 73.5 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        + '\t(gr_text "DO NOT FIT R15 + R16" (at 40 72.0 0) (layer "B.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))\n'
        + "\n".join(footprints) + "\n)\n"
    )


def make_schematic() -> str:
    text = base.make_schematic()
    # The top-level sheet UUID is the instance path shared by every symbol;
    # each PCB footprint path points to that symbol's own UUID.
    text = re.sub(
        r'(^\(kicad_sch\s+\(version [^)]+\)\s+\(generator "[^"]+"\)\s+'
        r'\(generator_version "[^"]+"\)\s+\(uuid ")[^"]+',
        rf'\g<1>{SCHEMATIC_UUID}',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    replacements = {
        "MF-1750 / M009F-T Full 50-pin Driver - Reference Schematic Draft": "MF-1750 / M009F-T Cascade Driver Rev A1",
        "Generated in ESP32_C73 workspace": "Production prototype - MF-1750 A1 reference circuit",
        "Critical fix versus DESPI-C73: J1 pin 4 is SL_CSB and must route to an ESP32 GPIO as CS2.":
            "J1 pin4 SL_CSB is linked to CSB by R15; remove R15 and fit R16 for independent CS2.",
        "Footprints are intentionally mostly blank; assign real packages and ratings in KiCad before layout.":
            "Footprints and voltage ratings are assigned for the Rev A production prototype.",
        "After board bring-up, firmware should enable EPD_PIN_CS2 and drive both CSB and SL_CSB for full 1024x600 refresh.":
            "Default firmware uses one CS with R15 fitted; independent CS2 is an optional bring-up configuration.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace('(property "Value" "MF-1750 50pin FPC"', '(property "Value" "FPC-05FB-50PH20"')
    text = text.replace('(property "Value" "ESP32 SPI 10pin"', '(property "Value" "HOST_10PIN_C73_COMPAT"')
    return text


def make_footprint_table() -> str:
    return (
        "(fp_lib_table\n"
        '\t(lib (name "MF1750_Production") (type "KiCad") (uri "${KIPRJMOD}/MF1750_Production.pretty") '
        '(options "") (descr "MF-1750 production local footprints"))\n'
        ")\n"
    )


def make_reference_bom() -> str:
    rows = [["Designator", "Value", "Footprint", "LCSC Part #", "Manufacturer", "MPN", "DNP", "Note"]]
    rows += [
        ["J1", "50pin 0.5mm dual-contact FPC", FPC_FOOTPRINT_NAME, "C2856838", "XUNPU", "FPC-05FB-50PH20", "No", "Official JLC footprint; pin1 left in assembled-board top view"],
        ["J2", "1x10 2.54mm header", base.MCU_FOOTPRINT_NAME, "", "Generic", "1x10 P2.54", "Manual", "First 8 pins C73-compatible"],
    ]
    part2_codes = {
        "C0": ("C69335", "SAMSUNG", "CL10A475KA8NQNC"),
        "C22": ("C69335", "SAMSUNG", "CL10A475KA8NQNC"),
        "C1": ("C415535", "Murata", "GRM188Z71E225KE43D"),
        "C3": ("C14663", "YAGEO", "CC0603KRX7R9BB104"),
        "C13": ("C87998", "SAMSUNG", "CL21B475KPFNNNE"),
        "C14": ("C309505", "YAGEO", "CC1210KKX7R9BB474"),
        "C15": ("C309505", "YAGEO", "CC1210KKX7R9BB474"),
        "L1": ("C149585", "SXN", "SMMS0650-150M"),
        "L2": ("C149585", "SXN", "SMMS0650-150M"),
        "D1": ("C77336", "JSCJ", "MBR0530"),
        "D2": ("C77336", "JSCJ", "MBR0530"),
        "D3": ("C77336", "JSCJ", "MBR0530"),
        "D4": ("C77336", "JSCJ", "MBR0530"),
        "R1": ("C2907350", "FOJAN", "FRL1206FR200TS"),
        "R3": ("C3017221", "VO", "SCR1206FR220"),
        "R9": ("C23162", "UNI-ROYAL", "0603WAF4701T5E"),
        "R10": ("C23162", "UNI-ROYAL", "0603WAF4701T5E"),
    }
    for ref in ["C2", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C23"]:
        part2_codes[ref] = ("C2909422", "Walsin", "1210B106K250CT")
    for ref in ["C16", "C17", "C18", "C19", "C20", "C21"]:
        part2_codes[ref] = ("C28323", "SAMSUNG", "CL21B105KBFNNNE")
    for ref in ["R2", "R4", "R5", "R6", "R7", "R8", "R12", "R13", "R15", "R16"]:
        part2_codes[ref] = ("C21189", "UNI-ROYAL", "0603WAF0000T5E")
    for part in PARTS_2PIN:
        lcsc, manufacturer, mpn = part2_codes.get(part.ref, ("", "", ""))
        rows.append([
            part.ref, part.value, base.footprint_name_for_part2(part), lcsc, manufacturer, mpn,
            "Yes" if ("DNP" in part.value or part.value == "NC") else "No", part.note,
        ])
    for part in PARTS_3PIN:
        if part.ref == "Q1":
            lcsc, manufacturer, mpn = "C3289597", "Vishay", "SI1308EDL-T1-BE3"
            note = part.note + "; reference-selected part, RDS(on) is a controlled A1 numerical deviation"
        else:
            lcsc, manufacturer, mpn = "C15127", "AOS", "AO3401A"
            note = part.note
        rows.append([part.ref, part.value, footprint_name_for_part3(part), lcsc, manufacturer, mpn, "No", note])
    for idx, net in enumerate(TESTPOINT_NETS, start=1):
        rows.append([f"TP{idx}", net, base.TP_FOOTPRINT_NAME, "", "", "", "Manual", "test pad only"])
    rows.append(["H1,H2", "M2.5 NPTH", "MountingHole:MountingHole_2.5mm", "", "", "", "Manual", "mechanical"])
    from io import StringIO

    stream = StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue()


def make_readme() -> str:
    return """# MF-1750 Cascade Driver Rev A1

This directory is generated from `../generate_mf1750_production_v1.py`,
`../prepare_mf1750_freerouting_seed.py`, Freerouting 2.2.4, and
`../finalize_mf1750_freerouting.py`. The checked-in `production/` directory is
the verified manufacturing handoff; regeneration is only needed after edits.

Design baseline:

- MF-1750 / M009F-T A1 reference circuit, page 10.
- 80 mm x 75 mm, 2-layer, 1.6 mm FR-4, 1 oz copper.
- J1 is XUNPU FPC-05FB-50PH20 / C2856838 (50 pin, 0.5 mm, 0.3 mm,
  dual-contact). Its footprint is reconstructed from the official JLC land
  pattern and the manufacturer drawing. It is rotated so the cable exits the
  top board edge and panel pin 1 is at the PCB's left-hand PIN1 marker.
- Host pins 1..8 retain the DESPI-C73 order; pin 9 is optional CS2 and pin 10 is GND.
- R15 is fitted by default and links CSB to SL_CSB, matching the E2802 cascade
  board's J4 link. For independent CS2, remove R15 and fit R16. Never fit both.
- R12/R13 fix BS0=BS1=0 (4-wire SPI per the MF-1750 interface table).

Important first-article checks:

1. Confirm panel flex pin 1 against the board's PIN1 silkscreen before insertion.
2. Power the board from a current-limited 3.3 V supply; start at 100 mA.
3. Check VDD/VDDIO before allowing a refresh, then verify VPH/PREVGH/PREVGL/VPC.
4. Use the default R15 single-CS configuration first. Only test CS2 after the
   single-CS cascade path has been measured.
5. J2 is intentionally through-hole/manual assembly; all SMT DNP parts are
   excluded from the normal placement file.
6. Q1 uses the official Si1308EDL SC-70 pinout (1=G, 2=S, 3=D). Its
   specified 2.5 V RDS(on) is a documented deviation from one numerical limit
   in the A1 component note, so verify switching temperature on first articles.

`production/` is populated by the routing/export script with Gerber, drill,
BOM, CPL, reports, and an order checklist.
"""


def main() -> None:
    patch_base_globals()
    OUT.mkdir(parents=True, exist_ok=True)
    FPC_LIB_DIR.mkdir(parents=True, exist_ok=True)
    FPC_FOOTPRINT.write_text(make_fpc_footprint(), encoding="utf-8")
    INDUCTOR_FOOTPRINT.write_text(make_inductor_footprint(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_pro").write_text(base.make_project(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(base.make_sym_lib_table(), encoding="utf-8")
    (OUT / "fp-lib-table").write_text(make_footprint_table(), encoding="utf-8")
    (OUT / "mf1750_local.kicad_sym").write_text(base.make_local_symbol_lib(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_sch").write_text(make_schematic(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_pcb").write_text(make_board_unrouted(), encoding="utf-8")
    (OUT / "bom_reference.csv").write_text(make_reference_bom(), encoding="utf-8")
    (OUT / "mf1750_fpc_pinmap.csv").write_text(base.make_pinmap(), encoding="utf-8")
    (OUT / "README.md").write_text(make_readme(), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
