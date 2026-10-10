#!/usr/bin/env python3
"""Fail-closed W10 factory-white host after exact T4 V4 terminal evidence.

Dry commands are offline-only.  Both live commands first deeply authenticate
the fixed V4 COMPLETE primary output.  FAULT is reserved and fail-closed until
a reviewed V4 salvage/reconciliation producer exists.  A mere attempt/error
file is never sufficient.  This tool does not flash firmware, reset the ESP32,
or control the relay.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_once as source_once,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_confirmation_successor_v4_white_v1_pack as pack,
)


class W10RunnerError(RuntimeError):
    """Raised before unsealed, unterminated, or wrong-lineage W10 I/O."""


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / (
            ".mf1750_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_"
            "confirmation_successor_v4_white_v1_claims"
        )
    )


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / (
            "MF1750_RAW_P16_CROSSOVER_W10_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V4_WHITE_20260901_V1"
        )
    )


def _diagnostic_path() -> Path:
    return _output_root() / "j2-off-diagnostic.json"


def _source_terminal_paths() -> dict[str, Path]:
    root = source_once._output_root().resolve()  # noqa: SLF001
    return {
        "COMPLETE": root / "action-01-position-balanced-atlas.json",
        "FAULT": root / "action-01-terminal-read-only-salvage-reconciled.json",
    }


def _load_w2_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_w2_discovery_successor_once.py"
    spec = importlib.util.spec_from_file_location(
        "_mf1750_raw_p16_w10_t4_v4_complete_terminal_white_base",
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
            "mf1750-raw-p16-crossover-w10-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v4-white-v1-claim"
        )
        value.RESULT_KIND = (
            "mf1750-raw-p16-crossover-w10-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v4-white-v1-result"
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
        raise W10RunnerError("W10 artifacts are not sealed; live entry points disabled")
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise W10RunnerError(f"sealed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise W10RunnerError(f"sealed {name} artifact identity differs: {path}")


def _read_integrity_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes, str]:
    if not path.is_file() or path.is_symlink():
        raise W10RunnerError(f"{label} missing or unsafe: {path}")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W10RunnerError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise W10RunnerError(f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if not isinstance(integrity, Mapping):
        raise W10RunnerError(f"{label} integrity missing")
    if integrity.get("algorithm") != "sha256-canonical-json-without-integrity":
        raise W10RunnerError(f"{label} integrity algorithm differs")
    recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    actual = pack.sha256_bytes(pack.canonical_json(body))
    if recorded != actual:
        raise W10RunnerError(f"{label} canonical integrity differs")
    return value, payload, str(recorded)


def _select_source_terminal_path(path: Path | None = None) -> tuple[str, Path]:
    expected = _source_terminal_paths()
    complete_exists = expected["COMPLETE"].is_file()
    fault_exists = expected["FAULT"].is_file()
    if fault_exists:
        raise W10RunnerError(pack.FAULT_POLICY)
    if path is not None:
        resolved = Path(path).resolve()
        if resolved == expected["FAULT"].resolve():
            raise W10RunnerError(pack.FAULT_POLICY)
        if resolved != expected["COMPLETE"].resolve():
            raise W10RunnerError(
                "source terminal evidence path is not the fixed V4 COMPLETE output"
            )
        if not complete_exists:
            raise W10RunnerError("fixed T4 V4 COMPLETE evidence is missing")
        return "COMPLETE", resolved
    if complete_exists:
        return "COMPLETE", expected["COMPLETE"].resolve()
    raise W10RunnerError("no fixed deeply validated T4 V4 COMPLETE evidence exists")


def _validate_source_terminal_evidence(path: Path | None = None) -> dict[str, Any]:
    selected_state, evidence_path = _select_source_terminal_path(path)
    if selected_state != "COMPLETE":
        raise W10RunnerError(pack.FAULT_POLICY)
    value, payload, canonical_sha = _read_integrity_json(
        evidence_path,
        label=f"T4 V4 {selected_state} terminal evidence",
    )
    source_report = pack.source.build_report()
    expected_action = source_report["actions"][0]
    expected = pack.build_white_report()["contract"]["source"]
    validator = getattr(source_once, "validate_terminal_evidence", None)
    if not callable(validator):
        raise W10RunnerError("T4 V4 deep terminal validator is unavailable")
    try:
        deep = validator(evidence_path)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise W10RunnerError("T4 V4 deep terminal validation failed") from error
    if not isinstance(deep, Mapping):
        raise W10RunnerError("T4 V4 deep terminal validation result differs")
    expected_deep = {
        "verified": True,
        "terminal_state": selected_state,
        "campaign_id": expected["campaign_id"],
        "contract_id": expected["contract_id"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "firmware_sha256": expected["firmware"]["bin_sha256"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "action_must_not_be_retried": True,
        "source_success_claimed": True,
    }
    for key, wanted in expected_deep.items():
        if deep.get(key) != wanted:
            raise W10RunnerError(f"T4 V4 deep terminal {key} differs")
    action = value.get("action")
    terminal = value.get("terminal_report")
    if (
        not isinstance(action, Mapping)
        or dict(action) != expected_action
        or action.get("action_id") != expected["action_id"]
        or action.get("descriptor_id") != expected["descriptor_id"]
        or action.get("round") != 4
        or action.get("global_header") != "active"
        or action.get("profile_id")
        != "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535"
        or not isinstance(terminal, Mapping)
        or terminal.get("campaign_id") != expected["campaign_id"]
        or terminal.get("contract_id") != expected["contract_id"]
        or terminal.get("descriptor_id") != expected["descriptor_id"]
        or terminal.get("action_id") != expected["action_id"]
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("no_retry") is not True
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise W10RunnerError("T4 V4 terminal evidence lineage or one-driver semantics differ")

    expected_kind = (
        "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
        "swap-confirmation-successor-v4-result"
    )
    if (
        value.get("kind") != expected_kind
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("campaign_complete") is not True
        or terminal.get("next_ordinal") != 2
    ):
        raise W10RunnerError("T4 V4 COMPLETE evidence semantics differ")

    return {
        "verified": True,
        "branch": "SOURCE_COMPLETE_SUCCESS_BOUND_WHITE",
        "source_terminal_state": selected_state,
        "source_success_claimed": True,
        "source_fault_policy": pack.FAULT_POLICY,
        "path": str(evidence_path),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": canonical_sha,
        "campaign_id": expected["campaign_id"],
        "contract_id": expected["contract_id"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "action_must_not_be_retried": True,
        "deep_validation": deepcopy(dict(deep)),
    }


def _configure_white() -> Any:
    base = _load_w2_runner()
    host = base._configure_white()  # noqa: SLF001
    host.DEFAULT_CLAIMS = _claim_root()
    host.DEFAULT_OUTPUT = _output_root()
    host.DIAGNOSTIC_OUTPUT = _diagnostic_path()
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS
    host.base.DEFAULT_OUTPUT = host.DEFAULT_OUTPUT
    host.base.DIAGNOSTIC_OUTPUT = host.DIAGNOSTIC_OUTPUT
    host.base.DIAGNOSTIC_KIND = (
        "mf1750-raw-p16-crossover-w10-t4-v4-white-v1-j2-off-diagnostic"
    )
    host.base.ATTEMPT_KIND = "mf1750-raw-p16-crossover-w10-t4-v4-white-v1-attempt"
    device = pack.validate_intent_parity()
    if host.pack.ARM_INTENT != device["arm"] or host.pack.EXECUTE_INTENT != device["execute"]:
        raise W10RunnerError("configured W10 host intents differ from shared firmware")
    return host


def _validate_diagnostic_evidence(host: Any | None = None) -> dict[str, Any]:
    path = _diagnostic_path().resolve()
    value, payload, canonical_sha = _read_integrity_json(
        path,
        label="fixed W10 J2-OFF diagnostic",
    )
    transcript = value.get("transcript")
    if (
        value.get("kind")
        != "mf1750-raw-p16-crossover-w10-t4-v4-white-v1-j2-off-diagnostic"
        or value.get("outcome") != "j2_off_diagnostic_pass"
        or value.get("firmware_sha256") != pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"]
        or value.get("running_app_elf_sha256")
        != pack.WHITE_ARTIFACTS[pack.STAGE]["elf_sha256"]
        or value.get("action") != pack.build_white_report()["action"]
        or value.get("j2_confirmed_off") is not True
        or value.get("fresh_nvs") is not True
        or value.get("busy") != 0
        or value.get("report_terminal_state") != "NOT_EXECUTED"
        or value.get("permanent_claims_created") != 0
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("visible_refreshes") != 0
        or value.get("output_write_contract") != "O_EXCL"
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        != [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
        ]
    ):
        raise W10RunnerError("fixed W10 J2-OFF diagnostic envelope differs")
    selected_host = _configure_white() if host is None else host
    try:
        running_sha = selected_host.base._validate_version(transcript[0]["body"])  # noqa: SLF001
        selected_host.base._base._validate_manifest(transcript[1]["body"], running_sha)  # noqa: SLF001
        boot_nonce = selected_host.base._validate_fresh_status(  # noqa: SLF001
            transcript[2]["body"], running_sha, expected_busy=0
        )
        selected_host.base._base._validate_fresh_report(transcript[3]["body"], running_sha)  # noqa: SLF001
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise W10RunnerError("fixed W10 J2-OFF diagnostic deep validation failed") from error
    status = transcript[2]["body"]
    report = transcript[3]["body"]
    if (
        value.get("boot_nonce") != boot_nonce
        or status.get("boot_nonce") != boot_nonce
        or status.get("state") != "ready"
        or status.get("phase_name") != "READY"
        or status.get("persistent_key_present") is not False
        or status.get("gpio_initialized") is not True
        or status.get("busy") != 0
        or status.get("rst") != 0
        or status.get("cs") != 0
        or status.get("cs2") != 0
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_called") is not False
        or report.get("driver_call_count_for_action") != 0
    ):
        raise W10RunnerError("fixed W10 diagnostic fresh boot or GPIO state differs")
    return {
        "verified": True,
        "path": str(path),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": canonical_sha,
        "boot_nonce": boot_nonce,
        "network": {"get": 4, "post": 0},
    }


def _same_boot_requester(
    requester: Callable[..., tuple[int, Mapping[str, Any]]],
    *,
    status_path: str,
    expected_boot_nonce: str,
) -> Callable[..., tuple[int, Mapping[str, Any]]]:
    def checked(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        result = requester(base_url, path, method=method, headers=headers, timeout=timeout)
        if path == status_path and result[1].get("boot_nonce") != expected_boot_nonce:
            raise W10RunnerError("W10 boot changed after J2-OFF diagnostic")
        return result

    return checked


def _live_envelope(
    *,
    command: str,
    source_terminal: Mapping[str, Any],
    operation: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the exact COMPLETE-only source admission in CLI output."""

    state = source_terminal["source_terminal_state"]
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w10-t4-v4-white-live-envelope",
        "command": command,
        "source_terminal_branch": source_terminal["branch"],
        "source_terminal_state": state,
        "source_success_claimed": state == "COMPLETE",
        "source_fault_is_not_success": False,
        "source_fault_policy": pack.FAULT_POLICY,
        "source_terminal_authority": deepcopy(dict(source_terminal)),
        "operation": deepcopy(dict(operation)),
    }


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    value = pack.dry_validate()
    if verify_artifacts:
        _verify_artifacts()
    host = _configure_white()
    endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.ENDPOINTS != endpoints:
        raise W10RunnerError("W10 endpoint set differs")
    if any(token in json.dumps(endpoints, sort_keys=True) for token in ("w7-after", "w8-after", "w9-after")):
        raise W10RunnerError("obsolete white route leaked into W10")
    return {
        **value,
        "kind": "mf1750-raw-p16-crossover-w10-t4-v4-white-runner-validation",
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "firmware_binding": _artifact_binding(),
        "endpoint_set": endpoints,
        "claim_root": str(_claim_root()),
        "output_root": str(_output_root()),
        "fixed_source_terminal_paths": {key: str(path) for key, path in _source_terminal_paths().items()},
        "source_terminal_evidence_required_before_any_live_request": True,
        "diagnostic_get_count": 4,
        "diagnostic_post_count": 0,
        "mutation_count_per_action": 2,
        "actions_per_campaign": 1,
        "j2_off_diagnostic_required_before_run": True,
        "same_boot_diagnostic_to_execute_required": True,
        "fresh_gnd_confirmation_required_before_j2_on": True,
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
    diag.add_argument("--source-terminal-evidence", type=Path)
    diag.add_argument("--timeout", type=float, default=10.0)
    white = sub.add_parser("run-white", allow_abbrev=False)
    white.add_argument("--base-url", required=True)
    white.add_argument("--confirm-j2-on", action="store_true", required=True)
    white.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    white.add_argument("--source-terminal-evidence", type=Path)
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
            source_terminal = _validate_source_terminal_evidence(
                args.source_terminal_evidence
            )
            host = _configure_white()
            operation = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
            value = _live_envelope(
                command=args.command,
                source_terminal=source_terminal,
                operation=operation,
            )
        else:
            if not args.confirm_gnd_normal:
                raise W10RunnerError("fresh physical GND confirmation is required before J2 ON")
            _verify_artifacts()
            source_terminal = _validate_source_terminal_evidence(
                args.source_terminal_evidence
            )
            host = _configure_white()
            diagnostic = _validate_diagnostic_evidence(host)
            requester = _same_boot_requester(
                host._default_requester,  # noqa: SLF001
                status_path=host.ENDPOINTS["status"],
                expected_boot_nonce=diagnostic["boot_nonce"],
            )
            operation = host.run_once(
                args.base_url,
                claims=host.base.DEFAULT_CLAIMS,
                output=host.base.DEFAULT_OUTPUT / "action-01-factory-otp-white.json",
                confirm_j2_on=args.confirm_j2_on,
                requester=requester,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
            value = _live_envelope(
                command=args.command,
                source_terminal=source_terminal,
                operation=operation,
            )
    except (W10RunnerError, pack.W10PackError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 W10 T4 V4 COMPLETE-terminal white error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
