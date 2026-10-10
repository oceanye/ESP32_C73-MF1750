#!/usr/bin/env python3
"""Compile the frozen, offline-only G1/S1 N2 quality campaign manifest.

The compiler deeply validates four existing experimental candidate bundles and
describes four *independent* future sessions.  Every cell starts from its own
fresh-boot MAP primer and permits one subsequent target action.  The resulting
manifest is evidence and planning data only: it creates no authorization
claim, emits no authorization string, exposes no device URL, and performs no
network, serial, GPIO, firmware, upload, or refresh operation.

Q1--Q4 order is an administrative review order, not a playback chain.  A
future hardware implementation must supply dedicated fixed-action runners for
the declared primer and target claims; the generic quality runner is not
invoked by this module.
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
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    controller_stream,
    fnv1a,
    generate_fixture,
    unpack_pixels,
    validate_frame,
)
from tools.g1_s1_rc2g_quality_refresh_once import (  # noqa: E402
    EXPECTED_BUILD_TAG,
    EXPECTED_DRIVER_API,
    EXPECTED_REFRESH_SPI_HZ,
    FIXED_CONTROLLER_MAPPINGS,
    MAX_JOB_DRIVER_DURATION_DELTA_MS,
    MAX_QUEUE_DELAY_MS,
    NOMINAL_JOB_DURATION_MS,
    NOMINAL_STAGE_TIMING_MS,
    Rc2gQualityRefreshError,
    _CandidateSnapshot,
    _load_candidate_snapshot as _load_quality_candidate_snapshot,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-rc2g-n2-quality-campaign-offline-manifest"
CAMPAIGN_ID = "g1-s1-rc2g-n2-quality-ab-four-independent-cells-v1"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
EXPECTED_CANDIDATE_KIND = "mf1750-g1-s1-experimental-panel-candidate"

HARDWARE_DIR = REPO_ROOT / ".test-output" / "hardware"
MAP_FIXTURE = "map-orient-v1"
MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_FRAME_FNV1A = 0x9D04142D
MAP_CS1_DTM_SHA256 = "d1ce843dca5ec7a615329f6a118dc9bd03498f686f1b5bfe55d51a97556eccaa"
MAP_CS1_DTM_FNV1A = 0xF26832DD
MAP_CS2_DTM_SHA256 = "ae0bc93cc2cf736fc2f9c209865c93443e90271b992647a8d8c7a5761e08c791"
MAP_CS2_DTM_FNV1A = 0xFE199FF5
SHARED_SOURCE_SHA256 = "b8400d6c901fcfefac49eafb2b2db4dadfdc5615392640dfe4cef7efe068f101"
SHARED_MAPPED_SHA256 = "22488999efd344e2f3462de09ca1db6eb36e95ab4a728f3481990acc3503d1ef"
SHARED_PROFILE_SHA256 = "34d8b88386b19ad3717b2e7d54b1c3e072b424f186413c994eb175d1989ca2ee"
Q3_Q4_DIFFERING_PIXELS = 50

# Both identities are checked by compile_campaign_manifest; changing any
# frozen action or input is therefore a code-review-visible contract change
# rather than silent drift.
EXPECTED_MANIFEST_CANONICAL_SHA256 = (
    "69ae1e892f7fb603515a005127ae89d9d3568249c6c7512fa8d3bc69d2be881c"
)
EXPECTED_MANIFEST_FILE_SHA256 = (
    "f77d599bca741454644f64f9755921857b4299983a9cf112f752bb5c94b51037"
)


class N2CampaignError(RuntimeError):
    """The fixed offline campaign could not be proven byte-for-byte."""


@dataclass(frozen=True)
class _CellSpec:
    cell_id: str
    ordinal: int
    algorithm: str
    artifact_id: str
    manifest_file_sha256: str
    manifest_canonical_sha256: str
    frame_sha256: str
    frame_fnv1a: int
    codes_sha256: str
    final_preview_sha256: str
    simulation_report_sha256: str
    cs1_dtm_sha256: str
    cs1_dtm_fnv1a: int
    cs2_dtm_sha256: str
    cs2_dtm_fnv1a: int

    @property
    def directory(self) -> Path:
        return HARDWARE_DIR / self.artifact_id

    @property
    def slug(self) -> str:
        return self.cell_id.lower()


CELL_SPECS = (
    _CellSpec(
        "Q1",
        1,
        "atkinson",
        "G1S1_QUALITY_ATKINSON_OFFLINE_20260806",
        "ae882e6c7cd032a8315e15a1deb2a77abee025711acb55b5ec22b0fe91a4f32b",
        "2a0cc6c35a0e0e6a862b4d23497db442a2443565e997e04654eb9fbc76dbbbdc",
        "63c779880b070e9097cac3cb8d8740aa5c8c98fabd741edd2e87a5a9bea4cdac",
        0xFAC8E693,
        "8fad20b20822df5057b55ef3e6a368f374f4a7e5d1b4dd7339b68d9795d214d5",
        "1e2b9ad7639d09edda4d1d0379bcee374dd15ee72131f3c6f56394f4d15aebaf",
        "d7e9d7e07c3519bb3ca1de9ee130899dc15ff8362dc1ffb643da673ef526a767",
        "d103f5593efd05cab3ce395e77289f806803808741b554884600e53f65aa9d7f",
        0xA93BEFB0,
        "89e165b283507c101a2636e6d2f47af6dd2f4b307f60cbba1c3e827ffd231440",
        0x35DA34BA,
    ),
    _CellSpec(
        "Q2",
        2,
        "area-weighted-blue-noise",
        "G1S1_QUALITY_BLUE_NOISE_OFFLINE_20260806",
        "69244cebe2e37c0d26404b85b9d89471cd95d492a9599481e5f34968c3159a48",
        "9f43658ffccb3e19dadfcda8a98ba78e5bbf1c06f02d24e57f476bfecda45b94",
        "eed46ab43bebe1b1056736d43d0189ea26650ff81fe5af1dd52a5882e447faf9",
        0xB932966C,
        "7dfa89c197472be138093510003da10dfc1d82b61e65392383305bf122e7aed0",
        "57bdc31ba5ee7380dabf7aa9b3a4d174e95de942f1b6c8479402098f6ba852b0",
        "64505bd8f5190634a709b97450ea9ef717a231c832f9902720d54b1821ad43f4",
        "e87eb5b8c055f40327df8b99076e48014349413b3daeb501a904aa44e8a501bc",
        0x1A6195F8,
        "37edfb015c1d825f45065dc6ac9925e7d539939e56a60a95f48ecd8a8a30499a",
        0xCB3B0FB9,
    ),
    _CellSpec(
        "Q3",
        3,
        "multicolor-dbs",
        "G1S1_QUALITY_MULTICOLOR_DBS_OFFLINE_20260806",
        "9eb946ddb91093d654071d55f9fa0f3f890497f368c3cbd7222ea19213f1db3e",
        "765e2e2baacfcda065a34ead2a37af4fa79387934751438c3e7ca48943a68bfc",
        "302122783e20b12b2c9b64c7a096a4ae3ef9c5bcceb62a778dde27d00fa2e494",
        0xCA448751,
        "6e7bd9cc0bd21c5f4a4473dfb21fc29c0d111e857db443a3b85ce50ac4fa30b9",
        "1ab51ec7532a9f7f2725aba5017002b734f3d519af811fe6f6194c51c4370ee3",
        "7143682551e873243000773d8b5b528c4105b2429e9a7d999fc110d9cc3819d4",
        "a0c95c1e25af17df54a4a9916ac3c1593a52b8616a347e9c063d26ecc2a9fc13",
        0xF69BE779,
        "000fcea61bfad973a0ed92f7fd42e6ccc0adef541d9c1687adeba30b78c89a68",
        0xC41898ED,
    ),
    _CellSpec(
        "Q4",
        4,
        "overlap-aware-dbs",
        "G1S1_QUALITY_OVERLAP_DBS_OFFLINE_20260806",
        "c7fc66c6cb879997c5a5b34d8b8234c2abbca691a80c29f44c7e212548ebd062",
        "3a5dfb36ae2830b986790e3129981f0a8aaf52a5d9b1af3be75b63dbef92ce2b",
        "ca2510adda0170c34fbf24a6309a8f6bdea9d477a911bd62b1fa172f4b7770c8",
        0x5CD8EEDF,
        "e6f05f8860d252ae287b3ebf2f4ce4b65284e96b20186c06053735c004a5c60c",
        "58e4725985ab8ae087383c04ca76fc5c4deab1dad83e5a09f323d347391876d6",
        "b993815f144cfc478c76c6a7a7eb81da90373881f0ce72122106af816072e403",
        "3eac69d74c2bc022663cdd9e95a519f3d1e03be252d217c937442bbd14e10950",
        0x66CEB8C7,
        "3d0024e10bc578c95526ffc3cee6f4a47247257332c173e4021e93f70f886962",
        0x61B42FA5,
    ),
)


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
        raise N2CampaignError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json_object(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_constant(token: str) -> None:
        raise N2CampaignError(f"{label} contains forbidden JSON constant {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise N2CampaignError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except N2CampaignError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N2CampaignError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N2CampaignError(f"{label} root must be an object")
    return value


def _mapping_record(mapping: object) -> dict[str, Any]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _validate_map_identity() -> Mapping[str, Any]:
    frame = generate_fixture(MAP_FIXTURE)
    validate_frame(frame)
    streams = tuple(controller_stream(frame, mapping) for mapping in FIXED_CONTROLLER_MAPPINGS)
    expected = (
        (MAP_CS1_DTM_SHA256, MAP_CS1_DTM_FNV1A),
        (MAP_CS2_DTM_SHA256, MAP_CS2_DTM_FNV1A),
    )
    if len(frame) != FRAME_BYTES or _sha256(frame) != MAP_FRAME_SHA256 or fnv1a(frame) != MAP_FRAME_FNV1A:
        raise N2CampaignError("frozen MAP fixture identity changed")
    controllers = []
    for index, (stream, mapping, identities) in enumerate(
        zip(streams, FIXED_CONTROLLER_MAPPINGS, expected), start=1
    ):
        if (
            len(stream) != CONTROLLER_FRAME_BYTES
            or _sha256(stream) != identities[0]
            or fnv1a(stream) != identities[1]
        ):
            raise N2CampaignError(f"frozen MAP CS{index} DTM identity changed")
        controllers.append(
            {
                "controller": f"CS{index}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": identities[0],
                "dtm_fnv1a": f"0x{identities[1]:08X}",
            }
        )
    return {
        "fixture": MAP_FIXTURE,
        "frame_bytes": len(frame),
        "frame_sha256": MAP_FRAME_SHA256,
        "frame_fnv1a": f"0x{MAP_FRAME_FNV1A:08X}",
        "controllers": controllers,
    }


def _load_fixed_cell(spec: _CellSpec) -> tuple[_CandidateSnapshot, Mapping[str, Any]]:
    try:
        snapshot = _load_quality_candidate_snapshot(
            spec.directory, spec.manifest_file_sha256
        )
    except Rc2gQualityRefreshError as error:
        raise N2CampaignError(f"{spec.cell_id} candidate validation failed: {error}") from error
    manifest = snapshot.manifest
    frame_record = manifest.get("frame")
    previews = manifest.get("previews")
    simulation = manifest.get("simulation")
    profile = manifest.get("profile")
    controllers = [dict(record) for record in snapshot.controllers]
    expected_controllers = [
        {
            "controller": "CS1",
            "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[0]),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_sha256": spec.cs1_dtm_sha256,
            "dtm_fnv1a": f"0x{spec.cs1_dtm_fnv1a:08X}",
        },
        {
            "controller": "CS2",
            "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[1]),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_sha256": spec.cs2_dtm_sha256,
            "dtm_fnv1a": f"0x{spec.cs2_dtm_fnv1a:08X}",
        },
    ]
    final_preview = previews.get("final") if isinstance(previews, Mapping) else None
    source_preview = previews.get("source") if isinstance(previews, Mapping) else None
    mapped_preview = previews.get("mapped") if isinstance(previews, Mapping) else None
    checks = (
        manifest.get("kind") == EXPECTED_CANDIDATE_KIND,
        snapshot.algorithm == spec.algorithm,
        snapshot.manifest_file_sha256 == spec.manifest_file_sha256,
        snapshot.manifest_canonical_sha256 == spec.manifest_canonical_sha256,
        snapshot.frame_sha256 == spec.frame_sha256,
        snapshot.frame_fnv1a == spec.frame_fnv1a,
        isinstance(frame_record, Mapping)
        and frame_record.get("codes_sha256") == spec.codes_sha256,
        controllers == expected_controllers,
        isinstance(final_preview, Mapping)
        and final_preview.get("file") == "final.png"
        and final_preview.get("sha256") == spec.final_preview_sha256,
        isinstance(source_preview, Mapping)
        and source_preview.get("sha256") == SHARED_SOURCE_SHA256,
        isinstance(mapped_preview, Mapping)
        and mapped_preview.get("sha256") == SHARED_MAPPED_SHA256,
        isinstance(simulation, Mapping)
        and simulation.get("report_canonical_sha256") == spec.simulation_report_sha256,
        isinstance(profile, Mapping)
        and profile.get("canonical_sha256") == SHARED_PROFILE_SHA256,
    )
    if not all(checks):
        raise N2CampaignError(f"{spec.cell_id} frozen candidate identity changed")
    record = {
        "artifact_id": spec.artifact_id,
        "workspace_relative_directory": f".test-output/hardware/{spec.artifact_id}",
        "manifest_kind": EXPECTED_CANDIDATE_KIND,
        "manifest_file_sha256": spec.manifest_file_sha256,
        "manifest_canonical_sha256": spec.manifest_canonical_sha256,
        "algorithm": spec.algorithm,
        "frame_bytes": FRAME_BYTES,
        "frame_sha256": spec.frame_sha256,
        "frame_fnv1a": f"0x{spec.frame_fnv1a:08X}",
        "codes_sha256": spec.codes_sha256,
        "controllers": expected_controllers,
        "strict_final_preview": {
            "file": "final.png",
            "sha256": spec.final_preview_sha256,
        },
        "simulation_report_canonical_sha256": spec.simulation_report_sha256,
        "source_sha256": SHARED_SOURCE_SHA256,
        "mapped_sha256": SHARED_MAPPED_SHA256,
        "profile_canonical_sha256": SHARED_PROFILE_SHA256,
        "input_kind": "synthetic_test_card",
        "natural_photo_input": False,
        "hardware_ready": False,
        "source_bundle_upload_authorized": False,
    }
    return snapshot, record


def _claim_declaration(spec: _CellSpec, phase: str, action_id: str) -> Mapping[str, Any]:
    suffix = "map_primer" if phase == "primer" else "target"
    return {
        "registry_id": f"workspace-g1-s1-rc2g-n2-{spec.slug}-{suffix}-registry-v1",
        "workspace_relative_registry": f".test-output/hardware/.g1_s1_rc2g_n2_{spec.slug}_{suffix}_registry",
        "fixed_filename": action_id,
        "workspace_global_fixed_action": True,
        "partitioned_by_result_directory": False,
        "partitioned_by_campaign_id": False,
        "partitioned_by_primer_result_sha256": False,
        "claim_created_by_compiler": False,
    }


def _exact_action(action_id: str) -> Mapping[str, Any]:
    return {
        "action_id": action_id,
        "method": "POST",
        "endpoint": "/api/frame",
        "maximum_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "remote_cancel": False,
    }


def _firmware_contract() -> Mapping[str, Any]:
    return {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "panel": f"{WIDTH}x{HEIGHT}",
        "frame_bytes": FRAME_BYTES,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "controller_mappings": [
            _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
        ],
    }


def _timing_contract() -> Mapping[str, Any]:
    return {
        "job_duration_ms": list(NOMINAL_JOB_DURATION_MS),
        "maximum_queue_delay_ms": MAX_QUEUE_DELAY_MS,
        "maximum_job_driver_duration_delta_ms": MAX_JOB_DRIVER_DURATION_DELTA_MS,
        "stages_ms": {
            name: list(bounds) for name, bounds in NOMINAL_STAGE_TIMING_MS.items()
        },
    }


def _compile_cell(
    spec: _CellSpec,
    candidate: Mapping[str, Any],
    map_identity: Mapping[str, Any],
) -> Mapping[str, Any]:
    primer_action_id = (
        f"rc2g-n2-{spec.slug}-{spec.algorithm}-cold-boot-map-primer-job1-op1-once-v1"
    )
    target_action_id = (
        f"rc2g-n2-{spec.slug}-{spec.algorithm}-after-own-map-primer-job2-op2-once-v1"
    )
    primer_identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-rc2g-n2-cell-map-primer-action-identity",
        "campaign_id": CAMPAIGN_ID,
        "cell_id": spec.cell_id,
        "algorithm": spec.algorithm,
        "action_id": primer_action_id,
        "claim": _claim_declaration(spec, "primer", primer_action_id),
        "required_initial_state": {
            "fresh_boot_required": True,
            "job_id": 0,
            "job_action": "none",
            "job_state": "idle",
            "completed_diagnostic": False,
            "panel_outputs_low_required": True,
        },
        "target": {
            "job_id": 1,
            "operation_id": 1,
            "frame": dict(map_identity),
            "required_state": "completed",
        },
        "firmware": _firmware_contract(),
        "timing": _timing_contract(),
        "gpio_policy": {
            "required_panel_outputs": {"rst": 0, "cs": 0, "cs2": 0},
            "busy_after_rst_low": "informational",
            "nested_command_edges": "authoritative",
        },
        "exact_action": _exact_action(primer_action_id),
        "authorization_issued": False,
        "hardware_execution_authorized": False,
        "blocked_by_campaign_gap_audit": True,
        "upload_authorized": False,
    }
    primer_sha = _sha256(_canonical_json(primer_identity))
    target_identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-rc2g-n2-cell-target-action-identity",
        "campaign_id": CAMPAIGN_ID,
        "cell_id": spec.cell_id,
        "algorithm": spec.algorithm,
        "action_id": target_action_id,
        "claim": _claim_declaration(spec, "target", target_action_id),
        "required_prior": {
            "same_cell_only": True,
            "primer_action_id": primer_action_id,
            "primer_action_identity_sha256": primer_sha,
            "job_id": 1,
            "operation_id": 1,
            "frame_sha256": MAP_FRAME_SHA256,
            "frame_fnv1a": f"0x{MAP_FRAME_FNV1A:08X}",
            "cs1_dtm_fnv1a": f"0x{MAP_CS1_DTM_FNV1A:08X}",
            "cs2_dtm_fnv1a": f"0x{MAP_CS2_DTM_FNV1A:08X}",
            "manual_map_fidelity_pass_required": True,
            "no_reboot_or_power_disconnect_since_primer_required": True,
        },
        "target": {
            "job_id": 2,
            "operation_id": 2,
            "candidate": dict(candidate),
            "required_state": "completed",
        },
        "firmware": _firmware_contract(),
        "timing": _timing_contract(),
        "gpio_policy": {
            "required_panel_outputs": {"rst": 0, "cs": 0, "cs2": 0},
            "busy_after_rst_low": "informational",
            "nested_command_edges": "authoritative",
        },
        "exact_action": _exact_action(target_action_id),
        "authorization_issued": False,
        "hardware_execution_authorized": False,
        "blocked_by_campaign_gap_audit": True,
        "upload_authorized": False,
    }
    target_sha = _sha256(_canonical_json(target_identity))
    return {
        "cell_id": spec.cell_id,
        "review_order": spec.ordinal,
        "algorithm": spec.algorithm,
        "candidate": dict(candidate),
        "session_isolation": {
            "independent_fresh_boot_session_required": True,
            "maximum_visible_refreshes": 2,
            "sequence": ["fresh_job0", "own_map_primer_job1_op1", "own_target_job2_op2"],
            "previous_cell_as_prior_authorized": False,
            "next_cell_without_new_fresh_boot_authorized": False,
            "serial_playback_authorized": False,
        },
        "map_primer": {
            "action_identity": primer_identity,
            "action_identity_sha256": primer_sha,
        },
        "target": {
            "action_identity": target_identity,
            "action_identity_sha256": target_sha,
        },
        "execution_runner_present": False,
        "authorization_string_issued": False,
        "natural_photo_input": False,
        "hardware_ready": False,
        "upload_authorized": False,
    }


def _validate_cross_cell_contract(cells: Sequence[Mapping[str, Any]]) -> None:
    if [cell.get("cell_id") for cell in cells] != ["Q1", "Q2", "Q3", "Q4"]:
        raise N2CampaignError("N2 cell order or membership changed")
    action_ids: list[str] = []
    identity_hashes: list[str] = []
    claim_pairs: list[tuple[str, str]] = []
    for cell in cells:
        for phase in ("map_primer", "target"):
            envelope = cell.get(phase)
            identity = envelope.get("action_identity") if isinstance(envelope, Mapping) else None
            if not isinstance(identity, Mapping):
                raise N2CampaignError("N2 action identity is missing")
            claim = identity.get("claim")
            if not isinstance(claim, Mapping):
                raise N2CampaignError("N2 fixed claim declaration is missing")
            action_ids.append(str(identity.get("action_id")))
            identity_hashes.append(str(envelope.get("action_identity_sha256")))
            claim_pairs.append((str(claim.get("registry_id")), str(claim.get("fixed_filename"))))
    expected_count = len(cells) * 2
    if not (
        len(set(action_ids)) == expected_count
        and len(set(identity_hashes)) == expected_count
        and len(set(claim_pairs)) == expected_count
    ):
        raise N2CampaignError("N2 actions or workspace-global claims are not distinct")


def compile_campaign_manifest() -> Mapping[str, Any]:
    """Deep-validate all fixed inputs and return the canonical N2 manifest."""

    map_identity = _validate_map_identity()
    cells = []
    snapshots: dict[str, _CandidateSnapshot] = {}
    for spec in CELL_SPECS:
        snapshot, candidate = _load_fixed_cell(spec)
        snapshots[spec.cell_id] = snapshot
        cells.append(_compile_cell(spec, candidate, map_identity))
    _validate_cross_cell_contract(cells)
    q3_codes = unpack_pixels(snapshots["Q3"].frame)
    q4_codes = unpack_pixels(snapshots["Q4"].frame)
    q3_q4_difference = sum(left != right for left, right in zip(q3_codes, q4_codes))
    if (
        len(q3_codes) != WIDTH * HEIGHT
        or len(q4_codes) != WIDTH * HEIGHT
        or q3_q4_difference != Q3_Q4_DIFFERING_PIXELS
    ):
        raise N2CampaignError("frozen Q3/Q4 candidate-gap audit changed")
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "campaign_id": CAMPAIGN_ID,
        "phase": "N2",
        "purpose": "legacy-synthetic-test-card-four-algorithm-gap-audit-planning-only",
        "classification": {
            "experimental": True,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "algorithm_qualification": False,
            "causal_attribution_authorized": False,
            "natural_image_quality_evaluation": False,
            "synthetic_test_card_comparison_only": True,
            "hardware_ready": False,
            "upload_authorized": False,
            "offline_compiler_only": True,
        },
        "transport": {
            "mode": "offline",
            "network_io_performed": False,
            "device_io_performed": False,
            "serial_io_performed": False,
            "gpio_io_performed": False,
            "upload_performed": False,
            "upload_authorized": False,
        },
        "campaign_policy": {
            "fixed_cell_order": ["Q1", "Q2", "Q3", "Q4"],
            "cell_count": 4,
            "sessions_are_independent": True,
            "fresh_map_primer_per_cell_required": True,
            "exactly_one_target_after_each_own_primer": True,
            "serial_playback_authorized": False,
            "cross_cell_prior_reuse_authorized": False,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "stop_after_first_abnormality_required": True,
        },
        "campaign_gap_audit": {
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "natural_photo_input_present": False,
            "source_input_kind": "synthetic_test_card",
            "all_cells_share_source_sha256": SHARED_SOURCE_SHA256,
            "q3_q4_differing_pixels": q3_q4_difference,
            "q3_q4_total_pixels": WIDTH * HEIGHT,
            "q3_q4_difference_ratio": q3_q4_difference / (WIDTH * HEIGHT),
            "q3_q4_separation_adequate_for_n2": False,
            "blockers": [
                "Q1-Q4 use a legacy synthetic test card, not a frozen natural photo",
                "Q3 and Q4 differ at only 50 of 614400 output pixels",
                "no dedicated per-cell primer or target execution runner exists",
                "no hardware authorization strings or claims have been issued",
            ],
            "required_replacement_before_hardware": [
                "freeze one real natural-photo source and identical mapping/profile/options across all cells",
                "regenerate all four candidate bundles from that source",
                "resolve or explicitly justify the near-identical Q3/Q4 outputs",
                "compile a new manifest identity and pass a separate safety review",
                "implement dedicated per-cell fixed primer and target runners",
            ],
        },
        "execution_graph": {
            "components": [
                {
                    "cell_id": spec.cell_id,
                    "edges": [
                        "fresh_job0 -> own_map_primer_job1_op1",
                        "own_map_primer_job1_op1 -> own_target_job2_op2",
                    ],
                }
                for spec in CELL_SPECS
            ],
            "inter_cell_edges": [],
            "disconnected_component_count": 4,
        },
        "shared_map_identity": dict(map_identity),
        "firmware_contract": _firmware_contract(),
        "timing_contract": _timing_contract(),
        "cells": cells,
        "integration_required_before_hardware": {
            "dedicated_fixed_primer_runner_per_cell": True,
            "dedicated_fixed_target_runner_per_cell": True,
            "manual_primer_result_binding_required": True,
            "fixed_claim_consumption_required_before_device_io": True,
            "generic_runner_direct_use_authorized": False,
            "compiler_contains_execution_path": False,
            "authorization_strings_issued": False,
            "hardware_execution_authorized": False,
            "current_candidate_set_hardware_ready": False,
            "natural_photo_candidate_rebuild_required": True,
            "q3_q4_separation_review_required": True,
            "upload_authorized": False,
        },
    }
    unsigned_sha = _sha256(_canonical_json(unsigned))
    if (
        EXPECTED_MANIFEST_CANONICAL_SHA256 is not None
        and unsigned_sha != EXPECTED_MANIFEST_CANONICAL_SHA256
    ):
        raise N2CampaignError("frozen N2 manifest canonical identity changed")
    manifest = {
        **unsigned,
        "manifest_integrity": {
            "canonical_sha256": unsigned_sha,
            "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
        },
    }
    manifest_bytes = _canonical_json(manifest)
    if (
        EXPECTED_MANIFEST_FILE_SHA256 is not None
        and _sha256(manifest_bytes) != EXPECTED_MANIFEST_FILE_SHA256
    ):
        raise N2CampaignError("frozen N2 manifest file identity changed")
    return manifest


def campaign_manifest_bytes() -> bytes:
    return _canonical_json(compile_campaign_manifest())


def _safe_output_file(path: Path, *, must_exist: bool) -> Path:
    try:
        require_local_regular_path_syntax(path, label="N2 campaign manifest file")
    except LocalPathSafetyError as error:
        raise N2CampaignError(str(error)) from error
    if path.suffix.lower() != ".json":
        raise N2CampaignError("N2 campaign manifest path must end in .json")
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise N2CampaignError(f"N2 campaign manifest does not exist: {error}") from error
        if path.is_symlink() or not resolved.is_file():
            raise N2CampaignError("N2 campaign manifest must be a real regular file")
        return resolved
    if os.path.lexists(path):
        raise N2CampaignError("output manifest already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N2CampaignError(f"output parent does not exist: {error}") from error
    if not parent.is_dir() or parent.is_symlink():
        raise N2CampaignError("output parent must be a real local directory")
    destination = parent / path.name
    if os.path.lexists(destination):
        raise N2CampaignError("output manifest already exists; refusing overwrite")
    return destination


def write_campaign_manifest(output_file: Path) -> Mapping[str, Any]:
    """Create one canonical local manifest file without overwriting anything."""

    if not isinstance(output_file, Path):
        raise N2CampaignError("output_file must be pathlib.Path")
    destination = _safe_output_file(output_file, must_exist=False)
    manifest = compile_campaign_manifest()
    payload = _canonical_json(manifest)
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        linked = True
        temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        raise N2CampaignError("output manifest appeared; refusing overwrite") from error
    except OSError as error:
        if linked:
            raise N2CampaignError("manifest committed but staging cleanup failed") from error
        raise N2CampaignError(f"could not atomically write N2 manifest: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return manifest


def validate_campaign_manifest(manifest_file: Path) -> Mapping[str, Any]:
    """Compare a local canonical manifest byte-for-byte with deep recompilation."""

    if not isinstance(manifest_file, Path):
        raise N2CampaignError("manifest_file must be pathlib.Path")
    path = _safe_output_file(manifest_file, must_exist=True)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N2CampaignError(f"could not read N2 campaign manifest: {error}") from error
    parsed = _strict_json_object(payload, label="N2 campaign manifest")
    if payload != _canonical_json(parsed):
        raise N2CampaignError("N2 campaign manifest is not canonical JSON")
    expected = compile_campaign_manifest()
    if parsed != expected or payload != _canonical_json(expected):
        raise N2CampaignError("N2 campaign manifest differs from fixed deep recompilation")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true", dest="print_manifest")
    mode.add_argument("--output-file", type=Path)
    mode.add_argument("--validate-file", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_file is not None:
            manifest = write_campaign_manifest(args.output_file)
            mode = "written"
        elif args.validate_file is not None:
            manifest = validate_campaign_manifest(args.validate_file)
            mode = "validated"
        else:
            manifest = compile_campaign_manifest()
            mode = "compiled"
    except (N2CampaignError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        _canonical_json(
            {
                "ok": True,
                "mode": mode,
                "kind": manifest["kind"],
                "campaign_id": manifest["campaign_id"],
                "manifest_canonical_sha256": manifest["manifest_integrity"]["canonical_sha256"],
                "manifest_file_sha256": _sha256(_canonical_json(manifest)),
                "cell_ids": [cell["cell_id"] for cell in manifest["cells"]],
                "network_io_performed": False,
                "device_io_performed": False,
                "claim_created": False,
                "authorization_strings_issued": False,
                "upload_authorized": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
