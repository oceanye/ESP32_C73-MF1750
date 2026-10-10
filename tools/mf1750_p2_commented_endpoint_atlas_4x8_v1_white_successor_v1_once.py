#!/usr/bin/env python3
"""One-shot P2-C ordinal-1 factory-OTP white host, evidence gated."""

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
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_pack as pack,
)


SOURCE_ONCE_MODULE = "tools.mf1750_p2_commented_endpoint_atlas_4x8_v1_once"
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_20260903_V1"
)
DIAGNOSTIC_OUTPUT = DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUT = DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
SOURCE_GATE_OUTPUT = DEFAULT_OUTPUT / "source-terminal-gate.json"
DIAGNOSTIC_KIND = (
    "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-"
    "j2-off-diagnostic"
)
ATTEMPT_KIND = (
    "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-attempt"
)
SOURCE_GATE_KIND = (
    "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-source-gate"
)
_DELEGATE: Any = None
# A successor invocation must bind the literal HTTP origin to one fresh
# IPv4↔MAC evidence file before selecting a requester.  The binding is kept
# separate from ``SOURCE_MAIN_BINDING``: the latter is part of the firmware's
# compiled identity and cannot contain a runtime MAC/IP value.
_CURRENT_EXACT_IPV4_MAC_BINDING: dict[str, Any] | None = None
_CURRENT_ORIGIN: str | None = None


class P2CommentedWhiteSuccessorRunnerError(RuntimeError):
    """Raised before wrong-lineage, replayed, or unsafe white execution."""


def _source_once() -> Any:
    try:
        return importlib.import_module(SOURCE_ONCE_MODULE)
    except (ImportError, AttributeError) as error:
        raise P2CommentedWhiteSuccessorRunnerError(
            "sealed P2-C source runner is not available"
        ) from error


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
    source = _source_once()
    outputs = getattr(source, "ACTION_OUTPUTS", None)
    if isinstance(outputs, Mapping) and 1 in outputs:
        return Path(outputs[1]).resolve()
    output = getattr(source, "ACTION_OUTPUT", None)
    if output is None:
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C source terminal path export missing"
        )
    return Path(output).resolve()


def _source_binding(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": report["contract"]["source_main_contract_id"],
        "source_main_offline_build_file_sha256": report["contract"][
            "source_main_offline_build_file_sha256"
        ],
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "source_main_nvs_boot_key": pack.source_nvs_boot_key(),
        "accepted_source_complete_ordinals": [1],
        "source_terminal_evidence_required_before_any_live_request": True,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "source_main_interrupted_or_completed_branch": False,
        "source_main_completed_p2_commented_only": True,
        "source_main_resume_forbidden_after_containment": True,
        "relay_off_required_before_containment": True,
    }


