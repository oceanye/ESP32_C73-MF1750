#!/usr/bin/env python3
"""Recover symbol metadata from three exact UBROF11 objects via E2 projection.

IAR XLIB 6.1.3.56 accepts UBROF11 generally but has the documented EW25659
failure on files carrying stack-usage information: ``Unknown tag: E2``.  No
record-level grammar for E2 was found in the two cited official sources; this
bounded search does not claim that no other official material exists.  This
tool therefore is not a general UBROF parser and never edits an original
object.

For the three identity-pinned delivered objects only, it validates an observed
``E2 + one-byte length + payload`` framing at an exact allowlist of offsets,
elides those records into a temporary metadata projection, recomputes the
module CRC, and asks the identity-pinned official XLIB to list EXTERNAL and
ENTRY symbols.  The resulting tables are official XLIB output for the
projection, not a native parse of the unmodified object.  The report keeps that
evidence distinction explicit and cross-checks all 52 observed external-index
call sites against the projected ordered EXTERNAL tables.

No waveform/object/disassembly bytes are emitted.  No hardware, serial port,
device network, firmware, reset, refresh, or authorization path is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_xlib_external_index_audit as legacy


KIND = "mf1750-iar-ubrof11-e2-projection-audit"
SCHEMA_VERSION = 2

OFFICIAL_RELEASE_NOTES_URL = legacy.OFFICIAL_XLINK_RELEASE_NOTES
OFFICIAL_RECORD_TAG_NOTE_URL = (
    "https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/UBROFRecordTags.pdf"
)
MSPGCC_CVS_SNAPSHOT_URL = "https://sourceforge.net/code-snapshots/cvs/m/ms/mspgcc.zip"
MSPGCC_ARCHIVE_IDENTITY = {
    "size_bytes": 9_827_966,
    "sha256": "8bd887ea38c5cc814ab098413f3684285362803e9b2c3b05d0679e62ddeb4940",
}
MSPGCC_RCS_MEMBER_IDENTITY = {
    "path": "mspgcc/ubroff/ubrof.c,v",
    "size_bytes": 13_691,
    "sha256": "cfda845435a1b2fd51b79d5e4d5056adf0a418b098f8afde149acd7701529c4d",
    "extracted_revision_size_bytes": 13_469,
    "extracted_revision_sha256": (
        "0a9466c28aac12030f8e4152becc0225593f2838de302bc7aac95a4bd98d4cb2"
    ),
}

EXPECTED_OBJECTS: dict[str, dict[str, Any]] = {
    "DELAY.r43": {
        "size_bytes": 1_774,
        "sha256": "82eaf1f5ae2ee28f7df7dafb7e9ecf8b46731d7f98784a4731d9b49f638c96da",
        "spans": (
            (0x6A6, 11, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x6DF, 11, "INFERRED_STACK_CATALOG_E2"),
        ),
        "false_e2_bytes_remaining": 0,
        "projection_size_bytes": 1_752,
        "projection_sha256": (
            "18ce50ec409d40de3834aabd2b838dc032a666cd7cc57f740c223d34fa2e3785"
        ),
        "projection_crc": "76C2",
        "external_count": 4,
        "external_table_sha256": (
            "e5f3a3c5c7c7600b82515fcfb7f25d33e1be8ccd0af4b36520475d2855fa64c0"
        ),
        "entry_count": 3,
        "entry_table_sha256": (
            "3f8891f007a7b7e91e9ed3575d144628d17b1aad21bc24e41d279cb8af615fd0"
        ),
    },
    "E6_73.r43": {
        "size_bytes": 109_582,
        "sha256": "0f4d22c6d07f79d9ededffd50f155dc96d802b0e90bf908c30f2b85f1714ee2f",
        "spans": (
            (0x36FC, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x39D4, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x3C30, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x4C87, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0xA870, 44, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0xAC73, 23, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0xB061, 23, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0xCF3A, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0xEE02, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x10CD0, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x12B92, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x14A58, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x16922, 30, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x16D1A, 23, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x1788E, 37, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x1894E, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x199ED, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x1ABC1, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x1ABFF, 11, "INFERRED_STACK_CATALOG_E2"),
        ),
        "false_e2_bytes_remaining": 10,
        "projection_size_bytes": 109_129,
        "projection_sha256": (
            "a06470e270a5a8030d03da9be9dbd5ac3e3636fe9a8c9fc141081dfd84bd187c"
        ),
        "projection_crc": "D6DC",
        "external_count": 5,
        "external_table_sha256": (
            "6622984c44bce3f0e177c885faf2f3000481895e77f5eaa8f371cf16c8c5a8fd"
        ),
        "entry_count": 25,
        "entry_table_sha256": (
            "ba611d907e96d06a4fc63185c4f0a1ae70bed507ac9871229dee28c08c6e418d"
        ),
    },
    "main.r43": {
        "size_bytes": 29_684,
        "sha256": "76ada9c8846226457ef74537a345ca1e057e8c11abc1002423424dfffd2640f4",
        "spans": (
            (0x4801, 11, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x4FD2, 16, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x7368, 79, "INFERRED_FUNCTION_ASSOCIATED_E2"),
            (0x73E5, 11, "INFERRED_STACK_CATALOG_E2"),
        ),
        "false_e2_bytes_remaining": 0,
        "projection_size_bytes": 29_567,
        "projection_sha256": (
            "f872802e612ee315ef1d90788ae7b447872ed4137a0f71800c84c0e907d2015d"
        ),
        "projection_crc": "9CCB",
        "external_count": 13,
        "external_table_sha256": (
            "d45b04df375364ed726b859bef26e3fc8e7648a2e9c9d6d898052644f670cd18"
        ),
        "entry_count": 26,
        "entry_table_sha256": (
            "9b4f2ef7847c0f6be05f4fe47f01319314b9659ffe1ef39e2cacba02a2f4c80e"
        ),
    },
}

STACK_CATALOG_RECORD = b"\xe2\x09\x02\x01\x06CSTACK"


class E2ProjectionAuditError(RuntimeError):
    """An identity, framing, CRC, official-tool, or cross-check invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E2ProjectionAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def ubrof_module_crc(payload_through_end_tag: bytes) -> int:
    """Return the observed UBROF module CRC used by all 29 delivered objects.

    This is comparative, non-IAR grammar evidence.  The 2002 experimental
    mspgcc UBROF5 decoder shifts a 16-bit register left, feeds every input byte
    least-significant bit first, XORs polynomial 0x8005, and starts at zero.
    """

    crc = 0
    for value in payload_through_end_tag:
        for _ in range(8):
            feedback = (value & 1) ^ ((crc >> 15) & 1)
            crc = (crc << 1) & 0xFFFF
            if feedback:
                crc ^= 0x8005
            value >>= 1
    return crc


