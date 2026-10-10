#!/usr/bin/env python3
"""Build a deterministic, offline MF1750 live-session evidence report.

The report is a *derived view*.  Immutable action receipts and camera capture
sidecars remain the evidence of record.  This module never opens a camera,
serial port, relay, socket, or subprocess; importing it performs no I/O.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import quote


INDEX_NAME = "session-index.json"
REPORT_NAME = "SESSION_REPORT.md"
INDEX_KIND = "mf1750-live-session-derived-index"
CAPTURE_KIND = "mf1750-camera-capture-evidence"
CAPTURE_FAILURE_KIND = "mf1750-camera-capture-failure"
ANALYSIS_KIND = "mf1750-camera-post-capture-analysis"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACTION_FILE_RE = re.compile(r"^action-(\d{2})-.+\.json$")
CAPTURE_FILE_RE = re.compile(r"^camera-action-(\d{2})\.capture\.json$")
ANALYSIS_FILE_RE = re.compile(r"^camera-action-(\d{2})\.analysis\.json$")


class SessionReportError(RuntimeError):
    """Raised when immutable evidence or a derived report is inconsistent."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {token}")
            ),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise SessionReportError(f"cannot read strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise SessionReportError(f"JSON root must be an object: {path}")
    return value


def _validate_integrity(value: Mapping[str, Any], *, label: str) -> str:
    integrity = value.get("integrity")
    if not isinstance(integrity, dict):
        raise SessionReportError(f"{label} lacks integrity")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise SessionReportError(f"{label} integrity algorithm differs")
    observed = integrity.get("sha256")
    if not isinstance(observed, str) or SHA256_RE.fullmatch(observed) is None:
        raise SessionReportError(f"{label} integrity SHA-256 is malformed")
    unsigned = dict(value)
    unsigned.pop("integrity", None)
    expected = _canonical_sha256(unsigned)
    if observed != expected:
        raise SessionReportError(f"{label} canonical integrity differs")
    return observed


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _canonical_sha256(sealed),
    }
    return sealed


