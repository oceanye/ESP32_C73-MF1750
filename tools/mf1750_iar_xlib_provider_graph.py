#!/usr/bin/env python3
"""Build a bounded provider-candidate graph from official XLIB symbol tables.

The companion r43 graph recovers identity-pinned CALLA relocation sites, but
its 0x5D targets are external-table indices rather than local section IDs.
This tool joins those sites to ordered EXTERNAL and ENTRY lists emitted by the
identity-pinned official IAR XLIB 6.1.3.56 executable.

That join deliberately produces *provider candidates*, not linked providers.
The 29 delivered objects are an inventory, not one link unit, and no link
manifest is delivered for the orphan E2801/E2802 objects. Moreover, XLIB
6.1.3.56 stops at stack-usage tag E2 in DELAY/E6_73/main. Their paired debug
names remain version-bounded and are never promoted to official table rows.

The report is metadata-only: it contains symbol names, section IDs, call-site
offsets, counts, identities, and hashes, but no object code, disassembly, LUT,
waveform, key, or plaintext bytes. It has no hardware, serial, network,
flashing, token, claim, or refresh interface.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_xlib_external_index_audit as xlib_audit


KIND = "mf1750-iar-xlib-provider-candidate-graph"
SCHEMA_VERSION = 1

EXPECTED_EXTERNAL_CALLS = 401
EXPECTED_EXTERNAL_GROUPS = 68
EXPECTED_XLIB_VERIFIED_CALLS = 349
EXPECTED_XLIB_VERIFIED_GROUPS = 58
EXPECTED_VERSION_BOUNDARY_CALLS = 52
EXPECTED_VERSION_BOUNDARY_GROUPS = 10
EXPECTED_PARSEABLE_TABLE_MANIFEST_SHA256 = (
    "40973a7a6b63f11b1b2cbc94e935021da2eb55a427bb1f7e9fc43627d4091413"
)

LEGACY_OBJECTS = ("E2801.r43", "E2802.r43")
TARGETS = ("EPD_Init", "Upload_Temperature_LUT")
MAIN_DISPLAY_SYMBOLS = (
    "EPD_Display_White",
    "EPD_Display_Black",
    "EPD_Display_Red",
    "EPD_Display_Yellow",
    "EPD_Display_Blue",
    "EPD_Display_Green",
)


class ProviderGraphError(RuntimeError):
    """An identity, official-tool, or graph invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProviderGraphError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hex_to_int(value: str) -> int:
    _require(value.startswith("0x"), f"expected hexadecimal value, got {value!r}")
    return int(value, 16)


def _candidate_classification(provider_count: int) -> str:
    _require(provider_count >= 0, "provider count cannot be negative")
    if provider_count == 0:
        return "NONE_IN_26_XLIB_PARSEABLE_OBJECTS"
    if provider_count == 1:
        return "UNIQUE_WITHIN_26_XLIB_PARSEABLE_OBJECTS"
    return "AMBIGUOUS_WITHIN_26_XLIB_PARSEABLE_OBJECTS"


