#!/usr/bin/env python3
"""Run the reviewed frozen G1/S1 macro4 quality candidate exactly once.

This runner is a fail-closed hardware gate for one exact source-preserving,
macrocell-clustered blue-noise frame.  It deep-validates and snapshots the
offline bundle before atomically consuming a workspace-global authorization
claim.  The claim is written before result-directory creation or any device
request.  After that point every failure is ``unknown_do_not_retry``; no code
path performs a recovery refresh or a second ``POST /api/frame``.

The candidate remains experimental regardless of outcome.  A successful
protocol report only permits manual comparison with the reviewed strict
preview and never implies formal or hardware qualification.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    validate_frame,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)
from tools.mf1750_frame_tool import (  # noqa: E402
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_POLL_INTERVAL_S,
    FrameToolError,
    _preflight_version,
    http_request,
    perform_refresh,
)


SCHEMA_VERSION = 1
LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "MACRO4-QUALITY-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-macro4-quality-refresh-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-macro4-quality-refresh-result"
CLAIM_KIND = "mf1750-g1-s1-macro4-quality-refresh-authorization-claim"
CLAIM_REGISTRY_ID = "workspace-g1-s1-macro4-quality-registry-v1"
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".g1_s1_macro4_quality_registry"
)
DEFAULT_CANDIDATE_DIRECTORY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807"
)

# These two digests bind different objects: the first is the exact on-disk
# manifest.json bytes; the second is the generator's canonical unsigned
# manifest digest recorded inside manifest_integrity.
EXPECTED_MANIFEST_SHA256 = "7c6f8569eb8a1cba9de144b7c660e79b932c1abbcbb5d6aa334ac694056420ad"
EXPECTED_MANIFEST_CANONICAL_SHA256 = "85abb1a948079eba89b7ca854c4b6b867e3b5f6716f5819c22765b610c2e900b"
EXPECTED_MANIFEST_KIND = "mf1750-g1-s1-macro4-quality-candidate"
EXPECTED_ALGORITHM_ID = "low-resolution-area-weighted-blue-noise-nearest-macro-v1"

EXPECTED_BUILD_TAG = (
    "MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05"
)
EXPECTED_DRIVER_API = "MF1750_R16_CASCADE_V3"
EXPECTED_REFRESH_SPI_HZ = 1_000_000
FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)

EXPECTED_LOW_SPATIAL_PRIOR = {
    "artifact_id": "G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430",
    "manifest_file_sha256": "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d",
    "manifest_canonical_sha256": "594d31031b4413ac83c376854dcd35f522e1ae769613908f3fa7289d5fece91d",
    "bytes": FRAME_BYTES,
    "sha256": "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65",
    "fnv1a": "0xA9641618",
    "codes_sha256": "caafec835cc5ef8a91767d71293100b6763442d337737fc0594e40ff9f8edbfa",
    "cs1_dtm_sha256": "c85a03621501c8bb0c535467a1581ab451f5bb0fc50fc4227c31e576d23d6070",
    "cs1_dtm_fnv1a": "0xCB085C03",
    "cs2_dtm_sha256": "bf25594c886c2046512eecf24795f8c2a5dacf1d9c565501658a6e6ea9889bd7",
    "cs2_dtm_fnv1a": "0x9ABD749A",
    "job_id": 4,
    "operation_id": 4,
}
EXPECTED_FRAME_SHA256 = "1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d"
EXPECTED_FRAME_FNV1A = 0x092C9775
EXPECTED_CS1_DTM_SHA256 = "a36a9288154d882916a6562d44d86c41278ea45ffbfcbc2afe634616d5a52fcc"
EXPECTED_CS1_DTM_FNV1A = 0x3F1601D5
EXPECTED_CS2_DTM_SHA256 = "d9bf80b6433bba8356502ce62ce44450da7339902413d9018d4ee6c959fb231d"
EXPECTED_CS2_DTM_FNV1A = 0x52ECC935
EXPECTED_PRIOR_JOB_ID = 4
EXPECTED_PRIOR_OPERATION_ID = 4
EXPECTED_TARGET_JOB_ID = 5
EXPECTED_TARGET_OPERATION_ID = 5

EXPECTED_PRIOR_JOB = {
    "job_id": 4,
    "action": "uploaded_frame",
    "state": "completed",
    "result": True,
    "queued_at_ms": 12_205_671,
    "started_at_ms": 12_205_675,
    "finished_at_ms": 12_239_845,
    "frame_fnv1a": 0xA9641618,
}
EXPECTED_PRIOR_DIAGNOSTIC = {
    "schema_version": 2,
    "firmware_build_tag": EXPECTED_BUILD_TAG,
    "driver_api_version": EXPECTED_DRIVER_API,
    "job_id": 4,
    "job_action": "uploaded_frame",
    "job_state": "completed",
    "job_result": True,
    "job_operation_id": 4,
    "job_queued_at_ms": 12_205_671,
    "job_started_at_ms": 12_205_675,
    "job_finished_at_ms": 12_239_845,
    "operation_id": 4,
    "valid": True,
    "running": False,
    "sequence_ok": True,
    "wait_timeout": False,
    "busy_assertion_missing": False,
    "busy_assert_grace_ms": 250,
    "mapping_applied": True,
    "pon_busy_seen": True,
    "drf_busy_seen": True,
    "pof_busy_seen": True,
    "post_psr_busy_seen": False,
    "spi_hz": 1_000_000,
    "input_fnv1a": 0xA9641618,
    "cs1_dtm_fnv1a": 0xCB085C03,
    "cs2_dtm_fnv1a": 0x9ABD749A,
    "total_ms": 34_169,
    "cs1_upload_ms": 2_440,
    "cs2_upload_ms": 2_440,
    "pon_ms": 181,
    "drf_ms": 21_690,
    "pof_ms": 140,
    "post_psr_ms": 5,
    "last_wait_ms": 5,
    "last_wait_stage": "post-display PSR",
    "timeout_stage": "none",
    "busy_missing_stage": "none",
    "mapping": {
        "cs1_source_half": 0,
        "cs1_flip_x": False,
        "cs1_flip_y": False,
        "cs1_nibble_swap": False,
        "cs2_source_half": 1,
        "cs2_flip_x": False,
        "cs2_flip_y": False,
        "cs2_nibble_swap": False,
    },
}
EXPECTED_COLD_RECONNECT_GPIO = {"busy": 0, "rst": 0, "cs": 0, "cs2": 0}
EXPECTED_WARM_SAFE_FINISH_GPIO = {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}

REQUIRED_AUTHORIZATION_CONFIRMATION = (
    "AUTHORIZE_ONE_VISIBLE_REFRESH_OF_REVIEWED_G1S1_MACRO4_STRICT_PREVIEW__"
    "NO_RETRY_NO_RECOVERY"
)
REQUIRED_CANDIDATE_FILES = frozenset(
    {
        "manifest.json",
        "frame.bin",
        "source.png",
        "mapped.png",
        "strict-final.png",
        "model.png",
    }
)

EXACT_ACTION = {
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_posts": 1,
    "automatic_retry": False,
    "automatic_recovery": False,
}
CLASSIFICATION = {
    "experimental": True,
    "variant": "macro4-blue-noise-quality-candidate",
    "variant_evaluation_only": True,
    "algorithm_qualification": False,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
}
MANUAL_OBSERVATION_REQUIRED = (
    "screen_matches_strict_preview",
    "power_supply_3_3v",
    "power_supply_cv",
    "current",
    "temperatures",
    "gpio_safety",
    "post_run_power_state",
)
POWER_POLICY = {
    "required_start": "explicit fresh J2-P1 reconnect with cold GPIO busy=0,rst=0,cs=0,cs2=0",
    "successful_supervised_run": "J2-P1 may remain powered while the supervised session continues",
    "abnormal_state": "use the physical switch to cut J2-P1",
    "session_end": "use the physical switch to cut J2-P1",
    "software_only_checks": "no J2-P1 power cycle required",
}
REQUIRED_VERIFIED_SCOPE = frozenset(
    {
        "canonical_frame_dimensions_and_physical_color_codes",
        "firmware_build_api_spi_psram_and_mapping_preflight",
        "frame_upload_bytes_and_fnv1a",
        "job_identity_state_result_and_frame_hash",
        "diagnostic_immutable_driver_operation_identity",
        "diagnostic_build_api_job_mapping_and_dtm_hashes",
        "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
    }
)


class Macro4QualityRefreshError(RuntimeError):
    """A failure before the permanent claim exists."""


class Macro4QualityRefreshUnknown(Macro4QualityRefreshError):
    """The permanent claim exists; this exact diagnostic must never be retried."""


@dataclass(frozen=True)
class _CandidateSnapshot:
    directory: Path
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    manifest_file_sha256: str
    frame: bytes


@dataclass(frozen=True)
class _AuthorizationClaim:
    registry: Path
    filename: str
    payload_sha256: str
    record: Mapping[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "file": self.filename,
            "sha256": self.payload_sha256,
            "attempt_id": self.record["attempt_id"],
            "state": self.record["state"],
        }


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
        raise Macro4QualityRefreshError(
            f"value cannot be represented as canonical JSON: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise Macro4QualityRefreshError(f"{label} must be a SHA-256 string")
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise Macro4QualityRefreshError(
            f"{label} must be exactly 64 hexadecimal digits"
        )
    return normalized


def _frozen_manifest_sha256() -> str:
    return _require_sha256(
        EXPECTED_MANIFEST_SHA256,
        label="frozen macro4 candidate manifest-file SHA-256",
    )


def _frozen_manifest_canonical_sha256() -> str:
    return _require_sha256(
        EXPECTED_MANIFEST_CANONICAL_SHA256,
        label="frozen macro4 candidate canonical manifest SHA-256",
    )


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _controller_records() -> list[dict[str, Any]]:
    hashes = (EXPECTED_CS1_DTM_FNV1A, EXPECTED_CS2_DTM_FNV1A)
    sha256s = (EXPECTED_CS1_DTM_SHA256, EXPECTED_CS2_DTM_SHA256)
    return [
        {
            "controller": f"CS{index}",
            "mapping": _mapping_record(mapping),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_sha256": sha256,
            "dtm_fnv1a": f"0x{hash_value:08X}",
        }
        for index, (mapping, sha256, hash_value) in enumerate(
            zip(FIXED_CONTROLLER_MAPPINGS, sha256s, hashes), start=1
        )
    ]


def _deep_validate_candidate_directory(directory: Path) -> Mapping[str, Any]:
    """Call the new candidate bundle's own deep validator.

    The import is local so this runner remains visibly fail-closed while the
    offline generator is being landed.  Missing or renamed validator code is a
    pre-claim error, never a fallback to the old candidate validator.
    """

    try:
        from tools.g1_s1_macro4_quality_candidate import (  # type: ignore[import-not-found]
            Macro4CandidateError,
            validate_candidate_directory,
        )
    except (ImportError, AttributeError) as error:
        raise Macro4QualityRefreshError(
            "the dedicated macro4 quality candidate deep validator is unavailable"
        ) from error
    try:
        manifest = validate_candidate_directory(directory)
    except (Macro4CandidateError, OSError, TypeError, ValueError) as error:
        raise Macro4QualityRefreshError(
            f"macro4 quality candidate deep validation failed: {error}"
        ) from error
    if not isinstance(manifest, Mapping):
        raise Macro4QualityRefreshError(
            "macro4 quality candidate validator did not return a manifest object"
        )
    return manifest


def _validate_fail_closed_manifest_fields(manifest: Mapping[str, Any]) -> None:
    classification = manifest.get("classification")
    required_classification = {
        "experimental": True,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "simulation_only": True,
        "upload_authorized": False,
        "preview_review_status": "pending_runtime_authorization_record",
    }
    if not isinstance(classification, Mapping) or any(
        classification.get(key) != value
        or type(classification.get(key)) is not type(value)
        for key, value in required_classification.items()
    ):
        raise Macro4QualityRefreshError(
            "candidate manifest is not the fail-closed offline experimental class"
        )
    transport = manifest.get("transport")
    required_transport = {
        "mode": "offline",
        "device_io_performed": False,
        "network_io_performed": False,
        "endpoint": None,
        "method": None,
        "upload_authorized": False,
        "refresh_runner_implemented": False,
    }
    if not isinstance(transport, Mapping) or any(
        transport.get(key) != value for key, value in required_transport.items()
    ):
        raise Macro4QualityRefreshError(
            "runner accepts only a completely offline candidate bundle"
        )


def _load_candidate_snapshot(
    candidate_dir: Path,
    expected_manifest_sha256: str,
) -> _CandidateSnapshot:
    """Deep-validate and snapshot the exact authorized bytes pre-claim."""

    try:
        require_local_regular_path_syntax(
            candidate_dir, label="macro4 candidate directory"
        )
    except LocalPathSafetyError as error:
        raise Macro4QualityRefreshError(str(error)) from error
    if candidate_dir.is_symlink():
        raise Macro4QualityRefreshError(
            "macro4 candidate directory must not be a symlink"
        )

    manifest = _deep_validate_candidate_directory(candidate_dir)
    try:
        directory = candidate_dir.resolve(strict=True)
        if not directory.is_dir():
            raise Macro4QualityRefreshError(
                "macro4 candidate path must be a directory"
            )
        entries = tuple(directory.iterdir())
        actual_files = {path.name for path in entries if path.is_file()}
        if actual_files != REQUIRED_CANDIDATE_FILES or any(path.is_dir() for path in entries):
            raise Macro4QualityRefreshError(
                "candidate bundle file set changed after deep validation"
            )
        manifest_path = directory / "manifest.json"
        frame_path = directory / "frame.bin"
        if manifest_path.is_symlink() or frame_path.is_symlink():
            raise Macro4QualityRefreshError(
                "candidate manifest/frame must not be symlinks"
            )
        manifest_bytes = manifest_path.read_bytes()
        if manifest_bytes != _canonical_json(manifest):
            raise Macro4QualityRefreshError(
                "candidate manifest bytes changed after deep validation"
            )
        manifest_file_sha256 = _sha256(manifest_bytes)
        if manifest_file_sha256 != expected_manifest_sha256:
            raise Macro4QualityRefreshError(
                "candidate manifest bytes do not match the frozen SHA-256"
            )

        integrity = manifest.get("manifest_integrity")
        unsigned = dict(manifest)
        unsigned.pop("manifest_integrity", None)
        canonical_sha256 = _sha256(_canonical_json(unsigned))
        if (
            not isinstance(integrity, Mapping)
            or integrity.get("canonical_sha256") != canonical_sha256
            or canonical_sha256 != _frozen_manifest_canonical_sha256()
        ):
            raise Macro4QualityRefreshError(
                "candidate canonical manifest integrity is not frozen"
            )

        _validate_fail_closed_manifest_fields(manifest)
        algorithm = manifest.get("algorithm")
        if (
            manifest.get("kind") != EXPECTED_MANIFEST_KIND
            or not isinstance(algorithm, Mapping)
            or algorithm.get("id") != EXPECTED_ALGORITHM_ID
        ):
            raise Macro4QualityRefreshError(
                "candidate kind or macro4 algorithm identity is not frozen"
            )
        evidence = manifest.get("evidence")
        prior = evidence.get("true_screen_prior") if isinstance(evidence, Mapping) else None
        required_prior = {
            key: EXPECTED_LOW_SPATIAL_PRIOR[key]
            for key in (
                "artifact_id",
                "manifest_file_sha256",
                "manifest_canonical_sha256",
                "sha256",
                "fnv1a",
                "codes_sha256",
            )
        }
        manifest_prior = {
            "artifact_id": prior.get("artifact_id") if isinstance(prior, Mapping) else None,
            "manifest_file_sha256": prior.get("manifest_file_sha256") if isinstance(prior, Mapping) else None,
            "manifest_canonical_sha256": prior.get("manifest_canonical_sha256") if isinstance(prior, Mapping) else None,
            "sha256": prior.get("frame_sha256") if isinstance(prior, Mapping) else None,
            "fnv1a": prior.get("frame_fnv1a") if isinstance(prior, Mapping) else None,
            "codes_sha256": prior.get("codes_sha256") if isinstance(prior, Mapping) else None,
        }
        if manifest_prior != required_prior:
            raise Macro4QualityRefreshError(
                "candidate manifest is not bound to the passed low-spatial true-screen prior"
            )
        output = manifest.get("output")
        if not isinstance(output, Mapping):
            raise Macro4QualityRefreshError(
                "candidate manifest payload is missing"
            )
        frame_record = output.get("frame")
        if not isinstance(frame_record, Mapping) or frame_record.get("file") != "frame.bin":
            raise Macro4QualityRefreshError(
                "candidate frame file identity is invalid"
            )
        frame = frame_path.read_bytes()
        validate_frame(frame)
        frame_sha256 = _sha256(frame)
        frame_fnv1a = fnv1a(frame)
        if (
            frame_record.get("bytes") != FRAME_BYTES
            or frame_record.get("sha256") != frame_sha256
            or frame_record.get("fnv1a") != f"0x{frame_fnv1a:08X}"
        ):
            raise Macro4QualityRefreshError(
                "candidate frame record does not match frame.bin"
            )
        if frame_sha256 != EXPECTED_FRAME_SHA256 or frame_fnv1a != EXPECTED_FRAME_FNV1A:
            raise Macro4QualityRefreshError(
                "candidate frame is not the one frozen macro4 frame"
            )
        actual_controller_hashes = tuple(
            fnv1a(controller_stream(frame, mapping))
            for mapping in FIXED_CONTROLLER_MAPPINGS
        )
        if actual_controller_hashes != (
            EXPECTED_CS1_DTM_FNV1A,
            EXPECTED_CS2_DTM_FNV1A,
        ):
            raise Macro4QualityRefreshError(
                "candidate frame controller DTM identities are not frozen"
            )
        if output.get("controllers") != _controller_records():
            raise Macro4QualityRefreshError(
                "candidate manifest controller records are not the frozen DTM streams"
            )
    except Macro4QualityRefreshError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise Macro4QualityRefreshError(
            f"candidate changed while taking the authorized snapshot: {error}"
        ) from error

    return _CandidateSnapshot(
        directory=directory,
        manifest=dict(manifest),
        manifest_bytes=manifest_bytes,
        manifest_file_sha256=manifest_file_sha256,
        frame=frame,
    )


def _prepare_new_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(result_dir, label="result directory")
    except LocalPathSafetyError as error:
        raise Macro4QualityRefreshError(str(error)) from error
    if os.path.lexists(result_dir):
        raise Macro4QualityRefreshError(
            "result directory already exists; refusing overwrite or rerun"
        )
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise Macro4QualityRefreshError(
            f"result parent does not exist: {error}"
        ) from error
    if not parent.is_dir():
        raise Macro4QualityRefreshError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise Macro4QualityRefreshError(
            "result directory already exists; refusing overwrite or rerun"
        )
    return destination


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _authorization_registry() -> Path:
    """Return the single non-configurable production claim registry."""

    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="authorization registry")
    except LocalPathSafetyError as error:
        raise Macro4QualityRefreshError(str(error)) from error
    if os.path.lexists(path) and path.is_symlink():
        raise Macro4QualityRefreshError(
            "authorization registry must not be a symlink"
        )
    try:
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise Macro4QualityRefreshError(
                "authorization registry parent must be a workspace directory"
            )
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except OSError as error:
        raise Macro4QualityRefreshError(
            f"could not create authorization registry: {error}"
        ) from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise Macro4QualityRefreshError(
            "authorization registry escaped the workspace or is not a directory"
        )
    return registry


def _claim_authorization(
    snapshot: _CandidateSnapshot,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    authorization_confirmation: str,
) -> _AuthorizationClaim:
    """Atomically consume the sole manifest identity before result/network I/O."""

    registry = _authorization_registry()
    if _is_within(result_destination, registry):
        raise Macro4QualityRefreshError(
            "result directory must not be inside the authorization registry"
        )
    filename = snapshot.manifest_file_sha256
    destination = registry / filename
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "manifest_file_sha256": snapshot.manifest_file_sha256,
        "frame": {
            "bytes": FRAME_BYTES,
            "sha256": EXPECTED_FRAME_SHA256,
            "fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
        },
        "controllers": _controller_records(),
        "declared_prior_frame": dict(EXPECTED_LOW_SPATIAL_PRIOR),
        "firmware": {
            "build_tag": EXPECTED_BUILD_TAG,
            "driver_api": EXPECTED_DRIVER_API,
            "panel": f"{WIDTH}x{HEIGHT}",
            "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        },
        "result_directory": str(result_destination),
        "exact_action": dict(EXACT_ACTION),
        "authorization_confirmation": authorization_confirmation,
        "expected_current_job_id": EXPECTED_PRIOR_JOB_ID,
        "expected_current_operation_id": EXPECTED_PRIOR_OPERATION_ID,
        "expected_target_job_id": EXPECTED_TARGET_JOB_ID,
        "expected_target_operation_id": EXPECTED_TARGET_OPERATION_ID,
        "expected_cold_reconnect_gpio": dict(EXPECTED_COLD_RECONNECT_GPIO),
        "expected_warm_safe_finish_gpio": dict(EXPECTED_WARM_SAFE_FINISH_GPIO),
        "power_policy": dict(POWER_POLICY),
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    payload = _canonical_json(record)
    claim = _AuthorizationClaim(registry, filename, _sha256(payload), record)
    temporary = registry / f".{filename}.tmp-{uuid.uuid4().hex}"
    claim_linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        claim_linked = True
        try:
            temporary.unlink()
        except OSError:
            pass
    except FileExistsError as error:
        if claim_linked:
            raise Macro4QualityRefreshUnknown(
                "candidate claim exists after post-claim cleanup failure; do not retry"
            ) from error
        raise Macro4QualityRefreshError(
            "this frozen candidate manifest was already permanently consumed; do not retry"
        ) from error
    except BaseException as error:
        if claim_linked:
            raise Macro4QualityRefreshUnknown(
                "candidate claim exists after post-claim processing failure; do not retry"
            ) from error
        if not isinstance(error, OSError):
            raise
        raise Macro4QualityRefreshError(
            f"could not atomically claim macro4 authorization: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass
    return claim


def _create_result_directory(
    destination: Path,
    snapshot: _CandidateSnapshot,
    claim: _AuthorizationClaim,
) -> Path:
    if _is_within(destination, snapshot.directory):
        raise Macro4QualityRefreshError(
            "result directory must not be inside the candidate bundle"
        )
    if _is_within(destination, claim.registry):
        raise Macro4QualityRefreshError(
            "result directory must not be inside the authorization registry"
        )
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise Macro4QualityRefreshError(
            "result directory appeared; refusing overwrite or rerun"
        ) from error
    except OSError as error:
        raise Macro4QualityRefreshError(
            f"could not create result directory: {error}"
        ) from error
    return destination


def _atomic_new_file(directory: Path, name: str, payload: bytes) -> None:
    temporary = directory / f".{name}.tmp-{uuid.uuid4().hex}"
    destination = directory / name
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        linked = True
        try:
            temporary.unlink()
        except OSError:
            pass
    except FileExistsError as error:
        raise Macro4QualityRefreshError(
            f"{name} already exists; refusing overwrite"
        ) from error
    except OSError as error:
        if linked:
            raise Macro4QualityRefreshError(
                f"{name} was committed but staging cleanup failed"
            ) from error
        raise Macro4QualityRefreshError(
            f"could not atomically write {name}: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


def _get_json_object(base_url: str, endpoint: str, *, label: str) -> Mapping[str, Any]:
    status, body = http_request(
        base_url,
        endpoint,
        method="GET",
        data=None,
        timeout=20.0,
    )
    if status != 200:
        raise Macro4QualityRefreshError(
            f"{label} returned HTTP {status}: {body[:200]}"
        )
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError) as error:
        raise Macro4QualityRefreshError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise Macro4QualityRefreshError(f"{label} must be a JSON object")
    return value


def _strict_json_equal(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _strict_json_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_json_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _validate_current_low_spatial_prior(base_url: str) -> Mapping[str, Any]:
    """Prove job4/op4 and the explicit cold-reconnect GPIO before the POST."""

    try:
        version = _preflight_version(base_url, http_request, FIXED_CONTROLLER_MAPPINGS)
    except FrameToolError as error:
        raise Macro4QualityRefreshError(
            f"current-prior firmware preflight failed: {error}"
        ) from error
    expected_version = {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "panel": f"{WIDTH}x{HEIGHT}",
        "frame_bytes": FRAME_BYTES,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "controller_mappings": [
            {"controller": f"CS{index}", "mapping": _mapping_record(mapping)}
            for index, mapping in enumerate(FIXED_CONTROLLER_MAPPINGS, start=1)
        ],
    }
    if any(version.get(key) != value for key, value in expected_version.items()):
        raise Macro4QualityRefreshError(
            "current-prior firmware build/API/panel/SPI/mappings are not frozen"
        )

    job = _get_json_object(base_url, "/api/job", label="current-prior job")
    diagnostic = _get_json_object(
        base_url, "/api/diagnostic/report", label="current-prior diagnostic"
    )
    status = _get_json_object(
        base_url, "/api/diagnostic/status", label="current-prior GPIO status"
    )
    if not _strict_json_equal(dict(job), EXPECTED_PRIOR_JOB):
        raise Macro4QualityRefreshError(
            "current screen is not the frozen completed low-spatial job4 prior"
        )
    if not _strict_json_equal(dict(diagnostic), EXPECTED_PRIOR_DIAGNOSTIC):
        raise Macro4QualityRefreshError(
            "current screen is not the frozen safe-finish low-spatial operation4 prior"
        )
    # RST remains driven low across this hardware state, so a fresh J2-P1
    # reconnect must not be treated as the historical warm BUSY-idle state.
    # The observed cold contract is all four sampled lines low; BUSY=1 is
    # accepted only after this run reaches its warm safe finish.
    if not _strict_json_equal(dict(status), EXPECTED_COLD_RECONNECT_GPIO):
        raise Macro4QualityRefreshError(
            "fresh J2-P1 reconnect is not cold GPIO busy=0,rst=0,cs=0,cs2=0"
        )
    return {
        "version": dict(version),
        "job": dict(job),
        "diagnostic": dict(diagnostic),
        "gpio_status": dict(status),
        "prior_frame": dict(EXPECTED_LOW_SPATIAL_PRIOR),
    }


def _validate_post_refresh_warm_gpio(base_url: str) -> Mapping[str, Any]:
    status = _read_post_refresh_gpio_status(base_url)
    return _require_post_refresh_warm_gpio(status)


def _read_post_refresh_gpio_status(base_url: str) -> Mapping[str, Any]:
    """Read and return the raw post-refresh GPIO object without adjudicating it.

    Keeping acquisition separate from validation is intentional: a non-matching
    GPIO sample is incident evidence and must survive the validation exception.
    """

    return dict(_get_json_object(
        base_url,
        "/api/diagnostic/status",
        label="post-refresh warm GPIO status",
    ))


def _require_post_refresh_warm_gpio(
    status: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not _strict_json_equal(dict(status), EXPECTED_WARM_SAFE_FINISH_GPIO):
        raise Macro4QualityRefreshError(
            "post-refresh GPIO is not warm safe-finish busy=1,rst=0,cs=0,cs2=0"
        )
    return dict(status)


def _capture_postclaim_read_only_evidence(base_url: str) -> Mapping[str, Any]:
    """Best-effort GET-only incident snapshot after a claimed attempt fails.

    This helper is deliberately incapable of accepting a method, payload, or
    refresh callback.  Every capture is a single GET and every failure is
    recorded independently so an unavailable endpoint cannot suppress evidence
    from the other endpoints.  It is evidence collection, never recovery.
    """

    captures: dict[str, Any] = {}
    endpoints = (
        ("job", "/api/job"),
        ("diagnostic_report", "/api/diagnostic/report"),
        ("gpio_status", "/api/diagnostic/status"),
    )
    for name, endpoint in endpoints:
        try:
            value = _get_json_object(
                base_url,
                endpoint,
                label=f"post-claim evidence {name}",
            )
        except BaseException as error:
            captures[name] = {
                "method": "GET",
                "endpoint": endpoint,
                "status": "capture_failed",
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        else:
            captures[name] = {
                "method": "GET",
                "endpoint": endpoint,
                "status": "captured",
                "value": dict(value),
            }
    return {
        "attempted": True,
        "purpose": "incident_evidence_only_not_retry_or_recovery",
        "requests_are_read_only": True,
        "state_changing_request_performed": False,
        "captures": captures,
    }


def _no_postclaim_capture(reason: str) -> Mapping[str, Any]:
    return {
        "attempted": False,
        "purpose": "incident_evidence_only_not_retry_or_recovery",
        "requests_are_read_only": True,
        "state_changing_request_performed": False,
        "reason": reason,
        "captures": {},
    }


def _validate_network_report(report: object) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise Macro4QualityRefreshError(
            "refresh protocol report must be an object"
        )
    if report.get("protocol_verified") is not True or report.get("hardware_tested") is not False:
        raise Macro4QualityRefreshError(
            "refresh protocol report lost its fail-closed classification"
        )
    scope = report.get("verified_scope")
    if not isinstance(scope, list) or not REQUIRED_VERIFIED_SCOPE.issubset(scope):
        raise Macro4QualityRefreshError(
            "refresh protocol report is missing required verified scope"
        )
    preflight = report.get("preflight")
    if not isinstance(preflight, Mapping):
        raise Macro4QualityRefreshError("refresh preflight record is missing")
    expected_mappings = [
        {"controller": f"CS{index}", "mapping": _mapping_record(mapping)}
        for index, mapping in enumerate(FIXED_CONTROLLER_MAPPINGS, start=1)
    ]
    expected_preflight = {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "panel": f"{WIDTH}x{HEIGHT}",
        "frame_bytes": FRAME_BYTES,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "controller_mappings": expected_mappings,
    }
    if any(preflight.get(key) != value for key, value in expected_preflight.items()):
        raise Macro4QualityRefreshError(
            "refresh preflight does not match the frozen build/API/panel/SPI/mappings"
        )
    job = report.get("job")
    job_id = report.get("job_id")
    if (
        not isinstance(job, Mapping)
        or type(job_id) is not int
        or job_id != EXPECTED_TARGET_JOB_ID
        or job.get("job_id") != job_id
        or job.get("action") != "uploaded_frame"
        or job.get("state") != "completed"
        or job.get("result") is not True
        or job.get("frame_fnv1a") != EXPECTED_FRAME_FNV1A
    ):
        raise Macro4QualityRefreshError(
            "completed job is not bound to the frozen candidate frame"
        )
    timestamps = tuple(
        job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms")
    )
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in timestamps):
        raise Macro4QualityRefreshError("completed job timing fields are not uint32")
    queued_at_ms, started_at_ms, finished_at_ms = timestamps
    queue_delay_ms = (started_at_ms - queued_at_ms) & 0xFFFFFFFF
    refresh_duration_ms = (finished_at_ms - started_at_ms) & 0xFFFFFFFF
    if queue_delay_ms > 60_000 or not 10_000 <= refresh_duration_ms <= 120_000:
        raise Macro4QualityRefreshError(
            "completed job timing is outside the visible-refresh safety envelope"
        )
    diagnostic = report.get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise Macro4QualityRefreshError("immutable diagnostic record is missing")
    operation_id = diagnostic.get("operation_id")
    if (
        type(operation_id) is not int
        or operation_id != EXPECTED_TARGET_OPERATION_ID
        or diagnostic.get("job_operation_id") != operation_id
        or diagnostic.get("job_driver_operation_identity_matched") is not True
        or diagnostic.get("sequence_verified") is not True
        or diagnostic.get("required_busy_stages_verified") is not True
        or diagnostic.get("busy_timeout") is not False
        or diagnostic.get("safe_finish_verified") is not True
    ):
        raise Macro4QualityRefreshError(
            "job/operation/sequence/safe-finish binding is incomplete"
        )
    physical = diagnostic.get("physical_controllers")
    expected_physical = [
        {
            "controller": record["controller"],
            "mapping": record["mapping"],
            "dtm_bytes": record["dtm_bytes"],
            "dtm_fnv1a": int(record["dtm_fnv1a"], 16),
        }
        for record in _controller_records()
    ]
    if physical != expected_physical:
        raise Macro4QualityRefreshError(
            "immutable diagnostic DTM identities are not the frozen controller streams"
        )
    return report


def _perform_refresh_once(
    base_url: str,
    frame: bytes,
    *,
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
) -> Mapping[str, Any]:
    # Exactly one call.  perform_refresh performs one /api/frame POST and only
    # GET polling/report retrieval afterward; there is no recovery call here.
    report = perform_refresh(
        base_url,
        frame,
        expected_mappings=FIXED_CONTROLLER_MAPPINGS,
        job_timeout_s=job_timeout_s,
        poll_interval_s=poll_interval_s,
        sleeper=sleeper,
        clock=clock,
    )
    return _validate_network_report(report)


def _base_result(
    *,
    attempt_id: str,
    snapshot: _CandidateSnapshot,
    claim: _AuthorizationClaim,
    recorded_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "candidate": {
            "manifest_file_sha256": snapshot.manifest_file_sha256,
            "manifest_canonical_sha256": EXPECTED_MANIFEST_CANONICAL_SHA256,
            "manifest_kind": EXPECTED_MANIFEST_KIND,
            "algorithm_id": EXPECTED_ALGORITHM_ID,
            "frame_sha256": EXPECTED_FRAME_SHA256,
            "frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
            "controllers": _controller_records(),
            "declared_prior_frame": dict(EXPECTED_LOW_SPATIAL_PRIOR),
        },
        "authorization_claim": claim.reference(),
        "exact_action": dict(EXACT_ACTION),
        "authorization_consumed_permanently": True,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "classification": dict(CLASSIFICATION),
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "algorithm_qualification": False,
        "manual_observation_required": list(MANUAL_OBSERVATION_REQUIRED),
        "manual_observation_completed": False,
        "power_policy": dict(POWER_POLICY),
    }


def run_macro4_quality_refresh_once(
    result_dir: Path,
    base_url: str,
    *,
    authorization_confirmation: str,
    confirm_j2_powered_supervised: bool = False,
    confirm_j2_reconnected_cold_start: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consume and run the sole frozen macro4 quality candidate authorization."""

    if not isinstance(result_dir, Path):
        raise Macro4QualityRefreshError(
            "result_dir must be a pathlib.Path object"
        )
    destination = _prepare_new_result_destination(result_dir)
    expected_manifest_sha256 = _frozen_manifest_sha256()
    _frozen_manifest_canonical_sha256()
    confirmations = {
        "reviewed_strict_preview_authorization": authorization_confirmation,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "J2_reconnected_cold_start": confirm_j2_reconnected_cold_start,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
    }
    if authorization_confirmation != REQUIRED_AUTHORIZATION_CONFIRMATION:
        raise Macro4QualityRefreshError(
            "the exact reviewed-preview one-refresh authorization string is required"
        )
    if (
        type(confirm_j2_powered_supervised) is not bool
        or confirm_j2_powered_supervised is not True
        or type(confirm_j2_reconnected_cold_start) is not bool
        or confirm_j2_reconnected_cold_start is not True
        or type(confirm_supply_and_temperature_normal) is not bool
        or confirm_supply_and_temperature_normal is not True
    ):
        raise Macro4QualityRefreshError(
            "explicit supervised-power, cold-reconnect, and normal-supply/temperature confirmations are required"
        )
    if not isinstance(base_url, str) or not base_url.strip():
        raise Macro4QualityRefreshError(
            "base_url must be a non-empty device root URL"
        )

    # This dedicated validator is the last operation before the permanent
    # authorization claim.  Neither the old candidate validator nor a generic
    # frame tool can substitute for it.
    snapshot = _load_candidate_snapshot(
        DEFAULT_CANDIDATE_DIRECTORY, expected_manifest_sha256
    )
    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    claim = _claim_authorization(
        snapshot,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        authorization_confirmation=authorization_confirmation,
    )

    directory: Optional[Path] = None
    prior_preflight: Optional[Mapping[str, Any]] = None
    network_report: Optional[Mapping[str, Any]] = None
    post_refresh_gpio_status: Optional[Mapping[str, Any]] = None
    device_io_started = False
    try:
        directory = _create_result_directory(destination, snapshot, claim)
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": LOCK_KIND,
            "attempt_id": attempt_id,
            "created_at_utc": created_at_utc,
            "state": "authorization_permanently_consumed_do_not_rerun",
            "candidate_manifest_file_sha256": snapshot.manifest_file_sha256,
            "candidate_manifest_canonical_sha256": EXPECTED_MANIFEST_CANONICAL_SHA256,
            "candidate_frame_sha256": EXPECTED_FRAME_SHA256,
            "candidate_frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
            "declared_prior_frame": dict(EXPECTED_LOW_SPATIAL_PRIOR),
            "fixed_controller_mappings": [
                _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
            ],
            "controllers": _controller_records(),
            "firmware": {
                "build_tag": EXPECTED_BUILD_TAG,
                "driver_api": EXPECTED_DRIVER_API,
                "panel": f"{WIDTH}x{HEIGHT}",
                "frame_bytes": FRAME_BYTES,
                "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
            },
            "authorization_claim": claim.reference(),
            "exact_action": dict(EXACT_ACTION),
            "power_policy": dict(POWER_POLICY),
            "confirmations": confirmations,
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "algorithm_qualification": False,
        }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        device_io_started = True
        prior_preflight = _validate_current_low_spatial_prior(base_url)
        network_report = _perform_refresh_once(
            base_url,
            snapshot.frame,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        # Acquire first and validate second.  A mismatching GPIO object is raw
        # incident evidence and must remain available to the exception record.
        post_refresh_gpio_status = _read_post_refresh_gpio_status(base_url)
        _require_post_refresh_warm_gpio(post_refresh_gpio_status)
        result = {
            **_base_result(
                attempt_id=attempt_id,
                snapshot=snapshot,
                claim=claim,
                recorded_at_utc=_utc_now(),
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "current_prior_preflight": dict(prior_preflight),
            "post_refresh_gpio_status": dict(post_refresh_gpio_status),
            "network_report": dict(network_report),
        }
        _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(result))
        return result
    except BaseException as error:
        record_error: Optional[BaseException] = None
        try:
            postclaim_evidence = (
                _capture_postclaim_read_only_evidence(base_url)
                if device_io_started
                else _no_postclaim_capture(
                    "no device I/O had started when the post-claim local failure occurred"
                )
            )
        except BaseException as capture_error:
            # The capture helper is designed not to raise, but preserve the
            # original failure and make even an unexpected local capture bug
            # explicit rather than masking the claimed attempt.
            postclaim_evidence = {
                **dict(_no_postclaim_capture("capture helper failed locally")),
                "capture_helper_error": {
                    "type": type(capture_error).__name__,
                    "message": str(capture_error),
                },
            }
        try:
            if directory is not None:
                unknown = {
                    **_base_result(
                        attempt_id=attempt_id,
                        snapshot=snapshot,
                        claim=claim,
                        recorded_at_utc=_utc_now(),
                    ),
                    "outcome": "unknown_do_not_retry",
                    "protocol_verified": (
                        network_report.get("protocol_verified")
                        if network_report is not None
                        else None
                    ),
                    "current_prior_preflight": (
                        dict(prior_preflight) if prior_preflight is not None else None
                    ),
                    "post_refresh_gpio_status": (
                        dict(post_refresh_gpio_status)
                        if post_refresh_gpio_status is not None
                        else None
                    ),
                    "network_report": (
                        dict(network_report) if network_report is not None else None
                    ),
                    "best_effort_postclaim_evidence": dict(postclaim_evidence),
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
                _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(unknown))
        except BaseException as result_error:
            record_error = result_error
        detail = (
            f"; macro4 quality result could not be recorded ({record_error})"
            if record_error is not None
            else ""
        )
        raise Macro4QualityRefreshUnknown(
            "macro4 quality candidate outcome is unknown_do_not_retry; "
            f"the global claim is permanent{detail}"
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument(
        "--url", required=True, help="device root URL on the trusted test network"
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help="exact reviewed-preview one-refresh authorization string",
    )
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-j2-reconnected-cold-start", action="store_true")
    parser.add_argument(
        "--confirm-supply-and-temperature-normal", action="store_true"
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_macro4_quality_refresh_once(
            args.result_dir,
            args.url,
            authorization_confirmation=args.confirm,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_j2_reconnected_cold_start=(
                args.confirm_j2_reconnected_cold_start
            ),
            confirm_supply_and_temperature_normal=(
                args.confirm_supply_and_temperature_normal
            ),
        )
    except Macro4QualityRefreshUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except Macro4QualityRefreshError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
