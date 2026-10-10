#!/usr/bin/env python3
"""Build the staging-only /BOOT_N R8e route from the frozen DCDC_EN board.

This is an additive, single-net REVISION builder.  It joins both SW4 pad-1
contacts, R53.2, and U1.27 without moving footprints or editing any source
copper.  Only F.Cu and B.Cu are used; B2, In1.Cu, the WROOM antenna keepout,
and the separately controlled U3/PS_HOLD reroute area remain untouched.
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
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_boot_n_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8e_boot_n_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8e_boot_n_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8e_boot_n_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8e_boot_n_board_verifier.json"
PREVIEW_DIR = STAGING / "r8e_boot_n_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_boot_n_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_boot_n_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_boot_n_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8e_boot_n_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"

ROUTING_UUID_SEED = 1750861
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
U3_PS_HOLD_CONTROLLED_AREA = (7.5, 75.5, 14.5, 84.0)
EXPECTED_SOURCE_COPPER = 1263
EXPECTED_ADDED_TRACKS = 16
EXPECTED_ADDED_VIAS = 4
EXPECTED_CANDIDATE_COPPER = 1283
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_UNCONNECTED = 120
EXPECTED_CANDIDATE_UNCONNECTED = 117
ALLOWED_NETS = frozenset({"/BOOT_N"})

PAD_CONTRACT = (
    ("SW4", "1", "/BOOT_N", 1.3500, 86.7000),
    ("SW4", "1", "/BOOT_N", 1.3500, 90.3000),
    ("R53", "2", "/BOOT_N", 36.8250, 96.5000),
    ("U1", "27", "/BOOT_N", 40.7500, 98.7500),
)

# SW4's two contacts are joined by a short F.Cu weave between its two NPTH
# mounting holes.  The B.Cu trunk stops before C36; a local F.Cu bridge then
# passes below C36 and returns to B.Cu in the gap between the existing
# USB_INPUT_VALID_N and EPD_FAULT routes.  The final F.Cu leg passes through
# R53.2 and reaches U1.27 above the lower resistor row.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    (
        "/BOOT_N",
        "F.Cu",
        (
            (1.3500, 86.7000),
            (1.3500, 87.4000),
            (2.0000, 88.0500),
            (2.0000, 88.9500),
            (1.3500, 89.6000),
            (1.3500, 90.3000),
            (1.3500, 92.0000),
            (4.0000, 94.2000),
        ),
    ),
    ("/BOOT_N", "B.Cu", ((4.0000, 94.2000), (25.3500, 94.2000))),
    (
        "/BOOT_N",
        "F.Cu",
        ((25.3500, 94.2000), (25.3500, 94.8000), (29.4000, 94.8000), (30.8000, 95.0800)),
    ),
    ("/BOOT_N", "B.Cu", ((30.8000, 95.0800), (36.8250, 95.0800))),
    (
        "/BOOT_N",
        "F.Cu",
        ((36.8250, 95.0800), (36.8250, 96.5000), (36.8250, 99.7000), (40.7500, 99.7000), (40.7500, 98.7500)),
    ),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/BOOT_N", 4.0000, 94.2000),
    ("/BOOT_N", 25.3500, 94.2000),
    ("/BOOT_N", 30.8000, 95.0800),
    ("/BOOT_N", 36.8250, 95.0800),
)


class RouteError(RuntimeError):
    """Fail-closed R8e BOOT_N route-builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r7_utility():
    if not R7_UTILITY.is_file() or sha256_file(R7_UTILITY) != R7_UTILITY_SHA256:
        raise RouteError(f"R7 utility missing or hash-mismatched: {R7_UTILITY}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8e_boot_n_r7_utility", R7_UTILITY)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R7 utility import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.base.ALLOWED_NETS = ALLOWED_NETS
    return module


r7 = load_r7_utility()
base = r7.base


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


