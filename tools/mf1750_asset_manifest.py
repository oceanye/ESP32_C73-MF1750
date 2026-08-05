#!/usr/bin/env python3
"""Create a non-overwriting SHA-256 manifest for explicitly listed evidence files.

This tool is deliberately offline.  It has no device, serial, HTTP, discovery,
refresh, delete, or retry capability.  Files are only read when they are named
in the input plan, and the output is opened with exclusive-create semantics.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
import re
import stat
import sys
from typing import Any, Mapping, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.local_path_safety import (
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


KIND = "mf1750-extended-color-asset-manifest"
SCHEMA_VERSION = 1
ROLES = frozenset(
    {
        "raw_camera",
        "oscilloscope",
        "colorimeter",
        "thermal",
        "environment",
        "power_supply",
        "other",
    }
)
PLAN_KEYS = frozenset({"run_id", "root_label", "hardware_tested", "assets"})
ASSET_KEYS = frozenset({"role", "path", "captured_at", "instrument_id"})
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "run_id",
        "created_at",
        "root_label",
        "hardware_tested",
        "assets",
    }
)
REPORT_ASSET_KEYS = frozenset(
    {"role", "relative_path", "bytes", "sha256", "captured_at", "instrument_id"}
)
REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_PRODUCTION_RELATIVE = Path("hardware/mf1750_production_v1/production")
LOCAL_TEST_OUTPUT_RELATIVE = Path(".test-output")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ManifestError(ValueError):
    """Raised when a manifest plan or filesystem target violates the contract."""


def _require_local_path(path: Path, label: str) -> None:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise ManifestError(str(error)) from error


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"{label} must be a JSON object")
    return value


def _require_exact_keys(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise ManifestError(f"{label} has unknown keys: {sorted(unknown)}")
    if missing:
        raise ManifestError(f"{label} is missing keys: {sorted(missing)}")


def _require_nonempty_string(value: object, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum or any(character in result for character in "\r\n\x00"):
        raise ManifestError(f"{label} is invalid or too long")
    return result


def _validate_optional_timestamp(value: object, label: str) -> Optional[str]:
    if value is None:
        return None
    text = _require_nonempty_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ManifestError(f"{label} must include a timezone")
    return text


def _stat_fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Return identity and mutation-sensitive fields without access-time noise."""

    return (
        value.st_mode,
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _path_identity_fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return fields that are stable between Windows handle and path stat calls.

    Python 3.12 on Windows can briefly expose a cached path ``st_ctime_ns``
    that differs from two matching ``fstat`` results for the same unchanged
    handle.  Keep ctime in the before/after descriptor check, but exclude it
    from this final handle-to-path identity comparison to avoid a false
    mutation verdict.  Device, inode, size and mtime still detect replacement
    or ordinary writes.
    """

    return (
        value.st_mode,
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )


def _stable_file_identity(path: Path) -> tuple[int, str]:
    """Hash one unchanged regular file through a single open descriptor."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ManifestError(f"asset is not a regular file: {path}")
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        current = path.stat()
    except OSError as error:
        raise ManifestError(f"could not hash asset {path}: {error}") from error

    if (
        _stat_fingerprint(after) != _stat_fingerprint(before)
        or _path_identity_fingerprint(current)
        != _path_identity_fingerprint(after)
    ):
        raise ManifestError(f"asset changed while hashing: {path}")
    return before.st_size, digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one stable regular file without loading it into memory."""

    return _stable_file_identity(path)[1]


def _normalized_relative_posix_path(value: object, label: str) -> PurePosixPath:
    """Reject paths whose meaning can change between POSIX and Windows."""

    text = _require_nonempty_string(value, label, maximum=4096)
    if "\\" in text:
        raise ManifestError(
            f"{label} must be a normalized relative path "
            "(a relative POSIX path using only '/' separators)"
        )
    relative = PurePosixPath(text)
    windows = PureWindowsPath(text)
    if (
        relative.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or not relative.parts
        or ".." in relative.parts
        or text != relative.as_posix()
    ):
        raise ManifestError(
            f"{label} must be a normalized relative path "
            "(a relative POSIX path using only '/' separators)"
        )
    _require_local_path(Path(*relative.parts), label)
    return relative


def _resolve_asset(root: Path, relative_text: object, index: int) -> tuple[Path, str]:
    label = f"assets[{index}].path"
    relative_posix = _normalized_relative_posix_path(relative_text, label)
    relative = Path(*relative_posix.parts)
    _require_local_path(relative, label)
    candidate = (root / relative).resolve(strict=True)
    _require_local_path(candidate, f"resolved assets[{index}].path")
    try:
        normalized = candidate.relative_to(root).as_posix()
    except ValueError as error:
        raise ManifestError(f"assets[{index}].path resolves outside root") from error
    if not candidate.is_file():
        raise ManifestError(f"assets[{index}].path is not a regular file")
    return candidate, normalized


def build_manifest(
    plan: Mapping[str, Any],
    root: Path,
    *,
    created_at: Optional[str] = None,
) -> dict[str, Any]:
    """Validate a plan and hash only its explicitly listed files."""

    plan = _require_mapping(plan, "plan")
    _require_exact_keys(plan, PLAN_KEYS, "plan")
    run_id = _require_nonempty_string(plan["run_id"], "run_id", maximum=128)
    root_label = _require_nonempty_string(plan["root_label"], "root_label")
    hardware_tested = plan["hardware_tested"]
    if type(hardware_tested) is not bool:
        raise ManifestError("hardware_tested must be a boolean")
    assets_value = plan["assets"]
    if not isinstance(assets_value, list) or not assets_value:
        raise ManifestError("assets must be a non-empty JSON array")

    _require_local_path(root, "asset root")
    resolved_root = root.resolve(strict=True)
    _require_local_path(resolved_root, "resolved asset root")
    if not resolved_root.is_dir():
        raise ManifestError("root must be a directory")

    assets: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw_asset in enumerate(assets_value):
        asset = _require_mapping(raw_asset, f"assets[{index}]")
        _require_exact_keys(asset, ASSET_KEYS, f"assets[{index}]")
        role = _require_nonempty_string(asset["role"], f"assets[{index}].role")
        if role not in ROLES:
            raise ManifestError(f"assets[{index}].role is unsupported")
        asset_path, relative_path = _resolve_asset(resolved_root, asset["path"], index)
        if relative_path in seen_paths:
            raise ManifestError(f"duplicate asset path: {relative_path}")
        seen_paths.add(relative_path)
        captured_at = _validate_optional_timestamp(
            asset["captured_at"], f"assets[{index}].captured_at"
        )
        instrument_id_value = asset["instrument_id"]
        instrument_id = (
            None
            if instrument_id_value is None
            else _require_nonempty_string(
                instrument_id_value, f"assets[{index}].instrument_id"
            )
        )
        byte_count, digest = _stable_file_identity(asset_path)
        assets.append(
            {
                "role": role,
                "relative_path": relative_path,
                "bytes": byte_count,
                "sha256": digest,
                "captured_at": captured_at,
                "instrument_id": instrument_id,
            }
        )

    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _validate_optional_timestamp(timestamp, "created_at")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_id": run_id,
        "created_at": timestamp,
        "root_label": root_label,
        "hardware_tested": hardware_tested,
        "assets": assets,
    }


def validate_manifest_report(report: Mapping[str, Any]) -> None:
    """Reject report objects that do not satisfy the writer's strict contract."""

    report = _require_mapping(report, "report")
    _require_exact_keys(report, REPORT_KEYS, "report")
    if type(report["schema_version"]) is not int or report["schema_version"] != SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {SCHEMA_VERSION}")
    if report["kind"] != KIND:
        raise ManifestError(f"kind must be {KIND}")
    _require_nonempty_string(report["run_id"], "run_id", maximum=128)
    _require_nonempty_string(report["root_label"], "root_label")
    if type(report["hardware_tested"]) is not bool:
        raise ManifestError("hardware_tested must be a boolean")
    if _validate_optional_timestamp(report["created_at"], "created_at") is None:
        raise ManifestError("created_at cannot be null")

    assets = report["assets"]
    if not isinstance(assets, list) or not assets:
        raise ManifestError("assets must be a non-empty JSON array")
    seen_paths: set[str] = set()
    for index, raw_asset in enumerate(assets):
        asset = _require_mapping(raw_asset, f"assets[{index}]")
        _require_exact_keys(asset, REPORT_ASSET_KEYS, f"assets[{index}]")
        role = _require_nonempty_string(asset["role"], f"assets[{index}].role")
        if role not in ROLES:
            raise ManifestError(f"assets[{index}].role is unsupported")
        relative_text = _require_nonempty_string(
            asset["relative_path"], f"assets[{index}].relative_path", maximum=4096
        )
        _normalized_relative_posix_path(
            relative_text, f"assets[{index}].relative_path"
        )
        if relative_text in seen_paths:
            raise ManifestError(f"duplicate asset path: {relative_text}")
        seen_paths.add(relative_text)
        byte_count = asset["bytes"]
        if type(byte_count) is not int or byte_count < 0:
            raise ManifestError(f"assets[{index}].bytes must be a non-negative integer")
        digest = asset["sha256"]
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ManifestError(f"assets[{index}].sha256 must be lowercase SHA-256")
        _validate_optional_timestamp(asset["captured_at"], f"assets[{index}].captured_at")
        instrument_id = asset["instrument_id"]
        if instrument_id is not None:
            _require_nonempty_string(instrument_id, f"assets[{index}].instrument_id")


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_output_path(output: Path) -> Path:
    """Resolve one output while permanently guarding repository-owned evidence paths."""

    _require_local_path(output, "manifest output")
    lexical_output = Path(os.path.abspath(output))
    _require_local_path(lexical_output, "absolute manifest output")
    protected = (
        REPO_ROOT / FROZEN_PRODUCTION_RELATIVE,
        REPO_ROOT / LOCAL_TEST_OUTPUT_RELATIVE,
    )
    for protected_root in protected:
        if _is_within(lexical_output, Path(os.path.abspath(protected_root))):
            raise ManifestError(f"output cannot be written inside protected {protected_root.name}")

    output_parent = output.parent.resolve(strict=True)
    _require_local_path(output_parent, "resolved manifest output parent")
    resolved_output = output_parent / output.name
    _require_local_path(resolved_output, "resolved manifest output")
    for protected_root in protected:
        if _is_within(resolved_output, protected_root.resolve(strict=False)):
            raise ManifestError(f"output cannot be written inside protected {protected_root.name}")
    return resolved_output


def validate_plan_path(plan: Path) -> Path:
    """Resolve one local regular plan without following a leaf symlink."""

    if not isinstance(plan, Path):
        raise ManifestError("manifest plan must be a pathlib.Path")
    _require_local_path(plan, "manifest plan")
    lexical = plan.absolute()
    if any(part.casefold() == LOCAL_TEST_OUTPUT_RELATIVE.name for part in lexical.parts):
        raise ManifestError("manifest plan cannot be read from protected .test-output")
    if plan.is_symlink():
        raise ManifestError("manifest plan must not be a symbolic link")
    try:
        resolved = plan.resolve(strict=True)
    except OSError as error:
        raise ManifestError(f"could not resolve manifest plan: {error}") from error
    _require_local_path(resolved, "resolved manifest plan")
    if any(part.casefold() == LOCAL_TEST_OUTPUT_RELATIVE.name for part in resolved.parts):
        raise ManifestError("manifest plan cannot resolve inside protected .test-output")
    if not resolved.is_file():
        raise ManifestError("manifest plan must be a regular file")
    return resolved


def write_manifest(report: Mapping[str, Any], output: Path) -> None:
    """Validate and write once, refusing protected paths and existing targets."""

    validate_manifest_report(report)
    resolved_output = validate_output_path(output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    try:
        with resolved_output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        raise ManifestError("output already exists; this tool never overwrites evidence") from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="root containing named assets")
    parser.add_argument("--plan", required=True, type=Path, help="JSON plan with explicit assets")
    parser.add_argument("--output", required=True, type=Path, help="new manifest path")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        plan_path = validate_plan_path(args.plan)
        with plan_path.open("r", encoding="utf-8") as stream:
            plan = json.load(stream)
        report = build_manifest(plan, args.root)
        write_manifest(report, args.output)
    except (OSError, json.JSONDecodeError, ManifestError) as error:
        sys.stderr.write(f"manifest error: {error}\n")
        return 2
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
