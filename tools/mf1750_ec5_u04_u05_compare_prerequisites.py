#!/usr/bin/env python3
"""Replay the immutable U04 and after-U04 white evidence for comparison work.

The corrected-V2 release source snapshot describes the source tree at release
time.  Later development is expected to change the live tree, so this replay
checks the sealed release, copied firmware/ELFs and compiled-symbol report
without requiring today's source files to retain the historical bytes.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from unittest.mock import patch

from tools import mf1750_ec5_compiled_identity as compiled_identity
from tools import mf1750_ec5_physical_once as candidate_runner
from tools import mf1750_ec5_release as corrected_release
from tools import mf1750_ec5_stage_a_v2_identity as corrected_identity
from tools import mf1750_ec5_white_recovery_once as white_runner


U04_ACTION_ID = corrected_identity.FROZEN_ACTION_IDS["U04"]
WHITE_ACTION_ID = white_runner.ACTION_IDS["after-u04"]
SHORT_HOLD_KIND = "mf1750-ec5-u04-operator-short-hold-observation"
WHITE_OBSERVATION_KIND = "mf1750-ec5-solid-white-manual-observation"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


class ComparePrerequisiteError(ValueError):
    """Historical prerequisite evidence failed closed."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path, *, label: str, maximum: int = 64 * 1024 * 1024) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise ComparePrerequisiteError(f"{label} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise ComparePrerequisiteError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ComparePrerequisiteError(f"could not read {label}: {error}") from error
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(payload) != after.st_size
    ):
        raise ComparePrerequisiteError(f"{label} changed while read")
    return payload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComparePrerequisiteError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ComparePrerequisiteError(f"{label} contains {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparePrerequisiteError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise ComparePrerequisiteError(f"{label} root must be an object")
    return value


def _panel(panel_file: Path) -> dict[str, str]:
    root = _json(_read(panel_file, label="panel", maximum=64 * 1024), label="panel")
    expected = {"model", "serial", "board_id", "pcb_revision"}
    if set(root) != expected:
        raise ComparePrerequisiteError("panel fields differ")
    result = {}
    for key in ("model", "serial", "board_id", "pcb_revision"):
        value = root[key]
        if not isinstance(value, str) or not value or value != value.strip():
            raise ComparePrerequisiteError(f"panel {key} is invalid")
        result[key] = value
    return result


def load_historical_u04_context(
    release_file: Path, panel_file: Path
) -> candidate_runner.ReleaseContext:
    """Deeply replay corrected-V2 U04 without a live-source equality gate."""

    release_file = Path(release_file)
    payload = _read(release_file, label="corrected-V2 release")
    root = _json(payload, label="corrected-V2 release")
    expected_keys = {
        "schema_version",
        "kind",
        "identity_revision",
        "created_at",
        "panel",
        "source_snapshot",
        "device_contract",
        "incident_lineage",
        "compiled_identity_report",
        "variants",
        "safety",
        "integrity",
    }
    if set(root) != expected_keys:
        raise ComparePrerequisiteError("corrected-V2 release fields differ")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if (
        not isinstance(integrity, Mapping)
        or set(integrity) != {"canonical_sha256", "scope"}
        or integrity.get("scope") != corrected_release.HASH_SCOPE
        or integrity.get("canonical_sha256") != _sha(canonical_json_bytes(unsigned))
    ):
        raise ComparePrerequisiteError("corrected-V2 release integrity differs")
    if (
        root["schema_version"] != corrected_release.SCHEMA_VERSION
        or root["kind"] != corrected_release.KIND
        or root["identity_revision"] != corrected_identity.IDENTITY_REVISION
        or root["device_contract"] != corrected_release.DEVICE_CONTRACT
        or root["incident_lineage"] != corrected_release.INCIDENT_LINEAGE
        or root["safety"] != corrected_release.SAFETY
    ):
        raise ComparePrerequisiteError("corrected-V2 release contract differs")
    panel = _panel(panel_file)
    if root["panel"] != panel:
        raise ComparePrerequisiteError("corrected-V2 panel differs")
    source = root["source_snapshot"]
    if not isinstance(source, Mapping) or set(source) != {
        "git_head",
        "git_dirty",
        "git_status_sha256",
        "git_status_line_count",
        "relevant_sources",
    }:
        raise ComparePrerequisiteError("historical source snapshot is malformed")
    if not isinstance(source["relevant_sources"], list) or [
        item.get("path") if isinstance(item, Mapping) else None
        for item in source["relevant_sources"]
    ] != list(corrected_release.SOURCE_PATHS):
        raise ComparePrerequisiteError("historical source list differs")
    for item in source["relevant_sources"]:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"path", "bytes", "sha256"}
            or not isinstance(item["bytes"], int)
            or item["bytes"] <= 0
            or SHA_RE.fullmatch(str(item["sha256"])) is None
        ):
            raise ComparePrerequisiteError("historical source entry is malformed")

    variants = root["variants"]
    if not isinstance(variants, Mapping) or set(variants) != {"U04", "U07"}:
        raise ComparePrerequisiteError("corrected-V2 variants differ")
    paths: dict[str, tuple[Path, Path]] = {}
    for candidate in ("U04", "U07"):
        variant = variants[candidate]
        frozen = corrected_identity.VARIANTS[candidate]
        if not isinstance(variant, Mapping):
            raise ComparePrerequisiteError(f"{candidate} variant is malformed")
        for key in (
            "candidate_id",
            "candidate_code",
            "environment",
            "build_tag",
            "test_id",
            "action_id",
            "identity_revision",
            "device_api_version",
            "top_schema_version",
            "driver_evidence_schema_version",
            "layout_id",
            "frame_sha256",
            "frame_fnv1a",
            "dtm_sha256",
            "dtm_fnv1a",
            "action_identity_preimage",
            "action_identity_sha256_scope",
            "nvs_contract",
        ):
            if variant.get(key) != frozen[key]:
                raise ComparePrerequisiteError(f"{candidate} variant {key} differs")
        if corrected_identity.derive_action_id(
            variant["action_identity_preimage"]
        ) != variant["action_id"]:
            raise ComparePrerequisiteError(f"{candidate} action preimage differs")
        firmware_entry = variant.get("firmware")
        elf_entry = variant.get("elf")
        if not isinstance(firmware_entry, Mapping) or set(firmware_entry) != {
            "file",
            "bytes",
            "sha256",
        }:
            raise ComparePrerequisiteError(f"{candidate} firmware entry differs")
        if not isinstance(elf_entry, Mapping) or set(elf_entry) != {
            "file",
            "bytes",
            "sha256",
        }:
            raise ComparePrerequisiteError(f"{candidate} ELF entry differs")
        firmware_path = release_file.parent / str(firmware_entry["file"])
        elf_path = release_file.parent / str(elf_entry["file"])
        firmware = _read(firmware_path, label=f"{candidate} firmware")
        elf = _read(elf_path, label=f"{candidate} ELF")
        if (
            len(firmware) != firmware_entry["bytes"]
            or _sha(firmware) != firmware_entry["sha256"]
            or len(elf) != elf_entry["bytes"]
            or _sha(elf) != elf_entry["sha256"]
        ):
            raise ComparePrerequisiteError(f"{candidate} artifact differs")
        paths[candidate] = (firmware_path, elf_path)
    try:
        compiled = compiled_identity.validate_pair(
            paths["U04"][1], paths["U07"][1]
        )
    except compiled_identity.CompiledIdentityError as error:
        raise ComparePrerequisiteError(
            f"corrected-V2 compiled identity replay failed: {error}"
        ) from error
    if root["compiled_identity_report"] != compiled:
        raise ComparePrerequisiteError("corrected-V2 compiled report differs")

    u04 = variants["U04"]
    return candidate_runner.ReleaseContext(
        path=release_file.resolve(),
        root=root,
        variant_id="U04",
        variant=u04,
        binary_path=paths["U04"][0].resolve(),
        binary_sha256=u04["firmware"]["sha256"],
        elf_path=paths["U04"][1].resolve(),
        elf_sha256=u04["elf"]["sha256"],
        release_canonical_sha256=integrity["canonical_sha256"],
        panel=panel,
        panel_verified=True,
        source_root=release_file.parent.resolve(),
        panel_file=Path(panel_file).resolve(),
    )


