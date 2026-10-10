#!/usr/bin/env python3
"""Read-only audit of the MF1750 WROOM B3 R6 critical route chain.

The audited byte chain is R4 -> R6 SI placement -> U4 -> BQ -> EPD.  This
tool never invokes a route builder and never saves a board.  It independently
hash-binds the existing builders, engines, reports, successful repeat logs and
boards; proves track/via UUID uniqueness and source-copper preservation; checks
the frozen-B2 and WROOM-antenna contracts; runs a fresh self-contained native
KiCad DRC and the project board verifier; and writes only new R6 audit evidence
inside the staging directory.

The candidate remains HOLD while 141 unrouted items and the documented
non-fatal fabrication/silkscreen findings remain.  Passing this audit is not a
manufacturing-release claim.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - evaluated by KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
STEM = "mf1750_wroom_b3_power_tf"

FORMAL_BOARD = B3_DIR / f"{STEM}.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / f"{STEM}.kicad_sch"
FORMAL_PROJECT = B3_DIR / f"{STEM}.kicad_pro"
R3_BOARD = STAGING / f"{STEM}_r3_placed.kicad_pcb"
R4_BOARD = STAGING / f"{STEM}_r4_functional_placed.kicad_pcb"
PLACEMENT_BOARD = STAGING / f"{STEM}_r6_si_placement_remediated.kicad_pcb"
U4_BOARD = STAGING / f"{STEM}_r6_u4_routed.kicad_pcb"
BQ_BOARD = STAGING / f"{STEM}_r6_bq_powerpath_routed.kicad_pcb"
FINAL_BOARD = STAGING / f"{STEM}_r6_epd_boundary_routed.kicad_pcb"

PLACEMENT_SCRIPT = HARDWARE / "build_mf1750_wroom_b3_r6_si_placement_remediation.py"
REPLAY_SCRIPT = HARDWARE / "replay_mf1750_wroom_b3_r6_route_stage.py"
U4_ENGINE = HARDWARE / "route_mf1750_wroom_b3_r5_u4.py"
BQ_ENGINE = HARDWARE / "route_mf1750_wroom_b3_bq_power_r5.py"
EPD_SCRIPT = HARDWARE / "route_mf1750_wroom_b3_epd_boundary_r6.py"
EPD_ENGINE = HARDWARE / "route_mf1750_wroom_b3_epd_boundary_r5.py"
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"

PLACEMENT_REPORT = STAGING / "r6_si_placement_remediation_report.json"
U4_REPORT = STAGING / "r6_u4_route_audit.json"
BQ_REPORT = STAGING / "r6_bq_powerpath_route_audit.json"
EPD_REPORT = STAGING / "r6_epd_boundary_route_report.json"

AUDIT_JSON = STAGING / "r6_critical_route_chain_audit.json"
DRC_JSON = STAGING / "r6_critical_route_chain_drc.json"
VERIFIER_JSON = STAGING / "r6_critical_route_chain_board_verifier.json"

EXPECTED_HASHES = {
    FORMAL_BOARD: "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7",
    FORMAL_SCHEMATIC: "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0",
    FORMAL_PROJECT: "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c",
    R3_BOARD: "c43446b3ba92a7ee6c2aa2af2ad89761a81902d5d8be58e315297d5161df22fb",
    R4_BOARD: "349ef014b520aedcb061ee8bbcadbb03bfaad3249b512937091280918d0f2fbf",
    PLACEMENT_BOARD: "17eca6f94c24e85d0d03ab5bfe69e68d1dcbf696339472457725d9e007e03660",
    U4_BOARD: "1c3a7ffb8bfc35cb7a354eb618e96924cc76b1d018951bd8c7d3f4d3a35f414b",
    BQ_BOARD: "0c83a7b7cd8ed690b3799a7a4ba60cb9c6fc2823c47536c4c768cf9eeae1aa70",
    FINAL_BOARD: "41fcea36a5ca4cc117b77fa02fb4d6332b248863ad82b5fe25c65b0aa72bcf28",
    PLACEMENT_SCRIPT: "79c7ad1f684410ebef6725758626470a77e26122d9da1b4f121b3e953359cbb4",
    REPLAY_SCRIPT: "9f6dff31f0e61c969f0306ed6dfc2c66a9fa16abd6c7f989522f51e95e45b1cc",
    U4_ENGINE: "8405cd8f8892566626f00f7b34170d0f2a606013af934677343bc40715424257",
    BQ_ENGINE: "3a338ed1327aea23ecb7f214aab066fa136328361dcfcbe29ffb464c490514c6",
    EPD_SCRIPT: "4250a737653775e82f5017dfdc8f110c7ea06a31c3c6bd7618e249742abf52f8",
    EPD_ENGINE: "28f43841aed156a9f1f7697f432a3e95b5205fd85529fb291851eddd9a0cee41",
    BOARD_VERIFIER: "ebd591073b2d93e9a289e431312d9ba17f1dd96bafbd6bcd40b8c42341b72745",
    PLACEMENT_REPORT: "ab4990c575ed79682fca232f6a1529b7331302110e5ac26dec3d5550db05b9aa",
    U4_REPORT: "330175b9db7bbdf65db85112daf841b8261ce2cd6b824e3befdb92608e9e156a",
    BQ_REPORT: "bbf476ad9ffb16071f08f7ea6f2c03f363645a887c6e293e35d39ad3e0336f15",
    EPD_REPORT: "e1b8f450a989ae9c21a51ac38573d2446be55a2f582c7d088ad722fc51a29717",
}

REPEAT_LOGS = {
    "placement": (
        (
            STAGING / "r6_si_placement_second_run.log",
            "24d080f07908082cf031fa1c41e0d0b004a9a191ae1d21e0772cd9e055e9d8e0",
        ),
        (
            STAGING / "r6_si_placement_external_repeat.log",
            "670650fe2c2c04b53cf52cec10b656f86653d7a901b605a8ed80ac36b13e3d5f",
        ),
    ),
    "u4": (
        (
            STAGING / "r6_u4_safe_replay.log",
            "c29bf39732faf2bb1f6255bf73c7d0254b3bee6ac221a97b0b7760cb1a0dd3e1",
        ),
        (
            STAGING / "r6_u4_external_repeat.log",
            "2badf6f8f4d11bf459a4aa0ba5474f5dcab1d4e661d237cfde1b989024823d4a",
        ),
    ),
    "bq": (
        (
            STAGING / "r6_bq_safe_replay.log",
            "db5a99a152d41cb0348457128716daea79a286aa73d0eadc444059b4977e3631",
        ),
        (
            STAGING / "r6_bq_external_repeat.log",
            "6f713cade65b04d3692ef27e5e36abcc416630bab3751500d3519e70dc68c752",
        ),
    ),
    "epd": (
        (
            STAGING / "r6_epd_final_repeat.log",
            "09459872dbe02a3100e94b256a4b07688dc878d59321b5b8478dec1cae844432",
        ),
        (
            STAGING / "r6_epd_safe_final_repeat.log",
            "4a40d3feb3103b7dea59b1ac188def7d87c626ed8aa24063af782b0f8e3b7e17",
        ),
    ),
}

FATAL_DRC_TYPES = frozenset(
    {
        "clearance",
        "copper_edge_clearance",
        "copper_sliver",
        "courtyards_overlap",
        "hole_clearance",
        "hole_to_hole",
        "item_on_disabled_layer",
        "items_not_allowed",
        "shorting_items",
        "solder_mask_bridge",
        "track_not_centered_on_via",
        "tracks_crossing",
    }
)
EXPECTED_UNCONNECTED = 141
B2_BOTTOM_MM = 60.5
ANTENNA_BBOX_MM = (58.75, 66.0, 79.75, 114.0)
SUBPROCESS_TIMEOUT_SECONDS = 600.0


class AuditError(RuntimeError):
    """Raised when an immutable-chain or verification gate fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: object) -> None:
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
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
    raise AuditError(f"KiCad 10 tool not found: {name}")


