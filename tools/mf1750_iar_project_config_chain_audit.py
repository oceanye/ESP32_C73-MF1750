#!/usr/bin/env python3
"""Audit the delivered IAR workspace/configuration/final-output chain offline.

This tool separates five evidence levels which are easy to conflate in the
mixed IAR delivery: project declarations, dependency producer inventory,
direct XLINK inputs, object-level provider candidates, and a provider/root
that is actually supported by the delivered final-link artifacts.

The output is metadata-only.  It never opens serial ports, talks to a device
or network, flashes firmware, creates a physical-action token, or requests a
display refresh.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import xml.etree.ElementTree as ET

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as r43_graph


KIND = "mf1750-iar-project-config-chain-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IAR_ROOT = r43_graph.DEFAULT_IAR_ROOT

EXPECTED_TREE_FILES = 66
EXPECTED_TREE_BYTES = 5_631_058
EXPECTED_TREE_MANIFEST_SHA256 = (
    "b1763fff073ec820cef28fd34ff5d6f26e3cd3b09100188df40b930e2c5d60b0"
)

EXPECTED_ARTIFACTS: dict[str, tuple[int, str]] = {
    "C2_Example.eww": (
        164,
        "7c0ac36031e5f81b52434f5820cbdea9f9e0f64542bfc14176fb19e0fcd1fd0d",
    ),
    "C2_Example.ewp": (
        82_056,
        "409e32ff9ecb6714efea2fd2478ce6fbf1821f55984989f01760d456bdb79582",
    ),
    "C2_Example.ewd": (
        27_219,
        "4c0f8ff688732846db277f2eab3b63c469d1933beeada130afbd6602037fd75d",
    ),
    "C2_Example.ewt": (
        165_166,
        "dc2abb37153c18ab73338dc90a91ad95b948b735461842896934ba5e5f2e972b",
    ),
    "C2_Example.dep": (
        11_281,
        "8b59303fa9d7a0b1ce453b117009ef4b468e1cac81e8a615e30ea026aa7dbaeb",
    ),
    "Debug/Obj/build.ninja": (
        615,
        "e1e73860a3a1c2a95930402fea1d2d61da36bd9831ba083a2ecedd2ae3dcd6e1",
    ),
    "Debug/Obj/.ninja_deps": (
        16,
        "971a2f3c7663b07e7e7a9854021dd31229b977a27ea8c13cf14f23da57814dcb",
    ),
    "Debug/Obj/.ninja_log": (
        1_019,
        "eb88f32444d45106c4107c2e2852f9de8741cec8364395f7f35d3849ee76b127",
    ),
    "Debug/Obj/C2_Example.pbd": (
        318_435,
        "79dcf7bc7b682d496494a637af44542dc7ae10a364704aad614be1d7a1945160",
    ),
    "Debug/Obj/C2_Example.pbd.browse": (
        318_435,
        "79dcf7bc7b682d496494a637af44542dc7ae10a364704aad614be1d7a1945160",
    ),
    "Debug/Obj/C2_Example.pbd.linf": (
        351,
        "a9fd7b11392d7aae737330e1cd16efe9b825499393a8270a836a3c0f118426fd",
    ),
    "Debug/Obj/C2_Example.pbw": (
        1_608_932,
        "1df9e7188a8b27a296841007a8a6897e64ac0d9d081dacdc2ed0ed4afea47e4b",
    ),
    "Debug/Obj/E2801.pbi": (
        935,
        "545424f7839df9dd21796d8c0e4050d8ae4f69f3441e79ab3467127a2194bead",
    ),
    "Debug/Obj/E6_73.xcl": (
        10_805,
        "ee0b8c4354f8298325d632830b8efbca2fd450a47630e268df0f4ae54105dd7d",
    ),
    "Debug/Obj/E6_73.pbi.xcl": (
        10_972,
        "e6e0f17d49acf1dc89de895fb4836b597ffb714c597cefd5057a6e90ae300473",
    ),
    "Debug/Exe/C2_Example.d43": (
        39_332,
        "56e915d88b4b26ca29baaea766015e43d8f9ba222095650f9a1bebbe6c3906c0",
    ),
    "Debug/Exe/C2_Example.txt": (
        6_150,
        "593194d980f66852223a47493f788ea671335f47b4f1b5c9880d83b9a04ddb49",
    ),
    "E6_73.c": (
        9_182,
        "8f511aca743bcd55d751d6d935261733b5931eb2fa101bb6d9f815cd0a8b06e9",
    ),
    "Version_Descriptions.txt": (
        105,
        "53c39d6a7a0e14c17c6437727df6d26362f8a5f5c9ca550f28827047e44f9ecc",
    ),
}

PROJECT_SOURCES = (
    "$PROJ_DIR$\\DELAY.C",
    "$PROJ_DIR$\\E6_73.c",
    "$PROJ_DIR$\\main.c",
)
TARGET_OBJECTS = ("E6_73.r43", "E2801.r43", "E2802.r43", "ED020OC4.r43")
TARGET_MARKERS = ("EPD_Init", "Upload_Temperature_LUT", "E2801", "E2802", "E6_73")


class ProjectChainError(RuntimeError):
    """An identity or bounded configuration-chain invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProjectChainError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pin(path: Path, expected: tuple[int, str], label: str) -> bytes:
    _require(path.is_file(), f"{label} is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == expected[0],
        f"{label} size mismatch: expected {expected[0]}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == expected[1],
        f"{label} SHA-256 mismatch: expected {expected[1]}, got {digest}",
    )
    return payload