def _stored_module_crc(payload: bytes) -> int:
    _require(len(payload) >= 4, "object is too short for UBROF module trailer")
    _require(payload[-4] == 0x3F, "object lost observed T_END byte")
    _require(payload[-1] == 0xFF, "object lost observed UBROF EOF byte")
    return int.from_bytes(payload[-3:-1], "big")


def _validate_crc(payload: bytes, label: str) -> str:
    stored = _stored_module_crc(payload)
    computed = ubrof_module_crc(payload[:-3])
    _require(stored == computed, f"{label} module CRC mismatch")
    return f"{stored:04X}"


def validate_all_delivered_crcs(iar_root: Path) -> dict[str, Any]:
    """Validate the comparative CRC routine against the 29 pinned r43 objects."""

    object_dir = iar_root / graph.OBJECT_DIR_REL
    manifest: list[dict[str, Any]] = []
    for name in sorted(graph.EXPECTED_OBJECTS, key=str.casefold):
        size, digest, version = graph.EXPECTED_OBJECTS[name]
        payload = (object_dir / name).read_bytes()
        _require(len(payload) == size, f"{name} size mismatch")
        _require(_sha256(payload) == digest, f"{name} SHA-256 mismatch")
        _require(payload[1] == version, f"{name} UBROF version mismatch")
        manifest.append({"name": name, "crc": _validate_crc(payload, name)})
    return {
        "objects_checked": len(manifest),
        "objects_matching": len(manifest),
        "all_29_match": len(manifest) == 29,
        "crc_manifest_sha256": _sha256(_canonical_bytes(manifest)),
    }


def _pin_target_object(path: Path, expected: dict[str, Any]) -> bytes:
    payload = path.read_bytes()
    _require(
        len(payload) == expected["size_bytes"],
        f"{path.name} size mismatch",
    )
    _require(
        _sha256(payload) == expected["sha256"],
        f"{path.name} SHA-256 mismatch",
    )
    _require(payload[:2] == b"\x01\x0b", f"{path.name} is not pinned UBROF11")
    _validate_crc(payload, path.name)
    return payload


def _scoped_names(payload: bytes) -> list[str]:
    return [
        str(row["name"])
        for row in graph._symbol_name_records(payload)  # noqa: SLF001
    ]


