#!/usr/bin/env python3
"""Build a staging-only conflict-remediated control/service routing candidate.

Operating mode: REVISION.  The sole geometry source is the SHA-bound R13
button-conflict-remediated staging PCB.  This builder adds copper only for
/MCU_EN, /UART0_RX, /UART0_TX and /JTAG_GPIO39..42.  It never changes source
copper, footprints, zones, J6, the inherited B2 EPD region, the WROOM antenna
keepout, or In1.Cu.

The R16 pure-additive merge proved each independent branch but exposed two
cross-branch interactions.  This recipe retains the independently verified
topology except for two controlled changes:

* /MCU_EN uses a short F.Cu bridge centred at y=79.0 mm and transfers to
  In2.Cu at (38.2, 78.0), clearing both fixed /USER_KEY_1_N copper and the
  /MCU_BUSY_N through via at (30.0, 78.0).
* /UART0_RX remains on F.Cu from the WROOM pad to TP29, avoiding the In2.Cu
  JTAG fanout entirely while keeping an uninterrupted In1.Cu reference plane.

Any new DRC item, source mutation, connectivity drift, UUID collision, or
non-deterministic build is a fail-closed HOLD.  This script does not promote
the formal PCB and does not access hardware, serial/COM, or the network.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

UTILITY = HARDWARE / "route_mf1750_wroom_b3_jtag_bundle_r15.py"
UTILITY_SHA256 = "2fa2cc6082275ab0362546ce1f525b755aff02d6739cc9f944a65b9527ec6a78"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated.kicad_pcb"
SOURCE_SHA256 = "4cccd877a42f0e787af73183fa70548f64ac2bb00d7461cede542bc1f840d19a"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated.kicad_pcb"
REPORT_JSON = STAGING / "r17_r13_control_service_conflict_remediated_report.json"
SOURCE_DRC_JSON = STAGING / "r17_r13_control_service_conflict_remediated_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r17_r13_control_service_conflict_remediated_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r17_r13_control_service_conflict_remediated_board_verifier.json"
PREVIEW_DIR = STAGING / "r17_r13_control_service_conflict_remediated_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated_bottom.png"
ISO_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated_iso.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r17_r13_control_service_conflict_remediated_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
UUID_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"

ROUTING_UUID_SEED = 1750961
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 66.0, 79.75, 114.0)

ALLOWED_NETS = frozenset(
    {
        "/MCU_EN",
        "/UART0_RX",
        "/UART0_TX",
        "/JTAG_GPIO39",
        "/JTAG_GPIO40",
        "/JTAG_GPIO41",
        "/JTAG_GPIO42",
    }
)
EXPECTED_SOURCE_COPPER = 1364
EXPECTED_ADDED_TRACKS = 76
EXPECTED_ADDED_VIAS = 23
EXPECTED_CANDIDATE_COPPER = 1463
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_OPEN = 106
EXPECTED_CANDIDATE_OPEN = 95

PAD_CONTRACT = (
    ("C48", "1", "/MCU_EN", 36.0250, 74.0000),
    ("R27", "2", "/MCU_EN", 36.8250, 76.5000),
    ("SW5", "1", "/MCU_EN", 1.3500, 94.7000),
    ("SW5", "1", "/MCU_EN", 1.3500, 98.3000),
    ("U1", "3", "/MCU_EN", 54.7200, 81.2500),
    ("U3", "10", "/MCU_EN", 11.8000, 78.2500),
    ("U1", "36", "/UART0_RX", 52.1800, 98.7500),
    ("TP29", "1", "/UART0_RX", 45.0000, 123.0000),
    ("U1", "37", "/UART0_TX", 53.4500, 98.7500),
    ("TP28", "1", "/UART0_TX", 61.0000, 120.0000),
    ("U1", "32", "/JTAG_GPIO39", 47.1000, 98.7500),
    ("TP30", "1", "/JTAG_GPIO39", 49.0000, 123.0000),
    ("U1", "33", "/JTAG_GPIO40", 48.3700, 98.7500),
    ("TP31", "1", "/JTAG_GPIO40", 53.0000, 123.0000),
    ("U1", "34", "/JTAG_GPIO41", 49.6400, 98.7500),
    ("TP32", "1", "/JTAG_GPIO41", 57.0000, 123.0000),
    ("U1", "35", "/JTAG_GPIO42", 50.9100, 98.7500),
    ("TP33", "1", "/JTAG_GPIO42", 61.0000, 123.0000),
)

ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    # MCU_EN: left switch weave and service/pull-up endpoints.
    (
        "/MCU_EN",
        "F.Cu",
        (
            (1.3500, 94.7000), (1.3500, 95.4000), (2.0000, 96.0500),
            (2.0000, 96.9500), (1.3500, 97.6000), (1.3500, 98.3000),
            (1.3500, 99.0000), (1.3500, 100.2000), (4.0000, 100.2000),
        ),
    ),
    (
        "/MCU_EN",
        "B.Cu",
        (
            (4.0000, 100.2000), (4.0000, 95.2000), (3.0000, 94.7000),
            (3.0000, 93.4000), (4.5000, 92.8000), (4.5000, 83.5000),
            (12.6000, 83.5000), (12.6000, 84.2000),
        ),
    ),
    ("/MCU_EN", "In2.Cu", ((12.6000, 84.2000), (12.6000, 85.0000), (18.2000, 85.0000), (18.2000, 84.2000))),
    ("/MCU_EN", "B.Cu", ((18.2000, 84.2000), (18.7000, 83.5000), (18.7000, 78.3000), (16.4000, 78.3000))),
    (
        "/MCU_EN",
        "F.Cu",
        ((11.8000, 78.2500), (12.1500, 78.2500), (12.4500, 78.3500), (13.3000, 78.3500), (13.8000, 77.9000), (15.3000, 77.9000), (16.4000, 78.3000)),
    ),
    ("/MCU_EN", "B.Cu", ((16.4000, 78.3000), (22.0000, 78.1000))),
    ("/MCU_EN", "F.Cu", ((22.0000, 78.1000), (22.5000, 78.5000), (24.1000, 78.5000), (24.3000, 78.1000))),
    # R16 conflict remediation: bridge above the MCU_BUSY_N via on F.Cu and
    # transfer at x=38.2, clear of fixed USER_KEY_1_N and In2 verticals.
    ("/MCU_EN", "F.Cu", ((24.3000, 78.1000), (25.3000, 79.0000), (31.5000, 79.0000), (38.2000, 78.0000))),
    (
        "/MCU_EN",
        "F.Cu",
        ((36.0250, 74.0000), (36.0250, 75.2000), (36.8250, 76.0000), (36.8250, 76.5000), (37.5000, 77.2000), (38.2000, 78.0000)),
    ),
    ("/MCU_EN", "In2.Cu", ((38.2000, 78.0000), (41.0000, 78.0000), (42.0000, 76.8000), (54.7500, 76.1000))),
    ("/MCU_EN", "F.Cu", ((54.7500, 76.1000), (54.9500, 76.7000), (54.9500, 80.1000), (54.7200, 80.5000), (54.7200, 81.2500))),

    # UART0_RX: one-layer route clears all four JTAG In2 fanouts.
    ("/UART0_RX", "F.Cu", ((52.1800, 98.7500), (52.1800, 118.0000), (46.5000, 118.0000), (46.5000, 123.0000), (45.0000, 123.0000))),
    # UART0_TX retains its independently verified path.
    ("/UART0_TX", "F.Cu", ((53.4500, 98.7500), (53.4500, 101.2000))),
    ("/UART0_TX", "B.Cu", ((53.4500, 101.2000), (53.4500, 111.5000))),
    ("/UART0_TX", "In2.Cu", ((53.4500, 111.5000), (53.4500, 116.0000), (59.0000, 116.0000))),
    ("/UART0_TX", "B.Cu", ((59.0000, 116.0000), (61.0000, 118.5000))),
    ("/UART0_TX", "F.Cu", ((61.0000, 118.5000), (61.0000, 120.0000))),

    # JTAG bundle retains the independently verified ordered fanout.
    ("/JTAG_GPIO39", "F.Cu", ((47.1000, 98.7500), (47.1000, 100.4000))),
    ("/JTAG_GPIO39", "B.Cu", ((47.1000, 100.4000), (47.1000, 105.5000))),
    ("/JTAG_GPIO39", "In2.Cu", ((47.1000, 105.5000), (47.1000, 116.0000), (48.2000, 121.5000))),
    ("/JTAG_GPIO39", "F.Cu", ((48.2000, 121.5000), (49.0000, 123.0000))),
    ("/JTAG_GPIO40", "F.Cu", ((48.3700, 98.7500), (48.3700, 100.4000))),
    ("/JTAG_GPIO40", "B.Cu", ((48.3700, 100.4000), (48.3700, 105.5000))),
    ("/JTAG_GPIO40", "In2.Cu", ((48.3700, 105.5000), (48.3700, 116.0000), (52.2000, 121.5000))),
    ("/JTAG_GPIO40", "F.Cu", ((52.2000, 121.5000), (53.0000, 123.0000))),
    ("/JTAG_GPIO41", "F.Cu", ((49.6400, 98.7500), (49.6400, 100.4000))),
    ("/JTAG_GPIO41", "B.Cu", ((49.6400, 100.4000), (49.6400, 105.5000))),
    ("/JTAG_GPIO41", "In2.Cu", ((49.6400, 105.5000), (49.6400, 116.0000), (56.2000, 121.5000))),
    ("/JTAG_GPIO41", "F.Cu", ((56.2000, 121.5000), (57.0000, 123.0000))),
    ("/JTAG_GPIO42", "F.Cu", ((50.9100, 98.7500), (50.9100, 100.4000))),
    ("/JTAG_GPIO42", "B.Cu", ((50.9100, 100.4000), (50.9100, 105.5000))),
    ("/JTAG_GPIO42", "In2.Cu", ((50.9100, 105.5000), (50.9100, 116.0000), (60.2000, 121.5000))),
    ("/JTAG_GPIO42", "F.Cu", ((60.2000, 121.5000), (61.0000, 123.0000))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/MCU_EN", 4.0000, 100.2000),
    ("/MCU_EN", 12.6000, 84.2000),
    ("/MCU_EN", 18.2000, 84.2000),
    ("/MCU_EN", 16.4000, 78.3000),
    ("/MCU_EN", 22.0000, 78.1000),
    ("/MCU_EN", 38.2000, 78.0000),
    ("/MCU_EN", 54.7500, 76.1000),
    ("/UART0_TX", 53.4500, 101.2000),
    ("/UART0_TX", 53.4500, 111.5000),
    ("/UART0_TX", 59.0000, 116.0000),
    ("/UART0_TX", 61.0000, 118.5000),
    ("/JTAG_GPIO39", 47.1000, 100.4000),
    ("/JTAG_GPIO39", 47.1000, 105.5000),
    ("/JTAG_GPIO39", 48.2000, 121.5000),
    ("/JTAG_GPIO40", 48.3700, 100.4000),
    ("/JTAG_GPIO40", 48.3700, 105.5000),
    ("/JTAG_GPIO40", 52.2000, 121.5000),
    ("/JTAG_GPIO41", 49.6400, 100.4000),
    ("/JTAG_GPIO41", 49.6400, 105.5000),
    ("/JTAG_GPIO41", 56.2000, 121.5000),
    ("/JTAG_GPIO42", 50.9100, 100.4000),
    ("/JTAG_GPIO42", 50.9100, 105.5000),
    ("/JTAG_GPIO42", 60.2000, 121.5000),
)

EXPECTED_NEW_NET_COUNTS = {
    "/MCU_EN": 53,
    "/UART0_RX": 4,
    "/UART0_TX": 10,
    "/JTAG_GPIO39": 8,
    "/JTAG_GPIO40": 8,
    "/JTAG_GPIO41": 8,
    "/JTAG_GPIO42": 8,
}


class RouteError(RuntimeError):
    """Fail-closed control/service remediation error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_utility():
    if not UTILITY.is_file() or sha256_file(UTILITY) != UTILITY_SHA256:
        raise RouteError("JTAG utility missing or SHA-256 mismatched")
    spec = importlib.util.spec_from_file_location("_mf1750_r17_control_utility", UTILITY)
    if spec is None or spec.loader is None:
        raise RouteError("could not import JTAG routing utility")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


