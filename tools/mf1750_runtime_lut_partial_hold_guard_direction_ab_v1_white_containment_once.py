#!/usr/bin/env python3
"""One-shot guard-direction A/B factory-OTP white containment host.

``diagnose-j2-off`` performs exactly four direct, no-proxy GETs and creates
no claim. ``run`` uses a fresh independent NVS identity and permanent claim,
then sends at most one ARM and one EXECUTE. It never flashes, resets, controls
power, retries, recovers, autochains, or skips an action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment_pack as pack,
)


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_hue_brightness_blue_v1_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_guard_direction_ab_white_containment_private_host", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load containment mechanics: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

REPORT = pack.build_report(verify_artifacts=False)
ACTION = REPORT["action"]
ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_guard_direction_ab_white_containment_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_20260824_V1"
)

# Rebind only this dynamically loaded private host and its private low-level
# validator. No older campaign module is mutated.
base.pack = pack
base._base.pack = pack  # noqa: SLF001
base._base.REPORT = REPORT  # noqa: SLF001
base._base.ACTION = ACTION  # noqa: SLF001
base._base.ENDPOINTS = ENDPOINTS  # noqa: SLF001
base.ACTION = ACTION
base.ENDPOINTS = ENDPOINTS
base.DEFAULT_CLAIMS = DEFAULT_CLAIMS
base.DEFAULT_OUTPUT = DEFAULT_OUTPUT
base.DIAGNOSTIC_KIND = "mf1750-guard-direction-ab-white-containment-j2-off-diagnostic"
base.ATTEMPT_KIND = "mf1750-guard-direction-ab-white-containment-attempt"

ContainmentError = base.ContainmentError
ContainmentConsumedError = base.ContainmentConsumedError
Requester = base.Requester
_default_requester = base._default_requester  # noqa: SLF001


def diagnose_j2_off(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return base.diagnose_j2_off(*args, **kwargs)


def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return base.run_once(*args, **kwargs)


def describe() -> dict[str, Any]:
    value = base.describe()
    value["purpose"] = (
        "guard_direction_ab_independent_fresh_factory_otp_white_fault_containment"
    )
    value["source_campaign_id"] = pack.SOURCE_CAMPAIGN_ID
    value["independent_nvs_and_claims"] = True
    value["artifact_binding_status"] = deepcopy(pack.artifact_binding_status())
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    diagnostic = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, required=True)
    diagnostic.add_argument("--timeout", type=float, default=10.0)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=10.0)
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=base.BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    )
    run.add_argument("--poll-count", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            value = run_once(
                args.base_url,
                claims=args.claims,
                output=args.output,
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except ContainmentError as exc:
        print(f"guard-direction containment error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
