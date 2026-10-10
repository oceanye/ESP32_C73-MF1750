#!/usr/bin/env python3
"""One-shot successor host for the RAW-P16 pre-gallery OTP-white anchor.

The transport is deliberately direct: environment/system proxies are disabled
and HTTP redirects are rejected.  The bound BIN/ELF are verified before the
permanent claim file can be created or any device request can be attempted.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1b_pack as pack,
)

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_raw_p16_pre_white_anchor_v1b_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load successor pre-white anchor host: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

base.pack = pack
base.REPORT = pack.build_report(verify_artifacts=False)
base.ACTION = base.REPORT["action"]
base.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.DEFAULT_CLAIMS = REPO_ROOT / (
    ".test-output/hardware/.mf1750_raw_p16_pre_white_anchor_v1b_claims"
)
base.DEFAULT_OUTPUT = REPO_ROOT / (
    ".test-output/hardware/MF1750_RAW_P16_PRE_WHITE_ANCHOR_20260828_V1B"
)


class _RejectRedirects(urllib_request.HTTPRedirectHandler):
    """Make every 3xx response terminal; never translate it into another request."""

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


_NO_PROXY_HANDLER = urllib_request.ProxyHandler({})
_DIRECT_OPENER = urllib_request.build_opener(
    _NO_PROXY_HANDLER,
    _RejectRedirects(),
)


def _validate_direct_origin(base_url: str) -> str:
    """Accept only a direct HTTP origin on a local IPv4 literal and port 80."""

    try:
        parsed = urllib_parse.urlsplit(base_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise base.ContainmentError("device origin is malformed") from exc
    if parsed.scheme != "http":
        raise base.ContainmentError("device origin scheme must be http")
    if parsed.username is not None or parsed.password is not None:
        raise base.ContainmentError("device origin userinfo is forbidden")
    if parsed.hostname is None:
        raise base.ContainmentError("device origin hostname is absent")
    try:
        address = ipaddress.IPv4Address(parsed.hostname)
    except ipaddress.AddressValueError as exc:
        raise base.ContainmentError(
            "device origin must use an IPv4 literal; hostnames are forbidden"
        ) from exc
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise base.ContainmentError("device origin must be local, never public")
    if port not in (None, 80):
        raise base.ContainmentError("device origin port must be 80")
    if parsed.path not in ("", "/"):
        raise base.ContainmentError("device origin path is forbidden")
    if parsed.query:
        raise base.ContainmentError("device origin query is forbidden")
    if parsed.fragment:
        raise base.ContainmentError("device origin fragment is forbidden")
    authority = str(address) if port is None else f"{address}:80"
    return f"http://{authority}"


def _direct_requester(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    request = urllib_request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers=dict(headers or {}),
        data=None,
    )
    try:
        with _DIRECT_OPENER.open(request, timeout=timeout) as response:
            status = response.status
            payload = response.read()
    except urllib_error.HTTPError as exc:
        status = exc.code
        payload = exc.read()
    except urllib_error.URLError as exc:
        raise base.ContainmentConsumedError(
            "direct no-proxy device request failed; retry is forbidden"
        ) from exc
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise base.ContainmentConsumedError(
            "direct device response is not UTF-8 JSON; retry is forbidden"
        ) from exc
    if not isinstance(value, Mapping):
        raise base.ContainmentConsumedError(
            "direct device response root is not an object; retry is forbidden"
        )
    return status, value


_base_run_once = base.run_once
_base_describe = base.describe


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    requester: Any = _direct_requester,
    timeout: float = 10.0,
    poll_seconds: float = base.BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    poll_count: int = 20,
    sleeper: Any = None,
) -> dict[str, Any]:
    """Verify local artifacts first, then delegate the one-shot state machine."""

    # This call must remain before _base_run_once: it precedes both _create_claim
    # and the first requester call in the delegated implementation.
    pack.build_report(verify_artifacts=True)
    direct_origin = _validate_direct_origin(base_url)
    kwargs: dict[str, Any] = {
        "claims": claims,
        "output": output,
        "requester": requester,
        "timeout": timeout,
        "poll_seconds": poll_seconds,
        "poll_count": poll_count,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    return _base_run_once(direct_origin, **kwargs)


def describe() -> dict[str, object]:
    value = _base_describe()
    value["purpose"] = pack.PURPOSE
    value["target_campaign_id"] = pack.TARGET_CAMPAIGN_ID
    value["transport"] = {
        "proxy_use": False,
        "redirect_follow": False,
        "direct_http_only": True,
        "origin_policy": (
            "HTTP_LOCAL_IPV4_LITERAL_PORT_80_NO_USERINFO_PATH_QUERY_FRAGMENT"
        ),
    }
    value["artifact_validation_before_claim"] = True
    return value


base.run_once = run_once
base.describe = describe


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["dry-validate"]:
        pack.build_report(verify_artifacts=True)
        value = describe()
        value["dry_validation"] = "PASS"
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0
    return base.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
