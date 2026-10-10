#!/usr/bin/env python3
"""Compile one canonical N3A or N3B exact execution plan, offline only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import canonical_json_bytes  # noqa: E402
from tools import g1_s1_n3_execution_contract as execution  # noqa: E402
from tools import g1_s1_rc2g_n2_photo_campaign_analyzer as n2_analyzer  # noqa: E402
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner  # noqa: E402


class N3PlanCompilerError(RuntimeError):
    """The offline exact-plan compiler rejected its inputs."""


def _load_assets(path: Optional[Path]) -> Optional[Mapping[str, Any]]:
    if path is None:
        return None
    try:
        assets, _payload = n2_runner._strict_json_file(
            path, label="N3 measurement asset registry"
        )
    except (ValueError, RuntimeError, OSError) as error:
        raise N3PlanCompilerError(str(error)) from error
    return assets


def compile_from_args(args: argparse.Namespace) -> Mapping[str, Any]:
    assets = _load_assets(args.measurement_assets)
    if args.study == "n3b":
        return execution.compile_n3b_exact_plan(measurement_assets=assets)
    directories = {
        key: getattr(args, key.replace("-", "_"))
        for key in n2_analyzer.EXPECTED_RESULT_KEYS
    }
    return execution.compile_n3a_exact_plan(
        n2_result_directories=directories,
        repeat_count=args.repeat_count,
        measurement_assets=assets,
    )


def write_exact_plan(plan: Mapping[str, Any], output: Path) -> str:
    try:
        root = execution.validate_n3_exact_plan(plan)
        n2_runner.require_local_regular_path_syntax(
            output, label="N3 exact plan output"
        )
        n2_runner._reject_reparse_path_chain(
            output, label="N3 exact plan output"
        )
        output.parent.resolve(strict=True)
    except (ValueError, RuntimeError, OSError) as error:
        raise N3PlanCompilerError(f"N3 exact plan output is unsafe: {error}") from error
    payload = canonical_json_bytes(root)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise N3PlanCompilerError("N3 exact plan output already exists") from error
    except OSError as error:
        raise N3PlanCompilerError(f"could not write N3 exact plan: {error}") from error
    return execution.exact_plan_file_sha256(root)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--study", choices=("n3a", "n3b"), required=True)
    parser.add_argument("--repeat-count", choices=(2, 3, 4), type=int)
    parser.add_argument("--measurement-assets", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    for key in n2_analyzer.EXPECTED_RESULT_KEYS:
        parser.add_argument(f"--n2-{key}-dir", dest=key.replace("-", "_"), type=Path)
    args = parser.parse_args(argv)
    n2_values = [getattr(args, key.replace("-", "_")) for key in n2_analyzer.EXPECTED_RESULT_KEYS]
    if args.study == "n3a":
        if args.repeat_count is None or any(value is None for value in n2_values):
            parser.error(
                "N3A requires --repeat-count and all eight --n2-*-dir finalized bundles"
            )
    elif args.repeat_count is not None or any(value is not None for value in n2_values):
        parser.error("N3B does not accept N2 winner directories or a repeat selection")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        plan = compile_from_args(args)
        file_sha = write_exact_plan(plan, args.output)
    except (N3PlanCompilerError, execution.N3ExecutionContractError) as error:
        print(str(error), file=sys.stderr)
        return 2
    summary = {
        "plan_id": plan["plan_id"],
        "study": plan["study"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": file_sha,
        "route_count": len(plan["selected_routes"]),
        "action_count": len(plan["fixed_actions"]),
        "measurement_assets_ready": plan["readiness"]["measurement_assets_ready"],
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N3PlanCompilerError",
    "compile_from_args",
    "main",
    "parse_args",
    "write_exact_plan",
]
