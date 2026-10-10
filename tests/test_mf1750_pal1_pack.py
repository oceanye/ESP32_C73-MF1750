"""PAL1 pack derivation tests; fully offline, synthetic white records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from host.static_photo import palette_cal_pal1 as pal1
from tools import mf1750_pal1_pack as pack

ROOT = Path(__file__).resolve().parents[1]


def _workspace(root: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix="pal1packtest_", dir=root / ".test-output"))


def _sealed(value: dict) -> dict:
    body = {k: v for k, v in value.items() if k != "integrity"}
    payload = pal1.canonical(body)
    return {**body, "integrity": {"algorithm": "sha256-canonical-json-without-integrity",
                                  "sha256": hashlib.sha256(payload).hexdigest()}}


def _white_records(root: Path) -> tuple[dict, str]:
    # Same byte-identical synthetic recipe as the LH3 dose tests/audit.
    white = root / "white"
    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH3_SOURCE_WHITE_V1_20260918",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = _sealed({"kind": "synthetic-lh3-white-close-review", "protocol": "PASS",
                     "terminal_report": terminal_report})
    (white / "close-review-v1.json").write_bytes(pal1.canonical(close) + b"\n")
    (white / pack.WHITE_RECORD_NAMES["app_flash"]).write_text(
        json.dumps({"binary": {"observed_sha256": "c" * 64}}), encoding="utf-8")
    (white / "live-white-v1").mkdir()
    (white / "live-white-v1" / "result.json").write_bytes(
        pal1.canonical(_sealed({"kind": "synthetic-lh3-white-result", "terminal_report": terminal_report})) + b"\n")
    (white / "postwhite-optical-review-v1.json").write_bytes(
        pal1.canonical(_sealed({"kind": "synthetic-lh3-white-optical-review"})) + b"\n")
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


def test_sealed_real_anchor_matches_white_batch():
    close = pack.WHITE / pack.REAL_RECORD_NAMES["close_review"]
    assert hashlib.sha256(close.read_bytes()).hexdigest() == pack.ANCHOR_SHA
    assert pack.ANCHOR_SHA == "5dd81034bd9a963d89b91fc4ce9e7a01d8eaf4f99fc883e8ce0a3bc8f77dc9b0"


def test_contract_single_action_and_frame(prepared):
    out, c = prepared
    assert c["action_count"] == 1
    assert len(c["actions"]) == 1
    a = c["actions"][0]
    assert a["ordinal"] == 1 and a["stage"] == "PAL1"
    assert a["role"] == "PAL1_CAL" and a["driver_role"] == "Source"
    assert a["branch"] == "PAL1_SYMMETRIC_ACTIVE"
    assert a["global_header"] == "active"
    assert a["source_state"] == pack.SOURCE_STATE
    assert a["target_state"] == "PAL1_CAL"
    assert a["prior_action_id"] is None
    assert a["frame"]["histogram"] == [33280] * 7 + [381440]
    assert (out / "pal1.frame4bpp").read_bytes() == pal1.frame("PAL1")
    assert c["nvs"] == {"namespace": "pal1_v5", "cursor": "cur_pal5", "boot": "boot_pal5"}
    assert c["level_counts"] is None
    assert c["palette_calibration"]["physical_palette_codes"] == [0, 1, 2, 3, 5, 6]
    assert c["palette_calibration"]["record_only_codes"] == [4, 7]
    assert c["lh3_dose_v1_bricked_preservation"]["expected_cursor_raw"] == 769
    v2 = c["lh3_dose_v2_terminal_preservation"]
    assert v2["expected_cursor_raw"] == 4
    assert v2["expected_boot"] == "4d53de6fe4b39d3b"
    assert v2["campaign_complete"] is True
    assert c["lh2_map_terminal_preservation"]["expected_boot"] == "ac92bb9e25c374ef"
    v1 = c["pal1_v1_fixture_defect_preservation"]
    assert v1["expected_cursor_raw"] == 1 and v1["fault_persisted"] is False
    assert v1["driver_call_count_at_failure"] == 0 and v1["recoverable"] is False
    assert v1["boot_key_present_required"] is True and v1["boot_value_pinned"] is False
    assert v1["cursor_key_may_be_absent"] is True
    v2 = c["pal1_v2_gate_mismatch_preservation"]
    assert v2["namespace"] == "pal1_v2" and v2["cursor_key_may_be_absent"] is True
    assert v2["recoverable"] is False
    assert c["algorithm_id"] == pal1.TEST_ID


def test_generated_sources_carry_pal1_rules(prepared):
    out, c = prepared
    gen = out / "generated"
    main = (gen / (pack.PREFIX + "_main.cpp")).read_text(encoding="utf-8")
    assert "FRESH_P2_FACTORY_WHITE" not in main
    assert "PAL1 measured palette calibration V5" in main
    assert "static constexpr uint8_t kActionCount = 1;" in main
    ordinal1 = [line for line in main.split("\n") if "if(action.ordinal==1) return String(" in line]
    assert len(ordinal1) == 1 and '\\"controller_tuple_dispatch\\":\\"AA\\"' in ordinal1[0]
    assert "if(action.ordinal==2) return String(" not in main
    driver = (gen / (pack.PREFIX + "_driver.inc")).read_text(encoding="utf-8")
    # Active header: the commented branch stays Mid-only; Target must NOT be added.
    assert driver.count(
        "#if defined(" + pack.MACRO + ")\n"
        "  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;") == 1
    assert "#if defined(" + pack.MACRO + ")\n" \
        "  if (role == EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target)" not in driver
    assert driver.count(
        "ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||") == 1
    assert "ph::kTargetCodes[0] != 3" not in driver
    hpp = (gen / "lh_frame_fill.hpp").read_text(encoding="utf-8")
    assert "code=role==1 ? (uint8_t)(i%8) : 7;" in hpp
    identity = (gen / (pack.PREFIX + "_identity.inc")).read_text(encoding="utf-8")
    assert "kTargetCodes[8]={0,1,2,3,4,5,6,7}" in identity
    assert "kActions[2]=" in identity
    assert pack.CPP_NAMESPACE in identity
    config = (gen / (pack.PREFIX + "_main_config.inc")).read_text(encoding="utf-8")
    assert '\\"target_codes\\":[0,1,2,3,4,5,6,7]' in config
    assert '\\"symmetric_tuple_sequence\\":[\\"AA\\"]' in config
    assert '\\"level_counts\\":null' in config
    assert "PAL1_COLUMNS_8X8" in config
    assert '"pal1_v5"' in config and '"cur_pal5"' in config and '"boot_pal5"' in config
    assert "MF1750_PAL1_V5_COMPILED|CONTRACT=" in config
    for token in ("oldFaultPreserved", "reboundV2TerminalPreserved",
                  "lh2DriveMapTerminalComplete", "lh2WhitePreserved",
                  "lh3DoseV1BrickedPreserved", "lh3DoseV2TerminalComplete",
                  "pal1V1DeadPreserved", "pal1V2DeadPreserved",
                  "pal1V3DeadPreserved", "pal1V4DeadPreserved",
                  "lh3WhiteConsumed", "lhGateDetailJson"):
        assert token in main
    assert 'old.isKey("boot_pal1")' in main and 'old.isKey("boot_pal2")' in main
    assert 'old.isKey("boot_pal3")' in main and 'old.isKey("boot_pal4")' in main
    assert '!old.isKey("cur_pal1") || old.getUShort("cur_pal1",0)==1' in main
    assert '!old.isKey("cur_pal3") || old.getUShort("cur_pal3",0)==1' in main
    assert '!old.isKey("cur_pal4") || old.getUShort("cur_pal4",0)==1' in main
    assert 'cur==1 || cur==769' in main  # pal1_v2 accepts the inferred fault cursor
    assert '\\"gate_detail\\":{' in main
    v3 = c["pal1_v3_dead_preservation"]
    assert v3["namespace"] == "pal1_v3" and v3["cursor_key_may_be_absent"] is True
    assert v3["recoverable"] is False
    v2 = c["pal1_v2_gate_mismatch_preservation"]
    assert v2["inferred_cursor_fault_769"] is True
    v4 = c["pal1_v4_dead_preservation"]
    assert v4["namespace"] == "pal1_v4" and v4["cursor_key_may_be_absent"] is True
    assert "kRoles[] = {EpdChromaGridRole::Source};" in driver
    assert "return phRoleIndex(role) == 1;" in driver
    assert 'old.getUShort("cur_lh3d",0)==769' in main
    assert 'source.getUShort("cur_lh3d2",0)==4' in main
    assert 'source.getULong64("boot_lh3d2",0)==0x4d53de6fe4b39d3bULL' in main
    assert 'white.begin("lh3srcw_v1", true)' in main
    assert 'white.getUShort("used_lh3sw1",0)==2' in main


def test_cpp_pal1_rule_matches_python_frame(prepared):
    out, c = prepared
    frame = bytearray([0x77]) * (1024 * 600 // 2)
    for cs in range(2):
        for i in range(64):
            code = i % 8
            x = cs * 512 + 68 + (i % 8) * (40 + 8)
            y = 64 + (i // 8) * (52 + 8)
            for row in range(y, y + 52):
                start = row * 512 + x // 2
                frame[start:start + 20] = bytes([code * 17]) * 20
    assert bytes(frame) == pal1.frame("PAL1")
    assert bytes(frame) == (out / "pal1.frame4bpp").read_bytes()
