"""Fail-closed, offline contracts for supervised visible-refresh campaigns.

This module compiles and validates data only.  In particular, it has no
network requester, device discovery, serial/GPIO access, firmware upload,
authorization generator, claim writer, retry path, or recovery path.  A
future executor may consume these contracts, but it must implement the claim
and one-POST rules independently and remain opt-in.

The contracts separate three concepts which earlier hardware notes sometimes
called "cold start" collectively:

* a controller/ESP32 fresh boot;
* an exact visible prior established by another action; and
* a physical panel/J2 power cycle with a measured off interval.

Keeping them explicit avoids unnecessary J2 cycling while preventing a warm
controller session from being mislabeled as a panel-cold repetition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
LIMIT_PROFILE_KIND = "mf1750-visible-refresh-limit-profile"
ACTION_KIND = "mf1750-fixed-visible-refresh-action-declaration"
SESSION_KIND = "mf1750-visible-refresh-session-contract"
CAMPAIGN_KIND = "mf1750-visible-refresh-campaign-contract"
RESULT_KIND = "mf1750-visible-refresh-action-result"
DESCRIPTION_KIND = "mf1750-visible-refresh-action-description"

LIMIT_PROFILE_HASH_SCOPE = (
    "entire limit profile excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
ACTION_IDENTITY_HASH_SCOPE = (
    "action identity object only; UTF-8 JSON with sorted keys, no whitespace, "
    "ensure_ascii=false, allow_nan=false"
)
SESSION_HASH_SCOPE = (
    "entire session contract excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
CAMPAIGN_HASH_SCOPE = (
    "entire campaign contract excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
RESULT_HASH_SCOPE = (
    "entire action result excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
DESCRIPTION_HASH_SCOPE = (
    "entire offline description excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)

CLAIM_REGISTRY_ID = "workspace-visible-refresh-fixed-action-registry-v1"
CLAIM_REGISTRY_RELATIVE_PATH = (
    ".test-output/hardware/.visible_refresh_fixed_action_claims_v1"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_HEX40_RE = re.compile(r"[0-9a-f]{40}\Z")
_FNV1A_RE = re.compile(r"0x[0-9A-F]{8}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,127})\Z")
_SEMVER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)

_PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
_FIRMWARE_KEYS = frozenset(
    {"source_commit", "build_tag", "binary_sha256", "driver_api"}
)
_ALLOWLIST_KEYS = frozenset(
    {
        "action_id",
        "action_identity_sha256",
        "method",
        "endpoint",
        "frame_sha256",
        "maximum_uses",
    }
)
_LIMIT_KEYS = frozenset(
    {
        "maximum_campaign_visible_refreshes",
        "maximum_session_visible_refreshes",
        "maximum_consecutive_visible_refreshes",
        "minimum_interval_seconds",
        "minimum_cooldown_seconds",
        "minimum_start_temperature_c",
        "maximum_start_temperature_c",
        "maximum_post_refresh_temperature_c",
    }
)
_USAGE_KEYS = frozenset(
    {
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
        "last_visible_refresh_completed_at",
        "snapshot_at",
        "evidence_sha256",
    }
)
_VALIDITY_KEYS = frozenset({"valid_from", "expires_at"})
_REVIEW_KEYS = frozenset(
    {"approved", "reviewer_id", "reviewed_at", "review_artifact_sha256"}
)
_INTEGRITY_KEYS = frozenset({"canonical_sha256", "canonical_sha256_scope"})
_PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "profile_id",
        "profile_version",
        "panel",
        "firmware",
        "action_allowlist",
        "limits",
        "usage",
        "validity",
        "review",
        "integrity",
    }
)
_PROFILE_AUTHORITY_KEYS = frozenset(
    {
        *_PROFILE_KEYS,
        "limit_authority_kind",
        "limit_authority_classification",
    }
)

_MAPPING_KEYS = frozenset({"source_half", "flip_x", "flip_y", "nibble_swap"})
_CONTROLLER_KEYS = frozenset(
    {"controller", "mapping", "dtm_bytes", "dtm_sha256", "dtm_fnv1a"}
)
_FRAME_KEYS = frozenset(
    {
        "width",
        "height",
        "bits_per_pixel",
        "bytes",
        "sha256",
        "fnv1a",
        "controllers",
    }
)
_REQUEST_KEYS = frozenset(
    {"method", "endpoint", "body", "maximum_post_requests"}
)
_PRIOR_KEYS = frozenset(
    {"action_identity_sha256", "scope", "required_result_state"}
)
_SCHEDULE_KEYS = frozenset(
    {"minimum_interval_since_prior_seconds", "counts_as_visible_refresh"}
)
_ACTION_IDENTITY_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "campaign_id",
        "session_id",
        "cell_id",
        "action_id",
        "phase",
        "frame",
        "request",
        "prior",
        "schedule",
        "automatic_retry",
        "automatic_recovery",
    }
)
_CLAIM_KEYS = frozenset(
    {
        "registry_id",
        "workspace_relative_registry",
        "filename",
        "partitioned_by_campaign_id",
        "overridable",
        "create_before_network",
    }
)
_ACTION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "identity",
        "action_identity_sha256",
        "action_identity_sha256_scope",
        "claim",
    }
)

_SESSION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "session_id",
        "cell_id",
        "power_mode",
        "requires_controller_fresh_boot",
        "requires_panel_power_cycle",
        "minimum_panel_power_off_seconds",
        "j2_may_remain_on_before_session",
        "planned_cooldown_seconds",
        "final_power_off_required",
        "action_identity_sha256s",
        "automatic_advance",
        "integrity",
    }
)
_CAMPAIGN_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "campaign_id",
        "panel",
        "firmware",
        "actions",
        "sessions",
        "classification",
        "integrity",
    }
)
_CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}


class CampaignContractError(ValueError):
    """Raised when an offline visible-refresh contract fails closed."""


class ResultState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INVALID = "INVALID"
    STOP = "STOP"
    UNKNOWN_DO_NOT_RETRY = "UNKNOWN_DO_NOT_RETRY"


RESULT_STATES = tuple(state.value for state in ResultState)


@dataclass(frozen=True)
class LimitDecision:
    """Time-specific decision derived from an immutable limit profile."""

    hardware_ready: bool
    evaluated_at: str
    profile_canonical_sha256: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hardware_ready": self.hardware_ready,
            "evaluated_at": self.evaluated_at,
            "profile_canonical_sha256": self.profile_canonical_sha256,
            "reasons": list(self.reasons),
        }


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON encoding used by every P0 identity."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CampaignContractError(f"value is not canonical JSON data: {error}") from error


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:  # pragma: no cover
        raise CampaignContractError(f"could not snapshot canonical JSON: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignContractError(f"{label} must be an object")
    actual = set(value)
    if actual != set(keys):
        missing = sorted(set(keys) - actual)
        extra = sorted(actual - set(keys))
        raise CampaignContractError(
            f"{label} keys differ from contract; missing={missing}, extra={extra}"
        )
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CampaignContractError(f"{label} must be an array")
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CampaignContractError(f"{label} must be a non-empty string of at most {maximum} characters")
    if any(ord(character) < 0x20 for character in value):
        raise CampaignContractError(f"{label} must not contain control characters")
    return value


def _nullable_text(value: Any, *, label: str, maximum: int = 4096) -> Optional[str]:
    if value is None:
        return None
    return _text(value, label=label, maximum=maximum)


def _token(value: Any, *, label: str) -> str:
    result = _text(value, label=label, maximum=128)
    if _TOKEN_RE.fullmatch(result) is None:
        raise CampaignContractError(f"{label} is not a supported stable token")
    return result


def _nullable_token(value: Any, *, label: str) -> Optional[str]:
    if value is None:
        return None
    return _token(value, label=label)


def _hash(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be 64 lowercase hexadecimal digits{suffix}")
    return value


def _nullable_hex40(value: Any, *, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or _HEX40_RE.fullmatch(value) is None:
        raise CampaignContractError(f"{label} must be 40 lowercase hexadecimal digits or null")
    return value


def _nonnegative_number(value: Any, *, label: str, nullable: bool = False) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be a non-negative finite number{suffix}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise CampaignContractError(f"{label} must be a non-negative finite number")
    return result


def _temperature(value: Any, *, label: str, nullable: bool = False) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be a finite temperature{suffix}")
    result = float(value)
    if not math.isfinite(result) or not -100.0 <= result <= 200.0:
        raise CampaignContractError(f"{label} must be within -100..200 degC")
    return result


def _positive_integer(value: Any, *, label: str, nullable: bool = False) -> Optional[int]:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 1:
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be a positive integer{suffix}")
    return value


def _nonnegative_integer(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[int]:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0:
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be a non-negative integer{suffix}")
    return value


def _timestamp(value: Any, *, label: str, nullable: bool = False) -> Optional[datetime]:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise CampaignContractError(f"{label} must be an RFC3339 timestamp{suffix}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CampaignContractError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None:
        raise CampaignContractError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(canonical_json_bytes(unsigned)),
        "canonical_sha256_scope": scope,
    }


def _validate_integrity(
    document: Mapping[str, Any], *, label: str, scope: str
) -> str:
    integrity = _mapping(document.get("integrity"), label=f"{label}.integrity", keys=_INTEGRITY_KEYS)
    unsigned = dict(document)
    unsigned.pop("integrity")
    expected = _integrity(unsigned, scope)
    if dict(integrity) != expected:
        raise CampaignContractError(f"{label} canonical integrity is invalid")
    return expected["canonical_sha256"]


def _validate_panel(value: Any, *, allow_null: bool, label: str) -> Mapping[str, Any]:
    panel = _mapping(value, label=label, keys=_PANEL_KEYS)
    for field in ("model", "serial", "board_id", "pcb_revision"):
        if allow_null:
            _nullable_text(panel[field], label=f"{label}.{field}", maximum=256)
        else:
            _text(panel[field], label=f"{label}.{field}", maximum=256)
    return panel


def _validate_firmware(value: Any, *, allow_null: bool, label: str) -> Mapping[str, Any]:
    firmware = _mapping(value, label=label, keys=_FIRMWARE_KEYS)
    if allow_null:
        _nullable_hex40(firmware["source_commit"], label=f"{label}.source_commit")
        _nullable_text(firmware["build_tag"], label=f"{label}.build_tag", maximum=128)
        _hash(firmware["binary_sha256"], label=f"{label}.binary_sha256", nullable=True)
        _nullable_text(firmware["driver_api"], label=f"{label}.driver_api", maximum=128)
    else:
        if not isinstance(firmware["source_commit"], str) or _HEX40_RE.fullmatch(
            firmware["source_commit"]
        ) is None:
            raise CampaignContractError(f"{label}.source_commit must be 40 lowercase hexadecimal digits")
        _text(firmware["build_tag"], label=f"{label}.build_tag", maximum=128)
        _hash(firmware["binary_sha256"], label=f"{label}.binary_sha256")
        _text(firmware["driver_api"], label=f"{label}.driver_api", maximum=128)
    return firmware


def seal_limit_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one draft or reviewed machine-readable limit profile.

    Nullable safety values are retained so a draft can be audited.  They never
    make the resulting profile ready; :func:`evaluate_limit_profile` reports
    every missing critical value.
    """

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise CampaignContractError("limit profile payload must be an object without integrity")
    snapshot = _snapshot(payload)
    snapshot["integrity"] = _integrity(snapshot, LIMIT_PROFILE_HASH_SCOPE)
    validate_limit_profile(snapshot)
    return snapshot


