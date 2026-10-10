"""Offline seed-and-perturbation planning for the MF-1750 panel.

This module deliberately stops before waveform materialisation.  It records
known endpoint seeds and can enumerate bounded *metadata* candidates only when
an independently reviewed, safe time/frame axis is supplied.  The default
production path has no such axis and therefore returns a stable fail-closed
decision.  No payload bytes, firmware include, transport callback, or device
operation can be produced here.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
KIND = "mf1750-seed-perturbation-offline-audit"
DECISION_BLOCKED = "OFFLINE_BLOCKED_NO_SAFE_PERTURBATION_ABI"
DECISION_METADATA_ONLY = "OFFLINE_METADATA_CANDIDATES_ONLY"
CLASSIFICATION = "FAIL_CLOSED_NO_WAVEFORM_MATERIALIZATION"

PANEL_MODEL = "MF-17506-M009F-T"
CONTROLLER_MODEL = "SPD1657B/E2802"
PROFILE_ID = "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535"
SOURCE_ACTION_ID = "7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526"
SOURCE_ACTION_SHA256 = "dffb561044aa8103048fe535cdf10e1deebabd94e884740968f14083a3c80f72"
SOURCE_CANONICAL_SHA256 = "d759ac0b16d4326015ec189f55adbcddd74177add302f3ac65bf60f254f9aa60"
SOURCE_FIRMWARE_SHA256 = "f5c83b357c1db3dd065669e36d0ac9a09edfe47c720fadecad98c196a81652ed"
SOURCE_ACTION_PATH = (
    ".test-output/hardware/MF1750_P1_COMPLETE_ACTIVE_ENDPOINT_20260901_V1/"
    "action-01-active-complete-position-balanced-4x8-endpoint-atlas.json"
)
HOLD_AUDIT_PATH = "docs/MF1750_SPD1657_HOLD_CODE_FEASIBILITY_AUDIT_2026-09-02.json"
HOLD_AUDIT_FILE_SHA256 = "6912060a7efa8ad0d530cdc7fbf5a27a35229139ea6e56aaed5fb6255f03790b"
HOLD_AUDIT_CANONICAL_SHA256 = "4753edff82b68b750c1f9d68b98a7e8765496269fc3b041f89ca12e67a69cb12"

SEED_CODES = (0, 1, 6)
FIRST_ROUND_VALUE_COUNT = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

_SEED_KEYS = frozenset(
    {
        "controller",
        "profile_id",
        "transport_code",
        "source_action_id",
        "source_action_sha256",
        "source_canonical_sha256",
        "source_firmware_sha256",
        "candidate_only",
        "qualified",
        "payload_bytes_emitted",
        "seed_identity_sha256",
    }
)
_AXIS_KEYS = frozenset(
    {
        "axis_id",
        "axis_kind",
        "proof_artifact_sha256",
        "semantics_proven",
        "safe_for_live",
        "unit",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "controller",
        "profile_id",
        "seed_code",
        "seed_identity_sha256",
        "perturbation_vector",
        "order",
        "position_replicate_ids",
        "position_replicate_count",
        "payload_bytes_emitted",
        "firmware_include_generated",
        "live_eligible",
    }
)
_VECTOR_KEYS = frozenset({"axis_id", "axis_kind", "value", "unit"})
_POSITION_REPLICATE_IDS = ("P0", "P1", "P2", "P3")
_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "created_at",
        "panel",
        "scope",
        "decision",
        "classification",
        "evidence_chain",
        "seed_inventory",
        "perturbation_axis",
        "requested_axis_values",
        "candidate_count",
        "candidate_metadata",
        "search_contract",
        "blocker_codes",
        "next_action",
        "output_contract",
        "io_proof",
        "artifact_status",
        "safety",
        "integrity",
    }
)
_PANEL_KEYS = frozenset({"model", "controller_model", "controller_count", "controller_local_analysis"})
_SEARCH_KEYS = frozenset(
    {
        "first_round_m",
        "seed_codes",
        "values_per_axis",
        "candidates_per_controller",
        "position_replicates_per_candidate",
        "position_replicate_ids",
        "single_pixel_no_dither",
        "complete_busy_required",
        "one_driver_one_visible_refresh",
        "same_payload_required_for_both_controllers",
        "retry_allowed",
        "recovery_allowed",
        "autochain_allowed",
    }
)
_OUTPUT_KEYS = frozenset(
    {
        "candidate_payload_generated",
        "candidate_payload_bytes",
        "firmware_include_generated",
        "live_runner_created",
        "hardware_execution_eligible",
        "visible_refresh_authorized",
    }
)
_IO_PROOF_KEYS = frozenset({"device_io", "network_io", "serial_or_com_io", "visible_refreshes"})
_SAFETY_KEYS = frozenset(
    {
        "offline_only",
        "hardware_accessed",
        "serial_or_com_accessed",
        "device_network_accessed",
        "relay_or_power_accessed",
        "firmware_or_flash_written",
        "display_refresh_attempted",
        "raw_waveform_bytes_emitted",
        "runtime_payload_generated",
    }
)
_EVIDENCE_CHAIN_KEYS = frozenset({"source_action", "hold_feasibility_audit"})
_EVIDENCE_ITEM_KEYS = frozenset(
    {"path", "file_sha256", "canonical_sha256", "identity_pinned", "decision"}
)
_ARTIFACT_STATUS_KEYS = frozenset(
    {
        "schema",
        "manifest",
        "audit",
        "runner",
        "pack",
        "nvs_ordinal",
        "exact_identity_binding",
        "bin_elf_frame_dtm_contract_descriptor_action",
        "live_firmware",
    }
)
_ARTIFACT_STATUS_VALUES = {
    "schema": "GENERATED",
    "manifest": "GENERATED_METADATA_ONLY",
    "audit": "GENERATED",
    "runner": "NOT_GENERATED_BLOCKED",
    "pack": "NOT_GENERATED_BLOCKED",
    "nvs_ordinal": "NOT_GENERATED_BLOCKED",
    "exact_identity_binding": "NOT_GENERATED_BLOCKED",
    "bin_elf_frame_dtm_contract_descriptor_action": "NOT_GENERATED_BLOCKED",
    "live_firmware": "NOT_GENERATED_BLOCKED",
}

# There is intentionally no registered positive proof in this checkout.  A
# caller cannot self-assert ``semantics_proven``/``safe_for_live`` with an
# arbitrary hash and thereby unlock even metadata enumeration.  Populating
# this set requires a separately reviewed, identity-pinned artifact and a new
# audit/test revision.
_REVIEWED_SAFE_AXIS_PROOF_SHA256 = frozenset()


class SeedPerturbationError(ValueError):
    """Raised when an offline seed/axis declaration is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SeedPerturbationError("value is not canonical JSON") from error


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SeedPerturbationError(message)


