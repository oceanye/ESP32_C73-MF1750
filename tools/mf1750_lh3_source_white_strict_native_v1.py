#!/usr/bin/env python3
"""Strict native audit of the sealed LH3 source-white firmware package.

MSVC desktop-compiles the frozen generated main.cpp (protocol state machine)
with desktop Arduino/Preferences/WebServer/WiFi/GPIO substitutes and exercises
every protocol scenario, including the four-namespace lh2DriveMapTerminalComplete
source gate (source namespace lh2map_v1 exact terminal pair cur_lh2m=4 /
boot_lh2m=0xac92bb9e25c374ef; old fault namespace lhist_v1 cur_lh1=770 /
boot_lh1=0x30a9e5989873f4e0, rebound V2 namespace lh1reb_v2 cur_lh1r=4 /
boot_lh1r=0x7274e005c8833ca1 and consumed LH2 white marker
lh2srcw_v1/used_lh2sw1=2 all preserved).

No hardware, serial, network, relay or camera access. The panel driver is a
desktop stub; no physical refresh is represented. Every artifact is written
with O_EXCL into a fresh output directory and the audit self-seals with a
canonical-JSON SHA256 integrity field.
"""

from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.mf1750_lightness_history_native_audit import compiler_environment  # noqa: E402

PKG = ROOT / ".test-output/offline/LH3_SOURCE_WHITE_20260918_R1"
OUT = ROOT / ".test-output/offline/LH3_SOURCE_WHITE_STRICT_NATIVE_20260918_R1"
FIXTURE_SRC = ROOT / "tests/fixtures/lh1_source_white_native_v2"

