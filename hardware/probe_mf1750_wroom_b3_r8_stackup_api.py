#!/usr/bin/env python3
"""Fail-closed KiCad 10 stackup-API probe for MF1750 WROOM B3.

This utility is intentionally *not* a PCB builder.  It hash-binds the reviewed
R7 MCU-routed staging board, asks KiCad's own Python API whether the requested
JLC04161H-7628 stackup can be expressed, and performs two isolated temporary
default-stackup exports plus one load/save round trip.  KiCad 10.0.3 exposes
BOARD_STACKUP only as an opaque ``SwigPyObject`` with no item mutators.  Merely
setting ``m_HasStackup`` serializes KiCad's generic three-by-0.48 mm FR4
dielectric stack, not the requested JLC structure.

Consequently this probe writes only a JSON evidence report and exits blocked.
It never emits a candidate PCB and never edits the formal project or any
reviewed staging board.  A future GUI-controlled or structured-editing flow
must create a distinct candidate and then independently re-run DRC, parity,
the project verifier and deterministic round-trip checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - KiCad Python owns pcbnew
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_epd_mcu_routed.kicad_pcb"
SOURCE_SHA256 = "adf3a61c2231049f4a50b6ba97d95d5bd7b7fe9ff54be3f27469eb3f78cdc009"
SOURCE_ROUTE_REPORT = STAGING / "r7_epd_mcu_route_report.json"
SOURCE_DRC_REPORT = STAGING / "r7_epd_mcu_drc.json"
SOURCE_VERIFIER_REPORT = STAGING / "r7_epd_mcu_board_verifier.json"

FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
PROTECTED_HASHES = {
    FORMAL_BOARD: "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7",
    FORMAL_SCHEMATIC: "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0",
    FORMAL_PROJECT: "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c",
}

REPORT_JSON = STAGING / "r8_jlc04161h_7628_stackup_api_probe_report.json"
FORBIDDEN_CANDIDATE = (
    STAGING / "mf1750_wroom_b3_power_tf_r8_jlc04161h_7628_stackup_candidate.kicad_pcb"
)

TARGET_STACKUP = (
    {"name": "F.Cu", "type": "copper", "thickness_mm": 0.035},
    {
        "name": "dielectric 1",
        "type": "prepreg",
        "material": "7628",
        "thickness_mm": 0.2104,
    },
    {"name": "In1.Cu", "type": "copper", "thickness_mm": 0.0152},
    {
        "name": "dielectric 2",
        "type": "core",
        "material": "JLC04161H-7628 core",
        "thickness_mm": 1.065,
    },
    {"name": "In2.Cu", "type": "copper", "thickness_mm": 0.0152},
    {
        "name": "dielectric 3",
        "type": "prepreg",
        "material": "7628",
        "thickness_mm": 0.2104,
    },
    {"name": "B.Cu", "type": "copper", "thickness_mm": 0.035},
)
TARGET_LAMINATE_SUM_MM = 1.5862
TARGET_FINISHED_BOARD_THICKNESS_MM = 1.6

OFFICIAL_SOURCES = (
    "https://jlcpcb.com/impedance",
    "https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator",
    "https://jlcpcb.com/help/article/multi-layer-pcb-standard-laminated-structures",
    "https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html",
)


class ProbeError(RuntimeError):
    """An invariant failed before the expected API limitation was proven."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def protected_hashes() -> dict[str, str]:
    return {str(path): sha256_file(path) for path in PROTECTED_HASHES}


