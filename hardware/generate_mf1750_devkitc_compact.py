"""Generate a compact MF-1750 carrier for ESP32-S3-DevKitC-1 N16R8.

This is an independent Rev B0 engineering layout.  It deliberately leaves the
verified 80 x 75 mm Rev A1 manufacturing handoff untouched.  The electrical
MF-1750 power stage and packages are retained; area is reduced by rotating and
stacking a socketed DevKitC-1 over the lower half of the carrier.

The proven independent-CS population is the default here: R16 fitted, R15 DNP.
The socket does not connect either DevKitC 3V3 pin.  J3 is the load-bearing,
current-limited external EPD 3V3 input; fitted R4/R8 distribute that rail to
EPD_3V3 and V_B.  TP1/TP2 are bottom-side measurement pads only.  The
USB-powered DevKitC and panel power domain share ground and seven direct GPIO
signals, but no power rail.  Because the GPIOs have no Ioff isolation, firmware
must hold them high impedance whenever J3 is off.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import replace
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
OUT = HARDWARE / "mf1750_devkitc_compact"
PROJECT = "mf1750_devkitc_compact"
KICAD = Path(r"C:\Program Files\KiCad\10.0\share\kicad")

sys.path.insert(0, str(HARDWARE))
import generate_mf1750_kicad_project as base  # noqa: E402
import generate_mf1750_production_v1 as a1  # noqa: E402


BOARD_W_MM = 62.0
BOARD_H_MM = 58.0
FPC_X_MM = 31.0
FPC_Y_MM = 5.0
DEVKIT_X_MM = 5.5
DEVKIT_Y_MM = 56.0
DEVKIT_ROTATION_DEG = 90.0

DEVKIT_FOOTPRINT_NAME = "MF1750_Compact:ESP32-S3-DevKitC-1_Socket"
LOCAL_LIB_DIR = OUT / "MF1750_Compact.pretty"
DEVKIT_FOOTPRINT = LOCAL_LIB_DIR / "ESP32-S3-DevKitC-1_Socket.kicad_mod"
MOUNTING_HOLE = (
    KICAD / "footprints" / "MountingHole.pretty" / "MountingHole_2.5mm.kicad_mod"
)
POWER_TESTPOINT = (
    KICAD
    / "footprints"
    / "TestPoint.pretty"
    / "TestPoint_THTPad_D2.0mm_Drill1.0mm.kicad_mod"
)
POWER_TESTPOINT_NAME = "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm"
POWER_CONNECTOR = (
    KICAD
    / "footprints"
    / "Connector_JST.pretty"
    / ("JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal.kicad_mod")
)
POWER_CONNECTOR_NAME = "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal"
POWER_CONNECTOR_PINS = [
    base.Pin(1, "EPD 3V3 IN", "3V3"),
    base.Pin(2, "GND", "GND"),
]


# Official ESP32-S3-DevKitC-1 J1/J3 numbering.  Only the current verified EPD
# GPIOs and power/ground pins receive nets; every other header pad is NC on the
# carrier, so the development board remains removable and reusable.
DEVKIT_PINS: list[base.Pin] = [
    base.Pin(1, "J1-1 3V3 (isolated)", None),
    base.Pin(2, "J1-2 3V3 (isolated)", None),
    base.Pin(3, "J1-3 RST/EN", None),
    base.Pin(4, "J1-4 GPIO4 / BUSY_N", "BUSY_N"),
    base.Pin(5, "J1-5 GPIO5 / RST_N", "RST_N"),
    base.Pin(6, "J1-6 GPIO6 / DC", "DC"),
    base.Pin(7, "J1-7 GPIO7 / CSB", "CSB"),
    base.Pin(8, "J1-8 GPIO15", None),
    base.Pin(9, "J1-9 GPIO16", None),
    base.Pin(10, "J1-10 GPIO17", None),
    base.Pin(11, "J1-11 GPIO18", None),
    base.Pin(12, "J1-12 GPIO8", None),
    base.Pin(13, "J1-13 GPIO3", None),
    base.Pin(14, "J1-14 GPIO46", None),
    base.Pin(15, "J1-15 GPIO9", None),
    base.Pin(16, "J1-16 GPIO10 / CS2", "CS2"),
    base.Pin(17, "J1-17 GPIO11 / SI0", "SI0"),
    base.Pin(18, "J1-18 GPIO12 / SCL", "SCL"),
    base.Pin(19, "J1-19 GPIO13", None),
    base.Pin(20, "J1-20 GPIO14", None),
    base.Pin(21, "J1-21 5V", None),
    base.Pin(22, "J1-22 GND", "GND"),
    base.Pin(23, "J3-22 GND", "GND"),
    base.Pin(24, "J3-21 GND", "GND"),
    base.Pin(25, "J3-20 GPIO19/USB_D-", None),
    base.Pin(26, "J3-19 GPIO20/USB_D+", None),
    base.Pin(27, "J3-18 GPIO21", None),
    base.Pin(28, "J3-17 GPIO47", None),
    base.Pin(29, "J3-16 GPIO48", None),
    base.Pin(30, "J3-15 GPIO45", None),
    base.Pin(31, "J3-14 GPIO0", None),
    base.Pin(32, "J3-13 GPIO35", None),
    base.Pin(33, "J3-12 GPIO36", None),
    base.Pin(34, "J3-11 GPIO37", None),
    base.Pin(35, "J3-10 GPIO38", None),
    base.Pin(36, "J3-9 GPIO39", None),
    base.Pin(37, "J3-8 GPIO40", None),
    base.Pin(38, "J3-7 GPIO41", None),
    base.Pin(39, "J3-6 GPIO42", None),
    base.Pin(40, "J3-5 GPIO2", None),
    base.Pin(41, "J3-4 GPIO1", None),
    base.Pin(42, "J3-3 GPIO44/RX", None),
    base.Pin(43, "J3-2 GPIO43/TX", None),
    base.Pin(44, "J3-1 GND", "GND"),
]


def _parts() -> list[base.Part2]:
    result: list[base.Part2] = []
    for part in a1.PARTS_2PIN:
        if part.ref == "R4":
            result.append(
                replace(
                    part,
                    value="0R",
                    note="FIT: distributes J3 external EPD 3V3 input to EPD_3V3",
                )
            )
        elif part.ref == "R15":
            result.append(
                replace(
                    part,
                    value="0R DNP",
                    note="DNP: independent CS configuration verified on real panel",
                )
            )
        elif part.ref == "R16":
            result.append(
                replace(
                    part,
                    value="0R",
                    note="FIT: routes GPIO10/CS2 to SL_CSB; real-panel verified configuration",
                )
            )
        else:
            result.append(part)
    return result


FPC_PINS = a1.FPC_PINS
MCU_PINS = DEVKIT_PINS
PARTS_2PIN = _parts()
PARTS_3PIN = a1.PARTS_3PIN
TESTPOINT_NETS = [
    "3V3",
    "GND",
    "VPH",
    "PREVGH",
    "PREVGL",
    "VPC",
    "VDDIO",
    "CSB",
    "SL_CSB",
    "BUSY_N",
]

SCHEMATIC_REFS = (
    ["J1", "J2", "J3"]
    + [part.ref for part in PARTS_2PIN]
    + [part.ref for part in PARTS_3PIN]
)
SCHEMATIC_REFS += [f"TP{idx}" for idx in range(1, len(TESTPOINT_NETS) + 1)]
SCHEMATIC_UUID = base.uuid.uuid5(base.uuid.NAMESPACE_URL, f"{PROJECT}/root-sheet")
SYMBOL_UUIDS = {
    ref: str(base.uuid.uuid5(base.uuid.NAMESPACE_URL, f"{PROJECT}/symbol/{ref}"))
    for ref in SCHEMATIC_REFS
}


def patch_base_globals() -> None:
    base.OUT = OUT
    base.PROJECT = PROJECT
    base.FPC_FOOTPRINT = a1.FPC_FOOTPRINT
    base.FPC_FOOTPRINT_NAME = a1.FPC_FOOTPRINT_NAME
    base.MCU_FOOTPRINT = DEVKIT_FOOTPRINT
    base.MCU_FOOTPRINT_NAME = DEVKIT_FOOTPRINT_NAME
    base.FPC_PINS = FPC_PINS
    base.MCU_PINS = MCU_PINS
    base.PARTS_2PIN = PARTS_2PIN
    base.PARTS_3PIN = PARTS_3PIN
    base.TESTPOINT_NETS = TESTPOINT_NETS
    base.RESERVED_TEST_NETS = []
    base.symbol_instance = production_symbol_instance
    base.footprint_name_for_part2 = a1.footprint_name_for_part2
    base.footprint_path_for_part2 = a1.footprint_path_for_part2
    base.footprint_name_for_part3 = a1.footprint_name_for_part3
    base.footprint_path_for_part3 = a1.footprint_path_for_part3
    base.local_symbol_defs = local_symbol_defs
    base.place_connector_labels = compact_place_connector_labels
    base.place_part3 = a1.place_part3
    base.patch_footprint = a1.production_patch_footprint
    base.NETS = base.all_nets()
    for pin in FPC_PINS:
        if pin.net is None:
            name = f"unconnected-(J1-{pin.name}-Pad{pin.number})"
            base.NETS[name] = len(base.NETS) + 1
    for pin in MCU_PINS:
        if pin.net is None:
            name = schematic_nc_net(pin)
            base.NETS[name] = len(base.NETS) + 1


def schematic_nc_net(pin: base.Pin) -> str:
    """Mirror KiCad's private-net escaping for an explicit no-connect pin."""
    escaped = pin.name.replace("/", "{slash}").replace(" ", "_")
    return f"unconnected-(J2-{escaped}-Pad{pin.number})"