def validate_scope(board) -> dict[str, object]:
    refs: set[str] = set()
    actual_pads: list[tuple[str, str, str, float, float]] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != "/BOOT_N":
                continue
            refs.add(footprint.GetReference())
            x_mm, y_mm = base.point_mm(pad.GetPosition())
            actual_pads.append(
                (footprint.GetReference(), pad.GetNumber(), pad.GetNetname(), x_mm, y_mm)
            )
    expected = sorted(PAD_CONTRACT)
    actual = sorted(actual_pads)
    if len(actual) != len(expected):
        raise RouteError(f"BOOT_N pad-count drift: actual={actual}")
    for got, wanted in zip(actual, expected, strict=True):
        if got[:3] != wanted[:3] or any(abs(a - b) > 0.000002 for a, b in zip(got[3:], wanted[3:], strict=True)):
            raise RouteError(f"BOOT_N pad contract drift: got={got}, expected={wanted}")
    if refs != {"SW4", "R53", "U1"}:
        raise RouteError(f"BOOT_N endpoint reference drift: {sorted(refs)}")
    mechanical_dependency = sorted(
        ref for ref in refs if ref in {"J4", "J5", "J6"} or (ref.startswith("SW") and ref != "SW4")
    )
    if mechanical_dependency:
        raise RouteError(f"unexpected mechanical dependency: {mechanical_dependency}")
    return {
        "passed": True,
        "net": "/BOOT_N",
        "endpoint_references": sorted(refs),
        "pad_contract": [
            {"reference": ref, "pad": pad, "net": net, "position_mm": [x_mm, y_mm]}
            for ref, pad, net, x_mm, y_mm in actual
        ],
        "connected_set_required": ["SW4.1@86.7", "SW4.1@90.3", "R53.2", "U1.27"],
        "mechanical_dependency_references": mechanical_dependency,
    }


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net, layer, points in ROUTES:
        if net not in ALLOWED_NETS or layer not in {"F.Cu", "B.Cu"}:
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