PROTOCOL_CPP = r"""#include <iostream>
#include <stdexcept>
#include <string>
#include SOURCE_MAIN_PATH
int calls=0; bool driverSuccess=true; EpdOperationReport stubReport; int busy=1;
void epdBegin(){}
int epdReadBusy(){return busy;}
const EpdOperationReport& epdGetLastOperationReport(){return stubReport;}
bool epdValidateCompiledFactoryOtpWhiteRecoveryFixture(){return true;}
bool epdDisplayCompiledFactoryOtpWhiteRecovery(){++calls; stubReport.valid=true; stubReport.sequenceOk=driverSuccess; return driverSuccess;}
String epdDiagnosticReportJson(){return String("{\"synthetic_desktop_stub\":true,\"valid\":true,\"sequence_ok\":true}");}
void check(bool x,const char*m){if(!x)throw std::runtime_error(m);}
void output(const char* label){std::cout<<label<<'\t'<<server.code<<'\t'<<server.body.c_str()<<'\n';}
void req(const char* path,int method,const char* label){server.request(path,method);output(label);}
void headers(bool exec){server.headers.clear();server.argumentCount=0;server.headers={{kBuildHeader,kBuildTag},{kTestHeader,kTestId},{kCampaignHeader,kCampaignId},{kActionHeader,kActionId},{kOrdinalHeader,"1"},{kDescriptorHeader,kDescriptorId},{kBootNonceHeader,bootNonce()},{kIntentHeader,exec?kExecuteIntent:kArmIntent}};if(exec)server.headers[kArmNonceHeader]=armNonce();}
void arm(){headers(false);req(kArmRoute,HTTP_POST,"arm");check(server.code==201,"ARM not accepted");}
void execute(){headers(true);req(kExecuteRoute,HTTP_POST,"execute");check(server.code==202,"EXECUTE not accepted");}
void reportGet(const char*label){server.headers.clear();server.argumentCount=0;req(kReportRoute,HTTP_GET,label);check(server.code==200,"report GET failed");}
void sourceLoss(const std::string&s){if(s=="missing_source")Preferences::values.erase("lh2map_v1/cur_lh2m");else if(s=="missing_boot")Preferences::values.erase("lh2map_v1/boot_lh2m");else if(s=="boot0")Preferences::values["lh2map_v1/boot_lh2m"]=0;else if(s=="cur1")Preferences::values["lh2map_v1/cur_lh2m"]=1;else if(s=="cur3")Preferences::values["lh2map_v1/cur_lh2m"]=3;else if(s=="wrong_nonzero_boot")Preferences::values["lh2map_v1/boot_lh2m"]=0x1111111111111111ULL;else if(s=="old_cur_changed")Preferences::values["lhist_v1/cur_lh1"]=769;else if(s=="old_boot0")Preferences::values["lhist_v1/boot_lh1"]=0;else if(s=="reb_cur_changed")Preferences::values["lh1reb_v2/cur_lh1r"]=3;else if(s=="reb_boot0")Preferences::values["lh1reb_v2/boot_lh1r"]=0;else if(s=="white_used_changed")Preferences::values["lh2srcw_v1/used_lh2sw1"]=1;else if(s=="white_used_missing")Preferences::values.erase("lh2srcw_v1/used_lh2sw1");else Preferences::values["lh2map_v1/cur_lh2m"]=0xff02;}
int main(int argc,char**argv){try{
 std::string s=argc>1?argv[1]:"all";
 Preferences::values.clear();Preferences::values["lhist_v1/cur_lh1"]=770;Preferences::values["lhist_v1/boot_lh1"]=0x30a9e5989873f4e0ULL;Preferences::values["lh1reb_v2/cur_lh1r"]=4;Preferences::values["lh1reb_v2/boot_lh1r"]=0x7274e005c8833ca1ULL;Preferences::values["lh2srcw_v1/used_lh2sw1"]=2;Preferences::values["lh2map_v1/cur_lh2m"]=4;Preferences::values["lh2map_v1/boot_lh2m"]=0xac92bb9e25c374efULL;
 if(s=="own_consumed_boot")Preferences::values[std::string(kNvsNamespace)+"/"+kNvsKey]=0x0201;
 if(s=="own_complete_boot")Preferences::values[std::string(kNvsNamespace)+"/"+kNvsKey]=2;
 setup();check(calls==0,"startup called driver");
 if(s=="own_consumed_boot"||s=="own_complete_boot"){headers(false);req(kArmRoute,HTTP_POST,"arm_rejected");check(server.code==409&&calls==0,"replayed persistent cursor");return 0;}
 check(state==RuntimeState::Ready,"startup not READY");
 if(s=="all"||s=="off_gets"){
  if(s=="off_gets")busy=0;
  for(auto p:{kVersionRoute,kManifestRoute,kStatusRoute,kReportRoute}){req(p,HTTP_GET,p);check(server.code==200,"GET failed");}
  check(calls==0&&armRequestCount==0&&executeRequestCount==0,"GET mutated");
  if(s=="off_gets")return 0;
 }
 if(s=="missing_source"||s=="missing_boot"||s=="boot0"||s=="cur1"||s=="cur3"||s=="source_fault"||s=="wrong_nonzero_boot"||s=="old_cur_changed"||s=="old_boot0"||s=="reb_cur_changed"||s=="reb_boot0"||s=="white_used_changed"||s=="white_used_missing"){
  sourceLoss(s);headers(false);req(kArmRoute,HTTP_POST,"arm_rejected");check(server.code==409&&calls==0,"ARM source guard failed");reportGet("fault_report");return 0;
 }
 if(s=="body"||s=="wrongaction"||s=="wrongdescriptor"||s=="wrongboot"||s=="oldwhiteaction"||s=="busy_arm"||s=="writefail_arm"||s=="unknown_post"){
  headers(false);if(s=="body")server.argumentCount=1;if(s=="wrongaction")server.headers[kActionHeader]="wrong";if(s=="wrongdescriptor")server.headers[kDescriptorHeader]="wrong";if(s=="wrongboot")server.headers[kBootNonceHeader]="wrong";if(s=="oldwhiteaction")server.headers[kActionHeader]="677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19";if(s=="busy_arm")busy=0;if(s=="writefail_arm")Preferences::failWrite=true;
  req(s=="unknown_post"?"/not-allowed":kArmRoute,HTTP_POST,"arm_rejected");check(server.code>=400&&calls==0,"bad ARM accepted");Preferences::failWrite=false;reportGet("fault_report");return 0;
 }
 if(s=="execute_without_arm"){headers(true);req(kExecuteRoute,HTTP_POST,"execute_rejected");check(server.code==409&&calls==0,"EXEC before ARM accepted");return 0;}
 arm();
 if(s=="duplicate_arm"){headers(false);req(kArmRoute,HTTP_POST,"duplicate_arm_rejected");check(server.code==409&&calls==0,"duplicate ARM accepted");return 0;}
 if(s=="source_lost_after_arm"||s=="busy_execute"||s=="writefail_execute"||s=="wrong_arm_nonce"){
  headers(true);if(s=="source_lost_after_arm")sourceLoss("missing_source");if(s=="busy_execute")busy=0;if(s=="writefail_execute")Preferences::failWrite=true;if(s=="wrong_arm_nonce")server.headers[kArmNonceHeader]="wrong";
  req(kExecuteRoute,HTTP_POST,"execute_rejected");check(server.code>=400&&calls==0&&!executePending,"EXEC guard failed");Preferences::failWrite=false;reportGet("fault_report");return 0;
 }
 execute();
 if(s=="duplicate_execute"){headers(true);req(kExecuteRoute,HTTP_POST,"duplicate_execute_rejected");check(server.code==409&&calls==0,"duplicate EXEC accepted");loop();check(calls==0,"fault duplicate dispatched");return 0;}
 if(s=="source_lost_before_dispatch")sourceLoss("missing_source");
 if(s=="busy_dispatch")busy=0;
 if(s=="driver_failed")driverSuccess=false;
 if(s=="writefail_complete")Preferences::failWrite=true;
 loop();const bool beforeDriverFail=s=="source_lost_before_dispatch"||s=="busy_dispatch";
 check(calls==(beforeDriverFail?0:1),"driver count mismatch");Preferences::failWrite=false;reportGet("terminal_report");
 if(beforeDriverFail||s=="driver_failed"||s=="writefail_complete")check(state==RuntimeState::FaultLocked,"not FAULT locked");
 else check(state==RuntimeState::Complete&&nextOrdinal==2&&!executePending,"not COMPLETE");
 for(int i=0;i<3;++i)loop();check(calls==(beforeDriverFail?0:1),"autochain called driver");return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
"""

