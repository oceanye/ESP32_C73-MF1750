#!/usr/bin/env python3
"""Route only /PWR_INT_N from frozen R8b into an isolated R8c PCB."""

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
R8B_SCRIPT = HARDWARE / "route_mf1750_wroom_b3_dcdc_pg_r8b.py"
R8B_SCRIPT_SHA256 = "6f595cf24445394e6beb9b1f5047ecaf0faab542facda19bf3a6b9e67d33b15b"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8b_dcdc_pg_routed.kicad_pcb"
SOURCE_SHA256 = "a07aede19ece6e805b9510baa28435c52b40570cc45d7082645c9bf6d93e3269"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8c_pwr_int_n_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8c_pwr_int_n_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8c_pwr_int_n_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8c_pwr_int_n_board_verifier.json"
PREVIEW_DIR = STAGING / "r8c_pwr_int_n_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8c_pwr_int_n_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
README = ROOT / "README.md"
R8A_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8a_internal_control_routed.kicad_pcb"
R7_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"

ROUTING_UUID_SEED = 1750831
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_UNCONNECTED = 126
EXPECTED_CANDIDATE_UNCONNECTED = 125
ALLOWED_NETS = frozenset({"/PWR_INT_N"})

PAD_CONTRACT = {
    ("U3", "11"): ("/PWR_INT_N", 11.8000, 77.7500),
    ("U1", "23"): ("/PWR_INT_N", 39.5000, 93.1750),
}

# The B.Cu route crosses to the right of the SYS_3V3 riser before that riser
# starts, while weaving above the immutable GND/SYS/DCDC_PG vias.  A private
# In2 lane at x=38.8 clears the three R7 EPD signal vias at x=38.0 and reaches
# U1 through one short F.Cu pad escape.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/PWR_INT_N", "B.Cu", ((20.8250, 81.1000), (20.8250, 80.1000), (29.8000, 80.1000), (31.8000, 80.5000), (32.0000, 81.3000), (38.8000, 81.3000))),
    ("/PWR_INT_N", "In2.Cu", ((38.8000, 81.3000), (38.8000, 93.1750))),
    ("/PWR_INT_N", "F.Cu", ((38.8000, 93.1750), (39.5000, 93.1750))),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/PWR_INT_N", 38.8000, 81.3000),
    ("/PWR_INT_N", 38.8000, 93.1750),
)