def _validate_source_terminal(path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != _source_terminal_path():
        raise P2CommentedWhiteSuccessorRunnerError(
            "source is fixed at P2-C ordinal-1 COMPLETE output"
        )
    source = _source_once()
    validator = getattr(source, "validate_terminal_evidence", None)
    if not callable(validator):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C terminal deep validator missing"
        )
    try:
        deep = validator(candidate)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C ordinal-1 terminal deep validation failed"
        ) from error
    accepted = report["contract"]["accepted_source_complete_actions"][0]
    exact = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": 1,
        "descriptor_id": accepted["descriptor_id"],
        "action_id": accepted["action_id"],
        "role": pack.SOURCE_MAIN_ROLE,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "visible_refreshes": 1,
        "retry": False,
        "recovery": False,
        "autochain": False,
    }
    if any(deep.get(key) != wanted for key, wanted in exact.items()):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C lineage or driver semantics differ"
        )
    payload = candidate.read_bytes()
    claim_path_value = deep.get("claim_path") or deep.get("claim_file")
    if not isinstance(claim_path_value, str):
        raise P2CommentedWhiteSuccessorRunnerError("P2-C source claim path missing")
    claim_path = Path(claim_path_value)
    if not claim_path.is_absolute():
        claim_path = REPO_ROOT / claim_path
    if not claim_path.is_file() or claim_path.is_symlink():
        raise P2CommentedWhiteSuccessorRunnerError("P2-C source claim missing")
    claim_payload = claim_path.read_bytes()
    claim_file_sha = hashlib.sha256(claim_payload).hexdigest()
    if deep.get("claim_file_sha256") not in (None, claim_file_sha):
        raise P2CommentedWhiteSuccessorRunnerError("P2-C source claim differs")
    return {
        "verified": True,
        **exact,
        "source_success_claimed": True,
        "path": _repo_relative(candidate),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": deep["canonical_integrity_sha256"],
        "boot_nonce": deep["boot_nonce"],
        "claim": {
            "path": _repo_relative(claim_path),
            "bytes": len(claim_payload),
            "file_sha256": claim_file_sha,
            "canonical_integrity_sha256": deep[
                "claim_canonical_integrity_sha256"
            ],
        },
    }


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise P2CommentedWhiteSuccessorRunnerError(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise P2CommentedWhiteSuccessorRunnerError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise P2CommentedWhiteSuccessorRunnerError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if integrity != {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }:
        raise P2CommentedWhiteSuccessorRunnerError(f"{label} integrity differs")
    return value


def _validate_exact_ipv4_mac_binding(
    path: Path, base_url: str
) -> dict[str, Any]:
    """Deep-validate one fresh literal IPv4↔MAC binding without I/O.

    The P2 main runner owns the canonical binding schema and validator.  Using
    that validator here keeps the successor's identity rules identical to the
    main action (one literal candidate, one active probe, expected device MAC,
    no HTTP/mutation/refresh, and an O_EXCL terminal evidence file).
    """

    source = _source_once()
    validator = getattr(source, "validate_exact_ipv4_mac_binding", None)
    if not callable(validator):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C source exact IPv4/MAC validator is unavailable"
        )
    try:
        value = validator(Path(path), base_url)
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise P2CommentedWhiteSuccessorRunnerError(
            "fresh exact IPv4/MAC binding failed deep validation"
        ) from error
    if not isinstance(value, Mapping):
        raise P2CommentedWhiteSuccessorRunnerError(
            "fresh exact IPv4/MAC binding validator returned a non-object"
        )
    # Copy into a plain dict so later evidence cannot be changed by a caller.
    result = deepcopy(dict(value))
    if (
        result.get("fresh_binding_passed") is not True
        or result.get("device_application_identity_proven") is not False
        or result.get("device_api_requests") != 0
        or result.get("mutation_requests") != 0
        or result.get("visible_refresh_requests") != 0
        or result.get("outcome") != "active_exact_mac_binding_pass"
        or not isinstance(result.get("candidate_ipv4"), str)
        or not isinstance(result.get("expected_mac"), str)
        or not isinstance(result.get("path"), str)
    ):
        raise P2CommentedWhiteSuccessorRunnerError(
            "fresh exact IPv4/MAC binding semantics differ"
        )
    return result


def _canonical_private_origin(value: str) -> str:
    """Use the sealed P2 origin parser (HTTP/80, literal RFC1918 IPv4)."""

    source = _source_once()
    parser = getattr(source, "_private_origin", None)
    if not callable(parser):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C source private-origin validator is unavailable"
        )
    try:
        origin = parser(value)
    except (TypeError, ValueError, RuntimeError) as error:
        raise P2CommentedWhiteSuccessorRunnerError(
            "successor base URL is not the exact private HTTP origin"
        ) from error
    if not isinstance(origin, str) or not origin:
        raise P2CommentedWhiteSuccessorRunnerError(
            "successor private-origin validator returned an invalid origin"
        )
    return origin


def _set_current_binding(binding: Mapping[str, Any], origin: str) -> None:
    """Set the per-process binding used by evidence enrichment and replay."""

    global _CURRENT_EXACT_IPV4_MAC_BINDING, _CURRENT_ORIGIN  # noqa: PLW0603
    _CURRENT_EXACT_IPV4_MAC_BINDING = deepcopy(dict(binding))
    _CURRENT_ORIGIN = str(origin)


