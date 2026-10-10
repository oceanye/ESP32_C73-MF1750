#!/usr/bin/env python3
"""Fail-closed one-action runner for the isolated OTP matrix recheck.

This tool never flashes the ESP32 and never chains visible actions.  It offers
one read-only J2-OFF diagnostic and one permanently claimed ARM/EXECUTE action
per invocation.  Primer, Target, and White therefore remain three separate
operator decisions.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.parse
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BUILD_TAG = "MF1750_EC5_OTP_TRANSITION_MATRIX_RECHECK_V1_2026-08-20"
TEST_ID = "EC5-OTP-TRANSITION-MATRIX-RECHECK-V1"
CAMPAIGN_ID = "EC5_OTP_TRANSITION_MATRIX_RECHECK_CAMPAIGN_V1"
DEVICE_API_VERSION = "MF1750_EC5_OTP_TRANSITION_MATRIX_RECHECK_DEVICE_V1"
IDENTITY_REVISION = "otp-transition-matrix-recheck-v1"
CONTRACT_ID = "19aa55ae2fbb1e4343a877155034a2a5a2829dac361439ff90e4aab982b8e8b5"
CLASSIFICATION = "FACTORY_OTP_8X8_TRANSITION_EXPERIMENT_NO_RUNTIME_LUT"
DEVICE_KIND_PREFIX = "mf1750-ec5-otp-transition-matrix"
EVIDENCE_KIND_PREFIX = "mf1750-ec5-otp-transition-matrix-recheck"
NVS_NAMESPACE = "mf1750_otpm8r2"
NVS_KEY = "cursor_v1"
FIRMWARE_SHA256 = "3710ab8460ed42bfba4790e0ff94c9a161386bb404cb552ae2cb5533b94aff13"
FIRMWARE_BYTES = 787856

ENDPOINTS = {
    name: f"/api/ec5/otp-transition-matrix-recheck/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_TRANSITION_MATRIX_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_FACTORY_OTP_TRANSITION_MATRIX_ACTION_ONCE"
DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_otp_transition_matrix_recheck_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_OTP_TRANSITION_MATRIX_RECHECK_20260820_V1"
)

DESCRIPTOR_IDS = (
    "21d96bae9d994271a7916005b173d74b2113049d3ec7a8832655333105df8a9e",
    "fcb96838b86404b766a27989b0f6cf7465a77b28ba2cdb262fa1a609e5eada5a",
    "dcfcea2c8ab503fc2808f4c366e439bc216a189a0697d2f9d71b20108ba65f4f",
)
ACTION_IDS = (
    "ce50ab9d61546a4262280904519644ec9d0a597955a95540a2db7d53f3d9a6a0",
    "306ef1c31617bf642c26e083551d471917fccf41439a4e2ca3a4950f1bcab973",
    "a30c620068d317d2ddd84aa64b113bc363b727b48da5b3f96ec89310b1c5de6c",
)
ACTIONS = (
    {
        "ordinal": 1,
        "descriptor_id": DESCRIPTOR_IDS[0],
        "action_id": ACTION_IDS[0],
        "prior_static_action_id": None,
        "role": "OTP_8X8_TRANSITION_PRIMER",
        "round": 1,
        "branch": "FACTORY_OTP_8X8_OLD_STATE_PRIMER",
        "frame_sha256": "01529ea97197e5435370a0eb77a9cabff167c129237952b7a627a0f4903744dc",
        "cs1_dtm_sha256": "208c3d8e03329bbba08bb54cb5f84a9568349295ed750c749aad0e29f259017f",
        "cs2_dtm_sha256": "d66c999e89ace23dd3a112c53e9ca1f7bbbc984772e08af4359dcd843740cb1c",
    },
    {
        "ordinal": 2,
        "descriptor_id": DESCRIPTOR_IDS[1],
        "action_id": ACTION_IDS[1],
        "prior_static_action_id": ACTION_IDS[0],
        "role": "OTP_8X8_TRANSITION_TARGET",
        "round": 1,
        "branch": "FACTORY_OTP_8X8_OLD_TO_NEW_TARGET",
        "frame_sha256": "e3f476f24176e4b5d0f196e6c3d912dabf5044f2cbac0a59bf63806d8d051a38",
        "cs1_dtm_sha256": "4a980b33107b1d0c1da6282952d5adf8c32334af46be8f2e82aceb4c30a94387",
        "cs2_dtm_sha256": "70d4f642ec98bb034de65fb350d51285e7f644dd42c5aa3e89de5b607f4643c3",
    },
    {
        "ordinal": 3,
        "descriptor_id": DESCRIPTOR_IDS[2],
        "action_id": ACTION_IDS[2],
        "prior_static_action_id": ACTION_IDS[1],
        "role": "OTP_WHITE_RECOVERY",
        "round": 1,
        "branch": "FACTORY_OTP_WHITE_RECOVERY",
        "frame_sha256": "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "cs1_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "cs2_dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    },
)

Requester = Callable[..., tuple[int, Mapping[str, Any]]]
_NONCE = re.compile(r"^[0-9a-f]{16}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024


class RecheckError(RuntimeError):
    """A fixed identity, state, or one-shot boundary differed."""


def _http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Contact the selected LAN origin directly, never through host proxies."""

    request = urllib.request.Request(
        base_url + path,
        headers=dict(headers or {}),
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.getcode()
            payload = response.read(_MAX_JSON_BYTES + 1)
    except Exception as error:
        raise RecheckError(f"{method} {path} failed: {error}") from error
    if len(payload) > _MAX_JSON_BYTES:
        raise RecheckError(f"{method} {path} response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecheckError(f"{method} {path} response is not JSON") from error
    if not isinstance(value, Mapping):
        raise RecheckError(f"{method} {path} response root is not an object")
    return status, value


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(value))
    root["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(root)).hexdigest(),
    }
    return root


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise RecheckError(f"refusing to overwrite {path}") from error


def _origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise RecheckError("base URL must be a plain HTTP origin")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _request(
    requester: Requester,
    transcript: list[dict[str, Any]],
    base_url: str,
    endpoint: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: float = 12.0,
) -> Mapping[str, Any]:
    try:
        status, value = requester(
            base_url,
            ENDPOINTS[endpoint],
            method=method,
            headers=headers,
            timeout=timeout,
        )
    except Exception as error:
        raise RecheckError(f"{method} {endpoint} failed: {error}") from error
    if not isinstance(status, int) or not isinstance(value, Mapping):
        raise RecheckError(f"{method} {endpoint} returned malformed data")
    transcript.append(
        {
            "method": method,
            "endpoint": endpoint,
            "path": ENDPOINTS[endpoint],
            "headers": dict(sorted((headers or {}).items())),
            "status": status,
            "response": deepcopy(dict(value)),
        }
    )
    if not 200 <= status < 300:
        raise RecheckError(f"{method} {endpoint} returned HTTP {status}")
    return value


def _identity(value: Mapping[str, Any], *, kind_suffix: str) -> None:
    exact = {
        "kind": f"{DEVICE_KIND_PREFIX}-{kind_suffix}",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "contract_id": CONTRACT_ID,
        "classification": CLASSIFICATION,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise RecheckError(f"device {kind_suffix} {key} differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _identity(value, kind_suffix="version")
    expected_false = (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "runtime_lut_write",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    )
    if value.get("action_count") != len(ACTIONS) or any(
        value.get(key) is not False for key in expected_false
    ):
        raise RecheckError("device version safety contract differs")
    nvs = value.get("nvs_contract", {})
    if nvs.get("namespace") != NVS_NAMESPACE or nvs.get("key") != NVS_KEY:
        raise RecheckError("device NVS isolation differs")


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _identity(value, kind_suffix="manifest")
    if value.get("actions") != list(ACTIONS):
        raise RecheckError("device fixed action manifest differs")
    if (
        value.get("action_count") != len(ACTIONS)
        or value.get("one_driver_call_per_action") is not True
    ):
        raise RecheckError("device manifest action contract differs")


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    _identity(value, kind_suffix="status")
    terminal_ordinal = len(ACTIONS) + 1
    expected_state = "complete" if ordinal == terminal_ordinal else "ready"
    exact = {
        "state": expected_state,
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": ordinal,
        "next_ordinal": ordinal,
        "current_action": None,
        "campaign_complete": ordinal == terminal_ordinal,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "busy": expected_busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "execute_pending": False,
        "persistent_key_present": ordinal != 1,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise RecheckError(f"device ready status {key} differs")
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        raise RecheckError("device boot nonce is malformed")
    return nonce


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Requester,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    transcript: list[dict[str, Any]] = []
    version = _request(requester, transcript, base_url, "version")
    manifest = _request(requester, transcript, base_url, "manifest")
    status = _request(requester, transcript, base_url, "status")
    report = _request(requester, transcript, base_url, "report")
    _validate_version(version)
    _validate_manifest(manifest)
    boot_nonce = _validate_ready_status(status, ordinal, expected_busy=expected_busy)
    _identity(report, kind_suffix="report")
    if report.get("boot_nonce") != boot_nonce:
        raise RecheckError("device report boot nonce differs")
    return boot_nonce, transcript, report


def describe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": f"{EVIDENCE_KIND_PREFIX}-description",
        "build_tag": BUILD_TAG,
        "campaign_id": CAMPAIGN_ID,
        "firmware": {"bytes": FIRMWARE_BYTES, "sha256": FIRMWARE_SHA256},
        "nvs": {"namespace": NVS_NAMESPACE, "key": NVS_KEY},
        "actions": list(ACTIONS),
        "visible_actions": len(ACTIONS),
        "startup_refresh": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "firmware_flash_performed_by_runner": False,
        "live_authorized": False,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    requester: Requester = _http_request,
) -> dict[str, Any]:
    boot_nonce, transcript, report = _preflight(
        _origin(base_url), 1, expected_busy=0, requester=requester
    )
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": f"{EVIDENCE_KIND_PREFIX}-j2-off-diagnostic",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "visible_refreshes": 0,
        }
    )
    _write_new(output, evidence)
    return evidence


def _headers(action: Mapping[str, Any], boot_nonce: str, intent: str) -> dict[str, str]:
    return {
        "X-EC5-Build-Tag": BUILD_TAG,
        "X-EC5-Test-Id": TEST_ID,
        "X-EC5-Campaign-Id": CAMPAIGN_ID,
        "X-EC5-Action-Id": str(action["action_id"]),
        "X-EC5-Ordinal": str(action["ordinal"]),
        "X-EC5-Descriptor-Id": str(action["descriptor_id"]),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Requester = _http_request,
    poll_seconds: float = 2.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    if ordinal < 1 or ordinal > len(ACTIONS):
        raise RecheckError(f"ordinal must be between 1 and {len(ACTIONS)}")
    action = ACTIONS[ordinal - 1]
    claims = Path(claims)
    claim_file = claims / f"{action['action_id']}.json"
    if claim_file.exists():
        raise RecheckError(f"action {ordinal} was already permanently claimed")
    if ordinal > 1 and not (claims / f"{ACTION_IDS[ordinal - 2]}.json").is_file():
        raise RecheckError(f"action {ordinal} requires the local prior-action claim")

    origin = _origin(base_url)
    boot_nonce, transcript, _ = _preflight(
        origin, ordinal, expected_busy=1, requester=requester
    )
    claim = _seal(
        {
            "schema_version": 1,
            "kind": f"{EVIDENCE_KIND_PREFIX}-permanent-claim",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(action),
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    _write_new(claim_file, claim)

    arm = _request(
        requester,
        transcript,
        origin,
        "arm",
        method="POST",
        headers=_headers(action, boot_nonce, ARM_INTENT),
    )
    arm_nonce = arm.get("arm_nonce")
    if (
        arm.get("accepted") is not True
        or arm.get("armed") is not True
        or arm.get("action_id") != action["action_id"]
        or arm.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or _NONCE.fullmatch(arm_nonce) is None
    ):
        raise RecheckError("ARM response differs; claim remains consumed")

    execute_headers = _headers(action, boot_nonce, EXECUTE_INTENT)
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    execute = _request(
        requester,
        transcript,
        origin,
        "execute",
        method="POST",
        headers=execute_headers,
    )
    if (
        execute.get("accepted") is not True
        or execute.get("execute_consumed") is not True
        or execute.get("action_id") != action["action_id"]
        or execute.get("boot_nonce") != boot_nonce
    ):
        raise RecheckError("EXECUTE response differs; claim remains consumed")

    terminal_report: Mapping[str, Any] | None = None
    for _ in range(poll_count):
        if poll_seconds > 0:
            time.sleep(poll_seconds)
        report = _request(requester, transcript, origin, "report")
        if report.get("terminal_state") in ("COMPLETE", "FAULT"):
            terminal_report = report
            break
    if terminal_report is None:
        raise RecheckError("terminal report not observed; action must not be retried")
    _identity(terminal_report, kind_suffix="report")
    if (
        terminal_report.get("boot_nonce") != boot_nonce
        or terminal_report.get("ordinal") != ordinal
        or terminal_report.get("action_id") != action["action_id"]
        or terminal_report.get("terminal_state") != "COMPLETE"
        or terminal_report.get("result") is not True
        or terminal_report.get("driver_called") is not True
        or terminal_report.get("driver_call_count_for_action") != 1
    ):
        raise RecheckError(
            "terminal report is not a one-call success; claim remains consumed"
        )

    result = _seal(
        {
            "schema_version": 1,
            "kind": f"{EVIDENCE_KIND_PREFIX}-result",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(action),
            "claim_file": str(claim_file.resolve()),
            "terminal_report": deepcopy(dict(terminal_report)),
            "transcript": transcript,
            "network": {
                "get": sum(item["method"] == "GET" for item in transcript),
                "arm_post": 1,
                "execute_post": 1,
            },
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    _write_new(output, result)
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    diagnostic = sub.add_parser("diagnose-j2-off")
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=2.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(args.base_url, output=args.output)
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except RecheckError as error:
        print(f"OTP recheck error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
