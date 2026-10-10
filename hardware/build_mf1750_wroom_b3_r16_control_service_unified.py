#!/usr/bin/env python3
"""Strictly unify proven R12 control/service route branches in staging.

Operating mode: REVISION, staging-only.  The SHA-bound R12 PCB is the sole
geometry source.  This builder imports the exact additive copper deltas from
the independently verified button-remediation, MCU_EN, UART0, and JTAG
branches.  It never creates or edits route geometry and never relaxes a gate.

The candidate is intentionally retained as HOLD evidence if independently
valid branches conflict after unification.  Formal PCB/project/schematic,
source branches, routing registry, README, and STATUS files are protected
read-only inputs.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Iterable

import route_mf1750_wroom_b3_boot_n_r8e as boot


pcbnew = boot.pcbnew
base = boot.base

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r12_r11_user_key_2_n_routed.kicad_pcb"
SOURCE_SHA256 = "3a92f2aa31292032f38fcbae7152e67d20ef1cf50e0e619f6243faf3abe32ea3"

BRANCHES: tuple[dict[str, Any], ...] = (
    {
        "label": "BUTTON_CONFLICT_REMEDIATED",
        "path": STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated.kicad_pcb",
        "sha256": "4cccd877a42f0e787af73183fa70548f64ac2bb00d7461cede542bc1f840d19a",
        "report": STAGING / "r13_r12_button_conflict_remediation_report.json",
        "added": 43,
        "tracks": 39,
        "vias": 4,
        "net_counts": {"/PWR_BUTTON_N": 19, "/USER_KEY_1_N": 24},
        "open": 106,
    },
    {
        "label": "MCU_EN",
        "path": STAGING / "mf1750_wroom_b3_power_tf_r14_r12_mcu_en_routed.kicad_pcb",
        "sha256": "3124fe582fbebf0f21d7ac98b9f5293044223e22ed6dd4a7b6a61d6fc0b6d635",
        "report": STAGING / "r14_r12_mcu_en_route_report.json",
        "added": 54,
        "tracks": 46,
        "vias": 8,
        "net_counts": {"/MCU_EN": 54},
        "open": 107,
    },
    {
        "label": "UART0_PAIR",
        "path": STAGING / "mf1750_wroom_b3_power_tf_r14_r12_uart0_pair_routed.kicad_pcb",
        "sha256": "a6435943f5b282c4d30df68b1b1b884bee827d6aa48afe39e876a3a40772fa53",
        "report": STAGING / "r14_r12_uart0_pair_route_report.json",
        "added": 19,
        "tracks": 12,
        "vias": 7,
        "net_counts": {"/UART0_RX": 9, "/UART0_TX": 10},
        "open": 110,
    },
    {
        "label": "JTAG_BUNDLE",
        "path": STAGING / "mf1750_wroom_b3_power_tf_r15_r12_jtag_bundle_routed.kicad_pcb",
        "sha256": "4bda0980e05cc60f1543ecc54acfa3894841e3aab0f670d55a97bc6312dbef9e",
        "report": STAGING / "r15_r12_jtag_bundle_route_report.json",
        "added": 32,
        "tracks": 20,
        "vias": 12,
        "net_counts": {
            "/JTAG_GPIO39": 8,
            "/JTAG_GPIO40": 8,
            "/JTAG_GPIO41": 8,
            "/JTAG_GPIO42": 8,
        },
        "open": 108,
    },
)

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified.kicad_pcb"
OUTPUT_REPORT = STAGING / "r16_r13_control_service_unified_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r16_r13_control_service_unified_source_drc.json"
OUTPUT_DRC = STAGING / "r16_r13_control_service_unified_drc.json"
OUTPUT_VERIFIER = STAGING / "r16_r13_control_service_unified_board_verifier.json"
PREVIEW_DIR = STAGING / "r16_r13_control_service_unified_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified_bottom.png"
OUTPUT_FRONT = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified_front.svg"
OUTPUT_BACK = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified_back.svg"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r16_r13_control_service_unified_iso.png"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"
UUID_REGISTRY = B3_DIR / "ROUTING_UUID_SEEDS.json"

EXPECTED_SOURCE_COPPER = 1321
EXPECTED_ADDED_COPPER = 148
EXPECTED_ADDED_TRACKS = 117
EXPECTED_ADDED_VIAS = 31
EXPECTED_CANDIDATE_COPPER = 1469
EXPECTED_SOURCE_DRC = 13
EXPECTED_CANDIDATE_DRC = 13
EXPECTED_SOURCE_OPEN = 112
EXPECTED_CANDIDATE_OPEN = 95
EXPECTED_OPEN_REDUCTION = 17
EXPECTED_J6_POSITION_MM = (13.75, 120.0)
EXPECTED_J6_ROTATION_DEG = 0.0

COMPLETED_NETS = (
    "/DCDC_EN",
    "/BOOT_N",
    "/PS_HOLD",
    "/USER_KEY_1_N",
    "/USER_KEY_2_N",
    "/PWR_BUTTON_N",
    "/MCU_EN",
    "/UART0_RX",
    "/UART0_TX",
    "/JTAG_GPIO39",
    "/JTAG_GPIO40",
    "/JTAG_GPIO41",
    "/JTAG_GPIO42",
)
TARGET_NETS = frozenset(COMPLETED_NETS)
SOURCE_TARGET_OPEN = {
    "/DCDC_EN": 0,
    "/BOOT_N": 0,
    "/PS_HOLD": 0,
    "/USER_KEY_1_N": 3,
    "/USER_KEY_2_N": 0,
    "/PWR_BUTTON_N": 3,
    "/MCU_EN": 5,
    "/UART0_RX": 1,
    "/UART0_TX": 1,
    "/JTAG_GPIO39": 1,
    "/JTAG_GPIO40": 1,
    "/JTAG_GPIO41": 1,
    "/JTAG_GPIO42": 1,
}


class MergeError(RuntimeError):
    """Fail-closed R16 unification error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_board(path: Path):
    board = pcbnew.LoadBoard(str(path.resolve()))
    if board is None:
        raise MergeError(f"KiCad could not load board: {path}")
    return board


