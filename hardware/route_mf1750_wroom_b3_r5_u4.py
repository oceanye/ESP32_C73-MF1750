#!/usr/bin/env python3
"""Route the TPS63070 island into an isolated MF1750 B3 R5 staging PCB.

This builder is deliberately narrow.  It preserves every footprint, drawing,
zone outline/setting, and pre-existing copper item from the selected R4-derived
source.  It only adds copper on a frozen TPS63070-net allow-list and never
writes the formal B3 PCB, the schematic, R3, or R4.

The default source is hash-bound to the reviewed R4 candidate.  A caller may
chain this builder after another independent R5 builder by supplying both
``--source`` and ``--source-sha256``.  This prevents a silently changed board
from being routed against coordinates reviewed for a different placement.
"""

from __future__ import annotations

import argparse
import collections
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
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r5_u4_routed.kicad_pcb"
AUDIT_JSON = STAGING / "r5_u4_route_audit.json"
DRC_JSON = STAGING / "r5_u4_drc.json"
PREVIEW_DIR = STAGING / "r5_u4_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_u4_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r5_u4_bottom.png"

ROUTING_UUID_SEED = 17505
ROUTE_BBOX_MM = (11.0, 75.5, 34.5, 95.0)
ALLOWED_NETS = frozenset(
    {
        "/VSYS_RAW",
        "/SYS_3V3",
        "/DCDC_L1",
        "/DCDC_L2",
        "GND",
        "/DCDC_VAUX",
        "/DCDC_PS_SYNC",
        "/DCDC_PG",
        "/DCDC_EN",
        "/DCDC_FB",
    }
)
ISLAND_REFS = frozenset(
    {
        "U4",
        "L3",
        "C31",
        "C32",
        "C33",
        "C34",
        "C35",
        "C36",
        "C37",
        "C38",
        "C46",
        "C47",
        "R29",
        "R30",
        "R31",
        "R32",
        "R61",
    }
)

# Pad centres and nets bind every route to the reviewed R4 placement.  Values
# are millimetres in the board coordinate system.  Duplicate/compound U4 pads
# are intentionally addressed by their unique numbered pad used below.
PAD_CONTRACT: dict[tuple[str, str], tuple[str, float, float]] = {
    ("U4", "1"): ("/DCDC_PS_SYNC", 22.850, 84.750),
    ("U4", "2"): ("/DCDC_PG", 22.850, 85.250),
    ("U4", "3"): ("/DCDC_VAUX", 22.850, 85.750),
    ("U4", "4"): ("GND", 22.850, 86.250),
    ("U4", "5"): ("/DCDC_FB", 23.275, 86.900),
    ("U4", "8"): ("/SYS_3V3", 24.775, 86.900),
    ("U4", "9"): ("/DCDC_L2", 24.675, 86.000),
    ("U4", "10"): ("GND", 24.500, 85.500),
    ("U4", "11"): ("/DCDC_L1", 24.675, 85.000),
    ("U4", "12"): ("/VSYS_RAW", 24.775, 84.100),
    ("U4", "14"): ("/DCDC_EN", 23.775, 84.100),
    ("U4", "15"): ("GND", 23.275, 84.100),
    ("L3", "1"): ("/DCDC_L1", 28.700, 84.315),
    ("L3", "2"): ("/DCDC_L2", 28.700, 86.685),
    ("C31", "1"): ("/VSYS_RAW", 16.450, 84.000),
    ("C32", "1"): ("/VSYS_RAW", 16.450, 87.000),
    ("C33", "1"): ("/VSYS_RAW", 16.450, 90.000),
    ("C34", "1"): ("/SYS_3V3", 15.475, 93.500),
    ("C35", "1"): ("/SYS_3V3", 20.975, 93.500),
    ("C36", "1"): ("/SYS_3V3", 26.475, 93.500),
    ("C37", "1"): ("/SYS_3V3", 30.950, 93.500),
    ("C38", "1"): ("/DCDC_VAUX", 20.925, 86.250),
    ("C38", "2"): ("GND", 19.375, 86.250),
    ("C46", "1"): ("/VSYS_RAW", 24.775, 82.150),
    ("C46", "2"): ("GND", 23.225, 82.150),
    ("C47", "1"): ("/SYS_3V3", 25.200, 88.825),
    ("C47", "2"): ("GND", 25.200, 90.375),
    ("R29", "1"): ("/VSYS_RAW", 19.325, 84.200),
    ("R29", "2"): ("/DCDC_PS_SYNC", 20.975, 84.200),
    ("R30", "1"): ("/SYS_3V3", 30.675, 80.500),
    ("R30", "2"): ("/DCDC_PG", 32.325, 80.500),
    ("R31", "1"): ("/SYS_3V3", 20.900, 90.425),
    ("R31", "2"): ("/DCDC_FB", 20.900, 88.775),
    ("R32", "1"): ("/DCDC_FB", 23.150, 88.775),
    ("R32", "2"): ("GND", 23.150, 90.425),
    ("R61", "1"): ("/DCDC_EN", 26.175, 77.000),
}

