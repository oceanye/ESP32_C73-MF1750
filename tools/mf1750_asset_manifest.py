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
import sys
from typing import Any, Mapping, Optional, Sequence


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


def sha256_file(path: Path) -> str:
    """Hash one regular file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_asset(root: Path, relative_text: object, index: int) -> tuple[Path, str]:
    relative = Path(_require_nonempty_string(relative_text, f"assets[{index}].path", maximum=4096))
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ManifestError(f"assets[{index}].path must be a relative path without '..'")
    candidate = (root / relative).resolve(strict=True)
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

    resolved_root = root.resolve(strict=True)
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
        assets.append(
            {
                "role": role,
                "relative_path": relative_path,
                "bytes": asset_path.stat().st_size,
                "sha256": sha256_file(asset_path),
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
        relative = PurePosixPath(relative_text)
        windows_path = PureWindowsPath(relative_text)
        if (
            relative.is_absolute()
            or bool(windows_path.drive)
            or bool(windows_path.root)
            or ".." in relative.parts
            or relative_text != relative.as_posix()
        ):
            raise ManifestError(
                f"assets[{index}].relative_path must be a normalized relative POSIX path"
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

    lexical_output = Path(os.path.abspath(output))
    protected = (
        REPO_ROOT / FROZEN_PRODUCTION_RELATIVE,
        REPO_ROOT / LOCAL_TEST_OUTPUT_RELATIVE,
    )
    for protected_root in protected:
        if _is_within(lexical_output, Path(os.path.abspath(protected_root))):
            raise ManifestError(f"output cannot be written inside protected {protected_root.name}")

    output_parent = output.parent.resolve(strict=True)
    resolved_output = output_parent / output.name
    for protected_root in protected:
        if _is_within(resolved_output, protected_root.resolve(strict=False)):
            raise ManifestError(f"output cannot be written inside protected {protected_root.name}")
    return resolved_output


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
        with args.plan.open("r", encoding="utf-8") as stream:
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
