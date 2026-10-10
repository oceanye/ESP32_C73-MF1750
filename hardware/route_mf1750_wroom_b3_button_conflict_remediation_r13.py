#!/usr/bin/env python3
"""Remediate the proven three-button merge conflict on frozen R12.

Operating mode: REVISION, staging-only.  R12 (including USER_KEY_2_N) is the
sole editable geometry source.  The rejected R13 merge remains immutable
conflict evidence.  This builder creates a new USER_KEY_1_N route under the
reserved UUID seed 1750921, crossing the vertical PS_HOLD B.Cu trunk on F.Cu
and eliminating the via that was too close to the future
PWR_BUTTON_N In2.Cu trunk.  It then replays the frozen PWR_BUTTON_N delta
exactly, without changing any existing copper, footprint, or zone.
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
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

R13_EVIDENCE_BUILDER = HARDWARE / "build_mf1750_wroom_b3_r13_button_routes_unified.py"
R13_EVIDENCE_BUILDER_SHA256 = "6c51796126a0dddb82f0fd017468cfef2b608d9767398f85b727e240f4c77df9"
R13_EVIDENCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_routes_unified.kicad_pcb"
R13_EVIDENCE_BOARD_SHA256 = "f011920de2c3661bdfa813d935005819306d5aaa42dfc789fe9b16a8b833e004"
R13_EVIDENCE_REPORT = STAGING / "r13_r12_button_routes_unified_report.json"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated.kicad_pcb"
OUTPUT_REPORT = STAGING / "r13_r12_button_conflict_remediation_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r13_r12_button_conflict_remediation_source_drc.json"
OUTPUT_DRC = STAGING / "r13_r12_button_conflict_remediation_drc.json"
OUTPUT_VERIFIER = STAGING / "r13_r12_button_conflict_remediation_board_verifier.json"
PREVIEW_DIR = STAGING / "r13_r12_button_conflict_remediation_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated_bottom.png"
OUTPUT_FRONT = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated_front.svg"
OUTPUT_BACK = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated_back.svg"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r13_r12_button_conflict_remediated_iso.png"

ROUTING_UUID_SEED = 1750921
SIGNAL_WIDTH_MM = 0.20
VIA_DIAMETER_MM = 0.60
VIA_DRILL_MM = 0.30
EXPECTED_SOURCE_COPPER = 1321
EXPECTED_KEY1_TRACKS = 22
EXPECTED_KEY1_VIAS = 2
EXPECTED_KEY1_ADDED = EXPECTED_KEY1_TRACKS + EXPECTED_KEY1_VIAS
EXPECTED_PWR_ADDED = 19
EXPECTED_CANDIDATE_COPPER = 1364
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


class RouteError(RuntimeError):
    """Fail-closed R13 button-conflict remediation error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, expected_sha256: str, name: str):
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise RouteError(f"frozen dependency missing or hash-mismatched: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RouteError(f"could not import frozen dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


r13 = load_module(
    R13_EVIDENCE_BUILDER, R13_EVIDENCE_BUILDER_SHA256, "_mf1750_r13_conflict_evidence"
)
pcbnew = r13.pcbnew
base = r13.base
key1 = r13.key1
pwr = r13.pwr

SOURCE_BOARD = r13.SOURCE_BOARD
SOURCE_SHA256 = r13.SOURCE_SHA256
R11_BOARD = r13.R11_BOARD
R11_SHA256 = r13.R11_SHA256
PWR_SOURCE_BOARD = r13.PWR_SOURCE_BOARD
PWR_SOURCE_SHA256 = r13.PWR_SOURCE_SHA256
PWR_BRANCH_BOARD = r13.PWR_BRANCH_BOARD
PWR_BRANCH_SHA256 = r13.PWR_BRANCH_SHA256
PWR_BUILDER = r13.PWR_BUILDER
PWR_BUILDER_SHA256 = r13.PWR_BUILDER_SHA256
SEED_LEDGER = r13.SEED_LEDGER

FORMAL_BOARD = r13.FORMAL_BOARD
FORMAL_SCHEMATIC = r13.FORMAL_SCHEMATIC
FORMAL_PROJECT = r13.FORMAL_PROJECT
ROOT_README = r13.ROOT_README
B3_README = r13.B3_README
STATUS_HANDOFF = r13.STATUS_HANDOFF

# SW2 weave and R51 endpoint stay on F.Cu.  The old via at (4.0, 76.45)
# is removed entirely, providing 0.50 mm centre distance from the future PWR
# In2 trunk.  The short F.Cu diagonal crosses the immutable PS_HOLD vertical
# B.Cu trunk on a different layer; no vias are needed at either end.  The
# proven eastbound/tail geometry remains.
ROUTES: tuple[tuple[str, str, tuple[tuple[float, float], ...]], ...] = (
    (
        "/USER_KEY_1_N",
        "F.Cu",
        (
            (1.3500, 70.7000),
            (1.3500, 71.4000),
            (2.0000, 72.0500),
            (2.0000, 72.9500),
            (1.3500, 73.6000),
            (1.3500, 74.3000),
            (1.3500, 75.7000),
            (2.1000, 76.4500),
            (4.0000, 76.4500),
            (5.0000, 75.5000),
            (6.8000, 74.5000),
        ),
    ),
    (
        "/USER_KEY_1_N",
        "F.Cu",
        ((6.8000, 74.5000), (7.3500, 74.5000), (7.8250, 75.2000), (7.8250, 76.5000)),
    ),
    ("/USER_KEY_1_N", "F.Cu", ((6.8000, 74.5000), (14.2000, 72.9000))),
    ("/USER_KEY_1_N", "F.Cu", ((14.2000, 72.9000), (27.2000, 72.9000))),
    (
        "/USER_KEY_1_N",
        "B.Cu",
        (
            (27.2000, 72.9000),
            (27.8000, 75.0000),
            (27.8000, 77.0000),
            (38.5000, 77.0000),
            (40.0000, 78.0000),
            (41.5000, 79.2000),
            (42.3000, 80.2000),
            (43.2900, 81.2500),
        ),
    ),
)

VIAS: tuple[tuple[str, float, float], ...] = (
    ("/USER_KEY_1_N", 27.2000, 72.9000),
    ("/USER_KEY_1_N", 43.2900, 81.2500),
)


def seed_registry_audit() -> dict[str, object]:
    ledger = json.loads(SEED_LEDGER.read_text(encoding="utf-8"))
    rows = [
        row
        for row in ledger.get("assignments", [])
        if int(row.get("seed_decimal", -1)) == ROUTING_UUID_SEED
    ]
    pattern = re.compile(r"ROUTING_UUID_SEED\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)")
    owners: dict[int, set[str]] = collections.defaultdict(set)
    for path in sorted(HARDWARE.rglob("*.py")):
        for token in pattern.findall(path.read_text(encoding="utf-8", errors="replace")):
            owners[int(token, 0)].add(str(path.resolve()))
    current = str(Path(__file__).resolve())
    checks = {
        "seed_exactly_1750921": ROUTING_UUID_SEED == 1750921,
        "ledger_has_one_reservation": len(rows) == 1,
        "ledger_owner_exact": len(rows) == 1
        and rows[0].get("owner") == Path(__file__).name,
        "ledger_status_reserved_for_candidate": len(rows) == 1
        and rows[0].get("status") == "reserved_for_candidate",
        "python_owner_unique": owners.get(ROUTING_UUID_SEED, set()) == {current},
    }
    if not all(checks.values()):
        raise RouteError("UUID seed registry failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "ledger_path": str(SEED_LEDGER.resolve()),
        "ledger_sha256": sha256_file(SEED_LEDGER),
        "reservation": rows[0],
        "python_owner": current,
    }


def add_key1_route(board: Any) -> list[Any]:
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added: list[Any] = []
    for net, layer, points in ROUTES:
        if net != "/USER_KEY_1_N" or layer not in {"F.Cu", "B.Cu", "In2.Cu"}:
            raise RouteError(f"KEY1 route violates net/layer contract: {net}/{layer}")
        for start, end in zip(points, points[1:], strict=False):
            added.append(base.add_track(board, net, layer, SIGNAL_WIDTH_MM, start, end))
    for net, x_mm, y_mm in VIAS:
        if net != "/USER_KEY_1_N":
            raise RouteError(f"KEY1 via violates net contract: {net}")
        added.append(base.add_via(board, net, x_mm, y_mm))
    track_count = sum(not isinstance(item, pcbnew.PCB_VIA) for item in added)
    via_count = sum(isinstance(item, pcbnew.PCB_VIA) for item in added)
    if (track_count, via_count) != (EXPECTED_KEY1_TRACKS, EXPECTED_KEY1_VIAS):
        raise RouteError(f"unexpected KEY1 copper counts: tracks={track_count}, vias={via_count}")
    return added


def conflict_evidence_audit() -> dict[str, object]:
    if not R13_EVIDENCE_BOARD.is_file() or sha256_file(R13_EVIDENCE_BOARD) != R13_EVIDENCE_BOARD_SHA256:
        raise RouteError("rejected R13 conflict board missing or hash-mismatched")
    report = json.loads(R13_EVIDENCE_REPORT.read_text(encoding="utf-8"))
    fingerprints = set(report.get("new_violation_fingerprints", []))
    expected_tokens = (
        "221b7032-b946-453b-82e1-a140ce51da42",
        "ff6e057f-5a7a-4235-9e72-0816d8e7a4e5",
        "08208fc3-4209-437f-8f93-19e836a76460",
        "f25f26ad-5200-4ba7-bf01-65547ffd5bfa",
    )
    checks = {
        "rejected_state_hold": report.get("state") == "R13_R12_BUTTON_ROUTES_UNIFIED_HOLD",
        "rejected_routing_checks_false": report.get("routing_checks_passed") is False,
        "rejected_candidate_drc_15": report.get("candidate_drc", {}).get("violation_count") == 15,
        "rejected_candidate_open_106": report.get("candidate_drc", {}).get("unconnected_count") == 106,
        "two_new_fingerprints": len(fingerprints) == 2,
        "all_four_conflict_uuids_bound": all(
            any(token in fingerprint for fingerprint in fingerprints) for token in expected_tokens
        ),
    }
    if not all(checks.values()):
        raise RouteError("rejected R13 evidence audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "builder": {
            "path": str(R13_EVIDENCE_BUILDER.resolve()),
            "sha256": R13_EVIDENCE_BUILDER_SHA256,
        },
        "board": {
            "path": str(R13_EVIDENCE_BOARD.resolve()),
            "sha256": R13_EVIDENCE_BOARD_SHA256,
        },
        "report": {
            "path": str(R13_EVIDENCE_REPORT.resolve()),
            "sha256": sha256_file(R13_EVIDENCE_REPORT),
            "identity_policy": "SEMANTIC_GATE_VALIDATED_TIMESTAMPED_REPORT",
        },
        "new_violation_fingerprints": sorted(fingerprints),
    }


