#!/usr/bin/env python3
"""Build a staging-only /DCDC_EN route on the frozen R8d edge-access PCB.

The sole PCB geometry source is SHA-bound below.  The route is additive and
uses only /DCDC_EN on F.Cu, B.Cu, and In2.Cu.  U4.14 needs one explicitly
qualified 0.50/0.30 mm fanout via because a 0.60 mm annulus cannot clear the
neighbouring 0.5-mm-pitch pads without degrading U4.15's GND thermal relief.
The other four vias remain 0.60/0.30 mm.  No formal project file is written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

ENGINE = HARDWARE / "route_mf1750_wroom_b3_dcdc_en_r8d.py"
ENGINE_SHA256 = "eb9c35fbeda9db531034bdfc6ace4b2a9102d67576b59b217d9b97d98365311e"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb"
SOURCE_SHA256 = "9a0f1e309abe27cc8577404e2ef62a719ca7a39934553023c941bff5b5c62403"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
REPORT_JSON = STAGING / "r8d_edge_dcdc_en_route_report.json"
SOURCE_DRC_JSON = STAGING / "r8d_edge_dcdc_en_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r8d_edge_dcdc_en_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r8d_edge_dcdc_en_board_verifier.json"
PREVIEW_DIR = STAGING / "r8d_edge_dcdc_en_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_back.svg"

ROUTING_UUID_SEED = 1750851
SIGNAL_WIDTH_MM = 0.20
STANDARD_VIA = (0.60, 0.30)
U4_FANOUT_VIA = (0.50, 0.30)
EXPECTED_SOURCE_UNCONNECTED = 123
EXPECTED_CANDIDATE_UNCONNECTED = 120
EXPECTED_SOURCE_COPPER = 1238
EXPECTED_ADDED_TRACKS = 20
EXPECTED_ADDED_VIAS = 5

U4_FANOUT_POSITION = (23.775, 83.550)

ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    ("/DCDC_EN", "F.Cu", ((11.800, 78.750), (14.400, 78.750))),
    ("/DCDC_EN", "In2.Cu", ((14.400, 78.750), (14.400, 79.200), (22.500, 79.200), (22.500, 83.000), U4_FANOUT_POSITION)),
    # U4.14 leaves vertically; no horizontal copper crosses U4.15's thermal.
    ("/DCDC_EN", "F.Cu", ((23.775, 84.100), U4_FANOUT_POSITION)),
    ("/DCDC_EN", "F.Cu", ((26.175, 77.000), (26.175, 75.000))),
    # Local B.Cu crossover stays far from the /STM_CSRD via at 19.05/76.0.
    ("/DCDC_EN", "B.Cu", ((26.175, 75.000), (23.500, 75.000), (23.500, 77.800))),
    ("/DCDC_EN", "In2.Cu", ((23.500, 77.800), (22.500, 78.800), (22.500, 83.000), U4_FANOUT_POSITION)),
    # The long leg stays between VSYS_RAW and EPD_FAULT, then outside antenna.
    ("/DCDC_EN", "In2.Cu", (U4_FANOUT_POSITION, (23.000, 84.500), (23.000, 91.200), (27.300, 91.200), (27.300, 104.200), (57.500, 104.200), (57.500, 115.200), (61.000, 115.200))),
    ("/DCDC_EN", "F.Cu", ((61.000, 115.200), (61.000, 116.500))),
)

VIAS: tuple[tuple[float, float, float, float], ...] = (
    (14.400, 78.750, *STANDARD_VIA),
    (*U4_FANOUT_POSITION, *U4_FANOUT_VIA),
    (26.175, 75.000, *STANDARD_VIA),
    (23.500, 77.800, *STANDARD_VIA),
    (61.000, 115.200, *STANDARD_VIA),
)


class RouteError(RuntimeError):
    """Fail-closed R8d edge-access /DCDC_EN builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine():
    if not ENGINE.is_file() or sha256_file(ENGINE) != ENGINE_SHA256:
        raise RouteError(f"routing engine missing or hash-mismatched: {ENGINE}")
    spec = importlib.util.spec_from_file_location("_mf1750_r8d_edge_dcdc_engine", ENGINE)
    if spec is None or spec.loader is None:
        raise RouteError("could not create routing-engine import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


engine = load_engine()
pcbnew = engine.pcbnew


def added_via_policy(board, added_ids: set[str]) -> dict[str, object]:
    actual = []
    for item in board.GetTracks():
        item_id = engine.base.item_uuid(item)
        if item_id not in added_ids or not isinstance(item, pcbnew.PCB_VIA):
            continue
        actual.append(
            {
                "uuid": item_id,
                "position_mm": list(engine.base.point_mm(item.GetPosition())),
                "diameter_mm": round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6),
                "drill_mm": round(pcbnew.ToMM(item.GetDrillValue()), 6),
            }
        )
    actual.sort(key=lambda row: tuple(row["position_mm"]))
    expected = sorted(
        [
            {
                "position_mm": [round(x, 6), round(y, 6)],
                "diameter_mm": diameter,
                "drill_mm": drill,
            }
            for x, y, diameter, drill in VIAS
        ],
        key=lambda row: tuple(row["position_mm"]),
    )
    comparable = [
        {key: row[key] for key in ("position_mm", "diameter_mm", "drill_mm")}
        for row in actual
    ]
    return {
        "passed": len(actual) == EXPECTED_ADDED_VIAS and comparable == expected,
        "policy": "four_0p60_0p30_plus_one_u4_fanout_0p50_0p30",
        "u4_fanout_reason": "0.5_mm_pad_pitch_clearance_and_preserve_U4_pad15_GND_thermal",
        "expected": expected,
        "actual": actual,
    }