# Each entry is (net, layer, width_mm, point sequence).  The two switching
# nodes neck down only at U4's 0.25 mm-high pads, then widen before L3.  FB is
# routed below/left of U4 and never shares the switch-node corridor.
ROUTES: tuple[tuple[str, int, float, tuple[tuple[float, float], ...]], ...] = (
    # TPS63070 <-> inductor switch nodes.
    (
        "/DCDC_L1",
        0,
        0.20,
        ((24.675, 85.000), (26.000, 85.000), (26.400, 84.550)),
    ),
    (
        "/DCDC_L1",
        0,
        0.60,
        ((26.400, 84.550), (28.700, 84.550), (28.700, 84.315)),
    ),
    (
        "/DCDC_L2",
        0,
        0.20,
        ((24.675, 86.000), (26.000, 86.000), (26.400, 86.450)),
    ),
    (
        "/DCDC_L2",
        0,
        0.60,
        ((26.400, 86.450), (28.700, 86.450), (28.700, 86.685)),
    ),
    # Input HF loop and the local bulk bank.  The short 0.20 mm segment passes
    # between C46 and the EN escape; it is not accepted as a final current-
    # capacity proof (see HOLD list).
    ("/VSYS_RAW", 0, 0.60, ((24.775, 82.150), (24.775, 83.400))),
    ("/VSYS_RAW", 0, 0.25, ((24.775, 83.400), (24.775, 84.100))),
    ("/VSYS_RAW", 0, 0.80, ((16.450, 84.000), (16.450, 82.950), (21.300, 82.950))),
    ("/VSYS_RAW", 0, 0.20, ((21.300, 82.950), (24.775, 82.950))),
    ("/VSYS_RAW", 0, 0.40, ((24.775, 82.950), (24.775, 82.150))),
    ("/VSYS_RAW", 0, 0.80, ((16.450, 84.000), (16.450, 87.000), (16.450, 90.000))),
    ("/VSYS_RAW", 0, 0.30, ((19.325, 84.200), (19.325, 82.950))),
    # Output HF loop, local bulk bank, and output-side feedback take-off.
    (
        "/SYS_3V3",
        0,
        0.20,
        ((24.775, 86.900), (24.775, 87.300)),
    ),
    (
        "/SYS_3V3",
        0,
        0.45,
        ((24.775, 87.300), (25.200, 87.600), (25.200, 88.825)),
    ),
    (
        "/SYS_3V3",
        0,
        0.60,
        ((25.200, 88.825), (26.200, 88.825), (26.200, 91.500)),
    ),
    ("/SYS_3V3", 0, 0.80, ((15.475, 91.500), (31.600, 91.500))),
    ("/SYS_3V3", 0, 0.80, ((15.475, 91.500), (15.475, 93.500))),
    ("/SYS_3V3", 0, 0.80, ((20.975, 91.500), (20.975, 93.500))),
    ("/SYS_3V3", 0, 0.80, ((26.475, 91.500), (26.475, 93.500))),
    ("/SYS_3V3", 0, 0.80, ((30.950, 91.500), (30.950, 93.500))),
    ("/SYS_3V3", 0, 0.20, ((20.900, 90.425), (20.900, 91.500))),
    ("/SYS_3V3", 0, 0.20, ((30.675, 80.500), (30.675, 81.500))),
    (
        "/SYS_3V3",
        2,
        0.40,
        ((30.675, 81.500), (31.600, 82.425), (31.600, 91.500)),
    ),
    # Quiet control and sense nets.
    (
        "/DCDC_PS_SYNC",
        0,
        0.20,
        ((20.975, 84.200), (21.500, 84.200), (22.200, 84.750), (22.850, 84.750)),
    ),
    (
        "/DCDC_VAUX",
        0,
        0.20,
        ((20.925, 86.250), (21.500, 86.250), (22.400, 85.750), (22.850, 85.750)),
    ),
    ("/DCDC_FB", 0, 0.20, ((23.275, 86.900), (23.150, 88.775))),
    ("/DCDC_FB", 0, 0.20, ((23.150, 88.775), (20.900, 88.775))),
    # PG changes layer immediately outside the crowded left side and stays on
    # B.Cu until the R30 pull-up.  EN remains HOLD because no compliant escape
    # from U4 pad 14 can be proven without changing the frozen R4 placement.
    ("/DCDC_PG", 0, 0.20, ((22.850, 85.250), (20.000, 85.250))),
    (
        "/DCDC_PG",
        2,
        0.20,
        ((20.000, 85.250), (20.000, 78.800), (33.200, 78.800), (33.200, 80.500)),
    ),
    ("/DCDC_PG", 0, 0.20, ((33.200, 80.500), (32.325, 80.500))),
    # Explicit ground escape paths; the ground zones remain the authoritative
    # broad return planes after refill.
    ("GND", 0, 0.50, ((23.225, 82.150), (23.225, 80.900))),
    ("GND", 0, 0.20, ((24.500, 85.500), (26.600, 85.500))),
    (
        "GND",
        0,
        0.25,
        ((22.850, 86.250), (22.500, 86.550), (21.750, 87.350)),
    ),
    ("GND", 0, 0.50, ((19.375, 86.250), (18.300, 86.250))),
    ("GND", 0, 0.40, ((23.150, 90.425), (24.150, 90.425), (25.200, 90.375))),
    # One local plane-transition via per bulk capacitor ground pad.
    ("GND", 0, 0.50, ((14.550, 84.000), (13.500, 84.000))),
    ("GND", 0, 0.50, ((14.550, 87.000), (13.500, 87.000))),
    ("GND", 0, 0.50, ((14.550, 90.000), (13.500, 90.000))),
    ("GND", 0, 0.50, ((12.525, 93.500), (11.400, 93.500))),
    ("GND", 0, 0.50, ((18.025, 93.500), (17.000, 93.500))),
    ("GND", 0, 0.50, ((23.525, 93.500), (22.400, 93.500))),
    ("GND", 0, 0.50, ((29.050, 93.500), (28.000, 93.500))),
)

