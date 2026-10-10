#!/usr/bin/env python3
"""Cross-check pinned IAR r43 external indices with the official XLIB tool.

The delivered objects contain paired CALLA/debug-source records.  Those
records expose an external-table index and a human-readable callee name, but
the name alone is not an independently decoded EXTERNAL table.  This tool
runs an identity-pinned official IAR XLIB executable, parses only its symbol
list output, and checks every parseable external-index call against the
ordered XLIB EXTERNAL table.

The pinned XLIB 6.1.3.56 predates stack-usage support.  It parses the 26
UBROF10 objects and reports ``Error [14]: Unknown tag: E2`` for the three
newer, stack-usage-bearing UBROF11 objects.  That failure is an explicit tool
version boundary, never an empty-symbol result.  IAR's later XLINK release
notes identify the same E2/stack-usage failure and record its correction in
6.3.4.78 (issue EW25659).

Only names, counts, identities, and hashes are emitted.  Object code,
waveform bytes, keys, and payload bytes are never copied into the report.
No hardware, serial, device-network, flashing, or refresh interface exists.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph


KIND = "mf1750-iar-xlib-external-index-audit"
SCHEMA_VERSION = 1
XLIB_VERSION = "6.1.3.56"
EXPECTED_XLIB = {
    "size_bytes": 550_912,
    "sha256": "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
}
EXPECTED_UNSUPPORTED_OBJECTS = {"DELAY.r43", "E6_73.r43", "main.r43"}
EXPECTED_EXTERNAL_INDEX_CALLS = 401
EXPECTED_XLIB_VERIFIED_CALLS = 349
EXPECTED_VERSION_BOUNDARY_CALLS = 52
OFFICIAL_XLINK_RELEASE_NOTES = (
    "https://netstorage.iar.com/FileStore/STANDARD/001/000/603/ew/doc/"
    "infocenter/xlink.ENU.html"
)

MODULE_RE = re.compile(r"^\s*\d+\.\s+Pgm\s+(?P<name>\S+)\s*$")
SYMBOL_RE = re.compile(r"^\s+(?P<kind>Ext|Ent)\s+(?P<name>\S.*?)\s*$")
VERSION_BANNER = f"IAR Universal Librarian V{XLIB_VERSION}"
UNKNOWN_E2 = "Error [14]: Unknown tag: E2"


class XlibAuditError(RuntimeError):
    """An identity, XLIB output, or cross-check invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise XlibAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _table_sha256(names: list[str]) -> str:
    encoded = "".join(f"{index}\0{name}\n" for index, name in enumerate(names)).encode()
    return _sha256(encoded)


def _pin_xlib(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"XLIB executable is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == EXPECTED_XLIB["size_bytes"],
        "XLIB size mismatch: expected "
        f"{EXPECTED_XLIB['size_bytes']}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == EXPECTED_XLIB["sha256"],
        f"XLIB SHA-256 mismatch: expected {EXPECTED_XLIB['sha256']}, got {digest}",
    )
    return {
        "filename": path.name,
        "version": XLIB_VERSION,
        "size_bytes": len(payload),
        "sha256": digest,
    }


def parse_xlib_symbol_list(payload: bytes, *, expected_kind: str) -> dict[str, Any]:
    """Parse one deterministic LIST-EXTERNALS or LIST-ENTRIES output."""

    _require(expected_kind in {"Ext", "Ent"}, "unsupported XLIB symbol-list kind")
    text = payload.decode("cp1252")
    _require(VERSION_BANNER in text, "XLIB list version banner changed")
    modules = [
        match.group("name")
        for line in text.splitlines()
        if (match := MODULE_RE.match(line)) is not None
    ]
    _require(len(modules) == 1, f"expected one XLIB module, found {len(modules)}")
    symbols: list[str] = []
    unexpected_kinds: list[str] = []
    for line in text.splitlines():
        match = SYMBOL_RE.match(line)
        if match is None:
            continue
        kind = match.group("kind")
        if kind != expected_kind:
            unexpected_kinds.append(kind)
        symbols.append(match.group("name"))
    _require(not unexpected_kinds, "XLIB list mixed external and entry rows")
    _require(len(symbols) == len(set(symbols)), "XLIB symbol table contains duplicates")
    return {
        "module": modules[0],
        "symbols": symbols,
        "table_sha256": _table_sha256(symbols),
    }