def load_u04_result_binding(
    *,
    release_file: Path,
    result_file: Path,
    panel_file: Path,
    claim_registry: Path,
) -> tuple[candidate_runner.ReleaseContext, dict[str, Any]]:
    context = load_historical_u04_context(release_file, panel_file)
    try:
        result = candidate_runner.validate_result(
            context, Path(result_file), claim_registry=Path(claim_registry)
        )
    except candidate_runner.Ec5PhysicalError as error:
        raise ComparePrerequisiteError(f"U04 result replay failed: {error}") from error
    if result["outcome"] != "complete_pass":
        raise ComparePrerequisiteError("U04 result is not complete_pass")
    result_payload = _read(result_file, label="U04 result")
    claim_path = Path(claim_registry) / f"{U04_ACTION_ID}.json"
    claim_payload = _read(claim_path, label="U04 permanent claim")
    return context, {
        "action_id": U04_ACTION_ID,
        "attempt_id": result["attempt_id"],
        "outcome": "complete_pass",
        "release_file": str(Path(release_file).resolve()),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "result_file": str(Path(result_file).resolve()),
        "result_bytes": len(result_payload),
        "result_file_sha256": _sha(result_payload),
        "result_integrity_sha256": result["integrity"]["canonical_sha256"],
        "claim_file": str(claim_path.resolve()),
        "claim_bytes": len(claim_payload),
        "claim_file_sha256": _sha(claim_payload),
        "panel": deepcopy(context.panel),
        "historical_source_snapshot_bound_not_live_source_equality": True,
    }


