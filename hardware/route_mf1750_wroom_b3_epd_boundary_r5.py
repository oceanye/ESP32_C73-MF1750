#!/usr/bin/env python3
"""Route the MF1750 B3 EPD boundary into an isolated R5 staging PCB.

This narrow REVISION builder starts from the reviewed R4 functional-placement
candidate (or an explicitly hash-bound chained ``--source``), preserves every
source footprint/zone/copper item, and only adds copper for the U5/U6 EPD
boundary.  It never writes the formal B3 PCB, R3, R4, or the schematic.

The candidate intentionally leaves the U6 MCU-side fanout to U1/J2 and the
remaining system-rail trunks on HOLD.  It does complete the protected B2
interface: U5 OUT reaches the existing TP1 ``EPD_SW_3V3`` entry, and all seven
U6 panel-side channels reach their nine frozen B2 tail anchors.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - evaluated under KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
DEFAULT_SOURCE = STAGING / "mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb"
DEFAULT_SOURCE_SHA256 = (
    "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf"
)
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
R3_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"
R4_BOARD = DEFAULT_SOURCE
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r5_epd_boundary_routed.kicad_pcb"
AUDIT_JSON = STAGING / "r5_epd_boundary_route_report.json"
SOURCE_DRC_JSON = STAGING / "r5_epd_boundary_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r5_epd_boundary_drc.json"
PREVIEW_DIR = STAGING / "r5_epd_boundary_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_epd_boundary_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_epd_boundary_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_epd_boundary_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_epd_boundary_back.svg"

ROUTING_UUID_SEED = 17507
BOARD_WIDTH_MM = 80.0
BOARD_HEIGHT_MM = 125.0
B2_BOTTOM_MM = 60.5
SIGNAL_WIDTH_MM = 0.20
EPD_RAIL_WIDTH_MM = 0.40
POWER_NECK_WIDTH_MM = 0.60
POWER_TRUNK_WIDTH_MM = 0.80
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30

ALLOWED_NETS = frozenset(
    {
        "/SYS_3V3",
        "/EPD_PWR_EN",
        "/EPD_ILIM",
        "/EPD_FAULT_N",
        "/EPD_SW_3V3",
        "/EPD_3V3",
        "/EPD_BUF_OE_N",
        "/EPD_BUF_CONNECT",
        "/RST_N",
        "/DC",
        "/CSB",
        "/CS2",
        "/SCL",
        "/SI0",
        "/BUSY_N",
        "/MCU_BUSY_N",
        "GND",
    }
)

EPD_REFS = frozenset(
    {
        "U5",
        "C39",
        "C40",
        "R33",
        "R34",
        "R35",
        "U6",
        "C45",
        "Q3",
        "R36",
        *(f"R{index}" for index in range(54, 64)),
        "TP1",
    }
)

# The pad centres bind this routing recipe to the reviewed R4 placement.
PAD_CONTRACT: dict[tuple[str, str], tuple[str, float, float]] = {
    ("U5", "1"): ("/EPD_PWR_EN", 6.6500, 63.2500),
    ("U5", "2"): ("/SYS_3V3", 6.6500, 64.2000),
    ("U5", "3"): ("GND", 6.6500, 65.1500),
    ("U5", "4"): ("/EPD_ILIM", 9.3500, 65.1500),
    ("U5", "5"): ("/EPD_SW_3V3", 9.3500, 64.2000),
    ("U5", "6"): ("/EPD_FAULT_N", 9.3500, 63.2500),
    ("C39", "1"): ("/SYS_3V3", 12.0500, 63.1000),
    ("C39", "2"): ("GND", 13.9500, 63.1000),
    ("C40", "1"): ("/EPD_SW_3V3", 12.0500, 66.6000),
    ("C40", "2"): ("GND", 13.9500, 66.6000),
    ("R33", "1"): ("/EPD_ILIM", 16.1750, 62.8000),
    ("R33", "2"): ("GND", 17.8250, 62.8000),
    ("R34", "1"): ("/SYS_3V3", 16.1750, 65.3000),
    ("R34", "2"): ("/EPD_FAULT_N", 17.8250, 65.3000),
    ("R35", "1"): ("/EPD_PWR_EN", 16.1750, 67.8000),
    ("R35", "2"): ("GND", 17.8250, 67.8000),
    ("C45", "1"): ("/EPD_3V3", 26.7250, 62.5000),
    ("C45", "2"): ("GND", 28.2750, 62.5000),
    ("Q3", "1"): ("/EPD_BUF_CONNECT", 25.8625, 65.0500),
    ("Q3", "2"): ("GND", 25.8625, 66.9500),
    ("Q3", "3"): ("/EPD_BUF_OE_N", 28.1375, 66.0000),
    ("R36", "1"): ("/EPD_3V3", 22.1750, 62.5000),
    ("R36", "2"): ("/EPD_BUF_OE_N", 23.8250, 62.5000),
    ("R54", "1"): ("/EPD_3V3", 22.1750, 65.0000),
    ("R54", "2"): ("/CSB", 23.8250, 65.0000),
    ("R55", "1"): ("/EPD_3V3", 22.1750, 67.5000),
    ("R55", "2"): ("/CS2", 23.8250, 67.5000),
    ("R56", "1"): ("/RST_N", 22.1750, 70.0000),
    ("R56", "2"): ("GND", 23.8250, 70.0000),
    ("R57", "1"): ("/DC", 25.6750, 70.5000),
    ("R57", "2"): ("GND", 27.3250, 70.5000),
    ("R58", "1"): ("/SCL", 29.1750, 71.5000),
    ("R58", "2"): ("GND", 30.8250, 71.5000),
    ("R59", "1"): ("/SI0", 32.6750, 71.5000),
    ("R59", "2"): ("GND", 34.3250, 71.5000),
    ("R60", "2"): ("GND", 37.6250, 71.5000),
    ("R61", "2"): ("GND", 27.8250, 77.0000),
    ("R62", "1"): ("/SYS_3V3", 29.1750, 74.2000),
    ("R62", "2"): ("/MCU_BUSY_N", 30.8250, 74.2000),
    ("R63", "1"): ("/EPD_BUF_CONNECT", 32.6750, 74.2000),
    ("R63", "2"): ("GND", 34.3250, 74.2000),
    ("U6", "2"): ("/MCU_RST_N", 31.1375, 63.2250),
    ("U6", "3"): ("/MCU_DC", 31.1375, 63.8750),
    ("U6", "4"): ("/MCU_CSB", 31.1375, 64.5250),
    ("U6", "5"): ("/MCU_CS2", 31.1375, 65.1750),
    ("U6", "6"): ("/MCU_SCL", 31.1375, 65.8250),
    ("U6", "7"): ("/MCU_SI0", 31.1375, 66.4750),
    ("U6", "8"): ("/MCU_BUSY_N", 31.1375, 67.1250),
    ("U6", "10"): ("GND", 31.1375, 68.4250),
    ("U6", "12"): ("/BUSY_N", 36.8625, 67.7750),
    ("U6", "13"): ("/SI0", 36.8625, 67.1250),
    ("U6", "14"): ("/SCL", 36.8625, 66.4750),
    ("U6", "15"): ("/CS2", 36.8625, 65.8250),
    ("U6", "16"): ("/CSB", 36.8625, 65.1750),
    ("U6", "17"): ("/DC", 36.8625, 64.5250),
    ("U6", "18"): ("/RST_N", 36.8625, 63.8750),
    ("U6", "19"): ("/EPD_BUF_OE_N", 36.8625, 63.2250),
    ("U6", "20"): ("/EPD_3V3", 36.8625, 62.5750),
    ("TP1", "1"): ("/EPD_SW_3V3", 4.5000, 50.5000),
}

PANEL_ANCHORS: dict[str, tuple[tuple[float, float, str], ...]] = {
    "/BUSY_N": ((17.8336, 54.2864, "F.Cu"), (6.4932, 51.3732, "B.Cu")),
    "/RST_N": ((10.0862, 52.4262, "B.Cu"),),
    "/DC": ((12.2199, 52.0199, "B.Cu"),),
    "/CSB": ((25.7400, 54.0000, "B.Cu"), (14.3169, 51.5769, "B.Cu")),
    "/CS2": ((45.0120, 57.5880, "F.Cu"),),
    "/SI0": ((43.2101, 55.0701, "B.Cu"),),
    "/SCL": ((43.9517, 53.2717, "B.Cu"),),
}

PANEL_PAD_BY_NET: dict[str, str] = {
    "/BUSY_N": "12",
    "/SI0": "13",
    "/SCL": "14",
    "/CS2": "15",
    "/CSB": "16",
    "/DC": "17",
    "/RST_N": "18",
}

# Each route is (net, layer-name, width-mm, point-sequence).  Routes below the
# B2 boundary are restricted to the reviewed panel anchors and TP1 power entry.
ROUTES: tuple[tuple[str, str, float, tuple[tuple[float, float], ...]], ...] = (
    # U5 system input and input bypass.  The upstream system trunk remains HOLD.
    ("/SYS_3V3", "F.Cu", 0.60, ((6.650, 64.200), (5.400, 64.200), (5.400, 61.800), (12.050, 61.800), (12.050, 63.100))),
    ("/SYS_3V3", "F.Cu", 0.20, ((12.050, 63.100), (12.050, 64.550), (14.550, 64.550), (15.300, 65.300), (16.175, 65.300))),
    # EN and FAULT use separate buried-layer corridors so the wide power necks
    # remain short and uncrossed on the component side.
    ("/EPD_PWR_EN", "F.Cu", 0.20, ((6.650, 63.250), (7.700, 63.250))),
    ("/EPD_PWR_EN", "In2.Cu", 0.20, ((7.700, 63.250), (8.000, 69.500), (16.175, 69.500))),
    ("/EPD_PWR_EN", "F.Cu", 0.20, ((16.175, 69.500), (16.175, 67.800))),
    ("/EPD_FAULT_N", "F.Cu", 0.20, ((9.350, 63.250), (10.500, 63.250))),
    ("/EPD_FAULT_N", "In1.Cu", 0.20, ((10.500, 63.250), (10.500, 60.700), (19.200, 60.700), (19.200, 65.300))),
    ("/EPD_FAULT_N", "F.Cu", 0.20, ((19.200, 65.300), (17.825, 65.300))),
    # ILIM exits below U5 and returns outside the local passives.
    ("/EPD_ILIM", "F.Cu", 0.20, ((9.350, 65.150), (9.350, 66.400))),
    ("/EPD_ILIM", "In1.Cu", 0.20, ((9.350, 66.400), (10.800, 68.200), (14.800, 68.200), (14.800, 61.500), (16.175, 61.500))),
    ("/EPD_ILIM", "F.Cu", 0.20, ((16.175, 61.500), (16.175, 62.800))),
    # U5 output is 0.60 mm at the IC/cap neck and 0.80 mm on the protected
    # TP1 trunk.  This is the only new trace that enters the frozen B2 region.
    ("/EPD_SW_3V3", "F.Cu", 0.60, ((9.350, 64.200), (10.300, 64.200), (12.050, 65.950), (12.050, 66.600))),
    ("/EPD_SW_3V3", "B.Cu", 0.80, ((10.300, 64.200), (11.300, 65.200), (11.300, 70.500), (4.300, 70.500), (4.300, 51.200), (4.500, 50.500))),
    # The EPD rail goes around the right end of J2 on In2.Cu.  It does not use
    # the physically impossible 0.54 mm PTH gaps (0.60 mm is required for a
    # 0.20 mm trace with 0.20 mm clearance on both sides).
    ("/EPD_3V3", "In2.Cu", 0.40, ((26.725, 45.500), (61.000, 45.500), (61.000, 60.400), (35.700, 60.400))),
    ("/EPD_3V3", "F.Cu", 0.40, ((35.700, 60.400), (36.8625, 61.5625), (36.8625, 62.575))),
    ("/EPD_3V3", "F.Cu", 0.40, ((35.700, 60.400), (26.725, 60.400), (26.725, 62.500))),
    ("/EPD_3V3", "In2.Cu", 0.20, ((35.700, 60.400), (21.000, 60.400))),
    ("/EPD_3V3", "F.Cu", 0.20, ((21.000, 60.400), (21.000, 67.500), (22.175, 67.500))),
    ("/EPD_3V3", "F.Cu", 0.20, ((21.000, 62.500), (22.175, 62.500))),
    ("/EPD_3V3", "F.Cu", 0.20, ((21.000, 65.000), (22.175, 65.000))),
    # U6 output-enable and Q3 default-control network.  OE uses In1.Cu to
    # avoid crossing the separate EPD rail on In2.Cu/F.Cu.
    ("/EPD_BUF_OE_N", "F.Cu", 0.20, ((36.8625, 63.225), (38.200, 63.225))),
    ("/EPD_BUF_OE_N", "In1.Cu", 0.20, ((38.200, 63.225), (35.200, 61.500), (24.800, 61.500))),
    ("/EPD_BUF_OE_N", "F.Cu", 0.20, ((24.800, 61.500), (23.825, 62.500))),
    ("/EPD_BUF_OE_N", "In1.Cu", 0.20, ((24.800, 61.500), (24.800, 66.000), (29.400, 66.000))),
    ("/EPD_BUF_OE_N", "F.Cu", 0.20, ((29.400, 66.000), (28.1375, 66.000))),
    ("/EPD_BUF_CONNECT", "F.Cu", 0.20, ((25.8625, 65.050), (27.200, 65.050))),
    ("/EPD_BUF_CONNECT", "B.Cu", 0.20, ((27.200, 65.050), (28.200, 69.000), (32.675, 72.900))),
    ("/EPD_BUF_CONNECT", "F.Cu", 0.20, ((32.675, 72.900), (32.675, 74.200))),
    # Panel fanout: the J2 adjacent PTH copper gap is only 0.54 mm, less than
    # the 0.60 mm required by a 0.20 mm trace plus two 0.20 mm clearances.
    # Every channel therefore escapes to the right while x < 58.75 at y >= 66,
    # rounds the connector at x >= 61.0, and returns above J2.  Five ordered
    # lanes use In1.Cu; CS2 and BUSY use F.Cu.  No source track is edited.
    ("/RST_N", "F.Cu", 0.20, ((36.8625, 63.875), (39.500, 63.875))),
    ("/RST_N", "In2.Cu", 0.20, ((39.500, 63.875), (44.000, 61.500), (62.000, 61.500))),
    ("/RST_N", "In1.Cu", 0.20, ((62.000, 61.500), (62.000, 57.000), (12.000, 57.000))),
    ("/RST_N", "B.Cu", 0.20, ((12.000, 57.000), (10.0862, 55.0862), (10.0862, 52.4262))),
    ("/DC", "F.Cu", 0.20, ((36.8625, 64.525), (41.000, 64.525))),
    ("/DC", "In1.Cu", 0.20, ((41.000, 64.525), (44.000, 62.500), (63.000, 62.500), (63.000, 56.000), (18.000, 56.000))),
    ("/DC", "B.Cu", 0.20, ((18.000, 56.000), (12.900, 56.000), (12.2199, 55.3199), (12.2199, 52.0199))),
    ("/CSB", "F.Cu", 0.20, ((36.8625, 65.175), (42.000, 65.175))),
    ("/CSB", "In1.Cu", 0.20, ((42.000, 65.175), (45.000, 63.500), (64.000, 63.500), (64.000, 55.000), (25.000, 55.000))),
    ("/CSB", "B.Cu", 0.20, ((25.000, 55.000), (25.740, 54.260), (25.740, 54.000))),
    ("/CSB", "B.Cu", 0.20, ((25.000, 55.000), (15.200, 55.000), (14.3169, 54.1169), (14.3169, 51.5769))),
    ("/SCL", "F.Cu", 0.20, ((36.8625, 66.475), (38.200, 66.475))),
    ("/SCL", "In1.Cu", 0.20, ((38.200, 66.475), (43.500, 66.475), (46.000, 64.500), (65.000, 64.500), (65.000, 53.500), (46.000, 53.500))),
    ("/SCL", "B.Cu", 0.20, ((46.000, 53.500), (45.200, 52.700), (44.500, 52.700), (43.9517, 53.2717))),
    ("/SI0", "F.Cu", 0.20, ((36.8625, 67.125), (39.000, 67.125))),
    ("/SI0", "In1.Cu", 0.20, ((39.000, 67.125), (44.000, 68.200), (47.000, 65.500), (66.000, 65.500), (66.000, 52.500), (49.000, 52.500))),
    ("/SI0", "B.Cu", 0.20, ((49.000, 52.500), (49.000, 56.200), (45.000, 56.200), (43.2101, 55.0701))),
    ("/CS2", "F.Cu", 0.20, ((36.8625, 65.825), (44.000, 65.825), (47.000, 64.500), (57.500, 64.500), (61.000, 61.000), (61.000, 56.000), (50.500, 56.000), (48.9381, 57.588))),
    ("/BUSY_N", "F.Cu", 0.20, ((36.8625, 67.775), (43.000, 67.775), (46.000, 65.500), (65.500, 65.500), (65.500, 52.500), (54.200, 52.500), (53.200, 51.500))),
    ("/BUSY_N", "B.Cu", 0.20, ((53.200, 51.500), (53.200, 54.000), (52.500, 54.000))),
    # BUSY's left B2 tail is a second disconnected source component.  Extend
    # the protected F.Cu tail to a clear via, then append a short B.Cu branch.
    ("/BUSY_N", "F.Cu", 0.20, ((17.8336, 54.2864), (10.000, 54.2864), (5.500, 52.3664))),
    ("/BUSY_N", "B.Cu", 0.20, ((5.500, 52.3664), (6.4932, 51.3732))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/EPD_PWR_EN", 7.700, 63.250),
    ("/EPD_PWR_EN", 16.175, 69.500),
    ("/EPD_FAULT_N", 10.500, 63.250),
    ("/EPD_FAULT_N", 19.200, 65.300),
    ("/EPD_ILIM", 9.350, 66.400),
    ("/EPD_ILIM", 16.175, 61.500),
    ("/EPD_SW_3V3", 10.300, 64.200),
    ("/EPD_3V3", 35.700, 60.400),
    ("/EPD_3V3", 21.000, 60.400),
    ("/EPD_BUF_OE_N", 38.200, 63.225),
    ("/EPD_BUF_OE_N", 24.800, 61.500),
    ("/EPD_BUF_OE_N", 29.400, 66.000),
    ("/EPD_BUF_CONNECT", 27.200, 65.050),
    ("/EPD_BUF_CONNECT", 32.675, 72.900),
    ("/RST_N", 39.500, 63.875),
    ("/RST_N", 62.000, 61.500),
    ("/RST_N", 12.000, 57.000),
    ("/DC", 41.000, 64.525),
    ("/DC", 18.000, 56.000),
    ("/CSB", 42.000, 65.175),
    ("/CSB", 25.000, 55.000),
    ("/SCL", 38.200, 66.475),
    ("/SCL", 46.000, 53.500),
    ("/SI0", 39.000, 67.125),
    ("/SI0", 49.000, 52.500),
    ("/BUSY_N", 53.200, 51.500),
    ("/BUSY_N", 5.500, 52.3664),
    # Local GND drops into the existing four-layer reference planes.
    ("GND", 6.650, 66.400),
    ("GND", 13.950, 61.800),
    ("GND", 13.950, 65.300),
    ("GND", 18.800, 59.700),
    ("GND", 19.200, 67.800),
    ("GND", 29.600, 62.500),
    ("GND", 26.900, 66.950),
    ("GND", 30.000, 68.425),
)

GROUND_STUBS: tuple[tuple[tuple[float, float], tuple[float, float]], ...] = (
    ((6.650, 65.150), (6.650, 66.400)),
    ((13.950, 63.100), (13.950, 61.800)),
    ((13.950, 66.600), (13.950, 65.300)),
    ((17.825, 62.800), (18.800, 62.800)),
    ((18.800, 62.800), (18.800, 59.700)),
    ((17.825, 67.800), (19.200, 67.800)),
    ((28.275, 62.500), (29.600, 62.500)),
    ((25.8625, 66.950), (26.900, 66.950)),
    ((31.1375, 68.425), (30.000, 68.425)),
)

ZERO_REQUIRED_DRC_TYPES = frozenset(
    {
        "clearance",
        "shorting_items",
        "items_not_allowed",
        "item_on_disabled_layer",
        "courtyards_overlap",
        "hole_clearance",
        "hole_to_hole",
        "tracks_crossing",
        "track_not_centered_on_via",
        "solder_mask_bridge",
        "copper_sliver",
    }
)


class RouteError(RuntimeError):
    """Fail-closed R5 route builder error."""


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(token) if token.isdigit() else token for token in re.split(r"(\d+)", value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_kicad_cli() -> Path:
    candidates = (
        shutil.which("kicad-cli"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RouteError("KiCad 10 kicad-cli was not found")


def point_mm(point) -> tuple[float, float]:
    return (round(pcbnew.ToMM(point.x), 6), round(pcbnew.ToMM(point.y), 6))


def item_uuid(item) -> str:
    value = item.m_Uuid.AsString()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise RouteError(f"invalid KiCad item UUID {value!r}")
    return value


def track_signature(item) -> tuple[object, ...]:
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            item.GetNetname(),
            point_mm(item.GetPosition()),
            round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
            round(pcbnew.ToMM(item.GetDrillValue()), 6),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    return (
        "track",
        item.GetNetname(),
        int(item.GetLayer()),
        point_mm(item.GetStart()),
        point_mm(item.GetEnd()),
        round(pcbnew.ToMM(item.GetWidth()), 6),
    )


def footprint_signature(footprint) -> tuple[object, ...]:
    return (
        point_mm(footprint.GetPosition()),
        round(float(footprint.GetOrientationDegrees()), 6),
        int(footprint.GetLayer()),
        bool(footprint.IsFlipped()),
        footprint.GetFPID().GetUniStringLibId(),
        tuple(
            sorted(
                (
                    pad.GetNumber(),
                    pad.GetNetname(),
                    point_mm(pad.GetPosition()),
                )
                for pad in footprint.Pads()
            )
        ),
    )


def zone_signature(zone) -> tuple[object, ...]:
    outline = zone.Outline()
    polygons = []
    for polygon_index in range(outline.OutlineCount()):
        contour = outline.Outline(polygon_index)
        polygons.append(tuple(point_mm(contour.CPoint(index)) for index in range(contour.PointCount())))
    return (
        item_uuid(zone),
        zone.GetNetname(),
        tuple(zone.GetLayerSet().Seq()),
        tuple(polygons),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
    )


def copper_uuid_audit(board) -> dict[str, object]:
    uuids = [item_uuid(item) for item in board.GetTracks()]
    counts = collections.Counter(uuids)
    duplicates = {
        uuid: count for uuid, count in sorted(counts.items()) if count != 1
    }
    return {
        "item_count": len(uuids),
        "unique_uuid_count": len(counts),
        "duplicate_uuid_counts": duplicates,
        "passed": not duplicates,
    }


def source_state(board) -> dict[str, object]:
    return {
        "footprints": {fp.GetReference(): footprint_signature(fp) for fp in board.GetFootprints()},
        "tracks": {item_uuid(item): track_signature(item) for item in board.GetTracks()},
        "zones": {item_uuid(zone): zone_signature(zone) for zone in board.Zones()},
        "copper_uuid_audit": copper_uuid_audit(board),
    }


def source_panel_anchor_evidence(board) -> dict[str, list[dict[str, object]]]:
    """Bind every frozen B2 anchor to immutable source-copper UUIDs."""
    evidence: dict[str, list[dict[str, object]]] = {}
    for net_name, anchors in PANEL_ANCHORS.items():
        net_evidence = []
        for x_mm, y_mm, layer_name in anchors:
            expected_point = (round(x_mm, 6), round(y_mm, 6))
            expected_layer = layer_id(board, layer_name)
            matches = []
            for item in board.GetTracks():
                if isinstance(item, pcbnew.PCB_VIA):
                    continue
                if item.GetNetname() != net_name or item.GetLayer() != expected_layer:
                    continue
                if expected_point in (point_mm(item.GetStart()), point_mm(item.GetEnd())):
                    matches.append(item_uuid(item))
            if not matches:
                raise RouteError(
                    f"frozen anchor missing from source copper: {net_name}@{expected_point}/{layer_name}"
                )
            net_evidence.append(
                {
                    "position_mm": list(expected_point),
                    "layer": layer_name,
                    "source_item_uuids": sorted(matches),
                }
            )
        evidence[net_name] = net_evidence
    return evidence


def verify_panel_connected_sets(
    board, source_anchor_evidence: dict[str, list[dict[str, object]]]
) -> dict[str, object]:
    """Prove each U6 output pad reaches every frozen source component."""
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    by_net: dict[str, object] = {}
    for net_name, pad_number in PANEL_PAD_BY_NET.items():
        pad = find_numbered_pad(board, "U6", pad_number)
        connected_items = list(connectivity.GetConnectedItems(pad))
        connected_uuids = {
            item_uuid(item)
            for item in connected_items
            if hasattr(item, "m_Uuid")
        }
        anchor_results = []
        for anchor in source_anchor_evidence[net_name]:
            required = set(anchor["source_item_uuids"])
            anchor_results.append(
                {
                    **anchor,
                    "source_items_in_pad_connected_set": sorted(required & connected_uuids),
                    "connected": required.issubset(connected_uuids),
                }
            )
        by_net[net_name] = {
            "u6_pad": pad_number,
            "pad_net": pad.GetNetname(),
            "connected_item_count": len(connected_items),
            "anchors": anchor_results,
            "passed": pad.GetNetname() == net_name and all(item["connected"] for item in anchor_results),
        }
    return {
        "required_net_count": len(PANEL_PAD_BY_NET),
        "required_anchor_count": sum(len(items) for items in PANEL_ANCHORS.values()),
        "by_net": by_net,
        "passed": all(item["passed"] for item in by_net.values()),
    }


def find_numbered_pad(board, ref: str, number: str):
    for footprint in board.GetFootprints():
        if footprint.GetReference() == ref:
            matches = [pad for pad in footprint.Pads() if pad.GetNumber() == number]
            if not matches:
                raise RouteError(f"missing pad {ref}.{number}")
            # The only duplicated numbered pad in this design is U1.41; none of
            # the EPD route contract entries uses a duplicated pad number.
            if len(matches) != 1:
                raise RouteError(f"ambiguous pad {ref}.{number}: {len(matches)} matches")
            return matches[0]
    raise RouteError(f"missing footprint {ref}")


def validate_pad_contract(board) -> list[dict[str, object]]:
    refs = {footprint.GetReference() for footprint in board.GetFootprints()}
    missing = sorted(EPD_REFS - refs, key=natural_key)
    if missing:
        raise RouteError(f"missing EPD-boundary refs: {missing}")
    evidence = []
    for (ref, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = find_numbered_pad(board, ref, number)
        actual = point_mm(pad.GetPosition())
        position_matches = (
            abs(actual[0] - x_mm) <= 0.000002
            and abs(actual[1] - y_mm) <= 0.000002
        )
        if pad.GetNetname() != net or not position_matches:
            raise RouteError(
                f"pad contract drift {ref}.{number}: "
                f"net={pad.GetNetname()!r} pos={actual}, expected={net!r}@{(x_mm, y_mm)}"
            )
        evidence.append({"ref": ref, "pad": number, "net": net, "position_mm": list(actual)})
    return evidence


def layer_id(board, name: str) -> int:
    layer = board.GetLayerID(name)
    if layer < 0:
        raise RouteError(f"board does not contain layer {name}")
    return layer


def add_track(board, net_name: str, layer_name: str, width_mm: float, start, end):
    net = board.FindNet(net_name)
    if net is None:
        raise RouteError(f"board does not contain required net {net_name}")
    item = pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I_MM(*start))
    item.SetEnd(pcbnew.VECTOR2I_MM(*end))
    item.SetWidth(pcbnew.FromMM(width_mm))
    item.SetLayer(layer_id(board, layer_name))
    item.SetNet(net)
    board.Add(item)
    return item


def add_via(board, net_name: str, x_mm: float, y_mm: float):
    net = board.FindNet(net_name)
    if net is None:
        raise RouteError(f"board does not contain required net {net_name}")
    item = pcbnew.PCB_VIA(board)
    item.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
    item.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
    item.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    item.SetNet(net)
    board.Add(item)
    return item


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net_name, layer_name, width_mm, points in ROUTES:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"forbidden route net {net_name}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(add_track(board, net_name, layer_name, width_mm, start, end))
    for start, end in GROUND_STUBS:
        added.append(add_track(board, "GND", "F.Cu", SIGNAL_WIDTH_MM, start, end))
    for net_name, x_mm, y_mm in VIAS:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"forbidden via net {net_name}")
        added.append(add_via(board, net_name, x_mm, y_mm))
    return added


def prepare_validation_context(temp_dir: Path, board_source: Path) -> tuple[Path, Path]:
    stem = "mf1750_wroom_b3_power_tf"
    board_path = temp_dir / f"{stem}.kicad_pcb"
    shutil.copy2(board_source, board_path)
    shutil.copy2(FORMAL_SCHEMATIC, temp_dir / f"{stem}.kicad_sch")
    shutil.copy2(FORMAL_PROJECT, temp_dir / f"{stem}.kicad_pro")
    for table_name in ("fp-lib-table", "sym-lib-table"):
        source = B3_DIR / table_name
        if source.is_file():
            shutil.copy2(source, temp_dir / table_name)
    for library_name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        source = B3_DIR / library_name
        if source.is_file():
            shutil.copy2(source, temp_dir / library_name)
    for directory_name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / directory_name
        if source.is_dir():
            shutil.copytree(source, temp_dir / directory_name)
    return board_path, temp_dir / "drc.json"


def run_drc(kicad_cli: Path, board_source: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mf1750-r5-epd-drc-") as directory:
        board_path, report_path = prepare_validation_context(Path(directory), board_source)
        command = [
            str(kicad_cli),
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--schematic-parity",
            "--refill-zones",
            "--output",
            str(report_path),
            str(board_path),
        ]
        completed = subprocess.run(
            command,
            cwd=board_path.parent,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
        if completed.returncode != 0 or not report_path.is_file():
            raise RouteError(
                "KiCad DRC failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    categories = collections.Counter(str(item.get("type")) for item in raw.get("violations", []))
    return {
        "command": command,
        "returncode": completed.returncode,
        "kicad_version": raw.get("kicad_version"),
        "violation_count": len(raw.get("violations", [])),
        "violation_categories": dict(sorted(categories.items())),
        "unconnected_count": len(raw.get("unconnected_items", [])),
        "schematic_parity_count": len(raw.get("schematic_parity", [])),
        "schematic_parity_sample": raw.get("schematic_parity", [])[:10],
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "raw": raw,
    }


def render(kicad_cli: Path, board_path: Path, output: Path, side: str) -> dict[str, object]:
    command = [
        str(kicad_cli),
        "pcb",
        "render",
        "--side",
        side,
        "--background",
        "opaque",
        "--quality",
        "high",
        "--width",
        "1800",
        "--height",
        "1600",
        "--output",
        str(output),
        str(board_path),
    ]
    completed = subprocess.run(command, cwd=B3_DIR, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RouteError(f"{side} render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    return {"side": side, "bytes": output.stat().st_size, "command": command}


def export_svg(kicad_cli: Path, board_path: Path, output: Path, layers: str, mirror: bool = False) -> dict[str, object]:
    command = [
        str(kicad_cli),
        "pcb",
        "export",
        "svg",
        "--mode-single",
        "--fit-page-to-board",
        "--exclude-drawing-sheet",
        "--layers",
        layers,
        "--output",
        str(output),
    ]
    if mirror:
        command.append("--mirror")
    command.append(str(board_path))
    completed = subprocess.run(command, cwd=B3_DIR, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RouteError("SVG export failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    return {"layers": layers, "mirror": mirror, "bytes": output.stat().st_size, "command": command}


def audit_candidate(board, before: dict[str, object], added_uuids: set[str]) -> dict[str, object]:
    footprints = {fp.GetReference(): footprint_signature(fp) for fp in board.GetFootprints()}
    footprint_drift = sorted(
        (set(before["footprints"]) | set(footprints)), key=natural_key
    )
    footprint_drift = [ref for ref in footprint_drift if before["footprints"].get(ref) != footprints.get(ref)]
    candidate_uuid_audit = copper_uuid_audit(board)
    tracks = {item_uuid(item): item for item in board.GetTracks()}
    missing_source = sorted(set(before["tracks"]) - set(tracks))
    changed_source = sorted(
        uuid for uuid in set(before["tracks"]) & set(tracks)
        if before["tracks"][uuid] != track_signature(tracks[uuid])
    )
    new_ids = set(tracks) - set(before["tracks"])
    unexpected_new = sorted(new_ids - added_uuids)
    missing_added = sorted(added_uuids - new_ids)
    new_items = [tracks[uuid] for uuid in sorted(new_ids)]
    forbidden_nets = sorted({item.GetNetname() for item in new_items if item.GetNetname() not in ALLOWED_NETS})
    bad_vias = []
    bad_widths = []
    b2_added = []
    for item in new_items:
        if isinstance(item, pcbnew.PCB_VIA):
            diameter = round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6)
            drill = round(pcbnew.ToMM(item.GetDrillValue()), 6)
            if (diameter, drill) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                bad_vias.append({"uuid": item_uuid(item), "diameter_mm": diameter, "drill_mm": drill})
            points = [point_mm(item.GetPosition())]
        else:
            width = round(pcbnew.ToMM(item.GetWidth()), 6)
            if width not in {0.20, 0.40, 0.60, 0.80}:
                bad_widths.append({"uuid": item_uuid(item), "width_mm": width})
            points = [point_mm(item.GetStart()), point_mm(item.GetEnd())]
        if any(y < B2_BOTTOM_MM for _, y in points):
            b2_added.append({"uuid": item_uuid(item), "net": item.GetNetname(), "points_mm": points})
    zones = {item_uuid(zone): zone_signature(zone) for zone in board.Zones()}
    changed_zones = sorted(
        uuid for uuid in set(before["zones"]) & set(zones)
        if before["zones"][uuid] != zones[uuid]
    )
    missing_zones = sorted(set(before["zones"]) - set(zones))
    extra_zones = sorted(set(zones) - set(before["zones"]))
    checks = {
        "all_source_footprints_exact": not footprint_drift,
        "source_copper_uuids_unique": before["copper_uuid_audit"]["passed"],
        "candidate_copper_uuids_unique": candidate_uuid_audit["passed"],
        "all_source_copper_uuid_geometry_exact": not missing_source and not changed_source,
        "only_builder_added_copper": not unexpected_new and not missing_added,
        "only_allowlisted_nets": not forbidden_nets,
        "via_rule_0p60_0p30": not bad_vias,
        "width_allowlist": not bad_widths,
        "all_source_zones_exact": not changed_zones and not missing_zones and not extra_zones,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_copper_count": len(before["tracks"]),
        "source_copper_uuid_audit": before["copper_uuid_audit"],
        "candidate_copper_uuid_audit": candidate_uuid_audit,
        "added_copper_count": len(new_items),
        "added_track_count": sum(not isinstance(item, pcbnew.PCB_VIA) for item in new_items),
        "added_via_count": sum(isinstance(item, pcbnew.PCB_VIA) for item in new_items),
        "added_nets": sorted({item.GetNetname() for item in new_items}),
        "footprint_drift": footprint_drift,
        "missing_source_copper": missing_source,
        "changed_source_copper": changed_source,
        "unexpected_new_ids": unexpected_new,
        "missing_added_ids": missing_added,
        "forbidden_nets": forbidden_nets,
        "bad_vias": bad_vias,
        "bad_widths": bad_widths,
        "changed_zones": changed_zones,
        "missing_zones": missing_zones,
        "extra_zones": extra_zones,
        "b2_added_copper": b2_added,
    }


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    zero_required = {name: candidate_categories.get(name, 0) for name in sorted(ZERO_REQUIRED_DRC_TYPES)}
    new_categories = {
        name: candidate_categories[name] - source_categories.get(name, 0)
        for name in sorted(candidate_categories)
        if candidate_categories[name] > source_categories.get(name, 0)
    }
    checks = {
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "zero_forbidden_geometry_categories": not any(zero_required.values()),
        "no_new_drc_category_count": not new_categories,
        "unconnected_not_increased": candidate["unconnected_count"] <= source["unconnected_count"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "zero_required_counts": zero_required,
        "new_violation_category_counts": new_categories,
        "unconnected_delta": candidate["unconnected_count"] - source["unconnected_count"],
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--source-sha256",
        help="required with a non-default chained --source; binds the exact input candidate",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.resolve()
    report: dict[str, object]
    formal_before = sha256_file(FORMAL_BOARD) if FORMAL_BOARD.is_file() else None
    r3_before = sha256_file(R3_BOARD) if R3_BOARD.is_file() else None
    r4_before = sha256_file(R4_BOARD) if R4_BOARD.is_file() else None
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not source.is_file():
            raise RouteError(f"source board missing: {source}")
        protected = {FORMAL_BOARD.resolve(), R3_BOARD.resolve(), R4_BOARD.resolve()}
        if OUTPUT_BOARD.resolve() in protected or source == OUTPUT_BOARD.resolve():
            raise RouteError("output/source aliases a protected or self-overwriting board")
        expected_sha = DEFAULT_SOURCE_SHA256 if source == DEFAULT_SOURCE.resolve() else args.source_sha256
        if not expected_sha:
            raise RouteError("non-default --source requires --source-sha256")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
            raise RouteError("--source-sha256 must be exactly 64 hexadecimal characters")
        source_sha = sha256_file(source)
        if source_sha.lower() != expected_sha.lower():
            raise RouteError(f"source SHA-256 mismatch: {source_sha} != {expected_sha.lower()}")
        # Other deterministic R5 builders may concurrently use isolated
        # temporary .kicad_pro bundles in staging.  Only a pcbnew board lock can
        # alias copper being read/written here; unrelated project locks must not
        # serialize the independent route builders.
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        kicad_cli = find_kicad_cli()

        board = pcbnew.LoadBoard(str(source))
        if board is None:
            raise RouteError("KiCad could not parse source board")
        pad_evidence = validate_pad_contract(board)
        before = source_state(board)
        if not before["copper_uuid_audit"]["passed"]:
            raise RouteError(
                "source board has duplicate track/via UUIDs: "
                + json.dumps(before["copper_uuid_audit"]["duplicate_uuid_counts"])
            )
        frozen_anchor_evidence = source_panel_anchor_evidence(board)
        source_drc = run_drc(kicad_cli, source)
        if source_drc["schematic_parity_count"] != 0:
            raise RouteError("source board has non-zero schematic parity")

        added = add_routes(board)
        added_uuids = {item_uuid(item) for item in added}
        if len(added_uuids) != len(added):
            raise RouteError("deterministic routing produced duplicate UUIDs")

        STAGING.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mf1750-r5-epd-save-") as directory:
            temporary = Path(directory) / OUTPUT_BOARD.name
            if not pcbnew.SaveBoard(str(temporary), board):
                raise RouteError("KiCad failed to save temporary R5 EPD candidate")
            reloaded = pcbnew.LoadBoard(str(temporary))
            if reloaded is None:
                raise RouteError("saved R5 EPD candidate does not reload")
            audit = audit_candidate(reloaded, before, added_uuids)
            panel_connectivity = verify_panel_connected_sets(reloaded, frozen_anchor_evidence)
            audit["panel_connected_sets"] = panel_connectivity
            audit["passed"] = audit["passed"] and panel_connectivity["passed"]
            if not audit["passed"]:
                raise RouteError("candidate source-preservation audit failed: " + json.dumps(audit))
            os.replace(temporary, OUTPUT_BOARD)

        candidate_drc = run_drc(kicad_cli, OUTPUT_BOARD)
        gate = drc_gate(source_drc, candidate_drc)
        # Reports are always retained, including a failed first-pass geometry,
        # but failed DRC gates keep the candidate in HOLD and return non-zero.
        SOURCE_DRC_JSON.write_text(json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CANDIDATE_DRC_JSON.write_text(json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        render_evidence = [
            render(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top"),
            render(kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom"),
            export_svg(kicad_cli, OUTPUT_BOARD, FRONT_COPPER_SVG, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"),
            export_svg(kicad_cli, OUTPUT_BOARD, BACK_COPPER_SVG, "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts", mirror=True),
        ]
        protected_after = {
            "formal": sha256_file(FORMAL_BOARD) if FORMAL_BOARD.is_file() else None,
            "r3": sha256_file(R3_BOARD) if R3_BOARD.is_file() else None,
            "r4": sha256_file(R4_BOARD) if R4_BOARD.is_file() else None,
        }
        protected_unchanged = protected_after == {"formal": formal_before, "r3": r3_before, "r4": r4_before}
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "REVISION_TO_STAGING_ONLY",
            "state": "R5_EPD_BOUNDARY_ROUTED_CANDIDATE",
            "overall_status": "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "route_checks_passed": audit["passed"],
            "drc_increment_gate_passed": gate["passed"],
            "routing_checks_passed": audit["passed"] and gate["passed"],
            "locally_verified": False,
            "kicad_version": str(pcbnew.GetBuildVersion()),
            "inputs": {
                "source": {"path": str(source), "sha256": source_sha},
                "formal_schematic": {"path": str(FORMAL_SCHEMATIC), "sha256": sha256_file(FORMAL_SCHEMATIC)},
                "formal_project": {"path": str(FORMAL_PROJECT), "sha256": sha256_file(FORMAL_PROJECT)},
            },
            "output": {"path": str(OUTPUT_BOARD), "sha256": sha256_file(OUTPUT_BOARD)},
            "protected_sources": {
                "unchanged": protected_unchanged,
                "before": {"formal": formal_before, "r3": r3_before, "r4": r4_before},
                "after": protected_after,
            },
            "routing_contract": {
                "signal_width_mm": SIGNAL_WIDTH_MM,
                "epd_rail_width_mm": EPD_RAIL_WIDTH_MM,
                "power_neck_width_mm": POWER_NECK_WIDTH_MM,
                "power_trunk_width_mm": POWER_TRUNK_WIDTH_MM,
                "via_diameter_mm": VIA_DIAMETER_MM,
                "via_drill_mm": VIA_DRILL_MM,
                "allowed_nets": sorted(ALLOWED_NETS),
                "panel_anchors": {net: [list(item) for item in anchors] for net, anchors in PANEL_ANCHORS.items()},
                "pad_contract": pad_evidence,
            },
            "audit": audit,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "artifacts": {
                "source_drc_json": str(SOURCE_DRC_JSON),
                "candidate_drc_json": str(CANDIDATE_DRC_JSON),
                "top_preview": str(TOP_PREVIEW),
                "bottom_preview": str(BOTTOM_PREVIEW),
                "front_copper_svg": str(FRONT_COPPER_SVG),
                "back_copper_svg": str(BACK_COPPER_SVG),
                "render_export": render_evidence,
            },
            "completed_scope": [
                "U5 local decoupling/control/ILIM and 0.60/0.80 mm OUT-to-TP1 path",
                "U6 VCC/decoupling/OE/Q3 local network",
                *(
                    ["all seven U6 panel channels reach all nine frozen B2 source components"]
                    if panel_connectivity["passed"]
                    else []
                ),
                "local GND drops use only 0.60/0.30 mm through vias",
            ],
            "holds": [
                "U6 MCU-side fanout to U1 and J2 remains unrouted",
                "U5 SYS_3V3, EPD_PWR_EN, and EPD_FAULT_N onward system trunks remain unrouted",
                "R54-R59 signal-side safe-bias taps remain unrouted pending the next collision-free fanout pass",
                "R60/R61 control nets and R62 SYS_3V3 side remain system-routing HOLD",
                "whole-board unconnected count is non-zero; this is not LOCALLY_VERIFIED or manufacturing-ready",
            ],
        }
        AUDIT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key not in {"audit", "routing_contract"}}, ensure_ascii=False, indent=2))
        return 0 if gate["passed"] and protected_unchanged else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "REVISION_TO_STAGING_ONLY",
            "state": "R5_EPD_BOUNDARY_ROUTE_FAILED",
            "overall_status": "FAIL",
            "operation_completed": False,
            "hardware_accessed": False,
            "routing_checks_passed": False,
            "locally_verified": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "source": str(source),
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        AUDIT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