def preflight_audit() -> dict[str, object]:
    inputs = r13.verified_inputs()
    _, source = r13.load_state(SOURCE_BOARD)
    _, r11_state = r13.load_state(R11_BOARD)
    key2_delta = r13.branch_delta(
        "USER_KEY_2_N", R11_BOARD, SOURCE_BOARD, r13.EXPECTED_KEY2_ADDED, "/USER_KEY_2_N"
    )
    pwr_delta = r13.branch_delta(
        "PWR_BUTTON_N",
        PWR_SOURCE_BOARD,
        PWR_BRANCH_BOARD,
        EXPECTED_PWR_ADDED,
        "/PWR_BUTTON_N",
    )
    seed = seed_registry_audit()
    conflict = conflict_evidence_audit()
    source_ids = set(source["tracks"])
    key2_ids = key2_delta["_added_set"]
    pwr_ids = pwr_delta["_added_set"]
    checks = {
        "source_sha_exact": sha256_file(SOURCE_BOARD) == SOURCE_SHA256,
        "source_copper_count_1321": len(source_ids) == EXPECTED_SOURCE_COPPER,
        "source_is_r11_plus_key2": source_ids == set(r11_state["tracks"]) | key2_ids,
        "pwr_delta_disjoint_from_source": not (pwr_ids & source_ids),
        "pwr_delta_additive_19": pwr_delta["added_count"] == EXPECTED_PWR_ADDED
        and not pwr_delta["removed_uuids"]
        and not pwr_delta["changed_uuids"],
        "seed_registry_passed": seed["passed"] is True,
        "rejected_conflict_evidence_preserved": conflict["passed"] is True,
    }
    if not all(checks.values()):
        raise RouteError("remediation preflight failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "input_hash_bindings": inputs,
        "seed_registry": seed,
        "rejected_r13_conflict_evidence": conflict,
        "key2_inherited_delta": r13.strip_private(key2_delta),
        "pwr_future_delta": r13.strip_private(pwr_delta),
        "_pwr_delta": pwr_delta,
    }


