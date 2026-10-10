#!/usr/bin/env python3
"""Close the delivered ArmCC/Keil mode-1 residual search offline.

The broader vendor artifact hunt already identity-pins both extracted trees and
their original archives.  This audit adds the missing configuration layer: the
Keil project/options/dependency snapshot, every retained LNP/scatter/final pair,
editor and cleanup residue, the single Arm archive member, and the ambiguous
``79661.csv`` analyzer export.  It emits identities, names, symbols, counts, and
bounded verdicts only; it never emits waveform bytes or key material.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import write_new_bytes_durable  # noqa: E402
from tools import mf1750_armcc_loadwf_deep_audit as armcc  # noqa: E402
from tools import mf1750_spd1657_reverse_delta as reverse_delta  # noqa: E402
from tools import mf1750_stm32_loadwf_abi_boundary_audit as abi_boundary  # noqa: E402
from tools import mf1750_vendor_artifact_hunt as artifact_hunt  # noqa: E402


KIND = "mf1750-armcc-mode1-residual-audit"
SCHEMA_VERSION = 1
DEFAULT_STM32_ROOT = artifact_hunt.DEFAULT_STM32_ROOT
DEFAULT_IAR_ROOT = artifact_hunt.DEFAULT_IAR_ROOT

PROJECT_REL = Path("Projects/MDK-ARM/atk_f103.uvprojx")
OPTIONS_REL = Path("Projects/MDK-ARM/atk_f103.uvoptx")
ADMIN_GUI_REL = Path("Projects/MDK-ARM/atk_f103.uvguix.Administrator")
ZHANG_GUI_REL = Path("Projects/MDK-ARM/atk_f103.uvguix.zhangweijia")
DEPENDENCY_REL = Path("Output/atk_f103_USART.dep")
CLEANUP_REL = Path("keilkill.bat")
CAPTURE_REL = Path("79661.csv")
EXTENSIONLESS_REL = Path("Projects/MDK-ARM/12")
LIBRARY_REL = artifact_hunt.LOADER_LIBRARY_REL

EXPECTED_IDENTITIES: dict[Path, tuple[int, str]] = {
    PROJECT_REL: (
        22_696,
        "2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8",
    ),
    OPTIONS_REL: (
        24_696,
        "99ca1fe15f077ed1a4c7171fd31be903d5361787c22fd89463912ee69bcfd9a6",
    ),
    ADMIN_GUI_REL: (
        196_072,
        "313c944967fbec713ea4fc318d264e43533cc0b23bcb3e53b873cd12fe1fd800",
    ),
    ZHANG_GUI_REL: (
        185_650,
        "b76db4a3e1522960b0f07cf7315138e9b4d1880e303830fadbdf48b557a8a257",
    ),
    DEPENDENCY_REL: (
        173_109,
        "7bde5e25582d4429922be07c01dac9b737ed2a3cfe16397871c8f080befbd769",
    ),
    CLEANUP_REL: (
        443,
        "c843dec4cdb7dcb5257c2373bfdf00d2bd7afd85073a279f1f2c213d91e92832",
    ),
    CAPTURE_REL: (
        370_580,
        "3dd08472fc1fc75866381c6963a2cf35787c712aaa8ff8256687ec86bcac159d",
    ),
    EXTENSIONLESS_REL: (
        5_776,
        "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d",
    ),
}

MODE_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "E5_3Bit_Mode": re.compile(
        r"(?<![A-Za-z0-9_])(?:-D\s*)?E5_3Bit_Mode\s*(?:=\s*|\s+)(\d+)"
        r"(?![0-9])",
        re.IGNORECASE,
    ),
    "WF_DeCode_SIZE": re.compile(
        r"(?<![A-Za-z0-9_])(?:-D\s*)?WF_DeCode_SIZE\s*(?:=\s*|\s+)(\d+)"
        r"(?![0-9])",
        re.IGNORECASE,
    ),
    "WF_SIZE": re.compile(
        r"(?<![A-Za-z0-9_])(?:-D\s*)?WF_SIZE\s*(?:=\s*|\s+)(\d+)"
        r"(?![0-9])",
        re.IGNORECASE,
    ),
}

CLEANUP_SUFFIXES = (
    ".bak",
    ".ddk",
    ".edk",
    ".lst",
    ".lnp",
    ".mpf",
    ".mpj",
    ".obj",
    ".omf",
    ".plg",
    ".rpt",
    ".tmp",
    ".__i",
    ".crf",
    ".o",
    ".d",
    ".axf",
    ".tra",
    ".dep",
    ".iex",
    ".htm",
    ".sct",
    ".map",
    ".dbgconf",
    ".administrator",
)


class ResidualAuditError(RuntimeError):
    """Raised when a pinned identity or structural invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResidualAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _identity(path: Path, root: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _read_pinned(root: Path, relative: Path) -> bytes:
    path = root / relative
    _require(path.is_file(), f"missing pinned artifact: {relative.as_posix()}")
    payload = path.read_bytes()
    expected_bytes, expected_sha = EXPECTED_IDENTITIES[relative]
    _require(len(payload) == expected_bytes, f"size changed: {relative.as_posix()}")
    _require(_sha256(payload) == expected_sha, f"SHA changed: {relative.as_posix()}")
    return payload


def _printable_ascii(payload: bytes) -> str:
    return "\n".join(
        item.decode("ascii") for item in re.findall(rb"[\x20-\x7e]{4,}", payload)
    )


def _text_views(path: Path) -> list[tuple[str, str]]:
    payload = path.read_bytes()
    views = [("ascii", _printable_ascii(payload))]
    little = re.findall(rb"(?:[\x20-\x7e]\x00){4,}", payload)
    big = re.findall(rb"(?:\x00[\x20-\x7e]){4,}", payload)
    if little:
        views.append(("utf16le", "\n".join(item.decode("utf-16le") for item in little)))
    if big:
        views.append(("utf16be", "\n".join(item.decode("utf-16be") for item in big)))

    if path.name.startswith("atk_f103.uvguix."):
        text = payload.decode("utf-8")
        decoded_parts: list[bytes] = []
        for encoded in re.findall(r"<Data>([0-9A-Fa-f]+)</Data>", text):
            if len(encoded) % 2 == 0:
                decoded_parts.append(bytes.fromhex(encoded))
        if decoded_parts:
            views.append(
                ("uvguix_hex_data", _printable_ascii(b"\n".join(decoded_parts)))
            )
    return views


def _scan_mode_bindings(
    stm32_root: Path,
    iar_root: Path,
) -> dict[str, object]:
    roots = (("stm32", stm32_root), ("iar", iar_root))
    bindings: dict[str, dict[str, list[dict[str, object]]]] = {
        name: {} for name in MODE_VALUE_PATTERNS
    }
    for scope, root in roots:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            for encoding, view in _text_views(path):
                for name, pattern in MODE_VALUE_PATTERNS.items():
                    counts: dict[str, int] = {}
                    for match in pattern.finditer(view):
                        value = match.group(1)
                        counts[value] = counts.get(value, 0) + 1
                    for value, occurrences in counts.items():
                        bindings[name].setdefault(value, []).append(
                            {
                                "scope": scope,
                                "path": path.relative_to(root).as_posix(),
                                "encoding": encoding,
                                "occurrences": occurrences,
                                "bytes": path.stat().st_size,
                                "sha256": _sha256(path.read_bytes()),
                            }
                        )

    result: dict[str, object] = {}
    for name, values in bindings.items():
        result[name] = {
            "values": {
                value: {
                    "occurrences": sum(int(row["occurrences"]) for row in rows),
                    "hits": rows,
                }
                for value, rows in sorted(values.items(), key=lambda item: int(item[0]))
            }
        }
    return result


def _parse_project(project_payload: bytes, options_payload: bytes) -> dict[str, object]:
    project = ET.fromstring(project_payload)
    options = ET.fromstring(options_payload)
    targets: list[dict[str, object]] = []
    for target in project.findall("./Targets/Target"):
        defines: list[str] = []
        for node in target.findall(".//Define"):
            if node.text:
                defines.extend(
                    part.strip() for part in node.text.split(",") if part.strip()
                )
        library_refs = sorted(
            node.text.replace("\\", "/")
            for node in target.findall(".//FilePath")
            if node.text and node.text.lower().endswith((".lib", ".a"))
        )
        scatter_files = sorted(
            node.text.replace("\\", "/")
            for node in target.findall(".//ScatterFile")
            if node.text and node.text.strip()
        )
        targets.append(
            {
                "name": target.findtext("TargetName"),
                "output_name": target.findtext(
                    "./TargetOption/TargetCommonOption/OutputName"
                ),
                "defines": sorted(set(defines)),
                "file_records": len(target.findall(".//File")),
                "library_references": library_refs,
                "nonempty_scatter_file_overrides": scatter_files,
            }
        )

    option_library_refs = sorted(
        node.text.replace("\\", "/")
        for node in options.findall(".//PathWithFileName")
        if node.text and node.text.lower().endswith((".lib", ".a"))
    )
    option_file_records = len(options.findall(".//PathWithFileName"))
    option_targets = []
    for target in options.findall("./Target"):
        option_targets.append(
            {
                "name": target.findtext("TargetName"),
                "is_current_target": target.findtext(".//IsCurrentTarget") == "1",
                "file_records": option_file_records,
                "library_references": option_library_refs,
            }
        )
    return {"uvprojx_targets": targets, "uvoptx_targets": option_targets}


def _parse_dependency(root: Path, payload: bytes) -> dict[str, object]:
    text = payload.decode("latin-1")
    header = re.search(r"Dependencies for Project '([^']+)', Target '([^']+)'", text)
    compiler = re.search(r"^CompilerVersion: ([^\r\n]+)", text, re.MULTILINE)
    _require(header is not None and compiler is not None, "dependency header changed")
    library_records = re.findall(
        r"^F \(([^)]*\.(?:lib|a))\)\([^)]*\)\(([^)]*)\)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    defines = sorted(set(re.findall(r"(?<!\S)-D([^\s)]+)", text)))
    return {
        "identity": _identity(root / DEPENDENCY_REL, root),
        "project": header.group(1),
        "target": header.group(2),
        "compiler_version_record": compiler.group(1),
        "file_records": len(re.findall(r"^F \(", text, re.MULTILINE)),
        "include_records": len(re.findall(r"^I \(", text, re.MULTILINE)),
        "compile_defines": defines,
        "library_records": [
            {
                "path": path.replace("\\", "/"),
                "compiler_flags": flags,
            }
            for path, flags in library_records
        ],
        "loader_source_record_present": "eload_20250305b1.c" in text,
        "wf20_include_record_present": "WF20_25.h" in text,
        "wf23_include_record_present": "WF23_25" in text,
    }


def _parse_library(
    root: Path,
    deep: dict[str, Any],
) -> dict[str, object]:
    library_path = root / LIBRARY_REL
    payload = library_path.read_bytes()
    records = artifact_hunt._parse_ar_members(payload)
    object_rows = [
        {"name": name, "bytes": len(body), "sha256": _sha256(body)}
        for name, body in records
        if name not in {"/", "//"}
    ]
    object_payload = next(
        body for name, body in records if name == "eload_20250305b1.o"
    )
    printable = _printable_ascii(object_payload)
    compiler = re.search(
        r"Component: (ARM Compiler 5\.06 update \d+ \(build \d+\))", printable
    )
    _require(compiler is not None, "loader compiler marker changed")
    macro_values = {
        row["name"]: row["value"]
        for row in deep["compiler_and_macros"]["source_macro_records"]
    }
    delivered_source = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("eload_20250305b1.c")
        if path.is_file()
    )
    symbols = deep["archive"]["archive_public_symbols"]
    return {
        "identity": _identity(library_path, root),
        "ar_records": len(records),
        "object_members": object_rows,
        "public_symbols": symbols,
        "loadwf_named_public_symbols": [
            name for name in symbols if "loadwf" in name.lower()
        ],
        "retained_source_macros": macro_values,
        "compiler": compiler.group(1),
        "compile_cpu_cortex_m3_marker_present": "--cpu=Cortex-M3" in printable,
        "compile_cpu_lpc54606_define_present": "-DCPU_LPC54606" in printable,
        "source_basename": "eload_20250305b1.c",
        "source_delivered": bool(delivered_source),
        "delivered_source_paths": delivered_source,
        "prebuilt_object_not_recompiled_by_stm32_project": True,
    }