def signature_digest(signatures: dict[str, object], ids: set[str]) -> str:
    payload = {item_id: signatures[item_id] for item_id in sorted(ids)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list).encode("utf-8")
    ).hexdigest()


def verified_inputs() -> dict[str, object]:
    paths = {"source": (SOURCE_BOARD, SOURCE_SHA256)}
    for branch in BRANCHES:
        paths[str(branch["label"])] = (branch["path"], branch["sha256"])
    evidence: dict[str, object] = {}
    mismatches: list[str] = []
    for label, (path, wanted) in paths.items():
        actual = sha256_file(path) if path.is_file() else None
        passed = actual == wanted
        evidence[label] = {
            "path": str(path.resolve()),
            "expected_sha256": wanted,
            "actual_sha256": actual,
            "passed": passed,
        }
        if not passed:
            mismatches.append(label)
    if mismatches:
        raise MergeError("hash-bound PCB input mismatch: " + ", ".join(mismatches))

    reports: dict[str, object] = {}
    for branch in BRANCHES:
        path = branch["report"]
        if not path.is_file():
            raise MergeError(f"branch report missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload.get("board_verifier", {}).get("summary", {})
        checks = {
            "routing_checks_passed": payload.get("routing_checks_passed") is True,
            "output_sha256_exact": payload.get("output", {}).get("sha256") == branch["sha256"],
            "drc_13": payload.get("candidate_drc", {}).get("violation_count") == 13,
            "open_exact": payload.get("candidate_drc", {}).get("unconnected_count") == branch["open"],
            "parity_zero": payload.get("candidate_drc", {}).get("schematic_parity_count") == 0,
            "double_build_byte_identical": payload.get("determinism", {}).get("double_build_byte_identical") is True,
            "verifier_13_of_13": summary == {"total": 13, "passed": 13, "failed": 0},
        }
        reports[str(branch["label"])] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "identity_policy": "SEMANTIC_GATE_VALIDATED_TIMESTAMPED_REPORT",
            "checks": checks,
            "passed": all(checks.values()),
        }
        if not all(checks.values()):
            raise MergeError(f"branch report semantic gate failed: {branch['label']}")
    return {"pcbs": evidence, "reports": reports, "passed": True}