VIAS: tuple[tuple[str, float, float, float, float], ...] = (
    # net, x, y, diameter, drill (all through-vias)
    ("GND", 23.225, 80.900, 0.60, 0.30),
    ("GND", 26.600, 85.500, 0.60, 0.30),
    ("GND", 21.750, 87.350, 0.60, 0.30),
    ("GND", 18.300, 86.250, 0.60, 0.30),
    ("GND", 24.150, 90.425, 0.60, 0.30),
    ("GND", 13.500, 84.000, 0.60, 0.30),
    ("GND", 13.500, 87.000, 0.60, 0.30),
    ("GND", 13.500, 90.000, 0.60, 0.30),
    ("GND", 11.400, 93.500, 0.60, 0.30),
    ("GND", 17.000, 93.500, 0.60, 0.30),
    ("GND", 22.400, 93.500, 0.60, 0.30),
    ("GND", 28.000, 93.500, 0.60, 0.30),
    ("/DCDC_PG", 20.000, 85.250, 0.60, 0.30),
    ("/DCDC_PG", 33.200, 80.500, 0.60, 0.30),
    ("/SYS_3V3", 30.675, 81.500, 0.60, 0.30),
    ("/SYS_3V3", 31.600, 91.500, 0.60, 0.30),
)

# These groups are the positive, endpoint-level completion claim.  A falling
# unconnected count is only secondary evidence; every member below must appear
# in KiCad's same connected-item set after save/reload and zone refill.
LOCAL_CONNECTIVITY_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "vin_hf_and_local_bulk": (
        ("U4", "12"),
        ("C46", "1"),
        ("C31", "1"),
        ("C32", "1"),
        ("C33", "1"),
        ("R29", "1"),
    ),
    "vout_hf_and_local_bulk": (
        ("U4", "8"),
        ("C47", "1"),
        ("C34", "1"),
        ("C35", "1"),
        ("C36", "1"),
        ("C37", "1"),
        ("R30", "1"),
        ("R31", "1"),
    ),
    "switch_l1": (("U4", "11"), ("L3", "1")),
    "switch_l2": (("U4", "9"), ("L3", "2")),
    "vaux_decoupling": (("U4", "3"), ("C38", "1")),
    "ps_sync_series": (("U4", "1"), ("R29", "2")),
    "pg_local_pullup": (("U4", "2"), ("R30", "2")),
    "feedback_divider": (("U4", "5"), ("R31", "2"), ("R32", "1")),
    "local_ground_including_exposed_pad10": (
        ("U4", "4"),
        ("U4", "10"),
        ("C38", "2"),
        ("C46", "2"),
        ("C47", "2"),
        ("R32", "2"),
        ("C31", "2"),
        ("C32", "2"),
        ("C33", "2"),
        ("C34", "2"),
        ("C35", "2"),
        ("C36", "2"),
        ("C37", "2"),
    ),
}