def build_candidate(destination: Path, preflight: dict[str, object]):
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise RouteError("KiCad could not load frozen R12 source")
    before = base.source_state(board)
    if len(before["tracks"]) != EXPECTED_SOURCE_COPPER:
        raise RouteError(f"source copper-count drift: {len(before['tracks'])}")
    key1_scope = key1.validate_scope(board)
    pwr_scope = pwr.validate_scope(board)
    key1_objects = add_key1_route(board)
    key1_ids = {base.item_uuid(item) for item in key1_objects}
    pwr_objects = pwr.add_routes(board)
    pwr_ids = {base.item_uuid(item) for item in pwr_objects}
    expected_pwr = preflight["_pwr_delta"]["_added_set"]
    checks = {
        "key1_uuid_count_26": len(key1_ids) == EXPECTED_KEY1_ADDED,
        "pwr_uuid_set_exactly_frozen_delta": pwr_ids == expected_pwr,
        "new_uuid_sets_disjoint": not (key1_ids & pwr_ids),
        "new_uuid_sets_disjoint_from_source": not ((key1_ids | pwr_ids) & set(before["tracks"])),
    }
    if not all(checks.values()):
        raise RouteError("remediation replay failed: " + json.dumps(checks, sort_keys=True))
    if not pcbnew.SaveBoard(str(destination.resolve()), board):
        raise RouteError(f"failed to save candidate: {destination}")
    return before, key1_ids, pwr_ids, {
        "passed": True,
        "checks": checks,
        "key1_scope": key1_scope,
        "pwr_scope": pwr_scope,
    }