utility = load_utility()
engine = utility.engine
pcbnew = utility.pcbnew
base = utility.base


def point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x_value, y_value = point
    x0, y0, x1, y1 = rect
    return x0 <= x_value <= x1 and y0 <= y_value <= y1


def segment_hits_rect(start, end, rect) -> bool:
    x0, y0, x1, y1 = rect
    xa, ya = start
    xb, yb = end
    dx, dy = xb - xa, yb - ya
    lo, hi = 0.0, 1.0
    for p_value, q_value in zip(
        (-dx, dx, -dy, dy),
        (xa - x0, x1 - xa, ya - y0, y1 - ya),
        strict=True,
    ):
        if abs(p_value) < 1e-12:
            if q_value < 0:
                return False
            continue
        ratio = q_value / p_value
        if p_value < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def seed_registry_audit() -> dict[str, object]:
    raw = json.loads(UUID_REGISTRY.read_text(encoding="utf-8"))
    matches = [
        item for item in raw.get("assignments", [])
        if int(item.get("seed_decimal", -1)) == ROUTING_UUID_SEED
    ]
    checks = {
        "one_seed_assignment": len(matches) == 1,
        "owner_exact": len(matches) == 1 and matches[0].get("owner") == Path(__file__).name,
        "status_reserved_or_occupied": len(matches) == 1 and matches[0].get("status") in {"reserved_for_candidate", "occupied"},
    }
    return {"passed": all(checks.values()), "checks": checks, "matches": matches}


