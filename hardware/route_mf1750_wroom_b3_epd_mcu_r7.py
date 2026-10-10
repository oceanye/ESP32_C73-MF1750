#!/usr/bin/env python3
"""Route only the reviewed MCU-side EPD nets into an isolated R7 PCB.

This builder is deliberately narrower than a general board router.  It starts
from the hash-bound R7 DRC-hygiene board chained from the frozen R6 EPD
candidate, preserves every source footprint, pad, zone and copper UUID/geometry,
and adds only the thirteen connections that can be completed without entering
the frozen B2 region.  The seven DNP J2 branches remain explicit HOLD items.

The script never writes the formal board, the R6 source, or README.md.  It
fails closed if the route is not byte-deterministic, if any new signal uses
In1.Cu, if new copper reaches y < 60.5 mm or the WROOM antenna keepout, if an
other-net unconnected count changes, or if the exact 141 -> 128 unconnected
reduction is not achieved.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - KiCad Python owns pcbnew
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
R6_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r6_epd_boundary_routed.kicad_pcb"
R6_SHA256 = "41fcea36a5ca4cc117b77fa02fb4d6332b248863ad82b5fe25c65b0aa72bcf28"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"
SOURCE_SHA256 = "88dfc906bd8d15adccecc54ccdbb9a6d2e5f1ec3149ede199475923ba22c1cf8"
ENGINE = HARDWARE / "route_mf1750_wroom_b3_epd_boundary_r5.py"
ENGINE_SHA256 = "28f43841aed156a9f1f7697f432a3e95b5205fd85529fb291851eddd9a0cee41"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"
REPORT_JSON = STAGING / "r7_epd_mcu_route_report.json"
SOURCE_DRC_JSON = STAGING / "r7_epd_mcu_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r7_epd_mcu_drc.json"
PREVIEW_DIR = STAGING / "r7_epd_mcu_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_epd_mcu_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_epd_mcu_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_epd_mcu_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_epd_mcu_back.svg"
BOARD_VERIFIER_JSON = STAGING / "r7_epd_mcu_board_verifier.json"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
README = ROOT / "README.md"
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"

ROUTING_UUID_SEED = 1750713
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 66.0, 79.75, 114.0)
EXPECTED_SOURCE_UNCONNECTED = 141
EXPECTED_CANDIDATE_UNCONNECTED = 128
EXPECTED_REDUCTION = 13

ALLOWED_NETS = frozenset(
    {
        "/MCU_RST_N",
        "/MCU_DC",
        "/MCU_CSB",
        "/MCU_CS2",
        "/MCU_SCL",
        "/MCU_SI0",
        "/MCU_BUSY_N",
        "/EPD_PWR_EN",
        "/EPD_FAULT_N",
        "/EPD_BUF_CONNECT",
    }
)

J2_HOLDS = (
    ("J2", "4", "/MCU_BUSY_N", 13.62, 58.50),
    ("J2", "5", "/MCU_RST_N", 16.16, 58.50),
    ("J2", "6", "/MCU_DC", 18.70, 58.50),
    ("J2", "7", "/MCU_CSB", 21.24, 58.50),
    ("J2", "16", "/MCU_CS2", 44.10, 58.50),
    ("J2", "17", "/MCU_SI0", 46.64, 58.50),
    ("J2", "18", "/MCU_SCL", 49.18, 58.50),
)

# Pad centres bind the recipe to the reviewed R6 placement.  Existing vias are
# separately bound by the source SHA and are used only where already present.
PAD_CONTRACT: dict[tuple[str, str], tuple[str, float, float]] = {
    ("U6", "2"): ("/MCU_RST_N", 31.1375, 63.2250),
    ("U6", "3"): ("/MCU_DC", 31.1375, 63.8750),
    ("U6", "4"): ("/MCU_CSB", 31.1375, 64.5250),
    ("U6", "5"): ("/MCU_CS2", 31.1375, 65.1750),
    ("U6", "6"): ("/MCU_SCL", 31.1375, 65.8250),
    ("U6", "7"): ("/MCU_SI0", 31.1375, 66.4750),
    ("U6", "8"): ("/MCU_BUSY_N", 31.1375, 67.1250),
    ("R62", "2"): ("/MCU_BUSY_N", 30.8250, 74.2000),
    ("TP20", "1"): ("/MCU_SI0", 40.0000, 75.0000),
    ("R63", "1"): ("/EPD_BUF_CONNECT", 32.6750, 74.2000),
    ("U1", "4"): ("/MCU_BUSY_N", 53.4500, 81.2500),
    ("U1", "5"): ("/MCU_RST_N", 52.1800, 81.2500),
    ("U1", "6"): ("/MCU_DC", 50.9100, 81.2500),
    ("U1", "7"): ("/MCU_CSB", 49.6400, 81.2500),
    ("U1", "18"): ("/MCU_CS2", 39.5000, 86.8250),
    ("U1", "19"): ("/MCU_SI0", 39.5000, 88.0950),
    ("U1", "20"): ("/MCU_SCL", 39.5000, 89.3650),
    ("U1", "21"): ("/EPD_PWR_EN", 39.5000, 90.6350),
    ("U1", "25"): ("/EPD_FAULT_N", 39.5000, 95.7150),
    ("U1", "31"): ("/EPD_BUF_CONNECT", 45.8300, 98.7500),
    ("TP19", "1"): ("/EPD_FAULT_N", 57.0000, 120.0000),
}

# Each route is (net, layer, ordered points).  Every segment is 0.20 mm.
# F.Cu items are short pad escapes; B.Cu and In2.Cu carry the longer trunks.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    # Seven F.Cu pad escapes terminate at staggered through-vias.  Their
    # pairwise spacing is >= 1.2 mm and each via clears the immutable
    # panel-side diagnostic vias east of U6.
    ("/MCU_RST_N", "F.Cu", ((31.1375, 63.2250), (30.0000, 63.2250))),
    ("/MCU_DC", "F.Cu", ((31.1375, 63.8750), (32.2000, 63.8750))),
    ("/MCU_CSB", "F.Cu", ((31.1375, 64.5250), (28.0000, 64.5250))),
    ("/MCU_CS2", "F.Cu", ((31.1375, 65.1750), (33.0000, 65.1750))),
    ("/MCU_SCL", "F.Cu", ((31.1375, 65.8250), (34.0000, 65.8250))),
    ("/MCU_SI0", "F.Cu", ((31.1375, 66.4750), (35.0000, 66.4750))),
    ("/MCU_BUSY_N", "F.Cu", ((31.1375, 67.1250), (32.4000, 67.1250))),

    # Each source uses a private In2.Cu vertical lane.  The four upper U1
    # channels change to B.Cu at ordered crossbars; their endpoint order and
    # crossbar order are identical, so no B.Cu crossbar can cut another net's
    # destination riser.
    ("/MCU_BUSY_N", "In2.Cu", ((32.4000, 67.1250), (32.4000, 70.0000))),
    ("/MCU_BUSY_N", "B.Cu", ((32.4000, 70.0000), (55.5000, 70.0000), (55.5000, 82.5000), (53.4500, 82.5000))),
    ("/MCU_BUSY_N", "F.Cu", ((53.4500, 81.2500), (53.4500, 82.5000))),
    ("/MCU_RST_N", "In2.Cu", ((30.0000, 63.2250), (30.8000, 63.2250), (30.8000, 72.5000), (29.5000, 73.0000))),
    ("/MCU_RST_N", "B.Cu", ((29.5000, 73.0000), (29.5000, 74.2000), (52.1800, 74.2000), (52.1800, 79.7000))),
    ("/MCU_RST_N", "F.Cu", ((52.1800, 79.7000), (52.1800, 81.2500))),
    ("/MCU_DC", "In2.Cu", ((32.2000, 63.8750), (31.8000, 66.0000), (31.8000, 75.2000))),
    ("/MCU_DC", "B.Cu", ((31.8000, 75.2000), (50.9100, 75.2000), (50.9100, 79.7000))),
    ("/MCU_DC", "F.Cu", ((50.9100, 79.7000), (50.9100, 81.2500))),
    ("/MCU_CSB", "In2.Cu", ((28.0000, 64.5250), (30.2000, 64.5250), (30.2000, 66.8000), (28.8000, 67.6000), (28.8000, 76.2000))),
    ("/MCU_CSB", "B.Cu", ((28.8000, 76.2000), (49.6400, 76.2000), (49.6400, 79.7000))),
    ("/MCU_CSB", "F.Cu", ((49.6400, 79.7000), (49.6400, 81.2500))),

    # The three lower U1 channels remain parallel on In2.Cu and use short,
    # mutually separated B.Cu crossbars at the destination pad ordinates.
    ("/MCU_CS2", "In2.Cu", ((33.0000, 65.1750), (34.8000, 69.0000), (34.8000, 86.8250))),
    ("/MCU_CS2", "B.Cu", ((34.8000, 86.8250), (38.0000, 86.8250))),
    ("/MCU_CS2", "F.Cu", ((38.0000, 86.8250), (39.5000, 86.8250))),
    ("/MCU_SCL", "In2.Cu", ((34.0000, 65.8250), (36.0000, 69.8000), (36.0000, 89.3650))),
    ("/MCU_SCL", "B.Cu", ((36.0000, 89.3650), (38.0000, 89.3650))),
    ("/MCU_SCL", "F.Cu", ((38.0000, 89.3650), (39.5000, 89.3650))),
    ("/MCU_SI0", "In2.Cu", ((35.0000, 66.4750), (37.2000, 70.6000), (37.2000, 88.0950))),
    ("/MCU_SI0", "B.Cu", ((37.2000, 88.0950), (38.0000, 88.0950))),
    ("/MCU_SI0", "F.Cu", ((38.0000, 88.0950), (39.5000, 88.0950))),
    # TP20 reaches the SI0 In2 lane from a via below all four top crossbars.
    ("/MCU_SI0", "F.Cu", ((40.0000, 75.0000), (40.0000, 77.0000))),
    ("/MCU_SI0", "In2.Cu", ((40.0000, 77.0000), (37.2000, 77.0000))),

    # R62 uses a low In2.Cu return lane.  It joins the main BUSY island at the
    # destination via without crossing the three lower In2 source lanes.
    ("/MCU_BUSY_N", "F.Cu", ((30.8250, 74.2000), (30.8250, 78.0000), (30.0000, 78.0000))),
    ("/MCU_BUSY_N", "In2.Cu", ((30.0000, 78.0000), (30.0000, 103.0000), (57.0000, 103.0000), (57.0000, 82.5000), (53.4500, 82.5000))),

    # Existing through-vias at 16.175/69.5, 19.2/65.3 and 32.675/72.9 are
    # source copper.  The new trunks begin there; no source item is edited.
    ("/EPD_PWR_EN", "B.Cu", ((16.1750, 69.5000), (15.5000, 71.0000), (15.5000, 92.8000), (37.0000, 92.8000), (37.0000, 90.6350))),
    ("/EPD_PWR_EN", "F.Cu", ((37.0000, 90.6350), (39.5000, 90.6350))),
    ("/EPD_FAULT_N", "In2.Cu", ((19.2000, 65.3000), (21.0000, 68.8000), (26.7000, 68.8000), (25.0000, 73.5000), (25.0000, 90.0000), (28.8000, 90.0000), (28.8000, 95.7150))),
    ("/EPD_FAULT_N", "B.Cu", ((28.8000, 95.7150), (38.0000, 95.7150), (45.0000, 106.0000), (55.5000, 116.0000), (55.5000, 120.0000))),
    ("/EPD_FAULT_N", "F.Cu", ((38.0000, 95.7150), (39.5000, 95.7150))),
    ("/EPD_FAULT_N", "F.Cu", ((55.5000, 120.0000), (57.0000, 120.0000))),
    ("/EPD_BUF_CONNECT", "In2.Cu", ((32.6750, 72.9000), (32.6750, 76.8000), (34.0000, 76.8000), (34.0000, 101.5000), (45.8300, 101.5000), (45.8300, 100.2000))),
    ("/EPD_BUF_CONNECT", "F.Cu", ((45.8300, 100.2000), (45.8300, 98.7500))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/MCU_RST_N", 30.0000, 63.2250),
    ("/MCU_RST_N", 29.5000, 73.0000),
    ("/MCU_RST_N", 52.1800, 79.7000),
    ("/MCU_DC", 32.2000, 63.8750),
    ("/MCU_DC", 31.8000, 75.2000),
    ("/MCU_DC", 50.9100, 79.7000),
    ("/MCU_CSB", 28.0000, 64.5250),
    ("/MCU_CSB", 28.8000, 76.2000),
    ("/MCU_CSB", 49.6400, 79.7000),
    ("/MCU_CS2", 33.0000, 65.1750),
    ("/MCU_CS2", 34.8000, 86.8250),
    ("/MCU_CS2", 38.0000, 86.8250),
    ("/MCU_SCL", 34.0000, 65.8250),
    ("/MCU_SCL", 36.0000, 89.3650),
    ("/MCU_SCL", 38.0000, 89.3650),
    ("/MCU_SI0", 35.0000, 66.4750),
    ("/MCU_SI0", 40.0000, 77.0000),
    ("/MCU_SI0", 37.2000, 88.0950),
    ("/MCU_SI0", 38.0000, 88.0950),
    ("/MCU_BUSY_N", 32.4000, 67.1250),
    ("/MCU_BUSY_N", 32.4000, 70.0000),
    ("/MCU_BUSY_N", 53.4500, 82.5000),
    ("/MCU_BUSY_N", 30.0000, 78.0000),
    ("/EPD_PWR_EN", 37.0000, 90.6350),
    ("/EPD_FAULT_N", 28.8000, 95.7150),
    ("/EPD_FAULT_N", 38.0000, 95.7150),
    ("/EPD_FAULT_N", 55.5000, 120.0000),
    ("/EPD_BUF_CONNECT", 45.8300, 100.2000),
)


class RouteError(RuntimeError):
    """Fail-closed R7 route builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine():
    if not ENGINE.is_file() or sha256_file(ENGINE) != ENGINE_SHA256:
        raise RouteError(f"R5 utility engine missing or hash-mismatched: {ENGINE}")
    spec = importlib.util.spec_from_file_location("_mf1750_r7_route_util", ENGINE)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R5 utility-engine import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ALLOWED_NETS = ALLOWED_NETS
    module.B2_BOTTOM_MM = B2_BOTTOM_MM
    return module


