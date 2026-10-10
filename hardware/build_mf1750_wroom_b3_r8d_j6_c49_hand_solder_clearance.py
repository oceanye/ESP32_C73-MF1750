#!/usr/bin/env python3
"""Move only unrouted J6 left 1.00 mm in an isolated R8d staging candidate.

The fixed R8d unified board is the sole PCB source.  J6 remains at the lower
edge with rotation 0 degrees and BAT+/GND/NTC left-to-right order unchanged.
No copper, zone, drawing, other footprint, formal project, or README is
modified.  The candidate remains HOLD pending connector/pack authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import build_mf1750_wroom_b3_r8d_epd_internal_dcdc_pg_pwr_int_edge_access as r8d


r8 = r8d.r8
edge = r8d.edge
pcbnew = edge.pcbnew

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = (
    STAGING
    / "mf1750_wroom_b3_power_tf_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.kicad_pcb"
)
SOURCE_BOARD_SHA256 = (
    "9a0f1e309abe27cc8577404e2ef62a719ca7a39934553023c941bff5b5c62403"
)
R8D_BUILDER = (
    HARDWARE
    / "build_mf1750_wroom_b3_r8d_epd_internal_dcdc_pg_pwr_int_edge_access.py"
)
R8D_BUILDER_SHA256 = (
    "bae5045ee95687ab84b2a262012a837291350576f62261566c73faf96284a8e2"
)
R8D_REPORT = STAGING / "r8d_epd_internal_dcdc_pg_pwr_int_edge_access_report.json"
R8D_REPORT_SHA256 = (
    "5d40570068144cf192cd73b403c5773d663a6677a0c363b6faa22677ab6b0ef6"
)
R8D_DRC = STAGING / "r8d_epd_internal_dcdc_pg_pwr_int_edge_access_drc.json"
R8D_DRC_SHA256 = (
    "a3e73b0a7d76c7c20ce0b95243f0574f4c48fedfb992c4ec1b59bdc9a6e38c7e"
)
CURRENT_BOARD_README_SHA256 = (
    "3bfc5732de4644051f722a26fab8aa9a6833cf9da9ee38bdea64443cce6bc912"
)

OUTPUT_BOARD = (
    STAGING / "mf1750_wroom_b3_power_tf_r8d_j6_c49_hand_solder_clearance.kicad_pcb"
)
OUTPUT_REPORT = STAGING / "r8d_j6_c49_hand_solder_clearance_report.json"
OUTPUT_DRC = STAGING / "r8d_j6_c49_hand_solder_clearance_drc.json"
PREVIEW_DIR = STAGING / "r8d_j6_c49_hand_solder_clearance_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_j6_c49_hand_solder_clearance_top.png"
OUTPUT_BOTTOM = (
    PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r8d_j6_c49_hand_solder_clearance_bottom.png"
)

EXPECTED_COPPER = 1238
EXPECTED_UNCONNECTED = 123
SOURCE_J6 = (14.75, 120.0, 0.0)
CANDIDATE_J6 = (13.75, 120.0, 0.0)
MIN_J6_C49_COURTYARD_MM = 1.0
EXPECTED_SOURCE_J6_C49_GAP_MM = 0.03
EXPECTED_J6_C49_GAP_MM = 1.03
EXPECTED_H3_J6_GAP_MM = 2.760001
EXPECTED_J6_J4_GAP_MM = 4.37
EXPECTED_R50_J6_GAP_MM = 1.33
FROZEN_EDGE_REFS = ("J4", "J5", "SW1", "SW2", "SW3", "SW4", "SW5")


class ClearanceError(r8d.FinalRebaseError):
    """Fail-closed J6/C49 mechanical-clearance error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def configure() -> None:
    r8d.configure()
    protected = dict(r8.PROTECTED_HASHES)
    protected[SOURCE_BOARD] = SOURCE_BOARD_SHA256
    protected[R8D_BUILDER] = R8D_BUILDER_SHA256
    protected[R8D_REPORT] = R8D_REPORT_SHA256
    protected[R8D_DRC] = R8D_DRC_SHA256
    # Documentation changed independently after R8d publication.  Freeze the
    # current board-family README and never write it.
    protected[r8.FORMAL_README] = CURRENT_BOARD_README_SHA256

    r8.SOURCE_BOARD = SOURCE_BOARD
    r8.SOURCE_BOARD_SHA256 = SOURCE_BOARD_SHA256
    r8.OUTPUT_BOARD = OUTPUT_BOARD
    r8.OUTPUT_REPORT = OUTPUT_REPORT
    r8.OUTPUT_DRC = OUTPUT_DRC
    r8.PREVIEW_DIR = PREVIEW_DIR
    r8.OUTPUT_TOP = OUTPUT_TOP
    r8.OUTPUT_BOTTOM = OUTPUT_BOTTOM
    r8.EXPECTED_SOURCE_COPPER = EXPECTED_COPPER
    r8.EXPECTED_CANDIDATE_COPPER = EXPECTED_COPPER
    r8.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_UNCONNECTED
    r8.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_UNCONNECTED
    r8.PROTECTED_HASHES = protected
    r8.__file__ = str(Path(__file__).resolve())

    edge.build_once = build_once
    edge.mechanical_evidence = mechanical_evidence
    r8.epd_route_preservation = unified_source_preservation
    r8.validate_r8_drc = validate_drc
    r8.json_bytes = report_json_bytes


