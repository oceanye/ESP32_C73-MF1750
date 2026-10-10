#!/usr/bin/env python3
"""Build and audit the staging-only MF1750 WROOM B3 R5 route chain.

The fixed order is R4 placement -> U4 island -> BQ power path -> EPD boundary.
Every branch is run as a separate fail-closed process.  The selected source,
branch script, branch audit, and branch output are SHA-256 bound before the next
branch may start.  The canonical B3 PCB/schematic/project and the R3/R4 staging
boards are protected inputs and are never output targets.

After the three routing branches succeed, this tool runs the project-owned board
verifier and an independent, self-contained KiCad DRC/parity context.  Expected
remaining unrouted items keep the resulting board at HOLD; they do not weaken
the zero-parity and zero-fatal-routing-class gates.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
STEM = "mf1750_wroom_b3_power_tf"

FORMAL_PROJECT = B3_DIR / f"{STEM}.kicad_pro"
FORMAL_SCHEMATIC = B3_DIR / f"{STEM}.kicad_sch"
FORMAL_BOARD = B3_DIR / f"{STEM}.kicad_pcb"
R3_BOARD = STAGING / f"{STEM}_r3_placed.kicad_pcb"
R4_BOARD = STAGING / f"{STEM}_r4_functional_placed.kicad_pcb"

BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"
CHAIN_AUDIT = STAGING / "r5_critical_route_chain_audit.json"
CHAIN_DRC = STAGING / "r5_critical_route_chain_drc.json"
CHAIN_BOARD_VERIFIER = STAGING / "r5_critical_route_chain_board_verifier.json"

EXPECTED_PROTECTED_HASHES = {
    FORMAL_PROJECT: "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c",
    FORMAL_SCHEMATIC: "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0",
    FORMAL_BOARD: "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7",
    R3_BOARD: "c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb",
    R4_BOARD: "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf",
}

FORBIDDEN_DRC_TYPES = frozenset(
    {
        "clearance",
        "copper_edge_clearance",
        "copper_sliver",
        "courtyards_overlap",
        "hole_clearance",
        "hole_to_hole",
        "item_on_disabled_layer",
        "items_not_allowed",
        "solder_mask_bridge",
        "shorting_items",
        "track_not_centered_on_via",
        "tracks_crossing",
    }
)

PREFLIGHT_TIMEOUT_SECONDS = 120.0
BRANCH_TIMEOUT_SECONDS = 900.0
VERIFIER_TIMEOUT_SECONDS = 300.0
DRC_TIMEOUT_SECONDS = 600.0


@dataclasses.dataclass(frozen=True)
class BranchSpec:
    name: str
    script: Path
    output: Path
    audit: Path
    source_hash_argument: bool


BRANCHES = (
    BranchSpec(
        name="u4",
        script=HARDWARE / "route_mf1750_wroom_b3_r5_u4.py",
        output=STAGING / f"{STEM}_r5_u4_routed.kicad_pcb",
        audit=STAGING / "r5_u4_route_audit.json",
        source_hash_argument=True,
    ),
    BranchSpec(
        name="bq_powerpath",
        script=HARDWARE / "route_mf1750_wroom_b3_bq_power_r5.py",
        output=STAGING / f"{STEM}_r5_bq_powerpath_routed.kicad_pcb",
        audit=STAGING / "r5_bq_powerpath_route_audit.json",
        source_hash_argument=True,
    ),
    BranchSpec(
        name="epd_boundary",
        script=HARDWARE / "route_mf1750_wroom_b3_epd_boundary_r5.py",
        output=STAGING / f"{STEM}_r5_epd_boundary_routed.kicad_pcb",
        audit=STAGING / "r5_epd_boundary_route_report.json",
        source_hash_argument=True,
    ),
)


class ChainError(RuntimeError):
    """Raised when a chain evidence or preservation gate fails."""


class CommandAttemptError(ChainError):
    """Raised when a subprocess times out, with machine-readable evidence."""

    def __init__(self, evidence: dict[str, object]) -> None:
        self.evidence = evidence
        super().__init__(
            f"subprocess timed out: {evidence['label']} after "
            f"{evidence['timeout_seconds']} seconds"
        )


class ChainTailError(ChainError):
    """Raised when a branch artifact no longer matches its recorded binding."""

    def __init__(self, evidence: dict[str, object]) -> None:
        self.evidence = evidence
        super().__init__("branch chain-tail hash revalidation failed")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def file_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "sha256": sha256_file(path),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
    }


def assert_refreshed(
    path: Path,
    before: dict[str, object] | None,
    started_ns: int,
    label: str,
) -> dict[str, object]:
    after = file_state(path)
    if after is None:
        raise ChainError(f"{label} was not produced: {path}")
    if int(after["mtime_ns"]) < started_ns:
        raise ChainError(f"{label} predates this branch run: {path}")
    if before is not None and after == before:
        raise ChainError(f"{label} was not refreshed by this branch run: {path}")
    return after


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    )
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: object) -> None:
    content = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(path, content)


def resolve_kicad_tool(name: str) -> Path:
    candidates = [
        Path(r"C:\Program Files\KiCad\10.0\bin") / name,
        Path(r"C:\Program Files\KiCad\10\bin") / name,
    ]
    located = shutil.which(name)
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ChainError(f"KiCad 10 tool was not found: {name}")


def command_evidence(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return {
        "returncode": completed.returncode,
        "stdout_sha256": sha256_text(completed.stdout),
        "stderr_sha256": sha256_text(completed.stderr),
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def protected_snapshot() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path, expected_hash in EXPECTED_PROTECTED_HASHES.items():
        if not path.is_file():
            raise ChainError(f"protected input is missing: {path}")
        actual_hash = sha256_file(path)
        if actual_hash.casefold() != expected_hash.casefold():
            raise ChainError(
                f"protected input hash mismatch: {path}: "
                f"{actual_hash} != {expected_hash}"
            )
        snapshot[str(path.resolve())] = actual_hash
    return snapshot


def assert_protected_unchanged(expected: dict[str, str], stage: str) -> None:
    for raw_path, expected_hash in expected.items():
        path = Path(raw_path)
        if not path.is_file():
            raise ChainError(f"{stage}: protected input disappeared: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ChainError(
                f"{stage}: protected input changed: {path}: "
                f"{actual_hash} != {expected_hash}"
            )


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_command(
    command: list[str],
    cwd: Path,
    *,
    label: str,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    started_at = dt.datetime.now(dt.timezone.utc)
    started_monotonic = time.monotonic()
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
    except subprocess.TimeoutExpired as exc:
        stdout = stream_text(exc.stdout)
        stderr = stream_text(exc.stderr)
        finished_at = dt.datetime.now(dt.timezone.utc)
        evidence: dict[str, object] = {
            "label": label,
            "command": command,
            "cwd": str(cwd.resolve()),
            "timeout_seconds": timeout_seconds,
            "timed_out": True,
            "returncode": None,
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": finished_at.isoformat(),
            "duration_seconds": round(time.monotonic() - started_monotonic, 6),
            "stdout_sha256": sha256_text(stdout),
            "stderr_sha256": sha256_text(stderr),
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
        }
        raise CommandAttemptError(evidence) from exc


def parse_json_output(stdout: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ChainError(f"{label} did not emit a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ChainError(f"{label} emitted JSON that is not an object")
    return value


def nested_hash(record: object, *keys: str) -> str | None:
    current = record
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, str) and re.fullmatch(r"[0-9a-fA-F]{64}", current):
        return current.casefold()
    return None


def preflight_branch_interfaces(kicad_python: Path) -> list[dict[str, object]]:
    protected_paths = {path.resolve() for path in EXPECTED_PROTECTED_HASHES}
    seen_outputs: set[Path] = set()
    result: list[dict[str, object]] = []
    for branch in BRANCHES:
        if not branch.script.is_file():
            raise ChainError(f"branch script is missing: {branch.script}")
        script_hash = sha256_file(branch.script)
        for label, path in (("output", branch.output), ("audit", branch.audit)):
            if not is_inside(path, STAGING):
                raise ChainError(
                    f"{branch.name} {label} is outside the staging directory: {path}"
                )
            if path.resolve() in protected_paths:
                raise ChainError(
                    f"{branch.name} {label} aliases a protected source: {path}"
                )
        if branch.output.resolve() in seen_outputs:
            raise ChainError(f"duplicate branch output: {branch.output}")
        seen_outputs.add(branch.output.resolve())
        command = [str(kicad_python), str(branch.script), "--help"]
        completed = run_command(
            command,
            ROOT,
            label=f"{branch.name} --help preflight",
            timeout_seconds=PREFLIGHT_TIMEOUT_SECONDS,
        )
        if sha256_file(branch.script) != script_hash:
            raise ChainError(f"{branch.name} script changed during --help preflight")
        if completed.returncode != 0 or "--source" not in completed.stdout:
            raise ChainError(
                f"{branch.name} does not expose a usable --source interface: "
                f"{command_evidence(completed)}"
            )
        if branch.source_hash_argument and "--source-sha256" not in completed.stdout:
            raise ChainError(
                f"{branch.name} does not expose required --source-sha256"
            )
        result.append(
            {
                "name": branch.name,
                "script": str(branch.script),
                "script_sha256": script_hash,
                "output": str(branch.output),
                "audit": str(branch.audit),
                "requires_source_sha256": branch.source_hash_argument,
                "help_command": command,
                "help_evidence": command_evidence(completed),
            }
        )
    return result


def audit_branch_report(
    branch: BranchSpec,
    source: Path,
    source_hash: str,
    output_hash: str,
    started_ns: int,
    audit_before: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    assert_refreshed(
        branch.audit,
        audit_before,
        started_ns,
        f"{branch.name} audit",
    )
    audit_bytes = branch.audit.read_bytes()
    audit_hash = hashlib.sha256(audit_bytes).hexdigest()
    audit = json.loads(audit_bytes.decode("utf-8"))
    if not isinstance(audit, dict):
        raise ChainError(f"{branch.name} audit is not a JSON object")
    if audit.get("operation_completed") is not True:
        raise ChainError(f"{branch.name} audit does not mark operation_completed=true")
    gate_keys = (
        "routing_checks_passed",
        "route_checks_passed",
        "drc_increment_gate_passed",
    )
    present_gates = {key: audit[key] for key in gate_keys if key in audit}
    if not present_gates or any(value is not True for value in present_gates.values()):
        raise ChainError(
            f"{branch.name} audit route/DRC gates are absent or not all true: "
            f"{present_gates}"
        )
    if audit.get("hardware_accessed") is not False:
        raise ChainError(f"{branch.name} audit does not explicitly say hardware_accessed=false")

    reported_source_hash = nested_hash(audit, "inputs", "source", "sha256")
    reported_output_hash = nested_hash(audit, "output", "sha256")
    if reported_source_hash != source_hash.casefold():
        raise ChainError(
            f"{branch.name} audit source hash mismatch: "
            f"{reported_source_hash} != {source_hash}"
        )
    if reported_output_hash != output_hash.casefold():
        raise ChainError(
            f"{branch.name} audit output hash mismatch: "
            f"{reported_output_hash} != {output_hash}"
        )
    reported_source_path = audit.get("inputs", {}).get("source", {}).get("path")
    reported_output_path = audit.get("output", {}).get("path")
    if not isinstance(reported_source_path, str) or Path(reported_source_path).resolve() != source:
        raise ChainError(f"{branch.name} audit source path mismatch")
    if not isinstance(reported_output_path, str) or Path(reported_output_path).resolve() != branch.output.resolve():
        raise ChainError(f"{branch.name} audit output path mismatch")
    if sha256_file(branch.audit) != audit_hash:
        raise ChainError(f"{branch.name} audit changed while it was being validated")
    return audit, audit_hash


def run_branch(
    branch: BranchSpec,
    source: Path,
    kicad_python: Path,
    protected: dict[str, str],
) -> dict[str, object]:
    source = source.resolve()
    if not source.is_file():
        raise ChainError(f"{branch.name} source is missing: {source}")
    if source.resolve() in {path.resolve() for path in (FORMAL_BOARD, R3_BOARD)}:
        raise ChainError(f"{branch.name} source is not an approved staging derivative: {source}")
    if not is_inside(source, STAGING):
        raise ChainError(f"{branch.name} source is outside staging: {source}")
    if source == branch.output.resolve():
        raise ChainError(f"{branch.name} source aliases its fixed output")

    source_hash = sha256_file(source)
    script_hash = sha256_file(branch.script)
    output_before = file_state(branch.output)
    audit_before = file_state(branch.audit)
    command = [str(kicad_python), str(branch.script), "--source", str(source)]
    if branch.source_hash_argument:
        command.extend(["--source-sha256", source_hash])
    started_ns = time.time_ns()
    completed = run_command(
        command,
        ROOT,
        label=f"{branch.name} routing branch",
        timeout_seconds=BRANCH_TIMEOUT_SECONDS,
    )
    execution = command_evidence(completed)
    if completed.returncode != 0:
        raise ChainError(f"{branch.name} failed: {execution}")
    if sha256_file(branch.script) != script_hash:
        raise ChainError(f"{branch.name} script changed during execution")
    if sha256_file(source) != source_hash:
        raise ChainError(f"{branch.name} changed its selected source")
    assert_protected_unchanged(protected, f"after {branch.name}")
    output_after = assert_refreshed(
        branch.output,
        output_before,
        started_ns,
        f"{branch.name} fixed output",
    )
    if int(output_after["bytes"]) == 0:
        raise ChainError(f"{branch.name} produced an empty fixed staging output")
    output_hash = sha256_file(branch.output)
    branch_audit, branch_audit_hash = audit_branch_report(
        branch,
        source,
        source_hash,
        output_hash,
        started_ns,
        audit_before,
    )
    return {
        "name": branch.name,
        "command": command,
        "execution": execution,
        "script": {"path": str(branch.script), "sha256": script_hash},
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "bytes": source.stat().st_size,
        },
        "output": {
            "path": str(branch.output.resolve()),
            "sha256": output_hash,
            "bytes": branch.output.stat().st_size,
            "pre_run_state": output_before,
            "post_run_state": output_after,
        },
        "branch_audit": {
            "path": str(branch.audit.resolve()),
            "sha256": branch_audit_hash,
            "state": branch_audit.get("state"),
            "overall_status": branch_audit.get("overall_status"),
            "operation_completed": branch_audit.get("operation_completed"),
            "routing_checks_passed": branch_audit.get("routing_checks_passed"),
        },
    }


def rehash_branch_chain_tail(
    branch_records: list[dict[str, object]],
) -> dict[str, object]:
    """Re-bind every completed branch after all downstream work has finished."""

    records: list[dict[str, object]] = []
    all_match = len(branch_records) == len(BRANCHES)
    for index, branch in enumerate(BRANCHES):
        if index >= len(branch_records):
            records.append(
                {
                    "name": branch.name,
                    "present": False,
                    "all_match": False,
                    "error": "missing branch result",
                }
            )
            continue
        record = branch_records[index]
        name_match = record.get("name") == branch.name
        bindings: dict[str, dict[str, object]] = {}
        for key, required_path in (
            ("script", branch.script),
            ("output", branch.output),
            ("branch_audit", branch.audit),
        ):
            raw_binding = record.get(key)
            expected_path: str | None = None
            expected_hash: str | None = None
            if isinstance(raw_binding, dict):
                raw_path = raw_binding.get("path")
                raw_hash = raw_binding.get("sha256")
                if isinstance(raw_path, str):
                    expected_path = raw_path
                if isinstance(raw_hash, str):
                    expected_hash = raw_hash.casefold()
            recorded_path_matches = (
                expected_path is not None
                and Path(expected_path).resolve() == required_path.resolve()
            )
            exists = required_path.is_file()
            current_hash = sha256_file(required_path) if exists else None
            hash_matches = (
                expected_hash is not None
                and current_hash is not None
                and current_hash.casefold() == expected_hash
            )
            binding_passed = recorded_path_matches and hash_matches
            bindings[key] = {
                "path": str(required_path.resolve()),
                "recorded_path": expected_path,
                "recorded_path_matches": recorded_path_matches,
                "expected_sha256": expected_hash,
                "recomputed_sha256": current_hash,
                "exists": exists,
                "passed": binding_passed,
            }
            all_match = all_match and binding_passed
        branch_match = name_match and all(
            bool(binding["passed"]) for binding in bindings.values()
        )
        all_match = all_match and branch_match
        records.append(
            {
                "name": branch.name,
                "recorded_name": record.get("name"),
                "name_matches": name_match,
                "present": True,
                "bindings": bindings,
                "all_match": branch_match,
            }
        )
    evidence: dict[str, object] = {
        "expected_branch_count": len(BRANCHES),
        "recorded_branch_count": len(branch_records),
        "branches": records,
        "all_match": all_match,
    }
    if not all_match:
        raise ChainTailError(evidence)
    return evidence


def apply_final_protected_write_gate(report: dict[str, object]) -> None:
    """Fail closed unless all five immutable inputs still match their pins."""

    evidence: list[dict[str, object]] = []
    all_match = True
    for path, expected_hash in EXPECTED_PROTECTED_HASHES.items():
        exists = path.is_file()
        actual_hash = sha256_file(path) if exists else None
        matches = (
            actual_hash is not None
            and actual_hash.casefold() == expected_hash.casefold()
        )
        all_match = all_match and matches
        evidence.append(
            {
                "path": str(path.resolve()),
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "exists": exists,
                "matches": matches,
            }
        )
    report["final_write_protected_gate"] = {
        "checked_count": len(evidence),
        "expected_count": len(EXPECTED_PROTECTED_HASHES),
        "all_match": all_match,
        "files": evidence,
    }
    report["protected_inputs_unchanged_at_final_write"] = all_match
    by_path = {item["path"]: item for item in evidence}
    report["formal_b3_modified"] = not bool(
        by_path[str(FORMAL_BOARD.resolve())]["matches"]
    )
    report["schematic_modified"] = not bool(
        by_path[str(FORMAL_SCHEMATIC.resolve())]["matches"]
    )
    report["project_modified"] = not bool(
        by_path[str(FORMAL_PROJECT.resolve())]["matches"]
    )
    report["r3_modified"] = not bool(by_path[str(R3_BOARD.resolve())]["matches"])
    report["r4_modified"] = not bool(by_path[str(R4_BOARD.resolve())]["matches"])
    if not all_match:
        prior_error = report.get("error")
        suffix = "ChainError: final-write protected-input gate failed"
        report.update(
            {
                "state": "HOLD_R5_CRITICAL_ROUTE_CHAIN_FAILED",
                "overall_status": "FAIL",
                "operation_completed": False,
                "locally_verified": False,
                "protected_inputs_unchanged": False,
                "error": f"{prior_error}; {suffix}" if prior_error else suffix,
            }
        )


def prepare_self_contained_context(directory: Path, board_source: Path) -> Path:
    board = directory / f"{STEM}.kicad_pcb"
    shutil.copy2(board_source, board)
    shutil.copy2(FORMAL_SCHEMATIC, directory / f"{STEM}.kicad_sch")
    shutil.copy2(FORMAL_PROJECT, directory / f"{STEM}.kicad_pro")
    for name in ("fp-lib-table", "sym-lib-table"):
        source = B3_DIR / name
        if source.is_file():
            shutil.copy2(source, directory / name)
    for name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        source = B3_DIR / name
        if source.is_file():
            shutil.copy2(source, directory / name)
    for name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / name
        if not source.is_dir():
            raise ChainError(f"self-contained DRC library is missing: {source}")
        shutil.copytree(source, directory / name)
    return board


def run_self_contained_drc(kicad_cli: Path, board: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mf1750-b3-r5-chain-drc-") as name:
        root = Path(name)
        contextual_board = prepare_self_contained_context(root, board)
        raw_report = root / "drc.json"
        raw_report_before = file_state(raw_report)
        command = [
            str(kicad_cli),
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--schematic-parity",
            "--refill-zones",
            "--output",
            str(raw_report),
            str(contextual_board),
        ]
        started_ns = time.time_ns()
        completed = run_command(
            command,
            root,
            label="final self-contained KiCad DRC",
            timeout_seconds=DRC_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0 or not raw_report.is_file():
            raise ChainError(
                "self-contained DRC command failed: "
                + json.dumps(command_evidence(completed), ensure_ascii=False)
            )
        raw_report_state = assert_refreshed(
            raw_report,
            raw_report_before,
            started_ns,
            "self-contained DRC JSON",
        )
        raw = raw_report.read_bytes()
        raw_hash = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ChainError("self-contained DRC JSON is not an object")
        if data.get("$schema") != "https://schemas.kicad.org/drc.v1.json":
            raise ChainError(
                "self-contained DRC JSON has an unexpected schema: "
                f"{data.get('$schema')}"
            )
        if data.get("coordinate_units") != "mm":
            raise ChainError("self-contained DRC JSON is not expressed in mm")
        if data.get("source") != contextual_board.name:
            raise ChainError(
                "self-contained DRC JSON source mismatch: "
                f"{data.get('source')} != {contextual_board.name}"
            )
        report_date = data.get("date")
        if not isinstance(report_date, str):
            raise ChainError("self-contained DRC JSON has no date string")
        try:
            dt.datetime.fromisoformat(report_date)
        except ValueError as exc:
            raise ChainError(
                f"self-contained DRC JSON date is invalid: {report_date}"
            ) from exc
        violations = data.get("violations")
        unconnected_items = data.get("unconnected_items")
        schematic_parity = data.get("schematic_parity")
        ignored_checks = data.get("ignored_checks")
        included_severities = data.get("included_severities")
        if not isinstance(violations, list):
            raise ChainError("self-contained DRC JSON has no violations array")
        if not isinstance(unconnected_items, list):
            raise ChainError("self-contained DRC JSON has no unconnected_items array")
        if not isinstance(schematic_parity, list):
            raise ChainError("self-contained DRC JSON has no schematic_parity array")
        if not isinstance(ignored_checks, list):
            raise ChainError("self-contained DRC JSON has no ignored_checks array")
        if not isinstance(included_severities, list) or not all(
            isinstance(item, str) for item in included_severities
        ):
            raise ChainError(
                "self-contained DRC JSON has no valid included_severities array"
            )
        if not {"error", "warning", "exclusion"}.issubset(included_severities):
            raise ChainError(
                "self-contained DRC did not include all requested severities"
            )
        for key, values in (
            ("violations", violations),
            ("unconnected_items", unconnected_items),
            ("schematic_parity", schematic_parity),
            ("ignored_checks", ignored_checks),
        ):
            if not all(isinstance(item, dict) for item in values):
                raise ChainError(
                    f"self-contained DRC JSON {key} contains a non-object item"
                )
        for item in [*violations, *unconnected_items, *schematic_parity]:
            if not isinstance(item.get("type"), str):
                raise ChainError("self-contained DRC finding has no string type")
            if not isinstance(item.get("severity"), str):
                raise ChainError("self-contained DRC finding has no string severity")
        for item in ignored_checks:
            if not isinstance(item.get("key"), str):
                raise ChainError("self-contained DRC ignored check has no string key")
            if not isinstance(item.get("description"), str):
                raise ChainError(
                    "self-contained DRC ignored check has no string description"
                )
        kicad_version_value = data.get("kicad_version")
        if (
            not isinstance(kicad_version_value, str)
            or kicad_version_value.split(".", 1)[0] != "10"
        ):
            raise ChainError(
                f"self-contained DRC did not report KiCad 10: {kicad_version_value}"
            )
        atomic_write_bytes(CHAIN_DRC, raw)
        published_hash = sha256_file(CHAIN_DRC)
        if published_hash != raw_hash:
            raise ChainError("published DRC JSON does not match the fresh raw report")

    categories = collections.Counter(str(item.get("type")) for item in violations)
    forbidden = {name: int(categories.get(name, 0)) for name in sorted(FORBIDDEN_DRC_TYPES)}
    ignored_keys = {
        str(item.get("key"))
        for item in ignored_checks
        if isinstance(item, dict) and item.get("key") is not None
    }
    ignored_forbidden = sorted(ignored_keys & FORBIDDEN_DRC_TYPES)
    result = {
        "command": command,
        "execution": command_evidence(completed),
        "kicad_version": data.get("kicad_version"),
        "schema": data.get("$schema"),
        "coordinate_units": data.get("coordinate_units"),
        "source": data.get("source"),
        "date": data.get("date"),
        "included_severities": included_severities,
        "violation_count": len(violations),
        "violation_categories": dict(sorted(categories.items())),
        "unconnected_count": len(unconnected_items),
        "schematic_parity_count": len(schematic_parity),
        "forbidden_categories": forbidden,
        "ignored_check_keys": sorted(ignored_keys),
        "ignored_checks": ignored_checks,
        "ignored_forbidden_check_keys": ignored_forbidden,
        "freshness": {
            "pre_run_state": raw_report_before,
            "post_run_state": raw_report_state,
            "fresh_for_this_attempt": True,
        },
        "report": {
            "path": str(CHAIN_DRC.resolve()),
            "sha256": published_hash,
            "source_raw_sha256": raw_hash,
            "sha256_final_rehash": sha256_file(CHAIN_DRC),
        },
    }
    result["chain_gate_passed"] = (
        result["schematic_parity_count"] == 0
        and all(count == 0 for count in forbidden.values())
        and not ignored_forbidden
    )
    return result


def run_board_verifier(kicad_python: Path, board: Path) -> dict[str, object]:
    command = [
        str(kicad_python),
        str(BOARD_VERIFIER),
        str(board),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = run_command(
        command,
        ROOT,
        label="final project board verifier",
        timeout_seconds=VERIFIER_TIMEOUT_SECONDS,
    )
    evidence = command_evidence(completed)
    if completed.returncode != 0:
        raise ChainError(f"project board verifier failed: {evidence}")
    report = parse_json_output(completed.stdout, "project board verifier")
    if report.get("passed") is not True:
        raise ChainError("project board verifier JSON does not report passed=true")
    for flag in ("hardware_accessed", "boards_modified", "schematics_modified"):
        if report.get(flag) is not False:
            raise ChainError(
                f"project board verifier does not explicitly report {flag}=false"
            )
    reported_board = report.get("inputs", {}).get("staging_r3_pcb", {})
    reported_path = reported_board.get("path")
    reported_hash = reported_board.get("sha256")
    actual_hash = sha256_file(board)
    if (
        not isinstance(reported_path, str)
        or Path(reported_path).resolve() != board.resolve()
        or not isinstance(reported_hash, str)
        or reported_hash.casefold() != actual_hash
    ):
        raise ChainError(
            "project board verifier report is not bound to the selected final board"
        )
    atomic_write_json(CHAIN_BOARD_VERIFIER, report)
    return {
        "command": command,
        "execution": evidence,
        "passed": True,
        "result": report.get("result"),
        "summary": report.get("summary"),
        "verified_board": {
            "path": str(board.resolve()),
            "sha256": actual_hash,
        },
        "report": {
            "path": str(CHAIN_BOARD_VERIFIER.resolve()),
            "sha256": sha256_file(CHAIN_BOARD_VERIFIER),
        },
    }


def run_copper_uuid_uniqueness_gate(
    kicad_python: Path, board: Path
) -> dict[str, object]:
    """Require every final-board track/via to have one globally unique UUID."""

    marker = "MF1750_UUID_AUDIT="
    probe = (
        "import collections,json,pcbnew,sys;"
        "b=pcbnew.LoadBoard(sys.argv[1]);"
        "c=collections.Counter(i.m_Uuid.AsString() for i in b.GetTracks());"
        "d=sorted((u,n) for u,n in c.items() if n!=1);"
        f"print({marker!r}+json.dumps({{"
        "'passed':not d,'copper_item_count':sum(c.values()),"
        "'unique_uuid_count':len(c),"
        "'duplicate_uuid_count':sum(n-1 for _,n in d),"
        "'duplicate_uuid_sample':[{'uuid':u,'multiplicity':n} for u,n in d[:20]]"
        "},sort_keys=True))"
    )
    board_hash_before = sha256_file(board)
    command = [str(kicad_python), "-c", probe, str(board.resolve())]
    completed = run_command(
        command,
        ROOT,
        label="final track/via UUID uniqueness gate",
        timeout_seconds=VERIFIER_TIMEOUT_SECONDS,
    )
    evidence = command_evidence(completed)
    if completed.returncode != 0:
        raise ChainError(f"track/via UUID audit failed to run: {evidence}")
    marked = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
    if len(marked) != 1:
        raise ChainError(
            "track/via UUID audit did not emit exactly one marked JSON record"
        )
    result = parse_json_output(marked[0][len(marker) :], "track/via UUID audit")
    if result.get("passed") is not True or result.get("duplicate_uuid_count") != 0:
        raise ChainError(
            "final board contains duplicate track/via UUIDs: "
            + json.dumps(result, ensure_ascii=False)
        )
    board_hash_after = sha256_file(board)
    if board_hash_after != board_hash_before:
        raise ChainError("track/via UUID audit changed the final board")
    return {
        "command": command,
        "execution": evidence,
        "passed": True,
        "board": {
            "path": str(board.resolve()),
            "sha256_before": board_hash_before,
            "sha256_after": board_hash_after,
        },
        "result": result,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="check protected hashes and branch CLIs without generating routed boards",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    started = dt.datetime.now(dt.timezone.utc)
    chain_script = Path(__file__).resolve()
    chain_script_hash = sha256_file(chain_script)
    report: dict[str, object] = {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": started.isoformat(),
        "mode": "REVISION_TO_STAGING_ONLY",
        "state": "HOLD_R5_CRITICAL_ROUTE_CHAIN_FAILED",
        "overall_status": "FAIL",
        "operation_completed": False,
        "locally_verified": False,
        "hardware_accessed": False,
        "chain_script": {
            "path": str(chain_script),
            "sha256": chain_script_hash,
        },
        "branch_order": [branch.name for branch in BRANCHES],
        "branches": [],
    }
    try:
        STAGING.mkdir(parents=True, exist_ok=True)
        locks = sorted(
            {*B3_DIR.glob("~*.lck"), *STAGING.glob("~*.lck")},
            key=lambda path: str(path).casefold(),
        )
        if locks:
            raise ChainError("close KiCad first: " + ", ".join(map(str, locks)))
        kicad_python = resolve_kicad_tool("python.exe")
        kicad_cli = resolve_kicad_tool("kicad-cli.exe")
        protected = protected_snapshot()
        interfaces = preflight_branch_interfaces(kicad_python)
        report["protected_inputs"] = protected
        report["branch_interfaces"] = interfaces
        report["tools"] = {
            "chain_python": sys.version,
            "kicad_python": str(kicad_python),
            "kicad_cli": str(kicad_cli),
        }
        if args.preflight_only:
            assert_protected_unchanged(protected, "after preflight")
            interface_tail: list[dict[str, object]] = []
            interface_tail_passed = True
            for branch, interface in zip(BRANCHES, interfaces, strict=True):
                recomputed_hash = sha256_file(branch.script)
                recorded_hash = interface.get("script_sha256")
                matches = (
                    isinstance(recorded_hash, str)
                    and recomputed_hash == recorded_hash.casefold()
                )
                interface_tail_passed = interface_tail_passed and matches
                interface_tail.append(
                    {
                        "name": branch.name,
                        "path": str(branch.script.resolve()),
                        "expected_sha256": recorded_hash,
                        "recomputed_sha256": recomputed_hash,
                        "passed": matches,
                    }
                )
            if not interface_tail_passed:
                raise ChainError("preflight branch script tail rehash failed")
            report.update(
                {
                    "state": "R5_CRITICAL_ROUTE_CHAIN_PREFLIGHT_READY",
                    "overall_status": "HOLD",
                    "operation_completed": True,
                    "preflight_only": True,
                    "protected_inputs_unchanged": True,
                    "preflight_script_tail_rehash": {
                        "branches": interface_tail,
                        "all_match": True,
                    },
                }
            )
        else:
            source = R4_BOARD.resolve()
            branches: list[dict[str, object]] = []
            for branch in BRANCHES:
                branch_result = run_branch(branch, source, kicad_python, protected)
                branches.append(branch_result)
                report["branches"] = branches
                source = branch.output.resolve()
            final_board = source
            final_hash = sha256_file(final_board)
            uuid_uniqueness = run_copper_uuid_uniqueness_gate(
                kicad_python, final_board
            )
            if sha256_file(final_board) != final_hash:
                raise ChainError("UUID uniqueness gate changed the final candidate")
            verifier = run_board_verifier(kicad_python, final_board)
            if sha256_file(final_board) != final_hash:
                raise ChainError("project board verifier changed the final candidate")
            drc = run_self_contained_drc(kicad_cli, final_board)
            final_hash_after_verification = sha256_file(final_board)
            if final_hash_after_verification != final_hash:
                raise ChainError("self-contained DRC changed the final candidate")
            chain_tail = rehash_branch_chain_tail(branches)
            final_hash_at_chain_tail = sha256_file(final_board)
            if final_hash_at_chain_tail != final_hash:
                raise ChainError("final candidate changed before chain-tail binding")
            verifier_report_rehash = sha256_file(CHAIN_BOARD_VERIFIER)
            if verifier_report_rehash != verifier["report"]["sha256"]:
                raise ChainError("board verifier evidence changed after validation")
            drc_report_rehash = sha256_file(CHAIN_DRC)
            if drc_report_rehash != drc["report"]["sha256"]:
                raise ChainError("DRC evidence changed after validation")
            if not drc["chain_gate_passed"]:
                report["project_board_verifier"] = verifier
                report["self_contained_drc"] = drc
                report["chain_tail_rehash"] = chain_tail
                raise ChainError("final self-contained DRC/parity gate failed")
            assert_protected_unchanged(protected, "after final verification")
            remaining = int(drc["unconnected_count"])
            violations = int(drc["violation_count"])
            report.update(
                {
                    "state": "R5_CRITICAL_ROUTE_CHAIN_CANDIDATE",
                    "overall_status": "HOLD",
                    "operation_completed": True,
                    "preflight_only": False,
                    "protected_inputs_unchanged": True,
                    "final_board": {
                        "path": str(final_board),
                        "sha256": final_hash,
                        "sha256_after_verification": final_hash_after_verification,
                        "sha256_at_chain_tail": final_hash_at_chain_tail,
                        "bytes": final_board.stat().st_size,
                    },
                    "track_via_uuid_uniqueness": uuid_uniqueness,
                    "project_board_verifier": verifier,
                    "self_contained_drc": drc,
                    "chain_tail_rehash": chain_tail,
                    "evidence_final_rehash": {
                        "board_verifier_report_sha256": verifier_report_rehash,
                        "drc_report_sha256": drc_report_rehash,
                        "passed": True,
                    },
                    "holds": [
                        f"{remaining} unconnected items remain after the three critical route branches",
                        f"{violations} DRC violations remain; category counts are recorded separately",
                        "whole-board routing, power/current/thermal validation, stackup/SI, enclosure fit, and manufacturing readiness remain HOLD",
                    ],
                }
            )
    except Exception as exc:
        report.update(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "protected_inputs_unchanged_at_failure": None,
            }
        )
        if isinstance(exc, CommandAttemptError):
            report["failed_subprocess_attempt"] = exc.evidence
        if isinstance(exc, ChainTailError):
            report["chain_tail_rehash"] = exc.evidence
        try:
            current = {
                str(path.resolve()): sha256_file(path)
                for path in EXPECTED_PROTECTED_HASHES
                if path.is_file()
            }
            expected = {
                str(path.resolve()): value
                for path, value in EXPECTED_PROTECTED_HASHES.items()
            }
            report["protected_inputs_unchanged_at_failure"] = current == expected
            report["protected_inputs_at_failure"] = current
        except Exception as snapshot_exc:
            report["protected_snapshot_error"] = (
                f"{type(snapshot_exc).__name__}: {snapshot_exc}"
            )
    report["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["chain_script_unchanged"] = sha256_file(chain_script) == chain_script_hash
    if not report["chain_script_unchanged"]:
        report.update(
            {
                "state": "HOLD_R5_CRITICAL_ROUTE_CHAIN_FAILED",
                "overall_status": "FAIL",
                "operation_completed": False,
                "error": "ChainError: chain script changed during execution",
            }
        )
    apply_final_protected_write_gate(report)
    atomic_write_json(CHAIN_AUDIT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
