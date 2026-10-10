#!/usr/bin/env python3
"""Build an isolated lineage-repair candidate for the P2-C white successor.

The shipped successor omitted one source binding member from ``identityJson``.
This tool copies the sealed generated sources into a new tree, adds exactly
that JSON member, and compiles a new candidate.  It never touches the sealed
tree, NVS key, driver, waveform, or any hardware.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OLD_ROOT = ROOT / ".pio/generated-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1"
NEW_ROOT = ROOT / ".pio/g_lhr4"
BUILD_ROOT = ".pio/br_lhr4"
ENV = "lhr4"
INI = ROOT / "platformio.lhr4.ini"
OUT = (
    ROOT
    / ".test-output/offline/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_LINEAGE_REPAIR_20260912_LH4"
)
SEAL = (
    ROOT
    / "docs/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json"
)
SOURCE_BUILD_SHA = "e2c1adce901971fa2472967c8f237507861ac697e3fc3ef9b8ed51a5301a2d06"
OLD_MAIN_SHA = "e463ead9cceb5f4596f2f0953fbaa5d56afe64992b02075a915563a364c02db9"
OLD_DRIVER_SHA = "0e34ed03c6655d906b0e23cef5f8c383db2f395d57665c7698ac44098d859f32"
OLD_IDENTITY_SHA = "f9040ad5b3dfb268678e241a456c725acc7922cef9dc59318ff37d24bbebe623"
BIN = ROOT / BUILD_ROOT / ENV / "firmware.bin"
ELF = ROOT / BUILD_ROOT / ENV / "firmware.elf"

NAMES = {
    "main": "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp",
    "driver": "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_epd_driver.cpp",
    "identity": "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc",
}
MARKER = "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_P2_COMMENTED_ENDPOINT_ATLAS_ORDINAL1_COMPLETE|SHA256=312b07fa5bac5ff93274bc342c0579640e8264f38b74e18e4904b3ddd6daef16"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def patch_main(old: str) -> tuple[str, dict[str, Any]]:
    token = '         "\\",\\"source_main_contract_exact_binding\\":true,"'
    if old.count(token) != 1:
        raise RuntimeError("expected one identityJson insertion site")
    insertion = r"""         "\",\"source_main_offline_build_file_sha256\":\"" +
         kSourceMainOfflineBuildSha256 + "\",\"source_main_contract_exact_binding\":true,"