def _run_xlib_list(
    xlib_path: Path,
    object_path: Path,
    *,
    command: str,
    expected_kind: str,
) -> dict[str, Any]:
    _require(command in {"LIST-EXTERNALS", "LIST-ENTRIES"}, "unsafe XLIB command")
    with tempfile.TemporaryDirectory(prefix="mf1750-xlib-list-") as temp_dir:
        # XLIB 6.1.3 reads a byte-oriented command stream and is not reliable
        # with the Chinese component in the vendor-tree path.  The source
        # object has already been fully identity-pinned by ``graph``; copying
        # it to this fresh ASCII-only directory changes neither the bytes nor
        # the evidence scope.
        object_copy = Path(temp_dir) / object_path.name
        shutil.copyfile(object_path, object_copy)
        output_path = Path(temp_dir) / "symbols.txt"
        commands = (
            f'ON-ERROR-EXIT\r\n{command} "{object_copy}" "{output_path}"\r\nEXIT\r\n'
        )
        completed = subprocess.run(
            [str(xlib_path)],
            input=commands.encode("ascii"),
            check=False,
            capture_output=True,
            timeout=30,
        )
        stdout = completed.stdout.decode("cp1252")
        stderr = completed.stderr.decode("cp1252")
        combined = stdout + stderr
        _require(VERSION_BANNER in combined, "XLIB process version banner changed")
        if completed.returncode == 0:
            _require(output_path.is_file(), f"{command} did not create its list file")
            payload = output_path.read_bytes()
            _require(payload, f"{command} created an empty list file")
            parsed = parse_xlib_symbol_list(payload, expected_kind=expected_kind)
            return {
                "status": "PARSED",
                "returncode": 0,
                **parsed,
            }
        if completed.returncode == 2 and UNKNOWN_E2 in combined:
            _require(
                not output_path.exists() or output_path.stat().st_size == 0,
                f"{command} E2 failure unexpectedly emitted a nonempty list",
            )
            return {
                "status": "UNSUPPORTED_STACK_USAGE_TAG_E2",
                "returncode": 2,
                "diagnostic": UNKNOWN_E2,
            }
        raise XlibAuditError(
            f"{command} failed unexpectedly with return code {completed.returncode}: "
            f"{combined.strip()!r}"
        )


XlibListRunner = Callable[[Path, Path], tuple[dict[str, Any], dict[str, Any]]]


