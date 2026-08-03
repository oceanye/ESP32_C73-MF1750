from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware" / "mf1750_full_driver_kicad"
KICAD = Path(r"C:\Program Files\KiCad\10.0\share\kicad")
PROJECT = "mf1750_full_driver"
GRID = 2.54

FPC_FOOTPRINT = KICAD / "footprints" / "Connector_FFC-FPC.pretty" / (
    "Hirose_FH12-50S-0.5SH_1x50-1MP_P0.50mm_Horizontal.kicad_mod"
)
MCU_FOOTPRINT = KICAD / "footprints" / "Connector_PinHeader_2.54mm.pretty" / (
    "PinHeader_1x10_P2.54mm_Vertical.kicad_mod"
)
R_0603_FOOTPRINT = KICAD / "footprints" / "Resistor_SMD.pretty" / "R_0603_1608Metric.kicad_mod"
R_1206_FOOTPRINT = KICAD / "footprints" / "Resistor_SMD.pretty" / "R_1206_3216Metric.kicad_mod"
C_0603_FOOTPRINT = KICAD / "footprints" / "Capacitor_SMD.pretty" / "C_0603_1608Metric.kicad_mod"
C_0805_FOOTPRINT = KICAD / "footprints" / "Capacitor_SMD.pretty" / "C_0805_2012Metric.kicad_mod"
C_1210_FOOTPRINT = KICAD / "footprints" / "Capacitor_SMD.pretty" / "C_1210_3225Metric.kicad_mod"
D_SOD123_FOOTPRINT = KICAD / "footprints" / "Diode_SMD.pretty" / "D_SOD-123.kicad_mod"
SOT23_FOOTPRINT = KICAD / "footprints" / "Package_TO_SOT_SMD.pretty" / "SOT-23-3.kicad_mod"
L_7X7_FOOTPRINT = KICAD / "footprints" / "Inductor_SMD.pretty" / "L_7.3x7.3_H4.5.kicad_mod"
TP_FOOTPRINT = KICAD / "footprints" / "TestPoint.pretty" / "TestPoint_Pad_D1.0mm.kicad_mod"

FPC_FOOTPRINT_NAME = "Connector_FFC-FPC:Hirose_FH12-50S-0.5SH_1x50-1MP_P0.50mm_Horizontal"
MCU_FOOTPRINT_NAME = "Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical"
R_0603_FOOTPRINT_NAME = "Resistor_SMD:R_0603_1608Metric"
R_1206_FOOTPRINT_NAME = "Resistor_SMD:R_1206_3216Metric"
C_0603_FOOTPRINT_NAME = "Capacitor_SMD:C_0603_1608Metric"
C_0805_FOOTPRINT_NAME = "Capacitor_SMD:C_0805_2012Metric"
C_1210_FOOTPRINT_NAME = "Capacitor_SMD:C_1210_3225Metric"
D_SOD123_FOOTPRINT_NAME = "Diode_SMD:D_SOD-123"
SOT23_FOOTPRINT_NAME = "Package_TO_SOT_SMD:SOT-23-3"
L_7X7_FOOTPRINT_NAME = "Inductor_SMD:L_7.3x7.3_H4.5"
TP_FOOTPRINT_NAME = "TestPoint:TestPoint_Pad_D1.0mm"


@dataclass(frozen=True)
class Pin:
    number: int
    name: str
    net: str | None
    note: str = ""


@dataclass(frozen=True)
class Part2:
    ref: str
    kind: str
    value: str
    net1: str
    net2: str
    footprint: str = ""
    note: str = ""


@dataclass(frozen=True)
class Part3:
    ref: str
    kind: str
    value: str
    pins: tuple[tuple[str, str, str], ...]  # pin number, pin name, net
    footprint: str = ""
    note: str = ""


def uid() -> str:
    return str(uuid.uuid4())


