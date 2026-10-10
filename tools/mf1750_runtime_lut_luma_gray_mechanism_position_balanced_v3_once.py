#!/usr/bin/env python3
"""Fail-closed one-action host for LUMA/GRAY mechanism V3.

The host never flashes, resets, controls power, retries, recovers, or chains
actions.  It consumes one explicitly selected ordinal only, requires a sealed
same-boot J2-OFF diagnostic plus fresh human J2/GND assertions, and accepts one
strict COMPLETE result.  G4 is never selected automatically.
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

from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as pack,
)

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_luma_gray_mpb_v3_host", _BASE_PATH
)
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
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-luma-gray-mechanism-position-balanced-v3"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-luma-gray-mechanism-position-balanced-v3"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = str(pack.ARTIFACTS["bin_sha256"])
base.runner.FIRMWARE_BYTES = int(pack.ARTIFACTS["bin_bytes"])
ELF_SHA256 = str(pack.ARTIFACTS["elf_sha256"])
ELF_BYTES = int(pack.ARTIFACTS["elf_bytes"])
BUILD_DIR = REPO_ROOT / ".pio" / pack.CONFIG.build_root / pack.CONFIG.environment
base.runner.ENDPOINTS = {
    name: f"{pack.CONFIG.base_route}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = pack.ARM_INTENT
base.runner.EXECUTE_INTENT = pack.EXECUTE_INTENT


def _runner_actions() -> tuple[dict[str, Any], ...]:
    actions = deepcopy(base._actions())
    for action, source in zip(actions, REPORT["actions"], strict=True):
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
        action["driver_entry"] = "epdDisplayCompiledChromaGrid"
    return tuple(actions)


base.runner.ACTIONS = _runner_actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_luma_gray_mechanism_position_balanced_v3_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_20260901_V3"
)
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUTS = {
    1: base.runner.DEFAULT_OUTPUT / "action-01-g1-active-c7-source.json",
    2: base.runner.DEFAULT_OUTPUT
    / "action-02-g2-commented-c0-to-c7-position-balanced-middle.json",
    3: base.runner.DEFAULT_OUTPUT / "action-03-g3-active-c3-c7-target.json",
    4: base.runner.DEFAULT_OUTPUT
    / "action-04-g4-active-c3-c7-identical-target-repeat.json",
}
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
    if not pack.artifacts_are_sealed():
        raise base.runner.RecheckError("V3 artifacts are not sealed")
    for name, size, digest in (
        ("firmware.bin", base.runner.FIRMWARE_BYTES, base.runner.FIRMWARE_SHA256),
        ("firmware.elf", ELF_BYTES, ELF_SHA256),
    ):
        path = BUILD_DIR / name
        if not path.is_file():
            raise base.runner.RecheckError(
                f"reviewed LUMA/GRAY V3 artifact missing: {path}"
            )
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise base.runner.RecheckError(
                f"reviewed LUMA/GRAY V3 artifact differs: {path}"
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
            raise base.runner.RecheckError(f"LUMA/GRAY V3 capability {key} differs")
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
                f"LUMA/GRAY V3 forbidden capability {key} differs"
            )
    if (
        value.get("qualified_gray_levels") != 0
        or value.get("qualified_brightness_levels") != 0
    ):
        raise base.runner.RecheckError("LUMA/GRAY V3 qualified-level count differs")
    if (
        value.get("g4_manual_or_host_selection_only") is not True
        or value.get("g4_autochain") is not False
    ):
        raise base.runner.RecheckError("LUMA/GRAY V3 G4 selection policy differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 4
        or value.get("runtime_lut_write") is not True
    ):
        raise base.runner.RecheckError("LUMA/GRAY V3 version contract differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("actions") != list(base.runner.ACTIONS)
        or value.get("action_count") != 4
    ):
        raise base.runner.RecheckError("LUMA/GRAY V3 manifest/action table differs")
    layout = value.get("history_layout", {})
    expected = {
        "recipes": 16,
        "repeats_per_recipe_per_controller": 4,
        "required_valid_repeats": "4_of_4",
        "source_code": 7,
        "target_codes": [3, 7],
        "cs2_semantic_rotation_degrees": 180,
        "border_pixels": 0,
        "central_roi": True,
        "g4_payload_byte_identical_to_g3": True,
        "g4_independent_explicit_manual_or_host_selection": True,
        "g4_automatic_chain": False,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
    }
    if any(layout.get(key) != wanted for key, wanted in expected.items()):
        raise base.runner.RecheckError("LUMA/GRAY V3 manifest layout differs")
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


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"{label} missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise base.runner.RecheckError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256") if isinstance(integrity, Mapping) else None
    actual = hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if recorded != actual:
        raise base.runner.RecheckError(f"{label} canonical integrity differs")
    return value


def diagnose_j2_off(
    base_url: str,
    *,
    confirm_j2_off: bool,
    output: Path = DIAGNOSTIC_OUTPUT,
    requester: Any = None,
) -> dict[str, Any]:
    """Capture one immutable four-GET, zero-mutation diagnostic."""

    if confirm_j2_off is not True:
        raise base.runner.RecheckError(
            "V3 diagnostic requires explicit J2-OFF confirmation"
        )
    pack.validate_source_gate()
    _verify_local_artifacts()
    selected = requester or _direct_http_request
    origin = _private_origin(base_url)
    boot_nonce, transcript, report = v3._preflight(  # noqa: SLF001
        origin, 1, expected_busy=0, requester=selected
    )
    value = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 2,
            "kind": (
                "mf1750-ec5-luma-gray-mechanism-position-balanced-v3-j2-off-diagnostic"
            ),
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CONFIG.campaign_id,
            "contract_id": REPORT["contract_id"],
            "firmware": {
                "bytes": base.runner.FIRMWARE_BYTES,
                "sha256": base.runner.FIRMWARE_SHA256,
            },
            "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
            "source_gate": deepcopy(pack.validate_source_gate()),
            "base_url": origin,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "visible_refreshes": 0,
            "no_retry": True,
            "no_fallback": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(Path(output), value)  # noqa: SLF001
    return value


def _validate_diagnostic(path: Path, base_url: str) -> dict[str, Any]:
    value = _read_integrity_json(path, label="V3 J2-OFF diagnostic")
    transcript = value.get("transcript")
    expected_paths = [
        base.runner.ENDPOINTS[name]
        for name in ("version", "manifest", "status", "report")
    ]
    if (
        value.get("kind")
        != "mf1750-ec5-luma-gray-mechanism-position-balanced-v3-j2-off-diagnostic"
        or value.get("campaign_id") != pack.CONFIG.campaign_id
        or value.get("contract_id") != REPORT["contract_id"]
        or value.get("firmware")
        != {
            "bytes": base.runner.FIRMWARE_BYTES,
            "sha256": base.runner.FIRMWARE_SHA256,
        }
        or value.get("elf") != {"bytes": ELF_BYTES, "sha256": ELF_SHA256}
        or value.get("source_gate") != pack.validate_source_gate()
        or value.get("base_url") != _private_origin(base_url)
        or value.get("j2_confirmed_off") is not True
        or value.get("next_ordinal") != 1
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("visible_refreshes") != 0
        or not isinstance(transcript, list)
        or len(transcript) != 4
        or [item.get("path") for item in transcript] != expected_paths
        or any(item.get("method") != "GET" for item in transcript)
        or any(item.get("status") != 200 for item in transcript)
    ):
        raise base.runner.RecheckError("V3 J2-OFF diagnostic semantics differ")
    boot_nonce = value.get("boot_nonce")
    if (
        not isinstance(boot_nonce, str)
        or re.fullmatch(r"[0-9a-f]{16}", boot_nonce) is None
    ):
        raise base.runner.RecheckError("V3 diagnostic boot nonce differs")
    return value


def _same_boot_requester(expected_boot_nonce: str, requester: Any) -> Any:
    def checked(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = requester(*args, **kwargs)
        observed = value.get("boot_nonce") if isinstance(value, Mapping) else None
        if observed is not None and observed != expected_boot_nonce:
            raise base.runner.RecheckError(
                "V3 live response boot nonce differs from J2-OFF diagnostic"
            )
        return status, value

    return checked


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    confirm_j2_on: bool = False,
    confirm_gnd_normal: bool = False,
    confirm_current_v3_camera_relative_white: bool = False,
    confirm_optional_g4_repeat: bool = False,
) -> dict[str, Any]:
    if confirm_j2_on is not True:
        raise base.runner.RecheckError("V3 run requires explicit J2-ON confirmation")
    if confirm_gnd_normal is not True:
        raise base.runner.RecheckError(
            "V3 run requires explicit GND-normal confirmation"
        )
    if confirm_current_v3_camera_relative_white is not True:
        raise base.runner.RecheckError(
            "V3 run requires explicit current V3 camera-relative clean-white confirmation"
        )
    if ordinal == 4 and confirm_optional_g4_repeat is not True:
        raise base.runner.RecheckError(
            "G4 is optional and requires its own explicit repeat confirmation"
        )
    if ordinal != 4 and confirm_optional_g4_repeat is True:
        raise base.runner.RecheckError("G4 repeat confirmation is forbidden for G1-G3")
    pack.validate_source_gate()
    _verify_local_artifacts()
    diagnostic = _validate_diagnostic(DIAGNOSTIC_OUTPUT, base_url)
    selected = requester or _direct_http_request
    selected = _same_boot_requester(str(diagnostic["boot_nonce"]), selected)
    return v3.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=selected,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    pack.dry_validate(verify_artifacts=verify_artifacts)
    if verify_artifacts:
        _verify_local_artifacts()
    contract = REPORT["contract"]
    if (
        REPORT["contract_id"] != base.runner.CONTRACT_ID
        or len(REPORT["actions"]) != 4
        or len(contract["recipes"]) != 16
    ):
        raise base.runner.RecheckError("LUMA/GRAY V3 offline identity differs")
    counts_cs1 = {recipe: pack.CS1_RECIPE_AT_CELL.count(recipe) for recipe in range(16)}
    counts_cs2 = {recipe: pack.CS2_RECIPE_AT_CELL.count(recipe) for recipe in range(16)}
    if set(counts_cs1.values()) != {4} or counts_cs1 != counts_cs2:
        raise base.runner.RecheckError("LUMA/GRAY V3 repeat placement differs")
    return {
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-runner-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": REPORT["contract_id"],
        "actions": 4,
        "recipes": 16,
        "repeats_per_recipe_per_controller": 4,
        "source_gate": deepcopy(pack.validate_source_gate()),
        "g4_explicit_optional_no_autochain": True,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "artifacts_verified": verify_artifacts,
        "firmware": {
            "bytes": base.runner.FIRMWARE_BYTES,
            "sha256": base.runner.FIRMWARE_SHA256,
        },
        "elf": {"bytes": ELF_BYTES, "sha256": ELF_SHA256},
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(verify_artifacts=pack.artifacts_are_sealed()),
        "contract": deepcopy(REPORT["contract"]),
        "actions_table": deepcopy(base.runner.ACTIONS),
        "endpoints": deepcopy(base.runner.ENDPOINTS),
        "claims_root": str(base.runner.DEFAULT_CLAIMS),
        "output_root": str(base.runner.DEFAULT_OUTPUT),
    }


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    """Deep-validate a sealed G1-G4 COMPLETE result without any I/O."""

    _verify_local_artifacts()
    value = _read_integrity_json(Path(path), label="V3 terminal evidence")
    action = value.get("action")
    terminal = value.get("terminal_report")
    transcript = value.get("transcript")
    if not isinstance(action, Mapping) or not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("V3 terminal action/report missing")
    ordinal = action.get("ordinal")
    if (
        not isinstance(ordinal, int)
        or isinstance(ordinal, bool)
        or not 1 <= ordinal <= 4
    ):
        raise base.runner.RecheckError("V3 terminal ordinal differs")
    expected = base.runner.ACTIONS[ordinal - 1]
    if dict(action) != expected:
        raise base.runner.RecheckError("V3 terminal action identity differs")
    boot_nonce = value.get("boot_nonce")
    if (
        not isinstance(boot_nonce, str)
        or base.runner._NONCE.fullmatch(boot_nonce) is None
    ):  # noqa: SLF001
        raise base.runner.RecheckError("V3 terminal boot nonce differs")
    try:
        v3._validate_complete_report(terminal, ordinal, boot_nonce)  # noqa: SLF001
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "V3 terminal strict COMPLETE/driver validation failed"
        ) from error
    driver = terminal.get("driver")
    if (
        set(value)
        != {
            "schema_version",
            "kind",
            "created_at",
            "firmware_sha256",
            "boot_nonce",
            "action",
            "claim_file",
            "terminal_report",
            "transcript",
            "network",
            "outcome",
            "visible_refreshes",
            "no_retry",
            "no_recovery",
            "no_autochain",
            "integrity",
        }
        or value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-ec5-luma-gray-mechanism-position-balanced-v3-result"
        or value.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or terminal.get("boot_nonce") != boot_nonce
        or terminal.get("campaign_id") != pack.CAMPAIGN_ID
        or terminal.get("contract_id") != REPORT["contract_id"]
        or terminal.get("total_driver_call_count") != ordinal
        or not isinstance(driver, Mapping)
        or driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("timeout_stage") != "none"
    ):
        raise base.runner.RecheckError("V3 terminal COMPLETE/driver semantics differ")
    if not isinstance(transcript, list) or len(transcript) < 7:
        raise base.runner.RecheckError("V3 terminal transcript missing")
    expected_prefix = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    observed_prefix = [
        (item.get("method"), item.get("endpoint")) for item in transcript[:6]
    ]
    if (
        observed_prefix != expected_prefix
        or any(
            (item.get("method"), item.get("endpoint")) != ("GET", "report")
            for item in transcript[6:]
        )
        or any(
            item.get("path") != base.runner.ENDPOINTS[item.get("endpoint")]
            or not 200 <= item.get("status", 0) < 300
            or not isinstance(item.get("response"), Mapping)
            for item in transcript
        )
        or value.get("network")
        != {"get": 4 + len(transcript[6:]), "arm_post": 1, "execute_post": 1}
    ):
        raise base.runner.RecheckError(
            "V3 terminal transcript mutation sequence differs"
        )
    try:
        v3._validate_version(transcript[0]["response"])  # noqa: SLF001
        v3._validate_manifest(transcript[1]["response"])  # noqa: SLF001
        observed_boot = v3._validate_ready_status(  # noqa: SLF001
            transcript[2]["response"], ordinal, expected_busy=1
        )
        if ordinal == 1:
            v1._validate_fresh_no_execute_report(  # noqa: SLF001
                transcript[3]["response"], observed_boot
            )
        else:
            v3._validate_prior_terminal_report(  # noqa: SLF001
                transcript[3]["response"], ordinal, observed_boot
            )
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError("V3 preflight transcript differs") from error
    if observed_boot != boot_nonce:
        raise base.runner.RecheckError("V3 preflight/result boot nonce differs")
    arm = transcript[4]
    execute = transcript[5]
    arm_response = arm["response"]
    execute_response = execute["response"]
    arm_nonce = arm_response.get("arm_nonce")
    expected_arm_headers = base.runner._headers(  # noqa: SLF001
        expected, boot_nonce, pack.ARM_INTENT
    )
    expected_execute_headers = base.runner._headers(  # noqa: SLF001
        expected, boot_nonce, pack.EXECUTE_INTENT
    )
    expected_execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    if (
        arm.get("headers") != dict(sorted(expected_arm_headers.items()))
        or execute.get("headers") != dict(sorted(expected_execute_headers.items()))
        or arm_response.get("accepted") is not True
        or arm_response.get("armed") is not True
        or arm_response.get("ordinal") != ordinal
        or arm_response.get("action_id") != expected["action_id"]
        or arm_response.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or base.runner._NONCE.fullmatch(arm_nonce) is None  # noqa: SLF001
        or execute_response.get("accepted") is not True
        or execute_response.get("execute_consumed") is not True
        or execute_response.get("ordinal") != ordinal
        or execute_response.get("action_id") != expected["action_id"]
        or execute_response.get("boot_nonce") != boot_nonce
        or transcript[-1]["response"] != terminal
    ):
        raise base.runner.RecheckError("V3 ARM/EXECUTE/report wire evidence differs")
    claim_path = value.get("claim_file")
    if not isinstance(claim_path, str):
        raise base.runner.RecheckError("V3 terminal claim path missing")
    expected_claim_path = (
        base.runner.DEFAULT_CLAIMS / f"{expected['action_id']}.json"
    ).resolve()
    if Path(claim_path).resolve() != expected_claim_path:
        raise base.runner.RecheckError("V3 permanent claim path differs")
    try:
        claim, claim_file_sha256 = v1._load_permanent_claim(  # noqa: SLF001
            expected_claim_path, expected
        )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "V3 permanent claim deep validation failed"
        ) from error
    if (
        claim.get("action") != expected
        or claim.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or claim.get("boot_nonce") != boot_nonce
        or claim.get("state") != "claimed_before_first_mutation"
        or claim.get("no_retry") is not True
        or claim.get("no_recovery") is not True
        or claim.get("no_autochain") is not True
    ):
        raise base.runner.RecheckError("V3 permanent claim semantics differ")
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "ordinal": ordinal,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "boot_nonce": boot_nonce,
        "total_driver_call_count": ordinal,
        "claim_file_sha256": claim_file_sha256,
        "file_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    sub.add_parser("prebuild-validate")
    sub.add_parser("describe")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 5), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    run.add_argument(
        "--confirm-current-v3-camera-relative-white", action="store_true", required=True
    )
    run.add_argument("--confirm-optional-g4-repeat", action="store_true")
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate(verify_artifacts=True)
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "describe":
            value = describe()
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                confirm_j2_off=args.confirm_j2_off,
                output=DIAGNOSTIC_OUTPUT,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=base.runner.DEFAULT_CLAIMS,
                output=ACTION_OUTPUTS[args.ordinal],
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_current_v3_camera_relative_white=(
                    args.confirm_current_v3_camera_relative_white
                ),
                confirm_optional_g4_repeat=args.confirm_optional_g4_repeat,
            )
    except base.runner.RecheckError as error:
        print(f"LUMA/GRAY mechanism V3 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
