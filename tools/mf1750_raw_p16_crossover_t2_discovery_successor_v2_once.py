#!/usr/bin/env python3
"""Fail-closed host for one exposure-corrected T2 V2 discovery action.

This host does not flash, reset, control J2, retry, recover, chain, or capture.
It reuses the reviewed V1 transport mechanically while replacing every
campaign identity and requiring the sealed V1 underexposure authority.
"""

from __future__ import annotations

from copy import deepcopy
import argparse
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
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as pack,
)


class DiscoveryV2RunnerError(RuntimeError):
    """Raised before stale or unbound V2 I/O can occur."""


def _load_v1_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_t2_discovery_successor_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_t2_discovery_successor_v2_base", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load frozen T2 V1 host: {path}")
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
            raise DiscoveryV2RunnerError(f"sealed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise DiscoveryV2RunnerError(
                f"sealed {name} artifact identity differs: {path}"
            )


def _validate_repeat_boundary(host: Any, value: Mapping[str, Any]) -> None:
    observed = value.get("repeat_authority")
    expected = pack.repeat_authority_binding()
    if not isinstance(observed, Mapping):
        raise host.base.runner.RecheckError("T2 V2 repeat authority is absent")
    for key in (
        "kind",
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "state",
        "underexposed_measurement_only",
        "visible_payload_failure_claimed",
        "authorizes_fresh_discovery_repeat_only",
        "white_reference_min_lstar",
    ):
        if observed.get(key) != expected.get(key):
            raise host.base.runner.RecheckError(
                f"T2 V2 repeat authority {key} differs"
            )
    if observed.get("exposure") != pack.CAPTURE_PLAN["exposure"]:
        raise host.base.runner.RecheckError("T2 V2 capture exposure differs")
    if observed.get("automatic_threshold_relaxation") is not False:
        raise host.base.runner.RecheckError("T2 V2 threshold boundary differs")


def _set_roots(host: Any) -> None:
    output = (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2"
    )
    claims = (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_t2_ca_coarse_discovery_successor_v2_claims"
    )
    diagnostic = output / "j2-off-diagnostic.json"
    actions = {1: output / "action-01-position-balanced-atlas.json"}
    host.DEFAULT_OUTPUT = output
    host.DEFAULT_CLAIMS = claims
    host.DIAGNOSTIC_OUTPUT = diagnostic
    host.ACTION_OUTPUTS = actions
    host.base.runner.DEFAULT_OUTPUT = output
    host.base.runner.DEFAULT_CLAIMS = claims


def configure() -> Any:
    """Return the isolated V2 host without touching hardware."""

    pack.validate_coarse_authority()
    pack.validate_repeat_authority()
    isolated = _load_v1_runner()
    host = isolated.configure()

    # The reviewed transport host defaults to the V1 external-white role.  V2
    # deliberately strengthens that role with the exact exposure requirement;
    # rebind the validator global to the identity emitted by the V2 firmware.
    host._FACTORY_WHITE_ANCHOR_ROLE = pack.FACTORY_WHITE_ANCHOR_ROLE  # noqa: SLF001

    # The transport adapter builds the wire-shaped action from the frozen V1
    # host and therefore retains round=1.  V2 emits the same payload under a
    # fresh round=2 identity, so bind that one field from the reviewed V2 pack.
    report_actions = pack.build_report()["actions"]
    wire_actions = deepcopy(host.base.runner.ACTIONS)
    if len(wire_actions) != len(report_actions):
        raise DiscoveryV2RunnerError("V2 wire action count differs")
    for wire_action, report_action in zip(wire_actions, report_actions, strict=True):
        wire_action["round"] = report_action["round"]
    host.base.runner.ACTIONS = tuple(wire_actions)
    host.base.runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in wire_actions
    )
    host.base.runner.ACTION_IDS = tuple(item["action_id"] for item in wire_actions)

    original_version = host._validate_version  # noqa: SLF001
    original_manifest = host._validate_manifest  # noqa: SLF001

    def validate_version(value: Mapping[str, Any]) -> None:
        original_version(value)
        _validate_repeat_boundary(host, value)

    def validate_manifest(value: Mapping[str, Any]) -> None:
        original_manifest(value)
        _validate_repeat_boundary(host, value)

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
        pack.validate_repeat_authority()
        _verify_artifacts()
        return original_diagnose(*args, **kwargs)

    def run_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pack.validate_repeat_authority()
        _verify_artifacts()
        return original_run(*args, **kwargs)

    host.diagnose_j2_off = diagnose_j2_off
    host.run_once = run_once
    host.DISCOVERY_AUTHORITY = deepcopy(pack.coarse_authority_binding())
    host.REPEAT_AUTHORITY = deepcopy(pack.repeat_authority_binding())
    host.CAPTURE_PLAN = deepcopy(pack.CAPTURE_PLAN)
    _set_roots(host)
    return host


def dry_validate(
    *,
    verify_authority: bool = True,
    verify_repeat_authority: bool = True,
    verify_artifacts: bool = True,
) -> dict[str, Any]:
    value = pack.dry_validate(
        verify_authority=verify_authority,
        verify_repeat_authority=verify_repeat_authority,
    )
    if verify_artifacts:
        _verify_artifacts()
    host = configure()
    report = pack.build_report()
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-"
            "successor-v2-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "default_evidence_root": str(host.DEFAULT_OUTPUT),
        "claim_root": str(host.DEFAULT_CLAIMS),
        "campaign_id": report["contract"]["campaign_id"],
        "repeat_authority": deepcopy(pack.repeat_authority_binding()),
        "capture_plan": deepcopy(pack.CAPTURE_PLAN),
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
        DiscoveryV2RunnerError,
        pack.DiscoveryV2PackError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"RAW-P16 T2 discovery V2 error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
