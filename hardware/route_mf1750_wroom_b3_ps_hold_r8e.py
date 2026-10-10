#!/usr/bin/env python3
"""Build a fail-closed, PS_HOLD-only R8e routing candidate from frozen R8d.

The fixed R8d board places U3.4 between two pre-existing 0.6/0.3 mm vias
while an 0.8 mm /VSYS_RAW trunk occupies In2.Cu immediately behind the pad.
With the frozen 0.20 mm clearance/track-width and standard through-via rules,
U3.4 has no legal escape unless existing copper is rerouted or an unapproved
HDI/via-in-pad process is introduced.  This builder therefore adds only the
safe R60.1-to-U1.38 portion of /PS_HOLD, verifies zero new DRC violations, and
returns HOLD because U3.4 remains intentionally unconnected.

No footprint, zone, rule, or source-copper item is edited.  The formal PCB is
never written.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
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

R7_UTILITY = HARDWARE / "route_mf1750_wroom_b3_epd_mcu_r7.py"
R7_UTILITY_SHA256 = "9f5add51e5e220bd4ddb02692ac6b2efb9039bdea090932c53b9ff71a3232a82"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb"
SOURCE_SHA256 = "9a0f1e309abe27cc8577404e2ef62a719ca7a39934553023c941bff5b5c62403"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_ps_hold_partial_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8e_ps_hold_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8e_ps_hold_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8e_ps_hold_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8e_ps_hold_board_verifier.json"
PREVIEW_DIR = STAGING / "r8e_ps_hold_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_ps_hold_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_ps_hold_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_ps_hold_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_ps_hold_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"

ROUTING_UUID_SEED = 1750851
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
DEFAULT_CLEARANCE_MM = 0.20
MIN_STANDARD_VIA_DIAMETER_MM = 0.50
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_COPPER = 1238
EXPECTED_CANDIDATE_COPPER = 1246
EXPECTED_SOURCE_UNCONNECTED = 123
EXPECTED_CANDIDATE_UNCONNECTED = 122
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
ALLOWED_NETS = frozenset({"/PS_HOLD"})

PAD_CONTRACT: dict[tuple[str, str], tuple[str, float, float]] = {
    ("U1", "38"): ("/PS_HOLD", 54.7200, 98.7500),
    ("U3", "4"): ("/PS_HOLD", 10.2000, 78.7500),
    ("R60", "1"): ("/PS_HOLD", 35.9750, 71.5000),
}

# Safe partial route only.  U3.4 is not touched; see escape_cage_audit().
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/PS_HOLD", "F.Cu", ((35.9750, 71.5000), (35.9750, 69.2000), (39.0000, 69.2000))),
    ("/PS_HOLD", "In2.Cu", ((39.0000, 69.2000), (47.0000, 69.2000), (47.0000, 92.2800), (54.7200, 100.0000))),
    ("/PS_HOLD", "F.Cu", ((54.7200, 100.0000), (54.7200, 98.7500))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/PS_HOLD", 39.0000, 69.2000),
    ("/PS_HOLD", 54.7200, 100.0000),
)


class RouteError(RuntimeError):
    """Fail-closed R8e route-builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r7_utility():
    if not R7_UTILITY.is_file() or sha256_file(R7_UTILITY) != R7_UTILITY_SHA256:
        raise RouteError(f"R7 utility missing or hash-mismatched: {R7_UTILITY}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8e_r7_utility", R7_UTILITY)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R7 utility import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.base.ALLOWED_NETS = ALLOWED_NETS
    return module


r7 = load_r7_utility()
base = r7.base


def point_mm(item) -> tuple[float, float]:
    point = item.GetPosition()
    return pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)


def find_via(board, net: str, x_mm: float, y_mm: float):
    for item in board.GetTracks():
        if not isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != net:
            continue
        x_actual, y_actual = point_mm(item)
        if abs(x_actual - x_mm) <= 0.000002 and abs(y_actual - y_mm) <= 0.000002:
            return item
    raise RouteError(f"expected via missing: {net}@({x_mm},{y_mm})")


