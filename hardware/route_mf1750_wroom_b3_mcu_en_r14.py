#!/usr/bin/env python3
"""Route /MCU_EN on the SHA-bound R12 staging board.

Operating mode: REVISION, staging-only.  The builder is additive and may add
only /MCU_EN copper.  It never moves footprints, edits zones, or replaces
existing copper.  F.Cu provides the six SMD-pad escapes, B.Cu carries the
left-to-centre trunk, and In2.Cu carries the centre-to-WROOM trunk.  B2,
In1.Cu, and the WROOM antenna keepout are forbidden.

UUID seed 1750901 is reserved for this builder in the project registry.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import route_mf1750_wroom_b3_boot_n_r8e as boot


pcbnew = boot.pcbnew
base = boot.base

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r12_r11_user_key_2_n_routed.kicad_pcb"
SOURCE_SHA256 = "3a92f2aa31292032f38fcbae7152e67d20ef1cf50e0e619f6243faf3abe32ea3"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_routed.kicad_pcb"
REPORT_JSON = STAGING / "r14_r12_mcu_en_route_report.json"
SOURCE_DRC_JSON = STAGING / "r14_r12_mcu_en_source_drc.json"
CANDIDATE_DRC_JSON = STAGING / "r14_r12_mcu_en_drc.json"
BOARD_VERIFIER_JSON = STAGING / "r14_r12_mcu_en_board_verifier.json"
PREVIEW_DIR = STAGING / "r14_r12_mcu_en_preview"
TOP_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_top.png"
BOTTOM_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_bottom.png"
FRONT_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_front.svg"
BACK_COPPER_SVG = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_back.svg"
ISO_PREVIEW = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_iso.png"

SEED_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"
SEED_REGISTRY_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_uuid_seed_registry.py"
BOOT_TEMPLATE = HARDWARE / "route_mf1750_wroom_b3_boot_n_r8e.py"

ROUTING_UUID_SEED = 1750901
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
B2_BOTTOM_MM = 60.5
WROOM_ANTENNA_KEEPOUT = (58.75, 79.75, 66.0, 114.0)
EXPECTED_SOURCE_COPPER = 1321
EXPECTED_ADDED_TRACKS = 46
EXPECTED_ADDED_VIAS = 8
EXPECTED_CANDIDATE_COPPER = 1375
EXPECTED_SOURCE_UNCONNECTED = 112
EXPECTED_CANDIDATE_UNCONNECTED = 107
ALLOWED_NETS = frozenset({"/MCU_EN"})

PAD_CONTRACT = (
    ("C48", "1", "/MCU_EN", 36.0250, 74.0000),
    ("R27", "2", "/MCU_EN", 36.8250, 76.5000),
    ("SW5", "1", "/MCU_EN", 1.3500, 94.7000),
    ("SW5", "1", "/MCU_EN", 1.3500, 98.3000),
    ("U1", "3", "/MCU_EN", 54.7200, 81.2500),
    ("U3", "10", "/MCU_EN", 11.8000, 78.2500),
)

# SW5 weave -> B.Cu left trunk.  Two through vias cross the vertical B.Cu
# /EPD_PWR_EN barrier on In2.Cu, then return to B.Cu and join the U3 escape.
# The centre B.Cu trunk uses a short In2.Cu bridge around the existing
# /DCDC_EN vertical segment.  At x=39 another through via changes to In2.Cu
# for the WROOM escape.  U1.3 is taken through the narrow F.Cu channel
# between C41 and C42 before the final via at y=76.1 mm.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    (
        "/MCU_EN",
        "F.Cu",
        (
            (1.3500, 94.7000),
            (1.3500, 95.4000),
            (2.0000, 96.0500),
            (2.0000, 96.9500),
            (1.3500, 97.6000),
            (1.3500, 98.3000),
            (1.3500, 99.0000),
            (1.3500, 100.2000),
            (4.0000, 100.2000),
        ),
    ),
    (
        "/MCU_EN",
        "B.Cu",
        (
            (4.0000, 100.2000),
            (4.0000, 95.2000),
            (3.0000, 94.7000),
            (3.0000, 93.4000),
            (4.5000, 92.8000),
            (4.5000, 83.5000),
            (12.6000, 83.5000),
            (12.6000, 84.2000),
        ),
    ),
    ("/MCU_EN", "In2.Cu", ((12.6000, 84.2000), (12.6000, 85.0000), (18.2000, 85.0000), (18.2000, 84.2000))),
    ("/MCU_EN", "B.Cu", ((18.2000, 84.2000), (18.7000, 83.5000), (18.7000, 78.3000), (16.4000, 78.3000))),
    (
        "/MCU_EN",
        "F.Cu",
        (
            (11.8000, 78.2500),
            (12.1500, 78.2500),
            (12.4500, 78.3500),
            (13.3000, 78.3500),
            (13.8000, 77.9000),
            (15.3000, 77.9000),
            (16.4000, 78.3000),
        ),
    ),
    ("/MCU_EN", "B.Cu", ((16.4000, 78.3000), (22.0000, 78.1000))),
    ("/MCU_EN", "F.Cu", ((22.0000, 78.1000), (22.5000, 78.5000), (24.1000, 78.5000), (24.3000, 78.1000))),
    ("/MCU_EN", "B.Cu", ((24.3000, 78.1000), (25.3000, 77.3000), (31.0000, 77.3000), (39.0000, 78.0000))),
    (
        "/MCU_EN",
        "F.Cu",
        (
            (36.0250, 74.0000),
            (36.0250, 75.2000),
            (36.8250, 76.0000),
            (36.8250, 76.5000),
            (37.5000, 77.2000),
            (39.0000, 78.0000),
        ),
    ),
    ("/MCU_EN", "In2.Cu", ((39.0000, 78.0000), (41.0000, 78.0000), (42.0000, 76.8000), (54.7500, 76.1000))),
    (
        "/MCU_EN",
        "F.Cu",
        ((54.7500, 76.1000), (54.9500, 76.7000), (54.9500, 80.1000), (54.7200, 80.5000), (54.7200, 81.2500)),
    ),
)

VIAS = (
    ("/MCU_EN", 4.0000, 100.2000),
    ("/MCU_EN", 12.6000, 84.2000),
    ("/MCU_EN", 18.2000, 84.2000),
    ("/MCU_EN", 16.4000, 78.3000),
    ("/MCU_EN", 22.0000, 78.1000),
    ("/MCU_EN", 24.3000, 78.1000),
    ("/MCU_EN", 39.0000, 78.0000),
    ("/MCU_EN", 54.7500, 76.1000),
)


class RouteError(RuntimeError):
    """Fail-closed MCU_EN route-builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_scope(board: Any) -> dict[str, object]:
    actual: list[tuple[str, str, str, float, float]] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != "/MCU_EN":
                continue
            x_mm, y_mm = base.point_mm(pad.GetPosition())
            actual.append((footprint.GetReference(), pad.GetNumber(), pad.GetNetname(), x_mm, y_mm))
    actual.sort()
    expected = sorted(PAD_CONTRACT)
    if len(actual) != len(expected):
        raise RouteError(f"MCU_EN pad-count drift: {actual}")
    for got, wanted in zip(actual, expected, strict=True):
        if got[:3] != wanted[:3] or any(
            abs(a - b) > 0.000002 for a, b in zip(got[3:], wanted[3:], strict=True)
        ):
            raise RouteError(f"MCU_EN pad contract drift: got={got}, expected={wanted}")
    refs = {item[0] for item in actual}
    if refs != {"C48", "R27", "SW5", "U1", "U3"}:
        raise RouteError(f"MCU_EN endpoint reference drift: {sorted(refs)}")
    return {
        "passed": True,
        "net": "/MCU_EN",
        "endpoint_references": sorted(refs),
        "source_ratlines_expected": 5,
        "pad_contract": [
            {"reference": ref, "pad": pad, "net": net, "position_mm": [x, y]}
            for ref, pad, net, x, y in actual
        ],
        "connected_set_required": ["SW5.1@94.7", "SW5.1@98.3", "U3.10", "C48.1", "R27.2", "U1.3"],
    }


