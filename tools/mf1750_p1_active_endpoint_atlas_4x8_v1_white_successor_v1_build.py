#!/usr/bin/env python3
"""Compile-only builder for the P1 ordinal-1 white successor."""

from __future__ import annotations

import argparse
import hashlib
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
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_codegen as codegen,
)
from tools import (  # noqa: E402
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_pack as pack,
)

CONFIG = "platformio.p1_active_endpoint_atlas_4x8_v1_white_successor_v1.ini"


class P1WhiteSuccessorBuildError(RuntimeError):
    """Raised before an invalid compile-only white build."""


def _platformio(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    if discovered := shutil.which("pio"):
        candidates.append(Path(discovered))
    scripts = "Scripts" if os.name == "nt" else "bin"
    candidates.append(
        Path.home()
        / ".platformio"
        / "penv"
        / scripts
        / ("pio.exe" if os.name == "nt" else "pio")
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise P1WhiteSuccessorBuildError("PlatformIO executable not found")


def preflight() -> dict[str, Any]:
    if not pack.source_artifacts_are_sealed():
        raise P1WhiteSuccessorBuildError("P1 source artifacts are not sealed")
    report = pack.build_report(verify_artifacts=False)
    return {
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "accepted_source_ordinals": [1],
        "source_artifacts_sealed": True,
    }


def build(*, pio: Path | None = None) -> dict[str, Any]:
    before = preflight()
    generated = codegen.generate()
    executable = _platformio(pio)
    command = [str(executable), "run", "-c", CONFIG]
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    environment["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] = "0"
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    artifacts: dict[str, dict[str, Any]] = {}
    for label, path in zip(("bin", "elf"), pack.artifact_paths(), strict=True):
        if not path.is_file() or path.is_symlink():
            raise P1WhiteSuccessorBuildError(f"compiled {label} missing")
        payload = path.read_bytes()
        artifacts[label] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    if pack.artifacts_are_sealed():
        pack.build_report(verify_artifacts=True)
    return {
        "schema_version": 1,
        "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-build",
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
        "preflight": before,
        "generated": generated,
        "artifact_status": (
            "SEALED_AND_VERIFIED"
            if pack.artifacts_are_sealed()
            else "CANDIDATE_HASHES_REQUIRE_EXPLICIT_PACK_BINDING"
        ),
        "artifact_candidate": artifacts,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    compile_parser = sub.add_parser("build", allow_abbrev=False)
    compile_parser.add_argument("--pio", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        value = preflight() if args.command == "preflight" else build(pio=args.pio)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"P1 white successor build blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
