#!/usr/bin/env python3
"""Fail-closed static verifier for the MF1750 WROOM B3 schematic.

The verifier is intentionally independent from the schematic generator.  It
parses the KiCad S-expression, asks KiCad to export a resolved netlist, parses
that netlist structurally, and then checks the frozen B2 provenance plus the
electrical contracts for the WROOM, power tree, EPD bus switch, USB-C, and
microSD circuits.

No schematic, PCB, library, relay, serial port, or attached hardware is ever
modified or accessed.  JSON is written to stdout (and optionally to a report
path).  Any missing evidence or failed assertion returns a non-zero status.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
DEFAULT_SCHEMATIC = (
    B3_DIR / "staging" / "mf1750_wroom_b3_power_tf_r3_schematic.kicad_sch"
)
B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_FROZEN_SHA256 = {
    "mf1750_devkitc_b2_pcba_margin.kicad_pro": (
        "fcd393069f22846615113f8296d6553c5ffeee8ba507b7475f81baae9fe4aa27"
    ),
    "mf1750_devkitc_b2_pcba_margin.kicad_sch": (
        "bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb"
    ),
    "mf1750_devkitc_b2_pcba_margin.kicad_pcb": (
        "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
    ),
}

EXPECTED_REVISION = "B3-WROOM-POWER-TF-R3-SCHEMATIC"
EXPECTED_COMPONENT_COUNT = 176
EXPECTED_NET_COUNT = 175
EXPECTED_PIN_NODE_COUNT = 552
EXPECTED_U6_LIB_ID = "B3_WROOM:SN74CB3Q3245PWR"
EXPECTED_U6_VALUE_TOKENS = ("SN74CB3Q3245PWR", "C470961")
EXPECTED_U6_FOOTPRINT = "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm"
EXPECTED_U4_LIB_ID = "B3_WROOM:TPS63070RNMR"
EXPECTED_PTC_LIB_ID = "B3_WROOM:PTC_BSMD1206_075_16V"
EXPECTED_ESD_LIB_ID = "Power_Protection:USBLC6-2SC6"
EXPECTED_ESD_PIN_NAMES = {
    "1": "I/O1",
    "2": "GND",
    "3": "I/O2",
    "4": "I/O2",
    "5": "VBUS",
    "6": "I/O1",
}
EXPECTED_U4_VOUT_PINS = {
    "7": {"name": "VOUT", "type": "power_out"},
    # Pin 8 is physically the second VOUT land.  ``passive`` is the approved
    # ERC model that avoids a duplicate power-output conflict; it is not a
    # different electrical signal or an authorization to remap the pad.
    "8": {"name": "VOUT", "type": "passive"},
}

# TI SCDS124B, PW/TSSOP top view.  Do not replace this with the interleaved
# RGY/VQFN mapping or the common 74x245 transceiver mapping.
U6_OFFICIAL_PIN_NAMES = {
    "1": "NC",
    "2": "A1",
    "3": "A2",
    "4": "A3",
    "5": "A4",
    "6": "A5",
    "7": "A6",
    "8": "A7",
    "9": "A8",
    "10": "GND",
    "11": "B8",
    "12": "B7",
    "13": "B6",
    "14": "B5",
    "15": "B4",
    "16": "B3",
    "17": "B2",
    "18": "B1",
    "19": "OE",
    "20": "VCC",
}
U6_OFFICIAL_PIN_TYPES = {
    "1": "no_connect",
    **{str(pin): "bidirectional" for pin in range(2, 10)},
    "10": "power_in",
    **{str(pin): "bidirectional" for pin in range(11, 19)},
    "19": "input",
    "20": "power_in",
}
U6_EXPECTED_NETS = {
    "19": "EPD_BUF_OE_N",
    "2": "MCU_RST_N",
    "18": "RST_N",
    "3": "MCU_DC",
    "17": "DC",
    "4": "MCU_CSB",
    "16": "CSB",
    "5": "MCU_CS2",
    "15": "CS2",
    "6": "MCU_SCL",
    "14": "SCL",
    "7": "MCU_SI0",
    "13": "SI0",
    "8": "MCU_BUSY_N",
    "12": "BUSY_N",
    "10": "GND",
    "20": "EPD_3V3",
}
U6_UNUSED_CHANNEL_PINS = ("1", "9", "11")


class SExprError(ValueError):
    """Raised for malformed or unsupported S-expression input."""


SExpr = list[object]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tokens(text: str) -> Iterator[str]:
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if char in "()":
            yield char
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < length:
                char = text[index]
                if char == '"':
                    index += 1
                    yield "".join(value)
                    break
                if char == "\\":
                    index += 1
                    if index >= length:
                        raise SExprError("unterminated escape in quoted string")
                    escaped = text[index]
                    value.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
                    index += 1
                    continue
                value.append(char)
                index += 1
            else:
                raise SExprError("unterminated quoted string")
            continue
        start = index
        while index < length and not text[index].isspace() and text[index] not in "()":
            index += 1
        if start == index:
            raise SExprError(f"cannot tokenize character at offset {index}")
        yield text[start:index]


def parse_sexpr(text: str) -> SExpr:
    stack: list[SExpr] = []
    roots: list[SExpr] = []
    for token in _tokens(text):
        if token == "(":
            node: SExpr = []
            if stack:
                stack[-1].append(node)
            else:
                roots.append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise SExprError("unmatched closing parenthesis")
            stack.pop()
        else:
            if not stack:
                raise SExprError("atom outside a list")
            stack[-1].append(token)
    if stack:
        raise SExprError("unterminated list")
    if len(roots) != 1:
        raise SExprError(f"expected exactly one root list, got {len(roots)}")
    if not roots[0]:
        raise SExprError("empty root list")
    return roots[0]


def head(node: object) -> str | None:
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return None


def direct(node: SExpr, tag: str) -> list[SExpr]:
    return [item for item in node[1:] if isinstance(item, list) and head(item) == tag]


def first(node: SExpr, tag: str) -> SExpr | None:
    items = direct(node, tag)
    return items[0] if items else None


def atom(node: SExpr | None, index: int = 1, default: str | None = None) -> str | None:
    if node is None or len(node) <= index or not isinstance(node[index], str):
        return default
    return node[index]


def walk(node: object) -> Iterator[SExpr]:
    if not isinstance(node, list):
        return
    yield node
    for item in node:
        if isinstance(item, list):
            yield from walk(item)


def normalize_pin_name(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def is_unconnected_net(name: str | None) -> bool:
    if not name:
        return True
    lowered = name.lstrip("/").casefold()
    return lowered.startswith("unconnected-") or lowered.startswith("unconnected_(")


def canonical_net(name: str | None) -> str | None:
    """Normalize KiCad's root-sheet '/NET' export spelling to 'NET'."""
    if is_unconnected_net(name):
        return None
    assert name is not None
    return name[1:] if name.startswith("/") else name