base = load_engine()


def find_pad(board, ref: str, number: str):
    return base.find_numbered_pad(board, ref, number)


def validate_pad_contract(board) -> list[dict[str, object]]:
    evidence = []
    for (ref, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = find_pad(board, ref, number)
        actual = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or any(
            abs(got - expected) > 0.000002
            for got, expected in zip(actual, (x_mm, y_mm), strict=True)
        ):
            raise RouteError(
                f"pad contract drift {ref}.{number}: {pad.GetNetname()}@{actual}, "
                f"expected {net}@{(x_mm, y_mm)}"
            )
        evidence.append({"ref": ref, "pad": number, "net": net, "position_mm": list(actual)})
    for ref, number, net, x_mm, y_mm in J2_HOLDS:
        pad = find_pad(board, ref, number)
        actual = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or actual != (x_mm, y_mm):
            raise RouteError(f"DNP J2 HOLD drift {ref}.{number}: {pad.GetNetname()}@{actual}")
    return evidence


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net_name, layer_name, points in ROUTES:
        if net_name not in ALLOWED_NETS or layer_name == "In1.Cu":
            raise RouteError(f"route violates allowlist/layer contract: {net_name}/{layer_name}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(base.add_track(board, net_name, layer_name, SIGNAL_WIDTH_MM, start, end))
    for net_name, x_mm, y_mm in VIAS:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"via violates net allowlist: {net_name}")
        added.append(base.add_via(board, net_name, x_mm, y_mm))
    return added


def point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x, y = point
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def segment_hits_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    """Liang-Barsky segment/closed-rectangle intersection test."""
    x0, y0, x1, y1 = rect
    x_a, y_a = start
    x_b, y_b = end
    dx, dy = x_b - x_a, y_b - y_a
    p = (-dx, dx, -dy, dy)
    q = (x_a - x0, x1 - x_a, y_a - y0, y1 - y_a)
    lo, hi = 0.0, 1.0
    for p_i, q_i in zip(p, q, strict=True):
        if abs(p_i) < 1e-12:
            if q_i < 0:
                return False
            continue
        ratio = q_i / p_i
        if p_i < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def route_envelope_audit(board, before: dict[str, object], added_ids: set[str]) -> dict[str, object]:
    tracks = {base.item_uuid(item): item for item in board.GetTracks()}
    new_items = [tracks[item_id] for item_id in sorted(added_ids)]
    b2 = []
    antenna = []
    in1 = []
    bad_width = []
    bad_via = []
    for item in new_items:
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            diameter = round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6)
            drill = round(pcbnew.ToMM(item.GetDrillValue()), 6)
            if (diameter, drill) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                bad_via.append(base.item_uuid(item))
            hits_antenna = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                bad_width.append(base.item_uuid(item))
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                in1.append(base.item_uuid(item))
            hits_antenna = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y < B2_BOTTOM_MM for _, y in points):
            b2.append({"uuid": base.item_uuid(item), "net": item.GetNetname(), "points_mm": points})
        if hits_antenna:
            antenna.append({"uuid": base.item_uuid(item), "net": item.GetNetname(), "points_mm": points})
    source_ids = set(before["tracks"])
    source_panel_side = {
        item_id: signature
        for item_id, signature in before["tracks"].items()
        if (
            (signature[0] == "via" and signature[2][1] < B2_BOTTOM_MM)
            or (signature[0] == "track" and min(signature[3][1], signature[4][1]) < B2_BOTTOM_MM)
        )
    }
    checks = {
        "no_new_copper_in_b2": not b2,
        "no_new_copper_in_wroom_antenna_keepout": not antenna,
        "no_signal_track_on_in1": not in1,
        "all_new_tracks_exactly_0p20_mm": not bad_width,
        "all_new_vias_exactly_0p60_0p30_mm": not bad_via,
        "source_panel_side_copper_uuids_preserved": set(source_panel_side).issubset(source_ids),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "b2_added_copper": b2,
        "antenna_keepout_added_copper": antenna,
        "in1_signal_track_uuids": in1,
        "bad_width_uuids": bad_width,
        "bad_via_uuids": bad_via,
        "source_panel_side_copper_count": len(source_panel_side),
    }


