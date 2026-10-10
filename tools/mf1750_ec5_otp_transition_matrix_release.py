#!/usr/bin/env python3
"""Seal and deeply validate the exact factory-OTP matrix execution bundle.

The bundle layer is deliberately narrower than the materialized release.  It
does not authorize a refresh.  It proves that the campaign, materialized
release, BIN, and ELF used by the physical runner are the four exact regular
files in one directory, replays the existing release validator, and verifies
the ESP-IDF BIN-to-ELF app-descriptor binding.  No hardware, serial, network,
upload, or claim operation is implemented here.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
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

from tools import mf1750_ec5_otp_transition_matrix_campaign as campaign  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_contract as contract  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-otp-transition-matrix-self-contained-execution-bundle"
MANIFEST_FILE = "bundle-manifest.json"
CAMPAIGN_FILE = "otp-transition-matrix-campaign.json"
RELEASE_FILE = "otp-transition-matrix-real-release.json"
FIRMWARE_BINARY_FILE = "firmware.bin"
FIRMWARE_ELF_FILE = "firmware.elf"
SOURCE_FILES = (
    CAMPAIGN_FILE,
    RELEASE_FILE,
    FIRMWARE_BINARY_FILE,
    FIRMWARE_ELF_FILE,
)
EXACT_FILES = (*SOURCE_FILES, MANIFEST_FILE)
HASH_SCOPE = "entire object excluding integrity; canonical UTF-8 JSON"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_BINARY_BYTES = 4_000_000
MAX_ELF_BYTES = 32_000_000
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PREVIEW_BYTES = 16 * 1024 * 1024

_MAXIMUMS = {
    CAMPAIGN_FILE: MAX_JSON_BYTES,
    RELEASE_FILE: MAX_JSON_BYTES,
    FIRMWARE_BINARY_FILE: MAX_BINARY_BYTES,
    FIRMWARE_ELF_FILE: MAX_ELF_BYTES,
    MANIFEST_FILE: MAX_MANIFEST_BYTES,
}


class OtpTransitionMatrixReleaseError(RuntimeError):
    """The bundle is not the exact sealed, offline execution bundle."""


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
        raise OtpTransitionMatrixReleaseError(
            f"value is not canonical JSON: {error}"
        ) from error


def sha256(payload: bytes | Mapping[str, Any]) -> str:
    data = canonical_json_bytes(payload) if isinstance(payload, Mapping) else payload
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OtpTransitionMatrixReleaseError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                OtpTransitionMatrixReleaseError(
                    f"{label} contains forbidden number {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OtpTransitionMatrixReleaseError(
            f"{label} is invalid UTF-8 JSON: {error}"
        ) from error
    if not isinstance(root, Mapping):
        raise OtpTransitionMatrixReleaseError(f"{label} root must be an object")
    return root


def _regular_metadata(path: Path, *, label: str, maximum: int) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not inspect {label}: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise OtpTransitionMatrixReleaseError(
            f"{label} must be a regular non-symlink file"
        )
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        raise OtpTransitionMatrixReleaseError(f"{label} size is invalid")
    return metadata


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    before = _regular_metadata(path, label=label, maximum=maximum)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(f"could not read {label}: {error}") from error
    after = _regular_metadata(path, label=label, maximum=maximum)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise OtpTransitionMatrixReleaseError(f"{label} changed while it was read")
    if len(payload) != after.st_size:
        raise OtpTransitionMatrixReleaseError(f"{label} read length differs")
    return payload


def _bundle_root(bundle: Path) -> Path:
    bundle = Path(bundle)
    try:
        metadata = bundle.lstat()
        resolved = bundle.resolve(strict=True)
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not inspect bundle directory: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise OtpTransitionMatrixReleaseError(
            "bundle must be a non-symlink local directory"
        )
    return resolved


def _exact_entries(bundle: Path, *, include_manifest: bool) -> None:
    expected = set(EXACT_FILES if include_manifest else SOURCE_FILES)
    try:
        entries = list(bundle.iterdir())
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not enumerate bundle directory: {error}"
        ) from error
    names = {entry.name for entry in entries}
    if len(names) != len(entries) or names != expected:
        missing = sorted(expected - names)
        extra = sorted(names - expected)
        raise OtpTransitionMatrixReleaseError(
            "bundle exact-file whitelist differs "
            f"(missing={missing!r}, extra={extra!r})"
        )
    for entry in entries:
        _regular_metadata(
            entry,
            label=f"bundle entry {entry.name}",
            maximum=_MAXIMUMS[entry.name],
        )


def _bundle_file(bundle: Path, filename: str) -> Path:
    if filename not in EXACT_FILES or Path(filename).name != filename:
        raise OtpTransitionMatrixReleaseError("bundle filename is not allowlisted")
    path = bundle / filename
    _regular_metadata(
        path, label=f"bundle entry {filename}", maximum=_MAXIMUMS[filename]
    )
    return path


def _read_sources(bundle: Path) -> dict[str, bytes]:
    return {
        filename: _read_regular(
            _bundle_file(bundle, filename),
            label=f"bundle entry {filename}",
            maximum=_MAXIMUMS[filename],
        )
        for filename in SOURCE_FILES
    }


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["integrity"] = {
        "canonical_sha256": sha256(unsigned),
        "scope": HASH_SCOPE,
    }
    return result


def _validate_seal(root: Mapping[str, Any]) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise OtpTransitionMatrixReleaseError("bundle integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {"canonical_sha256": sha256(unsigned), "scope": HASH_SCOPE}
    if dict(integrity) != expected:
        raise OtpTransitionMatrixReleaseError("bundle canonical seal differs")
    return str(integrity["canonical_sha256"])


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


def _exact_local_reference(
    value: Any, *, bundle: Path, filename: str, label: str
) -> Path:
    if not isinstance(value, str) or not value:
        raise OtpTransitionMatrixReleaseError(f"{label} path is malformed")
    supplied = Path(value)
    expected = bundle / filename
    if not supplied.is_absolute() or not _same_path(supplied, expected):
        raise OtpTransitionMatrixReleaseError(
            f"{label} path must be the exact file inside this bundle"
        )
    try:
        if supplied.resolve(strict=True) != expected.resolve(strict=True):
            raise OtpTransitionMatrixReleaseError(
                f"{label} resolves outside this bundle"
            )
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not resolve {label}: {error}"
        ) from error
    _regular_metadata(supplied, label=label, maximum=_MAXIMUMS[filename])
    return supplied


def _validate_execution_paths(release_root: Mapping[str, Any], bundle: Path) -> None:
    compiled = release_root.get("compiled_campaign")
    firmware = release_root.get("firmware")
    if not isinstance(compiled, Mapping) or not isinstance(firmware, Mapping):
        raise OtpTransitionMatrixReleaseError(
            "release execution artifact references are absent"
        )
    binary = firmware.get("binary")
    elf = firmware.get("elf")
    if not isinstance(binary, Mapping) or not isinstance(elf, Mapping):
        raise OtpTransitionMatrixReleaseError(
            "release firmware execution references are absent"
        )
    _exact_local_reference(
        compiled.get("file"),
        bundle=bundle,
        filename=CAMPAIGN_FILE,
        label="release campaign execution authority",
    )
    _exact_local_reference(
        binary.get("file"),
        bundle=bundle,
        filename=FIRMWARE_BINARY_FILE,
        label="release firmware BIN execution authority",
    )
    _exact_local_reference(
        elf.get("file"),
        bundle=bundle,
        filename=FIRMWARE_ELF_FILE,
        label="release firmware ELF execution authority",
    )


def _binary_elf_link(binary: bytes, elf: bytes) -> dict[str, Any]:
    app_descriptor_offset = 32
    embedded_elf_sha256_offset = 176
    app_descriptor_magic = bytes.fromhex("3254cdab")
    elf_digest = hashlib.sha256(elf).digest()
    if (
        len(binary) < embedded_elf_sha256_offset + len(elf_digest)
        or not binary.startswith(b"\xE9")
        or not elf.startswith(b"\x7fELF")
        or binary[
            app_descriptor_offset : app_descriptor_offset
            + len(app_descriptor_magic)
        ]
        != app_descriptor_magic
        or binary[
            embedded_elf_sha256_offset : embedded_elf_sha256_offset
            + len(elf_digest)
        ]
        != elf_digest
    ):
        raise OtpTransitionMatrixReleaseError(
            "firmware BIN app descriptor does not bind the bundled ELF"
        )
    return {
        "app_descriptor_offset": app_descriptor_offset,
        "app_descriptor_magic_hex": app_descriptor_magic.hex(),
        "embedded_elf_sha256_offset": embedded_elf_sha256_offset,
        "embedded_elf_sha256": elf_digest.hex(),
        "selected_elf_sha256": hashlib.sha256(elf).hexdigest(),
        "exact_match": True,
    }


def _runner_frozen_identity() -> dict[str, str]:
    # Importing the runner performs no I/O.  These constants are the final gate
    # consulted before any physical operation, so the bundle must bind them.
    from tools import (  # noqa: PLC0415
        mf1750_ec5_otp_transition_matrix_physical_once as physical,
    )

    return {
        "campaign_file_sha256": physical.EXPECTED_CAMPAIGN_FILE_SHA256,
        "campaign_canonical_sha256": physical.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "release_file_sha256": physical.EXPECTED_RELEASE_FILE_SHA256,
        "release_canonical_sha256": physical.EXPECTED_RELEASE_CANONICAL_SHA256,
        "firmware_binary_sha256": physical.EXPECTED_FIRMWARE_BINARY_SHA256,
        "firmware_elf_sha256": physical.EXPECTED_FIRMWARE_ELF_SHA256,
    }


def _operator_preview_records() -> dict[str, dict[str, Any]]:
    """Freeze the three external layout previews consumed by the runner."""

    from tools import (  # noqa: PLC0415
        mf1750_ec5_otp_transition_matrix_physical_once as physical,
    )

    if set(physical.PREVIEW_FILES) != set(contract.ROLES):
        raise OtpTransitionMatrixReleaseError(
            "physical runner preview roles differ from the three-action campaign"
        )
    records: dict[str, dict[str, Any]] = {}
    for role in contract.ROLES:
        path = Path(physical.PREVIEW_FILES[role])
        if not path.is_absolute():
            raise OtpTransitionMatrixReleaseError(
                f"physical runner preview for {role} is not an exact absolute path"
            )
        payload = _read_regular(
            path, label=f"physical runner preview for {role}", maximum=MAX_PREVIEW_BYTES
        )
        records[role] = {
            "file": str(path),
            "bytes": len(payload),
            "sha256": sha256(payload),
            "interpretation": "pseudocolor_layout_only_not_physical_colour",
        }
    return records


def _validate_safety_contract(
    campaign_root: Mapping[str, Any],
    release_root: Mapping[str, Any],
    *,
    campaign_report: Mapping[str, Any],
    release_report: Mapping[str, Any],
) -> dict[str, Any]:
    actions = campaign_root.get("actions")
    classification = campaign_root.get("classification")
    firmware_contract = campaign_root.get("firmware_contract")
    release_safety = release_root.get("safety")
    if (
        not isinstance(actions, list)
        or len(actions) != 3
        or [action.get("ordinal") for action in actions] != [1, 2, 3]
        or [action.get("role") for action in actions] != list(contract.ROLES)
        or any(action.get("execution_eligible") is not False for action in actions)
        or len({action.get("action_id") for action in actions}) != 3
        or campaign_report.get("action_count") != 3
        or release_report.get("action_count") != 3
    ):
        raise OtpTransitionMatrixReleaseError(
            "bundle must contain the exact three non-authorizing matrix actions"
        )
    if (
        not isinstance(classification, Mapping)
        or classification.get("profile_source") != "factory_otp"
        or classification.get("runtime_lut_or_waveform_changed") is not False
        or classification.get("visible_refresh_authorized_by_this_compiler")
        is not False
        or not isinstance(firmware_contract, Mapping)
        or firmware_contract.get("profile_source") != "factory_otp"
        or firmware_contract.get("runtime_lut_write") is not False
        or firmware_contract.get("custom_lut_or_waveform") is not False
        or not isinstance(release_safety, Mapping)
        or release_safety.get("profile_source") != "factory_otp"
        or release_safety.get("runtime_lut_or_waveform_write") is not False
        or release_safety.get("electrical_parameter_write") is not False
        or release_safety.get("visible_refresh_authorized_by_release") != 0
        or release_safety.get("materializer_visible_refreshes") != 0
        or release_report.get("visible_refresh_authorized_by_release") != 0
    ):
        raise OtpTransitionMatrixReleaseError(
            "factory-OTP, no-runtime-LUT, zero-refresh-authorization contract differs"
        )
    return {
        "action_count": 3,
        "ordinals": [1, 2, 3],
        "roles": list(contract.ROLES),
        "action_ids": [str(action["action_id"]) for action in actions],
        "profile_source": "factory_otp",
        "runtime_lut_or_waveform_changed": False,
    }


def _artifact_record(
    filename: str, payload: bytes, *, canonical_sha256: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file": filename,
        "bytes": len(payload),
        "sha256": sha256(payload),
    }
    if canonical_sha256 is not None:
        result["canonical_sha256"] = canonical_sha256
    return result


def _deep_validate_sources(bundle: Path, payloads: Mapping[str, bytes]) -> dict[str, Any]:
    campaign_root = _decode_json(
        payloads[CAMPAIGN_FILE], label="bundled OTP transition-matrix campaign"
    )
    release_root = _decode_json(
        payloads[RELEASE_FILE], label="bundled OTP transition-matrix release"
    )
    _validate_execution_paths(release_root, bundle)
    campaign_path = bundle / CAMPAIGN_FILE
    release_path = bundle / RELEASE_FILE
    try:
        campaign_report = campaign.validate_campaign(campaign_path)
        release_report = campaign.validate_materialized_release(release_path)
    except campaign.OtpTransitionMatrixCampaignError as error:
        raise OtpTransitionMatrixReleaseError(
            f"materialized release validator failed: {error}"
        ) from error
    link = _binary_elf_link(
        payloads[FIRMWARE_BINARY_FILE], payloads[FIRMWARE_ELF_FILE]
    )
    release_firmware = release_root.get("firmware")
    if (
        not isinstance(release_firmware, Mapping)
        or release_firmware.get("binary_elf_link") != link
    ):
        raise OtpTransitionMatrixReleaseError(
            "release BIN/ELF app-descriptor evidence differs"
        )
    campaign_contract = _validate_safety_contract(
        campaign_root,
        release_root,
        campaign_report=campaign_report,
        release_report=release_report,
    )
    runner_identity = _runner_frozen_identity()
    observed_runner_identity = {
        "campaign_file_sha256": sha256(payloads[CAMPAIGN_FILE]),
        "campaign_canonical_sha256": str(campaign_report["canonical_sha256"]),
        "release_file_sha256": sha256(payloads[RELEASE_FILE]),
        "release_canonical_sha256": str(release_report["canonical_sha256"]),
        "firmware_binary_sha256": sha256(payloads[FIRMWARE_BINARY_FILE]),
        "firmware_elf_sha256": sha256(payloads[FIRMWARE_ELF_FILE]),
    }
    if observed_runner_identity != runner_identity:
        raise OtpTransitionMatrixReleaseError(
            "bundle differs from the physical runner frozen execution identity"
        )
    return {
        "campaign_report": campaign_report,
        "release_report": release_report,
        "campaign_contract": campaign_contract,
        "binary_elf_link": link,
        "runner_frozen_identity": runner_identity,
        "operator_previews": _operator_preview_records(),
    }


def _unsigned_manifest(
    payloads: Mapping[str, bytes], validation: Mapping[str, Any]
) -> dict[str, Any]:
    campaign_report = validation["campaign_report"]
    release_report = validation["release_report"]
    release_record = _artifact_record(
        RELEASE_FILE,
        payloads[RELEASE_FILE],
        canonical_sha256=str(release_report["canonical_sha256"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "bundle_layout": {
            "exact_files": list(EXACT_FILES),
            "additional_entries_allowed": False,
            "symlinks_allowed": False,
            "execution_paths": "exact bundle-local regular files",
            "operator_previews_embedded": False,
        },
        "execution_authority": {
            **release_record,
            "authority_kind": "materialized_release_for_physical_runner",
            "execution_eligible": True,
            "visible_refresh_authorizations": 0,
            "runner_frozen_identity": deepcopy(
                validation["runner_frozen_identity"]
            ),
        },
        "artifacts": {
            "compiled_campaign": _artifact_record(
                CAMPAIGN_FILE,
                payloads[CAMPAIGN_FILE],
                canonical_sha256=str(campaign_report["canonical_sha256"]),
            ),
            "materialized_release": release_record,
            "firmware_binary": _artifact_record(
                FIRMWARE_BINARY_FILE, payloads[FIRMWARE_BINARY_FILE]
            ),
            "firmware_elf": _artifact_record(
                FIRMWARE_ELF_FILE, payloads[FIRMWARE_ELF_FILE]
            ),
        },
        "binary_elf_link": deepcopy(validation["binary_elf_link"]),
        "operator_previews": deepcopy(validation["operator_previews"]),
        "campaign_contract": deepcopy(validation["campaign_contract"]),
        "safety": {
            "offline_sealer": True,
            "device_access_performed": False,
            "network_requests": 0,
            "serial_requests": 0,
            "upload_performed": False,
            "claim_created": False,
            "visible_refreshes_performed": 0,
            "visible_refresh_authorizations": 0,
            "profile_source": "factory_otp",
            "runtime_lut_or_waveform_write": False,
        },
    }


def _validate_manifest_policy(root: Mapping[str, Any]) -> None:
    if set(root) != {
        "schema_version",
        "kind",
        "bundle_layout",
        "execution_authority",
        "artifacts",
        "binary_elf_link",
        "operator_previews",
        "campaign_contract",
        "safety",
        "integrity",
    }:
        raise OtpTransitionMatrixReleaseError("bundle manifest fields differ")
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise OtpTransitionMatrixReleaseError("bundle identity differs")
    if root.get("bundle_layout") != {
        "exact_files": list(EXACT_FILES),
        "additional_entries_allowed": False,
        "symlinks_allowed": False,
        "execution_paths": "exact bundle-local regular files",
        "operator_previews_embedded": False,
    }:
        raise OtpTransitionMatrixReleaseError("bundle layout policy differs")
    expected_safety = {
        "offline_sealer": True,
        "device_access_performed": False,
        "network_requests": 0,
        "serial_requests": 0,
        "upload_performed": False,
        "claim_created": False,
        "visible_refreshes_performed": 0,
        "visible_refresh_authorizations": 0,
        "profile_source": "factory_otp",
        "runtime_lut_or_waveform_write": False,
    }
    if root.get("safety") != expected_safety:
        raise OtpTransitionMatrixReleaseError(
            "bundle zero-authorization factory-OTP safety policy differs"
        )
    authority = root.get("execution_authority")
    if (
        not isinstance(authority, Mapping)
        or authority.get("file") != RELEASE_FILE
        or authority.get("authority_kind")
        != "materialized_release_for_physical_runner"
        or authority.get("execution_eligible") is not True
        or authority.get("visible_refresh_authorizations") != 0
    ):
        raise OtpTransitionMatrixReleaseError(
            "bundle execution authority policy differs"
        )
    previews = root.get("operator_previews")
    if not isinstance(previews, Mapping) or set(previews) != set(contract.ROLES):
        raise OtpTransitionMatrixReleaseError(
            "bundle operator preview records differ"
        )
    for role in contract.ROLES:
        record = previews[role]
        if (
            not isinstance(record, Mapping)
            or set(record) != {"file", "bytes", "sha256", "interpretation"}
            or not isinstance(record.get("file"), str)
            or not Path(str(record["file"])).is_absolute()
            or record.get("interpretation")
            != "pseudocolor_layout_only_not_physical_colour"
        ):
            raise OtpTransitionMatrixReleaseError(
                f"bundle operator preview record for {role} differs"
            )


def _verify_manifest_artifacts(
    root: Mapping[str, Any], payloads: Mapping[str, bytes]
) -> None:
    artifacts = root.get("artifacts")
    authority = root.get("execution_authority")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "compiled_campaign",
        "materialized_release",
        "firmware_binary",
        "firmware_elf",
    }:
        raise OtpTransitionMatrixReleaseError("bundle artifact records differ")
    expected_files = {
        "compiled_campaign": CAMPAIGN_FILE,
        "materialized_release": RELEASE_FILE,
        "firmware_binary": FIRMWARE_BINARY_FILE,
        "firmware_elf": FIRMWARE_ELF_FILE,
    }
    for role, filename in expected_files.items():
        record = artifacts[role]
        expected_keys = {"file", "bytes", "sha256"}
        if role in {"compiled_campaign", "materialized_release"}:
            expected_keys.add("canonical_sha256")
        if not isinstance(record, Mapping) or set(record) != expected_keys:
            raise OtpTransitionMatrixReleaseError(
                f"bundle {role} artifact record fields differ"
            )
        payload = payloads[filename]
        if (
            record.get("file") != filename
            or record.get("bytes") != len(payload)
            or record.get("sha256") != sha256(payload)
        ):
            raise OtpTransitionMatrixReleaseError(
                f"bundle {role} artifact bytes or SHA-256 differ"
            )
    if not isinstance(authority, Mapping) or any(
        authority.get(key) != artifacts["materialized_release"].get(key)
        for key in ("file", "bytes", "sha256", "canonical_sha256")
    ):
        raise OtpTransitionMatrixReleaseError(
            "execution authority does not bind the bundled release bytes"
        )


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(value)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise OtpTransitionMatrixReleaseError(
            f"refusing to overwrite existing {path.name}"
        ) from error
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not create {path.name}: {error}"
        ) from error


def build_bundle(bundle: Path) -> dict[str, Any]:
    """Create ``bundle-manifest.json`` without overwriting any existing file."""

    root = _bundle_root(bundle)
    manifest_path = root / MANIFEST_FILE
    try:
        manifest_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise OtpTransitionMatrixReleaseError(
            f"could not inspect existing bundle manifest: {error}"
        ) from error
    else:
        raise OtpTransitionMatrixReleaseError(
            f"refusing to overwrite existing {MANIFEST_FILE}"
        )
    _exact_entries(root, include_manifest=False)
    payloads = _read_sources(root)
    validation = _deep_validate_sources(root, payloads)
    if _read_sources(root) != payloads:
        raise OtpTransitionMatrixReleaseError(
            "bundle source artifacts changed before sealing"
        )
    _exact_entries(root, include_manifest=False)
    manifest = _seal(_unsigned_manifest(payloads, validation))
    _write_new(manifest_path, manifest)
    validate_bundle(root)
    return manifest


def validate_bundle(bundle: Path) -> dict[str, Any]:
    """Deeply replay the bundle without authorizing or performing a refresh."""

    root = _bundle_root(bundle)
    _exact_entries(root, include_manifest=True)
    manifest_payload = _read_regular(
        _bundle_file(root, MANIFEST_FILE),
        label="bundle manifest",
        maximum=MAX_MANIFEST_BYTES,
    )
    manifest = _decode_json(manifest_payload, label="bundle manifest")
    canonical = _validate_seal(manifest)
    _validate_manifest_policy(manifest)
    payloads = _read_sources(root)
    _verify_manifest_artifacts(manifest, payloads)
    validation = _deep_validate_sources(root, payloads)
    expected = _seal(_unsigned_manifest(payloads, validation))
    if dict(manifest) != expected:
        raise OtpTransitionMatrixReleaseError(
            "bundle manifest differs from deep replay"
        )
    if _read_sources(root) != payloads:
        raise OtpTransitionMatrixReleaseError(
            "bundle source artifacts changed during validation"
        )
    if (
        _read_regular(
            root / MANIFEST_FILE,
            label="bundle manifest",
            maximum=MAX_MANIFEST_BYTES,
        )
        != manifest_payload
    ):
        raise OtpTransitionMatrixReleaseError(
            "bundle manifest changed during validation"
        )
    _exact_entries(root, include_manifest=True)
    return {
        "bundle": str(root),
        "manifest_file": MANIFEST_FILE,
        "manifest_bytes": len(manifest_payload),
        "manifest_file_sha256": sha256(manifest_payload),
        "canonical_sha256": canonical,
        "execution_authority_file": RELEASE_FILE,
        "execution_authority_sha256": sha256(payloads[RELEASE_FILE]),
        "action_count": 3,
        "profile_source": "factory_otp",
        "runtime_lut_or_waveform_write": False,
        "visible_refresh_authorizations": 0,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "validate"):
        subparser = commands.add_parser(command, allow_abbrev=False)
        subparser.add_argument("--bundle", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "build":
            manifest = build_bundle(args.bundle)
            output = {
                "bundle": str(Path(args.bundle).resolve()),
                "manifest_file": MANIFEST_FILE,
                "canonical_sha256": manifest["integrity"]["canonical_sha256"],
                "visible_refresh_authorizations": 0,
            }
        else:
            output = validate_bundle(args.bundle)
    except OtpTransitionMatrixReleaseError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
