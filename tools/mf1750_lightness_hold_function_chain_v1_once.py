#!/usr/bin/env python3
"""Fail-closed one-action host for lightness construction plus local HOLD V1.

The host never flashes, resets, switches power, retries, recovers, or chains
actions.  Source authority and reviewed local artifacts are verified before
any device request.  One invocation may consume only one explicitly selected
ordinal from the five-action main firmware; factory-OTP white is a separate
successor and is intentionally absent here.
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

from tools import mf1750_lightness_hold_function_chain_v1_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_lightness_hold_function_chain_v1_host", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed one-action mechanics: {_BASE_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)
v1 = host.v1
base = host.base

REPORT = pack.build_report()
host.pack = pack
host.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

binding = pack.ARTIFACTS[pack.VARIANT_KEY]
base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-lightness-hold-function-chain-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-lightness-hold-function-chain-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = binding["bin_sha256"]
base.runner.FIRMWARE_BYTES = binding["bin_bytes"]
ELF_SHA256 = str(binding["elf_sha256"])
ELF_BYTES = int(binding["elf_bytes"])
base.runner.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = pack.ARM_INTENT
base.runner.EXECUTE_INTENT = pack.EXECUTE_INTENT


def _runner_actions() -> tuple[dict[str, Any], ...]:
    actions: list[dict[str, Any]] = []
    for source in REPORT["actions"]:
        ordinal = int(source["ordinal"])
        transport = source["transport"]
        actions.append(
            {
                "ordinal": ordinal,
                "descriptor_id": source["descriptor_id"],
                "action_id": source["action_id"],
                "prior_static_action_id": source["prior_action_id"],
                "boot_admission": {
                    "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
                    "admission": (
                        "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                        if ordinal == 1
                        else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY"
                    ),
                    "required_prior_terminal_state": (
                        None if ordinal == 1 else "COMPLETE"
                    ),
                    "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
                    "firmware_arm_gate": True,
                    "firmware_execute_gate": True,
                    "firmware_dispatch_gate": True,
                    "reboot_resume_allowed": False,
                    "post_containment_resume_allowed": False,
                },
                "role": source["role"],
                "round": 1,
                "branch": source["branch"],
                "palette_source": "L535_RUNTIME",
                "global_header": source["global_header"],
                "driver_entry": "epdDisplayCompiledChromaGrid",
                "frame_sha256": source["frame"]["sha256"],
                "cs1_dtm_sha256": transport["cs1_dtm"]["sha256"],
                "cs2_dtm_sha256": transport["cs2_dtm"]["sha256"],
                "transport_code_histogram": source["frame"]["histogram"],
            }
        )
    return tuple(actions)


base.runner.ACTIONS = _runner_actions()
base.runner.DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in base.runner.ACTIONS)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_lightness_hold_function_chain_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_20260901_V1"
)
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
ACTION_OUTPUTS = {
    ordinal: base.runner.DEFAULT_OUTPUT / f"action-{ordinal:02d}.json"
    for ordinal in range(1, 6)
}

_MAX_JSON_BYTES = 16 * 1024 * 1024
_NONCE = re.compile(r"^[0-9a-f]{16}$")


def _private_origin(value: str) -> str:
    if not isinstance(value, str):
        raise base.runner.RecheckError("base URL must be a private literal IPv4 HTTP origin")
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
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise base.runner.RecheckError("base URL must be an exact plain HTTP origin")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as error:
        raise base.runner.RecheckError("base URL must use literal IPv4") from error
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
        raise base.runner.RecheckError("base URL must use private/local IPv4")
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
    request = urllib_request.Request(
        base_url + path,
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
    )
    opener = urllib_request.build_opener(
        urllib_request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:  # noqa: S310
            status = response.status
            payload = response.read(_MAX_JSON_BYTES + 1)
    except urllib_error.HTTPError as error:
        status = error.code
        payload = error.read(_MAX_JSON_BYTES + 1)
    except (OSError, urllib_error.URLError) as error:
        raise base.runner.RecheckError(f"direct {method} {path} failed: {error}") from error
    if len(payload) > _MAX_JSON_BYTES:
        raise base.runner.RecheckError("device response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError("device response is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("device response root is not an object")
    return status, value


def _verify_local_artifacts() -> dict[str, Any]:
    try:
        return pack.validate_artifacts()
    except (OSError, RuntimeError) as error:
        raise base.runner.RecheckError(str(error)) from error


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    for key in (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "cross_palette_hold_probe",
        "history_brightness_screening",
        "brightness_candidates_only",
        "source_authority_sealed",
        "live_authorized",
    ):
        if value.get(key) is not True:
            raise base.runner.RecheckError(f"lightness/HOLD capability {key} differs")
    for key in (
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "local_hold_claimed",
        "automatic_chaining",
        "retry",
        "recovery",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(f"lightness/HOLD forbidden capability {key} differs")
    if value.get("qualified_brightness_levels") != 0:
        raise base.runner.RecheckError("qualified brightness count differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 5
        or value.get("runtime_lut_write") is not True
    ):
        raise base.runner.RecheckError("lightness/HOLD version contract differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != pack.NVS_NAMESPACE
        or nvs.get("key") != pack.NVS_KEY
        or nvs.get("campaign_boot_key") != pack.NVS_BOOT_KEY
        or nvs.get("reboot_resume_allowed") is not False
    ):
        raise base.runner.RecheckError("lightness/HOLD NVS isolation differs")
    baseline = value.get("baseline_contract", {})
    if baseline.get("external_anchor_required") is not True:
        raise base.runner.RecheckError("fresh external white anchor gate differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 5
        or value.get("actions") != list(base.runner.ACTIONS)
        or value.get("factory_otp") is not False
        or value.get("one_driver_call_per_action") is not True
    ):
        raise base.runner.RecheckError("lightness/HOLD manifest differs")
    layout = value.get("history_layout", {})
    expected = {
        "candidate_cells_total_observations": 128,
        "grid_x0_local": 20,
        "grid_y0": 40,
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 560,
        "profile_sequence": list(pack.GLOBAL_HEADERS),
        "hold_windows_nonoverlap_candidate_grid": True,
        "runtime_code7_full_dtm_prestage": True,
        "runtime_code7_prestage_bytes_per_controller": 153600,
        "ptlw_payloads_hex": [payload.hex() for payload in pack.PTLW_PAYLOADS],
        "runtime_target_dtm_bytes_per_controller": 4608,
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "command_0x86": False,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
    }
    if any(layout.get(key) != wanted for key, wanted in expected.items()):
        raise base.runner.RecheckError("lightness/HOLD manifest geometry/transport differs")
    source = layout.get("source_authority", {})
    if (
        source.get("sealed") is not True
        or source.get("state") != "SEALED"
        or source.get("required_before_any_device_request") is not True
        or source.get("clean_white_review_id") != pack.SOURCE_REVIEW_ID
    ):
        raise base.runner.RecheckError("lightness/HOLD source-authority surface differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= 5:
        raise base.runner.RecheckError("lightness/HOLD runnable ordinal differs")
    if expected_busy not in (0, 1) or (expected_busy == 0 and ordinal != 1):
        raise base.runner.RecheckError("lightness/HOLD BUSY admission differs")
    if value.get("busy") != expected_busy:
        raise base.runner.RecheckError("lightness/HOLD raw BUSY differs")
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=expected_busy
    )
    expected_count = ordinal - 1
    for key in ("arm_request_count", "execute_request_count", "total_driver_call_count"):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"lightness/HOLD ready {key} differs")
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
    ):
        raise base.runner.RecheckError("lightness/HOLD same-boot binding differs")
    return nonce


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if not 1 <= ordinal <= 5:
        raise base.runner.RecheckError("lightness/HOLD COMPLETE ordinal differs")
    action = base.runner.ACTIONS[ordinal - 1]
    source = REPORT["actions"][ordinal - 1]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 5,
        "no_retry": True,
        "no_recovery": True,
    }
    if any(value.get(key) != wanted for key, wanted in exact.items()):
        raise base.runner.RecheckError("lightness/HOLD terminal COMPLETE differs")
    driver = value.get("driver")
    transport = source["transport"]
    driver_exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": "none",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "spi_hz": 1_000_000,
        "operation_id": ordinal,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "input_fnv1a": source["frame"]["fnv1a"],
        "cs1_dtm_fnv1a": transport["cs1_dtm"]["fnv1a"],
        "cs2_dtm_fnv1a": transport["cs2_dtm"]["fnv1a"],
    }
    if not isinstance(driver, Mapping) or any(
        driver.get(key) != wanted for key, wanted in driver_exact.items()
    ):
        raise base.runner.RecheckError("lightness/HOLD driver evidence differs")
    if any(not _positive_int(driver.get(key)) for key in ("pon_ms", "drf_ms", "pof_ms")):
        raise base.runner.RecheckError("lightness/HOLD BUSY duration evidence differs")
    safe = driver.get("safe_finish", {})
    gpio = safe.get("final_gpio", {}) if isinstance(safe, Mapping) else {}
    if (
        not isinstance(safe, Mapping)
        or any(safe.get(key) != 1 for key in (
            "busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"
        ))
        or not isinstance(gpio, Mapping)
        or gpio != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}
    ):
        raise base.runner.RecheckError("lightness/HOLD safe finish differs")


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal <= 1:
        raise base.runner.RecheckError("lightness/HOLD prior ordinal differs")
    _validate_complete_report(value, ordinal - 1, boot_nonce)


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url, ordinal, expected_busy=expected_busy, requester=requester
    )
    if ordinal == 1:
        v1._validate_fresh_no_execute_report(report, boot_nonce)  # noqa: SLF001
    else:
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


# Rebind every validator consumed by the isolated reviewed runner facade.
host._validate_capabilities = _validate_capabilities
host._validate_version = _validate_version
host._validate_manifest = _validate_manifest
host._validate_ready_status = _validate_ready_status
host._validate_complete_report = _validate_complete_report
host._validate_prior_terminal_report = _validate_prior_terminal_report
host._preflight = _preflight
host._require_firmware_binding = lambda: _verify_local_artifacts()
host._FACTORY_HEALTH_ROLE = "__NO_FACTORY_ACTION_IN_MAIN__"
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner._origin = _private_origin
base.runner._http_request = _direct_http_request
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def _read_integrity_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"{label} missing or unsafe: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
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
    confirm_source_clean_white_retained: bool,
    output: Path = DIAGNOSTIC_OUTPUT,
    requester: Any = None,
) -> dict[str, Any]:
    if confirm_j2_off is not True or confirm_source_clean_white_retained is not True:
        raise base.runner.RecheckError("diagnostic requires J2-OFF and retained clean-white confirmations")
    source = pack.validate_source_authority(require_sealed=True)
    artifacts = _verify_local_artifacts()
    selected = requester or _direct_http_request
    origin = _private_origin(base_url)
    boot_nonce, transcript, report = _preflight(
        origin, 1, expected_busy=0, requester=selected
    )
    value = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-lightness-hold-function-chain-v1-j2-off-diagnostic",
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "source_authority": deepcopy(source),
            "artifacts": artifacts,
            "base_url": origin,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "source_clean_white_retained_confirmed": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "visible_refreshes": 0,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(Path(output), value)  # noqa: SLF001
    return value


def _validate_diagnostic(path: Path, base_url: str) -> dict[str, Any]:
    value = _read_integrity_json(path, label="lightness/HOLD J2-OFF diagnostic")
    if (
        value.get("kind") != "mf1750-lightness-hold-function-chain-v1-j2-off-diagnostic"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != REPORT["contract_id"]
        or value.get("source_authority") != pack.validate_source_authority(require_sealed=True)
        or value.get("artifacts") != _verify_local_artifacts()
        or value.get("base_url") != _private_origin(base_url)
        or value.get("j2_confirmed_off") is not True
        or value.get("source_clean_white_retained_confirmed") is not True
        or value.get("next_ordinal") != 1
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("visible_refreshes") != 0
    ):
        raise base.runner.RecheckError("lightness/HOLD diagnostic differs")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(boot_nonce, str) or _NONCE.fullmatch(boot_nonce) is None:
        raise base.runner.RecheckError("lightness/HOLD diagnostic boot nonce differs")
    return value


def _same_boot_requester(expected_boot_nonce: str, requester: Any) -> Any:
    def checked(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = requester(*args, **kwargs)
        observed = value.get("boot_nonce") if isinstance(value, Mapping) else None
        if observed is not None and observed != expected_boot_nonce:
            raise base.runner.RecheckError("live boot nonce differs from J2-OFF diagnostic")
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
    confirm_source_clean_white_review: bool = False,
) -> dict[str, Any]:
    if confirm_j2_on is not True or confirm_gnd_normal is not True:
        raise base.runner.RecheckError("run requires J2-ON and GND-normal confirmations")
    if confirm_source_clean_white_review is not True:
        raise base.runner.RecheckError("run requires the bound clean-white source confirmation")
    pack.validate_source_authority(require_sealed=True)
    _verify_local_artifacts()
    diagnostic = _validate_diagnostic(DIAGNOSTIC_OUTPUT, base_url)
    selected = requester or _direct_http_request
    selected = _same_boot_requester(str(diagnostic["boot_nonce"]), selected)
    return host.run_once(
        base_url,
        ordinal,
        claims=claims,
        output=output,
        requester=selected,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    result = pack.dry_validate(
        require_source_sealed=True, verify_artifacts=verify_artifacts
    )
    if len(base.runner.ACTIONS) != 5 or REPORT["contract"]["factory_white_successor_embedded"]:
        raise base.runner.RecheckError("five-action/no-white-successor boundary differs")
    return {
        "kind": "mf1750-lightness-hold-function-chain-v1-runner-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": REPORT["contract_id"],
        "actions": 5,
        "candidate_cells": 128,
        "hold_probes": 2,
        "qualified_brightness_levels": 0,
        "local_hold_claimed": False,
        "independent_white_successor_required": True,
        "artifacts_verified": verify_artifacts,
        "pack_validation": result,
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
    """Deep-validate the fixed ordinal-5 H2 COMPLETE result without device I/O."""

    pack.validate_source_authority(require_sealed=True)
    _verify_local_artifacts()
    resolved = Path(path).resolve()
    expected_path = ACTION_OUTPUTS[5].resolve()
    if resolved != expected_path:
        raise base.runner.RecheckError(
            "white successor accepts only the fixed ordinal-5 H2 COMPLETE file"
        )
    value = _read_integrity_json(resolved, label="lightness/HOLD H2 terminal evidence")
    if set(value) != {
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
    }:
        raise base.runner.RecheckError("lightness/HOLD H2 terminal fields differ")
    action = value.get("action")
    terminal = value.get("terminal_report")
    transcript = value.get("transcript")
    expected = base.runner.ACTIONS[4]
    if not isinstance(action, Mapping) or dict(action) != expected:
        raise base.runner.RecheckError("lightness/HOLD H2 action identity differs")
    if not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("lightness/HOLD H2 terminal report missing")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(boot_nonce, str) or _NONCE.fullmatch(boot_nonce) is None:
        raise base.runner.RecheckError("lightness/HOLD H2 boot nonce differs")
    _validate_complete_report(terminal, 5, boot_nonce)
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "mf1750-ec5-lightness-hold-function-chain-v1-result"
        or value.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or terminal.get("campaign_id") != pack.CAMPAIGN_ID
        or terminal.get("contract_id") != REPORT["contract_id"]
        or terminal.get("total_driver_call_count") != 5
    ):
        raise base.runner.RecheckError(
            "lightness/HOLD H2 COMPLETE/driver semantics differ"
        )
    if not isinstance(transcript, list) or len(transcript) < 7:
        raise base.runner.RecheckError("lightness/HOLD H2 transcript missing")
    expected_prefix = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    if (
        [(item.get("method"), item.get("endpoint")) for item in transcript[:6]]
        != expected_prefix
        or any(
            (item.get("method"), item.get("endpoint")) != ("GET", "report")
            for item in transcript[6:]
        )
        or any(
            item.get("path") != base.runner.ENDPOINTS.get(item.get("endpoint"))
            or not isinstance(item.get("status"), int)
            or not 200 <= item["status"] < 300
            or not isinstance(item.get("response"), Mapping)
            for item in transcript
        )
        or value.get("network")
        != {"get": 4 + len(transcript[6:]), "arm_post": 1, "execute_post": 1}
    ):
        raise base.runner.RecheckError(
            "lightness/HOLD H2 transcript mutation sequence differs"
        )
    try:
        _validate_version(transcript[0]["response"])
        _validate_manifest(transcript[1]["response"])
        observed_boot = _validate_ready_status(
            transcript[2]["response"], 5, expected_busy=1
        )
        _validate_prior_terminal_report(transcript[3]["response"], 5, observed_boot)
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "lightness/HOLD H2 preflight transcript differs"
        ) from error
    if observed_boot != boot_nonce:
        raise base.runner.RecheckError(
            "lightness/HOLD H2 preflight/result boot nonce differs"
        )
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
        or arm_response.get("ordinal") != 5
        or arm_response.get("action_id") != expected["action_id"]
        or arm_response.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or _NONCE.fullmatch(arm_nonce) is None
        or execute_response.get("accepted") is not True
        or execute_response.get("execute_consumed") is not True
        or execute_response.get("ordinal") != 5
        or execute_response.get("action_id") != expected["action_id"]
        or execute_response.get("boot_nonce") != boot_nonce
        or transcript[-1]["response"] != terminal
    ):
        raise base.runner.RecheckError(
            "lightness/HOLD H2 ARM/EXECUTE/report wire evidence differs"
        )
    claim_path = value.get("claim_file")
    expected_claim_path = (
        base.runner.DEFAULT_CLAIMS / f"{expected['action_id']}.json"
    ).resolve()
    if not isinstance(claim_path, str) or Path(claim_path).resolve() != expected_claim_path:
        raise base.runner.RecheckError("lightness/HOLD H2 permanent claim path differs")
    try:
        claim, claim_file_sha256 = v1._load_permanent_claim(  # noqa: SLF001
            expected_claim_path, expected
        )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "lightness/HOLD H2 permanent claim deep validation failed"
        ) from error
    if claim.get("boot_nonce") != boot_nonce:
        raise base.runner.RecheckError("lightness/HOLD H2 claim boot differs")
    claim_payload = expected_claim_path.read_bytes()
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "ordinal": 5,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 5,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "boot_nonce": boot_nonce,
        "claim_path": expected_claim_path.relative_to(REPO_ROOT).as_posix(),
        "claim_bytes": len(claim_payload),
        "claim_file_sha256": claim_file_sha256,
        "claim_canonical_integrity_sha256": claim["integrity"]["sha256"],
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
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
    diag.add_argument(
        "--confirm-source-clean-white-retained", action="store_true", required=True
    )
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=range(1, 6), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    run.add_argument(
        "--confirm-source-clean-white-review", action="store_true", required=True
    )
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
                confirm_source_clean_white_retained=(
                    args.confirm_source_clean_white_retained
                ),
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
                confirm_source_clean_white_review=(
                    args.confirm_source_clean_white_review
                ),
            )
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"lightness/HOLD V1 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
