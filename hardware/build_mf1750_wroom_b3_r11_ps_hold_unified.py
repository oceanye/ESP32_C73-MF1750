#!/usr/bin/env python3
"""Merge the proven controlled PS_HOLD delta into frozen R10 unified PCB.

Operating mode: REVISION.  R10 is the sole editable geometry source.  The
hash-bound R8e PS_HOLD engine replays exactly the branch's six removals and 22
additions.  BOOT_N's 20 R10 additions are audited UUID-for-UUID and
geometry-for-geometry before and after the merge.  No component or zone moves.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

PS_ENGINE = HARDWARE / "route_mf1750_wroom_b3_ps_hold_controlled_r8e.py"
PS_ENGINE_SHA256 = "50cb516f808729836eab55211fc964c21b38e7eb07f76064800e41bfab1697c2"
J6_UTILITY = HARDWARE / "build_mf1750_wroom_b3_r8d_j6_c49_hand_solder_clearance.py"
J6_UTILITY_SHA256 = "d8f7b8c610b1598ec204f5475ab032b18c5ed5f7eb2a9c0d62d3a8b2236438e8"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified.kicad_pcb"
SOURCE_SHA256 = "53ec067d73cbca12de0c874f2576b84dfe3120a544a43393c23f38dd283e08d0"
BRANCH_SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
BRANCH_SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"
PS_BRANCH_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_edge_dcdc_en_ps_hold_routed.kicad_pcb"
PS_BRANCH_SHA256 = "44014cdc68039f0e0482877cd2c532e94ba8ee171e0631c3a0b4341cf697b2bc"
BOOT_BRANCH_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_boot_n_routed.kicad_pcb"
BOOT_BRANCH_SHA256 = "2a1f76928cfa17de688949be06c410bdedccf6dbe7b1ddbe2b0080d907e0ab7e"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified.kicad_pcb"
OUTPUT_REPORT = STAGING / "r11_r10_ps_hold_unified_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r11_r10_ps_hold_unified_source_drc.json"
OUTPUT_DRC = STAGING / "r11_r10_ps_hold_unified_drc.json"
OUTPUT_VERIFIER = STAGING / "r11_r10_ps_hold_unified_board_verifier.json"
PREVIEW_DIR = STAGING / "r11_r10_ps_hold_unified_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified_bottom.png"
OUTPUT_FRONT = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified_front.svg"
OUTPUT_BACK = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified_back.svg"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified_iso.png"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"

EXPECTED_SOURCE_COPPER = 1283
EXPECTED_CANDIDATE_COPPER = 1299
EXPECTED_SOURCE_OPEN = 117
EXPECTED_CANDIDATE_OPEN = 115
EXPECTED_DRC = 13
EXPECTED_PS_ADDED = 22
EXPECTED_PS_REMOVED = 6
EXPECTED_BOOT_ADDED = 20
EXPECTED_J6_POSITION_MM = (13.75, 120.0)
EXPECTED_J6_ROTATION_DEG = 0.0
MIN_J6_C49_COURTYARD_MM = 1.03


class MergeError(RuntimeError):
    """Fail-closed R11 unified-candidate error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, expected_sha256: str, name: str):
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise MergeError(f"frozen dependency missing or hash-mismatched: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise MergeError(f"could not import frozen dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ps = load_module(PS_ENGINE, PS_ENGINE_SHA256, "_mf1750_r11_ps_engine")
j6c = load_module(J6_UTILITY, J6_UTILITY_SHA256, "_mf1750_r11_j6_utility")
pcbnew = ps.pcbnew
base = ps.base


def configure_ps_engine() -> None:
    ps.SOURCE_BOARD = SOURCE_BOARD
    ps.SOURCE_SHA256 = SOURCE_SHA256
    ps.OUTPUT_BOARD = OUTPUT_BOARD
    ps.REPORT_JSON = OUTPUT_REPORT
    ps.SOURCE_DRC_JSON = OUTPUT_SOURCE_DRC
    ps.CANDIDATE_DRC_JSON = OUTPUT_DRC
    ps.BOARD_VERIFIER_JSON = OUTPUT_VERIFIER
    ps.PREVIEW_DIR = PREVIEW_DIR
    ps.TOP_PREVIEW = OUTPUT_TOP
    ps.BOTTOM_PREVIEW = OUTPUT_BOTTOM
    ps.FRONT_COPPER_SVG = OUTPUT_FRONT
    ps.BACK_COPPER_SVG = OUTPUT_BACK
    ps.EXPECTED_SOURCE_COPPER = EXPECTED_SOURCE_COPPER
    ps.EXPECTED_CANDIDATE_COPPER = EXPECTED_CANDIDATE_COPPER
    ps.EXPECTED_SOURCE_UNCONNECTED = EXPECTED_SOURCE_OPEN
    ps.EXPECTED_CANDIDATE_UNCONNECTED = EXPECTED_CANDIDATE_OPEN
    ps.EXPECTED_DRC_COUNT = EXPECTED_DRC


def track_signatures(board) -> dict[str, object]:
    return {base.item_uuid(item): base.track_signature(item) for item in board.GetTracks()}


def load_signatures(path: Path) -> tuple[object, dict[str, object]]:
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        raise MergeError(f"could not load board: {path}")
    return board, track_signatures(board)


def branch_context() -> dict[str, object]:
    _, source = load_signatures(SOURCE_BOARD)
    _, branch_source = load_signatures(BRANCH_SOURCE_BOARD)
    _, ps_branch = load_signatures(PS_BRANCH_BOARD)
    _, boot_branch = load_signatures(BOOT_BRANCH_BOARD)
    source_ids = set(source)
    branch_source_ids = set(branch_source)
    ps_ids = set(ps_branch)
    boot_ids = set(boot_branch)
    ps_added_ids = ps_ids - branch_source_ids
    ps_removed_ids = branch_source_ids - ps_ids
    boot_added_ids = boot_ids - branch_source_ids
    return {
        "source": source,
        "branch_source": branch_source,
        "ps_branch": ps_branch,
        "boot_branch": boot_branch,
        "ps_added_ids": ps_added_ids,
        "ps_removed_ids": ps_removed_ids,
        "boot_added_ids": boot_added_ids,
        "source_ids": source_ids,
    }


def preflight_audit() -> dict[str, object]:
    context = branch_context()
    source = context["source"]
    branch_source = context["branch_source"]
    ps_branch = context["ps_branch"]
    boot_branch = context["boot_branch"]
    source_ids = context["source_ids"]
    ps_added_ids = context["ps_added_ids"]
    ps_removed_ids = context["ps_removed_ids"]
    boot_added_ids = context["boot_added_ids"]
    controlled = set(ps.CONTROLLED_OLD_COPPER)
    r10_added_over_branch_source = source_ids - set(branch_source)
    checks = {
        "r10_source_copper_count_1283": len(source) == EXPECTED_SOURCE_COPPER,
        "ps_branch_added_exactly_22": len(ps_added_ids) == EXPECTED_PS_ADDED,
        "ps_branch_removed_exactly_6": len(ps_removed_ids) == EXPECTED_PS_REMOVED,
        "ps_branch_removed_set_exactly_controlled_six": ps_removed_ids == controlled,
        "r10_contains_all_controlled_six": controlled <= source_ids,
        "r10_controlled_six_geometry_matches_branch_source": all(
            source[item_id] == branch_source[item_id] for item_id in controlled
        ),
        "ps_added_uuid_intersection_with_r10_zero": not (ps_added_ids & source_ids),
        "boot_branch_added_exactly_20": len(boot_added_ids) == EXPECTED_BOOT_ADDED,
        "r10_delta_over_branch_source_exactly_boot_20": r10_added_over_branch_source
        == boot_added_ids,
        "r10_boot_20_uuid_geometry_exact": all(
            source[item_id] == boot_branch[item_id] for item_id in boot_added_ids
        ),
        "r10_retains_branch_source_copper_uuid_geometry_exact": all(
            source.get(item_id) == signature
            for item_id, signature in branch_source.items()
        ),
        "ps_branch_candidate_has_no_duplicate_copper_uuid": len(ps_branch)
        == len(set(ps_branch)),
    }
    if not all(checks.values()):
        raise MergeError("R11 preflight failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "r10_copper_count": len(source),
        "controlled_removed_uuids": sorted(ps_removed_ids),
        "ps_added_uuids": sorted(ps_added_ids),
        "boot_added_uuids": sorted(boot_added_ids),
        "ps_added_signature_sha256": hashlib.sha256(
            json.dumps(
                {item_id: ps_branch[item_id] for item_id in sorted(ps_added_ids)},
                sort_keys=True,
                default=list,
            ).encode("utf-8")
        ).hexdigest(),
    }


def exact_merge_audit() -> dict[str, object]:
    source_board, source = load_signatures(SOURCE_BOARD)
    candidate_board, candidate = load_signatures(OUTPUT_BOARD)
    context = branch_context()
    ps_branch = context["ps_branch"]
    boot_branch = context["boot_branch"]
    ps_added_ids = context["ps_added_ids"]
    ps_removed_ids = context["ps_removed_ids"]
    boot_added_ids = context["boot_added_ids"]
    source_ids = set(source)
    candidate_ids = set(candidate)
    actual_added_ids = candidate_ids - source_ids
    actual_removed_ids = source_ids - candidate_ids
    retained_ids = source_ids & candidate_ids
    source_state = base.source_state(source_board)
    candidate_state = base.source_state(candidate_board)
    actual_added_objects = {
        base.item_uuid(item): item
        for item in candidate_board.GetTracks()
        if base.item_uuid(item) in actual_added_ids
    }
    new_net_counts: dict[str, int] = {}
    for item in actual_added_objects.values():
        new_net_counts[item.GetNetname()] = new_net_counts.get(item.GetNetname(), 0) + 1
    checks = {
        "source_copper_count_1283": len(source) == EXPECTED_SOURCE_COPPER,
        "candidate_copper_count_1299": len(candidate) == EXPECTED_CANDIDATE_COPPER,
        "actual_removed_exactly_controlled_six": actual_removed_ids == ps_removed_ids
        == set(ps.CONTROLLED_OLD_COPPER),
        "actual_added_uuid_set_exactly_ps_branch_22": actual_added_ids == ps_added_ids,
        "actual_added_uuid_geometry_exactly_ps_branch": all(
            candidate[item_id] == ps_branch[item_id] for item_id in ps_added_ids
        ),
        "all_other_r10_copper_uuid_geometry_exact": all(
            candidate[item_id] == source[item_id] for item_id in retained_ids
        ),
        "boot_20_preserved_uuid_geometry_exact": all(
            source[item_id] == candidate[item_id] == boot_branch[item_id]
            for item_id in boot_added_ids
        ),
        "boot_20_none_removed": not (boot_added_ids & actual_removed_ids),
        "new_net_counts_exact": dict(sorted(new_net_counts.items()))
        == dict(sorted(ps.NEW_NET_COUNTS.items())),
        "footprints_exact": source_state["footprints"] == candidate_state["footprints"],
        "zones_exact": source_state["zones"] == candidate_state["zones"],
        "candidate_copper_uuid_unique": candidate_state["copper_uuid_audit"]["passed"]
        is True,
    }
    if not all(checks.values()):
        raise MergeError("exact R11 merge audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source),
        "candidate_copper_count": len(candidate),
        "removed_uuids": sorted(actual_removed_ids),
        "added_uuids": sorted(actual_added_ids),
        "boot_preserved_uuids": sorted(boot_added_ids),
        "new_net_counts": dict(sorted(new_net_counts.items())),
    }


def j6_mechanical_audit() -> dict[str, object]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD))
    candidate = pcbnew.LoadBoard(str(OUTPUT_BOARD))
    if source is None or candidate is None:
        raise MergeError("could not load boards for J6 audit")
    source_j6 = source.FindFootprintByReference("J6")
    candidate_j6 = candidate.FindFootprintByReference("J6")
    source_c49 = source.FindFootprintByReference("C49")
    candidate_c49 = candidate.FindFootprintByReference("C49")
    if any(item is None for item in (source_j6, candidate_j6, source_c49, candidate_c49)):
        raise MergeError("J6/C49 missing from R11 audit")
    source_position = tuple(round(value, 6) for value in j6c.edge.point_mm(source_j6.GetPosition()))
    candidate_position = tuple(
        round(value, 6) for value in j6c.edge.point_mm(candidate_j6.GetPosition())
    )
    source_rotation = round(float(source_j6.GetOrientationDegrees()) % 360.0, 6)
    candidate_rotation = round(float(candidate_j6.GetOrientationDegrees()) % 360.0, 6)
    source_gap = j6c.rect_gap(j6c.courtyard_bbox(source_j6), j6c.courtyard_bbox(source_c49))[2]
    candidate_gap = j6c.rect_gap(
        j6c.courtyard_bbox(candidate_j6), j6c.courtyard_bbox(candidate_c49)
    )[2]
    checks = {
        "source_j6_position_exact": source_position == EXPECTED_J6_POSITION_MM,
        "candidate_j6_position_exact": candidate_position == EXPECTED_J6_POSITION_MM,
        "source_j6_rotation_zero": source_rotation == EXPECTED_J6_ROTATION_DEG,
        "candidate_j6_rotation_zero": candidate_rotation == EXPECTED_J6_ROTATION_DEG,
        "j6_transform_unchanged": source_position == candidate_position
        and source_rotation == candidate_rotation,
        "j6_c49_gap_unchanged": source_gap == candidate_gap,
        "candidate_j6_c49_gap_at_least_1p03": candidate_gap >= MIN_J6_C49_COURTYARD_MM,
        "j6_track_or_via_hits_zero": not j6c.pad_track_hits(candidate, "J6"),
        "c49_track_or_via_hits_zero": not j6c.pad_track_hits(candidate, "C49"),
    }
    if not all(checks.values()):
        raise MergeError("R11 J6 mechanical audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_position_mm": list(source_position),
        "candidate_position_mm": list(candidate_position),
        "source_rotation_deg": source_rotation,
        "candidate_rotation_deg": candidate_rotation,
        "source_j6_c49_gap_mm": source_gap,
        "candidate_j6_c49_gap_mm": candidate_gap,
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r11-ps-hold-iso-") as name:
        temporary = Path(name)
        outputs = [temporary / "iso1.png", temporary / "iso2.png"]
        hashes = []
        commands = []
        for output in outputs:
            command = [
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
                "--floor",
                "--rotate",
                "315,0,45",
                "--output",
                str(output),
                str(OUTPUT_BOARD),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise MergeError(
                    "isometric render failed: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
            hashes.append(sha256_file(output))
            commands.append(command)
        os.replace(outputs[0], OUTPUT_ISO)
    return {
        "path": str(OUTPUT_ISO),
        "bytes": OUTPUT_ISO.stat().st_size,
        "sha256": sha256_file(OUTPUT_ISO),
        "render": "perspective_isometric_top_315_0_45",
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "release_gate": False,
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def protected_hashes() -> dict[str, str | None]:
    paths = (
        SOURCE_BOARD,
        BRANCH_SOURCE_BOARD,
        PS_BRANCH_BOARD,
        BOOT_BRANCH_BOARD,
        PS_ENGINE,
        J6_UTILITY,
        FORMAL_BOARD,
        FORMAL_SCHEMATIC,
        FORMAL_PROJECT,
        ROOT_README,
        B3_README,
        STATUS_HANDOFF,
    )
    return {str(path.resolve()): sha256_file(path) if path.is_file() else None for path in paths}


def rewrite_report(
    engine_exit: int,
    preflight: dict[str, object],
    protected_before: dict[str, str | None],
) -> int:
    report = json.loads(OUTPUT_REPORT.read_text(encoding="utf-8")) if OUTPUT_REPORT.is_file() else {}
    try:
        if engine_exit != 0:
            raise MergeError(f"PS_HOLD engine returned {engine_exit}")
        exact_merge = exact_merge_audit()
        mechanical = j6_mechanical_audit()
        drc_checks = report.get("drc_gate", {}).get("checks", {})
        candidate_open_by_net = report.get("drc_gate", {}).get(
            "candidate_unconnected_by_net", {}
        )
        drc_gate = {
            "source_violation_count_13": report.get("source_drc", {}).get("violation_count")
            == EXPECTED_DRC,
            "candidate_violation_count_13": report.get("candidate_drc", {}).get(
                "violation_count"
            )
            == EXPECTED_DRC,
            "source_open_117": report.get("source_drc", {}).get("unconnected_count")
            == EXPECTED_SOURCE_OPEN,
            "candidate_open_115": report.get("candidate_drc", {}).get("unconnected_count")
            == EXPECTED_CANDIDATE_OPEN,
            "ps_hold_zero": candidate_open_by_net.get("/PS_HOLD", 0) == 0,
            "dcdc_en_zero": candidate_open_by_net.get("/DCDC_EN", 0) == 0,
            "boot_n_zero": candidate_open_by_net.get("/BOOT_N", 0) == 0,
            "parity_zero": report.get("candidate_drc", {}).get("schematic_parity_count") == 0,
            "violation_identity_unchanged": drc_checks.get(
                "inherited_violation_identity_exact"
            )
            is True,
            "other_net_unconnected_counts_unchanged": drc_checks.get(
                "all_other_unconnected_counts_unchanged"
            )
            is True,
        }
        verifier_summary = report.get("board_verifier", {}).get("summary", {})
        engine_checks = {
            "routing_checks_passed": report.get("routing_checks_passed") is True,
            "double_build_byte_identical": report.get("determinism", {}).get(
                "double_build_byte_identical"
            )
            is True,
            "source_preservation_passed": report.get("source_preservation_audit", {}).get(
                "passed"
            )
            is True,
            "source_uuid_intersection_zero": report.get("source_preservation_audit", {})
            .get("checks", {})
            .get("new_uuid_source_intersection_zero")
            is True,
            "known_sibling_uuid_intersections_zero": report.get("uuid_namespace_audit", {}).get(
                "passed"
            )
            is True,
            "board_verifier_13_of_13": verifier_summary
            == {"total": 13, "passed": 13, "failed": 0},
        }
        if not all(drc_gate.values()):
            raise MergeError("R11 DRC/connectivity gate failed: " + json.dumps(drc_gate))
        if not all(engine_checks.values()):
            raise MergeError("R11 engine gate failed: " + json.dumps(engine_checks))
        iso = render_isometric(base.find_kicad_cli())
        protected_after = protected_hashes()
        if protected_before != protected_after:
            raise MergeError("protected source/dependency changed during R11 merge")
        report.update(
            {
                "operating_mode": "REVISION",
                "mode": "STAGING_ONLY_EXACT_PS_HOLD_BRANCH_MERGE",
                "revision": "R11_R10_PS_HOLD_UNIFIED_STAGING",
                "state": "R11_R10_PS_HOLD_UNIFIED_ROUTED_CANDIDATE",
                "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD",
                "routing_checks_passed": True,
                "locally_verified": False,
                "source": {
                    "role": "sole_editable_PCB_geometry_source",
                    "path": str(SOURCE_BOARD.resolve()),
                    "sha256": SOURCE_SHA256,
                },
                "builder": {
                    "path": str(Path(__file__).resolve()),
                    "ps_hold_engine": {
                        "path": str(PS_ENGINE.resolve()),
                        "sha256": PS_ENGINE_SHA256,
                        "routing_uuid_seed": ps.ROUTING_UUID_SEED,
                    },
                    "j6_mechanical_utility": {
                        "path": str(J6_UTILITY.resolve()),
                        "sha256": J6_UTILITY_SHA256,
                    },
                },
                "preflight_branch_applicability_audit": preflight,
                "exact_branch_delta_audit": exact_merge,
                "j6_mechanical_audit": mechanical,
                "r11_drc_connectivity_gate": {"passed": True, "checks": drc_gate},
                "r11_engine_gate": {"passed": True, "checks": engine_checks},
                "protected_sources": {
                    "unchanged": True,
                    "before": protected_before,
                    "after": protected_after,
                },
            }
        )
        report["output"] = {
            "path": str(OUTPUT_BOARD),
            "bytes": OUTPUT_BOARD.stat().st_size,
            "sha256": sha256_file(OUTPUT_BOARD),
        }
        report.setdefault("artifacts", {})["isometric_3d"] = iso
        report["visual_review_inputs"] = {
            "top": str(OUTPUT_TOP),
            "bottom": str(OUTPUT_BOTTOM),
            "isometric_3d": str(OUTPUT_ISO),
            "review_status": "GENERATED_FOR_AGENT_VISUAL_REVIEW",
        }
        report["completed_scope"] = ["/DCDC_EN", "/BOOT_N", "/PS_HOLD"]
        report["inherited_completed_scope"] = ["/DCDC_EN", "/BOOT_N"]
        report["holds"] = [
            {
                "scope": "J6_CONNECTOR_AUTHORITY",
                "reason": "placement clearance passes; exact connector/pack/mating authority remains HOLD",
            },
            {
                "scope": "WHOLE_BOARD",
                "reason": "115 unrelated/held unconnected items remain; not manufacturing-ready",
            },
        ]
        OUTPUT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        report.update(
            {
                "operating_mode": "REVISION",
                "mode": "STAGING_ONLY_EXACT_PS_HOLD_BRANCH_MERGE",
                "revision": "R11_R10_PS_HOLD_UNIFIED_STAGING",
                "state": "R11_R10_PS_HOLD_UNIFIED_HOLD",
                "overall_status": "HOLD",
                "routing_checks_passed": False,
                "locally_verified": False,
                "merge_error": f"{type(exc).__name__}: {exc}",
                "merge_traceback": traceback.format_exc(),
                "preflight_branch_applicability_audit": preflight,
                "protected_sources_before": protected_before,
            }
        )
        STAGING.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 2


def verify_hash_bound_inputs() -> None:
    expected = (
        (SOURCE_BOARD, SOURCE_SHA256),
        (BRANCH_SOURCE_BOARD, BRANCH_SOURCE_SHA256),
        (PS_BRANCH_BOARD, PS_BRANCH_SHA256),
        (BOOT_BRANCH_BOARD, BOOT_BRANCH_SHA256),
        (PS_ENGINE, PS_ENGINE_SHA256),
        (J6_UTILITY, J6_UTILITY_SHA256),
    )
    mismatches = [
        str(path)
        for path, digest in expected
        if not path.is_file() or sha256_file(path) != digest
    ]
    if mismatches:
        raise MergeError("hash-bound input missing or changed: " + ", ".join(mismatches))


def main(argv: Iterable[str] | None = None) -> int:
    verify_hash_bound_inputs()
    locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
    if locks:
        raise MergeError("close KiCad first: " + ", ".join(str(path) for path in locks))
    protected_before = protected_hashes()
    preflight = preflight_audit()
    configure_ps_engine()
    engine_exit = ps.main(argv)
    result = rewrite_report(engine_exit, preflight, protected_before)
    summary = json.loads(OUTPUT_REPORT.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "state": summary.get("state"),
                "routing_checks_passed": summary.get("routing_checks_passed"),
                "output": summary.get("output"),
                "drc": summary.get("r11_drc_connectivity_gate"),
                "report": str(OUTPUT_REPORT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        STAGING.mkdir(parents=True, exist_ok=True)
        failure = {
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_EXACT_PS_HOLD_BRANCH_MERGE",
            "revision": "R11_R10_PS_HOLD_UNIFIED_STAGING",
            "state": "R11_R10_PS_HOLD_UNIFIED_FAILED",
            "overall_status": "HOLD",
            "routing_checks_passed": False,
            "locally_verified": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
        OUTPUT_REPORT.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        raise SystemExit(2)