def load_short_hold_boundary(
    observation_file: Path, *, u04_result_file: Path
) -> dict[str, Any]:
    payload = _read(observation_file, label="U04 short-hold observation")
    root = _json(payload, label="U04 short-hold observation")
    expected_keys = {
        "schema_version",
        "kind",
        "candidate_id",
        "candidate_code",
        "action_id",
        "result_file",
        "result_file_sha256",
        "refresh_finished_at",
        "immediate_observation",
        "five_minute_observation",
        "not_reported",
        "thirty_minute_observation",
        "conclusion",
        "retry_authorized",
        "recovery_implicitly_authorized",
    }
    if set(root) != expected_keys:
        raise ComparePrerequisiteError("short-hold fields differ")
    result_payload = _read(u04_result_file, label="U04 result for short hold")
    if (
        root["schema_version"] != 1
        or root["kind"] != SHORT_HOLD_KIND
        or root["candidate_id"] != "U04"
        or root["candidate_code"] != 4
        or root["action_id"] != U04_ACTION_ID
        or root["result_file"] != Path(u04_result_file).name
        or root["result_file_sha256"] != _sha(result_payload)
        or root["retry_authorized"] is not False
        or root["recovery_implicitly_authorized"] is not False
    ):
        raise ComparePrerequisiteError("short-hold identity differs")
    immediate = root["immediate_observation"]
    five = root["five_minute_observation"]
    skipped = root["thirty_minute_observation"]
    conclusion = root["conclusion"]
    if (
        not isinstance(immediate, Mapping)
        or any(
            immediate.get(key) is not True
            for key in (
                "geometry_correct",
                "left_right_symmetric",
                "edges_clear",
                "patch_uniform",
                "white_background_clean",
                "electrical_normal",
            )
        )
        or immediate.get("operator_perceived_color") != "blue"
        or not isinstance(five, Mapping)
        or five.get("visually_unchanged_from_immediate") is not True
        or five.get("electrical_normal") is not True
        or not isinstance(skipped, Mapping)
        or skipped.get("status") != "SKIPPED_BY_OPERATOR"
        or not isinstance(conclusion, Mapping)
        or conclusion.get("short_term_optical_stability_through_about_five_minutes")
        is not True
        or conclusion.get("long_term_thirty_minute_stability_evaluated") is not False
        or conclusion.get("formal_hold_0_5_30_chain_satisfied") is not False
    ):
        raise ComparePrerequisiteError("short-hold/skip boundary differs")
    return {
        "file": str(Path(observation_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "kind": SHORT_HOLD_KIND,
        "action_id": U04_ACTION_ID,
        "five_minute_short_hold_passed": True,
        "thirty_minute_observation": "SKIPPED_BY_OPERATOR",
        "thirty_minute_hold_required_for_comparison": False,
        "formal_u07_gate_satisfied": False,
    }


def load_white_result_binding(
    *,
    context: candidate_runner.ReleaseContext,
    release_file: Path,
    u04_result_file: Path,
    white_result_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    candidate_claim_registry: Path,
    white_claim_registry: Path,
) -> dict[str, Any]:
    """Run the authoritative white validator against the historical context."""

    try:
        with patch.object(candidate_runner, "load_release", return_value=context):
            binding = white_runner.load_result_binding(
                result_file=Path(white_result_file),
                panel_file=Path(panel_file),
                rc2g_binary_file=Path(rc2g_binary_file),
                claim_registry=Path(white_claim_registry),
                release_file=Path(release_file),
                candidate_result_file=Path(u04_result_file),
                candidate_claim_registry=Path(candidate_claim_registry),
            )
    except white_runner.WhiteRecoveryError as error:
        raise ComparePrerequisiteError(
            f"after-U04 white replay failed: {error}"
        ) from error
    if binding["stage"] != "after-u04" or binding["action_id"] != WHITE_ACTION_ID:
        raise ComparePrerequisiteError("after-U04 white binding differs")
    return binding


def load_white_manual_observation(
    observation_file: Path, *, white_result_file: Path
) -> dict[str, Any]:
    payload = _read(observation_file, label="white manual observation")
    root = _json(payload, label="white manual observation")
    result_payload = _read(white_result_file, label="white result for observation")
    if (
        root.get("schema_version") != 1
        or root.get("kind") != WHITE_OBSERVATION_KIND
        or root.get("stage") != "after-u04"
        or root.get("action_id") != WHITE_ACTION_ID
        or root.get("result_file") != Path(white_result_file).name
        or root.get("result_file_sha256") != _sha(result_payload)
        or root.get("decision") != "VISUAL_AND_ELECTRICAL_PASS"
        or root.get("retry_authorized") is not False
        or root.get("recovery_replay_authorized") is not False
    ):
        raise ComparePrerequisiteError("white manual observation identity differs")
    visual = root.get("visual")
    supervised = root.get("supervised_observation")
    conclusion = root.get("conclusion")
    if (
        not isinstance(visual, Mapping)
        or any(value is not True for value in visual.values())
        or not isinstance(supervised, Mapping)
        or supervised.get("electrical_normal") is not True
        or not isinstance(conclusion, Mapping)
        or conclusion.get("u04_short_term_state_cleanly_white_recoverable") is not True
        or conclusion.get("new_seventh_color_proven") is not False
    ):
        raise ComparePrerequisiteError("white manual observation result differs")
    return {
        "file": str(Path(observation_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "kind": WHITE_OBSERVATION_KIND,
        "action_id": WHITE_ACTION_ID,
        "visual_and_electrical_pass": True,
        "u04_cleanly_white_recoverable": True,
        "u04_distinct_from_u05_not_yet_proven": True,
    }

