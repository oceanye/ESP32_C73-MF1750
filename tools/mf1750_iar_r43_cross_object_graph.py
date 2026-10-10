#!/usr/bin/env python3
"""Build an identity-pinned cross-object graph for the delivered IAR r43 set.

The 29 inputs mix UBROF10 and UBROF11.  IAR does not publish the binary tag
encoding needed for a general-purpose reader, and no matching XLIB executable
is delivered.  This tool therefore parses only byte families that are both
observable in, and pinned to, these exact objects:

* length-delimited 0xCD symbol-name records;
* A1 CODE section declarations and C7 section-origin records;
* CALLA debug-source records immediately paired with a 0x5D/0x5E relocation.

It deliberately calls local targets "definitions", not PUBLIC exports.  A
PUBLIC/EXTERN table requires matching XLIB LIST-ENTRIES/LIST-EXTERNALS output;
plain symbol strings are never promoted to call edges.  The report contains
metadata only and never emits object bytes, LUT bytes, keys, or plaintext.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
IAR_ROOT_REL = Path(
    "参考资料/E6_73_sample code_V1.2_20250116/E6_73_sample code_V1.2_20250116"
)
DEFAULT_IAR_ROOT = REPO_ROOT / IAR_ROOT_REL
OBJECT_DIR_REL = Path("Debug/Obj")
DEPENDENCY_REL = Path("C2_Example.dep")
FINAL_REL = Path("Debug/Exe/C2_Example.d43")

KIND = "mf1750-iar-r43-cross-object-graph"
SCHEMA_VERSION = 2

EXPECTED_DEPENDENCY = {
    "size_bytes": 11_281,
    "sha256": "8b59303fa9d7a0b1ce453b117009ef4b468e1cac81e8a615e30ea026aa7dbaeb",
}
EXPECTED_FINAL = {
    "size_bytes": 39_332,
    "sha256": "56e915d88b4b26ca29baaea766015e43d8f9ba222095650f9a1bebbe6c3906c0",
}

# The key is case-sensitive because the delivered object names are.  Every
# offset interpretation is rejected before use unless all identities match.
# fmt: off
EXPECTED_OBJECTS: dict[str, tuple[int, str, int]] = {
    "DAC.r43": (14_328, "1b53d6d8f7e0c9b025eb41fe0c553b67f715aaa2c192955bfd32e8216beed9fe", 10),
    "DELAY.r43": (1_774, "82eaf1f5ae2ee28f7df7dafb7e9ecf8b46731d7f98784a4731d9b49f638c96da", 11),
    "descriptors.r43": (17_840, "4e23bb439501546fcc594afea5670052bf13d74aa41b930935c639821b22e319", 10),
    "dma.r43": (24_363, "65540be65a254bd1d30fa13af01cc8f5161d2d71b6e51e74cc8658b7709fb908", 10),
    "E2801.r43": (315_632, "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3", 10),
    "E2802.r43": (328_062, "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce", 10),
    "E6_73.r43": (109_582, "0f4d22c6d07f79d9ededffd50f155dc96d802b0e90bf908c30f2b85f1714ee2f", 11),
    "ED020OC2.r43": (179_160, "b7ca54419667cdec9fe2d0059d7dcf86be8a7890b8144230bd603f1901ddb63a", 10),
    "ED020OC4.r43": (222_033, "6f97cafa87e90a51b9f64f1fbbcdd27e1b24e7b42c19d452df210cdec2f0502e", 10),
    "EL073.r43": (123_542, "c03343c6f1c261422f636a9581a9839833717eb2239ea93bd5e74f692f35a8f4", 10),
    "HAL_FLASH.r43": (17_416, "14fe7361d265cc4668b7e151098415ab58cf1d49b08d1e0bb3ab64b93730b9de", 10),
    "HAL_PMAP.r43": (12_881, "639b42be19688a515081aa85c4097a8e0eb62ada1cd8b2236dd82c57eee8d618", 10),
    "HAL_PMM.r43": (19_880, "752ac62fe74566752af8da1db86211ff8606e2beffc2c0d14a596d9491ea2dd1", 10),
    "HAL_TLV.r43": (22_461, "c3f3cc038c8b5cf400a16cd7c39af95d1e03ee4576b89e85a8ac83f52ab20a43", 10),
    "HAL_UCS.r43": (29_433, "bb9f2509f9bb897ac5336481a236c73b4a606b95847e7dd16cf71d82c49fa54b", 10),
    "main.r43": (29_684, "76ada9c8846226457ef74537a345ca1e057e8c11abc1002423424dfffd2640f4", 11),
    "PENG030D01.r43": (92_911, "0758ef7eecfd379a61a51bdef232267caa6ce397e4ed7b2ecc8a08d005a75e0b", 10),
    "PENG073D01.r43": (98_504, "4beed455dc2398f4c652d83145aead95a832dc055338b90e4ae72367b08d6c2f", 10),
    "usb.r43": (127_850, "1d20a56fb1ddfaf0f0890f17a3ec0347dcc958750a9d4ec2974f1bf95d08b9f2", 10),
    "UsbCdc.r43": (129_669, "b96101413114c035a7920d16fea5d86bcf3009beb163c47045af24475e9845e0", 10),
    "usbConstructs.r43": (22_828, "4e792b5fb0ed8059463d2a3b66812b577fe4af1e81da6dd7cefe169b0e6e2056", 10),
    "usbEventHandling.r43": (17_038, "8733697272b85a0e1f744d931c1a3fb26546df6c8ae0b837543625bc585cc303", 10),
    "UsbHid.r43": (10_837, "56b0192f343790fdf217431a8e34472773ea9474180260ed61b1bd1e35270bab", 10),
    "UsbHidReq.r43": (9_129, "f8da280e0c82b1f4ab3e822b1ecfc44d30beeb8985da8cf179d43ac133f2aa6c", 10),
    "UsbIsr.r43": (54_314, "d8939171b79f8988413d1c49774e8809fef2bcc97903c85f4e8021b028e32809", 10),
    "UsbMscReq.r43": (1_304, "6109ffe8c2bb4f070e20e1b3a522fb0dddd7ddfb98089ef7d956d4138e3094d1", 10),
    "UsbMscScsi.r43": (10_894, "3c6850f24ce51b48310f1039f09a1d51dfadfcf16ca377bd3bf876ca03aead93", 10),
    "UsbMscStateMachine.r43": (10_910, "f9a8a52011cb0da190e9173716eff2a442cd59111f157df9e57a660fc025088e", 10),
    "UsbPHDC.r43": (1_302, "04221d6ef592879287a50065c0690f40752dcf32406b5a37104fd3bcc6088a31", 10),
}
# fmt: on
EXPECTED_OBJECT_MANIFEST_SHA256 = (
    "08f7b10936d066441c09843ee0345ec3f61ac3735ae521a1d892af100c0ba70d"
)

TARGET_SYMBOLS = ("EPD_Init", "Upload_Temperature_LUT", "dataBuff")
LEGACY_TARGET_OBJECTS = ("E2801.r43", "E2802.r43")

# E6_73's EPD_Init has no branch-label record and no same-object caller.  This
# one mapping is independently pinned by its exact source-line span, the
# shipped E6_73.c, main's external relocation, and the final d43 symbol marker.
CURRENT_E6_INIT_SECTION = 0x0D

SOURCE_RECORD_RE = re.compile(
    rb" File: (?P<file>[^\x00\r\n]+), Line: (?P<line>\d+) \n"
    rb" Source: (?P<source>[ -~]+)"
)
DIRECT_CALL_RE = re.compile(
    rb" File: (?P<file>[^\x00\r\n]+), Line: (?P<line>\d+) \n"
    rb" Source: (?P<source>CALLA\s+#(?P<encoded_symbol>[A-Za-z0-9_?$@.]+)s)"
    rb"\xff\xff\x80\x00\x00\x00\xff\xff\x9d\x00\x5b"
    rb"(?P<operator>[\x5d\x5e])(?P<target_id>.)(?P<addend>.{4})",
    re.DOTALL,
)
CODE_SECTION_RE = re.compile(rb"\xa1(?P<section_id>.)\x21\x04CODE")
BRANCH_LABEL_RE = re.compile(rb"\?\?(?P<name>[A-Za-z0-9_?$@.]+)_\d+pa")


class GraphError(ValueError):
    """Raised when an identity or observed-record invariant changes."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex(value: int | None) -> str | None:
    return None if value is None else f"0x{value:X}"


