#!/usr/bin/env python3
"""Recover the observed MSP430 UBROF11 E2 stack-usage dialect, boundedly.

This audit is deliberately narrower than an official UBROF11 parser.  It
discovers E2 records without an offset allowlist in three delivered objects and
in an optional, identity-pinned public comparison corpus.  The recovered
sample dialect has three observed forms:

* a function record with no call-graph-root category;
* a function record with the ``interrupt`` root category; and
* a one-stack catalog naming ``CSTACK``.

Function records carry an observed namespace-1 scoped-name reference, a stack
vector width, and terminal/direct-call path entries.  All structural field
names remain inferred because the cited IAR material establishes that UBROF11
added stack-usage information and documents the XLIB ``Unknown tag: E2`` bug,
but does not publish the E2 byte grammar.

The identity-pinned XLIB 6.1.3.56 is used only as a differential oracle: every
unmodified sample stops at the documented E2 bug, while temporary E2-elided,
CRC-repaired projections parse.  That is evidence for record boundaries, not
a native parse of any original and not permission to link, replace, or flash a
projection.  No object, waveform, disassembly, or firmware bytes are emitted.
No hardware, serial port, device network, reset, refresh, or authorization path
is touched.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_ubrof11_e2_projection_audit as projection
from tools import mf1750_iar_xlib_external_index_audit as legacy


KIND = "mf1750-iar-ubrof11-e2-grammar-audit"
SCHEMA_VERSION = 1

OFFICIAL_XLINK_NOTES_URL = (
    "https://updates.iar.com/FileStore/STANDARD/001/000/590/ew/doc/"
    "infocenter/xlink.ENU.html"
)
OFFICIAL_MSP430_XMAN_URL = (
    "https://updates.iar.com/SuppDB/Public/UPDINFO/013105/430/doc/"
    "infocenter/xman.ENU.html"
)
OFFICIAL_2005_RECORD_NOTE_URL = projection.OFFICIAL_RECORD_TAG_NOTE_URL

EXPECTED_DELIVERED_SOURCES = {
    "DELAY.C": {
        "size_bytes": 101,
        "sha256": "9c6d39202e1eef3f3c9ae300cd20311ef8813567e2c44331dbf8e62a227f6ee3",
    },
    "E6_73.c": {
        "size_bytes": 9_182,
        "sha256": "8f511aca743bcd55d751d6d935261733b5931eb2fa101bb6d9f815cd0a8b06e9",
    },
    "main.c": {
        "size_bytes": 5_278,
        "sha256": "b39520e578a257d0c9146fb4c84f65cd5f92743b12e6681c78a658733da710af",
    },
}

PUBLIC_REPOS: dict[str, dict[str, Any]] = {
    "andersonethan44/RemoteControlledCar": {
        "commit": "eb4e81be84cbd0fb889a587a1423420c86175278",
        "checkout_name": "andersonethan44__RemoteControlledCar",
        "url": "https://github.com/andersonethan44/RemoteControlledCar",
        "expected_UBROF11_objects": 19,
        "object_manifest_sha256": (
            "8b6e569972f77e0fdce0125cf60d4f4ebbe9d936c737dd53b24c2570024cbe69"
        ),
        "anchor": {
            "path": "Debug/List/Project_08.map",
            "size_bytes": 127_778,
            "sha256": "a7d0fb461cf66f936f3d4e0d2f66465247d564f4b257f10f68d197bdd8ae8c20",
            "git_blob_sha1": "bd278ac672b9accd19ba473d867b486bdd7e39b5",
            "classification": "THIRD_PARTY_COMMITTED_IAR_LINKER_MAP",
        },
    },
    "hrishikeshkarande/MSP430G2453_IAR_Quantum_Leap": {
        "commit": "82c5d7e29f6250a89d35913df9cf4d8ac4cd38f1",
        "checkout_name": "hrishikeshkarande__MSP430G2453_IAR_Quantum_Leap",
        "url": "https://github.com/hrishikeshkarande/MSP430G2453_IAR_Quantum_Leap",
        "expected_UBROF11_objects": 6,
        "object_manifest_sha256": (
            "e9db62eb68188fda956abfc82a9de8f86f3f718cce1d837dfabc4f0008942ba8"
        ),
    },
    "kevinbird61/2015-MSP430-IAR": {
        "commit": "e5b45ca63c21b469ddd2b830e994f4bd4d0d4dc1",
        "checkout_name": "kevinbird61__2015-MSP430-IAR",
        "url": "https://github.com/kevinbird61/2015-MSP430-IAR",
        "expected_UBROF11_objects": 4,
        "object_manifest_sha256": (
            "5e5bab1f6a8d10c22471bd2ea89ed097ab13b788c993501928e22138a4b7b7e7"
        ),
        "anchor": {
            "path": "lab5/main.c",
            "size_bytes": 384,
            "sha256": "2e3772a75764c171e15567da0bf844778b243450663c5859c851b9983744d1d4",
            "git_blob_sha1": "93e67711f4c0ed215adaadd4e50216e8f9145abf",
            "classification": "THIRD_PARTY_COMMITTED_SOURCE",
        },
    },
}

EXPECTED_PUBLIC_CORPUS_MANIFEST_SHA256 = (
    "8a0708b799e8065634a3d611ab2978c6fc82d6829cc8efef28d04bf6f241957a"
)


class E2GrammarAuditError(RuntimeError):
    """An identity, grammar, projection, or differential invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E2GrammarAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hex(value: int) -> str:
    return f"0x{value:X}"


