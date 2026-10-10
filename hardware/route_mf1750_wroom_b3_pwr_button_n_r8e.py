#!/usr/bin/env python3
"""Route /PWR_BUTTON_N on the frozen R8d edge-DCDC staging board.

Operating mode: REVISION, staging-only.  The SHA-bound DCDC_EN board is the
sole geometry source.  The builder moves no footprint and preserves every
source copper object.  It joins both SW1 pad-1 contacts and U3 pads 2/6 using
F.Cu, In2.Cu, and two standard through vias.  In1.Cu, B2, and the WROOM
antenna keepout are forbidden.  In2.Cu is intentional: the SW2 NPTH and the
existing wide /EPD_SW_3V3 B.Cu trunk leave no manufacturable B.Cu channel.

UUID seed 1750871 is reserved uniquely for this route.  Each build audits the
seed registry and proves its new UUIDs are disjoint from both the source board
and every other existing staging-board copper set.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import build_mf1750_wroom_b3_r8d_j6_c49_hand_solder_clearance as j6_helper
import route_mf1750_wroom_b3_boot_n_r8e as boot


pcbnew = boot.pcbnew
base = boot.base

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"
SOURCE_ROUTE_BUILDER = HARDWARE / "route_mf1750_wroom_b3_edge_dcdc_en_r8d.py"
SOURCE_ROUTE_BUILDER_SHA256 = (
    "3f2ce4a13cb7f595311de32b4299bc26c6a1603106087f8608f66c765d20a656"
)
SOURCE_ROUTE_REPORT = STAGING / "r8d_edge_dcdc_en_route_report.json"
SOURCE_ROUTE_REPORT_SHA256 = (
    "c75f09bb7c98e22064399a46dc863532de8677a59d07c1a2a1292546d7e96065"
)
BOOT_TEMPLATE = HARDWARE / "route_mf1750_wroom_b3_boot_n_r8e.py"
BOOT_TEMPLATE_SHA256 = (
    "e286488409b537a12159c6d3c91f6f800292e7ead9f8460885eda7f60d8c551d"
)
R11_PS_SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified.kicad_pcb"
R11_PS_SOURCE_SHA256 = (
    "53ec067d73cbca12de0c874f2576b84dfe3120a544a43393c23f38dd283e08d0"
)
R11_PS_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified.kicad_pcb"
R11_PS_BOARD_SHA256 = (
    "74d1e8a023e6aae67049b96e39d7210b9e66f42427cec7394053d76433e97d43"
)
R11_PS_BUILDER = HARDWARE / "build_mf1750_wroom_b3_r11_ps_hold_unified.py"
R11_PS_BUILDER_SHA256 = (
    "6f1f9b1df7a36aee4e4dbbed29c6c4b10b0fb0da68494a2eecd343aac6a75cea"
)
R11_PS_REPORT = STAGING / "r11_r10_ps_hold_unified_report.json"
R11_PS_REPORT_SHA256 = (
    "05ca634ab1a6bf3ca0ad393e6a26dd3f5b1256be30605b9761b8309bf69e4a46"
)

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8e_pwr_button_n_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8e_pwr_button_n_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8e_pwr_button_n_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8e_pwr_button_n_board_verifier.json"
PREVIEW_DIR = STAGING / "r8e_pwr_button_n_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_back.svg"

ROUTING_UUID_SEED = 1750871
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_COPPER = 1263
EXPECTED_ADDED_TRACKS = 17
EXPECTED_ADDED_VIAS = 2
EXPECTED_CANDIDATE_COPPER = 1282
EXPECTED_SOURCE_UNCONNECTED = 120
EXPECTED_CANDIDATE_UNCONNECTED = 117
ALLOWED_NETS = frozenset({"/PWR_BUTTON_N"})

PAD_CONTRACT = (
    ("SW1", "1", "/PWR_BUTTON_N", 1.3500, 62.7000),
    ("SW1", "1", "/PWR_BUTTON_N", 1.3500, 66.3000),
    ("U3", "2", "/PWR_BUTTON_N", 10.2000, 77.7500),
    ("U3", "6", "/PWR_BUTTON_N", 10.2000, 79.7500),
)

# The SW1 weave is the proven switch-contact geometry used by the BOOT_N
# route, translated to SW1.  A through via drops to In2.Cu above SW2; the
# trunk then passes right of the switch NPTHs without touching the existing
# B.Cu /EPD_SW_3V3 trunk.  One U3-side via feeds two independent F.Cu escapes.
# U3.6 exits directly below /STM_CSRD.  U3.2 uses the package centre channel
# and loops below U3, avoiding the blocked /VSYS_RAW--/STM_VREF corridor.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    (
        "/PWR_BUTTON_N",
        "F.Cu",
        (
            (1.3500, 62.7000),
            (1.3500, 63.4000),
            (2.0000, 64.0500),
            (2.0000, 64.9500),
            (1.3500, 65.6000),
            (1.3500, 66.3000),
            (1.3500, 68.0000),
            (3.0000, 68.0000),
        ),
    ),
    (
        "/PWR_BUTTON_N",
        "In2.Cu",
        ((3.0000, 68.0000), (4.5000, 69.5000), (4.5000, 80.4000), (5.0000, 80.4000)),
    ),
    (
        "/PWR_BUTTON_N",
        "F.Cu",
        ((5.0000, 80.4000), (8.0000, 80.4000)),
    ),
    (
        "/PWR_BUTTON_N",
        "F.Cu",
        ((8.0000, 80.4000), (9.4000, 80.4000), (9.8000, 79.7500), (10.2000, 79.7500)),
    ),
    (
        "/PWR_BUTTON_N",
        "F.Cu",
        (
            (8.0000, 80.4000),
            (10.8500, 80.4000),
            (10.8500, 77.7500),
            (10.2000, 77.7500),
        ),
    ),
)

VIAS = (
    ("/PWR_BUTTON_N", 3.0000, 68.0000),
    ("/PWR_BUTTON_N", 5.0000, 80.4000),
)


class RouteError(RuntimeError):
    """Fail-closed /PWR_BUTTON_N routing error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure_template() -> None:
    boot.SOURCE_BOARD = SOURCE_BOARD
    boot.SOURCE_SHA256 = SOURCE_SHA256
    boot.OUTPUT_BOARD = OUTPUT_BOARD
    boot.REPORT_JSON = REPORT_JSON
    boot.SOURCE_DRC_JSON = SOURCE_DRC_JSON
    boot.CANDIDATE_DRC_JSON = CANDIDATE_DRC_JSON
    boot.BOARD_VERIFIER_JSON = BOARD_VERIFIER_JSON
    boot.PREVIEW_DIR = PREVIEW_DIR
    boot.TOP_PREVIEW = TOP_PREVIEW
    boot.BOTTOM_PREVIEW = BOTTOM_PREVIEW
    boot.FRONT_COPPER_SVG = FRONT_COPPER_SVG
    boot.BACK_COPPER_SVG = BACK_COPPER_SVG
    boot.ROUTING_UUID_SEED = ROUTING_UUID_SEED
    boot.SIGNAL_WIDTH_MM = SIGNAL_WIDTH_MM
    boot.VIA_DIAMETER_MM = VIA_DIAMETER_MM
    boot.VIA_DRILL_MM = VIA_DRILL_MM
    boot.B2_BOTTOM_MM = B2_BOTTOM_MM
    boot.WROOM_ANTENNA_KEEPOUT = WROOM_ANTENNA_KEEPOUT
    boot.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    boot.EXPECTED_ADDED_TRACKS = EXPECTED_ADDED_TRACKS
    boot.EXPECTED_ADDED_VIAS = EXPECTED_ADDED_VIAS
    boot.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    boot.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_SOURCE_UNCONNECTED
    boot.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_CANDIDATE_UNCONNECTED
    boot.ALLOWED_NETS = ALLOWED_NETS
    base.ALLOWED_NETS = ALLOWED_NETS
    boot.PAD_CONTRACT = PAD_CONTRACT
    boot.ROUTES = ROUTES
    boot.VIAS = VIAS
    boot.add_routes = add_routes
    boot.__file__ = str(Path(__file__).resolve())
    boot.validate_scope = validate_scope
    boot.build_candidate = build_candidate
    boot.envelope_audit = envelope_audit
    boot.drc_gate = drc_gate