@dataclass
class SymbolInstance:
    ref: str
    lib_id: str
    value: str
    footprint: str
    properties: dict[str, str]
    dnp: bool
    in_bom: bool
    on_board: bool


@dataclass
class LibraryPin:
    number: str
    name: str
    electrical_type: str


@dataclass
class LibrarySymbol:
    lib_id: str
    properties: dict[str, str]
    pins: dict[str, LibraryPin]


@dataclass
class NetNode:
    ref: str
    pin: str
    function: str
    pin_type: str


@dataclass
class Check:
    check_id: str
    category: str
    passed: bool
    message: str
    evidence: object | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.check_id,
            "category": self.category,
            "status": "PASS" if self.passed else "FAIL",
            "message": self.message,
        }
        if self.evidence is not None:
            result["evidence"] = self.evidence
        return result


@dataclass
class Audit:
    checks: list[Check] = field(default_factory=list)

    def add(
        self,
        check_id: str,
        category: str,
        passed: bool,
        message: str,
        evidence: object | None = None,
    ) -> None:
        self.checks.append(Check(check_id, category, bool(passed), message, evidence))

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


def property_map(node: SExpr) -> dict[str, str]:
    result: dict[str, str] = {}
    for prop in direct(node, "property"):
        name = atom(prop, 1)
        value = atom(prop, 2, "")
        if name is not None:
            result[name] = value or ""
    return result


def extract_instances(root: SExpr) -> tuple[dict[str, SymbolInstance], list[str]]:
    result: dict[str, SymbolInstance] = {}
    duplicates: list[str] = []
    for node in walk(root):
        if head(node) != "symbol" or first(node, "lib_id") is None:
            continue
        props = property_map(node)
        ref = props.get("Reference", "")
        if not ref:
            continue
        instance = SymbolInstance(
            ref=ref,
            lib_id=atom(first(node, "lib_id"), 1, "") or "",
            value=props.get("Value", ""),
            footprint=props.get("Footprint", ""),
            properties=props,
            dnp=(atom(first(node, "dnp"), 1, "no") == "yes"),
            in_bom=(atom(first(node, "in_bom"), 1, "yes") == "yes"),
            on_board=(atom(first(node, "on_board"), 1, "yes") == "yes"),
        )
        if ref in result:
            duplicates.append(ref)
        else:
            result[ref] = instance
    return result, sorted(set(duplicates))


def extract_library_symbols(root: SExpr) -> dict[str, LibrarySymbol]:
    container = first(root, "lib_symbols")
    if container is None:
        return {}
    result: dict[str, LibrarySymbol] = {}
    for symbol in direct(container, "symbol"):
        lib_id = atom(symbol, 1, "") or ""
        pins: dict[str, LibraryPin] = {}
        for pin in walk(symbol):
            if head(pin) != "pin" or len(pin) < 2 or not isinstance(pin[1], str):
                continue
            number = atom(first(pin, "number"), 1, "") or ""
            name = atom(first(pin, "name"), 1, "") or ""
            if number:
                pins[number] = LibraryPin(number, name, pin[1])
        result[lib_id] = LibrarySymbol(lib_id, property_map(symbol), pins)
    return result


def extract_netlist(
    root: SExpr,
) -> tuple[dict[tuple[str, str], str], dict[str, list[NetNode]], dict[str, dict[str, str]]]:
    pin_to_net: dict[tuple[str, str], str] = {}
    net_nodes: dict[str, list[NetNode]] = {}
    components: dict[str, dict[str, str]] = {}

    component_container = first(root, "components")
    if component_container is not None:
        for comp in direct(component_container, "comp"):
            ref = atom(first(comp, "ref"), 1, "") or ""
            if not ref:
                continue
            components[ref] = {
                "value": atom(first(comp, "value"), 1, "") or "",
                "footprint": atom(first(comp, "footprint"), 1, "") or "",
            }

    nets_container = first(root, "nets")
    if nets_container is None:
        raise SExprError("exported netlist has no (nets ...) section")
    for net in direct(nets_container, "net"):
        net_name = atom(first(net, "name"), 1, "") or ""
        nodes: list[NetNode] = []
        for node in direct(net, "node"):
            ref = atom(first(node, "ref"), 1, "") or ""
            pin = atom(first(node, "pin"), 1, "") or ""
            if not ref or not pin:
                continue
            item = NetNode(
                ref=ref,
                pin=pin,
                function=atom(first(node, "pinfunction"), 1, "") or "",
                pin_type=atom(first(node, "pintype"), 1, "") or "",
            )
            key = (ref, pin)
            if key in pin_to_net and pin_to_net[key] != net_name:
                raise SExprError(
                    f"pin {ref}.{pin} appears on multiple nets: "
                    f"{pin_to_net[key]!r}, {net_name!r}"
                )
            pin_to_net[key] = net_name
            nodes.append(item)
        net_nodes[net_name] = nodes
    return pin_to_net, net_nodes, components


def resolve_kicad_cli(requested: Path | None) -> Path | None:
    if requested is not None:
        return requested.resolve() if requested.is_file() else None
    located = shutil.which("kicad-cli")
    if located:
        return Path(located).resolve()
    candidates = [
        Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
        Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
        Path("/usr/bin/kicad-cli"),
    ]
    return next((path for path in candidates if path.is_file()), None)