def _lnp_inputs(path: Path) -> list[str]:
    inputs = []
    for line in path.read_bytes().decode("latin-1").splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and stripped.endswith('"'):
            inputs.append(stripped[1:-1].replace("\\", "/").lower())
    return inputs


def _output_chain(root: Path, current_output: str) -> dict[str, object]:
    output = root / "Output"
    lnps = sorted(output.glob("*.lnp"))
    rows = []
    input_hashes: set[str] = set()
    for path in lnps:
        inputs = _lnp_inputs(path)
        input_hash = _sha256(("\n".join(inputs) + "\n").encode("utf-8"))
        input_hashes.add(input_hash)
        libraries = [item for item in inputs if item.endswith((".lib", ".a"))]
        rows.append(
            {
                **_identity(path, root),
                "link_inputs": len(inputs),
                "object_inputs": sum(item.endswith(".o") for item in inputs),
                "library_inputs": libraries,
                "normalized_input_list_sha256": input_hash,
            }
        )

    marker_names = (
        b"loadWF",
        LIBRARY_REL.name.encode("ascii"),
        b"eload_20250305b1.o",
        b"E5_3Bit_Mode",
        b"WF_DeCode_SIZE",
        b"WF_SIZE",
    )
    final_marker_hits = []
    for path in sorted([*output.glob("*.map"), *output.glob("*.axf")]):
        payload = path.read_bytes()
        hits = [marker.decode("ascii") for marker in marker_names if marker in payload]
        if hits:
            final_marker_hits.append({**_identity(path, root), "markers": hits})

    scatters = sorted(output.glob("*.sct"))
    scatter_rows = [_identity(path, root) for path in scatters]
    output_basenames = sorted(path.stem for path in lnps)
    build_logs = []
    for path in sorted(output.glob("*.build_log.htm")):
        text = path.read_bytes().decode("latin-1")
        target = re.search(r"(?:Build|Rebuild) target '([^']+)'", text)
        compiler = re.search(r"Armcc\.exe ([^\r\n<]+)", text)
        _require(
            target is not None and compiler is not None, "build log marker changed"
        )
        build_logs.append(
            {
                "path": path.relative_to(root).as_posix(),
                "target": target.group(1),
                "compiler": compiler.group(1).strip(),
            }
        )

    return {
        "lnp_files": rows,
        "lnp_count": len(rows),
        "all_lnp_input_lists_identical": len(input_hashes) == 1,
        "normalized_input_list_sha256": next(iter(input_hashes)),
        "scatter_files": scatter_rows,
        "scatter_count": len(scatter_rows),
        "unique_scatter_sha256": sorted({row["sha256"] for row in scatter_rows}),
        "map_axf_loader_or_mode_marker_hits": final_marker_hits,
        "map_files": len(list(output.glob("*.map"))),
        "axf_files": len(list(output.glob("*.axf"))),
        "build_logs": build_logs,
        "current_project_output_name": current_output,
        "current_output_pair_present": current_output in output_basenames,
        "output_basenames_not_declared_by_current_project_snapshot": [
            name for name in output_basenames if name != current_output
        ],
        "older_output_name_is_alternate_target_or_mode_proven": False,
    }


