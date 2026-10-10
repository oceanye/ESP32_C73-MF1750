#!/usr/bin/env python3
"""Build and deeply validate the corrected Stage-A V2 EC5 release.

This module performs local file operations only.  It requires both PlatformIO
BIN and ELF artifacts for U04 and U07, extracts the linked runtime digest
symbols from those ELFs, and binds that independently replayable report into
the release manifest.  It never uploads firmware or contacts a device.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_compiled_identity as compiled_identity  # noqa: E402
from tools import mf1750_ec5_stage_a_v2_identity as identity  # noqa: E402


SCHEMA_VERSION = 2
KIND = "mf1750-ec5-nodither-release-bundle"
IDENTITY_REVISION = identity.IDENTITY_REVISION
HASH_SCOPE = (
    "entire release manifest excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_FIRMWARE_BYTES = 32 * 1024 * 1024
MAX_ELF_BYTES = compiled_identity.MAX_ELF_BYTES
QUARANTINE_MARKER = "QUARANTINED_DO_NOT_USE.md"
SOURCE_PATHS = (
    "platformio.ini",
    "src/ec5_unknown_probe_main.cpp",
    "src/epd_config.h",
    "src/epd_driver.cpp",
    "src/epd_driver.h",
    "tools/mf1750_ec5_compiled_identity.py",
    "tools/mf1750_ec5_physical_once.py",
    "tools/mf1750_ec5_release.py",
    "tools/mf1750_ec5_stage_a_v2_identity.py",
)
PANEL_KEYS = frozenset({"model", "serial", "board_id", "pcb_revision"})
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")

DEVICE_CONTRACT = {
    "device_api_version": "MF1750_EC5_DEVICE_V3",
    "top_schema_version": 3,
    "driver_evidence_schema_version": 2,
    "identity_revision": "corrected-v2",
    "read_routes": [
        "/api/ec5/version",
        "/api/ec5/manifest",
        "/api/ec5/status",
        "/api/ec5/report",
    ],
    "arm_route": "/api/ec5/arm",
    "execute_route": "/api/ec5/execute",
    "arm_intent": "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION",
    "execute_intent": (
        "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION"
    ),
    "persistent_claim": True,
    "arm_required": True,
    "maximum_arm_posts": 1,
    "maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "j2_off_get_only_diagnostic_required_before_claim": True,
    "diagnostic_get_requests": 4,
    "diagnostic_post_requests": 0,
    "same_boot_nonce_required_for_visible_run": True,
    "legacy_nvs_never_written_or_cleared": True,
    "raw_frame_ingress": False,
    "startup_refresh": False,
}

SAFETY = {
    "classification": "EXPERIMENTAL_NOT_QUALIFIED",
    "hardware_authorized": False,
    "upload_performed": False,
    "device_io_performed": False,
    "visible_refresh_performed": False,
    "u07_requires_independent_post_u04_go": True,
    "custom_waveform_or_lut_used": False,
    "factory_otp_unchanged": True,
}

INCIDENT_LINEAGE = {
    "v1_release_canonical_sha256": (
        "adedbbdfe7ccacb3705149282689db46407261e834298c2b5c77dd285eb6d7dd"
    ),
    "v1_u04_action_id": (
        "bf2fcbcb29a35cf0a7915c67b48468aca26f7a35aef20e9ff68c9d60a37d0df5"
    ),
    "v1_u04_result_file_sha256": (
        "e1bf5659d6357dd5055fb7de8b447a9e23a07de9808a07a8e35687394ffdc954"
    ),
    "v1_u04_post_stop_readback_file_sha256": (
        "69e8009f8f63785d37e3ee82b0567f46a2ed9e503b8f5217bc6124eb4a8928e0"
    ),
    "v1_u04_forensic_supplement_canonical_sha256": (
        "30c27f69d952766bc158000267dac187eab5fa69e6b32b932f392f4a2ddc9b50"
    ),
    "v1_u04_forensic_supplement_file_sha256": (
        "660eac73d4d4b45c4ff98620106abceb89baa58e6d518d7fde410c140a0ec73e"
    ),
    "v1_host_claim_sha256": (
        "66b3d2c3ac0e01570346239bab9c759635fbc0125bc5a88a05bc90eacc37ce37"
    ),
    "v1_quarantine_marker_file_sha256": (
        "1ee694a037aae19e0bd7c8efda48dfc768c85131743472cf662b84039a7d0c3d"
    ),
    "display_sequence_started": False,
}

VARIANTS: dict[str, dict[str, Any]] = {
    candidate: deepcopy(dict(identity.VARIANTS[candidate]))
    for candidate in ("U04", "U07")
}


class EC5ReleaseError(ValueError):
    """Release construction or deep validation failed closed."""


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
        raise EC5ReleaseError(f"value is not canonical JSON data: {error}") from error


def sha256(payload: bytes | Mapping[str, Any]) -> str:
    data = payload if isinstance(payload, bytes) else canonical_json_bytes(payload)
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EC5ReleaseError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise EC5ReleaseError(f"{label} must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise EC5ReleaseError(f"{label} has an invalid size")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EC5ReleaseError(f"could not read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise EC5ReleaseError(f"{label} changed while it was read")
    return payload


def read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    payload = _read_regular(path, label=label, maximum=MAX_JSON_BYTES)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EC5ReleaseError(f"{label} contains forbidden number {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EC5ReleaseError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise EC5ReleaseError(f"{label} root must be an object")
    return value


def _validate_panel(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != PANEL_KEYS:
        raise EC5ReleaseError("panel identity fields differ from contract")
    result: dict[str, str] = {}
    for key in ("model", "serial", "board_id", "pcb_revision"):
        field = value[key]
        if (
            not isinstance(field, str)
            or not field
            or field != field.strip()
            or len(field) > 256
            or any(ord(character) < 0x20 for character in field)
        ):
            raise EC5ReleaseError(f"panel identity {key} is malformed")
        result[key] = field
    return result


def _git_text(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise EC5ReleaseError(f"git {' '.join(arguments)} failed")
    return result.stdout


def _source_snapshot() -> dict[str, Any]:
    sources = []
    for relative in SOURCE_PATHS:
        payload = _read_regular(
            REPO_ROOT / relative,
            label=f"source {relative}",
            maximum=8 * 1024 * 1024,
        )
        sources.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256(payload)}
        )
    head = _git_text(["rev-parse", "HEAD"]).strip()
    if COMMIT_RE.fullmatch(head) is None:
        raise EC5ReleaseError("Git HEAD is not a full lowercase commit")
    status = _git_text(["status", "--porcelain=v1", "--untracked-files=all"])
    status_payload = status.encode("utf-8")
    return {
        "git_head": head,
        "git_dirty": bool(status),
        "git_status_sha256": sha256(status_payload),
        "git_status_line_count": len(status.splitlines()),
        "relevant_sources": sources,
    }


def _validate_binary(payload: bytes, variant: Mapping[str, Any]) -> None:
    if not payload or len(payload) > MAX_FIRMWARE_BYTES:
        raise EC5ReleaseError("firmware size is invalid")
    nvs = variant["nvs_contract"]
    required = (
        variant["build_tag"],
        variant["test_id"],
        variant["action_id"],
        variant["frame_sha256"],
        variant["dtm_sha256"],
        variant["identity_revision"],
        variant["device_api_version"],
        nvs["legacy"]["namespace"],
        nvs["legacy"]["key"],
        nvs["active"]["namespace"],
        nvs["active"]["key"],
    )
    for token in required:
        if str(token).encode("ascii") not in payload:
            raise EC5ReleaseError(f"firmware omits frozen token {token}")

    other_id = "U07" if variant["candidate_id"] == "U04" else "U04"
    other = VARIANTS[other_id]
    for token in (other["build_tag"], other["test_id"], other["action_id"]):
        if str(token).encode("ascii") in payload:
            raise EC5ReleaseError("firmware contains the other candidate identity")
    for token in identity.V1_BINARY_IDENTITY_TOKENS:
        if token.encode("ascii") in payload:
            raise EC5ReleaseError("firmware contains a quarantined V1 identity")


def _compiled_identity_report(u04_elf: Path, u07_elf: Path) -> dict[str, Any]:
    try:
        report = compiled_identity.validate_pair(Path(u04_elf), Path(u07_elf))
    except compiled_identity.CompiledIdentityError as error:
        raise EC5ReleaseError(f"compiled ELF identity gate failed: {error}") from error
    return json.loads(canonical_json_bytes(report).decode("utf-8"))


def _verify_elf_payloads(
    report: Mapping[str, Any], elf_payloads: Mapping[str, bytes]
) -> None:
    variants = report.get("variants")
    if not isinstance(variants, Mapping) or set(variants) != {"U04", "U07"}:
        raise EC5ReleaseError("compiled identity report variants are malformed")
    for candidate in ("U04", "U07"):
        entry = variants[candidate]
        if not isinstance(entry, Mapping):
            raise EC5ReleaseError("compiled identity report variant is malformed")
        payload = elf_payloads[candidate]
        if entry.get("elf_bytes") != len(payload) or entry.get("elf_sha256") != sha256(
            payload
        ):
            raise EC5ReleaseError(
                f"{candidate} ELF changed after compiled identity validation"
            )


_VARIANT_VALUE_KEYS = (
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
)


def _variant_manifest(
    candidate_id: str, binary: bytes, elf: bytes
) -> dict[str, Any]:
    expected = VARIANTS[candidate_id]
    _validate_binary(binary, expected)
    return {
        key: deepcopy(expected[key]) for key in _VARIANT_VALUE_KEYS
    } | {
        "firmware": {
            "file": expected["firmware_file"],
            "bytes": len(binary),
            "sha256": sha256(binary),
        },
        "elf": {
            "file": expected["elf_file"],
            "bytes": len(elf),
            "sha256": sha256(elf),
        },
        "build_command": ["pio", "run", "-e", expected["environment"]],
    }


def build_release(
    *,
    panel_file: Path,
    u04_binary: Path,
    u07_binary: Path,
    u04_elf: Path,
    u07_elf: Path,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, dict[str, bytes]]]:
    """Construct an in-memory V2 release after replaying the two ELF gates."""

    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise EC5ReleaseError("created_at must be RFC3339") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise EC5ReleaseError("created_at must include a UTC offset")
    panel = _validate_panel(read_json(panel_file, label="panel identity"))
    binaries = {
        "U04": _read_regular(
            u04_binary, label="U04 firmware", maximum=MAX_FIRMWARE_BYTES
        ),
        "U07": _read_regular(
            u07_binary, label="U07 firmware", maximum=MAX_FIRMWARE_BYTES
        ),
    }
    report = _compiled_identity_report(u04_elf, u07_elf)
    elfs = {
        "U04": _read_regular(u04_elf, label="U04 ELF", maximum=MAX_ELF_BYTES),
        "U07": _read_regular(u07_elf, label="U07 ELF", maximum=MAX_ELF_BYTES),
    }
    _verify_elf_payloads(report, elfs)
    artifacts = {
        candidate: {"firmware": binaries[candidate], "elf": elfs[candidate]}
        for candidate in ("U04", "U07")
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "identity_revision": IDENTITY_REVISION,
        "created_at": created_at,
        "panel": panel,
        "source_snapshot": _source_snapshot(),
        "device_contract": deepcopy(DEVICE_CONTRACT),
        "incident_lineage": deepcopy(INCIDENT_LINEAGE),
        "compiled_identity_report": report,
        "variants": {
            candidate: _variant_manifest(
                candidate, binaries[candidate], elfs[candidate]
            )
            for candidate in ("U04", "U07")
        },
        "safety": deepcopy(SAFETY),
    }
    manifest = {
        **unsigned,
        "integrity": {"canonical_sha256": sha256(unsigned), "scope": HASH_SCOPE},
    }
    return manifest, artifacts


def _validate_exact_keys(
    value: Any, expected: set[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise EC5ReleaseError(f"{label} fields differ from contract")
    return value


def _reject_quarantine_marker(bundle_dir: Path) -> None:
    marker = bundle_dir / QUARANTINE_MARKER
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise EC5ReleaseError(f"could not inspect release quarantine marker: {error}") from error
    raise EC5ReleaseError("corrected V2 release bundle must not contain a quarantine marker")


def _validate_source_snapshot(value: Any) -> None:
    source = _validate_exact_keys(
        value,
        {
            "git_head",
            "git_dirty",
            "git_status_sha256",
            "git_status_line_count",
            "relevant_sources",
        },
        "source snapshot",
    )
    if (
        COMMIT_RE.fullmatch(str(source["git_head"])) is None
        or type(source["git_dirty"]) is not bool
    ):
        raise EC5ReleaseError("source Git identity is malformed")
    if SHA_RE.fullmatch(str(source["git_status_sha256"])) is None:
        raise EC5ReleaseError("source status digest is malformed")
    if (
        isinstance(source["git_status_line_count"], bool)
        or not isinstance(source["git_status_line_count"], int)
        or source["git_status_line_count"] < 0
    ):
        raise EC5ReleaseError("source status line count is malformed")
    listed_sources = source["relevant_sources"]
    if not isinstance(listed_sources, list) or [
        item.get("path") if isinstance(item, Mapping) else None
        for item in listed_sources
    ] != list(SOURCE_PATHS):
        raise EC5ReleaseError("relevant source list differs")
    for item in listed_sources:
        if not isinstance(item, Mapping) or set(item) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise EC5ReleaseError("source entry is malformed")
        payload = _read_regular(
            REPO_ROOT / item["path"],
            label=f"source {item['path']}",
            maximum=8 * 1024 * 1024,
        )
        if item["bytes"] != len(payload) or item["sha256"] != sha256(payload):
            raise EC5ReleaseError(f"source {item['path']} differs from release")


def _validate_variant(
    bundle_dir: Path, candidate_id: str, value: Any
) -> tuple[bytes, Path]:
    expected = VARIANTS[candidate_id]
    expected_keys = set(_VARIANT_VALUE_KEYS) | {
        "firmware",
        "elf",
        "build_command",
    }
    variant = _validate_exact_keys(value, expected_keys, f"variant {candidate_id}")
    for key in _VARIANT_VALUE_KEYS:
        if variant[key] != expected[key]:
            raise EC5ReleaseError(f"variant {candidate_id} field {key} differs")
    preimage = variant["action_identity_preimage"]
    if identity.derive_action_id(preimage) != variant["action_id"]:
        raise EC5ReleaseError(f"variant {candidate_id} action preimage hash differs")
    if variant["build_command"] != [
        "pio",
        "run",
        "-e",
        expected["environment"],
    ]:
        raise EC5ReleaseError("build command differs")

    firmware = _validate_exact_keys(
        variant["firmware"],
        {"file", "bytes", "sha256"},
        f"{candidate_id} firmware",
    )
    if (
        firmware["file"] != expected["firmware_file"]
        or SHA_RE.fullmatch(str(firmware["sha256"])) is None
    ):
        raise EC5ReleaseError("firmware identity is malformed")
    binary = _read_regular(
        bundle_dir / firmware["file"],
        label=f"{candidate_id} firmware",
        maximum=MAX_FIRMWARE_BYTES,
    )
    if firmware["bytes"] != len(binary) or firmware["sha256"] != sha256(binary):
        raise EC5ReleaseError(f"{candidate_id} firmware bytes differ")
    _validate_binary(binary, expected)

    elf = _validate_exact_keys(
        variant["elf"], {"file", "bytes", "sha256"}, f"{candidate_id} ELF"
    )
    if (
        elf["file"] != expected["elf_file"]
        or SHA_RE.fullmatch(str(elf["sha256"])) is None
    ):
        raise EC5ReleaseError("ELF identity is malformed")
    elf_path = bundle_dir / elf["file"]
    elf_payload = _read_regular(
        elf_path, label=f"{candidate_id} ELF", maximum=MAX_ELF_BYTES
    )
    if elf["bytes"] != len(elf_payload) or elf["sha256"] != sha256(elf_payload):
        raise EC5ReleaseError(f"{candidate_id} ELF bytes differ")
    return elf_payload, elf_path


def validate_release(bundle_dir: Path) -> dict[str, Any]:
    """Deeply replay a V2 release, including its copied ELF symbol gate."""

    bundle_dir = Path(bundle_dir)
    if bundle_dir.is_symlink() or not bundle_dir.is_dir():
        raise EC5ReleaseError("bundle must be a local directory")
    _reject_quarantine_marker(bundle_dir)
    manifest = read_json(bundle_dir / "release-manifest.json", label="release manifest")
    root = _validate_exact_keys(
        manifest,
        {
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
        },
        "release manifest",
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != KIND
        or root["identity_revision"] != IDENTITY_REVISION
    ):
        raise EC5ReleaseError("release manifest type or identity revision is unsupported")
    try:
        timestamp = datetime.fromisoformat(str(root["created_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise EC5ReleaseError("release created_at is invalid") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise EC5ReleaseError("release created_at lacks a UTC offset")
    _validate_panel(root["panel"])
    if root["device_contract"] != DEVICE_CONTRACT:
        raise EC5ReleaseError("device contract differs from frozen contract")
    if root["incident_lineage"] != INCIDENT_LINEAGE:
        raise EC5ReleaseError("incident lineage differs from the frozen V1 evidence")
    if root["safety"] != SAFETY:
        raise EC5ReleaseError("release safety declaration differs")
    _validate_source_snapshot(root["source_snapshot"])

    variants = _validate_exact_keys(root["variants"], {"U04", "U07"}, "variants")
    elf_payloads: dict[str, bytes] = {}
    elf_paths: dict[str, Path] = {}
    for candidate in ("U04", "U07"):
        elf_payloads[candidate], elf_paths[candidate] = _validate_variant(
            bundle_dir, candidate, variants[candidate]
        )
    replayed_report = _compiled_identity_report(elf_paths["U04"], elf_paths["U07"])
    _verify_elf_payloads(replayed_report, elf_payloads)
    if root["compiled_identity_report"] != replayed_report:
        raise EC5ReleaseError("compiled identity report differs from copied ELF replay")

    integrity = _validate_exact_keys(
        root["integrity"], {"canonical_sha256", "scope"}, "integrity"
    )
    unsigned = dict(root)
    unsigned.pop("integrity")
    if (
        integrity["scope"] != HASH_SCOPE
        or integrity["canonical_sha256"] != sha256(unsigned)
    ):
        raise EC5ReleaseError("release integrity is invalid")
    return json.loads(canonical_json_bytes(root).decode("utf-8"))


def publish_release(
    output: Path,
    manifest: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, bytes]],
) -> None:
    """Publish BIN, ELF, and manifest without altering any V1 evidence."""

    if set(artifacts) != {"U04", "U07"}:
        raise EC5ReleaseError("release artifacts must contain exactly U04 and U07")
    try:
        parent = output.parent.resolve(strict=True)
    except OSError as error:
        raise EC5ReleaseError(f"release parent is unavailable: {error}") from error
    destination = parent / output.name
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
        for candidate in ("U04", "U07"):
            candidate_artifacts = artifacts[candidate]
            if set(candidate_artifacts) != {"firmware", "elf"}:
                raise EC5ReleaseError(f"{candidate} release artifacts differ")
            for kind, file_key in (("firmware", "firmware_file"), ("elf", "elf_file")):
                with (destination / VARIANTS[candidate][file_key]).open("xb") as stream:
                    stream.write(candidate_artifacts[kind])
                    stream.flush()
                    os.fsync(stream.fileno())
        with (destination / "release-manifest.json").open("xb") as stream:
            stream.write(canonical_json_bytes(manifest))
            stream.flush()
            os.fsync(stream.fileno())
    except EC5ReleaseError:
        raise
    except OSError as error:
        raise EC5ReleaseError(f"could not publish release: {error}") from error
    validate_release(destination)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="publish a new offline V2 release")
    build.add_argument("--panel", type=Path, required=True)
    build.add_argument("--u04-binary", type=Path, required=True)
    build.add_argument("--u07-binary", type=Path, required=True)
    build.add_argument("--u04-elf", type=Path, required=True)
    build.add_argument("--u07-elf", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--created-at", required=True)
    validate = subparsers.add_parser("validate", help="deeply validate a V2 release")
    validate.add_argument("--bundle", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            manifest, artifacts = build_release(
                panel_file=args.panel,
                u04_binary=args.u04_binary,
                u07_binary=args.u07_binary,
                u04_elf=args.u04_elf,
                u07_elf=args.u07_elf,
                created_at=args.created_at,
            )
            publish_release(args.output, manifest, artifacts)
            print(
                json.dumps(
                    {
                        "bundle": str(args.output),
                        "manifest_sha256": manifest["integrity"][
                            "canonical_sha256"
                        ],
                    },
                    sort_keys=True,
                )
            )
        else:
            manifest = validate_release(args.bundle)
            print(
                json.dumps(
                    {
                        "valid": True,
                        "manifest_sha256": manifest["integrity"][
                            "canonical_sha256"
                        ],
                    },
                    sort_keys=True,
                )
            )
    except EC5ReleaseError as error:
        print(f"EC5 release error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
