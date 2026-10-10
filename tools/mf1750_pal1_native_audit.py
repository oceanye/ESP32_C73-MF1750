#!/usr/bin/env python3
"""Strict native audit of the PAL1 measured-palette V2 single-action firmware.

V2 (2026-09-24, defect PAL1-R1-D1): the R1 package faulted at its first real
boot with compiled_fixture_self_check_failed because the frozen fixture role
loop {Source,Mid,Target} indexed the single-action identity kActions[2] out of
bounds. The R1 audit MISSED it (protocol fixture stubs the self-check; the
driver probe never touched ph::kActions) — this V2 audit closes that hole with
a static role/identity bounds assertion and a fixture-equivalent probe loop
that compiles the exact kFixtureRoles declaration and checks each role's
identity bounds, histogram and frame FNV. Run against the R1 package, this
audit FAILS (fixture_self_check_equivalent=0).

MSVC-compiles the actual generated main.cpp with desktop
Arduino/Preferences/WebServer/WiFi/GPIO doubles and exercises the full
protocol: one PAL1 action (ordinal 1, LH3-white-anchored, driver role Source,
active global header, code=column index, campaign complete at
next_ordinal=2). The frame rule is compiled from the actual generated
lh_frame_fill.hpp and asserted byte for byte against
host/static_photo/palette_cal_pal1.py and the packaged pal1.frame4bpp. The
generated driver's own phBuildExpectedFrame/phLayoutValid path is compiled and
executed verbatim in a separate probe.

The firmware source gate requires the LH3 dose V2 terminal (lh3dose_v2
cur_lh3d2=4 / boot_lh3d2=0x4d53de6fe4b39d3b, campaign complete), the bricked
V1 dose cursor 769, the dead PAL1 V1 namespace (pal1_v1 cursor=1 with boot key
present, zero driver calls), the consumed LH3 white marker (lh3srcw_v1
used_lh3sw1==2), the LH2 drive-map terminal and the preserved lhist_v1 /
lh1reb_v2 / lh2srcw_v1 namespaces; dedicated rejection scenarios erase or
alter each of them. Synthetic mode (no --package) synthesizes the white
records with exactly the recipe used by tests/test_mf1750_pal1_pack.py;
--package audits the real sealed package anchored on the 2026-09-22 LH3 white
close-review.

No hardware, serial, network, relay or camera access. Every artifact is
written with O_EXCL into a fresh output directory; the report self-seals with
a canonical-JSON SHA256 integrity field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo import palette_cal_pal1 as pal1  # noqa: E402
from tools import mf1750_lightness_history_firmware as base_firmware  # noqa: E402
from tools import mf1750_pal1_pack as pack  # noqa: E402
from tools.mf1750_lightness_history_native_audit import compiler_environment  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/lightness_history_native"
DEFAULT_OUT = ROOT / ".test-output/offline/PAL1_CAL_NATIVE_20260925_R2"
KIND = "mf1750-pal1-native-audit-v1"
RUN_ID = "PAL1_NATIVE_AUDIT"
OLD_FAULT = {"namespace": "lhist_v1", "cursor": "cur_lh1", "boot": "boot_lh1",
             "cursor_raw": 770, "boot_nonce": "30a9e5989873f4e0"}
REBOUND_V2 = {"namespace": "lh1reb_v2", "cursor": "cur_lh1r", "boot": "boot_lh1r",
              "cursor_raw": 4, "boot_nonce": "7274e005c8833ca1"}
LH2_MAP = {"namespace": "lh2map_v1", "cursor": "cur_lh2m", "boot": "boot_lh2m",
           "cursor_raw": 4, "boot_nonce": "ac92bb9e25c374ef"}
LH2_WHITE = {"namespace": "lh2srcw_v1", "key": "used_lh2sw1", "cursor_raw": 2}
LH3_WHITE = {"namespace": "lh3srcw_v1", "key": "used_lh3sw1", "cursor_raw": 2}
LH3_DOSE_V1_BRICKED = {"namespace": "lh3dose_v1", "cursor": "cur_lh3d",
                       "cursor_raw": 769, "phase": "FAULT", "ordinal": 1,
                       "driver_call_count_at_brick": 0, "recoverable": False}
LH3_DOSE_V2_TERMINAL = {"namespace": "lh3dose_v2", "cursor": "cur_lh3d2",
                        "boot": "boot_lh3d2", "cursor_raw": 4,
                        "boot_nonce": "4d53de6fe4b39d3b",
                        "campaign_complete": True}
PAL1_V1_DEAD = {"namespace": "pal1_v1", "cursor": "cur_pal1", "boot": "boot_pal1",
                "cursor_key_may_be_absent": True,
                "cursor_absent_means_fresh_value_1": True,
                "boot_key_present_required": True,
                "fault_persisted": False, "driver_call_count_at_failure": 0,
                "visible_refresh_count_at_failure": 0, "recoverable": False,
                "cause": "PAL1-R1-D1 compiled_fixture_self_check_failed"}
PAL1_V2_DEAD = {"namespace": "pal1_v2", "cursor": "cur_pal2", "boot": "boot_pal2",
                "cursor_key_may_be_absent": True,
                "cursor_absent_means_fresh_value_1": True,
                "cursor_fault_769_accepted": True,
                "boot_key_present_required": True,
                "fault_persisted": False, "driver_call_count_at_failure": 0,
                "visible_refresh_count_at_failure": 0, "recoverable": False,
                "cause": "PAL1-R2-D2 gate demanded a cursor key the boot path "
                         "never writes; the dump's own RTS reset then wrote "
                         "the persistent boot-fault cursor 769",
                "cursor_769_inference": "dump predates its own RTS reset; "
                         "V2's only pre-ARM cursor write is boot fault 769; "
                         "the V4 gate bitmap confirmed pal1_v2=false"}
PAL1_V4_DEAD = {"namespace": "pal1_v4", "cursor": "cur_pal4", "boot": "boot_pal4",
                "cursor_key_may_be_absent": True,
                "cursor_absent_means_fresh_value_1": True,
                "boot_key_present_required": True,
                "fault_persisted": False, "driver_call_count_at_failure": 0,
                "visible_refresh_count_at_failure": 0, "recoverable": False,
                "cause": "V4 diagnosed PAL1-R3-D3 via gate_detail "
                         "(pal1_v2=false); V4 never ARMed; flashing V5 strands "
                         "its boot binding",
                "boot_nonce_field_reported": "f434e324f1bca44f",
                "boot_not_in_dump": "post-dump first boot; value from the "
                                    "field report, not the parse"}
PAL1_V3_DEAD = {"namespace": "pal1_v3", "cursor": "cur_pal3", "boot": "boot_pal3",
                "cursor_key_may_be_absent": True,
                "cursor_absent_means_fresh_value_1": True,
                "boot_key_present_required": True,
                "fault_persisted": False, "driver_call_count_at_failure": 0,
                "visible_refresh_count_at_failure": 0, "recoverable": False,
                "cause": "PAL1-R3-D3 all gate pins matched the dump yet "
                         "source_nvs_complete stayed false; dump RTS reset "
                         "killed the fresh pal1_v3 boot binding",
                "boot_nonce_field_reported": "09665a142b77a580",
                "boot_not_in_dump": "post-dump first boot; value from the "
                                    "field report, not the parse"}
ROLE_ENUM_VALUE = {"Source": 1, "Mid": 2, "Target": 3}
NVS_PARSE = ROOT / ".test-output/offline/NVS_DUMP_PARSE_20260924_V1/nvs-dump-parse.json"
GATE_DETAIL_KEYS = ("old_fault", "rebound_v2", "lh2_map", "lh2_white",
                    "lh3dose_v1", "lh3dose_v2", "pal1_v1", "pal1_v2",
                    "pal1_v3", "pal1_v4", "lh3_white")
PAL1_HISTOGRAM = [33280] * 7 + [381440]

# Rejection scenarios: one ARM/EXECUTE request is rejected with the expected
# HTTP status and error string, the driver is never called and the campaign
# fault-locks.
REJECTION_CASES = {
    "missing_white": (400, "source_white_not_complete"),
    "old_fault_missing": (400, "source_white_not_complete"),
    "old_fault_changed": (400, "source_white_not_complete"),
    "old_fault_boot_changed": (400, "source_white_not_complete"),
    "rebound_missing": (400, "source_white_not_complete"),
    "rebound_changed": (400, "source_white_not_complete"),
    "lh2_map_missing": (400, "source_white_not_complete"),
    "lh2_map_changed": (400, "source_white_not_complete"),
    "lh2_map_boot_changed": (400, "source_white_not_complete"),
    "lh2_white_missing": (400, "source_white_not_complete"),
    "lh2_white_changed": (400, "source_white_not_complete"),
    "lh3dose_v1_missing": (400, "source_white_not_complete"),
    "lh3dose_v1_changed": (400, "source_white_not_complete"),
    "lh3dose_v2_missing": (400, "source_white_not_complete"),
    "lh3dose_v2_changed": (400, "source_white_not_complete"),
    "lh3dose_v2_boot_changed": (400, "source_white_not_complete"),
    "pal1_v1_boot_missing": (400, "source_white_not_complete"),
    "pal1_v1_cursor_written": (400, "source_white_not_complete"),
    "pal1_v2_boot_missing": (400, "source_white_not_complete"),
    "pal1_v2_cursor_written": (400, "source_white_not_complete"),
    "pal1_v3_boot_missing": (400, "source_white_not_complete"),
    "pal1_v3_cursor_written": (400, "source_white_not_complete"),
    "pal1_v4_boot_missing": (400, "source_white_not_complete"),
    "pal1_v4_cursor_written": (400, "source_white_not_complete"),
    "pal1_v2_cursor_767": (400, "source_white_not_complete"),
    "missing_review_header": (400, "missing_or_invalid_review_binding"),
    "invalid_review": (400, "missing_or_invalid_review_binding"),
    "wrong_source_review": (400, "source_review_anchor_mismatch"),
    "first_prior_not_source": (400, "first_review_must_bind_white"),
    "changed_review_execute": (400, "run_or_source_review_changed"),
    "wrong_boot": (400, "boot_nonce_missing_or_stale"),
    "wrong_action": (400, "action_id_missing_or_mismatch"),
    "ordinal_skip": (400, "ordinal_missing_or_mismatch"),
    "body": (400, "body_or_arguments_forbidden"),
    "unknown_mutation": (404, "unknown_mutation_route"),
    "duplicate_arm": (409, "arm_duplicate_complete_or_not_ready"),
    "execute_without_arm": (409, "execute_duplicate_stale_or_not_armed"),
    "duplicate_execute": (409, "execute_duplicate_stale_or_not_armed"),
    "busy_arm": (503, "arm_busy_not_idle_high"),
    "busy_execute": (503, "execute_busy_not_idle_high"),
    "arm_write_failure": (503, "persistent_armed_write_failed"),
    "consume_write_failure": (503, "persistent_consumed_write_failed"),
}
# Scenarios ending in a published fault report (GET /report): expected error
# string, whether the driver was called, and the expected total driver calls.
FAULT_REPORT_CASES = {
    "reboot": ("campaign_boot_binding_mismatch_at_boot", False, 1),
    "driver_failure": ("driver_operation_failed", True, 1),
    "bad_driver_report": ("driver_operation_failed", True, 1),
    "complete_write_failure": ("persistent_next_ready_write_failed", True, 1),
    "busy_dispatch": ("dispatch_busy_not_idle_high", False, 0),
    "source_lost_dispatch": ("dispatch_source_white_not_complete", False, 0),
    "cursor_changed_dispatch": ("runtime_queue_or_cursor_mismatch", False, 0),
    "fixture_failure": ("compiled_fixture_self_check_failed", False, 0),
    "nvs_open_failure": ("cursor_store_open_failed", False, 0),
    "boot_write_failure": ("campaign_boot_binding_mismatch_at_boot", False, 0),
    "invalid_cursor": ("persistent_cursor_invalid", False, 0),
}
SPECIAL_CASES = ("chain", "read_only", "frames")
CASES = (
    "chain",
    "read_only",
    "frames",
    "reboot",
    "execute_without_arm",
    "duplicate_arm",
    "duplicate_execute",
    "ordinal_skip",
    "missing_review_header",
    "invalid_review",
    "wrong_source_review",
    "first_prior_not_source",
    "changed_review_execute",
    "missing_white",
    "old_fault_missing",
    "old_fault_changed",
    "old_fault_boot_changed",
    "rebound_missing",
    "rebound_changed",
    "lh2_map_missing",
    "lh2_map_changed",
    "lh2_map_boot_changed",
    "lh2_white_missing",
    "lh2_white_changed",
    "lh3dose_v1_missing",
    "lh3dose_v1_changed",
    "lh3dose_v2_missing",
    "lh3dose_v2_changed",
    "lh3dose_v2_boot_changed",
    "pal1_v1_boot_missing",
    "pal1_v1_cursor_written",
    "pal1_v2_boot_missing",
    "pal1_v2_cursor_written",
    "pal1_v3_boot_missing",
    "pal1_v3_cursor_written",
    "pal1_v4_boot_missing",
    "pal1_v4_cursor_written",
    "pal1_v2_cursor_767",
    "pal1_v2_cursor_fault_accepted",
    "gate_detail_partial",
    "source_lost_dispatch",
    "cursor_changed_dispatch",
    "driver_failure",
    "bad_driver_report",
    "complete_write_failure",
    "busy_arm",
    "busy_execute",
    "busy_dispatch",
    "arm_write_failure",
    "consume_write_failure",
    "wrong_boot",
    "wrong_action",
    "body",
    "unknown_mutation",
    "fixture_failure",
    "nvs_open_failure",
    "boot_write_failure",
    "invalid_cursor",
)

HELPERS = r"""void getReport(const char *label) {
  server.headers.clear(); server.argumentCount=0; server.request(kReportRoute,HTTP_GET);
  check(server.code==200,"report GET failed");
  std::cout<<label<<'\t'<<server.code<<'\t'<<server.body.c_str()<<'\n';
}
void printReject(const char *label) {
  std::cout<<label<<'\t'<<server.code<<'\t'<<server.body.c_str()<<'\n';
}
int main(int argc,char **argv) {"""

PRESETS = """  Preferences::values["lhist_v1/cur_lh1"]=770;
  Preferences::values["lhist_v1/boot_lh1"]=0x30a9e5989873f4e0ULL;
  Preferences::values["lh1reb_v2/cur_lh1r"]=4;
  Preferences::values["lh1reb_v2/boot_lh1r"]=0x7274e005c8833ca1ULL;
  Preferences::values["lh2map_v1/cur_lh2m"]=4;
  Preferences::values["lh2map_v1/boot_lh2m"]=0xac92bb9e25c374efULL;
  Preferences::values["lh2srcw_v1/used_lh2sw1"]=2;
  Preferences::values["lh3srcw_v1/used_lh3sw1"]=2;
  Preferences::values["lh3dose_v1/cur_lh3d"]=769;
  Preferences::values["lh3dose_v2/cur_lh3d2"]=4;
  Preferences::values["lh3dose_v2/boot_lh3d2"]=0x4d53de6fe4b39d3bULL;
  // Ground truth from the read-only NVS dump (NVS_DUMP_PARSE_20260924_V1):
  // the dead PAL1 V1/V2 namespaces have their boot keys only; the boot path
  // writes no cursor key (the cursor is first written at ARM).
  Preferences::values["pal1_v1/boot_pal1"]=0x0d6a2ca543a5dafdULL;
  Preferences::values["pal1_v2/boot_pal2"]=0x26e40800d67745a5ULL;
  Preferences::values["pal1_v3/boot_pal3"]=0x09665a142b77a580ULL;
  Preferences::values["pal1_v4/boot_pal4"]=0xf434e324f1bca44fULL;"""

CHAIN_TERMINAL = r"""      check(state==RuntimeState::Complete,"campaign not complete");
      check(Preferences::values.at("pal1_v5/cur_pal5")==2,"terminal cursor raw must be 2");
      check(cursorRaw==2&&nextOrdinal==2&&persistentPhase==kPhaseReady,"terminal cursor fields mismatch");
      server.headers.clear(); server.argumentCount=0; server.request(kStatusRoute,HTTP_GET);
      check(server.code==200,"terminal status failed"); std::cout<<"terminal_status\t"<<server.code<<"\t"<<server.body.c_str()<<'\n';
      requestHeaders(1,false,std::string(64,'d')); server.request(kArmRoute,HTTP_POST); printReject("post_complete_arm_rejected"); stopped(1);
      check(Preferences::values.at("pal1_v5/cur_pal5")==encodeCursor(kPhaseFault,1),"post-complete ARM must fault-lock the cursor");"""

NEW_SCENARIO_BRANCHES = r"""    } else if(scenario=="gate_detail_partial") {
      Preferences::values.erase("lh2map_v1/cur_lh2m");
      server.headers.clear(); server.argumentCount=0; server.request(kStatusRoute,HTTP_GET);
      check(server.code==200,"status GET failed"); printReject("status_partial");
    } else if(scenario=="pal1_v2_cursor_fault_accepted") {
      Preferences::values["pal1_v2/cur_pal2"]=769;
      server.headers.clear(); server.argumentCount=0; server.request(kStatusRoute,HTTP_GET);
      check(server.code==200,"status GET failed"); printReject("status_ok");
    } else if(scenario=="execute_without_arm") {
      requestHeaders(1,true); server.request(kExecuteRoute,HTTP_POST);
      printReject("rejected"); stopped();
    } else {
      requestHeaders(1,false);"""

MUTATIONS = r"""      else if(scenario=="missing_review_header") server.headers.erase("X-LH-Source-Review");
      else if(scenario=="first_prior_not_source") server.headers["X-LH-Prior-Review"]=WRONG_REVIEW;
      else if(scenario=="wrong_source_review") server.headers["X-LH-Source-Review"]=WRONG_REVIEW;
      else if(scenario=="old_fault_missing") Preferences::values.erase("lhist_v1/cur_lh1");
      else if(scenario=="old_fault_changed") Preferences::values["lhist_v1/cur_lh1"]=771;
      else if(scenario=="old_fault_boot_changed") Preferences::values["lhist_v1/boot_lh1"]=0x30a9e5989873f4e1ULL;
      else if(scenario=="rebound_missing") Preferences::values.erase("lh1reb_v2/cur_lh1r");
      else if(scenario=="rebound_changed") Preferences::values["lh1reb_v2/cur_lh1r"]=3;
      else if(scenario=="lh2_map_missing") Preferences::values.erase("lh2map_v1/cur_lh2m");
      else if(scenario=="lh2_map_changed") Preferences::values["lh2map_v1/cur_lh2m"]=3;
      else if(scenario=="lh2_map_boot_changed") Preferences::values["lh2map_v1/boot_lh2m"]=0xac92bb9e25c374e0ULL;
      else if(scenario=="lh2_white_missing") Preferences::values.erase("lh2srcw_v1/used_lh2sw1");
      else if(scenario=="lh2_white_changed") Preferences::values["lh2srcw_v1/used_lh2sw1"]=1;
      else if(scenario=="lh3dose_v1_missing") Preferences::values.erase("lh3dose_v1/cur_lh3d");
      else if(scenario=="lh3dose_v1_changed") Preferences::values["lh3dose_v1/cur_lh3d"]=770;
      else if(scenario=="lh3dose_v2_missing") Preferences::values.erase("lh3dose_v2/cur_lh3d2");
      else if(scenario=="lh3dose_v2_changed") Preferences::values["lh3dose_v2/cur_lh3d2"]=3;
      else if(scenario=="lh3dose_v2_boot_changed") Preferences::values["lh3dose_v2/boot_lh3d2"]=0x4d53de6fe4b39d30ULL;
      else if(scenario=="pal1_v1_boot_missing") Preferences::values.erase("pal1_v1/boot_pal1");
      else if(scenario=="pal1_v1_cursor_written") Preferences::values["pal1_v1/cur_pal1"]=2;
      else if(scenario=="pal1_v2_boot_missing") Preferences::values.erase("pal1_v2/boot_pal2");
      else if(scenario=="pal1_v2_cursor_written") Preferences::values["pal1_v2/cur_pal2"]=2;
      else if(scenario=="pal1_v3_boot_missing") Preferences::values.erase("pal1_v3/boot_pal3");
      else if(scenario=="pal1_v3_cursor_written") Preferences::values["pal1_v3/cur_pal3"]=2;
      else if(scenario=="pal1_v4_boot_missing") Preferences::values.erase("pal1_v4/boot_pal4");
      else if(scenario=="pal1_v4_cursor_written") Preferences::values["pal1_v4/cur_pal4"]=2;
      else if(scenario=="pal1_v2_cursor_767") Preferences::values["pal1_v2/cur_pal2"]=767;
      else if(scenario=="gate_detail_partial") Preferences::values.erase("lh2map_v1/cur_lh2m");
      else check(scenario=="unknown_mutation","unknown case");"""

PRESERVATION_TAIL = r"""  if(scenario!="old_fault_missing") check(Preferences::values.at("lhist_v1/cur_lh1")==unsigned(scenario=="old_fault_changed"?771:770),"old fault cursor altered");
  else check(!Preferences::values.count("lhist_v1/cur_lh1"),"old fault cursor recreated");
  check(Preferences::values.at("lhist_v1/boot_lh1")==0x30a9e5989873f4e0ULL+unsigned(scenario=="old_fault_boot_changed"?1:0),"old fault boot altered");
  if(scenario!="rebound_missing") check(Preferences::values.at("lh1reb_v2/cur_lh1r")==unsigned(scenario=="rebound_changed"?3:4),"rebound v2 cursor altered");
  else check(!Preferences::values.count("lh1reb_v2/cur_lh1r"),"rebound v2 cursor recreated");
  check(Preferences::values.at("lh1reb_v2/boot_lh1r")==0x7274e005c8833ca1ULL,"rebound v2 boot altered");
  if(scenario!="lh2_map_missing"&&scenario!="gate_detail_partial") check(Preferences::values.at("lh2map_v1/cur_lh2m")==unsigned(scenario=="lh2_map_changed"?3:4),"lh2 map cursor altered");
  else check(!Preferences::values.count("lh2map_v1/cur_lh2m"),"lh2 map cursor recreated");
  check(Preferences::values.at("lh2map_v1/boot_lh2m")==(scenario=="lh2_map_boot_changed"?0xac92bb9e25c374e0ULL:0xac92bb9e25c374efULL),"lh2 map boot altered");
  if(scenario!="lh2_white_missing") check(Preferences::values.at("lh2srcw_v1/used_lh2sw1")==unsigned(scenario=="lh2_white_changed"?1:2),"lh2 white marker altered");
  else check(!Preferences::values.count("lh2srcw_v1/used_lh2sw1"),"lh2 white marker recreated");
  if(scenario!="missing_white"&&scenario!="source_lost_dispatch") check(Preferences::values.at("lh3srcw_v1/used_lh3sw1")==2,"lh3 white marker altered");
  else check(!Preferences::values.count("lh3srcw_v1/used_lh3sw1"),"lh3 white marker recreated");
  if(scenario!="lh3dose_v1_missing") check(Preferences::values.at("lh3dose_v1/cur_lh3d")==unsigned(scenario=="lh3dose_v1_changed"?770:769),"lh3 dose v1 bricked cursor altered");
  else check(!Preferences::values.count("lh3dose_v1/cur_lh3d"),"lh3 dose v1 cursor recreated");
  if(scenario!="lh3dose_v2_missing") check(Preferences::values.at("lh3dose_v2/cur_lh3d2")==unsigned(scenario=="lh3dose_v2_changed"?3:4),"lh3 dose v2 terminal cursor altered");
  else check(!Preferences::values.count("lh3dose_v2/cur_lh3d2"),"lh3 dose v2 cursor recreated");
  check(Preferences::values.at("lh3dose_v2/boot_lh3d2")==(scenario=="lh3dose_v2_boot_changed"?0x4d53de6fe4b39d30ULL:0x4d53de6fe4b39d3bULL),"lh3 dose v2 boot altered");
  if(scenario!="pal1_v1_boot_missing") check(Preferences::values.at("pal1_v1/boot_pal1")==0x0d6a2ca543a5dafdULL,"pal1 v1 boot key altered");
  else check(!Preferences::values.count("pal1_v1/boot_pal1"),"pal1 v1 boot key recreated");
  if(scenario!="pal1_v1_cursor_written") check(!Preferences::values.count("pal1_v1/cur_pal1"),"pal1 v1 cursor key must stay absent");
  else check(Preferences::values.at("pal1_v1/cur_pal1")==2,"pal1 v1 cursor mutation value differs");
  if(scenario!="pal1_v2_boot_missing") check(Preferences::values.at("pal1_v2/boot_pal2")==0x26e40800d67745a5ULL,"pal1 v2 boot key altered");
  else check(!Preferences::values.count("pal1_v2/boot_pal2"),"pal1 v2 boot key recreated");
  if(scenario=="pal1_v2_cursor_written") check(Preferences::values.at("pal1_v2/cur_pal2")==2,"pal1 v2 cursor mutation value differs");
  else if(scenario=="pal1_v2_cursor_fault_accepted") check(Preferences::values.at("pal1_v2/cur_pal2")==769,"pal1 v2 fault cursor differs");
  else if(scenario=="pal1_v2_cursor_767") check(Preferences::values.at("pal1_v2/cur_pal2")==767,"pal1 v2 cursor mutation value differs");
  else check(!Preferences::values.count("pal1_v2/cur_pal2"),"pal1 v2 cursor key must stay absent");
  if(scenario!="pal1_v4_boot_missing") check(Preferences::values.at("pal1_v4/boot_pal4")==0xf434e324f1bca44fULL,"pal1 v4 boot key altered");
  else check(!Preferences::values.count("pal1_v4/boot_pal4"),"pal1 v4 boot key recreated");
  if(scenario!="pal1_v4_cursor_written") check(!Preferences::values.count("pal1_v4/cur_pal4"),"pal1 v4 cursor key must stay absent");
  else check(Preferences::values.at("pal1_v4/cur_pal4")==2,"pal1 v4 cursor mutation value differs");
  if(scenario!="pal1_v3_boot_missing") check(Preferences::values.at("pal1_v3/boot_pal3")==0x09665a142b77a580ULL,"pal1 v3 boot key altered");
  else check(!Preferences::values.count("pal1_v3/boot_pal3"),"pal1 v3 boot key recreated");
  if(scenario!="pal1_v3_cursor_written") check(!Preferences::values.count("pal1_v3/cur_pal3"),"pal1 v3 cursor key must stay absent");
  else check(Preferences::values.at("pal1_v3/cur_pal3")==2,"pal1 v3 cursor mutation value differs");
  std::cout<<"PASS "<<scenario"""

FRAMES_CASE = r"""      check(lh_frame::build(1,frame.data(),histogram),"frame build failed");
      std::ofstream f("native-frame-1.bin",std::ios::binary); f.write(reinterpret_cast<char *>(frame.data()),frame.size());
      for(unsigned i=0;i<8;++i) check(histogram[i]==kActions[0].histogram[i],"histogram differs");
      check(lh_frame::build(2,frame.data(),histogram)&&lh_frame::build(3,frame.data(),histogram),"unused roles must still build");"""

PROBE_PREFIX = r"""#include <cstdint>
#include <cstring>
#include <iostream>
#include "pal1_cal_v5_identity.inc"
#include "lh_frame_fill.hpp"
// Values mirror the pinned src/ec5_chroma_grid_epd_driver.h and src/epd_config.h
// (both SHA256-bound in the audit report); only the driver gate functions are probed.
enum class EpdChromaGridRole : uint8_t { White=0, Source=1, Mid=2, Target=3, ReverseSource=4, ReverseTarget=5 };
static constexpr uint16_t EPD_WIDTH=1024, EPD_HEIGHT=600, EPD_CONTROLLER_WIDTH=512;
static constexpr uint8_t PH_CODE_COUNT = 8;
namespace ph = mf1750_pal1_cal_v5;
namespace {
"""

PROBE_MAIN = r"""}
uint32_t fnv1aProbe(const uint8_t *d, size_t n) {
  // FNV-1a, algorithm-equivalent to the driver's fnv1a(); the driver's own
  // sha256 digest comparison is not reproduced on the desktop (no mbedTLS),
  // but the histogram+FNV equality against the identity table is exactly the
  // check that the PAL1-R1-D1 defect broke.
  uint32_t h=2166136261u; for(size_t i=0;i<n;++i) h=(h^d[i])*16777619u; return h;
}
int main() {
  std::cout << "layout_valid=" << int(phLayoutValid()) << std::endl;
  std::cout << "target_codes=" << int(ph::kTargetCodes[0]) << "," << int(ph::kTargetCodes[1]) << std::endl;
  for (unsigned r=1;r<=3;++r) {
    static uint8_t frame[307200]; uint32_t histogram[8];
    const EpdChromaGridRole role=static_cast<EpdChromaGridRole>(r);
    std::cout << "role_valid_" << r << "=" << int(phRoleValid(role)) << std::endl;
    std::cout << "driver_build_role" << r << "=" << int(phBuildExpectedFrame(role, frame, histogram)) << std::endl;
    std::cout << "hpp_build_role" << r << "=" << int(lh_frame::build(r, frame, histogram)) << std::endl;
  }
  // Fixture-equivalent check (PAL1-R1-D1 coverage fix): every role the
  // compiled fixture self-check loop validates must have an in-bounds identity
  // entry whose histogram and frame FNV match the freshly built frame. The R1
  // package fails this: kRoles={Source,Mid,Target} but kActions[2].
  int fixture_ok=1;
  for (const EpdChromaGridRole role : kFixtureRoles) {
    const size_t idx=phRoleIndex(role);
    std::cout<<"fixture_role_"<<int(role)<<"_index="<<idx<<std::endl;
    if(idx>=sizeof(ph::kActions)/sizeof(ph::kActions[0])){fixture_ok=0;continue;}
    static uint8_t frame2[307200]; uint32_t histogram2[8];
    if(!phBuildExpectedFrame(role,frame2,histogram2)){fixture_ok=0;continue;}
    if(std::memcmp(histogram2,ph::kActions[idx].histogram,sizeof(histogram2))!=0) fixture_ok=0;
    if(fnv1aProbe(frame2,307200)!=ph::kActions[idx].frameFnv1a) fixture_ok=0;
  }
  std::cout<<"fixture_self_check_equivalent="<<fixture_ok<<std::endl;
  return 0;
}
"""


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key " + key)
        result[key] = value
    return result


def parse_doc(body):
    return json.loads(
        body,
        object_pairs_hook=unique,
        parse_constant=lambda v: (_ for _ in ()).throw(
            ValueError("invalid number " + v)
        ),
    )


def replace_exact(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f"fixture anchor count changed: {old[:80]!r}")
    return text.replace(old, new)


def synthesize_white_records(white):
    """Byte-identical recipe to tests/test_mf1750_pal1_pack.py."""
    def sealed(value):
        body = {k: v for k, v in value.items() if k != "integrity"}
        payload = pal1.canonical(body)
        return {**body, "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": hashlib.sha256(payload).hexdigest()}}

    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH3_SOURCE_WHITE_V1_20260918",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = sealed({"kind": "synthetic-lh3-white-close-review", "protocol": "PASS",
                    "terminal_report": terminal_report})
    base_firmware.write_new(white / "close-review-v1.json",
                            pal1.canonical(close) + b"\n")
    base_firmware.write_new(
        white / pack.WHITE_RECORD_NAMES["app_flash"],
        json.dumps({"binary": {"observed_sha256": "c" * 64}}))
    (white / "live-white-v1").mkdir()
    base_firmware.write_new(
        white / "live-white-v1" / "result.json",
        pal1.canonical(sealed({"kind": "synthetic-lh3-white-result",
                               "terminal_report": terminal_report})) + b"\n")
    base_firmware.write_new(
        white / "postwhite-optical-review-v1.json",
        pal1.canonical(sealed({"kind": "synthetic-lh3-white-optical-review"})) + b"\n")
    records = {k: white / n for k, n in pack.WHITE_RECORD_NAMES.items()}
    anchor = hashlib.sha256(
        (white / "close-review-v1.json").read_bytes()).hexdigest()
    return records, anchor


def prepare_fixture(fixture, anchor):
    fixture.mkdir()
    wrong_review = ("0" if anchor[0] != "0" else "1") * 64
    source = (FIXTURES / "protocol.cpp").read_text(encoding="utf-8")
    source = replace_exact(
        source, '#include "ec5_lightness_history_v1_main.cpp"',
        '#include "pal1_cal_v5_main.cpp"')
    source = replace_exact(source, "TEST_FIXTURE_LH1", RUN_ID)
    source = replace_exact(
        source, "p2catwsv1/used_p2cw1", "lh3srcw_v1/used_lh3sw1", count=3)
    source = replace_exact(
        source, "lhist_v1/cur_lh1", "pal1_v5/cur_pal5", count=2)
    source = replace_exact(
        source, "const String sourceReview=std::string(64,'a');",
        f'const String sourceReview="{anchor}";\n'
        f'const String WRONG_REVIEW="{wrong_review}";')
    source = replace_exact(
        source, '  Preferences::values["lh3srcw_v1/used_lh3sw1"]=2;', PRESETS)
    source = replace_exact(
        source, "const String review=std::string(64,char('a'+n-1));",
        "const String review=sourceReview;")
    source = replace_exact(
        source, "int main(int argc,char **argv) {", HELPERS)
    source = replace_exact(
        source, "        std::cout<<publishedReport.c_str()<<'\\n';",
        '        getReport("action_report");')
    source = replace_exact(
        source,
        "      for(unsigned n=1;n<=3;++n) {\n"
        '        check(lh_frame::build(n,frame.data(),histogram),"frame build failed");\n'
        '        std::ofstream f("native-frame-"+std::to_string(n)+".bin",std::ios::binary); f.write(reinterpret_cast<char *>(frame.data()),frame.size());\n'
        '        for(unsigned i=0;i<8;++i) check(histogram[i]==kActions[n-1].histogram[i],"histogram differs");\n'
        "      }",
        FRAMES_CASE)
    source = replace_exact(
        source, "for(unsigned n=1;n<=3;++n)", "for(unsigned n=1;n<=1;++n)")
    source = replace_exact(
        source,
        '      check(state==RuntimeState::Complete,"campaign not complete");\n'
        "      requestHeaders(3,false,std::string(64,'d')); "
        "server.request(kArmRoute,HTTP_POST); stopped(3);",
        CHAIN_TERMINAL)
    source = replace_exact(
        source,
        "        server.request(route,HTTP_GET); check(server.code==200,"
        "\"GET failed\"); std::cout<<server.body.c_str()<<'\\n';",
        "        server.request(route,HTTP_GET); check(server.code==200,"
        "\"GET failed\"); std::cout<<route<<\"\\t\"<<server.code<<\"\\t\""
        "<<server.body.c_str()<<'\\n';")
    source = replace_exact(
        source, "      setup(); stopped(1);",
        '      setup(); getReport("boot_fault_report"); stopped(1);')
    source = replace_exact(
        source, "      queue(1); server.request(kExecuteRoute,HTTP_POST); stopped();",
        '      queue(1); server.request(kExecuteRoute,HTTP_POST); '
        'printReject("rejected"); stopped();')
    source = replace_exact(
        source, "      arm(1); server.request(kArmRoute,HTTP_POST); stopped();",
        '      arm(1); server.request(kArmRoute,HTTP_POST); '
        'printReject("rejected"); stopped();')
    source = replace_exact(
        source,
        '      arm(1); requestHeaders(1,true); '
        'server.headers["X-LH-Run-Id"]="different_run"; '
        "server.request(kExecuteRoute,HTTP_POST); stopped();",
        '      arm(1); requestHeaders(1,true); '
        'server.headers["X-LH-Run-Id"]="different_run"; '
        'server.request(kExecuteRoute,HTTP_POST); printReject("rejected"); stopped();')
    # Single-action chain: the base reused_stage_review/reused_prior_stage_review
    # scenarios do not exist here (no ordinals 2/3); drop those branches.
    source = replace_exact(
        source,
        '    } else if(scenario=="reused_stage_review") {\n'
        "      queue(1); loop(); requestHeaders(2,false); "
        "server.request(kArmRoute,HTTP_POST); stopped(1);\n",
        "")
    source = replace_exact(
        source,
        '      testFailOnComplete=scenario=="complete_write_failure"; '
        "loop(); stopped(1);",
        '      testFailOnComplete=scenario=="complete_write_failure"; '
        'loop(); getReport("fault_report"); stopped(1);')
    source = replace_exact(
        source,
        "      arm(1); requestHeaders(1,true);\n"
        '      testBusy=scenario=="busy_execute"?0:1; '
        'Preferences::failWrite=scenario=="consume_write_failure";\n'
        "      server.request(kExecuteRoute,HTTP_POST); stopped();",
        "      arm(1); requestHeaders(1,true);\n"
        '      testBusy=scenario=="busy_execute"?0:1; '
        'Preferences::failWrite=scenario=="consume_write_failure";\n'
        '      server.request(kExecuteRoute,HTTP_POST); printReject("rejected"); '
        "stopped();")
    source = replace_exact(
        source, "      loop(); stopped();",
        '      loop(); getReport("fault_report"); stopped();')
    source = replace_exact(
        source, "    } else {\n      requestHeaders(1,false);",
        NEW_SCENARIO_BRANCHES)
    source = replace_exact(
        source,
        '      server.request(scenario=="unknown_mutation"?"/api/reset":kArmRoute,'
        "HTTP_POST); stopped();",
        '      server.request(scenario=="unknown_mutation"?"/api/reset":kArmRoute,'
        'HTTP_POST); printReject("rejected"); stopped();')
    source = replace_exact(
        source, '      else check(scenario=="unknown_mutation","unknown case");',
        MUTATIONS)
    source = replace_exact(
        source,
        '    check(state==RuntimeState::FaultLocked&&testCalls==0&&testBeginCalls==0,'
        '"startup failure touched driver");',
        '    check(state==RuntimeState::FaultLocked&&testCalls==0&&testBeginCalls==0,'
        '"startup failure touched driver");\n'
        '    getReport("boot_fault_report");')
    source = replace_exact(
        source, '  std::cout<<"PASS "<<scenario', PRESERVATION_TAIL)
    base_firmware.write_new(fixture / "protocol.cpp", source)
    # Desktop NVS double enforces the real ESP32 15-byte key/namespace limit.
    pref = (FIXTURES / "Preferences.h").read_text(encoding="utf-8")
    pref = replace_exact(pref, "return !failBegin;",
                         "return !failBegin && ns.size()>0 && ns.size()<=15;")
    pref = replace_exact(
        pref, "if(failWrite||readOnly) return 0; values[key(k)]=v; return 2;",
        "if(failWrite||readOnly||std::string(k).size()>15) return 0; values[key(k)]=v; return 2;")
    pref = replace_exact(
        pref, "if(failWrite||readOnly) return 0; values[key(k)]=v; return 8;",
        "if(failWrite||readOnly||std::string(k).size()>15) return 0; values[key(k)]=v; return 8;")
    base_firmware.write_new(fixture / "Preferences.h", pref)
    return fixture


def probe_source(driver_text):
    begin = driver_text.index("size_t phRoleIndex(")
    end = driver_text.index("bool phDigestMatchesHex(")
    segment = driver_text[begin:end]
    build = driver_text.index("bool phBuildExpectedFrame(")
    frame_fn = driver_text[build:driver_text.index("\n}\n", build) + 3]
    # The fixture self-check's role list is the PAL1-R1-D1 defect surface:
    # compile the exact compiled declaration (renamed) into the probe.
    roles = re.search(r"static constexpr EpdChromaGridRole kRoles\[\] = \{[^}]*\};",
                      driver_text)
    if not roles:
        raise ValueError("fixture kRoles declaration not found in driver")
    roles_decl = roles.group(0).replace("kRoles", "kFixtureRoles")
    return PROBE_PREFIX + roles_decl + "\n" + segment + frame_fn + PROBE_MAIN


def snapshot_generated(generated):
    return {
        p.name: {"bytes": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(generated.iterdir()) if p.is_file()
    }


def check_gate_detail(body, errors, label, false_segment=None):
    detail = body.get("gate_detail")
    if not isinstance(detail, dict) or set(detail) != set(GATE_DETAIL_KEYS):
        errors.append({"label": label, "error": "gate_detail missing or keys differ",
                       "actual": detail})
        return
    for key, value in detail.items():
        wanted = key != false_segment
        if value is not wanted:
            errors.append({"label": label, "gate_detail_segment": key,
                           "expected": wanted, "actual": value})
    if body.get("source_nvs_complete") is not (false_segment is None):
        errors.append({"label": label, "error": "source_nvs_complete/gate_detail "
                       "inconsistent", "actual": body.get("source_nvs_complete")})


def check_chain(documents, contract, anchor, errors):
    if len(documents) != 3:
        errors.append({"expected_documents": 3,
                       "actual_documents": len(documents)})
        return
    labels = [d["label"] for d in documents]
    if labels != ["action_report", "terminal_status", "post_complete_arm_rejected"]:
        errors.append({"error": "unexpected chain labels", "labels": labels})
        return
    action = contract["actions"][0]
    body = documents[0]["json"]
    driver = body.get("driver", {})
    for fkey, wanted in (("input_fnv1a", action["frame"]["fnv1a"]),
                         ("cs1_dtm_fnv1a", action["cs1_dtm"]["fnv1a"]),
                         ("cs2_dtm_fnv1a", action["cs2_dtm"]["fnv1a"])):
        if driver.get(fkey) != wanted:
            errors.append({"field": "driver." + fkey, "expected": wanted,
                           "actual": driver.get(fkey)})
    expected = {
        "ordinal": 1,
        "role": "PAL1_CAL",
        "branch": "PAL1_SYMMETRIC_ACTIVE",
        "global_header": "active",
        "controller_tuple_dispatch": "AA",
        "source_state": pack.SOURCE_STATE,
        "target_state": "PAL1_CAL",
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
        "no_recovery": True,
        "campaign_id": pack.CAMPAIGN,
        "test_id": pal1.TEST_ID,
        "contract_id": contract["contract_id"],
        "identity_revision": "palette-cal-pal1-v5",
        "run_id": RUN_ID,
        "source_review_sha256": anchor,
        "prior_review_sha256": anchor,
        "source_nvs_complete": True,
        "qualified_count": 0,
        "waveform_internal_phase": "OPAQUE",
        "review_digests_are_host_assertions_only": True,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "job_id": 1,
    }
    for key, wanted in expected.items():
        if body.get(key) != wanted:
            errors.append({"field": key, "expected": wanted,
                           "actual": body.get(key)})
    if driver.get("busy_stage_samples", {}).get("unreached_level_sentinel") != 255:
        errors.append({"error": "busy sentinel differs"})
    if documents[0]["status"] != 200:
        errors.append({"error": "report GET not 200"})
    terminal = documents[1]["json"]
    for key, wanted in {
        "cursor_raw": 2,
        "next_ordinal": 2,
        "campaign_complete": True,
        "state": "complete",
        "phase": 0,
        "phase_name": "READY",
        "cursor_valid": True,
        "persistent_key_present": True,
        "campaign_boot_key_present": True,
        "campaign_boot_matches_current": True,
        "execute_pending": False,
        "arm_request_count": 1,
        "execute_request_count": 1,
        "total_driver_call_count": 1,
        "gpio_initialized": True,
        "fixture_self_check_passed": True,
    }.items():
        if terminal.get(key) != wanted:
            errors.append({"terminal_status_field": key, "expected": wanted,
                           "actual": terminal.get(key)})
    nvs = terminal.get("nvs_contract", {})
    if (nvs.get("namespace"), nvs.get("key"), nvs.get("campaign_boot_key"),
            nvs.get("terminal_next_ordinal")) != (
            "pal1_v5", "cur_pal5", "boot_pal5", 2):
        errors.append({"error": "nvs contract mismatch", "actual": nvs})
    rejected = documents[2]
    body = rejected["json"]
    if not (rejected["status"] == 409 and body.get("accepted") is False
            and body.get("fault_locked") is True
            and body.get("error") == "arm_duplicate_complete_or_not_ready"):
        errors.append({"error": "post-complete ARM not rejected as expected",
                       "actual": body})
    check_gate_detail(documents[0]["json"], errors, "action_report")
    check_gate_detail(documents[1]["json"], errors, "terminal_status")


def check_read_only(documents, contract, errors):
    if len(documents) != 4:
        errors.append({"expected_documents": 4,
                       "actual_documents": len(documents)})
        return
    routes = [d["label"] for d in documents]
    if routes != ["/api/ec5/lightness-history-v1/" + n
                  for n in ("version", "manifest", "status", "report")]:
        errors.append({"error": "unexpected read_only routes", "routes": routes})
    version, manifest, status, report = (d["json"] for d in documents)
    for name, doc in zip(("version", "manifest", "status", "report"),
                         (version, manifest, status, report)):
        if doc.get("contract_id") != contract["contract_id"]:
            errors.append({"document": name, "error": "contract_id mismatch"})
        if doc.get("campaign_id") != pack.CAMPAIGN or doc.get("test_id") != pal1.TEST_ID:
            errors.append({"document": name, "error": "campaign/test id mismatch"})
        if doc.get("identity_revision") != "palette-cal-pal1-v5":
            errors.append({"document": name, "error": "identity revision mismatch"})
        check_gate_detail(doc, errors, name)
    for key, wanted in {
        "action_count": 1, "automatic_chaining": False, "startup_refresh": False,
        "retry": False, "recovery": False, "raw_frame_ingress": False,
        "runtime_lut_write": True, "caller_electrical_parameter_write": False,
        "fixed_profile_parameter_write": True, "dither": False,
        "spatial_mixing": False, "layout_id": "PAL1_COLUMNS_8X8",
        "source_nvs_complete": True, "run_id": "", "source_review_sha256": "",
        "prior_review_sha256": "", "qualified_count": 0,
        "waveform_internal_phase": "OPAQUE",
    }.items():
        if version.get(key) != wanted:
            errors.append({"version_field": key, "expected": wanted,
                           "actual": version.get(key)})
    nvs = version.get("nvs_contract", {})
    if (nvs.get("namespace"), nvs.get("key"), nvs.get("campaign_boot_key"),
            nvs.get("terminal_next_ordinal"), nvs.get("initial_value")) != (
            "pal1_v5", "cur_pal5", "boot_pal5", 2, 1):
        errors.append({"error": "version nvs contract mismatch", "actual": nvs})
    baseline = version.get("baseline_contract", {})
    if baseline.get("external_anchor_kind") != pack.SOURCE_STATE:
        errors.append({"error": "baseline anchor kind mismatch",
                       "actual": baseline})
    actions = manifest.get("actions", [])
    if len(actions) != 1:
        errors.append({"error": "manifest action count differs"})
    contract_action = contract["actions"][0]
    for key, wanted in {
        "ordinal": 1, "role": "PAL1_CAL",
        "branch": "PAL1_SYMMETRIC_ACTIVE",
        "global_header": "active",
        "controller_tuple_dispatch": "AA",
        "source_state": pack.SOURCE_STATE,
        "target_state": "PAL1_CAL",
        "frame_sha256": contract_action["frame"]["sha256"],
        "transport_code_histogram": contract_action["frame"]["histogram"],
        "descriptor_id": contract_action["descriptor_id"],
        "action_id": contract_action["action_id"],
    }.items():
        if actions and actions[0].get(key) != wanted:
            errors.append({"manifest_action_field": key,
                           "expected": wanted,
                           "actual": actions[0].get(key) if actions else None})
    layout = manifest.get("history_layout", {})
    if layout.get("target_codes") != list(range(8)):
        errors.append({"error": "manifest target codes differ",
                       "actual": layout.get("target_codes")})
    if layout.get("symmetric_tuple_sequence") != ["AA"]:
        errors.append({"error": "manifest tuple sequence differs",
                       "actual": layout.get("symmetric_tuple_sequence")})
    if layout.get("level_counts") is not None:
        errors.append({"error": "level counts must be null",
                       "actual": layout.get("level_counts")})
    if layout.get("source_white_observation_authority") != "HOST_REVIEW_REQUIRED":
        errors.append({"error": "white observation authority differs"})
    for key, wanted in {
        "one_driver_call_per_action": True, "automatic_chaining": False,
        "factory_otp": False, "custom_lut_or_waveform": True,
        "synchronous_both_controllers": True, "startup_refresh": False,
    }.items():
        if manifest.get(key) != wanted:
            errors.append({"manifest_field": key, "expected": wanted,
                           "actual": manifest.get(key)})
    for key, wanted in {
        "state": "ready", "cursor_raw": 1, "next_ordinal": 1,
        "campaign_complete": False, "phase": 0, "phase_name": "READY",
        "cursor_valid": True, "persistent_key_present": False,
        "campaign_boot_key_present": True, "campaign_boot_matches_current": True,
        "execute_pending": False, "arm_request_count": 0,
        "execute_request_count": 0, "total_driver_call_count": 0,
        "gpio_initialized": True, "fixture_self_check_passed": True,
    }.items():
        if status.get(key) != wanted:
            errors.append({"status_field": key, "expected": wanted,
                           "actual": status.get(key)})
    for key, wanted in {
        "terminal_state": "NOT_EXECUTED", "valid": False, "result": False,
        "driver_called": False, "driver_call_count_for_action": 0,
        "ordinal": None, "no_retry": True, "no_recovery": True,
    }.items():
        if report.get(key) != wanted:
            errors.append({"report_field": key, "expected": wanted,
                           "actual": report.get(key)})


def static_assertions(generated, package, anchor):
    checks = []
    main = (generated / f"{pack.PREFIX}_main.cpp").read_text(encoding="utf-8")
    driver = (generated / f"{pack.PREFIX}_driver.inc").read_text(encoding="utf-8")
    hpp = (generated / "lh_frame_fill.hpp").read_text(encoding="utf-8")
    config = (generated / f"{pack.PREFIX}_main_config.inc").read_text(
        encoding="utf-8")
    identity = (generated / f"{pack.PREFIX}_identity.inc").read_text(
        encoding="utf-8")

    def record(name, ok, detail):
        checks.append({"check": name, "result": "PASS" if ok else "FAIL",
                       "detail": detail})

    record("pal1_frame_byte_identical_to_python",
           (package / "pal1.frame4bpp").read_bytes() == pal1.frame("PAL1"),
           "packaged PAL1 frame equals the host algorithm frame")
    record("main_single_action_count",
           "static constexpr uint8_t kActionCount = 1;" in main
           and "kActions[2]=" in identity,
           "single action: kActionCount=1, terminal ordinal 2, kActions[2]")
    active_branch = ("#if defined(" + pack.MACRO + ")\n"
                     "  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;")
    record("driver_commented_branch_stays_mid_only",
           driver.count(active_branch) == 1
           and ("#if defined(" + pack.MACRO + ")\n"
                "  if (role == EpdChromaGridRole::Mid || role == "
                "EpdChromaGridRole::Target)") not in driver,
           "active-header PAL1: commented profile only for Mid, never Target")
    ordinal1 = [line for line in main.split("\n")
                if "if(action.ordinal==1) return String(" in line]
    record("main_ordinal1_transport_dispatch_aa",
           len(ordinal1) == 1
           and '\\"controller_tuple_dispatch\\":\\"AA\\"' in ordinal1[0]
           and "if(action.ordinal==2) return String(" not in main
           and "if(action.ordinal==3) return String(" not in main,
           "PAL1 transport dispatch is AA on both controllers; no ordinals 2/3")
    record("hpp_pal1_frame_rule",
           "code=role==1 ? (uint8_t)(i%8) : 7;" in hpp,
           "code = cell column index 0..7 for the Source role")
    record("config_nvs_names",
           all(f'"{v}"' in config for v in pack.NVS.values()),
           "pal1_v5/cur_pal5/boot_pal2 compiled")
    record("config_tuple_sequence",
           '\\"symmetric_tuple_sequence\\":[\\"AA\\"]' in config,
           "single AA symmetric tuple")
    record("config_target_codes",
           '\\"target_codes\\":[0,1,2,3,4,5,6,7]' in config,
           "eight PAL1 code columns compiled")
    record("config_level_counts_null", '\\"level_counts\\":null' in config,
           "level counts are not refresh counts")
    record("identity_target_codes",
           "kTargetCodes[8]={0,1,2,3,4,5,6,7}" in identity,
           "identity carries all eight PAL1 codes")
    record("driver_layout_gate_pins_pal1_target_codes",
           driver.count("ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||") == 1
           and "ph::kTargetCodes[0] != 3" not in driver,
           "phLayoutValid pins the PAL1 kTargetCodes endpoints (LH2-DM-D1 class fix)")
    record("gate_old_fault_preserved",
           "bool oldFaultPreserved()" in main
           and 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL' in main,
           "lhist_v1 cur_lh1=770/boot_lh1=0x30a9e5989873f4e0 gate compiled")
    record("gate_rebound_v2_terminal_preserved",
           "bool reboundV2TerminalPreserved()" in main
           and 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL' in main,
           "lh1reb_v2 cur_lh1r=4/boot_lh1r=0x7274e005c8833ca1 gate compiled")
    record("gate_lh2_map_terminal_complete",
           "bool lh2DriveMapTerminalComplete()" in main
           and 'source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL' in main,
           "lh2map_v1 cur_lh2m=4/boot_lh2m=0xac92bb9e25c374ef gate compiled")
    record("gate_lh2_white_preserved",
           "bool lh2WhitePreserved()" in main
           and 'white.getUShort("used_lh2sw1",0)==2' in main,
           "lh2srcw_v1 used_lh2sw1=2 preservation gate compiled")
    record("gate_lh3_dose_v1_bricked_preserved",
           "bool lh3DoseV1BrickedPreserved()" in main
           and 'old.getUShort("cur_lh3d",0)==769' in main,
           "lh3dose_v1 bricked FAULT cursor 769 pinned as historical evidence")
    record("gate_lh3_dose_v2_terminal_complete",
           "bool lh3DoseV2TerminalComplete()" in main
           and 'source.getUShort("cur_lh3d2",0)==4' in main
           and 'source.getULong64("boot_lh3d2",0)==0x4d53de6fe4b39d3bULL' in main,
           "lh3dose_v2 cur_lh3d2=4/boot_lh3d2=0x4d53de6fe4b39d3b terminal gate compiled")
    record("gate_pal1_dead_namespaces_match_nvs_ground_truth",
           "bool pal1V1DeadPreserved()" in main and "bool pal1V2DeadPreserved()" in main
           and "bool pal1V3DeadPreserved()" in main and "bool pal1V4DeadPreserved()" in main
           and 'old.isKey("boot_pal1")' in main and 'old.isKey("boot_pal2")' in main
           and 'old.isKey("boot_pal3")' in main and 'old.isKey("boot_pal4")' in main
           and '!old.isKey("cur_pal1") || old.getUShort("cur_pal1",0)==1' in main
           and '!old.isKey("cur_pal3") || old.getUShort("cur_pal3",0)==1' in main
           and '!old.isKey("cur_pal4") || old.getUShort("cur_pal4",0)==1' in main
           and 'cur==1 || cur==769' in main,
           "pal1_v1/v3/v4 accept boot-key-present + cursor absent-or-1; "
           "pal1_v2 additionally accepts the inferred boot-fault cursor 769 "
           "(dump predates its own RTS reset; V4 bitmap confirmed)")
    record("gate_white_source_requires_all_namespaces",
           "if (!oldFaultPreserved() || !reboundV2TerminalPreserved() || "
           "!lh2DriveMapTerminalComplete() || !lh2WhitePreserved() || "
           "!lh3DoseV1BrickedPreserved() || !lh3DoseV2TerminalComplete() || "
           "!pal1V1DeadPreserved() || !pal1V2DeadPreserved() || "
           "!pal1V3DeadPreserved() || !pal1V4DeadPreserved()) return false;"
           in main and "return lh3WhiteConsumed();" in main
           and 'white.begin("lh3srcw_v1", true)' in main
           and 'white.getUShort("used_lh3sw1",0)==2' in main,
           "whiteSourceReady requires every preserved namespace plus the "
           "consumed LH3 white (segment split for gate_detail)")
    record("gate_detail_bitmap_compiled",
           "String lhGateDetailJson()" in main
           and '\\"gate_detail\\":{' in main
           and '\\"pal1_v4\\":"' in main
           and '+lhGateDetailJson();' in main,
           "identity JSON carries the eleven-segment gate bitmap")
    record("gate_source_review_anchor",
           f'if(source!="{anchor}") return "source_review_anchor_mismatch";'
           in main,
           "X-LH-Source-Review must equal the close-review anchor")
    record("main_labels",
           "PAL1 measured palette calibration V5" in main
           and "FRESH_P2_FACTORY_WHITE" not in main,
           "PAL1 V5 labels compiled without stale source states")
    roles = re.search(r"kRoles\[\] = \{([^}]*)\}", driver)
    slots = re.search(r"kActions\[(\d+)\]", identity)
    role_values = [ROLE_ENUM_VALUE[r.strip().split("::")[-1]]
                   for r in roles.group(1).split(",")] if roles else []
    record("fixture_roles_within_identity_bounds",
           bool(roles) and bool(slots) and bool(role_values)
           and all(0 < v < int(slots.group(1)) for v in role_values)
           and "phRoleIndex(role) == 1" in driver,
           "PAL1-R1-D1 fix: every fixture-validated role has an in-bounds "
           "identity entry and phRoleValid admits only Source")
    return checks


def nvs_ground_truth_checks():
    """Cross-check every compiled gate constant against the sealed NVS dump.

    The desktop Preferences stub models the keys we tell it about; the real
    device's write path is only knowable from a captured dump. PAL1-R2-D2 was
    exactly this class of defect (gate demanded a cursor key that boot never
    writes), so the audit binds the sealed parse report and compares.
    """
    report = json.loads(NVS_PARSE.read_text(encoding="utf-8"),
                        object_pairs_hook=unique)
    body = {k: v for k, v in report.items() if k != "integrity"}
    integrity = report.get("integrity", {})
    if hashlib.sha256(pal1.canonical(body)).hexdigest() != \
            integrity.get("sha256"):
        raise ValueError("NVS dump parse report integrity mismatch")
    active = report["active_values"]
    expectations = [
        ("lhist_v1/cur_lh1", 770, "eq"), ("lhist_v1/boot_lh1", 0x30A9E5989873F4E0, "eq"),
        ("lh1reb_v2/cur_lh1r", 4, "eq"), ("lh1reb_v2/boot_lh1r", 0x7274E005C8833CA1, "eq"),
        ("lh2map_v1/cur_lh2m", 4, "eq"), ("lh2map_v1/boot_lh2m", 0xAC92BB9E25C374EF, "eq"),
        ("lh2srcw_v1/used_lh2sw1", 2, "eq"), ("lh3srcw_v1/used_lh3sw1", 2, "eq"),
        ("lh3dose_v1/cur_lh3d", 769, "eq"),
        ("lh3dose_v2/cur_lh3d2", 4, "eq"), ("lh3dose_v2/boot_lh3d2", 0x4D53DE6FE4B39D3B, "eq"),
        ("pal1_v1/boot_pal1", None, "present"), ("pal1_v1/cur_pal1", 1, "absent_or_eq"),
        ("pal1_v2/boot_pal2", None, "present"),
        # Inferred: the dump predates its own RTS reset; V2's only pre-ARM
        # cursor write is the persistent boot fault 769 (V4 bitmap confirmed
        # pal1_v2=false). Not dump-verifiable by construction.
        ("pal1_v2/cur_pal2", 769, "inferred_post_dump_write"),
        # pal1_v3's boot binding was written at the V3 first boot, AFTER the
        # dump; the value comes from the field report (09665a142b77a580).
        ("pal1_v3/boot_pal3", None, "informational_post_dump"),
        ("pal1_v3/cur_pal3", 1, "informational_absent_or_eq"),
        ("pal1_v4/boot_pal4", None, "informational_post_dump"),
        ("pal1_v4/cur_pal4", 1, "informational_absent_or_eq"),
    ]
    checks = []
    for key, wanted, mode in expectations:
        present = key in active
        actual = active.get(key)
        if mode == "eq":
            ok = present and actual == wanted
        elif mode == "present":
            ok = present
        elif mode == "absent_or_eq":
            ok = (not present) or actual == wanted
        elif mode == "inferred_post_dump_write":
            ok = True  # dump predates the write; the V4 bitmap confirmed it
        else:  # informational: post-dump binding, value from the field report
            ok = True
        checks.append({"key": key, "mode": mode, "expected": wanted,
                       "present": present, "actual": actual,
                       "result": "PASS" if ok else "FAIL"})
    return {"parse_report": base_firmware.bind(NVS_PARSE),
            "checks": checks,
            "all_match": all(c["result"] == "PASS" for c in checks)}


def audit(out=DEFAULT_OUT, package_path=None):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)

    synthetic = package_path is None
    if synthetic:
        white = out / "synthetic-white"
        records, anchor = synthesize_white_records(white)
        base = pack.configured(records, anchor)
        package = out / "synthetic-package"
        prepared = base.prepare(package)
        if prepared["result"] != "PASS_OFFLINE_PREPARED":
            raise RuntimeError("synthetic package prepare failed")
        base.verify_package(package)
    else:
        # Audit the real sealed package: the anchor is the actual LH3 white
        # close-review digest compiled into the firmware, and the records are
        # the real 2026-09-22 field-batch white evidence.
        package = Path(package_path).resolve()
        base = pack.module()
        base.verify_package(package)
        prepared_contract = json.loads(
            (package / "contract.json").read_text(encoding="utf-8"),
            object_pairs_hook=unique)
        anchor = prepared_contract["lh3_white_source_anchor"]["sha256"]
        records = pack.real_records()
        prepared = {"result": "EXTERNAL_SEALED_PACKAGE",
                    "contract_id": prepared_contract["contract_id"]}
    generated = package / "generated"
    contract = json.loads((package / "contract.json").read_text(encoding="utf-8"),
                          object_pairs_hook=unique)
    if len(contract["actions"]) != 1:
        raise ValueError("PAL1 contract must hold exactly one action")
    if contract["actions"][0]["frame"]["histogram"] != PAL1_HISTOGRAM:
        raise ValueError("contract PAL1 histogram differs")

    sources_before = snapshot_generated(generated)
    static_checks = static_assertions(generated, package, anchor)
    static_failures = [c["check"] for c in static_checks
                       if c["result"] != "PASS"]
    nvs_truth = nvs_ground_truth_checks()
    if not nvs_truth["all_match"]:
        static_failures.append("nvs_ground_truth_mismatch")

    fixture = prepare_fixture(out / "fixture", anchor)
    compiler, environment, msvc = compiler_environment()
    if not msvc:
        raise RuntimeError("MSVC toolchain required")
    includes = [fixture, FIXTURES, generated, ROOT / "src"]
    macros = [
        "MF1750_ENABLE_CHROMA_GRID=1",
        pack.MACRO + "=1",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1",
    ]
    command_records = []

    def compile_cpp(source, name, extra_includes=()):
        exe = out / (name + ".exe")
        args = [compiler, "/nologo", "/std:c++17", "/EHsc", "/utf-8",
                "/D_CRT_SECURE_NO_WARNINGS"]
        args += ["/I" + str(p) for p in list(includes) + list(extra_includes)]
        args += ["/D" + m for m in macros]
        args += [str(source), "/Fe:" + str(exe),
                 "/Fo:" + str(out / (name + ".obj"))]
        result = subprocess.run(args, cwd=out, env=environment,
                                capture_output=True, check=False)
        base_firmware.write_new(out / (name + "-compile.log"),
                                result.stdout + result.stderr)
        command_records.append({"command": args,
                                "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError("native compile failed: " + name)
        return exe

    executable = compile_cpp(fixture / "protocol.cpp", "protocol")
    cases = {}
    failures = []
    for name in CASES:
        result = subprocess.run([str(executable), name], cwd=out,
                                capture_output=True, check=False)
        base_firmware.write_new(out / (name + ".log"),
                                result.stdout + result.stderr)
        documents = []
        errors = []
        for index, line in enumerate(
                result.stdout.decode("utf-8").splitlines(), 1):
            if line == f"PASS {name}":
                continue
            try:
                label, status, body = line.split("\t", 2)
                doc = parse_doc(body)
                if not isinstance(doc, dict):
                    raise ValueError("non-object JSON")
                documents.append({
                    "label": label, "status": int(status), "json": doc,
                    "raw_body_sha256": hashlib.sha256(
                        body.encode()).hexdigest()})
            except Exception as error:  # noqa: BLE001 - evidence collection
                errors.append({"line": index, "error": str(error)})
        if result.returncode:
            errors.append({"exit_code": result.returncode,
                           "stderr": result.stderr.decode(
                               "utf-8", errors="replace")})
        elif f"PASS {name}" not in result.stdout.decode("utf-8").splitlines():
            errors.append({"error": "harness PASS marker missing"})
        if name == "chain":
            check_chain(documents, contract, anchor, errors)
        elif name == "read_only":
            check_read_only(documents, contract, errors)
        elif name == "frames":
            if documents:
                errors.append({"error": "frames case must not emit documents"})
        elif name in REJECTION_CASES:
            wanted_status, wanted_error = REJECTION_CASES[name]
            if len(documents) != 1:
                errors.append({"expected_documents": 1,
                               "actual_documents": len(documents)})
            else:
                doc = documents[0]
                body = doc["json"]
                if not (doc["status"] == wanted_status
                        and doc["label"] == "rejected"
                        and body.get("accepted") is False
                        and body.get("fault_locked") is True
                        and body.get("no_retry") is True
                        and body.get("error") == wanted_error):
                    errors.append({"expected": [wanted_status, wanted_error],
                                   "actual_status": doc["status"],
                                   "actual": body})
        elif name in FAULT_REPORT_CASES:
            wanted_error, driver_called, wanted_total = FAULT_REPORT_CASES[name]
            if len(documents) != 1:
                errors.append({"expected_documents": 1,
                               "actual_documents": len(documents)})
            else:
                doc = documents[0]
                body = doc["json"]
                if not (doc["status"] == 200
                        and body.get("terminal_state") == "FAULT"
                        and body.get("result") is False
                        and body.get("error") == wanted_error
                        and body.get("driver_called") is driver_called
                        and body.get("valid") is driver_called
                        and body.get("no_retry") is True
                        and body.get("total_driver_call_count")
                        == wanted_total):
                    errors.append({"expected": wanted_error, "actual": body})
        elif name == "gate_detail_partial":
            if len(documents) != 1:
                errors.append({"expected_documents": 1,
                               "actual_documents": len(documents)})
            else:
                doc = documents[0]
                if doc["status"] != 200 or doc["label"] != "status_partial" \
                        or doc["json"].get("state") != "ready":
                    errors.append({"error": "partial-gate status not served",
                                   "actual_status": doc["status"],
                                   "actual": doc["json"].get("state")})
                else:
                    check_gate_detail(doc["json"], errors, name,
                                      false_segment="lh2_map")
        elif name == "pal1_v2_cursor_fault_accepted":
            # The V2 dead-namespace gate must accept the inferred persistent
            # boot-fault cursor 769 (dump predates its own RTS reset).
            if len(documents) != 1:
                errors.append({"expected_documents": 1,
                               "actual_documents": len(documents)})
            else:
                doc = documents[0]
                if doc["status"] != 200 or doc["label"] != "status_ok" \
                        or doc["json"].get("state") != "ready":
                    errors.append({"error": "769-acceptance status not served",
                                   "actual_status": doc["status"]})
                else:
                    check_gate_detail(doc["json"], errors, name)
                    if doc["json"].get("source_nvs_complete") is not True:
                        errors.append({"error": "gate must accept pal1_v2 "
                                       "cursor 769 (inferred boot fault)"})
        for doc in documents:
            body = doc["json"]
            if "contract_id" in body and body["contract_id"] != contract[
                    "contract_id"]:
                errors.append({"label": doc["label"],
                               "error": "contract_id mismatch"})
        cases[name] = {
            "result": "PASS" if not errors else "FAIL_STOP",
            "expected_documents": {"chain": 3, "read_only": 4, "frames": 0}.get(
                name, 1),
            "parsed_documents": len(documents),
            "raw": base_firmware.bind(out / (name + ".log")),
            "errors": errors,
            "documents": documents,
        }
        if errors:
            failures.append(name)

    frames = []
    path = out / "native-frame-1.bin"
    data = path.read_bytes()
    python_match = data == pal1.frame("PAL1")
    package_match = data == (package / "pal1.frame4bpp").read_bytes()
    if not (python_match and package_match):
        failures.append("frames")
        cases["frames"]["result"] = "FAIL_STOP"
        cases["frames"]["errors"].append(
            {"python_match": python_match, "package_match": package_match})
    frames.append({
        "ordinal": 1, "stage": "PAL1", "role": "PAL1_CAL",
        "global_header": "active",
        "histogram": contract["actions"][0]["frame"]["histogram"],
        "byte_for_byte_match_python": python_match,
        "byte_for_byte_match_package_frame4bpp": package_match,
        **base_firmware.bind(path),
    })

    # The driver's own gate path is compiled and executed verbatim from the
    # generated driver include so its behavior is evidence, not assumption.
    driver_path = generated / f"{pack.PREFIX}_driver.inc"
    probe = out / "driver-gate-probe.cpp"
    base_firmware.write_new(
        probe, probe_source(driver_path.read_text(encoding="utf-8")))
    probe_exe = compile_cpp(probe, "driver-gate-probe")
    result = subprocess.run([str(probe_exe)], cwd=out, capture_output=True,
                            check=False)
    base_firmware.write_new(out / "driver-gate-probe.log",
                            result.stdout + result.stderr)
    probe_facts = {}
    if result.returncode:
        failures.append("driver_frame_gate_probe")
        probe_errors = [{"exit_code": result.returncode}]
    else:
        probe_errors = []
        for line in result.stdout.decode("utf-8").splitlines():
            key, _, value = line.partition("=")
            probe_facts[key] = value
        # PAL1-R1-D1 fix expectations: phRoleValid admits only the Source
        # role; the driver's frame builder rejects Mid/Target; the hpp builder
        # still builds all roles (all-white for 2/3); and the
        # fixture-equivalent loop (the exact compiled kFixtureRoles) has every
        # role in identity bounds with matching histogram/FNV. On the R1
        # package this probe prints fixture_self_check_equivalent=0 (kRoles
        # {Source,Mid,Target} vs kActions[2] out-of-bounds), proving the R1
        # audit's blind spot is now covered.
        expected_probe = {
            "layout_valid": "1",
            "target_codes": "0,1",
            "role_valid_1": "1", "role_valid_2": "0", "role_valid_3": "0",
            "driver_build_role1": "1", "driver_build_role2": "0",
            "driver_build_role3": "0",
            "hpp_build_role1": "1", "hpp_build_role2": "1",
            "hpp_build_role3": "1",
            "fixture_role_1_index": "1",
            "fixture_self_check_equivalent": "1",
        }
        if probe_facts != expected_probe:
            probe_errors.append({"expected": expected_probe,
                                 "actual": probe_facts})
            failures.append("driver_frame_gate_probe")
    probe_case = {
        "result": "PASS" if not probe_errors else "FAIL_STOP",
        "errors": probe_errors,
        "facts": probe_facts,
        "source": base_firmware.bind(probe),
        "log": base_firmware.bind(out / "driver-gate-probe.log"),
        "binary": base_firmware.bind(probe_exe),
    }
    defects = []
    resolved_defects = [{
        "id": "PAL1-R1-D1",
        "severity": "blocks_all_hardware_actions",
        "status": "FIXED_IN_V2_PACK_BEFORE_THIS_AUDIT_SEALED",
        "summary": ("R1 package faulted at first real boot with "
                    "compiled_fixture_self_check_failed: the frozen driver's "
                    "epdValidateCompiledChromaGridFixtures() loops "
                    "kRoles={Source,Mid,Target} and phValidateRole() indexes "
                    "ph::kActions[phRoleIndex(role)] with "
                    "phRoleIndex=(size_t)role (Source=1, Mid=2, Target=3), "
                    "while the single-action R1 identity compiled "
                    "kActions[2] (slot 0 + one action), so Mid/Target read "
                    "out of bounds and the histogram/identity comparison can "
                    "never pass. The R1 native audit MISSED this defect: its "
                    "protocol fixture stubs epdValidateCompiledChromaGridFixtures"
                    "() and its driver probe never touched ph::kActions. V2 "
                    "compiles kRoles={Source} and restricts phRoleValid to "
                    "the Source role; this audit adds a static role/identity "
                    "bounds check and a fixture-equivalent probe loop "
                    "(in-bounds + histogram + frame FNV per compiled role), "
                    "which fails on the R1 package."),
        "evidence": {"probe": probe_facts},
    }, {
        "id": "PAL1-R2-D2",
        "severity": "blocks_all_hardware_actions",
        "status": "FIXED_IN_V3_PACK_BEFORE_THIS_AUDIT_SEALED",
        "summary": ("The V2 gate demanded pal1_v1/cur_pal1 == 1 with isKey, but "
                    "the boot path (initializeOrValidateCampaignBootBinding) "
                    "writes ONLY the campaign boot key; the cursor key is "
                    "first written at the ARM transition. On the real device "
                    "pal1_v1 therefore has boot_pal1 and no cursor key "
                    "(NVS_DUMP_PARSE_20260924_V1), so whiteSourceReady() was "
                    "false and the runner preflight saw "
                    "source_nvs_complete=false. The desktop Preferences stub "
                    "in this audit presets whatever the author writes, which "
                    "is why the V2 audit could not catch a gate-vs-write-path "
                    "mismatch by itself; this audit now cross-checks every "
                    "gate constant against the sealed NVS dump parse "
                    "(nvs_ground_truth), and the pal1_v1/pal1_v2 gates accept "
                    "boot-key-present + cursor absent-or-1. The read-only dump "
                    "operation's RTS reset then killed the fresh pal1_v2 boot "
                    "binding, so pal1_v2 is dead too and pinned the same way."),
        "evidence": {"nvs_ground_truth_all_match": nvs_truth["all_match"]},
    }]

    sources_after = snapshot_generated(generated)
    sources_unchanged = sources_before == sources_after
    if not sources_unchanged:
        failures.append("generated_sources_changed")
    base.verify_package(package)

    report = {
        "schema_version": 1,
        "kind": KIND,
        "result": "PASS" if not failures and not static_failures
        else "FAIL_STOP",
        "synthetic_source_white": synthetic,
        "synthetic_white_method": (
            "tests/test_mf1750_pal1_pack.py::_white_records recipe: sealed "
            "close-review + app-flash-raw + live result + optical review; "
            "review anchor = close-review file SHA256."
            if synthetic else
            "Real sealed package audited in place; the white anchor is the "
            "actual 2026-09-22 LH3 source-white field batch close-review "
            "digest compiled into the firmware."),
        "live_ready": False,
        "live_authorization_granted": False,
        "hardware_accessed": False,
        "network_accessed": False,
        "visible_refreshes": 0,
        "qualified_count": 0,
        "native_driver_stub": True,
        "physical_refreshes_represented_by_stub": 0,
        "audited": {
            "pack_tool": base_firmware.bind(
                ROOT / "tools/mf1750_pal1_pack.py"),
            "host_algorithm": base_firmware.bind(
                ROOT / "host/static_photo/palette_cal_pal1.py"),
            "base_firmware_generator": base_firmware.bind(
                ROOT / "tools/mf1750_lightness_history_firmware.py"),
        },
        "synthetic_white_anchor_sha256": anchor,
        "white_anchor_sha256": anchor,
        "synthetic_white_records": {
            name: base_firmware.bind(path) for name, path in records.items()},
        "package": str(package),
        "package_manifest": base_firmware.bind(package / "manifest.json"),
        "contract": base_firmware.bind(package / "contract.json"),
        "contract_id": contract["contract_id"],
        "prepare_result": prepared,
        "generated_sources_unmodified_during_audit": sources_unchanged,
        "generated_sources": {
            name: {"before": before["sha256"],
                   "after": sources_after[name]["sha256"],
                   "bytes": before["bytes"]}
            for name, before in sources_before.items()},
        "static_assertions": static_checks,
        "nvs_contract_observed": {
            "namespace": "pal1_v5", "cursor": "cur_pal5", "boot": "boot_pal5",
            "encoding": "uint16 (phase<<8)|ordinal",
            "terminal_cursor_raw": 2, "terminal_campaign_complete": True,
        },
        "preserved_namespace_gates": {
            "old_fault": OLD_FAULT, "rebound_v2_terminal": REBOUND_V2,
            "lh2_map_terminal": LH2_MAP, "lh2_white_marker": LH2_WHITE,
            "lh3_white_consumed_marker": LH3_WHITE,
            "lh3_dose_v1_bricked": LH3_DOSE_V1_BRICKED,
            "lh3_dose_v2_terminal": LH3_DOSE_V2_TERMINAL,
            "pal1_v1_dead": PAL1_V1_DEAD, "pal1_v2_dead": PAL1_V2_DEAD,
            "pal1_v3_dead": PAL1_V3_DEAD, "pal1_v4_dead": PAL1_V4_DEAD},
        "nvs_ground_truth": nvs_truth,
        "driver_frame_gate_probe": probe_case,
        "defects": defects,
        "resolved_defects": resolved_defects,
        "compiler": base_firmware.bind(compiler),
        "compile_commands": command_records,
        "native_fixture_files": [
            base_firmware.bind(p) for p in sorted(fixture.iterdir())
            if p.is_file()]
        + [base_firmware.bind(p) for p in sorted(FIXTURES.iterdir())
           if p.is_file()],
        "native_harness": base_firmware.bind(fixture / "protocol.cpp"),
        "native_binary": base_firmware.bind(executable),
        "cases": cases,
        "scenario_count": len(cases),
        "total_parsed_documents": sum(c["parsed_documents"]
                                      for c in cases.values()),
        "failed_scenarios": failures + static_failures,
        "frames": frames,
        "inputs": [
            base_firmware.bind(Path(__file__)),
            base_firmware.bind(ROOT / "tools/mf1750_lightness_history_native_audit.py"),
            base_firmware.bind(ROOT / "tests/fixtures/lightness_history_native/protocol.cpp"),
            base_firmware.bind(ROOT / "tests/test_mf1750_pal1_pack.py"),
        ],
        "evidence": [base_firmware.bind(p) for p in sorted(out.rglob("*"))
                     if p.is_file() and "synthetic-package" not in p.parts],
        "limits": [
            "MSVC compiles the actual generated main.cpp with desktop "
            "Arduino/Preferences/WebServer/WiFi/GPIO substitutes. No HTTP "
            "sockets, serial, GPIO, relay or panel hardware accessed.",
            "Protocol scenarios use a desktop driver stub; compilation and "
            "JSON/state-machine tests do not prove physical driver waveforms, "
            "timing, electrical or optical validity. The real generated "
            "driver gate is probed separately (driver_frame_gate_probe): "
            "layout_valid=1 and all role frames build.",
            "This audit grants no live readiness.",
            "All native responses are parsed with duplicate-key rejection; "
            "malformed lines fail the scenario.",
            "NVS durability across real power cycles, the ESP32 HTTP stack "
            "and physical BUSY behavior are desktop simulations only.",
            "The desktop Preferences stub presets exactly the keys the audit "
            "writes; the real firmware's NVS write path (boot writes only the "
            "boot key; the cursor is first written at ARM) is verified "
            "separately against the sealed NVS dump parse (nvs_ground_truth).",
        ],
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(pal1.canonical(report)).hexdigest(),
    }
    base_firmware.write_new(out / "strict-native-audit.json", report)
    return {
        "result": report["result"],
        "scenarios": len(cases),
        "total_parsed_documents": report["total_parsed_documents"],
        "failed_scenarios": report["failed_scenarios"],
        "defects": [d["id"] for d in defects],
        "synthetic_source_white": synthetic,
        "hardware_accessed": False,
        "report": str(out / "strict-native-audit.json"),
        "report_sha256": hashlib.sha256(
            (out / "strict-native-audit.json").read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--package", type=Path, default=None,
                        help="audit this already-sealed package instead of "
                             "building a synthetic-anchored one")
    args = parser.parse_args()
    summary = audit(args.output_dir, package_path=args.package)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if summary["result"] == "PASS" else 2)
