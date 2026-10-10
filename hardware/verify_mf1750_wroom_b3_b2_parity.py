#!/usr/bin/env python3
"""Strict, read-only B2 -> B3 frozen-driver schematic parity verifier.

The checker exports the immutable MF1750 B2 schematic and a B3 candidate with
KiCad 10 in ``kicadxml`` netlist format, parses both XML documents, and compares
the frozen driver references pin by pin.  It deliberately does not import the
B3 schematic builder or trust labels found only in the source text.

The only accepted differences are enumerated below: J2 is outside the frozen
reference set because its architecture migrates in B3, the old 3V3 interface
may be renamed to one of the two explicit EPD power domains, and seven control
nets may acquire their explicit MCU-side names across U6.  No wildcard or
prefix-based net-name relaxation is used.

The schematics and hardware are never modified or accessed.  A JSON report is
printed to stdout; any missing evidence or mismatch returns a non-zero status.
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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
DEFAULT_B2 = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_sch"
)
DEFAULT_B3 = (
    HARDWARE
    / "mf1750_wroom_b3_power_tf"
    / "staging"
    / "mf1750_wroom_b3_power_tf_r3_schematic.kicad_sch"
)

B2_FROZEN_SHA256 = "bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb"

FROZEN_REFS = tuple(
    [*(f"C{index}" for index in range(24))]
    + [*(f"D{index}" for index in range(1, 5))]
    + ["J1"]
    + ["L1", "L2"]
    + ["Q1", "Q2"]
    + [*(f"R{index}" for index in range(1, 17))]
    + [*(f"TP{index}" for index in range(1, 11))]
)

# These reference gaps are part of the SHA-256-bound B2 baseline.  They are
# checked explicitly so a new B3 part cannot silently occupy a frozen ref.
KNOWN_ABSENT_REFS = frozenset({"R11", "R14"})

# Exact, one-way migrations from the B2 names.  Identity is always accepted.
POWER_NET_TRANSITIONS = {
    "3V3": frozenset({"EPD_SW_3V3", "EPD_3V3"}),
}
CONTROL_NET_TRANSITIONS = {
    "RST_N": "MCU_RST_N",
    "DC": "MCU_DC",
    "CSB": "MCU_CSB",
    "CS2": "MCU_CS2",
    "SCL": "MCU_SCL",
    "SI0": "MCU_SI0",
    "BUSY_N": "MCU_BUSY_N",
}


@dataclass(frozen=True)
class Node:
    net: str | None
    pin_function: str
    pin_type: str


@dataclass(frozen=True)
class Component:
    ref: str
    value: str
    footprint: str
    library: str
    part: str
    dnp: bool
    declared_pins: frozenset[str]


@dataclass(frozen=True)
class Netlist:
    path: Path
    source: str
    tool: str
    components: dict[str, Component]
    nodes: dict[tuple[str, str], Node]


@dataclass
class Audit:
    checks: list[dict[str, object]] = field(default_factory=list)
    allowed_counts: dict[str, int] = field(
        default_factory=lambda: {
            "identity": 0,
            "power_domain": 0,
            "u6_control_side": 0,
            "tp1_value_power_domain": 0,
        }
    )

    def add(
        self,
        check_id: str,
        category: str,
        passed: bool,
        message: str,
        evidence: object | None = None,
    ) -> None:
        entry: dict[str, object] = {
            "id": check_id,
            "category": category,
            "status": "PASS" if passed else "FAIL",
            "message": message,
        }
        if evidence is not None:
            entry["evidence"] = evidence
        self.checks.append(entry)

    def summary(self) -> dict[str, object]:
        categories: dict[str, dict[str, int]] = {}
        for check in self.checks:
            counts = categories.setdefault(str(check["category"]), {"pass": 0, "fail": 0})
            counts["pass" if check["status"] == "PASS" else "fail"] += 1
        failed = sum(check["status"] == "FAIL" for check in self.checks)
        return {
            "total": len(self.checks),
            "passed": len(self.checks) - failed,
            "failed": failed,
            "categories": categories,
            "accepted_transition_counts": dict(self.allowed_counts),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_net(name: str | None) -> str | None:
    if name is None:
        return None
    # KiCad XML prefixes root-sheet labels with exactly one slash.  Remove only
    # root-sheet path separators; never case-fold or fuzzy-match net names.
    normalized = name.lstrip("/")
    return normalized or None


def parse_xml_netlist(path: Path) -> Netlist:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"XML netlist is missing or empty: {path}")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise RuntimeError(f"XML netlist exceeds the 50 MiB verifier limit: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise RuntimeError(f"malformed KiCad XML netlist {path}: {exc}") from exc
    if root.tag != "export":
        raise RuntimeError(f"unexpected XML root {root.tag!r}; expected 'export'")

    source = root.findtext("./design/source", default="")
    tool = root.findtext("./design/tool", default="")
    components: dict[str, Component] = {}
    for element in root.findall("./components/comp"):
        ref = element.get("ref", "")
        if not ref:
            raise RuntimeError("component without a reference in XML netlist")
        if ref in components:
            raise RuntimeError(f"duplicate component reference in XML netlist: {ref}")
        libsource = element.find("libsource")
        properties = {
            item.get("name", "").casefold()
            for item in element.findall("property")
            if item.get("name")
        }
        declared_pins = frozenset(
            pin.get("num", "")
            for pin in element.findall("./units/unit/pins/pin")
            if pin.get("num")
        )
        components[ref] = Component(
            ref=ref,
            value=element.findtext("value", default=""),
            footprint=element.findtext("footprint", default=""),
            library="" if libsource is None else libsource.get("lib", ""),
            part="" if libsource is None else libsource.get("part", ""),
            dnp="dnp" in properties,
            declared_pins=declared_pins,
        )

    nodes: dict[tuple[str, str], Node] = {}
    for net in root.findall("./nets/net"):
        net_name = canonical_net(net.get("name"))
        for element in net.findall("node"):
            ref = element.get("ref", "")
            pin = element.get("pin", "")
            if not ref or not pin:
                raise RuntimeError("net node without ref/pin in XML netlist")
            key = (ref, pin)
            if key in nodes:
                raise RuntimeError(f"pin {ref}.{pin} occurs on more than one net")
            nodes[key] = Node(
                net=net_name,
                pin_function=element.get("pinfunction", ""),
                pin_type=element.get("pintype", ""),
            )

    # Every declared physical pin must have an exported connectivity record,
    # including KiCad's explicit unconnected pseudo-nets.
    for component in components.values():
        missing = sorted(
            pin for pin in component.declared_pins if (component.ref, pin) not in nodes
        )
        if missing:
            raise RuntimeError(
                f"component {component.ref} has declared pins absent from nets: {missing}"
            )
    return Netlist(
        path=path,
        source=source,
        tool=tool,
        components=components,
        nodes=nodes,
    )


def resolve_kicad_cli(requested: Path | None) -> Path | None:
    if requested is not None:
        return requested.resolve() if requested.is_file() else None
    located = shutil.which("kicad-cli")
    if located:
        return Path(located).resolve()
    candidates = (
        Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
        Path("/usr/bin/kicad-cli"),
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def kicad_version(kicad_cli: Path) -> dict[str, object]:
    completed = subprocess.run(
        [str(kicad_cli), "--version"],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    version = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0:
        raise RuntimeError(f"kicad-cli --version failed: {version or 'no diagnostic'}")
    major = version.split(".", 1)[0]
    if major != "10":
        raise RuntimeError(f"KiCad 10 is required for parity evidence; found {version!r}")
    return {"path": str(kicad_cli), "version": version, "major": 10}


def export_netlist(
    kicad_cli: Path,
    schematic: Path,
    output: Path,
) -> dict[str, object]:
    command = [
        str(kicad_cli),
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "--output",
        str(output),
        str(schematic),
    ]
    completed = subprocess.run(
        command,
        cwd=output.parent,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    evidence: dict[str, object] = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.returncode != 0:
        raise RuntimeError(
            f"KiCad XML netlist export failed for {schematic}: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"KiCad returned success without XML output for {schematic}")
    evidence["bytes"] = output.stat().st_size
    evidence["sha256"] = sha256_file(output)
    return evidence


def net_transition(b2: str | None, b3: str | None) -> tuple[bool, str]:
    if b2 == b3:
        return True, "identity"
    if b2 in POWER_NET_TRANSITIONS and b3 in POWER_NET_TRANSITIONS[b2]:
        return True, "power_domain"
    if b2 in CONTROL_NET_TRANSITIONS and b3 == CONTROL_NET_TRANSITIONS[b2]:
        return True, "u6_control_side"
    return False, "forbidden"


def value_transition(ref: str, b2: str, b3: str) -> tuple[bool, str]:
    if b2 == b3:
        return True, "identity"
    if ref == "TP1" and b2 == "3V3" and b3 in POWER_NET_TRANSITIONS["3V3"]:
        return True, "tp1_value_power_domain"
    return False, "forbidden"


def node_for(netlist: Netlist, ref: str, pin: str) -> Node:
    try:
        return netlist.nodes[(ref, pin)]
    except KeyError as exc:
        raise RuntimeError(f"missing exported node for {ref}.{pin} in {netlist.path}") from exc


def audit_parity(
    b2_path: Path,
    b3_path: Path,
    b2: Netlist,
    b3: Netlist,
    cli_evidence: dict[str, object],
    export_evidence: dict[str, object],
) -> dict[str, object]:
    audit = Audit()
    b2_hash = sha256_file(b2_path)
    audit.add(
        "baseline.b2_sha256",
        "provenance",
        b2_hash == B2_FROZEN_SHA256,
        "frozen B2 schematic SHA-256 matches" if b2_hash == B2_FROZEN_SHA256 else "frozen B2 schematic SHA-256 mismatch",
        {"expected": B2_FROZEN_SHA256, "actual": b2_hash},
    )
    audit.add(
        "tool.kicad10",
        "provenance",
        cli_evidence.get("major") == 10,
        "netlists were exported with KiCad 10",
        cli_evidence,
    )
    audit.add(
        "scope.explicit_refs",
        "scope",
        len(FROZEN_REFS) == len(set(FROZEN_REFS)) == 59,
        "frozen reference scope contains 59 unique explicit refs",
        {"refs": list(FROZEN_REFS), "known_absent_in_b2": sorted(KNOWN_ABSENT_REFS)},
    )

    for ref in FROZEN_REFS:
        b2_component = b2.components.get(ref)
        b3_component = b3.components.get(ref)
        if ref in KNOWN_ABSENT_REFS:
            passed = b2_component is None and b3_component is None
            audit.add(
                f"ref.{ref}.preserved_absence",
                "presence",
                passed,
                f"{ref} remains absent as frozen in B2" if passed else f"{ref} violates frozen absent-reference gap",
                {"b2_present": b2_component is not None, "b3_present": b3_component is not None},
            )
            continue

        present = b2_component is not None and b3_component is not None
        audit.add(
            f"ref.{ref}.presence",
            "presence",
            present,
            f"{ref} exists in both B2 and B3" if present else f"{ref} missing from B2 or B3",
            {"b2_present": b2_component is not None, "b3_present": b3_component is not None},
        )
        if not present:
            continue
        assert b2_component is not None and b3_component is not None

        value_ok, value_rule = value_transition(ref, b2_component.value, b3_component.value)
        if value_ok:
            audit.allowed_counts[value_rule] += 1
        audit.add(
            f"ref.{ref}.value",
            "attributes",
            value_ok,
            f"{ref} value matches frozen B2 under {value_rule} rule" if value_ok else f"{ref} value changed without an explicit allowance",
            {"b2": b2_component.value, "b3": b3_component.value, "rule": value_rule},
        )
        audit.add(
            f"ref.{ref}.footprint",
            "attributes",
            b2_component.footprint == b3_component.footprint,
            f"{ref} footprint is unchanged" if b2_component.footprint == b3_component.footprint else f"{ref} footprint changed",
            {"b2": b2_component.footprint, "b3": b3_component.footprint},
        )
        library_same = (
            b2_component.library == b3_component.library
            and b2_component.part == b3_component.part
        )
        audit.add(
            f"ref.{ref}.symbol_identity",
            "attributes",
            library_same,
            f"{ref} symbol library/part is unchanged" if library_same else f"{ref} symbol library/part changed",
            {
                "b2": {"library": b2_component.library, "part": b2_component.part},
                "b3": {"library": b3_component.library, "part": b3_component.part},
            },
        )
        audit.add(
            f"ref.{ref}.dnp",
            "attributes",
            b2_component.dnp == b3_component.dnp,
            f"{ref} DNP population state is unchanged" if b2_component.dnp == b3_component.dnp else f"{ref} DNP population state changed",
            {"b2": b2_component.dnp, "b3": b3_component.dnp},
        )

        pins_same = b2_component.declared_pins == b3_component.declared_pins
        audit.add(
            f"ref.{ref}.pin_set",
            "pin_contract",
            pins_same,
            f"{ref} physical pin set is unchanged" if pins_same else f"{ref} physical pin set changed",
            {
                "b2": sorted(b2_component.declared_pins),
                "b3": sorted(b3_component.declared_pins),
                "removed": sorted(b2_component.declared_pins - b3_component.declared_pins),
                "added": sorted(b3_component.declared_pins - b2_component.declared_pins),
            },
        )

        for pin in sorted(b2_component.declared_pins | b3_component.declared_pins):
            if pin not in b2_component.declared_pins or pin not in b3_component.declared_pins:
                continue
            b2_node = node_for(b2, ref, pin)
            b3_node = node_for(b3, ref, pin)
            metadata_same = (
                b2_node.pin_function == b3_node.pin_function
                and b2_node.pin_type == b3_node.pin_type
            )
            audit.add(
                f"pin.{ref}.{pin}.identity",
                "pin_contract",
                metadata_same,
                f"{ref}.{pin} function/type is unchanged" if metadata_same else f"{ref}.{pin} function/type changed",
                {
                    "b2": {"function": b2_node.pin_function, "type": b2_node.pin_type},
                    "b3": {"function": b3_node.pin_function, "type": b3_node.pin_type},
                },
            )
            net_ok, net_rule = net_transition(b2_node.net, b3_node.net)
            if net_ok:
                audit.allowed_counts[net_rule] += 1
            audit.add(
                f"pin.{ref}.{pin}.net",
                "connectivity",
                net_ok,
                f"{ref}.{pin} connectivity matches under {net_rule} rule" if net_ok else f"{ref}.{pin} connectivity changed without an explicit allowance",
                {"b2": b2_node.net, "b3": b3_node.net, "rule": net_rule},
            )

    summary = audit.summary()
    passed = summary["failed"] == 0
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "REVIEW_ONLY",
        "inputs": {
            "frozen_b2": {
                "path": str(b2_path),
                "bytes": b2_path.stat().st_size,
                "sha256": sha256_file(b2_path),
                "netlist_source": b2.source,
                "netlist_tool": b2.tool,
            },
            "candidate_b3": {
                "path": str(b3_path),
                "bytes": b3_path.stat().st_size,
                "sha256": sha256_file(b3_path),
                "netlist_source": b3.source,
                "netlist_tool": b3.tool,
            },
        },
        "kicad": cli_evidence,
        "exports": export_evidence,
        "allowed_difference_policy": {
            "j2": "J2 architecture is explicitly outside the frozen reference set",
            "power_net_transitions": {
                source: sorted(targets) for source, targets in POWER_NET_TRANSITIONS.items()
            },
            "control_net_transitions": dict(CONTROL_NET_TRANSITIONS),
            "identity_always_allowed": True,
            "all_other_value_footprint_symbol_pin_or_net_changes": "FAIL",
        },
        "result": "PASS" if passed else "FAIL",
        "passed": passed,
        "summary": summary,
        "checks": audit.checks,
        "hardware_accessed": False,
        "schematics_modified": False,
    }


def failure_report(b2: Path, b3: Path, message: str) -> dict[str, object]:
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "REVIEW_ONLY",
        "inputs": {"frozen_b2": str(b2), "candidate_b3": str(b3)},
        "result": "FAIL",
        "passed": False,
        "summary": {"total": 1, "passed": 0, "failed": 1},
        "checks": [
            {
                "id": "verifier.internal",
                "category": "verifier",
                "status": "FAIL",
                "message": message,
            }
        ],
        "hardware_accessed": False,
        "schematics_modified": False,
    }


def write_report(report: dict[str, object], output: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    sys.stdout.write(rendered)
    if output is None:
        return
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
        description="Strict B2 -> B3 frozen-driver parity verifier using KiCad 10 XML netlists"
    )
    parser.add_argument(
        "b3_schematic",
        nargs="?",
        type=Path,
        default=DEFAULT_B3,
        help=f"B3 candidate .kicad_sch (default: {DEFAULT_B3})",
    )
    parser.add_argument(
        "--b2",
        type=Path,
        default=DEFAULT_B2,
        help=f"SHA-256-bound frozen B2 schematic (default: {DEFAULT_B2})",
    )
    parser.add_argument("--json-report", type=Path, help="also atomically write JSON here")
    parser.add_argument("--kicad-cli", type=Path, help="explicit KiCad 10 kicad-cli path")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    b2_path = args.b2.resolve()
    b3_path = args.b3_schematic.resolve()
    report: dict[str, object]
    try:
        for label, path in (("B2", b2_path), ("B3", b3_path)):
            if path.suffix.casefold() != ".kicad_sch":
                raise RuntimeError(f"{label} path must end in .kicad_sch: {path}")
            if not path.is_file():
                raise RuntimeError(f"{label} schematic is missing: {path}")
            if path.stat().st_size > 50 * 1024 * 1024:
                raise RuntimeError(f"{label} schematic exceeds the 50 MiB limit: {path}")
        # Refuse to use a substituted baseline before invoking KiCad.
        actual_b2_hash = sha256_file(b2_path)
        if actual_b2_hash != B2_FROZEN_SHA256:
            raise RuntimeError(
                f"B2 SHA-256 mismatch: expected {B2_FROZEN_SHA256}, got {actual_b2_hash}"
            )
        kicad_cli = resolve_kicad_cli(args.kicad_cli)
        if kicad_cli is None:
            raise RuntimeError("KiCad 10 kicad-cli was not found")
        cli_evidence = kicad_version(kicad_cli)
        with tempfile.TemporaryDirectory(prefix="mf1750-b2-b3-parity-") as temp_name:
            temp_dir = Path(temp_name)
            b2_xml = temp_dir / "frozen_b2.xml"
            b3_xml = temp_dir / "candidate_b3.xml"
            export_evidence = {
                "frozen_b2": export_netlist(kicad_cli, b2_path, b2_xml),
                "candidate_b3": export_netlist(kicad_cli, b3_path, b3_xml),
            }
            b2 = parse_xml_netlist(b2_xml)
            b3 = parse_xml_netlist(b3_xml)
            report = audit_parity(
                b2_path,
                b3_path,
                b2,
                b3,
                cli_evidence,
                export_evidence,
            )
    except Exception as exc:  # fail closed, while retaining machine-readable output
        report = failure_report(b2_path, b3_path, f"{type(exc).__name__}: {exc}")
    write_report(report, args.json_report)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
