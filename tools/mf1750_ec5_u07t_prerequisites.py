#!/usr/bin/env python3
"""Deep replay and freeze the exact historical prerequisites for U07T."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import stat
from typing import Any

from tools import mf1750_ec5_u04_u05_compare_release as historical
from tools import mf1750_ec5_u07t_identity as identity


class U07TPrerequisiteError(ValueError):
    """One U07T prerequisite or formal-claim absence check failed closed."""


def _sha_file(path: Path, *, label: str) -> str:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise U07TPrerequisiteError(f"{label} must be a regular file")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise U07TPrerequisiteError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise U07TPrerequisiteError(f"{label} changed while read")
    return hashlib.sha256(payload).hexdigest()


def formal_u07_claim_absence(formal_claim_registry: Path) -> dict[str, Any]:
    registry = Path(formal_claim_registry)
    try:
        metadata = registry.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise U07TPrerequisiteError(
                "formal claim registry must be a non-symlink directory"
            )
        resolved = registry.resolve(strict=True)
    except OSError as error:
        raise U07TPrerequisiteError(
            f"could not inspect formal claim registry: {error}"
        ) from error
    claim = resolved / f"{identity.FORMAL_U07_ACTION_ID}.json"
    try:
        claim.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise U07TPrerequisiteError(
            f"could not inspect formal U07 claim: {error}"
        ) from error
    else:
        raise U07TPrerequisiteError("formal U07 action is already claimed")
    return {
        "registry_id": identity.FORMAL_CLAIM_REGISTRY_ID,
        "registry": str(resolved),
        "action_id": identity.FORMAL_U07_ACTION_ID,
        "claim_file": str(claim),
        "exists": False,
        "formal_action_consumed": False,
    }


def distinct_claim_registries(
    formal_claim_registry: Path, technical_claim_registry: Path
) -> tuple[Path, Path]:
    formal = Path(formal_claim_registry).resolve(strict=True)
    technical_path = Path(technical_claim_registry)
    try:
        technical_parent = technical_path.parent.resolve(strict=True)
    except OSError as error:
        raise U07TPrerequisiteError(
            f"technical claim registry parent is unavailable: {error}"
        ) from error
    technical = technical_parent / technical_path.name
    try:
        if technical.exists():
            metadata = technical.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise U07TPrerequisiteError(
                    "technical claim registry must be a non-symlink directory"
                )
            if technical.resolve(strict=True) == formal:
                raise U07TPrerequisiteError(
                    "technical and formal claim registries must differ"
                )
    except OSError as error:
        raise U07TPrerequisiteError(
            f"could not resolve technical claim registry: {error}"
        ) from error
    if technical == formal:
        raise U07TPrerequisiteError(
            "technical and formal claim registries must differ"
        )
    return formal, technical


def load_all(
    *,
    corrected_release_file: Path,
    u04_result_file: Path,
    short_hold_file: Path,
    white_result_file: Path,
    white_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    candidate_claim_registry: Path,
    white_claim_registry: Path,
    formal_claim_registry: Path,
) -> dict[str, Any]:
    """Replay authoritative validators, then enforce tonight's exact hashes."""

    try:
        formal_resolved = Path(formal_claim_registry).resolve(strict=True)
        candidate_resolved = Path(candidate_claim_registry).resolve(strict=True)
    except OSError as error:
        raise U07TPrerequisiteError(
            f"could not resolve the authoritative formal registry: {error}"
        ) from error
    if formal_resolved != candidate_resolved:
        raise U07TPrerequisiteError(
            "formal U07 absence must use the same registry that contains U04 claim"
        )
    try:
        replay = historical.load_prerequisites(
            corrected_release_file=Path(corrected_release_file),
            u04_result_file=Path(u04_result_file),
            short_hold_file=Path(short_hold_file),
            white_result_file=Path(white_result_file),
            white_observation_file=Path(white_observation_file),
            panel_file=Path(panel_file),
            rc2g_binary_file=Path(rc2g_binary_file),
            candidate_claim_registry=Path(candidate_claim_registry),
            white_claim_registry=Path(white_claim_registry),
        )
    except historical.CompareReleaseError as error:
        raise U07TPrerequisiteError(
            f"authoritative historical replay failed: {error}"
        ) from error

    exact_files = {
        "corrected_u04_result": (
            Path(u04_result_file),
            identity.CORRECTED_U04_RESULT_FILE_SHA256,
        ),
        "corrected_u04_claim": (
            Path(candidate_claim_registry)
            / f"{identity.CORRECTED_U04_ACTION_ID}.json",
            identity.CORRECTED_U04_CLAIM_FILE_SHA256,
        ),
        "u04_short_hold": (
            Path(short_hold_file),
            identity.U04_SHORT_HOLD_FILE_SHA256,
        ),
        "after_u04_white_result": (
            Path(white_result_file),
            identity.AFTER_U04_WHITE_RESULT_FILE_SHA256,
        ),
        "after_u04_white_claim": (
            Path(white_claim_registry)
            / f"{identity.AFTER_U04_WHITE_ACTION_ID}.json",
            identity.AFTER_U04_WHITE_CLAIM_FILE_SHA256,
        ),
        "after_u04_white_observation": (
            Path(white_observation_file),
            identity.AFTER_U04_WHITE_OBSERVATION_FILE_SHA256,
        ),
    }
    exact = {}
    for label, (path, expected) in exact_files.items():
        observed = _sha_file(path, label=label)
        if observed != expected:
            raise U07TPrerequisiteError(f"{label} hash differs")
        exact[label] = {
            "file": str(path.resolve(strict=True)),
            "file_sha256": observed,
        }
    if (
        replay["corrected_u04"]["action_id"] != identity.CORRECTED_U04_ACTION_ID
        or replay["corrected_u04"]["outcome"] != "complete_pass"
        or replay["corrected_u04"]["release_canonical_sha256"]
        != identity.CORRECTED_U04_RELEASE_CANONICAL_SHA256
        or replay["operator_short_hold_skip_boundary"][
            "five_minute_short_hold_passed"
        ]
        is not True
        or replay["operator_short_hold_skip_boundary"]["thirty_minute_observation"]
        != "SKIPPED_BY_OPERATOR"
        or replay["operator_short_hold_skip_boundary"]["formal_u07_gate_satisfied"]
        is not False
        or replay["after_u04_white_recovery"]["action_id"]
        != identity.AFTER_U04_WHITE_ACTION_ID
        or replay["after_u04_white_recovery"]["outcome"] != "complete_pass"
        or replay["after_u04_white_manual_observation"][
            "visual_and_electrical_pass"
        ]
        is not True
    ):
        raise U07TPrerequisiteError("historical prerequisite boundary differs")
    absence = formal_u07_claim_absence(formal_claim_registry)
    return {
        "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
        "authoritative_replay": deepcopy(replay),
        "exact_evidence": exact,
        "formal_u07_claim_absence_at_release": absence,
        "boundary": {
            "corrected_u04_complete_pass": True,
            "u04_five_minute_short_hold_passed": True,
            "u04_thirty_minute_observation": "SKIPPED_BY_OPERATOR",
            "formal_u07_review_gate_satisfied": False,
            "after_u04_white_complete_pass": True,
            "after_u04_white_manual_visual_and_electrical_pass": True,
            "formal_u07_qualification_inferred": False,
        },
    }