def _clear_current_binding() -> None:
    """Clear invocation-local binding state after a pure offline operation."""

    global _CURRENT_EXACT_IPV4_MAC_BINDING, _CURRENT_ORIGIN  # noqa: PLW0603
    _CURRENT_EXACT_IPV4_MAC_BINDING = None
    _CURRENT_ORIGIN = None


def _validate_current_binding_in_evidence(
    evidence: Mapping[str, Any], *, origin: str, binding: Mapping[str, Any]
) -> None:
    """Require diagnostic/action evidence to carry the exact fresh binding."""

    if evidence.get("base_url") != origin:
        raise P2CommentedWhiteSuccessorRunnerError(
            "successor evidence origin differs from fresh binding"
        )
    observed = evidence.get("exact_ipv4_mac_binding")
    if not isinstance(observed, Mapping) or dict(observed) != dict(binding):
        raise P2CommentedWhiteSuccessorRunnerError(
            "successor evidence exact IPv4/MAC binding differs"
        )


def _install_binding_evidence_writer(host: Any) -> None:
    """Attach runtime binding to durable diagnostic/action envelopes.

    The dynamic binding must not be added to ``SOURCE_MAIN_BINDING`` because
    that mapping is checked against firmware responses.  Instead, wrap the
    delegate's existing O_EXCL writer for only the two successor evidence
    files.  The original writer still computes the canonical integrity seal.
    """

    original = getattr(host, "_p2_successor_original_write_new", None)
    if original is not None:
        return
    original = host._write_new
    host._p2_successor_original_write_new = original

    def write_with_binding(path: Path, value: Mapping[str, Any]) -> None:
        candidate = Path(path).resolve()
        targets = {DIAGNOSTIC_OUTPUT.resolve(), ACTION_OUTPUT.resolve()}
        binding = _CURRENT_EXACT_IPV4_MAC_BINDING
        origin = _CURRENT_ORIGIN
        if candidate in targets and binding is not None and origin is not None:
            enriched = deepcopy(dict(value))
            existing = enriched.get("exact_ipv4_mac_binding")
            if existing is not None and dict(existing) != dict(binding):
                raise P2CommentedWhiteSuccessorRunnerError(
                    "delegate evidence already contains a different IPv4/MAC binding"
                )
            enriched["exact_ipv4_mac_binding"] = deepcopy(binding)
            # The delegate action envelope historically omitted its origin;
            # adding it makes the action replayable against the same binding.
            if candidate == ACTION_OUTPUT.resolve():
                existing_origin = enriched.get("base_url")
                if existing_origin is not None and existing_origin != origin:
                    raise P2CommentedWhiteSuccessorRunnerError(
                        "delegate action origin differs from fresh binding"
                    )
                enriched["base_url"] = origin
            original(path, enriched)
            return
        original(path, value)

    host._write_new = write_with_binding


def _verify_source_pack() -> None:
    source_pack = pack._source_pack()  # noqa: SLF001
    validator = getattr(source_pack, "validate_artifacts", None)
    if callable(validator):
        validator()
        return
    builder = getattr(source_pack, "build_report", None)
    if callable(builder):
        try:
            builder(verify_artifacts=True)
            return
        except TypeError:
            pass
    if not pack.source_artifacts_are_sealed():
        raise P2CommentedWhiteSuccessorRunnerError("P2-C source artifacts unsealed")