def compact_place_connector_labels(
    lines: list[str],
    x: float,
    y: float,
    pins: list[base.Pin],
    left_count: int,
) -> None:
    """Correct the base schematic's legacy hard-coded 10-pin J2 split."""
    effective_left_count = 22 if pins is MCU_PINS else left_count
    for index, pin in enumerate(pins):
        if index < effective_left_count:
            py = y - (effective_left_count - 1 - index) * 2.54
            px = x - 15.24
            side = "left"
        else:
            py = y - (len(pins) - index - 1) * 2.54
            px = x + 15.24
            side = "right"
        if pin.net:
            base.connect_pin_to_label(lines, px, py, pin.net, side)
        else:
            lines.append(base.no_connect(px, py))


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
    symbol_id = SYMBOL_UUIDS[ref]
    lines = [
        "\t(symbol",
        f'\t\t(lib_id "{base.q(lib_id)}")',
        f"\t\t(at {x:.2f} {y:.2f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        f"\t\t(in_bom {'no' if ref.startswith('TP') else 'yes'})",
        "\t\t(on_board yes)",
        f"\t\t(dnp {'yes' if dnp else 'no'})",
        f'\t\t(uuid "{symbol_id}")',
        base.prop("Reference", ref, x, y - 4.0),
        base.prop("Value", value, x, y + 3.5),
        base.prop("Footprint", footprint, x, y, True),
        base.prop("Datasheet", "", x, y, True),
        base.prop("Description", "", x, y, True),
    ]
    for pin in pins:
        lines.extend([f'\t\t(pin "{pin}"', f'\t\t\t(uuid "{base.uid()}")', "\t\t)"])
    lines.extend(
        [
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
    )
    return "\n".join(lines)


def local_symbol_defs() -> list[str]:
    return [
        base.symbol_lib_connector("MF1750_FPC50", FPC_PINS, 25, a1.FPC_FOOTPRINT_NAME),
        # base.make_schematic() instantiates this legacy local-library name.
        # Keep the identifier stable while replacing its body with the full
        # DevKitC 2x22 pinout; otherwise ERC sees an unresolved 10-pin symbol.
        base.symbol_lib_connector(
            "ESP32_SPI_10PIN", MCU_PINS, 22, DEVKIT_FOOTPRINT_NAME
        ),
        base.symbol_lib_connector(
            "EPD_POWER_IN", POWER_CONNECTOR_PINS, 1, POWER_CONNECTOR_NAME
        ),
        base.symbol_lib_two_pin("R", "R", base.R_0603_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("C", "C", base.C_0603_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("L", "L", a1.INDUCTOR_FOOTPRINT_NAME),
        base.symbol_lib_two_pin("D_SCH", "D", base.D_SOD123_FOOTPRINT_NAME, "K", "A"),
        a1.fet_symbol("NMOS", a1.SC70_FOOTPRINT_NAME),
        a1.fet_symbol("PMOS", a1.SOT23_FOOTPRINT_NAME),
        base.symbol_lib_testpoint(),
    ]


# Compact placement keeps the 50-pin support parts adjacent to J1, the two
# switching stages at the left/right edges, and low-profile logic/power links
# in the socketed DevKitC cavity.  Values are footprint origins in mm.
PART_POSITIONS: dict[str, tuple[float, float, float]] = {
    "C13": (5.5, 14.0, 270),
    "C14": (10.0, 14.0, 270),
    "R2": (14.0, 14.0, 270),
    "C7": (18.0, 14.5, 270),
    "C8": (22.0, 14.5, 270),
    "C9": (26.0, 14.5, 270),
    "C10": (30.0, 14.5, 270),
    "C11": (34.0, 14.5, 270),
    "C12": (38.0, 14.5, 270),
    "C21": (42.5, 14.0, 270),
    "C20": (46.0, 14.0, 270),
    "R9": (42.5, 18.5, 270),
    "R10": (46.0, 18.5, 270),
    "R12": (50.0, 12.0, 0),
    "R13": (54.0, 12.0, 0),
    "C1": (41.5, 22.0, 0),
    "C19": (45.0, 21.5, 0),
    "C18": (49.0, 22.0, 0),
    "C17": (53.0, 21.5, 0),
    "C16": (57.0, 21.5, 0),
    "C15": (58.5, 16.0, 270),
    # Keep both switch-current loops above the inner DevKitC socket row.  The
    # row occupies y=33.14 mm and must not share copper/courtyard with parts.
    "C0": (3.5, 28.5, 270),
    "L1": (9.5, 27.5, 0),
    "D1": (16.8, 29.2, 180),
    "C2": (22.5, 29.0, 0),
    "R5": (27.0, 29.0, 90),
    "R1": (20.5, 25.0, 0),
    "C22": (34.0, 29.2, 180),
    "L2": (46.0, 27.5, 0),
    "D4": (53.5, 29.2, 0),
    "C6": (59.5, 29.0, 90),
    "R3": (57.0, 25.0, 0),
    # Low-profile pump/link parts sit inside the socketed-board cavity.  Use
    # the specified >=11 mm stacking sockets so the daughterboard cannot foul
    # the tallest 1210 part in this area.
    "C4": (5.0, 38.0, 0),
    "D2": (10.5, 38.0, 180),
    "D3": (16.0, 38.0, 0),
    "C5": (21.5, 38.0, 0),
    "R4": (4.0, 44.0, 0),
    "R8": (8.0, 44.0, 0),
    "C23": (13.0, 44.0, 0),
    "R6": (18.5, 44.0, 0),
    "R7": (22.5, 44.0, 0),
    "C3": (27.0, 44.0, 0),
    "R15": (36.0, 38.0, 0),
    "R16": (40.0, 38.0, 0),
}
Q_POSITIONS = {"Q1": (16.5, 25.0, 90), "Q2": (39.0, 28.5, 0)}
TP_POSITIONS = {
    # Measurement pads are reachable from the bottom with the module fitted.
    # The load-bearing power entry is J3, not TP1/TP2.
    "TP1": (4.0, 48.0, 0),
    "TP2": (8.0, 48.0, 0),
    # Rail probes stay next to the associated power-stage parts, avoiding long
    # test-point stubs across the stacked DevKitC cavity.
    "TP3": (24.5, 25.0, 0),
    "TP4": (28.5, 25.0, 0),
    "TP5": (24.5, 41.0, 0),
    "TP6": (60.0, 20.0, 0),
    "TP7": (29.0, 41.0, 0),
    "TP8": (36.0, 51.5, 0),
    "TP9": (41.0, 51.5, 0),
    "TP10": (52.0, 51.5, 0),
}
# Put the right-angle JST-PH at the top edge so its mating direction is clear
# of both the stacked DevKitC and the panel FPC.  The plastic body deliberately
# overhangs the carrier; both plated pins remain inside the board outline.
POWER_CONNECTOR_POSITION = (11.5, 1.8, 180.0)


def make_devkit_footprint() -> str:
    """Create a socket footprint from Espressif's official 2x22 geometry."""
    # The 2x22/22.86 mm header geometry follows Espressif's published DevKitC
    # layout.  It is re-emitted in KiCad 10 syntax here; the full mechanical
    # envelope still requires a measurement of the user's exact N16R8 board.
    lines = [
        '(footprint "ESP32-S3-DevKitC-1_Socket"',
        "\t(version 20260206)",
        '\t(generator "pcbnew")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        '\t(descr "ESP32-S3-DevKitC-1 socket; Espressif official 2x22 geometry")',
        '\t(tags "ESP32-S3 DevKitC socket N16R8")',
        '\t(property "Reference" "REF**" (at 11.43 -2.1 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
        '\t(property "Value" "ESP32-S3-DevKitC-1 N16R8 SOCKET" (at 11.43 29.46 90) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
        "\t(attr through_hole exclude_from_pos_files)",
        # The full daughterboard outline is mechanical documentation, not the
        # solder courtyard.  Two disjoint courtyards reserve the female header
        # rows while deliberately permitting low-profile parts in the stacked
        # cavity between them.
        '\t(fp_rect (start -1.50 -1.10) (end 24.36 62.79728) (stroke (width 0.12) (type solid)) (fill none) (layer "F.Fab"))',
        '\t(fp_rect (start -1.25 -0.85) (end 1.25 54.19) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
        '\t(fp_rect (start 21.61 -0.85) (end 24.11 54.19) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
        '\t(fp_rect (start 2.46012 -7.01312) (end 20.44332 -1.12032) (stroke (width 0.12) (type solid)) (fill none) (layer "F.Fab"))',
        '\t(fp_text user "USB" (at 11.43 -4.0 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
        '\t(fp_text user "ANTENNA" (at 11.43 59.5 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
    ]
    for number in range(1, 23):
        shape = "rect" if number == 1 else "oval"
        lines.extend(
            [
                f'\t(pad "{number}" thru_hole {shape}',
                f"\t\t(at 0 {(number - 1) * 2.54:.5f} 270)",
                "\t\t(size 1.2 2)",
                "\t\t(drill 0.8)",
                '\t\t(layers "*.Cu" "*.Mask")',
                "\t)",
            ]
        )
    for number in range(23, 45):
        y = (44 - number) * 2.54
        lines.extend(
            [
                f'\t(pad "{number}" thru_hole oval',
                f"\t\t(at 22.86 {y:.5f} 270)",
                "\t\t(size 1.2 2)",
                "\t\t(drill 0.8)",
                '\t\t(layers "*.Cu" "*.Mask")',
                "\t)",
            ]
        )
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    return "\n".join(lines)


def _mark_dnp(text: str, dnp: bool) -> str:
    return text.replace("(attr smd)", "(attr smd dnp)", 1) if dnp else text


def make_board_unrouted() -> str:
    nets = ['\t(net 0 "")'] + [
        f'\t(net {idx} "{name if name.startswith("unconnected-") else "/" + name}")'
        for name, idx in sorted(base.NETS.items(), key=lambda item: item[1])
    ]
    footprints: list[str] = [
        base.patch_footprint(
            a1.FPC_FOOTPRINT,
            a1.FPC_FOOTPRINT_NAME,
            "J1",
            "FPC-05FB-50PH20",
            FPC_X_MM,
            FPC_Y_MM,
            180,
            {str(pin.number): pin.net for pin in FPC_PINS if pin.net},
        ),
        base.patch_footprint(
            DEVKIT_FOOTPRINT,
            DEVKIT_FOOTPRINT_NAME,
            "J2",
            "ESP32-S3-DevKitC-1-N16R8_SOCKET",
            DEVKIT_X_MM,
            DEVKIT_Y_MM,
            DEVKIT_ROTATION_DEG,
            {str(pin.number): pin.net for pin in MCU_PINS if pin.net},
        ),
        base.patch_footprint(
            POWER_CONNECTOR,
            POWER_CONNECTOR_NAME,
            "J3",
            "EPD_3V3_IN_JST_PH",
            *POWER_CONNECTOR_POSITION,
            {"1": "3V3", "2": "GND"},
        ),
    ]
    # KiCad's schematic-parity checker models explicit no-connect pins as
    # private unconnected-* nets.  Give the unused socket pads the same names;
    # they remain electrically isolated from one another and from all rails.
    devkit = footprints[1]
    for pin in MCU_PINS:
        if pin.net is not None:
            continue
        name = schematic_nc_net(pin)
        code = base.NETS[name]
        marker = f'\t(pad "{pin.number}"'
        start = devkit.find(marker)
        if start < 0:
            raise RuntimeError(f"DevKit footprint missing pad {pin.number}")
        end = devkit.find("\n\t)", start)
        devkit = devkit[:end] + f'\n\t\t(net {code} "{name}")' + devkit[end:]
    footprints[1] = devkit
    # J3's moulded body intentionally overhangs the top edge.  Keep its full
    # outline on the assembly layer and use the explicit bottom legend below
    # instead of clipping silkscreen at the board edge.
    footprints[-1] = footprints[-1].replace('"F.SilkS"', '"F.Fab"')
    for part in PARTS_2PIN:
        footprint = base.patch_footprint(
            base.footprint_path_for_part2(part),
            base.footprint_name_for_part2(part),
            part.ref,
            part.value,
            *PART_POSITIONS[part.ref],
            {"1": part.net1, "2": part.net2},
        )
        footprints.append(
            _mark_dnp(footprint, "DNP" in part.value or part.value == "NC")
        )
    for part in PARTS_3PIN:
        x, y, rotation = Q_POSITIONS[part.ref]
        footprints.append(
            base.patch_footprint(
                base.footprint_path_for_part3(part),
                base.footprint_name_for_part3(part),
                part.ref,
                part.value,
                x,
                y,
                rotation,
                {number: net for number, _name, net in part.pins},
            )
        )
    for index, net in enumerate(TESTPOINT_NETS, start=1):
        ref = f"TP{index}"
        source = base.TP_FOOTPRINT
        footprint_name = base.TP_FOOTPRINT_NAME
        testpoint = base.patch_footprint(
            source,
            footprint_name,
            ref,
            net,
            *TP_POSITIONS[ref],
            {"1": net},
        )
        # Test points are probed from the carrier bottom after the DevKitC is
        # installed, so place their SMD pad/mask and outline on the back side.
        testpoint = testpoint.replace('\t(layer "F.Cu")', '\t(layer "B.Cu")', 1)
        testpoint = testpoint.replace('"F.Cu" "F.Mask"', '"B.Cu" "B.Mask"')
        testpoint = testpoint.replace('"F.SilkS"', '"B.SilkS"')
        testpoint = testpoint.replace('"F.CrtYd"', '"B.CrtYd"')
        testpoint = testpoint.replace('"F.Fab"', '"B.Fab"')
        footprints.append(testpoint)
    for ref, x, y in (("H1", 3.5, 3.5), ("H2", 58.5, 3.5)):
        mounting = base.patch_footprint(
            MOUNTING_HOLE,
            "MountingHole:MountingHole_2.5mm",
            ref,
            "M2.5_NPTH",
            x,
            y,
            0,
            {},
        )
        mounting = mounting.replace(
            "(attr exclude_from_pos_files exclude_from_bom)",
            "(attr board_only exclude_from_pos_files exclude_from_bom)",
        )
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
        + "\n".join(nets)
        + "\n"
        + f'\t(gr_rect (start 0 0) (end {BOARD_W_MM:g} {BOARD_H_MM:g}) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts"))\n'
        + '\t(gr_text "MF1750 COMPACT B0" (at 30 46.5 0) (layer "B.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))\n'
        + '\t(gr_text "PIN1 >" (at 13 8.3 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))\n'
        + '\t(gr_text "USB LEFT" (at 2.2 45.0 90) (layer "F.SilkS") (effects (font (size 0.65 0.65) (thickness 0.11))))\n'
        + '\t(gr_text "ANT RIGHT" (at 60.6 44.5 90) (layer "F.SilkS") (effects (font (size 0.65 0.65) (thickness 0.11))))\n'
        + '\t(gr_text "J2.1" (at 5.5 54.0 0) (layer "F.SilkS") (effects (font (size 0.65 0.65) (thickness 0.11))))\n'
        + '\t(gr_text "GND | +3V3" (at 10.5 4.35 0) (layer "F.SilkS") (effects (font (size 0.65 0.65) (thickness 0.11))))\n'
        + '\t(gr_text "R16 FIT / R15 DNP" (at 38 35.6 0) (layer "F.SilkS") (effects (font (size 0.65 0.65) (thickness 0.11))))\n'
        + '\t(gr_text "R16 FIT / R15 DNP" (at 45 36.0 0) (layer "B.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))\n'
        + '\t(gr_text "J3 P1=3V3 P2=GND" (at 11.5 5.2 0) (layer "B.SilkS") (effects (font (size 0.7 0.7) (thickness 0.11)) (justify mirror)))\n'
        + "\n".join(footprints)
        + "\n)\n"
    )


def make_schematic() -> str:
    text = base.make_schematic()
    text = re.sub(
        r'(^\(kicad_sch\s+\(version [^)]+\)\s+\(generator "[^"]+"\)\s+'
        r'\(generator_version "[^"]+"\)\s+\(uuid ")[^"]+',
        rf"\g<1>{SCHEMATIC_UUID}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    replacements = {
        "MF-1750 / M009F-T Full 50-pin Driver - Reference Schematic Draft": "MF-1750 DevKitC Compact Carrier Rev B0",
        "Generated in ESP32_C73 workspace": "62 x 58 mm engineering layout; R16 independent CS",
        "ESP32 SPI 10pin": "ESP32-S3-DevKitC-1-N16R8 socket",
        "Critical fix versus DESPI-C73: J1 pin 4 is SL_CSB and must route to an ESP32 GPIO as CS2.": "Verified topology: R16 fitted routes SL_CSB to DevKitC GPIO10; R15 is DNP.",
        "After board bring-up, firmware should enable EPD_PIN_CS2 and drive both CSB and SL_CSB for full 1024x600 refresh.": "GPIO7 drives CSB and GPIO10 independently drives SL_CSB; never fit R15 and R16 together.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    insertion = base.symbol_instance(
        "Local:EPD_POWER_IN",
        "J3",
        "EPD 3V3 IN",
        POWER_CONNECTOR_NAME,
        284.48,
        111.76,
        ["1", "2"],
    )
    power_labels: list[str] = []
    compact_place_connector_labels(
        power_labels, 284.48, 111.76, POWER_CONNECTOR_PINS, 1
    )
    text = text.replace(
        "\t(sheet_instances",
        insertion + "\n" + "\n".join(power_labels) + "\n\t(sheet_instances",
        1,
    )
    return text


def make_footprint_table() -> str:
    return (
        "(fp_lib_table\n"
        '\t(lib (name "MF1750_Compact") (type "KiCad") (uri "${KIPRJMOD}/MF1750_Compact.pretty") (options "") (descr "Compact carrier local footprints"))\n'
        '\t(lib (name "MF1750_Production") (type "KiCad") (uri "${KIPRJMOD}/../mf1750_production_v1/MF1750_Production.pretty") (options "") (descr "Verified MF1750 FPC and inductor footprints"))\n'
        ")\n"
    )


def make_reference_bom() -> str:
    rows = list(csv.reader(StringIO(a1.make_reference_bom())))
    rows = [row for row in rows if not row or row[0] != "J2"]
    rows.insert(
        2,
        [
            "J2",
            "ESP32-S3-DevKitC-1-N16R8 socket",
            DEVKIT_FOOTPRINT_NAME,
            "",
            "Espressif",
            "ESP32-S3-DevKitC-1-N16R8 + 2x 1x22 stacking female socket",
            "Manual",
            "Exact N16R8; 22.86 mm rows; installed board spacing >=11 mm; manual/DNP from SMT",
        ],
    )
    rows.insert(
        3,
        [
            "J3",
            "EPD 3V3 INPUT",
            POWER_CONNECTOR_NAME,
            "",
            "JST",
            "S2B-PH-K + PHR-2 housing + wire-gauge-matched PH crimp contacts",
            "Manual",
            "Hand-fit keyed horizontal input; pin1=3V3, pin2=GND",
        ],
    )
    for row in rows:
        if not row:
            continue
        if row[0] == "R4":
            row[1] = "0R"
            row[6] = "No"
            row[7] = "FIT; J3 external EPD 3V3 to EPD_3V3"
        elif row[0] == "R8":
            row[1] = "0R"
            row[6] = "No"
            row[7] = "FIT; J3 external EPD 3V3 to V_B"
        elif row[0] == "R15":
            row[1] = "0R DNP"
            row[6] = "Yes"
            row[7] = "DNP; do not fit with R16"
        elif row[0] == "R16":
            row[1] = "0R"
            row[6] = "No"
            row[7] = "FIT; verified independent CS2 to SL_CSB"
        elif row[0] in {"TP1", "TP2"}:
            row[7] = (
                "Bottom-side measurement pad only; never use as the panel supply connector"
            )
    stream = StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue()


def make_readme() -> str:
    return """# MF-1750 DevKitC Compact Carrier Rev B0

> Generator staging document only.  The board is unrouted and unverified until
> the complete routing/import/finalization/verification chain passes.  Do not
> use this file or `unrouted_source.kicad_pcb` as a manufacturing handoff.

Independent engineering revision; the verified Rev A1 manufacturing handoff is
unchanged.

- 62 x 58 mm, 2 layers, 1.6 mm FR-4, Top-side SMT.
- Socketed ESP32-S3-DevKitC-1 N16R8, rotated 90 degrees.  USB overhangs the
  left edge and the WROOM PCB antenna overhangs the right edge.
- J2 uses Espressif's official 2x22, 22.86 mm row-spacing footprint geometry.
- GPIO mapping is identical to the tested firmware: BUSY=4, RST=5, DC=6,
  CS1=7, CS2=10, MOSI=11, SCK=12.
- R16 is fitted and R15 is DNP.  Never fit both.
- Both DevKitC 3V3 header pins are deliberately isolated on the carrier.
  J3 pin 1 is the current-limited external EPD 3V3 input and J3 pin 2 is GND;
  fitted R4/R8 feed EPD_3V3 and V_B. USB powers only the DevKitC. TP1/TP2 are
  measurement pads and must not carry the panel supply cable.
- Power sequence for B0: connect USB first, then enable the current-limited
  J3 panel supply. Disable J3 before removing USB. While J3 is off, firmware
  must keep all seven cross-domain GPIOs as inputs/high impedance with no
  sourcing pulls; this sequence alone does not provide Ioff isolation. Add
  Ioff-rated buffers in a future revision if independent sequencing is required.
- The MF-1750 high-voltage parts and packages remain the Rev A1 set; no
  unmeasured inductor/capacitor downsizing is hidden in this layout.
- The antenna end has an explicit all-copper/all-track keepout; do not place
  metal, battery, display frame, cable or enclosure hardware over it.
- Use two 1x22 stacking sockets with at least 11 mm board-to-board clearance;
  validate the actual N16R8 underside height, tail-pin size, and antenna
  position first.  The placeholder socket has 0.80 mm finished holes and must
  not be released until a selected socket manufacturer's drill recommendation
  is substituted and checked.

## Current verification

- Routing is complete with dual-layer GND pours, partial/discontinuous local
  3V3 copper relief, explicit antenna/edge rule areas, and selected widened
  converter paths.  The 3V3 relief is two filled islands, not a continuous
  J3-to-R4/R8 bus.  Dense `/3V3`, `/EPD_3V3`, and `/V_B` distribution still
  contains 0.20 mm necks; this is a known B0 power-integrity limitation and is
  not electrically equivalent to Rev A1.
- KiCad 10.0.3: ERC 0 errors / 0 warnings; DRC 0 violations; 0 unconnected;
  schematic parity 0 footprint errors.  See `erc_final.rpt` and `drc_final.rpt`.
- Canonical files are `mf1750_devkitc_compact.kicad_sch` and
  `mf1750_devkitc_compact.kicad_pcb`; previews are `preview/final_top.png` and
  `preview/final_bottom.png`.  `bom_reference.csv` is the full engineering BOM.
- Rebuild order: generator -> Freerouting 2.2.4 (`-mp 600 -mt 1 -da
  --gui.enabled=false`) -> importer -> finalizer -> fresh ERC/DRC with
  schematic parity -> final top/bottom renders.  The finalizer is
  `../finalize_mf1750_devkitc_compact.py`; run
  `../verify_mf1750_devkitc_compact.py` with KiCad's bundled Python for the
  final gates and renders.  A new route is not authoritative until that script
  passes.  The generator writes `unrouted_source.kicad_pcb` and
  `README.provisional.md`; it deliberately cannot overwrite a verified
  canonical PCB or handoff README.

This B0 remains an engineering prototype, not a production release.  Before
ordering, measure the actual N16R8 socket/USB/antenna Z-envelope and connector
access against the intended enclosure.  Provide enclosure support below the
lower board edge; the two upper mounting holes do not carry connector insertion
loads by themselves.  First article must use current limit,
rail/current/temperature monitoring and the physical cut-off; confirm all MF-
1750 rails before attaching the panel.  Software checks do not qualify the
high-voltage stage or the panel electrically.
"""


def main() -> None:
    patch_base_globals()
    OUT.mkdir(parents=True, exist_ok=True)
    LOCAL_LIB_DIR.mkdir(parents=True, exist_ok=True)
    a1.FPC_LIB_DIR.mkdir(parents=True, exist_ok=True)
    if not a1.FPC_FOOTPRINT.exists():
        a1.FPC_FOOTPRINT.write_text(a1.make_fpc_footprint(), encoding="utf-8")
    if not a1.INDUCTOR_FOOTPRINT.exists():
        a1.INDUCTOR_FOOTPRINT.write_text(a1.make_inductor_footprint(), encoding="utf-8")
    DEVKIT_FOOTPRINT.write_text(make_devkit_footprint(), encoding="utf-8")
    (OUT / f"{PROJECT}.kicad_pro").write_text(base.make_project(), encoding="utf-8")
    (OUT / "sym-lib-table").write_text(base.make_sym_lib_table(), encoding="utf-8")
    (OUT / "fp-lib-table").write_text(make_footprint_table(), encoding="utf-8")
    (OUT / "mf1750_local.kicad_sym").write_text(
        base.make_local_symbol_lib(), encoding="utf-8"
    )
    (OUT / f"{PROJECT}.kicad_sch").write_text(make_schematic(), encoding="utf-8")
    # Keep the verified canonical PCB fail-safe.  A generator-only run writes
    # a staging input and must never replace the last board that passed the
    # importer/finalizer/verification chain.
    (OUT / "unrouted_source.kicad_pcb").write_text(
        make_board_unrouted(), encoding="utf-8"
    )
    (OUT / "bom_reference.csv").write_text(make_reference_bom(), encoding="utf-8")
    (OUT / "mf1750_fpc_pinmap.csv").write_text(base.make_pinmap(), encoding="utf-8")
    (OUT / "README.provisional.md").write_text(make_readme(), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
