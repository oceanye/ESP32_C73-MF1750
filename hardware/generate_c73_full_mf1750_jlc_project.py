from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import generate_mf1750_kicad_project as base


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware" / "c73_full_mf1750_adapted_kicad"
PROJECT = "c73_full_mf1750_adapted"


FPC_PINS = [
    base.Pin(1, "NC", None, "MF-1750 pin 1 NC; C73 original pin 1 VPP is not used"),
    base.Pin(2, "TFT_VCOM", "TFT_VCOM"),
    base.Pin(3, "FPL_VCOM", "FPL_VCOM"),
    base.Pin(4, "SL_CSB", "SL_CSB", "MF-1750 critical change: replaces C73 original P1 pin 4 VDD"),
    base.Pin(5, "GDRH", "GDRH"),
    base.Pin(6, "RESEH", "RESEH"),
    base.Pin(7, "GDRL", "GDRL", "C73 original marks this node NC"),
    base.Pin(8, "RESEL", "RESEL"),
    base.Pin(9, "GDRC", "GDRC"),
    base.Pin(10, "RESEC", "RESEC"),
    base.Pin(11, "VPC", "VPC"),
    base.Pin(12, "GND", "GND"),
    base.Pin(13, "VGL", "PREVGL", "C73 rail label PREVGL"),
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
    base.Pin(25, "TSDA", "TSDA", "C73 original marks this node NC"),
    base.Pin(26, "BS0", "BS0"),
    base.Pin(27, "BS1", "BS1"),
    base.Pin(28, "RST_N", "RST_N"),
    base.Pin(29, "BUSY_N", "BUSY_N"),
    base.Pin(30, "DC", "DC"),
    base.Pin(31, "CSB", "CSB"),
    base.Pin(32, "SCL", "SCL"),
    base.Pin(33, "SI0", "SI0"),
    base.Pin(34, "SI1", "SI1", "C73 original marks this node NC"),
    base.Pin(35, "SI2", "SI2", "C73 original marks this node NC"),
    base.Pin(36, "SI3", "SI3", "C73 original marks this node NC"),
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
    base.Pin(47, "CGH1N", "CGH1N", "C73 original marks this node NC"),
    base.Pin(48, "CGH1P", "CGH1P", "C73 original marks this node NC"),
    base.Pin(49, "VGH", "PREVGH", "C73 rail label PREVGH"),
    base.Pin(50, "VCOMBD", "VCOMBD"),
]


MCU_PINS = [
    base.Pin(1, "3V3", "3V3"),
    base.Pin(2, "GND", "GND"),
    base.Pin(3, "SDI/SI0", "SI0"),
    base.Pin(4, "SCLK/SCL", "SCL"),
    base.Pin(5, "CSB", "CSB"),
    base.Pin(6, "D/C", "DC"),
    base.Pin(7, "RES/RST_N", "RST_N"),
    base.Pin(8, "BUSY_N", "BUSY_N"),
    base.Pin(9, "SL_CSB/CS2", "SL_CSB"),
    base.Pin(10, "GND", "GND"),
]