def _load_delegate() -> Any:
    global _DELEGATE  # noqa: PLW0603
    if _DELEGATE is not None:
        return _DELEGATE
    report = pack.build_report(verify_artifacts=True)
    _verify_source_pack()
    source = _source_once()
    old = importlib.import_module(
        "tools.mf1750_lightness_hold_function_chain_v1_white_successor_v1_once"
    )
    pack.CONTRACT_ID = report["contract_id"]
    pack.DESCRIPTOR_ID = report["descriptor_id"]
    pack.ACTION_ID = report["action_id"]
    pack.DESCRIPTOR_MARKER = pack.compiled_identity_marker(report)
    pack.source_pack = pack._source_pack()  # type: ignore[attr-defined]  # noqa: SLF001
    reviewed = old.reviewed
    host = old.host
    endpoints = {
        name: f"{pack.BASE_ROUTE}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    binding = _source_binding(report)
    old.pack = pack
    old.source_once = source
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
    reviewed.source_once = source
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
    # Reuse the main P2 literal-private-origin parser in the delegated host.
    # The older containment host accepts arbitrary private ports; assigning the
    # sealed parser closes that compatibility escape hatch (campaign port 80).
    source_origin = getattr(source, "_private_origin", None)
    if not callable(source_origin):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C source private-origin validator is unavailable"
        )
    host._origin = source_origin
    host._base._origin = source_origin  # type: ignore[attr-defined]
    _install_binding_evidence_writer(host)

    def source_paths() -> dict[int, Path]:
        return {1: _source_terminal_path()}

    def verify_artifacts() -> None:
        pack.build_report(verify_artifacts=True)
        _verify_source_pack()

    def validate_source(
        path: Path, *, confirm_optional_l4_source: bool = False
    ) -> dict[str, Any]:
        if confirm_optional_l4_source is True:
            raise P2CommentedWhiteSuccessorRunnerError("alternate source forbidden")
        return _validate_source_terminal(path, report)

    def dynamic_binding(source_evidence: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **deepcopy(binding),
            "selected_source_terminal_evidence": deepcopy(dict(source_evidence)),
            "selected_source_terminal_evidence_o_excl_bound": True,
        }

    def validate_receipt(source_evidence: Mapping[str, Any]) -> dict[str, Any]:
        value = _read_integrity_json(SOURCE_GATE_OUTPUT, label="P2-C source receipt")
        if (
            value.get("kind") != SOURCE_GATE_KIND
            or value.get("white_campaign_id") != pack.CAMPAIGN_ID
            or value.get("white_contract_id") != report["contract_id"]
            or value.get("white_descriptor_id") != report["descriptor_id"]
            or value.get("white_action_id") != report["action_id"]
            or value.get("selected_source_terminal_evidence")
            != dict(source_evidence)
            or value.get("state")
            != "DEEPLY_VALIDATED_P2_COMMENTED_ORDINAL1_COMPLETE_BEFORE_ANY_WHITE_LIVE_REQUEST"
            or value.get("write_contract") != "O_EXCL"
            or value.get("no_retry") is not True
            or value.get("no_recovery") is not True
            or value.get("no_autochain") is not True
        ):
            raise P2CommentedWhiteSuccessorRunnerError("P2-C source receipt differs")
        payload = SOURCE_GATE_OUTPUT.read_bytes()
        return {
            "verified": True,
            "path": _repo_relative(SOURCE_GATE_OUTPUT),
            "bytes": len(payload),
            "file_sha256": hashlib.sha256(payload).hexdigest(),
            "canonical_integrity_sha256": value["integrity"]["sha256"],
        }

    def write_receipt(source_evidence: Mapping[str, Any]) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "kind": SOURCE_GATE_KIND,
            "created_at": host._now(),  # noqa: SLF001
            "white_campaign_id": pack.CAMPAIGN_ID,
            "white_contract_id": report["contract_id"],
            "white_descriptor_id": report["descriptor_id"],
            "white_action_id": report["action_id"],
            "selected_source_terminal_evidence": deepcopy(dict(source_evidence)),
            "state": (
                "DEEPLY_VALIDATED_P2_COMMENTED_ORDINAL1_COMPLETE_"
                "BEFORE_ANY_WHITE_LIVE_REQUEST"
            ),
            "write_contract": "O_EXCL",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
        host._write_new(SOURCE_GATE_OUTPUT, value)  # noqa: SLF001
        return validate_receipt(source_evidence)

    reviewed._source_terminal_paths = source_paths  # noqa: SLF001
    reviewed._verify_artifacts = verify_artifacts  # noqa: SLF001
    reviewed._validate_source_terminal = validate_source  # noqa: SLF001
    reviewed._dynamic_source_binding = dynamic_binding  # noqa: SLF001
    reviewed._read_integrity_json = _read_integrity_json  # noqa: SLF001
    reviewed._validate_source_receipt = validate_receipt  # noqa: SLF001
    reviewed._write_source_receipt = write_receipt  # noqa: SLF001
    _DELEGATE = old
    return old


