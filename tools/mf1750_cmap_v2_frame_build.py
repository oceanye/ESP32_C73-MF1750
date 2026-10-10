#!/usr/bin/env python3
"""MAP-v2 color-intermediate frames: history-builder + probe (offline, no device).

Two PAL1-class grid frames for the L535 frame-path variant firmware:

* history.frame4bpp - per side, row r (0..7) is driven uniformly with code r,
  so after this refresh every main-matrix cell holds its row's history code.
* probe.frame4bpp - per side, cell (r, c) is driven to code c, so every
  (history r, target c) transition appears exactly once per side.

Per-side calibration (both frames identical geometry):
* right strip (x=456, 8 cells): history frame all code 7 (white), probe frame
  code r -> the (white -> code) session code axis and the XOR-3 control row.
* bottom strip (4 blocks): history all 7, probe [7, 3, 7, 3] -> white and dark
  session references.

Everything outside the cells is code 7 in both frames.  Codes 0..7 (L535 drive
semantics); validated with the explicit full nibble set.  Outputs (O_EXCL)
into .test-output/offline/CMAP_V2_20261009_R1/ with a canonical manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import epd_frame  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402

OUT_DIR = ROOT / ".test-output/offline/CMAP_V2_20261009_R1"

CAL_X = 456
REF_Y = 560
REF_H = 32
REF_BLOCKS = 4


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _paint_cell(value: bytearray, controller: int, x: int, y: int, code: int) -> None:
    stripe = bytes([code * 17]) * (base.CELL_W // 2)
    x_abs = controller * base.HALF + x
    for py in range(y, y + base.CELL_H):
        start = py * (base.WIDTH // 2) + x_abs // 2
        value[start: start + base.CELL_W // 2] = stripe


def _paint_block(value: bytearray, controller: int, x: int, y: int,
                 width: int, height: int, code: int) -> None:
    stripe = bytes([code * 17]) * (width // 2)
    x_abs = controller * base.HALF + x
    for py in range(y, y + height):
        start = py * (base.WIDTH // 2) + x_abs // 2
        value[start: start + width // 2] = stripe


def _frame(stage: str) -> bytes:
    if stage not in ("history", "probe"):
        raise ValueError("stage must be history or probe")
    value = bytearray([0x77]) * (base.WIDTH * base.HEIGHT // 2)
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                code = row if stage == "history" else column
                _paint_cell(
                    value, controller,
                    base.X0 + column * (base.CELL_W + base.GAP),
                    base.Y0 + row * (base.CELL_H + base.GAP),
                    code,
                )
        for row in range(8):
            _paint_cell(
                value, controller, CAL_X,
                base.Y0 + row * (base.CELL_H + base.GAP),
                7 if stage == "history" else row,
            )
        block_w = base.HALF // REF_BLOCKS
        for block in range(REF_BLOCKS):
            _paint_block(
                value, controller, block * block_w, REF_Y, block_w, REF_H,
                7 if stage == "history" else (3 if block % 2 else 7),
            )
    return bytes(value)


def _cell_map() -> dict:
    cells = []
    for controller in range(2):
        side = f"CS{controller + 1}"
        for row in range(8):
            for column in range(8):
                cells.append({
                    "side": side, "kind": "matrix",
                    "row": row, "column": column,
                    "history_code": row, "target_code": column,
                    "roi": {"x": controller * base.HALF + base.X0 + column * (base.CELL_W + base.GAP),
                            "y": base.Y0 + row * (base.CELL_H + base.GAP),
                            "width": base.CELL_W, "height": base.CELL_H},
                })
        for row in range(8):
            cells.append({
                "side": side, "kind": "calibration_code_axis",
                "row": row, "column": None,
                "history_code": 7, "target_code": row,
                "roi": {"x": controller * base.HALF + CAL_X,
                        "y": base.Y0 + row * (base.CELL_H + base.GAP),
                        "width": base.CELL_W, "height": base.CELL_H},
            })
        block_w = base.HALF // REF_BLOCKS
        for block in range(REF_BLOCKS):
            cells.append({
                "side": side, "kind": "reference",
                "row": None, "column": block,
                "history_code": 7, "target_code": 3 if block % 2 else 7,
                "roi": {"x": controller * base.HALF + block * block_w,
                        "y": REF_Y, "width": block_w, "height": REF_H},
            })
    return cells


def _audit(history: bytes, probe: bytes, cells: list) -> dict:
    errors = []
    for frame, stage in ((history, "history"), (probe, "probe")):
        try:
            epd_frame.validate_frame(frame, allowed_colors=list(range(8)))
        except Exception as error:  # noqa: BLE001
            errors.append(f"{stage} frame validation failed: {error}")
    matrix = [c for c in cells if c["kind"] == "matrix"]
    pairs = {(c["side"], c["history_code"], c["target_code"]) for c in matrix}
    expected = {
        (side, h, t)
        for side in ("CS1", "CS2") for h in range(8) for t in range(8)
    }
    if pairs != expected:
        errors.append("matrix (side, history, target) coverage differs")
    # byte-level spot checks: every cell's uniform code matches the map
    for cell in cells:
        roi = cell["roi"]
        for frame, stage in ((history, "history"), (probe, "probe")):
            code = cell["history_code"] if stage == "history" else cell["target_code"]
            x, y, w, h = roi["x"], roi["y"], roi["width"], roi["height"]
            row_bytes = w // 2
            start = y * (base.WIDTH // 2) + x // 2
            chunk = frame[start: start + row_bytes]
            expected_byte = code * 17
            if chunk != bytes([expected_byte]) * row_bytes:
                errors.append(f"{stage} cell {cell['kind']}@{side_of(cell)} code differs")
                break
        if errors:
            break
    return {"passed": not errors, "errors": errors}


def side_of(cell: dict) -> str:
    return f"{cell['side']},{cell['kind']},r{cell['row']},c{cell['column']}"


def _bind(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": _sha(data)}


def main() -> None:
    if OUT_DIR.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    OUT_DIR.mkdir(parents=True, exist_ok=False)
    history = _frame("history")
    probe = _frame("probe")
    cells = _cell_map()
    audit = _audit(history, probe, cells)
    if not audit["passed"]:
        raise SystemExit(f"frame audit failed: {audit['errors']}")

    (OUT_DIR / "history.frame4bpp").write_bytes(history)
    (OUT_DIR / "probe.frame4bpp").write_bytes(probe)
    (OUT_DIR / "cell-map.json").write_text(
        json.dumps(cells, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    manifest = {
        "kind": "mf1750-cmap-v2-frame-kit-v1",
        "date": "2026-10-09",
        "design_doc": "docs/MF1750_COLOR_INTERMEDIATE_MAP_V2_DESIGN_20261009.md",
        "firmware": {
            "pio_env": "esp32-s3-devkitc-1-l535-frame",
            "build_tag": "MF1750_L535_FRAME_V1_20260926",
            "bin_sha256": "cb25e57c424ad7c9be703268afe6d944800b2a636af938bc8713508763d204ae",
        },
        "frames": {
            "history": _bind(OUT_DIR / "history.frame4bpp"),
            "probe": _bind(OUT_DIR / "probe.frame4bpp"),
        },
        "geometry": {
            "matrix": "8x8 per side; row=history code 0..7, column=target code 0..7",
            "calibration_code_axis": "right strip x=456, 8 cells; history all 7, probe code r (XOR-3 control + session code axis)",
            "reference_strip": "bottom y=560, 4 blocks; history all 7, probe [7,3,7,3]",
            "background_code": 7,
            "cell": {"x0": base.X0, "y0": base.Y0, "w": base.CELL_W,
                     "h": base.CELL_H, "gap": base.GAP},
        },
        "frame_validation": "host.epd_frame.validate_frame with explicit allowed_colors 0..7",
        "audit": audit,
        "hardware_accessed": False,
    }
    manifest["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha(base.canonical(manifest)),
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(OUT_DIR),
                      "history_sha256": _sha(history), "probe_sha256": _sha(probe),
                      "audit": audit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
