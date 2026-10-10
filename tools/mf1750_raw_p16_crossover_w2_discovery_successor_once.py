#!/usr/bin/env python3
"""Fail-closed host for one fresh post-T2-discovery OTP-white action.

No command flashes firmware, resets the ESP32, controls J2, retries, recovers,
or chains to another action.  The diagnostic command performs only the
reviewed read-only GET sequence; ``run-white`` can consume exactly one action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as pack,
)


class WhiteSuccessorRunnerError(RuntimeError):
    """Raised before a stale or unsealed containment action can run."""


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load isolated white host: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_w2_t2_discovery_successor_white_claims"
    )


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_W2_T2_DISCOVERY_SUCCESSOR_WHITE_20260830_V1"
    )


def _artifact_binding() -> dict[str, dict[str, Any]]:
    values = pack.WHITE_ARTIFACTS[pack.STAGE]
    firmware_bin, firmware_elf = pack.white_artifact_paths()
    return {
        "bin": {
            "path": firmware_bin,
            "bytes": values["bin_bytes"],
            "sha256": values["bin_sha256"],
        },
        "elf": {
            "path": firmware_elf,
            "bytes": values["elf_bytes"],
            "sha256": values["elf_sha256"],
        },
    }


def _verify_binding(binding: Mapping[str, Mapping[str, Any]]) -> None:
    for name in ("bin", "elf"):
        item = binding[name]
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise WhiteSuccessorRunnerError(
                f"sealed {name} artifact is missing: {path}"
            )
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise WhiteSuccessorRunnerError(
                f"sealed {name} artifact identity differs: {path}"
            )


def _adapter() -> SimpleNamespace:
    cfg = pack.CONFIG
    report = pack.build_white_report()
    action = report["action"]
    binding = _artifact_binding()

    def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
        if verify_artifacts:
            _verify_binding(binding)
        return deepcopy(report)

    return SimpleNamespace(
        BUILD_TAG=cfg.build_tag,
        TEST_ID=cfg.test_id,
        CAMPAIGN_ID=cfg.campaign_id,
        SOURCE_CAMPAIGN_ID=report["contract"]["source_campaign_id"],
        ENVIRONMENT=cfg.environment,
        PROFILE_ID="WF23_25",
        CONTRACT_ID=report["contract_id"],
        NVS_NAMESPACE=cfg.nvs_namespace,
        NVS_KEY=cfg.nvs_key,
        BASE_ROUTE=cfg.base_route,
        DEVICE_API_VERSION=pack.DEVICE_API_VERSION,
        IDENTITY_REVISION=pack.IDENTITY_REVISION,
        CLASSIFICATION=pack.CLASSIFICATION,
        DESCRIPTOR_ID=action["descriptor_id"],
        ACTION_ID=action["action_id"],
        DESCRIPTOR_MARKER=pack.marker(),
        FRAME_SHA256=pack.FACTORY_WHITE_FRAME_SHA256,
        DTM_SHA256=pack.FACTORY_WHITE_DTM_SHA256,
        FRAME_FNV1A=pack.FACTORY_WHITE_FRAME_FNV1A,
        DTM_FNV1A=pack.FACTORY_WHITE_DTM_FNV1A,
        FIRMWARE_BIN=Path(binding["bin"]["path"]),
        FIRMWARE_ELF=Path(binding["elf"]["path"]),
        FIRMWARE_BIN_BYTES=binding["bin"]["bytes"],
        FIRMWARE_BIN_SHA256=binding["bin"]["sha256"],
        FIRMWARE_ELF_BYTES=binding["elf"]["bytes"],
        FIRMWARE_ELF_SHA256=binding["elf"]["sha256"],
        ARM_INTENT=pack.WHITE_ARM_INTENT,
        EXECUTE_INTENT=pack.WHITE_EXECUTE_INTENT,
        CLAIM_KIND=("mf1750-raw-p16-crossover-w2-t2-discovery-successor-white-claim"),
        RESULT_KIND=("mf1750-raw-p16-crossover-w2-t2-discovery-successor-white-result"),
        build_report=build_report,
    )


def _configure_white() -> Any:
    adapter = _adapter()
    host = _load_module(
        REPO_ROOT
        / "tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_once.py",
        "_mf1750_p16x_w2_t2_discovery_successor_white_host",
    )
    report = adapter.build_report(verify_artifacts=False)
    action = report["action"]
    endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    host.pack = adapter
    host.REPORT = report
    host.ACTION = action
    host.ENDPOINTS = endpoints
    host.base.pack = adapter
    host.base.REPORT = report
    host.base.ACTION = action
    host.base.ENDPOINTS = endpoints
    host.base._base.pack = adapter  # noqa: SLF001
    host.base._base.REPORT = report  # noqa: SLF001
    host.base._base.ACTION = action  # noqa: SLF001
    host.base._base.ENDPOINTS = endpoints  # noqa: SLF001
    host.DEFAULT_CLAIMS = _claim_root()
    host.DEFAULT_OUTPUT = _output_root()
    host.DIAGNOSTIC_OUTPUT = host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS
    host.base.DEFAULT_OUTPUT = host.DEFAULT_OUTPUT
    host.base.DIAGNOSTIC_OUTPUT = host.DIAGNOSTIC_OUTPUT
    host.base.DIAGNOSTIC_KIND = (
        "mf1750-raw-p16-crossover-w2-t2-discovery-successor-white-j2-off-diagnostic"
    )
    host.base.ATTEMPT_KIND = (
        "mf1750-raw-p16-crossover-w2-t2-discovery-successor-white-attempt"
    )
    return host


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    pack_validation = pack.dry_validate()
    if verify_artifacts:
        _verify_binding(_artifact_binding())
    host = _configure_white()
    expected_endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.ENDPOINTS != expected_endpoints:
        raise WhiteSuccessorRunnerError("fresh endpoint set differs")
    if "w2-after-t2-white-v1" in json.dumps(expected_endpoints, sort_keys=True):
        raise WhiteSuccessorRunnerError("frozen W2 route leaked into successor")
    return {
        **pack_validation,
        "kind": (
            "mf1750-raw-p16-crossover-w2-discovery-successor-white-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
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
        if args.command == "describe":
            value = pack.build_white_report()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-white-j2-off":
            host = _configure_white()
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            host = _configure_white()
            value = host.run_once(
                args.base_url,
                claims=host.base.DEFAULT_CLAIMS,
                output=host.base.DEFAULT_OUTPUT / "action-01-factory-otp-white.json",
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (WhiteSuccessorRunnerError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 W2 discovery-successor white error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