def assert_inputs() -> dict[str, str]:
    if pcbnew is None:
        raise ProbeError(f"pcbnew import failed: {PCBNEW_IMPORT_ERROR}")
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise ProbeError("R7 MCU-routed source is missing or hash-mismatched")
    for path, expected in PROTECTED_HASHES.items():
        if not path.is_file() or sha256_file(path) != expected:
            raise ProbeError(f"protected formal source changed: {path}")
    if FORBIDDEN_CANDIDATE.exists():
        raise ProbeError(
            "refusing to overwrite an existing stackup candidate; this probe emits none"
        )
    evidence = {
        "route_report": SOURCE_ROUTE_REPORT,
        "drc_report": SOURCE_DRC_REPORT,
        "verifier_report": SOURCE_VERIFIER_REPORT,
    }
    for label, path in evidence.items():
        if not path.is_file():
            raise ProbeError(f"missing source evidence {label}: {path}")
    return {label: sha256_file(path) for label, path in evidence.items()}


def extract_balanced(text: str, start: int) -> str:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ProbeError("unterminated S-expression in isolated KiCad output")


def parse_stackup(text: str) -> list[dict[str, object]]:
    marker = "(stackup"
    start = text.find(marker)
    if start < 0:
        raise ProbeError("isolated KiCad output did not contain a stackup block")
    block = extract_balanced(text, start)
    items: list[dict[str, object]] = []
    offset = 0
    while True:
        match = re.search(r'\(layer\s+"([^"]+)"', block[offset:])
        if not match:
            break
        item_start = offset + match.start()
        item_block = extract_balanced(block, item_start)
        item: dict[str, object] = {"name": match.group(1)}
        for key, pattern in (
            ("type", r'\(type\s+"([^"]+)"\)'),
            ("material", r'\(material\s+"([^"]+)"\)'),
            ("thickness_mm", r"\(thickness\s+([0-9.]+)\)"),
            ("epsilon_r", r"\(epsilon_r\s+([0-9.]+)\)"),
            ("loss_tangent", r"\(loss_tangent\s+([0-9.]+)\)"),
        ):
            value = re.search(pattern, item_block)
            if value:
                item[key] = (
                    float(value.group(1))
                    if key in {"thickness_mm", "epsilon_r", "loss_tangent"}
                    else value.group(1)
                )
        items.append(item)
        offset = item_start + len(item_block)
    return items


def export_default_stackup(source: Path, output: Path) -> dict[str, object]:
    board = pcbnew.LoadBoard(str(source))
    settings = board.GetDesignSettings()
    before = {
        "has_stackup": bool(settings.m_HasStackup),
        "board_thickness_mm": pcbnew.ToMM(settings.GetBoardThickness()),
        "copper_layer_count": board.GetCopperLayerCount(),
        "descriptor_type": type(settings.GetStackupDescriptor()).__name__,
        "descriptor_attributes": sorted(
            name for name in dir(settings.GetStackupDescriptor()) if not name.startswith("_")
        ),
    }
    settings.m_HasStackup = True
    pcbnew.SaveBoard(str(output), board)
    text = output.read_text(encoding="utf-8")
    reloaded = pcbnew.LoadBoard(str(output))
    after_settings = reloaded.GetDesignSettings()
    return {
        "before": before,
        "after": {
            "has_stackup": bool(after_settings.m_HasStackup),
            "board_thickness_mm": pcbnew.ToMM(after_settings.GetBoardThickness()),
            "copper_layer_count": reloaded.GetCopperLayerCount(),
        },
        "sha256": sha256_file(output),
        "stackup_items": parse_stackup(text),
    }


def semantic_stackup(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            key: item[key]
            for key in ("name", "type", "material", "thickness_mm")
            if key in item
        }
        for item in items
        if item.get("name") in {entry["name"] for entry in TARGET_STACKUP}
    ]