"""
    return old.replace(token, insertion), {
        "old_occurrences": 1,
        "new_field": "source_main_offline_build_file_sha256",
        "semantic_scope": "identityJson only",
    }


def generate() -> dict[str, Any]:
    if not OLD_ROOT.is_dir() or OLD_ROOT.is_symlink():
        raise RuntimeError("sealed generated source tree missing")
    if sha(SEAL) != SOURCE_BUILD_SHA:
        raise RuntimeError("source main offline seal hash differs")
    old = {k: OLD_ROOT / v for k, v in NAMES.items()}
    if {k: sha(p) for k, p in old.items()} != {
        "main": OLD_MAIN_SHA,
        "driver": OLD_DRIVER_SHA,
        "identity": OLD_IDENTITY_SHA,
    }:
        raise RuntimeError("sealed generated source hash differs")
    if NEW_ROOT.exists() or OUT.exists() or INI.exists():
        # Re-entry is read-only and accepted only when the prior isolated
        # candidate is complete and exactly matches the repair transformation.
        if (
            not all((NEW_ROOT / n).is_file() for n in NAMES.values())
            or not INI.is_file()
        ):
            raise RuntimeError("repair output already exists but is incomplete")
        expected_main, _ = patch_main(old["main"].read_text(encoding="utf-8"))
        if (NEW_ROOT / NAMES["main"]).read_bytes() != expected_main.encode("utf-8"):
            raise RuntimeError("existing repair main bytes differ")
        if any(
            (NEW_ROOT / NAMES[k]).read_bytes() != old[k].read_bytes()
            for k in ("driver", "identity")
        ):
            raise RuntimeError("existing repair driver/identity bytes differ")
        if (
            sha(INI)
            != "0a734b6de6aec71d8834a0a1421f3457c278c8550f67f41fc31ccd529c924e19"
        ):
            raise RuntimeError("existing repair config bytes differ")
        return {
            "result": "PASS",
            "offline_only": True,
            "hardware_accessed": False,
            "source_build_sha256": SOURCE_BUILD_SHA,
            "source_tree_sha256": {k: sha(p) for k, p in old.items()},
            "candidate_sources": {
                k: {
                    "path": str((NEW_ROOT / NAMES[k]).relative_to(ROOT)),
                    "bytes": (NEW_ROOT / NAMES[k]).stat().st_size,
                    "sha256": sha(NEW_ROOT / NAMES[k]),
                }
                for k in NAMES
            },
            "semantic_diff": {
                "old_occurrences": 1,
                "new_field": "source_main_offline_build_file_sha256",
                "semantic_scope": "identityJson only",
            },
            "config": str(INI.relative_to(ROOT)),
        }
    main, diff = patch_main(old["main"].read_text(encoding="utf-8"))
    NEW_ROOT.mkdir(parents=True)
    (NEW_ROOT / NAMES["main"]).write_text(main, encoding="utf-8", newline="")
    shutil.copyfile(old["driver"], NEW_ROOT / NAMES["driver"])
    shutil.copyfile(old["identity"], NEW_ROOT / NAMES["identity"])
    config = f"""[platformio]\ndefault_envs = {ENV}\nbuild_dir = {BUILD_ROOT}\nsrc_dir = {NEW_ROOT.relative_to(ROOT).as_posix()}\n\n[env:{ENV}]\nplatform = platformio/espressif32@7.0.1\nboard = esp32-s3-devkitc-1\nframework = arduino\nboard_build.arduino.memory_type = qio_opi\nboard_build.psram_type = opi\nmonitor_speed = 115200\nboard_build.filesystem = littlefs\nbuild_src_filter =\n  -<*>\n  +<{NAMES["driver"]}>\n  +<{NAMES["main"]}>\nbuild_flags =\n  -D CORE_DEBUG_LEVEL=3\n  -g0\n  -D BOARD_HAS_PSRAM\n  -I src\n  -D EPD_ENABLE_TEST_PATTERN=0\n  -D MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1\n  -D MF1750_OTP_WHITE_FOR_PROFILE_WF20_25=0\n  -D MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1\n  -D MF1750_OTP_WHITE_FOR_DUAL_R20_H20_20260821=0\n  -D MF1750_OTP_WHITE_FOR_DUAL_R20_H23_20260821=0\n  -D MF1750_PURE_FIELD_WHITE=1\n  -D MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1_BUILD=1\n"""
    INI.write_text(config, encoding="utf-8", newline="")
    return {
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "source_build_sha256": SOURCE_BUILD_SHA,
        "source_tree_sha256": {k: sha(p) for k, p in old.items()},
        "candidate_sources": {
            k: {
                "path": str((NEW_ROOT / NAMES[k]).relative_to(ROOT)),
                "bytes": (NEW_ROOT / NAMES[k]).stat().st_size,
                "sha256": sha(NEW_ROOT / NAMES[k]),
            }
            for k in NAMES
        },
        "semantic_diff": diff,
        "config": str(INI.relative_to(ROOT)),
    }


def build() -> dict[str, Any]:
    if OUT.exists():
        raise RuntimeError("sealed output exists; no compile or overwrite")
    generated = generate()
    pio = shutil.which("pio") or str(Path.home() / ".platformio/penv/Scripts/pio.exe")
    subprocess.run(
        [pio, "run", "-c", str(INI.name)],
        cwd=ROOT,
        check=True,
        env={
            **__import__("os").environ,
            "PLATFORMIO_SETTING_ENABLE_TELEMETRY": "no",
            "PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL": "0",
        },
    )
    if not BIN.is_file() or not ELF.is_file():
        raise RuntimeError("candidate artifacts missing")
    artifacts = {
        "firmware.bin": {
            "bytes": BIN.stat().st_size,
            "sha256": sha(BIN),
            "path": str(BIN.relative_to(ROOT)),
        },
        "firmware.elf": {
            "bytes": ELF.stat().st_size,
            "sha256": sha(ELF),
            "path": str(ELF.relative_to(ROOT)),
        },
    }
    if (
        BIN.read_bytes().count(MARKER.encode()) != 1
        or ELF.read_bytes().count(MARKER.encode()) != 1
    ):
        raise RuntimeError("descriptor marker count differs")
    value = {
        "schema_version": 1,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-lineage-repair-offline-build",
        "created_on": "2026-09-12",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "source_build_report": {
            "path": str(SEAL.relative_to(ROOT)),
            "sha256": SOURCE_BUILD_SHA,
        },
        "source_tree_sha256": generated["source_tree_sha256"],
        "candidate_sources": generated["candidate_sources"],
        "semantic_diff": generated["semantic_diff"],
        "successor_artifacts": artifacts,
        "compiled_descriptor_marker_counts": {"firmware_bin": 1, "firmware_elf": 1},
        "original_firmware_preserved": True,
        "runner_binding": "must bind this manifest and candidate hashes before any live use",
    }
    OUT.mkdir(parents=True)
    body = dict(value)
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
    }
    with (OUT / "lineage-repair-offline-build.json").open(
        "x", encoding="utf-8", newline=""
    ) as stream:
        stream.write(
            json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return value


if __name__ == "__main__":
    try:
        print(json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"lineage repair blocked: {e}", file=sys.stderr)
        raise SystemExit(2)
