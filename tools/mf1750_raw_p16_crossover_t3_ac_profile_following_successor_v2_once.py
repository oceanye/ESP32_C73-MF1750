#!/usr/bin/env python3
"""Fail-closed host for one fresh T3 AC profile-following successor V2.

The module reuses the reviewed V1 transport implementation, but replaces every
campaign, route, action, NVS, evidence, and claim identity with V2.  It performs
no discovery and has no default base URL: any future live entry point requires
one explicit ``--base-url`` argument.
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
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as pack,
)


class T3ProfileFollowingV2RunnerError(RuntimeError):
    """Raised before stale, unsealed, or predecessor-bound V2 I/O can occur."""


def _load_v1_transport() -> Any:
    path = (
        REPO_ROOT
        / "tools/mf1750_raw_p16_crossover_t3_ac_profile_following_successor_once.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_t3_ac_profile_following_v2_transport", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load reviewed T3 V1 transport: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pack = pack
    return module


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2"
    )


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_claims"
    )


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
    if not pack.artifacts_are_sealed():
        raise T3ProfileFollowingV2RunnerError(
            "T3 AC successor V2 artifacts are not sealed; live entry points disabled"
        )
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise T3ProfileFollowingV2RunnerError(
                f"sealed V2 {name} artifact missing: {path}"
            )
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise T3ProfileFollowingV2RunnerError(
                f"sealed V2 {name} artifact identity differs: {path}"
            )


def _set_roots(host: Any) -> None:
    output = _output_root()
    claims = _claim_root()
    host.DEFAULT_OUTPUT = output
    host.DEFAULT_CLAIMS = claims
    host.DIAGNOSTIC_OUTPUT = output / "j2-off-diagnostic.json"
    host.ACTION_OUTPUTS = {1: output / "action-01-position-balanced-atlas.json"}
    host.base.runner.DEFAULT_OUTPUT = output
    host.base.runner.DEFAULT_CLAIMS = claims


def _validate_v2_boundary(host: Any, value: Mapping[str, Any]) -> None:
    exact = {
        "v1_terminal_failure_authority": pack.v1_failure_authority_binding(),
        "address_resolution_boundary": pack.address_resolution_boundary_binding(),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise host.base.runner.RecheckError(f"T3 AC successor V2 {key} differs")


def _assert_v2_executable_identity(transport: Any, host: Any) -> None:
    transport._assert_executable_identity(host)  # noqa: SLF001
    report = pack.build_report()
    action = report["actions"][0]
    if (
        action.get("supersedes_failed_unmutated_v1_action_id")
        != pack.v1_failure_authority_binding()["predecessor_action_id"]
    ):
        raise T3ProfileFollowingV2RunnerError("V2 failed-predecessor binding differs")
    expected_endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.base.runner.ENDPOINTS != expected_endpoints:
        raise T3ProfileFollowingV2RunnerError("V2 endpoint allowlist differs")
    serialized = json.dumps(expected_endpoints, sort_keys=True)
    if (
        pack.CONFIG.base_route not in serialized
        or "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v1"
        in serialized
    ):
        raise T3ProfileFollowingV2RunnerError("V1 route leaked into V2 allowlist")


def configure() -> Any:
    """Return the isolated V2 host without touching hardware or the network."""

    pack.validate_authorities()
    transport = _load_v1_transport()
    host = transport.configure()

    original_version = host._validate_version  # noqa: SLF001
    original_manifest = host._validate_manifest  # noqa: SLF001

    def validate_version(value: Mapping[str, Any]) -> None:
        original_version(value)
        _validate_v2_boundary(host, value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        original_manifest(value)
        _validate_v2_boundary(host, value)

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
        pack.validate_authorities()
        _assert_v2_executable_identity(transport, host)
        _verify_artifacts()
        return original_diagnose(*args, **kwargs)

    def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pack.validate_authorities()
        _assert_v2_executable_identity(transport, host)
        _verify_artifacts()
        return original_run(*args, **kwargs)

    host.diagnose_j2_off = diagnose_j2_off
    host.run_once = run_once
    host.V1_TERMINAL_FAILURE_AUTHORITY = deepcopy(
        pack.v1_failure_authority_binding()
    )
    host.ADDRESS_RESOLUTION_BOUNDARY = deepcopy(
        pack.address_resolution_boundary_binding()
    )
    host.NON_REUSABLE_ACTION_IDS = tuple(pack.non_reusable_action_ids())
    _set_roots(host)
    _assert_v2_executable_identity(transport, host)
    return host


def dry_validate(
    *, verify_authorities: bool = True, verify_artifacts: bool = True
) -> dict[str, Any]:
    value = pack.dry_validate(verify_authorities=verify_authorities)
    if verify_artifacts:
        _verify_artifacts()
    host = configure()
    report = pack.build_report()
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-"
            "successor-v2-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "default_evidence_root": str(host.DEFAULT_OUTPUT),
        "claim_root": str(host.DEFAULT_CLAIMS),
        "campaign_id": report["contract"]["campaign_id"],
        "v1_terminal_failure_authority": deepcopy(
            pack.v1_failure_authority_binding()
        ),
        "address_resolution_boundary": deepcopy(
            pack.address_resolution_boundary_binding()
        ),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "explicit_base_url_required_for_live_cli": True,
        "default_base_url": None,
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
            result = pack.build_report()
        elif args.command == "prebuild-validate":
            result = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            result = dry_validate()
        elif args.command == "diagnose-j2-off":
            host = configure()
            result = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            host = configure()
            result = host.run_once(
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
        T3ProfileFollowingV2RunnerError,
        pack.T3ProfileFollowingPackError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"RAW-P16 T3 AC profile-following successor V2 error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