def _iso_with_timezone(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SessionReportError(f"{label} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SessionReportError(f"{label} is not an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SessionReportError(f"{label} must include a timezone")
    return value


def _required_string(value: Mapping[str, Any], key: str, *, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise SessionReportError(f"{label}.{key} must be a non-empty string")
    return result


def _required_sha(value: Mapping[str, Any], key: str, *, label: str) -> str:
    result = _required_string(value, key, label=label)
    if SHA256_RE.fullmatch(result) is None:
        raise SessionReportError(f"{label}.{key} is not a lowercase SHA-256")
    return result


def _relative_source_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise SessionReportError(
            f"source escapes campaign directory: {path}"
        ) from error


def _safe_sidecar_path(sidecar: Path, raw: Any, *, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise SessionReportError(f"{label} path must be a non-empty string")
    if "\\" in raw:
        raise SessionReportError(f"{label} path must use POSIX separators")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts:
        raise SessionReportError(f"{label} path escapes the sidecar directory")
    base = sidecar.parent.resolve()
    candidate = (base / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise SessionReportError(
            f"{label} path escapes the sidecar directory"
        ) from error
    if candidate.is_symlink() or not candidate.is_file():
        raise SessionReportError(f"{label} is not an ordinary existing file")
    return candidate


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise SessionReportError(f"photo is not a complete JPEG: {path}")
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    offset = 2
    while offset + 4 <= len(data):
        while offset < len(data) and data[offset] != 0xFF:
            offset += 1
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise SessionReportError(f"photo has a malformed JPEG segment: {path}")
        if marker in sof_markers:
            if length < 8:
                raise SessionReportError(f"photo has a malformed JPEG SOF: {path}")
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            if width <= 0 or height <= 0:
                raise SessionReportError(f"photo dimensions are invalid: {path}")
            return width, height
        offset += length
    raise SessionReportError(f"photo JPEG dimensions were not found: {path}")


def _manifest_from_action(action: Mapping[str, Any]) -> dict[str, Any]:
    transcript = action.get("transcript")
    if not isinstance(transcript, list):
        raise SessionReportError("action transcript must be a list")
    manifests = [
        item.get("response")
        for item in transcript
        if isinstance(item, dict) and item.get("endpoint") == "manifest"
    ]
    if len(manifests) != 1 or not isinstance(manifests[0], dict):
        raise SessionReportError("action must contain exactly one manifest response")
    return manifests[0]


def _network_counts(value: Mapping[str, Any]) -> dict[str, int]:
    network = value.get("network")
    if not isinstance(network, dict):
        raise SessionReportError("action network counts are missing")
    result: dict[str, int] = {}
    for key in ("get", "arm_post", "execute_post"):
        count = network.get(key, 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise SessionReportError(f"action network.{key} is invalid")
        result[key] = count
    return result


def _load_actions(campaign_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files = sorted(
        path
        for path in campaign_dir.iterdir()
        if path.is_file() and ACTION_FILE_RE.fullmatch(path.name)
    )
    if not files:
        raise SessionReportError("campaign contains no immutable action JSON")

    loaded: list[dict[str, Any]] = []
    reference_manifest: dict[str, Any] | None = None
    seen_ordinals: set[int] = set()
    identity: dict[str, str] | None = None
    for path in files:
        filename_match = ACTION_FILE_RE.fullmatch(path.name)
        assert filename_match is not None
        filename_ordinal = int(filename_match.group(1))
        value = _strict_json(path)
        canonical_integrity = _validate_integrity(value, label=path.name)
        action = value.get("action")
        terminal = value.get("terminal_report")
        if not isinstance(action, dict) or not isinstance(terminal, dict):
            raise SessionReportError(f"{path.name} lacks action or terminal_report")
        ordinal = action.get("ordinal")
        if ordinal != filename_ordinal or not isinstance(ordinal, int):
            raise SessionReportError(f"{path.name} ordinal differs from filename")
        if ordinal in seen_ordinals:
            raise SessionReportError(f"duplicate action ordinal {ordinal}")
        seen_ordinals.add(ordinal)
        manifest = _manifest_from_action(value)
        if reference_manifest is None:
            reference_manifest = manifest
        elif manifest != reference_manifest:
            raise SessionReportError("manifest changed between immutable actions")
        current_identity = {
            "campaign_id": _required_string(terminal, "campaign_id", label=path.name),
            "test_id": _required_string(terminal, "test_id", label=path.name),
            "contract_id": _required_sha(terminal, "contract_id", label=path.name),
            "build_tag": _required_string(terminal, "build_tag", label=path.name),
            "firmware_sha256": _required_sha(value, "firmware_sha256", label=path.name),
            "boot_nonce": _required_string(value, "boot_nonce", label=path.name),
        }
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise SessionReportError(
                "contract/firmware/boot identity changed between actions"
            )
        for key in ("ordinal", "action_id", "descriptor_id", "role"):
            if terminal.get(key) != action.get(key):
                raise SessionReportError(f"{path.name} terminal {key} differs")
        if terminal.get("boot_nonce") != current_identity["boot_nonce"]:
            raise SessionReportError(f"{path.name} terminal boot nonce differs")
        if value.get("visible_refreshes") != terminal.get(
            "driver_call_count_for_action"
        ):
            raise SessionReportError(f"{path.name} visible/driver count differs")
        network = _network_counts(value)
        driver = terminal.get("driver")
        if driver is not None and not isinstance(driver, dict):
            raise SessionReportError(f"{path.name} driver evidence is invalid")
        loaded.append(
            {
                "path": path,
                "value": value,
                "ordinal": ordinal,
                "action": action,
                "terminal": terminal,
                "file_bytes": path.stat().st_size,
                "file_sha256": _file_sha256(path),
                "canonical_integrity_sha256": canonical_integrity,
                "network": network,
            }
        )

    assert reference_manifest is not None and identity is not None
    actions = reference_manifest.get("actions")
    action_count = reference_manifest.get("action_count")
    if not isinstance(actions, list) or action_count != len(actions) or not actions:
        raise SessionReportError("manifest action list/count is invalid")
    expected_ordinals = [
        item.get("ordinal") for item in actions if isinstance(item, dict)
    ]
    if expected_ordinals != list(range(1, len(actions) + 1)):
        raise SessionReportError("manifest ordinals are not contiguous from one")
    manifest_identity = {
        key: reference_manifest.get(key)
        for key in ("campaign_id", "test_id", "contract_id", "build_tag")
    }
    if manifest_identity != {key: identity[key] for key in manifest_identity}:
        raise SessionReportError("manifest identity differs from action identity")
    for item in loaded:
        descriptor = actions[item["ordinal"] - 1]
        for key in (
            "ordinal",
            "action_id",
            "descriptor_id",
            "role",
            "frame_sha256",
            "palette_source",
            "global_header",
        ):
            if item["action"].get(key) != descriptor.get(key):
                raise SessionReportError(
                    f"action {item['ordinal']} differs from manifest field {key}"
                )
    loaded.sort(key=lambda item: item["ordinal"])
    if [item["ordinal"] for item in loaded] != list(range(1, len(loaded) + 1)):
        raise SessionReportError("recorded action ordinals contain a gap")
    return loaded, reference_manifest


def _capture_action_result(value: Mapping[str, Any]) -> Mapping[str, Any]:
    result = value.get("action_result")
    if isinstance(result, dict):
        return result
    legacy = value.get("action_evidence")
    if isinstance(legacy, dict):
        return {
            "path": legacy.get("path"),
            "bytes": legacy.get("bytes"),
            "file_sha256": legacy.get("file_sha256", legacy.get("sha256")),
            "canonical_integrity_sha256": legacy.get("canonical_integrity_sha256"),
            "outcome": value.get("action_outcome"),
            "terminal_state": value.get("action_terminal_state"),
            "visible_refreshes": value.get("visible_refreshes"),
        }
    raise SessionReportError("capture sidecar lacks action_result")


def _load_captures(
    campaign_dir: Path,
    actions: Sequence[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    by_ordinal = {item["ordinal"]: item for item in actions}
    result: dict[int, dict[str, Any]] = {}
    files = sorted(
        path
        for path in campaign_dir.iterdir()
        if path.is_file() and CAPTURE_FILE_RE.fullmatch(path.name)
    )
    for path in files:
        match = CAPTURE_FILE_RE.fullmatch(path.name)
        assert match is not None
        filename_ordinal = int(match.group(1))
        value = _strict_json(path)
        canonical_integrity = _validate_integrity(value, label=path.name)
        kind = value.get("kind")
        if value.get("schema_version") not in {1, 2} or kind not in {
            CAPTURE_KIND,
            CAPTURE_FAILURE_KIND,
        }:
            raise SessionReportError(f"{path.name} capture schema/kind differs")
        if kind == CAPTURE_KIND:
            # Import is deliberately inside the explicit filesystem operation.
            # The capture module itself promises import-time zero I/O, and its
            # validator is the authoritative exact-schema/JPEG decoder.
            if __package__:
                from tools.mf1750_camera_capture_evidence import (
                    CameraCaptureEvidenceError,
                    validate_capture_evidence,
                )
            else:  # Direct ``python tools/<script>.py`` execution.
                from mf1750_camera_capture_evidence import (  # type: ignore[no-redef]
                    CameraCaptureEvidenceError,
                    validate_capture_evidence,
                )

            try:
                deeply_validated = validate_capture_evidence(path)
            except CameraCaptureEvidenceError as error:
                raise SessionReportError(
                    f"{path.name} deep capture validation failed: {error}"
                ) from error
            if deeply_validated != value:
                raise SessionReportError(
                    f"{path.name} deep capture validator changed evidence"
                )
        ordinal = value.get("ordinal")
        if ordinal != filename_ordinal or not isinstance(ordinal, int):
            raise SessionReportError(f"{path.name} ordinal differs from filename")
        if ordinal in result:
            raise SessionReportError(f"duplicate capture ordinal {ordinal}")
        source = by_ordinal.get(ordinal)
        if source is None:
            raise SessionReportError(
                f"capture ordinal {ordinal} has no action evidence"
            )
        action = source["action"]
        terminal = source["terminal"]
        bindings = {
            "campaign_id": terminal["campaign_id"],
            "test_id": terminal["test_id"],
            "contract_id": terminal["contract_id"],
            "firmware_sha256": source["value"]["firmware_sha256"],
            "boot_nonce": source["value"]["boot_nonce"],
            "ordinal": ordinal,
            "action_id": action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "role": action["role"],
            "frame_sha256": action["frame_sha256"],
        }
        for key, expected in bindings.items():
            observed = value.get(key)
            if (
                observed is None
                and kind == CAPTURE_FAILURE_KIND
                and key
                in {
                    "test_id",
                    "firmware_sha256",
                    "descriptor_id",
                    "role",
                    "frame_sha256",
                }
            ):
                continue
            if observed != expected:
                raise SessionReportError(f"{path.name} {key} differs from action")
        action_result = _capture_action_result(value)
        action_path = _safe_sidecar_path(
            path, action_result.get("path"), label=f"{path.name} action_result"
        )
        if action_path != source["path"].resolve():
            raise SessionReportError(f"{path.name} references the wrong action file")
        expected_action_fields = {
            "bytes": source["file_bytes"],
            "file_sha256": source["file_sha256"],
            "canonical_integrity_sha256": source["canonical_integrity_sha256"],
            "outcome": source["value"].get("outcome"),
            "terminal_state": terminal.get("terminal_state"),
            "visible_refreshes": source["value"].get("visible_refreshes"),
        }
        for key, expected in expected_action_fields.items():
            observed = action_result.get(key)
            if observed is None and kind == CAPTURE_FAILURE_KIND:
                continue
            if observed != expected:
                raise SessionReportError(
                    f"{path.name} action_result.{key} differs from action"
                )

        coverage = value.get("coverage")
        assessment = value.get("automated_assessment")
        camera = value.get("camera")
        if not isinstance(coverage, dict) or not isinstance(assessment, dict):
            raise SessionReportError(f"{path.name} lacks coverage/assessment")
        if not isinstance(camera, dict):
            raise SessionReportError(f"{path.name} lacks camera metadata")
        full_visible = coverage.get("full_panel_visible") is True
        full_uncropped = coverage.get("full_panel_uncropped") is True
        scope = coverage.get("scope")
        supplied_verdict = assessment.get("verdict")
        confidence = assessment.get("confidence")
        limitations = assessment.get("limitations")
        if supplied_verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise SessionReportError(f"{path.name} automated verdict is invalid")
        if confidence not in {"low", "medium", "high"}:
            raise SessionReportError(f"{path.name} confidence is invalid")
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) and item for item in limitations
        ):
            raise SessionReportError(f"{path.name} limitations are invalid")
        effective_verdict = supplied_verdict
        effective_limitations = list(limitations)
        if (
            kind == CAPTURE_FAILURE_KIND
            or scope != "full_panel"
            or not full_visible
            or not full_uncropped
            or confidence == "low"
        ):
            effective_verdict = "INCONCLUSIVE"
            reason = "partial_or_low_confidence_capture_cannot_prove_full_panel"
            if reason not in effective_limitations:
                effective_limitations.append(reason)

        photo_summary: dict[str, Any] | None = None
        photo = value.get("photo")
        if kind == CAPTURE_KIND:
            if not isinstance(photo, dict):
                raise SessionReportError(f"{path.name} success lacks photo")
            photo_path = _safe_sidecar_path(
                path, photo.get("path"), label=f"{path.name} photo"
            )
            observed_bytes = photo_path.stat().st_size
            observed_sha = _file_sha256(photo_path)
            width, height = _jpeg_dimensions(photo_path)
            if photo.get("bytes") != observed_bytes:
                raise SessionReportError(f"{path.name} photo bytes differ")
            if photo.get("sha256") != observed_sha:
                raise SessionReportError(f"{path.name} photo SHA-256 differs")
            if photo.get("width") != width or photo.get("height") != height:
                raise SessionReportError(f"{path.name} photo dimensions differ")
            if photo.get("decoded_format") != "JPEG":
                raise SessionReportError(f"{path.name} decoded photo format differs")
            photo_summary = {
                "path": _relative_source_path(photo_path, campaign_dir),
                "bytes": observed_bytes,
                "sha256": observed_sha,
                "width": width,
                "height": height,
                "decoded_format": "JPEG",
                "mode": photo.get("mode"),
                "quality_metrics": photo.get("quality_metrics"),
            }
            _iso_with_timezone(
                _required_string(value, "captured_at", label=path.name),
                label=f"{path.name}.captured_at",
            )
        else:
            if photo is not None:
                raise SessionReportError(f"{path.name} failure must have photo=null")
            if value.get("action_consumed") is not True:
                raise SessionReportError(
                    f"{path.name} failure must preserve consumed action"
                )
            if value.get("action_must_not_be_retried") is not True:
                raise SessionReportError(f"{path.name} failure must forbid retry")

        result[ordinal] = {
            "path": _relative_source_path(path, campaign_dir),
            "file_bytes": path.stat().st_size,
            "file_sha256": _file_sha256(path),
            "canonical_integrity_sha256": canonical_integrity,
            "kind": kind,
            "capture_id": value.get("capture_id"),
            "capture_binding": value.get("capture_binding"),
            "captured_at": value.get("captured_at", value.get("created_at")),
            "camera": camera,
            "coverage": coverage,
            "automated_assessment": {
                "supplied_verdict": supplied_verdict,
                "effective_verdict": effective_verdict,
                "confidence": confidence,
                "limitations": effective_limitations,
                "full_panel_pass_claimed": (
                    effective_verdict == "PASS"
                    and full_visible
                    and full_uncropped
                    and scope == "full_panel"
                ),
            },
            "photo": photo_summary,
            "capture_error": value.get("capture_error"),
        }
    return result


def _capture_supports_full_panel_analysis(capture: Mapping[str, Any]) -> bool:
    coverage = capture.get("coverage")
    return bool(
        capture.get("kind") == CAPTURE_KIND
        and capture.get("capture_binding") == "live_synchronized"
        and isinstance(coverage, dict)
        and coverage.get("scope") == "full_panel"
        and coverage.get("full_panel_visible") is True
        and coverage.get("full_panel_uncropped") is True
        and capture.get("photo") is not None
    )


def _validate_analysis_with_available_module(
    path: Path, value: Mapping[str, Any]
) -> None:
    """Use the authoritative post-analysis validator when it is installed.

    The fallback below deliberately validates the planned v1 contract so the
    report module remains importable while the optional analysis producer is
    not installed.  A present producer is always authoritative.
    """

    validator: Any | None = None
    validator_error: type[BaseException] = RuntimeError
    try:
        if __package__:
            from tools.mf1750_camera_post_capture_analysis import (
                PostCaptureAnalysisError,
                validate_post_capture_analysis,
            )
        else:  # Direct ``python tools/<script>.py`` execution.
            from mf1750_camera_post_capture_analysis import (  # type: ignore[no-redef]
                PostCaptureAnalysisError,
                validate_post_capture_analysis,
            )
    except ModuleNotFoundError as error:
        expected_names = {
            "tools.mf1750_camera_post_capture_analysis",
            "mf1750_camera_post_capture_analysis",
        }
        if error.name not in expected_names:
            raise
    else:
        validator = validate_post_capture_analysis
        validator_error = PostCaptureAnalysisError

    if validator is not None:
        try:
            deeply_validated = validator(path)
        except validator_error as error:
            raise SessionReportError(
                f"{path.name} deep post-analysis validation failed: {error}"
            ) from error
        if deeply_validated != value:
            raise SessionReportError(
                f"{path.name} deep post-analysis validator changed evidence"
            )
        return

    required_root = {
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
    if set(value) != required_root:
        raise SessionReportError(f"{path.name} post-analysis root keys differ")
    bindings = value.get("bindings")
    analysis = value.get("analysis")
    if not isinstance(bindings, dict) or set(bindings) != {
        "action_result",
        "capture_sidecar",
        "photo",
    }:
        raise SessionReportError(f"{path.name} post-analysis bindings differ")
    if not isinstance(analysis, dict):
        raise SessionReportError(f"{path.name} post-analysis payload is invalid")
    binding_key_sets = {
        "action_result": {
            "path",
            "bytes",
            "file_sha256",
            "canonical_integrity_sha256",
        },
        "capture_sidecar": {
            "path",
            "bytes",
            "file_sha256",
            "canonical_integrity_sha256",
            "capture_id",
            "capture_binding",
        },
        "photo": {"path", "bytes", "sha256"},
    }
    for name, expected in binding_key_sets.items():
        binding = bindings.get(name)
        if not isinstance(binding, dict) or set(binding) != expected:
            raise SessionReportError(
                f"{path.name} post-analysis {name} binding keys differ"
            )
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
        raise SessionReportError(f"{path.name} post-analysis detail keys differ")
    coverage = analysis.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != {
        "capture_scope",
        "claim_scope",
        "full_panel_visible",
        "mount_id",
    }:
        raise SessionReportError(f"{path.name} post-analysis coverage keys differ")


def _analysis_binding(
    path: Path,
    binding: Any,
    *,
    expected_path: Path,
    expected_fields: Mapping[str, Any],
    label: str,
) -> None:
    if not isinstance(binding, dict):
        raise SessionReportError(f"{path.name} {label} binding is invalid")
    bound_path = _safe_sidecar_path(
        path, binding.get("path"), label=f"{path.name} {label}"
    )
    if bound_path != expected_path.resolve():
        raise SessionReportError(f"{path.name} {label} references the wrong file")
    for key, expected in expected_fields.items():
        if binding.get(key) != expected:
            raise SessionReportError(f"{path.name} {label}.{key} differs")


def _load_analyses(
    campaign_dir: Path,
    actions: Sequence[dict[str, Any]],
    captures: Mapping[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    by_ordinal = {item["ordinal"]: item for item in actions}
    result: dict[int, dict[str, Any]] = {}
    files = sorted(
        path
        for path in campaign_dir.iterdir()
        if path.is_file() and ANALYSIS_FILE_RE.fullmatch(path.name)
    )
    for path in files:
        match = ANALYSIS_FILE_RE.fullmatch(path.name)
        assert match is not None
        filename_ordinal = int(match.group(1))
        value = _strict_json(path)
        canonical_integrity = _validate_integrity(value, label=path.name)
        if value.get("schema_version") != 1 or value.get("kind") != ANALYSIS_KIND:
            raise SessionReportError(f"{path.name} post-analysis schema/kind differs")
        _validate_analysis_with_available_module(path, value)
        _required_sha(value, "analysis_id", label=path.name)

        ordinal = value.get("ordinal")
        if ordinal != filename_ordinal or not isinstance(ordinal, int):
            raise SessionReportError(f"{path.name} ordinal differs from filename")
        if ordinal in result:
            raise SessionReportError(f"duplicate post-analysis ordinal {ordinal}")
        source = by_ordinal.get(ordinal)
        capture = captures.get(ordinal)
        if source is None or capture is None:
            raise SessionReportError(
                f"post-analysis ordinal {ordinal} lacks bound action/capture evidence"
            )
        if capture["kind"] != CAPTURE_KIND or capture["photo"] is None:
            raise SessionReportError(
                f"post-analysis ordinal {ordinal} cannot bind a failed capture"
            )

        action = source["action"]
        terminal = source["terminal"]
        identity_bindings = {
            "campaign_id": terminal["campaign_id"],
            "test_id": terminal["test_id"],
            "contract_id": terminal["contract_id"],
            "firmware_sha256": source["value"]["firmware_sha256"],
            "boot_nonce": source["value"]["boot_nonce"],
            "ordinal": ordinal,
            "action_id": action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "role": action["role"],
            "frame_sha256": action["frame_sha256"],
        }
        for key, expected in identity_bindings.items():
            if value.get(key) != expected:
                raise SessionReportError(f"{path.name} {key} differs from action")

        bindings = value.get("bindings")
        if not isinstance(bindings, dict):
            raise SessionReportError(f"{path.name} lacks bindings")
        _analysis_binding(
            path,
            bindings.get("action_result"),
            expected_path=source["path"],
            expected_fields={
                "bytes": source["file_bytes"],
                "file_sha256": source["file_sha256"],
                "canonical_integrity_sha256": source["canonical_integrity_sha256"],
            },
            label="bindings.action_result",
        )
        capture_path = campaign_dir / capture["path"]
        _analysis_binding(
            path,
            bindings.get("capture_sidecar"),
            expected_path=capture_path,
            expected_fields={
                "bytes": capture["file_bytes"],
                "file_sha256": capture["file_sha256"],
                "canonical_integrity_sha256": capture["canonical_integrity_sha256"],
                "capture_id": capture["capture_id"],
                "capture_binding": capture["capture_binding"],
            },
            label="bindings.capture_sidecar",
        )
        photo = capture["photo"]
        assert photo is not None
        photo_path = campaign_dir / photo["path"]
        _analysis_binding(
            path,
            bindings.get("photo"),
            expected_path=photo_path,
            expected_fields={
                "bytes": photo["bytes"],
                "sha256": photo["sha256"],
            },
            label="bindings.photo",
        )

        analysis = value.get("analysis")
        if not isinstance(analysis, dict):
            raise SessionReportError(f"{path.name} lacks analysis")
        analysis_source = analysis.get("analysis_source")
        model_or_algorithm_id = analysis.get("model_or_algorithm_id")
        verdict = analysis.get("verdict")
        confidence = analysis.get("confidence")
        candidate_detected = analysis.get("candidate_detected")
        observations = analysis.get("observations")
        limitations = analysis.get("limitations")
        coverage = analysis.get("coverage")
        if not isinstance(analysis_source, str) or not analysis_source:
            raise SessionReportError(f"{path.name} analysis_source is invalid")
        if not isinstance(model_or_algorithm_id, str) or not model_or_algorithm_id:
            raise SessionReportError(f"{path.name} model_or_algorithm_id is invalid")
        if verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise SessionReportError(f"{path.name} analysis verdict is invalid")
        if confidence not in {"low", "medium", "high"}:
            raise SessionReportError(f"{path.name} analysis confidence is invalid")
        if candidate_detected is not None and not isinstance(candidate_detected, bool):
            raise SessionReportError(f"{path.name} candidate_detected is invalid")
        expected_candidate = (
            True if verdict == "PASS" else False if verdict == "FAIL" else None
        )
        if candidate_detected is not expected_candidate:
            raise SessionReportError(
                f"{path.name} candidate_detected differs from verdict"
            )
        for name, items in (
            ("observations", observations),
            ("limitations", limitations),
        ):
            if not isinstance(items, list) or not all(
                isinstance(item, str) and item for item in items
            ):
                raise SessionReportError(f"{path.name} {name} are invalid")
        if confidence == "low" and verdict != "INCONCLUSIVE":
            raise SessionReportError(
                f"{path.name} low-confidence analysis must be INCONCLUSIVE"
            )
        if verdict != "INCONCLUSIVE" and not observations:
            raise SessionReportError(
                f"{path.name} conclusive analysis lacks observations"
            )
        if not isinstance(coverage, dict):
            raise SessionReportError(f"{path.name} analysis coverage is invalid")
        capture_scope = coverage.get("capture_scope")
        claim_scope = coverage.get("claim_scope")
        if capture_scope not in {"partial_panel", "full_panel"}:
            raise SessionReportError(f"{path.name} capture_scope is invalid")
        if claim_scope not in {"visible_roi", "full_panel"}:
            raise SessionReportError(f"{path.name} claim_scope is invalid")
        if capture_scope == "partial_panel" and claim_scope == "full_panel":
            raise SessionReportError(
                f"{path.name} partial capture cannot claim full panel"
            )
        if not isinstance(coverage.get("full_panel_visible"), bool):
            raise SessionReportError(f"{path.name} full_panel_visible must be boolean")
        full_panel_visible = coverage.get("full_panel_visible") is True
        if capture_scope != capture["coverage"].get("scope"):
            raise SessionReportError(
                f"{path.name} analysis coverage differs from capture scope"
            )
        if full_panel_visible != (
            capture["coverage"].get("full_panel_visible") is True
        ):
            raise SessionReportError(
                f"{path.name} analysis full-panel visibility differs from capture"
            )
        if coverage.get("mount_id") != capture["coverage"].get("mount_id"):
            raise SessionReportError(
                f"{path.name} analysis mount_id differs from capture"
            )

        effective_verdict = verdict
        effective_limitations = list(limitations)
        capture_full = _capture_supports_full_panel_analysis(capture)
        if not capture_full or claim_scope != "full_panel" or confidence == "low":
            effective_verdict = "INCONCLUSIVE"
            reason = "partial_or_low_confidence_analysis_cannot_prove_full_panel"
            if reason not in effective_limitations:
                effective_limitations.append(reason)

        _iso_with_timezone(
            _required_string(value, "analyzed_at", label=path.name),
            label=f"{path.name}.analyzed_at",
        )
        result[ordinal] = {
            "path": _relative_source_path(path, campaign_dir),
            "file_bytes": path.stat().st_size,
            "file_sha256": _file_sha256(path),
            "canonical_integrity_sha256": canonical_integrity,
            "analysis_id": value.get("analysis_id"),
            "analyzed_at": value.get("analyzed_at"),
            "analysis_source": analysis_source,
            "model_or_algorithm_id": model_or_algorithm_id,
            "parameters": analysis.get("parameters"),
            "roi": analysis.get("roi"),
            "coverage": coverage,
            "supplied_verdict": verdict,
            "effective_verdict": effective_verdict,
            "confidence": confidence,
            "candidate_detected": candidate_detected,
            "observations": list(observations),
            "limitations": effective_limitations,
            "full_panel_pass_claimed": (
                effective_verdict == "PASS"
                and capture_full
                and claim_scope == "full_panel"
            ),
        }
    return result


def _ancillary_artifacts(
    campaign_dir: Path, identity: Mapping[str, str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for kind, name in (
        ("single_app_boot_flash", "app-only-single-boot-flash.json"),
        ("j2_off_diagnostic", "j2-off-diagnostic.json"),
    ):
        path = campaign_dir / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise SessionReportError(
                f"ancillary evidence is not an ordinary file: {name}"
            )
        value = _strict_json(path)
        canonical = _validate_integrity(value, label=name)
        if kind == "j2_off_diagnostic":
            for key in ("campaign_id", "contract_id", "boot_nonce"):
                if value.get(key) != identity[key]:
                    raise SessionReportError(f"diagnostic {key} differs")
            local = value.get("local_artifact_binding")
            if isinstance(local, dict):
                observed_firmware = local.get(
                    "firmware_sha256", local.get("bin_sha256")
                )
                if (
                    observed_firmware is not None
                    and observed_firmware != identity["firmware_sha256"]
                ):
                    raise SessionReportError("diagnostic firmware SHA-256 differs")
        if kind == "single_app_boot_flash":
            binary = value.get("binary")
            if not isinstance(binary, dict):
                raise SessionReportError("flash evidence lacks binary binding")
            if binary.get("observed_sha256") != identity["firmware_sha256"]:
                raise SessionReportError("flash firmware SHA-256 differs")
        result.append(
            {
                "kind": kind,
                "path": name,
                "bytes": path.stat().st_size,
                "file_sha256": _file_sha256(path),
                "canonical_integrity_sha256": canonical,
                "outcome": value.get("outcome"),
            }
        )
    return result


def _action_summary(
    descriptor: Mapping[str, Any],
    source: dict[str, Any] | None,
    capture: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    ordinal = descriptor["ordinal"]
    if source is None:
        return {
            "ordinal": ordinal,
            "role": descriptor.get("role"),
            "palette_source": descriptor.get("palette_source"),
            "global_header": descriptor.get("global_header"),
            "action_id": descriptor.get("action_id"),
            "descriptor_id": descriptor.get("descriptor_id"),
            "frame_sha256": descriptor.get("frame_sha256"),
            "execution_state": "NOT_EXECUTED",
            "machine": None,
            "capture": None,
            "analysis": None,
            "automated_verdict": "INCONCLUSIVE",
            "verdict_source": "not_executed",
        }
    value = source["value"]
    terminal = source["terminal"]
    driver = terminal.get("driver") if isinstance(terminal.get("driver"), dict) else {}
    machine = {
        "path": source["path"].name,
        "bytes": source["file_bytes"],
        "file_sha256": source["file_sha256"],
        "canonical_integrity_sha256": source["canonical_integrity_sha256"],
        "outcome": value.get("outcome"),
        "terminal_state": terminal.get("terminal_state"),
        "driver_called": terminal.get("driver_called"),
        "driver_call_count_for_action": terminal.get("driver_call_count_for_action"),
        "visible_refreshes": value.get("visible_refreshes"),
        "network": source["network"],
        "no_retry": value.get("no_retry"),
        "no_recovery": value.get("no_recovery"),
        "no_autochain": value.get("no_autochain"),
        "driver": {
            "sequence_ok": driver.get("sequence_ok"),
            "wait_timeout": driver.get("wait_timeout"),
            "failure_stage": driver.get("failure_stage"),
            "timeout_stage": driver.get("timeout_stage"),
            "spi_hz": driver.get("spi_hz"),
            "pon_ms": driver.get("pon_ms"),
            "drf_ms": driver.get("drf_ms"),
            "pof_ms": driver.get("pof_ms"),
            "total_ms": driver.get("total_ms"),
            "safe_finish": driver.get("safe_finish"),
        },
    }
    machine_pass = (
        value.get("outcome") == "complete_pass"
        and terminal.get("terminal_state") == "COMPLETE"
        and terminal.get("result") is True
    )
    if not machine_pass:
        verdict = "FAIL"
        verdict_source = "machine_evidence"
    elif capture is None or analysis is None:
        verdict = "INCONCLUSIVE"
        verdict_source = (
            "missing_capture" if capture is None else "missing_post_capture_analysis"
        )
    else:
        verdict = analysis["effective_verdict"]
        verdict_source = "post_capture_analysis"
    return {
        "ordinal": ordinal,
        "role": descriptor.get("role"),
        "palette_source": descriptor.get("palette_source"),
        "global_header": descriptor.get("global_header"),
        "action_id": descriptor.get("action_id"),
        "descriptor_id": descriptor.get("descriptor_id"),
        "frame_sha256": descriptor.get("frame_sha256"),
        "execution_state": terminal.get("terminal_state", "RECORDED"),
        "machine": machine,
        "capture": capture,
        "analysis": analysis,
        "automated_verdict": verdict,
        "verdict_source": verdict_source,
    }


def _compile_session(campaign_dir: Path, *, generated_at: str) -> dict[str, Any]:
    campaign_dir = campaign_dir.resolve()
    if not campaign_dir.is_dir():
        raise SessionReportError(f"campaign directory is missing: {campaign_dir}")
    _iso_with_timezone(generated_at, label="generated_at")
    loaded_actions, manifest = _load_actions(campaign_dir)
    captures = _load_captures(campaign_dir, loaded_actions)
    analyses = _load_analyses(campaign_dir, loaded_actions, captures)
    first = loaded_actions[0]
    terminal = first["terminal"]
    identity = {
        "campaign_id": terminal["campaign_id"],
        "test_id": terminal["test_id"],
        "contract_id": terminal["contract_id"],
        "build_tag": terminal["build_tag"],
        "firmware_sha256": first["value"]["firmware_sha256"],
        "boot_nonce": first["value"]["boot_nonce"],
    }
    source_by_ordinal = {item["ordinal"]: item for item in loaded_actions}
    summaries = [
        _action_summary(
            descriptor,
            source_by_ordinal.get(descriptor["ordinal"]),
            captures.get(descriptor["ordinal"]),
            analyses.get(descriptor["ordinal"]),
        )
        for descriptor in manifest["actions"]
    ]
    completed = [item for item in summaries if item["machine"] is not None]
    if any(item["automated_verdict"] == "FAIL" for item in completed):
        verdict = "FAIL"
    elif len(completed) == len(summaries) and all(
        item["automated_verdict"] == "PASS" for item in completed
    ):
        verdict = "PASS"
    else:
        verdict = "INCONCLUSIVE"
    limitations: list[str] = []
    if len(completed) != len(summaries):
        limitations.append("campaign_actions_incomplete")
    if len(captures) != len(completed):
        limitations.append("one_or_more_completed_actions_lack_capture_sidecars")
    if len(analyses) != len(completed):
        limitations.append("one_or_more_completed_actions_lack_post_capture_analysis")
    if any(
        item["capture"] is not None
        and not _capture_supports_full_panel_analysis(item["capture"])
        for item in completed
    ):
        limitations.append("one_or_more_captures_cannot_support_full_panel_analysis")
    if any(
        item["analysis"] is not None
        and item["analysis"]["effective_verdict"] == "INCONCLUSIVE"
        for item in completed
    ):
        limitations.append("one_or_more_post_capture_analyses_are_inconclusive")
    if verdict != "PASS":
        limitations.append("no_automatic_full_panel_pass_claim")
    next_ordinal = next(
        (item["ordinal"] for item in summaries if item["machine"] is None), None
    )
    ordinal4 = next((item for item in summaries if item["ordinal"] == 4), None)
    ordinal4_qualified = bool(
        ordinal4 is not None
        and ordinal4["capture"] is not None
        and ordinal4["analysis"] is not None
        and ordinal4["capture"]["coverage"].get("scope") == "full_panel"
        and ordinal4["capture"]["coverage"].get("full_panel_visible") is True
        and ordinal4["capture"]["coverage"].get("full_panel_uncropped") is True
        and ordinal4["analysis"]["full_panel_pass_claimed"] is True
        and ordinal4["analysis"]["effective_verdict"] == "PASS"
        and ordinal4["analysis"]["confidence"] == "high"
        and ordinal4["analysis"]["candidate_detected"] is True
    )
    if verdict == "FAIL":
        next_gate = "STOP_AND_SEAL_CAMPAIGN"
    elif any(
        item["capture"] is not None
        and not _capture_supports_full_panel_analysis(item["capture"])
        for item in completed
    ):
        next_gate = "CAMERA_REPOSITION_OR_AUTOMATED_RECAPTURE_GATE"
    elif any(item["analysis"] is None for item in completed):
        next_gate = "AUTOMATED_POST_CAPTURE_ANALYSIS_GATE"
    elif any(
        item["analysis"] is not None
        and item["analysis"]["effective_verdict"] == "INCONCLUSIVE"
        for item in completed
    ):
        next_gate = "AUTOMATED_POST_CAPTURE_ANALYSIS_OR_RECAPTURE_GATE"
    elif next_ordinal is None:
        next_gate = "CAMPAIGN_REVIEW_GATE"
    elif next_ordinal == 5:
        next_gate = (
            "CONSIDER_ORDINAL5_SEPARATELY"
            if ordinal4_qualified
            else "STOP_ORDINAL4_NO_QUALIFIED_FULL_PANEL_CANDIDATE"
        )
    else:
        next_gate = f"ORDINAL_{next_ordinal:02d}_EXPLICIT_RELEASE_GATE"
    return {
        "schema_version": 1,
        "kind": INDEX_KIND,
        "generated_at": generated_at,
        "derivation": {
            "offline_only": True,
            "device_network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "camera_opened": False,
            "subprocess_started": False,
            "source_evidence_mutated": False,
            "human_observation_required_for_automated_verdict": False,
        },
        "identity": identity,
        "process_evidence": _ancillary_artifacts(campaign_dir, identity),
        "progress": {
            "expected_actions": len(summaries),
            "recorded_actions": len(completed),
            "captured_actions": len(captures),
            "analyzed_actions": len(analyses),
            "campaign_complete": len(completed) == len(summaries),
            "next_ordinal": next_ordinal,
        },
        "actions": summaries,
        "automated_adjudication": {
            "verdict": verdict,
            "confidence": (
                "high" if verdict == "PASS" else "high" if verdict == "FAIL" else "low"
            ),
            "full_panel_pass_claimed": verdict == "PASS",
            "qualified_colour_claimed": False,
            "limitations": limitations,
            "next_gate": next_gate,
        },
        "evidence_boundary": {
            "protocol_pass_is_visual_pass": False,
            "partial_view_is_full_panel_evidence": False,
            "camera_colour_is_calibrated": False,
            "new_or_qualified_colour_proven": False,
            "automatic_retry_or_autochain_allowed": False,
        },
    }


def _md_cell(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _photo_link(campaign_dir: Path, report_path: Path, relative: str) -> str:
    target = campaign_dir / Path(*PurePosixPath(relative).parts)
    raw = os.path.relpath(target, report_path.parent).replace(os.sep, "/")
    return quote(raw, safe="/._-")


def _render_markdown(
    index: Mapping[str, Any], *, campaign_dir: Path, report_path: Path
) -> str:
    identity = index["identity"]
    progress = index["progress"]
    adjudication = index["automated_adjudication"]
    lines = [
        "# MF1750 自动化真屏会话记录",
        "",
        f"- 派生时间：`{index['generated_at']}`",
        f"- 自动结论：**{adjudication['verdict']}**（置信度 `{adjudication['confidence']}`）",
        f"- 当前门：`{adjudication['next_gate']}`",
        f"- 进度：`{progress['recorded_actions']}/{progress['expected_actions']}` actions，`{progress['captured_actions']}` captures，`{progress['analyzed_actions']}` analyses",
        "- 本报告不依赖人工判断生成；相机局部入镜或低置信度只允许 `INCONCLUSIVE`。",
        "- `human_observation_required=false`；后续视觉门由全屏相机复拍与自动判读闭合。",
        "",
        "## 身份与范围",
        "",
        "| 字段 | 值 |",
        "|---|---|",
    ]
    for key in (
        "campaign_id",
        "test_id",
        "contract_id",
        "build_tag",
        "firmware_sha256",
        "boot_nonce",
    ):
        lines.append(f"| `{key}` | `{_md_cell(identity[key])}` |")
    lines.extend(
        [
            "",
            "## 部署与诊断流程",
            "",
            "| 阶段 | outcome | 文件 | SHA-256 |",
            "|---|---|---|---|",
        ]
    )
    if index["process_evidence"]:
        for item in index["process_evidence"]:
            lines.append(
                f"| `{item['kind']}` | `{_md_cell(item['outcome'])}` | "
                f"`{item['path']}` | `{item['file_sha256']}` |"
            )
    else:
        lines.append("| — | 未提供 | — | — |")
    lines.extend(
        [
            "",
            "## 动作总表",
            "",
            "| ordinal | role | palette/header | machine | capture | analysis | 自动结论 |",
            "|---:|---|---|---|---|---|---|",
        ]
    )
    for action in index["actions"]:
        machine = action["machine"]
        capture = action["capture"]
        machine_state = "NOT_EXECUTED" if machine is None else machine["outcome"]
        capture_state = (
            "MISSING"
            if capture is None
            else "FAILED"
            if capture["kind"] == CAPTURE_FAILURE_KIND
            else "CAPTURED"
        )
        analysis_state = "MISSING" if action["analysis"] is None else "ANALYZED"
        profile = f"{action['palette_source']}/{action['global_header'] or '-'}"
        lines.append(
            f"| {action['ordinal']} | `{_md_cell(action['role'])}` | `{profile}` | "
            f"`{machine_state}` | `{capture_state}` | `{analysis_state}` | "
            f"**{action['automated_verdict']}** |"
        )
    for action in index["actions"]:
        lines.extend(
            [
                "",
                f"## Action {action['ordinal']:02d} — `{_md_cell(action['role'])}`",
                "",
                f"- action ID：`{action['action_id']}`",
                f"- descriptor ID：`{action['descriptor_id']}`",
                f"- frame SHA-256：`{action['frame_sha256']}`",
                f"- 执行状态：`{action['execution_state']}`",
                f"- 自动结论：**{action['automated_verdict']}**",
                f"- 结论来源：`{action['verdict_source']}`",
            ]
        )
        machine = action["machine"]
        if machine is None:
            lines.append("- 机器证据：尚未执行。")
            continue
        driver = machine["driver"]
        network = machine["network"]
        lines.extend(
            [
                f"- 机器文件：`{machine['path']}`（`{machine['bytes']}` bytes，SHA-256 `{machine['file_sha256']}`）",
                f"- 网络计数：GET `{network['get']}` / ARM POST `{network['arm_post']}` / EXECUTE POST `{network['execute_post']}`",
                f"- driver / visible refresh：`{machine['driver_call_count_for_action']}` / `{machine['visible_refreshes']}`",
                f"- driver 时序：PON `{_md_cell(driver['pon_ms'])}` ms，DRF `{_md_cell(driver['drf_ms'])}` ms，POF `{_md_cell(driver['pof_ms'])}` ms，总计 `{_md_cell(driver['total_ms'])}` ms",
                f"- 安全约束：no-retry `{machine['no_retry']}`，no-recovery `{machine['no_recovery']}`，no-autochain `{machine['no_autochain']}`",
                f"- safe-finish：`{json.dumps(driver['safe_finish'], ensure_ascii=False, sort_keys=True)}`",
            ]
        )
        capture = action["capture"]
        if capture is None:
            lines.append("- 相机证据：缺失；视觉结论保持 `INCONCLUSIVE`。")
            continue
        assessment = capture["automated_assessment"]
        coverage = capture["coverage"]
        lines.extend(
            [
                f"- capture sidecar：`{capture['path']}`（SHA-256 `{capture['file_sha256']}`）",
                f"- 覆盖范围：`{_md_cell(coverage.get('scope'))}`；full-panel-visible `{coverage.get('full_panel_visible')}`；uncropped `{coverage.get('full_panel_uncropped')}`",
                f"- 相机判读：supplied `{assessment['supplied_verdict']}` → effective `{assessment['effective_verdict']}`，confidence `{assessment['confidence']}`",
                f"- 限制：{'; '.join(assessment['limitations']) or '无'}",
            ]
        )
        photo = capture["photo"]
        if photo is None:
            lines.append(f"- 拍照失败：`{_md_cell(capture['capture_error'])}`")
        else:
            link = _photo_link(campaign_dir, report_path, photo["path"])
            lines.extend(
                [
                    f"- 照片：`{photo['path']}`；`{photo['width']}×{photo['height']}`；`{photo['bytes']}` bytes；SHA-256 `{photo['sha256']}`",
                    "",
                    f"![Action {action['ordinal']:02d} capture](<{link}>)",
                ]
            )
        analysis = action["analysis"]
        if analysis is None:
            lines.append(
                "- Post-capture analysis：缺失；capture 不能自行升级为视觉 PASS，结论保持 `INCONCLUSIVE`。"
            )
            continue
        lines.extend(
            [
                f"- analysis sidecar：`{analysis['path']}`（SHA-256 `{analysis['file_sha256']}`）",
                f"- 分析源：`{analysis['analysis_source']}`；模型/算法：`{analysis['model_or_algorithm_id']}`",
                f"- Post-analysis 判读：supplied `{analysis['supplied_verdict']}` → effective `{analysis['effective_verdict']}`，confidence `{analysis['confidence']}`，candidate `{analysis['candidate_detected']}`",
                f"- observations：{'; '.join(analysis['observations']) or '无'}",
                f"- analysis limitations：{'; '.join(analysis['limitations']) or '无'}",
            ]
        )
    lines.extend(
        [
            "",
            "## 自动结论、限制与下一门",
            "",
            f"自动结论为 **{adjudication['verdict']}**；不声明合格新颜色。",
            "",
        ]
    )
    if adjudication["limitations"]:
        lines.extend(f"- `{item}`" for item in adjudication["limitations"])
    else:
        lines.append("- 无已登记限制。")
    lines.extend(
        [
            "",
            f"下一门：`{adjudication['next_gate']}`。本报告不会触发刷新、retry、recovery 或 autochain。",
            "",
            "## 证据边界与复核",
            "",
            "- protocol PASS 不等于视觉 PASS。",
            "- partial-panel 照片不等于全屏证据。",
            "- 未标定相机 RGB 不等于 Lab／绝对颜色测量。",
            "- 本报告为源 action/capture/post-analysis JSON 的纯离线派生视图。",
            "",
            "复核命令：",
            "",
            "```powershell",
            "python -B tools/mf1750_live_session_report.py validate --campaign-dir <CAMPAIGN_DIR>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _external_docs_path(campaign_dir: Path, docs_output: Path) -> Path:
    path = Path(docs_output).resolve()
    try:
        path.relative_to(campaign_dir.resolve())
    except ValueError:
        return path
    raise SessionReportError(
        "extra docs output must be outside the immutable campaign directory"
    )


def build_session(
    campaign_dir: Path,
    *,
    generated_at: str,
    docs_output: Path | None = None,
) -> dict[str, Any]:
    """Validate source evidence and atomically replace both derived outputs."""

    campaign_dir = Path(campaign_dir).resolve()
    draft = _compile_session(campaign_dir, generated_at=generated_at)
    report_path = campaign_dir / REPORT_NAME
    markdown = _render_markdown(
        draft, campaign_dir=campaign_dir, report_path=report_path
    )
    markdown_bytes = markdown.encode("utf-8")
    with_outputs = {
        **draft,
        "derived_outputs": {
            "markdown": {
                "path": REPORT_NAME,
                "bytes": len(markdown_bytes),
                "sha256": hashlib.sha256(markdown_bytes).hexdigest(),
            }
        },
    }
    index = _seal(with_outputs)
    index_bytes = (
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    _atomic_replace(report_path, markdown_bytes)
    _atomic_replace(campaign_dir / INDEX_NAME, index_bytes)
    if docs_output is not None:
        docs_path = _external_docs_path(campaign_dir, docs_output)
        docs_markdown = _render_markdown(
            draft, campaign_dir=campaign_dir, report_path=docs_path
        ).encode("utf-8")
        _atomic_replace(docs_path, docs_markdown)
    return index


def validate_session(
    campaign_dir: Path, *, docs_output: Path | None = None
) -> dict[str, Any]:
    """Recompute and validate an existing session index and Markdown report."""

    campaign_dir = Path(campaign_dir).resolve()
    index_path = campaign_dir / INDEX_NAME
    report_path = campaign_dir / REPORT_NAME
    existing = _strict_json(index_path)
    _validate_integrity(existing, label=INDEX_NAME)
    generated_at = _required_string(existing, "generated_at", label=INDEX_NAME)
    draft = _compile_session(campaign_dir, generated_at=generated_at)
    expected_markdown = _render_markdown(
        draft, campaign_dir=campaign_dir, report_path=report_path
    ).encode("utf-8")
    expected = _seal(
        {
            **draft,
            "derived_outputs": {
                "markdown": {
                    "path": REPORT_NAME,
                    "bytes": len(expected_markdown),
                    "sha256": hashlib.sha256(expected_markdown).hexdigest(),
                }
            },
        }
    )
    if existing != expected:
        raise SessionReportError("session index differs from source evidence")
    if not report_path.is_file() or report_path.read_bytes() != expected_markdown:
        raise SessionReportError("SESSION_REPORT.md differs from source evidence")
    if docs_output is not None:
        docs_path = _external_docs_path(campaign_dir, docs_output)
        expected_docs = _render_markdown(
            draft, campaign_dir=campaign_dir, report_path=docs_path
        ).encode("utf-8")
        if not docs_path.is_file() or docs_path.read_bytes() != expected_docs:
            raise SessionReportError("extra docs output differs from source evidence")
    return existing


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build derived JSON and Markdown")
    build.add_argument("--campaign-dir", type=Path, required=True)
    build.add_argument("--generated-at", required=True)
    build.add_argument("--docs-output", type=Path)
    validate = subparsers.add_parser("validate", help="recompute and validate outputs")
    validate.add_argument("--campaign-dir", type=Path, required=True)
    validate.add_argument("--docs-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "build":
            result = build_session(
                args.campaign_dir,
                generated_at=args.generated_at,
                docs_output=args.docs_output,
            )
        else:
            result = validate_session(args.campaign_dir, docs_output=args.docs_output)
    except SessionReportError as error:
        print(f"MF1750 session report error: {error}", file=os.sys.stderr)
        return 2
    print(json.dumps(result["automated_adjudication"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