class RouteError(RuntimeError):
    """Fail-closed R8c builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r8b():
    if not R8B_SCRIPT.is_file() or sha256_file(R8B_SCRIPT) != R8B_SCRIPT_SHA256:
        raise RouteError(f"R8b utility missing or hash-mismatched: {R8B_SCRIPT}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8c_r8b_util", R8B_SCRIPT)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R8b utility import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ALLOWED_NETS = ALLOWED_NETS
    module.base.ALLOWED_NETS = ALLOWED_NETS
    module.r8a.ALLOWED_NETS = ALLOWED_NETS
    return module


r8b = load_r8b()
base = r8b.base


def validate_scope(board) -> dict[str, object]:
    refs: set[str] = set()
    evidence = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() in ALLOWED_NETS:
                refs.add(footprint.GetReference())
    forbidden = sorted(ref for ref in refs if ref in {"J4", "J5", "J6"} or ref.startswith("SW"))
    if forbidden:
        raise RouteError(f"PWR_INT_N unexpectedly touches mechanical references: {forbidden}")
    for (ref, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = base.find_numbered_pad(board, ref, number)
        actual = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or any(abs(got - expected) > 0.000002 for got, expected in zip(actual, (x_mm, y_mm), strict=True)):
            raise RouteError(f"pad contract drift {ref}.{number}: {pad.GetNetname()}@{actual}")
        evidence.append({"ref": ref, "pad": number, "net": net, "position_mm": list(actual)})
    return {"passed": True, "net": "/PWR_INT_N", "refs": sorted(refs), "mechanical_dependency_refs": forbidden, "pad_contract": evidence}


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net, layer, points in ROUTES:
        if net not in ALLOWED_NETS or layer == "In1.Cu":
            raise RouteError(f"route violates allowlist/layer contract: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end))
    for net, x_mm, y_mm in VIAS:
        added.append(base.add_via(board, net, x_mm, y_mm))
    return added


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    if board is None:
        raise RouteError("KiCad could not parse fixed R8b source")
    scope = validate_scope(board)
    before = base.source_state(board)
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
        unique = set(name for name in names if name)
        counts[next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"] += 1
    return dict(sorted(counts.items()))


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    increases = {name: candidate_categories[name] - source_categories.get(name, 0) for name in sorted(candidate_categories) if candidate_categories[name] > source_categories.get(name, 0)}
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    others = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)} for net in sorted(others) if source_nets.get(net, 0) != candidate_nets.get(net, 0)}
    checks = {
        "source_unconnected_exactly_126": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_125": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_1": source["unconnected_count"] - candidate["unconnected_count"] == 1,
        "source_pwr_int_n_unconnected_exactly_1": source_nets.get("/PWR_INT_N", 0) == 1,
        "candidate_pwr_int_n_unconnected_zero": candidate_nets.get("/PWR_INT_N", 0) == 0,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "fatal_drc_category_delta_zero": not increases,
        "no_new_track_dangling": candidate_categories.get("track_dangling", 0) <= source_categories.get("track_dangling", 0),
    }
    return {"passed": all(checks.values()), "checks": checks, "violation_category_increases": increases, "source_categories": dict(sorted(source_categories.items())), "candidate_categories": dict(sorted(candidate_categories.items())), "source_unconnected_by_net": source_nets, "candidate_unconnected_by_net": candidate_nets, "other_net_unconnected_drift": other_drift}


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-python", type=Path, default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    protected_paths = {"formal_board": FORMAL_BOARD, "formal_schematic": FORMAL_SCHEMATIC, "formal_project": FORMAL_PROJECT, "readme": README, "r7_board": R7_BOARD, "r8a_board": R8A_BOARD, "r8b_source_board": SOURCE_BOARD, "r8b_builder": R8B_SCRIPT}
    protected_before = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("fixed R8b source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r8c-pwr-int-") as name:
            temp_dir = Path(name)
            first, second = temp_dir / "first.kicad_pcb", temp_dir / "second.kicad_pcb"
            before, added_ids, scope = build_candidate(first)
            before2, added_ids2, scope2 = build_candidate(second)
            deterministic = first.read_bytes() == second.read_bytes() and before == before2 and added_ids == added_ids2 and scope == scope2
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            build_sha = sha256_file(first)
            board = pcbnew.LoadBoard(str(first))
            if board is None:
                raise RouteError("saved candidate failed reload")
            preservation = base.audit_candidate(board, before, added_ids)
            envelope = r8b.r8a.envelope_audit(board, added_ids)
            preservation["r8c_route_envelope"] = envelope
            preservation["passed"] = preservation["passed"] and envelope["passed"]
            if not preservation["passed"]:
                raise RouteError("source/envelope preservation audit failed")
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)
        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        gate = drc_gate(source_drc, candidate_drc)
        verifier = r8b.r8a.r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)
        SOURCE_DRC_JSON.write_text(json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CANDIDATE_DRC_JSON.write_text(json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        BOARD_VERIFIER_JSON.write_text(json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        renders = [base.render(kicad_cli, OUTPUT_BOARD, TOP_PREVIEW, "top"), base.render(kicad_cli, OUTPUT_BOARD, BOTTOM_PREVIEW, "bottom"), base.export_svg(kicad_cli, OUTPUT_BOARD, FRONT_COPPER_SVG, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"), base.export_svg(kicad_cli, OUTPUT_BOARD, BACK_COPPER_SVG, "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts", mirror=True)]
        protected_after = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
        protected_unchanged = protected_before == protected_after
        passed = preservation["passed"] and gate["passed"] and verifier["passed"] and protected_unchanged
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_PWR_INT_N", "state": "R8C_PWR_INT_N_ROUTED_CANDIDATE" if passed else "R8C_PWR_INT_N_HOLD", "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD", "operation_completed": True, "hardware_accessed": False, "locally_verified": False, "routing_checks_passed": passed, "kicad_version": str(pcbnew.GetBuildVersion()),
            "inputs": {"source": {"path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256}, "r8b_builder": {"path": str(R8B_SCRIPT), "sha256": R8B_SCRIPT_SHA256}}, "output": {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)}, "determinism": {"double_build_byte_identical": deterministic, "first_sha256": build_sha, "second_sha256": build_sha}, "protected_sources": {"unchanged": protected_unchanged, "before": protected_before, "after": protected_after}, "scope_audit": scope,
            "routing_contract": {"allowed_nets": sorted(ALLOWED_NETS), "layers": ["F.Cu", "B.Cu", "In2.Cu"], "in1_signal_routing": "FORBIDDEN", "signal_width_mm": SIGNAL_WIDTH_MM, "via_diameter_mm": VIA_DIAMETER_MM, "via_drill_mm": VIA_DRILL_MM, "b2_boundary_y_mm": B2_BOTTOM_MM, "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT), "expected_unconnected": {"source": 126, "candidate": 125, "reduction": 1}},
            "source_preservation_audit": preservation, "source_drc": {key: value for key, value in source_drc.items() if key != "raw"}, "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"}, "drc_gate": gate, "board_verifier": {key: value for key, value in verifier.items() if key != "raw"}, "completed_scope": ["/PWR_INT_N"] if passed else [], "holds": [{"scope": "OTHER_INTERNAL_CONTROL_NETS", "nets": ["/DCDC_EN", "/PS_HOLD"], "reason": "not part of this single-net candidate"}, {"scope": "WHOLE_BOARD", "reason": f"{candidate_drc['unconnected_count']} unrelated/held items remain; not manufacturing-ready"}], "artifacts": {"source_drc_json": str(SOURCE_DRC_JSON), "candidate_drc_json": str(CANDIDATE_DRC_JSON), "board_verifier_json": str(BOARD_VERIFIER_JSON), "top_preview": str(TOP_PREVIEW), "bottom_preview": str(BOTTOM_PREVIEW), "front_copper_svg": str(FRONT_COPPER_SVG), "back_copper_svg": str(BACK_COPPER_SVG), "render_export": renders},
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"state": report["state"], "routing_checks_passed": passed, "output": report["output"], "drc": {"source_unconnected": source_drc["unconnected_count"], "candidate_unconnected": candidate_drc["unconnected_count"], "gate_passed": gate["passed"], "categories": gate["candidate_categories"]}, "board_verifier": verifier["summary"], "report": str(REPORT_JSON)}, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except Exception as exc:
        report = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_PWR_INT_N", "state": "R8C_PWR_INT_N_ROUTE_FAILED", "overall_status": "HOLD", "operation_completed": False, "hardware_accessed": False, "locally_verified": False, "routing_checks_passed": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(), "source": str(SOURCE_BOARD), "protected_sources_before": protected_before}
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
