#!/usr/bin/env python3
"""Execute one of the eight frozen N2P RC2G actions exactly once.

The offline compiler in :mod:`tools.g1_s1_rc2g_n2_photo_campaign` is the
single source of campaign, frame, session, and claim identities.  This module
adds only the execution envelope: reviewed-limit checks, a workspace-global
P0 claim committed before network I/O, the already-audited RC2G protocol
validators, and an offline observation finalizer.

There is no retry, second POST, recovery, candidate override, frame override,
hash override, or job-number override.  Once a claim exists, every execution
failure is terminal ``UNKNOWN_DO_NOT_RETRY``.  A successful protocol run is
still not PASS until a separate observation record is validated and sealed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid

from PIL import Image, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    controller_stream,
    fnv1a,
    generate_fixture,
    validate_frame,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CLAIM_REGISTRY_ID,
    CLAIM_REGISTRY_RELATIVE_PATH,
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    describe_action_offline,
    result_file_sha256,
    validate_campaign_contract,
    validate_limit_profile,
    validate_result_record,
)
from tools import g1_s1_rc2g_map_baseline_once as _map  # noqa: E402
from tools import g1_s1_rc2g_quality_refresh_once as _quality  # noqa: E402
from tools.g1_s1_rc2g_n2_photo_campaign import (  # noqa: E402
    EXPECTED_MANIFEST_CANONICAL_SHA256,
    EXPECTED_MANIFEST_FILE_SHA256,
    MAP_FIXTURE,
    MAP_FRAME_SHA256,
    compile_campaign_manifest,
    validate_compiled_manifest,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-g1-s1-rc2g-n2p-fixed-action-runner"
CLAIM_KIND = "mf1750-visible-refresh-fixed-action-consumed-claim"
LOCK_KIND = "mf1750-g1-s1-rc2g-n2p-fixed-action-lock"
EVIDENCE_KIND = "mf1750-g1-s1-rc2g-n2p-action-evidence"
OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n2p-manual-observation"
FINALIZATION_KIND = "mf1750-g1-s1-rc2g-n2p-action-finalization"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n2p-fixed-action-description"

LOCK_FILENAME = "ATTEMPT-LOCK.json"
PROFILE_FILENAME = "REVIEWED-LIMIT-PROFILE.json"
EVIDENCE_FILENAME = "N2P-ACTION-EVIDENCE.json"
OBSERVATION_FILENAME = "N2P-OBSERVATION.json"
FINALIZATION_FILENAME = "N2P-FINALIZATION.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
CAMERA_CAPTURE_FILENAME = "N2P-CAMERA-CAPTURE.bin"
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)

EXPECTED_CAMPAIGN_CANONICAL_SHA256 = (
    "976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b"
)
EXPECTED_CAMPAIGN_FILE_SHA256 = (
    "d7d55f62f6e2392d42dd8d65ea5cd5d7c0c5179b4cd51b9109666b420a21d687"
)
EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256 = (
    "f23476c4c887057877e3f3f6c9315813bb761f6da57996b9eea538584a545cdb"
)
EXECUTION_SUPPLEMENT_FILE = (
    REPO_ROOT / "docs" / "N2P_RC2G_FIXED_EXECUTION_SUPPLEMENT_V2.json"
)
EXECUTION_SUPPLEMENT_CANONICAL_SHA256 = (
    "29cdb6ccb75d320d3b1e1fa6ea544f88196b16ca38d1f34ec84343afdc787099"
)
EXECUTION_SUPPLEMENT_FILE_SHA256 = (
    "f1d22bc22a0487bb0cd31b6be7d0c80ccb8f3ae2a86b60c88a8a11ec312865af"
)

FIXED_ACTION_SHA256S = {
    "q1-map-primer": "f8ff64bd6a63b1bbfe89b7776c14c3593f7adbbbfaec33a6e3942051db2d2ac4",
    "q1-target": "e5393a6907df9d01f5c898b6ceb03fe40d61d14bc02f538718710e991aab12a4",
    "q2-map-primer": "c2de02b4e97a77c9767eddd687fc0dfdd0f7ae801c185932eff00e036322620c",
    "q2-target": "3ec6e864b5c857b9c272745704885d55534690fa64d9299b46a9a6b389a5996b",
    "q3-map-primer": "9e90d7408087174659c9aeaa6f2a61a91d5099a61f8b1f115bd7d23c1eb0c1f6",
    "q3-target": "e08e7ed557f00b54537df773c275478831600f9aa5ef783daec8f787dac33677",
    "q4-map-primer": "5dc8f6fbdfbd10a3f26f2187cdc520c424b65e2ced1420d43cc6cde81c5e9ad7",
    "q4-target": "2918859bcf09b9aee4fffe4a08a8747c072e6cd6b083dc379736214ad8277060",
}
FIXED_ACTION_KEYS = tuple(FIXED_ACTION_SHA256S)

AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N2P_FIXED_ACTION__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"

DEFAULT_CLAIM_REGISTRY = REPO_ROOT / Path(CLAIM_REGISTRY_RELATIVE_PATH)
http_request = _quality.http_request

SCORING_CONTRACT = {
    "schema_version": 1,
    "contract_id": "n2p-natural-photo-visual-score-v1",
    "scale": {
        "minimum": 1,
        "maximum": 5,
        "direction": "higher_is_better",
        "anchors": {
            "1": "severe_and_dominant_defect",
            "2": "clearly_objectionable_defect",
            "3": "acceptable_with_visible_limitations",
            "4": "good_with_minor_limitations",
            "5": "excellent_for_this_panel_and_source",
        },
    },
    "dimensions": {
        "detail": "fine_subject_structure_and_edge_readability",
        "tone": "relative_light_dark_and_colour_tone_relationships",
        "gradients": "smoothness_without_false_bands_or_contours",
        "texture": "natural_texture_without_grain_clumping_or_worms",
        "artifacts": "absence_of_patterning_seams_ghosting_and_false_structure",
        "source_fidelity": "overall_match_to_the_frozen_reference_preview",
    },
    "pass_threshold": {
        "each_dimension_minimum": 3,
        "minimum_sum": 21,
        "minimum_mean": 3.5,
    },
    "separation": {
        "visual_scores_measure_image_quality_only": True,
        "electrical_checks_are_recorded_separately": True,
        "electrical_normality_does_not_increase_visual_scores": True,
        "electrical_failure_forces_overall_action_fail": True,
    },
}

CAMERA_OBSERVATION_CONTRACT = {
    "schema_version": 1,
    "contract_id": "n2p-fixed-camera-manual-observation-v1",
    "manual_observation": {
        "full_panel_required": True,
        "reference_preview_required": True,
        "viewing_distance_cm_inclusive": [40, 100],
        "stable_lighting_required": True,
        "same_observer_preferred_across_q1_q4": True,
        "scores_must_be_assigned_before_cross_cell_ranking": True,
    },
    "camera": {
        "optional": True,
        "full_panel_uncropped_required_if_captured": True,
        "tripod_position_id": "n2p-fixed-position-v1",
        "lighting_setup_id": "n2p-fixed-lighting-v1",
        "exposure_mode": "manual-locked",
        "white_balance_mode": "manual-locked",
        "focus_mode": "manual-locked",
        "image_processing": "disabled-or-fixed",
        "same_camera_and_settings_required_across_q1_q4": True,
    },
    "electrical": {
        "record_3v3_cv_current_temperature": True,
        "record_no_restart_and_physical_cutoff": True,
        "score_visual_and_electrical_independently": True,
    },
}

SCORING_CONTRACT_SHA256 = (
    "7e2aa7e7ac9f85271e2b18101546f5a82b35966d21e93f0037449ef3762076a9"
)
CAMERA_OBSERVATION_CONTRACT_SHA256 = (
    "6e274ff0b3eb2ae35706e43e516b8a765eaaa280b062cecb6ddf06952f29901c"
)


class N2PFixedActionError(RuntimeError):
    """Rejected before the fixed action claim was committed."""


class N2PFixedActionUnknown(N2PFixedActionError):
    """The P0 claim exists; the action is terminal and must not be retried."""


@dataclass(frozen=True)
class _ActionSnapshot:
    key: str
    cell_id: str
    phase: str
    action: Mapping[str, Any]
    campaign: Mapping[str, Any]
    outer_manifest: Mapping[str, Any]
    cell: Mapping[str, Any]
    frame: bytes
    reference_preview: Mapping[str, Any]


@dataclass(frozen=True)
class FixedExecutionSpec:
    """Internal compiler-to-executor boundary shared by fixed wrappers.

    A wrapper may construct this only from an already validated compiler
    artifact.  No CLI parser in this module accepts any of these fields.
    Keeping frame, claim, dependency, and job sequencing in one immutable
    object prevents a later wrapper from accidentally adding a frame/hash/job
    override while reusing the claim and terminal-result machinery.
    """

    selection_key: str
    campaign: Mapping[str, Any]
    action: Mapping[str, Any]
    frame: bytes
    reference_preview: Mapping[str, Any]
    expected_initial_job_id: int
    expected_initial_operation_id: int
    expected_target_job_id: int
    expected_target_operation_id: int


@dataclass(frozen=True)
class _PriorBundle:
    result: Mapping[str, Any]
    result_sha256: str
    evidence: Mapping[str, Any]
    observation: Mapping[str, Any]
    finalization: Mapping[str, Any]


@dataclass(frozen=True)
class _Claim:
    registry: Path
    filename: str
    record: Mapping[str, Any]
    file_sha256: str

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.filename,
            "file_sha256": self.file_sha256,
            "attempt_id": self.record["attempt_id"],
            "action_identity_sha256": self.record["action_identity_sha256"],
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
        raise N2PFixedActionError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


if _sha256(_canonical_json(SCORING_CONTRACT)) != SCORING_CONTRACT_SHA256:
    raise RuntimeError("frozen N2P visual scoring contract changed")
if (
    _sha256(_canonical_json(CAMERA_OBSERVATION_CONTRACT))
    != CAMERA_OBSERVATION_CONTRACT_SHA256
):
    raise RuntimeError("frozen N2P camera/observation contract changed")


def required_authorization_confirmation(action_key: str) -> str:
    """Return the exact future operator token for one frozen action."""

    try:
        action_sha = FIXED_ACTION_SHA256S[action_key]
    except KeyError as error:
        raise N2PFixedActionError("action_key is not one of the eight frozen actions") from error
    return f"{AUTHORIZATION_PREFIX}{action_sha.upper()}{AUTHORIZATION_SUFFIX}"


def authorization_confirmation_sha256(action_key: str) -> str:
    return _sha256(required_authorization_confirmation(action_key).encode("ascii"))


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    """Reject a leaf or ancestor that can redirect evidence I/O."""

    try:
        lexical = path.absolute()
    except OSError as error:
        raise N2PFixedActionError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise N2PFixedActionError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise N2PFixedActionError(
                f"{label} leaf and ancestors must not be a symlink or reparse point"
            )


def _safe_regular_file(path: Path, *, label: str) -> Path:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise N2PFixedActionError(str(error)) from error
    _reject_reparse_path_chain(path, label=label)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise N2PFixedActionError(f"{label} does not resolve locally: {error}") from error
    try:
        require_local_regular_path_syntax(resolved, label=f"resolved {label}")
    except LocalPathSafetyError as error:
        raise N2PFixedActionError(str(error)) from error
    if resolved.is_symlink() or not resolved.is_file():
        raise N2PFixedActionError(f"{label} must resolve to a regular local file")
    return resolved


def _strict_json_file(
    path: Path, *, label: str, allow_single_trailing_lf: bool = False
) -> tuple[Mapping[str, Any], bytes]:
    if not isinstance(path, Path):
        raise N2PFixedActionError(f"{label} path must be pathlib.Path")
    try:
        resolved = _safe_regular_file(path, label=label)
        payload = resolved.read_bytes()
    except N2PFixedActionError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise N2PFixedActionError(f"could not read {label}: {error}") from error

    def reject_constant(token: str) -> None:
        raise ValueError(f"forbidden JSON constant {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key {key!r}")
            value[key] = item
        return value

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise N2PFixedActionError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(parsed, Mapping):
        raise N2PFixedActionError(f"{label} root must be an object")
    compared_payload = (
        payload[:-1]
        if allow_single_trailing_lf
        and payload.endswith(b"\n")
        and not payload.endswith(b"\n\n")
        else payload
    )
    if compared_payload != canonical_json_bytes(parsed):
        raise N2PFixedActionError(f"{label} must use canonical JSON bytes")
    return parsed, payload


def _load_execution_supplement() -> Mapping[str, Any]:
    supplement, payload = _strict_json_file(
        EXECUTION_SUPPLEMENT_FILE,
        label="N2P V2 execution supplement",
        allow_single_trailing_lf=True,
    )
    if _sha256(payload) != EXECUTION_SUPPLEMENT_FILE_SHA256:
        raise N2PFixedActionError("N2P execution supplement file identity changed")
    if set(supplement) != {
        "schema_version",
        "kind",
        "supplement_id",
        "source",
        "fixed_actions",
        "execution_contract",
        "visual_contracts",
        "readiness",
        "integrity",
    }:
        raise N2PFixedActionError("N2P execution supplement fields changed")
    unsigned = dict(supplement)
    integrity = unsigned.pop("integrity")
    if (
        supplement["schema_version"] != 2
        or supplement["kind"]
        != "mf1750-g1-s1-rc2g-n2p-fixed-execution-supplement"
        or supplement["supplement_id"] != "g1-s1-rc2g-n2p-fixed-execution-v2"
        or not isinstance(integrity, Mapping)
        or integrity.get("canonical_sha256")
        != EXECUTION_SUPPLEMENT_CANONICAL_SHA256
        or _sha256(_canonical_json(unsigned))
        != EXECUTION_SUPPLEMENT_CANONICAL_SHA256
    ):
        raise N2PFixedActionError("N2P execution supplement integrity is invalid")
    source = supplement["source"]
    visual = supplement["visual_contracts"]
    execution = supplement["execution_contract"]
    readiness = supplement["readiness"]
    if (
        supplement["fixed_actions"] != FIXED_ACTION_SHA256S
        or not isinstance(source, Mapping)
        or source.get("outer_manifest_canonical_sha256")
        != EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or source.get("outer_manifest_file_sha256")
        != EXPECTED_CAMPAIGN_FILE_SHA256
        or source.get("p0_campaign_canonical_sha256")
        != EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
        or source.get("compiler_is_only_action_frame_hash_job_source") is not True
        or source.get("source_manifest_modified") is not False
        or not isinstance(visual, Mapping)
        or visual.get("scoring_contract_sha256") != SCORING_CONTRACT_SHA256
        or visual.get("camera_observation_contract_sha256")
        != CAMERA_OBSERVATION_CONTRACT_SHA256
        or visual.get("camera_capture_optional_for_single_action_verdict") is not True
        or visual.get(
            "cross_candidate_camera_comparability_requires_verified_captures_for_all_four_targets"
        )
        is not True
        or not isinstance(execution, Mapping)
        or execution.get("cli_candidate_frame_hash_job_overrides") is not False
        or execution.get("workspace_global_p0_claim_before_network") is not True
        or execution.get("maximum_post_requests_per_action") != 1
        or execution.get("automatic_retry") is not False
        or execution.get("automatic_recovery") is not False
        or not isinstance(readiness, Mapping)
        or readiness.get("supplement_contract_ready") is not True
        or readiness.get("hardware_ready") is not False
        or readiness.get("source_manifest_readiness_is_not_rewritten") is not True
        or readiness.get("describe_only_always_hardware_ready_false") is not True
    ):
        raise N2PFixedActionError("N2P execution supplement binding changed")
    return supplement


def _validate_frozen_outer_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    validate_compiled_manifest(manifest)
    if (
        EXPECTED_MANIFEST_CANONICAL_SHA256 != EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or EXPECTED_MANIFEST_FILE_SHA256 != EXPECTED_CAMPAIGN_FILE_SHA256
        or manifest["manifest_integrity"]["canonical_sha256"]
        != EXPECTED_CAMPAIGN_CANONICAL_SHA256
        or _sha256(_canonical_json(manifest)) != EXPECTED_CAMPAIGN_FILE_SHA256
    ):
        raise N2PFixedActionError("frozen N2P outer campaign identity changed")
    campaign = validate_campaign_contract(manifest["p0_campaign_contract"])
    if campaign["integrity"]["canonical_sha256"] != EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256:
        raise N2PFixedActionError("frozen N2P P0 campaign identity changed")
    actual: dict[str, str] = {}
    for action in campaign["actions"]:
        identity = action["identity"]
        key = f"{str(identity['cell_id']).lower()}-{'map-primer' if identity['phase'] == 'map-primer' else 'target'}"
        actual[key] = action["action_identity_sha256"]
    if actual != FIXED_ACTION_SHA256S:
        raise N2PFixedActionError("frozen N2P eight-action allowlist changed")
    return manifest


def _load_action_snapshot(
    action_key: str,
    *,
    _validated_manifest: Optional[Mapping[str, Any]] = None,
) -> _ActionSnapshot:
    if action_key not in FIXED_ACTION_SHA256S:
        raise N2PFixedActionError("action_key is not one of the eight frozen actions")
    _load_execution_supplement()
    try:
        manifest = _validate_frozen_outer_manifest(
            compile_campaign_manifest()
            if _validated_manifest is None
            else _validated_manifest
        )
    except (CampaignContractError, OSError, ValueError) as error:
        raise N2PFixedActionError(f"frozen N2P campaign validation failed: {error}") from error
    campaign = manifest["p0_campaign_contract"]
    action_sha = FIXED_ACTION_SHA256S[action_key]
    actions = [
        action
        for action in campaign["actions"]
        if action["action_identity_sha256"] == action_sha
    ]
    if len(actions) != 1:
        raise N2PFixedActionError("selected frozen action is not unique")
    action = actions[0]
    cell_id = action["identity"]["cell_id"]
    cells = [cell for cell in manifest["cells"] if cell["cell_id"] == cell_id]
    if len(cells) != 1:
        raise N2PFixedActionError("selected frozen cell is not unique")
    cell = cells[0]
    phase = action["identity"]["phase"]
    if phase == "map-primer":
        frame = generate_fixture(MAP_FIXTURE)
        reference_preview = {
            "kind": "map_fixture_frame",
            "workspace_relative_path": None,
            "sha256": MAP_FRAME_SHA256,
        }
    elif phase == "target":
        relative = cell["candidate"]["artifact"]["workspace_relative_directory"]
        frame_path = REPO_ROOT / Path(relative) / "frame.bin"
        try:
            resolved_frame = _safe_regular_file(
                frame_path, label="frozen target frame"
            )
            expected_directory = (REPO_ROOT / Path(relative)).resolve(strict=True)
            if resolved_frame.parent != expected_directory or not _is_within(
                resolved_frame, REPO_ROOT.resolve(strict=True)
            ):
                raise N2PFixedActionError(
                    "frozen target frame escaped its compiler-validated directory"
                )
            frame = resolved_frame.read_bytes()
        except OSError as error:
            raise N2PFixedActionError(f"could not read frozen target frame: {error}") from error
        preview = cell["candidate"]["previews"]["final"]
        reference_preview = {
            "kind": "strict_final_png",
            "workspace_relative_path": f"{relative}/final.png",
            "sha256": preview["sha256"],
        }
    else:
        raise N2PFixedActionError("frozen action phase changed")
    try:
        validate_frame(frame)
    except ValueError as error:
        raise N2PFixedActionError(f"frozen frame validation failed: {error}") from error
    frame_record = action["identity"]["frame"]
    actual_controllers = []
    for mapping in _quality.FIXED_CONTROLLER_MAPPINGS:
        stream = controller_stream(frame, mapping)
        actual_controllers.append((_sha256(stream), f"0x{fnv1a(stream):08X}"))
    if (
        _sha256(frame) != frame_record["sha256"]
        or f"0x{fnv1a(frame):08X}" != frame_record["fnv1a"]
        or actual_controllers
        != [
            (controller["dtm_sha256"], controller["dtm_fnv1a"])
            for controller in frame_record["controllers"]
        ]
    ):
        raise N2PFixedActionError("frozen action frame/DTM identity changed")
    return _ActionSnapshot(
        key=action_key,
        cell_id=cell_id,
        phase=phase,
        action=action,
        campaign=campaign,
        outer_manifest=manifest,
        cell=cell,
        frame=frame,
        reference_preview=reference_preview,
    )


def _require_physical_panel_binding(snapshot: _ActionSnapshot) -> None:
    """Reject the legacy offline placeholder before claim creation or network I/O.

    The V2 campaign was compiled with an intentionally unbound panel serial.  A
    limit profile copied from that placeholder can satisfy the generic equality
    check, so the legacy live entry point must never treat it as a physical
    identity.  A separately materialized physical campaign owns new action and
    claim identities; this guard is deliberately not overridable by the CLI.
    """

    panel = snapshot.campaign.get("panel")
    serial = panel.get("serial") if isinstance(panel, Mapping) else None
    if (
        not isinstance(serial, str)
        or not serial.strip()
        or serial.strip().upper().startswith("UNBOUND")
    ):
        raise N2PFixedActionError(
            "legacy N2P live execution is disabled: the campaign panel is "
            "UNBOUND; materialize a physical-bound campaign with new action "
            "and claim identities"
        )


def _fixed_execution_spec(snapshot: _ActionSnapshot) -> FixedExecutionSpec:
    if snapshot.phase == "map-primer":
        job_contract = (0, 0, 1, 1)
    else:
        job_contract = (1, 1, 2, 2)
    spec = FixedExecutionSpec(
        selection_key=snapshot.key,
        campaign=snapshot.campaign,
        action=snapshot.action,
        frame=snapshot.frame,
        reference_preview=snapshot.reference_preview,
        expected_initial_job_id=job_contract[0],
        expected_initial_operation_id=job_contract[1],
        expected_target_job_id=job_contract[2],
        expected_target_operation_id=job_contract[3],
    )
    # Revalidate the generic boundary independently of the N2 outer manifest.
    campaign = validate_campaign_contract(spec.campaign)
    matches = [
        action
        for action in campaign["actions"]
        if action["action_identity_sha256"]
        == spec.action["action_identity_sha256"]
    ]
    if len(matches) != 1 or matches[0] != spec.action:
        raise N2PFixedActionError("fixed execution spec action is not unique in campaign")
    if (
        _sha256(spec.frame) != spec.action["identity"]["frame"]["sha256"]
        or spec.action["identity"]["request"]
        != {
            "method": "POST",
            "endpoint": "/api/frame",
            "body": "exact-canonical-frame-bytes",
            "maximum_post_requests": 1,
        }
        or spec.expected_target_job_id != spec.expected_initial_job_id + 1
        or spec.expected_target_operation_id != spec.expected_initial_operation_id + 1
    ):
        raise N2PFixedActionError("fixed execution spec frame/request/job contract changed")
    return spec


def _load_profile(path: Path) -> tuple[Mapping[str, Any], str]:
    profile, payload = _strict_json_file(path, label="reviewed N2P limit profile")
    try:
        validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N2PFixedActionError(f"reviewed limit profile is invalid: {error}") from error
    return profile, _sha256(payload)


def _validate_consumed_claim_reference(
    action_identity_sha256: str, reference: object
) -> Mapping[str, Any]:
    if (
        not isinstance(action_identity_sha256, str)
        or len(action_identity_sha256) != 64
        or any(character not in "0123456789abcdef" for character in action_identity_sha256)
    ):
        raise N2PFixedActionError("stored P0 claim action SHA-256 is invalid")
    expected_filename = f"{action_identity_sha256}.json"
    if not isinstance(reference, Mapping) or reference.get("registry_id") != CLAIM_REGISTRY_ID:
        raise N2PFixedActionError("stored P0 claim reference is invalid")
    if (
        reference.get("filename") != expected_filename
        or reference.get("action_identity_sha256") != action_identity_sha256
        or reference.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise N2PFixedActionError("stored P0 claim reference action/state changed")
    file_sha = reference.get("file_sha256")
    if (
        not isinstance(file_sha, str)
        or len(file_sha) != 64
        or any(character not in "0123456789abcdef" for character in file_sha)
    ):
        raise N2PFixedActionError("stored P0 claim reference SHA-256 is invalid")
    registry_path = DEFAULT_CLAIM_REGISTRY
    try:
        require_local_regular_path_syntax(
            registry_path, label="existing P0 fixed-action claim registry"
        )
    except LocalPathSafetyError as error:
        raise N2PFixedActionError(str(error)) from error
    _reject_reparse_path_chain(
        registry_path, label="existing P0 fixed-action claim registry"
    )
    try:
        registry = registry_path.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
    except OSError as error:
        raise N2PFixedActionError(f"stored P0 claim registry is unavailable: {error}") from error
    if not registry.is_dir() or not _is_within(registry, workspace):
        raise N2PFixedActionError("stored P0 claim registry escaped the workspace")
    record, payload = _strict_json_file(
        registry / expected_filename, label="consumed workspace-global P0 claim"
    )
    if (
        _sha256(payload) != file_sha
        or record.get("kind") != CLAIM_KIND
        or record.get("action_identity_sha256") != action_identity_sha256
        or record.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
        or record.get("attempt_id") != reference.get("attempt_id")
    ):
        raise N2PFixedActionError("consumed workspace-global P0 claim binding changed")
    return record


def _load_prior_bundle(path: Path, snapshot: _ActionSnapshot) -> _PriorBundle:
    if snapshot.phase != "target":
        raise N2PFixedActionError("only a target action may bind a primer result")
    result, result_payload = _strict_json_file(path, label="same-cell primer P0 result")
    try:
        validate_result_record(result)
    except CampaignContractError as error:
        raise N2PFixedActionError(f"same-cell primer result is invalid: {error}") from error
    actual_result_sha = _sha256(result_payload)
    if result_file_sha256(result) != actual_result_sha:
        raise N2PFixedActionError("primer result whole-file identity is invalid")
    expected_prior = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    if (
        result["action_identity_sha256"] != expected_prior
        or result["state"] != ResultState.PASS.value
    ):
        raise N2PFixedActionError("primer result is cross-cell, replayed, or not PASS")
    directory = path.parent
    evidence, evidence_payload = _strict_json_file(
        directory / EVIDENCE_FILENAME, label="same-cell primer protocol evidence"
    )
    observation, observation_payload = _strict_json_file(
        directory / OBSERVATION_FILENAME, label="same-cell primer observation"
    )
    finalization, finalization_payload = _strict_json_file(
        directory / FINALIZATION_FILENAME, label="same-cell primer finalization"
    )
    _validate_consumed_claim_reference(expected_prior, evidence.get("claim"))
    if (
        evidence.get("kind") != EVIDENCE_KIND
        or evidence.get("phase") != "map-primer"
        or evidence.get("action_identity_sha256") != expected_prior
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or observation.get("kind") != OBSERVATION_KIND
        or observation.get("action_identity_sha256") != expected_prior
        or observation.get("visual_pass") is not True
        or finalization.get("kind") != FINALIZATION_KIND
        or finalization.get("action_identity_sha256") != expected_prior
        or finalization.get("state") != ResultState.PASS.value
        or finalization.get("protocol_evidence_file_sha256") != _sha256(evidence_payload)
        or finalization.get("observation_file_sha256") != _sha256(observation_payload)
        or result["evidence_manifest_sha256"] != _sha256(finalization_payload)
    ):
        raise N2PFixedActionError("same-cell primer evidence/finalization binding is invalid")
    map_visual = observation.get("visual")
    if not isinstance(map_visual, Mapping) or any(value is not True for value in map_visual.values()):
        raise N2PFixedActionError("same-cell primer MAP fidelity was not fully passed")
    return _PriorBundle(result, actual_result_sha, evidence, observation, finalization)


def _prepare_fixed_inputs(
    snapshot: _ActionSnapshot,
    *,
    limit_profile_file: Optional[Path] = None,
    evaluated_at: Optional[str] = None,
    primer_result_file: Optional[Path] = None,
) -> tuple[
    dict[str, Any],
    Optional[Mapping[str, Any]],
    Optional[str],
    Optional[_PriorBundle],
]:
    _fixed_execution_spec(snapshot)
    blockers: list[str] = []
    profile_file_sha: Optional[str] = None
    profile: Optional[Mapping[str, Any]] = None
    prior: Optional[_PriorBundle] = None
    p0_description: Optional[Mapping[str, Any]] = None
    if limit_profile_file is None:
        blockers.append("reviewed_limit_profile_missing")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if snapshot.phase == "target" and primer_result_file is None:
        blockers.append("same_cell_canonical_pass_primer_result_missing")
    if snapshot.phase == "map-primer" and primer_result_file is not None:
        raise N2PFixedActionError("map-primer must not receive a prior result")
    if primer_result_file is not None:
        prior = _load_prior_bundle(primer_result_file, snapshot)
    if limit_profile_file is not None and evaluated_at is not None:
        profile, profile_file_sha = _load_profile(limit_profile_file)
        try:
            p0_description = describe_action_offline(
                snapshot.campaign,
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=profile,
                evaluated_at=evaluated_at,
                prior_result=prior.result if prior else None,
                prior_result_sha256=prior.result_sha256 if prior else None,
            )
        except CampaignContractError as error:
            raise N2PFixedActionError(f"P0 action description failed: {error}") from error
        blockers.extend(p0_description["blockers"])
    blockers = list(dict.fromkeys(blockers))
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "campaign_canonical_sha256": EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "p0_campaign_canonical_sha256": EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
        "execution_supplement_canonical_sha256": (
            EXECUTION_SUPPLEMENT_CANONICAL_SHA256
        ),
        "execution_supplement_file_sha256": EXECUTION_SUPPLEMENT_FILE_SHA256,
        "execution_supplement_contract_ready": True,
        "source_manifest_readiness_unchanged": dict(
            snapshot.outer_manifest["readiness"]
        ),
        "source_manifest_readiness_superseded_only_by_bound_v2_supplement": True,
        "phase": snapshot.phase,
        "cell_id": snapshot.cell_id,
        "frame": dict(snapshot.action["identity"]["frame"]),
        "reference_preview": dict(snapshot.reference_preview),
        "profile_file_sha256": profile_file_sha,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "p0_description": dict(p0_description) if p0_description else None,
        "contract_ready": bool(p0_description and p0_description["contract_ready"]),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "required_authorization_confirmation_sha256": authorization_confirmation_sha256(
            snapshot.key
        ),
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": CAMERA_OBSERVATION_CONTRACT_SHA256,
        "camera_capture_optional_for_single_action_verdict": True,
        "cross_candidate_camera_comparability": (
            "unavailable_until_verified_fixed-camera_captures_exist_for_all_four_targets"
        ),
        "blockers": blockers,
    }
    return description, profile, profile_file_sha, prior


def describe_n2p_fixed_action(
    action_key: str,
    *,
    limit_profile_file: Optional[Path] = None,
    evaluated_at: Optional[str] = None,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Deep-describe one frozen action without claim, authorization, or network."""

    snapshot = _load_action_snapshot(action_key)
    description, _profile, _profile_sha, _prior = _prepare_fixed_inputs(
        snapshot,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    return description


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_result_destination(path: Path) -> Path:
    if not isinstance(path, Path):
        raise N2PFixedActionError("result_dir must be pathlib.Path")
    try:
        require_local_regular_path_syntax(path, label="N2P result directory")
        if os.path.lexists(path):
            raise N2PFixedActionError("result directory already exists; refusing replay")
        _reject_reparse_path_chain(path.parent, label="N2P result directory parent")
        parent = path.parent.resolve(strict=True)
    except N2PFixedActionError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise N2PFixedActionError(f"invalid result directory: {error}") from error
    if not parent.is_dir():
        raise N2PFixedActionError("result parent must be a directory")
    return parent / path.name


def _claim_registry() -> Path:
    path = DEFAULT_CLAIM_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="P0 fixed-action claim registry")
        if os.path.lexists(path) and path.is_symlink():
            raise N2PFixedActionError("P0 claim registry must not be a symlink")
        _reject_reparse_path_chain(path, label="P0 fixed-action claim registry")
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise N2PFixedActionError("P0 claim registry parent escaped the workspace")
        path.mkdir(exist_ok=True)
        _reject_reparse_path_chain(path, label="P0 fixed-action claim registry")
        registry = path.resolve(strict=True)
    except N2PFixedActionError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise N2PFixedActionError(f"could not prepare P0 claim registry: {error}") from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise N2PFixedActionError("P0 claim registry escaped the workspace")
    return registry