def q(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def grid(value: float) -> float:
    return round(value / GRID) * GRID


FPC_PINS: list[Pin] = [
    Pin(1, "NC", None, "No connect; do not tie to other NC pins"),
    Pin(2, "TFT_VCOM", "TFT_VCOM"),
    Pin(3, "FPL_VCOM", "FPL_VCOM"),
    Pin(4, "SL_CSB", "SL_CSB", "Second SPD1657B chip-select; missing on DESPI-C73"),
    Pin(5, "GDRH", "GDRH"),
    Pin(6, "RESEH", "RESEH"),
    Pin(7, "GDRL", "GDRL", "Reserved; route only to isolated optional test pad"),
    Pin(8, "RESEL", "RESEL", "0-ohm to GND through R2"),
    Pin(9, "GDRC", "GDRC"),
    Pin(10, "RESEC", "RESEC"),
    Pin(11, "VPC", "VPC"),
    Pin(12, "GND", "GND"),
    Pin(13, "VGL", "PREVGL", "Reference labels this rail PREVGL"),
    Pin(14, "VPH", "VPH"),
    Pin(15, "VSH", "VSH"),
    Pin(16, "VSH_LV", "VSH_LV"),
    Pin(17, "VSH_LV2", "VSH_LV2"),
    Pin(18, "VSL", "VSL"),
    Pin(19, "VSL_LV", "VSL_LV"),
    Pin(20, "VSL_LV2", "VSL_LV2"),
    Pin(21, "GNDA", "GND"),
    Pin(22, "REFN", "REFN"),
    Pin(23, "REFP", "REFP"),
    Pin(24, "TSCL", "TSCL"),
    Pin(25, "TSDA", "TSDA"),
    Pin(26, "BS0", "BS0"),
    Pin(27, "BS1", "BS1"),
    Pin(28, "RST_N", "RST_N"),
    Pin(29, "BUSY_N", "BUSY_N"),
    Pin(30, "DC", "DC"),
    Pin(31, "CSB", "CSB"),
    Pin(32, "SCL", "SCL"),
    Pin(33, "SI0", "SI0"),
    Pin(34, "SI1", "SI1", "Reserved in 4-wire SPI; optional isolated test pad"),
    Pin(35, "SI2", "SI2", "Reserved in 4-wire SPI; optional isolated test pad"),
    Pin(36, "SI3", "SI3", "Reserved in 4-wire SPI; optional isolated test pad"),
    Pin(37, "VDDD", "VDDD"),
    Pin(38, "VDD", "VDD"),
    Pin(39, "GND", "GND"),
    Pin(40, "VDDIO", "VDDIO"),
    Pin(41, "VCP2", "VCP2"),
    Pin(42, "CP2N", "CP2N"),
    Pin(43, "CP2P", "CP2P"),
    Pin(44, "VCP1", "VCP1"),
    Pin(45, "CP1N", "CP1N"),
    Pin(46, "CP1P", "CP1P"),
    Pin(47, "CGH1N", "CGH1N", "Charge pump reserved; optional isolated test pad"),
    Pin(48, "CGH1P", "CGH1P", "Charge pump reserved; optional isolated test pad"),
    Pin(49, "VGH", "PREVGH", "Reference labels this rail PREVGH"),
    Pin(50, "VCOMBD", "VCOMBD"),
]

MCU_PINS: list[Pin] = [
    Pin(1, "3V3", "3V3"),
    Pin(2, "GND", "GND"),
    Pin(3, "SDI/SI0", "SI0"),
    Pin(4, "SCLK/SCL", "SCL"),
    Pin(5, "CSB", "CSB"),
    Pin(6, "SL_CSB", "SL_CSB"),
    Pin(7, "D/C", "DC"),
    Pin(8, "RES/RST_N", "RST_N"),
    Pin(9, "BUSY_N", "BUSY_N"),
    Pin(10, "GND", "GND"),
]


PARTS_2PIN: list[Part2] = [
    # High-voltage boost and charge-pump section.
    Part2("C0", "C", "4.7uF/25V/0603", "V_B", "GND", note="Local V_B input cap near L1"),
    Part2("L1", "L", "15uH 2A", "V_B", "SW_H", note="High-side boost inductor"),
    Part2("D1", "D_SCH", "MBR0530", "VPH", "SW_H", note="Polarity: pad1/K=VPH, pad2/A=SW_H"),
    Part2("C2", "C", "10uF/25V/1210", "VPH", "GND"),
    Part2("R5", "R", "0R", "VPH", "PREVGH"),
    Part2("C4", "C", "10uF/25V/1210", "SW_H", "NEG_PUMP_H"),
    Part2("D2", "D_SCH", "MBR0530", "NEG_PUMP_H", "GND", note="Polarity: pad1/K=NEG_PUMP_H, pad2/A=GND"),
    Part2("D3", "D_SCH", "MBR0530", "NEG_PUMP_H", "PREVGL", note="Polarity: pad1/K=NEG_PUMP_H, pad2/A=PREVGL"),
    Part2("C5", "C", "10uF/25V/1210", "PREVGL", "GND"),
    Part2("R1", "R", "0.2R 0.2W 1%", "RESEH", "GND"),
    # PMOS / VPC section.
    Part2("C22", "C", "4.7uF/25V/0603", "V_B", "GND", note="Local V_B input cap near Q2"),
    Part2("L2", "L", "15uH 2A", "SW_C", "RESEC"),
    Part2("D4", "D_SCH", "MBR0530", "SW_C", "VPC", note="Polarity: pad1/K=SW_C, pad2/A=VPC"),
    Part2("C6", "C", "10uF/25V/1210", "VPC", "GND"),
    Part2("R3", "R", "0.22R 0.2W 1%", "RESEC", "GND"),
    # Logic/power rails.
    Part2("R4", "R", "0R", "3V3", "EPD_3V3"),
    Part2("R8", "R", "0R", "3V3", "V_B"),
    Part2("C23", "C", "10uF/25V/1210", "V_B", "GND"),
    Part2("R6", "R", "0R", "EPD_3V3", "VDD"),
    Part2("R7", "R", "0R", "EPD_3V3", "VDDIO"),
    Part2("C3", "C", "0.1uF/25V/0603", "EPD_3V3", "GND"),
    # Cascade pull-ups from the MF-1750 reference.
    Part2("R9", "R", "4.7k 0.1W 1%", "TSCL", "3V3"),
    Part2("R10", "R", "4.7k 0.1W 1%", "TSDA", "3V3"),
    # BS mode: 4-wire SPI default, BS0=0 and BS1=0.
    Part2("R11", "R", "NC", "VDD", "BS0", note="DNP in 4-wire SPI default"),
    Part2("R12", "R", "0R", "GND", "BS0", note="Populate for 4-wire SPI default"),
    Part2("R14", "R", "NC", "VDD", "BS1", note="DNP in 4-wire SPI default"),
    Part2("R13", "R", "0R", "GND", "BS1", note="Populate for 4-wire SPI default"),
    # FPC decoupling and flying capacitors.
    Part2("C13", "C", "4.7uF/10V/0805", "TFT_VCOM", "GND"),
    Part2("C14", "C", "0.47uF/25V/1210", "FPL_VCOM", "GND"),
    Part2("R2", "R", "0R", "RESEL", "GND"),
    Part2("C7", "C", "10uF/25V/1210", "VSH", "GND"),
    Part2("C8", "C", "10uF/25V/1210", "VSH_LV", "GND"),
    Part2("C9", "C", "10uF/25V/1210", "VSH_LV2", "GND"),
    Part2("C10", "C", "10uF/25V/1210", "VSL", "GND"),
    Part2("C11", "C", "10uF/25V/1210", "VSL_LV", "GND"),
    Part2("C12", "C", "10uF/25V/1210", "VSL_LV2", "GND"),
    Part2("C21", "C", "1uF/10V/0805", "REFN", "GND"),
    Part2("C20", "C", "1uF/10V/0805", "REFP", "GND"),
    Part2("C1", "C", "2.2uF/25V/0603", "VDDD", "GND"),
    Part2("C19", "C", "1uF/10V/0805", "VCP2", "GND"),
    Part2("C18", "C", "1uF/10V/0805", "CP2N", "CP2P"),
    Part2("C17", "C", "1uF/10V/0805", "VCP1", "GND"),
    Part2("C16", "C", "1uF/10V/0805", "CP1N", "CP1P"),
    Part2("C15", "C", "0.47uF/25V/1210", "VCOMBD", "GND"),
    # Practical add-ons, marked DNP, because the reference only shows TSCL/TSDA pull-ups.
    Part2("R15", "R", "47k DNP", "CSB", "VDDIO", note="Optional CS pull-up for debug/boot stability"),
    Part2("R16", "R", "47k DNP", "SL_CSB", "VDDIO", note="Optional SL_CSB pull-up for debug/boot stability"),
    Part2("R17", "R", "47k DNP", "RST_N", "VDDIO", note="Optional reset pull-up"),
]

PARTS_3PIN: list[Part3] = [
    Part3(
        "Q1",
        "NMOS",
        "Si1308EDL",
        (("1", "G", "GDRH"), ("2", "S", "RESEH"), ("3", "D", "SW_H")),
        note="NMOS VDS=30V, low Ron at VGS=2.5V, Qg <= 3.5nC",
    ),
    Part3(
        "Q2",
        "PMOS",
        "SI2301CDS-T1-GE3",
        (("1", "G", "GDRC"), ("2", "S", "V_B"), ("3", "D", "SW_C")),
        note="PMOS VDS=-20V, low Ron at VGS=-2.5V, Qg <= 7.6nC",
    ),
]

TESTPOINT_NETS = [
    "3V3",
    "GND",
    "V_B",
    "EPD_3V3",
    "VDD",
    "VDDIO",
    "VPH",
    "PREVGH",
    "PREVGL",
    "VPC",
    "CSB",
    "SL_CSB",
    "SCL",
    "SI0",
    "DC",
    "RST_N",
    "BUSY_N",
    "GDRH",
    "GDRC",
    "RESEH",
    "RESEC",
]

RESERVED_TEST_NETS = [
    "GDRL",
    "SI1",
    "SI2",
    "SI3",
    "CGH1N",
    "CGH1P",
]


def all_nets() -> dict[str, int]:
    names: list[str] = []
    for pin in FPC_PINS + MCU_PINS:
        if pin.net:
            names.append(pin.net)
    for part in PARTS_2PIN:
        names.extend([part.net1, part.net2])
    for part in PARTS_3PIN:
        names.extend(net for _, _, net in part.pins)
    names.extend(TESTPOINT_NETS)
    names.extend(RESERVED_TEST_NETS)
    deduped = list(dict.fromkeys(names))
    return {name: index + 1 for index, name in enumerate(deduped)}


NETS = all_nets()


def footprint_name_for_part2(part: Part2) -> str:
    if part.kind == "R":
        if part.ref in {"R1", "R3"}:
            return R_1206_FOOTPRINT_NAME
        return R_0603_FOOTPRINT_NAME
    if part.kind == "C":
        if "/1210" in part.value:
            return C_1210_FOOTPRINT_NAME
        if "/0805" in part.value:
            return C_0805_FOOTPRINT_NAME
        return C_0603_FOOTPRINT_NAME
    if part.kind == "L":
        return L_7X7_FOOTPRINT_NAME
    if part.kind == "D_SCH":
        return D_SOD123_FOOTPRINT_NAME
    return part.footprint


def footprint_path_for_part2(part: Part2) -> Path:
    footprint = footprint_name_for_part2(part)
    mapping = {
        R_0603_FOOTPRINT_NAME: R_0603_FOOTPRINT,
        R_1206_FOOTPRINT_NAME: R_1206_FOOTPRINT,
        C_0603_FOOTPRINT_NAME: C_0603_FOOTPRINT,
        C_0805_FOOTPRINT_NAME: C_0805_FOOTPRINT,
        C_1210_FOOTPRINT_NAME: C_1210_FOOTPRINT,
        L_7X7_FOOTPRINT_NAME: L_7X7_FOOTPRINT,
        D_SOD123_FOOTPRINT_NAME: D_SOD123_FOOTPRINT,
    }
    return mapping[footprint]


def footprint_name_for_part3(part: Part3) -> str:
    return SOT23_FOOTPRINT_NAME


def footprint_path_for_part3(part: Part3) -> Path:
    return SOT23_FOOTPRINT


def make_project() -> str:
    data = {
        "meta": {"version": 1, "filename": f"{PROJECT}.kicad_pro"},
        "board": {
            "design_settings": {
                "defaults": {
                    "board_outline_line_width": 0.1,
                    "copper_line_width": 0.2,
                    "copper_text_size_h": 1.0,
                    "copper_text_size_v": 1.0,
                    "copper_text_thickness": 0.15,
                    "silk_line_width": 0.12,
                    "silk_text_size_h": 1.0,
                    "silk_text_size_v": 1.0,
                    "silk_text_thickness": 0.15,
                },
                "meta": {"version": 2},
            }
        },
        "schematic": {
            "drawing": {"default_line_thickness": 6, "default_text_size": 50},
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "meta": {"version": 1},
        },
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    }
    return json.dumps(data, indent=2)


def make_sym_lib_table() -> str:
    return (
        "(sym_lib_table\n"
        '\t(lib (name "Local") (type "KiCad") (uri "${KIPRJMOD}/mf1750_local.kicad_sym") '
        '(options "") (descr "Local symbols for MF-1750 reference schematic"))\n'
        ")\n"
    )


def make_local_symbol_lib() -> str:
    body = "\n".join(local_symbol_defs())
    body = body.replace('\t\t(symbol "Local:', '\t(symbol "')
    return (
        "(kicad_symbol_lib\n"
        "\t(version 20250114)\n"
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "10.0")\n'
        f"{body}\n"
        ")\n"
    )


