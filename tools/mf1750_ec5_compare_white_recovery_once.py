#!/usr/bin/env python3
"""One exact RC2G solid-white recovery after the U04-vs-U05 comparison.

The action is deliberately separate from all existing EC5 white actions.  The
tool never uploads firmware.  ``prepare-j2-off`` seals the exact RC2G binary
and offline prerequisite gate while J2 is physically off.  ``preflight`` is
four GETs and zero POSTs after the operator has flashed RC2G and powered J2.
``run`` repeats that fresh GET-only check, durably creates the independent
claim, then permits one solid-white POST with no retry or automatic recovery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import stat
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_compare_white_identity as identity  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_identity as compare_identity  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_physical_once as compare_runner  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_preview as compare_preview  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_release as compare_release  # noqa: E402
from tools import mf1750_ec5_white_recovery_once as white  # noqa: E402
from tools import mf1750_frame_tool as frame_tool  # noqa: E402


FLASH_GATE_KIND = "mf1750-ec5-compare-white-j2-off-flash-gate"
PREFLIGHT_KIND = "mf1750-ec5-compare-white-j2-on-preflight"
CLAIM_KIND = "mf1750-ec5-compare-white-permanent-claim"
RESULT_KIND = "mf1750-ec5-compare-white-physical-once-result"
WHITE_OBSERVATION_KIND = "mf1750-ec5-compare-white-manual-observation"
U07T_BINDING_KIND = "mf1750-ec5-u07t-latest-white-predecessor-binding"
COMPARE_OBSERVATION_KIND = "mf1750-ec5-u04-u05-blind-manual-observation"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_u04_u05_compare_white_claims"
)
FORMAL_WHITE_CLAIM_REGISTRY = white.DEFAULT_CLAIM_REGISTRY
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
MAX_JSON_BYTES = 16 * 1024 * 1024


class CompareWhiteError(RuntimeError):
    """One identity, evidence, protocol, or one-shot gate failed closed."""


@dataclass(frozen=True)
class CompareBindingContext:
    release: compare_runner.ReleaseContext
    binding: Mapping[str, Any]


def canonical_json_bytes(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise CompareWhiteError(f"{label} must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompareWhiteError(f"{label} is not RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CompareWhiteError(f"{label} lacks an offset")
    return parsed


def _read(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise CompareWhiteError(f"{label} must be a regular non-symlink file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise CompareWhiteError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise CompareWhiteError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise CompareWhiteError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise CompareWhiteError(f"{label} read length differs")
    return payload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompareWhiteError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CompareWhiteError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompareWhiteError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise CompareWhiteError(f"{label} root must be an object")
    return value


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise CompareWhiteError(f"{label} fields differ from contract")
    return value


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["integrity"] = {
        "canonical_sha256": _sha(canonical_json_bytes(unsigned))
    }
    return result


def _validate_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _keys(
        root.get("integrity"), {"canonical_sha256"}, label=f"{label}.integrity"
    )
    digest = integrity["canonical_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise CompareWhiteError(f"{label} integrity is malformed")
    unsigned = dict(root)
    unsigned.pop("integrity")
    if _sha(canonical_json_bytes(unsigned)) != digest:
        raise CompareWhiteError(f"{label} integrity differs")
    return digest


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    path = Path(path)
    payload = canonical_json_bytes(value)
    try:
        parent = path.parent.resolve(strict=True)
        if parent.is_symlink() or not parent.is_dir():
            raise CompareWhiteError("output parent is unsafe")
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise CompareWhiteError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise CompareWhiteError(f"could not create {path}: {error}") from error
    return payload


def _regular_entry_exists(path: Path, *, label: str) -> bool:
    """Use lstat so a dangling symlink can never masquerade as absence."""

    try:
        metadata = Path(path).lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise CompareWhiteError(f"could not inspect {label}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CompareWhiteError(f"{label} must be a regular non-symlink file")
    return True


def required_authorization() -> str:
    return (
        "AUTHORIZE_ONE_VISIBLE_RC2G_EC5_SOLID_WHITE_AFTER_U04_U05_COMPARE__"
        f"ACTION_{identity.FROZEN_ACTION_ID.upper()}{AUTHORIZATION_SUFFIX}"
    )


def _panel(path: Path) -> dict[str, str]:
    try:
        return white._panel(Path(path))  # noqa: SLF001
    except white.WhiteRecoveryError as error:
        raise CompareWhiteError(str(error)) from error


def _rc2g(path: Path) -> dict[str, Any]:
    try:
        result = white._rc2g_binary(Path(path))  # noqa: SLF001
    except white.WhiteRecoveryError as error:
        raise CompareWhiteError(str(error)) from error
    if (
        result["bytes"] != identity.RC2G_BINARY_BYTES
        or result["sha256"] != identity.RC2G_BINARY_SHA256
        or white.RC2G_BUILD_TAG != identity.RC2G_BUILD_TAG
        or white.WHITE_FRAME_SHA256 != identity.WHITE_FRAME_SHA256
        or white.WHITE_FRAME_FNV1A != identity.WHITE_FRAME_FNV1A
        or white.WHITE_DTM_FNV1A != identity.WHITE_DTM_FNV1A
    ):
        raise CompareWhiteError("authoritative RC2G/white identity differs")
    return result


def _historical_release_context(
    release_file: Path, panel_file: Path
) -> compare_runner.ReleaseContext:
    """Replay the sealed V2 compare release without live-source equality."""

    release_file = Path(release_file)
    payload = _read(release_file, label="compare V2 release")
    if _sha(payload) != identity.COMPARE_RELEASE_FILE_SHA256:
        raise CompareWhiteError("compare release file hash differs")
    root = _decode(payload, label="compare V2 release")
    expected_root_keys = {
        "schema_version",
        "kind",
        "created_at",
        "panel",
        "source_snapshot",
        "device_contract",
        "variant",
        "compiled_identity_report",
        "preview",
        "prerequisites",
        "safety",
        "integrity",
    }
    if (
        set(root) != expected_root_keys
        or root["schema_version"] != compare_release.SCHEMA_VERSION
        or root["kind"] != compare_release.KIND
    ):
        raise CompareWhiteError("compare release schema/kind differs")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": compare_release.sha256(unsigned),
        "scope": compare_release.HASH_SCOPE,
    }:
        raise CompareWhiteError("compare release integrity differs")
    if integrity["canonical_sha256"] != identity.COMPARE_RELEASE_CANONICAL_SHA256:
        raise CompareWhiteError("compare release canonical identity differs")
    panel = _panel(panel_file)
    if root["panel"] != panel:
        raise CompareWhiteError("compare release panel differs")
    if root["device_contract"] != compare_release.DEVICE_CONTRACT:
        raise CompareWhiteError("compare release device contract differs")
    if root["safety"] != compare_release.SAFETY:
        raise CompareWhiteError("compare release safety contract differs")
    snapshot = root["source_snapshot"]
    if not isinstance(snapshot, list) or [
        item.get("path") if isinstance(item, Mapping) else None for item in snapshot
    ] != list(compare_release.SOURCE_PATHS):
        raise CompareWhiteError("historical compare source snapshot is malformed")
    for item in snapshot:
        _keys(item, {"path", "bytes", "sha256"}, label="source snapshot entry")
        if not isinstance(item["bytes"], int) or item["bytes"] <= 0:
            raise CompareWhiteError("source snapshot byte count is invalid")

    expected_variant = compare_identity.variant()
    variant = root["variant"]
    if not isinstance(variant, Mapping):
        raise CompareWhiteError("compare release variant is malformed")
    for key, wanted in expected_variant.items():
        if key not in ("firmware_file", "elf_file") and variant.get(key) != wanted:
            raise CompareWhiteError(f"compare release variant {key} differs")
    if variant["action_id"] != identity.COMPARE_ACTION_ID:
        raise CompareWhiteError("compare action identity differs")
    binary_path = release_file.parent / variant["firmware"]["file"]
    elf_path = release_file.parent / variant["elf"]["file"]
    binary = _read(binary_path, label="compare firmware", maximum=32 << 20)
    elf = _read(elf_path, label="compare ELF", maximum=64 << 20)
    for name, data in (("firmware", binary), ("elf", elf)):
        entry = variant[name]
        if len(data) != entry["bytes"] or _sha(data) != entry["sha256"]:
            raise CompareWhiteError(f"compare {name} artifact differs")
    try:
        compare_release._validate_firmware(binary)  # noqa: SLF001
        compiled = compare_release.compiled_identity_report(elf_path)
        preview_report = compare_preview.validate(
            release_file.parent / compare_preview.MANIFEST_FILE
        )
    except (
        compare_release.CompareReleaseError,
        compare_preview.U04U05ComparePreviewError,
    ) as error:
        raise CompareWhiteError(f"compare artifact replay failed: {error}") from error
    if compiled != root["compiled_identity_report"]:
        raise CompareWhiteError("compare compiled identity report differs")
    if preview_report != root["preview"]["validated"]:
        raise CompareWhiteError("compare preview validation differs")

    prereqs = root["prerequisites"]
    corrected = prereqs["corrected_u04"]
    short_hold = prereqs["operator_short_hold_skip_boundary"]
    prior_white = prereqs["after_u04_white_recovery"]
    prior_white_observation = prereqs["after_u04_white_manual_observation"]
    prerequisite_files = compare_runner.PrerequisiteFiles(
        corrected_u04_release=Path(corrected["release_file"]),
        u04_result=Path(corrected["result_file"]),
        u04_short_hold=Path(short_hold["file"]),
        white_result=Path(prior_white["file"]),
        white_observation=Path(prior_white_observation["file"]),
        rc2g_binary=Path(prior_white["rc2g_binary"]["file"]),
        candidate_claim_registry=Path(corrected["claim_file"]).parent,
        white_claim_registry=white.DEFAULT_CLAIM_REGISTRY,
    )
    try:
        replayed_prereqs = compare_release.load_prerequisites(
            corrected_release_file=prerequisite_files.corrected_u04_release,
            u04_result_file=prerequisite_files.u04_result,
            short_hold_file=prerequisite_files.u04_short_hold,
            white_result_file=prerequisite_files.white_result,
            white_observation_file=prerequisite_files.white_observation,
            panel_file=panel_file,
            rc2g_binary_file=prerequisite_files.rc2g_binary,
            candidate_claim_registry=prerequisite_files.candidate_claim_registry,
            white_claim_registry=prerequisite_files.white_claim_registry,
        )
    except compare_release.CompareReleaseError as error:
        raise CompareWhiteError(f"compare prerequisite replay failed: {error}") from error
    if replayed_prereqs != prereqs:
        raise CompareWhiteError("compare prerequisite evidence differs")
    return compare_runner.ReleaseContext(
        path=release_file.resolve(),
        root=root,
        variant=variant,
        release_canonical_sha256=integrity["canonical_sha256"],
        binary_path=binary_path.resolve(),
        binary_sha256=variant["firmware"]["sha256"],
        elf_path=elf_path.resolve(),
        elf_sha256=variant["elf"]["sha256"],
        panel=panel,
        prerequisites=prereqs,
        prerequisite_files=prerequisite_files,
    )


def _validate_compare_observation(
    observation_file: Path, *, compare_result_file: Path
) -> dict[str, Any]:
    payload = _read(observation_file, label="compare blind observation")
    if _sha(payload) != identity.COMPARE_OBSERVATION_FILE_SHA256:
        raise CompareWhiteError("compare observation file hash differs")
    root = _decode(payload, label="compare blind observation")
    expected_keys = {
        "schema_version",
        "kind",
        "action_id",
        "result_file",
        "result_file_sha256",
        "result_integrity_sha256",
        "observed_at",
        "observation_method",
        "operator_reports_verbatim",
        "blind_visual_observation",
        "post_blind_layout_decode",
        "supervised_safety_observation",
        "conclusion",
        "retry_authorized",
        "recovery_implicitly_authorized",
    }
    _keys(root, expected_keys, label="compare blind observation")
    result_payload = _read(compare_result_file, label="compare result for observation")
    result = _decode(result_payload, label="compare result for observation")
    if (
        root["schema_version"] != 1
        or root["kind"] != COMPARE_OBSERVATION_KIND
        or root["action_id"] != identity.COMPARE_ACTION_ID
        or root["result_file"] != Path(compare_result_file).name
        or root["result_file_sha256"] != _sha(result_payload)
        or root["result_integrity_sha256"]
        != result.get("integrity", {}).get("canonical_sha256")
        or root["retry_authorized"] is not False
        or root["recovery_implicitly_authorized"] is not False
    ):
        raise CompareWhiteError("compare observation identity differs")
    observed_at = _timestamp(root["observed_at"], label="compare observation time")
    result_finished_at = _timestamp(
        result.get("finished_at"), label="compare result finish"
    )
    if observed_at < result_finished_at:
        raise CompareWhiteError("compare observation predates compare result finish")
    method = _keys(
        root["observation_method"],
        {
            "operator_blinded_to_code_positions_before_directional_report",
            "pseudocolor_preview_withheld_before_directional_report",
            "layout",
            "spatial_dithering_present",
        },
        label="compare observation method",
    )
    visual = _keys(
        root["blind_visual_observation"],
        {
            "all_four_patches_perceived_blue",
            "left_top_darker_than_left_bottom",
            "right_bottom_darker_than_right_top",
            "difference_strength_scale_0_to_4",
            "difference_strength_label",
            "saturation_difference",
            "patches_uniform",
            "edges_clear",
            "white_background_clean",
        },
        label="compare blind visual observation",
    )
    decoded = _keys(
        root["post_blind_layout_decode"],
        {
            "left_top",
            "left_bottom",
            "right_top",
            "right_bottom",
            "u04_darker_than_u05_on_cs1",
            "u04_darker_than_u05_on_cs2",
            "same_direction_across_controllers",
            "controller_and_vertical_position_confound_rejected_by_crossover",
        },
        label="compare layout decode",
    )
    safety = _keys(
        root["supervised_safety_observation"],
        {"electrical_normal", "temperature_c", "esp32_did_not_restart"},
        label="compare safety observation",
    )
    conclusion = _keys(
        root["conclusion"],
        {
            "visual_directional_gate_passed",
            "u04_visually_distinguishable_from_u05_under_this_condition",
            "u04_classification",
            "u04_is_visual_alias_of_u05",
            "formal_new_color_qualification",
            "repeatability_evaluated",
            "clean_white_recovery_after_comparison_required",
        },
        label="compare conclusion",
    )
    if (
        method
        != {
            "operator_blinded_to_code_positions_before_directional_report": True,
            "pseudocolor_preview_withheld_before_directional_report": True,
            "layout": "two vertically aligned 64x64 patches on each controller half",
            "spatial_dithering_present": False,
        }
        or visual["difference_strength_scale_0_to_4"] != 2
        or visual["difference_strength_label"] != "clearly_distinguishable"
        or any(
            visual[key] is not True
            for key in (
                "all_four_patches_perceived_blue",
                "left_top_darker_than_left_bottom",
                "right_bottom_darker_than_right_top",
                "patches_uniform",
                "edges_clear",
                "white_background_clean",
            )
        )
        or decoded
        != {
            "left_top": "U04",
            "left_bottom": "U05",
            "right_top": "U05",
            "right_bottom": "U04",
            "u04_darker_than_u05_on_cs1": True,
            "u04_darker_than_u05_on_cs2": True,
            "same_direction_across_controllers": True,
            "controller_and_vertical_position_confound_rejected_by_crossover": True,
        }
        or safety
        != {
            "electrical_normal": True,
            "temperature_c": 35.0,
            "esp32_did_not_restart": True,
        }
        or conclusion["visual_directional_gate_passed"] is not True
        or conclusion["u04_visually_distinguishable_from_u05_under_this_condition"]
        is not True
        or conclusion["u04_classification"]
        != "visually_distinguishable_darker_blue_shade_candidate"
        or conclusion["u04_is_visual_alias_of_u05"] is not False
        or conclusion["formal_new_color_qualification"] is not False
        or conclusion["repeatability_evaluated"] is not False
        or conclusion["clean_white_recovery_after_comparison_required"] is not True
    ):
        raise CompareWhiteError("compare blind observation boundary differs")
    reports = root["operator_reports_verbatim"]
    if (
        not isinstance(reports, list)
        or len(reports) < 3
        or any(not isinstance(item, str) or not item.strip() for item in reports)
    ):
        raise CompareWhiteError("compare operator reports are incomplete")
    return {
        "file": str(Path(observation_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "kind": COMPARE_OBSERVATION_KIND,
        "observed_at": root["observed_at"],
        "visual_directional_gate_passed": True,
        "u04_darker_blue_than_u05_on_both_controllers": True,
        "difference_strength_scale_0_to_4": 2,
        "electrical_normal": True,
        "temperature_c": 35.0,
        "esp32_did_not_restart": True,
        "formal_new_color_qualification": False,
        "clean_white_recovery_required": True,
    }


def load_compare_binding(
    *,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
) -> CompareBindingContext:
    context = _historical_release_context(compare_release_file, panel_file)
    try:
        result = compare_runner.validate_result(
            context,
            Path(compare_result_file),
            claim_registry=Path(compare_claim_registry),
        )
    except compare_runner.ComparePhysicalError as error:
        raise CompareWhiteError(f"compare result replay failed: {error}") from error
    result_payload = _read(compare_result_file, label="compare physical result")
    if (
        _sha(result_payload) != identity.COMPARE_RESULT_FILE_SHA256
        or result["outcome"] != "complete_pass"
        or result["integrity"]["canonical_sha256"]
        != identity.COMPARE_RESULT_INTEGRITY_SHA256
    ):
        raise CompareWhiteError("compare result identity/outcome differs")
    claim_path = (
        Path(compare_claim_registry) / f"{identity.COMPARE_ACTION_ID}.json"
    )
    claim_payload = _read(claim_path, label="compare permanent claim")
    if _sha(claim_payload) != identity.COMPARE_CLAIM_FILE_SHA256:
        raise CompareWhiteError("compare permanent claim hash differs")
    observation = _validate_compare_observation(
        compare_observation_file, compare_result_file=compare_result_file
    )
    binding = {
        "compare_action_id": identity.COMPARE_ACTION_ID,
        "release": {
            "file": str(Path(compare_release_file).resolve()),
            "file_sha256": identity.COMPARE_RELEASE_FILE_SHA256,
            "canonical_sha256": identity.COMPARE_RELEASE_CANONICAL_SHA256,
            "firmware_sha256": context.binary_sha256,
            "elf_sha256": context.elf_sha256,
        },
        "result": {
            "file": str(Path(compare_result_file).resolve()),
            "bytes": len(result_payload),
            "file_sha256": _sha(result_payload),
            "integrity_sha256": result["integrity"]["canonical_sha256"],
            "attempt_id": result["attempt_id"],
            "outcome": "complete_pass",
        },
        "claim": {
            "file": str(claim_path.resolve()),
            "bytes": len(claim_payload),
            "file_sha256": _sha(claim_payload),
            "attempt_id": result["attempt_id"],
        },
        "manual_observation": observation,
        "panel": dict(context.panel),
        "ready_for_separately_authorized_white_recovery": True,
    }
    return CompareBindingContext(release=context, binding=binding)


def _resolved_registry(path: Path, *, create: bool) -> Path:
    path = Path(path)
    try:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise CompareWhiteError("claim registry must be a non-symlink directory")
            return path.resolve(strict=True)
        parent = path.parent.resolve(strict=True)
        if create:
            path.mkdir(mode=0o700, exist_ok=False)
            return path.resolve(strict=True)
        return parent / path.name
    except OSError as error:
        raise CompareWhiteError(f"could not resolve claim registry: {error}") from error


def _registry_isolation(
    claim_registry: Path, formal_white_claim_registry: Path, *, create: bool
) -> tuple[Path, Path]:
    independent = _resolved_registry(claim_registry, create=create)
    formal = _resolved_registry(formal_white_claim_registry, create=False)
    if os.path.normcase(str(independent)) == os.path.normcase(str(formal)):
        raise CompareWhiteError("independent and formal white registries must differ")
    if identity.FROZEN_ACTION_ID in identity.FORMAL_WHITE_ACTION_IDS.values():
        raise CompareWhiteError("compare-white action collides with a formal action")
    return independent, formal


def _formal_snapshot(registry: Path) -> dict[str, Any]:
    resolved = _resolved_registry(registry, create=False)
    actions: dict[str, Any] = {}
    for name, action_id in identity.FORMAL_WHITE_ACTION_IDS.items():
        path = resolved / f"{action_id}.json"
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            actions[name] = {
                "action_id": action_id,
                "claim_file": str(path),
                "exists": False,
                "file_sha256": None,
            }
            continue
        except OSError as error:
            raise CompareWhiteError(f"could not inspect formal claim: {error}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CompareWhiteError("formal white claim is not a regular file")
        payload = _read(path, label=f"formal {name} white claim")
        actions[name] = {
            "action_id": action_id,
            "claim_file": str(path),
            "exists": True,
            "file_sha256": _sha(payload),
        }
    return {
        "registry": str(resolved),
        "actions": actions,
        "compare_white_action_present": (
            _regular_entry_exists(
                resolved / f"{identity.FROZEN_ACTION_ID}.json",
                label="formal compare-white claim entry",
            )
        ),
    }


def _claim_path(registry: Path) -> Path:
    return Path(registry) / f"{identity.FROZEN_ACTION_ID}.json"


def _file_reference(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read(path, label=label)
    root = _decode(payload, label=label)
    digest = _validate_integrity(root, label=label)
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "integrity_sha256": digest,
    }


def create_j2_off_flash_gate(
    *,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
    evidence_file: Path,
    confirm_j2_off: bool,
) -> dict[str, Any]:
    if not confirm_j2_off:
        raise CompareWhiteError("J2-off flash gate requires explicit confirmation")
    binding = load_compare_binding(
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
    ).binding
    panel = _panel(panel_file)
    binary = _rc2g(rc2g_binary_file)
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    if _regular_entry_exists(
        _claim_path(independent), label="independent compare-white claim"
    ):
        raise CompareWhiteError("compare-white action is already claimed")
    formal_snapshot = _formal_snapshot(formal)
    if formal_snapshot["compare_white_action_present"] is not False:
        raise CompareWhiteError("formal registry contains compare-white action")
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": FLASH_GATE_KIND,
            "created_at": _now(),
            "action_id": identity.FROZEN_ACTION_ID,
            "identity_revision": identity.IDENTITY_REVISION,
            "panel": panel,
            "compare_binding": deepcopy(binding),
            "rc2g_binary": binary,
            "independent_claim_registry": str(independent),
            "formal_white_claim_snapshot": formal_snapshot,
            "j2_driver_power_confirmed_off": True,
            "firmware_upload_scope": "exact_archived_rc2g_binary_only",
            "network_requests": 0,
            "device_io_performed_by_this_tool": False,
            "claim_created": False,
            "visible_refresh_authorized": False,
            "state": "j2_off_exact_rc2g_flash_gate_pass",
        }
    )
    _write_new(evidence_file, evidence)
    return evidence


def validate_j2_off_flash_gate(
    *,
    evidence_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
    require_unclaimed: bool = True,
) -> dict[str, Any]:
    payload = _read(evidence_file, label="J2-off flash gate")
    root = _decode(payload, label="J2-off flash gate")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "created_at",
            "action_id",
            "identity_revision",
            "panel",
            "compare_binding",
            "rc2g_binary",
            "independent_claim_registry",
            "formal_white_claim_snapshot",
            "j2_driver_power_confirmed_off",
            "firmware_upload_scope",
            "network_requests",
            "device_io_performed_by_this_tool",
            "claim_created",
            "visible_refresh_authorized",
            "state",
            "integrity",
        },
        label="J2-off flash gate",
    )
    _validate_integrity(root, label="J2-off flash gate")
    created_at = _timestamp(root["created_at"], label="flash gate time")
    binding = load_compare_binding(
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
    ).binding
    compare_observed_at = _timestamp(
        binding["manual_observation"]["observed_at"],
        label="compare observation binding time",
    )
    if created_at < compare_observed_at:
        raise CompareWhiteError("J2-off flash gate predates compare observation")
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    expected = {
        "schema_version": 1,
        "kind": FLASH_GATE_KIND,
        "action_id": identity.FROZEN_ACTION_ID,
        "identity_revision": identity.IDENTITY_REVISION,
        "panel": _panel(panel_file),
        "compare_binding": binding,
        "rc2g_binary": _rc2g(rc2g_binary_file),
        "independent_claim_registry": str(independent),
        "formal_white_claim_snapshot": _formal_snapshot(formal),
        "j2_driver_power_confirmed_off": True,
        "firmware_upload_scope": "exact_archived_rc2g_binary_only",
        "network_requests": 0,
        "device_io_performed_by_this_tool": False,
        "claim_created": False,
        "visible_refresh_authorized": False,
        "state": "j2_off_exact_rc2g_flash_gate_pass",
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise CompareWhiteError(f"J2-off flash gate {key} differs")
    if require_unclaimed and _regular_entry_exists(
        _claim_path(independent), label="independent compare-white claim"
    ):
        raise CompareWhiteError("compare-white action is already claimed")
    return dict(root)


def _replay_fresh_transcript(records: Any) -> dict[str, Any]:
    if not isinstance(records, list) or len(records) != 4:
        raise CompareWhiteError("preflight transcript must contain exactly four GETs")
    index = 0

    def delegate(
        _base_url: str,
        path: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        nonlocal index
        if index >= len(records):
            raise CompareWhiteError("stored preflight transcript is exhausted")
        record = records[index]
        index += 1
        if (
            not isinstance(record, Mapping)
            or record.get("method") != method
            or record.get("path") != path
            or record.get("request_bytes") != 0
            or record.get("request_sha256") is not None
            or data is not None
            or not isinstance(record.get("status"), int)
            or not isinstance(record.get("response_body"), str)
            or timeout <= 0
        ):
            raise CompareWhiteError("stored preflight record differs")
        return record["status"], record["response_body"]

    audited = white._AuditRequester(delegate)  # noqa: SLF001
    try:
        fresh = white._fresh_preflight("http://127.0.0.1", audited)  # noqa: SLF001
    except white.WhiteRecoveryError as error:
        raise CompareWhiteError(f"stored preflight replay failed: {error}") from error
    if index != 4 or audited.records != records or audited.post_count != 0:
        raise CompareWhiteError("stored preflight transcript replay differs")
    return fresh


def create_j2_on_preflight(
    *,
    base_url: str,
    flash_gate_file: Path,
    evidence_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
    confirm_j2_on: bool,
    confirm_electrical_normal: bool,
    requester: frame_tool.HttpRequester = frame_tool.http_request,
) -> dict[str, Any]:
    if not confirm_j2_on or not confirm_electrical_normal:
        raise CompareWhiteError("J2-on preflight requires electrical confirmation")
    flash_gate = validate_j2_off_flash_gate(
        evidence_file=flash_gate_file,
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        claim_registry=claim_registry,
        formal_white_claim_registry=formal_white_claim_registry,
    )
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    if _regular_entry_exists(
        _claim_path(independent), label="independent compare-white claim"
    ):
        raise CompareWhiteError("compare-white action is already claimed")
    audited = white._AuditRequester(requester)  # noqa: SLF001
    try:
        fresh = white._fresh_preflight(base_url, audited)  # noqa: SLF001
    except white.WhiteRecoveryError as error:
        raise CompareWhiteError(f"RC2G GET-only preflight failed: {error}") from error
    if len(audited.records) != 4 or audited.post_count != 0:
        raise CompareWhiteError("RC2G preflight was not exactly four GETs")
    gate_ref = _file_reference(flash_gate_file, label="J2-off flash gate")
    evidence = _seal(
        {
            "schema_version": 1,
            "kind": PREFLIGHT_KIND,
            "created_at": _now(),
            "action_id": identity.FROZEN_ACTION_ID,
            "panel": _panel(panel_file),
            "rc2g_binary": _rc2g(rc2g_binary_file),
            "flash_gate": gate_ref,
            "compare_binding_sha256": _sha(
                canonical_json_bytes(flash_gate["compare_binding"])
            ),
            "formal_white_claim_snapshot": _formal_snapshot(formal),
            "independent_claim_registry": str(independent),
            "j2_driver_power_confirmed_on": True,
            "operator_electrical_normal": True,
            "fresh": fresh,
            "transcript": audited.records,
            "get_requests": 4,
            "post_requests": 0,
            "claim_created": False,
            "visible_refresh_authorized": False,
            "state": "j2_on_get_only_preflight_pass_no_mutation",
        }
    )
    _write_new(evidence_file, evidence)
    return evidence


def validate_j2_on_preflight(
    *,
    evidence_file: Path,
    flash_gate_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
    require_unclaimed: bool = True,
) -> dict[str, Any]:
    flash_gate = validate_j2_off_flash_gate(
        evidence_file=flash_gate_file,
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        claim_registry=claim_registry,
        formal_white_claim_registry=formal_white_claim_registry,
        require_unclaimed=require_unclaimed,
    )
    payload = _read(evidence_file, label="J2-on preflight")
    root = _decode(payload, label="J2-on preflight")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "created_at",
            "action_id",
            "panel",
            "rc2g_binary",
            "flash_gate",
            "compare_binding_sha256",
            "formal_white_claim_snapshot",
            "independent_claim_registry",
            "j2_driver_power_confirmed_on",
            "operator_electrical_normal",
            "fresh",
            "transcript",
            "get_requests",
            "post_requests",
            "claim_created",
            "visible_refresh_authorized",
            "state",
            "integrity",
        },
        label="J2-on preflight",
    )
    _validate_integrity(root, label="J2-on preflight")
    created_at = _timestamp(root["created_at"], label="preflight time")
    if created_at < _timestamp(
        flash_gate["created_at"], label="J2-off flash gate creation"
    ):
        raise CompareWhiteError("J2-on preflight predates J2-off flash gate")
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    expected = {
        "schema_version": 1,
        "kind": PREFLIGHT_KIND,
        "action_id": identity.FROZEN_ACTION_ID,
        "panel": _panel(panel_file),
        "rc2g_binary": _rc2g(rc2g_binary_file),
        "flash_gate": _file_reference(flash_gate_file, label="J2-off flash gate"),
        "compare_binding_sha256": _sha(
            canonical_json_bytes(flash_gate["compare_binding"])
        ),
        "formal_white_claim_snapshot": _formal_snapshot(formal),
        "independent_claim_registry": str(independent),
        "j2_driver_power_confirmed_on": True,
        "operator_electrical_normal": True,
        "get_requests": 4,
        "post_requests": 0,
        "claim_created": False,
        "visible_refresh_authorized": False,
        "state": "j2_on_get_only_preflight_pass_no_mutation",
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise CompareWhiteError(f"J2-on preflight {key} differs")
    if root["fresh"] != _replay_fresh_transcript(root["transcript"]):
        raise CompareWhiteError("J2-on stored fresh payload differs")
    if require_unclaimed and _regular_entry_exists(
        _claim_path(independent), label="independent compare-white claim"
    ):
        raise CompareWhiteError("compare-white action is already claimed")
    return dict(root)


def _create_claim(
    *,
    registry: Path,
    panel: Mapping[str, str],
    rc2g_binary: Mapping[str, Any],
    compare_binding: Mapping[str, Any],
    flash_gate_file: Path,
    preflight_file: Path,
    live_fresh: Mapping[str, Any],
    formal_snapshot: Mapping[str, Any],
    attempt_id: str,
) -> tuple[dict[str, Any], bytes, Path]:
    resolved = _resolved_registry(registry, create=True)
    path = _claim_path(resolved)
    claim = _seal(
        {
            "schema_version": 1,
            "kind": CLAIM_KIND,
            "registry_id": identity.CLAIM_REGISTRY_ID,
            "stage": identity.STAGE,
            "action_id": identity.FROZEN_ACTION_ID,
            "attempt_id": attempt_id,
            "created_at": _now(),
            "panel": dict(panel),
            "rc2g_binary": deepcopy(dict(rc2g_binary)),
            "frame_sha256": identity.WHITE_FRAME_SHA256,
            "frame_fnv1a": identity.WHITE_FRAME_FNV1A,
            "compare_binding": deepcopy(dict(compare_binding)),
            "flash_gate": _file_reference(flash_gate_file, label="flash gate for claim"),
            "j2_on_preflight": _file_reference(
                preflight_file, label="J2-on preflight for claim"
            ),
            "live_fresh_preflight_sha256": _sha(canonical_json_bytes(live_fresh)),
            "formal_white_claim_snapshot_before_post": deepcopy(
                dict(formal_snapshot)
            ),
            "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
            "maximum_frame_posts": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
    )
    payload = _write_new(path, claim)
    return claim, payload, path


def run_once(
    *,
    base_url: str,
    authorization: str,
    flash_gate_file: Path,
    preflight_file: Path,
    result_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
    confirm_j2_on: bool,
    confirm_electrical_normal: bool,
    requester: frame_tool.HttpRequester = frame_tool.http_request,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    if authorization != required_authorization():
        raise CompareWhiteError("exact compare-white authorization is required")
    if not confirm_j2_on or not confirm_electrical_normal:
        raise CompareWhiteError("run requires live J2-on electrical confirmation")
    preflight = validate_j2_on_preflight(
        evidence_file=preflight_file,
        flash_gate_file=flash_gate_file,
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        claim_registry=claim_registry,
        formal_white_claim_registry=formal_white_claim_registry,
    )
    binding = load_compare_binding(
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
    ).binding
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    if _regular_entry_exists(
        _claim_path(independent), label="independent compare-white claim"
    ):
        raise CompareWhiteError("compare-white action is already claimed")
    formal_before = _formal_snapshot(formal)
    audited = white._AuditRequester(requester)  # noqa: SLF001
    try:
        live_fresh = white._fresh_preflight(base_url, audited)  # noqa: SLF001
    except white.WhiteRecoveryError as error:
        raise CompareWhiteError(f"live RC2G preflight failed: {error}") from error
    if live_fresh != preflight["fresh"] or len(audited.records) != 4:
        raise CompareWhiteError("live RC2G state differs from sealed preflight")
    attempt_id = str(uuid.uuid4())
    claim, claim_payload, claim_path = _create_claim(
        registry=independent,
        panel=_panel(panel_file),
        rc2g_binary=_rc2g(rc2g_binary_file),
        compare_binding=binding,
        flash_gate_file=flash_gate_file,
        preflight_file=preflight_file,
        live_fresh=live_fresh,
        formal_snapshot=formal_before,
        attempt_id=attempt_id,
    )
    started_at = _now()
    outcome = "unknown_do_not_retry_or_recover"
    error_text: str | None = None
    protocol: Mapping[str, Any] | None = None
    try:
        protocol = frame_tool.perform_refresh(
            base_url,
            white.WHITE_FRAME,
            expected_mappings=white.MAPPINGS,
            requester=audited,
            sleeper=sleeper,
            clock=clock,
        )
        replay = white._replay_success(audited.records)  # noqa: SLF001
        if (
            protocol["preflight"] != replay["version"]
            or protocol["job"] != replay["job"]
            or protocol["diagnostic"] != replay["diagnostic"]
        ):
            raise CompareWhiteError("live white protocol differs from transcript replay")
        outcome = "complete_pass"
    except Exception as error:  # durable claim forbids retry/recovery
        error_text = str(error)
    formal_after: Mapping[str, Any] | None
    formal_after_error: str | None = None
    try:
        formal_after = _formal_snapshot(formal)
    except CompareWhiteError as error:
        formal_after = None
        formal_after_error = str(error)
        outcome = "unknown_do_not_retry_or_recover"
        error_text = f"formal white claim registry post-action read failed: {error}"
    if formal_after is not None and formal_after != formal_before:
        outcome = "unknown_do_not_retry_or_recover"
        error_text = "formal white claim registry changed during action"
    claim_reference = {
        "filename": claim_path.name,
        "file_sha256": _sha(claim_payload),
        "integrity_sha256": claim["integrity"]["canonical_sha256"],
        "attempt_id": attempt_id,
        "state": claim["state"],
    }
    result = _seal(
        {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "stage": identity.STAGE,
            "action_id": identity.FROZEN_ACTION_ID,
            "attempt_id": attempt_id,
            "panel": _panel(panel_file),
            "rc2g_binary": _rc2g(rc2g_binary_file),
            "frame_bytes": white.WHITE_FRAME_BYTES,
            "frame_sha256": identity.WHITE_FRAME_SHA256,
            "frame_fnv1a": identity.WHITE_FRAME_FNV1A,
            "dtm_fnv1a": identity.WHITE_DTM_FNV1A,
            "compare_binding": binding,
            "flash_gate": _file_reference(flash_gate_file, label="flash gate result"),
            "j2_on_preflight": _file_reference(
                preflight_file, label="preflight result"
            ),
            "authorization_confirmation_sha256": _sha(
                authorization.encode("utf-8")
            ),
            "claim": claim_reference,
            "formal_white_claim_snapshot_before_post": formal_before,
            "formal_white_claim_snapshot_after_action": formal_after,
            "formal_white_claim_snapshot_after_action_error": formal_after_error,
            "started_at": started_at,
            "completed_at": _now(),
            "outcome": outcome,
            "error": error_text,
            "network": {
                "get_requests": sum(
                    item["method"] == "GET" for item in audited.records
                ),
                "post_requests": audited.post_count,
                "maximum_frame_posts": 1,
                "no_retry": True,
                "no_recovery": True,
            },
            "live_fresh_preflight": live_fresh,
            "transcript": audited.records,
            "protocol": deepcopy(protocol),
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
    )
    _write_new(result_file, result)
    return result


def validate_result(
    *,
    result_file: Path,
    flash_gate_file: Path,
    preflight_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    formal_white_claim_registry: Path = FORMAL_WHITE_CLAIM_REGISTRY,
) -> dict[str, Any]:
    preflight = validate_j2_on_preflight(
        evidence_file=preflight_file,
        flash_gate_file=flash_gate_file,
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        claim_registry=claim_registry,
        formal_white_claim_registry=formal_white_claim_registry,
        require_unclaimed=False,
    )
    binding = load_compare_binding(
        compare_release_file=compare_release_file,
        compare_result_file=compare_result_file,
        compare_claim_registry=compare_claim_registry,
        compare_observation_file=compare_observation_file,
        panel_file=panel_file,
    ).binding
    payload = _read(result_file, label="compare-white result")
    root = _decode(payload, label="compare-white result")
    expected_keys = {
        "schema_version",
        "kind",
        "stage",
        "action_id",
        "attempt_id",
        "panel",
        "rc2g_binary",
        "frame_bytes",
        "frame_sha256",
        "frame_fnv1a",
        "dtm_fnv1a",
        "compare_binding",
        "flash_gate",
        "j2_on_preflight",
        "authorization_confirmation_sha256",
        "claim",
        "formal_white_claim_snapshot_before_post",
        "formal_white_claim_snapshot_after_action",
        "formal_white_claim_snapshot_after_action_error",
        "started_at",
        "completed_at",
        "outcome",
        "error",
        "network",
        "live_fresh_preflight",
        "transcript",
        "protocol",
        "state",
        "integrity",
    }
    _keys(root, expected_keys, label="compare-white result")
    _validate_integrity(root, label="compare-white result")
    started = _timestamp(root["started_at"], label="result start")
    completed = _timestamp(root["completed_at"], label="result completion")
    if completed < started:
        raise CompareWhiteError("compare-white result timestamps are reversed")
    if started < _timestamp(
        preflight["created_at"], label="J2-on preflight creation"
    ):
        raise CompareWhiteError("compare-white result predates J2-on preflight")
    independent, formal = _registry_isolation(
        claim_registry, formal_white_claim_registry, create=False
    )
    exact = {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "stage": identity.STAGE,
        "action_id": identity.FROZEN_ACTION_ID,
        "panel": _panel(panel_file),
        "rc2g_binary": _rc2g(rc2g_binary_file),
        "frame_bytes": white.WHITE_FRAME_BYTES,
        "frame_sha256": identity.WHITE_FRAME_SHA256,
        "frame_fnv1a": identity.WHITE_FRAME_FNV1A,
        "dtm_fnv1a": identity.WHITE_DTM_FNV1A,
        "compare_binding": binding,
        "flash_gate": _file_reference(flash_gate_file, label="flash gate result"),
        "j2_on_preflight": _file_reference(
            preflight_file, label="preflight result"
        ),
        "authorization_confirmation_sha256": _sha(
            required_authorization().encode("utf-8")
        ),
        "formal_white_claim_snapshot_before_post": preflight[
            "formal_white_claim_snapshot"
        ],
        "state": "authorization_permanently_consumed_do_not_rerun",
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise CompareWhiteError(f"compare-white result {key} differs")
    if root["outcome"] == "complete_pass":
        if (
            root["formal_white_claim_snapshot_after_action_error"] is not None
            or root["formal_white_claim_snapshot_after_action"]
            != _formal_snapshot(formal)
            or root["formal_white_claim_snapshot_before_post"]
            != root["formal_white_claim_snapshot_after_action"]
        ):
            raise CompareWhiteError("formal white registry changed during action")
    elif not (
        root["formal_white_claim_snapshot_after_action"] is None
        and isinstance(
            root["formal_white_claim_snapshot_after_action_error"], str
        )
        and root["formal_white_claim_snapshot_after_action_error"].strip()
    ) and root["formal_white_claim_snapshot_before_post"] != root[
        "formal_white_claim_snapshot_after_action"
    ]:
        raise CompareWhiteError("unknown result formal snapshot evidence differs")
    claim_ref = _keys(
        root["claim"],
        {"filename", "file_sha256", "integrity_sha256", "attempt_id", "state"},
        label="compare-white claim reference",
    )
    claim_path = _claim_path(independent)
    claim_payload = _read(claim_path, label="compare-white permanent claim")
    claim = _decode(claim_payload, label="compare-white permanent claim")
    _validate_integrity(claim, label="compare-white permanent claim")
    if claim_ref != {
        "filename": claim_path.name,
        "file_sha256": _sha(claim_payload),
        "integrity_sha256": claim["integrity"]["canonical_sha256"],
        "attempt_id": root["attempt_id"],
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
    }:
        raise CompareWhiteError("compare-white claim reference differs")
    claim_exact = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": identity.CLAIM_REGISTRY_ID,
        "stage": identity.STAGE,
        "action_id": identity.FROZEN_ACTION_ID,
        "attempt_id": root["attempt_id"],
        "panel": _panel(panel_file),
        "rc2g_binary": _rc2g(rc2g_binary_file),
        "frame_sha256": identity.WHITE_FRAME_SHA256,
        "frame_fnv1a": identity.WHITE_FRAME_FNV1A,
        "compare_binding": binding,
        "flash_gate": root["flash_gate"],
        "j2_on_preflight": root["j2_on_preflight"],
        "live_fresh_preflight_sha256": _sha(
            canonical_json_bytes(root["live_fresh_preflight"])
        ),
        "formal_white_claim_snapshot_before_post": root[
            "formal_white_claim_snapshot_before_post"
        ],
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
        "maximum_frame_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    _keys(
        claim,
        set(claim_exact) | {"created_at", "integrity"},
        label="compare-white permanent claim",
    )
    for key, wanted in claim_exact.items():
        if claim[key] != wanted:
            raise CompareWhiteError(f"compare-white claim {key} differs")
    created = _timestamp(claim["created_at"], label="claim creation")
    if created > started:
        raise CompareWhiteError("claim was not created before execution")
    network = _keys(
        root["network"],
        {"get_requests", "post_requests", "maximum_frame_posts", "no_retry", "no_recovery"},
        label="compare-white network evidence",
    )
    transcript = root["transcript"]
    if not isinstance(transcript, list):
        raise CompareWhiteError("compare-white transcript is malformed")
    if (
        network["get_requests"]
        != sum(isinstance(item, Mapping) and item.get("method") == "GET" for item in transcript)
        or network["post_requests"]
        != sum(isinstance(item, Mapping) and item.get("method") == "POST" for item in transcript)
        or network["maximum_frame_posts"] != 1
        or network["no_retry"] is not True
        or network["no_recovery"] is not True
    ):
        raise CompareWhiteError("compare-white network counts differ")
    if root["outcome"] == "complete_pass":
        if network["post_requests"] != 1 or root["error"] is not None:
            raise CompareWhiteError("complete compare-white result lacks one POST")
        try:
            replay = white._replay_success(transcript)  # noqa: SLF001
        except white.WhiteRecoveryError as error:
            raise CompareWhiteError(f"white transcript replay failed: {error}") from error
        protocol = root["protocol"]
        if (
            not isinstance(protocol, Mapping)
            or protocol.get("preflight") != replay["version"]
            or protocol.get("job") != replay["job"]
            or protocol.get("diagnostic") != replay["diagnostic"]
        ):
            raise CompareWhiteError("stored white protocol differs")
    elif root["outcome"] != "unknown_do_not_retry_or_recover":
        raise CompareWhiteError("compare-white outcome differs")
    return dict(root)


def create_white_manual_observation(
    *,
    result_file: Path,
    observation_file: Path,
    operator_report: str,
    temperature_c: float,
    confirm_full_white: bool,
    confirm_compare_patches_gone: bool,
    confirm_no_residual: bool,
    confirm_electrical_normal: bool,
    confirm_esp32_no_restart: bool,
    validation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    confirmations = (
        confirm_full_white,
        confirm_compare_patches_gone,
        confirm_no_residual,
        confirm_electrical_normal,
        confirm_esp32_no_restart,
    )
    if not all(confirmations):
        raise CompareWhiteError("manual white observation requires all confirmations")
    if not isinstance(operator_report, str) or not operator_report.strip():
        raise CompareWhiteError("operator report is required")
    if isinstance(temperature_c, bool) or not 0 <= temperature_c <= 60:
        raise CompareWhiteError("temperature must be between 0 and 60 C")
    result = validate_result(result_file=result_file, **dict(validation_kwargs))
    if result["outcome"] != "complete_pass":
        raise CompareWhiteError("manual observation requires a complete white result")
    result_payload = _read(result_file, label="white result for observation")
    observation = _seal(
        {
            "schema_version": 1,
            "kind": WHITE_OBSERVATION_KIND,
            "observed_at": _now(),
            "action_id": identity.FROZEN_ACTION_ID,
            "stage": identity.STAGE,
            "result_file": str(Path(result_file).resolve()),
            "result_file_sha256": _sha(result_payload),
            "result_integrity_sha256": result["integrity"]["canonical_sha256"],
            "panel": deepcopy(result["panel"]),
            "operator_report_verbatim": operator_report.strip(),
            "visual": {
                "full_screen_clean_white": True,
                "comparison_patches_completely_gone": True,
                "no_old_or_unexpected_residual": True,
            },
            "supervised": {
                "electrical_normal": True,
                "temperature_c": float(temperature_c),
                "esp32_did_not_restart_during_white_refresh": True,
            },
            "conclusion": {
                "compare_pattern_cleanly_white_recoverable": True,
                "latest_visible_state_is_clean_white": True,
                "eligible_as_u07t_white_predecessor": True,
                "formal_u07_qualification_inferred": False,
                "no_intervening_refresh_after_observation_requires_live_confirmation": True,
            },
            "retry_authorized": False,
            "recovery_replay_authorized": False,
        }
    )
    _write_new(observation_file, observation)
    return observation


def validate_white_manual_observation(
    *,
    result_file: Path,
    observation_file: Path,
    validation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    result = validate_result(result_file=result_file, **dict(validation_kwargs))
    if result["outcome"] != "complete_pass":
        raise CompareWhiteError("white observation result is not complete_pass")
    result_payload = _read(result_file, label="white result for observation")
    payload = _read(observation_file, label="white manual observation")
    root = _decode(payload, label="white manual observation")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "observed_at",
            "action_id",
            "stage",
            "result_file",
            "result_file_sha256",
            "result_integrity_sha256",
            "panel",
            "operator_report_verbatim",
            "visual",
            "supervised",
            "conclusion",
            "retry_authorized",
            "recovery_replay_authorized",
            "integrity",
        },
        label="white manual observation",
    )
    digest = _validate_integrity(root, label="white manual observation")
    observed_at = _timestamp(root["observed_at"], label="white observation time")
    if observed_at < _timestamp(result["completed_at"], label="white completion"):
        raise CompareWhiteError("white observation predates white completion")
    exact = {
        "schema_version": 1,
        "kind": WHITE_OBSERVATION_KIND,
        "action_id": identity.FROZEN_ACTION_ID,
        "stage": identity.STAGE,
        "result_file": str(Path(result_file).resolve()),
        "result_file_sha256": _sha(result_payload),
        "result_integrity_sha256": result["integrity"]["canonical_sha256"],
        "panel": result["panel"],
        "visual": {
            "full_screen_clean_white": True,
            "comparison_patches_completely_gone": True,
            "no_old_or_unexpected_residual": True,
        },
        "conclusion": {
            "compare_pattern_cleanly_white_recoverable": True,
            "latest_visible_state_is_clean_white": True,
            "eligible_as_u07t_white_predecessor": True,
            "formal_u07_qualification_inferred": False,
            "no_intervening_refresh_after_observation_requires_live_confirmation": True,
        },
        "retry_authorized": False,
        "recovery_replay_authorized": False,
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise CompareWhiteError(f"white manual observation {key} differs")
    supervised = _keys(
        root["supervised"],
        {"electrical_normal", "temperature_c", "esp32_did_not_restart_during_white_refresh"},
        label="white observation supervision",
    )
    if (
        supervised["electrical_normal"] is not True
        or supervised["esp32_did_not_restart_during_white_refresh"] is not True
        or isinstance(supervised["temperature_c"], bool)
        or not isinstance(supervised["temperature_c"], (int, float))
        or not 0 <= supervised["temperature_c"] <= 60
        or not isinstance(root["operator_report_verbatim"], str)
        or not root["operator_report_verbatim"].strip()
    ):
        raise CompareWhiteError("white manual supervision differs")
    return {
        "file": str(Path(observation_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "integrity_sha256": digest,
        "observed_at": root["observed_at"],
        "temperature_c": supervised["temperature_c"],
        "full_clean_white_pass": True,
        "eligible_as_u07t_white_predecessor": True,
    }


def create_u07t_latest_white_binding(
    *,
    result_file: Path,
    observation_file: Path,
    output_file: Path,
    validation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    result = validate_result(result_file=result_file, **dict(validation_kwargs))
    if result["outcome"] != "complete_pass":
        raise CompareWhiteError("U07T binding requires a complete white result")
    observation = validate_white_manual_observation(
        result_file=result_file,
        observation_file=observation_file,
        validation_kwargs=validation_kwargs,
    )
    result_payload = _read(result_file, label="white result for U07T binding")
    independent, _formal = _registry_isolation(
        Path(validation_kwargs.get("claim_registry", DEFAULT_CLAIM_REGISTRY)),
        Path(
            validation_kwargs.get(
                "formal_white_claim_registry", FORMAL_WHITE_CLAIM_REGISTRY
            )
        ),
        create=False,
    )
    claim_path = _claim_path(independent)
    claim_payload = _read(claim_path, label="white claim for U07T binding")
    created_at = _now()
    if _timestamp(created_at, label="U07T binding creation") < _timestamp(
        observation["observed_at"], label="manual white observation time"
    ):
        raise CompareWhiteError("U07T binding predates manual white observation")
    binding = _seal(
        {
            "schema_version": 1,
            "kind": U07T_BINDING_KIND,
            "created_at": created_at,
            "panel": deepcopy(result["panel"]),
            "predecessor_action_id": identity.FROZEN_ACTION_ID,
            "predecessor_stage": identity.STAGE,
            "compare_action_id": identity.COMPARE_ACTION_ID,
            "compare_binding": deepcopy(result["compare_binding"]),
            "white_result": {
                "file": str(Path(result_file).resolve()),
                "bytes": len(result_payload),
                "file_sha256": _sha(result_payload),
                "integrity_sha256": result["integrity"]["canonical_sha256"],
                "attempt_id": result["attempt_id"],
                "outcome": "complete_pass",
                "completed_at": result["completed_at"],
            },
            "white_claim": {
                "file": str(claim_path.resolve()),
                "bytes": len(claim_payload),
                "file_sha256": _sha(claim_payload),
                "registry_id": identity.CLAIM_REGISTRY_ID,
            },
            "manual_white_observation": observation,
            "latest_visible_state": "clean_white_after_u04_u05_comparison",
            "supersedes_prior_after_u04_white_predecessor": True,
            "invalidated_prior_u07t_action_id": (
                "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310"
            ),
            "requires_new_u07t_action_identity": True,
            "no_intervening_visible_refresh_requires_live_confirmation": True,
            "formal_u07_qualification_inferred": False,
        }
    )
    _write_new(output_file, binding)
    return binding


def validate_u07t_latest_white_binding(
    *,
    result_file: Path,
    observation_file: Path,
    binding_file: Path,
    validation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Deep-replay the only handoff accepted by the next U07T materializer."""

    result = validate_result(result_file=result_file, **dict(validation_kwargs))
    if result["outcome"] != "complete_pass":
        raise CompareWhiteError("U07T binding result is not complete_pass")
    observation = validate_white_manual_observation(
        result_file=result_file,
        observation_file=observation_file,
        validation_kwargs=validation_kwargs,
    )
    result_payload = _read(result_file, label="white result for U07T validation")
    independent, _formal = _registry_isolation(
        Path(validation_kwargs.get("claim_registry", DEFAULT_CLAIM_REGISTRY)),
        Path(
            validation_kwargs.get(
                "formal_white_claim_registry", FORMAL_WHITE_CLAIM_REGISTRY
            )
        ),
        create=False,
    )
    claim_path = _claim_path(independent)
    claim_payload = _read(claim_path, label="white claim for U07T validation")
    payload = _read(binding_file, label="U07T latest-white binding")
    root = _decode(payload, label="U07T latest-white binding")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "created_at",
            "panel",
            "predecessor_action_id",
            "predecessor_stage",
            "compare_action_id",
            "compare_binding",
            "white_result",
            "white_claim",
            "manual_white_observation",
            "latest_visible_state",
            "supersedes_prior_after_u04_white_predecessor",
            "invalidated_prior_u07t_action_id",
            "requires_new_u07t_action_identity",
            "no_intervening_visible_refresh_requires_live_confirmation",
            "formal_u07_qualification_inferred",
            "integrity",
        },
        label="U07T latest-white binding",
    )
    digest = _validate_integrity(root, label="U07T latest-white binding")
    created_at = _timestamp(root["created_at"], label="U07T binding creation")
    observed_at = _timestamp(
        observation["observed_at"], label="manual white observation time"
    )
    if created_at < observed_at:
        raise CompareWhiteError("U07T binding predates manual white observation")
    expected = {
        "schema_version": 1,
        "kind": U07T_BINDING_KIND,
        "panel": result["panel"],
        "predecessor_action_id": identity.FROZEN_ACTION_ID,
        "predecessor_stage": identity.STAGE,
        "compare_action_id": identity.COMPARE_ACTION_ID,
        "compare_binding": result["compare_binding"],
        "white_result": {
            "file": str(Path(result_file).resolve()),
            "bytes": len(result_payload),
            "file_sha256": _sha(result_payload),
            "integrity_sha256": result["integrity"]["canonical_sha256"],
            "attempt_id": result["attempt_id"],
            "outcome": "complete_pass",
            "completed_at": result["completed_at"],
        },
        "white_claim": {
            "file": str(claim_path.resolve(strict=True)),
            "bytes": len(claim_payload),
            "file_sha256": _sha(claim_payload),
            "registry_id": identity.CLAIM_REGISTRY_ID,
        },
        "manual_white_observation": observation,
        "latest_visible_state": "clean_white_after_u04_u05_comparison",
        "supersedes_prior_after_u04_white_predecessor": True,
        "invalidated_prior_u07t_action_id": (
            "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310"
        ),
        "requires_new_u07t_action_identity": True,
        "no_intervening_visible_refresh_requires_live_confirmation": True,
        "formal_u07_qualification_inferred": False,
    }
    for key, wanted in expected.items():
        if root[key] != wanted:
            raise CompareWhiteError(f"U07T latest-white binding {key} differs")
    if observed_at < _timestamp(
        result["completed_at"], label="white result completion"
    ):
        raise CompareWhiteError("manual white observation predates result completion")
    return {
        "file": str(Path(binding_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "integrity_sha256": digest,
        "created_at": root["created_at"],
        "predecessor_action_id": identity.FROZEN_ACTION_ID,
        "predecessor_stage": identity.STAGE,
        "latest_visible_state": root["latest_visible_state"],
        "requires_new_u07t_action_identity": True,
        "no_intervening_visible_refresh_requires_live_confirmation": True,
    }


def _common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--compare-release", type=Path, required=True)
    parser.add_argument("--compare-result", type=Path, required=True)
    parser.add_argument("--compare-claim-registry", type=Path, required=True)
    parser.add_argument("--compare-observation", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--rc2g-binary", type=Path, required=True)
    parser.add_argument(
        "--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY
    )
    parser.add_argument(
        "--formal-white-claim-registry",
        type=Path,
        default=FORMAL_WHITE_CLAIM_REGISTRY,
    )


def _validation_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "flash_gate_file": args.flash_gate,
        "preflight_file": args.preflight,
        "compare_release_file": args.compare_release,
        "compare_result_file": args.compare_result,
        "compare_claim_registry": args.compare_claim_registry,
        "compare_observation_file": args.compare_observation,
        "panel_file": args.panel,
        "rc2g_binary_file": args.rc2g_binary,
        "claim_registry": args.claim_registry,
        "formal_white_claim_registry": args.formal_white_claim_registry,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-j2-off", allow_abbrev=False)
    _common_args(prepare)
    prepare.add_argument("--evidence", type=Path, required=True)
    prepare.add_argument("--confirm-j2-off", action="store_true")
    preflight = commands.add_parser("preflight", allow_abbrev=False)
    _common_args(preflight)
    preflight.add_argument("--base-url", required=True)
    preflight.add_argument("--flash-gate", type=Path, required=True)
    preflight.add_argument("--evidence", type=Path, required=True)
    preflight.add_argument("--confirm-j2-on", action="store_true")
    preflight.add_argument("--confirm-electrical-normal", action="store_true")
    run = commands.add_parser("run", allow_abbrev=False)
    _common_args(run)
    run.add_argument("--base-url", required=True)
    run.add_argument("--flash-gate", type=Path, required=True)
    run.add_argument("--preflight", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--authorize", required=True)
    run.add_argument("--confirm-j2-on", action="store_true")
    run.add_argument("--confirm-electrical-normal", action="store_true")
    validate = commands.add_parser("validate", allow_abbrev=False)
    _common_args(validate)
    validate.add_argument("--flash-gate", type=Path, required=True)
    validate.add_argument("--preflight", type=Path, required=True)
    validate.add_argument("--result", type=Path, required=True)
    for name in (
        "seal-observation",
        "validate-observation",
        "u07t-binding",
        "validate-u07t-binding",
    ):
        item = commands.add_parser(name, allow_abbrev=False)
        _common_args(item)
        item.add_argument("--flash-gate", type=Path, required=True)
        item.add_argument("--preflight", type=Path, required=True)
        item.add_argument("--result", type=Path, required=True)
        item.add_argument("--white-observation", type=Path, required=True)
        if name == "seal-observation":
            item.add_argument("--operator-report", required=True)
            item.add_argument("--temperature-c", type=float, required=True)
            item.add_argument("--confirm-full-white", action="store_true")
            item.add_argument("--confirm-compare-patches-gone", action="store_true")
            item.add_argument("--confirm-no-residual", action="store_true")
            item.add_argument("--confirm-electrical-normal", action="store_true")
            item.add_argument("--confirm-esp32-no-restart", action="store_true")
        if name == "u07t-binding":
            item.add_argument("--output", type=Path, required=True)
        if name == "validate-u07t-binding":
            item.add_argument("--binding", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    common = {
        "compare_release_file": args.compare_release,
        "compare_result_file": args.compare_result,
        "compare_claim_registry": args.compare_claim_registry,
        "compare_observation_file": args.compare_observation,
        "panel_file": args.panel,
        "rc2g_binary_file": args.rc2g_binary,
        "claim_registry": args.claim_registry,
        "formal_white_claim_registry": args.formal_white_claim_registry,
    }
    try:
        if args.command == "prepare-j2-off":
            output = create_j2_off_flash_gate(
                evidence_file=args.evidence,
                confirm_j2_off=args.confirm_j2_off,
                **common,
            )
        elif args.command == "preflight":
            output = create_j2_on_preflight(
                base_url=args.base_url,
                flash_gate_file=args.flash_gate,
                evidence_file=args.evidence,
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                **common,
            )
        elif args.command == "run":
            output = run_once(
                base_url=args.base_url,
                authorization=args.authorize,
                flash_gate_file=args.flash_gate,
                preflight_file=args.preflight,
                result_file=args.result,
                confirm_j2_on=args.confirm_j2_on,
                confirm_electrical_normal=args.confirm_electrical_normal,
                **common,
            )
        elif args.command == "validate":
            output = validate_result(
                result_file=args.result,
                flash_gate_file=args.flash_gate,
                preflight_file=args.preflight,
                **common,
            )
        else:
            kwargs = _validation_kwargs(args)
            if args.command == "seal-observation":
                output = create_white_manual_observation(
                    result_file=args.result,
                    observation_file=args.white_observation,
                    operator_report=args.operator_report,
                    temperature_c=args.temperature_c,
                    confirm_full_white=args.confirm_full_white,
                    confirm_compare_patches_gone=args.confirm_compare_patches_gone,
                    confirm_no_residual=args.confirm_no_residual,
                    confirm_electrical_normal=args.confirm_electrical_normal,
                    confirm_esp32_no_restart=args.confirm_esp32_no_restart,
                    validation_kwargs=kwargs,
                )
            elif args.command == "validate-observation":
                output = validate_white_manual_observation(
                    result_file=args.result,
                    observation_file=args.white_observation,
                    validation_kwargs=kwargs,
                )
            elif args.command == "u07t-binding":
                output = create_u07t_latest_white_binding(
                    result_file=args.result,
                    observation_file=args.white_observation,
                    output_file=args.output,
                    validation_kwargs=kwargs,
                )
            else:
                output = validate_u07t_latest_white_binding(
                    result_file=args.result,
                    observation_file=args.white_observation,
                    binding_file=args.binding,
                    validation_kwargs=kwargs,
                )
    except CompareWhiteError as error:
        print(f"EC5 compare-white error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
