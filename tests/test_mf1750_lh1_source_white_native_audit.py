from pathlib import Path
import json


def test_lh1_source_white_native_audit_sealed():
    p = Path(
        ".test-output/offline/LH1_SOURCE_WHITE_NATIVE_20260912_R1/native-audit.json"
    )
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["hardware_accessed"] is False
    assert d["protocol_findings"]["arm_execute_dispatch_nvs_guard"] is True
    assert d["protocol_findings"]["source_terminal_middleware_rejection"] is False
    assert d["live_ready"] if "live_ready" in d else True
    assert d["qualified_count"] == 0


def test_lh1_generated_source_guards():
    p = Path(".test-output/offline/LH1_SOURCE_WHITE_20260912_R1/generated/main.cpp")
    s = p.read_text(encoding="utf-8")
    assert s.count("bool sourceOrdinalOneComplete()") == 1
    assert s.count("sourceOrdinalOneComplete()") >= 4
    assert 'source.getUShort("cur_lh1",0)==2' in s
    assert 'source.getULong64("boot_lh1",0)!=0' in s