def find_track(board, net: str, layer: str, start: tuple[float, float], end: tuple[float, float]):
    layer_id = base.layer_id(board, layer)
    wanted = {tuple(round(value, 6) for value in start), tuple(round(value, 6) for value in end)}
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != net or item.GetLayer() != layer_id:
            continue
        actual = {
            tuple(round(value, 6) for value in base.point_mm(item.GetStart())),
            tuple(round(value, 6) for value in base.point_mm(item.GetEnd())),
        }
        if actual == wanted:
            return item
    raise RouteError(f"expected track missing: {net}/{layer}@{start}->{end}")


def validate_scope(board) -> dict[str, object]:
    refs: set[str] = set()
    pad_evidence = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() in ALLOWED_NETS:
                refs.add(footprint.GetReference())
    if refs != {"R60", "U1", "U3"}:
        raise RouteError(f"PS_HOLD endpoint reference drift: {sorted(refs)}")
    for (reference, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = base.find_numbered_pad(board, reference, number)
        actual = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or any(
            abs(got - expected) > 0.000002
            for got, expected in zip(actual, (x_mm, y_mm), strict=True)
        ):
            raise RouteError(
                f"pad contract drift {reference}.{number}: {pad.GetNetname()}@{actual}, "
                f"expected {net}@{(x_mm, y_mm)}"
            )
        pad_evidence.append(
            {"reference": reference, "pad": number, "net": net, "position_mm": list(actual)}
        )
    return {
        "passed": True,
        "net": "/PS_HOLD",
        "endpoint_references": sorted(refs),
        "pad_contract": pad_evidence,
        "mechanical_dependency_references": [],
        "planned_connected_subset": ["R60.1", "U1.38"],
        "held_endpoint": "U3.4",
    }


def escape_cage_audit(board) -> dict[str, object]:
    upper_pad = base.find_numbered_pad(board, "U3", "3")
    target_pad = base.find_numbered_pad(board, "U3", "4")
    lower_pad = base.find_numbered_pad(board, "U3", "5")
    upper_via = find_via(board, "/STM_VREF", 9.0, 78.25)
    lower_via = find_via(board, "/STM_CSRD", 9.0, 79.25)
    upper_f_track = find_track(board, "/STM_VREF", "F.Cu", (10.2, 78.25), (9.0, 78.25))
    lower_f_track = find_track(board, "/STM_CSRD", "F.Cu", (10.2, 79.25), (9.0, 79.25))
    upper_continuation = find_track(board, "/STM_VREF", "B.Cu", (9.0, 78.25), (7.5, 78.25))
    lower_continuation = find_track(board, "/STM_CSRD", "In2.Cu", (9.0, 79.25), (8.0, 79.25))
    vsys_track = find_track(board, "/VSYS_RAW", "In2.Cu", (10.0, 75.6), (10.0, 83.0))

    neighbor_via_radius = pcbnew.ToMM(upper_via.GetWidth(pcbnew.F_Cu)) / 2.0
    proposed_min_via_radius = MIN_STANDARD_VIA_DIAMETER_MM / 2.0
    track_radius = SIGNAL_WIDTH_MM / 2.0
    neighbor_spacing = abs(point_mm(lower_via)[1] - point_mm(upper_via)[1])
    required_track_center_spacing = neighbor_via_radius + DEFAULT_CLEARANCE_MM + track_radius
    track_corridor_overlap = 2.0 * required_track_center_spacing - neighbor_spacing

    required_new_via_spacing = neighbor_via_radius + DEFAULT_CLEARANCE_MM + proposed_min_via_radius
    vertical_offset = abs(point_mm(target_pad)[1] - point_mm(upper_via)[1])
    min_rightward_x_offset = math.sqrt(
        max(0.0, required_new_via_spacing**2 - vertical_offset**2)
    )
    min_x_from_neighbor_vias = point_mm(upper_via)[0] + min_rightward_x_offset
    vsys_half_width = pcbnew.ToMM(vsys_track.GetWidth()) / 2.0
    max_x_to_clear_vsys = (
        10.0 - vsys_half_width - proposed_min_via_radius - DEFAULT_CLEARANCE_MM
    )

    checks = {
        "u3_neighbor_pad_contract": (
            upper_pad.GetNetname() == "/STM_VREF"
            and target_pad.GetNetname() == "/PS_HOLD"
            and lower_pad.GetNetname() == "/STM_CSRD"
            and base.point_mm(upper_pad.GetPosition()) == (10.2, 78.25)
            and base.point_mm(target_pad.GetPosition()) == (10.2, 78.75)
            and base.point_mm(lower_pad.GetPosition()) == (10.2, 79.25)
        ),
        "neighbor_vias_are_standard_0p60_0p30": all(
            (
                round(pcbnew.ToMM(via.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(via.GetDrillValue()), 6),
            )
            == (0.6, 0.3)
            for via in (upper_via, lower_via)
        ),
        "in2_vsys_trunk_is_0p8_mm": round(pcbnew.ToMM(vsys_track.GetWidth()), 6) == 0.8,
        "f_cu_track_center_corridor_closed": track_corridor_overlap > 0.0,
        "standard_through_via_x_intervals_disjoint": min_x_from_neighbor_vias > max_x_to_clear_vsys,
    }
    if not all(checks.values()):
        raise RouteError(f"U3.4 escape-cage evidence drift: {checks}")
    return {
        "passed": True,
        "classification": "HOLD_EXISTING_COPPER_TOPOLOGY_BLOCKS_STANDARD_ESCAPE",
        "checks": checks,
        "evidence": {
            "u3_pads": {
                "upper": {"pad": "3", "net": upper_pad.GetNetname(), "position_mm": list(base.point_mm(upper_pad.GetPosition()))},
                "target": {"pad": "4", "net": target_pad.GetNetname(), "position_mm": list(base.point_mm(target_pad.GetPosition()))},
                "lower": {"pad": "5", "net": lower_pad.GetNetname(), "position_mm": list(base.point_mm(lower_pad.GetPosition()))},
            },
            "neighbor_vias": [
                {"net": upper_via.GetNetname(), "position_mm": list(point_mm(upper_via)), "diameter_mm": 0.6, "drill_mm": 0.3},
                {"net": lower_via.GetNetname(), "position_mm": list(point_mm(lower_via)), "diameter_mm": 0.6, "drill_mm": 0.3},
            ],
            "in2_blocker": {
                "net": vsys_track.GetNetname(),
                "start_mm": list(base.point_mm(vsys_track.GetStart())),
                "end_mm": list(base.point_mm(vsys_track.GetEnd())),
                "width_mm": pcbnew.ToMM(vsys_track.GetWidth()),
            },
            "rules_mm": {
                "clearance": DEFAULT_CLEARANCE_MM,
                "minimum_track_width": SIGNAL_WIDTH_MM,
                "minimum_standard_via_diameter": MIN_STANDARD_VIA_DIAMETER_MM,
                "standard_via_drill": VIA_DRILL_MM,
            },
            "f_cu_track_center_corridor_overlap_mm": round(track_corridor_overlap, 6),
            "minimum_x_to_clear_neighbor_vias_mm": round(min_x_from_neighbor_vias, 6),
            "maximum_x_to_clear_in2_vsys_mm": round(max_x_to_clear_vsys, 6),
            "infeasible_interval_gap_mm": round(min_x_from_neighbor_vias - max_x_to_clear_vsys, 6),
        },
        "required_resolution": (
            "reroute one or both frozen U3.3/U3.5 escape vias/tracks, or approve and "
            "fabrication-bind an HDI/via-in-pad process; neither is authorized in R8e"
        ),
        "minimum_controlled_change_plan": {
            "status": "PROPOSED_NOT_EXECUTED_NOT_APPROVED",
            "existing_copper_delta_whitelist": [
                {"uuid": base.item_uuid(upper_via), "net": "/STM_VREF", "kind": "via"},
                {"uuid": base.item_uuid(lower_via), "net": "/STM_CSRD", "kind": "via"},
                {"uuid": base.item_uuid(upper_f_track), "net": "/STM_VREF", "kind": "F.Cu local escape"},
                {"uuid": base.item_uuid(lower_f_track), "net": "/STM_CSRD", "kind": "F.Cu local escape"},
                {"uuid": base.item_uuid(upper_continuation), "net": "/STM_VREF", "kind": "B.Cu local continuation"},
                {"uuid": base.item_uuid(lower_continuation), "net": "/STM_CSRD", "kind": "In2.Cu local continuation"},
            ],
            "probe_centers_mm": {
                "STM_VREF_via": [8.2, 77.9],
                "STM_CSRD_via": [8.2, 79.6],
                "PS_HOLD_via": [8.8, 78.75],
            },
            "route_intent": (
                "rebuild only the two neighboring local escapes/continuations, then take "
                "the PS_HOLD long leg on B.Cu; preserve B2, antenna keepout, and In1 GND"
            ),
            "mandatory_gates": [
                "all three 0.60/0.30 mm via center distances greater than 0.80 mm",
                "PS_HOLD via remains left of the In2 /VSYS_RAW x=10.0 mm trunk",
                "zero-new-DRC versus the 13-item R8d baseline",
                "all unrelated source-copper UUID/geometry exact",
                "schematic parity 0 and project verifier 13/13",
                "deterministic double build",
            ],
        },
    }


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net, layer, points in ROUTES:
        if net not in ALLOWED_NETS or layer == "In1.Cu":
            raise RouteError(f"route violates allowlist/layer contract: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end))
    for net, x_mm, y_mm in VIAS:
        if net not in ALLOWED_NETS:
            raise RouteError(f"via violates allowlist: {net}")
        added.append(base.add_via(board, net, x_mm, y_mm))
    return added


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


def envelope_audit(board, added_ids: set[str]) -> dict[str, object]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    findings: dict[str, list[str]] = {
        "non_allowlisted_net": [],
        "b2": [],
        "antenna": [],
        "in1": [],
        "bad_width": [],
        "bad_via": [],
    }
    for item_id in sorted(added_ids):
        item = by_id[item_id]
        if item.GetNetname() not in ALLOWED_NETS:
            findings["non_allowlisted_net"].append(item_id)
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            ) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna_hit = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    checks = {
        "new_copper_net_whitelist_ps_hold_only": not findings["non_allowlisted_net"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_wroom_antenna_keepout": not findings["antenna"],
        "no_signal_track_on_in1": not findings["in1"],
        "all_new_tracks_exactly_0p20_mm": not findings["bad_width"],
        "all_new_vias_exactly_0p60_0p30_mm": not findings["bad_via"],
    }
    return {"passed": all(checks.values()), "checks": checks, "findings": findings}


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not parse the fixed R8d source")
    scope = validate_scope(board)
    escape_cage = escape_cage_audit(board)
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(
            f"source copper-count drift: {len(before['tracks'])}, expected {EXPECTED_SOURCE_COPPER}"
        )
    added = add_routes(board)
    added_ids = {base.item_uuid(item) for item in added}
    if len(added_ids) != len(added):
        raise RouteError("duplicate deterministic copper UUID")
    if not pcbnew.SaveBoard(str(destination), board):
        raise RouteError(f"failed to save {destination}")
    return before, added_ids, scope, escape_cage


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def violation_fingerprints(raw: dict[str, object]) -> list[tuple[object, ...]]:
    fingerprints = []
    for violation in raw.get("violations", []):
        items = []
        for item in violation.get("items", []):
            position = item.get("pos", {})
            items.append(
                (
                    str(item.get("uuid", "")),
                    round(float(position.get("x", 0.0)), 6),
                    round(float(position.get("y", 0.0)), 6),
                )
            )
        fingerprints.append((str(violation.get("type", "")), tuple(sorted(items))))
    return sorted(fingerprints, key=repr)


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fingerprints = violation_fingerprints(source["raw"])
    candidate_fingerprints = violation_fingerprints(candidate["raw"])
    safety_checks = {
        "source_drc_exactly_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_drc_exactly_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_fingerprints_exact": source_fingerprints == candidate_fingerprints,
        "source_unconnected_exactly_123": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_122": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_1": source["unconnected_count"] - candidate["unconnected_count"] == 1,
        "source_ps_hold_unconnected_exactly_2": source_nets.get("/PS_HOLD", 0) == 2,
        "candidate_ps_hold_unconnected_exactly_1": candidate_nets.get("/PS_HOLD", 0) == 1,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "violation_categories_exact": source_categories == candidate_categories,
    }
    completion_checks = {
        "all_ps_hold_endpoints_connected": candidate_nets.get("/PS_HOLD", 0) == 0,
    }
    return {
        "safety_passed": all(safety_checks.values()),
        "routing_complete": all(completion_checks.values()),
        "safety_checks": safety_checks,
        "completion_checks": completion_checks,
        "source_categories": dict(sorted(source_categories.items())),
        "candidate_categories": dict(sorted(candidate_categories.items())),
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_fingerprints": source_fingerprints,
        "candidate_violation_fingerprints": candidate_fingerprints,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kicad-python",
        type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    protected_paths = {
        "formal_board": FORMAL_BOARD,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
        "root_readme": ROOT_README,
        "b3_readme": B3_README,
        "r8d_source_board": SOURCE_BOARD,
        "r7_utility": R7_UTILITY,
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
            raise RouteError("fixed R8d source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))

        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r8e-ps-hold-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, scope, escape_cage = build_candidate(first)
            before2, added_ids2, scope2, escape_cage2 = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and before == before2
                and added_ids == added_ids2
                and scope == scope2
                and escape_cage == escape_cage2
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            reloaded = pcbnew.LoadBoard(str(first))
            if reloaded is None:
                raise RouteError("saved candidate failed reload")
            preservation = base.audit_candidate(reloaded, before, added_ids)
            envelope = envelope_audit(reloaded, added_ids)
            preservation["r8e_route_envelope"] = envelope
            preservation["passed"] = preservation["passed"] and envelope["passed"]
            candidate_copper = len(list(reloaded.GetTracks()))
            if candidate_copper != EXPECTED_CANDIDATE_COPPER:
                raise RouteError(
                    f"candidate copper-count drift: {candidate_copper}, expected {EXPECTED_CANDIDATE_COPPER}"
                )
            if not preservation["passed"]:
                raise RouteError("source/envelope preservation audit failed")
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)

        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        gate = drc_gate(source_drc, candidate_drc)
        verifier = r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)

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
        renders = [
            base.render(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom"),
            base.export_svg(
                kicad_cli,
                OUTPUT_BOARD,
                FRONT_COPPER_SVG,
                "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts",
            ),
            base.export_svg(
                kicad_cli,
                OUTPUT_BOARD,
                BACK_COPPER_SVG,
                "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts",
                mirror=True,
            ),
        ]

        protected_after = {
            name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()
        }
        protected_unchanged = protected_before == protected_after
        safety_passed = (
            preservation["passed"]
            and gate["safety_passed"]
            and verifier["passed"]
            and protected_unchanged
        )
        routing_complete = safety_passed and gate["routing_complete"]
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "REVISION_STAGING_ONLY_ADDITIVE_SINGLE_NET_PS_HOLD",
            "state": "R8E_PS_HOLD_ROUTED_CANDIDATE" if routing_complete else "R8E_PS_HOLD_PARTIAL_ROUTE_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if routing_complete else "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "locally_verified": False,
            "safety_checks_passed": safety_passed,
            "routing_complete": routing_complete,
            "inputs": {
                "source": {"path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256},
                "r7_utility": {"path": str(R7_UTILITY), "sha256": R7_UTILITY_SHA256},
            },
            "output": {
                "path": str(OUTPUT_BOARD),
                "bytes": OUTPUT_BOARD.stat().st_size,
                "sha256": sha256_file(OUTPUT_BOARD),
            },
            "kicad": {"version": str(pcbnew.GetBuildVersion()), "cli": str(kicad_cli)},
            "determinism": {
                "double_build_byte_identical": deterministic,
                "first_sha256": build_sha,
                "second_sha256": build_sha,
            },
            "protected_sources": {
                "unchanged": protected_unchanged,
                "before": protected_before,
                "after": protected_after,
            },
            "scope_audit": scope,
            "u3_escape_cage": escape_cage,
            "routing_contract": {
                "allowed_nets": sorted(ALLOWED_NETS),
                "new_copper_count": EXPECTED_CANDIDATE_COPPER - EXPECTED_SOURCE_COPPER,
                "layers": ["F.Cu", "In2.Cu"],
                "in1_signal_routing": "FORBIDDEN",
                "signal_width_mm": SIGNAL_WIDTH_MM,
                "via_diameter_mm": VIA_DIAMETER_MM,
                "via_drill_mm": VIA_DRILL_MM,
                "b2_boundary_y_mm": B2_BOTTOM_MM,
                "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
                "expected_drc": {"source": 13, "candidate": 13, "new": 0},
                "expected_unconnected": {"source": 123, "candidate": 122, "reduction": 1},
            },
            "source_preservation_audit": preservation,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": ["/PS_HOLD"] if routing_complete else [],
            "safe_partial_scope": ["/PS_HOLD:R60.1<->U1.38"] if safety_passed else [],
            "holds": [
                {
                    "scope": "/PS_HOLD:U3.4",
                    "reason": escape_cage["required_resolution"],
                },
                {
                    "scope": "WHOLE_BOARD",
                    "reason": f"{candidate_drc['unconnected_count']} unrelated/held items remain; not manufacturing-ready",
                },
            ],
            "artifacts": {
                "source_drc_json": str(SOURCE_DRC_JSON),
                "candidate_drc_json": str(CANDIDATE_DRC_JSON),
                "board_verifier_json": str(BOARD_VERIFIER_JSON),
                "top_preview": str(TOP_PREVIEW),
                "bottom_preview": str(BOTTOM_PREVIEW),
                "front_copper_svg": str(FRONT_COPPER_SVG),
                "back_copper_svg": str(BACK_COPPER_SVG),
                "render_export": renders,
            },
        }
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "state": report["state"],
                    "safety_checks_passed": safety_passed,
                    "routing_complete": routing_complete,
                    "output": report["output"],
                    "drc": {
                        "source_violations": source_drc["violation_count"],
                        "candidate_violations": candidate_drc["violation_count"],
                        "source_unconnected": source_drc["unconnected_count"],
                        "candidate_unconnected": candidate_drc["unconnected_count"],
                        "safety_gate_passed": gate["safety_passed"],
                    },
                    "board_verifier": verifier["summary"],
                    "report": str(REPORT_JSON),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if routing_complete else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "REVISION_STAGING_ONLY_ADDITIVE_SINGLE_NET_PS_HOLD",
            "state": "R8E_PS_HOLD_ROUTE_FAILED",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "locally_verified": False,
            "safety_checks_passed": False,
            "routing_complete": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "source": str(SOURCE_BOARD),
            "protected_sources_before": protected_before,
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