def export_netlist(kicad_cli: Path, schematic: Path) -> tuple[SExpr, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="mf1750-b3-static-netlist-") as temp_name:
        output = Path(temp_name) / "candidate.net"
        completed = subprocess.run(
            [
                str(kicad_cli),
                "sch",
                "export",
                "netlist",
                "--output",
                str(output),
                str(schematic),
            ],
            cwd=temp_name,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
        evidence = {
            "command": [str(kicad_cli), "sch", "export", "netlist", "--output", str(output), str(schematic)],
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        if completed.returncode != 0:
            raise RuntimeError(
                "KiCad netlist export failed: "
                + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
            )
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("KiCad netlist export returned success without an output file")
        text = output.read_text(encoding="utf-8", errors="strict")
        evidence["bytes"] = len(text.encode("utf-8"))
        evidence["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return parse_sexpr(text), evidence


def meaningful_pin_net(pin_to_net: dict[tuple[str, str], str], ref: str, pin: str) -> str | None:
    return canonical_net(pin_to_net.get((ref, pin)))


def has_tokens(value: str, tokens: Sequence[str]) -> bool:
    folded = value.casefold()
    return all(token.casefold() in folded for token in tokens)


def audit_schematic(
    schematic: Path,
    source_root: SExpr,
    netlist_root: SExpr,
    netlist_evidence: dict[str, object],
) -> dict[str, object]:
    audit = Audit()
    instances, duplicate_refs = extract_instances(source_root)
    libraries = extract_library_symbols(source_root)
    pin_to_net, net_nodes, net_components = extract_netlist(netlist_root)

    audit.add(
        "source.unique_references",
        "structure",
        not duplicate_refs,
        "schematic references are unique" if not duplicate_refs else "duplicate schematic references found",
        duplicate_refs,
    )
    source_refs_for_parity = {
        ref for ref in instances if not ref.startswith(("#FLG", "#PWR"))
    }
    netlist_refs_for_parity = {
        ref for ref in net_components if not ref.startswith(("#FLG", "#PWR"))
    }
    audit.add(
        "source.netlist_component_parity",
        "structure",
        source_refs_for_parity == netlist_refs_for_parity,
        "source instances and exported netlist component references match",
        {
            "only_in_source": sorted(source_refs_for_parity - netlist_refs_for_parity),
            "only_in_netlist": sorted(netlist_refs_for_parity - source_refs_for_parity),
        },
    )
    observed_scale = {
        "components": len(net_components),
        "nets": len(net_nodes),
        "pin_nodes": len(pin_to_net),
    }
    expected_scale = {
        "components": EXPECTED_COMPONENT_COUNT,
        "nets": EXPECTED_NET_COUNT,
        "pin_nodes": EXPECTED_PIN_NODE_COUNT,
    }
    audit.add(
        "source.expected_scale",
        "structure",
        observed_scale == expected_scale,
        "resolved netlist component/net/pin-node counts match the frozen R3 contract",
        {"expected": expected_scale, "actual": observed_scale},
    )

    title_block = first(source_root, "title_block")
    title = atom(first(title_block, "title"), 1, "") if title_block else ""
    audit.add(
        "source.revision_marker",
        "structure",
        EXPECTED_REVISION in (title or ""),
        f"title contains frozen revision {EXPECTED_REVISION}",
        title,
    )

    observed_b2: dict[str, dict[str, str]] = {}
    for name, expected in B2_FROZEN_SHA256.items():
        path = B2_DIR / name
        actual = sha256_file(path) if path.is_file() else "MISSING"
        observed_b2[name] = {"expected": expected, "actual": actual}
        audit.add(
            f"b2.hash.{Path(name).suffix.lstrip('.')}",
            "b2_provenance",
            actual == expected,
            f"frozen B2 {Path(name).suffix} SHA-256 matches",
            observed_b2[name],
        )

    b2_refs = {
        "J1", "J2", "R4", "R8", "R15", "R16", "Q1", "Q2", "L1", "L2",
        "D1", "D2", "D3", "D4", *{f"TP{index}" for index in range(1, 11)},
    }
    missing_b2_refs = sorted(b2_refs - set(instances))
    audit.add(
        "b2.key_references",
        "b2_preservation",
        not missing_b2_refs,
        "all frozen B2 key references are present",
        missing_b2_refs,
    )

    def instance_check(
        check_id: str,
        ref: str,
        value_tokens: Sequence[str] = (),
        footprint: str | None = None,
        lib_id: str | None = None,
        *,
        assembled: bool = True,
    ) -> SymbolInstance | None:
        item = instances.get(ref)
        ok = item is not None
        reasons: list[str] = []
        if item is None:
            reasons.append("missing")
        else:
            if value_tokens and not has_tokens(item.value, value_tokens):
                ok = False
                reasons.append(f"value={item.value!r}")
            if footprint is not None and item.footprint != footprint:
                ok = False
                reasons.append(f"footprint={item.footprint!r}")
            if lib_id is not None and item.lib_id != lib_id:
                ok = False
                reasons.append(f"lib_id={item.lib_id!r}")
            if assembled and (item.dnp or not item.in_bom or not item.on_board):
                ok = False
                reasons.append(
                    f"dnp={item.dnp}, in_bom={item.in_bom}, on_board={item.on_board}"
                )
            if not assembled and not item.dnp:
                ok = False
                reasons.append("expected DNP")
        audit.add(
            check_id,
            "components",
            ok,
            f"{ref} component contract matches" if ok else f"{ref} component contract mismatch",
            reasons or ({"value": item.value, "footprint": item.footprint} if item else None),
        )
        return item

    critical_components = [
        ("U1", ("ESP32-S3-WROOM-1-N16R8", "C2913202"), "RF_Module:ESP32-S3-WROOM-1"),
        ("U2", ("BQ24074RGTR", "C54313"), "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm"),
        ("U3", ("STM6600CS25DM6F", "C443976"), "Package_DFN_QFN:TDFN-12_2x3mm_P0.5mm"),
        ("U4", ("TPS63070RNMR", "C109322"), "B3_WROOM:TI_RNM0015A_VQFN-HR-15_2.5x3mm"),
        ("U5", ("TPS22950CQDDCRQ1", "C17349276"), "B3_WROOM:TI_DDC0006A_SOT-23-6_2.9x1.6mm"),
        ("U6", EXPECTED_U6_VALUE_TOKENS, EXPECTED_U6_FOOTPRINT),
        ("Q3", ("2N7002", "C8545"), "Package_TO_SOT_SMD:SOT-23-3"),
        ("J4", ("Molex", "1040310811", "C585350"), "Connector_Card:microSD_HC_Molex_104031-0811"),
        ("J5", ("TYPE-C-31-M-12", "C165948"), "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"),
        ("J6", ("BAT+", "BAT-", "10kNTC"), "Connector_JST:JST_PH_S3B-PH-K_1x03_P2.00mm_Horizontal"),
    ]
    for ref, tokens, footprint in critical_components:
        instance_check(f"component.{ref}", ref, tokens, footprint)
    for ref in ("U8", "U9", "U10", "U11"):
        instance_check(
            f"component.{ref}", ref, ("USBLC6-2SC6", "C2827654"),
            "Package_TO_SOT_SMD:SOT-23-6",
            EXPECTED_ESD_LIB_ID,
        )
    instance_check(
        "component.F1",
        "F1",
        ("750mA", "C883128"),
        "Resistor_SMD:R_1206_3216Metric",
        EXPECTED_PTC_LIB_ID,
    )
    instance_check("component.J1", "J1", ("MF-1750", "50pin"),
                   "MF1750_Production:XUNPU_FPC-05FB-50PH20_1x50_P0.5mm_DualContact")
    instance_check("component.J2_dnp", "J2", ("DNP",), assembled=False)
    instance_check("component.R15_dnp", "R15", ("0R", "DNP"), assembled=False)
    instance_check("component.R16_fit", "R16", ("0R",), assembled=True)

    ptc_library = libraries.get(EXPECTED_PTC_LIB_ID)
    audit.add(
        "f1.ptc_1206_library_binding",
        "components",
        ptc_library is not None
        and ptc_library.properties.get("Footprint")
        == "Resistor_SMD:R_1206_3216Metric"
        and ptc_library.properties.get("ki_fp_filters") == "R?1206*",
        "F1 embedded local PTC symbol binds exactly to an R_1206-compatible filter",
        ptc_library.properties if ptc_library else None,
    )
    esd_library = libraries.get(EXPECTED_ESD_LIB_ID)
    observed_esd_pins = (
        {
            number: pin.name
            for number, pin in sorted(esd_library.pins.items())
        }
        if esd_library
        else {}
    )
    audit.add(
        "esd.usblc6_2sc6_flattened_binding",
        "components",
        esd_library is not None
        and esd_library.properties.get("Footprint")
        == "Package_TO_SOT_SMD:SOT-23-6"
        and esd_library.properties.get("ki_fp_filters") == "SOT?23*"
        and observed_esd_pins == EXPECTED_ESD_PIN_NAMES,
        "U8-U11 use the flattened KiCad USBLC6-2SC6 SOT-23 symbol and pin map",
        {
            "properties": esd_library.properties if esd_library else None,
            "expected_pins": EXPECTED_ESD_PIN_NAMES,
            "actual_pins": observed_esd_pins,
        },
    )

    assembled_legacy = sorted(
        item.ref
        for item in instances.values()
        if not item.dnp and item.in_bom and item.on_board
        and ("SN74LVC125" in item.value.upper() or "SN74LVC125" in item.lib_id.upper() or item.ref == "U12")
    )
    audit.add(
        "components.no_assembled_legacy_buffer",
        "components",
        not assembled_legacy,
        "no assembled SN74LVC125 or U12 remains",
        assembled_legacy,
    )

    u6 = instances.get("U6")
    audit.add(
        "u6.lib_id",
        "epd_bus_switch",
        u6 is not None and u6.lib_id == EXPECTED_U6_LIB_ID,
        "U6 uses the frozen SN74CB3Q3245PWR library symbol",
        u6.lib_id if u6 else None,
    )
    u6_library = libraries.get(EXPECTED_U6_LIB_ID)
    audit.add(
        "u6.library_embedded",
        "epd_bus_switch",
        u6_library is not None,
        "embedded U6 library definition is present",
        sorted(libraries) if u6_library is None else EXPECTED_U6_LIB_ID,
    )
    if u6_library is not None:
        lcsc = u6_library.properties.get("LCSC", "")
        value = u6_library.properties.get("Value", "")
        lcsc_ok = "C470961" in lcsc or "C470961" in value or (u6 and "C470961" in u6.value)
        audit.add(
            "u6.lcsc",
            "epd_bus_switch",
            bool(lcsc_ok),
            "U6 is bound to LCSC C470961",
            {"library_lcsc": lcsc, "library_value": value, "instance_value": u6.value if u6 else ""},
        )
        actual_pin_map = {
            number: normalize_pin_name(pin.name) for number, pin in u6_library.pins.items()
        }
        expected_pin_map = {
            number: normalize_pin_name(name) for number, name in U6_OFFICIAL_PIN_NAMES.items()
        }
        audit.add(
            "u6.official_pw_pin_names",
            "epd_bus_switch",
            actual_pin_map == expected_pin_map,
            "U6 embedded symbol matches TI PW/TSSOP-20 physical pin names",
            {"expected": expected_pin_map, "actual": actual_pin_map},
        )
        actual_types = {
            number: pin.electrical_type for number, pin in u6_library.pins.items()
        }
        audit.add(
            "u6.official_pin_types",
            "epd_bus_switch",
            actual_types == U6_OFFICIAL_PIN_TYPES,
            "U6 embedded symbol uses bidirectional A/B pins and correct power/OE/NC types",
            {"expected": U6_OFFICIAL_PIN_TYPES, "actual": actual_types},
        )

    # Freeze the TPS63070 dual-VOUT physical pad contract independently from
    # the per-pad net checks below.  This distinguishes the approved pin-8 ERC
    # modelling choice from a physical pin-number/name change.
    u4 = instances.get("U4")
    u4_library = libraries.get(EXPECTED_U4_LIB_ID)
    audit.add(
        "u4.lib_id",
        "tps63070",
        u4 is not None and u4.lib_id == EXPECTED_U4_LIB_ID,
        "U4 uses the frozen TPS63070RNMR library symbol",
        u4.lib_id if u4 else None,
    )
    audit.add(
        "u4.library_embedded",
        "tps63070",
        u4_library is not None,
        "embedded U4 library definition is present",
        sorted(libraries) if u4_library is None else EXPECTED_U4_LIB_ID,
    )
    if u4_library is not None:
        actual_u4_vout = {
            number: {
                "name": normalize_pin_name(u4_library.pins[number].name),
                "type": u4_library.pins[number].electrical_type,
            }
            for number in EXPECTED_U4_VOUT_PINS
            if number in u4_library.pins
        }
        expected_u4_vout = {
            number: {
                "name": normalize_pin_name(contract["name"]),
                "type": contract["type"],
            }
            for number, contract in EXPECTED_U4_VOUT_PINS.items()
        }
        audit.add(
            "u4.vout_physical_pin_contract",
            "tps63070",
            actual_u4_vout == expected_u4_vout,
            "U4 pins 7/8 are physical VOUT pads with approved ERC types",
            {"expected": expected_u4_vout, "actual": actual_u4_vout},
        )

    def pin_net_check(check_id: str, category: str, ref: str, pin: str, expected: str | None) -> None:
        actual = meaningful_pin_net(pin_to_net, ref, pin)
        audit.add(
            check_id,
            category,
            actual == expected,
            f"{ref}.{pin} is on {expected if expected is not None else 'NC'}",
            {"expected": expected, "actual": actual},
        )

    for pin, expected_net in U6_EXPECTED_NETS.items():
        pin_net_check(f"u6.net.pin_{pin}", "epd_bus_switch", "U6", pin, expected_net)
    for pin in U6_UNUSED_CHANNEL_PINS:
        pin_net_check(f"u6.unused.pin_{pin}", "epd_bus_switch", "U6", pin, None)
    for pin, net in {"1": "EPD_BUF_CONNECT", "2": "GND", "3": "EPD_BUF_OE_N"}.items():
        pin_net_check(f"u6.q3_pin_{pin}", "epd_bus_switch", "Q3", pin, net)
    if u6_library is not None:
        si0_types_ok = all(
            u6_library.pins.get(pin) is not None
            and u6_library.pins[pin].electrical_type == "bidirectional"
            for pin in ("7", "13")
        )
        audit.add(
            "u6.si0_bidirectional",
            "epd_bus_switch",
            si0_types_ok
            and meaningful_pin_net(pin_to_net, "U6", "7") == "MCU_SI0"
            and meaningful_pin_net(pin_to_net, "U6", "13") == "SI0",
            "SI0 readback crosses a bidirectional U6 A6/B6 channel",
            {"A6_pin": 7, "B6_pin": 13},
        )

    gpio_map = {
        "1": "GND", "2": "SYS_3V3", "3": "MCU_EN",
        "4": "MCU_BUSY_N", "5": "MCU_RST_N", "6": "MCU_DC", "7": "MCU_CSB",
        "8": "TF_SCLK", "9": "TF_MOSI", "10": "TF_MISO", "11": "TF_CS_N",
        "12": "USER_KEY_1_N", "13": "USB_D-", "14": "USB_D+",
        "17": "USER_KEY_2_N", "18": "MCU_CS2", "19": "MCU_SI0", "20": "MCU_SCL",
        "21": "EPD_PWR_EN", "22": "TF_CD_N", "23": "PWR_INT_N",
        "24": "USB_INPUT_VALID_N", "25": "EPD_FAULT_N", "27": "BOOT_N",
        "31": "EPD_BUF_CONNECT", "32": "JTAG_GPIO39", "33": "JTAG_GPIO40",
        "34": "JTAG_GPIO41", "35": "JTAG_GPIO42", "36": "UART0_RX",
        "37": "UART0_TX", "38": "PS_HOLD", "39": "BAT_ADC", "40": "GND", "41": "GND",
    }
    gpio_failures: dict[str, dict[str, str | None]] = {}
    for pin, expected in gpio_map.items():
        actual = meaningful_pin_net(pin_to_net, "U1", pin)
        if actual != expected:
            gpio_failures[pin] = {"expected": expected, "actual": actual}
    audit.add(
        "gpio.final_map",
        "esp32_gpio",
        not gpio_failures,
        "ESP32-S3-WROOM-1 final GPIO map matches the frozen allocation",
        gpio_failures,
    )
    forbidden_pins = {
        "15": "GPIO3 strap", "16": "GPIO46 strap", "26": "GPIO45 strap",
        "28": "GPIO35 Octal PSRAM", "29": "GPIO36 Octal PSRAM", "30": "GPIO37 Octal PSRAM",
    }
    forbidden_failures = {
        pin: {"reason": reason, "net": meaningful_pin_net(pin_to_net, "U1", pin)}
        for pin, reason in forbidden_pins.items()
        if meaningful_pin_net(pin_to_net, "U1", pin) is not None
    }
    audit.add(
        "gpio.forbidden_unconnected",
        "esp32_gpio",
        not forbidden_failures,
        "strap GPIO3/45/46 and N16R8 GPIO35-37 are not assigned",
        forbidden_failures,
    )

    def two_pin_check(
        check_id: str,
        category: str,
        ref: str,
        expected_nets: tuple[str, str],
        value_tokens: Sequence[str],
        *,
        dnp: bool | None = None,
        expected_footprint: str | None = None,
    ) -> None:
        item = instances.get(ref)
        nets = [meaningful_pin_net(pin_to_net, ref, "1"), meaningful_pin_net(pin_to_net, ref, "2")]
        expected = list(expected_nets)
        topology_ok = None not in nets and sorted(nets) == sorted(expected)
        value_ok = item is not None and has_tokens(item.value, value_tokens)
        population_ok = item is not None and (dnp is None or item.dnp == dnp)
        footprint_ok = item is not None and (
            expected_footprint is None or item.footprint == expected_footprint
        )
        ok = bool(item and topology_ok and value_ok and population_ok and footprint_ok)
        audit.add(
            check_id,
            category,
            ok,
            f"{ref} value/population/topology contract matches",
            {
                "expected_nets": expected,
                "actual_nets": nets,
                "value": item.value if item else None,
                "expected_footprint": expected_footprint,
                "actual_footprint": item.footprint if item else None,
                "dnp": item.dnp if item else None,
            },
        )

    # WROOM supply/reset/boot/key defaults and optional battery sensing.
    for args in (
        ("wroom.R27_en_pullup", "R27", ("SYS_3V3", "MCU_EN"), ("10k",), None),
        ("wroom.C48_en_delay", "C48", ("MCU_EN", "GND"), ("0.1uF",), None),
        ("wroom.C41_bulk", "C41", ("SYS_3V3", "GND"), ("10uF",), None),
        ("wroom.C42_local", "C42", ("SYS_3V3", "GND"), ("0.1uF",), None),
        ("wroom.R53_boot", "R53", ("SYS_3V3", "BOOT_N"), ("10k",), None),
        ("wroom.R51_user1", "R51", ("SYS_3V3", "USER_KEY_1_N"), ("10k",), None),
        ("wroom.R52_user2", "R52", ("SYS_3V3", "USER_KEY_2_N"), ("10k",), None),
        ("wroom.SW2_user1", "SW2", ("USER_KEY_1_N", "GND"), ("USER1",), None),
        ("wroom.SW3_user2", "SW3", ("USER_KEY_2_N", "GND"), ("USER2",), None),
        ("wroom.R49_bat_adc_optional", "R49", ("BAT_POS", "BAT_ADC"), ("220k", "DNP"), True),
        ("wroom.R50_bat_adc_bottom", "R50", ("BAT_ADC", "GND"), ("100k",), None),
        ("wroom.C49_bat_adc_filter", "C49", ("BAT_ADC", "GND"), ("0.1uF",), None),
    ):
        two_pin_check(args[0], "esp32_gpio", args[1], args[2], args[3], dnp=args[4])

    # B2 bridge population and the R4/R8 preserved power entry.
    two_pin_check("b2.R4", "b2_preservation", "R4", ("EPD_SW_3V3", "EPD_3V3"), ("0R",), dnp=False)
    two_pin_check("b2.R8", "b2_preservation", "R8", ("EPD_SW_3V3", "V_B"), ("0R",), dnp=False)
    two_pin_check("b2.R15", "b2_preservation", "R15", ("CSB", "SL_CSB"), ("0R", "DNP"), dnp=True)
    two_pin_check("b2.R16", "b2_preservation", "R16", ("CS2", "SL_CSB"), ("0R",), dnp=False)

    # BQ24074 PowerPath and charger programming.
    bq_nets = {
        "1": "BAT_NTC", "2": "BAT_POS", "3": "BAT_POS", "4": "GND",
        "5": "GND", "6": "USB_5V_FUSED", "7": "USB_INPUT_VALID_N",
        "8": "GND", "9": "BQ_CHG_N", "10": "VSYS_RAW", "11": "VSYS_RAW",
        "12": "BQ_ILIM", "13": "USB_5V_FUSED", "14": "BQ_TMR",
        "16": "BQ_ISET", "17": "GND",
    }
    for pin, net in bq_nets.items():
        pin_net_check(f"bq.pin_{pin}", "bq24074", "U2", pin, net)
    pin_net_check("bq.iterm_nc", "bq24074", "U2", "15", None)
    for args in (
        ("bq.R21_iset", "R21", ("BQ_ISET", "GND"), ("1.78k",)),
        ("bq.R22_ilim", "R22", ("BQ_ILIM", "GND"), ("3.16k",)),
        ("bq.R24_tmr", "R24", ("BQ_TMR", "GND"), ("46.4k",)),
        ("bq.R25_pgood", "R25", ("SYS_3V3", "USB_INPUT_VALID_N"), ("100k",)),
        ("bq.R26_chg", "R26", ("SYS_3V3", "BQ_CHG_N"), ("100k",)),
        ("bq.C25_in", "C25", ("USB_5V_FUSED", "GND"), ("1uF",)),
        ("bq.C26_bat", "C26", ("BAT_POS", "GND"), ("10uF",)),
        ("bq.C27_out", "C27", ("VSYS_RAW", "GND"), ("10uF",)),
    ):
        two_pin_check(args[0], "bq24074", args[1], args[2], args[3])
    for pin, net in {"1": "BAT_POS", "2": "GND", "3": "BAT_NTC"}.items():
        pin_net_check(f"battery.pin_{pin}", "bq24074", "J6", pin, net)

    # STM6600 single-button contract and default-off handoff.
    stm_nets = {
        "1": "VSYS_RAW", "2": "PWR_BUTTON_N", "3": "STM_VREF",
        "4": "PS_HOLD", "5": "STM_CSRD", "6": "PWR_BUTTON_N",
        "9": "DCDC_EN", "10": "MCU_EN", "11": "PWR_INT_N", "12": "GND",
    }
    for pin, net in stm_nets.items():
        pin_net_check(f"stm.pin_{pin}", "stm6600", "U3", pin, net)
    # STM6600 pin 7 (VCCLO) and pin 8 (PB_OUT) are deliberately unused in the
    # frozen single-button topology.  Keep both explicit NC rather than naming
    # otherwise floating nets, so accidental loads cannot evade this contract.
    pin_net_check("stm.vcclo_nc", "stm6600", "U3", "7", None)
    pin_net_check("stm.pbout_nc", "stm6600", "U3", "8", None)
    for args in (
        ("stm.C28_vcc", "C28", ("VSYS_RAW", "GND"), ("0.1uF",)),
        ("stm.C29_vref", "C29", ("STM_VREF", "GND"), ("1uF",)),
        ("stm.C30_csrd", "C30", ("STM_CSRD", "GND"), ("1uF",)),
        ("stm.R28_int", "R28", ("SYS_3V3", "PWR_INT_N"), ("10k",)),
        ("stm.R60_pshold", "R60", ("PS_HOLD", "GND"), ("100k",)),
        ("stm.R61_dcdc_en", "R61", ("DCDC_EN", "GND"), ("100k",)),
        ("stm.SW1_single_key", "SW1", ("PWR_BUTTON_N", "GND"), ("POWER",)),
    ):
        two_pin_check(args[0], "stm6600", args[1], args[2], args[3])

    # TPS63070 3.3-V converter.
    tps63070_nets = {
        "1": "DCDC_PS_SYNC", "2": "DCDC_PG", "3": "DCDC_VAUX", "4": "GND",
        "5": "DCDC_FB", "7": "SYS_3V3", "8": "SYS_3V3", "9": "DCDC_L2",
        "10": "GND", "11": "DCDC_L1", "12": "VSYS_RAW", "13": "VSYS_RAW",
        "14": "DCDC_EN", "15": "GND",
    }
    for pin, net in tps63070_nets.items():
        pin_net_check(f"tps63070.pin_{pin}", "tps63070", "U4", pin, net)
    pin_net_check("tps63070.fb2_nc", "tps63070", "U4", "6", None)
    two_pin_check(
        "tps63070.R29_pssync",
        "tps63070",
        "R29",
        ("VSYS_RAW", "DCDC_PS_SYNC"),
        ("10k",),
        expected_footprint="Resistor_SMD:R_0603_1608Metric",
    )
    converter_parts = [
        ("tps63070.L3", "L3", ("DCDC_L1", "DCDC_L2"), ("1.5uH", "4.5A")),
        ("tps63070.R30_pg", "R30", ("SYS_3V3", "DCDC_PG"), ("100k",)),
        ("tps63070.R31_fb_top", "R31", ("SYS_3V3", "DCDC_FB"), ("470k",)),
        ("tps63070.R32_fb_bottom", "R32", ("DCDC_FB", "GND"), ("150k",)),
        ("tps63070.C38_vaux", "C38", ("DCDC_VAUX", "GND"), ("0.1uF",)),
    ]
    converter_parts += [
        (f"tps63070.{ref.lower()}", ref, ("VSYS_RAW", "GND"), ("10uF",))
        for ref in ("C31", "C32", "C33")
    ]
    converter_parts += [
        (f"tps63070.{ref.lower()}", ref, ("SYS_3V3", "GND"), ("22uF",))
        for ref in ("C34", "C35", "C36")
    ]
    converter_parts.append(("tps63070.c37", "C37", ("SYS_3V3", "GND"), ("10uF",)))
    for args in converter_parts:
        two_pin_check(args[0], "tps63070", args[1], args[2], args[3])
    two_pin_check(
        "tps63070.c46_vin_local_hf",
        "tps63070",
        "C46",
        ("VSYS_RAW", "GND"),
        ("10uF", "local HF", "TI 11.1"),
        expected_footprint="Capacitor_SMD:C_0603_1608Metric",
    )
    two_pin_check(
        "tps63070.c47_vout_local_hf",
        "tps63070",
        "C47",
        ("SYS_3V3", "GND"),
        ("10uF", "local HF", "TI 11.1"),
        expected_footprint="Capacitor_SMD:C_0603_1608Metric",
    )

    # TPS22950 EPD load switch and deterministic reset defaults.
    tps22950_nets = {
        "1": "EPD_PWR_EN", "2": "SYS_3V3", "3": "GND",
        "4": "EPD_ILIM", "5": "EPD_SW_3V3", "6": "EPD_FAULT_N",
    }
    for pin, net in tps22950_nets.items():
        pin_net_check(f"tps22950.pin_{pin}", "tps22950", "U5", pin, net)
    for args in (
        ("tps22950.R33_ilim", "R33", ("EPD_ILIM", "GND"), ("1.50k",)),
        ("tps22950.R34_fault", "R34", ("SYS_3V3", "EPD_FAULT_N"), ("10k",)),
        ("tps22950.R35_on_default", "R35", ("EPD_PWR_EN", "GND"), ("100k",)),
        ("tps22950.C39_vin", "C39", ("SYS_3V3", "GND"), ("1uF",)),
        ("tps22950.C40_vout", "C40", ("EPD_SW_3V3", "GND"), ("10uF",)),
        ("u6.R36_oe_pullup", "R36", ("EPD_3V3", "EPD_BUF_OE_N"), ("10k",)),
        ("u6.C45_decoupling", "C45", ("EPD_3V3", "GND"), ("0.1uF",)),
        ("u6.R62_busy_idle", "R62", ("SYS_3V3", "MCU_BUSY_N"), ("100k",)),
        ("u6.R63_gate_default", "R63", ("EPD_BUF_CONNECT", "GND"), ("100k",)),
    ):
        two_pin_check(args[0], "tps22950", args[1], args[2], args[3])

    # These pulls must be on the panel side of an isolated U6.  MCU-side-only
    # pulls do not protect an energized panel while ESP32 is in reset.
    safe_defaults = (
        ("defaults.R54_csb", "R54", ("EPD_3V3", "CSB"), ("100k",)),
        ("defaults.R55_cs2", "R55", ("EPD_3V3", "CS2"), ("100k",)),
        ("defaults.R56_rst", "R56", ("RST_N", "GND"), ("100k",)),
        ("defaults.R57_dc", "R57", ("DC", "GND"), ("100k",)),
        ("defaults.R58_scl", "R58", ("SCL", "GND"), ("100k",)),
        ("defaults.R59_si0", "R59", ("SI0", "GND"), ("100k",)),
    )
    for args in safe_defaults:
        two_pin_check(args[0], "reset_defaults", args[1], args[2], args[3])

    # USB-C sink, native USB, protection, and series termination.
    usb_connector_nets = {
        "A1": "GND", "A4": "USB_VBUS", "A5": "USB_CC1",
        "A6": "USB_DP_CONN", "A7": "USB_DN_CONN", "A9": "USB_VBUS", "A12": "GND",
        "B1": "GND", "B4": "USB_VBUS", "B5": "USB_CC2",
        "B6": "USB_DP_CONN", "B7": "USB_DN_CONN", "B9": "USB_VBUS", "B12": "GND",
    }
    for pin, net in usb_connector_nets.items():
        pin_net_check(f"usb.j5_{pin}", "usb", "J5", pin, net)
    pin_net_check("usb.sbu1_nc", "usb", "J5", "A8", None)
    pin_net_check("usb.sbu2_nc", "usb", "J5", "B8", None)
    for args in (
        ("usb.R17_cc1", "R17", ("USB_CC1", "GND"), ("5.1k", "1%")),
        ("usb.R18_cc2", "R18", ("USB_CC2", "GND"), ("5.1k", "1%")),
        ("usb.R19_dn", "R19", ("USB_DN_ESD", "USB_D-"), ("22R",)),
        ("usb.R20_dp", "R20", ("USB_DP_ESD", "USB_D+"), ("22R",)),
        ("usb.F1", "F1", ("USB_VBUS", "USB_5V_FUSED"), ("750mA", "C883128")),
        ("usb.D5_tvs", "D5", ("USB_5V_FUSED", "GND"), ("SMF5.0A", "C908213")),
        ("usb.C24", "C24", ("USB_5V_FUSED", "GND"), ("1uF",)),
    ):
        two_pin_check(args[0], "usb", args[1], args[2], args[3])
    usb_esd_nets = {"1": "USB_DN_CONN", "2": "GND", "3": "USB_DP_CONN", "4": "USB_DP_ESD", "5": "USB_5V_FUSED", "6": "USB_DN_ESD"}
    for pin, net in usb_esd_nets.items():
        pin_net_check(f"usb.u8_{pin}", "usb", "U8", pin, net)

    # microSD SPI, mandatory card-side pulls, series resistors, and all six
    # exposed signal contacts covered by three dual USBLC6 arrays.
    sd_nets = {
        "1": "TF_DAT2_CARD", "2": "TF_DAT3_CARD", "3": "TF_CMD_CARD",
        "4": "SYS_3V3", "5": "TF_CLK_CARD", "6": "GND",
        "7": "TF_DAT0_CARD", "8": "TF_DAT1_CARD", "9": "TF_CD_N",
        "10": "GND", "SH": "GND",
    }
    for pin, net in sd_nets.items():
        pin_net_check(f"tf.j4_{pin}", "microSD", "J4", pin, net)
    pullups = {
        "R39": "TF_DAT2_CARD", "R40": "TF_DAT3_CARD", "R41": "TF_CMD_CARD",
        "R42": "TF_DAT0_CARD", "R43": "TF_DAT1_CARD",
    }
    for ref, net in pullups.items():
        two_pin_check(f"tf.{ref.lower()}_pullup", "microSD", ref, ("SYS_3V3", net), ("10k",))
    two_pin_check("tf.R44_cd_pullup", "microSD", "R44", ("SYS_3V3", "TF_CD_N"), ("10k",))
    for check_id, ref, nets in (
        ("tf.R45_clk", "R45", ("TF_SCLK", "TF_CLK_ESD")),
        ("tf.R46_cmd", "R46", ("TF_MOSI", "TF_CMD_ESD")),
        ("tf.R47_dat0", "R47", ("TF_MISO", "TF_DAT0_ESD")),
        ("tf.R48_dat3", "R48", ("TF_CS_N", "TF_DAT3_ESD")),
    ):
        two_pin_check(check_id, "microSD", ref, nets, ("22R",))
    tf_esd = {
        "U9": {"1": "TF_CLK_CARD", "2": "GND", "3": "TF_CMD_CARD", "4": "TF_CMD_ESD", "5": "SYS_3V3", "6": "TF_CLK_ESD"},
        "U10": {"1": "TF_DAT0_CARD", "2": "GND", "3": "TF_DAT3_CARD", "4": "TF_DAT3_ESD", "5": "SYS_3V3", "6": "TF_DAT0_ESD"},
        # DAT1/DAT2 are unused in SPI mode.  Their card contacts still receive
        # mandatory pull-ups and ESD clamps through U11 pins 1/3, while the
        # corresponding board-side flow-through pins 6/4 remain explicit NC.
        "U11": {"1": "TF_DAT1_CARD", "2": "GND", "3": "TF_DAT2_CARD", "4": None, "5": "SYS_3V3", "6": None},
    }
    for ref, mapping in tf_esd.items():
        for pin, net in mapping.items():
            pin_net_check(f"tf.{ref.lower()}_{pin}", "microSD", ref, pin, net)

    categories: dict[str, dict[str, int]] = {}
    for check in audit.checks:
        counts = categories.setdefault(check.category, {"pass": 0, "fail": 0})
        counts["pass" if check.passed else "fail"] += 1
    passed_count = sum(check.passed for check in audit.checks)
    failed_count = len(audit.checks) - passed_count
    return {
        "schema": 1,
        "tool": "verify_mf1750_wroom_b3_schematic.py",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input": {
            "path": str(schematic),
            "bytes": schematic.stat().st_size,
            "sha256": sha256_file(schematic),
        },
        "kicad_netlist_export": netlist_evidence,
        "frozen_b2_sha256": observed_b2,
        "result": "PASS" if audit.passed else "FAIL",
        "passed": audit.passed,
        "summary": {
            "total": len(audit.checks),
            "passed": passed_count,
            "failed": failed_count,
            "categories": categories,
        },
        "checks": [check.as_dict() for check in audit.checks],
        "hardware_accessed": False,
        "schematic_modified": False,
    }


def failure_report(schematic: Path, message: str, *, check_id: str = "verifier.internal") -> dict[str, object]:
    return {
        "schema": 1,
        "tool": "verify_mf1750_wroom_b3_schematic.py",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input": {"path": str(schematic)},
        "result": "FAIL",
        "passed": False,
        "summary": {"total": 1, "passed": 0, "failed": 1},
        "checks": [
            {
                "id": check_id,
                "category": "verifier",
                "status": "FAIL",
                "message": message,
            }
        ],
        "hardware_accessed": False,
        "schematic_modified": False,
    }


def write_report(report: dict[str, object], output: Path | None) -> None:
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    sys.stdout.write(rendered)
    if output is not None:
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(rendered, encoding="utf-8", newline="\n")
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed static verifier for MF1750 WROOM B3 KiCad schematic"
    )
    parser.add_argument(
        "schematic",
        nargs="?",
        type=Path,
        default=DEFAULT_SCHEMATIC,
        help=f"candidate .kicad_sch (default: {DEFAULT_SCHEMATIC})",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="also write the JSON report atomically to this path",
    )
    parser.add_argument(
        "--kicad-cli",
        type=Path,
        help="explicit kicad-cli executable path",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    schematic = args.schematic.resolve()
    report: dict[str, object]
    try:
        if schematic.suffix.casefold() != ".kicad_sch":
            raise RuntimeError("candidate path must end in .kicad_sch")
        if not schematic.is_file():
            raise RuntimeError(f"candidate schematic is missing: {schematic}")
        if schematic.stat().st_size > 50 * 1024 * 1024:
            raise RuntimeError("candidate schematic exceeds the 50 MiB verifier limit")
        source_text = schematic.read_text(encoding="utf-8", errors="strict")
        source_root = parse_sexpr(source_text)
        if head(source_root) != "kicad_sch":
            raise RuntimeError(f"candidate root is {head(source_root)!r}, expected 'kicad_sch'")
        kicad_cli = resolve_kicad_cli(args.kicad_cli)
        if kicad_cli is None:
            raise RuntimeError("kicad-cli was not found; connectivity cannot be proven")
        netlist_root, netlist_evidence = export_netlist(kicad_cli, schematic)
        if head(netlist_root) != "export":
            raise RuntimeError(f"netlist root is {head(netlist_root)!r}, expected 'export'")
        report = audit_schematic(schematic, source_root, netlist_root, netlist_evidence)
    except Exception as exc:  # fail closed and still return machine-readable JSON
        report = failure_report(schematic, f"{type(exc).__name__}: {exc}")
    write_report(report, args.json_report)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