def envelope_audit(board, added_ids: set[str]) -> dict[str, object]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    findings: dict[str, list[str]] = {
        "non_allowlisted_net": [],
        "b2": [],
        "antenna": [],
        "in1": [],
        "u3_ps_hold_controlled_area": [],
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
            controlled_hit = point_in_rect(points[0], U3_PS_HOLD_CONTROLLED_AREA)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
            controlled_hit = segment_hits_rect(points[0], points[1], U3_PS_HOLD_CONTROLLED_AREA)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
        if controlled_hit:
            findings["u3_ps_hold_controlled_area"].append(item_id)
    checks = {
        "new_copper_net_whitelist_boot_n_only": not findings["non_allowlisted_net"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_wroom_antenna_keepout": not findings["antenna"],
        "no_signal_track_on_in1": not findings["in1"],
        "no_new_copper_in_u3_ps_hold_controlled_area": not findings["u3_ps_hold_controlled_area"],
        "all_new_tracks_exactly_0p20_mm": not findings["bad_width"],
        "all_new_vias_exactly_0p60_0p30_mm": not findings["bad_via"],
    }
    return {"passed": all(checks.values()), "checks": checks, "findings": findings}


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not parse the fixed R8d source")
    scope = validate_scope(board)
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
    return before, added_ids, scope


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names = []
        for item in entry.get("items", []):
            names.extend(re.findall(r"\[([^\]]+)\]", str(item.get("description", ""))))
        unique = {name for name in names if name}
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
    # Preserve explicit zero evidence for the completed source DCDC_EN route
    # and the newly completed BOOT_N route instead of relying on absent keys.
    for net in ("/BOOT_N", "/DCDC_EN"):
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fingerprints = violation_fingerprints(source["raw"])
    candidate_fingerprints = violation_fingerprints(candidate["raw"])
    checks = {
        "source_drc_exactly_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_drc_exactly_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_uuid_position_identity_exact": source_fingerprints == candidate_fingerprints,
        "source_unconnected_exactly_120": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_117": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_3": source["unconnected_count"] - candidate["unconnected_count"] == 3,
        "source_boot_n_unconnected_exactly_3": source_nets.get("/BOOT_N", 0) == 3,
        "candidate_boot_n_unconnected_zero": candidate_nets.get("/BOOT_N", 0) == 0,
        "source_dcdc_en_unconnected_zero": source_nets.get("/DCDC_EN", 0) == 0,
        "candidate_dcdc_en_unconnected_zero": candidate_nets.get("/DCDC_EN", 0) == 0,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
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
            raise RouteError("fixed R8d DCDC_EN source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))

        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r8e-boot-n-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, scope = build_candidate(first)
            before2, added_ids2, scope2 = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and before == before2
                and added_ids == added_ids2
                and scope == scope2
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            reloaded = pcbnew.LoadBoard(str(first))
            if reloaded is None:
                raise RouteError("saved candidate failed reload")
            preservation = base.audit_candidate(reloaded, before, added_ids)
            envelope = envelope_audit(reloaded, added_ids)
            preservation["r8e_boot_n_route_envelope"] = envelope
            preservation["checks"]["source_copper_count_exactly_1263"] = (
                preservation["source_copper_count"] == EXPECTED_SOURCE_COPPER
            )
            preservation["checks"]["added_tracks_exactly_16"] = (
                preservation["added_track_count"] == EXPECTED_ADDED_TRACKS
            )
            preservation["checks"]["added_vias_exactly_4"] = (
                preservation["added_via_count"] == EXPECTED_ADDED_VIAS
            )
            preservation["passed"] = all(preservation["checks"].values()) and envelope["passed"]
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
        passed = preservation["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_BOOT_N",
            "revision": "R8E_BOOT_N_STAGING",
            "state": "R8E_BOOT_N_ROUTED_CANDIDATE" if passed else "R8E_BOOT_N_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": passed,
            "inputs": {
                "source": {
                    "role": "sole_PCB_geometry_source",
                    "path": str(SOURCE_BOARD.resolve()),
                    "sha256": SOURCE_SHA256,
                },
                "r7_utility": {"path": str(R7_UTILITY.resolve()), "sha256": R7_UTILITY_SHA256},
            },
            "output": {
                "path": str(OUTPUT_BOARD),
                "bytes": OUTPUT_BOARD.stat().st_size,
                "sha256": sha256_file(OUTPUT_BOARD),
            },
            "builder": {"path": str(Path(__file__).resolve())},
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
            "routing_contract": {
                "allowed_nets": sorted(ALLOWED_NETS),
                "new_copper": {"tracks": EXPECTED_ADDED_TRACKS, "vias": EXPECTED_ADDED_VIAS},
                "layers": ["F.Cu", "B.Cu"],
                "in1_signal_routing": "FORBIDDEN",
                "signal_width_mm": SIGNAL_WIDTH_MM,
                "via_diameter_mm": VIA_DIAMETER_MM,
                "via_drill_mm": VIA_DRILL_MM,
                "b2_boundary_y_mm": B2_BOTTOM_MM,
                "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
                "u3_ps_hold_controlled_area_mm": list(U3_PS_HOLD_CONTROLLED_AREA),
                "expected_drc": {"source": 13, "candidate": 13, "new": 0},
                "expected_unconnected": {"source": 120, "candidate": 117, "reduction": 3},
                "all_four_boot_n_contacts_one_connected_set": gate["checks"]["candidate_boot_n_unconnected_zero"],
                "dcdc_en_remains_connected": gate["checks"]["candidate_dcdc_en_unconnected_zero"],
            },
            "source_preservation_audit": preservation,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": ["/BOOT_N"] if passed else [],
            "holds": [
                {"scope": "/PS_HOLD", "reason": "separate controlled reroute scope; untouched"},
                {"scope": "EDGE_CONNECTORS_USB_TF_POWER_TRUNKS", "reason": "outside this single-net route scope"},
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
                    "routing_checks_passed": passed,
                    "output": report["output"],
                    "drc": {
                        "source_violations": source_drc["violation_count"],
                        "candidate_violations": candidate_drc["violation_count"],
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
        return 0 if passed else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_BOOT_N",
            "revision": "R8E_BOOT_N_STAGING",
            "state": "R8E_BOOT_N_ROUTE_FAILED",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": False,
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