def _pin_inputs(iar_root: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    files = sorted(
        (path for path in iar_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(iar_root).as_posix(),
    )
    rows: list[dict[str, Any]] = []
    for path in files:
        payload = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(iar_root).as_posix(),
                "size_bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    manifest = "".join(
        f"{row['path']}\0{row['size_bytes']}\0{row['sha256']}\n" for row in rows
    ).encode("utf-8")
    manifest_sha256 = _sha256(manifest)
    _require(len(rows) == EXPECTED_TREE_FILES, "IAR project file count changed")
    _require(
        sum(int(row["size_bytes"]) for row in rows) == EXPECTED_TREE_BYTES,
        "IAR project byte count changed",
    )
    _require(
        manifest_sha256 == EXPECTED_TREE_MANIFEST_SHA256,
        "IAR project tree manifest changed",
    )

    pinned = {
        relative: _pin(iar_root / relative, expected, relative)
        for relative, expected in EXPECTED_ARTIFACTS.items()
    }
    return pinned, {
        "file_count": len(rows),
        "size_bytes": sum(int(row["size_bytes"]) for row in rows),
        "manifest_sha256": manifest_sha256,
        "key_artifacts": [
            {
                "path": relative,
                "size_bytes": expected[0],
                "sha256": expected[1],
            }
            for relative, expected in EXPECTED_ARTIFACTS.items()
        ],
    }


def _parse_xml(payload: bytes, label: str, expected_root: str) -> ET.Element:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ProjectChainError(f"{label} XML parse failed: {error}") from error
    _require(root.tag == expected_root, f"{label} root tag changed: {root.tag}")
    return root


def _configurations(root: ET.Element, label: str) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for node in root.findall("configuration"):
        name = (node.findtext("name") or "").strip()
        _require(name and name not in result, f"{label} has duplicate/empty config")
        result[name] = node
    _require(set(result) == {"Debug", "Release"}, f"{label} configs changed")
    return result


def _option_values(
    configuration: ET.Element, setting_name: str, option: str
) -> list[str]:
    settings = [
        node
        for node in configuration.findall("settings")
        if (node.findtext("name") or "").strip() == setting_name
    ]
    _require(
        len(settings) == 1,
        f"{configuration.findtext('name')} missing/duplicate {setting_name}",
    )
    options = [
        node
        for node in settings[0].findall("./data/option")
        if (node.findtext("name") or "").strip() == option
    ]
    _require(
        len(options) == 1,
        f"{configuration.findtext('name')} {setting_name}/{option} changed",
    )
    return [
        "" if node.text is None else node.text for node in options[0].findall("state")
    ]


def _one_option(configuration: ET.Element, setting_name: str, option: str) -> str:
    values = _option_values(configuration, setting_name, option)
    _require(len(values) == 1, f"{setting_name}/{option} is not scalar")
    return values[0]


def _build_action(configuration: ET.Element) -> dict[str, str]:
    settings = [
        node
        for node in configuration.findall("settings")
        if (node.findtext("name") or "").strip() == "BUILDACTION"
    ]
    _require(len(settings) == 1, "missing/duplicate BUILDACTION")
    data = settings[0].find("data")
    _require(data is not None, "BUILDACTION data is missing")
    return {
        "prebuild": data.findtext("prebuild") or "",
        "postbuild": data.findtext("postbuild") or "",
    }


def _parse_project(payload: bytes) -> dict[str, Any]:
    root = _parse_xml(payload, "C2_Example.ewp", "project")
    _require((root.findtext("fileVersion") or "").strip() == "3", "EWP version changed")
    sources = tuple(
        (node.findtext("name") or "").strip() for node in root.findall("file")
    )
    _require(sources == PROJECT_SOURCES, "project-declared source set changed")
    _require(not root.findall("group"), "unexpected project group appeared")
    _require(not root.findall(".//excluded"), "unexpected source exclusion appeared")

    configs = _configurations(root, "EWP")
    rows: dict[str, Any] = {}
    for name, node in configs.items():
        rows[name] = {
            "toolchain": (node.findtext("./toolchain/name") or "").strip(),
            "debug_flag": int((node.findtext("debug") or "").strip()),
            "declared_sources": list(sources),
            "file_specific_exclusions": [],
            "paths": {
                "exe": _one_option(node, "General", "ExePath"),
                "obj": _one_option(node, "General", "ObjPath"),
                "list": _one_option(node, "General", "ListPath"),
            },
            "target": _one_option(node, "General", "OGChipSelectMenu"),
            "compiler": {
                "include_paths": _option_values(node, "ICC430", "newCCIncludePaths"),
                "optimization_level": int(_one_option(node, "ICC430", "CCOptLevel")),
                "defines": _option_values(node, "ICC430", "ADefines"),
                "object_name_template": _one_option(node, "ICC430", "OutputFile"),
            },
            "runtime_library": {
                "configuration_header": _one_option(node, "General", "RTConfigPath"),
                "library": _one_option(node, "General", "RTLibraryPath"),
            },
            "link": {
                "primary_output": _one_option(node, "XLINK", "OutputFile"),
                "output_format_code": _one_option(node, "XLINK", "OutputFormat"),
                "format_variant_code": _one_option(node, "XLINK", "FormatVariant"),
                "generate_extra_output": _one_option(
                    node, "XLINK", "GenerateExtraOutput"
                )
                == "1",
                "extra_output": _one_option(node, "XLINK", "ExtraOutputFile"),
                "listing_enabled": _one_option(node, "XLINK", "XList") == "1",
                "linker_command_override": _one_option(node, "XLINK", "XclOverride")
                == "1",
                "configured_linker_command": _one_option(node, "XLINK", "XclFile"),
                "extra_options_enabled": _one_option(
                    node, "XLINK", "XExtraOptionsCheck"
                )
                == "1",
                "extra_options": _one_option(node, "XLINK", "XExtraOptions"),
                "control_files": _one_option(node, "XLINK", "XlinkControlFiles"),
                "input_log_enabled": _one_option(node, "XLINK", "XlinkLogInputFiles")
                == "1",
                "module_selection_log_enabled": _one_option(
                    node, "XLINK", "XlinkLogModuleSelection"
                )
                == "1",
                "call_graph_enabled": _one_option(
                    node, "XLINK", "XlinkCallGraphFileEnable"
                )
                == "1",
            },
            "archive_inputs": _option_values(node, "XAR", "XARInputs"),
            "build_actions": _build_action(node),
        }

    debug = rows["Debug"]
    release = rows["Release"]
    _require(
        debug["toolchain"] == release["toolchain"] == "MSP430", "toolchain changed"
    )
    _require(debug["target"] == "MSP430F5502\tMSP430F5502", "Debug target changed")
    _require(release["target"] == "MSP430F5529\tMSP430F5529", "Release target changed")
    _require(
        debug["link"]["primary_output"] == "C2_Example.d43", "Debug output changed"
    )
    _require(debug["link"]["generate_extra_output"], "Debug extra output disabled")
    _require(
        debug["link"]["extra_output"] == "C2_Example.txt", "Debug extra output changed"
    )
    _require(
        release["link"]["primary_output"] == "C2_Example.txt", "Release output changed"
    )
    _require(
        not release["link"]["generate_extra_output"], "Release extra output enabled"
    )
    for name, row in rows.items():
        _require(
            row["build_actions"] == {"prebuild": "", "postbuild": ""},
            f"{name} build action changed",
        )
        _require(row["archive_inputs"] == [""], f"{name} XAR inputs changed")
        _require(not row["link"]["listing_enabled"], f"{name} linker listing enabled")
        _require(
            not row["link"]["linker_command_override"], f"{name} XCL override enabled"
        )
        _require(
            not row["link"]["extra_options_enabled"],
            f"{name} extra linker options enabled",
        )
        _require(
            row["link"]["extra_options"] == "", f"{name} extra linker options appeared"
        )
        _require(row["link"]["control_files"] == "", f"{name} control files appeared")
        _require(not row["link"]["input_log_enabled"], f"{name} input log enabled")
        _require(
            not row["link"]["module_selection_log_enabled"],
            f"{name} module log enabled",
        )
        _require(not row["link"]["call_graph_enabled"], f"{name} call graph enabled")
    return {
        "file_version": 3,
        "project_level_sources": list(sources),
        "group_count": 0,
        "exclusion_count": 0,
        "configurations": rows,
    }


def _parse_workspace(payload: bytes) -> dict[str, Any]:
    root = _parse_xml(payload, "C2_Example.eww", "workspace")
    projects = [
        (node.findtext("path") or "").strip() for node in root.findall("project")
    ]
    _require(projects == ["$WS_DIR$\\C2_Example.ewp"], "workspace project set changed")
    batch = root.find("batchBuild")
    _require(batch is not None and len(batch) == 0, "workspace batch build changed")
    return {"projects": projects, "batch_build_entries": 0}


def _auxiliary_project_metadata(pinned: dict[str, bytes]) -> dict[str, Any]:
    ewd = _parse_xml(pinned["C2_Example.ewd"], "C2_Example.ewd", "project")
    ewt = _parse_xml(pinned["C2_Example.ewt"], "C2_Example.ewt", "project")
    ewd_configs = list(_configurations(ewd, "EWD"))
    ewt_configs = list(_configurations(ewt, "EWT"))
    ewt_files = [(node.findtext("name") or "").strip() for node in ewt.findall("file")]
    _require(ewt_files == list(PROJECT_SOURCES), "EWT source set changed")
    return {
        "debugger_ewd": {
            "configurations": ewd_configs,
            "classification": "DEBUGGER_SETTINGS_NOT_A_LINK_MANIFEST",
        },
        "static_analysis_ewt": {
            "configurations": ewt_configs,
            "project_files": ewt_files,
            "classification": "C_STAT_SETTINGS_NOT_A_LINK_MANIFEST",
        },
    }


def _dependency_release_state(payload: bytes) -> dict[str, Any]:
    root = _parse_xml(payload, "C2_Example.dep", "project")
    configurations = _configurations(root, "DEP")
    release = configurations["Release"]
    outputs = release.find("outputs")
    _require(outputs is not None, "Release DEP outputs node is missing")
    _require(len(outputs.findall("file")) == 0, "Release DEP outputs appeared")
    _require(not release.findall("file"), "Release DEP producer/input nodes appeared")
    return {
        "output_table_entries": 0,
        "producer_or_input_relation_nodes": 0,
        "classification": "NO_DELIVERED_RELEASE_DEPENDENCY_GRAPH",
    }


def _parse_build_ninja(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8")
    build_rows = []
    for line in text.splitlines():
        match = re.fullmatch(r"build ([^:]+) : (.+)", line)
        if match is not None:
            build_rows.append((match.group(1), match.group(2)))
    expected = [
        ("DELAY.pbi", "index DELAY.xcl"),
        ("E6_73.pbi", "index E6_73.xcl"),
        ("main.pbi", "index main.xcl"),
        ("C2_Example.pbd", "link DELAY.pbi E6_73.pbi main.pbi"),
        ("C2_Example.pbw", "browsedata C2_Example.pbd"),
    ]
    _require(build_rows == expected, "source-browser Ninja graph changed")
    return {
        "classification": "SOURCE_BROWSER_GRAPH_NOT_FIRMWARE_LINK_GRAPH",
        "index_inputs": ["DELAY.xcl", "E6_73.xcl", "main.xcl"],
        "pbd_inputs": ["DELAY.pbi", "E6_73.pbi", "main.pbi"],
        "pbw_input": "C2_Example.pbd",
    }


def _parse_source_browser(payload: bytes) -> dict[str, Any]:
    try:
        rows = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectChainError(f"PBW parse failed: {error}") from error
    _require(isinstance(rows, list) and len(rows) == 3_187, "PBW row count changed")
    path_counts = Counter(
        str(row.get("location", {}).get("path", ""))
        for row in rows
        if isinstance(row, dict)
    )
    name_counts = Counter(
        str(row.get("name", "")) for row in rows if isinstance(row, dict)
    )
    _require(name_counts["EPD_Init"] == 3, "PBW EPD_Init rows changed")
    _require(name_counts["Upload_Temperature_LUT"] == 0, "PBW gained runtime upload")
    serialized = payload
    _require(
        b"E2801" not in serialized and b"E2802" not in serialized,
        "PBW gained E280x lineage",
    )
    project_source_paths = sorted(
        path
        for path in path_counts
        if path.casefold().endswith(("\\delay.c", "\\e6_73.c", "\\main.c"))
    )
    _require(len(project_source_paths) == 3, "PBW project source path set changed")
    return {
        "record_count": len(rows),
        "distinct_location_paths": len(path_counts),
        "project_source_paths": project_source_paths,
        "EPD_Init_name_rows": name_counts["EPD_Init"],
        "Upload_Temperature_LUT_name_rows": 0,
        "E2801_or_E2802_marker_present": False,
        "classification": "CURRENT_E6_SOURCE_BROWSER_AGGREGATE_NOT_LINK_PROOF",
    }


def _source_browser_auxiliary(pinned: dict[str, bytes]) -> dict[str, Any]:
    linf_lines = [
        line
        for line in pinned["Debug/Obj/C2_Example.pbd.linf"]
        .decode("utf-8-sig")
        .splitlines()
        if line
    ]
    linf_names = [Path(line.replace("\\", "/")).name for line in linf_lines]
    _require(
        linf_names
        == [
            "C2_Example.pbd",
            "DELAY.pbi",
            "E6_73.pbi",
            "main.pbi",
        ],
        "PBD LINF aggregation set changed",
    )
    _require(
        all("EPEV073D021_V1_20231027" in line for line in linf_lines),
        "PBD LINF source-browser lineage changed",
    )

    ninja_lines = pinned["Debug/Obj/.ninja_log"].decode("utf-8").splitlines()
    _require(ninja_lines[0] == "# ninja log v5", "Ninja log version changed")
    targets = [line.split("\t")[3] for line in ninja_lines[1:]]
    target_counts = Counter(targets)
    _require(
        target_counts
        == Counter(
            {
                "DELAY.pbi": 3,
                "E6_73.pbi": 4,
                "main.pbi": 3,
                "C2_Example.pbd": 4,
                "C2_Example.pbw": 4,
            }
        ),
        "Ninja source-browser target history changed",
    )

    pbd = pinned["Debug/Obj/C2_Example.pbd"]
    pbd_browse = pinned["Debug/Obj/C2_Example.pbd.browse"]
    _require(pbd == pbd_browse, "PBD and PBD browse copy differ")
    for marker in (b"Upload_Temperature_LUT", b"E2801", b"E2802"):
        _require(marker not in pbd, f"PBD gained {marker.decode('ascii')}")
    return {
        "pbd_linf": {
            "aggregated_names": linf_names,
            "absolute_path_lineage": "EPEV073D021_V1_20231027",
            "E2801_or_E2802_aggregated": False,
            "classification": "SOURCE_BROWSER_INPUT_LIST_NOT_LINKER_INPUT_LIST",
        },
        "ninja_log": {
            "record_count": len(targets),
            "target_counts": dict(sorted(target_counts.items())),
            "E2801_or_E2802_target_present": False,
            "classification": "SOURCE_BROWSER_BUILD_HISTORY_NOT_FIRMWARE_LINK_HISTORY",
        },
        "pbd": {
            "pbd_and_browse_copy_byte_identical": True,
            "Upload_Temperature_LUT_marker_present": False,
            "E2801_or_E2802_marker_present": False,
        },
    }


def _parse_ti_txt(payload: bytes) -> dict[str, Any]:
    try:
        tokens = payload.decode("ascii").split()
    except UnicodeDecodeError as error:
        raise ProjectChainError(f"C2_Example.txt is not ASCII: {error}") from error
    segments: list[tuple[int, bytes]] = []
    address: int | None = None
    data = bytearray()
    terminated = False
    for token in tokens:
        if token == "q":
            terminated = True
            break
        if token.startswith("@"):
            if address is not None:
                segments.append((address, bytes(data)))
            try:
                address = int(token[1:], 16)
            except ValueError as error:
                raise ProjectChainError(f"invalid TI-TXT address {token}") from error
            data = bytearray()
            continue
        _require(address is not None, "TI-TXT data precedes address")
        _require(bool(re.fullmatch(r"[0-9A-Fa-f]{2}", token)), "invalid TI-TXT byte")
        data.append(int(token, 16))
    if address is not None:
        segments.append((address, bytes(data)))
    _require(terminated, "TI-TXT terminator is missing")
    _require(
        [(address, len(data)) for address, data in segments]
        == [(0xA000, 2_000), (0xFFFE, 2)],
        "TI-TXT segment layout changed",
    )
    _require(segments[-1][1] == b"\x00\xa0", "TI-TXT reset vector changed")
    return {
        "format": "TI-TXT",
        "segments": [
            {
                "start_address": f"0x{address:04X}",
                "size_bytes": len(data),
                "sha256": _sha256(data),
            }
            for address, data in segments
        ],
        "total_data_bytes": sum(len(data) for _, data in segments),
        "concatenated_data_sha256": _sha256(b"".join(data for _, data in segments)),
        "reset_vector": "0xA000",
        "contains_symbol_table": False,
    }


def _embedded_source_paths(payload: bytes) -> list[str]:
    return sorted(
        {
            match.group("file").decode("ascii")
            for match in r43_graph.SOURCE_RECORD_RE.finditer(payload)
        }
    )


def _artifact_inventory(iar_root: Path, build_ninja: dict[str, Any]) -> dict[str, Any]:
    files = [path for path in iar_root.rglob("*") if path.is_file()]
    extension_counts = Counter(path.suffix.casefold() or "<none>" for path in files)
    local_xcl = sorted(
        path.relative_to(iar_root).as_posix()
        for path in files
        if path.suffix.casefold() == ".xcl"
    )
    current_index_names = set(build_ninja["index_inputs"])
    current_source_indexer_xcl = [
        path for path in local_xcl if Path(path).name in current_index_names
    ]
    historical_source_indexer_xcl = [
        path for path in local_xcl if Path(path).name not in current_index_names
    ]
    map_or_listing = sorted(
        path.relative_to(iar_root).as_posix()
        for path in files
        if path.suffix.casefold() in {".map", ".lst", ".list"}
    )
    link_response = sorted(
        path
        for path in local_xcl
        if Path(path).name.casefold()
        in {"lnk430f5502.xcl", "multiplier32.xcl", "lnk0t.xcl"}
    )
    debug_list = iar_root / "Debug" / "List"
    _require(debug_list.is_dir(), "Debug/List directory is missing")
    _require(not any(debug_list.iterdir()), "Debug/List is no longer empty")
    _require(len(local_xcl) == 7, "local XCL count changed")
    _require(
        len(current_source_indexer_xcl) == 3, "current SourceIndexer XCL count changed"
    )
    _require(len(historical_source_indexer_xcl) == 4, "historical XCL count changed")
    _require(not map_or_listing, "map/list artifact appeared")
    _require(not link_response, "local linker response file appeared")
    return {
        "extension_counts": dict(sorted(extension_counts.items())),
        "local_xcl_files": local_xcl,
        "current_source_indexer_xcl": current_source_indexer_xcl,
        "historical_source_indexer_xcl": historical_source_indexer_xcl,
        "local_linker_response_xcl": link_response,
        "map_or_listing_files": map_or_listing,
        "Debug_List_directory_empty": True,
        "Release_directory_present": (iar_root / "Release").exists(),
        "classification": (
            "ALL_SEVEN_LOCAL_XCL_FILES_ARE_SOURCE_BROWSER_ARGUMENT_FILES;_"
            "NONE_IS_A_DELIVERED_XLINK_RESPONSE_FILE"
        ),
    }


def _provider_ownership(
    iar_root: Path,
    graph_report: dict[str, Any],
    d43_payload: bytes,
    source_browser: dict[str, Any],
) -> dict[str, Any]:
    dependency = graph_report["dependency_graph"]
    output_inventory = set(dependency["project_r43_output_table_names"])
    direct_inputs = set(dependency["final_d43_direct_project_r43_input_names"])
    current_sources = {Path(path).stem.casefold() for path in PROJECT_SOURCES}
    source_browser_names = {
        Path(path.replace("\\", "/")).stem.casefold()
        for path in source_browser["project_source_paths"]
    }
    rows: dict[str, Any] = {}
    for object_name in TARGET_OBJECTS:
        object_report = graph_report["objects"][object_name]
        payload = (iar_root / r43_graph.OBJECT_DIR_REL / object_name).read_bytes()
        stem = Path(object_name).stem.casefold()
        source_paths = _embedded_source_paths(payload)
        _require(len(source_paths) == 1, f"{object_name} producer source set changed")
        rows[object_name] = {
            "producer_source_embedded_in_object": source_paths[0],
            "project_declared_source_family": stem in current_sources,
            "source_browser_aggregated": stem in source_browser_names,
            "dependency_output_inventory_member": object_name in output_inventory,
            "final_d43_direct_project_input": object_name in direct_inputs,
            "object_entry_candidates": {
                target: object_report["target_sections"][target]
                for target in ("EPD_Init", "Upload_Temperature_LUT")
            },
            "final_d43_marker_counts": {
                target: d43_payload.count(target.encode("ascii"))
                for target in TARGET_MARKERS
            },
            "provider_object_proven_for_current_final_upload": False,
        }

    e6 = rows["E6_73.r43"]
    _require(e6["project_declared_source_family"], "E6_73 project declaration changed")
    _require(
        e6["dependency_output_inventory_member"], "E6_73 producer membership changed"
    )
    _require(e6["final_d43_direct_project_input"], "E6_73 direct input changed")
    _require(e6["object_entry_candidates"]["EPD_Init"] == ["0xD"], "E6 init changed")
    _require(
        not e6["object_entry_candidates"]["Upload_Temperature_LUT"],
        "E6 upload appeared",
    )
    _require(
        e6["final_d43_marker_counts"]["EPD_Init"] == 1, "final EPD_Init marker changed"
    )
    _require(
        e6["final_d43_marker_counts"]["Upload_Temperature_LUT"] == 0,
        "final upload marker appeared",
    )
    e6["provider_status"] = "BOUNDED_CURRENT_DEBUG_EPD_INIT_ATTRIBUTION"
    e6["EPD_Init_provider_attribution_basis"] = (
        "project declaration + DEP producer + direct XLINK membership + object definition + final d43 marker"
    )

    for object_name in ("E2801.r43", "E2802.r43", "ED020OC4.r43"):
        row = rows[object_name]
        _require(
            not row["project_declared_source_family"], f"{object_name} became declared"
        )
        _require(
            not row["dependency_output_inventory_member"],
            f"{object_name} entered DEP outputs",
        )
        _require(
            not row["final_d43_direct_project_input"],
            f"{object_name} entered final link",
        )
        _require(
            bool(row["object_entry_candidates"]["Upload_Temperature_LUT"]),
            f"{object_name} upload candidate disappeared",
        )
        row["provider_status"] = "ORPHAN_OBJECT_PROVIDER_CANDIDATE_NOT_LINKED"
    return rows


def _source_revision_boundary(
    iar_root: Path,
    pinned: dict[str, bytes],
    provider_rows: dict[str, Any],
) -> dict[str, Any]:
    version_text = pinned["Version_Descriptions.txt"].decode("ascii")
    source = pinned["E6_73.c"]
    object_payload = (iar_root / "Debug/Obj/E6_73.r43").read_bytes()
    # The object read above is identity-pinned independently by the r43 graph.
    _require(
        "V1.2 20250116 --> add VDD cut sequence at each display function"
        in version_text,
        "V1.2 description changed",
    )
    _require(
        source.count(b"SWC_L;//VDD SW off") == 6, "V1.2 VDD-cut source count changed"
    )
    _require(
        object_payload.count(b"VDD SW off") == 0,
        "linked E6 object gained V1.2 source records",
    )
    embedded = provider_rows["E6_73.r43"]["producer_source_embedded_in_object"]
    _require("V1.1_20231030" in embedded, "E6 object producer version changed")
    return {
        "package_version_line": "V1.2 20250116 --> add VDD cut sequence at each display function",
        "delivered_E6_73_c": {
            "sha256": EXPECTED_ARTIFACTS["E6_73.c"][1],
            "VDD_cut_debug_statement_occurrences": 6,
        },
        "delivered_direct_input_E6_73_r43": {
            "sha256": r43_graph.EXPECTED_OBJECTS["E6_73.r43"][1],
            "embedded_producer_source": embedded,
            "VDD_cut_debug_statement_occurrences": 0,
        },
        "final_output_revision_provenance": "V1.1_OBJECT_LINEAGE_NOT_V1.2_REBUILD",
        "boundary": (
            "The project declaration points at the delivered V1.2 source, but the shipped "
            "Debug object/final-output chain embeds V1.1_20231030 provenance. The ready-made "
            "d43/TI-TXT must not be represented as a rebuild of the V1.2 source."
        ),
    }


def build_report(iar_root: Path = DEFAULT_IAR_ROOT) -> dict[str, Any]:
    """Build a deterministic, identity-pinned metadata report."""

    pinned, tree_identity = _pin_inputs(iar_root)
    workspace = _parse_workspace(pinned["C2_Example.eww"])
    project = _parse_project(pinned["C2_Example.ewp"])
    auxiliary = _auxiliary_project_metadata(pinned)
    build_ninja = _parse_build_ninja(pinned["Debug/Obj/build.ninja"])
    source_browser = _parse_source_browser(pinned["Debug/Obj/C2_Example.pbw"])
    source_browser_auxiliary = _source_browser_auxiliary(pinned)
    inventory = _artifact_inventory(iar_root, build_ninja)

    graph_report = r43_graph.build_report(iar_root)
    dependency = graph_report["dependency_graph"]
    release_dependency = _dependency_release_state(pinned["C2_Example.dep"])
    d43 = pinned["Debug/Exe/C2_Example.d43"]
    ti_txt = _parse_ti_txt(pinned["Debug/Exe/C2_Example.txt"])
    provider_rows = _provider_ownership(iar_root, graph_report, d43, source_browser)

    direct_rows = dependency["final_d43_direct_xlink_input_rows"]
    _require(
        [row["name"] for row in direct_rows]
        == [
            "lnk430f5502.xcl",
            "multiplier32.xcl",
            "DELAY.r43",
            "E6_73.r43",
            "main.r43",
            "dl430xlsfn.r43",
        ],
        "Debug direct XLINK chain changed",
    )
    _require(
        not inventory["Release_directory_present"],
        "Release artifact directory appeared",
    )
    _require(
        dependency["root_xlink_output_rows"][1]["name"] == "C2_Example.txt",
        "Debug alternate output relation changed",
    )

    final_markers = {
        marker: d43.count(marker.encode("ascii")) for marker in TARGET_MARKERS
    }
    _require(
        final_markers
        == {
            "EPD_Init": 1,
            "Upload_Temperature_LUT": 0,
            "E2801": 0,
            "E2802": 0,
            "E6_73": 10,
        },
        "final d43 target marker inventory changed",
    )
    runtime_library_markers = {
        "dl430xlsfn": d43.count(b"dl430xlsfn"),
        "dl430xsfn": d43.count(b"dl430xsfn"),
    }
    _require(
        runtime_library_markers == {"dl430xlsfn": 12, "dl430xsfn": 0},
        "final d43 runtime-library marker inventory changed",
    )

    project_output_names = set(dependency["project_r43_output_table_names"])
    direct_project_names = set(dependency["final_d43_direct_project_r43_input_names"])
    inventory_only_names = sorted(project_output_names - direct_project_names)
    _require(
        inventory_only_names
        == [
            "EL073.r43",
            "HAL_FLASH.r43",
            "HAL_PMAP.r43",
            "HAL_PMM.r43",
            "HAL_TLV.r43",
            "HAL_UCS.r43",
        ],
        "DEP inventory-only project object set changed",
    )

    source_revision = _source_revision_boundary(iar_root, pinned, provider_rows)
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_or_refresh_requested": False,
            "physical_action_token_or_claim_created": False,
            "raw_object_or_firmware_bytes_emitted": False,
        },
        "identity": {
            "iar_project_root": r43_graph.IAR_ROOT_REL.as_posix(),
            **tree_identity,
        },
        "workspace": workspace,
        "project": project,
        "auxiliary_project_metadata": auxiliary,
        "artifact_inventory": inventory,
        "dependency_and_link_chain": {
            "Debug": {
                "dependency_file_version": dependency["file_version"],
                "producer_output_inventory": dependency["r43_output_table_rows"],
                "declared_source_to_object_checks": dependency[
                    "zero_based_producer_output_checks"
                ],
                "direct_XLINK_inputs": direct_rows,
                "root_XLINK_outputs": dependency["root_xlink_output_rows"],
                "classification": (
                    "DIRECT_INPUT_MEMBERSHIP_PROVEN_BY_PINNED_DEP_RELATION"
                ),
            },
            "Release": release_dependency,
        },
        "source_browser_chain": {
            "ninja": build_ninja,
            "pbw": source_browser,
            "auxiliary": source_browser_auxiliary,
            "pbd_and_pbd_browse_are_byte_identical": True,
            "pbd_sha256": EXPECTED_ARTIFACTS["Debug/Obj/C2_Example.pbd"][1],
        },
        "configuration_snapshot_vs_generated_Debug_chain": {
            "project_declared_source_count": len(PROJECT_SOURCES),
            "DEP_project_object_inventory_count": len(project_output_names),
            "DEP_direct_project_object_count": len(direct_project_names),
            "DEP_inventory_only_not_direct_input": inventory_only_names,
            "EWP_Debug_runtime_library_option": project["configurations"]["Debug"][
                "runtime_library"
            ]["library"],
            "DEP_direct_runtime_library": dependency[
                "final_d43_direct_toolkit_r43_input_names"
            ][0],
            "final_d43_runtime_library_marker_counts": runtime_library_markers,
            "adjudication": (
                "The generated Debug dependency/final artifacts select and name "
                "dl430xlsfn.r43 even though the EWP option snapshot names dl430xsfn.r43. "
                "The DEP direct-input relation and final marker are used for this final, "
                "without guessing why the project option snapshot differs."
            ),
        },
        "final_outputs": {
            "Debug_d43": {
                "path": "Debug/Exe/C2_Example.d43",
                "size_bytes": EXPECTED_ARTIFACTS["Debug/Exe/C2_Example.d43"][0],
                "sha256": EXPECTED_ARTIFACTS["Debug/Exe/C2_Example.d43"][1],
                "target_marker_counts": final_markers,
                "classification": "DEBUG_SYMBOL_BEARING_FINAL_OUTPUT",
            },
            "Debug_extra_TI_TXT": {
                "path": "Debug/Exe/C2_Example.txt",
                "size_bytes": EXPECTED_ARTIFACTS["Debug/Exe/C2_Example.txt"][0],
                "sha256": EXPECTED_ARTIFACTS["Debug/Exe/C2_Example.txt"][1],
                **ti_txt,
                "relation": "EXTRA_OUTPUT_OF_THE_SAME_DEBUG_XLINK_ROOT",
                "independent_provider_or_link_manifest": False,
            },
            "Release": {
                "declared_primary_name": "C2_Example.txt",
                "delivered_output_found": False,
                "delivered_dependency_graph_found": False,
            },
        },
        "producer_and_provider_ownership": provider_rows,
        "source_revision_boundary": source_revision,
        "adjudication": {
            "current_Debug_main_root_present": True,
            "current_Debug_E6_73_EPD_Init_attribution_supported": True,
            "current_Debug_Upload_Temperature_LUT_present": False,
            "E2801_or_E2802_directly_linked": False,
            "independent_alternate_final_with_runtime_upload_found": False,
            "final_linked_root_combining_main_or_EPD_Init_with_Upload_Temperature_LUT_found": False,
            "verdict": "NO_FINAL_LINKED_ROOT_TO_RUNTIME_UPLOAD_IN_DELIVERED_CONFIGURATIONS",
            "wording": (
                "The delivered Debug chain links main/DELAY/E6_73 and the E6 EPD_Init path. "
                "Its TI-TXT is only an extra representation of that same link. Release has no "
                "delivered dependency/output chain. E2801, E2802, and ED020OC4 remain orphan "
                "provider candidates; no delivered configuration links any of their runtime "
                "upload entries to a main/display root."
            ),
        },
        "evidence_boundaries": {
            "project_declaration_is_link_proof": False,
            "dependency_output_inventory_is_direct_input_proof": False,
            "object_entry_name_is_provider_selection_proof": False,
            "source_browser_name_or_path_is_link_proof": False,
            "TI_TXT_without_symbols_is_independent_provider_proof": False,
            "provider_candidate_name_join_is_final_link_proof": False,
            "missing_map_or_listing_is_global_nonexistence_proof": False,
            "negative_scope": (
                "The negative result is bounded to the exact 66-file extracted IAR tree, its "
                "identity-pinned workspace/project/DEP/source-browser/final artifacts, and the "
                "29 delivered r43 objects. It does not exclude unpublished projects or outputs."
            ),
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
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.iar_root)
        payload = _serialize(report, args.compact)
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (OSError, ProjectChainError, r43_graph.GraphError) as error:
        print(f"IAR project/config chain audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