def branch_delta(branch: dict[str, Any], source_state: dict[str, object]) -> dict[str, Any]:
    board = load_board(branch["path"])
    state = base.source_state(board)
    source_ids = set(source_state["tracks"])
    branch_ids = set(state["tracks"])
    added = branch_ids - source_ids
    removed = source_ids - branch_ids
    changed = {
        item_id
        for item_id in source_ids & branch_ids
        if source_state["tracks"][item_id] != state["tracks"][item_id]
    }
    objects = {base.item_uuid(item): item for item in board.GetTracks()}
    net_counts = collections.Counter(objects[item_id].GetNetname() for item_id in added)
    tracks = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    vias = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    checks = {
        "source_copper_uuid_unique": source_state["copper_uuid_audit"]["passed"] is True,
        "branch_copper_uuid_unique": state["copper_uuid_audit"]["passed"] is True,
        "pure_additive_no_removed": not removed,
        "pure_additive_no_changed": not changed,
        "added_count_exact": len(added) == branch["added"],
        "added_track_count_exact": tracks == branch["tracks"],
        "added_via_count_exact": vias == branch["vias"],
        "added_net_counts_exact": dict(sorted(net_counts.items())) == branch["net_counts"],
        "footprints_exact": source_state["footprints"] == state["footprints"],
        "zones_exact": source_state["zones"] == state["zones"],
    }
    if not all(checks.values()):
        raise MergeError(
            f"{branch['label']} is not the exact pure-additive R12 branch: "
            + json.dumps(checks, sort_keys=True)
        )
    return {
        "label": branch["label"],
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source_ids),
        "branch_copper_count": len(branch_ids),
        "added_count": len(added),
        "added_track_count": tracks,
        "added_via_count": vias,
        "added_net_counts": dict(sorted(net_counts.items())),
        "added_uuids": sorted(added),
        "removed_uuids": sorted(removed),
        "changed_source_uuids": sorted(changed),
        "added_signature_sha256": signature_digest(state["tracks"], added),
        "_board": board,
        "_state": state,
        "_added": added,
        "_objects": objects,
    }


