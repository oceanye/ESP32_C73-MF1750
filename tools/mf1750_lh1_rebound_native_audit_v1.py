#!/usr/bin/env python3
"""Offline native protocol/transport audit for the LH1 rebound package.

This is deliberately isolated from ``mf1750_lightness_history_native_audit``.
The rebound package has a new generated namespace and NVS keys, so the old
fixture cannot be reused verbatim.  The harness below substitutes only the
include name and the sealed rebound keys; it does not access hardware,
network, relay, camera, or the production source tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo import lightness_history as algorithm  # noqa: E402
from host.static_photo.common import attach_integrity  # noqa: E402
from tools import mf1750_lightness_history_native_audit as legacy  # noqa: E402

CASES = legacy.CASES
FIXTURE = ROOT / "tests/fixtures/lightness_history_native"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_custom_integrity(value: dict, label: str) -> None:
    integrity = value.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256-canonical-json-without-integrity":
        raise ValueError(f"{label} has no rebound canonical integrity")
    body = dict(value)
    body.pop("integrity", None)
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    expected = hashlib.sha256(canonical).hexdigest()
    if integrity.get("sha256") != expected:
        raise ValueError(f"{label} integrity mismatch")


def _verify_package(package: Path) -> dict:
    manifest = _read_json(package / "manifest.json")
    contract = _read_json(package / "contract.json")
    _verify_custom_integrity(manifest, "manifest")
    _verify_custom_integrity(contract, "contract")
    if manifest.get("contract_id") != contract.get("contract_id"):
        raise ValueError("manifest/contract id mismatch")
    if contract.get("campaign_id") != "EC5_LIGHTNESS_HISTORY_LH1_REBOUND_V1_20260914":
        raise ValueError("unexpected rebound campaign")
    if contract.get("nvs") != {
        "namespace": "lhist_lh1_rebound_v1",
        "cursor": "cur_lh1_rebound",
        "boot": "boot_lh1_rebound",
    }:
        raise ValueError("rebound NVS contract mismatch")
    if contract.get("old_fault_preservation", {}).get("expected_cursor_raw") != 770:
        raise ValueError("old fault preservation gate missing")
    source = contract.get("source_white", {})
    expected_source = {
        "contract_id": "8746bf27c2317649096c353bebe69a762b09657e648241114e4c23c6a20eb7f3",
        "action_id": "60e078ff9c79f6a9a9e09fee327231a78cc69074da0c0c1bc91ff6a026fad966",
        "nvs_namespace": "lh1srcw_v1",
        "nvs_key": "used_lh1sw1",
        "complete_cursor": 2,
    }
    if any(source.get(k) != v for k, v in expected_source.items()):
        raise ValueError("rebound white source anchor mismatch")
    if len(contract.get("actions", [])) != 3:
        raise ValueError("rebound action count mismatch")
    for ordinal, stage in enumerate(algorithm.STAGES, 1):
        frame = package / f"{stage.lower()}.frame4bpp"
        if frame.read_bytes() != algorithm.frame(stage):
            raise ValueError(f"frame mismatch: {stage}")
        if contract["actions"][ordinal - 1]["frame"]["sha256"] != _sha(frame):
            raise ValueError(f"contract frame hash mismatch: {stage}")
    generated = package / "generated"
    main = next(generated.glob("*_main.cpp"), None)
    driver = next(generated.glob("*_driver.inc"), None)
    if not main or not driver:
        raise ValueError("generated rebound main/driver missing")
    generated_text = "\n".join(p.read_text(encoding="utf-8") for p in generated.iterdir() if p.is_file())
    required = ("lhist_lh1_rebound_v1", "lh1srcw_v1", "used_lh1sw1", "cur_lh1_rebound", "boot_lh1_rebound")
    if any(item not in generated_text for item in required):
        raise ValueError("compiled rebound namespace/source gate missing")
    # The old identifiers may occur in the host contract's preservation note,
    # but must not occur in generated firmware source.
    if "lhist_v1" in generated_text or "cur_lh1\"" in generated_text or "boot_lh1\"" in generated_text or "p2catwsv1" in generated_text or "used_p2cw1" in generated_text:
        raise ValueError("old namespace/key leaked into rebound main")
    return {"manifest": manifest, "contract": contract, "main": main, "driver": driver}


def _fixture_source(main_name: str, namespace: str, cursor: str) -> str:
    source = (FIXTURE / "protocol.cpp").read_text(encoding="utf-8")
    source = source.replace('"ec5_lightness_history_v1_main.cpp"', json.dumps(main_name))
    source = source.replace("p2catwsv1/used_p2cw1", f"lh1srcw_v1/used_lh1sw1")
    source = source.replace("lhist_v1/cur_lh1", f"{namespace}/{cursor}")
    source = source.replace('"p2catwsv1/used_p2cw1"', '"lh1srcw_v1/used_lh1sw1"')
    return source


def audit(package: Path, output: Path) -> dict:
    package = package.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    info = _verify_package(package)
    output.mkdir(parents=True)
    main_name = info["main"].name
    source = output / "protocol.cpp"
    source.write_text(_fixture_source(main_name, "lhist_lh1_rebound_v1", "cur_lh1_rebound"), encoding="utf-8", newline="\n")
    compiler, environment, msvc = legacy.compiler_environment()
    includes = [FIXTURE, package / "generated", ROOT / "src"]
    macros = [
        "MF1750_ENABLE_CHROMA_GRID=1",
        "MF1750_LIGHTNESS_LH1_REBOUND_V1_BUILD=1",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1",
    ]
    exe = output / ("protocol.exe" if msvc else "protocol")
    if msvc:
        args = [compiler, "/nologo", "/std:c++17", "/EHsc", "/utf-8", "/D_CRT_SECURE_NO_WARNINGS"]
        args += ["/I" + str(p) for p in includes] + ["/D" + m for m in macros]
        args += [str(source), "/Fe:" + str(exe), "/Fo:" + str(output / "protocol.obj")]
    else:
        args = [compiler, "-std=c++17"] + ["-I" + str(p) for p in includes] + ["-D" + m for m in macros]
        args += [str(source), "-o", str(exe)]
    compile_result = subprocess.run(args, cwd=output, env=environment, capture_output=True, check=False)
    (output / "protocol-compile.log").write_bytes(compile_result.stdout + compile_result.stderr)
    if compile_result.returncode:
        raise RuntimeError("rebound native protocol compile failed")
    records = []
    for case in CASES:
        result = subprocess.run([str(exe), case], cwd=output, capture_output=True, check=False)
        (output / f"{case}.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"rebound native protocol case failed: {case}")
        docs = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines() if line.startswith("{")]
        if case == "chain":
            if len(docs) != 3 or any(d.get("driver_call_count_for_action") != 1 or d.get("qualified_count") != 0 for d in docs):
                raise ValueError("rebound chain documents failed")
            if [d.get("controller_tuple_dispatch") for d in docs] != ["AA", "CC", "AA"]:
                raise ValueError("rebound dispatch sequence failed")
        if case == "read_only" and len(docs) != 4:
            raise ValueError("rebound read-only document count failed")
        records.append({"case": case, "result": "PASS", "parsed_json_documents": len(docs)})
    report = attach_integrity({
        "kind": "mf1750-lh1-rebound-native-audit-v1",
        "result": "PASS",
        "contract_id": info["contract"]["contract_id"],
        "package": _binding(package / "manifest.json"),
        "native_harness": _binding(source),
        "protocol_binary": _binding(exe),
        "compiler": _binding(Path(compiler)),
        "cases": records,
        "scenario_count": len(records),
        "hardware_accessed": False,
        "network_accessed": False,
        "visible_refresh_count": 0,
        "qualified_count": 0,
        "limits": ["Desktop Arduino/Preferences/WebServer/WiFi/GPIO doubles only; no physical BUSY/SPI/panel proof.", "This audit does not grant live authorization or optical qualification.", "Old lhist_v1 fault namespace is checked as a preservation contract, not modified."],
    })
    report_path = output / "native-audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"result": "PASS", "protocol_cases": len(records), "parsed_documents": sum(r["parsed_json_documents"] for r in records), "report": str(report_path), "hardware_accessed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.package, args.output_dir), ensure_ascii=False, indent=2))