EXPECTED = {
    "all": 7,
    "off_gets": 4,
    "missing_source": 2,
    "missing_boot": 2,
    "boot0": 2,
    "cur1": 2,
    "cur3": 2,
    "source_fault": 2,
    "wrong_nonzero_boot": 2,
    "old_cur_changed": 2,
    "old_boot0": 2,
    "reb_cur_changed": 2,
    "reb_boot0": 2,
    "white_used_changed": 2,
    "white_used_missing": 2,
    "body": 2,
    "wrongaction": 2,
    "wrongdescriptor": 2,
    "wrongboot": 2,
    "oldwhiteaction": 2,
    "busy_arm": 2,
    "writefail_arm": 2,
    "unknown_post": 2,
    "execute_without_arm": 1,
    "duplicate_arm": 2,
    "source_lost_after_arm": 3,
    "busy_execute": 3,
    "writefail_execute": 3,
    "wrong_arm_nonce": 3,
    "duplicate_execute": 3,
    "source_lost_before_dispatch": 3,
    "busy_dispatch": 3,
    "driver_failed": 3,
    "writefail_complete": 3,
    "own_consumed_boot": 1,
    "own_complete_boot": 1,
}


def sha(p):
    b = Path(p).read_bytes()
    return {
        "path": str(Path(p).resolve()),
        "bytes": len(b),
        "sha256": hashlib.sha256(b).hexdigest(),
    }


def unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key " + k)
        d[k] = v
    return d