def transform_tuple(x_mm: float, y_mm: float, rotation: float) -> tuple[int, int, float]:
    return (
        int(pcbnew.FromMM(x_mm)),
        int(pcbnew.FromMM(y_mm)),
        round(rotation % 360.0, 6),
    )


def changed_keys(before: Mapping[Any, Any], after: Mapping[Any, Any]) -> list[Any]:
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in before or key not in after or before[key] != after[key]
    )


def pad_track_hits(board: Any, reference: str) -> list[dict[str, Any]]:
    footprint = board.FindFootprintByReference(reference)
    if footprint is None:
        raise ClearanceError(f"missing footprint {reference}")
    hits: list[dict[str, Any]] = []
    for pad in footprint.Pads():
        for item in board.GetTracks():
            if item.GetNetCode() != pad.GetNetCode():
                continue
            points = (
                [("via", item.GetPosition())]
                if isinstance(item, pcbnew.PCB_VIA)
                else [("start", item.GetStart()), ("end", item.GetEnd())]
            )
            for endpoint, point in points:
                if pad.HitTest(point):
                    hits.append(
                        {
                            "pad": pad.GetNumber(),
                            "net": pad.GetNetname(),
                            "item_uuid": edge.item_uuid(item),
                            "endpoint": endpoint,
                            "position_mm": list(edge.point_mm(point)),
                        }
                    )
    return sorted(
        hits,
        key=lambda item: (item["pad"], item["item_uuid"], item["endpoint"]),
    )