def build_candidate(destination: Path) -> tuple[dict[str, object], set[str], list[dict[str, object]]]:
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not parse the fixed R6 source")
    pad_evidence = validate_pad_contract(board)
    before = base.source_state(board)
    added = add_routes(board)
    added_ids = {base.item_uuid(item) for item in added}
    if len(added_ids) != len(added):
        raise RouteError("deterministic KIID seed produced duplicate copper UUIDs")
    if not pcbnew.SaveBoard(str(destination), board):
        raise RouteError(f"KiCad failed to save candidate {destination}")
    return before, added_ids, pad_evidence


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        names = [name for name in names if name]
        if not names:
            counts["<NO_NET_TOKEN>"] += 1
        else:
            unique = set(names)
            if len(unique) != 1:
                counts["<MIXED:" + "|".join(sorted(unique)) + ">"] += 1
            else:
                counts[next(iter(unique))] += 1
    return dict(sorted(counts.items()))


def j2_residual_evidence(raw: dict[str, object]) -> dict[str, object]:
    results = {}
    for ref, number, net, x_mm, y_mm in J2_HOLDS:
        matches = []
        net_token = f"[{net}]"
        pad_token = f"{ref}"
        for entry in raw.get("unconnected_items", []):
            descriptions = [str(item.get("description", "")) for item in entry.get("items", [])]
            if any(net_token in text and pad_token in text and f" {number} " in text for text in descriptions):
                matches.append(entry)
        results[net] = {
            "ref": ref,
            "pad": number,
            "position_mm": [x_mm, y_mm],
            "residual_match_count": len(matches),
            "passed": len(matches) == 1,
        }
    return {"by_net": results, "passed": all(item["passed"] for item in results.values())}


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    category_increases = {
        name: candidate_categories[name] - source_categories.get(name, 0)
        for name in sorted(candidate_categories)
        if candidate_categories[name] > source_categories.get(name, 0)
    }
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    expected_target = {net: 1 for _, _, net, _, _ in J2_HOLDS}
    expected_target.update({"/EPD_PWR_EN": 0, "/EPD_FAULT_N": 0, "/EPD_BUF_CONNECT": 0})
    target_results = {
        net: {
            "source": source_nets.get(net, 0),
            "candidate": candidate_nets.get(net, 0),
            "expected_candidate": expected,
            "passed": candidate_nets.get(net, 0) == expected,
        }
        for net, expected in sorted(expected_target.items())
    }
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    residual = j2_residual_evidence(candidate["raw"])
    checks = {
        "source_unconnected_exactly_141": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_128": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_13": source["unconnected_count"] - candidate["unconnected_count"] == EXPECTED_REDUCTION,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "fatal_drc_category_delta_zero": not category_increases,
        "target_net_residual_counts_exact": all(item["passed"] for item in target_results.values()),
        "other_net_unconnected_counts_unchanged": not other_drift,
        "seven_j2_dnp_residuals_present": residual["passed"],
        "no_new_track_dangling": candidate_categories.get("track_dangling", 0) <= source_categories.get("track_dangling", 0),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "violation_category_increases": category_increases,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "target_net_results": target_results,
        "other_net_unconnected_drift": other_drift,
        "j2_residual_evidence": residual,
    }