PARTS_2PIN = [
    # C73 original high-voltage boost / negative pump.
    base.Part2("C2", "C", "4.7uF/25V/0603", "V_B", "GND", note="C73 input cap near L1"),
    base.Part2("L1", "L", "10uH 1A", "V_B", "SW_H"),
    base.Part2("D4", "D_SCH", "MBR0530", "VPH", "SW_H", note="C73 boost diode"),
    base.Part2("C5", "C", "10uF/25V/1210", "VPH", "GND"),
    base.Part2("R5", "R", "0R", "VPH", "PREVGH"),
    base.Part2("C3", "C", "10uF/25V/1210", "SW_H", "NEG_PUMP_H"),
    base.Part2("D2", "D_SCH", "MBR0530", "PREVGL", "NEG_PUMP_H", note="C73 negative pump diode"),
    base.Part2("D3", "D_SCH", "MBR0530", "NEG_PUMP_H", "GND", note="C73 clamp diode"),
    base.Part2("C6", "C", "10uF/25V/1210", "PREVGL", "GND"),
    base.Part2("R2", "R", "1M", "GDRH", "GND"),
    base.Part2("R4", "R", "0.22R 0.2W 1%", "RESEH", "GND"),
    # C73 original VPC pump.
    base.Part2("C1", "C", "4.7uF/25V/0603", "V_B", "GND", note="C73 input cap near Q2"),
    base.Part2("R1", "R", "1M", "V_B", "GDRC"),
    base.Part2("D1", "D_SCH", "MBR0530", "SW_C", "VPC"),
    base.Part2("C4", "C", "10uF/25V/1210", "VPC", "GND"),
    base.Part2("L2", "L", "10uH 1A", "SW_C", "RESEC"),
    base.Part2("R3", "R", "0.22R 0.2W 1%", "RESEC", "GND"),
    # C73 power distribution.
    base.Part2("L3", "L", "L0603 120R@100MHz", "3V3", "EPD_3V3"),
    base.Part2("L4", "L", "L0603 120R@100MHz", "3V3", "EPD_3V3"),
    base.Part2("R10", "R", "1R", "EPD_3V3", "V_B"),
    base.Part2("C23", "C", "100uF/6.3V", "V_B", "GND"),
    base.Part2("C24", "C", "0.1uF/25V/0603", "EPD_3V3", "GND"),
    base.Part2("R11", "R", "0R", "EPD_3V3", "VDD"),
    base.Part2("R12", "R", "0R", "EPD_3V3", "VDDIO"),
    # Panel-side rails and mode straps from the C73 topology.
    base.Part2("C15", "C", "4.7uF/25V/0603", "TFT_VCOM", "GND"),
    base.Part2("C7", "C", "0.47uF/25V/1210", "FPL_VCOM", "GND"),
    base.Part2("R8", "R", "0R", "VDD", "FPL_VCOM"),
    base.Part2("C8", "C", "10uF/25V/1210", "VSH", "GND"),
    base.Part2("C9", "C", "10uF/25V/1210", "VSH_LV", "GND"),
    base.Part2("C10", "C", "10uF/25V/1210", "VSH_LV2", "GND"),
    base.Part2("C17", "C", "10uF/25V/1210", "VSL", "GND"),
    base.Part2("C18", "C", "10uF/25V/1210", "VSL_LV", "GND"),
    base.Part2("C19", "C", "10uF/25V/1210", "VSL_LV2", "GND"),
    base.Part2("C11", "C", "1uF/25V/0805", "REFN", "GND"),
    base.Part2("C20", "C", "1uF/25V/0805 NC", "REFP", "GND", note="C73 drawing marks NC"),
    base.Part2("R6", "R", "0R", "GND", "BS0", note="4-wire SPI mode strap; verify against final C73 ECO"),
    base.Part2("R7", "R", "0R", "GND", "BS1", note="4-wire SPI mode strap; verify against final C73 ECO"),
    base.Part2("C12", "C", "2.2uF/25V/0603", "VDDD", "GND"),
    base.Part2("C13", "C", "1uF/25V/0805", "VCP2", "GND"),
    base.Part2("C21", "C", "1uF/25V/0805", "CP2N", "CP2P"),
    base.Part2("C14", "C", "1uF/25V/0805", "VCP1", "GND"),
    base.Part2("C22", "C", "1uF/25V/0805", "CP1N", "CP1P"),
    base.Part2("C16", "C", "0.47uF/25V/1210", "VCOMBD", "GND"),
    base.Part2("R9", "R", "0R", "PREVGH", "VCOMBD", note="C73 VCOMBD/rail option; verify before layout"),
    # MF-1750/C73 adaptation additions.
    base.Part2("R_SL", "R", "47k DNP", "SL_CSB", "VDDIO", note="Optional CS2 pull-up for reset/default idle"),
]


PARTS_3PIN = [
    base.Part3("Q1", "NMOS", "Si1308EDL", (("1", "G", "GDRH"), ("2", "S", "RESEH"), ("3", "D", "SW_H"))),
    base.Part3("Q2", "PMOS", "SI2301", (("1", "G", "GDRC"), ("2", "S", "V_B"), ("3", "D", "SW_C"))),
]


TESTPOINTS = [
    "3V3", "GND", "EPD_3V3", "V_B", "VDDIO", "VPH", "PREVGH", "PREVGL", "VPC", "CSB", "SL_CSB",
    "GDRL", "RESEL", "TSCL", "TSDA", "SI1", "SI2", "SI3", "CGH1N", "CGH1P",
]


def configure_base() -> None:
    base.OUT = OUT
    base.PROJECT = PROJECT
    base.FPC_PINS = FPC_PINS
    base.MCU_PINS = MCU_PINS
    base.PARTS_2PIN = PARTS_2PIN
    base.PARTS_3PIN = PARTS_3PIN


def part2(ref: str) -> base.Part2:
    return next(p for p in PARTS_2PIN if p.ref == ref)