def exact_merge_audit(
    before: dict[str, object], key1_ids: set[str], pwr_ids: set[str], preflight: dict[str, object]
) -> dict[str, object]:
    _, source = r13.load_state(SOURCE_BOARD)
    candidate_board, candidate = r13.load_state(OUTPUT_BOARD)
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
    pwr_signatures = preflight["_pwr_delta"]["_branch_signatures"]
    pwr_geometry = all(
        candidate["tracks"].get(item_id) == pwr_signatures[item_id] for item_id in pwr_ids
    )
    base.ALLOWED_NETS = TARGET_NETS
    preservation = base.audit_candidate(candidate_board, before, expected_added)
    key1_envelope = key1.envelope_audit(candidate_board, key1_ids)
    pwr_envelope = pwr.envelope_audit(candidate_board, pwr_ids)
    objects = {base.item_uuid(item): item for item in candidate_board.GetTracks()}
    net_counts = collections.Counter(objects[item_id].GetNetname() for item_id in added)
    checks = {
        "candidate_copper_count_1364": len(candidate_ids) == EXPECTED_CANDIDATE_COPPER,
        "actual_added_exact": added == expected_added,
        "actual_removed_zero": not removed,
        "actual_changed_source_zero": not changed,
        "pwr_geometry_exactly_frozen_branch": pwr_geometry,
        "added_net_counts_exact": dict(net_counts)
        == {"/USER_KEY_1_N": EXPECTED_KEY1_ADDED, "/PWR_BUTTON_N": EXPECTED_PWR_ADDED},
        "source_preservation_passed": preservation["passed"] is True,
        "key1_envelope_passed": key1_envelope["passed"] is True,
        "pwr_envelope_passed": pwr_envelope["passed"] is True,
        "footprints_exact": source["footprints"] == candidate["footprints"],
        "zones_exact": source["zones"] == candidate["zones"],
    }
    if not all(checks.values()):
        raise RouteError("exact remediation audit failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_copper_count": len(source_ids),
        "candidate_copper_count": len(candidate_ids),
        "added_count": len(added),
        "added_net_counts": dict(sorted(net_counts.items())),
        "key1_added_uuids": sorted(key1_ids),
        "pwr_added_uuids": sorted(pwr_ids),
        "removed_uuids": sorted(removed),
        "changed_source_uuids": sorted(changed),
        "key1_signature_sha256": r13.signature_digest(candidate["tracks"], key1_ids),
        "pwr_signature_sha256": r13.signature_digest(candidate["tracks"], pwr_ids),
        "source_preservation": preservation,
        "key1_envelope": key1_envelope,
        "pwr_envelope": pwr_envelope,
    }