def source_baseline() -> dict[str, object]:
    route = json.loads(SOURCE_ROUTE_REPORT.read_text(encoding="utf-8"))
    drc = json.loads(SOURCE_DRC_REPORT.read_text(encoding="utf-8"))
    verifier = json.loads(SOURCE_VERIFIER_REPORT.read_text(encoding="utf-8"))
    if route.get("output", {}).get("sha256") != SOURCE_SHA256:
        raise ProbeError("source route report is not bound to the selected R7 board")
    result = {
        "source_sha256": SOURCE_SHA256,
        "drc_violation_count": len(drc.get("violations", [])),
        "drc_categories": {},
        "unconnected_count": len(drc.get("unconnected_items", [])),
        "schematic_parity_count": len(drc.get("schematic_parity", [])),
        "verifier": verifier.get("summary", {}),
        "source_double_build_byte_identical": route.get("determinism", {}).get(
            "double_build_byte_identical"
        ),
    }
    for violation in drc.get("violations", []):
        key = violation.get("type", "unknown")
        result["drc_categories"][key] = result["drc_categories"].get(key, 0) + 1
    expected = (
        result["drc_violation_count"] == 13
        and result["drc_categories"] == {"drill_out_of_range": 12, "track_dangling": 1}
        and result["unconnected_count"] == 128
        and result["schematic_parity_count"] == 0
        and result["verifier"] == {"total": 13, "passed": 13, "failed": 0}
        and result["source_double_build_byte_identical"] is True
    )
    if not expected:
        raise ProbeError("selected R7 source no longer matches its accepted baseline")
    return result


