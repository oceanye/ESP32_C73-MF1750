#!/usr/bin/env python3
"""Fail-closed independent OTP-white successor for stable-code0 Latin V3.

The fixed L3 or explicitly selected L4 COMPLETE file is deeply validated and
sealed into an O_EXCL source-gate receipt before any white-firmware request.
The diagnostic is four GETs with J2 OFF and no claim.  A later, same-boot run
requires fresh GND/J2 assertions and consumes exactly one permanent claim,
one ARM, one EXECUTE, one factory-OTP driver call, and one visible refresh.
No flash, reset, relay, camera, retry, fallback, recovery, or autochain exists
in this runner.
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

from tools import mf1750_stable_code0_luma_latin_v3_once as source_once  # noqa: E402
from tools import (  # noqa: E402
    mf1750_stable_code0_luma_latin_v3_white_successor_v1_pack as pack,
)


class WhiteSuccessorV1Error(RuntimeError):
    """Raised before a wrong-lineage or already-consumed white action."""


_HOST_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_stable_code0_latin_v3_white_private_host", _HOST_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed factory-white mechanics: {_HOST_PATH}")
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
host.DEFAULT_CLAIMS = REPO_ROOT / Path(
    ".test-output/hardware/.mf1750_stable_code0_luma_latin_v3_"
    "white_successor_v1_claims"
)
host.DEFAULT_OUTPUT = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_20260901_V1"
)
host.DIAGNOSTIC_OUTPUT = host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
host.ACTION_OUTPUT = host.DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
SOURCE_GATE_OUTPUT = host.DEFAULT_OUTPUT / "source-terminal-gate.json"
host.DIAGNOSTIC_KIND = (
    "mf1750-stable-code0-luma-latin-v3-white-successor-v1-j2-off-diagnostic"
)
host.ATTEMPT_KIND = "mf1750-stable-code0-luma-latin-v3-white-successor-v1-attempt"

DEVICE_SOURCE_BINDING = {
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
host.SOURCE_MAIN_BINDING = deepcopy(DEVICE_SOURCE_BINDING)


def _identity(value: Mapping[str, Any], *, running_sha: str) -> None:
    """Validate device identity without requiring host-only source digests."""

    host._BASE_IDENTITY(value, running_sha=running_sha)  # noqa: SLF001
    for key, wanted in DEVICE_SOURCE_BINDING.items():
        if value.get(key) != wanted:
            raise host.ContainmentError(f"source main binding {key} differs")


host._identity = _identity  # noqa: SLF001
host._base._identity = _identity  # noqa: SLF001


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


def _verify_artifacts() -> None:
    pack.dry_validate(verify_artifacts=True)
    pack.source_pack.dry_validate(verify_source=True, verify_artifacts=True)


def _validate_source_terminal(
    path: Path, *, confirm_optional_l4_source: bool = False
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    paths = _source_terminal_paths()
    selected = next((ordinal for ordinal, fixed in paths.items() if fixed == candidate), None)
    if selected not in (3, 4):
        raise WhiteSuccessorV1Error("source must be the fixed Latin-V3 L3 or L4 COMPLETE file")
    if selected == 3 and paths[4].is_file():
        raise WhiteSuccessorV1Error("L4 exists; stale L3 cannot authorize post-L4 white")
    if selected == 4 and confirm_optional_l4_source is not True:
        raise WhiteSuccessorV1Error("L4 source requires explicit optional-repeat confirmation")
    if selected == 3 and confirm_optional_l4_source is True:
        raise WhiteSuccessorV1Error("L4 confirmation is forbidden for an L3 source")
    try:
        deep = source_once.validate_terminal_evidence(candidate)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise WhiteSuccessorV1Error("source terminal deep validation failed") from error
    expected = next(
        item
        for item in REPORT["contract"]["accepted_source_complete_actions"]
        if item["ordinal"] == selected
    )
    exact = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": selected,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": selected,
        "visible_refreshes": 1,
        "source_success_claimed": True,
    }
    if any(deep.get(key) != wanted for key, wanted in exact.items()):
        raise WhiteSuccessorV1Error("source terminal lineage or driver semantics differ")
    payload = candidate.read_bytes()
    return {
        "verified": True,
        "terminal_state": "COMPLETE",
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
        "claim": {
            "path": deep["claim_path"],
            "bytes": deep["claim_bytes"],
            "file_sha256": deep["claim_file_sha256"],
            "canonical_integrity_sha256": deep[
                "claim_canonical_integrity_sha256"
            ],
        },
        "optional_l4_explicitly_confirmed": selected == 4,
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
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != digest
    ):
        raise WhiteSuccessorV1Error(f"{label} canonical integrity differs")
    return value


def _write_source_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-white-successor-v1-source-gate",
        "created_at": host._now(),  # noqa: SLF001
        "white_campaign_id": pack.CAMPAIGN_ID,
        "white_contract_id": pack.CONTRACT_ID,
        "white_descriptor_id": pack.DESCRIPTOR_ID,
        "white_action_id": pack.ACTION_ID,
        "selected_source_terminal_evidence": deepcopy(dict(source)),
        "state": "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST",
        "write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    host._write_new(SOURCE_GATE_OUTPUT, value)  # noqa: SLF001
    return _validate_source_receipt(source)


def _validate_source_receipt(source: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_integrity_json(SOURCE_GATE_OUTPUT, label="fixed source-gate receipt")
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-stable-code0-luma-latin-v3-white-successor-v1-source-gate"
        or value.get("white_campaign_id") != pack.CAMPAIGN_ID
        or value.get("white_contract_id") != pack.CONTRACT_ID
        or value.get("white_descriptor_id") != pack.DESCRIPTOR_ID
        or value.get("white_action_id") != pack.ACTION_ID
        or value.get("selected_source_terminal_evidence") != dict(source)
        or value.get("state") != "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST"
        or value.get("write_contract") != "O_EXCL"
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise WhiteSuccessorV1Error("fixed source-gate receipt differs")
    payload = SOURCE_GATE_OUTPUT.read_bytes()
    return {
        "verified": True,
        "path": _repo_relative(SOURCE_GATE_OUTPUT),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
    }


def _same_boot_requester(requester: Any, boot_nonce: str) -> Any:
    def checked(*args: Any, **kwargs: Any) -> Any:
        status, value = requester(*args, **kwargs)
        if (
            isinstance(value, Mapping)
            and value.get("boot_nonce") is not None
            and value.get("boot_nonce") != boot_nonce
        ):
            raise WhiteSuccessorV1Error("boot changed after J2-OFF diagnostic")
        return status, value

    return checked


def dry_validate() -> dict[str, Any]:
    _verify_artifacts()
    contract = REPORT["contract"]
    if (
        contract["accepted_source_ordinals"] != [3, 4]
        or contract["one_visible_refresh"] is not True
        or contract["runtime_lut_write"] is not False
        or contract["autochain"] is not False
        or contract["retry"] is not False
        or contract["automatic_recovery"] is not False
    ):
        raise WhiteSuccessorV1Error("white successor contract differs")
    return {
        "kind": "mf1750-stable-code0-luma-latin-v3-white-successor-v1-validation",
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
        "accepted_source_ordinals": [3, 4],
        "source_gate_o_excl": True,
        "same_boot_j2_off_then_gnd_j2_on": True,
        "exactly_one_factory_otp_white_refresh": True,
        "no_runtime_lut": True,
        "no_retry": True,
        "no_fallback": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_off: bool,
    confirm_optional_l4_source: bool = False,
    output: Path | None = None,
    requester: Any = None,
) -> dict[str, Any]:
    if confirm_j2_off is not True:
        raise WhiteSuccessorV1Error(
            "diagnose-j2-off requires an explicit J2-OFF assertion"
        )
    _verify_artifacts()
    source = _validate_source_terminal(
        source_terminal_evidence,
        confirm_optional_l4_source=confirm_optional_l4_source,
    )
    receipt = _write_source_receipt(source)
    host.SOURCE_MAIN_BINDING = _dynamic_source_binding(source)
    kwargs: dict[str, Any] = {
        "output": _fixed_path(output, host.DIAGNOSTIC_OUTPUT, label="diagnostic output"),
        "confirm_j2_off": confirm_j2_off,
    }
    if requester is not None:
        kwargs["requester"] = requester
    diagnostic = host.diagnose_j2_off(base_url, **kwargs)
    return {"source": source, "source_receipt": receipt, "diagnostic": diagnostic}


def run_once(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    confirm_optional_l4_source: bool = False,
    claims: Path | None = None,
    output: Path | None = None,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 20,
) -> dict[str, Any]:
    if confirm_j2_on is not True:
        raise WhiteSuccessorV1Error("run requires a fresh explicit J2-ON assertion")
    if confirm_gnd_normal is not True:
        raise WhiteSuccessorV1Error("run requires a fresh explicit GND-normal assertion")
    _verify_artifacts()
    source = _validate_source_terminal(
        source_terminal_evidence,
        confirm_optional_l4_source=confirm_optional_l4_source,
    )
    receipt = _validate_source_receipt(source)
    host.SOURCE_MAIN_BINDING = _dynamic_source_binding(source)
    diagnostic = _read_integrity_json(
        host.DIAGNOSTIC_OUTPUT, label="fixed same-boot J2-OFF diagnostic"
    )
    # Reuse the reviewed deep four-GET validator after restoring the exact
    # dynamic source binding which was sealed into that diagnostic.
    deep_diagnostic = _validate_diagnostic(base_url, source)
    selected = host._default_requester if requester is None else requester  # noqa: SLF001
    result = host.run_once(
        base_url,
        claims=_fixed_path(claims, host.DEFAULT_CLAIMS, label="claims root"),
        output=_fixed_path(output, host.ACTION_OUTPUT, label="action output"),
        requester=_same_boot_requester(selected, deep_diagnostic["boot_nonce"]),
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )
    return {
        "source": source,
        "source_receipt": receipt,
        "j2_off_same_boot_gate": deep_diagnostic,
        "white_result": result,
        "diagnostic_integrity": diagnostic["integrity"],
    }


def _validate_diagnostic(base_url: str, source: Mapping[str, Any]) -> dict[str, Any]:
    host.SOURCE_MAIN_BINDING = _dynamic_source_binding(source)
    value = host._validate_diagnostic_evidence() if hasattr(  # noqa: SLF001
        host, "_validate_diagnostic_evidence"
    ) else None
    if value is None:
        # The private host does not expose the successor helper; validate its
        # four responses directly with the same mature endpoint validators.
        evidence = _read_integrity_json(
            host.DIAGNOSTIC_OUTPUT, label="fixed same-boot J2-OFF diagnostic"
        )
        transcript = evidence.get("transcript")
        expected_transcript = [
            ("GET", name, host.ENDPOINTS[name], 200)
            for name in ("version", "manifest", "status", "report")
        ]
        if (
            evidence.get("schema_version") != 1
            or evidence.get("kind") != host.DIAGNOSTIC_KIND
            or evidence.get("outcome") != "j2_off_diagnostic_pass"
            or evidence.get("firmware_sha256") != pack.FIRMWARE_BIN_SHA256
            or evidence.get("running_app_elf_sha256") != pack.FIRMWARE_ELF_SHA256
            or evidence.get("action") != REPORT["action"]
            or evidence.get("base_url") != host._origin(base_url)  # noqa: SLF001
            or evidence.get("transport")
            != {
                "mode": "direct_private_literal_ipv4_http",
                "proxy": False,
                "redirect": False,
            }
            or evidence.get("j2_confirmed_off") is not True
            or evidence.get("fresh_nvs") is not True
            or evidence.get("busy") != 0
            or evidence.get("report_terminal_state") != "NOT_EXECUTED"
            or evidence.get("artifact_preflight_completed_before_network") is not True
            or evidence.get("network") != {"get": 4, "post": 0}
            or evidence.get("permanent_claims_created") != 0
            or evidence.get("claims_directory_accessed") is not False
            or evidence.get("visible_refreshes") != 0
            or evidence.get("output_write_contract") != "O_EXCL"
            or evidence.get("no_retry") is not True
            or evidence.get("no_recovery") is not True
            or evidence.get("no_autochain") is not True
            or evidence.get("no_ordinal_skip") is not True
            or any(
                evidence.get(key) != wanted
                for key, wanted in _dynamic_source_binding(source).items()
            )
            or not isinstance(transcript, list)
            or len(transcript) != 4
            or [
                (
                    item.get("method"),
                    item.get("endpoint"),
                    item.get("path"),
                    item.get("status"),
                )
                for item in transcript
            ]
            != expected_transcript
        ):
            raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic envelope differs")
        bodies = [item.get("body") for item in transcript]
        if any(not isinstance(body, Mapping) for body in bodies):
            raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic responses differ")
        if evidence.get("report") != bodies[3]:
            raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic report binding differs")
        running = host._validate_version(bodies[0])  # noqa: SLF001
        host._base._validate_manifest(bodies[1], running)  # noqa: SLF001
        boot = host._validate_fresh_status(bodies[2], running, expected_busy=0)  # noqa: SLF001
        host._base._validate_fresh_report(bodies[3], running)  # noqa: SLF001
        if evidence.get("boot_nonce") != boot:
            raise WhiteSuccessorV1Error("fixed J2-OFF diagnostic boot differs")
        return {"verified": True, "boot_nonce": boot}
    return value


def describe() -> dict[str, Any]:
    return {
        **dry_validate(),
        "contract": deepcopy(REPORT["contract"]),
        "action": deepcopy(REPORT["action"]),
        "source_terminal_paths": {
            str(key): _repo_relative(value) for key, value in _source_terminal_paths().items()
        },
        "fixed_outputs": {
            "source_gate": _repo_relative(SOURCE_GATE_OUTPUT),
            "diagnostic": _repo_relative(host.DIAGNOSTIC_OUTPUT),
            "action": _repo_relative(host.ACTION_OUTPUT),
            "claims": _repo_relative(host.DEFAULT_CLAIMS),
        },
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
        command.add_argument("--confirm-optional-l4-source", action="store_true")
        if name == "diagnose-j2-off":
            command.add_argument("--confirm-j2-off", action="store_true", required=True)
        else:
            command.add_argument("--confirm-j2-on", action="store_true", required=True)
            command.add_argument("--confirm-gnd-normal", action="store_true", required=True)
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
                confirm_optional_l4_source=args.confirm_optional_l4_source,
            )
        else:
            value = run_once(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_optional_l4_source=args.confirm_optional_l4_source,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (WhiteSuccessorV1Error, host.ContainmentError, OSError, RuntimeError) as error:
        print(f"stable-code0 Latin V3 white successor error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
