"""LH3 dose pack derivation tests; fully offline, synthetic white records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from host.static_photo import lightness_history_lh3_dose as lh3dose
from tools import mf1750_lh3_dose_pack as pack

ROOT = Path(__file__).resolve().parents[1]


def _workspace(root: Path) -> Path:
    # base.prepare() writes a relative platformio.ini, so the synthetic package
    # must live inside the repository; it is removed after the test.
    return Path(tempfile.mkdtemp(prefix="lh3dosepacktest_", dir=root / ".test-output"))


def _sealed(value: dict) -> dict:
    body = {k: v for k, v in value.items() if k != "integrity"}
    payload = lh3dose.canonical(body)
    return {**body, "integrity": {"algorithm": "sha256-canonical-json-without-integrity",
                                  "sha256": hashlib.sha256(payload).hexdigest()}}


def _white_records(root: Path) -> tuple[dict, str]:
    white = root / "white"
    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH3_SOURCE_WHITE_V1_20260918",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = _sealed({"kind": "synthetic-lh3-white-close-review", "protocol": "PASS",
                     "terminal_report": terminal_report})
    (white / "close-review-v1.json").write_bytes(lh3dose.canonical(close) + b"\n")
    (white / pack.WHITE_RECORD_NAMES["app_flash"]).write_text(
        json.dumps({"binary": {"observed_sha256": "c" * 64}}), encoding="utf-8")
    (white / "live-white-v1").mkdir()
    (white / "live-white-v1" / "result.json").write_bytes(
        lh3dose.canonical(_sealed({"kind": "synthetic-lh3-white-result", "terminal_report": terminal_report})) + b"\n")
    (white / "postwhite-optical-review-v1.json").write_bytes(
        lh3dose.canonical(_sealed({"kind": "synthetic-lh3-white-optical-review"})) + b"\n")
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
    # The pinned anchor must equal the real LH3 white close-review file digest
    # on disk; the record's own integrity sha256 is a different, also-verified
    # value (see pack module comment).
    close = pack.WHITE / pack.REAL_RECORD_NAMES["close_review"]
    assert hashlib.sha256(close.read_bytes()).hexdigest() == pack.ANCHOR_SHA


def test_contract_actions_and_dose_frames(prepared):
    out, c = prepared
    assert [a["stage"] for a in c["actions"]] == ["SOURCE", "DOSE1", "DOSE2"]
    assert [a["role"] for a in c["actions"]] == ["LH3_SOURCE", "LH3_DOSE1", "LH3_DOSE2"]
    assert [a["driver_role"] for a in c["actions"]] == ["Source", "Mid", "Target"]
    assert [a["global_header"] for a in c["actions"]] == ["active", "commented", "commented"]
    assert [a["branch"] for a in c["actions"]] == [
        "LH3_SYMMETRIC_SOURCE", "LH3_SYMMETRIC_DOSE1", "LH3_SYMMETRIC_DOSE2"]
    assert c["actions"][0]["source_state"] == pack.SOURCE_STATE
    assert c["actions"][1]["source_state"] == "LH3_SOURCE"
    assert c["actions"][2]["source_state"] == "LH3_DOSE1"
    assert c["actions"][0]["frame"]["histogram"] == [0] * 7 + [614400]
    for index in (1, 2):
        assert c["actions"][index]["frame"]["histogram"] == [33280] * 7 + [381440]
    # The dose-axis independent variable: DOSE2 is byte-identical to DOSE1.
    assert c["actions"][1]["frame"] == c["actions"][2]["frame"]
    assert c["actions"][1]["cs1_dtm"] == c["actions"][2]["cs1_dtm"]
    assert c["actions"][1]["cs2_dtm"] == c["actions"][2]["cs2_dtm"]
    assert c["actions"][1]["action_id"] != c["actions"][2]["action_id"]
    assert (out / "dose1.frame4bpp").read_bytes() == lh3dose.frame("DOSE1")
    assert (out / "dose2.frame4bpp").read_bytes() == lh3dose.frame("DOSE2")
    assert c["nvs"] == {"namespace": "lh3dose_v2", "cursor": "cur_lh3d2", "boot": "boot_lh3d2"}
    assert c["level_counts"] is None
    assert "recipes_per_target" not in c
    assert c["dose_axis"]["dose2_frame_byte_identical_to_dose1"] is True
    assert c["dose_axis"]["rows_per_code_per_side"] == 8
    assert c["old_fault_preservation"]["expected_cursor_raw"] == 770
    assert c["rebound_v2_terminal_preservation"]["expected_boot"] == "7274e005c8833ca1"
    assert c["lh2_map_terminal_preservation"]["expected_cursor_raw"] == 4
    assert c["lh2_map_terminal_preservation"]["expected_boot"] == "ac92bb9e25c374ef"
    assert c["lh2_white_preservation"]["expected_cursor_raw"] == 2
    v1 = c["lh3_dose_v1_bricked_preservation"]
    assert v1["namespace"] == "lh3dose_v1" and v1["expected_cursor_raw"] == 769
    assert v1["recoverable"] is False and v1["must_remain_untouched"] is True
    assert v1["driver_call_count_at_brick"] == 0
    assert c["algorithm_id"] == lh3dose.TEST_ID
    assert c["source_white"]["nvs_namespace"] == "lh3srcw_v1"
    assert c["source_white"]["nvs_key"] == "used_lh3sw1"


def test_generated_sources_carry_lh3_dose_rules(prepared):
    out, c = prepared
    gen = out / "generated"
    main = (gen / (pack.PREFIX + "_main.cpp")).read_text(encoding="utf-8")
    assert "FRESH_P2_FACTORY_WHITE" not in main
    assert "LH3 dose history V2" in main
    ordinal3 = [line for line in main.split("\n") if "if(action.ordinal==3) return String(" in line]
    assert len(ordinal3) == 1 and '\\"controller_tuple_dispatch\\":\\"CC\\"' in ordinal3[0]
    driver = (gen / (pack.PREFIX + "_driver.inc")).read_text(encoding="utf-8")
    assert driver.count(
        "if (role == EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target) useCommentedGlobal = true;") == 1
    assert driver.count(
        "ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||") == 1
    assert "ph::kTargetCodes[0] != 3" not in driver
    hpp = (gen / "lh_frame_fill.hpp").read_text(encoding="utf-8")
    assert "code=role==1 ? 7 : (uint8_t)(i%8);" in hpp
    identity = (gen / (pack.PREFIX + "_identity.inc")).read_text(encoding="utf-8")
    assert "kTargetCodes[8]={0,1,2,3,4,5,6,7}" in identity
    assert pack.CPP_NAMESPACE in identity
    config = (gen / (pack.PREFIX + "_main_config.inc")).read_text(encoding="utf-8")
    assert '\\"target_codes\\":[0,1,2,3,4,5,6,7]' in config
    assert '\\"symmetric_tuple_sequence\\":[\\"AA\\",\\"CC\\",\\"CC\\"]' in config
    assert '\\"level_counts\\":null' in config
    assert "LH3_DOSE_COLUMNS_8X8" in config
    assert '"lh3dose_v2"' in config and '"cur_lh3d2"' in config and '"boot_lh3d2"' in config
    assert "MF1750_LH3_DOSE_V2_COMPILED|CONTRACT=" in config
    # The white gate must require the preserved namespaces, the LH2 drive-map
    # terminal, the LH2 white marker, the consumed LH3 white marker and the
    # bricked V1 dose namespace pinned at its fault cursor 769.
    assert "oldFaultPreserved" in main and "reboundV2TerminalPreserved" in main
    assert "lh2DriveMapTerminalComplete" in main and "lh2WhitePreserved" in main
    assert "lh3DoseV1BrickedPreserved" in main
    assert 'old.getUShort("cur_lh3d",0)==769' in main
    assert 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL' in main
    assert 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL' in main
    assert 'source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL' in main
    assert 'white.getUShort("used_lh2sw1",0)==2' in main
    assert 'white.begin("lh3srcw_v1", true)' in main
    assert 'white.getUShort("used_lh3sw1",0)==2' in main


def test_cpp_dose_rule_matches_python_frame(prepared):
    # Mirror the exact C++ index arithmetic from lh_frame_fill.hpp and require
    # byte equality with the Python-generated DOSE frames.
    out, c = prepared
    for stage in ("DOSE1", "DOSE2"):
        frame = bytearray([0x77]) * (1024 * 600 // 2)
        for cs in range(2):
            for i in range(64):
                code = i % 8
                x = cs * 512 + 68 + (i % 8) * (40 + 8)
                y = 64 + (i // 8) * (52 + 8)
                for row in range(y, y + 52):
                    start = row * 512 + x // 2
                    frame[start:start + 20] = bytes([code * 17]) * 20
        assert bytes(frame) == lh3dose.frame(stage)
        assert bytes(frame) == (out / (stage.lower() + ".frame4bpp")).read_bytes()
