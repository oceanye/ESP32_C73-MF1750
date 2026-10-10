#!/usr/bin/env python3
"""Fail-closed W8 white host bound to the sealed T4 V3 terminal FAULT.

No command flashes, resets, controls a relay, retries, recovers, or chains.
Every live entry point validates the immutable consumed failure, permanent
claim, four-GET transcript, offline FAULT reconciliation, and relay-OFF query
before constructing the HTTP host.
"""

from __future__ import annotations

import argparse
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
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_pack as pack,
)


class W8RunnerError(RuntimeError):
    """Raised before unsealed or wrong-authority W8 device I/O."""


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_claims"
    )


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_20260831_V1"
    )


def _diagnostic_path() -> Path:
    return _output_root() / "j2-off-diagnostic.json"


def _load_w2_runner() -> Any:
    path = REPO_ROOT / "tools/mf1750_raw_p16_crossover_w2_discovery_successor_once.py"
    spec = importlib.util.spec_from_file_location("_mf1750_raw_p16_w8_t4_v3_fault_white_base", path)
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
        value.CLAIM_KIND = "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-claim"
        value.RESULT_KIND = "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-result"
        return value

    module._adapter = adapter  # noqa: SLF001
    return module


def _artifact_binding() -> dict[str, dict[str, Any]]:
    values = pack.WHITE_ARTIFACTS[pack.STAGE]
    firmware_bin, firmware_elf = pack.white_artifact_paths()
    return {
        "bin": {"path": str(firmware_bin), "bytes": values["bin_bytes"], "sha256": values["bin_sha256"]},
        "elf": {"path": str(firmware_elf), "bytes": values["elf_bytes"], "sha256": values["elf_sha256"]},
    }


def _verify_artifacts() -> None:
    if not pack.artifacts_are_sealed():
        raise W8RunnerError("W8 artifacts are not sealed; live entry points disabled")
    for name, item in _artifact_binding().items():
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise W8RunnerError(f"sealed {name} artifact missing: {path}")
        payload = path.read_bytes()
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise W8RunnerError(f"sealed {name} artifact identity differs: {path}")


def _verify_fault_authority_chain() -> dict[str, Any]:
    """Re-read exact sealed files and deep-validate terminal FAULT semantics."""

    for label, binding in (
        ("source failure", pack.SOURCE_FAILURE_BINDING),
        ("consumed claim", pack.CLAIM_BINDING),
        ("raw four-GET salvage", pack.RAW_SALVAGE_BINDING),
        ("offline FAULT reconciliation", pack.FAULT_RECONCILIATION_BINDING),
        ("historical relay OFF query", pack.RELAY_OFF_QUERY_BINDING),
        ("latest repower ON", pack.LATEST_REPOWER_ON_BINDING),
        ("fresh protective OFF", pack.PROTECTIVE_OFF_BINDING),
    ):
        path = Path(str(binding["path"])).resolve()
        if not path.is_file() or path.is_symlink():
            raise W8RunnerError(f"sealed {label} missing or unsafe")
        payload = path.read_bytes()
        if len(payload) != binding["bytes"] or hashlib.sha256(payload).hexdigest() != binding["file_sha256"]:
            raise W8RunnerError(f"sealed {label} file identity differs")
    authority = pack.validate_fault_authority()
    report = pack.build_white_report()
    contract = report["contract"]
    if (
        authority.get("terminal_state") != "FAULT"
        or authority.get("outcome") != "fault_salvaged_read_only"
        or authority.get("action", {}).get("action_id") != contract["source_action_id"]
        or contract.get("source_complete_path_forbidden") is not True
        or contract.get("source_action_must_not_be_retried") is not True
        or contract.get("panel_state_qualified") is not False
        or contract.get("fresh_fault_bound_white_containment_required") is not True
        or contract.get("protective_off_switch_receipt_required_before_live") is not True
        or contract.get("protective_off_postdates_latest_repower_on") is not True
        or report["action"]["action_id"] in contract["rejected_obsolete_white_action_ids"]
    ):
        raise W8RunnerError("W8 FAULT authority admission differs")
    return authority


def _configure_white() -> Any:
    base = _load_w2_runner()
    host = base._configure_white()  # noqa: SLF001
    host.DEFAULT_CLAIMS = _claim_root()
    host.DEFAULT_OUTPUT = _output_root()
    host.DIAGNOSTIC_OUTPUT = _output_root() / "j2-off-diagnostic.json"
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS
    host.base.DEFAULT_OUTPUT = host.DEFAULT_OUTPUT
    host.base.DIAGNOSTIC_OUTPUT = host.DIAGNOSTIC_OUTPUT
    host.base.DIAGNOSTIC_KIND = "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-j2-off-diagnostic"
    host.base.ATTEMPT_KIND = "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-attempt"
    return host