def _default_runner(
    xlib_path: Path, object_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    externals = _run_xlib_list(
        xlib_path,
        object_path,
        command="LIST-EXTERNALS",
        expected_kind="Ext",
    )
    entries = _run_xlib_list(
        xlib_path,
        object_path,
        command="LIST-ENTRIES",
        expected_kind="Ent",
    )
    return externals, entries


def _group_external_calls(
    edges: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["relocation_classification"] == "external-index":
            grouped[str(edge["object"])].append(edge)
    return grouped


def _observed_index_rows(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for edge in edges:
        index = int(str(edge["target_id"]), 16)
        symbol = str(edge["callee_symbol"])
        row = grouped.setdefault(index, {"symbols": set(), "call_count": 0})
        row["symbols"].add(symbol)
        row["call_count"] += 1
    return [
        {
            "external_index": index,
            "observed_debug_symbols": sorted(row["symbols"]),
            "call_count": row["call_count"],
        }
        for index, row in sorted(grouped.items())
    ]


def build_report(
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
    *,
    runner: XlibListRunner = _default_runner,
) -> dict[str, Any]:
    """Build a deterministic metadata-only XLIB/external-index audit."""

    xlib_identity = _pin_xlib(xlib_path)
    graph_report = graph.build_report(iar_root, include_all_edges=True)
    edges = graph_report["graph"]["edges"]
    external_calls = _group_external_calls(edges)
    total_calls = sum(len(rows) for rows in external_calls.values())
    _require(
        total_calls == EXPECTED_EXTERNAL_INDEX_CALLS,
        f"external-index call count changed: expected 401, got {total_calls}",
    )

    object_dir = iar_root / graph.OBJECT_DIR_REL
    objects: dict[str, dict[str, Any]] = {}
    verified_calls = 0
    boundary_calls = 0
    mismatch_rows: list[dict[str, Any]] = []
    table_manifest_rows: list[dict[str, Any]] = []
    parsed_entry_names: dict[str, list[str]] = {}

    for identity in graph_report["identity"]["objects"]:
        name = str(identity["name"])
        object_path = object_dir / name
        externals, entries = runner(xlib_path, object_path)
        _require(
            externals["status"] == entries["status"],
            f"{name} LIST-EXTERNALS/LIST-ENTRIES status mismatch",
        )
        calls = external_calls.get(name, [])
        observed_rows = _observed_index_rows(calls)
        expected_unsupported = name in EXPECTED_UNSUPPORTED_OBJECTS

        if externals["status"] == "PARSED":
            _require(
                not expected_unsupported, f"{name} unexpectedly became XLIB-parseable"
            )
            _require(
                externals["module"] == object_path.stem,
                f"{name} external-list module changed",
            )
            _require(
                entries["module"] == object_path.stem,
                f"{name} entry-list module changed",
            )
            external_names = list(externals["symbols"])
            entry_names = list(entries["symbols"])
            parsed_entry_names[name] = entry_names
            for edge in calls:
                index = int(str(edge["target_id"]), 16)
                observed = str(edge["callee_symbol"])
                actual = external_names[index] if index < len(external_names) else None
                if actual != observed:
                    mismatch_rows.append(
                        {
                            "object": name,
                            "external_index": index,
                            "xlib_symbol": actual,
                            "observed_debug_symbol": observed,
                        }
                    )
            verified_calls += len(calls)
            table_manifest_rows.append(
                {
                    "object": name,
                    "external_table_sha256": externals["table_sha256"],
                    "entry_table_sha256": entries["table_sha256"],
                }
            )
            objects[name] = {
                "ubrof_version_byte": identity["ubrof_version_byte"],
                "xlib_status": "PARSED",
                "external_count": len(external_names),
                "entry_count": len(entry_names),
                "external_table_sha256": externals["table_sha256"],
                "entry_table_sha256": entries["table_sha256"],
                "external_index_calls": len(calls),
                "verified_call_count": len(calls),
                "observed_external_indices": observed_rows,
                "external_index_table": [
                    {"external_index": index, "symbol": symbol}
                    for index, symbol in enumerate(external_names)
                ],
            }
        else:
            _require(
                expected_unsupported,
                f"{name} unexpectedly hit the stack-usage E2 boundary",
            )
            _require(
                externals["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
                f"{name} has unknown XLIB status",
            )
            boundary_calls += len(calls)
            objects[name] = {
                "ubrof_version_byte": identity["ubrof_version_byte"],
                "xlib_status": "UNSUPPORTED_STACK_USAGE_TAG_E2",
                "diagnostic": UNKNOWN_E2,
                "external_count": None,
                "entry_count": None,
                "external_index_calls": len(calls),
                "verified_call_count": 0,
                "observed_external_indices": observed_rows,
                "empty_symbol_table_inferred": False,
            }

    parsed_names = [
        name for name, row in objects.items() if row["xlib_status"] == "PARSED"
    ]
    unsupported_names = [
        name
        for name, row in objects.items()
        if row["xlib_status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2"
    ]
    _require(
        len(parsed_names) == 26, f"expected 26 parsed objects, got {len(parsed_names)}"
    )
    _require(
        set(unsupported_names) == EXPECTED_UNSUPPORTED_OBJECTS,
        "the exact three-object XLIB version boundary changed",
    )
    _require(
        verified_calls == EXPECTED_XLIB_VERIFIED_CALLS,
        f"expected 349 XLIB-verified calls, got {verified_calls}",
    )
    _require(
        boundary_calls == EXPECTED_VERSION_BOUNDARY_CALLS,
        f"expected 52 version-boundary calls, got {boundary_calls}",
    )
    _require(
        not mismatch_rows, f"XLIB/debug external-index mismatches: {mismatch_rows}"
    )

    e2801 = objects["E2801.r43"]
    e2802 = objects["E2802.r43"]
    e2801_table = {
        row["external_index"]: row["symbol"] for row in e2801["external_index_table"]
    }
    e2802_table = {
        row["external_index"]: row["symbol"] for row in e2802["external_index_table"]
    }
    _require(e2801["entry_count"] == 50, "E2801 entry count changed")
    _require(e2802["entry_count"] == 49, "E2802 entry count changed")
    _require(e2801["external_count"] == 11, "E2801 external count changed")
    _require(e2802["external_count"] == 11, "E2802 external count changed")
    _require(e2801_table.get(3) == "ReadData", "E2801 external index 3 changed")
    _require(e2802_table.get(3) == "ReadData", "E2802 external index 3 changed")
    for name in ("E2801.r43", "E2802.r43"):
        _require(
            "Upload_Temperature_LUT" in parsed_entry_names[name],
            f"{name} Upload_Temperature_LUT entry disappeared",
        )
        _require(
            "EPD_Init" in parsed_entry_names[name],
            f"{name} EPD_Init entry disappeared",
        )
    _require(
        set(parsed_entry_names["E2801.r43"]) - set(parsed_entry_names["E2802.r43"])
        == {"for_AX"},
        "E2801/E2802 entry-table difference changed",
    )
    _require(
        not set(parsed_entry_names["E2802.r43"]) - set(parsed_entry_names["E2801.r43"]),
        "E2802 gained an entry absent from E2801",
    )
    main_index_2 = next(
        row
        for row in objects["main.r43"]["observed_external_indices"]
        if row["external_index"] == 2
    )
    _require(
        main_index_2["observed_debug_symbols"] == ["EPD_Init"]
        and main_index_2["call_count"] == 1,
        "main external index 2 debug-source mapping changed",
    )
    _require(
        graph_report["current_delivered_direct_xlink_inputs"][
            "Upload_Temperature_LUT_marker_in_final_d43"
        ]
        is False,
        "final d43 unexpectedly gained the legacy upload marker",
    )

    table_manifest = sorted(
        table_manifest_rows, key=lambda row: row["object"].casefold()
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": {
            "r43_objects": 29,
            "xlib_parsed_objects": 26,
            "xlib_version_boundary_objects": 3,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "flashed": False,
            "visible_refreshes": 0,
            "raw_object_code_emitted": False,
            "raw_waveform_or_payload_emitted": False,
        },
        "identity": {
            "xlib": xlib_identity,
            "r43_object_manifest_sha256": graph_report["identity"][
                "object_manifest_sha256"
            ],
            "parsed_external_and_entry_table_manifest_sha256": _sha256(
                _canonical_bytes(table_manifest)
            ),
        },
        "official_tool_version_boundary": {
            "pinned_xlib_version": XLIB_VERSION,
            "pinned_xlib_predates_stack_usage_support_added_in": "6.2.0.62",
            "observed_diagnostic": UNKNOWN_E2,
            "official_issue": "EW25659",
            "official_issue_wording_class": (
                "XLIB unknown-tag-E2 failure on files containing stack-usage information"
            ),
            "official_fix_version": "6.3.4.78",
            "official_release_notes": OFFICIAL_XLINK_RELEASE_NOTES,
            "failure_means_empty_external_or_entry_table": False,
            "matching_6.3.4_or_newer_xlib_still_required_for_direct_tables": True,
        },
        "objects": objects,
        "external_index_cross_check": {
            "total_paired_external_index_calls": total_calls,
            "official_xlib_verified_calls": verified_calls,
            "version_boundary_calls": boundary_calls,
            "verified_mismatches": mismatch_rows,
            "parseable_objects_zero_mismatch": True,
        },
        "targeted_adjudication": {
            "E2801": {
                "entry_count": e2801["entry_count"],
                "external_count": e2801["external_count"],
                "external_index_3": e2801_table[3],
                "ReadData_call_count": next(
                    row["call_count"]
                    for row in e2801["observed_external_indices"]
                    if row["external_index"] == 3
                ),
            },
            "E2802": {
                "entry_count": e2802["entry_count"],
                "external_count": e2802["external_count"],
                "external_index_3": e2802_table[3],
                "ReadData_call_count": next(
                    row["call_count"]
                    for row in e2802["observed_external_indices"]
                    if row["external_index"] == 3
                ),
            },
            "external_index_3_is_ReadData_independently_confirmed": True,
            "ReadData_provider_or_implementation_location_proven": False,
            "main_external_index_2_debug_symbol": "EPD_Init",
            "main_index_2_independently_parsed_by_this_xlib": False,
            "E6_73_is_provider_proven_by_this_xlib": False,
            "Upload_Temperature_LUT_entry_in_E2801_and_E2802": True,
            "legacy_upload_is_in_current_final_link_unit": False,
        },
        "adjudication": {
            "verdict": (
                "OFFICIAL_XLIB_CONFIRMS_349_OF_401_EXTERNAL_INDEX_CALLS_"
                "WITH_ZERO_MISMATCH_52_REMAIN_VERSION_BOUNDED"
            ),
            "why": (
                "The exact official XLIB independently confirms every external-index "
                "call in the 26 parseable UBROF10 objects. The three UBROF11 objects "
                "are explicit E2 failures, not empty tables. The audit does not resolve "
                "provider implementation, final-link reachability, SPD1657 ABI, or "
                "physical transport safety."
            ),
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.xlib, args.iar_root)
        indent = None if args.compact else 2
        payload = (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=indent) + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (OSError, subprocess.SubprocessError, XlibAuditError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