def _find_all(payload: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    start = 0
    while True:
        offset = payload.find(needle, start)
        if offset < 0:
            return result
        result.append(offset)
        start = offset + 1


def parse_namespace1_scoped_names(payload: bytes) -> list[dict[str, Any]]:
    """Decode the complete observed namespace-1 T_SCOPED_NAME sequence.

    Unlike the older landmark helper, this retains alias records whose final
    four-byte reference is not FFFFFFFF.  Those records are required to keep
    the numeric namespace stable for interrupt functions.
    """

    records: list[dict[str, Any]] = []
    for offset in _find_all(payload, b"\xcd\x00\x00\x00"):
        if offset + 5 > len(payload):
            continue
        record_length = payload[offset + 4]
        body = payload[offset + 5 : offset + 5 + record_length]
        if len(body) < 9 or body[:4] != b"\x01\x00\x00\x00":
            continue
        name_length = body[4]
        if len(body) != 9 + name_length:
            continue
        raw_name = body[5 : 5 + name_length]
        if not raw_name or any(value < 0x20 or value > 0x7E for value in raw_name):
            continue
        trailing_reference = int.from_bytes(body[-4:], "big")
        records.append(
            {
                "index": len(records),
                "file_offset_int": offset,
                "name": raw_name.decode("ascii"),
                "trailing_reference": trailing_reference,
                "is_unbound": trailing_reference == 0xFFFFFFFF,
            }
        )
    _require(records, "no observed namespace-1 scoped names")
    return records


def _read_ascii_vector(
    payload: bytes, cursor: int, count: int
) -> tuple[list[str], int]:
    values: list[str] = []
    for _ in range(count):
        if cursor >= len(payload):
            raise E2GrammarAuditError("truncated E2 string vector")
        length = payload[cursor]
        cursor += 1
        if length == 0 or cursor + length > len(payload):
            raise E2GrammarAuditError("invalid E2 string length")
        raw = payload[cursor : cursor + length]
        if any(value < 0x20 or value > 0x7E for value in raw):
            raise E2GrammarAuditError("non-ASCII E2 string")
        values.append(raw.decode("ascii"))
        cursor += length
    return values, cursor


def parse_function_payload(body: bytes) -> dict[str, Any]:
    """Parse the bounded function form observed in the pinned MSP430 corpus."""

    _require(bool(body), "empty E2 function payload")
    cursor = 0
    root_category_count = body[cursor]
    cursor += 1
    root_categories, cursor = _read_ascii_vector(body, cursor, root_category_count)
    _require(cursor + 6 <= len(body), "truncated E2 function header")
    caller_index = int.from_bytes(body[cursor : cursor + 4], "big")
    cursor += 4
    stack_vector_width = body[cursor]
    cursor += 1
    path_count = body[cursor]
    cursor += 1
    _require(stack_vector_width > 0, "zero E2 stack-vector width")
    _require(path_count > 0, "zero E2 path count")

    paths: list[dict[str, Any]] = []
    for _ in range(path_count):
        _require(cursor < len(body), "truncated E2 path kind")
        path_kind = body[cursor]
        cursor += 1
        _require(
            cursor + stack_vector_width <= len(body),
            "truncated E2 stack vector",
        )
        stack_vector = list(body[cursor : cursor + stack_vector_width])
        cursor += stack_vector_width
        if path_kind == 0:
            paths.append(
                {
                    "path_kind": 0,
                    "inferred_role": "TERMINAL_NO_CALLEE_PATH",
                    "stack_byte_vector": stack_vector,
                }
            )
            continue
        _require(path_kind == 1, f"unobserved E2 path kind {path_kind}")
        _require(cursor + 5 <= len(body), "truncated E2 direct-call path")
        callee_index = int.from_bytes(body[cursor : cursor + 4], "big")
        cursor += 4
        unknown_tail = body[cursor]
        cursor += 1
        _require(unknown_tail == 0, "nonzero E2 direct-call tail is unobserved")
        paths.append(
            {
                "path_kind": 1,
                "inferred_role": "DIRECT_CALLEE_PATH",
                "stack_byte_vector": stack_vector,
                "callee_index": callee_index,
                "unknown_tail_u8": unknown_tail,
            }
        )

    _require(cursor == len(body), "E2 function payload has trailing bytes")
    return {
        "root_categories": root_categories,
        "caller_index": caller_index,
        "stack_vector_width": stack_vector_width,
        "paths": paths,
    }


def parse_stack_catalog_payload(body: bytes) -> dict[str, Any]:
    """Parse the bounded subtype-2 stack-name catalog."""

    _require(len(body) >= 2, "short E2 stack catalog")
    _require(body[0] == 2, "E2 stack catalog subtype is not 2")
    stack_count = body[1]
    _require(stack_count > 0, "empty E2 stack catalog")
    names, cursor = _read_ascii_vector(body, 2, stack_count)
    _require(cursor == len(body), "E2 stack catalog has trailing bytes")
    return {"stack_names": names}


def scan_observed_e2_records(payload: bytes) -> dict[str, Any]:
    """Discover observed records by grammar and context, never by offset."""

    names = parse_namespace1_scoped_names(payload)
    records: list[dict[str, Any]] = []
    rejected = Counter()
    for offset, value in enumerate(payload[:-1]):
        if value != 0xE2:
            continue
        payload_length = payload[offset + 1]
        end = offset + 2 + payload_length
        if end >= len(payload):
            rejected["LENGTH_OUT_OF_RANGE"] += 1
            continue
        body = payload[offset + 2 : end]
        predecessor = payload[offset - 1] if offset else None
        successor = payload[end]
        if predecessor == 0x49 and successor == 0xC7:
            try:
                parsed = parse_function_payload(body)
            except E2GrammarAuditError:
                rejected["FUNCTION_CONTEXT_BODY_REJECTED"] += 1
                continue
            caller_index = int(parsed["caller_index"])
            if caller_index >= len(names):
                rejected["FUNCTION_CALLER_REFERENCE_OUT_OF_RANGE"] += 1
                continue
            bad_callee = any(
                path["path_kind"] == 1 and int(path["callee_index"]) >= len(names)
                for path in parsed["paths"]
            )
            if bad_callee:
                rejected["FUNCTION_CALLEE_REFERENCE_OUT_OF_RANGE"] += 1
                continue
            roots = list(parsed["root_categories"])
            if not roots:
                record_class = "FUNCTION_NO_ROOT_CATEGORY"
            elif roots == ["interrupt"]:
                record_class = "FUNCTION_INTERRUPT_ROOT"
            else:
                record_class = "FUNCTION_OTHER_ROOT_CATEGORY"
            caller = names[caller_index]
            path_rows: list[dict[str, Any]] = []
            for path in parsed["paths"]:
                row = dict(path)
                if path["path_kind"] == 1:
                    callee_index = int(path["callee_index"])
                    row["callee_name"] = names[callee_index]["name"]
                path_rows.append(row)
            alias_names = [
                row["name"]
                for row in names
                if row["trailing_reference"] == caller_index
                and str(row["name"]).startswith("??INTVEC ")
            ]
            records.append(
                {
                    "file_offset_int": offset,
                    "end_offset_int": end,
                    "payload_length": payload_length,
                    "record_class": record_class,
                    "root_categories": roots,
                    "caller_index": caller_index,
                    "caller_name": caller["name"],
                    "stack_vector_width": parsed["stack_vector_width"],
                    "paths": path_rows,
                    "interrupt_vector_aliases": alias_names,
                }
            )
            continue
        if successor == 0x3F:
            try:
                parsed_catalog = parse_stack_catalog_payload(body)
            except E2GrammarAuditError:
                rejected["END_CONTEXT_CATALOG_BODY_REJECTED"] += 1
                continue
            records.append(
                {
                    "file_offset_int": offset,
                    "end_offset_int": end,
                    "payload_length": payload_length,
                    "record_class": "STACK_CATALOG",
                    "stack_names": parsed_catalog["stack_names"],
                }
            )
            continue
        rejected["NO_OBSERVED_RECORD_CONTEXT"] += 1

    records.sort(key=lambda row: int(row["file_offset_int"]))
    for left, right in zip(records, records[1:]):
        _require(
            int(left["end_offset_int"]) <= int(right["file_offset_int"]),
            "discovered E2 records overlap",
        )
    catalogs = [row for row in records if row["record_class"] == "STACK_CATALOG"]
    _require(len(catalogs) == 1, f"expected one E2 stack catalog, got {len(catalogs)}")
    stack_names = list(catalogs[0]["stack_names"])
    _require(stack_names == ["CSTACK"], f"unobserved E2 stack catalog {stack_names}")
    functions = [row for row in records if row["record_class"] != "STACK_CATALOG"]
    for row in functions:
        _require(
            int(row["stack_vector_width"]) == len(stack_names),
            "function stack-vector width does not match catalog",
        )
        if row["record_class"] == "FUNCTION_INTERRUPT_ROOT":
            _require(
                len(row["interrupt_vector_aliases"]) == 1,
                "interrupt root lacks one observed INTVEC alias backreference",
            )

    return {
        "names": names,
        "records": records,
        "rejected_reason_histogram": dict(sorted(rejected.items())),
        "raw_E2_byte_count": payload.count(0xE2),
    }


def _projection_bytes(payload: bytes, records: list[dict[str, Any]]) -> bytes:
    projected = bytearray(payload)
    for row in reversed(records):
        start = int(row["file_offset_int"])
        end = int(row["end_offset_int"])
        del projected[start:end]
    projected[-3:-1] = projection.ubrof_module_crc(bytes(projected[:-3])).to_bytes(
        2, "big"
    )
    result = bytes(projected)
    projection._validate_crc(result, "grammar projection")  # noqa: SLF001
    return result


def _record_summary(scan: dict[str, Any]) -> dict[str, Any]:
    functions = [
        row for row in scan["records"] if row["record_class"] != "STACK_CATALOG"
    ]
    catalogs = [
        row for row in scan["records"] if row["record_class"] == "STACK_CATALOG"
    ]
    path_kinds = Counter()
    stack_values = Counter()
    direct_tails = Counter()
    for row in functions:
        for path in row["paths"]:
            path_kinds[int(path["path_kind"])] += 1
            for value in path["stack_byte_vector"]:
                stack_values[int(value)] += 1
            if path["path_kind"] == 1:
                direct_tails[int(path["unknown_tail_u8"])] += 1
    return {
        "selected_record_count": len(scan["records"]),
        "function_no_root_category_count": sum(
            row["record_class"] == "FUNCTION_NO_ROOT_CATEGORY" for row in functions
        ),
        "function_interrupt_root_count": sum(
            row["record_class"] == "FUNCTION_INTERRUPT_ROOT" for row in functions
        ),
        "function_other_root_category_count": sum(
            row["record_class"] == "FUNCTION_OTHER_ROOT_CATEGORY" for row in functions
        ),
        "stack_catalog_count": len(catalogs),
        "terminal_path_count": path_kinds[0],
        "direct_callee_path_count": path_kinds[1],
        "stack_byte_value_histogram": {
            str(key): value for key, value in sorted(stack_values.items())
        },
        "direct_call_unknown_tail_histogram": {
            str(key): value for key, value in sorted(direct_tails.items())
        },
        "interrupt_vector_alias_backreference_count": sum(
            len(row["interrupt_vector_aliases"])
            for row in functions
            if row["record_class"] == "FUNCTION_INTERRUPT_ROOT"
        ),
        "raw_E2_byte_count": scan["raw_E2_byte_count"],
        "rejected_incidental_E2_count": scan["raw_E2_byte_count"]
        - len(scan["records"]),
        "rejected_reason_histogram": scan["rejected_reason_histogram"],
    }


def _public_record_rows(scan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in scan["records"]:
        row = {
            key: value
            for key, value in record.items()
            if key not in {"file_offset_int", "end_offset_int", "paths"}
        }
        row["file_offset"] = _hex(int(record["file_offset_int"]))
        if "paths" in record:
            row["path_count"] = len(record["paths"])
            row["terminal_path_count"] = sum(
                path["path_kind"] == 0 for path in record["paths"]
            )
            row["direct_callee_path_count"] = sum(
                path["path_kind"] == 1 for path in record["paths"]
            )
            row["direct_callee_names"] = sorted(
                {
                    str(path["callee_name"])
                    for path in record["paths"]
                    if path["path_kind"] == 1
                }
            )
            row["path_manifest_sha256"] = _sha256(_canonical_bytes(record["paths"]))
        rows.append(row)
    return rows


def _analyze_object(label: str, payload: bytes) -> dict[str, Any]:
    _require(payload[:2] == b"\x01\x0b", f"{label} is not observed UBROF11")
    original_crc = projection._validate_crc(payload, label)  # noqa: SLF001
    scan = scan_observed_e2_records(payload)
    projected = _projection_bytes(payload, scan["records"])
    return {
        "label": label,
        "payload": payload,
        "projection": projected,
        "scan": scan,
        "public": {
            "size_bytes": len(payload),
            "sha256": _sha256(payload),
            "UBROF_version_byte": payload[1],
            "module_crc": original_crc,
            "namespace1_scoped_name_count": len(scan["names"]),
            "record_summary": _record_summary(scan),
            "record_manifest": _public_record_rows(scan),
            "record_manifest_sha256": _sha256(
                _canonical_bytes(_public_record_rows(scan))
            ),
            "projection_size_bytes": len(projected),
            "projection_sha256": _sha256(projected),
            "projection_module_crc": f"{projection._stored_module_crc(projected):04X}",  # noqa: SLF001
            "incidental_E2_bytes_retained_in_projection": projected.count(0xE2),
        },
    }


def _xlib_pair(
    xlib_path: Path, original: bytes, projected: bytes, index: int
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mf1750-e2-grammar-xlib-") as temp:
        original_path = Path(temp) / f"original-{index}.r43"
        projected_path = Path(temp) / f"projection-{index}.r43"
        original_path.write_bytes(original)
        projected_path.write_bytes(projected)
        original_external, original_entries = legacy._default_runner(  # noqa: SLF001
            xlib_path, original_path
        )
        projection_external, projection_entries = legacy._default_runner(  # noqa: SLF001
            xlib_path, projected_path
        )
    _require(
        original_external["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2"
        and original_entries["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
        "original object no longer reproduces the known XLIB E2 boundary",
    )
    _require(
        projection_external["status"] == "PARSED"
        and projection_entries["status"] == "PARSED",
        "grammar projection did not parse in the pinned XLIB",
    )
    return {
        "unmodified_original": {
            "LIST_EXTERNALS_status": original_external["status"],
            "LIST_ENTRIES_status": original_entries["status"],
            "diagnostic": legacy.UNKNOWN_E2,
        },
        "temporary_projection": {
            "LIST_EXTERNALS_status": projection_external["status"],
            "external_count": len(projection_external["symbols"]),
            "external_table_sha256": projection_external["table_sha256"],
            "LIST_ENTRIES_status": projection_entries["status"],
            "entry_count": len(projection_entries["symbols"]),
            "entry_table_sha256": projection_entries["table_sha256"],
        },
    }


def _pin_delivered_source(iar_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, expected in EXPECTED_DELIVERED_SOURCES.items():
        payload = (iar_root / name).read_bytes()
        _require(len(payload) == expected["size_bytes"], f"{name} size mismatch")
        _require(_sha256(payload) == expected["sha256"], f"{name} digest mismatch")
        rows.append({"name": name, **expected})
    return rows


def _delivered_graph_cross_check(
    analyses: dict[str, dict[str, Any]], iar_root: Path
) -> dict[str, Any]:
    graph_report = graph.build_report(iar_root, include_all_edges=True)
    machine_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    machine_unions: dict[str, set[str]] = defaultdict(set)
    for edge in graph_report["graph"]["edges"]:
        object_name = str(edge["object"])
        if object_name not in analyses:
            continue
        callee = str(edge["callee_symbol"])
        machine_unions[object_name].add(callee)
        for caller in edge.get("caller_symbols") or []:
            machine_sets[(object_name, str(caller))].add(callee)

    grammar_sets: dict[tuple[str, str], set[str]] = {}
    grammar_unions: dict[str, set[str]] = defaultdict(set)
    for name, analysis in analyses.items():
        for record in analysis["scan"]["records"]:
            if record["record_class"] == "STACK_CATALOG":
                continue
            callees = {
                str(path["callee_name"])
                for path in record["paths"]
                if path["path_kind"] == 1
            }
            grammar_sets[(name, str(record["caller_name"]))] = callees
            grammar_unions[name].update(callees)

    overlap = sorted(set(grammar_sets) & set(machine_sets))
    mismatches = [
        {
            "object": key[0],
            "caller": key[1],
            "grammar": sorted(grammar_sets[key]),
            "machine": sorted(machine_sets[key]),
        }
        for key in overlap
        if grammar_sets[key] != machine_sets[key]
    ]
    union_mismatches = [
        name
        for name in analyses
        if grammar_unions[name] != machine_unions.get(name, set())
    ]
    _require(len(overlap) == 14, f"expected 14 mapped caller sets, got {len(overlap)}")
    _require(not mismatches, f"E2/machine caller-set mismatches: {mismatches}")
    _require(not union_mismatches, f"E2/machine union mismatches: {union_mismatches}")
    return {
        "mapped_caller_sets_checked": len(overlap),
        "mapped_caller_set_mismatches": 0,
        "object_callee_unions_checked": len(analyses),
        "object_callee_union_mismatches": 0,
        "machine_CALLA_relocation_edges_are_not_E2_path_count": True,
    }


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    return environment


def _git(checkout: Path, arguments: list[str], *, text: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=text,
        env=_git_environment(),
    )
    _require(
        result.returncode == 0,
        f"offline git {' '.join(arguments)} failed in {checkout}: {result.stderr!r}",
    )
    return result.stdout


def _git_show(checkout: Path, commit: str, path: str) -> bytes:
    value = _git(checkout, ["show", f"{commit}:{path}"])
    _require(isinstance(value, bytes), "git show unexpectedly returned text")
    return value


def _git_blob_sha1(checkout: Path, commit: str, path: str) -> str:
    value = _git(checkout, ["rev-parse", f"{commit}:{path}"], text=True)
    _require(isinstance(value, str), "git rev-parse unexpectedly returned bytes")
    digest = value.strip()
    _require(re.fullmatch(r"[0-9a-f]{40}", digest) is not None, "invalid git blob id")
    return digest


def _public_checkout_rows(
    public_checkouts: dict[str, Path],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    analyses: list[dict[str, Any]] = []
    repo_reports: dict[str, Any] = {}
    for slug, expected in PUBLIC_REPOS.items():
        _require(slug in public_checkouts, f"missing offline public checkout: {slug}")
        checkout = public_checkouts[slug].resolve()
        _require((checkout / ".git").exists(), f"not a git checkout: {checkout}")
        head = str(_git(checkout, ["rev-parse", "HEAD"], text=True)).strip()
        _require(head == expected["commit"], f"{slug} commit mismatch: {head}")
        raw_tree = _git(checkout, ["ls-tree", "-r", "-z", "--name-only", head])
        _require(isinstance(raw_tree, bytes), "git tree unexpectedly returned text")
        paths = [item.decode("utf-8") for item in raw_tree.split(b"\0") if item]
        license_paths = [
            path
            for path in paths
            if re.search(r"(?i)(^|/)(license|copying)(\.|$)", path)
        ]
        _require(not license_paths, f"{slug} license-file inventory changed")

        object_rows: list[dict[str, Any]] = []
        for path in paths:
            if not path.casefold().endswith(".r43"):
                continue
            payload = _git_show(checkout, head, path)
            if payload[:2] != b"\x01\x0b":
                continue
            analysis = _analyze_object(f"{slug}:{path}", payload)
            blob_sha1 = _git_blob_sha1(checkout, head, path)
            analysis["repo_slug"] = slug
            analysis["repo_path"] = path
            analysis["git_blob_sha1"] = blob_sha1
            analyses.append(analysis)
            object_rows.append(
                {
                    "path": path,
                    "size_bytes": len(payload),
                    "sha256": _sha256(payload),
                    "git_blob_sha1": blob_sha1,
                    "raw_E2_byte_count": analysis["scan"]["raw_E2_byte_count"],
                    "selected_record_count": len(analysis["scan"]["records"]),
                    "function_record_count": sum(
                        row["record_class"] != "STACK_CATALOG"
                        for row in analysis["scan"]["records"]
                    ),
                }
            )
        object_rows.sort(key=lambda row: str(row["path"]).casefold())
        _require(
            len(object_rows) == expected["expected_UBROF11_objects"],
            f"{slug} UBROF11 object count changed",
        )
        manifest_hash = _sha256(_canonical_bytes(object_rows))
        _require(
            manifest_hash == expected["object_manifest_sha256"],
            f"{slug} public object manifest changed",
        )

        anchor_report = None
        if "anchor" in expected:
            anchor = expected["anchor"]
            anchor_payload = _git_show(checkout, head, anchor["path"])
            anchor_blob = _git_blob_sha1(checkout, head, anchor["path"])
            _require(
                len(anchor_payload) == anchor["size_bytes"],
                f"{slug} anchor size mismatch",
            )
            _require(
                _sha256(anchor_payload) == anchor["sha256"],
                f"{slug} anchor digest mismatch",
            )
            _require(
                anchor_blob == anchor["git_blob_sha1"], f"{slug} anchor blob changed"
            )
            anchor_report = dict(anchor)
            if anchor["path"].endswith("Project_08.map"):
                _require(
                    b"Embedded Workbench 7.4" in anchor_payload
                    and b"Copyright (C) 1987-2016 IAR Systems AB." in anchor_payload,
                    "public IAR 7.4 map anchors changed",
                )
                anchor_report["observed_tool_lineage"] = "IAR Embedded Workbench 7.4"
            if anchor["path"] == "lab5/main.c":
                _require(
                    b"DelayTenths(600);" in anchor_payload
                    and b"led_tra();" in anchor_payload,
                    "public source call anchors changed",
                )
                anchor_report["observed_source_calls"] = ["DelayTenths", "led_tra"]

        repo_reports[slug] = {
            "url": expected["url"],
            "commit": head,
            "source_classification": (
                "PUBLIC_THIRD_PARTY_GITHUB_COMMIT_METADATA_ONLY_INSPECTION"
            ),
            "license_file_found_at_pinned_commit": False,
            "license_inferred": False,
            "object_count": len(object_rows),
            "object_manifest_sha256": manifest_hash,
            "objects": object_rows,
            "anchor": anchor_report,
        }
    return analyses, repo_reports


def _aggregate_summaries(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    stack_values = Counter()
    root_categories = Counter()
    for analysis in analyses:
        summary = _record_summary(analysis["scan"])
        for key in (
            "selected_record_count",
            "function_no_root_category_count",
            "function_interrupt_root_count",
            "function_other_root_category_count",
            "stack_catalog_count",
            "terminal_path_count",
            "direct_callee_path_count",
            "interrupt_vector_alias_backreference_count",
            "raw_E2_byte_count",
            "rejected_incidental_E2_count",
        ):
            totals[key] += int(summary[key])
        for key, value in summary["stack_byte_value_histogram"].items():
            stack_values[int(key)] += int(value)
        for record in analysis["scan"]["records"]:
            if record["record_class"] == "STACK_CATALOG":
                continue
            roots = tuple(record["root_categories"])
            root_categories[roots] += 1
    result = dict(totals)
    result["object_count"] = len(analyses)
    result["stack_byte_value_histogram"] = {
        str(key): value for key, value in sorted(stack_values.items())
    }
    result["root_category_histogram"] = {
        "<none>" if not key else ",".join(key): value
        for key, value in sorted(root_categories.items())
    }
    return result


def _public_source_cross_check(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    target = next(
        row
        for row in analyses
        if row.get("repo_slug") == "kevinbird61/2015-MSP430-IAR"
        and row.get("repo_path") == "lab5/Debug/Obj/main.r43"
    )
    functions = {
        str(row["caller_name"]): row
        for row in target["scan"]["records"]
        if row["record_class"] != "STACK_CATALOG"
    }
    _require(
        set(functions) == {"main", "led_tra"}, "public source function set changed"
    )
    main_callees = {
        str(path["callee_name"])
        for path in functions["main"]["paths"]
        if path["path_kind"] == 1
    }
    _require(
        main_callees == {"DelayTenths", "led_tra"},
        "public source/E2 direct-callee set changed",
    )
    _require(
        len(functions["led_tra"]["paths"]) == 1
        and functions["led_tra"]["paths"][0]["path_kind"] == 0,
        "public leaf-function E2 path changed",
    )
    return {
        "source_path": "lab5/main.c",
        "source_sha256": PUBLIC_REPOS["kevinbird61/2015-MSP430-IAR"]["anchor"][
            "sha256"
        ],
        "source_declared_call_set": ["DelayTenths", "led_tra"],
        "E2_main_direct_callee_set": sorted(main_callees),
        "sets_match": True,
        "E2_led_tra_terminal_path_only": True,
    }


def build_report(
    xlib_path: Path,
    public_checkouts: dict[str, Path],
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build the deterministic full-corpus, metadata-only grammar audit."""

    xlib_identity = legacy._pin_xlib(xlib_path)  # noqa: SLF001
    source_manifest = _pin_delivered_source(iar_root)
    object_dir = iar_root / graph.OBJECT_DIR_REL
    delivered: dict[str, dict[str, Any]] = {}
    delivered_internal: dict[str, dict[str, Any]] = {}
    all_analyses: list[dict[str, Any]] = []

    for index, (name, expected) in enumerate(projection.EXPECTED_OBJECTS.items()):
        payload = (object_dir / name).read_bytes()
        _require(len(payload) == expected["size_bytes"], f"{name} size mismatch")
        _require(_sha256(payload) == expected["sha256"], f"{name} digest mismatch")
        analysis = _analyze_object(name, payload)
        discovered_spans = [
            (int(row["file_offset_int"]), int(row["end_offset_int"]))
            for row in analysis["scan"]["records"]
        ]
        allowed_spans = [
            (offset, offset + length) for offset, length, _ in expected["spans"]
        ]
        _require(
            discovered_spans == allowed_spans,
            f"{name} grammar discovery disagrees with prior exact offsets",
        )
        _require(
            analysis["public"]["projection_sha256"] == expected["projection_sha256"],
            f"{name} grammar projection identity changed",
        )
        xlib = _xlib_pair(xlib_path, payload, analysis["projection"], index)
        public_row = dict(analysis["public"])
        public_row["prior_exact_offset_allowlist_agrees"] = True
        public_row["official_XLIB_differential"] = xlib
        delivered[name] = public_row
        delivered_internal[name] = analysis
        all_analyses.append(analysis)

    delivered_graph = _delivered_graph_cross_check(delivered_internal, iar_root)
    public_analyses, public_repos = _public_checkout_rows(public_checkouts)
    for offset, analysis in enumerate(public_analyses, start=len(all_analyses)):
        analysis["xlib"] = _xlib_pair(
            xlib_path, analysis["payload"], analysis["projection"], offset
        )
        all_analyses.append(analysis)

    public_manifest_rows = [
        {
            "repo": str(row["repo_slug"]),
            "path": str(row["repo_path"]),
            "size_bytes": len(row["payload"]),
            "sha256": _sha256(row["payload"]),
            "git_blob_sha1": str(row["git_blob_sha1"]),
            "record_manifest_sha256": row["public"]["record_manifest_sha256"],
        }
        for row in sorted(
            public_analyses,
            key=lambda value: (
                str(value["repo_slug"]).casefold(),
                str(value["repo_path"]).casefold(),
            ),
        )
    ]
    public_manifest_hash = _sha256(_canonical_bytes(public_manifest_rows))
    _require(
        public_manifest_hash == EXPECTED_PUBLIC_CORPUS_MANIFEST_SHA256,
        "public corpus manifest changed",
    )

    public_objects = [
        {
            "repo": row["repo_slug"],
            "path": row["repo_path"],
            "git_blob_sha1": row["git_blob_sha1"],
            **row["public"],
            "official_XLIB_differential": row["xlib"],
        }
        for row in sorted(
            public_analyses,
            key=lambda value: (
                str(value["repo_slug"]).casefold(),
                str(value["repo_path"]).casefold(),
            ),
        )
    ]
    delivered_totals = _aggregate_summaries(list(delivered_internal.values()))
    public_totals = _aggregate_summaries(public_analyses)
    overall_totals = _aggregate_summaries(all_analyses)

    _require(
        delivered_totals["object_count"] == 3
        and delivered_totals["function_no_root_category_count"] == 22
        and delivered_totals["function_interrupt_root_count"] == 0
        and delivered_totals["stack_catalog_count"] == 3
        and delivered_totals["selected_record_count"] == 25,
        "delivered grammar totals changed",
    )
    _require(
        public_totals["object_count"] == 29
        and public_totals["function_no_root_category_count"] == 76
        and public_totals["function_interrupt_root_count"] == 9
        and public_totals["stack_catalog_count"] == 29
        and public_totals["selected_record_count"] == 114,
        "public grammar totals changed",
    )
    _require(
        overall_totals["object_count"] == 32
        and overall_totals["selected_record_count"] == 139
        and overall_totals["terminal_path_count"] == 56
        and overall_totals["direct_callee_path_count"] == 126
        and overall_totals["raw_E2_byte_count"] == 227
        and overall_totals["rejected_incidental_E2_count"] == 88,
        "overall grammar totals changed",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "pure_software": True,
            "delivered_objects": 3,
            "public_third_party_objects": 29,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refresh_requested": False,
            "authorization_token_or_claim_used": False,
            "network_accessed_by_this_tool": False,
            "public_inputs_read_from_local_identity_pinned_git_checkouts": True,
            "git_lazy_fetch_disabled": True,
            "original_objects_modified": False,
            "temporary_projection_bytes_written_for_XLIB_only": True,
            "persistent_projection_written": False,
            "raw_object_bytes_emitted": False,
            "raw_waveform_or_LUT_bytes_emitted": False,
            "raw_disassembly_emitted": False,
        },
        "official_public_evidence": {
            "XLINK_release_notes": {
                "url": OFFICIAL_XLINK_NOTES_URL,
                "supported_claims": [
                    "XLINK stack-usage analysis starts at 6.2.0.62",
                    "EW25659: XLIB can report Unknown tag: E2 on UBROF stack-usage information; fixed in 6.3.4.78",
                    "EW25431: UBROF11.0.1 interrupt stack-usage input had a separate corrupt-input fix in 6.3.1.71",
                    "multi-stack support was introduced in 6.3.0.70 and was then limited to AVR",
                ],
                "byte_level_E2_grammar_published_there": False,
            },
            "MSP430_XLINK_manual_update": {
                "url": OFFICIAL_MSP430_XMAN_URL,
                "supported_claim": "the official UBROF history lists stack usage analysis as a UBROF11 addition",
                "byte_level_E2_grammar_published_there": False,
            },
            "IAR_2005_record_type_note": {
                "url": OFFICIAL_2005_RECORD_NOTE_URL,
                "predates_UBROF11": True,
                "byte_level_E2_grammar_published_there": False,
            },
        },
        "official_XLIB_6_1_3_56": xlib_identity,
        "delivered_source_manifest": source_manifest,
        "observed_dialect_grammar": {
            "status": "INFERRED_EXACT_CORPUS_DIALECT_NOT_OFFICIAL_GENERAL_GRAMMAR",
            "framing": "E2 + payload_length_u8 + payload",
            "function_context": "49 immediately before E2; C7 immediately after payload",
            "function_payload": {
                "root_category_count_u8": True,
                "root_categories": "counted length_u8 ASCII strings",
                "caller_namespace1_index_candidate_u32be": True,
                "stack_vector_width_u8": True,
                "path_count_u8": True,
                "path_kind_0": "terminal/no-callee + stack-byte vector",
                "path_kind_1": "direct-callee + stack-byte vector + namespace1-index candidate u32be + unknown tail u8",
                "all_observed_direct_call_tails": 0,
            },
            "stack_catalog_payload": "subtype 2 + stack_count_u8 + counted length_u8 ASCII names",
            "stack_catalog_successor": "3F",
            "all_observed_catalogs": ["CSTACK"],
            "field_names_and_roles_are_inferred": True,
            "upper_nonzero_bytes_for_u32_name_references_observed": False,
            "multi_stack_vector_observed": False,
            "other_path_kind_observed": False,
        },
        "coverage": {
            "delivered": delivered_totals,
            "public": public_totals,
            "overall": overall_totals,
            "all_caller_name_references_resolved": True,
            "caller_name_references_checked": 107,
            "all_direct_callee_name_references_resolved": True,
            "direct_callee_name_references_checked": 126,
            "all_32_originals_reproduce_known_XLIB_E2_boundary": True,
            "all_32_temporary_projections_parse_in_pinned_XLIB": True,
            "projection_parse_is_not_native_original_parse": True,
        },
        "delivered_objects": delivered,
        "delivered_machine_graph_cross_check": delivered_graph,
        "public_corpus": {
            "classification": "PINNED_PUBLIC_THIRD_PARTY_NEGATIVE_AND_DIALECT_CONTROLS",
            "license_boundary": (
                "no LICENSE/COPYING file was found at the three pinned commits; no license is inferred; only object metadata is reported and no public object bytes are redistributed"
            ),
            "repos": public_repos,
            "corpus_manifest_sha256": public_manifest_hash,
            "corpus_manifest": public_manifest_rows,
            "source_cross_check": _public_source_cross_check(public_analyses),
            "objects": public_objects,
        },
        "adjudication": {
            "verdict": (
                "OBSERVED_MSP430_E2_DIALECT_RECOVERED_WITH_32_OF_32_"
                "PROJECTION_DIFFERENTIALS_BUT_OFFICIAL_GENERAL_GRAMMAR_AND_"
                "NATIVE_ORIGINAL_PARSE_REMAIN_UNPROVEN"
            ),
            "observed_exact_corpus_dialect_recovered": True,
            "official_general_UBROF11_E2_grammar_recovered": False,
            "fixed_or_newer_XLIB_native_original_parse_obtained": False,
            "unmodified_objects_natively_parsed_by_pinned_old_XLIB": False,
            "temporary_projection_differential_complete": True,
            "projection_may_be_described_as_original_object_parse": False,
            "safe_link_flash_or_object_replacement_use": False,
            "meaning": (
                "A no-offset scanner explains 139 records across 32 exact MSP430 UBROF11 objects, including 9 interrupt-root records that the prior exact-offset corpus did not contain. All namespace references resolve, all interrupt roots have an INTVEC alias, delivered call sets agree with the independent machine-relocation graph, and every E2-elided temporary projection parses in the pinned old XLIB. The cited official material does not publish the bytes, so this remains an inferred observed dialect and none of those differentials is a native parse of an original."
            ),
        },
        "remaining_boundary": {
            "native_original_external_and_entry_tables": (
                "still require direct testing with a legally obtained identity-pinned official XLIB 6.3.4.78 or newer"
            ),
            "official_general_E2_grammar": "not recovered",
            "cross_architecture_validation": "not performed; all exact objects are MSP430",
            "multiple_stack_catalogs_or_vectors": "not observed; all 32 objects declare only CSTACK",
            "nonzero_upper_name_reference_bytes": "not observed",
            "root_categories_other_than_interrupt": "not observed",
            "path_kinds_other_than_0_and_1": "not observed",
            "direct_call_tail_semantics": "unknown; all 126 observed values are zero",
            "stack_byte_vector_semantics": (
                "consistent with per-path stack contribution, but exact official field semantics are not published in cited sources"
            ),
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


def discover_public_checkouts() -> dict[str, Path] | None:
    configured = os.environ.get("MF1750_E2_PUBLIC_REPO_ROOT")
    base = (
        Path(configured)
        if configured
        else Path(os.environ.get("TEMP", tempfile.gettempdir()))
        / "mf1750_ubrof_public_repos"
    )
    result = {
        slug: (base / expected["checkout_name"]).resolve()
        for slug, expected in PUBLIC_REPOS.items()
    }
    return result if all((path / ".git").exists() for path in result.values()) else None


def _parse_checkout(values: list[str]) -> dict[str, Path]:
    if not values:
        discovered = discover_public_checkouts()
        _require(discovered is not None, "three pinned public checkouts are required")
        return discovered
    result: dict[str, Path] = {}
    for value in values:
        slug, separator, raw_path = value.partition("=")
        _require(bool(separator), "--public-checkout must be SLUG=PATH")
        _require(slug in PUBLIC_REPOS, f"unexpected public repository slug: {slug}")
        _require(slug not in result, f"duplicate public checkout: {slug}")
        result[slug] = Path(raw_path).resolve()
    _require(
        set(result) == set(PUBLIC_REPOS), "all three public checkouts are required"
    )
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", type=Path, default=_discover_xlib())
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument(
        "--public-checkout",
        action="append",
        default=[],
        metavar="SLUG=PATH",
        help="repeat for all three identity-pinned public repositories",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require(args.xlib is not None, "identity-pinned XLIB path is required")
        public_checkouts = _parse_checkout(args.public_checkout)
        report = build_report(
            args.xlib.resolve(), public_checkouts, args.iar_root.resolve()
        )
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
        E2GrammarAuditError,
        projection.E2ProjectionAuditError,
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