def run_command(
    command: list[str], cwd: Path, label: str, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    started = dt.datetime.now(dt.timezone.utc)
    monotonic = time.monotonic()
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
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise AuditError(
            json.dumps(
                {
                    "label": label,
                    "timed_out": True,
                    "timeout_seconds": timeout_seconds,
                    "started_at_utc": started.isoformat(),
                    "duration_seconds": round(time.monotonic() - monotonic, 6),
                    "command": command,
                    "stdout_sha256": sha256_text(stdout),
                    "stderr_sha256": sha256_text(stderr),
                    "stdout_tail": stdout[-2000:],
                    "stderr_tail": stderr[-2000:],
                },
                ensure_ascii=False,
            )
        ) from exc


def command_evidence(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return {
        "returncode": completed.returncode,
        "stdout_sha256": sha256_text(completed.stdout),
        "stderr_sha256": sha256_text(completed.stderr),
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def snapshot_expected_hashes() -> dict[str, str]:
    evidence: dict[str, str] = {}
    for path, expected in EXPECTED_HASHES.items():
        if not path.is_file():
            raise AuditError(f"pinned input missing: {path}")
        actual = sha256_file(path)
        if actual.casefold() != expected.casefold():
            raise AuditError(f"pinned hash mismatch: {path}: {actual} != {expected}")
        evidence[str(path.resolve())] = actual
    return evidence


def r5_artifact_paths() -> tuple[Path, ...]:
    # This is the same reviewed R5 evidence scope used by the placement
    # remediation builder: top-level R5 route engines/chain runner plus every
    # R5-named artifact in this B3 staging tree.  Re-enumeration at the end
    # also detects newly created files in that scope.
    candidates = set(HARDWARE.glob("*r5*.py"))
    candidates.update(path for path in STAGING.rglob("*r5*") if path.is_file())
    return tuple(sorted((path.resolve() for path in candidates), key=str))


def immutable_chain_evidence_paths() -> tuple[Path, ...]:
    paths = set(EXPECTED_HASHES)
    for logs in REPEAT_LOGS.values():
        paths.update(path for path, _ in logs)
    return tuple(sorted((path.resolve() for path in paths), key=str))


def snapshot_paths(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path.resolve()): sha256_file(path) for path in paths}


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"JSON artifact is not an object: {path}")
    return value


def read_logged_json(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    offset = text.find("{")
    if offset < 0:
        raise AuditError(f"repeat log contains no JSON object: {path}")
    try:
        value = json.loads(text[offset:])
    except json.JSONDecodeError as exc:
        raise AuditError(f"repeat log JSON is invalid: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"repeat log JSON is not an object: {path}")
    return value


def nested(value: object, *keys: str) -> object:
    current = value
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def path_matches(value: object, expected: Path) -> bool:
    return isinstance(value, str) and Path(value).resolve() == expected.resolve()


def hash_matches(value: object, expected: str) -> bool:
    return isinstance(value, str) and value.casefold() == expected.casefold()


def audit_report_bindings() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    reports = {
        "placement": read_json(PLACEMENT_REPORT),
        "u4": read_json(U4_REPORT),
        "bq": read_json(BQ_REPORT),
        "epd": read_json(EPD_REPORT),
    }
    specifications = {
        "placement": (R4_BOARD, PLACEMENT_BOARD, PLACEMENT_REPORT),
        "u4": (PLACEMENT_BOARD, U4_BOARD, U4_REPORT),
        "bq": (U4_BOARD, BQ_BOARD, BQ_REPORT),
        "epd": (BQ_BOARD, FINAL_BOARD, EPD_REPORT),
    }
    evidence: dict[str, object] = {}
    all_passed = True
    for name, (source, output, report_path) in specifications.items():
        report = reports[name]
        if name == "placement":
            source_record = nested(report, "inputs", "r4")
        else:
            source_record = nested(report, "inputs", "source")
        output_record = report.get("output")
        checks = {
            "report_hash_pinned": sha256_file(report_path)
            == EXPECTED_HASHES[report_path],
            "operation_completed": report.get("operation_completed") is True,
            "hardware_accessed_false": report.get("hardware_accessed") is False,
            "source_path_bound": path_matches(
                nested(source_record, "path") if isinstance(source_record, dict) else None,
                source,
            ),
            "source_hash_bound": hash_matches(
                nested(source_record, "sha256") if isinstance(source_record, dict) else None,
                EXPECTED_HASHES[source],
            ),
            "output_path_bound": path_matches(
                nested(output_record, "path") if isinstance(output_record, dict) else None,
                output,
            ),
            "output_hash_bound": hash_matches(
                nested(output_record, "sha256") if isinstance(output_record, dict) else None,
                EXPECTED_HASHES[output],
            ),
        }
        if name == "placement":
            checks.update(
                {
                    "script_hash_bound": hash_matches(
                        report.get("script_sha256"), EXPECTED_HASHES[PLACEMENT_SCRIPT]
                    ),
                    "determinism_passed": nested(report, "determinism", "passed") is True,
                    "determinism_run1_bound": hash_matches(
                        nested(report, "determinism", "run1_sha256"),
                        EXPECTED_HASHES[PLACEMENT_BOARD],
                    ),
                    "determinism_run2_bound": hash_matches(
                        nested(report, "determinism", "run2_sha256"),
                        EXPECTED_HASHES[PLACEMENT_BOARD],
                    ),
                    "candidate_audit_passed": nested(report, "audit", "passed") is True,
                    "r5_artifacts_unchanged": report.get("r5_artifacts_unchanged") is True,
                }
            )
        elif name in {"u4", "bq"}:
            engine = U4_ENGINE if name == "u4" else BQ_ENGINE
            adapter = report.get("r6_replay_adapter")
            checks.update(
                {
                    "routing_checks_passed": report.get("routing_checks_passed") is True,
                    "adapter_path_bound": path_matches(
                        nested(adapter, "adapter") if isinstance(adapter, dict) else None,
                        REPLAY_SCRIPT,
                    ),
                    "engine_path_bound": path_matches(
                        nested(adapter, "engine") if isinstance(adapter, dict) else None,
                        engine,
                    ),
                    "engine_hash_bound": hash_matches(
                        nested(adapter, "engine_sha256") if isinstance(adapter, dict) else None,
                        EXPECTED_HASHES[engine],
                    ),
                    "adapter_source_hash_bound": hash_matches(
                        nested(adapter, "source_sha256") if isinstance(adapter, dict) else None,
                        EXPECTED_HASHES[source],
                    ),
                    "adapter_sha256_independently_pinned": sha256_file(REPLAY_SCRIPT)
                    == EXPECTED_HASHES[REPLAY_SCRIPT],
                }
            )
            if name == "u4":
                checks.update(
                    {
                        "preservation_audit_passed": nested(
                            report, "preservation_audit", "passed"
                        )
                        is True,
                        "local_connectivity_passed": nested(
                            report, "local_connectivity", "passed"
                        )
                        is True,
                        "drc_delta_gate_passed": nested(
                            report, "drc", "delta_gate", "passed"
                        )
                        is True,
                    }
                )
            else:
                dangerous_delta = nested(report, "drc", "dangerous_category_delta")
                checks.update(
                    {
                        "source_copper_preserved": nested(
                            report, "audit", "source_copper_preserved"
                        )
                        is True,
                        "footprints_preserved": nested(
                            report, "audit", "footprints_preserved"
                        )
                        is True,
                        "formal_r3_r4_unchanged": nested(
                            report, "audit", "formal_r3_r4_unchanged"
                        )
                        is True,
                        "drc_fatal_delta_exact_keyset": isinstance(
                            dangerous_delta, dict
                        )
                        and set(dangerous_delta) == FATAL_DRC_TYPES,
                        "drc_fatal_delta_zero": isinstance(dangerous_delta, dict)
                        and set(dangerous_delta) == FATAL_DRC_TYPES
                        and all(int(count) == 0 for count in dangerous_delta.values()),
                    }
                )
        else:
            checks.update(
                {
                    "route_checks_passed": report.get("route_checks_passed") is True,
                    "routing_checks_passed": report.get("routing_checks_passed") is True,
                    "drc_increment_gate_passed": report.get("drc_increment_gate_passed")
                    is True,
                    "candidate_audit_passed": nested(report, "audit", "passed") is True,
                    "panel_connected_sets_passed": nested(
                        report, "audit", "panel_connected_sets", "passed"
                    )
                    is True,
                    "protected_sources_unchanged": nested(
                        report, "protected_sources", "unchanged"
                    )
                    is True,
                    "drc_gate_passed": nested(report, "drc_gate", "passed") is True,
                    "wrapper_sha256_independently_pinned": sha256_file(EPD_SCRIPT)
                    == EXPECTED_HASHES[EPD_SCRIPT],
                    "engine_sha256_independently_pinned": sha256_file(EPD_ENGINE)
                    == EXPECTED_HASHES[EPD_ENGINE],
                }
            )
        passed = all(checks.values())
        all_passed = all_passed and passed
        evidence[name] = {
            "source": {"path": str(source.resolve()), "sha256": EXPECTED_HASHES[source]},
            "output": {"path": str(output.resolve()), "sha256": EXPECTED_HASHES[output]},
            "report": {
                "path": str(report_path.resolve()),
                "sha256": sha256_file(report_path),
            },
            "checks": checks,
            "passed": passed,
        }
    runner_bindings = {
        "placement_builder": {
            "path": str(PLACEMENT_SCRIPT.resolve()),
            "sha256": sha256_file(PLACEMENT_SCRIPT),
        },
        "r6_replay_adapter": {
            "path": str(REPLAY_SCRIPT.resolve()),
            "sha256": sha256_file(REPLAY_SCRIPT),
        },
        "u4_engine": {"path": str(U4_ENGINE.resolve()), "sha256": sha256_file(U4_ENGINE)},
        "bq_engine": {"path": str(BQ_ENGINE.resolve()), "sha256": sha256_file(BQ_ENGINE)},
        "epd_wrapper": {"path": str(EPD_SCRIPT.resolve()), "sha256": sha256_file(EPD_SCRIPT)},
        "epd_engine": {"path": str(EPD_ENGINE.resolve()), "sha256": sha256_file(EPD_ENGINE)},
    }
    return {"stages": evidence, "runners": runner_bindings, "passed": all_passed}, reports


def audit_repeat_evidence() -> dict[str, object]:
    stage_io = {
        "placement": (R4_BOARD, PLACEMENT_BOARD),
        "u4": (PLACEMENT_BOARD, U4_BOARD),
        "bq": (U4_BOARD, BQ_BOARD),
        "epd": (BQ_BOARD, FINAL_BOARD),
    }
    result: dict[str, object] = {}
    all_passed = True
    for name, logs in REPEAT_LOGS.items():
        source, output = stage_io[name]
        entries = []
        for path, expected_log_hash in logs:
            actual_log_hash = sha256_file(path)
            record = read_logged_json(path)
            source_record = (
                nested(record, "inputs", "r4")
                if name == "placement"
                else nested(record, "inputs", "source")
            )
            output_record = record.get("output")
            checks = {
                "log_hash_pinned": actual_log_hash == expected_log_hash,
                "operation_completed": record.get("operation_completed") is True,
                "hardware_accessed_false": record.get("hardware_accessed") is False,
                "output_path_bound": path_matches(
                    nested(output_record, "path") if isinstance(output_record, dict) else None,
                    output,
                ),
                "output_hash_bound": hash_matches(
                    nested(output_record, "sha256") if isinstance(output_record, dict) else None,
                    EXPECTED_HASHES[output],
                ),
            }
            if isinstance(source_record, dict):
                checks.update(
                    {
                        "source_path_bound": path_matches(source_record.get("path"), source),
                        "source_hash_bound": hash_matches(
                            source_record.get("sha256"), EXPECTED_HASHES[source]
                        ),
                    }
                )
            else:
                checks["source_path_bound"] = False
                checks["source_hash_bound"] = False
            passed = all(checks.values())
            all_passed = all_passed and passed
            entries.append(
                {
                    "path": str(path.resolve()),
                    "sha256": actual_log_hash,
                    "state": record.get("state"),
                    "checks": checks,
                    "passed": passed,
                }
            )
        same_output = all(
            entry["checks"]["output_hash_bound"] is True for entry in entries
        )
        stage_passed = len(entries) == 2 and same_output and all(
            entry["passed"] is True for entry in entries
        )
        all_passed = all_passed and stage_passed
        result[name] = {
            "successful_run_count": len(entries),
            "entries": entries,
            "same_expected_output_sha256": same_output,
            "passed": stage_passed,
        }
    result["passed"] = all_passed
    return result


def item_uuid(item) -> str:
    return item.m_Uuid.AsString()


def track_signature(item) -> tuple[object, ...]:
    start = item.GetStart()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            item_uuid(item),
            item.GetNetname(),
            int(start.x),
            int(start.y),
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    end = item.GetEnd()
    return (
        "track",
        item_uuid(item),
        item.GetNetname(),
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


def polygon_points(poly_set) -> tuple[tuple[tuple[int, int], ...], ...]:
    contours = []
    for index in range(poly_set.OutlineCount()):
        contour = poly_set.COutline(index)
        contours.append(
            tuple(
                (int(contour.CPoint(point).x), int(contour.CPoint(point).y))
                for point in range(contour.PointCount())
            )
        )
    return tuple(contours)


def zone_signature(zone) -> tuple[object, ...]:
    return (
        item_uuid(zone),
        zone.GetZoneName(),
        zone.GetNetname(),
        int(zone.GetLayer()),
        tuple(int(layer) for layer in zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        polygon_points(zone.Outline()),
    )


def pad_signature(pad) -> tuple[object, ...]:
    position = pad.GetPosition()
    size = pad.GetSize()
    drill = pad.GetDrillSize()
    return (
        item_uuid(pad),
        pad.GetNumber(),
        pad.GetNetname(),
        tuple(int(layer) for layer in pad.GetLayerSet().Seq()),
        int(position.x),
        int(position.y),
        int(size.x),
        int(size.y),
        int(drill.x),
        int(drill.y),
        int(pad.GetShape()),
        int(pad.GetAttribute()),
    )


def footprint_signature(footprint) -> tuple[object, ...]:
    position = footprint.GetPosition()
    return (
        item_uuid(footprint),
        footprint.GetReference(),
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        tuple(sorted((pad_signature(pad) for pad in footprint.Pads()), key=str)),
    )


def copper_map(board) -> dict[str, tuple[object, ...]]:
    return {item_uuid(item): track_signature(item) for item in board.GetTracks()}


def preservation_gate(source, candidate, label: str) -> dict[str, object]:
    source_items = copper_map(source)
    candidate_items = copper_map(candidate)
    missing = sorted(set(source_items) - set(candidate_items))
    changed = sorted(
        uuid
        for uuid in set(source_items) & set(candidate_items)
        if source_items[uuid] != candidate_items[uuid]
    )
    added = sorted(set(candidate_items) - set(source_items))
    return {
        "label": label,
        "source_count": len(source_items),
        "candidate_count": len(candidate_items),
        "added_count": len(added),
        "missing_source_uuid_count": len(missing),
        "changed_source_uuid_count": len(changed),
        "missing_source_uuid_sample": missing[:20],
        "changed_source_uuid_sample": changed[:20],
        "passed": not missing and not changed,
    }


def point_list_mm(item) -> list[tuple[float, float]]:
    if isinstance(item, pcbnew.PCB_VIA):
        position = item.GetPosition()
        return [(pcbnew.ToMM(position.x), pcbnew.ToMM(position.y))]
    start = item.GetStart()
    end = item.GetEnd()
    return [
        (pcbnew.ToMM(start.x), pcbnew.ToMM(start.y)),
        (pcbnew.ToMM(end.x), pcbnew.ToMM(end.y)),
    ]


def bbox_mm(item) -> tuple[float, float, float, float]:
    box = item.GetBoundingBox()
    left = pcbnew.ToMM(box.GetX())
    top = pcbnew.ToMM(box.GetY())
    return (
        left,
        top,
        left + pcbnew.ToMM(box.GetWidth()),
        top + pcbnew.ToMM(box.GetHeight()),
    )


def boxes_overlap_positive_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(
        first[1], second[1]
    ) < min(first[3], second[3])


def audit_boards(epd_report: dict[str, object]) -> dict[str, object]:
    board_paths = {
        "r4": R4_BOARD,
        "placement": PLACEMENT_BOARD,
        "u4": U4_BOARD,
        "bq": BQ_BOARD,
        "epd": FINAL_BOARD,
    }
    boards = {name: pcbnew.LoadBoard(str(path.resolve())) for name, path in board_paths.items()}
    if any(board is None for board in boards.values()):
        raise AuditError("pcbnew failed to load one or more chain boards")

    uuid_evidence = {}
    all_uuid_unique = True
    for name, board in boards.items():
        counts = collections.Counter(item_uuid(item) for item in board.GetTracks())
        duplicates = sorted((uuid, count) for uuid, count in counts.items() if count != 1)
        passed = not duplicates
        all_uuid_unique = all_uuid_unique and passed
        uuid_evidence[name] = {
            "board_sha256": sha256_file(board_paths[name]),
            "copper_item_count": sum(counts.values()),
            "unique_uuid_count": len(counts),
            "duplicate_uuid_count": sum(count - 1 for _, count in duplicates),
            "duplicate_uuid_sample": [
                {"uuid": uuid, "multiplicity": count} for uuid, count in duplicates[:20]
            ],
            "passed": passed,
        }

    transitions = [
        ("r4_to_placement", boards["r4"], boards["placement"]),
        ("placement_to_u4", boards["placement"], boards["u4"]),
        ("u4_to_bq", boards["u4"], boards["bq"]),
        ("bq_to_epd", boards["bq"], boards["epd"]),
    ]
    preservation = {
        name: preservation_gate(source, candidate, name)
        for name, source, candidate in transitions
    }
    preservation_passed = all(value["passed"] for value in preservation.values())

    placement_fp = {
        fp.GetReference(): footprint_signature(fp)
        for fp in boards["placement"].GetFootprints()
    }
    final_fp = {
        fp.GetReference(): footprint_signature(fp) for fp in boards["epd"].GetFootprints()
    }
    fp_missing = sorted(set(placement_fp) - set(final_fp))
    fp_extra = sorted(set(final_fp) - set(placement_fp))
    fp_changed = sorted(
        ref
        for ref in set(placement_fp) & set(final_fp)
        if placement_fp[ref] != final_fp[ref]
    )
    footprint_gate = {
        "placement_count": len(placement_fp),
        "final_count": len(final_fp),
        "missing": fp_missing,
        "extra": fp_extra,
        "changed": fp_changed,
        "passed": not fp_missing and not fp_extra and not fp_changed,
    }

    placement_zones = {item_uuid(zone): zone_signature(zone) for zone in boards["placement"].Zones()}
    final_zones = {item_uuid(zone): zone_signature(zone) for zone in boards["epd"].Zones()}
    zone_missing = sorted(set(placement_zones) - set(final_zones))
    zone_extra = sorted(set(final_zones) - set(placement_zones))
    zone_changed = sorted(
        uuid
        for uuid in set(placement_zones) & set(final_zones)
        if placement_zones[uuid] != final_zones[uuid]
    )
    zone_gate = {
        "placement_count": len(placement_zones),
        "final_count": len(final_zones),
        "missing": zone_missing,
        "extra": zone_extra,
        "changed": zone_changed,
        "passed": not zone_missing and not zone_extra and not zone_changed,
    }

    in1_non_ground_tracks = []
    signal_through_vias = []
    for item in boards["epd"].GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            if item.IsOnLayer(pcbnew.In1_Cu) and item.GetNetname() != "GND":
                signal_through_vias.append(item_uuid(item))
        elif item.GetLayer() == pcbnew.In1_Cu and item.GetNetname() != "GND":
            in1_non_ground_tracks.append(
                {"uuid": item_uuid(item), "net": item.GetNetname()}
            )
    in1_non_ground_zones = [
        {"uuid": item_uuid(zone), "net": zone.GetNetname()}
        for zone in boards["epd"].Zones()
        if not zone.GetIsRuleArea()
        and zone.IsOnLayer(pcbnew.In1_Cu)
        and zone.GetNetname() != "GND"
    ]
    in1_gate = {
        "non_ground_track_count": len(in1_non_ground_tracks),
        "non_ground_tracks": in1_non_ground_tracks,
        "non_ground_copper_zone_count": len(in1_non_ground_zones),
        "non_ground_copper_zones": in1_non_ground_zones,
        "allowed_signal_through_via_count": len(signal_through_vias),
        "allowed_signal_through_via_uuid_sample": sorted(signal_through_vias)[:20],
        "rule_areas_excluded_from_copper_zone_count": True,
        "passed": not in1_non_ground_tracks and not in1_non_ground_zones,
    }

    placement_ids = {item_uuid(item) for item in boards["placement"].GetTracks()}
    final_added = [
        item for item in boards["epd"].GetTracks() if item_uuid(item) not in placement_ids
    ]
    b2_reported = {
        str(item.get("uuid"))
        for item in (nested(epd_report, "audit", "b2_added_copper") or [])
        if isinstance(item, dict) and isinstance(item.get("uuid"), str)
    }
    b2_actual = {
        item_uuid(item)
        for item in final_added
        if any(y < B2_BOTTOM_MM for _, y in point_list_mm(item))
    }
    pre_epd_b2_added = {}
    for name in ("u4", "bq"):
        items = [
            item_uuid(item)
            for item in boards[name].GetTracks()
            if item_uuid(item) not in placement_ids
            and any(y < B2_BOTTOM_MM for _, y in point_list_mm(item))
        ]
        pre_epd_b2_added[name] = sorted(items)
    placement_copper = copper_map(boards["placement"])
    final_copper = copper_map(boards["epd"])
    inherited_b2 = {
        item_uuid(item)
        for item in boards["placement"].GetTracks()
        if any(y < B2_BOTTOM_MM for _, y in point_list_mm(item))
    }
    inherited_b2_missing = sorted(inherited_b2 - set(final_copper))
    inherited_b2_changed = sorted(
        uuid
        for uuid in inherited_b2 & set(final_copper)
        if placement_copper[uuid] != final_copper[uuid]
    )
    b2_gate = {
        "boundary_y_mm": B2_BOTTOM_MM,
        "inherited_source_copper_count": len(inherited_b2),
        "inherited_missing_count": len(inherited_b2_missing),
        "inherited_changed_count": len(inherited_b2_changed),
        "pre_epd_new_copper_below_boundary": pre_epd_b2_added,
        "epd_reported_added_uuid_count": len(b2_reported),
        "final_actual_added_uuid_count": len(b2_actual),
        "reported_missing_from_final": sorted(b2_reported - b2_actual),
        "unreported_final_additions": sorted(b2_actual - b2_reported),
        "panel_connected_sets_passed": nested(
            epd_report, "audit", "panel_connected_sets", "passed"
        )
        is True,
    }
    b2_gate["passed"] = (
        not inherited_b2_missing
        and not inherited_b2_changed
        and not pre_epd_b2_added["u4"]
        and not pre_epd_b2_added["bq"]
        and b2_reported == b2_actual
        and b2_gate["panel_connected_sets_passed"] is True
    )

    antenna_hits = []
    for item in final_added:
        item_box = bbox_mm(item)
        if boxes_overlap_positive_area(item_box, ANTENNA_BBOX_MM):
            antenna_hits.append(
                {
                    "uuid": item_uuid(item),
                    "net": item.GetNetname(),
                    "bbox_mm": item_box,
                }
            )
    placement_report = read_json(PLACEMENT_REPORT)
    antenna_gate = {
        "keepout_bbox_mm": ANTENNA_BBOX_MM,
        "new_copper_positive_area_bbox_hits": antenna_hits,
        "placement_report_antenna_intrusions": nested(
            placement_report, "audit", "courtyards", "antenna_intrusions"
        ),
        "final_footprints_exactly_match_placement": footprint_gate["passed"],
        "final_zones_exactly_match_placement": zone_gate["passed"],
    }
    antenna_gate["passed"] = (
        not antenna_hits
        and antenna_gate["placement_report_antenna_intrusions"] == []
        and footprint_gate["passed"] is True
        and zone_gate["passed"] is True
    )

    passed = (
        all_uuid_unique
        and preservation_passed
        and footprint_gate["passed"]
        and zone_gate["passed"]
        and in1_gate["passed"]
        and b2_gate["passed"]
        and antenna_gate["passed"]
    )
    return {
        "board_hash_chain": [
            {
                "name": name,
                "path": str(board_paths[name].resolve()),
                "sha256": sha256_file(board_paths[name]),
            }
            for name in ("r4", "placement", "u4", "bq", "epd")
        ],
        "copper_uuid_uniqueness": {"boards": uuid_evidence, "passed": all_uuid_unique},
        "source_copper_preservation": {
            "transitions": preservation,
            "passed": preservation_passed,
        },
        "footprint_preservation": footprint_gate,
        "zone_preservation": zone_gate,
        "in1_continuous_ground_policy": in1_gate,
        "frozen_b2": b2_gate,
        "wroom_antenna_keepout": antenna_gate,
        "passed": passed,
    }


def prepare_self_contained_context(directory: Path) -> Path:
    board = directory / f"{STEM}.kicad_pcb"
    shutil.copy2(FINAL_BOARD, board)
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
            raise AuditError(f"self-contained DRC library missing: {source}")
        shutil.copytree(source, directory / name)
    return board


def run_native_drc(kicad_cli: Path) -> dict[str, object]:
    board_hash_before = sha256_file(FINAL_BOARD)
    with tempfile.TemporaryDirectory(prefix="mf1750-r6-chain-drc-") as name:
        root = Path(name)
        contextual_board = prepare_self_contained_context(root)
        raw_report = root / "drc.json"
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
        completed = run_command(command, root, "R6 critical-chain native DRC", SUBPROCESS_TIMEOUT_SECONDS)
        if completed.returncode != 0 or not raw_report.is_file():
            raise AuditError(
                "native DRC failed: " + json.dumps(command_evidence(completed), ensure_ascii=False)
            )
        raw = raw_report.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise AuditError("native DRC report is not a JSON object")
        atomic_write_bytes(DRC_JSON, raw)
    if sha256_file(FINAL_BOARD) != board_hash_before:
        raise AuditError("native DRC changed the selected final board")
    violations = data.get("violations")
    unconnected = data.get("unconnected_items")
    parity = data.get("schematic_parity")
    ignored = data.get("ignored_checks")
    severities = data.get("included_severities")
    if not all(isinstance(value, list) for value in (violations, unconnected, parity, ignored, severities)):
        raise AuditError("native DRC report arrays are incomplete")
    categories = collections.Counter(str(item.get("type")) for item in violations)
    severity_counts = collections.Counter(str(item.get("severity")) for item in violations)
    fatal = {name: int(categories.get(name, 0)) for name in sorted(FATAL_DRC_TYPES)}
    ignored_keys = {
        str(item.get("key"))
        for item in ignored
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    ignored_fatal = sorted(ignored_keys & FATAL_DRC_TYPES)
    checks = {
        "kicad_10": isinstance(data.get("kicad_version"), str)
        and str(data.get("kicad_version")).split(".", 1)[0] == "10",
        "schema_v1": data.get("$schema") == "https://schemas.kicad.org/drc.v1.json",
        "coordinate_units_mm": data.get("coordinate_units") == "mm",
        "all_severities_included": {"error", "warning", "exclusion"}.issubset(
            set(str(value) for value in severities)
        ),
        "schematic_parity_zero": len(parity) == 0,
        "unconnected_exactly_141": len(unconnected) == EXPECTED_UNCONNECTED,
        "fatal_categories_zero": all(count == 0 for count in fatal.values()),
        "fatal_categories_not_ignored": not ignored_fatal,
        "clearance_zero": fatal["clearance"] == 0,
        "shorting_items_zero": fatal["shorting_items"] == 0,
        "tracks_crossing_zero": fatal["tracks_crossing"] == 0,
    }
    critical_route_gate_passed = all(checks.values())
    fully_clean = not violations and not unconnected and not parity
    return {
        "command": command,
        "execution": command_evidence(completed),
        "kicad_version": data.get("kicad_version"),
        "violation_count": len(violations),
        "violation_categories": dict(sorted(categories.items())),
        "violation_severity_counts": dict(sorted(severity_counts.items())),
        "unconnected_count": len(unconnected),
        "schematic_parity_count": len(parity),
        "fatal_category_counts": fatal,
        "ignored_check_keys": sorted(ignored_keys),
        "ignored_fatal_check_keys": ignored_fatal,
        "report": {
            "path": str(DRC_JSON.resolve()),
            "sha256": sha256_file(DRC_JSON),
        },
        "checks": checks,
        "critical_route_gate_passed": critical_route_gate_passed,
        "fully_clean": fully_clean,
    }


def run_board_verifier(kicad_python: Path) -> dict[str, object]:
    board_hash_before = sha256_file(FINAL_BOARD)
    command = [
        str(kicad_python),
        str(BOARD_VERIFIER),
        str(FINAL_BOARD.resolve()),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = run_command(
        command, ROOT, "R6 critical-chain project board verifier", SUBPROCESS_TIMEOUT_SECONDS
    )
    if completed.returncode != 0:
        raise AuditError(
            "board verifier failed: "
            + json.dumps(command_evidence(completed), ensure_ascii=False)
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuditError(f"board verifier emitted invalid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise AuditError("board verifier output is not a JSON object")
    reported_board = nested(report, "inputs", "staging_r3_pcb")
    summary = report.get("summary")
    checks = {
        "passed_true": report.get("passed") is True,
        "hardware_accessed_false": report.get("hardware_accessed") is False,
        "boards_modified_false": report.get("boards_modified") is False,
        "schematics_modified_false": report.get("schematics_modified") is False,
        "board_path_bound": path_matches(
            nested(reported_board, "path") if isinstance(reported_board, dict) else None,
            FINAL_BOARD,
        ),
        "board_hash_bound": hash_matches(
            nested(reported_board, "sha256") if isinstance(reported_board, dict) else None,
            EXPECTED_HASHES[FINAL_BOARD],
        ),
        "thirteen_of_thirteen": isinstance(summary, dict)
        and summary.get("total") == 13
        and summary.get("passed") == 13
        and summary.get("failed") == 0,
        "frozen_b2_hash_pass": nested(report, "checks", "frozen_b2_sha256", "status")
        == "PASS",
        "b2_footprint_geometry_pass": nested(
            report, "checks", "b2_footprint_geometry", "status"
        )
        == "PASS",
        "b2_copper_zone_subset_pass": nested(
            report, "checks", "b2_copper_zone_subset", "status"
        )
        == "PASS",
        "protected_copper_subset_pass": nested(
            report, "checks", "protected_copper_subset", "status"
        )
        == "PASS",
        "wroom_antenna_rule_area_pass": nested(
            report, "checks", "wroom_antenna_rule_area", "status"
        )
        == "PASS",
    }
    atomic_write_json(VERIFIER_JSON, report)
    if sha256_file(FINAL_BOARD) != board_hash_before:
        raise AuditError("board verifier changed the selected final board")
    return {
        "command": command,
        "execution": command_evidence(completed),
        "summary": summary,
        "b2_check": nested(report, "checks", "b2_copper_zone_subset"),
        "protected_copper_check": nested(report, "checks", "protected_copper_subset"),
        "antenna_check": nested(report, "checks", "wroom_antenna_rule_area"),
        "report": {
            "path": str(VERIFIER_JSON.resolve()),
            "sha256": sha256_file(VERIFIER_JSON),
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    started = dt.datetime.now(dt.timezone.utc)
    script = Path(__file__).resolve()
    script_hash = sha256_file(script)
    report: dict[str, object] = {
        "schema": 1,
        "tool": script.name,
        "generated_at_utc": started.isoformat(),
        "mode": "READ_ONLY_AUDIT_TO_STAGING_EVIDENCE",
        "state": "HOLD_R6_CRITICAL_ROUTE_CHAIN_AUDIT_FAILED",
        "overall_status": "FAIL",
        "operation_completed": False,
        "locally_verified": False,
        "hardware_accessed": False,
        "boards_modified": False,
        "schematics_modified": False,
        "chain_script": {"path": str(script), "sha256": script_hash},
    }
    r5_before: dict[str, str] = {}
    immutable_before: dict[str, str] = {}
    try:
        if pcbnew is None:
            raise AuditError(f"pcbnew unavailable; run with KiCad Python: {PCBNEW_IMPORT_ERROR}")
        locks = sorted(
            {*B3_DIR.glob("~*.lck"), *STAGING.glob("~*.lck")}, key=lambda path: str(path)
        )
        if locks:
            raise AuditError("close KiCad before auditing: " + ", ".join(map(str, locks)))
        kicad_python = resolve_kicad_tool("python.exe")
        kicad_cli = resolve_kicad_tool("kicad-cli.exe")
        pinned_before = snapshot_expected_hashes()
        r5_before = snapshot_paths(r5_artifact_paths())
        immutable_before = snapshot_paths(immutable_chain_evidence_paths())

        report_bindings, branch_reports = audit_report_bindings()
        repeat_evidence = audit_repeat_evidence()
        board_audit = audit_boards(branch_reports["epd"])
        verifier = run_board_verifier(kicad_python)
        drc = run_native_drc(kicad_cli)

        pinned_after = snapshot_expected_hashes()
        # Re-enumerate the glob, rather than only rehashing the original list,
        # so a newly created R5-named artifact is also a protection failure.
        r5_after = snapshot_paths(r5_artifact_paths())
        immutable_after = snapshot_paths(immutable_chain_evidence_paths())
        script_unchanged = sha256_file(script) == script_hash
        evidence_unchanged = (
            immutable_before == immutable_after and pinned_before == pinned_after
        )
        r5_unchanged = r5_before == r5_after
        gates = {
            "exact_report_and_hash_chain": report_bindings["passed"] is True,
            "two_successful_runs_per_stage": repeat_evidence["passed"] is True,
            "board_structure_and_preservation": board_audit["passed"] is True,
            "native_drc_critical_route_gate": drc["critical_route_gate_passed"]
            is True,
            "project_board_verifier_13_of_13": verifier["passed"] is True,
            "pinned_chain_artifacts_unchanged_during_audit": evidence_unchanged,
            "all_r5_artifacts_unchanged_during_audit": r5_unchanged,
            "audit_script_unchanged_during_audit": script_unchanged,
        }
        if not all(gates.values()):
            raise AuditError("one or more final audit gates failed: " + json.dumps(gates))
        report.update(
            {
                "state": "R6_CRITICAL_ROUTE_CHAIN_AUDITED_HOLD",
                "overall_status": "HOLD",
                "operation_completed": True,
                # The critical route invariants are verified, but the board is
                # deliberately not LOCALLY_VERIFIED while native DRC still has
                # error-severity findings and 141 unrouted items.
                "locally_verified": False,
                "critical_route_scope_verified": True,
                "tools": {
                    "python": sys.version,
                    "pcbnew": pcbnew.GetBuildVersion(),
                    "kicad_python": str(kicad_python),
                    "kicad_cli": str(kicad_cli),
                },
                "pinned_artifacts_before": pinned_before,
                "pinned_artifacts_after": pinned_after,
                "report_bindings": report_bindings,
                "provenance_limitations": [
                    "U4 report records the replay-adapter path but not its SHA-256; this audit independently pins the current adapter bytes",
                    "EPD report does not serialize wrapper/engine identity; this audit independently pins both current files but cannot retroactively add a direct report-to-runner signature",
                    "successful repeat logs are hash-pinned output evidence but do not serialize the invoking command or process exit code",
                ],
                "repeat_evidence": repeat_evidence,
                "board_audit": board_audit,
                "project_board_verifier": verifier,
                "native_drc": drc,
                "r5_artifact_protection": {
                    "count": len(r5_before),
                    "before": r5_before,
                    "after": r5_after,
                    "unchanged": r5_unchanged,
                },
                "final_gates": gates,
                "holds": [
                    "141 unconnected items remain; whole-board routing is incomplete",
                    f"{drc['violation_count']} native DRC findings remain, including {drc['violation_severity_counts'].get('error', 0)} error-severity findings outside the critical-route fatal set; the board DRC is not clean",
                    "stackup/SI, current/thermal, enclosure, assembly and manufacturing release remain HOLD",
                ],
            }
        )
    except Exception as exc:
        report.update(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "operation_completed": False,
                "locally_verified": False,
            }
        )
        if r5_before:
            try:
                r5_after = snapshot_paths(r5_artifact_paths())
                report["r5_artifact_protection_at_failure"] = {
                    "count": len(r5_before),
                    "unchanged": r5_before == r5_after,
                }
            except Exception as snapshot_exc:
                report["r5_failure_snapshot_error"] = (
                    f"{type(snapshot_exc).__name__}: {snapshot_exc}"
                )
        if immutable_before:
            try:
                immutable_after = snapshot_paths(immutable_chain_evidence_paths())
                report["pinned_artifacts_unchanged_at_failure"] = (
                    immutable_before == immutable_after
                )
            except Exception as snapshot_exc:
                report["immutable_failure_snapshot_error"] = (
                    f"{type(snapshot_exc).__name__}: {snapshot_exc}"
                )
    report["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["chain_script_unchanged"] = sha256_file(script) == script_hash
    final_write_gate: dict[str, object] = {"passed": False, "checks": {}}
    try:
        final_pinned = snapshot_expected_hashes()
        final_immutable = snapshot_paths(immutable_chain_evidence_paths())
        final_r5 = snapshot_paths(r5_artifact_paths())
        drc_hash_matches = (
            DRC_JSON.is_file()
            and sha256_file(DRC_JSON) == nested(report, "native_drc", "report", "sha256")
        )
        verifier_hash_matches = (
            VERIFIER_JSON.is_file()
            and sha256_file(VERIFIER_JSON)
            == nested(report, "project_board_verifier", "report", "sha256")
        )
        final_checks = {
            "pinned_hashes_still_match": bool(immutable_before)
            and final_pinned == snapshot_paths(EXPECTED_HASHES),
            "chain_scripts_reports_boards_and_repeat_logs_unchanged": bool(
                immutable_before
            )
            and immutable_before == final_immutable,
            "r5_artifact_scope_unchanged": bool(r5_before) and r5_before == final_r5,
            "fresh_drc_report_hash_matches": drc_hash_matches,
            "fresh_verifier_report_hash_matches": verifier_hash_matches,
            "audit_script_unchanged": report["chain_script_unchanged"] is True,
        }
        final_write_gate = {
            "checks": final_checks,
            "pinned_artifact_count": len(final_pinned),
            "immutable_chain_evidence_count": len(final_immutable),
            "r5_artifact_count": len(final_r5),
            "passed": all(final_checks.values()),
        }
    except Exception as final_exc:
        final_write_gate = {
            "checks": {},
            "passed": False,
            "error": f"{type(final_exc).__name__}: {final_exc}",
        }
    report["final_write_gate"] = final_write_gate
    if report.get("operation_completed") is True and final_write_gate["passed"] is not True:
        report.update(
            {
                "state": "HOLD_R6_CRITICAL_ROUTE_CHAIN_AUDIT_FAILED",
                "overall_status": "FAIL",
                "operation_completed": False,
                "critical_route_scope_verified": False,
                "error": "AuditError: final-write evidence rehash gate failed",
            }
        )
    atomic_write_json(AUDIT_JSON, report)
    result = {
        "operation_completed": report.get("operation_completed"),
        "state": report.get("state"),
        "overall_status": report.get("overall_status"),
        "audit": {
            "path": str(AUDIT_JSON.resolve()),
            "sha256": sha256_file(AUDIT_JSON),
        },
        "script": {"path": str(script), "sha256": sha256_file(script)},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("operation_completed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
