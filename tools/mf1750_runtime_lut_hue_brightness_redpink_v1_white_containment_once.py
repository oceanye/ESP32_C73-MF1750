#!/usr/bin/env python3
"""Red/pink-brightness factory-OTP white containment host.

The read-only ``diagnose-j2-off`` command performs exactly four direct GETs
and creates no permanent claim. The one-shot ``run`` command performs the same
fresh-state preflight with J2 ON, creates its permanent O_EXCL claim only after
all four GETs pass, and then issues exactly one ARM and one EXECUTE.

This host never flashes, resets, controls power, uses a proxy, retries a
mutation, recovers, autochains, or skips a brightness-campaign ordinal.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_pack as pack,
)


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
)
MATURE_HOST_BYTES = 19_019
MATURE_HOST_SHA256 = "b54e4a40ec1b4be4a01b4e4be80d367336cba7cdf859e0366fcf94534545ff0d"
if (
    not _BASE_PATH.is_file()
    or _BASE_PATH.is_symlink()
    or _BASE_PATH.stat().st_size != MATURE_HOST_BYTES
    or hashlib.sha256(_BASE_PATH.read_bytes()).hexdigest() != MATURE_HOST_SHA256
):
    raise ImportError("reviewed mature containment host identity differs")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_hue_brightness_redpink_white_containment_private_host", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load one-shot containment mechanics: {_BASE_PATH}")
_base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_base)

# Rebind a private copy only. This reuses the exact endpoint payload validators
# without mutating the older cross-profile runner's global state.
_base.pack = pack
_base.REPORT = pack.build_report(verify_artifacts=False)
_base.ACTION = _base.REPORT["action"]
_base.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}

ContainmentError = _base.ContainmentError
ContainmentConsumedError = _base.ContainmentConsumedError
BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS = (
    _base.BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS
)
ACTION = _base.ACTION
ENDPOINTS = _base.ENDPOINTS
DEFAULT_CLAIMS = REPO_ROOT / Path(
    ".test-output/hardware/.mf1750_target_hue_redpink_brightness_"
    "white_containment_v1_claims"
)
DEFAULT_OUTPUT = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V1"
)
DIAGNOSTIC_KIND = (
    "mf1750-target-hue-redpink-brightness-v1-white-containment-j2-off-diagnostic"
)
ATTEMPT_KIND = "mf1750-target-hue-redpink-brightness-v1-white-containment-attempt"
MAX_JSON_BYTES = 1024 * 1024

Requester = Callable[..., tuple[int, Mapping[str, Any]]]
_write_new = _base._write_new
_BASE_IDENTITY = _base._identity


SOURCE_MAIN_BINDING = {
    "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
    "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
    "source_main_contract_exact_binding": True,
    "source_main_device_enforced_same_boot": True,
    "source_main_direct_exact_post_resume_after_reboot": False,
    "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
    "main_campaign_resume_after_containment": False,
    "containment_terminal_for_source_campaign": True,
    "ordinal4_no_visible_difference_branch": True,
    "source_main_ordinals_5_and_6_forbidden_after_branch": True,
    "relay_off_required_before_containment": True,
}


def _identity(value: Mapping[str, Any], *, running_sha: str) -> None:
    _BASE_IDENTITY(value, running_sha=running_sha)
    for key, wanted in SOURCE_MAIN_BINDING.items():
        if value.get(key) != wanted:
            raise ContainmentError(f"source main binding {key} differs")


_base._identity = _identity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _origin(value: str) -> str:
    """Return an exact private/local literal-IPv4 HTTP origin."""

    if not isinstance(value, str):
        raise ContainmentError("base URL must be a plain HTTP origin")
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ContainmentError("base URL port is invalid") from exc
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ContainmentError("base URL must be an exact plain HTTP origin")
    hostname = parsed.hostname
    try:
        address = ipaddress.ip_address(hostname or "")
    except ValueError as exc:
        raise ContainmentError("base URL must use a literal IPv4 address") from exc
    if address.version != 4 or not (
        address.is_private or address.is_loopback or address.is_link_local
    ):
        raise ContainmentError("base URL must use a local/private IPv4 address")
    authority = str(address) if port is None else f"{address}:{port}"
    return f"http://{authority}"


def _validate_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 0 < float(timeout) <= 30
    ):
        raise ContainmentError("timeout must be in (0,30]")
    return float(timeout)


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _default_requester(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Contact the literal LAN origin directly with proxies disabled."""

    request = urllib_request.Request(
        f"{base_url}{path}",
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
        data=None,
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            status = response.status
            payload = response.read(MAX_JSON_BYTES + 1)
    except urllib_error.HTTPError as exc:
        status = exc.code
        payload = exc.read(MAX_JSON_BYTES + 1)
    except (OSError, urllib_error.URLError) as exc:
        raise ContainmentError(f"direct {method} {path} failed: {exc}") from exc
    if len(payload) > MAX_JSON_BYTES:
        raise ContainmentError(f"direct {method} {path} response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContainmentError(
            f"direct {method} {path} response is not UTF-8 JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise ContainmentError(f"direct {method} {path} response root is not an object")
    return status, value


def _request(
    requester: Requester,
    transcript: list[dict[str, Any]],
    base_url: str,
    name: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
    expected_status: int,
) -> Mapping[str, Any]:
    entry: dict[str, Any] = {
        "method": method,
        "endpoint": name,
        "path": ENDPOINTS[name],
        "headers": dict(sorted((headers or {}).items())),
    }
    transcript.append(entry)
    try:
        response = requester(
            base_url,
            ENDPOINTS[name],
            method=method,
            headers=headers,
            timeout=timeout,
        )
    except Exception as exc:
        entry["transport_error"] = f"{type(exc).__name__}: {exc}"
        raise ContainmentError(f"{method} {name} failed: {exc}") from exc
    if not isinstance(response, tuple) or len(response) != 2:
        entry["response_error"] = "requester did not return a (status, object) tuple"
        raise ContainmentError(f"{method} {name} returned malformed data")
    status, value = response
    entry["status"] = status
    if isinstance(value, Mapping):
        entry["body"] = deepcopy(dict(value))
    else:
        entry["response_error"] = f"root type is {type(value).__name__}"
    if isinstance(status, bool) or not isinstance(status, int):
        raise ContainmentError(f"{method} {name} returned malformed status")
    if not isinstance(value, Mapping):
        raise ContainmentError(f"{method} {name} response root is not an object")
    if status != expected_status:
        raise ContainmentError(f"{method} {name} returned HTTP {status}")
    return value


def _validate_version(value: Mapping[str, Any]) -> str:
    running_sha = _base._validate_version(value)
    if running_sha != pack.FIRMWARE_ELF_SHA256:
        raise ContainmentError(
            "running app ELF differs from the bound Red/pink artifact"
        )
    return running_sha


def _validate_fresh_status(
    value: Mapping[str, Any], running_sha: str, *, expected_busy: int
) -> str:
    _base._identity(value, running_sha=running_sha)
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or _base.NONCE.fullmatch(nonce) is None:
        raise ContainmentError("fresh status boot nonce is malformed")
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 1,
        "next_ordinal": 1,
        "campaign_complete": False,
        "cursor_valid": True,
        "persistent_key_present": False,
        "fixture_self_check_passed": True,
        "execute_pending": False,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
        "gpio_initialized": True,
        "busy": expected_busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise ContainmentError(f"fresh status {key} differs")
    return nonce


def _preflight(
    requester: Requester,
    transcript: list[dict[str, Any]],
    base_url: str,
    *,
    expected_busy: int,
    timeout: float,
    progress: dict[str, str],
) -> tuple[str, str, Mapping[str, Any]]:
    """Collect four GETs, then validate exact identity and untouched NVS state."""

    observed: dict[str, Mapping[str, Any]] = {}
    for name in ("version", "manifest", "status", "report"):
        progress["stage"] = f"preflight_get_{name}"
        observed[name] = _request(
            requester,
            transcript,
            base_url,
            name,
            method="GET",
            headers=None,
            timeout=timeout,
            expected_status=200,
        )
    progress["stage"] = "preflight_validate_exact_identity"
    running_sha = _validate_version(observed["version"])
    _base._validate_manifest(observed["manifest"], running_sha)
    progress["stage"] = "preflight_validate_fresh_status"
    boot_nonce = _validate_fresh_status(
        observed["status"], running_sha, expected_busy=expected_busy
    )
    progress["stage"] = "preflight_validate_not_executed_report"
    _base._validate_fresh_report(observed["report"], running_sha)
    return running_sha, boot_nonce, observed["report"]


def _claim_path(claims: Path) -> Path:
    return Path(claims) / f"{pack.ACTION_ID}.json"


def _create_claim(
    claims: Path, *, boot_nonce: str, running_sha: str, preflight_get_count: int
) -> Path:
    """Create the permanent claim after preflight and immediately before ARM."""

    if preflight_get_count != 4:
        raise ContainmentError("permanent claim requires exactly four preflight GETs")
    if running_sha != pack.FIRMWARE_ELF_SHA256:
        raise ContainmentError("permanent claim requires the exact bound Red/pink ELF")
    if not isinstance(boot_nonce, str) or _base.NONCE.fullmatch(boot_nonce) is None:
        raise ContainmentError("permanent claim boot nonce is malformed")
    claim = _claim_path(Path(claims))
    value = {
        "schema_version": 1,
        "kind": pack.CLAIM_KIND,
        **SOURCE_MAIN_BINDING,
        "created_at": _now(),
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "running_app_elf_sha256": running_sha,
        "boot_nonce": boot_nonce,
        "action": ACTION,
        "preflight": {
            "transport": "direct_no_proxy",
            "get": 4,
            "post": 0,
            "busy": 1,
            "fresh_nvs": True,
            "report_terminal_state": "NOT_EXECUTED",
        },
        "state": "permanently_claimed_after_j2_on_preflight_before_first_arm",
        "write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    try:
        _write_new(claim, value)
    except FileExistsError as exc:
        raise ContainmentConsumedError(
            "containment action is permanently claimed; retry is forbidden"
        ) from exc
    return claim


def _network_counts(transcript: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "get": sum(item.get("method") == "GET" for item in transcript),
        "post": sum(item.get("method") == "POST" for item in transcript),
    }


def _attempt_evidence(
    *,
    outcome: str,
    stage: str,
    error: BaseException,
    transcript: Sequence[Mapping[str, Any]],
    claim_file: Path | None,
    claim_state: str,
    running_sha: str | None,
    boot_nonce: str | None,
) -> dict[str, Any]:
    post_count = sum(item.get("method") == "POST" for item in transcript)
    return {
        "schema_version": 1,
        "kind": ATTEMPT_KIND,
        **SOURCE_MAIN_BINDING,
        "created_at": _now(),
        "outcome": outcome,
        "stage": stage,
        "error": {"type": type(error).__name__, "message": str(error)},
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "running_app_elf_sha256": running_sha,
        "boot_nonce": boot_nonce,
        "action": ACTION,
        "claim_file": None if claim_file is None else str(claim_file.resolve()),
        "claim_state": claim_state,
        "permanent_claims_created_by_this_invocation": int(
            claim_state == "permanently_consumed_by_this_invocation"
        ),
        "network": _network_counts(transcript),
        "transcript": deepcopy(list(transcript)),
        "visible_refreshes_confirmed": 0,
        "visible_refresh_may_have_occurred": post_count >= 2,
        "output_write_contract": "O_EXCL",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }


def _write_attempt_best_effort(output: Path, evidence: Mapping[str, Any]) -> str | None:
    try:
        _write_new(output, evidence)
    except Exception as exc:  # The original containment failure remains primary.
        return f"{type(exc).__name__}: {exc}"
    return None


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = _default_requester,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Seal a four-GET, zero-POST, zero-claim fresh-state J2-OFF check."""

    if confirm_j2_off is not True:
        raise ContainmentError("diagnose-j2-off requires explicit J2-OFF confirmation")
    pack.build_report(verify_artifacts=True)
    origin = _origin(base_url)
    checked_timeout = _validate_timeout(timeout)
    output = Path(output)
    if output.exists():
        raise ContainmentError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    transcript: list[dict[str, Any]] = []
    progress = {"stage": "diagnostic_start"}
    running_sha: str | None = None
    boot_nonce: str | None = None
    try:
        running_sha, boot_nonce, report = _preflight(
            requester,
            transcript,
            origin,
            expected_busy=0,
            timeout=checked_timeout,
            progress=progress,
        )
        evidence = {
            "schema_version": 1,
            "kind": DIAGNOSTIC_KIND,
            **SOURCE_MAIN_BINDING,
            "created_at": _now(),
            "outcome": "j2_off_diagnostic_pass",
            "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
            "running_app_elf_sha256": running_sha,
            "boot_nonce": boot_nonce,
            "action": ACTION,
            "j2_confirmed_off": True,
            "fresh_nvs": True,
            "busy": 0,
            "report_terminal_state": "NOT_EXECUTED",
            "report": deepcopy(dict(report)),
            "permanent_claims_created": 0,
            "network": {"get": 4, "post": 0},
            "transcript": transcript,
            "visible_refreshes": 0,
            "output_write_contract": "O_EXCL",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "no_ordinal_skip": True,
        }
        progress["stage"] = "diagnostic_evidence_create"
        _write_new(output, evidence)
        return evidence
    except Exception as exc:
        attempt = _attempt_evidence(
            outcome="j2_off_diagnostic_failed_no_claim",
            stage=progress["stage"],
            error=exc,
            transcript=transcript,
            claim_file=None,
            claim_state="not_created",
            running_sha=running_sha,
            boot_nonce=boot_nonce,
        )
        attempt["kind"] = f"{DIAGNOSTIC_KIND}-attempt"
        attempt["permanent_claims_created"] = 0
        write_error = None
        if not output.exists():
            write_error = _write_attempt_best_effort(output, attempt)
        detail = (
            f"; attempt evidence write failed: {write_error}" if write_error else ""
        )
        raise ContainmentError(f"J2-OFF diagnostic failed: {exc}{detail}") from exc


def _headers(
    boot_nonce: str, intent: str, arm_nonce: str | None = None
) -> dict[str, str]:
    return _base._headers(boot_nonce, intent, arm_nonce)


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    requester: Requester = _default_requester,
    timeout: float = 10.0,
    poll_seconds: float = BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS,
    poll_count: int = 20,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Consume the exact Red/pink white action once; any post-claim doubt is final."""

    pack.build_report(verify_artifacts=True)
    origin = _origin(base_url)
    checked_timeout = _validate_timeout(timeout)
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise ContainmentError("poll_count must be a positive integer")
    if (
        isinstance(poll_seconds, bool)
        or not isinstance(poll_seconds, (int, float))
        or not math.isfinite(float(poll_seconds))
        or not BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS <= float(poll_seconds) <= 300
    ):
        raise ContainmentError("poll_seconds must be in 65..300")

    output = Path(output)
    claims = Path(claims)
    claim_target = _claim_path(claims)
    if output.resolve() == claim_target.resolve():
        raise ContainmentError("output and permanent claim paths must differ")
    if output.exists():
        raise ContainmentError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    claims.mkdir(parents=True, exist_ok=True)

    transcript: list[dict[str, Any]] = []
    progress = {"stage": "preclaim_checks"}
    running_sha: str | None = None
    boot_nonce: str | None = None
    claim: Path | None = None
    claim_preexisted = claim_target.exists()
    try:
        if claim_preexisted:
            raise ContainmentConsumedError(
                "containment action is permanently claimed; retry is forbidden"
            )

        running_sha, boot_nonce, _ = _preflight(
            requester,
            transcript,
            origin,
            expected_busy=1,
            timeout=checked_timeout,
            progress=progress,
        )

        # Prepare the immutable ARM request entirely before claiming. The claim
        # creation below is therefore the final operation before the first ARM.
        arm_headers = _headers(boot_nonce, pack.ARM_INTENT)
        progress["stage"] = "permanent_claim_create_before_first_arm"
        claim = _create_claim(
            claims,
            boot_nonce=boot_nonce,
            running_sha=running_sha,
            preflight_get_count=_network_counts(transcript)["get"],
        )

        progress["stage"] = "arm_post"
        arm = _request(
            requester,
            transcript,
            origin,
            "arm",
            method="POST",
            headers=arm_headers,
            timeout=checked_timeout,
            expected_status=201,
        )
        arm_nonce = arm.get("arm_nonce")
        _base._identity(arm, running_sha=running_sha)
        if (
            arm.get("accepted") is not True
            or arm.get("armed") is not True
            or arm.get("ordinal") != 1
            or arm.get("action_id") != pack.ACTION_ID
            or arm.get("boot_nonce") != boot_nonce
            or not isinstance(arm_nonce, str)
            or _base.NONCE.fullmatch(arm_nonce) is None
        ):
            raise ContainmentConsumedError(
                "ARM response differs; permanent claim remains; retry is forbidden"
            )

        execute_headers = _headers(boot_nonce, pack.EXECUTE_INTENT, arm_nonce)
        progress["stage"] = "execute_post"
        execute = _request(
            requester,
            transcript,
            origin,
            "execute",
            method="POST",
            headers=execute_headers,
            timeout=checked_timeout,
            expected_status=202,
        )
        _base._identity(execute, running_sha=running_sha)
        if (
            execute.get("accepted") is not True
            or execute.get("job_id") != 1
            or execute.get("action_id") != pack.ACTION_ID
            or execute.get("execute_consumed") is not True
            or execute.get("no_retry") is not True
        ):
            raise ContainmentConsumedError(
                "EXECUTE response differs; permanent claim remains; retry is forbidden"
            )

        terminal: Mapping[str, Any] | None = None
        for index in range(poll_count):
            progress["stage"] = f"terminal_wait_{index + 1}"
            sleeper(float(poll_seconds))
            progress["stage"] = f"terminal_report_get_{index + 1}"
            observed = _request(
                requester,
                transcript,
                origin,
                "report",
                method="GET",
                headers=None,
                timeout=checked_timeout,
                expected_status=200,
            )
            state = observed.get("terminal_state")
            if state == "COMPLETE":
                _base._validate_complete(observed, running_sha)
                terminal = observed
                break
            if state == "FAULT":
                raise ContainmentConsumedError(
                    "device reported FAULT; permanent claim remains; retry is forbidden"
                )
        if terminal is None:
            raise ContainmentConsumedError(
                "terminal report was not observed; permanent claim remains; retry is forbidden"
            )

        result = {
            "schema_version": 1,
            "kind": pack.RESULT_KIND,
            **SOURCE_MAIN_BINDING,
            "created_at": _now(),
            "outcome": "complete_pass",
            "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
            "running_app_elf_sha256": running_sha,
            "claim_file": str(claim.resolve()),
            "claim_state": "permanently_consumed_by_this_invocation",
            "claim_timing": "after_four_get_j2_on_preflight_before_first_arm",
            "boot_nonce": boot_nonce,
            "action": ACTION,
            "visible_refreshes": 1,
            "network": _network_counts(transcript),
            "transcript": transcript,
            "terminal_report": terminal,
            "output_write_contract": "O_EXCL",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "no_ordinal_skip": True,
        }
        progress["stage"] = "complete_result_create"
        _write_new(output, result)
        return result
    except Exception as exc:
        claim_present = claim is not None or claim_target.exists()
        if claim is not None:
            claim_state = "permanently_consumed_by_this_invocation"
            outcome = "claimed_attempt_failed_do_not_retry"
            evidence_claim = claim
        elif claim_present:
            claim_state = "preexisting_concurrent_or_uncertain_permanent_claim"
            outcome = "blocked_by_permanent_claim_do_not_retry"
            evidence_claim = claim_target
        else:
            claim_state = "not_created"
            outcome = "preflight_failed_no_claim"
            evidence_claim = None
        attempt = _attempt_evidence(
            outcome=outcome,
            stage=progress["stage"],
            error=exc,
            transcript=transcript,
            claim_file=evidence_claim,
            claim_state=claim_state,
            running_sha=running_sha,
            boot_nonce=boot_nonce,
        )
        write_error = None
        if not output.exists():
            write_error = _write_attempt_best_effort(output, attempt)
        detail = (
            f"; attempt evidence write failed: {write_error}" if write_error else ""
        )
        if claim_present or claim_preexisted:
            raise ContainmentConsumedError(
                f"{exc}; permanent claim forbids retry{detail}"
            ) from exc
        raise ContainmentError(f"containment preflight failed: {exc}{detail}") from exc


def describe() -> dict[str, Any]:
    value = pack.build_report(verify_artifacts=False)
    return {
        **value,
        "purpose": (
            "redpink_brightness_independent_fresh_factory_otp_white_fault_containment"
        ),
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "ordinal4_no_visible_difference_branch": True,
        "source_main_ordinals_5_and_6_forbidden_after_branch": True,
        "relay_off_required_before_containment": True,
        "independent_nvs_and_claims": True,
        "mature_host_binding": {
            "bytes": MATURE_HOST_BYTES,
            "sha256": MATURE_HOST_SHA256,
            "verified_before_import": True,
        },
        "transport": {
            "mode": "direct_literal_private_ipv4_http",
            "proxy": False,
            "redirect": False,
        },
        "diagnose_j2_off": {
            "read_only": True,
            "busy": 0,
            "network": {"get": 4, "post": 0},
            "permanent_claims_created": 0,
            "fresh_nvs_required": True,
            "report_terminal_state": "NOT_EXECUTED",
            "output_write_contract": "O_EXCL",
        },
        "run": {
            "j2_on_preflight_busy": 1,
            "preflight_network": {"get": 4, "post": 0},
            "claim_timing": "after_four_get_j2_on_preflight_before_first_arm",
            "mutation_network": {"arm_post_max": 1, "execute_post_max": 1},
            "failure_evidence_best_effort": True,
            "failure_evidence_write_contract": "O_EXCL",
        },
        "firmware_busy_gates": ["ARM", "EXECUTE", "DISPATCH"],
        "blocking_refresh_first_poll_floor_seconds": (
            BLOCKING_REFRESH_FIRST_POLL_FLOOR_SECONDS
        ),
        "network_requests": 0,
        "visible_refreshes": 0,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "ordinal_skip": False,
    }


def dry_validate() -> dict[str, Any]:
    """Verify artifacts, source-main binding, and host identity without I/O."""

    report = pack.build_report(verify_artifacts=True)
    if report["source_main_binding"] != {
        "expected_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "observed_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "exact": True,
        "device_enforced_same_boot": True,
        "direct_exact_post_resume_after_reboot": False,
        "nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
        "resume_allowed_after_containment": False,
        "ordinal4_no_visible_difference_branch": True,
        "source_main_ordinals_5_and_6_forbidden_after_branch": True,
        "relay_off_required_before_containment": True,
    }:
        raise ContainmentError("source main contract dry binding differs")
    return {
        "kind": "mf1750-target-hue-redpink-brightness-v1-white-containment-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "visible_refreshes": 0,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        **SOURCE_MAIN_BINDING,
        "containment_contract_id": pack.CONTRACT_ID,
        "action_id": pack.ACTION_ID,
        "artifact_binding_status": report["artifact_binding_status"],
        "mature_host_binding": {
            "bytes": MATURE_HOST_BYTES,
            "sha256": MATURE_HOST_SHA256,
            "verified_before_import": True,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "describe",
        help="verify artifacts and print the offline Red/pink host contract",
    )
    sub.add_parser(
        "dry-validate",
        help="verify all local bindings without network or visible refresh",
    )
    diagnostic = sub.add_parser(
        "diagnose-j2-off",
        help="perform exactly four direct GETs, zero POSTs, and zero claims",
        allow_abbrev=False,
    )
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, required=True)
    diagnostic.add_argument("--timeout", type=float, default=10.0)
    run = sub.add_parser(
        "run",
        help="preflight J2 ON, permanently claim, ARM once, and EXECUTE once",
        allow_abbrev=False,
    )
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
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
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except ContainmentError as exc:
        print(f"Red/pink factory-OTP containment error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
