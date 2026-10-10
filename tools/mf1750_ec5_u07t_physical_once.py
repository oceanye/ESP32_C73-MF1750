#!/usr/bin/env python3
"""Fail-closed one-shot runner for independent technical-only EC5 U07T."""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_u07t_identity as identity  # noqa: E402
from tools import mf1750_ec5_u07t_prerequisites as prereq  # noqa: E402
from tools import mf1750_ec5_u07t_release as release  # noqa: E402


SCHEMA_VERSION = 1
CLASSIFICATION = "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
DIAGNOSTIC_KIND = "mf1750-ec5-u07t-j2-off-diagnostic"
INITIAL_STATE_KIND = "mf1750-ec5-u07t-initial-white-attestation"
RESULT_KIND = "mf1750-ec5-u07t-physical-once-result"
CLAIM_KIND = "mf1750-ec5-u07t-permanent-technical-claim"
DEFAULT_TECHNICAL_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_u07t_technical_claims"
)
DEFAULT_FORMAL_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_claim_registry"
)
ENDPOINTS = {
    "version": "/api/ec5/version",
    "manifest": "/api/ec5/manifest",
    "status": "/api/ec5/status",
    "report": "/api/ec5/report",
    "arm": "/api/ec5/arm",
    "execute": "/api/ec5/execute",
}
ARM_INTENT = "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3"
SAFETY_SCOPE = "accidental_post_interlock_not_hardware_authorization"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_COUNT = 40
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
NONCE_RE = re.compile(r"[0-9a-f]{16}\Z")


class U07TPhysicalError(RuntimeError):
    """The U07T host contract failed closed."""


class U07TReadError(U07TPhysicalError):
    """One HTTP exchange failed before a valid response was obtained."""


@dataclass(frozen=True)
class ReleaseContext:
    release_file: Path
    root: Mapping[str, Any]
    panel: Mapping[str, str]
    binary_path: Path
    binary_sha256: str
    elf_path: Path
    elf_sha256: str
    release_canonical_sha256: str


