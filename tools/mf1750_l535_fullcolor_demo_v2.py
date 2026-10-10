#!/usr/bin/env python3
"""L535 demo v2 frame: v1 source image rotated 180 degrees as compensation.

The L535_DEMO_20260926_V1 batch showed the panel renders the frame globally
rotated 180 degrees vs the host frame coordinate system (correlation 0.766,
decisive vs all other geometry candidates). This v2 frame pre-rotates the
source so that, if the rotation persists, the on-screen content matches the
upright preview. Same palette, same Floyd-Steinberg quantization, same frame
packing as tools/mf1750_l535_fullcolor_demo.py.

Outputs (O_EXCL) into .test-output/offline/L535_DEMO_V2_20260927_V1/:
source-rot180.png, demo-v2.frame4bpp, preview-quantized.png, manifest.json.

Fully offline; no device, network, relay or camera access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.palette import load_palette  # noqa: E402
from host.color_pipeline.pipeline import (  # noqa: E402
    DitherMode, PipelineOptions, RasterImage, quantize_image,
)
from host.epd_frame import validate_frame  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402
from tools.mf1750_l535_fullcolor_demo import _bind  # noqa: E402

V1_OUT = ROOT / ".test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1"
V2_OUT = ROOT / ".test-output/offline/L535_DEMO_V2_20260927_V1"
PALETTE = ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json"


def main() -> None:
    if V2_OUT.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    V2_OUT.mkdir(parents=True, exist_ok=False)

    source_v1 = np.asarray(Image.open(V1_OUT / "source.png").convert("RGB"))
    rotated = np.rot90(source_v1, 2).copy()  # exact 180-degree rotation
    Image.fromarray(rotated, "RGB").save(V2_OUT / "source-rot180.png")

    palette = load_palette(PALETTE)
    if palette.render_path != "l535_r20":
        raise SystemExit("demo v2 requires the measured L535 palette (render_path l535_r20)")
    image = RasterImage(base.WIDTH, base.HEIGHT, "RGB", rotated.tobytes())
    result = quantize_image(
        image,
        palette=palette,
        options=PipelineOptions(DitherMode.FLOYD_STEINBERG),
    )
    frame = result.frame
    validate_frame(frame, allowed_colors=list(range(8)))
    (V2_OUT / "demo-v2.frame4bpp").write_bytes(frame)
    preview = np.frombuffer(result.preview_rgb(), dtype=np.uint8).reshape(
        base.HEIGHT, base.WIDTH, 3)
    Image.fromarray(preview, "RGB").save(V2_OUT / "preview-quantized.png")
    report = result.report.to_dict()
    manifest = {
        "kind": "mf1750-l535-fullcolor-demo-v2-manifest-v1",
        "compensation": {
            "transform": "source image rotated 180 degrees before quantization",
            "reason": ("L535_DEMO_20260926_V1: on-screen content equals the v1 preview "
                       "under a global 180-degree rotation (corr 0.766, decisive); "
                       "if the rotation persists, v2 renders upright on the panel"),
            "source_v1": _bind(V1_OUT / "source.png"),
            "v1_batch": ".test-output/hardware/L535_DEMO_20260926_V1",
        },
        "palette": {
            "palette_id": palette.palette_id,
            "render_path": palette.render_path,
            "canonical_sha256": palette.canonical_sha256,
        },
        "source_rot180": _bind(V2_OUT / "source-rot180.png"),
        "frame": _bind(V2_OUT / "demo-v2.frame4bpp"),
        "preview": _bind(V2_OUT / "preview-quantized.png"),
        "dither": "floyd-steinberg",
        "frame_validation": "host.epd_frame.validate_frame with explicit allowed_colors 0..7",
        "code_histogram": report["usage"],
        "frame_sha256_from_pipeline": report["frame_sha256"],
        "hardware_accessed": False,
    }
    manifest["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(base.canonical(manifest)).hexdigest(),
    }
    (V2_OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(V2_OUT),
                      "frame_sha256": report["frame_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
