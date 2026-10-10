"""Sealed LH3 dose native audit assertions; fully offline."""

import json
from pathlib import Path

AUDIT = Path(".test-output/offline/LH3_DOSE_NATIVE_20260924_R3/strict-native-audit.json")
SUPERSEDED = Path(".test-output/offline/LH3_DOSE_NATIVE_20260921_R2/strict-native-audit.json")


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_lh3_dose_native_audit_sealed_pass():
    d = _audit()
    assert d["result"] == "PASS"
    assert d["hardware_accessed"] is False
    assert d["network_accessed"] is False
    assert d["visible_refreshes"] == 0
    assert d["qualified_count"] == 0
    assert d["live_ready"] is False
    assert d["live_authorization_granted"] is False
    assert d["synthetic_source_white"] is False  # R3 audits the real sealed V2 package
    assert d["white_anchor_sha256"] == "5dd81034bd9a963d89b91fc4ce9e7a01d8eaf4f99fc883e8ce0a3bc8f77dc9b0"
    assert d["failed_scenarios"] == []
    assert d["defects"] == []
    assert d["scenario_count"] == len(d["cases"])
    assert all(c["result"] == "PASS" for c in d["cases"].values())
    assert d["generated_sources_unmodified_during_audit"] is True
    assert all(c["result"] == "PASS" for c in d["static_assertions"])


def test_lh3_dose_driver_gate_probe_and_prevented_defect():
    d = _audit()
    probe = d["driver_frame_gate_probe"]
    assert probe["result"] == "PASS"
    assert probe["facts"]["layout_valid"] == "1"
    assert probe["facts"]["driver_build_role3"] == "1"
    assert probe["facts"]["hpp_build_role3"] == "1"
    resolved = {r["id"]: r for r in d["resolved_defects"]}
    assert resolved["LH3-DOSE-D1"]["status"] == "PREVENTED_IN_PACK_BEFORE_THIS_AUDIT_SEALED"


def test_lh3_dose_native_frames_byte_exact_and_dose2_equals_dose1():
    d = _audit()
    assert SUPERSEDED.is_file()  # R2 (V1 package) audit stays sealed as historical evidence
    assert d["dose2_frame_byte_identical_to_dose1"] is True
    frames = {f["stage"]: f for f in d["frames"]}
    assert set(frames) == {"SOURCE", "DOSE1", "DOSE2"}
    for item in frames.values():
        assert item["byte_for_byte_match_python"] is True
        assert item["byte_for_byte_match_package_frame4bpp"] is True
    assert frames["DOSE1"]["sha256"] == frames["DOSE2"]["sha256"]
    assert frames["DOSE1"]["histogram"] == [33280] * 7 + [381440]
    chain = d["cases"]["chain"]
    assert [doc["label"] for doc in chain["documents"]] == [
        "action_report", "action_report", "action_report",
        "terminal_status", "post_complete_arm_rejected"]
    terminal = chain["documents"][3]["json"]
    assert terminal["campaign_complete"] is True
    assert terminal["cursor_raw"] == 4
    reports = [doc["json"] for doc in chain["documents"][:3]]
    assert [r["global_header"] for r in reports] == ["active", "commented", "commented"]
    assert [r["controller_tuple_dispatch"] for r in reports] == ["AA", "CC", "CC"]
    assert reports[1]["driver"]["input_fnv1a"] == reports[2]["driver"]["input_fnv1a"]


def test_lh3_dose_source_gate_rejection_scenarios():
    d = _audit()
    for name in ("missing_white", "old_fault_missing", "old_fault_changed",
                 "old_fault_boot_changed", "rebound_missing", "rebound_changed",
                 "lh2_map_missing", "lh2_map_changed", "lh2_map_boot_changed",
                 "lh2_white_missing", "lh2_white_changed",
                 "lh3dose_v1_missing", "lh3dose_v1_changed"):
        case = d["cases"][name]
        assert case["result"] == "PASS"
        doc = case["documents"][0]
        assert doc["status"] == 400
        assert doc["json"]["error"] == "source_white_not_complete"
        assert doc["json"]["accepted"] is False and doc["json"]["fault_locked"] is True
    gates = d["preserved_namespace_gates"]
    assert gates["lh2_map_terminal"]["cursor_raw"] == 4
    assert gates["lh2_map_terminal"]["boot_nonce"] == "ac92bb9e25c374ef"
    assert gates["lh2_white_marker"]["cursor_raw"] == 2
    assert gates["lh3_white_consumed_marker"] == {
        "namespace": "lh3srcw_v1", "key": "used_lh3sw1", "cursor_raw": 2}
    assert gates["lh3_dose_v1_bricked"] == {
        "namespace": "lh3dose_v1", "cursor": "cur_lh3d", "cursor_raw": 769,
        "phase": "FAULT", "ordinal": 1, "driver_call_count_at_brick": 0,
        "recoverable": False}
