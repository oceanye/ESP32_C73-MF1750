#!/usr/bin/env python3
"""One-action runner for the external-anchor post-PON repeat-PTLW probe.

The runner never flashes, resets, controls power, retries, recovers, or chains
actions.  Every run invocation requires an explicit acknowledgement that the
campaign lineage started from a factory-OTP clean-white anchor established
outside this firmware; for later ordinals this does not claim the screen is
currently white.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_pack as pack,
)

_BASE_PATH = Path(__file__).with_name("mf1750_runtime_lut_partial_hold_once.py")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_repeat_ptlw_v1_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

_BASE_VALIDATE_READY_STATUS = base.runner._validate_ready_status  # noqa: SLF001
_BASE_PREFLIGHT = base.runner._preflight  # noqa: SLF001

REPORT = pack.build_report()
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 55.0
base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V1"
)
base.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-repeat-ptlw-v1"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_POST_PON_REPEAT_PTLW_"
    "EXTERNAL_FACTORY_WHITE_ANCHOR_REQUIRED"
)
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-runtime-lut-repeat-ptlw-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = "cursor_rptlw_v1"
base.runner.FIRMWARE_SHA256 = (
    "1be9e61d5d3749701a98b642c16c9e02b56d37e7103c51052d8d9db1698ea116"
)
base.runner.FIRMWARE_BYTES = 793312
base.runner.ENDPOINTS = {
    name: f"/api/ec5/runtime-lut-repeat-ptlw/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = "ARM_ONE_FIXED_L535_POST_PON_REPEAT_PTLW_ACTION"
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_L535_POST_PON_REPEAT_PTLW_ACTION_ONCE"
)
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_repeat_ptlw_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_REPEAT_PTLW_20260823_V1"
)


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "same_palette_hold_probe",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "full_screen_global_refresh",
        "cross_palette_hold_probe",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("repeat-PTLW capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError(
            "repeat-PTLW forbidden-operation contract differs"
        )


def _validate_baseline(value: Mapping[str, Any]) -> None:
    baseline = value.get("baseline_contract", {})
    expected = {
        "ordinal": None,
        "role": "EXTERNAL_FACTORY_OTP_CLEAN_WHITE",
        "external_anchor_required": True,
        "anchor_established_by_firmware": False,
        "one_visible_refresh_required": False,
        "code7_baseline_action_reachable": False,
        "recovery_action_reachable": False,
    }
    if baseline != expected:
        raise base.runner.RecheckError("external factory-white anchor differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")
    expected_false = (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    )
    if value.get("action_count") != len(base.runner.ACTIONS):
        raise base.runner.RecheckError("device action count differs")
    if value.get("runtime_lut_write") is not True or any(
        value.get(key) is not False for key in expected_false
    ):
        raise base.runner.RecheckError("device repeat-PTLW safety contract differs")
    nvs = value.get("nvs_contract", {})
    if (
        nvs.get("namespace") != base.runner.NVS_NAMESPACE
        or nvs.get("key") != base.runner.NVS_KEY
        or nvs.get("terminal_next_ordinal") != 4
    ):
        raise base.runner.RecheckError("device NVS isolation differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")
    if value.get("actions") != list(base.runner.ACTIONS):
        raise base.runner.RecheckError("device three-action manifest differs")
    exact = {
        "action_count": 3,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device manifest {key} differs")
    layout = value.get("history_layout", {})
    layout_exact = {
        "runtime_lut_profile_id": pack.PROFILE_ID,
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "ptlw_mode": 1,
        "windows_disjoint": True,
        "external_factory_white_anchor_required": True,
        "anchor_established_by_firmware": False,
        "runtime_code7_action_reachable": False,
        "full_white_dtm_transport": None,
        "ptlw_writes_per_controller": 2,
        "initial_ptlw_before_cropped_dtm": True,
        "repeat_ptlw_after_pon_busy": True,
        "pre_pon_cdi_ff_preserved": True,
        "post_pon_sequence": [
            "PTLW_CS1",
            "PTLW_CS2",
            "CDI_FF_BOTH",
            "BTST2",
            "DRF",
        ],
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"device layout {key} differs")
    profile = REPORT["contract"]["profile"]
    for key in (
        "cs1_r20_prefix_bytes",
        "cs1_r20_prefix_sha256",
        "cs2_r20_prefix_bytes",
        "cs2_r20_prefix_sha256",
        "r21_bytes",
        "r21_sha256",
    ):
        if layout.get(key) != profile[key]:
            raise base.runner.RecheckError(f"device LUT profile {key} differs")
    _validate_capabilities(value)
    _validate_baseline(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    """Accept late BUSY-low only for an otherwise exact runnable state.

    The base validator continues to enforce READY phase, cursor, fresh-key
    state, fixture self-check, RST/CS/CS2 LOW and all other GPIO/state fields.
    The matching report proof is enforced by :func:`_preflight` below.
    """

    observed_busy = value.get("busy")
    accepted_busy = expected_busy
    if (
        expected_busy == 1
        and 1 <= ordinal <= len(base.runner.ACTIONS)
        and observed_busy == 0
    ):
        accepted_busy = 0
    nonce = _BASE_VALIDATE_READY_STATUS(
        value, ordinal, expected_busy=accepted_busy
    )
    expected_count = ordinal - 1
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"device ready status {key} differs")
    return nonce


def _validate_fresh_no_execute_report(
    value: Mapping[str, Any], boot_nonce: str
) -> None:
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": False,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "phase": 0,
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device fresh report {key} differs")
    if "driver" in value:
        raise base.runner.RecheckError("device fresh report unexpectedly has driver")


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    prior = base.runner.ACTIONS[ordinal - 2]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal - 1,
        "ordinal": ordinal - 1,
        "descriptor_id": prior["descriptor_id"],
        "action_id": prior["action_id"],
        "role": prior["role"],
        "branch": prior["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal,
        "campaign_complete": False,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device prior report {key} differs")

    driver = value.get("driver")
    safe_finish = driver.get("safe_finish") if isinstance(driver, Mapping) else None
    final_gpio = (
        safe_finish.get("final_gpio") if isinstance(safe_finish, Mapping) else None
    )
    if not isinstance(driver, Mapping) or any(
        driver.get(key) != wanted
        for key, wanted in {
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "spi_hz": 1_000_000,
        }.items()
    ):
        raise base.runner.RecheckError("device prior terminal driver differs")
    if not isinstance(safe_finish, Mapping) or any(
        safe_finish.get(key) != 1
        for key in (
            "busy_before_pins_low",
            "busy_after_pins_low",
            "busy_after_5ms",
        )
    ):
        raise base.runner.RecheckError("device prior safe-finish BUSY differs")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != wanted
        for key, wanted in {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}.items()
    ):
        raise base.runner.RecheckError("device prior safe-finish GPIO differs")


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = _BASE_PREFLIGHT(
        base_url,
        ordinal,
        expected_busy=expected_busy,
        requester=requester,
    )
    if ordinal == 1:
        _validate_fresh_no_execute_report(report, boot_nonce)
    elif 1 < ordinal <= len(base.runner.ACTIONS):
        _validate_prior_terminal_report(report, ordinal, boot_nonce)
    return boot_nonce, transcript, report


def _load_permanent_claim(
    path: Path, action: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    path = Path(path)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise base.runner.RecheckError(f"cannot read permanent claim {path}: {error}") from error
    if len(payload) > base.runner._MAX_JSON_BYTES:  # noqa: SLF001
        raise base.runner.RecheckError("permanent claim is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError("permanent claim is not valid UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("permanent claim root is not an object")
    claim = deepcopy(dict(value))
    integrity = claim.pop("integrity", None)
    expected_integrity = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(base.runner._canonical(claim)).hexdigest(),  # noqa: SLF001
    }
    if integrity != expected_integrity:
        raise base.runner.RecheckError("permanent claim integrity differs")
    allowed_keys = {
        "schema_version",
        "kind",
        "created_at",
        "firmware_sha256",
        "boot_nonce",
        "action",
        "state",
        "no_retry",
        "no_recovery",
        "no_autochain",
    }
    if set(claim) != allowed_keys:
        raise base.runner.RecheckError("permanent claim fields differ")
    exact = {
        "schema_version": 1,
        "kind": f"{base.runner.EVIDENCE_KIND_PREFIX}-permanent-claim",
        "firmware_sha256": base.runner.FIRMWARE_SHA256,
        "action": dict(action),
        "state": "claimed_before_first_mutation",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    for key, wanted in exact.items():
        if claim.get(key) != wanted:
            raise base.runner.RecheckError(f"permanent claim {key} differs")
    boot_nonce = claim.get("boot_nonce")
    if (
        not isinstance(boot_nonce, str)
        or base.runner._NONCE.fullmatch(boot_nonce) is None  # noqa: SLF001
    ):
        raise base.runner.RecheckError("permanent claim boot nonce is malformed")
    if not isinstance(claim.get("created_at"), str) or not claim["created_at"]:
        raise base.runner.RecheckError("permanent claim created_at differs")
    claim["integrity"] = integrity
    return claim, hashlib.sha256(payload).hexdigest()


def _validate_fault_status(
    value: Mapping[str, Any],
    action: Mapping[str, Any],
    boot_nonce: str,
) -> None:
    base.runner._identity(value, kind_suffix="status")  # noqa: SLF001
    ordinal = int(action["ordinal"])
    exact = {
        "boot_nonce": boot_nonce,
        "state": "fault_locked",
        "phase": 3,
        "phase_name": "FAULT",
        "cursor_raw": (3 << 8) | ordinal,
        "next_ordinal": ordinal,
        "current_action": dict(action),
        "campaign_complete": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "persistent_key_present": True,
        "execute_pending": False,
        "gpio_initialized": True,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "arm_request_count": ordinal,
        "execute_request_count": ordinal,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device fault status {key} differs")
    if value.get("busy") not in (0, 1):
        raise base.runner.RecheckError("device fault status busy differs")
    if value.get("total_driver_call_count") not in (ordinal - 1, ordinal):
        raise base.runner.RecheckError(
            "device fault status total_driver_call_count differs"
        )


def _validate_fault_report(
    value: Mapping[str, Any],
    action: Mapping[str, Any],
    boot_nonce: str,
    *,
    status: Mapping[str, Any] | None = None,
) -> None:
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    ordinal = int(action["ordinal"])
    driver_called = value.get("driver_called")
    if driver_called not in (False, True):
        raise base.runner.RecheckError("device fault report driver_called differs")
    expected_total = ordinal if driver_called else ordinal - 1
    exact = {
        "boot_nonce": boot_nonce,
        "valid": bool(driver_called),
        "terminal_state": "FAULT",
        "result": False,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": ordinal,
        "driver_call_count_for_action": 1 if driver_called else 0,
        "total_driver_call_count": expected_total,
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": ordinal,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"device fault report {key} differs")
    error = value.get("error")
    if not isinstance(error, str) or not error:
        raise base.runner.RecheckError("device fault report error differs")
    if status is not None and status.get("total_driver_call_count") != expected_total:
        raise base.runner.RecheckError("fault status/report driver count differs")

    driver = value.get("driver")
    if not driver_called:
        if driver is not None:
            raise base.runner.RecheckError(
                "device no-driver fault unexpectedly includes driver"
            )
        return
    if not isinstance(driver, Mapping) or any(
        driver.get(key) != wanted
        for key, wanted in {
            "valid": True,
            "running": False,
            "spi_hz": 1_000_000,
        }.items()
    ):
        raise base.runner.RecheckError("device fault driver differs")
    safe_finish = driver.get("safe_finish")
    final_gpio = (
        safe_finish.get("final_gpio") if isinstance(safe_finish, Mapping) else None
    )
    if not isinstance(safe_finish, Mapping) or any(
        safe_finish.get(key) not in (0, 1)
        for key in (
            "busy_before_pins_low",
            "busy_after_pins_low",
            "busy_after_5ms",
        )
    ):
        raise base.runner.RecheckError("device fault safe-finish BUSY differs")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != 0 for key in ("rst", "cs", "cs2")
    ):
        raise base.runner.RecheckError("device fault safe-finish GPIO differs")
    if final_gpio.get("busy") not in (0, 1):
        raise base.runner.RecheckError("device fault final BUSY differs")


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
) -> dict[str, Any]:
    """GET-only recovery of a same-boot consumed FAULT evidence record."""

    if ordinal < 1 or ordinal > len(base.runner.ACTIONS):
        raise base.runner.RecheckError(
            f"ordinal must be between 1 and {len(base.runner.ACTIONS)}"
        )
    output = Path(output)
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    action = base.runner.ACTIONS[ordinal - 1]
    claim_file = Path(claims) / f"{action['action_id']}.json"
    claim, claim_file_sha256 = _load_permanent_claim(claim_file, action)
    boot_nonce = str(claim["boot_nonce"])
    requester = requester or base.runner._http_request  # noqa: SLF001
    origin = base.runner._origin(base_url)  # noqa: SLF001
    transcript: list[dict[str, Any]] = []
    version = base.runner._request(  # noqa: SLF001
        requester, transcript, origin, "version"
    )
    manifest = base.runner._request(  # noqa: SLF001
        requester, transcript, origin, "manifest"
    )
    status = base.runner._request(  # noqa: SLF001
        requester, transcript, origin, "status"
    )
    report = base.runner._request(  # noqa: SLF001
        requester, transcript, origin, "report"
    )
    _validate_version(version)
    _validate_manifest(manifest)
    _validate_fault_status(status, action, boot_nonce)
    _validate_fault_report(report, action, boot_nonce, status=status)
    evidence = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": (
                f"{base.runner.EVIDENCE_KIND_PREFIX}-read-only-fault-salvage"
            ),
            "created_at": base.runner._now(),  # noqa: SLF001
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(action),
            "claim_file": str(claim_file.resolve()),
            "claim_file_sha256": claim_file_sha256,
            "claim_integrity": deepcopy(claim["integrity"]),
            "status": deepcopy(dict(status)),
            "terminal_report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "outcome": "fault_salvaged_read_only",
            "claim_state": "permanently_consumed",
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "hardware_mutation_requested": False,
        }
    )
    base.runner._write_new(output, evidence)  # noqa: SLF001
    return evidence


def _write_consumed_failure_evidence(
    *,
    output: Path,
    action: Mapping[str, Any],
    claim_file: Path,
    claim: Mapping[str, Any],
    boot_nonce: str,
    transcript: list[dict[str, Any]],
    outcome: str,
    error: str,
    terminal_report: Mapping[str, Any] | None = None,
    terminal_report_strictly_validated: bool = False,
) -> dict[str, Any]:
    try:
        claim_file_sha256 = hashlib.sha256(claim_file.read_bytes()).hexdigest()
    except OSError as error:
        raise base.runner.RecheckError(
            f"cannot bind consumed claim {claim_file}: {error}"
        ) from error
    evidence = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": f"{base.runner.EVIDENCE_KIND_PREFIX}-consumed-failure",
            "created_at": base.runner._now(),  # noqa: SLF001
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(dict(action)),
            "claim_file": str(claim_file.resolve()),
            "claim_file_sha256": claim_file_sha256,
            "claim_integrity": deepcopy(dict(claim["integrity"])),
            "terminal_report": (
                deepcopy(dict(terminal_report))
                if isinstance(terminal_report, Mapping)
                else None
            ),
            "terminal_report_strictly_validated": (
                terminal_report_strictly_validated
            ),
            "transcript": transcript,
            "network": {
                "get": sum(item["method"] == "GET" for item in transcript),
                "arm_post": sum(
                    item["method"] == "POST" and item["endpoint"] == "arm"
                    for item in transcript
                ),
                "execute_post": sum(
                    item["method"] == "POST" and item["endpoint"] == "execute"
                    for item in transcript
                ),
            },
            "outcome": outcome,
            "error": error,
            "claim_state": "permanently_consumed",
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(output, evidence)  # noqa: SLF001
    return evidence


def _record_untranscribed_request_error(
    transcript: list[dict[str, Any]],
    *,
    previous_length: int,
    endpoint: str,
    method: str,
    headers: Mapping[str, str] | None,
    error: Exception,
) -> None:
    """Record an attempted request only when the base helper recorded nothing."""

    if len(transcript) != previous_length:
        return
    transcript.append(
        {
            "method": method,
            "endpoint": endpoint,
            "path": base.runner.ENDPOINTS[endpoint],
            "headers": dict(sorted((headers or {}).items())),
            "status": None,
            "response": None,
            "observation_error": str(error),
        }
    )


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    requester: Any = None,
    poll_seconds: float = 2.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    """One mutation attempt that persists every observed terminal outcome."""

    if ordinal < 1 or ordinal > len(base.runner.ACTIONS):
        raise base.runner.RecheckError(
            f"ordinal must be between 1 and {len(base.runner.ACTIONS)}"
        )
    output = Path(output)
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    action = base.runner.ACTIONS[ordinal - 1]
    claims = Path(claims)
    claim_file = claims / f"{action['action_id']}.json"
    if claim_file.exists():
        raise base.runner.RecheckError(
            f"action {ordinal} was already permanently claimed"
        )
    if ordinal > 1 and not (
        claims / f"{base.runner.ACTION_IDS[ordinal - 2]}.json"
    ).is_file():
        raise base.runner.RecheckError(
            f"action {ordinal} requires the local prior-action claim"
        )

    requester = requester or base.runner._http_request  # noqa: SLF001
    origin = base.runner._origin(base_url)  # noqa: SLF001
    boot_nonce, transcript, _ = _preflight(
        origin, ordinal, expected_busy=1, requester=requester
    )
    claim = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": f"{base.runner.EVIDENCE_KIND_PREFIX}-permanent-claim",
            "created_at": base.runner._now(),  # noqa: SLF001
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(action),
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(claim_file, claim)  # noqa: SLF001

    arm_headers = base.runner._headers(  # noqa: SLF001
        action, boot_nonce, base.runner.ARM_INTENT
    )
    before_request = len(transcript)
    try:
        arm = base.runner._request(  # noqa: SLF001
            requester,
            transcript,
            origin,
            "arm",
            method="POST",
            headers=arm_headers,
        )
    except base.runner.RecheckError as error:
        _record_untranscribed_request_error(
            transcript,
            previous_length=before_request,
            endpoint="arm",
            method="POST",
            headers=arm_headers,
            error=error,
        )
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="arm_observation_error",
            error=str(error),
        )
        raise base.runner.RecheckError(
            "ARM observation failed; consumed-failure evidence written; "
            "action must not be retried"
        ) from error
    arm_nonce = arm.get("arm_nonce")
    if (
        arm.get("accepted") is not True
        or arm.get("armed") is not True
        or arm.get("action_id") != action["action_id"]
        or arm.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or base.runner._NONCE.fullmatch(arm_nonce) is None  # noqa: SLF001
    ):
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="arm_response_rejected",
            error="ARM response differs",
        )
        raise base.runner.RecheckError(
            "ARM response differs; consumed-failure evidence written; "
            "action must not be retried"
        )

    execute_headers = base.runner._headers(  # noqa: SLF001
        action, boot_nonce, base.runner.EXECUTE_INTENT
    )
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    before_request = len(transcript)
    try:
        execute = base.runner._request(  # noqa: SLF001
            requester,
            transcript,
            origin,
            "execute",
            method="POST",
            headers=execute_headers,
        )
    except base.runner.RecheckError as error:
        _record_untranscribed_request_error(
            transcript,
            previous_length=before_request,
            endpoint="execute",
            method="POST",
            headers=execute_headers,
            error=error,
        )
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="execute_observation_error",
            error=str(error),
        )
        raise base.runner.RecheckError(
            "EXECUTE observation failed; consumed-failure evidence written; "
            "action must not be retried"
        ) from error
    if (
        execute.get("accepted") is not True
        or execute.get("execute_consumed") is not True
        or execute.get("action_id") != action["action_id"]
        or execute.get("boot_nonce") != boot_nonce
    ):
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="execute_response_rejected",
            error="EXECUTE response differs",
        )
        raise base.runner.RecheckError(
            "EXECUTE response differs; consumed-failure evidence written; "
            "action must not be retried"
        )

    terminal_report: Mapping[str, Any] | None = None
    for _ in range(poll_count):
        if poll_seconds > 0:
            time.sleep(poll_seconds)
        before_request = len(transcript)
        try:
            report = base.runner._request(  # noqa: SLF001
                requester, transcript, origin, "report"
            )
        except base.runner.RecheckError as error:
            _record_untranscribed_request_error(
                transcript,
                previous_length=before_request,
                endpoint="report",
                method="GET",
                headers=None,
                error=error,
            )
            _write_consumed_failure_evidence(
                output=output,
                action=action,
                claim_file=claim_file,
                claim=claim,
                boot_nonce=boot_nonce,
                transcript=transcript,
                outcome="terminal_report_read_error",
                error=str(error),
            )
            raise base.runner.RecheckError(
                "terminal report read failed; consumed-failure evidence written; "
                "use GET-only salvage and never retry the action"
            ) from error
        if report.get("terminal_state") in ("COMPLETE", "FAULT"):
            terminal_report = report
            break

    if terminal_report is None:
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="terminal_report_not_observed",
            error="terminal report not observed within fixed poll budget",
        )
        raise base.runner.RecheckError(
            "terminal report not observed; consumed-failure evidence written; "
            "use GET-only salvage and never retry the action"
        )

    if terminal_report.get("terminal_state") == "FAULT":
        try:
            _validate_fault_report(terminal_report, action, boot_nonce)
        except base.runner.RecheckError as error:
            _write_consumed_failure_evidence(
                output=output,
                action=action,
                claim_file=claim_file,
                claim=claim,
                boot_nonce=boot_nonce,
                transcript=transcript,
                outcome="terminal_fault_rejected",
                error=str(error),
                terminal_report=terminal_report,
            )
            raise base.runner.RecheckError(
                "terminal FAULT failed strict validation; raw observation saved; "
                "action must not be retried"
            ) from error
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="terminal_fault",
            error=str(terminal_report["error"]),
            terminal_report=terminal_report,
            terminal_report_strictly_validated=True,
        )
        raise base.runner.RecheckError(
            "terminal FAULT saved; claim remains consumed and action must not be retried"
        )

    base.runner._identity(terminal_report, kind_suffix="report")  # noqa: SLF001
    if (
        terminal_report.get("boot_nonce") != boot_nonce
        or terminal_report.get("ordinal") != ordinal
        or terminal_report.get("action_id") != action["action_id"]
        or terminal_report.get("terminal_state") != "COMPLETE"
        or terminal_report.get("result") is not True
        or terminal_report.get("driver_called") is not True
        or terminal_report.get("driver_call_count_for_action") != 1
    ):
        _write_consumed_failure_evidence(
            output=output,
            action=action,
            claim_file=claim_file,
            claim=claim,
            boot_nonce=boot_nonce,
            transcript=transcript,
            outcome="terminal_complete_rejected",
            error="terminal COMPLETE identity or one-call result differs",
            terminal_report=terminal_report,
        )
        raise base.runner.RecheckError(
            "terminal COMPLETE failed validation; raw observation saved; "
            "action must not be retried"
        )

    result = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": f"{base.runner.EVIDENCE_KIND_PREFIX}-result",
            "created_at": base.runner._now(),  # noqa: SLF001
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
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
    base.runner._write_new(output, result)  # noqa: SLF001
    return result


_BASE_DESCRIBE = base.runner.describe


def describe() -> dict[str, Any]:
    value = _BASE_DESCRIBE()
    value["variant"] = REPORT["contract"]
    value["fixed_transport"] = {
        "spi_hz": 1_000_000,
        "runtime_lut": True,
        "profile_id": pack.PROFILE_ID,
        "ptlw_command": "0x83",
        "ptlw_endpoint": "inclusive",
        "ptlw_mode": 1,
        "cropped_dtm": True,
        "ptlw_writes_per_controller": 2,
        "post_pon_order": [
            "PTLW_CS1",
            "PTLW_CS2",
            "CDI_FF_BOTH",
            "BTST2",
            "DRF",
        ],
        "blocking_refresh_first_poll_floor_seconds": (
            base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS
        ),
    }
    value["required_external_anchor"] = {
        "kind": "FACTORY_OTP_CLEAN_WHITE",
        "established_by_firmware": False,
        "confirmation_flag": "--confirm-external-factory-white-anchor",
        "confirmation_semantics": (
            "CAMPAIGN_START_LINEAGE_ACKNOWLEDGEMENT_NOT_CURRENT_SCREEN_WHITE"
        ),
    }
    value["forbidden_operations"] = {
        "full_screen_refresh_action": True,
        "runtime_code7_baseline": True,
        "runtime_code7_recovery": True,
        "command_0x86": True,
        "cross_palette_switch": True,
        "mid_refresh_power_cut": True,
        "spi_frequency_sweep": True,
        "automatic_retry": True,
        "automatic_recovery": True,
        "automatic_chaining": True,
    }
    value["read_only_fault_salvage"] = {
        "command": "salvage-fault",
        "requires_existing_permanent_claim": True,
        "requires_same_boot_fault_status_and_report": True,
        "network": {"get": 4, "post": 0},
        "hardware_mutation_requested": False,
        "action_must_not_be_retried": True,
    }
    value["consumed_failure_persistence"] = {
        "terminal_fault": True,
        "terminal_report_read_error": True,
        "terminal_poll_exhaustion": True,
        "automatic_retry": False,
    }
    return value


base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner.run_once = run_once
base.runner.describe = describe


def _require_external_anchor(argv: Sequence[str] | None) -> list[str]:
    arguments = list(argv or [])
    if arguments and arguments[0] == "run":
        flag = "--confirm-external-factory-white-anchor"
        if flag not in arguments:
            raise SystemExit(f"run requires {flag}")
        arguments.remove(flag)
    return arguments


def _salvage_fault_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=(
            "mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_once.py "
            "salvage-fault"
        ),
        description=(
            "Read and seal an already-consumed same-boot FAULT using exactly "
            "four GETs and no POST."
        ),
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ordinal", required=True, type=int)
    parser.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv))
    try:
        value = salvage_fault_once(
            args.base_url,
            args.ordinal,
            claims=args.claims,
            output=args.output,
        )
    except base.runner.RecheckError as error:
        print(f"repeat-PTLW fault salvage error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv or [])
    if arguments and arguments[0] == "salvage-fault":
        return _salvage_fault_cli(arguments[1:])
    return base.main(_require_external_anchor(arguments))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
