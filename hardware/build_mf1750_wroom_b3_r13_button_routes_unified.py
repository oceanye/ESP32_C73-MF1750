#!/usr/bin/env python3
"""Unify the three proven button-route branches on the frozen R12 PCB.

Operating mode: REVISION, staging-only.  The SHA-bound R12 USER_KEY_2_N
candidate is the sole editable geometry source.  This builder replays the
frozen USER_KEY_1_N and PWR_BUTTON_N route generators without altering their
geometry.  Before building, it derives every branch delta UUID-for-UUID from
the frozen source/result pairs and proves that all three deltas are additive,
mutually disjoint, and disjoint from the R11 copper namespace.

The build fails closed on any new DRC fingerprint, any non-target open-net
drift, any source geometry change, any branch-geometry mismatch, or any J6
transform drift.  Formal PCB/project/schematic and handoff documents are
protected read-only inputs and are never written.
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
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

R11_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified.kicad_pcb"
R11_SHA256 = "74d1e8a023e6aae67049b96e39d7210b9e66f42427cec7394053d76433e97d43"
SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r12_r11_user_key_2_n_routed.kicad_pcb"
SOURCE_SHA256 = "3a92f2aa31292032f38fcbae7152e67d20ef1cf50e0e619f6243faf3abe32ea3"

KEY2_BUILDER = HARDWARE / "route_mf1750_wroom_b3_user_key_2_n_r12.py"
KEY2_BUILDER_SHA256 = "b4bc903b872b997d2060a9fe681a3d76ca56774a7df43100a015ddcaae9875cf"
KEY2_REPORT = STAGING / "r12_r11_user_key_2_n_route_report.json"
KEY2_REPORT_SHA256 = "f2ac9142151beb13cfac5ac797e004eb2229c61a85ee8d5a475341f2a67152c3"

KEY1_BUILDER = HARDWARE / "route_mf1750_wroom_b3_user_key_1_n_r10.py"
KEY1_BUILDER_SHA256 = "318e4355820381b11979a37d8f7374f14b510e428e7437bea08a9630bd7e94b7"
KEY1_SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r10_r9_boot_n_unified.kicad_pcb"
KEY1_SOURCE_SHA256 = "53ec067d73cbca12de0c874f2576b84dfe3120a544a43393c23f38dd283e08d0"
KEY1_BRANCH_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_user_key_1_n_routed.kicad_pcb"
KEY1_BRANCH_SHA256 = "da582e0aee383b2354db0cfc1b637b5446944c09c7f02b653fb720c05d1307cc"
KEY1_REPORT = STAGING / "r11_user_key_1_n_route_report.json"
KEY1_REPORT_SHA256 = "0ad318e19834016338be05c49bc797cc9b1a7b5a89c1a0d4e590c2a80f27c5a3"

PWR_BUILDER = HARDWARE / "route_mf1750_wroom_b3_pwr_button_n_r8e.py"
PWR_BUILDER_SHA256 = "18c769f55a452e71c3a0cf1a0c963413bcf754875926cd56f6a21dfc1208a126"
PWR_SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8d_edge_dcdc_en_routed.kicad_pcb"
PWR_SOURCE_SHA256 = "0784823edb50fa642f38784ddc30b420ef7731447cc6920396dc7e5275365ada"
PWR_BRANCH_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r8e_pwr_button_n_routed.kicad_pcb"
PWR_BRANCH_SHA256 = "2a75e712ed6d8c4e38e21527ee4e27cd55832c7342001d7c2918f5e29adc65c4"
PWR_REPORT = STAGING / "r8e_pwr_button_n_route_report.json"
PWR_REPORT_SHA256 = "8170ec22c23bbbeed68ad389f0dfe3faf6f0619e3636d81ac6c72334c18ac23c"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified.kicad_pcb"
OUTPUT_REPORT = STAGING / "r13_r12_button_routes_unified_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r13_r12_button_routes_unified_source_drc.json"
OUTPUT_DRC = STAGING / "r13_r12_button_routes_unified_drc.json"
OUTPUT_VERIFIER = STAGING / "r13_r12_button_routes_unified_board_verifier.json"
PREVIEW_DIR = STAGING / "r13_r12_button_routes_unified_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified_bottom.png"
OUTPUT_FRONT = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified_front.svg"
OUTPUT_BACK = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified_back.svg"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified_iso.png"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
ROOT_README = ROOT / "README.md"
B3_README = B3_DIR / "README.md"
STATUS_HANDOFF = ROOT / "docs" / "STATUS_HANDOFF.md"
SEED_LEDGER = B3_DIR / "ROUTING_UUID_SEEDS.json"

EXPECTED_R11_COPPER = 1299
EXPECTED_SOURCE_COPPER = 1321
EXPECTED_CANDIDATE_COPPER = 1367
EXPECTED_KEY1_ADDED = 27
EXPECTED_KEY2_ADDED = 22
EXPECTED_PWR_ADDED = 19
EXPECTED_SOURCE_OPEN = 112
EXPECTED_CANDIDATE_OPEN = 106
EXPECTED_DRC = 13
TARGET_NETS = frozenset({"/USER_KEY_1_N", "/PWR_BUTTON_N"})
ALL_COMPLETED_NETS = (
    "/DCDC_EN",
    "/BOOT_N",
    "/PS_HOLD",
    "/USER_KEY_1_N",
    "/USER_KEY_2_N",
    "/PWR_BUTTON_N",
)
EXPECTED_J6_POSITION_MM = (13.75, 120.0)
EXPECTED_J6_ROTATION_DEG = 0.0


class MergeError(RuntimeError):
    """Fail-closed R13 unified button-route error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, expected_sha256: str, name: str):
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise MergeError(f"frozen builder missing or hash-mismatched: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise MergeError(f"could not import frozen builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


key1 = load_module(KEY1_BUILDER, KEY1_BUILDER_SHA256, "_mf1750_r13_key1")
pwr = load_module(PWR_BUILDER, PWR_BUILDER_SHA256, "_mf1750_r13_pwr")
pcbnew = key1.pcbnew
base = key1.base


def verified_inputs() -> dict[str, dict[str, object]]:
    expected = {
        "r11_board": (R11_BOARD, R11_SHA256),
        "r12_key2_source": (SOURCE_BOARD, SOURCE_SHA256),
        "key2_builder": (KEY2_BUILDER, KEY2_BUILDER_SHA256),
        "key1_builder": (KEY1_BUILDER, KEY1_BUILDER_SHA256),
        "key1_source": (KEY1_SOURCE_BOARD, KEY1_SOURCE_SHA256),
        "key1_branch": (KEY1_BRANCH_BOARD, KEY1_BRANCH_SHA256),
        "pwr_builder": (PWR_BUILDER, PWR_BUILDER_SHA256),
        "pwr_source": (PWR_SOURCE_BOARD, PWR_SOURCE_SHA256),
        "pwr_branch": (PWR_BRANCH_BOARD, PWR_BRANCH_SHA256),
    }
    evidence: dict[str, dict[str, object]] = {}
    bad = []
    for role, (path, wanted) in expected.items():
        actual = sha256_file(path) if path.is_file() else None
        passed = actual == wanted
        evidence[role] = {
            "path": str(path.resolve()),
            "expected_sha256": wanted,
            "actual_sha256": actual,
            "passed": passed,
        }
        if not passed:
            bad.append(role)
    if bad:
        raise MergeError("hash-bound input mismatch: " + ", ".join(bad))
    # Route reports contain generation timestamps and are therefore not stable
    # identities when a frozen builder is independently re-run.  Bind the
    # builders and PCBs above; record the reports' current hashes here and
    # validate their semantic gates in preflight_audit().
    for role, path, former_freeze in (
        ("key2_report", KEY2_REPORT, KEY2_REPORT_SHA256),
        ("key1_report", KEY1_REPORT, KEY1_REPORT_SHA256),
        ("pwr_report", PWR_REPORT, PWR_REPORT_SHA256),
    ):
        if not path.is_file():
            raise MergeError(f"branch report missing: {path}")
        evidence[role] = {
            "path": str(path.resolve()),
            "actual_sha256": sha256_file(path),
            "former_freeze_sha256": former_freeze,
            "identity_policy": "SEMANTIC_GATE_VALIDATED_TIMESTAMPED_REPORT",
            "passed": True,
        }
    return evidence


def load_state(path: Path) -> tuple[Any, dict[str, object]]:
    board = pcbnew.LoadBoard(str(path.resolve()))
    if board is None:
        raise MergeError(f"KiCad could not load PCB: {path}")
    return board, base.source_state(board)


def signature_digest(signatures: dict[str, object], ids: set[str]) -> str:
    payload = {item_id: signatures[item_id] for item_id in sorted(ids)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list).encode("utf-8")
    ).hexdigest()