def _find_all(payload: bytes, needle: bytes) -> list[int]:
    result: list[int] = []
    offset = 0
    while True:
        offset = payload.find(needle, offset)
        if offset < 0:
            return result
        result.append(offset)
        offset += 1


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphError(message)


def _pin_file(path: Path, expected: dict[str, Any], label: str) -> bytes:
    payload = path.read_bytes()
    _require(
        len(payload) == expected["size_bytes"],
        f"{label} size mismatch: expected {expected['size_bytes']}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == expected["sha256"],
        f"{label} SHA-256 mismatch: expected {expected['sha256']}, got {digest}",
    )
    return payload


def _symbol_name_records(payload: bytes) -> list[dict[str, Any]]:
    """Decode only structurally complete observed 0xCD namespace-1 names."""

    records: list[dict[str, Any]] = []
    for offset in _find_all(payload, b"\xcd\x00\x00\x00"):
        if offset + 5 > len(payload):
            continue
        record_length = payload[offset + 4]
        body = payload[offset + 5 : offset + 5 + record_length]
        if len(body) < 9 or body[:4] != b"\x01\x00\x00\x00":
            continue
        name_length = body[4]
        if len(body) != 4 + 1 + name_length + 4:
            continue
        if body[-4:] != b"\xff\xff\xff\xff":
            continue
        raw_name = body[5 : 5 + name_length]
        if not raw_name or any(value < 0x20 or value > 0x7E for value in raw_name):
            continue
        records.append(
            {
                "file_offset": _hex(offset),
                "name": raw_name.decode("ascii"),
                "record_length": record_length,
            }
        )
    return records


