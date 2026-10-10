"""Sealed LH2 drive-map native audit assertions; fully offline."""
from __future__ import annotations

import json
from pathlib import Path

AUDIT = Path(".test-output/offline/LH2_DRIVE_MAP_NATIVE_20260918_R3/strict-native-audit.json")
SUPERSEDED = Path(".test-output/offline/LH2_DRIVE_MAP_NATIVE_20260917_R1/strict-native-audit.json")


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_lh2_drive_map_native_audit_sealed_pass():
    d = _audit()
    assert d["result"] == "PASS"
    assert d["hardware_accessed"] is False
    assert d["network_accessed"] is False
    assert d["visible_refreshes"] == 0
    assert d["qualified_count"] == 0
    assert d["live_ready"] is False
    assert d["live_authorization_granted"] is False
    assert d["synthetic_source_white"] is False  # R3 audits the real sealed package
    assert d["white_anchor_sha256"] == "99078ff932313f89aa2af0b02fa38d25dee23e42fbcc7505dfc7c2edf0702a47"
    assert d["failed_scenarios"] == []
    assert d["defects"] == []
    assert d["scenario_count"] == len(d["cases"])
    assert all(c["result"] == "PASS" for c in d["cases"].values())
    assert d["generated_sources_unmodified_during_audit"] is True
    assert all(c["result"] == "PASS" for c in d["static_assertions"])


def test_lh2_drive_map_driver_gate_probe_and_resolved_defect():
    d = _audit()
    probe = d["driver_frame_gate_probe"]
    assert probe["result"] == "PASS"
    assert probe["facts"]["layout_valid"] == "1"
    assert probe["facts"]["driver_build_role3"] == "1"
    assert probe["facts"]["hpp_build_role3"] == "1"
    resolved = {r["id"]: r for r in d["resolved_defects"]}
    assert resolved["LH2-DM-D1"]["status"] == "FIXED_IN_PACK_BEFORE_THIS_AUDIT_SEALED"


def test_lh2_drive_map_native_frames_byte_exact():
    d = _audit()
    assert SUPERSEDED.is_file()  # R1 stays sealed as historical evidence
    frames = {f["stage"]: f for f in d["frames"]}
    assert set(frames) == {"SOURCE", "MIDDLE", "MAP"}
    for item in frames.values():
        assert item["byte_for_byte_match_python"] is True
        assert item["byte_for_byte_match_package_frame4bpp"] is True
    assert frames["MAP"]["histogram"] == [33280] * 7 + [381440]
    chain = d["cases"]["chain"]
    assert [doc["label"] for doc in chain["documents"]] == [
        "action_report", "action_report", "action_report",
        "terminal_status", "post_complete_arm_rejected"]
    terminal = chain["documents"][3]["json"]
    assert terminal["campaign_complete"] is True
    assert terminal["cursor_raw"] == 4
