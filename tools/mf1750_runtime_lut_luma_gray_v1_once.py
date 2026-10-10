#!/usr/bin/env python3
"""Fail-closed one-action runner for the LUMA-GRAY-V1 exploratory campaign.

The host never flashes, resets, controls power, retries, recovers, or chains
actions.  It consumes one reviewed ordinal only, requires raw BUSY=1, and
accepts one strict COMPLETE result.  Use the independent fresh containment
firmware after action 8 (or after any stopped/failed campaign).
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_luma_gray_v1_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location("_mf1750_luma_gray_v1_host", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed one-action mechanics: {_BASE_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)
v1 = v3.v1
base = v3.base

REPORT = pack.build_report()
v3.pack = pack
v3.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = "MF1750_EC5_LUMA_GRAY_EXPLORATORY_DEVICE_V1"
base.runner.IDENTITY_REVISION = (
    "runtime-lut-luma-gray-two-page-source-anchor-single-app-boot-v1"
)
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_CAMERA_RELATIVE_LUMA_GRAY_CANDIDATES_ZERO_QUALIFIED_GRAY_LEVELS"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-luma-gray-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-luma-gray-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = (
    "fbdbb9e7cca723c8ac2b39992c2b01792cd8bff9888e5d8a10d511602777b9b2"
)
base.runner.FIRMWARE_BYTES = 801_712
ELF_SHA256 = "2df06b6da6070b12e23550eb9b81d68d7fd9b38c33a28b04a859491cd93ad8cc"
ELF_BYTES = 13_296_684
BUILD_DIR = (
    REPO_ROOT / ".pio/build-runtime-lut-luma-gray-v1/ec5_runtime_lut_luma_gray_v1"
)
base.runner.ENDPOINTS = {
    name: f"/api/ec5/luma-gray-v1/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_LUMA_GRAY_V1_EXPLORATORY_ACTION"
base.runner.EXECUTE_INTENT = "EXECUTE_ARMED_LUMA_GRAY_V1_EXPLORATORY_ACTION_ONCE"


def _runner_actions() -> tuple[dict[str, Any], ...]:
    actions = deepcopy(base._actions())
    for action, source in zip(actions, REPORT["actions"], strict=True):
        factory = source["palette_source"] == "FACTORY_OTP"
        ordinal = action["ordinal"]
        action["boot_admission"] = {
            "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
            "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
            if ordinal == 1
            else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY",
            "required_prior_terminal_state": None if ordinal == 1 else "COMPLETE",
            "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
            "firmware_arm_gate": True,
            "firmware_execute_gate": True,
            "firmware_dispatch_gate": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        }
        action["palette_source"] = source["palette_source"]
        action["global_header"] = source["global_header"]
        action["driver_entry"] = (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if factory
            else "epdDisplayCompiledChromaGrid"
        )
    return tuple(actions)


base.runner.ACTIONS = _runner_actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT / ".test-output/hardware/.mf1750_luma_gray_v1_claims"
)
base.runner.DEFAULT_OUTPUT = REPO_ROOT / ".test-output/hardware/MF1750_LUMA_GRAY_V1"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024


def _private_origin(value: str) -> str:
    """Return only an exact private/local literal-IPv4 HTTP origin."""

    if not isinstance(value, str):
        raise base.runner.RecheckError(
            "base URL must be a private/local literal IPv4 HTTP origin"
        )
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise base.runner.RecheckError("base URL port is invalid") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise base.runner.RecheckError("base URL must be an exact plain HTTP origin")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as error:
        raise base.runner.RecheckError(
            "base URL must use a literal IPv4 address"
        ) from error
    allowed = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
    )
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in allowed
    ):
        raise base.runner.RecheckError(
            "base URL must use a private/local literal IPv4 address"
        )
    authority = str(address) if port is None else f"{address}:{port}"
    return f"http://{authority}"


def _request_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 < float(value) <= 30
    ):
        raise base.runner.RecheckError("HTTP timeout must be in (0,30]")
    return float(value)


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


def _direct_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Perform one direct request; never consult proxies or follow redirects."""

    request = urllib_request.Request(
        base_url + path,
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:  # noqa: S310
            status = response.status
            payload = response.read(_MAX_JSON_BYTES + 1)
    except urllib_error.HTTPError as error:
        status = error.code
        payload = error.read(_MAX_JSON_BYTES + 1)
    except (OSError, urllib_error.URLError) as error:
        raise base.runner.RecheckError(
            f"direct {method} {path} failed: {error}"
        ) from error
    if len(payload) > _MAX_JSON_BYTES:
        raise base.runner.RecheckError(f"direct {method} {path} response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(
            f"direct {method} {path} response is not UTF-8 JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(
            f"direct {method} {path} response root is not an object"
        )
    return status, value


def _verify_local_artifacts() -> None:
    for name, size, digest in (
        ("firmware.bin", base.runner.FIRMWARE_BYTES, base.runner.FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        path = BUILD_DIR / name
        if not path.is_file():
            raise base.runner.RecheckError(
                f"reviewed LUMA-GRAY artifact missing: {path}"
            )
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise base.runner.RecheckError(
                f"reviewed LUMA-GRAY artifact differs: {path}"
            )


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    for key in (
        "full_screen_global_refresh",
        "history_brightness_screening",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
        "candidate_only",
        "independent_fresh_white_containment_required",
    ):
        if value.get(key) is not True:
            raise base.runner.RecheckError(f"LUMA-GRAY capability {key} differs")
    for key in (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "local_hold_claimed",
        "true_neutral_gray_claimed",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(
                f"LUMA-GRAY forbidden capability {key} differs"
            )
    if (
        value.get("qualified_gray_levels") != 0
        or value.get("qualified_brightness_levels") != 0
    ):
        raise base.runner.RecheckError("LUMA-GRAY qualified-level count differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 8
        or value.get("runtime_lut_write") is not True
    ):
        raise base.runner.RecheckError("LUMA-GRAY version contract differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("actions") != list(base.runner.ACTIONS)
        or value.get("action_count") != 8
    ):
        raise base.runner.RecheckError("LUMA-GRAY manifest/action table differs")
    layout = value.get("history_layout", {})
    expected = {
        "pages": 2,
        "recipes_per_page": 16,
        "repeats_per_recipe_per_controller": 4,
        "required_valid_repeats": "4_of_4",
        "source_anchor_codes": [3, 7],
        "factory_otp_per_cell_black_white_source_implemented": False,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "position_dispersion_p95_delta_e76_max": 6.6032,
    }
    if any(layout.get(key) != wanted for key, wanted in expected.items()):
        raise base.runner.RecheckError("LUMA-GRAY manifest threshold/layout differs")
    _validate_capabilities(value)


# Rebind all dynamic validators inside the private mature runner facade.
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._origin = _private_origin
base.runner._http_request = _direct_http_request


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    _verify_local_artifacts()
    return v3.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def dry_validate() -> dict[str, Any]:
    _verify_local_artifacts()
    contract = REPORT["contract"]
    if (
        REPORT["contract_id"] != base.runner.CONTRACT_ID
        or len(REPORT["actions"]) != 8
        or len(contract["recipes"]) != 32
    ):
        raise base.runner.RecheckError("LUMA-GRAY offline identity differs")
    counts = {recipe: pack.RECIPE_AT_CELL.count(recipe) for recipe in range(16)}
    if set(counts.values()) != {4}:
        raise base.runner.RecheckError("LUMA-GRAY repeat placement differs")
    return {
        "kind": "mf1750-luma-gray-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": REPORT["contract_id"],
        "actions": 8,
        "recipes": 32,
        "repeats_per_recipe_per_controller": 4,
        "source_model_change": contract["source_model_change"],
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "firmware": {
            "bytes": base.runner.FIRMWARE_BYTES,
            "sha256": base.runner.FIRMWARE_SHA256,
        },
        "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(),
        "contract": deepcopy(REPORT["contract"]),
        "actions_table": deepcopy(base.runner.ACTIONS),
        "endpoints": deepcopy(base.runner.ENDPOINTS),
        "claims_root": str(base.runner.DEFAULT_CLAIMS),
        "output_root": str(base.runner.DEFAULT_OUTPUT),
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    sub.add_parser("describe")
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 9), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate()
        elif args.command == "describe":
            value = describe()
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"LUMA-GRAY-V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