def part3(ref: str) -> base.Part3:
    return next(p for p in PARTS_3PIN if p.ref == ref)


def make_schematic() -> str:
    configure_base()
    lines = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{base.uid()}")',
        '\t(paper "A2")',
        "\t(title_block",
        '\t\t(title "DESPI-C73 Full Circuit Adapted for MF-1750 Pin 4 SL_CSB")',
        '\t\t(company "Generated in ESP32_C73 workspace")',
        "\t)",
        "\t(lib_symbols",
        *base.local_symbol_defs(),
        "\t)",
    ]

    groups = [
        ("MCU interface - C73 P2 plus added CS2", 25, 25, 126, 112, (50, 95, 170)),
        ("Panel connector - MF-1750 pin4 is SL_CSB", 372, 25, 548, 156, (50, 95, 170)),
        ("C73 HV boost and negative pump", 25, 132, 274, 236, (180, 90, 35)),
        ("C73 VPC pump", 25, 250, 274, 322, (180, 90, 35)),
        ("C73 power distribution and mode straps", 142, 25, 360, 112, (70, 120, 80)),
        ("Panel-side capacitors and charge-pump pins", 286, 172, 548, 322, (120, 90, 150)),
        ("Bring-up test pads", 25, 338, 548, 394, (95, 95, 95)),
    ]
    for title, x1, y1, x2, y2, color in groups:
        lines.append(base.graphic_rect(x1, y1, x2, y2, color))
        lines.append(base.text_note(title, x1 + 3, y1 + 5, 1.15))

    j2_x, j2_y = base.grid(72), base.grid(65)
    j1_x, j1_y = base.grid(462), base.grid(86)
    lines.append(base.symbol_instance("Local:ESP32_SPI_10PIN", "J2", "C73 P2 + CS2 10pin", base.MCU_FOOTPRINT_NAME, j2_x, j2_y, [str(p.number) for p in MCU_PINS]))
    lines.append(base.symbol_instance("Local:MF1750_FPC50", "J1", "MF-1750 50pin FPC adapted from C73", base.FPC_FOOTPRINT_NAME, j1_x, j1_y, [str(p.number) for p in FPC_PINS]))
    base.place_connector_labels(lines, j2_x, j2_y, MCU_PINS, 10)
    base.place_connector_labels(lines, j1_x, j1_y, FPC_PINS, 25)

    hv_positions = {
        "C2": (44, 154), "L1": (84, 154), "D4": (126, 154), "C5": (168, 154), "R5": (220, 154),
        "C3": (84, 176), "D2": (126, 176), "D3": (168, 176), "C6": (220, 176),
        "Q1": (84, 206), "R2": (44, 222), "R4": (168, 206),
    }
    for ref in ["C2", "L1", "D4", "C5", "R5", "C3", "D2", "D3", "C6", "R2", "R4"]:
        base.place_part2(lines, part2(ref), *hv_positions[ref])
    base.place_part3(lines, part3("Q1"), *hv_positions["Q1"])
    lines.append(base.text_note("C73 original HV topology; only panel connector pin4 is changed.", 32, 232, 0.9))

    vpc_positions = {
        "C1": (44, 270), "R1": (84, 270), "Q2": (84, 292), "D1": (128, 292), "C4": (176, 292),
        "L2": (128, 308), "R3": (176, 308),
    }
    for ref in ["C1", "R1", "D1", "C4", "L2", "R3"]:
        base.place_part2(lines, part2(ref), *vpc_positions[ref])
    base.place_part3(lines, part3("Q2"), *vpc_positions["Q2"])

    power_positions = {
        "L3": (162, 48), "L4": (162, 62), "R10": (214, 62), "C23": (266, 62), "C24": (214, 88),
        "R11": (300, 46), "R12": (300, 62), "R6": (214, 100), "R7": (266, 100), "R_SL": (322, 92),
    }
    for ref, pos in power_positions.items():
        base.place_part2(lines, part2(ref), *pos)
    lines.append(base.text_note("J1 pin4 is no longer C73 VDD; it is SL_CSB routed to J2 pin9.", 146, 108, 0.9))

    panel_positions = {
        "C15": (306, 192), "C7": (366, 192), "R8": (426, 192),
        "C8": (306, 216), "C9": (366, 216), "C10": (426, 216),
        "C17": (486, 216), "C18": (306, 240), "C19": (366, 240),
        "C11": (426, 240), "C20": (486, 240), "C12": (306, 264),
        "C13": (366, 264), "C21": (426, 264), "C14": (486, 264),
        "C22": (366, 288), "C16": (426, 288), "R9": (486, 288),
    }
    for ref, pos in panel_positions.items():
        base.place_part2(lines, part2(ref), *pos)

    for i, net in enumerate(TESTPOINTS):
        x = base.grid(48 + (i % 10) * 50)
        y = base.grid(356 + (i // 10) * 18)
        lines.append(base.symbol_instance("Local:TP", f"TP{i + 1}", net, base.TP_FOOTPRINT_NAME, x, y, ["1"]))
        base.connect_pin_to_label(lines, x - 5.08, y, net, "left")

    notes = [
        "This is the complete C73-style circuit, not only a 50-pin interposer.",
        "Critical adaptation: C73 original P1 pin4 VDD is replaced by MF-1750 SL_CSB.",
        "C73 P1 pin1 VPP is not connected because MF-1750 pin1 is NC.",
        "Subsystem boxes are intentional: interface, power, HV pump, VPC pump, panel caps, test pads.",
        "Before layout, verify J1 contact side, pin-1 direction, diode polarity, and BS0/BS1 straps.",
    ]
    for i, note in enumerate(notes):
        lines.append(base.text_note(note, 32, 405 + i * 6, 1.0))

    lines += ["\t(sheet_instances", '\t\t(path "/" (page "1"))', "\t)", ")"]
    return "\n".join(lines) + "\n"


def make_bom() -> str:
    rows = [["ref", "kind", "value", "net1", "net2", "footprint", "note"]]
    rows += [
        ["J1", "connector", "MF-1750 50pin FPC", "", "", base.FPC_FOOTPRINT_NAME, "C73 P1 pin4 changed to SL_CSB"],
        ["J2", "connector", "C73 P2 plus CS2 10pin", "", "", base.MCU_FOOTPRINT_NAME, "pin9 added SL_CSB/CS2"],
    ]
    for p in PARTS_2PIN:
        rows.append([p.ref, p.kind, p.value, p.net1, p.net2, base.footprint_name_for_part2(p), p.note])
    for p in PARTS_3PIN:
        nets = ";".join(f"{name}={net}" for _, name, net in p.pins)
        rows.append([p.ref, p.kind, p.value, nets, "", base.footprint_name_for_part3(p), p.note])
    out = []
    for row in rows:
        out.append(",".join(f'"{cell}"' if "," in cell or ";" in cell else cell for cell in row))
    return "\n".join(out) + "\n"


def make_pinmap() -> str:
    rows = [["pin", "mf1750_signal", "net", "c73_delta_note"]]
    for pin in FPC_PINS:
        rows.append([str(pin.number), pin.name, pin.net or "", pin.note])
    return "\n".join(",".join(row) for row in rows) + "\n"


def make_readme() -> str:
    return """# DESPI-C73 Full Circuit Adapted for MF-1750

This is the full C73-style circuit redraw for JLC/KiCad import. It is not just
a 50-pin interposer.

Main adaptation:

- C73 original P1 pin 4 was `VDD`.
- MF-1750 pin 4 is `SL_CSB`.
- This schematic routes J1 pin 4 to `SL_CSB` and exposes it on J2 pin 9.
- C73 original P1 pin 1 `VPP` is left unconnected because MF-1750 pin 1 is NC.

The schematic is divided into subsystem boxes: MCU interface, panel connector,
power distribution, HV boost/negative pump, VPC pump, panel-side capacitors,
and bring-up test pads.

Before PCB layout, verify connector contact side, pin-1 direction, diode
polarity, BS0/BS1 straps, and package choices against parts available in JLC.
"""


def main() -> None:
    configure_base()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{PROJECT}.kicad_pro").write_text(base.make_project(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(base.make_sym_lib_table(), encoding="utf-8")
    local_symbols = base.make_local_symbol_lib()
    (OUT / "mf1750_local.kicad_sym").write_text(local_symbols, encoding="utf-8")
    (OUT / "c73_full_local.kicad_sym").write_text(local_symbols, encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_sch").write_text(make_schematic(), encoding="utf-8")
    (OUT / "bom_reference.csv").write_text(make_bom(), encoding="utf-8")
    (OUT / "mf1750_fpc_pinmap.csv").write_text(make_pinmap(), encoding="utf-8")
    (OUT / "README.md").write_text(make_readme(), encoding="utf-8")
    zip_path = ROOT / "hardware" / "c73_full_mf1750_adapted_jlc_import.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.iterdir():
            zf.write(path, path.name)
    print(OUT)
    print(zip_path)


if __name__ == "__main__":
    main()
