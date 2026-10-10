#!/usr/bin/env python3
"""Fail-closed W7 white host for the exact completed T4 successor V3 action.

No command flashes, resets, controls J2, retries, recovers, or chains. The two
live entry points refuse all device I/O unless the isolated artifacts are sealed
and the fixed T4 V3 result file proves one complete-pass visible action.
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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_once as source_once,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_pack as pack,
)


class W7RunnerError(RuntimeError):
    """Raised before stale, unsealed, or wrong-lineage W7 I/O can occur."""


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / (
            ".mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v3_white_v1_claims"
        )
    )


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / (
            "MF1750_RAW_P16_CROSSOVER_W7_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V3_WHITE_20260831_V1"
        )
    )


def _load_w2_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_w2_discovery_successor_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_w7_t4_active_header_ca_r20_swap_successor_v3_white_base",
        path,
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
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-v1-claim"
        )
        value.RESULT_KIND = (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-v1-result"
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
    if not pack.artifacts_are_sealed():
        raise W7RunnerError("W7 artifacts are not sealed; live entry points disabled")
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise W7RunnerError(f"sealed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if (
            len(payload) != item["bytes"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise W7RunnerError(f"sealed {name} artifact identity differs: {path}")


def _expected_source_complete_evidence() -> Path:
    # The V3 host has one fixed ordinal and one fixed O_EXCL output name.  Use
    # its isolated output-root function directly: configuring the V3 mechanics
    # here would mutate shared adapter modules after the W7 white adapter was
    # configured and could make an otherwise read-only preflight order-sensitive.
    return (
        source_once._output_root()  # noqa: SLF001
        / "action-01-position-balanced-atlas.json"
    ).resolve()


def _validate_source_complete_evidence(path: Path | None = None) -> dict[str, Any]:
    expected_path = _expected_source_complete_evidence()
    evidence_path = expected_path if path is None else Path(path).resolve()
    if evidence_path != expected_path:
        raise W7RunnerError(
            "source completion evidence must be the fixed T4 V3 action output"
        )
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise W7RunnerError(f"T4 V3 complete action evidence missing: {evidence_path}")
    payload = evidence_path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W7RunnerError("T4 V3 complete action evidence is not JSON") from error
    if not isinstance(value, Mapping):
        raise W7RunnerError("T4 V3 complete action evidence root differs")
    body = deepcopy(dict(value))
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != pack.sha256_bytes(pack.canonical_json(body))
    ):
        raise W7RunnerError("T4 V3 complete action evidence integrity differs")
    expected_source = pack.build_white_report()["contract"]["source"]
    expected_source_action = pack.source.build_report()["actions"][0]
    source_action = value.get("action")
    terminal = value.get("terminal_report")
    if (
        value.get("kind")
        != (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-result"
        )
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or not isinstance(source_action, Mapping)
        or dict(source_action) != expected_source_action
        or source_action.get("ordinal") != 1
        or source_action.get("action_id") != expected_source["action_id"]
        or source_action.get("descriptor_id") != expected_source["descriptor_id"]
        or source_action.get("round") != 4
        or source_action.get("global_header") != "active"
        or source_action.get("profile_id")
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or not isinstance(terminal, Mapping)
        or terminal.get("ordinal") != 1
        or terminal.get("action_id") != expected_source["action_id"]
        or terminal.get("descriptor_id") != expected_source["descriptor_id"]
        or terminal.get("contract_id") != expected_source["contract_id"]
        or terminal.get("campaign_id") != expected_source["campaign_id"]
        or terminal.get("role") != expected_source_action["role"]
        or terminal.get("round") != 4
        or terminal.get("profile_id")
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or terminal.get("global_header") != "active"
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("campaign_complete") is not True
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("next_ordinal") != 2
    ):
        raise W7RunnerError("T4 V3 complete-pass action semantics differ")
    forbidden = {
        *pack.build_white_report()["contract"]["rejected_failed_source_action_ids"],
        *pack.build_white_report()["contract"]["rejected_obsolete_white_action_ids"],
    }
    if source_action["action_id"] in forbidden:
        raise W7RunnerError("failed or obsolete predecessor became W7 source")
    return {
        "verified": True,
        "path": str(evidence_path),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": integrity["sha256"],
        "campaign_id": terminal["campaign_id"],
        "contract_id": terminal["contract_id"],
        "descriptor_id": terminal["descriptor_id"],
        "action_id": terminal["action_id"],
        "terminal_state": terminal["terminal_state"],
        "result": terminal["result"],
        "visible_refreshes": value["visible_refreshes"],
        "driver_call_count_for_action": terminal["driver_call_count_for_action"],
    }


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
        "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
        "confirmation-successor-v3-white-v1-j2-off-diagnostic"
    )
    host.base.ATTEMPT_KIND = (
        "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
        "confirmation-successor-v3-white-v1-attempt"
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
        raise W7RunnerError("W7 endpoint set differs")
    stale_tokens = (
        "w2-after-t2-coarse-discovery-successor-white-v1",
        "w3-after-t2-coarse-discovery-successor-v2-white-v1",
        "w4-after-t3-ac-profile-following-successor-white-v1",
        "w4-after-t3-ac-profile-following-successor-v2-white-v1",
        "w5-after-t4-active-header-ca-r20-swap-confirmation-white-v1",
        "w6-after-t4-active-header-ca-r20-swap-confirmation-successor-v2-white-v1",
    )
    serialized = json.dumps(expected_endpoints, sort_keys=True)
    if any(token in serialized for token in stale_tokens):
        raise W7RunnerError("prior white route leaked into W7")
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-w7-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-white-runner-validation"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "endpoint_set": expected_endpoints,
        "claim_root": str(_claim_root()),
        "output_root": str(_output_root()),
        "expected_source_complete_evidence": str(
            _expected_source_complete_evidence()
        ),
        "source_complete_evidence_checked_during_offline_build": False,
        "source_complete_evidence_required_before_any_live_device_request": True,
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
    diag.add_argument("--source-complete-evidence", type=Path)
    diag.add_argument("--timeout", type=float, default=10.0)
    white = sub.add_parser("run-white", allow_abbrev=False)
    white.add_argument("--base-url", required=True)
    white.add_argument("--confirm-j2-on", action="store_true", required=True)
    white.add_argument("--source-complete-evidence", type=Path)
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
            _verify_artifacts()
            _validate_source_complete_evidence(args.source_complete_evidence)
            host = _configure_white()
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            _verify_artifacts()
            _validate_source_complete_evidence(args.source_complete_evidence)
            host = _configure_white()
            value = host.run_once(
                args.base_url,
                claims=host.base.DEFAULT_CLAIMS,
                output=host.base.DEFAULT_OUTPUT / "action-01-factory-otp-white.json",
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (W7RunnerError, pack.W7PackError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 W7 T4 CA-R20 swap successor V3 white error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