def _atomic_commit(path: Path, payload: bytes, *, unknown_after_commit: bool) -> None:
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        if unknown_after_commit:
            raise N2PFixedActionUnknown(
                f"{path.name} already exists; action is permanently consumed"
            ) from error
        raise N2PFixedActionError(f"{path.name} already exists; refusing overwrite") from error
    except OSError as error:
        if unknown_after_commit:
            raise N2PFixedActionUnknown(
                f"atomic state of {path.name} is uncertain; do not retry"
            ) from error
        raise N2PFixedActionError(f"could not atomically commit {path.name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


def _claim_action(
    snapshot: _ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    profile: Mapping[str, Any],
    profile_file_sha256: str,
    prior: Optional[_PriorBundle],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
) -> _Claim:
    declaration = snapshot.action["claim"]
    if (
        declaration["registry_id"] != CLAIM_REGISTRY_ID
        or declaration["workspace_relative_registry"] != CLAIM_REGISTRY_RELATIVE_PATH
        or declaration["filename"]
        != f"{snapshot.action['action_identity_sha256']}.json"
        or declaration["create_before_network"] is not True
    ):
        raise N2PFixedActionError("P0 workspace-global claim declaration changed")
    registry = _claim_registry()
    if _is_within(destination, registry):
        raise N2PFixedActionError("result directory must not overlap the claim registry")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "campaign_canonical_sha256": EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "p0_campaign_canonical_sha256": EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
        "execution_supplement_file_sha256": EXECUTION_SUPPLEMENT_FILE_SHA256,
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("ascii")
        ),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = _canonical_json(record)
    filename = declaration["filename"]
    _atomic_commit(registry / filename, payload, unknown_after_commit=True)
    return _Claim(registry, filename, record, _sha256(payload))


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical_json(value)
    _atomic_commit(directory / filename, payload, unknown_after_commit=False)
    return _sha256(payload)