def seed_registry_audit() -> dict[str, object]:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    matches = [
        record for record in registry["assignments"]
        if int(record["seed_decimal"]) == ROUTING_UUID_SEED
    ]
    owner_ok = len(matches) == 1 and matches[0]["owner"] == Path(__file__).name
    literal = re.compile(r"ROUTING_UUID_SEED\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)")
    owners = []
    for script in sorted(HARDWARE.glob("*.py")):
        values = {int(token, 0) for token in literal.findall(script.read_text(encoding="utf-8"))}
        if ROUTING_UUID_SEED in values:
            owners.append(script.name)
    checks = {
        "registry_has_exact_owner": owner_ok,
        "literal_seed_has_single_owner": owners == [Path(__file__).name],
        "seed_exactly_1750901": ROUTING_UUID_SEED == 1750901,
    }
    if not all(checks.values()):
        raise RouteError(f"seed registry audit failed: {checks}, owners={owners}")
    return {"passed": True, "checks": checks, "owners": owners, "record": matches[0]}


def uuid_collision_audit(added_ids: set[str], source_ids: set[str]) -> dict[str, object]:
    source_intersection = sorted(added_ids & source_ids)
    staging_union: set[str] = set()
    board_records = []
    for path in sorted(STAGING.glob("*.kicad_pcb")):
        if path.resolve() == OUTPUT_BOARD.resolve():
            continue
        board = pcbnew.LoadBoard(str(path.resolve()))
        if board is None:
            raise RouteError(f"could not parse staging UUID evidence board: {path}")
        ids = {base.item_uuid(item) for item in board.GetTracks()}
        intersection = sorted(ids & added_ids)
        staging_union.update(ids)
        board_records.append({"path": str(path.resolve()), "sha256": sha256_file(path), "intersection": intersection})
    staging_intersection = sorted(staging_union & added_ids)
    checks = {
        "added_uuid_count_exact": len(added_ids) == EXPECTED_ADDED_TRACKS + EXPECTED_ADDED_VIAS,
        "source_intersection_zero": not source_intersection,
        "all_staging_intersection_zero": not staging_intersection,
        "every_staging_board_intersection_zero": all(not record["intersection"] for record in board_records),
    }
    if not all(checks.values()):
        raise RouteError(f"UUID collision audit failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "added_uuids": sorted(added_ids),
        "source_intersection": source_intersection,
        "staging_intersection": staging_intersection,
        "staging_board_count": len(board_records),
        "boards": board_records,
    }


