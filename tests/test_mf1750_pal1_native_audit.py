"""Sealed PAL1 native audit assertions; fully offline."""

import json
from pathlib import Path

AUDIT = Path(".test-output/offline/PAL1_CAL_NATIVE_20260925_R2/strict-native-audit.json")
SUPERSEDED = Path(".test-output/offline/PAL1_CAL_NATIVE_20260925_R1/strict-native-audit.json")
REPRO = Path(".test-output/offline/PAL1_FIXTURE_DEFECT_REPRO_20260924_R1/fixture-defect-repro.json")


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_pal1_native_audit_sealed_pass():
    d = _audit()
    assert d["result"] == "PASS"
    assert d["hardware_accessed"] is False
    assert d["network_accessed"] is False
    assert d["visible_refreshes"] == 0
    assert d["qualified_count"] == 0
    assert d["live_ready"] is False
    assert d["live_authorization_granted"] is False
    assert d["synthetic_source_white"] is False  # R2 audits the real sealed V5 package
    assert d["white_anchor_sha256"] == "5dd81034bd9a963d89b91fc4ce9e7a01d8eaf4f99fc883e8ce0a3bc8f77dc9b0"
    assert d["failed_scenarios"] == []
    assert d["defects"] == []
    assert d["scenario_count"] == len(d["cases"])
    assert all(c["result"] == "PASS" for c in d["cases"].values())
    assert d["generated_sources_unmodified_during_audit"] is True
    assert all(c["result"] == "PASS" for c in d["static_assertions"])


def test_pal1_driver_gate_probe_and_single_action_facts():
    d = _audit()
    probe = d["driver_frame_gate_probe"]
    assert probe["result"] == "PASS"
    assert probe["facts"]["layout_valid"] == "1"
    assert probe["facts"]["driver_build_role1"] == "1"
    assert probe["facts"]["role_valid_2"] == "0"  # phRoleValid admits only Source
    assert probe["facts"]["fixture_self_check_equivalent"] == "1"
    assert probe["facts"]["fixture_role_1_index"] == "1"
    resolved = {r["id"]: r for r in d["resolved_defects"]}
    assert resolved["PAL1-R1-D1"]["status"] == "FIXED_IN_V2_PACK_BEFORE_THIS_AUDIT_SEALED"
    assert "MISSED" in resolved["PAL1-R1-D1"]["summary"]  # the R1 audit's blind spot is on record
    chain = d["cases"]["chain"]
    assert [doc["label"] for doc in chain["documents"]] == [
        "action_report", "terminal_status", "post_complete_arm_rejected"]
    report = chain["documents"][0]["json"]
    assert report["global_header"] == "active"
    assert report["controller_tuple_dispatch"] == "AA"
    assert report["campaign_complete"] is True
    assert report["next_ordinal"] == 2
    terminal = chain["documents"][1]["json"]
    assert terminal["cursor_raw"] == 2
    assert terminal["campaign_complete"] is True
    assert d["nvs_contract_observed"]["terminal_cursor_raw"] == 2


def test_pal1_native_frame_byte_exact():
    d = _audit()
    (frame,) = d["frames"]
    assert frame["stage"] == "PAL1"
    assert frame["byte_for_byte_match_python"] is True
    assert frame["byte_for_byte_match_package_frame4bpp"] is True
    assert frame["histogram"] == [33280] * 7 + [381440]


