"""Measured-evidence-gated N6 fixed visible browser execution.

The ordinary application server remains offline by default.  This module is a
separate, fail-closed bridge for the future N6 hardware action: it accepts only
an exact four-preview artifact backed by a complete measured palette and gamut
profile, reviewed static/runtime evidence, a reviewed P0 limit profile, and an
immutable prior PASS result.

No function in this module invents measurement, review, or operator evidence.
Materialization is pure.  The sole device-I/O entry point consumes the
workspace-global action claim with exclusive-create semantics *before* calling
an injected protocol driver.  Once that claim is consumed, every ambiguous
outcome is terminal ``UNKNOWN_DO_NOT_RETRY``; there is no retry or recovery
path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence
import ipaddress
from urllib.parse import urlsplit

from host.color_pipeline import Palette, PaletteError, palette_from_mapping
from host.epd_frame import ControllerMapping, FRAME_BYTES, fnv1a
from host.extended_color import (
    MeasurementAggregationError,
    validate_palette_aggregate,
)
from host.gamut_mapping import (
    GamutProfile,
    GamutProfileError,
    gamut_profile_from_mapping,
)
from host.visible_refresh_campaign import (
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    evaluate_limit_profile,
    result_file_sha256,
    validate_limit_profile,
    validate_result_record,
    workspace_global_claim_declaration,
)
from tools import mf1750_frame_tool as frame_tool

from .n6_browser_campaign import (
    DEFAULT_MAPPINGS,
    N6BrowserCampaignError,
    validate_n6_offline_manifest,
)
from .durable_io import ensure_directory_tree_durable, fsync_directory
from .pipeline import ApplicationArtifact, ApplicationError


SCHEMA_VERSION = 1

FORMAL_ARTIFACT_REVIEW_KIND = "mf1750-n6-formal-artifact-review"
RUNTIME_REVIEW_KIND = "mf1750-n6-reviewed-runtime-envelope"
MATERIALIZATION_DESCRIPTION_KIND = "mf1750-n6-formal-materialization-description"
FORMAL_MANIFEST_KIND = "mf1750-n6-formal-execution-manifest"
AUTHORIZATION_KIND = "mf1750-n6-external-one-visible-authorization"
RUNTIME_OBSERVATION_KIND = "mf1750-n6-runtime-observation"
CLAIM_KIND = "mf1750-n6-workspace-global-consumed-claim"
PROTOCOL_RECEIPT_KIND = "mf1750-n6-fixed-protocol-receipt"
MANUAL_OBSERVATION_KIND = "mf1750-n6-manual-screen-observation"
FINALIZED_BUNDLE_KIND = "mf1750-n6-finalized-visible-execution-bundle"

N6_ARM_CONFIRMATION = "ARM MF1750 REFRESH"
LEGACY_N6_ENQUEUE_BLOCK_MESSAGE = (
    "legacy N6 browser enqueue is disabled: use the physical/production "
    "N6 browser controller with deep evidence validation"
)

CANONICAL_HASH_SCOPE = (
    "entire document excluding integrity; UTF-8 JSON with sorted keys, no "
    "whitespace, ensure_ascii=false, allow_nan=false"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")

_PREVIEW_STAGES = ("source", "mapped", "final", "model")
_FIXED_MAPPING_RECORDS = (
    {
        "source_half": 0,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
    {
        "source_half": 1,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
)


class N6VisibleExecutionError(ValueError):
    """An N6 formal input or transition failed closed before device I/O."""


class N6ClaimConsumed(N6VisibleExecutionError):
    """The immutable workspace-global claim already exists."""


class N6TransportOutcomeUnknown(RuntimeError):
    """A driver outcome is unknown after zero or one possible frame POST."""

    def __init__(self, detail: str, *, frame_post_request_count: int) -> None:
        super().__init__(detail)
        if type(frame_post_request_count) is not int or frame_post_request_count not in {0, 1}:
            raise ValueError("frame_post_request_count must be integer zero or one")
        self.frame_post_request_count = frame_post_request_count


class N6PostClaimUnknown(N6VisibleExecutionError):
    """The action is terminal UNKNOWN after permanent claim consumption."""

    def __init__(self, detail: str, *, receipt: Mapping[str, Any]) -> None:
        super().__init__(detail)
        self.receipt = _snapshot(receipt)


class N6ClaimWriteOutcomeUnknown(RuntimeError):
    """Exclusive claim creation occurred but durable write could not be proven."""

    def __init__(self, detail: str, *, claim_commit: "N6ClaimCommit") -> None:
        super().__init__(detail)
        self.claim_commit = claim_commit


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise N6VisibleExecutionError(f"value is not canonical JSON data: {error}") from error


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _canonical_sha256(unsigned),
        "canonical_sha256_scope": CANONICAL_HASH_SCOPE,
    }


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise N6VisibleExecutionError("sealed payload must be an object without integrity")
    root = _snapshot(payload)
    root["integrity"] = _integrity(root)
    return root


def _exact(value: Any, *, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N6VisibleExecutionError(f"{label} must be an object")
    if set(value) != keys:
        raise N6VisibleExecutionError(
            f"{label} fields differ; missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise N6VisibleExecutionError(f"{label} must be trimmed non-empty text")
    return value


def _token(value: Any, *, label: str) -> str:
    text = _text(value, label=label, maximum=256)
    if _TOKEN_RE.fullmatch(text) is None:
        raise N6VisibleExecutionError(f"{label} contains unsupported characters")
    return text


def _hash(value: Any, *, label: str, reject_placeholder: bool = True) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise N6VisibleExecutionError(f"{label} must be 64 lowercase hex digits")
    if reject_placeholder and value == "0" * 64:
        raise N6VisibleExecutionError(f"{label} must not be a placeholder SHA-256")
    return value


def _hex40(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HEX40_RE.fullmatch(value) is None:
        raise N6VisibleExecutionError(f"{label} must be 40 lowercase hex digits")
    if value == "0" * 40:
        raise N6VisibleExecutionError(f"{label} must not be a placeholder commit")
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise N6VisibleExecutionError(f"{label} must be strict RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N6VisibleExecutionError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N6VisibleExecutionError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise N6VisibleExecutionError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise N6VisibleExecutionError(f"{label} is below {minimum}")
    if maximum is not None and result > maximum:
        raise N6VisibleExecutionError(f"{label} is above {maximum}")
    return result


def _check_integrity(root: Mapping[str, Any], *, label: str) -> None:
    unsigned = dict(root)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise N6VisibleExecutionError(f"{label} canonical integrity is invalid")


def _artifact_identity(value: Any, *, label: str) -> Mapping[str, Any]:
    root = _exact(
        value,
        label=label,
        keys={"frame_sha256", "frame_fnv1a", "frame_bytes", "report_sha256"},
    )
    _hash(root["frame_sha256"], label=f"{label}.frame_sha256")
    _hash(root["report_sha256"], label=f"{label}.report_sha256")
    if type(root["frame_fnv1a"]) is not int or not 0 <= root["frame_fnv1a"] <= 0xFFFFFFFF:
        raise N6VisibleExecutionError(f"{label}.frame_fnv1a must be uint32")
    if root["frame_bytes"] != FRAME_BYTES or type(root["frame_bytes"]) is not int:
        raise N6VisibleExecutionError(f"{label}.frame_bytes must be {FRAME_BYTES}")
    return root


def _review(value: Any, *, label: str) -> Mapping[str, Any]:
    root = _exact(
        value,
        label=label,
        keys={"approved", "reviewer_id", "reviewed_at", "review_artifact_sha256"},
    )
    if type(root["approved"]) is not bool:
        raise N6VisibleExecutionError(f"{label}.approved must be boolean")
    _text(root["reviewer_id"], label=f"{label}.reviewer_id", maximum=256)
    _timestamp(root["reviewed_at"], label=f"{label}.reviewed_at")
    _hash(root["review_artifact_sha256"], label=f"{label}.review_artifact_sha256")
    return root


def seal_n6_formal_artifact_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal externally authored review evidence; sealing is not approval."""

    root = _seal(payload)
    validate_n6_formal_artifact_review(root)
    return root


