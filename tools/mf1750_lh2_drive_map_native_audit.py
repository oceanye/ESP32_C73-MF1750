#!/usr/bin/env python3
"""Strict native audit of the LH2 drive-map three-action firmware package.

The real LH2 white-successor field run has not executed, so genuine white
evidence does not exist. This audit synthesizes the white records with exactly
the recipe used by tests/test_mf1750_lh2_drive_map_pack.py (sealed
close-review + app-flash-raw + live result + optical review; the review anchor
is the close-review file SHA256), builds the package into the audit directory
via mf1750_lh2_drive_map_pack.configured(), then MSVC-compiles the actual
generated main.cpp with desktop Arduino/Preferences/WebServer/WiFi/GPIO
doubles and exercises the full protocol: ordinal1 SOURCE (LH2_SOURCE, driver
role Source, active global header, all-white code 7), ordinal2 MIDDLE
(LH2_MIDDLE, Mid, commented, code=recipe%8), ordinal3 MAP (LH2_MAP, Target,
commented, code=4*(recipe/8)+quadrant with quadrant TL0/TR1/BL2/BR3 =
(row>=4)*2+(col>=4)).

The MAP frame rule is compiled from the actual generated lh_frame_fill.hpp and
asserted byte for byte against host/static_photo/lightness_history_lh2.py
frames and the packaged source/middle/map.frame4bpp files. The generated
driver's own phBuildExpectedFrame/phLayoutValid path is compiled and executed
verbatim in a separate probe so driver-gate behavior is documented, not
assumed.

No hardware, serial, network, relay or camera access. Every artifact is
written with O_EXCL into a fresh output directory; the report self-seals with
a canonical-JSON SHA256 integrity field. synthetic_source_white=true,
live_ready=false, hardware_accessed=false.
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

from host.static_photo import lightness_history_lh2 as lh2  # noqa: E402
from tools import mf1750_lightness_history_firmware as base_firmware  # noqa: E402
from tools import mf1750_lh2_drive_map_pack as pack  # noqa: E402
from tools.mf1750_lightness_history_native_audit import compiler_environment  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/lightness_history_native"
DEFAULT_OUT = ROOT / ".test-output/offline/LH2_DRIVE_MAP_NATIVE_20260917_R1"
KIND = "mf1750-lh2-drive-map-native-audit-v1"
RUN_ID = "LH2_DRIVE_MAP_NATIVE_AUDIT"
OLD_FAULT = {"namespace": "lhist_v1", "cursor": "cur_lh1", "boot": "boot_lh1",
             "cursor_raw": 770, "boot_nonce": "30a9e5989873f4e0"}
REBOUND_V2 = {"namespace": "lh1reb_v2", "cursor": "cur_lh1r", "boot": "boot_lh1r",
              "cursor_raw": 4, "boot_nonce": "7274e005c8833ca1"}
MAP_HISTOGRAM = [33280] * 7 + [381440]
TUPLE_SEQUENCE = ["AA", "CC", "CC"]
HEADERS = ["active", "commented", "commented"]
ROLES = ["LH2_SOURCE", "LH2_MIDDLE", "LH2_MAP"]
BRANCHES = ["LH2_SYMMETRIC_SOURCE", "LH2_SYMMETRIC_MIDDLE", "LH2_SYMMETRIC_MAP"]
TARGET_STATES = ["LH2_SOURCE", "LH2_MIDDLE", "LH2_MAP"]
SOURCE_STATES = [pack.SOURCE_STATE, "LH2_SOURCE", "LH2_MIDDLE"]

# Rejection scenarios: one ARM/EXECUTE request is rejected with the expected
# HTTP status and error string, the driver is never called and the campaign
# fault-locks. The native harness asserts the state transition; the parsed
# rejection document is asserted here.
REJECTION_CASES = {
    "missing_white": (400, "source_white_not_complete"),
    "old_fault_missing": (400, "source_white_not_complete"),
    "old_fault_changed": (400, "source_white_not_complete"),
    "old_fault_boot_changed": (400, "source_white_not_complete"),
    "rebound_missing": (400, "source_white_not_complete"),
    "rebound_changed": (400, "source_white_not_complete"),
    "missing_review_header": (400, "missing_or_invalid_review_binding"),
    "invalid_review": (400, "missing_or_invalid_review_binding"),
    "wrong_source_review": (400, "source_review_anchor_mismatch"),
    "first_prior_not_source": (400, "first_review_must_bind_white"),
    "reused_stage_review": (400, "prior_review_cannot_reuse_white"),
    "reused_prior_stage_review": (400, "new_stage_review_required"),
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
# string, whether the driver was called for the faulting action, and the
# expected total driver call count ("reboot" faults the next ordinal after
# ordinal 1 already completed, so the total stays 1 there).
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
    "reused_stage_review",
    "reused_prior_stage_review",
    "changed_review_execute",
    "missing_white",
    "old_fault_missing",
    "old_fault_changed",
    "old_fault_boot_changed",
    "rebound_missing",
    "rebound_changed",
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
  Preferences::values["lh2srcw_v1/used_lh2sw1"]=2;"""