def project_exact_object(name: str, payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Build one exact, CRC-valid E2-elided metadata projection.

    Offsets are an allowlist for the pinned identity, not a scanner.  Incidental
    E2 bytes in nested debug records or MSP430 code are deliberately retained.
    """

    _require(name in EXPECTED_OBJECTS, f"unsupported projection object: {name}")
    expected = EXPECTED_OBJECTS[name]
    _require(len(payload) == expected["size_bytes"], f"{name} size changed")
    _require(_sha256(payload) == expected["sha256"], f"{name} identity changed")
    names = _scoped_names(payload)
    spans: list[tuple[int, int]] = []
    function_names: list[str] = []
    rows: list[dict[str, Any]] = []

    for offset, total_length, record_class in expected["spans"]:
        end = offset + total_length
        _require(end <= len(payload) - 3, f"{name} E2 span is out of range")
        _require(payload[offset] == 0xE2, f"{name} E2 tag changed at {offset:#x}")
        _require(
            payload[offset + 1] + 2 == total_length,
            f"{name} inferred E2 length changed at {offset:#x}",
        )
        if record_class == "INFERRED_FUNCTION_ASSOCIATED_E2":
            _require(
                payload[offset - 1] == 0x49,
                f"{name} function-E2 predecessor changed at {offset:#x}",
            )
            _require(
                payload[end] == 0xC7,
                f"{name} function-E2 successor changed at {offset:#x}",
            )
            body = payload[offset + 2 : end]
            _require(
                len(body) >= 5 and body[:4] == b"\0\0\0\0",
                f"{name} function-E2 observed name prefix changed at {offset:#x}",
            )
            name_index = body[4]
            _require(name_index < len(names), f"{name} E2 name index is out of range")
            function_names.append(names[name_index])
        else:
            _require(
                payload[offset:end] == STACK_CATALOG_RECORD,
                f"{name} stack-catalog record changed",
            )
            _require(
                payload[offset - 1] == 0x9C and payload[end] == 0x3F,
                f"{name} stack-catalog context changed",
            )
        spans.append((offset, end))
        rows.append(
            {
                "file_offset": f"0x{offset:X}",
                "record_class": record_class,
                "classification_is_inferred": True,
                "total_length": total_length,
            }
        )

    for (_, end), (next_start, _) in zip(spans, spans[1:]):
        _require(end <= next_start, f"{name} E2 spans overlap")

    projection = bytearray(payload)
    for start, end in reversed(spans):
        del projection[start:end]
    projection[-3:-1] = ubrof_module_crc(bytes(projection[:-3])).to_bytes(2, "big")
    projected = bytes(projection)

    _require(
        projected[:2] == b"\x01\x0b",
        f"{name} projection changed the UBROF major version",
    )
    _require(
        projected.count(0xE2) == expected["false_e2_bytes_remaining"],
        f"{name} incidental E2 retention changed",
    )
    _require(
        len(projected) == expected["projection_size_bytes"],
        f"{name} projection size changed",
    )
    _require(
        _sha256(projected) == expected["projection_sha256"],
        f"{name} projection SHA-256 changed",
    )
    projection_crc = _validate_crc(projected, f"{name} projection")
    _require(
        projection_crc == expected["projection_crc"],
        f"{name} projection CRC changed",
    )

    metadata = {
        "selected_record_count": len(rows),
        "inferred_function_associated_record_count": len(function_names),
        "inferred_stack_catalog_record_count": len(rows) - len(function_names),
        "bytes_elided": len(payload) - len(projected),
        "incidental_E2_bytes_retained": projected.count(0xE2),
        "record_manifest": rows,
        "record_manifest_sha256": _sha256(_canonical_bytes(rows)),
        "referenced_function_names": function_names,
        "referenced_function_manifest_sha256": _sha256(
            _canonical_bytes(function_names)
        ),
        "projection_size_bytes": len(projected),
        "projection_sha256": _sha256(projected),
        "projection_crc": projection_crc,
        "original_UBROF_version_retained": True,
        "original_object_modified": False,
    }
    return projected, metadata


def _run_original_boundary(xlib_path: Path, object_path: Path) -> dict[str, Any]:
    externals, entries = legacy._default_runner(  # noqa: SLF001
        xlib_path, object_path
    )
    _require(
        externals["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
        f"{object_path.name} original no longer hits E2 boundary",
    )
    _require(
        entries["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
        f"{object_path.name} original entry listing no longer hits E2 boundary",
    )
    return {
        "LIST_EXTERNALS_status": externals["status"],
        "LIST_ENTRIES_status": entries["status"],
        "diagnostic": legacy.UNKNOWN_E2,
    }


def _run_projection_lists(
    xlib_path: Path,
    projected: bytes,
    name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="mf1750-ubrof11-e2-projection-") as temp:
        path = Path(temp) / name
        path.write_bytes(projected)
        return legacy._default_runner(xlib_path, path)  # noqa: SLF001


def _cross_check_external_calls(
    edges: list[dict[str, Any]],
    tables: dict[str, list[str]],
) -> dict[str, Any]:
    grouped = legacy._group_external_calls(edges)  # noqa: SLF001
    checked = 0
    mismatches: list[dict[str, Any]] = []
    observed_indices: dict[str, list[dict[str, Any]]] = {}
    for name in EXPECTED_OBJECTS:
        calls = grouped.get(name, [])
        observed_indices[name] = legacy._observed_index_rows(calls)  # noqa: SLF001
        external_names = tables[name]
        for call in calls:
            index = int(str(call["target_id"]), 0)
            actual = external_names[index] if index < len(external_names) else None
            if actual != call["callee_symbol"]:
                mismatches.append(
                    {
                        "object": name,
                        "external_index": index,
                        "observed_debug_symbol": call["callee_symbol"],
                        "projected_XLIB_symbol": actual,
                    }
                )
            checked += 1
    _require(checked == 52, f"expected 52 UBROF11 external-index calls, got {checked}")
    _require(not mismatches, f"projected XLIB external-table mismatches: {mismatches}")
    return {
        "paired_external_index_calls_checked": checked,
        "mismatch_count": 0,
        "zero_mismatch": True,
        "observed_indices": observed_indices,
    }


def build_report(
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build the deterministic metadata-only projection audit."""

    xlib_identity = legacy._pin_xlib(xlib_path)  # noqa: SLF001
    graph_report = graph.build_report(iar_root, include_all_edges=True)
    crc_validation = validate_all_delivered_crcs(iar_root)
    object_dir = iar_root / graph.OBJECT_DIR_REL

    objects: dict[str, Any] = {}
    external_tables: dict[str, list[str]] = {}
    total_function_records = 0
    total_records = 0
    total_bytes_elided = 0

    for name, expected in EXPECTED_OBJECTS.items():
        path = object_dir / name
        original = _pin_target_object(path, expected)
        original_boundary = _run_original_boundary(xlib_path, path)
        projected, projection_metadata = project_exact_object(name, original)
        externals, entries = _run_projection_lists(xlib_path, projected, name)
        _require(externals["status"] == "PARSED", f"{name} projection externals failed")
        _require(entries["status"] == "PARSED", f"{name} projection entries failed")
        external_names = list(externals["symbols"])
        entry_names = list(entries["symbols"])
        _require(
            len(external_names) == expected["external_count"],
            f"{name} external count changed",
        )
        _require(
            len(entry_names) == expected["entry_count"], f"{name} entry count changed"
        )
        _require(
            externals["table_sha256"] == expected["external_table_sha256"],
            f"{name} external table changed",
        )
        _require(
            entries["table_sha256"] == expected["entry_table_sha256"],
            f"{name} entry table changed",
        )
        external_tables[name] = external_names
        total_function_records += projection_metadata[
            "inferred_function_associated_record_count"
        ]
        total_records += projection_metadata["selected_record_count"]
        total_bytes_elided += projection_metadata["bytes_elided"]
        objects[name] = {
            "original_identity": {
                "size_bytes": len(original),
                "sha256": _sha256(original),
                "UBROF_version_byte": original[1],
                "module_crc": f"{_stored_module_crc(original):04X}",
            },
            "original_official_XLIB": original_boundary,
            "experimental_identity_pinned_projection": projection_metadata,
            "official_XLIB_on_projection": {
                "external_count": len(external_names),
                "external_table_sha256": externals["table_sha256"],
                "external_index_table": [
                    {"external_index": index, "symbol": symbol}
                    for index, symbol in enumerate(external_names)
                ],
                "entry_count": len(entry_names),
                "entry_table_sha256": entries["table_sha256"],
                "entry_table": entry_names,
            },
        }

    call_cross_check = _cross_check_external_calls(
        graph_report["graph"]["edges"], external_tables
    )
    _require(total_records == 25, "selected E2 record total changed")
    _require(total_function_records == 22, "function E2 record total changed")
    _require(total_bytes_elided == 592, "E2 byte total changed")

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "pure_software": True,
            "input_objects": 3,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refresh_requested": False,
            "authorization_token_or_claim_used": False,
            "network_accessed_by_this_tool": False,
            "original_objects_modified": False,
            "temporary_projection_only": True,
            "raw_object_bytes_emitted": False,
            "raw_waveform_or_LUT_bytes_emitted": False,
            "raw_disassembly_emitted": False,
        },
        "official_XLIB": xlib_identity,
        "public_evidence": {
            "IAR_release_notes": {
                "url": OFFICIAL_RELEASE_NOTES_URL,
                "supported_claim": (
                    "EW25659 associates Unknown tag E2 with UBROF stack-usage "
                    "information and records the XLIB fix in 6.3.4.78"
                ),
                "record_level_E2_grammar_published_there": False,
            },
            "IAR_2005_record_tag_note": {
                "url": OFFICIAL_RECORD_TAG_NOTE_URL,
                "supported_claim": (
                    "semantic UBROF record families are named; a byte-level E2 "
                    "grammar is not supplied"
                ),
                "predates_UBROF11": True,
            },
            "third_party_comparative_CRC_source": {
                "url": MSPGCC_CVS_SNAPSHOT_URL,
                "classification": "EXPERIMENTAL_UBROF5_DECODER_NOT_IAR_SPECIFICATION",
                "archive_identity": MSPGCC_ARCHIVE_IDENTITY,
                "RCS_member_identity": MSPGCC_RCS_MEMBER_IDENTITY,
                "algorithm": (
                    "init 0; each byte LSB-first; 16-bit left shift; polynomial 0x8005"
                ),
                "validated_against_delivered_objects": crc_validation,
            },
        },
        "projection_method": {
            "general_UBROF_parser": False,
            "general_E2_scanner": False,
            "identity_pinned_offset_allowlist": True,
            "inferred_record_framing": "E2 + one-byte payload length + payload",
            "official_record_level_E2_grammar_found_in_cited_sources": False,
            "global_official_E2_grammar_absence_claimed": False,
            "all_E2_record_classification_is_inferred": True,
            "selected_E2_records": total_records,
            "inferred_function_associated_E2_records": total_function_records,
            "inferred_stack_catalog_E2_records": total_records - total_function_records,
            "bytes_elided": total_bytes_elided,
            "UBROF_major_version_rewritten": False,
            "CRC_recomputed": True,
            "projection_is_a_link_or_flash_input": False,
        },
        "objects": objects,
        "external_index_cross_check": call_cross_check,
        "adjudication": {
            "verdict": (
                "EXACT_E2_ELIDED_PROJECTIONS_PARSE_AND_ALL_52_EXTERNAL_INDEX_"
                "CALLS_MATCH_BUT_NATIVE_ORIGINAL_TABLES_REMAIN_UNPARSED"
            ),
            "projected_symbol_tables_recovered": True,
            "unmodified_objects_natively_parsed": False,
            "projection_metadata_usable_only_with_evidence_label": True,
            "native_original_metadata_claim_allowed": False,
            "safe_link_flash_or_object_replacement_use": False,
            "meaning": (
                "For the three exact pinned objects, removing only 25 observed E2 "
                "stack records and repairing the independently validated module CRC "
                "lets the pinned official XLIB list ordered EXTERNAL/ENTRY metadata. "
                "All 52 paired external-index calls agree. Because neither cited "
                "official source supplies an E2 byte grammar, these are official "
                "XLIB tables for a deterministic projection, not a native parse of "
                "the originals."
            ),
        },
        "remaining_boundary": {
            "native_original_EXTERNAL_ENTRY_tables": (
                "requires an identity-pinned official XLIB 6.3.4.78 or newer"
            ),
            "general_UBROF11_E2_parser": "not established",
            "official_E2_grammar_search_scope": (
                "the two cited official sources only; global absence is not claimed"
            ),
            "E2_stack_parameter_semantics": "not promoted beyond observed framing and name references",
            "SPD1657_runtime_LUT_ABI_or_electrical_parameters": "not addressed by this audit",
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _discover_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
    if configured:
        return Path(configured).resolve()
    candidate = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        / "Temp/iar_ew430_6201_xlink_only/component_430_xlink_common/430/bin/xlib.exe"
    )
    return candidate.resolve() if candidate.is_file() else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", type=Path, default=_discover_xlib())
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require(args.xlib is not None, "identity-pinned XLIB path is required")
        report = build_report(args.xlib.resolve(), args.iar_root.resolve())
        payload = (
            _canonical_bytes(report) + b"\n"
            if args.compact
            else (
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
        )
        if args.output:
            write_new_bytes_durable(args.output.resolve(), payload)
        else:
            sys.stdout.buffer.write(payload)
    except (
        E2ProjectionAuditError,
        legacy.XlibAuditError,
        graph.GraphError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
