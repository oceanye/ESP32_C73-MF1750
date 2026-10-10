#!/usr/bin/env python3
"""Route only /UART0_RX and /UART0_TX on the frozen R12 staging PCB.

Operating mode: REVISION.  The R12 source is hash-bound and immutable.  This
builder adds deterministic 0.20 mm UART copper and 0.60/0.30 mm through-vias
only; footprints, zones, all source copper, formal design files, and project
documentation are protected.  Any DRC fingerprint, unrelated ratline, B2,
WROOM antenna, In1.Cu, or UUID-namespace drift fails closed.
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
import subprocess
import sys
import tempfile
import traceback
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

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r12_r11_user_key_2_n_routed.kicad_pcb"
SOURCE_SHA256 = "3a92f2aa31292032f38fcbae7152e67d20ef1cf50e0e619f6243faf3abe32ea3"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_routed.kicad_pcb"
REPORT_JSON = STAGING / "r14_r12_uart0_pair_route_report.json"
SOURCE_DRC_JSON = STAGING / "r14_r12_uart0_pair_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r14_r12_uart0_pair_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r14_r12_uart0_pair_board_verifier.json"
PREVIEW_DIR = STAGING / "r14_r12_uart0_pair_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_bottom.png"
ISO_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_iso.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"
UUID_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"

ROUTING_UUID_SEED = 1750911
ALLOWED_NETS = frozenset({"/UART0_RX", "/UART0_TX"})
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 66.0, 79.75, 114.0)
EXPECTED_SOURCE_COPPER = 1321
EXPECTED_ADDED_TRACKS = 12
EXPECTED_ADDED_VIAS = 7
EXPECTED_CANDIDATE_COPPER = 1340
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_OPEN = 112
EXPECTED_CANDIDATE_OPEN = 110

PAD_CONTRACT = (
    ("U1", "36", "/UART0_RX", 52.1800, 98.7500),
    ("TP29", "1", "/UART0_RX", 45.0000, 123.0000),
    ("U1", "37", "/UART0_TX", 53.4500, 98.7500),
    ("TP28", "1", "/UART0_TX", 61.0000, 120.0000),
)

# F.Cu is used only for pad/test-point escapes.  B.Cu carries the upper
# parallel trunks; each changes to In2.Cu before reaching the inherited
# EPD_FAULT_N diagonal.  TX does not move east of x=58.75 until y>114 mm.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/UART0_RX", "F.Cu", ((52.1800, 98.7500), (52.1800, 100.4000))),
    ("/UART0_RX", "B.Cu", ((52.1800, 100.4000), (52.1800, 110.0000))),
    (
        "/UART0_RX",
        "In2.Cu",
        ((52.1800, 110.0000), (52.1800, 121.4000), (46.5000, 121.4000), (46.5000, 123.0000)),
    ),
    ("/UART0_RX", "F.Cu", ((46.5000, 123.0000), (45.0000, 123.0000))),
    ("/UART0_TX", "F.Cu", ((53.4500, 98.7500), (53.4500, 101.2000))),
    ("/UART0_TX", "B.Cu", ((53.4500, 101.2000), (53.4500, 111.5000))),
    (
        "/UART0_TX",
        "In2.Cu",
        ((53.4500, 111.5000), (53.4500, 116.0000), (59.0000, 116.0000)),
    ),
    ("/UART0_TX", "B.Cu", ((59.0000, 116.0000), (61.0000, 118.5000))),
    ("/UART0_TX", "F.Cu", ((61.0000, 118.5000), (61.0000, 120.0000))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/UART0_RX", 52.1800, 100.4000),
    ("/UART0_RX", 52.1800, 110.0000),
    ("/UART0_RX", 46.5000, 123.0000),
    ("/UART0_TX", 53.4500, 101.2000),
    ("/UART0_TX", 53.4500, 111.5000),
    ("/UART0_TX", 59.0000, 116.0000),
    ("/UART0_TX", 61.0000, 118.5000),
)


class RouteError(RuntimeError):
    """Fail-closed UART pair route error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r7_utility():
    if not R7_UTILITY.is_file() or sha256_file(R7_UTILITY) != R7_UTILITY_SHA256:
        raise RouteError("R7 utility missing or hash-mismatched")
    spec = importlib.util.spec_from_file_location("_mf1750_r14_uart0_r7", R7_UTILITY)
    if spec is None or spec.loader is None:
        raise RouteError("could not import R7 utility")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.base.ALLOWED_NETS = ALLOWED_NETS
    return module


r7 = load_r7_utility()
base = r7.base


def point_in_rect(point, rect) -> bool:
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


