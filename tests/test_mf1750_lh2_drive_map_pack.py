"""LH2 drive-map pack derivation tests; fully offline, synthetic white records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from host.static_photo import lightness_history_lh2 as lh2
from tools import mf1750_lh2_drive_map_pack as pack

ROOT = Path(__file__).resolve().parents[1]


def _workspace(root: Path) -> Path:
    # base.prepare() writes a relative platformio.ini, so the synthetic package
    # must live inside the repository; it is removed after the test.
    return Path(tempfile.mkdtemp(prefix="lh2packtest_", dir=root / ".test-output"))


def _sealed(value: dict) -> dict:
    body = {k: v for k, v in value.items() if k != "integrity"}
    payload = lh2.canonical(body)
    return {**body, "integrity": {"algorithm": "sha256-canonical-json-without-integrity",
                                  "sha256": hashlib.sha256(payload).hexdigest()}}


def _white_records(root: Path) -> tuple[dict, str]:
    white = root / "white"
    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH2_SOURCE_WHITE_V1_20260917",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = _sealed({"kind": "synthetic-lh2-white-close-review", "protocol": "PASS",
                     "terminal_report": terminal_report})
    (white / "close-review-v1.json").write_bytes(lh2.canonical(close) + b"\n")
    (white / pack.WHITE_RECORD_NAMES["app_flash"]).write_text(
        json.dumps({"binary": {"observed_sha256": "c" * 64}}), encoding="utf-8")
    (white / "live-white-v1").mkdir()
    (white / "live-white-v1" / "result.json").write_bytes(
        lh2.canonical(_sealed({"kind": "synthetic-lh2-white-result", "terminal_report": terminal_report})) + b"\n")
    (white / "postwhite-optical-review-v1.json").write_bytes(
        lh2.canonical(_sealed({"kind": "synthetic-lh2-white-optical-review"})) + b"\n")
    records = {k: white / n for k, n in pack.WHITE_RECORD_NAMES.items()}
    anchor = hashlib.sha256((white / "close-review-v1.json").read_bytes()).hexdigest()
    return records, anchor


@pytest.fixture()
def prepared(tmp_path):
    work = _workspace(ROOT)
    try:
        records, anchor = _white_records(work)
        base = pack.configured(records, anchor)
        out = work / "pkg"
        result = base.prepare(out)
        assert result["result"] == "PASS_OFFLINE_PREPARED"
        yield out, json.loads((out / "contract.json").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_prepare_refuses_without_sealed_white_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "ANCHOR_SHA", None)
    with pytest.raises(ValueError):
        pack.prepare(tmp_path / "never")


def test_sealed_real_anchor_matches_white_batch():
    # The pinned anchor must equal the real LH2 white close-review on disk.
    import hashlib

    close = pack.WHITE / pack.WHITE_RECORD_NAMES["close_review"]
    assert hashlib.sha256(close.read_bytes()).hexdigest() == pack.ANCHOR_SHA


def test_contract_actions_and_map_frame(prepared):
    out, c = prepared
    assert [a["stage"] for a in c["actions"]] == ["SOURCE", "MIDDLE", "MAP"]
    assert [a["role"] for a in c["actions"]] == ["LH2_SOURCE", "LH2_MIDDLE", "LH2_MAP"]
    assert [a["driver_role"] for a in c["actions"]] == ["Source", "Mid", "Target"]
    assert [a["global_header"] for a in c["actions"]] == ["active", "commented", "commented"]
    assert [a["branch"] for a in c["actions"]] == [
        "LH2_SYMMETRIC_SOURCE", "LH2_SYMMETRIC_MIDDLE", "LH2_SYMMETRIC_MAP"]
    assert c["actions"][0]["source_state"] == pack.SOURCE_STATE
    assert c["actions"][1]["source_state"] == "LH2_SOURCE"
    assert c["actions"][2]["source_state"] == "LH2_MIDDLE"
    assert c["actions"][2]["frame"]["histogram"] == [33280] * 7 + [381440]
    assert (out / "map.frame4bpp").read_bytes() == lh2.frame("MAP")
    assert c["nvs"] == {"namespace": "lh2map_v1", "cursor": "cur_lh2m", "boot": "boot_lh2m"}
    assert c["level_counts"] is None
    assert c["drive_map"]["histories_per_map_code_per_side"] == 8
    assert c["old_fault_preservation"]["expected_cursor_raw"] == 770
    assert c["rebound_v2_terminal_preservation"]["expected_boot"] == "7274e005c8833ca1"
    assert c["algorithm_id"] == lh2.TEST_ID


def test_generated_sources_carry_lh2_rules(prepared):
    out, c = prepared
    gen = out / "generated"
    main = (gen / (pack.PREFIX + "_main.cpp")).read_text(encoding="utf-8")
    assert "FRESH_P2_FACTORY_WHITE" not in main
    assert "LH2 drive-map history V1" in main
    ordinal3 = [line for line in main.split("\n") if "if(action.ordinal==3) return String(" in line]
    assert len(ordinal3) == 1 and '\\"controller_tuple_dispatch\\":\\"CC\\"' in ordinal3[0]
    driver = (gen / (pack.PREFIX + "_driver.inc")).read_text(encoding="utf-8")
    assert driver.count(
        "if (role == EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target) useCommentedGlobal = true;") == 1
    assert driver.count(
        "ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||") == 1
    assert "ph::kTargetCodes[0] != 3" not in driver
    hpp = (gen / "lh_frame_fill.hpp").read_text(encoding="utf-8")
    assert "(uint8_t)(4*(recipe/8)+((i/8)>=4?2:0)+((i%8)>=4?1:0))" in hpp
    identity = (gen / (pack.PREFIX + "_identity.inc")).read_text(encoding="utf-8")
    assert "kTargetCodes[8]={0,1,2,3,4,5,6,7}" in identity
    assert pack.CPP_NAMESPACE in identity
    config = (gen / (pack.PREFIX + "_main_config.inc")).read_text(encoding="utf-8")
    assert '\\"target_codes\\":[0,1,2,3,4,5,6,7]' in config
    assert '\\"symmetric_tuple_sequence\\":[\\"AA\\",\\"CC\\",\\"CC\\"]' in config
    assert '\\"level_counts\\":null' in config
    assert "LH2_DRIVE_MAP_8X8" in config
    assert '"lh2map_v1"' in config and '"cur_lh2m"' in config and '"boot_lh2m"' in config
    assert "MF1750_LH2_COMPILED|CONTRACT=" in config
    # The white gate must require both preserved namespaces plus the LH2 white.
    assert "oldFaultPreserved" in main and "reboundV2TerminalPreserved" in main
    assert 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL' in main
    assert 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL' in main
    assert 'white.begin("lh2srcw_v1", true)' in main


def test_cpp_map_rule_matches_python_frame(prepared):
    # Mirror the exact C++ index arithmetic from lh_frame_fill.hpp and require
    # byte equality with the Python-generated MAP frame.
    out, c = prepared
    placement = lh2.placement()
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    for cs in range(2):
        cells = placement[cs]
        for i in range(64):
            recipe = cells[i]
            code = 4 * (recipe // 8) + (2 if (i // 8) >= 4 else 0) + (1 if (i % 8) >= 4 else 0)
            x = cs * 512 + 68 + (i % 8) * (40 + 8)
            y = 64 + (i // 8) * (52 + 8)
            for row in range(y, y + 52):
                start = row * 512 + x // 2
                frame[start:start + 20] = bytes([code * 17]) * 20
    assert bytes(frame) == lh2.frame("MAP")
    assert bytes(frame) == (out / "map.frame4bpp").read_bytes()
