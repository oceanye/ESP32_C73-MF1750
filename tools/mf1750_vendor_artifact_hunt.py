#!/usr/bin/env python3
"""Inventory the two local MF1750 vendor trees and their archives offline.

The report contains paths, sizes, hashes, marker names, and provenance classes
only.  It never emits waveform bytes or key material and performs no hardware,
serial, network, flashing, or refresh action.  Negative marker results are
bounded to the enumerated, identity-pinned inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any
from zipfile import ZipFile


KIND = "mf1750-vendor-artifact-hunt"
SCHEMA_VERSION = 2
REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_STM32_ROOT = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
DEFAULT_STM32_ZIP = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1).zip"
DEFAULT_IAR_ROOT = REPO_ROOT / "参考资料" / "E6_73_sample code_V1.2_20250116"
DEFAULT_IAR_7Z = REPO_ROOT / "参考资料" / "E6_73_sample code_V1.2_20250116.7z"
IAR_PROJECT_DIR = Path("E6_73_sample code_V1.2_20250116")

EXPECTED = {
    "stm32_zip_bytes": 17_297_740,
    "stm32_zip_sha256": (
        "c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead"
    ),
    "stm32_tree_files": 364,
    "stm32_tree_bytes": 82_180_051,
    "stm32_tree_manifest_sha256": (
        "5855f19047ab69949eafb14b9a746f2799cd2392a5fd55d5b863d40d687b020d"
    ),
    "stm32_zip_entries": 399,
    "stm32_zip_files": 364,
    "stm32_zip_legacy_name_normalizations": 14,
    "iar_7z_bytes": 376_465,
    "iar_7z_sha256": (
        "8f326e897810cfde51906198568239de87f7c7bbbf2983640480bc4fb9b1b2ee"
    ),
    "iar_7z_entries": 72,
    "iar_7z_files": 66,
    "iar_7z_metadata_manifest_sha256": (
        "3f21f4dbc3049be88b8d5478a0e5deb8e8ebfdc0e14a3c744b2ca4c18021f634"
    ),
    "iar_tree_files": 66,
    "iar_tree_bytes": 5_631_058,
    "iar_tree_manifest_sha256": (
        "d2d52e3d20e6788eff2c5e16735cb68fdacbc6d05424d5cc980f44282bf0257a"
    ),
    "loader_library_sha256": (
        "f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b"
    ),
    "loader_object_sha256": (
        "92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d"
    ),
    "wf23_editor_file_sha256": (
        "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d"
    ),
    "main_backup_sha256": (
        "e3a30aad634a96dcf0919057d52ff65d21d019b6401a819c8ab25a67e2f11217"
    ),
    "comm_backup_sha256": (
        "090b155c48b65c1aea5304fa1f7b77b30dcbeab5e5781614379c7af2cbe89ecc"
    ),
    "pin_backup_sha256": (
        "7681612a0630f19785fe2f675cb052aa75a2458235e31c267681f6ec38968681"
    ),
    "legacy_e2802_sha256": (
        "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce"
    ),
    "legacy_e2801_sha256": (
        "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3"
    ),
    "iar_dependency_bytes": 11_281,
    "iar_dependency_sha256": (
        "8b59303fa9d7a0b1ce453b117009ef4b468e1cac81e8a615e30ea026aa7dbaeb"
    ),
}

LOADER_LIBRARY_REL = Path("lib/eload_3bits_M3_E2802_20251229.lib")
WF23_REL = Path("Projects/MDK-ARM/12")
PROJECT_REL = Path("Projects/MDK-ARM/atk_f103.uvprojx")
EDITOR_STATE_REL = Path("Projects/MDK-ARM/atk_f103.uvguix.Administrator")

# These are safe names/fingerprints, not waveform fragments.  Alternatives are
# grouped under one semantic marker so a report never needs to print context.
MARKERS: dict[str, tuple[bytes, ...]] = {
    "compile_E5_3Bit_Mode_1": (b"E5_3Bit_Mode 1",),
    "compile_E5_3Bit_Mode_0": (b"E5_3Bit_Mode 0",),
    "compile_WF_DeCode_SIZE_800": (b"WF_DeCode_SIZE 800",),
    "compile_WF_DeCode_SIZE_809": (b"WF_DeCode_SIZE 809",),
    "compile_WF_DeCode_SIZE_544": (b"WF_DeCode_SIZE 544",),
    "compile_WF_SIZE_799": (b"WF_SIZE 799",),
    "compile_WF_SIZE_535": (b"WF_SIZE 535",),
    "symbol_loadWF": (b"loadWF",),
    "symbol_LUT1_DATA": (b"LUT1_DATA",),
    "text_PSR_5F_E9": (
        b"PSR5FE9",
        b"0x5F,0xE9",
        b"0x5F, 0xE9",
        b"0x5f,0xe9",
        b"0x5f, 0xe9",
    ),
    "text_command_E9": (b"0xE9", b"0xe9"),
    "dual_ToBoth": (b"ToBoth",),
    "dual_TARGET_BOTH": (b"TARGET_BOTH",),
    "dual_slave_cs": (b"E_Paper_SLAVE_CS",),
    "dual_selector_spiChipSelect": (b"spiChipSelect",),
    "dual_selector_MAS_SLA": (b"MAS_SLA",),
    "profile_WF23_25": (b"WF23_25",),
    "profile_WF25_25": (b"WF25_25",),
    "profile_WF00_05": (b"WF00_05",),
    "recovery_EPD_initial_noOTP": (b"EPD_initial_noOTP",),
    "recovery_display_White": (b"display_White",),
}

COMPRESSED_SIGNATURES = {
    "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "7z": (b"7z\xbc\xaf\x27\x1c",),
    "rar": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
    "gzip": (b"\x1f\x8b",),
    "bzip2": (b"BZh",),
    "xz": (b"\xfd7zXZ\x00",),
    "cab": (b"MSCF",),
}


class ArtifactAuditError(RuntimeError):
    """Raised when an identity or archive invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_sha256(rows: list[dict[str, Any]]) -> str:
    encoded = "".join(
        f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n"
        for row in sorted(rows, key=lambda item: item["path"])
    ).encode("utf-8")
    return _sha256(encoded)


