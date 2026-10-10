#!/usr/bin/env python3
"""Execute the fixed EC5 U04-vs-U05 comparison exactly once.

The runner has two physical phases.  ``diagnose-j2-off`` records exactly four
GETs and creates neither a claim nor a POST.  ``run`` replays that immutable
evidence, performs a fresh four-GET J2-on gate on the same boot nonce, creates
the permanent host claim, then sends at most one ARM and one EXECUTE POST.
There is no retry or recovery path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import urllib.parse
import urllib.request
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_u04_u05_compare_identity as identity  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_release as release_contract  # noqa: E402


SCHEMA_VERSION = 1
DIAGNOSTIC_KIND = "mf1750-ec5-u04-u05-compare-j2-off-diagnostic"
RESULT_KIND = "mf1750-ec5-u04-u05-compare-physical-once-result"
CLAIM_KIND = "mf1750-ec5-u04-u05-compare-permanent-claim"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-u04-u05-compare-claims-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_u04_u05_compare_claims"
)
ENDPOINTS = {
    "version": "/api/ec5/version",
    "manifest": "/api/ec5/manifest",
    "status": "/api/ec5/status",
    "report": "/api/ec5/report",
    "arm": "/api/ec5/arm",
    "execute": "/api/ec5/execute",
}
DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3"
ARM_INTENT = "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = (
    "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
)
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
MAX_JSON_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_COUNT = 40
DEFAULT_POLL_INTERVAL_SECONDS = 0.25


class ComparePhysicalError(RuntimeError):
    """A local, release, protocol, or immutable-evidence check failed."""


class ComparePhysicalReadError(ComparePhysicalError):
    """One device read failed; mutation retries remain forbidden."""


@dataclass(frozen=True)
class PrerequisiteFiles:
    corrected_u04_release: Path
    u04_result: Path
    u04_short_hold: Path
    white_result: Path
    white_observation: Path
    rc2g_binary: Path
    candidate_claim_registry: Path
    white_claim_registry: Path


@dataclass(frozen=True)
class ReleaseContext:
    path: Path
    root: Mapping[str, Any]
    variant: Mapping[str, Any]
    release_canonical_sha256: str
    binary_path: Path
    binary_sha256: str
    elf_path: Path
    elf_sha256: str
    panel: Mapping[str, str]
    prerequisites: Mapping[str, Any]
    prerequisite_files: PrerequisiteFiles


def canonical_json_bytes(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _read(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise ComparePhysicalError(f"{label} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise ComparePhysicalError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ComparePhysicalError(f"could not read {label}: {error}") from error
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ComparePhysicalError(f"{label} changed while read")
    return payload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComparePhysicalError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise ComparePhysicalError(f"{label} exceeds JSON limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ComparePhysicalError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparePhysicalError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise ComparePhysicalError(f"{label} root must be an object")
    return value


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ComparePhysicalError(f"{label} fields differ from contract")
    return value


def _hex64(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ComparePhysicalError(f"{label} must be lowercase SHA-256")
    return value


def _nonce(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 16
        or any(character not in "0123456789abcdef" for character in value)
        or value == "0" * 16
    ):
        raise ComparePhysicalError(f"{label} is not a 64-bit lowercase nonce")
    return value


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ComparePhysicalError(f"{label} is not an integer >= {minimum}")
    return value


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(unsigned))
    value["integrity"] = {"canonical_sha256": _sha(canonical_json_bytes(unsigned))}
    return value


def _validate_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {"canonical_sha256"}:
        raise ComparePhysicalError(f"{label} integrity is malformed")
    expected = _hex64(integrity["canonical_sha256"], label=f"{label} integrity")
    unsigned = dict(root)
    unsigned.pop("integrity")
    if _sha(canonical_json_bytes(unsigned)) != expected:
        raise ComparePhysicalError(f"{label} integrity differs")
    return expected


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    payload = canonical_json_bytes(value)
    path = Path(path)
    try:
        path.parent.resolve(strict=True)
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise ComparePhysicalError(f"could not create immutable {path}: {error}") from error
    return payload


def load_release(
    release_file: Path,
    panel_file: Path,
    prerequisite_files: PrerequisiteFiles,
) -> ReleaseContext:
    release_file = Path(release_file)
    try:
        root = release_contract.validate_release(release_file.parent)
        live_prerequisites = release_contract.load_prerequisites(
            corrected_release_file=prerequisite_files.corrected_u04_release,
            u04_result_file=prerequisite_files.u04_result,
            short_hold_file=prerequisite_files.u04_short_hold,
            white_result_file=prerequisite_files.white_result,
            white_observation_file=prerequisite_files.white_observation,
            panel_file=panel_file,
            rc2g_binary_file=prerequisite_files.rc2g_binary,
            candidate_claim_registry=prerequisite_files.candidate_claim_registry,
            white_claim_registry=prerequisite_files.white_claim_registry,
        )
    except release_contract.CompareReleaseError as error:
        raise ComparePhysicalError(f"release replay failed: {error}") from error
    if release_file.resolve() != (release_file.parent / release_contract.MANIFEST_FILE).resolve():
        raise ComparePhysicalError("release path must name release-manifest.json")
    if root["prerequisites"] != live_prerequisites:
        raise ComparePhysicalError("live prerequisite evidence differs from release")
    try:
        panel = json.loads(_read(panel_file, label="live panel", maximum=64 * 1024))
    except json.JSONDecodeError as error:
        raise ComparePhysicalError(f"live panel is invalid JSON: {error}") from error
    if panel != root["panel"]:
        raise ComparePhysicalError("live panel differs from release")
    variant = root["variant"]
    binary_path = release_file.parent / variant["firmware"]["file"]
    elf_path = release_file.parent / variant["elf"]["file"]
    return ReleaseContext(
        path=release_file.resolve(),
        root=root,
        variant=variant,
        release_canonical_sha256=root["integrity"]["canonical_sha256"],
        binary_path=binary_path.resolve(),
        binary_sha256=variant["firmware"]["sha256"],
        elf_path=elf_path.resolve(),
        elf_sha256=variant["elf"]["sha256"],
        panel=panel,
        prerequisites=live_prerequisites,
        prerequisite_files=prerequisite_files,
    )


def required_authorization() -> str:
    return (
        "AUTHORIZE_ONE_VISIBLE_EC5_U04_U05_COMPARE__ACTION_"
        f"{identity.FROZEN_ACTION_ID.upper()}{AUTHORIZATION_SUFFIX}"
    )


def _base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ComparePhysicalError("base URL must be a plain HTTP device origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ComparePhysicalError("base URL must not include a path/query/fragment")
    host = parsed.hostname
    if host not in ("localhost", "127.0.0.1"):
        try:
            parts = [int(part) for part in host.split(".")]
        except ValueError as error:
            raise ComparePhysicalError("device host must be a private IPv4 literal") from error
        private = (
            len(parts) == 4
            and all(0 <= part <= 255 for part in parts)
            and (
                parts[0] == 10
                or parts[:2] == [192, 168]
                or (parts[0] == 172 and 16 <= parts[1] <= 31)
            )
        )
        if not private:
            raise ComparePhysicalError("device host must be loopback/RFC1918 IPv4")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"http://{host}{port}"


def _request(
    base_url: str,
    endpoint: str,
    *,
    method: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float,
    _urlopen: Callable[..., Any],
) -> tuple[Mapping[str, Any], bytes]:
    request = urllib.request.Request(
        _base_url(base_url) + endpoint,
        data=None,
        headers=dict(headers or {}),
        method=method,
    )
    try:
        with _urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            payload = response.read(MAX_JSON_BYTES + 1)
    except Exception as error:
        raise ComparePhysicalReadError(f"{method} {endpoint} failed: {error}") from error
    if status < 200 or status >= 300:
        raise ComparePhysicalReadError(f"{method} {endpoint} returned HTTP {status}")
    return _decode(payload, label=f"{method} {endpoint}"), payload


def _nvs_contract() -> dict[str, Any]:
    return identity.nvs_contract()


def _nvs_virgin(value: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "nvs_contract": _nvs_contract(),
        "legacy_key_present": True,
        "legacy_phase": 2,
        "legacy_match": True,
        "active_key_present": False,
        "active_phase": 0,
        "active_virgin": True,
        "migration_ready": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise ComparePhysicalError(f"{label} {key} is not virgin/migration-ready")


def _identity_fields(value: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "layout_id": identity.LAYOUT_ID,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise ComparePhysicalError(f"{label} {key} differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    _keys(
        value,
        {
            "schema_version", "kind", "build_tag", "device_api_version",
            "identity_revision", "driver_api_version", "layout_id",
            "compiled_codes", "automatic_execute", "startup_refresh",
            "raw_frame_ingress", "dither", "lut_modification", "retry",
            "recovery", "boot_fixture_guard", "persistent_claim",
            "arm_required", "execute_limit_per_binary", "safety_scope",
        },
        label="version",
    )
    _identity_fields(value, label="version")
    expected = {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-version",
        "driver_api_version": DRIVER_API_VERSION,
        "compiled_codes": [4, 5],
        "automatic_execute": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "dither": False,
        "lut_modification": False,
        "retry": False,
        "recovery": False,
        "boot_fixture_guard": "exact_driver_action_validator",
        "persistent_claim": True,
        "arm_required": True,
        "execute_limit_per_binary": 1,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"version {key} differs")


def _manifest_rois() -> list[dict[str, Any]]:
    return [dict(roi) for roi in identity.ROIS]


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _keys(
        value,
        {
            "schema_version", "kind", "scope", "layout_id", "test_id",
            "action_id", "sequence_class", "repetition", "width", "height",
            "frame_bytes", "pixel_packing", "background_code", "rois",
            "histogram", "frame_sha256", "frame_fnv1a", "cs1_dtm_sha256",
            "cs1_dtm_fnv1a", "cs2_dtm_sha256", "cs2_dtm_fnv1a",
            "mapping_cs1", "mapping_cs2", "build_tag", "device_api_version",
            "identity_revision", "otp_mode", "dither", "mutation_contract",
            "exact_driver_fixture_guard_required", "nvs_contract",
            "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin",
            "migration_ready", "manifest_payload_sha256", "binary_sha256",
            "external_build_sidecar_required",
        },
        label="manifest",
    )
    _identity_fields(value, label="manifest")
    expected = {
        "schema_version": 3,
        "kind": "mf1750-ec5-compiled-fixture-manifest",
        "scope": "experimental_scaffold_not_hardware_authorization",
        "test_id": identity.TEST_ID,
        "action_id": identity.FROZEN_ACTION_ID,
        "sequence_class": "white_initial_fixed_nodither_diagonal_crossover",
        "repetition": 1,
        "width": 1024,
        "height": 600,
        "frame_bytes": 307_200,
        "pixel_packing": "row_major_4bpp_even_x_high_nibble",
        "background_code": 1,
        "rois": _manifest_rois(),
        "histogram": {"1": 598_016, "4": 8_192, "5": 8_192},
        "frame_sha256": identity.FRAME_SHA256,
        "frame_fnv1a": f"0x{identity.FRAME_FNV1A:08x}",
        "cs1_dtm_sha256": identity.CS1_DTM_SHA256,
        "cs1_dtm_fnv1a": f"0x{identity.CS1_DTM_FNV1A:08x}",
        "cs2_dtm_sha256": identity.CS2_DTM_SHA256,
        "cs2_dtm_fnv1a": f"0x{identity.CS2_DTM_FNV1A:08x}",
        "mapping_cs1": [0, 0, 0, 0],
        "mapping_cs2": [1, 0, 0, 0],
        "otp_mode": "existing_on_chip_otp_unchanged",
        "dither": False,
        "mutation_contract": {
            "bodyless": True,
            "exact_build_test_action_boot_nonce": True,
            "arm_nonce_required_for_execute": True,
            "not_hardware_authorization": True,
        },
        "exact_driver_fixture_guard_required": True,
        "manifest_payload_sha256": None,
        "binary_sha256": None,
        "external_build_sidecar_required": True,
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"manifest {key} differs")
    _nvs_virgin(value, label="manifest")


def _validate_status(
    value: Mapping[str, Any], *, boot_nonce: str | None, virgin: bool, busy: int | None
) -> str:
    _keys(
        value,
        {
            "schema_version", "kind", "boot_nonce", "build_tag",
            "device_api_version", "identity_revision", "layout_id", "test_id",
            "action_id", "state", "fixture_self_check_passed",
            "driver_fixture_guard_passed", "claim_store_ready",
            "persistent_phase", "arm_request_count", "execute_consumed",
            "execute_pending", "execute_request_count", "driver_call_count",
            "gpio_initialized", "busy", "rst", "cs", "cs2", "nvs_contract",
            "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin",
            "migration_ready",
        },
        label="status",
    )
    _identity_fields(value, label="status")
    nonce = _nonce(value["boot_nonce"], label="status boot_nonce")
    if boot_nonce is not None and nonce != boot_nonce:
        raise ComparePhysicalError("status boot nonce differs")
    if value["schema_version"] != 3 or value["kind"] != "mf1750-ec5-u04-u05-compare-status":
        raise ComparePhysicalError("status schema/kind differs")
    if value["test_id"] != identity.TEST_ID or value["action_id"] != identity.FROZEN_ACTION_ID:
        raise ComparePhysicalError("status test/action differs")
    if value["fixture_self_check_passed"] is not True or value["driver_fixture_guard_passed"] is not True or value["claim_store_ready"] is not True or value["gpio_initialized"] is not True:
        raise ComparePhysicalError("status readiness differs")
    if value["rst"] != 0 or value["cs"] != 0 or value["cs2"] != 0:
        raise ComparePhysicalError("status control pins are not safely low")
    if busy is not None and value["busy"] != busy:
        raise ComparePhysicalError("status BUSY differs from physical power gate")
    if virgin:
        expected = {
            "state": "ready", "persistent_phase": 0, "arm_request_count": 0,
            "execute_consumed": False, "execute_pending": False,
            "execute_request_count": 0, "driver_call_count": 0,
        }
        for key, wanted in expected.items():
            if value[key] != wanted:
                raise ComparePhysicalError(f"virgin status {key} differs")
        _nvs_virgin(value, label="status")
    else:
        if value["state"] not in {"queued", "running", "completed", "fault_locked"}:
            raise ComparePhysicalError("post-EXECUTE status state differs")
        consumed = {
            "persistent_phase": 2,
            "arm_request_count": 1,
            "execute_consumed": True,
            "execute_request_count": 1,
            "nvs_contract": _nvs_contract(),
            "legacy_key_present": True,
            "legacy_phase": 2,
            "legacy_match": True,
            "active_key_present": True,
            "active_phase": 2,
            "active_virgin": False,
            "migration_ready": True,
        }
        for key, wanted in consumed.items():
            if value[key] != wanted:
                raise ComparePhysicalError(f"post-EXECUTE status {key} differs")
        if value["state"] == "queued":
            if value["driver_call_count"] not in (0, 1):
                raise ComparePhysicalError("queued driver count differs")
        elif value["state"] == "running":
            if value["driver_call_count"] != 1 or value["execute_pending"] is not False:
                raise ComparePhysicalError("running status counters differ")
        elif value["driver_call_count"] != 1 or value["execute_pending"] is not False:
            raise ComparePhysicalError("terminal status counters differ")
    return nonce


def _validate_virgin_report(value: Mapping[str, Any], *, boot_nonce: str) -> None:
    _keys(
        value,
        {
            "schema_version", "kind", "valid", "test_id", "build_tag",
            "device_api_version", "identity_revision", "layout_id", "boot_nonce",
            "action_id", "terminal_state", "error",
            "driver_fixture_guard_passed", "execute_consumed", "driver_called",
            "persistent_phase", "no_retry", "no_recovery", "nvs_contract",
            "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin",
            "migration_ready",
        },
        label="virgin report",
    )
    _identity_fields(value, label="report")
    expected = {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-report",
        "valid": False,
        "test_id": identity.TEST_ID,
        "boot_nonce": boot_nonce,
        "action_id": identity.FROZEN_ACTION_ID,
        "terminal_state": "NOT_EXECUTED",
        "error": "no_execute_report",
        "driver_fixture_guard_passed": True,
        "execute_consumed": False,
        "driver_called": False,
        "persistent_phase": 0,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"virgin report {key} differs")
    _nvs_virgin(value, label="report")


def _read_snapshot(
    base_url: str,
    *,
    timeout_seconds: float,
    _urlopen: Callable[..., Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, bytes]]:
    values: dict[str, Mapping[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for name in ("version", "manifest", "status", "report"):
        values[name], payloads[name] = _request(
            base_url,
            ENDPOINTS[name],
            method="GET",
            timeout_seconds=timeout_seconds,
            _urlopen=_urlopen,
        )
    return values, payloads


def _validate_virgin_snapshot(
    values: Mapping[str, Mapping[str, Any]], *, busy: int
) -> str:
    if set(values) != {"version", "manifest", "status", "report"}:
        raise ComparePhysicalError("snapshot endpoints differ")
    _validate_version(values["version"])
    _validate_manifest(values["manifest"])
    nonce = _validate_status(
        values["status"], boot_nonce=None, virgin=True, busy=busy
    )
    _validate_virgin_report(values["report"], boot_nonce=nonce)
    return nonce


def _raw_records(payloads: Mapping[str, bytes]) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "path": ENDPOINTS[name],
            "raw_base64": base64.b64encode(payloads[name]).decode("ascii"),
            "payload_bytes": len(payloads[name]),
            "payload_sha256": _sha(payloads[name]),
        }
        for name in ("version", "manifest", "status", "report")
    ]


def _replay_raw(records: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list) or len(records) != 4:
        raise ComparePhysicalError("diagnostic must contain exactly four GET records")
    values = {}
    for record, name in zip(records, ("version", "manifest", "status", "report"), strict=True):
        item = _keys(
            record,
            {"name", "path", "raw_base64", "payload_bytes", "payload_sha256"},
            label=f"diagnostic {name}",
        )
        if item["name"] != name or item["path"] != ENDPOINTS[name]:
            raise ComparePhysicalError("diagnostic endpoint order differs")
        try:
            payload = base64.b64decode(item["raw_base64"], validate=True)
        except Exception as error:
            raise ComparePhysicalError("diagnostic raw base64 is invalid") from error
        if len(payload) != item["payload_bytes"] or _sha(payload) != item["payload_sha256"]:
            raise ComparePhysicalError("diagnostic raw payload identity differs")
        values[name] = _decode(payload, label=f"diagnostic {name}")
    return values


def _prerequisite_sha(context: ReleaseContext) -> str:
    return _sha(canonical_json_bytes(context.prerequisites))


def _claim_path(context: ReleaseContext, registry: Path | None) -> Path:
    root = DEFAULT_CLAIM_REGISTRY if registry is None else Path(registry)
    return root / f"{identity.FROZEN_ACTION_ID}.json"


def describe(context: ReleaseContext) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-u04-u05-compare-description",
        "action_id": identity.FROZEN_ACTION_ID,
        "layout_id": identity.LAYOUT_ID,
        "frame_sha256": identity.FRAME_SHA256,
        "cs1_dtm_sha256": identity.CS1_DTM_SHA256,
        "cs2_dtm_sha256": identity.CS2_DTM_SHA256,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware": {
            "file": str(context.binary_path),
            "sha256": context.binary_sha256,
        },
        "panel": dict(context.panel),
        "prerequisites_deep_validated": True,
        "u04_thirty_minute_hold_required": False,
        "u04_short_hold_skip_boundary_bound": True,
        "required_authorization": required_authorization(),
        "j2_off_diagnostic": {"get_requests": 4, "post_requests": 0, "claim": False},
        "run": {"fresh_get_requests": 4, "maximum_arm_posts": 1, "maximum_execute_posts": 1, "retry": False, "recovery": False},
        "network_requests": 0,
    }


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    confirm_j2_off: bool,
    evidence_file: Path,
    claim_registry: Path | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not confirm_j2_off:
        raise ComparePhysicalError("diagnostic requires explicit --confirm-j2-off")
    claim_path = _claim_path(context, claim_registry)
    if claim_path.exists():
        raise ComparePhysicalError("comparison action is already permanently claimed")
    values, payloads = _read_snapshot(
        base_url, timeout_seconds=timeout_seconds, _urlopen=_urlopen
    )
    boot_nonce = _validate_virgin_snapshot(values, busy=0)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "created_at": _now(),
        "action_id": identity.FROZEN_ACTION_ID,
        "release_file": str(context.path),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "elf_sha256": context.elf_sha256,
        "compiled_identity_report_sha256": _sha(
            canonical_json_bytes(context.root["compiled_identity_report"])
        ),
        "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "boot_nonce": boot_nonce,
        "j2_confirmed_off": True,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "raw_endpoints": _raw_records(payloads),
        "state": "diagnostic_pass_j2_off_no_mutation",
    }
    evidence = _seal(unsigned)
    _write_new(evidence_file, evidence)
    return evidence


def validate_diagnostic(
    context: ReleaseContext, evidence_file: Path
) -> dict[str, Any]:
    payload = _read(evidence_file, label="J2-off diagnostic")
    root = _decode(payload, label="J2-off diagnostic")
    _keys(
        root,
        {
            "schema_version", "kind", "created_at", "action_id", "release_file",
            "release_canonical_sha256", "firmware_sha256", "elf_sha256",
            "compiled_identity_report_sha256", "panel", "prerequisites_sha256",
            "boot_nonce", "j2_confirmed_off", "get_requests", "post_requests",
            "claim_created", "raw_endpoints", "state", "integrity",
        },
        label="J2-off diagnostic",
    )
    _validate_integrity(root, label="J2-off diagnostic")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": DIAGNOSTIC_KIND,
        "action_id": identity.FROZEN_ACTION_ID,
        "release_file": str(context.path),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "elf_sha256": context.elf_sha256,
        "compiled_identity_report_sha256": _sha(canonical_json_bytes(context.root["compiled_identity_report"])),
        "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "j2_confirmed_off": True,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "state": "diagnostic_pass_j2_off_no_mutation",
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise ComparePhysicalError(f"diagnostic {key} differs")
    values = _replay_raw(root["raw_endpoints"])
    nonce = _validate_virgin_snapshot(values, busy=0)
    if nonce != root["boot_nonce"]:
        raise ComparePhysicalError("diagnostic boot nonce differs from raw evidence")
    return dict(root)


def _headers(boot_nonce: str, *, intent: str, arm_nonce: str | None = None) -> dict[str, str]:
    result = {
        "X-EC5-Build-Tag": identity.BUILD_TAG,
        "X-EC5-Test-Id": identity.TEST_ID,
        "X-EC5-Action-Id": identity.FROZEN_ACTION_ID,
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        result["X-EC5-Arm-Nonce"] = arm_nonce
    return result


def _create_claim(
    context: ReleaseContext,
    diagnostic_file: Path,
    boot_nonce: str,
    attempt_id: str,
    authorization_sha256: str,
    registry: Path | None,
) -> tuple[Mapping[str, Any], bytes, Path]:
    path = _claim_path(context, registry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ComparePhysicalError(f"could not prepare claim registry: {error}") from error
    diagnostic_payload = _read(diagnostic_file, label="diagnostic for claim")
    claim = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "created_at": _now(),
        "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "diagnostic_file": str(Path(diagnostic_file).resolve()),
        "diagnostic_file_sha256": _sha(diagnostic_payload),
        "boot_nonce": boot_nonce,
        "authorization_confirmation_sha256": authorization_sha256,
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    payload = canonical_json_bytes(claim)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ComparePhysicalError("comparison action is already claimed") from error
    except OSError as error:
        raise ComparePhysicalError(f"could not create permanent claim: {error}") from error
    return claim, payload, path


def _validate_arm(value: Mapping[str, Any], *, boot_nonce: str) -> str:
    expected_keys = {
        "accepted", "armed", "test_id", "build_tag", "action_id",
        "device_api_version", "identity_revision", "boot_nonce", "arm_nonce",
        "persistent_phase", "migration_ready", "safety_scope",
        "not_hardware_authorization",
    }
    _keys(value, expected_keys, label="ARM response")
    expected = {
        "accepted": True, "armed": True, "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG, "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION, "boot_nonce": boot_nonce,
        "persistent_phase": 1, "migration_ready": True,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
        "not_hardware_authorization": True,
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"ARM response {key} differs")
    return _nonce(value["arm_nonce"], label="ARM nonce")


def _validate_execute(value: Mapping[str, Any], *, boot_nonce: str) -> None:
    _keys(
        value,
        {
            "accepted", "job_id", "test_id", "build_tag", "action_id",
            "device_api_version", "identity_revision", "boot_nonce",
            "execute_consumed", "persistent_phase", "migration_ready",
            "no_retry", "no_recovery",
        },
        label="EXECUTE response",
    )
    expected = {
        "accepted": True, "job_id": 1, "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG, "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION, "boot_nonce": boot_nonce,
        "execute_consumed": True, "persistent_phase": 2, "migration_ready": True,
        "no_retry": True, "no_recovery": True,
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"EXECUTE response {key} differs")


def _validate_driver(driver: Mapping[str, Any], *, require_pass: bool) -> None:
    _keys(
        driver,
        {
            "driver_evidence_schema_version", "operation_id", "valid", "running",
            "sequence_ok", "wait_timeout", "busy_assertion_missing",
            "mapping_applied", "pon_busy_seen", "drf_busy_seen", "pof_busy_seen",
            "post_psr_busy_seen", "pre_command_idle_failure", "failure_stage",
            "failure_code", "spi_hz", "free_psram_before",
            "largest_psram_block_before", "input_fnv1a", "cs1_dtm_fnv1a",
            "cs2_dtm_fnv1a", "total_ms", "cs1_upload_ms", "cs2_upload_ms",
            "pon_ms", "drf_ms", "pof_ms", "post_psr_ms", "last_wait_stage",
            "timeout_stage", "busy_missing_stage", "pre_command_busy_stage",
            "safe_finish",
        },
        label="driver evidence",
    )
    if driver["driver_evidence_schema_version"] != 2 or driver["operation_id"] != 1:
        raise ComparePhysicalError("driver schema/operation differs")
    if driver["input_fnv1a"] != identity.FRAME_FNV1A:
        raise ComparePhysicalError("driver input FNV differs")
    if driver["cs1_dtm_fnv1a"] != identity.CS1_DTM_FNV1A:
        raise ComparePhysicalError("driver CS1 DTM FNV differs")
    if driver["cs2_dtm_fnv1a"] != identity.CS2_DTM_FNV1A:
        raise ComparePhysicalError("driver CS2 DTM FNV differs")
    safe = _keys(
        driver["safe_finish"],
        {"busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms", "final_gpio"},
        label="safe finish",
    )
    gpio = _keys(safe["final_gpio"], {"busy", "rst", "cs", "cs2"}, label="final GPIO")
    if gpio["rst"] != 0 or gpio["cs"] != 0 or gpio["cs2"] != 0:
        raise ComparePhysicalError("driver final control pins are not low")
    if require_pass:
        expected = {
            "valid": True, "running": False, "sequence_ok": True,
            "wait_timeout": False, "busy_assertion_missing": False,
            "mapping_applied": True, "pon_busy_seen": True,
            "drf_busy_seen": True, "pof_busy_seen": True,
            "post_psr_busy_seen": False, "pre_command_idle_failure": False,
            "failure_stage": "none", "failure_code": 0, "spi_hz": 1_000_000,
            "timeout_stage": "none", "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
        }
        for key, wanted in expected.items():
            if driver[key] != wanted:
                raise ComparePhysicalError(f"successful driver {key} differs")
        if any(_integer(driver[key], label=f"driver {key}", minimum=1) <= 0 for key in ("free_psram_before", "largest_psram_block_before", "total_ms", "cs1_upload_ms", "cs2_upload_ms", "pon_ms", "drf_ms", "pof_ms")):
            raise ComparePhysicalError("successful driver timing/memory evidence differs")
        if safe != {
            "busy_before_pins_low": 1,
            "busy_after_pins_low": 1,
            "busy_after_5ms": 1,
            "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
        }:
            raise ComparePhysicalError("successful driver safe finish differs")


def _validate_terminal_report(value: Mapping[str, Any], *, boot_nonce: str) -> bool:
    _keys(
        value,
        {
            "schema_version", "kind", "valid", "test_id", "build_tag",
            "device_api_version", "identity_revision", "layout_id", "boot_nonce",
            "action_id", "job_id", "terminal_state", "result",
            "driver_fixture_guard_passed", "execute_consumed", "driver_called",
            "driver_call_count", "persistent_phase", "no_retry", "no_recovery",
            "job_queued_at_ms", "job_started_at_ms", "job_finished_at_ms", "driver",
            "nvs_contract", "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin", "migration_ready",
        },
        label="terminal report",
    )
    _identity_fields(value, label="terminal report")
    expected = {
        "schema_version": 3, "kind": "mf1750-ec5-u04-u05-compare-report",
        "valid": True, "test_id": identity.TEST_ID, "boot_nonce": boot_nonce,
        "action_id": identity.FROZEN_ACTION_ID, "job_id": 1,
        "driver_fixture_guard_passed": True, "execute_consumed": True,
        "driver_called": True, "driver_call_count": 1, "persistent_phase": 2,
        "no_retry": True, "no_recovery": True, "nvs_contract": _nvs_contract(),
        "legacy_key_present": True, "legacy_phase": 2, "legacy_match": True,
        "active_key_present": True, "active_phase": 2, "active_virgin": False,
        "migration_ready": True,
    }
    for key, wanted in expected.items():
        if value[key] != wanted:
            raise ComparePhysicalError(f"terminal report {key} differs")
    queued = _integer(value["job_queued_at_ms"], label="queued time", minimum=1)
    started = _integer(value["job_started_at_ms"], label="started time", minimum=queued)
    _integer(value["job_finished_at_ms"], label="finished time", minimum=started)
    passed = value["terminal_state"] == "completed" and value["result"] is True
    if not passed and not (value["terminal_state"] == "fault_locked" and value["result"] is False):
        raise ComparePhysicalError("terminal state/result pair differs")
    _validate_driver(value["driver"], require_pass=passed)
    return passed


def run_once(
    context: ReleaseContext,
    base_url: str,
    *,
    authorization: str,
    diagnostic_file: Path,
    result_file: Path,
    claim_registry: Path | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if authorization != required_authorization():
        raise ComparePhysicalError("authorization phrase differs")
    if poll_count <= 0 or poll_interval_seconds < 0:
        raise ComparePhysicalError("poll controls are invalid")
    diagnostic = validate_diagnostic(context, diagnostic_file)
    values, _payloads = _read_snapshot(
        base_url, timeout_seconds=timeout_seconds, _urlopen=_urlopen
    )
    boot_nonce = _validate_virgin_snapshot(values, busy=1)
    if boot_nonce != diagnostic["boot_nonce"]:
        raise ComparePhysicalError("J2-on preflight is not the diagnostic boot")
    attempt_id = str(uuid.uuid4())
    authorization_sha = _sha(authorization.encode("utf-8"))
    claim, claim_payload, claim_path = _create_claim(
        context,
        diagnostic_file,
        boot_nonce,
        attempt_id,
        authorization_sha,
        claim_registry,
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
                    base_url, ENDPOINTS["status"], method="GET",
                    timeout_seconds=timeout_seconds, _urlopen=_urlopen,
                )
                _validate_status(status, boot_nonce=boot_nonce, virgin=False, busy=None)
                observations.append({"poll": poll, "state": status["state"], "driver_call_count": status["driver_call_count"]})
                if status["state"] in ("completed", "fault_locked"):
                    report, _ = _request(
                        base_url, ENDPOINTS["report"], method="GET",
                        timeout_seconds=timeout_seconds, _urlopen=_urlopen,
                    )
                    passed = _validate_terminal_report(report, boot_nonce=boot_nonce)
                    final_status, final_report = status, report
                    outcome = "complete_pass" if passed else "complete_driver_failure_no_retry"
                    break
            except ComparePhysicalReadError as read_error:
                observations.append({"poll": poll, "read_error": str(read_error)})
            if poll < poll_count and poll_interval_seconds:
                time.sleep(poll_interval_seconds)
        if final_report is None:
            error_text = "terminal report not obtained; do not retry or recover"
    except ComparePhysicalError as error:
        error_text = str(error)
    finished_at = _now()
    claim_reference = {
        "filename": claim_path.name,
        "file_sha256": _sha(claim_payload),
        "attempt_id": attempt_id,
        "state": claim["state"],
    }
    diagnostic_payload = _read(diagnostic_file, label="diagnostic result binding")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "diagnostic": {
            "file": str(Path(diagnostic_file).resolve()),
            "file_sha256": _sha(diagnostic_payload),
            "integrity_sha256": diagnostic["integrity"]["canonical_sha256"],
            "boot_nonce": boot_nonce,
        },
        "boot_nonce": boot_nonce,
        "authorization_confirmation_sha256": authorization_sha,
        "claim": claim_reference,
        "started_at": started_at,
        "finished_at": finished_at,
        "outcome": outcome,
        "error": error_text,
        "post_requests": post_requests,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "observations": observations,
        "final_status": final_status,
        "final_report": final_report,
        "state": "authorization_permanently_consumed_do_not_rerun",
    }
    result = _seal(unsigned)
    _write_new(result_file, result)
    return result


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path | None = None,
) -> dict[str, Any]:
    payload = _read(result_file, label="comparison result")
    root = _decode(payload, label="comparison result")
    _keys(
        root,
        {
            "schema_version", "kind", "attempt_id", "action_id",
            "release_canonical_sha256", "firmware_sha256", "panel",
            "prerequisites_sha256", "diagnostic", "boot_nonce",
            "authorization_confirmation_sha256", "claim", "started_at",
            "finished_at", "outcome", "error", "post_requests",
            "maximum_arm_posts", "maximum_execute_posts", "automatic_retry",
            "automatic_recovery", "observations", "final_status", "final_report",
            "state", "integrity",
        },
        label="comparison result",
    )
    _validate_integrity(root, label="comparison result")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "authorization_confirmation_sha256": _sha(required_authorization().encode("utf-8")),
        "maximum_arm_posts": 1, "maximum_execute_posts": 1,
        "automatic_retry": False, "automatic_recovery": False,
        "state": "authorization_permanently_consumed_do_not_rerun",
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise ComparePhysicalError(f"result {key} differs")
    diagnostic = _keys(root["diagnostic"], {"file", "file_sha256", "integrity_sha256", "boot_nonce"}, label="result diagnostic")
    diagnostic_path = Path(diagnostic["file"])
    diagnostic_payload = _read(diagnostic_path, label="result diagnostic file")
    validated_diagnostic = validate_diagnostic(context, diagnostic_path)
    if diagnostic["file_sha256"] != _sha(diagnostic_payload) or diagnostic["integrity_sha256"] != validated_diagnostic["integrity"]["canonical_sha256"] or diagnostic["boot_nonce"] != root["boot_nonce"]:
        raise ComparePhysicalError("result diagnostic binding differs")
    claim_ref = _keys(root["claim"], {"filename", "file_sha256", "attempt_id", "state"}, label="result claim")
    claim_path = _claim_path(context, claim_registry)
    claim_payload = _read(claim_path, label="permanent comparison claim")
    claim = _decode(claim_payload, label="permanent comparison claim")
    if claim_ref != {"filename": claim_path.name, "file_sha256": _sha(claim_payload), "attempt_id": root["attempt_id"], "state": "permanently_claimed_before_first_post_no_retry_no_recovery"}:
        raise ComparePhysicalError("result claim reference differs")
    claim_expected = {
        "schema_version": 1, "kind": CLAIM_KIND, "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": root["attempt_id"], "action_id": identity.FROZEN_ACTION_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256, "panel": dict(context.panel),
        "prerequisites_sha256": _prerequisite_sha(context),
        "diagnostic_file": str(diagnostic_path.resolve()),
        "diagnostic_file_sha256": _sha(diagnostic_payload),
        "boot_nonce": root["boot_nonce"],
        "authorization_confirmation_sha256": root["authorization_confirmation_sha256"],
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
        "maximum_arm_posts": 1, "maximum_execute_posts": 1,
        "automatic_retry": False, "automatic_recovery": False,
    }
    if set(claim) != set(claim_expected) | {"created_at"}:
        raise ComparePhysicalError("permanent claim fields differ")
    for key, wanted in claim_expected.items():
        if claim[key] != wanted:
            raise ComparePhysicalError(f"permanent claim {key} differs")
    if root["outcome"] == "complete_pass":
        if root["post_requests"] != 2 or root["error"] is not None:
            raise ComparePhysicalError("complete result POST/error differs")
        if not isinstance(root["final_status"], Mapping) or not isinstance(root["final_report"], Mapping):
            raise ComparePhysicalError("complete result lacks terminal evidence")
        _validate_status(root["final_status"], boot_nonce=root["boot_nonce"], virgin=False, busy=None)
        if not _validate_terminal_report(root["final_report"], boot_nonce=root["boot_nonce"]):
            raise ComparePhysicalError("complete result has failing driver report")
    elif root["outcome"] not in {"complete_driver_failure_no_retry", "unknown_do_not_retry_or_recover"}:
        raise ComparePhysicalError("result outcome differs")
    if root["post_requests"] not in (0, 1, 2):
        raise ComparePhysicalError("result POST count is invalid")
    return dict(root)


def _prerequisite_args(item: argparse.ArgumentParser) -> None:
    item.add_argument("--corrected-u04-release", type=Path, required=True)
    item.add_argument("--u04-result", type=Path, required=True)
    item.add_argument("--u04-short-hold", type=Path, required=True)
    item.add_argument("--white-result", type=Path, required=True)
    item.add_argument("--white-observation", type=Path, required=True)
    item.add_argument("--rc2g-binary", type=Path, required=True)
    item.add_argument("--candidate-claim-registry", type=Path, required=True)
    item.add_argument("--white-claim-registry", type=Path, required=True)


def _prerequisites(args: argparse.Namespace) -> PrerequisiteFiles:
    return PrerequisiteFiles(
        corrected_u04_release=args.corrected_u04_release,
        u04_result=args.u04_result,
        u04_short_hold=args.u04_short_hold,
        white_result=args.white_result,
        white_observation=args.white_observation,
        rc2g_binary=args.rc2g_binary,
        candidate_claim_registry=args.candidate_claim_registry,
        white_claim_registry=args.white_claim_registry,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("describe", "diagnose-j2-off", "run", "validate"):
        item = sub.add_parser(name, allow_abbrev=False)
        item.add_argument("--release", type=Path, required=True)
        item.add_argument("--panel", type=Path, required=True)
        _prerequisite_args(item)
        if name in ("diagnose-j2-off", "run"):
            item.add_argument("--base-url", required=True)
            item.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
        if name == "diagnose-j2-off":
            item.add_argument("--confirm-j2-off", action="store_true")
            item.add_argument("--evidence", type=Path, required=True)
            item.add_argument("--claim-registry", type=Path)
        elif name == "run":
            item.add_argument("--authorization", required=True)
            item.add_argument("--diagnostic", type=Path, required=True)
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--claim-registry", type=Path)
            item.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
            item.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
        elif name == "validate":
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--claim-registry", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        context = load_release(args.release, args.panel, _prerequisites(args))
        if args.command == "describe":
            report = describe(context)
        elif args.command == "diagnose-j2-off":
            report = diagnose_j2_off(
                context, args.base_url, confirm_j2_off=args.confirm_j2_off,
                evidence_file=args.evidence, claim_registry=args.claim_registry,
                timeout_seconds=args.timeout,
            )
        elif args.command == "run":
            report = run_once(
                context, args.base_url, authorization=args.authorization,
                diagnostic_file=args.diagnostic, result_file=args.result,
                claim_registry=args.claim_registry, timeout_seconds=args.timeout,
                poll_count=args.poll_count, poll_interval_seconds=args.poll_interval,
            )
        else:
            report = validate_result(context, args.result, claim_registry=args.claim_registry)
    except ComparePhysicalError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