def add_routes(board: Any) -> list[object]:
    """Add only the deterministic PWR_BUTTON_N route on allowed layers."""
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added: list[object] = []
    allowed_layers = {"F.Cu", "B.Cu", "In2.Cu"}
    for net, layer, points in ROUTES:
        if net not in ALLOWED_NETS or layer not in allowed_layers:
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


def validate_scope(board: Any) -> dict[str, object]:
    refs: set[str] = set()
    actual: list[tuple[str, str, str, float, float]] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != "/PWR_BUTTON_N":
                continue
            refs.add(footprint.GetReference())
            x_mm, y_mm = base.point_mm(pad.GetPosition())
            actual.append(
                (footprint.GetReference(), pad.GetNumber(), pad.GetNetname(), x_mm, y_mm)
            )
    expected = sorted(PAD_CONTRACT)
    actual.sort()
    if len(actual) != len(expected):
        raise RouteError(f"PWR_BUTTON_N pad-count drift: actual={actual}")
    for got, wanted in zip(actual, expected, strict=True):
        if got[:3] != wanted[:3] or any(
            abs(a - b) > 0.000002
            for a, b in zip(got[3:], wanted[3:], strict=True)
        ):
            raise RouteError(
                f"PWR_BUTTON_N pad contract drift: got={got}, expected={wanted}"
            )
    if refs != {"SW1", "U3"}:
        raise RouteError(f"PWR_BUTTON_N endpoint reference drift: {sorted(refs)}")
    return {
        "passed": True,
        "net": "/PWR_BUTTON_N",
        "endpoint_references": sorted(refs),
        "pad_contract": [
            {
                "reference": ref,
                "pad": pad,
                "net": net,
                "position_mm": [x_mm, y_mm],
            }
            for ref, pad, net, x_mm, y_mm in actual
        ],
        "connected_set_required": [
            "SW1.1@62.7",
            "SW1.1@66.3",
            "U3.2",
            "U3.6",
        ],
        "mechanical_dependency_references": [],
    }