def branch_delta(
    label: str,
    source_path: Path,
    branch_path: Path,
    expected_added: int,
    expected_net: str,
) -> dict[str, object]:
    source_board, source = load_state(source_path)
    branch_board, branch = load_state(branch_path)
    source_ids = set(source["tracks"])
    branch_ids = set(branch["tracks"])
    added = branch_ids - source_ids
    removed = source_ids - branch_ids
    changed = {
        item_id
        for item_id in source_ids & branch_ids
        if source["tracks"][item_id] != branch["tracks"][item_id]
    }
    objects = {base.item_uuid(item): item for item in branch_board.GetTracks()}
    nets = collections.Counter(objects[item_id].GetNetname() for item_id in added)
    tracks = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    vias = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    checks = {
        "source_copper_uuid_unique": source["copper_uuid_audit"]["passed"] is True,
        "branch_copper_uuid_unique": branch["copper_uuid_audit"]["passed"] is True,
        "pure_additive_no_removed": not removed,
        "pure_additive_no_changed": not changed,
        "added_count_exact": len(added) == expected_added,
        "added_net_exact": dict(nets) == {expected_net: expected_added},
        "footprints_exact": source["footprints"] == branch["footprints"],
        "zones_exact": source["zones"] == branch["zones"],
    }
    if not all(checks.values()):
        raise MergeError(f"{label} frozen branch delta failed: {json.dumps(checks, sort_keys=True)}")
    return {
        "label": label,
        "passed": True,
        "checks": checks,
        "source_path": str(source_path.resolve()),
        "branch_path": str(branch_path.resolve()),
        "source_copper_count": len(source_ids),
        "branch_copper_count": len(branch_ids),
        "added_count": len(added),
        "added_track_count": tracks,
        "added_via_count": vias,
        "added_net_counts": dict(sorted(nets.items())),
        "added_uuids": sorted(added),
        "removed_uuids": sorted(removed),
        "changed_uuids": sorted(changed),
        "added_signature_sha256": signature_digest(branch["tracks"], added),
        "_added_set": added,
        "_branch_signatures": branch["tracks"],
    }


