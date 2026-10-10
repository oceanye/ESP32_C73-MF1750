#!/usr/bin/env python3
"""Seal the P2-C retained clean-white human admission observation.

This tool is deliberately offline-only.  It does not open a camera, serial
port, relay, or network connection and it cannot flash or refresh a display.
It binds one direct human observation to the exact, already-completed P1
factory-white result, permanent claim, source gate, and relay-OFF receipt.

The record is tamper-evident and is created with ``O_EXCL``.  The operator's
words are retained verbatim.  Because a chat statement has no cryptographic
operator signature, the record explicitly remains a conversation assertion;
it proves neither uninterrupted retention since the white action nor the
electrical state behind the relay contact.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_once as p2  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-p2-retained-clean-white-human-review-v1"
EXPECTED_SOURCE_ACTION_ID = (
    "b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc"
)
SOURCE_FILE_NAMES = ("white_result", "white_claim", "source_gate", "relay_off")
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
OUTPUT_WRITE_CONTRACT = "O_EXCL"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_VERBATIM_CHARACTERS = 4096
OFFLINE_EXECUTION = {
    "hardware_accessed": False,
    "camera_accessed": False,
    "relay_accessed": False,
    "serial_or_com_accessed": False,
    "network_accessed": False,
    "firmware_flashed": False,
    "display_refreshed": False,
    "visible_refreshes": 0,
}
EVIDENCE_BOUNDARIES = {
    "conversation_assertion_only": True,
    "cryptographic_operator_identity_proven": False,
    "camera_evidence_claimed": False,
    "retained_action_to_observation_continuity_proven": False,
    "no_intervening_visible_refresh_proven": False,
    "relay_off_is_command_and_query_not_load_voltage_proof": True,
    "electrical_state_proven": False,
    "absolute_white_point_proven": False,
    "spatial_uniformity_or_colour_level_qualified": False,
    "live_action_authorized_by_this_record": False,
}


class RetainedCleanWhiteHumanReviewError(RuntimeError):
    """The human review or one of its exact source bindings is invalid."""


class _DuplicateKeyError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"value is not canonical-JSON encodable: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(unsigned))
    value["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256(canonical_json_bytes(value)),
    }
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKeyError(key)
        value[key] = item
    return value


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
    except OSError as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"cannot stat {label}: {error}"
        ) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RetainedCleanWhiteHumanReviewError(
            f"{label} must be a regular non-symlink file"
        )
    if before.st_size < 1 or before.st_size > MAX_JSON_BYTES:
        raise RetainedCleanWhiteHumanReviewError(f"{label} size is outside its limit")
    try:
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"cannot read {label}: {error}"
        ) from error
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != before.st_size:
        raise RetainedCleanWhiteHumanReviewError(f"{label} changed while being read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateKeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(root, dict):
        raise RetainedCleanWhiteHumanReviewError(f"{label} root must be an object")
    return payload, root


def _timestamp(value: Any, *, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise RetainedCleanWhiteHumanReviewError(
            f"{label} must be non-empty RFC3339 text"
        )
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"{label} is not RFC3339"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RetainedCleanWhiteHumanReviewError(f"{label} must include a UTC offset")
    return value, parsed


def _text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetainedCleanWhiteHumanReviewError(f"{label} must be non-empty text")
    if len(value) > maximum:
        raise RetainedCleanWhiteHumanReviewError(f"{label} is too long")
    return value


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def validate_source_machine_authority() -> dict[str, Any]:
    """Deep-replay and snapshot the exact latest P1 white machine evidence."""

    try:
        authority = p2.validate_source_white_authority()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"latest P1 white source authority failed: {error}"
        ) from error
    files = authority.get("files")
    if (
        authority.get("kind")
        != "mf1750-p2-latest-p1-white-successor-machine-authority-v1"
        or authority.get("sealed") is not True
        or authority.get("source_action_id") != EXPECTED_SOURCE_ACTION_ID
        or authority.get("relay_off_commanded_and_queried") is not True
        or authority.get("electrical_state_proven") is not False
        or authority.get("retained_action_to_review_continuity_claimed") is not False
        or not isinstance(files, Mapping)
        or set(files) != set(SOURCE_FILE_NAMES)
    ):
        raise RetainedCleanWhiteHumanReviewError(
            "latest P1 white machine authority semantics differ"
        )
    source_files: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILE_NAMES:
        binding = files.get(name)
        if not isinstance(binding, Mapping) or set(binding) != {
            "path",
            "bytes",
            "file_sha256",
            "canonical_sha256",
        }:
            raise RetainedCleanWhiteHumanReviewError(
                f"latest P1 white {name} binding differs"
            )
        path = binding.get("path")
        if not isinstance(path, str) or not path or Path(path).is_absolute():
            raise RetainedCleanWhiteHumanReviewError(
                f"latest P1 white {name} path is not repository-relative"
            )
        byte_count = binding.get("bytes")
        file_sha = binding.get("file_sha256")
        canonical_sha = binding.get("canonical_sha256")
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 1
            or not isinstance(file_sha, str)
            or len(file_sha) != 64
            or not isinstance(canonical_sha, str)
            or len(canonical_sha) != 64
        ):
            raise RetainedCleanWhiteHumanReviewError(
                f"latest P1 white {name} file seal differs"
            )
        source_files[name] = dict(binding)
    return {
        "kind": authority["kind"],
        "state": authority["state"],
        "source_campaign_id": authority["source_campaign_id"],
        "source_contract_id": authority["source_contract_id"],
        "source_descriptor_id": authority["source_descriptor_id"],
        "source_action_id": authority["source_action_id"],
        "source_boot_nonce": authority["source_boot_nonce"],
        "source_firmware_sha256": authority["source_firmware_sha256"],
        "source_elf_sha256": authority["source_elf_sha256"],
        "source_p1_action_id": authority["source_p1_action_id"],
        "files": source_files,
        "relay_off_commanded_and_queried": True,
        "electrical_state_proven": False,
    }


def _relay_switched_at(authority: Mapping[str, Any]) -> tuple[str, datetime]:
    binding = authority["files"]["relay_off"]
    relay_path = REPO_ROOT / binding["path"]
    payload, root = _load_json(relay_path, label="latest P1 relay-OFF receipt")
    if (
        len(payload) != binding["bytes"]
        or _sha256(payload) != binding["file_sha256"]
    ):
        raise RetainedCleanWhiteHumanReviewError(
            "latest P1 relay-OFF receipt changed after source validation"
        )
    return _timestamp(root.get("switched_at"), label="relay switched_at")


def build_review(
    *,
    reported_at: str,
    operator_verbatim: str,
    confirm_full_screen_clean_white: bool,
    confirm_no_visible_colour_block_border_stain_or_fixed_line: bool,
    confirm_direct_current_visual_inspection: bool,
    confirm_source_message_is_explicit_clean_white_confirmation: bool,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Build but do not write one exact P2 retained-white human review."""

    if not all(
        type(value) is bool and value is True
        for value in (
            confirm_full_screen_clean_white,
            confirm_no_visible_colour_block_border_stain_or_fixed_line,
            confirm_direct_current_visual_inspection,
            confirm_source_message_is_explicit_clean_white_confirmation,
        )
    ):
        raise RetainedCleanWhiteHumanReviewError(
            "an explicit current clean-white human confirmation is required"
        )
    verbatim = _text(
        operator_verbatim,
        label="operator_verbatim",
        maximum=MAX_VERBATIM_CHARACTERS,
    )
    reported_text, reported = _timestamp(reported_at, label="reported_at")
    recorded_text, recorded = _timestamp(
        _now() if recorded_at is None else recorded_at,
        label="recorded_at",
    )
    if recorded < reported:
        raise RetainedCleanWhiteHumanReviewError(
            "recorded_at cannot precede reported_at"
        )
    authority = validate_source_machine_authority()
    _relay_text, relay_switched = _relay_switched_at(authority)
    if reported < relay_switched:
        raise RetainedCleanWhiteHumanReviewError(
            "reported_at cannot precede the bound relay-OFF receipt"
        )
    raw_observation = {
        "source": "conversation-user-message",
        "operator_id": "conversation-user",
        "operator_verbatim": verbatim,
        "reported_at": reported_text,
        "source_message_is_explicit_clean_white_confirmation": True,
    }
    visual_observation = {
        "method": "human-direct-current-visual-inspection",
        "full_screen_clean_white_confirmed": True,
        "no_visible_colour_block_border_stain_or_fixed_line_confirmed": True,
        "admission_scope": "CURRENT_RETAINED_FULL_SCREEN_VISUAL_PRECONDITION_ONLY",
    }
    review_id = _sha256(
        canonical_json_bytes(
            {
                "machine_authority": authority,
                "raw_operator_observation": raw_observation,
                "visual_observation": visual_observation,
                "recorded_at": recorded_text,
            }
        )
    )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "review_id": review_id,
            "recorded_at": recorded_text,
            "campaign_id": p2.pack.CAMPAIGN_ID,
            "machine_authority_binding": authority,
            "raw_operator_observation": raw_observation,
            "visual_observation": visual_observation,
            "evidence_boundaries": deepcopy(EVIDENCE_BOUNDARIES),
            "offline_execution": deepcopy(OFFLINE_EXECUTION),
            "output_write_contract": OUTPUT_WRITE_CONTRACT,
        }
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise RetainedCleanWhiteHumanReviewError(
            f"refusing to overwrite output: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def create_review(*, output_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Build and exclusively persist one current human review."""

    value = build_review(**kwargs)
    _write_exclusive(Path(output_path), canonical_json_bytes(value) + b"\n")
    return value


def validate_review(path: Path) -> dict[str, Any]:
    """Deep-replay a stored review against the current exact source evidence."""

    payload, root = _load_json(Path(path), label="P2 retained-white human review")
    if payload != canonical_json_bytes(root) + b"\n":
        raise RetainedCleanWhiteHumanReviewError(
            "review is not canonical JSON with one trailing newline"
        )
    expected_keys = {
        "schema_version",
        "kind",
        "review_id",
        "recorded_at",
        "campaign_id",
        "machine_authority_binding",
        "raw_operator_observation",
        "visual_observation",
        "evidence_boundaries",
        "offline_execution",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_keys:
        raise RetainedCleanWhiteHumanReviewError("review top-level keys differ")
    unsigned = deepcopy(root)
    integrity = unsigned.pop("integrity", None)
    if integrity != {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256(canonical_json_bytes(unsigned)),
    }:
        raise RetainedCleanWhiteHumanReviewError("review canonical integrity differs")
    raw = root.get("raw_operator_observation")
    visual = root.get("visual_observation")
    if not isinstance(raw, Mapping) or set(raw) != {
        "source",
        "operator_id",
        "operator_verbatim",
        "reported_at",
        "source_message_is_explicit_clean_white_confirmation",
    }:
        raise RetainedCleanWhiteHumanReviewError("raw operator observation differs")
    if not isinstance(visual, Mapping) or set(visual) != {
        "method",
        "full_screen_clean_white_confirmed",
        "no_visible_colour_block_border_stain_or_fixed_line_confirmed",
        "admission_scope",
    }:
        raise RetainedCleanWhiteHumanReviewError("visual observation differs")
    _text(
        raw.get("operator_verbatim"),
        label="operator_verbatim",
        maximum=MAX_VERBATIM_CHARACTERS,
    )
    reported_text, reported = _timestamp(raw.get("reported_at"), label="reported_at")
    recorded_text, recorded = _timestamp(root.get("recorded_at"), label="recorded_at")
    if reported > recorded:
        raise RetainedCleanWhiteHumanReviewError(
            "recorded_at cannot precede reported_at"
        )
    authority = validate_source_machine_authority()
    _relay_text, relay_switched = _relay_switched_at(authority)
    if reported < relay_switched:
        raise RetainedCleanWhiteHumanReviewError(
            "reported_at cannot precede the bound relay-OFF receipt"
        )
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("campaign_id") != p2.pack.CAMPAIGN_ID
        or root.get("machine_authority_binding") != authority
        or raw.get("source") != "conversation-user-message"
        or raw.get("operator_id") != "conversation-user"
        or raw.get("reported_at") != reported_text
        or raw.get("source_message_is_explicit_clean_white_confirmation") is not True
        or visual.get("method") != "human-direct-current-visual-inspection"
        or visual.get("full_screen_clean_white_confirmed") is not True
        or visual.get(
            "no_visible_colour_block_border_stain_or_fixed_line_confirmed"
        )
        is not True
        or visual.get("admission_scope")
        != "CURRENT_RETAINED_FULL_SCREEN_VISUAL_PRECONDITION_ONLY"
        or root.get("evidence_boundaries") != EVIDENCE_BOUNDARIES
        or root.get("offline_execution") != OFFLINE_EXECUTION
        or root.get("output_write_contract") != OUTPUT_WRITE_CONTRACT
        or root.get("recorded_at") != recorded_text
    ):
        raise RetainedCleanWhiteHumanReviewError("review semantics differ")
    expected_review_id = _sha256(
        canonical_json_bytes(
            {
                "machine_authority": authority,
                "raw_operator_observation": dict(raw),
                "visual_observation": dict(visual),
                "recorded_at": recorded_text,
            }
        )
    )
    if root.get("review_id") != expected_review_id:
        raise RetainedCleanWhiteHumanReviewError("review_id differs")
    return dict(root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    seal = sub.add_parser("seal", allow_abbrev=False)
    seal.add_argument("--reported-at", required=True)
    seal.add_argument("--operator-verbatim", required=True)
    seal.add_argument("--output", type=Path, default=p2.RETAINED_CLEAN_WHITE_REVIEW)
    seal.add_argument("--confirm-full-screen-clean-white", action="store_true", required=True)
    seal.add_argument(
        "--confirm-no-visible-colour-block-border-stain-or-fixed-line",
        action="store_true",
        required=True,
    )
    seal.add_argument(
        "--confirm-direct-current-visual-inspection",
        action="store_true",
        required=True,
    )
    seal.add_argument(
        "--confirm-source-message-is-explicit-clean-white-confirmation",
        action="store_true",
        required=True,
    )
    validate = sub.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--review", type=Path, required=True)
    sub.add_parser("validate-source", allow_abbrev=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-source":
            value = validate_source_machine_authority()
        elif args.command == "validate":
            value = validate_review(args.review)
        else:
            value = create_review(
                output_path=args.output,
                reported_at=args.reported_at,
                operator_verbatim=args.operator_verbatim,
                confirm_full_screen_clean_white=args.confirm_full_screen_clean_white,
                confirm_no_visible_colour_block_border_stain_or_fixed_line=(
                    args.confirm_no_visible_colour_block_border_stain_or_fixed_line
                ),
                confirm_direct_current_visual_inspection=(
                    args.confirm_direct_current_visual_inspection
                ),
                confirm_source_message_is_explicit_clean_white_confirmation=(
                    args.confirm_source_message_is_explicit_clean_white_confirmation
                ),
            )
    except (RetainedCleanWhiteHumanReviewError, OSError) as error:
        print(f"P2 retained clean-white human review error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
