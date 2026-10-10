#!/usr/bin/env python3
"""Run one exact G1/S1 quality candidate on the instrumented RC2G build.

The caller freezes an offline experimental candidate manifest, the exact
completed prior job/operation/frame identity, and the next target job and
operation.  A canonical action identity is derived from those inputs.  Its
exact authorization is atomically and permanently claimed before any device
request.  The claimed action can issue at most one ``POST /api/frame`` and has
no retry, recovery, or cancel path.

RC2G nested BUSY-edge evidence is mandatory for both the prior and target
operations.  RST/CS1/CS2 must finish low.  BUSY sampled after RST is low is
retained as informational evidence rather than treated as an idle verdict.
Every post-claim exception is ``unknown_do_not_retry`` and preserves completed
reports, raw GPIO, a request audit, and GET-only best-effort evidence.
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
)
from tools import g1_s1_experimental_refresh as experimental_refresh  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)
from tools.mf1750_frame_tool import (  # noqa: E402
    BUSY_TRACE_BUILD_TAGS,
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_POLL_INTERVAL_S,
    FrameToolError,
    _preflight_version,
    _validate_busy_trace,
    _validate_diagnostic,
    _validate_job,
    http_request,
    perform_refresh,
)


SCHEMA_VERSION = 1
LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "RC2G-QUALITY-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-rc2g-quality-refresh-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-rc2g-quality-refresh-result"
CLAIM_KIND = "mf1750-g1-s1-rc2g-quality-refresh-claim"
CLAIM_REGISTRY_ID = "workspace-g1-s1-rc2g-quality-refresh-registry-v1"
ACTION_IDENTITY_KIND = "mf1750-g1-s1-rc2g-quality-refresh-action-identity"

DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".g1_s1_rc2g_quality_refresh_registry"
)

EXPECTED_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
EXPECTED_DRIVER_API = "MF1750_R16_CASCADE_V3"
EXPECTED_REFRESH_SPI_HZ = 1_000_000
FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)
EXPECTED_PANEL_OUTPUTS_LOW = {"rst": 0, "cs": 0, "cs2": 0}

# Keep these equal to the reviewed macro4 redisplay gate.  Unlike the generic
# frame tool's broad safety bounds, these are the nominal quality-run bounds.
NOMINAL_JOB_DURATION_MS = (28_000, 45_000)
NOMINAL_STAGE_TIMING_MS = {
    "total_ms": (28_000, 45_000),
    "cs1_upload_ms": (1_500, 5_000),
    "cs2_upload_ms": (1_500, 5_000),
    "pon_ms": (50, 2_000),
    "drf_ms": (18_000, 26_000),
    "pof_ms": (50, 1_000),
    "post_psr_ms": (0, 100),
}
MAX_QUEUE_DELAY_MS = 5_000
MAX_JOB_DRIVER_DURATION_DELTA_MS = 2_000

ALLOWED_QUALITY_ALGORITHMS = frozenset(
    {
        "atkinson",
        "area-weighted-blue-noise",
        "multicolor-dbs",
        "overlap-aware-dbs",
    }
)
EXPECTED_MANIFEST_KIND = "mf1750-g1-s1-experimental-panel-candidate"
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_QUALITY_REFRESH__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
EXACT_ACTION = {
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_posts": 1,
    "automatic_retry": False,
    "automatic_recovery": False,
    "remote_cancel": False,
}
CLASSIFICATION = {
    "experimental": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
    "algorithm_qualification": False,
    "quality_candidate_evaluation_only": True,
}

# The public quality runner remains parameterized only for the four reviewed
# natural-image candidate manifests.  Its underscored prevalidated path exists
# solely so the dedicated N1 runner can reuse the protocol core for one exact
# diagnostic raster.  These frozen values are repeated here deliberately: a
# caller cannot use the internal hook to bypass the normal manifest/algorithm
# allowlist or create a new claim partition.
_INTERNAL_N1_ACTION_ID = (
    "rc2g-n1-low-balanced-pilot-after-map-primer-job2-op2-once-v1"
)
_INTERNAL_N1_PILOT_ID = "n1-low-balanced-pilot-v1"
_INTERNAL_N1_BINDING_KIND = (
    "mf1750-g1-s1-rc2g-n1-low-balanced-pilot-evidence-binding"
)
_INTERNAL_N1_DIRECTORY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2"
)
_INTERNAL_N1_MANIFEST_FILE_SHA256 = (
    "b25efedae7d3ff5947c7b5c546879b6fbce44f67ae59d410581b4d745e8db055"
)
_INTERNAL_N1_MANIFEST_CANONICAL_SHA256 = (
    "7e0be9f7473b69ee0f612fed21e3ede955fcd0f28a7fe044fb5469a3165315f1"
)
_INTERNAL_N1_FRAME_SHA256 = (
    "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65"
)
_INTERNAL_N1_FRAME_FNV1A = 0xA9641618
_INTERNAL_N1_CS1_DTM_FNV1A = "0xCB085C03"
_INTERNAL_N1_CS2_DTM_FNV1A = "0x9ABD749A"
_INTERNAL_N1_MAP_FRAME_SHA256 = (
    "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
)
_INTERNAL_N1_MAP_FRAME_FNV1A = "0x9D04142D"
_INTERNAL_N1_MAP_CS1_DTM_FNV1A = "0xF26832DD"
_INTERNAL_N1_MAP_CS2_DTM_FNV1A = "0xFE199FF5"
_INTERNAL_N1_PRIMER_ACTION_ID = (
    "rc2g-n1-low-balanced-pilot-cold-boot-map-primer-job1-op1-once-v1"
)
_INTERNAL_N1_PRIMER_ACTION_SHA256 = (
    "6354b456bc71033fa4ef96ebc8ff972e8d1e45f0f27403977c99bdee4cc20660"
)
_INTERNAL_N1_OLD_MANIFEST_SHA256 = (
    "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d"
)
_INTERNAL_N1_PREVIEW_SHA256 = (
    "39c10018dda091bb5af0ebad26b006c1c5e7c3374096de086e7cc8debcc42205"
)
_INTERNAL_N1_CLASSIFICATION = {
    "experimental": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
    "algorithm_qualification": False,
    "n1_low_balanced_safety_fidelity_pilot_only": True,
    "causal_attribution_authorized": False,
    "natural_image_quality_evaluation": False,
}
_INTERNAL_N1_MANUAL_OBSERVATIONS = [
    "primer_MAP_visual_fidelity_was_confirmed_before_target",
    "screen_matches_frozen_low_balanced_strict_preview",
    "large_regions_left_right_halves_orientation_and_center_seam",
    "all_six_codes_full_panel_coverage_and_no_MAP_retention",
    "power_supply_3_3v_cv_current_and_temperature",
    "no_odor_sound_hotspot_damage_or_voltage_droop",
    "diagnostic_geometry_is_not_scored_as_natural_image_quality",
    "post_run_power_state",
]
REQUIRED_VERIFIED_SCOPE = frozenset(
    {
        "canonical_frame_dimensions_and_physical_color_codes",
        "firmware_build_api_spi_psram_and_mapping_preflight",
        "frame_upload_bytes_and_fnv1a",
        "job_identity_state_result_and_frame_hash",
        "diagnostic_immutable_driver_operation_identity",
        "diagnostic_build_api_job_mapping_and_dtm_hashes",
        "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
        "diagnostic_idle_before_command_busy_edges_and_safe_finish_pin_snapshot",
    }
)


class Rc2gQualityRefreshError(RuntimeError):
    """The action was rejected before its permanent claim existed."""


class Rc2gQualityRefreshUnknown(Rc2gQualityRefreshError):
    """The claim exists, so the exact action must never be attempted again."""


@dataclass(frozen=True)
class _CandidateSnapshot:
    directory: Path
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    manifest_file_sha256: str
    manifest_canonical_sha256: str
    algorithm: str
    frame: bytes
    frame_sha256: str
    frame_fnv1a: int
    controllers: tuple[Mapping[str, Any], Mapping[str, Any]]


@dataclass(frozen=True)
class _RunContract:
    snapshot: _CandidateSnapshot
    expected_prior_job_id: int
    expected_prior_operation_id: int
    expected_prior_frame_sha256: str
    expected_prior_frame_fnv1a: int
    expected_prior_cs1_dtm_fnv1a: int
    expected_prior_cs2_dtm_fnv1a: int
    expected_target_job_id: int
    expected_target_operation_id: int
    action_identity: Mapping[str, Any]
    action_identity_sha256: str
    required_authorization_confirmation: str


@dataclass(frozen=True)
class _Claim:
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
            "action_identity_sha256": self.record["action_identity_sha256"],
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
        raise Rc2gQualityRefreshError(
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
        raise Rc2gQualityRefreshError(f"{label} must be a SHA-256 string")
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise Rc2gQualityRefreshError(
            f"{label} must be exactly 64 hexadecimal digits"
        )
    return normalized


def _require_u32(value: object, *, label: str, nonzero: bool = False) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise Rc2gQualityRefreshError(f"{label} must be an unsigned 32-bit integer")
    if nonzero and value == 0:
        raise Rc2gQualityRefreshError(f"{label} must be non-zero")
    return value


def _next_nonzero_u32(value: int) -> int:
    next_value = (value + 1) & 0xFFFFFFFF
    return 1 if next_value == 0 else next_value


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _controller_records(frame: bytes) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for index, mapping in enumerate(FIXED_CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        records.append(
            {
                "controller": f"CS{index}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    return records[0], records[1]


def _load_candidate_snapshot(
    candidate_dir: Path,
    expected_manifest_sha256: str,
) -> _CandidateSnapshot:
    expected_sha256 = _require_sha256(
        expected_manifest_sha256, label="expected candidate manifest SHA-256"
    )
    try:
        source = experimental_refresh._load_candidate_snapshot(  # noqa: SLF001
            candidate_dir,
            expected_sha256,
        )
    except experimental_refresh.ExperimentalRefreshError as error:
        raise Rc2gQualityRefreshError(str(error)) from error
    manifest = source.manifest
    options = manifest.get("options")
    option_value = options.get("value") if isinstance(options, Mapping) else None
    algorithm = option_value.get("algorithm") if isinstance(option_value, Mapping) else None
    if manifest.get("kind") != EXPECTED_MANIFEST_KIND:
        raise Rc2gQualityRefreshError("candidate manifest kind is not the experimental contract")
    if algorithm not in ALLOWED_QUALITY_ALGORITHMS:
        allowed = ", ".join(sorted(ALLOWED_QUALITY_ALGORITHMS))
        raise Rc2gQualityRefreshError(
            f"candidate algorithm is outside the RC2G quality allowlist: {allowed}"
        )
    integrity = manifest.get("manifest_integrity")
    canonical_sha256 = (
        integrity.get("canonical_sha256") if isinstance(integrity, Mapping) else None
    )
    canonical_sha256 = _require_sha256(
        canonical_sha256, label="candidate canonical manifest SHA-256"
    )
    frame = bytes(source.frame)
    return _CandidateSnapshot(
        directory=source.directory,
        manifest=dict(manifest),
        manifest_bytes=bytes(source.manifest_bytes),
        manifest_file_sha256=source.manifest_file_sha256,
        manifest_canonical_sha256=canonical_sha256,
        algorithm=algorithm,
        frame=frame,
        frame_sha256=_sha256(frame),
        frame_fnv1a=fnv1a(frame),
        controllers=_controller_records(frame),
    )


def _validate_internal_n1_override(
    snapshot: _CandidateSnapshot,
    binding: Optional[Mapping[str, Any]],
    expected_exact_prior_evidence: Optional[Mapping[str, Any]],
    additional_confirmations: Optional[Mapping[str, Any]],
    fixed_claim_filename: Optional[str],
    result_classification: Optional[Mapping[str, Any]],
    manual_observations: Optional[Sequence[str]],
    fixed_result_metadata: Optional[Mapping[str, Any]],
    *,
    expected_prior_job_id: int,
    expected_prior_operation_id: int,
    expected_prior_frame_sha256: str,
    expected_prior_frame_fnv1a: int,
    expected_prior_cs1_dtm_fnv1a: int,
    expected_prior_cs2_dtm_fnv1a: int,
    expected_target_job_id: int,
    expected_target_operation_id: int,
) -> None:
    """Fail closed unless every internal hook is the sole frozen N1 action."""

    values = (
        binding,
        expected_exact_prior_evidence,
        additional_confirmations,
        fixed_claim_filename,
        result_classification,
        manual_observations,
        fixed_result_metadata,
    )
    if all(value is None for value in values):
        raise Rc2gQualityRefreshError(
            "a prevalidated snapshot is forbidden without the complete fixed N1 scope"
        )
    if any(value is None for value in values):
        raise Rc2gQualityRefreshError(
            "internal RC2G overrides must be the complete fixed N1 scope"
        )
    assert binding is not None
    assert expected_exact_prior_evidence is not None
    assert additional_confirmations is not None
    assert fixed_claim_filename is not None
    assert result_classification is not None
    assert manual_observations is not None
    assert fixed_result_metadata is not None

    try:
        expected_directory = _INTERNAL_N1_DIRECTORY.resolve(strict=True)
        actual_directory = snapshot.directory.resolve(strict=True)
    except OSError as error:
        raise Rc2gQualityRefreshError(
            f"fixed N1 candidate directory is unavailable: {error}"
        ) from error
    recalculated_controllers = _controller_records(snapshot.frame)
    if (
        actual_directory != expected_directory
        or snapshot.algorithm != "n1-low-balanced-safety-fidelity-pilot"
        or snapshot.manifest.get("kind")
        != "mf1750-g1-s1-root-cause-2x2-offline-audit"
        or snapshot.manifest_file_sha256 != _INTERNAL_N1_MANIFEST_FILE_SHA256
        or _sha256(snapshot.manifest_bytes) != _INTERNAL_N1_MANIFEST_FILE_SHA256
        or snapshot.manifest_canonical_sha256
        != _INTERNAL_N1_MANIFEST_CANONICAL_SHA256
        or snapshot.frame_sha256 != _INTERNAL_N1_FRAME_SHA256
        or _sha256(snapshot.frame) != _INTERNAL_N1_FRAME_SHA256
        or snapshot.frame_fnv1a != _INTERNAL_N1_FRAME_FNV1A
        or fnv1a(snapshot.frame) != _INTERNAL_N1_FRAME_FNV1A
        or len(snapshot.frame) != FRAME_BYTES
        or len(snapshot.controllers) != 2
        or tuple(dict(record) for record in snapshot.controllers)
        != tuple(dict(record) for record in recalculated_controllers)
        or snapshot.controllers[0].get("dtm_fnv1a")
        != _INTERNAL_N1_CS1_DTM_FNV1A
        or snapshot.controllers[1].get("dtm_fnv1a")
        != _INTERNAL_N1_CS2_DTM_FNV1A
    ):
        raise Rc2gQualityRefreshError(
            "internal prevalidated snapshot is not the sole frozen N1 low-balanced raster"
        )
    manifest_classification = snapshot.manifest.get("classification")
    if (
        not isinstance(manifest_classification, Mapping)
        or manifest_classification.get("upload_authorized") is not False
        or manifest_classification.get("simulation_only") is not True
        or manifest_classification.get("hardware_tested") is not False
    ):
        raise Rc2gQualityRefreshError(
            "fixed N1 source manifest lost its fail-closed classification"
        )

    if set(binding) != {
        "schema_version",
        "kind",
        "fixed_action_id",
        "pilot_id",
        "phase",
        "fixed_cell",
        "claim_scope",
        "primer_result",
        "candidate",
        "classification",
    }:
        raise Rc2gQualityRefreshError("fixed N1 evidence binding fields changed")
    if (
        binding.get("schema_version") != 1
        or binding.get("kind") != _INTERNAL_N1_BINDING_KIND
        or binding.get("fixed_action_id") != _INTERNAL_N1_ACTION_ID
        or binding.get("pilot_id") != _INTERNAL_N1_PILOT_ID
        or binding.get("phase") != "N1"
        or binding.get("fixed_cell") != "low-balanced"
        or binding.get("classification") != _INTERNAL_N1_CLASSIFICATION
    ):
        raise Rc2gQualityRefreshError("fixed N1 evidence binding identity changed")
    claim_scope = binding.get("claim_scope")
    expected_claim_scope = {
        "registry_id": CLAIM_REGISTRY_ID,
        "fixed_filename": _INTERNAL_N1_ACTION_ID,
        "workspace_global_fixed_action": True,
        "partitioned_by_primer_result_sha256": False,
        "partitioned_by_result_directory": False,
        "campaign_id_override_supported": False,
    }
    if claim_scope != expected_claim_scope or fixed_claim_filename != _INTERNAL_N1_ACTION_ID:
        raise Rc2gQualityRefreshError(
            "fixed N1 claim scope or filename changed"
        )
    primer_result = binding.get("primer_result")
    if not isinstance(primer_result, Mapping) or set(primer_result) != {
        "sha256",
        "attempt_id",
        "claim_sha256",
        "action_id",
        "action_identity_sha256",
        "completed_job_id",
        "completed_operation_id",
        "frame_sha256",
        "frame_fnv1a",
        "cs1_dtm_fnv1a",
        "cs2_dtm_fnv1a",
        "manual_visual_pass_must_be_confirmed_separately",
        "job_raw_canonical_sha256",
        "diagnostic_raw_canonical_sha256",
    }:
        raise Rc2gQualityRefreshError("fixed N1 primer-result binding fields changed")
    _require_sha256(primer_result.get("sha256"), label="fixed N1 primer result SHA-256")
    _require_sha256(primer_result.get("claim_sha256"), label="fixed N1 primer claim SHA-256")
    _require_sha256(
        primer_result.get("job_raw_canonical_sha256"),
        label="fixed N1 primer job evidence SHA-256",
    )
    _require_sha256(
        primer_result.get("diagnostic_raw_canonical_sha256"),
        label="fixed N1 primer diagnostic evidence SHA-256",
    )
    if (
        not isinstance(primer_result.get("attempt_id"), str)
        or not primer_result.get("attempt_id")
        or primer_result.get("action_id") != _INTERNAL_N1_PRIMER_ACTION_ID
        or primer_result.get("action_identity_sha256")
        != _INTERNAL_N1_PRIMER_ACTION_SHA256
        or primer_result.get("completed_job_id") != 1
        or primer_result.get("completed_operation_id") != 1
        or primer_result.get("frame_sha256") != _INTERNAL_N1_MAP_FRAME_SHA256
        or primer_result.get("frame_fnv1a") != _INTERNAL_N1_MAP_FRAME_FNV1A
        or primer_result.get("cs1_dtm_fnv1a")
        != _INTERNAL_N1_MAP_CS1_DTM_FNV1A
        or primer_result.get("cs2_dtm_fnv1a")
        != _INTERNAL_N1_MAP_CS2_DTM_FNV1A
        or primer_result.get("manual_visual_pass_must_be_confirmed_separately")
        is not True
    ):
        raise Rc2gQualityRefreshError("fixed N1 primer-result binding changed")
    expected_job = expected_exact_prior_evidence.get("job_raw")
    expected_diagnostic = expected_exact_prior_evidence.get("diagnostic_raw")
    if (
        set(expected_exact_prior_evidence) != {"job_raw", "diagnostic_raw"}
        or not isinstance(expected_job, Mapping)
        or not isinstance(expected_diagnostic, Mapping)
        or _sha256(_canonical_json(expected_job))
        != primer_result.get("job_raw_canonical_sha256")
        or _sha256(_canonical_json(expected_diagnostic))
        != primer_result.get("diagnostic_raw_canonical_sha256")
    ):
        raise Rc2gQualityRefreshError("fixed N1 exact prior evidence binding changed")
    candidate = binding.get("candidate")
    expected_candidate = {
        "source_bundle_manifest_file_sha256": _INTERNAL_N1_MANIFEST_FILE_SHA256,
        "source_bundle_manifest_canonical_sha256": (
            _INTERNAL_N1_MANIFEST_CANONICAL_SHA256
        ),
        "source_bundle_upload_authorized": False,
        "single_exact_action_override_only": True,
        "old_low_spatial_manifest_sha256": _INTERNAL_N1_OLD_MANIFEST_SHA256,
        "byte_identical_to_old_successful_low_spatial_frame": True,
        "frame_sha256": _INTERNAL_N1_FRAME_SHA256,
        "frame_fnv1a": f"0x{_INTERNAL_N1_FRAME_FNV1A:08X}",
        "cs1_dtm_fnv1a": _INTERNAL_N1_CS1_DTM_FNV1A,
        "cs2_dtm_fnv1a": _INTERNAL_N1_CS2_DTM_FNV1A,
        "strict_preview_sha256": _INTERNAL_N1_PREVIEW_SHA256,
    }
    if candidate != expected_candidate:
        raise Rc2gQualityRefreshError("fixed N1 candidate binding changed")

    if dict(additional_confirmations) != {
        "primer_visual_fidelity_pass": True,
        "no_esp32_reboot_since_primer": True,
        "no_j2_disconnect_since_primer": True,
        "fixed_low_balanced_pilot_scope_acknowledged": True,
    }:
        raise Rc2gQualityRefreshError("fixed N1 additional confirmations changed")
    if dict(result_classification) != _INTERNAL_N1_CLASSIFICATION:
        raise Rc2gQualityRefreshError("fixed N1 result classification changed")
    if list(manual_observations) != _INTERNAL_N1_MANUAL_OBSERVATIONS:
        raise Rc2gQualityRefreshError("fixed N1 manual observation contract changed")
    expected_metadata = {
        "fixed_action_id": _INTERNAL_N1_ACTION_ID,
        "pilot_id": _INTERNAL_N1_PILOT_ID,
        "primer_result_sha256": primer_result["sha256"],
        "source_bundle_upload_authorized": False,
        "single_exact_action_override_only": True,
    }
    if dict(fixed_result_metadata) != expected_metadata:
        raise Rc2gQualityRefreshError("fixed N1 result metadata changed")
    if (
        expected_prior_job_id != 1
        or expected_prior_operation_id != 1
        or expected_prior_frame_sha256 != _INTERNAL_N1_MAP_FRAME_SHA256
        or expected_prior_frame_fnv1a != int(_INTERNAL_N1_MAP_FRAME_FNV1A, 16)
        or expected_prior_cs1_dtm_fnv1a
        != int(_INTERNAL_N1_MAP_CS1_DTM_FNV1A, 16)
        or expected_prior_cs2_dtm_fnv1a
        != int(_INTERNAL_N1_MAP_CS2_DTM_FNV1A, 16)
        or expected_target_job_id != 2
        or expected_target_operation_id != 2
    ):
        raise Rc2gQualityRefreshError("fixed N1 prior/target job contract changed")


def required_authorization_confirmation(action_identity_sha256: str) -> str:
    normalized = _require_sha256(
        action_identity_sha256, label="action identity SHA-256"
    )
    return f"{AUTHORIZATION_PREFIX}{normalized.upper()}{AUTHORIZATION_SUFFIX}"


def _build_run_contract(
    snapshot: _CandidateSnapshot,
    *,
    expected_prior_job_id: int,
    expected_prior_operation_id: int,
    expected_prior_frame_sha256: str,
    expected_prior_frame_fnv1a: int,
    expected_prior_cs1_dtm_fnv1a: int,
    expected_prior_cs2_dtm_fnv1a: int,
    expected_target_job_id: int,
    expected_target_operation_id: int,
    fixed_external_evidence_binding: Optional[Mapping[str, Any]] = None,
) -> _RunContract:
    prior_job = _require_u32(
        expected_prior_job_id, label="expected prior job ID", nonzero=True
    )
    prior_operation = _require_u32(
        expected_prior_operation_id,
        label="expected prior operation ID",
        nonzero=True,
    )
    prior_frame_sha256 = _require_sha256(
        expected_prior_frame_sha256, label="expected prior frame SHA-256"
    )
    prior_frame = _require_u32(
        expected_prior_frame_fnv1a, label="expected prior frame FNV-1a"
    )
    prior_cs1 = _require_u32(
        expected_prior_cs1_dtm_fnv1a,
        label="expected prior CS1 DTM FNV-1a",
    )
    prior_cs2 = _require_u32(
        expected_prior_cs2_dtm_fnv1a,
        label="expected prior CS2 DTM FNV-1a",
    )
    target_job = _require_u32(
        expected_target_job_id, label="expected target job ID", nonzero=True
    )
    target_operation = _require_u32(
        expected_target_operation_id,
        label="expected target operation ID",
        nonzero=True,
    )
    if target_job != _next_nonzero_u32(prior_job):
        raise Rc2gQualityRefreshError("target job ID must be the next non-zero uint32 job")
    if target_operation != _next_nonzero_u32(prior_operation):
        raise Rc2gQualityRefreshError(
            "target operation ID must be the next non-zero uint32 operation"
        )
    action_identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTION_IDENTITY_KIND,
        "candidate": {
            "manifest_file_sha256": snapshot.manifest_file_sha256,
            "manifest_canonical_sha256": snapshot.manifest_canonical_sha256,
            "manifest_kind": snapshot.manifest.get("kind"),
            "algorithm": snapshot.algorithm,
            "frame_bytes": FRAME_BYTES,
            "frame_sha256": snapshot.frame_sha256,
            "frame_fnv1a": f"0x{snapshot.frame_fnv1a:08X}",
            "controllers": [dict(record) for record in snapshot.controllers],
        },
        "prior": {
            "job_id": prior_job,
            "operation_id": prior_operation,
            "frame_sha256": prior_frame_sha256,
            "frame_fnv1a": f"0x{prior_frame:08X}",
            "cs1_dtm_fnv1a": f"0x{prior_cs1:08X}",
            "cs2_dtm_fnv1a": f"0x{prior_cs2:08X}",
            "frame_sha256_evidence_scope": (
                "offline frozen action identity; firmware report does not expose SHA-256"
            ),
            "required_state": "completed",
            "nested_busy_edge_required": True,
        },
        "target": {
            "job_id": target_job,
            "operation_id": target_operation,
            "frame_fnv1a": f"0x{snapshot.frame_fnv1a:08X}",
            "required_state": "completed",
            "nested_busy_edge_required": True,
        },
        "firmware": {
            "build_tag": EXPECTED_BUILD_TAG,
            "driver_api": EXPECTED_DRIVER_API,
            "panel": f"{WIDTH}x{HEIGHT}",
            "frame_bytes": FRAME_BYTES,
            "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
            "controller_mappings": [
                _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
            ],
        },
        "timing": {
            "job_duration_ms": list(NOMINAL_JOB_DURATION_MS),
            "maximum_queue_delay_ms": MAX_QUEUE_DELAY_MS,
            "maximum_job_driver_duration_delta_ms": (
                MAX_JOB_DRIVER_DURATION_DELTA_MS
            ),
            "stages_ms": {
                name: list(bounds)
                for name, bounds in NOMINAL_STAGE_TIMING_MS.items()
            },
        },
        "gpio_policy": {
            "required_panel_outputs": dict(EXPECTED_PANEL_OUTPUTS_LOW),
            "busy_after_rst_low": "informational",
            "nested_command_edges": "authoritative",
        },
        "exact_action": dict(EXACT_ACTION),
    }
    if fixed_external_evidence_binding is not None:
        if not isinstance(fixed_external_evidence_binding, Mapping):
            raise Rc2gQualityRefreshError(
                "fixed external evidence binding must be an object"
            )
        # Canonicalize once here so callers cannot smuggle a mutable or
        # non-JSON value into the permanent action identity.
        try:
            frozen_binding = json.loads(
                _canonical_json(dict(fixed_external_evidence_binding)).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Rc2gQualityRefreshError(
                f"fixed external evidence binding is invalid: {error}"
            ) from error
        action_identity["fixed_external_evidence_binding"] = frozen_binding
    action_sha256 = _sha256(_canonical_json(action_identity))
    return _RunContract(
        snapshot=snapshot,
        expected_prior_job_id=prior_job,
        expected_prior_operation_id=prior_operation,
        expected_prior_frame_sha256=prior_frame_sha256,
        expected_prior_frame_fnv1a=prior_frame,
        expected_prior_cs1_dtm_fnv1a=prior_cs1,
        expected_prior_cs2_dtm_fnv1a=prior_cs2,
        expected_target_job_id=target_job,
        expected_target_operation_id=target_operation,
        action_identity=action_identity,
        action_identity_sha256=action_sha256,
        required_authorization_confirmation=required_authorization_confirmation(
            action_sha256
        ),
    )


def describe_rc2g_quality_action(
    candidate_dir: Path,
    *,
    expected_manifest_sha256: str,
    expected_prior_job_id: int,
    expected_prior_operation_id: int,
    expected_prior_frame_sha256: str,
    expected_prior_frame_fnv1a: int,
    expected_prior_cs1_dtm_fnv1a: int,
    expected_prior_cs2_dtm_fnv1a: int,
    expected_target_job_id: int,
    expected_target_operation_id: int,
) -> dict[str, Any]:
    """Deep-validate locally and print the exact per-run authorization identity."""

    snapshot = _load_candidate_snapshot(candidate_dir, expected_manifest_sha256)
    contract = _build_run_contract(
        snapshot,
        expected_prior_job_id=expected_prior_job_id,
        expected_prior_operation_id=expected_prior_operation_id,
        expected_prior_frame_sha256=expected_prior_frame_sha256,
        expected_prior_frame_fnv1a=expected_prior_frame_fnv1a,
        expected_prior_cs1_dtm_fnv1a=expected_prior_cs1_dtm_fnv1a,
        expected_prior_cs2_dtm_fnv1a=expected_prior_cs2_dtm_fnv1a,
        expected_target_job_id=expected_target_job_id,
        expected_target_operation_id=expected_target_operation_id,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "authorization-description-only",
        "device_io_performed": False,
        "claim_created": False,
        "action_identity": dict(contract.action_identity),
        "action_identity_sha256": contract.action_identity_sha256,
        "required_authorization_confirmation": (
            contract.required_authorization_confirmation
        ),
    }


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(
            result_dir, label="RC2G quality result directory"
        )
    except LocalPathSafetyError as error:
        raise Rc2gQualityRefreshError(str(error)) from error
    if os.path.lexists(result_dir):
        raise Rc2gQualityRefreshError(
            "result directory already exists; refusing overwrite or rerun"
        )
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise Rc2gQualityRefreshError(
            f"result parent does not exist: {error}"
        ) from error
    if not parent.is_dir():
        raise Rc2gQualityRefreshError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise Rc2gQualityRefreshError(
            "result directory already exists; refusing overwrite or rerun"
        )
    return destination


def _authorization_registry() -> Path:
    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(
            path, label="RC2G quality authorization registry"
        )
    except LocalPathSafetyError as error:
        raise Rc2gQualityRefreshError(str(error)) from error
    if os.path.lexists(path) and path.is_symlink():
        raise Rc2gQualityRefreshError("authorization registry must not be a symlink")
    try:
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise Rc2gQualityRefreshError(
                "authorization registry parent must be inside the workspace"
            )
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except OSError as error:
        raise Rc2gQualityRefreshError(
            f"could not create authorization registry: {error}"
        ) from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(
        registry, workspace
    ):
        raise Rc2gQualityRefreshError("authorization registry escaped the workspace")
    return registry


def _claim_action(
    contract: _RunContract,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    authorization_confirmation: str,
    confirmations: Mapping[str, Any],
    fixed_claim_filename: Optional[str] = None,
) -> _Claim:
    """Permanently consume the canonical action before result or network I/O."""

    registry = _authorization_registry()
    if _is_within(result_destination, registry):
        raise Rc2gQualityRefreshError(
            "result directory must not be inside the authorization registry"
        )
    filename = contract.action_identity_sha256
    if fixed_claim_filename is not None:
        if (
            not isinstance(fixed_claim_filename, str)
            or not fixed_claim_filename
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in fixed_claim_filename
            )
        ):
            raise Rc2gQualityRefreshError(
                "fixed claim filename must contain only lowercase ASCII letters, digits, '-' or '_'"
            )
        filename = fixed_claim_filename
    destination = registry / filename
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "action_identity": dict(contract.action_identity),
        "action_identity_sha256": contract.action_identity_sha256,
        "required_authorization_confirmation": (
            contract.required_authorization_confirmation
        ),
        "authorization_confirmation": authorization_confirmation,
        "confirmations": dict(confirmations),
        "result_directory": str(result_destination),
        "exact_action": dict(EXACT_ACTION),
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    fixed_binding = contract.action_identity.get("fixed_external_evidence_binding")
    if isinstance(fixed_binding, Mapping):
        record["fixed_action_id"] = fixed_binding.get("fixed_action_id")
        record["pilot_id"] = fixed_binding.get("pilot_id")
        record["exact_action"] = {
            **dict(EXACT_ACTION),
            "action_id": fixed_binding.get("fixed_action_id"),
        }
    payload = _canonical_json(record)
    claim = _Claim(registry, filename, _sha256(payload), record)
    temporary = registry / f".{filename}.tmp-{uuid.uuid4().hex}"
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
        if linked:
            raise Rc2gQualityRefreshUnknown(
                "action claim exists after cleanup failure; do not retry"
            ) from error
        raise Rc2gQualityRefreshError(
            "this exact RC2G quality action was already permanently consumed; do not retry"
        ) from error
    except BaseException as error:
        if linked:
            raise Rc2gQualityRefreshUnknown(
                "action claim exists after claim processing failure; do not retry"
            ) from error
        if not isinstance(error, OSError):
            raise
        raise Rc2gQualityRefreshError(
            f"could not atomically claim RC2G quality action: {error}"
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
    claim: _Claim,
) -> Path:
    if _is_within(destination, snapshot.directory):
        raise Rc2gQualityRefreshError(
            "result directory must not be inside the candidate bundle"
        )
    if _is_within(destination, claim.registry):
        raise Rc2gQualityRefreshError(
            "result directory must not be inside the authorization registry"
        )
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise Rc2gQualityRefreshError(
            "result directory appeared; refusing overwrite or rerun"
        ) from error
    except OSError as error:
        raise Rc2gQualityRefreshError(
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
        raise Rc2gQualityRefreshError(
            f"{name} already exists; refusing overwrite"
        ) from error
    except OSError as error:
        if linked:
            raise Rc2gQualityRefreshError(
                f"{name} was committed but staging cleanup failed"
            ) from error
        raise Rc2gQualityRefreshError(
            f"could not atomically write {name}: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


class _AuditedRequester:
    """Allowlist device routes and hard-limit the sole state-changing request."""

    _ALLOWED = {
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("POST", "/api/frame"),
    }

    def __init__(self, requester: Callable[..., tuple[int, str]]) -> None:
        self._requester = requester
        self.calls: list[dict[str, Any]] = []
        self.post_attempt_count = 0
        self.post_issued_count = 0

    def __call__(
        self,
        base_url: str,
        endpoint: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        normalized_method = method.upper()
        entry: dict[str, Any] = {
            "index": len(self.calls) + 1,
            "method": normalized_method,
            "endpoint": endpoint,
            "timeout_seconds": timeout,
            "request_bytes": len(data) if data is not None else 0,
        }
        if data is not None:
            entry["request_sha256"] = _sha256(bytes(data))
        self.calls.append(entry)
        if (normalized_method, endpoint) not in self._ALLOWED:
            entry["outcome"] = "blocked_route"
            raise Rc2gQualityRefreshError(
                f"request route is not allowlisted: {normalized_method} {endpoint}"
            )
        if normalized_method == "POST":
            self.post_attempt_count += 1
            if endpoint != "/api/frame" or self.post_issued_count >= 1:
                entry["outcome"] = "blocked_additional_post"
                raise Rc2gQualityRefreshError(
                    "RC2G quality action permits exactly one issued POST /api/frame"
                )
            self.post_issued_count += 1
        try:
            status, body = self._requester(
                base_url,
                endpoint,
                method=normalized_method,
                data=data,
                timeout=timeout,
            )
        except BaseException as error:
            entry["outcome"] = "exception"
            entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            raise
        entry["outcome"] = "response"
        entry["status"] = status
        if isinstance(body, str):
            encoded = body.encode("utf-8")
            entry["response_bytes"] = len(encoded)
            entry["response_sha256"] = _sha256(encoded)
        else:
            entry["response_bytes"] = None
            entry["response_sha256"] = None
        return status, body

    def snapshot(self) -> dict[str, Any]:
        return {
            "post_attempt_count": self.post_attempt_count,
            "post_issued_count": self.post_issued_count,
            "calls": [dict(call) for call in self.calls],
        }


def _get_json_object(
    base_url: str,
    endpoint: str,
    *,
    label: str,
    requester: _AuditedRequester,
) -> Mapping[str, Any]:
    status, body = requester(
        base_url, endpoint, method="GET", data=None, timeout=20.0
    )
    if status != 200:
        raise Rc2gQualityRefreshError(
            f"{label} returned HTTP {status}: {body[:200]}"
        )
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError) as error:
        raise Rc2gQualityRefreshError(
            f"{label} is not valid JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise Rc2gQualityRefreshError(f"{label} must be a JSON object")
    return value


def _expected_version_static() -> dict[str, Any]:
    return {
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


def _validate_version(version: Mapping[str, Any], *, label: str) -> None:
    if EXPECTED_BUILD_TAG not in BUSY_TRACE_BUILD_TAGS:
        raise Rc2gQualityRefreshError(
            "EXPECTED_BUILD_TAG must be an allowlisted RC2G BUSY-trace build"
        )
    if any(
        version.get(key) != value
        for key, value in _expected_version_static().items()
    ):
        raise Rc2gQualityRefreshError(
            f"{label} build/API/panel/SPI/mappings are not the frozen RC2G contract"
        )


def _validate_gpio_snapshot(
    value: Mapping[str, Any], *, label: str
) -> dict[str, int]:
    if set(value) != {"busy", "rst", "cs", "cs2"}:
        raise Rc2gQualityRefreshError(
            f"{label} fields are not the strict GPIO contract"
        )
    snapshot: dict[str, int] = {}
    for key in ("busy", "rst", "cs", "cs2"):
        level = value.get(key)
        if type(level) is not int or level not in (0, 1):
            raise Rc2gQualityRefreshError(
                f"{label}.{key} must be integer level 0 or 1"
            )
        snapshot[key] = level
    if any(
        snapshot[key] != expected
        for key, expected in EXPECTED_PANEL_OUTPUTS_LOW.items()
    ):
        raise Rc2gQualityRefreshError(
            f"{label} RST/CS1/CS2 outputs are not all low"
        )
    return snapshot


def _gpio_evidence(snapshot: Mapping[str, int]) -> dict[str, Any]:
    return {
        "raw": dict(snapshot),
        "panel_outputs_low_verified": True,
        "busy_level": snapshot["busy"],
        "busy_after_rst_low_is_informational": True,
        "busy_interpretation": (
            "sample retained; nested per-command BUSY edges are authoritative"
        ),
    }


def _u32_duration(start: int, finish: int) -> int:
    return (finish - start) & 0xFFFFFFFF


def _validate_timing(
    job: Mapping[str, Any],
    raw_diagnostic: Mapping[str, Any],
    *,
    label: str,
) -> None:
    timestamps = tuple(
        job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms")
    )
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFFFFFF
        for value in timestamps
    ):
        raise Rc2gQualityRefreshError(f"{label} job timestamps are not uint32")
    queued, started, finished = timestamps
    queue_delay = _u32_duration(queued, started)
    job_duration = _u32_duration(started, finished)
    if queue_delay > MAX_QUEUE_DELAY_MS or not (
        NOMINAL_JOB_DURATION_MS[0]
        <= job_duration
        <= NOMINAL_JOB_DURATION_MS[1]
    ):
        raise Rc2gQualityRefreshError(
            f"{label} job timing is outside the nominal RC2G envelope"
        )
    for field, (minimum, maximum) in NOMINAL_STAGE_TIMING_MS.items():
        value = raw_diagnostic.get(field)
        if type(value) is not int or not minimum <= value <= maximum:
            raise Rc2gQualityRefreshError(
                f"{label} {field} is outside {minimum}..{maximum} ms"
            )
    minimum_total = sum(
        int(raw_diagnostic[field])
        for field in (
            "cs1_upload_ms",
            "cs2_upload_ms",
            "pon_ms",
            "drf_ms",
            "pof_ms",
            "post_psr_ms",
        )
    )
    if int(raw_diagnostic["total_ms"]) < minimum_total:
        raise Rc2gQualityRefreshError(
            f"{label} total_ms is shorter than uploads plus recorded waits"
        )
    if (
        abs(job_duration - int(raw_diagnostic["total_ms"]))
        > MAX_JOB_DRIVER_DURATION_DELTA_MS
    ):
        raise Rc2gQualityRefreshError(
            f"{label} job duration and driver total differ beyond the nominal gate"
        )


def _validate_normalized_busy_trace(
    trace: object, *, label: str
) -> Mapping[str, Any]:
    if not isinstance(trace, Mapping):
        raise Rc2gQualityRefreshError(f"{label} nested BUSY trace is required")
    if (
        trace.get("schema_version") != 1
        or trace.get("idle_level") != 1
        or trace.get("command_edge_contract_verified") is not True
        or trace.get("safe_finish_pin_levels_verified") is not True
        or trace.get("busy_after_rst_low_is_informational") is not True
    ):
        raise Rc2gQualityRefreshError(
            f"{label} nested BUSY trace contract is not verified"
        )
    stages = trace.get("stages")
    if not isinstance(stages, Mapping) or set(stages) != {
        "reset",
        "pon",
        "drf",
        "pof",
        "post_psr",
    }:
        raise Rc2gQualityRefreshError(f"{label} BUSY stages are incomplete")
    reset = stages.get("reset")
    if (
        not isinstance(reset, Mapping)
        or reset.get("gate_entry_level") != 255
        or reset.get("pre_command_level") != 255
        or reset.get("pre_command_idle_ok") is not False
        or reset.get("assertion_after_idle") is not False
        or reset.get("wait_exit_level") != 1
    ):
        raise Rc2gQualityRefreshError(f"{label} RESET BUSY evidence is invalid")
    for stage_name in ("pon", "drf", "pof"):
        stage = stages.get(stage_name)
        if (
            not isinstance(stage, Mapping)
            or stage.get("gate_entry_level") != 1
            or stage.get("pre_command_level") != 1
            or stage.get("pre_command_idle_ok") is not True
            or stage.get("assertion_after_idle") is not True
            or stage.get("wait_exit_level") != 1
        ):
            raise Rc2gQualityRefreshError(
                f"{label} {stage_name.upper()} lacks idle-before-command/new-edge proof"
            )
    post_psr = stages.get("post_psr")
    if (
        not isinstance(post_psr, Mapping)
        or post_psr.get("assertion_after_idle") is not False
        or post_psr.get("wait_exit_level") != 1
    ):
        raise Rc2gQualityRefreshError(
            f"{label} post-PSR informational BUSY evidence is invalid"
        )
    safe_finish = trace.get("safe_finish")
    final_gpio = trace.get("final_gpio")
    if (
        not isinstance(safe_finish, Mapping)
        or safe_finish.get("busy_before_pins_low") != 1
    ):
        raise Rc2gQualityRefreshError(
            f"{label} did not enter safe finish with BUSY idle"
        )
    if not isinstance(final_gpio, Mapping):
        raise Rc2gQualityRefreshError(f"{label} final GPIO trace is missing")
    _validate_gpio_snapshot(final_gpio, label=f"{label} final GPIO")
    # Both BUSY samples occur after RST is low and remain informational.  The
    # asynchronous input may legitimately change between those two reads, so
    # they are preserved independently and are deliberately not equated.
    return trace


def _validate_prior_raw_diagnostic(
    raw: Mapping[str, Any],
    job: Mapping[str, Any],
    contract: _RunContract,
) -> Mapping[str, Any]:
    label = "prior diagnostic"
    required_equal = {
        "schema_version": 2,
        "firmware_build_tag": EXPECTED_BUILD_TAG,
        "driver_api_version": EXPECTED_DRIVER_API,
        "job_id": contract.expected_prior_job_id,
        "job_action": "uploaded_frame",
        "job_state": "completed",
        "job_result": True,
        "job_operation_id": contract.expected_prior_operation_id,
        "operation_id": contract.expected_prior_operation_id,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "input_fnv1a": contract.expected_prior_frame_fnv1a,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
    }
    if any(
        raw.get(key) != value or type(raw.get(key)) is not type(value)
        for key, value in required_equal.items()
    ):
        raise Rc2gQualityRefreshError(
            "prior diagnostic identity/sequence/safe-finish contract is incomplete"
        )
    for report_key, job_key in (
        ("job_queued_at_ms", "queued_at_ms"),
        ("job_started_at_ms", "started_at_ms"),
        ("job_finished_at_ms", "finished_at_ms"),
    ):
        if raw.get(report_key) != job.get(job_key):
            raise Rc2gQualityRefreshError(
                f"prior diagnostic {report_key} differs from prior job"
            )
    if raw.get("last_wait_ms") != raw.get("post_psr_ms"):
        raise Rc2gQualityRefreshError(
            "prior diagnostic last_wait_ms differs from post_psr_ms"
        )
    raw_mapping = raw.get("mapping")
    expected_mapping = {
        "cs1_source_half": 0,
        "cs1_flip_x": False,
        "cs1_flip_y": False,
        "cs1_nibble_swap": False,
        "cs2_source_half": 1,
        "cs2_flip_x": False,
        "cs2_flip_y": False,
        "cs2_nibble_swap": False,
    }
    if raw_mapping != expected_mapping:
        raise Rc2gQualityRefreshError(
            "prior diagnostic controller mapping is not frozen"
        )
    expected_dtm = {
        "cs1_dtm_fnv1a": contract.expected_prior_cs1_dtm_fnv1a,
        "cs2_dtm_fnv1a": contract.expected_prior_cs2_dtm_fnv1a,
    }
    for field, expected in expected_dtm.items():
        actual = _require_u32(raw.get(field), label=f"prior diagnostic {field}")
        if actual != expected:
            raise Rc2gQualityRefreshError(
                f"prior diagnostic {field} does not match the frozen prior DTM"
            )
    _validate_timing(job, raw, label="prior")
    wait_ms = {
        stage: int(raw[f"{stage}_ms"])
        for stage in ("pon", "drf", "pof", "post_psr")
    }
    try:
        trace = _validate_busy_trace(raw, wait_ms)
    except FrameToolError as error:
        raise Rc2gQualityRefreshError(
            f"prior nested BUSY trace validation failed: {error}"
        ) from error
    return _validate_normalized_busy_trace(trace, label=label)


def _validate_prior(
    base_url: str,
    requester: _AuditedRequester,
    contract: _RunContract,
    expected_exact_prior_evidence: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    try:
        version = _preflight_version(
            base_url, requester, FIXED_CONTROLLER_MAPPINGS
        )
    except FrameToolError as error:
        raise Rc2gQualityRefreshError(
            f"prior firmware preflight failed: {error}"
        ) from error
    _validate_version(version, label="prior firmware")
    job = _get_json_object(
        base_url, "/api/job", label="prior job", requester=requester
    )
    required_job_keys = {
        "job_id",
        "action",
        "state",
        "result",
        "queued_at_ms",
        "started_at_ms",
        "finished_at_ms",
        "frame_fnv1a",
    }
    if set(job) != required_job_keys:
        raise Rc2gQualityRefreshError(
            "prior job fields are not the strict job contract"
        )
    try:
        state = _validate_job(
            job,
            contract.expected_prior_job_id,
            contract.expected_prior_frame_fnv1a,
        )
    except FrameToolError as error:
        raise Rc2gQualityRefreshError(
            f"prior job validation failed: {error}"
        ) from error
    if state != "completed":
        raise Rc2gQualityRefreshError("prior job is not completed")
    raw_diagnostic = _get_json_object(
        base_url,
        "/api/diagnostic/report",
        label="prior diagnostic",
        requester=requester,
    )
    trace = _validate_prior_raw_diagnostic(raw_diagnostic, job, contract)
    if expected_exact_prior_evidence is not None:
        expected_job = expected_exact_prior_evidence.get("job_raw")
        expected_diagnostic = expected_exact_prior_evidence.get("diagnostic_raw")
        if (
            not isinstance(expected_job, Mapping)
            or not isinstance(expected_diagnostic, Mapping)
            or dict(job) != dict(expected_job)
            or dict(raw_diagnostic) != dict(expected_diagnostic)
        ):
            raise Rc2gQualityRefreshError(
                "live prior is not the exact stored primer job/operation evidence"
            )
    gpio_raw = _get_json_object(
        base_url,
        "/api/diagnostic/status",
        label="prior GPIO",
        requester=requester,
    )
    gpio = _validate_gpio_snapshot(gpio_raw, label="prior GPIO")
    return {
        "version": dict(version),
        "job": dict(job),
        "diagnostic_raw": dict(raw_diagnostic),
        "nested_busy_trace": dict(trace),
        "gpio": _gpio_evidence(gpio),
        "expected_identity": dict(contract.action_identity["prior"]),
    }


def _validate_network_report(
    report: object,
    contract: _RunContract,
) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise Rc2gQualityRefreshError("target network report must be an object")
    if (
        report.get("protocol_verified") is not True
        or report.get("hardware_tested") is not False
    ):
        raise Rc2gQualityRefreshError(
            "target report lost its fail-closed protocol classification"
        )
    scope = report.get("verified_scope")
    if not isinstance(scope, list) or not REQUIRED_VERIFIED_SCOPE.issubset(scope):
        raise Rc2gQualityRefreshError(
            "target report lacks RC2G nested BUSY verified scope"
        )
    preflight = report.get("preflight")
    if not isinstance(preflight, Mapping):
        raise Rc2gQualityRefreshError("target firmware preflight is missing")
    _validate_version(preflight, label="target firmware")
    job = report.get("job")
    if not isinstance(job, Mapping):
        raise Rc2gQualityRefreshError("target completed job is missing")
    try:
        state = _validate_job(
            job,
            contract.expected_target_job_id,
            contract.snapshot.frame_fnv1a,
        )
    except FrameToolError as error:
        raise Rc2gQualityRefreshError(
            f"target job validation failed: {error}"
        ) from error
    if (
        state != "completed"
        or report.get("job_id") != contract.expected_target_job_id
    ):
        raise Rc2gQualityRefreshError(
            "target result is not the exact completed next job"
        )
    diagnostic = report.get("diagnostic")
    if (
        not isinstance(diagnostic, Mapping)
        or diagnostic.get("operation_id")
        != contract.expected_target_operation_id
        or diagnostic.get("job_operation_id")
        != contract.expected_target_operation_id
        or diagnostic.get("job_driver_operation_identity_matched") is not True
        or diagnostic.get("sequence_verified") is not True
        or diagnostic.get("required_busy_stages_verified") is not True
        or diagnostic.get("busy_timeout") is not False
        or diagnostic.get("safe_finish_verified") is not True
    ):
        raise Rc2gQualityRefreshError(
            "target job/operation/sequence/safe-finish binding is incomplete"
        )
    _validate_normalized_busy_trace(
        diagnostic.get("busy_trace"), label="target diagnostic"
    )
    expected_physical = [
        {
            "controller": record["controller"],
            "mapping": record["mapping"],
            "dtm_bytes": record["dtm_bytes"],
            "dtm_fnv1a": int(str(record["dtm_fnv1a"]), 16),
        }
        for record in contract.snapshot.controllers
    ]
    if diagnostic.get("physical_controllers") != expected_physical:
        raise Rc2gQualityRefreshError(
            "target DTM identities are not the frozen candidate streams"
        )
    timestamps = tuple(
        job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms")
    )
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFFFFFF
        for value in timestamps
    ):
        raise Rc2gQualityRefreshError("target job timestamps are not uint32")
    queued, started, finished = timestamps
    if _u32_duration(queued, started) > MAX_QUEUE_DELAY_MS or not (
        NOMINAL_JOB_DURATION_MS[0]
        <= _u32_duration(started, finished)
        <= NOMINAL_JOB_DURATION_MS[1]
    ):
        raise Rc2gQualityRefreshError(
            "target job timing is outside the nominal RC2G envelope"
        )
    return report


def _validate_target_raw_diagnostic(
    raw: Mapping[str, Any],
    report: Mapping[str, Any],
    contract: _RunContract,
) -> Mapping[str, Any]:
    version = report.get("preflight")
    job = report.get("job")
    if not isinstance(version, Mapping) or not isinstance(job, Mapping):
        raise Rc2gQualityRefreshError(
            "target report cannot bind the raw diagnostic"
        )
    try:
        normalized = _validate_diagnostic(
            raw,
            contract.snapshot.frame,
            FIXED_CONTROLLER_MAPPINGS,
            version,
            job,
        )
    except FrameToolError as error:
        raise Rc2gQualityRefreshError(
            f"target raw diagnostic validation failed: {error}"
        ) from error
    if (
        normalized.get("operation_id")
        != contract.expected_target_operation_id
        or normalized.get("job_operation_id")
        != contract.expected_target_operation_id
    ):
        raise Rc2gQualityRefreshError(
            "target raw diagnostic operation identity changed"
        )
    if normalized != report.get("diagnostic"):
        raise Rc2gQualityRefreshError(
            "target immutable diagnostic changed between verified reads"
        )
    _validate_timing(job, raw, label="target")
    _validate_normalized_busy_trace(
        normalized.get("busy_trace"), label="target raw diagnostic"
    )
    return normalized


def _perform_refresh_once(
    base_url: str,
    frame: bytes,
    requester: _AuditedRequester,
    *,
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
) -> Mapping[str, Any]:
    # Exactly one call.  perform_refresh issues one POST /api/frame and uses
    # GET only for preflight, polling, and the immutable diagnostic report.
    return perform_refresh(
        base_url,
        frame,
        expected_mappings=FIXED_CONTROLLER_MAPPINGS,
        job_timeout_s=job_timeout_s,
        poll_interval_s=poll_interval_s,
        requester=requester,
        sleeper=sleeper,
        clock=clock,
    )


def _collect_best_effort_evidence(
    base_url: str,
    requester: _AuditedRequester,
) -> dict[str, Any]:
    captures: dict[str, Any] = {}
    for name, endpoint in (
        ("job", "/api/job"),
        ("diagnostic_report", "/api/diagnostic/report"),
        ("gpio_status", "/api/diagnostic/status"),
    ):
        try:
            value = _get_json_object(
                base_url,
                endpoint,
                label=f"best-effort {name}",
                requester=requester,
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


def _base_result(
    *,
    attempt_id: str,
    contract: _RunContract,
    claim: _Claim,
    recorded_at_utc: str,
    classification_override: Optional[Mapping[str, Any]] = None,
    manual_observation_override: Optional[Sequence[str]] = None,
    fixed_result_metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "action_identity": dict(contract.action_identity),
        "action_identity_sha256": contract.action_identity_sha256,
        "authorization_claim": claim.reference(),
        "authorization_consumed_permanently": True,
        "exact_action": dict(EXACT_ACTION),
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "classification": dict(CLASSIFICATION),
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "algorithm_qualification": False,
        "busy_policy": {
            "post_rst_busy_is_informational": True,
            "nested_command_edges_are_authoritative": True,
            "panel_outputs_low_required": True,
        },
        "manual_observation_required": [
            "screen_matches_reviewed_strict_preview",
            "full_panel_halves_orientation_and_seam",
            "power_supply_3_3v_and_cv",
            "current_and_temperature",
            "odor_sound_hotspot_damage_or_droop",
            "post_run_power_state",
        ],
        "manual_observation_completed": False,
    }
    fixed_binding = contract.action_identity.get("fixed_external_evidence_binding")
    if isinstance(fixed_binding, Mapping):
        result["exact_action"] = {
            **dict(EXACT_ACTION),
            "action_id": fixed_binding.get("fixed_action_id"),
        }
    if classification_override is not None:
        if not isinstance(classification_override, Mapping):
            raise Rc2gQualityRefreshError("result classification override must be an object")
        result["classification"] = json.loads(
            _canonical_json(dict(classification_override)).decode("utf-8")
        )
    if manual_observation_override is not None:
        if (
            isinstance(manual_observation_override, (str, bytes))
            or not isinstance(manual_observation_override, Sequence)
            or any(
                not isinstance(item, str) or not item
                for item in manual_observation_override
            )
        ):
            raise Rc2gQualityRefreshError(
                "manual observation override must contain non-empty strings"
            )
        result["manual_observation_required"] = list(manual_observation_override)
    if fixed_result_metadata is not None:
        if not isinstance(fixed_result_metadata, Mapping):
            raise Rc2gQualityRefreshError("fixed result metadata must be an object")
        metadata = json.loads(
            _canonical_json(dict(fixed_result_metadata)).decode("utf-8")
        )
        overlap = set(metadata).intersection(result)
        if overlap:
            raise Rc2gQualityRefreshError(
                "fixed result metadata overlaps core fields: "
                + ", ".join(sorted(overlap))
            )
        result.update(metadata)
    return result


def run_rc2g_quality_refresh_once(
    result_dir: Path,
    base_url: str,
    candidate_dir: Path,
    *,
    expected_manifest_sha256: str,
    expected_prior_job_id: int,
    expected_prior_operation_id: int,
    expected_prior_frame_sha256: str,
    expected_prior_frame_fnv1a: int,
    expected_prior_cs1_dtm_fnv1a: int,
    expected_prior_cs2_dtm_fnv1a: int,
    expected_target_job_id: int,
    expected_target_operation_id: int,
    authorization_confirmation: str,
    confirm_j2_powered_supervised: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_reviewed_strict_preview: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    _prevalidated_snapshot: Optional[_CandidateSnapshot] = None,
    _fixed_external_evidence_binding: Optional[Mapping[str, Any]] = None,
    _fixed_expected_prior_evidence: Optional[Mapping[str, Any]] = None,
    _additional_fixed_confirmations: Optional[Mapping[str, Any]] = None,
    _fixed_claim_filename: Optional[str] = None,
    _result_classification_override: Optional[Mapping[str, Any]] = None,
    _manual_observation_override: Optional[Sequence[str]] = None,
    _fixed_result_metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Claim and execute one exact sequential RC2G quality refresh."""

    if not isinstance(result_dir, Path):
        raise Rc2gQualityRefreshError("result_dir must be pathlib.Path")
    if not isinstance(candidate_dir, Path):
        raise Rc2gQualityRefreshError("candidate_dir must be pathlib.Path")
    destination = _prepare_result_destination(result_dir)
    confirmations = {
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "reviewed_strict_preview": confirm_reviewed_strict_preview,
    }
    if any(
        type(value) is not bool or value is not True
        for value in confirmations.values()
    ):
        raise Rc2gQualityRefreshError(
            "explicit supervised-power, normal-supply/temperature, and reviewed-preview confirmations are required"
        )
    if _additional_fixed_confirmations is not None:
        if not isinstance(_additional_fixed_confirmations, Mapping):
            raise Rc2gQualityRefreshError(
                "additional fixed confirmations must be an object"
            )
        for key, value in _additional_fixed_confirmations.items():
            if not isinstance(key, str) or not key or key in confirmations:
                raise Rc2gQualityRefreshError(
                    "additional fixed confirmation keys must be new non-empty strings"
                )
            if type(value) is not bool or value is not True:
                raise Rc2gQualityRefreshError(
                    "every additional fixed confirmation must be exactly true"
                )
            confirmations[key] = value
    if not isinstance(base_url, str) or not base_url.strip():
        raise Rc2gQualityRefreshError("base_url must be a non-empty device root URL")

    internal_overrides = (
        _fixed_external_evidence_binding,
        _fixed_expected_prior_evidence,
        _additional_fixed_confirmations,
        _fixed_claim_filename,
        _result_classification_override,
        _manual_observation_override,
        _fixed_result_metadata,
    )
    if _prevalidated_snapshot is None:
        if any(value is not None for value in internal_overrides):
            raise Rc2gQualityRefreshError(
                "internal RC2G overrides require the sole fixed N1 snapshot"
            )
        snapshot = _load_candidate_snapshot(candidate_dir, expected_manifest_sha256)
    elif not isinstance(_prevalidated_snapshot, _CandidateSnapshot):
        raise Rc2gQualityRefreshError(
            "internal prevalidated candidate snapshot has the wrong type"
        )
    else:
        snapshot = _prevalidated_snapshot
        if snapshot.directory.resolve(strict=True) != candidate_dir.resolve(strict=True):
            raise Rc2gQualityRefreshError(
                "internal prevalidated candidate directory does not match candidate_dir"
            )
        expected_manifest = _require_sha256(
            expected_manifest_sha256,
            label="expected candidate manifest SHA-256",
        )
        if snapshot.manifest_file_sha256 != expected_manifest:
            raise Rc2gQualityRefreshError(
                "internal prevalidated candidate manifest SHA-256 does not match"
            )
        _validate_internal_n1_override(
            snapshot,
            _fixed_external_evidence_binding,
            _fixed_expected_prior_evidence,
            _additional_fixed_confirmations,
            _fixed_claim_filename,
            _result_classification_override,
            _manual_observation_override,
            _fixed_result_metadata,
            expected_prior_job_id=expected_prior_job_id,
            expected_prior_operation_id=expected_prior_operation_id,
            expected_prior_frame_sha256=expected_prior_frame_sha256,
            expected_prior_frame_fnv1a=expected_prior_frame_fnv1a,
            expected_prior_cs1_dtm_fnv1a=expected_prior_cs1_dtm_fnv1a,
            expected_prior_cs2_dtm_fnv1a=expected_prior_cs2_dtm_fnv1a,
            expected_target_job_id=expected_target_job_id,
            expected_target_operation_id=expected_target_operation_id,
        )
    contract = _build_run_contract(
        snapshot,
        expected_prior_job_id=expected_prior_job_id,
        expected_prior_operation_id=expected_prior_operation_id,
        expected_prior_frame_sha256=expected_prior_frame_sha256,
        expected_prior_frame_fnv1a=expected_prior_frame_fnv1a,
        expected_prior_cs1_dtm_fnv1a=expected_prior_cs1_dtm_fnv1a,
        expected_prior_cs2_dtm_fnv1a=expected_prior_cs2_dtm_fnv1a,
        expected_target_job_id=expected_target_job_id,
        expected_target_operation_id=expected_target_operation_id,
        fixed_external_evidence_binding=_fixed_external_evidence_binding,
    )
    if authorization_confirmation != contract.required_authorization_confirmation:
        raise Rc2gQualityRefreshError(
            "exact per-action RC2G quality authorization string is required; use --describe-only first"
        )

    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    claim = _claim_action(
        contract,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        authorization_confirmation=authorization_confirmation,
        confirmations=confirmations,
        fixed_claim_filename=_fixed_claim_filename,
    )

    directory: Optional[Path] = None
    requester = _AuditedRequester(http_request)
    device_io_started = False
    prior: Optional[Mapping[str, Any]] = None
    network_report: Optional[Mapping[str, Any]] = None
    target_job_raw: Optional[Mapping[str, Any]] = None
    target_diagnostic_raw: Optional[Mapping[str, Any]] = None
    target_protocol_verified = False
    post_gpio_raw: Optional[Mapping[str, Any]] = None
    try:
        directory = _create_result_directory(destination, snapshot, claim)
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": LOCK_KIND,
            "attempt_id": attempt_id,
            "created_at_utc": created_at_utc,
            "state": "authorization_permanently_consumed_do_not_rerun",
            "action_identity": dict(contract.action_identity),
            "action_identity_sha256": contract.action_identity_sha256,
            "authorization_claim": claim.reference(),
            "confirmations": confirmations,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
        }
        fixed_binding = contract.action_identity.get(
            "fixed_external_evidence_binding"
        )
        if isinstance(fixed_binding, Mapping):
            lock["fixed_action_id"] = fixed_binding.get("fixed_action_id")
            lock["pilot_id"] = fixed_binding.get("pilot_id")
            lock["exact_action"] = {
                **dict(EXACT_ACTION),
                "action_id": fixed_binding.get("fixed_action_id"),
            }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        device_io_started = True
        prior = _validate_prior(
            base_url,
            requester,
            contract,
            expected_exact_prior_evidence=_fixed_expected_prior_evidence,
        )
        network_report = _perform_refresh_once(
            base_url,
            snapshot.frame,
            requester,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        _validate_network_report(network_report, contract)
        target_job_raw = _get_json_object(
            base_url,
            "/api/job",
            label="target immutable job reread",
            requester=requester,
        )
        if target_job_raw != network_report.get("job"):
            raise Rc2gQualityRefreshError(
                "target immutable job changed between verified reads"
            )
        target_diagnostic_raw = _get_json_object(
            base_url,
            "/api/diagnostic/report",
            label="target immutable diagnostic reread",
            requester=requester,
        )
        _validate_target_raw_diagnostic(
            target_diagnostic_raw, network_report, contract
        )
        target_protocol_verified = True
        if (
            requester.post_attempt_count != 1
            or requester.post_issued_count != 1
        ):
            raise Rc2gQualityRefreshError(
                "target did not issue exactly one POST /api/frame"
            )
        post_gpio_raw = _get_json_object(
            base_url,
            "/api/diagnostic/status",
            label="post-refresh GPIO",
            requester=requester,
        )
        post_gpio = _validate_gpio_snapshot(
            post_gpio_raw, label="post-refresh GPIO"
        )
        result = {
            **_base_result(
                attempt_id=attempt_id,
                contract=contract,
                claim=claim,
                recorded_at_utc=_utc_now(),
                classification_override=_result_classification_override,
                manual_observation_override=_manual_observation_override,
                fixed_result_metadata=_fixed_result_metadata,
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "prior_preflight": dict(prior),
            "network_report": dict(network_report),
            "target_job_raw": dict(target_job_raw),
            "target_diagnostic_raw": dict(target_diagnostic_raw),
            "post_refresh_gpio_status_raw": dict(post_gpio_raw),
            "post_refresh_gpio": _gpio_evidence(post_gpio),
            "request_audit": requester.snapshot(),
            "best_effort_postclaim_evidence": None,
        }
        _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(result))
        return result
    except BaseException as error:
        try:
            best_effort = (
                _collect_best_effort_evidence(base_url, requester)
                if device_io_started
                else {
                    "attempted": False,
                    "purpose": "incident_evidence_only_not_retry_or_recovery",
                    "requests_are_read_only": True,
                    "state_changing_request_performed": False,
                    "reason": "no device I/O had started",
                    "captures": {},
                }
            )
        except BaseException as capture_error:
            best_effort = {
                "attempted": False,
                "purpose": "incident_evidence_only_not_retry_or_recovery",
                "requests_are_read_only": True,
                "state_changing_request_performed": False,
                "captures": {},
                "capture_helper_error": {
                    "type": type(capture_error).__name__,
                    "message": str(capture_error),
                },
            }
        record_error: Optional[BaseException] = None
        try:
            if directory is not None:
                unknown = {
                    **_base_result(
                        attempt_id=attempt_id,
                        contract=contract,
                        claim=claim,
                        recorded_at_utc=_utc_now(),
                        classification_override=_result_classification_override,
                        manual_observation_override=_manual_observation_override,
                        fixed_result_metadata=_fixed_result_metadata,
                    ),
                    "outcome": "unknown_do_not_retry",
                    "protocol_verified": (
                        True if target_protocol_verified else None
                    ),
                    "prior_preflight": dict(prior) if prior is not None else None,
                    "network_report": (
                        dict(network_report) if network_report is not None else None
                    ),
                    "target_job_raw": (
                        dict(target_job_raw) if target_job_raw is not None else None
                    ),
                    "target_diagnostic_raw": (
                        dict(target_diagnostic_raw)
                        if target_diagnostic_raw is not None
                        else None
                    ),
                    "post_refresh_gpio_status_raw": (
                        dict(post_gpio_raw) if post_gpio_raw is not None else None
                    ),
                    "request_audit": requester.snapshot(),
                    "best_effort_postclaim_evidence": dict(best_effort),
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
                _atomic_new_file(
                    directory, RESULT_FILENAME, _canonical_json(unknown)
                )
        except BaseException as result_error:
            record_error = result_error
        detail = (
            f"; result recording also failed ({record_error})"
            if record_error is not None
            else ""
        )
        raise Rc2gQualityRefreshUnknown(
            "RC2G quality outcome is unknown_do_not_retry; the action claim is permanent"
            + detail
        ) from error


def _sha256_argument(value: str) -> str:
    try:
        return _require_sha256(value, label="manifest SHA-256")
    except Rc2gQualityRefreshError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _u32_argument(value: str) -> int:
    try:
        parsed = int(value, 0)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(
            "expected an unsigned 32-bit integer (decimal or 0x-prefixed hex)"
        ) from error
    try:
        return _require_u32(parsed, label="value")
    except Rc2gQualityRefreshError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _nonzero_u32_argument(value: str) -> int:
    parsed = _u32_argument(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("expected a non-zero unsigned 32-bit integer")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--manifest-sha256", type=_sha256_argument, required=True)
    parser.add_argument(
        "--expected-prior-job-id", type=_nonzero_u32_argument, required=True
    )
    parser.add_argument(
        "--expected-prior-operation-id",
        type=_nonzero_u32_argument,
        required=True,
    )
    parser.add_argument(
        "--expected-prior-frame-sha256", type=_sha256_argument, required=True
    )
    parser.add_argument(
        "--expected-prior-frame-fnv1a", type=_u32_argument, required=True
    )
    parser.add_argument(
        "--expected-prior-cs1-dtm-fnv1a", type=_u32_argument, required=True
    )
    parser.add_argument(
        "--expected-prior-cs2-dtm-fnv1a", type=_u32_argument, required=True
    )
    parser.add_argument(
        "--expected-target-job-id", type=_nonzero_u32_argument, required=True
    )
    parser.add_argument(
        "--expected-target-operation-id",
        type=_nonzero_u32_argument,
        required=True,
    )
    parser.add_argument(
        "--describe-only",
        action="store_true",
        help="deep-validate locally and print the exact action authorization; no claim or device I/O",
    )
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--url", help="device root URL on the trusted test network")
    parser.add_argument("--confirm", help="exact per-action authorization string")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument(
        "--confirm-supply-and-temperature-normal", action="store_true"
    )
    parser.add_argument("--confirm-reviewed-strict-preview", action="store_true")
    args = parser.parse_args(argv)
    if not args.describe_only:
        missing = [
            option
            for option, value in (
                ("--result-dir", args.result_dir),
                ("--url", args.url),
                ("--confirm", args.confirm),
            )
            if value is None
        ]
        if missing:
            parser.error(
                "normal run requires " + ", ".join(missing)
            )
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    contract_arguments = {
        "expected_manifest_sha256": args.manifest_sha256,
        "expected_prior_job_id": args.expected_prior_job_id,
        "expected_prior_operation_id": args.expected_prior_operation_id,
        "expected_prior_frame_sha256": args.expected_prior_frame_sha256,
        "expected_prior_frame_fnv1a": args.expected_prior_frame_fnv1a,
        "expected_prior_cs1_dtm_fnv1a": args.expected_prior_cs1_dtm_fnv1a,
        "expected_prior_cs2_dtm_fnv1a": args.expected_prior_cs2_dtm_fnv1a,
        "expected_target_job_id": args.expected_target_job_id,
        "expected_target_operation_id": args.expected_target_operation_id,
    }
    try:
        if args.describe_only:
            result = describe_rc2g_quality_action(
                args.candidate_dir,
                **contract_arguments,
            )
        else:
            assert args.result_dir is not None
            assert args.url is not None
            assert args.confirm is not None
            result = run_rc2g_quality_refresh_once(
                args.result_dir,
                args.url,
                args.candidate_dir,
                authorization_confirmation=args.confirm,
                confirm_j2_powered_supervised=(
                    args.confirm_j2_powered_supervised
                ),
                confirm_supply_and_temperature_normal=(
                    args.confirm_supply_and_temperature_normal
                ),
                confirm_reviewed_strict_preview=(
                    args.confirm_reviewed_strict_preview
                ),
                **contract_arguments,
            )
    except Rc2gQualityRefreshUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except Rc2gQualityRefreshError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