def _validate_diagnostic_evidence(host: Any | None = None) -> dict[str, Any]:
    """Require the exact successful W8 four-GET diagnostic before RUN."""

    path = _diagnostic_path().resolve()
    if not path.is_file() or path.is_symlink():
        raise W8RunnerError("fixed W8 J2-OFF diagnostic is missing or unsafe")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W8RunnerError("fixed W8 J2-OFF diagnostic is not JSON") from error
    if not isinstance(value, Mapping):
        raise W8RunnerError("fixed W8 J2-OFF diagnostic root differs")
    body = dict(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != pack.sha256_bytes(pack.canonical_json(body))
    ):
        raise W8RunnerError("fixed W8 J2-OFF diagnostic integrity differs")
    transcript = value.get("transcript")
    if (
        value.get("kind") != "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-j2-off-diagnostic"
        or value.get("outcome") != "j2_off_diagnostic_pass"
        or value.get("firmware_sha256") != pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"]
        or value.get("running_app_elf_sha256") != pack.WHITE_ARTIFACTS[pack.STAGE]["elf_sha256"]
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
        or value.get("no_ordinal_skip") is not True
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        != [("GET", "version", 200), ("GET", "manifest", 200), ("GET", "status", 200), ("GET", "report", 200)]
        or value.get("report") != transcript[3].get("body")
    ):
        raise W8RunnerError("fixed W8 J2-OFF diagnostic envelope differs")
    selected_host = _configure_white() if host is None else host
    try:
        running_sha = selected_host.base._validate_version(transcript[0]["body"])  # noqa: SLF001
        selected_host.base._base._validate_manifest(  # noqa: SLF001
            transcript[1]["body"], running_sha
        )
        boot_nonce = selected_host.base._validate_fresh_status(  # noqa: SLF001
            transcript[2]["body"], running_sha, expected_busy=0
        )
        selected_host.base._base._validate_fresh_report(  # noqa: SLF001
            transcript[3]["body"], running_sha
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise W8RunnerError("fixed W8 J2-OFF diagnostic deep validation failed") from error
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
        raise W8RunnerError("fixed W8 diagnostic fresh boot or GPIO state differs")
    return {
        "verified": True,
        "path": str(path),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": integrity["sha256"],
        "boot_nonce": boot_nonce,
        "network": {"get": 4, "post": 0},
    }


def _same_boot_requester(
    requester: Callable[..., tuple[int, Mapping[str, Any]]],
    *,
    status_path: str,
    expected_boot_nonce: str,
) -> Callable[..., tuple[int, Mapping[str, Any]]]:
    """Reject a J2-ON preflight status from any boot other than diagnostic boot."""

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
            raise W8RunnerError("W8 boot changed after J2-OFF diagnostic")
        return result

    return checked


def dry_validate(*, verify_artifacts: bool = True, verify_authority: bool = True) -> dict[str, Any]:
    value = pack.dry_validate(verify_authority=verify_authority)
    if verify_artifacts:
        _verify_artifacts()
    authority = _verify_fault_authority_chain() if verify_authority else None
    host = _configure_white()
    endpoints = {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    if host.ENDPOINTS != endpoints:
        raise W8RunnerError("W8 endpoint set differs")
    serialized = json.dumps(endpoints, sort_keys=True)
    if any(token in serialized for token in ("w5-after", "w6-after", "w7-after")):
        raise W8RunnerError("obsolete white route leaked into W8")
    return {
        **value,
        "kind": "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-runner-validation",
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "fault_authority_required": verify_authority,
        "fault_authority_verified": verify_authority,
        "authority_terminal_state": None if authority is None else authority["terminal_state"],
        "firmware_binding": _artifact_binding(),
        "endpoint_set": endpoints,
        "claim_root": str(_claim_root()),
        "output_root": str(_output_root()),
        "diagnostic_get_count": 4,
        "diagnostic_post_count": 0,
        "mutation_count_per_action": 2,
        "actions_per_campaign": 1,
        "source_complete_evidence_path_accepted": False,
        "source_t4_retry_allowed": False,
        "fresh_user_physical_gnd_confirmation_required_before_j2_on": True,
        "j2_off_diagnostic_required_before_run": True,
        "same_boot_diagnostic_to_execute_required": True,
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
    white.add_argument("--confirm-gnd-normal", action="store_true", required=True)
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
            _verify_fault_authority_chain()
            host = _configure_white()
            value = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            if not args.confirm_gnd_normal:
                raise W8RunnerError("fresh physical GND confirmation is required before J2 ON")
            _verify_artifacts()
            _verify_fault_authority_chain()
            if not _diagnostic_path().is_file():
                raise W8RunnerError("fixed W8 J2-OFF diagnostic is required before RUN")
            host = _configure_white()
            diagnostic = _validate_diagnostic_evidence(host)
            requester = _same_boot_requester(
                host._default_requester,  # noqa: SLF001
                status_path=host.ENDPOINTS["status"],
                expected_boot_nonce=diagnostic["boot_nonce"],
            )
            value = host.run_once(
                args.base_url,
                claims=host.base.DEFAULT_CLAIMS,
                output=host.base.DEFAULT_OUTPUT / "action-01-factory-otp-white.json",
                confirm_j2_on=args.confirm_j2_on,
                requester=requester,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (W8RunnerError, pack.W8PackError, ValueError, RuntimeError) as error:
        print(f"RAW-P16 W8 T4 V3 fault-bound white error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
