#!/usr/bin/env python3
"""Seal four direct GETs proving the consumed RAW-P16 V1 action stayed unused.

This is a diagnostic evidence collector, not an action runner.  It creates no
claim, sends no POST, follows no redirect, and never asks the panel to refresh.
The only network surface is the four frozen read-only V1 routes.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_once as original_once,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_pack as pack,
)


class SalvageError(ValueError):
    """The read-only evidence could not establish the frozen V1 state."""


RawResponse = tuple[int, Mapping[str, str], bytes, str]
Requester = Callable[[str, str, float], RawResponse]

ENDPOINT_NAMES = ("version", "manifest", "status", "report")
ENDPOINTS = {name: f"{pack.BASE_ROUTE}/{name}" for name in ENDPOINT_NAMES}
DEFAULT_CLAIM = REPO_ROOT / (
    ".test-output/hardware/.mf1750_raw_p16_pre_white_anchor_v1_claims/"
    f"{pack.ACTION_ID}.json"
)
DEFAULT_OUTPUT = REPO_ROOT / (
    ".test-output/hardware/MF1750_RAW_P16_PRE_WHITE_ANCHOR_20260828_V1/"
    "read-only-four-get-transcript.json"
)
RFC1918 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strict_origin(base_url: str) -> str:
    """Accept only HTTP to an RFC1918 literal IPv4 address on port 80."""

    try:
        parsed = urllib_parse.urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise SalvageError("base URL is malformed") from exc
    if parsed.scheme != "http":
        raise SalvageError("base URL scheme must be exactly http")
    if parsed.username is not None or parsed.password is not None:
        raise SalvageError("base URL userinfo is forbidden")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise SalvageError("base URL must contain only the origin")
    if port not in (None, 80):
        raise SalvageError("base URL port must be 80")
    if parsed.hostname is None:
        raise SalvageError("base URL host is absent")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise SalvageError("base URL host must be a literal IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in RFC1918
    ):
        raise SalvageError("base URL host must be an RFC1918 literal IPv4 address")
    return f"http://{address}"


class _RejectRedirects(urllib_request.HTTPRedirectHandler):
    """Turn every redirect into a terminal HTTP response."""

    def redirect_request(  # type: ignore[override]
        self,
        request: urllib_request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Mapping[str, str],
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


_DIRECT_OPENER = urllib_request.build_opener(
    urllib_request.ProxyHandler({}),
    _RejectRedirects(),
)


def _direct_get(origin: str, path: str, timeout: float) -> RawResponse:
    url = f"{origin}{path}"
    request = urllib_request.Request(url, method="GET", data=None)
    try:
        with _DIRECT_OPENER.open(request, timeout=timeout) as response:
            return (
                int(response.status),
                dict(response.headers.items()),
                response.read(),
                response.geturl(),
            )
    except urllib_error.HTTPError as exc:
        return int(exc.code), dict(exc.headers.items()), exc.read(), exc.geturl()
    except urllib_error.URLError as exc:
        raise SalvageError("direct no-proxy GET failed") from exc


def _read_existing_claim(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise SalvageError("the permanent V1 claim is absent or is a symlink")
    if path.name != f"{pack.ACTION_ID}.json":
        raise SalvageError("the permanent V1 claim filename differs")
    raw = path.read_bytes()
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SalvageError("the permanent V1 claim is not UTF-8 JSON") from exc
    if not isinstance(root, dict):
        raise SalvageError("the permanent V1 claim root is not an object")
    integrity = root.get("integrity")
    body = {key: value for key, value in root.items() if key != "integrity"}
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != _sha256(_canonical(body))
    ):
        raise SalvageError("the permanent V1 claim integrity differs")
    expected = {
        "schema_version": 1,
        "kind": pack.CLAIM_KIND,
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "action": pack.build_report(verify_artifacts=True)["action"],
        "state": "claimed_before_first_network_request",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise SalvageError(f"the permanent V1 claim {key} differs")
    return {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "file_sha256": _sha256(raw),
        "canonical_sha256": integrity["sha256"],
        "created_at": root.get("created_at"),
        "read_only_existing_claim": True,
        "claim_created_by_salvage": False,
    }


def _content_type(headers: Mapping[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value
    return ""


def _response_record(
    *,
    ordinal: int,
    name: str,
    path: str,
    status: int,
    headers: Mapping[str, str],
    raw: bytes,
    effective_url: str,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    content_type = _content_type(headers)
    record: dict[str, Any] = {
        "ordinal": ordinal,
        "method": "GET",
        "endpoint": name,
        "path": path,
        "status": status,
        "content_type": content_type,
        "effective_url": effective_url,
        "redirect_followed": False,
        "received_at": _now(),
        "raw_body_bytes": len(raw),
        "raw_body_sha256": _sha256(raw),
        "raw_body_base64": base64.b64encode(raw).decode("ascii"),
    }
    if status != 200:
        raise SalvageError(f"GET {name} returned HTTP {status}")
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise SalvageError(f"GET {name} content type is not application/json")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SalvageError(f"GET {name} body is not UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise SalvageError(f"GET {name} JSON root is not an object")
    record["parsed_body"] = value
    return record, value


def _validate_four(
    responses: Mapping[str, Mapping[str, Any]], origin: str
) -> dict[str, Any]:
    version = responses["version"]
    running_sha = original_once.base._validate_version(version)
    if running_sha != pack.FIRMWARE_ELF_SHA256:
        raise SalvageError("running app ELF SHA-256 differs from the frozen V1 ELF")
    for name, value in responses.items():
        if value.get("target_campaign_id") != pack.TARGET_CAMPAIGN_ID:
            raise SalvageError(f"GET {name} target campaign differs")
        if value.get("purpose") != pack.PURPOSE:
            raise SalvageError(f"GET {name} purpose differs")
    original_once.base._validate_manifest(responses["manifest"], running_sha)
    boot_nonce = original_once.base._validate_fresh_status(
        responses["status"], running_sha
    )
    original_once.base._validate_fresh_report(responses["report"], running_sha)
    status = responses["status"]
    if any(status.get(key) != 0 for key in ("sck", "dc", "mosi")):
        raise SalvageError("fresh status safe GPIO tail differs")
    return {
        "origin": origin,
        "running_app_elf_sha256": running_sha,
        "boot_nonce": boot_nonce,
        "state": status["state"],
        "phase": status["phase"],
        "cursor_raw": status["cursor_raw"],
        "next_ordinal": status["next_ordinal"],
        "persistent_key_present": status["persistent_key_present"],
        "arm_request_count": status["arm_request_count"],
        "execute_request_count": status["execute_request_count"],
        "total_driver_call_count": status["total_driver_call_count"],
        "report_terminal_state": responses["report"]["terminal_state"],
        "report_driver_called": responses["report"]["driver_called"],
        "zero_arm_execute_driver_proven": True,
    }


def _reserve(path: Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SalvageError(f"refusing to overwrite {path}") from exc


def _seal(descriptor: int, value: Mapping[str, Any]) -> None:
    body = dict(value)
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha256(_canonical(body)),
    }
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def collect(
    base_url: str,
    *,
    claim: Path = DEFAULT_CLAIM,
    output: Path = DEFAULT_OUTPUT,
    timeout: float = 10.0,
    requester: Requester = _direct_get,
) -> dict[str, Any]:
    """Issue exactly four GETs and seal their lossless response bodies."""

    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not (0.1 <= float(timeout) <= 30.0)
    ):
        raise SalvageError("timeout must be in 0.1..30 seconds")
    origin = _strict_origin(base_url)
    claim_evidence = _read_existing_claim(Path(claim))
    descriptor = _reserve(Path(output))
    transcript: list[dict[str, Any]] = []
    responses: dict[str, Mapping[str, Any]] = {}
    started_at = _now()
    try:
        for ordinal, name in enumerate(ENDPOINT_NAMES, start=1):
            path = ENDPOINTS[name]
            status, headers, raw, effective_url = requester(
                origin, path, float(timeout)
            )
            expected_url = f"{origin}{path}"
            if effective_url != expected_url:
                raise SalvageError(f"GET {name} effective URL differs")
            record, value = _response_record(
                ordinal=ordinal,
                name=name,
                path=path,
                status=status,
                headers=headers,
                raw=raw,
                effective_url=effective_url,
            )
            transcript.append(record)
            responses[name] = value
        validated = _validate_four(responses, origin)
        result: dict[str, Any] = {
            "schema_version": 1,
            "kind": "mf1750-raw-p16-pre-white-v1-read-only-four-get-salvage",
            "outcome": "validated_zero_arm_execute_driver",
            "started_at": started_at,
            "finished_at": _now(),
            "target": {
                "origin": origin,
                "literal_rfc1918_ipv4": True,
                "port": 80,
            },
            "transport": {
                "direct_no_proxy": True,
                "redirect_follow": False,
                "methods": ["GET"],
            },
            "network": {"get": 4, "post": 0},
            "mutation": {
                "claim_created": 0,
                "arm_requested": 0,
                "execute_requested": 0,
                "visible_refresh_requested": 0,
            },
            "existing_claim": claim_evidence,
            "transcript": transcript,
            "validated_state": validated,
            "disposition": {
                "v1_host_claim_remains_permanently_consumed": True,
                "v1_action_retry_allowed": False,
                "fresh_successor_identity_required": True,
            },
            "output_write_contract": "O_EXCL",
        }
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "kind": "mf1750-raw-p16-pre-white-v1-read-only-four-get-salvage",
            "outcome": "read_only_salvage_failed",
            "started_at": started_at,
            "finished_at": _now(),
            "target": {"origin": origin},
            "network": {"get": len(transcript), "post": 0},
            "mutation": {"claim_created": 0, "visible_refresh_requested": 0},
            "existing_claim": claim_evidence,
            "transcript": transcript,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "output_write_contract": "O_EXCL",
        }
        _seal(descriptor, failure)
        if isinstance(exc, SalvageError):
            raise
        raise SalvageError("unexpected read-only salvage failure") from exc
    _seal(descriptor, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--claim", type=Path, default=DEFAULT_CLAIM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect(
            args.base_url,
            claim=args.claim,
            output=args.output,
            timeout=args.timeout,
        )
    except SalvageError as exc:
        print(f"read-only salvage error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