def _entry_table_index(
    parsed_entries: dict[str, list[str]],
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for object_name, symbols in parsed_entries.items():
        for symbol in symbols:
            index[symbol].append(object_name)
    return {
        symbol: sorted(names, key=str.casefold)
        for symbol, names in sorted(index.items())
    }


def _observed_local_definition_index(
    graph_report: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for object_name, object_row in graph_report["objects"].items():
        for section in object_row["code_sections"]:
            for symbol in section["symbols"]:
                index[str(symbol)].append(
                    {
                        "object": str(object_name),
                        "section_id": str(section["section_id"]),
                    }
                )
    return {
        symbol: sorted(
            rows,
            key=lambda row: (row["object"].casefold(), _hex_to_int(row["section_id"])),
        )
        for symbol, rows in sorted(index.items())
    }


def _group_external_calls(
    edges: list[dict[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["relocation_classification"] != "external-index":
            continue
        grouped[(str(edge["object"]), _hex_to_int(str(edge["target_id"])))].append(edge)
    for rows in grouped.values():
        rows.sort(key=lambda row: _hex_to_int(str(row["relocation_file_offset"])))
    return dict(grouped)


def _local_adjacency(
    edges: list[dict[str, Any]], object_name: str
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if (
            edge["object"] != object_name
            or edge["relocation_classification"] != "local-section-relative"
            or edge["caller_section_id"] is None
        ):
            continue
        adjacency[str(edge["caller_section_id"])].add(str(edge["target_id"]))
    return dict(adjacency)


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    found: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(adjacency.get(current, ()))
    return found


def _single_target_section(
    graph_report: dict[str, Any], object_name: str, symbol: str
) -> str:
    sections = graph_report["objects"][object_name]["target_sections"][symbol]
    _require(
        len(sections) == 1,
        f"{object_name} does not have one observed {symbol} section",
    )
    return str(sections[0])


def _symbol_sections(
    graph_report: dict[str, Any], object_name: str, symbol: str
) -> list[str]:
    return [
        str(section["section_id"])
        for section in graph_report["objects"][object_name]["code_sections"]
        if symbol in section["symbols"]
    ]


def _legacy_target_rows(
    graph_report: dict[str, Any],
    all_edges: list[dict[str, Any]],
    parsed_entries: dict[str, list[str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for object_name in LEGACY_OBJECTS:
        entries = parsed_entries[object_name]
        _require(
            all(target in entries for target in TARGETS),
            f"{object_name} official ENTRY table lost a target",
        )
        init_section = _single_target_section(graph_report, object_name, "EPD_Init")
        upload_section = _single_target_section(
            graph_report, object_name, "Upload_Temperature_LUT"
        )
        adjacency = _local_adjacency(all_edges, object_name)
        display_edges = [
            edge
            for edge in all_edges
            if edge["object"] == object_name
            and edge["relocation_classification"] == "local-section-relative"
            and edge["callee_symbol"] == "Upload_Temperature_LUT"
        ]
        _require(len(display_edges) == 7, f"{object_name} upload edge count changed")
        root_sections = set(
            graph_report["objects"][object_name]["local_graph"]["root_sections"]
        )
        _require(
            all(edge["caller_section_id"] in root_sections for edge in display_edges),
            f"{object_name} upload caller stopped being a local root",
        )
        _require(
            upload_section not in _reachable(init_section, adjacency),
            f"{object_name} EPD_Init unexpectedly reaches upload",
        )
        result[object_name] = {
            "official_xlib_entries_confirm_both_targets": True,
            "EPD_Init_section": init_section,
            "Upload_Temperature_LUT_section": upload_section,
            "EPD_Init_reaches_Upload_Temperature_LUT_locally": False,
            "local_root_display_to_upload_edges": [
                {
                    "caller_section_id": edge["caller_section_id"],
                    "caller_symbols": edge["caller_symbols"],
                    "relocation_file_offset": edge["relocation_file_offset"],
                    "source_line": edge["source_line"],
                    "target_section_id": edge["target_id"],
                }
                for edge in display_edges
            ],
            "local_root_display_to_upload_edge_count": len(display_edges),
        }
    return result


def _objects_with_both_targets(
    graph_report: dict[str, Any],
    all_edges: list[dict[str, Any]],
    parsed_entries: dict[str, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for object_name, entries in sorted(parsed_entries.items()):
        if not all(target in entries for target in TARGETS):
            continue
        init_sections = _symbol_sections(graph_report, object_name, "EPD_Init")
        upload_sections = _symbol_sections(
            graph_report, object_name, "Upload_Temperature_LUT"
        )
        _require(
            len(init_sections) == 1 and len(upload_sections) == 1,
            f"{object_name} target section mapping changed",
        )
        adjacency = _local_adjacency(all_edges, object_name)
        reaches = upload_sections[0] in _reachable(init_sections[0], adjacency)
        rows.append(
            {
                "object": object_name,
                "EPD_Init_section": init_sections[0],
                "Upload_Temperature_LUT_section": upload_sections[0],
                "EPD_Init_reaches_Upload_Temperature_LUT_locally": reaches,
            }
        )
    return rows


def _main_candidate_paths(
    grouped_calls: dict[tuple[str, int], list[dict[str, Any]]],
    graph_report: dict[str, Any],
    all_edges: list[dict[str, Any]],
    parsed_entries: dict[str, list[str]],
) -> list[dict[str, Any]]:
    main_groups = {
        rows[0]["callee_symbol"]: (external_index, rows)
        for (object_name, external_index), rows in grouped_calls.items()
        if object_name == "main.r43"
    }
    paths: list[dict[str, Any]] = []
    for provider_object in LEGACY_OBJECTS:
        provider_entries = parsed_entries[provider_object]
        upload_section = _single_target_section(
            graph_report, provider_object, "Upload_Temperature_LUT"
        )
        for symbol in MAIN_DISPLAY_SYMBOLS:
            if symbol not in main_groups or symbol not in provider_entries:
                continue
            provider_sections = _symbol_sections(graph_report, provider_object, symbol)
            _require(
                len(provider_sections) == 1,
                f"{provider_object} {symbol} section mapping changed",
            )
            provider_section = provider_sections[0]
            matching_local = [
                edge
                for edge in all_edges
                if edge["object"] == provider_object
                and edge["relocation_classification"] == "local-section-relative"
                and edge["caller_section_id"] == provider_section
                and edge["target_id"] == upload_section
                and edge["callee_symbol"] == "Upload_Temperature_LUT"
            ]
            if not matching_local:
                continue
            _require(
                len(matching_local) == 1,
                f"{provider_object} {symbol} upload edge is not unique",
            )
            external_index, call_sites = main_groups[symbol]
            paths.append(
                {
                    "root_object": "main.r43",
                    "root_section_id": "0x19",
                    "root_symbol": "main",
                    "main_external_index": external_index,
                    "main_external_symbol": symbol,
                    "main_call_site_count": len(call_sites),
                    "main_symbol_evidence": (
                        "PAIRED_DEBUG_SOURCE_ONLY_XLIB_E2_VERSION_BOUNDARY"
                    ),
                    "candidate_provider_object": provider_object,
                    "candidate_provider_entry_confirmed_by_official_xlib": True,
                    "candidate_provider_section_id": provider_section,
                    "local_upload_target_section_id": upload_section,
                    "local_upload_edge_file_offset": matching_local[0][
                        "relocation_file_offset"
                    ],
                    "provider_selection_proven": False,
                    "compatible_with_current_final_d43_direct_inputs": False,
                    "path_classification": (
                        "NAME_MATCHED_CANDIDATE_PATH_ONLY_NOT_A_LINKED_ROOT_CHAIN"
                    ),
                }
            )
    return paths


def build_report(
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
    *,
    runner: xlib_audit.XlibListRunner = xlib_audit._default_runner,
) -> dict[str, Any]:
    """Build a deterministic, metadata-only provider-candidate graph."""

    try:
        xlib_identity = xlib_audit._pin_xlib(xlib_path)
        graph_report = graph.build_report(iar_root, include_all_edges=True)
    except (graph.GraphError, xlib_audit.XlibAuditError) as error:
        raise ProviderGraphError(str(error)) from error

    object_dir = iar_root / graph.OBJECT_DIR_REL
    parsed_entries: dict[str, list[str]] = {}
    parsed_externals: dict[str, list[str]] = {}
    object_tables: dict[str, dict[str, Any]] = {}
    table_manifest_rows: list[dict[str, Any]] = []

    for identity in graph_report["identity"]["objects"]:
        object_name = str(identity["name"])
        try:
            externals, entries = runner(xlib_path, object_dir / object_name)
        except xlib_audit.XlibAuditError as error:
            raise ProviderGraphError(str(error)) from error
        _require(
            externals["status"] == entries["status"],
            f"{object_name} LIST-EXTERNALS/LIST-ENTRIES status mismatch",
        )
        expected_boundary = object_name in xlib_audit.EXPECTED_UNSUPPORTED_OBJECTS
        if externals["status"] == "PARSED":
            _require(
                not expected_boundary,
                f"{object_name} unexpectedly became XLIB-parseable",
            )
            expected_module = Path(object_name).stem
            _require(
                externals["module"] == expected_module,
                f"{object_name} EXTERNAL module changed",
            )
            _require(
                entries["module"] == expected_module,
                f"{object_name} ENTRY module changed",
            )
            external_names = list(externals["symbols"])
            entry_names = list(entries["symbols"])
            parsed_externals[object_name] = external_names
            parsed_entries[object_name] = entry_names
            table_manifest_rows.append(
                {
                    "object": object_name,
                    "external_table_sha256": externals["table_sha256"],
                    "entry_table_sha256": entries["table_sha256"],
                }
            )
            object_tables[object_name] = {
                "ubrof_version_byte": identity["ubrof_version_byte"],
                "xlib_status": "PARSED",
                "external_count": len(external_names),
                "entry_count": len(entry_names),
                "external_table_sha256": externals["table_sha256"],
                "entry_table_sha256": entries["table_sha256"],
            }
        else:
            _require(
                expected_boundary,
                f"{object_name} unexpectedly hit an XLIB version boundary",
            )
            _require(
                externals["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
                f"{object_name} has unknown XLIB status",
            )
            object_tables[object_name] = {
                "ubrof_version_byte": identity["ubrof_version_byte"],
                "xlib_status": "UNSUPPORTED_STACK_USAGE_TAG_E2",
                "diagnostic": xlib_audit.UNKNOWN_E2,
                "external_count": None,
                "entry_count": None,
                "empty_tables_inferred": False,
            }

    _require(len(parsed_entries) == 26, "official XLIB parsed-object count changed")
    table_manifest = sorted(
        table_manifest_rows, key=lambda row: row["object"].casefold()
    )
    table_manifest_sha = _sha256(_canonical_bytes(table_manifest))
    _require(
        table_manifest_sha == EXPECTED_PARSEABLE_TABLE_MANIFEST_SHA256,
        "official XLIB table manifest changed",
    )

    all_edges = list(graph_report["graph"]["edges"])
    grouped_calls = _group_external_calls(all_edges)
    _require(
        len(grouped_calls) == EXPECTED_EXTERNAL_GROUPS,
        f"external group count changed: {len(grouped_calls)}",
    )
    _require(
        sum(len(rows) for rows in grouped_calls.values()) == EXPECTED_EXTERNAL_CALLS,
        "external call count changed",
    )

    provider_index = _entry_table_index(parsed_entries)
    observed_definition_index = _observed_local_definition_index(graph_report)
    boundary_objects = xlib_audit.EXPECTED_UNSUPPORTED_OBJECTS
    provider_groups: list[dict[str, Any]] = []
    verified_calls = 0
    verified_groups = 0
    boundary_calls = 0
    boundary_groups = 0
    classification_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"groups": 0, "call_sites": 0}
    )

    for (caller_object, external_index), rows in sorted(
        grouped_calls.items(), key=lambda item: (item[0][0].casefold(), item[0][1])
    ):
        observed_symbols = sorted({str(row["callee_symbol"]) for row in rows})
        _require(
            len(observed_symbols) == 1,
            f"{caller_object} external index {external_index} has mixed debug names",
        )
        observed_symbol = observed_symbols[0]
        if caller_object in parsed_externals:
            table = parsed_externals[caller_object]
            _require(
                external_index < len(table),
                f"{caller_object} external index {external_index} is out of range",
            )
            official_symbol: str | None = table[external_index]
            _require(
                official_symbol == observed_symbol,
                f"{caller_object} external index {external_index} disagrees with XLIB",
            )
            symbol_basis = "OFFICIAL_XLIB_EXTERNAL_TABLE"
            verified_groups += 1
            verified_calls += len(rows)
        else:
            official_symbol = None
            symbol_basis = "PAIRED_DEBUG_SOURCE_ONLY_XLIB_E2_VERSION_BOUNDARY"
            boundary_groups += 1
            boundary_calls += len(rows)

        candidate_providers = provider_index.get(observed_symbol, [])
        candidate_class = _candidate_classification(len(candidate_providers))
        classification_counts[candidate_class]["groups"] += 1
        classification_counts[candidate_class]["call_sites"] += len(rows)
        boundary_local_candidates = [
            row
            for row in observed_definition_index.get(observed_symbol, [])
            if row["object"] in boundary_objects
        ]
        provider_groups.append(
            {
                "caller_object": caller_object,
                "caller_xlib_status": object_tables[caller_object]["xlib_status"],
                "external_index": external_index,
                "official_xlib_external_symbol": official_symbol,
                "observed_debug_symbol": observed_symbol,
                "symbol_basis": symbol_basis,
                "call_site_count": len(rows),
                "call_sites": [
                    {
                        "relocation_file_offset": row["relocation_file_offset"],
                        "caller_section_id": row["caller_section_id"],
                        "caller_symbols": row["caller_symbols"],
                        "source_file": row["source_file"],
                        "source_line": row["source_line"],
                    }
                    for row in rows
                ],
                "official_xlib_entry_provider_candidates": candidate_providers,
                "official_candidate_classification": candidate_class,
                "version_boundary_observed_local_definition_candidates": (
                    boundary_local_candidates
                ),
                "provider_object_proven": False,
            }
        )

    _require(
        (verified_calls, verified_groups)
        == (EXPECTED_XLIB_VERIFIED_CALLS, EXPECTED_XLIB_VERIFIED_GROUPS),
        "official XLIB verified call/group count changed",
    )
    _require(
        (boundary_calls, boundary_groups)
        == (EXPECTED_VERSION_BOUNDARY_CALLS, EXPECTED_VERSION_BOUNDARY_GROUPS),
        "XLIB version-boundary call/group count changed",
    )
    expected_classification_counts = {
        "NONE_IN_26_XLIB_PARSEABLE_OBJECTS": {"groups": 24, "call_sites": 351},
        "UNIQUE_WITHIN_26_XLIB_PARSEABLE_OBJECTS": {"groups": 38, "call_sites": 43},
        "AMBIGUOUS_WITHIN_26_XLIB_PARSEABLE_OBJECTS": {
            "groups": 6,
            "call_sites": 7,
        },
    }
    _require(
        dict(classification_counts) == expected_classification_counts,
        "provider-candidate classification counts changed",
    )
    boundary_definition_groups = [
        row
        for row in provider_groups
        if row["version_boundary_observed_local_definition_candidates"]
    ]
    _require(
        len(boundary_definition_groups) == 16
        and sum(row["call_site_count"] for row in boundary_definition_groups) == 235,
        "version-boundary observed-definition candidate count changed",
    )

    legacy_targets = _legacy_target_rows(graph_report, all_edges, parsed_entries)
    both_target_objects = _objects_with_both_targets(
        graph_report, all_edges, parsed_entries
    )
    _require(
        [row["object"] for row in both_target_objects]
        == ["E2801.r43", "E2802.r43", "ED020OC4.r43"],
        "objects exporting both target entries changed",
    )
    _require(
        not any(
            row["EPD_Init_reaches_Upload_Temperature_LUT_locally"]
            for row in both_target_objects
        ),
        "an object gained a local EPD_Init-to-upload path",
    )
    upload_external_calls = [
        row
        for row in provider_groups
        if row["observed_debug_symbol"] == "Upload_Temperature_LUT"
    ]
    _require(not upload_external_calls, "an external upload call appeared")

    main_candidate_paths = _main_candidate_paths(
        grouped_calls,
        graph_report,
        all_edges,
        parsed_entries,
    )
    _require(len(main_candidate_paths) == 8, "main legacy candidate-path count changed")
    _require(
        sum(row["main_call_site_count"] for row in main_candidate_paths) == 10,
        "main legacy candidate-path weighted call count changed",
    )

    current = graph_report["current_delivered_direct_xlink_inputs"]
    _require(
        current["project_r43_objects"] == ["DELAY.r43", "E6_73.r43", "main.r43"],
        "current direct project-input set changed",
    )
    _require(
        all(name not in current["project_r43_objects"] for name in LEGACY_OBJECTS),
        "a legacy object entered the current direct project-input set",
    )
    _require(
        current["Upload_Temperature_LUT_marker_in_final_d43"] is False,
        "current final d43 gained the upload marker",
    )

    main_epd_init_group = next(
        row
        for row in provider_groups
        if row["caller_object"] == "main.r43"
        and row["observed_debug_symbol"] == "EPD_Init"
    )
    e6_init_candidates = [
        row
        for row in main_epd_init_group[
            "version_boundary_observed_local_definition_candidates"
        ]
        if row["object"] == "E6_73.r43"
    ]
    _require(
        e6_init_candidates == [{"object": "E6_73.r43", "section_id": "0xD"}],
        "E6_73 observed EPD_Init definition mapping changed",
    )
    current_e6_candidate_edges: list[dict[str, Any]] = []
    for row in provider_groups:
        if row["caller_object"] != "main.r43":
            continue
        e6_candidates = [
            candidate
            for candidate in row[
                "version_boundary_observed_local_definition_candidates"
            ]
            if candidate["object"] == "E6_73.r43"
        ]
        for candidate in e6_candidates:
            current_e6_candidate_edges.append(
                {
                    "caller_object": "main.r43",
                    "caller_section_id": "0x19",
                    "external_index": row["external_index"],
                    "observed_debug_symbol": row["observed_debug_symbol"],
                    "call_site_count": row["call_site_count"],
                    "candidate_provider": candidate,
                    "caller_external_table_officially_parsed": False,
                    "provider_entry_table_officially_parsed": False,
                    "provider_selection_proven": False,
                }
            )
    _require(
        len(current_e6_candidate_edges) == 7
        and sum(row["call_site_count"] for row in current_e6_candidate_edges) == 8,
        "main-to-E6 observed-definition candidate edge count changed",
    )
    _require(
        {row["observed_debug_symbol"] for row in current_e6_candidate_edges}
        == {"EPD_Init", *MAIN_DISPLAY_SYMBOLS},
        "main-to-E6 display/init candidate set changed",
    )
    legacy_read_data_rows: dict[str, dict[str, Any]] = {}
    for object_name in LEGACY_OBJECTS:
        read_data = next(
            row
            for row in provider_groups
            if row["caller_object"] == object_name
            and row["observed_debug_symbol"] == "ReadData"
        )
        _require(
            read_data["external_index"] == 3
            and read_data["official_xlib_external_symbol"] == "ReadData"
            and not read_data["official_xlib_entry_provider_candidates"]
            and not read_data["version_boundary_observed_local_definition_candidates"],
            f"{object_name} ReadData provider boundary changed",
        )
        legacy_read_data_rows[object_name] = {
            "external_index": read_data["external_index"],
            "official_xlib_external_symbol": read_data["official_xlib_external_symbol"],
            "call_site_count": read_data["call_site_count"],
            "provider_candidates_in_29_delivered_object_evidence": [],
            "provider_object_or_transport_proven": False,
        }

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "r43_objects": 29,
            "xlib_parsed_objects": 26,
            "xlib_version_boundary_objects": 3,
            "offline_read_only": True,
            "official_xlib_process_invoked": True,
            "temporary_ascii_object_copies_only": True,
            "source_objects_modified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "live_token_or_claim_generated": False,
            "visible_refreshes": 0,
            "raw_object_code_emitted": False,
            "raw_disassembly_emitted": False,
            "raw_lut_waveform_key_or_plaintext_emitted": False,
        },
        "identity": {
            "xlib": xlib_identity,
            "r43_object_manifest_sha256": graph_report["identity"][
                "object_manifest_sha256"
            ],
            "parsed_external_and_entry_table_manifest_sha256": table_manifest_sha,
            "dependency_manifest": graph_report["identity"]["dependency_manifest"],
            "final_d43": graph_report["identity"]["final_d43"],
        },
        "official_tool_boundary": {
            "parsed_objects": sorted(parsed_entries, key=str.casefold),
            "unsupported_objects": sorted(boundary_objects, key=str.casefold),
            "diagnostic": xlib_audit.UNKNOWN_E2,
            "unsupported_tables_treated_as_empty": False,
            "transformed_copies_used": False,
            "matching_6_3_4_78_or_newer_xlib_still_required": True,
        },
        "object_symbol_tables": object_tables,
        "external_provider_candidate_graph": {
            "external_call_groups": len(provider_groups),
            "external_call_sites": sum(
                row["call_site_count"] for row in provider_groups
            ),
            "official_xlib_verified_groups": verified_groups,
            "official_xlib_verified_call_sites": verified_calls,
            "version_boundary_groups": boundary_groups,
            "version_boundary_call_sites": boundary_calls,
            "candidate_classification_counts": expected_classification_counts,
            "groups_with_version_boundary_observed_definition_candidates": len(
                boundary_definition_groups
            ),
            "call_sites_with_version_boundary_observed_definition_candidates": sum(
                row["call_site_count"] for row in boundary_definition_groups
            ),
            "external_provider_object_edges_proven": 0,
            "candidate_rows": provider_groups,
        },
        "target_chain_adjudication": {
            "objects_with_official_entries_for_both_EPD_Init_and_upload": (
                both_target_objects
            ),
            "legacy_objects": legacy_targets,
            "external_calls_to_exact_Upload_Temperature_LUT": 0,
            "main_to_legacy_upload_name_matched_candidate_paths": (
                main_candidate_paths
            ),
            "main_to_legacy_upload_candidate_path_count": len(main_candidate_paths),
            "main_to_legacy_upload_candidate_call_site_weight": sum(
                row["main_call_site_count"] for row in main_candidate_paths
            ),
            "candidate_paths_are_proven_linked_paths": False,
            "main_to_EPD_Init_to_upload_candidate_path_found": False,
            "legacy_ReadData_external_dependencies": legacy_read_data_rows,
            "current_final_d43": {
                "direct_project_r43_inputs": current["project_r43_objects"],
                "direct_toolkit_r43_inputs": current["toolkit_r43_objects"],
                "main_EPD_Init_call_site": current["EPD_Init_edge"],
                "E6_73_EPD_Init_observed_definition_candidate": (e6_init_candidates[0]),
                "main_to_E6_73_observed_definition_candidate_edges": (
                    current_e6_candidate_edges
                ),
                "main_to_E6_73_candidate_edge_groups": len(current_e6_candidate_edges),
                "main_to_E6_73_candidate_call_sites": sum(
                    row["call_site_count"] for row in current_e6_candidate_edges
                ),
                "E6_73_observed_Upload_Temperature_LUT_section": None,
                "E6_73_provider_is_officially_resolved_by_this_xlib": False,
                "E2801_or_E2802_is_a_direct_input": False,
                "Upload_Temperature_LUT_marker_present": False,
                "candidate_main_to_legacy_upload_paths_compatible_with_direct_inputs": (
                    False
                ),
            },
            "proven_main_or_EPD_Init_root_to_E2801_or_E2802_upload": False,
            "verdict": (
                "NOT_FOUND_WITHIN_OFFICIAL_XLIB_TABLES_AND_PINNED_LINK_MEMBERSHIP"
            ),
        },
        "evidence_boundaries": {
            "xlib_EXTERNAL_index_to_symbol_is_independently_proven_for_26_objects": (
                True
            ),
            "xlib_ENTRY_name_to_candidate_object_is_independently_proven_for_26_objects": (
                True
            ),
            "matching_EXTERNAL_and_ENTRY_names_prove_link_selection": False,
            "unique_candidate_within_26_parseable_objects_proves_provider": False,
            "all_29_objects_are_one_link_unit": False,
            "orphan_E2801_E2802_link_manifests_delivered": False,
            "UBROF11_official_external_or_entry_tables_recovered": False,
            "observed_local_definition_name_is_complete_PUBLIC_table": False,
            "toolkit_library_symbols_parsed": False,
            "indirect_calls_ruled_out": False,
            "unpublished_or_stripped_code_ruled_out": False,
            "provider_implementation_or_transport_proven": False,
            "current_SPD1657_ABI_or_dual_controller_contract_proven": False,
            "authorizes_hardware_or_visible_refresh": False,
            "meaning": (
                "Official XLIB proves ordered EXTERNAL/ENTRY names for 26 UBROF10 "
                "objects. Exact-name joins enumerate reproducible provider candidates, "
                "but cannot select a provider without a link manifest. main/E6_73/DELAY "
                "remain explicit E2 version boundaries. Name-matching main display calls "
                "to E2801/E2802 yields candidate inventory paths into their seven local "
                "upload callers, but both legacy objects are absent from the delivered "
                "final-d43 direct inputs, so those paths are not linked root chains."
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
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                indent=None if args.compact else 2,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        OSError,
        subprocess.SubprocessError,
        ProviderGraphError,
        xlib_audit.XlibAuditError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