def dry_validate() -> dict[str, Any]:
    value = pack.dry_validate(require_sealed=True, verify_artifacts=True)
    contract = pack.build_report(verify_artifacts=True)["contract"]
    if (
        contract["accepted_source_ordinals"] != [1]
        or contract["source_fault_not_accepted"] is not True
        or contract["source_early_stop_not_accepted"] is not True
        or contract["factory_otp"] is not True
        or contract["runtime_lut_write"] is not False
        or contract["one_visible_refresh"] is not True
        or contract["full_busy_required"] is not True
        or contract["retry"] is not False
        or contract["automatic_recovery"] is not False
        or contract["autochain"] is not False
    ):
        raise P2CommentedWhiteSuccessorRunnerError(
            "P2-C white successor contract differs"
        )
    return {
        **value,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-host-validation",
        "accepted_source_ordinals": [1],
        "source_terminal_path": _repo_relative(_source_terminal_path()),
        "source_gate_o_excl": True,
        "same_boot_j2_off_then_gnd_j2_on": True,
        "exactly_one_factory_otp_white_refresh": True,
        "full_busy_required": True,
        "no_runtime_lut": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    exact_ipv4_mac_binding: Path,
    confirm_j2_off: bool,
    output: Path | None = None,
    requester: Any = None,
) -> dict[str, Any]:
    old = _load_delegate()
    origin = _canonical_private_origin(base_url)
    binding = _validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    _set_current_binding(binding, origin)
    result = old.reviewed.diagnose_j2_off(
        origin,
        source_terminal_evidence=source_terminal_evidence,
        confirm_j2_off=confirm_j2_off,
        confirm_optional_l4_source=False,
        output=output,
        requester=requester,
    )
    evidence = _read_integrity_json(
        DIAGNOSTIC_OUTPUT, label="successor J2-OFF diagnostic"
    )
    _validate_current_binding_in_evidence(
        evidence, origin=origin, binding=binding
    )
    return {
        **dict(result),
        "exact_ipv4_mac_binding": deepcopy(binding),
        "binding_origin": origin,
    }


def run_once(
    base_url: str,
    *,
    source_terminal_evidence: Path,
    exact_ipv4_mac_binding: Path,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    claims: Path | None = None,
    output: Path | None = None,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 20,
) -> dict[str, Any]:
    old = _load_delegate()
    origin = _canonical_private_origin(base_url)
    binding = _validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    _set_current_binding(binding, origin)
    diagnostic_path = Path(DIAGNOSTIC_OUTPUT).resolve()
    if not diagnostic_path.is_file() or diagnostic_path.is_symlink():
        raise P2CommentedWhiteSuccessorRunnerError(
            "successor J2-OFF diagnostic is missing or unsafe"
        )
    diagnostic = _read_integrity_json(
        diagnostic_path, label="successor J2-OFF diagnostic"
    )
    _validate_current_binding_in_evidence(
        diagnostic, origin=origin, binding=binding
    )
    result = old.reviewed.run_once(
        origin,
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
    evidence = _read_integrity_json(
        ACTION_OUTPUT, label="successor terminal action evidence"
    )
    _validate_current_binding_in_evidence(
        evidence, origin=origin, binding=binding
    )
    return {
        **dict(result),
        "exact_ipv4_mac_binding": deepcopy(binding),
        "binding_origin": origin,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    for name in ("diagnose-j2-off", "run"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--base-url", required=True)
        command.add_argument("--source-terminal-evidence", type=Path, required=True)
        command.add_argument("--exact-ipv4-mac-binding", type=Path, required=True)
        if name == "diagnose-j2-off":
            command.add_argument("--confirm-j2-off", action="store_true", required=True)
        else:
            command.add_argument("--confirm-j2-on", action="store_true", required=True)
            command.add_argument("--confirm-gnd-normal", action="store_true", required=True)
            command.add_argument("--poll-seconds", type=float, default=65.0)
            command.add_argument("--poll-count", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                source_terminal_evidence=args.source_terminal_evidence,
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (OSError, RuntimeError) as error:
        print(f"P2-C white successor blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
