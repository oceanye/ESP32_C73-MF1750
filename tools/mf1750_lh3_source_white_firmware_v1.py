#!/usr/bin/env python3
"""Offline candidate: one-shot factory-OTP white after the LH2 drive-map chain.

This generator never accesses hardware, sockets, serial, relay or camera. It
derives the frozen R5 factory white sources and adds an exact, read-only source
gate: the LH2 drive-map campaign terminal (lh2map_v1 cur_lh2m=4, boot
ac92bb9e25c374ef) must be present and the three older namespaces must remain
untouched: the old fault namespace (lhist_v1 cur_lh1=770,
boot_lh1=30a9e5989873f4e0), the rebound V2 namespace (lh1reb_v2 cur_lh1r=4,
boot_lh1r=7274e005c8833ca1) and the consumed LH2 white marker
(lh2srcw_v1 used_lh2sw1=2). The successor uses its own namespace
lh3srcw_v1/used_lh3sw1: this is a new white action with its own
single-refresh budget, not shared with any historical white.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lightness_history_firmware as main_pack
from tools import mf1750_lh1_lh4_firmware as binding
from tools import mf1750_lh2_drive_map_once_v1 as lh2map

ROOT = main_pack.ROOT
R5 = ROOT / ".test-output/offline/LH1_SOURCE_WHITE_20260913_R5"
DEFAULT_OUTPUT = ROOT / ".test-output/offline/LH3_SOURCE_WHITE_20260918_R1"
CAMPAIGN = "EC5_LH3_SOURCE_WHITE_V1_20260918"
BASE = "/api/ec5/lh3-source-white-v1"
EXPECTED_MAP_BOOT = "ac92bb9e25c374ef"
EXPECTED_MAP_CURSOR = 4
EXPECTED_REBOUND_BOOT = "7274e005c8833ca1"
EXPECTED_REBOUND_CURSOR = 4
EXPECTED_OLD_FAULT_BOOT = "30a9e5989873f4e0"
EXPECTED_OLD_FAULT_CURSOR = 770
EXPECTED_LH2_WHITE_USED_CURSOR = 2
MAP_RESULT = ROOT / ".test-output/hardware/LH2_DRIVE_MAP_20260918_V1/live-s3/result.json"
MAP_CLAIM = ROOT / ".test-output/hardware/.mf1750_lh2_drive_map_action_claims/be45e5a14e4634e49a1cbf4a1713002e8ee046d13fffe8934453cec30348a8a6-ordinal3.json"
WHITE_CLOSE_REVIEW = ROOT / ".test-output/hardware/LH2_SOURCE_WHITE_20260918_V1/close-review-v1.json"

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def canonical(v) -> bytes: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def bind(path: Path) -> dict: return main_pack.bind(path)
def seal(v: dict) -> dict: return {**v, "integrity": {"algorithm": "sha256-canonical-json-without-integrity", "sha256": sha(canonical(v))}}
def write_new(path: Path, value):
    data = canonical(value)+b"\n" if isinstance(value, dict) else value.encode() if isinstance(value, str) else value
    with path.open("xb") as f: f.write(data); f.flush(); os.fsync(f.fileno())


def render():
    if not (R5 / "contract.json").exists(): raise FileNotFoundError(R5 / "contract.json")
    ctx = lh2map.validate_package()
    lh2 = ctx["contract"]
    if lh2["actions"][2]["ordinal"] != 3 or lh2["actions"][2]["stage"] != "MAP":
        raise ValueError("LH2 contract MAP action differs")
    # Pin the expected terminal pair to the sealed field evidence, not to memory.
    claim = json.loads(MAP_CLAIM.read_bytes())
    result = json.loads(MAP_RESULT.read_bytes())
    if claim.get("contract_id") != lh2["contract_id"] or result.get("contract_id") != lh2["contract_id"]:
        raise ValueError("LH2 terminal evidence contract differs")
    if claim.get("ordinal") != 3 or claim.get("action_id") != lh2["actions"][2]["action_id"]:
        raise ValueError("LH2 MAP claim differs")
    if claim.get("boot_nonce") != EXPECTED_MAP_BOOT or result.get("boot_nonce") != EXPECTED_MAP_BOOT:
        raise ValueError("LH2 MAP terminal boot differs")
    if result.get("protocol_verdict") != "PASS" or result.get("campaign_complete") is not True:
        raise ValueError("LH2 MAP terminal is not complete")
    r5_contract = json.loads((R5 / "contract.json").read_text(encoding="utf-8"))
    r5_build = json.loads((R5 / "build-report.json").read_text(encoding="utf-8"))
    if r5_build.get("result") != "PASS": raise ValueError("R5 build is not PASS")
    contract = {
        "kind": "mf1750-lh3-source-white-contract-v1",
        "campaign_id": CAMPAIGN,
        "source_campaign_id": lh2["campaign_id"],
        "source_contract_id": lh2["contract_id"],
        "source_action_id": lh2["actions"][2]["action_id"],
        "accepted_source_ordinals": [3],
        "source_terminal_required": "exact LH2 drive map MAP ordinal 3 COMPLETE (campaign complete, cursor_raw=4); reject any other state",
        "source_terminal_gate": {"namespace": "lh2map_v1", "cursor_key": "cur_lh2m",
            "expected_cursor_raw": EXPECTED_MAP_CURSOR, "boot_key": "boot_lh2m",
            "expected_boot_nonce": EXPECTED_MAP_BOOT},
        "old_fault_preservation": {"namespace": "lhist_v1", "cursor_key": "cur_lh1",
            "expected_cursor_raw": EXPECTED_OLD_FAULT_CURSOR, "boot_key": "boot_lh1",
            "expected_boot_nonce": EXPECTED_OLD_FAULT_BOOT, "must_remain_untouched": True},
        "rebound_v2_preservation": {"namespace": "lh1reb_v2", "cursor_key": "cur_lh1r",
            "expected_cursor_raw": EXPECTED_REBOUND_CURSOR, "boot_key": "boot_lh1r",
            "expected_boot_nonce": EXPECTED_REBOUND_BOOT, "must_remain_untouched": True},
        "lh2_white_preservation": {"namespace": "lh2srcw_v1", "cursor_key": "used_lh2sw1",
            "expected_cursor_raw": EXPECTED_LH2_WHITE_USED_CURSOR, "must_remain_untouched": True},
        "source_terminal_evidence": {
            "map_claim": bind(MAP_CLAIM),
            "map_result": bind(MAP_RESULT),
            "white_close_review": bind(WHITE_CLOSE_REVIEW)},
        "successor_nvs": {"namespace": "lh3srcw_v1", "cursor_key": "used_lh3sw1", "initial_cursor": 1, "complete_cursor": 2},
        "profile_id": r5_contract["profile_id"],
        "frame_sha256": r5_contract["frame_sha256"], "dtm_sha256": r5_contract["dtm_sha256"],
        "lh2_contract": bind(lh2map.PACKAGE / "contract.json"),
        "lh2_manifest": bind(lh2map.PACKAGE / "manifest.json"),
        "lh2_firmware": ctx["firmware"], "lh2_elf": ctx["elf"],
        "r5_contract": bind(R5 / "contract.json"), "r5_manifest": bind(R5 / "manifest.json"),
        "r5_build": bind(R5 / "build-report.json"),
        "driver_body_unchanged_from_r5": True, "waveform_internal_phase": "OPAQUE",
        "runtime_payload": False, "electrical_parameter_ingress": False, "timing_parameter_ingress": False,
        "retry": False, "automatic_recovery": False, "main_resume_after_recovery": False,
        "no_main_nvs_clear_route": True, "live_action_authorized": False, "qualified_count": 0,
        "generator": bind(Path(__file__)),
    }
    contract["contract_id"] = sha(canonical(contract))
    contract["descriptor_id"] = sha(canonical({"contract": contract["contract_id"], "role": "LH3_PRE_WHITE", "profile": contract["profile_id"], "source_cursor": EXPECTED_MAP_CURSOR}))
    contract["action_id"] = sha(canonical({"descriptor": contract["descriptor_id"], "ordinal": 1, "source_terminal_cursor": EXPECTED_MAP_CURSOR}))
    contract["compiled_marker"] = "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LH2_DRIVE_MAP_COMPLETE|SHA256=" + contract["descriptor_id"]
    ident = (R5 / "generated/identity.inc").read_text(encoding="utf-8")
    vals = {"kEnvironmentId": "lh3_source_white_v1", "kCampaignId": CAMPAIGN,
        "kSourceCampaignId": lh2["campaign_id"],
        "kSourceMainContractId": lh2["contract_id"],
        "kSourceMainOfflineBuildSha256": sha((lh2map.PACKAGE / "build-report.json").read_bytes()),
        "kBuildTag": "MF1750_EC5_LH3_SOURCE_WHITE_V1_2026-09-18",
        "kContractId": contract["contract_id"], "kDescriptorId": contract["descriptor_id"],
        "kActionId": contract["action_id"], "kNvsNamespace": "lh3srcw_v1",
        "kAcceptedSourceActionsSha256": sha(canonical(lh2["actions"][2])),
        "kSourceFirmwareBinSha256": ctx["firmware"]["sha256"],
        "kSourceFirmwareElfSha256": ctx["elf"]["sha256"]}
    for k, v in vals.items():
        ident, n = re.subn(r'(static constexpr const char \*' + k + r'\s*=\s*)"[^"]*";', lambda m: m[1] + json.dumps(v) + ";", ident)
        if n != 1: raise ValueError("identity anchor: " + k)
    ident = ident.replace("after LH1 SOURCE ordinal-1", "after LH2 drive-map MAP ordinal-3 campaign-complete")
    ident = ident.replace("MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE|SHA256=" + r5_contract["descriptor_id"], contract["compiled_marker"])
    main = (R5 / "generated/main.cpp").read_text(encoding="utf-8")
    for a, b in (("MF1750_LH1_SOURCE_WHITE_V5_BUILD", "MF1750_LH3_SOURCE_WHITE_V1_BUILD"),
                 ("FACTORY_OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE_ONE_ACTION_NO_RUNTIME_PAYLOAD", "FACTORY_OTP_WHITE_AFTER_LH2_DRIVE_MAP_COMPLETE_ONE_ACTION_NO_RUNTIME_PAYLOAD"),
                 ("LH1 SOURCE", "LH3 PRE-WHITE"),
                 ("lh1-source-white-v1", "lh3-source-white-v1"),
                 ("LH1_SOURCE_V1", "LH3_SOURCE_V1"),
                 ("EC5-LH1-SOURCE-WHITE-V1", "EC5-LH3-SOURCE-WHITE-V1"),
                 (r'\"source_main_nvs_boot_key\":\"boot_lh1\",', r'\"source_main_nvs_boot_key\":\"boot_lh2m\",'),
                 ('"used_lh1sw1"', '"used_lh3sw1"')):
        if a not in main: raise ValueError("rename anchor missing: " + a)
        main = main.replace(a, b)
    old_gate = re.search(r'// Necessary NVS guard\. Host still validates exact source terminal/action/claim\.\nbool sourceOrdinalOneComplete\(\) \{.*?\n\}\n', main, re.S)
    if not old_gate: raise ValueError("source gate missing")
    gate = '''// Exact terminal gate: LH2 drive-map campaign complete; three older namespaces untouched.
bool lh2DriveMapTerminalComplete() {
  Preferences oldFault;
  if (!oldFault.begin("lhist_v1", true)) return false;
  const bool oldOk = oldFault.isKey("cur_lh1") && oldFault.getUShort("cur_lh1",0)==770 &&
                     oldFault.isKey("boot_lh1") && oldFault.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL;
  oldFault.end();
  if (!oldOk) return false;
  Preferences rebound;
  if (!rebound.begin("lh1reb_v2", true)) return false;
  const bool rebOk = rebound.isKey("cur_lh1r") && rebound.getUShort("cur_lh1r",0)==4 &&
                     rebound.isKey("boot_lh1r") && rebound.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL;
  rebound.end();
  if (!rebOk) return false;
  Preferences white;
  if (!white.begin("lh2srcw_v1", true)) return false;
  const bool whiteOk = white.isKey("used_lh2sw1") && white.getUShort("used_lh2sw1",0)==2;
  white.end();
  if (!whiteOk) return false;
  Preferences source;
  if (!source.begin("lh2map_v1", true)) return false;
  const bool ok = source.isKey("cur_lh2m") && source.getUShort("cur_lh2m",0)==4 &&
                  source.isKey("boot_lh2m") && source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL;
  source.end();
  return ok;
}
'''
    main = main[:old_gate.start()] + gate + main[old_gate.end():]
    main = main.replace("sourceOrdinalOneComplete()", "lh2DriveMapTerminalComplete()")
    main = main.replace(r'\"source_main_completed_lh1_source_only\":true,', r'\"source_main_completed_lh1_source_only\":false,')
    main = main.replace(r'\"source_main_resume_forbidden_after_containment\":true,', r'\"source_main_resume_forbidden_after_containment\":true,\"main_nvs_clear_route\":false,')
    diag = '''String lh2MapDiagnosticJson() {
  Preferences oldFault;
  bool oldOpened = oldFault.begin("lhist_v1", true);
  bool oldCursorPresent = oldOpened && oldFault.isKey("cur_lh1");
  bool oldBootPresent = oldOpened && oldFault.isKey("boot_lh1");
  uint16_t oldCursor = oldCursorPresent ? oldFault.getUShort("cur_lh1", 0) : 0;
  uint64_t oldBoot = oldBootPresent ? oldFault.getULong64("boot_lh1", 0) : 0;
  if (oldOpened) oldFault.end();
  Preferences rebound;
  bool rebOpened = rebound.begin("lh1reb_v2", true);
  uint16_t rebCursor = rebOpened && rebound.isKey("cur_lh1r") ? rebound.getUShort("cur_lh1r", 0) : 0;
  uint64_t rebBoot = rebOpened && rebound.isKey("boot_lh1r") ? rebound.getULong64("boot_lh1r", 0) : 0;
  if (rebOpened) rebound.end();
  Preferences white;
  bool whiteOpened = white.begin("lh2srcw_v1", true);
  uint16_t whiteUsed = whiteOpened && white.isKey("used_lh2sw1") ? white.getUShort("used_lh2sw1", 0) : 0;
  if (whiteOpened) white.end();
  Preferences source;
  bool opened = source.begin("lh2map_v1", true);
  bool cursorPresent = opened && source.isKey("cur_lh2m");
  bool bootPresent = opened && source.isKey("boot_lh2m");
  uint16_t observedCursor = cursorPresent ? source.getUShort("cur_lh2m", 0) : 0;
  uint64_t observedBoot = bootPresent ? source.getULong64("boot_lh2m", 0) : 0;
  if (opened) source.end();
  char bootText[17] = {};
  snprintf(bootText, sizeof(bootText), "%016llx", (unsigned long long)observedBoot);
  const bool gate = oldCursorPresent && oldBootPresent && oldCursor == 770 &&
                    oldBoot == 0x30a9e5989873f4e0ULL &&
                    rebCursor == 4 && rebBoot == 0x7274e005c8833ca1ULL &&
                    whiteUsed == 2 && cursorPresent && bootPresent &&
                    observedCursor == 4 && observedBoot == 0xac92bb9e25c374efULL;
  return String(",\\"source_nvs_namespace\\":\\"lh2map_v1\\",\\"source_cursor_key_present\\":") + (cursorPresent ? "true" : "false") +
         ",\\"source_boot_key_present\\":" + (bootPresent ? "true" : "false") +
         ",\\"source_observed_cursor_raw\\":" + String(observedCursor) +
         ",\\"source_observed_boot_nonce\\":\\"" + bootText +
         "\\",\\"old_fault_cursor_raw\\":" + String(oldCursor) +
         ",\\"rebound_v2_cursor_raw\\":" + String(rebCursor) +
         ",\\"lh2_white_used_cursor_raw\\":" + String(whiteUsed) +
         ",\\"source_terminal_gate_pass\\":" + (gate ? "true" : "false") +
         ",\\"source_terminal_expected_cursor_raw\\":4,\\"source_terminal_expected_boot_nonce\\":\\"ac92bb9e25c374ef\\"";
}
'''
    main = main.replace('String identityJson() {', diag + '\nString identityJson() {', 1)
    main = main.replace('         kTransactionDescriptorMarker + "\\\"";', '         kTransactionDescriptorMarker + "\\\"" + lh2MapDiagnosticJson();', 1)
    return seal(contract), {"main.cpp": main, "identity.inc": ident,
        "driver.cpp": '#include <SPI.h>\n#include "frozen_epd_driver.cpp.inc"\n'}


def prepare(out: Path):
    contract, src = render(); out = out.resolve(); out.mkdir(parents=True, exist_ok=False); gen = out / "generated"; gen.mkdir()
    for n, c in src.items(): write_new(gen / n, c)
    write_new(gen / "frozen_epd_driver.cpp.inc", (R5 / "generated/frozen_epd_driver.cpp.inc").read_bytes())
    write_new(out / "contract.json", contract)
    cfg = (R5 / "platformio.ini").read_text(encoding="utf-8")
    cfg = cfg.replace("lh1sw", "lh3sw")
    cfg = cfg.replace(R5.relative_to(ROOT).as_posix() + "/build", out.relative_to(ROOT).as_posix() + "/build")
    cfg = cfg.replace(R5.relative_to(ROOT).as_posix() + "/generated", out.relative_to(ROOT).as_posix() + "/generated")
    cfg = cfg.replace("MF1750_LH1_SOURCE_WHITE_V5_BUILD", "MF1750_LH3_SOURCE_WHITE_V1_BUILD")
    write_new(out / "platformio.ini", cfg)
    inputs = [bind(p) for p in sorted((ROOT / "src").rglob("*")) if p.is_file() and p.suffix in (".h", ".hpp", ".inc", ".cpp")]
    inputs += [bind(Path(__file__)), bind(R5 / "contract.json"), bind(R5 / "manifest.json"), bind(R5 / "build-report.json"),
               bind(lh2map.PACKAGE / "contract.json"), bind(lh2map.PACKAGE / "manifest.json"), bind(R5 / "platformio.ini")]
    outputs = [bind(p) for p in sorted(out.rglob("*")) if p.is_file()]
    write_new(out / "manifest.json", seal({"kind": "mf1750-lh3-source-white-package-v1", "inputs": inputs, "outputs": outputs, "contract_id": contract["contract_id"], "live_ready": False, "hardware_accessed": False}))
    return {"result": "PASS", "output": str(out), "contract_id": contract["contract_id"], "live_ready": False, "hardware_accessed": False}


def verify(out: Path):
    m = binding.read_sealed(out / "manifest.json")
    for x in m["inputs"] + m["outputs"]:
        if bind(Path(x["path"])) != x: raise ValueError("sealed file differs: " + x["path"])
    return binding.read_sealed(out / "contract.json")


def build(out: Path):
    c = verify(out); out = out.resolve(); (out / "build").mkdir(exist_ok=False)
    pio = shutil.which("pio") or str(Path.home() / ".platformio/penv/Scripts/pio.exe")
    with (out / "build.log").open("xb") as f:
        rc = subprocess.run([pio, "run", "-c", str(out / "platformio.ini")], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env={**os.environ, "PLATFORMIO_SETTING_ENABLE_TELEMETRY": "no", "PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL": "0"}).returncode
    if rc: raise RuntimeError("compile failed")
    arts = [bind(out / "build/lh3sw" / n) for n in ("firmware.bin", "firmware.elf")]
    for artifact in arts:
        if Path(artifact["path"]).read_bytes().count(c["compiled_marker"].encode()) != 1:
            raise ValueError("compiled successor descriptor count differs")
    rec = seal({"kind": "mf1750-lh3-source-white-build-v1", "result": "PASS", "recorded_at": datetime.now(timezone.utc).isoformat(), "contract": bind(out / "contract.json"), "manifest": bind(out / "manifest.json"), "artifacts": arts, "log": bind(out / "build.log"), "hardware_accessed": False, "visible_refreshes": 0, "live_ready": False, "native_and_host_audit_pending": True, "qualified_count": 0})
    write_new(out / "build-report.json", rec); return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=("prepare", "verify", "build")); ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT); a = ap.parse_args(); o = a.output_dir.resolve(); r = prepare(o) if a.command == "prepare" else verify(o) if a.command == "verify" else build(o); print(json.dumps(r, ensure_ascii=False, indent=2))
