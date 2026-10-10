#!/usr/bin/env python3
"""Fail-closed one-shot host for the post-HOLD OTP-white successor.

The sealed H2 COMPLETE result is the default source.  H1 COMPLETE is accepted
only when the operator supplies the dedicated explicit-H1-stop confirmation.
FAULT, arbitrary paths, and automatic branch selection are rejected before
any device request.
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

from tools import mf1750_position_balanced_gray_hold_successor_v1_once as source_once  # noqa: E402
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_pack as pack,
)


class WhiteSuccessorV1Error(RuntimeError):
    """Raised before a wrong-lineage or already-consumed white action."""


_REVIEWED_PATH = Path(__file__).with_name(
    "mf1750_stable_code0_luma_latin_v3_white_successor_v1_once.py"
)
_REVIEWED_BYTES = 22678
_REVIEWED_SHA256 = "6a498612fa634bb8c914c9aadc7830d8c0c05bf727ab1590dc247567ce94a8cb"
if (
    not _REVIEWED_PATH.is_file()
    or _REVIEWED_PATH.is_symlink()
    or _REVIEWED_PATH.stat().st_size != _REVIEWED_BYTES
    or hashlib.sha256(_REVIEWED_PATH.read_bytes()).hexdigest() != _REVIEWED_SHA256
):
    raise ImportError("reviewed white-successor host dependency identity differs")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_position_balanced_gray_hold_white_successor_v1_private_host",
    _REVIEWED_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(
        f"cannot load reviewed white-successor mechanics: {_REVIEWED_PATH}"
    )
reviewed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reviewed)

REPORT = pack.build_report(verify_artifacts=False)
host = reviewed.host
ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_WHITE_SUCCESSOR_20260901_V1"
)
DIAGNOSTIC_OUTPUT = DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUT = DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
SOURCE_GATE_OUTPUT = DEFAULT_OUTPUT / "source-terminal-gate.json"
DIAGNOSTIC_KIND = "mf1750-position-balanced-gray-hold-successor-v1-white-successor-v1-j2-off-diagnostic"
ATTEMPT_KIND = (
    "mf1750-position-balanced-gray-hold-successor-v1-white-successor-v1-attempt"
)
SOURCE_GATE_KIND = (
    "mf1750-position-balanced-gray-hold-successor-v1-white-successor-v1-source-gate"
)

DEVICE_SOURCE_BINDING = {
    "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
    "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
    "source_main_contract_exact_binding": True,
    "source_main_device_enforced_same_boot": True,
    "source_main_direct_exact_post_resume_after_reboot": False,
    "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
    "accepted_source_complete_ordinals_default": [2],
    "explicit_h1_stop_ordinal": 1,
    "source_terminal_evidence_required_before_any_live_request": True,
    "main_campaign_resume_after_containment": False,
    "containment_terminal_for_source_campaign": True,
    "source_main_interrupted_or_completed_branch": False,
    "source_main_h2_default": True,
    "source_main_h1_requires_explicit": True,
    "source_main_resume_forbidden_after_containment": True,
    "relay_off_required_before_containment": True,
}

# Rebind a private reviewed host.  No existing campaign module is mutated.
reviewed.pack = pack
reviewed.source_once = source_once
reviewed.REPORT = REPORT
reviewed.SOURCE_GATE_OUTPUT = SOURCE_GATE_OUTPUT
reviewed.DEVICE_SOURCE_BINDING = deepcopy(DEVICE_SOURCE_BINDING)
host.pack = pack
host._base.pack = pack  # noqa: SLF001
host._base.REPORT = REPORT  # noqa: SLF001
host._base.ACTION = REPORT["action"]  # noqa: SLF001
host._base.ENDPOINTS = ENDPOINTS  # noqa: SLF001
host.ACTION = REPORT["action"]
host.ENDPOINTS = ENDPOINTS
host.DEFAULT_CLAIMS = DEFAULT_CLAIMS
host.DEFAULT_OUTPUT = DEFAULT_OUTPUT
host.DIAGNOSTIC_OUTPUT = DIAGNOSTIC_OUTPUT
host.ACTION_OUTPUT = ACTION_OUTPUT
host.DIAGNOSTIC_KIND = DIAGNOSTIC_KIND
host.ATTEMPT_KIND = ATTEMPT_KIND
host.SOURCE_MAIN_BINDING = deepcopy(DEVICE_SOURCE_BINDING)


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _source_terminal_paths() -> dict[int, Path]:
    return {
        1: source_once.ACTION_OUTPUTS[1].resolve(),
        2: source_once.ACTION_OUTPUTS[2].resolve(),
    }


def _verify_artifacts() -> None:
    pack.dry_validate(verify_artifacts=True)
    pack.source_pack.dry_validate(require_live_source=False, verify_artifacts=True)


def _validate_source_terminal(
    path: Path, *, confirm_optional_l4_source: bool = False
) -> dict[str, Any]:
    explicit_h1 = confirm_optional_l4_source is True
    selected_ordinal = 1 if explicit_h1 else 2
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    expected_path = _source_terminal_paths()[selected_ordinal]
    if candidate != expected_path:
        raise WhiteSuccessorV1Error(
            "source path differs from the selected H2-default or explicit-H1 result"
        )
    try:
        deep = source_once.validate_terminal_evidence(
            candidate, allow_explicit_h1_stop=explicit_h1
        )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise WhiteSuccessorV1Error(
            "source H2 terminal deep validation failed"
        ) from error
    accepted = (
        REPORT["contract"]["explicit_h1_stop_action"]
        if explicit_h1
        else REPORT["contract"]["accepted_source_complete_actions_default"][0]
    )
    exact = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": selected_ordinal,
        "descriptor_id": accepted["descriptor_id"],
        "action_id": accepted["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": selected_ordinal,
        "explicit_h1_stop_selected": explicit_h1,
        "visible_refreshes": 1,
        "source_success_claimed": True,
    }
    if any(deep.get(key) != wanted for key, wanted in exact.items()):
        raise WhiteSuccessorV1Error("source H2 lineage or driver semantics differ")
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
            "canonical_integrity_sha256": deep["claim_canonical_integrity_sha256"],
        },
    }


def _dynamic_source_binding(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **deepcopy(DEVICE_SOURCE_BINDING),
        "selected_source_terminal_evidence": deepcopy(dict(source)),
        "selected_source_terminal_evidence_o_excl_bound": True,
    }


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise WhiteSuccessorV1Error(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WhiteSuccessorV1Error(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise WhiteSuccessorV1Error(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    digest = hashlib.sha256(host._base._canonical(body)).hexdigest()  # noqa: SLF001
    if integrity != {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": digest,
    }:
        raise WhiteSuccessorV1Error(f"{label} canonical integrity differs")
    return value


def _validate_source_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    selected = (
        "H1_EXPLICIT" if source.get("explicit_h1_stop_selected") else "H2_DEFAULT"
    )
    expected_state = (
        f"DEEPLY_VALIDATED_{selected}_COMPLETE_BEFORE_ANY_WHITE_LIVE_REQUEST"
    )
    value = _read_integrity_json(
        SOURCE_GATE_OUTPUT, label="selected source-gate receipt"
    )
    if (
        value.get("schema_version") != 1
        or value.get("kind") != SOURCE_GATE_KIND
        or value.get("white_campaign_id") != pack.CAMPAIGN_ID
        or value.get("white_contract_id") != pack.CONTRACT_ID
        or value.get("white_descriptor_id") != pack.DESCRIPTOR_ID
        or value.get("white_action_id") != pack.ACTION_ID
        or value.get("selected_source_terminal_evidence") != dict(source)
        or value.get("state") != expected_state
        or value.get("write_contract") != "O_EXCL"
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise WhiteSuccessorV1Error("selected source-gate receipt differs")
    payload = SOURCE_GATE_OUTPUT.read_bytes()
    return {
        "verified": True,
        "path": _repo_relative(SOURCE_GATE_OUTPUT),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
    }


def _write_source_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    selected = (
        "H1_EXPLICIT" if source.get("explicit_h1_stop_selected") else "H2_DEFAULT"
    )
    value = {
        "schema_version": 1,
        "kind": SOURCE_GATE_KIND,
        "created_at": host._now(),  # noqa: SLF001
        "white_campaign_id": pack.CAMPAIGN_ID,
        "white_contract_id": pack.CONTRACT_ID,
        "white_descriptor_id": pack.DESCRIPTOR_ID,
        "white_action_id": pack.ACTION_ID,
        "selected_source_terminal_evidence": deepcopy(dict(source)),
        "state": f"DEEPLY_VALIDATED_{selected}_COMPLETE_BEFORE_ANY_WHITE_LIVE_REQUEST",
        "write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    host._write_new(SOURCE_GATE_OUTPUT, value)  # noqa: SLF001
    return _validate_source_receipt(source)


# The reviewed public mechanics resolve these names dynamically in their
# private module namespace.
reviewed._source_terminal_paths = _source_terminal_paths  # noqa: SLF001
reviewed._verify_artifacts = _verify_artifacts  # noqa: SLF001
reviewed._validate_source_terminal = _validate_source_terminal  # noqa: SLF001
reviewed._dynamic_source_binding = _dynamic_source_binding  # noqa: SLF001
reviewed._read_integrity_json = _read_integrity_json  # noqa: SLF001
reviewed._validate_source_receipt = _validate_source_receipt  # noqa: SLF001
reviewed._write_source_receipt = _write_source_receipt  # noqa: SLF001


def dry_validate() -> dict[str, Any]:
    _verify_artifacts()
    contract = REPORT["contract"]
    if (
        contract["accepted_source_complete_ordinals_default"] != [2]
        or contract["explicit_h1_stop_ordinal"] != 1
        or contract["h1_requires_explicit_selection"] is not True
        or contract["source_fault_not_accepted"] is not True
        or contract["source_early_stop_not_accepted"] is not True
        or contract["one_visible_refresh"] is not True
        or contract["runtime_lut_write"] is not False
        or contract["autochain"] is not False
        or contract["retry"] is not False
        or contract["automatic_recovery"] is not False
    ):
        raise WhiteSuccessorV1Error("post-H2 white successor contract differs")
    return {
        "kind": "mf1750-position-balanced-gray-hold-successor-v1-white-successor-v1-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "action_id": pack.ACTION_ID,
        "accepted_source_ordinals_default": [2],
        "explicit_h1_stop_ordinal": 1,
        "h1_requires_explicit_selection": True,
        "source_fault_accepted": False,
        "source_early_stop_accepted": False,
        "source_gate_o_excl": True,
        "same_boot_j2_off_then_gnd_j2_on": True,
        "exactly_one_factory_otp_white_refresh": True,
        "no_runtime_lut": True,
        "no_retry": True,
        "no_fallback": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(),
        "contract": deepcopy(REPORT["contract"]),
        "action": deepcopy(REPORT["action"]),
        "source_terminal_paths": {
            str(key): _repo_relative(value)
            for key, value in _source_terminal_paths().items()
        },
        "fixed_outputs": {
            "source_gate": _repo_relative(SOURCE_GATE_OUTPUT),
            "diagnostic": _repo_relative(DIAGNOSTIC_OUTPUT),
            "action": _repo_relative(ACTION_OUTPUT),
            "claims": _repo_relative(DEFAULT_CLAIMS),
        },
    }


def diagnose_j2_off(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_off: bool,
    confirm_explicit_h1_stop: bool = False,
    output: Path | None = None,
    requester: Any = None,
) -> dict[str, Any]:
    return reviewed.diagnose_j2_off(
        base_url,
        source_terminal_evidence=source_terminal_evidence,
        confirm_j2_off=confirm_j2_off,
        confirm_optional_l4_source=confirm_explicit_h1_stop,
        output=output,
        requester=requester,
    )


def run_once(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    confirm_explicit_h1_stop: bool = False,
    claims: Path | None = None,
    output: Path | None = None,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 20,
) -> dict[str, Any]:
    return reviewed.run_once(
        base_url,
        source_terminal_evidence=source_terminal_evidence,
        confirm_j2_on=confirm_j2_on,
        confirm_gnd_normal=confirm_gnd_normal,
        confirm_optional_l4_source=confirm_explicit_h1_stop,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    sub.add_parser("describe")
    for name in ("diagnose-j2-off", "run"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--base-url", required=True)
        command.add_argument("--source-terminal-evidence", type=Path, required=True)
        command.add_argument("--confirm-explicit-h1-stop", action="store_true")
        if name == "diagnose-j2-off":
            command.add_argument("--confirm-j2-off", action="store_true", required=True)
        else:
            command.add_argument("--confirm-j2-on", action="store_true", required=True)
            command.add_argument(
                "--confirm-gnd-normal", action="store_true", required=True
            )
            command.add_argument("--poll-seconds", type=float, default=65.0)
            command.add_argument("--poll-count", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_off=args.confirm_j2_off,
                confirm_explicit_h1_stop=args.confirm_explicit_h1_stop,
            )
        else:
            value = run_once(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_explicit_h1_stop=args.confirm_explicit_h1_stop,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (
        WhiteSuccessorV1Error,
        host.ContainmentError,
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"position-balanced gray HOLD white successor V1 error: {error}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