def canon(v):
    return json.dumps(
        v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def write(path, data):
    with Path(path).open("xb") as f:
        f.write(data)


def main():
    contract = json.loads(
        (PKG / "contract.json").read_text(encoding="utf-8"), object_pairs_hook=unique
    )
    build = json.loads(
        (PKG / "build-report.json").read_text(encoding="utf-8"),
        object_pairs_hook=unique,
    )
    assert build["result"] == "PASS", "sealed build is not PASS"
    elf = next(v for v in build["artifacts"] if v["path"].endswith(".elf"))
    assert sha(elf["path"])["sha256"] == elf["sha256"], "ELF artifact mismatch"
    firmware_bin = next(v for v in build["artifacts"] if v["path"].endswith(".bin"))
    assert sha(firmware_bin["path"])["sha256"] == firmware_bin["sha256"], (
        "BIN artifact mismatch"
    )
    main_cpp = PKG / "generated/main.cpp"
    authority_before = sha(main_cpp)
    OUT.mkdir(exist_ok=False)
    fixture = OUT / "fixture"
    fixture.mkdir(exist_ok=False)
    for src in FIXTURE_SRC.glob("*.h"):
        if src.name != "esp_ota_ops.h":
            shutil.copyfile(src, fixture / src.name)
    values = ",".join("0x" + elf["sha256"][i : i + 2] for i in range(0, 64, 2))
    write(
        fixture / "esp_ota_ops.h",
        (
            "#pragma once\n#include <cstdint>\n"
            "struct esp_app_desc_t { uint8_t app_elf_sha256[32]; };\n"
            "inline const esp_app_desc_t* esp_ota_get_app_description(){ "
            "static esp_app_desc_t d={{" + values + "}}; return &d; }\n"
        ).encode(),
    )
    # Fake GPIO model is explicit and keeps all non-BUSY outputs low; never hardware observations.
    p = fixture / "Arduino.h"
    s = p.read_text(encoding="utf-8")
    assert "inline int digitalRead(int) { return 1; }" in s
    s = s.replace(
        "inline int digitalRead(int) { return 1; }",
        "extern int busy; inline int digitalRead(int pin) { return pin==4?busy:0; }",
    )
    p.write_text(s, encoding="utf-8")
    macro = re.search(
        r"#ifndef (MF1750_LH3_SOURCE_WHITE_V\d+_BUILD)",
        main_cpp.read_text(encoding="utf-8"),
    )[1]
    write(
        OUT / "config.hpp",
        (
            "#define asm(...)\n"
            'extern "C" const char kTransactionDescriptorMarker[] = '
            + json.dumps(contract["compiled_marker"])
            + ";\n#define SOURCE_MAIN_PATH "
            + json.dumps(main_cpp.as_posix())
            + "\n"
        ).encode(),
    )
    write(OUT / "protocol.cpp", PROTOCOL_CPP.encode())
    cl, env, msvc = compiler_environment()
    assert msvc, "MSVC toolchain required"
    exe = OUT / "protocol.exe"
    cmd = [
        cl,
        "/nologo",
        "/std:c++17",
        "/EHsc",
        "/utf-8",
        "/D_CRT_SECURE_NO_WARNINGS",
        "/D_ALLOW_KEYWORD_MACROS=1",
        "/D" + macro + "=1",
        "/DMF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1",
        "/DMF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1",
        "/DEPD_ENABLE_TEST_PATTERN=0",
        "/DMF1750_PURE_FIELD_WHITE=1",
        "/FI" + str(OUT / "config.hpp"),
        "/I" + str(fixture),
        str(OUT / "protocol.cpp"),
        "/Fe:" + str(exe),
        "/Fo:" + str(OUT / "protocol.obj"),
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, cwd=OUT)
    write(OUT / "compile.stdout", r.stdout)
    write(OUT / "compile.stderr", r.stderr)
    if r.returncode:
        raise RuntimeError("native compile failed " + str(r.returncode))
    cases = {}
    failures = []
    for case, number in EXPECTED.items():
        r = subprocess.run([str(exe), case], capture_output=True, cwd=OUT)
        write(OUT / (case + ".raw.tsv"), r.stdout)
        write(OUT / (case + ".stderr"), r.stderr)
        documents = []
        errors = []
        for i, line in enumerate(r.stdout.decode("utf-8").splitlines(), 1):
            try:
                label, status, body = line.split("\t", 2)
                d = json.loads(
                    body,
                    object_pairs_hook=unique,
                    parse_constant=lambda v: (_ for _ in ()).throw(
                        ValueError("invalid number " + v)
                    ),
                )
                assert isinstance(d, dict), "non-object JSON"
                if "contract_id" in d:
                    assert d["contract_id"] == contract["contract_id"], "wrong contract"
                    assert d["profile_id"] == contract["profile_id"], "wrong profile"
                    assert d["running_app_elf_sha256"] == elf["sha256"], (
                        "wrong running ELF"
                    )
                    assert d["source_main_contract_id"] == contract[
                        "source_contract_id"
                    ], "wrong source contract"
                documents.append(
                    {
                        "label": label,
                        "status": int(status),
                        "json": d,
                        "raw_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    }
                )
            except Exception as e:
                errors.append({"line": i, "error": str(e)})
        if len(documents) != number:
            errors.append(
                {"expected_documents": number, "actual_documents": len(documents)}
            )
        if r.returncode:
            errors.append(
                {
                    "exit_code": r.returncode,
                    "stderr": r.stderr.decode("utf-8", errors="replace"),
                }
            )
        if case == "all" and len(documents) == 7:
            first = documents[0]["json"]
            if not (
                first.get("source_terminal_gate_pass") is True
                and first.get("source_observed_cursor_raw") == 4
                and first.get("source_observed_boot_nonce") == "ac92bb9e25c374ef"
                and first.get("old_fault_cursor_raw") == 770
                and first.get("rebound_v2_cursor_raw") == 4
                and first.get("lh2_white_used_cursor_raw") == 2
                and first.get("main_nvs_clear_route") is False
            ):
                errors.append({"error": "source terminal gate diagnostic mismatch"})
            last = documents[-1]["json"]
            if not (
                last.get("terminal_state") == "COMPLETE"
                and last.get("driver_call_count_for_action")
                == last.get("total_driver_call_count")
                == 1
                and last.get("next_ordinal") == 2
            ):
                errors.append({"error": "terminal facts mismatch"})
        cases[case] = {
            "result": "PASS" if not errors else "FAIL_STOP",
            "expected_documents": number,
            "parsed_documents": len(documents),
            "raw": sha(OUT / (case + ".raw.tsv")),
            "errors": errors,
            "documents": documents,
        }
        if errors:
            failures.append(case)
    assert sha(main_cpp) == authority_before, "authoritative source changed"
    review = {
        "schema_version": 1,
        "kind": "mf1750-lh3-source-white-strict-native-v1",
        "result": "PASS" if not failures else "FAIL_STOP",
        "hardware_accessed": False,
        "network_accessed": False,
        "visible_refreshes": 0,
        "qualified_count": 0,
        "native_driver_stub": True,
        "physical_refreshes_represented_by_stub": 0,
        "live_authorization_granted": False,
        "package": str(PKG),
        "contract": sha(PKG / "contract.json"),
        "build_report": sha(PKG / "build-report.json"),
        "authoritative_main": authority_before,
        "authoritative_main_compiled_without_edits": True,
        "firmware_artifacts": build["artifacts"],
        "source_terminal_gate": contract["source_terminal_gate"],
        "old_fault_preservation": contract["old_fault_preservation"],
        "rebound_v2_preservation": contract["rebound_v2_preservation"],
        "lh2_white_preservation": contract["lh2_white_preservation"],
        "native_fixture_files": [sha(p) for p in sorted(fixture.glob("*.h"))],
        "native_harness": sha(OUT / "protocol.cpp"),
        "native_config": sha(OUT / "config.hpp"),
        "desktop_asm_substitution": "GCC asm marker ignored by macro and replaced with same contract marker C string; original main/identity unchanged",
        "native_audit_source": sha(Path(__file__)),
        "native_binary": sha(exe),
        "successful_sequence_expected_documents": 7,
        "successful_sequence_parsed_documents": cases["all"]["parsed_documents"],
        "scenario_count": len(cases),
        "total_parsed_documents": sum(c["parsed_documents"] for c in cases.values()),
        "failed_scenarios": failures,
        "cases": cases,
        "limits": [
            "MSVC compiles actual frozen generated main with desktop Arduino/Preferences/WebServer/WiFi/GPIO substitutes. No HTTP sockets, serial or GPIO hardware accessed.",
            "Driver body is a desktop stub; compilation and JSON/state-machine tests do not prove physical driver waveforms, timing, electrical or optical validity.",
            "All raw responses must parse fully with duplicate-key rejection; literal trailing backslash-n is not stripped or accepted.",
            "Firmware source gate only proves the exact stored LH2 drive-map terminal pair (lh2map_v1 cur_lh2m=4, boot_lh2m=0xac92bb9e25c374ef) with the three older namespaces (lhist_v1 cur_lh1=770 / boot_lh1=0x30a9e5989873f4e0, lh1reb_v2 cur_lh1r=4 / boot_lh1r=0x7274e005c8833ca1, lh2srcw_v1 used_lh2sw1=2) preserved; physical source campaign completion remains independently evidenced by the host-side terminal claim/result bound in the contract.",
        ],
    }
    review["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(canon(review)).hexdigest(),
    }
    write(
        OUT / "strict-native-audit.json",
        json.dumps(review, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n",
    )
    print(
        json.dumps(
            {
                "result": review["result"],
                "cases": len(cases),
                "all_parsed": cases["all"]["parsed_documents"],
                "total_parsed": review["total_parsed_documents"],
                "failed": {c: cases[c]["errors"] for c in failures},
                "file": sha(OUT / "strict-native-audit.json"),
            },
            indent=2,
        )
    )
    return review["result"] == "PASS"


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