def prop(name: str, value: str, x: float, y: float, hidden: bool = False) -> str:
    hide = "\n\t\t\t\t(hide yes)" if hidden else ""
    return (
        f'\t\t(property "{name}" "{q(value)}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        f"\t\t\t\t){hide}\n"
        "\t\t\t)\n"
        "\t\t)"
    )


def symbol_lib_connector(name: str, pins: list[Pin], left_count: int, footprint: str) -> str:
    top = max(left_count, len(pins) - left_count) * 2.54
    lines = [
        f'\t\t(symbol "Local:{name}"',
        "\t\t\t(pin_names",
        "\t\t\t\t(offset 1.016)",
        "\t\t\t)",
        "\t\t\t(exclude_from_sim no)",
        "\t\t\t(in_bom yes)",
        "\t\t\t(on_board yes)",
        '\t\t\t(property "Reference" "J"',
        "\t\t\t\t(at 0 0 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)))",
        "\t\t\t)",
        f'\t\t\t(property "Value" "{name}"',
        "\t\t\t\t(at 0 -2.54 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)))",
        "\t\t\t)",
        f'\t\t\t(property "Footprint" "{q(footprint)}"',
        "\t\t\t\t(at 0 0 0)",
        "\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes))",
        "\t\t\t)",
        f'\t\t\t(symbol "{name}_0_1"',
        "\t\t\t\t(rectangle",
        f"\t\t\t\t\t(start -10 {-4:.2f})",
        f"\t\t\t\t\t(end 10 {top:.2f})",
        "\t\t\t\t\t(stroke (width 0.254) (type default))",
        "\t\t\t\t\t(fill (type background))",
        "\t\t\t\t)",
        "\t\t\t)",
        f'\t\t\t(symbol "{name}_1_1"',
    ]
    for index, pin in enumerate(pins):
        if index < left_count:
            y = (left_count - 1 - index) * 2.54
            x = -15.24
            rot = 0
        else:
            y = (len(pins) - index - 1) * 2.54
            x = 15.24
            rot = 180
        lines += [
            "\t\t\t\t(pin passive line",
            f"\t\t\t\t\t(at {x:.2f} {y:.2f} {rot})",
            "\t\t\t\t\t(length 5.08)",
            f'\t\t\t\t\t(name "{q(pin.name)}" (effects (font (size 0.85 0.85))))',
            f'\t\t\t\t\t(number "{pin.number}" (effects (font (size 0.8 0.8))))',
            "\t\t\t\t)",
        ]
    lines += ["\t\t\t)", "\t\t)"]
    return "\n".join(lines)


