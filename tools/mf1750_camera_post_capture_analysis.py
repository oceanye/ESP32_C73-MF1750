#!/usr/bin/env python3
"""Seal one offline visual analysis against MF1750 camera evidence.

This module never opens a camera, socket, serial port, relay, or display.  It
does not mutate the completed action receipt, capture sidecar, or JPEG.  A
successful ``create`` writes exactly one new ``camera-action-NN.analysis.json``
file with exclusive-create semantics; ``validate`` rechecks every bound byte.

Importing this module performs no filesystem or device I/O.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


SCHEMA_VERSION = 1
KIND = "mf1750-camera-post-capture-analysis"
ERROR_KIND = "mf1750-camera-post-capture-analysis-error"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
OUTPUT_WRITE_CONTRACT = "O_EXCL"
VERDICTS = frozenset({"PASS", "FAIL", "INCONCLUSIVE"})
CONFIDENCES = frozenset({"low", "medium", "high"})
CLAIM_SCOPES = frozenset({"visible_roi", "full_panel"})
CAPTURE_SCOPES = frozenset({"partial_panel", "full_panel"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OUTPUT_NAME_RE = re.compile(r"^camera-action-(\d{2})\.analysis\.json$")


class PostCaptureAnalysisError(RuntimeError):
    """An analysis record or one of its immutable bindings is invalid."""


class _DuplicateKeyError(ValueError):
    pass


def _load_camera_module() -> Any:
    """Load the capture validator without making direct-script use brittle."""

    try:
        from tools import mf1750_camera_capture_evidence as camera
    except ModuleNotFoundError as error:
        if error.name != "tools":
            raise
        import mf1750_camera_capture_evidence as camera  # type: ignore[no-redef]

    return camera


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PostCaptureAnalysisError(
            f"value is not canonical JSON: {error}"
        ) from error


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "integrity" in result:
        raise PostCaptureAnalysisError("cannot seal a record that has integrity")
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _canonical_sha256(result),
    }
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PostCaptureAnalysisError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise PostCaptureAnalysisError(f"cannot read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise PostCaptureAnalysisError(f"{label} changed while it was read")
    return payload


def _load_strict_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PostCaptureAnalysisError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise PostCaptureAnalysisError(f"{label} root must be an object")
    return payload, value


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PostCaptureAnalysisError(f"{label} must be an object")
    return value


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PostCaptureAnalysisError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    text = _require_text(value, label=label)
    if SHA256_RE.fullmatch(text) is None:
        raise PostCaptureAnalysisError(f"{label} is not lowercase SHA-256")
    return text


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _require_mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise PostCaptureAnalysisError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise PostCaptureAnalysisError(f"{label}.integrity algorithm differs")
    declared = _require_sha256(
        integrity.get("sha256"), label=f"{label}.integrity.sha256"
    )
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _canonical_sha256(unsigned) != declared:
        raise PostCaptureAnalysisError(f"{label}.integrity SHA-256 differs")
    return declared


def _normalise_object(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PostCaptureAnalysisError(f"{label} must be an object")
    try:
        normalised = json.loads(_canonical_json_bytes(dict(value)).decode("utf-8"))
    except json.JSONDecodeError as error:  # pragma: no cover - canonical bytes decode
        raise PostCaptureAnalysisError(f"cannot normalise {label}: {error}") from error
    if not isinstance(normalised, dict):  # pragma: no cover - guarded above
        raise PostCaptureAnalysisError(f"{label} must remain an object")
    return normalised


def _normalise_text_list(value: Sequence[str], *, label: str) -> list[str]:
    if isinstance(value, (str, bytes)):
        raise PostCaptureAnalysisError(f"{label} must be an array of strings")
    return [_require_text(item, label=f"{label} item") for item in value]


def _require_timestamp(value: Any, *, label: str) -> str:
    text = _require_text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise PostCaptureAnalysisError(f"{label} must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise PostCaptureAnalysisError(f"{label} must include a UTC offset")
    return text


def _relative_path(path: Path, *, record_path: Path, label: str) -> str:
    base = record_path.parent.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as error:
        raise PostCaptureAnalysisError(
            f"{label} must be inside the analysis directory tree"
        ) from error
    if not relative.parts:
        raise PostCaptureAnalysisError(f"{label} cannot be the analysis directory")
    return PurePosixPath(*relative.parts).as_posix()


def _resolve_path(value: Any, *, record_path: Path, label: str) -> Path:
    text = _require_text(value, label=label)
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PostCaptureAnalysisError(f"{label} must be a safe relative POSIX path")
    base = record_path.parent.resolve()
    candidate = base.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise PostCaptureAnalysisError(
            f"{label} escapes the analysis directory"
        ) from error
    return candidate


def _capture_relative_path(
    value: Any, *, capture_sidecar_path: Path, label: str
) -> Path:
    text = _require_text(value, label=label)
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PostCaptureAnalysisError(f"{label} is not a safe relative POSIX path")
    base = capture_sidecar_path.parent.resolve()
    candidate = base.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise PostCaptureAnalysisError(
            f"{label} escapes the capture directory"
        ) from error
    return candidate


def _reserve_output(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise PostCaptureAnalysisError(
            f"refusing to overwrite analysis record: {path}"
        ) from error
    except OSError as error:
        raise PostCaptureAnalysisError(
            f"cannot reserve analysis record: {error}"
        ) from error


def _write_reserved(fd: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        count = os.write(fd, payload[written:])
        if count < 1:
            raise PostCaptureAnalysisError("short write to analysis record")
        written += count
    os.fsync(fd)


def _validate_assessment(
    *,
    capture_scope: str,
    claim_scope: str,
    verdict: str,
    confidence: str,
    candidate_detected: bool | None,
    observations: Sequence[str],
    limitations: Sequence[str],
) -> tuple[list[str], list[str]]:
    if capture_scope not in CAPTURE_SCOPES:
        raise PostCaptureAnalysisError("capture coverage scope is invalid")
    if claim_scope not in CLAIM_SCOPES:
        raise PostCaptureAnalysisError("analysis claim_scope is invalid")
    if verdict not in VERDICTS:
        raise PostCaptureAnalysisError("analysis verdict is invalid")
    if confidence not in CONFIDENCES:
        raise PostCaptureAnalysisError("analysis confidence is invalid")
    if not (
        candidate_detected is True
        or candidate_detected is False
        or candidate_detected is None
    ):
        raise PostCaptureAnalysisError(
            "candidate_detected must be true, false, or null"
        )
    clean_observations = _normalise_text_list(observations, label="observations")
    clean_limitations = _normalise_text_list(limitations, label="limitations")
    if capture_scope == "partial_panel" and claim_scope == "full_panel":
        raise PostCaptureAnalysisError(
            "partial_panel evidence cannot make a full-panel claim"
        )
    expected_candidate = (
        True if verdict == "PASS" else False if verdict == "FAIL" else None
    )
    if candidate_detected is not expected_candidate:
        raise PostCaptureAnalysisError(
            "candidate_detected must be true for PASS, false for FAIL, and null "
            "for INCONCLUSIVE"
        )
    if confidence == "low" and verdict != "INCONCLUSIVE":
        raise PostCaptureAnalysisError("low-confidence analysis must be INCONCLUSIVE")
    if verdict != "INCONCLUSIVE" and not clean_observations:
        raise PostCaptureAnalysisError(
            "a conclusive analysis requires at least one observation"
        )
    if verdict == "PASS" and confidence == "high":
        if (
            capture_scope != "full_panel"
            or claim_scope != "full_panel"
            or candidate_detected is not True
        ):
            raise PostCaptureAnalysisError(
                "a high-confidence PASS candidate requires full_panel capture and "
                "claim coverage with candidate_detected=true"
            )
    return clean_observations, clean_limitations


def _load_validated_capture(
    capture_sidecar_path: Path,
) -> tuple[bytes, dict[str, Any], str]:
    camera = _load_camera_module()
    try:
        validated = camera.validate_capture_evidence(capture_sidecar_path)
    except Exception as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise PostCaptureAnalysisError(
            f"capture evidence validation failed: {error}"
        ) from error
    payload, strict_root = _load_strict_json(
        capture_sidecar_path, label="capture sidecar"
    )
    if strict_root != validated:
        raise PostCaptureAnalysisError(
            "capture validator result differs from persisted sidecar"
        )
    integrity = _require_mapping(
        strict_root.get("integrity"), label="capture sidecar.integrity"
    )
    canonical = _require_sha256(
        integrity.get("sha256"), label="capture sidecar.integrity.sha256"
    )
    return payload, strict_root, canonical


def _default_claim_scope(capture_scope: str) -> str:
    return "full_panel" if capture_scope == "full_panel" else "visible_roi"


def create_post_capture_analysis(
    *,
    capture_sidecar_path: Path,
    analysis_path: Path,
    analysis_source: str,
    model_or_algorithm_id: str,
    parameters: Mapping[str, Any],
    roi: Mapping[str, Any],
    verdict: str,
    confidence: str,
    candidate_detected: bool | None,
    observations: Sequence[str] = (),
    limitations: Sequence[str] = (),
    claim_scope: str | None = None,
    analyzed_at: str | None = None,
) -> dict[str, Any]:
    """Create one immutable post-capture analysis record.

    The capture sidecar is deep-validated first through the capture evidence
    validator.  The action JSON and JPEG are then byte-bound in this record.
    """

    capture_sidecar_path = Path(capture_sidecar_path)
    analysis_path = Path(analysis_path)
    fd = _reserve_output(analysis_path)
    try:
        capture_payload, capture_root, capture_integrity = _load_validated_capture(
            capture_sidecar_path
        )
        ordinal = capture_root.get("ordinal")
        if type(ordinal) is not int or ordinal < 1 or ordinal > 99:
            raise PostCaptureAnalysisError("capture ordinal must be in range 1..99")
        expected_name = f"camera-action-{ordinal:02d}.analysis.json"
        if analysis_path.name != expected_name:
            raise PostCaptureAnalysisError(f"analysis filename must be {expected_name}")
        source = _require_text(analysis_source, label="analysis_source")
        model_id = _require_text(model_or_algorithm_id, label="model_or_algorithm_id")
        clean_parameters = _normalise_object(parameters, label="parameters")
        clean_roi = _normalise_object(roi, label="roi")
        coverage_root = _require_mapping(
            capture_root.get("coverage"), label="capture coverage"
        )
        capture_scope = _require_text(
            coverage_root.get("scope"), label="capture coverage.scope"
        )
        effective_claim_scope = claim_scope or _default_claim_scope(capture_scope)
        clean_observations, clean_limitations = _validate_assessment(
            capture_scope=capture_scope,
            claim_scope=effective_claim_scope,
            verdict=verdict,
            confidence=confidence,
            candidate_detected=candidate_detected,
            observations=observations,
            limitations=limitations,
        )
        timestamp = _require_timestamp(
            analyzed_at
            or datetime.now().astimezone().isoformat(timespec="milliseconds"),
            label="analyzed_at",
        )

        capture_action = _require_mapping(
            capture_root.get("action_result"), label="capture action_result"
        )
        action_path = _capture_relative_path(
            capture_action.get("path"),
            capture_sidecar_path=capture_sidecar_path,
            label="capture action_result.path",
        )
        action_payload = _read_stable_regular(action_path, label="action result")
        capture_photo = _require_mapping(
            capture_root.get("photo"), label="capture photo"
        )
        photo_path = _capture_relative_path(
            capture_photo.get("path"),
            capture_sidecar_path=capture_sidecar_path,
            label="capture photo.path",
        )
        photo_payload = _read_stable_regular(photo_path, label="photo")

        bindings = {
            "action_result": {
                "path": _relative_path(
                    action_path, record_path=analysis_path, label="action result"
                ),
                "bytes": len(action_payload),
                "file_sha256": _sha256_bytes(action_payload),
                "canonical_integrity_sha256": _require_sha256(
                    capture_action.get("canonical_integrity_sha256"),
                    label="capture action canonical integrity",
                ),
            },
            "capture_sidecar": {
                "path": _relative_path(
                    capture_sidecar_path,
                    record_path=analysis_path,
                    label="capture sidecar",
                ),
                "bytes": len(capture_payload),
                "file_sha256": _sha256_bytes(capture_payload),
                "canonical_integrity_sha256": capture_integrity,
                "capture_id": _require_sha256(
                    capture_root.get("capture_id"), label="capture_id"
                ),
                "capture_binding": _require_text(
                    capture_root.get("capture_binding"), label="capture_binding"
                ),
            },
            "photo": {
                "path": _relative_path(
                    photo_path, record_path=analysis_path, label="photo"
                ),
                "bytes": len(photo_payload),
                "sha256": _sha256_bytes(photo_payload),
            },
        }
        coverage = {
            "capture_scope": capture_scope,
            "claim_scope": effective_claim_scope,
            "full_panel_visible": coverage_root.get("full_panel_visible"),
            "mount_id": _require_text(
                coverage_root.get("mount_id"), label="capture coverage.mount_id"
            ),
        }
        analysis = {
            "analysis_source": source,
            "model_or_algorithm_id": model_id,
            "parameters": clean_parameters,
            "roi": clean_roi,
            "coverage": coverage,
            "verdict": verdict,
            "confidence": confidence,
            "candidate_detected": candidate_detected,
            "observations": clean_observations,
            "limitations": clean_limitations,
        }
        analysis_id = _canonical_sha256(
            {
                "action_id": capture_root.get("action_id"),
                "capture_id": capture_root.get("capture_id"),
                "capture_sidecar_file_sha256": bindings["capture_sidecar"][
                    "file_sha256"
                ],
                "photo_sha256": bindings["photo"]["sha256"],
                "analyzed_at": timestamp,
                "analysis": analysis,
            }
        )
        identity_fields = {
            key: capture_root.get(key)
            for key in (
                "campaign_id",
                "test_id",
                "contract_id",
                "firmware_sha256",
                "boot_nonce",
                "ordinal",
                "action_id",
                "descriptor_id",
                "role",
                "frame_sha256",
            )
        }
        record = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": KIND,
                "analysis_id": analysis_id,
                "analyzed_at": timestamp,
                **identity_fields,
                "bindings": bindings,
                "analysis": analysis,
                "output_write_contract": OUTPUT_WRITE_CONTRACT,
            }
        )
        payload = (
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        _write_reserved(fd, payload)
        os.close(fd)
        fd = -1
        return validate_post_capture_analysis(analysis_path)
    except Exception:
        if fd >= 0:
            os.close(fd)
        analysis_path.unlink(missing_ok=True)
        raise


def validate_post_capture_analysis(analysis_path: Path) -> dict[str, Any]:
    """Deep-validate one analysis and all of its immutable evidence bindings."""

    analysis_path = Path(analysis_path)
    _payload, root = _load_strict_json(analysis_path, label="analysis record")
    expected_keys = {
        "schema_version",
        "kind",
        "analysis_id",
        "analyzed_at",
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
        "bindings",
        "analysis",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_keys:
        raise PostCaptureAnalysisError("analysis top-level keys differ")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise PostCaptureAnalysisError("analysis schema identity differs")
    _verify_integrity(root, label="analysis record")
    if root.get("output_write_contract") != OUTPUT_WRITE_CONTRACT:
        raise PostCaptureAnalysisError("analysis output write contract differs")
    timestamp = _require_timestamp(root.get("analyzed_at"), label="analyzed_at")
    ordinal = root.get("ordinal")
    if type(ordinal) is not int or not 1 <= ordinal <= 99:
        raise PostCaptureAnalysisError("analysis ordinal must be in range 1..99")
    expected_name = f"camera-action-{ordinal:02d}.analysis.json"
    if analysis_path.name != expected_name:
        raise PostCaptureAnalysisError(f"analysis filename must be {expected_name}")

    bindings = _require_mapping(root.get("bindings"), label="bindings")
    if set(bindings) != {"action_result", "capture_sidecar", "photo"}:
        raise PostCaptureAnalysisError("analysis binding keys differ")
    capture_binding = _require_mapping(
        bindings.get("capture_sidecar"), label="bindings.capture_sidecar"
    )
    if set(capture_binding) != {
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "capture_id",
        "capture_binding",
    }:
        raise PostCaptureAnalysisError("capture_sidecar binding keys differ")
    capture_path = _resolve_path(
        capture_binding.get("path"),
        record_path=analysis_path,
        label="bindings.capture_sidecar.path",
    )
    capture_payload, capture_root, capture_integrity = _load_validated_capture(
        capture_path
    )
    capture_comparisons = {
        "bytes": len(capture_payload),
        "file_sha256": _sha256_bytes(capture_payload),
        "canonical_integrity_sha256": capture_integrity,
        "capture_id": capture_root.get("capture_id"),
        "capture_binding": capture_root.get("capture_binding"),
    }
    for field, expected in capture_comparisons.items():
        if capture_binding.get(field) != expected:
            raise PostCaptureAnalysisError(f"capture_sidecar binding {field} differs")

    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if root.get(field) != capture_root.get(field):
            raise PostCaptureAnalysisError(f"analysis {field} differs from capture")

    capture_action = _require_mapping(
        capture_root.get("action_result"), label="capture action_result"
    )
    expected_action_path = _capture_relative_path(
        capture_action.get("path"),
        capture_sidecar_path=capture_path,
        label="capture action_result.path",
    )
    action_binding = _require_mapping(
        bindings.get("action_result"), label="bindings.action_result"
    )
    if set(action_binding) != {
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
    }:
        raise PostCaptureAnalysisError("action_result binding keys differ")
    bound_action_path = _resolve_path(
        action_binding.get("path"),
        record_path=analysis_path,
        label="bindings.action_result.path",
    )
    if bound_action_path != expected_action_path:
        raise PostCaptureAnalysisError(
            "action_result binding path differs from capture"
        )
    action_payload = _read_stable_regular(bound_action_path, label="action result")
    action_comparisons = {
        "bytes": len(action_payload),
        "file_sha256": _sha256_bytes(action_payload),
        "canonical_integrity_sha256": capture_action.get("canonical_integrity_sha256"),
    }
    for field, expected in action_comparisons.items():
        if action_binding.get(field) != expected:
            raise PostCaptureAnalysisError(f"action_result binding {field} differs")

    capture_photo = _require_mapping(capture_root.get("photo"), label="capture photo")
    expected_photo_path = _capture_relative_path(
        capture_photo.get("path"),
        capture_sidecar_path=capture_path,
        label="capture photo.path",
    )
    photo_binding = _require_mapping(bindings.get("photo"), label="bindings.photo")
    if set(photo_binding) != {"path", "bytes", "sha256"}:
        raise PostCaptureAnalysisError("photo binding keys differ")
    bound_photo_path = _resolve_path(
        photo_binding.get("path"),
        record_path=analysis_path,
        label="bindings.photo.path",
    )
    if bound_photo_path != expected_photo_path:
        raise PostCaptureAnalysisError("photo binding path differs from capture")
    photo_payload = _read_stable_regular(bound_photo_path, label="photo")
    photo_comparisons = {
        "bytes": len(photo_payload),
        "sha256": _sha256_bytes(photo_payload),
    }
    for field, expected in photo_comparisons.items():
        if photo_binding.get(field) != expected or expected != capture_photo.get(field):
            raise PostCaptureAnalysisError(f"photo binding {field} differs")

    analysis = _require_mapping(root.get("analysis"), label="analysis")
    if set(analysis) != {
        "analysis_source",
        "model_or_algorithm_id",
        "parameters",
        "roi",
        "coverage",
        "verdict",
        "confidence",
        "candidate_detected",
        "observations",
        "limitations",
    }:
        raise PostCaptureAnalysisError("analysis detail keys differ")
    _require_text(analysis.get("analysis_source"), label="analysis_source")
    _require_text(analysis.get("model_or_algorithm_id"), label="model_or_algorithm_id")
    parameters = _normalise_object(
        _require_mapping(analysis.get("parameters"), label="parameters"),
        label="parameters",
    )
    roi = _normalise_object(
        _require_mapping(analysis.get("roi"), label="roi"), label="roi"
    )
    if analysis.get("parameters") != parameters or analysis.get("roi") != roi:
        raise PostCaptureAnalysisError("parameters or roi are not canonical objects")
    coverage = _require_mapping(analysis.get("coverage"), label="analysis.coverage")
    if set(coverage) != {
        "capture_scope",
        "claim_scope",
        "full_panel_visible",
        "mount_id",
    }:
        raise PostCaptureAnalysisError("analysis coverage keys differ")
    capture_coverage = _require_mapping(
        capture_root.get("coverage"), label="capture coverage"
    )
    expected_coverage = {
        "capture_scope": capture_coverage.get("scope"),
        "claim_scope": coverage.get("claim_scope"),
        "full_panel_visible": capture_coverage.get("full_panel_visible"),
        "mount_id": capture_coverage.get("mount_id"),
    }
    if dict(coverage) != expected_coverage:
        raise PostCaptureAnalysisError("analysis coverage differs from capture")
    observations = analysis.get("observations")
    limitations = analysis.get("limitations")
    if not isinstance(observations, list) or not isinstance(limitations, list):
        raise PostCaptureAnalysisError(
            "analysis observations and limitations must be arrays"
        )
    clean_observations, clean_limitations = _validate_assessment(
        capture_scope=coverage.get("capture_scope"),
        claim_scope=coverage.get("claim_scope"),
        verdict=analysis.get("verdict"),
        confidence=analysis.get("confidence"),
        candidate_detected=analysis.get("candidate_detected"),
        observations=observations,
        limitations=limitations,
    )
    if observations != clean_observations or limitations != clean_limitations:
        raise PostCaptureAnalysisError("analysis text arrays differ")

    expected_id = _canonical_sha256(
        {
            "action_id": capture_root.get("action_id"),
            "capture_id": capture_root.get("capture_id"),
            "capture_sidecar_file_sha256": capture_binding["file_sha256"],
            "photo_sha256": photo_binding["sha256"],
            "analyzed_at": timestamp,
            "analysis": dict(analysis),
        }
    )
    if root.get("analysis_id") != expected_id:
        raise PostCaptureAnalysisError("analysis_id differs")
    return dict(root)


def describe_schema() -> dict[str, Any]:
    """Return the static schema contract without touching the filesystem."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "output_filename": "camera-action-NN.analysis.json",
        "output_write_contract": OUTPUT_WRITE_CONTRACT,
        "verdicts": sorted(VERDICTS),
        "confidences": sorted(CONFIDENCES),
        "capture_scopes": sorted(CAPTURE_SCOPES),
        "claim_scopes": sorted(CLAIM_SCOPES),
        "constraints": [
            "partial_panel cannot claim full_panel",
            "low confidence must be INCONCLUSIVE",
            "high-confidence PASS candidate requires full_panel capture and claim",
            "PASS/FAIL/INCONCLUSIVE maps to candidate_detected true/false/null",
            "create never overwrites action, capture, photo, or analysis evidence",
        ],
    }


