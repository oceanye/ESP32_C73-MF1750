from pathlib import Path
import json

AUDIT = Path(
    ".test-output/offline/LH2_SOURCE_WHITE_STRICT_NATIVE_20260917_R1/strict-native-audit.json"
)
MAIN = Path(".test-output/offline/LH2_SOURCE_WHITE_20260917_R1/generated/main.cpp")


def test_lh2_source_white_strict_native_audit_sealed():
    d = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert d["kind"] == "mf1750-lh2-source-white-strict-native-v1"
    assert d["result"] == "PASS"
    assert d["hardware_accessed"] is False
    assert d["network_accessed"] is False
    assert d["visible_refreshes"] == 0
    assert d["qualified_count"] == 0
    assert d["live_authorization_granted"] is False
    assert d["scenario_count"] == 32
    assert d["scenario_count"] == len(d["cases"])
    assert d["failed_scenarios"] == []


def test_lh2_generated_source_gate():
    s = MAIN.read_text(encoding="utf-8")
    assert s.count("bool reboundV2TerminalComplete()") == 1
    assert s.count("reboundV2TerminalComplete()") >= 4
    assert 'source.getUShort("cur_lh1r",0)==4' in s
    assert "0x7274e005c8833ca1ULL" in s
    assert 'oldFault.getUShort("cur_lh1",0)==770' in s