def validate_limit_profile(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate profile shape, canonical identity, and all non-null values."""

    authority_fields = {
        "limit_authority_kind",
        "limit_authority_classification",
    }
    keys = (
        _PROFILE_AUTHORITY_KEYS
        if authority_fields.intersection(profile)
        else _PROFILE_KEYS
    )
    root = _mapping(profile, label="limit profile", keys=keys)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"limit profile schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != LIMIT_PROFILE_KIND:
        raise CampaignContractError("limit profile kind is invalid")
    _token(root["profile_id"], label="limit profile.profile_id")
    version = _text(root["profile_version"], label="limit profile.profile_version", maximum=32)
    if _SEMVER_RE.fullmatch(version) is None:
        raise CampaignContractError("limit profile.profile_version must be semantic x.y.z")
    _validate_panel(root["panel"], allow_null=True, label="limit profile.panel")
    _validate_firmware(root["firmware"], allow_null=True, label="limit profile.firmware")
    if keys == _PROFILE_AUTHORITY_KEYS:
        _text(
            root["limit_authority_kind"],
            label="limit profile.limit_authority_kind",
            maximum=128,
        )
        _text(
            root["limit_authority_classification"],
            label="limit profile.limit_authority_classification",
            maximum=128,
        )

    allowlist = _list(root["action_allowlist"], label="limit profile.action_allowlist")
    seen_actions: set[str] = set()
    seen_identities: set[str] = set()
    for index, value in enumerate(allowlist):
        entry = _mapping(
            value,
            label=f"limit profile.action_allowlist[{index}]",
            keys=_ALLOWLIST_KEYS,
        )
        action_id = _token(entry["action_id"], label=f"action allowlist {index}.action_id")
        identity = _hash(
            entry["action_identity_sha256"],
            label=f"action allowlist {index}.action_identity_sha256",
        )
        if action_id in seen_actions or identity in seen_identities:
            raise CampaignContractError("limit profile action allowlist contains a duplicate")
        seen_actions.add(action_id)
        seen_identities.add(str(identity))
        if entry["method"] != "POST":
            raise CampaignContractError("limit profile actions must use POST")
        endpoint = _text(entry["endpoint"], label=f"action allowlist {index}.endpoint", maximum=256)
        if not endpoint.startswith("/api/") or "?" in endpoint or "#" in endpoint:
            raise CampaignContractError("limit profile action endpoint must be a fixed /api/ path")
        _hash(entry["frame_sha256"], label=f"action allowlist {index}.frame_sha256")
        if entry["maximum_uses"] != 1 or type(entry["maximum_uses"]) is not int:
            raise CampaignContractError("limit profile action maximum_uses must be integer one")

    limits = _mapping(root["limits"], label="limit profile.limits", keys=_LIMIT_KEYS)
    maxima = {}
    for field in (
        "maximum_campaign_visible_refreshes",
        "maximum_session_visible_refreshes",
        "maximum_consecutive_visible_refreshes",
    ):
        maxima[field] = _positive_integer(
            limits[field], label=f"limit profile.limits.{field}", nullable=True
        )
    for field in ("minimum_interval_seconds", "minimum_cooldown_seconds"):
        _nonnegative_number(
            limits[field], label=f"limit profile.limits.{field}", nullable=True
        )
    temperatures = {}
    for field in (
        "minimum_start_temperature_c",
        "maximum_start_temperature_c",
        "maximum_post_refresh_temperature_c",
    ):
        temperatures[field] = _temperature(
            limits[field], label=f"limit profile.limits.{field}", nullable=True
        )
    if all(value is not None for value in maxima.values()):
        assert maxima["maximum_campaign_visible_refreshes"] is not None
        assert maxima["maximum_session_visible_refreshes"] is not None
        assert maxima["maximum_consecutive_visible_refreshes"] is not None
        if not (
            maxima["maximum_consecutive_visible_refreshes"]
            <= maxima["maximum_session_visible_refreshes"]
            <= maxima["maximum_campaign_visible_refreshes"]
        ):
            raise CampaignContractError(
                "limit profile consecutive/session/campaign maxima are inconsistent"
            )
    if (
        temperatures["minimum_start_temperature_c"] is not None
        and temperatures["maximum_start_temperature_c"] is not None
        and temperatures["minimum_start_temperature_c"]
        >= temperatures["maximum_start_temperature_c"]
    ):
        raise CampaignContractError("limit profile start temperature interval is empty")

    usage = _mapping(root["usage"], label="limit profile.usage", keys=_USAGE_KEYS)
    usage_counts = {}
    for field in (
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
    ):
        usage_counts[field] = _nonnegative_integer(
            usage[field], label=f"limit profile.usage.{field}", nullable=True
        )
    if all(value is not None for value in usage_counts.values()):
        assert usage_counts["cumulative_visible_refresh_count"] is not None
        assert usage_counts["session_visible_refresh_count"] is not None
        assert usage_counts["consecutive_visible_refresh_count"] is not None
        if not (
            usage_counts["consecutive_visible_refresh_count"]
            <= usage_counts["session_visible_refresh_count"]
            <= usage_counts["cumulative_visible_refresh_count"]
        ):
            raise CampaignContractError(
                "limit profile consecutive/session/cumulative usage counts are inconsistent"
            )
    last_visible = _timestamp(
        usage["last_visible_refresh_completed_at"],
        label="limit profile.usage.last_visible_refresh_completed_at",
        nullable=True,
    )
    snapshot_at = _timestamp(
        usage["snapshot_at"],
        label="limit profile.usage.snapshot_at",
        nullable=True,
    )
    _hash(
        usage["evidence_sha256"],
        label="limit profile.usage.evidence_sha256",
        nullable=True,
    )
    if last_visible is not None and snapshot_at is not None and last_visible > snapshot_at:
        raise CampaignContractError(
            "limit profile last visible refresh occurs after its usage snapshot"
        )

    validity = _mapping(root["validity"], label="limit profile.validity", keys=_VALIDITY_KEYS)
    valid_from = _timestamp(validity["valid_from"], label="limit profile.validity.valid_from", nullable=True)
    expires_at = _timestamp(validity["expires_at"], label="limit profile.validity.expires_at", nullable=True)
    if valid_from is not None and expires_at is not None and expires_at <= valid_from:
        raise CampaignContractError("limit profile validity interval is empty")

    review = _mapping(root["review"], label="limit profile.review", keys=_REVIEW_KEYS)
    if type(review["approved"]) is not bool:
        raise CampaignContractError("limit profile.review.approved must be boolean")
    reviewer = _nullable_text(review["reviewer_id"], label="limit profile.review.reviewer_id", maximum=256)
    reviewed_at = _timestamp(
        review["reviewed_at"], label="limit profile.review.reviewed_at", nullable=True
    )
    review_sha = _hash(
        review["review_artifact_sha256"],
        label="limit profile.review.review_artifact_sha256",
        nullable=True,
    )
    if review["approved"] and (reviewer is None or reviewed_at is None or review_sha is None):
        raise CampaignContractError("approved limit profile requires complete review provenance")
    if reviewed_at is not None and valid_from is not None and reviewed_at > valid_from:
        raise CampaignContractError("limit profile review must not occur after valid_from")

    _validate_integrity(root, label="limit profile", scope=LIMIT_PROFILE_HASH_SCOPE)
    return root


def evaluate_limit_profile(
    profile: Mapping[str, Any], *, evaluated_at: str
) -> LimitDecision:
    """Evaluate null, approval, and validity gates at one explicit instant."""

    root = validate_limit_profile(profile)
    now = _timestamp(evaluated_at, label="evaluated_at")
    assert now is not None
    reasons: list[str] = []

    for field, value in root["panel"].items():
        if value is None:
            reasons.append(f"critical_null:panel.{field}")
    for field, value in root["firmware"].items():
        if value is None:
            reasons.append(f"critical_null:firmware.{field}")
    if not root["action_allowlist"]:
        reasons.append("critical_empty:action_allowlist")
    for field, value in root["limits"].items():
        if value is None:
            reasons.append(f"critical_null:limits.{field}")
    usage = root["usage"]
    for field in (
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
        "snapshot_at",
        "evidence_sha256",
    ):
        if usage[field] is None:
            reasons.append(f"critical_null:usage.{field}")
    cumulative_count = usage["cumulative_visible_refresh_count"]
    if cumulative_count is None or cumulative_count > 0:
        if usage["last_visible_refresh_completed_at"] is None:
            reasons.append(
                "critical_null:usage.last_visible_refresh_completed_at"
            )
    for field, value in root["validity"].items():
        if value is None:
            reasons.append(f"critical_null:validity.{field}")
    review = root["review"]
    if review["approved"] is not True:
        reasons.append("review_not_approved")
    for field in ("reviewer_id", "reviewed_at", "review_artifact_sha256"):
        if review[field] is None:
            reasons.append(f"critical_null:review.{field}")

    valid_from = _timestamp(root["validity"]["valid_from"], label="valid_from", nullable=True)
    expires_at = _timestamp(root["validity"]["expires_at"], label="expires_at", nullable=True)
    reviewed_at = _timestamp(review["reviewed_at"], label="reviewed_at", nullable=True)
    snapshot_at = _timestamp(usage["snapshot_at"], label="snapshot_at", nullable=True)
    last_visible = _timestamp(
        usage["last_visible_refresh_completed_at"],
        label="last_visible_refresh_completed_at",
        nullable=True,
    )
    if valid_from is not None and now < valid_from:
        reasons.append("profile_not_yet_valid")
    if expires_at is not None and now >= expires_at:
        reasons.append("profile_expired")
    if reviewed_at is not None and now < reviewed_at:
        reasons.append("review_timestamp_is_in_the_future")
    if snapshot_at is not None and now < snapshot_at:
        reasons.append("usage_snapshot_timestamp_is_in_the_future")
    if last_visible is not None and now < last_visible:
        reasons.append("last_visible_refresh_timestamp_is_in_the_future")
    if last_visible is not None and now >= last_visible:
        elapsed_seconds = (now - last_visible).total_seconds()
        minimum_interval = root["limits"]["minimum_interval_seconds"]
        if minimum_interval is not None and elapsed_seconds < minimum_interval:
            reasons.append("minimum_refresh_interval_not_elapsed")
        session_count = usage["session_visible_refresh_count"]
        minimum_cooldown = root["limits"]["minimum_cooldown_seconds"]
        if (
            session_count == 0
            and cumulative_count is not None
            and cumulative_count > 0
            and minimum_cooldown is not None
            and elapsed_seconds < minimum_cooldown
        ):
            reasons.append("minimum_inter_session_cooldown_not_elapsed")

    usage_limit_pairs = (
        (
            "cumulative_visible_refresh_count",
            "maximum_campaign_visible_refreshes",
            "campaign_visible_refresh_limit_exhausted",
        ),
        (
            "session_visible_refresh_count",
            "maximum_session_visible_refreshes",
            "session_visible_refresh_limit_exhausted",
        ),
        (
            "consecutive_visible_refresh_count",
            "maximum_consecutive_visible_refreshes",
            "consecutive_visible_refresh_limit_exhausted",
        ),
    )
    for count_field, limit_field, reason in usage_limit_pairs:
        count = usage[count_field]
        limit = root["limits"][limit_field]
        if count is not None and limit is not None and count >= limit:
            reasons.append(reason)

    canonical_sha = root["integrity"]["canonical_sha256"]
    unique_reasons = tuple(dict.fromkeys(reasons))
    return LimitDecision(not unique_reasons, evaluated_at, canonical_sha, unique_reasons)


def _validate_mapping_record(value: Any, *, controller: str, label: str) -> Mapping[str, Any]:
    mapping = _mapping(value, label=label, keys=_MAPPING_KEYS)
    expected_half = 0 if controller == "CS1" else 1
    if mapping != {
        "source_half": expected_half,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    }:
        raise CampaignContractError(f"{label} is not the frozen {controller} mapping")
    return mapping


def _validate_frame(value: Any, *, label: str) -> Mapping[str, Any]:
    frame = _mapping(value, label=label, keys=_FRAME_KEYS)
    if (
        frame["width"] != 1024
        or type(frame["width"]) is not int
        or frame["height"] != 600
        or type(frame["height"]) is not int
        or frame["bits_per_pixel"] != 4
        or type(frame["bits_per_pixel"]) is not int
        or frame["bytes"] != 307200
        or type(frame["bytes"]) is not int
    ):
        raise CampaignContractError(f"{label} is not a canonical 1024x600 4bpp frame")
    _hash(frame["sha256"], label=f"{label}.sha256")
    if not isinstance(frame["fnv1a"], str) or _FNV1A_RE.fullmatch(frame["fnv1a"]) is None:
        raise CampaignContractError(f"{label}.fnv1a must be canonical 0xXXXXXXXX")
    controllers = _list(frame["controllers"], label=f"{label}.controllers")
    if len(controllers) != 2:
        raise CampaignContractError(f"{label}.controllers must contain ordered CS1 and CS2")
    for index, expected_name in enumerate(("CS1", "CS2")):
        controller = _mapping(
            controllers[index],
            label=f"{label}.controllers[{index}]",
            keys=_CONTROLLER_KEYS,
        )
        if controller["controller"] != expected_name:
            raise CampaignContractError(f"{label}.controllers are not ordered CS1 then CS2")
        _validate_mapping_record(
            controller["mapping"],
            controller=expected_name,
            label=f"{label}.controllers[{index}].mapping",
        )
        if controller["dtm_bytes"] != 153600 or type(controller["dtm_bytes"]) is not int:
            raise CampaignContractError(f"{label}.{expected_name} DTM byte count is invalid")
        _hash(controller["dtm_sha256"], label=f"{label}.{expected_name}.dtm_sha256")
        if not isinstance(controller["dtm_fnv1a"], str) or _FNV1A_RE.fullmatch(
            controller["dtm_fnv1a"]
        ) is None:
            raise CampaignContractError(f"{label}.{expected_name}.dtm_fnv1a is invalid")
    return frame


def workspace_global_claim_declaration(action_identity_sha256: str) -> dict[str, Any]:
    """Return, but never create, the one workspace-global claim location."""

    identity = _hash(action_identity_sha256, label="action identity SHA-256")
    return {
        "registry_id": CLAIM_REGISTRY_ID,
        "workspace_relative_registry": CLAIM_REGISTRY_RELATIVE_PATH,
        "filename": f"{identity}.json",
        "partitioned_by_campaign_id": False,
        "overridable": False,
        "create_before_network": True,
    }


def _validate_claim(value: Any, *, action_identity_sha256: str) -> Mapping[str, Any]:
    claim = _mapping(value, label="action.claim", keys=_CLAIM_KEYS)
    if dict(claim) != workspace_global_claim_declaration(action_identity_sha256):
        raise CampaignContractError("action claim is not the fixed workspace-global declaration")
    relative_text = claim["workspace_relative_registry"]
    posix = PurePosixPath(relative_text)
    windows = PureWindowsPath(relative_text)
    if (
        posix.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
        or relative_text != posix.as_posix()
    ):
        raise CampaignContractError("workspace-global claim path is unsafe")
    return claim


def build_fixed_action_declaration(
    *,
    campaign_id: str,
    session_id: str,
    cell_id: str,
    action_id: str,
    phase: str,
    frame: Mapping[str, Any],
    endpoint: str = "/api/frame",
    request_body: str = "exact-canonical-frame-bytes",
    prior_action_identity_sha256: Optional[str] = None,
    prior_scope: Optional[str] = None,
    minimum_interval_since_prior_seconds: int | float = 0,
) -> dict[str, Any]:
    """Build one immutable fixed-action declaration without creating a claim."""

    prior: Optional[dict[str, Any]]
    if prior_action_identity_sha256 is None:
        if prior_scope is not None:
            raise CampaignContractError("root action cannot specify a prior scope")
        prior = None
    else:
        if prior_scope not in {"same_cell", "campaign"}:
            raise CampaignContractError("dependent action prior_scope must be same_cell or campaign")
        prior = {
            "action_identity_sha256": _hash(
                prior_action_identity_sha256, label="prior action identity SHA-256"
            ),
            "scope": prior_scope,
            "required_result_state": ResultState.PASS.value,
        }
    identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-fixed-visible-refresh-action-identity",
        "campaign_id": campaign_id,
        "session_id": session_id,
        "cell_id": cell_id,
        "action_id": action_id,
        "phase": phase,
        "frame": _snapshot(frame),
        "request": {
            "method": "POST",
            "endpoint": endpoint,
            "body": request_body,
            "maximum_post_requests": 1,
        },
        "prior": prior,
        "schedule": {
            "minimum_interval_since_prior_seconds": minimum_interval_since_prior_seconds,
            "counts_as_visible_refresh": True,
        },
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    identity_sha = _sha256(canonical_json_bytes(identity))
    declaration = {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTION_KIND,
        "identity": identity,
        "action_identity_sha256": identity_sha,
        "action_identity_sha256_scope": ACTION_IDENTITY_HASH_SCOPE,
        "claim": workspace_global_claim_declaration(identity_sha),
    }
    validate_fixed_action_declaration(declaration)
    return declaration


def validate_fixed_action_declaration(action: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(action, label="action", keys=_ACTION_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"action schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != ACTION_KIND:
        raise CampaignContractError("action kind is invalid")
    identity = _mapping(root["identity"], label="action.identity", keys=_ACTION_IDENTITY_KEYS)
    if identity["schema_version"] != SCHEMA_VERSION or type(identity["schema_version"]) is not int:
        raise CampaignContractError("action identity schema_version is invalid")
    if identity["kind"] != "mf1750-fixed-visible-refresh-action-identity":
        raise CampaignContractError("action identity kind is invalid")
    for field in ("campaign_id", "session_id", "cell_id", "action_id", "phase"):
        _token(identity[field], label=f"action.identity.{field}")
    _validate_frame(identity["frame"], label="action.identity.frame")
    request = _mapping(identity["request"], label="action.identity.request", keys=_REQUEST_KEYS)
    if (
        request["method"] != "POST"
        or request["body"] not in {"exact-canonical-frame-bytes", "none"}
        or request["maximum_post_requests"] != 1
        or type(request["maximum_post_requests"]) is not int
    ):
        raise CampaignContractError("action request is not the fixed one-POST contract")
    endpoint = _text(request["endpoint"], label="action.identity.request.endpoint", maximum=256)
    if not endpoint.startswith("/api/") or "?" in endpoint or "#" in endpoint:
        raise CampaignContractError("action endpoint must be a fixed /api/ path")
    if request["body"] == "none" and not endpoint.startswith("/api/diagnostic/"):
        raise CampaignContractError(
            "bodyless fixed action must use an explicit /api/diagnostic/ endpoint"
        )
    prior = identity["prior"]
    if prior is not None:
        prior_record = _mapping(prior, label="action.identity.prior", keys=_PRIOR_KEYS)
        _hash(
            prior_record["action_identity_sha256"],
            label="action.identity.prior.action_identity_sha256",
        )
        if prior_record["scope"] not in {"same_cell", "campaign"}:
            raise CampaignContractError("action prior scope is invalid")
        if prior_record["required_result_state"] != ResultState.PASS.value:
            raise CampaignContractError("action prior must require PASS")
    schedule = _mapping(identity["schedule"], label="action.identity.schedule", keys=_SCHEDULE_KEYS)
    _nonnegative_number(
        schedule["minimum_interval_since_prior_seconds"],
        label="action.identity.schedule.minimum_interval_since_prior_seconds",
    )
    if schedule["counts_as_visible_refresh"] is not True:
        raise CampaignContractError("fixed action must count as one visible refresh")
    if identity["automatic_retry"] is not False or identity["automatic_recovery"] is not False:
        raise CampaignContractError("fixed action must disable retry and recovery")
    actual_sha = _hash(root["action_identity_sha256"], label="action.action_identity_sha256")
    if actual_sha != _sha256(canonical_json_bytes(identity)):
        raise CampaignContractError("action identity SHA-256 does not match")
    if root["action_identity_sha256_scope"] != ACTION_IDENTITY_HASH_SCOPE:
        raise CampaignContractError("action identity hash scope is invalid")
    _validate_claim(root["claim"], action_identity_sha256=str(actual_sha))
    return root


def build_session_contract(
    *,
    session_id: str,
    cell_id: str,
    power_mode: str,
    planned_cooldown_seconds: int | float,
    final_power_off_required: bool,
    action_identity_sha256s: Sequence[str],
    minimum_panel_power_off_seconds: Optional[int | float] = None,
) -> dict[str, Any]:
    """Build one immutable session envelope around ordered fixed actions."""

    if power_mode == "supervised_continuous":
        controller_boot = False
        panel_cycle = False
        j2_may_remain = True
    elif power_mode == "controller_fresh_boot":
        controller_boot = True
        panel_cycle = False
        j2_may_remain = True
    elif power_mode == "panel_cold_cycle":
        controller_boot = True
        panel_cycle = True
        j2_may_remain = False
    elif power_mode == "panel_cold_driver_only":
        # The driver rail is cold-cycled while the ESP32 remains in the same
        # boot.  N7 uses this to preserve the ordered frequency-sweep
        # continuity while still starting every panel action from J2 off.
        controller_boot = False
        panel_cycle = True
        j2_may_remain = False
    else:
        raise CampaignContractError("session power_mode is invalid")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_KIND,
        "session_id": session_id,
        "cell_id": cell_id,
        "power_mode": power_mode,
        "requires_controller_fresh_boot": controller_boot,
        "requires_panel_power_cycle": panel_cycle,
        "minimum_panel_power_off_seconds": minimum_panel_power_off_seconds,
        "j2_may_remain_on_before_session": j2_may_remain,
        "planned_cooldown_seconds": planned_cooldown_seconds,
        "final_power_off_required": final_power_off_required,
        "action_identity_sha256s": list(action_identity_sha256s),
        "automatic_advance": False,
    }
    snapshot = _snapshot(payload)
    snapshot["integrity"] = _integrity(snapshot, SESSION_HASH_SCOPE)
    validate_session_contract(snapshot)
    return snapshot


def validate_session_contract(session: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(session, label="session", keys=_SESSION_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"session schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != SESSION_KIND:
        raise CampaignContractError("session kind is invalid")
    _token(root["session_id"], label="session.session_id")
    _token(root["cell_id"], label="session.cell_id")
    power_mode = root["power_mode"]
    expected = {
        "supervised_continuous": (False, False, True),
        "controller_fresh_boot": (True, False, True),
        "panel_cold_cycle": (True, True, False),
        "panel_cold_driver_only": (False, True, False),
    }
    if power_mode not in expected:
        raise CampaignContractError("session power_mode is invalid")
    actual = (
        root["requires_controller_fresh_boot"],
        root["requires_panel_power_cycle"],
        root["j2_may_remain_on_before_session"],
    )
    if actual != expected[power_mode] or any(type(value) is not bool for value in actual):
        raise CampaignContractError("session power-mode booleans are inconsistent")
    off_seconds = _nonnegative_number(
        root["minimum_panel_power_off_seconds"],
        label="session.minimum_panel_power_off_seconds",
        nullable=True,
    )
    if power_mode in {"panel_cold_cycle", "panel_cold_driver_only"}:
        if off_seconds is None or off_seconds <= 0:
            raise CampaignContractError("panel-cold session requires a positive measured off interval")
    elif off_seconds is not None:
        raise CampaignContractError("non-panel-cold session must keep panel off interval null")
    _nonnegative_number(root["planned_cooldown_seconds"], label="session.planned_cooldown_seconds")
    if type(root["final_power_off_required"]) is not bool:
        raise CampaignContractError("session.final_power_off_required must be boolean")
    actions = _list(root["action_identity_sha256s"], label="session.action_identity_sha256s")
    if not actions:
        raise CampaignContractError("session must contain at least one action")
    for index, identity in enumerate(actions):
        _hash(identity, label=f"session.action_identity_sha256s[{index}]")
    if len(set(actions)) != len(actions):
        raise CampaignContractError("session contains a duplicate action identity")
    if root["automatic_advance"] is not False:
        raise CampaignContractError("session automatic advance must remain disabled")
    _validate_integrity(root, label="session", scope=SESSION_HASH_SCOPE)
    return root


def seal_campaign_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal and deeply validate a complete fixed-action campaign DAG."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise CampaignContractError("campaign payload must be an object without integrity")
    snapshot = _snapshot(payload)
    snapshot["integrity"] = _integrity(snapshot, CAMPAIGN_HASH_SCOPE)
    validate_campaign_contract(snapshot)
    return snapshot


def validate_campaign_contract(campaign: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(campaign, label="campaign", keys=_CAMPAIGN_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"campaign schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != CAMPAIGN_KIND:
        raise CampaignContractError("campaign kind is invalid")
    campaign_id = _token(root["campaign_id"], label="campaign.campaign_id")
    _validate_panel(root["panel"], allow_null=False, label="campaign.panel")
    _validate_firmware(root["firmware"], allow_null=False, label="campaign.firmware")
    if root["classification"] != _CLASSIFICATION:
        raise CampaignContractError("campaign classification is not the frozen offline contract")

    actions_raw = _list(root["actions"], label="campaign.actions")
    sessions_raw = _list(root["sessions"], label="campaign.sessions")
    if not actions_raw or not sessions_raw:
        raise CampaignContractError("campaign must contain actions and sessions")
    actions: dict[str, Mapping[str, Any]] = {}
    action_ids: set[str] = set()
    for index, value in enumerate(actions_raw):
        try:
            action = validate_fixed_action_declaration(value)
        except CampaignContractError as error:
            raise CampaignContractError(f"campaign action {index} is invalid: {error}") from error
        identity = action["identity"]
        if identity["campaign_id"] != campaign_id:
            raise CampaignContractError("campaign action belongs to another campaign")
        action_sha = action["action_identity_sha256"]
        action_id = identity["action_id"]
        if action_sha in actions or action_id in action_ids:
            raise CampaignContractError("campaign action identity or action_id is duplicated")
        actions[action_sha] = action
        action_ids.add(action_id)

    sessions: dict[str, Mapping[str, Any]] = {}
    ordered_action_shas: list[str] = []
    for index, value in enumerate(sessions_raw):
        try:
            session = validate_session_contract(value)
        except CampaignContractError as error:
            raise CampaignContractError(f"campaign session {index} is invalid: {error}") from error
        session_id = session["session_id"]
        if session_id in sessions:
            raise CampaignContractError("campaign session_id is duplicated")
        sessions[session_id] = session
        for action_sha in session["action_identity_sha256s"]:
            if action_sha not in actions:
                raise CampaignContractError("session references an unknown action identity")
            action_identity = actions[action_sha]["identity"]
            if (
                action_identity["session_id"] != session_id
                or action_identity["cell_id"] != session["cell_id"]
            ):
                raise CampaignContractError("session/action identity binding is inconsistent")
            ordered_action_shas.append(action_sha)
    if len(ordered_action_shas) != len(set(ordered_action_shas)):
        raise CampaignContractError("an action is assigned to more than one session")
    if set(ordered_action_shas) != set(actions):
        raise CampaignContractError("not every campaign action is assigned to exactly one session")

    position = {action_sha: index for index, action_sha in enumerate(ordered_action_shas)}
    for action_sha, action in actions.items():
        identity = action["identity"]
        prior = identity["prior"]
        if prior is None:
            continue
        prior_sha = prior["action_identity_sha256"]
        if prior_sha not in actions:
            raise CampaignContractError("action DAG references an unknown prior action")
        if position[prior_sha] >= position[action_sha]:
            raise CampaignContractError("action DAG is cyclic or ordered after its dependent action")
        prior_identity = actions[prior_sha]["identity"]
        if prior["scope"] == "same_cell" and prior_identity["cell_id"] != identity["cell_id"]:
            raise CampaignContractError("same_cell prior crosses a campaign cell")

    _validate_integrity(root, label="campaign", scope=CAMPAIGN_HASH_SCOPE)
    return root


_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "action_identity_sha256",
        "state",
        "completed_at",
        "evidence_manifest_sha256",
        "claim",
        "post_request_count",
        "automatic_retry_count",
        "retry_allowed",
        "recovery_performed",
        "terminal",
        "details",
        "integrity",
    }
)
_LIMIT_DECISION_KEYS = frozenset(
    {
        "hardware_ready",
        "evaluated_at",
        "profile_canonical_sha256",
        "reasons",
    }
)
_PRIOR_RESULT_BINDING_KEYS = frozenset(
    {
        "action_identity_sha256",
        "result_file_sha256",
        "required_state",
        "observed_state",
    }
)
_DESCRIPTION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "mode",
        "campaign_id",
        "campaign_canonical_sha256",
        "action",
        "limit_profile_decision",
        "prior_result_binding",
        "contract_ready",
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "maximum_post_requests_if_future_executor_is_separately_authorized",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
        "blockers",
        "integrity",
    }
)


def build_result_record(
    *,
    action_identity_sha256: str,
    state: ResultState | str,
    completed_at: str,
    evidence_manifest_sha256: str,
    post_request_count: int,
    details: Optional[str] = None,
) -> dict[str, Any]:
    """Build an immutable terminal result; this performs no action or claim I/O."""

    state_text = state.value if isinstance(state, ResultState) else state
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "action_identity_sha256": action_identity_sha256,
        "state": state_text,
        "completed_at": completed_at,
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "claim": workspace_global_claim_declaration(action_identity_sha256),
        "post_request_count": post_request_count,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
        "terminal": True,
        "details": details,
    }
    snapshot = _snapshot(payload)
    snapshot["integrity"] = _integrity(snapshot, RESULT_HASH_SCOPE)
    validate_result_record(snapshot)
    return snapshot


def validate_result_record(result: Mapping[str, Any]) -> Mapping[str, Any]:
    root = _mapping(result, label="result", keys=_RESULT_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"result schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != RESULT_KIND:
        raise CampaignContractError("result kind is invalid")
    action_sha = _hash(root["action_identity_sha256"], label="result.action_identity_sha256")
    if root["state"] not in RESULT_STATES:
        raise CampaignContractError("result state is invalid")
    _timestamp(root["completed_at"], label="result.completed_at")
    _hash(root["evidence_manifest_sha256"], label="result.evidence_manifest_sha256")
    _validate_claim(root["claim"], action_identity_sha256=str(action_sha))
    count = root["post_request_count"]
    if type(count) is not int or count not in {0, 1}:
        raise CampaignContractError("result post_request_count must be integer zero or one")
    if root["state"] == ResultState.PASS.value and count != 1:
        raise CampaignContractError("PASS result requires exactly one POST")
    if root["automatic_retry_count"] != 0 or type(root["automatic_retry_count"]) is not int:
        raise CampaignContractError("result automatic_retry_count must remain integer zero")
    if (
        root["retry_allowed"] is not False
        or root["recovery_performed"] is not False
        or root["terminal"] is not True
    ):
        raise CampaignContractError("result must be terminal with no retry or recovery")
    _nullable_text(root["details"], label="result.details")
    _validate_integrity(root, label="result", scope=RESULT_HASH_SCOPE)
    return root


def result_file_sha256(result: Mapping[str, Any]) -> str:
    """Return the canonical whole-result file identity used by a dependent action."""

    root = validate_result_record(result)
    return _sha256(canonical_json_bytes(root))


def _campaign_profile_blockers(
    campaign: Mapping[str, Any],
    profile: Mapping[str, Any],
    action: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if campaign["panel"] != profile["panel"]:
        blockers.append("limit_profile_panel_mismatch")
    if campaign["firmware"] != profile["firmware"]:
        blockers.append("limit_profile_firmware_mismatch")
    identity = action["identity"]
    matches = [
        entry
        for entry in profile["action_allowlist"]
        if entry["action_identity_sha256"] == action["action_identity_sha256"]
    ]
    expected_allowlist = {
        "action_id": identity["action_id"],
        "action_identity_sha256": action["action_identity_sha256"],
        "method": identity["request"]["method"],
        "endpoint": identity["request"]["endpoint"],
        "frame_sha256": identity["frame"]["sha256"],
        "maximum_uses": 1,
    }
    if len(matches) != 1 or matches[0] != expected_allowlist:
        blockers.append("exact_action_not_allowlisted")
    limits = profile["limits"]
    total_limit = limits["maximum_campaign_visible_refreshes"]
    if total_limit is not None and len(campaign["actions"]) > total_limit:
        blockers.append("campaign_visible_refresh_limit_exceeded")
    session_by_id = {session["session_id"]: session for session in campaign["sessions"]}
    session = session_by_id[identity["session_id"]]
    session_limit = limits["maximum_session_visible_refreshes"]
    consecutive_limit = limits["maximum_consecutive_visible_refreshes"]
    session_count = len(session["action_identity_sha256s"])
    if session_limit is not None and session_count > session_limit:
        blockers.append("session_visible_refresh_limit_exceeded")
    if consecutive_limit is not None and session_count > consecutive_limit:
        blockers.append("consecutive_visible_refresh_limit_exceeded")
    interval_limit = limits["minimum_interval_seconds"]
    prior = identity["prior"]
    if (
        prior is not None
        and interval_limit is not None
        and identity["schedule"]["minimum_interval_since_prior_seconds"] < interval_limit
    ):
        blockers.append("planned_action_interval_too_short")
    cooldown_limit = limits["minimum_cooldown_seconds"]
    if (
        cooldown_limit is not None
        and session["planned_cooldown_seconds"] < cooldown_limit
    ):
        blockers.append("planned_session_cooldown_too_short")
    return blockers


def describe_action_offline(
    campaign: Mapping[str, Any],
    *,
    action_identity_sha256: str,
    limit_profile: Mapping[str, Any],
    evaluated_at: str,
    prior_result: Optional[Mapping[str, Any]] = None,
    prior_result_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Describe one future action with zero I/O, zero claim, and zero authorization.

    A dependency is bound to the canonical whole-file SHA-256 of its immutable
    PASS result.  Wrong-action results are treated as replay/cross-cell attacks
    and rejected.  A valid offline description still never claims that current
    voltage, temperature, operator presence, or authorization has passed, so
    ``hardware_ready`` and ``hardware_execution_authorized`` remain false.
    """

    campaign_root = validate_campaign_contract(campaign)
    profile_root = validate_limit_profile(limit_profile)
    requested_sha = _hash(action_identity_sha256, label="requested action identity SHA-256")
    action_matches = [
        action
        for action in campaign_root["actions"]
        if action["action_identity_sha256"] == requested_sha
    ]
    if len(action_matches) != 1:
        raise CampaignContractError("requested action is not uniquely present in campaign")
    action = action_matches[0]
    decision = evaluate_limit_profile(profile_root, evaluated_at=evaluated_at)
    blockers = list(decision.reasons)
    blockers.extend(_campaign_profile_blockers(campaign_root, profile_root, action))

    prior = action["identity"]["prior"]
    bound_prior: Optional[dict[str, str]] = None
    if prior is None:
        if prior_result is not None or prior_result_sha256 is not None:
            raise CampaignContractError("root action must not be supplied a prior result")
    else:
        if prior_result is None or prior_result_sha256 is None:
            blockers.append("required_prior_result_missing")
        else:
            result = validate_result_record(prior_result)
            supplied_sha = _hash(prior_result_sha256, label="prior result file SHA-256")
            actual_file_sha = result_file_sha256(result)
            if supplied_sha != actual_file_sha:
                raise CampaignContractError("prior result whole-file SHA-256 does not match")
            if result["action_identity_sha256"] != prior["action_identity_sha256"]:
                raise CampaignContractError("prior result belongs to another action")
            bound_prior = {
                "action_identity_sha256": result["action_identity_sha256"],
                "result_file_sha256": actual_file_sha,
                "required_state": prior["required_result_state"],
                "observed_state": result["state"],
            }
            if result["state"] != ResultState.PASS.value:
                blockers.append("prior_result_not_pass")
            else:
                usage = profile_root["usage"]
                recorded_counts = (
                    usage["cumulative_visible_refresh_count"],
                    usage["session_visible_refresh_count"],
                    usage["consecutive_visible_refresh_count"],
                )
                if any(count is None or count < 1 for count in recorded_counts):
                    blockers.append("usage_snapshot_does_not_record_prior_refresh")
                completed_at = _timestamp(
                    result["completed_at"], label="prior result completed_at"
                )
                snapshot_at = _timestamp(
                    usage["snapshot_at"], label="usage snapshot_at", nullable=True
                )
                last_visible = _timestamp(
                    usage["last_visible_refresh_completed_at"],
                    label="usage last_visible_refresh_completed_at",
                    nullable=True,
                )
                assert completed_at is not None
                if snapshot_at is None or snapshot_at < completed_at:
                    blockers.append("usage_snapshot_predates_prior_result")
                if last_visible is None or last_visible < completed_at:
                    blockers.append("usage_last_visible_predates_prior_result")

    contract_ready = not blockers
    # Offline description cannot observe or authorize the current physical run.
    runtime_blocker = "current_runtime_gates_and_exact_authorization_not_evaluated"
    all_blockers = tuple(dict.fromkeys([*blockers, runtime_blocker]))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "campaign_id": campaign_root["campaign_id"],
        "campaign_canonical_sha256": campaign_root["integrity"]["canonical_sha256"],
        "action": _snapshot(action),
        "limit_profile_decision": decision.to_dict(),
        "prior_result_binding": bound_prior,
        "contract_ready": contract_ready,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests_if_future_executor_is_separately_authorized": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": list(all_blockers),
    }
    snapshot = _snapshot(payload)
    snapshot["integrity"] = _integrity(snapshot, DESCRIPTION_HASH_SCOPE)
    validate_action_description(snapshot)
    return snapshot


