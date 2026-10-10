#!/usr/bin/env python3
"""Build and deeply validate the independent technical-only U07T release."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_stage_a_v2_identity as stage_a_identity  # noqa: E402
from tools import mf1750_ec5_u07t_compiled_identity as compiled  # noqa: E402
from tools import mf1750_ec5_u07t_identity as identity  # noqa: E402
from tools import mf1750_ec5_u07t_prerequisites as prereq  # noqa: E402
from tools import mf1750_ec5_u07t_preview as preview  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u07t-technical-release"
MANIFEST_FILE = "release-manifest.json"
QUARANTINE_MARKER = "QUARANTINED_DO_NOT_USE.md"
HASH_SCOPE = (
    "entire release manifest excluding integrity; canonical UTF-8 JSON sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
SOURCE_PATHS = (
    "platformio.u07t.ini",
    "src/ec5_u07t_main.cpp",
    "src/epd_config.h",
    "src/epd_driver.cpp",
    "src/epd_driver.h",
    "tools/mf1750_ec5_compiled_identity.py",
    "tools/mf1750_ec5_u07t_compiled_identity.py",
    "tools/mf1750_ec5_u07t_identity.py",
    "tools/mf1750_ec5_u07t_prerequisites.py",
    "tools/mf1750_ec5_u07t_preview.py",
    "tools/mf1750_ec5_u07t_release.py",
    "tools/mf1750_ec5_u07t_physical_once.py",
)
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
    "technical_claim_created_before_first_post": True,
    "technical_maximum_arm_posts": 1,
    "technical_maximum_execute_posts": 1,
    "retry_allowed": False,
    "recovery_included": False,
    "formal_u04_nvs_read_only": True,
    "formal_u07_nvs_read_only_and_must_remain_virgin": True,
    "formal_u07_claim_absence_required_before_and_after_action": True,
    "technical_claim_registry_must_differ_from_formal_registry": True,
    "initial_white_attestation_required_before_claim": True,
    "after_u04_white_must_be_immediate_visible_predecessor": True,
    "no_intervening_visible_refresh_required": True,
    "raw_frame_ingress": False,
    "startup_refresh": False,
}
SAFETY = {
    "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
    "hardware_authorized": False,
    "upload_performed": False,
    "device_io_performed": False,
    "visible_refresh_performed": False,
    "formal_u07_action_consumed": False,
    "formal_u07_qualification_inferred": False,
    "factory_otp_unchanged": True,
    "custom_waveform_or_lut_used": False,
    "dithering_present": False,
    "spatial_mixing_present": False,
    "u04_thirty_minute_hold_status": "SKIPPED_BY_OPERATOR",
    "after_u04_white_must_be_immediate_visible_predecessor": True,
    "no_intervening_visible_refresh_required": True,
    "post_action_screen_remains_u07t_until_separate_recovery": True,
    "formal_after_u07_white_action_must_not_be_reused": True,
}


class U07TReleaseError(ValueError):
    """U07T release construction or replay failed closed."""


def _require_execution_eligible() -> None:
    if not identity.EXECUTION_ELIGIBLE:
        raise U07TReleaseError(
            "U07T identity is invalidated and must be rebound after a new white recovery"
        )


def canonical_json_bytes(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path, *, label: str, maximum: int = 64 << 20) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise U07TReleaseError(f"{label} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise U07TReleaseError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise U07TReleaseError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise U07TReleaseError(f"{label} changed while read")
    return payload


def _json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_read(path, label=label, maximum=4 << 20).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise U07TReleaseError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise U07TReleaseError(f"{label} root must be an object")
    return value


def _panel(path: Path) -> dict[str, str]:
    value = _json(path, label="panel identity")
    if set(value) != {"model", "serial", "board_id", "pcb_revision"}:
        raise U07TReleaseError("panel fields differ")
    result = {}
    for key in ("model", "serial", "board_id", "pcb_revision"):
        item = value[key]
        if not isinstance(item, str) or not item or item != item.strip():
            raise U07TReleaseError(f"panel {key} is invalid")
        result[key] = item
    return result


def _source_snapshot() -> list[dict[str, Any]]:
    result = []
    for relative in SOURCE_PATHS:
        payload = _read(REPO_ROOT / relative, label=f"source {relative}")
        result.append({"path": relative, "bytes": len(payload), "sha256": sha256(payload)})
    return result


def _validate_firmware(payload: bytes) -> None:
    variant = identity.variant()
    required = (
        identity.BUILD_TAG,
        identity.TEST_ID,
        identity.FROZEN_ACTION_ID,
        identity.FRAME_SHA256,
        identity.DTM_SHA256,
        identity.IDENTITY_REVISION,
        identity.LAYOUT_ID,
        identity.DEVICE_API_VERSION,
        identity.FORMAL_NVS_NAMESPACE,
        identity.FORMAL_U04_NVS_KEY,
        identity.FORMAL_U07_NVS_KEY,
        identity.ACTIVE_NVS_NAMESPACE,
        identity.ACTIVE_NVS_KEY,
    )
    for token in required:
        if str(token).encode("ascii") not in payload:
            raise U07TReleaseError(f"firmware omits frozen token {token}")
    forbidden = (
        identity.FORMAL_U07_ACTION_ID,
        "d1874fb778b7af16a8e2c89687987d187e0fbed3a6ee279c966d427e633969a9",
        stage_a_identity.VARIANTS["U07"]["build_tag"],
        stage_a_identity.VARIANTS["U07"]["test_id"],
        *stage_a_identity.V1_BINARY_IDENTITY_TOKENS,
    )
    for token in forbidden:
        if str(token).encode("ascii") in payload:
            raise U07TReleaseError(f"firmware contains forbidden formal/V1 token {token}")
    if variant["classification"].encode("ascii") not in payload:
        raise U07TReleaseError("firmware omits technical-only classification")


_INPUT_NAMES = (
    "panel_file",
    "corrected_release_file",
    "u04_result_file",
    "short_hold_file",
    "white_result_file",
    "white_observation_file",
    "rc2g_binary_file",
    "candidate_claim_registry",
    "white_claim_registry",
    "formal_claim_registry",
)


def _input_paths(**values: Path) -> dict[str, str]:
    if set(values) != set(_INPUT_NAMES):
        raise U07TReleaseError("prerequisite input names differ")
    result = {}
    for name, value in values.items():
        path = Path(value)
        try:
            result[name] = str(path.resolve(strict=True))
        except OSError as error:
            raise U07TReleaseError(f"could not resolve {name}: {error}") from error
    return result


def _load_prerequisites(inputs: Mapping[str, str]) -> dict[str, Any]:
    try:
        return prereq.load_all(
            corrected_release_file=Path(inputs["corrected_release_file"]),
            u04_result_file=Path(inputs["u04_result_file"]),
            short_hold_file=Path(inputs["short_hold_file"]),
            white_result_file=Path(inputs["white_result_file"]),
            white_observation_file=Path(inputs["white_observation_file"]),
            panel_file=Path(inputs["panel_file"]),
            rc2g_binary_file=Path(inputs["rc2g_binary_file"]),
            candidate_claim_registry=Path(inputs["candidate_claim_registry"]),
            white_claim_registry=Path(inputs["white_claim_registry"]),
            formal_claim_registry=Path(inputs["formal_claim_registry"]),
        )
    except prereq.U07TPrerequisiteError as error:
        raise U07TReleaseError(f"U07T prerequisites failed: {error}") from error


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
    formal_claim_registry: Path,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    _require_execution_eligible()
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise U07TReleaseError("created_at must be RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise U07TReleaseError("created_at requires an offset")
    firmware = _read(firmware_file, label="U07T firmware", maximum=32 << 20)
    elf = _read(elf_file, label="U07T ELF")
    _validate_firmware(firmware)
    try:
        compiled_report = compiled.validate(elf_file)
        preview_report = preview.validate(preview_manifest_file)
    except (compiled.U07TCompiledIdentityError, preview.U07TPreviewError) as error:
        raise U07TReleaseError(str(error)) from error
    raw = _read(preview_manifest_file.parent / preview.RAW_FILE, label="U07T raw")
    png = _read(preview_manifest_file.parent / preview.PNG_FILE, label="U07T PNG")
    preview_manifest = _read(preview_manifest_file, label="U07T preview manifest")
    if raw != preview.generate_frame():
        raise U07TReleaseError("U07T preview raw differs")
    inputs = _input_paths(
        panel_file=panel_file,
        corrected_release_file=corrected_release_file,
        u04_result_file=u04_result_file,
        short_hold_file=short_hold_file,
        white_result_file=white_result_file,
        white_observation_file=white_observation_file,
        rc2g_binary_file=rc2g_binary_file,
        candidate_claim_registry=candidate_claim_registry,
        white_claim_registry=white_claim_registry,
        formal_claim_registry=formal_claim_registry,
    )
    prerequisites = _load_prerequisites(inputs)
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
            "build_command": [
                "pio",
                "run",
                "-c",
                "platformio.u07t.ini",
                "-e",
                identity.ENVIRONMENT,
            ],
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "created_at": created_at,
        "panel": _panel(panel_file),
        "source_snapshot": _source_snapshot(),
        "device_contract": deepcopy(DEVICE_CONTRACT),
        "variant": variant,
        "compiled_identity_report": compiled_report,
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
        "prerequisite_inputs": inputs,
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
    _require_execution_eligible()
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise U07TReleaseError("bundle must be a local directory")
    if (bundle / QUARANTINE_MARKER).exists():
        raise U07TReleaseError("U07T bundle is quarantined")
    root = _json(bundle / MANIFEST_FILE, label="U07T release")
    expected_keys = {
        "schema_version", "kind", "created_at", "panel", "source_snapshot",
        "device_contract", "variant", "compiled_identity_report", "preview",
        "prerequisite_inputs", "prerequisites", "safety", "integrity",
    }
    if set(root) != expected_keys or root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise U07TReleaseError("release schema/kind differs")
    unsigned = dict(root)
    integrity_value = unsigned.pop("integrity")
    if integrity_value != {"canonical_sha256": sha256(unsigned), "scope": HASH_SCOPE}:
        raise U07TReleaseError("release integrity differs")
    if root["device_contract"] != DEVICE_CONTRACT or root["safety"] != SAFETY:
        raise U07TReleaseError("release contract differs")
    if _panel(Path(root["prerequisite_inputs"]["panel_file"])) != root["panel"]:
        raise U07TReleaseError("release panel binding differs")
    sources = root["source_snapshot"]
    if not isinstance(sources, list) or [item.get("path") for item in sources] != list(SOURCE_PATHS):
        raise U07TReleaseError("source snapshot paths differ")
    if sources != _source_snapshot():
        raise U07TReleaseError("source snapshot differs from live sources")
    expected_variant = identity.variant()
    variant = root["variant"]
    if not isinstance(variant, Mapping):
        raise U07TReleaseError("variant is malformed")
    for key, wanted in expected_variant.items():
        if key not in ("firmware_file", "elf_file") and variant.get(key) != wanted:
            raise U07TReleaseError(f"variant {key} differs")
    if identity.derive_action_id(variant["action_identity_preimage"]) != identity.FROZEN_ACTION_ID:
        raise U07TReleaseError("variant action preimage differs")
    artifacts = {}
    for name in ("firmware", "elf"):
        entry = variant.get(name)
        if not isinstance(entry, Mapping) or set(entry) != {"file", "bytes", "sha256"}:
            raise U07TReleaseError(f"{name} entry differs")
        payload = _read(bundle / entry["file"], label=f"release {name}")
        if len(payload) != entry["bytes"] or sha256(payload) != entry["sha256"]:
            raise U07TReleaseError(f"release {name} differs")
        artifacts[name] = payload
    _validate_firmware(artifacts["firmware"])
    try:
        if compiled.validate(bundle / variant["elf"]["file"]) != root["compiled_identity_report"]:
            raise U07TReleaseError("compiled identity report differs")
        preview_report = preview.validate(bundle / preview.MANIFEST_FILE)
    except (compiled.U07TCompiledIdentityError, preview.U07TPreviewError) as error:
        raise U07TReleaseError(str(error)) from error
    preview_payloads = {
        "manifest": _read(bundle / preview.MANIFEST_FILE, label="release preview manifest"),
        "raw": _read(bundle / preview.RAW_FILE, label="release preview raw"),
        "png": _read(bundle / preview.PNG_FILE, label="release preview PNG"),
    }
    expected_preview = {
        "manifest_file": preview.MANIFEST_FILE,
        "manifest_bytes": len(preview_payloads["manifest"]),
        "manifest_sha256": sha256(preview_payloads["manifest"]),
        "raw_file": preview.RAW_FILE,
        "raw_bytes": len(preview_payloads["raw"]),
        "raw_sha256": sha256(preview_payloads["raw"]),
        "png_file": preview.PNG_FILE,
        "png_bytes": len(preview_payloads["png"]),
        "png_sha256": sha256(preview_payloads["png"]),
        "validated": preview_report,
    }
    if root["preview"] != expected_preview:
        raise U07TReleaseError("preview binding differs")
    if root["prerequisites"] != _load_prerequisites(root["prerequisite_inputs"]):
        raise U07TReleaseError("prerequisite replay differs")
    return dict(root)


def publish(output: Path, manifest: Mapping[str, Any], files: Mapping[str, bytes]) -> None:
    output = Path(output)
    try:
        output.mkdir(mode=0o700, exist_ok=False)
        for name, payload in files.items():
            with (output / name).open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        with (output / MANIFEST_FILE).open("xb") as stream:
            stream.write(canonical_json_bytes(manifest))
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise U07TReleaseError(f"could not publish U07T release: {error}") from error
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
    parser.add_argument("--formal-claim-registry", type=Path, required=True)


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
                panel_file=args.panel, firmware_file=args.firmware,
                elf_file=args.elf, preview_manifest_file=args.preview_manifest,
                corrected_release_file=args.corrected_u04_release,
                u04_result_file=args.u04_result,
                short_hold_file=args.u04_short_hold,
                white_result_file=args.white_result,
                white_observation_file=args.white_observation,
                rc2g_binary_file=args.rc2g_binary,
                candidate_claim_registry=args.candidate_claim_registry,
                white_claim_registry=args.white_claim_registry,
                formal_claim_registry=args.formal_claim_registry,
                created_at=args.created_at,
            )
            publish(args.output, manifest, files)
            report = {
                "bundle": str(args.output), "action_id": identity.FROZEN_ACTION_ID,
                "canonical_sha256": manifest["integrity"]["canonical_sha256"],
            }
        else:
            manifest = validate_release(args.bundle)
            report = {
                "valid": True, "action_id": identity.FROZEN_ACTION_ID,
                "canonical_sha256": manifest["integrity"]["canonical_sha256"],
            }
    except U07TReleaseError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
