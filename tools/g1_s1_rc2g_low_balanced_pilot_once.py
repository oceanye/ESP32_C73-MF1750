#!/usr/bin/env python3
"""Run the sole RC2G N1 low-balanced pilot after its exact MAP primer.

The low-balanced raster is fixed in code.  Before an action can be claimed,
this runner deep-regenerates the complete 2x2 V2 offline bundle, proves that
the selected raster is byte-identical to the previously displayed low-spatial
diagnostic, and validates a canonical successful result from the dedicated N1
MAP-primer runner.  The primer-result SHA-256 is part of the target action
identity, while the permanent claim filename is fixed workspace-wide so a
different result file cannot create a second authorization partition.

The actual device protocol is delegated to the reviewed RC2G quality core:
exact live MAP job1/operation1 prior, one POST /api/frame, target job2/
operation2, nominal timing, nested BUSY edges, immutable report rereads, low
RST/CS1/CS2, and read-only incident capture.  There is no retry or recovery.
This is an exploratory safety/fidelity pilot, not an algorithm qualification.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import FRAME_BYTES, fnv1a  # noqa: E402
from tools import g1_s1_low_spatial_diagnostic as low_spatial  # noqa: E402
from tools import g1_s1_rc2g_map_baseline_once as baseline  # noqa: E402
from tools import g1_s1_rc2g_n1_low_balanced_map_primer_once as primer  # noqa: E402
from tools import g1_s1_rc2g_quality_refresh_once as quality  # noqa: E402
from tools import g1_s1_root_cause_2x2_candidate as factorial  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
PILOT_ID = primer.PILOT_ID
FIXED_ACTION_ID = (
    "rc2g-n1-low-balanced-pilot-after-map-primer-job2-op2-once-v1"
)
RESULT_FILENAME = quality.RESULT_FILENAME
FIXED_CLAIM_REGISTRY_ID = quality.CLAIM_REGISTRY_ID
FIXED_CLAIM_FILENAME = FIXED_ACTION_ID

FACTORIAL_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2"
)
OLD_LOW_SPATIAL_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430"
)
VARIANT_NAME = "low-balanced"
EXPECTED_FACTORIAL_MANIFEST_SHA256 = factorial.EXPECTED_MANIFEST_FILE_SHA256
EXPECTED_FACTORIAL_CANONICAL_SHA256 = factorial.EXPECTED_MANIFEST_CANONICAL_SHA256
EXPECTED_OLD_MANIFEST_SHA256 = (
    "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d"
)
EXPECTED_FRAME_SHA256 = (
    "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65"
)
EXPECTED_FRAME_FNV1A = 0xA9641618
EXPECTED_CS1_DTM_SHA256 = (
    "c85a03621501c8bb0c535467a1581ab451f5bb0fc50fc4227c31e576d23d6070"
)
EXPECTED_CS1_DTM_FNV1A = 0xCB085C03
EXPECTED_CS2_DTM_SHA256 = (
    "bf25594c886c2046512eecf24795f8c2a5dacf1d9c565501658a6e6ea9889bd7"
)
EXPECTED_CS2_DTM_FNV1A = 0x9ABD749A
EXPECTED_STRICT_PREVIEW_SHA256 = (
    "39c10018dda091bb5af0ebad26b006c1c5e7c3374096de086e7cc8debcc42205"
)
EXPECTED_PRIOR_JOB_ID = 1
EXPECTED_PRIOR_OPERATION_ID = 1
EXPECTED_TARGET_JOB_ID = 2
EXPECTED_TARGET_OPERATION_ID = 2

CLASSIFICATION = {
    "experimental": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
    "algorithm_qualification": False,
    "n1_low_balanced_safety_fidelity_pilot_only": True,
    "causal_attribution_authorized": False,
    "natural_image_quality_evaluation": False,
}


class LowBalancedPilotError(RuntimeError):
    """The fixed target action was rejected before device mutation."""


@dataclass(frozen=True)
class _PrimerEvidence:
    path: Path
    result_sha256: str
    attempt_id: str
    claim_sha256: str
    claim_attempt_id: str
    result: Mapping[str, Any]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise LowBalancedPilotError(
            f"canonical JSON encoding failed: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise LowBalancedPilotError(f"{label} must be a SHA-256 string")
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise LowBalancedPilotError(
            f"{label} must be exactly 64 hexadecimal digits"
        )
    return normalized


def _strict_json_object(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise LowBalancedPilotError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise LowBalancedPilotError(f"{label} contains non-finite number {value}")

    try:
        decoded = payload.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except LowBalancedPilotError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LowBalancedPilotError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise LowBalancedPilotError(f"{label} must be a JSON object")
    if payload != _canonical_json(value):
        raise LowBalancedPilotError(f"{label} is not canonical JSON")
    return value


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _load_primer_evidence(
    primer_result: Path,
    expected_result_sha256: str,
) -> _PrimerEvidence:
    expected_sha = _require_sha256(
        expected_result_sha256, label="expected primer result SHA-256"
    )
    if not isinstance(primer_result, Path):
        raise LowBalancedPilotError("primer_result must be pathlib.Path")
    try:
        require_local_regular_path_syntax(
            primer_result, label="N1 MAP primer result"
        )
        if primer_result.name != primer.RESULT_FILENAME:
            raise LowBalancedPilotError(
                f"primer result filename must be {primer.RESULT_FILENAME}"
            )
        if os.path.lexists(primer_result) and primer_result.is_symlink():
            raise LowBalancedPilotError("primer result must not be a symlink")
        path = primer_result.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
    except LowBalancedPilotError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise LowBalancedPilotError(f"could not resolve primer result: {error}") from error
    if not path.is_file() or not _is_within(path, workspace):
        raise LowBalancedPilotError(
            "primer result must be a regular file inside the workspace"
        )
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise LowBalancedPilotError(f"could not read primer result: {error}") from error
    actual_sha = _sha256(payload)
    if actual_sha != expected_sha:
        raise LowBalancedPilotError("primer result SHA-256 does not match")
    result = _strict_json_object(payload, label="primer result")

    required_result = {
        "schema_version": primer.SCHEMA_VERSION,
        "kind": primer.RESULT_KIND,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "action_id": primer.FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
        "action_identity_sha256": primer.ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": primer.AUTHORIZATION_CONFIRMATION_SHA256,
        "authorization_consumed_permanently": True,
        "campaign_id_override_supported": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "follow_up_low_balanced_refresh_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "algorithm_qualification": False,
        "outcome": "protocol_verified_manual_observation_required",
        "protocol_verified": True,
        "manual_observation_completed": False,
    }
    for key, expected in required_result.items():
        if result.get(key) != expected or type(result.get(key)) is not type(expected):
            raise LowBalancedPilotError(
                f"primer result field {key!r} is not the exact successful contract"
            )
    if result.get("classification") != primer.CLASSIFICATION:
        raise LowBalancedPilotError("primer result classification changed")
    attempt_id = result.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise LowBalancedPilotError("primer result attempt_id is missing")

    claim_reference = result.get("authorization_claim")
    if not isinstance(claim_reference, Mapping):
        raise LowBalancedPilotError("primer authorization claim reference is missing")
    if (
        claim_reference.get("registry_id") != primer.CLAIM_REGISTRY_ID
        or claim_reference.get("file") != primer.FIXED_ACTION_ID
        or claim_reference.get("attempt_id") != attempt_id
        or claim_reference.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise LowBalancedPilotError("primer authorization claim reference changed")
    claim_sha = _require_sha256(
        claim_reference.get("sha256"), label="primer claim SHA-256"
    )
    claim_path = primer.DEFAULT_AUTHORIZATION_REGISTRY / primer.FIXED_ACTION_ID
    try:
        registry_path = primer.DEFAULT_AUTHORIZATION_REGISTRY.resolve(strict=True)
        resolved_claim = claim_path.resolve(strict=True)
        if (
            primer.DEFAULT_AUTHORIZATION_REGISTRY.is_symlink()
            or claim_path.is_symlink()
            or not registry_path.is_dir()
            or not resolved_claim.is_file()
            or not _is_within(registry_path, workspace)
            or not _is_within(resolved_claim, registry_path)
        ):
            raise LowBalancedPilotError(
                "primer permanent claim file or registry is unsafe"
            )
        claim_payload = resolved_claim.read_bytes()
    except LowBalancedPilotError:
        raise
    except OSError as error:
        raise LowBalancedPilotError(
            f"primer permanent claim file is unavailable: {error}"
        ) from error
    if _sha256(claim_payload) != claim_sha:
        raise LowBalancedPilotError("primer permanent claim SHA-256 differs")
    claim = _strict_json_object(claim_payload, label="primer permanent claim")
    required_claim = {
        "schema_version": primer.SCHEMA_VERSION,
        "kind": primer.CLAIM_KIND,
        "registry_id": primer.CLAIM_REGISTRY_ID,
        "action_id": primer.FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
        "action_identity": primer.ACTION_IDENTITY,
        "action_identity_sha256": primer.ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": primer.AUTHORIZATION_CONFIRMATION_SHA256,
        "attempt_id": attempt_id,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "frame_sha256": baseline.EXPECTED_FRAME_SHA256,
        "campaign_id_override_supported": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "follow_up_low_balanced_refresh_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    for key, expected in required_claim.items():
        if claim.get(key) != expected:
            raise LowBalancedPilotError(
                f"primer permanent claim field {key!r} changed"
            )
    confirmations = claim.get("confirmations")
    if (
        not isinstance(confirmations, Mapping)
        or confirmations.get("authorization_confirmation")
        != primer.REQUIRED_AUTHORIZATION_CONFIRMATION
        or any(
            confirmations.get(key) is not True
            for key in (
                "rc2g_flashed_fresh_boot",
                "J2_powered_supervised",
                "supply_and_temperature_normal",
                "single_visible_primer_refresh",
            )
        )
    ):
        raise LowBalancedPilotError("primer permanent claim confirmations changed")
    result_directory = claim.get("result_directory")
    if not isinstance(result_directory, str):
        raise LowBalancedPilotError("primer claim result directory is missing")
    try:
        claimed_directory = Path(result_directory).resolve(strict=True)
    except OSError as error:
        raise LowBalancedPilotError(
            f"primer claimed result directory is unavailable: {error}"
        ) from error
    if claimed_directory != path.parent:
        raise LowBalancedPilotError("primer result is not in its claimed directory")

    fresh = result.get("fresh_boot_preflight")
    if not isinstance(fresh, Mapping):
        raise LowBalancedPilotError("primer fresh-boot evidence is missing")
    version = fresh.get("version")
    if not isinstance(version, Mapping):
        raise LowBalancedPilotError("primer fresh-boot version evidence is missing")
    fresh_gpio = fresh.get("gpio_status_raw")
    if not isinstance(fresh_gpio, Mapping):
        raise LowBalancedPilotError("primer fresh-boot GPIO evidence is missing")
    try:
        baseline._validate_version(version, label="stored primer fresh-boot firmware")
        baseline._validate_gpio_snapshot(
            fresh_gpio, label="stored primer fresh-boot GPIO"
        )
    except baseline.Rc2gMapBaselineError as error:
        raise LowBalancedPilotError(str(error)) from error
    if fresh.get("job_raw") != {
        "job_id": 0,
        "action": "none",
        "state": "idle",
        "result": None,
        "queued_at_ms": 0,
        "started_at_ms": 0,
        "finished_at_ms": 0,
        "frame_fnv1a": 0,
    }:
        raise LowBalancedPilotError("stored primer did not start at exact fresh job0")
    if fresh.get("diagnostic_raw") != {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    }:
        raise LowBalancedPilotError("stored primer fresh boot already had a report")
    if fresh.get("busy_after_rst_low_is_informational") is not True:
        raise LowBalancedPilotError("stored primer fresh-boot BUSY policy changed")

    completed = result.get("completed_map_evidence")
    if not isinstance(completed, Mapping):
        raise LowBalancedPilotError("completed MAP evidence is missing")
    for field in ("network_report", "job_raw", "diagnostic_raw", "gpio_status_raw"):
        if not isinstance(completed.get(field), Mapping):
            raise LowBalancedPilotError(
                f"completed MAP evidence field {field!r} is missing"
            )
    try:
        map_snapshot = baseline._validate_fixture_snapshot()
        validated = baseline._validate_completed_map_evidence(
            completed.get("network_report"),
            completed.get("job_raw"),
            completed.get("diagnostic_raw"),
            completed.get("gpio_status_raw"),
            map_snapshot.frame,
        )
    except baseline.Rc2gMapBaselineError as error:
        raise LowBalancedPilotError(
            f"stored primer MAP evidence failed deep validation: {error}"
        ) from error
    if dict(validated) != dict(completed):
        raise LowBalancedPilotError("stored primer MAP evidence is not canonical")

    request_audit = result.get("request_audit")
    if not isinstance(request_audit, Mapping):
        raise LowBalancedPilotError("primer request audit is missing")
    calls = request_audit.get("calls")
    if (
        request_audit.get("post_attempt_count") != 1
        or request_audit.get("post_issued_count") != 1
        or not isinstance(calls, list)
    ):
        raise LowBalancedPilotError("primer request audit is not one successful POST")
    allowed_get_endpoints = {
        "/api/version",
        "/api/job",
        "/api/diagnostic/report",
        "/api/diagnostic/status",
    }
    post_calls = 0
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, Mapping) or call.get("index") != index:
            raise LowBalancedPilotError("primer request audit call order changed")
        method = call.get("method")
        endpoint = call.get("endpoint")
        outcome = call.get("outcome")
        if method == "POST":
            post_calls += 1
            if (
                endpoint != "/api/frame"
                or outcome != "response"
                or call.get("status") != 202
                or call.get("request_bytes") != FRAME_BYTES
                or call.get("request_sha256") != baseline.EXPECTED_FRAME_SHA256
            ):
                raise LowBalancedPilotError(
                    "primer request audit POST is not the sole successful MAP ingress"
                )
            continue
        if (
            method != "GET"
            or endpoint not in allowed_get_endpoints
            or call.get("request_bytes") != 0
            or outcome not in {"response", "exception"}
        ):
            raise LowBalancedPilotError(
                "primer request audit contains a non-read-only or unknown call"
            )
        if outcome == "response" and call.get("status") != 200:
            raise LowBalancedPilotError(
                "primer request audit contains a non-200 GET response"
            )
        if outcome == "exception" and not isinstance(call.get("error"), Mapping):
            raise LowBalancedPilotError(
                "primer request audit GET exception lacks frozen error evidence"
            )
    if post_calls != 1:
        raise LowBalancedPilotError("primer request audit is not one successful POST")

    return _PrimerEvidence(
        path=path,
        result_sha256=actual_sha,
        attempt_id=attempt_id,
        claim_sha256=claim_sha,
        claim_attempt_id=str(claim.get("attempt_id")),
        result=dict(result),
    )


def _load_fixed_candidate() -> quality._CandidateSnapshot:
    try:
        manifest = factorial.validate_factorial_directory(FACTORIAL_DIR)
    except factorial.FactorialCandidateError as error:
        raise LowBalancedPilotError(
            f"2x2 V2 bundle deep validation failed: {error}"
        ) from error
    manifest_path = FACTORIAL_DIR / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise LowBalancedPilotError(
            f"could not reread fixed 2x2 manifest: {error}"
        ) from error
    manifest_file_sha = _sha256(manifest_bytes)
    integrity = manifest.get("manifest_integrity")
    canonical_sha = (
        integrity.get("canonical_sha256") if isinstance(integrity, Mapping) else None
    )
    if (
        manifest_file_sha != EXPECTED_FACTORIAL_MANIFEST_SHA256
        or canonical_sha != EXPECTED_FACTORIAL_CANONICAL_SHA256
    ):
        raise LowBalancedPilotError("2x2 V2 frozen manifest identity changed")
    classification = manifest.get("classification")
    if (
        not isinstance(classification, Mapping)
        or classification.get("upload_authorized") is not False
        or classification.get("hardware_tested") is not False
        or classification.get("simulation_only") is not True
        or classification.get("strict_metric_orthogonality_proven") is not False
    ):
        raise LowBalancedPilotError("2x2 V2 fail-closed classification changed")
    variants = manifest.get("variants")
    variant = variants.get(VARIANT_NAME) if isinstance(variants, Mapping) else None
    if not isinstance(variant, Mapping):
        raise LowBalancedPilotError("2x2 V2 low-balanced variant is missing")
    if variant.get("factors") != {
        "controller_internal_spatial_frequency": "low",
        "half_load": "balanced",
    }:
        raise LowBalancedPilotError("2x2 V2 low-balanced factors changed")
    frame_record = variant.get("frame")
    if not isinstance(frame_record, Mapping):
        raise LowBalancedPilotError("2x2 V2 low-balanced frame record is missing")
    try:
        frame = (FACTORIAL_DIR / "low-balanced.frame.bin").read_bytes()
    except OSError as error:
        raise LowBalancedPilotError(
            f"could not read fixed low-balanced frame: {error}"
        ) from error
    if (
        len(frame) != FRAME_BYTES
        or _sha256(frame) != EXPECTED_FRAME_SHA256
        or fnv1a(frame) != EXPECTED_FRAME_FNV1A
        or frame_record.get("bytes") != FRAME_BYTES
        or frame_record.get("sha256") != EXPECTED_FRAME_SHA256
        or frame_record.get("fnv1a") != f"0x{EXPECTED_FRAME_FNV1A:08X}"
    ):
        raise LowBalancedPilotError("fixed low-balanced frame identity changed")
    controller_records = quality._controller_records(frame)
    if list(controller_records) != variant.get("controllers"):
        raise LowBalancedPilotError("fixed low-balanced controller records changed")
    if (
        controller_records[0].get("dtm_sha256") != EXPECTED_CS1_DTM_SHA256
        or controller_records[0].get("dtm_fnv1a")
        != f"0x{EXPECTED_CS1_DTM_FNV1A:08X}"
        or controller_records[1].get("dtm_sha256") != EXPECTED_CS2_DTM_SHA256
        or controller_records[1].get("dtm_fnv1a")
        != f"0x{EXPECTED_CS2_DTM_FNV1A:08X}"
    ):
        raise LowBalancedPilotError("fixed low-balanced DTM identity changed")
    try:
        preview = (FACTORIAL_DIR / "low-balanced.strict-final.png").read_bytes()
    except OSError as error:
        raise LowBalancedPilotError(
            f"could not read fixed low-balanced preview: {error}"
        ) from error
    if _sha256(preview) != EXPECTED_STRICT_PREVIEW_SHA256:
        raise LowBalancedPilotError("fixed low-balanced strict preview changed")

    try:
        low_spatial.validate_diagnostic_directory(OLD_LOW_SPATIAL_DIR)
    except low_spatial.DiagnosticError as error:
        raise LowBalancedPilotError(
            f"old successful low-spatial bundle failed validation: {error}"
        ) from error
    try:
        old_manifest_payload = (OLD_LOW_SPATIAL_DIR / "manifest.json").read_bytes()
        old_frame = (OLD_LOW_SPATIAL_DIR / "frame.bin").read_bytes()
    except OSError as error:
        raise LowBalancedPilotError(
            f"could not reread old low-spatial evidence: {error}"
        ) from error
    if (
        _sha256(old_manifest_payload) != EXPECTED_OLD_MANIFEST_SHA256
        or old_frame != frame
    ):
        raise LowBalancedPilotError(
            "low-balanced raster is not byte-identical to the old successful low-spatial frame"
        )

    return quality._CandidateSnapshot(
        directory=FACTORIAL_DIR.resolve(strict=True),
        manifest=dict(manifest),
        manifest_bytes=manifest_bytes,
        manifest_file_sha256=manifest_file_sha,
        manifest_canonical_sha256=str(canonical_sha),
        algorithm="n1-low-balanced-safety-fidelity-pilot",
        frame=frame,
        frame_sha256=EXPECTED_FRAME_SHA256,
        frame_fnv1a=EXPECTED_FRAME_FNV1A,
        controllers=controller_records,
    )


def _action_binding(evidence: _PrimerEvidence) -> dict[str, Any]:
    completed = evidence.result["completed_map_evidence"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-rc2g-n1-low-balanced-pilot-evidence-binding",
        "fixed_action_id": FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
        "phase": "N1",
        "fixed_cell": VARIANT_NAME,
        "claim_scope": {
            "registry_id": FIXED_CLAIM_REGISTRY_ID,
            "fixed_filename": FIXED_CLAIM_FILENAME,
            "workspace_global_fixed_action": True,
            "partitioned_by_primer_result_sha256": False,
            "partitioned_by_result_directory": False,
            "campaign_id_override_supported": False,
        },
        "primer_result": {
            "sha256": evidence.result_sha256,
            "attempt_id": evidence.attempt_id,
            "claim_sha256": evidence.claim_sha256,
            "action_id": primer.FIXED_ACTION_ID,
            "action_identity_sha256": primer.ACTION_IDENTITY_SHA256,
            "completed_job_id": EXPECTED_PRIOR_JOB_ID,
            "completed_operation_id": EXPECTED_PRIOR_OPERATION_ID,
            "frame_sha256": baseline.EXPECTED_FRAME_SHA256,
            "frame_fnv1a": f"0x{baseline.EXPECTED_FRAME_FNV1A:08X}",
            "cs1_dtm_fnv1a": f"0x{baseline.EXPECTED_CS1_DTM_FNV1A:08X}",
            "cs2_dtm_fnv1a": f"0x{baseline.EXPECTED_CS2_DTM_FNV1A:08X}",
            "manual_visual_pass_must_be_confirmed_separately": True,
            "job_raw_canonical_sha256": _sha256(
                _canonical_json(completed["job_raw"])
            ),
            "diagnostic_raw_canonical_sha256": _sha256(
                _canonical_json(completed["diagnostic_raw"])
            ),
        },
        "candidate": {
            "source_bundle_manifest_file_sha256": EXPECTED_FACTORIAL_MANIFEST_SHA256,
            "source_bundle_manifest_canonical_sha256": (
                EXPECTED_FACTORIAL_CANONICAL_SHA256
            ),
            "source_bundle_upload_authorized": False,
            "single_exact_action_override_only": True,
            "old_low_spatial_manifest_sha256": EXPECTED_OLD_MANIFEST_SHA256,
            "byte_identical_to_old_successful_low_spatial_frame": True,
            "frame_sha256": EXPECTED_FRAME_SHA256,
            "frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
            "cs1_dtm_fnv1a": f"0x{EXPECTED_CS1_DTM_FNV1A:08X}",
            "cs2_dtm_fnv1a": f"0x{EXPECTED_CS2_DTM_FNV1A:08X}",
            "strict_preview_sha256": EXPECTED_STRICT_PREVIEW_SHA256,
        },
        "classification": dict(CLASSIFICATION),
    }


def _build_contract(
    primer_result: Path,
    primer_result_sha256: str,
) -> tuple[quality._CandidateSnapshot, _PrimerEvidence, Mapping[str, Any], quality._RunContract]:
    evidence = _load_primer_evidence(primer_result, primer_result_sha256)
    snapshot = _load_fixed_candidate()
    binding = _action_binding(evidence)
    try:
        contract = quality._build_run_contract(
            snapshot,
            expected_prior_job_id=EXPECTED_PRIOR_JOB_ID,
            expected_prior_operation_id=EXPECTED_PRIOR_OPERATION_ID,
            expected_prior_frame_sha256=baseline.EXPECTED_FRAME_SHA256,
            expected_prior_frame_fnv1a=baseline.EXPECTED_FRAME_FNV1A,
            expected_prior_cs1_dtm_fnv1a=baseline.EXPECTED_CS1_DTM_FNV1A,
            expected_prior_cs2_dtm_fnv1a=baseline.EXPECTED_CS2_DTM_FNV1A,
            expected_target_job_id=EXPECTED_TARGET_JOB_ID,
            expected_target_operation_id=EXPECTED_TARGET_OPERATION_ID,
            fixed_external_evidence_binding=binding,
        )
    except quality.Rc2gQualityRefreshError as error:
        raise LowBalancedPilotError(str(error)) from error
    return snapshot, evidence, binding, contract


def describe_low_balanced_pilot(
    primer_result: Path,
    primer_result_sha256: str,
) -> dict[str, Any]:
    """Deep-validate all local evidence without a claim or device access."""

    _snapshot, evidence, binding, contract = _build_contract(
        primer_result, primer_result_sha256
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "authorization-description-only",
        "device_io_performed": False,
        "claim_created": False,
        "fixed_action_id": FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
        "primer_result_sha256": evidence.result_sha256,
        "action_identity": dict(contract.action_identity),
        "action_identity_sha256": contract.action_identity_sha256,
        "required_authorization_confirmation": (
            contract.required_authorization_confirmation
        ),
        "fixed_claim": {
            "registry_id": FIXED_CLAIM_REGISTRY_ID,
            "filename": FIXED_CLAIM_FILENAME,
        },
        "fixed_external_evidence_binding": dict(binding),
        "strict_preview": {
            "path": str(FACTORIAL_DIR / "low-balanced.strict-final.png"),
            "sha256": EXPECTED_STRICT_PREVIEW_SHA256,
        },
        "classification": dict(CLASSIFICATION),
    }


def run_low_balanced_pilot_once(
    result_dir: Path,
    base_url: str,
    primer_result: Path,
    *,
    primer_result_sha256: str,
    authorization_confirmation: str,
    confirm_j2_powered_supervised: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_primer_visual_pass: bool = False,
    confirm_no_esp32_reboot_since_primer: bool = False,
    confirm_no_j2_disconnect_since_primer: bool = False,
    confirm_reviewed_low_balanced_strict_preview: bool = False,
    job_timeout_s: float = quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Any = None,
    clock: Any = None,
) -> dict[str, Any]:
    """Claim and execute the sole fixed low-balanced target refresh."""

    explicit = {
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "primer_visual_fidelity_pass": confirm_primer_visual_pass,
        "no_esp32_reboot_since_primer": confirm_no_esp32_reboot_since_primer,
        "no_j2_disconnect_since_primer": confirm_no_j2_disconnect_since_primer,
        "reviewed_low_balanced_strict_preview": (
            confirm_reviewed_low_balanced_strict_preview
        ),
    }
    if any(type(value) is not bool or value is not True for value in explicit.values()):
        raise LowBalancedPilotError(
            "all supervised-power, normal-supply, primer-visual-pass, no-reboot, no-J2-disconnect, and reviewed-preview confirmations are required"
        )
    snapshot, _evidence, binding, contract = _build_contract(
        primer_result, primer_result_sha256
    )
    if authorization_confirmation != contract.required_authorization_confirmation:
        raise LowBalancedPilotError(
            "exact low-balanced pilot authorization is required; run --describe-only after the primer"
        )
    run_kwargs: dict[str, Any] = {}
    if sleeper is not None:
        run_kwargs["sleeper"] = sleeper
    if clock is not None:
        run_kwargs["clock"] = clock
    try:
        return quality.run_rc2g_quality_refresh_once(
            result_dir,
            base_url,
            FACTORIAL_DIR,
            expected_manifest_sha256=EXPECTED_FACTORIAL_MANIFEST_SHA256,
            expected_prior_job_id=EXPECTED_PRIOR_JOB_ID,
            expected_prior_operation_id=EXPECTED_PRIOR_OPERATION_ID,
            expected_prior_frame_sha256=baseline.EXPECTED_FRAME_SHA256,
            expected_prior_frame_fnv1a=baseline.EXPECTED_FRAME_FNV1A,
            expected_prior_cs1_dtm_fnv1a=baseline.EXPECTED_CS1_DTM_FNV1A,
            expected_prior_cs2_dtm_fnv1a=baseline.EXPECTED_CS2_DTM_FNV1A,
            expected_target_job_id=EXPECTED_TARGET_JOB_ID,
            expected_target_operation_id=EXPECTED_TARGET_OPERATION_ID,
            authorization_confirmation=authorization_confirmation,
            confirm_j2_powered_supervised=confirm_j2_powered_supervised,
            confirm_supply_and_temperature_normal=(
                confirm_supply_and_temperature_normal
            ),
            confirm_reviewed_strict_preview=(
                confirm_reviewed_low_balanced_strict_preview
            ),
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            _prevalidated_snapshot=snapshot,
            _fixed_external_evidence_binding=binding,
            _fixed_expected_prior_evidence={
                "job_raw": dict(
                    _evidence.result["completed_map_evidence"]["job_raw"]
                ),
                "diagnostic_raw": dict(
                    _evidence.result["completed_map_evidence"]["diagnostic_raw"]
                ),
            },
            _additional_fixed_confirmations={
                "primer_visual_fidelity_pass": confirm_primer_visual_pass,
                "no_esp32_reboot_since_primer": (
                    confirm_no_esp32_reboot_since_primer
                ),
                "no_j2_disconnect_since_primer": (
                    confirm_no_j2_disconnect_since_primer
                ),
                "fixed_low_balanced_pilot_scope_acknowledged": True,
            },
            _fixed_claim_filename=FIXED_CLAIM_FILENAME,
            _result_classification_override=CLASSIFICATION,
            _manual_observation_override=[
                "primer_MAP_visual_fidelity_was_confirmed_before_target",
                "screen_matches_frozen_low_balanced_strict_preview",
                "large_regions_left_right_halves_orientation_and_center_seam",
                "all_six_codes_full_panel_coverage_and_no_MAP_retention",
                "power_supply_3_3v_cv_current_and_temperature",
                "no_odor_sound_hotspot_damage_or_voltage_droop",
                "diagnostic_geometry_is_not_scored_as_natural_image_quality",
                "post_run_power_state",
            ],
            _fixed_result_metadata={
                "fixed_action_id": FIXED_ACTION_ID,
                "pilot_id": PILOT_ID,
                "primer_result_sha256": _evidence.result_sha256,
                "source_bundle_upload_authorized": False,
                "single_exact_action_override_only": True,
            },
            **run_kwargs,
        )
    except quality.Rc2gQualityRefreshUnknown:
        raise
    except quality.Rc2gQualityRefreshError as error:
        raise LowBalancedPilotError(str(error)) from error


def _sha256_argument(value: str) -> str:
    try:
        return _require_sha256(value, label="primer result SHA-256")
    except LowBalancedPilotError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--primer-result", type=Path, required=True)
    parser.add_argument(
        "--primer-result-sha256", type=_sha256_argument, required=True
    )
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--confirm")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument(
        "--confirm-supply-and-temperature-normal", action="store_true"
    )
    parser.add_argument("--confirm-primer-visual-pass", action="store_true")
    parser.add_argument("--confirm-no-esp32-reboot-since-primer", action="store_true")
    parser.add_argument("--confirm-no-j2-disconnect-since-primer", action="store_true")
    parser.add_argument(
        "--confirm-reviewed-low-balanced-strict-preview", action="store_true"
    )
    args = parser.parse_args(argv)
    if not args.describe_only:
        missing = [
            name
            for name, value in (
                ("--result-dir", args.result_dir),
                ("--url", args.url),
                ("--confirm", args.confirm),
            )
            if value is None
        ]
        if missing:
            parser.error("normal run requires " + ", ".join(missing))
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.describe_only:
            result = describe_low_balanced_pilot(
                args.primer_result, args.primer_result_sha256
            )
        else:
            assert args.result_dir is not None
            assert args.url is not None
            assert args.confirm is not None
            result = run_low_balanced_pilot_once(
                args.result_dir,
                args.url,
                args.primer_result,
                primer_result_sha256=args.primer_result_sha256,
                authorization_confirmation=args.confirm,
                confirm_j2_powered_supervised=(
                    args.confirm_j2_powered_supervised
                ),
                confirm_supply_and_temperature_normal=(
                    args.confirm_supply_and_temperature_normal
                ),
                confirm_primer_visual_pass=args.confirm_primer_visual_pass,
                confirm_no_esp32_reboot_since_primer=(
                    args.confirm_no_esp32_reboot_since_primer
                ),
                confirm_no_j2_disconnect_since_primer=(
                    args.confirm_no_j2_disconnect_since_primer
                ),
                confirm_reviewed_low_balanced_strict_preview=(
                    args.confirm_reviewed_low_balanced_strict_preview
                ),
            )
    except quality.Rc2gQualityRefreshUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except LowBalancedPilotError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