def symbol_lib_two_pin(name: str, ref_prefix: str, footprint: str, pin1: str = "1", pin2: str = "2") -> str:
    return "\n".join(
        [
            f'\t\t(symbol "Local:{name}"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            f'\t\t\t(property "Reference" "{ref_prefix}" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Value" "{name}" (at 0 2.54 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{q(footprint)}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'\t\t\t(symbol "{name}_0_1"',
            "\t\t\t\t(rectangle (start -2.54 -1.27) (end 2.54 1.27) (stroke (width 0.2) (type default)) (fill (type none)))",
            "\t\t\t)",
            f'\t\t\t(symbol "{name}_1_1"',
            f'\t\t\t\t(pin passive line (at -5.08 0 0) (length 2.54) (name "{pin1}" (effects (font (size 0.75 0.75)))) (number "1" (effects (font (size 0.75 0.75)))))',
            f'\t\t\t\t(pin passive line (at 5.08 0 180) (length 2.54) (name "{pin2}" (effects (font (size 0.75 0.75)))) (number "2" (effects (font (size 0.75 0.75)))))',
            "\t\t\t)",
            "\t\t)",
        ]
    )


def symbol_lib_fet(name: str, ref_prefix: str, footprint: str) -> str:
    return "\n".join(
        [
            f'\t\t(symbol "Local:{name}"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            f'\t\t\t(property "Reference" "{ref_prefix}" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Value" "{name}" (at 0 5.08 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{q(footprint)}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'\t\t\t(symbol "{name}_0_1"',
            "\t\t\t\t(rectangle (start -2.54 -3.81) (end 2.54 3.81) (stroke (width 0.2) (type default)) (fill (type none)))",
            "\t\t\t)",
            f'\t\t\t(symbol "{name}_1_1"',
            '\t\t\t\t(pin input line (at -5.08 0 0) (length 2.54) (name "G" (effects (font (size 0.75 0.75)))) (number "1" (effects (font (size 0.75 0.75)))))',
            '\t\t\t\t(pin passive line (at 5.08 -2.54 180) (length 2.54) (name "D" (effects (font (size 0.75 0.75)))) (number "2" (effects (font (size 0.75 0.75)))))',
            '\t\t\t\t(pin passive line (at 5.08 2.54 180) (length 2.54) (name "S" (effects (font (size 0.75 0.75)))) (number "3" (effects (font (size 0.75 0.75)))))',
            "\t\t\t)",
            "\t\t)",
        ]
    )


def symbol_lib_testpoint() -> str:
    return "\n".join(
        [
            '\t\t(symbol "Local:TP"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            '\t\t\t(property "Reference" "TP" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))',
            '\t\t\t(property "Value" "TP" (at 0 2.54 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{q(TP_FOOTPRINT_NAME)}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            '\t\t\t(symbol "TP_0_1"',
            "\t\t\t\t(circle (center 0 0) (radius 1.27) (stroke (width 0.2) (type default)) (fill (type none)))",
            "\t\t\t)",
            '\t\t\t(symbol "TP_1_1"',
            '\t\t\t\t(pin passive line (at -5.08 0 0) (length 3.81) (name "1" (effects (font (size 0.75 0.75)))) (number "1" (effects (font (size 0.75 0.75)))))',
            "\t\t\t)",
            "\t\t)",
        ]
    )


def symbol_instance(
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    pins: list[str],
    dnp: bool = False,
) -> str:
    sid = uid()
    lines = [
        "\t(symbol",
        f'\t\t(lib_id "{q(lib_id)}")',
        f"\t\t(at {x:.2f} {y:.2f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        "\t\t(in_bom yes)",
        "\t\t(on_board yes)",
        f"\t\t(dnp {'yes' if dnp else 'no'})",
        f'\t\t(uuid "{sid}")',
        prop("Reference", ref, x, y - 4.0),
        prop("Value", value, x, y + 3.5),
        prop("Footprint", footprint, x, y, True),
        prop("封装", footprint, x, y + 2.2, True),
        prop("Datasheet", "", x, y, True),
        prop("Description", "", x, y, True),
    ]
    for pin in pins:
        lines += [f'\t\t(pin "{pin}"', f'\t\t\t(uuid "{uid()}")', "\t\t)"]
    lines += [
        "\t\t(instances",
        f'\t\t\t(project "{PROJECT}"',
        f'\t\t\t\t(path "/{uid()}"',
        f'\t\t\t\t\t(reference "{ref}")',
        "\t\t\t\t\t(unit 1)",
        "\t\t\t\t)",
        "\t\t\t)",
        "\t\t)",
        "\t)",
    ]
    return "\n".join(lines)


def wire(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        "\t(wire\n"
        "\t\t(pts\n"
        f"\t\t\t(xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})\n"
        "\t\t)\n"
        "\t\t(stroke (width 0) (type solid))\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def label(text: str, x: float, y: float, rot: int = 0, justify: str = "left") -> str:
    return (
        f'\t(label "{q(text)}"\n'
        f"\t\t(at {x:.2f} {y:.2f} {rot})\n"
        "\t\t(effects\n"
        "\t\t\t(font (size 0.9 0.9))\n"
        f"\t\t\t(justify {justify})\n"
        "\t\t)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def no_connect(x: float, y: float) -> str:
    return f'\t(no_connect\n\t\t(at {x:.2f} {y:.2f})\n\t\t(uuid "{uid()}")\n\t)'


def text_note(text: str, x: float, y: float, size: float = 1.27) -> str:
    return (
        f'\t(text "{q(text)}"\n'
        "\t\t(exclude_from_sim no)\n"
        f"\t\t(at {x:.2f} {y:.2f} 0)\n"
        f"\t\t(effects (font (size {size:.2f} {size:.2f})) (justify left))\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def graphic_rect(x1: float, y1: float, x2: float, y2: float, color: tuple[int, int, int] = (80, 80, 80)) -> str:
    r, g, b = color
    return (
        f"\t(rectangle (start {x1:.2f} {y1:.2f}) (end {x2:.2f} {y2:.2f})\n"
        f"\t\t(stroke (width 0.12) (type dash) (color {r} {g} {b} 1))\n"
        "\t\t(fill (type none))\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def junction(x: float, y: float) -> str:
    return (
        f"\t(junction (at {x:.2f} {y:.2f}) (diameter 0) (color 0 0 0 0)\n"
        f'\t\t(uuid "{uid()}")\n'
        "\t)"
    )


def connect_pin_to_anchor(lines: list[str], px: float, py: float, ax: float, ay: float) -> None:
    if abs(px - ax) < 0.01 and abs(py - ay) < 0.01:
        return
    if abs(py - ay) < 0.01 or abs(px - ax) < 0.01:
        lines.append(wire(px, py, ax, ay))
        return
    lines.append(wire(px, py, ax, py))
    lines.append(junction(ax, py))
    lines.append(wire(ax, py, ax, ay))


def connect_net_group(
    lines: list[str],
    pins_by_net: dict[str, list[tuple[float, float]]],
    anchors: dict[str, tuple[float, float]],
    label_side: str = "left",
) -> None:
    for net, points in pins_by_net.items():
        if not points:
            continue
        if net in anchors:
            ax, ay = anchors[net]
        else:
            ax, ay = points[0]
        ax = grid(ax)
        ay = grid(ay)
        for px, py in points:
            connect_pin_to_anchor(lines, px, py, ax, ay)
        lines.append(junction(ax, ay))
        if label_side == "right":
            lines.append(label(net, ax, ay, 180, "right"))
        else:
            lines.append(label(net, ax, ay, 0, "left"))


def place_part2_symbol(lines: list[str], part: Part2, x: float, y: float) -> dict[str, tuple[float, float]]:
    x = grid(x)
    y = grid(y)
    dnp = "DNP" in part.value or part.value == "NC"
    lines.append(symbol_instance(f"Local:{part.kind}", part.ref, part.value, footprint_name_for_part2(part), x, y, ["1", "2"], dnp))
    if part.note:
        lines.append(text_note(part.note, x - 9.0, y + 4.8, 0.85))
    return {
        part.net1: (x - 5.08, y),
        part.net2: (x + 5.08, y),
    }


def place_part3_symbol(lines: list[str], part: Part3, x: float, y: float) -> dict[str, tuple[float, float]]:
    x = grid(x)
    y = grid(y)
    lines.append(symbol_instance(f"Local:{part.kind}", part.ref, part.value, footprint_name_for_part3(part), x, y, [p for p, _, _ in part.pins]))
    pin_points = {
        "1": (x - 5.08, y),
        "2": (x + 5.08, y + 2.54),
        "3": (x + 5.08, y - 2.54),
    }
    if part.note:
        lines.append(text_note(part.note, x - 9.0, y + 8.0, 0.85))
    return {net: pin_points[pin_num] for pin_num, _, net in part.pins}


def add_pin_points(target: dict[str, list[tuple[float, float]]], pins: dict[str, tuple[float, float]]) -> None:
    for net, point in pins.items():
        target.setdefault(net, []).append(point)


def connect_pin_to_label(lines: list[str], px: float, py: float, net: str, side: str) -> None:
    if side == "left":
        lx = px - 7.62
        rot = 0
        justify = "left"
    else:
        lx = px + 7.62
        rot = 180
        justify = "right"
    lines.append(wire(px, py, lx, py))
    lines.append(label(net, lx, py, rot, justify))


def place_connector_labels(lines: list[str], x: float, y: float, pins: list[Pin], left_count: int) -> None:
    for index, pin in enumerate(pins):
        if index < left_count:
            py = y - (left_count - 1 - index) * 2.54
            px = x - 15.24
            if not pin.net:
                lines.append(no_connect(px, py))
                continue
            connect_pin_to_label(lines, px, py, pin.net, "left")
        else:
            py = y - (len(pins) - index - 1) * 2.54
            px = x + 15.24
            if not pin.net:
                lines.append(no_connect(px, py))
                continue
            connect_pin_to_label(lines, px, py, pin.net, "right")


def place_part2(lines: list[str], part: Part2, x: float, y: float) -> None:
    x = grid(x)
    y = grid(y)
    dnp = "DNP" in part.value or part.value == "NC"
    lines.append(symbol_instance(f"Local:{part.kind}", part.ref, part.value, footprint_name_for_part2(part), x, y, ["1", "2"], dnp))
    connect_pin_to_label(lines, x - 5.08, y, part.net1, "left")
    connect_pin_to_label(lines, x + 5.08, y, part.net2, "right")
    if part.note:
        lines.append(text_note(part.note, x - 9.0, y + 4.8, 0.85))


def place_part3(lines: list[str], part: Part3, x: float, y: float) -> None:
    x = grid(x)
    y = grid(y)
    lines.append(symbol_instance(f"Local:{part.kind}", part.ref, part.value, footprint_name_for_part3(part), x, y, [p for p, _, _ in part.pins]))
    pin_points = {
        "1": (x - 5.08, y, "left"),
        "2": (x + 5.08, y + 2.54, "right"),
        "3": (x + 5.08, y - 2.54, "right"),
    }
    for pin_num, _, net in part.pins:
        px, py, side = pin_points[pin_num]
        connect_pin_to_label(lines, px, py, net, side)
    if part.note:
        lines.append(text_note(part.note, x - 9.0, y + 8.0, 0.85))


def local_symbol_defs() -> list[str]:
    return [
        symbol_lib_connector("MF1750_FPC50", FPC_PINS, 25, FPC_FOOTPRINT_NAME),
        symbol_lib_connector("ESP32_SPI_10PIN", MCU_PINS, 10, MCU_FOOTPRINT_NAME),
        symbol_lib_two_pin("R", "R", R_0603_FOOTPRINT_NAME),
        symbol_lib_two_pin("C", "C", C_0603_FOOTPRINT_NAME),
        symbol_lib_two_pin("L", "L", L_7X7_FOOTPRINT_NAME),
        symbol_lib_two_pin("D_SCH", "D", D_SOD123_FOOTPRINT_NAME, "K", "A"),
        symbol_lib_fet("NMOS", "Q", SOT23_FOOTPRINT_NAME),
        symbol_lib_fet("PMOS", "Q", SOT23_FOOTPRINT_NAME),
        symbol_lib_testpoint(),
    ]


def make_schematic() -> str:
    part2 = {part.ref: part for part in PARTS_2PIN}
    part3 = {part.ref: part for part in PARTS_3PIN}
    lines: list[str] = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{uid()}")',
        '\t(paper "A2")',
        "\t(title_block",
        '\t\t(title "MF-1750 / M009F-T Full 50-pin Driver - Reference Schematic Draft")',
        '\t\t(company "Generated in ESP32_C73 workspace")',
        "\t)",
        "\t(lib_symbols",
        *local_symbol_defs(),
        "\t)",
    ]

    # System-level functional groups. The schematic remains single-page for
    # JLC/KiCad import stability, while each block now has local wired nodes.
    groups = [
        ("MCU / SPI control input", 25, 25, 112, 104, (50, 95, 170)),
        ("3V3 distribution, pullups, and 4-wire mode", 122, 25, 318, 118, (70, 120, 80)),
        ("HV boost and negative gate pump", 25, 126, 264, 226, (180, 90, 35)),
        ("VPC positive pump", 25, 236, 264, 300, (180, 90, 35)),
        ("Panel FPC and MF-1750 signals", 338, 25, 542, 118, (50, 95, 170)),
        ("Panel-side caps, references, and flying capacitors", 276, 126, 542, 300, (120, 90, 150)),
        ("Bring-up and reserved test pads", 25, 312, 542, 387, (95, 95, 95)),
    ]
    for title, x1, y1, x2, y2, color in groups:
        lines.append(graphic_rect(x1, y1, x2, y2, color))
        lines.append(text_note(title, x1 + 3, y1 + 5, 1.15))

    # Connectors stay at the system boundaries and expose named interfaces.
    fpc_x, fpc_y = grid(460.0), grid(80.0)
    mcu_x, mcu_y = grid(70.0), grid(60.0)
    lines.append(
        symbol_instance(
            "Local:MF1750_FPC50",
            "J1",
            "MF-1750 50pin FPC",
            FPC_FOOTPRINT_NAME,
            fpc_x,
            fpc_y,
            [str(pin.number) for pin in FPC_PINS],
        )
    )
    lines.append(
        symbol_instance(
            "Local:ESP32_SPI_10PIN",
            "J2",
            "ESP32 SPI 10pin",
            MCU_FOOTPRINT_NAME,
            mcu_x,
            mcu_y,
            [str(pin.number) for pin in MCU_PINS],
        )
    )
    place_connector_labels(lines, fpc_x, fpc_y, FPC_PINS, 25)
    place_connector_labels(lines, mcu_x, mcu_y, MCU_PINS, 10)

    # 3V3 distribution, cascade pullups, optional logic pullups, and BS straps.
    power_positions = {
        "R4": (145, 45),
        "R8": (145, 58),
        "R6": (195, 45),
        "R7": (195, 58),
        "C3": (195, 72),
        # Keep C23 away from R12.  At (245, 58) their 7.62 mm label stubs
        # crossed and electrically merged V_B, GND, and BS0 in the netlist.
        "C23": (145, 72),
        "R9": (145, 91),
        "R10": (195, 91),
        "R11": (250, 45),
        "R12": (250, 58),
        "R14": (292, 45),
        "R13": (292, 58),
        "R15": (250, 91),
        "R16": (292, 91),
        "R17": (250, 104),
    }
    for ref, pos in power_positions.items():
        if ref in part2:
            place_part2(lines, part2[ref], *pos)
    lines.append(text_note("R12/R13 set BS0=0 and BS1=0 for 4-wire SPI.", 126, 114, 0.9))

    # HV boost and negative pump. Nets inside this block are physically wired
    # to shared nodes so ERC can see the pump topology directly.
    hv_positions = {
        "C0": (45, 148),
        "L1": (85, 148),
        "D1": (126, 148),
        "C2": (168, 148),
        "R5": (215, 148),
        "C4": (85, 169),
        "D2": (126, 169),
        "D3": (168, 169),
        "C5": (215, 169),
        "Q1": (85, 200),
        "R1": (168, 200),
    }
    for ref in ["C0", "L1", "D1", "C2", "R5", "C4", "D2", "D3", "C5", "R1"]:
        place_part2(lines, part2[ref], *hv_positions[ref])
    place_part3(lines, part3["Q1"], *hv_positions["Q1"])
    lines.append(text_note("Main current path: V_B -> L1 -> SW_H/Q1/D1 -> VPH -> R5 -> PREVGH.", 32, 222, 0.9))

    # VPC positive pump / source rail section.
    vpc_positions = {
        "C22": (45, 256),
        "Q2": (85, 274),
        "L2": (132, 274),
        "D4": (176, 274),
        "C6": (220, 274),
        "R3": (132, 291),
    }
    for ref in ["C22", "L2", "D4", "C6", "R3"]:
        place_part2(lines, part2[ref], *vpc_positions[ref])
    place_part3(lines, part3["Q2"], *vpc_positions["Q2"])
    lines.append(text_note("Q2/L2/D4/R3 form the VPC pump; keep this loop compact in PCB layout.", 32, 299, 0.9))

    # FPC-side decoupling and charge-pump capacitors.
    fpc_cap_positions = {
        "C13": (300, 148),
        "C14": (365, 148),
        "R2": (430, 148),
        "C7": (300, 173),
        "C8": (365, 173),
        "C9": (430, 173),
        "C10": (495, 173),
        "C11": (300, 198),
        "C12": (365, 198),
        "C21": (430, 198),
        "C20": (495, 198),
        "C1": (300, 223),
        "C19": (365, 223),
        "C18": (430, 223),
        "C17": (495, 223),
        "C16": (365, 248),
        "C15": (430, 248),
    }
    for ref, pos in fpc_cap_positions.items():
        place_part2(lines, part2[ref], *pos)

    # Test points need explicit schematic footprints because JLC import treats
    # missing footprint properties as fatal even when KiCad ERC allows them.
    for i, net in enumerate(TESTPOINT_NETS + RESERVED_TEST_NETS):
        ref = f"TP{i + 1}"
        x = grid(45 + (i % 9) * 55)
        y = grid(330 + (i // 9) * 18)
        lines.append(symbol_instance("Local:TP", ref, net, TP_FOOTPRINT_NAME, x, y, ["1"]))
        connect_pin_to_label(lines, x - 5.08, y, net, "left")

    notes = [
        "Reference source: MF-1750/M009F-T specification page 10 reference circuit.",
        "Critical fix versus DESPI-C73: J1 pin 4 is SL_CSB and must route to an ESP32 GPIO as CS2.",
        "Functional blocks now group and wire local nodes; net labels are reserved for cross-block interfaces.",
        "Default bus mode: BS0=0 and BS1=0 through R12/R13 for 4-wire SPI with D/C.",
        "Diode polarity is assigned in BOM notes; match footprint pin A/K to those notes before PCB layout.",
        "Reserved FPC pins are routed only to isolated single test pads; pin1 NC is explicitly no-connect.",
        "Footprints are intentionally mostly blank; assign real packages and ratings in KiCad before layout.",
        "After board bring-up, firmware should enable EPD_PIN_CS2 and drive both CSB and SL_CSB for full 1024x600 refresh.",
    ]
    for i, note in enumerate(notes):
        lines.append(text_note(note, 35.0, 394.0 + i * 5.0, 1.05))

    lines += ["\t(sheet_instances", '\t\t(path "/" (page "1"))', "\t)", ")"]
    return "\n".join(lines) + "\n"


def patch_footprint(
    source: Path,
    footprint_id: str,
    ref: str,
    value: str,
    at_x: float,
    at_y: float,
    rot: float,
    pad_nets: dict[str, str],
) -> str:
    text = source.read_text(encoding="utf-8")
    text = re.sub(r'^\(footprint ".*?"', f'(footprint "{footprint_id}"', text, count=1)
    text = re.sub(r'\(uuid "[0-9a-fA-F-]+"\)', lambda _m: f'(uuid "{uid()}")', text)
    text = re.sub(r'\(property "Reference" ".*?"', f'(property "Reference" "{ref}"', text, count=1)
    text = re.sub(r'\(property "Value" ".*?"', f'(property "Value" "{value}"', text, count=1)
    text = text.replace('\t(layer "F.Cu")', f'\t(layer "F.Cu")\n\t(at {at_x:.3f} {at_y:.3f} {rot:.1f})\n\t(uuid "{uid()}")', 1)

    # Keep generated placement clean for DRC/JLC import; reference designators
    # remain in BOM and Fab layer but do not crowd the provisional silkscreen.
    ref_processed: list[str] = []
    in_reference_property = False
    for line in text.splitlines():
        if '(property "Reference"' in line:
            in_reference_property = True
        elif '(property "Value"' in line:
            in_reference_property = False
        if in_reference_property and '(layer "F.SilkS")' in line:
            line = line.replace('"F.SilkS"', '"F.Fab"')
        ref_processed.append(line)
    text = "\n".join(ref_processed)

    out: list[str] = []
    current_pad: str | None = None
    for line in text.splitlines():
        m = re.match(r'\s*\(pad "([^"]+)"', line)
        if m:
            current_pad = m.group(1)
        out.append(line)
        if current_pad and "(layers " in line:
            net_name = pad_nets.get(current_pad)
            if net_name and net_name in NETS:
                out.append(f'\t\t(net {NETS[net_name]} "{net_name}")')
        if current_pad and line.startswith("\t)"):
            current_pad = None
    return "\n".join(out)


def make_board_placeholder() -> str:
    net_lines = ['\t(net 0 "")']
    for name, idx in sorted(NETS.items(), key=lambda item: item[1]):
        net_lines.append(f'\t(net {idx} "{name}")')

    footprints: list[str] = []
    if FPC_FOOTPRINT.exists():
        footprints.append(
            patch_footprint(
                FPC_FOOTPRINT,
                FPC_FOOTPRINT_NAME,
                "J1",
                "MF-1750_50PIN_FPC",
                115,
                28,
                0,
                {str(pin.number): pin.net for pin in FPC_PINS if pin.net},
            )
        )
    if MCU_FOOTPRINT.exists():
        footprints.append(
            patch_footprint(
                MCU_FOOTPRINT,
                MCU_FOOTPRINT_NAME,
                "J2",
                "ESP32_SPI_10PIN",
                25,
                35,
                0,
                {str(pin.number): pin.net for pin in MCU_PINS if pin.net},
            )
        )

    part2_positions: dict[str, tuple[float, float, float]] = {
        # High-voltage boost/negative pump. Keep these compact during manual layout.
        "C0": (48, 38, 0),
        "L1": (62, 38, 0),
        "D1": (78, 38, 0),
        "C2": (92, 38, 0),
        "R5": (106, 38, 0),
        "C4": (62, 51, 0),
        "D2": (78, 51, 0),
        "D3": (92, 51, 0),
        "C5": (96, 60, 0),
        "R1": (72, 63, 0),
        # PMOS/VPC stage.
        "C22": (48, 78, 0),
        "L2": (62, 78, 0),
        "D4": (78, 78, 0),
        "C6": (92, 78, 0),
        "R3": (72, 91, 0),
        # Power straps and mode straps.
        "R4": (25, 63, 0),
        "R8": (38, 63, 0),
        "C23": (51, 63, 0),
        "R6": (25, 74, 0),
        "R7": (38, 74, 0),
        "C3": (51, 74, 0),
        "R9": (25, 87, 0),
        "R10": (38, 87, 0),
        "R11": (122, 62, 0),
        "R12": (136, 62, 0),
        "R14": (122, 70, 0),
        "R13": (136, 70, 0),
        "R15": (150, 62, 0),
        "R16": (150, 70, 0),
        "R17": (150, 78, 0),
        # FPC-side capacitors near J1.
        "C13": (104, 35, 0),
        "C14": (116, 40, 0),
        "R2": (128, 35, 0),
        "C7": (104, 48, 0),
        "C8": (116, 48, 0),
        "C9": (128, 48, 0),
        "C10": (140, 48, 0),
        "C11": (152, 48, 0),
        "C12": (164, 48, 0),
        "C21": (104, 59, 0),
        "C20": (116, 59, 0),
        "C1": (128, 59, 0),
        "C19": (140, 59, 0),
        "C18": (152, 59, 0),
        "C17": (164, 59, 0),
        "C16": (140, 70, 0),
        "C15": (164, 70, 0),
    }
    for part in PARTS_2PIN:
        source = footprint_path_for_part2(part)
        if not source.exists():
            continue
        x, y, rot = part2_positions[part.ref]
        footprints.append(
            patch_footprint(
                source,
                footprint_name_for_part2(part),
                part.ref,
                part.value,
                x,
                y,
                rot,
                {"1": part.net1, "2": part.net2},
            )
        )

    part3_positions = {
        "Q1": (72, 51, 0),
        "Q2": (72, 78, 0),
    }
    for part in PARTS_3PIN:
        source = footprint_path_for_part3(part)
        if not source.exists():
            continue
        x, y, rot = part3_positions[part.ref]
        footprints.append(
            patch_footprint(
                source,
                footprint_name_for_part3(part),
                part.ref,
                part.value,
                x,
                y,
                rot,
                {pin_num: net for pin_num, _, net in part.pins},
            )
        )

    for i, net in enumerate(TESTPOINT_NETS + RESERVED_TEST_NETS):
        if not TP_FOOTPRINT.exists():
            continue
        footprints.append(
            patch_footprint(
                TP_FOOTPRINT,
                TP_FOOTPRINT_NAME,
                f"TP{i + 1}",
                net,
                102 + (i % 9) * 8,
                92 + (i // 9) * 7,
                0,
                {"1": net},
            )
        )

    return (
        "(kicad_pcb\n"
        "\t(version 20241229)\n"
        '\t(generator "pcbnew")\n'
        '\t(generator_version "10.0")\n'
        "\t(general (thickness 1.6) (legacy_teardrops no))\n"
        '\t(paper "A4")\n'
        "\t(layers\n"
        '\t\t(0 "F.Cu" signal)\n'
        '\t\t(2 "B.Cu" signal)\n'
        '\t\t(5 "F.SilkS" user)\n'
        '\t\t(1 "F.Mask" user)\n'
        '\t\t(3 "B.Mask" user)\n'
        '\t\t(25 "Edge.Cuts" user)\n'
        '\t\t(31 "F.CrtYd" user)\n'
        '\t\t(29 "B.CrtYd" user)\n'
        '\t\t(35 "F.Fab" user)\n'
        '\t\t(33 "B.Fab" user)\n'
        "\t)\n"
        "\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))\n"
        + "\n".join(net_lines)
        + "\n"
        '\t(gr_rect (start 10 10) (end 180 110) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts") '
        + f'(uuid "{uid()}"))\n'
        '\t(gr_text "MF-1750 FULL DRIVER - SEMI-AUTO PLACEMENT DRAFT" (at 18 14 0) (layer "F.SilkS") '
        + f'(uuid "{uid()}") (effects (font (size 1.0 1.0) (thickness 0.15)) (justify left)))\n'
        '\t(gr_text "VERIFY J1 CONTACT SIDE BEFORE FAB" (at 120 88 0) (layer "F.SilkS") '
        + f'(uuid "{uid()}") (effects (font (size 1.0 1.0) (thickness 0.15)) (justify left)))\n'
        '\t(gr_text "HV LOOP: KEEP L/Q/D/C SHORT AND WIDE" (at 38 105 0) (layer "F.SilkS") '
        + f'(uuid "{uid()}") (effects (font (size 1.0 1.0) (thickness 0.15)) (justify left)))\n'
        + "\n".join(footprints)
        + "\n)\n"
    )


def make_bom() -> str:
    rows = [
        "ref,kind,value,net1,net2,footprint,note",
        "J1,connector,MF-1750 50pin FPC,,,,Verify contact side/orientation before fabrication",
        "J2,connector,ESP32 SPI 10pin,,,,Includes CSB and SL_CSB",
    ]
    for part in PARTS_2PIN:
        rows.append(
            ",".join(
                [
                    part.ref,
                    part.kind,
                    part.value,
                    part.net1,
                    part.net2,
                    footprint_name_for_part2(part),
                    part.note,
                ]
            )
        )
    for part in PARTS_3PIN:
        nets = ";".join(f"{pin_name}={net}" for _, pin_name, net in part.pins)
        rows.append(",".join([part.ref, part.kind, part.value, nets, "", footprint_name_for_part3(part), part.note]))
    return "\n".join(rows) + "\n"


def make_pinmap() -> str:
    rows = ["pin,name,net,note"]
    for pin in FPC_PINS:
        rows.append(f"{pin.number},{pin.name},{pin.net or ''},{pin.note}")
    return "\n".join(rows) + "\n"


def make_readme() -> str:
    return """# MF-1750 Full Driver KiCad Reference Draft

This project is a KiCad 10 schematic-first reverse model of the MF-1750 /
M009F-T reference circuit.

Generated files:

- `mf1750_full_driver.kicad_pro`
- `mf1750_full_driver.kicad_sch`
- `mf1750_full_driver.kicad_pcb` semi-auto placement draft with all footprints
- `bom_reference.csv`
- `mf1750_fpc_pinmap.csv`
- `mf1750_full_driver_pcb_preview.svg` is generated separately by KiCad CLI
  for quick placement review.

Schematic organization:

- The schematic is a single KiCad sheet for stable JLC/KiCad import, but it is
  organized into functional blocks: MCU/SPI input, 3V3 distribution and mode
  straps, HV boost/negative pump, VPC pump, panel FPC, panel-side capacitors,
  and bring-up/reserved test pads.
- Local circuits are placed in signal-flow order inside each block. Net labels
  are kept close to their pins to preserve ERC-safe connectivity while avoiding
  accidental shorts in dense FPC and strap areas.

Important hardware conclusion:

- MF-1750 pin 4 is `SL_CSB`.
- MF-1750 pin 1 is treated as true `NC` from the I/O table and mechanical
  pin map, even though the page-10 reference drawing labels the connector side
  as `VPP`.
- DESPI-C73 ties its 50-pin pin 4 position differently, so it cannot drive the
  second SPD1657B controller on this 1024x600 cascade panel.
- The new board must route both `CSB` and `SL_CSB` to ESP32 GPIOs.
- Reserved pins `GDRL`, `SI1`, `SI2`, `SI3`, `CGH1N`, and `CGH1P` are only
  brought to isolated optional test pads.
- Diode polarity is assigned in `bom_reference.csv`: D1 pad1/K=VPH and
  pad2/A=SW_H; D2 pad1/K=NEG_PUMP_H and pad2/A=GND; D3
  pad1/K=NEG_PUMP_H and pad2/A=PREVGL; D4 pad1/K=SW_C and pad2/A=VPC.
- MOSFET footprints assume SOT-23 pinout 1=G, 2=S, 3=D.
- Current default footprints: resistors 0603 except R1/R3 as 1206, capacitors
  per reference package sizes, diodes SOD-123, inductors 7.3x7.3 mm, MOSFETs
  SOT-23-3.

Before fabrication:

- Re-check J1 FPC orientation/contact side with the real panel tail.
- Panel tail requirement from the mechanical drawing: 50 pins, 0.5 mm pitch,
  exposed finger width about 24.5 mm, stiffener thickness about 0.30 mm.
- For installation certainty, either use a dual-contact 50-pin 0.5 mm FPC
  connector, or copy the exact contact-side orientation from the working
  DESPI-C73 connector.
- Verify all assigned footprints against JLC/LCSC orderable parts before
  fabrication, especially J1, Q1/Q2, D1-D4, L1/L2, R1/R3.
- Ensure diode footprint pad numbering matches the assigned anode/cathode nets.
- Keep the high-voltage pump layout compact and use suitable voltage ratings.
- Default 4-wire SPI mode is BS0=0 and BS1=0 with R12/R13 populated.
- The PCB is intentionally unrouted. The remaining DRC unconnected items are
  expected until KiCad/JLC routing is completed.
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{PROJECT}.kicad_pro").write_text(make_project(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(make_sym_lib_table(), encoding="utf-8")
    (OUT / "mf1750_local.kicad_sym").write_text(make_local_symbol_lib(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_sch").write_text(make_schematic(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_pcb").write_text(make_board_placeholder(), encoding="utf-8")
    (OUT / "bom_reference.csv").write_text(make_bom(), encoding="utf-8")
    (OUT / "mf1750_fpc_pinmap.csv").write_text(make_pinmap(), encoding="utf-8")
    (OUT / "README.md").write_text(make_readme(), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
