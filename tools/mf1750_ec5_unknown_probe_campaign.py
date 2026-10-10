#!/usr/bin/env python3
"""Compile the fixed EC5 U04/white/single-pilot contract offline.

This tool materializes no device command and grants no hardware authority.  It
only binds the frozen U04 fixture to one panel identity, one single-candidate
build sidecar, and the actual firmware bytes.  U07 is deliberately a separate,
deferred design identity and cannot be compiled by this module.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    ROW_BYTES,
    WIDTH,
    controller_stream,
    fnv1a,
)
from host.extended_color.offline import (  # noqa: E402
    DEFAULT_CONTROLLER_MAPPINGS,
    generate_unknown_probe_frame,
    unknown_probe_rois,
    validate_unknown_probe_frame,
)


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u04-white-pilot-campaign"
BUILD_SIDECAR_KIND = "mf1750-ec5-single-candidate-build-sidecar"
LAYOUT_ID = "EC5_MIRROR64_CENTER_V1"
TEST_ID = "EC5-U04-I01-P01-L64M1"
U04_CODE = 0x4
WHITE_CODE = 0x1
DESIGN_DOCUMENT = "docs/UNKNOWN_CODE_EXPERIMENT_DESIGN_2026-08-05.md"
DESIGN_DOCUMENT_SHA256 = (
    "80bcf14100722cb51338e65ce942ca40fe5138283341f3c1e7d3c9284b9e9459"
)
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_FIRMWARE_BYTES = 32 * 1024 * 1024
HASH_SCOPE = (
    "entire EC5 U04 campaign excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)

U04_FRAME_SHA256 = (
    "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e"
)
U04_FRAME_FNV1A = 0x68533DC5
U04_DTM_SHA256 = (
    "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00"
)
U04_DTM_FNV1A = 0x15B7EDC5

U07_DESIGN_IDENTITY = {
    "candidate_id": "U07",
    "candidate_code": 0x7,
    "frame_sha256": (
        "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e"
    ),
    "cs1_dtm_sha256": (
        "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac"
    ),
    "cs2_dtm_sha256": (
        "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac"
    ),
    "materialization_state": "DEFERRED_SEPARATE_BUILD_REVIEW_AND_AUTHORIZATION",
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,127})\Z")
_PLACEHOLDER_RE = re.compile(
    r"(?:^|[-_. ])(?:UNBOUND|UNKNOWN|PLACEHOLDER|DRAFT|TBD|NONE|NULL|TEST)"
    r"(?:$|[-_. ])",
    re.IGNORECASE,
)
_PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
_BUILD_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "candidate_id",
        "candidate_code",
        "build_tag",
        "firmware_commit",
        "git_dirty",
        "binary_sha256",
        "config_sha256",
        "driver_baseline_commit",
        "command_sequence_digest",
        "otp_mode",
        "created_at",
        "review_id",
        "manifest_payload_sha256",
        "isolation",
    }
)
_ISOLATION_KEYS = frozenset(
    {
        "single_candidate_binary",
        "embedded_candidate_codes",
        "candidate_fixture_count",
        "contains_u07_fixture",
        "formal_six_color_guard_unchanged",
        "arbitrary_unknown_input_enabled",
        "unknown_spi_command_added",
        "waveform_modified",
    }
)
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "source",
        "fixture_manifest",
        "physical_binding",
        "actions",
        "manual_observation_contract",
        "pilot_contract",
        "classification",
        "integrity",
    }
)
_SOURCE_KEYS = frozenset({"design_document", "design_document_sha256", "stage"})
_FIXTURE_KEYS = frozenset(
    {
        "payload",
        "manifest_payload_sha256",
        "binary_sha256_excluded_to_avoid_self_reference",
    }
)
_BINDING_KEYS = frozenset(
    {
        "panel",
        "panel_file_sha256",
        "build_sidecar",
        "build_sidecar_sha256",
        "firmware_binary_sha256",
    }
)
_OBSERVATION_WRAPPER_KEYS = frozenset({"contract", "canonical_sha256"})
_ACTION_KEYS = frozenset(
    {
        "ordinal",
        "test_id",
        "candidate_id",
        "candidate_code",
        "intended_initial_code",
        "intended_initial_color",
        "repetition",
        "frame_identity",
        "manual_observation_contract_sha256",
        "body_or_raw_frame_materialized",
        "execution_route_materialized",
        "hardware_execution_authorized",
        "maximum_execute_attempts",
        "retry_allowed",
        "recovery_included",
        "action_identity_sha256",
    }
)


class EC5CampaignError(ValueError):
    """The fixed EC5 campaign or one of its local inputs failed closed."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical JSON encoding used by EC5 identity hashes."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EC5CampaignError(f"value is not canonical JSON data: {error}") from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EC5CampaignError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_regular_file(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    if not isinstance(path, Path):
        raise EC5CampaignError(f"{label} path must be pathlib.Path")
    try:
        if path.is_symlink() or not path.is_file():
            raise EC5CampaignError(f"{label} must be a local regular file")
        before = path.stat()
        if before.st_size > maximum_bytes:
            raise EC5CampaignError(
                f"{label} exceeds the {maximum_bytes}-byte safety limit"
            )
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise EC5CampaignError(f"could not read {label}: {error}") from error
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != after.st_size:
        raise EC5CampaignError(f"{label} changed while it was read")
    return payload


def read_strict_json(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    """Read canonical local JSON while rejecting duplicates and redirects."""

    payload = _read_regular_file(path, label=label, maximum_bytes=MAX_JSON_BYTES)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EC5CampaignError(f"{label} contains forbidden number {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EC5CampaignError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise EC5CampaignError(f"{label} JSON root must be an object")
    if payload != canonical_json_bytes(value):
        raise EC5CampaignError(f"{label} must use canonical JSON bytes")
    return value, payload


def publish_new_json(path: Path, value: Mapping[str, Any], *, label: str) -> str:
    """Publish one canonical JSON file and refuse overwrite."""

    payload = canonical_json_bytes(value)
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise EC5CampaignError(f"{label} parent is unavailable: {error}") from error
    if not parent.is_dir() or path.name in {"", ".", ".."}:
        raise EC5CampaignError(f"{label} must name a new file in an existing directory")
    destination = parent / path.name
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise EC5CampaignError(f"could not publish {label}: {error}") from error
    return sha256(payload)


def _require_exact_mapping(
    value: Any, *, label: str, keys: frozenset[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise EC5CampaignError(f"{label} fields differ from contract")
    return value


def _require_text(value: Any, *, label: str, token: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 256
        or any(ord(character) < 0x20 for character in value)
        or _PLACEHOLDER_RE.search(value) is not None
        or (token and _TOKEN_RE.fullmatch(value) is None)
    ):
        raise EC5CampaignError(f"{label} is blank, placeholder, or malformed")
    return value


def _require_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EC5CampaignError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _parse_rfc3339(value: Any, *, label: str) -> str:
    text = _require_text(value, label=label)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise EC5CampaignError(f"{label} must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EC5CampaignError(f"{label} must include a UTC offset")
    return text


def validate_panel_identity(value: Mapping[str, Any]) -> dict[str, str]:
    panel = _require_exact_mapping(value, label="panel identity", keys=_PANEL_KEYS)
    return {
        field: _require_text(panel[field], label=f"panel identity.{field}")
        for field in ("model", "serial", "board_id", "pcb_revision")
    }


def _mapping_dict(index: int) -> dict[str, Any]:
    mapping = DEFAULT_CONTROLLER_MAPPINGS[index]
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _fixed_rectangles() -> dict[str, dict[str, int]]:
    rois = unknown_probe_rois(U04_CODE)
    return {
        "roi_cs1": rois[0].measurement.to_dict(),
        "roi_cs2": rois[1].measurement.to_dict(),
        "guard_cs1": rois[0].guard_outer.to_dict(),
        "guard_cs2": rois[1].guard_outer.to_dict(),
    }


def build_fixture_manifest_payload(build: Mapping[str, Any]) -> dict[str, Any]:
    """Build the non-self-referential, compile-time U04 fixture payload."""

    rectangles = _fixed_rectangles()
    return {
        "schema_version": SCHEMA_VERSION,
        "layout_id": LAYOUT_ID,
        "test_id": TEST_ID,
        "candidate_code": U04_CODE,
        "intended_initial_code": WHITE_CODE,
        "sequence_class": "single-unknown-fixture-action",
        "repetition": 1,
        "width": WIDTH,
        "height": HEIGHT,
        "frame_bytes": FRAME_BYTES,
        "pixel_packing": "4bpp-high-nibble-left-low-nibble-right",
        **rectangles,
        "known_white_pixels": WIDTH * HEIGHT - 8192,
        "unknown_pixels": 8192,
        "color_histogram": {"0x1": WIDTH * HEIGHT - 8192, "0x4": 8192},
        "frame_sha256": U04_FRAME_SHA256,
        "frame_fnv1a": U04_FRAME_FNV1A,
        "cs1_dtm_sha256": U04_DTM_SHA256,
        "cs1_dtm_fnv1a": U04_DTM_FNV1A,
        "cs2_dtm_sha256": U04_DTM_SHA256,
        "cs2_dtm_fnv1a": U04_DTM_FNV1A,
        "mapping_cs1": _mapping_dict(0),
        "mapping_cs2": _mapping_dict(1),
        "firmware_commit": build["firmware_commit"],
        "build_tag": build["build_tag"],
        "config_sha256": build["config_sha256"],
        "driver_baseline_commit": build["driver_baseline_commit"],
        "command_sequence_digest": build["command_sequence_digest"],
        "otp_mode": build["otp_mode"],
        "created_at": build["created_at"],
        "review_id": build["review_id"],
    }


def validate_build_sidecar(
    value: Mapping[str, Any], firmware_payload: bytes
) -> dict[str, Any]:
    build = _require_exact_mapping(
        value, label="EC5 build sidecar", keys=_BUILD_KEYS
    )
    if build["schema_version"] != SCHEMA_VERSION or build["kind"] != BUILD_SIDECAR_KIND:
        raise EC5CampaignError("EC5 build sidecar type is unsupported")
    if build["candidate_id"] != "U04" or build["candidate_code"] != U04_CODE:
        raise EC5CampaignError("only the isolated U04 build is accepted")
    _require_text(build["build_tag"], label="build_tag", token=True)
    if (
        not isinstance(build["firmware_commit"], str)
        or _COMMIT_RE.fullmatch(build["firmware_commit"]) is None
        or not isinstance(build["driver_baseline_commit"], str)
        or _COMMIT_RE.fullmatch(build["driver_baseline_commit"]) is None
    ):
        raise EC5CampaignError("firmware and driver commits must be lowercase 40-hex")
    if build["git_dirty"] is not False:
        raise EC5CampaignError("EC5 build sidecar must bind a clean firmware tree")
    for field in (
        "binary_sha256",
        "config_sha256",
        "command_sequence_digest",
        "manifest_payload_sha256",
    ):
        _require_sha(build[field], label=field)
    _require_text(build["review_id"], label="review_id", token=True)
    _parse_rfc3339(build["created_at"], label="created_at")
    if build["otp_mode"] != "factory-otp-unchanged":
        raise EC5CampaignError("EC5 pilot must preserve factory OTP mode")
    isolation = _require_exact_mapping(
        build["isolation"], label="build isolation", keys=_ISOLATION_KEYS
    )
    expected_isolation = {
        "single_candidate_binary": True,
        "embedded_candidate_codes": [U04_CODE],
        "candidate_fixture_count": 1,
        "contains_u07_fixture": False,
        "formal_six_color_guard_unchanged": True,
        "arbitrary_unknown_input_enabled": False,
        "unknown_spi_command_added": False,
        "waveform_modified": False,
    }
    if isolation != expected_isolation:
        raise EC5CampaignError("build isolation does not prove a U04-only declaration")
    if sha256(firmware_payload) != build["binary_sha256"]:
        raise EC5CampaignError("actual firmware bytes differ from binary_sha256")
    payload = build_fixture_manifest_payload(build)
    if sha256(payload) != build["manifest_payload_sha256"]:
        raise EC5CampaignError("fixture manifest payload digest is invalid")
    return json.loads(canonical_json_bytes(build).decode("utf-8"))


def _independent_unknown_frame(code: int) -> bytes:
    """Second generator used only to byte-compare the frozen offline fixture."""

    if code not in (U04_CODE, 0x7):
        raise EC5CampaignError("independent EC5 generator accepts only 0x4 or 0x7")
    frame = bytearray(bytes((0x11,)) * FRAME_BYTES)
    value = bytes((((code << 4) | code),))
    rectangles = ((224, 268, 288, 332), (736, 268, 800, 332))
    for x0, y0, x1, y1 in rectangles:
        for y in range(y0, y1):
            start = y * ROW_BYTES + x0 // 2
            end = y * ROW_BYTES + x1 // 2
            frame[start:end] = value * (end - start)
    return bytes(frame)


def _verified_u04_identity() -> dict[str, Any]:
    primary = generate_unknown_probe_frame(U04_CODE)
    independent = _independent_unknown_frame(U04_CODE)
    if primary != independent:
        raise EC5CampaignError("the two independent U04 generators disagree")
    validate_unknown_probe_frame(primary, U04_CODE)
    allowed = (*PHYSICAL_COLOR_CODES, U04_CODE)
    dtms = tuple(
        controller_stream(primary, mapping, allowed_colors=allowed)
        for mapping in DEFAULT_CONTROLLER_MAPPINGS
    )
    full_sha = sha256(primary)
    dtm_shas = tuple(sha256(value) for value in dtms)
    if (
        full_sha != U04_FRAME_SHA256
        or fnv1a(primary) != U04_FRAME_FNV1A
        or dtm_shas != (U04_DTM_SHA256, U04_DTM_SHA256)
        or tuple(fnv1a(value) for value in dtms)
        != (U04_DTM_FNV1A, U04_DTM_FNV1A)
    ):
        raise EC5CampaignError("generated U04 frame/DTM identity is not frozen")
    return {
        "layout_id": LAYOUT_ID,
        "width": WIDTH,
        "height": HEIGHT,
        "frame_bytes": len(primary),
        "frame_sha256": full_sha,
        "frame_fnv1a": fnv1a(primary),
        "cs1_dtm_sha256": dtm_shas[0],
        "cs1_dtm_fnv1a": fnv1a(dtms[0]),
        "cs2_dtm_sha256": dtm_shas[1],
        "cs2_dtm_fnv1a": fnv1a(dtms[1]),
        "mapping_cs1": _mapping_dict(0),
        "mapping_cs2": _mapping_dict(1),
        "generator_agreement": True,
    }


def manual_observation_contract() -> dict[str, Any]:
    """Return the exact manual evidence fields accepted by the analyzer."""

    rectangles = _fixed_rectangles()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-u04-manual-observation-contract",
        "test_id": TEST_ID,
        "candidate_code": U04_CODE,
        "intended_initial_code": WHITE_CODE,
        "roi_order": [
            {
                "roi_id": "ec5-cs1-unknown",
                "controller": "CS1",
                "measurement": rectangles["roi_cs1"],
            },
            {
                "roi_id": "ec5-cs2-unknown",
                "controller": "CS2",
                "measurement": rectangles["roi_cs2"],
            },
        ],
        "allowed_roi_classifications": [
            "white-like",
            "black-like",
            "yellow-like",
            "red-like",
            "blue-like",
            "green-like",
            "other-stable",
            "mixed-or-unstable",
            "not-observed",
        ],
        "required_sections": [
            "lineage",
            "roi_observations",
            "hold",
            "electrical",
            "temperature",
            "esp_continuity",
            "anomaly_review",
        ],
        "interpretation_limits": {
            "descriptive_only": True,
            "unknown_code_safety_may_be_claimed": False,
            "physical_color_alias_may_be_claimed": False,
            "waveform_change_may_be_inferred": False,
            "qualification_may_be_claimed": False,
            "automatic_scope_expansion": False,
        },
    }


def _build_action(frame_identity: Mapping[str, Any], observation_sha: str) -> dict[str, Any]:
    unsigned = {
        "ordinal": 1,
        "test_id": TEST_ID,
        "candidate_id": "U04",
        "candidate_code": U04_CODE,
        "intended_initial_code": WHITE_CODE,
        "intended_initial_color": "white",
        "repetition": 1,
        "frame_identity": dict(frame_identity),
        "manual_observation_contract_sha256": observation_sha,
        "body_or_raw_frame_materialized": False,
        "execution_route_materialized": False,
        "hardware_execution_authorized": False,
        "maximum_execute_attempts": 1,
        "retry_allowed": False,
        "recovery_included": False,
    }
    return {**unsigned, "action_identity_sha256": sha256(unsigned)}


def compile_campaign(
    panel_file: Path, build_sidecar_file: Path, firmware_binary_file: Path
) -> dict[str, Any]:
    """Compile the exact U04 pilot from three immutable local inputs."""

    panel_value, panel_payload = read_strict_json(
        panel_file, label="panel identity"
    )
    panel = validate_panel_identity(panel_value)
    build_value, build_payload = read_strict_json(
        build_sidecar_file, label="EC5 build sidecar"
    )
    firmware_payload = _read_regular_file(
        firmware_binary_file,
        label="EC5 firmware binary",
        maximum_bytes=MAX_FIRMWARE_BYTES,
    )
    build = validate_build_sidecar(build_value, firmware_payload)
    fixture_payload = build_fixture_manifest_payload(build)
    frame_identity = _verified_u04_identity()
    observation_contract = manual_observation_contract()
    observation_sha = sha256(observation_contract)
    action = _build_action(frame_identity, observation_sha)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "design_document": DESIGN_DOCUMENT,
            "design_document_sha256": DESIGN_DOCUMENT_SHA256,
            "stage": "EC5-STAGE-F-OFFLINE-CONTRACT",
        },
        "fixture_manifest": {
            "payload": fixture_payload,
            "manifest_payload_sha256": sha256(fixture_payload),
            "binary_sha256_excluded_to_avoid_self_reference": True,
        },
        "physical_binding": {
            "panel": panel,
            "panel_file_sha256": sha256(panel_payload),
            "build_sidecar": build,
            "build_sidecar_sha256": sha256(build_payload),
            "firmware_binary_sha256": sha256(firmware_payload),
        },
        "actions": [action],
        "manual_observation_contract": {
            "contract": observation_contract,
            "canonical_sha256": observation_sha,
        },
        "pilot_contract": {
            "binary_class": "U04_ONLY",
            "initial_state_external": True,
            "white_measured_initial_required": True,
            "unknown_action_count": 1,
            "maximum_execute_attempts": 1,
            "u07_fixture_or_action_present": False,
            "other_initial_states_materialized": False,
            "repeat_campaign_materialized": False,
            "hold_study_materialized": False,
            "recovery_action_materialized": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
        "classification": {
            "offline_compiled": True,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "device_io_performed": False,
            "network_io_performed": False,
            "serial_io_performed": False,
            "firmware_written": False,
            "power_control_performed": False,
            "refresh_performed": False,
            "waveform_modified": False,
            "qualification_state": "NOT_QUALIFIED",
            "descriptive_observation_only": True,
        },
    }
    result = {
        **unsigned,
        "integrity": {
            "canonical_sha256": sha256(unsigned),
            "canonical_sha256_scope": HASH_SCOPE,
        },
    }
    return dict(
        validate_campaign(
            result,
            panel_file,
            build_sidecar_file,
            firmware_binary_file,
            recompile=False,
        )
    )


def validate_campaign(
    campaign: Mapping[str, Any],
    panel_file: Path,
    build_sidecar_file: Path,
    firmware_binary_file: Path,
    *,
    recompile: bool = True,
) -> Mapping[str, Any]:
    """Deeply validate and optionally rebuild the campaign from actual inputs."""

    _require_exact_mapping(campaign, label="EC5 campaign", keys=_ROOT_KEYS)
    unsigned = dict(campaign)
    integrity = unsigned.pop("integrity")
    expected_integrity = {
        "canonical_sha256": sha256(unsigned),
        "canonical_sha256_scope": HASH_SCOPE,
    }
    if integrity != expected_integrity:
        raise EC5CampaignError("EC5 campaign integrity is invalid")
    if campaign["schema_version"] != SCHEMA_VERSION or campaign["kind"] != KIND:
        raise EC5CampaignError("EC5 campaign type is unsupported")
    source = _require_exact_mapping(
        campaign["source"], label="EC5 source", keys=_SOURCE_KEYS
    )
    if source != {
        "design_document": DESIGN_DOCUMENT,
        "design_document_sha256": DESIGN_DOCUMENT_SHA256,
        "stage": "EC5-STAGE-F-OFFLINE-CONTRACT",
    }:
        raise EC5CampaignError("EC5 source design identity changed")
    binding = _require_exact_mapping(
        campaign["physical_binding"],
        label="EC5 physical binding",
        keys=_BINDING_KEYS,
    )
    panel = validate_panel_identity(binding["panel"])
    build = _require_exact_mapping(
        binding["build_sidecar"], label="embedded build sidecar", keys=_BUILD_KEYS
    )
    if (
        binding["build_sidecar_sha256"] != sha256(build)
        or binding["firmware_binary_sha256"] != build["binary_sha256"]
        or not isinstance(panel, Mapping)
    ):
        raise EC5CampaignError("EC5 embedded build/panel binding is invalid")
    actions = campaign["actions"]
    if not isinstance(actions, list) or len(actions) != 1:
        raise EC5CampaignError("EC5 pilot must contain exactly one action")
    action = _require_exact_mapping(
        actions[0], label="EC5 pilot action", keys=_ACTION_KEYS
    )
    action_unsigned = dict(action)
    action_digest = action_unsigned.pop("action_identity_sha256", None)
    if action_digest != sha256(action_unsigned):
        raise EC5CampaignError("EC5 pilot action identity is invalid")
    if (
        action.get("test_id") != TEST_ID
        or action.get("candidate_id") != "U04"
        or action.get("candidate_code") != U04_CODE
        or action.get("intended_initial_code") != WHITE_CODE
        or action.get("repetition") != 1
        or action.get("execution_route_materialized") is not False
        or action.get("hardware_execution_authorized") is not False
        or action.get("retry_allowed") is not False
    ):
        raise EC5CampaignError("EC5 pilot action escaped the U04/white/once scope")
    fixture = _require_exact_mapping(
        campaign["fixture_manifest"],
        label="EC5 fixture manifest",
        keys=_FIXTURE_KEYS,
    )
    if (
        fixture.get("manifest_payload_sha256") != sha256(fixture.get("payload"))
        or fixture.get("binary_sha256_excluded_to_avoid_self_reference") is not True
        or fixture.get("payload") != build_fixture_manifest_payload(build)
        or fixture.get("manifest_payload_sha256")
        != build.get("manifest_payload_sha256")
    ):
        raise EC5CampaignError("EC5 fixture manifest binding is invalid")
    observation = _require_exact_mapping(
        campaign["manual_observation_contract"],
        label="manual observation contract wrapper",
        keys=_OBSERVATION_WRAPPER_KEYS,
    )
    if (
        observation.get("contract") != manual_observation_contract()
        or observation.get("canonical_sha256")
        != sha256(manual_observation_contract())
        or action.get("manual_observation_contract_sha256")
        != observation.get("canonical_sha256")
    ):
        raise EC5CampaignError("manual observation contract binding is invalid")
    if action != _build_action(_verified_u04_identity(), observation["canonical_sha256"]):
        raise EC5CampaignError("EC5 pilot action differs from the frozen fixture")
    expected_pilot = {
        "binary_class": "U04_ONLY",
        "initial_state_external": True,
        "white_measured_initial_required": True,
        "unknown_action_count": 1,
        "maximum_execute_attempts": 1,
        "u07_fixture_or_action_present": False,
        "other_initial_states_materialized": False,
        "repeat_campaign_materialized": False,
        "hold_study_materialized": False,
        "recovery_action_materialized": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    if campaign["pilot_contract"] != expected_pilot:
        raise EC5CampaignError("EC5 pilot scope was widened")
    expected_classification = {
        "offline_compiled": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "serial_io_performed": False,
        "firmware_written": False,
        "power_control_performed": False,
        "refresh_performed": False,
        "waveform_modified": False,
        "qualification_state": "NOT_QUALIFIED",
        "descriptive_observation_only": True,
    }
    if campaign["classification"] != expected_classification:
        raise EC5CampaignError("EC5 offline classification was widened")
    if recompile:
        expected = compile_campaign(
            panel_file, build_sidecar_file, firmware_binary_file
        )
        if campaign != expected:
            raise EC5CampaignError("EC5 campaign differs from its actual inputs")
    return campaign


def describe_design_separation() -> dict[str, Any]:
    """Describe U04/U07 separation without materializing either action."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-ec5-unknown-candidate-separation-description",
        "u04": {
            "candidate_id": "U04",
            "candidate_code": U04_CODE,
            "first_materializable_scope": TEST_ID,
            "requires_isolated_single_candidate_build": True,
        },
        "u07": dict(U07_DESIGN_IDENTITY),
        "shared_binary_allowed": False,
        "u07_action_materialized": False,
        "hardware_execution_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
    }


def _load_campaign_file(path: Path) -> Mapping[str, Any]:
    value, _payload = read_strict_json(path, label="EC5 campaign")
    return value


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser("compile", allow_abbrev=False)
    compile_parser.add_argument("--panel", type=Path, required=True)
    compile_parser.add_argument("--build-sidecar", type=Path, required=True)
    compile_parser.add_argument("--firmware-binary", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate", allow_abbrev=False)
    validate_parser.add_argument("--campaign", type=Path, required=True)
    validate_parser.add_argument("--panel", type=Path, required=True)
    validate_parser.add_argument("--build-sidecar", type=Path, required=True)
    validate_parser.add_argument("--firmware-binary", type=Path, required=True)
    subparsers.add_parser("describe-separation", allow_abbrev=False)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        if args.command == "describe-separation":
            result = describe_design_separation()
        elif args.command == "compile":
            result = compile_campaign(
                args.panel, args.build_sidecar, args.firmware_binary
            )
            publish_new_json(args.output, result, label="EC5 campaign output")
        else:
            result = validate_campaign(
                _load_campaign_file(args.campaign),
                args.panel,
                args.build_sidecar,
                args.firmware_binary,
            )
    except EC5CampaignError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BUILD_SIDECAR_KIND",
    "EC5CampaignError",
    "KIND",
    "LAYOUT_ID",
    "TEST_ID",
    "U04_CODE",
    "U04_DTM_SHA256",
    "U04_FRAME_SHA256",
    "U07_DESIGN_IDENTITY",
    "WHITE_CODE",
    "build_fixture_manifest_payload",
    "canonical_json_bytes",
    "compile_campaign",
    "describe_design_separation",
    "manual_observation_contract",
    "publish_new_json",
    "read_strict_json",
    "sha256",
    "validate_campaign",
]