def seed_registry() -> dict[str, object]:
    pattern = re.compile(r"ROUTING_UUID_SEED\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)")
    owners: dict[int, list[str]] = collections.defaultdict(list)
    scanned: list[str] = []
    for path in sorted(HARDWARE.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = pattern.findall(text)
        if not matches:
            continue
        scanned.append(str(path.resolve()))
        for token in matches:
            owners[int(token, 0)].append(str(path.resolve()))
    current = str(Path(__file__).resolve())
    chosen_owners = sorted(set(owners.get(ROUTING_UUID_SEED, [])))
    checks = {
        "seed_exactly_1750871": ROUTING_UUID_SEED == 1750871,
        "chosen_seed_has_single_owner": chosen_owners == [current],
        "known_historical_1750851_collision_visible": len(
            set(owners.get(1750851, []))
        )
        == 2,
    }
    if not all(checks.values()):
        raise RouteError(
            "routing UUID seed registry failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "chosen_seed": ROUTING_UUID_SEED,
        "chosen_seed_owners": chosen_owners,
        "registry": {
            str(seed): sorted(set(paths)) for seed, paths in sorted(owners.items())
        },
        "scanned_python_files_with_seed": scanned,
    }


def uuid_collision_audit(added_ids: set[str], source_ids: set[str]) -> dict[str, object]:
    source_intersection = sorted(added_ids & source_ids)
    board_records: list[dict[str, object]] = []
    registry_union: set[str] = set()
    output_resolved = OUTPUT_BOARD.resolve()
    for path in sorted(STAGING.glob("*.kicad_pcb")):
        if path.resolve() == output_resolved:
            continue
        board = pcbnew.LoadBoard(str(path.resolve()))
        if board is None:
            raise RouteError(f"UUID registry board failed to parse: {path}")
        ids = {base.item_uuid(item) for item in board.GetTracks()}
        intersection = sorted(added_ids & ids)
        registry_union.update(ids)
        board_records.append(
            {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "copper_count": len(ids),
                "intersection": intersection,
            }
        )
    registry_intersection = sorted(added_ids & registry_union)
    checks = {
        "added_uuid_count_exact": len(added_ids)
        == EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS,
        "added_uuid_unique": len(added_ids)
        == EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS,
        "source_intersection_zero": not source_intersection,
        "all_existing_staging_board_copper_intersection_zero": not registry_intersection,
        "all_registry_boards_individually_zero": all(
            not record["intersection"] for record in board_records
        ),
    }
    if not all(checks.values()):
        raise RouteError(
            "routing UUID collision audit failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "added_uuids": sorted(added_ids),
        "source_intersection": source_intersection,
        "registry_board_count": len(board_records),
        "registry_copper_uuid_union_count": len(registry_union),
        "registry_intersection": registry_intersection,
        "boards": board_records,
    }


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise RouteError("KiCad could not parse the fixed R8d source")
    scope = validate_scope(board)
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(
            f"source copper-count drift: {len(before['tracks'])}, expected {EXPECTED_SOURCE_COPPER}"
        )
    added = boot.add_routes(board)
    added_ids = {base.item_uuid(item) for item in added}
    if len(added_ids) != len(added):
        raise RouteError("duplicate deterministic copper UUID within new route")
    scope["seed_registry_audit"] = seed_registry()
    scope["uuid_collision_audit"] = uuid_collision_audit(
        added_ids, set(before["tracks"])
    )
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise RouteError(f"failed to save {destination}")
    return before, added_ids, scope


def envelope_audit(board: Any, added_ids: set[str]) -> dict[str, object]:
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
            antenna_hit = boot.point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = boot.segment_hits_rect(
                points[0], points[1], WROOM_ANTENNA_KEEPOUT
            )
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    checks = {
        "new_copper_net_whitelist_pwr_button_n_only": not findings[
            "non_allowlisted_net"
        ],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_wroom_antenna_keepout": not findings["antenna"],
        "no_signal_track_on_in1": not findings["in1"],
        "all_new_tracks_exactly_0p20_mm": not findings["bad_width"],
        "all_new_vias_exactly_0p60_0p30_mm": not findings["bad_via"],
    }
    return {"passed": all(checks.values()), "checks": checks, "findings": findings}


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    source_nets = boot.unconnected_by_net(source["raw"])
    candidate_nets = boot.unconnected_by_net(candidate["raw"])
    for net in ("/PWR_BUTTON_N", "/DCDC_EN"):
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {
            "source": source_nets.get(net, 0),
            "candidate": candidate_nets.get(net, 0),
        }
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fingerprints = boot.violation_fingerprints(source["raw"])
    candidate_fingerprints = boot.violation_fingerprints(candidate["raw"])
    pwr_complete = candidate_nets.get("/PWR_BUTTON_N", 0) == 0
    checks = {
        "source_drc_exactly_13": source["violation_count"] == 13,
        "candidate_drc_exactly_13": candidate["violation_count"] == 13,
        "inherited_violation_uuid_position_identity_exact": source_fingerprints
        == candidate_fingerprints,
        "source_unconnected_exactly_120": source["unconnected_count"]
        == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_117": candidate["unconnected_count"]
        == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_3": source["unconnected_count"]
        - candidate["unconnected_count"]
        == 3,
        "source_pwr_button_n_unconnected_exactly_3": source_nets.get(
            "/PWR_BUTTON_N", 0
        )
        == 3,
        "candidate_pwr_button_n_unconnected_zero": pwr_complete,
        # Compatibility alias used by the imported report skeleton only.
        "candidate_boot_n_unconnected_zero": pwr_complete,
        "source_dcdc_en_unconnected_zero": source_nets.get("/DCDC_EN", 0) == 0,
        "candidate_dcdc_en_unconnected_zero": candidate_nets.get("/DCDC_EN", 0)
        == 0,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "source_schematic_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_schematic_parity_zero": candidate["schematic_parity_count"]
        == 0,
        "violation_categories_exact": source_categories == candidate_categories,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_categories": dict(sorted(source_categories.items())),
        "candidate_categories": dict(sorted(candidate_categories.items())),
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_fingerprints": source_fingerprints,
        "candidate_violation_fingerprints": candidate_fingerprints,
    }


def r11_ps_hold_cross_merge_audit() -> dict[str, object]:
    """Prove this exact delta can be overlaid on the frozen R11 PS branch."""
    lineage = {
        "r11_source_board": (R11_PS_SOURCE_BOARD, R11_PS_SOURCE_SHA256),
        "r11_ps_hold_board": (R11_PS_BOARD, R11_PS_BOARD_SHA256),
        "r11_ps_hold_builder": (R11_PS_BUILDER, R11_PS_BUILDER_SHA256),
        "r11_ps_hold_report": (R11_PS_REPORT, R11_PS_REPORT_SHA256),
    }
    lineage_checks = {
        key: path.is_file() and sha256_file(path) == expected
        for key, (path, expected) in lineage.items()
    }
    if not all(lineage_checks.values()):
        raise RouteError(f"R11 PS_HOLD cross-audit lineage drift: {lineage_checks}")

    def copper_by_uuid(board: Any) -> dict[str, Any]:
        return {base.item_uuid(item): item for item in board.GetTracks()}

    pwr_source = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    pwr_candidate = pcbnew.LoadBoard(str(OUTPUT_BOARD.resolve()))
    r11_source = pcbnew.LoadBoard(str(R11_PS_SOURCE_BOARD.resolve()))
    r11_candidate = pcbnew.LoadBoard(str(R11_PS_BOARD.resolve()))
    if any(board is None for board in (pwr_source, pwr_candidate, r11_source, r11_candidate)):
        raise RouteError("cross-merge audit could not parse a bound board")

    pwr_source_copper = copper_by_uuid(pwr_source)
    pwr_candidate_copper = copper_by_uuid(pwr_candidate)
    r11_source_copper = copper_by_uuid(r11_source)
    r11_candidate_copper = copper_by_uuid(r11_candidate)
    pwr_added = set(pwr_candidate_copper) - set(pwr_source_copper)
    pwr_removed = set(pwr_source_copper) - set(pwr_candidate_copper)
    ps_added = set(r11_candidate_copper) - set(r11_source_copper)
    ps_removed = set(r11_source_copper) - set(r11_candidate_copper)
    pwr_added_by_net = collections.Counter(
        pwr_candidate_copper[item_id].GetNetname() for item_id in pwr_added
    )
    ps_added_by_net = collections.Counter(
        r11_candidate_copper[item_id].GetNetname() for item_id in ps_added
    )
    ps_removed_by_net = collections.Counter(
        r11_source_copper[item_id].GetNetname() for item_id in ps_removed
    )

    kicad_cli = base.find_kicad_cli()
    r11_drc = base.run_drc(kicad_cli, R11_PS_BOARD)
    with tempfile.TemporaryDirectory(prefix="mf1750-pwr-r11-cross-") as name:
        merged_path = Path(name) / "r11_ps_hold_plus_pwr_button_n.kicad_pcb"
        merged_board = pcbnew.LoadBoard(str(R11_PS_BOARD.resolve()))
        before = base.source_state(merged_board)
        merged_items = add_routes(merged_board)
        merged_ids = {base.item_uuid(item) for item in merged_items}
        preexisting_intersection = sorted(merged_ids & set(before["tracks"]))
        if not pcbnew.SaveBoard(str(merged_path.resolve()), merged_board):
            raise RouteError("failed to save temporary R11 cross-merge board")
        reloaded = pcbnew.LoadBoard(str(merged_path.resolve()))
        preservation = base.audit_candidate(reloaded, before, merged_ids)
        envelope = envelope_audit(reloaded, merged_ids)
        merged_drc = base.run_drc(kicad_cli, merged_path)

    source_fingerprints = boot.violation_fingerprints(r11_drc["raw"])
    merged_fingerprints = boot.violation_fingerprints(merged_drc["raw"])
    source_nets = boot.unconnected_by_net(r11_drc["raw"])
    merged_nets = boot.unconnected_by_net(merged_drc["raw"])
    source_nets.setdefault("/PWR_BUTTON_N", 0)
    merged_nets.setdefault("/PWR_BUTTON_N", 0)
    other_net_drift = {
        net: {"source": source_nets.get(net, 0), "merged": merged_nets.get(net, 0)}
        for net in sorted(set(source_nets) | set(merged_nets))
        if net != "/PWR_BUTTON_N" and source_nets.get(net, 0) != merged_nets.get(net, 0)
    }
    checks = {
        "bound_r11_lineage_hashes_exact": all(lineage_checks.values()),
        "pwr_delta_exactly_19_add_0_remove": len(pwr_added) == 19 and not pwr_removed,
        "pwr_delta_only_pwr_button_n": pwr_added_by_net == {"/PWR_BUTTON_N": 19},
        "r11_ps_delta_exactly_22_add_6_replace": len(ps_added) == 22 and len(ps_removed) == 6,
        "r11_ps_delta_expected_net_composition": ps_added_by_net
        == {"/PS_HOLD": 16, "/STM_VREF": 3, "/STM_CSRD": 3}
        and ps_removed_by_net == {"/STM_VREF": 3, "/STM_CSRD": 3},
        "pwr_and_r11_ps_uuid_intersection_zero": not (pwr_added & ps_added),
        "overlay_generated_uuid_set_matches_standalone": merged_ids == pwr_added,
        "overlay_uuid_intersection_with_r11_zero": not preexisting_intersection,
        "overlay_preserves_every_r11_object": preservation["passed"],
        "overlay_envelope_passes": envelope["passed"],
        "overlay_drc_remains_exactly_13": r11_drc["violation_count"]
        == merged_drc["violation_count"]
        == 13,
        "overlay_violation_identity_exact": source_fingerprints == merged_fingerprints,
        "overlay_unconnected_reduction_exactly_3": r11_drc["unconnected_count"]
        - merged_drc["unconnected_count"]
        == 3,
        "overlay_pwr_button_n_3_to_0": source_nets.get("/PWR_BUTTON_N", 0) == 3
        and merged_nets.get("/PWR_BUTTON_N", 0) == 0,
        "overlay_other_net_unconnected_unchanged": not other_net_drift,
        "overlay_schematic_parity_zero": r11_drc["schematic_parity_count"]
        == merged_drc["schematic_parity_count"]
        == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "lineage": {
            key: {"path": str(path.resolve()), "sha256": expected, "matched": lineage_checks[key]}
            for key, (path, expected) in lineage.items()
        },
        "pwr_button_n_delta": {
            "added_count": len(pwr_added),
            "removed_count": len(pwr_removed),
            "added_by_net": dict(sorted(pwr_added_by_net.items())),
            "added_uuids": sorted(pwr_added),
            "removed_uuids": sorted(pwr_removed),
        },
        "r11_ps_hold_delta": {
            "added_count": len(ps_added),
            "removed_count": len(ps_removed),
            "added_by_net": dict(sorted(ps_added_by_net.items())),
            "removed_by_net": dict(sorted(ps_removed_by_net.items())),
            "added_uuids": sorted(ps_added),
            "removed_uuids": sorted(ps_removed),
        },
        "uuid_intersection": sorted(pwr_added & ps_added),
        "temporary_direct_overlay": {
            "published": False,
            "r11_source_drc": r11_drc["violation_count"],
            "merged_drc": merged_drc["violation_count"],
            "r11_source_unconnected": r11_drc["unconnected_count"],
            "merged_unconnected": merged_drc["unconnected_count"],
            "new_violation_count": len(set(merged_fingerprints) - set(source_fingerprints)),
            "lost_violation_count": len(set(source_fingerprints) - set(merged_fingerprints)),
            "other_net_unconnected_drift": other_net_drift,
            "preexisting_uuid_intersection": preexisting_intersection,
            "source_preservation": preservation,
            "route_envelope": envelope,
        },
    }


def postprocess_report(result: int, script_hash_before: str) -> None:
    if not REPORT_JSON.is_file():
        raise RouteError("template did not produce a route report")
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    script_hash_after = sha256_file(Path(__file__).resolve())
    if script_hash_after != script_hash_before:
        raise RouteError("builder changed while running")
    source_builder_hash = sha256_file(SOURCE_ROUTE_BUILDER)
    source_report_hash = sha256_file(SOURCE_ROUTE_REPORT)
    if source_builder_hash != SOURCE_ROUTE_BUILDER_SHA256:
        raise RouteError("DCDC source builder hash drift")
    if source_report_hash != SOURCE_ROUTE_REPORT_SHA256:
        raise RouteError("DCDC source report hash drift")

    cross_merge = r11_ps_hold_cross_merge_audit()
    passed = (
        result == 0
        and report.get("routing_checks_passed") is True
        and cross_merge["passed"]
    )
    preservation = report.get("source_preservation_audit", {})
    preservation_checks = preservation.get("checks", {})
    if isinstance(preservation_checks, dict):
        preservation_checks.pop("added_tracks_exactly_16", None)
        preservation_checks.pop("added_vias_exactly_4", None)
        preservation_checks[f"added_tracks_exactly_{EXPECTED_ADDED_TRACKS}"] = (
            preservation.get("added_track_count") == EXPECTED_ADDED_TRACKS
        )
        preservation_checks[f"added_vias_exactly_{EXPECTED_ADDED_VIAS}"] = (
            preservation.get("added_via_count") == EXPECTED_ADDED_VIAS
        )
    inherited_envelope = preservation.pop("r8e_boot_n_route_envelope", None)
    if inherited_envelope is not None:
        preservation["r8e_pwr_button_n_route_envelope"] = inherited_envelope
    report["mode"] = "STAGING_ONLY_ADDITIVE_SINGLE_NET_PWR_BUTTON_N"
    report["revision"] = "R8E_PWR_BUTTON_N_STAGING"
    report["state"] = (
        "R8E_PWR_BUTTON_N_ROUTED_CANDIDATE"
        if passed
        else "R8E_PWR_BUTTON_N_ROUTE_FAILED_HOLD"
    )
    report["routing_checks_passed"] = passed
    report["r11_ps_hold_cross_merge_audit"] = cross_merge
    report["builder"] = {
        "path": str(Path(__file__).resolve()),
        "sha256_before": script_hash_before,
        "sha256_after": script_hash_after,
        "unchanged": True,
        "template": {
            "path": str(BOOT_TEMPLATE.resolve()),
            "sha256": BOOT_TEMPLATE_SHA256,
        },
        "source_route_builder": {
            "path": str(SOURCE_ROUTE_BUILDER.resolve()),
            "sha256": SOURCE_ROUTE_BUILDER_SHA256,
        },
        "source_route_report": {
            "path": str(SOURCE_ROUTE_REPORT.resolve()),
            "sha256": SOURCE_ROUTE_REPORT_SHA256,
        },
    }
    if passed:
        gate = report["drc_gate"]
        scope = report["scope_audit"]
        report["completed_scope"] = ["/PWR_BUTTON_N"]
        report["routing_contract"] = {
            "allowed_nets": sorted(ALLOWED_NETS),
            "routing_uuid_seed": ROUTING_UUID_SEED,
            "new_copper": {
                "tracks": EXPECTED_ADDED_TRACKS,
                "vias": EXPECTED_ADDED_VIAS,
            },
            "layers": ["F.Cu", "In2.Cu"],
            "in1_signal_routing": "FORBIDDEN",
            "in2_routing_reason": (
                "SW2 NPTH at x=2.9 mm and the existing 0.8 mm-wide "
                "/EPD_SW_3V3 B.Cu trunk at x>=4.3 mm leave no reliable "
                "B.Cu passage; the untouched In2.Cu corridor at x=4.5 mm "
                "is used instead"
            ),
            "signal_width_mm": SIGNAL_WIDTH_MM,
            "via_diameter_mm": VIA_DIAMETER_MM,
            "via_drill_mm": VIA_DRILL_MM,
            "b2_boundary_y_mm": B2_BOTTOM_MM,
            "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
            "expected_drc": {"source": 13, "candidate": 13, "new": 0},
            "expected_unconnected": {
                "source": EXPECTED_SOURCE_UNCONNECTED,
                "candidate": EXPECTED_CANDIDATE_UNCONNECTED,
                "reduction": 3,
            },
            "all_four_contacts_one_connected_set": gate["checks"][
                "candidate_pwr_button_n_unconnected_zero"
            ],
            "dcdc_en_remains_connected": gate["checks"][
                "candidate_dcdc_en_unconnected_zero"
            ],
            "u3_escape": {
                "pad_6": "direct F.Cu escape below /STM_CSRD",
                "pad_2": (
                    "F.Cu centre-channel loop below U3; avoids the closed "
                    "/VSYS_RAW-to-/STM_VREF left-side corridor"
                ),
                "common_via_mm": [5.0, 80.4],
            },
        }
        report["seed_registry_audit"] = scope["seed_registry_audit"]
        report["uuid_collision_audit"] = scope["uuid_collision_audit"]
        report["holds"] = [
            {
                "scope": "/PS_HOLD",
                "reason": "separate controlled route scope; untouched",
            },
            {
                "scope": "EDGE_CONNECTORS_USB_TF_POWER_TRUNKS",
                "reason": "outside this single-net route scope",
            },
            {
                "scope": "WHOLE_BOARD",
                "reason": (
                    f"{report['candidate_drc']['unconnected_count']} other held "
                    "items remain; not manufacturing-ready"
                ),
            },
        ]
        artifact_paths = {
            "board": OUTPUT_BOARD,
            "candidate_drc_json": CANDIDATE_DRC_JSON,
            "source_drc_json": SOURCE_DRC_JSON,
            "board_verifier_json": BOARD_VERIFIER_JSON,
            "top_preview": TOP_PREVIEW,
            "bottom_preview": BOTTOM_PREVIEW,
            "front_copper_svg": FRONT_COPPER_SVG,
            "back_copper_svg": BACK_COPPER_SVG,
        }
        report["artifact_hashes"] = {
            key: {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for key, path in artifact_paths.items()
        }
    report_payload = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    REPORT_JSON.write_text(report_payload, encoding="utf-8")


def main() -> int:
    script_hash_before = sha256_file(Path(__file__).resolve())
    if sha256_file(BOOT_TEMPLATE) != BOOT_TEMPLATE_SHA256:
        raise RouteError("BOOT route template hash drift")
    configure_template()
    result = boot.main()
    postprocess_report(result, script_hash_before)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