def _json_object(text: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            f"{label} is not strict JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError(f"{label} must be a JSON object")
    return value


def _candidate_value(text: str) -> bool | None:
    values: dict[str, bool | None] = {"true": True, "false": False, "null": None}
    try:
        return values[text.lower()]
    except KeyError as error:
        raise argparse.ArgumentTypeError(
            "candidate must be true, false, or null"
        ) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create one immutable analysis")
    create.add_argument("--capture-sidecar", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--analysis-source", required=True)
    create.add_argument("--model-or-algorithm-id", required=True)
    create.add_argument(
        "--parameters-json",
        type=lambda text: _json_object(text, label="parameters"),
        default={},
    )
    create.add_argument(
        "--roi-json",
        type=lambda text: _json_object(text, label="roi"),
        default={"kind": "entire_captured_frame"},
    )
    create.add_argument("--claim-scope", choices=tuple(sorted(CLAIM_SCOPES)))
    create.add_argument("--verdict", choices=tuple(sorted(VERDICTS)), required=True)
    create.add_argument(
        "--confidence", choices=tuple(sorted(CONFIDENCES)), required=True
    )
    create.add_argument("--candidate-detected", type=_candidate_value, required=True)
    create.add_argument("--observation", action="append", default=[])
    create.add_argument("--limitation", action="append", default=[])
    create.add_argument("--analyzed-at")
    validate = commands.add_parser("validate", help="deep-validate one analysis")
    validate.add_argument("analysis", type=Path)
    commands.add_parser("describe", help="describe the offline analysis schema")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            result = describe_schema()
        elif args.command == "validate":
            result = validate_post_capture_analysis(args.analysis)
        else:
            result = create_post_capture_analysis(
                capture_sidecar_path=args.capture_sidecar,
                analysis_path=args.output,
                analysis_source=args.analysis_source,
                model_or_algorithm_id=args.model_or_algorithm_id,
                parameters=args.parameters_json,
                roi=args.roi_json,
                claim_scope=args.claim_scope,
                verdict=args.verdict,
                confidence=args.confidence,
                candidate_detected=args.candidate_detected,
                observations=args.observation,
                limitations=args.limitation,
                analyzed_at=args.analyzed_at,
            )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    except PostCaptureAnalysisError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": ERROR_KIND,
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=os.sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