def strip_private(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_private(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [strip_private(item) for item in value]
    return value


def preflight_audit() -> dict[str, object]:
    _, r11 = load_state(R11_BOARD)
    _, source = load_state(SOURCE_BOARD)
    key2_delta = branch_delta(
        "USER_KEY_2_N", R11_BOARD, SOURCE_BOARD, EXPECTED_KEY2_ADDED, "/USER_KEY_2_N"
    )
    key1_delta = branch_delta(
        "USER_KEY_1_N",
        KEY1_SOURCE_BOARD,
        KEY1_BRANCH_BOARD,
        EXPECTED_KEY1_ADDED,
        "/USER_KEY_1_N",
    )
    pwr_delta = branch_delta(
        "PWR_BUTTON_N",
        PWR_SOURCE_BOARD,
        PWR_BRANCH_BOARD,
        EXPECTED_PWR_ADDED,
        "/PWR_BUTTON_N",
    )
    deltas = {"key2": key2_delta, "key1": key1_delta, "pwr": pwr_delta}
    sets = {name: item["_added_set"] for name, item in deltas.items()}
    r11_ids = set(r11["tracks"])
    source_ids = set(source["tracks"])
    pairwise = {
        "key1_key2": sorted(sets["key1"] & sets["key2"]),
        "key1_pwr": sorted(sets["key1"] & sets["pwr"]),
        "key2_pwr": sorted(sets["key2"] & sets["pwr"]),
    }
    branch_report_checks = {}
    for label, report_path, output_sha in (
        ("key1", KEY1_REPORT, KEY1_BRANCH_SHA256),
        ("key2", KEY2_REPORT, SOURCE_SHA256),
        ("pwr", PWR_REPORT, PWR_BRANCH_SHA256),
    ):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        branch_report_checks[label] = {
            "routing_checks_passed": report.get("routing_checks_passed") is True,
            "output_sha256_exact": report.get("output", {}).get("sha256") == output_sha,
            "candidate_drc_13": report.get("candidate_drc", {}).get("violation_count") == EXPECTED_DRC,
            "parity_zero": report.get("candidate_drc", {}).get("schematic_parity_count") == 0,
            "deterministic": report.get("determinism", {}).get("double_build_byte_identical") is True,
            "verifier_13_of_13": report.get("board_verifier", {}).get("summary")
            == {"total": 13, "passed": 13, "failed": 0},
        }
    checks = {
        "r11_copper_count_1299": len(r11_ids) == EXPECTED_R11_COPPER,
        "r12_source_copper_count_1321": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "r12_is_exact_r11_plus_key2_delta": source_ids == r11_ids | sets["key2"],
        "r12_retains_all_r11_geometry_exact": all(
            source["tracks"].get(item_id) == signature for item_id, signature in r11["tracks"].items()
        ),
        "key2_geometry_exact_in_r12": all(
            source["tracks"].get(item_id) == key2_delta["_branch_signatures"][item_id]
            for item_id in sets["key2"]
        ),
        "all_three_delta_uuid_sets_pairwise_disjoint": all(not items for items in pairwise.values()),
        "all_three_delta_uuid_sets_disjoint_from_r11": not (
            (sets["key1"] | sets["key2"] | sets["pwr"]) & r11_ids
        ),
        "key1_and_pwr_delta_disjoint_from_r12_source": not (
            (sets["key1"] | sets["pwr"]) & source_ids
        ),
        "all_branch_reports_pass_frozen_gates": all(
            all(item.values()) for item in branch_report_checks.values()
        ),
    }
    if not all(checks.values()):
        raise MergeError("R13 branch preflight failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "branch_deltas": {name: strip_private(item) for name, item in deltas.items()},
        "pairwise_uuid_intersections": pairwise,
        "branch_report_checks": branch_report_checks,
        "_deltas": deltas,
    }


def build_candidate(destination: Path, preflight: dict[str, object]):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise MergeError("KiCad could not load frozen R12 source")
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise MergeError(f"R12 source copper count drift: {len(before['tracks'])}")
    key1_scope = key1.validate_scope(board)
    pwr_scope = pwr.validate_scope(board)
    key1_objects = key1.add_routes(board)
    key1_ids = {base.item_uuid(item) for item in key1_objects}
    pwr_objects = pwr.add_routes(board)
    pwr_ids = {base.item_uuid(item) for item in pwr_objects}
    deltas = preflight["_deltas"]
    checks = {
        "key1_replay_uuid_set_exact": key1_ids == deltas["key1"]["_added_set"],
        "pwr_replay_uuid_set_exact": pwr_ids == deltas["pwr"]["_added_set"],
        "replay_uuid_sets_disjoint": not (key1_ids & pwr_ids),
        "replay_uuid_sets_disjoint_from_source": not ((key1_ids | pwr_ids) & set(before["tracks"])),
    }
    if not all(checks.values()):
        raise MergeError("deterministic branch replay failed: " + json.dumps(checks, sort_keys=True))
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise MergeError(f"failed to save candidate: {destination}")
    return before, key1_ids, pwr_ids, {
        "passed": True,
        "checks": checks,
        "key1_scope": key1_scope,
        "pwr_scope": pwr_scope,
    }


def exact_merge_audit(
    before: dict[str, object], key1_ids: set[str], pwr_ids: set[str], preflight: dict[str, object]
) -> dict[str, object]:
    source_board, source = load_state(SOURCE_BOARD)
    candidate_board, candidate = load_state(OUTPUT_BOARD)
    source_ids = set(source["tracks"])
    candidate_ids = set(candidate["tracks"])
    added = candidate_ids - source_ids
    removed = source_ids - candidate_ids
    changed = {
        item_id
        for item_id in source_ids & candidate_ids
        if source["tracks"][item_id] != candidate["tracks"][item_id]
    }
    expected_added = key1_ids | pwr_ids
    deltas = preflight["_deltas"]
    key1_geometry = all(
        candidate["tracks"].get(item_id) == deltas["key1"]["_branch_signatures"][item_id]
        for item_id in key1_ids
    )
    pwr_geometry = all(
        candidate["tracks"].get(item_id) == deltas["pwr"]["_branch_signatures"][item_id]
        for item_id in pwr_ids
    )
    base.ALLOWED_NETS = TARGET_NETS
    preservation = base.audit_candidate(candidate_board, before, expected_added)
    key1_envelope = key1.envelope_audit(candidate_board, key1_ids)
    pwr_envelope = pwr.envelope_audit(candidate_board, pwr_ids)
    objects = {base.item_uuid(item): item for item in candidate_board.GetTracks()}
    added_nets = collections.Counter(objects[item_id].GetNetname() for item_id in added)
    added_tracks = sum(not isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    added_vias = sum(isinstance(objects[item_id], pcbnew.PCB_VIA) for item_id in added)
    checks = {
        "candidate_copper_count_1367": len(candidate_ids) == EXPECTED_CANDIDATE_COPPER,
        "actual_added_exactly_key1_plus_pwr": added == expected_added,
        "actual_removed_zero": not removed,
        "actual_changed_source_zero": not changed,
        "key1_uuid_geometry_exactly_frozen_branch": key1_geometry,
        "pwr_uuid_geometry_exactly_frozen_branch": pwr_geometry,
        "added_net_counts_exact": dict(added_nets)
        == {"/USER_KEY_1_N": EXPECTED_KEY1_ADDED, "/PWR_BUTTON_N": EXPECTED_PWR_ADDED},
        "added_track_count_39": added_tracks == 39,
        "added_via_count_7": added_vias == 7,
        "source_preservation_passed": preservation["passed"] is True,
        "key1_envelope_passed": key1_envelope["passed"] is True,
        "pwr_envelope_passed": pwr_envelope["passed"] is True,
        "footprints_exact": source["footprints"] == candidate["footprints"],
        "zones_exact": source["zones"] == candidate["zones"],
    }
    if not all(checks.values()):
        raise MergeError("R13 exact merge audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source_ids),
        "candidate_copper_count": len(candidate_ids),
        "added_count": len(added),
        "added_track_count": added_tracks,
        "added_via_count": added_vias,
        "added_net_counts": dict(sorted(added_nets.items())),
        "added_uuids": sorted(added),
        "removed_uuids": sorted(removed),
        "changed_source_uuids": sorted(changed),
        "source_preservation": preservation,
        "key1_envelope": key1_envelope,
        "pwr_envelope": pwr_envelope,
        "source_board_footprint_count": len(source_board.GetFootprints()),
    }


def j6_audit() -> dict[str, object]:
    source, _ = load_state(SOURCE_BOARD)
    candidate, _ = load_state(OUTPUT_BOARD)
    evidence = {}
    for label, board in (("source", source), ("candidate", candidate)):
        footprint = board.FindFootprintByReference("J6")
        if footprint is None:
            raise MergeError(f"J6 missing from {label}")
        evidence[label] = {
            "position_mm": list(base.point_mm(footprint.GetPosition())),
            "rotation_deg": round(float(footprint.GetOrientationDegrees()) % 360.0, 6),
            "signature": base.footprint_signature(footprint),
        }
    checks = {
        "source_position_exact_13p75_120": tuple(evidence["source"]["position_mm"])
        == EXPECTED_J6_POSITION_MM,
        "candidate_position_exact_13p75_120": tuple(evidence["candidate"]["position_mm"])
        == EXPECTED_J6_POSITION_MM,
        "source_rotation_zero": evidence["source"]["rotation_deg"] == EXPECTED_J6_ROTATION_DEG,
        "candidate_rotation_zero": evidence["candidate"]["rotation_deg"] == EXPECTED_J6_ROTATION_DEG,
        "transform_and_pad_contract_unchanged": evidence["source"]["signature"]
        == evidence["candidate"]["signature"],
    }
    if not all(checks.values()):
        raise MergeError("J6 audit failed: " + json.dumps(checks, sort_keys=True))
    return {"passed": True, "checks": checks, "evidence": evidence}


def unconnected_by_net(raw: dict[str, object]) -> dict[str, int]:
    return key1.boot.unconnected_by_net(raw)


def violation_fingerprints(raw: dict[str, object]) -> list[tuple[object, ...]]:
    return key1.boot.violation_fingerprints(raw)


def drc_connectivity_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_nets = unconnected_by_net(source["raw"])
    candidate_nets = unconnected_by_net(candidate["raw"])
    for net in ALL_COMPLETED_NETS:
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - TARGET_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    source_categories = collections.Counter(source["violation_categories"])
    candidate_categories = collections.Counter(candidate["violation_categories"])
    checks = {
        "source_violation_count_13": source["violation_count"] == EXPECTED_DRC,
        "candidate_violation_count_13": candidate["violation_count"] == EXPECTED_DRC,
        "violation_category_counts_exact": source_categories == candidate_categories,
        "violation_uuid_position_identity_exact": violation_fingerprints(source["raw"])
        == violation_fingerprints(candidate["raw"]),
        "source_open_112": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_106": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_6": source["unconnected_count"] - candidate["unconnected_count"] == 6,
        "source_key1_open_3": source_nets.get("/USER_KEY_1_N", 0) == 3,
        "source_pwr_button_open_3": source_nets.get("/PWR_BUTTON_N", 0) == 3,
        "candidate_key1_open_0": candidate_nets.get("/USER_KEY_1_N", 0) == 0,
        "candidate_pwr_button_open_0": candidate_nets.get("/PWR_BUTTON_N", 0) == 0,
        "all_completed_nets_zero": all(candidate_nets.get(net, 0) == 0 for net in ALL_COMPLETED_NETS),
        "all_non_target_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    if not all(checks.values()):
        raise MergeError("R13 DRC/connectivity gate failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "source_violation_fingerprints": violation_fingerprints(source["raw"]),
        "candidate_violation_fingerprints": violation_fingerprints(candidate["raw"]),
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r13-buttons-iso-") as name:
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
        "repeat_hashes": hashes,
        "byte_identical": hashes[0] == hashes[1],
        "classification": "VISUAL_EVIDENCE_ONLY_NOT_A_PCB_DETERMINISM_GATE",
        "commands": commands,
    }


def protected_paths() -> dict[str, Path]:
    return {
        "formal_board": FORMAL_BOARD,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
        "root_readme": ROOT_README,
        "b3_readme": B3_README,
        "status_handoff": STATUS_HANDOFF,
        "seed_ledger": SEED_LEDGER,
        "r11_board": R11_BOARD,
        "r12_source": SOURCE_BOARD,
        "key1_source": KEY1_SOURCE_BOARD,
        "key1_branch": KEY1_BRANCH_BOARD,
        "pwr_source": PWR_SOURCE_BOARD,
        "pwr_branch": PWR_BRANCH_BOARD,
        "key1_builder": KEY1_BUILDER,
        "key2_builder": KEY2_BUILDER,
        "pwr_builder": PWR_BUILDER,
    }


def protected_hashes() -> dict[str, str | None]:
    return {
        name: sha256_file(path) if path.is_file() else None
        for name, path in protected_paths().items()
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kicad-python",
        type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
    )
    return parser.parse_args(argv)


def write_failure(state: str, exc: Exception, extra: dict[str, object] | None = None) -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operating_mode": "REVISION",
        "mode": "STAGING_ONLY_EXACT_THREE_BUTTON_BRANCH_UNIFICATION",
        "revision": "R13_R12_BUTTON_ROUTES_UNIFIED_STAGING",
        "state": state,
        "overall_status": "HOLD",
        "routing_checks_passed": False,
        "locally_verified": False,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "network_accessed": False,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
    }
    if extra:
        report.update(extra)
    OUTPUT_REPORT.write_text(
        json.dumps(strip_private(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    preflight: dict[str, object] | None = None
    source_drc: dict[str, object] | None = None
    candidate_drc: dict[str, object] | None = None
    input_evidence: dict[str, dict[str, object]] | None = None
    replay: dict[str, object] | None = None
    exact_merge: dict[str, object] | None = None
    mechanical: dict[str, object] | None = None
    first_sha: str | None = None
    second_sha: str | None = None
    protected_before: dict[str, str | None] | None = None
    try:
        if pcbnew is None:
            raise MergeError("pcbnew unavailable")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise MergeError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise MergeError("close KiCad first: " + ", ".join(str(path) for path in locks))
        input_evidence = verified_inputs()
        protected_before = protected_hashes()
        preflight = preflight_audit()
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r13-buttons-") as name:
            temporary = Path(name)
            first = temporary / "first.kicad_pcb"
            second = temporary / "second.kicad_pcb"
            before, key1_ids, pwr_ids, replay = build_candidate(first, preflight)
            before2, key1_ids2, pwr_ids2, replay2 = build_candidate(second, preflight)
            deterministic = (
                first.read_bytes() == second.read_bytes()
                and before == before2
                and key1_ids == key1_ids2
                and pwr_ids == pwr_ids2
                and replay == replay2
            )
            if not deterministic:
                raise MergeError("R13 double build is not byte-deterministic")
            first_sha = sha256_file(first)
            second_sha = sha256_file(second)
            if first_sha != second_sha:
                raise MergeError("R13 deterministic SHA mismatch")
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)

        exact_merge = exact_merge_audit(before, key1_ids, pwr_ids, preflight)
        mechanical = j6_audit()
        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        # Persist the raw DRC evidence before the strict gate.  If the frozen
        # branches conflict, the HOLD report must remain independently
        # inspectable without relaxing or rerouting either branch.
        OUTPUT_SOURCE_DRC.write_text(
            json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        OUTPUT_DRC.write_text(
            json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        drc_gate = drc_connectivity_gate(source_drc, candidate_drc)
        verifier = key1.r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)
        if not verifier["passed"]:
            raise MergeError(f"board verifier failed: {verifier.get('summary')}")

        OUTPUT_SOURCE_DRC.write_text(
            json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        OUTPUT_DRC.write_text(
            json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        OUTPUT_VERIFIER.write_text(
            json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        renders = [
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_TOP, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_BOTTOM, "bottom"),
            base.export_svg(
                kicad_cli, OUTPUT_BOARD, OUTPUT_FRONT, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"
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
            raise MergeError("protected source/formal/document hash changed during R13 build")

        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_EXACT_THREE_BUTTON_BRANCH_UNIFICATION",
            "revision": "R13_R12_BUTTON_ROUTES_UNIFIED_STAGING",
            "state": "R13_R12_BUTTON_ROUTES_UNIFIED_CANDIDATE",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD",
            "routing_checks_passed": True,
            "locally_verified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "network_accessed": False,
            "input_hash_bindings": input_evidence,
            "source": {
                "role": "sole_editable_PCB_geometry_source",
                "path": str(SOURCE_BOARD.resolve()),
                "sha256": SOURCE_SHA256,
            },
            "builder": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
                "frozen_key1_builder": {"path": str(KEY1_BUILDER.resolve()), "sha256": KEY1_BUILDER_SHA256},
                "frozen_key2_builder": {"path": str(KEY2_BUILDER.resolve()), "sha256": KEY2_BUILDER_SHA256},
                "frozen_pwr_builder": {"path": str(PWR_BUILDER.resolve()), "sha256": PWR_BUILDER_SHA256},
            },
            "preflight_branch_delta_and_uuid_audit": strip_private(preflight),
            "deterministic_replay": replay,
            "determinism": {
                "double_build_byte_identical": True,
                "first_sha256": first_sha,
                "second_sha256": second_sha,
            },
            "exact_branch_merge_audit": exact_merge,
            "j6_mechanical_audit": mechanical,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_connectivity_gate": drc_gate,
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
            },
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
            "completed_scope": list(ALL_COMPLETED_NETS),
            "holds": [
                {
                    "scope": "J6_CONNECTOR_AUTHORITY",
                    "reason": "placement remains verified; exact pack/connector/line-order authority remains HOLD",
                },
                {
                    "scope": "WHOLE_BOARD",
                    "reason": "106 unrelated/held unconnected items remain; not manufacturing-ready",
                },
            ],
        }
        OUTPUT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "state": report["state"],
                    "routing_checks_passed": True,
                    "output": report["output"],
                    "drc": {
                        "violations": candidate_drc["violation_count"],
                        "unconnected": candidate_drc["unconnected_count"],
                        "schematic_parity": candidate_drc["schematic_parity_count"],
                    },
                    "verifier": verifier["summary"],
                    "report": str(OUTPUT_REPORT.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        failure_extra: dict[str, object] = {
            "preflight_branch_delta_and_uuid_audit": strip_private(preflight)
            if preflight
            else None,
            "input_hash_bindings": input_evidence,
            "deterministic_replay": replay,
            "determinism": {
                "double_build_byte_identical": first_sha is not None
                and first_sha == second_sha,
                "first_sha256": first_sha,
                "second_sha256": second_sha,
            },
            "exact_branch_merge_audit": exact_merge,
            "j6_mechanical_audit": mechanical,
            "protected_sources_before": protected_before,
        }
        if OUTPUT_BOARD.is_file():
            failure_extra["output"] = {
                "path": str(OUTPUT_BOARD.resolve()),
                "bytes": OUTPUT_BOARD.stat().st_size,
                "sha256": sha256_file(OUTPUT_BOARD),
                "classification": "HOLD_CONFLICT_EVIDENCE_NOT_PROMOTABLE",
            }
        if source_drc is not None:
            failure_extra["source_drc"] = {
                key: value for key, value in source_drc.items() if key != "raw"
            }
        if candidate_drc is not None:
            source_fingerprints = (
                set(map(repr, violation_fingerprints(source_drc["raw"])))
                if source_drc is not None
                else set()
            )
            candidate_fingerprints = set(
                map(repr, violation_fingerprints(candidate_drc["raw"]))
            )
            failure_extra["candidate_drc"] = {
                key: value for key, value in candidate_drc.items() if key != "raw"
            }
            failure_extra["new_violation_fingerprints"] = sorted(
                candidate_fingerprints - source_fingerprints
            )
        write_failure(
            "R13_R12_BUTTON_ROUTES_UNIFIED_HOLD",
            exc,
            failure_extra,
        )
        print(OUTPUT_REPORT.read_text(encoding="utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
