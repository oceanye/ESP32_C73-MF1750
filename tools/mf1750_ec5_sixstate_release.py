#!/usr/bin/env python3
"""Build and deeply validate an immutable EC5 six-state Stage-B release.

The bundle contains two isolated firmware binaries, both complete offline asset
directories, the exact physical panel identity, the safety-relevant source
snapshot, and the nine compiled action identities for each candidate.  It is
offline-only and refuses to overwrite any destination.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_sixstate_nodither as assets  # noqa: E402
from tools import mf1750_ec5_sixstate_physical_once as runner  # noqa: E402


MAX_FILE_BYTES = 32 * 1024 * 1024
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class SixStateReleaseError(RuntimeError):
    """Release construction or validation failed closed."""


def _read(path: Path, *, label: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise SixStateReleaseError(f"{label} must be a non-symlink regular file")
        before = path.stat()
        if before.st_size > maximum:
            raise SixStateReleaseError(f"{label} exceeds its size limit")
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise SixStateReleaseError(f"cannot read {label}: {error}") from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise SixStateReleaseError(f"{label} changed while being read")
    return payload


def _json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        return runner._decode_json(_read(path, label=label), label=label)
    except runner.SixStatePhysicalError as error:
        raise SixStateReleaseError(str(error)) from error


def _git(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SixStateReleaseError(f"git {' '.join(arguments)} failed")
    return result.stdout


def source_snapshot() -> dict[str, Any]:
    relevant = []
    for relative in runner.SOURCE_PATHS:
        payload = _read(REPO_ROOT / relative, label=f"source {relative}")
        relevant.append({"path": relative, "bytes": len(payload), "sha256": runner.sha256(payload)})
    head = _git(("rev-parse", "HEAD")).strip()
    if _COMMIT_RE.fullmatch(head) is None:
        raise SixStateReleaseError("Git HEAD is not a full lowercase commit")
    status = _git(("status", "--porcelain=v1", "--untracked-files=all"))
    return {
        "git_head": head,
        "git_dirty": bool(status),
        "git_status_sha256": runner.sha256(status.encode("utf-8")),
        "git_status_line_count": len(status.splitlines()),
        "relevant_sources": relevant,
    }


def _panel(path: Path) -> dict[str, str]:
    try:
        return runner._validate_panel(_json(path, label="panel identity"), label="panel identity")
    except runner.SixStatePhysicalError as error:
        raise SixStateReleaseError(str(error)) from error


def _asset_payloads(candidate_id: str, manifest_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    expected = runner.FROZEN_VARIANTS[candidate_id]
    try:
        report = assets.validate_bundle(manifest_path)
    except Exception as error:
        raise SixStateReleaseError(f"{candidate_id} asset validation failed: {error}") from error
    if report["candidate_id"] != candidate_id or report["manifest_payload_sha256"] != expected["asset_manifest_payload_sha256"]:
        raise SixStateReleaseError(f"{candidate_id} asset identity differs from frozen contract")
    manifest_payload = _read(manifest_path, label=f"{candidate_id} asset manifest")
    root = _json(manifest_path, label=f"{candidate_id} asset manifest")
    files: dict[str, bytes] = {}
    for frame in root["frames"].values():
        for key in ("raw_file", "preview_file"):
            name = frame[key]
            files[f"assets/{candidate_id}/{name}"] = _read(
                manifest_path.parent / name, label=f"{candidate_id} asset {name}"
            )
    release_name = f"assets/{candidate_id}/{manifest_path.name}"
    files[release_name] = manifest_payload
    block = {
        "candidate_id": candidate_id,
        "manifest_file": release_name,
        "manifest_bytes": len(manifest_payload),
        "manifest_sha256": runner.sha256(manifest_payload),
        "manifest_payload_sha256": report["manifest_payload_sha256"],
    }
    return block, files


def build_release(
    *,
    panel_file: Path,
    u04_binary: Path,
    u07_binary: Path,
    u04_asset_manifest: Path,
    u07_asset_manifest: Path,
    created_at: str,
    _source_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return a complete manifest and relative file payload mapping."""

    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise SixStateReleaseError("created_at must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SixStateReleaseError("created_at must include a timezone")
    panel = _panel(Path(panel_file))
    binary_paths = {"U04": Path(u04_binary), "U07": Path(u07_binary)}
    asset_paths = {"U04": Path(u04_asset_manifest), "U07": Path(u07_asset_manifest)}
    payloads: dict[str, bytes] = {}
    asset_blocks: dict[str, Any] = {}
    variants: dict[str, Any] = {}
    for candidate_id in ("U04", "U07"):
        expected = runner.FROZEN_VARIANTS[candidate_id]
        binary = _read(binary_paths[candidate_id], label=f"{candidate_id} firmware")
        try:
            runner._validate_binary(binary, candidate_id)
        except runner.SixStatePhysicalError as error:
            raise SixStateReleaseError(f"{candidate_id} binary validation failed: {error}") from error
        firmware_file = expected["firmware_file"]
        payloads[firmware_file] = binary
        asset_block, asset_files = _asset_payloads(candidate_id, asset_paths[candidate_id])
        asset_blocks[candidate_id] = asset_block
        payloads.update(asset_files)
        variants[candidate_id] = {
            "candidate_id": candidate_id,
            "candidate_code": expected["candidate_code"],
            "environment": expected["environment"],
            "build_tag": expected["build_tag"],
            "test_id": expected["test_id"],
            "layout_id": expected["layout_id"],
            "firmware": {"file": firmware_file, "bytes": len(binary), "sha256": runner.sha256(binary)},
            "build_command": ["pio", "run", "-e", expected["environment"]],
            "asset_manifest_sha256": asset_block["manifest_sha256"],
            "actions": list(runner.expected_actions(candidate_id)),
        }
    unsigned = {
        "schema_version": runner.SCHEMA_VERSION,
        "kind": runner.RELEASE_KIND,
        "created_at": created_at,
        "panel": panel,
        "source_snapshot": dict(_source_snapshot) if _source_snapshot is not None else source_snapshot(),
        "device_contract": dict(runner.DEVICE_CONTRACT),
        "assets": asset_blocks,
        "variants": variants,
        "safety": {
            "classification": "EXPERIMENTAL_NOT_QUALIFIED",
            "hardware_authorized": False,
            "upload_performed": False,
            "device_io_performed": False,
            "visible_refresh_performed": False,
            "dithering_present": False,
            "spatial_mixing_present": False,
            "custom_waveform_or_lut_used": False,
            "factory_otp_unchanged": True,
            "u07_requires_stage_a_pass_and_recovery": True,
            "target_observation_required_before_white": True,
            "white_recovery_required_before_next_primer": True,
        },
    }
    manifest = runner._seal(unsigned)
    return manifest, payloads


def publish_release(output: Path, manifest: Mapping[str, Any], payloads: Mapping[str, bytes]) -> Path:
    """Publish exclusively and replay the result for both candidates."""

    output = Path(output)
    try:
        parent = output.parent.resolve(strict=True)
        destination = parent / output.name
        destination.mkdir(mode=0o700, exist_ok=False)
        for relative_name in sorted(payloads):
            relative = Path(relative_name)
            if relative.is_absolute() or ".." in relative.parts:
                raise SixStateReleaseError("release payload path is unsafe")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payloads[relative_name])
                stream.flush()
                os.fsync(stream.fileno())
        manifest_path = destination / "release-manifest.json"
        with manifest_path.open("xb") as stream:
            stream.write(runner.canonical_json_bytes(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise SixStateReleaseError(f"refusing to overwrite release destination {output}") from error
    except OSError as error:
        raise SixStateReleaseError(f"cannot publish release: {error}") from error
    return manifest_path


def validate_release(
    release_file: Path,
    *,
    panel_file: Path,
    source_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Replay all files, sources, panel, assets, binaries and both variants."""

    try:
        contexts = {
            candidate: runner.load_release(
                Path(release_file), candidate, source_root=Path(source_root), panel_file=Path(panel_file)
            )
            for candidate in ("U04", "U07")
        }
    except runner.SixStatePhysicalError as error:
        raise SixStateReleaseError(str(error)) from error
    if contexts["U04"].binary_sha256 == contexts["U07"].binary_sha256:
        raise SixStateReleaseError("candidate firmware binaries are not isolated")
    return {
        "valid": True,
        "kind": runner.RELEASE_KIND,
        "release_canonical_sha256": contexts["U04"].release_canonical_sha256,
        "panel": dict(contexts["U04"].panel),
        "variants": {
            candidate: {
                "binary_sha256": contexts[candidate].binary_sha256,
                "asset_manifest_sha256": contexts[candidate].asset_file_sha256,
                "action_count": len(contexts[candidate].actions),
            }
            for candidate in ("U04", "U07")
        },
        "hardware_actions_performed": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", allow_abbrev=False)
    build.add_argument("--panel", type=Path, required=True)
    build.add_argument("--u04-binary", type=Path, required=True)
    build.add_argument("--u07-binary", type=Path, required=True)
    build.add_argument("--u04-assets", type=Path, required=True)
    build.add_argument("--u07-assets", type=Path, required=True)
    build.add_argument("--created-at", required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--release", type=Path, required=True)
    validate.add_argument("--panel", type=Path, required=True)
    validate.add_argument("--source-root", type=Path, default=REPO_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest, payloads = build_release(
                panel_file=args.panel,
                u04_binary=args.u04_binary,
                u07_binary=args.u07_binary,
                u04_asset_manifest=args.u04_assets,
                u07_asset_manifest=args.u07_assets,
                created_at=args.created_at,
            )
            path = publish_release(args.output, manifest, payloads)
            output = validate_release(path, panel_file=args.panel)
            output["release"] = str(path)
        else:
            output = validate_release(args.release, panel_file=args.panel, source_root=args.source_root)
    except SixStateReleaseError as error:
        print(f"EC5 six-state release error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
