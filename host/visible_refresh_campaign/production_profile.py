"""Production, file-bound construction of visible-refresh limit profiles.

The generic :mod:`host.visible_refresh_campaign.contracts` module deliberately
validates JSON values only.  This module is the stricter production boundary:
every identity that purports to describe external evidence is recomputed from
one safely opened local regular file.  Approval is a two-stage operation:

* a draft is deterministically compiled from a physical campaign, firmware
  binary, a truthful limit authority (legacy supplier limits or an explicitly
  non-supplier supervised process policy), and usage evidence; and
* a reviewer authenticates the exact draft and its source-file identities with
  HMAC-SHA256.  The resulting standard limit profile contains the SHA-256 of
  the real, canonical review artifact.

There is no network, device, claim, authorization, retry, or recovery path in
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Optional
import uuid

from tools.local_path_safety import LocalPathSafetyError, require_local_regular_path_syntax

from .contracts import (
    LIMIT_PROFILE_KIND,
    CampaignContractError,
    canonical_json_bytes,
    evaluate_limit_profile,
    seal_limit_profile,
    validate_campaign_contract,
    validate_limit_profile,
)


SCHEMA_VERSION = 1
SUPPLIER_LIMITS_KIND = "mf1750-visible-refresh-supplier-limits"
SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND = (
    "mf1750-visible-refresh-supervised-experimental-process-policy"
)
USAGE_EVIDENCE_KIND = "mf1750-visible-refresh-usage-evidence"
REVIEW_ARTIFACT_KIND = "mf1750-visible-refresh-profile-review-artifact"
REVIEW_AUTHENTICATION_ALGORITHM = "HMAC-SHA256"
REVIEW_SIGNATURE_SCOPE = (
    "entire review artifact excluding authentication.signature; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
APPROVED_PROFILE_PROJECTION_SCOPE = (
    "entire approved limit-profile payload excluding integrity and "
    "review.review_artifact_sha256; UTF-8 JSON with sorted keys, no "
    "whitespace, ensure_ascii=false, allow_nan=false"
)
MF1750_A1_SOURCE_DOCUMENT_SHA256 = (
    "c03ef3c34bbf4ece7d280d37197add64c67d0e13c26bff0861a1d399abbed187"
)
SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION = "supplier_document_limit_authority"
SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION = (
    "operator_selected_supervised_experimental_process_policy"
)
EXACT_SUPPLIER_DOCUMENT_PROVENANCE = "exact_supplier_document_evidence"
OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE = (
    "operator_selected_conservative_process_gate"
)

_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_FIRMWARE_BYTES = 32 * 1024 * 1024
_MAX_SOURCE_DOCUMENT_BYTES = 32 * 1024 * 1024
_MAX_REVIEW_KEY_BYTES = 4096
_MIN_REVIEW_KEY_BYTES = 32
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SEMVER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
_PHYSICAL_PLACEHOLDER_RE = re.compile(
    r"(?:^|[-_. ])(?:UNBOUND|UNKNOWN|PLACEHOLDER|DRAFT|TBD|NONE|NULL|TEST)(?:$|[-_. ])",
    re.IGNORECASE,
)

_LIMIT_FIELDS = (
    "maximum_campaign_visible_refreshes",
    "maximum_session_visible_refreshes",
    "maximum_consecutive_visible_refreshes",
    "minimum_interval_seconds",
    "minimum_cooldown_seconds",
    "minimum_start_temperature_c",
    "maximum_start_temperature_c",
    "maximum_post_refresh_temperature_c",
)
_USAGE_SOURCE_FIELDS = (
    "cumulative_visible_refresh_count",
    "session_visible_refresh_count",
    "consecutive_visible_refresh_count",
    "last_visible_refresh_completed_at",
    "snapshot_at",
)
_VALIDITY_FIELDS = ("valid_from", "expires_at")

_SUPPLIER_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "supplier_id",
        "document_id",
        "issued_at",
        "panel_model",
        "maximum_usage_snapshot_age_seconds",
        "limits",
        "validity",
    }
)
_PROCESS_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "not_a_supplier_rating",
        "supervised_only",
        "automatic_execution",
        "automatic_retry",
        "automatic_recovery",
        "issuer",
        "policy_id",
        "issued_at",
        "panel_model",
        "maximum_usage_snapshot_age_seconds",
        "limits",
        "validity",
        "field_provenance",
    }
)
_FIELD_PROVENANCE_KEYS = frozenset(
    {"classification", "source_document_sha256"}
)
_SUPPLIER_DOCUMENT_UNRATED_PROCESS_FIELDS = frozenset(
    {
        "maximum_campaign_visible_refreshes",
        "maximum_session_visible_refreshes",
        "maximum_consecutive_visible_refreshes",
        "minimum_interval_seconds",
        "minimum_cooldown_seconds",
    }
)
_EXACT_SUPPLIER_DOCUMENT_LIMIT_VALUES = {
    "minimum_start_temperature_c": 0,
    "maximum_start_temperature_c": 50,
    "maximum_post_refresh_temperature_c": 50,
}
_USAGE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "evidence_id",
        "campaign_canonical_sha256",
        "panel",
        "firmware",
        "usage",
    }
)
_REVIEW_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "decision",
        "profile_id",
        "profile_version",
        "draft_profile_file_sha256",
        "draft_profile_canonical_sha256",
        "approved_profile_projection_sha256",
        "approved_profile_projection_sha256_scope",
        "campaign_canonical_sha256",
        "campaign_file_sha256",
        "usage_evidence_file_sha256",
        "usage_canonical_sha256",
        "supplier_limits_file_sha256",
        "limits_canonical_sha256",
        "firmware_binary_sha256",
        "reviewer_id",
        "reviewed_at",
        "authentication",
    }
)
_PROCESS_POLICY_REVIEW_KEYS = frozenset(
    {
        *(_REVIEW_KEYS - {"supplier_limits_file_sha256"}),
        "limit_authority_kind",
        "limit_authority_classification",
        "limit_authority_file_sha256",
    }
)
_SUPPLIER_AUTHORITY_REVIEW_KEYS = frozenset(
    {
        *_REVIEW_KEYS,
        "limit_authority_kind",
        "limit_authority_classification",
        "limit_authority_file_sha256",
    }
)
_AUTHENTICATION_KEYS = frozenset(
    {"algorithm", "key_id", "signature", "signature_scope"}
)


class ProductionProfileError(ValueError):
    """Raised when production evidence or approval fails closed."""


@dataclass(frozen=True)
class ArtifactSnapshot:
    """One immutable read of a local regular file."""

    path: Path
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class ProductionInputs:
    """Deeply validated source snapshots used to compile or verify a profile."""

    campaign: Mapping[str, Any]
    campaign_file: ArtifactSnapshot
    firmware_binary: ArtifactSnapshot
    supplier_limits: Mapping[str, Any]
    supplier_limits_file: ArtifactSnapshot
    usage_evidence: Mapping[str, Any]
    usage_evidence_file: ArtifactSnapshot

    @property
    def limit_authority(self) -> Mapping[str, Any]:
        """Neutral alias retained alongside the legacy supplier field name."""

        return self.supplier_limits

    @property
    def limit_authority_file(self) -> ArtifactSnapshot:
        """Neutral alias retained alongside the legacy supplier file name."""

        return self.supplier_limits_file


@dataclass(frozen=True)
class ApprovalBundle:
    """Canonical review artifact and the standard reviewed limit profile."""

    review_artifact: Mapping[str, Any]
    review_artifact_bytes: bytes
    profile: Mapping[str, Any]
    profile_bytes: bytes


@dataclass(frozen=True)
class ValidatedProductionProfile:
    """Runner-facing result whose bytes all come from one validated read pass.

    The trusted review key is intentionally not retained.  ``reviewer_key_id``
    is its SHA-256 trust-anchor identity; all non-secret source and profile
    bytes remain available through the contained snapshots.
    """

    profile: Mapping[str, Any]
    profile_file: ArtifactSnapshot
    inputs: ProductionInputs
    review_artifact: Optional[Mapping[str, Any]]
    review_artifact_file: Optional[ArtifactSnapshot]
    reviewer_key_id: Optional[str]
    report: Mapping[str, Any]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact_mapping(value: Any, *, label: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionProfileError(f"{label} must be an object")
    actual = set(value)
    if actual != set(keys):
        missing = sorted(set(keys) - actual)
        extra = sorted(actual - set(keys))
        raise ProductionProfileError(
            f"{label} keys differ from contract; missing={missing}, extra={extra}"
        )
    return value


def _text(value: Any, *, label: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ProductionProfileError(
            f"{label} must be 1..{maximum} visible characters without surrounding whitespace"
        )
    return value


def _sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ProductionProfileError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def _timestamp(value: Any, *, label: str, nullable: bool = False) -> Optional[datetime]:
    if value is None and nullable:
        return None
    text = _text(value, label=label, maximum=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProductionProfileError(f"{label} must be an RFC3339 timestamp") from error
    if result.tzinfo is None:
        raise ProductionProfileError(f"{label} must include a timezone")
    return result.astimezone(timezone.utc)


def _nonnegative_number(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise ProductionProfileError(f"{label} must be a non-negative finite number{suffix}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ProductionProfileError(f"{label} must be a non-negative finite number")
    return result


def _finite_number(
    value: Any, *, label: str, nullable: bool = False
) -> Optional[float]:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if nullable else ""
        raise ProductionProfileError(f"{label} must be a finite number{suffix}")
    result = float(value)
    if not math.isfinite(result):
        raise ProductionProfileError(f"{label} must be a finite number")
    return result


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    try:
        lexical = path.absolute()
    except OSError as error:
        raise ProductionProfileError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ProductionProfileError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise ProductionProfileError(
                f"{label} must not contain a symlink or Windows reparse point"
            )


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and getattr(left, "st_mtime_ns", None) == getattr(right, "st_mtime_ns", None)
    )


def _read_descriptor_bytes(descriptor: int, *, maximum_bytes: int, label: str) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > maximum_bytes:
            raise ProductionProfileError(
                f"{label} exceeds the {maximum_bytes}-byte safety limit"
            )
    return b"".join(chunks)


def read_local_regular_file(
    path: Path, *, label: str, maximum_bytes: int
) -> ArtifactSnapshot:
    """Read a local file once and detect redirects or modification during the read."""

    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise ProductionProfileError(str(error)) from error
    _reject_reparse_path_chain(path, label=label)
    try:
        before = os.lstat(path)
    except OSError as error:
        raise ProductionProfileError(f"{label} is unavailable: {error}") from error
    if not stat.S_ISREG(before.st_mode):
        raise ProductionProfileError(f"{label} must be a regular file")
    if before.st_size > maximum_bytes:
        raise ProductionProfileError(
            f"{label} exceeds the {maximum_bytes}-byte safety limit"
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file_identity(before, opened):
            raise ProductionProfileError(f"{label} changed before it could be opened")
        payload = _read_descriptor_bytes(
            descriptor, maximum_bytes=maximum_bytes, label=label
        )
        after_read = os.fstat(descriptor)
        if not _same_file_identity(opened, after_read) or len(payload) != after_read.st_size:
            raise ProductionProfileError(f"{label} changed while it was being read")
    except OSError as error:
        raise ProductionProfileError(f"could not safely read {label}: {error}") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    try:
        after_path = os.lstat(path)
    except OSError as error:
        raise ProductionProfileError(f"{label} changed after it was read: {error}") from error
    if not _same_file_identity(after_read, after_path):
        raise ProductionProfileError(f"{label} path was replaced while it was being read")
    _reject_reparse_path_chain(path, label=label)
    return ArtifactSnapshot(path=path, payload=payload, sha256=_sha256(payload))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProductionProfileError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _parse_json(snapshot: ArtifactSnapshot, *, label: str) -> Mapping[str, Any]:
    try:
        text = snapshot.payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProductionProfileError(f"{label} must be UTF-8 JSON") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ProductionProfileError(f"{label} contains forbidden number {token}")
            ),
        )
    except ProductionProfileError:
        raise
    except json.JSONDecodeError as error:
        raise ProductionProfileError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise ProductionProfileError(f"{label} JSON root must be an object")
    return value


def _read_json(path: Path, *, label: str) -> tuple[Mapping[str, Any], ArtifactSnapshot]:
    snapshot = read_local_regular_file(path, label=label, maximum_bytes=_MAX_JSON_BYTES)
    return _parse_json(snapshot, label=label), snapshot


def _canonical_file(value: Mapping[str, Any], snapshot: ArtifactSnapshot, *, label: str) -> None:
    if snapshot.payload != canonical_json_bytes(value):
        raise ProductionProfileError(f"{label} must use the canonical JSON byte encoding")


def _validate_physical_campaign(
    value: Mapping[str, Any], snapshot: ArtifactSnapshot
) -> Mapping[str, Any]:
    try:
        campaign = validate_campaign_contract(value)
    except CampaignContractError as error:
        raise ProductionProfileError(f"physical campaign is invalid: {error}") from error
    _canonical_file(campaign, snapshot, label="physical campaign")
    panel = campaign["panel"]
    serial = _text(panel["serial"], label="physical campaign panel.serial")
    if _PHYSICAL_PLACEHOLDER_RE.search(serial) is not None:
        raise ProductionProfileError(
            "physical campaign panel.serial is unbound or placeholder data"
        )
    for field, item in panel.items():
        text = _text(item, label=f"physical campaign panel.{field}")
        if _PHYSICAL_PLACEHOLDER_RE.search(text) is not None:
            raise ProductionProfileError(
                f"physical campaign panel.{field} is unbound or placeholder data"
            )
    return campaign


def _validate_limit_and_validity_keys(
    root: Mapping[str, Any], *, label: str
) -> None:
    limits = root["limits"]
    if not isinstance(limits, Mapping) or set(limits) != set(_LIMIT_FIELDS):
        raise ProductionProfileError(f"{label}.limits keys differ from limit profile")
    validity = root["validity"]
    if not isinstance(validity, Mapping) or set(validity) != set(_VALIDITY_FIELDS):
        raise ProductionProfileError(f"{label}.validity keys differ from limit profile")


def _validate_supplier_limits(
    value: Mapping[str, Any], *, panel_model: str
) -> Mapping[str, Any]:
    root = _exact_mapping(value, label="supplier limits", keys=_SUPPLIER_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise ProductionProfileError("supplier limits schema_version is invalid")
    if root["kind"] != SUPPLIER_LIMITS_KIND:
        raise ProductionProfileError("supplier limits kind is invalid")
    _text(root["supplier_id"], label="supplier limits supplier_id")
    _text(root["document_id"], label="supplier limits document_id")
    _timestamp(root["issued_at"], label="supplier limits issued_at")
    if root["panel_model"] != panel_model:
        raise ProductionProfileError("supplier limits panel_model does not match campaign")
    age = _nonnegative_number(
        root["maximum_usage_snapshot_age_seconds"],
        label="supplier limits maximum_usage_snapshot_age_seconds",
        nullable=True,
    )
    if age is not None and age <= 0:
        raise ProductionProfileError(
            "supplier limits maximum_usage_snapshot_age_seconds must be positive"
        )
    _validate_limit_and_validity_keys(root, label="supplier limits")
    return root


def _validate_process_policy(
    value: Mapping[str, Any], *, panel_model: str
) -> Mapping[str, Any]:
    label = "supervised experimental process policy"
    root = _exact_mapping(value, label=label, keys=_PROCESS_POLICY_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise ProductionProfileError(f"{label} schema_version is invalid")
    if root["kind"] != SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND:
        raise ProductionProfileError(f"{label} kind is invalid")
    required_flags = {
        "not_a_supplier_rating": True,
        "supervised_only": True,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    for field, expected in required_flags.items():
        if root[field] is not expected or type(root[field]) is not bool:
            raise ProductionProfileError(
                f"{label} {field} must be exactly {str(expected).lower()}"
            )
    _text(root["issuer"], label=f"{label} issuer")
    _text(root["policy_id"], label=f"{label} policy_id")
    _timestamp(root["issued_at"], label=f"{label} issued_at")
    if root["panel_model"] != panel_model:
        raise ProductionProfileError(f"{label} panel_model does not match campaign")
    age = _nonnegative_number(
        root["maximum_usage_snapshot_age_seconds"],
        label=f"{label} maximum_usage_snapshot_age_seconds",
        nullable=True,
    )
    if age is not None and age <= 0:
        raise ProductionProfileError(
            f"{label} maximum_usage_snapshot_age_seconds must be positive"
        )
    _validate_limit_and_validity_keys(root, label=label)
    limits = root["limits"]
    for field in (
        "maximum_campaign_visible_refreshes",
        "maximum_session_visible_refreshes",
        "maximum_consecutive_visible_refreshes",
    ):
        value = limits[field]
        if value is not None and (
            type(value) is not int or value <= 0
        ):
            raise ProductionProfileError(
                f"{label} limits.{field} must be a positive integer or null"
            )
    for field in ("minimum_interval_seconds", "minimum_cooldown_seconds"):
        _nonnegative_number(
            limits[field], label=f"{label} limits.{field}", nullable=True
        )
    for field in (
        "minimum_start_temperature_c",
        "maximum_start_temperature_c",
        "maximum_post_refresh_temperature_c",
    ):
        _finite_number(
            limits[field], label=f"{label} limits.{field}", nullable=True
        )
    for field in _VALIDITY_FIELDS:
        _timestamp(
            root["validity"][field],
            label=f"{label} validity.{field}",
            nullable=True,
        )
    provenance = root["field_provenance"]
    if not isinstance(provenance, Mapping) or set(provenance) != set(_LIMIT_FIELDS):
        raise ProductionProfileError(
            f"{label} field_provenance must cover every limit exactly"
        )
    allowed = {
        EXACT_SUPPLIER_DOCUMENT_PROVENANCE,
        OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE,
    }
    for field in _LIMIT_FIELDS:
        record = _exact_mapping(
            provenance[field],
            label=f"{label} field_provenance.{field}",
            keys=_FIELD_PROVENANCE_KEYS,
        )
        classification = record["classification"]
        if classification not in allowed:
            raise ProductionProfileError(
                f"{label} field_provenance.{field}.classification is invalid"
            )
        if (
            classification == EXACT_SUPPLIER_DOCUMENT_PROVENANCE
            and field in _SUPPLIER_DOCUMENT_UNRATED_PROCESS_FIELDS
        ):
            raise ProductionProfileError(
                f"{label} cannot present {field} as a supplier rating"
            )
        if classification == EXACT_SUPPLIER_DOCUMENT_PROVENANCE:
            expected_value = _EXACT_SUPPLIER_DOCUMENT_LIMIT_VALUES.get(field)
            if expected_value is None or limits[field] != expected_value:
                raise ProductionProfileError(
                    f"{label} exact supplier evidence for {field} does not match "
                    "the source document value"
                )
        source_sha = _sha(
            record["source_document_sha256"],
            label=f"{label} field_provenance.{field}.source_document_sha256",
        )
        if source_sha != MF1750_A1_SOURCE_DOCUMENT_SHA256:
            raise ProductionProfileError(
                f"{label} field_provenance.{field} binds the wrong source document"
            )
    return root


def _validate_limit_authority(
    value: Mapping[str, Any], *, panel_model: str
) -> Mapping[str, Any]:
    kind = value.get("kind")
    if kind == SUPPLIER_LIMITS_KIND:
        return _validate_supplier_limits(value, panel_model=panel_model)
    if kind == SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND:
        return _validate_process_policy(value, panel_model=panel_model)
    raise ProductionProfileError("limit authority kind is invalid")


def _limit_authority_classification(authority: Mapping[str, Any]) -> str:
    if authority["kind"] == SUPPLIER_LIMITS_KIND:
        return SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION
    return SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION


def build_supervised_experimental_policy_template(
    *, issuer: str, policy_id: str, issued_at: str, panel_model: str
) -> dict[str, Any]:
    """Return an intentionally incomplete, never-approved policy worksheet."""

    _text(issuer, label="policy template issuer")
    _text(policy_id, label="policy template policy_id")
    _timestamp(issued_at, label="policy template issued_at")
    _text(panel_model, label="policy template panel_model")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
        "not_a_supplier_rating": True,
        "supervised_only": True,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "issuer": issuer,
        "policy_id": policy_id,
        "issued_at": issued_at,
        "panel_model": panel_model,
        "maximum_usage_snapshot_age_seconds": None,
        "limits": {field: None for field in _LIMIT_FIELDS},
        "validity": {field: None for field in _VALIDITY_FIELDS},
        "field_provenance": {
            field: {
                "classification": None,
                "source_document_sha256": MF1750_A1_SOURCE_DOCUMENT_SHA256,
            }
            for field in _LIMIT_FIELDS
        },
    }


def verify_mf1750_a1_source_document(path: Path) -> ArtifactSnapshot:
    """Safely read and identify the exact local MF-1750 A1 source PDF."""

    snapshot = read_local_regular_file(
        path,
        label="MF-1750 A1 source document",
        maximum_bytes=_MAX_SOURCE_DOCUMENT_BYTES,
    )
    if snapshot.sha256 != MF1750_A1_SOURCE_DOCUMENT_SHA256:
        raise ProductionProfileError(
            "MF-1750 A1 source document bytes do not match the exact reviewed PDF"
        )
    return snapshot


def _validate_usage_evidence(
    value: Mapping[str, Any], *, campaign: Mapping[str, Any]
) -> Mapping[str, Any]:
    root = _exact_mapping(value, label="usage evidence", keys=_USAGE_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise ProductionProfileError("usage evidence schema_version is invalid")
    if root["kind"] != USAGE_EVIDENCE_KIND:
        raise ProductionProfileError("usage evidence kind is invalid")
    _text(root["evidence_id"], label="usage evidence evidence_id")
    expected_campaign_sha = campaign["integrity"]["canonical_sha256"]
    if _sha(
        root["campaign_canonical_sha256"],
        label="usage evidence campaign_canonical_sha256",
    ) != expected_campaign_sha:
        raise ProductionProfileError("usage evidence belongs to another campaign")
    if root["panel"] != campaign["panel"]:
        raise ProductionProfileError("usage evidence panel binding does not match campaign")
    if root["firmware"] != campaign["firmware"]:
        raise ProductionProfileError("usage evidence firmware binding does not match campaign")
    usage = root["usage"]
    if not isinstance(usage, Mapping) or set(usage) != set(_USAGE_SOURCE_FIELDS):
        raise ProductionProfileError("usage evidence.usage keys differ from contract")
    return root


def load_production_inputs(
    *,
    campaign_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
) -> ProductionInputs:
    """Load and deeply bind every non-review source exactly once."""

    campaign_value, campaign_snapshot = _read_json(
        campaign_file, label="physical campaign"
    )
    campaign = _validate_physical_campaign(campaign_value, campaign_snapshot)
    firmware = read_local_regular_file(
        firmware_binary_file,
        label="firmware binary",
        maximum_bytes=_MAX_FIRMWARE_BYTES,
    )
    if firmware.sha256 != campaign["firmware"]["binary_sha256"]:
        raise ProductionProfileError(
            "firmware binary bytes do not match physical campaign firmware.binary_sha256"
        )
    supplier_value, supplier_snapshot = _read_json(
        supplier_limits_file, label="limit authority"
    )
    supplier = _validate_limit_authority(
        supplier_value, panel_model=str(campaign["panel"]["model"])
    )
    usage_value, usage_snapshot = _read_json(
        usage_evidence_file, label="usage evidence"
    )
    usage = _validate_usage_evidence(usage_value, campaign=campaign)
    return ProductionInputs(
        campaign=campaign,
        campaign_file=campaign_snapshot,
        firmware_binary=firmware,
        supplier_limits=supplier,
        supplier_limits_file=supplier_snapshot,
        usage_evidence=usage,
        usage_evidence_file=usage_snapshot,
    )


def _action_allowlist(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for action in campaign["actions"]:
        identity = action["identity"]
        result.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": identity["request"]["method"],
                "endpoint": identity["request"]["endpoint"],
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    return result


def compile_production_draft(
    inputs: ProductionInputs, *, profile_id: str, profile_version: str
) -> dict[str, Any]:
    """Compile a deterministic, never-approved draft standard limit profile."""

    _text(profile_id, label="profile_id", maximum=128)
    version = _text(profile_version, label="profile_version", maximum=32)
    if _SEMVER_RE.fullmatch(version) is None:
        raise ProductionProfileError("profile_version must be semantic x.y.z")
    source_usage = inputs.usage_evidence["usage"]
    authority_kind = str(inputs.limit_authority["kind"])
    authority_classification = _limit_authority_classification(
        inputs.limit_authority
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": LIMIT_PROFILE_KIND,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "panel": inputs.campaign["panel"],
        "firmware": inputs.campaign["firmware"],
        "action_allowlist": _action_allowlist(inputs.campaign),
        "limits": {
            field: inputs.limit_authority["limits"][field]
            for field in _LIMIT_FIELDS
        },
        "usage": {
            **{field: source_usage[field] for field in _USAGE_SOURCE_FIELDS},
            "evidence_sha256": inputs.usage_evidence_file.sha256,
        },
        "validity": {
            field: inputs.limit_authority["validity"][field]
            for field in _VALIDITY_FIELDS
        },
        "review": {
            "approved": False,
            "reviewer_id": None,
            "reviewed_at": None,
            "review_artifact_sha256": None,
        },
    }
    payload["limit_authority_kind"] = authority_kind
    payload["limit_authority_classification"] = authority_classification
    try:
        return seal_limit_profile(payload)
    except CampaignContractError as error:
        raise ProductionProfileError(f"could not compile production draft: {error}") from error


def compile_production_draft_from_files(
    *,
    campaign_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    profile_id: str,
    profile_version: str,
) -> dict[str, Any]:
    inputs = load_production_inputs(
        campaign_file=campaign_file,
        firmware_binary_file=firmware_binary_file,
        supplier_limits_file=supplier_limits_file,
        usage_evidence_file=usage_evidence_file,
    )
    return compile_production_draft(
        inputs, profile_id=profile_id, profile_version=profile_version
    )


def _load_canonical_profile(
    path: Path, *, label: str
) -> tuple[Mapping[str, Any], ArtifactSnapshot]:
    value, snapshot = _read_json(path, label=label)
    try:
        profile = validate_limit_profile(value)
    except CampaignContractError as error:
        raise ProductionProfileError(f"{label} is invalid: {error}") from error
    _canonical_file(profile, snapshot, label=label)
    return profile, snapshot


def _expected_draft_for_existing_profile(
    profile: Mapping[str, Any], inputs: ProductionInputs
) -> Mapping[str, Any]:
    expected = compile_production_draft(
        inputs,
        profile_id=str(profile["profile_id"]),
        profile_version=str(profile["profile_version"]),
    )
    if (
        inputs.limit_authority["kind"] == SUPPLIER_LIMITS_KIND
        and "limit_authority_kind" not in profile
        and "limit_authority_classification" not in profile
    ):
        legacy_payload = json.loads(canonical_json_bytes(expected).decode("utf-8"))
        legacy_payload.pop("integrity")
        legacy_payload.pop("limit_authority_kind")
        legacy_payload.pop("limit_authority_classification")
        try:
            return seal_limit_profile(legacy_payload)
        except CampaignContractError as error:  # pragma: no cover - defensive
            raise ProductionProfileError(
                f"could not reconstruct legacy supplier profile: {error}"
            ) from error
    return expected


def _require_exact_draft(
    draft: Mapping[str, Any], snapshot: ArtifactSnapshot, inputs: ProductionInputs
) -> Mapping[str, Any]:
    review = draft["review"]
    if review != {
        "approved": False,
        "reviewer_id": None,
        "reviewed_at": None,
        "review_artifact_sha256": None,
    }:
        raise ProductionProfileError("approval input must be an unapproved production draft")
    expected = _expected_draft_for_existing_profile(draft, inputs)
    if draft != expected or snapshot.payload != canonical_json_bytes(expected):
        raise ProductionProfileError(
            "draft profile is not the exact deterministic projection of current source files"
        )
    return expected


def _approval_completeness_blockers(
    draft: Mapping[str, Any], inputs: ProductionInputs, *, reviewed_at: datetime
) -> list[str]:
    blockers: list[str] = []
    for field, value in draft["limits"].items():
        if value is None:
            blockers.append(f"critical_null:limits.{field}")
    usage = draft["usage"]
    for field in (
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
        "snapshot_at",
        "evidence_sha256",
    ):
        if usage[field] is None:
            blockers.append(f"critical_null:usage.{field}")
    if usage["cumulative_visible_refresh_count"] not in (None, 0) and usage[
        "last_visible_refresh_completed_at"
    ] is None:
        blockers.append("critical_null:usage.last_visible_refresh_completed_at")
    for field, value in draft["validity"].items():
        if value is None:
            blockers.append(f"critical_null:validity.{field}")
    maximum_age = inputs.limit_authority["maximum_usage_snapshot_age_seconds"]
    if maximum_age is None:
        blockers.append("critical_null:supplier.maximum_usage_snapshot_age_seconds")
    snapshot_at = _timestamp(
        usage["snapshot_at"], label="usage snapshot_at", nullable=True
    )
    if snapshot_at is not None and snapshot_at > reviewed_at:
        blockers.append("usage_snapshot_after_review")
    valid_from = _timestamp(
        draft["validity"]["valid_from"], label="validity valid_from", nullable=True
    )
    if (
        snapshot_at is not None
        and valid_from is not None
        and maximum_age is not None
        and (valid_from - snapshot_at).total_seconds() > float(maximum_age)
    ):
        blockers.append("usage_snapshot_too_old_at_valid_from")
    issued_at = _timestamp(
        inputs.limit_authority["issued_at"], label="limit authority issued_at"
    )
    assert issued_at is not None
    if issued_at > reviewed_at:
        blockers.append("supplier_document_issued_after_review")
    limits = draft["limits"]
    if all(limits[field] is not None for field in _LIMIT_FIELDS):
        if len(inputs.campaign["actions"]) > limits[
            "maximum_campaign_visible_refreshes"
        ]:
            blockers.append("campaign_visible_refresh_limit_exceeded")
        for session in inputs.campaign["sessions"]:
            action_count = len(session["action_identity_sha256s"])
            if action_count > limits["maximum_session_visible_refreshes"]:
                blockers.append("session_visible_refresh_limit_exceeded")
            if action_count > limits["maximum_consecutive_visible_refreshes"]:
                blockers.append("consecutive_visible_refresh_limit_exceeded")
            if session["planned_cooldown_seconds"] < limits["minimum_cooldown_seconds"]:
                blockers.append("planned_session_cooldown_too_short")
        for action in inputs.campaign["actions"]:
            identity = action["identity"]
            if (
                identity["prior"] is not None
                and identity["schedule"]["minimum_interval_since_prior_seconds"]
                < limits["minimum_interval_seconds"]
            ):
                blockers.append("planned_action_interval_too_short")
    return list(dict.fromkeys(blockers))


def _approved_projection(
    draft: Mapping[str, Any], *, reviewer_id: str, reviewed_at: str
) -> Mapping[str, Any]:
    payload = json.loads(canonical_json_bytes(draft).decode("utf-8"))
    payload.pop("integrity")
    payload["review"] = {
        "approved": True,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
    }
    return payload


def _review_unsigned_bytes(artifact: Mapping[str, Any]) -> bytes:
    unsigned = json.loads(canonical_json_bytes(artifact).decode("utf-8"))
    authentication = unsigned["authentication"]
    authentication.pop("signature")
    return canonical_json_bytes(unsigned)


def _load_review_key(path: Path) -> ArtifactSnapshot:
    snapshot = read_local_regular_file(
        path, label="trusted reviewer key", maximum_bytes=_MAX_REVIEW_KEY_BYTES
    )
    if len(snapshot.payload) < _MIN_REVIEW_KEY_BYTES:
        raise ProductionProfileError(
            f"trusted reviewer key must contain at least {_MIN_REVIEW_KEY_BYTES} bytes"
        )
    return snapshot


def create_production_approval(
    *,
    draft_profile_file: Path,
    campaign_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    reviewer_id: str,
    reviewed_at: str,
    reviewer_key_file: Path,
) -> ApprovalBundle:
    """Authenticate one exact draft and return canonical review/profile bytes."""

    reviewer = _text(reviewer_id, label="reviewer_id")
    reviewed_datetime = _timestamp(reviewed_at, label="reviewed_at")
    assert reviewed_datetime is not None
    inputs = load_production_inputs(
        campaign_file=campaign_file,
        firmware_binary_file=firmware_binary_file,
        supplier_limits_file=supplier_limits_file,
        usage_evidence_file=usage_evidence_file,
    )
    draft, draft_snapshot = _load_canonical_profile(
        draft_profile_file, label="production draft profile"
    )
    exact_draft = _require_exact_draft(draft, draft_snapshot, inputs)
    blockers = _approval_completeness_blockers(
        exact_draft, inputs, reviewed_at=reviewed_datetime
    )
    if blockers:
        raise ProductionProfileError(
            "production draft cannot be approved: " + ", ".join(blockers)
        )
    projection = _approved_projection(
        exact_draft, reviewer_id=reviewer, reviewed_at=reviewed_at
    )
    projection_sha = _sha256(canonical_json_bytes(projection))
    key = _load_review_key(reviewer_key_file)
    authentication = {
        "algorithm": REVIEW_AUTHENTICATION_ALGORITHM,
        "key_id": key.sha256,
        "signature": "",
        "signature_scope": REVIEW_SIGNATURE_SCOPE,
    }
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": REVIEW_ARTIFACT_KIND,
        "decision": "approved",
        "profile_id": exact_draft["profile_id"],
        "profile_version": exact_draft["profile_version"],
        "draft_profile_file_sha256": draft_snapshot.sha256,
        "draft_profile_canonical_sha256": exact_draft["integrity"][
            "canonical_sha256"
        ],
        "approved_profile_projection_sha256": projection_sha,
        "approved_profile_projection_sha256_scope": APPROVED_PROFILE_PROJECTION_SCOPE,
        "campaign_canonical_sha256": inputs.campaign["integrity"][
            "canonical_sha256"
        ],
        "campaign_file_sha256": inputs.campaign_file.sha256,
        "usage_evidence_file_sha256": inputs.usage_evidence_file.sha256,
        "usage_canonical_sha256": _sha256(
            canonical_json_bytes(exact_draft["usage"])
        ),
        "supplier_limits_file_sha256": inputs.supplier_limits_file.sha256,
        "limits_canonical_sha256": _sha256(
            canonical_json_bytes(exact_draft["limits"])
        ),
        "firmware_binary_sha256": inputs.firmware_binary.sha256,
        "reviewer_id": reviewer,
        "reviewed_at": reviewed_at,
        "authentication": authentication,
    }
    authority_kind = str(inputs.limit_authority["kind"])
    if authority_kind == SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND:
        artifact.pop("supplier_limits_file_sha256")
        artifact.update(
            {
                "limit_authority_kind": authority_kind,
                "limit_authority_classification": (
                    _limit_authority_classification(inputs.limit_authority)
                ),
                "limit_authority_file_sha256": inputs.limit_authority_file.sha256,
            }
        )
    elif "limit_authority_kind" in exact_draft:
        artifact.update(
            {
                "limit_authority_kind": authority_kind,
                "limit_authority_classification": (
                    _limit_authority_classification(inputs.limit_authority)
                ),
                "limit_authority_file_sha256": inputs.limit_authority_file.sha256,
            }
        )
    signature = hmac.new(
        key.payload, _review_unsigned_bytes(artifact), hashlib.sha256
    ).hexdigest()
    artifact["authentication"]["signature"] = signature
    artifact_bytes = canonical_json_bytes(artifact)
    artifact_sha = _sha256(artifact_bytes)
    payload = json.loads(canonical_json_bytes(exact_draft).decode("utf-8"))
    payload.pop("integrity")
    payload["review"] = {
        "approved": True,
        "reviewer_id": reviewer,
        "reviewed_at": reviewed_at,
        "review_artifact_sha256": artifact_sha,
    }
    try:
        profile = seal_limit_profile(payload)
    except CampaignContractError as error:
        raise ProductionProfileError(f"approved profile is invalid: {error}") from error
    return ApprovalBundle(
        review_artifact=artifact,
        review_artifact_bytes=artifact_bytes,
        profile=profile,
        profile_bytes=canonical_json_bytes(profile),
    )


def _validate_review_artifact_shape(
    value: Mapping[str, Any],
    *,
    limit_authority_kind: str,
    profile_has_authority_metadata: bool,
) -> Mapping[str, Any]:
    process_policy = (
        limit_authority_kind == SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND
    )
    root = _exact_mapping(
        value,
        label="review artifact",
        keys=(
            _PROCESS_POLICY_REVIEW_KEYS
            if process_policy
            else (
                _SUPPLIER_AUTHORITY_REVIEW_KEYS
                if profile_has_authority_metadata
                else _REVIEW_KEYS
            )
        ),
    )
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise ProductionProfileError("review artifact schema_version is invalid")
    if root["kind"] != REVIEW_ARTIFACT_KIND or root["decision"] != "approved":
        raise ProductionProfileError("review artifact kind or decision is invalid")
    hash_fields = [
        "draft_profile_file_sha256",
        "draft_profile_canonical_sha256",
        "approved_profile_projection_sha256",
        "campaign_canonical_sha256",
        "campaign_file_sha256",
        "usage_evidence_file_sha256",
        "usage_canonical_sha256",
        "limits_canonical_sha256",
        "firmware_binary_sha256",
    ]
    if "supplier_limits_file_sha256" in root:
        hash_fields.append("supplier_limits_file_sha256")
    if "limit_authority_file_sha256" in root:
        hash_fields.append("limit_authority_file_sha256")
    for field in hash_fields:
        _sha(root[field], label=f"review artifact {field}")
    if "limit_authority_kind" in root:
        expected_classification = (
            SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION
            if process_policy
            else SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION
        )
        if (
            root["limit_authority_kind"] != limit_authority_kind
            or root["limit_authority_classification"]
            != expected_classification
        ):
            raise ProductionProfileError(
                "review artifact limit authority identity is invalid"
            )
    _text(root["profile_id"], label="review artifact profile_id", maximum=128)
    _text(root["profile_version"], label="review artifact profile_version", maximum=32)
    _text(root["reviewer_id"], label="review artifact reviewer_id")
    _timestamp(root["reviewed_at"], label="review artifact reviewed_at")
    if root["approved_profile_projection_sha256_scope"] != APPROVED_PROFILE_PROJECTION_SCOPE:
        raise ProductionProfileError("review artifact profile projection scope is invalid")
    authentication = _exact_mapping(
        root["authentication"],
        label="review artifact authentication",
        keys=_AUTHENTICATION_KEYS,
    )
    if (
        authentication["algorithm"] != REVIEW_AUTHENTICATION_ALGORITHM
        or authentication["signature_scope"] != REVIEW_SIGNATURE_SCOPE
    ):
        raise ProductionProfileError("review artifact authentication contract is invalid")
    _sha(authentication["key_id"], label="review artifact authentication.key_id")
    _sha(authentication["signature"], label="review artifact authentication.signature")
    return root


def load_validated_production_profile(
    *,
    profile_file: Path,
    campaign_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    review_artifact_file: Optional[Path] = None,
    reviewer_key_file: Optional[Path] = None,
    evaluated_at: Optional[str] = None,
) -> ValidatedProductionProfile:
    """Read once and return a deeply validated immutable production bundle."""

    inputs = load_production_inputs(
        campaign_file=campaign_file,
        firmware_binary_file=firmware_binary_file,
        supplier_limits_file=supplier_limits_file,
        usage_evidence_file=usage_evidence_file,
    )
    profile, profile_snapshot = _load_canonical_profile(
        profile_file, label="production limit profile"
    )
    review = profile["review"]
    expected_draft = _expected_draft_for_existing_profile(profile, inputs)
    artifact: Optional[Mapping[str, Any]] = None
    artifact_snapshot: Optional[ArtifactSnapshot] = None
    reviewer_key_id: Optional[str] = None
    if review["approved"] is False:
        if review_artifact_file is not None or reviewer_key_file is not None:
            raise ProductionProfileError(
                "an unapproved draft must not be supplied review artifact or reviewer key"
            )
        if profile != expected_draft:
            raise ProductionProfileError(
                "draft profile is not the exact deterministic projection of source files"
            )
    else:
        if review_artifact_file is None or reviewer_key_file is None:
            raise ProductionProfileError(
                "reviewed profile requires both review artifact and trusted reviewer key"
            )
        artifact_value, artifact_snapshot = _read_json(
            review_artifact_file, label="review artifact"
        )
        artifact = _validate_review_artifact_shape(
            artifact_value,
            limit_authority_kind=str(inputs.limit_authority["kind"]),
            profile_has_authority_metadata=(
                "limit_authority_kind" in profile
                and "limit_authority_classification" in profile
            ),
        )
        _canonical_file(artifact, artifact_snapshot, label="review artifact")
        key = _load_review_key(reviewer_key_file)
        reviewer_key_id = key.sha256
        authentication = artifact["authentication"]
        if authentication["key_id"] != key.sha256:
            raise ProductionProfileError("review artifact key_id is not the trusted reviewer key")
        expected_signature = hmac.new(
            key.payload, _review_unsigned_bytes(artifact), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(authentication["signature"], expected_signature):
            raise ProductionProfileError("review artifact authentication signature is invalid")
        expected_bindings = {
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
            "draft_profile_canonical_sha256": expected_draft["integrity"][
                "canonical_sha256"
            ],
            "campaign_canonical_sha256": inputs.campaign["integrity"][
                "canonical_sha256"
            ],
            "campaign_file_sha256": inputs.campaign_file.sha256,
            "usage_evidence_file_sha256": inputs.usage_evidence_file.sha256,
            "usage_canonical_sha256": _sha256(
                canonical_json_bytes(expected_draft["usage"])
            ),
            "limits_canonical_sha256": _sha256(
                canonical_json_bytes(expected_draft["limits"])
            ),
            "firmware_binary_sha256": inputs.firmware_binary.sha256,
            "reviewer_id": review["reviewer_id"],
            "reviewed_at": review["reviewed_at"],
        }
        authority_kind = str(inputs.limit_authority["kind"])
        if "supplier_limits_file_sha256" in artifact:
            expected_bindings["supplier_limits_file_sha256"] = (
                inputs.supplier_limits_file.sha256
            )
        if "limit_authority_file_sha256" in artifact:
            expected_bindings.update(
                {
                    "limit_authority_kind": authority_kind,
                    "limit_authority_classification": (
                        _limit_authority_classification(inputs.limit_authority)
                    ),
                    "limit_authority_file_sha256": (
                        inputs.limit_authority_file.sha256
                    ),
                }
            )
        for field, expected in expected_bindings.items():
            if artifact[field] != expected:
                raise ProductionProfileError(
                    f"review artifact {field} does not bind current production inputs"
                )
        expected_draft_bytes = canonical_json_bytes(expected_draft)
        if artifact["draft_profile_file_sha256"] != _sha256(expected_draft_bytes):
            raise ProductionProfileError("review artifact draft whole-file binding is invalid")
        projection = _approved_projection(
            expected_draft,
            reviewer_id=str(review["reviewer_id"]),
            reviewed_at=str(review["reviewed_at"]),
        )
        if artifact["approved_profile_projection_sha256"] != _sha256(
            canonical_json_bytes(projection)
        ):
            raise ProductionProfileError("review artifact approved-profile binding is invalid")
        if profile["usage"]["evidence_sha256"] != inputs.usage_evidence_file.sha256:
            raise ProductionProfileError("profile usage evidence SHA does not match real file")
        if review["review_artifact_sha256"] != artifact_snapshot.sha256:
            raise ProductionProfileError("profile review artifact SHA does not match real file")
        approved_payload = json.loads(expected_draft_bytes.decode("utf-8"))
        approved_payload.pop("integrity")
        approved_payload["review"] = {
            "approved": True,
            "reviewer_id": review["reviewer_id"],
            "reviewed_at": review["reviewed_at"],
            "review_artifact_sha256": artifact_snapshot.sha256,
        }
        try:
            expected_profile = seal_limit_profile(approved_payload)
        except CampaignContractError as error:  # pragma: no cover - defensive
            raise ProductionProfileError(f"could not reconstruct approved profile: {error}") from error
        if profile != expected_profile:
            raise ProductionProfileError(
                "reviewed profile is not the exact approved production projection"
            )
        reviewed_datetime = _timestamp(review["reviewed_at"], label="reviewed_at")
        assert reviewed_datetime is not None
        blockers = _approval_completeness_blockers(
            expected_draft, inputs, reviewed_at=reviewed_datetime
        )
        if blockers:
            raise ProductionProfileError(
                "reviewed profile no longer satisfies production approval gates: "
                + ", ".join(blockers)
            )

    decision = None
    production_reasons: list[str] = []
    if evaluated_at is not None:
        try:
            decision = evaluate_limit_profile(profile, evaluated_at=evaluated_at)
        except CampaignContractError as error:
            raise ProductionProfileError(f"profile evaluation failed: {error}") from error
        evaluation_time = _timestamp(evaluated_at, label="evaluated_at")
        snapshot_time = _timestamp(
            profile["usage"]["snapshot_at"], label="usage snapshot_at", nullable=True
        )
        maximum_age = inputs.limit_authority[
            "maximum_usage_snapshot_age_seconds"
        ]
        if (
            evaluation_time is not None
            and snapshot_time is not None
            and maximum_age is not None
            and (evaluation_time - snapshot_time).total_seconds() > float(maximum_age)
        ):
            production_reasons.append("usage_snapshot_stale")
        if decision is not None:
            production_reasons = list(
                dict.fromkeys([*decision.reasons, *production_reasons])
            )
    ready = bool(
        review["approved"] is True
        and decision is not None
        and decision.hardware_ready
        and not production_reasons
    )
    authority_kind = str(inputs.limit_authority["kind"])
    authority_classification = _limit_authority_classification(
        inputs.limit_authority
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-visible-refresh-production-profile-validation",
        "deep_bindings_valid": True,
        "approved": review["approved"],
        "production_ready": ready,
        "evaluated_at": evaluated_at,
        "reasons": production_reasons,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_snapshot.sha256,
        "campaign_canonical_sha256": inputs.campaign["integrity"]["canonical_sha256"],
        "campaign_file_sha256": inputs.campaign_file.sha256,
        "firmware_binary_sha256": inputs.firmware_binary.sha256,
        "limit_authority_kind": authority_kind,
        "limit_authority_classification": authority_classification,
        "limit_authority_file_sha256": inputs.limit_authority_file.sha256,
        "supplier_limits_file_sha256": (
            inputs.supplier_limits_file.sha256
            if authority_kind == SUPPLIER_LIMITS_KIND
            else None
        ),
        "usage_evidence_file_sha256": inputs.usage_evidence_file.sha256,
        "review_artifact_file_sha256": (
            artifact_snapshot.sha256 if artifact_snapshot is not None else None
        ),
        "reviewer_key_id": reviewer_key_id,
        "action_allowlist_count": len(profile["action_allowlist"]),
    }
    return ValidatedProductionProfile(
        profile=profile,
        profile_file=profile_snapshot,
        inputs=inputs,
        review_artifact=artifact,
        review_artifact_file=artifact_snapshot,
        reviewer_key_id=reviewer_key_id,
        report=report,
    )


def validate_production_profile(**kwargs: Any) -> dict[str, Any]:
    """Return only the report from :func:`load_validated_production_profile`."""

    return dict(load_validated_production_profile(**kwargs).report)


def describe_production_profile(**kwargs: Any) -> dict[str, Any]:
    """Alias for the read-only validation report used by the CLI describe command."""

    return validate_production_profile(**kwargs)


def _safe_output_parent(path: Path, *, label: str) -> Path:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise ProductionProfileError(str(error)) from error
    _reject_reparse_path_chain(path, label=label)
    if os.path.lexists(path):
        raise ProductionProfileError(f"{label} already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise ProductionProfileError(f"{label} parent is unavailable: {error}") from error
    try:
        require_local_regular_path_syntax(parent, label=f"resolved {label} parent")
    except LocalPathSafetyError as error:
        raise ProductionProfileError(str(error)) from error
    _reject_reparse_path_chain(parent, label=f"resolved {label} parent")
    if not parent.is_dir():
        raise ProductionProfileError(f"{label} parent must be a directory")
    return parent / path.name


def _stage_bytes(destination: Path, payload: bytes) -> Path:
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor: Optional[int] = None
    succeeded = False
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(payload)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:  # pragma: no cover - defensive OS invariant
                raise OSError("short write")
            written += count
        os.fsync(descriptor)
        succeeded = True
    except OSError as error:
        raise ProductionProfileError(
            f"could not stage {destination.name}: {error}"
        ) from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not succeeded:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return temporary


def _link_staged(temporary: Path, destination: Path) -> None:
    _reject_reparse_path_chain(destination.parent, label=f"{destination.name} output parent")
    try:
        os.link(temporary, destination)
    except FileExistsError as error:
        raise ProductionProfileError(
            f"{destination.name} already exists; refusing overwrite"
        ) from error
    except OSError as error:
        raise ProductionProfileError(
            f"could not atomically publish {destination.name}: {error}"
        ) from error


def publish_new_bytes(path: Path, payload: bytes, *, label: str) -> str:
    """Atomically publish one complete local file and refuse every overwrite."""

    destination = _safe_output_parent(path, label=label)
    temporary = _stage_bytes(destination, payload)
    try:
        _link_staged(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return _sha256(payload)


def publish_new_json(path: Path, value: Mapping[str, Any], *, label: str) -> str:
    return publish_new_bytes(path, canonical_json_bytes(value), label=label)


def publish_approval_bundle(
    bundle: ApprovalBundle, *, review_artifact_output: Path, profile_output: Path
) -> tuple[str, str]:
    """Publish the two approval files with no-clobber concurrency semantics."""

    review_destination = _safe_output_parent(
        review_artifact_output, label="review artifact output"
    )
    profile_destination = _safe_output_parent(
        profile_output, label="reviewed profile output"
    )
    if review_destination == profile_destination:
        raise ProductionProfileError("review artifact and profile outputs must differ")
    review_temporary: Optional[Path] = None
    profile_temporary: Optional[Path] = None
    review_linked = False
    try:
        review_temporary = _stage_bytes(
            review_destination, bundle.review_artifact_bytes
        )
        profile_temporary = _stage_bytes(profile_destination, bundle.profile_bytes)
        _link_staged(review_temporary, review_destination)
        review_linked = True
        try:
            _link_staged(profile_temporary, profile_destination)
        except Exception:
            try:
                if os.path.samefile(review_temporary, review_destination):
                    review_destination.unlink()
            except OSError:
                pass
            raise
    finally:
        for temporary in (review_temporary, profile_temporary):
            if temporary is None:
                continue
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    if not review_linked:  # pragma: no cover - defensive clarity
        raise ProductionProfileError("review artifact was not published")
    return _sha256(bundle.review_artifact_bytes), _sha256(bundle.profile_bytes)


__all__ = [
    "APPROVED_PROFILE_PROJECTION_SCOPE",
    "ApprovalBundle",
    "EXACT_SUPPLIER_DOCUMENT_PROVENANCE",
    "MF1750_A1_SOURCE_DOCUMENT_SHA256",
    "OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE",
    "ProductionInputs",
    "ProductionProfileError",
    "ValidatedProductionProfile",
    "REVIEW_ARTIFACT_KIND",
    "REVIEW_AUTHENTICATION_ALGORITHM",
    "SUPPLIER_LIMITS_KIND",
    "SUPPLIER_LIMIT_AUTHORITY_CLASSIFICATION",
    "SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND",
    "SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION",
    "USAGE_EVIDENCE_KIND",
    "build_supervised_experimental_policy_template",
    "compile_production_draft",
    "compile_production_draft_from_files",
    "create_production_approval",
    "describe_production_profile",
    "load_production_inputs",
    "load_validated_production_profile",
    "publish_approval_bundle",
    "publish_new_bytes",
    "publish_new_json",
    "read_local_regular_file",
    "validate_production_profile",
    "verify_mf1750_a1_source_document",
]