def _cleanup_residue(root: Path, payload: bytes) -> dict[str, object]:
    files = [path for path in root.rglob("*") if path.is_file()]
    counts = {
        suffix: sum(path.name.lower().endswith(suffix) for path in files)
        for suffix in CLEANUP_SUFFIXES
    }
    text = payload.decode("latin-1").lower()
    for suffix in CLEANUP_SUFFIXES:
        _require(suffix in text, f"cleanup suffix disappeared: {suffix}")
    temp_like = sorted(
        path.relative_to(root).as_posix()
        for path in files
        if path.name.lower().endswith(
            (".tmp", ".temp", ".old", ".orig", ".save", ".autosave", "~")
        )
    )
    return {
        "identity": _identity(root / CLEANUP_REL, root),
        "cleanup_target_suffix_counts": counts,
        "jlinklog_named_files": sum(
            path.name.lower() == "jlinklog.txt" for path in files
        ),
        "generic_temp_or_old_filename_hits": temp_like,
        "cleanup_script_execution_time_or_success_proven": False,
        "residues_are_present_in_original_zip": True,
    }


def _editor_residue(root: Path) -> dict[str, object]:
    rows = []
    project_markers = {"REG-API-FOG": 0, "WF-JD79661-128X296": 0}
    for relative in (ADMIN_GUI_REL, ZHANG_GUI_REL):
        path = root / relative
        document = ET.fromstring(path.read_bytes())
        strings = [
            node.text
            for node in document.iter()
            if node.tag in {"LastAddFilePath", "Name"} and node.text
        ]
        for marker in project_markers:
            project_markers[marker] += sum(
                marker.lower() in value.lower() for value in strings
            )
        hex_elements = [
            node.text
            for node in document.iter("Data")
            if node.text and re.fullmatch(r"[0-9A-Fa-f]+", node.text)
        ]
        rows.append(
            {
                **_identity(path, root),
                "path_or_name_records": len(strings),
                "hex_data_elements": len(hex_elements),
            }
        )
    return {
        "editor_state_files": rows,
        "external_or_older_project_path_markers": [
            {
                "project_tail": marker,
                "path_records": count,
                "matching_delivered_project_tree_found": any(
                    marker.lower() in path.name.lower()
                    for path in root.rglob("*")
                    if path.is_dir()
                ),
            }
            for marker, count in project_markers.items()
        ],
        "extensionless_editor_artifact": {
            **_identity(root / EXTENSIONLESS_REL, root),
            "profile_identifier": "WF23_25",
            "listed_in_current_uvprojx": False,
            "classification": "EDITOR_ONLY_NOT_BUILT",
        },
        "editor_path_residue_is_delivered_source_or_object": False,
    }


