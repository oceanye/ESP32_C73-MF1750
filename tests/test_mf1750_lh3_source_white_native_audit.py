from pathlib import Path
import json

AUDIT = Path(
    ".test-output/offline/LH3_SOURCE_WHITE_STRICT_NATIVE_20260918_R1/strict-native-audit.json"
)
MAIN = Path(".test-output/offline/LH3_SOURCE_WHITE_20260918_R1/generated/main.cpp")


def test_lh3_source_white_strict_native_audit_sealed():
    d = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert d["kind"] == "mf1750-lh3-source-white-strict-native-v1"
    assert d["result"] == "PASS"
    assert d["hardware_accessed"] is False
    assert d["network_accessed"] is False
    assert d["visible_refreshes"] == 0
    assert d["qualified_count"] == 0
    assert d["live_authorization_granted"] is False
    assert d["scenario_count"] == 36
    assert d["scenario_count"] == len(d["cases"])
    assert d["failed_scenarios"] == []


def test_lh3_generated_source_gate():
    s = MAIN.read_text(encoding="utf-8")
    assert s.count("bool lh2DriveMapTerminalComplete()") == 1
    assert s.count("lh2DriveMapTerminalComplete()") >= 4
    assert 'source.getUShort("cur_lh2m",0)==4' in s
    assert "0xac92bb9e25c374efULL" in s
    assert 'oldFault.getUShort("cur_lh1",0)==770' in s
    assert 'rebound.getUShort("cur_lh1r",0)==4' in s
    assert 'white.getUShort("used_lh2sw1",0)==2' in s