def add_routes(board) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
    for net, layer, points in ROUTES:
        if net != "/DCDC_EN" or layer == "In1.Cu":
            raise RouteError(f"route violates allowlist/layer contract: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(engine.base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end))
    net = board.FindNet("/DCDC_EN")
    if net is None:
        raise RouteError("source board lacks /DCDC_EN")
    for x_mm, y_mm, diameter_mm, drill_mm in VIAS:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
        via.SetWidth(pcbnew.FromMM(diameter_mm))
        via.SetDrill(pcbnew.FromMM(drill_mm))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(net)
        board.Add(via)
        added.append(via)
    if len(added) != EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS:
        raise RouteError(f"unexpected added copper count: {len(added)}")
    return added


_original_audit_candidate = engine.base.audit_candidate
_original_envelope_audit = engine.r8c.r8b.r8a.envelope_audit
_original_drc_gate = engine.drc_gate


def audit_candidate(board, before: dict[str, object], added_ids: set[str]) -> dict[str, object]:
    result = _original_audit_candidate(board, before, added_ids)
    via_policy = added_via_policy(board, added_ids)
    result["base_0p60_only_via_differences"] = result.pop("bad_vias", [])
    result["checks"].pop("via_rule_0p60_0p30", None)
    result["checks"]["mixed_via_policy_exact"] = via_policy["passed"]
    result["checks"]["source_copper_count_1238"] = result["source_copper_count"] == EXPECTED_SOURCE_COPPER
    result["checks"]["added_tracks_exactly_20"] = result["added_track_count"] == EXPECTED_ADDED_TRACKS
    result["checks"]["added_vias_exactly_5"] = result["added_via_count"] == EXPECTED_ADDED_VIAS
    result["via_policy"] = via_policy
    result["passed"] = all(result["checks"].values())
    return result


def envelope_audit(board, added_ids: set[str]) -> dict[str, object]:
    result = _original_envelope_audit(board, added_ids)
    via_policy = added_via_policy(board, added_ids)
    result["findings"]["accepted_u4_0p50_fanout_via"] = result["findings"].pop("bad_via", [])
    result["checks"].pop("all_new_vias_exactly_0p60_0p30_mm", None)
    result["checks"]["mixed_via_policy_exact"] = via_policy["passed"]
    result["via_policy"] = via_policy
    result["passed"] = all(result["checks"].values())
    return result


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    result = _original_drc_gate(source, candidate)
    checks = result["checks"]
    checks["source_unconnected_exactly_123"] = checks.pop("source_unconnected_exactly_125")
    checks["candidate_unconnected_exactly_120"] = checks.pop("candidate_unconnected_exactly_122")
    def identities(raw: dict[str, object]) -> list[tuple[str, tuple[str, ...]]]:
        return sorted(
            (
                str(violation.get("type", "")),
                tuple(sorted(str(item.get("uuid", "")) for item in violation.get("items", []))),
            )
            for violation in raw.get("violations", [])
        )

    source_identities = identities(source["raw"])
    candidate_identities = identities(candidate["raw"])
    checks["candidate_violation_identity_exactly_source"] = candidate_identities == source_identities
    result["source_violation_identity"] = source_identities
    result["candidate_violation_identity"] = candidate_identities
    result["passed"] = all(checks.values())
    return result


def configure_engine() -> None:
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
    engine.ROUTES = ROUTES
    engine.VIAS = tuple(("/DCDC_EN", x, y) for x, y, _, _ in VIAS)
    engine.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_SOURCE_UNCONNECTED
    engine.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_CANDIDATE_UNCONNECTED
    engine.add_routes = add_routes
    engine.drc_gate = drc_gate
    engine.base.audit_candidate = audit_candidate
    engine.r8c.r8b.r8a.envelope_audit = envelope_audit


def rewrite_report(exit_code: int) -> None:
    if not REPORT_JSON.is_file():
        return
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    passed = report.get("routing_checks_passed") is True and exit_code == 0
    report["operating_mode"] = "REVISION"
    report["revision"] = "R8D_EDGE_ACCESS_DCDC_EN_STAGING"
    report["state"] = "R8D_EDGE_DCDC_EN_ROUTED_CANDIDATE" if passed else "R8D_EDGE_DCDC_EN_HOLD"
    report["overall_status"] = "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD"
    report["locally_verified"] = False
    report["authoritative_geometry_source"] = {
        "role": "sole_PCB_geometry_source",
        "path": str(SOURCE_BOARD.resolve()),
        "sha256": SOURCE_SHA256,
    }
    report["builder"] = {
        "path": str(Path(__file__).resolve()),
        "engine": {"path": str(ENGINE.resolve()), "sha256": ENGINE_SHA256},
    }
    report["inputs"]["source"] = report["authoritative_geometry_source"]
    report["inputs"].pop("r8c_builder", None)
    report["routing_contract"]["expected_unconnected"] = {
        "source": EXPECTED_SOURCE_UNCONNECTED,
        "candidate": EXPECTED_CANDIDATE_UNCONNECTED,
        "reduction": 3,
    }
    report["routing_contract"].pop("via_diameter_mm", None)
    report["routing_contract"]["via_policy"] = {
        "standard_via_mm": list(STANDARD_VIA),
        "u4_fanout_via_mm": list(U4_FANOUT_VIA),
        "u4_fanout_position_mm": list(U4_FANOUT_POSITION),
        "all_drills_mm": 0.30,
        "clearance_rules_modified": False,
    }
    report["holds"] = [
        {"scope": "WHOLE_BOARD", "reason": "120 unrelated/held unconnected items remain; not manufacturing-ready"},
        {"scope": "MECHANICAL_AND_MANUFACTURING", "reason": "enclosure, stackup, assembly, thermal, RF, and vendor acceptance remain outside this route scope"},
    ]
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise RouteError("sole source PCB missing or SHA-256 mismatched")
    configure_engine()
    exit_code = engine.main(argv)
    rewrite_report(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
