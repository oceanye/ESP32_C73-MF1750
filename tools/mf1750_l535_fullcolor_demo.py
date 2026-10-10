#!/usr/bin/env python3
"""L535 full-colour demo frame + simulated preview; fully offline, no device.

Builds a synthetic 1024x600 test image (lightness gradient, hue sweep, colour
swatches, fine texture), quantizes it through the measured L535 palette with
the host color pipeline (Floyd-Steinberg), packs the canonical 4bpp frame in
L535 drive-code semantics (nibbles 0..7), and renders a simulated preview PNG
by mapping each quantized code back through the palette's measured Lab -> sRGB
(via the pipeline's own preview_rgb).

The frame uses L535 codes (e.g. white=7), which the canonical stock frame
contract does not cover; it is validated explicitly with the full 0..7 set.
Displaying it needs a firmware variant that loads the L535 R20 LUT and accepts
an arbitrary frame (next field task); this tool only produces the offline
frame and the preview.

Outputs (O_EXCL) into --output-dir: source.png, demo.frame4bpp,
preview-quantized.png, manifest.json (input/palette/frame/preview sha256).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import lab_to_srgb8  # noqa: E402
from host.color_pipeline.palette import load_palette  # noqa: E402
from host.color_pipeline.pipeline import (  # noqa: E402
    DitherMode, PipelineOptions, RasterImage, quantize_image,
)
from host.epd_frame import validate_frame  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402

DEFAULT_PALETTE = ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json"
DEFAULT_OUT = ROOT / ".test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1"


def build_source_image() -> np.ndarray:
    """1024x600 RGB: lightness gradient, hue sweep, swatches, texture."""
    width, height = base.WIDTH, base.HEIGHT
    image = np.zeros((height, width, 3), dtype=np.uint8)
    band = height // 4
    # Band 1: horizontal lightness gradient.
    grad = np.linspace(0, 255, width).round().astype(np.uint8)
    image[:band] = np.broadcast_to(grad[None, None, :], (band, 3, width)).transpose(0, 2, 1)
    # Band 2: hue sweep at mid lightness/chroma through the Lab roundtrip.
    for x in range(width):
        hue = 2 * math.pi * x / (width - 1)
        image[band:2 * band, x] = lab_to_srgb8((55.0, 45.0 * math.cos(hue),
                                                45.0 * math.sin(hue)))
    # Band 3: six saturated swatches across the hue circle.
    hues = (0.0, 30.0, 95.0, 140.0, 250.0, 290.0)
    for index, hue_deg in enumerate(hues):
        hue = math.radians(hue_deg)
        x0 = index * (width // 6)
        image[2 * band:3 * band, x0:x0 + width // 6] = lab_to_srgb8(
            (45.0, 55.0 * math.cos(hue), 55.0 * math.sin(hue)))
    # Band 4: left half fine 2px checkerboard, right half eight grey steps.
    yy, xx = np.mgrid[0:band, 0:width // 2]
    checker = (((xx // 2 + yy // 2) % 2) * 255).astype(np.uint8)
    image[3 * band:, :width // 2] = np.broadcast_to(checker[..., None],
                                                    (band, width // 2, 3))
    steps = 8
    for i in range(steps):
        x0 = width // 2 + i * (width // 2 // steps)
        image[3 * band:, x0:x0 + (width // 2 // steps)] = i * 255 // (steps - 1)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--palette", type=Path, default=DEFAULT_PALETTE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    out.mkdir(parents=True, exist_ok=False)

    palette = load_palette(args.palette)
    if palette.render_path != "l535_r20":
        raise SystemExit("demo requires the measured L535 palette (render_path l535_r20)")
    source = build_source_image()
    Image.fromarray(source, "RGB").save(out / "source.png")
    image = RasterImage(base.WIDTH, base.HEIGHT, "RGB", source.tobytes())
    result = quantize_image(
        image,
        palette=palette,
        options=PipelineOptions(DitherMode.FLOYD_STEINBERG),
    )
    frame = result.frame
    # L535 drive codes are 0..7 (white=7); the canonical stock contract does
    # not cover them, so validate explicitly against the full nibble set.
    validate_frame(frame, allowed_colors=list(range(8)))
    (out / "demo.frame4bpp").write_bytes(frame)
    preview = np.frombuffer(result.preview_rgb(), dtype=np.uint8).reshape(
        base.HEIGHT, base.WIDTH, 3)
    Image.fromarray(preview, "RGB").save(out / "preview-quantized.png")
    report = result.report.to_dict()
    manifest = {
        "kind": "mf1750-l535-fullcolor-demo-manifest-v1",
        "palette": {
            "palette_id": palette.palette_id,
            "render_path": palette.render_path,
            "calibrated": palette.calibrated,
            "canonical_sha256": palette.canonical_sha256,
            "calibration_measurement_id": palette.calibration.measurement_id,
        },
        "source_image": _bind(out / "source.png"),
        "frame": _bind(out / "demo.frame4bpp"),
        "preview": _bind(out / "preview-quantized.png"),
        "dither": "floyd-steinberg",
        "frame_validation": "host.epd_frame.validate_frame with explicit "
                            "allowed_colors 0..7 (L535 drive semantics; the "
                            "stock contract's physical set does not apply)",
        "code_histogram": report["usage"],
        "frame_sha256_from_pipeline": report["frame_sha256"],
        "display_gap": "needs a firmware variant that loads the L535 R20 LUT "
                       "and accepts an arbitrary frame (next field task)",
        "hardware_accessed": False,
    }
    manifest["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(base.canonical(manifest)).hexdigest(),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(out),
                      "frame_sha256": report["frame_sha256"],
                      "hardware_accessed": False}, ensure_ascii=False, indent=2))


def _bind(path: Path) -> dict:
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


if __name__ == "__main__":
    main()
