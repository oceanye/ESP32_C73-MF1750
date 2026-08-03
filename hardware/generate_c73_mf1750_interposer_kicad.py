from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware" / "c73_mf1750_interposer_kicad"
PROJECT = "c73_mf1750_interposer"
GRID = 2.54

FPC_FOOTPRINT_NAME = "Connector_FFC-FPC:Hirose_FH12-50S-0.5SH_1x50-1MP_P0.50mm_Horizontal"
HEADER_FOOTPRINT_NAME = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"
R_FOOTPRINT_NAME = "Resistor_SMD:R_0603_1608Metric"


@dataclass(frozen=True)
class PinMap:
    pin: int
    c73: str
    mf1750: str
    net: str | None
    action: str


def uid() -> str:
    return str(uuid.uuid4())


def q(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def grid(value: float) -> float:
    return round(value / GRID) * GRID


PINMAP: list[PinMap] = [
    PinMap(1, "VPP", "NC", None, "Do not pass through"),
    PinMap(2, "TFT_VCOM", "TFT_VCOM", "TFT_VCOM", "Pass through"),
    PinMap(3, "FPL_VCOM", "FPL_VCOM", "FPL_VCOM", "Pass through"),
    PinMap(4, "VDD", "SL_CSB", "SL_CSB", "Panel pin 4 goes to new CS2 header, not C73 P1-4"),
    PinMap(5, "GDRH", "GDRH", "GDRH", "Pass through"),
    PinMap(6, "RESEH", "RESEH", "RESEH", "Pass through"),
    PinMap(7, "GDRL", "GDRL", "GDRL", "Pass through; C73 original marks node NC"),
    PinMap(8, "RESEL", "RESEL", "RESEL", "Pass through"),
    PinMap(9, "GDRC", "GDRC", "GDRC", "Pass through"),
    PinMap(10, "RESEC", "RESEC", "RESEC", "Pass through"),
    PinMap(11, "VPC", "VPC", "VPC", "Pass through"),
    PinMap(12, "GND", "GND", "GND", "Pass through"),
    PinMap(13, "VGL", "VGL", "PREVGL", "Pass through; rail name alias"),
    PinMap(14, "VPH", "VPH", "VPH", "Pass through"),
    PinMap(15, "VSH", "VSH", "VSH", "Pass through"),
    PinMap(16, "VSH_LV", "VSH_LV", "VSH_LV", "Pass through"),
    PinMap(17, "VSH_LV2", "VSH_LV2", "VSH_LV2", "Pass through"),
    PinMap(18, "VSL", "VSL", "VSL", "Pass through"),
    PinMap(19, "VSL_LV", "VSL_LV", "VSL_LV", "Pass through"),
    PinMap(20, "VSL_LV2", "VSL_LV2", "VSL_LV2", "Pass through"),
    PinMap(21, "GND", "GNDA", "GND", "Pass through"),
    PinMap(22, "REFN", "REFN", "REFN", "Pass through"),
    PinMap(23, "REFP", "REFP", "REFP", "Pass through"),
    PinMap(24, "TSCL", "TSCL", "TSCL", "Keep C73 behavior"),
    PinMap(25, "TSDA", "TSDA", "TSDA", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(26, "BS0", "BS0", "BS0", "Keep C73 mode strap behavior"),
    PinMap(27, "BS1", "BS1", "BS1", "Keep C73 mode strap behavior"),
    PinMap(28, "RST_N", "RST_N", "RST_N", "Pass through"),
    PinMap(29, "BUSY_N", "BUSY_N", "BUSY_N", "Pass through"),
    PinMap(30, "DC", "DC", "DC", "Pass through"),
    PinMap(31, "CSB1", "CSB", "CSB", "Pass through main chip select"),
    PinMap(32, "SCL", "SCL", "SCL", "Pass through"),
    PinMap(33, "SI0", "SI0", "SI0", "Pass through"),
    PinMap(34, "SI1", "SI1", "SI1", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(35, "SI2", "SI2", "SI2", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(36, "SI3", "SI3", "SI3", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(37, "VDDD", "VDDD", "VDDD", "Pass through"),
    PinMap(38, "VDD", "VDD", "VDD", "Pass through"),
    PinMap(39, "GND", "GND", "GND", "Pass through"),
    PinMap(40, "VDDIO", "VDDIO", "VDDIO", "Pass through"),
    PinMap(41, "VCP2", "VCP2", "VCP2", "Pass through"),
    PinMap(42, "CP2N", "CP2N", "CP2N", "Pass through"),
    PinMap(43, "CP2P", "CP2P", "CP2P", "Pass through"),
    PinMap(44, "VCP1", "VCP1", "VCP1", "Pass through"),
    PinMap(45, "CP1N", "CP1N", "CP1N", "Pass through"),
    PinMap(46, "CP1P", "CP1P", "CP1P", "Pass through"),
    PinMap(47, "CGH1N", "CGH1N", "CGH1N", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(48, "CGH1P", "CGH1P", "CGH1P", "Keep C73 behavior; C73 original marks node NC"),
    PinMap(49, "VGH", "VGH", "PREVGH", "Pass through; rail name alias"),
    PinMap(50, "VCOMBD", "VCOMBD", "VCOMBD", "Pass through"),
]


def prop(name: str, value: str, x: float, y: float, hidden: bool = False) -> str:
    hide = "\n\t\t\t\t(hide yes)" if hidden else ""
    return (
        f'\t\t(property "{name}" "{q(value)}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font (size 1.27 1.27))"
        f"{hide}\n"
        "\t\t\t)\n"
        "\t\t)"
    )


def symbol_lib_fpc(name: str, source: str) -> str:
    top = 25 * 2.54
    pins = []
    for index, p in enumerate(PINMAP):
        if index < 25:
            pin_x = -15.24
            pin_y = (24 - index) * 2.54
            pin_rot = 0
        else:
            pin_x = 15.24
            pin_y = (49 - index) * 2.54
            pin_rot = 180
        pin_name = p.c73 if source == "c73" else p.mf1750
        pins.append(
            "\t\t\t\t(pin passive line\n"
            f"\t\t\t\t\t(at {pin_x:.2f} {pin_y:.2f} {pin_rot})\n"
            "\t\t\t\t\t(length 5.08)\n"
            f'\t\t\t\t\t(name "{q(pin_name)}" (effects (font (size 0.85 0.85))))\n'
            f'\t\t\t\t\t(number "{p.pin}" (effects (font (size 0.8 0.8))))\n'
            "\t\t\t\t)"
        )
    return "\n".join(
        [
            f'\t\t(symbol "Local:{name}"',
            "\t\t\t(pin_names",
            "\t\t\t\t(offset 1.016)",
            "\t\t\t)",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            '\t\t\t(property "Reference" "J" (at 0 0 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Value" "{name}" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{FPC_FOOTPRINT_NAME}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'\t\t\t(symbol "{name}_0_1"',
            "\t\t\t\t(rectangle",
            "\t\t\t\t\t(start -10 -4.00)",
            f"\t\t\t\t\t(end 10 {top:.2f})",
            "\t\t\t\t\t(stroke (width 0.254) (type default))",
            "\t\t\t\t\t(fill (type background))",
            "\t\t\t\t)",
            "\t\t\t)",
            f'\t\t\t(symbol "{name}_1_1"',
            *pins,
            "\t\t\t)",
            "\t\t)",
        ]
    )


def symbol_lib_header() -> str:
    pins = []
    for idx, name in enumerate(["SL_CSB", "GND", "VDDIO"], start=1):
        y = -2.54 + (idx - 1) * 2.54
        pins.append(
            f'\t\t\t\t(pin passive line (at -7.62 {y:.2f} 0) (length 5.08) '
            f'(name "{name}" (effects (font (size 0.75 0.75)))) '
            f'(number "{idx}" (effects (font (size 0.75 0.75)))))'
        )
    return "\n".join(
        [
            '\t\t(symbol "Local:CS2_HEADER"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            '\t\t\t(property "Reference" "H" (at 0 -6 0) (effects (font (size 1.27 1.27))))',
            '\t\t\t(property "Value" "CS2 header" (at 0 6 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{HEADER_FOOTPRINT_NAME}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            '\t\t\t(symbol "CS2_HEADER_0_1" (rectangle (start -2.54 -5.08) (end 2.54 5.08) (stroke (width 0.2) (type default)) (fill (type none))))',
            '\t\t\t(symbol "CS2_HEADER_1_1"',
            *pins,
            "\t\t\t)",
            "\t\t)",
        ]
    )


def symbol_lib_resistor() -> str:
    return "\n".join(
        [
            '\t\t(symbol "Local:R"',
            "\t\t\t(pin_names (offset 0.508))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            '\t\t\t(property "Reference" "R" (at 0 -3.5 0) (effects (font (size 1.27 1.27))))',
            '\t\t\t(property "Value" "R" (at 0 3.5 0) (effects (font (size 1.27 1.27))))',
            f'\t\t\t(property "Footprint" "{R_FOOTPRINT_NAME}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            '\t\t\t(symbol "R_0_1" (rectangle (start -2.54 -1.27) (end 2.54 1.27) (stroke (width 0.2) (type default)) (fill (type none))))',
            '\t\t\t(symbol "R_1_1"',
            '\t\t\t\t(pin passive line (at -5.08 0 0) (length 2.54) (name "1" (effects (font (size 0.75 0.75)))) (number "1" (effects (font (size 0.75 0.75)))))',
            '\t\t\t\t(pin passive line (at 5.08 0 180) (length 2.54) (name "2" (effects (font (size 0.75 0.75)))) (number "2" (effects (font (size 0.75 0.75)))))',
            "\t\t\t)",
            "\t\t)",
        ]
    )


def local_symbol_defs() -> list[str]:
    return [
        symbol_lib_fpc("C73_P1_50PIN", "c73"),
        symbol_lib_fpc("MF1750_PANEL_50PIN", "mf1750"),
        symbol_lib_header(),
        symbol_lib_resistor(),
    ]


def symbol_instance(lib_id: str, ref: str, value: str, footprint: str, x: float, y: float, pins: list[str]) -> str:
    lines = [
        "\t(symbol",
        f'\t\t(lib_id "{q(lib_id)}")',
        f"\t\t(at {x:.2f} {y:.2f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        "\t\t(in_bom yes)",
        "\t\t(on_board yes)",
        "\t\t(dnp no)",
        f'\t\t(uuid "{uid()}")',
        prop("Reference", ref, x, y - 4.0),
        prop("Value", value, x, y + 4.0),
        prop("Footprint", footprint, x, y, True),
        prop("Datasheet", "", x, y, True),
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


def make_project() -> str:
    return json.dumps(
        {
            "meta": {"version": 1, "filename": f"{PROJECT}.kicad_pro"},
            "schematic": {"drawing": {"default_line_thickness": 6, "default_text_size": 50}, "meta": {"version": 1}},
            "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        },
        indent=2,
    )


def make_sym_lib_table() -> str:
    return (
        "(sym_lib_table\n"
        '\t(lib (name "Local") (type "KiCad") (uri "${KIPRJMOD}/c73_mf1750_interposer_local.kicad_sym") '
        '(options "") (descr "Local symbols for C73 to MF-1750 interposer"))\n'
        ")\n"
    )


def make_local_symbol_lib() -> str:
    body = "\n".join(local_symbol_defs()).replace('\t\t(symbol "Local:', '\t(symbol "')
    return (
        "(kicad_symbol_lib\n"
        "\t(version 20250114)\n"
        '\t(generator "kicad_symbol_editor")\n'
        '\t(generator_version "10.0")\n'
        f"{body}\n"
        ")\n"
    )


def connector_pin_point(x: float, y: float, pin: int) -> tuple[float, float, str]:
    index = pin - 1
    if index < 25:
        return x - 15.24, y - (24 - index) * 2.54, "left"
    return x + 15.24, y - (49 - index) * 2.54, "right"


def connect_label(lines: list[str], px: float, py: float, net: str, side: str) -> None:
    if side == "left":
        lx = px - 7.62
        lines.append(wire(px, py, lx, py))
        lines.append(label(net, lx, py, 0, "left"))
    else:
        lx = px + 7.62
        lines.append(wire(px, py, lx, py))
        lines.append(label(net, lx, py, 180, "right"))


def make_schematic() -> str:
    host_x, panel_x, origin_y = grid(70), grid(190), grid(105)
    header_x, header_y = grid(270), grid(92)
    lines = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{uid()}")',
        '\t(paper "A3")',
        "\t(title_block",
        '\t\t(title "DESPI-C73 to MF-1750 Pin-4 Interposer")',
        '\t\t(company "Generated in ESP32_C73 workspace")',
        "\t)",
        "\t(lib_symbols",
        *local_symbol_defs(),
        "\t)",
        symbol_instance("Local:C73_P1_50PIN", "J_HOST", "DESPI-C73 P1 50pin", FPC_FOOTPRINT_NAME, host_x, origin_y, [str(p.pin) for p in PINMAP]),
        symbol_instance("Local:MF1750_PANEL_50PIN", "J_PANEL", "MF-1750 panel 50pin", FPC_FOOTPRINT_NAME, panel_x, origin_y, [str(p.pin) for p in PINMAP]),
        symbol_instance("Local:CS2_HEADER", "H_CS2", "SL_CSB / CS2", HEADER_FOOTPRINT_NAME, header_x, header_y, ["1", "2", "3"]),
        symbol_instance("Local:R", "R_SL", "47k DNP/optional", R_FOOTPRINT_NAME, header_x, header_y - 17.78, ["1", "2"]),
    ]

    for row in PINMAP:
        hx, hy, hside = connector_pin_point(host_x, origin_y, row.pin)
        px, py, pside = connector_pin_point(panel_x, origin_y, row.pin)
        if row.pin == 1:
            lines.append(no_connect(hx, hy))
            lines.append(no_connect(px, py))
            continue
        if row.pin == 4:
            lines.append(no_connect(hx, hy))
            connect_label(lines, px, py, "SL_CSB", pside)
            continue
        if row.net:
            connect_label(lines, hx, hy, row.net, hside)
            connect_label(lines, px, py, row.net, pside)
        if row.pin in {7, 25, 34, 35, 36, 47, 48}:
            lines.append(text_note("C73 NC", hx + 5, hy + 0.8, 0.7))

    # Panel pin 4 is the only intentional reroute.
    lines.append(wire(header_x - 7.62, header_y - 2.54, header_x - 20.32, header_y - 2.54))
    lines.append(label("SL_CSB", header_x - 20.32, header_y - 2.54))
    lines.append(wire(header_x - 7.62, header_y, header_x - 20.32, header_y))
    lines.append(label("GND", header_x - 20.32, header_y))
    lines.append(wire(header_x - 7.62, header_y + 2.54, header_x - 20.32, header_y + 2.54))
    lines.append(label("VDDIO", header_x - 20.32, header_y + 2.54))
    lines.append(wire(header_x - 5.08, header_y - 17.78, header_x - 20.32, header_y - 17.78))
    lines.append(label("SL_CSB", header_x - 20.32, header_y - 17.78))
    lines.append(wire(header_x + 5.08, header_y - 17.78, header_x + 20.32, header_y - 17.78))
    lines.append(label("VDDIO", header_x + 20.32, header_y - 17.78))

    notes = [
        "C73-based interposer: all compatible P1 pins pass through directly.",
        "Do not connect DESPI-C73 P1 pin 4 VDD to MF-1750 pin 4.",
        "MF-1750 pin 4 is SL_CSB and must be driven by a second ESP32 chip-select GPIO.",
        "Panel pin 1 is NC; do not pass C73 VPP through.",
        "This schematic intentionally reuses the DESPI-C73 HV driver and mode straps.",
    ]
    for i, note in enumerate(notes):
        lines.append(text_note(note, 25, 190 + i * 6, 1.05))

    lines += ["\t(sheet_instances", '\t\t(path "/" (page "1"))', "\t)", ")"]
    return "\n".join(lines) + "\n"


def make_pinmap() -> str:
    rows = ["pin,c73_original,mf1750_target,adapter_net,action"]
    for row in PINMAP:
        rows.append(f"{row.pin},{row.c73},{row.mf1750},{row.net or ''},{row.action}")
    return "\n".join(rows) + "\n"


def make_readme() -> str:
    return """# DESPI-C73 to MF-1750 Pin-4 Interposer

This KiCad project is the C73-based adaptation path. It preserves the original
DESPI-C73 high-voltage driver and 50-pin panel support circuitry.

Status: schematic import package for JLC/KiCad review. KiCad ERC is clean in
`erc.rpt`; still verify connector contact side and pin-1 orientation before PCB
layout or fabrication.

Intentional differences from DESPI-C73:

- C73 P1 pin 1 `VPP` is not passed to MF-1750 pin 1 `NC`.
- C73 P1 pin 4 `VDD` is not passed to MF-1750 pin 4.
- MF-1750 pin 4 `SL_CSB` is routed to `H_CS2` for a second ESP32 chip-select.
- `R_SL` is an optional weak pull-up from `SL_CSB` to `VDDIO`.

Everything else is pass-through unless the C73 original already leaves that
node unconnected internally.

See also:

- `../c73_original_mf1750_delta.md`
- `../despi_c73_mf1750_pinmap.csv`
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{PROJECT}.kicad_pro").write_text(make_project(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(make_sym_lib_table(), encoding="utf-8")
    (OUT / "c73_mf1750_interposer_local.kicad_sym").write_text(make_local_symbol_lib(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_sch").write_text(make_schematic(), encoding="utf-8")
    (OUT / "pinmap_delta.csv").write_text(make_pinmap(), encoding="utf-8")
    (OUT / "README.md").write_text(make_readme(), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