def _hash(value: Any, *, label: str) -> str:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None,
             f"{label} must be a lowercase SHA-256")
    return value


def _timestamp(value: Any, *, label: str) -> str:
    _require(isinstance(value, str) and _RFC3339.fullmatch(value) is not None,
             f"{label} must be RFC3339")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SeedPerturbationError(f"{label} is not a valid timestamp") from error
    return value


def _axis_is_proven(axis: Mapping[str, Any]) -> bool:
    return (
        axis["semantics_proven"] is True
        and axis["safe_for_live"] is True
        and axis["proof_artifact_sha256"] in _REVIEWED_SAFE_AXIS_PROOF_SHA256
    )


def _seed_identity(seed: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(seed))


def build_seed_inventory() -> list[dict[str, Any]]:
    """Return the six controller-local candidate seeds, without payload bytes."""

    seeds: list[dict[str, Any]] = []
    for controller in ("CS1", "CS2"):
        for code in SEED_CODES:
            seed = {
                "controller": controller,
                "profile_id": PROFILE_ID,
                "transport_code": code,
                "source_action_id": SOURCE_ACTION_ID,
                "source_action_sha256": SOURCE_ACTION_SHA256,
                "source_canonical_sha256": SOURCE_CANONICAL_SHA256,
                "source_firmware_sha256": SOURCE_FIRMWARE_SHA256,
                "candidate_only": True,
                "qualified": False,
                "payload_bytes_emitted": False,
            }
            seed["seed_identity_sha256"] = _seed_identity(seed)
            seeds.append(seed)
    return seeds