CHAIN_TERMINAL = r"""      check(state==RuntimeState::Complete,"campaign not complete");
      check(Preferences::values.at("lh2map_v1/cur_lh2m")==4,"terminal cursor raw must be 4");
      check(cursorRaw==4&&nextOrdinal==4&&persistentPhase==kPhaseReady,"terminal cursor fields mismatch");
      server.headers.clear(); server.argumentCount=0; server.request(kStatusRoute,HTTP_GET);
      check(server.code==200,"terminal status failed"); std::cout<<"terminal_status\t"<<server.code<<"\t"<<server.body.c_str()<<'\n';
      requestHeaders(3,false,std::string(64,'d')); server.request(kArmRoute,HTTP_POST); printReject("post_complete_arm_rejected"); stopped(3);
      check(Preferences::values.at("lh2map_v1/cur_lh2m")==encodeCursor(kPhaseFault,3),"post-complete ARM must fault-lock the cursor");"""

NEW_SCENARIO_BRANCHES = r"""    } else if(scenario=="reused_prior_stage_review") {
      queue(1); loop(); queue(2,String(std::string(64,'b'))); loop();
      requestHeaders(3,false,String(std::string(64,'b'))); server.request(kArmRoute,HTTP_POST);
      printReject("rejected"); stopped(2);
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
      else check(scenario=="unknown_mutation","unknown case");"""

PRESERVATION_TAIL = r"""  if(scenario!="old_fault_missing") check(Preferences::values.at("lhist_v1/cur_lh1")==unsigned(scenario=="old_fault_changed"?771:770),"old fault cursor altered");
  else check(!Preferences::values.count("lhist_v1/cur_lh1"),"old fault cursor recreated");
  check(Preferences::values.at("lhist_v1/boot_lh1")==0x30a9e5989873f4e0ULL+unsigned(scenario=="old_fault_boot_changed"?1:0),"old fault boot altered");
  if(scenario!="rebound_missing") check(Preferences::values.at("lh1reb_v2/cur_lh1r")==unsigned(scenario=="rebound_changed"?3:4),"rebound v2 cursor altered");
  else check(!Preferences::values.count("lh1reb_v2/cur_lh1r"),"rebound v2 cursor recreated");
  check(Preferences::values.at("lh1reb_v2/boot_lh1r")==0x7274e005c8833ca1ULL,"rebound v2 boot altered");
  std::cout<<"PASS "<<scenario"""