def _code_sections(payload: bytes) -> tuple[list[int], list[tuple[int, int]]]:
    declared = sorted(
        {match.group("section_id")[0] for match in CODE_SECTION_RE.finditer(payload)}
    )
    _require(declared, "no observed A1 CODE section declarations")
    starts: list[tuple[int, int]] = []
    for section_id in declared:
        marker = bytes((0xC7, section_id, 0, 0, 0, 0))
        offsets = _find_all(payload, marker)
        _require(
            len(offsets) == 1,
            f"CODE section {_hex(section_id)} has {len(offsets)} zero-origin C7 records",
        )
        starts.append((offsets[0], section_id))
    starts.sort()
    return declared, starts


def _source_records(payload: bytes) -> list[dict[str, Any]]:
    return [
        {
            "file_offset_int": match.start(),
            "source_file": Path(match.group("file").decode("ascii", "replace")).name,
            "source_line": int(match.group("line")),
            "source": match.group("source").decode("ascii"),
        }
        for match in SOURCE_RECORD_RE.finditer(payload)
    ]


def _section_at(
    file_offset: int, starts: list[tuple[int, int]]
) -> tuple[int, int] | None:
    offsets = [item[0] for item in starts]
    index = bisect_right(offsets, file_offset) - 1
    return None if index < 0 else starts[index]


