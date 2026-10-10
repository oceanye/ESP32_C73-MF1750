"""L535 measured palette / schema extension / demo frame tests; fully offline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from host.color_pipeline.palette import (
    PaletteError, load_palette, palette_from_mapping,
)
from host.color_pipeline.pipeline import (
    DitherMode, PipelineOptions, RasterImage, quantize_image,
)
from host.epd_frame import FrameContractError, validate_frame
from host.gamut_mapping.profile import load_gamut_profile

ROOT = Path(__file__).resolve().parents[1]
PALETTE = ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json"
PROFILE = ROOT / "host/gamut_mapping/profiles/mf1750_l535_measured_xyz_v1.json"
DEMO = ROOT / ".test-output/offline/L535_FULLCOLOR_DEMO_20260926_V1"


def _l535_doc(**overrides):
    doc = json.loads(PALETTE.read_text(encoding="utf-8"))
    for key, value in overrides.items():
        doc[key] = value
    return doc


def test_otp_path_unchanged():
    reference = load_palette(ROOT / "host/color_pipeline/palettes/reference_srgb_v1.json")
    assert reference.render_path == "otp"
    # The pinned reference canonical hash must not move (schema extension is
    # backward compatible; render_path only enters the hash when set).
    assert reference.canonical_sha256 == \
        "181770a2de3bb23bcc31666573279c8cde8225d2f4c27a24c9c1345dba54965e"
    assert b"render_path" not in reference.canonical_bytes()


def test_l535_palette_binds_and_hashes():
    palette = load_palette(PALETTE)
    assert palette.render_path == "l535_r20"
    assert palette.calibrated is True
    assert palette.calibration.measurement_id == "PAL1_CAL_BRIGHT_20260925_V1"
    assert palette.calibration.artifact_sha256
    codes = [entry.code for entry in palette.entries]
    assert sorted(codes) == [0, 1, 3, 4, 6, 7]
    assert {entry.name for entry in palette.entries} == {
        "black", "white", "yellow", "red", "blue", "green"}
    by_name = {entry.name: entry for entry in palette.entries}
    assert by_name["white"].code == 7
    assert by_name["black"].code == 3
    white_l = by_name["white"].lab[0]
    black_l = by_name["black"].lab[0]
    assert all(white_l > e.lab[0] and black_l < e.lab[0]
               for e in palette.entries if e.name not in ("white", "black"))
    doc = json.loads(palette.canonical_bytes())
    assert doc["render_path"] == "l535_r20"
    # Roundtrip: mapping -> Palette -> canonical bytes are stable.
    again = palette_from_mapping(json.loads(PALETTE.read_text(encoding="utf-8")))
    assert again.canonical_sha256 == palette.canonical_sha256


def test_l535_gates_fail_closed():
    # Black not darkest (but still below white so the white gate passes first).
    bad = _l535_doc()
    for entry in bad["entries"]:
        if entry["name"] == "black":
            entry["lab"][0] = 60.0
    with pytest.raises(PaletteError, match="darkest"):
        palette_from_mapping(bad)
    # White not brightest.
    bad = _l535_doc()
    for entry in bad["entries"]:
        if entry["name"] == "white":
            entry["lab"][0] = 1.0
    with pytest.raises(PaletteError, match="brightest"):
        palette_from_mapping(bad)
    # Chromatic role neutral.
    bad = _l535_doc()
    for entry in bad["entries"]:
        if entry["name"] == "red":
            entry["lab"] = [40.0, 1.0, 1.0]
    with pytest.raises(PaletteError, match="chromatic"):
        palette_from_mapping(bad)
    # Unknown render path rejected.
    with pytest.raises(PaletteError, match="render_path"):
        palette_from_mapping(_l535_doc(render_path="exotic"))
    # Role names must stay the six physical names.
    bad = _l535_doc()
    bad["entries"][0]["name"] = "not-a-role"
    with pytest.raises(PaletteError, match="role names"):
        palette_from_mapping(bad)


def test_l535_gamut_profile_binds_palette():
    palette = load_palette(PALETTE)
    profile = load_gamut_profile(PROFILE, palette)
    assert profile.render_path == "l535_r20"
    assert profile.characterization_level == "measured_primaries"
    assert [item.code for item in profile.pure_sample_refs] == [0, 1, 3, 4, 6, 7]
    assert all(item.artifact_sha256 for item in profile.pure_sample_refs)
    # Mismatched render_path refuses.
    doc = json.loads(PROFILE.read_text(encoding="utf-8"))
    doc["model"]["render_path"] = "otp"
    with pytest.raises(Exception):
        from host.gamut_mapping.profile import gamut_profile_from_mapping
        gamut_profile_from_mapping(doc, palette)
    # The OTP synthetic profile still loads on the reference palette.
    reference = load_palette(ROOT / "host/color_pipeline/palettes/reference_srgb_v1.json")
    synthetic = load_gamut_profile(
        ROOT / "host/gamut_mapping/profiles/synthetic_reference_linear_xyz_v1.json",
        reference)
    assert synthetic.render_path == "otp"


def test_demo_outputs_and_frame_semantics():
    manifest = json.loads((DEMO / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["integrity"]["sha256"] == hashlib.sha256(
        __import__("host.static_photo.lightness_history", fromlist=["canonical"])
        .canonical({k: v for k, v in manifest.items() if k != "integrity"})
    ).hexdigest()
    assert manifest["palette"]["canonical_sha256"] == load_palette(PALETTE).canonical_sha256
    frame = (DEMO / "demo.frame4bpp").read_bytes()
    assert manifest["frame"]["sha256"] == hashlib.sha256(frame).hexdigest()
    assert manifest["frame_sha256_from_pipeline"] == manifest["frame"]["sha256"]
    # L535 semantics: the demo frame drives nibbles outside the stock set.
    validate_frame(frame, allowed_colors=list(range(8)))
    with pytest.raises(FrameContractError):
        validate_frame(frame)  # stock contract must refuse L535 codes
    assert (DEMO / "preview-quantized.png").stat().st_size > 1000
    assert manifest["hardware_accessed"] is False


def test_demo_o_excl_and_palette_gate(tmp_path):
    out = tmp_path / "demo"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_l535_fullcolor_demo.py"),
         "--output-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["result"] != "FAIL" if "result" in manifest else True
    assert manifest["frame"]["sha256"]
    # Second run refuses (O_EXCL).
    again = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_l535_fullcolor_demo.py"),
         "--output-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert again.returncode != 0
    # OTP palette is refused by the demo tool.
    refused = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_l535_fullcolor_demo.py"),
         "--palette", str(ROOT / "host/color_pipeline/palettes/reference_srgb_v1.json"),
         "--output-dir", str(tmp_path / "never")],
        cwd=ROOT, capture_output=True, text=True)
    assert refused.returncode != 0
    assert "l535_r20" in refused.stderr or "l535_r20" in refused.stdout