def validate_source(board, before) -> dict[str, object]:
    pads = []
    for reference, number, net, x_mm, y_mm in PAD_CONTRACT:
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise RouteError(f"missing footprint {reference}")
        matches = [
            pad
            for pad in footprint.Pads()
            if pad.GetNumber() == number and base.point_mm(pad.GetPosition()) == (x_mm, y_mm)
        ]
        if len(matches) != 1 or matches[0].GetNetname() != net:
            raise RouteError(f"pad contract drift: {reference}.{number}@{(x_mm, y_mm)}")
        pads.append({"reference": reference, "pad": number, "net": net, "position_mm": [x_mm, y_mm]})
    source_net_counts = collections.Counter(signature[1] for signature in before["tracks"].values())
    checks = {
        "source_copper_count_1321": len(before["tracks"]) == EXPECTED_SOURCE_COPPER,
        "source_copper_uuid_unique": before["copper_uuid_audit"]["passed"] is True,
        "source_has_no_uart0_rx_copper": source_net_counts.get("/UART0_RX", 0) == 0,
        "source_has_no_uart0_tx_copper": source_net_counts.get("/UART0_TX", 0) == 0,
        "pad_contract_exact": len(pads) == len(PAD_CONTRACT),
    }
    if not all(checks.values()):
        raise RouteError("source contract failed: " + json.dumps(checks, sort_keys=True))
    return {"passed": True, "checks": checks, "pads": pads}


def add_routes(board) -> set[str]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added_ids: list[str] = []
    for net_name, layer, points in ROUTES:
        if net_name not in ALLOWED_NETS or layer == "In1.Cu":
            raise RouteError(f"forbidden route recipe: {net_name} on {layer}")
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


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not load fixed R12 source")
    before = base.source_state(board)
    source_contract = validate_source(board, before)
    added_ids = add_routes(board)
    collision = sorted(added_ids & set(before["tracks"]))
    if collision:
        raise RouteError(f"new UUID intersects R12 source: {collision}")
    if not pcbnew.SaveBoard(str(destination), board):
        raise RouteError(f"failed to save candidate: {destination}")
    return before, added_ids, source_contract


def known_branch_uuid_audit(added_ids: set[str]) -> dict[str, object]:
    evidence = []
    passed = True
    for path in sorted(STAGING.glob("*.kicad_pcb"), key=lambda item: item.name.lower()):
        if path.resolve() == OUTPUT_BOARD.resolve():
            continue
        board = pcbnew.LoadBoard(str(path))
        if board is None:
            passed = False
            evidence.append({"path": str(path), "load_failed": True, "passed": False})
            continue
        sibling_ids = set(base.source_state(board)["tracks"])
        intersection = sorted(added_ids & sibling_ids)
        item_passed = not intersection
        passed = passed and item_passed
        evidence.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "copper_uuid_count": len(sibling_ids),
                "intersection": intersection,
                "intersection_zero": not intersection,
                "passed": item_passed,
            }
        )
    return {
        "passed": passed,
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "new_uuid_count": len(added_ids),
        "audited_board_count": len(evidence),
        "boards": evidence,
    }


