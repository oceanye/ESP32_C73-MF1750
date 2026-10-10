#!/usr/bin/env python3
"""Fail-closed host for W4 white after the exact fresh T3 AC atlas.

No command flashes, resets, controls J2, retries, recovers, or chains.  The
module preserves offline inspection of the V1 evidence; its two former live
subcommands are parser-compatible tombstones that fail before host setup.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as pack,
)


class W4RunnerError(RuntimeError):
    """Raised before stale or unsealed W4 I/O can occur."""


TOMBSTONED_LIVE_COMMANDS = frozenset(
    {"diagnose-white-j2-off", "run-white"}
)
TOMBSTONE_REASON = (
    "W4 V1 live CLI is tombstoned; use the fresh T3 V2-paired W4 successor "
    "V2 white CLI"
)


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_claims"
    )


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_20260830_V1"
    )


def _load_w2_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_w2_discovery_successor_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_w4_t3_ac_profile_following_successor_white_base", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sealed white host: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pack = pack
    module._claim_root = _claim_root  # noqa: SLF001
    module._output_root = _output_root  # noqa: SLF001
    original_adapter = module._adapter  # noqa: SLF001

    def adapter() -> Any:
        value = original_adapter()
        value.CLAIM_KIND = (
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-successor-white-claim"
        )
        value.RESULT_KIND = (
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-successor-white-result"
        )
        return value

    module._adapter = adapter  # noqa: SLF001
    return module


def _artifact_binding() -> dict[str, dict[str, Any]]:
    values = pack.WHITE_ARTIFACTS[pack.STAGE]
    firmware_bin, firmware_elf = pack.white_artifact_paths()
    return {
        "bin": {
            "path": str(firmware_bin),
            "bytes": values["bin_bytes"],
            "sha256": values["bin_sha256"],
        },
        "elf": {
            "path": str(firmware_elf),
            "bytes": values["elf_bytes"],
            "sha256": values["elf_sha256"],
        },
    }


def _verify_artifacts() -> None:
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise W4RunnerError(f"sealed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise W4RunnerError(f"sealed {name} artifact identity differs: {path}")


def _configure_white() -> Any:
    base = _load_w2_runner()
    host = base._configure_white()  # noqa: SLF001
    host.DEFAULT_CLAIMS = _claim_root()
    host.DEFAULT_OUTPUT = _output_root()
    host.DIAGNOSTIC_OUTPUT = _output_root() / "j2-off-diagnostic.json"
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS
    host.base.DEFAULT_OUTPUT = host.DEFAULT_OUTPUT
    host.base.DIAGNOSTIC_OUTPUT = host.DIAGNOSTIC_OUTPUT
    host.base.DIAGNOSTIC_KIND = (
        "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
        "successor-white-j2-off-diagnostic"
    )
    host.base.ATTEMPT_KIND = (
        "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-successor-white-attempt"
    )
    return host


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    value = pack.dry_validate()
    if verify_artifacts:
        _verify_artifacts()
    host = _configure_white()
    expected_endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.ENDPOINTS != expected_endpoints:
        raise W4RunnerError("W4 endpoint set differs")
    stale_tokens = (
        "w2-after-t2-coarse-discovery-successor-white-v1",
        "w3-after-t2-coarse-discovery-successor-v2-white-v1",
        "w3-final-after-t3-white-v1",
    )
    serialized = json.dumps(expected_endpoints, sort_keys=True)
    if any(token in serialized for token in stale_tokens):
        raise W4RunnerError("prior white route leaked into W4")
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-w4-t3-ac-profile-following-"
            "successor-white-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "endpoint_set": expected_endpoints,
        "claim_root": str(_claim_root()),
        "output_root": str(_output_root()),
        "diagnostic_get_count": 4,
        "mutation_count_per_action": 2,
        "actions_per_campaign": 1,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-white-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument("--timeout", type=float, default=10.0)
    white = sub.add_parser("run-white", allow_abbrev=False)
    white.add_argument("--base-url", required=True)
    white.add_argument("--confirm-j2-on", action="store_true", required=True)
    white.add_argument("--poll-seconds", type=float, default=65.0)
    white.add_argument("--poll-count", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command in TOMBSTONED_LIVE_COMMANDS:
            raise W4RunnerError(TOMBSTONE_REASON)
        if args.command == "describe":
            value = pack.build_white_report()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate()
        else:
            raise W4RunnerError(f"unsupported command: {args.command}")
    except (W4RunnerError, pack.W4PackError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 W4 T3-profile-following white error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