def _temperature(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N2PFixedActionError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or not -50 <= normalized <= 100:
        raise N2PFixedActionError(f"{label} is outside the valid measurement range")
    return normalized


def _rfc3339(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise N2PFixedActionError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N2PFixedActionError(f"{label} is not a valid RFC3339 instant") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N2PFixedActionError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _target_contract(
    snapshot: _ActionSnapshot,
    *,
    required_authorization_confirmation_override: Optional[str] = None,
) -> _quality._RunContract:
    frame_record = snapshot.action["identity"]["frame"]
    candidate = snapshot.cell["candidate"]
    directory = REPO_ROOT / Path(
        candidate["artifact"]["workspace_relative_directory"]
    )
    quality_snapshot = _quality._CandidateSnapshot(
        directory=directory,
        manifest=candidate,
        manifest_bytes=b"",
        manifest_file_sha256=candidate["artifact"]["manifest_file_sha256"],
        manifest_canonical_sha256=candidate["artifact"]["manifest_canonical_sha256"],
        algorithm=candidate["algorithm"],
        frame=snapshot.frame,
        frame_sha256=frame_record["sha256"],
        frame_fnv1a=int(frame_record["fnv1a"], 16),
        controllers=tuple(frame_record["controllers"]),
    )
    return _quality._RunContract(
        snapshot=quality_snapshot,
        expected_prior_job_id=1,
        expected_prior_operation_id=1,
        expected_prior_frame_sha256=MAP_FRAME_SHA256,
        expected_prior_frame_fnv1a=_map.EXPECTED_FRAME_FNV1A,
        expected_prior_cs1_dtm_fnv1a=_map.EXPECTED_CS1_DTM_FNV1A,
        expected_prior_cs2_dtm_fnv1a=_map.EXPECTED_CS2_DTM_FNV1A,
        expected_target_job_id=2,
        expected_target_operation_id=2,
        action_identity=snapshot.action["identity"],
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        required_authorization_confirmation=(
            required_authorization_confirmation_override
            if required_authorization_confirmation_override is not None
            else required_authorization_confirmation(snapshot.key)
        ),
    )


def _execute_protocol(
    snapshot: _ActionSnapshot,
    prior: Optional[_PriorBundle],
    base_url: str,
    *,
    audit_sink: dict[str, Any],
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
    required_authorization_confirmation_override: Optional[str] = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    requester: _map._AuditedRequester | _quality._AuditedRequester
    if snapshot.phase == "map-primer":
        requester = _map._AuditedRequester(http_request)
    else:
        requester = _quality._AuditedRequester(http_request)
    try:
        if snapshot.phase == "map-primer":
            fresh = _map._validate_fresh_boot_state(base_url, requester)
            report = _map._perform_refresh_once(
                base_url,
                snapshot.frame,
                requester,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
            )
            raw_job = _map._get_json_object(
                base_url, "/api/job", label="N2P MAP immutable job", requester=requester
            )
            raw_diagnostic = _map._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N2P MAP immutable diagnostic",
                requester=requester,
            )
            gpio = _map._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N2P MAP post-refresh GPIO",
                requester=requester,
            )
            completed = _map._validate_completed_map_evidence(
                report, raw_job, raw_diagnostic, gpio, snapshot.frame
            )
            protocol = {
                "fresh_boot_preflight": dict(fresh),
                "completed_map_evidence": dict(completed),
            }
        else:
            if prior is None:
                raise N2PFixedActionError(
                    "target protocol requires a same-cell primer bundle"
                )
            contract = _target_contract(
                snapshot,
                required_authorization_confirmation_override=(
                    required_authorization_confirmation_override
                ),
            )
            prior_completed = prior.evidence.get("protocol_evidence", {}).get(
                "completed_map_evidence"
            )
            if not isinstance(prior_completed, Mapping):
                raise N2PFixedActionError("stored primer lacks exact MAP protocol evidence")
            exact_prior = {
                "job_raw": prior_completed.get("job_raw"),
                "diagnostic_raw": prior_completed.get("diagnostic_raw"),
            }
            live_prior = _quality._validate_prior(
                base_url,
                requester,
                contract,
                expected_exact_prior_evidence=exact_prior,
            )
            report = _quality._perform_refresh_once(
                base_url,
                snapshot.frame,
                requester,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
            )
            _quality._validate_network_report(report, contract)
            raw_job = _quality._get_json_object(
                base_url,
                "/api/job",
                label="N2P target immutable job reread",
                requester=requester,
            )
            if raw_job != report.get("job"):
                raise N2PFixedActionError("target immutable job changed between reads")
            raw_diagnostic = _quality._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N2P target immutable diagnostic reread",
                requester=requester,
            )
            normalized = _quality._validate_target_raw_diagnostic(
                raw_diagnostic, report, contract
            )
            gpio_raw = _quality._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N2P target post-refresh GPIO",
                requester=requester,
            )
            gpio = _quality._validate_gpio_snapshot(
                gpio_raw, label="N2P target post-refresh GPIO"
            )
            protocol = {
                "same_cell_primer_live_preflight": dict(live_prior),
                "network_report": dict(report),
                "target_job_raw": dict(raw_job),
                "target_diagnostic_raw": dict(raw_diagnostic),
                "target_diagnostic_validated": dict(normalized),
                "post_refresh_gpio_status_raw": dict(gpio),
            }
        audit = requester.snapshot()
        if audit["post_attempt_count"] != 1 or audit["post_issued_count"] != 1:
            raise N2PFixedActionError("fixed action did not issue exactly one POST /api/frame")
        return protocol, audit
    finally:
        audit_sink.clear()
        audit_sink.update(requester.snapshot())