def clean_private(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean_private(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [clean_private(item) for item in value]
    if isinstance(value, tuple):
        return [clean_private(item) for item in value]
    return value


def preflight_audit() -> dict[str, Any]:
    source_board = load_board(SOURCE_BOARD)
    source_state = base.source_state(source_board)
    if len(source_state["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise MergeError(f"R12 source copper count drift: {len(source_state['tracks'])}")
    deltas = [branch_delta(branch, source_state) for branch in BRANCHES]
    source_ids = set(source_state["tracks"])
    intersections: dict[str, list[str]] = {}
    for index, left in enumerate(deltas):
        intersections[f"{left['label']}__SOURCE"] = sorted(left["_added"] & source_ids)
        for right in deltas[index + 1 :]:
            intersections[f"{left['label']}__{right['label']}"] = sorted(
                left["_added"] & right["_added"]
            )
    union = set().union(*(delta["_added"] for delta in deltas))
    checks = {
        "source_copper_count_1321": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "all_delta_uuid_sets_disjoint_from_source": all(
            not values for key, values in intersections.items() if key.endswith("__SOURCE")
        ),
        "all_delta_uuid_sets_pairwise_disjoint": all(
            not values for key, values in intersections.items() if not key.endswith("__SOURCE")
        ),
        "delta_union_count_148": len(union) == EXPECTED_ADDED_COPPER,
        "all_delta_nets_exactly_targeted": set().union(
            *(set(delta["added_net_counts"]) for delta in deltas)
        ) == TARGET_NETS - {"/DCDC_EN", "/BOOT_N", "/PS_HOLD", "/USER_KEY_2_N"},
    }
    if not all(checks.values()):
        raise MergeError("branch namespace preflight failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "pairwise_and_source_uuid_intersections": intersections,
        "branch_deltas": [clean_private(delta) for delta in deltas],
        "delta_union_uuid_count": len(union),
        "delta_union_uuids": sorted(union),
        "_source_state": source_state,
        "_deltas": deltas,
        "_union": union,
    }


def clone_branch_item(item):
    cloned = pcbnew.Cast_to_BOARD_ITEM(item.Clone())
    if base.item_uuid(cloned) != base.item_uuid(item):
        raise MergeError("KiCad Clone() did not preserve branch item UUID")
    return cloned


def build_candidate(destination: Path, preflight: dict[str, Any]) -> dict[str, object]:
    board = load_board(SOURCE_BOARD)
    source_ids = set(preflight["_source_state"]["tracks"])
    imported: set[str] = set()
    import_order: list[dict[str, object]] = []
    for delta in preflight["_deltas"]:
        branch_imported: list[str] = []
        for item_id in sorted(delta["_added"]):
            item = delta["_objects"][item_id]
            board.Add(clone_branch_item(item))
            imported.add(item_id)
            branch_imported.append(item_id)
        import_order.append({"branch": delta["label"], "uuids": branch_imported})
    checks = {
        "imported_uuid_set_exact_delta_union": imported == preflight["_union"],
        "imported_uuid_count_148": len(imported) == EXPECTED_ADDED_COPPER,
        "imported_uuids_disjoint_from_source": not (imported & source_ids),
        "in_memory_copper_count_1469": len(board.GetTracks()) == EXPECTED_CANDIDATE_COPPER,
    }
    if not all(checks.values()):
        raise MergeError("candidate replay failed: " + json.dumps(checks, sort_keys=True))
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise MergeError(f"failed to save candidate: {destination}")
    return {"passed": True, "checks": checks, "import_order": import_order}


def exact_candidate_audit(preflight: dict[str, Any]) -> dict[str, object]:
    source_board = load_board(SOURCE_BOARD)
    candidate_board = load_board(OUTPUT_BOARD)
    source = base.source_state(source_board)
    candidate = base.source_state(candidate_board)
    source_ids = set(source["tracks"])
    candidate_ids = set(candidate["tracks"])
    added = candidate_ids - source_ids
    removed = source_ids - candidate_ids
    changed = {
        item_id
        for item_id in source_ids & candidate_ids
        if source["tracks"][item_id] != candidate["tracks"][item_id]
    }
    geometry_mismatch: dict[str, list[str]] = {}
    for delta in preflight["_deltas"]:
        geometry_mismatch[delta["label"]] = sorted(
            item_id
            for item_id in delta["_added"]
            if candidate["tracks"].get(item_id) != delta["_state"]["tracks"][item_id]
        )
    objects = {base.item_uuid(item): item for item in candidate_board.GetTracks()}
    net_counts = collections.Counter(objects[item_id].GetNetname() for item_id in added)
    tracks = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    vias = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    expected_net_counts: collections.Counter[str] = collections.Counter()
    for branch in BRANCHES:
        expected_net_counts.update(branch["net_counts"])
    source_j6 = source_board.FindFootprintByReference("J6")
    candidate_j6 = candidate_board.FindFootprintByReference("J6")
    if source_j6 is None or candidate_j6 is None:
        raise MergeError("J6 missing from source or candidate")
    j6_source_position = base.point_mm(source_j6.GetPosition())
    j6_candidate_position = base.point_mm(candidate_j6.GetPosition())
    j6_source_rotation = round(float(source_j6.GetOrientationDegrees()) % 360.0, 6)
    j6_candidate_rotation = round(float(candidate_j6.GetOrientationDegrees()) % 360.0, 6)
    checks = {
        "candidate_copper_uuid_unique": candidate["copper_uuid_audit"]["passed"] is True,
        "candidate_copper_count_1469": len(candidate_ids) == EXPECTED_CANDIDATE_COPPER,
        "actual_added_exact_delta_union": added == preflight["_union"],
        "actual_removed_source_zero": not removed,
        "actual_changed_source_zero": not changed,
        "all_branch_uuid_geometry_exact": all(not values for values in geometry_mismatch.values()),
        "added_track_count_117": tracks == EXPECTED_ADDED_TRACKS,
        "added_via_count_31": vias == EXPECTED_ADDED_VIAS,
        "added_net_counts_exact": net_counts == expected_net_counts,
        "footprints_exact": source["footprints"] == candidate["footprints"],
        "zones_exact": source["zones"] == candidate["zones"],
        "j6_source_position_exact": j6_source_position == EXPECTED_J6_POSITION_MM,
        "j6_candidate_position_exact": j6_candidate_position == EXPECTED_J6_POSITION_MM,
        "j6_source_rotation_exact": j6_source_rotation == EXPECTED_J6_ROTATION_DEG,
        "j6_candidate_rotation_exact": j6_candidate_rotation == EXPECTED_J6_ROTATION_DEG,
        "j6_footprint_signature_exact": base.footprint_signature(source_j6)
        == base.footprint_signature(candidate_j6),
    }
    if not all(checks.values()):
        raise MergeError("exact candidate audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source_ids),
        "candidate_copper_count": len(candidate_ids),
        "added_count": len(added),
        "added_track_count": tracks,
        "added_via_count": vias,
        "added_net_counts": dict(sorted(net_counts.items())),
        "added_uuids": sorted(added),
        "removed_source_uuids": sorted(removed),
        "changed_source_uuids": sorted(changed),
        "branch_geometry_mismatch_uuids": geometry_mismatch,
        "j6": {
            "source_position_mm": list(j6_source_position),
            "candidate_position_mm": list(j6_candidate_position),
            "source_rotation_deg": j6_source_rotation,
            "candidate_rotation_deg": j6_candidate_rotation,
        },
    }


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for entry in raw.get("unconnected_items", []):
        names: list[str] = []
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


def conflict_evidence(
    source_raw: dict[str, object], candidate_raw: dict[str, object], preflight: dict[str, Any]
) -> dict[str, object]:
    source_fps = set(map(repr, violation_fingerprints(source_raw)))
    ownership: dict[str, str] = {}
    for delta in preflight["_deltas"]:
        ownership.update({item_id: delta["label"] for item_id in delta["_added"]})
    ownership.update({item_id: "R12_SOURCE" for item_id in preflight["_source_state"]["tracks"]})
    new: list[dict[str, object]] = []
    owner_pairs: collections.Counter[str] = collections.Counter()
    for violation in candidate_raw.get("violations", []):
        items = []
        fp_items = []
        owners = set()
        for item in violation.get("items", []):
            position = item.get("pos", {})
            item_id = str(item.get("uuid", ""))
            owner = ownership.get(item_id, "NON_COPPER_OR_UNKNOWN")
            owners.add(owner)
            point = {
                "x": round(float(position.get("x", 0.0)), 6),
                "y": round(float(position.get("y", 0.0)), 6),
            }
            fp_items.append((item_id, point["x"], point["y"]))
            items.append(
                {
                    "uuid": item_id,
                    "position_mm": point,
                    "description": str(item.get("description", "")),
                    "owner": owner,
                }
            )
        fingerprint = (str(violation.get("type", "")), tuple(sorted(fp_items)))
        if repr(fingerprint) in source_fps:
            continue
        owner_key = "__".join(sorted(owners))
        owner_pairs[owner_key] += 1
        new.append(
            {
                "type": str(violation.get("type", "")),
                "description": str(violation.get("description", "")),
                "items": items,
                "owner_set": sorted(owners),
                "fingerprint": clean_private(fingerprint),
            }
        )
    return {
        "new_violation_count": len(new),
        "new_violation_categories": dict(sorted(collections.Counter(item["type"] for item in new).items())),
        "cross_branch_owner_pair_counts": dict(sorted(owner_pairs.items())),
        "new_violations": new,
    }


def drc_connectivity_gate(
    source: dict[str, object], candidate: dict[str, object], preflight: dict[str, Any]
) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    for net in COMPLETED_NETS:
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - TARGET_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_fps = violation_fingerprints(source["raw"])
    candidate_fps = violation_fingerprints(candidate["raw"])
    conflict = conflict_evidence(source["raw"], candidate["raw"], preflight)
    checks = {
        "source_drc_13": source["violation_count"] == EXPECTED_SOURCE_DRC,
        "candidate_drc_13": candidate["violation_count"] == EXPECTED_CANDIDATE_DRC,
        "inherited_violation_uuid_position_fingerprint_exact": source_fps == candidate_fps,
        "source_open_112": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_95": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_17": source["unconnected_count"] - candidate["unconnected_count"]
        == EXPECTED_OPEN_REDUCTION,
        "source_target_open_counts_exact": all(
            source_nets.get(net, 0) == count for net, count in SOURCE_TARGET_OPEN.items()
        ),
        "all_13_completed_nets_zero": all(candidate_nets.get(net, 0) == 0 for net in COMPLETED_NETS),
        "all_non_target_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_fingerprints": clean_private(source_fps),
        "candidate_violation_fingerprints": clean_private(candidate_fps),
        "conflict_evidence": conflict,
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r16-control-iso-") as name:
        temporary = Path(name)
        outputs = [temporary / "iso1.png", temporary / "iso2.png"]
        hashes: list[str] = []
        commands: list[list[str]] = []
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
                cwd=B3_DIR,
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
        "path": str(OUTPUT_ISO.resolve()),
        "bytes": OUTPUT_ISO.stat().st_size,
        "sha256": sha256_file(OUTPUT_ISO),
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def protected_paths() -> dict[str, Path]:
    paths = {
        "formal_board": FORMAL_BOARD,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
        "root_readme": ROOT_README,
        "b3_readme": B3_README,
        "status_handoff": STATUS_HANDOFF,
        "uuid_registry": UUID_REGISTRY,
        "source_board": SOURCE_BOARD,
    }
    for branch in BRANCHES:
        paths[f"branch_{branch['label']}"] = branch["path"]
        paths[f"report_{branch['label']}"] = branch["report"]
    return paths


def protected_hashes() -> dict[str, str | None]:
    return {
        label: sha256_file(path) if path.is_file() else None
        for label, path in protected_paths().items()
    }


def parse_args(argv: Iterable[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kicad-python",
        type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
    )
    return parser.parse_args(argv)


def write_failure(exc: Exception, partial: dict[str, object]) -> None:
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operating_mode": "REVISION",
        "mode": "STAGING_ONLY_STRICT_CONTROL_SERVICE_BRANCH_UNIFICATION",
        "revision": "R16_R13_CONTROL_SERVICE_UNIFIED_STAGING",
        "state": "R16_R13_CONTROL_SERVICE_UNIFICATION_FAILED",
        "overall_status": "HOLD",
        "operation_completed": False,
        "routing_checks_passed": False,
        "locally_verified": False,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "network_accessed": False,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
        **partial,
    }
    STAGING.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(
        json.dumps(clean_private(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    partial: dict[str, object] = {}
    try:
        if pcbnew is None or str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise MergeError("KiCad 10 pcbnew required")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise MergeError("close KiCad first: " + ", ".join(str(path) for path in locks))

        inputs = verified_inputs()
        partial["inputs"] = inputs
        protected_before = protected_hashes()
        preflight = preflight_audit()
        partial["preflight"] = clean_private(preflight)
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)

        with tempfile.TemporaryDirectory(prefix="mf1750-r16-control-") as name:
            temporary = Path(name)
            first = temporary / "first.kicad_pcb"
            second = temporary / "second.kicad_pcb"
            replay = build_candidate(first, preflight)
            replay2 = build_candidate(second, preflight)
            first_sha = sha256_file(first)
            second_sha = sha256_file(second)
            deterministic = first.read_bytes() == second.read_bytes() and replay == replay2
            if not deterministic or first_sha != second_sha:
                raise MergeError("double build is not byte-identical")
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)

        exact = exact_candidate_audit(preflight)
        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        OUTPUT_SOURCE_DRC.write_text(
            json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        OUTPUT_DRC.write_text(
            json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        gate = drc_connectivity_gate(source_drc, candidate_drc, preflight)

        verifier = boot.r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)
        if not verifier["passed"]:
            raise MergeError(f"board verifier failed: {verifier.get('summary')}")
        OUTPUT_VERIFIER.write_text(
            json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        renders = [
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_TOP, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_BOTTOM, "bottom"),
            base.export_svg(
                kicad_cli,
                OUTPUT_BOARD,
                OUTPUT_FRONT,
                "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts",
            ),
            base.export_svg(
                kicad_cli,
                OUTPUT_BOARD,
                OUTPUT_BACK,
                "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts",
                mirror=True,
            ),
        ]
        iso = render_isometric(kicad_cli)
        protected_after = protected_hashes()
        if protected_before != protected_after:
            raise MergeError("protected source/formal/document hash changed during build")

        passed = gate["passed"] is True
        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_STRICT_CONTROL_SERVICE_BRANCH_UNIFICATION",
            "revision": "R16_R13_CONTROL_SERVICE_UNIFIED_STAGING",
            "state": (
                "R16_R13_CONTROL_SERVICE_UNIFIED_CANDIDATE"
                if passed
                else "R16_R13_CONTROL_SERVICE_UNIFIED_CROSS_BRANCH_DRC_HOLD"
            ),
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD" if passed else "HOLD",
            "operation_completed": True,
            "routing_checks_passed": passed,
            "locally_verified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "network_accessed": False,
            "inputs": inputs,
            "builder": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "kicad": {"version": str(pcbnew.GetBuildVersion()), "cli": str(kicad_cli)},
            "preflight": clean_private(preflight),
            "deterministic_replay": replay,
            "determinism": {
                "double_build_byte_identical": True,
                "first_sha256": first_sha,
                "second_sha256": second_sha,
            },
            "exact_candidate_audit": exact,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_connectivity_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "protected_sources": {
                "unchanged": True,
                "before": protected_before,
                "after": protected_after,
            },
            "output": {
                "path": str(OUTPUT_BOARD.resolve()),
                "bytes": OUTPUT_BOARD.stat().st_size,
                "sha256": sha256_file(OUTPUT_BOARD),
                "classification": "STAGING_HOLD_EVIDENCE" if not passed else "STAGING_CANDIDATE",
            },
            "completed_scope": list(COMPLETED_NETS) if passed else [],
            "holds": (
                [
                    {
                        "scope": "CROSS_BRANCH_GEOMETRY",
                        "reason": (
                            f"strict merge introduces {gate['conflict_evidence']['new_violation_count']} "
                            "new DRC fingerprints; exact branch objects are recorded and no route was changed"
                        ),
                    },
                    {
                        "scope": "WHOLE_BOARD",
                        "reason": "candidate is HOLD evidence only and must not be promoted to the formal PCB",
                    },
                ]
                if not passed
                else [
                    {
                        "scope": "WHOLE_BOARD",
                        "reason": f"{candidate_drc['unconnected_count']} unrelated/held items remain; not manufacturing-ready",
                    }
                ]
            ),
            "artifacts": {
                "source_drc_json": str(OUTPUT_SOURCE_DRC.resolve()),
                "candidate_drc_json": str(OUTPUT_DRC.resolve()),
                "board_verifier_json": str(OUTPUT_VERIFIER.resolve()),
                "top_preview": str(OUTPUT_TOP.resolve()),
                "bottom_preview": str(OUTPUT_BOTTOM.resolve()),
                "front_copper_svg": str(OUTPUT_FRONT.resolve()),
                "back_copper_svg": str(OUTPUT_BACK.resolve()),
                "isometric_3d": iso,
                "render_export": renders,
            },
        }
        OUTPUT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
                        "new_conflicts": gate["conflict_evidence"]["new_violation_count"],
                    },
                    "verifier": verifier["summary"],
                    "report": str(OUTPUT_REPORT.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if passed else 2
    except Exception as exc:
        write_failure(exc, partial)
        print(OUTPUT_REPORT.read_text(encoding="utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
