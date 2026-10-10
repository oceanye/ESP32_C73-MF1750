#!/usr/bin/env python3
"""Compile-only builder for POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1."""

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

from tools import mf1750_position_balanced_gray_hold_successor_v1_pack as pack  # noqa: E402

CONFIG = "platformio.position_balanced_gray_hold_successor_v1.ini"


class BuildError(RuntimeError):
    """Raised when compile-only validation fails."""


def _pio(explicit: Path | None = None) -> Path:
    candidates = [Path(explicit)] if explicit is not None else []
    if found := shutil.which("pio"):
        candidates.append(Path(found))
    candidates.append(Path.home() / ".platformio/penv/Scripts/pio.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise BuildError("PlatformIO executable not found; pass --pio")


def prebuild_validate() -> dict[str, Any]:
    # The live G3 file is deliberately pending until the predecessor runs.
    return pack.dry_validate(require_live_source=False, verify_artifacts=False)


def build(*, pio: Path | None = None) -> dict[str, Any]:
    preflight = prebuild_validate()
    executable = _pio(pio)
    command = [str(executable), "run", "-c", CONFIG]
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    environment["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] = "0"
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    return {
        "kind": "mf1750-position-balanced-gray-hold-successor-v1-offline-build",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "command": command,
        "preflight": preflight,
        "postflight": pack.dry_validate(
            require_live_source=False, verify_artifacts=True
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("preflight", "build"))
    parser.add_argument("--pio", type=Path)
    args = parser.parse_args(argv)
    try:
        value = (
            prebuild_validate() if args.command == "preflight" else build(pio=args.pio)
        )
    except (BuildError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"position-balanced gray HOLD build error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