def preservation_audit(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    transform_changes = changed_keys(
        source["footprint_transform"], candidate["footprint_transform"]
    )
    checks = {
        "footprint_inventory_exact": set(source["footprint_transform"])
        == set(candidate["footprint_transform"]),
        "only_j6_transform_changed": transform_changes == ["J6"],
        "source_j6_transform_exact": source["footprint_transform"]["J6"]
        == transform_tuple(*SOURCE_J6),
        "candidate_j6_transform_exact": candidate["footprint_transform"]["J6"]
        == transform_tuple(*CANDIDATE_J6),
        "all_footprint_static_exact": source["footprint_static"]
        == candidate["footprint_static"],
        "all_pad_local_data_exact": source["pads_local"] == candidate["pads_local"],
        "all_graphics_local_exact": source["graphics_local"]
        == candidate["graphics_local"],
        "all_fields_local_exact": source["fields_local"]
        == candidate["fields_local"],
        "all_children_exact": source["children"] == candidate["children"],
        "all_1238_copper_uuid_geometry_exact": len(source["tracks"])
        == EXPECTED_COPPER
        and source["tracks"] == candidate["tracks"],
        "all_zones_exact": source["zones"] == candidate["zones"],
        "all_drawings_exact": source["drawings"] == candidate["drawings"],
        "j4_j5_sw_edge_access_transforms_exact": all(
            source["footprint_transform"][reference]
            == candidate["footprint_transform"][reference]
            for reference in FROZEN_EDGE_REFS
        ),
    }
    if not all(checks.values()):
        raise ClearanceError(
            "J6-only preservation gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "changed_footprint_transforms": transform_changes,
        "source_copper_count": len(source["tracks"]),
        "candidate_copper_count": len(candidate["tracks"]),
        "copper_signature_sha256": r8d.r8b.digest(source["tracks"]),
        "zones_count": len(source["zones"]),
        "drawings_count": len(source["drawings"]),
    }


def build_once(destination: Path) -> dict[str, Any]:
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise ClearanceError("could not load fixed R8d unified source")
    source_state = edge.board_state(board)
    j6 = board.FindFootprintByReference("J6")
    if j6 is None:
        raise ClearanceError("J6 missing")
    if edge.footprint_transform(j6) != transform_tuple(*SOURCE_J6):
        raise ClearanceError(f"source J6 transform drift: {edge.footprint_transform(j6)}")
    source_hits = pad_track_hits(board, "J6")
    if source_hits:
        raise ClearanceError(f"J6 is not unrouted: {source_hits}")

    before_pad_positions = {
        pad.GetNumber(): list(edge.point_mm(pad.GetPosition())) for pad in j6.Pads()
    }
    j6.SetPosition(pcbnew.VECTOR2I_MM(CANDIDATE_J6[0], CANDIDATE_J6[1]))
    j6.SetOrientationDegrees(CANDIDATE_J6[2])
    after_pad_positions = {
        pad.GetNumber(): list(edge.point_mm(pad.GetPosition())) for pad in j6.Pads()
    }
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise ClearanceError(f"failed to save {destination}")

    candidate_board = pcbnew.LoadBoard(str(destination.resolve()))
    if candidate_board is None:
        raise ClearanceError("could not reload candidate")
    candidate_state = edge.board_state(candidate_board)
    candidate_hits = pad_track_hits(candidate_board, "J6")
    if candidate_hits:
        raise ClearanceError(f"moved J6 unexpectedly touches copper: {candidate_hits}")
    audit = preservation_audit(source_state, candidate_state)
    return {
        "changes": {
            "scope": "J6_TRANSFORM_ONLY",
            "reference": "J6",
            "source_transform": list(transform_tuple(*SOURCE_J6)),
            "candidate_transform": list(transform_tuple(*CANDIDATE_J6)),
            "translation_mm": [-1.0, 0.0],
            "source_pad_positions_mm": before_pad_positions,
            "candidate_pad_positions_mm": after_pad_positions,
            "source_track_or_via_hits": source_hits,
            "candidate_track_or_via_hits": candidate_hits,
        },
        "audit": audit,
    }


def courtyard_bbox(footprint: Any) -> list[float]:
    return edge.bbox_mm(footprint.GetCourtyard(pcbnew.F_CrtYd).BBox())


def rect_gap(a: list[float], b: list[float]) -> tuple[float, float, float]:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return round(dx, 6), round(dy, 6), round((dx * dx + dy * dy) ** 0.5, 6)


def mechanical_evidence(candidate_path: Path) -> dict[str, Any]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    candidate = pcbnew.LoadBoard(str(candidate_path.resolve()))
    if source is None or candidate is None:
        raise ClearanceError("could not load boards for mechanical evidence")

    refs = ("J6", "C49", "H3", "J4", "R50", "J5") + FROZEN_EDGE_REFS[2:]
    source_fp = {ref: source.FindFootprintByReference(ref) for ref in refs}
    candidate_fp = {ref: candidate.FindFootprintByReference(ref) for ref in refs}
    if any(item is None for item in source_fp.values()) or any(
        item is None for item in candidate_fp.values()
    ):
        raise ClearanceError("mechanical evidence footprint missing")

    source_boxes = {ref: courtyard_bbox(source_fp[ref]) for ref in refs}
    candidate_boxes = {ref: courtyard_bbox(candidate_fp[ref]) for ref in refs}
    source_j6_c49 = rect_gap(source_boxes["J6"], source_boxes["C49"])[2]
    candidate_j6_c49 = rect_gap(candidate_boxes["J6"], candidate_boxes["C49"])[2]
    candidate_h3_j6 = rect_gap(candidate_boxes["H3"], candidate_boxes["J6"])[2]
    candidate_j6_j4 = rect_gap(candidate_boxes["J6"], candidate_boxes["J4"])[2]
    candidate_r50_j6 = rect_gap(candidate_boxes["R50"], candidate_boxes["J6"])[2]

    all_clearances: list[dict[str, Any]] = []
    j6_box = candidate_boxes["J6"]
    for footprint in candidate.GetFootprints():
        reference = footprint.GetReference()
        if reference == "J6":
            continue
        courtyard = footprint.GetCourtyard(pcbnew.F_CrtYd)
        if courtyard.OutlineCount() == 0:
            continue
        box = edge.bbox_mm(courtyard.BBox())
        dx, dy, distance = rect_gap(j6_box, box)
        all_clearances.append(
            {
                "reference": reference,
                "dx_mm": dx,
                "dy_mm": dy,
                "distance_mm": distance,
                "courtyard_bbox_mm": box,
            }
        )
    all_clearances.sort(key=lambda item: (item["distance_mm"], item["reference"]))

    j6 = candidate_fp["J6"]
    pad_order = sorted(
        (
            round(edge.point_mm(pad.GetPosition())[0], 6),
            pad.GetNumber(),
            pad.GetNetname(),
        )
        for pad in j6.Pads()
    )
    pad_boxes = [pad.GetBoundingBox() for pad in j6.Pads()]
    pad_bottom_mm = max(pcbnew.ToMM(box.GetBottom()) for box in pad_boxes)
    fab_box = edge.bbox_mm(j6.GetBoundingBox(False, False))

    checks = {
        "source_gap_exactly_0p03_mm": source_j6_c49
        == EXPECTED_SOURCE_J6_C49_GAP_MM,
        "candidate_gap_exactly_1p03_mm": candidate_j6_c49
        == EXPECTED_J6_C49_GAP_MM,
        "candidate_gap_at_least_1p0_mm": candidate_j6_c49
        >= MIN_J6_C49_COURTYARD_MM,
        "h3_j6_gap_exactly_2p760001_mm": candidate_h3_j6
        == EXPECTED_H3_J6_GAP_MM,
        "j6_j4_gap_exactly_4p37_mm": candidate_j6_j4
        == EXPECTED_J6_J4_GAP_MM,
        "r50_j6_gap_exactly_1p33_mm": candidate_r50_j6
        == EXPECTED_R50_J6_GAP_MM,
        "nearest_other_courtyard_at_least_1p0_mm": all_clearances[0][
            "distance_mm"
        ]
        >= 1.0,
        "j6_position_rotation_exact": edge.footprint_transform(j6)
        == transform_tuple(*CANDIDATE_J6),
        "bat_gnd_ntc_left_to_right_exact": pad_order
        == [
            (13.75, "1", "/BAT_POS"),
            (15.75, "2", "GND"),
            (17.75, "3", "/BAT_NTC"),
        ],
        "j6_pad_copper_inside_bottom_edge_by_4p125_mm": round(
            125.0 - pad_bottom_mm, 6
        )
        == 4.125,
        "j6_body_still_overhangs_bottom_outward": fab_box[3] > 125.0,
        "j6_track_or_via_hits_zero": not pad_track_hits(candidate, "J6"),
        "c49_track_or_via_hits_zero": not pad_track_hits(candidate, "C49"),
        "j4_j5_sw_edge_access_unchanged": all(
            edge.footprint_transform(source.FindFootprintByReference(reference))
            == edge.footprint_transform(candidate.FindFootprintByReference(reference))
            for reference in FROZEN_EDGE_REFS
        ),
    }
    if not all(checks.values()):
        raise ClearanceError(
            "mechanical evidence gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "source_courtyard_bboxes_mm": source_boxes,
        "candidate_courtyard_bboxes_mm": candidate_boxes,
        "gaps_mm": {
            "source_j6_to_c49": source_j6_c49,
            "candidate_j6_to_c49": candidate_j6_c49,
            "candidate_h3_to_j6": candidate_h3_j6,
            "candidate_j6_to_j4": candidate_j6_j4,
            "candidate_r50_to_j6": candidate_r50_j6,
            "improvement_j6_to_c49": round(
                candidate_j6_c49 - source_j6_c49, 6
            ),
        },
        "nearest_candidate_courtyards": all_clearances[:8],
        "j6_pad_order_left_to_right": [list(item) for item in pad_order],
        "j6_pad_bottom_clearance_mm": round(125.0 - pad_bottom_mm, 6),
        "j6_body_bbox_mm": fab_box,
        "j6_connector_pack_line_order_status": "HOLD",
    }


def unified_source_preservation(candidate_path: Path) -> dict[str, Any]:
    source_board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    candidate_board = pcbnew.LoadBoard(str(candidate_path.resolve()))
    if source_board is None or candidate_board is None:
        raise ClearanceError("could not load unified provenance boards")
    source_state = edge.board_state(source_board)
    candidate_state = edge.board_state(candidate_board)
    audit = preservation_audit(source_state, candidate_state)

    upstream = json.loads(R8D_REPORT.read_text(encoding="utf-8"))
    pwr = upstream.get("epd_route_preservation", {}).get("pwr_int_n_9", {})
    checks = {
        "upstream_state_exact": upstream.get("state")
        == "R8D_EPD_INTERNAL_DCDC_PG_PWR_INT_EDGE_ACCESS_CANDIDATE_HOLD",
        "upstream_board_sha_exact": upstream.get("artifacts", {})
        .get("board", {})
        .get("sha256")
        == SOURCE_BOARD_SHA256,
        "upstream_determinism_passed": upstream.get("determinism", {}).get(
            "passed"
        )
        is True,
        "upstream_preservation_passed": upstream.get("preservation", {}).get(
            "passed"
        )
        is True,
        "upstream_route_chain_passed": upstream.get(
            "epd_route_preservation", {}
        ).get("passed")
        is True,
        "upstream_drc_gate_passed": upstream.get("drc", {})
        .get("gate", {})
        .get("passed")
        is True,
        "upstream_verifier_13_of_13": upstream.get("project_board_verifier", {})
        .get("summary", {})
        == {"failed": 0, "passed": 13, "total": 13},
        "upstream_pwr_9_signature_exact": pwr.get("count") == 9
        and pwr.get("uuid_signature_sha256") == r8d.PWR_INT_N_SIGNATURE_SHA256
        and pwr.get("missing_or_changed") == [],
        "candidate_all_1238_copper_exact": audit["checks"][
            "all_1238_copper_uuid_geometry_exact"
        ],
    }
    if not all(checks.values()):
        raise ClearanceError(
            "R8d unified provenance gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "upstream_report": {
            "path": str(R8D_REPORT.resolve()),
            "sha256": R8D_REPORT_SHA256,
        },
        "source_board": {
            "path": str(SOURCE_BOARD.resolve()),
            "sha256": SOURCE_BOARD_SHA256,
            "copper_count": len(source_state["tracks"]),
            "copper_signature_sha256": audit["copper_signature_sha256"],
        },
        "candidate_copper_count": len(candidate_state["tracks"]),
    }