PROBE_PREFIX = r"""#include <cstdint>
#include <cstring>
#include <iostream>
#include "ec5_lightness_lh2_drive_map_v1_identity.inc"
#include "lh_frame_fill.hpp"
// Values mirror the pinned src/ec5_chroma_grid_epd_driver.h and src/epd_config.h
// (both SHA256-bound in the audit report); only the driver gate functions are probed.
enum class EpdChromaGridRole : uint8_t { White=0, Source=1, Mid=2, Target=3, ReverseSource=4, ReverseTarget=5 };
static constexpr uint16_t EPD_WIDTH=1024, EPD_HEIGHT=600, EPD_CONTROLLER_WIDTH=512;
static constexpr uint8_t PH_CODE_COUNT = 8;
namespace ph = mf1750_lh2_drive_map_v1;
namespace {
"""

PROBE_MAIN = r"""}
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
    """Byte-identical recipe to tests/test_mf1750_lh2_drive_map_pack.py."""
    def sealed(value):
        body = {k: v for k, v in value.items() if k != "integrity"}
        payload = lh2.canonical(body)
        return {**body, "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": hashlib.sha256(payload).hexdigest()}}

    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH2_SOURCE_WHITE_V1_20260917",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = sealed({"kind": "synthetic-lh2-white-close-review", "protocol": "PASS",
                    "terminal_report": terminal_report})
    base_firmware.write_new(white / "close-review-v1.json",
                            lh2.canonical(close) + b"\n")
    base_firmware.write_new(
        white / pack.WHITE_RECORD_NAMES["app_flash"],
        json.dumps({"binary": {"observed_sha256": "c" * 64}}))
    (white / "live-white-v1").mkdir()
    base_firmware.write_new(
        white / "live-white-v1" / "result.json",
        lh2.canonical(sealed({"kind": "synthetic-lh2-white-result",
                              "terminal_report": terminal_report})) + b"\n")
    base_firmware.write_new(
        white / "postwhite-optical-review-v1.json",
        lh2.canonical(sealed({"kind": "synthetic-lh2-white-optical-review"})) + b"\n")
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
        '#include "ec5_lightness_lh2_drive_map_v1_main.cpp"')
    source = replace_exact(source, "TEST_FIXTURE_LH1", RUN_ID)
    source = replace_exact(
        source, "p2catwsv1/used_p2cw1", "lh2srcw_v1/used_lh2sw1", count=3)
    source = replace_exact(
        source, "lhist_v1/cur_lh1", "lh2map_v1/cur_lh2m", count=2)
    source = replace_exact(
        source, "const String sourceReview=std::string(64,'a');",
        f'const String sourceReview="{anchor}";\n'
        f'const String WRONG_REVIEW="{wrong_review}";')
    source = replace_exact(
        source, '  Preferences::values["lh2srcw_v1/used_lh2sw1"]=2;', PRESETS)
    source = replace_exact(
        source, "const String review=std::string(64,char('a'+n-1));",
        "const String review=n==1 ? sourceReview : "
        "String(std::string(64,char('a'+n-1)));")
    source = replace_exact(
        source, "int main(int argc,char **argv) {", HELPERS)
    source = replace_exact(
        source, "        std::cout<<publishedReport.c_str()<<'\\n';",
        '        getReport("action_report");')
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
    source = replace_exact(
        source,
        "      queue(1); loop(); requestHeaders(2,false); "
        "server.request(kArmRoute,HTTP_POST); stopped(1);",
        "      queue(1); loop(); requestHeaders(2,false); "
        'server.request(kArmRoute,HTTP_POST); printReject("rejected"); stopped(1);')
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
    return PROBE_PREFIX + segment + frame_fn + PROBE_MAIN


def snapshot_generated(generated):
    return {
        p.name: {"bytes": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(generated.iterdir()) if p.is_file()
    }


def check_chain(documents, contract, anchor, errors):
    if len(documents) != 5:
        errors.append({"expected_documents": 5,
                       "actual_documents": len(documents)})
        return
    labels = [d["label"] for d in documents]
    if labels != ["action_report", "action_report", "action_report",
                  "terminal_status", "post_complete_arm_rejected"]:
        errors.append({"error": "unexpected chain labels", "labels": labels})
        return
    for ordinal, document in enumerate(documents[:3], 1):
        body = document["json"]
        action = contract["actions"][ordinal - 1]
        # The wire report binds frames through the driver FNV1a triple, not
        # top-level sha256 fields; those live in the manifest (read_only).
        driver = body.get("driver", {})
        for fkey, wanted in (("input_fnv1a", action["frame"]["fnv1a"]),
                             ("cs1_dtm_fnv1a", action["cs1_dtm"]["fnv1a"]),
                             ("cs2_dtm_fnv1a", action["cs2_dtm"]["fnv1a"])):
            if driver.get(fkey) != wanted:
                errors.append({"ordinal": ordinal, "field": "driver." + fkey,
                               "expected": wanted,
                               "actual": driver.get(fkey)})
        expected = {
            "ordinal": ordinal,
            "role": ROLES[ordinal - 1],
            "branch": BRANCHES[ordinal - 1],
            "global_header": HEADERS[ordinal - 1],
            "controller_tuple_dispatch": TUPLE_SEQUENCE[ordinal - 1],
            "source_state": SOURCE_STATES[ordinal - 1],
            "target_state": TARGET_STATES[ordinal - 1],
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": ordinal,
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": ordinal + 1,
            "campaign_complete": ordinal == 3,
            "no_retry": True,
            "no_recovery": True,
            "campaign_id": pack.CAMPAIGN,
            "test_id": lh2.TEST_ID,
            "contract_id": contract["contract_id"],
            "identity_revision": "lightness-lh2-drive-map-v1",
            "run_id": RUN_ID,
            "source_review_sha256": anchor,
            "prior_review_sha256": anchor if ordinal == 1 else chr(ord("a") + ordinal - 1) * 64,
            "source_nvs_complete": True,
            "qualified_count": 0,
            "waveform_internal_phase": "OPAQUE",
            "review_digests_are_host_assertions_only": True,
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "job_id": ordinal,
        }
        for key, wanted in expected.items():
            if body.get(key) != wanted:
                errors.append({"ordinal": ordinal, "field": key,
                               "expected": wanted, "actual": body.get(key)})
        driver = body.get("driver", {})
        if int(driver.get("input_fnv1a", -1)) != action["frame"]["fnv1a"]:
            errors.append({"ordinal": ordinal, "error": "driver frame fnv1a differs"})
        if int(driver.get("cs1_dtm_fnv1a", -1)) != action["cs1_dtm"]["fnv1a"]:
            errors.append({"ordinal": ordinal, "error": "driver cs1 fnv1a differs"})
        if int(driver.get("cs2_dtm_fnv1a", -1)) != action["cs2_dtm"]["fnv1a"]:
            errors.append({"ordinal": ordinal, "error": "driver cs2 fnv1a differs"})
        if driver.get("busy_stage_samples", {}).get("unreached_level_sentinel") != 255:
            errors.append({"ordinal": ordinal, "error": "busy sentinel differs"})
        if document["status"] != 200:
            errors.append({"ordinal": ordinal, "error": "report GET not 200"})
    terminal = documents[3]["json"]
    for key, wanted in {
        "cursor_raw": 4,
        "next_ordinal": 4,
        "campaign_complete": True,
        "state": "complete",
        "phase": 0,
        "phase_name": "READY",
        "cursor_valid": True,
        "persistent_key_present": True,
        "campaign_boot_key_present": True,
        "campaign_boot_matches_current": True,
        "execute_pending": False,
        "arm_request_count": 3,
        "execute_request_count": 3,
        "total_driver_call_count": 3,
        "gpio_initialized": True,
        "fixture_self_check_passed": True,
    }.items():
        if terminal.get(key) != wanted:
            errors.append({"terminal_status_field": key, "expected": wanted,
                           "actual": terminal.get(key)})
    nvs = terminal.get("nvs_contract", {})
    if (nvs.get("namespace"), nvs.get("key"), nvs.get("campaign_boot_key"),
            nvs.get("terminal_next_ordinal")) != (
            "lh2map_v1", "cur_lh2m", "boot_lh2m", 4):
        errors.append({"error": "nvs contract mismatch", "actual": nvs})
    rejected = documents[4]
    body = rejected["json"]
    if not (rejected["status"] == 409 and body.get("accepted") is False
            and body.get("fault_locked") is True
            and body.get("error") == "arm_duplicate_complete_or_not_ready"):
        errors.append({"error": "post-complete ARM not rejected as expected",
                       "actual": body})


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
        if doc.get("campaign_id") != pack.CAMPAIGN or doc.get("test_id") != lh2.TEST_ID:
            errors.append({"document": name, "error": "campaign/test id mismatch"})
        if doc.get("identity_revision") != "lightness-lh2-drive-map-v1":
            errors.append({"document": name, "error": "identity revision mismatch"})
    for key, wanted in {
        "action_count": 3, "automatic_chaining": False, "startup_refresh": False,
        "retry": False, "recovery": False, "raw_frame_ingress": False,
        "runtime_lut_write": True, "caller_electrical_parameter_write": False,
        "fixed_profile_parameter_write": True, "dither": False,
        "spatial_mixing": False, "layout_id": "LH2_DRIVE_MAP_8X8",
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
            "lh2map_v1", "cur_lh2m", "boot_lh2m", 4, 1):
        errors.append({"error": "version nvs contract mismatch", "actual": nvs})
    baseline = version.get("baseline_contract", {})
    if baseline.get("external_anchor_kind") != pack.SOURCE_STATE:
        errors.append({"error": "baseline anchor kind mismatch",
                       "actual": baseline})
    actions = manifest.get("actions", [])
    if len(actions) != 3:
        errors.append({"error": "manifest action count differs"})
    for ordinal, action in enumerate(actions, 1):
        contract_action = contract["actions"][ordinal - 1]
        for key, wanted in {
            "ordinal": ordinal, "role": ROLES[ordinal - 1],
            "branch": BRANCHES[ordinal - 1],
            "global_header": HEADERS[ordinal - 1],
            "controller_tuple_dispatch": TUPLE_SEQUENCE[ordinal - 1],
            "source_state": SOURCE_STATES[ordinal - 1],
            "target_state": TARGET_STATES[ordinal - 1],
            "frame_sha256": contract_action["frame"]["sha256"],
            "transport_code_histogram": contract_action["frame"]["histogram"],
            "descriptor_id": contract_action["descriptor_id"],
            "action_id": contract_action["action_id"],
        }.items():
            if action.get(key) != wanted:
                errors.append({"manifest_action": ordinal, "field": key,
                               "expected": wanted, "actual": action.get(key)})
    layout = manifest.get("history_layout", {})
    if layout.get("target_codes") != list(range(8)):
        errors.append({"error": "manifest target codes differ",
                       "actual": layout.get("target_codes")})
    if layout.get("symmetric_tuple_sequence") != TUPLE_SEQUENCE:
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


def static_assertions(generated, anchor):
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

    commented_branch = ("if (role == EpdChromaGridRole::Mid || role == "
                        "EpdChromaGridRole::Target) useCommentedGlobal = true;")
    record("driver_map_target_selects_commented_profile_exactly_once",
           driver.count(commented_branch) == 1,
           "Mid and Target roles both select the commented global profile")
    ordinal3 = [line for line in main.split("\n")
                if "if(action.ordinal==3) return String(" in line]
    record("main_ordinal3_transport_dispatch_cc",
           len(ordinal3) == 1
           and '\\"controller_tuple_dispatch\\":\\"CC\\"' in ordinal3[0],
           "MAP transport dispatch is CC on both controllers")
    record("hpp_map_frame_rule",
           "(uint8_t)(4*(recipe/8)+((i/8)>=4?2:0)+((i%8)>=4?1:0))" in hpp,
           "code = 4*(recipe/8) + quadrant(TL0,TR1,BL2,BR3)")
    record("config_nvs_names",
           all(f'"{v}"' in config for v in pack.NVS.values()),
           "lh2map_v1/cur_lh2m/boot_lh2m compiled")
    record("config_tuple_sequence",
           '\\"symmetric_tuple_sequence\\":[\\"AA\\",\\"CC\\",\\"CC\\"]' in config,
           "AA/CC/CC symmetric tuple sequence")
    record("config_target_codes",
           '\\"target_codes\\":[0,1,2,3,4,5,6,7]' in config,
           "eight map codes compiled")
    record("config_level_counts_null", '\\"level_counts\\":null' in config,
           "level counts are not refresh counts")
    record("identity_target_codes",
           "kTargetCodes[8]={0,1,2,3,4,5,6,7}" in identity,
           "identity carries all eight map codes")
    record("driver_layout_gate_pins_lh2_target_codes",
           driver.count("ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||") == 1
           and "ph::kTargetCodes[0] != 3" not in driver,
           "phLayoutValid pins the LH2 kTargetCodes endpoints (LH2-DM-D1 fix)")
    record("gate_old_fault_preserved",
           "bool oldFaultPreserved()" in main
           and 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL' in main,
           "lhist_v1 cur_lh1=770/boot_lh1=0x30a9e5989873f4e0 gate compiled")
    record("gate_rebound_v2_terminal_preserved",
           "bool reboundV2TerminalPreserved()" in main
           and 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL' in main,
           "lh1reb_v2 cur_lh1r=4/boot_lh1r=0x7274e005c8833ca1 gate compiled")
    record("gate_white_source_requires_preserved_namespaces",
           "if (!oldFaultPreserved() || !reboundV2TerminalPreserved()) return false;"
           in main and 'white.begin("lh2srcw_v1", true)' in main,
           "whiteSourceReady requires both preserved namespaces plus LH2 white")
    record("gate_source_review_anchor",
           f'if(source!="{anchor}") return "source_review_anchor_mismatch";'
           in main,
           "X-LH-Source-Review must equal the synthetic close-review anchor")
    record("main_labels",
           "LH2 drive-map history V1" in main
           and "FRESH_P2_FACTORY_WHITE" not in main,
           "LH2 labels compiled without stale source states")
    return checks


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
        # Audit the real sealed package: the anchor is the actual LH2 white
        # close-review digest compiled into the firmware, and the records are
        # the real field-batch white evidence.
        package = Path(package_path).resolve()
        base = pack.module()
        base.verify_package(package)
        prepared_contract = json.loads(
            (package / "contract.json").read_text(encoding="utf-8"),
            object_pairs_hook=unique)
        anchor = prepared_contract["lh2_white_source_anchor"]["sha256"]
        records = {k: pack.WHITE / n for k, n in pack.WHITE_RECORD_NAMES.items()}
        prepared = {"result": "EXTERNAL_SEALED_PACKAGE",
                    "contract_id": prepared_contract["contract_id"]}
    generated = package / "generated"
    contract = json.loads((package / "contract.json").read_text(encoding="utf-8"),
                          object_pairs_hook=unique)
    if contract["actions"][2]["frame"]["histogram"] != MAP_HISTOGRAM:
        raise ValueError("contract MAP histogram differs")

    sources_before = snapshot_generated(generated)
    static_checks = static_assertions(generated, anchor)
    static_failures = [c["check"] for c in static_checks
                       if c["result"] != "PASS"]

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
        for doc in documents:
            body = doc["json"]
            if "contract_id" in body and body["contract_id"] != contract[
                    "contract_id"]:
                errors.append({"label": doc["label"],
                               "error": "contract_id mismatch"})
        cases[name] = {
            "result": "PASS" if not errors else "FAIL_STOP",
            "expected_documents": {"chain": 5, "read_only": 4, "frames": 0}.get(
                name, 1),
            "parsed_documents": len(documents),
            "raw": base_firmware.bind(out / (name + ".log")),
            "errors": errors,
            "documents": documents,
        }
        if errors:
            failures.append(name)

    frames = []
    for ordinal, stage in enumerate(lh2.STAGES, 1):
        path = out / f"native-frame-{ordinal}.bin"
        data = path.read_bytes()
        python_match = data == lh2.frame(stage)
        package_path = package / (stage.lower() + ".frame4bpp")
        package_match = data == package_path.read_bytes()
        if not (python_match and package_match):
            failures.append("frames")
            cases["frames"]["result"] = "FAIL_STOP"
            cases["frames"]["errors"].append(
                {"stage": stage, "python_match": python_match,
                 "package_match": package_match})
        frames.append({
            "ordinal": ordinal, "stage": stage,
            "role": ROLES[ordinal - 1],
            "global_header": HEADERS[ordinal - 1],
            "histogram": contract["actions"][ordinal - 1]["frame"]["histogram"],
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
        # The generated driver's layout gate pins the LH2 identity
        # kTargetCodes[8]={0..7} endpoints (an earlier pack revision kept the
        # frozen LH1 {3,7} check, defect LH2-DM-D1, fixed in the pack before
        # this audit sealed). phLayoutValid() and the driver's own
        # phBuildExpectedFrame() must therefore accept all three roles, and
        # the generated lh_frame_fill.hpp builds all three frames (the path
        # the frames case audits byte for byte).
        expected_probe = {
            "layout_valid": "1",
            "target_codes": "0,1",
            "role_valid_1": "1", "role_valid_2": "1", "role_valid_3": "1",
            "driver_build_role1": "1", "driver_build_role2": "1",
            "driver_build_role3": "1",
            "hpp_build_role1": "1", "hpp_build_role2": "1",
            "hpp_build_role3": "1",
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
        "id": "LH2-DM-D1",
        "severity": "blocks_all_hardware_actions",
        "status": "FIXED_IN_PACK_BEFORE_THIS_AUDIT_SEALED",
        "summary": ("An earlier pack revision generated a driver whose "
                    "phLayoutValid() kept the frozen LH1/V3 check "
                    "kTargetCodes[0]!=3 || kTargetCodes[1]!=7 while the LH2 "
                    "identity redefined kTargetCodes[8]={0..7}; the layout "
                    "gate was therefore false and no action could ever be "
                    "armed on hardware. The pack now pins the new array's "
                    "endpoints (kTargetCodes[0]!=0 || kTargetCodes[7]!=7) "
                    "and this audit's driver_frame_gate_probe asserts "
                    "layout_valid=1 with all three roles building."),
        "evidence": {"probe": probe_facts},
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
            "tests/test_mf1750_lh2_drive_map_pack.py::_white_records recipe: "
            "sealed close-review + app-flash-raw + live result + optical "
            "review; review anchor = close-review file SHA256."
            if synthetic else
            "Real sealed package audited in place; the white anchor is the "
            "actual LH2 white-successor field batch close-review digest "
            "(LH2_SOURCE_WHITE_20260918_V1) compiled into the firmware."),
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
                ROOT / "tools/mf1750_lh2_drive_map_pack.py"),
            "host_algorithm": base_firmware.bind(
                ROOT / "host/static_photo/lightness_history_lh2.py"),
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
            "namespace": "lh2map_v1", "cursor": "cur_lh2m", "boot": "boot_lh2m",
            "encoding": "uint16 (phase<<8)|ordinal",
            "terminal_cursor_raw": 4, "terminal_campaign_complete": True,
        },
        "preserved_namespace_gates": {
            "old_fault": OLD_FAULT, "rebound_v2_terminal": REBOUND_V2},
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
            base_firmware.bind(ROOT / "tests/test_mf1750_lh2_drive_map_pack.py"),
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
            "layout_valid=1 and all three role frames build.",
            "White source records are synthetic; the real LH2 white-successor "
            "field run has not executed. This audit grants no live readiness.",
            "All native responses are parsed with duplicate-key rejection; "
            "malformed lines fail the scenario.",
            "NVS durability across real power cycles, the ESP32 HTTP stack "
            "and physical BUSY behavior are desktop simulations only.",
        ],
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(lh2.canonical(report)).hexdigest(),
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