def run() -> int:
    evidence_hashes = assert_inputs()
    protected_before = protected_hashes()
    baseline = source_baseline()

    with tempfile.TemporaryDirectory(prefix="mf1750-stackup-api-proof-") as temp_name:
        temp = Path(temp_name)
        first_path = temp / "default_first.kicad_pcb"
        second_path = temp / "default_second.kicad_pcb"
        roundtrip_path = temp / "default_roundtrip.kicad_pcb"
        first = export_default_stackup(SOURCE_BOARD, first_path)
        second = export_default_stackup(SOURCE_BOARD, second_path)
        roundtrip_board = pcbnew.LoadBoard(str(first_path))
        pcbnew.SaveBoard(str(roundtrip_path), roundtrip_board)
        roundtrip_sha = sha256_file(roundtrip_path)

        observed = semantic_stackup(first["stackup_items"])
        target = list(TARGET_STACKUP)
        api_symbols = {
            "BOARD_STACKUP": hasattr(pcbnew, "BOARD_STACKUP"),
            "BOARD_STACKUP_ITEM": hasattr(pcbnew, "BOARD_STACKUP_ITEM"),
            "SetStackupDescriptor": hasattr(
                pcbnew.LoadBoard(str(SOURCE_BOARD)).GetDesignSettings(),
                "SetStackupDescriptor",
            ),
        }
        editable_api = any(api_symbols.values())
        target_matches_default = observed == target
        default_double_build_identical = first["sha256"] == second["sha256"]
        default_roundtrip_identical = first["sha256"] == roundtrip_sha

    protected_after = protected_hashes()
    if protected_before != protected_after:
        raise ProbeError("protected formal files changed during isolated probe")
    if SOURCE_BOARD.exists() and sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise ProbeError("selected R7 source changed during isolated probe")

    fail_closed = (not editable_api) and (not target_matches_default)
    if not fail_closed:
        raise ProbeError(
            "unexpected stackup API behavior; refusing to infer that a candidate is safe"
        )

    report = {
        "schema": 1,
        "mode": "REVIEW_ONLY_STAGING_API_PROBE",
        "state": "FAIL_CLOSED_STACKUP_API_HOLD",
        "overall_status": "HOLD_NO_CANDIDATE_PCB_GENERATED",
        "operation_completed": True,
        "hardware_accessed": False,
        "formal_files_modified": False,
        "candidate_board_generated": False,
        "candidate_board_path_reserved_but_absent": str(FORBIDDEN_CANDIDATE),
        "source": {
            "path": str(SOURCE_BOARD),
            "sha256": SOURCE_SHA256,
            "baseline": baseline,
            "evidence_sha256": evidence_hashes,
        },
        "protected_sources": {
            "before": protected_before,
            "after": protected_after,
            "unchanged": protected_before == protected_after,
        },
        "target_stackup_hold": {
            "vendor_structure": "JLC04161H-7628",
            "finished_board_thickness_mm": TARGET_FINISHED_BOARD_THICKNESS_MM,
            "outer_copper_oz": 1.0,
            "inner_copper_oz": 0.5,
            "items": target,
            "listed_copper_plus_dielectric_sum_mm": TARGET_LAMINATE_SUM_MM,
            "note": (
                "The official listed copper+dielectric nominal sum is 1.5862 mm; "
                "the 1.6 mm finished board value includes soldermask/process nominal effects."
            ),
            "status": "HOLD_NOT_ENCODED_IN_PCB",
        },
        "pcbnew_api_evidence": {
            "kicad_version": pcbnew.GetBuildVersion(),
            "symbols": api_symbols,
            "descriptor_type": first["before"]["descriptor_type"],
            "descriptor_attributes": first["before"]["descriptor_attributes"],
            "editable_stackup_api_available": editable_api,
        },
        "isolated_wrong_default_evidence": {
            "first": first,
            "second_sha256": second["sha256"],
            "roundtrip_sha256": roundtrip_sha,
            "double_build_byte_identical": default_double_build_identical,
            "roundtrip_byte_identical": default_roundtrip_identical,
            "observed_relevant_items": observed,
            "matches_requested_jlc04161h_7628": target_matches_default,
            "diagnosis": (
                "Setting m_HasStackup alone produces KiCad generic FR4: all four "
                "copper layers 0.035 mm and three 0.48 mm dielectrics.  It is stable "
                "across isolated saves, but it is not the requested JLC structure."
            ),
        },
        "checks": {
            "source_hash_bound": True,
            "source_baseline_13_128_0_verifier_13_of_13": True,
            "protected_formal_sources_unchanged": True,
            "pcbnew_stackup_api_editable": editable_api,
            "isolated_default_matches_target": target_matches_default,
            "isolated_default_double_build_byte_identical": default_double_build_identical,
            "isolated_default_roundtrip_byte_identical": default_roundtrip_identical,
            "candidate_output_absent": not FORBIDDEN_CANDIDATE.exists(),
            "fail_closed": fail_closed,
        },
        "future_candidate_required_gates": {
            "all_footprints_pads_copper_zones_drawings_preserved": "NOT_RUN_NO_CANDIDATE",
            "stackup_exact_match_after_kicad_roundtrip": "NOT_RUN_NO_CANDIDATE",
            "drc_violation_count": 13,
            "unconnected_count": 128,
            "schematic_parity_count": 0,
            "project_verifier": "13/13",
            "double_build_byte_identical": True,
        },
        "holds": [
            "Enter the exact JLC04161H-7628 stackup in KiCad GUI or a future verified structured API, into a distinct staging candidate only.",
            "USB 90-ohm differential width, gap, coplanar ground gap and numeric skew remain HOLD pending the exact official JLCPCB calculator result.",
            "JLCPCB order-time precision impedance acceptance at +/-10% or tighter remains HOLD; free standard +/-20% is insufficient for the Espressif USB requirement.",
            "Do not route USB or TF from the generic 0.20/0.25 mm project defaults.",
        ],
        "official_sources": list(OFFICIAL_SOURCES),
        "exit_reason": (
            "FAIL_CLOSED: KiCad 10.0.3 pcbnew cannot edit BOARD_STACKUP items, "
            "and its only accessible default export is the wrong stackup."
        ),
    }
    atomic_write_json(REPORT_JSON, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2


def main() -> int:
    try:
        return run()
    except Exception as exc:
        emergency = {
            "schema": 1,
            "mode": "REVIEW_ONLY_STAGING_API_PROBE",
            "state": "FAIL_CLOSED_PROBE_ERROR",
            "overall_status": "HOLD_NO_CANDIDATE_PCB_GENERATED",
            "candidate_board_generated": False,
            "hardware_accessed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        atomic_write_json(REPORT_JSON, emergency)
        print(json.dumps(emergency, ensure_ascii=False, indent=2, sort_keys=True))
        return 3


if __name__ == "__main__":
    sys.exit(main())