def _capture_metadata(root: Path) -> dict[str, object]:
    path = root / CAPTURE_REL
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        packet_ids: list[int] = []
        miso_values: set[int] = set()
        rows = 0
        for row in reader:
            rows += 1
            packet_ids.append(int(row["Packet ID"]))
            int(row["MOSI"], 16)
            miso_values.add(int(row["MISO"], 16))
            float(row["Time [s]"])
    expected_ids = list(range(rows))
    index_constants = (704, 799, 800, 1503)
    return {
        "identity": _identity(path, root),
        "columns": columns,
        "rows": rows,
        "packet_id_first": packet_ids[0],
        "packet_id_last": packet_ids[-1],
        "packet_ids_are_contiguous_zero_based": packet_ids == expected_ids,
        "miso_unique_values": sorted(miso_values),
        "packet_id_rows_named_like_lut_sizes": {
            str(value): value in packet_ids for value in index_constants
        },
        "those_decimal_values_are_packet_indices_not_declared_lengths": True,
        "chip_select_column_present": bool(columns and "CS" in columns),
        "data_command_column_present": bool(columns and "D/C" in columns),
        "controller_or_target_column_present": bool(
            columns and any(name in columns for name in ("controller", "target"))
        ),
        "transaction_boundaries_proven": False,
        "filename_matches_editor_project_numeric_tail": "79661",
        "filename_to_editor_project_provenance_binding": False,
        "proves_799_or_1503_plus_704_loader_contract": False,
        "raw_mosi_or_waveform_content_emitted": False,
    }


