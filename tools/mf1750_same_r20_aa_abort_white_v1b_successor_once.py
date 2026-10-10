#!/usr/bin/env python3
"""Host-only V1B diagnostic successor for the already-flashed AA-abort V1 app.

``diagnose-j2-off`` is a manually started, immutable four-GET replacement for
the first failed diagnostic.  ``run`` accepts only that successful successor,
requires the same boot nonce, and then delegates to the reviewed V1 one-shot
ARM/EXECUTE mechanics.  There is no flash, reset, relay, retry, recovery, or
autochain operation in this runner.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_same_r20_aa_abort_white_v1_once as v1_once,
)
from tools import (  # noqa: E402
    mf1750_same_r20_aa_abort_white_v1b_successor_pack as pack,
)


ContainmentError = v1_once.ContainmentError
ContainmentConsumedError = v1_once.ContainmentConsumedError
Requester = Callable[..., tuple[int, Mapping[str, Any]]]

SUCCESSOR_DIAGNOSTIC_OUTPUT = pack.SUCCESSOR_DIAGNOSTIC_FILE
ACTION_OUTPUT = pack.ACTION_OUTPUT
DEFAULT_CLAIMS = pack.CLAIMS_ROOT
FLASH_OUTPUT = pack.FLASH_FILE
FAILED_DIAGNOSTIC_OUTPUT = pack.FAILED_DIAGNOSTIC_FILE
BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS = (
    v1_once.BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS
)
NORMALIZATION_EVIDENCE_KEY = "_host_v1b_exact_identity_normalization"


def _repo_relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _fixed_path(value: Path, expected: Path, *, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    wanted = Path(expected).resolve()
    if candidate != wanted:
        raise ContainmentError(f"{label} is fixed at {_repo_relative(expected)}")
    return wanted


@contextmanager
def _v1_successor_diagnostic_binding() -> Iterator[None]:
    """Temporarily point the reviewed V1 gate at the immutable V1B receipt."""

    old_output = v1_once.DIAGNOSTIC_OUTPUT
    old_kind = v1_once.DIAGNOSTIC_KIND
    v1_once.DIAGNOSTIC_OUTPUT = SUCCESSOR_DIAGNOSTIC_OUTPUT
    v1_once.DIAGNOSTIC_KIND = pack.SUCCESSOR_DIAGNOSTIC_KIND
    try:
        yield
    finally:
        v1_once.DIAGNOSTIC_OUTPUT = old_output
        v1_once.DIAGNOSTIC_KIND = old_kind


def _load_successor_diagnostic_gate(*, expected_origin: str) -> str:
    """Require the sealed successful V1B receipt before run-side network I/O."""

    try:
        pack.validate_predecessor_evidence(require_unexecuted=True)
        value = pack._read_sealed_json(  # noqa: SLF001
            SUCCESSOR_DIAGNOSTIC_OUTPUT,
            label="V1B successor J2-OFF diagnostic",
        )
    except ValueError as exc:
        raise ContainmentError(str(exc)) from exc
    for key, wanted in pack.SUCCESSOR_EVIDENCE_BINDING.items():
        if value.get(key) != wanted:
            raise ContainmentError(f"V1B successor diagnostic {key} differs")
    if value.get("successor_id") != pack.SUCCESSOR_ID:
        raise ContainmentError("V1B successor diagnostic successor_id differs")
    transcript = value.get("transcript")
    if not isinstance(transcript, list) or len(transcript) != 4:
        raise ContainmentError("V1B successor diagnostic transcript length differs")
    for item in transcript:
        body = item.get("body") if isinstance(item, Mapping) else None
        if not isinstance(body, Mapping):
            raise ContainmentError("V1B successor diagnostic body is malformed")
        _validate_normalization_evidence(body)
    with _v1_successor_diagnostic_binding():
        return v1_once._load_successor_diagnostic_gate(  # noqa: SLF001
            expected_origin=expected_origin
        )


def _decode_exact_malformed_identity_payload(
    payload: bytes,
    *,
    method: str,
    path: str,
    response_headers: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    """Apply the unique one-byte repair and attach independently checkable evidence."""

    if len(payload) > v1_once.MAX_JSON_BYTES:
        raise ContainmentError(f"direct {method} {path} response is too large")
    malformed_count = payload.count(pack.MALFORMED_IDENTITY_MARKER)
    corrected_count = payload.count(pack.CORRECTED_IDENTITY_MARKER)
    if malformed_count != 1 or corrected_count != 0:
        raise ContainmentError(
            "direct response exact malformed identity marker count differs "
            f"(malformed={malformed_count}, corrected={corrected_count})"
        )
    normalized = payload.replace(
        pack.MALFORMED_IDENTITY_MARKER,
        pack.CORRECTED_IDENTITY_MARKER,
        1,
    )
    try:
        value = json.loads(normalized.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainmentError(
            f"direct {method} {path} response remains invalid after exact V1 fix"
        ) from exc
    if not isinstance(value, Mapping):
        raise ContainmentError(f"direct {method} {path} response root is not an object")
    if NORMALIZATION_EVIDENCE_KEY in value:
        raise ContainmentError(
            "device response collides with reserved V1B evidence key"
        )
    result = dict(value)
    result[NORMALIZATION_EVIDENCE_KEY] = {
        "rule": "replace_exact_unique_malformed_identity_marker_once",
        "malformed_marker_count": malformed_count,
        "corrected_marker_count_before_replace": corrected_count,
        "replacement_count": 1,
        "raw_body_bytes": len(payload),
        "raw_body_sha256": hashlib.sha256(payload).hexdigest(),
        "raw_body_base64": base64.b64encode(payload).decode("ascii"),
        "malformed_marker_offset": payload.find(pack.MALFORMED_IDENTITY_MARKER),
        "normalized_body_bytes": len(normalized),
        "normalized_body_sha256": hashlib.sha256(normalized).hexdigest(),
        "http_content_type": (response_headers or {}).get("content-type"),
        "http_content_length": (response_headers or {}).get("content-length"),
    }
    return result


def _validate_normalization_evidence(value: Mapping[str, Any]) -> None:
    evidence = value.get(NORMALIZATION_EVIDENCE_KEY)
    if not isinstance(evidence, Mapping):
        raise ContainmentError("V1B exact normalization evidence is missing")
    try:
        raw = base64.b64decode(evidence.get("raw_body_base64", ""), validate=True)
    except (TypeError, ValueError) as exc:
        raise ContainmentError("V1B raw response base64 is malformed") from exc
    offset = raw.find(pack.MALFORMED_IDENTITY_MARKER)
    if (
        evidence.get("rule") != "replace_exact_unique_malformed_identity_marker_once"
        or evidence.get("malformed_marker_count") != 1
        or evidence.get("corrected_marker_count_before_replace") != 0
        or evidence.get("replacement_count") != 1
        or evidence.get("raw_body_bytes") != len(raw)
        or evidence.get("raw_body_sha256") != hashlib.sha256(raw).hexdigest()
        or evidence.get("malformed_marker_offset") != offset
        or offset < 0
        or raw.count(pack.MALFORMED_IDENTITY_MARKER) != 1
        or raw.count(pack.CORRECTED_IDENTITY_MARKER) != 0
    ):
        raise ContainmentError("V1B raw response normalization binding differs")
    normalized = raw.replace(
        pack.MALFORMED_IDENTITY_MARKER, pack.CORRECTED_IDENTITY_MARKER, 1
    )
    if (
        evidence.get("normalized_body_bytes") != len(normalized)
        or evidence.get("normalized_body_sha256")
        != hashlib.sha256(normalized).hexdigest()
    ):
        raise ContainmentError("V1B normalized response digest differs")
    try:
        decoded = json.loads(normalized.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainmentError(
            "V1B normalized response is not exact UTF-8 JSON"
        ) from exc
    observed = dict(value)
    observed.pop(NORMALIZATION_EVIDENCE_KEY, None)
    if decoded != observed:
        raise ContainmentError("V1B normalized response body binding differs")


def _exact_malformed_identity_requester(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Normalize only the one proven V1 identityJson quote defect."""

    request = v1_once.urllib_request.Request(  # noqa: SLF001
        f"{base_url}{path}",
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
        data=None,
    )
    opener = v1_once.urllib_request.build_opener(  # noqa: SLF001
        v1_once.urllib_request.ProxyHandler({}),  # noqa: SLF001
        v1_once._NoRedirect(),  # noqa: SLF001
    )
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            status = response.status
            payload = response.read(v1_once.MAX_JSON_BYTES + 1)
            response_headers = {
                str(key).lower(): str(value) for key, value in response.headers.items()
            }
    except v1_once.urllib_error.HTTPError as exc:  # noqa: SLF001
        status = exc.code
        payload = exc.read(v1_once.MAX_JSON_BYTES + 1)
        response_headers = {
            str(key).lower(): str(value) for key, value in exc.headers.items()
        }
    except (OSError, v1_once.urllib_error.URLError) as exc:  # noqa: SLF001
        raise ContainmentError(f"direct {method} {path} failed: {exc}") from exc
    return status, _decode_exact_malformed_identity_payload(
        payload,
        method=method,
        path=path,
        response_headers=response_headers,
    )


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = _exact_malformed_identity_requester,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Seal exactly four GETs and no POST/claim under the fixed V1B path."""

    if confirm_j2_off is not True:
        raise ContainmentError("diagnose-j2-off requires explicit J2-OFF confirmation")
    output = _fixed_path(
        Path(output), SUCCESSOR_DIAGNOSTIC_OUTPUT, label="diagnostic output"
    )
    if output.exists():
        raise ContainmentError(f"refusing to overwrite {output}")
    transcript: list[dict[str, Any]] = []
    progress = {"stage": "diagnostic_start"}
    running_sha: str | None = None
    boot_nonce: str | None = None
    artifact_preflight_complete = False
    origin: str | None = None
    try:
        progress["stage"] = "sealed_predecessor_and_artifact_preflight"
        pack.build_report(verify_artifacts=True, require_unexecuted=True)
        artifact_preflight_complete = True
        progress["stage"] = "origin_validation"
        origin = v1_once._origin(base_url)  # noqa: SLF001
        checked_timeout = v1_once._validate_timeout(timeout)  # noqa: SLF001
        running_sha, boot_nonce, report = v1_once._preflight(  # noqa: SLF001
            requester,
            transcript,
            origin,
            expected_busy=0,
            timeout=checked_timeout,
            progress=progress,
        )
        for item in transcript:
            body = item.get("body")
            if not isinstance(body, Mapping):
                raise ContainmentError("V1B diagnostic response body is malformed")
            _validate_normalization_evidence(body)
        evidence = {
            "schema_version": 1,
            "kind": pack.SUCCESSOR_DIAGNOSTIC_KIND,
            **v1_once.SOURCE_MAIN_BINDING,
            **pack.SUCCESSOR_EVIDENCE_BINDING,
            "successor_id": pack.SUCCESSOR_ID,
            "created_at": v1_once._now(),  # noqa: SLF001
            "outcome": "j2_off_diagnostic_pass",
            "firmware_sha256": v1_once.pack.FIRMWARE_BIN_SHA256,
            "running_app_elf_sha256": running_sha,
            "boot_nonce": boot_nonce,
            "action": v1_once.ACTION,
            "j2_confirmed_off": True,
            "fresh_nvs": True,
            "busy": 0,
            "report_terminal_state": "NOT_EXECUTED",
            "report": deepcopy(dict(report)),
            "artifact_preflight_completed_before_network": True,
            "base_url": origin,
            "transport": {
                "mode": "direct_private_literal_ipv4_http",
                "proxy": False,
                "redirect": False,
            },
            "permanent_claims_created": 0,
            "claims_directory_accessed": False,
            "network": {"get": 4, "post": 0},
            "transcript": transcript,
            "visible_refreshes": 0,
            "output_write_contract": "O_EXCL",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "no_ordinal_skip": True,
        }
        progress["stage"] = "successor_diagnostic_evidence_create"
        v1_once._write_new(output, evidence)  # noqa: SLF001
        return evidence
    except Exception as exc:
        attempt = v1_once._attempt_evidence(  # noqa: SLF001
            outcome="j2_off_diagnostic_failed_no_claim",
            stage=progress["stage"],
            error=exc,
            transcript=transcript,
            claim_file=None,
            claim_state="not_created",
            running_sha=running_sha,
            boot_nonce=boot_nonce,
        )
        attempt.update(pack.SUCCESSOR_EVIDENCE_BINDING)
        attempt["successor_id"] = pack.SUCCESSOR_ID
        attempt["kind"] = pack.SUCCESSOR_DIAGNOSTIC_ATTEMPT_KIND
        attempt["artifact_preflight_completed_before_network"] = (
            artifact_preflight_complete
        )
        attempt["base_url"] = origin
        attempt["transport"] = {
            "mode": "direct_private_literal_ipv4_http",
            "proxy": False,
            "redirect": False,
        }
        attempt["permanent_claims_created"] = 0
        attempt["claims_directory_accessed"] = False
        write_error = None
        if not output.exists():
            write_error = v1_once._write_attempt_best_effort(  # noqa: SLF001
                output, attempt
            )
        detail = (
            f"; attempt evidence write failed: {write_error}" if write_error else ""
        )
        raise ContainmentError(f"V1B J2-OFF diagnostic failed: {exc}{detail}") from exc


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    confirm_j2_on: bool = False,
    requester: Requester = _exact_malformed_identity_requester,
    timeout: float = 10.0,
    poll_seconds: float = BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    poll_count: int = 20,
    sleeper: Callable[[float], None] = v1_once.time.sleep,
) -> dict[str, Any]:
    """Run the unchanged V1 action only after the successful V1B gate."""

    if confirm_j2_on is not True:
        raise ContainmentError("run requires explicit J2-ON confirmation")
    claims = _fixed_path(Path(claims), DEFAULT_CLAIMS, label="claims root")
    output = _fixed_path(Path(output), ACTION_OUTPUT, label="action output")
    pack.build_report(verify_artifacts=True, require_unexecuted=True)
    origin = v1_once._origin(base_url)  # noqa: SLF001
    _load_successor_diagnostic_gate(expected_origin=origin)

    def evidence_required_requester(
        *args: Any, **kwargs: Any
    ) -> tuple[int, Mapping[str, Any]]:
        response = requester(*args, **kwargs)
        if not isinstance(response, tuple) or len(response) != 2:
            raise ContainmentError("V1B requester did not return a status/body tuple")
        status, body = response
        if not isinstance(body, Mapping):
            raise ContainmentError("V1B requester body is not an object")
        _validate_normalization_evidence(body)
        return status, body

    with _v1_successor_diagnostic_binding():
        return v1_once.run_once(
            origin,
            claims=claims,
            output=output,
            confirm_j2_on=True,
            requester=evidence_required_requester,
            timeout=timeout,
            poll_seconds=poll_seconds,
            poll_count=poll_count,
            sleeper=sleeper,
        )


def describe() -> dict[str, Any]:
    report = pack.build_report(verify_artifacts=False, require_unexecuted=False)
    return {
        **report,
        "purpose": "manual_host_only_successor_after_preserved_first_diagnostic_failure",
        "fixed_outputs": {
            "predecessor_flash": _repo_relative(FLASH_OUTPUT),
            "predecessor_failed_diagnostic": _repo_relative(FAILED_DIAGNOSTIC_OUTPUT),
            "successor_diagnostic": _repo_relative(SUCCESSOR_DIAGNOSTIC_OUTPUT),
            "action": _repo_relative(ACTION_OUTPUT),
            "claims_root": _repo_relative(DEFAULT_CLAIMS),
        },
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "network_requests": 0,
        "visible_refreshes": 0,
    }


def dry_validate() -> dict[str, Any]:
    report = pack.build_report(verify_artifacts=True, require_unexecuted=True)
    return {
        "schema_version": 1,
        "kind": "mf1750-same-r20-aa-abort-white-v1b-successor-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "host_only": True,
        "successor_id": pack.SUCCESSOR_ID,
        "bound_v1_contract_id": pack.v1_pack.CONTRACT_ID,
        "bound_v1_action_id": pack.v1_pack.ACTION_ID,
        "predecessor_failed_diagnostic_sha256": pack.FAILED_DIAGNOSTIC_SHA256,
        "predecessor_flash_evidence_sha256": pack.FLASH_SHA256,
        "successor_diagnostic_output": _repo_relative(SUCCESSOR_DIAGNOSTIC_OUTPUT),
        "artifact_binding": report["validated_evidence"],
        "network_requests": 0,
        "visible_refreshes": 0,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "device_reset": False,
        "display_refreshed": False,
        "claim_created": False,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnostic = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, default=SUCCESSOR_DIAGNOSTIC_OUTPUT)
    diagnostic.add_argument("--timeout", type=float, default=10.0)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, default=ACTION_OUTPUT)
    run.add_argument("--timeout", type=float, default=10.0)
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    )
    run.add_argument("--poll-count", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            value = run_once(
                args.base_url,
                claims=args.claims,
                output=args.output,
                confirm_j2_on=args.confirm_j2_on,
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except ContainmentError as exc:
        print(f"Same-R20 AA-abort V1B successor error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
