#!/usr/bin/env python3
"""Offline candidate for one-shot white containment after the LH1 MIDDLE fault.

This generator never accesses hardware, sockets, serial, relay or camera.  It
derives the frozen R5 factory white driver and adds an exact, read-only source
fault gate (boot_lh1=30a9e5989873f4e0, cur_lh1=770).  The main campaign is never
resumed and the successor namespace ``lh1srcw_v1/used_lh1sw1`` is shared with
R5, so this creates no additional refresh budget.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lightness_history_firmware as main_pack
from tools import mf1750_lh1_lh4_firmware as binding
from tools import mf1750_lh1_source_white_firmware_v5 as r5

ROOT = main_pack.ROOT
R5 = ROOT / ".test-output/offline/LH1_SOURCE_WHITE_20260913_R5"
DEFAULT_OUTPUT = ROOT / ".test-output/offline/LH1_MIDDLE_FAULT_WHITE_20260913_R1"
CAMPAIGN = "EC5_LH1_MIDDLE_FAULT_WHITE_V1_20260914"
BASE = "/api/ec5/lh1-middle-fault-white-v1"
EXPECTED_BOOT = "30a9e5989873f4e0"
EXPECTED_CURSOR = 770
FAULT_STATUS_SHA = "30873f87838b60d74a9e46b80a0b2456d271bbb95a48310d5a5c5263f4e86d0c"
FAULT_REPORT_SHA = "25bd5fa7a4effc0711449fb28435e77df12ac5ab33df99efa3dd6565a0e5abd7"
ARM_REJECT_SHA = "97256b3e474960b5aa15af60eb755f1a3d946cd9336971af69858d6ab74c247b"
SOURCE_RECON_SHA = "f2284a7a571a38cf78f61bf3c5850aa266623ff755a7d735b6d633cb354970a9"
MIDDLE_BINDING_SHA = "b2dd152ae5e60777d6ebf0298a51fcbfed47e26ac77e0955f58781b20856aacc"

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def canonical(v: dict) -> bytes: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def bind(path: Path) -> dict: return main_pack.bind(path)
def seal(v: dict) -> dict: return {**v, "integrity": {"algorithm":"sha256-canonical-json-without-integrity", "sha256":sha(canonical(v))}}
def write_new(path: Path, value):
    data = canonical(value)+b"\n" if isinstance(value,dict) else value.encode() if isinstance(value,str) else value
    with path.open("xb") as f: f.write(data); f.flush(); os.fsync(f.fileno())

def render():
    if not (R5 / "contract.json").exists(): raise FileNotFoundError(R5 / "contract.json")
    r5_contract = json.loads((R5 / "contract.json").read_text(encoding="utf-8"))
    r5_manifest = binding.read_sealed(R5 / "manifest.json")
    r5_build = json.loads((R5 / "build-report.json").read_text(encoding="utf-8"))
    if r5_contract["successor_nvs"] != {"namespace":"lh1srcw_v1","cursor_key":"used_lh1sw1","initial_cursor":1,"complete_cursor":2}:
        raise ValueError("R5 successor NVS contract changed")
    if r5_build.get("result") != "PASS": raise ValueError("R5 build is not PASS")
    source = r5_contract["source_contract_id"]
    contract = {
        "kind":"mf1750-lh1-middle-fault-white-containment-contract-v1",
        "campaign_id":CAMPAIGN, "source_campaign_id":"EC5_LIGHTNESS_HISTORY_LH4_V1_20260912",
        "source_contract_id":source, "source_action_id":r5_contract["source_action_id"],
        "source_terminal_required":"SOURCE ordinal 1 COMPLETE evidence plus exact MIDDLE ARM rejection; no driver dispatch",
        "source_fault_gate":{"namespace":"lhist_v1","cursor_key":"cur_lh1","expected_cursor_raw":EXPECTED_CURSOR,"boot_key":"boot_lh1","expected_boot_nonce":EXPECTED_BOOT},
        "source_evidence":{"terminal_reconciliation_sha256":SOURCE_RECON_SHA,"middle_binding_sha256":MIDDLE_BINDING_SHA,"fault_status_body_sha256":FAULT_STATUS_SHA,"fault_report_body_sha256":FAULT_REPORT_SHA,"arm_rejection_body_sha256":ARM_REJECT_SHA,"arm_rejection_error":"prior_review_cannot_reuse_white","middle_driver_call_count":0,"middle_visible_refresh_count":0},
        "successor_nvs":r5_contract["successor_nvs"], "profile_id":r5_contract["profile_id"],
        "frame_sha256":r5_contract["frame_sha256"], "dtm_sha256":r5_contract["dtm_sha256"],
        "r5_contract":bind(R5/"contract.json"), "r5_manifest":bind(R5/"manifest.json"),
        "r5_build":bind(R5/"build-report.json"), "r5_firmware":bind(R5/"build/lh1sw/firmware.bin"), "r5_elf":bind(R5/"build/lh1sw/firmware.elf"),
        "driver_body_unchanged_from_r5":True, "waveform_internal_phase":"OPAQUE",
        "runtime_payload":False,"electrical_parameter_ingress":False,"timing_parameter_ingress":False,
        "retry":False,"automatic_recovery":False,"main_resume_after_recovery":False,
        "no_main_nvs_clear_route":True,"live_action_authorized":False,"qualified_count":0,
        "generator":bind(Path(__file__)),
    }
    contract["contract_id"] = sha(canonical(contract))
    contract["descriptor_id"] = sha(canonical({"contract":contract["contract_id"],"role":"LH1_MIDDLE_FAULT_WHITE_CONTAINMENT","profile":contract["profile_id"],"source_cursor":EXPECTED_CURSOR}))
    contract["action_id"] = sha(canonical({"descriptor":contract["descriptor_id"],"ordinal":1,"source_fault_cursor":EXPECTED_CURSOR}))
    contract["compiled_marker"] = "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=LH1_MIDDLE_FAULT_WHITE_CONTAINMENT|SHA256="+contract["descriptor_id"]
    ident = (R5/"generated/identity.inc").read_text(encoding="utf-8")
    vals={"kEnvironmentId":"lh1_middle_fault_white_v1","kCampaignId":CAMPAIGN,"kBuildTag":"MF1750_EC5_LH1_MIDDLE_FAULT_WHITE_V1_2026-09-14","kContractId":contract["contract_id"],"kDescriptorId":contract["descriptor_id"],"kActionId":contract["action_id"]}
    for k,v in vals.items():
        ident,n = re.subn(r'(static constexpr const char \*'+k+r'\s*=\s*)"[^"]*";', lambda m:m[1]+json.dumps(v)+";", ident)
        if n != 1: raise ValueError("identity anchor: "+k)
    ident = ident.replace("after LH1 SOURCE ordinal-1", "after LH1 MIDDLE fault containment")
    ident = ident.replace("MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE|SHA256="+r5_contract["descriptor_id"], contract["compiled_marker"])
    main = (R5/"generated/main.cpp").read_text(encoding="utf-8")
    for a,b in (("MF1750_LH1_SOURCE_WHITE_V5_BUILD","MF1750_LH1_MIDDLE_FAULT_WHITE_V1_BUILD"),("LH1 SOURCE","LH1 MIDDLE FAULT"),("lh1-source-white-v1","lh1-middle-fault-white-v1"),("lh1_source_white_v1","lh1_middle_fault_white_v1"),("LH1_SOURCE_V1","LH1_MIDDLE_FAULT_V1"),("SOURCE_WHITE_V5","MIDDLE_FAULT_WHITE_V1"),("OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE","LH1_MIDDLE_FAULT_WHITE_CONTAINMENT"),("FACTORY_OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE_ONE_ACTION_NO_RUNTIME_PAYLOAD","LH1_MIDDLE_FAULT_WHITE_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"),("used_lh1sw1","used_lh1sw1")):
        main = main.replace(a,b)
    main = main.replace("static constexpr uint8_t kActionOrdinal = 1;", "static constexpr uint8_t kActionOrdinal = 1;")
    old_gate = re.search(r'// Necessary NVS guard\. Host still validates exact source terminal/action/claim\.\nbool sourceOrdinalOneComplete\(\) \{.*?\n\}\n', main, re.S)
    if not old_gate: raise ValueError("source gate missing")
    gate = '''// Exact containment gate: preserves main lhist_v1 and admits only the recorded fault.
bool sourceFaultContainmentExact() {
  Preferences source;
  if (!source.begin("lhist_v1", true)) return false;
  const bool ok = source.isKey("cur_lh1") && source.getUShort("cur_lh1",0)==770 &&
                  source.isKey("boot_lh1") && source.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL;
  source.end();
  return ok;
}
'''
    main = main[:old_gate.start()] + gate + main[old_gate.end():]
    main = main.replace("sourceOrdinalOneComplete()", "sourceFaultContainmentExact()")
    # The source fault fields are observed at runtime, never static assertions.
    main = main.replace(r'\"source_main_completed_lh1_source_only\":true,', r'\"source_main_completed_lh1_source_only\":false,')
    main = main.replace(r'\"source_main_resume_forbidden_after_containment\":true,', r'\"source_main_resume_forbidden_after_containment\":true,\"main_nvs_clear_route\":false,')
    diag = '''String sourceFaultDiagnosticJson() {
  Preferences source;
  bool opened = source.begin("lhist_v1", true);
  bool cursorPresent = opened && source.isKey("cur_lh1");
  bool bootPresent = opened && source.isKey("boot_lh1");
  uint16_t observedCursor = cursorPresent ? source.getUShort("cur_lh1", 0) : 0;
  uint64_t observedBoot = bootPresent ? source.getULong64("boot_lh1", 0) : 0;
  if (opened) source.end();
  char bootText[17] = {};
  snprintf(bootText, sizeof(bootText), "%016llx", (unsigned long long)observedBoot);
  const bool gate = cursorPresent && bootPresent && observedCursor == 770 && observedBoot == 0x30a9e5989873f4e0ULL;
  return String(",\\\"source_nvs_namespace\\\":\\\"lhist_v1\\\",\\\"source_cursor_key_present\\\":") + (cursorPresent ? "true" : "false") +
         ",\\\"source_boot_key_present\\\":" + (bootPresent ? "true" : "false") +
         ",\\\"source_observed_cursor_raw\\\":" + String(observedCursor) +
         ",\\\"source_observed_boot_nonce\\\":\\\"" + bootText +
         "\\\",\\\"source_fault_gate_pass\\\":" + (gate ? "true" : "false") +
         ",\\\"source_fault_expected_cursor_raw\\\":770,\\\"source_fault_expected_boot_nonce\\\":\\\"30a9e5989873f4e0\\\"";
}
'''
    main = main.replace('String identityJson() {', diag + '\nString identityJson() {', 1)
    main = main.replace('         kTransactionDescriptorMarker + "\\\"";', '         kTransactionDescriptorMarker + "\\\"" + sourceFaultDiagnosticJson();', 1)
    return seal(contract), {"main.cpp":main,"identity.inc":ident,"driver.cpp":'#include <SPI.h>\n#include "frozen_epd_driver.cpp.inc"\n'}

def prepare(out: Path):
    contract, src = render(); out=out.resolve(); out.mkdir(parents=True,exist_ok=False); gen=out/"generated"; gen.mkdir()
    for n,c in src.items(): write_new(gen/n,c)
    write_new(gen/"frozen_epd_driver.cpp.inc", (R5/"generated/frozen_epd_driver.cpp.inc").read_bytes())
    write_new(out/"contract.json",contract)
    cfg=(ROOT/"platformio.lhr4.ini").read_text(encoding="utf-8").replace("lhr4","lh1mw").replace(".pio/br_lh1mw", out.relative_to(ROOT).as_posix()+"/build").replace(".pio/g_lh1mw", out.relative_to(ROOT).as_posix()+"/generated")
    cfg=cfg.replace("ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_epd_driver.cpp","driver.cpp").replace("ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp","main.cpp").replace("MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_BUILD","MF1750_LH1_MIDDLE_FAULT_WHITE_V1_BUILD").replace("MF1750_LH1_SOURCE_WHITE_V5_BUILD","MF1750_LH1_MIDDLE_FAULT_WHITE_V1_BUILD")
    write_new(out/"platformio.ini",cfg)
    inputs=[bind(p) for p in sorted((ROOT/"src").rglob("*")) if p.is_file() and p.suffix in (".h",".hpp",".inc",".cpp")]
    inputs += [bind(Path(__file__)),bind(R5/"contract.json"),bind(R5/"manifest.json"),bind(R5/"build-report.json"),bind(R5/"build/lh1sw/firmware.bin"),bind(R5/"build/lh1sw/firmware.elf"),bind(ROOT/"platformio.lhr4.ini")]
    outputs=[bind(p) for p in sorted(out.rglob("*")) if p.is_file()]
    write_new(out/"manifest.json",seal({"kind":"mf1750-lh1-middle-fault-white-package-v1","inputs":inputs,"outputs":outputs,"contract_id":contract["contract_id"],"live_ready":False,"hardware_accessed":False}))
    return {"result":"PASS","output":str(out),"contract_id":contract["contract_id"],"live_ready":False,"hardware_accessed":False}

def verify(out: Path):
    m=binding.read_sealed(out/"manifest.json")
    for x in m["inputs"]+m["outputs"]:
        if bind(Path(x["path"])) != x: raise ValueError("sealed file differs: "+x["path"])
    return binding.read_sealed(out/"contract.json")

def build(out: Path):
    c=verify(out); out=out.resolve(); (out/"build").mkdir(exist_ok=False)
    pio=shutil.which("pio") or str(Path.home()/".platformio/penv/Scripts/pio.exe")
    with (out/"build.log").open("xb") as f:
        rc=subprocess.run([pio,"run","-c",str(out/"platformio.ini")],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,"PLATFORMIO_SETTING_ENABLE_TELEMETRY":"no","PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL":"0"}).returncode
    if rc: raise RuntimeError("compile failed")
    arts=[bind(out/"build/lh1mw"/n) for n in ("firmware.bin","firmware.elf")]
    rec=seal({"kind":"mf1750-lh1-middle-fault-white-build-v1","result":"PASS","recorded_at":datetime.now(timezone.utc).isoformat(),"contract":bind(out/"contract.json"),"manifest":bind(out/"manifest.json"),"artifacts":arts,"hardware_accessed":False,"visible_refreshes":0,"live_ready":False,"qualified_count":0})
    write_new(out/"build-report.json",rec); return rec

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("command",choices=("prepare","verify","build")); ap.add_argument("--output-dir",type=Path,default=DEFAULT_OUTPUT); a=ap.parse_args(); o=a.output_dir.resolve(); r=prepare(o) if a.command=="prepare" else verify(o) if a.command=="verify" else build(o); print(json.dumps(r,ensure_ascii=False,indent=2))
