#!/usr/bin/env python3
"""Fail-closed host for fresh Fullframe-vs-PTLW A/B V2.

This tool never flashes firmware, resets the ESP32, controls J2/power, retries,
recovers, or chains actions.  Every device-facing entry point first verifies
the sealed qualifier-V2 prerequisite bundle and the exact V2 BIN/ELF.  A live
fresh ordinal 1 admits raw BUSY=1 only.  A later raw BUSY=0 is accepted only
when both the device and local sealed evidence prove the immediately preceding
same-boot COMPLETE and strict safe finish.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_ptlw_fullframe_ab_v2_pack as pack,
)


_V1B_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_ptlw_fullframe_ab_v1_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_fullframe_ptlw_ab_v2_private_v1b_host", _V1B_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load sealed V1B host mechanics: {_V1B_PATH}")
v1b = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v1b)
endpoint = v1b.endpoint
v3 = v1b.v3
v2 = v1b.v2
v1 = v1b.v1
base = v1b.base

REPORT = pack.build_report()
_BASE_DIAGNOSE_J2_OFF = v1b._BASE_DIAGNOSE_J2_OFF  # noqa: SLF001
_STRICT_BASE_VALIDATE_READY_STATUS = (
    v1b._STRICT_BASE_VALIDATE_READY_STATUS  # noqa: SLF001
)
_BASE_PREFLIGHT = v1._BASE_PREFLIGHT  # noqa: SLF001
_BASE_SEAL = base.runner._seal  # noqa: SLF001
_BASE_WRITE_NEW = base.runner._write_new  # noqa: SLF001
_BASE_REQUEST = base.runner._request  # noqa: SLF001
_V3_BASE_VALIDATE_COMPLETE_REPORT = v3._validate_complete_report  # noqa: SLF001
_V1_BASE_VALIDATE_FAULT_STATUS = v1._validate_fault_status  # noqa: SLF001

for module in (v1b, endpoint, v3, v2, base):
    module.pack = pack
v1b.REPORT = REPORT
endpoint.REPORT = REPORT
v3.REPORT = REPORT
v2.REPORT = REPORT
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0

MAIN_BUILD_DIR = (
    REPO_ROOT
    / ".pio"
    / "build-runtime-lut-ptlw-fullframe-ab-v2"
    / "ec5_runtime_lut_ptlw_fullframe_ab_v2"
)
FIRMWARE_BIN = MAIN_BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = MAIN_BUILD_DIR / "firmware.elf"
# Frozen after the isolated reviewed clean build on 2026-08-26.
FIRMWARE_BIN_BYTES: int | None = 815_600
FIRMWARE_BIN_SHA256: str | None = (
    "0433f67810caf2248a27c3296fbd2ae5004e34b326e6ca87c32714de932863c4"
)
FIRMWARE_ELF_BYTES: int | None = 13_362_920
FIRMWARE_ELF_SHA256: str | None = (
    "17abc695304d36a5536a5041ac52adde92643181d360d4e76b1d2d0822e59b85"
)

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = (
    "EXPERIMENTAL_SPD1657_L535_FULLFRAME_VS_PTLW_AB_PER_ACTION_EXACT_"
    "DUAL_REV_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS"
)
base.runner.DEVICE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.EVIDENCE_KIND_PREFIX = pack.DEVICE_KIND_PREFIX
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
base.runner.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
v3.FIRMWARE_SHA256 = FIRMWARE_BIN_SHA256
v3.FIRMWARE_BYTES = FIRMWARE_BIN_BYTES
base.runner.ENDPOINTS = {
    name: f"{pack.ENDPOINT_BASE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "FULLFRAME_PTLW_AB_V2_ACTION"
)
base.runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_"
    "FULLFRAME_PTLW_AB_V2_ACTION_ONCE"
)
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_ptlw_fullframe_ab_v2_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_20260826_V2"
)

_PROFILE_SOURCE = "factory_otp_white_plus_legacy_complete_535_reference_active_global"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_PREREQUISITE: dict[str, str] | None = None
_ACTIVE_PRIOR: dict[str, Any] | None = None
_ACTIVE_ADMISSION_BUSY: int | None = None
_ACTIVE_CURRENT_ACTION: dict[str, Any] | None = None
_ACTIVE_CURRENT_CLAIM: Path | None = None
_ACTIVE_RESERVATION: dict[str, Any] | None = None
_DEVICE_ACCESS_GUARD = threading.Lock()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


@contextmanager
def _exclusive_device_access() -> Any:
    """Keep the module-level evidence context single-threaded and non-reentrant."""

    if not _DEVICE_ACCESS_GUARD.acquire(blocking=False):
        raise base.runner.RecheckError(
            "another V2 device-facing operation is active in this process"
        )
    try:
        yield
    finally:
        _DEVICE_ACCESS_GUARD.release()


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path))))


def _path_key(path: Path) -> str:
    try:
        resolved = _absolute_path(path).resolve(strict=False)
    except OSError as error:
        raise base.runner.RecheckError(f"cannot resolve evidence path {path}: {error}") from error
    return os.path.normcase(os.path.normpath(os.fspath(resolved)))


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = _absolute_path(path)
    components = [absolute, *absolute.parents]
    for component in components:
        try:
            if component.is_symlink():
                raise base.runner.RecheckError(
                    f"{label} contains a symlink component: {component}"
                )
        except OSError as error:
            raise base.runner.RecheckError(
                f"cannot inspect {label} path component {component}: {error}"
            ) from error


def _assert_distinct_paths(paths: Mapping[str, Path]) -> None:
    observed: dict[str, str] = {}
    for label, path in paths.items():
        _reject_symlink_components(path, label)
        key = _path_key(path)
        previous = observed.get(key)
        if previous is not None:
            raise base.runner.RecheckError(
                f"evidence path alias collision: {previous} and {label}"
            )
        observed[key] = label


def _reservation_path(output: Path) -> Path:
    output = Path(output)
    return output.with_name(f"{output.name}.reserve")


def _staged_path(output: Path) -> Path:
    output = Path(output)
    return output.with_name(f".{output.name}.v3-terminal-staging")


def _create_output_reservation(
    *,
    command: str,
    output: Path,
    ordinal: int | None,
    action: Mapping[str, Any] | None,
    claim_file: Path | None,
    prior_result: Path | None,
    prior_paths: Mapping[str, Path] | None = None,
    uses_staging: bool,
) -> dict[str, Any]:
    """O_EXCL-reserve every final output before the first device request."""

    output = _absolute_path(output)
    reservation_file = _absolute_path(_reservation_path(output))
    staged = _absolute_path(_staged_path(output)) if uses_staging else None
    path_set: dict[str, Path] = {
        "output": output,
        "output_reservation": reservation_file,
    }
    if staged is not None:
        path_set["terminal_staging"] = staged
    if claim_file is not None:
        path_set["current_claim"] = _absolute_path(claim_file)
    if prior_result is not None:
        path_set["prior_result_argument"] = _absolute_path(prior_result)
    if prior_paths is not None:
        path_set.update({key: _absolute_path(value) for key, value in prior_paths.items()})
    _assert_distinct_paths(path_set)

    for label in ("output", "output_reservation", "terminal_staging"):
        candidate = path_set.get(label)
        if candidate is not None and os.path.lexists(candidate):
            raise base.runner.RecheckError(
                f"refusing existing {label} path {candidate}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(output, "output")
    _reject_symlink_components(reservation_file, "output reservation")

    unsigned = {
        "schema_version": 1,
        "kind": f"{pack.DEVICE_KIND_PREFIX}-output-reservation",
        "created_at": base.runner._now(),  # noqa: SLF001
        "command": command,
        "firmware_sha256": FIRMWARE_BIN_SHA256,
        "contract_id": pack.CONTRACT_ID,
        "qualifier_v2_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        "ordinal": ordinal,
        "action": deepcopy(dict(action)) if isinstance(action, Mapping) else None,
        "output_file": str(output),
        "terminal_staging_file": str(staged) if staged is not None else None,
        "claim_file": (
            str(_absolute_path(claim_file)) if claim_file is not None else None
        ),
        "prior_result_argument": (
            str(_absolute_path(prior_result)) if prior_result is not None else None
        ),
        "state": "reserved_before_any_device_request",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    reservation = _BASE_SEAL(unsigned)
    try:
        _BASE_WRITE_NEW(reservation_file, reservation)
    except base.runner.RecheckError:
        raise
    except OSError as error:
        raise base.runner.RecheckError(
            f"cannot create output reservation {reservation_file}: {error}"
        ) from error
    payload_sha = _sha256(reservation_file)
    return {
        "reservation_file": str(reservation_file),
        "reservation_file_sha256": payload_sha,
        "reservation_integrity": deepcopy(reservation["integrity"]),
        "output_file": str(output),
        "terminal_staging_file": str(staged) if staged is not None else None,
        "command": command,
        "ordinal": ordinal,
    }


def artifact_binding_status() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, path, byte_count, wanted in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = _sha256(path) if present else None
        configured = (
            isinstance(byte_count, int)
            and not isinstance(byte_count, bool)
            and byte_count > 0
            and isinstance(wanted, str)
            and _SHA256_RE.fullmatch(wanted) is not None
        )
        result[key] = {
            "path": str(path),
            "configured": configured,
            "present": present,
            "verified": bool(
                configured
                and present
                and observed_bytes == byte_count
                and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
            "expected_bytes": byte_count,
            "expected_sha256": wanted,
        }
    return result


def _require_artifact_binding() -> None:
    if any(item["verified"] is not True for item in artifact_binding_status().values()):
        raise base.runner.RecheckError(
            "Fullframe/PTLW V2 BIN/ELF binding is pending or differs"
        )


def _bound_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise base.runner.RecheckError("prerequisite relative path is malformed")
    path = (REPO_ROOT / relative_path).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise base.runner.RecheckError(
            "prerequisite path escapes repository"
        ) from error
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"prerequisite file is absent: {path}")
    return path


def _read_bound_file(binding: Mapping[str, Any]) -> tuple[Path, bytes, str]:
    path = _bound_path(str(binding.get("relative_path", "")))
    payload = path.read_bytes()
    observed = _sha256_bytes(payload)
    if len(payload) != binding.get("bytes") or observed != binding.get("sha256"):
        raise base.runner.RecheckError(f"prerequisite file binding differs: {path}")
    return path, payload, observed


def _load_bound_json(
    name: str, binding: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    _, payload, observed = _read_bound_file(binding)
    if len(payload) > base.runner._MAX_JSON_BYTES:  # noqa: SLF001
        raise base.runner.RecheckError(f"prerequisite {name} JSON is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(
            f"prerequisite {name} is not UTF-8 JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"prerequisite {name} root differs")
    document = deepcopy(dict(value))
    integrity = document.pop("integrity", None)
    canonical_sha = _sha256_bytes(base.runner._canonical(document))  # noqa: SLF001
    expected_integrity = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": canonical_sha,
    }
    if integrity != expected_integrity:
        raise base.runner.RecheckError(f"prerequisite {name} canonical seal differs")
    if canonical_sha != binding.get("canonical_sha256"):
        raise base.runner.RecheckError(
            f"prerequisite {name} frozen canonical SHA differs"
        )
    document["integrity"] = integrity
    return document, observed


def _expect(value: Mapping[str, Any], exact: Mapping[str, Any], label: str) -> None:
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise base.runner.RecheckError(f"{label} {key} differs")


def _expect_revision_side(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"{label} revision side differs")
    _expect(
        value,
        {"stable": True, "nontrivial": True, "exact_010104": True},
        label,
    )
    for sample_name in ("sample1", "sample2"):
        sample = value.get(sample_name)
        if not isinstance(sample, Mapping) or sample != {
            "idle": True,
            "bytes": [1, 1, 4],
        }:
            raise base.runner.RecheckError(f"{label} {sample_name} differs")


def _validate_qualifier_readiness(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("qualifier readiness is absent")
    _expect(
        value,
        {
            "valid": True,
            "qualified": True,
            "entry_busy": 1,
            "final_busy": 1,
            "final_gpio": {
                "rst": 1,
                "cs1": 1,
                "cs2": 1,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
            "final_high_stable_ms": 50,
            "reset_count": 5,
            "revision_read_count": 4,
            "revision_command_trace": [112, 112, 112, 112],
            "all_revision_samples_exact_010104": True,
            "failure_stage": "none",
        },
        "qualifier readiness",
    )
    _expect_revision_side(value.get("cs1"), "qualifier CS1")
    _expect_revision_side(value.get("cs2"), "qualifier CS2")


def _validate_qualifier_probe(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("qualifier probe is absent")
    _expect(
        value,
        {
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
            "operation_id": 1,
            "pon_gate_entry": 1,
            "pof_gate_entry": 1,
            "pon_busy_seen": True,
            "pon_idle_completed": True,
            "pof_busy_seen": True,
            "pof_idle_completed": True,
            "pon_ms": 180,
            "pof_ms": 210,
            "post_psr_command_sent": True,
            "post_psr_payload_hex": "4f6e",
            "wire_event_count": 58,
            "wire_fnv1a": 3_240_907_477,
            "command_counts": {
                "command_0x86": 0,
                "drf": 0,
                "dtm": 0,
                "lut": 0,
                "pof": 1,
                "pon": 1,
                "ptlw": 0,
                "visible_refresh_requests": 0,
            },
            "forbidden_commands": {
                "command_0x86": False,
                "drf": False,
                "dtm": False,
                "lut": False,
                "ptlw": False,
            },
        },
        "qualifier probe",
    )
    safe_finish = value.get("safe_finish")
    if not isinstance(safe_finish, Mapping):
        raise base.runner.RecheckError("qualifier safe finish is absent")
    _expect(
        safe_finish,
        {
            "busy_before_pins_low": 1,
            "busy_after_pins_low": 1,
            "busy_after_5ms": 1,
            "final_gpio": {
                "busy": 1,
                "rst": 0,
                "cs1": 0,
                "cs2": 0,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        },
        "qualifier safe finish",
    )


def qualifier_prerequisite_status() -> dict[str, Any]:
    prerequisite = pack.QUALIFIER_V2_PREREQUISITE
    canonical_bundle = hashlib.sha256(
        pack.identity.canonical(prerequisite)
    ).hexdigest()
    if canonical_bundle != pack.QUALIFIER_V2_BUNDLE_ID:
        raise base.runner.RecheckError("qualifier prerequisite bundle ID differs")

    observed: dict[str, str] = {}
    for artifact_name in ("bin", "elf"):
        _, _, observed_sha = _read_bound_file(
            prerequisite["firmware"][artifact_name]
        )
        observed[f"qualifier_firmware_{artifact_name}"] = observed_sha

    records: dict[str, dict[str, Any]] = {}
    for name, binding in prerequisite["evidence"].items():
        records[name], observed[name] = _load_bound_json(name, binding)

    identity_exact = prerequisite["identity"]
    boot_nonce = prerequisite["boot_nonce"]
    qualification_nonce = prerequisite["qualification_nonce"]
    diagnostic = records["diagnostic"]
    result = records["result"]
    claim = records["claim"]
    attempt = records["attempt"]
    reservation = records["reservation"]

    _expect(
        diagnostic,
        {
            "kind": "mf1750-power-qualifier-pon-pof-no-drf-v2-j2-off-diagnostic",
            "boot_nonce": boot_nonce,
            "firmware_sha256": prerequisite["firmware"]["bin"]["sha256"],
            "j2_confirmed_off": True,
            "network": {"get": 4, "post": 0},
            "probe_driver_calls": 0,
            "visible_refresh_requests": 0,
        },
        "qualifier diagnostic",
    )
    diagnostic_transcript = diagnostic.get("transcript")
    if not isinstance(diagnostic_transcript, list) or len(diagnostic_transcript) != 4:
        raise base.runner.RecheckError("qualifier diagnostic transcript differs")
    diagnostic_status = diagnostic_transcript[2].get("response")
    if (
        not isinstance(diagnostic_status, Mapping)
        or diagnostic_status.get("boot_nonce") != boot_nonce
        or not isinstance(diagnostic_status.get("gpio"), Mapping)
        or diagnostic_status["gpio"].get("busy") != 0
        or diagnostic_status.get("qualifier_call_count") != 0
        or diagnostic_status.get("probe_call_count") != 0
        or diagnostic_status.get("total_driver_call_count") != 0
    ):
        raise base.runner.RecheckError("qualifier J2-OFF status differs")

    qualifier_action = {
        "ordinal": 1,
        "descriptor_id": identity_exact["descriptor_id"],
        "action_id": identity_exact["action_id"],
        "prior_static_action_id": (
            "8cd8b3794bed065ae9cd64a002957e162673f17706ea2464e9397035389f58a4"
        ),
        "role": "PON_POF_NO_DRF_POWER_PATH_PROBE",
        "round": 1,
        "branch": "PER_SAMPLE_RESET_EXACT_REV_READINESS_THEN_PON_THEN_POF_NO_DRF",
    }
    _expect(
        result,
        {
            "kind": "mf1750-power-qualifier-pon-pof-no-drf-v2-result",
            "boot_nonce": boot_nonce,
            "qualification_nonce": qualification_nonce,
            "firmware_sha256": prerequisite["firmware"]["bin"]["sha256"],
            "action": qualifier_action,
            "network": {"get": 9, "qualify_post": 1, "arm_post": 1, "execute_post": 1},
            "outcome": "complete_pass",
            "terminal_mismatches": [],
            "visible_refresh_requests": 0,
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "qualifier result",
    )
    result_transcript = result.get("transcript")
    if not isinstance(result_transcript, list) or len(result_transcript) < 12:
        raise base.runner.RecheckError("qualifier result transcript differs")
    initial_status = result_transcript[2].get("response")
    if (
        not isinstance(initial_status, Mapping)
        or initial_status.get("boot_nonce") != boot_nonce
        or not isinstance(initial_status.get("gpio"), Mapping)
        or initial_status["gpio"].get("busy") != 1
    ):
        raise base.runner.RecheckError("qualifier live initial BUSY differs")

    terminal = result.get("terminal_report")
    if not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("qualifier terminal report is absent")
    _expect(
        terminal,
        {
            "build_tag": identity_exact["build_tag"],
            "test_id": identity_exact["test_id"],
            "campaign_id": identity_exact["campaign_id"],
            "descriptor_id": identity_exact["descriptor_id"],
            "action_id": identity_exact["action_id"],
            "contract_id": identity_exact["contract_id"],
            "boot_nonce": boot_nonce,
            "qualification_nonce": qualification_nonce,
            "valid": True,
            "terminal_state": "COMPLETE",
            "result": True,
            "phase": 5,
            "phase_name": "COMPLETE",
            "next_ordinal": 2,
            "campaign_complete": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": 1,
            "qualifier_call_count": 1,
            "probe_call_count": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "qualifier terminal",
    )
    _validate_qualifier_readiness(terminal.get("readiness"))
    _validate_qualifier_probe(terminal.get("probe"))
    if terminal.get("driver") != terminal.get("probe"):
        raise base.runner.RecheckError("qualifier driver/probe evidence differs")

    for name, value, state, kind in (
        (
            "claim",
            claim,
            "claimed_after_qualification_before_arm",
            "mf1750-power-qualifier-pon-pof-no-drf-v2-permanent-claim",
        ),
        (
            "attempt",
            attempt,
            "reserved_before_qualify_post",
            "mf1750-power-qualifier-pon-pof-no-drf-v2-qualification-attempt",
        ),
    ):
        _expect(
            value,
            {
                "kind": kind,
                "boot_nonce": boot_nonce,
                "firmware_sha256": prerequisite["firmware"]["bin"]["sha256"],
                "action": qualifier_action,
                "initial_busy": 1,
                "state": state,
            },
            f"qualifier {name}",
        )
    _expect(
        claim,
        {
            "qualification_nonce": qualification_nonce,
            "qualified_busy": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "qualifier claim",
    )
    if attempt.get("no_automatic_retry") is not True:
        raise base.runner.RecheckError("qualifier attempt retry contract differs")
    _expect(
        reservation,
        {
            "kind": "mf1750-power-qualifier-pon-pof-no-drf-v2-output-reservation",
            "boot_nonce": boot_nonce,
        },
        "qualifier output reservation",
    )
    return {
        "verified": True,
        "bundle_id": canonical_bundle,
        "boot_nonce": boot_nonce,
        "qualification_nonce": qualification_nonce,
        "observed_sha256": dict(sorted(observed.items())),
    }


def _require_prerequisite_evidence() -> dict[str, str]:
    status = qualifier_prerequisite_status()
    if status.get("verified") is not True:
        raise base.runner.RecheckError("qualifier V2 prerequisite is not verified")
    return deepcopy(status["observed_sha256"])


def _active_reservation_binding() -> dict[str, Any]:
    if _ACTIVE_RESERVATION is None:
        raise base.runner.RecheckError("V2 evidence has no output reservation")
    path_value = _ACTIVE_RESERVATION.get("reservation_file")
    if not isinstance(path_value, str):
        raise base.runner.RecheckError("V2 output reservation path differs")
    record, file_sha = _load_sealed_record(Path(path_value), "output reservation")
    if file_sha != _ACTIVE_RESERVATION.get("reservation_file_sha256"):
        raise base.runner.RecheckError("V2 output reservation bytes changed")
    if record.get("integrity") != _ACTIVE_RESERVATION.get("reservation_integrity"):
        raise base.runner.RecheckError("V2 output reservation seal changed")
    _expect(
        record,
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-output-reservation",
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "contract_id": pack.CONTRACT_ID,
            "qualifier_v2_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
            "output_file": _ACTIVE_RESERVATION.get("output_file"),
            "terminal_staging_file": _ACTIVE_RESERVATION.get(
                "terminal_staging_file"
            ),
            "command": _ACTIVE_RESERVATION.get("command"),
            "ordinal": _ACTIVE_RESERVATION.get("ordinal"),
            "state": "reserved_before_any_device_request",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "output reservation",
    )
    return {
        "reservation_file": path_value,
        "reservation_file_sha256": file_sha,
        "reservation_integrity": deepcopy(record["integrity"]),
        "output_file": record["output_file"],
        "terminal_staging_file": record["terminal_staging_file"],
        "command": record["command"],
        "ordinal": record["ordinal"],
    }


def _current_claim_binding() -> dict[str, Any]:
    if _ACTIVE_CURRENT_CLAIM is None or _ACTIVE_CURRENT_ACTION is None:
        raise base.runner.RecheckError("V2 current claim context is absent")
    claim, file_sha = _load_sealed_record(_ACTIVE_CURRENT_CLAIM, "current claim")
    _validate_prerequisite_binding_fields(claim, "current claim")
    _expect(
        claim,
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-permanent-claim",
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "action": _ACTIVE_CURRENT_ACTION,
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "current claim",
    )
    return {
        "claim_file": str(_absolute_path(_ACTIVE_CURRENT_CLAIM)),
        "claim_file_sha256": file_sha,
        "claim_integrity": deepcopy(claim["integrity"]),
    }


def _validate_current_claim_reference(value: Mapping[str, Any], label: str) -> None:
    binding = _current_claim_binding()
    if any(value.get(key) != wanted for key, wanted in binding.items()):
        raise base.runner.RecheckError(f"{label} current claim binding differs")


def _seal_with_prerequisite(value: Mapping[str, Any]) -> dict[str, Any]:
    document = deepcopy(dict(value))
    kind = document.get("kind")
    if isinstance(kind, str) and kind.startswith(pack.DEVICE_KIND_PREFIX):
        if _ACTIVE_PREREQUISITE is None:
            raise base.runner.RecheckError(
                "V2 evidence cannot be sealed outside verified prerequisite context"
            )
        document["qualifier_v2_prerequisite_bundle_id"] = (
            pack.QUALIFIER_V2_BUNDLE_ID
        )
        document["qualifier_v2_observed_sha256"] = deepcopy(
            _ACTIVE_PREREQUISITE
        )
        if _ACTIVE_ADMISSION_BUSY not in (0, 1):
            raise base.runner.RecheckError(
                "V2 evidence has no exact admission raw BUSY binding"
            )
        document["admission_raw_busy"] = _ACTIVE_ADMISSION_BUSY
        document["output_reservation"] = _active_reservation_binding()
        if _ACTIVE_PRIOR is not None:
            document["prior_local_evidence"] = {
                key: deepcopy(_ACTIVE_PRIOR[key])
                for key in (
                    "boot_nonce",
                    "prior_result",
                    "prior_result_sha256",
                    "prior_claim",
                    "prior_claim_sha256",
                    "admission_raw_busy",
                )
            }
        if (
            _ACTIVE_CURRENT_CLAIM is not None
            and kind != f"{pack.DEVICE_KIND_PREFIX}-permanent-claim"
        ):
            document.update(_current_claim_binding())
            terminal = document.get("terminal_report")
            readiness = (
                terminal.get("readiness") if isinstance(terminal, Mapping) else None
            )
            entry_busy = (
                readiness.get("entry_busy")
                if isinstance(readiness, Mapping) and readiness.get("valid") is True
                else None
            )
            if entry_busy not in (None, 0, 1):
                raise base.runner.RecheckError(
                    "V2 evidence qualifier entry BUSY differs"
                )
            document["qualification_entry_busy"] = entry_busy
    return _BASE_SEAL(document)


base.runner._seal = _seal_with_prerequisite  # noqa: SLF001


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "full_screen_global_refresh",
        "factory_otp_white_actions",
        "ptlw_fullframe_ab_probe",
        "runtime_code7_full_dtm_prestage",
        "busy_qualified_arm_execute_dispatch",
    )
    required_false = (
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "runtime_treatment_action_stage_cdi",
        "runtime_treatment_action_stage_btst2",
        "runtime_treatment_repeat_ptlw_after_pon_busy",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("V2 capability contract differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("V2 forbidden capability differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    _expect(
        value,
        {
            "layout_id": pack.VARIANT_KEY,
            "profile_source": _PROFILE_SOURCE,
            "action_count": 5,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
            "automatic_execute": False,
            "automatic_chaining": False,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "electrical_parameter_write": False,
            "dither": False,
            "spatial_mixing": False,
            "retry": False,
            "recovery": False,
            "per_action_readiness_qualification_required": True,
            "three_gate_busy_admission_evidence_required": True,
            "qualifier_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        },
        "V2 version",
    )
    nvs = value.get("nvs_contract")
    if not isinstance(nvs, Mapping):
        raise base.runner.RecheckError("V2 version NVS contract is absent")
    _expect(
        nvs,
        {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 6,
            "initial_key_present": False,
            "initial_value": 1,
            "initial_next_ordinal": 1,
        },
        "V2 version NVS",
    )
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


def _expected_qualification_contract() -> dict[str, Any]:
    return {
        "required_for_ordinals": [1, 2, 3, 4, 5],
        "prerequisite_evidence_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
        "timing": (
            "AFTER_PERSISTENT_CONSUMED_BEFORE_ANY_ACTION_INIT_LUT_DTM_PTLW_PON"
        ),
        "single_call_per_action": True,
        "reset_count": 5,
        "success_reset_count_exact": 5,
        "failure_reset_count_may_be_partial": True,
        "reset_before_each_revision_sample": True,
        "revision_order": [
            "CS1_SAMPLE1",
            "CS1_SAMPLE2",
            "CS2_SAMPLE1",
            "CS2_SAMPLE2",
        ],
        "revision_command": 112,
        "revision_read_count": 4,
        "expected_revision_bytes": [1, 1, 4],
        "all_four_samples_exact_required": True,
        "final_posture_reset": True,
        "qualified_busy_level": 1,
        "qualified_busy_stable_ms": 50,
        "qualified_gpio": {
            "rst": 1,
            "cs1": 1,
            "cs2": 1,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "qualification_command_counts": {
            "rev": 4,
            "pon": 0,
            "pof": 0,
            "drf": 0,
            "dtm": 0,
            "lut": 0,
            "ptlw": 0,
            "command_0x86": 0,
            "visible_refresh_requests": 0,
        },
        "failure_semantics": "CONSUMED_THEN_FAULT_NO_RETRY_NO_DRIVER_CALL",
        "failure_action_stage_command_counts_all_zero": True,
        "evidence_counters_separate_from_driver_counters": True,
    }


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    _expect(
        value,
        {
            "layout_id": pack.VARIANT_KEY,
            "profile_source": _PROFILE_SOURCE,
            "actions": list(base.runner.ACTIONS),
            "action_count": 5,
            "one_driver_call_per_action": True,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "runtime_lut_write": True,
            "automatic_chaining": False,
            "startup_refresh": False,
            "retry": False,
            "recovery": False,
            "per_action_readiness_qualification": (
                _expected_qualification_contract()
            ),
            "busy_admission_contract": pack.BUSY_ADMISSION_CONTRACT,
        },
        "V2 manifest",
    )
    layout = value.get("history_layout")
    if not isinstance(layout, Mapping):
        raise base.runner.RecheckError("V2 history layout is absent")
    layout_exact = {
        "factory_otp_anchor_ordinal": 1,
        "factory_otp_reset_ordinal": 3,
        "factory_otp_recovery_ordinal": 5,
        "runtime_transport_codes": [5, 7],
        "ptlw_command": 0x83,
        "ptlw_payload_bytes": 9,
        "ptlw_mode": 1,
        "ptlw_payload_hex": "00b0014f00f0016701",
        "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
        "window": {
            "x": 176,
            "y": 240,
            "width": 160,
            "height": 120,
            "cs1_code": 5,
            "cs2_code": 5,
        },
        "runtime_code7_full_dtm_prestage": True,
        "runtime_code7_prestage_no_refresh": True,
        "runtime_code7_prestage_bytes_per_controller": 153_600,
        "runtime_code7_prestage_sha256": pack.PRELOAD_DTM_SHA256,
        "treatment_a": {
            "ordinal": 2,
            "ptlw": False,
            "dtm_transport": "FULL_CONTROLLER_COMPOSITE_NO_PTLW",
            "target_dtm_bytes_per_controller": 153_600,
            "target_dtm_sha256": pack.FULL_COMPOSITE_DTM_SHA256,
            "combined_dtm_bytes_per_controller": 307_200,
            "combined_dtm_sha256": pack.TREATMENT_A_COMBINED_DTM_SHA256,
        },
        "treatment_b": {
            "ordinal": 4,
            "ptlw": True,
            "ptlw_writes_per_controller": 1,
            "dtm_transport": "INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW",
            "target_dtm_bytes_per_controller": 9_600,
            "target_dtm_sha256": pack.CROPPED_DTM_SHA256,
            "combined_dtm_bytes_per_controller": 163_200,
            "combined_dtm_sha256": pack.TREATMENT_B_COMBINED_DTM_SHA256,
        },
        "same_final_controller_sram": True,
        "same_logical_frame": True,
        "logical_frame_sha256": pack.LOGICAL_FRAME_SHA256,
        "logical_frame_histogram": [0, 0, 0, 0, 0, 38_400, 0, 576_000],
        "common_refresh_sequence": [
            "PON_BUSY_COMPLETE_60S_GATE",
            "DRF_00_BUSY_COMPLETE_60S_GATE",
            "POF_00_BUSY_COMPLETE_60S_GATE",
        ],
        "fresh_white_before_each_treatment": True,
        "runtime_treatment_action_stage_cdi": False,
        "runtime_treatment_action_stage_btst2": False,
        "runtime_treatment_repeat_ptlw_after_pon_busy": False,
        "command_0x86": False,
        "extra_dtm_prefix_or_suffix_byte": False,
        "busy_idle_level_required": 1,
        "ordinal_1_raw_levels_accepted": [1],
        "fresh_low_admission_forbidden": True,
        "j2_off_raw0_allowed_only_on_read_only_get_diagnostic": True,
        "later_ordinal_raw_levels_accepted": [0, 1],
        "late_low_is_never_treated_as_idle": True,
        "late_low_requires_same_boot_prior_complete": True,
        "late_low_requires_prior_safe_finish_high": True,
        "late_low_requires_ram_only_firmware_eligibility": True,
        "late_pof_sleep_low_eligible_boot_default": False,
        "late_pof_sleep_low_eligible_consumed_before_qualification": True,
        "per_action_revision_qualifier_required": True,
        "unqualified_busy_zero_accepted": False,
    }
    for key, wanted in layout_exact.items():
        if layout.get(key) != wanted:
            raise base.runner.RecheckError(f"V2 history layout {key} differs")
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
            raise base.runner.RecheckError(f"V2 LUT profile {key} differs")
    _validate_capabilities(value)
    v2._validate_baseline(value)  # noqa: SLF001


_UNCAPTURED_BUSY_GATE = deepcopy(
    pack.BUSY_ADMISSION_CONTRACT["uncaptured_snapshot"]
)


def _validate_captured_busy_gate(value: Any, ordinal: int, label: str) -> int:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError(f"{label} BUSY gate evidence is absent")
    raw_busy = value.get("raw_busy")
    if raw_busy not in (0, 1):
        raise base.runner.RecheckError(f"{label} raw BUSY differs")
    if ordinal == 1:
        expected = {
            "captured": True,
            "raw_busy": 1,
            "allowed": True,
            "raw1_direct": True,
            "raw0_same_boot_prior_complete_ram_eligibility_used": False,
            "late_pof_sleep_low_eligible_before_gate": False,
        }
    elif raw_busy == 1:
        expected = {
            "captured": True,
            "raw_busy": 1,
            "allowed": True,
            "raw1_direct": True,
            "raw0_same_boot_prior_complete_ram_eligibility_used": False,
            "late_pof_sleep_low_eligible_before_gate": True,
        }
    else:
        expected = {
            "captured": True,
            "raw_busy": 0,
            "allowed": True,
            "raw1_direct": False,
            "raw0_same_boot_prior_complete_ram_eligibility_used": True,
            "late_pof_sleep_low_eligible_before_gate": True,
        }
    if dict(value) != expected:
        raise base.runner.RecheckError(f"{label} BUSY gate evidence differs")
    return int(raw_busy)


def _validate_busy_admission(
    value: Any,
    ordinal: int,
    *,
    captured_through: str,
) -> dict[str, int]:
    if not isinstance(value, Mapping) or value.get("ordinal") != ordinal:
        raise base.runner.RecheckError("BUSY admission ordinal differs")
    gate_names = ("arm", "execute", "dispatch")
    if captured_through not in gate_names:
        raise base.runner.RecheckError("BUSY admission capture stage differs")
    last_index = gate_names.index(captured_through)
    observed: dict[str, int] = {}
    for index, name in enumerate(gate_names):
        gate = value.get(name)
        if index <= last_index:
            observed[name] = _validate_captured_busy_gate(
                gate, ordinal, f"{name.upper()}"
            )
        elif gate != _UNCAPTURED_BUSY_GATE:
            raise base.runner.RecheckError(
                f"uncaptured {name.upper()} BUSY gate evidence differs"
            )
    return observed


def _validate_zero_busy_admission(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("fresh BUSY admission evidence is absent")
    if value.get("ordinal") != 0 or any(
        value.get(name) != _UNCAPTURED_BUSY_GATE
        for name in ("arm", "execute", "dispatch")
    ):
        raise base.runner.RecheckError("fresh BUSY admission evidence differs")


def _request_with_busy_evidence(
    requester: Any,
    transcript: list[dict[str, Any]],
    base_url: str,
    endpoint_name: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: float = 12.0,
) -> Mapping[str, Any]:
    value = _BASE_REQUEST(
        requester,
        transcript,
        base_url,
        endpoint_name,
        method=method,
        headers=headers,
        timeout=timeout,
    )
    if method == "POST" and endpoint_name in ("arm", "execute"):
        if _ACTIVE_CURRENT_ACTION is None:
            raise base.runner.RecheckError(
                "mutation response has no active V2 action context"
            )
        _validate_busy_admission(
            value.get("busy_admission"),
            int(_ACTIVE_CURRENT_ACTION["ordinal"]),
            captured_through="arm" if endpoint_name == "arm" else "execute",
        )
    return value


def _validate_zero_readiness(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("fresh readiness is absent")
    _expect(
        value,
        {
            "valid": False,
            "qualified": False,
            "operation_id": 0,
            "ordinal": 0,
            "reset_count": 0,
            "revision_read_count": 0,
            "revision_command_trace": [0, 0, 0, 0],
            "failure_stage": "none",
        },
        "fresh readiness",
    )


def _validate_action_readiness(value: Any, ordinal: int) -> int:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("per-action readiness is absent")
    entry_busy = value.get("entry_busy")
    if entry_busy not in (0, 1):
        raise base.runner.RecheckError(
            "per-action qualifier entry BUSY is outside its observed domain"
        )
    _expect(
        value,
        {
            "valid": True,
            "qualified": True,
            "operation_id": ordinal,
            "ordinal": ordinal,
            "final_busy": 1,
            "final_gpio": {
                "rst": 1,
                "cs1": 1,
                "cs2": 1,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
            "final_high_stable_ms": 50,
            "reset_count": 5,
            "revision_read_count": 4,
            "revision_command_trace": [112, 112, 112, 112],
            "all_revision_samples_exact_010104": True,
            "failure_stage": "none",
        },
        "per-action readiness",
    )
    _expect_revision_side(value.get("cs1"), "per-action CS1")
    _expect_revision_side(value.get("cs2"), "per-action CS2")
    return int(entry_busy)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if not 1 <= ordinal <= len(base.runner.ACTIONS):
        raise base.runner.RecheckError("V2 runnable ordinal differs")
    global _ACTIVE_ADMISSION_BUSY
    observed_busy = value.get("busy")
    if expected_busy == 0:
        if ordinal != 1 or observed_busy != 0:
            raise base.runner.RecheckError(
                "J2-OFF raw BUSY=0 diagnostic is fresh ordinal 1 only"
            )
        accepted_busy = 0
    elif ordinal == 1:
        if expected_busy != 1 or observed_busy != 1:
            raise base.runner.RecheckError("fresh ordinal 1 requires raw BUSY=1")
        accepted_busy = 1
    else:
        if expected_busy != 1 or observed_busy not in (0, 1):
            raise base.runner.RecheckError("later ordinal BUSY differs")
        if _ACTIVE_PRIOR is None:
            raise base.runner.RecheckError(
                "later ordinal requires a sealed local prior COMPLETE"
            )
        accepted_busy = int(observed_busy)

    _ACTIVE_ADMISSION_BUSY = accepted_busy

    nonce = _STRICT_BASE_VALIDATE_READY_STATUS(
        value, ordinal, expected_busy=accepted_busy
    )
    expected_count = ordinal - 1
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
        "total_qualification_call_count",
    ):
        if value.get(key) != expected_count:
            raise base.runner.RecheckError(f"V2 ready status {key} differs")
    if value.get("qualification_pending") is not False:
        raise base.runner.RecheckError("V2 qualification_pending differs")
    if value.get("qualification_running") is not False:
        raise base.runner.RecheckError("V2 qualification_running differs")
    if ordinal == 1:
        if (
            value.get("qualification_call_count_for_action") != 0
            or value.get("late_pof_sleep_low_eligible") is not False
        ):
            raise base.runner.RecheckError("V2 fresh qualification state differs")
        _validate_zero_readiness(value.get("readiness"))
        _validate_zero_busy_admission(value.get("busy_admission"))
    else:
        if (
            value.get("qualification_call_count_for_action") != 1
            or value.get("late_pof_sleep_low_eligible") is not True
        ):
            raise base.runner.RecheckError("V2 prior qualification state differs")
        prior_admission = (
            _ACTIVE_PRIOR.get("admission_raw_busy")
            if isinstance(_ACTIVE_PRIOR, Mapping)
            else None
        )
        if prior_admission not in (0, 1):
            raise base.runner.RecheckError("local prior admission BUSY differs")
        _validate_action_readiness(value.get("readiness"), ordinal - 1)
        _validate_busy_admission(
            value.get("busy_admission"),
            ordinal - 1,
            captured_through="dispatch",
        )
        if observed_busy == 0 and value.get("late_pof_sleep_low_eligible") is not True:
            raise base.runner.RecheckError("V2 raw-low RAM eligibility is absent")
    return nonce


def _expected_action_stage_counts(ordinal: int) -> dict[str, int]:
    if ordinal in (1, 3, 5):
        dtm_bytes, lut_bytes, ptlw_writes = 307_200, 0, 0
    elif ordinal == 2:
        dtm_bytes, lut_bytes, ptlw_writes = 614_400, 2_478, 0
    elif ordinal == 4:
        dtm_bytes, lut_bytes, ptlw_writes = 326_400, 2_478, 2
    else:
        raise base.runner.RecheckError("V2 action-stage ordinal differs")
    return {
        "pon": 1,
        "pof": 1,
        "drf": 1,
        "dtm_bytes": dtm_bytes,
        "lut_bytes": lut_bytes,
        "ptlw_writes": ptlw_writes,
        "command_0x86": 0,
        "visible_refresh_requests": 1,
    }


def _validate_complete_report(
    value: Mapping[str, Any],
    ordinal: int,
    boot_nonce: str,
    *,
    admission_raw_busy: int | None = None,
) -> None:
    admitted = _ACTIVE_ADMISSION_BUSY if admission_raw_busy is None else admission_raw_busy
    if admitted not in (0, 1) or (ordinal == 1 and admitted != 1):
        raise base.runner.RecheckError("V2 COMPLETE admission raw BUSY differs")
    _V3_BASE_VALIDATE_COMPLETE_REPORT(value, ordinal, boot_nonce)
    _expect(
        value,
        {
            "round": base.runner.ACTIONS[ordinal - 1]["round"],
            "job_id": ordinal,
            "qualification_called": True,
            "qualification_call_count_for_action": 1,
            "total_qualification_call_count": ordinal,
            "late_pof_sleep_low_eligible": ordinal < len(base.runner.ACTIONS),
            "action_stage_command_counts": _expected_action_stage_counts(ordinal),
        },
        "V2 COMPLETE",
    )
    _validate_action_readiness(value.get("readiness"), ordinal)
    _validate_busy_admission(
        value.get("busy_admission"), ordinal, captured_through="dispatch"
    )


def _validate_fresh_no_execute_report(
    value: Mapping[str, Any], boot_nonce: str
) -> None:
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    _expect(
        value,
        {
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
            "qualification_call_count_for_action": 0,
            "total_qualification_call_count": 0,
            "late_pof_sleep_low_eligible": False,
            "phase": 0,
            "next_ordinal": 1,
            "no_retry": True,
            "no_recovery": True,
        },
        "V2 fresh report",
    )
    _validate_zero_readiness(value.get("readiness"))
    _validate_zero_busy_admission(value.get("busy_admission"))
    if "driver" in value or "action_stage_command_counts" in value:
        raise base.runner.RecheckError("V2 fresh report has action evidence")


def _load_sealed_record(path: Path, label: str) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"{label} is absent or is a symlink: {path}")
    payload = path.read_bytes()
    if len(payload) > base.runner._MAX_JSON_BYTES:  # noqa: SLF001
        raise base.runner.RecheckError(f"{label} is too large")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(parsed, Mapping):
        raise base.runner.RecheckError(f"{label} root differs")
    document = deepcopy(dict(parsed))
    integrity = document.pop("integrity", None)
    expected = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha256_bytes(base.runner._canonical(document)),  # noqa: SLF001
    }
    if integrity != expected:
        raise base.runner.RecheckError(f"{label} canonical seal differs")
    document["integrity"] = integrity
    return document, _sha256_bytes(payload)


def _validate_reservation_reference(
    value: Mapping[str, Any], label: str
) -> dict[str, Any]:
    binding = value.get("output_reservation")
    if not isinstance(binding, Mapping):
        raise base.runner.RecheckError(f"{label} output reservation is absent")
    allowed = {
        "reservation_file",
        "reservation_file_sha256",
        "reservation_integrity",
        "output_file",
        "terminal_staging_file",
        "command",
        "ordinal",
    }
    if set(binding) != allowed:
        raise base.runner.RecheckError(f"{label} output reservation fields differ")
    path_value = binding.get("reservation_file")
    if not isinstance(path_value, str):
        raise base.runner.RecheckError(f"{label} output reservation path differs")
    reservation, file_sha = _load_sealed_record(
        Path(path_value), f"{label} output reservation"
    )
    if file_sha != binding.get("reservation_file_sha256"):
        raise base.runner.RecheckError(f"{label} reservation file SHA differs")
    if reservation.get("integrity") != binding.get("reservation_integrity"):
        raise base.runner.RecheckError(f"{label} reservation integrity differs")
    _expect(
        reservation,
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-output-reservation",
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "contract_id": pack.CONTRACT_ID,
            "qualifier_v2_prerequisite_bundle_id": pack.QUALIFIER_V2_BUNDLE_ID,
            "output_file": binding.get("output_file"),
            "terminal_staging_file": binding.get("terminal_staging_file"),
            "command": binding.get("command"),
            "ordinal": binding.get("ordinal"),
            "state": "reserved_before_any_device_request",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        f"{label} output reservation",
    )
    return deepcopy(dict(binding))


def _write_new_bound(path: Path, value: Mapping[str, Any]) -> None:
    """Permit campaign writes only to paths protected by the active reservation."""

    if _ACTIVE_RESERVATION is None:
        raise base.runner.RecheckError(
            "V2 evidence write attempted without an active output reservation"
        )
    allowed_paths = {
        _path_key(Path(_ACTIVE_RESERVATION["output_file"])),
    }
    staged_value = _ACTIVE_RESERVATION.get("terminal_staging_file")
    if isinstance(staged_value, str):
        allowed_paths.add(_path_key(Path(staged_value)))
    if _ACTIVE_CURRENT_CLAIM is not None:
        allowed_paths.add(_path_key(_ACTIVE_CURRENT_CLAIM))
    if _path_key(path) not in allowed_paths:
        raise base.runner.RecheckError(f"unreserved V2 evidence write path {path}")
    active_binding = _active_reservation_binding()
    if value.get("output_reservation") != active_binding:
        raise base.runner.RecheckError("V2 evidence reservation binding differs")
    if (
        _ACTIVE_CURRENT_CLAIM is not None
        and _path_key(path) != _path_key(_ACTIVE_CURRENT_CLAIM)
    ):
        claim_binding = _current_claim_binding()
        if any(value.get(key) != wanted for key, wanted in claim_binding.items()):
            raise base.runner.RecheckError("V2 evidence current claim binding differs")
    _BASE_WRITE_NEW(path, value)


def _validate_prerequisite_binding_fields(
    value: Mapping[str, Any], label: str
) -> None:
    if value.get("qualifier_v2_prerequisite_bundle_id") != (
        pack.QUALIFIER_V2_BUNDLE_ID
    ):
        raise base.runner.RecheckError(f"{label} qualifier bundle differs")
    if value.get("qualifier_v2_observed_sha256") != _ACTIVE_PREREQUISITE:
        raise base.runner.RecheckError(f"{label} prerequisite hashes differ")
    if value.get("admission_raw_busy") not in (0, 1):
        raise base.runner.RecheckError(f"{label} admission raw BUSY differs")
    _validate_reservation_reference(value, label)


def _validate_permanent_claim_document(
    claim: Mapping[str, Any], path: Path, action: Mapping[str, Any]
) -> int:
    _validate_prerequisite_binding_fields(claim, "permanent claim")
    _expect(
        claim,
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-permanent-claim",
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
            "action": dict(action),
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "permanent claim",
    )
    boot_nonce = claim.get("boot_nonce")
    if (
        not isinstance(boot_nonce, str)
        or base.runner._NONCE.fullmatch(boot_nonce) is None  # noqa: SLF001
    ):
        raise base.runner.RecheckError("permanent claim boot nonce differs")
    if not isinstance(claim.get("created_at"), str) or not claim["created_at"]:
        raise base.runner.RecheckError("permanent claim timestamp differs")
    admission = claim.get("admission_raw_busy")
    ordinal = int(action["ordinal"])
    if admission not in (0, 1) or (ordinal == 1 and admission != 1):
        raise base.runner.RecheckError("permanent claim admission BUSY differs")
    binding = _validate_reservation_reference(claim, "permanent claim")
    reservation, _ = _load_sealed_record(
        Path(str(binding["reservation_file"])), "permanent claim reservation"
    )
    if (
        reservation.get("command") != "run"
        or reservation.get("ordinal") != ordinal
        or reservation.get("action") != dict(action)
        or reservation.get("claim_file") != str(_absolute_path(path))
    ):
        raise base.runner.RecheckError("permanent claim reservation scope differs")
    return int(admission)


def _load_permanent_claim(
    path: Path, action: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    global _ACTIVE_ADMISSION_BUSY
    claim, file_sha = _load_sealed_record(path, "permanent claim")
    admission = _validate_permanent_claim_document(claim, Path(path), action)
    ordinal = int(action["ordinal"])
    if ordinal == 1:
        if claim.get("prior_local_evidence") is not None:
            raise base.runner.RecheckError("ordinal 1 claim has prior evidence")
    elif _ACTIVE_PRIOR is not None:
        expected_prior = {
            key: deepcopy(_ACTIVE_PRIOR[key])
            for key in (
                "boot_nonce",
                "prior_result",
                "prior_result_sha256",
                "prior_claim",
                "prior_claim_sha256",
                "admission_raw_busy",
            )
        }
        if claim.get("prior_local_evidence") != expected_prior:
            raise base.runner.RecheckError("current claim prior evidence differs")
    _ACTIVE_ADMISSION_BUSY = admission
    return claim, file_sha


def _validate_completed_result_document(
    result: Mapping[str, Any],
    result_path: Path,
    *,
    action: Mapping[str, Any],
    claim: Mapping[str, Any],
    claim_path: Path,
    claim_sha256: str,
) -> tuple[str, int]:
    _validate_prerequisite_binding_fields(result, "prior COMPLETE result")
    _expect(
        result,
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-result",
            "firmware_sha256": base.runner.FIRMWARE_SHA256,
            "action": dict(action),
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "claim_file": str(_absolute_path(claim_path)),
            "claim_file_sha256": claim_sha256,
            "claim_integrity": claim.get("integrity"),
        },
        "prior COMPLETE result",
    )
    result_binding = _validate_reservation_reference(result, "prior COMPLETE result")
    if _path_key(Path(str(result_binding["output_file"]))) != _path_key(result_path):
        raise base.runner.RecheckError("prior result reservation output differs")
    if result_binding != claim.get("output_reservation"):
        raise base.runner.RecheckError("prior result/claim reservations differ")
    boot_nonce = result.get("boot_nonce")
    if boot_nonce != claim.get("boot_nonce"):
        raise base.runner.RecheckError("prior result/claim boot differs")
    admission = result.get("admission_raw_busy")
    if admission != claim.get("admission_raw_busy") or admission not in (0, 1):
        raise base.runner.RecheckError("prior result/claim admission BUSY differs")
    ordinal = int(action["ordinal"])
    if ordinal == 1 and admission != 1:
        raise base.runner.RecheckError("prior ordinal 1 admission BUSY differs")
    terminal = result.get("terminal_report")
    if not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("prior result terminal is absent")
    _validate_complete_report(
        terminal,
        ordinal,
        str(boot_nonce),
        admission_raw_busy=int(admission),
    )
    readiness = terminal.get("readiness")
    entry_busy = readiness.get("entry_busy") if isinstance(readiness, Mapping) else None
    if entry_busy not in (0, 1) or result.get("qualification_entry_busy") != entry_busy:
        raise base.runner.RecheckError("prior result qualifier entry BUSY differs")
    return str(boot_nonce), int(admission)


def _validate_embedded_prior_chain(
    record: Mapping[str, Any], ordinal: int, *, visited: set[str] | None = None
) -> None:
    link = record.get("prior_local_evidence")
    if ordinal == 1:
        if link is not None:
            raise base.runner.RecheckError("ordinal 1 evidence has a prior link")
        return
    if not isinstance(link, Mapping):
        raise base.runner.RecheckError("later evidence prior link is absent")
    required_keys = {
        "boot_nonce",
        "prior_result",
        "prior_result_sha256",
        "prior_claim",
        "prior_claim_sha256",
        "admission_raw_busy",
    }
    if set(link) != required_keys:
        raise base.runner.RecheckError("later evidence prior link fields differ")
    result_path = Path(str(link.get("prior_result")))
    claim_path = Path(str(link.get("prior_claim")))
    _assert_distinct_paths({"embedded_prior_result": result_path, "embedded_prior_claim": claim_path})
    seen = set() if visited is None else set(visited)
    result_key = _path_key(result_path)
    claim_key = _path_key(claim_path)
    if result_key in seen or claim_key in seen:
        raise base.runner.RecheckError("prior evidence chain contains a cycle")
    seen.update((result_key, claim_key))
    prior_action = base.runner.ACTIONS[ordinal - 2]
    claim, claim_sha = _load_sealed_record(claim_path, "embedded prior claim")
    admission = _validate_permanent_claim_document(claim, claim_path, prior_action)
    result, result_sha = _load_sealed_record(result_path, "embedded prior result")
    if claim_sha != link.get("prior_claim_sha256"):
        raise base.runner.RecheckError("embedded prior claim SHA differs")
    if result_sha != link.get("prior_result_sha256"):
        raise base.runner.RecheckError("embedded prior result SHA differs")
    boot_nonce, result_admission = _validate_completed_result_document(
        result,
        result_path,
        action=prior_action,
        claim=claim,
        claim_path=claim_path,
        claim_sha256=claim_sha,
    )
    if (
        link.get("boot_nonce") != boot_nonce
        or link.get("admission_raw_busy") != admission
        or result_admission != admission
    ):
        raise base.runner.RecheckError("embedded prior evidence facts differ")
    if result.get("prior_local_evidence") != claim.get("prior_local_evidence"):
        raise base.runner.RecheckError("embedded prior claim/result chains differ")
    _validate_embedded_prior_chain(claim, ordinal - 1, visited=seen)


def _prepare_local_prior(
    ordinal: int, prior_result: Path | None, claims: Path
) -> dict[str, Any] | None:
    if ordinal == 1:
        if prior_result is not None:
            raise base.runner.RecheckError("fresh ordinal 1 forbids prior result")
        return None
    if prior_result is None:
        raise base.runner.RecheckError(
            "later ordinal requires --prior-result sealed COMPLETE evidence"
        )
    prior_action = base.runner.ACTIONS[ordinal - 2]
    expected_claim_path = Path(claims) / f"{prior_action['action_id']}.json"
    claim, claim_sha = _load_permanent_claim(expected_claim_path, prior_action)
    result, result_sha = _load_sealed_record(prior_result, "prior COMPLETE result")
    boot_nonce, admission_raw_busy = _validate_completed_result_document(
        result,
        Path(prior_result),
        action=prior_action,
        claim=claim,
        claim_path=expected_claim_path,
        claim_sha256=claim_sha,
    )
    if result.get("prior_local_evidence") != claim.get("prior_local_evidence"):
        raise base.runner.RecheckError("prior result/claim chain differs")
    _validate_embedded_prior_chain(claim, ordinal - 1)
    return {
        "boot_nonce": boot_nonce,
        "terminal_report": deepcopy(dict(result["terminal_report"])),
        "prior_result": str(Path(prior_result).resolve()),
        "prior_result_sha256": result_sha,
        "prior_claim": str(expected_claim_path.resolve()),
        "prior_claim_sha256": claim_sha,
        "admission_raw_busy": admission_raw_busy,
    }


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
        if _ACTIVE_PRIOR is not None:
            raise base.runner.RecheckError("fresh preflight has prior evidence")
        _validate_fresh_no_execute_report(report, boot_nonce)
    else:
        if _ACTIVE_PRIOR is None:
            raise base.runner.RecheckError("later preflight lacks local prior")
        prior_admission = _ACTIVE_PRIOR.get("admission_raw_busy")
        if prior_admission not in (0, 1):
            raise base.runner.RecheckError("local prior admission BUSY differs")
        _validate_complete_report(
            report,
            ordinal - 1,
            boot_nonce,
            admission_raw_busy=int(prior_admission),
        )
        if _ACTIVE_PRIOR.get("boot_nonce") != boot_nonce:
            raise base.runner.RecheckError("local prior is from another boot")
        if _ACTIVE_PRIOR.get("terminal_report") != dict(report):
            raise base.runner.RecheckError(
                "local prior terminal differs from device prior terminal"
            )
    return boot_nonce, transcript, report


_ZERO_ACTION_STAGE_COUNTS = {
    "pon": 0,
    "pof": 0,
    "drf": 0,
    "dtm_bytes": 0,
    "lut_bytes": 0,
    "ptlw_writes": 0,
    "command_0x86": 0,
    "visible_refresh_requests": 0,
}

_QUALIFICATION_FAILURE_COUNTS = {
    "cs2_disabled": (0, 0),
    "cs1_sample1_reset_busy": (1, 0),
    "cs1_sample2_reset_busy": (2, 1),
    "cs2_sample1_reset_busy": (3, 2),
    "cs2_sample2_reset_busy": (4, 3),
    "cs1_revision_unstable": (5, 4),
    "cs2_revision_unstable": (5, 4),
    "cs1_revision_trivial": (5, 4),
    "cs2_revision_trivial": (5, 4),
    "cs1_revision_not_010104": (5, 4),
    "cs2_revision_not_010104": (5, 4),
    "final_reset_busy_not_idle_high": (5, 4),
    "busy_or_gpio_posture_not_qualified": (5, 4),
}


def _validate_failed_readiness(value: Any, ordinal: int) -> int:
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("fault readiness is absent")
    entry_busy = value.get("entry_busy")
    if entry_busy not in (0, 1):
        raise base.runner.RecheckError("fault qualifier entry BUSY differs")
    stage = value.get("failure_stage")
    if stage not in _QUALIFICATION_FAILURE_COUNTS:
        raise base.runner.RecheckError("fault readiness stage differs")
    reset_count, read_count = _QUALIFICATION_FAILURE_COUNTS[str(stage)]
    _expect(
        value,
        {
            "valid": True,
            "qualified": False,
            "operation_id": ordinal,
            "ordinal": ordinal,
            "reset_count": reset_count,
            "revision_read_count": read_count,
            "revision_command_trace": [112] * read_count + [0] * (4 - read_count),
            "failure_stage": stage,
        },
        "fault readiness",
    )
    final_gpio = value.get("final_gpio")
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(key) != 0 for key in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        raise base.runner.RecheckError("fault readiness safe-low GPIO differs")
    if value.get("final_busy") not in (0, 1):
        raise base.runner.RecheckError("fault readiness final BUSY differs")
    return int(entry_busy)


def _validate_fault_status(
    value: Mapping[str, Any], action: Mapping[str, Any], boot_nonce: str
) -> None:
    _V1_BASE_VALIDATE_FAULT_STATUS(value, action, boot_nonce)
    ordinal = int(action["ordinal"])
    _expect(
        value,
        {
            "qualification_pending": False,
            "qualification_running": False,
            "qualification_call_count_for_action": 1,
            "total_qualification_call_count": ordinal,
            "late_pof_sleep_low_eligible": False,
            "total_driver_call_count": ordinal - 1,
        },
        "qualification fault status",
    )
    if _ACTIVE_ADMISSION_BUSY not in (0, 1):
        raise base.runner.RecheckError("fault admission raw BUSY differs")
    _validate_failed_readiness(value.get("readiness"), ordinal)
    _validate_busy_admission(
        value.get("busy_admission"), ordinal, captured_through="dispatch"
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
    _expect(
        value,
        {
            "boot_nonce": boot_nonce,
            "valid": True,
            "terminal_state": "FAULT",
            "result": False,
            "error": "per_action_readiness_qualification_failed",
            "ordinal": ordinal,
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "role": action["role"],
            "round": action["round"],
            "branch": action["branch"],
            "job_id": ordinal,
            "driver_called": False,
            "driver_call_count_for_action": 0,
            "total_driver_call_count": ordinal - 1,
            "qualification_called": True,
            "qualification_call_count_for_action": 1,
            "total_qualification_call_count": ordinal,
            "late_pof_sleep_low_eligible": False,
            "action_stage_command_counts": _ZERO_ACTION_STAGE_COUNTS,
            "phase": 3,
            "phase_name": "FAULT",
            "next_ordinal": ordinal,
            "no_retry": True,
            "no_recovery": True,
        },
        "qualification fault report",
    )
    if "driver" in value:
        raise base.runner.RecheckError("qualification fault called driver")
    if _ACTIVE_ADMISSION_BUSY not in (0, 1):
        raise base.runner.RecheckError("fault admission raw BUSY differs")
    _validate_failed_readiness(value.get("readiness"), ordinal)
    _validate_busy_admission(
        value.get("busy_admission"), ordinal, captured_through="dispatch"
    )
    if status is not None:
        common_keys = (
            "boot_nonce",
            "phase",
            "next_ordinal",
            "total_driver_call_count",
            "qualification_call_count_for_action",
            "total_qualification_call_count",
            "late_pof_sleep_low_eligible",
            "readiness",
            "busy_admission",
        )
        for key in common_keys:
            if status.get(key) != value.get(key):
                raise base.runner.RecheckError(
                    f"fault status/report {key} differs"
                )
        if status.get("current_action") != dict(action):
            raise base.runner.RecheckError("fault status action differs")


def _clear_active_context() -> None:
    global _ACTIVE_ADMISSION_BUSY, _ACTIVE_CURRENT_ACTION, _ACTIVE_CURRENT_CLAIM
    global _ACTIVE_PREREQUISITE, _ACTIVE_PRIOR, _ACTIVE_RESERVATION
    _ACTIVE_PRIOR = None
    _ACTIVE_ADMISSION_BUSY = None
    _ACTIVE_PREREQUISITE = None
    _ACTIVE_CURRENT_ACTION = None
    _ACTIVE_CURRENT_CLAIM = None
    _ACTIVE_RESERVATION = None


def _persist_unexpected_consumed_failure(output: Path, error: Exception) -> None:
    """Preserve a claim-bound receipt if an unexpected host error escapes."""

    if _ACTIVE_CURRENT_CLAIM is None or not _ACTIVE_CURRENT_CLAIM.is_file():
        return
    output = _absolute_path(output)
    if output.exists():
        return
    staged = _staged_path(output)
    if staged.is_file() and not staged.is_symlink():
        value, _ = _load_sealed_record(staged, "unexpected terminal staging")
        _validate_prerequisite_binding_fields(value, "unexpected terminal staging")
        _write_new_bound(output, value)
        return
    claim, _ = _load_sealed_record(_ACTIVE_CURRENT_CLAIM, "consumed current claim")
    if _ACTIVE_CURRENT_ACTION is None:
        raise base.runner.RecheckError("consumed action context is absent")
    _validate_permanent_claim_document(
        claim, _ACTIVE_CURRENT_CLAIM, _ACTIVE_CURRENT_ACTION
    )
    evidence = _seal_with_prerequisite(
        {
            "schema_version": 1,
            "kind": f"{pack.DEVICE_KIND_PREFIX}-consumed-host-failure",
            "created_at": base.runner._now(),  # noqa: SLF001
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": claim["boot_nonce"],
            "action": deepcopy(_ACTIVE_CURRENT_ACTION),
            "terminal_report": None,
            "transcript": [],
            "network": {"get": None, "arm_post": None, "execute_post": None},
            "outcome": "unexpected_host_exception_after_permanent_claim",
            "error_type": type(error).__name__,
            "error": str(error),
            "claim_state": "permanently_consumed",
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    _write_new_bound(output, evidence)


def _validate_poll_budget(poll_seconds: float, poll_count: int) -> None:
    if (
        not isinstance(poll_seconds, (int, float))
        or isinstance(poll_seconds, bool)
        or not math.isfinite(float(poll_seconds))
        or float(poll_seconds) < 65.0
    ):
        raise base.runner.RecheckError(
            "V2 run requires finite poll_seconds >= 65"
        )
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise base.runner.RecheckError("V2 run requires poll_count >= 1")


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    prior_result: Path | None = None,
    confirm_j2_on: bool = False,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    """Consume exactly one action after all local and live gates pass."""

    global _ACTIVE_ADMISSION_BUSY, _ACTIVE_CURRENT_ACTION, _ACTIVE_CURRENT_CLAIM
    global _ACTIVE_PREREQUISITE, _ACTIVE_PRIOR, _ACTIVE_RESERVATION
    if confirm_j2_on is not True:
        raise base.runner.RecheckError("live run requires explicit J2-ON confirmation")
    _validate_poll_budget(poll_seconds, poll_count)
    if ordinal < 1 or ordinal > len(base.runner.ACTIONS):
        raise base.runner.RecheckError("V2 ordinal differs")
    with _exclusive_device_access():
        _require_artifact_binding()
        observed = _require_prerequisite_evidence()
        _ACTIVE_PREREQUISITE = observed
        action = deepcopy(base.runner.ACTIONS[ordinal - 1])
        current_claim = _absolute_path(
            Path(claims) / f"{action['action_id']}.json"
        )
        if os.path.lexists(current_claim):
            _clear_active_context()
            raise base.runner.RecheckError(
                f"action {ordinal} was already permanently claimed"
            )
        try:
            _ACTIVE_PRIOR = _prepare_local_prior(
                ordinal, prior_result, Path(claims)
            )
            _ACTIVE_ADMISSION_BUSY = None
            prior_paths = {
                f"campaign_claim_ordinal_{item['ordinal']}": Path(claims)
                / f"{item['action_id']}.json"
                for item in base.runner.ACTIONS
                if int(item["ordinal"]) != ordinal
            }
            _ACTIVE_RESERVATION = _create_output_reservation(
                command="run",
                output=output,
                ordinal=ordinal,
                action=action,
                claim_file=current_claim,
                prior_result=prior_result,
                prior_paths=prior_paths,
                uses_staging=True,
            )
            _ACTIVE_CURRENT_ACTION = action
            _ACTIVE_CURRENT_CLAIM = current_claim
            try:
                result = v3.run_once(
                    base_url,
                    ordinal,
                    claims=claims,
                    output=output,
                    requester=requester,
                    poll_seconds=poll_seconds,
                    poll_count=poll_count,
                )
            except Exception as error:
                _persist_unexpected_consumed_failure(output, error)
                if isinstance(error, base.runner.RecheckError):
                    raise
                raise base.runner.RecheckError(
                    "unexpected host exception sealed after permanent claim; "
                    "action must not be retried"
                ) from error
            _validate_prerequisite_binding_fields(result, "V2 result")
            if result.get("admission_raw_busy") != _ACTIVE_ADMISSION_BUSY:
                raise base.runner.RecheckError("V2 result admission BUSY differs")
            _validate_current_claim_reference(result, "V2 result")
            return result
        finally:
            _clear_active_context()


def salvage_fault_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    prior_result: Path | None = None,
    confirm_j2_off: bool = False,
    requester: Any = None,
) -> dict[str, Any]:
    """Seal a consumed qualification FAULT using exactly four GETs."""

    global _ACTIVE_ADMISSION_BUSY, _ACTIVE_CURRENT_ACTION, _ACTIVE_CURRENT_CLAIM
    global _ACTIVE_PREREQUISITE, _ACTIVE_PRIOR, _ACTIVE_RESERVATION
    if confirm_j2_off is not True:
        raise base.runner.RecheckError(
            "fault salvage requires explicit J2-OFF confirmation"
        )
    if ordinal < 1 or ordinal > len(base.runner.ACTIONS):
        raise base.runner.RecheckError("V2 salvage ordinal differs")
    with _exclusive_device_access():
        _require_artifact_binding()
        _ACTIVE_PREREQUISITE = _require_prerequisite_evidence()
        action = deepcopy(base.runner.ACTIONS[ordinal - 1])
        current_claim = _absolute_path(
            Path(claims) / f"{action['action_id']}.json"
        )
        try:
            _ACTIVE_PRIOR = _prepare_local_prior(
                ordinal, prior_result, Path(claims)
            )
            _ACTIVE_ADMISSION_BUSY = None
            prior_paths = {
                f"campaign_claim_ordinal_{item['ordinal']}": Path(claims)
                / f"{item['action_id']}.json"
                for item in base.runner.ACTIONS
                if int(item["ordinal"]) != ordinal
            }
            _ACTIVE_RESERVATION = _create_output_reservation(
                command="salvage-fault",
                output=output,
                ordinal=ordinal,
                action=action,
                claim_file=current_claim,
                prior_result=prior_result,
                prior_paths=prior_paths,
                uses_staging=False,
            )
            _ACTIVE_CURRENT_ACTION = action
            _ACTIVE_CURRENT_CLAIM = current_claim
            value = v1.salvage_fault_once(
                base_url,
                ordinal,
                claims=claims,
                output=output,
                requester=requester,
            )
            if value.get("network") != {"get": 4, "post": 0}:
                raise base.runner.RecheckError("fault salvage network count differs")
            _validate_prerequisite_binding_fields(value, "fault salvage")
            _validate_current_claim_reference(value, "fault salvage")
            return value
        finally:
            _clear_active_context()


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Any = base.runner._http_request,  # noqa: SLF001
) -> dict[str, Any]:
    """Issue the four read-only identity/status/report GETs and no POST."""

    global _ACTIVE_ADMISSION_BUSY, _ACTIVE_CURRENT_ACTION, _ACTIVE_CURRENT_CLAIM
    global _ACTIVE_PREREQUISITE, _ACTIVE_PRIOR, _ACTIVE_RESERVATION
    if confirm_j2_off is not True:
        raise base.runner.RecheckError(
            "diagnose-j2-off requires explicit J2-OFF confirmation"
        )
    with _exclusive_device_access():
        _require_artifact_binding()
        _ACTIVE_PREREQUISITE = _require_prerequisite_evidence()
        _ACTIVE_PRIOR = None
        _ACTIVE_ADMISSION_BUSY = 0
        try:
            _ACTIVE_RESERVATION = _create_output_reservation(
                command="diagnose-j2-off",
                output=output,
                ordinal=None,
                action=None,
                claim_file=None,
                prior_result=None,
                uses_staging=False,
            )
            value = _BASE_DIAGNOSE_J2_OFF(
                base_url,
                output=output,
                requester=requester,
            )
            if value.get("network") != {"get": 4, "post": 0}:
                raise base.runner.RecheckError("J2-OFF diagnostic network count differs")
            _validate_prerequisite_binding_fields(value, "J2-OFF diagnostic")
            return value
        finally:
            _clear_active_context()


def dry_validate() -> dict[str, Any]:
    report = pack.build_report()
    if report["contract_id"] != pack.CONTRACT_ID:
        raise base.runner.RecheckError("V2 pack contract constant differs")
    if tuple(item["descriptor_id"] for item in report["actions"]) != (
        pack.DESCRIPTOR_IDS
    ):
        raise base.runner.RecheckError("V2 descriptor constants differ")
    if tuple(item["action_id"] for item in report["actions"]) != pack.ACTION_IDS:
        raise base.runner.RecheckError("V2 action constants differ")
    prerequisite = qualifier_prerequisite_status()
    artifacts = artifact_binding_status()
    return {
        "schema_version": 1,
        "kind": f"{pack.DEVICE_KIND_PREFIX}-dry-validation",
        "offline_only": True,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_ids": list(pack.DESCRIPTOR_IDS),
        "action_ids": list(pack.ACTION_IDS),
        "qualifier_v2_prerequisite": prerequisite,
        "artifact_binding_status": artifacts,
        "verified": prerequisite["verified"] is True
        and all(item["verified"] is True for item in artifacts.values()),
        "network": {"get": 0, "post": 0},
        "hardware_accessed": False,
    }


def describe() -> dict[str, Any]:
    value = v3.describe()
    value["variant"] = deepcopy(REPORT["contract"])
    value["artifact_binding_status"] = artifact_binding_status()
    try:
        prerequisite: dict[str, Any] = qualifier_prerequisite_status()
    except base.runner.RecheckError as error:
        prerequisite = {"verified": False, "error": str(error)}
    value["qualifier_v2_prerequisite"] = prerequisite
    value["qualifier_v2_prerequisite_bundle_id"] = (
        pack.QUALIFIER_V2_BUNDLE_ID
    )
    value["preflight_busy_contract"] = {
        "fresh_ordinal_1_live": "RAW_BUSY_1_ONLY",
        "j2_off_diagnostic": "RAW_BUSY_0_FOUR_GETS_ONLY",
        "later_raw_busy_levels": [0, 1],
        "later_raw0_requires": [
            "SAME_BOOT_DEVICE_PRIOR_COMPLETE",
            "DEVICE_PRIOR_SAFE_FINISH_HIGH",
            "RAM_ONLY_LATE_POF_SLEEP_LOW_ELIGIBLE",
            "LOCAL_PRIOR_PERMANENT_CLAIM",
            "LOCAL_SEALED_PRIOR_COMPLETE_RESULT",
        ],
    }
    value["per_action_readiness_qualification"] = deepcopy(
        REPORT["contract"]["per_action_readiness_qualification"]
    )
    value["busy_admission_evidence"] = {
        "contract": deepcopy(pack.BUSY_ADMISSION_CONTRACT),
        "device_runtime_snapshots": ["ARM", "EXECUTE", "DISPATCH"],
        "host_preflight_raw_busy_is_separate": True,
        "qualifier_entry_busy_is_separate": True,
        "no_cross_timestamp_equality_claim": True,
    }
    value["evidence_reservation"] = {
        "method": "OUTPUT_DOT_RESERVE_O_EXCL_BEFORE_ANY_DEVICE_REQUEST",
        "binds_claim_result_failure_salvage": True,
        "all_campaign_claim_paths_collision_checked": True,
    }
    value["fault_salvage"] = {
        "method": "FOUR_GETS_ONLY",
        "requires_j2_off": True,
        "later_ordinal_requires_prior_result": True,
        "post": 0,
        "retry": False,
        "recovery": False,
    }
    value["commands"] = {
        "describe": "offline",
        "dry-validate": "offline",
        "diagnose-j2-off": "four GETs, zero POST",
        "run": "one ARM plus one EXECUTE only after gates",
        "salvage-fault": "four GETs, zero POST",
    }
    value["startup_refresh"] = False
    value["automatic_chaining"] = False
    value["automatic_retry"] = False
    value["automatic_recovery"] = False
    value["live_authorized"] = False
    return value


# Rebind every dynamic validation point in the isolated private facade.
for module in (v1b, endpoint, v3, v2, base):
    module._validate_capabilities = _validate_capabilities
    module._validate_version = _validate_version
    module._validate_manifest = _validate_manifest
base.runner._validate_capabilities = _validate_capabilities
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner._request = _request_with_busy_evidence
base.runner._write_new = _write_new_bound
base.runner.run_once = run_once
base.runner.describe = describe
v1._validate_fresh_no_execute_report = _validate_fresh_no_execute_report
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._validate_ready_status = _validate_ready_status
v1._validate_fault_status = _validate_fault_status
v1._validate_fault_report = _validate_fault_report
v1._load_permanent_claim = _load_permanent_claim
v1._preflight = _preflight
v2._validate_ready_status = _validate_ready_status
v2._preflight = _preflight
v3._validate_ready_status = _validate_ready_status
v3._validate_complete_report = _validate_complete_report


def _validate_prior_terminal_report_bound(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if _ACTIVE_PRIOR is None:
        raise base.runner.RecheckError("V2 prior terminal has no local evidence")
    admission = _ACTIVE_PRIOR.get("admission_raw_busy")
    if admission not in (0, 1):
        raise base.runner.RecheckError("V2 prior terminal admission differs")
    _validate_complete_report(
        value,
        ordinal - 1,
        boot_nonce,
        admission_raw_busy=int(admission),
    )


v3._validate_prior_terminal_report = _validate_prior_terminal_report_bound
v3._preflight = _preflight


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnose = sub.add_parser("diagnose-j2-off")
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnose.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=base.runner.DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--prior-result", type=Path)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--ordinal", type=int, required=True)
    salvage.add_argument("--confirm-j2-off", action="store_true", required=True)
    salvage.add_argument(
        "--claims", type=Path, default=base.runner.DEFAULT_CLAIMS
    )
    salvage.add_argument("--output", type=Path, required=True)
    salvage.add_argument("--prior-result", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "dry-validate":
            value = dry_validate()
            if value.get("verified") is not True:
                print(json.dumps(value, ensure_ascii=False, sort_keys=True))
                return 2
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        elif args.command == "salvage-fault":
            value = salvage_fault_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=args.claims,
                output=args.output,
                prior_result=args.prior_result,
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except base.runner.RecheckError as error:
        print(f"Fullframe/PTLW V2 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
