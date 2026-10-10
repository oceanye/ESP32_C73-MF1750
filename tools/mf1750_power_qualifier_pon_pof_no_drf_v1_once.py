#!/usr/bin/env python3
"""Fail-closed host runner for the one-shot PON -> POF power probe.

The live path is deliberately split into three gates: four read-only identity
reads, one reset/readiness qualification, and four more read-only reads that
must prove qualified BUSY=1.  Only then is a permanent local claim created and
the unique ARM/EXECUTE probe permitted.  The runner never flashes, resets via
serial, controls a relay, retries, recovers, or chains another action.
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

from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as pack  # noqa: E402


REPORT = pack.build_report()
ACTION = deepcopy(REPORT["actions"][0])
KIND_PREFIX = "mf1750-power-qualifier-pon-pof-no-drf-v1"
ENDPOINT_BASE = "/api/ec5/power-qualifier-pon-pof-no-drf-v1"
ENDPOINTS = {
    name: f"{ENDPOINT_BASE}/{name}"
    for name in (
        "version",
        "manifest",
        "status",
        "report",
        "qualify",
        "arm",
        "execute",
    )
}
QUALIFY_INTENT = "QUALIFY_RESET_AND_STABLE_DUAL_REVISION_ONCE"
ARM_INTENT = "ARM_ONE_PON_POF_NO_DRF_POWER_PATH_PROBE"
EXECUTE_INTENT = "EXECUTE_ARMED_PON_POF_NO_DRF_POWER_PATH_PROBE_ONCE"

BUILD_DIR = REPO_ROOT / ".pio" / "build-power-qualifier-pon-pof-no-drf-v1" / pack.ENV_NAME
FIRMWARE_BIN = BUILD_DIR / "firmware.bin"
FIRMWARE_ELF = BUILD_DIR / "firmware.elf"

# These are filled only after the clean firmware build.  Describe and
# dry-validate remain useful while pending; every device-facing function is
# fail-closed until both exact bindings are frozen.
FIRMWARE_BIN_BYTES: int | None = 786_816
FIRMWARE_BIN_SHA256: str | None = (
    "fda829c0671bb0a200e5de65e6fe4d166a254149913da2e7b56af6f6da84accc"
)
FIRMWARE_ELF_BYTES: int | None = 13_111_404
FIRMWARE_ELF_SHA256: str | None = (
    "2d21c7d394c80a166283b81f93d3ee272522c09bd46f4c23213b3cc5e26d2efb"
)

DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_power_qualifier_pon_pof_no_drf_v1_claims"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_20260825_V1"
)

Requester = Callable[..., tuple[int, Mapping[str, Any]]]
_NONCE = re.compile(r"^[0-9a-f]{16}$")
_MAX_JSON_BYTES = 2 * 1024 * 1024
DEFAULT_POLL_COUNT = 90


class QualifierError(RuntimeError):
    """Raised when identity, state, qualification, or one-shot gates differ."""


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
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
    except FileExistsError as error:
        raise QualifierError(f"refusing to overwrite {path}") from error


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_sealed(path: Path, label: str) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise QualifierError(f"{label} is missing or is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualifierError(f"{label} is not readable canonical JSON") from error
    if not isinstance(value, dict):
        raise QualifierError(f"{label} root is not an object")
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping):
        raise QualifierError(f"{label} integrity is missing")
    body = deepcopy(value)
    body.pop("integrity", None)
    wanted = hashlib.sha256(_canonical(body)).hexdigest()
    if (
        integrity.get("algorithm")
        != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != wanted
    ):
        raise QualifierError(f"{label} integrity differs")
    return value, _sha256(path)


def artifact_binding_status() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, path, wanted_bytes, wanted_sha256 in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = _sha256(path) if present else None
        frozen = isinstance(wanted_bytes, int) and isinstance(wanted_sha256, str)
        result[name] = {
            "path": str(path),
            "present": present,
            "binding_frozen": frozen,
            "verified": bool(
                frozen
                and present
                and observed_bytes == wanted_bytes
                and observed_sha256 == wanted_sha256
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
            "expected_bytes": wanted_bytes,
            "expected_sha256": wanted_sha256,
        }
    return result


def _require_artifact_binding() -> None:
    if any(item["verified"] is not True for item in artifact_binding_status().values()):
        raise QualifierError(
            "PON/POF qualifier BIN/ELF binding is pending or differs; refusing device access"
        )


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
        raise QualifierError("base URL must be a plain HTTP origin")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    """Call the selected LAN origin directly, with host proxies disabled."""

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
        raise QualifierError(f"{method} {path} failed: {error}") from error
    if len(payload) > _MAX_JSON_BYTES:
        raise QualifierError(f"{method} {path} response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualifierError(f"{method} {path} response is not JSON") from error
    if not isinstance(value, Mapping):
        raise QualifierError(f"{method} {path} response root is not an object")
    return status, value


def _request(
    requester: Requester,
    transcript: list[dict[str, Any]],
    origin: str,
    endpoint: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: float = 12.0,
) -> Mapping[str, Any]:
    try:
        status, value = requester(
            origin,
            ENDPOINTS[endpoint],
            method=method,
            headers=headers,
            timeout=timeout,
        )
    except Exception as error:
        raise QualifierError(f"{method} {endpoint} failed: {error}") from error
    if not isinstance(status, int) or not isinstance(value, Mapping):
        raise QualifierError(f"{method} {endpoint} returned malformed data")
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
        raise QualifierError(f"{method} {endpoint} returned HTTP {status}")
    return value


def _identity(value: Mapping[str, Any], suffix: str) -> None:
    exact = {
        "kind": f"{KIND_PREFIX}-{suffix}",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "action_id": pack.ACTION_ID,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device {suffix} {key} differs")


def _identity_binding(value: Mapping[str, Any], label: str) -> None:
    exact = {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.CONTRACT_ID,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"{label} {key} differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _identity(value, "version")
    exact = {
        "action_count": 1,
        "startup_refresh": False,
        "visible_refresh_requests": 0,
        "base_route": ENDPOINT_BASE,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "classification": pack.CLASSIFICATION,
        "automatic_execute": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": False,
        "ptlw_write": False,
        "visible_refresh": False,
        "nvs_contract": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 2,
        },
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device version {key} differs")
def _validate_manifest(value: Mapping[str, Any]) -> None:
    _identity(value, "manifest")
    exact = {
        "actions": [ACTION],
        "classification": pack.CLASSIFICATION,
        "nvs": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 2,
            "missing_key_is_fresh_only": True,
            "nonterminal_phase_on_boot": "FAULT_NO_RESUME_NO_RETRY",
        },
        "qualification": {
            "reset_count": 1,
            "cs1_revision_reads": 2,
            "cs2_revision_reads": 2,
            "stable_required": True,
            "nontrivial_required": True,
            "same_boot_required": True,
            "qualified_busy_level": 1,
            "qualified_gpio": {
                "rst": 1, "cs1": 1, "cs2": 1,
                "sck": 0, "dc": 0, "mosi": 0,
            },
        },
        "probe": {
            "spi_hz": pack.PROBE_SPI_HZ,
            "exactly_one_pon": True,
            "exactly_one_pof": True,
            "pon_count": 1,
            "pof_count": 1,
            "drf_count": 0,
            "dtm_bytes": 0,
            "lut_bytes": 0,
            "ptlw_writes": 0,
            "command_0x86_count": 0,
            "visible_refresh_requests": 0,
            "failure_cleanup_matrix": pack.FAILURE_CLEANUP_MATRIX,
            "post_pof": [
                "DELAY_6000MS", "PSR_4F6E", "WAIT_IDLE",
                "DELAY_1000MS", "PINS_LOW",
            ],
        },
        "forbidden_commands": list(pack.FORBIDDEN_COMMANDS),
        "safety": {
            "startup_action": False,
            "automatic_execute": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "action_count": 1,
        "one_driver_call_per_action": True,
        "probe_sequence": list(pack.PROBE_SEQUENCE),
        "pon_count": 1,
        "pof_count": 1,
        "drf_count": 0,
        "dtm_bytes": 0,
        "lut_bytes": 0,
        "ptlw_writes": 0,
        "visible_refresh_requests": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device manifest {key} differs")
    allowed = value.get("allowed_command_payload_sequence")
    if allowed != [
        "REV_CS1_X2_70", "REV_CS2_X2_70", "AA_495520080918",
        "PWR_01_3F", "PSR_00_5F69", "BTST1_05_401F1F2C",
        "BTST3_08_6F1F1F22", "BTST2_06_6F1F1717",
        "POFS_03_00540044", "TCON_60_0200", "PLL_30_08",
        "CDI_50_3F", "TRES_61_02000258", "PWS_E3_2F",
        "T_VDCS_84_01", "CCSET_CS1_E0_01", "CCSET_CS2_E0_01",
        "SELECT_DUAL_BEFORE_PON", "PON_04",
        "SELECT_DUAL_BEFORE_POF", "POF_02_00",
        "SELECT_DUAL_BEFORE_POST_PSR", "PSR_00_4F6E",
    ]:
        raise QualifierError("device manifest allowed command/payload sequence differs")


def _nonce(value: Any, label: str) -> str:
    if not isinstance(value, str) or _NONCE.fullmatch(value) is None:
        raise QualifierError(f"{label} is malformed")
    return value


def _validate_status_common(value: Mapping[str, Any]) -> str:
    _identity(value, "status")
    exact = {
        "next_ordinal": 1,
        "campaign_complete": False,
        "probe_pending": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
        "total_driver_call_count": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device status {key} differs")
    return _nonce(value.get("boot_nonce"), "boot nonce")


def _validate_ready_status(value: Mapping[str, Any], *, expected_busy: int) -> str:
    nonce = _validate_status_common(value)
    gpio = value.get("gpio")
    exact = {
        "state": "ready_unqualified",
        "phase": 0,
        "phase_name": "FRESH",
        "same_boot_qualified": False,
        "qualified_pin_posture": False,
        "qualify_pending": False,
        "qualify_request_count": 0,
        "qualifier_call_count": 0,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "probe_call_count": 0,
        "cursor_raw": 0,
        "persistent_key_present": False,
        "qualification_consumed": False,
        "qualification_valid": False,
        "qualification_nonce": None,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device READY status {key} differs")
    if gpio != {
        "busy": expected_busy, "rst": 0, "cs1": 0, "cs2": 0,
        "sck": 0, "dc": 0, "mosi": 0,
    }:
        raise QualifierError("device READY GPIO posture differs")
    return nonce


def _validate_qualified_status(value: Mapping[str, Any], *, boot_nonce: str) -> str:
    nonce = _validate_status_common(value)
    gpio = value.get("gpio")
    exact = {
        "state": "qualified",
        "phase": 2,
        "phase_name": "QUALIFIED",
        "same_boot_qualified": True,
        "qualified_pin_posture": True,
        "qualify_pending": False,
        "qualify_request_count": 1,
        "qualifier_call_count": 1,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "probe_call_count": 0,
        "cursor_raw": 2,
        "persistent_key_present": True,
        "qualification_consumed": True,
        "qualification_valid": True,
    }
    if nonce != boot_nonce:
        raise QualifierError("boot changed across reset/readiness qualification")
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"device QUALIFIED status {key} differs")
    if gpio != {
        "busy": 1, "rst": 1, "cs1": 1, "cs2": 1,
        "sck": 0, "dc": 0, "mosi": 0,
    }:
        raise QualifierError("device QUALIFIED BUSY/GPIO posture differs")
    return _nonce(value.get("qualification_nonce"), "qualification nonce")


def _validate_readiness(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise QualifierError("qualified readiness evidence is missing")
    exact = {
        "valid": True,
        "qualified": True,
        "final_busy": 1,
        "final_gpio": {
            "rst": 1, "cs1": 1, "cs2": 1,
            "sck": 0, "dc": 0, "mosi": 0,
        },
        "final_high_stable_ms": 50,
        "reset_count": 1,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "failure_stage": "none",
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"qualified readiness {key} differs")
    for controller in ("cs1", "cs2"):
        samples = value.get(controller)
        if not isinstance(samples, Mapping):
            raise QualifierError(f"qualified readiness {controller} is missing")
        if samples.get("stable") is not True or samples.get("nontrivial") is not True:
            raise QualifierError(f"qualified readiness {controller} is not stable/nontrivial")
        first, second = samples.get("sample1"), samples.get("sample2")
        if not isinstance(first, Mapping) or not isinstance(second, Mapping):
            raise QualifierError(f"qualified readiness {controller} samples are missing")
        if first != second or first.get("idle") is not True:
            raise QualifierError(f"qualified readiness {controller} samples differ")
        revision = first.get("bytes")
        if (
            not isinstance(revision, list)
            or len(revision) != 3
            or any(not isinstance(byte, int) or not 0 <= byte <= 255 for byte in revision)
            or revision in ([0, 0, 0], [255, 255, 255])
        ):
            raise QualifierError(f"qualified readiness {controller} revision is trivial")


def _four_gets(
    origin: str,
    requester: Requester,
    transcript: list[dict[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    version = _request(requester, transcript, origin, "version")
    manifest = _request(requester, transcript, origin, "manifest")
    status = _request(requester, transcript, origin, "status")
    report = _request(requester, transcript, origin, "report")
    _validate_version(version)
    _validate_manifest(manifest)
    _identity(report, "report")
    return version, manifest, status, report


def _headers(boot_nonce: str, intent: str) -> dict[str, str]:
    return {
        "X-EC5-Build-Tag": pack.BUILD_TAG,
        "X-EC5-Test-Id": pack.TEST_ID,
        "X-EC5-Campaign-Id": pack.CAMPAIGN_ID,
        "X-EC5-Action-Id": ACTION["action_id"],
        "X-EC5-Ordinal": "1",
        "X-EC5-Descriptor-Id": ACTION["descriptor_id"],
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }


def _qualify_headers(boot_nonce: str) -> dict[str, str]:
    return {
        "X-EC5-Build-Tag": pack.BUILD_TAG,
        "X-EC5-Test-Id": pack.TEST_ID,
        "X-EC5-Campaign-Id": pack.CAMPAIGN_ID,
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": QUALIFY_INTENT,
    }


def dry_validate() -> dict[str, Any]:
    report = pack.build_report()
    if (
        report["descriptor_canonical_sha256"] != pack.DESCRIPTOR_ID
        or pack._action_id(pack.DESCRIPTOR_ID) != pack.ACTION_ID  # noqa: SLF001
        or report["contract_canonical_sha256"] != pack.CONTRACT_ID
        or report["contract_id"] != pack.CONTRACT_ID
    ):
        raise QualifierError("offline contract binding differs")
    if report["actions"] != [ACTION]:
        raise QualifierError("offline action identity differs")
    artifacts = artifact_binding_status()
    return _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-dry-validation",
            "offline_only": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
            "pack_valid": True,
            "contract_id": pack.CONTRACT_ID,
            "action": deepcopy(ACTION),
            "artifact_binding": artifacts,
            "live_entry_enabled": all(item["verified"] for item in artifacts.values()),
        }
    )


def describe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": f"{KIND_PREFIX}-description",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "environment": pack.ENV_NAME,
        "contract_id": pack.CONTRACT_ID,
        "nvs": {"namespace": pack.NVS_NAMESPACE, "key": pack.NVS_KEY},
        "endpoints": deepcopy(ENDPOINTS),
        "action": deepcopy(ACTION),
        "flow": [
            "J2_OFF_FOUR_GET_DIAGNOSTIC",
            "LIVE_FOUR_GET_PREQUALIFICATION",
            "ONE_RESET_STABLE_DUAL_REVISION_QUALIFICATION",
            "LIVE_FOUR_GET_QUALIFIED_BUSY1_RECHECK",
            "PERMANENT_LOCAL_CLAIM",
            "ONE_ARM",
            "ONE_EXECUTE_PON_THEN_POF",
        ],
        "read_only_fault_salvage": {
            "command": "salvage-fault",
            "network": {"get": 4, "post": 0},
            "requires_existing_qualification_attempt": True,
            "requires_existing_output_reservation": True,
            "creates_permanent_claim": False,
            "hardware_mutation_requested": False,
        },
        "probe": {
            "spi_hz": pack.PROBE_SPI_HZ,
            "pon": 1,
            "pof": 1,
            "drf": 0,
            "dtm_bytes": 0,
            "lut_bytes": 0,
            "ptlw_writes": 0,
            "visible_refresh_requests": 0,
            "failure_cleanup_matrix": deepcopy(pack.FAILURE_CLEANUP_MATRIX),
        },
        "raw_busy_zero_direct_arm": False,
        "direct_http_no_proxy": True,
        "startup_refresh": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "firmware_flash_performed_by_runner": False,
        "artifact_binding": artifact_binding_status(),
        "live_authorized": False,
    }


def diagnose_j2_off(
    base_url: str,
    *,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = _http_request,
) -> dict[str, Any]:
    if confirm_j2_off is not True:
        raise QualifierError("J2-OFF diagnostic requires explicit confirmation")
    _require_artifact_binding()
    transcript: list[dict[str, Any]] = []
    _, _, status, report = _four_gets(_origin(base_url), requester, transcript)
    boot_nonce = _validate_ready_status(status, expected_busy=0)
    if report.get("boot_nonce") != boot_nonce:
        raise QualifierError("J2-OFF report boot nonce differs")
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-j2-off-diagnostic",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "probe_driver_calls": 0,
            "visible_refresh_requests": 0,
        }
    )
    _write_new(output, evidence)
    return evidence


def _validate_qualification_fault_status(
    value: Mapping[str, Any], *, boot_nonce: str
) -> None:
    _identity(value, "status")
    exact = {
        "boot_nonce": boot_nonce,
        "state": "fault_locked",
        "phase": 6,
        "phase_name": "FAULT",
        "next_ordinal": 1,
        "campaign_complete": False,
        "same_boot_qualified": False,
        "qualification_nonce": None,
        "qualified_pin_posture": False,
        "qualify_pending": False,
        "probe_pending": False,
        "qualify_request_count": 1,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "qualifier_call_count": 1,
        "probe_call_count": 0,
        "cursor_raw": 6,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
        "persistent_key_present": True,
        "qualification_consumed": True,
        "qualification_valid": False,
        "total_driver_call_count": 0,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"qualification-fault status {key} differs")
    gpio = value.get("gpio")
    if not isinstance(gpio, Mapping) or any(
        gpio.get(pin) != 0 for pin in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        raise QualifierError("qualification-fault GPIO is not safely LOW")
    if gpio.get("busy") not in (0, 1):
        raise QualifierError("qualification-fault BUSY is malformed")


def _validate_revision_sample(
    value: Any, *, expected: list[int], label: str
) -> None:
    if not isinstance(value, Mapping):
        raise QualifierError(f"{label} revision sample is missing")
    if value.get("idle") is not True or value.get("bytes") != expected:
        raise QualifierError(f"{label} revision sample differs")


def _validate_qualification_fault_report(
    value: Mapping[str, Any], *, boot_nonce: str
) -> None:
    _identity(value, "report")
    exact = {
        "valid": True,
        "boot_nonce": boot_nonce,
        "terminal_state": "FAULT",
        "result": False,
        "error": "readiness_qualification_failed",
        "qualification_nonce": None,
        "phase": 6,
        "phase_name": "FAULT",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    for key, wanted in exact.items():
        if value.get(key) != wanted:
            raise QualifierError(f"qualification-fault report {key} differs")
    readiness = value.get("readiness")
    if not isinstance(readiness, Mapping):
        raise QualifierError("qualification-fault readiness is missing")
    readiness_exact = {
        "valid": True,
        "qualified": False,
        "entry_busy": 1,
        "reset_count": 1,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "failure_stage": "cs2_revision_trivial",
    }
    for key, wanted in readiness_exact.items():
        if readiness.get(key) != wanted:
            raise QualifierError(f"qualification-fault readiness {key} differs")
    readiness_gpio = readiness.get("final_gpio")
    if not isinstance(readiness_gpio, Mapping) or any(
        readiness_gpio.get(pin) != 0
        for pin in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        raise QualifierError("qualification-fault readiness GPIO is not safely LOW")
    if readiness.get("final_busy") not in (0, 1):
        raise QualifierError("qualification-fault readiness BUSY is malformed")
    cs1 = readiness.get("cs1")
    cs2 = readiness.get("cs2")
    if not isinstance(cs1, Mapping) or not isinstance(cs2, Mapping):
        raise QualifierError("qualification-fault controller evidence is missing")
    for name in ("sample1", "sample2"):
        _validate_revision_sample(cs1.get(name), expected=[1, 1, 4], label=f"CS1 {name}")
        _validate_revision_sample(cs2.get(name), expected=[0, 0, 0], label=f"CS2 {name}")
    if (
        cs1.get("stable") is not True
        or cs1.get("nontrivial") is not True
        or cs2.get("stable") is not True
        or cs2.get("nontrivial") is not False
    ):
        raise QualifierError("qualification-fault revision classification differs")
    probe = value.get("probe")
    if not isinstance(probe, Mapping):
        raise QualifierError("qualification-fault zero-probe evidence is missing")
    if any(
        probe.get(key) is not False
        for key in (
            "valid",
            "running",
            "pon_command_sent",
            "pof_command_sent",
            "post_psr_command_sent",
            "pon_busy_seen",
            "pof_busy_seen",
        )
    ):
        raise QualifierError("qualification fault unexpectedly entered the probe")
    if probe.get("command_counts") != {
        "pon": 0,
        "pof": 0,
        "drf": 0,
        "dtm": 0,
        "lut": 0,
        "ptlw": 0,
        "command_0x86": 0,
        "visible_refresh_requests": 0,
    }:
        raise QualifierError("qualification-fault command counts are not all zero")
    if (
        probe.get("command_trace") != []
        or probe.get("wire_event_count") != 0
        or probe.get("operation_id") != 0
    ):
        raise QualifierError("qualification-fault wire evidence is not empty")
    forbidden = probe.get("forbidden_commands")
    if forbidden != {
        "drf": False,
        "dtm": False,
        "lut": False,
        "ptlw": False,
        "command_0x86": False,
    }:
        raise QualifierError("qualification-fault forbidden-command evidence differs")


def salvage_fault(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    confirm_j2_off: bool = False,
    requester: Requester = _http_request,
) -> dict[str, Any]:
    """Seal one GET-only receipt for a pre-ARM qualification fault."""

    if confirm_j2_off is not True:
        raise QualifierError("fault salvage requires explicit J2-OFF confirmation")
    _require_artifact_binding()
    output = Path(output)
    if output.exists():
        raise QualifierError(f"refusing to overwrite final evidence {output}")
    attempt_file = Path(claims) / f"{ACTION['action_id']}.qualification-attempt.json"
    claim_file = Path(claims) / f"{ACTION['action_id']}.json"
    reservation_file = Path(str(output) + ".reserve")
    if claim_file.exists():
        raise QualifierError("qualification-fault salvage requires no permanent ARM claim")
    attempt, attempt_sha256 = _load_sealed(attempt_file, "qualification attempt")
    reservation, reservation_sha256 = _load_sealed(
        reservation_file, "output reservation"
    )
    if (
        attempt.get("kind")
        != f"{KIND_PREFIX}-qualification-attempt"
        or attempt.get("action") != ACTION
        or attempt.get("firmware_sha256") != FIRMWARE_BIN_SHA256
        or attempt.get("state") != "reserved_before_qualify_post"
        or attempt.get("no_automatic_retry") is not True
        or attempt.get("initial_busy") != 1
    ):
        raise QualifierError("qualification attempt binding differs")
    boot_nonce = _nonce(attempt.get("boot_nonce"), "attempt boot nonce")
    if (
        reservation.get("kind")
        != f"{KIND_PREFIX}-output-reservation"
        or reservation.get("boot_nonce") != boot_nonce
        or reservation.get("final_output") != str(output.resolve())
    ):
        raise QualifierError("output reservation binding differs")

    transcript: list[dict[str, Any]] = []
    _, _, status, report = _four_gets(_origin(base_url), requester, transcript)
    _validate_qualification_fault_status(status, boot_nonce=boot_nonce)
    _validate_qualification_fault_report(report, boot_nonce=boot_nonce)
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-qualification-fault-salvage",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(ACTION),
            "qualification_attempt_file": str(attempt_file.resolve()),
            "qualification_attempt_file_sha256": attempt_sha256,
            "qualification_attempt_integrity": deepcopy(attempt["integrity"]),
            "output_reservation_file": str(reservation_file.resolve()),
            "output_reservation_file_sha256": reservation_sha256,
            "output_reservation_integrity": deepcopy(reservation["integrity"]),
            "permanent_claim_file": str(claim_file.resolve()),
            "permanent_claim_present": False,
            "claim_semantics": "NOT_CREATED_BECAUSE_QUALIFICATION_FAILED_BEFORE_ARM",
            "status": deepcopy(dict(status)),
            "terminal_report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "outcome": "qualification_fault_salvaged_read_only",
            "attempt_state": "PERMANENTLY_CONSUMED_DO_NOT_RETRY_V1",
            "probe_command_counts": {"pon": 0, "pof": 0, "drf": 0},
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "hardware_mutation_requested": False,
        }
    )
    _write_new(output, evidence)
    return evidence


def run_once(
    base_url: str,
    *,
    claims: Path,
    output: Path,
    confirm_j2_on: bool = False,
    requester: Requester = _http_request,
    poll_seconds: float = 2.0,
    poll_count: int = DEFAULT_POLL_COUNT,
) -> dict[str, Any]:
    if confirm_j2_on is not True:
        raise QualifierError("live probe requires explicit J2-ON confirmation")
    if poll_seconds < 0 or poll_count < 1:
        raise QualifierError("poll parameters are invalid")
    _require_artifact_binding()
    output = Path(output)
    if output.exists():
        raise QualifierError(f"refusing to overwrite final evidence {output}")
    claim_file = Path(claims) / f"{ACTION['action_id']}.json"
    qualification_attempt_file = (
        Path(claims) / f"{ACTION['action_id']}.qualification-attempt.json"
    )
    reservation_file = Path(str(output) + ".reserve")
    if claim_file.exists():
        raise QualifierError("probe was already permanently claimed")
    if qualification_attempt_file.exists():
        raise QualifierError(
            "reset/readiness qualification was already attempted; do not retry"
        )
    if reservation_file.exists():
        raise QualifierError("final evidence path is already reserved")

    origin = _origin(base_url)
    transcript: list[dict[str, Any]] = []
    _, _, initial_status, initial_report = _four_gets(origin, requester, transcript)
    initial_gpio = initial_status.get("gpio")
    if not isinstance(initial_gpio, Mapping):
        raise QualifierError("initial GPIO status is malformed")
    initial_busy = initial_gpio.get("busy")
    if initial_busy not in (0, 1):
        raise QualifierError("initial raw BUSY is malformed")
    boot_nonce = _validate_ready_status(initial_status, expected_busy=initial_busy)
    if initial_report.get("boot_nonce") != boot_nonce:
        raise QualifierError("initial report boot nonce differs")

    # Reserve both the qualification attempt and final evidence path before
    # the first POST.  A lost QUALIFY response is therefore never retried in
    # the same campaign by accident.
    qualification_attempt = _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-qualification-attempt",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "action": deepcopy(ACTION),
            "initial_busy": initial_busy,
            "state": "reserved_before_qualify_post",
            "no_automatic_retry": True,
        }
    )
    _write_new(qualification_attempt_file, qualification_attempt)
    _write_new(
        reservation_file,
        _seal(
            {
                "schema_version": 1,
                "kind": f"{KIND_PREFIX}-output-reservation",
                "created_at": _now(),
                "boot_nonce": boot_nonce,
                "final_output": str(output.resolve()),
            }
        ),
    )

    qualify = _request(
        requester,
        transcript,
        origin,
        "qualify",
        method="POST",
        headers=_qualify_headers(boot_nonce),
        timeout=15.0,
    )
    _identity_binding(qualify, "qualification response")
    qualify_exact = {
        "accepted": True,
        "qualification_queued": True,
        "boot_nonce": boot_nonce,
        "action_id": ACTION["action_id"],
        "descriptor_id": ACTION["descriptor_id"],
        "phase": 1,
        "phase_name": "QUALIFY_CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in qualify_exact.items():
        if qualify.get(key) != wanted:
            raise QualifierError(
                f"reset/readiness qualification {key} differs; probe was not armed"
            )

    qualification_nonce: str | None = None
    qualified_report: Mapping[str, Any] | None = None
    for _ in range(poll_count):
        if poll_seconds:
            time.sleep(poll_seconds)
        _, _, candidate_status, candidate_report = _four_gets(
            origin, requester, transcript
        )
        if candidate_status.get("boot_nonce") != boot_nonce:
            raise QualifierError("boot changed during reset/readiness qualification")
        if candidate_status.get("state") == "qualified":
            qualification_nonce = _validate_qualified_status(
                candidate_status, boot_nonce=boot_nonce
            )
            qualified_report = candidate_report
            break
        if (
            candidate_status.get("state") == "fault_locked"
            or candidate_report.get("terminal_state") == "FAULT"
        ):
            raise QualifierError(
                "reset/readiness qualification faulted; do not retry"
            )
    if qualification_nonce is None or qualified_report is None:
        raise QualifierError(
            "qualified state not observed; qualification must not be retried"
        )
    if (
        qualified_report.get("boot_nonce") != boot_nonce
        or qualified_report.get("terminal_state") != "QUALIFIED"
        or qualified_report.get("result") is not True
        or qualified_report.get("phase") != 2
        or qualified_report.get("phase_name") != "QUALIFIED"
        or qualified_report.get("qualification_nonce") != qualification_nonce
        or qualified_report.get("probe") is not None
        or qualified_report.get("no_retry") is not True
        or qualified_report.get("no_recovery") is not True
        or qualified_report.get("no_autochain") is not True
    ):
        raise QualifierError("postqualification report differs; probe was not armed")
    _validate_readiness(qualified_report.get("readiness"))

    claim = _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-permanent-claim",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "qualification_nonce": qualification_nonce,
            "action": deepcopy(ACTION),
            "state": "claimed_after_qualification_before_arm",
            "initial_busy": initial_busy,
            "qualified_busy": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    _write_new(claim_file, claim)

    arm_headers = _headers(boot_nonce, ARM_INTENT)
    arm_headers["X-EC5-Qualification-Nonce"] = qualification_nonce
    arm = _request(
        requester,
        transcript,
        origin,
        "arm",
        method="POST",
        headers=arm_headers,
    )
    arm_nonce = _nonce(arm.get("arm_nonce"), "arm nonce")
    _identity_binding(arm, "ARM response")
    if (
        arm.get("accepted") is not True
        or arm.get("armed") is not True
        or arm.get("action_id") != ACTION["action_id"]
        or arm.get("descriptor_id") != ACTION["descriptor_id"]
        or arm.get("boot_nonce") != boot_nonce
        or arm.get("qualification_nonce") != qualification_nonce
    ):
        raise QualifierError("ARM response differs; permanent claim remains consumed")

    execute_headers = _headers(boot_nonce, EXECUTE_INTENT)
    execute_headers["X-EC5-Qualification-Nonce"] = qualification_nonce
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    execute = _request(
        requester,
        transcript,
        origin,
        "execute",
        method="POST",
        headers=execute_headers,
    )
    _identity_binding(execute, "EXECUTE response")
    if (
        execute.get("accepted") is not True
        or execute.get("execute_consumed") is not True
        or execute.get("action_id") != ACTION["action_id"]
        or execute.get("descriptor_id") != ACTION["descriptor_id"]
        or execute.get("boot_nonce") != boot_nonce
        or execute.get("qualification_nonce") != qualification_nonce
    ):
        raise QualifierError("EXECUTE response differs; permanent claim remains consumed")

    terminal: Mapping[str, Any] | None = None
    terminal_poll_errors: list[str] = []
    for _ in range(poll_count):
        if poll_seconds:
            time.sleep(poll_seconds)
        try:
            candidate = _request(requester, transcript, origin, "report")
        except QualifierError as error:
            terminal_poll_errors.append(str(error))
            continue
        if candidate.get("terminal_state") in ("COMPLETE", "FAULT"):
            terminal = candidate
            break
    mismatches: list[str] = []
    observed_terminal = terminal
    terminal = terminal or {}
    try:
        _identity(terminal, "report")
    except QualifierError as error:
        mismatches.append(str(error))
    common_terminal = {
        "boot_nonce": boot_nonce,
        "ordinal": 1,
        "role": ACTION["role"],
        "branch": ACTION["branch"],
        "phase": 5,
        "phase_name": "COMPLETE",
        "action_id": ACTION["action_id"],
        "descriptor_id": ACTION["descriptor_id"],
        "qualification_nonce": qualification_nonce,
        "qualifier_call_count": 1,
        "probe_call_count": 1,
        "valid": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    for key, wanted in common_terminal.items():
        if terminal.get(key) != wanted:
            mismatches.append(f"terminal {key} differs")

    driver = terminal.get("probe")
    if not isinstance(driver, Mapping):
        mismatches.append("terminal driver evidence missing")
        driver = {}
    if terminal.get("driver") != driver:
        mismatches.append("terminal driver/probe mirror differs")
    try:
        _validate_readiness(terminal.get("readiness"))
    except QualifierError as error:
        mismatches.append(str(error))
    forbidden = driver.get("forbidden_commands")
    if not isinstance(forbidden, Mapping) or forbidden != {
        "drf": False,
        "dtm": False,
        "lut": False,
        "ptlw": False,
        "command_0x86": False,
    }:
        mismatches.append("terminal forbidden-command evidence differs")

    strict_driver = {
        "spi_hz": pack.PROBE_SPI_HZ,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": "none",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "post_psr_command_sent": True,
        "post_psr_payload_hex": "4f6e",
        "pon_command_sent": True,
        "pof_command_sent": True,
        "pon_idle_completed": True,
        "pof_idle_completed": True,
        "command_trace": list(pack.PROBE_COMMAND_TRACE),
        "wire_event_count": pack.PROBE_WIRE_EVENT_COUNT,
        "wire_fnv1a": pack.PROBE_WIRE_FNV1A,
    }
    for key, wanted in strict_driver.items():
        if driver.get(key) != wanted:
            mismatches.append(f"terminal driver {key} differs")
    if driver.get("command_counts") != {
        "pon": 1,
        "pof": 1,
        "drf": 0,
        "dtm": 0,
        "lut": 0,
        "ptlw": 0,
        "command_0x86": 0,
        "visible_refresh_requests": 0,
    }:
        mismatches.append("terminal command counts differ")
    safe_finish = driver.get("safe_finish")
    if not isinstance(safe_finish, Mapping):
        mismatches.append("terminal safe-finish evidence is missing")
        safe_finish = {}
    if safe_finish.get("busy_before_pins_low") != 1:
        mismatches.append("safe-finish BUSY before pins-low differs")
    final_gpio = safe_finish.get("final_gpio", {})
    if not isinstance(final_gpio, Mapping) or any(
        final_gpio.get(pin) != 0
        for pin in ("rst", "cs1", "cs2", "sck", "dc", "mosi")
    ):
        mismatches.append("safe-finish panel outputs are not all LOW")

    success = (
        not mismatches
        and terminal.get("terminal_state") == "COMPLETE"
        and terminal.get("result") is True
        and driver.get("valid") is True
        and driver.get("running") is False
        and driver.get("pon_busy_seen") is True
        and driver.get("pof_busy_seen") is True
        and driver.get("pon_gate_entry") == 1
        and driver.get("pof_gate_entry") == 1
    )
    if not success and not mismatches:
        mismatches.append("terminal did not satisfy complete PON/POF success")
    outcome = "complete_pass" if success else "fault_locked_consumed"
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": f"{KIND_PREFIX}-result",
            "created_at": _now(),
            "firmware_sha256": FIRMWARE_BIN_SHA256,
            "boot_nonce": boot_nonce,
            "qualification_nonce": qualification_nonce,
            "action": deepcopy(ACTION),
            "claim_file": str(claim_file.resolve()),
            "qualification_attempt_file": str(qualification_attempt_file.resolve()),
            "output_reservation_file": str(reservation_file.resolve()),
            "terminal_report": (
                None
                if observed_terminal is None
                else deepcopy(dict(observed_terminal))
            ),
            "terminal_mismatches": mismatches,
            "terminal_poll_errors": terminal_poll_errors,
            "transcript": transcript,
            "network": {
                "get": sum(item["method"] == "GET" for item in transcript),
                "qualify_post": 1,
                "arm_post": 1,
                "execute_post": 1,
            },
            "outcome": outcome,
            "visible_refresh_requests": 0,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "action_must_not_be_retried": True,
        }
    )
    _write_new(output, evidence)
    if not success:
        raise QualifierError(
            "PON/POF probe faulted; evidence was written and action must not be retried"
        )
    return evidence


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("dry-validate")
    diagnostic = sub.add_parser("diagnose-j2-off")
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument("--output", type=Path, required=True)
    salvage = sub.add_parser("salvage-fault")
    salvage.add_argument("--base-url", required=True)
    salvage.add_argument("--confirm-j2-off", action="store_true", required=True)
    salvage.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    salvage.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=2.0)
    run.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
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
            )
        elif args.command == "salvage-fault":
            value = salvage_fault(
                args.base_url,
                claims=args.claims,
                output=args.output,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                claims=args.claims,
                output=args.output,
                confirm_j2_on=args.confirm_j2_on,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except QualifierError as error:
        print(f"PON/POF qualifier error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