def add_routes(board: Any) -> list[object]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added = []
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


def build_candidate(destination: Path):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise RouteError("KiCad could not parse fixed R12 source")
    scope = validate_scope(board)
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(f"source copper-count drift: {len(before['tracks'])}")
    added = add_routes(board)
    added_ids = {base.item_uuid(item) for item in added}
    if len(added_ids) != len(added):
        raise RouteError("duplicate deterministic UUID within MCU_EN route")
    scope["seed_registry_audit"] = seed_registry_audit()
    scope["uuid_collision_audit"] = uuid_collision_audit(added_ids, set(before["tracks"]))
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise RouteError(f"failed to save {destination}")
    return before, added_ids, scope


def envelope_audit(board: Any, added_ids: set[str]) -> dict[str, object]:
    by_id = {base.item_uuid(item): item for item in board.GetTracks()}
    findings = {key: [] for key in ("non_allowlisted_net", "b2", "antenna", "in1", "bad_width", "bad_via")}
    for item_id in sorted(added_ids):
        item = by_id[item_id]
        if item.GetNetname() not in ALLOWED_NETS:
            findings["non_allowlisted_net"].append(item_id)
        if isinstance(item, pcbnew.PCB_VIA):
            points = [base.point_mm(item.GetPosition())]
            if (round(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)), 6), round(pcbnew.ToMM(item.GetDrillValue()), 6)) != (VIA_DIAMETER_MM, VIA_DRILL_MM):
                findings["bad_via"].append(item_id)
            antenna_hit = boot.point_in_rect(points[0], WROOM_ANTENNA_KEEPOUT)
        else:
            points = [base.point_mm(item.GetStart()), base.point_mm(item.GetEnd())]
            if round(pcbnew.ToMM(item.GetWidth()), 6) != SIGNAL_WIDTH_MM:
                findings["bad_width"].append(item_id)
            if item.GetLayer() == base.layer_id(board, "In1.Cu"):
                findings["in1"].append(item_id)
            antenna_hit = boot.segment_hits_rect(points[0], points[1], WROOM_ANTENNA_KEEPOUT)
        if any(y < B2_BOTTOM_MM for _, y in points):
            findings["b2"].append(item_id)
        if antenna_hit:
            findings["antenna"].append(item_id)
    checks = {
        "new_copper_net_whitelist_mcu_en_only": not findings["non_allowlisted_net"],
        "no_new_copper_in_b2": not findings["b2"],
        "no_new_copper_in_wroom_antenna_keepout": not findings["antenna"],
        "no_signal_track_on_in1": not findings["in1"],
        "all_new_tracks_exactly_0p20_mm": not findings["bad_width"],
        "all_new_vias_exactly_0p60_0p30_mm": not findings["bad_via"],
    }
    return {"passed": all(checks.values()), "checks": checks, "findings": findings}


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_nets = boot.unconnected_by_net(source["raw"])
    candidate_nets = boot.unconnected_by_net(candidate["raw"])
    for net in ("/MCU_EN", "/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/USER_KEY_2_N"):
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(set(source_nets) | set(candidate_nets))
        if net not in ALLOWED_NETS and source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fingerprints = boot.violation_fingerprints(source["raw"])
    candidate_fingerprints = boot.violation_fingerprints(candidate["raw"])
    checks = {
        "source_drc_exactly_13": source["violation_count"] == 13,
        "candidate_drc_exactly_13": candidate["violation_count"] == 13,
        "inherited_violation_uuid_position_identity_exact": source_fingerprints == candidate_fingerprints,
        "source_unconnected_exactly_112": source["unconnected_count"] == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_exactly_107": candidate["unconnected_count"] == EXPECTED_CANDIDATE_UNCONNECTED,
        "exact_unconnected_reduction_5": source["unconnected_count"] - candidate["unconnected_count"] == 5,
        "source_mcu_en_unconnected_exactly_5": source_nets.get("/MCU_EN", 0) == 5,
        "candidate_mcu_en_unconnected_zero": candidate_nets.get("/MCU_EN", 0) == 0,
        # Compatibility key consumed by the imported report skeleton.
        "candidate_boot_n_unconnected_zero": candidate_nets.get("/MCU_EN", 0) == 0,
        "source_dcdc_en_unconnected_zero": source_nets.get("/DCDC_EN", 0) == 0,
        "candidate_dcdc_en_unconnected_zero": candidate_nets.get("/DCDC_EN", 0) == 0,
        "other_net_unconnected_counts_unchanged": not other_drift,
        "source_schematic_parity_zero": source["schematic_parity_count"] == 0,
        "candidate_schematic_parity_zero": candidate["schematic_parity_count"] == 0,
        "violation_categories_exact": collections.Counter(source["violation_categories"]) == collections.Counter(candidate["violation_categories"]),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_fingerprints": source_fingerprints,
        "candidate_violation_fingerprints": candidate_fingerprints,
    }


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
    boot.validate_scope = validate_scope
    boot.build_candidate = build_candidate
    boot.envelope_audit = envelope_audit
    boot.drc_gate = drc_gate
    boot.__file__ = str(Path(__file__).resolve())