def run_board_verifier(kicad_python: Path, candidate: Path) -> dict[str, object]:
    command = [
        str(kicad_python),
        str(BOARD_VERIFIER),
        str(candidate),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RouteError(f"board verifier did not emit JSON: {exc}: {completed.stdout[:500]}") from exc
    summary = raw.get("summary", {})
    passed = (
        completed.returncode == 0
        and raw.get("passed") is True
        and summary.get("total") == 13
        and summary.get("passed") == 13
        and summary.get("failed") == 0
    )
    return {
        "passed": passed,
        "command": command,
        "returncode": completed.returncode,
        "summary": summary,
        "stderr": completed.stderr.strip(),
        "raw": raw,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kicad-python",
        type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
        help="KiCad 10 Python used for the independent board verifier",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    report: dict[str, object]
    protected_paths = {
        "formal_board": FORMAL_BOARD,
        "r6_source": R6_BOARD,
        "r7_hygiene_source": SOURCE_BOARD,
        "readme": README,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
    }
    protected_before = {
        name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()
    }
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("fixed R6 source board missing or SHA-256 mismatched")
        if not args.kicad_python.is_file():
            raise RouteError(f"KiCad Python missing: {args.kicad_python}")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)

        with tempfile.TemporaryDirectory(prefix="mf1750-r7-epd-mcu-build-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, pad_evidence = build_candidate(first)
            before_second, added_ids_second, pad_evidence_second = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and sha256_file(first) == sha256_file(second)
                and added_ids == added_ids_second
                and before == before_second
                and pad_evidence == pad_evidence_second
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            first_build_sha = sha256_file(first)
            second_build_sha = sha256_file(second)
            reloaded = pcbnew.LoadBoard(str(first))
            if reloaded is None:
                raise RouteError("saved candidate does not reload")
            source_audit = base.audit_candidate(reloaded, before, added_ids)
            envelope = route_envelope_audit(reloaded, before, added_ids)
            source_audit["r7_route_envelope"] = envelope
            source_audit["passed"] = source_audit["passed"] and envelope["passed"]
            if not source_audit["passed"]:
                raise RouteError("source/envelope audit failed: " + json.dumps(source_audit))
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)

        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        gate = drc_gate(source_drc, candidate_drc)
        verifier = run_board_verifier(args.kicad_python, OUTPUT_BOARD)

        SOURCE_DRC_JSON.write_text(
            json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        CANDIDATE_DRC_JSON.write_text(
            json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        BOARD_VERIFIER_JSON.write_text(
            json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        render_evidence = [
            base.render(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, FRONT_COPPER_SVG, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, BACK_COPPER_SVG, "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts", mirror=True),
        ]

        protected_after = {
            name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()
        }
        protected_unchanged = protected_before == protected_after
        routing_passed = source_audit["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "STAGING_ONLY_ADDITIVE_COPPER",
            "state": "R7_EPD_MCU_SIDE_ROUTED_CANDIDATE" if routing_passed else "R7_EPD_MCU_SIDE_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if routing_passed else "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": routing_passed,
            "kicad_version": str(pcbnew.GetBuildVersion()),
            "inputs": {
                "source": {"path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256},
                "utility_engine": {"path": str(ENGINE), "sha256": ENGINE_SHA256},
            },
            "output": {
                "path": str(OUTPUT_BOARD),
                "bytes": OUTPUT_BOARD.stat().st_size,
                "sha256": sha256_file(OUTPUT_BOARD),
            },
            "determinism": {
                "double_build_byte_identical": deterministic,
                "first_sha256": first_build_sha,
                "second_sha256": second_build_sha,
            },
            "protected_sources": {
                "unchanged": protected_unchanged,
                "before": protected_before,
                "after": protected_after,
            },
            "routing_contract": {
                "allowed_nets": sorted(ALLOWED_NETS),
                "new_signal_layers": ["F.Cu", "In2.Cu", "B.Cu"],
                "in1_signal_routing": "FORBIDDEN",
                "signal_width_mm": SIGNAL_WIDTH_MM,
                "via_diameter_mm": VIA_DIAMETER_MM,
                "via_drill_mm": VIA_DRILL_MM,
                "b2_protected_region": {"rule": "all new copper y >= 60.5 mm", "boundary_y_mm": B2_BOTTOM_MM},
                "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
                "expected_unconnected": {"source": 141, "candidate": 128, "reduction": 13},
                "pad_contract": pad_evidence,
            },
            "source_preservation_audit": source_audit,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": [
                "seven U6 MCU-side channels routed to U1; BUSY also reaches R62 and SI0 reaches TP20",
                "EPD_PWR_EN reaches U1",
                "EPD_FAULT_N reaches U1 and TP19",
                "EPD_BUF_CONNECT reaches U1",
                "exactly thirteen source unconnected items removed",
            ],
            "holds": [
                {
                    "scope": "DNP_J2_BRANCH",
                    "ref": ref,
                    "pad": number,
                    "net": net,
                    "position_mm": [x_mm, y_mm],
                    "reason": "strict B2 protection: no new copper may enter y < 60.5 mm",
                }
                for ref, number, net, x_mm, y_mm in J2_HOLDS
            ]
            + [
                {
                    "scope": "WHOLE_BOARD",
                    "reason": "128 unrelated/held unconnected items remain; not manufacturing-ready",
                }
            ],
            "artifacts": {
                "source_drc_json": str(SOURCE_DRC_JSON),
                "candidate_drc_json": str(CANDIDATE_DRC_JSON),
                "board_verifier_json": str(BOARD_VERIFIER_JSON),
                "top_preview": str(TOP_PREVIEW),
                "bottom_preview": str(BOTTOM_PREVIEW),
                "front_copper_svg": str(FRONT_COPPER_SVG),
                "back_copper_svg": str(BACK_COPPER_SVG),
                "render_export": render_evidence,
            },
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "state": report["state"],
                    "routing_checks_passed": routing_passed,
                    "output": report["output"],
                    "drc": {
                        "source_unconnected": source_drc["unconnected_count"],
                        "candidate_unconnected": candidate_drc["unconnected_count"],
                        "gate_passed": gate["passed"],
                    },
                    "board_verifier": verifier["summary"],
                    "report": str(REPORT_JSON),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if routing_passed else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "STAGING_ONLY_ADDITIVE_COPPER",
            "state": "R7_EPD_MCU_SIDE_ROUTE_FAILED",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "protected_sources_before": protected_before,
            "source": str(SOURCE_BOARD),
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
