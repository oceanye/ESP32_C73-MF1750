#!/usr/bin/env python3
"""Add the frozen JLC04161H-7628 stackup to the hash-bound R11 board.

This is a staging-only, geometry-preserving builder.  KiCad 10.0.3 exposes
the stackup descriptor as an opaque SWIG object, so the reviewed stackup is
inserted as KiCad S-expression text and immediately round-tripped through
KiCad's own parser/writer.  The result is rejected unless every footprint,
copper item and zone is identical to the source, the exact inherited DRC
fingerprints remain unchanged, the project verifier passes 13/13, and two
independent builds are byte-identical.
"""

from __future__ import annotations

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

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - owned by KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = Path(__file__).resolve()
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_r10_ps_hold_unified.kicad_pcb"
SOURCE_SHA256 = "74d1e8a023e6aae67049b96e39d7210b9e66f42427cec7394053d76433e97d43"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r11_jlc04161h_stackup_candidate.kicad_pcb"
OUTPUT_REPORT = STAGING / "r11_jlc04161h_stackup_candidate_report.json"
OUTPUT_SOURCE_DRC = STAGING / "r11_jlc04161h_stackup_source_drc.json"
OUTPUT_DRC = STAGING / "r11_jlc04161h_stackup_drc.json"
OUTPUT_VERIFIER = STAGING / "r11_jlc04161h_stackup_board_verifier.json"
PREVIEW_DIR = STAGING / "r11_jlc04161h_stackup_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_jlc04161h_stackup_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_jlc04161h_stackup_bottom.png"
OUTPUT_ISO = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r11_jlc04161h_stackup_iso.png"

ENGINE = HARDWARE / "route_mf1750_wroom_b3_epd_boundary_r5.py"
ENGINE_SHA256 = "28f43841aed156a9f1f7697f432a3e95b5205fd85529fb291851eddd9a0cee41"
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"
BOARD_VERIFIER_SHA256 = "ebd591073b2d93e9a289e431312d9ba17f1dd96bafbd6bcd40b8c42341b72745"
FORMAL_FILES = (
    B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb",
    B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch",
    B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro",
)

EXPECTED_DRC = 13
EXPECTED_OPEN = 115
EXPECTED_BOARD_THICKNESS_MM = 1.6
EXPECTED_LAMINATE_SUM_MM = 1.5862

TARGET_STACKUP = (
    {"name": "F.Cu", "type": "copper", "thickness_mm": 0.035},
    {"name": "dielectric 1", "type": "prepreg", "material": "7628", "thickness_mm": 0.2104},
    {"name": "In1.Cu", "type": "copper", "thickness_mm": 0.0152},
    {"name": "dielectric 2", "type": "core", "material": "JLC04161H-7628 core", "thickness_mm": 1.065},
    {"name": "In2.Cu", "type": "copper", "thickness_mm": 0.0152},
    {"name": "dielectric 3", "type": "prepreg", "material": "7628", "thickness_mm": 0.2104},
    {"name": "B.Cu", "type": "copper", "thickness_mm": 0.035},
)

STACKUP_BLOCK = """\
\t\t(stackup
\t\t\t(layer \"F.SilkS\"
\t\t\t\t(type \"Top Silk Screen\")
\t\t\t)
\t\t\t(layer \"F.Paste\"
\t\t\t\t(type \"Top Solder Paste\")
\t\t\t)
\t\t\t(layer \"F.Mask\"
\t\t\t\t(type \"Top Solder Mask\")
\t\t\t\t(thickness 0.01)
\t\t\t)
\t\t\t(layer \"F.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer \"dielectric 1\"
\t\t\t\t(type \"prepreg\")
\t\t\t\t(thickness 0.2104)
\t\t\t\t(material \"7628\")
\t\t\t)
\t\t\t(layer \"In1.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.0152)
\t\t\t)
\t\t\t(layer \"dielectric 2\"
\t\t\t\t(type \"core\")
\t\t\t\t(thickness 1.065)
\t\t\t\t(material \"JLC04161H-7628 core\")
\t\t\t)
\t\t\t(layer \"In2.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.0152)
\t\t\t)
\t\t\t(layer \"dielectric 3\"
\t\t\t\t(type \"prepreg\")
\t\t\t\t(thickness 0.2104)
\t\t\t\t(material \"7628\")
\t\t\t)
\t\t\t(layer \"B.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer \"B.Mask\"
\t\t\t\t(type \"Bottom Solder Mask\")
\t\t\t\t(thickness 0.01)
\t\t\t)
\t\t\t(layer \"B.Paste\"
\t\t\t\t(type \"Bottom Solder Paste\")
\t\t\t)
\t\t\t(layer \"B.SilkS\"
\t\t\t\t(type \"Bottom Silk Screen\")
\t\t\t)
\t\t\t(copper_finish \"None\")
\t\t\t(dielectric_constraints no)
\t\t)
"""