def drc_gate(source: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    source_nets = r13.unconnected_by_net(source["raw"])
    candidate_nets = r13.unconnected_by_net(candidate["raw"])
    for net in ALL_COMPLETED_NETS:
        source_nets.setdefault(net, 0)
        candidate_nets.setdefault(net, 0)
    other_nets = (set(source_nets) | set(candidate_nets)) - TARGET_NETS
    other_drift = {
        net: {"source": source_nets.get(net, 0), "candidate": candidate_nets.get(net, 0)}
        for net in sorted(other_nets)
        if source_nets.get(net, 0) != candidate_nets.get(net, 0)
    }
    checks = {
        "source_drc_13": source["violation_count"] == EXPECTED_DRC,
        "candidate_drc_13": candidate["violation_count"] == EXPECTED_DRC,
        "violation_fingerprint_exact": r13.violation_fingerprints(source["raw"])
        == r13.violation_fingerprints(candidate["raw"]),
        "source_open_112": source["unconnected_count"] == EXPECTED_SOURCE_OPEN,
        "candidate_open_106": candidate["unconnected_count"] == EXPECTED_CANDIDATE_OPEN,
        "exact_open_reduction_6": source["unconnected_count"] - candidate["unconnected_count"] == 6,
        "source_key1_3": source_nets.get("/USER_KEY_1_N", 0) == 3,
        "source_pwr_3": source_nets.get("/PWR_BUTTON_N", 0) == 3,
        "all_completed_nets_zero": all(candidate_nets.get(net, 0) == 0 for net in ALL_COMPLETED_NETS),
        "all_non_target_open_counts_unchanged": not other_drift,
        "schematic_parity_zero": candidate["schematic_parity_count"] == 0,
    }
    if not all(checks.values()):
        raise RouteError("remediation DRC gate failed: " + json.dumps(checks, sort_keys=True))
    return {
        "passed": True,
        "checks": checks,
        "source_unconnected_by_net": source_nets,
        "candidate_unconnected_by_net": candidate_nets,
        "other_net_unconnected_drift": other_drift,
        "violation_fingerprints": r13.violation_fingerprints(candidate["raw"]),
    }


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r13-remediation-iso-") as name:
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
                command, cwd=ROOT, check=False, text=True, encoding="utf-8",
                errors="replace", capture_output=True,
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise RouteError("isometric render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
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
    return {
        "formal_board": FORMAL_BOARD,
        "formal_schematic": FORMAL_SCHEMATIC,
        "formal_project": FORMAL_PROJECT,
        "root_readme": ROOT_README,
        "b3_readme": B3_README,
        "status_handoff": STATUS_HANDOFF,
        "seed_ledger": SEED_LEDGER,
        "source_board": SOURCE_BOARD,
        "r11_board": R11_BOARD,
        "pwr_source": PWR_SOURCE_BOARD,
        "pwr_branch": PWR_BRANCH_BOARD,
        "pwr_builder": PWR_BUILDER,
        "rejected_r13_builder": R13_EVIDENCE_BUILDER,
        "rejected_r13_board": R13_EVIDENCE_BOARD,
    }


def protected_hashes() -> dict[str, str | None]:
    return {
        name: sha256_file(path) if path.is_file() else None
        for name, path in protected_paths().items()
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kicad-python", type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\bin\python.exe"),
    )
    return parser.parse_args(argv)


def clean(value: Any) -> Any:
    return r13.strip_private(value)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    preflight: dict[str, object] | None = None
    report: dict[str, object] = {}
    try:
        if pcbnew is None or str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise RouteError("KiCad 10 pcbnew required")
        locks = list(B3_DIR.glob("~*kicad_pcb.lck")) + list(STAGING.glob("~*kicad_pcb.lck"))
        if locks:
            raise RouteError("close KiCad first: " + ", ".join(str(path) for path in locks))
        protected_before = protected_hashes()
        preflight = preflight_audit()
        kicad_cli = base.find_kicad_cli()
        source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
        with tempfile.TemporaryDirectory(prefix="mf1750-r13-remediation-") as name:
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
                raise RouteError("remediation double build not byte-deterministic")
            first_sha = sha256_file(first)
            second_sha = sha256_file(second)
            STAGING.mkdir(parents=True, exist_ok=True)
            os.replace(first, OUTPUT_BOARD)
        exact = exact_merge_audit(before, key1_ids, pwr_ids, preflight)
        # J6 audit is local because the imported rejected builder hard-codes its output path.
        source_loaded, source_state = r13.load_state(SOURCE_BOARD)
        candidate_loaded, candidate_state = r13.load_state(OUTPUT_BOARD)
        source_j6 = source_loaded.FindFootprintByReference("J6")
        candidate_j6 = candidate_loaded.FindFootprintByReference("J6")
        if source_j6 is None or candidate_j6 is None:
            raise RouteError("J6 missing from remediation audit")
        j6_checks = {
            "position_exact": base.point_mm(candidate_j6.GetPosition()) == (13.75, 120.0),
            "rotation_zero": round(float(candidate_j6.GetOrientationDegrees()) % 360.0, 6) == 0.0,
            "footprint_signature_unchanged": base.footprint_signature(source_j6)
            == base.footprint_signature(candidate_j6),
            "all_footprints_exact": source_state["footprints"] == candidate_state["footprints"],
        }
        if not all(j6_checks.values()):
            raise RouteError("J6 remediation audit failed: " + json.dumps(j6_checks, sort_keys=True))
        mechanical = {"passed": True, "checks": j6_checks}

        candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
        OUTPUT_SOURCE_DRC.write_text(json.dumps(source_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUTPUT_DRC.write_text(json.dumps(candidate_drc["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        gate = drc_gate(source_drc, candidate_drc)
        verifier = key1.r7.run_board_verifier(args.kicad_python, OUTPUT_BOARD)
        if not verifier["passed"]:
            raise RouteError(f"board verifier failed: {verifier.get('summary')}")
        OUTPUT_VERIFIER.write_text(json.dumps(verifier["raw"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        renders = [
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_TOP, "top"),
            base.render(kicad_cli, OUTPUT_BOARD, OUTPUT_BOTTOM, "bottom"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, OUTPUT_FRONT, "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"),
            base.export_svg(kicad_cli, OUTPUT_BOARD, OUTPUT_BACK, "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts", mirror=True),
        ]
        iso = render_isometric(kicad_cli)
        protected_after = protected_hashes()
        if protected_before != protected_after:
            raise RouteError("protected source/formal/evidence hash changed during remediation")

        report = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_BUTTON_CONFLICT_REMEDIATION",
            "revision": "R13_R12_BUTTON_CONFLICT_REMEDIATED_STAGING",
            "state": "R13_R12_BUTTON_CONFLICT_REMEDIATED_CANDIDATE",
            "overall_status": "ROUTING_SCOPE_VERIFIED_WHOLE_BOARD_HOLD",
            "routing_checks_passed": True,
            "locally_verified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "network_accessed": False,
            "source": {"path": str(SOURCE_BOARD.resolve()), "sha256": SOURCE_SHA256, "role": "sole_editable_PCB_geometry_source"},
            "builder": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve()), "routing_uuid_seed": ROUTING_UUID_SEED},
            "preflight": clean(preflight),
            "deterministic_replay": replay,
            "determinism": {"double_build_byte_identical": True, "first_sha256": first_sha, "second_sha256": second_sha},
            "exact_merge_audit": exact,
            "j6_mechanical_audit": mechanical,
            "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
            "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
            "drc_connectivity_gate": gate,
            "board_verifier": {key: value for key, value in verifier.items() if key != "raw"},
            "protected_sources": {"unchanged": True, "before": protected_before, "after": protected_after},
            "output": {"path": str(OUTPUT_BOARD.resolve()), "bytes": OUTPUT_BOARD.stat().st_size, "sha256": sha256_file(OUTPUT_BOARD)},
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
            "holds": [{"scope": "WHOLE_BOARD", "reason": "106 unrelated/held unconnected items remain; not manufacturing-ready"}],
        }
        OUTPUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n", encoding="utf-8")
        print(json.dumps({"state": report["state"], "routing_checks_passed": True, "output": report["output"], "drc": {"violations": 13, "unconnected": 106, "schematic_parity": 0}, "verifier": verifier["summary"], "report": str(OUTPUT_REPORT.resolve())}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report.update({
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "operating_mode": "REVISION",
            "mode": "STAGING_ONLY_BUTTON_CONFLICT_REMEDIATION",
            "revision": "R13_R12_BUTTON_CONFLICT_REMEDIATED_STAGING",
            "state": "R13_R12_BUTTON_CONFLICT_REMEDIATION_HOLD",
            "overall_status": "HOLD",
            "routing_checks_passed": False,
            "locally_verified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "network_accessed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preflight": clean(preflight) if preflight else None,
        })
        STAGING.mkdir(parents=True, exist_ok=True)
        OUTPUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=list) + "\n", encoding="utf-8")
        print(OUTPUT_REPORT.read_text(encoding="utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