def _metadata_manifest_sha256(rows: list[dict[str, Any]]) -> str:
    encoded = "".join(
        f"{row['path']}\0{row['bytes']}\n"
        for row in sorted(rows, key=lambda item: item["path"])
    ).encode("utf-8")
    return _sha256(encoded)


def _unsafe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        name.startswith(("/", "\\"))
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
    )


def _normalize_legacy_zip_name(name: str, utf8_flag: bool) -> tuple[str, bool]:
    if utf8_flag:
        return name, False
    try:
        decoded = name.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name, False
    return decoded, decoded != name


def _inventory_tree(
    root: Path,
    *,
    scope_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    _require(root.is_dir(), f"vendor tree is missing: {root}")
    rows: list[dict[str, Any]] = []
    marker_hits: dict[str, list[dict[str, Any]]] = {name: [] for name in MARKERS}
    compressed_hits: list[dict[str, Any]] = []
    ar_hits: list[dict[str, Any]] = []

    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        row = {"path": relative, "bytes": len(payload), "sha256": _sha256(payload)}
        rows.append(row)

        for marker_name, alternatives in MARKERS.items():
            count = sum(payload.count(marker) for marker in alternatives)
            if count:
                marker_hits[marker_name].append(
                    {
                        "scope": scope_name,
                        "path": relative,
                        "bytes": len(payload),
                        "sha256": row["sha256"],
                        "occurrences": count,
                    }
                )

        for signature_name, alternatives in COMPRESSED_SIGNATURES.items():
            if any(payload.startswith(signature) for signature in alternatives):
                compressed_hits.append({**row, "signature": signature_name})
        if payload.startswith(b"!<arch>\n"):
            ar_hits.append({**row, "signature": "unix-ar"})

    summary = {
        "root": root.as_posix(),
        "files": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "manifest_encoding": "sorted path NUL decimal-size NUL sha256 LF",
        "manifest_sha256": _manifest_sha256(rows),
        "nested_compressed_archive_signature_hits": compressed_hits,
        "nested_unix_ar_container_hits": ar_hits,
    }
    return summary, rows, marker_hits


def _zip_eocd_metadata(payload: bytes) -> dict[str, Any]:
    marker = b"PK\x05\x06"
    offset = payload.rfind(marker)
    _require(offset >= 0 and offset + 22 <= len(payload), "ZIP EOCD is missing")
    comment_bytes = int.from_bytes(payload[offset + 20 : offset + 22], "little")
    logical_end = offset + 22 + comment_bytes
    _require(logical_end <= len(payload), "ZIP EOCD comment is truncated")
    return {
        "first_local_header_at_offset_zero": payload.startswith(b"PK\x03\x04"),
        "eocd_offset": offset,
        "comment_bytes": comment_bytes,
        "trailing_bytes_after_eocd": len(payload) - logical_end,
    }


def _audit_stm32_zip(
    zip_path: Path,
    tree_root: Path,
    tree_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    _require(zip_path.is_file(), f"vendor ZIP is missing: {zip_path}")
    archive_payload = zip_path.read_bytes()
    _require(len(archive_payload) == EXPECTED["stm32_zip_bytes"], "ZIP size changed")
    archive_sha = _sha256(archive_payload)
    _require(archive_sha == EXPECTED["stm32_zip_sha256"], "ZIP SHA-256 changed")

    tree_lookup = {row["path"]: row for row in tree_rows}
    archive_rows: list[dict[str, Any]] = []
    unsafe: list[str] = []
    normalized_count = 0
    normalized_names: list[dict[str, str]] = []
    all_names: list[str] = []
    exact_mismatches: list[str] = []
    nested_archive_names: list[str] = []

    with ZipFile(zip_path) as archive:
        infos = archive.infolist()
        for info in infos:
            normalized, changed = _normalize_legacy_zip_name(
                info.filename, bool(info.flag_bits & 0x800)
            )
            all_names.append(normalized)
            if changed:
                normalized_count += 1
                normalized_names.append(
                    {"zipfile_decoded": info.filename, "canonical_gbk": normalized}
                )
            if _unsafe_archive_name(normalized):
                unsafe.append(normalized)
            if info.is_dir():
                continue
            _require(
                normalized.startswith("REG-API-oqc/"),
                f"unexpected ZIP root: {normalized}",
            )
            relative = normalized.removeprefix("REG-API-oqc/")
            payload = archive.read(info)
            row = {
                "path": relative,
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
            archive_rows.append(row)
            disk_path = tree_root / Path(relative)
            if not disk_path.is_file() or disk_path.read_bytes() != payload:
                exact_mismatches.append(relative)
            suffix = PurePosixPath(relative).suffix.lower()
            if suffix in {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".cab"}:
                nested_archive_names.append(relative)

    duplicate_names = sorted({name for name in all_names if all_names.count(name) > 1})
    archive_paths = {row["path"] for row in archive_rows}
    missing_from_tree = sorted(archive_paths - set(tree_lookup))
    extra_in_tree = sorted(set(tree_lookup) - archive_paths)
    manifest_sha = _manifest_sha256(archive_rows)

    _require(len(infos) == EXPECTED["stm32_zip_entries"], "ZIP entry count changed")
    _require(len(archive_rows) == EXPECTED["stm32_zip_files"], "ZIP file count changed")
    _require(
        normalized_count == EXPECTED["stm32_zip_legacy_name_normalizations"],
        "legacy ZIP filename normalization count changed",
    )
    _require(not unsafe, "unsafe ZIP path found")
    _require(not duplicate_names, "duplicate canonical ZIP name found")
    _require(not exact_mismatches, "ZIP and extracted tree differ")
    _require(not missing_from_tree and not extra_in_tree, "ZIP/tree name set differs")
    _require(
        manifest_sha == EXPECTED["stm32_tree_manifest_sha256"],
        "ZIP content manifest changed",
    )

    return {
        "path": zip_path.as_posix(),
        "bytes": len(archive_payload),
        "sha256": archive_sha,
        "entries": len(infos),
        "files": len(archive_rows),
        "legacy_gbk_name_normalizations": normalized_count,
        "normalized_names": normalized_names,
        "unsafe_paths": unsafe,
        "duplicate_canonical_names": duplicate_names,
        "missing_from_extracted_tree": missing_from_tree,
        "extra_in_extracted_tree": extra_in_tree,
        "byte_mismatches": exact_mismatches,
        "archive_file_manifest_sha256": manifest_sha,
        "all_extracted_file_bytes_match": True,
        "nested_archive_filename_hits": nested_archive_names,
        "container_layout": _zip_eocd_metadata(archive_payload),
    }


def _run_tar(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["tar", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise ArtifactAuditError(
            "local tar/bsdtar is required to list the 7z"
        ) from error


def _audit_iar_7z(
    archive_path: Path,
    tree_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    _require(archive_path.is_file(), f"vendor 7z is missing: {archive_path}")
    archive_payload = archive_path.read_bytes()
    _require(len(archive_payload) == EXPECTED["iar_7z_bytes"], "7z size changed")
    archive_sha = _sha256(archive_payload)
    _require(archive_sha == EXPECTED["iar_7z_sha256"], "7z SHA-256 changed")

    names_run = _run_tar(["-tf", str(archive_path)])
    verbose_run = _run_tar(["-tvf", str(archive_path)])
    _require(names_run.returncode == 0, "cannot list 7z names")
    _require(verbose_run.returncode == 0, "cannot list 7z metadata")
    names = names_run.stdout.decode("utf-8", errors="strict").splitlines()
    verbose = verbose_run.stdout.decode("utf-8", errors="replace").splitlines()
    _require(len(names) == len(verbose), "7z listing/verbose entry count differs")

    rows: list[dict[str, Any]] = []
    unsafe: list[str] = []
    for name, line in zip(names, verbose):
        if _unsafe_archive_name(name):
            unsafe.append(name)
        if name.endswith("/"):
            continue
        fields = line.split(None, 8)
        _require(len(fields) == 9, f"cannot parse 7z metadata line for {name}")
        rows.append({"path": name, "bytes": int(fields[4])})

    tree_lookup = {row["path"]: row for row in tree_rows}
    archive_lookup = {row["path"]: row for row in rows}
    missing_from_tree = sorted(set(archive_lookup) - set(tree_lookup))
    extra_in_tree = sorted(set(tree_lookup) - set(archive_lookup))
    size_mismatches = sorted(
        path
        for path in set(archive_lookup) & set(tree_lookup)
        if archive_lookup[path]["bytes"] != tree_lookup[path]["bytes"]
    )
    metadata_manifest = _metadata_manifest_sha256(rows)

    _require(len(names) == EXPECTED["iar_7z_entries"], "7z entry count changed")
    _require(len(rows) == EXPECTED["iar_7z_files"], "7z file count changed")
    _require(not unsafe, "unsafe 7z path found")
    _require(not missing_from_tree and not extra_in_tree, "7z/tree name set differs")
    _require(not size_mismatches, "7z/tree member size differs")
    _require(
        metadata_manifest == EXPECTED["iar_7z_metadata_manifest_sha256"],
        "7z metadata manifest changed",
    )

    # The supplied container exposes names/sizes but its member bytes are
    # encrypted.  Probe one ordinary member without a password.  If a future
    # local reader can stream it, compare every member byte-for-byte.
    member_stream = _run_tar(["-xOf", str(archive_path), rows[0]["path"]])
    byte_mismatches: list[str] = []
    bytes_compared = member_stream.returncode == 0
    if bytes_compared:
        for row in rows:
            streamed = _run_tar(["-xOf", str(archive_path), row["path"]])
            _require(streamed.returncode == 0, f"cannot stream 7z member {row['path']}")
            if _sha256(streamed.stdout) != tree_lookup[row["path"]]["sha256"]:
                byte_mismatches.append(row["path"])
    stream_error = member_stream.stderr.lower()
    encrypted_reported = b"encrypted" in stream_error

    nested_names = [
        row["path"]
        for row in rows
        if PurePosixPath(row["path"]).suffix.lower()
        in {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".cab"}
    ]
    return {
        "path": archive_path.as_posix(),
        "bytes": len(archive_payload),
        "sha256": archive_sha,
        "entries": len(names),
        "files": len(rows),
        "archive_metadata_manifest_sha256": metadata_manifest,
        "missing_from_extracted_tree": missing_from_tree,
        "extra_in_extracted_tree": extra_in_tree,
        "size_mismatches": size_mismatches,
        "all_member_names_and_sizes_match_extracted_tree": True,
        "member_bytes_compared": bytes_compared,
        "member_byte_mismatches": byte_mismatches,
        "local_reader_reports_encrypted_content": encrypted_reported,
        "content_identity_evidence": (
            "byte-exact"
            if bytes_compared and not byte_mismatches
            else "name-and-size-only"
        ),
        "evidence_boundary": (
            "Encrypted members cannot be streamed without the archive password; "
            "matching names and sizes do not prove byte identity."
            if not bytes_compared
            else "All member bytes were streamed and hash-compared."
        ),
        "nested_archive_filename_hits": nested_names,
    }


def _parse_ar_members(payload: bytes) -> list[tuple[str, bytes]]:
    _require(payload.startswith(b"!<arch>\n"), "loader library is not an ar archive")
    position = 8
    records: list[tuple[str, bytes]] = []
    raw_records: list[tuple[str, bytes]] = []
    while position < len(payload):
        header = payload[position : position + 60]
        _require(len(header) == 60 and header[58:60] == b"`\n", "invalid ar header")
        raw_name = header[:16].decode("ascii", errors="replace").strip()
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as error:
            raise ArtifactAuditError("invalid ar member size") from error
        start = position + 60
        end = start + size
        _require(end <= len(payload), "truncated ar member")
        raw_records.append((raw_name, payload[start:end]))
        position = end + (size & 1)

    string_table = next((body for name, body in raw_records if name == "//"), b"")
    for raw_name, body in raw_records:
        name = raw_name
        if re.fullmatch(r"/\d+", raw_name) and string_table:
            tail = string_table[int(raw_name[1:]) :]
            stops = [
                value for marker in (b"/\n", b"\n") if (value := tail.find(marker)) >= 0
            ]
            name = tail[: min(stops) if stops else len(tail)].decode(
                "ascii", errors="replace"
            )
        elif raw_name.endswith("/") and raw_name not in {"/", "//"}:
            name = raw_name[:-1]
        records.append((name, body))
    return records


def _row(lookup: dict[str, dict[str, Any]], path: str) -> dict[str, Any]:
    _require(path in lookup, f"inventoried file is missing: {path}")
    return dict(lookup[path])


def _audit_loader_library(
    root: Path,
    lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    relative = LOADER_LIBRARY_REL.as_posix()
    library_row = _row(lookup, relative)
    _require(
        library_row["sha256"] == EXPECTED["loader_library_sha256"],
        "loader library identity changed",
    )
    payload = (root / LOADER_LIBRARY_REL).read_bytes()
    members = _parse_ar_members(payload)
    object_matches = [
        (name, body) for name, body in members if name == "eload_20250305b1.o"
    ]
    _require(len(object_matches) == 1, "loader object member count changed")
    object_name, object_body = object_matches[0]
    object_sha = _sha256(object_body)
    _require(object_sha == EXPECTED["loader_object_sha256"], "loader object changed")
    macro_values = {
        name.decode("ascii"): int(value)
        for name, value in re.findall(
            rb"(E5_3Bit_Mode|WF_DeCode_SIZE|WF_SIZE) (\d+)\x00", object_body
        )
    }
    _require(
        macro_values == {"E5_3Bit_Mode": 0, "WF_DeCode_SIZE": 544, "WF_SIZE": 535},
        "loader compile macro record changed",
    )

    output = root / "Output"
    lnps = sorted(output.glob("*.lnp"))
    maps = sorted(output.glob("*.map"))
    axfs = sorted(output.glob("*.axf"))
    library_name = LOADER_LIBRARY_REL.name.encode("ascii")
    lnp_mentions = [p.name for p in lnps if library_name in p.read_bytes()]
    linked_marker_hits = [
        p.name
        for p in [*maps, *axfs]
        if any(
            marker in p.read_bytes()
            for marker in (b"loadWF", b"eload_20250305b1.o", library_name)
        )
    ]
    _require(len(lnps) == 7 and len(lnp_mentions) == 7, "library LNP inputs changed")
    _require(not linked_marker_hits, "loader now appears in a final MAP/AXF")

    return {
        "library": library_row,
        "member": {
            "path": f"{relative}::{object_name}",
            "bytes": len(object_body),
            "sha256": object_sha,
        },
        "compile_macro_values": macro_values,
        "lnp_input_count": len(lnp_mentions),
        "lnp_inputs": lnp_mentions,
        "final_map_axf_loader_marker_hits": linked_marker_hits,
        "classification": "linker-input-library-member-not-pulled",
        "evidence_level": "direct library debug record plus final MAP/AXF negative",
    }


def _load_local_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _specialized_proofs(
    stm32_root: Path,
    stm32_zip: Path,
    iar_root: Path,
) -> dict[str, Any]:
    legacy_tool_path = REPO_ROOT / "tools" / "e2802_r43_lut_proof.py"
    final_tool_path = REPO_ROOT / "tools" / "mf1750_final_axf_init_linkage_audit.py"
    legacy_tool = _load_local_module("vendor_hunt_e2802_proof", legacy_tool_path)
    final_tool = _load_local_module("vendor_hunt_final_linkage", final_tool_path)

    object_path = iar_root / IAR_PROJECT_DIR / "Debug" / "Obj" / "E2802.r43"
    legacy = legacy_tool.prove_object(object_path)
    final = final_tool.build_report(stm32_root, stm32_zip)
    upload = legacy["upload_temperature_lut"]
    return {
        "proof_tools": [
            {
                "path": legacy_tool_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(legacy_tool_path.read_bytes()),
            },
            {
                "path": final_tool_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(final_tool_path.read_bytes()),
            },
        ],
        "legacy_h3": {
            "object": legacy["object"],
            "command_20_count_bytes": upload["lut0"]["count_bytes"],
            "command_21_value": upload["lut1"]["value"],
            "command_21_count_bytes": upload["lut1"]["count_bytes"],
            "direct_binary_evidence": True,
            "same_version_as_current_stm32_delivery": False,
            "current_project_linkage_proven": False,
            "recovery_closure_proven": legacy["power_and_recovery_classification"][
                "factory_or_OTP_recovery_closure"
            ],
        },
        "delivered_final_images": {
            "axf_map_pairs": final["scope"]["identity_pinned_final_axf_map_pairs"],
            "dual_factory_init_images": final["shared_dual_factory_init"]["images"],
            "dual_factory_init_image_count": final["shared_dual_factory_init"][
                "image_count"
            ],
            "factory_psr": final["shared_dual_factory_init"]["psr_bytes"],
            "runtime_lut_upload_in_factory_trace": final["shared_dual_factory_init"][
                "runtime_lut_upload_in_trace"
            ],
            "same_build_800_byte_loader_found": final["same_build_loader_search"][
                "same_build_800_byte_loader_found"
            ],
            "wf23_classification": final["wf23_linkage"]["classification"],
        },
    }


def _historical_source_root(payload: bytes, family: str) -> str | None:
    candidates: set[str] = set()
    for match in re.finditer(rb"[A-Za-z]:[\\/]", payload):
        end = match.start()
        while (
            end < len(payload)
            and 0x20 <= payload[end] <= 0x7E
            and end - match.start() < 300
        ):
            end += 1
        value = payload[match.start() : end].decode("ascii", errors="replace")
        if (
            family.lower() in value.lower()
            and ", Line:" not in value
            and "Program Files" not in value
            and len(value) >= 8
        ):
            candidates.add(value)
    return min(candidates, key=len) if candidates else None


def _audit_iar_objects(
    iar_root: Path,
    lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    project_prefix = IAR_PROJECT_DIR.as_posix()
    object_prefix = f"{project_prefix}/Debug/Obj/"
    all_objects = sorted(
        path
        for path in lookup
        if path.startswith(object_prefix) and path.endswith(".r43")
    )
    dep_path = iar_root / IAR_PROJECT_DIR / "C2_Example.dep"
    dep_payload = dep_path.read_bytes()
    _require(
        len(dep_payload) == EXPECTED["iar_dependency_bytes"]
        and _sha256(dep_payload) == EXPECTED["iar_dependency_sha256"],
        "IAR dependency manifest identity changed",
    )
    graph_tool = _load_local_module(
        "vendor_hunt_iar_dependency_graph",
        REPO_ROOT / "tools" / "mf1750_iar_r43_cross_object_graph.py",
    )
    dependency_graph = graph_tool.parse_dependency_graph(dep_payload)
    output_table_names = dependency_graph["project_r43_output_table_names"]
    direct_project_names = dependency_graph["final_d43_direct_project_r43_input_names"]
    direct_toolkit_names = dependency_graph["final_d43_direct_toolkit_r43_input_names"]
    output_table_paths = [f"{object_prefix}{name}" for name in output_table_names]
    direct_project_paths = [f"{object_prefix}{name}" for name in direct_project_names]
    not_direct_paths = sorted(set(all_objects) - set(direct_project_paths))
    _require(len(all_objects) == 29, "IAR r43 artifact count changed")
    _require(
        len(output_table_paths) == 9,
        "IAR project-r43 dependency output-table count changed",
    )
    _require(
        direct_project_names == ["DELAY.r43", "E6_73.r43", "main.r43"],
        "IAR final-d43 direct project-r43 inputs changed",
    )
    _require(
        direct_toolkit_names == ["dl430xlsfn.r43"],
        "IAR final-d43 direct toolkit-r43 input changed",
    )
    _require(
        len(not_direct_paths) == 26,
        "IAR delivered non-direct-input r43 count changed",
    )

    e2802_path = f"{object_prefix}E2802.r43"
    e2801_path = f"{object_prefix}E2801.r43"
    _require(
        lookup[e2802_path]["sha256"] == EXPECTED["legacy_e2802_sha256"],
        "E2802.r43 identity changed",
    )
    _require(
        lookup[e2801_path]["sha256"] == EXPECTED["legacy_e2801_sha256"],
        "E2801.r43 identity changed",
    )

    residue_families = {
        "E2801.r43": "E2801",
        "E2802.r43": "E2802",
        "PENG030D01.r43": "PENG030D01",
        "PENG073D01.r43": "PENG073D01",
        "E6_73.r43": "E6",
        "EL073.r43": "EL073",
    }
    residues = []
    for name, family in residue_families.items():
        relative = f"{object_prefix}{name}"
        root = _historical_source_root((iar_root / Path(relative)).read_bytes(), family)
        if relative in direct_project_paths:
            membership = "final-d43-direct-project-r43-input"
        elif relative in output_table_paths:
            membership = "project-r43-output-table-only-not-direct-input"
        else:
            membership = "delivered-inventory-not-in-project-r43-output-table"
        residues.append(
            {
                **_row(lookup, relative),
                "historical_source_root_residue": root,
                "dependency_membership": membership,
            }
        )

    return {
        "dependency_manifest": _row(lookup, f"{project_prefix}/C2_Example.dep"),
        "all_r43_count": len(all_objects),
        "dependency_semantics": {
            "output_file_table_is_not_direct_link_input_membership": True,
            "project_r43_output_table_count": len(output_table_paths),
            "final_d43_direct_project_r43_input_count": len(direct_project_paths),
            "final_d43_direct_toolkit_r43_inputs": direct_toolkit_names,
            "final_d43_direct_xlink_input_rows": dependency_graph[
                "final_d43_direct_xlink_input_rows"
            ],
        },
        "project_r43_output_table": [
            {
                **_row(lookup, path),
                "classification": (
                    "final-d43-direct-project-r43-input"
                    if path in direct_project_paths
                    else "project-r43-output-table-only-not-direct-input"
                ),
            }
            for path in output_table_paths
        ],
        "final_d43_direct_project_r43_inputs": [
            {
                **_row(lookup, path),
                "classification": "final-d43-direct-project-r43-input",
            }
            for path in direct_project_paths
        ],
        "delivered_r43_not_direct_inputs": [
            {
                **_row(lookup, path),
                "classification": "delivered-inventory-not-final-d43-direct-input",
            }
            for path in not_direct_paths
        ],
        "path_residues": residues,
        "classification_boundary": (
            "The DEP output file table records producer outputs and is not a link-input "
            "membership list. Only the final-d43 inputs/XLINK relation proves direct "
            "membership for this configuration. Absence there does not prove an object "
            "was never linked in another build or reached indirectly through a library."
        ),
    }


def _classified_stm32_artifacts(
    root: Path,
    lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    backup_contracts = {
        "Sample Code/main.c.bak": EXPECTED["main_backup_sha256"],
        "Sample Code/comm.h.bak": EXPECTED["comm_backup_sha256"],
        "Sample Code/pindefine.h.bak": EXPECTED["pin_backup_sha256"],
    }
    backups = []
    for path, expected_sha in backup_contracts.items():
        row = _row(lookup, path)
        _require(row["sha256"] == expected_sha, f"backup identity changed: {path}")
        backups.append({**row, "classification": "backup-editor-only"})

    wf23 = _row(lookup, WF23_REL.as_posix())
    _require(wf23["sha256"] == EXPECTED["wf23_editor_file_sha256"], "WF23 changed")
    project_payload = (root / PROJECT_REL).read_bytes()
    editor_payload = (root / EDITOR_STATE_REL).read_bytes()
    wf23_editor_hex_marker = b"5C313200000000023132"
    extensionless = {
        **wf23,
        "classification": "editor-only-not-built",
        "listed_in_project": b"WF23_25" in project_payload,
        "editor_state_path_residue_found": wf23_editor_hex_marker in editor_payload,
        "editor_state": _row(lookup, EDITOR_STATE_REL.as_posix()),
    }
    _require(not extensionless["listed_in_project"], "WF23 is now in the project")
    _require(
        extensionless["editor_state_path_residue_found"],
        "WF23 editor-state path residue changed",
    )

    final_outputs = []
    for suffix in (".axf", ".map", ".hex"):
        for path in sorted(
            key for key in lookup if key.startswith("Output/") and key.endswith(suffix)
        ):
            final_outputs.append(
                {
                    **_row(lookup, path),
                    "classification": (
                        "linked-final-image"
                        if suffix in {".axf", ".map"}
                        else "final-hex-output"
                    ),
                }
            )
    _require(
        sum(row["path"].endswith(".axf") for row in final_outputs) == 7,
        "final AXF count changed",
    )
    _require(
        sum(row["path"].endswith(".map") for row in final_outputs) == 7,
        "final MAP count changed",
    )
    _require(
        sum(row["path"].endswith(".hex") for row in final_outputs) == 7,
        "final HEX count changed",
    )

    sample_main = (root / "Sample Code" / "main.c").read_text(
        encoding="utf-8", errors="ignore"
    )
    backup_main = (root / "Sample Code" / "main.c.bak").read_text(
        encoding="utf-8", errors="ignore"
    )
    all_paths = set(lookup)
    missing_profile_pairings = {
        "current_source": {
            "source": _row(lookup, "Sample Code/main.c"),
            "reference": "WF00_05",
            "referenced": "WF00_05" in sample_main,
            "matching_named_file_found": any("WF00_05" in path for path in all_paths),
            "classification": "source-present-profile-definition-missing",
        },
        "backup_source": {
            "source": _row(lookup, "Sample Code/main.c.bak"),
            "reference": "WF25_25",
            "referenced": "WF25_25" in backup_main,
            "matching_named_file_found": any("WF25_25" in path for path in all_paths),
            "classification": "backup-only-profile-definition-missing",
        },
    }
    _require(
        not missing_profile_pairings["current_source"]["matching_named_file_found"],
        "WF00_05 pairing unexpectedly appeared",
    )
    _require(
        not missing_profile_pairings["backup_source"]["matching_named_file_found"],
        "WF25_25 pairing unexpectedly appeared",
    )

    return {
        "backups": backups,
        "extensionless_wf23": extensionless,
        "final_outputs": final_outputs,
        "missing_profile_pairings": missing_profile_pairings,
        "source_and_debug_classes": [
            {
                **_row(lookup, "User/EDP_init.c"),
                "classification": "source-linked-dual-factory-infrastructure",
            },
            {
                **_row(lookup, "Sample Code/E28xx.c"),
                "classification": "source-linked-loader-glue-without-dual-loader-routing",
            },
            {
                **_row(lookup, "Sample Code/main.c"),
                "classification": "source-present-not-current-project-main",
            },
            {
                **_row(lookup, "Output/e28xx.crf"),
                "classification": "debug-metadata-loadWF-declaration-only",
            },
            {
                **_row(lookup, "Output/main.crf"),
                "classification": "debug-metadata-loadWF-declaration-only",
            },
        ],
    }


def _combine_marker_hits(
    *scoped_hits: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for marker_name in MARKERS:
        hits = [hit for group in scoped_hits for hit in group[marker_name]]
        result[marker_name] = {
            "alternatives_checked": len(MARKERS[marker_name]),
            "files_with_hits": len(hits),
            "total_occurrences": sum(hit["occurrences"] for hit in hits),
            "hits": hits,
        }
    return result


def build_report(
    stm32_root: Path = DEFAULT_STM32_ROOT,
    stm32_zip: Path = DEFAULT_STM32_ZIP,
    iar_root: Path = DEFAULT_IAR_ROOT,
    iar_7z: Path = DEFAULT_IAR_7Z,
    *,
    include_file_manifests: bool = False,
) -> dict[str, Any]:
    stm32_tree, stm32_rows, stm32_markers = _inventory_tree(
        stm32_root, scope_name="stm32_vendor_tree"
    )
    iar_tree, iar_rows, iar_markers = _inventory_tree(
        iar_root, scope_name="iar_vendor_tree"
    )
    _require(
        (stm32_tree["files"], stm32_tree["bytes"], stm32_tree["manifest_sha256"])
        == (
            EXPECTED["stm32_tree_files"],
            EXPECTED["stm32_tree_bytes"],
            EXPECTED["stm32_tree_manifest_sha256"],
        ),
        "STM32 vendor tree manifest changed",
    )
    _require(
        (iar_tree["files"], iar_tree["bytes"], iar_tree["manifest_sha256"])
        == (
            EXPECTED["iar_tree_files"],
            EXPECTED["iar_tree_bytes"],
            EXPECTED["iar_tree_manifest_sha256"],
        ),
        "IAR vendor tree manifest changed",
    )

    stm32_lookup = {row["path"]: row for row in stm32_rows}
    iar_lookup = {row["path"]: row for row in iar_rows}
    marker_report = _combine_marker_hits(stm32_markers, iar_markers)
    stm32_zip_report = _audit_stm32_zip(stm32_zip, stm32_root, stm32_rows)
    iar_7z_report = _audit_iar_7z(iar_7z, iar_rows)
    loader = _audit_loader_library(stm32_root, stm32_lookup)
    specialized = _specialized_proofs(stm32_root, stm32_zip, iar_root)
    iar_objects = _audit_iar_objects(iar_root, iar_lookup)
    classified_stm32 = _classified_stm32_artifacts(stm32_root, stm32_lookup)

    mode1_named_hits = sum(
        marker_report[name]["files_with_hits"]
        for name in (
            "compile_E5_3Bit_Mode_1",
            "compile_WF_DeCode_SIZE_800",
            "compile_WF_DeCode_SIZE_809",
            "compile_WF_SIZE_799",
        )
    )
    _require(mode1_named_hits == 0, "a named mode-1/800 loader marker appeared")
    _require(
        specialized["delivered_final_images"]["same_build_800_byte_loader_found"]
        is False,
        "same-build 800-byte loader unexpectedly found",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "vendor_trees": 2,
            "files": stm32_tree["files"] + iar_tree["files"],
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_requested": False,
            "raw_waveform_emitted": False,
            "key_material_emitted": False,
        },
        "trees": {
            "stm32_vendor": stm32_tree,
            "iar_vendor": iar_tree,
        },
        "archives": {
            "stm32_zip": stm32_zip_report,
            "iar_7z": iar_7z_report,
        },
        "marker_search": marker_report,
        "loader_library": loader,
        "specialized_binary_and_linkage_proofs": specialized,
        "iar_object_provenance": iar_objects,
        "stm32_artifact_provenance": classified_stm32,
        "negative_search_boundary": {
            "additional_identity_distinct_named_mode1_or_800_loader_found": False,
            "same_build_mode1_or_800_loader_found_in_seven_final_pairs": False,
            "wording": (
                "No additional identity-distinct named mode-1/800 loader was found "
                "in the 430 identity-pinned extracted vendor files or the byte-exact "
                "ZIP contents. This is not proof that unpublished, encrypted-only, "
                "anonymous, or out-of-scope code does not exist."
            ),
        },
        "delta": {
            "new_reproducibility_increments": [
                "The 364-file ZIP/tree equality is byte-exact after 14 GBK name fixes.",
                "The encrypted 7z/tree equality is only name-and-size exact; member-byte identity remains unproven.",
                "C2_Example.dep is parsed as XML: its output table mentions 9 delivered project r43 objects, while the final-d43 XLINK relation directly selects only DELAY, E6_73, and main plus one toolkit r43 library.",
                "The three backups, extensionless WF23 editor file, final AXF/MAP/HEX identities, and debug-only loadWF residues are enumerated separately.",
            ],
            "confirmed_prior_conclusions": [
                "The only delivered loader library is mode 0 with decode size 544 and WF size 535.",
                "The legacy E2802 object directly proves 0x20/799 plus 0x21/704xFF, but is not a final-d43 direct input and is cross-version.",
                "Dual ToBoth infrastructure and five dual factory initializers are linked, while no delivered final image links the 800-byte loader.",
                "WF23 is vendor-supplied but editor-only; WF00_05 and WF25_25 source references have no paired definition file.",
                "No artifact closes a same-version dual runtime-loader plus verified recovery call chain.",
            ],
        },
    }
    if include_file_manifests:
        report["file_manifests"] = {
            "stm32_vendor": stm32_rows,
            "iar_vendor": iar_rows,
        }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stm32-root", type=Path, default=DEFAULT_STM32_ROOT)
    parser.add_argument("--stm32-zip", type=Path, default=DEFAULT_STM32_ZIP)
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--iar-7z", type=Path, default=DEFAULT_IAR_7Z)
    parser.add_argument("--include-file-manifests", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(
            args.stm32_root,
            args.stm32_zip,
            args.iar_root,
            args.iar_7z,
            include_file_manifests=args.include_file_manifests,
        )
    except (ArtifactAuditError, OSError, ValueError, KeyError) as error:
        print(f"artifact audit failed: {error}", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    json.dump(
        report,
        sys.stdout,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