def preservation_and_envelope_audit(candidate, before, added_ids) -> dict[str, object]:
    after = base.source_state(candidate)
    source_ids = set(before["tracks"])
    candidate_ids = set(after["tracks"])
    extra_ids = candidate_ids - source_ids
    missing_source = sorted(source_ids - candidate_ids)
    changed_source = sorted(
        item_id for item_id in source_ids & candidate_ids if before["tracks"][item_id] != after["tracks"][item_id]
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
            if item.GetLayer() == base.layer_id(candidate, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y_value < B2_BOTTOM_MM for _, y_value in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    new_net_counts = collections.Counter(after["tracks"][item_id][1] for item_id in extra_ids)
    expected_new = {"/UART0_RX": 9, "/UART0_TX": 10}
    checks = {
        "all_source_copper_uuid_geometry_exact": not missing_source and not changed_source,
        "only_deterministic_added_ids": not unexpected_extra and not missing_added,
        "new_uuid_intersection_with_source_zero": not (added_ids & source_ids),
        "candidate_copper_uuid_unique": after["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_count_1340": len(after["tracks"]) == EXPECTED_CANDIDATE_COPPER,
        "added_track_count_12": sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids) == EXPECTED_ADDED_TRACKS,
        "added_via_count_7": sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in extra_ids) == EXPECTED_ADDED_VIAS,
        "new_copper_only_uart0_pair": dict(sorted(new_net_counts.items())) == expected_new,
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
        "new_net_counts": dict(sorted(new_net_counts.items())),
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
    checks = {
        "source_violation_count_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_violation_count_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_identity_exact": violation_identity(source["raw"]) == violation_identity(candidate["raw"]),
        "source_open_112": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_110": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_2": source["unconnected_count"] - candidate["unconnected_count"] == 2,
        "source_uart0_rx_open_1": source_nets.get("/UART0_RX", 0) == 1,
        "source_uart0_tx_open_1": source_nets.get("/UART0_TX", 0) == 1,
        "candidate_uart0_rx_open_0": candidate_nets.get("/UART0_RX", 0) == 0,
        "candidate_uart0_tx_open_0": candidate_nets.get("/UART0_TX", 0) == 0,
        "dcdc_en_remains_0": candidate_nets.get("/DCDC_EN", 0) == 0,
        "boot_n_remains_0": candidate_nets.get("/BOOT_N", 0) == 0,
        "ps_hold_remains_0": candidate_nets.get("/PS_HOLD", 0) == 0,
        "user_key_2_n_remains_0": candidate_nets.get("/USER_KEY_2_N", 0) == 0,
        "all_other_net_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_drift": other_drift,
        "source_violation_identity": violation_identity(source["raw"]),
        "candidate_violation_identity": violation_identity(candidate["raw"]),
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mf1750-r14-uart0-iso-") as name:
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


def protected_hashes() -> dict[str, str | None]:
    paths = (
        SOURCE_BOARD, R7_UTILITY, FORMAL_BOARD, FORMAL_SCHEMATIC, FORMAL_PROJECT,
        ROOT_README, B3_README, STATUS_HANDOFF, UUID_REGISTRY,
    )
    return {str(path.resolve()): sha256_file(path) if path.is_file() else None for path in paths}


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-python", type=Path, default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    protected_before = protected_hashes()
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("fixed R12 source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r14-uart0-") as name:
            temporary = Path(name)
            first = temporary / "first.kicad_pcb"
            second = temporary / "second.kicad_pcb"
            before, added_ids, source_contract = build_candidate(first)
            before2, added_ids2, source_contract2 = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and before == before2
                and added_ids == added_ids2
                and source_contract == source_contract2
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            candidate = pcbnew.LoadBoard(str(first))
            if candidate is None:
                raise RouteError("saved candidate failed reload")
            preservation = preservation_and_envelope_audit(candidate, before, added_ids)
            namespace = known_branch_uuid_audit(added_ids)
            if not preservation["passed"] or not namespace["passed"]:
                raise RouteError("source preservation, envelope, or UUID namespace audit failed")
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
        iso = render_isometric(kicad_cli)
        protected_after = protected_hashes()
        protected_unchanged = protected_before == protected_after
        passed = preservation["passed"] and namespace["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_UART0_PAIR_ROUTE",
            "revision": "R14_R12_UART0_PAIR_STAGING",
            "state": "R14_R12_UART0_PAIR_ROUTED_CANDIDATE" if passed else "R14_R12_UART0_PAIR_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "routing_checks_passed": passed,
            "locally_verified": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "source": {"role": "sole_editable_PCB_geometry_source", "path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256},
            "builder": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve()), "routing_uuid_seed": ROUTING_UUID_SEED, "r7_utility": {"path": str(R7_UTILITY), "sha256": R7_UTILITY_SHA256}},
            "output": {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)},
            "determinism": {"double_build_byte_identical": deterministic, "first_sha256": build_sha, "second_sha256": build_sha},
            "source_contract": source_contract,
            "source_preservation_and_envelope_audit": preservation,
            "known_branch_uuid_namespace_audit": namespace,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_connectivity_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "protected_sources": {"unchanged": protected_unchanged, "before": protected_before, "after": protected_after},
            "completed_scope": sorted(ALLOWED_NETS) if passed else [],
            "inherited_completed_scope": ["/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/USER_KEY_2_N"] if passed else [],
            "holds": [{"scope": "WHOLE_BOARD", "reason": f"{candidate_drc['unconnected_count']} unrelated/held items remain; not manufacturing-ready"}],
            "artifacts": {"source_drc_json": str(SOURCE_DRC_JSON), "candidate_drc_json": str(CANDIDATE_DRC_JSON), "board_verifier_json": str(BOARD_VERIFIER_JSON), "top_preview": str(TOP_PREVIEW), "bottom_preview": str(BOTTOM_PREVIEW), "isometric_preview": iso, "front_copper_svg": str(FRONT_COPPER_SVG), "back_copper_svg": str(BACK_COPPER_SVG), "render_export": renders},
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"state": report["state"], "routing_checks_passed": passed, "output": report["output"], "drc": {"source": source_drc["violation_count"], "candidate": candidate_drc["violation_count"], "source_open": source_drc["unconnected_count"], "candidate_open": candidate_drc["unconnected_count"], "gate_passed": gate["passed"]}, "verifier": verifier["summary"], "report": str(REPORT_JSON)}, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except Exception as exc:
        failure = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_UART0_PAIR_ROUTE",
            "revision": "R14_R12_UART0_PAIR_STAGING",
            "state": "R14_R12_UART0_PAIR_ROUTE_FAILED",
            "overall_status": "HOLD",
            "routing_checks_passed": False,
            "locally_verified": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "protected_sources_before": protected_before,
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