def validate_seed_inventory(seeds: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate an exact metadata-only seed inventory."""

    _require(isinstance(seeds, (list, tuple)), "seed inventory must be an array")
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(seeds):
        _require(isinstance(raw, Mapping), f"seed {index} must be an object")
        _require(set(raw) == _SEED_KEYS, f"seed {index} keys differ")
        _require(isinstance(raw["controller"], str), f"seed {index} controller differs")
        _require(raw["controller"] in {"CS1", "CS2"}, f"seed {index} controller differs")
        _require(isinstance(raw["profile_id"], str) and raw["profile_id"] == PROFILE_ID,
                 f"seed {index} profile differs")
        _require(type(raw["transport_code"]) is int and 0 <= raw["transport_code"] <= 7,
                 f"seed {index} code differs")
        _require(raw["transport_code"] in SEED_CODES, f"seed {index} is outside reviewed seed set")
        _require(raw["source_action_id"] == SOURCE_ACTION_ID, f"seed {index} action differs")
        _hash(raw["source_action_sha256"], label=f"seed {index} source action")
        _hash(raw["source_canonical_sha256"], label=f"seed {index} source canonical")
        _hash(raw["source_firmware_sha256"], label=f"seed {index} firmware")
        _require(raw["candidate_only"] is True, f"seed {index} must remain candidate-only")
        _require(raw["qualified"] is False, f"seed {index} cannot be qualified offline")
        _require(raw["payload_bytes_emitted"] is False, f"seed {index} emitted payload bytes")
        unsigned = {key: raw[key] for key in _SEED_KEYS if key != "seed_identity_sha256"}
        _require(raw["seed_identity_sha256"] == _seed_identity(unsigned),
                 f"seed {index} identity differs")
        validated.append(dict(raw))
    _require(len(validated) == 6, "exactly six controller-local seeds are required")
    _require({(item["controller"], item["transport_code"]) for item in validated}
             == {(controller, code) for controller in ("CS1", "CS2") for code in SEED_CODES},
             "seed inventory coverage differs")
    return validated


def _validate_axis_metadata(axis: Mapping[str, Any]) -> dict[str, Any]:
    _require(isinstance(axis, Mapping) and set(axis) == _AXIS_KEYS,
             "perturbation axis keys differ")
    _require(isinstance(axis["axis_id"], str) and axis["axis_id"], "axis_id is invalid")
    _require(isinstance(axis["axis_kind"], str), "axis_kind must be time or frame")
    _require(axis["axis_kind"] in {"time", "frame"}, "axis_kind must be time or frame")
    _hash(axis["proof_artifact_sha256"], label="axis proof artifact")
    _require(type(axis["semantics_proven"]) is bool, "axis semantics_proven must be boolean")
    _require(type(axis["safe_for_live"]) is bool, "axis safe_for_live must be boolean")
    _require(isinstance(axis["unit"], str) and axis["unit"], "axis unit is invalid")
    return dict(axis)


def _validate_axis(
    axis: Mapping[str, Any],
    values: Sequence[Any],
    *,
    values_required: bool,
) -> dict[str, Any]:
    checked = _validate_axis_metadata(axis)
    _require(isinstance(values, (list, tuple)), "axis values must be an array")
    if values_required:
        _require(len(values) == FIRST_ROUND_VALUE_COUNT,
                 "first round requires exactly three axis values")
    else:
        _require(len(values) in {0, FIRST_ROUND_VALUE_COUNT},
                 "unproven axis accepts zero or exactly three values")
    for index, value in enumerate(values):
        _require(type(value) in {int, float} and not isinstance(value, bool),
                 f"axis value {index} must be numeric")
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError) as error:
            raise SeedPerturbationError(f"axis value {index} must be finite") from error
        _require(finite, f"axis value {index} must be finite")
    if values_required:
        _require(len(set(values)) == FIRST_ROUND_VALUE_COUNT,
                 "first round axis values must be distinct")
    return checked


def enumerate_m1_metadata(
    seeds: Sequence[Mapping[str, Any]],
    *,
    axis: Mapping[str, Any] | None = None,
    values: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    """Enumerate bounded metadata only when the axis is explicitly proven safe."""

    validated = validate_seed_inventory(seeds)
    if axis is None:
        return []
    checked_axis = _validate_axis_metadata(axis)
    axis_proven = _axis_is_proven(checked_axis)
    # An unproven axis is still schema-checked, but cannot create candidates.
    if not axis_proven:
        _validate_axis(axis, values, values_required=False)
        return []
    checked_axis = _validate_axis(axis, values, values_required=True)
    result: list[dict[str, Any]] = []
    for seed in validated:
        for value in values:
            result.append({
                "controller": seed["controller"],
                "profile_id": seed["profile_id"],
                "seed_code": seed["transport_code"],
                "seed_identity_sha256": seed["seed_identity_sha256"],
                "perturbation_vector": [{
                    "axis_id": checked_axis["axis_id"],
                    "axis_kind": checked_axis["axis_kind"],
                    "value": value,
                    "unit": checked_axis["unit"],
                }],
                "order": 1,
                "position_replicate_ids": list(_POSITION_REPLICATE_IDS),
                "position_replicate_count": len(_POSITION_REPLICATE_IDS),
                "payload_bytes_emitted": False,
                "firmware_include_generated": False,
                "live_eligible": False,
            })
    return result


def build_report(
    *,
    created_at: str,
    axis: Mapping[str, Any] | None = None,
    values: Sequence[Any] = (),
) -> dict[str, Any]:
    """Build a sealed audit report; never generate waveform or firmware bytes."""

    _timestamp(created_at, label="created_at")
    seeds = validate_seed_inventory(build_seed_inventory())
    checked_axis: dict[str, Any] | None = None
    if axis is not None:
        checked_axis = _validate_axis_metadata(axis)
    candidates = enumerate_m1_metadata(seeds, axis=axis, values=values)
    axis_proven = checked_axis is not None and _axis_is_proven(checked_axis)
    blockers = [] if axis_proven else [DECISION_BLOCKED]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "created_at": created_at,
        "panel": {
            "model": PANEL_MODEL,
            "controller_model": CONTROLLER_MODEL,
            "controller_count": 2,
            "controller_local_analysis": True,
        },
        "scope": "offline_seed_inventory_and_bounded_m1_metadata_only",
        "decision": DECISION_METADATA_ONLY if candidates else DECISION_BLOCKED,
        "classification": CLASSIFICATION,
        "evidence_chain": {
            "source_action": {
                "path": SOURCE_ACTION_PATH,
                "file_sha256": SOURCE_ACTION_SHA256,
                "canonical_sha256": SOURCE_CANONICAL_SHA256,
                "identity_pinned": True,
                "decision": "COMPLETE_ENDPOINT_ONLY_NOT_HOLD_PROOF",
            },
            "hold_feasibility_audit": {
                "path": HOLD_AUDIT_PATH,
                "file_sha256": HOLD_AUDIT_FILE_SHA256,
                "canonical_sha256": HOLD_AUDIT_CANONICAL_SHA256,
                "identity_pinned": True,
                "decision": "BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE",
            },
        },
        "seed_inventory": seeds,
        "perturbation_axis": checked_axis,
        "requested_axis_values": list(values) if axis is not None else [],
        "candidate_count": len(candidates),
        "candidate_metadata": candidates,
        "search_contract": {
            "first_round_m": 1,
            "seed_codes": list(SEED_CODES),
            "values_per_axis": FIRST_ROUND_VALUE_COUNT,
            "candidates_per_controller": FIRST_ROUND_VALUE_COUNT * len(SEED_CODES),
            "position_replicates_per_candidate": 4,
            "position_replicate_ids": list(_POSITION_REPLICATE_IDS),
            "single_pixel_no_dither": True,
            "complete_busy_required": True,
            "one_driver_one_visible_refresh": True,
            "same_payload_required_for_both_controllers": True,
            "retry_allowed": False,
            "recovery_allowed": False,
            "autochain_allowed": False,
        },
        "blocker_codes": blockers,
        "next_action": (
            "P2_FULL_PROFILE_ENDPOINT_ATLAS"
            if not candidates
            else "REVIEW_METADATA_ONLY_CANDIDATES_BEFORE_ANY_LIVE_CONTRACT"
        ),
        "output_contract": {
            "candidate_payload_generated": False,
            "candidate_payload_bytes": 0,
            "firmware_include_generated": False,
            "live_runner_created": False,
            "hardware_execution_eligible": False,
            "visible_refresh_authorized": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "relay_or_power_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "raw_waveform_bytes_emitted": False,
            "runtime_payload_generated": False,
        },
        "io_proof": {
            "device_io": False,
            "network_io": False,
            "serial_or_com_io": False,
            "visible_refreshes": 0,
        },
        "artifact_status": dict(_ARTIFACT_STATUS_VALUES),
    }
    unsigned["integrity"] = {
        "canonical_sha256": sha256_hex(canonical_json_bytes(unsigned)),
        "scope": "all_top_level_fields_except_integrity",
    }
    return unsigned


def validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the sealed report and preserve the no-I/O/no-payload boundary."""

    _require(isinstance(report, Mapping), "report must be an object")
    _require(set(report) == _REPORT_KEYS, "report keys differ")
    _require(report["schema_version"] == SCHEMA_VERSION, "report schema differs")
    _require(report["kind"] == KIND, "report kind differs")
    _timestamp(report["created_at"], label="report created_at")
    panel = report["panel"]
    _require(isinstance(panel, Mapping) and set(panel) == _PANEL_KEYS,
             "report panel keys differ")
    _require(panel["model"] == PANEL_MODEL, "report panel model differs")
    _require(panel["controller_model"] == CONTROLLER_MODEL,
             "report controller model differs")
    _require(type(panel["controller_count"]) is int and panel["controller_count"] == 2,
             "report controller count differs")
    _require(panel["controller_local_analysis"] is True,
             "report controller-local marker differs")
    _require(report["scope"] == "offline_seed_inventory_and_bounded_m1_metadata_only",
             "report scope differs")
    _require(report["classification"] == CLASSIFICATION, "report classification differs")

    integrity = report.get("integrity")
    _require(isinstance(integrity, Mapping) and set(integrity) == {"canonical_sha256", "scope"},
             "report integrity is missing or malformed")
    _require(integrity.get("scope") == "all_top_level_fields_except_integrity",
             "report integrity scope differs")
    unsigned = {key: value for key, value in report.items() if key != "integrity"}
    _require(_SHA256.fullmatch(integrity.get("canonical_sha256", "")) is not None,
             "report canonical hash is malformed")
    _require(integrity.get("canonical_sha256") == sha256_hex(canonical_json_bytes(unsigned)),
             "report integrity differs")

    chain = report["evidence_chain"]
    _require(isinstance(chain, Mapping) and set(chain) == _EVIDENCE_CHAIN_KEYS,
             "report evidence chain keys differ")
    source = chain["source_action"]
    _require(isinstance(source, Mapping) and set(source) == _EVIDENCE_ITEM_KEYS,
             "source evidence keys differ")
    _require(source["path"] == SOURCE_ACTION_PATH, "source evidence path differs")
    _require(source["file_sha256"] == SOURCE_ACTION_SHA256,
             "source evidence file hash differs")
    _require(source["canonical_sha256"] == SOURCE_CANONICAL_SHA256,
             "source evidence canonical hash differs")
    _require(source["identity_pinned"] is True, "source evidence is not pinned")
    _require(source["decision"] == "COMPLETE_ENDPOINT_ONLY_NOT_HOLD_PROOF",
             "source evidence decision differs")
    hold = chain["hold_feasibility_audit"]
    _require(isinstance(hold, Mapping) and set(hold) == _EVIDENCE_ITEM_KEYS,
             "hold audit evidence keys differ")
    _require(hold["path"] == HOLD_AUDIT_PATH, "hold audit path differs")
    _require(hold["file_sha256"] == HOLD_AUDIT_FILE_SHA256,
             "hold audit file hash differs")
    _require(hold["canonical_sha256"] == HOLD_AUDIT_CANONICAL_SHA256,
             "hold audit canonical hash differs")
    _require(hold["identity_pinned"] is True, "hold audit is not pinned")
    _require(hold["decision"] == "BLOCKED_NO_ELECTRICALLY_PROVEN_HOLD_CODE",
             "hold audit decision differs")

    seeds = validate_seed_inventory(report["seed_inventory"])
    _require(report["seed_inventory"] == seeds, "seed inventory changed while validating")

    axis = report["perturbation_axis"]
    checked_axis: dict[str, Any] | None = None
    if axis is not None:
        checked_axis = _validate_axis_metadata(axis)
    axis_proven = checked_axis is not None and _axis_is_proven(checked_axis)
    requested_values = report["requested_axis_values"]
    _require(isinstance(requested_values, list), "requested axis values must be an array")
    if checked_axis is not None:
        _validate_axis(checked_axis, requested_values, values_required=axis_proven)
    else:
        _require(requested_values == [], "axis-less report cannot contain requested values")

    search = report["search_contract"]
    _require(isinstance(search, Mapping) and set(search) == _SEARCH_KEYS,
             "search contract keys differ")
    _require(search["first_round_m"] == 1, "search M differs")
    _require(search["seed_codes"] == list(SEED_CODES), "search seed codes differ")
    _require(search["values_per_axis"] == FIRST_ROUND_VALUE_COUNT,
             "search axis value count differs")
    _require(search["candidates_per_controller"] == 9,
             "search candidate count differs")
    _require(search["position_replicates_per_candidate"] == len(_POSITION_REPLICATE_IDS),
             "search position replicate count differs")
    _require(search["position_replicate_ids"] == list(_POSITION_REPLICATE_IDS),
             "search position replicate IDs differ")
    for key in (
        "single_pixel_no_dither",
        "complete_busy_required",
        "one_driver_one_visible_refresh",
        "same_payload_required_for_both_controllers",
    ):
        _require(search[key] is True, f"search {key} differs")
    for key in ("retry_allowed", "recovery_allowed", "autochain_allowed"):
        _require(search[key] is False, f"search {key} differs")

    candidates = report["candidate_metadata"]
    _require(isinstance(candidates, list), "candidate metadata must be an array")
    _require(type(report["candidate_count"]) is int and report["candidate_count"] >= 0,
             "candidate count is invalid")
    _require(report["candidate_count"] == len(candidates),
             "candidate count does not match metadata")
    seed_by_key = {
        (seed["controller"], seed["transport_code"]): seed for seed in seeds
    }
    seen_candidates: set[tuple[str, int, float | int]] = set()
    values_by_seed: dict[tuple[str, int], set[float | int]] = {
        key: set() for key in seed_by_key
    }
    for index, candidate in enumerate(candidates):
        _require(isinstance(candidate, Mapping) and set(candidate) == _CANDIDATE_KEYS,
                 f"candidate {index} keys differ")
        _require(isinstance(candidate["controller"], str)
                 and candidate["controller"] in {"CS1", "CS2"},
                 f"candidate {index} controller differs")
        _require(type(candidate["seed_code"]) is int and candidate["seed_code"] in SEED_CODES,
                 f"candidate {index} seed code differs")
        seed = seed_by_key.get((candidate["controller"], candidate["seed_code"]))
        _require(seed is not None, f"candidate {index} seed binding differs")
        _require(candidate["profile_id"] == PROFILE_ID,
                 f"candidate {index} profile differs")
        _require(candidate["seed_identity_sha256"] == seed["seed_identity_sha256"],
                 f"candidate {index} seed identity differs")
        _require(type(candidate["order"]) is int and candidate["order"] == 1,
                 f"candidate {index} order differs")
        _require(candidate["position_replicate_ids"] == list(_POSITION_REPLICATE_IDS),
                 f"candidate {index} position IDs differ")
        _require(type(candidate["position_replicate_count"]) is int
                 and candidate["position_replicate_count"] == len(_POSITION_REPLICATE_IDS),
                 f"candidate {index} position count differs")
        for key in ("payload_bytes_emitted", "firmware_include_generated", "live_eligible"):
            _require(candidate[key] is False, f"candidate {index} {key} is unsafe")
        vector = candidate["perturbation_vector"]
        _require(isinstance(vector, list) and len(vector) == 1,
                 f"candidate {index} vector differs")
        item = vector[0]
        _require(isinstance(item, Mapping) and set(item) == _VECTOR_KEYS,
                 f"candidate {index} vector keys differ")
        _require(axis_proven and checked_axis is not None,
                 f"candidate {index} has no proven axis")
        _require(item["axis_id"] == checked_axis["axis_id"]
                 and item["axis_kind"] == checked_axis["axis_kind"]
                 and item["unit"] == checked_axis["unit"],
                 f"candidate {index} axis binding differs")
        value = item["value"]
        _require(type(value) in {int, float} and not isinstance(value, bool),
                 f"candidate {index} value is invalid")
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError) as error:
            raise SeedPerturbationError(f"candidate {index} value is invalid") from error
        _require(finite, f"candidate {index} value is invalid")
        key = (candidate["controller"], candidate["seed_code"], value)
        _require(key not in seen_candidates, f"candidate {index} is duplicated")
        seen_candidates.add(key)
        values_by_seed[(candidate["controller"], candidate["seed_code"])].add(value)

    if axis_proven:
        _require(report["decision"] == DECISION_METADATA_ONLY,
                 "proven axis decision differs")
        _require(report["candidate_count"] == 18,
                 "proven axis candidate count differs")
        _require(report["blocker_codes"] == [], "proven axis has blocker")
        _require(report["next_action"] == "REVIEW_METADATA_ONLY_CANDIDATES_BEFORE_ANY_LIVE_CONTRACT",
                 "proven axis next action differs")
        per_seed = {(controller, code): 0 for controller in ("CS1", "CS2") for code in SEED_CODES}
        for candidate in candidates:
            per_seed[(candidate["controller"], candidate["seed_code"])] += 1
        _require(all(count == FIRST_ROUND_VALUE_COUNT for count in per_seed.values()),
                 "proven axis coverage differs")
        expected_values = set(requested_values)
        _require(len(expected_values) == FIRST_ROUND_VALUE_COUNT,
                 "proven axis values differ")
        _require(all(values == expected_values for values in values_by_seed.values()),
                 "candidate axis value sets differ")
    else:
        _require(report["decision"] == DECISION_BLOCKED,
                 "blocked axis decision differs")
        _require(report["candidate_count"] == 0 and candidates == [],
                 "blocked report contains candidates")
        _require(report["blocker_codes"] == [DECISION_BLOCKED],
                 "blocked report blocker differs")
        _require(report["next_action"] == "P2_FULL_PROFILE_ENDPOINT_ATLAS",
                 "blocked report next action differs")

    output = report["output_contract"]
    _require(isinstance(output, Mapping) and set(output) == _OUTPUT_KEYS,
             "output contract keys differ")
    _require(output["candidate_payload_generated"] is False,
             "report claims payload generation")
    _require(type(output["candidate_payload_bytes"]) is int
             and output["candidate_payload_bytes"] == 0,
             "report claims payload bytes")
    for key in ("firmware_include_generated", "live_runner_created",
                "hardware_execution_eligible", "visible_refresh_authorized"):
        _require(output[key] is False, f"report output {key} is unsafe")

    io_proof = report["io_proof"]
    _require(isinstance(io_proof, Mapping) and set(io_proof) == _IO_PROOF_KEYS,
             "I/O proof keys differ")
    for key in ("device_io", "network_io", "serial_or_com_io"):
        _require(io_proof[key] is False, f"I/O proof {key} is unsafe")
    _require(type(io_proof["visible_refreshes"]) is int
             and io_proof["visible_refreshes"] == 0,
             "I/O proof visible refresh count differs")

    artifact_status = report["artifact_status"]
    _require(isinstance(artifact_status, Mapping)
             and set(artifact_status) == _ARTIFACT_STATUS_KEYS,
             "artifact status keys differ")
    _require(dict(artifact_status) == _ARTIFACT_STATUS_VALUES,
             "artifact status differs")

    safety = report["safety"]
    _require(isinstance(safety, Mapping) and set(safety) == _SAFETY_KEYS,
             "report safety keys differ")
    _require(safety["offline_only"] is True, "offline marker differs")
    for key in _SAFETY_KEYS - {"offline_only"}:
        _require(safety[key] is False, f"report safety {key} is unsafe")
    return {
        "valid": True,
        "decision": report["decision"],
        "candidate_count": report["candidate_count"],
        "canonical_sha256": integrity["canonical_sha256"],
        "hardware_execution_eligible": False,
        "visible_refresh_authorized": False,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    """Create one report without overwriting an existing evidence file."""

    validate_report(report)
    path = Path(path)
    _require(path.suffix.lower() == ".json", "output must have a .json suffix")
    _require(not path.is_symlink(), "output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(report) + b"\n"
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise SeedPerturbationError(f"refusing to overwrite {path}") from error
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": sha256_hex(payload),
        "report_canonical_sha256": report["integrity"]["canonical_sha256"],
        "decision": report["decision"],
        "candidate_count": report["candidate_count"],
    }


__all__ = [
    "CLASSIFICATION",
    "CONTROLLER_MODEL",
    "DECISION_BLOCKED",
    "DECISION_METADATA_ONLY",
    "KIND",
    "PANEL_MODEL",
    "SeedPerturbationError",
    "build_report",
    "build_seed_inventory",
    "canonical_json_bytes",
    "enumerate_m1_metadata",
    "sha256_hex",
    "validate_report",
    "validate_seed_inventory",
    "write_report",
]
