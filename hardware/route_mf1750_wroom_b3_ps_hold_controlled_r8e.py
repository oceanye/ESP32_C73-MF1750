#!/usr/bin/env python3
"""Controlled six-item U3 escape reroute plus complete /PS_HOLD routing.

The sole geometry source is the hash-bound R8d edge/DCDC_EN candidate.  The
only existing copper that may be removed or changed is the six UUIDs bound in
CONTROLLED_OLD_COPPER.  Replacement copper is limited to the same two STM
nets, and all other added copper is /PS_HOLD.  The builder fails closed unless
all three PS_HOLD endpoints are connected, DCDC_EN remains complete, the 13
inherited DRC violations retain the same identities, and every preservation
and project-verifier gate passes.
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
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover
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
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8e_edge_dcdc_en_ps_hold_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8e_edge_dcdc_en_ps_hold_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8e_edge_dcdc_en_ps_hold_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8e_edge_dcdc_en_ps_hold_board_verifier.json"
PREVIEW_DIR = STAGING / "r8e_edge_dcdc_en_ps_hold_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"

ROUTING_UUID_SEED = 1750852
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_COPPER = 1263
EXPECTED_CANDIDATE_COPPER = 1279
EXPECTED_SOURCE_UNCONNECTED = 120
EXPECTED_CANDIDATE_UNCONNECTED = 118
EXPECTED_DRC_COUNT = 13

# These boards are read only for KIID namespace collision auditing.  They are
# never consulted for placement or routing geometry; SOURCE_BOARD remains the
# sole geometry source.
UUID_AUDIT_SIBLING_BOARDS: tuple[tuple[str, Path, str], ...] = (
    (
        "r8e_ps_hold_partial_seed_1750851",
        STAGING / "mf1750_wroom_b3_power_tf_r8e_ps_hold_partial_routed.kicad_pcb",
        "86e9c10b87f35f7528dc09c60315f4d7e982c63bbb92f7bcf0b96f00891b9e9b",
    ),
    (
        "r8e_boot_n_seed_1750861",
        STAGING / "mf1750_wroom_b3_power_tf_r8e_boot_n_routed.kicad_pcb",
        "2a1f76928cfa17de688949be06c410bdedccf6dbe7b1ddbe2b0080d907e0ab7e",
    ),
)

CONTROLLED_OLD_COPPER: dict[str, tuple[object, ...]] = {
    "70083660-c0fc-4e09-8bef-795999615f10": ("via", "/STM_VREF", (9.0, 78.25), 0.6, 0.3, 0, 2),
    "067bb8c6-cfc4-485c-907d-77fcaa20f678": ("via", "/STM_CSRD", (9.0, 79.25), 0.6, 0.3, 0, 2),
    "a8343375-9400-47c8-85f4-2b1ce7107f3a": ("track", "/STM_VREF", 0, (10.2, 78.25), (9.0, 78.25), 0.2),
    "63dc1b80-3e26-40f6-8175-3e39256506c8": ("track", "/STM_CSRD", 0, (10.2, 79.25), (9.0, 79.25), 0.2),
    "645735ec-e719-4a13-8c26-c5f2d02e9380": ("track", "/STM_VREF", 2, (9.0, 78.25), (7.5, 78.25), 0.2),
    "31c081d4-a9e4-48af-ab32-318686138f11": ("track", "/STM_CSRD", 6, (9.0, 79.25), (8.0, 79.25), 0.2),
}

PAD_CONTRACT = {
    ("U1", "38"): ("/PS_HOLD", 54.7200, 98.7500),
    ("U3", "3"): ("/STM_VREF", 10.2000, 78.2500),
    ("U3", "4"): ("/PS_HOLD", 10.2000, 78.7500),
    ("U3", "5"): ("/STM_CSRD", 10.2000, 79.2500),
    ("R60", "1"): ("/PS_HOLD", 35.9750, 71.5000),
}

REPLACEMENT_ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/STM_VREF", "F.Cu", ((10.2000, 78.2500), (7.2000, 77.9000))),
    ("/STM_VREF", "B.Cu", ((7.2000, 77.9000), (7.5000, 78.2500))),
    ("/STM_CSRD", "F.Cu", ((10.2000, 79.2500), (8.2000, 79.6000))),
    ("/STM_CSRD", "In2.Cu", ((8.2000, 79.6000), (8.0000, 79.2500))),
)

REPLACEMENT_VIAS: tuple[tuple[str, float, float], ...] = (
    ("/STM_VREF", 7.2000, 77.9000),
    ("/STM_CSRD", 8.2000, 79.6000),
)

PS_HOLD_ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/PS_HOLD", "F.Cu", ((10.2000, 78.7500), (8.8000, 78.7500))),
    (
        "/PS_HOLD",
        "B.Cu",
        (
            (8.8000, 78.7500),
            (12.0000, 78.7500),
            (12.0000, 62.5000),
            (36.5000, 62.5000),
            (57.0000, 62.5000),
            (57.0000, 72.5000),
            (57.0000, 80.0000),
            (57.0000, 100.0000),
            (54.7200, 100.0000),
        ),
    ),
    ("/PS_HOLD", "F.Cu", ((35.9750, 71.5000), (35.9750, 72.5000), (45.0000, 72.5000), (57.0000, 72.5000))),
    ("/PS_HOLD", "F.Cu", ((54.7200, 100.0000), (54.7200, 98.7500))),
)

PS_HOLD_VIAS: tuple[tuple[str, float, float], ...] = (
    ("/PS_HOLD", 8.8000, 78.7500),
    ("/PS_HOLD", 57.0000, 72.5000),
    ("/PS_HOLD", 54.7200, 100.0000),
)

NEW_NET_COUNTS = {"/PS_HOLD": 16, "/STM_CSRD": 3, "/STM_VREF": 3}
NEW_NET_WHITELIST = frozenset(NEW_NET_COUNTS)


class RouteError(RuntimeError):
    """Fail-closed controlled-route error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r7_utility():
    if not R7_UTILITY.is_file() or sha256_file(R7_UTILITY) != R7_UTILITY_SHA256:
        raise RouteError(f"R7 utility missing or hash-mismatched: {R7_UTILITY}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8e_controlled_r7", R7_UTILITY)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R7 utility import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.base.ALLOWED_NETS = NEW_NET_WHITELIST
    return module