def _iar_boundary(
    vendor: dict[str, Any],
    reverse: dict[str, Any],
) -> dict[str, object]:
    legacy = reverse["legacy_iar_e2802"]
    direct_names = {
        Path(row["path"]).name
        for row in vendor["iar_object_provenance"][
            "final_d43_direct_project_r43_inputs"
        ]
    }
    runtime = legacy["reverse_engineered_runtime_sequence"]
    return {
        "object": {
            "path": legacy["path"],
            "bytes": legacy["bytes"],
            "sha256": legacy["sha256"],
            "format": legacy["format"],
        },
        "resident_constants": {
            "DATA0_bytes": legacy["data0"]["bytes"],
            "DATA0_layout_formula": legacy["data0"]["layout_formula"],
            "DATA1_bytes": legacy["data1"]["bytes"],
            "DATA1_layout_formula": legacy["data1"]["layout_formula"],
            "DATA1_referenced_by_active_upload_path": legacy["data1"][
                "referenced_by_active_upload_path"
            ],
        },
        "active_legacy_upload_transactions": [
            {
                "command": row["command"],
                "parameter_bytes": row["parameter_bytes"],
            }
            for row in runtime["transactions"]
        ],
        "direct_final_d43_input": "E2802.r43" in direct_names,
        "same_generation_as_current_armcc_loader": runtime[
            "same_generation_as_current_armcc_loader"
        ],
        "can_uniquely_prove_current_mode1_contract": runtime[
            "can_uniquely_prove_current_mode1_contract"
        ],
        "1503_and_704_are_armcc_mode1_macro_values": False,
    }