FORBIDDEN_NEW_DRC_TYPES = frozenset(
    {"clearance", "shorting_items", "items_not_allowed", "courtyards_overlap"}
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
    candidates = [
        shutil.which("kicad-cli"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise RouteError("KiCad 10 kicad-cli was not found")


def point_mm(point) -> tuple[float, float]:
    return (pcbnew.ToMM(point.x), pcbnew.ToMM(point.y))


def item_uuid(item) -> str:
    return item.m_Uuid.AsString()


def footprint_signature(footprint) -> tuple[object, ...]:
    pos = footprint.GetPosition()
    pads = []
    for pad in footprint.Pads():
        pad_pos = pad.GetPosition()
        pads.append(
            (
                pad.m_Uuid.AsString(),
                pad.GetNumber(),
                pad.GetNetname(),
                int(pad_pos.x),
                int(pad_pos.y),
                int(pad.GetLayer()),
            )
        )
    return (
        footprint.GetFPID().GetUniStringLibId(),
        int(pos.x),
        int(pos.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
        tuple(sorted(pads)),
    )


def track_signature(item) -> tuple[object, ...]:
    start = item.GetStart()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            item_uuid(item),
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
        item_uuid(item),
        item.GetNetname(),
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


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
        item_uuid(zone),
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


def drawing_signature(item) -> tuple[object, ...]:
    box = item.GetBoundingBox()
    return (
        type(item).__name__,
        item_uuid(item),
        int(item.GetLayer()),
        int(box.GetX()),
        int(box.GetY()),
        int(box.GetWidth()),
        int(box.GetHeight()),
    )


def find_numbered_pad(board, ref: str, number: str):
    footprint = board.FindFootprintByReference(ref)
    if footprint is None:
        raise RouteError(f"missing required TPS63070-island footprint {ref}")
    pads = [pad for pad in footprint.Pads() if pad.GetNumber() == number]
    if len(pads) != 1:
        raise RouteError(f"{ref} pad {number} is not unique: found {len(pads)}")
    return pads[0]


def validate_pad_contract(board) -> list[dict[str, object]]:
    actual_refs = {fp.GetReference() for fp in board.GetFootprints()}
    missing_refs = sorted(ISLAND_REFS - actual_refs, key=natural_key)
    if missing_refs:
        raise RouteError(f"TPS63070-island refs missing: {missing_refs}")
    evidence = []
    for (ref, number), (expected_net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = find_numbered_pad(board, ref, number)
        actual_x, actual_y = point_mm(pad.GetPosition())
        if pad.GetNetname() != expected_net:
            raise RouteError(
                f"{ref}.{number} net drift: {pad.GetNetname()!r} != {expected_net!r}"
            )
        if abs(actual_x - x_mm) > 1e-6 or abs(actual_y - y_mm) > 1e-6:
            raise RouteError(
                f"{ref}.{number} placement drift: {(actual_x, actual_y)} != {(x_mm, y_mm)}"
            )
        evidence.append(
            {
                "ref": ref,
                "pad": number,
                "net": expected_net,
                "position_mm": [actual_x, actual_y],
            }
        )
    return evidence


def validate_local_connectivity(board) -> dict[str, object]:
    connectivity = board.GetConnectivity()
    groups: dict[str, object] = {}
    all_passed = True
    for name, members in LOCAL_CONNECTIVITY_GROUPS.items():
        anchor = find_numbered_pad(board, *members[0])
        connected_ids = {
            item_uuid(item) for item in connectivity.GetConnectedItems(anchor)
        }
        member_evidence = []
        for ref, number in members:
            pad = find_numbered_pad(board, ref, number)
            connected = item_uuid(pad) in connected_ids
            all_passed = all_passed and connected
            member_evidence.append(
                {"ref": ref, "pad": number, "connected_to_group_anchor": connected}
            )
        groups[name] = {
            "anchor": {"ref": members[0][0], "pad": members[0][1]},
            "member_count": len(members),
            "connected_item_count": len(connected_ids),
            "members": member_evidence,
            "passed": all(item["connected_to_group_anchor"] for item in member_evidence),
        }

    pad10 = find_numbered_pad(board, "U4", "10")
    pad10_items = connectivity.GetConnectedItems(pad10)
    pad10_ids = {item_uuid(item) for item in pad10_items}
    pad10_external_connections = sorted(pad10_ids - {item_uuid(pad10)})
    return {
        "passed": all_passed,
        "completion_authority": "KICAD_CONNECTED_ITEM_SETS_AFTER_SAVE_RELOAD_AND_ZONE_REFILL",
        "groups": groups,
        "u4_exposed_ground_pad10": {
            "connected_item_count": len(pad10_ids),
            "external_connected_item_uuids": pad10_external_connections,
            "status": "HOLD_STARVED_THERMAL"
            if not pad10_external_connections
            else "CONNECTED",
        },
    }


def add_track(board, net_name: str, layer: int, width_mm: float, start, end):
    net = board.FindNet(net_name)
    if net is None:
        raise RouteError(f"board does not contain required net {net_name}")
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(*start))
    track.SetEnd(pcbnew.VECTOR2I_MM(*end))
    track.SetWidth(pcbnew.FromMM(width_mm))
    track.SetLayer(layer)
    track.SetNet(net)
    board.Add(track)
    return track


def add_via(board, net_name: str, x_mm: float, y_mm: float, diameter_mm: float, drill_mm: float):
    net = board.FindNet(net_name)
    if net is None:
        raise RouteError(f"board does not contain required net {net_name}")
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
    via.SetWidth(pcbnew.FromMM(diameter_mm))
    via.SetDrill(pcbnew.FromMM(drill_mm))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    return via


def add_routes(board) -> list[object]:
    added = []
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    for net_name, layer, width_mm, points in ROUTES:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"route plan contains forbidden net {net_name}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(add_track(board, net_name, layer, width_mm, start, end))
    for net_name, x_mm, y_mm, diameter_mm, drill_mm in VIAS:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"via plan contains forbidden net {net_name}")
        added.append(add_via(board, net_name, x_mm, y_mm, diameter_mm, drill_mm))
    return added


def prepare_validation_context(temp_dir: Path, board_source: Path) -> tuple[Path, Path]:
    stem = "mf1750_wroom_b3_power_tf"
    board_path = temp_dir / f"{stem}.kicad_pcb"
    schematic_path = temp_dir / f"{stem}.kicad_sch"
    project_path = temp_dir / f"{stem}.kicad_pro"
    shutil.copy2(board_source, board_path)
    shutil.copy2(FORMAL_SCHEMATIC, schematic_path)
    shutil.copy2(FORMAL_PROJECT, project_path)
    for table_name in ("fp-lib-table", "sym-lib-table"):
        table = B3_DIR / table_name
        if table.is_file():
            shutil.copy2(table, temp_dir / table_name)
    # Project tables point at ${KIPRJMOD}; make the local custom libraries
    # self-contained so parity/DRC never depends on the staging filename.
    for library_name in (
        "b3_wroom_symbols.kicad_sym",
        "mf1750_local.kicad_sym",
    ):
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


def run_drc(kicad_cli: Path, board_path: Path, report_path: Path) -> dict[str, object]:
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
            "KiCad DRC failed: " + (completed.stderr.strip() or completed.stdout.strip())
        )
    data = json.loads(report_path.read_text(encoding="utf-8"))
    violations = data.get("violations", [])
    categories = collections.Counter(str(item.get("type")) for item in violations)
    return {
        "command": command,
        "returncode": completed.returncode,
        "kicad_version": data.get("kicad_version"),
        "violation_count": len(violations),
        "violation_categories": dict(sorted(categories.items())),
        "unconnected_count": len(data.get("unconnected_items", [])),
        "schematic_parity_count": len(data.get("schematic_parity", [])),
        "schematic_parity_sample": data.get("schematic_parity", [])[:10],
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "raw": data,
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
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    return {"side": side, "bytes": output.stat().st_size, "command": command}


def audit_candidate(board, source_state: dict[str, object], added_uuids: set[str]) -> dict[str, object]:
    footprints = {
        fp.GetReference(): footprint_signature(fp) for fp in board.GetFootprints()
    }
    source_footprints = source_state["footprints"]
    footprint_drift = [
        ref
        for ref in sorted(set(source_footprints) | set(footprints), key=natural_key)
        if source_footprints.get(ref) != footprints.get(ref)
    ]

    tracks = {item_uuid(item): item for item in board.GetTracks()}
    source_tracks = source_state["tracks"]
    missing_source_copper = sorted(set(source_tracks) - set(tracks))
    changed_source_copper = sorted(
        uuid
        for uuid in set(source_tracks) & set(tracks)
        if source_tracks[uuid] != track_signature(tracks[uuid])
    )
    new_ids = set(tracks) - set(source_tracks)
    unexpected_new_ids = sorted(new_ids - added_uuids)
    missing_added_ids = sorted(added_uuids - new_ids)
    new_items = [tracks[uuid] for uuid in sorted(new_ids)]
    forbidden_nets = sorted(
        {item.GetNetname() for item in new_items if item.GetNetname() not in ALLOWED_NETS}
    )
    outside_bbox = []
    x0, y0, x1, y1 = ROUTE_BBOX_MM
    for item in new_items:
        points = [point_mm(item.GetStart())]
        if not isinstance(item, pcbnew.PCB_VIA):
            points.append(point_mm(item.GetEnd()))
        if any(not (x0 <= x <= x1 and y0 <= y <= y1) for x, y in points):
            outside_bbox.append({"uuid": item_uuid(item), "points_mm": points})

    zones = {item_uuid(zone): zone_signature(zone) for zone in board.Zones()}
    drawings = {item_uuid(item): drawing_signature(item) for item in board.GetDrawings()}
    zone_drift = zones != source_state["zones"]
    drawing_drift = drawings != source_state["drawings"]
    new_net_counts = collections.Counter(item.GetNetname() for item in new_items)
    new_type_counts = collections.Counter(
        "via" if isinstance(item, pcbnew.PCB_VIA) else "track" for item in new_items
    )
    track_widths_by_net: dict[str, set[float]] = collections.defaultdict(set)
    via_geometries = set()
    for item in new_items:
        if isinstance(item, pcbnew.PCB_VIA):
            via_geometries.add(
                (
                    round(pcbnew.ToMM(item.GetWidth(item.TopLayer())), 6),
                    round(pcbnew.ToMM(item.GetDrillValue()), 6),
                )
            )
        else:
            track_widths_by_net[item.GetNetname()].add(
                round(pcbnew.ToMM(item.GetWidth()), 6)
            )
    checks = {
        "all_footprints_exact": not footprint_drift,
        "all_source_copper_exact": not missing_source_copper and not changed_source_copper,
        "only_planned_new_copper_ids": not unexpected_new_ids and not missing_added_ids,
        "new_copper_nets_allowlisted": not forbidden_nets,
        "new_copper_inside_u4_island_bbox": not outside_bbox,
        "zone_outlines_and_settings_exact": not zone_drift,
        "drawings_exact": not drawing_drift,
        "minimum_new_track_width_0p20mm": all(
            width >= 0.20 for widths in track_widths_by_net.values() for width in widths
        ),
        "all_new_vias_standard_0p60_0p30mm": via_geometries == {(0.6, 0.3)},
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "footprint_drift": footprint_drift,
        "source_copper_count": len(source_tracks),
        "new_copper_count": len(new_items),
        "new_copper_type_counts": dict(sorted(new_type_counts.items())),
        "new_copper_net_counts": dict(sorted(new_net_counts.items())),
        "track_widths_mm_by_net": {
            net: sorted(widths) for net, widths in sorted(track_widths_by_net.items())
        },
        "via_geometries_mm": [
            {"diameter": diameter, "drill": drill}
            for diameter, drill in sorted(via_geometries)
        ],
        "missing_source_copper": missing_source_copper,
        "changed_source_copper": changed_source_copper,
        "unexpected_new_ids": unexpected_new_ids,
        "missing_added_ids": missing_added_ids,
        "forbidden_nets": forbidden_nets,
        "outside_bbox": outside_bbox,
        "route_bbox_mm": ROUTE_BBOX_MM,
        "zone_drift": zone_drift,
        "drawing_drift": drawing_drift,
    }


def snapshot_source(board) -> dict[str, object]:
    return {
        "footprints": {
            fp.GetReference(): footprint_signature(fp) for fp in board.GetFootprints()
        },
        "tracks": {item_uuid(item): track_signature(item) for item in board.GetTracks()},
        "zones": {item_uuid(zone): zone_signature(zone) for zone in board.Zones()},
        "drawings": {
            item_uuid(item): drawing_signature(item) for item in board.GetDrawings()
        },
    }


def validate_drc_delta(source_drc: dict[str, object], candidate_drc: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source_drc["violation_categories"])
    candidate_categories = collections.Counter(candidate_drc["violation_categories"])
    forbidden = {
        name: {
            "source": int(source_categories.get(name, 0)),
            "candidate": int(candidate_categories.get(name, 0)),
        }
        for name in sorted(FORBIDDEN_NEW_DRC_TYPES)
    }
    checks = {
        "source_schematic_parity_zero": source_drc["schematic_parity_count"] == 0,
        "candidate_schematic_parity_zero": candidate_drc["schematic_parity_count"] == 0,
        "no_forbidden_source_drc": all(item["source"] == 0 for item in forbidden.values()),
        "no_forbidden_candidate_drc": all(item["candidate"] == 0 for item in forbidden.values()),
        "unconnected_count_reduced": candidate_drc["unconnected_count"] < source_drc["unconnected_count"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "forbidden_types": forbidden,
        "unconnected_delta": int(candidate_drc["unconnected_count"])
        - int(source_drc["unconnected_count"]),
        "candidate_forbidden_samples": [
            violation
            for violation in candidate_drc["raw"].get("violations", [])
            if violation.get("type") in FORBIDDEN_NEW_DRC_TYPES
        ][:10],
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help="explicit R4-derived source; requires --source-sha256",
    )
    parser.add_argument(
        "--source-sha256",
        help="expected SHA-256 for an explicit --source",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.resolve() if args.source else DEFAULT_SOURCE.resolve()
    expected_source_hash = (
        args.source_sha256.casefold()
        if args.source_sha256
        else DEFAULT_SOURCE_SHA256
    )
    report: dict[str, object]
    try:
        if pcbnew is None:
            raise RouteError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        pcbnew_version = str(pcbnew.GetBuildVersion())
        if pcbnew_version.split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew_version}")
        if args.source is not None and not args.source_sha256:
            raise RouteError("explicit --source requires --source-sha256")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_source_hash):
            raise RouteError("source SHA-256 must contain exactly 64 hex digits")
        if not source.is_file():
            raise RouteError(f"source PCB does not exist: {source}")
        if source == OUTPUT_BOARD.resolve():
            raise RouteError("source and fixed R5 U4 output must be different files")
        if source.parent.resolve() != STAGING.resolve():
            raise RouteError("source must be an explicit file inside the B3 staging directory")
        for required in (FORMAL_BOARD, FORMAL_SCHEMATIC, FORMAL_PROJECT):
            if not required.is_file():
                raise RouteError(f"required canonical context file is missing: {required}")
        locks = list(B3_DIR.glob("~*.lck")) + list(STAGING.glob("~*.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(map(str, locks)))
        source_hash_before = sha256_file(source)
        if source_hash_before.casefold() != expected_source_hash.casefold():
            raise RouteError(
                f"source hash mismatch: {source_hash_before} != {expected_source_hash}"
            )
        formal_hash_before = sha256_file(FORMAL_BOARD)
        schematic_hash_before = sha256_file(FORMAL_SCHEMATIC)
        project_hash_before = sha256_file(FORMAL_PROJECT)
        kicad_cli = find_kicad_cli()

        board = pcbnew.LoadBoard(str(source))
        if board is None:
            raise RouteError("pcbnew could not parse the selected source")
        pad_evidence = validate_pad_contract(board)
        source_state = snapshot_source(board)
        added = add_routes(board)
        added_uuids = {item_uuid(item) for item in added}
        if len(added_uuids) != len(added):
            raise RouteError("deterministic copper creation generated duplicate UUIDs")

        title = board.GetTitleBlock()
        title.SetTitle("MF1750 WROOM B3 R5 TPS63070 critical-loop route candidate")
        title.SetRevision("B3-WROOM-POWER-TF-R5-U4-ROUTED")
        title.SetComment(0, "TPS63070 ISLAND ONLY; PARTIAL ROUTING; NOT MANUFACTURING READY")

        STAGING.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mf1750-r5-u4-") as temp_name:
            temp_root = Path(temp_name)
            candidate = temp_root / "candidate.kicad_pcb"
            source_context_dir = temp_root / "source_context"
            candidate_context_dir = temp_root / "candidate_context"
            source_context_dir.mkdir()
            candidate_context_dir.mkdir()
            top_temp = temp_root / TOP_PREVIEW.name
            bottom_temp = temp_root / BOTTOM_PREVIEW.name
            staged_board = STAGING / (
                f".{OUTPUT_BOARD.stem}.{os.getpid()}.{secrets.token_hex(6)}.kicad_pcb"
            )

            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(str(candidate), board)
            reloaded = pcbnew.LoadBoard(str(candidate))
            if reloaded is None:
                raise RouteError("saved R5 U4 candidate does not reload")
            candidate_audit = audit_candidate(reloaded, source_state, added_uuids)
            if not candidate_audit["passed"]:
                raise RouteError("candidate preservation audit failed: " + json.dumps(candidate_audit))
            local_connectivity = validate_local_connectivity(reloaded)
            if not local_connectivity["passed"]:
                raise RouteError(
                    "local endpoint connectivity contract failed: "
                    + json.dumps(local_connectivity)
                )

            source_context_board, source_drc_path = prepare_validation_context(
                source_context_dir, source
            )
            candidate_context_board, candidate_drc_path = prepare_validation_context(
                candidate_context_dir, candidate
            )
            source_drc = run_drc(kicad_cli, source_context_board, source_drc_path)
            candidate_drc = run_drc(
                kicad_cli, candidate_context_board, candidate_drc_path
            )
            drc_delta = validate_drc_delta(source_drc, candidate_drc)
            if not drc_delta["passed"]:
                raise RouteError("DRC/parity delta gate failed: " + json.dumps(drc_delta))

            render_top = render(kicad_cli, candidate, top_temp, "top")
            render_bottom = render(kicad_cli, candidate, bottom_temp, "bottom")

            # Immutable inputs are rechecked immediately before the only
            # repository write (an atomic replacement of the fixed staging file).
            if sha256_file(source) != source_hash_before:
                raise RouteError("selected source changed during R5 U4 construction")
            if sha256_file(FORMAL_BOARD) != formal_hash_before:
                raise RouteError("formal B3 PCB changed during R5 U4 construction")
            if sha256_file(FORMAL_SCHEMATIC) != schematic_hash_before:
                raise RouteError("formal B3 schematic changed during R5 U4 construction")
            if sha256_file(FORMAL_PROJECT) != project_hash_before:
                raise RouteError("formal B3 project changed during R5 U4 construction")
            locks_before_commit = list(B3_DIR.glob("~*.lck")) + list(
                STAGING.glob("~*.lck")
            )
            if locks_before_commit:
                raise RouteError(
                    "KiCad lock appeared before staging commit: "
                    + ", ".join(map(str, locks_before_commit))
                )

            validated_hash = sha256_file(candidate)
            shutil.copy2(candidate, staged_board)
            if sha256_file(staged_board) != validated_hash:
                staged_board.unlink(missing_ok=True)
                raise RouteError("staging transfer changed validated PCB bytes")
            os.replace(staged_board, OUTPUT_BOARD)
            if sha256_file(OUTPUT_BOARD) != validated_hash:
                raise RouteError("atomic staging replacement changed PCB bytes")
            shutil.copy2(candidate_drc_path, DRC_JSON)
            os.replace(top_temp, TOP_PREVIEW)
            os.replace(bottom_temp, BOTTOM_PREVIEW)

            compact_source_drc = {key: value for key, value in source_drc.items() if key != "raw"}
            compact_candidate_drc = {
                key: value for key, value in candidate_drc.items() if key != "raw"
            }
            report = {
                "schema": 1,
                "tool": Path(__file__).name,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R5_U4_PARTIALLY_ROUTED_CANDIDATE",
                "overall_status": "HOLD",
                "operation_completed": True,
                "routing_checks_passed": True,
                "locally_verified": False,
                "inputs": {
                    "source": {
                        "path": str(source),
                        "expected_sha256": expected_source_hash,
                        "sha256": source_hash_before,
                    },
                    "formal_b3_board_read_only": {
                        "path": str(FORMAL_BOARD),
                        "sha256": formal_hash_before,
                    },
                    "schematic_read_only": {
                        "path": str(FORMAL_SCHEMATIC),
                        "sha256": schematic_hash_before,
                    },
                },
                "tools": {
                    "pcbnew": pcbnew_version,
                    "kicad_cli": candidate_drc["kicad_version"],
                },
                "output": {
                    "path": str(OUTPUT_BOARD),
                    "sha256": validated_hash,
                    "bytes": OUTPUT_BOARD.stat().st_size,
                },
                "scope": {
                    "island_refs": sorted(ISLAND_REFS, key=natural_key),
                    "allowed_nets": sorted(ALLOWED_NETS),
                    "route_bbox_mm": ROUTE_BBOX_MM,
                    "new_track_segments": sum(len(points) - 1 for _, _, _, points in ROUTES),
                    "new_vias": len(VIAS),
                    "pad_contract": pad_evidence,
                },
                "preservation_audit": candidate_audit,
                "local_connectivity": local_connectivity,
                "drc": {
                    "source": compact_source_drc,
                    "candidate": compact_candidate_drc,
                    "delta_gate": drc_delta,
                    "raw_candidate_report": str(DRC_JSON),
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
                "routed_scope": [
                    "U4-C46 VIN high-frequency loop",
                    "U4-C47 VOUT high-frequency loop",
                    "U4-L3 L1/L2 switch nodes",
                    "local C31-C33 input bulk bank",
                    "local C34-C37 output bulk bank",
                    "VAUX decoupling and FB divider with FB kept away from L1/L2",
                    "local PS_SYNC and PG pull-up connections",
                    "local ground escapes, including U4 exposed pad10, and ground-plane transition vias",
                ],
                "holds": [
                    "R5 U4 is a partial-route candidate; the complete board remains unrouted",
                    "VSYS_RAW upstream connection from the U4 input bank remains for the BQ/power-path route",
                    "SYS_3V3 downstream distribution beyond the U4 output bank remains for later routing",
                    "DCDC_EN remains unrouted at U4 pad14/R61/U3/TP15 because no compliant escape is proven with frozen R4 placement",
                    "DCDC_PG to TP16 remains unrouted outside the U4 island",
                    "the 0.20 mm local input-bank neck is not accepted for final current capacity until measured peak current is authoritative",
                    "final current capacity, thermal performance, stackup/SI, enclosure fit, and manufacturing readiness remain HOLD",
                ],
                "formal_b3_modified": False,
                "schematic_modified": False,
                "r3_modified": False,
                "r4_modified": False,
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
            "state": "HOLD_R5_U4_ROUTE_FAILED",
            "overall_status": "FAIL",
            "operation_completed": False,
            "routing_checks_passed": False,
            "locally_verified": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "fixed_output": str(OUTPUT_BOARD),
            "formal_b3_modified": False,
            "schematic_modified": False,
            "r3_modified": False,
            "r4_modified": False,
            "hardware_accessed": False,
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
