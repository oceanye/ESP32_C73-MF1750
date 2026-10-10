#!/usr/bin/env python3
"""Route the reviewed internal low-speed control nets into an isolated R8 PCB.

The builder is intentionally additive and fail closed.  It starts from the
hash-bound, fully verified R7 EPD/MCU routed candidate and closes only the
lowest-risk first slice: the internal USB-input-valid GPIO island to U1.24.
The four harder internal nets remain explicit HOLD for a later R8b.  Edge
connectors, switches/buttons, USB D+/D-, TF signal routing, power trunks, the
B2 protected region, WROOM antenna keepout, and In1.Cu are outside this scope.
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
R7_SCRIPT = HARDWARE / "route_mf1750_wroom_b3_epd_mcu_r7.py"
R7_SCRIPT_SHA256 = "9f5add51e5e220bd4ddb02692ac6b2efb9039bdea090932c53b9ff71a3232a82"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"
SOURCE_SHA256 = "adf3a61c2231049f4a50b6ba97d95d5bd7b7fe9ff54be3f27469eb3f78cdc009"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8a_internal_control_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8a_internal_control_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8a_internal_control_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8a_internal_control_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8a_internal_control_board_verifier.json"
PREVIEW_DIR = STAGING / "r8a_internal_control_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8a_internal_control_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8a_internal_control_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8a_internal_control_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8a_internal_control_back.svg"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
README = ROOT / "README.md"
R6_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r6_epd_boundary_routed.kicad_pcb"
R7_HYGIENE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"

ROUTING_UUID_SEED = 1750811
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_UNCONNECTED = 128
EXPECTED_CANDIDATE_UNCONNECTED = 127
EXPECTED_REDUCTION = 1

ALLOWED_NETS = frozenset({"/USB_INPUT_VALID_N"})
DEFERRED_NETS = {
    "/DCDC_EN": {"source_unconnected": 3, "reason": "deferred after multi-net probe created DRC conflicts"},
    "/DCDC_PG": {"source_unconnected": 1, "reason": "deferred to an independently gated R8b"},
    "/PWR_INT_N": {"source_unconnected": 1, "reason": "deferred after B.Cu/In2 corridor conflict"},
    "/PS_HOLD": {"source_unconnected": 2, "reason": "deferred after dense U3-to-R60 corridor conflict"},
}
MECHANICAL_DEPENDENCY_REFS = frozenset({"J4", "J5", "J6"})

PAD_CONTRACT: dict[tuple[str, str], tuple[str, float, float]] = {
    ("U1", "24"): ("/USB_INPUT_VALID_N", 39.5000, 94.4450),
}

# Each route is (net, layer, ordered points); each segment is exactly 0.20 mm.
# F.Cu is used only for short pad escapes.  Long routes use B.Cu or In2.Cu.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    # USB_INPUT_VALID_N is an internal validity GPIO, not USB D+/D- routing.
    # It extends the already present internal island without entering J4/J5.
    ("/USB_INPUT_VALID_N", "B.Cu", ((28.0000, 105.0000), (27.5000, 105.0000), (27.5000, 94.4450), (41.0000, 94.4450))),
    ("/USB_INPUT_VALID_N", "F.Cu", ((41.0000, 94.4450), (39.5000, 94.4450))),

)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/USB_INPUT_VALID_N", 41.0000, 94.4450),
)


class RouteError(RuntimeError):
    """Fail-closed R8 route builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_r7():
    if not R7_SCRIPT.is_file() or sha256_file(R7_SCRIPT) != R7_SCRIPT_SHA256:
        raise RouteError(f"R7 utility missing or hash-mismatched: {R7_SCRIPT}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8_r7_util", R7_SCRIPT)
    if spec is None or spec.loader is None:
        raise RouteError("could not create R7 utility import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.base.ALLOWED_NETS = ALLOWED_NETS
    return module


r7 = load_r7()
base = r7.base


def validate_pad_and_scope_contract(board) -> dict[str, object]:
    pads = []
    refs_by_net: dict[str, set[str]] = {net: set() for net in ALLOWED_NETS}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        for pad in footprint.Pads():
            net = pad.GetNetname()
            if net in ALLOWED_NETS:
                refs_by_net[net].add(ref)
    excluded = {
        net: sorted(refs)
        for net, refs in refs_by_net.items()
        if refs & MECHANICAL_DEPENDENCY_REFS or any(ref.startswith("SW") for ref in refs)
    }
    if excluded:
        raise RouteError(f"scope touches mechanical-dependency references: {excluded}")
    for (ref, number), (net, x_mm, y_mm) in PAD_CONTRACT.items():
        pad = base.find_numbered_pad(board, ref, number)
        actual = base.point_mm(pad.GetPosition())
        if pad.GetNetname() != net or any(
            abs(got - expected) > 0.000002
            for got, expected in zip(actual, (x_mm, y_mm), strict=True)
        ):
            raise RouteError(
                f"pad contract drift {ref}.{number}: {pad.GetNetname()}@{actual}, "
                f"expected {net}@{(x_mm, y_mm)}"
            )
        pads.append({"ref": ref, "pad": number, "net": net, "position_mm": list(actual)})
    return {
        "passed": True,
        "refs_by_net": {net: sorted(refs) for net, refs in sorted(refs_by_net.items())},
        "mechanical_dependency_refs_forbidden": sorted(MECHANICAL_DEPENDENCY_REFS) + ["SW*"],
        "mechanical_dependent_nets_removed": [],
        "pad_contract": pads,
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
    x, y = point
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def segment_hits_rect(start, end, rect) -> bool:
    x0, y0, x1, y1 = rect
    xa, ya = start
    xb, yb = end
    dx, dy = xb - xa, yb - ya
    lo, hi = 0.0, 1.0
    for p, q in zip((-dx, dx, -dy, dy), (xa - x0, x1 - xa, ya - y0, y1 - ya), strict=True):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def envelope_audit(board, added_ids: set[str]) -> dict[str, object]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    findings = {"b2": [], "antenna": [], "in1": [], "bad_width": [], "bad_via": []}
    for item_id in sorted(added_ids):
        item = by_id[item_id]
        if item.GetNetname() not in ALLOWED_NETS:
            raise RouteError(f"new copper on non-allowlisted net: {item.GetNetname()}")
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (
                round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                round(pcbnew.ToMM(item.GetDrillValue()), 6),
            ) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna = point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna = segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y < B2_BOTTOM_MM for _, y in points):
            findings["b2"].append(item_id)
        if antenna:
            findings["antenna"].append(item_id)
    checks = {
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
        raise RouteError("KiCad could not parse the fixed R7 source")
    scope = validate_pad_and_scope_contract(board)
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
        key = next(iter(unique)) if len(unique) == 1 else "<MIXED_OR_EMPTY>"
        counts[key] += 1
    return dict(sorted(counts.items()))


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    increases = {
        name: candidate_categories[name] - source_categories.get(name, 0)
        for name in sorted(candidate_categories)
        if candidate_categories[name] > source_categories.get(name, 0)
    }
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    target = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(ALLOWED_NETS)
    }
    other_nets = (set(source_nets) | set(candidate_nets)) - ALLOWED_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    expected_source = {"/USB_INPUT_VALID_N": 1}
    checks = {
        "source_unconnected_exactly_128": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_127": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_1": source["unconnected_count"] - candidate["unconnected_count"] == EXPECTED_REDUCTION,
        "target_source_counts_exact": all(source_nets.get(net, 0) == count for net, count in expected_source.items()),
        "all_target_nets_zero": all(candidate_nets.get(net, 0) == 0 for net in ALLOWED_NETS),
        "other_net_unconnected_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "fatal_drc_category_delta_zero": not increases,
        "no_new_track_dangling": candidate_categories.get("track_dangling", 0) <= source_categories.get("track_dangling", 0),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "target_net_results": target,
        "other_net_unconnected_drift": other_drift,
        "violation_category_increases": increases,
        "source_categories": dict(sorted(source_categories.items())),
        "candidate_categories": dict(sorted(candidate_categories.items())),
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
        "readme": README,
        "r6_board": R6_BOARD,
        "r7_hygiene_board": R7_HYGIENE_BOARD,
        "r7_epd_mcu_source": SOURCE_BOARD,
        "r7_route_script": R7_SCRIPT,
    }
    protected_before = {name: sha256_file(path) if path.is_file() else None for name, path in protected_paths.items()}
    try:
        if pcbnew is None:
            raise RouteError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
            raise RouteError("fixed R7 source missing or SHA-256 mismatched")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r8-internal-control-") as name:
            temp_dir = Path(name)
            first = temp_dir / "first.kicad_pcb"
            second = temp_dir / "second.kicad_pcb"
            before, added_ids, scope = build_candidate(first)
            before2, added_ids2, scope2 = build_candidate(second)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and added_ids == added_ids2
                and before == before2
                and scope == scope2
            )
            if not deterministic:
                raise RouteError("double build is not byte-deterministic")
            first_sha = sha256_file(first)
            reloaded = pcbnew.LoadBoard(str(first))
            if reloaded is None:
                raise RouteError("candidate failed reload")
            preservation = base.audit_candidate(reloaded, before, added_ids)
            envelope = envelope_audit(reloaded, added_ids)
            preservation["r8_route_envelope"] = envelope
            preservation["passed"] = preservation["passed"] and envelope["passed"]
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
        render_evidence = [
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
            "mode": "STAGING_ONLY_ADDITIVE_INTERNAL_CONTROL_COPPER",
            "state": "R8A_INTERNAL_CONTROL_ROUTED_CANDIDATE" if passed else "R8A_INTERNAL_CONTROL_HOLD",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "operation_completed": True,
            "hardware_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": passed,
            "kicad_version": str(pcbnew.GetBuildVersion()),
            "inputs": {"source": {"path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256}, "r7_builder": {"path": str(R7_SCRIPT), "sha256": R7_SCRIPT_SHA256}},
            "output": {"path": str(OUTPUT_BOARD), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)},
            "determinism": {"double_build_byte_identical": deterministic, "first_sha256": first_sha, "second_sha256": first_sha},
            "protected_sources": {"unchanged": protected_unchanged, "before": protected_before, "after": protected_after},
            "scope_audit": scope,
            "routing_contract": {
                "allowed_nets": sorted(ALLOWED_NETS),
                "excluded_scopes": ["J4/J5/J6", "SW*", "edge connectors", "buttons", "USB D+/D-", "TF", "power trunks"],
                "layers": ["F.Cu", "B.Cu", "In2.Cu"],
                "in1_signal_routing": "FORBIDDEN",
                "signal_width_mm": SIGNAL_WIDTH_MM,
                "via_diameter_mm": VIA_DIAMETER_MM,
                "via_drill_mm": VIA_DRILL_MM,
                "b2_boundary_y_mm": B2_BOTTOM_MM,
                "wroom_antenna_keepout_mm": list(WROOM_ANTENNA_KEEPOUT),
                "expected_unconnected": {"source": 128, "candidate": 127, "reduction": 1},
            },
            "source_preservation_audit": preservation,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "completed_scope": sorted(ALLOWED_NETS) if passed else [],
            "holds": [
                {"scope": "DEFERRED_INTERNAL_CONTROL_NET", "net": net, **details}
                for net, details in sorted(DEFERRED_NETS.items())
            ]
            + [{"scope": "WHOLE_BOARD", "reason": f"{candidate_drc['unconnected_count']} unrelated/held unconnected items remain; not manufacturing-ready"}],
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
        print(json.dumps({"state": report["state"], "routing_checks_passed": passed, "output": report["output"], "drc": {"source_unconnected": source_drc["unconnected_count"], "candidate_unconnected": candidate_drc["unconnected_count"], "gate_passed": gate["passed"], "categories": gate["candidate_categories"]}, "board_verifier": verifier["summary"], "report": str(REPORT_JSON)}, ensure_ascii=False, indent=2))
        return 0 if passed else 2
    except Exception as exc:
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": "STAGING_ONLY_ADDITIVE_INTERNAL_CONTROL_COPPER",
            "state": "R8A_INTERNAL_CONTROL_ROUTE_FAILED",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "locally_verified": False,
            "routing_checks_passed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "source": str(SOURCE_BOARD),
            "protected_sources_before": protected_before,
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