def test_pal1_source_gate_rejection_scenarios():
    d = _audit()
    for name in ("missing_white", "old_fault_missing", "old_fault_changed",
                 "old_fault_boot_changed", "rebound_missing", "rebound_changed",
                 "lh2_map_missing", "lh2_map_changed", "lh2_map_boot_changed",
                 "lh2_white_missing", "lh2_white_changed",
                 "lh3dose_v1_missing", "lh3dose_v1_changed",
                 "lh3dose_v2_missing", "lh3dose_v2_changed",
                 "lh3dose_v2_boot_changed",
                 "pal1_v1_boot_missing", "pal1_v1_cursor_written",
                 "pal1_v2_boot_missing", "pal1_v2_cursor_written",
                 "pal1_v3_boot_missing", "pal1_v3_cursor_written",
                 "pal1_v4_boot_missing", "pal1_v4_cursor_written",
                 "pal1_v2_cursor_767"):
        case = d["cases"][name]
        assert case["result"] == "PASS"
        doc = case["documents"][0]
        assert doc["status"] == 400
        assert doc["json"]["error"] == "source_white_not_complete"
        assert doc["json"]["accepted"] is False and doc["json"]["fault_locked"] is True
    gates = d["preserved_namespace_gates"]
    assert gates["lh3_dose_v1_bricked"]["cursor_raw"] == 769
    assert gates["lh3_dose_v2_terminal"] == {
        "namespace": "lh3dose_v2", "cursor": "cur_lh3d2", "boot": "boot_lh3d2",
        "cursor_raw": 4, "boot_nonce": "4d53de6fe4b39d3b",
        "campaign_complete": True}
    assert gates["pal1_v1_dead"]["cursor_key_may_be_absent"] is True
    assert gates["pal1_v2_dead"]["cause"].startswith("PAL1-R2-D2")
    assert gates["pal1_v3_dead"]["cause"].startswith("PAL1-R3-D3")
    assert gates["pal1_v2_dead"]["cursor_fault_769_accepted"] is True
    assert gates["pal1_v4_dead"]["boot_nonce_field_reported"] == "f434e324f1bca44f"


def test_pal1_audit_cross_checks_nvs_ground_truth():
    d = _audit()
    truth = d["nvs_ground_truth"]
    assert truth["all_match"] is True
    by_key = {c["key"]: c for c in truth["checks"]}
    assert by_key["pal1_v1/cur_pal1"]["present"] is False
    assert by_key["pal1_v2/cur_pal2"]["present"] is False
    assert by_key["pal1_v1/boot_pal1"]["present"] is True
    assert by_key["lh3dose_v2/cur_lh3d2"]["actual"] == 4
    resolved = {r["id"]: r for r in d["resolved_defects"]}
    assert resolved["PAL1-R2-D2"]["status"] == "FIXED_IN_V3_PACK_BEFORE_THIS_AUDIT_SEALED"
    assert resolved["PAL1-R2-D2"]["evidence"]["nvs_ground_truth_all_match"] is True


def test_pal1_gate_detail_bitmap_coverage():
    d = _audit()
    # Every read-only and chain document carries the full bitmap, all true.
    keys = {"old_fault", "rebound_v2", "lh2_map", "lh2_white", "lh3dose_v1",
            "lh3dose_v2", "pal1_v1", "pal1_v2", "pal1_v3", "pal1_v4", "lh3_white"}
    for doc in d["cases"]["read_only"]["documents"]:
        assert set(doc["json"]["gate_detail"]) == keys
        assert all(doc["json"]["gate_detail"].values())
    assert all(d["cases"]["chain"]["documents"][0]["json"]["gate_detail"].values())
    # The partial scenario pinpoints one false segment while serving READY.
    case = d["cases"]["gate_detail_partial"]
    assert case["result"] == "PASS"
    doc = case["documents"][0]["json"]
    assert doc["state"] == "ready"
    assert doc["gate_detail"]["lh2_map"] is False
    assert doc["source_nvs_complete"] is False
    assert sum(1 for v in doc["gate_detail"].values() if v) == 10
    # pal1_v2 fault cursor 769 accepted, 767 rejected
    ok = d["cases"]["pal1_v2_cursor_fault_accepted"]
    assert ok["result"] == "PASS"
    assert ok["documents"][0]["json"]["gate_detail"]["pal1_v2"] is True
    assert ok["documents"][0]["json"]["source_nvs_complete"] is True
    bad = d["cases"]["pal1_v2_cursor_767"]
    assert bad["result"] == "PASS"
    assert bad["documents"][0]["status"] == 400
    assert bad["documents"][0]["json"]["error"] == "source_white_not_complete"
    truth = d["nvs_ground_truth"]
    assert truth["all_match"] is True
    informational = [c for c in truth["checks"]
                     if c["mode"].startswith(("informational", "inferred"))]
    assert {c["key"] for c in informational} == {
        "pal1_v3/boot_pal3", "pal1_v3/cur_pal3",
        "pal1_v4/boot_pal4", "pal1_v4/cur_pal4", "pal1_v2/cur_pal2"}
    assert next(c for c in truth["checks"]
                if c["key"] == "pal1_v2/cur_pal2")["expected"] == 769
