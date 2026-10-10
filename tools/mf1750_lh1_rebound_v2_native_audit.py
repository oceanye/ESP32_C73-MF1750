#!/usr/bin/env python3
"""Desktop C++ audit of the generated LH1 main, frames and tuple upload functions.

No hardware access. Arduino, HTTP, Wi-Fi, Preferences and the panel driver are
test doubles. Transport audit checks the exact two generated upload functions;
it does not simulate the shared electrical initialization or panel physics.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo import lightness_history as algorithm  # noqa: E402
from host.static_photo.common import attach_integrity  # noqa: E402
from tools import mf1750_lightness_history_firmware as pack
from tools import mf1750_lh1_rebound_v2_pack as rebound  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/lightness_history_native"
CASES = (
    "chain",
    "frames",
    "read_only",
    "reboot",
    "duplicate_execute",
    "duplicate_arm",
    "changed_review_execute",
    "reused_stage_review",
    "driver_failure",
    "bad_driver_report",
    "complete_write_failure",
    "busy_execute",
    "consume_write_failure",
    "busy_dispatch",
    "source_lost_dispatch",
    "cursor_changed_dispatch",
    "missing_white",
    "busy_arm",
    "arm_write_failure",
    "wrong_boot",
    "wrong_action",
    "body",
    "invalid_review",
    "ordinal_skip",
    "unknown_mutation",
    "fixture_failure",
    "nvs_open_failure",
    "boot_write_failure",
    "invalid_cursor",
)


def compiler_environment():
    if os.name != "nt":
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler:
            return compiler, dict(os.environ), False
        raise RuntimeError("native C++17 compiler required")
    vswhere = (
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    result = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    vcvars = Path(result.stdout.strip()) / "VC/Auxiliary/Build/vcvars64.bat"
    if not vcvars.is_file():
        raise RuntimeError("Visual C++ environment unavailable")
    # Capture environment privately: never print credentials or inherited values.
    result = subprocess.run(
        f'cmd.exe /d /u /s /c ""{vcvars}" >nul && set"',
        capture_output=True,
        text=True,
        encoding="utf-16-le",
        check=True,
    )
    environment = {key.upper(): value for key, value in os.environ.items()}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key:
            environment[key.upper()] = value
    compiler = shutil.which("cl.exe", path=environment["PATH"])
    if not compiler:
        raise RuntimeError("cl.exe unavailable after vcvars")
    return compiler, environment, True


def transport_source(driver):
    begin = driver.index("bool phApplyRuntimeLutGlobalConfig(")
    end = driver.index("\n#endif", begin)
    functions = driver[begin:end]
    before = r"""#include <cstdint>
#include <iostream>
#include <iomanip>
#include "generated/spd1657_legacy_535_reference.inc"
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
int selected=0;
void setActiveControllers(bool a,bool b) { selected=int(a)+2*int(b); }
bool epdWaitIdle(const char *) { return true; }
void phWriteFixedPayload(uint8_t command,const uint8_t *data,size_t size) {
  std::cout<<std::dec<<selected<<' '<<int(command)<<' ';
  for(size_t i=0;i<size;++i) std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<int(data[i]);
  std::cout<<'\n';
}
"""
    after = r"""