def _base_evidence(
    snapshot: _ActionSnapshot,
    *,
    attempt_id: str,
    claim: _Claim,
    recorded_at: str,
    profile: Mapping[str, Any],
    profile_file_sha256: str,
    evaluated_at: str,
    prior: Optional[_PriorBundle],
    start_temperature_c: float,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "campaign_canonical_sha256": EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "p0_campaign_canonical_sha256": EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
        "execution_supplement_file_sha256": EXECUTION_SUPPLEMENT_FILE_SHA256,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
        "profile_evaluated_at": evaluated_at,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_temperature_c": start_temperature_c,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": CAMERA_OBSERVATION_CONTRACT_SHA256,
        "maximum_post_requests": 1,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
    }


def _record_unknown(
    destination: Optional[Path],
    base: Mapping[str, Any],
    *,
    requester_audit: Optional[Mapping[str, Any]],
    error: BaseException,
) -> None:
    if destination is None or not destination.is_dir():
        return
    post_count = 0
    if requester_audit is not None:
        post_count = int(requester_audit.get("post_issued_count", 0))
    unknown_evidence = {
        **dict(base),
        "outcome": "UNKNOWN_DO_NOT_RETRY",
        "protocol_verified": False,
        "protocol_evidence": None,
        "request_audit": dict(requester_audit) if requester_audit else None,
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    evidence_sha = _write_new(destination, EVIDENCE_FILENAME, unknown_evidence)
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=_utc_now(),
        evidence_manifest_sha256=evidence_sha,
        post_request_count=post_count,
        details="claim consumed; no retry or recovery is permitted",
    )
    _write_new(destination, P0_RESULT_FILENAME, result)


