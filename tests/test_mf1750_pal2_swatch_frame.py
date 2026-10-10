"""PAL2 swatch frame generator tests; fully offline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from host.epd_frame import PHYSICAL_COLOR_CODES, validate_frame
from host.static_photo import palette_cal_pal1 as pal1
from tools import mf1750_pal2_swatch_frame as sw

KIT = Path(".test-output/offline/PAL2_SWATCH_20260925_V1")
PAL1_FRAME = Path(".test-output/offline/PAL1_CAL_20260925_R2/pal1.frame4bpp")


def test_frame_canonical_and_layout():
    frame = sw.frame()
    assert len(frame) == 307200
    validate_frame(frame)  # codes 4/7 must never appear
    identity = pal1.payload_identity(frame, True)
    # White code 1 owns the background plus columns 1/4/7; codes 4/7 are absent.
    assert identity["histogram"] == [33280, 448000, 33280, 33280, 0, 33280, 33280, 0]


def test_shared_columns_byte_identical_to_pal1():
    result = sw.pal1_column_comparison(PAL1_FRAME, sw.frame())
    assert result["status"] == "PASS"
    assert len(result["columns"]) == 6
    # Columns 4/7 differ by design (PAL1 drove codes 4/7; PAL2 fills white).
    pal1_frame = PAL1_FRAME.read_bytes()
    pal2 = sw.frame()
    from host.static_photo import lightness_history as base
    x = base.X0 + 7 * (base.CELL_W + base.GAP)
    y = base.Y0
    start = y * (base.WIDTH // 2) + x // 2
    span = slice(start, start + base.CELL_W // 2)
    assert pal1_frame[span] == bytes([7 * 17]) * 20
    assert pal2[span] == bytes([17]) * 20


def test_sealed_kit_and_report():
    contract = json.loads((KIT / "analysis-kit/contract.json").read_text(encoding="utf-8"))
    assert contract["kind"] == "mf1750-pal2-analysis-kit-v1"
    assert contract["not_a_campaign_package"] is True
    assert contract["codes_4_and_7_white_filled"] is True
    body = {k: v for k, v in contract.items() if k != "contract_id"}
    assert pal1.digest(pal1.canonical(body)) == contract["contract_id"]
    action = contract["actions"][0]
    assert action["frame"]["sha256"] == pal1.digest((KIT / "pal2.frame4bpp").read_bytes())
    blank = json.loads((KIT / "analysis-kit/observations.blank.json").read_text(encoding="utf-8"))
    assert len(blank["observations"]) == 128
    assert blank["identity"]["action_sha256"] == action["action_id"]
    report = json.loads((KIT / "report.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in report.items() if k != "integrity"}
    assert report["integrity"]["sha256"] == \
        __import__("hashlib").sha256(pal1.canonical(body)).hexdigest()
    assert report["canonical_validate_frame"] == "PASS"
    assert report["frame"]["sha256"] == action["frame"]["sha256"]


def test_output_dir_o_excl(tmp_path):
    out = tmp_path / "kit"
    out.mkdir()
    with pytest.raises(SystemExit, match="O_EXCL|must not exist"):
        import sys
        old = sys.argv
        sys.argv = ["x", "--output-dir", str(out)]
        try:
            sw.main()
        finally:
            sys.argv = old
