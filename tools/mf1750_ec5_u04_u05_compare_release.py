#!/usr/bin/env python3
"""Build the sealed offline release for the fixed U04-vs-U05 comparison."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_compiled_identity as elf_reader  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_identity as identity  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_prerequisites as prereq  # noqa: E402
from tools import mf1750_ec5_u04_u05_compare_preview as preview  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u04-u05-compare-release"
HASH_SCOPE = (
    "entire release manifest excluding integrity; canonical UTF-8 JSON sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MANIFEST_FILE = "release-manifest.json"
QUARANTINE_MARKER = "QUARANTINED_DO_NOT_USE.md"
OBSOLETE_ACTION_ID = (
    "45f212f9ac38b7a9117e312868abdad8cc67e95329698924cd08743b36609897"
)
SOURCE_PATHS = (
    "platformio.ini",
    "src/ec5_u04_u05_compare_main.cpp",
    "src/epd_config.h",
    "src/epd_driver.cpp",
    "src/epd_driver.h",
    "tools/mf1750_ec5_compiled_identity.py",
    "tools/mf1750_ec5_u04_u05_compare_identity.py",
    "tools/mf1750_ec5_u04_u05_compare_prerequisites.py",
    "tools/mf1750_ec5_u04_u05_compare_preview.py",
    "tools/mf1750_ec5_u04_u05_compare_release.py",
    "tools/mf1750_ec5_u04_u05_compare_physical_once.py",
)
FRAME_SYMBOL = "_ZN12_GLOBAL__N_1L16EC5_FRAME_SHA256E"
CS1_SYMBOL = "_ZN12_GLOBAL__N_1L18EC5_CS1_DTM_SHA256E"
CS2_SYMBOL = "_ZN12_GLOBAL__N_1L18EC5_CS2_DTM_SHA256E"
DEVICE_CONTRACT = {
    "device_api_version": identity.DEVICE_API_VERSION,
    "top_schema_version": identity.TOP_SCHEMA_VERSION,
    "driver_evidence_schema_version": identity.DRIVER_EVIDENCE_SCHEMA_VERSION,
    "identity_revision": identity.IDENTITY_REVISION,
    "read_routes": [
        "/api/ec5/version",
        "/api/ec5/manifest",
        "/api/ec5/status",
        "/api/ec5/report",
    ],
    "arm_route": "/api/ec5/arm",
    "execute_route": "/api/ec5/execute",
    "j2_off_get_only_diagnostic_required_before_claim": True,
    "diagnostic_get_requests": 4,
    "diagnostic_post_requests": 0,
    "same_boot_nonce_required_for_visible_run": True,
    "claim_created_before_first_post": True,
    "maximum_arm_posts": 1,
    "maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "raw_frame_ingress": False,
    "startup_refresh": False,
}
SAFETY = {
    "classification": "EXPERIMENTAL_TECHNICAL_COMPARISON_NOT_QUALIFIED",
    "hardware_authorized": False,
    "upload_performed": False,
    "device_io_performed": False,
    "visible_refresh_performed": False,
    "factory_otp_unchanged": True,
    "custom_waveform_or_lut_used": False,
    "dithering_present": False,
    "spatial_mixing_present": False,
    "thirty_minute_u04_hold_is_not_a_comparison_gate": True,
}


class CompareReleaseError(ValueError):
    """Comparison release construction or replay failed closed."""


def canonical_json_bytes(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def sha256(payload: bytes | Mapping[str, Any]) -> str:
    data = payload if isinstance(payload, bytes) else canonical_json_bytes(payload)
    return hashlib.sha256(data).hexdigest()


def _read(path: Path, *, label: str, maximum: int = 64 * 1024 * 1024) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise CompareReleaseError(f"{label} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise CompareReleaseError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise CompareReleaseError(f"could not read {label}: {error}") from error
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise CompareReleaseError(f"{label} changed while read")
    return payload


def _json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_read(path, label=label).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompareReleaseError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise CompareReleaseError(f"{label} root must be an object")
    return value


def _panel(panel_file: Path) -> dict[str, str]:
    value = _json(panel_file, label="panel identity")
    if set(value) != {"model", "serial", "board_id", "pcb_revision"}:
        raise CompareReleaseError("panel fields differ")
    result = {}
    for key in ("model", "serial", "board_id", "pcb_revision"):
        field = value[key]
        if not isinstance(field, str) or not field or field != field.strip():
            raise CompareReleaseError(f"panel {key} is invalid")
        result[key] = field
    return result


def _source_snapshot() -> list[dict[str, Any]]:
    result = []
    for relative in SOURCE_PATHS:
        payload = _read(REPO_ROOT / relative, label=f"source {relative}")
        result.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256(payload)}
        )
    return result


def _validate_firmware(payload: bytes) -> None:
    required_tokens = (
        identity.BUILD_TAG,
        identity.TEST_ID,
        identity.FROZEN_ACTION_ID,
        identity.FRAME_SHA256,
        identity.CS1_DTM_SHA256,
        identity.CS2_DTM_SHA256,
        identity.LAYOUT_ID,
        identity.DEVICE_API_VERSION,
        identity.LEGACY_NVS_NAMESPACE,
        identity.LEGACY_NVS_KEY,
        identity.ACTIVE_NVS_NAMESPACE,
        identity.ACTIVE_NVS_KEY,
    )
    for token in required_tokens:
        if token.encode("ascii") not in payload:
            raise CompareReleaseError(f"firmware omits frozen token {token}")
    if OBSOLETE_ACTION_ID.encode("ascii") in payload:
        raise CompareReleaseError("firmware contains obsolete horizontal action")


def compiled_identity_report(elf_file: Path) -> dict[str, Any]:
    try:
        resolved, payload = elf_reader._read_regular(  # noqa: SLF001
            Path(elf_file), label="comparison ELF"
        )
        image = elf_reader.Elf32Image(payload, label=str(resolved))
        symbols = {
            "frame_sha256": image.runtime_symbol(FRAME_SYMBOL),
            "cs1_dtm_sha256": image.runtime_symbol(CS1_SYMBOL),
            "cs2_dtm_sha256": image.runtime_symbol(CS2_SYMBOL),
        }
    except elf_reader.CompiledIdentityError as error:
        raise CompareReleaseError(f"compiled identity gate failed: {error}") from error
    wanted = {
        "frame_sha256": bytes.fromhex(identity.FRAME_SHA256),
        "cs1_dtm_sha256": bytes.fromhex(identity.CS1_DTM_SHA256),
        "cs2_dtm_sha256": bytes.fromhex(identity.CS2_DTM_SHA256),
    }
    for key, symbol in symbols.items():
        if symbol.payload != wanted[key]:
            raise CompareReleaseError(f"compiled {key} differs from frozen fixture")
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-u04-u05-compare-compiled-identity",
        "elf_bytes": len(payload),
        "elf_sha256": sha256(payload),
        "symbols": {
            key: {
                "name": symbol.name,
                "size": symbol.size,
                "section": symbol.section.name,
                "file_offset": symbol.file_offset,
                "sha256_bytes": symbol.payload.hex(),
            }
            for key, symbol in symbols.items()
        },
    }


def load_prerequisites(
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
) -> dict[str, Any]:
    try:
        context, u04 = prereq.load_u04_result_binding(
            release_file=corrected_release_file,
            result_file=u04_result_file,
            panel_file=panel_file,
            claim_registry=candidate_claim_registry,
        )
        short_hold = prereq.load_short_hold_boundary(
            short_hold_file, u04_result_file=u04_result_file
        )
        white = prereq.load_white_result_binding(
            context=context,
            release_file=corrected_release_file,
            u04_result_file=u04_result_file,
            white_result_file=white_result_file,
            panel_file=panel_file,
            rc2g_binary_file=rc2g_binary_file,
            candidate_claim_registry=candidate_claim_registry,
            white_claim_registry=white_claim_registry,
        )
        white_observation = prereq.load_white_manual_observation(
            white_observation_file, white_result_file=white_result_file
        )
    except prereq.ComparePrerequisiteError as error:
        raise CompareReleaseError(f"prerequisite replay failed: {error}") from error
    return {
        "corrected_u04": u04,
        "operator_short_hold_skip_boundary": short_hold,
        "after_u04_white_recovery": white,
        "after_u04_white_manual_observation": white_observation,
        "policy": {
            "deep_validated_u04_result_and_claim_required": True,
            "deep_validated_after_u04_white_result_and_claim_required": True,
            "five_minute_short_hold_bound": True,
            "thirty_minute_hold_status": "SKIPPED_BY_OPERATOR",
            "thirty_minute_hold_is_comparison_gate": False,
            "formal_u07_qualification_inferred": False,
        },
    }


def build_release(
    *,
    panel_file: Path,
    firmware_file: Path,
    elf_file: Path,
    preview_manifest_file: Path,
    corrected_release_file: Path,
    u04_result_file: Path,
    short_hold_file: Path,
    white_result_file: Path,
    white_observation_file: Path,
    rc2g_binary_file: Path,
    candidate_claim_registry: Path,
    white_claim_registry: Path,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompareReleaseError("created_at must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CompareReleaseError("created_at requires an offset")
    panel = _panel(panel_file)
    firmware = _read(firmware_file, label="comparison firmware", maximum=32 << 20)
    elf = _read(elf_file, label="comparison ELF")
    compiled = compiled_identity_report(elf_file)
    _validate_firmware(firmware)
    try:
        preview_report = preview.validate(preview_manifest_file)
    except preview.ComparePreviewError as error:
        raise CompareReleaseError(f"preview replay failed: {error}") from error
    raw = _read(preview_manifest_file.parent / preview.RAW_FILE, label="preview raw")
    png = _read(preview_manifest_file.parent / preview.PNG_FILE, label="preview PNG")
    preview_manifest = _read(preview_manifest_file, label="preview manifest")
    if raw != identity.generate_frame():
        raise CompareReleaseError("preview raw differs from frozen fixture")
    prerequisites = load_prerequisites(
        corrected_release_file=corrected_release_file,
        u04_result_file=u04_result_file,
        short_hold_file=short_hold_file,
        white_result_file=white_result_file,
        white_observation_file=white_observation_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        candidate_claim_registry=candidate_claim_registry,
        white_claim_registry=white_claim_registry,
    )
    variant = identity.variant()
    variant.update(
        {
            "firmware": {
                "file": variant.pop("firmware_file"),
                "bytes": len(firmware),
                "sha256": sha256(firmware),
            },
            "elf": {
                "file": variant.pop("elf_file"),
                "bytes": len(elf),
                "sha256": sha256(elf),
            },
            "build_command": ["pio", "run", "-e", identity.ENVIRONMENT],
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "created_at": created_at,
        "panel": panel,
        "source_snapshot": _source_snapshot(),
        "device_contract": deepcopy(DEVICE_CONTRACT),
        "variant": variant,
        "compiled_identity_report": compiled,
        "preview": {
            "manifest_file": preview.MANIFEST_FILE,
            "manifest_bytes": len(preview_manifest),
            "manifest_sha256": sha256(preview_manifest),
            "raw_file": preview.RAW_FILE,
            "raw_bytes": len(raw),
            "raw_sha256": sha256(raw),
            "png_file": preview.PNG_FILE,
            "png_bytes": len(png),
            "png_sha256": sha256(png),
            "validated": preview_report,
        },
        "prerequisites": prerequisites,
        "safety": deepcopy(SAFETY),
    }
    manifest = {
        **unsigned,
        "integrity": {"canonical_sha256": sha256(unsigned), "scope": HASH_SCOPE},
    }
    return manifest, {
        variant["firmware"]["file"]: firmware,
        variant["elf"]["file"]: elf,
        preview.RAW_FILE: raw,
        preview.PNG_FILE: png,
        preview.MANIFEST_FILE: preview_manifest,
    }


def validate_release(bundle: Path) -> dict[str, Any]:
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise CompareReleaseError("bundle must be a local directory")
    if (bundle / QUARANTINE_MARKER).exists():
        raise CompareReleaseError("bundle is quarantined")
    root = _json(bundle / MANIFEST_FILE, label="comparison release")
    expected_keys = {
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
    if set(root) != expected_keys or root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise CompareReleaseError("release schema/kind differs")
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if integrity != {"canonical_sha256": sha256(unsigned), "scope": HASH_SCOPE}:
        raise CompareReleaseError("release integrity differs")
    if root["device_contract"] != DEVICE_CONTRACT or root["safety"] != SAFETY:
        raise CompareReleaseError("release contract differs")
    source_snapshot = root["source_snapshot"]
    if not isinstance(source_snapshot, list) or [
        item.get("path") if isinstance(item, Mapping) else None
        for item in source_snapshot
    ] != list(SOURCE_PATHS):
        raise CompareReleaseError("release source snapshot paths differ")
    for item in source_snapshot:
        if not isinstance(item, Mapping) or set(item) != {"path", "bytes", "sha256"}:
            raise CompareReleaseError("release source snapshot entry differs")
        source_payload = _read(
            REPO_ROOT / item["path"], label=f"release source {item['path']}"
        )
        if item["bytes"] != len(source_payload) or item["sha256"] != sha256(
            source_payload
        ):
            raise CompareReleaseError(f"release source {item['path']} differs")
    expected_variant = identity.variant()
    variant = root["variant"]
    if not isinstance(variant, Mapping):
        raise CompareReleaseError("release variant is malformed")
    for key in expected_variant:
        if key in ("firmware_file", "elf_file"):
            continue
        if variant.get(key) != expected_variant[key]:
            raise CompareReleaseError(f"release variant {key} differs")
    if identity.derive_action_id(variant["action_identity_preimage"]) != identity.FROZEN_ACTION_ID:
        raise CompareReleaseError("release action preimage differs")
    artifact_payloads: dict[str, bytes] = {}
    for entry_name in ("firmware", "elf"):
        entry = variant.get(entry_name)
        if not isinstance(entry, Mapping) or set(entry) != {"file", "bytes", "sha256"}:
            raise CompareReleaseError(f"release {entry_name} entry differs")
        payload = _read(bundle / entry["file"], label=f"release {entry_name}")
        if len(payload) != entry["bytes"] or sha256(payload) != entry["sha256"]:
            raise CompareReleaseError(f"release {entry_name} bytes differ")
        artifact_payloads[entry_name] = payload
    _validate_firmware(artifact_payloads["firmware"])
    replay = compiled_identity_report(bundle / variant["elf"]["file"])
    if replay != root["compiled_identity_report"]:
        raise CompareReleaseError("compiled identity report differs")
    preview_report = preview.validate(bundle / preview.MANIFEST_FILE)
    preview_manifest_payload = _read(
        bundle / preview.MANIFEST_FILE, label="release preview manifest"
    )
    raw_payload = _read(bundle / preview.RAW_FILE, label="release preview raw")
    png_payload = _read(bundle / preview.PNG_FILE, label="release preview PNG")
    expected_preview = {
        "manifest_file": preview.MANIFEST_FILE,
        "manifest_bytes": len(preview_manifest_payload),
        "manifest_sha256": sha256(preview_manifest_payload),
        "raw_file": preview.RAW_FILE,
        "raw_bytes": len(raw_payload),
        "raw_sha256": sha256(raw_payload),
        "png_file": preview.PNG_FILE,
        "png_bytes": len(png_payload),
        "png_sha256": sha256(png_payload),
        "validated": preview_report,
    }
    if root["preview"] != expected_preview:
        raise CompareReleaseError("release preview binding differs")
    if OBSOLETE_ACTION_ID in canonical_json_bytes(root).decode("utf-8"):
        raise CompareReleaseError("release contains obsolete horizontal action")
    return dict(root)


def publish(output: Path, manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    output = Path(output)
    try:
        output.mkdir(mode=0o700, exist_ok=False)
        for filename, payload in files.items():
            with (output / filename).open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        with (output / MANIFEST_FILE).open("xb") as stream:
            stream.write(canonical_json_bytes(manifest))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise CompareReleaseError(f"could not publish release: {error}") from error
    validate_release(output)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--preview-manifest", type=Path, required=True)
    parser.add_argument("--corrected-u04-release", type=Path, required=True)
    parser.add_argument("--u04-result", type=Path, required=True)
    parser.add_argument("--u04-short-hold", type=Path, required=True)
    parser.add_argument("--white-result", type=Path, required=True)
    parser.add_argument("--white-observation", type=Path, required=True)
    parser.add_argument("--rc2g-binary", type=Path, required=True)
    parser.add_argument("--candidate-claim-registry", type=Path, required=True)
    parser.add_argument("--white-claim-registry", type=Path, required=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", allow_abbrev=False)
    _common(build)
    build.add_argument("--created-at", required=True)
    build.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate", allow_abbrev=False)
    check.add_argument("--bundle", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            manifest, files = build_release(
                panel_file=args.panel,
                firmware_file=args.firmware,
                elf_file=args.elf,
                preview_manifest_file=args.preview_manifest,
                corrected_release_file=args.corrected_u04_release,
                u04_result_file=args.u04_result,
                short_hold_file=args.u04_short_hold,
                white_result_file=args.white_result,
                white_observation_file=args.white_observation,
                rc2g_binary_file=args.rc2g_binary,
                candidate_claim_registry=args.candidate_claim_registry,
                white_claim_registry=args.white_claim_registry,
                created_at=args.created_at,
            )
            publish(args.output, manifest, files)
            report = {
                "bundle": str(args.output),
                "action_id": identity.FROZEN_ACTION_ID,
                "canonical_sha256": manifest["integrity"]["canonical_sha256"],
            }
        else:
            manifest = validate_release(args.bundle)
            report = {
                "valid": True,
                "action_id": identity.FROZEN_ACTION_ID,
                "canonical_sha256": manifest["integrity"]["canonical_sha256"],
            }
    except CompareReleaseError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
