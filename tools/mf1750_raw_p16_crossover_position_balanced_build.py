#!/usr/bin/env python3
"""Offline build bootstrap for the six RAW-P16 crossover images.

This tool invokes PlatformIO ``run`` only. It has no upload target and never
opens a device, serial/COM port, relay, camera, or HTTP endpoint. The ``build``
command performs an artifact-free contract preflight, builds the six isolated
environments in sequence, and then enforces every reviewed BIN/ELF hash.
"""

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
    mf1750_raw_p16_crossover_position_balanced_once as campaign,
)


CONFIGS = (
    "platformio.raw_p16_crossover_posbal_t1_ac_v1.ini",
    "platformio.raw_p16_crossover_w1_after_t1_white_v1.ini",
    "platformio.raw_p16_crossover_posbal_t2_ca_v1.ini",
    "platformio.raw_p16_crossover_w2_after_t2_white_v1.ini",
    "platformio.raw_p16_crossover_posbal_t3_ac_repeat_v1.ini",
    "platformio.raw_p16_crossover_w3_final_after_t3_white_v1.ini",
)


class BuildBootstrapError(RuntimeError):
    """Raised before claiming a reproducible six-image build."""


def _platformio_executable(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    discovered = shutil.which("pio")
    if discovered:
        candidates.append(Path(discovered))
    scripts = "Scripts" if os.name == "nt" else "bin"
    executable = "pio.exe" if os.name == "nt" else "pio"
    candidates.append(Path.home() / ".platformio" / "penv" / scripts / executable)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise BuildBootstrapError(
        "PlatformIO executable not found; install PlatformIO Core or pass --pio"
    )


def prebuild_validate() -> dict[str, Any]:
    """Validate identities/layout/fresh roots without requiring .pio artifacts."""

    return campaign.dry_validate(verify_artifacts=False)


def build_all(*, pio: Path | None = None) -> dict[str, Any]:
    """Build all six images, then require the reviewed artifact identities."""

    preflight = prebuild_validate()
    executable = _platformio_executable(pio)
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    commands: list[list[str]] = []
    for config in CONFIGS:
        if not (REPO_ROOT / config).is_file():
            raise BuildBootstrapError(f"missing reviewed build config: {config}")
        command = [str(executable), "run", "-c", config]
        commands.append(command)
        subprocess.run(  # noqa: S603
            command,
            cwd=REPO_ROOT,
            env=environment,
            check=True,
        )
    postflight = campaign.dry_validate(verify_artifacts=True)
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-position-balanced-build-bootstrap",
        "result": "PASS",
        "offline_build_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "platformio": str(executable),
        "commands": commands,
        "preflight": preflight,
        "postflight": postflight,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    build = sub.add_parser("build", allow_abbrev=False)
    build.add_argument("--pio", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        value = (
            prebuild_validate()
            if args.command == "preflight"
            else build_all(pio=args.pio)
        )
    except (BuildBootstrapError, OSError, subprocess.CalledProcessError) as error:
        print(f"RAW-P16 crossover build error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
