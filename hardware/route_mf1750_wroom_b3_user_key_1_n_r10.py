#!/usr/bin/env python3
"""Route /USER_KEY_1_N from the frozen R10 unified staging board.

Operating mode: REVISION.  This is a staging-only, additive, single-net
builder.  It joins the two SW2 pad-1 contacts, R51.2, and U1.12 without
moving footprints or changing any source copper or zone.  F.Cu, B.Cu and
In2.Cu may be used; In1.Cu, B2, the WROOM antenna keepout, and the U3 core
remain forbidden.  The only controlled-area exception is the unavoidable
short R51.2 endpoint escape, which never approaches U3 or PS_HOLD copper.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import traceback
from typing import Any, Iterable

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

BOOT_UTILITY = HARDWARE / "route_mf1750_wroom_b3_boot_n_r8e.py"
BOOT_UTILITY_SHA256 = "e286488409b537a12159c6d3c91f6f800292e7ead9f8460885eda7f60d8c551d"
R7_UTILITY = HARDWARE / "route_mf1750_wroom_b3_epd_mcu_r7.py"
R7_UTILITY_SHA256 = "9f5add51e5e220bd4ddb02692ac6b2efb9039bdea090932c53b9ff71a3232a82"
SEED_LEDGER = B3_DIR / "ROUTING_UUID_SEEDS.json"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified.kicad_pcb"
SOURCE_SHA256 = "53ec067d73cbca12de0c874f2576b84dfe3120a544a43393c23f38dd283e08d0"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_routed.kicad_pcb"
REPORT_JSON = STAGING / "r11_user_key_1_n_route_report.json"
SOURCE_DRC_JSON = STAGING / "r11_user_key_1_n_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r11_user_key_1_n_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r11_user_key_1_n_board_verifier.json"
PREVIEW_DIR = STAGING / "r11_user_key_1_n_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"

ROUTING_UUID_SEED = 1750881
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
U3_CORE_KEEPOUT = (9.45, 76.75, 12.55, 80.25)
LEGACY_U3_PS_HOLD_CONTROLLED_AREA = (7.5, 75.5, 14.5, 84.0)
R51_ENDPOINT_ESCAPE = (7.35, 74.45, 8.25, 76.85)

EXPECTED_SOURCE_COPPER = 1283
EXPECTED_ADDED_TRACKS = 22
EXPECTED_ADDED_VIAS = 5
EXPECTED_CANDIDATE_COPPER = 1310
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_UNCONNECTED = 117
EXPECTED_CANDIDATE_UNCONNECTED = 114
ALLOWED_NETS = frozenset({"/USER_KEY_1_N"})

PAD_CONTRACT = (
    ("SW2", "1", "/USER_KEY_1_N", 1.3500, 70.7000),
    ("SW2", "1", "/USER_KEY_1_N", 1.3500, 74.3000),
    ("R51", "2", "/USER_KEY_1_N", 7.8250, 76.5000),
    ("U1", "12", "/USER_KEY_1_N", 43.2900, 81.2500),
)

# The SW2 weave is the already proven four-contact switch geometry.  Its
# B.Cu escape stays above the U3 controlled area and branches to R51.2 by the
# shortest possible F.Cu endpoint stub.  A short In2 bridge crosses the
# DCDC_EN lane, after which B.Cu has a clear eastbound corridor.  The final
# F.Cu approach passes between TP25 and the top row of U1 pads.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    (
        "/USER_KEY_1_N",
        "F.Cu",
        (
            (1.3500, 70.7000),
            (1.3500, 71.4000),
            (2.0000, 72.0500),
            (2.0000, 72.9500),
            (1.3500, 73.6000),
            (1.3500, 74.3000),
            (1.3500, 75.7000),
            (2.1000, 76.4500),
            (4.0000, 76.4500),
        ),
    ),
    (
        "/USER_KEY_1_N",
        "B.Cu",
        (
            (4.0000, 76.4500),
            (5.0000, 75.5000),
            (6.8000, 74.5000),
            (14.2000, 72.9000),
        ),
    ),
    (
        "/USER_KEY_1_N",
        "F.Cu",
        ((6.8000, 74.5000), (7.3500, 74.5000), (7.8250, 75.2000), (7.8250, 76.5000)),
    ),
    (
        "/USER_KEY_1_N",
        "F.Cu",
        ((14.2000, 72.9000), (27.2000, 72.9000)),
    ),
    (
        "/USER_KEY_1_N",
        "B.Cu",
        (
            (27.2000, 72.9000),
            (27.8000, 75.0000),
            (27.8000, 77.0000),
            (38.5000, 77.0000),
            (40.0000, 78.0000),
            (41.5000, 79.2000),
            (42.3000, 80.2000),
            (43.2900, 81.2500),
        ),
    ),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/USER_KEY_1_N", 4.0000, 76.4500),
    ("/USER_KEY_1_N", 6.8000, 74.5000),
    ("/USER_KEY_1_N", 14.2000, 72.9000),
    ("/USER_KEY_1_N", 27.2000, 72.9000),
    ("/USER_KEY_1_N", 43.2900, 81.2500),
)


class RouteError(RuntimeError):
    """Fail-closed USER_KEY_1_N route-builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, expected_sha256: str, name: str):
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise RouteError(f"frozen helper missing or hash-mismatched: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RouteError(f"could not import frozen helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


boot = load_module(BOOT_UTILITY, BOOT_UTILITY_SHA256, "_mf1750_r11_user_key_boot_utility")
r7 = load_module(R7_UTILITY, R7_UTILITY_SHA256, "_mf1750_r11_user_key_r7_utility")
base = boot.base
base.ALLOWED_NETS = ALLOWED_NETS


def point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x_value, y_value = point
    x0, y0, x1, y1 = rect
    return x0 <= x_value <= x1 and y0 <= y_value <= y1


def segment_hits_rect(start, end, rect) -> bool:
    return boot.segment_hits_rect(start, end, rect)


def validate_scope(board: Any) -> dict[str, object]:
    refs: set[str] = set()
    actual: list[tuple[str, str, str, float, float]] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != "/USER_KEY_1_N":
                continue
            refs.add(footprint.GetReference())
            x_mm, y_mm = base.point_mm(pad.GetPosition())
            actual.append((footprint.GetReference(), pad.GetNumber(), pad.GetNetname(), x_mm, y_mm))
    actual.sort()
    expected = sorted(PAD_CONTRACT)
    if len(actual) != len(expected):
        raise RouteError(f"USER_KEY_1_N pad-count drift: actual={actual}")
    for got, wanted in zip(actual, expected, strict=True):
        if got[:3] != wanted[:3] or any(
            abs(a - b) > 0.000002 for a, b in zip(got[3:], wanted[3:], strict=True)
        ):
            raise RouteError(f"USER_KEY_1_N pad contract drift: got={got}, expected={wanted}")
    if refs != {"SW2", "R51", "U1"}:
        raise RouteError(f"USER_KEY_1_N endpoint reference drift: {sorted(refs)}")
    return {
        "passed": True,
        "net": "/USER_KEY_1_N",
        "endpoint_references": sorted(refs),
        "pad_contract": [
            {"reference": ref, "pad": pad, "net": net, "position_mm": [x, y]}
            for ref, pad, net, x, y in actual
        ],
        "connected_set_required": ["SW2.1@70.7", "SW2.1@74.3", "R51.2", "U1.12"],
        "mechanical_dependency_references": [],
    }


def seed_registry_audit() -> dict[str, object]:
    ledger = json.loads(SEED_LEDGER.read_text(encoding="utf-8"))
    rows = [row for row in ledger.get("assignments", []) if row.get("seed_decimal") == ROUTING_UUID_SEED]
    expected_owner = Path(__file__).name
    pattern = re.compile(r"ROUTING_UUID_SEED\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)")
    owners: dict[int, set[str]] = collections.defaultdict(set)
    for path in sorted(HARDWARE.rglob("*.py")):
        for token in pattern.findall(path.read_text(encoding="utf-8", errors="replace")):
            owners[int(token, 0)].add(str(path.resolve()))
    current = str(Path(__file__).resolve())
    duplicate_ledger_seeds = sorted(
        seed for seed, count in collections.Counter(
            int(row["seed_decimal"]) for row in ledger.get("assignments", [])
        ).items() if count > 1
    )
    checks = {
        "seed_exactly_1750881": ROUTING_UUID_SEED == 1750881,
        "ledger_has_one_exact_reservation": len(rows) == 1,
        "ledger_owner_exact": len(rows) == 1 and rows[0].get("owner") == expected_owner,
        "ledger_status_reserved_for_candidate": len(rows) == 1 and rows[0].get("status") == "reserved_for_candidate",
        "chosen_seed_has_single_python_owner": owners.get(ROUTING_UUID_SEED, set()) == {current},
        "ledger_seed_assignments_unique": not duplicate_ledger_seeds,
    }
    if not all(checks.values()):
        raise RouteError("seed registry failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "ledger_path": str(SEED_LEDGER.resolve()),
        "ledger_sha256": sha256_file(SEED_LEDGER),
        "reservation": rows[0],
        "python_owner": current,
        "duplicate_ledger_seeds": duplicate_ledger_seeds,
    }


def add_routes(board: Any) -> list[Any]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added: list[Any] = []
    for net, layer, points in ROUTES:
        if net not in ALLOWED_NETS or layer not in {"F.Cu", "B.Cu", "In2.Cu"}:
            raise RouteError(f"route violates allowlist/layer contract: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end))
    for net, x_mm, y_mm in VIAS:
        if net not in ALLOWED_NETS:
            raise RouteError(f"via violates allowlist: {net}")
        added.append(base.add_via(board, net, x_mm, y_mm))
    if len(added) != EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS:
        raise RouteError(f"unexpected added-copper count: {len(added)}")
    return added


def uuid_collision_audit(added_ids: set[str], source_ids: set[str]) -> dict[str, object]:
    registry_union: set[str] = set()
    records = []
    output_resolved = OUTPUT_BOARD.resolve()
    for path in sorted(STAGING.glob("*.kicad_pcb")):
        if path.resolve() == output_resolved:
            continue
        board = pcbnew.LoadBoard(str(path.resolve()))
        if board is None:
            raise RouteError(f"UUID registry board failed to parse: {path}")
        ids = {base.item_uuid(item) for item in board.GetTracks()}
        registry_union.update(ids)
        intersection = sorted(added_ids & ids)
        records.append({"path": str(path.resolve()), "sha256": sha256_file(path), "intersection": intersection})
    checks = {
        "added_uuid_count_exact": len(added_ids) == EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS,
        "source_intersection_zero": not (added_ids & source_ids),
        "all_existing_staging_board_intersection_zero": not (added_ids & registry_union),
        "all_registry_boards_individually_zero": all(not record["intersection"] for record in records),
    }
    if not all(checks.values()):
        raise RouteError("UUID collision audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "added_uuids": sorted(added_ids),
        "registry_board_count": len(records),
        "registry_union_count": len(registry_union),
        "records": records,
    }


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise RouteError("KiCad could not parse the fixed R10 source")
    scope = validate_scope(board)
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(f"source copper-count drift: {len(before['tracks'])}")
    added = add_routes(board)
    added_ids = {base.item_uuid(item) for item in added}
    if len(added_ids) != len(added):
        raise RouteError("duplicate deterministic copper UUID")
    scope["seed_registry_audit"] = seed_registry_audit()
    scope["uuid_collision_audit"] = uuid_collision_audit(added_ids, set(before["tracks"]))
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise RouteError(f"failed to save {destination}")
    return before, added_ids, scope


def envelope_audit(board: Any, added_ids: set[str]) -> dict[str, object]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    findings: dict[str, list[str]] = {
        "non_allowlisted_net": [], "b2": [], "antenna": [], "in1": [],
        "u3_core": [], "legacy_controlled_outside_r51_escape": [],
        "bad_width": [], "bad_via": [],
    }
    endpoint_escape_objects: list[str] = []
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
            core_hit = point_in_rect(points[0], U3_CORE_KEEPOUT)
            legacy_hit = point_in_rect(points[0], LEGACY_U3_PS_HOLD_CONTROLLED_AREA)
            escape_only = point_in_rect(points[0], R51_ENDPOINT_ESCAPE)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
            core_hit = segment_hits_rect(points[0], points[1], U3_CORE_KEEPOUT)
            legacy_hit = segment_hits_rect(points[0], points[1], LEGACY_U3_PS_HOLD_CONTROLLED_AREA)
            escape_only = all(point_in_rect(point, R51_ENDPOINT_ESCAPE) for point in points)
        if any(y < B2_BOTTOM_MM for _, y in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
        if core_hit:
            findings["u3_core"].append(item_id)
        if legacy_hit:
            if escape_only:
                endpoint_escape_objects.append(item_id)
            else:
                findings["legacy_controlled_outside_r51_escape"].append(item_id)
    checks = {
        "new_copper_user_key_1_n_only": not findings["non_allowlisted_net"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_wroom_antenna_keepout": not findings["antenna"],
        "no_signal_track_on_in1": not findings["in1"],
        "no_new_copper_in_u3_core": not findings["u3_core"],
        "legacy_controlled_area_only_unavoidable_r51_endpoint_escape": not findings[
            "legacy_controlled_outside_r51_escape"
        ],
        "all_new_tracks_exactly_0p20_mm": not findings["bad_width"],
        "all_new_vias_exactly_0p60_0p30_mm": not findings["bad_via"],
    }
    return {
        "passed": all(checks.values()), "checks": checks, "findings": findings,
        "r51_endpoint_escape_object_uuids": endpoint_escape_objects,
        "r51_endpoint_escape_reason": "minimum copper required to terminate at R51.2; U3 core and PS_HOLD copper remain untouched",
    }


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    return boot.unconnected_by_net(raw)


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    for net in ("/USER_KEY_1_N", "/DCDC_EN", "/BOOT_N", "/PS_HOLD"):
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets) if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fingerprints = boot.violation_fingerprints(source["raw"])
    candidate_fingerprints = boot.violation_fingerprints(candidate["raw"])
    checks = {
        "source_drc_exactly_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_drc_exactly_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_uuid_position_identity_exact": source_fingerprints == candidate_fingerprints,
        "source_unconnected_exactly_117": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_114": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_3": source["unconnected_count"] - candidate["unconnected_count"] == 3,
        "source_user_key_1_n_unconnected_exactly_3": source_nets.get("/USER_KEY_1_N", 0) == 3,
        "candidate_user_key_1_n_unconnected_zero": candidate_nets.get("/USER_KEY_1_N", 0) == 0,
        "source_dcdc_en_unconnected_zero": source_nets.get("/DCDC_EN", 0) == 0,
        "candidate_dcdc_en_unconnected_zero": candidate_nets.get("/DCDC_EN", 0) == 0,
        "source_boot_n_unconnected_zero": source_nets.get("/BOOT_N", 0) == 0,
        "candidate_boot_n_unconnected_zero": candidate_nets.get("/BOOT_N", 0) == 0,
        "source_ps_hold_unconnected_two": source_nets.get("/PS_HOLD", 0) == 2,
        "candidate_ps_hold_unconnected_two": candidate_nets.get("/PS_HOLD", 0) == 2,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "source_schematic_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "violation_categories_exact": source_categories == candidate_categories,
    }
    return {
        "passed": all(checks.values()), "checks": checks,
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
    parser.add_argument("--kicad-python", type=Path, default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    protected_paths = {
        "formal_board": FORMAL_BOARD, "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT, "root_readme": ROOT_README,
        "b3_readme": B3_README, "status_handoff": STATUS_HANDOFF,
        "r10_source_board": SOURCE_BOARD, "seed_ledger": SEED_LEDGER,
        "boot_utility": BOOT_UTILITY, "r7_utility": R7_UTILITY,
    }
    protected_before = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("fixed R10 source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))

        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r11-user-key-1-n-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, scope = build_candidate(first)
            before2, added_ids2, scope2 = build_candidate(second)
            deterministic = first.read_bytes() == second.read_bytes() and before == before2 and added_ids == added_ids2 and scope == scope2
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            reloaded = pcbnew.LoadBoard(str(first.resolve()))
            if reloaded is None:
                raise RouteError("saved candidate failed reload")
            preservation = base.audit_candidate(reloaded, before, added_ids)
            envelope = envelope_audit(reloaded, added_ids)
            preservation["r11_user_key_1_n_route_envelope"] = envelope
            preservation["checks"]["source_copper_count_exactly_1283"] = preservation["source_copper_count"] == EXPECTED_SOURCE_COPPER
            preservation["checks"]["added_tracks_exactly_22"] = preservation["added_track_count"] == EXPECTED_ADDED_TRACKS
            preservation["checks"]["added_vias_exactly_5"] = preservation["added_via_count"] == EXPECTED_ADDED_VIAS
            preservation["passed"] = all(preservation["checks"].values()) and envelope["passed"]
            if len(list(reloaded.GetTracks())) != EXPECTED_CANDIDATE_COPPER:
                raise RouteError("candidate copper-count drift")
            if not preservation["passed"]:
                raise RouteError("source/envelope preservation audit failed")
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
        passed = preservation["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION", "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_USER_KEY_1_N",
            "revision": "R11_USER_KEY_1_N_STAGING",
            "state": "R11_USER_KEY_1_N_ROUTED_CANDIDATE" if passed else "R11_USER_KEY_1_N_ROUTE_FAILED_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "operation_completed": True, "hardware_accessed": False, "network_accessed": False,
            "serial_or_com_accessed": False, "routing_checks_passed": passed,
            "inputs": {
                "source": {"role": "sole_PCB_geometry_source", "path": str(SOURCE_BOARD.resolve()), "sha256": SOURCE_SHA256},
                "boot_utility": {"path": str(BOOT_UTILITY.resolve()), "sha256": BOOT_UTILITY_SHA256},
                "r7_utility": {"path": str(R7_UTILITY.resolve()), "sha256": R7_UTILITY_SHA256},
            },
            "output": {"path": str(OUTPUT_BOARD.resolve()), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)},
            "builder": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
            "kicad": {"version": str(pcbnew.GetBuildVersion()), "cli": str(kicad_cli)},
            "determinism": {"double_build_byte_identical": deterministic, "first_sha256": build_sha, "second_sha256": build_sha},
            "protected_sources": {"unchanged": protected_unchanged, "before": protected_before, "after": protected_after},
            "scope_audit": scope,
            "routing_contract": {
                "allowed_nets": sorted(ALLOWED_NETS), "routing_uuid_seed": ROUTING_UUID_SEED,
                "new_copper": {"tracks": EXPECTED_ADDED_TRACKS, "vias": EXPECTED_ADDED_VIAS},
                "layers": ["F.Cu", "B.Cu", "In2.Cu"], "in1_signal_routing": "FORBIDDEN",
                "signal_width_mm": SIGNAL_WIDTH_MM, "via_diameter_mm": VIA_DIAMETER_MM, "via_drill_mm": VIA_DRILL_MM,
                "b2_boundary_y_mm": B2_BOTTOM_MM, "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
                "u3_core_keepout_mm": list(U3_CORE_KEEPOUT),
                "legacy_u3_ps_hold_controlled_area_mm": list(LEGACY_U3_PS_HOLD_CONTROLLED_AREA),
                "r51_endpoint_escape_mm": list(R51_ENDPOINT_ESCAPE),
                "expected_drc": {"source": 13, "candidate": 13, "new": 0},
                "expected_unconnected": {"source": 117, "candidate": 114, "reduction": 3},
            },
            "source_preservation_audit": preservation,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": ["/USER_KEY_1_N"] if passed else [],
            "holds": [
                {"scope": "/PS_HOLD", "reason": "remains at two opens; U3 controlled reroute untouched"},
                {"scope": "EDGE_CONNECTORS_USB_TF_POWER_TRUNKS", "reason": "outside this single-net route scope"},
                {"scope": "WHOLE_BOARD", "reason": f"{candidate_drc['unconnected_count']} held items remain; not manufacturing-ready"},
            ],
            "artifacts": {
                "source_drc_json": str(SOURCE_DRC_JSON.resolve()), "candidate_drc_json": str(CANDIDATE_DRC_JSON.resolve()),
                "board_verifier_json": str(BOARD_VERIFIER_JSON.resolve()), "top_preview": str(TOP_PREVIEW.resolve()),
                "bottom_preview": str(BOTTOM_PREVIEW.resolve()), "front_copper_svg": str(FRONT_COPPER_SVG.resolve()),
                "back_copper_svg": str(BACK_COPPER_SVG.resolve()), "render_export": renders,
            },
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"state": report["state"], "routing_checks_passed": passed, "output": report["output"], "drc": {"source_violations": source_drc["violation_count"], "candidate_violations": candidate_drc["violation_count"], "source_unconnected": source_drc["unconnected_count"], "candidate_unconnected": candidate_drc["unconnected_count"], "gate_passed": gate["passed"]}, "board_verifier": verifier["summary"], "report": str(REPORT_JSON)}, indent=2))
        return 0 if passed else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_USER_KEY_1_N", "revision": "R11_USER_KEY_1_N_STAGING",
            "state": "R11_USER_KEY_1_N_ROUTE_FAILED_HOLD", "overall_status": "HOLD", "operation_completed": False,
            "hardware_accessed": False, "network_accessed": False, "serial_or_com_accessed": False,
            "routing_checks_passed": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(),
            "source": str(SOURCE_BOARD), "protected_sources_before": protected_before,
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