def postprocess_report(result: int, script_hash_before: str) -> None:
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    script_hash_after = sha256_file(Path(__file__).resolve())
    if script_hash_after != script_hash_before:
        raise RouteError("builder changed while running")
    if result != 0 or report.get("routing_checks_passed") is not True:
        return
    preservation = report["source_preservation_audit"]
    checks = preservation["checks"]
    checks.pop("source_copper_count_exactly_1263", None)
    checks.pop("added_tracks_exactly_16", None)
    checks.pop("added_vias_exactly_4", None)
    checks[f"source_copper_count_exactly_{EXPECTED_SOURCE_COPPER}"] = preservation["source_copper_count"] == EXPECTED_SOURCE_COPPER
    checks[f"added_tracks_exactly_{EXPECTED_ADDED_TRACKS}"] = preservation["added_track_count"] == EXPECTED_ADDED_TRACKS
    checks[f"added_vias_exactly_{EXPECTED_ADDED_VIAS}"] = preservation["added_via_count"] == EXPECTED_ADDED_VIAS
    preservation["mcu_en_route_envelope"] = preservation.pop("r8e_boot_n_route_envelope")
    preservation["passed"] = all(checks.values()) and preservation["mcu_en_route_envelope"]["passed"]
    report.update({
        "mode": "STAGING_ONLY_ADDITIVE_SINGLE_NET_MCU_EN",
        "revision": "R14_R12_MCU_EN_STAGING",
        "state": "R14_R12_MCU_EN_ROUTED_CANDIDATE",
        "builder": {"path": str(Path(__file__).resolve()), "sha256_before": script_hash_before, "sha256_after": script_hash_after, "unchanged": True},
        "completed_scope": ["/MCU_EN"],
    })
    report["routing_contract"] = {
        "allowed_nets": ["/MCU_EN"],
        "routing_uuid_seed": ROUTING_UUID_SEED,
        "new_copper": {"tracks": EXPECTED_ADDED_TRACKS, "vias": EXPECTED_ADDED_VIAS},
        "layers": ["F.Cu", "B.Cu", "In2.Cu"],
        "signal_width_mm": SIGNAL_WIDTH_MM,
        "via_diameter_mm": VIA_DIAMETER_MM,
        "via_drill_mm": VIA_DRILL_MM,
        "in1_signal_routing": "FORBIDDEN",
        "expected_drc": {"source": 13, "candidate": 13, "new": 0},
        "expected_unconnected": {"source": EXPECTED_SOURCE_UNCONNECTED, "candidate": EXPECTED_CANDIDATE_UNCONNECTED, "reduction": 5},
        "all_mcu_en_endpoints_one_connected_set": report["drc_gate"]["checks"]["candidate_mcu_en_unconnected_zero"],
    }
    report["holds"] = [
        {"scope": "WHOLE_BOARD", "reason": f"{report['candidate_drc']['unconnected_count']} unrelated/held items remain; not manufacturing-ready"},
        {"scope": "EDGE_CONNECTORS_USB_TF_POWER_TRUNKS", "reason": "outside this single-net route scope"},
    ]
    artifact_paths = {
        "board": OUTPUT_BOARD,
        "source_drc_json": SOURCE_DRC_JSON,
        "candidate_drc_json": CANDIDATE_DRC_JSON,
        "board_verifier_json": BOARD_VERIFIER_JSON,
        "top_preview": TOP_PREVIEW,
        "bottom_preview": BOTTOM_PREVIEW,
        "front_copper_svg": FRONT_COPPER_SVG,
        "back_copper_svg": BACK_COPPER_SVG,
        "iso_preview": ISO_PREVIEW,
    }
    report["artifact_hashes"] = {
        key: {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for key, path in artifact_paths.items()
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    script_hash_before = sha256_file(Path(__file__).resolve())
    configure_template()
    result = boot.main()
    if result == 0:
        kicad_cli = base.find_kicad_cli()
        completed = subprocess.run(
            [
                str(kicad_cli),
                "pcb",
                "render",
                "--side",
                "top",
                "--background",
                "opaque",
                "--quality",
                "high",
                "--width",
                "1800",
                "--height",
                "1600",
                "--perspective",
                "--rotate",
                "35,0,35",
                "--zoom",
                "0.8",
                "--output",
                str(ISO_PREVIEW.resolve()),
                str(OUTPUT_BOARD.resolve()),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0 or not ISO_PREVIEW.is_file():
            raise RouteError(
                "isometric render failed: "
                f"rc={completed.returncode}, stderr={completed.stderr.strip()}"
            )
    postprocess_report(result, script_hash_before)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
