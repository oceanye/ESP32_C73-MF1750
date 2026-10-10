#!/usr/bin/env python3
"""Compile-only sealed builder for the P2-C one-shot atlas."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_codegen as codegen  # noqa: E402
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402


CONFIG = "platformio.p2_commented_endpoint_atlas_4x8_v1.ini"
OFFLINE_BUILD = (
    REPO_ROOT
    / "docs/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json"
)


def _validate_compile_time_profile_lock() -> None:
    """Reject a PlatformIO configuration that can select another profile."""

    config = (REPO_ROOT / CONFIG).read_text(encoding="utf-8")
    required = (
        "-D MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD=1",
        "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1",
    )
    if any(token not in config for token in required):
        raise RuntimeError("P2-C compile-time commented profile lock is missing")
    forbidden = (
        "-D MF1750_RUNTIME_LUT_SAME_R20_PARITY_4X8_V2_BUILD=1",
        "-D MF1750_RAW_P16_CROSSOVER_POSBAL_BUILD=1",
        "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD=1",
        "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD=1",
        "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD=1",
    )
    if any(token in config for token in forbidden):
        raise RuntimeError("P2-C config selects a foreign runtime profile")


def _platformio(explicit: Path | None) -> Path:
    candidates = [Path(explicit)] if explicit else []
    if found := shutil.which("pio"):
        candidates.append(Path(found))
    candidates.append(Path.home() / ".platformio/penv/Scripts/pio.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("PlatformIO executable not found")


def preflight() -> dict[str, Any]:
    _validate_compile_time_profile_lock()
    report = pack.build_report()
    action = report["actions"][0]
    if (
        report["offline_only"] is not True
        or action["waveform_binding"] != pack.commented_profile()
        or action["cs1_dtm"] != action["cs2_dtm"]
        or report["contract"]["action_count"] != 1
    ):
        raise RuntimeError("P2-C preflight contract differs")
    authority_sources = pack.authority_source_hashes()
    return {
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "action_id": action["action_id"],
        "authority_source_seal": pack.authority_source_seal(authority_sources),
    }


def build(*, pio: Path | None = None, clean: bool = True) -> dict[str, Any]:
    before = preflight()
    generated = codegen.generate()
    executable = _platformio(pio)
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    environment["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] = "0"
    commands: list[list[str]] = []
    if clean:
        commands.append([str(executable), "run", "-c", CONFIG, "-t", "clean"])
    commands.append([str(executable), "run", "-c", CONFIG])
    for command in commands:
        subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    artifacts = pack.validate_artifacts()
    report = pack.build_report()
    source_files = pack.authority_source_hashes()
    authority_seal = pack.authority_source_seal(source_files)
    result = {
        "schema_version": 1,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-offline-build",
        "result": "PASS",
        "offline_build_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": report["contract_id"],
        "action_descriptor_sha256": report["actions"][0]["descriptor_id"],
        "action_sha256": report["actions"][0]["action_id"],
        "frame_sha256": report["actions"][0]["frame"]["sha256"],
        "controller_dtm_sha256": report["actions"][0]["cs1_dtm"]["sha256"],
        "global_tuple_id": report["actions"][0]["global_tuple_id"],
        "artifacts": artifacts,
        "generated_sources": generated["generated"],
        "authority_sources": source_files,
        # Keep a named hash map as a compatibility/readability alias while
        # the structured seal carries the algorithm and aggregate digest.
        "authority_source_hashes": source_files,
        "offline_authority_seal": authority_seal,
        "commands": commands,
        "preflight": before,
    }
    OFFLINE_BUILD.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "build"))
    parser.add_argument("--pio", type=Path)
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = preflight() if args.command == "preflight" else build(pio=args.pio, clean=not args.no_clean)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"P2-C offline build blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