class StackupError(RuntimeError):
    """Fail-closed staging stackup builder error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine():
    if sha256_file(ENGINE) != ENGINE_SHA256:
        raise StackupError("frozen geometry-audit engine hash mismatch")
    spec = importlib.util.spec_from_file_location("_mf1750_stackup_base", ENGINE)
    if spec is None or spec.loader is None:
        raise StackupError("could not import frozen geometry-audit engine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_tool(name: str) -> Path:
    candidates = (
        Path(r"C:\Program Files\KiCad\10.0\bin") / name,
        Path(r"C:\Program Files\KiCad\9.0\bin") / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise StackupError(f"required KiCad tool not found: {name}")


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
    raise StackupError("unterminated S-expression")


def parse_stackup(text: str) -> list[dict[str, object]]:
    start = text.find("(stackup")
    if start < 0:
        raise StackupError("candidate has no stackup block")
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
        ):
            value = re.search(pattern, item_block)
            if value:
                item[key] = float(value.group(1)) if key == "thickness_mm" else value.group(1)
        items.append(item)
        offset = item_start + len(item_block)
    wanted = {entry["name"] for entry in TARGET_STACKUP}
    return [{key: item[key] for key in ("name", "type", "material", "thickness_mm") if key in item}
            for item in items if item.get("name") in wanted]


def inject_stackup(source_text: str) -> str:
    if "(stackup" in source_text:
        raise StackupError("source unexpectedly already contains a stackup")
    match = re.search(r"(?m)^\t\(setup\r?$", source_text)
    if match is None:
        raise StackupError("source setup block was not found")
    insert_at = source_text.find("\n", match.end()) + 1
    if insert_at <= 0:
        raise StackupError("source setup line is unterminated")
    return source_text[:insert_at] + STACKUP_BLOCK + source_text[insert_at:]


def build_once(destination: Path) -> dict[str, object]:
    source_text = SOURCE_BOARD.read_text(encoding="utf-8")
    injected = destination.with_suffix(".injected.kicad_pcb")
    injected.write_text(inject_stackup(source_text), encoding="utf-8", newline="\n")
    board = pcbnew.LoadBoard(str(injected))
    if board is None:
        raise StackupError("KiCad rejected the injected candidate")
    pcbnew.SaveBoard(str(destination), board)
    parsed = parse_stackup(destination.read_text(encoding="utf-8"))
    if parsed != list(TARGET_STACKUP):
        raise StackupError("KiCad round trip did not preserve the exact target stackup: " + json.dumps(parsed))
    return {
        "sha256": sha256_file(destination),
        "parsed_stackup": parsed,
        "board_thickness_mm": round(pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()), 6),
        "copper_layer_count": int(board.GetCopperLayerCount()),
    }


def violation_fingerprints(raw: dict[str, object]) -> list[tuple[object, ...]]:
    result = []
    for violation in raw.get("violations", []):
        items = []
        for item in violation.get("items", []):
            position = item.get("pos", {})
            items.append((str(item.get("uuid", "")), round(float(position.get("x", 0.0)), 6),
                          round(float(position.get("y", 0.0)), 6)))
        result.append((str(violation.get("type", "")), tuple(sorted(items))))
    return sorted(result, key=repr)


def drawing_signature(base, item) -> tuple[object, ...]:
    box = item.GetBoundingBox()
    text = item.GetText() if hasattr(item, "GetText") else ""
    return (
        type(item).__name__,
        int(item.GetLayer()),
        base.point_mm(box.GetPosition()),
        base.point_mm(box.GetSize()),
        str(text),
    )


def board_state(base, board) -> dict[str, object]:
    return {
        "footprints": {fp.GetReference(): base.footprint_signature(fp) for fp in board.GetFootprints()},
        "tracks": {base.item_uuid(item): base.track_signature(item) for item in board.GetTracks()},
        "zones": {base.item_uuid(zone): base.zone_signature(zone) for zone in board.Zones()},
        "drawings": {base.item_uuid(item): drawing_signature(base, item) for item in board.GetDrawings()},
        "groups": sorted(base.item_uuid(item) for item in board.Groups()),
        "nets": sorted((int(net.GetNetCode()), str(net.GetNetname())) for net in board.GetNetInfo().NetsByName().values()),
        "board_thickness_mm": round(pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()), 6),
        "copper_layer_count": int(board.GetCopperLayerCount()),
    }


def run_verifier(kicad_python: Path) -> dict[str, object]:
    command = [str(kicad_python), str(BOARD_VERIFIER), str(OUTPUT_BOARD),
               "--allow-board-only", "H3", "--allow-board-only", "H4"]
    completed = subprocess.run(command, cwd=ROOT, check=False, text=True, encoding="utf-8",
                               errors="replace", capture_output=True)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StackupError("board verifier did not emit JSON: " + completed.stdout[:500]) from exc
    OUTPUT_VERIFIER.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if completed.returncode != 0:
        raise StackupError("board verifier failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    summary = payload.get("summary", {})
    if summary != {"total": 13, "passed": 13, "failed": 0}:
        raise StackupError("board verifier did not pass 13/13")
    return {"command": command, "returncode": completed.returncode, "summary": summary}


def render(kicad_cli: Path, side: str, output: Path, width: int = 1800, height: int = 1600) -> dict[str, object]:
    command = [str(kicad_cli), "pcb", "render", "--side", side, "--background", "opaque",
               "--quality", "high", "--width", str(width), "--height", str(height),
               "--output", str(output), str(OUTPUT_BOARD)]
    completed = subprocess.run(command, cwd=B3_DIR, check=False, text=True, encoding="utf-8",
                               errors="replace", capture_output=True)
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise StackupError(f"{side} render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    return {"side": side, "command": command, "bytes": output.stat().st_size}


def render_isometric(kicad_cli: Path) -> dict[str, object]:
    command = [str(kicad_cli), "pcb", "render", "--side", "top", "--background", "opaque",
               "--quality", "high", "--width", "1800", "--height", "1600", "--perspective",
               "--floor", "--rotate", "315,0,45", "--output", str(OUTPUT_ISO), str(OUTPUT_BOARD)]
    completed = subprocess.run(command, cwd=B3_DIR, check=False, text=True, encoding="utf-8",
                               errors="replace", capture_output=True)
    if completed.returncode != 0 or not OUTPUT_ISO.is_file() or OUTPUT_ISO.stat().st_size == 0:
        raise StackupError("isometric render failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    return {"view": "perspective_isometric_top_315_0_45", "command": command,
            "bytes": OUTPUT_ISO.stat().st_size}


def main() -> int:
    if pcbnew is None:
        raise StackupError("pcbnew unavailable: " + PCBNEW_IMPORT_ERROR)
    if not SOURCE_BOARD.is_file() or sha256_file(SOURCE_BOARD) != SOURCE_SHA256:
        raise StackupError("hash-bound R11 source missing or changed")
    if sha256_file(BOARD_VERIFIER) != BOARD_VERIFIER_SHA256:
        raise StackupError("board verifier hash mismatch")
    formal_before = {str(path): sha256_file(path) for path in FORMAL_FILES}
    builder_before = sha256_file(BUILDER_PATH)
    base = load_engine()
    kicad_cli = resolve_tool("kicad-cli.exe")
    kicad_python = resolve_tool("python.exe")

    STAGING.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mf1750-r11-stackup-") as directory:
        first_path = Path(directory) / "first.kicad_pcb"
        second_path = Path(directory) / "second.kicad_pcb"
        first = build_once(first_path)
        second = build_once(second_path)
        if first["sha256"] != second["sha256"] or first_path.read_bytes() != second_path.read_bytes():
            raise StackupError("double build was not byte-identical")
        OUTPUT_BOARD.write_bytes(first_path.read_bytes())

    source_board = pcbnew.LoadBoard(str(SOURCE_BOARD))
    candidate_board = pcbnew.LoadBoard(str(OUTPUT_BOARD))
    source_state = board_state(base, source_board)
    candidate_state = board_state(base, candidate_board)
    geometry_checks = {
        "footprints_exact": source_state["footprints"] == candidate_state["footprints"],
        "tracks_exact": source_state["tracks"] == candidate_state["tracks"],
        "zones_exact": source_state["zones"] == candidate_state["zones"],
        "drawings_exact": source_state["drawings"] == candidate_state["drawings"],
        "groups_exact": source_state["groups"] == candidate_state["groups"],
        "nets_exact": source_state["nets"] == candidate_state["nets"],
        "four_copper_layers": candidate_state["copper_layer_count"] == 4,
        "board_thickness_1p6_mm": candidate_state["board_thickness_mm"] == EXPECTED_BOARD_THICKNESS_MM,
        "laminate_sum_1p5862_mm": round(sum(float(item["thickness_mm"]) for item in TARGET_STACKUP), 4)
        == EXPECTED_LAMINATE_SUM_MM,
    }
    if not all(geometry_checks.values()):
        raise StackupError("geometry preservation failed: " + json.dumps(geometry_checks, sort_keys=True))

    source_drc = base.run_drc(kicad_cli, SOURCE_BOARD)
    candidate_drc = base.run_drc(kicad_cli, OUTPUT_BOARD)
    source_fp = violation_fingerprints(source_drc["raw"])
    candidate_fp = violation_fingerprints(candidate_drc["raw"])
    drc_checks = {
        "source_drc_13": source_drc["violation_count"] == EXPECTED_DRC,
        "candidate_drc_13": candidate_drc["violation_count"] == EXPECTED_DRC,
        "source_open_115": source_drc["unconnected_count"] == EXPECTED_OPEN,
        "candidate_open_115": candidate_drc["unconnected_count"] == EXPECTED_OPEN,
        "parity_zero": candidate_drc["schematic_parity_count"] == 0,
        "violation_fingerprints_exact": source_fp == candidate_fp,
    }
    if not all(drc_checks.values()):
        raise StackupError("DRC preservation failed: " + json.dumps(drc_checks, sort_keys=True))
    OUTPUT_SOURCE_DRC.write_text(json.dumps(source_drc["raw"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUTPUT_DRC.write_text(json.dumps(candidate_drc["raw"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    verifier_command = [str(kicad_python), str(BOARD_VERIFIER), str(OUTPUT_BOARD),
                        "--allow-board-only", "H3", "--allow-board-only", "H4"]
    completed = subprocess.run(verifier_command, cwd=ROOT, check=False, text=True, encoding="utf-8",
                               errors="replace", capture_output=True)
    try:
        verifier_payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StackupError("board verifier did not emit JSON: " + completed.stdout[:500]) from exc
    OUTPUT_VERIFIER.write_text(json.dumps(verifier_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if completed.returncode != 0:
        raise StackupError("board verifier failed: " + (completed.stderr.strip() or completed.stdout.strip()))
    verifier_summary = verifier_payload.get("summary", {})
    if verifier_summary != {"total": 13, "passed": 13, "failed": 0}:
        raise StackupError("board verifier did not pass 13/13")

    render_results = [
        render(kicad_cli, "top", OUTPUT_TOP),
        render(kicad_cli, "bottom", OUTPUT_BOTTOM),
        render_isometric(kicad_cli),
    ]
    formal_after = {str(path): sha256_file(path) for path in FORMAL_FILES}
    builder_after = sha256_file(BUILDER_PATH)
    final_checks = {
        "formal_files_unchanged": formal_before == formal_after,
        "builder_unchanged_during_run": builder_before == builder_after,
        "output_hash_matches_double_build": sha256_file(OUTPUT_BOARD) == first["sha256"],
        "exact_stackup": parse_stackup(OUTPUT_BOARD.read_text(encoding="utf-8")) == list(TARGET_STACKUP),
    }
    if not all(final_checks.values()):
        raise StackupError("final integrity checks failed: " + json.dumps(final_checks, sort_keys=True))

    report = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        "state": "R11_JLC04161H_7628_STACKUP_STAGING_CANDIDATE",
        "hardware_accessed": False,
        "source": {"path": str(SOURCE_BOARD), "sha256": SOURCE_SHA256},
        "output": {"path": str(OUTPUT_BOARD), "sha256": sha256_file(OUTPUT_BOARD)},
        "stackup": {
            "vendor_structure": "JLC04161H-7628",
            "finished_board_thickness_mm": EXPECTED_BOARD_THICKNESS_MM,
            "laminate_sum_mm": EXPECTED_LAMINATE_SUM_MM,
            "outer_copper_oz": 1.0,
            "inner_copper_oz": 0.5,
            "layers": list(TARGET_STACKUP),
            "kicad_roundtrip": first,
        },
        "determinism": {"double_build_byte_identical": True, "first_sha256": first["sha256"],
                        "second_sha256": second["sha256"]},
        "geometry_checks": geometry_checks,
        "drc_checks": drc_checks,
        "source_drc": {key: value for key, value in source_drc.items() if key != "raw"},
        "candidate_drc": {key: value for key, value in candidate_drc.items() if key != "raw"},
        "verifier": {"command": verifier_command, "summary": verifier_summary},
        "render_results": render_results,
        "formal_files": {"before": formal_before, "after": formal_after},
        "builder": {"path": str(BUILDER_PATH), "sha256": builder_after},
        "final_checks": final_checks,
        "holds": [
            "Staging only; the formal PCB is not promoted by this builder.",
            "USB 90-ohm differential geometry remains HOLD until official JLC impedance-calculator dimensions are frozen.",
            "This candidate does not resolve the 115 remaining open items or the 13 inherited DRC items.",
        ],
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "board": report["output"], "stackup": report["stackup"],
                      "drc": drc_checks, "verifier": verifier_summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"passed": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2,
                         ensure_ascii=False), file=sys.stderr)
        raise
