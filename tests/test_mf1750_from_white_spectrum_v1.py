"""From-white spectrum v0 sealed report assertions; fully offline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path(".test-output/offline/FROM_WHITE_SPECTRUM_20260918_V1")


def test_spectrum_report_sealed_and_counts():
    report = json.loads((OUT / "spectrum.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in report.items() if k != "integrity"}
    digest = hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert report["integrity"]["sha256"] == digest
    assert report["qualified_count"] == 0
    assert report["camera_relative_only"] is True
    assert report["from_white_code_space_exhausted"] is True
    assert len(report["endpoints"]) == 8
    counts = report["level_counts"]
    assert counts["R"] == 3
    assert counts["NEUTRAL"] == 1
    ladders = {l["family"]: l for l in report["ladders"]}
    red = [r["middle_code"] for r in ladders["R"]["ladder"]]
    assert red == [0, 2, 1]  # ascending L*: 29.8 -> 39.8 -> 47.8
    # The V-family break M3 -> M5 (hue delta 6.3 deg > 5 deg frozen gate)
    # must be recorded, not silently merged.
    assert ladders["V"]["level_count"] == 1
    assert ladders["V"]["chain_breaks"][0]["delta_hue_degrees"] > 5.0


def test_spectrum_png_bound_and_nonempty():
    report = json.loads((OUT / "spectrum.json").read_text(encoding="utf-8"))
    png = OUT / "spectrum.png"
    data = png.read_bytes()
    assert len(data) == report["spectrum_png"]["bytes"]
    assert hashlib.sha256(data).hexdigest() == report["spectrum_png"]["sha256"]
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