def validate_source(board, before) -> dict[str, object]:
    pads = []
    for reference, number, net, x_mm, y_mm in PAD_CONTRACT:
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise RouteError(f"missing footprint {reference}")
        matches = [
            pad for pad in footprint.Pads()
            if pad.GetNumber() == number and base.point_mm(pad.GetPosition()) == (x_mm, y_mm)
        ]
        if len(matches) != 1 or matches[0].GetNetname() != net:
            raise RouteError(f"pad contract drift: {reference}.{number}@{(x_mm, y_mm)}")
        pads.append({"reference": reference, "pad": number, "net": net, "position_mm": [x_mm, y_mm]})
    source_counts = collections.Counter(signature[1] for signature in before["tracks"].values())
    registry = seed_registry_audit()
    checks = {
        "source_copper_count_1364": len(before["tracks"]) == EXPECTED_SOURCE_COPPER,
        "source_copper_uuid_unique": before["copper_uuid_audit"]["passed"] is True,
        "source_has_no_target_copper": all(source_counts.get(net, 0) == 0 for net in ALLOWED_NETS),
        "pad_contract_exact_18": len(pads) == len(PAD_CONTRACT),
        "seed_registry_assignment_exact": registry["passed"],
    }
    if not all(checks.values()):
        raise RouteError("source contract failed: " + json.dumps(checks, sort_keys=True))
    return {"passed": True, "checks": checks, "pads": pads, "seed_registry": registry}