def validate_action_description(description: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a sealed describe-only artifact without performing any I/O."""

    root = _mapping(description, label="description", keys=_DESCRIPTION_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise CampaignContractError(f"description schema_version must be {SCHEMA_VERSION}")
    if root["kind"] != DESCRIPTION_KIND or root["mode"] != "describe-only":
        raise CampaignContractError("description kind or mode is invalid")
    campaign_id = _token(root["campaign_id"], label="description.campaign_id")
    _hash(
        root["campaign_canonical_sha256"],
        label="description.campaign_canonical_sha256",
    )
    action = validate_fixed_action_declaration(root["action"])
    if action["identity"]["campaign_id"] != campaign_id:
        raise CampaignContractError("description campaign/action binding is inconsistent")

    decision = _mapping(
        root["limit_profile_decision"],
        label="description.limit_profile_decision",
        keys=_LIMIT_DECISION_KEYS,
    )
    if type(decision["hardware_ready"]) is not bool:
        raise CampaignContractError("description limit decision readiness must be boolean")
    _timestamp(decision["evaluated_at"], label="description.limit_profile_decision.evaluated_at")
    _hash(
        decision["profile_canonical_sha256"],
        label="description.limit_profile_decision.profile_canonical_sha256",
    )
    decision_reasons = _list(
        decision["reasons"], label="description.limit_profile_decision.reasons"
    )
    for index, reason in enumerate(decision_reasons):
        _text(reason, label=f"description.limit_profile_decision.reasons[{index}]")
    if len(set(decision_reasons)) != len(decision_reasons):
        raise CampaignContractError("description limit decision reasons are duplicated")
    if decision["hardware_ready"] != (not decision_reasons):
        raise CampaignContractError("description limit decision readiness is inconsistent")

    prior = action["identity"]["prior"]
    binding = root["prior_result_binding"]
    if binding is not None:
        binding_root = _mapping(
            binding,
            label="description.prior_result_binding",
            keys=_PRIOR_RESULT_BINDING_KEYS,
        )
        _hash(
            binding_root["action_identity_sha256"],
            label="description.prior_result_binding.action_identity_sha256",
        )
        _hash(
            binding_root["result_file_sha256"],
            label="description.prior_result_binding.result_file_sha256",
        )
        if binding_root["required_state"] != ResultState.PASS.value:
            raise CampaignContractError("description prior binding must require PASS")
        if binding_root["observed_state"] not in RESULT_STATES:
            raise CampaignContractError("description prior binding observed state is invalid")
        if (
            prior is None
            or binding_root["action_identity_sha256"]
            != prior["action_identity_sha256"]
        ):
            raise CampaignContractError("description prior binding is inconsistent")
    elif prior is None:
        binding_root = None
    else:
        binding_root = None

    blockers = _list(root["blockers"], label="description.blockers")
    for index, blocker in enumerate(blockers):
        _text(blocker, label=f"description.blockers[{index}]")
    if len(set(blockers)) != len(blockers):
        raise CampaignContractError("description blockers are duplicated")
    runtime_blocker = "current_runtime_gates_and_exact_authorization_not_evaluated"
    if runtime_blocker not in blockers:
        raise CampaignContractError("description must retain its runtime authorization blocker")
    if type(root["contract_ready"]) is not bool:
        raise CampaignContractError("description.contract_ready must be boolean")
    static_blockers = [blocker for blocker in blockers if blocker != runtime_blocker]
    if root["contract_ready"] != (not static_blockers):
        raise CampaignContractError("description contract readiness is inconsistent")
    if not set(decision_reasons).issubset(blockers):
        raise CampaignContractError("description omits limit-profile blockers")
    if prior is not None and binding_root is None:
        if "required_prior_result_missing" not in blockers:
            raise CampaignContractError("description omits its missing-prior blocker")
    if (
        binding_root is not None
        and binding_root["observed_state"] != ResultState.PASS.value
        and "prior_result_not_pass" not in blockers
    ):
        raise CampaignContractError("description omits its non-PASS prior blocker")
    if (
        binding_root is not None
        and binding_root["observed_state"] == ResultState.PASS.value
        and "prior_result_not_pass" in blockers
    ):
        raise CampaignContractError("description contradicts its PASS prior binding")

    fixed_false_fields = (
        "hardware_ready",
        "hardware_execution_authorized",
        "authorization_created",
        "claim_created",
        "network_io_performed",
        "device_io_performed",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
    )
    if any(root[field] is not False for field in fixed_false_fields):
        raise CampaignContractError(
            "describe-only artifact must keep hardware, I/O, claim, authorization, retry, and recovery false"
        )
    maximum_posts = root[
        "maximum_post_requests_if_future_executor_is_separately_authorized"
    ]
    if maximum_posts != 1 or type(maximum_posts) is not int:
        raise CampaignContractError("description future maximum POST count must be integer one")
    _validate_integrity(root, label="description", scope=DESCRIPTION_HASH_SCOPE)
    return root


__all__ = [
    "ACTION_KIND",
    "CAMPAIGN_KIND",
    "CLAIM_REGISTRY_ID",
    "CLAIM_REGISTRY_RELATIVE_PATH",
    "DESCRIPTION_KIND",
    "LIMIT_PROFILE_KIND",
    "RESULT_KIND",
    "RESULT_STATES",
    "SESSION_KIND",
    "CampaignContractError",
    "LimitDecision",
    "ResultState",
    "build_fixed_action_declaration",
    "build_result_record",
    "build_session_contract",
    "canonical_json_bytes",
    "describe_action_offline",
    "evaluate_limit_profile",
    "result_file_sha256",
    "seal_campaign_contract",
    "seal_limit_profile",
    "validate_campaign_contract",
    "validate_action_description",
    "validate_fixed_action_declaration",
    "validate_limit_profile",
    "validate_result_record",
    "validate_session_contract",
    "workspace_global_claim_declaration",
]
