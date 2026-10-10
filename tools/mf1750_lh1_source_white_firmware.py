#!/usr/bin/env python3
"""Offline-only, isolated factory-OTP successor after LH1 SOURCE ordinal 1.

No flash, serial, relay, camera or device HTTP entry point is provided. A build
is a candidate until its native protocol audit and host review are sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

from tools import mf1750_lightness_history_firmware as main_pack
from tools import mf1750_lh1_lh4_firmware as binding

ROOT = main_pack.ROOT
SOURCE = ROOT / ".test-output/offline/LH1_LH4_20260912_R1"
DEFAULT_OUTPUT = ROOT / ".test-output/offline/LH1_SOURCE_WHITE_20260912_R1"
OLD = ROOT / ".pio/g_lhr4"
OLD_MAIN = OLD / "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp"
OLD_IDENTITY = (
    OLD / "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc"
)
PINNED = {
    OLD_MAIN: "a45d1544e1312a29af5ac3dcf75d2eebeedf62ece5e64138b6aad94b2dc85096",
    OLD_IDENTITY: "f9040ad5b3dfb268678e241a456c725acc7922cef9dc59318ff37d24bbebe623",
}
CAMPAIGN = "EC5_LH1_SOURCE_WHITE_V1_20260912"
BASE = "/api/ec5/lh1-source-white-v1"
MACRO = "MF1750_LH1_SOURCE_WHITE_V1_BUILD"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def seal(value: dict) -> dict:
    return {
        **value,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": sha(canonical(value)),
        },
    }


def write_new(path: Path, value: dict | str | bytes):
    data = (
        canonical(value) + b"\n"
        if isinstance(value, dict)
        else value.encode()
        if isinstance(value, str)
        else value
    )
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def replace(source: str, old: str, new: str, count=1) -> str:
    if source.count(old) != count:
        raise ValueError(f"white template anchor count differs: {old[:80]}")
    return source.replace(old, new)


def source_context() -> tuple[dict, dict]:
    binding.validate_white_source()
    main_pack.verify_package(SOURCE)
    for path, expected in PINNED.items():
        if path.is_symlink() or sha(path.read_bytes()) != expected:
            raise ValueError(f"frozen LH4 white input differs: {path}")
    contract = json.loads((SOURCE / "contract.json").read_text(encoding="utf-8"))
    build = json.loads((SOURCE / "build-report.json").read_text(encoding="utf-8"))
    if build["result"] != "PASS":
        raise ValueError("source build not PASS")
    return contract, {Path(a["path"]).suffix: a for a in build["artifacts"]}


def render() -> tuple[dict, dict[str, str]]:
    source, artifacts = source_context()
    contract = {
        "kind": "mf1750-lh1-source-white-contract-v1",
        "campaign_id": CAMPAIGN,
        "source_contract_id": source["contract_id"],
        "source_campaign_id": source["campaign_id"],
        "source_action_id": source["actions"][0]["action_id"],
        "accepted_source_ordinals": [1],
        "source_terminal_required": "exact SOURCE ordinal 1 COMPLETE; reject fault/early-stop/MIDDLE/TARGET",
        "source_build": main_pack.bind(SOURCE / "build-report.json"),
        "source_firmware": artifacts[".bin"],
        "source_elf": artifacts[".elf"],
        "source_nvs": {
            "namespace": "lhist_v1",
            "cursor_key": "cur_lh1",
            "complete_cursor": 2,
            "boot_key": "boot_lh1",
        },
        "successor_nvs": {
            "namespace": "lh1srcw_v1",
            "cursor_key": "used_lh1sw1",
            "initial_cursor": 1,
            "complete_cursor": 2,
        },
        "profile_id": "WF23_25",
        "frame_sha256": "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "source_terminal_host_gate_required": True,
        "source_nvs_is_not_terminal_proof": True,
        "driver_body_unchanged_from_lh4": True,
        "waveform_internal_phase": "OPAQUE",
        "runtime_payload": False,
        "retry": False,
        "automatic_recovery": False,
        "main_resume_after_recovery": False,
        "qualified_count": 0,
        "live_action_authorized": False,
        "generator": main_pack.bind(Path(__file__)),
    }
    contract["contract_id"] = sha(canonical(contract))
    contract["descriptor_id"] = sha(
        canonical(
            {
                "contract": contract["contract_id"],
                "role": "LH1_SOURCE_POST_TEST_WHITE",
                "profile": "WF23_25",
            }
        )
    )
    contract["action_id"] = sha(
        canonical(
            {
                "descriptor": contract["descriptor_id"],
                "ordinal": 1,
                "source_action": contract["source_action_id"],
            }
        )
    )
    marker = (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE|SHA256="
        + contract["descriptor_id"]
    )
    contract["compiled_marker"] = marker
    values = {
        "kProfileId": "WF23_25",
        "kEnvironmentId": "lh1_source_white_v1",
        "kCampaignId": CAMPAIGN,
        "kSourceCampaignId": source["campaign_id"],
        "kSourceMainContractId": source["contract_id"],
        "kSourceMainOfflineBuildSha256": contract["source_build"]["sha256"],
        "kBuildTag": "MF1750_EC5_LH1_SOURCE_WHITE_V1_2026-09-12",
        "kContractId": contract["contract_id"],
        "kNvsNamespace": "lh1srcw_v1",
        "kDescriptorId": contract["descriptor_id"],
        "kActionId": contract["action_id"],
        "kAcceptedSourceActionsSha256": sha(canonical(source["actions"][0])),
        "kSourceFirmwareBinSha256": artifacts[".bin"]["sha256"],
        "kSourceFirmwareElfSha256": artifacts[".elf"]["sha256"],
    }
    identity = OLD_IDENTITY.read_text(encoding="utf-8")
    for key, value in values.items():
        pattern = r"(static constexpr const char \*" + key + r'\s*=\s*)"[^"]*";'
        identity, count = re.subn(
            pattern, lambda m: m[1] + json.dumps(value) + ";", identity
        )
        if count != 1:
            raise ValueError("white identity declaration differs: " + key)
    oldmarker = re.search(
        r"MF1750_EC5_TX_DESCRIPTOR_V1\|PROFILE=WF23_25\|ROLE=[A-Z0-9_]+\|SHA256=[0-9a-f]{64}",
        identity,
    )
    if oldmarker is None:
        raise ValueError("white marker missing")
    identity = replace(identity, oldmarker[0], marker)
    identity = identity.replace("after P2-C ordinal-1", "after LH1 SOURCE ordinal-1")
    main = OLD_MAIN.read_text(encoding="utf-8")
    # Identity/route changes only; factory driver and electrical values are frozen.
    for before, after in (
        ("MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_BUILD", MACRO),
        ("P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1", "LH1_SOURCE_V1"),
        ("P2_COMMENTED_ENDPOINT_ATLAS_ORDINAL1", "LH1_SOURCE_ORDINAL1"),
        (
            "p2-commented-endpoint-atlas-4x8-v1/white-successor-v1",
            "lh1-source-white-v1",
        ),
        (
            "p2-commented-endpoint-atlas-4x8-v1-white-successor-v1",
            "lh1-source-white-v1",
        ),
        (
            "P2-COMMENTED-ENDPOINT-ATLAS-4X8-V1-WHITE-SUCCESSOR-V1",
            "LH1-SOURCE-WHITE-V1",
        ),
        (
            "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc",
            "identity.inc",
        ),
        ("used_p2cw1", "used_lh1sw1"),
        ("boot_p2c", "boot_lh1"),
        (
            "source_main_completed_p2_commented_only",
            "source_main_completed_lh1_source_only",
        ),
        ("P2 commented endpoint atlas", "LH1 SOURCE"),
    ):
        if before not in main:
            raise ValueError("white rename anchor missing: " + before)
        main = main.replace(before, after)
    gate = """// Necessary NVS guard. Host still validates exact source terminal/action/claim.