def add_routes(board) -> set[str]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added_ids: list[str] = []
    for net_name, layer, points in ROUTES:
        if net_name not in ALLOWED_NETS or layer == "In1.Cu":
            raise RouteError(f"forbidden route recipe: {net_name}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            item = base.add_track(board, net_name, layer, SIGNAL_WIDTH_MM, start, end)
            added_ids.append(base.item_uuid(item))
    for net_name, x_mm, y_mm in VIAS:
        if net_name not in ALLOWED_NETS:
            raise RouteError(f"forbidden via net {net_name}")
        item = base.add_via(board, net_name, x_mm, y_mm)
        added_ids.append(base.item_uuid(item))
    if len(set(added_ids)) != len(added_ids):
        raise RouteError("new deterministic copper UUID collision")
    return set(added_ids)


def preservation_and_envelope_audit(candidate, before, added_ids) -> dict[str, object]:
    after = base.source_state(candidate)
    source_ids = set(before["tracks"])
    candidate_ids = set(after["tracks"])
    extra_ids = candidate_ids - source_ids
    missing_source = sorted(source_ids - candidate_ids)
    changed_source = sorted(
        item_id for item_id in source_ids & candidate_ids
        if before["tracks"][item_id] != after["tracks"][item_id]
    )
    unexpected_extra = sorted(extra_ids - added_ids)
    missing_added = sorted(added_ids - extra_ids)
    objects = {base.item_uuid(item): item for item in candidate.GetTracks()}
    findings = {"bad_net": [], "bad_width": [], "bad_via": [], "b2": [], "antenna": [], "in1": []}
    for item_id in sorted(extra_ids):
        item = objects[item_id]
        if item.GetNetname() not in ALLOWED_NETS:
            findings["bad_net"].append(item_id)
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            actual = (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            )
            if actual != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna_hit = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(candidate, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    new_counts = collections.Counter(after["tracks"][item_id][1] for item_id in extra_ids)
    added_track_count = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    added_via_count = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids)
    checks = {
        "all_source_copper_uuid_geometry_exact": not missing_source and not changed_source,
        "only_deterministic_added_ids": not unexpected_extra and not missing_added,
        "new_uuid_intersection_with_source_zero": not (added_ids & source_ids),
        "candidate_copper_uuid_unique": after["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_count_1463": len(after["tracks"]) == EXPECTED_CANDIDATE_COPPER,
        "added_track_count_76": added_track_count == EXPECTED_ADDED_TRACKS,
        "added_via_count_23": added_via_count == EXPECTED_ADDED_VIAS,
        "new_copper_exact_target_counts": dict(sorted(new_counts.items())) == dict(sorted(EXPECTED_NEW_NET_COUNTS.items())),
        "footprints_exact": before["footprints"] == after["footprints"],
        "zones_exact": before["zones"] == after["zones"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_antenna_keepout": not findings["antenna"],
        "no_new_signal_track_on_in1": not findings["in1"],
        "all_new_tracks_0p20_mm": not findings["bad_width"],
        "all_new_vias_0p60_0p30_mm": not findings["bad_via"],
        "no_bad_new_net": not findings["bad_net"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_copper_count": len(before["tracks"]),
        "candidate_copper_count": len(after["tracks"]),
        "added_ids": sorted(extra_ids),
        "removed_ids": missing_source,
        "changed_source_ids": changed_source,
        "unexpected_extra": unexpected_extra,
        "missing_added": missing_added,
        "new_net_counts": dict(sorted(new_counts.items())),
        "envelope_findings": findings,
    }


def unconnected_by_net(raw) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def violation_identity(raw) -> list[tuple[str, tuple[str, ...]]]:
    return sorted(
        (
            str(violation.get("type", "")),
            tuple(sorted(str(item.get("uuid", "")) for item in violation.get("items", []))),
        )
        for violation in raw.get("violations", [])
    )


def drc_gate(source, candidate) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    target_source = {net: source_nets.get(net, 0) for net in sorted(ALLOWED_NETS)}
    target_candidate = {net: candidate_nets.get(net, 0) for net in sorted(ALLOWED_NETS)}
    checks = {
        "source_violation_count_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_violation_count_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_identity_exact": violation_identity(source["raw"]) == violation_identity(candidate["raw"]),
        "source_open_106": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_95": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_11": source["unconnected_count"] - candidate["unconnected_count"] == 11,
        "source_target_open_vector_exact": target_source == {
            "/JTAG_GPIO39": 1, "/JTAG_GPIO40": 1, "/JTAG_GPIO41": 1, "/JTAG_GPIO42": 1,
            "/MCU_EN": 5, "/UART0_RX": 1, "/UART0_TX": 1,
        },
        "candidate_all_target_open_zero": all(value == 0 for value in target_candidate.values()),
        "inherited_control_nets_remain_zero": all(
            candidate_nets.get(net, 0) == 0
            for net in ("/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/PWR_BUTTON_N", "/USER_KEY_1_N", "/USER_KEY_2_N")
        ),
        "all_other_net_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "target_source": target_source,
        "target_candidate": target_candidate,
        "other_net_drift": other_drift,
        "source_violation_identity": violation_identity(source["raw"]),
        "candidate_violation_identity": violation_identity(candidate["raw"]),
    }


def protected_hashes() -> dict[str, str | None]:
    paths = (SOURCE_BOARD, UTILITY, FORMAL_BOARD, FORMAL_SCHEMATIC, FORMAL_PROJECT)
    return {str(path.resolve()): sha256_file(path) if path.is_file() else None for path in paths}


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r17-control-iso-") as name:
        temporary = Path(name)
        outputs = [temporary / "iso1.png", temporary / "iso2.png"]
        hashes = []
        commands = []
        for output in outputs:
            command = [
                str(kicad_cli), "pcb", "render", "--side", "top", "--background", "opaque",
                "--quality", "high", "--width", "1800", "--height", "1600", "--perspective",
                "--floor", "--rotate", "315,0,45", "--output", str(output), str(OUTPUT_BOARD),
            ]
            completed = subprocess.run(
                command, cwd=ROOT, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise RouteError("isometric render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
            hashes.append(sha256_file(output))
            commands.append(command)
        os.replace(outputs[0], ISO_PREVIEW)
    return {
        "path": str(ISO_PREVIEW),
        "bytes": ISO_PREVIEW.stat().st_size,
        "sha256": sha256_file(ISO_PREVIEW),
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def conflict_evidence(raw: dict[str, object]) -> list[dict[str, object]]:
    inherited = {"drill_out_of_range", "track_dangling"}
    evidence = []
    for violation in raw.get("violations", []):
        if str(violation.get("type", "")) in inherited:
            continue
        evidence.append(
            {
                "type": violation.get("type"),
                "description": violation.get("description"),
                "items": [
                    {
                        "uuid": item.get("uuid"),
                        "description": item.get("description"),
                        "position": item.get("pos"),
                    }
                    for item in violation.get("items", [])
                ],
            }
        )
    return evidence


def configure_engine() -> None:
    base.ALLOWED_NETS = ALLOWED_NETS
    engine.SOURCE_BOARD = SOURCE_BOARD
    engine.SOURCE_SHA256 = SOURCE_SHA256
    engine.OUTPUT_BOARD = OUTPUT_BOARD
    engine.REPORT_JSON = REPORT_JSON
    engine.SOURCE_DRC_JSON = SOURCE_DRC_JSON
    engine.CANDIDATE_DRC_JSON = CANDIDATE_DRC_JSON
    engine.BOARD_VERIFIER_JSON = BOARD_VERIFIER_JSON
    engine.PREVIEW_DIR = PREVIEW_DIR
    engine.TOP_PREVIEW = TOP_PREVIEW
    engine.BOTTOM_PREVIEW = BOTTOM_PREVIEW
    engine.FRONT_COPPER_SVG = FRONT_COPPER_SVG
    engine.BACK_COPPER_SVG = BACK_COPPER_SVG
    engine.ROUTING_UUID_SEED = ROUTING_UUID_SEED
    engine.ALLOWED_NET = "/CONTROL_SERVICE_REMEDIATION_WRAPPER"
    engine.ALLOWED_NETS = ALLOWED_NETS
    engine.ROUTES = ROUTES
    engine.VIAS = VIAS
    engine.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    engine.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    engine.EXPECTED_ADDED_TRACKS = EXPECTED_ADDED_TRACKS
    engine.EXPECTED_ADDED_VIAS = EXPECTED_ADDED_VIAS
    engine.EXPECTED_SOURCE_DRC = EXPECTED_SOURCE_DRC
    engine.EXPECTED_CANDIDATE_DRC = EXPECTED_CANDIDATE_DRC
    engine.EXPECTED_SOURCE_OPEN = EXPECTED_SOURCE_OPEN
    engine.EXPECTED_CANDIDATE_OPEN = EXPECTED_CANDIDATE_OPEN
    engine.PAD_CONTRACT = PAD_CONTRACT
    engine.validate_source = validate_source
    engine.add_routes = add_routes
    engine.preservation_and_envelope_audit = preservation_and_envelope_audit
    engine.drc_gate = drc_gate
    engine.protected_hashes = protected_hashes


def rewrite_report(exit_code: int) -> None:
    if not REPORT_JSON.is_file():
        return
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    passed = report.get("routing_checks_passed") is True and exit_code == 0
    report["operating_mode"] = "REVISION"
    report["mode"] = "STAGING_ONLY_CONTROL_SERVICE_CONFLICT_REMEDIATION"
    report["revision"] = "R17_R13_CONTROL_SERVICE_CONFLICT_REMEDIATED_STAGING"
    report["state"] = (
        "R17_R13_CONTROL_SERVICE_CONFLICT_REMEDIATED_CANDIDATE"
        if passed else "R17_R13_CONTROL_SERVICE_CONFLICT_REMEDIATION_HOLD"
    )
    report["overall_status"] = "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD"
    report["locally_verified"] = False
    report["source"] = {"role": "sole_editable_PCB_geometry_source", "path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256}
    report["builder"] = {
        "path": str(Path(__file__).resolve()),
        "sha256": sha256_file(Path(__file__).resolve()),
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "utility": {"path": str(UTILITY), "sha256": UTILITY_SHA256},
    }
    report["completed_scope"] = sorted(ALLOWED_NETS) if passed else []
    report["inherited_completed_scope"] = [
        "/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/PWR_BUTTON_N", "/USER_KEY_1_N", "/USER_KEY_2_N"
    ] if passed else []
    if OUTPUT_BOARD.is_file() and "output" in report:
        report["output"] = {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)}
    report["holds"] = [{"scope": "WHOLE_BOARD", "reason": "95 unrelated/held unconnected items remain; not manufacturing-ready"}]
    if CANDIDATE_DRC_JSON.is_file():
        raw = json.loads(CANDIDATE_DRC_JSON.read_text(encoding="utf-8"))
        report["new_conflict_evidence"] = conflict_evidence(raw)
    if passed:
        report.setdefault("artifacts", {})["isometric_preview"] = render_isometric(base.find_kicad_cli())
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise RouteError("sole source PCB missing or SHA-256 mismatched")
    configure_engine()
    exit_code = engine.main(argv)
    rewrite_report(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