def validate_n6_formal_artifact_review(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N6 formal artifact review",
        keys={
            "schema_version",
            "kind",
            "review_id",
            "offline_manifest_canonical_sha256",
            "artifact_identity",
            "source_input_sha256",
            "four_preview_sha256",
            "palette_aggregate_canonical_sha256",
            "palette_canonical_sha256",
            "gamut_profile_canonical_sha256",
            "panel",
            "firmware",
            "application_build_sha256",
            "review",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != FORMAL_ARTIFACT_REVIEW_KIND:
        raise N6VisibleExecutionError("N6 formal artifact review kind/version is invalid")
    _token(root["review_id"], label="formal artifact review_id")
    for field in (
        "offline_manifest_canonical_sha256",
        "source_input_sha256",
        "palette_aggregate_canonical_sha256",
        "palette_canonical_sha256",
        "gamut_profile_canonical_sha256",
        "application_build_sha256",
    ):
        _hash(root[field], label=f"formal artifact {field}")
    _artifact_identity(root["artifact_identity"], label="formal artifact identity")
    previews = _exact(
        root["four_preview_sha256"],
        label="formal artifact four_preview_sha256",
        keys=set(_PREVIEW_STAGES),
    )
    for stage in _PREVIEW_STAGES:
        _hash(previews[stage], label=f"formal artifact {stage} preview")
    if not isinstance(root["panel"], Mapping) or not isinstance(root["firmware"], Mapping):
        raise N6VisibleExecutionError("formal artifact panel/firmware must be objects")
    _review(root["review"], label="formal artifact review")
    _check_integrity(root, label="N6 formal artifact review")
    return root


def seal_n6_runtime_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal an externally reviewed host/browser/runtime envelope."""

    root = _seal(payload)
    validate_n6_runtime_review(root)
    return root


def validate_n6_runtime_review(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N6 runtime review",
        keys={
            "schema_version",
            "kind",
            "runtime_id",
            "application_build",
            "firmware",
            "browser_contract",
            "device_contract",
            "review",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != RUNTIME_REVIEW_KIND:
        raise N6VisibleExecutionError("N6 runtime review kind/version is invalid")
    _token(root["runtime_id"], label="runtime_id")
    build = _exact(
        root["application_build"],
        label="runtime application_build",
        keys={"source_commit", "bundle_sha256"},
    )
    _hex40(build["source_commit"], label="runtime application source_commit")
    _hash(build["bundle_sha256"], label="runtime application bundle_sha256")
    if not isinstance(root["firmware"], Mapping):
        raise N6VisibleExecutionError("runtime firmware binding must be an object")
    browser = _exact(
        root["browser_contract"],
        label="runtime browser_contract",
        keys={
            "loopback_only",
            "token_required",
            "same_origin_post_required",
            "server_recomputes_source_sha256",
            "convert_v2_required",
            "four_previews_required",
            "one_shot_arm_required",
            "reload_cannot_reset_claim_or_submission",
        },
    )
    if any(browser[field] is not True for field in browser):
        raise N6VisibleExecutionError("runtime browser contract must keep every safety gate true")
    device = _exact(
        root["device_contract"],
        label="runtime device_contract",
        keys={
            "method",
            "endpoint",
            "maximum_frame_posts",
            "automatic_retry",
            "automatic_recovery",
            "cs1_mapping",
            "cs2_mapping",
            "minimum_controller_voltage_v",
            "maximum_controller_voltage_v",
            "maximum_idle_current_a",
            "j2_must_be_on",
        },
    )
    minimum_voltage = _number(
        device["minimum_controller_voltage_v"],
        label="runtime minimum controller voltage",
        minimum=0,
        maximum=10,
    )
    maximum_voltage = _number(
        device["maximum_controller_voltage_v"],
        label="runtime maximum controller voltage",
        minimum=0,
        maximum=10,
    )
    _number(
        device["maximum_idle_current_a"],
        label="runtime maximum idle current",
        minimum=0,
        maximum=100,
    )
    if (
        device["method"] != "POST"
        or device["endpoint"] != "/api/frame"
        or device["maximum_frame_posts"] != 1
        or type(device["maximum_frame_posts"]) is not int
        or device["automatic_retry"] is not False
        or device["automatic_recovery"] is not False
        or device["cs1_mapping"] != _FIXED_MAPPING_RECORDS[0]
        or device["cs2_mapping"] != _FIXED_MAPPING_RECORDS[1]
        or minimum_voltage >= maximum_voltage
        or device["j2_must_be_on"] is not True
    ):
        raise N6VisibleExecutionError("runtime device contract differs from fixed one-POST N6")
    _review(root["review"], label="runtime review")
    _check_integrity(root, label="N6 runtime review")
    return root


def _measured_inputs(
    palette_aggregate: Mapping[str, Any],
    gamut_profile: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Palette, GamutProfile]:
    try:
        aggregate = validate_palette_aggregate(palette_aggregate)
    except MeasurementAggregationError as error:
        raise N6VisibleExecutionError(f"measured palette aggregate is invalid: {error}") from error
    if (
        aggregate["classification"].get("measured") is not True
        or aggregate["classification"].get("calibrated") is not True
        or aggregate["accepted_sample_count"] != aggregate["expected_sample_count"]
        or aggregate["blockers"]
        or aggregate["palette"] is None
    ):
        raise N6VisibleExecutionError(
            "measured palette aggregate is incomplete or not calibrated"
        )
    try:
        palette = palette_from_mapping(aggregate["palette"])
    except PaletteError as error:  # pragma: no cover - aggregate validator already parses it
        raise N6VisibleExecutionError(f"measured palette is invalid: {error}") from error
    if not palette.calibrated or palette.calibration is None:
        raise N6VisibleExecutionError("N6 palette must retain calibrated measurement provenance")
    try:
        profile = gamut_profile_from_mapping(gamut_profile, palette)
    except GamutProfileError as error:
        raise N6VisibleExecutionError(f"measured gamut profile is invalid: {error}") from error
    if (
        profile.characterization_level != "measured_mixtures"
        or profile.model_kind != "measured_point_cloud_v1"
        or not profile.provenance_complete_for_formal_use
    ):
        raise N6VisibleExecutionError(
            "N6 gamut profile must be a complete measured_mixtures point-cloud profile"
        )
    # hardware_formal_qualified intentionally remains false in GamutProfile.
    # Trust is supplied only by the exact external review bound below.
    if profile.hardware_formal_qualified is not False:
        raise N6VisibleExecutionError("gamut fingerprint unexpectedly claims trust approval")
    return aggregate, palette, profile


def _expected_allowlist(action: Mapping[str, Any]) -> dict[str, Any]:
    identity = action["identity"]
    return {
        "action_id": identity["action_id"],
        "action_identity_sha256": action["action_identity_sha256"],
        "method": "POST",
        "endpoint": "/api/frame",
        "frame_sha256": identity["frame"]["sha256"],
        "maximum_uses": 1,
    }


def _validate_profile_for_action(
    profile: Mapping[str, Any],
    *,
    offline_manifest: Mapping[str, Any],
    evaluated_at: str,
) -> Mapping[str, Any]:
    try:
        root = validate_limit_profile(profile)
        decision = evaluate_limit_profile(root, evaluated_at=evaluated_at)
    except CampaignContractError as error:
        raise N6VisibleExecutionError(f"reviewed limit profile is invalid: {error}") from error
    campaign = offline_manifest["p0_campaign"]
    action = campaign["actions"][0]
    if root["panel"] != campaign["panel"] or root["firmware"] != campaign["firmware"]:
        raise N6VisibleExecutionError("reviewed limit profile panel/firmware binding changed")
    if root["action_allowlist"] != [_expected_allowlist(action)]:
        raise N6VisibleExecutionError("reviewed limit profile must allow only the exact N6 action")
    if root["review"]["approved"] is not True:
        raise N6VisibleExecutionError("N6 limit profile is not approved")
    if not decision.hardware_ready or decision.reasons:
        raise N6VisibleExecutionError(
            "N6 limit profile is not ready at materialization time: "
            + ", ".join(decision.reasons)
        )
    return root


def _prior_binding(
    prior_result: Mapping[str, Any],
    prior_result_sha256: str,
    *,
    limit_profile: Mapping[str, Any],
) -> tuple[Mapping[str, Any], str]:
    try:
        result = validate_result_record(prior_result)
        actual_sha = result_file_sha256(result)
    except CampaignContractError as error:
        raise N6VisibleExecutionError(f"prior result is invalid: {error}") from error
    supplied_sha = _hash(prior_result_sha256, label="prior result whole-file SHA-256")
    if supplied_sha != actual_sha:
        raise N6VisibleExecutionError("prior result whole-file SHA-256 does not match")
    if result["state"] != ResultState.PASS.value or result["post_request_count"] != 1:
        raise N6VisibleExecutionError("N6 prior result must be an immutable one-POST PASS")
    usage = limit_profile["usage"]
    counts = (
        usage["cumulative_visible_refresh_count"],
        usage["session_visible_refresh_count"],
        usage["consecutive_visible_refresh_count"],
    )
    if any(type(count) is not int or count < 1 for count in counts):
        raise N6VisibleExecutionError("limit usage snapshot does not include the prior refresh")
    completed = _timestamp(result["completed_at"], label="prior result completed_at")
    snapshot_at = _timestamp(usage["snapshot_at"], label="limit usage snapshot_at")
    last_visible = _timestamp(
        usage["last_visible_refresh_completed_at"],
        label="limit usage last_visible_refresh_completed_at",
    )
    if snapshot_at < completed or last_visible < completed:
        raise N6VisibleExecutionError("limit usage snapshot predates the bound prior PASS")
    return result, actual_sha


def _artifact_review_bindings(
    review: Mapping[str, Any],
    *,
    offline_manifest: Mapping[str, Any],
    palette_aggregate: Mapping[str, Any],
    palette: Palette,
    gamut_profile: GamutProfile,
    runtime_review: Mapping[str, Any],
) -> None:
    source = offline_manifest["source_artifact"]
    expected_previews = {
        stage: source["previews"][stage]["sha256"] for stage in _PREVIEW_STAGES
    }
    expected = {
        "offline_manifest_canonical_sha256": offline_manifest["integrity"][
            "canonical_sha256"
        ],
        "artifact_identity": source["artifact_identity"],
        "source_input_sha256": source["input"]["sha256"],
        "four_preview_sha256": expected_previews,
        "palette_aggregate_canonical_sha256": palette_aggregate["integrity"][
            "canonical_sha256"
        ],
        "palette_canonical_sha256": palette.canonical_sha256,
        "gamut_profile_canonical_sha256": gamut_profile.canonical_sha256,
        "panel": offline_manifest["p0_campaign"]["panel"],
        "firmware": offline_manifest["p0_campaign"]["firmware"],
        "application_build_sha256": runtime_review["application_build"][
            "bundle_sha256"
        ],
    }
    for field, value in expected.items():
        if review[field] != value:
            raise N6VisibleExecutionError(f"formal artifact review {field} binding changed")
    if review["review"]["approved"] is not True:
        raise N6VisibleExecutionError("formal artifact review is not approved")


def _static_bindings(
    offline_manifest: Mapping[str, Any],
    palette_aggregate: Mapping[str, Any],
    palette: Palette,
    gamut_profile: GamutProfile,
    formal_artifact_review: Mapping[str, Any],
    limit_profile: Mapping[str, Any],
    runtime_review: Mapping[str, Any],
    prior_result: Mapping[str, Any],
    prior_result_sha256: str,
) -> None:
    source = offline_manifest["source_artifact"]
    source_palette = source["palette"]
    source_profile = source["gamut_profile"]
    if (
        source_palette["id"] != palette.palette_id
        or source_palette["canonical_sha256"] != palette.canonical_sha256
        or source_palette["calibrated"] is not True
        or source_palette["measurement_bound"] is not True
    ):
        raise N6VisibleExecutionError("browser artifact differs from measured palette")
    if (
        source_profile["id"] != gamut_profile.profile_id
        or source_profile["canonical_sha256"] != gamut_profile.canonical_sha256
        or source_profile["characterization_level"] != "measured_mixtures"
    ):
        raise N6VisibleExecutionError("browser artifact differs from measured gamut profile")
    campaign = offline_manifest["p0_campaign"]
    panel = campaign["panel"]
    firmware = campaign["firmware"]
    if gamut_profile.panel_model != panel["model"] or gamut_profile.panel_id != panel["serial"]:
        raise N6VisibleExecutionError("measured gamut profile panel binding changed")
    if gamut_profile.firmware_commit != firmware["source_commit"]:
        raise N6VisibleExecutionError("measured gamut profile firmware commit changed")
    if runtime_review["firmware"] != firmware:
        raise N6VisibleExecutionError("runtime review firmware binding changed")
    if runtime_review["review"]["approved"] is not True:
        raise N6VisibleExecutionError("runtime envelope is not approved")
    _artifact_review_bindings(
        formal_artifact_review,
        offline_manifest=offline_manifest,
        palette_aggregate=palette_aggregate,
        palette=palette,
        gamut_profile=gamut_profile,
        runtime_review=runtime_review,
    )
    # Retain explicit arguments so a future refactor cannot silently drop them.
    if limit_profile["panel"] != panel or prior_result["state"] != ResultState.PASS.value:
        raise N6VisibleExecutionError("limit/prior static binding changed")
    _hash(prior_result_sha256, label="bound prior result SHA-256")


def describe_n6_formal_materialization(
    offline_manifest: Mapping[str, Any],
    *,
    evaluated_at: str,
    palette_aggregate: Mapping[str, Any] | None = None,
    gamut_profile: Mapping[str, Any] | None = None,
    formal_artifact_review: Mapping[str, Any] | None = None,
    reviewed_limit_profile: Mapping[str, Any] | None = None,
    runtime_review: Mapping[str, Any] | None = None,
    prior_result: Mapping[str, Any] | None = None,
    prior_result_sha256: str | None = None,
) -> dict[str, Any]:
    """Describe missing formal inputs with zero claim, authorization, or I/O.

    Missing inputs are reported as blockers.  Supplied-but-invalid inputs raise
    immediately; they are not converted into a softer "missing" state.
    """

    try:
        offline = validate_n6_offline_manifest(offline_manifest)
    except N6BrowserCampaignError as error:
        raise N6VisibleExecutionError(f"offline N6 manifest is invalid: {error}") from error
    _timestamp(evaluated_at, label="materialization evaluated_at")
    blockers: list[str] = []
    identities: dict[str, Optional[str]] = {
        "palette_aggregate_canonical_sha256": None,
        "palette_canonical_sha256": None,
        "gamut_profile_canonical_sha256": None,
        "formal_artifact_review_canonical_sha256": None,
        "limit_profile_canonical_sha256": None,
        "runtime_review_canonical_sha256": None,
        "prior_result_file_sha256": None,
    }

    aggregate: Mapping[str, Any] | None = None
    palette: Palette | None = None
    profile: GamutProfile | None = None
    if palette_aggregate is None:
        blockers.append("complete_measured_palette_aggregate_missing")
    if gamut_profile is None:
        blockers.append("complete_measured_gamut_profile_missing")
    if palette_aggregate is not None and gamut_profile is not None:
        aggregate, palette, profile = _measured_inputs(palette_aggregate, gamut_profile)
        identities.update(
            {
                "palette_aggregate_canonical_sha256": aggregate["integrity"][
                    "canonical_sha256"
                ],
                "palette_canonical_sha256": palette.canonical_sha256,
                "gamut_profile_canonical_sha256": profile.canonical_sha256,
            }
        )

    artifact_review_root: Mapping[str, Any] | None = None
    if formal_artifact_review is None:
        blockers.append("approved_formal_artifact_review_missing")
    else:
        artifact_review_root = validate_n6_formal_artifact_review(formal_artifact_review)
        identities["formal_artifact_review_canonical_sha256"] = artifact_review_root[
            "integrity"
        ]["canonical_sha256"]
        if artifact_review_root["review"]["approved"] is not True:
            blockers.append("formal_artifact_review_not_approved")

    limit_root: Mapping[str, Any] | None = None
    if reviewed_limit_profile is None:
        blockers.append("reviewed_limit_profile_missing")
    else:
        limit_root = _validate_profile_for_action(
            reviewed_limit_profile,
            offline_manifest=offline,
            evaluated_at=evaluated_at,
        )
        identities["limit_profile_canonical_sha256"] = limit_root["integrity"][
            "canonical_sha256"
        ]

    runtime_root: Mapping[str, Any] | None = None
    if runtime_review is None:
        blockers.append("approved_runtime_review_missing")
    else:
        runtime_root = validate_n6_runtime_review(runtime_review)
        identities["runtime_review_canonical_sha256"] = runtime_root["integrity"][
            "canonical_sha256"
        ]
        if runtime_root["review"]["approved"] is not True:
            blockers.append("runtime_review_not_approved")

    prior_root: Mapping[str, Any] | None = None
    actual_prior_sha: str | None = None
    if prior_result is None or prior_result_sha256 is None:
        blockers.append("immutable_prior_pass_result_binding_missing")
    elif limit_root is not None:
        prior_root, actual_prior_sha = _prior_binding(
            prior_result,
            prior_result_sha256,
            limit_profile=limit_root,
        )
        identities["prior_result_file_sha256"] = actual_prior_sha

    if all(
        value is not None
        for value in (
            aggregate,
            palette,
            profile,
            artifact_review_root,
            limit_root,
            runtime_root,
            prior_root,
            actual_prior_sha,
        )
    ):
        assert aggregate is not None and palette is not None and profile is not None
        assert artifact_review_root is not None and limit_root is not None
        assert runtime_root is not None and prior_root is not None and actual_prior_sha is not None
        _static_bindings(
            offline,
            aggregate,
            palette,
            profile,
            artifact_review_root,
            limit_root,
            runtime_root,
            prior_root,
            actual_prior_sha,
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": MATERIALIZATION_DESCRIPTION_KIND,
        "mode": "describe-only",
        "evaluated_at": evaluated_at,
        "offline_manifest_canonical_sha256": offline["integrity"]["canonical_sha256"],
        "action_identity_sha256": offline["p0_action_identity_sha256"],
        "evidence_identities": identities,
        "materialization_ready": not blockers,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_frame_posts_if_separately_authorized": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
    }
    root = _seal(payload)
    validate_n6_materialization_description(root)
    return root


def validate_n6_materialization_description(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N6 materialization description",
        keys={
            "schema_version",
            "kind",
            "mode",
            "evaluated_at",
            "offline_manifest_canonical_sha256",
            "action_identity_sha256",
            "evidence_identities",
            "materialization_ready",
            "hardware_ready",
            "hardware_execution_authorized",
            "authorization_created",
            "claim_created",
            "network_io_performed",
            "device_io_performed",
            "maximum_frame_posts_if_separately_authorized",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
            "blockers",
            "integrity",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != MATERIALIZATION_DESCRIPTION_KIND
        or root["mode"] != "describe-only"
    ):
        raise N6VisibleExecutionError("N6 materialization description kind/version is invalid")
    _timestamp(root["evaluated_at"], label="description evaluated_at")
    _hash(root["offline_manifest_canonical_sha256"], label="offline manifest identity")
    _hash(root["action_identity_sha256"], label="N6 action identity")
    identities = _exact(
        root["evidence_identities"],
        label="description evidence identities",
        keys={
            "palette_aggregate_canonical_sha256",
            "palette_canonical_sha256",
            "gamut_profile_canonical_sha256",
            "formal_artifact_review_canonical_sha256",
            "limit_profile_canonical_sha256",
            "runtime_review_canonical_sha256",
            "prior_result_file_sha256",
        },
    )
    for field, value in identities.items():
        if value is not None:
            _hash(value, label=f"description evidence {field}")
    blockers = root["blockers"]
    if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
        raise N6VisibleExecutionError("materialization blockers must be a list of strings")
    if len(blockers) != len(set(blockers)):
        raise N6VisibleExecutionError("materialization blockers are duplicated")
    if type(root["materialization_ready"]) is not bool or root["materialization_ready"] != (not blockers):
        raise N6VisibleExecutionError("materialization readiness is inconsistent")
    false_fields = (
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
    )
    if any(root[field] is not False for field in false_fields):
        raise N6VisibleExecutionError("describe-only materialization attempted a side effect")
    if root["maximum_frame_posts_if_separately_authorized"] != 1:
        raise N6VisibleExecutionError("future N6 action must remain capped at one frame POST")
    _check_integrity(root, label="N6 materialization description")
    return root


_EXECUTION_POLICY = {
    "claim_before_any_device_network": True,
    "claim_is_workspace_global": True,
    "claim_is_permanent": True,
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_frame_posts": 1,
    "http_202_is_not_completion": True,
    "matching_terminal_job_required": True,
    "matching_diagnostic_report_required": True,
    "manual_screen_and_electrical_observation_required": True,
    "automatic_retry": False,
    "automatic_recovery": False,
    "unknown_outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
}

_MATERIALIZED_CLASSIFICATION = {
    "offline_materialized": True,
    "measured_palette_complete": True,
    "measured_gamut_profile_complete": True,
    "static_reviews_complete": True,
    "hardware_execution_authorized": False,
    "authorization_created": False,
    "claim_created": False,
    "network_io_performed": False,
    "device_io_performed": False,
    "automatic_retry": False,
    "automatic_recovery": False,
}


def materialize_n6_formal_manifest(
    offline_manifest: Mapping[str, Any],
    *,
    materialized_at: str,
    palette_aggregate: Mapping[str, Any],
    gamut_profile: Mapping[str, Any],
    formal_artifact_review: Mapping[str, Any],
    reviewed_limit_profile: Mapping[str, Any],
    runtime_review: Mapping[str, Any],
    prior_result: Mapping[str, Any],
    prior_result_sha256: str,
) -> dict[str, Any]:
    """Materialize one exact N6 action only after every static gate is closed."""

    description = describe_n6_formal_materialization(
        offline_manifest,
        evaluated_at=materialized_at,
        palette_aggregate=palette_aggregate,
        gamut_profile=gamut_profile,
        formal_artifact_review=formal_artifact_review,
        reviewed_limit_profile=reviewed_limit_profile,
        runtime_review=runtime_review,
        prior_result=prior_result,
        prior_result_sha256=prior_result_sha256,
    )
    if description["materialization_ready"] is not True:
        raise N6VisibleExecutionError(
            "N6 formal manifest remains blocked: " + ", ".join(description["blockers"])
        )
    offline = validate_n6_offline_manifest(offline_manifest)
    aggregate, palette, profile = _measured_inputs(palette_aggregate, gamut_profile)
    artifact_review_root = validate_n6_formal_artifact_review(formal_artifact_review)
    limit_root = _validate_profile_for_action(
        reviewed_limit_profile,
        offline_manifest=offline,
        evaluated_at=materialized_at,
    )
    runtime_root = validate_n6_runtime_review(runtime_review)
    prior_root, actual_prior_sha = _prior_binding(
        prior_result, prior_result_sha256, limit_profile=limit_root
    )
    _static_bindings(
        offline,
        aggregate,
        palette,
        profile,
        artifact_review_root,
        limit_root,
        runtime_root,
        prior_root,
        actual_prior_sha,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": FORMAL_MANIFEST_KIND,
        "materialized_at": materialized_at,
        "offline_manifest": _snapshot(offline),
        "palette_aggregate": _snapshot(aggregate),
        "gamut_profile": _snapshot(profile.canonical_mapping()),
        "formal_artifact_review": _snapshot(artifact_review_root),
        "reviewed_limit_profile": _snapshot(limit_root),
        "runtime_review": _snapshot(runtime_root),
        "prior_binding": {
            "action_identity_sha256": prior_root["action_identity_sha256"],
            "result_file_sha256": actual_prior_sha,
            "required_state": ResultState.PASS.value,
            "result": _snapshot(prior_root),
        },
        "action": _snapshot(offline["p0_campaign"]["actions"][0]),
        "execution_policy": _snapshot(_EXECUTION_POLICY),
        "browser_contract": _snapshot(runtime_root["browser_contract"]),
        "classification": _snapshot(_MATERIALIZED_CLASSIFICATION),
    }
    root = _seal(payload)
    validate_n6_formal_manifest(root)
    return root


def validate_n6_formal_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        manifest,
        label="N6 formal manifest",
        keys={
            "schema_version",
            "kind",
            "materialized_at",
            "offline_manifest",
            "palette_aggregate",
            "gamut_profile",
            "formal_artifact_review",
            "reviewed_limit_profile",
            "runtime_review",
            "prior_binding",
            "action",
            "execution_policy",
            "browser_contract",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != FORMAL_MANIFEST_KIND:
        raise N6VisibleExecutionError("N6 formal manifest kind/version is invalid")
    materialized_at = root["materialized_at"]
    _timestamp(materialized_at, label="N6 materialized_at")
    try:
        offline = validate_n6_offline_manifest(root["offline_manifest"])
    except N6BrowserCampaignError as error:
        raise N6VisibleExecutionError(f"embedded N6 offline manifest is invalid: {error}") from error
    aggregate, palette, profile = _measured_inputs(
        root["palette_aggregate"], root["gamut_profile"]
    )
    artifact_review = validate_n6_formal_artifact_review(
        root["formal_artifact_review"]
    )
    limit_profile = _validate_profile_for_action(
        root["reviewed_limit_profile"],
        offline_manifest=offline,
        evaluated_at=materialized_at,
    )
    runtime_review = validate_n6_runtime_review(root["runtime_review"])
    prior = _exact(
        root["prior_binding"],
        label="N6 prior binding",
        keys={
            "action_identity_sha256",
            "result_file_sha256",
            "required_state",
            "result",
        },
    )
    if prior["required_state"] != ResultState.PASS.value:
        raise N6VisibleExecutionError("N6 prior binding must require PASS")
    prior_result, prior_sha = _prior_binding(
        prior["result"],
        prior["result_file_sha256"],
        limit_profile=limit_profile,
    )
    if prior["action_identity_sha256"] != prior_result["action_identity_sha256"]:
        raise N6VisibleExecutionError("N6 prior action identity changed")
    _static_bindings(
        offline,
        aggregate,
        palette,
        profile,
        artifact_review,
        limit_profile,
        runtime_review,
        prior_result,
        prior_sha,
    )
    if root["action"] != offline["p0_campaign"]["actions"][0]:
        raise N6VisibleExecutionError("N6 formal action differs from its P0 declaration")
    if root["execution_policy"] != _EXECUTION_POLICY:
        raise N6VisibleExecutionError("N6 fixed execution policy changed")
    if root["browser_contract"] != runtime_review["browser_contract"]:
        raise N6VisibleExecutionError("N6 browser contract differs from reviewed runtime")
    if root["classification"] != _MATERIALIZED_CLASSIFICATION:
        raise N6VisibleExecutionError("N6 materialized classification changed")
    _check_integrity(root, label="N6 formal manifest")
    return root


def n6_formal_manifest_file_sha256(manifest: Mapping[str, Any]) -> str:
    return _canonical_sha256(validate_n6_formal_manifest(manifest))


def measured_palette_from_n6_manifest(manifest: Mapping[str, Any]) -> Palette:
    root = validate_n6_formal_manifest(manifest)
    try:
        return palette_from_mapping(root["palette_aggregate"]["palette"])
    except PaletteError as error:  # pragma: no cover - deep validator already checked
        raise N6VisibleExecutionError(f"embedded measured palette is invalid: {error}") from error


def measured_gamut_profile_from_n6_manifest(manifest: Mapping[str, Any]) -> GamutProfile:
    root = validate_n6_formal_manifest(manifest)
    palette = measured_palette_from_n6_manifest(root)
    try:
        return gamut_profile_from_mapping(root["gamut_profile"], palette)
    except GamutProfileError as error:  # pragma: no cover - deep validator already checked
        raise N6VisibleExecutionError(f"embedded measured profile is invalid: {error}") from error


def validate_n6_runtime_artifact(
    manifest: Mapping[str, Any], artifact: ApplicationArtifact
) -> Mapping[str, Any]:
    """Revalidate and bind the browser-created four-preview artifact exactly."""

    root = validate_n6_formal_manifest(manifest)
    if type(artifact) is not ApplicationArtifact:
        raise N6VisibleExecutionError("N6 runtime artifact must be an ApplicationArtifact")
    try:
        snapshot = artifact.validated_snapshot()
    except (ApplicationError, AttributeError, TypeError) as error:
        raise N6VisibleExecutionError(f"N6 runtime artifact is invalid: {error}") from error
    expected = root["offline_manifest"]["source_artifact"]
    if snapshot.identity != expected["artifact_identity"]:
        raise N6VisibleExecutionError("runtime artifact identity differs from formal manifest")
    report = snapshot.report
    if (
        report["input"].get("sha256") != expected["input"]["sha256"]
        or report["input"].get("media_type") != expected["input"]["media_type"]
        or report["normalization"].get("fit") != expected["geometry"]["fit"]
        or report["normalization"].get("explicit_rotation_degrees")
        != expected["geometry"]["rotation_degrees"]
    ):
        raise N6VisibleExecutionError("runtime source/geometry binding changed")
    if (
        report.get("purpose") != "offline_preview"
        or report.get("formal_upload_authorized") is not False
        or snapshot.upload_authorized is not False
        or report.get("hardware_tested") is not False
    ):
        raise N6VisibleExecutionError(
            "N6 runtime artifact must retain its offline report; external review is separate"
        )
    preview_payloads = {
        "source": snapshot.source_preview_png,
        "mapped": snapshot.mapped_preview_png,
        "final": snapshot.preview_png,
        "model": snapshot.model_preview_png,
    }
    for stage, payload in preview_payloads.items():
        actual_sha = hashlib.sha256(payload).hexdigest()
        if (
            actual_sha != expected["previews"][stage]["sha256"]
            or actual_sha != report["previews"][stage]["sha256"]
        ):
            raise N6VisibleExecutionError(f"runtime {stage} preview binding changed")
    if hashlib.sha256(snapshot.frame).hexdigest() != root["action"]["identity"]["frame"]["sha256"]:
        raise N6VisibleExecutionError("runtime frame differs from fixed N6 action")
    return {
        "artifact_identity": _snapshot(snapshot.identity),
        "source_input_sha256": report["input"]["sha256"],
        "four_preview_sha256": {
            stage: hashlib.sha256(payload).hexdigest()
            for stage, payload in preview_payloads.items()
        },
        "frame_sha256": hashlib.sha256(snapshot.frame).hexdigest(),
        "frame_fnv1a": fnv1a(snapshot.frame),
        "external_formal_review_canonical_sha256": root["formal_artifact_review"][
            "integrity"
        ]["canonical_sha256"],
    }


def seal_n6_external_authorization(
    payload: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Seal externally captured authorization; this does not solicit or grant it."""

    root = _seal(payload)
    validate_n6_external_authorization(root, manifest=manifest)
    return root


def validate_n6_external_authorization(
    record: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    root = _exact(
        record,
        label="N6 external authorization",
        keys={
            "schema_version",
            "kind",
            "authorization_id",
            "formal_manifest_canonical_sha256",
            "action_identity_sha256",
            "prior_result_file_sha256",
            "issued_at",
            "expires_at",
            "operator_id",
            "authorization_artifact_sha256",
            "confirmation_sha256",
            "maximum_frame_posts",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != AUTHORIZATION_KIND:
        raise N6VisibleExecutionError("N6 external authorization kind/version is invalid")
    _token(root["authorization_id"], label="authorization_id")
    _text(root["operator_id"], label="authorization operator_id", maximum=256)
    if (
        root["formal_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["action_identity_sha256"]
        != manifest_root["action"]["action_identity_sha256"]
        or root["prior_result_file_sha256"]
        != manifest_root["prior_binding"]["result_file_sha256"]
    ):
        raise N6VisibleExecutionError("N6 external authorization binding changed")
    issued = _timestamp(root["issued_at"], label="authorization issued_at")
    expires = _timestamp(root["expires_at"], label="authorization expires_at")
    if expires <= issued:
        raise N6VisibleExecutionError("N6 authorization validity interval is empty")
    _hash(
        root["authorization_artifact_sha256"],
        label="authorization artifact SHA-256",
    )
    confirmation_sha = _hash(
        root["confirmation_sha256"], label="authorization confirmation SHA-256"
    )
    if confirmation_sha != hashlib.sha256(N6_ARM_CONFIRMATION.encode("utf-8")).hexdigest():
        raise N6VisibleExecutionError("authorization does not bind the exact N6 arm phrase")
    if (
        root["maximum_frame_posts"] != 1
        or type(root["maximum_frame_posts"]) is not int
        or root["automatic_retry_authorized"] is not False
        or root["automatic_recovery_authorized"] is not False
    ):
        raise N6VisibleExecutionError("authorization differs from one-POST/no-recovery policy")
    _check_integrity(root, label="N6 external authorization")
    return root


def seal_n6_runtime_observation(
    payload: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Seal caller-observed live electrical/operator gates."""

    root = _seal(payload)
    validate_n6_runtime_observation(root, manifest=manifest)
    return root


def _loopback_origin(value: Any, *, label: str) -> str:
    origin = _text(value, label=label, maximum=256)
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as error:
        raise N6VisibleExecutionError(
            f"{label} must contain a valid explicit port"
        ) from error
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or port is None
    ):
        raise N6VisibleExecutionError(f"{label} must be an explicit HTTP loopback origin")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as error:
        raise N6VisibleExecutionError(f"{label} must use a numeric loopback host") from error
    if not address.is_loopback:
        raise N6VisibleExecutionError(f"{label} must use a loopback host")
    return origin


def validate_n6_runtime_observation(
    record: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    root = _exact(
        record,
        label="N6 runtime observation",
        keys={
            "schema_version",
            "kind",
            "formal_manifest_canonical_sha256",
            "observed_at",
            "controller_voltage_v",
            "idle_current_a",
            "start_temperature_c",
            "supply_3v3_normal",
            "supply_cv_current_normal",
            "j2_on",
            "physical_cutoff_available",
            "operator_present",
            "application_origin",
            "operator_gate_artifact_sha256",
            "runtime_evidence_sha256",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != RUNTIME_OBSERVATION_KIND:
        raise N6VisibleExecutionError("N6 runtime observation kind/version is invalid")
    if root["formal_manifest_canonical_sha256"] != manifest_root["integrity"]["canonical_sha256"]:
        raise N6VisibleExecutionError("N6 runtime observation manifest binding changed")
    _timestamp(root["observed_at"], label="runtime observed_at")
    device = manifest_root["runtime_review"]["device_contract"]
    voltage = _number(
        root["controller_voltage_v"],
        label="runtime controller voltage",
        minimum=0,
        maximum=10,
    )
    idle_current = _number(
        root["idle_current_a"], label="runtime idle current", minimum=0, maximum=100
    )
    temperature = _number(
        root["start_temperature_c"],
        label="runtime start temperature",
        minimum=-100,
        maximum=200,
    )
    if not float(device["minimum_controller_voltage_v"]) <= voltage <= float(
        device["maximum_controller_voltage_v"]
    ):
        raise N6VisibleExecutionError("runtime controller voltage is outside reviewed limits")
    if idle_current > float(device["maximum_idle_current_a"]):
        raise N6VisibleExecutionError("runtime idle current exceeds reviewed maximum")
    limits = manifest_root["reviewed_limit_profile"]["limits"]
    if not float(limits["minimum_start_temperature_c"]) <= temperature <= float(
        limits["maximum_start_temperature_c"]
    ):
        raise N6VisibleExecutionError("runtime start temperature is outside reviewed limits")
    for field in (
        "supply_3v3_normal",
        "supply_cv_current_normal",
        "j2_on",
        "physical_cutoff_available",
        "operator_present",
    ):
        if root[field] is not True:
            raise N6VisibleExecutionError(f"runtime gate {field} is not true")
    _loopback_origin(root["application_origin"], label="runtime application_origin")
    _hash(root["operator_gate_artifact_sha256"], label="operator gate artifact")
    _hash(root["runtime_evidence_sha256"], label="runtime evidence")
    _check_integrity(root, label="N6 runtime observation")
    return root


def validate_n6_browser_chain_observation(record: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _exact(
        record,
        label="N6 browser chain observation",
        keys={
            "source_conversion_bound",
            "source_input_sha256",
            "artifact_report_sha256",
            "preview_stages_verified",
            "page_load_count",
            "reload_count",
            "token_validated",
            "same_origin_mutations_validated",
            "local_preflight_only",
            "one_shot_arm_count",
            "execute_request_count",
            "browser_evidence_sha256",
        },
    )
    if root["source_conversion_bound"] is not True:
        raise N6VisibleExecutionError("browser source/convert chain is not bound")
    _hash(root["source_input_sha256"], label="browser source input")
    _hash(root["artifact_report_sha256"], label="browser artifact report")
    if root["preview_stages_verified"] != list(_PREVIEW_STAGES):
        raise N6VisibleExecutionError("browser did not verify all four preview stages in order")
    for field, minimum in (
        ("page_load_count", 1),
        ("reload_count", 0),
        ("one_shot_arm_count", 1),
        ("execute_request_count", 1),
    ):
        value = root[field]
        if type(value) is not int or value < minimum:
            raise N6VisibleExecutionError(f"browser {field} is invalid")
    if root["one_shot_arm_count"] != 1 or root["execute_request_count"] != 1:
        raise N6VisibleExecutionError("browser arm/execute must each occur exactly once")
    for field in (
        "token_validated",
        "same_origin_mutations_validated",
        "local_preflight_only",
    ):
        if root[field] is not True:
            raise N6VisibleExecutionError(f"browser security gate {field} is not true")
    browser_sha = _hash(root["browser_evidence_sha256"], label="browser chain evidence")
    unsigned = dict(root)
    unsigned.pop("browser_evidence_sha256")
    if browser_sha != _canonical_sha256(unsigned):
        raise N6VisibleExecutionError("browser chain evidence SHA-256 does not match")
    return root


def _claim_payload(
    manifest: Mapping[str, Any],
    authorization: Mapping[str, Any],
    runtime_observation: Mapping[str, Any],
    browser_observation: Mapping[str, Any],
    artifact_binding: Mapping[str, Any],
    *,
    attempt_id: str,
    claimed_at: str,
) -> dict[str, Any]:
    action = manifest["action"]
    declaration = action["claim"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": declaration["registry_id"],
        "workspace_relative_registry": declaration["workspace_relative_registry"],
        "filename": declaration["filename"],
        "attempt_id": attempt_id,
        "action_identity_sha256": action["action_identity_sha256"],
        "formal_manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "authorization_id": authorization["authorization_id"],
        "authorization_canonical_sha256": authorization["integrity"]["canonical_sha256"],
        "runtime_observation_canonical_sha256": runtime_observation["integrity"][
            "canonical_sha256"
        ],
        "browser_evidence_sha256": browser_observation["browser_evidence_sha256"],
        "artifact_report_sha256": artifact_binding["artifact_identity"]["report_sha256"],
        "prior_result_file_sha256": manifest["prior_binding"]["result_file_sha256"],
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "atomic_create_mode": "exclusive-create-before-any-device-network",
        "maximum_frame_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def validate_n6_claim_record(
    record: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    root = _exact(
        record,
        label="N6 consumed claim",
        keys={
            "schema_version",
            "kind",
            "registry_id",
            "workspace_relative_registry",
            "filename",
            "attempt_id",
            "action_identity_sha256",
            "formal_manifest_canonical_sha256",
            "authorization_id",
            "authorization_canonical_sha256",
            "runtime_observation_canonical_sha256",
            "browser_evidence_sha256",
            "artifact_report_sha256",
            "prior_result_file_sha256",
            "claimed_at",
            "state",
            "authorization_consumed_permanently",
            "atomic_create_mode",
            "maximum_frame_posts",
            "automatic_retry_authorized",
            "automatic_recovery_authorized",
        },
    )
    action = manifest_root["action"]
    declaration = workspace_global_claim_declaration(action["action_identity_sha256"])
    if any(root[field] != declaration[field] for field in ("registry_id", "workspace_relative_registry", "filename")):
        raise N6VisibleExecutionError("N6 consumed claim registry binding changed")
    _token(root["attempt_id"], label="claim attempt_id")
    for field in (
        "action_identity_sha256",
        "formal_manifest_canonical_sha256",
        "authorization_canonical_sha256",
        "runtime_observation_canonical_sha256",
        "browser_evidence_sha256",
        "artifact_report_sha256",
        "prior_result_file_sha256",
    ):
        _hash(root[field], label=f"claim {field}")
    if (
        root["action_identity_sha256"] != action["action_identity_sha256"]
        or root["formal_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["prior_result_file_sha256"]
        != manifest_root["prior_binding"]["result_file_sha256"]
        or root["state"] != "authorization_permanently_consumed_do_not_rerun"
        or root["authorization_consumed_permanently"] is not True
        or root["atomic_create_mode"] != "exclusive-create-before-any-device-network"
        or root["maximum_frame_posts"] != 1
        or type(root["maximum_frame_posts"]) is not int
        or root["automatic_retry_authorized"] is not False
        or root["automatic_recovery_authorized"] is not False
    ):
        raise N6VisibleExecutionError("N6 consumed claim fixed binding changed")
    _text(root["authorization_id"], label="claim authorization_id", maximum=256)
    _timestamp(root["claimed_at"], label="claim claimed_at")
    return root


@dataclass(frozen=True)
class N6ClaimCommit:
    record: Mapping[str, Any]
    file_sha256: str
    path: Path


class AtomicN6ClaimStore:
    """Exclusive-create claim writer rooted at an explicit workspace path."""

    def __init__(self, workspace_root: str | Path) -> None:
        root = Path(workspace_root).resolve(strict=True)
        if not root.is_dir():
            raise N6VisibleExecutionError("N6 claim workspace root must be a directory")
        self.workspace_root = root

    def claim_path(self, manifest: Mapping[str, Any]) -> Path:
        """Resolve the exact claim path without creating directories or files."""

        root = validate_n6_formal_manifest(manifest)
        declaration = root["action"]["claim"]
        registry_candidate = self.workspace_root / declaration[
            "workspace_relative_registry"
        ]
        registry = registry_candidate.resolve(strict=False)
        try:
            registry.relative_to(self.workspace_root)
        except ValueError as error:
            raise N6VisibleExecutionError("N6 claim registry escapes workspace") from error
        destination = registry / declaration["filename"]
        try:
            destination.relative_to(registry)
        except ValueError as error:
            raise N6VisibleExecutionError("N6 claim filename escapes registry") from error
        return destination

    def prepare_registry(self, manifest: Mapping[str, Any]) -> Path:
        """Durably create the fixed claim directory tree before claim time."""

        root = validate_n6_formal_manifest(manifest)
        declaration = root["action"]["claim"]
        registry_candidate = self.workspace_root / declaration[
            "workspace_relative_registry"
        ]
        registry = registry_candidate.resolve(strict=False)
        try:
            registry.relative_to(self.workspace_root)
        except ValueError as error:
            raise N6VisibleExecutionError("N6 claim registry escapes workspace") from error
        try:
            return ensure_directory_tree_durable(
                registry_candidate, root=self.workspace_root
            )
        except OSError as error:
            raise N6VisibleExecutionError(
                f"could not durably prepare N6 claim registry: {error}"
            ) from error

    def commit(
        self, manifest: Mapping[str, Any], claim: Mapping[str, Any]
    ) -> N6ClaimCommit:
        root = validate_n6_formal_manifest(manifest)
        claim_root = validate_n6_claim_record(claim, manifest=root)
        declaration = root["action"]["claim"]
        registry_candidate = self.workspace_root / declaration[
            "workspace_relative_registry"
        ]
        registry = registry_candidate.resolve(strict=False)
        try:
            registry.relative_to(self.workspace_root)
        except ValueError as error:
            raise N6VisibleExecutionError("N6 claim registry escapes workspace") from error
        registry = self.prepare_registry(root)
        destination = registry / declaration["filename"]
        try:
            destination.relative_to(registry)
        except ValueError as error:
            raise N6VisibleExecutionError("N6 claim filename escapes registry") from error
        payload = canonical_json_bytes(claim_root) + b"\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            descriptor = os.open(destination, flags, 0o600)
        except FileExistsError as error:
            raise N6ClaimConsumed(
                "this exact N6 action claim is permanently consumed; do not retry"
            ) from error
        except OSError as error:
            raise N6VisibleExecutionError(f"could not atomically create N6 claim: {error}") from error
        claim_commit = N6ClaimCommit(
            record=_snapshot(claim_root),
            file_sha256=hashlib.sha256(payload).hexdigest(),
            path=destination,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            fsync_directory(registry)
        except BaseException as error:
            # Exclusive creation may already have made a permanent claim.  Do
            # not delete or retry a partially written claim.
            raise N6ClaimWriteOutcomeUnknown(
                "N6 claim write outcome is unknown; do not retry",
                claim_commit=claim_commit,
            ) from error
        return claim_commit


class N6ProtocolDriver(Protocol):
    def __call__(
        self,
        frame: bytes,
        mappings: Sequence[ControllerMapping],
    ) -> Mapping[str, Any]: ...


class N6HttpRefreshDriver:
    """One-call wrapper around the audited one-POST protocol implementation."""

    def __init__(
        self,
        device_url: str,
        *,
        requester: Optional[frame_tool.HttpRequester] = None,
        job_timeout_s: float = frame_tool.DEFAULT_JOB_TIMEOUT_S,
        poll_interval_s: float = frame_tool.DEFAULT_POLL_INTERVAL_S,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        try:
            self._device_url = frame_tool._normalize_base_url(device_url)
        except frame_tool.FrameToolError as error:
            raise N6VisibleExecutionError(str(error)) from error
        self._requester = requester or frame_tool.http_request
        self._job_timeout_s = job_timeout_s
        self._poll_interval_s = poll_interval_s
        self._sleeper = sleeper
        self._clock = clock
        self.frame_post_request_count = 0
        self.total_request_count = 0

    def __call__(
        self, frame: bytes, mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        if self.total_request_count or self.frame_post_request_count:
            raise N6TransportOutcomeUnknown(
                "N6 protocol driver instance is one-shot and already used",
                frame_post_request_count=self.frame_post_request_count,
            )

        def counted_requester(
            base_url: str, endpoint: str, **kwargs: Any
        ) -> tuple[int, str]:
            self.total_request_count += 1
            if kwargs.get("method", "GET") == "POST" and endpoint == "/api/frame":
                self.frame_post_request_count += 1
                if self.frame_post_request_count > 1:
                    raise frame_tool.FrameToolError("second N6 frame POST is forbidden")
            return self._requester(base_url, endpoint, **kwargs)

        kwargs: dict[str, Any] = {
            "expected_mappings": tuple(mappings),
            "job_timeout_s": self._job_timeout_s,
            "poll_interval_s": self._poll_interval_s,
            "requester": counted_requester,
        }
        if self._sleeper is not None:
            kwargs["sleeper"] = self._sleeper
        if self._clock is not None:
            kwargs["clock"] = self._clock
        try:
            result = frame_tool.perform_refresh(self._device_url, frame, **kwargs)
        except (frame_tool.FrameToolError, frame_tool.FrameToolNetworkError) as error:
            raise N6TransportOutcomeUnknown(
                str(error), frame_post_request_count=min(self.frame_post_request_count, 1)
            ) from error
        if self.frame_post_request_count != 1:
            raise N6TransportOutcomeUnknown(
                "protocol returned without exactly one frame POST",
                frame_post_request_count=min(self.frame_post_request_count, 1),
            )
        return {**result, "frame_post_request_count": 1}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class N6BrowserExecutionController:
    """Server-side one-shot state for the real loopback browser chain.

    Preflight is intentionally local: no device request is made until
    :meth:`enqueue` enters :func:`execute_n6_formal_once`, whose first side
    effect is the atomic workspace-global claim.
    """

    def __init__(
        self,
        manifest: Mapping[str, Any],
        *,
        authorization: Mapping[str, Any],
        claim_store: AtomicN6ClaimStore,
        protocol_driver: N6ProtocolDriver,
        attempt_id: str,
        runtime_observation: Mapping[str, Any] | None = None,
        utc_now: Callable[[], str] = _utc_now_text,
    ) -> None:
        self.manifest = _snapshot(validate_n6_formal_manifest(manifest))
        self.authorization = _snapshot(
            validate_n6_external_authorization(authorization, manifest=self.manifest)
        )
        _token(attempt_id, label="browser controller attempt_id")
        if not callable(utc_now):
            raise N6VisibleExecutionError("browser controller utc_now must be callable")
        self.claim_store = claim_store
        self.protocol_driver = protocol_driver
        self.attempt_id = attempt_id
        self._utc_now = utc_now
        self._lock = threading.RLock()
        self._runtime_observation: Mapping[str, Any] | None = None
        self._server_origin: str | None = None
        self._artifact: ApplicationArtifact | None = None
        self._artifact_binding: Mapping[str, Any] | None = None
        self._artifact_error: str | None = None
        self._preview_stages: set[str] = set()
        self._page_load_count = 0
        self._token_validated = False
        self._same_origin_mutations_validated = False
        self._connection_allowed = False
        self._preflight_verified = False
        self._armed = False
        self._arm_count = 0
        self._execute_request_count = 0
        self._execution_started = False
        self._report_retrieved = False
        self._receipt: Mapping[str, Any] | None = None
        self._last_error: str | None = None
        if runtime_observation is not None:
            self.set_runtime_observation(runtime_observation)

    @property
    def receipt(self) -> Mapping[str, Any] | None:
        with self._lock:
            return None if self._receipt is None else _snapshot(self._receipt)

    def bind_server_origin(self, origin: str) -> None:
        with self._lock:
            normalized = _loopback_origin(origin, label="N6 server origin")
            if self._server_origin is not None and self._server_origin != normalized:
                raise N6VisibleExecutionError("N6 server origin cannot change")
            if (
                self._runtime_observation is not None
                and self._runtime_observation["application_origin"] != normalized
            ):
                raise N6VisibleExecutionError(
                    "N6 runtime observation origin differs from bound browser server"
                )
            self._server_origin = normalized

    def set_runtime_observation(self, observation: Mapping[str, Any]) -> None:
        with self._lock:
            if self._execution_started:
                raise N6VisibleExecutionError("N6 runtime observation is frozen after execution starts")
            root = validate_n6_runtime_observation(observation, manifest=self.manifest)
            if self._server_origin is not None and root["application_origin"] != self._server_origin:
                raise N6VisibleExecutionError(
                    "N6 runtime observation origin differs from bound browser server"
                )
            self._runtime_observation = _snapshot(root)

    def record_page_load(self) -> None:
        with self._lock:
            self._page_load_count += 1

    def record_authenticated_read(self) -> None:
        with self._lock:
            self._token_validated = True

    def observe_artifact(self, artifact: ApplicationArtifact) -> bool:
        with self._lock:
            if self._execution_started:
                raise N6VisibleExecutionError("N6 artifact cannot change after execution starts")
            self._artifact = artifact
            self._preview_stages.clear()
            self._connection_allowed = False
            self._preflight_verified = False
            self._armed = False
            try:
                self._artifact_binding = validate_n6_runtime_artifact(
                    self.manifest, artifact
                )
            except N6VisibleExecutionError as error:
                self._artifact_binding = None
                self._artifact_error = str(error)
                return False
            self._artifact_error = None
            return True

    def invalidate_artifact(self) -> None:
        with self._lock:
            if self._execution_started:
                # Page reload/invalidation can hide previews, but must never
                # erase a consumed claim or submission state.
                self._artifact = None
                self._artifact_binding = None
                self._preview_stages.clear()
                self._armed = False
                return
            self._artifact = None
            self._artifact_binding = None
            self._artifact_error = None
            self._preview_stages.clear()
            self._connection_allowed = False
            self._preflight_verified = False
            self._armed = False

    def record_preview_fetch(self, report_sha256: str, stage: str) -> None:
        with self._lock:
            if self._artifact_binding is None:
                return
            if stage not in _PREVIEW_STAGES:
                raise N6VisibleExecutionError("N6 preview stage is invalid")
            if report_sha256 != self._artifact_binding["artifact_identity"]["report_sha256"]:
                raise N6VisibleExecutionError("N6 preview report identity changed")
            self._preview_stages.add(stage)

    def _security(self, *, token_validated: bool, same_origin_validated: bool) -> None:
        if token_validated is not True or same_origin_validated is not True:
            raise N6VisibleExecutionError("N6 formal mutation lacks token/same-origin validation")
        self._token_validated = True
        self._same_origin_mutations_validated = True

    def allow_connection(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if self._execution_started:
                raise N6VisibleExecutionError("N6 connection cannot be changed after execution")
            if self._artifact_binding is None:
                raise N6VisibleExecutionError("exact formal N6 browser artifact is not present")
            self._connection_allowed = True
            self._preflight_verified = False
            self._armed = False
            return {
                "connection_allowed": True,
                "local_preflight_only": True,
                "device_network_requests": 0,
                "artifact_identity": _snapshot(self._artifact_binding["artifact_identity"]),
                "hardware_tested": False,
            }

    def local_preflight(
        self,
        mappings: Sequence[ControllerMapping],
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if not self._connection_allowed or self._artifact_binding is None:
                raise N6VisibleExecutionError("N6 local preflight requires exact artifact and allow")
            if tuple(mappings) != DEFAULT_MAPPINGS:
                raise N6VisibleExecutionError("N6 local preflight mappings differ from fixed CS1/CS2")
            if self._preview_stages != set(_PREVIEW_STAGES):
                raise N6VisibleExecutionError("N6 local preflight requires all four fetched previews")
            if self._execution_started:
                raise N6VisibleExecutionError("N6 local preflight is closed after execution")
            self._preflight_verified = True
            self._armed = False
            firmware = self.manifest["offline_manifest"]["p0_campaign"]["firmware"]
            return {
                "build_tag": firmware["build_tag"],
                "driver_api": firmware["driver_api"],
                "artifact_identity": _snapshot(self._artifact_binding["artifact_identity"]),
                "local_preflight_only": True,
                "device_network_requests": 0,
                "protocol_verified": False,
                "hardware_tested": False,
            }

    def arm(
        self,
        confirmation: str,
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if confirmation != N6_ARM_CONFIRMATION:
                raise N6VisibleExecutionError(
                    f"N6 arm phrase must exactly equal {N6_ARM_CONFIRMATION!r}"
                )
            if not self._preflight_verified or self._artifact_binding is None:
                raise N6VisibleExecutionError("N6 arm requires the exact local preflight")
            if self._arm_count != 0 or self._execution_started:
                raise N6VisibleExecutionError("N6 one-shot arm has already been consumed")
            self._armed = True
            self._arm_count = 1
            return {
                "armed": True,
                "one_shot": True,
                "artifact_identity": _snapshot(self._artifact_binding["artifact_identity"]),
                "request_sent": False,
                "hardware_tested": False,
            }

    def _browser_observation(self) -> dict[str, Any]:
        if self._artifact_binding is None:
            raise N6VisibleExecutionError("N6 browser artifact is absent")
        payload = {
            "source_conversion_bound": True,
            "source_input_sha256": self._artifact_binding["source_input_sha256"],
            "artifact_report_sha256": self._artifact_binding["artifact_identity"][
                "report_sha256"
            ],
            "preview_stages_verified": list(_PREVIEW_STAGES),
            "page_load_count": self._page_load_count,
            "reload_count": max(0, self._page_load_count - 1),
            "token_validated": self._token_validated,
            "same_origin_mutations_validated": self._same_origin_mutations_validated,
            "local_preflight_only": True,
            "one_shot_arm_count": self._arm_count,
            "execute_request_count": self._execute_request_count,
        }
        payload["browser_evidence_sha256"] = _canonical_sha256(payload)
        validate_n6_browser_chain_observation(payload)
        return payload

    def enqueue(
        self,
        mappings: Sequence[ControllerMapping],
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        """Fail closed on the obsolete self-sealed live surface.

        The implementation remains available only to the physical/production
        wrapper and legacy offline tests through the deliberately private
        ``_enqueue_legacy_test_only`` method below.  Calling this public method
        never creates a claim and never reaches the protocol driver.
        """

        del mappings, token_validated, same_origin_validated
        raise N6VisibleExecutionError(LEGACY_N6_ENQUEUE_BLOCK_MESSAGE)

    def _enqueue_legacy_test_only(
        self,
        mappings: Sequence[ControllerMapping],
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if tuple(mappings) != DEFAULT_MAPPINGS:
                raise N6VisibleExecutionError("N6 enqueue mappings differ from local preflight")
            if (
                not self._armed
                or not self._preflight_verified
                or self._artifact is None
                or self._artifact_binding is None
                or self._runtime_observation is None
                or self._server_origin is None
            ):
                raise N6VisibleExecutionError("N6 enqueue gates are incomplete")
            if self._runtime_observation["application_origin"] != self._server_origin:
                raise N6VisibleExecutionError("N6 runtime/browser origin binding changed")
            if self._execution_started or self._execute_request_count != 0:
                raise N6VisibleExecutionError("N6 duplicate submission is permanently locked")
            self._armed = False
            self._preflight_verified = False
            self._execution_started = True
            self._execute_request_count = 1
            claimed_at = self._utc_now()
            artifact = self._artifact
            artifact_identity = _snapshot(self._artifact_binding["artifact_identity"])
            runtime_observation = _snapshot(self._runtime_observation)
            browser_observation = self._browser_observation()
        try:
            receipt = execute_n6_formal_once(
                self.manifest,
                artifact,
                authorization=self.authorization,
                runtime_observation=runtime_observation,
                browser_observation=browser_observation,
                arm_confirmation=N6_ARM_CONFIRMATION,
                attempt_id=self.attempt_id,
                claimed_at=claimed_at,
                completed_at=self._utc_now,
                claim_store=self.claim_store,
                protocol_driver=self.protocol_driver,
            )
        except N6PostClaimUnknown as error:
            with self._lock:
                self._receipt = _snapshot(error.receipt)
                self._last_error = str(error)
            raise
        except N6VisibleExecutionError as error:
            with self._lock:
                self._last_error = str(error)
            raise
        with self._lock:
            self._receipt = _snapshot(receipt)
            self._last_error = None
            return {
                "accepted": True,
                "http_status": 202,
                "state": "queued",
                "statement": "one POST consumed; matching terminal job/report already captured",
                "artifact_identity": artifact_identity,
                "protocol_verified": False,
                "hardware_tested": False,
            }

    def poll_job(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if self._receipt is None:
                raise N6VisibleExecutionError("N6 has no protocol receipt")
            receipt = validate_n6_protocol_receipt(
                self._receipt, manifest=self.manifest
            )
            if receipt["state"] != "PROTOCOL_VERIFIED_PENDING_MANUAL":
                raise N6VisibleExecutionError("N6 outcome is UNKNOWN_DO_NOT_RETRY")
            return {
                "state": "completed_pending_report",
                "job": _snapshot(receipt["protocol_evidence"]["job"]),
                "artifact_identity": _snapshot(receipt["artifact_binding"]["artifact_identity"]),
                "protocol_verified": False,
                "hardware_tested": False,
            }

    def diagnostic_report(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        with self._lock:
            self._security(
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
            if self._receipt is None:
                raise N6VisibleExecutionError("N6 has no protocol receipt")
            receipt = validate_n6_protocol_receipt(
                self._receipt, manifest=self.manifest
            )
            if receipt["state"] != "PROTOCOL_VERIFIED_PENDING_MANUAL":
                raise N6VisibleExecutionError("N6 outcome is UNKNOWN_DO_NOT_RETRY")
            self._report_retrieved = True
            protocol = receipt["protocol_evidence"]
            return {
                **_snapshot(protocol),
                "state": "protocol_verified",
                "artifact_identity": _snapshot(receipt["artifact_binding"]["artifact_identity"]),
                "n6_protocol_receipt_canonical_sha256": receipt["integrity"][
                    "canonical_sha256"
                ],
            }

    def status_overlay(self, base_status: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            status = dict(base_status)
            unknown = bool(
                self._receipt is not None
                and self._receipt.get("state") == ResultState.UNKNOWN_DO_NOT_RETRY.value
            )
            protocol_verified = bool(
                self._receipt is not None
                and self._receipt.get("state") == "PROTOCOL_VERIFIED_PENDING_MANUAL"
                and self._report_retrieved
            )
            refresh_locked = bool(
                unknown
                or (self._execution_started and not self._report_retrieved)
            )
            state = (
                ResultState.UNKNOWN_DO_NOT_RETRY.value
                if unknown
                else (
                    "protocol_verified"
                    if protocol_verified
                    else (
                        "completed_pending_report"
                        if self._receipt is not None
                        else (
                            "armed"
                            if self._armed
                            else ("ready" if self._connection_allowed else "offline")
                        )
                    )
                )
            )
            status.update(
                {
                    "state": state,
                    "n6_formal_mode": True,
                    "formal_upload_authorized": self._artifact_binding is not None
                    and not self._execution_started,
                    "connection_allowed": self._connection_allowed,
                    "preflight_verified": self._preflight_verified,
                    "armed": self._armed,
                    "refresh_locked": refresh_locked,
                    "local_abort_quarantine": unknown,
                    "remote_job_may_continue": unknown,
                    "recovery_available": False,
                    "error": self._last_error or self._artifact_error,
                    "protocol_verified": protocol_verified,
                    "hardware_tested": False,
                    "n6_claim_consumed": self._receipt is not None,
                    "n6_frame_post_request_count": (
                        0
                        if self._receipt is None
                        else self._receipt["frame_post_request_count"]
                    ),
                    "n6_automatic_retry_count": 0,
                    "n6_automatic_recovery_count": 0,
                }
            )
            return status

    @staticmethod
    def forbidden_recovery() -> Mapping[str, Any]:
        raise N6VisibleExecutionError("N6 fixed action has no cancel, retry, or recovery path")



def _validate_driver_success(
    result: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise N6TransportOutcomeUnknown(
            "N6 protocol driver result is not an object", frame_post_request_count=1
        )
    root = _snapshot(result)
    if (
        root.get("mode") != "refresh"
        or root.get("protocol_verified") is not True
        or root.get("hardware_tested") is not False
        or root.get("frame_post_request_count") != 1
        or type(root.get("frame_post_request_count")) is not int
    ):
        raise N6TransportOutcomeUnknown(
            "N6 protocol driver did not return one-POST verified evidence",
            frame_post_request_count=1,
        )
    preflight = root.get("preflight")
    job = root.get("job")
    diagnostic = root.get("diagnostic")
    if not isinstance(preflight, Mapping) or not isinstance(job, Mapping) or not isinstance(
        diagnostic, Mapping
    ):
        raise N6TransportOutcomeUnknown(
            "N6 protocol evidence omits preflight/job/diagnostic",
            frame_post_request_count=1,
        )
    firmware = manifest["offline_manifest"]["p0_campaign"]["firmware"]
    if (
        preflight.get("build_tag") != firmware["build_tag"]
        or preflight.get("driver_api") != firmware["driver_api"]
        or preflight.get("frame_bytes") != FRAME_BYTES
        or preflight.get("controller_mappings")
        != [
            {"controller": "CS1", "mapping": _FIXED_MAPPING_RECORDS[0]},
            {"controller": "CS2", "mapping": _FIXED_MAPPING_RECORDS[1]},
        ]
    ):
        raise N6TransportOutcomeUnknown(
            "N6 firmware preflight differs from panel/build/mapping binding",
            frame_post_request_count=1,
        )
    job_id = root.get("job_id")
    if type(job_id) is not int or job_id < 1:
        raise N6TransportOutcomeUnknown(
            "N6 protocol job_id is invalid", frame_post_request_count=1
        )
    try:
        state = frame_tool._validate_job(
            job,
            job_id,
            int(manifest["action"]["identity"]["frame"]["fnv1a"][2:], 16),
        )
    except frame_tool.FrameToolError as error:
        raise N6TransportOutcomeUnknown(
            f"N6 terminal job evidence is invalid: {error}",
            frame_post_request_count=1,
        ) from error
    if state != "completed":
        raise N6TransportOutcomeUnknown(
            "N6 job is not terminal completed", frame_post_request_count=1
        )
    if (
        diagnostic.get("operation_id") != diagnostic.get("job_operation_id")
        or diagnostic.get("job_driver_operation_identity_matched") is not True
        or diagnostic.get("sequence_verified") is not True
        or diagnostic.get("required_busy_stages_verified") is not True
        or diagnostic.get("busy_timeout") is not False
        or diagnostic.get("safe_finish_verified") is not True
    ):
        raise N6TransportOutcomeUnknown(
            "N6 diagnostic operation/safe-finish evidence is invalid",
            frame_post_request_count=1,
        )
    physical = diagnostic.get("physical_controllers")
    if not isinstance(physical, list) or len(physical) != 2:
        raise N6TransportOutcomeUnknown(
            "N6 diagnostic physical-controller evidence is incomplete",
            frame_post_request_count=1,
        )
    expected_controllers = manifest["action"]["identity"]["frame"]["controllers"]
    for index, expected_name in enumerate(("CS1", "CS2")):
        item = physical[index]
        if not isinstance(item, Mapping):
            raise N6TransportOutcomeUnknown(
                "N6 physical controller evidence is malformed",
                frame_post_request_count=1,
            )
        expected_fnv = int(expected_controllers[index]["dtm_fnv1a"][2:], 16)
        if (
            item.get("controller") != expected_name
            or item.get("mapping") != _FIXED_MAPPING_RECORDS[index]
            or item.get("dtm_bytes") != expected_controllers[index]["dtm_bytes"]
            or item.get("dtm_fnv1a") != expected_fnv
        ):
            raise N6TransportOutcomeUnknown(
                f"N6 {expected_name} diagnostic mapping/DTM binding changed",
                frame_post_request_count=1,
            )
    required_manual = {
        "full_panel_visual_result",
        "power_supply_cv_and_current",
        "L1_L2_temperature",
    }
    if set(root.get("manual_observation_required", [])) != required_manual:
        raise N6TransportOutcomeUnknown(
            "N6 protocol evidence changed its manual-observation boundary",
            frame_post_request_count=1,
        )
    return root


def _protocol_receipt(
    *,
    manifest: Mapping[str, Any],
    authorization: Mapping[str, Any],
    runtime_observation: Mapping[str, Any],
    browser_observation: Mapping[str, Any],
    artifact_binding: Mapping[str, Any],
    claim_commit: N6ClaimCommit,
    attempt_id: str,
    claimed_at: str,
    completed_at: str,
    state: str,
    frame_post_request_count: int,
    protocol_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROTOCOL_RECEIPT_KIND,
        "formal_manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "action_identity_sha256": manifest["action"]["action_identity_sha256"],
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "completed_at": completed_at,
        "state": state,
        "authorization": _snapshot(authorization),
        "runtime_observation": _snapshot(runtime_observation),
        "browser_observation": _snapshot(browser_observation),
        "artifact_binding": _snapshot(artifact_binding),
        "claim": _snapshot(claim_commit.record),
        "claim_file_sha256": claim_commit.file_sha256,
        "protocol_evidence": _snapshot(protocol_evidence),
        "frame_post_request_count": frame_post_request_count,
        "second_frame_post_authorized": False,
        "automatic_retry_count": 0,
        "automatic_recovery_count": 0,
        "retry_allowed": False,
        "recovery_allowed": False,
        "manual_observation_required": state == "PROTOCOL_VERIFIED_PENDING_MANUAL",
    }
    root = _seal(payload)
    validate_n6_protocol_receipt(root, manifest=manifest)
    return root


def validate_n6_protocol_receipt(
    receipt: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    root = _exact(
        receipt,
        label="N6 protocol receipt",
        keys={
            "schema_version",
            "kind",
            "formal_manifest_canonical_sha256",
            "action_identity_sha256",
            "attempt_id",
            "claimed_at",
            "completed_at",
            "state",
            "authorization",
            "runtime_observation",
            "browser_observation",
            "artifact_binding",
            "claim",
            "claim_file_sha256",
            "protocol_evidence",
            "frame_post_request_count",
            "second_frame_post_authorized",
            "automatic_retry_count",
            "automatic_recovery_count",
            "retry_allowed",
            "recovery_allowed",
            "manual_observation_required",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PROTOCOL_RECEIPT_KIND:
        raise N6VisibleExecutionError("N6 protocol receipt kind/version is invalid")
    if (
        root["formal_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["action_identity_sha256"]
        != manifest_root["action"]["action_identity_sha256"]
    ):
        raise N6VisibleExecutionError("N6 protocol receipt manifest/action binding changed")
    _token(root["attempt_id"], label="protocol attempt_id")
    claimed = _timestamp(root["claimed_at"], label="protocol claimed_at")
    completed = _timestamp(root["completed_at"], label="protocol completed_at")
    if completed < claimed:
        raise N6VisibleExecutionError("N6 protocol completion precedes claim consumption")
    authorization = validate_n6_external_authorization(
        root["authorization"], manifest=manifest_root
    )
    runtime = validate_n6_runtime_observation(
        root["runtime_observation"], manifest=manifest_root
    )
    browser = validate_n6_browser_chain_observation(root["browser_observation"])
    artifact = root["artifact_binding"]
    _artifact_identity(artifact.get("artifact_identity") if isinstance(artifact, Mapping) else None, label="receipt artifact identity")
    expected_artifact = manifest_root["offline_manifest"]["source_artifact"]
    if (
        artifact.get("artifact_identity") != expected_artifact["artifact_identity"]
        or artifact.get("source_input_sha256") != expected_artifact["input"]["sha256"]
        or artifact.get("four_preview_sha256")
        != {
            stage: expected_artifact["previews"][stage]["sha256"]
            for stage in _PREVIEW_STAGES
        }
        or artifact.get("frame_sha256") != manifest_root["action"]["identity"]["frame"]["sha256"]
        or artifact.get("frame_fnv1a") != int(manifest_root["action"]["identity"]["frame"]["fnv1a"][2:], 16)
        or artifact.get("external_formal_review_canonical_sha256")
        != manifest_root["formal_artifact_review"]["integrity"]["canonical_sha256"]
    ):
        raise N6VisibleExecutionError("N6 receipt artifact binding changed")
    claim = validate_n6_claim_record(root["claim"], manifest=manifest_root)
    expected_claim_sha = hashlib.sha256(canonical_json_bytes(claim) + b"\n").hexdigest()
    if root["claim_file_sha256"] != expected_claim_sha:
        raise N6VisibleExecutionError("N6 claim whole-file SHA-256 changed")
    if (
        claim["attempt_id"] != root["attempt_id"]
        or claim["authorization_id"] != authorization["authorization_id"]
        or claim["authorization_canonical_sha256"]
        != authorization["integrity"]["canonical_sha256"]
        or claim["runtime_observation_canonical_sha256"]
        != runtime["integrity"]["canonical_sha256"]
        or claim["browser_evidence_sha256"] != browser["browser_evidence_sha256"]
        or claim["artifact_report_sha256"] != artifact["artifact_identity"]["report_sha256"]
        or claim["claimed_at"] != root["claimed_at"]
    ):
        raise N6VisibleExecutionError("N6 claim/receipt evidence binding changed")
    post_count = root["frame_post_request_count"]
    if type(post_count) is not int or post_count not in {0, 1}:
        raise N6VisibleExecutionError("N6 receipt frame POST count must be zero or one")
    if (
        root["second_frame_post_authorized"] is not False
        or root["automatic_retry_count"] != 0
        or root["automatic_recovery_count"] != 0
        or root["retry_allowed"] is not False
        or root["recovery_allowed"] is not False
    ):
        raise N6VisibleExecutionError("N6 receipt permits retry, recovery, or second POST")
    state = root["state"]
    if state == "PROTOCOL_VERIFIED_PENDING_MANUAL":
        if post_count != 1 or root["manual_observation_required"] is not True:
            raise N6VisibleExecutionError("verified N6 receipt counters are inconsistent")
        evidence = root["protocol_evidence"]
        try:
            _validate_driver_success(evidence, manifest=manifest_root)
        except N6TransportOutcomeUnknown as error:
            raise N6VisibleExecutionError(
                f"verified N6 receipt protocol evidence is invalid: {error}"
            ) from error
    elif state == ResultState.UNKNOWN_DO_NOT_RETRY.value:
        if root["manual_observation_required"] is not False:
            raise N6VisibleExecutionError("UNKNOWN N6 receipt cannot enter manual PASS flow")
        evidence = _exact(
            root["protocol_evidence"],
            label="UNKNOWN N6 protocol evidence",
            keys={"outcome", "detail", "frame_post_request_count"},
        )
        if (
            evidence["outcome"] != ResultState.UNKNOWN_DO_NOT_RETRY.value
            or evidence["frame_post_request_count"] != post_count
        ):
            raise N6VisibleExecutionError("UNKNOWN N6 protocol evidence is inconsistent")
        _text(evidence["detail"], label="UNKNOWN N6 protocol detail")
    else:
        raise N6VisibleExecutionError("N6 protocol receipt state is invalid")
    if not (
        _timestamp(authorization["issued_at"], label="authorization issued_at")
        <= claimed
        < _timestamp(authorization["expires_at"], label="authorization expires_at")
    ):
        raise N6VisibleExecutionError("N6 claim falls outside authorization validity")
    if _timestamp(runtime["observed_at"], label="runtime observed_at") > claimed:
        raise N6VisibleExecutionError("N6 runtime observation follows claim")
    _check_integrity(root, label="N6 protocol receipt")
    return root


def execute_n6_formal_once(
    manifest: Mapping[str, Any],
    artifact: ApplicationArtifact,
    *,
    authorization: Mapping[str, Any],
    runtime_observation: Mapping[str, Any],
    browser_observation: Mapping[str, Any],
    arm_confirmation: str,
    attempt_id: str,
    claimed_at: str,
    completed_at: str | Callable[[], str],
    claim_store: AtomicN6ClaimStore,
    protocol_driver: N6ProtocolDriver,
) -> dict[str, Any]:
    """Consume the global claim, then perform at most one fixed frame POST."""

    root = validate_n6_formal_manifest(manifest)
    artifact_binding = validate_n6_runtime_artifact(root, artifact)
    authorization_root = validate_n6_external_authorization(authorization, manifest=root)
    runtime_root = validate_n6_runtime_observation(runtime_observation, manifest=root)
    browser_root = validate_n6_browser_chain_observation(browser_observation)
    if arm_confirmation != N6_ARM_CONFIRMATION:
        raise N6VisibleExecutionError(f"N6 arm phrase must exactly equal {N6_ARM_CONFIRMATION!r}")
    _token(attempt_id, label="attempt_id")
    claimed_time = _timestamp(claimed_at, label="claimed_at")
    if not callable(completed_at):
        supplied_completed = _timestamp(completed_at, label="completed_at")
        if supplied_completed < claimed_time:
            raise N6VisibleExecutionError("N6 completed_at precedes claimed_at")
    if _timestamp(root["materialized_at"], label="materialized_at") > claimed_time:
        raise N6VisibleExecutionError("N6 manifest was materialized after claim time")
    if not (
        _timestamp(authorization_root["issued_at"], label="authorization issued_at")
        <= claimed_time
        < _timestamp(authorization_root["expires_at"], label="authorization expires_at")
    ):
        raise N6VisibleExecutionError("N6 authorization is not valid at claim time")
    if _timestamp(runtime_root["observed_at"], label="runtime observed_at") > claimed_time:
        raise N6VisibleExecutionError("runtime observation follows claim time")
    try:
        decision = evaluate_limit_profile(
            root["reviewed_limit_profile"], evaluated_at=claimed_at
        )
    except CampaignContractError as error:
        raise N6VisibleExecutionError(f"N6 limit profile execution evaluation failed: {error}") from error
    if not decision.hardware_ready or decision.reasons:
        raise N6VisibleExecutionError(
            "N6 reviewed limits are closed at claim time: " + ", ".join(decision.reasons)
        )
    if (
        browser_root["source_input_sha256"] != artifact_binding["source_input_sha256"]
        or browser_root["artifact_report_sha256"]
        != artifact_binding["artifact_identity"]["report_sha256"]
    ):
        raise N6VisibleExecutionError("browser observation differs from exact N6 artifact")
    if runtime_root["application_origin"] == "":  # pragma: no cover - validator rejects
        raise N6VisibleExecutionError("runtime browser origin is missing")

    claim = _claim_payload(
        root,
        authorization_root,
        runtime_root,
        browser_root,
        artifact_binding,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
    )
    def completion_timestamp() -> str:
        if not callable(completed_at):
            return completed_at
        try:
            value = completed_at()
            completed_time = _timestamp(value, label="completed_at")
        except BaseException:
            return claimed_at
        return value if completed_time >= claimed_time else claimed_at

    try:
        claim_commit = claim_store.commit(root, claim)
    except N6ClaimWriteOutcomeUnknown as error:
        completed_text = completion_timestamp()
        receipt = _protocol_receipt(
            manifest=root,
            authorization=authorization_root,
            runtime_observation=runtime_root,
            browser_observation=browser_root,
            artifact_binding=artifact_binding,
            claim_commit=error.claim_commit,
            attempt_id=attempt_id,
            claimed_at=claimed_at,
            completed_at=completed_text,
            state=ResultState.UNKNOWN_DO_NOT_RETRY.value,
            frame_post_request_count=0,
            protocol_evidence={
                "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
                "detail": str(error),
                "frame_post_request_count": 0,
            },
        )
        raise N6PostClaimUnknown(
            "N6 claim durability is unknown; claim remains consumed and no device request is allowed",
            receipt=receipt,
        ) from error

    try:
        raw_protocol = protocol_driver(artifact.frame, DEFAULT_MAPPINGS)
        protocol = _validate_driver_success(raw_protocol, manifest=root)
    except N6TransportOutcomeUnknown as error:
        completed_text = completion_timestamp()
        receipt = _protocol_receipt(
            manifest=root,
            authorization=authorization_root,
            runtime_observation=runtime_root,
            browser_observation=browser_root,
            artifact_binding=artifact_binding,
            claim_commit=claim_commit,
            attempt_id=attempt_id,
            claimed_at=claimed_at,
            completed_at=completed_text,
            state=ResultState.UNKNOWN_DO_NOT_RETRY.value,
            frame_post_request_count=error.frame_post_request_count,
            protocol_evidence={
                "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
                "detail": str(error),
                "frame_post_request_count": error.frame_post_request_count,
            },
        )
        raise N6PostClaimUnknown(
            "N6 action is UNKNOWN_DO_NOT_RETRY after permanent claim consumption",
            receipt=receipt,
        ) from error
    except BaseException as error:
        # An untyped driver exception cannot prove whether the request reached
        # the device.  Conservatively account for the one permitted POST.
        completed_text = completion_timestamp()
        receipt = _protocol_receipt(
            manifest=root,
            authorization=authorization_root,
            runtime_observation=runtime_root,
            browser_observation=browser_root,
            artifact_binding=artifact_binding,
            claim_commit=claim_commit,
            attempt_id=attempt_id,
            claimed_at=claimed_at,
            completed_at=completed_text,
            state=ResultState.UNKNOWN_DO_NOT_RETRY.value,
            frame_post_request_count=1,
            protocol_evidence={
                "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
                "detail": f"untyped protocol driver failure: {type(error).__name__}",
                "frame_post_request_count": 1,
            },
        )
        raise N6PostClaimUnknown(
            "N6 driver outcome is unknown; claim remains consumed",
            receipt=receipt,
        ) from error

    completed_text = completion_timestamp()
    return _protocol_receipt(
        manifest=root,
        authorization=authorization_root,
        runtime_observation=runtime_root,
        browser_observation=browser_root,
        artifact_binding=artifact_binding,
        claim_commit=claim_commit,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        completed_at=completed_text,
        state="PROTOCOL_VERIFIED_PENDING_MANUAL",
        frame_post_request_count=1,
        protocol_evidence=protocol,
    )


def seal_n6_manual_observation(
    payload: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    protocol_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal the human screen/electrical judgment after one visible refresh."""

    root = _seal(payload)
    validate_n6_manual_observation(
        root, manifest=manifest, protocol_receipt=protocol_receipt
    )
    return root


def validate_n6_manual_observation(
    record: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    protocol_receipt: Mapping[str, Any],
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    receipt = validate_n6_protocol_receipt(protocol_receipt, manifest=manifest_root)
    if receipt["state"] != "PROTOCOL_VERIFIED_PENDING_MANUAL":
        raise N6VisibleExecutionError("only a protocol-verified N6 receipt can be judged manually")
    root = _exact(
        record,
        label="N6 manual observation",
        keys={
            "schema_version",
            "kind",
            "formal_manifest_canonical_sha256",
            "protocol_receipt_canonical_sha256",
            "action_identity_sha256",
            "attempt_id",
            "observed_at",
            "observer_id",
            "full_panel_visual_matches_preview",
            "map_fidelity_pass",
            "orientation_seam_and_ghosting_normal",
            "supply_cv_current_normal",
            "post_refresh_current_normal",
            "temperature_normal",
            "esp32_unexpected_restart",
            "j2_state_after_observation",
            "manual_evidence_sha256",
            "notes",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != MANUAL_OBSERVATION_KIND:
        raise N6VisibleExecutionError("N6 manual observation kind/version is invalid")
    if (
        root["formal_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["protocol_receipt_canonical_sha256"]
        != receipt["integrity"]["canonical_sha256"]
        or root["action_identity_sha256"]
        != manifest_root["action"]["action_identity_sha256"]
        or root["attempt_id"] != receipt["attempt_id"]
    ):
        raise N6VisibleExecutionError("N6 manual observation binding changed")
    observed = _timestamp(root["observed_at"], label="manual observed_at")
    if observed < _timestamp(receipt["completed_at"], label="protocol completed_at"):
        raise N6VisibleExecutionError("manual observation precedes protocol completion")
    _text(root["observer_id"], label="manual observer_id", maximum=256)
    for field in (
        "full_panel_visual_matches_preview",
        "map_fidelity_pass",
        "orientation_seam_and_ghosting_normal",
        "supply_cv_current_normal",
        "post_refresh_current_normal",
        "temperature_normal",
        "esp32_unexpected_restart",
    ):
        if type(root[field]) is not bool:
            raise N6VisibleExecutionError(f"manual observation {field} must be boolean")
    if root["j2_state_after_observation"] not in {"on", "off_after_observation"}:
        raise N6VisibleExecutionError("manual observation J2 state is invalid")
    _hash(root["manual_evidence_sha256"], label="manual observation evidence")
    if root["notes"] is not None:
        _text(root["notes"], label="manual observation notes")
    _check_integrity(root, label="N6 manual observation")
    return root


def _manual_pass(observation: Mapping[str, Any]) -> bool:
    return all(
        observation[field] is True
        for field in (
            "full_panel_visual_matches_preview",
            "map_fidelity_pass",
            "orientation_seam_and_ghosting_normal",
            "supply_cv_current_normal",
            "post_refresh_current_normal",
            "temperature_normal",
        )
    ) and observation["esp32_unexpected_restart"] is False


def finalize_n6_manual_observation(
    manifest: Mapping[str, Any],
    protocol_receipt: Mapping[str, Any],
    manual_observation: Mapping[str, Any],
    *,
    finalized_at: str,
) -> dict[str, Any]:
    """Create the immutable PASS/FAIL result after the operator judges the screen."""

    manifest_root = validate_n6_formal_manifest(manifest)
    receipt = validate_n6_protocol_receipt(protocol_receipt, manifest=manifest_root)
    observation = validate_n6_manual_observation(
        manual_observation,
        manifest=manifest_root,
        protocol_receipt=receipt,
    )
    finalized_time = _timestamp(finalized_at, label="N6 finalized_at")
    if finalized_time < _timestamp(observation["observed_at"], label="manual observed_at"):
        raise N6VisibleExecutionError("N6 finalization precedes manual observation")
    state = ResultState.PASS if _manual_pass(observation) else ResultState.FAIL
    result = build_result_record(
        action_identity_sha256=manifest_root["action"]["action_identity_sha256"],
        state=state,
        completed_at=finalized_at,
        evidence_manifest_sha256=observation["integrity"]["canonical_sha256"],
        post_request_count=receipt["frame_post_request_count"],
        details=(
            "N6 browser/source/four-preview/protocol/manual evidence closed; no retry or recovery"
            if state is ResultState.PASS
            else "N6 manual screen/electrical judgment failed; terminal; no retry or recovery"
        ),
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZED_BUNDLE_KIND,
        "formal_manifest_canonical_sha256": manifest_root["integrity"]["canonical_sha256"],
        "action_identity_sha256": manifest_root["action"]["action_identity_sha256"],
        "attempt_id": receipt["attempt_id"],
        "finalized_at": finalized_at,
        "protocol_receipt": _snapshot(receipt),
        "manual_observation": _snapshot(observation),
        "result": result,
        "classification": {
            "terminal": True,
            "protocol_verified": True,
            "manual_observation_complete": True,
            "hardware_observed": True,
            "retry_allowed": False,
            "recovery_allowed": False,
        },
    }
    root = _seal(payload)
    validate_n6_finalized_bundle(root, manifest=manifest_root)
    return root


def finalize_n6_unknown_receipt(
    manifest: Mapping[str, Any],
    protocol_receipt: Mapping[str, Any],
    *,
    finalized_at: str,
) -> dict[str, Any]:
    """Publish terminal UNKNOWN without permitting manual promotion or another POST."""

    manifest_root = validate_n6_formal_manifest(manifest)
    receipt = validate_n6_protocol_receipt(protocol_receipt, manifest=manifest_root)
    if receipt["state"] != ResultState.UNKNOWN_DO_NOT_RETRY.value:
        raise N6VisibleExecutionError("unknown finalizer requires an UNKNOWN protocol receipt")
    if _timestamp(finalized_at, label="N6 finalized_at") < _timestamp(
        receipt["completed_at"], label="protocol completed_at"
    ):
        raise N6VisibleExecutionError("N6 finalization precedes protocol receipt")
    result = build_result_record(
        action_identity_sha256=manifest_root["action"]["action_identity_sha256"],
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=finalized_at,
        evidence_manifest_sha256=receipt["integrity"]["canonical_sha256"],
        post_request_count=receipt["frame_post_request_count"],
        details="N6 device outcome unknown after permanent claim; no second POST or recovery",
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZED_BUNDLE_KIND,
        "formal_manifest_canonical_sha256": manifest_root["integrity"]["canonical_sha256"],
        "action_identity_sha256": manifest_root["action"]["action_identity_sha256"],
        "attempt_id": receipt["attempt_id"],
        "finalized_at": finalized_at,
        "protocol_receipt": _snapshot(receipt),
        "manual_observation": None,
        "result": result,
        "classification": {
            "terminal": True,
            "protocol_verified": False,
            "manual_observation_complete": False,
            "hardware_observed": False,
            "retry_allowed": False,
            "recovery_allowed": False,
        },
    }
    root = _seal(payload)
    validate_n6_finalized_bundle(root, manifest=manifest_root)
    return root


def validate_n6_finalized_bundle(
    bundle: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> Mapping[str, Any]:
    manifest_root = validate_n6_formal_manifest(manifest)
    root = _exact(
        bundle,
        label="N6 finalized bundle",
        keys={
            "schema_version",
            "kind",
            "formal_manifest_canonical_sha256",
            "action_identity_sha256",
            "attempt_id",
            "finalized_at",
            "protocol_receipt",
            "manual_observation",
            "result",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != FINALIZED_BUNDLE_KIND:
        raise N6VisibleExecutionError("N6 finalized bundle kind/version is invalid")
    if (
        root["formal_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["action_identity_sha256"]
        != manifest_root["action"]["action_identity_sha256"]
    ):
        raise N6VisibleExecutionError("N6 finalized bundle manifest/action binding changed")
    finalized = _timestamp(root["finalized_at"], label="N6 finalized_at")
    receipt = validate_n6_protocol_receipt(root["protocol_receipt"], manifest=manifest_root)
    if root["attempt_id"] != receipt["attempt_id"]:
        raise N6VisibleExecutionError("N6 finalized attempt identity changed")
    try:
        result = validate_result_record(root["result"])
    except CampaignContractError as error:
        raise N6VisibleExecutionError(f"N6 final result is invalid: {error}") from error
    if (
        result["action_identity_sha256"] != root["action_identity_sha256"]
        or result["post_request_count"] != receipt["frame_post_request_count"]
        or result["automatic_retry_count"] != 0
        or result["retry_allowed"] is not False
        or result["recovery_performed"] is not False
    ):
        raise N6VisibleExecutionError("N6 final result/receipt binding changed")
    if finalized != _timestamp(result["completed_at"], label="result completed_at"):
        raise N6VisibleExecutionError("N6 final result timestamp differs from bundle")
    classification = _exact(
        root["classification"],
        label="N6 finalized classification",
        keys={
            "terminal",
            "protocol_verified",
            "manual_observation_complete",
            "hardware_observed",
            "retry_allowed",
            "recovery_allowed",
        },
    )
    if (
        classification["terminal"] is not True
        or classification["retry_allowed"] is not False
        or classification["recovery_allowed"] is not False
    ):
        raise N6VisibleExecutionError("N6 finalized classification permits continuation")
    if receipt["state"] == "PROTOCOL_VERIFIED_PENDING_MANUAL":
        observation = validate_n6_manual_observation(
            root["manual_observation"],
            manifest=manifest_root,
            protocol_receipt=receipt,
        )
        expected_state = ResultState.PASS.value if _manual_pass(observation) else ResultState.FAIL.value
        if (
            result["state"] != expected_state
            or result["evidence_manifest_sha256"]
            != observation["integrity"]["canonical_sha256"]
            or classification
            != {
                "terminal": True,
                "protocol_verified": True,
                "manual_observation_complete": True,
                "hardware_observed": True,
                "retry_allowed": False,
                "recovery_allowed": False,
            }
        ):
            raise N6VisibleExecutionError("N6 manual finalization semantics changed")
    else:
        if (
            root["manual_observation"] is not None
            or result["state"] != ResultState.UNKNOWN_DO_NOT_RETRY.value
            or result["evidence_manifest_sha256"]
            != receipt["integrity"]["canonical_sha256"]
            or classification
            != {
                "terminal": True,
                "protocol_verified": False,
                "manual_observation_complete": False,
                "hardware_observed": False,
                "retry_allowed": False,
                "recovery_allowed": False,
            }
        ):
            raise N6VisibleExecutionError("N6 UNKNOWN finalization semantics changed")
    _check_integrity(root, label="N6 finalized bundle")
    return root


def n6_finalized_bundle_file_sha256(
    bundle: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> str:
    return _canonical_sha256(validate_n6_finalized_bundle(bundle, manifest=manifest))


__all__ = [
    "AUTHORIZATION_KIND",
    "AtomicN6ClaimStore",
    "CANONICAL_HASH_SCOPE",
    "CLAIM_KIND",
    "FINALIZED_BUNDLE_KIND",
    "FORMAL_ARTIFACT_REVIEW_KIND",
    "FORMAL_MANIFEST_KIND",
    "MANUAL_OBSERVATION_KIND",
    "MATERIALIZATION_DESCRIPTION_KIND",
    "N6BrowserExecutionController",
    "N6ClaimConsumed",
    "N6HttpRefreshDriver",
    "N6PostClaimUnknown",
    "N6ProtocolDriver",
    "N6TransportOutcomeUnknown",
    "N6VisibleExecutionError",
    "N6_ARM_CONFIRMATION",
    "LEGACY_N6_ENQUEUE_BLOCK_MESSAGE",
    "PROTOCOL_RECEIPT_KIND",
    "RUNTIME_OBSERVATION_KIND",
    "RUNTIME_REVIEW_KIND",
    "SCHEMA_VERSION",
    "describe_n6_formal_materialization",
    "execute_n6_formal_once",
    "finalize_n6_manual_observation",
    "finalize_n6_unknown_receipt",
    "materialize_n6_formal_manifest",
    "measured_gamut_profile_from_n6_manifest",
    "measured_palette_from_n6_manifest",
    "n6_finalized_bundle_file_sha256",
    "n6_formal_manifest_file_sha256",
    "seal_n6_external_authorization",
    "seal_n6_formal_artifact_review",
    "seal_n6_manual_observation",
    "seal_n6_runtime_observation",
    "seal_n6_runtime_review",
    "validate_n6_browser_chain_observation",
    "validate_n6_claim_record",
    "validate_n6_external_authorization",
    "validate_n6_finalized_bundle",
    "validate_n6_formal_artifact_review",
    "validate_n6_formal_manifest",
    "validate_n6_manual_observation",
    "validate_n6_materialization_description",
    "validate_n6_protocol_receipt",
    "validate_n6_runtime_artifact",
    "validate_n6_runtime_observation",
    "validate_n6_runtime_review",
]
