#!/usr/bin/env python3
"""One-shot R3-only factory-OTP white host, sealed-evidence gated."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_once as source_once,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_pack as pack,
)

DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_WHITE_20260901_V1"
)
DIAGNOSTIC_OUTPUT = DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUT = DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
SOURCE_GATE_OUTPUT = DEFAULT_OUTPUT / "source-terminal-gate.json"
DIAGNOSTIC_KIND = (
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
    "white-successor-v1-j2-off-diagnostic"
)
ATTEMPT_KIND = (
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
    "white-successor-v1-attempt"
)
SOURCE_GATE_KIND = (
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
    "white-successor-v1-source-gate"
)
_DELEGATE: Any = None


class ReconstructionWhiteRunnerError(RuntimeError):
    """Raised before wrong-lineage or already-consumed white execution."""


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _source_terminal_path() -> Path:
    return source_once.ACTION_OUTPUTS[3].resolve()


def _source_binding(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": report["contract"]["source_main_contract_id"],
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
        "accepted_source_complete_ordinals": [3],
        "source_terminal_evidence_required_before_any_live_request": True,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "source_main_interrupted_or_completed_branch": False,
        "source_main_completed_r3_only": True,
        "source_main_resume_forbidden_after_containment": True,
        "relay_off_required_before_containment": True,
    }


def _validate_source_terminal(path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != _source_terminal_path():
        raise ReconstructionWhiteRunnerError(
            "source is fixed at reconstruction ordinal-3 R3 COMPLETE"
        )
    try:
        deep = source_once.validate_terminal_evidence(candidate)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise ReconstructionWhiteRunnerError(
            "reconstruction R3 terminal deep validation failed"
        ) from error
    accepted = report["contract"]["accepted_source_complete_actions"][0]
    exact = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": report["contract"]["source_main_contract_id"],
        "ordinal": 3,
        "descriptor_id": accepted["descriptor_id"],
        "action_id": accepted["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 3,
        "visible_refreshes": 1,
        "source_success_claimed": True,
    }
    if any(deep.get(key) != wanted for key, wanted in exact.items()):
        raise ReconstructionWhiteRunnerError("R3 lineage or driver semantics differ")
    payload = candidate.read_bytes()
    return {
        "verified": True,
        **exact,
        "path": _repo_relative(candidate),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": deep["canonical_integrity_sha256"],
        "boot_nonce": deep["boot_nonce"],
        "claim": {
            "path": deep["claim_path"],
            "bytes": deep["claim_bytes"],
            "file_sha256": deep["claim_file_sha256"],
            "canonical_integrity_sha256": deep[
                "claim_canonical_integrity_sha256"
            ],
        },
    }


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReconstructionWhiteRunnerError(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconstructionWhiteRunnerError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise ReconstructionWhiteRunnerError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if integrity != {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }:
        raise ReconstructionWhiteRunnerError(f"{label} integrity differs")
    return value


def _load_delegate() -> Any:
    global _DELEGATE  # noqa: PLW0603
    if _DELEGATE is not None:
        return _DELEGATE
    report = pack.build_report(verify_artifacts=True)
    pack.source_pack.dry_validate(require_sealed=True, verify_artifacts=True)
    old = importlib.import_module(
        "tools.mf1750_lightness_hold_function_chain_v1_white_successor_v1_once"
    )
    setattr(pack, "CONTRACT_ID", report["contract_id"])
    setattr(pack, "DESCRIPTOR_ID", report["descriptor_id"])
    setattr(pack, "ACTION_ID", report["action_id"])
    setattr(pack, "SOURCE_MAIN_CONTRACT_ID", report["contract"]["source_main_contract_id"])
    reviewed = old.reviewed
    host = old.host
    endpoints = {
        name: f"{pack.BASE_ROUTE}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    binding = _source_binding(report)
    old.pack = pack
    old.source_once = source_once
    old.REPORT = report
    old.ENDPOINTS = endpoints
    old.DEFAULT_CLAIMS = DEFAULT_CLAIMS
    old.DEFAULT_OUTPUT = DEFAULT_OUTPUT
    old.DIAGNOSTIC_OUTPUT = DIAGNOSTIC_OUTPUT
    old.ACTION_OUTPUT = ACTION_OUTPUT
    old.SOURCE_GATE_OUTPUT = SOURCE_GATE_OUTPUT
    old.DIAGNOSTIC_KIND = DIAGNOSTIC_KIND
    old.ATTEMPT_KIND = ATTEMPT_KIND
    old.SOURCE_GATE_KIND = SOURCE_GATE_KIND
    old.DEVICE_SOURCE_BINDING = binding
    reviewed.pack = pack
    reviewed.source_once = source_once
    reviewed.REPORT = report
    reviewed.SOURCE_GATE_OUTPUT = SOURCE_GATE_OUTPUT
    reviewed.DEVICE_SOURCE_BINDING = deepcopy(binding)
    host.pack = pack
    host._base.pack = pack  # noqa: SLF001
    host._base.REPORT = report  # noqa: SLF001
    host._base.ACTION = report["action"]  # noqa: SLF001
    host._base.ENDPOINTS = endpoints  # noqa: SLF001
    host.ACTION = report["action"]
    host.ENDPOINTS = endpoints
    host.DEFAULT_CLAIMS = DEFAULT_CLAIMS
    host.DEFAULT_OUTPUT = DEFAULT_OUTPUT
    host.DIAGNOSTIC_OUTPUT = DIAGNOSTIC_OUTPUT
    host.ACTION_OUTPUT = ACTION_OUTPUT
    host.DIAGNOSTIC_KIND = DIAGNOSTIC_KIND
    host.ATTEMPT_KIND = ATTEMPT_KIND
    host.SOURCE_MAIN_BINDING = deepcopy(binding)

    def source_paths() -> dict[int, Path]:
        return {3: _source_terminal_path()}

    def verify_artifacts() -> None:
        pack.build_report(verify_artifacts=True)
        pack.source_pack.dry_validate(require_sealed=True, verify_artifacts=True)

    def validate_source(
        path: Path, *, confirm_optional_l4_source: bool = False
    ) -> dict[str, Any]:
        if confirm_optional_l4_source is True:
            raise ReconstructionWhiteRunnerError("alternate source forbidden")
        return _validate_source_terminal(path, report)

    def dynamic_binding(source: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **deepcopy(binding),
            "selected_source_terminal_evidence": deepcopy(dict(source)),
            "selected_source_terminal_evidence_o_excl_bound": True,
        }

    def validate_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
        value = _read_integrity_json(SOURCE_GATE_OUTPUT, label="R3 source receipt")
        if (
            value.get("kind") != SOURCE_GATE_KIND
            or value.get("white_campaign_id") != pack.CAMPAIGN_ID
            or value.get("white_contract_id") != report["contract_id"]
            or value.get("white_descriptor_id") != report["descriptor_id"]
            or value.get("white_action_id") != report["action_id"]
            or value.get("selected_source_terminal_evidence") != dict(source)
            or value.get("state")
            != "DEEPLY_VALIDATED_RECONSTRUCTION_R3_COMPLETE_BEFORE_ANY_WHITE_LIVE_REQUEST"
            or value.get("write_contract") != "O_EXCL"
        ):
            raise ReconstructionWhiteRunnerError("R3 source receipt differs")
        payload = SOURCE_GATE_OUTPUT.read_bytes()
        return {
            "verified": True,
            "path": _repo_relative(SOURCE_GATE_OUTPUT),
            "bytes": len(payload),
            "file_sha256": hashlib.sha256(payload).hexdigest(),
            "canonical_integrity_sha256": value["integrity"]["sha256"],
        }

    def write_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "kind": SOURCE_GATE_KIND,
            "created_at": host._now(),  # noqa: SLF001
            "white_campaign_id": pack.CAMPAIGN_ID,
            "white_contract_id": report["contract_id"],
            "white_descriptor_id": report["descriptor_id"],
            "white_action_id": report["action_id"],
            "selected_source_terminal_evidence": deepcopy(dict(source)),
            "state": (
                "DEEPLY_VALIDATED_RECONSTRUCTION_R3_COMPLETE_"
                "BEFORE_ANY_WHITE_LIVE_REQUEST"
            ),
            "write_contract": "O_EXCL",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
        host._write_new(SOURCE_GATE_OUTPUT, value)  # noqa: SLF001
        return validate_receipt(source)

    reviewed._source_terminal_paths = source_paths  # noqa: SLF001
    reviewed._verify_artifacts = verify_artifacts  # noqa: SLF001
    reviewed._validate_source_terminal = validate_source  # noqa: SLF001
    reviewed._dynamic_source_binding = dynamic_binding  # noqa: SLF001
    reviewed._read_integrity_json = _read_integrity_json  # noqa: SLF001
    reviewed._validate_source_receipt = validate_receipt  # noqa: SLF001
    reviewed._write_source_receipt = write_receipt  # noqa: SLF001
    _DELEGATE = old
    return old


def dry_validate(*, require_sealed: bool = False) -> dict[str, Any]:
    value = pack.dry_validate(
        require_sealed=require_sealed,
        verify_artifacts=require_sealed,
    )
    return {
        **value,
        "kind": (
            "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
            "white-successor-v1-runner-validation"
        ),
        "accepted_source_ordinals": [3],
        "source_terminal_path": _repo_relative(_source_terminal_path()),
        "source_gate_o_excl": True,
        "same_boot_j2_off_then_gnd_j2_on": True,
        "exactly_one_factory_otp_white_refresh": True,
        "no_runtime_lut": True,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_off: bool,
    output: Path | None = None,
    requester: Any = None,
) -> dict[str, Any]:
    old = _load_delegate()
    return old.reviewed.diagnose_j2_off(
        base_url,
        source_terminal_evidence=source_terminal_evidence,
        confirm_j2_off=confirm_j2_off,
        confirm_optional_l4_source=False,
        output=output,
        requester=requester,
    )


def run_once(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    claims: Path | None = None,
    output: Path | None = None,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 20,
) -> dict[str, Any]:
    old = _load_delegate()
    return old.reviewed.run_once(
        base_url,
        source_terminal_evidence=source_terminal_evidence,
        confirm_j2_on=confirm_j2_on,
        confirm_gnd_normal=confirm_gnd_normal,
        confirm_optional_l4_source=False,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    for name in ("diagnose-j2-off", "run"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--base-url", required=True)
        command.add_argument("--source-terminal-evidence", type=Path, required=True)
        if name == "diagnose-j2-off":
            command.add_argument("--confirm-j2-off", action="store_true", required=True)
        else:
            command.add_argument("--confirm-j2-on", action="store_true", required=True)
            command.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate(require_sealed=False)
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
            )
    except (OSError, RuntimeError) as error:
        print(f"reconstruction white runner blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
