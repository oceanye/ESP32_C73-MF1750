#!/usr/bin/env python3
"""DITHER_ATLAS frame kit: measured color/lightness ladder via spatial dither.

Layout (1024x600, palette codes only: 0 blue / 1 violet / 3 black / 4 yellow /
6 green / 7 white):
* 8 rows x 11 columns of large cells (84x66 px, gap 6, origin (20,15)).
  Rows 0-5: codes [0,1,3,4,6,7], each with a white-coverage ladder
  0%,10%,...,100% (11 columns), ordered-8x8-Bayer micro-pattern (uniform).
  Row 6: 50/50 hue bridges: (1,4),(4,6),(6,0),(0,1),(1,3),(3,7),(0,7),(4,7),
  (6,7),(1,7),(0,4) - Bayer 50% checker blend.
  Row 7: anchor row with a non-palindromic code sequence
  [0,1,3,4,6,7,3,4,1,0,6] (solid cells) for transform readout.
* Full-width orientation bands: top (y 0-18) code 3 (navy), bottom
  (y 582-600) code 6 (sage) - different colors disambiguate vertical flip;
  combined with the anchor row sequence every rigid transform is resolvable.

Background outside cells/bands is code 7 (white).  Outputs (O_EXCL) into
.test-output/offline/DITHER_ATLAS_20261010_R1/: atlas.frame4bpp,
preview.png (endpoint-color render), cell-map.json (cell -> (code family,
level, predicted Lab)), manifest.json.  No device access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import epd_frame  # noqa: E402
from host.color_pipeline.palette import load_palette  # noqa: E402
from host.color_pipeline.color import lab_to_srgb8  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402

OUT_DIR = ROOT / ".test-output/offline/DITHER_ATLAS_20261010_R1"

CODES = (0, 1, 3, 4, 6, 7)
BRIDGES = [(1, 4), (4, 6), (6, 0), (0, 1), (1, 3), (3, 7), (0, 7), (4, 7), (6, 7), (1, 7), (0, 4)]
ANCHOR_SEQ = [0, 1, 3, 4, 6, 7, 3, 4, 1, 0, 6]

GRID_X0, GRID_Y0 = 20, 15
CELL_W, CELL_H, GAP = 84, 66, 6
COLS, ROWS = 11, 8

BAYER8 = np.array([
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
], dtype=np.uint8)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _paint_dither(value: np.ndarray, x: int, y: int, code: int, level: int) -> None:
    """Fill cell with ordered-Bayer dither: `level`/10 of pixels get `code`."""
    yy, xx = np.mgrid[y:y + CELL_H, x:x + CELL_W]
    mask = BAYER8[yy % 8, xx % 8] < (level * 6.4)  # 0..64 thresholds -> 0..10 levels
    region = value[y:y + CELL_H, x:x + CELL_W]
    region[mask] = code
    value[y:y + CELL_H, x:x + CELL_W] = region


def _paint_bridge(value: np.ndarray, x: int, y: int, pair: tuple[int, int]) -> None:
    """50/50 checker blend of two codes."""
    yy, xx = np.mgrid[y:y + CELL_H, x:x + CELL_W]
    mask = (xx + yy) % 2 == 0
    region = value[y:y + CELL_H, x:x + CELL_W]
    region[mask] = pair[0]
    region[~mask] = pair[1]
    value[y:y + CELL_H, x:x + CELL_W] = region


def _paint_solid(value: np.ndarray, x: int, y: int, w: int, h: int, code: int) -> None:
    value[y:y + h, x:x + w] = code


def build_frame() -> np.ndarray:
    frame = np.full((base.HEIGHT, base.WIDTH), 7, dtype=np.uint8)
    # orientation bands first: they must not overwrite the ladder cells
    _paint_solid(frame, 0, 0, base.WIDTH, 18, 3)              # top band: navy
    _paint_solid(frame, 0, base.HEIGHT - 18, base.WIDTH, 18, 6)  # bottom band: sage
    for row in range(6):
        for col in range(COLS):
            _paint_dither(frame, GRID_X0 + col * (CELL_W + GAP), GRID_Y0 + row * (CELL_H + GAP),
                          CODES[row], col)
    for col, pair in enumerate(BRIDGES):
        _paint_bridge(frame, GRID_X0 + col * (CELL_W + GAP), GRID_Y0 + 6 * (CELL_H + GAP), pair)
    for col, code in enumerate(ANCHOR_SEQ):
        _paint_solid(frame, GRID_X0 + col * (CELL_W + GAP), GRID_Y0 + 7 * (CELL_H + GAP),
                     CELL_W, CELL_H, code)
    return frame


def predicted_lab(palette, code: int, level: int) -> list[float]:
    """Naive linear-Lab mix between white endpoint and the code endpoint."""
    white = next(c for c in palette.entries if c.code == 7)
    if code == 7:
        return list(white.lab)
    entry = next(c for c in palette.entries if c.code == code)
    f = level / 10.0
    return [white.lab[0] + f * (entry.lab[0] - white.lab[0]),
            white.lab[1] + f * (entry.lab[1] - white.lab[1]),
            white.lab[2] + f * (entry.lab[2] - white.lab[2])]


def main() -> None:
    if OUT_DIR.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    OUT_DIR.mkdir(parents=True, exist_ok=False)

    palette = load_palette(ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json")
    frame = build_frame()
    packed = epd_frame.pack_pixels(frame.reshape(-1).tolist(), allowed_colors=list(range(8)))
    epd_frame.validate_frame(packed, allowed_colors=list(range(8)))

    lut = {c.code: lab_to_srgb8(tuple(c.lab)) for c in palette.entries}
    preview = np.zeros((base.HEIGHT, base.WIDTH, 3), dtype=np.uint8)
    for code, rgb in lut.items():
        preview[frame == code] = rgb

    cells = []
    for row in range(6):
        for col in range(COLS):
            cells.append({
                "row": row, "column": col, "kind": "ladder",
                "code": CODES[row], "level_percent": col * 10,
                "predicted_lab_linear_mix": [round(v, 2) for v in predicted_lab(palette, CODES[row], col)],
                "roi": {"x": GRID_X0 + col * (CELL_W + GAP), "y": GRID_Y0 + row * (CELL_H + GAP),
                        "width": CELL_W, "height": CELL_H},
            })
    for col, pair in enumerate(BRIDGES):
        cells.append({
            "row": 6, "column": col, "kind": "bridge_50_50",
            "code_pair": list(pair),
            "predicted_lab_linear_mix": [round(v, 2) for v in predicted_lab(palette, pair[0], 5)
                                         if False] or None,
            "roi": {"x": GRID_X0 + col * (CELL_W + GAP), "y": GRID_Y0 + 6 * (CELL_H + GAP),
                    "width": CELL_W, "height": CELL_H},
        })
    for col, code in enumerate(ANCHOR_SEQ):
        cells.append({
            "row": 7, "column": col, "kind": "anchor", "code": code,
            "roi": {"x": GRID_X0 + col * (CELL_W + GAP), "y": GRID_Y0 + 7 * (CELL_H + GAP),
                    "width": CELL_W, "height": CELL_H},
        })

    (OUT_DIR / "atlas.frame4bpp").write_bytes(packed)
    from PIL import Image
    Image.fromarray(preview, "RGB").save(OUT_DIR / "preview.png")
    (OUT_DIR / "cell-map.json").write_text(
        json.dumps(cells, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    manifest = {
        "kind": "mf1750-dither-atlas-frame-kit-v1",
        "date": "2026-10-10",
        "geometry": {
            "grid": "8 rows x 11 cols, cell 84x66, gap 6, origin (20,15)",
            "ladder_rows": "rows 0-5 = codes [0,1,3,4,6,7], white-coverage 0..100% in 10% steps, ordered 8x8 Bayer",
            "bridge_row": "row 6: 50/50 checker hue bridges " + json.dumps(BRIDGES),
            "anchor_row": "row 7: non-palindromic solid sequence " + json.dumps(ANCHOR_SEQ),
            "orientation_bands": "top (y0-18) code 3 navy; bottom (y582-600) code 6 sage",
            "background_code": 7,
        },
        "palette": {"palette_id": palette.palette_id, "canonical_sha256": palette.canonical_sha256},
        "frame": {"path": str(OUT_DIR / "atlas.frame4bpp"), "bytes": len(packed), "sha256": _sha(packed)},
        "frame_validation": "host.epd_frame.validate_frame with explicit allowed_colors 0..7",
        "hardware_accessed": False,
    }
    manifest["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha(base.canonical(manifest)),
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "frame_sha256": _sha(packed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
