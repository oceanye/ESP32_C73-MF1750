#!/usr/bin/env python3
"""Route the MF1750 WROOM B3 BQ24074/PowerPath staging candidate.

This is a deterministic, staging-only REVISION.  It accepts the frozen R4
functional placement or a later compatible routed candidate through a
hash-bound ``--source``/``--source-sha256`` pair.  It preserves every source
footprint, zone and copper item,
then adds only the reviewed BQ24074/USB-power/STM6600-local routes declared
below.  It never overwrites the formal, R3, or R4 PCB.

Important evidence boundaries:

* USB D+/D- are deliberately not routed because the final controlled-
  impedance stackup is not frozen.
* J6 BAT/NTC external wiring is deliberately not routed because the battery
  pack, mating harness, pin order and NTC contract remain HOLD.
* TPS63070, TF, EPD and the frozen B2 driver region are outside this stage.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - exercised only outside KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
PROJECT_BASENAME = "mf1750_wroom_b3_power_tf"
CANONICAL_PROJECT = B3_DIR / f"{PROJECT_BASENAME}.kicad_pro"
CANONICAL_SCHEMATIC = B3_DIR / f"{PROJECT_BASENAME}.kicad_sch"
FORMAL_BOARD = B3_DIR / f"{PROJECT_BASENAME}.kicad_pcb"
R3_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"
R4_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r4_functional_placed.kicad_pcb"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r5_bq_powerpath_routed.kicad_pcb"
AUDIT_JSON = STAGING / "r5_bq_powerpath_route_audit.json"
DRC_JSON = STAGING / "r5_bq_powerpath_drc.json"
PREVIEW_DIR = STAGING / "r5_bq_powerpath_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_bq_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_bq_bottom.png"

R4_SHA256 = "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf"
SCHEMATIC_SHA256 = "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0"
FORMAL_BOARD_SHA256 = "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7"
R3_BOARD_SHA256 = "c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb"

# U4 owns seed 17505 and EPD owns 17507.  A route stage must never reuse an
# upstream seed: doing so creates syntactically loadable boards with duplicate
# track/via UUIDs and makes UUID-based preservation evidence ambiguous.
ROUTE_UUID_SEED = 17506
MIN_TRACK_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.50

ALLOWED_NETS = frozenset(
    {
        "/USB_VBUS",
        "/USB_5V_FUSED",
        "/BAT_POS",
        "/VSYS_RAW",
        "GND",
        "/BQ_ISET",
        "/BQ_ILIM",
        "/BQ_TMR",
        "/BQ_CHG_N",
        "/USB_INPUT_VALID_N",
        "/STM_VREF",
        "/STM_CSRD",
        "/PWR_INT_N",
    }
)
FORBIDDEN_NETS = frozenset(
    {
        "/USB_DP_CONN",
        "/USB_DN_CONN",
        "/USB_DP_ESD",
        "/USB_DN_ESD",
        "/BAT_NTC",
        "/DCDC_L1",
        "/DCDC_L2",
    }
)
REQUIRED_REFS = frozenset(
    {
        "J5",
        "F1",
        "D5",
        "C24",
        "C25",
        "U2",
        "C26",
        "C27",
        "J6",
        "U3",
        "C28",
        "C29",
        "C30",
        "C31",
        "R21",
        "R22",
        "R24",
        "R25",
        "R26",
        "R28",
        "R51",
        "R52",
    }
)


@dataclasses.dataclass(frozen=True)
class RouteSpec:
    name: str
    net: str
    layer_name: str
    width_mm: float
    points_mm: tuple[tuple[float, float], ...]


@dataclasses.dataclass(frozen=True)
class ViaSpec:
    name: str
    net: str
    point_mm: tuple[float, float]


def route(
    name: str,
    net: str,
    layer_name: str,
    width_mm: float,
    *points_mm: tuple[float, float],
) -> RouteSpec:
    return RouteSpec(name, net, layer_name, width_mm, tuple(points_mm))


def via(name: str, net: str, x_mm: float, y_mm: float) -> ViaSpec:
    return ViaSpec(name, net, (x_mm, y_mm))


# Reviewed deterministic copper.  The narrow 0.20/0.25 mm pieces are only
# QFN escape neck-downs or low-speed controls.  Main power trunks are
# 0.50-0.80 mm, pending final current/temperature validation.
ROUTES: tuple[RouteSpec, ...] = (
    # USB-C VBUS duplicate power pads -> F1.  D+/D- and CC are untouched.
    route(
        "vbus_upper_escape",
        "/USB_VBUS",
        "F.Cu",
        0.20,
        (1.455, 106.55),
        (2.0, 106.795),
        (4.2, 106.795),
    ),
    route(
        "vbus_lower_escape",
        "/USB_VBUS",
        "F.Cu",
        0.20,
        (1.455, 111.45),
        (2.0, 111.205),
        (4.2, 111.205),
    ),
    route("vbus_pair_join", "/USB_VBUS", "F.Cu", 0.60, (4.2, 111.205), (4.2, 106.795)),
    route(
        "vbus_to_fuse",
        "/USB_VBUS",
        "F.Cu",
        0.80,
        (4.2, 106.795),
        (4.8, 105.75),
        (4.8, 101.0),
        (7.0375, 99.0),
    ),
    # Fused 5 V entry, TVS branch, input capacitors and both BQ IN pins.
    route(
        "usb5_fuse_to_trunk",
        "/USB_5V_FUSED",
        "F.Cu",
        0.70,
        (9.9625, 99.0),
        (10.5, 98.0),
        (18.05, 98.0),
        (18.05, 100.0),
    ),
    route(
        "usb5_tvs_branch", "/USB_5V_FUSED", "F.Cu", 0.60, (12.35, 100.0), (12.35, 98.0)
    ),
    route(
        "usb5_c24_escape",
        "/USB_5V_FUSED",
        "F.Cu",
        0.60,
        (18.05, 100.0),
        (17.1, 100.0),
        (17.1, 101.0),
    ),
    route(
        "usb5_bottom_core",
        "/USB_5V_FUSED",
        "B.Cu",
        0.60,
        (17.1, 101.0),
        (19.2, 101.0),
        (19.2, 104.3),
    ),
    route(
        "usb5_c25_bottom",
        "/USB_5V_FUSED",
        "B.Cu",
        0.60,
        (19.2, 101.0),
        (21.0, 101.0),
        (21.0, 104.4),
    ),
    route(
        "usb5_c25_entry",
        "/USB_5V_FUSED",
        "F.Cu",
        0.50,
        (21.0, 104.4),
        (21.0, 105.0),
        (22.05, 105.0),
    ),
    route(
        "usb5_in13_neck",
        "/USB_5V_FUSED",
        "F.Cu",
        0.20,
        (19.2, 104.3),
        (18.75, 104.8),
        (18.75, 105.5625),
    ),
    route(
        "usb5_in6_bottom",
        "/USB_5V_FUSED",
        "B.Cu",
        0.50,
        (17.1, 101.0),
        (14.0, 101.0),
        (14.0, 112.8),
        (16.7, 112.8),
        (16.7, 110.5),
    ),
    route(
        "usb5_in6_neck",
        "/USB_5V_FUSED",
        "F.Cu",
        0.20,
        (16.7, 110.5),
        (17.65, 109.2),
        (17.75, 108.4375),
    ),
    # BQ BAT pins -> local C26.  The J6 BAT and NTC external branches remain HOLD.
    route("bat_pin2_neck", "/BAT_POS", "F.Cu", 0.25, (16.5625, 106.75), (15.2, 106.75)),
    route("bat_pin3_neck", "/BAT_POS", "F.Cu", 0.25, (16.5625, 107.25), (15.2, 107.25)),
    route(
        "bat_pin_join",
        "/BAT_POS",
        "F.Cu",
        0.50,
        (15.2, 106.75),
        (15.2, 107.0),
        (15.2, 107.25),
    ),
    route(
        "bat_local_power",
        "/BAT_POS",
        "In2.Cu",
        0.80,
        (15.2, 107.0),
        (15.2, 116.0),
        (22.05, 116.0),
        (22.05, 112.5),
    ),
    route("bat_c26_entry", "/BAT_POS", "F.Cu", 0.60, (22.05, 112.5), (22.05, 108.0)),
    # BQ OUT pins -> C27 -> C31/U4 input bank, with a branch to U3/C28.
    # The route terminates on C31 rather than entering the TPS63070 pin field.
    route(
        "vsys_out10_neck", "/VSYS_RAW", "F.Cu", 0.20, (19.4375, 107.25), (20.2, 107.25)
    ),
    route(
        "vsys_out11_neck", "/VSYS_RAW", "F.Cu", 0.20, (19.4375, 106.75), (20.2, 106.75)
    ),
    route(
        "vsys_out_join",
        "/VSYS_RAW",
        "F.Cu",
        0.20,
        (20.2, 106.75),
        (20.2, 107.25),
        (21.0, 107.0),
    ),
    route(
        "vsys_c27_l3_branch",
        "/VSYS_RAW",
        "In2.Cu",
        0.80,
        (24.0, 107.0),
        (24.0, 111.3),
        (18.05, 111.3),
        (18.05, 112.5),
    ),
    route("vsys_c27_entry", "/VSYS_RAW", "F.Cu", 0.60, (18.05, 112.5), (18.05, 111.0)),
    route(
        "vsys_c31_l3_trunk",
        "/VSYS_RAW",
        "In2.Cu",
        0.80,
        (21.0, 107.0),
        (26.5, 107.0),
        (26.5, 92.0),
        (10.0, 92.0),
        (10.0, 83.0),
        (16.45, 83.0),
    ),
    route("vsys_c31_entry", "/VSYS_RAW", "F.Cu", 0.60, (16.45, 83.0), (16.45, 84.0)),
    route(
        "vsys_u3_l3_branch",
        "/VSYS_RAW",
        "In2.Cu",
        0.80,
        (10.0, 83.0),
        (10.0, 75.6),
        (14.3, 75.6),
    ),
    route(
        "vsys_u3_pin1_escape",
        "/VSYS_RAW",
        "F.Cu",
        0.25,
        (10.2, 77.25),
        (9.2, 77.25),
        (9.2, 75.6),
        (14.3, 75.6),
    ),
    route(
        "vsys_c28_entry",
        "/VSYS_RAW",
        "F.Cu",
        0.45,
        (14.3, 75.6),
        (15.225, 76.5),
        (15.225, 77.0),
    ),
    # BQ programming and open-drain status lines.  Every QFN escape is 0.20 mm.
    route("bq_iset_escape", "/BQ_ISET", "F.Cu", 0.20, (17.25, 105.5625), (15.0, 105.5)),
    route(
        "bq_iset_l3",
        "/BQ_ISET",
        "In2.Cu",
        0.20,
        (15.0, 105.5),
        (12.5, 105.5),
        (12.5, 95.8),
        (17.175, 95.8),
    ),
    route("bq_iset_r21", "/BQ_ISET", "F.Cu", 0.20, (17.175, 95.8), (17.175, 96.8)),
    route(
        "bq_ilim_escape",
        "/BQ_ILIM",
        "F.Cu",
        0.20,
        (19.4375, 106.25),
        (20.0, 106.25),
        (20.0, 103.5),
    ),
    route(
        "bq_ilim_l3",
        "/BQ_ILIM",
        "In2.Cu",
        0.20,
        (20.0, 103.5),
        (22.7, 100.8),
        (22.7, 95.6),
        (20.675, 95.6),
    ),
    route("bq_ilim_r22", "/BQ_ILIM", "F.Cu", 0.20, (20.675, 95.6), (20.675, 96.8)),
    route(
        "bq_tmr_escape",
        "/BQ_TMR",
        "F.Cu",
        0.20,
        (18.25, 105.5625),
        (18.25, 104.8),
        (18.0, 104.2),
    ),
    route(
        "bq_tmr_l3",
        "/BQ_TMR",
        "In2.Cu",
        0.20,
        (18.0, 104.2),
        (18.0, 94.5),
        (24.175, 94.5),
        (24.175, 95.6),
    ),
    route("bq_tmr_r24", "/BQ_TMR", "F.Cu", 0.20, (24.175, 95.6), (24.175, 96.8)),
    route(
        "bq_chg_escape",
        "/BQ_CHG_N",
        "F.Cu",
        0.20,
        (19.4375, 107.75),
        (20.2, 107.75),
        (20.8, 109.0),
    ),
    route(
        "bq_chg_bottom",
        "/BQ_CHG_N",
        "B.Cu",
        0.20,
        (20.8, 109.0),
        (21.5, 108.4),
        (26.0, 108.4),
        (26.0, 103.7),
        (22.325, 103.7),
    ),
    route("bq_chg_r26", "/BQ_CHG_N", "F.Cu", 0.20, (22.325, 103.7), (22.325, 102.5)),
    route(
        "bq_pgood_escape",
        "/USB_INPUT_VALID_N",
        "F.Cu",
        0.20,
        (18.25, 108.4375),
        (18.25, 109.4),
    ),
    route(
        "bq_pgood_bottom",
        "/USB_INPUT_VALID_N",
        "B.Cu",
        0.20,
        (18.25, 109.4),
        (18.25, 110.2),
        (29.0, 110.2),
        (29.0, 105.0),
        (28.0, 105.0),
    ),
    route(
        "bq_pgood_r25",
        "/USB_INPUT_VALID_N",
        "F.Cu",
        0.20,
        (28.0, 105.0),
        (27.325, 105.0),
    ),
    # STM6600 local timing/interrupt routes.  MCU_EN, PS_HOLD, DCDC_EN and
    # user-button global fanout are intentionally deferred so this stage does
    # not enter the WROOM or TPS63070 routing islands.
    route("stm_vref_escape", "/STM_VREF", "F.Cu", 0.20, (10.2, 78.25), (9.0, 78.25)),
    route(
        "stm_vref_bottom",
        "/STM_VREF",
        "B.Cu",
        0.20,
        (9.0, 78.25),
        (7.5, 78.25),
        (7.5, 81.2),
        (14.0, 81.2),
        (14.0, 80.0),
    ),
    route("stm_vref_c29", "/STM_VREF", "F.Cu", 0.20, (14.0, 80.0), (15.05, 80.0)),
    route("stm_csrd_escape", "/STM_CSRD", "F.Cu", 0.20, (10.2, 79.25), (9.0, 79.25)),
    route(
        "stm_csrd_l3",
        "/STM_CSRD",
        "In2.Cu",
        0.20,
        (9.0, 79.25),
        (8.0, 79.25),
        (8.0, 73.8),
        (19.05, 73.8),
        (19.05, 76.0),
    ),
    route("stm_csrd_c30", "/STM_CSRD", "F.Cu", 0.20, (19.05, 76.0), (19.05, 77.0)),
    route("stm_int_escape", "/PWR_INT_N", "F.Cu", 0.20, (11.8, 77.75), (12.7, 77.75)),
    route(
        "stm_int_l3",
        "/PWR_INT_N",
        "In2.Cu",
        0.20,
        (12.7, 77.75),
        (12.7, 82.0),
        (20.825, 82.0),
        (20.825, 81.1),
    ),
    route("stm_int_r28", "/PWR_INT_N", "F.Cu", 0.20, (20.825, 81.1), (20.825, 80.0)),
    # Ground stubs to an L2 ground via.  U2 EPAD receives a dedicated 0.6/0.3
    # mm thermal/ground via; production via-fill/tenting remains assembly HOLD.
    route("gnd_d5", "GND", "F.Cu", 0.50, (15.65, 100.0), (15.65, 102.0)),
    route("gnd_c24", "GND", "F.Cu", 0.50, (19.95, 100.0), (21.2, 100.0)),
    route("gnd_c25", "GND", "F.Cu", 0.60, (23.95, 105.0), (24.8, 105.8)),
    route("gnd_c26", "GND", "F.Cu", 0.60, (24.8, 105.8), (24.8, 108.0), (23.95, 108.0)),
    route("gnd_c27", "GND", "F.Cu", 0.60, (19.95, 111.0), (19.95, 112.5)),
    route("gnd_c28", "GND", "F.Cu", 0.35, (16.775, 77.0), (17.6, 76.0)),
    route("gnd_c29", "GND", "F.Cu", 0.35, (16.95, 80.0), (17.8, 80.0)),
    route("gnd_c30", "GND", "F.Cu", 0.35, (20.95, 77.0), (21.8, 77.0)),
    route("gnd_u3", "GND", "F.Cu", 0.25, (11.8, 77.25), (12.8, 76.5)),
    route(
        "gnd_u2_pin4_pin5",
        "GND",
        "F.Cu",
        0.20,
        (16.5625, 107.75),
        (16.2, 108.3),
        (16.2, 109.2),
        (16.5, 108.8),
        (17.25, 108.4375),
    ),
    route(
        "gnd_u2_pin8",
        "GND",
        "F.Cu",
        0.20,
        (18.75, 108.4375),
        (19.2, 109.0),
        (19.5, 109.5),
    ),
    route("gnd_r21", "GND", "F.Cu", 0.25, (18.825, 96.8), (18.825, 95.8)),
    route("gnd_r22", "GND", "F.Cu", 0.25, (22.325, 96.8), (22.325, 98.0), (21.5, 98.0)),
    route("gnd_r24", "GND", "F.Cu", 0.25, (25.825, 96.8), (25.825, 97.8), (24.9, 97.8)),
)

VIAS: tuple[ViaSpec, ...] = (
    via("gnd_d5_via", "GND", 15.65, 102.0),
    via("gnd_c24_via", "GND", 21.2, 100.0),
    via("gnd_c25_c26_via", "GND", 24.8, 105.8),
    via("gnd_c27_via", "GND", 19.95, 112.5),
    via("gnd_c28_via", "GND", 17.6, 76.0),
    via("gnd_c29_via", "GND", 17.8, 80.0),
    via("gnd_c30_via", "GND", 21.8, 77.0),
    via("gnd_u3_via", "GND", 12.8, 76.5),
    via("gnd_u2_pin4_pin5_via", "GND", 16.2, 109.2),
    via("gnd_u2_pin8_via", "GND", 19.5, 109.5),
    via("gnd_r21_via", "GND", 18.825, 95.8),
    via("gnd_r22_via", "GND", 21.5, 98.0),
    via("gnd_r24_via", "GND", 24.9, 97.8),
    via("gnd_u2_epad_via", "GND", 18.0, 107.0),
    via("usb5_c24_via", "/USB_5V_FUSED", 17.1, 101.0),
    via("usb5_in13_via", "/USB_5V_FUSED", 19.2, 104.3),
    via("usb5_c25_via", "/USB_5V_FUSED", 21.0, 104.4),
    via("usb5_in6_via", "/USB_5V_FUSED", 16.7, 110.5),
    via("bat_pin_via", "/BAT_POS", 15.2, 107.0),
    via("bat_c26_via", "/BAT_POS", 22.05, 112.5),
    via("vsys_out_via", "/VSYS_RAW", 21.0, 107.0),
    via("vsys_c27_via", "/VSYS_RAW", 18.05, 112.5),
    via("vsys_c31_via", "/VSYS_RAW", 16.45, 83.0),
    via("vsys_u3_via", "/VSYS_RAW", 14.3, 75.6),
    via("bq_iset_start", "/BQ_ISET", 15.0, 105.5),
    via("bq_iset_end", "/BQ_ISET", 17.175, 95.8),
    via("bq_ilim_start", "/BQ_ILIM", 20.0, 103.5),
    via("bq_ilim_end", "/BQ_ILIM", 20.675, 95.6),
    via("bq_tmr_start", "/BQ_TMR", 18.0, 104.2),
    via("bq_tmr_end", "/BQ_TMR", 24.175, 95.6),
    via("bq_chg_start", "/BQ_CHG_N", 20.8, 109.0),
    via("bq_chg_end", "/BQ_CHG_N", 22.325, 103.7),
    via("bq_pgood_start", "/USB_INPUT_VALID_N", 18.25, 109.4),
    via("bq_pgood_end", "/USB_INPUT_VALID_N", 28.0, 105.0),
    via("stm_vref_start", "/STM_VREF", 9.0, 78.25),
    via("stm_vref_end", "/STM_VREF", 14.0, 80.0),
    via("stm_csrd_start", "/STM_CSRD", 9.0, 79.25),
    via("stm_csrd_end", "/STM_CSRD", 19.05, 76.0),
    via("stm_int_start", "/PWR_INT_N", 12.7, 77.75),
    via("stm_int_end", "/PWR_INT_N", 20.825, 81.1),
)


class RouteError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    )


def find_kicad_cli() -> Path:
    candidates = (
        shutil.which("kicad-cli"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise RouteError("KiCad 10 kicad-cli was not found")


def point_mm(point) -> tuple[float, float]:
    return (round(pcbnew.ToMM(point.x), 6), round(pcbnew.ToMM(point.y), 6))


def footprint_signature(footprint) -> tuple[object, ...]:
    position = footprint.GetPosition()
    return (
        footprint.GetReference(),
        footprint.GetFPID().GetUniStringLibId(),
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
    )


def track_signature(item) -> tuple[object, ...]:
    start = item.GetStart()
    uuid = item.m_Uuid.AsString()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            uuid,
            item.GetNetname(),
            int(start.x),
            int(start.y),
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    end = item.GetEnd()
    return (
        "track",
        uuid,
        item.GetNetname(),
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


def copper_uuid_audit(board) -> dict[str, object]:
    """Return a fail-closed uniqueness audit for every track and via UUID."""

    counts = collections.Counter(item.m_Uuid.AsString() for item in board.GetTracks())
    duplicates = sorted(uuid for uuid, count in counts.items() if count != 1)
    return {
        "passed": not duplicates,
        "copper_item_count": sum(counts.values()),
        "unique_uuid_count": len(counts),
        "duplicate_uuid_count": sum(counts[uuid] - 1 for uuid in duplicates),
        "duplicate_uuid_sample": [
            {"uuid": uuid, "multiplicity": counts[uuid]}
            for uuid in duplicates[:20]
        ],
    }


def polygon_points(poly_set) -> tuple[tuple[tuple[int, int], ...], ...]:
    contours = []
    for index in range(poly_set.OutlineCount()):
        contour = poly_set.COutline(index)
        contours.append(
            tuple(
                (int(contour.CPoint(point).x), int(contour.CPoint(point).y))
                for point in range(contour.PointCount())
            )
        )
    return tuple(contours)


def zone_signature(zone) -> tuple[object, ...]:
    return (
        zone.m_Uuid.AsString(),
        zone.GetZoneName(),
        zone.GetNetname(),
        int(zone.GetLayer()),
        tuple(zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        polygon_points(zone.Outline()),
    )


def named_nets(board) -> dict[str, object]:
    result: dict[str, object] = {}
    for net in board.GetNetInfo().NetsByNetcode().values():
        result[net.GetNetname()] = net
    return result


def pad_record(pad) -> dict[str, object]:
    footprint = pad.GetParentFootprint()
    position = pad.GetPosition()
    x_mm = pcbnew.ToMM(position.x)
    y_mm = pcbnew.ToMM(position.y)
    reference = footprint.GetReference()
    number = pad.GetNumber()
    return {
        "key": f"{reference}.{number}@{x_mm:.4f},{y_mm:.4f}",
        "reference": reference,
        "pad": number,
        "net": pad.GetNetname(),
        "x_mm": round(x_mm, 4),
        "y_mm": round(y_mm, 4),
    }


def matching_pads(board, reference: str, number: str) -> list[object]:
    return [
        pad
        for footprint in board.GetFootprints()
        if footprint.GetReference() == reference
        for pad in footprint.Pads()
        if pad.GetNumber() == number
    ]


def vsys_chain_proof(board) -> dict[str, object]:
    """Prove the PowerPath nodes are one physical connected component.

    The U4-side bulk bank is source-owned.  A plain R4 source therefore
    proves only the BQ-to-C31 core; a chained U4 source must already expose
    at least one U4 input pad at C31, in which case every reviewed U4-bank
    pad below is required to remain in the resulting component.
    """

    core_targets = (("U2", "10"), ("U2", "11"), ("C27", "1"), ("C31", "1"))
    u4_bank_targets = (
        ("C32", "1"),
        ("C33", "1"),
        ("C46", "1"),
        ("U4", "12"),
        ("U4", "13"),
    )
    target_pads: dict[str, list[object]] = {}
    for reference, number in (*core_targets, *u4_bank_targets):
        pads = matching_pads(board, reference, number)
        if not pads:
            raise RouteError(f"connectivity target is missing: {reference}.{number}")
        target_pads[f"{reference}.{number}"] = pads
    anchor_pads = target_pads["C31.1"]
    if len(anchor_pads) != 1:
        raise RouteError(f"expected one C31.1 anchor, found {len(anchor_pads)}")

    connectivity = board.GetConnectivity()
    connectivity.Build(board)
    connected_items = connectivity.GetConnectedItems(anchor_pads[0])
    connected_pads = [item for item in connected_items if isinstance(item, pcbnew.PAD)]
    if all(
        item.m_Uuid.AsString() != anchor_pads[0].m_Uuid.AsString()
        for item in connected_pads
    ):
        connected_pads.append(anchor_pads[0])
    connected_records = sorted(
        (pad_record(pad) for pad in connected_pads),
        key=lambda item: natural_key(str(item["key"])),
    )
    connected_keys = {str(item["key"]) for item in connected_records}

    def target_records(targets: tuple[tuple[str, str], ...]) -> list[dict[str, object]]:
        records = [
            pad_record(pad)
            for reference, number in targets
            for pad in target_pads[f"{reference}.{number}"]
        ]
        return sorted(records, key=lambda item: natural_key(str(item["key"])))

    core_records = target_records(core_targets)
    u4_records = target_records(u4_bank_targets)
    core_pass = all(str(item["key"]) in connected_keys for item in core_records)
    u4_connected_count = sum(str(item["key"]) in connected_keys for item in u4_records)
    u4_pass = u4_connected_count == len(u4_records)
    return {
        "anchor": pad_record(anchor_pads[0]),
        "net": "/VSYS_RAW",
        "connected_pad_count": len(connected_records),
        "connected_pads": connected_records,
        "required_core": core_records,
        "required_u4_bank": u4_records,
        "core_same_connected_set": core_pass,
        "u4_bank_connected_count": u4_connected_count,
        "u4_bank_target_count": len(u4_records),
        "u4_bank_any_connected": u4_connected_count > 0,
        "u4_bank_same_connected_set": u4_pass,
        "full_chain_same_connected_set": core_pass and u4_pass,
    }


def layer_id(board, layer_name: str) -> int:
    for layer in range(pcbnew.PCB_LAYER_ID_COUNT):
        if board.IsLayerEnabled(layer) and board.GetLayerName(layer) == layer_name:
            return layer
    raise RouteError(f"enabled layer not found: {layer_name}")


def add_track(board, net, layer: int, width_mm: float, start_mm, end_mm) -> None:
    if width_mm + 1e-9 < MIN_TRACK_WIDTH_MM:
        raise RouteError(f"track width below project minimum: {width_mm}")
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(net)
    item.SetLayer(layer)
    item.SetWidth(pcbnew.FromMM(width_mm))
    item.SetStart(pcbnew.VECTOR2I_MM(*start_mm))
    item.SetEnd(pcbnew.VECTOR2I_MM(*end_mm))
    if item.GetStart() == item.GetEnd():
        raise RouteError(f"zero-length track: {start_mm}")
    board.Add(item)


def add_via(board, net, position_mm) -> None:
    item = pcbnew.PCB_VIA(board)
    item.SetNet(net)
    item.SetPosition(pcbnew.VECTOR2I_MM(*position_mm))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    item.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
    item.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
    board.Add(item)


def route_manifest() -> dict[str, object]:
    width_by_net: dict[str, set[float]] = collections.defaultdict(set)
    layer_by_net: dict[str, set[str]] = collections.defaultdict(set)
    segment_count = 0
    length_by_net: dict[str, float] = collections.defaultdict(float)
    for spec in ROUTES:
        width_by_net[spec.net].add(spec.width_mm)
        layer_by_net[spec.net].add(spec.layer_name)
        segment_count += len(spec.points_mm) - 1
        for first, second in zip(spec.points_mm, spec.points_mm[1:]):
            length_by_net[spec.net] += (
                (second[0] - first[0]) ** 2 + (second[1] - first[1]) ** 2
            ) ** 0.5
    return {
        "route_spec_count": len(ROUTES),
        "track_segment_count": segment_count,
        "via_count": len(VIAS),
        "nets": {
            net: {
                "layers": sorted(layer_by_net[net]),
                "widths_mm": sorted(width_by_net[net]),
                "track_length_mm": round(length_by_net[net], 4),
                "via_count": sum(item.net == net for item in VIAS),
            }
            for net in sorted(width_by_net)
        },
        "power_width_policy": {
            "main_power_mm": [0.50, 0.60, 0.70, 0.80],
            "qfn_neck_down_mm": [0.20, 0.25],
            "low_speed_mm": 0.20,
            "via_mm": {"diameter": VIA_DIAMETER_MM, "drill": VIA_DRILL_MM},
            "status": "GEOMETRY_CANDIDATE; final ampacity/temperature budget HOLD",
        },
    }


def validate_static_specs() -> None:
    names = [item.name for item in ROUTES] + [item.name for item in VIAS]
    duplicate_names = sorted(
        name for name, count in collections.Counter(names).items() if count != 1
    )
    if duplicate_names:
        raise RouteError(f"duplicate route/via names: {duplicate_names}")
    route_nets = {item.net for item in ROUTES}
    via_nets = {item.net for item in VIAS}
    if not route_nets | via_nets <= ALLOWED_NETS:
        raise RouteError(
            f"route spec contains unapproved nets: {(route_nets | via_nets) - ALLOWED_NETS}"
        )
    if (route_nets | via_nets) & FORBIDDEN_NETS:
        raise RouteError("route spec touches a forbidden net")
    for spec in ROUTES:
        if len(spec.points_mm) < 2:
            raise RouteError(f"route {spec.name} has fewer than two points")
        if spec.width_mm + 1e-9 < MIN_TRACK_WIDTH_MM:
            raise RouteError(f"route {spec.name} violates min width")
        for x_mm, y_mm in spec.points_mm:
            if not (0.5 <= x_mm <= 79.5 and B2_BOTTOM_MM < y_mm <= 124.5):
                raise RouteError(
                    f"route {spec.name} leaves approved B3 area: {(x_mm, y_mm)}"
                )
    for spec in VIAS:
        x_mm, y_mm = spec.point_mm
        if not (0.5 <= x_mm <= 79.5 and B2_BOTTOM_MM < y_mm <= 124.5):
            raise RouteError(f"via {spec.name} leaves approved B3 area")


def copy_required(source: Path, destination: Path, label: str) -> None:
    if not source.is_file():
        raise RouteError(f"missing {label}: {source}")
    shutil.copy2(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise RouteError(f"copy verification failed for {label}")


def prepare_drc_context(directory: Path, board_source: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=False)
    project = directory / f"{PROJECT_BASENAME}.kicad_pro"
    schematic = directory / f"{PROJECT_BASENAME}.kicad_sch"
    board = directory / f"{PROJECT_BASENAME}.kicad_pcb"
    copy_required(CANONICAL_PROJECT, project, "canonical project")
    copy_required(CANONICAL_SCHEMATIC, schematic, "canonical schematic")
    copy_required(board_source, board, "DRC PCB")
    copy_required(B3_DIR / "fp-lib-table", directory / "fp-lib-table", "fp-lib-table")
    copy_required(
        B3_DIR / "sym-lib-table", directory / "sym-lib-table", "sym-lib-table"
    )
    for symbol_name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        copy_required(B3_DIR / symbol_name, directory / symbol_name, symbol_name)
    for library_name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / library_name
        if not source.is_dir():
            raise RouteError(f"missing footprint library: {source}")
        shutil.copytree(source, directory / library_name)
    if sha256_file(schematic) != SCHEMATIC_SHA256:
        raise RouteError("disposable schematic hash mismatch")
    return {"project": project, "schematic": schematic, "board": board}


def run_drc(
    kicad_cli: Path, board_source: Path, context_root: Path, label: str
) -> tuple[dict[str, object], bytes]:
    context = prepare_drc_context(context_root / label, board_source)
    report_path = context_root / f"{label}_drc.json"
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
        str(context["board"]),
    ]
    completed = subprocess.run(
        command,
        cwd=context["board"].parent,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    if completed.returncode != 0 or not report_path.is_file():
        raise RouteError(
            f"{label} DRC failed to execute: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    raw = report_path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteError(f"{label} DRC JSON is invalid: {exc}") from exc
    violations = data.get("violations")
    unconnected = data.get("unconnected_items")
    parity = data.get("schematic_parity")
    if (
        not isinstance(violations, list)
        or not isinstance(unconnected, list)
        or not isinstance(parity, list)
    ):
        raise RouteError(f"{label} DRC result arrays are missing")
    categories = collections.Counter(
        str(item.get("type", "UNKNOWN")) for item in violations
    )
    dangerous = {
        "clearance": categories.get("clearance", 0),
        "copper_edge_clearance": categories.get("copper_edge_clearance", 0),
        "shorting_items": categories.get("shorting_items", 0),
        "items_not_allowed": categories.get("items_not_allowed", 0),
        "item_on_disabled_layer": categories.get("item_on_disabled_layer", 0),
        "courtyards_overlap": categories.get("courtyards_overlap", 0),
        "hole_clearance": categories.get("hole_clearance", 0),
        "hole_to_hole": categories.get("hole_to_hole", 0),
        "tracks_crossing": categories.get("tracks_crossing", 0),
        "track_not_centered_on_via": categories.get("track_not_centered_on_via", 0),
        "solder_mask_bridge": categories.get("solder_mask_bridge", 0),
        "copper_sliver": categories.get("copper_sliver", 0),
    }
    return (
        {
            "label": label,
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "kicad_version": data.get("kicad_version"),
            "report_source": data.get("source"),
            "violations": len(violations),
            "unconnected": len(unconnected),
            "schematic_parity": len(parity),
            "categories": dict(sorted(categories.items())),
            "dangerous": dangerous,
            "ignored_checks": data.get("ignored_checks", []),
        },
        raw,
    )


def render(kicad_cli: Path, board: Path, output: Path, side: str) -> dict[str, object]:
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
        str(board),
    ]
    completed = subprocess.run(
        command,
        cwd=B3_DIR,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RouteError(
            f"{side} render failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    return {"side": side, "bytes": output.stat().st_size, "command": command}


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help="explicit R4-derived staging source; requires --source-sha256",
    )
    parser.add_argument(
        "--source-sha256",
        help="expected SHA-256 for an explicit --source",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.resolve() if args.source else R4_BOARD.resolve()
    expected_source_hash = (
        args.source_sha256.casefold() if args.source_sha256 else R4_SHA256
    )
    candidate: Path | None = None
    candidate_companions: list[Path] = []
    report: dict[str, object]
    try:
        validate_static_specs()
        if pcbnew is None:
            raise RouteError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        for path, expected, label in (
            (R4_BOARD, R4_SHA256, "frozen R4 baseline"),
            (CANONICAL_SCHEMATIC, SCHEMATIC_SHA256, "canonical schematic"),
            (FORMAL_BOARD, FORMAL_BOARD_SHA256, "formal PCB"),
            (R3_BOARD, R3_BOARD_SHA256, "R3 staging PCB"),
        ):
            if not path.is_file() or sha256_file(path) != expected:
                raise RouteError(f"{label} hash mismatch: {path}")
        if args.source is not None and not args.source_sha256:
            raise RouteError("explicit --source requires --source-sha256")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_source_hash):
            raise RouteError("source SHA-256 must contain exactly 64 hex digits")
        if not source.is_file():
            raise RouteError(f"source PCB is missing: {source}")
        if source == OUTPUT_BOARD.resolve():
            raise RouteError("refusing to use the output PCB as its own source")
        locks = sorted(
            {
                *B3_DIR.glob("~*.lck"),
                *STAGING.glob("~*.lck"),
            },
            key=lambda path: str(path).casefold(),
        )
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(map(str, locks)))

        source_hash_before = sha256_file(source)
        if source_hash_before.casefold() != expected_source_hash:
            raise RouteError(
                f"source hash mismatch: {source_hash_before} != {expected_source_hash}"
            )

        kicad_cli = find_kicad_cli()
        formal_before = sha256_file(FORMAL_BOARD)
        r3_before = sha256_file(R3_BOARD)
        r4_before = sha256_file(R4_BOARD)

        baseline = pcbnew.LoadBoard(str(R4_BOARD))
        board = pcbnew.LoadBoard(str(source))
        if baseline is None or board is None:
            raise RouteError("KiCad could not load R4 baseline/source PCB")
        baseline_footprints = collections.Counter(
            footprint_signature(item) for item in baseline.GetFootprints()
        )
        source_footprints = collections.Counter(
            footprint_signature(item) for item in board.GetFootprints()
        )
        if source_footprints != baseline_footprints:
            raise RouteError("source footprint geometry differs from frozen R4")
        refs = {item.GetReference() for item in board.GetFootprints()}
        if not REQUIRED_REFS <= refs:
            raise RouteError(
                f"source lacks required refs: {sorted(REQUIRED_REFS - refs, key=natural_key)}"
            )
        baseline_tracks = collections.Counter(
            track_signature(item) for item in baseline.GetTracks()
        )
        source_tracks = collections.Counter(
            track_signature(item) for item in board.GetTracks()
        )
        source_uuid_audit = copper_uuid_audit(board)
        if not source_uuid_audit["passed"]:
            raise RouteError(
                "source board contains duplicate track/via UUIDs: "
                + json.dumps(source_uuid_audit, ensure_ascii=False)
            )
        if baseline_tracks - source_tracks:
            raise RouteError("source does not preserve every frozen R4 copper item")
        baseline_zones = collections.Counter(
            zone_signature(item) for item in baseline.Zones()
        )
        source_zones = collections.Counter(
            zone_signature(item) for item in board.Zones()
        )
        if source_zones != baseline_zones:
            raise RouteError("source zone outline/settings differ from frozen R4")
        source_vsys_proof = vsys_chain_proof(board)
        require_u4_bank = bool(source_vsys_proof["u4_bank_any_connected"])

        nets = named_nets(board)
        missing_nets = sorted((ALLOWED_NETS | FORBIDDEN_NETS) - set(nets))
        if missing_nets:
            raise RouteError(f"source lacks reviewed nets: {missing_nets}")
        layers = {
            name: layer_id(board, name) for name in {item.layer_name for item in ROUTES}
        }

        # Seed all new item KIID values so identical source + script produces
        # byte-identical output across clean runs.
        pcbnew.KIID.SeedGenerator(ROUTE_UUID_SEED)
        for spec in ROUTES:
            for first, second in zip(spec.points_mm, spec.points_mm[1:]):
                add_track(
                    board,
                    nets[spec.net],
                    layers[spec.layer_name],
                    spec.width_mm,
                    first,
                    second,
                )
        for spec in VIAS:
            add_via(board, nets[spec.net], spec.point_mm)

        title = board.GetTitleBlock()
        title.SetTitle("MF1750 WROOM B3 BQ24074 PowerPath routed candidate")
        title.SetRevision("B3-WROOM-POWER-TF-R5-BQ-POWERPATH")
        title.SetComment(0, "BQ/POWERPATH TO C31; J6/USB DATA/U4 PIN FIELD/TF/EPD HOLD")

        STAGING.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mf1750-b3-bq-r5-") as temp_name:
            temp_root = Path(temp_name)
            candidate = STAGING / (
                f".{OUTPUT_BOARD.stem}.{os.getpid()}.{secrets.token_hex(6)}.kicad_pcb"
            )
            candidate_companions = [
                candidate.with_suffix(".kicad_pro"),
                candidate.with_suffix(".kicad_prl"),
            ]
            top_temp = temp_root / TOP_PREVIEW.name
            bottom_temp = temp_root / BOTTOM_PREVIEW.name
            previous_output = temp_root / "previous_output.kicad_pcb"

            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(str(candidate), board)
            reloaded = pcbnew.LoadBoard(str(candidate))
            if reloaded is None:
                raise RouteError("saved candidate does not reload")

            actual_footprints = collections.Counter(
                footprint_signature(item) for item in reloaded.GetFootprints()
            )
            actual_tracks = collections.Counter(
                track_signature(item) for item in reloaded.GetTracks()
            )
            candidate_uuid_audit = copper_uuid_audit(reloaded)
            if not candidate_uuid_audit["passed"]:
                raise RouteError(
                    "candidate contains duplicate track/via UUIDs: "
                    + json.dumps(candidate_uuid_audit, ensure_ascii=False)
                )
            actual_zones = collections.Counter(
                zone_signature(item) for item in reloaded.Zones()
            )
            if actual_footprints != source_footprints:
                raise RouteError("candidate changed footprint geometry")
            if actual_zones != source_zones:
                raise RouteError("candidate changed zone outline/settings")
            if source_tracks - actual_tracks:
                raise RouteError("candidate removed or changed source copper")
            added_items = list((actual_tracks - source_tracks).elements())
            expected_added = route_manifest()["track_segment_count"] + len(VIAS)
            if len(added_items) != expected_added:
                raise RouteError(
                    f"added copper count mismatch: expected {expected_added}, got {len(added_items)}"
                )
            added_nets = {str(item[2]) for item in added_items}
            if not added_nets <= ALLOWED_NETS or added_nets & FORBIDDEN_NETS:
                raise RouteError(
                    f"candidate added copper on unapproved nets: {sorted(added_nets - ALLOWED_NETS)}"
                )
            if any(
                item[0] == "track"
                and pcbnew.ToMM(int(item[8])) + 1e-9 < MIN_TRACK_WIDTH_MM
                for item in added_items
            ):
                raise RouteError("candidate contains an undersized new track")
            new_vias = [item for item in added_items if item[0] == "via"]
            if any(
                abs(pcbnew.ToMM(int(item[5])) - VIA_DIAMETER_MM) > 1e-6
                or abs(pcbnew.ToMM(int(item[6])) - VIA_DRILL_MM) > 1e-6
                for item in new_vias
            ):
                raise RouteError("candidate contains a non-0.60/0.30 new via")
            if any(
                item[0] == "track"
                and min(pcbnew.ToMM(int(item[5])), pcbnew.ToMM(int(item[7])))
                <= B2_BOTTOM_MM
                for item in added_items
            ):
                raise RouteError("new track entered the frozen B2 region")
            if any(
                item[0] == "via" and pcbnew.ToMM(int(item[4])) <= B2_BOTTOM_MM
                for item in new_vias
            ):
                raise RouteError("new via entered the frozen B2 region")

            candidate_vsys_proof = vsys_chain_proof(reloaded)
            if not candidate_vsys_proof["core_same_connected_set"]:
                raise RouteError(
                    "VSYS core is not one connected set: U2.10/11 -> C27.1 -> C31.1"
                )
            if (
                require_u4_bank
                and not candidate_vsys_proof["full_chain_same_connected_set"]
            ):
                raise RouteError(
                    "source-owned U4 input bank was not preserved in the VSYS connected set"
                )

            baseline_drc, _ = run_drc(kicad_cli, source, temp_root, "source")
            candidate_drc, candidate_drc_raw = run_drc(
                kicad_cli, candidate, temp_root, "candidate"
            )
            if candidate_drc["schematic_parity"] != 0:
                raise RouteError(
                    f"candidate schematic parity is not zero: {candidate_drc['schematic_parity']}"
                )
            dangerous_delta = {
                key: int(candidate_drc["dangerous"][key])
                - int(baseline_drc["dangerous"][key])
                for key in candidate_drc["dangerous"]
            }
            if any(candidate_drc["dangerous"].values()) or any(
                value > 0 for value in dangerous_delta.values()
            ):
                raise RouteError(
                    "candidate introduces/contains fatal routing DRC classes: "
                    + json.dumps(
                        {
                            "candidate": candidate_drc["dangerous"],
                            "delta": dangerous_delta,
                        }
                    )
                )

            render_top = render(kicad_cli, candidate, top_temp, "top")
            render_bottom = render(kicad_cli, candidate, bottom_temp, "bottom")

            if sha256_file(source) != source_hash_before:
                raise RouteError("selected source changed during BQ routing")

            previous_sha = sha256_file(OUTPUT_BOARD) if OUTPUT_BOARD.is_file() else None
            if OUTPUT_BOARD.is_file():
                shutil.copy2(OUTPUT_BOARD, previous_output)
            os.replace(candidate, OUTPUT_BOARD)
            candidate = None
            try:
                os.replace(top_temp, TOP_PREVIEW)
                os.replace(bottom_temp, BOTTOM_PREVIEW)
                DRC_JSON.write_bytes(candidate_drc_raw)
            except Exception:
                if previous_output.is_file():
                    os.replace(previous_output, OUTPUT_BOARD)
                elif OUTPUT_BOARD.is_file():
                    OUTPUT_BOARD.unlink()
                raise

            if sha256_file(FORMAL_BOARD) != formal_before:
                raise RouteError("formal B3 PCB changed unexpectedly")
            if sha256_file(R3_BOARD) != r3_before:
                raise RouteError("R3 staging PCB changed unexpectedly")
            if sha256_file(R4_BOARD) != r4_before:
                raise RouteError("R4 staging PCB changed unexpectedly")

            report = {
                "schema": 1,
                "tool": Path(__file__).name,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R5_BQ_POWERPATH_ROUTED_CANDIDATE_PARTIAL_BOARD",
                "overall_status": "HOLD",
                "operation_completed": True,
                "routing_checks_passed": True,
                "locally_verified": False,
                "inputs": {
                    "runner": {
                        "path": str(Path(__file__).resolve()),
                        "sha256": sha256_file(Path(__file__).resolve()),
                    },
                    "source": {
                        "path": str(source),
                        "expected_sha256": expected_source_hash,
                        "sha256": source_hash_before,
                    },
                    "frozen_r4": {"path": str(R4_BOARD), "sha256": r4_before},
                    "canonical_schematic": {
                        "path": str(CANONICAL_SCHEMATIC),
                        "sha256": sha256_file(CANONICAL_SCHEMATIC),
                    },
                },
                "output": {
                    "path": str(OUTPUT_BOARD),
                    "previous_sha256": previous_sha,
                    "sha256": sha256_file(OUTPUT_BOARD),
                    "bytes": OUTPUT_BOARD.stat().st_size,
                },
                "audit": {
                    "source_copper_items": sum(source_tracks.values()),
                    "added_copper_items": len(added_items),
                    "added_track_segments": len(added_items) - len(new_vias),
                    "added_vias": len(new_vias),
                    "added_nets": sorted(added_nets),
                    "source_copper_preserved": True,
                    "footprints_preserved": True,
                    "zone_outlines_settings_preserved": True,
                    "new_copper_outside_frozen_b2": True,
                    "usb_data_copper_added": False,
                    "j6_external_copper_added": False,
                    "formal_r3_r4_unchanged": True,
                    "track_via_uuid_uniqueness": {
                        "source": source_uuid_audit,
                        "candidate": candidate_uuid_audit,
                    },
                    "route_manifest": route_manifest(),
                    "vsys_connected_set": {
                        "u4_bank_required_from_source": require_u4_bank,
                        "source": source_vsys_proof,
                        "candidate": candidate_vsys_proof,
                        "accepted": bool(
                            candidate_vsys_proof["core_same_connected_set"]
                        )
                        and (
                            not require_u4_bank
                            or bool(
                                candidate_vsys_proof["full_chain_same_connected_set"]
                            )
                        ),
                    },
                },
                "drc": {
                    "source": baseline_drc,
                    "candidate": candidate_drc,
                    "dangerous_category_delta": dangerous_delta,
                    "report_path": str(DRC_JSON),
                    "report_sha256": sha256_file(DRC_JSON),
                },
                "previews": {
                    "top": {
                        **render_top,
                        "path": str(TOP_PREVIEW),
                        "sha256": sha256_file(TOP_PREVIEW),
                    },
                    "bottom": {
                        **render_bottom,
                        "path": str(BOTTOM_PREVIEW),
                        "sha256": sha256_file(BOTTOM_PREVIEW),
                    },
                },
                "holds": [
                    "J6 BAT/NTC external route is HOLD pending exact battery pack, mating harness, pin-order and NTC contract",
                    "USB D+/D- are HOLD pending final 90-ohm stackup geometry",
                    "U4 pin-field copper is source-owned and preserved; this stage terminates at C31, while TF, EPD and global WROOM/STM controls remain outside scope",
                    "0.50-0.80 mm power geometry is a candidate; worst-case current, copper weight, temperature rise and BQ thermal validation remain HOLD",
                    "U2 EPAD through-via fill/tent and solder-wicking strategy remains an assembly HOLD",
                    "whole-board unconnected items and unrelated inherited DRC findings remain, so this is not LOCALLY_VERIFIED",
                ],
                "hardware_accessed": False,
            }
            AUDIT_JSON.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except Exception as exc:
        report = {
            "schema": 1,
            "tool": Path(__file__).name,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "state": "HOLD_BQ_POWERPATH_ROUTING_FAILED",
            "overall_status": "FAIL",
            "operation_completed": False,
            "routing_checks_passed": False,
            "locally_verified": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "output": str(OUTPUT_BOARD),
            "formal_b3_modified": False,
            "hardware_accessed": False,
        }
    finally:
        if candidate is not None and candidate.exists():
            if candidate.parent.resolve() != STAGING.resolve():
                raise RouteError(f"refusing cleanup outside staging: {candidate}")
            candidate.unlink()
        for companion in candidate_companions:
            if companion.exists():
                if companion.parent.resolve() != STAGING.resolve():
                    raise RouteError(f"refusing cleanup outside staging: {companion}")
                companion.unlink()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