def build_report(
    stm32_root: Path = DEFAULT_STM32_ROOT,
    iar_root: Path = DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build a deterministic, metadata-only residual closure report."""

    stm32_root = stm32_root.resolve()
    iar_root = iar_root.resolve()
    _require(stm32_root.is_dir(), f"missing STM32 root: {stm32_root}")
    _require(iar_root.is_dir(), f"missing IAR root: {iar_root}")
    pinned = {
        relative.as_posix(): _read_pinned(stm32_root, relative)
        for relative in EXPECTED_IDENTITIES
    }

    vendor = artifact_hunt.build_report(stm32_root=stm32_root, iar_root=iar_root)
    deep = armcc.build_report(stm32_root / LIBRARY_REL)
    boundary = abi_boundary.build_report(reference_root=stm32_root)
    reverse = reverse_delta.build_report(reference_root=stm32_root)

    _require(vendor["kind"] == artifact_hunt.KIND, "vendor audit kind changed")
    _require(deep["kind"] == armcc.KIND, "ArmCC audit kind changed")
    _require(boundary["kind"] == abi_boundary.KIND, "ABI audit kind changed")
    _require(reverse["kind"] == reverse_delta.KIND, "reverse audit kind changed")
    _require(
        vendor["archives"]["stm32_zip"]["all_extracted_file_bytes_match"],
        "STM32 ZIP/tree byte identity changed",
    )

    project = _parse_project(
        pinned[PROJECT_REL.as_posix()], pinned[OPTIONS_REL.as_posix()]
    )
    _require(len(project["uvprojx_targets"]) == 1, "project target count changed")
    current_target = project["uvprojx_targets"][0]
    _require(current_target["name"] == "USART", "current target changed")
    _require(
        current_target["output_name"] == "jiaxian-M009F-T_OQC_YX",
        "current output name changed",
    )

    dependency = _parse_dependency(stm32_root, pinned[DEPENDENCY_REL.as_posix()])
    library = _parse_library(stm32_root, deep)
    mode_scan = _scan_mode_bindings(stm32_root, iar_root)
    _require(
        set(mode_scan["E5_3Bit_Mode"]["values"]) == {"0"},
        "E5_3Bit_Mode residual values changed",
    )
    _require(
        set(mode_scan["WF_DeCode_SIZE"]["values"]) == {"544"},
        "WF_DeCode_SIZE residual values changed",
    )
    _require(
        set(mode_scan["WF_SIZE"]["values"]) == {"535"},
        "WF_SIZE residual values changed",
    )
    for marker in mode_scan.values():
        for value in marker["values"].values():
            _require(
                len(value["hits"]) == 1
                and value["hits"][0]["path"] == LIBRARY_REL.as_posix(),
                "mode macro escaped the single library",
            )

    output_chain = _output_chain(stm32_root, str(current_target["output_name"]))
    _require(output_chain["lnp_count"] == 7, "LNP count changed")
    _require(output_chain["all_lnp_input_lists_identical"], "LNP inputs diverged")
    _require(
        not output_chain["map_axf_loader_or_mode_marker_hits"], "final marker appeared"
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "stm32_files": vendor["trees"]["stm32_vendor"]["files"],
            "iar_files": vendor["trees"]["iar_vendor"]["files"],
            "original_stm32_zip_byte_compared": True,
            "original_iar_7z_member_bytes_compared": vendor["archives"]["iar_7z"][
                "member_bytes_compared"
            ],
            "offline_read_only": True,
        },
        "upstream_cross_checks": {
            "vendor_artifact_hunt": {
                "kind": vendor["kind"],
                "schema_version": vendor["schema_version"],
                "stm32_tree_manifest_sha256": vendor["trees"]["stm32_vendor"][
                    "manifest_sha256"
                ],
                "iar_tree_manifest_sha256": vendor["trees"]["iar_vendor"][
                    "manifest_sha256"
                ],
                "stm32_zip_sha256": vendor["archives"]["stm32_zip"]["sha256"],
                "iar_7z_sha256": vendor["archives"]["iar_7z"]["sha256"],
            },
            "armcc_deep_audit": {
                "kind": deep["kind"],
                "schema_version": deep["schema_version"],
                "same_object_799_byte_write_present": deep["strict_negative_findings"][
                    "same_object_799_byte_write_present"
                ],
            },
            "abi_boundary_audit": {
                "kind": boundary["kind"],
                "schema_version": boundary["schema_version"],
                "current_armcc_800_compatible": boundary["candidate_800_records"][
                    "current_armcc_loader_compatible"
                ],
                "adjudication": boundary["adjudication"]["800_byte_current_armcc_abi"],
            },
        },
        "project_and_options": {
            "identities": {
                PROJECT_REL.as_posix(): _identity(stm32_root / PROJECT_REL, stm32_root),
                OPTIONS_REL.as_posix(): _identity(stm32_root / OPTIONS_REL, stm32_root),
            },
            **project,
        },
        "keil_dependency_snapshot": dependency,
        "arm_archive": library,
        "multiencoding_mode_value_scan": {
            "encodings_checked": [
                "printable ASCII",
                "UTF-16LE printable ASCII subset",
                "UTF-16BE printable ASCII subset",
                "decoded hexadecimal Data elements in both uvguix files",
            ],
            "files_checked": vendor["scope"]["files"],
            "bindings": mode_scan,
            "mode1_or_800_or_799_value_binding_found": False,
        },
        "output_link_chain": output_chain,
        "cleanup_and_temp_residue": _cleanup_residue(
            stm32_root, pinned[CLEANUP_REL.as_posix()]
        ),
        "editor_residue": _editor_residue(stm32_root),
        "spi_analyzer_export": _capture_metadata(stm32_root),
        "legacy_iar_1503_704_boundary": _iar_boundary(vendor, reverse),
        "adjudication": {
            "additional_identity_distinct_armcc_library_found": False,
            "alternate_armcc_object_member_found": False,
            "delivered_recompilable_loader_source_found": False,
            "mode1_project_define_found": False,
            "mode1_or_800_loader_value_binding_found": False,
            "project_defines_can_recompile_or_select_prebuilt_library_branch": False,
            "same_build_mode1_800_loader_found": False,
            "editor_or_capture_residue_promoted_to_code_evidence": False,
            "verdict": "NO_ADDITIONAL_MODE1_ARMCC_ARTIFACT_IN_PINNED_DELIVERY",
            "authorizes_live_hardware_action": False,
        },
        "evidence_boundaries": {
            "negative_scope": (
                "The negative is bounded to the exact 364-file STM32 tree and its "
                "byte-identical ZIP, plus the exact 66-file extracted IAR tree."
            ),
            "encrypted_iar_7z_boundary": vendor["archives"]["iar_7z"][
                "evidence_boundary"
            ],
            "editor_paths_are_file_presence_proof": False,
            "numeric_packet_ids_are_transaction_length_proof": False,
            "map_or_axf_plaintext_marker_absence_is_global_nonexistence_proof": False,
            "unpublished_or_out_of_scope_artifacts_excluded": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "raw_waveform_emitted": False,
            "customer_key_material_emitted": False,
            "runtime_payload_generated": False,
            "vendor_evidence_modified": False,
        },
    }
    report["report_canonical_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _serialize(report: dict[str, Any], compact: bool) -> bytes:
    if compact:
        text = json.dumps(
            report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    else:
        text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    return (text + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stm32-root", type=Path, default=DEFAULT_STM32_ROOT)
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.stm32_root, args.iar_root)
        payload = _serialize(report, args.compact)
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        ET.ParseError,
        ResidualAuditError,
        artifact_hunt.ArtifactAuditError,
        armcc.DeepAuditError,
        abi_boundary.AbiBoundaryAuditError,
        reverse_delta.ReverseAuditError,
    ) as error:
        print(f"ArmCC mode-1 residual audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