bool sourceOrdinalOneComplete() {
  Preferences source;
  if (!source.begin("lhist_v1", true)) return false;
  const bool ok=source.isKey("cur_lh1") && source.getUShort("cur_lh1",0)==2 &&
    source.isKey("boot_lh1") && source.getULong64("boot_lh1",0)!=0;
  source.end();
  return ok;
}
"""
    main = replace(main, "String identityJson() {", gate + "\nString identityJson() {")
    for name in ("Arm", "Execute"):
        token = f"void handle{name}() {{\n  ++{name.lower()}RequestCount;"
        main = replace(
            main,
            token,
            token
            + '\n  if (!sourceOrdinalOneComplete()) { rejectMutation(409,"lh1_source_not_complete"); return; }',
        )
    token = "void executePendingAction() {\n  if (!executePending) return;"
    main = replace(
        main,
        token,
        token
        + '\n  if (!sourceOrdinalOneComplete()) { enterFault("lh1_source_lost_before_dispatch"); return; }',
    )
    driver = '// Frozen actual shared WF23 factory-OTP driver bytes.\n#include <SPI.h>\n#include "frozen_epd_driver.cpp.inc"\n'
    return seal(contract), {
        "main.cpp": main,
        "identity.inc": identity,
        "driver.cpp": driver,
    }


def prepare(out: Path) -> dict:
    contract, sources = render()
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    gen = out / "generated"
    gen.mkdir()
    for name, content in sources.items():
        write_new(gen / name, content)
    write_new(
        gen / "frozen_epd_driver.cpp.inc", (ROOT / "src/epd_driver.cpp").read_bytes()
    )
    write_new(out / "contract.json", contract)
    relative = out.relative_to(ROOT).as_posix()
    config = (ROOT / "platformio.lhr4.ini").read_text(encoding="utf-8")
    config = (
        config.replace("lhr4", "lh1sw")
        .replace(".pio/br_lh1sw", relative + "/build")
        .replace(".pio/g_lh1sw", relative + "/generated")
    )
    config = (
        config.replace(
            "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_epd_driver.cpp",
            "driver.cpp",
        )
        .replace(
            "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp",
            "main.cpp",
        )
        .replace(
            "MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_BUILD", MACRO
        )
    )
    write_new(out / "platformio.ini", config)
    # Bind all possible local include inputs; never print wifi_secrets contents.
    inputs = [
        main_pack.bind(p)
        for p in sorted((ROOT / "src").rglob("*"))
        if p.is_file() and p.suffix in (".h", ".hpp", ".inc", ".cpp")
    ]
    inputs += [
        main_pack.bind(p)
        for p in (
            *PINNED,
            Path(__file__),
            SOURCE / "manifest.json",
            SOURCE / "build-report.json",
            ROOT / "platformio.lhr4.ini",
        )
    ]
    outputs = [main_pack.bind(p) for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = seal(
        {
            "kind": "mf1750-lh1-source-white-package-v1",
            "inputs": inputs,
            "outputs": outputs,
            "contract_id": contract["contract_id"],
            "live_ready": False,
        }
    )
    write_new(out / "manifest.json", manifest)
    return {
        "result": "PASS",
        "output": str(out),
        "contract_id": contract["contract_id"],
        "live_ready": False,
        "hardware_accessed": False,
    }


def verify(out: Path) -> dict:
    manifest = binding.read_sealed(out / "manifest.json")
    for item in manifest["inputs"] + manifest["outputs"]:
        if main_pack.bind(Path(item["path"])) != item:
            raise ValueError("successor sealed file differs: " + item["path"])
    return binding.read_sealed(out / "contract.json")


def build(out: Path) -> dict:
    contract = verify(out)
    if (out / "build").exists() or (out / "build-report.json").exists():
        raise FileExistsError("successor build output exists; preserve it")
    executable = shutil.which("pio") or str(
        Path.home() / ".platformio/penv/Scripts/pio.exe"
    )
    command = [executable, "run", "-c", str(out / "platformio.ini")]
    with (out / "build.log").open("xb") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "PLATFORMIO_SETTING_ENABLE_TELEMETRY": "no",
                "PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL": "0",
            },
        )
    if result.returncode:
        raise RuntimeError("successor compile failed; preserve build.log")
    artifacts = [
        main_pack.bind(out / "build/lh1sw" / name)
        for name in ("firmware.bin", "firmware.elf")
    ]
    for artifact in artifacts:
        if (
            Path(artifact["path"])
            .read_bytes()
            .count(contract["compiled_marker"].encode())
            != 1
        ):
            raise ValueError("compiled successor descriptor count differs")
    verify(out)
    record = seal(
        {
            "kind": "mf1750-lh1-source-white-build-v1",
            "result": "PASS",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "contract": main_pack.bind(out / "contract.json"),
            "manifest": main_pack.bind(out / "manifest.json"),
            "artifacts": artifacts,
            "log": main_pack.bind(out / "build.log"),
            "hardware_accessed": False,
            "visible_refreshes": 0,
            "live_ready": False,
            "native_and_host_audit_pending": True,
            "qualified_count": 0,
        }
    )
    write_new(out / "build-report.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "verify"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    result = (
        prepare(output)
        if args.command == "prepare"
        else build(output)
        if args.command == "build"
        else verify(output)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
