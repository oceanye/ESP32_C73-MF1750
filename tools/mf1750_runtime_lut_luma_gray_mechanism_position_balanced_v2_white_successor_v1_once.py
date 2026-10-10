#!/usr/bin/env python3
"""Fail-closed factory-OTP white successor for position-balanced V2.

Every live entry first verifies sealed V2/white artifacts and deeply validates
the fixed G3 COMPLETE result, or the separately confirmed optional G4 COMPLETE
result.  The source gate runs before any GET, claim, ARM, or EXECUTE.  This
runner never flashes, resets, controls a relay, retries, recovers, or chains.
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
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_once as source_once,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_white_successor_v1_pack as pack,
)


class WhiteSuccessorV1Error(RuntimeError):
    """Raised before an unsealed or wrong-lineage white action can run."""


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_lgmpb2_white_successor_v1_private_host", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed factory-white host: {_BASE_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)

REPORT = pack.build_report(verify_artifacts=False)
host.pack = pack
host._base.pack = pack  # noqa: SLF001
host._base.REPORT = REPORT  # noqa: SLF001
host._base.ACTION = REPORT["action"]  # noqa: SLF001
host._base.ENDPOINTS = {  # noqa: SLF001
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
host.ACTION = REPORT["action"]
host.ENDPOINTS = host._base.ENDPOINTS  # noqa: SLF001
host.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_luma_gray_mechanism_position_balanced_v2_white_successor_v1_claims"
)
host.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_WHITE_SUCCESSOR_20260901_V1"
)
host.DIAGNOSTIC_OUTPUT = host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
host.ACTION_OUTPUT = host.DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
SOURCE_GATE_OUTPUT = host.DEFAULT_OUTPUT / "source-terminal-gate.json"
host.DIAGNOSTIC_KIND = (
    "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-j2-off-diagnostic"
)
host.ATTEMPT_KIND = (
    "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-attempt"
)
host.SOURCE_MAIN_BINDING = {
    "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
    "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
    "source_main_contract_exact_binding": True,
    "source_main_device_enforced_same_boot": True,
    "source_main_direct_exact_post_resume_after_reboot": False,
    "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
    "accepted_source_complete_ordinals": [3, 4],
    "source_terminal_evidence_required_before_any_live_request": True,
    "main_campaign_resume_after_containment": False,
    "containment_terminal_for_source_campaign": True,
    "source_main_interrupted_or_completed_branch": True,
    "source_main_resume_forbidden_after_containment": True,
    "relay_off_required_before_containment": True,
}


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _fixed_path(value: Path | None, expected: Path, *, label: str) -> Path:
    candidate = expected if value is None else Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if candidate.resolve() != expected.resolve():
        raise WhiteSuccessorV1Error(f"{label} is fixed at {_repo_relative(expected)}")
    return expected.resolve()


def _source_terminal_paths() -> dict[int, Path]:
    return {ordinal: source_once.ACTION_OUTPUTS[ordinal].resolve() for ordinal in (3, 4)}


def _validate_source_terminal_evidence(
    path: Path, *, confirm_optional_g4_source: bool = False
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    paths = _source_terminal_paths()
    selected = next((ordinal for ordinal, fixed in paths.items() if candidate == fixed), None)
    if selected not in (3, 4):
        raise WhiteSuccessorV1Error(
            "source evidence must be the fixed V2 G3 or optional G4 COMPLETE output"
        )
    if selected == 3 and paths[4].is_file():
        raise WhiteSuccessorV1Error(
            "G4 output exists; stale G3 cannot authorize post-G4 white containment"
        )
    if selected == 4 and confirm_optional_g4_source is not True:
        raise WhiteSuccessorV1Error(
            "optional G4 source requires explicit --confirm-source-g4-repeat"
        )
    if selected == 3 and confirm_optional_g4_source is True:
        raise WhiteSuccessorV1Error("G4 confirmation is forbidden for a G3 source")
    try:
        deep = source_once.validate_terminal_evidence(candidate)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise WhiteSuccessorV1Error("source terminal deep validation failed") from error
    expected = pack.build_report()["contract"]["accepted_source_complete_actions"]
    wanted = next(item for item in expected if item["ordinal"] == selected)
    if (
        deep.get("terminal_state") != "COMPLETE"
        or deep.get("campaign_id") != pack.SOURCE_CAMPAIGN_ID
        or deep.get("contract_id") != pack.SOURCE_MAIN_CONTRACT_ID
        or deep.get("ordinal") != selected
        or deep.get("descriptor_id") != wanted["descriptor_id"]
        or deep.get("action_id") != wanted["action_id"]
        or deep.get("driver_call_count_for_action") != 1
        or deep.get("total_driver_call_count") != selected
        or deep.get("visible_refreshes") != 1
        or deep.get("source_success_claimed") is not True
    ):
        raise WhiteSuccessorV1Error("source terminal lineage/driver semantics differ")
    payload = candidate.read_bytes()
    return {
        "verified": True,
        "ordinal": selected,
        "path": _repo_relative(candidate),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": deep["canonical_integrity_sha256"],
        "campaign_id": deep["campaign_id"],
        "contract_id": deep["contract_id"],
        "descriptor_id": deep["descriptor_id"],
        "action_id": deep["action_id"],
        "boot_nonce": deep["boot_nonce"],
        "claim_file_sha256": deep["claim_file_sha256"],
        "optional_g4_explicitly_confirmed": selected == 4,
    }


def _verify_artifacts() -> None:
    pack.dry_validate(verify_artifacts=True)
    pack.source_pack.dry_validate(verify_artifacts=True)


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise WhiteSuccessorV1Error(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WhiteSuccessorV1Error(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise WhiteSuccessorV1Error(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm")
        != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256")
        != hashlib.sha256(host._base._canonical(body)).hexdigest()  # noqa: SLF001
    ):
        raise WhiteSuccessorV1Error(f"{label} canonical integrity differs")
    return value


def _validate_diagnostic_evidence() -> dict[str, Any]:
    path = host.DIAGNOSTIC_OUTPUT.resolve()
    value = _read_integrity_json(path, label="fixed white-successor J2-OFF diagnostic")
    transcript = value.get("transcript")
    if (
        value.get("kind") != host.DIAGNOSTIC_KIND
        or value.get("outcome") != "j2_off_diagnostic_pass"
        or value.get("firmware_sha256") != pack.FIRMWARE_BIN_SHA256
        or value.get("running_app_elf_sha256") != pack.FIRMWARE_ELF_SHA256
        or value.get("action") != REPORT["action"]
        or value.get("j2_confirmed_off") is not True
        or value.get("fresh_nvs") is not True
        or value.get("busy") != 0
        or value.get("report_terminal_state") != "NOT_EXECUTED"
        or value.get("artifact_preflight_completed_before_network") is not True
        or value.get("permanent_claims_created") != 0
        or value.get("claims_directory_accessed") is not False
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("visible_refreshes") != 0
        or value.get("output_write_contract") != "O_EXCL"
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or any(value.get(key) != wanted for key, wanted in host.SOURCE_MAIN_BINDING.items())
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        != [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
        ]
        or any(not isinstance(item.get("body"), Mapping) for item in transcript)
    ):
        raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic envelope differs")
    try:
        running_sha = host._validate_version(transcript[0]["body"])  # noqa: SLF001
        host._base._validate_manifest(transcript[1]["body"], running_sha)  # noqa: SLF001
        boot_nonce = host._validate_fresh_status(  # noqa: SLF001
            transcript[2]["body"], running_sha, expected_busy=0
        )
        host._base._validate_fresh_report(transcript[3]["body"], running_sha)  # noqa: SLF001
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic deep validation failed") from error
    if value.get("boot_nonce") != boot_nonce:
        raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic boot nonce differs")
    payload = path.read_bytes()
    return {
        "verified": True,
        "path": _repo_relative(path),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
        "boot_nonce": boot_nonce,
        "network": {"get": 4, "post": 0},
        "permanent_claims_created": 0,
    }


def _source_gate_receipt_body(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-source-terminal-gate",
        "created_at": host._now(),  # noqa: SLF001
        "white_campaign_id": pack.CAMPAIGN_ID,
        "white_contract_id": pack.CONTRACT_ID,
        "white_descriptor_id": pack.DESCRIPTOR_ID,
        "white_action_id": pack.ACTION_ID,
        "source_terminal_gate": deepcopy(dict(source)),
        "state": "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST",
        "output_write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def _create_source_gate_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    if SOURCE_GATE_OUTPUT.exists():
        raise WhiteSuccessorV1Error(
            f"refusing to overwrite {_repo_relative(SOURCE_GATE_OUTPUT)}"
        )
    value = _source_gate_receipt_body(source)
    host._write_new(SOURCE_GATE_OUTPUT, value)  # noqa: SLF001
    return _validate_source_gate_receipt(source)


def _validate_source_gate_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_integrity_json(
        SOURCE_GATE_OUTPUT, label="fixed white-successor source-terminal gate"
    )
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-source-terminal-gate"
        or value.get("white_campaign_id") != pack.CAMPAIGN_ID
        or value.get("white_contract_id") != pack.CONTRACT_ID
        or value.get("white_descriptor_id") != pack.DESCRIPTOR_ID
        or value.get("white_action_id") != pack.ACTION_ID
        or value.get("source_terminal_gate") != dict(source)
        or value.get("state") != "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST"
        or value.get("output_write_contract") != "O_EXCL"
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise WhiteSuccessorV1Error("fixed source-terminal gate receipt differs")
    payload = SOURCE_GATE_OUTPUT.read_bytes()
    return {
        "verified": True,
        "path": _repo_relative(SOURCE_GATE_OUTPUT),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
        "source_terminal_gate": deepcopy(dict(source)),
    }


def _same_boot_requester(requester: Any, boot_nonce: str) -> Any:
    def guarded(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> Any:
        result = requester(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[1], Mapping)
            and "boot_nonce" in result[1]
            and result[1].get("boot_nonce") != boot_nonce
        ):
            raise WhiteSuccessorV1Error(
                "device boot nonce changed after fixed J2-OFF diagnostic"
            )
        return result

    return guarded


def dry_validate() -> dict[str, Any]:
    _verify_artifacts()
    accepted = REPORT["contract"]["accepted_source_complete_actions"]
    if (
        [item["ordinal"] for item in accepted] != [3, 4]
        or REPORT["contract"]["autochain"] is not False
        or REPORT["contract"]["retry"] is not False
        or REPORT["contract"]["automatic_recovery"] is not False
        or REPORT["contract"]["main_campaign_resume_after_containment"] is not False
    ):
        raise WhiteSuccessorV1Error("white successor contract differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "accepted_source_complete_ordinals": [3, 4],
        "source_terminal_evidence_required_before_any_live_request": True,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "action_id": pack.ACTION_ID,
        "artifacts_sealed": pack.artifacts_are_sealed(),
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
            str(ordinal): _repo_relative(path)
            for ordinal, path in _source_terminal_paths().items()
        },
        "source_g4_requires_separate_confirmation": True,
        "endpoints": deepcopy(host.ENDPOINTS),
        "fixed_output_files": {
            "source_terminal_gate": _repo_relative(SOURCE_GATE_OUTPUT),
            "diagnostic": _repo_relative(host.DIAGNOSTIC_OUTPUT),
            "action": _repo_relative(host.ACTION_OUTPUT),
            "claims_root": _repo_relative(host.DEFAULT_CLAIMS),
        },
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_off: bool,
    confirm_source_g4_repeat: bool = False,
    output: Path | None = None,
    requester: Any = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    _verify_artifacts()
    source = _validate_source_terminal_evidence(
        source_terminal_evidence,
        confirm_optional_g4_source=confirm_source_g4_repeat,
    )
    receipt = _create_source_gate_receipt(source)
    kwargs: dict[str, Any] = {
        "output": _fixed_path(output, host.DIAGNOSTIC_OUTPUT, label="diagnostic output"),
        "confirm_j2_off": confirm_j2_off,
        "timeout": timeout,
    }
    if requester is not None:
        kwargs["requester"] = requester
    result = host.diagnose_j2_off(base_url, **kwargs)
    return {
        "source_terminal_gate": source,
        "source_terminal_gate_receipt": receipt,
        "diagnostic": result,
    }


def run_once(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    confirm_source_g4_repeat: bool = False,
    claims: Path | None = None,
    output: Path | None = None,
    requester: Any = None,
    timeout: float = 10.0,
    poll_seconds: float = 65.0,
    poll_count: int = 20,
) -> dict[str, Any]:
    if confirm_j2_on is not True:
        raise WhiteSuccessorV1Error("run requires explicit J2-ON confirmation")
    if confirm_gnd_normal is not True:
        raise WhiteSuccessorV1Error("run requires a fresh normal-GND confirmation")
    _verify_artifacts()
    source = _validate_source_terminal_evidence(
        source_terminal_evidence,
        confirm_optional_g4_source=confirm_source_g4_repeat,
    )
    receipt = _validate_source_gate_receipt(source)
    diagnostic = _validate_diagnostic_evidence()
    kwargs: dict[str, Any] = {
        "claims": _fixed_path(claims, host.DEFAULT_CLAIMS, label="claims root"),
        "output": _fixed_path(output, host.ACTION_OUTPUT, label="action output"),
        "timeout": timeout,
        "poll_seconds": poll_seconds,
        "poll_count": poll_count,
    }
    selected_requester = host._default_requester if requester is None else requester  # noqa: SLF001
    kwargs["requester"] = _same_boot_requester(
        selected_requester, diagnostic["boot_nonce"]
    )
    result = host.run_once(base_url, **kwargs)
    return {
        "source_terminal_gate": source,
        "source_terminal_gate_receipt": receipt,
        "j2_off_same_boot_gate": diagnostic,
        "white_result": result,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    sub.add_parser("describe")
    for name in ("diagnose-j2-off", "run"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--base-url", required=True)
        command.add_argument("--source-terminal-evidence", type=Path, required=True)
        command.add_argument("--confirm-source-g4-repeat", action="store_true")
        command.add_argument("--timeout", type=float, default=10.0)
        if name == "diagnose-j2-off":
            command.add_argument("--confirm-j2-off", action="store_true", required=True)
            command.add_argument("--output", type=Path)
        else:
            command.add_argument("--confirm-j2-on", action="store_true", required=True)
            command.add_argument("--confirm-gnd-normal", action="store_true", required=True)
            command.add_argument("--claims", type=Path)
            command.add_argument("--output", type=Path)
            command.add_argument("--poll-seconds", type=float, default=65.0)
            command.add_argument("--poll-count", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "dry-validate":
            result = dry_validate()
        elif args.command == "describe":
            result = describe()
        elif args.command == "diagnose-j2-off":
            result = diagnose_j2_off(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_off=args.confirm_j2_off,
                confirm_source_g4_repeat=args.confirm_source_g4_repeat,
                output=args.output,
                timeout=args.timeout,
            )
        else:
            result = run_once(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_source_g4_repeat=args.confirm_source_g4_repeat,
                claims=args.claims,
                output=args.output,
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (WhiteSuccessorV1Error, host.ContainmentError, OSError, RuntimeError) as error:
        print(f"LUMA/GRAY V2 white successor error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
