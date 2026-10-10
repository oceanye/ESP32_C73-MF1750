#!/usr/bin/env python3
"""Compile-only builder for the position-balanced V3 white successor."""

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

from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_once as runner,
)


CONFIG = "platformio.runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1.ini"


class BuildError(RuntimeError):
    """Raised before claiming an isolated compile-only build."""


def _platformio_executable(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    if discovered := shutil.which("pio"):
        candidates.append(Path(discovered))
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "pio.exe" if os.name == "nt" else "pio"
    candidates.append(Path.home() / ".platformio" / "penv" / scripts / executable)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise BuildError("PlatformIO executable not found; pass --pio")


def prebuild_validate() -> dict[str, Any]:
    report = runner.pack.build_report(verify_artifacts=False)
    return {
        "result": "PASS",
        "offline_only": True,
        "contract_id": report["contract_id"],
        "action_id": report["action_id"],
        "source_main_contract_id": runner.pack.SOURCE_MAIN_CONTRACT_ID,
    }


def build(*, pio: Path | None = None) -> dict[str, Any]:
    preflight = prebuild_validate()
    executable = _platformio_executable(pio)
    command = [str(executable), "run", "-c", CONFIG]
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    environment["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] = "0"
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    postflight = runner.dry_validate()
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-white-successor-v1-build",
        "result": "PASS",
        "offline_build_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "command": command,
        "preflight": preflight,
        "postflight": postflight,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    compile_parser = sub.add_parser("build", allow_abbrev=False)
    compile_parser.add_argument("--pio", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        value = (
            prebuild_validate() if args.command == "preflight" else build(pio=args.pio)
        )
    except (BuildError, OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"LUMA/GRAY V3 white successor build error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
