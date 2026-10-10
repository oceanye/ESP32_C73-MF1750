#!/usr/bin/env python3
"""Fail-closed one-visible EC5 U04/U07 physical executor.

The runner consumes a frozen ``mf1750-ec5-nodither-release-bundle``.  It
validates the selected binary, source snapshot, panel binding and all release
integrity before making any request.  ``preflight`` is GET-only.  ``run``
creates a workspace-global, permanent host claim before its first mutation,
sends ARM and EXECUTE at most once each, and never retries or recovers.

This module does not upload firmware and is never invoked by a build.  Merely
importing it, describing a release, validating evidence, or running preflight
cannot create a claim or issue a POST request.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
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

from tools import mf1750_ec5_release as release_contract  # noqa: E402
from tools import mf1750_ec5_compiled_identity as compiled_identity  # noqa: E402
from tools import mf1750_ec5_stage_a_v2_identity as stage_a_identity  # noqa: E402


SCHEMA_VERSION = 1
RELEASE_SCHEMA_VERSION = release_contract.SCHEMA_VERSION
RESULT_SCHEMA_VERSION = 3
DIAGNOSTIC_SCHEMA_VERSION = 1
RELEASE_KIND = "mf1750-ec5-nodither-release-bundle"
RESULT_KIND = "mf1750-ec5-physical-once-result"
DIAGNOSTIC_KIND = "mf1750-ec5-j2-off-diagnostic-preflight"
U04_REVIEW_KIND = "mf1750-ec5-u04-finalized-review"
HOLD_KIND = "mf1750-ec5-immutable-hold-observation"
U04_HOLD_KIND = HOLD_KIND  # backwards-compatible public constant
CLAIM_KIND = "mf1750-ec5-physical-permanent-claim"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-physical-claim-registry-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_claim_registry"
)
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_BINARY_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_COUNT = 40
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
QUARANTINE_MARKER = "QUARANTINED_DO_NOT_USE.md"

ARM_INTENT = "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = (
    "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
)
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"

_HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{16}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_CANDIDATES = {"U04": 4, "U07": 7}
EXPECTED_DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3"
EXPECTED_DEVICE_API_VERSION = stage_a_identity.DEVICE_API_VERSION
EXPECTED_DEVICE_SCHEMA_VERSION = stage_a_identity.TOP_SCHEMA_VERSION
EXPECTED_IDENTITY_REVISION = stage_a_identity.IDENTITY_REVISION
EXPECTED_DRIVER_EVIDENCE_SCHEMA_VERSION = (
    stage_a_identity.DRIVER_EVIDENCE_SCHEMA_VERSION
)
_EARLY_PRE_PANEL_FAILURE_STAGES = {
    "allocation",
    "frame_build",
    "full_sha",
    "cs1_compute",
    "cs2_compute",
    "cs1_identity",
    "cs2_identity",
}
_PANEL_FAILURE_STAGES = {"cascade_prepare", "stream_identity", "refresh_sequence"}
_KNOWN_DRIVER_FAILURE_STAGES = (
    {"none"} | _EARLY_PRE_PANEL_FAILURE_STAGES | _PANEL_FAILURE_STAGES
)
_FINAL_REPORT_KEYS = {
    "schema_version", "kind", "valid", "test_id", "build_tag",
    "device_api_version", "identity_revision", "boot_nonce", "action_id",
    "candidate_code",
    "job_id", "terminal_state", "result", "driver_fixture_guard_passed",
    "execute_consumed", "driver_called", "driver_call_count",
    "persistent_phase", "no_retry", "no_recovery", "job_queued_at_ms",
    "job_started_at_ms", "job_finished_at_ms", "driver", "nvs_contract",
    "legacy_key_present", "legacy_phase", "legacy_match",
    "active_key_present", "active_phase", "active_virgin", "migration_ready",
}
_FINAL_DRIVER_KEYS = {
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
}
_EXPECTED_SOURCE_PATHS = release_contract.SOURCE_PATHS
_EXPECTED_VARIANTS = stage_a_identity.VARIANTS
_ENDPOINTS = {
    "version": "/api/ec5/version",
    "manifest": "/api/ec5/manifest",
    "status": "/api/ec5/status",
    "report": "/api/ec5/report",
    "arm": "/api/ec5/arm",
    "execute": "/api/ec5/execute",
}


class Ec5PhysicalError(RuntimeError):
    """Rejected before the permanent mutation boundary."""


class Ec5PhysicalUnknown(Ec5PhysicalError):
    """The host claim exists, so another attempt is permanently forbidden."""


class Ec5PhysicalReadError(Ec5PhysicalError):
    """A device response could not be transported or read."""


@dataclass(frozen=True)
class ReleaseContext:
    path: Path
    root: Mapping[str, Any]
    variant_id: str
    variant: Mapping[str, Any]
    binary_path: Path
    binary_sha256: str
    elf_path: Path
    elf_sha256: str
    release_canonical_sha256: str
    panel: Mapping[str, str]
    panel_verified: bool
    source_root: Path
    panel_file: Path | None


@dataclass(frozen=True)
class Claim:
    path: Path
    record: Mapping[str, Any]
    payload: bytes

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.path.name,
            "file_sha256": _sha256(self.payload),
            "attempt_id": self.record["attempt_id"],
            "action_id": self.record["action_id"],
            "state": self.record["state"],
        }


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Ec5PhysicalError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise Ec5PhysicalError(f"{label} exceeds the JSON size limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                Ec5PhysicalError(f"{label} contains forbidden number {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Ec5PhysicalError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise Ec5PhysicalError(f"{label} must be a JSON object")
    return value


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as error:
        raise Ec5PhysicalError(f"cannot stat {label}: {error}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Ec5PhysicalError(f"{label} must be a non-symlink regular file")
    if info.st_size > maximum:
        raise Ec5PhysicalError(f"{label} exceeds the size limit")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise Ec5PhysicalError(f"cannot read {label}: {error}") from error
    if len(payload) != info.st_size:
        raise Ec5PhysicalError(f"{label} changed while being read")
    return payload


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise Ec5PhysicalError(
            f"{label} keys differ: expected {sorted(expected)!r}, got {actual!r}"
        )
    return value


def _strict_json_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON values without Python's bool/int equality aliasing."""

    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(_strict_json_equal(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _strict_json_equal(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _string(value: Any, *, label: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise Ec5PhysicalError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Ec5PhysicalError(f"{label} must be an integer >= {minimum}")
    return value


def _signed_integer(
    value: Any,
    *,
    label: str,
    minimum: int = -(2**31),
    maximum: int = 2**31 - 1,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise Ec5PhysicalError(
            f"{label} must be an integer between {minimum} and {maximum}"
        )
    return value


def _number(value: Any, *, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Ec5PhysicalError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or not minimum <= normalized <= maximum:
        raise Ec5PhysicalError(f"{label} must be between {minimum} and {maximum}")
    return normalized


def _boolean(value: Any, expected: bool, *, label: str) -> None:
    if value is not expected:
        raise Ec5PhysicalError(f"{label} must be {str(expected).lower()}")


def _hex64(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise Ec5PhysicalError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise Ec5PhysicalError(f"{label} must be RFC3339 with an explicit timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Ec5PhysicalError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Ec5PhysicalError(f"{label} lacks a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: Any, *, label: str) -> str:
    _parse_timestamp(value, label=label)
    return value


def _safe_relative(value: Any, *, label: str) -> Path:
    text = _string(value, label=label)
    candidate = Path(text)
    if candidate.is_absolute() or not candidate.parts or any(
        part in ("", ".", "..") for part in candidate.parts
    ):
        raise Ec5PhysicalError(f"{label} must be a normalized relative path")
    return candidate


def _inside(root: Path, relative: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise Ec5PhysicalError(f"{label} escapes its root") from error
    return resolved


def _fnv_value(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise Ec5PhysicalError(f"{label} must be an unsigned 32-bit integer")
    return value


def _validate_panel(value: Any, *, label: str) -> dict[str, str]:
    panel = _keys(
        value,
        {"model", "serial", "board_id", "pcb_revision"},
        label=label,
    )
    result: dict[str, str] = {}
    for key in panel:
        field = _string(panel[key], label=f"{label}.{key}")
        if field != field.strip() or len(field) > 256 or any(ord(character) < 0x20 for character in field):
            raise Ec5PhysicalError(f"{label}.{key} is malformed")
        result[key] = field
    return result


def _integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _keys(root.get("integrity"), {"canonical_sha256", "scope"}, label=f"{label}.integrity")
    expected = _hex64(integrity["canonical_sha256"], label=f"{label}.integrity.canonical_sha256")
    unsigned = deepcopy(root)
    unsigned.pop("integrity")
    # Release bundles use compact UTF-8 canonical JSON without the trailing
    # newline used by the physical evidence records in this module.
    release_bytes = json.dumps(
        unsigned,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual = _sha256(release_bytes)
    if actual != expected:
        raise Ec5PhysicalError(f"{label} canonical integrity mismatch")
    expected_scope = (
        "entire release manifest excluding integrity; UTF-8 JSON with sorted keys, "
        "no whitespace, ensure_ascii=false, allow_nan=false"
    )
    if integrity["scope"] != expected_scope:
        raise Ec5PhysicalError(f"{label} integrity scope mismatch")
    return actual


def _validate_source_snapshot(value: Any, source_root: Path) -> None:
    snapshot = _keys(
        value,
        {
            "git_head",
            "git_dirty",
            "git_status_sha256",
            "git_status_line_count",
            "relevant_sources",
        },
        label="source_snapshot",
    )
    if not isinstance(snapshot["git_head"], str) or re.fullmatch(r"[0-9a-f]{40}", snapshot["git_head"]) is None:
        raise Ec5PhysicalError("source_snapshot.git_head is malformed")
    if not isinstance(snapshot["git_dirty"], bool):
        raise Ec5PhysicalError("source_snapshot.git_dirty must be boolean")
    _hex64(snapshot["git_status_sha256"], label="source_snapshot.git_status_sha256")
    _integer(snapshot["git_status_line_count"], label="source_snapshot.git_status_line_count")
    entries = snapshot["relevant_sources"]
    if not isinstance(entries, list) or not entries:
        raise Ec5PhysicalError("source_snapshot.relevant_sources must be a non-empty list")
    if [entry.get("path") if isinstance(entry, Mapping) else None for entry in entries] != list(_EXPECTED_SOURCE_PATHS):
        raise Ec5PhysicalError("source_snapshot relevant source list differs from the frozen contract")
    normalized: list[dict[str, Any]] = []
    prior = ""
    for index, raw in enumerate(entries):
        entry = _keys(raw, {"path", "bytes", "sha256"}, label=f"source file {index}")
        relative = _safe_relative(entry["path"], label=f"source file {index}.path")
        path_text = relative.as_posix()
        if path_text <= prior:
            raise Ec5PhysicalError("source_snapshot.relevant_sources must be unique and path-sorted")
        prior = path_text
        size = _integer(entry["bytes"], label=f"source file {path_text}.bytes", minimum=1)
        digest = _hex64(entry["sha256"], label=f"source file {path_text}.sha256")
        payload = _read_regular(
            _inside(source_root, relative, label=f"source file {path_text}"),
            label=f"source file {path_text}",
            maximum=MAX_BINARY_BYTES,
        )
        if len(payload) != size or _sha256(payload) != digest:
            raise Ec5PhysicalError(f"source file {path_text} no longer matches the release")
        normalized.append({"path": path_text, "bytes": size, "sha256": digest})
    # The complete source_snapshot is covered by the release root integrity.


def load_release(
    release_file: Path,
    candidate: str,
    *,
    source_root: Path = REPO_ROOT,
    panel_file: Path | None = None,
) -> ReleaseContext:
    candidate = candidate.upper()
    if candidate not in _CANDIDATES:
        raise Ec5PhysicalError("candidate must be U04 or U07")
    release_file = Path(release_file)
    quarantine_marker = release_file.parent / QUARANTINE_MARKER
    try:
        quarantine_marker.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise Ec5PhysicalError(f"cannot inspect EC5 release quarantine marker: {error}") from error
    else:
        raise Ec5PhysicalError(
            f"EC5 release bundle is quarantined by {QUARANTINE_MARKER}; do not use"
        )
    payload = _read_regular(release_file, label="EC5 release manifest", maximum=MAX_JSON_BYTES)
    root = _decode_json(payload, label="EC5 release manifest")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "identity_revision",
            "created_at",
            "panel",
            "source_snapshot",
            "device_contract",
            "incident_lineage",
            "compiled_identity_report",
            "variants",
            "safety",
            "integrity",
        },
        label="EC5 release manifest",
    )
    if (
        root["schema_version"] != RELEASE_SCHEMA_VERSION
        or root["kind"] != RELEASE_KIND
        or root["identity_revision"] != EXPECTED_IDENTITY_REVISION
    ):
        raise Ec5PhysicalError("unsupported EC5 release schema or kind")
    if not _strict_json_equal(
        root["incident_lineage"], release_contract.INCIDENT_LINEAGE
    ):
        raise Ec5PhysicalError("release V1 incident lineage mismatch")
    _timestamp(root["created_at"], label="release created_at")
    panel = _validate_panel(root["panel"], label="release panel")
    if panel_file is not None:
        panel_payload = _read_regular(Path(panel_file), label="live panel identity", maximum=64 * 1024)
        live_panel = _validate_panel(_decode_json(panel_payload, label="live panel identity"), label="live panel identity")
        if live_panel != panel:
            raise Ec5PhysicalError("live panel identity does not match the frozen release panel")

    _validate_source_snapshot(root["source_snapshot"], Path(source_root))
    contract = _keys(
        root["device_contract"],
        set(release_contract.DEVICE_CONTRACT),
        label="device_contract",
    )
    if not _strict_json_equal(contract, release_contract.DEVICE_CONTRACT):
        raise Ec5PhysicalError("device_contract differs from corrected V2 release")
    if contract["read_routes"] != [_ENDPOINTS[key] for key in ("version", "manifest", "status", "report")] or contract["arm_route"] != _ENDPOINTS["arm"] or contract["execute_route"] != _ENDPOINTS["execute"]:
        raise Ec5PhysicalError("device_contract endpoints differ from the fixed EC5 API")
    if contract["arm_intent"] != ARM_INTENT or contract["execute_intent"] != EXECUTE_INTENT:
        raise Ec5PhysicalError("device_contract mutation intents differ from the fixed runner")

    for key in ("persistent_claim", "arm_required"):
        _boolean(contract[key], True, label=f"device_contract.{key}")
    for key in ("retry_allowed", "recovery_included", "raw_frame_ingress", "startup_refresh"):
        _boolean(contract[key], False, label=f"device_contract.{key}")
    if contract["maximum_arm_posts"] != 1 or contract["maximum_execute_posts"] != 1:
        raise Ec5PhysicalError("device_contract does not freeze one ARM and one EXECUTE POST")

    safety = _keys(
        root["safety"],
        {
            "classification", "hardware_authorized", "upload_performed",
            "device_io_performed", "visible_refresh_performed",
            "u07_requires_independent_post_u04_go", "custom_waveform_or_lut_used",
            "factory_otp_unchanged",
        },
        label="safety",
    )
    if safety["classification"] != "EXPERIMENTAL_NOT_QUALIFIED":
        raise Ec5PhysicalError("release safety classification mismatch")
    for key in ("hardware_authorized", "upload_performed", "device_io_performed", "visible_refresh_performed", "custom_waveform_or_lut_used"):
        _boolean(safety[key], False, label=f"safety.{key}")
    for key in ("u07_requires_independent_post_u04_go", "factory_otp_unchanged"):
        _boolean(safety[key], True, label=f"safety.{key}")

    variants = root["variants"]
    if not isinstance(variants, Mapping) or set(variants) != set(_CANDIDATES):
        raise Ec5PhysicalError("release variants must contain exactly U04 and U07")
    raw_variant = variants[candidate]
    variant = _keys(
        raw_variant,
        {
            "candidate_id",
            "candidate_code",
            "environment",
            "build_tag",
            "test_id",
            "action_id",
            "identity_revision",
            "device_api_version",
            "top_schema_version",
            "driver_evidence_schema_version",
            "layout_id",
            "frame_sha256",
            "frame_fnv1a",
            "dtm_sha256",
            "dtm_fnv1a",
            "action_identity_preimage",
            "action_identity_sha256_scope",
            "nvs_contract",
            "firmware",
            "elf",
            "build_command",
        },
        label=f"variant {candidate}",
    )
    if variant["candidate_id"] != candidate or variant["candidate_code"] != _CANDIDATES[candidate]:
        raise Ec5PhysicalError(f"variant {candidate} candidate identity mismatch")
    expected_environment = f"esp32-s3-devkitc-1-ec5-{candidate.lower()}"
    if variant["environment"] != expected_environment:
        raise Ec5PhysicalError(f"variant {candidate} environment mismatch")
    for key in (
        "build_tag",
        "test_id",
        "identity_revision",
        "device_api_version",
        "layout_id",
        "action_identity_sha256_scope",
    ):
        _string(variant[key], label=f"variant {candidate}.{key}")
    _hex64(variant["action_id"], label=f"variant {candidate}.action_id")
    _hex64(variant["frame_sha256"], label=f"variant {candidate}.frame_sha256")
    _fnv_value(variant["frame_fnv1a"], label=f"variant {candidate}.frame_fnv1a")
    _hex64(variant["dtm_sha256"], label=f"variant {candidate}.dtm_sha256")
    _fnv_value(variant["dtm_fnv1a"], label=f"variant {candidate}.dtm_fnv1a")
    if variant["build_command"] != ["pio", "run", "-e", expected_environment]:
        raise Ec5PhysicalError(f"variant {candidate} build command mismatch")
    expected_variant = _EXPECTED_VARIANTS[candidate]
    for key in (
        "candidate_id",
        "candidate_code",
        "environment",
        "build_tag",
        "test_id",
        "action_id",
        "identity_revision",
        "device_api_version",
        "top_schema_version",
        "driver_evidence_schema_version",
        "layout_id",
        "frame_sha256",
        "frame_fnv1a",
        "dtm_sha256",
        "dtm_fnv1a",
        "action_identity_preimage",
        "action_identity_sha256_scope",
        "nvs_contract",
    ):
        expected = expected_variant[key]
        if not _strict_json_equal(variant[key], expected):
            raise Ec5PhysicalError(f"variant {candidate}.{key} differs from the frozen candidate")
    if stage_a_identity.derive_action_id(variant["action_identity_preimage"]) != variant["action_id"]:
        raise Ec5PhysicalError(f"variant {candidate} action identity preimage hash mismatch")
    if variant["device_api_version"] != EXPECTED_DEVICE_API_VERSION:
        raise Ec5PhysicalError(f"variant {candidate} device API mismatch")
    if variant["top_schema_version"] != EXPECTED_DEVICE_SCHEMA_VERSION:
        raise Ec5PhysicalError(f"variant {candidate} top schema mismatch")
    if variant["driver_evidence_schema_version"] != EXPECTED_DRIVER_EVIDENCE_SCHEMA_VERSION:
        raise Ec5PhysicalError(f"variant {candidate} driver evidence schema mismatch")
    firmware = _keys(variant["firmware"], {"file", "bytes", "sha256"}, label=f"variant {candidate}.firmware")
    relative_binary = _safe_relative(firmware["file"], label=f"variant {candidate}.firmware.file")
    if relative_binary.as_posix() != expected_variant["firmware_file"]:
        raise Ec5PhysicalError(f"variant {candidate} firmware filename mismatch")
    binary_path = _inside(release_file.parent, relative_binary, label="firmware binary")
    binary = _read_regular(binary_path, label=f"{candidate} firmware binary", maximum=MAX_BINARY_BYTES)
    binary_size = _integer(firmware["bytes"], label=f"variant {candidate}.firmware.bytes", minimum=1)
    binary_sha256 = _hex64(firmware["sha256"], label=f"variant {candidate}.firmware.sha256")
    if len(binary) != binary_size or _sha256(binary) != binary_sha256:
        raise Ec5PhysicalError(f"{candidate} firmware bytes do not match the release")
    for key in (
        "build_tag",
        "test_id",
        "action_id",
        "frame_sha256",
        "dtm_sha256",
        "identity_revision",
        "device_api_version",
    ):
        if str(variant[key]).encode("ascii") not in binary:
            raise Ec5PhysicalError(f"{candidate} firmware omits frozen token {key}")
    for side in ("legacy", "active"):
        for key in ("namespace", "key"):
            token = str(variant["nvs_contract"][side][key]).encode("ascii")
            if token not in binary:
                raise Ec5PhysicalError(
                    f"{candidate} firmware omits frozen NVS token {side}.{key}"
                )
    other = "U07" if candidate == "U04" else "U04"
    for key in ("build_tag", "test_id", "action_id"):
        if str(_EXPECTED_VARIANTS[other][key]).encode("ascii") in binary:
            raise Ec5PhysicalError(f"{candidate} firmware contains the other candidate identity")
    for token in stage_a_identity.V1_BINARY_IDENTITY_TOKENS:
        if token.encode("ascii") in binary:
            raise Ec5PhysicalError(f"{candidate} firmware contains a quarantined V1 identity")

    elf = _keys(
        variant["elf"],
        {"file", "bytes", "sha256"},
        label=f"variant {candidate}.elf",
    )
    relative_elf = _safe_relative(elf["file"], label=f"variant {candidate}.elf.file")
    if relative_elf.as_posix() != expected_variant["elf_file"]:
        raise Ec5PhysicalError(f"variant {candidate} ELF filename mismatch")
    elf_path = _inside(release_file.parent, relative_elf, label="firmware ELF")
    elf_payload = _read_regular(
        elf_path,
        label=f"{candidate} firmware ELF",
        maximum=compiled_identity.MAX_ELF_BYTES,
    )
    elf_size = _integer(elf["bytes"], label=f"variant {candidate}.elf.bytes", minimum=1)
    elf_sha256 = _hex64(elf["sha256"], label=f"variant {candidate}.elf.sha256")
    if len(elf_payload) != elf_size or _sha256(elf_payload) != elf_sha256:
        raise Ec5PhysicalError(f"{candidate} ELF bytes do not match the release")

    elf_paths: dict[str, Path] = {}
    for identity_candidate in ("U04", "U07"):
        candidate_variant = variants[identity_candidate]
        if not isinstance(candidate_variant, Mapping):
            raise Ec5PhysicalError("release variant is malformed")
        candidate_elf = _keys(
            candidate_variant.get("elf"),
            {"file", "bytes", "sha256"},
            label=f"variant {identity_candidate}.elf",
        )
        relative = _safe_relative(
            candidate_elf["file"],
            label=f"variant {identity_candidate}.elf.file",
        )
        if relative.as_posix() != _EXPECTED_VARIANTS[identity_candidate]["elf_file"]:
            raise Ec5PhysicalError(f"variant {identity_candidate} ELF filename mismatch")
        path = _inside(release_file.parent, relative, label=f"{identity_candidate} ELF")
        payload = _read_regular(
            path,
            label=f"{identity_candidate} ELF",
            maximum=compiled_identity.MAX_ELF_BYTES,
        )
        if (
            len(payload)
            != _integer(
                candidate_elf["bytes"],
                label=f"variant {identity_candidate}.elf.bytes",
                minimum=1,
            )
            or _sha256(payload)
            != _hex64(
                candidate_elf["sha256"],
                label=f"variant {identity_candidate}.elf.sha256",
            )
        ):
            raise Ec5PhysicalError(
                f"variant {identity_candidate} ELF bytes do not match the release"
            )
        elf_paths[identity_candidate] = path
    try:
        compiled_report = compiled_identity.validate_pair(
            elf_paths["U04"], elf_paths["U07"]
        )
    except compiled_identity.CompiledIdentityError as error:
        raise Ec5PhysicalError(f"compiled ELF identity validation failed: {error}") from error
    if not _strict_json_equal(root["compiled_identity_report"], compiled_report):
        raise Ec5PhysicalError("release compiled identity report mismatch")
    release_sha = _integrity(root, label="EC5 release manifest")
    return ReleaseContext(
        path=release_file.resolve(),
        root=root,
        variant_id=candidate,
        variant=variant,
        binary_path=binary_path,
        binary_sha256=binary_sha256,
        elf_path=elf_path,
        elf_sha256=elf_sha256,
        release_canonical_sha256=release_sha,
        panel=panel,
        panel_verified=panel_file is not None,
        source_root=Path(source_root).resolve(),
        panel_file=Path(panel_file).resolve() if panel_file is not None else None,
    )


def required_authorization(context: ReleaseContext) -> str:
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_{context.variant_id}__ACTION_"
        f"{context.variant['action_id'].upper()}{AUTHORIZATION_SUFFIX}"
    )


# Hardened immutable evidence-chain API used by the physical executor.
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _candidate_result_reference(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path | None,
    result_validation_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not context.panel_verified:
        raise Ec5PhysicalError("hold evidence requires a verified release/panel")
    kwargs = dict(result_validation_kwargs or {})
    if "claim_registry" in kwargs:
        raise Ec5PhysicalError("result validation kwargs cannot override claim_registry")
    result = validate_result(
        context,
        Path(result_file),
        claim_registry=claim_registry,
        **kwargs,
    )
    if result["outcome"] != "complete_pass":
        raise Ec5PhysicalError("hold evidence requires a complete_pass candidate result")
    payload = _read_regular(
        Path(result_file), label="candidate physical result", maximum=MAX_JSON_BYTES
    )
    return {
        "file": str(Path(result_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "integrity_sha256": result["integrity"]["canonical_sha256"],
        "attempt_id": result["attempt_id"],
        "action_id": result["action_id"],
        "outcome": "complete_pass",
        "completed_at": result["finished_at"],
    }


def _u04_result_reference(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path | None,
) -> dict[str, Any]:
    if context.variant_id != "U04":
        raise Ec5PhysicalError("U04 result reference requires the U04 context")
    return _candidate_result_reference(
        context,
        result_file,
        claim_registry=claim_registry,
    )


def _hold_file_reference(path: Path, root: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "integrity_sha256": root["integrity"]["canonical_sha256"],
        "hold_minutes": root["hold_minutes"],
        "recorded_at": root["recorded_at"],
    }


def _validate_hold_observation_at(
    context: ReleaseContext,
    observation_file: Path,
    candidate_result_file: Path,
    *,
    expected_hold_minutes: int,
    prior_hold_files: Mapping[int, Path] | None = None,
    claim_registry: Path | None = None,
    result_validation_kwargs: Mapping[str, Any] | None = None,
    now: datetime,
) -> dict[str, Any]:
    if expected_hold_minutes not in (0, 5, 30):
        raise Ec5PhysicalError("hold must be exactly 0, 5, or 30 minutes")
    if now.tzinfo is None or now.utcoffset() is None:
        raise Ec5PhysicalError("hold validation current time must be timezone-aware")
    payload = _read_regular(
        Path(observation_file), label="hold observation", maximum=MAX_JSON_BYTES
    )
    root = _decode_json(payload, label="hold observation")
    _keys(
        root,
        {
            "schema_version", "kind", "candidate_id",
            "release_canonical_sha256", "panel", "candidate_result",
            "hold_minutes", "recorded_at", "temperature_c",
            "visual_stable", "electrical_normal", "esp32_not_restarted",
            "no_uncommanded_refresh", "prior_holds", "integrity",
        },
        label="hold observation",
    )
    if root["schema_version"] != 1 or root["kind"] != HOLD_KIND:
        raise Ec5PhysicalError("unsupported hold observation")
    if root["candidate_id"] != context.variant_id:
        raise Ec5PhysicalError("hold belongs to another candidate")
    if root["release_canonical_sha256"] != context.release_canonical_sha256:
        raise Ec5PhysicalError("hold belongs to another release")
    if _validate_panel(root["panel"], label="hold panel") != dict(context.panel):
        raise Ec5PhysicalError("hold belongs to another panel")
    integrity = _keys(root["integrity"], {"canonical_sha256"}, label="hold integrity")
    digest = _hex64(integrity["canonical_sha256"], label="hold canonical_sha256")
    unsigned = deepcopy(root)
    unsigned["integrity"]["canonical_sha256"] = None
    if _sha256(canonical_json_bytes(unsigned)) != digest:
        raise Ec5PhysicalError("hold integrity mismatch")
    result_ref = _candidate_result_reference(
        context,
        Path(candidate_result_file),
        claim_registry=claim_registry,
        result_validation_kwargs=result_validation_kwargs,
    )
    if root["candidate_result"] != result_ref:
        raise Ec5PhysicalError("hold does not bind the exact candidate result")
    if root["hold_minutes"] != expected_hold_minutes:
        raise Ec5PhysicalError("hold minute label mismatch")
    recorded = _parse_timestamp(root["recorded_at"], label="hold recorded_at")
    completed = _parse_timestamp(result_ref["completed_at"], label="candidate result completed_at")
    if recorded > now + timedelta(seconds=2):
        raise Ec5PhysicalError("hold timestamp is in the future")
    if recorded < completed + timedelta(minutes=expected_hold_minutes):
        raise Ec5PhysicalError("hold was recorded before the real elapsed boundary")
    _number(root["temperature_c"], label="hold temperature_c", minimum=10.0, maximum=45.0)
    for key in ("visual_stable", "electrical_normal", "esp32_not_restarted", "no_uncommanded_refresh"):
        _boolean(root[key], True, label=f"hold {key}")
    supplied = dict(prior_hold_files or {})
    required_prior = () if expected_hold_minutes == 0 else ((0,) if expected_hold_minutes == 5 else (0, 5))
    if set(supplied) != set(required_prior):
        raise Ec5PhysicalError("hold prior evidence set differs from contract")
    expected_prior: list[dict[str, Any]] = []
    prior_roots: dict[int, Mapping[str, Any]] = {}
    for minute in required_prior:
        prior_path = Path(supplied[minute])
        prior_payload = _read_regular(prior_path, label=f"hold {minute}", maximum=MAX_JSON_BYTES)
        prior_root = _decode_json(prior_payload, label=f"hold {minute}")
        _validate_hold_observation_at(
            context,
            prior_path,
            candidate_result_file,
            expected_hold_minutes=minute,
            prior_hold_files={m: supplied[m] for m in (() if minute == 0 else ((0,) if minute == 5 else (0, 5)))},
            claim_registry=claim_registry,
            result_validation_kwargs=result_validation_kwargs,
            now=now,
        )
        prior_roots[minute] = prior_root
        expected_prior.append(_hold_file_reference(prior_path, prior_root, prior_payload))
    if root["prior_holds"] != expected_prior:
        raise Ec5PhysicalError("hold prior evidence binding mismatch")
    if expected_hold_minutes == 5:
        prior_time = _parse_timestamp(prior_roots[0]["recorded_at"], label="hold0 recorded_at")
        if recorded < prior_time + timedelta(minutes=5):
            raise Ec5PhysicalError("U04 hold5 is compressed relative to hold0")
    if expected_hold_minutes == 30:
        hold0 = _parse_timestamp(prior_roots[0]["recorded_at"], label="hold0 recorded_at")
        hold5 = _parse_timestamp(prior_roots[5]["recorded_at"], label="hold5 recorded_at")
        if recorded < hold0 + timedelta(minutes=30) or hold5 < hold0 + timedelta(minutes=5):
            raise Ec5PhysicalError("U04 hold30 chain is compressed")
    return _hold_file_reference(Path(observation_file), root, payload)


def validate_hold_observation(
    context: ReleaseContext,
    observation_file: Path,
    candidate_result_file: Path,
    *,
    expected_hold_minutes: int,
    prior_hold_files: Mapping[int, Path] | None = None,
    claim_registry: Path | None = None,
    result_validation_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay an immutable hold against the current host wall clock."""

    return _validate_hold_observation_at(
        context,
        observation_file,
        candidate_result_file,
        expected_hold_minutes=expected_hold_minutes,
        prior_hold_files=prior_hold_files,
        claim_registry=claim_registry,
        result_validation_kwargs=result_validation_kwargs,
        now=_utc_now(),
    )


def record_hold_observation(
    context: ReleaseContext,
    *,
    candidate_result_file: Path,
    output_file: Path,
    hold_minutes: int,
    temperature_c: float,
    confirmations: Mapping[str, bool],
    prior_hold_files: Mapping[int, Path] | None = None,
    claim_registry: Path | None = None,
    result_validation_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_confirmation_keys = {
        "visual_stable", "electrical_normal", "esp32_not_restarted",
        "no_uncommanded_refresh",
    }
    if not isinstance(confirmations, Mapping) or set(confirmations) != expected_confirmation_keys:
        raise Ec5PhysicalError("hold confirmation fields differ")
    for key, value in confirmations.items():
        _boolean(value, True, label=f"hold confirmation {key}")
    _number(temperature_c, label="hold temperature_c", minimum=10.0, maximum=45.0)
    now = _utc_now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise Ec5PhysicalError("hold current time must be timezone-aware")
    result_ref = _candidate_result_reference(
        context,
        Path(candidate_result_file),
        claim_registry=claim_registry,
        result_validation_kwargs=result_validation_kwargs,
    )
    supplied = dict(prior_hold_files or {})
    required_prior = () if hold_minutes == 0 else ((0,) if hold_minutes == 5 else ((0, 5) if hold_minutes == 30 else None))
    if required_prior is None or set(supplied) != set(required_prior):
        raise Ec5PhysicalError("hold minute/prior evidence set differs")
    prior_refs: list[dict[str, Any]] = []
    for minute in required_prior:
        prior_refs.append(
            _validate_hold_observation_at(
                context,
                Path(supplied[minute]),
                candidate_result_file,
                expected_hold_minutes=minute,
                prior_hold_files={m: supplied[m] for m in (() if minute == 0 else (0,))},
                claim_registry=claim_registry,
                result_validation_kwargs=result_validation_kwargs,
                now=now,
            )
        )
    completed = _parse_timestamp(result_ref["completed_at"], label="candidate result completed_at")
    if now < completed + timedelta(minutes=hold_minutes):
        raise Ec5PhysicalError("hold boundary has not elapsed in host wall clock")
    if hold_minutes == 5:
        hold0 = _parse_timestamp(prior_refs[0]["recorded_at"], label="hold0 recorded_at")
        if now < hold0 + timedelta(minutes=5):
            raise Ec5PhysicalError("five minutes have not elapsed since hold0")
    if hold_minutes == 30:
        hold0 = _parse_timestamp(prior_refs[0]["recorded_at"], label="hold0 recorded_at")
        if now < hold0 + timedelta(minutes=30):
            raise Ec5PhysicalError("thirty minutes have not elapsed since hold0")
    recorded_at = now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    artifact = {
        "schema_version": 1,
        "kind": HOLD_KIND,
        "candidate_id": context.variant_id,
        "release_canonical_sha256": context.release_canonical_sha256,
        "panel": dict(context.panel),
        "candidate_result": result_ref,
        "hold_minutes": hold_minutes,
        "recorded_at": recorded_at,
        "temperature_c": float(temperature_c),
        "visual_stable": confirmations["visual_stable"],
        "electrical_normal": confirmations["electrical_normal"],
        "esp32_not_restarted": confirmations["esp32_not_restarted"],
        "no_uncommanded_refresh": confirmations["no_uncommanded_refresh"],
        "prior_holds": prior_refs,
        "integrity": {"canonical_sha256": None},
    }
    artifact["integrity"]["canonical_sha256"] = _sha256(canonical_json_bytes(artifact))
    _write_immutable(Path(output_file), artifact)
    _validate_hold_observation_at(
        context,
        Path(output_file),
        candidate_result_file,
        expected_hold_minutes=hold_minutes,
        prior_hold_files=supplied,
        claim_registry=claim_registry,
        result_validation_kwargs=result_validation_kwargs,
        now=now,
    )
    return artifact


def validate_u04_hold_observation(
    context: ReleaseContext,
    observation_file: Path,
    u04_result_file: Path,
    *,
    expected_hold_minutes: int,
    prior_hold_files: Mapping[int, Path] | None = None,
    claim_registry: Path | None = None,
) -> dict[str, Any]:
    if context.variant_id != "U04":
        raise Ec5PhysicalError("U04 hold wrapper requires the U04 context")
    return validate_hold_observation(
        context,
        observation_file,
        u04_result_file,
        expected_hold_minutes=expected_hold_minutes,
        prior_hold_files=prior_hold_files,
        claim_registry=claim_registry,
    )


def record_u04_hold_observation(
    context: ReleaseContext,
    *,
    u04_result_file: Path,
    output_file: Path,
    hold_minutes: int,
    temperature_c: float,
    confirmations: Mapping[str, bool],
    prior_hold_files: Mapping[int, Path] | None = None,
    claim_registry: Path | None = None,
) -> dict[str, Any]:
    if context.variant_id != "U04":
        raise Ec5PhysicalError("U04 hold wrapper requires the U04 context")
    return record_hold_observation(
        context,
        candidate_result_file=u04_result_file,
        output_file=output_file,
        hold_minutes=hold_minutes,
        temperature_c=temperature_c,
        confirmations=confirmations,
        prior_hold_files=prior_hold_files,
        claim_registry=claim_registry,
    )


def validate_u04_review(
    context: ReleaseContext,
    review_file: Path,
    u04_result_file: Path,
    *,
    hold_0_file: Path | None = None,
    hold_5_file: Path | None = None,
    hold_30_file: Path | None = None,
    white_recovery_result_file: Path | None = None,
    rc2g_binary_file: Path | None = None,
    white_claim_registry: Path | None = None,
    claim_registry: Path | None = None,
) -> dict[str, Any]:
    required_files = (hold_0_file, hold_5_file, hold_30_file, white_recovery_result_file, rc2g_binary_file)
    if any(path is None for path in required_files):
        raise Ec5PhysicalError("U04 review requires hold0/5/30, after-u04 white result, and frozen RC2G binary")
    if context.variant_id != "U07" or not context.panel_verified:
        raise Ec5PhysicalError("finalized U04 review is only a verified-panel U07 gate")
    now = _utc_now()
    u04_context = load_release(
        context.path, "U04", source_root=context.source_root, panel_file=context.panel_file
    )
    holds = {
        0: _validate_hold_observation_at(
            u04_context, Path(hold_0_file), u04_result_file,
            expected_hold_minutes=0, claim_registry=claim_registry, now=now,
        ),
        5: _validate_hold_observation_at(
            u04_context, Path(hold_5_file), u04_result_file,
            expected_hold_minutes=5, prior_hold_files={0: Path(hold_0_file)},
            claim_registry=claim_registry, now=now,
        ),
        30: _validate_hold_observation_at(
            u04_context, Path(hold_30_file), u04_result_file,
            expected_hold_minutes=30,
            prior_hold_files={0: Path(hold_0_file), 5: Path(hold_5_file)},
            claim_registry=claim_registry, now=now,
        ),
    }
    from tools import mf1750_ec5_white_recovery_once as white_runner

    try:
        white_ref = white_runner.load_result_binding(
            result_file=Path(white_recovery_result_file),
            panel_file=Path(context.panel_file),
            rc2g_binary_file=Path(rc2g_binary_file),
            claim_registry=Path(white_claim_registry or white_runner.DEFAULT_CLAIM_REGISTRY),
            release_file=context.path,
            candidate_result_file=Path(u04_result_file),
            candidate_claim_registry=Path(claim_registry or DEFAULT_CLAIM_REGISTRY),
        )
    except white_runner.WhiteRecoveryError as error:
        raise Ec5PhysicalError(f"after-u04 white recovery replay failed: {error}") from error
    if white_ref["stage"] != "after-u04" or white_ref["candidate_binding"]["candidate_id"] != "U04":
        raise Ec5PhysicalError("white recovery is not the exact after-u04 action")
    hold30_time = _parse_timestamp(holds[30]["recorded_at"], label="hold30 recorded_at")
    if _parse_timestamp(white_ref["completed_at"], label="white recovery completed_at") < hold30_time:
        raise Ec5PhysicalError("white recovery completed before the hold30 evidence")

    payload = _read_regular(Path(review_file), label="finalized U04 review", maximum=MAX_JSON_BYTES)
    root = _decode_json(payload, label="finalized U04 review")
    _keys(
        root,
        {"schema_version", "kind", "release_canonical_sha256", "panel", "u04_result", "hold_observations", "white_recovery", "gates", "reviewer", "integrity"},
        label="finalized U04 review",
    )
    if root["schema_version"] != 2 or root["kind"] != U04_REVIEW_KIND:
        raise Ec5PhysicalError("unsupported hardened U04 review")
    if root["release_canonical_sha256"] != context.release_canonical_sha256 or _validate_panel(root["panel"], label="U04 review panel") != dict(context.panel):
        raise Ec5PhysicalError("U04 review release/panel binding mismatch")
    integrity = _keys(root["integrity"], {"canonical_sha256"}, label="U04 review integrity")
    digest = _hex64(integrity["canonical_sha256"], label="U04 review canonical_sha256")
    unsigned = deepcopy(root)
    unsigned["integrity"]["canonical_sha256"] = None
    if _sha256(canonical_json_bytes(unsigned)) != digest:
        raise Ec5PhysicalError("U04 review integrity mismatch")
    result_ref = _u04_result_reference(u04_context, Path(u04_result_file), claim_registry=claim_registry)
    if root["u04_result"] != result_ref or root["hold_observations"] != [holds[0], holds[5], holds[30]] or root["white_recovery"] != white_ref:
        raise Ec5PhysicalError("U04 review external evidence binding mismatch")
    gates = _keys(root["gates"], {"left_right_match", "preview_match", "white_recovery_visual_pass", "electrical_normal", "esp32_not_restarted", "no_uncommanded_refresh", "review_pass"}, label="U04 review gates")
    for key, value in gates.items():
        _boolean(value, True, label=f"U04 review gate {key}")
    reviewer = _keys(root["reviewer"], {"name", "reviewed_at"}, label="U04 review reviewer")
    if reviewer["name"] != "Ye":
        raise Ec5PhysicalError("U04 review reviewer must be Ye")
    reviewed = _parse_timestamp(reviewer["reviewed_at"], label="U04 review reviewed_at")
    if reviewed > now + timedelta(seconds=2) or reviewed < _parse_timestamp(white_ref["completed_at"], label="white completed_at"):
        raise Ec5PhysicalError("U04 review finalization time is future or before white recovery")
    return {
        "kind": U04_REVIEW_KIND,
        "file_sha256": _sha256(payload),
        "canonical_sha256": digest,
        "release_canonical_sha256": context.release_canonical_sha256,
        "panel": dict(context.panel),
        "u04_result_file_sha256": result_ref["file_sha256"],
        "u04_attempt_id": result_ref["attempt_id"],
        "hold_file_sha256": {str(m): holds[m]["file_sha256"] for m in (0, 5, 30)},
        "white_recovery_result_file_sha256": white_ref["file_sha256"],
        "reviewer": "Ye",
        "review_pass": True,
    }


_FINALIZE_CONFIRMATION_KEYS = {
    "left_right_match",
    "preview_match",
    "white_recovery_visual_pass",
    "electrical_normal",
    "esp32_not_restarted",
    "no_uncommanded_refresh",
}


def finalize_u04_review(
    context: ReleaseContext,
    *,
    u04_result_file: Path,
    hold_0_file: Path,
    hold_5_file: Path,
    hold_30_file: Path,
    white_recovery_result_file: Path,
    rc2g_binary_file: Path,
    output_file: Path,
    reviewer: str,
    confirmations: Mapping[str, bool],
    white_claim_registry: Path | None = None,
    claim_registry: Path | None = None,
) -> dict[str, Any]:
    if context.variant_id != "U04" or not context.panel_verified or reviewer != "Ye":
        raise Ec5PhysicalError("U04 review finalizer requires verified U04 panel and reviewer Ye")
    if not isinstance(confirmations, Mapping) or set(confirmations) != _FINALIZE_CONFIRMATION_KEYS:
        raise Ec5PhysicalError("U04 review confirmation fields differ")
    for key, value in confirmations.items():
        _boolean(value, True, label=f"U04 review confirmation {key}")
    now = _utc_now()
    holds = {
        0: _validate_hold_observation_at(context, hold_0_file, u04_result_file, expected_hold_minutes=0, claim_registry=claim_registry, now=now),
        5: _validate_hold_observation_at(context, hold_5_file, u04_result_file, expected_hold_minutes=5, prior_hold_files={0: hold_0_file}, claim_registry=claim_registry, now=now),
        30: _validate_hold_observation_at(context, hold_30_file, u04_result_file, expected_hold_minutes=30, prior_hold_files={0: hold_0_file, 5: hold_5_file}, claim_registry=claim_registry, now=now),
    }
    from tools import mf1750_ec5_white_recovery_once as white_runner
    try:
        white_ref = white_runner.load_result_binding(
            result_file=white_recovery_result_file,
            panel_file=Path(context.panel_file),
            rc2g_binary_file=rc2g_binary_file,
            claim_registry=Path(white_claim_registry or white_runner.DEFAULT_CLAIM_REGISTRY),
            release_file=context.path,
            candidate_result_file=u04_result_file,
            candidate_claim_registry=Path(claim_registry or DEFAULT_CLAIM_REGISTRY),
        )
    except white_runner.WhiteRecoveryError as error:
        raise Ec5PhysicalError(f"after-u04 white recovery replay failed: {error}") from error
    if white_ref["stage"] != "after-u04" or _parse_timestamp(white_ref["completed_at"], label="white completed_at") < _parse_timestamp(holds[30]["recorded_at"], label="hold30 recorded_at"):
        raise Ec5PhysicalError("white recovery is wrong stage or predates hold30")
    result_ref = _u04_result_reference(context, u04_result_file, claim_registry=claim_registry)
    reviewed_at = now.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    review = {
        "schema_version": 2,
        "kind": U04_REVIEW_KIND,
        "release_canonical_sha256": context.release_canonical_sha256,
        "panel": dict(context.panel),
        "u04_result": result_ref,
        "hold_observations": [holds[0], holds[5], holds[30]],
        "white_recovery": white_ref,
        "gates": {**dict(confirmations), "review_pass": True},
        "reviewer": {"name": reviewer, "reviewed_at": reviewed_at},
        "integrity": {"canonical_sha256": None},
    }
    review["integrity"]["canonical_sha256"] = _sha256(canonical_json_bytes(review))
    _write_immutable(output_file, review)
    u07_context = load_release(context.path, "U07", source_root=context.source_root, panel_file=context.panel_file)
    validate_u04_review(
        u07_context,
        output_file,
        u04_result_file,
        hold_0_file=hold_0_file,
        hold_5_file=hold_5_file,
        hold_30_file=hold_30_file,
        white_recovery_result_file=white_recovery_result_file,
        rc2g_binary_file=rc2g_binary_file,
        white_claim_registry=white_claim_registry,
        claim_registry=claim_registry,
    )
    return review


def describe(context: ReleaseContext) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-physical-once-description",
        "candidate_id": context.variant_id,
        "candidate_code": context.variant["candidate_code"],
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "layout_id": context.variant["layout_id"],
        "firmware": {
            "file": str(context.binary_path),
            "bytes": context.variant["firmware"]["bytes"],
            "sha256": context.binary_sha256,
        },
        "panel": dict(context.panel),
        "live_panel_identity_verified": context.panel_verified,
        "u07_run_requires_finalized_u04_review": context.variant_id == "U07",
        "u07_run_requires_exact_u04_result_bytes": context.variant_id == "U07",
        "required_authorization": required_authorization(context),
        "run_requires_same_boot_j2_off_diagnostic": True,
        "diagnostic_get_requests": 4,
        "diagnostic_post_requests": 0,
        "diagnostic_claim_created": False,
        "preflight_is_get_only": True,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "authorization_created": False,
        "claim_created": False,
        "network_requests": 0,
    }


def _base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise Ec5PhysicalError("base URL must be a plain http device origin")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise Ec5PhysicalError("base URL must not include path, query, credentials, or fragment")
    host = parsed.hostname
    if host not in ("localhost", "127.0.0.1"):
        try:
            parts = [int(part) for part in host.split(".")]
        except ValueError as error:
            raise Ec5PhysicalError("device host must be an IPv4 literal") from error
        if len(parts) != 4 or any(part < 0 or part > 255 for part in parts):
            raise Ec5PhysicalError("device host must be an IPv4 literal")
        if not (parts[0] == 10 or parts[:2] == [192, 168] or parts[:2] == [172, 16] or (parts[0] == 172 and 16 <= parts[1] <= 31)):
            raise Ec5PhysicalError("device host must be loopback or RFC1918 private IPv4")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"http://{host}{port}"


def _http_json_with_payload(
    base_url: str,
    endpoint: str,
    *,
    method: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[Mapping[str, Any], bytes]:
    request = urllib.request.Request(
        base_url + endpoint,
        data=None,
        headers=dict(headers or {}),
        method=method,
    )
    try:
        with _urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            payload = response.read(MAX_JSON_BYTES + 1)
    except Exception as error:
        raise Ec5PhysicalReadError(f"{method} {endpoint} failed: {error}") from error
    if status < 200 or status >= 300:
        raise Ec5PhysicalReadError(f"{method} {endpoint} returned HTTP {status}")
    return _decode_json(payload, label=f"{method} {endpoint} response"), payload


def _http_json(
    base_url: str,
    endpoint: str,
    *,
    method: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> Mapping[str, Any]:
    value, _payload = _http_json_with_payload(
        base_url,
        endpoint,
        method=method,
        headers=headers,
        timeout_seconds=timeout_seconds,
        _urlopen=_urlopen,
    )
    return value


def _expect_identity(value: Mapping[str, Any], context: ReleaseContext, *, label: str, boot_nonce: str | None = None) -> str | None:
    expected = {
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise Ec5PhysicalError(f"{label} {key} mismatch")
    if boot_nonce is not None and value.get("boot_nonce") != boot_nonce:
        raise Ec5PhysicalError(f"{label} boot_nonce is stale or mismatched")
    candidate = value.get("candidate_code")
    if candidate is not None and candidate != context.variant["candidate_code"]:
        raise Ec5PhysicalError(f"{label} candidate_code mismatch")
    return value.get("boot_nonce") if isinstance(value.get("boot_nonce"), str) else None


def _expected_identity_revision(context: ReleaseContext) -> str:
    revision = _string(
        context.variant.get("identity_revision"),
        label=f"variant {context.variant_id}.identity_revision",
    )
    if revision != EXPECTED_IDENTITY_REVISION:
        raise Ec5PhysicalError("release variant is not the corrected-v2 identity")
    return revision


def _expected_nvs_contract(context: ReleaseContext) -> Mapping[str, Any]:
    contract = _keys(
        context.variant.get("nvs_contract"),
        {"legacy", "active"},
        label=f"variant {context.variant_id}.nvs_contract",
    )
    legacy = _keys(
        contract["legacy"],
        {"namespace", "key", "expected_present", "expected_phase", "read_only"},
        label=f"variant {context.variant_id}.nvs_contract.legacy",
    )
    active = _keys(
        contract["active"],
        {"namespace", "key", "expected_present", "expected_phase", "read_only"},
        label=f"variant {context.variant_id}.nvs_contract.active",
    )
    for name, entry in (("legacy", legacy), ("active", active)):
        _string(entry["namespace"], label=f"nvs_contract.{name}.namespace")
        _string(entry["key"], label=f"nvs_contract.{name}.key")
        if not isinstance(entry["expected_present"], bool):
            raise Ec5PhysicalError(
                f"nvs_contract.{name}.expected_present must be boolean"
            )
        _integer(
            entry["expected_phase"],
            label=f"nvs_contract.{name}.expected_phase",
            minimum=0,
        )
        if not isinstance(entry["read_only"], bool):
            raise Ec5PhysicalError(f"nvs_contract.{name}.read_only must be boolean")
    if legacy["read_only"] is not True:
        raise Ec5PhysicalError("legacy NVS contract must be read-only")
    if (
        active["expected_present"] is not False
        or active["expected_phase"] != 0
        or active["read_only"] is not False
    ):
        raise Ec5PhysicalError("active corrected-v2 NVS contract must start virgin")
    if legacy["namespace"] == active["namespace"]:
        raise Ec5PhysicalError("legacy and active NVS namespaces must be isolated")
    return contract


def _validate_nvs_evidence(
    value: Mapping[str, Any],
    context: ReleaseContext,
    *,
    expected_active_phase: int,
    label: str,
) -> None:
    contract = _expected_nvs_contract(context)
    if not _strict_json_equal(value.get("nvs_contract"), contract):
        raise Ec5PhysicalError(f"{label} NVS contract mismatch")
    legacy = contract["legacy"]
    expected = {
        "legacy_key_present": legacy["expected_present"],
        "legacy_phase": legacy["expected_phase"],
        "legacy_match": True,
        "active_key_present": expected_active_phase != 0,
        "active_phase": expected_active_phase,
        "active_virgin": expected_active_phase == 0,
        "migration_ready": True,
    }
    for key, wanted in expected.items():
        if not _strict_json_equal(value.get(key), wanted):
            raise Ec5PhysicalError(f"{label} {key} mismatch")


def _validate_version(value: Mapping[str, Any], context: ReleaseContext) -> None:
    _keys(
        value,
        {
            "schema_version", "kind", "build_tag", "device_api_version",
            "identity_revision", "driver_api_version", "candidate_code", "layout_id",
            "automatic_execute", "startup_refresh", "raw_frame_ingress",
            "retry", "recovery", "boot_fixture_guard", "persistent_claim",
            "arm_required", "execute_limit_per_binary_candidate", "safety_scope",
        },
        label="device version",
    )
    if value.get("schema_version") != EXPECTED_DEVICE_SCHEMA_VERSION or value.get("kind") != "mf1750-ec5-unknown-probe-version":
        raise Ec5PhysicalError("device version schema/kind mismatch")
    if value.get("build_tag") != context.variant["build_tag"]:
        raise Ec5PhysicalError("device version build_tag mismatch")
    if value.get("candidate_code") != f"0x{context.variant['candidate_code']:x}":
        raise Ec5PhysicalError("device version candidate code mismatch")
    if value.get("layout_id") != context.variant["layout_id"]:
        raise Ec5PhysicalError("device version layout mismatch")
    if value.get("driver_api_version") != EXPECTED_DRIVER_API_VERSION:
        raise Ec5PhysicalError("device version driver API mismatch")
    if value.get("device_api_version") != EXPECTED_DEVICE_API_VERSION:
        raise Ec5PhysicalError("device version EC5 device API mismatch")
    if value.get("identity_revision") != _expected_identity_revision(context):
        raise Ec5PhysicalError("device version identity revision mismatch")
    expected_flags = {
        "automatic_execute": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "retry": False,
        "recovery": False,
        "persistent_claim": True,
        "arm_required": True,
    }
    for key, expected in expected_flags.items():
        if value.get(key) is not expected:
            raise Ec5PhysicalError(f"device version {key} mismatch")
    if value.get("execute_limit_per_binary_candidate") != 1:
        raise Ec5PhysicalError("device version does not enforce one execute")
    if value.get("boot_fixture_guard") != "exact_driver_action_validator":
        raise Ec5PhysicalError("device version boot fixture guard mismatch")
    if value.get("safety_scope") != "accidental_post_interlock_not_hardware_authorization":
        raise Ec5PhysicalError("device version safety scope mismatch")


def _validate_device_manifest(value: Mapping[str, Any], context: ReleaseContext) -> None:
    _keys(
        value,
        {
            "schema_version", "kind", "scope", "layout_id", "test_id",
            "action_id", "candidate_code", "candidate_code_hex",
            "intended_initial_code", "sequence_class", "repetition", "width",
            "height", "frame_bytes", "pixel_packing", "roi_cs1", "roi_cs2",
            "guard_cs1", "guard_cs2", "known_white_pixels", "unknown_pixels",
            "frame_sha256", "frame_fnv1a", "cs1_dtm_sha256", "cs1_dtm_fnv1a",
            "cs2_dtm_sha256", "cs2_dtm_fnv1a", "mapping_cs1", "mapping_cs2",
            "build_tag", "device_api_version", "identity_revision", "otp_mode",
            "mutation_contract", "nvs_contract", "legacy_key_present",
            "legacy_phase", "legacy_match", "active_key_present", "active_phase",
            "active_virgin", "migration_ready",
            "exact_driver_fixture_guard_required", "manifest_payload_sha256",
            "binary_sha256", "external_build_sidecar_required",
        },
        label="device manifest",
    )
    if value.get("schema_version") != EXPECTED_DEVICE_SCHEMA_VERSION or value.get("kind") != "mf1750-ec5-compiled-fixture-manifest":
        raise Ec5PhysicalError("device manifest schema/kind mismatch")
    _expect_identity(value, context, label="device manifest")
    checks = {
        "scope": "experimental_scaffold_not_hardware_authorization",
        "layout_id": context.variant["layout_id"],
        "candidate_code_hex": f"0x{context.variant['candidate_code']:x}",
        "intended_initial_code": 1,
        "sequence_class": "white_initial_single_probe",
        "repetition": 1,
        "width": 1024,
        "height": 600,
        "frame_bytes": 307200,
        "pixel_packing": "row_major_4bpp_even_x_high_nibble",
        "known_white_pixels": 606208,
        "unknown_pixels": 8192,
        "roi_cs1": {"x0": 224, "x1": 288, "y0": 268, "y1": 332},
        "roi_cs2": {"x0": 736, "x1": 800, "y0": 268, "y1": 332},
        "guard_cs1": {"x0": 192, "x1": 320, "y0": 236, "y1": 364},
        "guard_cs2": {"x0": 704, "x1": 832, "y0": 236, "y1": 364},
        "mapping_cs1": [0, 0, 0, 0],
        "mapping_cs2": [1, 0, 0, 0],
        "frame_sha256": context.variant["frame_sha256"],
        "frame_fnv1a": f"0x{context.variant['frame_fnv1a']:08x}",
        "cs1_dtm_sha256": context.variant["dtm_sha256"],
        "cs1_dtm_fnv1a": f"0x{context.variant['dtm_fnv1a']:08x}",
        "cs2_dtm_sha256": context.variant["dtm_sha256"],
        "cs2_dtm_fnv1a": f"0x{context.variant['dtm_fnv1a']:08x}",
        "otp_mode": "existing_on_chip_otp_unchanged",
        "external_build_sidecar_required": True,
        "manifest_payload_sha256": None,
        "binary_sha256": None,
        "device_api_version": EXPECTED_DEVICE_API_VERSION,
        "identity_revision": _expected_identity_revision(context),
        "exact_driver_fixture_guard_required": True,
    }
    for key, expected in checks.items():
        actual = value.get(key)
        if key.endswith("fnv1a") and isinstance(actual, str):
            actual = actual.lower()
        if actual != expected:
            raise Ec5PhysicalError(f"device manifest {key} mismatch")
    if value.get("candidate_code") != context.variant["candidate_code"]:
        raise Ec5PhysicalError("device manifest candidate mismatch")
    mutation = value.get("mutation_contract")
    _keys(
        mutation,
        {
            "bodyless", "exact_build_test_action_boot_nonce",
            "arm_nonce_required_for_execute", "not_hardware_authorization",
        },
        label="device manifest mutation_contract",
    )
    for key in ("bodyless", "exact_build_test_action_boot_nonce", "arm_nonce_required_for_execute", "not_hardware_authorization"):
        if mutation.get(key) is not True:
            raise Ec5PhysicalError(f"device manifest mutation_contract.{key} mismatch")
    _validate_nvs_evidence(
        value,
        context,
        expected_active_phase=0,
        label="device manifest",
    )


def _validate_status(
    value: Mapping[str, Any],
    context: ReleaseContext,
    *,
    boot_nonce: str | None,
    allowed_states: set[str],
) -> str:
    _keys(
        value,
        {
            "schema_version", "kind", "boot_nonce", "build_tag",
            "device_api_version", "identity_revision", "test_id", "action_id", "state",
            "fixture_self_check_passed", "driver_fixture_guard_passed",
            "claim_store_ready", "persistent_phase", "arm_request_count",
            "execute_consumed", "execute_pending", "execute_request_count",
            "driver_call_count", "gpio_initialized", "busy", "rst", "cs", "cs2",
            "nvs_contract", "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin", "migration_ready",
        },
        label="device status",
    )
    if value.get("schema_version") != EXPECTED_DEVICE_SCHEMA_VERSION or value.get("kind") != "mf1750-ec5-unknown-probe-status":
        raise Ec5PhysicalError("device status schema/kind mismatch")
    _expect_identity(value, context, label="device status", boot_nonce=boot_nonce)
    if value.get("device_api_version") != EXPECTED_DEVICE_API_VERSION:
        raise Ec5PhysicalError("device status EC5 device API mismatch")
    if value.get("identity_revision") != _expected_identity_revision(context):
        raise Ec5PhysicalError("device status identity revision mismatch")
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None or nonce == "0" * 16:
        raise Ec5PhysicalError("device status boot_nonce is malformed")
    if value.get("state") not in allowed_states:
        raise Ec5PhysicalError(f"device status state {value.get('state')!r} is not allowed")
    if (
        value.get("fixture_self_check_passed") is not True
        or value.get("driver_fixture_guard_passed") is not True
        or value.get("claim_store_ready") is not True
    ):
        raise Ec5PhysicalError("device fixture or persistent claim store is not ready")
    for key in ("persistent_phase", "arm_request_count", "execute_request_count", "driver_call_count"):
        _integer(value.get(key), label=f"device status {key}")
    for key in ("execute_consumed", "execute_pending", "gpio_initialized"):
        if not isinstance(value.get(key), bool):
            raise Ec5PhysicalError(f"device status {key} must be boolean")
    if value.get("gpio_initialized") is not True:
        raise Ec5PhysicalError("device GPIO is not initialized")
    for key in ("busy", "rst", "cs", "cs2"):
        if value.get(key) not in (0, 1):
            raise Ec5PhysicalError(f"device status {key} is not a GPIO level")
    _validate_nvs_evidence(
        value,
        context,
        expected_active_phase=value["persistent_phase"],
        label="device status",
    )
    return nonce


def _require_safe_idle_gpio(
    value: Mapping[str, Any], *, label: str, busy_level: int = 1
) -> None:
    if busy_level not in (0, 1):
        raise Ec5PhysicalError("expected BUSY level must be 0 or 1")
    expected = {"busy": busy_level, "rst": 0, "cs": 0, "cs2": 0}
    for key, level in expected.items():
        if value.get(key) != level:
            raise Ec5PhysicalError(f"{label} {key} must be safe idle level {level}")


def _read_preflight_endpoints(
    base_url: str,
    *,
    timeout_seconds: float,
    _urlopen: Callable[..., Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, bytes]]:
    values: dict[str, Mapping[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for name in ("version", "manifest", "status", "report"):
        value, payload = _http_json_with_payload(
            base_url,
            _ENDPOINTS[name],
            method="GET",
            timeout_seconds=timeout_seconds,
            _urlopen=_urlopen,
        )
        values[name] = value
        payloads[name] = payload
    return values, payloads


def _validate_virgin_report(
    report: Mapping[str, Any], context: ReleaseContext, boot_nonce: str
) -> None:
    _keys(
        report,
        {
            "schema_version", "kind", "valid", "test_id", "build_tag",
            "device_api_version", "identity_revision", "boot_nonce", "action_id",
            "candidate_code", "terminal_state", "error",
            "driver_fixture_guard_passed", "execute_consumed", "driver_called",
            "persistent_phase", "no_retry", "no_recovery", "nvs_contract",
            "legacy_key_present", "legacy_phase", "legacy_match",
            "active_key_present", "active_phase", "active_virgin",
            "migration_ready",
        },
        label="virgin preflight report",
    )
    if (
        report.get("schema_version") != EXPECTED_DEVICE_SCHEMA_VERSION
        or report.get("kind") != "mf1750-ec5-unknown-probe-report"
        or report.get("valid") is not False
        or report.get("error") != "no_execute_report"
    ):
        raise Ec5PhysicalError("device preflight report is not the virgin sentinel")
    _expect_identity(
        report,
        context,
        label="virgin preflight report",
        boot_nonce=boot_nonce,
    )
    if (
        report.get("candidate_code") != context.variant["candidate_code"]
        or report.get("device_api_version") != EXPECTED_DEVICE_API_VERSION
        or report.get("identity_revision") != _expected_identity_revision(context)
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_fixture_guard_passed") is not True
        or report.get("execute_consumed") is not False
        or report.get("driver_called") is not False
        or report.get("persistent_phase") != 0
        or report.get("no_retry") is not True
        or report.get("no_recovery") is not True
    ):
        raise Ec5PhysicalError("device virgin report identity/state evidence mismatch")
    _validate_nvs_evidence(
        report,
        context,
        expected_active_phase=0,
        label="virgin preflight report",
    )


def _validate_virgin_snapshot(
    context: ReleaseContext,
    values: Mapping[str, Mapping[str, Any]],
    *,
    busy_level: int,
    expected_boot_nonce: str | None,
) -> str:
    if set(values) != {"version", "manifest", "status", "report"}:
        raise Ec5PhysicalError("preflight snapshot must contain exactly four endpoints")
    _validate_version(values["version"], context)
    _validate_device_manifest(values["manifest"], context)
    boot_nonce = _validate_status(
        values["status"],
        context,
        boot_nonce=expected_boot_nonce,
        allowed_states={"ready"},
    )
    _require_safe_idle_gpio(
        values["status"],
        label="virgin preflight status",
        busy_level=busy_level,
    )
    status = values["status"]
    if (
        status["persistent_phase"] != 0
        or status["arm_request_count"] != 0
        or status["execute_request_count"] != 0
        or status["driver_call_count"] != 0
    ):
        raise Ec5PhysicalError("device candidate is not virgin")
    if status["execute_consumed"] or status["execute_pending"]:
        raise Ec5PhysicalError("device candidate already has execute state")
    _validate_virgin_report(values["report"], context, boot_nonce)
    return boot_nonce


def preflight(
    context: ReleaseContext,
    base_url: str,
    *,
    expected_boot_nonce: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not context.panel_verified:
        raise Ec5PhysicalError("live panel identity must be verified before preflight")
    base = _base_url(base_url)
    values, _payloads = _read_preflight_endpoints(
        base,
        timeout_seconds=timeout_seconds,
        _urlopen=_urlopen,
    )
    boot_nonce = _validate_virgin_snapshot(
        context,
        values,
        busy_level=1,
        expected_boot_nonce=expected_boot_nonce,
    )
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-get-only-preflight",
        "candidate_id": context.variant_id,
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "boot_nonce": boot_nonce,
        "identity_revision": _expected_identity_revision(context),
        "migration_ready": True,
        "state": "ready",
        "persistent_phase": 0,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "authorization_created": False,
    }


def _raw_endpoint_records(payloads: Mapping[str, bytes]) -> list[dict[str, Any]]:
    if set(payloads) != {"version", "manifest", "status", "report"}:
        raise Ec5PhysicalError("raw preflight evidence must contain four endpoints")
    records: list[dict[str, Any]] = []
    for name in ("version", "manifest", "status", "report"):
        payload = payloads[name]
        records.append(
            {
                "name": name,
                "path": _ENDPOINTS[name],
                "raw_base64": base64.b64encode(payload).decode("ascii"),
                "payload_bytes": len(payload),
                "payload_sha256": _sha256(payload),
            }
        )
    return records


def _replay_raw_endpoint_records(
    records: Any,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, bytes]]:
    if not isinstance(records, list) or len(records) != 4:
        raise Ec5PhysicalError("diagnostic endpoint evidence must contain four records")
    values: dict[str, Mapping[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    expected_names = ("version", "manifest", "status", "report")
    for index, (record_value, expected_name) in enumerate(
        zip(records, expected_names, strict=True)
    ):
        record = _keys(
            record_value,
            {"name", "path", "raw_base64", "payload_bytes", "payload_sha256"},
            label=f"diagnostic endpoint record {index}",
        )
        if (
            record["name"] != expected_name
            or record["path"] != _ENDPOINTS[expected_name]
        ):
            raise Ec5PhysicalError("diagnostic endpoint order/path mismatch")
        encoded = _string(
            record["raw_base64"],
            label=f"diagnostic {expected_name} raw_base64",
        )
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error) as error:
            raise Ec5PhysicalError(
                f"diagnostic {expected_name} raw bytes are not canonical base64"
            ) from error
        if base64.b64encode(payload).decode("ascii") != encoded:
            raise Ec5PhysicalError(
                f"diagnostic {expected_name} raw bytes are not canonical base64"
            )
        payload_bytes = _integer(
            record["payload_bytes"],
            label=f"diagnostic {expected_name} payload_bytes",
            minimum=1,
        )
        payload_sha256 = _hex64(
            record["payload_sha256"],
            label=f"diagnostic {expected_name} payload_sha256",
        )
        if len(payload) != payload_bytes or _sha256(payload) != payload_sha256:
            raise Ec5PhysicalError(
                f"diagnostic {expected_name} raw payload length/SHA mismatch"
            )
        values[expected_name] = _decode_json(
            payload,
            label=f"diagnostic {expected_name} raw payload",
        )
        payloads[expected_name] = payload
    return values, payloads


def _diagnostic_release_binding(context: ReleaseContext) -> dict[str, Any]:
    manifest_payload = _read_regular(
        context.path,
        label="EC5 release manifest",
        maximum=MAX_JSON_BYTES,
    )
    firmware_payload = _read_regular(
        context.binary_path,
        label=f"{context.variant_id} firmware binary",
        maximum=MAX_BINARY_BYTES,
    )
    elf_payload = _read_regular(
        context.elf_path,
        label=f"{context.variant_id} firmware ELF",
        maximum=compiled_identity.MAX_ELF_BYTES,
    )
    if (
        _sha256(firmware_payload) != context.binary_sha256
        or _sha256(elf_payload) != context.elf_sha256
    ):
        raise Ec5PhysicalError("release artifacts changed after release validation")
    return {
        "manifest": {
            "file": str(context.path),
            "bytes": len(manifest_payload),
            "file_sha256": _sha256(manifest_payload),
            "canonical_sha256": context.release_canonical_sha256,
        },
        "firmware": {
            "file": str(context.binary_path),
            "bytes": len(firmware_payload),
            "sha256": context.binary_sha256,
        },
        "elf": {
            "file": str(context.elf_path),
            "bytes": len(elf_payload),
            "sha256": context.elf_sha256,
        },
        "compiled_identity_report": deepcopy(
            context.root["compiled_identity_report"]
        ),
    }


def _diagnostic_reference(
    path: Path, payload: bytes, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "integrity_sha256": evidence["integrity"]["canonical_sha256"],
        "candidate_id": evidence["candidate_id"],
        "action_id": evidence["action_id"],
        "boot_nonce": evidence["boot_nonce"],
        "created_at": evidence["created_at"],
        "state": evidence["state"],
    }


def validate_diagnostic_preflight(
    context: ReleaseContext, evidence_file: Path
) -> dict[str, Any]:
    payload = _read_regular(
        Path(evidence_file),
        label="EC5 J2-off diagnostic evidence",
        maximum=MAX_JSON_BYTES,
    )
    evidence = _decode_json(payload, label="EC5 J2-off diagnostic evidence")
    _keys(
        evidence,
        {
            "schema_version", "kind", "candidate_id", "candidate_code",
            "build_tag", "test_id", "action_id", "device_api_version",
            "identity_revision", "release", "incident_lineage", "panel",
            "boot_nonce", "endpoints", "gpio", "j2_driver_power_confirmed_off",
            "created_at", "get_requests", "post_requests", "claim_created",
            "authorization_created", "state", "integrity",
        },
        label="EC5 J2-off diagnostic evidence",
    )
    if (
        evidence.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION
        or evidence.get("kind") != DIAGNOSTIC_KIND
    ):
        raise Ec5PhysicalError("unsupported EC5 J2-off diagnostic evidence")
    integrity = _keys(
        evidence.get("integrity"),
        {"canonical_sha256"},
        label="diagnostic integrity",
    )
    expected_integrity = _hex64(
        integrity["canonical_sha256"],
        label="diagnostic integrity canonical_sha256",
    )
    unsigned = deepcopy(evidence)
    unsigned["integrity"]["canonical_sha256"] = None
    if _sha256(canonical_json_bytes(unsigned)) != expected_integrity:
        raise Ec5PhysicalError("diagnostic canonical integrity mismatch")
    if payload != canonical_json_bytes(evidence):
        raise Ec5PhysicalError("diagnostic evidence file is not canonical JSON")
    expected_links = {
        "candidate_id": context.variant_id,
        "candidate_code": context.variant["candidate_code"],
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "device_api_version": EXPECTED_DEVICE_API_VERSION,
        "identity_revision": _expected_identity_revision(context),
        "release": _diagnostic_release_binding(context),
        "incident_lineage": deepcopy(context.root["incident_lineage"]),
        "panel": dict(context.panel),
        "gpio": {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
        "j2_driver_power_confirmed_off": True,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "authorization_created": False,
        "state": "diagnostic_pass_j2_off_no_mutation",
    }
    for key, wanted in expected_links.items():
        if not _strict_json_equal(evidence.get(key), wanted):
            raise Ec5PhysicalError(f"diagnostic evidence {key} binding mismatch")
    _timestamp(evidence.get("created_at"), label="diagnostic created_at")
    values, _payloads = _replay_raw_endpoint_records(evidence["endpoints"])
    boot_nonce = _validate_virgin_snapshot(
        context,
        values,
        busy_level=0,
        expected_boot_nonce=None,
    )
    if evidence.get("boot_nonce") != boot_nonce:
        raise Ec5PhysicalError("diagnostic evidence boot_nonce mismatch")
    return _diagnostic_reference(Path(evidence_file), payload, evidence)


def diagnose_j2_off(
    context: ReleaseContext,
    base_url: str,
    *,
    confirm_j2_off: bool,
    evidence_file: Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not context.panel_verified:
        raise Ec5PhysicalError(
            "live panel identity must be verified before J2-off diagnosis"
        )
    if confirm_j2_off is not True:
        raise Ec5PhysicalError("--confirm-j2-off is required before diagnosis")
    evidence_path = Path(evidence_file)
    try:
        evidence_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise Ec5PhysicalError(f"cannot inspect diagnostic evidence path: {error}") from error
    else:
        raise Ec5PhysicalError(
            "diagnostic evidence already exists; immutable evidence is never overwritten"
        )
    base = _base_url(base_url)
    values, payloads = _read_preflight_endpoints(
        base,
        timeout_seconds=timeout_seconds,
        _urlopen=_urlopen,
    )
    boot_nonce = _validate_virgin_snapshot(
        context,
        values,
        busy_level=0,
        expected_boot_nonce=None,
    )
    evidence = _sealed_result(
        {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "kind": DIAGNOSTIC_KIND,
            "candidate_id": context.variant_id,
            "candidate_code": context.variant["candidate_code"],
            "build_tag": context.variant["build_tag"],
            "test_id": context.variant["test_id"],
            "action_id": context.variant["action_id"],
            "device_api_version": EXPECTED_DEVICE_API_VERSION,
            "identity_revision": _expected_identity_revision(context),
            "release": _diagnostic_release_binding(context),
            "incident_lineage": deepcopy(context.root["incident_lineage"]),
            "panel": dict(context.panel),
            "boot_nonce": boot_nonce,
            "endpoints": _raw_endpoint_records(payloads),
            "gpio": {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
            "j2_driver_power_confirmed_off": True,
            "created_at": _now(),
            "get_requests": 4,
            "post_requests": 0,
            "claim_created": False,
            "authorization_created": False,
            "state": "diagnostic_pass_j2_off_no_mutation",
        }
    )
    _write_immutable(evidence_path, evidence)
    return evidence


def _claim_registry() -> Path:
    return DEFAULT_CLAIM_REGISTRY


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _atomic_claim(
    context: ReleaseContext,
    attempt_id: str,
    *,
    claim_registry: Path | None = None,
    u04_review: Mapping[str, Any] | None = None,
) -> Claim:
    registry = Path(claim_registry) if claim_registry is not None else _claim_registry()
    if registry.exists() and (registry.is_symlink() or not registry.is_dir()):
        raise Ec5PhysicalError("EC5 claim registry must be a non-symlink directory")
    registry.mkdir(parents=True, exist_ok=True)
    if registry.is_symlink() or not registry.is_dir():
        raise Ec5PhysicalError("EC5 claim registry is unsafe")
    record = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.variant_id,
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "u04_review": deepcopy(u04_review),
        "claimed_at": _now(),
        "state": "permanently_consumed_do_not_retry_or_recover",
        "authorization_consumed_permanently": True,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    payload = canonical_json_bytes(record)
    path = registry / f"{context.variant['action_id']}.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise Ec5PhysicalError("this EC5 action already has a permanent host claim") from error
    except OSError as error:
        raise Ec5PhysicalError(f"could not atomically create EC5 host claim: {error}") from error
    return Claim(path=path, record=record, payload=payload)


def _claim_path(context: ReleaseContext, claim_registry: Path | None) -> Path:
    registry = Path(claim_registry) if claim_registry is not None else _claim_registry()
    return registry / f"{context.variant['action_id']}.json"


def _headers(context: ReleaseContext, boot_nonce: str, *, intent: str, arm_nonce: str | None = None) -> dict[str, str]:
    headers = {
        "X-EC5-Build-Tag": context.variant["build_tag"],
        "X-EC5-Test-Id": context.variant["test_id"],
        "X-EC5-Action-Id": context.variant["action_id"],
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _validate_arm_response(value: Mapping[str, Any], context: ReleaseContext, boot_nonce: str) -> str:
    _keys(
        value,
        {
            "accepted", "armed", "test_id", "build_tag", "action_id",
            "device_api_version", "identity_revision", "boot_nonce", "arm_nonce",
            "persistent_phase", "safety_scope", "not_hardware_authorization",
            "migration_ready",
        },
        label="ARM response",
    )
    _expect_identity(value, context, label="ARM response", boot_nonce=boot_nonce)
    if value.get("accepted") is not True or value.get("armed") is not True or value.get("persistent_phase") != 1:
        raise Ec5PhysicalError("ARM response did not commit persistent phase 1")
    nonce = value.get("arm_nonce")
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None or nonce == "0" * 16:
        raise Ec5PhysicalError("ARM response arm_nonce is malformed")
    if (
        value.get("device_api_version") != EXPECTED_DEVICE_API_VERSION
        or value.get("identity_revision") != _expected_identity_revision(context)
        or value.get("migration_ready") is not True
        or value.get("safety_scope")
        != "accidental_post_interlock_not_hardware_authorization"
        or value.get("not_hardware_authorization") is not True
    ):
        raise Ec5PhysicalError("ARM response safety scope mismatch")
    return nonce


def _validate_execute_response(value: Mapping[str, Any], context: ReleaseContext, boot_nonce: str) -> None:
    _keys(
        value,
        {
            "accepted", "job_id", "test_id", "build_tag", "action_id",
            "device_api_version", "identity_revision", "boot_nonce",
            "execute_consumed", "persistent_phase", "no_retry", "no_recovery",
            "migration_ready",
        },
        label="EXECUTE response",
    )
    _expect_identity(value, context, label="EXECUTE response", boot_nonce=boot_nonce)
    if value.get("accepted") is not True or value.get("job_id") != 1 or value.get("execute_consumed") is not True or value.get("persistent_phase") != 2:
        raise Ec5PhysicalError("EXECUTE response did not commit the one job")
    if value.get("no_retry") is not True or value.get("no_recovery") is not True:
        raise Ec5PhysicalError("EXECUTE response retry/recovery contract mismatch")
    if (
        value.get("device_api_version") != EXPECTED_DEVICE_API_VERSION
        or value.get("identity_revision") != _expected_identity_revision(context)
        or value.get("migration_ready") is not True
    ):
        raise Ec5PhysicalError("EXECUTE response corrected-v2 identity mismatch")


def _validate_terminal_report_envelope(
    value: Mapping[str, Any], context: ReleaseContext, boot_nonce: str
) -> tuple[Mapping[str, Any], bool]:
    _keys(value, _FINAL_REPORT_KEYS, label="final report")
    if value.get("schema_version") != EXPECTED_DEVICE_SCHEMA_VERSION or value.get("kind") != "mf1750-ec5-unknown-probe-report" or value.get("valid") is not True:
        raise Ec5PhysicalError("final report schema/kind/valid mismatch")
    _expect_identity(value, context, label="final report", boot_nonce=boot_nonce)
    if value.get("device_api_version") != EXPECTED_DEVICE_API_VERSION:
        raise Ec5PhysicalError("final report EC5 device API mismatch")
    if value.get("identity_revision") != _expected_identity_revision(context):
        raise Ec5PhysicalError("final report identity revision mismatch")
    if value.get("driver_fixture_guard_passed") is not True:
        raise Ec5PhysicalError("final report driver fixture guard did not pass")
    if value.get("job_id") != 1 or value.get("execute_consumed") is not True or value.get("driver_called") is not True or value.get("driver_call_count") != 1 or value.get("persistent_phase") != 2:
        raise Ec5PhysicalError("final report one-call/persistent evidence mismatch")
    if value.get("no_retry") is not True or value.get("no_recovery") is not True:
        raise Ec5PhysicalError("final report retry/recovery evidence mismatch")
    _validate_nvs_evidence(
        value,
        context,
        expected_active_phase=2,
        label="final report",
    )
    if value.get("terminal_state") not in ("completed", "fault_locked"):
        raise Ec5PhysicalError("final report terminal_state mismatch")
    driver = value.get("driver")
    _keys(driver, _FINAL_DRIVER_KEYS, label="final driver")
    if driver.get("driver_evidence_schema_version") != EXPECTED_DRIVER_EVIDENCE_SCHEMA_VERSION:
        raise Ec5PhysicalError("final driver evidence schema mismatch")
    operation_id = _fnv_value(driver.get("operation_id"), label="final driver operation_id")
    if operation_id == 0:
        raise Ec5PhysicalError("final driver operation_id must be non-zero")
    for key in (
        "valid", "running", "sequence_ok", "wait_timeout",
        "busy_assertion_missing", "mapping_applied", "pon_busy_seen",
        "drf_busy_seen", "pof_busy_seen", "post_psr_busy_seen",
        "pre_command_idle_failure",
    ):
        if not isinstance(driver.get(key), bool):
            raise Ec5PhysicalError(f"final driver {key} must be boolean")
    failure_stage = _string(driver.get("failure_stage"), label="final driver failure_stage")
    if failure_stage not in _KNOWN_DRIVER_FAILURE_STAGES:
        raise Ec5PhysicalError("final driver failure_stage is outside the frozen enum")
    _signed_integer(driver.get("failure_code"), label="final driver failure_code")
    for key in (
        "spi_hz", "free_psram_before", "largest_psram_block_before",
        "input_fnv1a", "cs1_dtm_fnv1a", "cs2_dtm_fnv1a", "total_ms",
        "cs1_upload_ms", "cs2_upload_ms", "pon_ms", "drf_ms", "pof_ms",
        "post_psr_ms",
    ):
        _fnv_value(driver.get(key), label=f"final driver {key}")
    if driver.get("spi_hz") == 0:
        raise Ec5PhysicalError("final driver spi_hz must be non-zero")
    for key in ("last_wait_stage", "timeout_stage", "busy_missing_stage", "pre_command_busy_stage"):
        _string(driver.get(key), label=f"final driver {key}")
    for key in ("job_queued_at_ms", "job_started_at_ms", "job_finished_at_ms"):
        _fnv_value(value.get(key), label=f"final report {key}")
    if driver.get("valid") is not True or driver.get("running") is not False:
        raise Ec5PhysicalError("final driver valid/running evidence mismatch")
    result = value.get("result")
    sequence_ok = driver.get("sequence_ok")
    if not isinstance(result, bool) or not isinstance(sequence_ok, bool):
        raise Ec5PhysicalError("final result/driver sequence_ok must be boolean")
    if sequence_ok is not result:
        raise Ec5PhysicalError("driver sequence_ok differs from top-level result")
    expected_terminal = "completed" if result else "fault_locked"
    if value.get("terminal_state") != expected_terminal:
        raise Ec5PhysicalError("final report result/terminal_state evidence mismatch")
    return driver, result


def _validate_safe_final_gpio(driver: Mapping[str, Any]) -> Mapping[str, Any]:
    safe = driver.get("safe_finish")
    _keys(
        safe,
        {"busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms", "final_gpio"},
        label="final driver safe_finish",
    )
    for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"):
        if safe.get(key) not in (0, 1, 0xFF):
            raise Ec5PhysicalError(f"safe_finish {key} is not a GPIO level or sentinel")
    gpio = safe["final_gpio"]
    _keys(gpio, {"busy", "rst", "cs", "cs2"}, label="safe_finish final_gpio")
    for key in ("busy", "rst", "cs", "cs2"):
        if gpio.get(key) not in (0, 1):
            raise Ec5PhysicalError(f"safe_finish final_gpio {key} is not a GPIO level")
    if gpio.get("busy") != 1 or gpio.get("rst") != 0 or gpio.get("cs") != 0 or gpio.get("cs2") != 0:
        raise Ec5PhysicalError("safe_finish final GPIO is not panel-safe")
    return safe


def _validate_terminal_status_counters(value: Mapping[str, Any]) -> None:
    if value.get("state") not in ("completed", "fault_locked"):
        raise Ec5PhysicalError("terminal status state is not terminal")
    if (
        value.get("persistent_phase") != 2
        or value.get("arm_request_count") != 1
        or value.get("execute_request_count") != 1
        or value.get("driver_call_count") != 1
        or value.get("execute_pending") is not False
        or value.get("execute_consumed") is not True
    ):
        raise Ec5PhysicalError("terminal status does not prove one consumed driver call")


def _early_pre_panel_io_fault(driver: Mapping[str, Any], result: bool) -> bool:
    if result or driver.get("failure_stage") not in _EARLY_PRE_PANEL_FAILURE_STAGES:
        return False
    false_fields = (
        "mapping_applied",
        "pon_busy_seen",
        "drf_busy_seen",
        "pof_busy_seen",
        "post_psr_busy_seen",
        "wait_timeout",
        "busy_assertion_missing",
        "pre_command_idle_failure",
    )
    zero_fields = (
        "cs1_upload_ms",
        "cs2_upload_ms",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
    )
    stage_fields = ("last_wait_stage", "timeout_stage", "busy_missing_stage", "pre_command_busy_stage")
    safe = driver.get("safe_finish")
    return (
        all(driver.get(key) is False for key in false_fields)
        and all(driver.get(key) == 0 for key in zero_fields)
        and all(driver.get(key) == "none" for key in stage_fields)
        and isinstance(safe, Mapping)
    )


def _validate_final_report(value: Mapping[str, Any], context: ReleaseContext, boot_nonce: str) -> dict[str, Any]:
    driver, result = _validate_terminal_report_envelope(value, context, boot_nonce)
    if driver.get("failure_stage") in _EARLY_PRE_PANEL_FAILURE_STAGES:
        if not _early_pre_panel_io_fault(driver, result):
            raise Ec5PhysicalError("typed early pre-panel driver failure evidence is inconsistent")
        safe = _validate_safe_final_gpio(driver)
        for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"):
            if safe.get(key) != 1:
                raise Ec5PhysicalError(f"early pre-panel safe_finish {key} is not idle-high")
        return {
            "passed": False,
            "driver": deepcopy(driver),
            "failure_class": "early_pre_panel_io",
            "failure_stage": driver["failure_stage"],
            "visible_refresh_started": False,
        }

    if driver.get("failure_stage") in _PANEL_FAILURE_STAGES:
        if result or driver.get("failure_code") != 0:
            raise Ec5PhysicalError("typed panel-stage driver failure result/code is inconsistent")
        safe = _validate_safe_final_gpio(driver)
        for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"):
            if safe.get(key) != 1:
                raise Ec5PhysicalError(f"panel-stage safe_finish {key} is not idle-high")
        expected_fnv = context.variant["frame_fnv1a"]
        expected_dtm = context.variant["dtm_fnv1a"]
        stage = driver["failure_stage"]
        if driver.get("input_fnv1a") != expected_fnv:
            raise Ec5PhysicalError("panel-stage driver input FNV evidence mismatch")
        if stage == "cascade_prepare":
            if (
                driver.get("cs1_dtm_fnv1a") != expected_dtm
                or driver.get("cs2_dtm_fnv1a") != expected_dtm
                or driver.get("mapping_applied") is not False
                or any(driver.get(key) != 0 for key in ("cs1_upload_ms", "cs2_upload_ms"))
                or any(driver.get(key) is not False for key in ("pon_busy_seen", "drf_busy_seen", "pof_busy_seen"))
            ):
                raise Ec5PhysicalError("cascade_prepare driver failure evidence is inconsistent")
        elif stage == "stream_identity":
            if (
                driver.get("mapping_applied") is not True
                or (
                    driver.get("cs1_dtm_fnv1a") == expected_dtm
                    and driver.get("cs2_dtm_fnv1a") == expected_dtm
                )
                or any(driver.get(key) is not False for key in ("pon_busy_seen", "drf_busy_seen", "pof_busy_seen"))
            ):
                raise Ec5PhysicalError("stream_identity driver failure evidence is inconsistent")
        elif (
            driver.get("mapping_applied") is not True
            or driver.get("cs1_dtm_fnv1a") != expected_dtm
            or driver.get("cs2_dtm_fnv1a") != expected_dtm
        ):
            raise Ec5PhysicalError("refresh_sequence driver failure evidence is inconsistent")
        return {
            "passed": False,
            "driver": deepcopy(driver),
            "failure_class": "panel_stage_failure",
            "failure_stage": stage,
            "visible_refresh_started": None if stage == "refresh_sequence" else False,
        }

    if driver.get("failure_stage") != "none" or driver.get("failure_code") != 0:
        raise Ec5PhysicalError("final driver unrecognized non-early failure evidence")
    if not result:
        raise Ec5PhysicalError("failed final driver report omits its typed failure_stage")
    expected_fnv = context.variant["frame_fnv1a"]
    expected_dtm = context.variant["dtm_fnv1a"]
    if driver.get("input_fnv1a") != expected_fnv or driver.get("cs1_dtm_fnv1a") != expected_dtm or driver.get("cs2_dtm_fnv1a") != expected_dtm:
        raise Ec5PhysicalError("final driver FNV evidence mismatch")
    required_true = ("mapping_applied", "pon_busy_seen", "drf_busy_seen", "pof_busy_seen")
    for key in required_true:
        if driver.get(key) is not True:
            raise Ec5PhysicalError(f"final driver {key} is not true")
    required_false = ("running", "wait_timeout", "busy_assertion_missing", "pre_command_idle_failure")
    for key in required_false:
        if driver.get(key) is not False:
            raise Ec5PhysicalError(f"final driver {key} is not false")
    for key in ("timeout_stage", "busy_missing_stage", "pre_command_busy_stage"):
        if driver.get(key) != "none":
            raise Ec5PhysicalError(f"final driver {key} is not none")
    safe = _validate_safe_final_gpio(driver)
    for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"):
        if safe.get(key) != 1:
            raise Ec5PhysicalError(f"safe_finish {key} does not prove BUSY idle-high")
    return {
        "passed": True,
        "driver": deepcopy(driver),
        "failure_class": None,
        "visible_refresh_started": True,
    }


def _sealed_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result["integrity"] = {"canonical_sha256": None}
    result["integrity"]["canonical_sha256"] = _sha256(canonical_json_bytes(result))
    return result


def _write_immutable(path: Path, result: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(result)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise Ec5PhysicalError("result file already exists; immutable evidence is never overwritten") from error


def run_once(
    context: ReleaseContext,
    base_url: str,
    *,
    authorization: str,
    result_file: Path,
    diagnostic_preflight_file: Path,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    rc2g_binary_file: Path | None = None,
    white_claim_registry: Path | None = None,
    claim_registry: Path | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not context.panel_verified:
        raise Ec5PhysicalError("live panel identity must be verified before run")
    u04_review: Mapping[str, Any] | None = None
    if context.variant_id == "U07":
        if any(
            path is None
            for path in (
                u04_review_file,
                u04_result_file,
                u04_hold_0_file,
                u04_hold_5_file,
                u04_hold_30_file,
                u04_white_recovery_result_file,
                rc2g_binary_file,
            )
        ):
            raise Ec5PhysicalError(
                "U07 requires its exact U04 result, hold0/5/30, after-u04 white "
                "result, frozen RC2G binary, and finalized review before any claim/network"
            )
        u04_review = validate_u04_review(
            context,
            Path(u04_review_file),
            Path(u04_result_file),
            hold_0_file=Path(u04_hold_0_file),
            hold_5_file=Path(u04_hold_5_file),
            hold_30_file=Path(u04_hold_30_file),
            white_recovery_result_file=Path(u04_white_recovery_result_file),
            rc2g_binary_file=Path(rc2g_binary_file),
            white_claim_registry=white_claim_registry,
            claim_registry=claim_registry,
        )
    elif any(
        path is not None
        for path in (
            u04_review_file,
            u04_result_file,
            u04_hold_0_file,
            u04_hold_5_file,
            u04_hold_30_file,
            u04_white_recovery_result_file,
            rc2g_binary_file,
            white_claim_registry,
        )
    ):
        raise Ec5PhysicalError("U04 run does not accept a U04 prerequisite review")
    if authorization != required_authorization(context):
        raise Ec5PhysicalError("exact candidate-bound one-visible authorization is required")
    if isinstance(poll_count, bool) or not isinstance(poll_count, int) or poll_count < 1 or poll_count > 1000:
        raise Ec5PhysicalError("poll_count must be between 1 and 1000")
    if poll_interval_seconds < 0 or poll_interval_seconds > 10:
        raise Ec5PhysicalError("poll interval must be between 0 and 10 seconds")
    # Give a known duplicate a zero-network failure.  The later O_EXCL claim is
    # still the authoritative race-free boundary.
    if _claim_path(context, claim_registry).exists():
        raise Ec5PhysicalError("this EC5 action already has a permanent host claim")

    # The durable J2-off gate is validated locally first. The following four
    # requests are GET-only and must prove the same ESP32 boot with J2 on. A
    # stale/tampered diagnostic or reboot therefore cannot consume a claim or
    # reach either mutation route.
    diagnostic_preflight = validate_diagnostic_preflight(
        context, Path(diagnostic_preflight_file)
    )
    snapshot = preflight(
        context,
        base_url,
        expected_boot_nonce=diagnostic_preflight["boot_nonce"],
        timeout_seconds=timeout_seconds,
        _urlopen=_urlopen,
    )
    boot_nonce = snapshot["boot_nonce"]
    attempt_id = str(uuid.uuid4())
    claim = _atomic_claim(
        context,
        attempt_id,
        claim_registry=claim_registry,
        u04_review=u04_review,
    )
    started_at = _now()
    post_requests = 0
    observations: list[dict[str, Any]] = []
    outcome = "unknown_do_not_retry_or_recover"
    error_text: str | None = None
    final_report: Mapping[str, Any] | None = None
    final_status: Mapping[str, Any] | None = None
    observed_terminal_report: Mapping[str, Any] | None = None
    observed_terminal_report_payload_bytes: int | None = None
    observed_terminal_report_payload_sha256: str | None = None

    mutation_error: Exception | None = None
    try:
        post_requests += 1
        arm = _http_json(
            _base_url(base_url),
            _ENDPOINTS["arm"],
            method="POST",
            headers=_headers(context, boot_nonce, intent=ARM_INTENT),
            timeout_seconds=timeout_seconds,
            _urlopen=_urlopen,
        )
        arm_nonce = _validate_arm_response(arm, context, boot_nonce)
        armed_status = _http_json(_base_url(base_url), _ENDPOINTS["status"], method="GET", timeout_seconds=timeout_seconds, _urlopen=_urlopen)
        _validate_status(armed_status, context, boot_nonce=boot_nonce, allowed_states={"armed"})
        _require_safe_idle_gpio(armed_status, label="armed status")
        if armed_status["persistent_phase"] != 1 or armed_status["arm_request_count"] != 1 or armed_status["execute_request_count"] != 0 or armed_status["driver_call_count"] != 0:
            raise Ec5PhysicalError("armed status counters or persistent phase mismatch")

        post_requests += 1
        executed = _http_json(
            _base_url(base_url),
            _ENDPOINTS["execute"],
            method="POST",
            headers=_headers(context, boot_nonce, intent=EXECUTE_INTENT, arm_nonce=arm_nonce),
            timeout_seconds=timeout_seconds,
            _urlopen=_urlopen,
        )
        _validate_execute_response(executed, context, boot_nonce)

    except Exception as error:  # claim already exists: never retry or recover
        mutation_error = error

    # Whether the mutation replies were clear, malformed, or timed out, the
    # remainder is GET-only.  This can adjudicate an EXECUTE whose 202 reply
    # was lost, but can never resume an ARM whose nonce reply was lost.
    for index in range(poll_count):
        try:
            status = _http_json(_base_url(base_url), _ENDPOINTS["status"], method="GET", timeout_seconds=timeout_seconds, _urlopen=_urlopen)
        except Ec5PhysicalReadError as read_error:
            observations.append({"poll": index + 1, "endpoint": "status", "read_error": str(read_error)})
            if index + 1 < poll_count:
                _sleep(poll_interval_seconds)
            continue
        except Ec5PhysicalError as validation_error:
            observations.append({"poll": index + 1, "endpoint": "status", "validation_error": str(validation_error)})
            if index + 1 < poll_count:
                _sleep(poll_interval_seconds)
            continue
        try:
            _validate_status(
                status,
                context,
                boot_nonce=boot_nonce,
                allowed_states={"ready", "armed", "queued", "running", "completed", "fault_locked"},
            )
        except Ec5PhysicalError as validation_error:
            observations.append({"poll": index + 1, "endpoint": "status", "validation_error": str(validation_error)})
            if index + 1 < poll_count:
                _sleep(poll_interval_seconds)
            continue
        final_status = deepcopy(status)
        try:
            report, report_payload = _http_json_with_payload(
                _base_url(base_url),
                _ENDPOINTS["report"],
                method="GET",
                timeout_seconds=timeout_seconds,
                _urlopen=_urlopen,
            )
        except Ec5PhysicalReadError as read_error:
            observations.append({"poll": index + 1, "endpoint": "report", "read_error": str(read_error)})
            if index + 1 < poll_count:
                _sleep(poll_interval_seconds)
            continue
        except Ec5PhysicalError as validation_error:
            observations.append({"poll": index + 1, "endpoint": "report", "validation_error": str(validation_error)})
            if index + 1 < poll_count:
                _sleep(poll_interval_seconds)
            continue
        observation = {
            "poll": index + 1,
            "state": status["state"],
            "persistent_phase": status["persistent_phase"],
            "driver_call_count": status["driver_call_count"],
            "report_valid": report.get("valid"),
        }
        observations.append(observation)
        if status["state"] in ("completed", "fault_locked") and report.get("valid") is True:
            # Preserve the first stable terminal evidence before applying any
            # local semantic checks. A rejected report must remain available
            # for offline diagnosis even though it cannot prove a pass.
            observed_terminal_report = deepcopy(report)
            observed_terminal_report_payload_bytes = len(report_payload)
            observed_terminal_report_payload_sha256 = _sha256(report_payload)
            try:
                verdict = _validate_final_report(report, context, boot_nonce)
                _validate_terminal_status_counters(status)
            except Ec5PhysicalError as validation_error:
                observation["validation_error"] = str(validation_error)
                error_text = f"terminal report validation failed: {validation_error}"
                break
            final_report = deepcopy(report)
            outcome = "complete_pass" if verdict["passed"] else "complete_driver_failure_no_retry"
            observation["terminal_verdict"] = outcome
            if not verdict["passed"]:
                stage_detail = (
                    f"; failure_stage={verdict['failure_stage']}"
                    if verdict.get("failure_stage") is not None
                    else ""
                )
                error_text = (
                    f"terminal driver failure: {verdict['failure_class']}{stage_detail}; "
                    f"visible_refresh_started={str(verdict['visible_refresh_started']).lower()}; no retry"
                )
            mutation_error = None
            break
        if index + 1 < poll_count:
            _sleep(poll_interval_seconds)
    if final_report is None and error_text is None:
        error_text = str(mutation_error) if mutation_error is not None else "read-only polling ended without a validated terminal report"

    result = _sealed_result(
        {
            "schema_version": RESULT_SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "attempt_id": attempt_id,
            "candidate_id": context.variant_id,
            "candidate_code": context.variant["candidate_code"],
            "build_tag": context.variant["build_tag"],
            "test_id": context.variant["test_id"],
            "action_id": context.variant["action_id"],
            "boot_nonce": boot_nonce,
            "release_canonical_sha256": context.release_canonical_sha256,
            "firmware_sha256": context.binary_sha256,
            "panel": dict(context.panel),
            "diagnostic_preflight": diagnostic_preflight,
            "u04_review": deepcopy(u04_review),
            "authorization_confirmation_sha256": _sha256(authorization.encode("utf-8")),
            "claim": claim.reference(),
            "started_at": started_at,
            "finished_at": _now(),
            "outcome": outcome,
            "error": error_text,
            "post_requests": post_requests,
            "maximum_arm_posts": 1,
            "maximum_execute_posts": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
            "observations": observations,
            "final_status": deepcopy(final_status),
            "final_report": deepcopy(final_report),
            "observed_terminal_report": deepcopy(observed_terminal_report),
            "observed_terminal_report_payload_bytes": observed_terminal_report_payload_bytes,
            "observed_terminal_report_payload_sha256": observed_terminal_report_payload_sha256,
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
    )
    _write_immutable(Path(result_file), result)
    return result


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path | None = None,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    rc2g_binary_file: Path | None = None,
    white_claim_registry: Path | None = None,
) -> dict[str, Any]:
    payload = _read_regular(Path(result_file), label="EC5 physical result", maximum=MAX_JSON_BYTES)
    result = _decode_json(payload, label="EC5 physical result")
    base_result_keys = {
        "schema_version", "kind", "attempt_id", "candidate_id",
        "candidate_code", "build_tag", "test_id", "action_id",
        "boot_nonce", "release_canonical_sha256", "firmware_sha256",
        "panel", "u04_review", "authorization_confirmation_sha256",
        "claim", "started_at", "finished_at", "outcome", "error",
        "post_requests", "maximum_arm_posts", "maximum_execute_posts",
        "automatic_retry", "automatic_recovery", "observations",
        "final_status", "final_report", "state", "integrity",
    }
    schema_version = result.get("schema_version")
    if schema_version == 1:
        expected_result_keys = base_result_keys
    elif schema_version == 2:
        expected_result_keys = base_result_keys | {
            "observed_terminal_report",
            "observed_terminal_report_payload_bytes",
            "observed_terminal_report_payload_sha256",
        }
    elif schema_version == RESULT_SCHEMA_VERSION:
        expected_result_keys = base_result_keys | {
            "diagnostic_preflight",
            "observed_terminal_report",
            "observed_terminal_report_payload_bytes",
            "observed_terminal_report_payload_sha256",
        }
    else:
        raise Ec5PhysicalError("unsupported EC5 result schema/kind")
    _keys(
        result,
        expected_result_keys,
        label="EC5 physical result",
    )
    if result.get("kind") != RESULT_KIND:
        raise Ec5PhysicalError("unsupported EC5 result schema/kind")
    integrity = result.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {"canonical_sha256"}:
        raise Ec5PhysicalError("EC5 result integrity is malformed")
    expected = _hex64(integrity["canonical_sha256"], label="result integrity")
    unsigned = deepcopy(result)
    unsigned["integrity"]["canonical_sha256"] = None
    if _sha256(canonical_json_bytes(unsigned)) != expected:
        raise Ec5PhysicalError("EC5 result integrity mismatch")
    links = {
        "candidate_id": context.variant_id,
        "candidate_code": context.variant["candidate_code"],
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "u04_review": result.get("u04_review"),
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_confirmation_sha256": _sha256(
            required_authorization(context).encode("utf-8")
        ),
    }
    for key, expected_value in links.items():
        if result.get(key) != expected_value:
            raise Ec5PhysicalError(f"EC5 result {key} binding mismatch")
    if schema_version == RESULT_SCHEMA_VERSION:
        diagnostic = _keys(
            result.get("diagnostic_preflight"),
            {
                "file", "bytes", "file_sha256", "integrity_sha256",
                "candidate_id", "action_id", "boot_nonce", "created_at", "state",
            },
            label="EC5 result diagnostic preflight reference",
        )
        diagnostic_path = Path(
            _string(diagnostic["file"], label="diagnostic preflight file")
        )
        validated_diagnostic = validate_diagnostic_preflight(
            context, diagnostic_path
        )
        if diagnostic != validated_diagnostic:
            raise Ec5PhysicalError("EC5 result diagnostic preflight binding mismatch")
        if diagnostic["boot_nonce"] != result.get("boot_nonce"):
            raise Ec5PhysicalError("EC5 result boot differs from diagnostic preflight")
    if result.get("post_requests") not in (1, 2):
        raise Ec5PhysicalError("EC5 result POST count is impossible")
    claim = result.get("claim")
    if not isinstance(claim, Mapping) or claim.get("action_id") != context.variant["action_id"] or claim.get("state") != "permanently_consumed_do_not_retry_or_recover":
        raise Ec5PhysicalError("EC5 result permanent claim reference is malformed")
    claim_path = _claim_path(context, claim_registry)
    if claim.get("filename") != claim_path.name:
        raise Ec5PhysicalError("EC5 result claim filename mismatch")
    claim_payload = _read_regular(claim_path, label="EC5 permanent host claim", maximum=MAX_JSON_BYTES)
    if claim.get("file_sha256") != _sha256(claim_payload):
        raise Ec5PhysicalError("EC5 permanent host claim digest mismatch")
    claim_record = _decode_json(claim_payload, label="EC5 permanent host claim")
    _keys(
        claim_record,
        {
            "schema_version", "kind", "registry_id", "attempt_id",
            "release_canonical_sha256", "candidate_id", "build_tag",
            "test_id", "action_id", "firmware_sha256", "panel",
            "u04_review", "claimed_at", "state",
            "authorization_consumed_permanently", "maximum_arm_posts",
            "maximum_execute_posts", "automatic_retry", "automatic_recovery",
        },
        label="EC5 permanent host claim",
    )
    claim_links = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": result.get("attempt_id"),
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.variant_id,
        "build_tag": context.variant["build_tag"],
        "test_id": context.variant["test_id"],
        "action_id": context.variant["action_id"],
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "u04_review": result.get("u04_review"),
        "state": "permanently_consumed_do_not_retry_or_recover",
        "authorization_consumed_permanently": True,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    for key, expected_value in claim_links.items():
        if claim_record.get(key) != expected_value:
            raise Ec5PhysicalError(f"EC5 permanent host claim {key} binding mismatch")
    _timestamp(claim_record.get("claimed_at"), label="claim claimed_at")
    if claim.get("attempt_id") != result.get("attempt_id"):
        raise Ec5PhysicalError("EC5 result and claim attempt IDs differ")
    _timestamp(result.get("started_at"), label="result started_at")
    _timestamp(result.get("finished_at"), label="result finished_at")
    if result.get("outcome") not in {
        "complete_pass",
        "complete_driver_failure_no_retry",
        "unknown_do_not_retry_or_recover",
    }:
        raise Ec5PhysicalError("EC5 result outcome is invalid")
    final_status = result.get("final_status")
    final_report = result.get("final_report")
    if final_status is not None:
        if not isinstance(final_status, Mapping):
            raise Ec5PhysicalError("stored EC5 status evidence is malformed")
        _validate_status(
            final_status,
            context,
            boot_nonce=result.get("boot_nonce"),
            allowed_states={"ready", "armed", "queued", "running", "completed", "fault_locked"},
        )
        if final_status.get("state") in ("completed", "fault_locked"):
            _validate_terminal_status_counters(final_status)
    if final_report is not None:
        if not isinstance(final_report, Mapping):
            raise Ec5PhysicalError("stored EC5 report evidence is malformed")
        _validate_terminal_report_envelope(final_report, context, result.get("boot_nonce"))

    observed_terminal_report: Mapping[str, Any] | None
    if schema_version in (2, RESULT_SCHEMA_VERSION):
        observed_value = result.get("observed_terminal_report")
        observed_bytes = result.get("observed_terminal_report_payload_bytes")
        observed_sha256 = result.get("observed_terminal_report_payload_sha256")
        if observed_value is None:
            if observed_bytes is not None or observed_sha256 is not None:
                raise Ec5PhysicalError("absent observed terminal report has payload metadata")
            observed_terminal_report = None
        else:
            if not isinstance(observed_value, Mapping):
                raise Ec5PhysicalError("observed terminal report is malformed")
            _integer(observed_bytes, label="observed terminal report payload bytes", minimum=1)
            _hex64(observed_sha256, label="observed terminal report payload SHA256")
            _validate_terminal_report_envelope(observed_value, context, result.get("boot_nonce"))
            observed_terminal_report = observed_value
    else:
        observed_terminal_report = final_report if isinstance(final_report, Mapping) else None

    if result.get("outcome").startswith("complete_"):
        if not isinstance(final_status, Mapping) or not isinstance(final_report, Mapping):
            raise Ec5PhysicalError("complete EC5 result lacks terminal evidence")
        if schema_version in (2, RESULT_SCHEMA_VERSION) and observed_terminal_report != final_report:
            raise Ec5PhysicalError("complete EC5 result differs from its observed terminal report")
        verdict = _validate_final_report(final_report, context, result.get("boot_nonce"))
        if (result["outcome"] == "complete_pass") is not verdict["passed"]:
            raise Ec5PhysicalError("EC5 result outcome disagrees with terminal evidence")
    elif observed_terminal_report is not None:
        try:
            _validate_final_report(observed_terminal_report, context, result.get("boot_nonce"))
        except Ec5PhysicalError:
            pass
        else:
            raise Ec5PhysicalError("unknown EC5 outcome disagrees with validated terminal evidence")
    if context.variant_id == "U07":
        if any(
            path is None
            for path in (
                u04_review_file,
                u04_result_file,
                u04_hold_0_file,
                u04_hold_5_file,
                u04_hold_30_file,
                u04_white_recovery_result_file,
                rc2g_binary_file,
            )
        ):
            raise Ec5PhysicalError(
                "validating U07 requires its exact U04 result, hold0/5/30, "
                "after-u04 white result, frozen RC2G binary, and finalized review"
            )
        expected_review = validate_u04_review(
            context,
            Path(u04_review_file),
            Path(u04_result_file),
            hold_0_file=Path(u04_hold_0_file),
            hold_5_file=Path(u04_hold_5_file),
            hold_30_file=Path(u04_hold_30_file),
            white_recovery_result_file=Path(u04_white_recovery_result_file),
            rc2g_binary_file=Path(rc2g_binary_file),
            white_claim_registry=white_claim_registry,
            claim_registry=claim_registry,
        )
        if result.get("u04_review") != expected_review:
            raise Ec5PhysicalError("U07 result U04 review binding mismatch")
    else:
        if result.get("u04_review") is not None:
            raise Ec5PhysicalError("U04 result unexpectedly contains a U04 prerequisite review")
        if any(
            path is not None
            for path in (
                u04_review_file,
                u04_result_file,
                u04_hold_0_file,
                u04_hold_5_file,
                u04_hold_30_file,
                u04_white_recovery_result_file,
                rc2g_binary_file,
                white_claim_registry,
            )
        ):
            raise Ec5PhysicalError("U04 result validation rejects U07-only prerequisites")
    return dict(result)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("describe", "diagnose-j2-off", "preflight", "run", "validate"):
        item = sub.add_parser(name)
        item.add_argument("--release", type=Path, required=True)
        item.add_argument("--candidate", choices=sorted(_CANDIDATES), required=True)
        item.add_argument("--source-root", type=Path, default=REPO_ROOT)
        item.add_argument("--panel", type=Path)
        if name in ("diagnose-j2-off", "preflight", "run"):
            item.add_argument("--base-url", required=True)
            item.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
        if name == "diagnose-j2-off":
            item.add_argument("--confirm-j2-off", action="store_true")
            item.add_argument("--evidence", type=Path, required=True)
        if name == "run":
            item.add_argument("--authorization", required=True)
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--diagnostic-preflight", type=Path, required=True)
            item.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
            item.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
        if name == "validate":
            item.add_argument("--result", type=Path, required=True)
        if name in ("run", "validate"):
            item.add_argument("--u04-review", type=Path)
            item.add_argument("--u04-result", type=Path)
            item.add_argument("--u04-hold-0", type=Path)
            item.add_argument("--u04-hold-5", type=Path)
            item.add_argument("--u04-hold-30", type=Path)
            item.add_argument("--u04-white-recovery-result", type=Path)
            item.add_argument("--rc2g-binary", type=Path)
            item.add_argument("--white-claim-registry", type=Path)
            item.add_argument("--claim-registry", type=Path)
    observe = sub.add_parser(
        "observe-hold",
        help="record one immutable host-now 0/5/30-minute candidate observation",
    )
    observe.add_argument("--release", type=Path, required=True)
    observe.add_argument("--candidate", choices=sorted(_CANDIDATES), required=True)
    observe.add_argument("--source-root", type=Path, default=REPO_ROOT)
    observe.add_argument("--panel", type=Path, required=True)
    observe.add_argument("--candidate-result", type=Path, required=True)
    observe.add_argument("--output", type=Path, required=True)
    observe.add_argument("--hold-minutes", type=int, choices=(0, 5, 30), required=True)
    observe.add_argument("--temperature-c", type=float, required=True)
    observe.add_argument("--prior-hold-0", type=Path)
    observe.add_argument("--prior-hold-5", type=Path)
    observe.add_argument("--claim-registry", type=Path)
    observe.add_argument("--u04-review", type=Path)
    observe.add_argument("--u04-result", type=Path)
    observe.add_argument("--u04-hold-0", type=Path)
    observe.add_argument("--u04-hold-5", type=Path)
    observe.add_argument("--u04-hold-30", type=Path)
    observe.add_argument("--u04-white-recovery-result", type=Path)
    observe.add_argument("--rc2g-binary", type=Path)
    observe.add_argument("--white-claim-registry", type=Path)
    observe.add_argument("--confirm-visual-stable", action="store_true")
    observe.add_argument("--confirm-electrical-normal", action="store_true")
    observe.add_argument("--confirm-esp32-not-restarted", action="store_true")
    observe.add_argument("--confirm-no-uncommanded-refresh", action="store_true")
    finalize = sub.add_parser(
        "finalize-u04-review",
        help="exclusively create the human-reviewed U04 gate for U07",
    )
    finalize.add_argument("--release", type=Path, required=True)
    finalize.add_argument("--source-root", type=Path, default=REPO_ROOT)
    finalize.add_argument("--panel", type=Path, required=True)
    finalize.add_argument("--u04-result", type=Path, required=True)
    finalize.add_argument("--hold-0", type=Path, required=True)
    finalize.add_argument("--hold-5", type=Path, required=True)
    finalize.add_argument("--hold-30", type=Path, required=True)
    finalize.add_argument("--white-recovery-result", type=Path, required=True)
    finalize.add_argument("--rc2g-binary", type=Path, required=True)
    finalize.add_argument("--claim-registry", type=Path)
    finalize.add_argument("--white-claim-registry", type=Path)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.add_argument("--reviewer", required=True)
    finalize.add_argument("--confirm-left-right-match", action="store_true")
    finalize.add_argument("--confirm-preview-match", action="store_true")
    finalize.add_argument("--confirm-white-recovery-visual-pass", action="store_true")
    finalize.add_argument("--confirm-electrical-normal", action="store_true")
    finalize.add_argument("--confirm-esp32-not-restarted", action="store_true")
    finalize.add_argument("--confirm-no-uncommanded-refresh", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "observe-hold":
        context = load_release(
            args.release,
            args.candidate,
            source_root=args.source_root,
            panel_file=args.panel,
        )
        result_validation_kwargs = {}
        if args.candidate == "U07":
            result_validation_kwargs = {
                "u04_review_file": args.u04_review,
                "u04_result_file": args.u04_result,
                "u04_hold_0_file": args.u04_hold_0,
                "u04_hold_5_file": args.u04_hold_5,
                "u04_hold_30_file": args.u04_hold_30,
                "u04_white_recovery_result_file": args.u04_white_recovery_result,
                "rc2g_binary_file": args.rc2g_binary,
                "white_claim_registry": args.white_claim_registry,
            }
        prior_holds = {}
        if args.prior_hold_0 is not None:
            prior_holds[0] = args.prior_hold_0
        if args.prior_hold_5 is not None:
            prior_holds[5] = args.prior_hold_5
        output = record_hold_observation(
            context,
            candidate_result_file=args.candidate_result,
            output_file=args.output,
            hold_minutes=args.hold_minutes,
            temperature_c=args.temperature_c,
            confirmations={
                "visual_stable": args.confirm_visual_stable,
                "electrical_normal": args.confirm_electrical_normal,
                "esp32_not_restarted": args.confirm_esp32_not_restarted,
                "no_uncommanded_refresh": args.confirm_no_uncommanded_refresh,
            },
            prior_hold_files=prior_holds,
            claim_registry=args.claim_registry,
            result_validation_kwargs=result_validation_kwargs,
        )
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    if args.command == "finalize-u04-review":
        context = load_release(
            args.release,
            "U04",
            source_root=args.source_root,
            panel_file=args.panel,
        )
        output = finalize_u04_review(
            context,
            u04_result_file=args.u04_result,
            hold_0_file=args.hold_0,
            hold_5_file=args.hold_5,
            hold_30_file=args.hold_30,
            white_recovery_result_file=args.white_recovery_result,
            rc2g_binary_file=args.rc2g_binary,
            output_file=args.output,
            reviewer=args.reviewer,
            claim_registry=args.claim_registry,
            white_claim_registry=args.white_claim_registry,
            confirmations={
                "left_right_match": args.confirm_left_right_match,
                "preview_match": args.confirm_preview_match,
                "white_recovery_visual_pass": args.confirm_white_recovery_visual_pass,
                "electrical_normal": args.confirm_electrical_normal,
                "esp32_not_restarted": args.confirm_esp32_not_restarted,
                "no_uncommanded_refresh": args.confirm_no_uncommanded_refresh,
            },
        )
        sys.stdout.buffer.write(canonical_json_bytes(output))
        return 0
    if args.command in ("diagnose-j2-off", "preflight", "run") and args.panel is None:
        raise Ec5PhysicalError(
            "--panel is required for live diagnostic/preflight/run panel binding"
        )
    context = load_release(args.release, args.candidate, source_root=args.source_root, panel_file=args.panel)
    if args.command == "describe":
        output = describe(context)
    elif args.command == "diagnose-j2-off":
        output = diagnose_j2_off(
            context,
            args.base_url,
            confirm_j2_off=args.confirm_j2_off,
            evidence_file=args.evidence,
            timeout_seconds=args.timeout,
        )
    elif args.command == "preflight":
        output = preflight(context, args.base_url, timeout_seconds=args.timeout)
    elif args.command == "run":
        output = run_once(
            context,
            args.base_url,
            authorization=args.authorization,
            result_file=args.result,
            diagnostic_preflight_file=args.diagnostic_preflight,
            u04_review_file=args.u04_review,
            u04_result_file=args.u04_result,
            u04_hold_0_file=args.u04_hold_0,
            u04_hold_5_file=args.u04_hold_5,
            u04_hold_30_file=args.u04_hold_30,
            u04_white_recovery_result_file=args.u04_white_recovery_result,
            rc2g_binary_file=args.rc2g_binary,
            white_claim_registry=args.white_claim_registry,
            claim_registry=args.claim_registry,
            timeout_seconds=args.timeout,
            poll_count=args.poll_count,
            poll_interval_seconds=args.poll_interval,
        )
    else:
        output = validate_result(
            context,
            args.result,
            u04_review_file=args.u04_review,
            u04_result_file=args.u04_result,
            u04_hold_0_file=args.u04_hold_0,
            u04_hold_5_file=args.u04_hold_5,
            u04_hold_30_file=args.u04_hold_30,
            u04_white_recovery_result_file=args.u04_white_recovery_result,
            rc2g_binary_file=args.rc2g_binary,
            white_claim_registry=args.white_claim_registry,
            claim_registry=args.claim_registry,
        )
    sys.stdout.buffer.write(canonical_json_bytes(output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Ec5PhysicalError as error:
        print(f"EC5 physical once rejected: {error}", file=sys.stderr)
        raise SystemExit(2)
