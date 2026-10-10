"""Physical/production N6 browser execution with authenticated evidence.

This module is the only production-live wrapper around the retained N6
browser one-shot core.  Materialization is offline and deterministic.  The
runner reopens every production source, evaluates it against an injected or
real clock, checks three exact operator tokens, and only then delegates to the
legacy claim-before-network kernel.

The legacy records embedded here are compatibility payloads, not trust
anchors.  Trust comes from actual evidence bytes authenticated with a trusted
HMAC key, the physical campaign rebind, and the deep production-profile
validator.  No function claims hardware qualification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import threading
from typing import Any, Callable, Mapping, Optional, Sequence

from host.epd_frame import ControllerMapping
from host.visible_refresh_campaign import (
    CampaignContractError,
    ResultState,
    canonical_json_bytes,
    seal_limit_profile,
    validate_campaign_contract,
)
from host.visible_refresh_campaign import physical_rebind
from host.visible_refresh_campaign.production_profile import (
    ArtifactSnapshot,
    ProductionProfileError,
    ValidatedProductionProfile,
    load_validated_production_profile,
    read_local_regular_file,
)

from . import n6_browser_campaign as browser
from . import n6_visible_execution as legacy
from .durable_io import write_new_bytes_durable
from .pipeline import ApplicationArtifact


SCHEMA_VERSION = 1
PHYSICAL_CONTEXT_KIND = "mf1750-n6-physical-browser-context"
PHYSICAL_MANIFEST_KIND = "mf1750-n6-physical-production-manifest"
AUTHENTICATED_EVIDENCE_KIND = "mf1750-n6-authenticated-evidence"
PHYSICAL_RECEIPT_KIND = "mf1750-n6-physical-production-receipt"
PHYSICAL_RECEIPT_COMMIT_KIND = (
    "mf1750-n6-physical-production-receipt-durable-commit"
)
PHYSICAL_POSTCLAIM_INCIDENT_KIND = (
    "mf1750-n6-physical-production-postclaim-unknown-incident"
)
PHYSICAL_FINALIZED_KIND = "mf1750-n6-physical-production-finalized-bundle"

FORMAL_REVIEW_ROLE = "formal-artifact-review"
RUNTIME_REVIEW_ROLE = "runtime-envelope-review"
EXTERNAL_AUTHORIZATION_ROLE = "external-one-visible-authorization"
RUNTIME_OBSERVATION_ROLE = "live-runtime-observation"
_EVIDENCE_ROLES = frozenset(
    {
        FORMAL_REVIEW_ROLE,
        RUNTIME_REVIEW_ROLE,
        EXTERNAL_AUTHORIZATION_ROLE,
        RUNTIME_OBSERVATION_ROLE,
    }
)

AUTHENTICATION_ALGORITHM = "HMAC-SHA256"
AUTHENTICATION_SCOPE = (
    "entire authenticated N6 evidence object excluding authentication.signature; "
    "UTF-8 canonical JSON"
)
CANONICAL_HASH_SCOPE = (
    "entire document excluding integrity; UTF-8 JSON with sorted keys, no "
    "whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_LIVE_EVALUATION_AGE_SECONDS = 300
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_REVIEW_KEY_BYTES = 64 * 1024
MIN_REVIEW_KEY_BYTES = 32

ACTION_AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_N6_PHYSICAL__ACTION_"
ACTION_AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_PLAN_CONFIRMATION_PREFIX = "CONFIRM_N6_PHYSICAL_PANEL_PLAN"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N6_APPROVED_PRODUCTION_PROFILE"
EXPECTED_RC2G_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
EXPECTED_RC2G_DRIVER_API = "MF1750_R16_CASCADE_V3"

_N5_PHYSICAL_PALETTE_REPLAY_CACHE: dict[str, bytes] = {}
_N5_PHYSICAL_PALETTE_REPLAY_CACHE_LIMIT = 8


class N6PhysicalExecutionError(ValueError):
    """A physical/production N6 gate failed closed before device I/O."""


class N6PhysicalPostClaimUnknown(N6PhysicalExecutionError):
    """The physical action is terminal UNKNOWN after claim consumption."""

    def __init__(self, detail: str, *, receipt: Mapping[str, Any]) -> None:
        super().__init__(detail)
        self.receipt = _snapshot(receipt)


@dataclass(frozen=True)
class N6PhysicalSources:
    """Original values required to reproduce the physical action identity."""

    offline_manifest: Mapping[str, Any]
    physical_anchor_campaign: Mapping[str, Any]
    physical_anchor_campaign_file: Path
    binding_review_bytes: bytes
    minimum_interval_seconds: float
    planned_cooldown_seconds: float
    palette_aggregate: Mapping[str, Any]
    palette_aggregate_file: Path
    n5_physical_palette: "N6N5PhysicalPaletteEvidence"
    gamut_profile: Mapping[str, Any]
    prior_result: Mapping[str, Any]
    prior_result_sha256: str


@dataclass(frozen=True)
class N6N5PhysicalPaletteEvidence:
    """Files needed to replay the N5 physical palette trust boundary.

    ``palette_aggregate`` in :class:`N6PhysicalSources` is deliberately the
    outer N5 physical envelope, never the weaker core aggregate accepted by
    the retained N6 compatibility materializer.  The inner aggregate is only
    released after the physical plan, finalized strict-RC2G bundle, and every
    result directory have been replayed from their original evidence.
    """

    context: Any
    observations: tuple[Mapping[str, Any], ...]
    observation_files: tuple[Path, ...]
    standard_table: Mapping[str, Any]
    standard_table_file: Path
    instrument_qualification: Mapping[str, Any]
    instrument_qualification_file: Path
    finalized_bundle: Mapping[str, Any]
    finalized_bundle_file: Path
    result_dirs: tuple[Path, ...]
    profile_reviewer_key_file: Path


@dataclass(frozen=True)
class N6PhysicalReceiptPaths:
    """Three distinct absolute files forming the durable receipt boundary."""

    receipt_output: Path
    receipt_commit_output: Path
    incident_output: Path


@dataclass(frozen=True)
class N6ProductionProfileFiles:
    profile_file: Path
    campaign_file: Path
    firmware_binary_file: Path
    limit_authority_file: Path
    usage_evidence_file: Path
    review_artifact_file: Path
    reviewer_key_file: Path


@dataclass(frozen=True)
class N6StaticEvidenceFiles:
    formal_review_evidence_file: Path
    runtime_review_evidence_file: Path
    trusted_reviewer_key_file: Path


@dataclass(frozen=True)
class N6RuntimeEvidenceFiles:
    authorization_evidence_file: Path
    runtime_observation_evidence_file: Path
    trusted_reviewer_key_file: Path


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N6PhysicalExecutionError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bounded_text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise N6PhysicalExecutionError(
            f"{label} must be non-empty text no longer than {maximum} characters"
        )
    return value


def _canonical_sha256(value: Any) -> str:
    return _sha256(canonical_json_bytes(value))


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise N6PhysicalExecutionError(
            "N6 physical sealed payload must omit integrity"
        )
    root = _snapshot(payload)
    root["integrity"] = {
        "canonical_sha256": _canonical_sha256(root),
        "canonical_sha256_scope": CANONICAL_HASH_SCOPE,
    }
    return root


def _check_integrity(root: Mapping[str, Any], *, label: str) -> None:
    unsigned = dict(root)
    integrity = unsigned.pop("integrity", None)
    expected = {
        "canonical_sha256": _canonical_sha256(unsigned),
        "canonical_sha256_scope": CANONICAL_HASH_SCOPE,
    }
    if integrity != expected:
        raise N6PhysicalExecutionError(f"{label} canonical integrity is invalid")


def _exact(value: Any, *, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise N6PhysicalExecutionError(f"{label} must be an object")
    if set(value) != keys:
        raise N6PhysicalExecutionError(
            f"{label} fields differ; missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise N6PhysicalExecutionError(f"{label} must be RFC3339 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N6PhysicalExecutionError(f"{label} must be strict RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N6PhysicalExecutionError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _schedule_number(value: Any, *, label: str, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N6PhysicalExecutionError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        requirement = "positive" if positive else "non-negative"
        raise N6PhysicalExecutionError(f"{label} must be finite and {requirement}")
    return result


def _read_bytes(path: Path, *, label: str, maximum_bytes: int) -> ArtifactSnapshot:
    try:
        return read_local_regular_file(path, label=label, maximum_bytes=maximum_bytes)
    except ProductionProfileError as error:
        raise N6PhysicalExecutionError(str(error)) from error


def _review_key(path: Path) -> ArtifactSnapshot:
    snapshot = _read_bytes(
        path, label="N6 trusted reviewer key", maximum_bytes=MAX_REVIEW_KEY_BYTES
    )
    if len(snapshot.payload) < MIN_REVIEW_KEY_BYTES:
        raise N6PhysicalExecutionError(
            f"N6 trusted reviewer key must contain at least {MIN_REVIEW_KEY_BYTES} bytes"
        )
    return snapshot


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise N6PhysicalExecutionError(
                f"N6 physical anchor contains duplicate JSON key {key!r}"
            )
        result[key] = value
    return result


def _canonical_json_snapshot(
    path: Path, *, label: str, maximum_bytes: int
) -> tuple[Mapping[str, Any], ArtifactSnapshot]:
    snapshot = _read_bytes(path, label=label, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N6PhysicalExecutionError(
                    f"{label} contains forbidden number {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N6PhysicalExecutionError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N6PhysicalExecutionError(f"{label} JSON root must be an object")
    if snapshot.payload != canonical_json_bytes(value):
        raise N6PhysicalExecutionError(f"{label} must use canonical JSON bytes")
    return value, snapshot


def _n5_physical_palette_aggregate(
    sources: N6PhysicalSources,
    *,
    expected_panel: Mapping[str, Any],
    expected_firmware: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Replay the N5 physical envelope and return its proven inner aggregate.

    Importing the N5 physical runner lazily keeps the application package free
    of a module-import cycle while still making the production boundary use
    the exact same validators as the N5 producer.
    """

    from host.extended_color import aggregation as n5_aggregation
    from host.extended_color import execution as n5_execution
    from host.extended_color import spectral as n5_spectral
    from tools import mf1750_n5_physical_execution as n5_physical

    envelope_value, envelope_file = _canonical_json_snapshot(
        sources.palette_aggregate_file,
        label="N5 physical palette aggregate",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if envelope_value != sources.palette_aggregate:
        raise N6PhysicalExecutionError(
            "N5 physical palette aggregate object differs from actual canonical file bytes"
        )
    envelope = _exact(
        envelope_value,
        label="N5 physical palette aggregate envelope",
        keys={
            "schema_version",
            "kind",
            "physical_plan_canonical_sha256",
            "execution_contract_canonical_sha256",
            "finalized_bundle_canonical_sha256",
            "strict_action_count",
            "strict_rc2g_verified",
            "every_action_deep_production_profile_replayed",
            "aggregate",
            "classification",
            "integrity",
        },
    )
    if (
        envelope["schema_version"] != n5_physical.SCHEMA_VERSION
        or envelope["kind"] != n5_physical.PHYSICAL_PALETTE_AGGREGATE_KIND
    ):
        raise N6PhysicalExecutionError(
            "N6 requires the N5 production physical palette aggregate envelope; "
            "a core-only aggregate is ineligible"
        )
    unsigned = dict(envelope)
    integrity = unsigned.pop("integrity", None)
    if integrity != n5_execution._integrity(unsigned):  # noqa: SLF001
        raise N6PhysicalExecutionError(
            "N5 physical palette aggregate envelope integrity changed"
        )

    evidence = sources.n5_physical_palette
    if not isinstance(evidence, N6N5PhysicalPaletteEvidence):
        raise N6PhysicalExecutionError(
            "N5 physical palette deep-replay evidence is required"
        )
    if not isinstance(evidence.context, n5_physical.N5PhysicalContext):
        raise N6PhysicalExecutionError("N5 physical palette context type changed")
    if (
        len(evidence.observations) != len(evidence.observation_files)
        or not evidence.observations
        or len({path.resolve() for path in evidence.observation_files})
        != len(evidence.observation_files)
    ):
        raise N6PhysicalExecutionError(
            "N5 physical palette raw observation files are missing or duplicated"
        )
    observations: list[Mapping[str, Any]] = []
    observation_file_sha256s: list[str] = []
    for index, (expected_observation, observation_path) in enumerate(
        zip(evidence.observations, evidence.observation_files)
    ):
        actual_observation, observation_file = _canonical_json_snapshot(
            observation_path,
            label=f"N5 physical palette raw observation {index}",
            maximum_bytes=MAX_EVIDENCE_BYTES,
        )
        if actual_observation != expected_observation:
            raise N6PhysicalExecutionError(
                "N5 physical palette observation object differs from actual canonical file bytes"
            )
        observations.append(actual_observation)
        observation_file_sha256s.append(observation_file.sha256)
    standard_table, standard_table_file = _canonical_json_snapshot(
        evidence.standard_table_file,
        label="N5 physical authoritative standard table",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if standard_table != evidence.standard_table:
        raise N6PhysicalExecutionError(
            "N5 physical standard table object differs from actual canonical file bytes"
        )
    instrument_qualification, instrument_file = _canonical_json_snapshot(
        evidence.instrument_qualification_file,
        label="N5 physical instrument qualification",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if instrument_qualification != evidence.instrument_qualification:
        raise N6PhysicalExecutionError(
            "N5 physical instrument qualification differs from actual canonical file bytes"
        )
    bundle_value, bundle_file = _canonical_json_snapshot(
        evidence.finalized_bundle_file,
        label="N5 physical finalized bundle",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if bundle_value != evidence.finalized_bundle:
        raise N6PhysicalExecutionError(
            "N5 finalized bundle object differs from actual canonical file bytes"
        )
    try:
        replay_key = _canonical_sha256(
            {
                "envelope_file_sha256": envelope_file.sha256,
                "bundle_file_sha256": bundle_file.sha256,
                "observation_file_sha256s": observation_file_sha256s,
                "standard_table_file_sha256": standard_table_file.sha256,
                "instrument_qualification_file_sha256": instrument_file.sha256,
                "physical_context_content_key": (
                    n5_physical._physical_context_cache_key(  # noqa: SLF001
                        evidence.context
                    )
                ),
                "physical_result_content_keys": [
                    n5_physical._physical_result_cache_key(  # noqa: SLF001
                        evidence.context,
                        result_dir,
                        evidence.profile_reviewer_key_file,
                    )
                    for result_dir in evidence.result_dirs
                ],
                "expected_panel": expected_panel,
                "expected_firmware": expected_firmware,
            }
        )
    except n5_physical.N5PhysicalExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N5 physical palette source fingerprint failed: {error}"
        ) from error
    cached = _N5_PHYSICAL_PALETTE_REPLAY_CACHE.get(replay_key)
    if cached is not None:
        replay = json.loads(cached.decode("utf-8"))
        return replay["aggregate"], replay["binding"]
    try:
        plan = n5_physical.validate_n5_physical_context(evidence.context)
        deep = n5_physical.validate_n5_physical_finalized_bundle(
            evidence.context,
            bundle_value,
            result_dirs=evidence.result_dirs,
            profile_reviewer_key_file=evidence.profile_reviewer_key_file,
        )
        rebuilt_envelope = n5_physical.aggregate_n5_physical_palette(
            evidence.context,
            observations,
            standard_table=standard_table,
            instrument_qualification=instrument_qualification,
            finalized_bundle=bundle_value,
            result_dirs=evidence.result_dirs,
            profile_reviewer_key_file=evidence.profile_reviewer_key_file,
        )
    except (
        n5_physical.N5PhysicalExecutionError,
        n5_aggregation.MeasurementAggregationError,
        n5_spectral.SpectralContractError,
    ) as error:
        raise N6PhysicalExecutionError(
            f"N5 physical palette deep replay failed: {error}"
        ) from error
    if envelope != rebuilt_envelope:
        raise N6PhysicalExecutionError(
            "N5 physical palette envelope differs from full raw-observation reconstruction"
        )

    contract = plan["execution_contract"]
    formal_palette_plan = plan["runtime_manifest"]["formal_palette_plan"]
    expected_action_ids = {
        str(slot[field])
        for slot in formal_palette_plan["expected_slots"]
        for field in (
            "primer_action_identity_sha256",
            "target_action_identity_sha256",
        )
    }
    strict_actions = deep.get("strict_actions_by_sha")
    if (
        deep.get("state") != "normal"
        or deep.get("physical_deep_replay") is not True
        or deep.get("strict_rc2g_verified") is not True
        or not isinstance(strict_actions, Mapping)
        or not expected_action_ids.issubset(set(strict_actions))
    ):
        raise N6PhysicalExecutionError(
            "N5 physical palette bundle does not deeply cover the frozen palette plan"
        )
    if (
        plan["physical_rebind"]["physical_campaign"]["panel"]
        != expected_panel
        or plan["physical_rebind"]["physical_campaign"]["firmware"]
        != expected_firmware
    ):
        raise N6PhysicalExecutionError(
            "N5 physical palette belongs to another panel or firmware"
        )

    classification = envelope["classification"]
    if classification != {
        "production_physical": True,
        "offline_structural_only": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }:
        raise N6PhysicalExecutionError(
            "N5 physical palette aggregate classification changed"
        )
    if (
        envelope["physical_plan_canonical_sha256"]
        != plan["integrity"]["canonical_sha256"]
        or envelope["execution_contract_canonical_sha256"]
        != contract["integrity"]["canonical_sha256"]
        or envelope["finalized_bundle_canonical_sha256"]
        != bundle_value["integrity"]["canonical_sha256"]
        or envelope["strict_action_count"] != len(strict_actions)
        or envelope["strict_rc2g_verified"] is not True
        or envelope["every_action_deep_production_profile_replayed"] is not True
    ):
        raise N6PhysicalExecutionError(
            "N5 physical palette plan/bundle/deep-replay lineage changed"
        )
    try:
        aggregate = n5_aggregation.validate_palette_aggregate(
            envelope["aggregate"]
        )
    except n5_aggregation.MeasurementAggregationError as error:
        raise N6PhysicalExecutionError(
            f"N5 physical palette inner aggregate is invalid: {error}"
        ) from error
    if (
        aggregate["plan_canonical_sha256"]
        != formal_palette_plan["integrity"]["canonical_sha256"]
        or aggregate["classification"].get("measured") is not True
        or aggregate["classification"].get("calibrated") is not True
        or aggregate["accepted_sample_count"]
        != aggregate["expected_sample_count"]
        or aggregate["blockers"]
        or aggregate["palette"] is None
    ):
        raise N6PhysicalExecutionError(
            "N5 physical palette inner aggregate is not the complete frozen-plan result"
        )
    binding = {
        "physical_palette_aggregate_canonical_sha256": envelope["integrity"][
            "canonical_sha256"
        ],
        "physical_palette_aggregate_file_sha256": envelope_file.sha256,
        "physical_plan_canonical_sha256": plan["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "finalized_bundle_canonical_sha256": bundle_value["integrity"][
            "canonical_sha256"
        ],
        "finalized_bundle_file_sha256": bundle_file.sha256,
        "raw_observation_count": len(observations),
        "raw_observation_file_sha256s": observation_file_sha256s,
        "standard_table_canonical_sha256": standard_table["integrity"][
            "canonical_sha256"
        ],
        "standard_table_file_sha256": standard_table_file.sha256,
        "instrument_qualification_canonical_sha256": instrument_qualification[
            "integrity"
        ]["canonical_sha256"],
        "instrument_qualification_file_sha256": instrument_file.sha256,
        "strict_action_count": len(strict_actions),
        "palette_plan_required_action_count": len(expected_action_ids),
        "inner_palette_aggregate_canonical_sha256": aggregate["integrity"][
            "canonical_sha256"
        ],
        "physical_deep_replay": True,
        "strict_rc2g_verified": True,
    }
    if len(_N5_PHYSICAL_PALETTE_REPLAY_CACHE) >= (
        _N5_PHYSICAL_PALETTE_REPLAY_CACHE_LIMIT
    ):
        _N5_PHYSICAL_PALETTE_REPLAY_CACHE.pop(
            next(iter(_N5_PHYSICAL_PALETTE_REPLAY_CACHE))
        )
    _N5_PHYSICAL_PALETTE_REPLAY_CACHE[replay_key] = canonical_json_bytes(
        {"aggregate": aggregate, "binding": binding}
    )
    return aggregate, binding


def _authentication_unsigned_bytes(envelope: Mapping[str, Any]) -> bytes:
    unsigned = _snapshot(envelope)
    unsigned["authentication"].pop("signature")
    return canonical_json_bytes(unsigned)


def sign_n6_authenticated_evidence(
    record: Mapping[str, Any],
    *,
    role: str,
    evidence_bytes: bytes,
    binding: Mapping[str, Any],
    trusted_reviewer_key: bytes,
) -> dict[str, Any]:
    """Authenticate an exact record and actual evidence bytes.

    This is a signing primitive, not an approval generator.  Public validators
    always require the original evidence bytes and independently trusted key.
    """

    if role not in _EVIDENCE_ROLES:
        raise N6PhysicalExecutionError("N6 authenticated evidence role is invalid")
    if not isinstance(evidence_bytes, bytes) or not evidence_bytes:
        raise N6PhysicalExecutionError("N6 actual evidence bytes are required")
    if len(evidence_bytes) > MAX_EVIDENCE_BYTES:
        raise N6PhysicalExecutionError("N6 actual evidence exceeds the size limit")
    if (
        not isinstance(trusted_reviewer_key, bytes)
        or len(trusted_reviewer_key) < MIN_REVIEW_KEY_BYTES
        or len(trusted_reviewer_key) > MAX_REVIEW_KEY_BYTES
    ):
        raise N6PhysicalExecutionError("N6 trusted reviewer key bytes are invalid")
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": AUTHENTICATED_EVIDENCE_KIND,
        "role": role,
        "record": _snapshot(record),
        "record_canonical_sha256": _canonical_sha256(record),
        "actual_evidence": {
            "bytes": len(evidence_bytes),
            "sha256": _sha256(evidence_bytes),
            "actual_bytes_hashed": True,
        },
        "binding": _snapshot(binding),
        "authentication": {
            "algorithm": AUTHENTICATION_ALGORITHM,
            "key_id": _sha256(trusted_reviewer_key),
            "signature": "",
            "signature_scope": AUTHENTICATION_SCOPE,
        },
    }
    signature = hmac.new(
        trusted_reviewer_key,
        _authentication_unsigned_bytes(root),
        hashlib.sha256,
    ).hexdigest()
    root["authentication"]["signature"] = signature
    return _snapshot(root)


def validate_n6_authenticated_evidence(
    envelope: Mapping[str, Any],
    *,
    role: str,
    expected_record: Mapping[str, Any],
    expected_binding: Mapping[str, Any],
    actual_evidence_bytes: bytes,
    trusted_reviewer_key: bytes,
) -> Mapping[str, Any]:
    root = _exact(
        envelope,
        label="N6 authenticated evidence",
        keys={
            "schema_version",
            "kind",
            "role",
            "record",
            "record_canonical_sha256",
            "actual_evidence",
            "binding",
            "authentication",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != AUTHENTICATED_EVIDENCE_KIND
        or root["role"] != role
        or role not in _EVIDENCE_ROLES
    ):
        raise N6PhysicalExecutionError(
            "N6 authenticated evidence kind/version/role is invalid"
        )
    if root["record"] != expected_record:
        raise N6PhysicalExecutionError("authenticated N6 record binding changed")
    if root["record_canonical_sha256"] != _canonical_sha256(expected_record):
        raise N6PhysicalExecutionError("authenticated N6 record SHA-256 changed")
    if root["binding"] != expected_binding:
        raise N6PhysicalExecutionError("authenticated N6 evidence binding changed")
    if not isinstance(actual_evidence_bytes, bytes) or not actual_evidence_bytes:
        raise N6PhysicalExecutionError("actual N6 evidence bytes are required")
    evidence = _exact(
        root["actual_evidence"],
        label="authenticated N6 actual_evidence",
        keys={"bytes", "sha256", "actual_bytes_hashed"},
    )
    if evidence != {
        "bytes": len(actual_evidence_bytes),
        "sha256": _sha256(actual_evidence_bytes),
        "actual_bytes_hashed": True,
    }:
        raise N6PhysicalExecutionError(
            "authenticated N6 evidence does not match actual bytes"
        )
    if (
        not isinstance(trusted_reviewer_key, bytes)
        or len(trusted_reviewer_key) < MIN_REVIEW_KEY_BYTES
        or len(trusted_reviewer_key) > MAX_REVIEW_KEY_BYTES
    ):
        raise N6PhysicalExecutionError("trusted N6 reviewer key bytes are invalid")
    authentication = _exact(
        root["authentication"],
        label="N6 evidence authentication",
        keys={"algorithm", "key_id", "signature", "signature_scope"},
    )
    if (
        authentication["algorithm"] != AUTHENTICATION_ALGORITHM
        or authentication["signature_scope"] != AUTHENTICATION_SCOPE
        or authentication["key_id"] != _sha256(trusted_reviewer_key)
    ):
        raise N6PhysicalExecutionError(
            "N6 evidence authentication trust anchor changed"
        )
    expected_signature = hmac.new(
        trusted_reviewer_key,
        _authentication_unsigned_bytes(root),
        hashlib.sha256,
    ).hexdigest()
    signature = authentication["signature"]
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, expected_signature
    ):
        raise N6PhysicalExecutionError(
            "N6 evidence HMAC authentication signature is invalid"
        )
    return root


def _action_allowlist(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action_id": action["identity"]["action_id"],
            "action_identity_sha256": action["action_identity_sha256"],
            "method": action["identity"]["request"]["method"],
            "endpoint": action["identity"]["request"]["endpoint"],
            "frame_sha256": action["identity"]["frame"]["sha256"],
            "maximum_uses": 1,
        }
        for action in campaign["actions"]
    ]


def _physical_offline_manifest(
    offline_manifest: Mapping[str, Any],
    rebind_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    offline = browser.validate_n6_offline_manifest(offline_manifest)
    campaign = validate_campaign_contract(rebind_manifest["physical_campaign"])
    if len(campaign["actions"]) != 1 or len(campaign["sessions"]) != 1:
        raise N6PhysicalExecutionError(
            "N6 physical campaign must retain exactly one action/session"
        )
    action = campaign["actions"][0]
    draft_payload = _snapshot(offline["draft_limit_profile"])
    draft_payload.pop("integrity")
    draft_payload.update(
        {
            "profile_id": f"n6-physical-unreviewed-{action['action_identity_sha256'][:16]}",
            "panel": _snapshot(campaign["panel"]),
            "firmware": _snapshot(campaign["firmware"]),
            "action_allowlist": _action_allowlist(campaign),
            "review": {
                "approved": False,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_artifact_sha256": None,
            },
        }
    )
    try:
        draft = seal_limit_profile(draft_payload)
    except CampaignContractError as error:
        raise N6PhysicalExecutionError(
            f"could not rebuild N6 physical draft profile: {error}"
        ) from error
    payload = _snapshot(offline)
    payload.pop("integrity")
    payload.update(
        {
            "campaign_id": campaign["campaign_id"],
            "p0_campaign": _snapshot(campaign),
            "p0_action_identity_sha256": action["action_identity_sha256"],
            "p0_claim_declaration": _snapshot(action["claim"]),
            "draft_limit_profile": draft,
        }
    )
    payload["integrity"] = browser._integrity(  # noqa: SLF001 - audited adapter
        payload, browser.MANIFEST_HASH_SCOPE
    )
    try:
        browser.validate_n6_offline_manifest(payload)
    except browser.N6BrowserCampaignError as error:
        raise N6PhysicalExecutionError(
            f"rebuilt N6 physical offline manifest is invalid: {error}"
        ) from error
    return payload


def compile_n6_physical_context(sources: N6PhysicalSources) -> dict[str, Any]:
    interval = _schedule_number(
        sources.minimum_interval_seconds,
        label="N6 materialized minimum interval",
        positive=True,
    )
    cooldown = _schedule_number(
        sources.planned_cooldown_seconds,
        label="N6 materialized planned cooldown",
        positive=False,
    )
    anchor_value, anchor_snapshot = _canonical_json_snapshot(
        sources.physical_anchor_campaign_file,
        label="N6 physical anchor campaign",
        maximum_bytes=16 * 1024 * 1024,
    )
    if anchor_value != sources.physical_anchor_campaign:
        raise N6PhysicalExecutionError(
            "N6 physical anchor object differs from actual canonical anchor file bytes"
        )
    anchor_firmware = anchor_value.get("firmware")
    if (
        not isinstance(anchor_firmware, Mapping)
        or anchor_firmware.get("build_tag") != EXPECTED_RC2G_BUILD_TAG
        or anchor_firmware.get("driver_api") != EXPECTED_RC2G_DRIVER_API
    ):
        raise N6PhysicalExecutionError(
            "N6 physical anchor must bind the exact reviewed RC2G build/API"
        )
    _inner_palette, n5_palette_binding = _n5_physical_palette_aggregate(
        sources,
        expected_panel=anchor_value["panel"],
        expected_firmware=anchor_firmware,
    )
    try:
        rebind_manifest = physical_rebind.compile_physical_campaign_rebind(
            sources.offline_manifest["p0_campaign"],
            anchor_value,
            namespace="n6-browser-production",
            binding_review_bytes=sources.binding_review_bytes,
            minimum_interval_seconds=interval,
            planned_cooldown_seconds=cooldown,
        )
    except (KeyError, physical_rebind.PhysicalCampaignRebindError) as error:
        raise N6PhysicalExecutionError(f"N6 physical rebind failed: {error}") from error
    physical_offline = _physical_offline_manifest(
        sources.offline_manifest, rebind_manifest
    )
    source_action = sources.offline_manifest["p0_action_identity_sha256"]
    physical_action = physical_offline["p0_action_identity_sha256"]
    if source_action == physical_action:
        raise N6PhysicalExecutionError(
            "N6 physical action reused the offline/UNBOUND identity"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHYSICAL_CONTEXT_KIND,
        "physical_anchor_file": {
            "bytes": len(anchor_snapshot.payload),
            "sha256": anchor_snapshot.sha256,
            "actual_bytes_hashed": True,
        },
        "physical_rebind": rebind_manifest,
        "physical_offline_manifest": physical_offline,
        "n5_physical_palette_binding": n5_palette_binding,
        "operator_schedule": {
            "classification": "operator_selected_experimental_process_schedule",
            "not_a_supplier_rating": True,
            "minimum_interval_seconds": interval,
            "planned_cooldown_seconds": cooldown,
        },
        "identity_rotation": {
            "source_action_identity_sha256": source_action,
            "physical_action_identity_sha256": physical_action,
            "source_claim_filename": sources.offline_manifest[
                "p0_claim_declaration"
            ]["filename"],
            "physical_claim_filename": physical_offline["p0_claim_declaration"][
                "filename"
            ],
        },
        "classification": {
            "offline_materialized": True,
            "physical_panel_instance_bound": True,
            "actual_physical_anchor_file_bytes_bound": True,
            "n5_physical_palette_deep_replayed": True,
            "n5_strict_rc2g_bundle_replayed": True,
            "firmware_binary_deep_validation_required": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "hardware_qualification_claimed": False,
        },
    }
    return _seal(payload)


def validate_n6_physical_context(
    context: Mapping[str, Any], *, sources: N6PhysicalSources
) -> Mapping[str, Any]:
    root = _exact(
        context,
        label="N6 physical context",
        keys={
            "schema_version",
            "kind",
            "physical_anchor_file",
            "physical_rebind",
            "physical_offline_manifest",
            "n5_physical_palette_binding",
            "operator_schedule",
            "identity_rotation",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PHYSICAL_CONTEXT_KIND:
        raise N6PhysicalExecutionError("N6 physical context kind/version is invalid")
    expected = compile_n6_physical_context(sources)
    if root != expected:
        raise N6PhysicalExecutionError(
            "N6 physical context differs from deterministic source reconstruction"
        )
    _check_integrity(root, label="N6 physical context")
    return root


def _load_production(
    files: N6ProductionProfileFiles, *, evaluated_at: str
) -> ValidatedProductionProfile:
    _timestamp(evaluated_at, label="N6 production profile evaluated_at")
    try:
        production = load_validated_production_profile(
            profile_file=files.profile_file,
            campaign_file=files.campaign_file,
            firmware_binary_file=files.firmware_binary_file,
            supplier_limits_file=files.limit_authority_file,
            usage_evidence_file=files.usage_evidence_file,
            review_artifact_file=files.review_artifact_file,
            reviewer_key_file=files.reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N6PhysicalExecutionError(
            f"N6 production profile deep validation failed: {error}"
        ) from error
    if (
        production.report["approved"] is not True
        or production.report["production_ready"] is not True
        or production.review_artifact_file is None
        or production.reviewer_key_id is None
    ):
        reasons = production.report.get("reasons") or ["not approved/ready"]
        raise N6PhysicalExecutionError(
            "N6 production profile is not ready: " + ", ".join(reasons)
        )
    return production


def _production_binding(
    production: ValidatedProductionProfile,
) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N6PhysicalExecutionError(
            "N6 production profile review trust chain is incomplete"
        )
    return {
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "campaign_canonical_sha256": production.inputs.campaign["integrity"][
            "canonical_sha256"
        ],
        "campaign_file_sha256": production.inputs.campaign_file.sha256,
        "firmware_binary_sha256": production.inputs.firmware_binary.sha256,
        "limit_authority_kind": production.inputs.limit_authority["kind"],
        "limit_authority_file_sha256": production.inputs.limit_authority_file.sha256,
        "usage_evidence_file_sha256": production.inputs.usage_evidence_file.sha256,
        "profile_review_artifact_file_sha256": review.sha256,
        "reviewer_key_id": production.reviewer_key_id,
        "action_allowlist": _snapshot(production.profile["action_allowlist"]),
    }


def _validate_production_for_context(
    production: ValidatedProductionProfile, context: Mapping[str, Any]
) -> None:
    campaign = context["physical_rebind"]["physical_campaign"]
    if production.inputs.campaign != campaign:
        raise N6PhysicalExecutionError(
            "N6 production profile belongs to another physical campaign"
        )
    if production.profile["panel"] != campaign["panel"]:
        raise N6PhysicalExecutionError(
            "N6 production profile belongs to another physical panel"
        )
    if production.profile["firmware"] != campaign["firmware"]:
        raise N6PhysicalExecutionError(
            "N6 production profile firmware binding changed"
        )
    if production.profile["action_allowlist"] != _action_allowlist(campaign):
        raise N6PhysicalExecutionError(
            "N6 production profile must contain the complete exact action allowlist"
        )
    if (
        production.inputs.firmware_binary.sha256
        != campaign["firmware"]["binary_sha256"]
    ):
        raise N6PhysicalExecutionError(
            "N6 actual firmware bytes differ from physical campaign"
        )


def _static_review_binding(
    context: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    role: str,
) -> dict[str, Any]:
    if role not in {FORMAL_REVIEW_ROLE, RUNTIME_REVIEW_ROLE}:
        raise N6PhysicalExecutionError("N6 static review role is invalid")
    offline = context["physical_offline_manifest"]
    campaign = context["physical_rebind"]["physical_campaign"]
    return {
        "role": role,
        "physical_context_canonical_sha256": context["integrity"][
            "canonical_sha256"
        ],
        "physical_offline_manifest_canonical_sha256": offline["integrity"][
            "canonical_sha256"
        ],
        "physical_campaign_canonical_sha256": campaign["integrity"][
            "canonical_sha256"
        ],
        "action_identity_sha256": offline["p0_action_identity_sha256"],
        "panel": _snapshot(campaign["panel"]),
        "firmware": _snapshot(campaign["firmware"]),
        "production_profile": _production_binding(production),
    }


def static_review_binding(
    context: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    role: str,
) -> dict[str, Any]:
    """Return the exact binding an external N6 review signer must authenticate."""

    return _static_review_binding(context, production, role=role)


def _review_evidence_hash(record: Mapping[str, Any], *, role: str) -> str:
    if role == FORMAL_REVIEW_ROLE:
        try:
            reviewed = legacy.validate_n6_formal_artifact_review(record)
        except legacy.N6VisibleExecutionError as error:
            raise N6PhysicalExecutionError(
                f"N6 formal artifact review is invalid: {error}"
            ) from error
        return str(reviewed["review"]["review_artifact_sha256"])
    if role == RUNTIME_REVIEW_ROLE:
        try:
            reviewed = legacy.validate_n6_runtime_review(record)
        except legacy.N6VisibleExecutionError as error:
            raise N6PhysicalExecutionError(
                f"N6 runtime review is invalid: {error}"
            ) from error
        return str(reviewed["review"]["review_artifact_sha256"])
    raise N6PhysicalExecutionError("N6 review evidence role is invalid")


def _validate_static_envelope(
    envelope: Mapping[str, Any],
    *,
    role: str,
    context: Mapping[str, Any],
    production: ValidatedProductionProfile,
    evidence: ArtifactSnapshot,
    trusted_key: ArtifactSnapshot,
) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping) or not isinstance(
        envelope.get("record"), Mapping
    ):
        raise N6PhysicalExecutionError("N6 authenticated review record is missing")
    record = envelope["record"]
    if _review_evidence_hash(record, role=role) != evidence.sha256:
        raise N6PhysicalExecutionError(
            "N6 review record does not bind the actual review evidence bytes"
        )
    root = validate_n6_authenticated_evidence(
        envelope,
        role=role,
        expected_record=record,
        expected_binding=_static_review_binding(context, production, role=role),
        actual_evidence_bytes=evidence.payload,
        trusted_reviewer_key=trusted_key.payload,
    )
    if root["authentication"]["key_id"] != production.reviewer_key_id:
        raise N6PhysicalExecutionError(
            "N6 static review key differs from production-profile reviewer trust anchor"
        )
    return root


def _load_static_evidence(
    files: N6StaticEvidenceFiles,
) -> tuple[ArtifactSnapshot, ArtifactSnapshot, ArtifactSnapshot]:
    formal = _read_bytes(
        files.formal_review_evidence_file,
        label="N6 formal artifact review evidence",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    runtime = _read_bytes(
        files.runtime_review_evidence_file,
        label="N6 runtime review evidence",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    key = _review_key(files.trusted_reviewer_key_file)
    return formal, runtime, key


_PHYSICAL_EXECUTION_POLICY = {
    "physical_production_wrapper_required": True,
    "actual_clock_required_for_live": True,
    "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATION_AGE_SECONDS,
    "three_exact_operator_tokens_required": True,
    "workspace_global_claim_before_any_device_network": True,
    "maximum_frame_posts": 1,
    "automatic_retry": False,
    "automatic_recovery": False,
    "post_claim_failure": "UNKNOWN_DO_NOT_RETRY",
}


_PHYSICAL_CLASSIFICATION = {
    "offline_materialized": True,
    "physical_panel_instance_bound": True,
    "actual_firmware_bytes_bound": True,
    "authenticated_static_reviews_complete": True,
    "deep_production_profile_complete": True,
    "n5_physical_palette_deep_replayed": True,
    "n5_strict_rc2g_bundle_replayed": True,
    "hardware_execution_authorized": False,
    "external_authorization_created": False,
    "claim_created": False,
    "network_io_performed": False,
    "device_io_performed": False,
    "hardware_qualification_claimed": False,
    "automatic_retry": False,
    "automatic_recovery": False,
}


def _materialize_with_loaded(
    context: Mapping[str, Any],
    *,
    sources: N6PhysicalSources,
    production: ValidatedProductionProfile,
    formal_review_envelope: Mapping[str, Any],
    runtime_review_envelope: Mapping[str, Any],
    formal_evidence: ArtifactSnapshot,
    runtime_evidence: ArtifactSnapshot,
    trusted_key: ArtifactSnapshot,
    materialized_at: str,
) -> dict[str, Any]:
    validated_context = validate_n6_physical_context(context, sources=sources)
    physical_campaign = validated_context["physical_rebind"]["physical_campaign"]
    inner_palette_aggregate, n5_palette_binding = (
        _n5_physical_palette_aggregate(
            sources,
            expected_panel=physical_campaign["panel"],
            expected_firmware=physical_campaign["firmware"],
        )
    )
    if n5_palette_binding != validated_context["n5_physical_palette_binding"]:
        raise N6PhysicalExecutionError(
            "N5 physical palette binding changed after context validation"
        )
    _validate_production_for_context(production, validated_context)
    formal_envelope = _validate_static_envelope(
        formal_review_envelope,
        role=FORMAL_REVIEW_ROLE,
        context=validated_context,
        production=production,
        evidence=formal_evidence,
        trusted_key=trusted_key,
    )
    runtime_envelope = _validate_static_envelope(
        runtime_review_envelope,
        role=RUNTIME_REVIEW_ROLE,
        context=validated_context,
        production=production,
        evidence=runtime_evidence,
        trusted_key=trusted_key,
    )
    materialized_time = _timestamp(
        materialized_at, label="N6 physical materialized_at"
    )
    for role, envelope in (
        (FORMAL_REVIEW_ROLE, formal_envelope),
        (RUNTIME_REVIEW_ROLE, runtime_envelope),
    ):
        reviewed_at = envelope["record"]["review"]["reviewed_at"]
        if _timestamp(reviewed_at, label=f"N6 {role} reviewed_at") > materialized_time:
            raise N6PhysicalExecutionError(
                f"N6 {role} occurs after physical materialization"
            )
    offline = validated_context["physical_offline_manifest"]
    try:
        formal_manifest = legacy.materialize_n6_formal_manifest(
            offline,
            materialized_at=materialized_at,
            palette_aggregate=inner_palette_aggregate,
            gamut_profile=sources.gamut_profile,
            formal_artifact_review=formal_envelope["record"],
            reviewed_limit_profile=production.profile,
            runtime_review=runtime_envelope["record"],
            prior_result=sources.prior_result,
            prior_result_sha256=sources.prior_result_sha256,
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N6 compatibility formal materialization failed: {error}"
        ) from error
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHYSICAL_MANIFEST_KIND,
        "materialized_at": materialized_at,
        "physical_context": _snapshot(validated_context),
        "legacy_formal_manifest": formal_manifest,
        "n5_physical_palette_binding": _snapshot(n5_palette_binding),
        "production_profile_binding": _production_binding(production),
        "authenticated_static_reviews": {
            "formal_artifact_review": _snapshot(formal_envelope),
            "runtime_review": _snapshot(runtime_envelope),
        },
        "operator_schedule": _snapshot(validated_context["operator_schedule"]),
        "execution_policy": _snapshot(_PHYSICAL_EXECUTION_POLICY),
        "classification": _snapshot(_PHYSICAL_CLASSIFICATION),
    }
    return _seal(payload)


def materialize_n6_physical_manifest(
    context: Mapping[str, Any],
    *,
    sources: N6PhysicalSources,
    production_files: N6ProductionProfileFiles,
    static_evidence_files: N6StaticEvidenceFiles,
    formal_review_envelope: Mapping[str, Any],
    runtime_review_envelope: Mapping[str, Any],
    materialized_at: str,
) -> dict[str, Any]:
    """Materialize a physical N6 manifest without creating authorization/claim."""

    _timestamp(materialized_at, label="N6 physical materialized_at")
    production = _load_production(production_files, evaluated_at=materialized_at)
    formal_evidence, runtime_evidence, trusted_key = _load_static_evidence(
        static_evidence_files
    )
    root = _materialize_with_loaded(
        context,
        sources=sources,
        production=production,
        formal_review_envelope=formal_review_envelope,
        runtime_review_envelope=runtime_review_envelope,
        formal_evidence=formal_evidence,
        runtime_evidence=runtime_evidence,
        trusted_key=trusted_key,
        materialized_at=materialized_at,
    )
    validate_n6_physical_manifest(
        root,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_evidence_files,
        evaluated_at=materialized_at,
    )
    return root


def validate_n6_physical_manifest(
    manifest: Mapping[str, Any],
    *,
    sources: N6PhysicalSources,
    production_files: N6ProductionProfileFiles,
    static_evidence_files: N6StaticEvidenceFiles,
    evaluated_at: str,
) -> Mapping[str, Any]:
    """Deeply validate a physical manifest against all original bytes/files."""

    root = _exact(
        manifest,
        label="N6 physical production manifest",
        keys={
            "schema_version",
            "kind",
            "materialized_at",
            "physical_context",
            "legacy_formal_manifest",
            "n5_physical_palette_binding",
            "production_profile_binding",
            "authenticated_static_reviews",
            "operator_schedule",
            "execution_policy",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PHYSICAL_MANIFEST_KIND:
        raise N6PhysicalExecutionError(
            "N6 physical production manifest kind/version is invalid"
        )
    materialized_at = root["materialized_at"]
    _timestamp(materialized_at, label="N6 physical materialized_at")
    production = _load_production(production_files, evaluated_at=evaluated_at)
    formal_evidence, runtime_evidence, trusted_key = _load_static_evidence(
        static_evidence_files
    )
    reviews = _exact(
        root["authenticated_static_reviews"],
        label="N6 authenticated static reviews",
        keys={"formal_artifact_review", "runtime_review"},
    )
    expected = _materialize_with_loaded(
        root["physical_context"],
        sources=sources,
        production=production,
        formal_review_envelope=reviews["formal_artifact_review"],
        runtime_review_envelope=reviews["runtime_review"],
        formal_evidence=formal_evidence,
        runtime_evidence=runtime_evidence,
        trusted_key=trusted_key,
        materialized_at=materialized_at,
    )
    if root != expected:
        raise N6PhysicalExecutionError(
            "N6 physical production manifest differs from deep reconstruction"
        )
    if (
        root["n5_physical_palette_binding"]
        != root["physical_context"]["n5_physical_palette_binding"]
        or root["production_profile_binding"] != _production_binding(production)
        or root["operator_schedule"]
        != root["physical_context"]["operator_schedule"]
        or root["execution_policy"] != _PHYSICAL_EXECUTION_POLICY
        or root["classification"] != _PHYSICAL_CLASSIFICATION
    ):
        raise N6PhysicalExecutionError(
            "N6 physical production policy/profile binding changed"
        )
    _check_integrity(root, label="N6 physical production manifest")
    return root


def required_n6_action_authorization(manifest: Mapping[str, Any]) -> str:
    action_sha = manifest["legacy_formal_manifest"]["action"][
        "action_identity_sha256"
    ]
    return (
        f"{ACTION_AUTHORIZATION_PREFIX}{str(action_sha).upper()}"
        f"{ACTION_AUTHORIZATION_SUFFIX}"
    )


def required_n6_panel_plan_confirmation(manifest: Mapping[str, Any]) -> str:
    context = manifest["physical_context"]
    panel = context["physical_rebind"]["physical_campaign"]["panel"]
    return (
        f"{PANEL_PLAN_CONFIRMATION_PREFIX}"
        f"__SERIAL_{panel['serial']}"
        f"__PLAN_{context['integrity']['canonical_sha256'].upper()}"
    )


def required_n6_profile_confirmation(manifest: Mapping[str, Any]) -> str:
    profile = manifest["production_profile_binding"]
    return (
        f"{PROFILE_CONFIRMATION_PREFIX}"
        f"__PROFILE_CANONICAL_{profile['profile_canonical_sha256'].upper()}"
        f"__PROFILE_FILE_{profile['profile_file_sha256'].upper()}"
        f"__REVIEW_ARTIFACT_FILE_"
        f"{profile['profile_review_artifact_file_sha256'].upper()}"
        f"__REVIEWER_KEY_ID_{profile['reviewer_key_id']}"
        f"__USAGE_FILE_{profile['usage_evidence_file_sha256'].upper()}"
        f"__LIMIT_AUTHORITY_FILE_"
        f"{profile['limit_authority_file_sha256'].upper()}"
    )


def _required_tokens(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {
        "action_authorization": required_n6_action_authorization(manifest),
        "panel_plan_confirmation": required_n6_panel_plan_confirmation(manifest),
        "production_profile_confirmation": required_n6_profile_confirmation(manifest),
    }


def _token_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {
        name: _sha256(value.encode("utf-8"))
        for name, value in _required_tokens(manifest).items()
    }


def _runtime_schedule_decision(
    manifest: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
) -> dict[str, Any]:
    now = _timestamp(evaluated_at, label="N6 runtime schedule evaluated_at")
    schedule = manifest["operator_schedule"]
    profile = production.profile
    usage = profile["usage"]
    limits = profile["limits"]
    materialized_interval = _schedule_number(
        schedule["minimum_interval_seconds"],
        label="N6 materialized minimum interval",
        positive=True,
    )
    materialized_cooldown = _schedule_number(
        schedule["planned_cooldown_seconds"],
        label="N6 materialized planned cooldown",
        positive=False,
    )
    authority_interval = _schedule_number(
        limits["minimum_interval_seconds"],
        label="N6 limit-authority minimum interval",
        positive=False,
    )
    authority_cooldown = _schedule_number(
        limits["minimum_cooldown_seconds"],
        label="N6 limit-authority minimum cooldown",
        positive=False,
    )
    effective_interval = max(materialized_interval, authority_interval)
    effective_cooldown = max(materialized_cooldown, authority_cooldown)
    cumulative = usage["cumulative_visible_refresh_count"]
    session_count = usage["session_visible_refresh_count"]
    last_value = usage["last_visible_refresh_completed_at"]
    last = None if last_value is None else _timestamp(
        last_value, label="N6 last visible refresh completed_at"
    )
    elapsed = None if last is None else (now - last).total_seconds()
    interval_required = bool(cumulative > 0)
    cooldown_required = bool(cumulative > 0 and session_count == 0)
    blockers: list[str] = []
    if interval_required and (elapsed is None or elapsed < effective_interval):
        blockers.append("materialized_operator_interval_not_elapsed")
    if cooldown_required and (elapsed is None or elapsed < effective_cooldown):
        blockers.append("materialized_operator_cooldown_not_elapsed")
    if elapsed is not None and elapsed < 0:
        blockers.append("usage_last_visible_refresh_is_in_the_future")
    return {
        "evaluated_at": evaluated_at,
        "last_visible_refresh_completed_at": last_value,
        "elapsed_since_last_visible_refresh_seconds": elapsed,
        "interval_required": interval_required,
        "materialized_operator_minimum_interval_seconds": materialized_interval,
        "limit_authority_minimum_interval_seconds": authority_interval,
        "effective_minimum_interval_seconds": effective_interval,
        "cooldown_required": cooldown_required,
        "materialized_operator_planned_cooldown_seconds": materialized_cooldown,
        "limit_authority_minimum_cooldown_seconds": authority_cooldown,
        "effective_minimum_cooldown_seconds": effective_cooldown,
        "operator_schedule_classification": schedule["classification"],
        "operator_schedule_not_a_supplier_rating": schedule[
            "not_a_supplier_rating"
        ],
        "ready": not blockers,
        "blockers": blockers,
    }


def _authorization_binding(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "action_identity_sha256": manifest["legacy_formal_manifest"]["action"][
            "action_identity_sha256"
        ],
        "physical_context_canonical_sha256": manifest["physical_context"][
            "integrity"
        ]["canonical_sha256"],
        "production_profile_binding": _snapshot(
            manifest["production_profile_binding"]
        ),
        "required_token_sha256": _token_hashes(manifest),
        "maximum_frame_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def authorization_binding(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact external-authorization signer binding."""

    return _authorization_binding(manifest)


def _validate_authorization_envelope(
    manifest: Mapping[str, Any],
    envelope: Mapping[str, Any],
    *,
    evidence: ArtifactSnapshot,
    trusted_key: ArtifactSnapshot,
    evaluated_at: str,
) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping) or not isinstance(
        envelope.get("record"), Mapping
    ):
        raise N6PhysicalExecutionError(
            "N6 authenticated external authorization is missing"
        )
    legacy_manifest = manifest["legacy_formal_manifest"]
    try:
        authorization = legacy.validate_n6_external_authorization(
            envelope["record"], manifest=legacy_manifest
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N6 external authorization is invalid: {error}"
        ) from error
    if authorization["authorization_artifact_sha256"] != evidence.sha256:
        raise N6PhysicalExecutionError(
            "N6 authorization does not bind actual authorization evidence bytes"
        )
    root = validate_n6_authenticated_evidence(
        envelope,
        role=EXTERNAL_AUTHORIZATION_ROLE,
        expected_record=authorization,
        expected_binding=_authorization_binding(manifest),
        actual_evidence_bytes=evidence.payload,
        trusted_reviewer_key=trusted_key.payload,
    )
    if root["authentication"]["key_id"] != manifest[
        "production_profile_binding"
    ]["reviewer_key_id"]:
        raise N6PhysicalExecutionError(
            "N6 authorization key differs from the trusted production reviewer key"
        )
    now = _timestamp(evaluated_at, label="N6 authorization evaluated_at")
    issued = _timestamp(authorization["issued_at"], label="N6 authorization issued_at")
    expires = _timestamp(
        authorization["expires_at"], label="N6 authorization expires_at"
    )
    if not issued <= now < expires:
        raise N6PhysicalExecutionError(
            "N6 external authorization is not valid at actual live time"
        )
    return root


def _runtime_control_binding(
    manifest: Mapping[str, Any],
    authorization_envelope: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "action_identity_sha256": manifest["legacy_formal_manifest"]["action"][
            "action_identity_sha256"
        ],
        "authorization_envelope_canonical_sha256": _canonical_sha256(
            authorization_envelope
        ),
        "production_profile_binding": _production_binding(production),
        "required_token_sha256": _token_hashes(manifest),
        "operator_schedule_decision": _runtime_schedule_decision(
            manifest, production, evaluated_at=observed_at
        ),
        "runtime_observation_maximum_age_seconds": (
            MAX_LIVE_EVALUATION_AGE_SECONDS
        ),
        "claim_before_any_device_network": True,
        "maximum_frame_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def runtime_control_binding(
    manifest: Mapping[str, Any],
    authorization_envelope: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    observed_at: str,
) -> dict[str, Any]:
    """Return the exact live-observation signer/control binding."""

    return _runtime_control_binding(
        manifest,
        authorization_envelope,
        production,
        observed_at=observed_at,
    )


def _validate_runtime_observation_envelope(
    manifest: Mapping[str, Any],
    authorization_envelope: Mapping[str, Any],
    envelope: Mapping[str, Any],
    production: ValidatedProductionProfile,
    *,
    evidence: ArtifactSnapshot,
    trusted_key: ArtifactSnapshot,
    evaluated_at: str,
) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping) or not isinstance(
        envelope.get("record"), Mapping
    ):
        raise N6PhysicalExecutionError(
            "N6 authenticated runtime observation is missing"
        )
    legacy_manifest = manifest["legacy_formal_manifest"]
    try:
        observation = legacy.validate_n6_runtime_observation(
            envelope["record"], manifest=legacy_manifest
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N6 runtime observation is invalid: {error}"
        ) from error
    if observation["runtime_evidence_sha256"] != evidence.sha256:
        raise N6PhysicalExecutionError(
            "N6 runtime observation does not bind actual evidence bytes"
        )
    expected_binding = _runtime_control_binding(
        manifest,
        authorization_envelope,
        production,
        observed_at=observation["observed_at"],
    )
    if observation["operator_gate_artifact_sha256"] != _canonical_sha256(
        expected_binding
    ):
        raise N6PhysicalExecutionError(
            "N6 runtime observation does not bind exact tokens/schedule/profile"
        )
    root = validate_n6_authenticated_evidence(
        envelope,
        role=RUNTIME_OBSERVATION_ROLE,
        expected_record=observation,
        expected_binding=expected_binding,
        actual_evidence_bytes=evidence.payload,
        trusted_reviewer_key=trusted_key.payload,
    )
    if root["authentication"]["key_id"] != manifest[
        "production_profile_binding"
    ]["reviewer_key_id"]:
        raise N6PhysicalExecutionError(
            "N6 runtime observation key differs from trusted production reviewer key"
        )
    now = _timestamp(evaluated_at, label="N6 runtime observation evaluated_at")
    observed = _timestamp(
        observation["observed_at"], label="N6 runtime observation observed_at"
    )
    age = (now - observed).total_seconds()
    if age < 0:
        raise N6PhysicalExecutionError(
            "N6 runtime observation is in the future"
        )
    if age > MAX_LIVE_EVALUATION_AGE_SECONDS:
        raise N6PhysicalExecutionError(
            "N6 runtime observation is older than 300 seconds"
        )
    decision = expected_binding["operator_schedule_decision"]
    if decision["ready"] is not True or decision["blockers"]:
        raise N6PhysicalExecutionError(
            "N6 materialized runtime schedule is closed: "
            + ", ".join(decision["blockers"])
        )
    return root


def _runtime_snapshots(
    files: N6RuntimeEvidenceFiles,
) -> tuple[ArtifactSnapshot, ArtifactSnapshot, ArtifactSnapshot]:
    authorization = _read_bytes(
        files.authorization_evidence_file,
        label="N6 external authorization evidence",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    observation = _read_bytes(
        files.runtime_observation_evidence_file,
        label="N6 runtime observation evidence",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    key = _review_key(files.trusted_reviewer_key_file)
    return authorization, observation, key


def _live_age(then: str, now: str, *, label: str) -> float:
    age = (_timestamp(now, label=f"{label} current time") - _timestamp(
        then, label=f"{label} evaluated_at"
    )).total_seconds()
    if age < 0:
        raise N6PhysicalExecutionError(f"{label} evaluated_at is in the future")
    if age > MAX_LIVE_EVALUATION_AGE_SECONDS:
        raise N6PhysicalExecutionError(
            f"{label} is older than {MAX_LIVE_EVALUATION_AGE_SECONDS} seconds"
        )
    return age


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _physical_receipt(
    manifest: Mapping[str, Any],
    legacy_receipt: Mapping[str, Any],
    *,
    authorization_envelope: Mapping[str, Any],
    runtime_observation_envelope: Mapping[str, Any],
    initial_live_evaluated_at: str,
) -> dict[str, Any]:
    claimed_at = legacy_receipt["claimed_at"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHYSICAL_RECEIPT_KIND,
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "action_identity_sha256": manifest["legacy_formal_manifest"]["action"][
            "action_identity_sha256"
        ],
        "attempt_id": legacy_receipt["attempt_id"],
        "initial_live_evaluated_at": initial_live_evaluated_at,
        "claim_live_evaluated_at": claimed_at,
        "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATION_AGE_SECONDS,
        "production_profile_binding": _snapshot(
            manifest["production_profile_binding"]
        ),
        "required_token_sha256": _token_hashes(manifest),
        "authorization_envelope": _snapshot(authorization_envelope),
        "runtime_observation_envelope": _snapshot(runtime_observation_envelope),
        "runtime_control_binding": _snapshot(
            runtime_observation_envelope["binding"]
        ),
        "legacy_protocol_receipt": _snapshot(legacy_receipt),
        "classification": {
            "physical_production_chain": True,
            "claim_consumed": True,
            "frame_post_request_count": legacy_receipt[
                "frame_post_request_count"
            ],
            "retry_allowed": False,
            "recovery_allowed": False,
            "hardware_qualification_claimed": False,
        },
    }
    return _seal(payload)


def _receipt_path(path: Path, *, label: str) -> Path:
    if not isinstance(path, Path) or not path.name:
        raise N6PhysicalExecutionError(f"{label} must be an explicit file path")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N6PhysicalExecutionError(
            f"{label} parent directory is unavailable: {error}"
        ) from error
    if not parent.is_dir() or parent.is_symlink():
        raise N6PhysicalExecutionError(f"{label} parent must be a regular directory")
    return parent / path.name


def normalize_n6_physical_receipt_paths(
    paths: N6PhysicalReceiptPaths,
) -> N6PhysicalReceiptPaths:
    if not isinstance(paths, N6PhysicalReceiptPaths):
        raise N6PhysicalExecutionError("N6 physical receipt paths are required")
    normalized = N6PhysicalReceiptPaths(
        receipt_output=_receipt_path(paths.receipt_output, label="receipt output"),
        receipt_commit_output=_receipt_path(
            paths.receipt_commit_output, label="receipt durable commit output"
        ),
        incident_output=_receipt_path(
            paths.incident_output, label="post-claim incident output"
        ),
    )
    if len(set(normalized.__dict__.values())) != 3:
        raise N6PhysicalExecutionError(
            "receipt, durable commit, and incident outputs must be distinct"
        )
    return normalized


def _build_n6_physical_receipt_durable_commit(
    receipt: Mapping[str, Any],
    *,
    paths: N6PhysicalReceiptPaths,
    committed_at: str,
) -> dict[str, Any]:
    """Build metadata only after the concrete store durably wrote the receipt."""

    _check_integrity(receipt, label="N6 physical receipt for durable commit")
    if receipt.get("kind") != PHYSICAL_RECEIPT_KIND:
        raise N6PhysicalExecutionError(
            "durable commit requires an N6 physical production receipt"
        )
    normalized = normalize_n6_physical_receipt_paths(paths)
    committed = _timestamp(
        committed_at, label="N6 physical receipt durable committed_at"
    )
    completed = _timestamp(
        receipt["legacy_protocol_receipt"]["completed_at"],
        label="N6 physical receipt protocol completed_at",
    )
    if committed < completed:
        raise N6PhysicalExecutionError(
            "N6 physical receipt durable commit precedes protocol completion"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHYSICAL_RECEIPT_COMMIT_KIND,
        "physical_receipt_canonical_sha256": receipt["integrity"][
            "canonical_sha256"
        ],
        "physical_receipt_file_sha256": _sha256(canonical_json_bytes(receipt)),
        "receipt_output_path_sha256": _sha256(
            str(normalized.receipt_output).encode("utf-8")
        ),
        "receipt_commit_output_path_sha256": _sha256(
            str(normalized.receipt_commit_output).encode("utf-8")
        ),
        "postclaim_incident_output_path_sha256": _sha256(
            str(normalized.incident_output).encode("utf-8")
        ),
        "committed_at": committed_at,
        "exclusive_create": True,
        "file_fsynced": True,
        "parent_directory_fsynced": True,
        "sidecar_exclusive_create": True,
        "sidecar_file_fsynced": True,
        "sidecar_parent_directory_fsynced": True,
        "postclaim_incident_absent_at_commit": True,
        "classification": {
            "durable_receipt_committed": True,
            "claim_consumed": True,
            "retry_allowed": False,
            "recovery_allowed": False,
            "hardware_qualification_claimed": False,
        },
    }
    return _seal(payload)


def _validate_n6_physical_receipt_commit_mapping(
    commit: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any],
    paths: N6PhysicalReceiptPaths,
) -> Mapping[str, Any]:
    normalized = normalize_n6_physical_receipt_paths(paths)
    root = _exact(
        commit,
        label="N6 physical receipt durable commit",
        keys={
            "schema_version",
            "kind",
            "physical_receipt_canonical_sha256",
            "physical_receipt_file_sha256",
            "receipt_output_path_sha256",
            "receipt_commit_output_path_sha256",
            "postclaim_incident_output_path_sha256",
            "committed_at",
            "exclusive_create",
            "file_fsynced",
            "parent_directory_fsynced",
            "sidecar_exclusive_create",
            "sidecar_file_fsynced",
            "sidecar_parent_directory_fsynced",
            "postclaim_incident_absent_at_commit",
            "classification",
            "integrity",
        },
    )
    _check_integrity(receipt, label="N6 physical receipt for durable replay")
    expected_classification = {
        "durable_receipt_committed": True,
        "claim_consumed": True,
        "retry_allowed": False,
        "recovery_allowed": False,
        "hardware_qualification_claimed": False,
    }
    expected_path_hashes = {
        "receipt_output_path_sha256": _sha256(
            str(normalized.receipt_output).encode("utf-8")
        ),
        "receipt_commit_output_path_sha256": _sha256(
            str(normalized.receipt_commit_output).encode("utf-8")
        ),
        "postclaim_incident_output_path_sha256": _sha256(
            str(normalized.incident_output).encode("utf-8")
        ),
    }
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != PHYSICAL_RECEIPT_COMMIT_KIND
        or root["physical_receipt_canonical_sha256"]
        != receipt["integrity"]["canonical_sha256"]
        or root["physical_receipt_file_sha256"]
        != _sha256(canonical_json_bytes(receipt))
        or any(root[key] != value for key, value in expected_path_hashes.items())
        or root["exclusive_create"] is not True
        or root["file_fsynced"] is not True
        or root["parent_directory_fsynced"] is not True
        or root["sidecar_exclusive_create"] is not True
        or root["sidecar_file_fsynced"] is not True
        or root["sidecar_parent_directory_fsynced"] is not True
        or root["postclaim_incident_absent_at_commit"] is not True
        or root["classification"] != expected_classification
    ):
        raise N6PhysicalExecutionError(
            "N6 physical receipt durable commit binding changed"
        )
    completed = _timestamp(
        receipt["legacy_protocol_receipt"]["completed_at"],
        label="N6 physical receipt protocol completed_at",
    )
    if _timestamp(
        root["committed_at"], label="N6 physical durable committed_at"
    ) < completed:
        raise N6PhysicalExecutionError(
            "N6 physical receipt durable commit precedes protocol completion"
        )
    _check_integrity(root, label="N6 physical receipt durable commit")
    return root


def validate_n6_physical_receipt_durable_commit(
    commit: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any],
    paths: N6PhysicalReceiptPaths,
) -> Mapping[str, Any]:
    """Replay the sidecar against the three actual canonical filesystem paths."""

    normalized = normalize_n6_physical_receipt_paths(paths)
    root = _validate_n6_physical_receipt_commit_mapping(
        commit, receipt=receipt, paths=normalized
    )
    actual_receipt, receipt_file = _canonical_json_snapshot(
        normalized.receipt_output,
        label="durable N6 physical receipt",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    actual_commit, _commit_file = _canonical_json_snapshot(
        normalized.receipt_commit_output,
        label="durable N6 physical receipt commit",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if (
        actual_receipt != receipt
        or receipt_file.sha256 != root["physical_receipt_file_sha256"]
        or actual_commit != root
    ):
        raise N6PhysicalExecutionError(
            "actual durable N6 receipt/sidecar bytes differ from their binding"
        )
    if normalized.incident_output.exists() or normalized.incident_output.is_symlink():
        raise N6PhysicalExecutionError(
            "post-claim UNKNOWN incident exists; receipt cannot be finalized"
        )
    return root


class N6PhysicalReceiptStore:
    """Concrete O_EXCL+fsync receipt store required by production execution."""

    def __init__(
        self,
        manifest: Mapping[str, Any],
        *,
        paths: N6PhysicalReceiptPaths,
    ) -> None:
        _check_integrity(manifest, label="N6 physical receipt-store manifest")
        if manifest.get("kind") != PHYSICAL_MANIFEST_KIND:
            raise N6PhysicalExecutionError(
                "receipt store requires an N6 physical production manifest"
            )
        self._manifest_canonical_sha256 = manifest["integrity"]["canonical_sha256"]
        self._paths = normalize_n6_physical_receipt_paths(paths)
        for path in self._paths.__dict__.values():
            if path.exists() or path.is_symlink():
                raise N6PhysicalExecutionError(
                    "N6 physical receipt store outputs must not already exist"
                )
        self._lock = threading.Lock()
        self._committed = False
        self._incident: Optional[Mapping[str, Any]] = None

    @property
    def paths(self) -> N6PhysicalReceiptPaths:
        return self._paths

    @property
    def manifest_canonical_sha256(self) -> str:
        return self._manifest_canonical_sha256

    @property
    def incident(self) -> Optional[Mapping[str, Any]]:
        return None if self._incident is None else _snapshot(self._incident)

    def commit(
        self, receipt: Mapping[str, Any], *, committed_at: str
    ) -> Mapping[str, Any]:
        with self._lock:
            if self._committed or self._incident is not None:
                raise N6PhysicalExecutionError(
                    "N6 physical receipt store is permanently consumed"
                )
            if any(
                path.exists() or path.is_symlink()
                for path in self._paths.__dict__.values()
            ):
                raise N6PhysicalExecutionError(
                    "N6 physical receipt-store output appeared after preflight"
                )
            write_new_bytes_durable(
                self._paths.receipt_output, canonical_json_bytes(receipt)
            )
            commit = _build_n6_physical_receipt_durable_commit(
                receipt, paths=self._paths, committed_at=committed_at
            )
            write_new_bytes_durable(
                self._paths.receipt_commit_output, canonical_json_bytes(commit)
            )
            validated = validate_n6_physical_receipt_durable_commit(
                commit, receipt=receipt, paths=self._paths
            )
            self._committed = True
            return _snapshot(validated)

    def record_unknown(
        self,
        evidence: Mapping[str, Any],
        *,
        claim_path: Path,
        stage: str,
        detail: str,
    ) -> Mapping[str, Any]:
        """Durably record terminal UNKNOWN after a claim may have been consumed."""

        with self._lock:
            if self._incident is not None:
                return _snapshot(self._incident)
            _bounded_text(stage, label="post-claim incident stage", maximum=256)
            _bounded_text(detail, label="post-claim incident detail", maximum=2048)
            normalized_claim = _receipt_path(
                claim_path, label="workspace-global claim observation"
            )
            if normalized_claim.is_symlink():
                claim_observation = {
                    "status": "unsafe_non_regular",
                    "file_sha256": None,
                    "bytes": None,
                }
            elif not normalized_claim.exists():
                claim_observation = {
                    "status": "absent_outcome_unknown",
                    "file_sha256": None,
                    "bytes": None,
                }
            else:
                try:
                    claim_snapshot = read_local_regular_file(
                        normalized_claim,
                        label="post-claim incident claim observation",
                        maximum_bytes=MAX_EVIDENCE_BYTES,
                    )
                except ProductionProfileError:
                    claim_observation = {
                        "status": "unsafe_non_regular",
                        "file_sha256": None,
                        "bytes": None,
                    }
                else:
                    claim_observation = {
                        "status": "regular_file",
                        "file_sha256": claim_snapshot.sha256,
                        "bytes": len(claim_snapshot.payload),
                    }
            payload = {
                "schema_version": SCHEMA_VERSION,
                "kind": PHYSICAL_POSTCLAIM_INCIDENT_KIND,
                "state": ResultState.UNKNOWN_DO_NOT_RETRY.value,
                "recorded_at_from_actual_wall_clock": _utc_now_text(),
                "physical_manifest_canonical_sha256": self._manifest_canonical_sha256,
                "evidence_canonical_sha256": _canonical_sha256(evidence),
                "evidence": _snapshot(evidence),
                "failure_stage": stage,
                "failure_detail": detail,
                "workspace_global_claim_path_sha256": _sha256(
                    str(normalized_claim).encode("utf-8")
                ),
                "workspace_global_claim_observation": claim_observation,
                "receipt_output_path_sha256": _sha256(
                    str(self._paths.receipt_output).encode("utf-8")
                ),
                "receipt_commit_output_path_sha256": _sha256(
                    str(self._paths.receipt_commit_output).encode("utf-8")
                ),
                "incident_output_path_sha256": _sha256(
                    str(self._paths.incident_output).encode("utf-8")
                ),
                "classification": {
                    "claim_consumed": True,
                    "retry_allowed": False,
                    "recovery_allowed": False,
                    "second_post_allowed": False,
                    "hardware_qualification_claimed": False,
                },
            }
            incident = _seal(payload)
            write_new_bytes_durable(
                self._paths.incident_output, canonical_json_bytes(incident)
            )
            actual, _snapshot_file = _canonical_json_snapshot(
                self._paths.incident_output,
                label="durable N6 physical post-claim incident",
                maximum_bytes=MAX_EVIDENCE_BYTES,
            )
            if actual != incident:
                raise N6PhysicalExecutionError(
                    "durable N6 physical post-claim incident readback changed"
                )
            self._incident = _snapshot(incident)
            return _snapshot(incident)


def validate_n6_physical_postclaim_incident(
    incident: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    sources: N6PhysicalSources,
    production_files: N6ProductionProfileFiles,
    static_evidence_files: N6StaticEvidenceFiles,
    receipt_paths: N6PhysicalReceiptPaths,
    claim_store: legacy.AtomicN6ClaimStore,
) -> Mapping[str, Any]:
    """Deeply replay a terminal emergency UNKNOWN without promoting it."""

    normalized_paths = normalize_n6_physical_receipt_paths(receipt_paths)
    if type(claim_store) is not legacy.AtomicN6ClaimStore:
        raise N6PhysicalExecutionError(
            "incident replay requires the concrete atomic claim store"
        )
    manifest_root = validate_n6_physical_manifest(
        manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_evidence_files,
        evaluated_at=str(manifest.get("materialized_at")),
    )
    actual_incident, _incident_file = _canonical_json_snapshot(
        normalized_paths.incident_output,
        label="N6 physical post-claim UNKNOWN incident",
        maximum_bytes=MAX_EVIDENCE_BYTES,
    )
    if actual_incident != incident:
        raise N6PhysicalExecutionError(
            "N6 physical incident object differs from actual canonical file bytes"
        )
    root = _exact(
        incident,
        label="N6 physical post-claim UNKNOWN incident",
        keys={
            "schema_version",
            "kind",
            "state",
            "recorded_at_from_actual_wall_clock",
            "physical_manifest_canonical_sha256",
            "evidence_canonical_sha256",
            "evidence",
            "failure_stage",
            "failure_detail",
            "workspace_global_claim_path_sha256",
            "workspace_global_claim_observation",
            "receipt_output_path_sha256",
            "receipt_commit_output_path_sha256",
            "incident_output_path_sha256",
            "classification",
            "integrity",
        },
    )
    _timestamp(
        root["recorded_at_from_actual_wall_clock"],
        label="N6 physical incident recorded_at",
    )
    _bounded_text(root["failure_stage"], label="incident failure stage", maximum=256)
    _bounded_text(
        root["failure_detail"], label="incident failure detail", maximum=2048
    )
    if not isinstance(root["evidence"], Mapping):
        raise N6PhysicalExecutionError("N6 physical incident evidence must be an object")
    claim_path = _receipt_path(
        claim_store.claim_path(manifest_root["legacy_formal_manifest"]),
        label="incident workspace-global claim",
    )
    expected_incident_path = claim_path.parent / (
        f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json"
    )
    if normalized_paths.incident_output != expected_incident_path:
        raise N6PhysicalExecutionError(
            "N6 physical incident is not stored at the fixed per-claim path"
        )
    claim_observation = _exact(
        root["workspace_global_claim_observation"],
        label="incident workspace-global claim observation",
        keys={"status", "file_sha256", "bytes"},
    )
    status = claim_observation["status"]
    if status not in {
        "regular_file",
        "absent_outcome_unknown",
        "unsafe_non_regular",
    }:
        raise N6PhysicalExecutionError("N6 physical incident claim status changed")
    if status == "regular_file":
        try:
            claim_snapshot = read_local_regular_file(
                claim_path,
                label="incident workspace-global claim replay",
                maximum_bytes=MAX_EVIDENCE_BYTES,
            )
        except ProductionProfileError as error:
            raise N6PhysicalExecutionError(
                f"cannot replay incident claim file: {error}"
            ) from error
        if (
            claim_observation["file_sha256"] != claim_snapshot.sha256
            or claim_observation["bytes"] != len(claim_snapshot.payload)
        ):
            raise N6PhysicalExecutionError(
                "incident workspace-global claim bytes changed after recording"
            )
    elif (
        claim_observation["file_sha256"] is not None
        or claim_observation["bytes"] is not None
    ):
        raise N6PhysicalExecutionError(
            "non-regular incident claim observation cannot carry a file digest"
        )
    expected_classification = {
        "claim_consumed": True,
        "retry_allowed": False,
        "recovery_allowed": False,
        "second_post_allowed": False,
        "hardware_qualification_claimed": False,
    }
    expected_path_hashes = {
        "workspace_global_claim_path_sha256": _sha256(
            str(claim_path).encode("utf-8")
        ),
        "receipt_output_path_sha256": _sha256(
            str(normalized_paths.receipt_output).encode("utf-8")
        ),
        "receipt_commit_output_path_sha256": _sha256(
            str(normalized_paths.receipt_commit_output).encode("utf-8")
        ),
        "incident_output_path_sha256": _sha256(
            str(normalized_paths.incident_output).encode("utf-8")
        ),
    }
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != PHYSICAL_POSTCLAIM_INCIDENT_KIND
        or root["state"] != ResultState.UNKNOWN_DO_NOT_RETRY.value
        or root["physical_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["evidence_canonical_sha256"] != _canonical_sha256(root["evidence"])
        or any(root[key] != value for key, value in expected_path_hashes.items())
        or root["classification"] != expected_classification
    ):
        raise N6PhysicalExecutionError(
            "N6 physical post-claim incident binding changed"
        )
    _check_integrity(root, label="N6 physical post-claim UNKNOWN incident")
    return root


class N6PhysicalBrowserController:
    """Physical/production adapter for the real Chromium one-shot chain."""

    physical_production_mode = True

    def __init__(
        self,
        manifest: Mapping[str, Any],
        *,
        sources: N6PhysicalSources,
        production_files: N6ProductionProfileFiles,
        static_evidence_files: N6StaticEvidenceFiles,
        authorization_envelope: Mapping[str, Any],
        runtime_observation_envelope: Mapping[str, Any],
        runtime_evidence_files: N6RuntimeEvidenceFiles,
        claim_store: legacy.AtomicN6ClaimStore,
        protocol_driver: legacy.N6ProtocolDriver,
        attempt_id: str,
        post_claim_receipt_sink: N6PhysicalReceiptStore,
        utc_now: Callable[[], str] = _utc_now_text,
    ) -> None:
        if not callable(utc_now):
            raise N6PhysicalExecutionError("N6 physical utc_now must be callable")
        self._clock = utc_now
        if type(post_claim_receipt_sink) is not N6PhysicalReceiptStore:
            raise N6PhysicalExecutionError(
                "N6 physical execution requires the concrete durable receipt store"
            )
        if type(claim_store) is not legacy.AtomicN6ClaimStore:
            raise N6PhysicalExecutionError(
                "N6 physical execution requires the concrete atomic claim store"
            )
        if type(protocol_driver) is not legacy.N6HttpRefreshDriver:
            raise N6PhysicalExecutionError(
                "N6 physical execution requires the audited one-shot HTTP driver"
            )
        claim_path = claim_store.claim_path(manifest["legacy_formal_manifest"])
        expected_incident_path = claim_path.parent / (
            f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json"
        )
        if post_claim_receipt_sink.paths.incident_output != expected_incident_path:
            raise N6PhysicalExecutionError(
                "N6 physical incident output must be the fixed per-claim path"
            )
        if (
            post_claim_receipt_sink.manifest_canonical_sha256
            != manifest.get("integrity", {}).get("canonical_sha256")
        ):
            raise N6PhysicalExecutionError(
                "N6 physical receipt store is bound to a different manifest"
            )
        self._post_claim_receipt_sink = post_claim_receipt_sink
        self._receipt_sink_completed = False
        self._receipt_durable_commit: Optional[Mapping[str, Any]] = None
        self._sources = sources
        self._production_files = production_files
        self._static_evidence_files = static_evidence_files
        self._runtime_evidence_files = runtime_evidence_files
        self._claim_store = claim_store
        self._protocol_driver = protocol_driver
        self._attempt_id = attempt_id
        self.manifest = _snapshot(manifest)
        self.authorization_envelope = _snapshot(authorization_envelope)
        self.runtime_observation_envelope = _snapshot(
            runtime_observation_envelope
        )
        self._initial_live_evaluated_at = self._now()
        self._claim_clock_value: Optional[str] = None
        self._production = self._validate_live_inputs(
            self._initial_live_evaluated_at
        )
        authorization_record = self.authorization_envelope["record"]
        runtime_record = self.runtime_observation_envelope["record"]
        self._legacy = legacy.N6BrowserExecutionController(
            self.manifest["legacy_formal_manifest"],
            authorization=authorization_record,
            runtime_observation=runtime_record,
            claim_store=claim_store,
            protocol_driver=protocol_driver,
            attempt_id=attempt_id,
            utc_now=self._legacy_now,
        )
        self._tokens_armed = False
        self._execution_started = False
        self._receipt: Optional[Mapping[str, Any]] = None

    def _now(self) -> str:
        try:
            value = self._clock()
        except Exception as error:
            raise N6PhysicalExecutionError(
                "N6 physical live clock failed"
            ) from error
        _timestamp(value, label="N6 physical live clock")
        return value

    def _legacy_now(self) -> str:
        if self._claim_clock_value is not None:
            value = self._claim_clock_value
            self._claim_clock_value = None
            return value
        return self._now()

    def _commit_receipt_before_http_return(self) -> None:
        if self._receipt is None or self._receipt_sink_completed:
            return
        try:
            validate_n6_physical_receipt(
                self._receipt,
                manifest=self.manifest,
                sources=self._sources,
                production_files=self._production_files,
                static_evidence_files=self._static_evidence_files,
                runtime_evidence_files=self._runtime_evidence_files,
            )
            commit = self._post_claim_receipt_sink.commit(
                _snapshot(self._receipt), committed_at=self._now()
            )
            self._receipt_durable_commit = _snapshot(
                validate_n6_physical_receipt_durable_commit(
                    commit,
                    receipt=self._receipt,
                    paths=self._post_claim_receipt_sink.paths,
                )
            )
        except BaseException as error:
            try:
                self._post_claim_receipt_sink.record_unknown(
                    self._receipt,
                    claim_path=self._claim_store.claim_path(
                        self.manifest["legacy_formal_manifest"]
                    ),
                    stage="physical_receipt_validation_or_durable_commit",
                    detail=f"{type(error).__name__}: {error}",
                )
            except BaseException as incident_error:
                raise N6PhysicalPostClaimUnknown(
                    "N6 physical receipt and UNKNOWN incident durability are uncertain; do not retry",
                    receipt=self._receipt,
                ) from incident_error
            raise N6PhysicalPostClaimUnknown(
                "N6 physical receipt durability is UNKNOWN_DO_NOT_RETRY after claim",
                receipt=self._receipt,
            ) from error
        self._receipt_sink_completed = True

    def _postclaim_emergency(
        self,
        evidence: Mapping[str, Any],
        *,
        stage: str,
        error: BaseException,
    ) -> None:
        emergency = {
            "schema_version": SCHEMA_VERSION,
            "kind": "mf1750-n6-physical-emergency-postclaim-evidence",
            "physical_manifest_canonical_sha256": self.manifest["integrity"][
                "canonical_sha256"
            ],
            "attempt_id": self._attempt_id,
            "stage": stage,
            "source_evidence": _snapshot(evidence),
        }
        try:
            self._post_claim_receipt_sink.record_unknown(
                emergency,
                claim_path=self._claim_store.claim_path(
                    self.manifest["legacy_formal_manifest"]
                ),
                stage=stage,
                detail=f"{type(error).__name__}: {error}",
            )
        except BaseException as incident_error:
            raise N6PhysicalPostClaimUnknown(
                "N6 physical claim consumed and emergency incident durability is uncertain; do not retry",
                receipt=emergency,
            ) from incident_error
        raise N6PhysicalPostClaimUnknown(
            "N6 physical claim consumed; durable emergency UNKNOWN incident committed",
            receipt=emergency,
        ) from error

    def _validate_live_inputs(
        self, evaluated_at: str
    ) -> ValidatedProductionProfile:
        validate_n6_physical_manifest(
            self.manifest,
            sources=self._sources,
            production_files=self._production_files,
            static_evidence_files=self._static_evidence_files,
            evaluated_at=evaluated_at,
        )
        production = _load_production(
            self._production_files, evaluated_at=evaluated_at
        )
        _validate_production_for_context(
            production, self.manifest["physical_context"]
        )
        authorization_evidence, runtime_evidence, key = _runtime_snapshots(
            self._runtime_evidence_files
        )
        if key.sha256 != production.reviewer_key_id:
            raise N6PhysicalExecutionError(
                "N6 live reviewer key differs from production-profile trust anchor"
            )
        _validate_authorization_envelope(
            self.manifest,
            self.authorization_envelope,
            evidence=authorization_evidence,
            trusted_key=key,
            evaluated_at=evaluated_at,
        )
        _validate_runtime_observation_envelope(
            self.manifest,
            self.authorization_envelope,
            self.runtime_observation_envelope,
            production,
            evidence=runtime_evidence,
            trusted_key=key,
            evaluated_at=evaluated_at,
        )
        return production

    @property
    def receipt(self) -> Optional[Mapping[str, Any]]:
        return None if self._receipt is None else _snapshot(self._receipt)

    @property
    def receipt_durable_commit(self) -> Optional[Mapping[str, Any]]:
        return (
            None
            if self._receipt_durable_commit is None
            else _snapshot(self._receipt_durable_commit)
        )

    @property
    def receipt_paths(self) -> N6PhysicalReceiptPaths:
        return self._post_claim_receipt_sink.paths

    def bind_server_origin(self, origin: str) -> None:
        self._legacy.bind_server_origin(origin)

    def set_runtime_observation(self, observation: Mapping[str, Any]) -> None:
        del observation
        raise N6PhysicalExecutionError(
            "N6 physical runtime observation is authenticated and immutable"
        )

    def record_page_load(self) -> None:
        self._legacy.record_page_load()

    def record_authenticated_read(self) -> None:
        self._legacy.record_authenticated_read()

    def observe_artifact(self, artifact: ApplicationArtifact) -> bool:
        return self._legacy.observe_artifact(artifact)

    def invalidate_artifact(self) -> None:
        self._legacy.invalidate_artifact()

    def record_preview_fetch(self, report_sha256: str, stage: str) -> None:
        self._legacy.record_preview_fetch(report_sha256, stage)

    def allow_connection(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        return self._legacy.allow_connection(
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )

    def local_preflight(
        self,
        mappings: Sequence[ControllerMapping],
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        return self._legacy.local_preflight(
            mappings,
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )

    def arm(
        self,
        confirmation: str,
        *,
        panel_plan_confirmation: str,
        profile_confirmation: str,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        required = _required_tokens(self.manifest)
        supplied = {
            "action_authorization": confirmation,
            "panel_plan_confirmation": panel_plan_confirmation,
            "production_profile_confirmation": profile_confirmation,
        }
        if supplied != required:
            raise N6PhysicalExecutionError(
                "N6 physical arm requires all three exact action/panel/profile tokens"
            )
        result = self._legacy.arm(
            legacy.N6_ARM_CONFIRMATION,
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )
        self._tokens_armed = True
        return {
            **result,
            "physical_production_mode": True,
            "three_exact_tokens_verified": True,
            "required_token_sha256": _token_hashes(self.manifest),
        }

    def enqueue(
        self,
        mappings: Sequence[ControllerMapping],
        *,
        token_validated: bool,
        same_origin_validated: bool,
    ) -> Mapping[str, Any]:
        """Revalidate with the actual clock, then claim and perform <=1 POST."""

        if self._execution_started:
            raise N6PhysicalExecutionError(
                "N6 physical duplicate submission is permanently locked"
            )
        if not self._tokens_armed:
            raise N6PhysicalExecutionError(
                "N6 physical enqueue requires the three exact arm tokens"
            )
        live_now = self._now()
        _live_age(
            self._initial_live_evaluated_at,
            live_now,
            label="N6 physical live validation",
        )
        # Every check above and below occurs before the private kernel creates
        # the claim or calls the injected protocol driver.
        self._production = self._validate_live_inputs(live_now)
        current_decision = _runtime_schedule_decision(
            self.manifest,
            self._production,
            evaluated_at=live_now,
        )
        if current_decision["ready"] is not True or current_decision["blockers"]:
            raise N6PhysicalExecutionError(
                "N6 physical schedule is closed before claim: "
                + ", ".join(current_decision["blockers"])
            )
        self._execution_started = True
        self._tokens_armed = False
        self._claim_clock_value = live_now
        try:
            result = self._legacy._enqueue_legacy_test_only(  # noqa: SLF001
                mappings,
                token_validated=token_validated,
                same_origin_validated=same_origin_validated,
            )
        except BaseException as error:
            if (
                isinstance(error, legacy.N6ClaimConsumed)
                and self._protocol_driver.total_request_count == 0
                and self._protocol_driver.frame_post_request_count == 0
                and self._legacy.receipt is None
            ):
                # The permanent claim predates this invocation; this attempt
                # performed no device I/O and must not manufacture a new
                # post-claim incident for the already-consumed action.
                raise
            legacy_receipt = (
                error.receipt
                if isinstance(error, legacy.N6PostClaimUnknown)
                else self._legacy.receipt
            )
            try:
                claim_path = self._claim_store.claim_path(
                    self.manifest["legacy_formal_manifest"]
                )
                claim_may_be_consumed = claim_path.exists() or claim_path.is_symlink()
            except BaseException:
                claim_may_be_consumed = True
            if legacy_receipt is None and not claim_may_be_consumed:
                raise
            if legacy_receipt is None:
                self._postclaim_emergency(
                    {
                        "manifest_canonical_sha256": self.manifest["integrity"][
                            "canonical_sha256"
                        ],
                        "attempt_id": self._attempt_id,
                        "claim_file_observed": claim_may_be_consumed,
                    },
                    stage="claim_or_protocol_without_legacy_receipt",
                    error=error,
                )
            try:
                physical_receipt = _physical_receipt(
                    self.manifest,
                    legacy_receipt,
                    authorization_envelope=self.authorization_envelope,
                    runtime_observation_envelope=self.runtime_observation_envelope,
                    initial_live_evaluated_at=self._initial_live_evaluated_at,
                )
            except BaseException as conversion_error:
                self._postclaim_emergency(
                    legacy_receipt,
                    stage="physical_receipt_construction",
                    error=conversion_error,
                )
            self._receipt = physical_receipt
            self._commit_receipt_before_http_return()
            raise N6PhysicalPostClaimUnknown(
                "N6 physical action is UNKNOWN_DO_NOT_RETRY after permanent claim",
                receipt=physical_receipt,
            ) from error
        legacy_receipt = self._legacy.receipt
        if legacy_receipt is None:  # pragma: no cover - compatibility kernel invariant
            self._postclaim_emergency(
                {
                    "manifest_canonical_sha256": self.manifest["integrity"][
                        "canonical_sha256"
                    ],
                    "attempt_id": self._attempt_id,
                    "compatibility_kernel_returned": True,
                },
                stage="compatibility_kernel_missing_success_receipt",
                error=N6PhysicalExecutionError(
                    "N6 compatibility kernel returned without a receipt"
                ),
            )
        try:
            self._receipt = _physical_receipt(
                self.manifest,
                legacy_receipt,
                authorization_envelope=self.authorization_envelope,
                runtime_observation_envelope=self.runtime_observation_envelope,
                initial_live_evaluated_at=self._initial_live_evaluated_at,
            )
        except BaseException as conversion_error:
            self._postclaim_emergency(
                legacy_receipt,
                stage="physical_success_receipt_construction",
                error=conversion_error,
            )
        self._commit_receipt_before_http_return()
        return {
            **result,
            "physical_production_mode": True,
            "physical_receipt_canonical_sha256": self._receipt["integrity"][
                "canonical_sha256"
            ],
            "hardware_qualification_claimed": False,
        }

    def poll_job(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        return self._legacy.poll_job(
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )

    def diagnostic_report(
        self, *, token_validated: bool, same_origin_validated: bool
    ) -> Mapping[str, Any]:
        return self._legacy.diagnostic_report(
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )

    def status_overlay(self, base_status: Mapping[str, Any]) -> dict[str, Any]:
        status = self._legacy.status_overlay(base_status)
        status.update(
            {
                "n6_formal_mode": False,
                "n6_physical_production_mode": True,
                "three_exact_tokens_required": True,
                "hardware_qualification_claimed": False,
            }
        )
        return status

    @staticmethod
    def forbidden_recovery() -> Mapping[str, Any]:
        raise N6PhysicalExecutionError(
            "N6 physical action has no cancel, retry, or recovery path"
        )


def validate_n6_physical_receipt(
    receipt: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    sources: N6PhysicalSources,
    production_files: N6ProductionProfileFiles,
    static_evidence_files: N6StaticEvidenceFiles,
    runtime_evidence_files: N6RuntimeEvidenceFiles,
    evaluated_at: Optional[str] = None,
) -> Mapping[str, Any]:
    """Deep-validate receipt, claim, tokens, HMAC evidence, and original files."""

    root = _exact(
        receipt,
        label="N6 physical production receipt",
        keys={
            "schema_version",
            "kind",
            "physical_manifest_canonical_sha256",
            "action_identity_sha256",
            "attempt_id",
            "initial_live_evaluated_at",
            "claim_live_evaluated_at",
            "maximum_live_evaluation_age_seconds",
            "production_profile_binding",
            "required_token_sha256",
            "authorization_envelope",
            "runtime_observation_envelope",
            "runtime_control_binding",
            "legacy_protocol_receipt",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PHYSICAL_RECEIPT_KIND:
        raise N6PhysicalExecutionError(
            "N6 physical production receipt kind/version is invalid"
        )
    claimed_at = root["legacy_protocol_receipt"].get("claimed_at")
    _timestamp(claimed_at, label="N6 physical receipt claimed_at")
    manifest_root = validate_n6_physical_manifest(
        manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_evidence_files,
        evaluated_at=claimed_at,
    )
    production = _load_production(production_files, evaluated_at=claimed_at)
    authorization_evidence, runtime_evidence, key = _runtime_snapshots(
        runtime_evidence_files
    )
    authorization = _validate_authorization_envelope(
        manifest_root,
        root["authorization_envelope"],
        evidence=authorization_evidence,
        trusted_key=key,
        evaluated_at=claimed_at,
    )
    runtime = _validate_runtime_observation_envelope(
        manifest_root,
        root["authorization_envelope"],
        root["runtime_observation_envelope"],
        production,
        evidence=runtime_evidence,
        trusted_key=key,
        evaluated_at=claimed_at,
    )
    legacy_manifest = manifest_root["legacy_formal_manifest"]
    try:
        legacy_receipt = legacy.validate_n6_protocol_receipt(
            root["legacy_protocol_receipt"], manifest=legacy_manifest
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"embedded N6 protocol receipt is invalid: {error}"
        ) from error
    if (
        legacy_receipt["authorization"] != authorization["record"]
        or legacy_receipt["runtime_observation"] != runtime["record"]
    ):
        raise N6PhysicalExecutionError(
            "N6 physical receipt HMAC envelopes differ from claimed legacy evidence"
        )
    expected_classification = {
        "physical_production_chain": True,
        "claim_consumed": True,
        "frame_post_request_count": legacy_receipt["frame_post_request_count"],
        "retry_allowed": False,
        "recovery_allowed": False,
        "hardware_qualification_claimed": False,
    }
    if (
        root["physical_manifest_canonical_sha256"]
        != manifest_root["integrity"]["canonical_sha256"]
        or root["action_identity_sha256"]
        != legacy_manifest["action"]["action_identity_sha256"]
        or root["attempt_id"] != legacy_receipt["attempt_id"]
        or root["claim_live_evaluated_at"] != legacy_receipt["claimed_at"]
        or root["maximum_live_evaluation_age_seconds"]
        != MAX_LIVE_EVALUATION_AGE_SECONDS
        or root["production_profile_binding"] != _production_binding(production)
        or root["required_token_sha256"] != _token_hashes(manifest_root)
        or root["runtime_control_binding"] != runtime["binding"]
        or root["classification"] != expected_classification
    ):
        raise N6PhysicalExecutionError(
            "N6 physical receipt production/token/claim binding changed"
        )
    _live_age(
        root["initial_live_evaluated_at"],
        root["claim_live_evaluated_at"],
        label="N6 receipt preclaim validation",
    )
    if evaluated_at is not None:
        _live_age(
            root["claim_live_evaluated_at"],
            evaluated_at,
            label="N6 receipt live validation",
        )
    _check_integrity(root, label="N6 physical production receipt")
    return root


def _wrap_finalized(
    manifest: Mapping[str, Any],
    physical_receipt: Mapping[str, Any],
    receipt_durable_commit: Mapping[str, Any],
    legacy_finalized_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    legacy_result = legacy_finalized_bundle["result"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHYSICAL_FINALIZED_KIND,
        "physical_manifest_canonical_sha256": manifest["integrity"][
            "canonical_sha256"
        ],
        "physical_receipt_canonical_sha256": physical_receipt["integrity"][
            "canonical_sha256"
        ],
        "action_identity_sha256": manifest["legacy_formal_manifest"]["action"][
            "action_identity_sha256"
        ],
        "attempt_id": physical_receipt["attempt_id"],
        "required_token_sha256": _token_hashes(manifest),
        "production_profile_binding": _snapshot(
            manifest["production_profile_binding"]
        ),
        "physical_receipt": _snapshot(physical_receipt),
        "receipt_durable_commit": _snapshot(receipt_durable_commit),
        "legacy_finalized_bundle": _snapshot(legacy_finalized_bundle),
        "result": _snapshot(legacy_result),
        "classification": {
            "terminal": True,
            "physical_production_chain": True,
            "retry_allowed": False,
            "recovery_allowed": False,
            "hardware_observation_recorded": (
                legacy_finalized_bundle["manual_observation"] is not None
            ),
            "hardware_qualification_claimed": False,
        },
    }
    return _seal(payload)


def validate_n6_physical_claim_file(
    manifest: Mapping[str, Any],
    physical_receipt: Mapping[str, Any],
    *,
    claim_store: legacy.AtomicN6ClaimStore,
) -> Path:
    """Replay the standalone O_EXCL claim bytes from the configured workspace."""

    if type(claim_store) is not legacy.AtomicN6ClaimStore:
        raise N6PhysicalExecutionError(
            "N6 physical claim replay requires the concrete atomic claim store"
        )
    _check_integrity(physical_receipt, label="N6 physical receipt claim replay")
    legacy_receipt = physical_receipt["legacy_protocol_receipt"]
    path = claim_store.claim_path(manifest["legacy_formal_manifest"])
    try:
        snapshot = read_local_regular_file(
            path,
            label="N6 physical workspace-global claim",
            maximum_bytes=MAX_EVIDENCE_BYTES,
        )
    except ProductionProfileError as error:
        raise N6PhysicalExecutionError(
            f"cannot replay N6 physical workspace-global claim: {error}"
        ) from error
    expected = canonical_json_bytes(legacy_receipt["claim"]) + b"\n"
    if (
        snapshot.payload != expected
        or snapshot.sha256 != legacy_receipt["claim_file_sha256"]
    ):
        raise N6PhysicalExecutionError(
            "N6 physical workspace-global claim bytes differ from receipt"
        )
    return path


def finalize_n6_physical_manual_observation(
    manifest: Mapping[str, Any],
    physical_receipt: Mapping[str, Any],
    manual_observation: Mapping[str, Any],
    *,
    receipt_durable_commit: Mapping[str, Any],
    receipt_paths: N6PhysicalReceiptPaths,
    claim_store: legacy.AtomicN6ClaimStore,
    finalized_at: str,
) -> dict[str, Any]:
    """Wrap the retained manual PASS/FAIL finalizer without qualification uplift."""

    commit = validate_n6_physical_receipt_durable_commit(
        receipt_durable_commit,
        receipt=physical_receipt,
        paths=receipt_paths,
    )
    validate_n6_physical_claim_file(
        manifest, physical_receipt, claim_store=claim_store
    )
    try:
        legacy_bundle = legacy.finalize_n6_manual_observation(
            manifest["legacy_formal_manifest"],
            physical_receipt["legacy_protocol_receipt"],
            manual_observation,
            finalized_at=finalized_at,
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N6 physical manual finalization failed: {error}"
        ) from error
    return _wrap_finalized(manifest, physical_receipt, commit, legacy_bundle)


def finalize_n6_physical_unknown(
    manifest: Mapping[str, Any],
    physical_receipt: Mapping[str, Any],
    *,
    receipt_durable_commit: Mapping[str, Any],
    receipt_paths: N6PhysicalReceiptPaths,
    claim_store: legacy.AtomicN6ClaimStore,
    finalized_at: str,
) -> dict[str, Any]:
    """Wrap a terminal UNKNOWN receipt; no retry/recovery is introduced."""

    commit = validate_n6_physical_receipt_durable_commit(
        receipt_durable_commit,
        receipt=physical_receipt,
        paths=receipt_paths,
    )
    validate_n6_physical_claim_file(
        manifest, physical_receipt, claim_store=claim_store
    )
    try:
        legacy_bundle = legacy.finalize_n6_unknown_receipt(
            manifest["legacy_formal_manifest"],
            physical_receipt["legacy_protocol_receipt"],
            finalized_at=finalized_at,
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"N6 physical UNKNOWN finalization failed: {error}"
        ) from error
    return _wrap_finalized(manifest, physical_receipt, commit, legacy_bundle)


def validate_n6_physical_finalized_bundle(
    bundle: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    sources: N6PhysicalSources,
    production_files: N6ProductionProfileFiles,
    static_evidence_files: N6StaticEvidenceFiles,
    runtime_evidence_files: N6RuntimeEvidenceFiles,
    receipt_paths: N6PhysicalReceiptPaths,
    claim_store: legacy.AtomicN6ClaimStore,
) -> Mapping[str, Any]:
    """Public deep final validator requiring every original trusted input."""

    root = _exact(
        bundle,
        label="N6 physical finalized bundle",
        keys={
            "schema_version",
            "kind",
            "physical_manifest_canonical_sha256",
            "physical_receipt_canonical_sha256",
            "action_identity_sha256",
            "attempt_id",
            "required_token_sha256",
            "production_profile_binding",
            "physical_receipt",
            "receipt_durable_commit",
            "legacy_finalized_bundle",
            "result",
            "classification",
            "integrity",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != PHYSICAL_FINALIZED_KIND:
        raise N6PhysicalExecutionError(
            "N6 physical finalized bundle kind/version is invalid"
        )
    receipt = validate_n6_physical_receipt(
        root["physical_receipt"],
        manifest=manifest,
        sources=sources,
        production_files=production_files,
        static_evidence_files=static_evidence_files,
        runtime_evidence_files=runtime_evidence_files,
    )
    durable_commit = validate_n6_physical_receipt_durable_commit(
        root["receipt_durable_commit"],
        receipt=receipt,
        paths=receipt_paths,
    )
    validate_n6_physical_claim_file(
        manifest, receipt, claim_store=claim_store
    )
    legacy_manifest = manifest["legacy_formal_manifest"]
    try:
        legacy_bundle = legacy.validate_n6_finalized_bundle(
            root["legacy_finalized_bundle"], manifest=legacy_manifest
        )
    except legacy.N6VisibleExecutionError as error:
        raise N6PhysicalExecutionError(
            f"embedded N6 finalized bundle is invalid: {error}"
        ) from error
    expected = _wrap_finalized(
        manifest, receipt, durable_commit, legacy_bundle
    )
    if root != expected:
        raise N6PhysicalExecutionError(
            "N6 physical finalized bundle differs from deep reconstruction"
        )
    if root["result"] != legacy_bundle["result"]:
        raise N6PhysicalExecutionError("N6 physical final result binding changed")
    _check_integrity(root, label="N6 physical finalized bundle")
    return root


__all__ = [
    "ACTION_AUTHORIZATION_PREFIX",
    "ACTION_AUTHORIZATION_SUFFIX",
    "AUTHENTICATED_EVIDENCE_KIND",
    "EXTERNAL_AUTHORIZATION_ROLE",
    "EXPECTED_RC2G_BUILD_TAG",
    "EXPECTED_RC2G_DRIVER_API",
    "FORMAL_REVIEW_ROLE",
    "MAX_LIVE_EVALUATION_AGE_SECONDS",
    "N6PhysicalBrowserController",
    "N6PhysicalExecutionError",
    "N6N5PhysicalPaletteEvidence",
    "N6PhysicalPostClaimUnknown",
    "N6PhysicalReceiptPaths",
    "N6PhysicalReceiptStore",
    "N6PhysicalSources",
    "N6ProductionProfileFiles",
    "N6RuntimeEvidenceFiles",
    "N6StaticEvidenceFiles",
    "PANEL_PLAN_CONFIRMATION_PREFIX",
    "PHYSICAL_CONTEXT_KIND",
    "PHYSICAL_FINALIZED_KIND",
    "PHYSICAL_MANIFEST_KIND",
    "PHYSICAL_RECEIPT_KIND",
    "PHYSICAL_RECEIPT_COMMIT_KIND",
    "PHYSICAL_POSTCLAIM_INCIDENT_KIND",
    "PROFILE_CONFIRMATION_PREFIX",
    "RUNTIME_OBSERVATION_ROLE",
    "RUNTIME_REVIEW_ROLE",
    "authorization_binding",
    "compile_n6_physical_context",
    "finalize_n6_physical_manual_observation",
    "finalize_n6_physical_unknown",
    "materialize_n6_physical_manifest",
    "normalize_n6_physical_receipt_paths",
    "required_n6_action_authorization",
    "required_n6_panel_plan_confirmation",
    "required_n6_profile_confirmation",
    "runtime_control_binding",
    "sign_n6_authenticated_evidence",
    "static_review_binding",
    "validate_n6_authenticated_evidence",
    "validate_n6_physical_context",
    "validate_n6_physical_claim_file",
    "validate_n6_physical_finalized_bundle",
    "validate_n6_physical_manifest",
    "validate_n6_physical_postclaim_incident",
    "validate_n6_physical_receipt",
    "validate_n6_physical_receipt_durable_commit",
]