def _direct_calls(
    payload: bytes, starts: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for match in DIRECT_CALL_RE.finditer(payload):
        current = _section_at(match.start(), starts)
        operator = match.group("operator")[0]
        _require(operator in (0x5D, 0x5E), "unexpected relocation operator")
        encoded = match.group("encoded_symbol").decode("ascii")
        calls.append(
            {
                "relocation_file_offset_int": match.start(),
                "caller_section_id_int": None if current is None else current[1],
                "callee_symbol": encoded,
                "encoded_debug_symbol": f"{encoded}s",
                "source_file": Path(
                    match.group("file").decode("ascii", "replace")
                ).name,
                "source_line": int(match.group("line")),
                "observed_operator": _hex(operator),
                "target_id_int": match.group("target_id")[0],
                "addend_int": int.from_bytes(match.group("addend"), "little"),
                "relocation_classification": (
                    "external-index" if operator == 0x5D else "local-section-relative"
                ),
                "evidence": "paired-CALLA-debug-source-and-relocation",
            }
        )
    return calls


def _choose_section_names(
    payload: bytes,
    starts: list[tuple[int, int]],
    calls: list[dict[str, Any]],
) -> dict[int, set[str]]:
    names: dict[int, set[str]] = {}

    def add(section_id: int, name: str) -> None:
        names.setdefault(section_id, set()).add(name)

    for call in calls:
        if call["relocation_classification"] == "local-section-relative":
            add(int(call["target_id_int"]), str(call["callee_symbol"]))
    for record in _source_records(payload):
        current = _section_at(int(record["file_offset_int"]), starts)
        if current is None:
            continue
        for match in BRANCH_LABEL_RE.finditer(str(record["source"]).encode("ascii")):
            add(current[1], match.group("name").decode("ascii"))
    return names


def _canonical_names(candidates: set[str]) -> list[str]:
    """Discard only strict truncation prefixes; preserve real ambiguities."""

    return sorted(
        name
        for name in candidates
        if not any(name != other and other.startswith(name) for other in candidates)
    )


def _reachable(start: int, adjacency: dict[int, set[int]]) -> set[int]:
    found: set[int] = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node in found:
            continue
        found.add(node)
        pending.extend(adjacency.get(node, ()))
    return found


def _object_report(
    name: str, payload: bytes
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected_size, expected_sha, expected_version = EXPECTED_OBJECTS[name]
    _require(len(payload) == expected_size, f"{name} size changed after pin")
    _require(_sha256(payload) == expected_sha, f"{name} digest changed after pin")
    _require(payload[:1] == b"\x01", f"{name} UBROF module marker changed")
    _require(payload[1] == expected_version, f"{name} UBROF version changed")

    symbol_records = _symbol_name_records(payload)
    declared, starts = _code_sections(payload)
    calls = _direct_calls(payload, starts)
    section_name_sets = _choose_section_names(payload, starts, calls)
    if name == "E6_73.r43":
        add_names = section_name_sets.setdefault(CURRENT_E6_INIT_SECTION, set())
        add_names.add("EPD_Init")

    section_names = {
        section_id: _canonical_names(candidates)
        for section_id, candidates in section_name_sets.items()
    }
    adjacency: dict[int, set[int]] = {section: set() for section in declared}
    incoming: set[int] = set()
    for call in calls:
        caller = call["caller_section_id_int"]
        if (
            caller is None
            or call["relocation_classification"] != "local-section-relative"
        ):
            continue
        target = int(call["target_id_int"])
        if target in adjacency:
            adjacency[int(caller)].add(target)
            incoming.add(target)
    roots = sorted(set(declared) - incoming)

    target_sections: dict[str, list[int]] = {}
    for target in TARGET_SYMBOLS[:2]:
        target_sections[target] = sorted(
            section_id for section_id, names in section_names.items() if target in names
        )

    source_records = _source_records(payload)
    data_buff_reference_sections: dict[int, int] = {}
    for record in source_records:
        if re.search(
            r"(?<![A-Za-z0-9_])dataBuff(?![A-Za-z0-9_])", str(record["source"])
        ):
            current = _section_at(int(record["file_offset_int"]), starts)
            if current is not None:
                data_buff_reference_sections[current[1]] = (
                    data_buff_reference_sections.get(current[1], 0) + 1
                )

    common_roots: list[int] = []
    init_sections = set(target_sections["EPD_Init"])
    upload_sections = set(target_sections["Upload_Temperature_LUT"])
    for root in roots:
        reached = _reachable(root, adjacency)
        if reached & init_sections and reached & upload_sections:
            common_roots.append(root)

    target_name_records = {
        target: [
            record["file_offset"]
            for record in symbol_records
            if record["name"] == target
        ]
        for target in TARGET_SYMBOLS
    }
    external_calls = [
        call for call in calls if call["relocation_classification"] == "external-index"
    ]
    local_calls = [
        call
        for call in calls
        if call["relocation_classification"] == "local-section-relative"
    ]

    public_calls: list[dict[str, Any]] = []
    for call in calls:
        caller = call["caller_section_id_int"]
        public_calls.append(
            {
                "relocation_file_offset": _hex(int(call["relocation_file_offset_int"])),
                "caller_section_id": _hex(None if caller is None else int(caller)),
                "caller_symbols": []
                if caller is None
                else section_names.get(int(caller), []),
                "callee_symbol": call["callee_symbol"],
                "encoded_debug_symbol": call["encoded_debug_symbol"],
                "source_file": call["source_file"],
                "source_line": call["source_line"],
                "observed_operator": call["observed_operator"],
                "target_id": _hex(int(call["target_id_int"])),
                "addend": _hex(int(call["addend_int"])),
                "relocation_classification": call["relocation_classification"],
                "evidence": call["evidence"],
            }
        )

    report = {
        "path": f"{IAR_ROOT_REL.as_posix()}/{OBJECT_DIR_REL.as_posix()}/{name}",
        "size_bytes": expected_size,
        "sha256": expected_sha,
        "ubrof_version_byte": expected_version,
        "observed_records": {
            "symbol_name_0xCD_namespace_1": len(symbol_records),
            "A1_CODE_sections": len(declared),
            "C7_zero_origin_CODE_sections": len(starts),
            "paired_CALLA_relocations": len(calls),
            "operator_0x5D_external_index": len(external_calls),
            "operator_0x5E_local_section_relative": len(local_calls),
        },
        "code_sections": [
            {
                "section_id": _hex(section_id),
                "origin_record_file_offset": _hex(
                    next(offset for offset, current in starts if current == section_id)
                ),
                "symbols": section_names.get(section_id, []),
            }
            for section_id in declared
        ],
        "target_symbol_name_records": target_name_records,
        "target_sections": {
            target: [_hex(value) for value in values]
            for target, values in target_sections.items()
        },
        "dataBuff_source_reference_sections": [
            {
                "section_id": _hex(section_id),
                "symbols": section_names.get(section_id, []),
                "source_record_count": count,
            }
            for section_id, count in sorted(data_buff_reference_sections.items())
        ],
        "local_graph": {
            "root_sections": [_hex(value) for value in roots],
            "common_root_reaching_EPD_Init_and_Upload_Temperature_LUT": [
                _hex(value) for value in common_roots
            ],
        },
        "direct_call_edge_count": len(public_calls),
    }
    return report, public_calls


def _manifest_digest(rows: list[dict[str, Any]]) -> str:
    canonical = "".join(
        f"{row['name']}\0{row['size_bytes']}\0{row['sha256']}\n" for row in rows
    ).encode("utf-8")
    return _sha256(canonical)


def _required_element(parent: ET.Element, path: str, label: str) -> ET.Element:
    matches = parent.findall(path)
    _require(len(matches) == 1, f"expected one {label}, found {len(matches)}")
    return matches[0]


def _required_text(element: ET.Element, label: str) -> str:
    value = "" if element.text is None else element.text.strip()
    _require(bool(value), f"{label} is empty")
    return value


def _file_ids(element: ET.Element, label: str) -> list[int]:
    raw = _required_text(element, label)
    tokens = raw.split()
    _require(
        all(token.isdecimal() for token in tokens), f"{label} has a non-integer ID"
    )
    result = [int(token) for token in tokens]
    _require(len(result) == len(set(result)), f"{label} has duplicate IDs")
    return result


def _tool_file_ids(
    file_node: ET.Element, relation: str, tool_name: str, label: str
) -> list[int]:
    relation_node = _required_element(file_node, relation, f"{label} {relation}")
    tools = [
        tool
        for tool in relation_node.findall("tool")
        if (tool.findtext("name") or "").strip() == tool_name
    ]
    _require(
        len(tools) == 1,
        f"expected one {label} {relation}/{tool_name} tool, found {len(tools)}",
    )
    file_element = _required_element(
        tools[0], "file", f"{label} {relation}/{tool_name}/file"
    )
    return _file_ids(file_element, f"{label} {relation}/{tool_name}/file")


def _dependency_basename(path: str) -> str:
    return path.rsplit("\\", maxsplit=1)[-1]


def _dependency_row(file_id: int, paths: list[str]) -> dict[str, Any]:
    _require(
        0 <= file_id < len(paths),
        f"dependency file ID {file_id} is outside the zero-based output table",
    )
    path = paths[file_id]
    lower = path.casefold()
    if lower.startswith("$proj_dir$\\debug\\obj\\") and lower.endswith(".r43"):
        classification = "project-r43-object"
    elif lower.startswith("$toolkit_dir$\\") and lower.endswith(".r43"):
        classification = "toolkit-r43-library"
    elif lower.startswith("$toolkit_dir$\\") and lower.endswith(".xcl"):
        classification = "toolkit-linker-command-file"
    else:
        classification = "other"
    return {
        "file_id": file_id,
        "path": path,
        "name": _dependency_basename(path),
        "classification": classification,
    }


def _named_file_node(
    configuration: ET.Element, expected_name: str, label: str
) -> ET.Element:
    matches = [
        node
        for node in configuration.findall("file")
        if (node.findtext("name") or "").strip() == expected_name
    ]
    _require(len(matches) == 1, f"expected one {label} file node, found {len(matches)}")
    return matches[0]


def parse_dependency_graph(payload: bytes) -> dict[str, Any]:
    """Resolve the pinned DEP's zero-based file IDs without regex inference."""

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise GraphError(f"dependency XML parse failed: {error}") from error
    _require(root.tag == "project", f"unexpected dependency XML root {root.tag!r}")
    file_version = int(
        _required_text(
            _required_element(root, "fileVersion", "dependency fileVersion"),
            "dependency fileVersion",
        )
    )
    _require(file_version == 4, f"unexpected dependency fileVersion {file_version}")

    configurations = [
        node
        for node in root.findall("configuration")
        if (node.findtext("name") or "").strip() == "Debug"
    ]
    _require(
        len(configurations) == 1,
        f"expected one Debug configuration, found {len(configurations)}",
    )
    configuration = configurations[0]
    output_table = _required_element(
        configuration, "outputs", "Debug top-level output file table"
    )
    paths = [
        _required_text(node, f"Debug output file table entry {index}")
        for index, node in enumerate(output_table.findall("file"))
    ]
    _require(len(paths) == 60, f"expected 60 Debug output entries, found {len(paths)}")
    _require(
        len(paths) == len(set(paths)), "Debug output file table has duplicate paths"
    )

    producer_expectations = (
        (
            "$PROJ_DIR$\\E6_73.c",
            56,
            "$PROJ_DIR$\\Debug\\Obj\\E6_73.r43",
        ),
        (
            "$PROJ_DIR$\\DELAY.C",
            44,
            "$PROJ_DIR$\\Debug\\Obj\\DELAY.r43",
        ),
        (
            "$PROJ_DIR$\\main.c",
            38,
            "$PROJ_DIR$\\Debug\\Obj\\main.r43",
        ),
    )
    producer_rows: list[dict[str, Any]] = []
    for source_path, expected_id, expected_output_path in producer_expectations:
        source_node = _named_file_node(configuration, source_path, source_path)
        ids = _tool_file_ids(source_node, "outputs", "ICC430", source_path)
        _require(ids == [expected_id], f"{source_path} ICC430 output ID changed")
        row = _dependency_row(ids[0], paths)
        _require(
            row["path"] == expected_output_path,
            f"{source_path} ICC430 output path changed",
        )
        producer_rows.append({"producer_source": source_path, "tool": "ICC430", **row})

    root_node = _named_file_node(configuration, "[ROOT_NODE]", "Debug root")
    root_xlink_ids = _tool_file_ids(root_node, "outputs", "XLINK", "Debug root")
    root_xlink_rows = [_dependency_row(file_id, paths) for file_id in root_xlink_ids]
    _require(
        [(row["file_id"], row["path"]) for row in root_xlink_rows]
        == [
            (51, "$PROJ_DIR$\\Debug\\Exe\\C2_Example.d43"),
            (13, "$PROJ_DIR$\\Debug\\Exe\\C2_Example.txt"),
        ],
        "Debug root XLINK output relation changed",
    )

    d43_path = "$PROJ_DIR$\\Debug\\Exe\\C2_Example.d43"
    d43_node = _named_file_node(configuration, d43_path, "final d43")
    d43_input_ids = _tool_file_ids(d43_node, "inputs", "XLINK", "final d43")
    direct_input_rows = [_dependency_row(file_id, paths) for file_id in d43_input_ids]
    _require(
        d43_input_ids == [28, 27, 44, 56, 38, 32],
        "final d43 direct XLINK input IDs changed",
    )

    r43_output_rows = [
        _dependency_row(file_id, paths)
        for file_id, path in enumerate(paths)
        if path.casefold().endswith(".r43")
    ]
    project_r43_output_names = [
        str(row["name"])
        for row in r43_output_rows
        if row["classification"] == "project-r43-object"
    ]
    direct_project_names = [
        str(row["name"])
        for row in direct_input_rows
        if row["classification"] == "project-r43-object"
    ]
    direct_toolkit_names = [
        str(row["name"])
        for row in direct_input_rows
        if row["classification"] == "toolkit-r43-library"
    ]
    _require(len(r43_output_rows) == 10, "Debug output table r43 count changed")
    _require(
        len(project_r43_output_names) == 9,
        "Debug project r43 output-table count changed",
    )
    _require(
        set(project_r43_output_names).issubset(EXPECTED_OBJECTS),
        "project r43 output-table names are not a subset of the pinned objects",
    )
    _require(
        direct_project_names == ["DELAY.r43", "E6_73.r43", "main.r43"],
        "final d43 direct project-r43 inputs changed",
    )
    _require(
        direct_toolkit_names == ["dl430xlsfn.r43"],
        "final d43 direct toolkit-r43 inputs changed",
    )

    return {
        "file_version": file_version,
        "configuration": "Debug",
        "file_id_base": 0,
        "output_file_table_entry_count": len(paths),
        "zero_based_producer_output_checks": producer_rows,
        "root_xlink_output_rows": root_xlink_rows,
        "r43_output_table_rows": r43_output_rows,
        "project_r43_output_table_names": project_r43_output_names,
        "final_d43_direct_xlink_input_rows": direct_input_rows,
        "final_d43_direct_project_r43_input_names": direct_project_names,
        "final_d43_direct_toolkit_r43_input_names": direct_toolkit_names,
    }


def build_report(
    iar_root: Path = DEFAULT_IAR_ROOT, *, include_all_edges: bool = False
) -> dict[str, Any]:
    object_dir = iar_root / OBJECT_DIR_REL
    actual_names = sorted(
        (path.name for path in object_dir.glob("*.r43")), key=str.casefold
    )
    expected_names = sorted(EXPECTED_OBJECTS, key=str.casefold)
    _require(
        actual_names == expected_names, "the delivered 29-object filename set changed"
    )

    object_payloads: dict[str, bytes] = {}
    identity_rows: list[dict[str, Any]] = []
    for name in expected_names:
        size, digest, version = EXPECTED_OBJECTS[name]
        payload = _pin_file(
            object_dir / name,
            {"size_bytes": size, "sha256": digest},
            name,
        )
        object_payloads[name] = payload
        _require(payload[1] == version, f"{name} UBROF version byte mismatch")
        identity_rows.append(
            {
                "name": name,
                "size_bytes": size,
                "sha256": digest,
                "ubrof_version_byte": version,
            }
        )
    manifest_sha = _manifest_digest(identity_rows)
    _require(
        manifest_sha == EXPECTED_OBJECT_MANIFEST_SHA256,
        "object-set canonical manifest SHA-256 mismatch",
    )

    dep_payload = _pin_file(
        iar_root / DEPENDENCY_REL, EXPECTED_DEPENDENCY, "C2_Example.dep"
    )
    final_payload = _pin_file(iar_root / FINAL_REL, EXPECTED_FINAL, "C2_Example.d43")
    dependency_graph = parse_dependency_graph(dep_payload)
    direct_project_names = dependency_graph["final_d43_direct_project_r43_input_names"]

    objects: dict[str, dict[str, Any]] = {}
    all_edges: list[dict[str, Any]] = []
    for name in expected_names:
        object_report, edges = _object_report(name, object_payloads[name])
        objects[name] = object_report
        for edge in edges:
            all_edges.append({"object": name, **edge})

    # Exact target call edges are a small, inspectable subset.  A mere symbol
    # name record cannot enter this collection.
    target_edges = [
        edge for edge in all_edges if edge["callee_symbol"] in TARGET_SYMBOLS[:2]
    ]
    upload_edges = [
        edge
        for edge in target_edges
        if edge["callee_symbol"] == "Upload_Temperature_LUT"
    ]
    upload_external_edges = [
        edge
        for edge in upload_edges
        if edge["relocation_classification"] == "external-index"
    ]

    legacy: dict[str, Any] = {}
    for name in LEGACY_TARGET_OBJECTS:
        obj = objects[name]
        init_sections = obj["target_sections"]["EPD_Init"]
        upload_sections = obj["target_sections"]["Upload_Temperature_LUT"]
        relevant = [edge for edge in upload_edges if edge["object"] == name]
        _require(len(init_sections) == 1, f"{name} EPD_Init section not unique")
        _require(len(upload_sections) == 1, f"{name} upload section not unique")
        _require(len(relevant) == 7, f"{name} upload caller count changed")
        _require(
            not obj["local_graph"][
                "common_root_reaching_EPD_Init_and_Upload_Temperature_LUT"
            ],
            f"{name} unexpectedly has a common init/upload root",
        )
        data_refs = {
            row["section_id"]: row["source_record_count"]
            for row in obj["dataBuff_source_reference_sections"]
        }
        _require(init_sections[0] in data_refs, f"{name} init lost dataBuff references")
        _require(
            upload_sections[0] in data_refs, f"{name} upload lost dataBuff references"
        )
        legacy[name] = {
            "EPD_Init_section": init_sections[0],
            "Upload_Temperature_LUT_section": upload_sections[0],
            "EPD_Init_dataBuff_source_records": data_refs[init_sections[0]],
            "Upload_dataBuff_source_records": data_refs[upload_sections[0]],
            "direct_upload_callers": [
                {
                    "caller_section_id": edge["caller_section_id"],
                    "caller_symbols": edge["caller_symbols"],
                    "relocation_file_offset": edge["relocation_file_offset"],
                    "target_section_id": edge["target_id"],
                }
                for edge in relevant
            ],
            "EPD_Init_calls_Upload_Temperature_LUT": any(
                edge["caller_section_id"] == init_sections[0] for edge in relevant
            ),
            "common_local_root_reaches_both": False,
        }

    current_edges = [
        edge for edge in all_edges if edge["object"] in direct_project_names
    ]
    current_upload_edges = [
        edge
        for edge in current_edges
        if edge["callee_symbol"] == "Upload_Temperature_LUT"
    ]
    current_init_edges = [
        edge for edge in current_edges if edge["callee_symbol"] == "EPD_Init"
    ]
    _require(len(current_init_edges) == 1, "current main EPD_Init edge changed")
    _require(current_init_edges[0]["object"] == "main.r43", "EPD_Init caller changed")
    _require(
        current_init_edges[0]["caller_symbols"] == ["main"],
        "main section mapping changed",
    )
    _require(
        not current_upload_edges,
        "direct project-r43 XLINK inputs gained an upload call",
    )
    _require(b"EPD_Init" in final_payload, "final d43 lost EPD_Init marker")
    _require(
        b"Upload_Temperature_LUT" not in final_payload,
        "final d43 gained Upload_Temperature_LUT marker",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "r43_objects": len(identity_rows),
            "UBROF10_objects": sum(
                row["ubrof_version_byte"] == 10 for row in identity_rows
            ),
            "UBROF11_objects": sum(
                row["ubrof_version_byte"] == 11 for row in identity_rows
            ),
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_requested": False,
            "raw_object_bytes_emitted": False,
            "raw_LUT_or_waveform_emitted": False,
            "key_or_plaintext_emitted": False,
        },
        "identity": {
            "object_manifest_sha256": manifest_sha,
            "objects": identity_rows,
            "dependency_manifest": {
                "path": f"{IAR_ROOT_REL.as_posix()}/{DEPENDENCY_REL.as_posix()}",
                **EXPECTED_DEPENDENCY,
            },
            "final_d43": {
                "path": f"{IAR_ROOT_REL.as_posix()}/{FINAL_REL.as_posix()}",
                **EXPECTED_FINAL,
            },
        },
        "observed_format": {
            "versions_are_mixed": True,
            "parsed_record_families": [
                "length-delimited 0xCD namespace-1 symbol-name records",
                "A1 CODE declarations",
                "C7 zero-origin CODE section records",
                "CALLA debug-source records paired with observed 0x5D/0x5E relocation expressions",
            ],
            "operator_classification_basis": (
                "Within the pinned objects, 0x5E targets declared local CODE section IDs; "
                "0x5D targets external indices and is resolved only when independent link-set evidence exists."
            ),
            "general_UBROF_parser": False,
            "matching_XLIB_LIST_ENTRIES_or_LIST_EXTERNALS_available": False,
        },
        "objects": objects,
        "dependency_graph": dependency_graph,
        "graph": {
            "direct_call_edges": len(all_edges),
            "target_edges": target_edges,
            "all_edges_included": include_all_edges,
        },
        "legacy_E2801_E2802": legacy,
        "current_delivered_direct_xlink_inputs": {
            "membership_evidence": (
                "identity-pinned C2_Example.dep Debug/final-d43 inputs/XLINK "
                "zero-based file IDs"
            ),
            "project_r43_objects": direct_project_names,
            "toolkit_r43_objects": dependency_graph[
                "final_d43_direct_toolkit_r43_input_names"
            ],
            "root": {"object": "main.r43", "section_id": "0x19", "symbol": "main"},
            "EPD_Init_edge": current_init_edges[0],
            "resolved_EPD_Init_provider": {
                "object": "E6_73.r43",
                "section_id": _hex(CURRENT_E6_INIT_SECTION),
                "final_d43_symbol_marker_present": True,
            },
            "Upload_Temperature_LUT_symbol_name_in_direct_project_r43_inputs": any(
                objects[name]["target_symbol_name_records"]["Upload_Temperature_LUT"]
                for name in direct_project_names
            ),
            "Upload_Temperature_LUT_direct_call_edges": current_upload_edges,
            "Upload_Temperature_LUT_marker_in_final_d43": False,
            "main_reaches_legacy_runtime_upload": False,
        },
        "adjudication": {
            "external_direct_calls_to_Upload_Temperature_LUT_across_all_29": len(
                upload_external_edges
            ),
            "legacy_upload_calls_are_local_only": len(upload_edges) == 14
            and not upload_external_edges,
            "delivered_root_combining_EPD_Init_dataBuff_and_E2801_or_E2802_upload_found": False,
            "verdict": "NOT_FOUND_WITHIN_PINNED_DELIVERED_GRAPH",
            "meaning": (
                "The final d43 has three direct project-r43 XLINK inputs: DELAY, E6_73, "
                "and main. They contain the current E6_73 EPD_Init path but no "
                "Upload_Temperature_LUT path; the six other project r43 output-table entries "
                "are not direct inputs. E2801 and E2802 are absent from both sets. They each "
                "contain seven local display-to-upload edges in the separately pinned corpus, "
                "while their EPD_Init sections are separate and no local root reaches both."
            ),
        },
        "evidence_boundaries": {
            "symbol_string_is_not_a_call_edge": True,
            "local_definition_is_not_automatically_a_PUBLIC_export": True,
            "direct_xlink_input_is_not_a_call_edge": True,
            "dependency_output_table_membership_is_not_direct_xlink_input": True,
            "all_29_objects_are_not_one_link_unit": True,
            "orphan_objects_have_no_delivered_link_manifest": True,
            "toolkit_r43_direct_input_not_parsed": True,
            "complete_PUBLIC_EXTERN_tables_recovered": False,
            "why": (
                "The official IAR record-tag document names semantic records but does not "
                "publish their binary tag encoding, and a matching XLIB is not delivered. "
                "The DEP output file table mentions ten r43 paths, but its final-d43 XLINK "
                "input relation directly selects only three delivered project objects plus "
                "one undelivered toolkit r43 library. Accordingly this report proves paired "
                "direct relocations and exact direct-input membership, but does not claim "
                "that an absent edge or name proves that unpublished, stripped, indirect-call, "
                "toolkit-library, or differently linked code cannot exist."
            ),
        },
    }
    if include_all_edges:
        report["graph"]["edges"] = all_edges
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--include-all-edges", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.iar_root, include_all_edges=args.include_all_edges)
    except (GraphError, OSError, UnicodeError) as error:
        print(f"IAR r43 graph audit failed: {error}", file=sys.stderr)
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
