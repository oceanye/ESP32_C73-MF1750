#!/usr/bin/env python3
"""Fail-closed host for one fresh T3 AC profile-following review atlas.

This module directly configures the reviewed position-balanced transport.  It
does not inherit either T2 successor validator layer and never flashes, resets,
controls J2, retries, recovers, chains, or captures a photograph.
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
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as pack,
)


class T3ProfileFollowingRunnerError(RuntimeError):
    """Raised before stale, unsealed, or predecessor-bound I/O can occur."""


V1_TERMINAL_ACTION_ID = (
    "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104"
)
V1_SUCCESSOR_ROUTE = (
    "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v1"
)


def _load_position_balanced_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_position_balanced_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_t3_ac_profile_following_position_base", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load reviewed position-balanced host: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pack = pack
    return module


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260830_V1"
    )


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v1_claims"
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
        raise T3ProfileFollowingRunnerError(
            "T3 AC artifacts are not sealed; live entry points remain disabled"
        )
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise T3ProfileFollowingRunnerError(
                f"sealed {name} artifact missing: {path}"
            )
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise T3ProfileFollowingRunnerError(
                f"sealed {name} artifact identity differs: {path}"
            )


def _validate_review_boundary(host: Any, value: Mapping[str, Any]) -> None:
    exact = {
        "source_action_authority": pack.completed_t2_v2_action_binding(),
        "pre_white_action_evidence": pack.completed_w3_white_action_binding(),
        "pre_white_authority": pack.pre_white_authority_binding(),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "human_observation_plan": pack.HUMAN_OBSERVATION_PLAN,
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "human_observation_gate_after_every_action": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise host.base.runner.RecheckError(f"T3 AC review {key} differs")


def _set_roots(host: Any) -> None:
    output = _output_root()
    claims = _claim_root()
    host.DEFAULT_OUTPUT = output
    host.DEFAULT_CLAIMS = claims
    host.DIAGNOSTIC_OUTPUT = output / "j2-off-diagnostic.json"
    host.ACTION_OUTPUTS = {1: output / "action-01-position-balanced-atlas.json"}
    host.base.runner.DEFAULT_OUTPUT = output
    host.base.runner.DEFAULT_CLAIMS = claims


def _bind_wire_action(host: Any) -> None:
    report_action = pack.build_report()["actions"][0]
    wire_actions = deepcopy(host.base.runner.ACTIONS)
    if len(wire_actions) != 1:
        raise T3ProfileFollowingRunnerError("T3 AC wire action count differs")
    wire_action = wire_actions[0]
    wire_action["round"] = report_action["round"]
    wire_action["prior_static_action_id"] = report_action["prior_static_action_id"]
    host.base.runner.ACTIONS = tuple(wire_actions)
    host.base.runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in wire_actions
    )
    host.base.runner.ACTION_IDS = tuple(item["action_id"] for item in wire_actions)


def _assert_executable_identity(host: Any) -> None:
    report = pack.build_report()
    expected = report["actions"][0]
    actions = tuple(host.base.runner.ACTIONS)
    if len(actions) != 1:
        raise T3ProfileFollowingRunnerError("T3 AC executable count differs")
    observed = actions[0]
    for key in (
        "action_id",
        "descriptor_id",
        "role",
        "branch",
        "round",
        "profile_id",
        "global_header",
        "global_tuple_id",
        "prior_static_action_id",
    ):
        if observed.get(key) != expected.get(key):
            raise T3ProfileFollowingRunnerError(f"T3 AC executable {key} differs")
    if observed["action_id"] in pack.non_reusable_action_ids():
        raise T3ProfileFollowingRunnerError("predecessor action became executable")
    expected_endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.base.runner.ENDPOINTS != expected_endpoints:
        raise T3ProfileFollowingRunnerError("T3 AC endpoint allowlist differs")


def configure() -> Any:
    """Return the isolated successor host without touching hardware."""

    pack.validate_authorities()
    isolated = _load_position_balanced_runner()
    host = isolated._configure_atlas(pack.STAGE)  # noqa: SLF001

    # The reusable transport owns this validator global.  Bind it before
    # capturing the validators so the old generic anchor can never pass.
    host._FACTORY_WHITE_ANCHOR_ROLE = pack.FACTORY_WHITE_ANCHOR_ROLE  # noqa: SLF001
    _bind_wire_action(host)

    original_version = host._validate_version  # noqa: SLF001
    original_manifest = host._validate_manifest  # noqa: SLF001

    def validate_version(value: Mapping[str, Any]) -> None:
        original_version(value)
        _validate_review_boundary(host, value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        original_manifest(value)
        _validate_review_boundary(host, value)

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
        _assert_executable_identity(host)
        _verify_artifacts()
        return original_diagnose(*args, **kwargs)

    def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pack.validate_authorities()
        _assert_executable_identity(host)
        _verify_artifacts()
        return original_run(*args, **kwargs)

    host.diagnose_j2_off = diagnose_j2_off
    host.run_once = run_once
    host.SOURCE_ACTION_AUTHORITY = deepcopy(pack.completed_t2_v2_action_binding())
    host.PRE_WHITE_ACTION_EVIDENCE = deepcopy(pack.completed_w3_white_action_binding())
    host.PRE_WHITE_AUTHORITY = deepcopy(pack.pre_white_authority_binding())
    host.NON_REUSABLE_ACTION_IDS = tuple(pack.non_reusable_action_ids())
    host.HUMAN_OBSERVATION_PLAN = deepcopy(pack.HUMAN_OBSERVATION_PLAN)
    _set_roots(host)
    _assert_executable_identity(host)
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
            "successor-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "default_evidence_root": str(host.DEFAULT_OUTPUT),
        "claim_root": str(host.DEFAULT_CLAIMS),
        "campaign_id": report["contract"]["campaign_id"],
        "source_action_authority": deepcopy(pack.completed_t2_v2_action_binding()),
        "pre_white_action_evidence": deepcopy(pack.completed_w3_white_action_binding()),
        "pre_white_authority": deepcopy(pack.pre_white_authority_binding()),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "human_observation_plan": deepcopy(pack.HUMAN_OBSERVATION_PLAN),
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
    if args.command in {"diagnose-j2-off", "run"}:
        print(
            "RAW-P16 T3 AC profile-following successor V1 live CLI is "
            f"terminally tombstoned (action {V1_TERMINAL_ACTION_ID}); "
            "use a separately authorized fresh successor identity",
            file=sys.stderr,
        )
        return 2
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
        T3ProfileFollowingRunnerError,
        pack.T3ProfileFollowingPackError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"RAW-P16 T3 AC profile-following successor error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