def validate_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    source_identity = edge.violation_identity(source)
    candidate_identity = edge.violation_identity(candidate)
    source_nets = edge.unconnected_by_net(source)
    candidate_nets = edge.unconnected_by_net(candidate)
    delta = {
        net: candidate_nets.get(net, 0) - source_nets.get(net, 0)
        for net in sorted(set(source_nets) | set(candidate_nets))
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_drills = {
        uuid
        for category, uuids in source_identity
        if category == "drill_out_of_range"
        for uuid in uuids
    }
    source_dangling = {
        uuid
        for category, uuids in source_identity
        if category == "track_dangling"
        for uuid in uuids
    }
    checks = {
        "source_categories_exact": source["violation_categories"]
        == edge.EXPECTED_DRC_CATEGORIES,
        "candidate_categories_exact": candidate["violation_categories"]
        == edge.EXPECTED_DRC_CATEGORIES,
        "source_violation_count_13": source["violation_count"] == 13,
        "candidate_violation_count_13": candidate["violation_count"] == 13,
        "source_unconnected_123": source["unconnected_count"]
        == EXPECTED_UNCONNECTED,
        "candidate_unconnected_123": candidate["unconnected_count"]
        == EXPECTED_UNCONNECTED,
        "unconnected_by_net_exactly_unchanged": not delta,
        "usb_vbus_ratline_zero": source_nets.get("/USB_VBUS", 0) == 0
        and candidate_nets.get("/USB_VBUS", 0) == 0,
        "pwr_int_n_ratline_zero": source_nets.get("/PWR_INT_N", 0) == 0
        and candidate_nets.get("/PWR_INT_N", 0) == 0,
        "source_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_parity_zero": candidate["schematic_parity_count"] == 0,
        "violation_identity_exactly_unchanged": source_identity
        == candidate_identity,
        "source_u1_drill_uuid_set_exact": source_drills
        == set(edge.r7base.U1_DRILL_UUIDS),
        "source_dangling_uuid_exact": source_dangling
        == {edge.r7base.DANGLING_TRACK_UUID},
    }
    if not all(checks.values()):
        raise ClearanceError(
            "J6 clearance DRC gate failed: "
            + json.dumps(checks, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "source_categories": source["violation_categories"],
        "candidate_categories": candidate["violation_categories"],
        "source_violation_identity": [
            [category, list(uuids)] for category, uuids in source_identity
        ],
        "candidate_violation_identity": [
            [category, list(uuids)] for category, uuids in candidate_identity
        ],
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "unconnected_delta_by_net": delta,
        "unconnected_count": candidate["unconnected_count"],
        "schematic_parity_count": candidate["schematic_parity_count"],
    }


def report_json_bytes(value: Mapping[str, Any]) -> bytes:
    if isinstance(value, dict):
        state = value.get("state")
        if state == "R8_EPD_EDGE_ACCESS_CANDIDATE_HOLD":
            value["state"] = "R8D_J6_C49_HAND_SOLDER_CLEARANCE_CANDIDATE_HOLD"
            value["r8d_unified_source_modified"] = False
            value["builder"]["r8d_unified_builder"] = {
                "path": str(R8D_BUILDER.resolve()),
                "sha256": R8D_BUILDER_SHA256,
            }
            value["builder"]["r8d_unified_report"] = {
                "path": str(R8D_REPORT.resolve()),
                "sha256": R8D_REPORT_SHA256,
            }
            evidence = value.get("connectivity_evidence", {})
            if isinstance(evidence, dict):
                evidence["unconnected_reduction"] = {
                    "source_total": EXPECTED_UNCONNECTED,
                    "candidate_total": EXPECTED_UNCONNECTED,
                    "delta_by_net": {},
                    "reason": "J6-only unrouted-footprint translation preserves every net and ratline",
                    "all_net_ratline_counts_unchanged": True,
                }
                evidence["usb_vbus_conclusion"] = (
                    "CONNECTED_SET_EXACTLY_PRESERVED_BY_J6_ONLY_MOVE"
                )
            value["holds"] = [
                "J6 placement clearance target passes, but exact connector choice, battery pack envelope, mating access, and /BAT_POS-GND-/BAT_NTC line-order authority remain HOLD",
                "J5 enclosure cutout/cable envelope and SW1-SW5 pushrod travel remain HOLD",
                "12 U1 0.20 mm thermal drills, the inherited /EPD_SW_3V3 dangling endpoint, and 123 remaining unconnected items remain HOLD",
                "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
            ]
        elif state == "R8_EPD_EDGE_ACCESS_BUILD_FAILED_HOLD":
            value["state"] = "R8D_J6_C49_HAND_SOLDER_CLEARANCE_BUILD_FAILED_HOLD"
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    configure()
    return r8.main()


if __name__ == "__main__":
    raise SystemExit(main())