int main() {
  for(unsigned stage=1;stage<=3;++stage) {
    bool commented=stage==2;
    if(!phApplyRuntimeLutGlobalConfig(commented) ||
       !phUploadRuntimeLutToController(false,commented) ||
       !phUploadRuntimeLutToController(true,commented)) return 1;
  }
}
"""
    return before + functions + after




def prepare_fixture(out):
    fixture = out / "fixtures"
    fixture.mkdir()
    source = (FIXTURES / "protocol.cpp").read_text(encoding="utf-8")
    source = source.replace('"ec5_lightness_history_v1_main.cpp"', '"'+rebound.PREFIX+'_main.cpp"')
    source = source.replace('p2catwsv1/used_p2cw1','lh1srcw_v1/used_lh1sw1')
    source = source.replace('lhist_v1/cur_lh1',rebound.NVS['namespace']+'/'+rebound.NVS['cursor'])
    source = source.replace("const String sourceReview=std::string(64,'a');", 'const String sourceReview="'+rebound.ANCHOR_SHA+'";')
    source = source.replace("const String review=std::string(64,char('a'+n-1));", "const String review=n==1 ? sourceReview : String(std::string(64,char('a'+n-1)));")
    source = source.replace('  Preferences::values["lh1srcw_v1/used_lh1sw1"]=2;', '  Preferences::values["lhist_v1/cur_lh1"]=770;\n  Preferences::values["lhist_v1/boot_lh1"]=0x30a9e5989873f4e0ULL;\n  Preferences::values["lh1srcw_v1/used_lh1sw1"]=2;')
    source = source.replace('else check(scenario=="unknown_mutation","unknown case");', 'else if(scenario=="wrong_source_review") server.headers["X-LH-Source-Review"]=std::string(64,char(97));\n      else if(scenario=="old_fault_missing") Preferences::values.erase("lhist_v1/cur_lh1");\n      else if(scenario=="old_fault_changed") Preferences::values["lhist_v1/cur_lh1"]=771;\n      else check(scenario=="unknown_mutation","unknown case");')
    source = source.replace('std::cout<<"PASS "<<scenario', 'check(Preferences::values.at("lhist_v1/boot_lh1")==0x30a9e5989873f4e0ULL,"old boot altered");\n  if(scenario!="old_fault_missing") check(Preferences::values.at("lhist_v1/cur_lh1")==unsigned(scenario=="old_fault_changed"?771:770),"old fault altered");\n  else check(!Preferences::values.count("lhist_v1/cur_lh1"),"old fault recreated");\n  std::cout<<"PASS "<<scenario')
    (fixture/"protocol.cpp").write_text(source,encoding="utf-8")
    pref=(FIXTURES/"Preferences.h").read_text(encoding="utf-8")
    pref=pref.replace('return !failBegin;', 'return !failBegin && ns.size()>0 && ns.size()<=15;')
    pref=pref.replace('if(failWrite||readOnly) return 0;', 'if(failWrite||readOnly||std::string(k).size()>15) return 0;')
    (fixture/"Preferences.h").write_text(pref,encoding="utf-8")
    return fixture


def audit(package, out):
    package, out = package.resolve(), out.resolve()
    pack.verify_package(package)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    compiler, environment, msvc = compiler_environment()
    generated = package / "generated"
    fixture = prepare_fixture(out)
    includes = [fixture, FIXTURES, generated, ROOT / "src"]
    macros = [
        "MF1750_ENABLE_CHROMA_GRID=1",
        rebound.MACRO + "=1",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1",
    ]
    command_records = []

    def compile_cpp(source, name):
        exe = out / (name + (".exe" if msvc else ""))
        if msvc:
            args = [
                compiler,
                "/nologo",
                "/std:c++17",
                "/EHsc",
                "/utf-8",
                "/D_CRT_SECURE_NO_WARNINGS",
            ]
            args += ["/I" + str(p) for p in includes] + ["/D" + m for m in macros]
            args += [
                str(source),
                "/Fe:" + str(exe),
                "/Fo:" + str(out / (name + ".obj")),
            ]
        else:
            args = (
                [compiler, "-std=c++17"]
                + ["-I" + str(p) for p in includes]
                + ["-D" + m for m in macros]
            )
            args += [str(source), "-o", str(exe)]
        result = subprocess.run(
            args, cwd=out, env=environment, capture_output=True, check=False
        )
        pack.write_new(out / (name + "-compile.log"), result.stdout + result.stderr)
        command_records.append({"command": args, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError("native compile failed: " + name)
        return exe

    executable = compile_cpp(fixture / "protocol.cpp", "protocol")
    case_records = []
    for name in CASES + ("wrong_source_review", "old_fault_missing", "old_fault_changed"):
        result = subprocess.run(
            [str(executable), name], cwd=out, capture_output=True, check=False
        )
        pack.write_new(out / (name + ".log"), result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("native protocol case failed: " + name)
        lines = result.stdout.decode("utf-8").splitlines()
        documents = [json.loads(line) for line in lines if line.startswith("{")]
        if name == "chain":
            assert len(documents) == 3
            for ordinal, document in enumerate(documents, 1):
                assert document["ordinal"] == ordinal
                assert document["driver_call_count_for_action"] == 1
                assert document["qualified_count"] == 0
                assert (
                    document["driver"]["busy_stage_samples"]["unreached_level_sentinel"]
                    == 255
                )
                assert document["controller_tuple_dispatch"] == (
                    "CC" if ordinal == 2 else "AA"
                )
        if name == "read_only":
            assert len(documents) == 4
        case_records.append(
            {"case": name, "result": "PASS", "parsed_json_documents": len(documents)}
        )
    frames = []
    for ordinal, stage in enumerate(algorithm.STAGES, 1):
        path = out / f"native-frame-{ordinal}.bin"
        if path.read_bytes() != algorithm.frame(stage):
            raise ValueError("C++ / Python frame mismatch: " + stage)
        frames.append({"stage": stage, **pack.bind(path), "byte_for_byte_match": True})

    driver_path = generated / f"{rebound.PREFIX}_driver.inc"
    source = out / "transport.cpp"
    pack.write_new(source, transport_source(driver_path.read_text(encoding="utf-8")))
    executable = compile_cpp(source, "transport")
    result = subprocess.run([str(executable)], cwd=out, capture_output=True, check=True)
    pack.write_new(out / "transport.log", result.stdout + result.stderr)
    lines = result.stdout.decode().splitlines()
    c = json.loads((package / "contract.json").read_text(encoding="utf-8"))
    expected_order = [
        (3, 0),
        (3, 1),
        (3, 0x30),
        (3, 0x61),
        (1, 0xE9),
        (1, 0x20),
        (1, 0x21),
        (2, 0xE9),
        (2, 0x20),
        (2, 0x21),
    ]
    assert len(lines) == 30
    transport_records = []
    for stage, action in enumerate(c["actions"]):
        p = action["profile"]
        records = []
        for line, (mask, cmd) in zip(
            lines[stage * 10 : (stage + 1) * 10], expected_order, strict=True
        ):
            actual_mask, actual_command, hex_data = line.split()
            assert (int(actual_mask), int(actual_command)) == (mask, cmd)
            data = bytes.fromhex(hex_data)
            key = {
                0: "runtime_psr",
                1: "power_payload",
                0x30: "pll_payload",
                0x61: "tres",
                0xE9: "hidden_enable",
                0x20: "r20_prefix",
                0x21: "r21",
            }[cmd]
            expected = (
                p if mask == 3 or cmd == 0xE9 else p["cs1" if mask == 1 else "cs2"]
            )
            assert algorithm.digest(data) == expected[key + "_sha256"]
            assert len(data) == expected[key + "_bytes"]
            records.append(
                {
                    "controller_mask": mask,
                    "command": cmd,
                    "bytes": len(data),
                    "sha256": algorithm.digest(data),
                }
            )
        transport_records.append(
            {"ordinal": stage + 1, "commands": records, "result": "PASS"}
        )
    pack.verify_package(package)
    report = attach_integrity(
        {
            "kind": "mf1750-lh1-rebound-v2-native-audit",
            "old_fault_runtime_assertions": True,
            "nvs_length_enforced_by_double": True,
            "result": "PASS",
            "contract_id": c["contract_id"],
            "package_manifest": pack.bind(package / "manifest.json"),
            "compiler": pack.bind(compiler),
            "compile_commands": command_records,
            "cases": case_records,
            "frames": frames,
            "tuple_uploads": transport_records,
            "inputs": [pack.bind(Path(__file__)), pack.bind(driver_path), pack.bind(fixture / "protocol.cpp"), pack.bind(fixture / "Preferences.h")]
            + [pack.bind(p) for p in sorted(FIXTURES.iterdir()) if p.is_file()],
            "evidence": [pack.bind(p) for p in sorted(out.iterdir()) if p.is_file()],
            "scope": "Actual generated main with desktop doubles; actual frame builder; extracted unchanged global/tuple upload functions. No physical BUSY/SPI/panel, NVS durability or HTTP stack proof.",
            "hardware_accessed": False,
            "visible_refresh_count": 0,
            "qualified_count": 0,
        }
    )
    pack.write_new(out / "native-audit.json", report)
    return {
        "result": "PASS",
        "protocol_cases": len(CASES) + 3,
        "frames": 3,
        "tuple_commands": 30,
        "hardware_accessed": False,
        "report": str(out / "native-audit.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(audit(args.package, args.output_dir), ensure_ascii=False, indent=2)
    )