def run_n2p_fixed_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    limit_profile_file: Path,
    evaluated_at: str,
    authorization_confirmation: str,
    start_temperature_c: float,
    primer_result_file: Optional[Path] = None,
    confirm_reviewed_panel_and_build: bool = False,
    confirm_supervised_supply_cv_current_normal: bool = False,
    confirm_physical_cutoff_available: bool = False,
    confirm_single_visible_refresh: bool = False,
    confirm_controller_fresh_boot: bool = False,
    confirm_map_fidelity_from_primer: bool = False,
    confirm_esp32_not_restarted_since_primer: bool = False,
    job_timeout_s: float = _quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = _quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consume the P0 claim, then perform exactly one frozen visible refresh."""

    snapshot = _load_action_snapshot(action_key)
    _require_physical_panel_binding(snapshot)
    destination = _prepare_result_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N2PFixedActionError("base_url must be a non-empty device root URL")
    description, profile, profile_file_sha, prior = _prepare_fixed_inputs(
        snapshot,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    if not description["contract_ready"]:
        raise N2PFixedActionError(
            "reviewed P0 contract is not ready: " + ", ".join(description["blockers"])
        )
    if profile is None or profile_file_sha is None:
        raise N2PFixedActionError("reviewed profile did not survive preclaim validation")
    start_temp = _temperature(start_temperature_c, label="start_temperature_c")
    limits = profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N2PFixedActionError("start temperature is outside the reviewed profile")
    common_confirmations = {
        "reviewed_panel_and_build": confirm_reviewed_panel_and_build,
        "supervised_supply_cv_current_normal": confirm_supervised_supply_cv_current_normal,
        "physical_cutoff_available": confirm_physical_cutoff_available,
        "single_visible_refresh": confirm_single_visible_refresh,
    }
    phase_confirmations = (
        {"controller_fresh_boot": confirm_controller_fresh_boot}
        if snapshot.phase == "map-primer"
        else {
            "map_fidelity_from_same_cell_primer": confirm_map_fidelity_from_primer,
            "esp32_not_restarted_since_primer": confirm_esp32_not_restarted_since_primer,
        }
    )
    confirmations = {**common_confirmations, **phase_confirmations}
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N2PFixedActionError("all action-specific physical confirmations must be true")
    expected_confirmation = required_authorization_confirmation(action_key)
    if authorization_confirmation != expected_confirmation:
        raise N2PFixedActionError("exact fixed-action authorization confirmation is required")

    attempt_id = uuid.uuid4().hex
    claimed_at = _utc_now()
    claim = _claim_action(
        snapshot,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        destination=destination,
        profile=profile,
        profile_file_sha256=profile_file_sha,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
    )
    created_destination: Optional[Path] = None
    audit_capture: dict[str, Any] = {}
    requester_audit: Optional[Mapping[str, Any]] = audit_capture
    base = _base_evidence(
        snapshot,
        attempt_id=attempt_id,
        claim=claim,
        recorded_at=claimed_at,
        profile=profile,
        profile_file_sha256=profile_file_sha,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
    )
    try:
        destination.mkdir()
        created_destination = destination
        _write_new(
            destination,
            LOCK_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": LOCK_KIND,
                "attempt_id": attempt_id,
                "action_key": action_key,
                "action_identity_sha256": snapshot.action["action_identity_sha256"],
                "claim": claim.reference(),
                "confirmations": confirmations,
                "authorization_confirmation_sha256": authorization_confirmation_sha256(
                    action_key
                ),
                "state": "authorization_permanently_consumed_do_not_rerun",
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
        )
        _write_new(destination, PROFILE_FILENAME, profile)
        protocol, requester_audit = _execute_protocol(
            snapshot,
            prior,
            base_url,
            audit_sink=audit_capture,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        evidence = {
            **base,
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
            "protocol_completed_at": _utc_now(),
            "protocol_evidence": dict(protocol),
            "request_audit": dict(requester_audit),
            "error": None,
        }
        _write_new(destination, EVIDENCE_FILENAME, evidence)
        return evidence
    except BaseException as error:
        try:
            _record_unknown(
                created_destination,
                base,
                requester_audit=requester_audit,
                error=error,
            )
        except BaseException:
            pass
        raise N2PFixedActionUnknown(
            "N2P action is UNKNOWN_DO_NOT_RETRY; its workspace-global claim is permanent"
        ) from error


def _require_keys(value: object, keys: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise N2PFixedActionError(f"{label} fields differ from the frozen contract")
    return value


def _validate_observation(
    observation: Mapping[str, Any],
    snapshot: _ActionSnapshot,
    profile: Mapping[str, Any],
    *,
    camera_base_directory: Path,
    minimum_observed_at: datetime,
) -> tuple[bool, bool, bool, float, Optional[bytes], Optional[Mapping[str, Any]]]:
    root = _require_keys(
        observation,
        {
            "schema_version",
            "kind",
            "action_key",
            "action_identity_sha256",
            "observed_at",
            "observer_id",
            "full_panel_inspected",
            "reference_preview_sha256",
            "viewing_distance_cm",
            "stable_lighting",
            "visual",
            "electrical",
            "post_refresh_temperature_c",
            "camera",
        },
        label="N2P observation",
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != OBSERVATION_KIND
        or root["action_key"] != snapshot.key
        or root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or not isinstance(root["observer_id"], str)
        or not root["observer_id"].strip()
        or root["full_panel_inspected"] is not True
        or root["reference_preview_sha256"] != snapshot.reference_preview["sha256"]
        or root["stable_lighting"] is not True
    ):
        raise N2PFixedActionError("N2P observation identity/environment is invalid")
    observed_at = _rfc3339(root["observed_at"], label="observation.observed_at")
    if observed_at < minimum_observed_at:
        raise N2PFixedActionError(
            "observation timestamp predates the completed visible-refresh protocol"
        )
    now = _rfc3339(_utc_now(), label="current finalization time")
    if observed_at > now + timedelta(minutes=15):
        raise N2PFixedActionError(
            "observation timestamp is implausibly far in the future"
        )
    distance = root["viewing_distance_cm"]
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not 40 <= distance <= 100:
        raise N2PFixedActionError("viewing distance must be within frozen 40..100 cm")
    if snapshot.phase == "map-primer":
        visual = _require_keys(
            root["visual"],
            {
                "screen_matches_reference",
                "orientation_correct",
                "labels_legible",
                "center_seam_correct",
                "all_six_colors_present",
                "no_retained_old_regions",
            },
            label="MAP visual observation",
        )
        visual_pass = all(type(value) is bool and value for value in visual.values())
    else:
        visual = _require_keys(
            root["visual"],
            {
                "detail",
                "tone",
                "gradients",
                "texture",
                "artifacts",
                "source_fidelity",
                "screen_geometry_matches_reference",
                "no_retained_old_regions",
            },
            label="target visual scores",
        )
        scores = [visual[key] for key in SCORING_CONTRACT["dimensions"]]
        if any(type(score) is not int or not 1 <= score <= 5 for score in scores):
            raise N2PFixedActionError("every target visual score must be integer 1..5")
        threshold = SCORING_CONTRACT["pass_threshold"]
        visual_pass = (
            min(scores) >= threshold["each_dimension_minimum"]
            and sum(scores) >= threshold["minimum_sum"]
            and visual["screen_geometry_matches_reference"] is True
            and visual["no_retained_old_regions"] is True
        )
    electrical = _require_keys(
        root["electrical"],
        {
            "supply_3v3_normal",
            "cv_mode_normal",
            "current_normal",
            "temperature_normal",
            "no_odor_sound_hotspot_damage_or_voltage_droop",
            "esp32_did_not_restart_during_action",
            "physical_cutoff_available",
            "visual_quality_scored_independently_from_electrical",
        },
        label="electrical observation",
    )
    electrical_pass = all(type(value) is bool and value for value in electrical.values())
    camera = _require_keys(
        root["camera"],
        {
            "capture_performed",
            "file",
            "sha256",
            "camera_id",
            "tripod_position_id",
            "lighting_setup_id",
            "exposure_mode",
            "white_balance_mode",
            "focus_mode",
            "image_processing",
            "full_panel_uncropped",
        },
        label="camera observation",
    )
    capture = camera["capture_performed"]
    if type(capture) is not bool:
        raise N2PFixedActionError("camera.capture_performed must be boolean")
    camera_fields = set(camera) - {"capture_performed"}
    if not capture:
        if any(camera[field] is not None for field in camera_fields):
            raise N2PFixedActionError("uncaptured camera fields must all be null")
        camera_payload: Optional[bytes] = None
        camera_binding: Optional[Mapping[str, Any]] = None
    else:
        expected = CAMERA_OBSERVATION_CONTRACT["camera"]
        fixed = {
            "tripod_position_id": expected["tripod_position_id"],
            "lighting_setup_id": expected["lighting_setup_id"],
            "exposure_mode": expected["exposure_mode"],
            "white_balance_mode": expected["white_balance_mode"],
            "focus_mode": expected["focus_mode"],
            "image_processing": expected["image_processing"],
            "full_panel_uncropped": True,
        }
        if any(camera[key] != value for key, value in fixed.items()):
            raise N2PFixedActionError("camera capture does not use the frozen setup")
        if not all(isinstance(camera[key], str) and camera[key] for key in ("file", "camera_id")):
            raise N2PFixedActionError("camera file and camera_id are required")
        sha = camera["sha256"]
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise N2PFixedActionError("camera SHA-256 is invalid")
        declared_path = Path(str(camera["file"]))
        capture_path = (
            declared_path
            if declared_path.is_absolute()
            else camera_base_directory / declared_path
        )
        resolved_capture = _safe_regular_file(
            capture_path, label="N2P camera capture"
        )
        try:
            camera_payload = resolved_capture.read_bytes()
        except OSError as error:
            raise N2PFixedActionError(f"could not read N2P camera capture: {error}") from error
        if _sha256(camera_payload) != sha:
            raise N2PFixedActionError("camera file bytes do not match declared SHA-256")
        try:
            with Image.open(BytesIO(camera_payload)) as opened:
                image_format = opened.format
                width, height = opened.size
                opened.verify()
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise N2PFixedActionError(f"camera capture is not a valid image: {error}") from error
        if not image_format or width <= 0 or height <= 0:
            raise N2PFixedActionError("camera capture image metadata is invalid")
        camera_binding = {
            "copied_file": CAMERA_CAPTURE_FILENAME,
            "bytes": len(camera_payload),
            "sha256": sha,
            "decoded_format": image_format,
            "width": width,
            "height": height,
            "source_path_recorded_but_not_trusted_after_copy": str(camera["file"]),
        }
    post_temp = _temperature(
        root["post_refresh_temperature_c"], label="post_refresh_temperature_c"
    )
    thermal_pass = post_temp <= profile["limits"]["maximum_post_refresh_temperature_c"]
    return (
        visual_pass,
        electrical_pass,
        thermal_pass,
        post_temp,
        camera_payload,
        camera_binding,
    )


def finalize_n2p_observation(
    result_dir: Path,
    observation_file: Path,
) -> dict[str, Any]:
    """Validate a manual observation and create the immutable P0 result."""

    if not isinstance(result_dir, Path):
        raise N2PFixedActionError("result_dir must be pathlib.Path")
    _reject_reparse_path_chain(result_dir, label="N2P result directory")
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise N2PFixedActionError("result_dir must be an existing regular directory")
    for name in (OBSERVATION_FILENAME, FINALIZATION_FILENAME, P0_RESULT_FILENAME):
        if os.path.lexists(result_dir / name):
            raise N2PFixedActionError("observation was already finalized; refusing replay")
    evidence, evidence_payload = _strict_json_file(
        result_dir / EVIDENCE_FILENAME, label="N2P protocol evidence"
    )
    profile, profile_payload = _strict_json_file(
        result_dir / PROFILE_FILENAME, label="N2P copied reviewed limit profile"
    )
    try:
        validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N2PFixedActionError(f"copied reviewed limit profile is invalid: {error}") from error
    if (
        evidence.get("kind") != EVIDENCE_KIND
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("profile_file_sha256") != _sha256(profile_payload)
        or evidence.get("profile_canonical_sha256")
        != profile["integrity"]["canonical_sha256"]
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
    ):
        raise N2PFixedActionError("protocol evidence is not finalizable")
    _validate_consumed_claim_reference(
        str(evidence["action_identity_sha256"]), evidence.get("claim")
    )
    protocol_completed_at = _rfc3339(
        evidence.get("protocol_completed_at"), label="protocol_completed_at"
    )
    claimed_at = _rfc3339(evidence.get("recorded_at"), label="claim recorded_at")
    if protocol_completed_at < claimed_at:
        raise N2PFixedActionError("protocol completion predates the consumed claim")
    action_key = evidence.get("action_key")
    if action_key not in FIXED_ACTION_SHA256S:
        raise N2PFixedActionError("protocol evidence action is not frozen")
    snapshot = _load_action_snapshot(str(action_key))
    if evidence.get("action_identity_sha256") != snapshot.action["action_identity_sha256"]:
        raise N2PFixedActionError("protocol evidence action binding changed")
    observation, observation_payload = _strict_json_file(
        observation_file, label="operator N2P observation"
    )
    (
        visual_pass,
        electrical_pass,
        thermal_pass,
        post_temp,
        camera_payload,
        camera_binding,
    ) = _validate_observation(
        observation,
        snapshot,
        profile,
        camera_base_directory=observation_file.parent,
        minimum_observed_at=protocol_completed_at,
    )
    state = (
        ResultState.PASS
        if visual_pass and electrical_pass and thermal_pass
        else ResultState.FAIL
    )
    stored_observation = {
        **dict(observation),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "overall_state": state.value,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": CAMERA_OBSERVATION_CONTRACT_SHA256,
        "source_observation_file_sha256": _sha256(observation_payload),
        "verified_camera_evidence": dict(camera_binding) if camera_binding else None,
    }
    stored_observation_payload = _canonical_json(stored_observation)
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "state": state.value,
        "protocol_evidence_file_sha256": _sha256(evidence_payload),
        "observation_file_sha256": _sha256(stored_observation_payload),
        "profile_file_sha256": _sha256(profile_payload),
        "post_refresh_temperature_c": post_temp,
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "visual_and_electrical_assessed_separately": True,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": CAMERA_OBSERVATION_CONTRACT_SHA256,
        "camera_capture_file_sha256": (
            camera_binding["sha256"] if camera_binding else None
        ),
        "camera_capture_present_for_this_action": camera_binding is not None,
        "cross_candidate_camera_comparability": (
            "not_established_by_single_action; requires verified fixed-camera "
            "captures for all four N2P targets"
        ),
    }
    finalization_payload = _canonical_json(finalization)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=state,
        completed_at=str(observation["observed_at"]),
        evidence_manifest_sha256=_sha256(finalization_payload),
        post_request_count=1,
        details=(
            "visual/electrical/thermal PASS recorded independently"
            if state is ResultState.PASS
            else "one or more visual/electrical/thermal acceptance gates failed"
        ),
    )
    if camera_payload is not None:
        _atomic_commit(
            result_dir / CAMERA_CAPTURE_FILENAME,
            camera_payload,
            unknown_after_commit=False,
        )
    _atomic_commit(
        result_dir / OBSERVATION_FILENAME,
        stored_observation_payload,
        unknown_after_commit=False,
    )
    _atomic_commit(
        result_dir / FINALIZATION_FILENAME,
        finalization_payload,
        unknown_after_commit=False,
    )
    _write_new(result_dir, P0_RESULT_FILENAME, result)
    return {
        "state": state.value,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "result_file_sha256": result_file_sha256(result),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
    }


def _float_argument(value: str) -> float:
    try:
        return _temperature(float(value), label="temperature")
    except (ValueError, N2PFixedActionError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--action", choices=FIXED_ACTION_KEYS)
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize-observation", action="store_true")
    parser.add_argument("--limit-profile", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--primer-result", type=Path)
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--observation-file", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--confirm")
    parser.add_argument("--start-temperature-c", type=_float_argument)
    parser.add_argument("--confirm-reviewed-panel-and-build", action="store_true")
    parser.add_argument(
        "--confirm-supervised-supply-cv-current-normal", action="store_true"
    )
    parser.add_argument("--confirm-physical-cutoff-available", action="store_true")
    parser.add_argument("--confirm-single-visible-refresh", action="store_true")
    parser.add_argument("--confirm-controller-fresh-boot", action="store_true")
    parser.add_argument("--confirm-map-fidelity-from-primer", action="store_true")
    parser.add_argument(
        "--confirm-esp32-not-restarted-since-primer", action="store_true"
    )
    args = parser.parse_args(argv)
    if args.finalize_observation:
        if args.result_dir is None or args.observation_file is None:
            parser.error("finalization requires --result-dir and --observation-file")
        if args.action is not None:
            parser.error("finalization derives the frozen action from evidence")
        return args
    if args.action is None:
        parser.error("--action is required")
    if args.describe_only:
        return args
    required = {
        "--limit-profile": args.limit_profile,
        "--evaluated-at": args.evaluated_at,
        "--result-dir": args.result_dir,
        "--url": args.url,
        "--confirm": args.confirm,
        "--start-temperature-c": args.start_temperature_c,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("live execution requires " + ", ".join(missing))
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.finalize_observation:
            result = finalize_n2p_observation(args.result_dir, args.observation_file)
        elif args.describe_only:
            result = describe_n2p_fixed_action(
                args.action,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                primer_result_file=args.primer_result,
            )
        else:
            result = run_n2p_fixed_action_once(
                args.action,
                args.result_dir,
                args.url,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                authorization_confirmation=args.confirm,
                start_temperature_c=args.start_temperature_c,
                primer_result_file=args.primer_result,
                confirm_reviewed_panel_and_build=args.confirm_reviewed_panel_and_build,
                confirm_supervised_supply_cv_current_normal=(
                    args.confirm_supervised_supply_cv_current_normal
                ),
                confirm_physical_cutoff_available=args.confirm_physical_cutoff_available,
                confirm_single_visible_refresh=args.confirm_single_visible_refresh,
                confirm_controller_fresh_boot=args.confirm_controller_fresh_boot,
                confirm_map_fidelity_from_primer=args.confirm_map_fidelity_from_primer,
                confirm_esp32_not_restarted_since_primer=(
                    args.confirm_esp32_not_restarted_since_primer
                ),
            )
    except N2PFixedActionUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N2PFixedActionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
