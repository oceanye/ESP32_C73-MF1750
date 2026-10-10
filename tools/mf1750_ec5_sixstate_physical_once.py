#!/usr/bin/env python3
"""Fail-closed, one-action-at-a-time EC5 six-state physical executor.

The runner consumes a frozen release that binds both candidate binaries, the
safety-relevant source snapshot, the physical panel, both offline asset
bundles, and all nine compiled actions.  It never uploads firmware.  Each
``run`` invocation can execute only the device's current ordinal, creates an
immutable host claim before the first POST, sends ARM/EXECUTE at most once,
and uses GET-only adjudication after any uncertain mutation.

The nine fixed actions are ``primer -> target -> white`` repeated three times.
The host deliberately adds gates that the embedded monotonic state cannot
provide: a 150 second wall-clock cooldown, a finalized target observation
(0/5/30 minute holds and all twelve ROIs) before each white action, and a
finalized white-recovery observation before the next primer.  U07 is blocked
unless the real Stage-A U04/U07 results, claims, 0/5/30 holds, frozen RC2G
binary, and both post-candidate white recoveries all replay successfully.
"""

from __future__ import annotations

import argparse
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
import urllib.parse
import urllib.request
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_sixstate_nodither as asset_tool  # noqa: E402


SCHEMA_VERSION = 1
RELEASE_KIND = "mf1750-ec5-sixstate-release-bundle"
RESULT_KIND = "mf1750-ec5-sixstate-physical-once-result"
CLAIM_KIND = "mf1750-ec5-sixstate-permanent-host-claim"
OBSERVATION_KIND = "mf1750-ec5-sixstate-finalized-observation"
OBSERVATION_POINT_KIND = "mf1750-ec5-sixstate-observation-point"
CLAIM_REGISTRY_ID = "workspace-mf1750-ec5-sixstate-claim-registry-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_sixstate_claims"
)
HASH_SCOPE = (
    "entire object excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_BINARY_BYTES = 32 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_COUNT = 40
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
COOLDOWN_SECONDS = 150
MAX_TEMPERATURE_C = 45.0
MIN_TEMPERATURE_C = 10.0
ARM_INTENT = "ARM_ONE_FIXED_SIXSTATE_REFRESH_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_SIXSTATE_REFRESH_NOT_HARDWARE_AUTHORIZATION"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
EXPECTED_DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3"
LAYOUT_ID = "EC5_SIXSTATE_MIRROR24_NODITHER_V1"

SOURCE_PATHS = (
    "platformio.ini",
    "src/ec5_sixstate_main.cpp",
    "src/epd_config.h",
    "src/epd_driver.cpp",
    "src/epd_driver.h",
)
PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
ROLES = ("primer", "target", "white")
INITIAL_CODES = (1, 0, 3, 2, 5, 6)
ROI_IDS = tuple(
    f"{name}-{controller}"
    for name in ("WHITE", "BLACK", "RED", "YELLOW", "BLUE", "GREEN")
    for controller in ("CS1", "CS2")
)
_HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
_HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
_NONCE_RE = re.compile(r"[0-9a-f]{16}\Z")
_HEX32_TEXT_RE = re.compile(r"0x[0-9a-f]{8}\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)

_ENDPOINTS = {
    "version": "/api/ec5/sixstate/version",
    "manifest": "/api/ec5/sixstate/manifest",
    "status": "/api/ec5/sixstate/status",
    "report": "/api/ec5/sixstate/report",
    "arm": "/api/ec5/sixstate/arm",
    "execute": "/api/ec5/sixstate/execute",
}

DEVICE_CONTRACT = {
    "read_routes": [_ENDPOINTS[name] for name in ("version", "manifest", "status", "report")],
    "arm_route": _ENDPOINTS["arm"],
    "execute_route": _ENDPOINTS["execute"],
    "arm_intent": ARM_INTENT,
    "execute_intent": EXECUTE_INTENT,
    "persistent_progress": True,
    "fixed_action_count": 9,
    "cooldown_seconds": COOLDOWN_SECONDS,
    "maximum_arm_posts_per_action": 1,
    "maximum_execute_posts_per_action": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "raw_frame_ingress": False,
    "startup_refresh": False,
    "lut_modification": False,
}

_COMMON_IDENTITIES = {
    "primer": {
        "frame_sha256": "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
        "frame_fnv1a": "0xe4f04785",
        "dtm_sha256": "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
        "dtm_fnv1a": "0x58214425",
    },
    "white": {
        "frame_sha256": "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "frame_fnv1a": "0x13340dc5",
        "dtm_sha256": "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "dtm_fnv1a": "0xb7a855c5",
    },
}

FROZEN_VARIANTS: dict[str, dict[str, Any]] = {
    "U04": {
        "candidate_id": "U04",
        "candidate_code": 4,
        "environment": "esp32-s3-devkitc-1-ec5-sixstate-u04",
        "build_tag": "MF1750_EC5_SIXSTATE_U04_MIRROR24_NODITHER_V1_2026-08-09",
        "test_id": "EC5-SIXSTATE-U04-M24-NODITHER-V1",
        "layout_id": LAYOUT_ID,
        "firmware_file": "firmware-sixstate-u04.bin",
        "asset_manifest_payload_sha256": "8928e066526cab5a62a38ddeb5c0d322d2042335ef69eb4c0b526741942dea1f",
        "target": {
            "frame_sha256": "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6",
            "frame_fnv1a": "0x263bd845",
            "dtm_sha256": "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
            "dtm_fnv1a": "0xef6ed905",
        },
    },
    "U07": {
        "candidate_id": "U07",
        "candidate_code": 7,
        "environment": "esp32-s3-devkitc-1-ec5-sixstate-u07",
        "build_tag": "MF1750_EC5_SIXSTATE_U07_MIRROR24_NODITHER_V1_2026-08-09",
        "test_id": "EC5-SIXSTATE-U07-M24-NODITHER-V1",
        "layout_id": LAYOUT_ID,
        "firmware_file": "firmware-sixstate-u07.bin",
        "asset_manifest_payload_sha256": "f9cbae963413a62528661e508bbc4a720dff32b3d9cbd718738b437d517fee8d",
        "target": {
            "frame_sha256": "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21",
            "frame_fnv1a": "0xf93bd8c5",
            "dtm_sha256": "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
            "dtm_fnv1a": "0xe4d43b45",
        },
    },
}


class SixStatePhysicalError(RuntimeError):
    """Rejected without making a device mutation."""


class SixStatePhysicalUnknown(SixStatePhysicalError):
    """A host claim exists; another mutation attempt is permanently forbidden."""


@dataclass(frozen=True)
class ReleaseContext:
    path: Path
    root: Mapping[str, Any]
    candidate_id: str
    variant: Mapping[str, Any]
    actions: tuple[Mapping[str, Any], ...]
    binary_path: Path
    binary_sha256: str
    asset_manifest_path: Path
    asset_file_sha256: str
    release_canonical_sha256: str
    panel: Mapping[str, str]
    panel_verified: bool
    panel_file: Path | None
    source_root: Path


@dataclass(frozen=True)
class Preflight:
    version: Mapping[str, Any]
    manifest: Mapping[str, Any]
    status: Mapping[str, Any]
    report: Mapping[str, Any]
    boot_nonce: str

    def digest(self) -> str:
        return sha256(canonical_json_bytes({
            "version": self.version,
            "manifest": self.manifest,
            "status": self.status,
            "report": self.report,
        }))


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SixStatePhysicalError(f"value is not canonical JSON data: {error}") from error


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SixStatePhysicalError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise SixStatePhysicalError(f"{label} exceeds the JSON size limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                SixStatePhysicalError(f"{label} contains forbidden number {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SixStatePhysicalError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise SixStatePhysicalError(f"{label} must be a JSON object")
    return value


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise SixStatePhysicalError(f"{label} must be a non-symlink regular file")
        if before.st_size > maximum:
            raise SixStatePhysicalError(f"{label} exceeds its size limit")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise SixStatePhysicalError(f"cannot read {label}: {error}") from error
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != after.st_size:
        raise SixStatePhysicalError(f"{label} changed while being read")
    return payload


def _read_json(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    payload = _read_regular(path, label=label, maximum=MAX_JSON_BYTES)
    return _decode_json(payload, label=label), payload


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise SixStatePhysicalError(
            f"{label} fields differ: expected {sorted(expected)!r}, got {actual!r}"
        )
    return value


def _string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SixStatePhysicalError(f"{label} must be a non-empty trimmed string")
    if len(value) > 512 or any(ord(character) < 0x20 for character in value):
        raise SixStatePhysicalError(f"{label} is malformed")
    return value


def _integer(value: Any, *, label: str, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SixStatePhysicalError(f"{label} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise SixStatePhysicalError(f"{label} must be <= {maximum}")
    return value


def _number(value: Any, *, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SixStatePhysicalError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise SixStatePhysicalError(f"{label} must be between {minimum} and {maximum}")
    return result


def _hex64(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise SixStatePhysicalError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def _hex32_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HEX32_TEXT_RE.fullmatch(value) is None:
        raise SixStatePhysicalError(f"{label} must be 0x plus 8 lowercase hexadecimal digits")
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise SixStatePhysicalError(f"{label} must be RFC3339 with an explicit timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SixStatePhysicalError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SixStatePhysicalError(f"{label} lacks a timezone")
    return parsed


def _boolean(value: Any, expected: bool, *, label: str) -> None:
    if value is not expected:
        raise SixStatePhysicalError(f"{label} must be {str(expected).lower()}")


def _safe_relative(value: Any, *, label: str) -> Path:
    text = _string(value, label=label)
    relative = Path(text)
    if relative.is_absolute() or not relative.parts or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise SixStatePhysicalError(f"{label} must be a normalized relative path")
    return relative


def _inside(root: Path, relative: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise SixStatePhysicalError(f"{label} escapes its root") from error
    return resolved


def _validate_panel(value: Any, *, label: str) -> dict[str, str]:
    panel = _keys(value, set(PANEL_KEYS), label=label)
    return {key: _string(panel[key], label=f"{label}.{key}") for key in sorted(PANEL_KEYS)}


def _identity_for(candidate_id: str, role: str) -> dict[str, str]:
    if role == "target":
        return dict(FROZEN_VARIANTS[candidate_id]["target"])
    return dict(_COMMON_IDENTITIES[role])


def expected_actions(candidate_id: str) -> tuple[dict[str, Any], ...]:
    candidate_id = candidate_id.upper()
    if candidate_id not in FROZEN_VARIANTS:
        raise SixStatePhysicalError("candidate must be U04 or U07")
    variant = FROZEN_VARIANTS[candidate_id]
    actions: list[dict[str, Any]] = []
    for ordinal in range(1, 10):
        role = ROLES[(ordinal - 1) % 3]
        round_index = (ordinal - 1) // 3 + 1
        action_id = sha256(
            (
                f"{variant['build_tag']}|{variant['test_id']}|ordinal={ordinal}|"
                f"round={round_index}|role={role}|candidate=0x{variant['candidate_code']:x}"
            ).encode("ascii")
        )
        identity = _identity_for(candidate_id, role)
        actions.append({
            "ordinal": ordinal,
            "round": round_index,
            "role": role,
            "action_id": action_id,
            "frame_sha256": identity["frame_sha256"],
            "frame_fnv1a": identity["frame_fnv1a"],
            "cs1_dtm_sha256": identity["dtm_sha256"],
            "cs2_dtm_sha256": identity["dtm_sha256"],
            "cs1_dtm_fnv1a": identity["dtm_fnv1a"],
            "cs2_dtm_fnv1a": identity["dtm_fnv1a"],
        })
    return tuple(actions)


def _validate_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _keys(root.get("integrity"), {"canonical_sha256", "scope"}, label=f"{label}.integrity")
    expected = _hex64(integrity["canonical_sha256"], label=f"{label}.integrity.canonical_sha256")
    if integrity["scope"] != HASH_SCOPE:
        raise SixStatePhysicalError(f"{label} integrity scope mismatch")
    unsigned = deepcopy(root)
    unsigned.pop("integrity")
    actual = sha256(canonical_json_bytes(unsigned))
    if actual != expected:
        raise SixStatePhysicalError(f"{label} canonical integrity mismatch")
    return actual


def _validate_source_snapshot(value: Any, source_root: Path) -> None:
    snapshot = _keys(
        value,
        {"git_head", "git_dirty", "git_status_sha256", "git_status_line_count", "relevant_sources"},
        label="source_snapshot",
    )
    if not isinstance(snapshot["git_head"], str) or _HEX40_RE.fullmatch(snapshot["git_head"]) is None:
        raise SixStatePhysicalError("source_snapshot.git_head is malformed")
    if not isinstance(snapshot["git_dirty"], bool):
        raise SixStatePhysicalError("source_snapshot.git_dirty must be boolean")
    _hex64(snapshot["git_status_sha256"], label="source_snapshot.git_status_sha256")
    _integer(snapshot["git_status_line_count"], label="source_snapshot.git_status_line_count")
    entries = snapshot["relevant_sources"]
    if not isinstance(entries, list) or [item.get("path") if isinstance(item, Mapping) else None for item in entries] != list(SOURCE_PATHS):
        raise SixStatePhysicalError("source_snapshot relevant sources differ from the frozen list")
    for index, raw in enumerate(entries):
        item = _keys(raw, {"path", "bytes", "sha256"}, label=f"source entry {index}")
        relative = _safe_relative(item["path"], label=f"source entry {index}.path")
        payload = _read_regular(
            _inside(source_root, relative, label=f"source {relative.as_posix()}"),
            label=f"source {relative.as_posix()}",
            maximum=MAX_BINARY_BYTES,
        )
        if item["bytes"] != len(payload) or item["sha256"] != sha256(payload):
            raise SixStatePhysicalError(f"source {relative.as_posix()} differs from release")


def _validate_binary(payload: bytes, candidate_id: str) -> None:
    if not payload:
        raise SixStatePhysicalError("firmware binary is empty")
    expected = FROZEN_VARIANTS[candidate_id]
    tokens = [expected["build_tag"], expected["test_id"], LAYOUT_ID]
    for action in expected_actions(candidate_id):
        tokens.extend((action["action_id"], action["frame_sha256"], action["cs1_dtm_sha256"]))
    for token in set(tokens):
        if str(token).encode("ascii") not in payload:
            raise SixStatePhysicalError(f"firmware omits frozen token {token}")
    other = "U07" if candidate_id == "U04" else "U04"
    for token in (
        FROZEN_VARIANTS[other]["build_tag"],
        FROZEN_VARIANTS[other]["test_id"],
        expected_actions(other)[0]["action_id"],
    ):
        if str(token).encode("ascii") in payload:
            raise SixStatePhysicalError("firmware contains the other candidate identity")
    forbidden_stage_a_tokens = (
        "MF1750_EC5_U04_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
        "MF1750_EC5_U07_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
        "EC5-U04-I01-P01-L64M1",
        "EC5-U07-I01-P01-L64M1",
    )
    for token in forbidden_stage_a_tokens:
        if token.encode("ascii") in payload:
            raise SixStatePhysicalError("six-state firmware contains a Stage-A identity")
    # Match complete C-string routes so the required sixstate-prefixed routes
    # cannot collide with these shorter, forbidden APIs.
    for route in (b"/api/ec5/arm\0", b"/api/ec5/execute\0", b"/api/frame\0"):
        if route in payload:
            raise SixStatePhysicalError(f"six-state firmware contains forbidden route {route[:-1].decode()}")


def load_release(
    release_file: Path,
    candidate_id: str,
    *,
    source_root: Path = REPO_ROOT,
    panel_file: Path | None = None,
) -> ReleaseContext:
    """Deeply validate and select one candidate from a frozen release."""

    candidate_id = candidate_id.upper()
    if candidate_id not in FROZEN_VARIANTS:
        raise SixStatePhysicalError("candidate must be U04 or U07")
    release_file = Path(release_file)
    root, _payload = _read_json(release_file, label="six-state release manifest")
    _keys(
        root,
        {"schema_version", "kind", "created_at", "panel", "source_snapshot", "device_contract", "assets", "variants", "safety", "integrity"},
        label="six-state release manifest",
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != RELEASE_KIND:
        raise SixStatePhysicalError("unsupported six-state release schema or kind")
    _timestamp(root["created_at"], label="release.created_at")
    release_hash = _validate_integrity(root, label="six-state release")
    panel = _validate_panel(root["panel"], label="release.panel")
    panel_verified = False
    verified_panel_file: Path | None = None
    if panel_file is not None:
        live, _ = _read_json(Path(panel_file), label="live panel identity")
        if _validate_panel(live, label="live panel identity") != panel:
            raise SixStatePhysicalError("live panel identity does not match frozen release panel")
        panel_verified = True
        verified_panel_file = Path(panel_file).resolve()
    _validate_source_snapshot(root["source_snapshot"], Path(source_root))
    if root["device_contract"] != DEVICE_CONTRACT:
        raise SixStatePhysicalError("device contract differs from the frozen contract")
    safety = _keys(
        root["safety"],
        {"classification", "hardware_authorized", "upload_performed", "device_io_performed", "visible_refresh_performed", "dithering_present", "spatial_mixing_present", "custom_waveform_or_lut_used", "factory_otp_unchanged", "u07_requires_stage_a_pass_and_recovery", "target_observation_required_before_white", "white_recovery_required_before_next_primer"},
        label="release.safety",
    )
    expected_safety = {
        "classification": "EXPERIMENTAL_NOT_QUALIFIED",
        "hardware_authorized": False,
        "upload_performed": False,
        "device_io_performed": False,
        "visible_refresh_performed": False,
        "dithering_present": False,
        "spatial_mixing_present": False,
        "custom_waveform_or_lut_used": False,
        "factory_otp_unchanged": True,
        "u07_requires_stage_a_pass_and_recovery": True,
        "target_observation_required_before_white": True,
        "white_recovery_required_before_next_primer": True,
    }
    if safety != expected_safety:
        raise SixStatePhysicalError("release safety declaration differs from the frozen contract")

    assets = _keys(root["assets"], {"U04", "U07"}, label="release.assets")
    variants = _keys(root["variants"], {"U04", "U07"}, label="release.variants")
    selected_asset_path: Path | None = None
    selected_asset_sha = ""
    selected_binary_path: Path | None = None
    selected_binary_sha = ""
    selected_variant: Mapping[str, Any] | None = None
    for tag in ("U04", "U07"):
        expected_variant = FROZEN_VARIANTS[tag]
        asset = _keys(
            assets[tag],
            {"candidate_id", "manifest_file", "manifest_bytes", "manifest_sha256", "manifest_payload_sha256"},
            label=f"release.assets.{tag}",
        )
        if asset["candidate_id"] != tag:
            raise SixStatePhysicalError(f"release.assets.{tag} candidate mismatch")
        relative_asset = _safe_relative(asset["manifest_file"], label=f"release.assets.{tag}.manifest_file")
        asset_path = _inside(release_file.parent, relative_asset, label=f"{tag} asset manifest")
        asset_bytes = _read_regular(asset_path, label=f"{tag} asset manifest", maximum=MAX_JSON_BYTES)
        if asset["manifest_bytes"] != len(asset_bytes) or asset["manifest_sha256"] != sha256(asset_bytes):
            raise SixStatePhysicalError(f"{tag} asset manifest file identity mismatch")
        if asset["manifest_payload_sha256"] != expected_variant["asset_manifest_payload_sha256"]:
            raise SixStatePhysicalError(f"{tag} asset payload identity differs from frozen contract")
        try:
            asset_report = asset_tool.validate_bundle(asset_path)
        except Exception as error:
            raise SixStatePhysicalError(f"{tag} asset bundle deep validation failed: {error}") from error
        if asset_report["candidate_id"] != tag or asset_report["manifest_payload_sha256"] != asset["manifest_payload_sha256"]:
            raise SixStatePhysicalError(f"{tag} asset bundle report mismatch")

        variant = _keys(
            variants[tag],
            {"candidate_id", "candidate_code", "environment", "build_tag", "test_id", "layout_id", "firmware", "build_command", "asset_manifest_sha256", "actions"},
            label=f"release.variants.{tag}",
        )
        for key in ("candidate_id", "candidate_code", "environment", "build_tag", "test_id", "layout_id"):
            if variant[key] != expected_variant[key]:
                raise SixStatePhysicalError(f"release.variants.{tag}.{key} differs from frozen contract")
        if variant["build_command"] != ["pio", "run", "-e", expected_variant["environment"]]:
            raise SixStatePhysicalError(f"release.variants.{tag}.build_command differs")
        if variant["asset_manifest_sha256"] != asset["manifest_sha256"]:
            raise SixStatePhysicalError(f"release.variants.{tag} is not bound to its asset manifest")
        if variant["actions"] != list(expected_actions(tag)):
            raise SixStatePhysicalError(f"release.variants.{tag}.actions differ from the frozen nine actions")
        firmware = _keys(variant["firmware"], {"file", "bytes", "sha256"}, label=f"release.variants.{tag}.firmware")
        if firmware["file"] != expected_variant["firmware_file"]:
            raise SixStatePhysicalError(f"release.variants.{tag}.firmware filename differs")
        relative_binary = _safe_relative(firmware["file"], label=f"release.variants.{tag}.firmware.file")
        binary_path = _inside(release_file.parent, relative_binary, label=f"{tag} firmware")
        binary = _read_regular(binary_path, label=f"{tag} firmware", maximum=MAX_BINARY_BYTES)
        if firmware["bytes"] != len(binary) or firmware["sha256"] != sha256(binary):
            raise SixStatePhysicalError(f"{tag} firmware file identity mismatch")
        _validate_binary(binary, tag)
        if tag == candidate_id:
            selected_asset_path, selected_asset_sha = asset_path, asset["manifest_sha256"]
            selected_binary_path, selected_binary_sha = binary_path, firmware["sha256"]
            selected_variant = variant
    assert selected_asset_path is not None and selected_binary_path is not None and selected_variant is not None
    return ReleaseContext(
        path=release_file.resolve(),
        root=root,
        candidate_id=candidate_id,
        variant=selected_variant,
        actions=tuple(selected_variant["actions"]),
        binary_path=selected_binary_path,
        binary_sha256=selected_binary_sha,
        asset_manifest_path=selected_asset_path,
        asset_file_sha256=selected_asset_sha,
        release_canonical_sha256=release_hash,
        panel=panel,
        panel_verified=panel_verified,
        panel_file=verified_panel_file,
        source_root=Path(source_root).resolve(),
    )


def _action(context: ReleaseContext, ordinal: int) -> Mapping[str, Any]:
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 1 <= ordinal <= 9:
        raise SixStatePhysicalError("ordinal must be an integer from 1 through 9")
    return context.actions[ordinal - 1]


def required_authorization(context: ReleaseContext, ordinal: int) -> str:
    action = _action(context, ordinal)
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_SIXSTATE_{context.candidate_id}_"
        f"ORDINAL_{ordinal}_{str(action['role']).upper()}__ACTION_"
        f"{str(action['action_id']).upper()}{AUTHORIZATION_SUFFIX}"
    )


def _identity_reference(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read_regular(path, label=label, maximum=MAX_JSON_BYTES)
    root = _decode_json(payload, label=label)
    integrity = root.get("integrity")
    integrity_sha = None
    if isinstance(integrity, Mapping):
        integrity_sha = integrity.get("canonical_sha256")
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": integrity_sha,
    }


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **deepcopy(dict(unsigned)),
        "integrity": {
            "canonical_sha256": sha256(canonical_json_bytes(unsigned)),
            "scope": HASH_SCOPE,
        },
    }


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    payload = canonical_json_bytes(value) + b"\n"
    try:
        parent = path.parent.resolve(strict=True)
        destination = parent / path.name
        with destination.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise SixStatePhysicalError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise SixStatePhysicalError(f"could not write {path}: {error}") from error


STAGE_A_EVIDENCE_KEYS = frozenset(
    {
        "release_file",
        "u04_result_file",
        "u04_review_file",
        "u04_hold_0_file",
        "u04_hold_5_file",
        "u04_hold_30_file",
        "after_u04_white_result_file",
        "u07_result_file",
        "u07_hold_0_file",
        "u07_hold_5_file",
        "u07_hold_30_file",
        "after_u07_white_result_file",
        "candidate_claim_registry",
        "white_claim_registry",
        "rc2g_binary_file",
    }
)


def _validate_stage_a_gate(
    context: ReleaseContext,
    evidence: Mapping[str, Path | None],
) -> dict[str, Any] | None:
    """Replay the real Stage-A result/claims/holds/white bytes for U07."""

    if set(evidence) != set(STAGE_A_EVIDENCE_KEYS):
        raise SixStatePhysicalError("internal Stage-A evidence fields differ")
    supplied = {key: value for key, value in evidence.items() if value is not None}
    if context.candidate_id == "U04":
        if supplied:
            raise SixStatePhysicalError("U04 Stage-B must not receive U07 Stage-A gate evidence")
        return None
    if set(supplied) != set(STAGE_A_EVIDENCE_KEYS):
        missing = sorted(set(STAGE_A_EVIDENCE_KEYS) - set(supplied))
        raise SixStatePhysicalError(
            f"U07 Stage-B requires real Stage-A release/result/claim/hold/white evidence; missing {missing}"
        )
    paths = {key: Path(value) for key, value in supplied.items()}
    try:
        from tools import mf1750_ec5_physical_once as pilot
        from tools import mf1750_ec5_white_recovery_once as white

        pilot_context = pilot.load_release(
            paths["release_file"],
            "U07",
            panel_file=context.panel_file,
        )
        validation_kwargs = {
            "u04_review_file": paths["u04_review_file"],
            "u04_result_file": paths["u04_result_file"],
            "u04_hold_0_file": paths["u04_hold_0_file"],
            "u04_hold_5_file": paths["u04_hold_5_file"],
            "u04_hold_30_file": paths["u04_hold_30_file"],
            "u04_white_recovery_result_file": paths["after_u04_white_result_file"],
            "rc2g_binary_file": paths["rc2g_binary_file"],
            "white_claim_registry": paths["white_claim_registry"],
        }
        pilot_result = pilot.validate_result(
            pilot_context,
            paths["u07_result_file"],
            claim_registry=paths["candidate_claim_registry"],
            **validation_kwargs,
        )
        if pilot_result["outcome"] != "complete_pass":
            raise SixStatePhysicalError("Stage-A U07 physical result is not complete_pass")
        holds = {
            0: pilot.validate_hold_observation(
                pilot_context,
                paths["u07_hold_0_file"],
                paths["u07_result_file"],
                expected_hold_minutes=0,
                prior_hold_files={},
                claim_registry=paths["candidate_claim_registry"],
                result_validation_kwargs=validation_kwargs,
            ),
            5: pilot.validate_hold_observation(
                pilot_context,
                paths["u07_hold_5_file"],
                paths["u07_result_file"],
                expected_hold_minutes=5,
                prior_hold_files={0: paths["u07_hold_0_file"]},
                claim_registry=paths["candidate_claim_registry"],
                result_validation_kwargs=validation_kwargs,
            ),
            30: pilot.validate_hold_observation(
                pilot_context,
                paths["u07_hold_30_file"],
                paths["u07_result_file"],
                expected_hold_minutes=30,
                prior_hold_files={0: paths["u07_hold_0_file"], 5: paths["u07_hold_5_file"]},
                claim_registry=paths["candidate_claim_registry"],
                result_validation_kwargs=validation_kwargs,
            ),
        }
        white_ref = white.load_result_binding(
            result_file=paths["after_u07_white_result_file"],
            panel_file=context.panel_file,
            rc2g_binary_file=paths["rc2g_binary_file"],
            claim_registry=paths["white_claim_registry"],
            release_file=paths["release_file"],
            candidate_result_file=paths["u07_result_file"],
            candidate_claim_registry=paths["candidate_claim_registry"],
            u04_review_file=paths["u04_review_file"],
            u04_result_file=paths["u04_result_file"],
            u04_hold_0_file=paths["u04_hold_0_file"],
            u04_hold_5_file=paths["u04_hold_5_file"],
            u04_hold_30_file=paths["u04_hold_30_file"],
            u04_white_recovery_result_file=paths["after_u04_white_result_file"],
            u04_rc2g_binary_file=paths["rc2g_binary_file"],
            u04_white_claim_registry=paths["white_claim_registry"],
        )
    except SixStatePhysicalError:
        raise
    except Exception as error:
        raise SixStatePhysicalError(f"real Stage-A U07 gate replay failed: {error}") from error
    if white_ref["stage"] != "after-u07" or white_ref["candidate_binding"]["candidate_id"] != "U07":
        raise SixStatePhysicalError("Stage-A recovery is not the exact after-u07 white result")
    if _timestamp(white_ref["completed_at"], label="after-u07 white completed_at") < _timestamp(holds[30]["recorded_at"], label="U07 hold30 recorded_at"):
        raise SixStatePhysicalError("after-u07 white recovery predates the U07 30-minute hold")
    pilot_payload = _read_regular(paths["u07_result_file"], label="Stage-A U07 result", maximum=MAX_JSON_BYTES)
    return {
        "release_file": str(paths["release_file"].resolve()),
        "release_canonical_sha256": pilot_context.release_canonical_sha256,
        "u07_result": {
            "file": str(paths["u07_result_file"].resolve()),
            "bytes": len(pilot_payload),
            "file_sha256": sha256(pilot_payload),
            "integrity_sha256": pilot_result["integrity"]["canonical_sha256"],
            "action_id": pilot_context.variant["action_id"],
            "outcome": "complete_pass",
        },
        "holds": [holds[minute] for minute in (0, 5, 30)],
        "after_u07_white": white_ref,
        "rc2g_binary_sha256": white_ref["rc2g_binary"]["sha256"],
        "gate_pass": True,
    }


def _validate_gpio(value: Any, *, label: str) -> Mapping[str, Any]:
    gpio = _keys(value, {"initialized", "busy", "rst", "cs1", "cs2"}, label=label)
    _boolean(gpio["initialized"], True, label=f"{label}.initialized")
    for key in ("busy", "rst", "cs1", "cs2"):
        _integer(gpio[key], label=f"{label}.{key}", maximum=1)
    return gpio


def _validate_version(context: ReleaseContext, value: Any) -> Mapping[str, Any]:
    version = _keys(
        value,
        {"schema_version", "kind", "build_tag", "test_id", "candidate_id", "candidate_code", "driver_api_version", "layout_id", "startup_refresh", "raw_frame_ingress", "lut_modification", "automatic_execute", "fixed_action_count", "cooldown_ms", "persistent_progress", "retry", "recovery", "not_hardware_authorization"},
        label="device version",
    )
    expected = FROZEN_VARIANTS[context.candidate_id]
    if version["schema_version"] != 1 or version["kind"] != "mf1750-ec5-sixstate-version":
        raise SixStatePhysicalError("device version schema mismatch")
    for key in ("build_tag", "test_id", "candidate_id", "layout_id"):
        if version[key] != expected[key]:
            raise SixStatePhysicalError(f"device version {key} mismatch")
    if version["candidate_code"] != f"0x{expected['candidate_code']:x}" or version["driver_api_version"] != EXPECTED_DRIVER_API_VERSION:
        raise SixStatePhysicalError("device version candidate or driver API mismatch")
    for key in ("startup_refresh", "raw_frame_ingress", "lut_modification", "automatic_execute", "retry", "recovery"):
        _boolean(version[key], False, label=f"device version.{key}")
    for key in ("persistent_progress", "not_hardware_authorization"):
        _boolean(version[key], True, label=f"device version.{key}")
    if version["fixed_action_count"] != 9 or version["cooldown_ms"] != COOLDOWN_SECONDS * 1000:
        raise SixStatePhysicalError("device version action count or cooldown mismatch")
    return version


def _validate_device_action(raw: Any, expected: Mapping[str, Any], *, label: str) -> None:
    action = _keys(raw, set(expected), label=label)
    if action != expected:
        raise SixStatePhysicalError(f"{label} differs from frozen action")


def _validate_manifest(context: ReleaseContext, value: Any) -> Mapping[str, Any]:
    manifest = _keys(
        value,
        {"schema_version", "kind", "build_tag", "test_id", "candidate_id", "candidate_code", "layout_id", "geometry", "initial_codes", "y0", "roi_x0", "mapping_cs1", "mapping_cs2", "sequence", "safety"},
        label="device manifest",
    )
    expected = FROZEN_VARIANTS[context.candidate_id]
    if manifest["schema_version"] != 1 or manifest["kind"] != "mf1750-ec5-sixstate-manifest":
        raise SixStatePhysicalError("device manifest schema mismatch")
    for key in ("build_tag", "test_id", "candidate_id", "candidate_code", "layout_id"):
        if manifest[key] != expected[key]:
            raise SixStatePhysicalError(f"device manifest {key} mismatch")
    geometry = _keys(manifest["geometry"], {"width", "height", "frame_bytes", "packing", "roi_count", "roi_width", "roi_height", "candidate_pixels", "background_code"}, label="device manifest.geometry")
    expected_geometry = {"width": 1024, "height": 600, "frame_bytes": 307200, "packing": "row_major_4bpp_even_x_high_nibble", "roi_count": 12, "roi_width": 24, "roi_height": 24, "candidate_pixels": 6912, "background_code": 1}
    if geometry != expected_geometry:
        raise SixStatePhysicalError("device manifest geometry mismatch")
    if manifest["initial_codes"] != list(INITIAL_CODES) or manifest["y0"] != [48, 144, 240, 336, 432, 528] or manifest["roi_x0"] != {"cs1": 244, "cs2": 756}:
        raise SixStatePhysicalError("device manifest ROI layout mismatch")
    if manifest["mapping_cs1"] != [0, 0, 0, 0] or manifest["mapping_cs2"] != [1, 0, 0, 0]:
        raise SixStatePhysicalError("device manifest controller mapping mismatch")
    sequence = manifest["sequence"]
    if not isinstance(sequence, list) or len(sequence) != 9:
        raise SixStatePhysicalError("device manifest sequence must contain nine actions")
    for index, raw in enumerate(sequence):
        _validate_device_action(raw, context.actions[index], label=f"device manifest.sequence[{index}]")
    safety = _keys(
        manifest["safety"],
        {"dithering", "spatial_mixing", "uniform_single_code_rois", "bodyless_mutations", "exact_build_test_action_ordinal_boot_arm_nonce", "claim_before_driver", "max_driver_calls_per_action", "cooldown_from_previous_completion_ms", "reboot_cooldown_is_conservatively_restarted", "network_reset_clear_retry_recovery_routes", "not_hardware_authorization"},
        label="device manifest.safety",
    )
    for key in ("dithering", "spatial_mixing", "network_reset_clear_retry_recovery_routes"):
        _boolean(safety[key], False, label=f"device manifest.safety.{key}")
    for key in ("uniform_single_code_rois", "bodyless_mutations", "exact_build_test_action_ordinal_boot_arm_nonce", "claim_before_driver", "reboot_cooldown_is_conservatively_restarted", "not_hardware_authorization"):
        _boolean(safety[key], True, label=f"device manifest.safety.{key}")
    if safety["max_driver_calls_per_action"] != 1 or safety["cooldown_from_previous_completion_ms"] != COOLDOWN_SECONDS * 1000:
        raise SixStatePhysicalError("device manifest safety limits mismatch")
    return manifest


def _validate_status(
    context: ReleaseContext,
    value: Any,
    *,
    expected_ordinal: int,
    phase: str,
    boot_nonce: str | None = None,
) -> Mapping[str, Any]:
    status = _keys(
        value,
        {"schema_version", "kind", "build_tag", "test_id", "boot_nonce", "candidate_code", "state", "next_ordinal", "next_round", "next_role", "next_action_id", "pending_phase", "fixture_self_check_passed", "execute_pending", "current_action_driver_called", "total_driver_calls_this_boot", "cooldown_ms", "cooldown_remaining_ms", "gpio", "no_retry", "no_recovery"},
        label="device status",
    )
    variant = FROZEN_VARIANTS[context.candidate_id]
    if status["schema_version"] != 1 or status["kind"] != "mf1750-ec5-sixstate-status" or status["build_tag"] != variant["build_tag"] or status["test_id"] != variant["test_id"] or status["candidate_code"] != variant["candidate_code"]:
        raise SixStatePhysicalError("device status identity mismatch")
    nonce = status["boot_nonce"]
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None or (boot_nonce is not None and nonce != boot_nonce):
        raise SixStatePhysicalError("device status boot nonce is malformed or changed")
    _boolean(status["fixture_self_check_passed"], True, label="device status.fixture_self_check_passed")
    _boolean(status["no_retry"], True, label="device status.no_retry")
    _boolean(status["no_recovery"], True, label="device status.no_recovery")
    gpio = _validate_gpio(status["gpio"], label="device status.gpio")
    _integer(status["total_driver_calls_this_boot"], label="device status.total_driver_calls_this_boot")
    if status["cooldown_ms"] != COOLDOWN_SECONDS * 1000:
        raise SixStatePhysicalError("device status cooldown contract mismatch")
    remaining = _integer(status["cooldown_remaining_ms"], label="device status.cooldown_remaining_ms", maximum=COOLDOWN_SECONDS * 1000)
    if phase in ("ready", "armed"):
        if gpio != {"initialized": True, "busy": 1, "rst": 0, "cs1": 0, "cs2": 0}:
            raise SixStatePhysicalError(
                f"device {phase} GPIO is not exact safe idle-high BUSY with RST/CS low"
            )
        action = _action(context, expected_ordinal)
        expected_state = "ready" if phase == "ready" else "armed"
        expected_pending = "virgin" if phase == "ready" else "claimed"
        if status["state"] != expected_state or status["pending_phase"] != expected_pending or status["next_ordinal"] != expected_ordinal or status["next_round"] != action["round"] or status["next_role"] != action["role"] or status["next_action_id"] != action["action_id"] or remaining != 0:
            raise SixStatePhysicalError(f"device status is not exact {phase} state for ordinal {expected_ordinal}")
        _boolean(status["execute_pending"], False, label="device status.execute_pending")
        _boolean(status["current_action_driver_called"], False, label="device status.current_action_driver_called")
    elif phase == "terminal":
        if gpio != {"initialized": True, "busy": 1, "rst": 0, "cs1": 0, "cs2": 0}:
            raise SixStatePhysicalError("device terminal GPIO is not exact safe finish")
        next_ordinal = expected_ordinal + 1
        if status["next_ordinal"] != next_ordinal or status["pending_phase"] != "virgin":
            raise SixStatePhysicalError("terminal status did not persist the next ordinal")
        _boolean(status["execute_pending"], False, label="terminal status.execute_pending")
        _boolean(status["current_action_driver_called"], True, label="terminal status.current_action_driver_called")
        if expected_ordinal == 9:
            if status["state"] != "campaign_complete" or status["next_round"] != 0 or status["next_role"] is not None or status["next_action_id"] is not None or remaining != 0:
                raise SixStatePhysicalError("ordinal 9 terminal status is not campaign_complete")
        else:
            next_action = _action(context, next_ordinal)
            if status["state"] != "cooldown" or status["next_round"] != next_action["round"] or status["next_role"] != next_action["role"] or status["next_action_id"] != next_action["action_id"] or remaining <= 0:
                raise SixStatePhysicalError("terminal status is not in the required cooldown")
    else:
        raise SixStatePhysicalError("internal invalid status phase")
    return status


def _validate_no_execute_report(context: ReleaseContext, value: Any, *, ordinal: int, boot_nonce: str) -> Mapping[str, Any]:
    report = _keys(
        value,
        {"schema_version", "kind", "valid", "terminal_state", "error", "build_tag", "test_id", "boot_nonce", "candidate_code", "next_ordinal", "next_action_id", "pending_phase", "driver_called", "no_retry", "no_recovery"},
        label="device no-execute report",
    )
    action = _action(context, ordinal)
    variant = FROZEN_VARIANTS[context.candidate_id]
    expected = {
        "schema_version": 1,
        "kind": "mf1750-ec5-sixstate-report",
        "valid": False,
        "terminal_state": "NOT_EXECUTED",
        "error": "no_execute_report",
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "boot_nonce": boot_nonce,
        "candidate_code": variant["candidate_code"],
        "next_ordinal": ordinal,
        "next_action_id": action["action_id"],
        "pending_phase": "virgin",
        "driver_called": False,
        "no_retry": True,
        "no_recovery": True,
    }
    if report != expected:
        raise SixStatePhysicalError("device preflight report is not exact NOT_EXECUTED virgin evidence")
    return report


def _validate_busy_stage(value: Any, *, label: str) -> None:
    stage = _keys(
        value,
        {"gate_entry_level", "pre_command_level", "wait_entry_level", "wait_exit_level", "pre_command_idle_ok", "assertion_after_idle", "pre_command_wait_ms", "wait_ms", "assertion_latency_ms"},
        label=label,
    )
    for key in ("gate_entry_level", "pre_command_level", "wait_entry_level", "wait_exit_level"):
        _integer(stage[key], label=f"{label}.{key}", maximum=1)
    _boolean(stage["pre_command_idle_ok"], True, label=f"{label}.pre_command_idle_ok")
    if not isinstance(stage["assertion_after_idle"], bool):
        raise SixStatePhysicalError(f"{label}.assertion_after_idle must be boolean")
    for key in ("pre_command_wait_ms", "wait_ms", "assertion_latency_ms"):
        _integer(stage[key], label=f"{label}.{key}")


def _validate_terminal_report(
    context: ReleaseContext,
    value: Any,
    *,
    ordinal: int,
    boot_nonce: str,
) -> Mapping[str, Any]:
    report = _keys(
        value,
        {"schema_version", "kind", "valid", "build_tag", "test_id", "boot_nonce", "candidate_code", "ordinal", "round", "role", "action_id", "terminal_state", "result", "driver_called", "driver_call_count_for_action", "expected_identity", "next_ordinal", "pending_phase", "cooldown_ms", "job_queued_at_ms", "job_started_at_ms", "job_finished_at_ms", "no_retry", "no_recovery", "driver"},
        label="device terminal report",
    )
    action = _action(context, ordinal)
    variant = FROZEN_VARIANTS[context.candidate_id]
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-sixstate-report",
        "valid": True,
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "boot_nonce": boot_nonce,
        "candidate_code": variant["candidate_code"],
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "terminal_state": "COMPLETED",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "next_ordinal": ordinal + 1,
        "pending_phase": "virgin",
        "cooldown_ms": 0 if ordinal == 9 else COOLDOWN_SECONDS * 1000,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, expected in exact.items():
        if report[key] != expected:
            raise SixStatePhysicalError(f"device terminal report {key} mismatch")
    expected_identity = {
        "frame_sha256": action["frame_sha256"],
        "frame_fnv1a": action["frame_fnv1a"],
        "cs1_dtm_sha256": action["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["cs2_dtm_sha256"],
        "cs1_dtm_fnv1a": action["cs1_dtm_fnv1a"],
        "cs2_dtm_fnv1a": action["cs2_dtm_fnv1a"],
    }
    if report["expected_identity"] != expected_identity:
        raise SixStatePhysicalError("device terminal expected identity mismatch")
    queued = _integer(report["job_queued_at_ms"], label="device report.job_queued_at_ms")
    started = _integer(report["job_started_at_ms"], label="device report.job_started_at_ms")
    finished = _integer(report["job_finished_at_ms"], label="device report.job_finished_at_ms")
    if not queued <= started <= finished:
        raise SixStatePhysicalError("device job timestamps are not monotonic")

    driver = _keys(
        report["driver"],
        {"operation_id", "valid", "running", "sequence_ok", "wait_timed_out", "busy_assertion_missing", "pre_command_idle_failure", "mapping_applied", "input_frame_fnv1a", "cs1_dtm_fnv1a", "cs2_dtm_fnv1a", "spi_hz", "total_ms", "upload_ms", "busy_seen", "busy_stages", "wait_ms", "last_wait_stage", "timeout_stage", "busy_missing_stage", "pre_command_busy_stage", "safe_finish"},
        label="device report.driver",
    )
    _integer(driver["operation_id"], label="device driver.operation_id", minimum=1)
    for key in ("valid", "sequence_ok", "mapping_applied"):
        _boolean(driver[key], True, label=f"device driver.{key}")
    for key in ("running", "wait_timed_out", "busy_assertion_missing", "pre_command_idle_failure"):
        _boolean(driver[key], False, label=f"device driver.{key}")
    if driver["input_frame_fnv1a"] != action["frame_fnv1a"] or driver["cs1_dtm_fnv1a"] != action["cs1_dtm_fnv1a"] or driver["cs2_dtm_fnv1a"] != action["cs2_dtm_fnv1a"]:
        raise SixStatePhysicalError("device driver frame/DTM FNV evidence mismatch")
    _integer(driver["spi_hz"], label="device driver.spi_hz", minimum=1)
    _integer(driver["total_ms"], label="device driver.total_ms", minimum=1)
    uploads = _keys(driver["upload_ms"], {"cs1", "cs2"}, label="device driver.upload_ms")
    for key in ("cs1", "cs2"):
        _integer(uploads[key], label=f"device driver.upload_ms.{key}")
    busy_seen = _keys(driver["busy_seen"], {"pon", "drf", "pof", "post_psr"}, label="device driver.busy_seen")
    for key in ("pon", "drf", "pof"):
        _boolean(busy_seen[key], True, label=f"device driver.busy_seen.{key}")
    if not isinstance(busy_seen["post_psr"], bool):
        raise SixStatePhysicalError("device driver.busy_seen.post_psr must be boolean")
    stages = _keys(driver["busy_stages"], {"reset", "pon", "drf", "pof", "post_psr"}, label="device driver.busy_stages")
    for name, stage in stages.items():
        _validate_busy_stage(stage, label=f"device driver.busy_stages.{name}")
    waits = _keys(driver["wait_ms"], {"pon", "drf", "pof", "post_psr"}, label="device driver.wait_ms")
    for key, wait in waits.items():
        _integer(wait, label=f"device driver.wait_ms.{key}")
    _string(driver["last_wait_stage"], label="device driver.last_wait_stage")
    for key in ("timeout_stage", "busy_missing_stage", "pre_command_busy_stage"):
        if driver[key] != "none":
            raise SixStatePhysicalError(f"device driver.{key} is not none")
    safe = _keys(driver["safe_finish"], {"busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms", "final_gpio"}, label="device driver.safe_finish")
    for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms"):
        if safe[key] != 1:
            raise SixStatePhysicalError(f"device safe finish {key} must be idle-high")
    final_gpio = _keys(safe["final_gpio"], {"busy", "rst", "cs1", "cs2"}, label="device driver.safe_finish.final_gpio")
    if final_gpio != {"busy": 1, "rst": 0, "cs1": 0, "cs2": 0}:
        raise SixStatePhysicalError("device safe finish GPIO differs from frozen safe state")
    return report


def _base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SixStatePhysicalError("base URL must be an absolute HTTP(S) origin without credentials/query/fragment")
    if parsed.path not in ("", "/"):
        raise SixStatePhysicalError("base URL must not contain a path")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _http_json(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
    urlopen: Callable[..., Any],
) -> Mapping[str, Any]:
    request = urllib.request.Request(
        base_url + path,
        data=None,
        headers=dict(headers or {}),
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            payload = response.read(MAX_JSON_BYTES + 1)
    except Exception as error:
        raise SixStatePhysicalError(f"{method} {path} failed: {error}") from error
    if not isinstance(status, int) or not 200 <= status < 300:
        raise SixStatePhysicalError(f"{method} {path} returned HTTP {status}")
    return _decode_json(payload, label=f"{method} {path} response")


def _get_snapshot(
    context: ReleaseContext,
    base_url: str,
    *,
    timeout: float,
    urlopen: Callable[..., Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    status = _http_json(base_url, _ENDPOINTS["status"], method="GET", headers=None, timeout=timeout, urlopen=urlopen)
    report = _http_json(base_url, _ENDPOINTS["report"], method="GET", headers=None, timeout=timeout, urlopen=urlopen)
    return status, report


def preflight(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> Preflight:
    """Perform exactly four read-only GETs and require the selected virgin action."""

    if not context.panel_verified or context.panel_file is None:
        raise SixStatePhysicalError("preflight requires a deeply verified live panel identity file")
    # Re-read it at the last read-only boundary so replacement after release
    # loading is detected before any request.
    live_panel, _ = _read_json(context.panel_file, label="live panel identity")
    if _validate_panel(live_panel, label="live panel identity") != dict(context.panel):
        raise SixStatePhysicalError("live panel identity changed after release loading")
    action = _action(context, ordinal)
    origin = _base_url(base_url)
    version = _validate_version(
        context,
        _http_json(origin, _ENDPOINTS["version"], method="GET", headers=None, timeout=timeout, urlopen=_urlopen),
    )
    manifest = _validate_manifest(
        context,
        _http_json(origin, _ENDPOINTS["manifest"], method="GET", headers=None, timeout=timeout, urlopen=_urlopen),
    )
    status_raw = _http_json(origin, _ENDPOINTS["status"], method="GET", headers=None, timeout=timeout, urlopen=_urlopen)
    status = _validate_status(context, status_raw, expected_ordinal=ordinal, phase="ready")
    boot_nonce = str(status["boot_nonce"])
    report = _validate_no_execute_report(
        context,
        _http_json(origin, _ENDPOINTS["report"], method="GET", headers=None, timeout=timeout, urlopen=_urlopen),
        ordinal=ordinal,
        boot_nonce=boot_nonce,
    )
    if status["next_action_id"] != action["action_id"]:
        raise SixStatePhysicalError("device expected action differs from selected ordinal")
    return Preflight(version, manifest, status, report, boot_nonce)


def _validate_arm_response(context: ReleaseContext, value: Any, *, ordinal: int, boot_nonce: str) -> str:
    response = _keys(
        value,
        {"accepted", "armed", "build_tag", "test_id", "ordinal", "round", "role", "action_id", "boot_nonce", "arm_nonce", "persistent_phase", "not_hardware_authorization"},
        label="ARM response",
    )
    action = _action(context, ordinal)
    variant = FROZEN_VARIANTS[context.candidate_id]
    expected = {
        "accepted": True,
        "armed": True,
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "boot_nonce": boot_nonce,
        "persistent_phase": "claimed",
        "not_hardware_authorization": True,
    }
    for key, expected_value in expected.items():
        if response[key] != expected_value:
            raise SixStatePhysicalError(f"ARM response {key} mismatch")
    arm_nonce = response["arm_nonce"]
    if not isinstance(arm_nonce, str) or _NONCE_RE.fullmatch(arm_nonce) is None:
        raise SixStatePhysicalError("ARM response arm nonce is malformed")
    return arm_nonce


def _validate_execute_response(context: ReleaseContext, value: Any, *, ordinal: int, boot_nonce: str) -> None:
    response = _keys(
        value,
        {"accepted", "queued", "build_tag", "test_id", "boot_nonce", "candidate_code", "ordinal", "round", "role", "action_id", "execute_consumed", "no_retry", "no_recovery"},
        label="EXECUTE response",
    )
    action = _action(context, ordinal)
    variant = FROZEN_VARIANTS[context.candidate_id]
    expected = {
        "accepted": True,
        "queued": True,
        "build_tag": variant["build_tag"],
        "test_id": variant["test_id"],
        "boot_nonce": boot_nonce,
        "candidate_code": variant["candidate_code"],
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "execute_consumed": True,
        "no_retry": True,
        "no_recovery": True,
    }
    if response != expected:
        raise SixStatePhysicalError("EXECUTE response differs from exact queued contract")


def _claim_path(registry: Path, action_id: str) -> Path:
    return Path(registry) / f"{action_id}.json"


def _validate_claim_payload(
    context: ReleaseContext,
    payload: bytes,
    *,
    ordinal: int,
    expected_path: Path,
) -> Mapping[str, Any]:
    claim = _decode_json(payload, label="permanent host claim")
    _keys(
        claim,
        {"schema_version", "kind", "registry_id", "created_at", "release_canonical_sha256", "candidate_id", "panel", "ordinal", "round", "role", "action_id", "attempt_id", "binary_sha256", "asset_manifest_sha256", "boot_nonce", "preflight_sha256", "prerequisites", "state", "integrity"},
        label="permanent host claim",
    )
    _validate_integrity(claim, label="permanent host claim")
    action = _action(context, ordinal)
    exact = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "binary_sha256": context.binary_sha256,
        "asset_manifest_sha256": context.asset_file_sha256,
        "state": "claimed_before_first_post_permanent_no_retry_no_recovery",
    }
    for key, expected in exact.items():
        if claim[key] != expected:
            raise SixStatePhysicalError(f"permanent host claim {key} mismatch")
    _timestamp(claim["created_at"], label="permanent host claim.created_at")
    _string(claim["attempt_id"], label="permanent host claim.attempt_id")
    if _NONCE_RE.fullmatch(str(claim["boot_nonce"])) is None:
        raise SixStatePhysicalError("permanent host claim boot nonce is malformed")
    _hex64(claim["preflight_sha256"], label="permanent host claim.preflight_sha256")
    if not isinstance(claim["prerequisites"], Mapping):
        raise SixStatePhysicalError("permanent host claim prerequisites must be an object")
    if expected_path.name != f"{action['action_id']}.json":
        raise SixStatePhysicalError("permanent host claim filename mismatch")
    return claim


def _create_claim(
    context: ReleaseContext,
    ordinal: int,
    *,
    registry: Path,
    attempt_id: str,
    created_at: str,
    preflight_value: Preflight,
    prerequisites: Mapping[str, Any],
) -> tuple[Path, Mapping[str, Any], bytes]:
    action = _action(context, ordinal)
    registry = Path(registry)
    try:
        if registry.exists():
            if registry.is_symlink() or not registry.is_dir():
                raise SixStatePhysicalError("claim registry must be a non-symlink directory")
        else:
            parent = registry.parent.resolve(strict=True)
            (parent / registry.name).mkdir(mode=0o700)
    except OSError as error:
        raise SixStatePhysicalError(f"cannot prepare claim registry: {error}") from error
    destination = _claim_path(registry, str(action["action_id"]))
    unsigned = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "created_at": created_at,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "attempt_id": attempt_id,
        "binary_sha256": context.binary_sha256,
        "asset_manifest_sha256": context.asset_file_sha256,
        "boot_nonce": preflight_value.boot_nonce,
        "preflight_sha256": preflight_value.digest(),
        "prerequisites": deepcopy(dict(prerequisites)),
        "state": "claimed_before_first_post_permanent_no_retry_no_recovery",
    }
    claim = _seal(unsigned)
    payload = canonical_json_bytes(claim) + b"\n"
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise SixStatePhysicalError(
            f"action {action['action_id']} already has a permanent host claim"
        ) from error
    except OSError as error:
        raise SixStatePhysicalError(f"cannot create permanent host claim: {error}") from error
    _validate_claim_payload(context, payload, ordinal=ordinal, expected_path=destination)
    return destination, claim, payload


def _claim_reference(path: Path, claim: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    return {
        "registry_id": CLAIM_REGISTRY_ID,
        "filename": path.name,
        "file_sha256": sha256(payload),
        "integrity_sha256": claim["integrity"]["canonical_sha256"],
        "attempt_id": claim["attempt_id"],
        "action_id": claim["action_id"],
        "state": claim["state"],
    }


def validate_result(
    context: ReleaseContext,
    result_file: Path,
    *,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    root, _payload = _read_json(Path(result_file), label="six-state physical result")
    _keys(
        root,
        {"schema_version", "kind", "release_canonical_sha256", "candidate_id", "panel", "ordinal", "round", "role", "action_id", "attempt_id", "binary_sha256", "asset_manifest_sha256", "started_at", "completed_at", "base_url", "boot_nonce", "claim", "prerequisites", "network", "outcome", "device", "integrity"},
        label="six-state physical result",
    )
    if root["schema_version"] != 1 or root["kind"] != RESULT_KIND:
        raise SixStatePhysicalError("unsupported six-state physical result")
    _validate_integrity(root, label="six-state physical result")
    if root["release_canonical_sha256"] != context.release_canonical_sha256 or root["candidate_id"] != context.candidate_id or root["panel"] != dict(context.panel):
        raise SixStatePhysicalError("physical result release/candidate/panel binding mismatch")
    ordinal = _integer(root["ordinal"], label="physical result.ordinal", minimum=1, maximum=9)
    action = _action(context, ordinal)
    for key in ("round", "role", "action_id"):
        if root[key] != action[key]:
            raise SixStatePhysicalError(f"physical result {key} mismatch")
    if root["binary_sha256"] != context.binary_sha256 or root["asset_manifest_sha256"] != context.asset_file_sha256:
        raise SixStatePhysicalError("physical result binary/assets binding mismatch")
    _timestamp(root["started_at"], label="physical result.started_at")
    completed = _timestamp(root["completed_at"], label="physical result.completed_at")
    if completed < _timestamp(root["started_at"], label="physical result.started_at"):
        raise SixStatePhysicalError("physical result timestamps are reversed")
    _base_url(root["base_url"])
    if _NONCE_RE.fullmatch(str(root["boot_nonce"])) is None:
        raise SixStatePhysicalError("physical result boot nonce malformed")
    claim_ref = _keys(root["claim"], {"registry_id", "filename", "file_sha256", "integrity_sha256", "attempt_id", "action_id", "state"}, label="physical result.claim")
    if claim_ref["registry_id"] != CLAIM_REGISTRY_ID or claim_ref["filename"] != f"{action['action_id']}.json" or claim_ref["action_id"] != action["action_id"] or claim_ref["attempt_id"] != root["attempt_id"]:
        raise SixStatePhysicalError("physical result claim reference mismatch")
    claim_path = _claim_path(Path(claim_registry), str(action["action_id"]))
    claim_payload = _read_regular(claim_path, label="referenced permanent host claim", maximum=MAX_JSON_BYTES)
    claim = _validate_claim_payload(context, claim_payload, ordinal=ordinal, expected_path=claim_path)
    if claim_ref["file_sha256"] != sha256(claim_payload) or claim_ref["integrity_sha256"] != claim["integrity"]["canonical_sha256"] or claim_ref["state"] != claim["state"]:
        raise SixStatePhysicalError("physical result claim bytes differ")
    if claim["attempt_id"] != root["attempt_id"] or claim["boot_nonce"] != root["boot_nonce"] or claim["prerequisites"] != root["prerequisites"]:
        raise SixStatePhysicalError("physical result differs from permanent claim")
    network = _keys(root["network"], {"get_requests", "post_requests", "arm_posts", "execute_posts", "no_retry", "no_recovery"}, label="physical result.network")
    gets = _integer(network["get_requests"], label="physical result.network.get_requests", minimum=4)
    posts = _integer(network["post_requests"], label="physical result.network.post_requests", maximum=2)
    arms = _integer(network["arm_posts"], label="physical result.network.arm_posts", maximum=1)
    executes = _integer(network["execute_posts"], label="physical result.network.execute_posts", maximum=1)
    if posts != arms + executes or executes > arms:
        raise SixStatePhysicalError("physical result POST counts violate one-shot ordering")
    _boolean(network["no_retry"], True, label="physical result.network.no_retry")
    _boolean(network["no_recovery"], True, label="physical result.network.no_recovery")
    if root["outcome"] not in ("complete_pass", "unknown_do_not_retry_or_recover"):
        raise SixStatePhysicalError("physical result outcome is unsupported")
    device = _keys(root["device"], {"preflight_sha256", "arm_response", "armed_status", "execute_response", "terminal_status", "terminal_report", "adjudication_errors"}, label="physical result.device")
    if device["preflight_sha256"] != claim["preflight_sha256"]:
        raise SixStatePhysicalError("physical result preflight digest mismatch")
    if not isinstance(device["adjudication_errors"], list) or any(not isinstance(item, str) for item in device["adjudication_errors"]):
        raise SixStatePhysicalError("physical result adjudication_errors malformed")
    if root["outcome"] == "complete_pass":
        if (posts, arms, executes) != (2, 1, 1) or gets < 7:
            raise SixStatePhysicalError("complete result lacks the one ARM/EXECUTE and GET evidence")
        if any(device[key] is None for key in ("arm_response", "armed_status", "terminal_status", "terminal_report")):
            raise SixStatePhysicalError("complete result is missing device evidence")
        arm_nonce = _validate_arm_response(context, device["arm_response"], ordinal=ordinal, boot_nonce=root["boot_nonce"])
        _validate_status(context, device["armed_status"], expected_ordinal=ordinal, phase="armed", boot_nonce=root["boot_nonce"])
        if device["execute_response"] is not None:
            _validate_execute_response(context, device["execute_response"], ordinal=ordinal, boot_nonce=root["boot_nonce"])
        elif not any(str(item).startswith("EXECUTE reply unavailable:") for item in device["adjudication_errors"]):
            raise SixStatePhysicalError("missing EXECUTE reply lacks explicit transport-uncertainty evidence")
        _validate_status(context, device["terminal_status"], expected_ordinal=ordinal, phase="terminal", boot_nonce=root["boot_nonce"])
        _validate_terminal_report(context, device["terminal_report"], ordinal=ordinal, boot_nonce=root["boot_nonce"])
        if _NONCE_RE.fullmatch(arm_nonce) is None:
            raise SixStatePhysicalError("complete result ARM nonce malformed")
    return dict(root)


def _result_reference(context: ReleaseContext, result_file: Path, *, ordinal: int, claim_registry: Path) -> dict[str, Any]:
    result = validate_result(context, result_file, claim_registry=claim_registry)
    if result["ordinal"] != ordinal or result["outcome"] != "complete_pass":
        raise SixStatePhysicalError(f"required prior ordinal {ordinal} result is not complete_pass")
    payload = _read_regular(Path(result_file), label=f"ordinal {ordinal} prior result", maximum=MAX_JSON_BYTES)
    return {
        "file": str(Path(result_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": result["integrity"]["canonical_sha256"],
        "ordinal": ordinal,
        "action_id": result["action_id"],
        "outcome": result["outcome"],
        "completed_at": result["completed_at"],
    }


def _validate_observation(
    context: ReleaseContext,
    observation_file: Path,
    *,
    expected_ordinal: int,
    expected_role: str,
    prior_result_file: Path,
    claim_registry: Path,
) -> dict[str, Any]:
    root, payload = _read_json(Path(observation_file), label=f"finalized {expected_role} observation")
    _keys(
        root,
        {"schema_version", "kind", "release_canonical_sha256", "candidate_id", "panel", "action", "result", "point_evidence", "observation", "gates", "reviewer", "integrity"},
        label="finalized observation",
    )
    if root["schema_version"] != 1 or root["kind"] != OBSERVATION_KIND:
        raise SixStatePhysicalError("unsupported finalized observation")
    _validate_integrity(root, label="finalized observation")
    if root["release_canonical_sha256"] != context.release_canonical_sha256 or root["candidate_id"] != context.candidate_id or root["panel"] != dict(context.panel):
        raise SixStatePhysicalError("finalized observation binding mismatch")
    action = _action(context, expected_ordinal)
    if action["role"] != expected_role or root["action"] != dict(action):
        raise SixStatePhysicalError("finalized observation action mismatch")
    result_ref = _result_reference(context, prior_result_file, ordinal=expected_ordinal, claim_registry=claim_registry)
    if root["result"] != result_ref:
        raise SixStatePhysicalError("finalized observation result reference mismatch")
    point_evidence = root["point_evidence"]
    expected_point_names = ("hold_0min", "hold_5min", "hold_30min") if expected_role == "target" else ("white_recovery",)
    if not isinstance(point_evidence, list) or len(point_evidence) != len(expected_point_names):
        raise SixStatePhysicalError("finalized observation point evidence count mismatch")
    # The final artifact binds exact immutable point bytes.  Re-open every
    # absolute file and replay its result/action/time/ROI contract.
    replayed_points: list[dict[str, Any]] = []
    for reference, point_name in zip(point_evidence, expected_point_names):
        if not isinstance(reference, Mapping) or not isinstance(reference.get("file"), str):
            raise SixStatePhysicalError("finalized observation point reference is malformed")
        replayed = _validate_observation_point(
            context,
            Path(reference["file"]),
            result_file=prior_result_file,
            expected_point=point_name,
            claim_registry=claim_registry,
        )
        if reference != replayed:
            raise SixStatePhysicalError("finalized observation point bytes changed")
        replayed_points.append(replayed)
    for index in range(1, len(replayed_points)):
        if replayed_points[index]["prior_point"] != replayed_points[index - 1]:
            raise SixStatePhysicalError("finalized observation point chain mismatch")
    completed = _timestamp(result_ref["completed_at"], label="observation result completed_at")
    observation = root["observation"]
    if expected_role == "target":
        detail = _keys(observation, {"type", "holds", "preview_match", "left_right_pairs_match", "all_twelve_rois_reviewed", "rois", "no_old_image_residual"}, label="target observation")
        if detail["type"] != "target_hold_review":
            raise SixStatePhysicalError("target observation type mismatch")
        for key in ("preview_match", "left_right_pairs_match", "all_twelve_rois_reviewed", "no_old_image_residual"):
            _boolean(detail[key], True, label=f"target observation.{key}")
        holds = detail["holds"]
        if not isinstance(holds, list) or len(holds) != 3:
            raise SixStatePhysicalError("target observation must contain 0/5/30 minute holds")
        for index, (hold, elapsed) in enumerate(zip(holds, (0, 5, 30))):
            item = _keys(hold, {"label", "elapsed_minutes", "observed_at", "visual_stable", "electrical_normal", "temperature_c", "esp32_not_restarted", "no_uncommanded_refresh"}, label=f"target hold {elapsed}")
            if item["label"] != f"hold_{elapsed}min" or item["elapsed_minutes"] != elapsed:
                raise SixStatePhysicalError("target hold labels/elapsed values are not frozen")
            observed = _timestamp(item["observed_at"], label=f"target hold {elapsed}.observed_at")
            if observed < completed + timedelta(minutes=elapsed):
                raise SixStatePhysicalError(f"target hold {elapsed} was finalized too early")
            for key in ("visual_stable", "electrical_normal", "esp32_not_restarted", "no_uncommanded_refresh"):
                _boolean(item[key], True, label=f"target hold {elapsed}.{key}")
            _number(item["temperature_c"], label=f"target hold {elapsed}.temperature_c", minimum=MIN_TEMPERATURE_C, maximum=MAX_TEMPERATURE_C)
        rois = detail["rois"]
        if not isinstance(rois, list) or len(rois) != 12:
            raise SixStatePhysicalError("target observation must review all twelve ROIs")
        expected_rois = asset_tool.frozen_rois(FROZEN_VARIANTS[context.candidate_id]["candidate_code"])
        for index, (review, frozen) in enumerate(zip(rois, expected_rois)):
            expected_review = {
                "roi_id": frozen["roi_id"],
                "controller": frozen["controller"],
                "initial_code": frozen["initial_code"],
                "target_code": frozen["target_code"],
                "visible": True,
                "appearance_recorded": True,
            }
            if review != expected_review:
                raise SixStatePhysicalError(f"target ROI review {index} mismatch")
    elif expected_role == "white":
        detail = _keys(observation, {"type", "observed_at", "uniform_white", "no_old_image_residual", "electrical_normal", "temperature_c", "esp32_not_restarted", "no_uncommanded_refresh"}, label="white recovery observation")
        if detail["type"] != "white_recovery" or _timestamp(detail["observed_at"], label="white recovery observed_at") < completed:
            raise SixStatePhysicalError("white recovery observation type/time mismatch")
        for key in ("uniform_white", "no_old_image_residual", "electrical_normal", "esp32_not_restarted", "no_uncommanded_refresh"):
            _boolean(detail[key], True, label=f"white recovery.{key}")
        _number(detail["temperature_c"], label="white recovery.temperature_c", minimum=MIN_TEMPERATURE_C, maximum=MAX_TEMPERATURE_C)
    else:
        raise SixStatePhysicalError("only target and white observations can be finalized")
    gates = _keys(root["gates"], {"role", "observation_pass", "electrical_normal", "temperature_normal", "esp32_not_restarted", "no_uncommanded_refresh", "review_pass"}, label="finalized observation.gates")
    if gates["role"] != expected_role:
        raise SixStatePhysicalError("finalized observation gate role mismatch")
    for key in ("observation_pass", "electrical_normal", "temperature_normal", "esp32_not_restarted", "no_uncommanded_refresh", "review_pass"):
        _boolean(gates[key], True, label=f"finalized observation.gates.{key}")
    reviewer = _keys(root["reviewer"], {"name", "reviewed_at"}, label="finalized observation.reviewer")
    _string(reviewer["name"], label="finalized observation reviewer")
    _timestamp(reviewer["reviewed_at"], label="finalized observation reviewed_at")
    return {
        "file": str(Path(observation_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": root["integrity"]["canonical_sha256"],
        "ordinal": expected_ordinal,
        "role": expected_role,
        "review_pass": True,
    }


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SixStatePhysicalError("internal timestamp lacks timezone")
    return value.isoformat(timespec="seconds")


def _prepare_prerequisites(
    context: ReleaseContext,
    ordinal: int,
    *,
    prior_result_file: Path | None,
    prior_target_observation_file: Path | None,
    prior_white_recovery_file: Path | None,
    stage_a_evidence: Mapping[str, Path | None],
    claim_registry: Path,
    now: datetime,
) -> dict[str, Any]:
    """Validate every local gate before any claim or network operation."""

    action = _action(context, ordinal)
    if not context.panel_verified or context.panel_file is None:
        raise SixStatePhysicalError("physical execution requires a verified live panel identity")
    stage_a = _validate_stage_a_gate(context, stage_a_evidence)
    prerequisites: dict[str, Any] = {
        "prior_result": None,
        "target_observation": None,
        "white_recovery": None,
        "stage_a_u07": stage_a,
    }
    if ordinal == 1:
        if prior_result_file is not None or prior_target_observation_file is not None or prior_white_recovery_file is not None:
            raise SixStatePhysicalError("ordinal 1 must not receive prior Stage-B evidence")
    else:
        if prior_result_file is None:
            raise SixStatePhysicalError(f"ordinal {ordinal} requires --prior-result for ordinal {ordinal - 1}")
        prior = _result_reference(context, Path(prior_result_file), ordinal=ordinal - 1, claim_registry=claim_registry)
        completed = _timestamp(prior["completed_at"], label="prior result completed_at")
        if now.tzinfo is None or now.utcoffset() is None:
            raise SixStatePhysicalError("current wall clock lacks a timezone")
        elapsed = (now.astimezone(timezone.utc) - completed.astimezone(timezone.utc)).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            raise SixStatePhysicalError(
                f"host wall-clock cooldown has only {max(0.0, elapsed):.3f}s; {COOLDOWN_SECONDS}s required"
            )
        prerequisites["prior_result"] = prior

    if action["role"] == "white":
        if prior_target_observation_file is None or prior_result_file is None:
            raise SixStatePhysicalError("white action requires the immediately preceding finalized target observation")
        prerequisites["target_observation"] = _validate_observation(
            context,
            Path(prior_target_observation_file),
            expected_ordinal=ordinal - 1,
            expected_role="target",
            prior_result_file=Path(prior_result_file),
            claim_registry=claim_registry,
        )
        if prior_white_recovery_file is not None:
            raise SixStatePhysicalError("white action must not use a prior white-recovery artifact")
    elif action["role"] == "primer" and ordinal > 1:
        if prior_white_recovery_file is None or prior_result_file is None:
            raise SixStatePhysicalError("next-round primer requires the immediately preceding finalized white recovery")
        prerequisites["white_recovery"] = _validate_observation(
            context,
            Path(prior_white_recovery_file),
            expected_ordinal=ordinal - 1,
            expected_role="white",
            prior_result_file=Path(prior_result_file),
            claim_registry=claim_registry,
        )
        if prior_target_observation_file is not None:
            raise SixStatePhysicalError("primer action must not use a target-observation artifact")
    elif prior_target_observation_file is not None or prior_white_recovery_file is not None:
        raise SixStatePhysicalError("selected action received an inapplicable finalized observation")
    return prerequisites


_OBSERVATION_CONFIRMATIONS = {
    "visual_stable",
    "preview_match",
    "all_twelve_rois_reviewed",
    "left_right_pairs_match",
    "no_old_image_residual",
    "uniform_white",
    "electrical_normal",
    "esp32_not_restarted",
    "no_uncommanded_refresh",
}


def _validate_observation_point(
    context: ReleaseContext,
    point_file: Path,
    *,
    result_file: Path,
    expected_point: str,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
) -> dict[str, Any]:
    root, payload = _read_json(Path(point_file), label=f"observation point {expected_point}")
    _keys(root, {"schema_version", "kind", "release_canonical_sha256", "candidate_id", "panel", "action", "result", "point", "captured_at", "temperature_c", "confirmations", "rois", "prior_point", "integrity"}, label="observation point")
    if root["schema_version"] != 1 or root["kind"] != OBSERVATION_POINT_KIND:
        raise SixStatePhysicalError("unsupported observation point artifact")
    _validate_integrity(root, label="observation point")
    if root["release_canonical_sha256"] != context.release_canonical_sha256 or root["candidate_id"] != context.candidate_id or root["panel"] != dict(context.panel):
        raise SixStatePhysicalError("observation point release/candidate/panel binding mismatch")
    result = validate_result(context, Path(result_file), claim_registry=claim_registry)
    if result["outcome"] != "complete_pass":
        raise SixStatePhysicalError("observation point result is not complete_pass")
    action = _action(context, result["ordinal"])
    if root["action"] != dict(action) or root["result"] != _result_reference(context, Path(result_file), ordinal=result["ordinal"], claim_registry=claim_registry):
        raise SixStatePhysicalError("observation point action/result binding mismatch")
    if root["point"] != expected_point:
        raise SixStatePhysicalError("observation point label mismatch")
    captured = _timestamp(root["captured_at"], label="observation point.captured_at")
    completed = _timestamp(result["completed_at"], label="observation point result completed_at")
    elapsed_required = {"hold_0min": 0, "hold_5min": 5, "hold_30min": 30, "white_recovery": 0}.get(expected_point)
    if elapsed_required is None or captured < completed + timedelta(minutes=elapsed_required):
        raise SixStatePhysicalError("observation point was captured before its real hold deadline")
    _number(root["temperature_c"], label="observation point.temperature_c", minimum=MIN_TEMPERATURE_C, maximum=MAX_TEMPERATURE_C)
    confirmations = _keys(root["confirmations"], set(_OBSERVATION_CONFIRMATIONS), label="observation point.confirmations")
    for key, value in confirmations.items():
        _boolean(value, True, label=f"observation point.confirmations.{key}")
    frozen_rois = asset_tool.frozen_rois(FROZEN_VARIANTS[context.candidate_id]["candidate_code"])
    expected_rois = [
        {"roi_id": roi["roi_id"], "controller": roi["controller"], "initial_code": roi["initial_code"], "target_code": roi["target_code"], "visible": True, "appearance_recorded": True}
        for roi in frozen_rois
    ] if action["role"] == "target" else []
    if root["rois"] != expected_rois:
        raise SixStatePhysicalError("observation point ROI list differs from the true frozen row order")
    return {
        "file": str(Path(point_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": root["integrity"]["canonical_sha256"],
        "point": expected_point,
        "captured_at": root["captured_at"],
        "temperature_c": float(root["temperature_c"]),
        "prior_point": root["prior_point"],
    }


def record_observation_point(
    context: ReleaseContext,
    *,
    result_file: Path,
    point: str,
    temperature_c: float,
    output_file: Path,
    prior_point_file: Path | None,
    confirmations: Mapping[str, bool],
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    _utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Capture one immutable hold point using host time; timestamps are not input."""

    if not context.panel_verified:
        raise SixStatePhysicalError("observation capture requires a verified panel")
    if not isinstance(confirmations, Mapping) or set(confirmations) != _OBSERVATION_CONFIRMATIONS:
        raise SixStatePhysicalError("observation confirmation fields differ")
    for key, value in confirmations.items():
        _boolean(value, True, label=f"observation confirmation {key}")
    result = validate_result(context, Path(result_file), claim_registry=claim_registry)
    if result["outcome"] != "complete_pass":
        raise SixStatePhysicalError("only a complete-pass result may be observed")
    action = _action(context, result["ordinal"])
    allowed = ("hold_0min", "hold_5min", "hold_30min") if action["role"] == "target" else (("white_recovery",) if action["role"] == "white" else ())
    if point not in allowed:
        raise SixStatePhysicalError(f"point {point!r} is not valid for role {action['role']}")
    required_prior = {"hold_0min": None, "hold_5min": "hold_0min", "hold_30min": "hold_5min", "white_recovery": None}[point]
    prior_ref: dict[str, Any] | None = None
    if required_prior is None:
        if prior_point_file is not None:
            raise SixStatePhysicalError(f"{point} must not receive a prior point")
    else:
        if prior_point_file is None:
            raise SixStatePhysicalError(f"{point} requires the immutable {required_prior} point")
        prior_ref = _validate_observation_point(context, Path(prior_point_file), result_file=Path(result_file), expected_point=required_prior, claim_registry=claim_registry)
    now = _utcnow()
    if now.tzinfo is None or now.utcoffset() is None:
        raise SixStatePhysicalError("host observation clock lacks a timezone")
    completed = _timestamp(result["completed_at"], label="observation result completed_at")
    elapsed = {"hold_0min": 0, "hold_5min": 5, "hold_30min": 30, "white_recovery": 0}[point]
    if now < completed + timedelta(minutes=elapsed):
        raise SixStatePhysicalError(f"{point} cannot be captured before completion + {elapsed} minutes")
    if prior_ref is not None:
        prior_time = _timestamp(prior_ref["captured_at"], label="prior observation captured_at")
        required_gap_minutes = 5 if point == "hold_5min" else 25
        if now < prior_time + timedelta(minutes=required_gap_minutes):
            raise SixStatePhysicalError(
                f"{point} requires {required_gap_minutes} real minutes after its prior immutable point"
            )
    temperature = _number(temperature_c, label="observation temperature_c", minimum=MIN_TEMPERATURE_C, maximum=MAX_TEMPERATURE_C)
    frozen_rois = asset_tool.frozen_rois(FROZEN_VARIANTS[context.candidate_id]["candidate_code"])
    rois = [
        {"roi_id": roi["roi_id"], "controller": roi["controller"], "initial_code": roi["initial_code"], "target_code": roi["target_code"], "visible": True, "appearance_recorded": True}
        for roi in frozen_rois
    ] if action["role"] == "target" else []
    unsigned = {
        "schema_version": 1,
        "kind": OBSERVATION_POINT_KIND,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "action": dict(action),
        "result": _result_reference(context, Path(result_file), ordinal=result["ordinal"], claim_registry=claim_registry),
        "point": point,
        "captured_at": _utc_text(now),
        "temperature_c": temperature,
        "confirmations": dict(confirmations),
        "rois": rois,
        "prior_point": prior_ref,
    }
    artifact = _seal(unsigned)
    _write_new(Path(output_file), artifact)
    _validate_observation_point(context, Path(output_file), result_file=Path(result_file), expected_point=point, claim_registry=claim_registry)
    return artifact


def finalize_observation(
    context: ReleaseContext,
    *,
    result_file: Path,
    point_files: Sequence[Path],
    output_file: Path,
    reviewer: str,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    _utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Finalize only already-recorded immutable points; no timestamp is accepted."""

    if not context.panel_verified or reviewer != "Ye":
        raise SixStatePhysicalError("finalization requires verified panel and reviewer Ye")
    result = validate_result(context, Path(result_file), claim_registry=claim_registry)
    if result["outcome"] != "complete_pass":
        raise SixStatePhysicalError("only a complete-pass action result can be finalized")
    ordinal = result["ordinal"]
    action = _action(context, ordinal)
    expected_points = ("hold_0min", "hold_5min", "hold_30min") if action["role"] == "target" else (("white_recovery",) if action["role"] == "white" else ())
    if len(point_files) != len(expected_points):
        raise SixStatePhysicalError(f"role {action['role']} requires points {expected_points}")
    point_refs = [
        _validate_observation_point(context, Path(path), result_file=Path(result_file), expected_point=point, claim_registry=claim_registry)
        for path, point in zip(point_files, expected_points)
    ]
    for index in range(1, len(point_refs)):
        if point_refs[index]["prior_point"] != point_refs[index - 1]:
            raise SixStatePhysicalError("observation point chain does not bind exact preceding bytes")
    if action["role"] == "target":
        point_times = [
            _timestamp(reference["captured_at"], label=f"point {index} captured_at")
            for index, reference in enumerate(point_refs)
        ]
        if point_times[1] < point_times[0] + timedelta(minutes=5) or point_times[2] < point_times[0] + timedelta(minutes=30):
            raise SixStatePhysicalError("immutable target points compress the real 0/5/30-minute span")
    reviewed = _utcnow()
    if reviewed.tzinfo is None or reviewed.utcoffset() is None or reviewed < _timestamp(point_refs[-1]["captured_at"], label="last point captured_at"):
        raise SixStatePhysicalError("review host time predates the last immutable point")
    result_ref = _result_reference(context, Path(result_file), ordinal=ordinal, claim_registry=claim_registry)
    if action["role"] == "target":
        frozen_rois = asset_tool.frozen_rois(FROZEN_VARIANTS[context.candidate_id]["candidate_code"])
        detail: dict[str, Any] = {
            "type": "target_hold_review",
            "holds": [
                {"label": f"hold_{elapsed}min", "elapsed_minutes": elapsed, "observed_at": point_ref["captured_at"], "visual_stable": True, "electrical_normal": True, "temperature_c": point_ref["temperature_c"], "esp32_not_restarted": True, "no_uncommanded_refresh": True}
                for elapsed, point_ref in zip((0, 5, 30), point_refs)
            ],
            "preview_match": True,
            "left_right_pairs_match": True,
            "all_twelve_rois_reviewed": True,
            "rois": [
                {"roi_id": roi["roi_id"], "controller": roi["controller"], "initial_code": roi["initial_code"], "target_code": roi["target_code"], "visible": True, "appearance_recorded": True}
                for roi in frozen_rois
            ],
            "no_old_image_residual": True,
        }
    elif action["role"] == "white":
        detail = {"type": "white_recovery", "observed_at": point_refs[0]["captured_at"], "uniform_white": True, "no_old_image_residual": True, "electrical_normal": True, "temperature_c": point_refs[0]["temperature_c"], "esp32_not_restarted": True, "no_uncommanded_refresh": True}
    else:
        raise SixStatePhysicalError("primer results do not have a finalized observation")
    unsigned = {
        "schema_version": 1,
        "kind": OBSERVATION_KIND,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "action": dict(action),
        "result": result_ref,
        "point_evidence": point_refs,
        "observation": detail,
        "gates": {"role": action["role"], "observation_pass": True, "electrical_normal": True, "temperature_normal": True, "esp32_not_restarted": True, "no_uncommanded_refresh": True, "review_pass": True},
        "reviewer": {"name": reviewer, "reviewed_at": _utc_text(reviewed)},
    }
    artifact = _seal(unsigned)
    _write_new(Path(output_file), artifact)
    _validate_observation(
        context,
        Path(output_file),
        expected_ordinal=ordinal,
        expected_role=str(action["role"]),
        prior_result_file=Path(result_file),
        claim_registry=claim_registry,
    )
    return artifact


def _check_execution_paths(result_file: Path, claim_registry: Path, action_id: str) -> None:
    result_file = Path(result_file)
    if result_file.exists() or result_file.is_symlink():
        raise SixStatePhysicalError("result file already exists; refusing to overwrite it")
    try:
        if result_file.parent.is_symlink() or not result_file.parent.is_dir():
            raise SixStatePhysicalError("result parent must be an existing non-symlink directory")
        registry = Path(claim_registry)
        if registry.exists():
            if registry.is_symlink() or not registry.is_dir():
                raise SixStatePhysicalError("claim registry must be a non-symlink directory")
            if _claim_path(registry, action_id).exists() or _claim_path(registry, action_id).is_symlink():
                raise SixStatePhysicalError(f"action {action_id} already has a permanent host claim")
        elif registry.parent.is_symlink() or not registry.parent.is_dir():
            raise SixStatePhysicalError("claim registry parent must be an existing non-symlink directory")
    except OSError as error:
        raise SixStatePhysicalError(f"cannot validate execution paths: {error}") from error


def _mutation_headers(
    context: ReleaseContext,
    ordinal: int,
    *,
    boot_nonce: str,
    intent: str,
    arm_nonce: str | None = None,
) -> dict[str, str]:
    action = _action(context, ordinal)
    headers = {
        "X-EC5-Build-Tag": str(context.variant["build_tag"]),
        "X-EC5-Test-Id": str(context.variant["test_id"]),
        "X-EC5-Action-Id": str(action["action_id"]),
        "X-EC5-Ordinal": str(ordinal),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _poll_terminal(
    context: ReleaseContext,
    base_url: str,
    *,
    ordinal: int,
    boot_nonce: str,
    timeout: float,
    poll_count: int,
    poll_interval_seconds: float,
    urlopen: Callable[..., Any],
    sleep: Callable[[float], None],
    errors: list[str],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, bool]:
    last_status: Mapping[str, Any] | None = None
    last_report: Mapping[str, Any] | None = None
    for poll_index in range(poll_count):
        try:
            last_status, last_report = _get_snapshot(
                context, base_url, timeout=timeout, urlopen=urlopen
            )
            try:
                terminal_status = _validate_status(
                    context,
                    last_status,
                    expected_ordinal=ordinal,
                    phase="terminal",
                    boot_nonce=boot_nonce,
                )
                terminal_report = _validate_terminal_report(
                    context,
                    last_report,
                    ordinal=ordinal,
                    boot_nonce=boot_nonce,
                )
                return terminal_status, terminal_report, True
            except SixStatePhysicalError as validation_error:
                errors.append(f"terminal poll {poll_index + 1}: {validation_error}")
                if isinstance(last_status, Mapping) and last_status.get("state") == "fault_locked":
                    return last_status, last_report, False
        except SixStatePhysicalError as request_error:
            errors.append(f"terminal poll {poll_index + 1} GET unavailable: {request_error}")
        if poll_index + 1 < poll_count and poll_interval_seconds > 0:
            sleep(poll_interval_seconds)
    return last_status, last_report, False


def run_once(
    context: ReleaseContext,
    base_url: str,
    ordinal: int,
    *,
    authorization: str,
    result_file: Path,
    prior_result_file: Path | None = None,
    prior_target_observation_file: Path | None = None,
    prior_white_recovery_file: Path | None = None,
    stage_a_release_file: Path | None = None,
    stage_a_u04_result_file: Path | None = None,
    stage_a_u04_review_file: Path | None = None,
    stage_a_u04_hold_0_file: Path | None = None,
    stage_a_u04_hold_5_file: Path | None = None,
    stage_a_u04_hold_30_file: Path | None = None,
    stage_a_after_u04_white_result_file: Path | None = None,
    stage_a_u07_result_file: Path | None = None,
    stage_a_u07_hold_0_file: Path | None = None,
    stage_a_u07_hold_5_file: Path | None = None,
    stage_a_u07_hold_30_file: Path | None = None,
    stage_a_after_u07_white_result_file: Path | None = None,
    stage_a_candidate_claim_registry: Path | None = None,
    stage_a_white_claim_registry: Path | None = None,
    stage_a_rc2g_binary_file: Path | None = None,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_count: int = DEFAULT_POLL_COUNT,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    _urlopen: Callable[..., Any] = urllib.request.urlopen,
    _sleep: Callable[[float], None] = time.sleep,
    _utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Execute only ``ordinal``; this function never advances to another action."""

    action = _action(context, ordinal)
    if authorization != required_authorization(context, ordinal):
        raise SixStatePhysicalError("exact action-bound authorization phrase mismatch")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(float(timeout)) or not 0.1 <= float(timeout) <= 60:
        raise SixStatePhysicalError("timeout must be between 0.1 and 60 seconds")
    if isinstance(poll_count, bool) or not isinstance(poll_count, int) or not 1 <= poll_count <= 1000:
        raise SixStatePhysicalError("poll_count must be an integer from 1 through 1000")
    if isinstance(poll_interval_seconds, bool) or not isinstance(poll_interval_seconds, (int, float)) or not math.isfinite(float(poll_interval_seconds)) or not 0 <= float(poll_interval_seconds) <= 60:
        raise SixStatePhysicalError("poll_interval_seconds must be between 0 and 60")
    origin = _base_url(base_url)
    _check_execution_paths(Path(result_file), Path(claim_registry), str(action["action_id"]))
    started = _utcnow()
    if started.tzinfo is None or started.utcoffset() is None:
        raise SixStatePhysicalError("host clock must return a timezone-aware datetime")
    prerequisites = _prepare_prerequisites(
        context,
        ordinal,
        prior_result_file=prior_result_file,
        prior_target_observation_file=prior_target_observation_file,
        prior_white_recovery_file=prior_white_recovery_file,
        stage_a_evidence={
            "release_file": stage_a_release_file,
            "u04_result_file": stage_a_u04_result_file,
            "u04_review_file": stage_a_u04_review_file,
            "u04_hold_0_file": stage_a_u04_hold_0_file,
            "u04_hold_5_file": stage_a_u04_hold_5_file,
            "u04_hold_30_file": stage_a_u04_hold_30_file,
            "after_u04_white_result_file": stage_a_after_u04_white_result_file,
            "u07_result_file": stage_a_u07_result_file,
            "u07_hold_0_file": stage_a_u07_hold_0_file,
            "u07_hold_5_file": stage_a_u07_hold_5_file,
            "u07_hold_30_file": stage_a_u07_hold_30_file,
            "after_u07_white_result_file": stage_a_after_u07_white_result_file,
            "candidate_claim_registry": stage_a_candidate_claim_registry,
            "white_claim_registry": stage_a_white_claim_registry,
            "rc2g_binary_file": stage_a_rc2g_binary_file,
        },
        claim_registry=Path(claim_registry),
        now=started,
    )

    counters = {"GET": 0, "POST": 0, "arm": 0, "execute": 0}

    def counted_open(request: Any, timeout: float) -> Any:
        method = request.get_method()
        if method not in ("GET", "POST"):
            raise SixStatePhysicalError("internal request method is not GET/POST")
        counters[method] += 1
        path = urllib.parse.urlsplit(request.full_url).path
        if method == "POST":
            if path == _ENDPOINTS["arm"]:
                counters["arm"] += 1
                if counters["arm"] > 1:
                    raise SixStatePhysicalError("internal ARM retry prevented")
            elif path == _ENDPOINTS["execute"]:
                counters["execute"] += 1
                if counters["execute"] > 1:
                    raise SixStatePhysicalError("internal EXECUTE retry prevented")
            else:
                raise SixStatePhysicalError("internal unknown mutation route prevented")
        return _urlopen(request, timeout=timeout)

    # All local gates above intentionally precede these four GET-only requests.
    preflight_value = preflight(
        context,
        origin,
        ordinal,
        timeout=float(timeout),
        _urlopen=counted_open,
    )
    attempt_id = uuid.uuid4().hex
    claimed_at = _utc_text(_utcnow())
    claim_path, claim, claim_payload = _create_claim(
        context,
        ordinal,
        registry=Path(claim_registry),
        attempt_id=attempt_id,
        created_at=claimed_at,
        preflight_value=preflight_value,
        prerequisites=prerequisites,
    )

    arm_response: Mapping[str, Any] | None = None
    armed_status: Mapping[str, Any] | None = None
    execute_response: Mapping[str, Any] | None = None
    terminal_status: Mapping[str, Any] | None = None
    terminal_report: Mapping[str, Any] | None = None
    errors: list[str] = []
    terminal_pass = False
    may_execute = True
    try:
        raw_arm = _http_json(
            origin,
            _ENDPOINTS["arm"],
            method="POST",
            headers=_mutation_headers(context, ordinal, boot_nonce=preflight_value.boot_nonce, intent=ARM_INTENT),
            timeout=float(timeout),
            urlopen=counted_open,
        )
        arm_response = raw_arm
        arm_nonce = _validate_arm_response(context, raw_arm, ordinal=ordinal, boot_nonce=preflight_value.boot_nonce)
    except SixStatePhysicalError as error:
        errors.append(f"ARM reply unavailable or invalid: {error}")
        may_execute = False
        arm_nonce = None

    if may_execute:
        try:
            raw_armed_status = _http_json(origin, _ENDPOINTS["status"], method="GET", headers=None, timeout=float(timeout), urlopen=counted_open)
            armed_status = _validate_status(context, raw_armed_status, expected_ordinal=ordinal, phase="armed", boot_nonce=preflight_value.boot_nonce)
        except SixStatePhysicalError as error:
            errors.append(f"armed status unavailable or invalid: {error}")
            may_execute = False

    if may_execute and arm_nonce is not None:
        try:
            raw_execute = _http_json(
                origin,
                _ENDPOINTS["execute"],
                method="POST",
                headers=_mutation_headers(context, ordinal, boot_nonce=preflight_value.boot_nonce, arm_nonce=arm_nonce, intent=EXECUTE_INTENT),
                timeout=float(timeout),
                urlopen=counted_open,
            )
            _validate_execute_response(context, raw_execute, ordinal=ordinal, boot_nonce=preflight_value.boot_nonce)
            execute_response = raw_execute
        except SixStatePhysicalError as error:
            # The POST was sent at most once.  A lost reply may still have
            # consumed/executed it, so only GET evidence can decide now.
            errors.append(f"EXECUTE reply unavailable: {error}")

    terminal_status, terminal_report, terminal_pass = _poll_terminal(
        context,
        origin,
        ordinal=ordinal,
        boot_nonce=preflight_value.boot_nonce,
        timeout=float(timeout),
        poll_count=poll_count,
        poll_interval_seconds=float(poll_interval_seconds),
        urlopen=counted_open,
        sleep=_sleep,
        errors=errors,
    )
    if not may_execute:
        terminal_pass = False
    completed = _utcnow()
    if completed.tzinfo is None or completed.utcoffset() is None or completed < started:
        raise SixStatePhysicalUnknown(
            "host clock invalid after permanent claim; do not retry or recover"
        )
    outcome = "complete_pass" if terminal_pass else "unknown_do_not_retry_or_recover"
    unsigned = {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "ordinal": ordinal,
        "round": action["round"],
        "role": action["role"],
        "action_id": action["action_id"],
        "attempt_id": attempt_id,
        "binary_sha256": context.binary_sha256,
        "asset_manifest_sha256": context.asset_file_sha256,
        "started_at": _utc_text(started),
        "completed_at": _utc_text(completed),
        "base_url": origin,
        "boot_nonce": preflight_value.boot_nonce,
        "claim": _claim_reference(claim_path, claim, claim_payload),
        "prerequisites": prerequisites,
        "network": {
            "get_requests": counters["GET"],
            "post_requests": counters["POST"],
            "arm_posts": counters["arm"],
            "execute_posts": counters["execute"],
            "no_retry": True,
            "no_recovery": True,
        },
        "outcome": outcome,
        "device": {
            "preflight_sha256": preflight_value.digest(),
            "arm_response": arm_response,
            "armed_status": armed_status,
            "execute_response": execute_response,
            "terminal_status": terminal_status,
            "terminal_report": terminal_report,
            "adjudication_errors": errors,
        },
    }
    result = _seal(unsigned)
    _write_new(Path(result_file), result)
    validate_result(context, Path(result_file), claim_registry=Path(claim_registry))
    return result


def describe(context: ReleaseContext, ordinal: int) -> dict[str, Any]:
    action = _action(context, ordinal)
    return {
        "schema_version": 1,
        "kind": RELEASE_KIND,
        "release_canonical_sha256": context.release_canonical_sha256,
        "candidate_id": context.candidate_id,
        "panel": dict(context.panel),
        "panel_verified": context.panel_verified,
        "binary": {"file": str(context.binary_path), "sha256": context.binary_sha256},
        "assets": {"manifest": str(context.asset_manifest_path), "sha256": context.asset_file_sha256},
        "selected_action": dict(action),
        "authorization": required_authorization(context, ordinal),
        "visible_refreshes_this_invocation": 0,
        "network_requests": 0,
        "claim_created": False,
        "batch_execution_available": False,
        "u07_stage_a_gate_required": context.candidate_id == "U07",
    }


def _confirmation_arguments(parser: argparse.ArgumentParser) -> None:
    for name in sorted(_OBSERVATION_CONFIRMATIONS):
        parser.add_argument(f"--confirm-{name.replace('_', '-')}", action="store_true")


def _confirmations_from_args(args: argparse.Namespace) -> dict[str, bool]:
    return {name: bool(getattr(args, f"confirm_{name}")) for name in _OBSERVATION_CONFIRMATIONS}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("describe", "preflight", "run", "validate", "record-observation", "finalize-observation"):
        item = sub.add_parser(name, allow_abbrev=False)
        item.add_argument("--release", type=Path, required=True)
        item.add_argument("--candidate", choices=("U04", "U07"), required=True)
        item.add_argument("--panel", type=Path, required=True)
        item.add_argument("--source-root", type=Path, default=REPO_ROOT)
    for name in ("describe", "preflight", "run"):
        sub.choices[name].add_argument("--ordinal", type=int, required=True)
    sub.choices["preflight"].add_argument("--base-url", required=True)

    run = sub.choices["run"]
    run.add_argument("--base-url", required=True)
    run.add_argument("--authorization", required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    run.add_argument("--prior-result", type=Path)
    run.add_argument("--prior-target-observation", type=Path)
    run.add_argument("--prior-white-recovery", type=Path)
    for option in (
        "release",
        "u04-result",
        "u04-review",
        "u04-hold-0",
        "u04-hold-5",
        "u04-hold-30",
        "after-u04-white-result",
        "u07-result",
        "u07-hold-0",
        "u07-hold-5",
        "u07-hold-30",
        "after-u07-white-result",
        "candidate-claim-registry",
        "white-claim-registry",
        "rc2g-binary",
    ):
        run.add_argument(f"--stage-a-{option}", type=Path)
    run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--poll-count", type=int, default=DEFAULT_POLL_COUNT)
    run.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)

    validate = sub.choices["validate"]
    validate.add_argument("--result", type=Path, required=True)
    validate.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)

    record = sub.choices["record-observation"]
    record.add_argument("--result", type=Path, required=True)
    record.add_argument("--point", choices=("hold_0min", "hold_5min", "hold_30min", "white_recovery"), required=True)
    record.add_argument("--temperature-c", type=float, required=True)
    record.add_argument("--prior-point", type=Path)
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    _confirmation_arguments(record)

    finalize = sub.choices["finalize-observation"]
    finalize.add_argument("--result", type=Path, required=True)
    finalize.add_argument("--point", type=Path, action="append", required=True)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.add_argument("--reviewer", required=True)
    finalize.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        context = load_release(
            args.release,
            args.candidate,
            source_root=args.source_root,
            panel_file=args.panel,
        )
        if args.command == "describe":
            output = describe(context, args.ordinal)
        elif args.command == "preflight":
            checked = preflight(context, args.base_url, args.ordinal)
            output = {
                "valid": True,
                "candidate_id": context.candidate_id,
                "ordinal": args.ordinal,
                "boot_nonce": checked.boot_nonce,
                "preflight_sha256": checked.digest(),
                "post_requests": 0,
                "claim_created": False,
            }
        elif args.command == "run":
            output = run_once(
                context,
                args.base_url,
                args.ordinal,
                authorization=args.authorization,
                result_file=args.result,
                prior_result_file=args.prior_result,
                prior_target_observation_file=args.prior_target_observation,
                prior_white_recovery_file=args.prior_white_recovery,
                stage_a_release_file=args.stage_a_release,
                stage_a_u04_result_file=args.stage_a_u04_result,
                stage_a_u04_review_file=args.stage_a_u04_review,
                stage_a_u04_hold_0_file=args.stage_a_u04_hold_0,
                stage_a_u04_hold_5_file=args.stage_a_u04_hold_5,
                stage_a_u04_hold_30_file=args.stage_a_u04_hold_30,
                stage_a_after_u04_white_result_file=args.stage_a_after_u04_white_result,
                stage_a_u07_result_file=args.stage_a_u07_result,
                stage_a_u07_hold_0_file=args.stage_a_u07_hold_0,
                stage_a_u07_hold_5_file=args.stage_a_u07_hold_5,
                stage_a_u07_hold_30_file=args.stage_a_u07_hold_30,
                stage_a_after_u07_white_result_file=args.stage_a_after_u07_white_result,
                stage_a_candidate_claim_registry=args.stage_a_candidate_claim_registry,
                stage_a_white_claim_registry=args.stage_a_white_claim_registry,
                stage_a_rc2g_binary_file=args.stage_a_rc2g_binary,
                claim_registry=args.claim_registry,
                timeout=args.timeout,
                poll_count=args.poll_count,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        elif args.command == "validate":
            result = validate_result(context, args.result, claim_registry=args.claim_registry)
            output = {"valid": True, "outcome": result["outcome"], "ordinal": result["ordinal"], "action_id": result["action_id"]}
        elif args.command == "record-observation":
            output = record_observation_point(
                context,
                result_file=args.result,
                point=args.point,
                temperature_c=args.temperature_c,
                output_file=args.output,
                prior_point_file=args.prior_point,
                confirmations=_confirmations_from_args(args),
                claim_registry=args.claim_registry,
            )
        else:
            output = finalize_observation(
                context,
                result_file=args.result,
                point_files=args.point,
                output_file=args.output,
                reviewer=args.reviewer,
                claim_registry=args.claim_registry,
            )
    except SixStatePhysicalError as error:
        print(f"EC5 six-state physical error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
