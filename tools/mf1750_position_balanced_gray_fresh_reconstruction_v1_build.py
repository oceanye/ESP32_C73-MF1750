#!/usr/bin/env python3
"""Compile-only builder for the sealed fresh reconstruction firmware."""

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
    mf1750_position_balanced_gray_fresh_reconstruction_v1_codegen as codegen,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as pack,
)

CONFIG = "platformio.position_balanced_gray_fresh_reconstruction_v1.ini"


class FreshReconstructionBuildError(RuntimeError):
    """Raised before an unsealed or invalid compile-only build."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    raise FreshReconstructionBuildError("PlatformIO executable not found; pass --pio")


def preflight() -> dict[str, Any]:
    return pack.dry_validate(require_sealed=True, verify_artifacts=False)


def _artifact_candidate() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, path in zip(("bin", "elf"), pack.artifact_paths(), strict=True):
        if not path.is_file() or path.is_symlink():
            raise FreshReconstructionBuildError(f"compiled {label} missing")
        payload = path.read_bytes()
        result[label] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": _sha(payload),
        }
    return result


def build(*, pio: Path | None = None) -> dict[str, Any]:
    preflight_report = preflight()
    generated = codegen.generate()
    config_path = REPO_ROOT / CONFIG
    if not config_path.is_file() or config_path.is_symlink():
        raise FreshReconstructionBuildError("isolated PlatformIO config missing")
    executable = _platformio_executable(pio)
    command = [str(executable), "run", "-c", CONFIG]
    environment = dict(os.environ)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    environment["PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL"] = "0"
    subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)  # noqa: S603
    candidate = _artifact_candidate()
    artifact_status = (
        "SEALED_AND_VERIFIED"
        if pack.artifacts_are_sealed()
        else "CANDIDATE_HASHES_REQUIRE_EXPLICIT_PACK_BINDING"
    )
    if pack.artifacts_are_sealed():
        pack.verify_artifact_files()
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-fresh-reconstruction-v1-build",
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
        "preflight": preflight_report,
        "generated": generated,
        "artifact_status": artifact_status,
        "artifact_candidate": candidate,
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
    except (
        FreshReconstructionBuildError,
        OSError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        print(f"fresh reconstruction build blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
