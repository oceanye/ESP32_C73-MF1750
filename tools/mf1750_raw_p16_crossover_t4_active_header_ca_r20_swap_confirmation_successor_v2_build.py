#!/usr/bin/env python3
"""Compile-only builder for fresh T4 matched-swap successor V2."""

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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_once as runner,
)


CONFIG = (
    "platformio.raw_p16_crossover_t4_active_header_ca_r20_"
    "swap_confirmation_successor_v2.ini"
)


class BuildError(RuntimeError):
    """Raised before claiming a successful isolated V2 build."""


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
    raise BuildError("PlatformIO executable not found")


def prebuild_validate() -> dict[str, Any]:
    return runner.dry_validate(verify_artifacts=False)


def build(*, pio: Path | None = None) -> dict[str, Any]:
    preflight = prebuild_validate()
    executable = _platformio_executable(pio)
    config = REPO_ROOT / CONFIG
    if not config.is_file():
        raise BuildError(f"missing isolated config: {config}")
    command = [str(executable), "run", "-c", CONFIG]
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    postflight = runner.dry_validate()
    return {
        "schema_version": 2,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-build-v2"
        ),
        "result": "PASS",
        "offline_build_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "platformio": str(executable),
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
        print(f"RAW-P16 T4 V2 matched-swap build error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