def canonical_json_bytes(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def _sha(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _read(path: Path, *, label: str, maximum: int = 64 << 20) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise U07TPhysicalError(f"{label} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise U07TPhysicalError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise U07TPhysicalError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise U07TPhysicalError(f"{label} changed while read")
    return payload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise U07TPhysicalError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                U07TPhysicalError(f"{label} contains {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise U07TPhysicalError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise U07TPhysicalError(f"{label} root must be an object")
    return value


def _keys(value: Any, wanted: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != wanted:
        raise U07TPhysicalError(f"{label} fields differ")
    return value


def _nonce(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or NONCE_RE.fullmatch(value) is None:
        raise U07TPhysicalError(f"{label} is invalid")
    return value


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise U07TPhysicalError(f"{label} is invalid")
    return value


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return {**deepcopy(dict(unsigned)), "integrity": {"canonical_sha256": _sha(unsigned)}}


def _validate_integrity(value: Mapping[str, Any], *, label: str) -> None:
    integrity_value = value.get("integrity")
    if not isinstance(integrity_value, Mapping) or set(integrity_value) != {
        "canonical_sha256"
    }:
        raise U07TPhysicalError(f"{label} integrity fields differ")
    unsigned = dict(value)
    unsigned.pop("integrity")
    if integrity_value["canonical_sha256"] != _sha(unsigned):
        raise U07TPhysicalError(f"{label} integrity differs")


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    payload = canonical_json_bytes(value)
    path = Path(path)
    try:
        parent = path.parent.resolve(strict=True)
        target = parent / path.name
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise U07TPhysicalError(f"could not publish {path.name}: {error}") from error
    return payload


def load_release(release_file: Path, panel_file: Path) -> ReleaseContext:
    if not identity.EXECUTION_ELIGIBLE:
        raise U07TPhysicalError(
            "U07T identity was invalidated by an intervening visible refresh"
        )
    release_file = Path(release_file)
    try:
        root = release.validate_release(release_file.parent)
    except release.U07TReleaseError as error:
        raise U07TPhysicalError(f"U07T release replay failed: {error}") from error
    if release_file.name != release.MANIFEST_FILE:
        raise U07TPhysicalError("release filename differs")
    try:
        panel = json.loads(_read(panel_file, label="panel", maximum=64 << 10))
    except json.JSONDecodeError as error:
        raise U07TPhysicalError(f"panel is invalid JSON: {error}") from error
    if panel != root["panel"]:
        raise U07TPhysicalError("panel differs from release")
    variant = root["variant"]
    return ReleaseContext(
        release_file=release_file.resolve(strict=True),
        root=root,
        panel=panel,
        binary_path=(release_file.parent / variant["firmware"]["file"]).resolve(
            strict=True
        ),
        binary_sha256=variant["firmware"]["sha256"],
        elf_path=(release_file.parent / variant["elf"]["file"]).resolve(strict=True),
        elf_sha256=variant["elf"]["sha256"],
        release_canonical_sha256=root["integrity"]["canonical_sha256"],
    )


def required_authorization() -> str:
    return (
        "AUTHORIZE_ONE_VISIBLE_EC5_U07T_TECHNICAL__ACTION_"
        + identity.FROZEN_ACTION_ID.upper()
        + AUTHORIZATION_SUFFIX
    )


def _base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or not parsed.netloc or parsed.path not in ("", "/"):
        raise U07TPhysicalError("base URL must be an HTTP origin")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise U07TPhysicalError("base URL must not contain credentials/query/fragment")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[Mapping[str, Any], bytes]:
    if method not in ("GET", "POST") or path not in ENDPOINTS.values():
        raise U07TPhysicalError("HTTP request differs from frozen routes")
    request = urllib.request.Request(
        _base_url(base_url) + path,
        data=None if method == "GET" else b"",
        method=method,
        headers=dict(headers or {}),
    )
    try:
        with _urlopen(request, timeout=timeout_seconds) as response:
            status = response.getcode()
            payload = response.read((4 << 20) + 1)
    except (OSError, urllib.error.URLError) as error:
        raise U07TReadError(f"{method} {path} failed: {error}") from error
    if status not in (200, 201, 202) or len(payload) > 4 << 20:
        raise U07TReadError(f"{method} {path} response is invalid")
    return _decode(payload, label=f"{method} {path}"), payload


def _device_nvs_contract() -> dict[str, Any]:
    value = identity.nvs_contract()
    value["formal_u07"]["never_write_or_clear"] = True
    return value


def _validate_common(value: Mapping[str, Any], *, terminal: bool) -> None:
    expected = {
        "schema_version": 3,
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "classification": CLASSIFICATION,
        "formal_u07_unclaimed_and_virgin": True,
        "nvs_contract": _device_nvs_contract(),
        "formal_store_ready": True,
        "formal_u04_key_present": True,
        "formal_u04_phase": 2,
        "formal_u04_match": True,
        "formal_u07_key_present": False,
        "formal_u07_phase": 0,
        "formal_u07_match": True,
        "formal_prerequisites_match": True,
        "active_store_ready": True,
        "migration_ready": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"device {key} differs")
    if terminal:
        if value.get("active_key_present") is not True or value.get("active_phase") != 2 or value.get("active_virgin") is not False:
            raise U07TPhysicalError("terminal technical NVS evidence differs")
    elif value.get("active_key_present") is not False or value.get("active_phase") != 0 or value.get("active_virgin") is not True:
        raise U07TPhysicalError("virgin technical NVS evidence differs")


def _validate_version(value: Mapping[str, Any], *, terminal: bool = False) -> None:
    if value.get("kind") != "mf1750-ec5-u07t-version" or value.get("driver_api_version") != DRIVER_API_VERSION or value.get("candidate_code") != "0x7" or value.get("layout_id") != identity.LAYOUT_ID:
        raise U07TPhysicalError("device version identity differs")
    for key, wanted in {
        "automatic_execute": False, "startup_refresh": False,
        "raw_frame_ingress": False, "dither": False, "lut_modified": False,
        "retry": False, "recovery": False, "persistent_claim": True,
        "arm_required": True, "safety_scope": SAFETY_SCOPE,
    }.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"device version {key} differs")
    _validate_common(value, terminal=terminal)


def _validate_manifest(value: Mapping[str, Any], *, terminal: bool = False) -> None:
    expected = {
        "kind": "mf1750-ec5-u07t-compiled-fixture-manifest",
        "scope": "technical_descriptive_not_formal_qualification",
        "layout_id": identity.LAYOUT_ID, "test_id": identity.TEST_ID,
        "action_id": identity.FROZEN_ACTION_ID, "candidate_code": 7,
        "candidate_code_hex": "0x7", "intended_initial_code": 1,
        "sequence_class": "white_initial_single_technical_probe",
        "repetition": 1, "width": 1024, "height": 600,
        "frame_bytes": 307200,
        "pixel_packing": "row_major_4bpp_even_x_high_nibble",
        "roi_cs1": {"x0": 224, "x1": 288, "y0": 268, "y1": 332},
        "roi_cs2": {"x0": 736, "x1": 800, "y0": 268, "y1": 332},
        "known_white_pixels": 606208, "candidate_pixels": 8192,
        "frame_sha256": identity.FRAME_SHA256,
        "frame_fnv1a": f"0x{identity.FRAME_FNV1A:08x}",
        "cs1_dtm_sha256": identity.DTM_SHA256,
        "cs1_dtm_fnv1a": f"0x{identity.DTM_FNV1A:08x}",
        "cs2_dtm_sha256": identity.DTM_SHA256,
        "cs2_dtm_fnv1a": f"0x{identity.DTM_FNV1A:08x}",
        "mapping_cs1": [0, 0, 0, 0], "mapping_cs2": [1, 0, 0, 0],
        "otp_mode": "existing_on_chip_otp_unchanged", "dither": False,
        "spatial_mixing": False, "raw_frame_ingress": False,
        "startup_refresh": False, "retry": False, "recovery": False,
        "lut_modified": False, "manifest_payload_sha256": None,
        "binary_sha256": None, "external_build_sidecar_required": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"device manifest {key} differs")
    _validate_common(value, terminal=terminal)


def _validate_status(
    value: Mapping[str, Any], *, boot_nonce: str | None, terminal: bool, busy: int | None
) -> str:
    if value.get("kind") != "mf1750-ec5-u07t-status" or value.get("layout_id") != identity.LAYOUT_ID or value.get("test_id") != identity.TEST_ID or value.get("action_id") != identity.FROZEN_ACTION_ID:
        raise U07TPhysicalError("device status identity differs")
    nonce = _nonce(value.get("boot_nonce"), label="boot nonce")
    if boot_nonce is not None and nonce != boot_nonce:
        raise U07TPhysicalError("boot nonce changed")
    _validate_common(value, terminal=terminal)
    expected = {
        "fixture_self_check_passed": True,
        "driver_fixture_guard_passed": True,
        "claim_store_ready": True,
        "gpio_initialized": True,
        "rst": 0, "cs": 0, "cs2": 0,
    }
    if terminal:
        expected |= {"persistent_phase": 2, "arm_request_count": 1,
                     "execute_consumed": True, "execute_pending": False,
                     "execute_request_count": 1, "driver_call_count": 1}
    else:
        expected |= {"state": "ready", "persistent_phase": 0,
                     "arm_request_count": 0, "execute_consumed": False,
                     "execute_pending": False, "execute_request_count": 0,
                     "driver_call_count": 0}
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"device status {key} differs")
    if busy is not None and value.get("busy") != busy:
        raise U07TPhysicalError("BUSY level differs from power-state gate")
    return nonce


def _validate_virgin_report(value: Mapping[str, Any], *, boot_nonce: str) -> None:
    expected = {
        "kind": "mf1750-ec5-u07t-report", "valid": False,
        "test_id": identity.TEST_ID, "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "classification": CLASSIFICATION, "boot_nonce": boot_nonce,
        "action_id": identity.FROZEN_ACTION_ID, "candidate_code": 7,
        "terminal_state": "NOT_EXECUTED", "error": "no_execute_report",
        "driver_fixture_guard_passed": True, "execute_consumed": False,
        "driver_called": False, "persistent_phase": 0,
        "formal_u07_unclaimed_and_virgin": True,
        "no_retry": True, "no_recovery": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"virgin report {key} differs")
    _validate_common(value, terminal=False)


def _read_snapshot(
    base_url: str,
    *,
    timeout_seconds: float,
    _urlopen: Callable[..., Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, bytes]]:
    values, payloads = {}, {}
    for name in ("version", "manifest", "status", "report"):
        values[name], payloads[name] = _request(
            base_url, ENDPOINTS[name], timeout_seconds=timeout_seconds, _urlopen=_urlopen
        )
    return values, payloads


def _validate_virgin_snapshot(
    values: Mapping[str, Mapping[str, Any]], *, busy: int
) -> str:
    status = values["status"]
    nonce = _validate_status(status, boot_nonce=None, terminal=False, busy=busy)
    _validate_version(values["version"])
    _validate_manifest(values["manifest"])
    _validate_virgin_report(values["report"], boot_nonce=nonce)
    return nonce


def _raw_records(payloads: Mapping[str, bytes]) -> list[dict[str, Any]]:
    return [
        {
            "endpoint": name,
            "path": ENDPOINTS[name],
            "status": 200,
            "bytes": len(payloads[name]),
            "sha256": _sha(payloads[name]),
            "body_base64": base64.b64encode(payloads[name]).decode("ascii"),
        }
        for name in ("version", "manifest", "status", "report")
    ]


def _replay_raw(records: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list) or len(records) != 4:
        raise U07TPhysicalError("diagnostic raw records differ")
    values = {}
    for record, name in zip(records, ("version", "manifest", "status", "report")):
        if not isinstance(record, Mapping) or record.get("endpoint") != name or record.get("path") != ENDPOINTS[name] or record.get("status") != 200:
            raise U07TPhysicalError("diagnostic raw endpoint differs")
        try:
            payload = base64.b64decode(record.get("body_base64"), validate=True)
        except (TypeError, ValueError) as error:
            raise U07TPhysicalError("diagnostic raw base64 differs") from error
        if record.get("bytes") != len(payload) or record.get("sha256") != _sha(payload):
            raise U07TPhysicalError("diagnostic raw digest differs")
        values[name] = _decode(payload, label=f"diagnostic {name}")
    return values


def _formal_absence(registry: Path) -> dict[str, Any]:
    try:
        return prereq.formal_u07_claim_absence(registry)
    except prereq.U07TPrerequisiteError as error:
        raise U07TPhysicalError(str(error)) from error


def _technical_claim_path(context: ReleaseContext, registry: Path) -> Path:
    try:
        formal = Path(context.root["prerequisite_inputs"]["formal_claim_registry"])
        _formal, technical = prereq.distinct_claim_registries(formal, registry)
    except prereq.U07TPrerequisiteError as error:
        raise U07TPhysicalError(str(error)) from error
    return technical / f"{identity.FROZEN_ACTION_ID}.json"


def _require_technical_unclaimed(context: ReleaseContext, registry: Path) -> Path:
    claim = _technical_claim_path(context, registry)
    try:
        claim.lstat()
    except FileNotFoundError:
        return claim
    except OSError as error:
        raise U07TPhysicalError(f"could not inspect technical claim: {error}") from error
    raise U07TPhysicalError("U07T technical action is already claimed")


def describe(context: ReleaseContext) -> dict[str, Any]:
    return {
        "classification": CLASSIFICATION,
        "action_id": identity.FROZEN_ACTION_ID,
        "required_authorization": required_authorization(),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "formal_u07_action_id": identity.FORMAL_U07_ACTION_ID,
        "formal_u07_qualification_inferred": False,
        "post_action_screen_remains_u07t_until_separate_recovery": True,
    }


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    confirm_j2_off: bool,
    evidence_file: Path,
    technical_claim_registry: Path = DEFAULT_TECHNICAL_CLAIM_REGISTRY,
    formal_claim_registry: Path = DEFAULT_FORMAL_CLAIM_REGISTRY,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not confirm_j2_off:
        raise U07TPhysicalError("J2-off confirmation is required")
    configured_formal = Path(context.root["prerequisite_inputs"]["formal_claim_registry"])
    if configured_formal.resolve(strict=True) != Path(formal_claim_registry).resolve(strict=True):
        raise U07TPhysicalError("formal claim registry differs from release")
    formal_before = _formal_absence(formal_claim_registry)
    technical_claim = _require_technical_unclaimed(context, technical_claim_registry)
    values, payloads = _read_snapshot(
        base_url, timeout_seconds=timeout_seconds, _urlopen=_urlopen
    )
    boot_nonce = _validate_virgin_snapshot(values, busy=0)
    unsigned = {
        "schema_version": SCHEMA_VERSION, "kind": DIAGNOSTIC_KIND,
        "classification": CLASSIFICATION, "created_at": _now(),
        "action_id": identity.FROZEN_ACTION_ID,
        "release_file": str(context.release_file),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "elf_sha256": context.elf_sha256,
        "compiled_identity_report": deepcopy(context.root["compiled_identity_report"]),
        "panel": deepcopy(dict(context.panel)), "boot_nonce": boot_nonce,
        "formal_u07_claim_absence_before": formal_before,
        "technical_claim_file": str(technical_claim),
        "technical_claim_exists": False,
        "j2_confirmed_off": True, "get_requests": 4, "post_requests": 0,
        "claim_created": False, "raw_responses": _raw_records(payloads),
        "state": "diagnostic_pass_j2_off_no_mutation",
        "formal_u07_qualification_inferred": False,
    }
    result = _seal(unsigned)
    _write_new(evidence_file, result)
    return result


def validate_diagnostic(
    context: ReleaseContext,
    diagnostic_file: Path,
    *,
    formal_claim_registry: Path = DEFAULT_FORMAL_CLAIM_REGISTRY,
) -> dict[str, Any]:
    root = _decode(_read(diagnostic_file, label="U07T diagnostic"), label="U07T diagnostic")
    _validate_integrity(root, label="U07T diagnostic")
    expected = {
        "schema_version": SCHEMA_VERSION, "kind": DIAGNOSTIC_KIND,
        "classification": CLASSIFICATION, "action_id": identity.FROZEN_ACTION_ID,
        "release_file": str(context.release_file),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256, "elf_sha256": context.elf_sha256,
        "compiled_identity_report": context.root["compiled_identity_report"],
        "panel": dict(context.panel), "j2_confirmed_off": True,
        "get_requests": 4, "post_requests": 0, "claim_created": False,
        "state": "diagnostic_pass_j2_off_no_mutation",
        "formal_u07_qualification_inferred": False,
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise U07TPhysicalError(f"diagnostic {key} differs")
    boot_nonce = _nonce(root.get("boot_nonce"), label="diagnostic boot nonce")
    if (
        _validate_virgin_snapshot(_replay_raw(root.get("raw_responses")), busy=0)
        != boot_nonce
    ):
        raise U07TPhysicalError("diagnostic raw boot nonce differs")
    if root["formal_u07_claim_absence_before"] != _formal_absence(formal_claim_registry):
        raise U07TPhysicalError("diagnostic formal claim absence differs")
    return dict(root)


def validate_initial_white_attestation(
    context: ReleaseContext, evidence_file: Path
) -> dict[str, Any]:
    root = _decode(_read(evidence_file, label="U07T initial white attestation"), label="U07T initial white attestation")
    _validate_integrity(root, label="U07T initial white attestation")
    expected = {
        "schema_version": 1, "kind": INITIAL_STATE_KIND,
        "classification": CLASSIFICATION, "panel": dict(context.panel),
        "bound_after_u04_white_action_id": identity.AFTER_U04_WHITE_ACTION_ID,
        "bound_after_u04_white_result_file_sha256": identity.AFTER_U04_WHITE_RESULT_FILE_SHA256,
        "bound_after_u04_white_observation_file_sha256": identity.AFTER_U04_WHITE_OBSERVATION_FILE_SHA256,
        "full_panel_white": True,
        "no_intervening_visible_refresh_since_bound_white": True,
        "electrical_normal": True, "hardware_authorization": False,
        "formal_u07_qualification_inferred": False,
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise U07TPhysicalError(f"initial white attestation {key} differs")
    if not isinstance(root.get("observed_at"), str) or not isinstance(root.get("operator_report_verbatim"), str) or not root["operator_report_verbatim"]:
        raise U07TPhysicalError("initial white attestation operator fields differ")
    return dict(root)


def _headers(boot_nonce: str, *, intent: str, arm_nonce: str | None = None) -> dict[str, str]:
    headers = {
        "X-EC5-Build-Tag": identity.BUILD_TAG,
        "X-EC5-Test-Id": identity.TEST_ID,
        "X-EC5-Action-Id": identity.FROZEN_ACTION_ID,
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _create_claim(
    context: ReleaseContext,
    *,
    registry: Path,
    attempt_id: str,
    boot_nonce: str,
    authorization_sha256: str,
    diagnostic_file: Path,
    initial_state_file: Path,
    formal_before: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes, Path]:
    claim_path = _require_technical_unclaimed(context, registry)
    try:
        claim_path.parent.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        pass
    except OSError as error:
        raise U07TPhysicalError(f"could not create technical claim registry: {error}") from error
    diagnostic_payload = _read(diagnostic_file, label="diagnostic claim binding")
    initial_payload = _read(initial_state_file, label="initial-state claim binding")
    claim = {
        "schema_version": 1, "kind": CLAIM_KIND,
        "registry_id": identity.TECHNICAL_CLAIM_REGISTRY_ID,
        "classification": CLASSIFICATION, "created_at": _now(),
        "attempt_id": attempt_id, "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256, "panel": dict(context.panel),
        "boot_nonce": boot_nonce,
        "authorization_confirmation_sha256": authorization_sha256,
        "diagnostic_file": str(Path(diagnostic_file).resolve(strict=True)),
        "diagnostic_file_sha256": _sha(diagnostic_payload),
        "initial_state_file": str(Path(initial_state_file).resolve(strict=True)),
        "initial_state_file_sha256": _sha(initial_payload),
        "formal_u07_claim_absence_before_first_post": deepcopy(dict(formal_before)),
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
        "maximum_arm_posts": 1, "maximum_execute_posts": 1,
        "automatic_retry": False, "automatic_recovery": False,
        "formal_u07_action_consumed": False,
        "formal_u07_qualification_inferred": False,
    }
    payload = _write_new(claim_path, claim)
    return claim, payload, claim_path


def _validate_arm(value: Mapping[str, Any], *, boot_nonce: str) -> str:
    expected = {
        "accepted": True, "armed": True, "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG, "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "classification": CLASSIFICATION, "boot_nonce": boot_nonce,
        "persistent_phase": 1, "migration_ready": True,
        "formal_u07_unclaimed_and_virgin": True, "safety_scope": SAFETY_SCOPE,
        "not_hardware_authorization": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"ARM response {key} differs")
    return _nonce(value.get("arm_nonce"), label="arm nonce")


def _validate_execute(value: Mapping[str, Any], *, boot_nonce: str) -> None:
    expected = {
        "accepted": True, "job_id": 1, "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG, "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "classification": CLASSIFICATION, "boot_nonce": boot_nonce,
        "execute_consumed": True, "persistent_phase": 2,
        "migration_ready": True, "formal_u07_unclaimed_and_virgin": True,
        "no_retry": True, "no_recovery": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"EXECUTE response {key} differs")


def _validate_driver(driver: Mapping[str, Any], *, passed: bool) -> None:
    if driver.get("driver_evidence_schema_version") != 2 or driver.get("operation_id") != 1 or driver.get("input_fnv1a") != identity.FRAME_FNV1A or driver.get("cs1_dtm_fnv1a") != identity.DTM_FNV1A or driver.get("cs2_dtm_fnv1a") != identity.DTM_FNV1A:
        raise U07TPhysicalError("terminal driver identity differs")
    safe = driver.get("safe_finish")
    if not isinstance(safe, Mapping) or safe.get("final_gpio", {}).get("rst") != 0 or safe.get("final_gpio", {}).get("cs") != 0 or safe.get("final_gpio", {}).get("cs2") != 0:
        raise U07TPhysicalError("terminal driver safe finish differs")
    if passed:
        for key, wanted in {
            "valid": True, "running": False, "sequence_ok": True,
            "wait_timeout": False, "busy_assertion_missing": False,
            "mapping_applied": True, "pon_busy_seen": True,
            "drf_busy_seen": True, "pof_busy_seen": True,
            "post_psr_busy_seen": False, "pre_command_idle_failure": False,
            "failure_stage": "none", "failure_code": 0, "spi_hz": 1_000_000,
            "timeout_stage": "none", "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
        }.items():
            if driver.get(key) != wanted:
                raise U07TPhysicalError(f"terminal driver {key} differs")


def _validate_terminal_report(value: Mapping[str, Any], *, boot_nonce: str) -> bool:
    expected = {
        "kind": "mf1750-ec5-u07t-report", "valid": True,
        "test_id": identity.TEST_ID, "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "classification": CLASSIFICATION, "boot_nonce": boot_nonce,
        "action_id": identity.FROZEN_ACTION_ID, "candidate_code": 7,
        "job_id": 1, "driver_fixture_guard_passed": True,
        "execute_consumed": True, "driver_called": True,
        "driver_call_count": 1, "persistent_phase": 2,
        "formal_u07_unclaimed_and_virgin": True,
        "no_retry": True, "no_recovery": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise U07TPhysicalError(f"terminal report {key} differs")
    _validate_common(value, terminal=True)
    passed = value.get("terminal_state") == "completed" and value.get("result") is True
    if not passed and not (value.get("terminal_state") == "fault_locked" and value.get("result") is False):
        raise U07TPhysicalError("terminal report state/result differs")
    queued = _integer(value.get("job_queued_at_ms"), label="queued time", minimum=1)
    started = _integer(value.get("job_started_at_ms"), label="started time", minimum=queued)
    _integer(value.get("job_finished_at_ms"), label="finished time", minimum=started)
    driver = value.get("driver")
    if not isinstance(driver, Mapping):
        raise U07TPhysicalError("terminal driver evidence is missing")
    _validate_driver(driver, passed=passed)
    return passed


def run_once(
    context: ReleaseContext,
    base_url: str,
    *,
    authorization: str,
    diagnostic_file: Path,
    initial_state_file: Path,
    result_file: Path,
    confirm_current_clean_white_no_intervening_refresh: bool,
    technical_claim_registry: Path = DEFAULT_TECHNICAL_CLAIM_REGISTRY,
    formal_claim_registry: Path = DEFAULT_FORMAL_CLAIM_REGISTRY,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if authorization != required_authorization():
        raise U07TPhysicalError("authorization phrase differs")
    if not confirm_current_clean_white_no_intervening_refresh:
        raise U07TPhysicalError(
            "current clean-white/no-intervening-refresh confirmation is required"
        )
    if poll_count <= 0 or poll_interval_seconds < 0:
        raise U07TPhysicalError("poll controls are invalid")
    diagnostic = validate_diagnostic(
        context, diagnostic_file, formal_claim_registry=formal_claim_registry
    )
    initial = validate_initial_white_attestation(context, initial_state_file)
    formal_before = _formal_absence(formal_claim_registry)
    _require_technical_unclaimed(context, technical_claim_registry)
    values, _payloads = _read_snapshot(
        base_url, timeout_seconds=timeout_seconds, _urlopen=_urlopen
    )
    boot_nonce = _validate_virgin_snapshot(values, busy=1)
    if boot_nonce != diagnostic["boot_nonce"]:
        raise U07TPhysicalError("J2-on preflight is not the diagnostic boot")
    attempt_id = str(uuid.uuid4())
    authorization_sha = _sha(authorization.encode("utf-8"))
    claim, claim_payload, claim_path = _create_claim(
        context, registry=technical_claim_registry, attempt_id=attempt_id,
        boot_nonce=boot_nonce, authorization_sha256=authorization_sha,
        diagnostic_file=diagnostic_file, initial_state_file=initial_state_file,
        formal_before=formal_before,
    )
    started_at = _now()
    post_requests = 0
    observations: list[dict[str, Any]] = []
    final_status: Mapping[str, Any] | None = None
    final_report: Mapping[str, Any] | None = None
    outcome = "unknown_do_not_retry_or_recover"
    error_text: str | None = None
    try:
        post_requests = 1
        arm, _ = _request(
            base_url, ENDPOINTS["arm"], method="POST",
            headers=_headers(boot_nonce, intent=ARM_INTENT),
            timeout_seconds=timeout_seconds, _urlopen=_urlopen,
        )
        arm_nonce = _validate_arm(arm, boot_nonce=boot_nonce)
        post_requests = 2
        executed, _ = _request(
            base_url, ENDPOINTS["execute"], method="POST",
            headers=_headers(boot_nonce, intent=EXECUTE_INTENT, arm_nonce=arm_nonce),
            timeout_seconds=timeout_seconds, _urlopen=_urlopen,
        )
        _validate_execute(executed, boot_nonce=boot_nonce)
        for poll in range(1, poll_count + 1):
            try:
                status, _ = _request(
                    base_url, ENDPOINTS["status"], timeout_seconds=timeout_seconds,
                    _urlopen=_urlopen,
                )
                _validate_status(status, boot_nonce=boot_nonce, terminal=True, busy=None)
                observations.append({"poll": poll, "state": status.get("state")})
                if status.get("state") in ("completed", "fault_locked"):
                    report_value, _ = _request(
                        base_url, ENDPOINTS["report"], timeout_seconds=timeout_seconds,
                        _urlopen=_urlopen,
                    )
                    passed = _validate_terminal_report(report_value, boot_nonce=boot_nonce)
                    final_status, final_report = status, report_value
                    outcome = (
                        "complete_pass_technical_not_qualified"
                        if passed else "complete_driver_failure_no_retry"
                    )
                    break
            except U07TReadError as read_error:
                observations.append({"poll": poll, "read_error": str(read_error)})
            if poll < poll_count and poll_interval_seconds:
                time.sleep(poll_interval_seconds)
        if final_report is None:
            error_text = "terminal report not obtained; do not retry or recover"
    except U07TPhysicalError as error:
        error_text = str(error)
    formal_after = _formal_absence(formal_claim_registry)
    finished_at = _now()
    unsigned = {
        "schema_version": SCHEMA_VERSION, "kind": RESULT_KIND,
        "classification": CLASSIFICATION, "attempt_id": attempt_id,
        "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256, "panel": dict(context.panel),
        "boot_nonce": boot_nonce,
        "authorization_confirmation_sha256": authorization_sha,
        "diagnostic": {
            "file": str(Path(diagnostic_file).resolve(strict=True)),
            "file_sha256": _sha(_read(diagnostic_file, label="result diagnostic")),
        },
        "initial_state": {
            "file": str(Path(initial_state_file).resolve(strict=True)),
            "file_sha256": _sha(_read(initial_state_file, label="result initial state")),
            "no_intervening_visible_refresh_since_bound_white": initial[
                "no_intervening_visible_refresh_since_bound_white"
            ],
            "current_clean_white_no_intervening_refresh_confirmed": True,
        },
        "claim": {
            "filename": claim_path.name, "file_sha256": _sha(claim_payload),
            "attempt_id": attempt_id, "state": claim["state"],
        },
        "formal_u07_claim_absence_before": formal_before,
        "formal_u07_claim_absence_after": formal_after,
        "started_at": started_at, "finished_at": finished_at,
        "outcome": outcome, "error": error_text, "post_requests": post_requests,
        "maximum_arm_posts": 1, "maximum_execute_posts": 1,
        "automatic_retry": False, "automatic_recovery": False,
        "observations": observations, "final_status": final_status,
        "final_report": final_report,
        "formal_u07_action_consumed": False,
        "formal_u07_qualification_inferred": False,
        "state": "technical_authorization_permanently_consumed_do_not_rerun",
        "post_action_screen_state": "U07T_REMAINS_UNTIL_SEPARATE_RECOVERY",
    }
    result = _seal(unsigned)
    _write_new(result_file, result)
    return result


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    technical_claim_registry: Path = DEFAULT_TECHNICAL_CLAIM_REGISTRY,
    formal_claim_registry: Path = DEFAULT_FORMAL_CLAIM_REGISTRY,
) -> dict[str, Any]:
    root = _decode(_read(result_file, label="U07T result"), label="U07T result")
    _validate_integrity(root, label="U07T result")
    expected = {
        "schema_version": SCHEMA_VERSION, "kind": RESULT_KIND,
        "classification": CLASSIFICATION, "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256, "panel": dict(context.panel),
        "authorization_confirmation_sha256": _sha(required_authorization().encode("utf-8")),
        "maximum_arm_posts": 1, "maximum_execute_posts": 1,
        "automatic_retry": False, "automatic_recovery": False,
        "formal_u07_action_consumed": False,
        "formal_u07_qualification_inferred": False,
        "state": "technical_authorization_permanently_consumed_do_not_rerun",
        "post_action_screen_state": "U07T_REMAINS_UNTIL_SEPARATE_RECOVERY",
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise U07TPhysicalError(f"result {key} differs")
    diagnostic_path = Path(root["diagnostic"]["file"])
    if root["diagnostic"]["file_sha256"] != _sha(_read(diagnostic_path, label="bound diagnostic")):
        raise U07TPhysicalError("result diagnostic digest differs")
    validate_diagnostic(context, diagnostic_path, formal_claim_registry=formal_claim_registry)
    initial_path = Path(root["initial_state"]["file"])
    if root["initial_state"]["file_sha256"] != _sha(_read(initial_path, label="bound initial state")):
        raise U07TPhysicalError("result initial state digest differs")
    validate_initial_white_attestation(context, initial_path)
    if root["initial_state"].get(
        "current_clean_white_no_intervening_refresh_confirmed"
    ) is not True:
        raise U07TPhysicalError("result current-white confirmation differs")
    claim_path = _technical_claim_path(context, technical_claim_registry)
    claim_payload = _read(claim_path, label="technical permanent claim")
    if root["claim"]["filename"] != claim_path.name or root["claim"]["file_sha256"] != _sha(claim_payload) or root["claim"]["attempt_id"] != root["attempt_id"]:
        raise U07TPhysicalError("result claim binding differs")
    claim = _decode(claim_payload, label="technical permanent claim")
    if claim.get("attempt_id") != root["attempt_id"] or claim.get("action_id") != identity.FROZEN_ACTION_ID or claim.get("formal_u07_action_consumed") is not False:
        raise U07TPhysicalError("technical permanent claim differs")
    current_absence = _formal_absence(formal_claim_registry)
    if root["formal_u07_claim_absence_before"] != current_absence or root["formal_u07_claim_absence_after"] != current_absence:
        raise U07TPhysicalError("formal U07 claim absence result differs")
    outcome = root.get("outcome")
    if outcome == "complete_pass_technical_not_qualified":
        if root.get("post_requests") != 2 or root.get("error") is not None:
            raise U07TPhysicalError("complete technical result POST/error differs")
        _validate_status(root["final_status"], boot_nonce=root["boot_nonce"], terminal=True, busy=None)
        if not _validate_terminal_report(root["final_report"], boot_nonce=root["boot_nonce"]):
            raise U07TPhysicalError("complete technical result report failed")
    elif outcome not in {"complete_driver_failure_no_retry", "unknown_do_not_retry_or_recover"}:
        raise U07TPhysicalError("result outcome differs")
    if root.get("post_requests") not in (0, 1, 2):
        raise U07TPhysicalError("result POST count differs")
    return dict(root)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("describe", "diagnose-j2-off", "run", "validate"):
        item = sub.add_parser(name, allow_abbrev=False)
        item.add_argument("--release", type=Path, required=True)
        item.add_argument("--panel", type=Path, required=True)
        if name in ("diagnose-j2-off", "run"):
            item.add_argument("--base-url", required=True)
            item.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
        if name == "diagnose-j2-off":
            item.add_argument("--confirm-j2-off", action="store_true")
            item.add_argument("--evidence", type=Path, required=True)
            item.add_argument("--technical-claim-registry", type=Path, default=DEFAULT_TECHNICAL_CLAIM_REGISTRY)
            item.add_argument("--formal-claim-registry", type=Path, default=DEFAULT_FORMAL_CLAIM_REGISTRY)
        elif name == "run":
            item.add_argument("--authorization", required=True)
            item.add_argument("--diagnostic", type=Path, required=True)
            item.add_argument("--initial-state", type=Path, required=True)
            item.add_argument(
                "--confirm-current-clean-white-no-intervening-refresh",
                action="store_true",
            )
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--technical-claim-registry", type=Path, default=DEFAULT_TECHNICAL_CLAIM_REGISTRY)
            item.add_argument("--formal-claim-registry", type=Path, default=DEFAULT_FORMAL_CLAIM_REGISTRY)
            item.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
            item.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
        elif name == "validate":
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--technical-claim-registry", type=Path, default=DEFAULT_TECHNICAL_CLAIM_REGISTRY)
            item.add_argument("--formal-claim-registry", type=Path, default=DEFAULT_FORMAL_CLAIM_REGISTRY)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        context = load_release(args.release, args.panel)
        if args.command == "describe":
            report = describe(context)
        elif args.command == "diagnose-j2-off":
            report = diagnose_j2_off(
                context, args.base_url, confirm_j2_off=args.confirm_j2_off,
                evidence_file=args.evidence,
                technical_claim_registry=args.technical_claim_registry,
                formal_claim_registry=args.formal_claim_registry,
                timeout_seconds=args.timeout,
            )
        elif args.command == "run":
            report = run_once(
                context, args.base_url, authorization=args.authorization,
                diagnostic_file=args.diagnostic, initial_state_file=args.initial_state,
                result_file=args.result,
                confirm_current_clean_white_no_intervening_refresh=(
                    args.confirm_current_clean_white_no_intervening_refresh
                ),
                technical_claim_registry=args.technical_claim_registry,
                formal_claim_registry=args.formal_claim_registry,
                timeout_seconds=args.timeout, poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval,
            )
        else:
            report = validate_result(
                context, args.result,
                technical_claim_registry=args.technical_claim_registry,
                formal_claim_registry=args.formal_claim_registry,
            )
    except U07TPhysicalError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