r7 = load_r7_utility()
base = r7.base


def validate_source_contract(board, state: dict[str, object]) -> dict[str, object]:
    if len(state["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(f"source copper count drift: {len(state['tracks'])}")
    if state["copper_uuid_audit"]["passed"] is not True:
        raise RouteError("source contains duplicate copper UUIDs")
    actual = {item_id: state["tracks"].get(item_id) for item_id in CONTROLLED_OLD_COPPER}
    if actual != CONTROLLED_OLD_COPPER:
        raise RouteError(f"controlled old-copper signature drift: {actual}")
    pads = []
    for (reference, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = base.find_numbered_pad(board, reference, number)
        position = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or any(
            abs(got - expected) > 0.000002
            for got, expected in zip(position, (x_mm, y_mm), strict=True)
        ):
            raise RouteError(f"pad contract drift: {reference}.{number} {pad.GetNetname()}@{position}")
        pads.append({"reference": reference, "pad": number, "net": net, "position_mm": list(position)})
    return {
        "passed": True,
        "source_copper_count": len(state["tracks"]),
        "controlled_old_copper": [
            {"uuid": item_id, "signature": list(signature)}
            for item_id, signature in sorted(CONTROLLED_OLD_COPPER.items())
        ],
        "pad_contract": pads,
    }


def remove_controlled_items(board) -> list[dict[str, object]]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    removed = []
    for item_id in sorted(CONTROLLED_OLD_COPPER):
        item = by_id.get(item_id)
        if item is None:
            raise RouteError(f"controlled source item missing: {item_id}")
        removed.append({"uuid": item_id, "net": item.GetNetname()})
        board.Remove(item)
    return removed


def add_track_routes(board, routes) -> list[str]:
    """Add routes and capture their KIIDs while SWIG still owns a live proxy."""
    added_ids: list[str] = []
    for net, layer, points in routes:
        if net not in NEW_NET_WHITELIST or layer == "In1.Cu":
            raise RouteError(f"new route violates whitelist/layer rule: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            item = base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end)
            added_ids.append(base.item_uuid(item))
    return added_ids


def add_vias(board, vias) -> list[str]:
    """Add vias and capture their KIIDs immediately (see add_track_routes)."""
    added_ids: list[str] = []
    for net, x_mm, y_mm in vias:
        if net not in NEW_NET_WHITELIST:
            raise RouteError(f"new via violates net whitelist: {net}")
        item = base.add_via(board, net, x_mm, y_mm)
        added_ids.append(base.item_uuid(item))
    return added_ids


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not parse fixed DCDC_EN source")
    before = base.source_state(board)
    source_contract = validate_source_contract(board, before)
    # Capture every new KIID before removing old SWIG-owned board items.  KiCad
    # 10 invalidates Python-facing KIID proxies after BOARD.Remove(), even for
    # subsequently allocated tracks; doing additions first avoids that binding
    # hazard while producing the same final board topology.
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added_ids_list: list[str] = []
    added_ids_list.extend(add_track_routes(board, REPLACEMENT_ROUTES))
    added_ids_list.extend(add_vias(board, REPLACEMENT_VIAS))
    added_ids_list.extend(add_track_routes(board, PS_HOLD_ROUTES))
    added_ids_list.extend(add_vias(board, PS_HOLD_VIAS))
    added_ids = set(added_ids_list)
    if len(added_ids) != len(added_ids_list):
        raise RouteError("deterministic KIID seed generated duplicate copper UUIDs")
    source_ids = set(before["tracks"])
    collision = sorted(added_ids & source_ids)
    if collision:
        raise RouteError(f"new copper KIID collides with source copper: {collision}")
    removed = remove_controlled_items(board)
    if not pcbnew.SaveBoard(str(destination), board):
        raise RouteError(f"failed to save candidate: {destination}")
    return before, added_ids, source_contract, removed


def sibling_uuid_namespace_audit(added_ids: set[str]) -> dict[str, object]:
    evidence = []
    passed = True
    for label, path, expected_sha in UUID_AUDIT_SIBLING_BOARDS:
        actual_sha = sha256_file(path) if path.is_file() else None
        hash_matches = actual_sha == expected_sha
        sibling_ids: set[str] = set()
        if hash_matches:
            sibling = pcbnew.LoadBoard(str(path))
            if sibling is None:
                hash_matches = False
            else:
                sibling_ids = set(base.source_state(sibling)["tracks"])
        intersection = sorted(added_ids & sibling_ids)
        item_passed = hash_matches and not intersection
        passed = passed and item_passed
        evidence.append(
            {
                "label": label,
                "role": "UUID_namespace_audit_only_not_geometry_source",
                "path": str(path),
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "hash_matches": hash_matches,
                "sibling_copper_uuid_count": len(sibling_ids),
                "new_uuid_intersection": intersection,
                "intersection_zero": not intersection,
                "passed": item_passed,
            }
        )
    return {
        "passed": passed,
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "new_uuid_count": len(added_ids),
        "all_known_sibling_intersections_zero": all(not item["new_uuid_intersection"] for item in evidence),
        "siblings": evidence,
    }


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


def controlled_preservation_audit(candidate, before, added_ids: set[str]) -> dict[str, object]:
    after = base.source_state(candidate)
    source_ids = set(before["tracks"])
    candidate_ids = set(after["tracks"])
    removed_ids = source_ids - candidate_ids
    unexpected_removed = sorted(removed_ids - set(CONTROLLED_OLD_COPPER))
    missing_controlled_removals = sorted(set(CONTROLLED_OLD_COPPER) - removed_ids)
    changed_retained = sorted(
        item_id
        for item_id in source_ids & candidate_ids
        if before["tracks"][item_id] != after["tracks"][item_id]
    )
    extra_ids = candidate_ids - source_ids
    new_uuid_source_intersection = sorted(added_ids & source_ids)
    unexpected_extra = sorted(extra_ids - added_ids)
    missing_added = sorted(added_ids - extra_ids)
    new_net_counts = collections.Counter(after["tracks"][item_id][1] for item_id in extra_ids)
    bad_new_nets = sorted(net for net in new_net_counts if net not in NEW_NET_WHITELIST)

    findings = {"b2": [], "antenna": [], "in1": [], "width": [], "via": []}
    by_id = {base.item_uuid(item): item for item in candidate.GetTracks()}
    for item_id in sorted(extra_ids):
        item = by_id[item_id]
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            ) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["via"].append(item_id)
            antenna_hit = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["width"].append(item_id)
            if item.GetLayer() == base.layer_id(candidate, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)

    checks = {
        "source_copper_uuid_unique": before["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_uuid_unique": after["copper_uuid_audit"]["passed"] is True,
        "exactly_six_controlled_source_items_removed": removed_ids == set(CONTROLLED_OLD_COPPER),
        "no_unexpected_source_copper_removed": not unexpected_removed,
        "all_controlled_old_copper_replaced": not missing_controlled_removals,
        "all_other_source_copper_uuid_geometry_exact": not changed_retained,
        "only_deterministic_added_ids": not unexpected_extra and not missing_added,
        "new_uuid_source_intersection_zero": not new_uuid_source_intersection,
        "new_copper_net_counts_exact": dict(sorted(new_net_counts.items())) == NEW_NET_COUNTS,
        "new_copper_nets_whitelisted": not bad_new_nets,
        "footprints_exact": before["footprints"] == after["footprints"],
        "zones_exact": before["zones"] == after["zones"],
        "candidate_copper_count_exactly_1279": len(after["tracks"]) == EXPECTED_CANDIDATE_COPPER,
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_antenna_keepout": not findings["antenna"],
        "no_new_track_on_in1": not findings["in1"],
        "all_new_tracks_0p20_mm": not findings["width"],
        "all_new_vias_0p60_0p30_mm": not findings["via"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_copper_count": len(before["tracks"]),
        "candidate_copper_count": len(after["tracks"]),
        "removed_ids": sorted(removed_ids),
        "added_ids": sorted(extra_ids),
        "new_net_counts": dict(sorted(new_net_counts.items())),
        "unexpected_removed": unexpected_removed,
        "missing_controlled_removals": missing_controlled_removals,
        "changed_retained_source_items": changed_retained,
        "unexpected_extra": unexpected_extra,
        "missing_added": missing_added,
        "new_uuid_source_intersection": new_uuid_source_intersection,
        "bad_new_nets": bad_new_nets,
        "envelope_findings": findings,
    }


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def violation_identity(raw: dict[str, object]) -> list[tuple[str, tuple[str, ...]]]:
    return sorted(
        (
            str(violation.get("type", "")),
            tuple(sorted(str(item.get("uuid", "")) for item in violation.get("items", []))),
        )
        for violation in raw.get("violations", [])
    )


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    other_nets = (set(source_nets) | set(candidate_nets)) - {"/PS_HOLD"}
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    checks = {
        "source_drc_exactly_13": source["violation_count"] == EXPECTED_DRC_COUNT,
        "candidate_drc_exactly_13": candidate["violation_count"] == EXPECTED_DRC_COUNT,
        "inherited_violation_identity_exact": violation_identity(source["raw"]) == violation_identity(candidate["raw"]),
        "source_unconnected_exactly_120": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_118": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_2": source["unconnected_count"] - candidate["unconnected_count"] == 2,
        "source_ps_hold_open_exactly_2": source_nets.get("/PS_HOLD", 0) == 2,
        "candidate_ps_hold_open_zero": candidate_nets.get("/PS_HOLD", 0) == 0,
        "source_dcdc_en_open_zero": source_nets.get("/DCDC_EN", 0) == 0,
        "candidate_dcdc_en_open_zero": candidate_nets.get("/DCDC_EN", 0) == 0,
        "all_other_unconnected_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_identity": violation_identity(source["raw"]),
        "candidate_violation_identity": violation_identity(candidate["raw"]),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-python", type=Path, default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    protected_paths = {
        "formal_board": FORMAL_BOARD,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
        "root_readme": ROOT_README,
        "b3_readme": B3_README,
        "sole_source_board": SOURCE_BOARD,
        "r7_utility": R7_UTILITY,
    }
    protected_before = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("sole DCDC_EN source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))

        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r8e-controlled-ps-hold-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, source_contract, removed = build_candidate(first)
            before2, added_ids2, source_contract2, removed2 = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and before == before2
                and added_ids == added_ids2
                and source_contract == source_contract2
                and removed == removed2
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            uuid_namespace = sibling_uuid_namespace_audit(added_ids)
            if not uuid_namespace["passed"]:
                raise RouteError("new copper UUID namespace intersects a hash-bound sibling branch")
            candidate = pcbnew.LoadBoard(str(first))
            if candidate is None:
                raise RouteError("saved candidate failed reload")
            preservation = controlled_preservation_audit(candidate, before, added_ids)
            if not preservation["passed"]:
                raise RouteError("controlled preservation/envelope audit failed")
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)

        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        gate = drc_gate(source_drc, candidate_drc)
        verifier = r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)

        SOURCE_DRC_JSON.write_text(json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CANDIDATE_DRC_JSON.write_text(json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        BOARD_VERIFIER_JSON.write_text(json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        renders = [
            base.render(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, FRONT_COPPER_SVG, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, BACK_COPPER_SVG, "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts", mirror=True),
        ]
        protected_after = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
        protected_unchanged = protected_before == protected_after
        passed = preservation["passed"] and uuid_namespace["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "REVISION_STAGING_ONLY_CONTROLLED_PS_HOLD_REROUTE",
            "state": "R8E_EDGE_DCDC_EN_PS_HOLD_ROUTED_CANDIDATE" if passed else "R8E_EDGE_DCDC_EN_PS_HOLD_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": passed,
            "kicad_version": str(pcbnew.GetBuildVersion()),
            "inputs": {"source": {"role": "sole_PCB_geometry_source", "path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256}, "r7_utility": {"path": str(R7_UTILITY), "sha256": R7_UTILITY_SHA256}},
            "output": {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)},
            "determinism": {"double_build_byte_identical": deterministic, "first_sha256": build_sha, "second_sha256": build_sha},
            "uuid_namespace_audit": uuid_namespace,
            "protected_sources": {"unchanged": protected_unchanged, "before": protected_before, "after": protected_after},
            "source_contract": source_contract,
            "controlled_change": {
                "allowed_removed_source_uuids": sorted(CONTROLLED_OLD_COPPER),
                "actual_removed_source_items": removed,
                "replacement_via_centers_mm": {"STM_VREF": [7.2, 77.9], "STM_CSRD": [8.2, 79.6]},
                "ps_hold_via_centers_mm": [[8.8, 78.75], [57.0, 72.5], [54.72, 100.0]],
                "new_net_counts": NEW_NET_COUNTS,
            },
            "routing_contract": {"completed_net": "/PS_HOLD", "inherited_completed_net": "/DCDC_EN", "routing_uuid_seed": ROUTING_UUID_SEED, "expected_unconnected": {"source": 120, "candidate": 118, "reduction": 2}, "expected_drc": {"source": 13, "candidate": 13, "identity": "exact"}, "signal_width_mm": SIGNAL_WIDTH_MM, "via_diameter_mm": VIA_DIAMETER_MM, "via_drill_mm": VIA_DRILL_MM, "b2_boundary_y_mm": B2_BOTTOM_MM, "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT), "in1_signal_routing": "FORBIDDEN"},
            "source_preservation_audit": preservation,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": ["/PS_HOLD"] if passed else [],
            "inherited_completed_scope": ["/DCDC_EN"] if gate["checks"]["candidate_dcdc_en_open_zero"] else [],
            "holds": [{"scope": "WHOLE_BOARD", "reason": f"{candidate_drc['unconnected_count']} unrelated items remain; not manufacturing-ready"}],
            "artifacts": {"source_drc_json": str(SOURCE_DRC_JSON), "candidate_drc_json": str(CANDIDATE_DRC_JSON), "board_verifier_json": str(BOARD_VERIFIER_JSON), "top_preview": str(TOP_PREVIEW), "bottom_preview": str(BOTTOM_PREVIEW), "front_copper_svg": str(FRONT_COPPER_SVG), "back_copper_svg": str(BACK_COPPER_SVG), "render_export": renders},
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"state": report["state"], "routing_checks_passed": passed, "output": report["output"], "drc": {"source_violations": source_drc["violation_count"], "candidate_violations": candidate_drc["violation_count"], "source_unconnected": source_drc["unconnected_count"], "candidate_unconnected": candidate_drc["unconnected_count"], "gate_passed": gate["passed"]}, "board_verifier": verifier["summary"], "report": str(REPORT_JSON)}, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except Exception as exc:
        report = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "REVISION_STAGING_ONLY_CONTROLLED_PS_HOLD_REROUTE", "state": "R8E_EDGE_DCDC_EN_PS_HOLD_ROUTE_FAILED", "overall_status": "HOLD", "operation_completed": False, "hardware_accessed": False, "network_accessed": False, "serial_or_com_accessed": False, "locally_verified": False, "routing_checks_passed": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "source": str(SOURCE_BOARD), "protected_sources_before": protected_before}
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
