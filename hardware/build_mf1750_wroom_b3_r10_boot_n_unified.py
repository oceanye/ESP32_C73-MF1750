#!/usr/bin/env python3
"""Merge the proven BOOT_N copper into the frozen R9 staging candidate.

Operating mode: REVISION.  The sole editable geometry source is the SHA-bound
R9 DCDC_EN/J6-clearance PCB.  The 20 BOOT_N objects are replayed by the frozen
R8e BOOT_N builder, then compared UUID-for-UUID and geometry-for-geometry with
the already verified R8e branch delta.  No source copper or footprint moves.
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

BOOT_ENGINE = HARDWARE / "route_mf1750_wroom_b3_boot_n_r8e.py"
BOOT_ENGINE_SHA256 = "e286488409b537a12159c6d3c91f6f800292e7ead9f8460885eda7f60d8c551d"
J6_UTILITY = HARDWARE / "build_mf1750_wroom_b3_r8d_j6_c49_hand_solder_clearance.py"
J6_UTILITY_SHA256 = "d8f7b8c610b1598ec204f5475ab032b18c5ed5f7eb2a9c0d62d3a8b2236438e8"

SOURCE_BOARD = (
    STAGING / "mf1750_wroom_b3_power_tf_r9_dcdc_en_j6_clearance_fallback.kicad_pcb"
)
SOURCE_SHA256 = "5bd6dde973d95508855cc9c9b886f0030b6a9892caa3b99b6ebc542ae7a09b18"
BRANCH_SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
BRANCH_SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"
BRANCH_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_boot_n_routed.kicad_pcb"
BRANCH_BOARD_SHA256 = "2a1f76928cfa17de688949be06c410bdedccf6dbe7b1ddbe2b0080d907e0ab7e"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified.kicad_pcb"
OUTPUT_REPORT = STAGING / "r10_r9_boot_n_unified_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r10_r9_boot_n_unified_source_drc.json"
OUTPUT_DRC = STAGING / "r10_r9_boot_n_unified_drc.json"
OUTPUT_VERIFIER = STAGING / "r10_r9_boot_n_unified_board_verifier.json"
PREVIEW_DIR = STAGING / "r10_r9_boot_n_unified_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified_bottom.png"
OUTPUT_FRONT = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified_front.svg"
OUTPUT_BACK = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified_back.svg"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified_iso.png"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"

EXPECTED_SOURCE_COPPER = 1263
EXPECTED_CANDIDATE_COPPER = 1283
EXPECTED_ADDED_TRACKS = 16
EXPECTED_ADDED_VIAS = 4
EXPECTED_SOURCE_UNCONNECTED = 120
EXPECTED_CANDIDATE_UNCONNECTED = 117
EXPECTED_DRC = 13
EXPECTED_J6_POSITION_MM = (13.75, 120.0)
EXPECTED_J6_ROTATION_DEG = 0.0
MIN_J6_C49_COURTYARD_MM = 1.03


class MergeError(RuntimeError):
    """Fail-closed R10 unified-candidate error."""


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


boot = load_module(BOOT_ENGINE, BOOT_ENGINE_SHA256, "_mf1750_r10_boot_engine")
j6c = load_module(J6_UTILITY, J6_UTILITY_SHA256, "_mf1750_r10_j6_utility")
pcbnew = boot.pcbnew
base = boot.base


def configure_boot_engine() -> None:
    boot.SOURCE_BOARD = SOURCE_BOARD
    boot.SOURCE_SHA256 = SOURCE_SHA256
    boot.OUTPUT_BOARD = OUTPUT_BOARD
    boot.REPORT_JSON = OUTPUT_REPORT
    boot.SOURCE_DRC_JSON = OUTPUT_SOURCE_DRC
    boot.CANDIDATE_DRC_JSON = OUTPUT_DRC
    boot.BOARD_VERIFIER_JSON = OUTPUT_VERIFIER
    boot.PREVIEW_DIR = PREVIEW_DIR
    boot.TOP_PREVIEW = OUTPUT_TOP
    boot.BOTTOM_PREVIEW = OUTPUT_BOTTOM
    boot.FRONT_COPPER_SVG = OUTPUT_FRONT
    boot.BACK_COPPER_SVG = OUTPUT_BACK


def track_map(board) -> dict[str, object]:
    return {base.item_uuid(item): item for item in board.GetTracks()}


def track_signatures(board) -> dict[str, object]:
    return {base.item_uuid(item): base.track_signature(item) for item in board.GetTracks()}


def exact_branch_delta_audit() -> dict[str, object]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD))
    candidate = pcbnew.LoadBoard(str(OUTPUT_BOARD))
    branch_source = pcbnew.LoadBoard(str(BRANCH_SOURCE_BOARD))
    branch = pcbnew.LoadBoard(str(BRANCH_BOARD))
    if any(board is None for board in (source, candidate, branch_source, branch)):
        raise MergeError("could not load boards for exact branch-delta audit")

    source_sigs = track_signatures(source)
    candidate_sigs = track_signatures(candidate)
    branch_source_sigs = track_signatures(branch_source)
    branch_sigs = track_signatures(branch)
    source_ids = set(source_sigs)
    candidate_ids = set(candidate_sigs)
    branch_source_ids = set(branch_source_sigs)
    branch_ids = set(branch_sigs)
    actual_added_ids = candidate_ids - source_ids
    branch_added_ids = branch_ids - branch_source_ids
    actual_added = {uuid: candidate_sigs[uuid] for uuid in actual_added_ids}
    branch_added = {uuid: branch_sigs[uuid] for uuid in branch_added_ids}

    candidate_objects = track_map(candidate)
    actual_objects = [candidate_objects[uuid] for uuid in sorted(actual_added_ids)]
    track_count = sum(not isinstance(item, pcbnew.PCB_VIA) for item in actual_objects)
    via_count = sum(isinstance(item, pcbnew.PCB_VIA) for item in actual_objects)
    checks = {
        "r9_source_copper_count_1263": len(source_sigs) == EXPECTED_SOURCE_COPPER,
        "candidate_copper_count_1283": len(candidate_sigs) == EXPECTED_CANDIDATE_COPPER,
        "r9_and_branch_source_copper_uuid_geometry_exact": source_sigs == branch_source_sigs,
        "all_r9_source_copper_uuid_geometry_exact": all(
            uuid in candidate_sigs and candidate_sigs[uuid] == signature
            for uuid, signature in source_sigs.items()
        ),
        "added_uuid_intersection_with_r9_source_zero": not (actual_added_ids & source_ids),
        "branch_added_exactly_20": len(branch_added_ids) == 20,
        "candidate_added_exactly_20": len(actual_added_ids) == 20,
        "candidate_added_uuid_set_exactly_branch": actual_added_ids == branch_added_ids,
        "candidate_added_uuid_geometry_exactly_branch": actual_added == branch_added,
        "candidate_added_16_tracks": track_count == EXPECTED_ADDED_TRACKS,
        "candidate_added_4_vias": via_count == EXPECTED_ADDED_VIAS,
        "candidate_added_boot_n_only": {item.GetNetname() for item in actual_objects}
        == {"/BOOT_N"},
    }
    if not all(checks.values()):
        raise MergeError("exact branch-delta audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source_sigs),
        "candidate_copper_count": len(candidate_sigs),
        "added_track_count": track_count,
        "added_via_count": via_count,
        "added_uuids": sorted(actual_added_ids),
        "added_signature_sha256": hashlib.sha256(
            json.dumps(actual_added, sort_keys=True, default=list).encode("utf-8")
        ).hexdigest(),
        "branch_evidence": {
            "source": {"path": str(BRANCH_SOURCE_BOARD.resolve()), "sha256": BRANCH_SOURCE_SHA256},
            "candidate": {"path": str(BRANCH_BOARD.resolve()), "sha256": BRANCH_BOARD_SHA256},
            "builder": {"path": str(BOOT_ENGINE.resolve()), "sha256": BOOT_ENGINE_SHA256},
        },
    }


def j6_mechanical_audit() -> dict[str, object]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD))
    candidate = pcbnew.LoadBoard(str(OUTPUT_BOARD))
    if source is None or candidate is None:
        raise MergeError("could not load boards for J6 mechanical audit")
    source_j6 = source.FindFootprintByReference("J6")
    candidate_j6 = candidate.FindFootprintByReference("J6")
    source_c49 = source.FindFootprintByReference("C49")
    candidate_c49 = candidate.FindFootprintByReference("C49")
    if any(item is None for item in (source_j6, candidate_j6, source_c49, candidate_c49)):
        raise MergeError("J6/C49 missing from mechanical audit")
    source_j6_box = j6c.courtyard_bbox(source_j6)
    candidate_j6_box = j6c.courtyard_bbox(candidate_j6)
    source_c49_box = j6c.courtyard_bbox(source_c49)
    candidate_c49_box = j6c.courtyard_bbox(candidate_c49)
    source_gap = j6c.rect_gap(source_j6_box, source_c49_box)[2]
    candidate_gap = j6c.rect_gap(candidate_j6_box, candidate_c49_box)[2]
    source_position = tuple(round(value, 6) for value in j6c.edge.point_mm(source_j6.GetPosition()))
    candidate_position = tuple(
        round(value, 6) for value in j6c.edge.point_mm(candidate_j6.GetPosition())
    )
    source_rotation = round(float(source_j6.GetOrientationDegrees()) % 360.0, 6)
    candidate_rotation = round(float(candidate_j6.GetOrientationDegrees()) % 360.0, 6)
    checks = {
        "source_j6_position_exactly_13p75_120": source_position == EXPECTED_J6_POSITION_MM,
        "candidate_j6_position_exactly_13p75_120": candidate_position == EXPECTED_J6_POSITION_MM,
        "source_j6_rotation_zero": source_rotation == EXPECTED_J6_ROTATION_DEG,
        "candidate_j6_rotation_zero": candidate_rotation == EXPECTED_J6_ROTATION_DEG,
        "j6_transform_unchanged": (
            source_position == candidate_position and source_rotation == candidate_rotation
        ),
        "source_j6_c49_courtyard_gap_at_least_1p03": source_gap >= MIN_J6_C49_COURTYARD_MM,
        "candidate_j6_c49_courtyard_gap_at_least_1p03": candidate_gap
        >= MIN_J6_C49_COURTYARD_MM,
        "j6_c49_courtyard_gap_unchanged": source_gap == candidate_gap,
        "j6_track_or_via_hits_zero": not j6c.pad_track_hits(candidate, "J6"),
        "c49_track_or_via_hits_zero": not j6c.pad_track_hits(candidate, "C49"),
    }
    if not all(checks.values()):
        raise MergeError("J6 mechanical audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source": {
            "j6_position_mm": list(source_position),
            "j6_rotation_deg": source_rotation,
            "j6_courtyard_bbox_mm": source_j6_box,
            "c49_courtyard_bbox_mm": source_c49_box,
            "j6_c49_gap_mm": source_gap,
        },
        "candidate": {
            "j6_position_mm": list(candidate_position),
            "j6_rotation_deg": candidate_rotation,
            "j6_courtyard_bbox_mm": candidate_j6_box,
            "c49_courtyard_bbox_mm": candidate_c49_box,
            "j6_c49_gap_mm": candidate_gap,
        },
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r10-boot-iso-") as name:
        temp_dir = Path(name)
        outputs = [temp_dir / "iso1.png", temp_dir / "iso2.png"]
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
        BRANCH_BOARD,
        BOOT_ENGINE,
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
    protected_before: dict[str, str | None],
    extra_error: str | None = None,
) -> int:
    report = (
        json.loads(OUTPUT_REPORT.read_text(encoding="utf-8"))
        if OUTPUT_REPORT.is_file()
        else {}
    )
    try:
        if engine_exit != 0:
            raise MergeError(f"BOOT_N engine returned {engine_exit}")
        exact_delta = exact_branch_delta_audit()
        mechanical = j6_mechanical_audit()
        drc_checks = report.get("drc_gate", {}).get("checks", {})
        drc_gate = {
            "source_violation_count_13": report.get("source_drc", {}).get("violation_count")
            == EXPECTED_DRC,
            "candidate_violation_count_13": report.get("candidate_drc", {}).get("violation_count")
            == EXPECTED_DRC,
            "source_open_120": report.get("source_drc", {}).get("unconnected_count")
            == EXPECTED_SOURCE_UNCONNECTED,
            "candidate_open_117": report.get("candidate_drc", {}).get("unconnected_count")
            == EXPECTED_CANDIDATE_UNCONNECTED,
            "boot_n_zero": drc_checks.get("candidate_boot_n_unconnected_zero") is True,
            "dcdc_en_zero": drc_checks.get("candidate_dcdc_en_unconnected_zero") is True,
            "ps_hold_remains_two": report.get("drc_gate", {})
            .get("candidate_unconnected_by_net", {})
            .get("/PS_HOLD", 0)
            == 2,
            "parity_zero": report.get("candidate_drc", {}).get("schematic_parity_count") == 0,
            "violation_identity_unchanged": drc_checks.get(
                "inherited_violation_uuid_position_identity_exact"
            )
            is True,
            "other_net_unconnected_counts_unchanged": drc_checks.get(
                "other_net_unconnected_counts_unchanged"
            )
            is True,
        }
        if not all(drc_gate.values()):
            raise MergeError("R10 DRC/connectivity closure failed: " + json.dumps(drc_gate))
        verifier_summary = report.get("board_verifier", {}).get("summary", {})
        if verifier_summary != {"total": 13, "passed": 13, "failed": 0}:
            raise MergeError(f"board verifier not 13/13: {verifier_summary}")
        kicad_cli = base.find_kicad_cli()
        iso = render_isometric(kicad_cli)
        protected_after = protected_hashes()
        if protected_before != protected_after:
            raise MergeError("protected source/dependency changed during R10 build")

        report.update(
            {
                "operating_mode": "REVISION",
                "mode": "STAGING_ONLY_EXACT_BOOT_N_BRANCH_MERGE",
                "revision": "R10_R9_BOOT_N_UNIFIED_STAGING",
                "state": "R10_R9_BOOT_N_UNIFIED_ROUTED_CANDIDATE",
                "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD",
                "locally_verified": False,
                "routing_checks_passed": True,
                "source": {
                    "role": "sole_editable_PCB_geometry_source",
                    "path": str(SOURCE_BOARD.resolve()),
                    "sha256": SOURCE_SHA256,
                },
                "builder": {
                    "path": str(Path(__file__).resolve()),
                    "boot_n_engine": {
                        "path": str(BOOT_ENGINE.resolve()),
                        "sha256": BOOT_ENGINE_SHA256,
                    },
                    "j6_mechanical_utility": {
                        "path": str(J6_UTILITY.resolve()),
                        "sha256": J6_UTILITY_SHA256,
                    },
                },
                "exact_branch_delta_audit": exact_delta,
                "j6_mechanical_audit": mechanical,
                "r10_drc_connectivity_gate": {"passed": True, "checks": drc_gate},
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
        report["completed_scope"] = ["/BOOT_N"]
        report["holds"] = [
            {"scope": "/PS_HOLD", "reason": "remains at two ratlines; not part of this merge"},
            {
                "scope": "J6_CONNECTOR_AUTHORITY",
                "reason": "placement clearance passes; exact connector/pack/mating authority remains HOLD",
            },
            {
                "scope": "WHOLE_BOARD",
                "reason": "117 unrelated/held unconnected items remain; not manufacturing-ready",
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
                "mode": "STAGING_ONLY_EXACT_BOOT_N_BRANCH_MERGE",
                "revision": "R10_R9_BOOT_N_UNIFIED_STAGING",
                "state": "R10_R9_BOOT_N_UNIFIED_HOLD",
                "overall_status": "HOLD",
                "locally_verified": False,
                "routing_checks_passed": False,
                "merge_error": extra_error or f"{type(exc).__name__}: {exc}",
                "merge_traceback": traceback.format_exc(),
                "protected_sources_before": protected_before,
            }
        )
        STAGING.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 2


def main(argv: Iterable[str] | None = None) -> int:
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise MergeError("sole R9 source missing or SHA-256 mismatched")
    if not BRANCH_SOURCE_BOARD.is_file() or sha256_file(BRANCH_SOURCE_BOARD) != BRANCH_SOURCE_SHA256:
        raise MergeError("BOOT_N branch source evidence missing or SHA-256 mismatched")
    if not BRANCH_BOARD.is_file() or sha256_file(BRANCH_BOARD) != BRANCH_BOARD_SHA256:
        raise MergeError("BOOT_N branch candidate evidence missing or SHA-256 mismatched")
    locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
    if locks:
        raise MergeError("close KiCad first: " + ", ".join(str(path) for path in locks))
    protected_before = protected_hashes()
    configure_boot_engine()
    engine_exit = boot.main(argv)
    result = rewrite_report(engine_exit, protected_before)
    summary = json.loads(OUTPUT_REPORT.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "state": summary.get("state"),
                "routing_checks_passed": summary.get("routing_checks_passed"),
                "output": summary.get("output"),
                "drc": summary.get("r10_drc_connectivity_gate"),
                "report": str(OUTPUT_REPORT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
