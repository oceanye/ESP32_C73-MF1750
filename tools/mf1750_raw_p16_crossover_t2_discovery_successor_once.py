#!/usr/bin/env python3
"""Fail-closed runner for one fresh T2-CA coarse-discovery action.

This host never flashes firmware, resets the ESP32, controls J2, retries,
recovers, or chains.  It reuses the reviewed one-action RAW-P16 host mechanics
under a fresh campaign identity and additionally verifies the immutable T1
coarse-screen authority before any device request.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as pack,
)


class DiscoveryRunnerError(RuntimeError):
    """Raised before stale or unbound discovery I/O can occur."""


def _load_isolated_base() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_position_balanced_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_t2_discovery_successor_base", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load reviewed crossover host: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pack = pack
    return module


def _artifact_binding() -> dict[str, dict[str, Any]]:
    values = pack.ARTIFACTS[pack.STAGE]
    firmware_bin, firmware_elf = pack.artifact_paths()
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
            raise DiscoveryRunnerError(f"reviewed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise DiscoveryRunnerError(
                f"reviewed {name} artifact identity differs: {path}"
            )


def _validate_discovery_boundary(host: Any, value: Mapping[str, Any]) -> None:
    expected = pack.coarse_authority_binding()
    if value.get("coarse_discovery_authority") != expected:
        raise host.base.runner.RecheckError(
            "T2 discovery coarse-screen authority binding differs"
        )
    if value.get("coarse_discovery_only") is not True:
        raise host.base.runner.RecheckError("T2 discovery-only capability differs")
    if value.get("formal_gate_evaluated") is not False:
        raise host.base.runner.RecheckError("T2 formal gate boundary differs")
    if value.get("formal_advance_to_t2_permitted") is not False:
        raise host.base.runner.RecheckError("T2 formal advance boundary differs")


def configure() -> Any:
    """Return the isolated successor host without touching hardware."""

    pack.validate_coarse_authority()
    isolated = _load_isolated_base()
    host = isolated._configure_atlas(pack.STAGE)  # noqa: SLF001

    original_version = host._validate_version  # noqa: SLF001
    original_manifest = host._validate_manifest  # noqa: SLF001

    def validate_version(value: Mapping[str, Any]) -> None:
        original_version(value)
        _validate_discovery_boundary(host, value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        original_manifest(value)
        _validate_discovery_boundary(host, value)

    host._validate_version = validate_version
    host._validate_manifest = validate_manifest
    host.v3._validate_version = validate_version
    host.v3._validate_manifest = validate_manifest
    host.base._validate_version = validate_version
    host.base._validate_manifest = validate_manifest
    host.base.runner._validate_version = validate_version
    host.base.runner._validate_manifest = validate_manifest

    original_diagnose = host.diagnose_j2_off
    original_run = host.run_once

    def diagnose_j2_off(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pack.validate_coarse_authority()
        _verify_artifacts()
        return original_diagnose(*args, **kwargs)

    def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pack.validate_coarse_authority()
        _verify_artifacts()
        return original_run(*args, **kwargs)

    host.diagnose_j2_off = diagnose_j2_off
    host.run_once = run_once
    host.DISCOVERY_AUTHORITY = deepcopy(pack.coarse_authority_binding())
    host.DEFAULT_OUTPUT = host.base.runner.DEFAULT_OUTPUT
    host.DEFAULT_CLAIMS = host.base.runner.DEFAULT_CLAIMS
    return host


def dry_validate(
    *, verify_authority: bool = True, verify_artifacts: bool = True
) -> dict[str, Any]:
    pack_value = pack.dry_validate(verify_authority=verify_authority)
    if verify_artifacts:
        _verify_artifacts()
    report = pack.build_report()
    return {
        **pack_value,
        "kind": "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-runner-validation",
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "default_evidence_root": str(
            REPO_ROOT
            / ".test-output/hardware"
            / f"MF1750_RAW_P16_CROSSOVER_{pack.CONFIG.suffix}_20260830_V1"
        ),
        "campaign_id": report["contract"]["campaign_id"],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument("--timeout", type=float, default=10.0)
    action = sub.add_parser("run", allow_abbrev=False)
    action.add_argument("--base-url", required=True)
    action.add_argument("--confirm-j2-on", action="store_true", required=True)
    action.add_argument(
        "--confirm-external-pre-white", action="store_true", required=True
    )
    action.add_argument("--poll-seconds", type=float, default=65.0)
    action.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = pack.build_report()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_authority=True, verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            host = configure()
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            host = configure()
            value = host.run_once(
                args.base_url,
                1,
                claims=host.DEFAULT_CLAIMS,
                output=host.ACTION_OUTPUTS[1],
                confirm_j2_on=args.confirm_j2_on,
                confirm_external_pre_white=args.confirm_external_pre_white,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (
        DiscoveryRunnerError,
        pack.DiscoveryPackError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"RAW-P16 T2 discovery error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
