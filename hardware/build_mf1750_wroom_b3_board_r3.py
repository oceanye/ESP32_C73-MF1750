#!/usr/bin/env python3
"""Build the MF1750 WROOM B3 R3 *placed, not routed* PCB staging file.

This is a fail-closed schematic-to-board synchronization foundation.  It:

* exports a KiCad 10 ``kicadxml`` netlist from the selected B3 schematic;
* loads the SHA-256-frozen B2 PCB as the sole geometry/routing predecessor;
* preserves every B2 footprint except removed J3 (including J2/H1/H2)
  position/orientation/side/package;
* removes only the eleven source-track UUIDs authorized by the reviewed R3
  migration audit and preserves every other B2 track plus all 75 vias as a
  geometry/net subset;
* removes obsolete J3, retains J2 as the schematic-controlled DNP footprint;
* migrates every routed/pad/zone use of ``/3V3`` to ``/EPD_SW_3V3``;
* synchronizes every schematic footprint, UUID path, DNP flag and numbered pad
  net, loading footprints only from explicit project or KiCad 10 libraries;
* expands the outline to a parameterized 80 x 125 mm default; and
* reshapes the F/B/In1 GND pours with a real right-edge notch around the
  official WROOM antenna keepout (a fill-only exclusion is not accepted).

The only persistent output is the fixed staging PCB path below.  JSON audit
evidence is emitted to stdout.  The formal B3 PCB, B2 inputs, schematics and
attached hardware are never modified or accessed.  Routing and final placement
remain explicitly out of scope.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - exercised by non-KiCad Python
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_BOARD = B2_DIR / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"
PROJECT_BASENAME = "mf1750_wroom_b3_power_tf"
# This path and digest are the reviewed R3 schematic authority.  The identically
# hashed ``*_r3_staging.kicad_sch`` is evidence only and is deliberately not a
# selectable input.  A caller cannot redirect synchronization to another
# schematic with a command-line option.
CANONICAL_SCHEMATIC = B3_DIR / f"{PROJECT_BASENAME}.kicad_sch"
CANONICAL_SCHEMATIC_SHA256 = (
    "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0"
)
CANONICAL_PROJECT = B3_DIR / f"{PROJECT_BASENAME}.kicad_pro"
FORMAL_B3_BOARD = B3_DIR / f"{PROJECT_BASENAME}.kicad_pcb"
OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"

B2_BOARD_SHA256 = "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
DEFAULT_WIDTH_MM = 80.0
DEFAULT_HEIGHT_MM = 125.0
B2_DRIVER_BOTTOM_MM = 60.5
EDGE_INSET_MM = 0.65
ANTENNA_NOTCH_MARGIN_MM = 0.30

BOARD_ONLY_MECHANICAL_REFS = frozenset({"H1", "H2"})
OBSOLETE_REFS = frozenset({"J3"})

# Exact source B2 track exemptions from the reviewed placement/migration audit.
# UUIDs are only valid because B2_BOARD_SHA256 is checked before they are used.
# No via is exempt: all 75 source vias must survive.
EXEMPT_TRACK_CONTRACT: dict[str, dict[str, object]] = {
    "4d1417b9-2610-4ea8-9606-e6195d1b5abf": {
        "net": "/BUSY_N",
        "anchor_mm": (17.8336, 54.2864),
        "layer": "F.Cu",
    },
    "c7ac9ba3-f6f4-46d4-935c-e214f9bccdbc": {
        "net": "/BUSY_N",
        "anchor_mm": (6.4932, 51.3732),
        "layer": "B.Cu",
    },
    "5efd92a2-34d2-494e-8c59-2932a0ddd77d": {
        "net": "/RST_N",
        "anchor_mm": (10.0862, 52.4262),
        "layer": "B.Cu",
    },
    "0340befd-a85d-4e52-b8ef-655f1d3f1177": {
        "net": "/DC",
        "anchor_mm": (12.2199, 52.0199),
        "layer": "B.Cu",
    },
    "928a5728-d641-42f7-b774-6d21012d5bbb": {
        "net": "/CSB",
        "anchor_mm": (25.74, 54.0),
        "layer": "B.Cu",
    },
    "afa163df-7a84-4853-b0c1-b422f06590a5": {
        "net": "/CSB",
        "anchor_mm": (14.3169, 51.5769),
        "layer": "B.Cu",
    },
    "32be88ed-7f34-4043-9dce-4fdbcc086e2a": {
        "net": "/CS2",
        "anchor_mm": (45.012, 57.588),
        "layer": "F.Cu",
    },
    "062cf581-1873-4721-a329-56c85f3ec102": {
        "net": "/SI0",
        "anchor_mm": (43.2101, 55.0701),
        "layer": "B.Cu",
    },
    "15478d8c-6cc5-453b-85eb-5549480f929b": {
        "net": "/SCL",
        "anchor_mm": (43.9517, 53.2717),
        "layer": "B.Cu",
    },
    "97f80bfc-b49e-4a41-a1d7-24d5ca5f256c": {
        "net": "/3V3",
        "anchor_mm": (12.0, 10.5),
        "layer": "In2.Cu",
    },
    "40f189e3-83b2-4816-9a92-7f26f31c232e": {
        "net": "/GND",
        "anchor_mm": (9.0983, 4.3),
        "layer": "F.Cu",
    },
}
TRACK_UUID_EXEMPT = frozenset(EXEMPT_TRACK_CONTRACT)
VIA_UUID_EXEMPT: frozenset[str] = frozenset()
INTERFACE_PANEL_NETS = frozenset(
    {"/RST_N", "/DC", "/CSB", "/CS2", "/SCL", "/SI0", "/BUSY_N"}
)
J2_REQUIRED_PAD_NETS = {
    "4": "/MCU_BUSY_N",
    "5": "/MCU_RST_N",
    "6": "/MCU_DC",
    "7": "/MCU_CSB",
    "16": "/MCU_CS2",
    "17": "/MCU_SI0",
    "18": "/MCU_SCL",
}
# Mechanical pads intentionally present in a frozen/package footprint but not
# represented as electrical symbol pins.  They must remain unconnected.
ALLOWED_UNCONNECTED_MECHANICAL_PADS = {"J1": frozenset({"MP1", "MP2"})}
POWER_NET_ALIAS = {"/3V3": "/EPD_SW_3V3", "/GND": "GND"}
NO_CONNECT_NET_CANONICALIZATION = {
    "unconnected-(J2-J3-3_GPIO44/RX-Pad42)": (
        "unconnected-(J2-J3-3_GPIO44{slash}RX-Pad42)"
    ),
    "unconnected-(J2-J3-2_GPIO43/TX-Pad43)": (
        "unconnected-(J2-J3-2_GPIO43{slash}TX-Pad43)"
    ),
    "unconnected-(U11-I/O2-Pad4)": "unconnected-(U11-I{slash}O2-Pad4)",
    "unconnected-(U11-I/O1-Pad6)": "unconnected-(U11-I{slash}O1-Pad6)",
}

PROJECT_FOOTPRINT_LIBRARIES = {
    "B3_WROOM": B3_DIR / "b3_wroom_footprints.pretty",
    "MF1750_Compact": B3_DIR / "MF1750_Compact.pretty",
    "MF1750_Production": B3_DIR / "MF1750_Production.pretty",
}

# These are deterministic review placements, not an electrically optimized
# placement.  Everything else is parked on documented grids for later audit.
FIXED_PLACEMENTS_MM = {
    "U1": (52.0, 90.0, 270.0),
    "J4": (48.0, 119.0, 180.0),
    "J5": (3.0, 111.0, 90.0),
    "J6": (18.0, 120.0, 180.0),
    "U2": (39.0, 65.0, 0.0),
    "U3": (45.0, 65.0, 0.0),
    "U4": (51.0, 65.0, 0.0),
    "U5": (39.0, 72.0, 0.0),
    "U6": (49.0, 74.0, 0.0),
    "U8": (38.0, 83.0, 0.0),
    "U9": (44.0, 83.0, 0.0),
    "U10": (50.0, 83.0, 0.0),
    "U11": (56.0, 83.0, 0.0),
    "L3": (35.0, 65.0, 0.0),
    "Q3": (35.0, 72.0, 0.0),
    "D5": (35.0, 78.0, 0.0),
    "F1": (35.0, 84.0, 0.0),
    "SW1": (2.0, 65.0, 90.0),
    "SW2": (2.0, 73.0, 90.0),
    "SW3": (2.0, 81.0, 90.0),
    "SW4": (2.0, 89.0, 90.0),
    "SW5": (2.0, 97.0, 90.0),
}


@dataclass(frozen=True)
class SchematicComponent:
    ref: str
    value: str
    footprint: str
    dnp: bool
    uuid: str
    pins: frozenset[str]


@dataclass(frozen=True)
class SchematicNetlist:
    source: str
    tool: str
    components: dict[str, SchematicComponent]
    pin_nets: dict[tuple[str, str], str]
    nets: frozenset[str]


class BuildError(RuntimeError):
    """Raised whenever synchronization evidence is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_exact_sha256(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise BuildError(f"{label} is missing: {path}")
    actual = sha256_file(path)
    if actual.casefold() != expected.casefold():
        raise BuildError(
            f"{label} hash mismatch: expected {expected.casefold()}, got {actual}"
        )
    return actual


def find_project_locks() -> list[Path]:
    """Return KiCad locks in every source/output directory we protect."""
    locks: set[Path] = set()
    for directory in (B2_DIR, B3_DIR, STAGING):
        if directory.is_dir():
            locks.update(path.resolve() for path in directory.glob("~*.lck"))
    return sorted(locks, key=lambda path: str(path).casefold())


def _copy_required_file(source: Path, destination: Path, label: str) -> None:
    if not source.is_file():
        raise BuildError(f"self-contained project {label} is missing: {source}")
    shutil.copy2(source, destination)
    if not destination.is_file() or sha256_file(destination) != sha256_file(source):
        raise BuildError(f"self-contained project {label} copy failed: {destination}")


def prepare_self_contained_project(
    directory: Path,
    *,
    board_source: Path | None = None,
) -> dict[str, object]:
    """Create a disposable, basename-matched KiCad project in OS temp.

    KiCad schematic-parity resolution is basename/project-context sensitive.
    The copied project, schematic and eventual board therefore share exactly
    ``PROJECT_BASENAME``; project-local symbol/footprint tables and libraries
    are copied with them instead of relying on the authoritative source tree as
    an implicit working directory.
    """
    directory.mkdir(parents=True, exist_ok=False)
    project_path = directory / f"{PROJECT_BASENAME}.kicad_pro"
    schematic_path = directory / f"{PROJECT_BASENAME}.kicad_sch"
    board_path = directory / f"{PROJECT_BASENAME}.kicad_pcb"
    _copy_required_file(CANONICAL_PROJECT, project_path, "project")
    _copy_required_file(CANONICAL_SCHEMATIC, schematic_path, "schematic")
    _copy_required_file(B3_DIR / "fp-lib-table", directory / "fp-lib-table", "fp-lib-table")
    _copy_required_file(
        B3_DIR / "sym-lib-table", directory / "sym-lib-table", "sym-lib-table"
    )
    for symbol_name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        _copy_required_file(
            B3_DIR / symbol_name, directory / symbol_name, f"symbol library {symbol_name}"
        )
    for library_name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / library_name
        destination = directory / library_name
        if not source.is_dir():
            raise BuildError(f"self-contained footprint library is missing: {source}")
        shutil.copytree(source, destination)
    if board_source is not None:
        _copy_required_file(board_source, board_path, "PCB")

    if len({project_path.stem, schematic_path.stem, board_path.stem}) != 1:
        raise BuildError("self-contained KiCad project basenames do not match")
    if sha256_file(schematic_path) != CANONICAL_SCHEMATIC_SHA256:
        raise BuildError("self-contained schematic is not the frozen R3 authority")
    required = (
        project_path,
        schematic_path,
        directory / "fp-lib-table",
        directory / "sym-lib-table",
    )
    return {
        "directory": str(directory),
        "project": str(project_path),
        "schematic": str(schematic_path),
        "board": str(board_path),
        "same_basename": True,
        "required_file_sha256": {
            path.name: sha256_file(path) for path in required
        },
        "project_footprint_libraries": [
            "b3_wroom_footprints.pretty",
            "MF1750_Compact.pretty",
            "MF1750_Production.pretty",
        ],
        "project_symbol_libraries": [
            "b3_wroom_symbols.kicad_sym",
            "mf1750_local.kicad_sym",
        ],
    }


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    )


def find_kicad_cli(requested: Path | None) -> Path | None:
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


def kicad_cli_version(kicad_cli: Path) -> dict[str, object]:
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
        raise BuildError(f"kicad-cli --version failed: {version or 'no diagnostic'}")
    if version.split(".", 1)[0] != "10":
        raise BuildError(f"KiCad 10 is required; found {version!r}")
    return {"path": str(kicad_cli), "version": version}


def export_kicad_xml(
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
    if completed.returncode != 0:
        raise BuildError(
            "KiCad XML netlist export failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise BuildError("KiCad XML export returned success without an output file")
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "bytes": output.stat().st_size,
        "sha256": sha256_file(output),
    }


def parse_kicad_xml(path: Path) -> SchematicNetlist:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise BuildError(f"malformed KiCad XML netlist: {exc}") from exc
    if root.tag != "export":
        raise BuildError(f"unexpected netlist root {root.tag!r}")

    components: dict[str, SchematicComponent] = {}
    for element in root.findall("./components/comp"):
        ref = element.get("ref", "")
        if not ref or ref in components:
            raise BuildError(f"missing or duplicate schematic reference {ref!r}")
        value = element.findtext("value", default="")
        footprint = element.findtext("footprint", default="")
        uuid = element.findtext("tstamps", default="").strip()
        properties = {
            item.get("name", "").casefold()
            for item in element.findall("property")
            if item.get("name")
        }
        pins = frozenset(
            pin.get("num", "")
            for pin in element.findall("./units/unit/pins/pin")
            if pin.get("num")
        )
        if not footprint:
            raise BuildError(f"schematic component {ref} has no footprint")
        if not uuid or "/" in uuid or " " in uuid:
            raise BuildError(
                f"schematic component {ref} has invalid root UUID {uuid!r}"
            )
        if not pins:
            raise BuildError(f"schematic component {ref} exports no physical pins")
        components[ref] = SchematicComponent(
            ref=ref,
            value=value,
            footprint=footprint,
            dnp="dnp" in properties,
            uuid=uuid,
            pins=pins,
        )

    pin_nets: dict[tuple[str, str], str] = {}
    nets: set[str] = set()
    for net in root.findall("./nets/net"):
        xml_name = net.get("name", "")
        if not xml_name:
            raise BuildError("schematic XML contains an unnamed net")
        if (
            xml_name.startswith("unconnected-(")
            and "/" in xml_name
            and xml_name not in NO_CONNECT_NET_CANONICALIZATION
        ):
            raise BuildError(
                "unreviewed slash-bearing no-connect net requires exact KiCad "
                f"board-name canonicalization: {xml_name!r}"
            )
        name = NO_CONNECT_NET_CANONICALIZATION.get(xml_name, xml_name)
        nets.add(name)
        for node in net.findall("node"):
            ref = node.get("ref", "")
            pin = node.get("pin", "")
            key = (ref, pin)
            if not ref or not pin or key in pin_nets:
                raise BuildError(f"missing or duplicate schematic net node {key}")
            pin_nets[key] = name

    for component in components.values():
        missing = sorted(
            pin for pin in component.pins if (component.ref, pin) not in pin_nets
        )
        if missing:
            raise BuildError(f"{component.ref} pins lack exported nets: {missing}")
    return SchematicNetlist(
        source=root.findtext("./design/source", default=""),
        tool=root.findtext("./design/tool", default=""),
        components=components,
        pin_nets=pin_nets,
        nets=frozenset(nets),
    )


def validate_xml_source_identity(
    netlist: SchematicNetlist, schematic: Path
) -> dict[str, object]:
    if not netlist.source:
        raise BuildError("KiCad XML netlist has no design/source identity")
    xml_source = Path(netlist.source).resolve()
    canonical = schematic.resolve()
    if os.path.normcase(str(xml_source)) != os.path.normcase(str(canonical)):
        raise BuildError(
            f"KiCad XML source mismatch: expected {canonical}, got {xml_source}"
        )
    if not re.match(r"^Eeschema\s+10(?:\.|\s|$)", netlist.tool):
        raise BuildError(f"unexpected KiCad XML design/tool identity: {netlist.tool!r}")
    return {
        "expected_source": str(canonical),
        "xml_source": netlist.source,
        "source_matches": True,
        "xml_tool": netlist.tool,
        "tool_major_matches": True,
    }


def footprint_library_path(library: str, kicad_share: Path) -> Path:
    if library in PROJECT_FOOTPRINT_LIBRARIES:
        path = PROJECT_FOOTPRINT_LIBRARIES[library]
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", library):
            raise BuildError(
                f"unsafe or unsupported footprint library name {library!r}"
            )
        path = kicad_share / "footprints" / f"{library}.pretty"
    if not path.is_dir():
        raise BuildError(f"footprint library is missing: {library} -> {path}")
    return path.resolve()


def load_footprint(footprint_id: str, kicad_share: Path, footprint_io):
    if pcbnew is None:
        raise BuildError(f"pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
    if footprint_id.count(":") != 1:
        raise BuildError(f"footprint ID must be LIBRARY:NAME, got {footprint_id!r}")
    library, name = footprint_id.split(":", 1)
    if not re.fullmatch(r"[A-Za-z0-9_.+()\[\], -]+", name):
        raise BuildError(f"unsafe or unsupported footprint name {name!r}")
    library_path = footprint_library_path(library, kicad_share)
    expected_file = (library_path / f"{name}.kicad_mod").resolve()
    if expected_file.parent != library_path or not expected_file.is_file():
        raise BuildError(
            f"footprint file is missing: {footprint_id} -> {expected_file}"
        )
    # Do not use pcbnew.FootprintLoad(): in KiCad 10's SWIG build its global
    # plugin resolver can return a raw SwigPyObject without FootprintLoad.
    # The explicit s-expression IO object is deterministic for .pretty libs.
    footprint = footprint_io.FootprintLoad(str(library_path), name, False)
    if footprint is None:
        raise BuildError(f"pcbnew could not load {footprint_id}")
    if not isinstance(footprint, pcbnew.FOOTPRINT):
        raise BuildError(
            f"pcbnew returned an invalid footprint object for {footprint_id}: {type(footprint)!r}"
        )
    footprint.SetFPIDAsString(footprint_id)
    return footprint


def footprint_state(footprint) -> dict[str, object]:
    position = footprint.GetPosition()
    return {
        "x_iu": int(position.x),
        "y_iu": int(position.y),
        "rotation_deg": float(footprint.GetOrientationDegrees()),
        "flipped": bool(footprint.IsFlipped()),
        "layer": int(footprint.GetLayer()),
        "footprint": footprint.GetFPID().GetUniStringLibId(),
    }


def item_uuid(item) -> str:
    value = item.m_Uuid.AsString()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise BuildError(f"invalid KiCad item UUID {value!r}")
    return value


def point_matches_mm(point, xy_mm: tuple[float, float]) -> bool:
    return int(point.x) == pcbnew.FromMM(xy_mm[0]) and int(point.y) == pcbnew.FromMM(
        xy_mm[1]
    )


def validate_source_exemptions(board) -> dict[str, object]:
    """Bind every allowed removal to the frozen B2 UUID/net/layer/anchor."""
    found: dict[str, object] = {}
    source_vias = 0
    for item in board.GetTracks():
        uuid = item_uuid(item)
        if isinstance(item, pcbnew.PCB_VIA):
            source_vias += 1
            if uuid in TRACK_UUID_EXEMPT:
                raise BuildError(
                    f"track exemption unexpectedly identifies a via: {uuid}"
                )
            continue
        if uuid in TRACK_UUID_EXEMPT:
            found[uuid] = item
    missing = sorted(TRACK_UUID_EXEMPT - set(found))
    if missing:
        raise BuildError(f"frozen B2 is missing authorized exempt tracks: {missing}")
    if source_vias != 75 or VIA_UUID_EXEMPT:
        raise BuildError(
            f"B2 via freeze contract mismatch: source={source_vias}, exemptions={sorted(VIA_UUID_EXEMPT)}"
        )

    evidence: dict[str, object] = {}
    for uuid, contract in EXEMPT_TRACK_CONTRACT.items():
        item = found[uuid]
        actual_net = item.GetNetname()
        actual_layer = board.GetLayerName(item.GetLayer())
        anchor_mm = contract["anchor_mm"]
        anchor_found = point_matches_mm(item.GetStart(), anchor_mm) or point_matches_mm(
            item.GetEnd(), anchor_mm
        )
        if (
            actual_net != contract["net"]
            or actual_layer != contract["layer"]
            or not anchor_found
        ):
            raise BuildError(
                "authorized exemption geometry mismatch: "
                + repr(
                    {
                        "uuid": uuid,
                        "expected": contract,
                        "actual_net": actual_net,
                        "actual_layer": actual_layer,
                        "anchor_found": anchor_found,
                    }
                )
            )
        start = item.GetStart()
        end = item.GetEnd()
        evidence[uuid] = {
            "net": actual_net,
            "layer": actual_layer,
            "start_mm": [pcbnew.ToMM(start.x), pcbnew.ToMM(start.y)],
            "end_mm": [pcbnew.ToMM(end.x), pcbnew.ToMM(end.y)],
            "protected_anchor_mm": list(anchor_mm),
        }
    return {
        "source_track_exemption_count": len(found),
        "source_via_count": source_vias,
        "via_exemption_count": len(VIA_UUID_EXEMPT),
        "tracks": evidence,
    }


def track_signature(item, *, net_name: str | None = None) -> tuple[object, ...]:
    name = item.GetNetname() if net_name is None else net_name
    start = item.GetStart()
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            name,
            int(start.x),
            int(start.y),
            # KiCad 10 requires the queried layer for a via annulus width;
            # calling the no-argument overload asserts in wx debug builds.
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    end = item.GetEnd()
    return (
        str(item.GetClass()),
        name,
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


def ensure_net(board, name: str):
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def set_zone_polygon(zone, points_mm: list[tuple[float, float]]) -> None:
    if len(points_mm) < 4:
        raise BuildError("zone polygon needs at least four points")
    outline = zone.Outline()
    outline.RemoveAllContours()
    polygon = outline.NewOutline()
    for x, y in points_mm:
        outline.Append(pcbnew.VECTOR2I_MM(x, y), polygon)


def set_board_outline(board, width_mm: float, height_mm: float) -> None:
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(drawing)
    outline = pcbnew.PCB_SHAPE(board)
    outline.SetShape(pcbnew.SHAPE_T_RECT)
    outline.SetLayer(pcbnew.Edge_Cuts)
    outline.SetStart(pcbnew.VECTOR2I_MM(0.0, 0.0))
    outline.SetEnd(pcbnew.VECTOR2I_MM(width_mm, height_mm))
    outline.SetWidth(pcbnew.FromMM(0.05))
    board.Add(outline)


def place_new_footprints(new_refs: list[str]) -> dict[str, tuple[float, float, float]]:
    placements: dict[str, tuple[float, float, float]] = {}
    small_refs = [
        ref
        for ref in sorted(new_refs, key=natural_key)
        if ref not in FIXED_PLACEMENTS_MM and not ref.startswith("TP")
    ]
    for index, ref in enumerate(small_refs):
        column = index % 7
        row = index // 7
        placements[ref] = (8.0 + 3.8 * column, 64.0 + 3.8 * row, 0.0)

    testpoints = [
        ref
        for ref in sorted(new_refs, key=natural_key)
        if ref.startswith("TP") and ref not in FIXED_PLACEMENTS_MM
    ]
    for index, ref in enumerate(testpoints):
        column = index % 5
        row = index // 5
        placements[ref] = (38.0 + 4.5 * column, 94.0 + 4.5 * row, 0.0)

    for ref in new_refs:
        if ref in FIXED_PLACEMENTS_MM:
            placements[ref] = FIXED_PLACEMENTS_MM[ref]
    missing = sorted(set(new_refs) - set(placements), key=natural_key)
    if missing:
        raise BuildError(
            f"new footprints lack deterministic review placement: {missing}"
        )
    return placements


def synchronize_footprints(
    board,
    schematic: Path,
    netlist: SchematicNetlist,
    kicad_share: Path,
) -> dict[str, object]:
    existing = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    if len(existing) != len(list(board.GetFootprints())):
        raise BuildError("B2 board has duplicate footprint references")

    for ref in OBSOLETE_REFS:
        footprint = existing.pop(ref, None)
        if footprint is not None:
            board.Remove(footprint)

    unexpected = sorted(
        set(existing) - set(netlist.components) - BOARD_ONLY_MECHANICAL_REFS,
        key=natural_key,
    )
    if unexpected:
        raise BuildError(f"B2 board has unexplained board-only refs: {unexpected}")

    # Every retained B2 schematic footprint, including J2, is package-frozen.
    # H1/H2 are board-only mechanical footprints and are covered by the
    # post-save geometry state comparison.
    for ref in sorted(set(existing) & set(netlist.components), key=natural_key):
        actual_id = existing[ref].GetFPID().GetUniStringLibId()
        expected_id = netlist.components[ref].footprint
        if actual_id != expected_id:
            raise BuildError(
                f"frozen footprint substitution forbidden for {ref}: {actual_id!r} != {expected_id!r}"
            )

    new_refs = sorted(set(netlist.components) - set(existing), key=natural_key)
    placements = place_new_footprints(new_refs)
    # Keep one IO plugin alive across the complete load sequence.  Recreating
    # it for each footprint triggers a KiCad 10 SWIG lifetime defect where a
    # later call can return an unwrapped SwigPyObject.
    footprint_io = pcbnew.PCB_IO_KICAD_SEXPR()
    for ref in new_refs:
        component = netlist.components[ref]
        footprint = load_footprint(component.footprint, kicad_share, footprint_io)
        x, y, rotation = placements[ref]
        footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        footprint.SetOrientationDegrees(rotation)
        footprint.SetReference(ref)
        board.Add(footprint)
        existing[ref] = footprint

    # Ensure all XML nets exist before assigning any pad or migrated route.
    for name in sorted(netlist.nets):
        ensure_net(board, name)

    pad_contract_errors: list[dict[str, object]] = []
    for ref, component in sorted(
        netlist.components.items(), key=lambda item: natural_key(item[0])
    ):
        footprint = existing[ref]
        actual_id = footprint.GetFPID().GetUniStringLibId()
        if actual_id != component.footprint:
            # J2 is allowed to migrate geometrically, but never to an arbitrary
            # package that disagrees with the schematic contract.
            raise BuildError(
                f"footprint ID mismatch for {ref}: board={actual_id!r}, schematic={component.footprint!r}"
            )
        footprint.SetReference(ref)
        footprint.SetValue(component.value)
        footprint.SetDNP(component.dnp)
        footprint.SetPath(pcbnew.KIID_PATH(f"/{component.uuid}"))
        footprint.SetSheetfile(schematic.name)
        footprint.SetSheetname("")

        pads_by_number: dict[str, list[object]] = collections.defaultdict(list)
        for pad in footprint.Pads():
            number = pad.GetNumber()
            if number:
                pads_by_number[number].append(pad)
        missing = sorted(component.pins - set(pads_by_number), key=natural_key)
        allowed_mechanical = ALLOWED_UNCONNECTED_MECHANICAL_PADS.get(ref, frozenset())
        mechanical_net_errors = sorted(
            number
            for number in allowed_mechanical & set(pads_by_number)
            if any(pad.GetNetname() for pad in pads_by_number[number])
        )
        extra = sorted(
            set(pads_by_number) - component.pins - allowed_mechanical,
            key=natural_key,
        )
        if missing or extra or mechanical_net_errors:
            pad_contract_errors.append(
                {
                    "ref": ref,
                    "missing": missing,
                    "extra": extra,
                    "mechanical_pad_net_errors": mechanical_net_errors,
                }
            )
            continue
        for pin in component.pins:
            net_name = netlist.pin_nets[(ref, pin)]
            net = ensure_net(board, net_name)
            for pad in pads_by_number[pin]:
                pad.SetNet(net)
    if pad_contract_errors:
        raise BuildError(
            f"schematic/footprint pad-number mismatch: {pad_contract_errors}"
        )

    return {
        "schematic_footprints": len(netlist.components),
        "added_footprints": len(new_refs),
        "new_refs": new_refs,
        "retained_board_only_mechanical_refs": sorted(BOARD_ONLY_MECHANICAL_REFS),
        "removed_obsolete_refs": sorted(OBSOLETE_REFS),
        "review_placements_mm": {
            ref: {"x": xyz[0], "y": xyz[1], "rotation": xyz[2]}
            for ref, xyz in sorted(
                placements.items(), key=lambda item: natural_key(item[0])
            )
        },
        "no_connect_net_canonicalization": NO_CONNECT_NET_CANONICALIZATION,
    }


def migrate_routes(board) -> dict[str, object]:
    alias_nets = {
        source: ensure_net(board, target) for source, target in POWER_NET_ALIAS.items()
    }
    removed: dict[str, dict[str, object]] = {}
    migrated = 0
    for item in list(board.GetTracks()):
        uuid = item_uuid(item)
        net_name = item.GetNetname()
        if uuid in TRACK_UUID_EXEMPT:
            if isinstance(item, pcbnew.PCB_VIA):
                raise BuildError(f"via removal is forbidden: {uuid}")
            removed[uuid] = {
                "net": net_name,
                "layer": board.GetLayerName(item.GetLayer()),
            }
            board.Remove(item)
        elif net_name in alias_nets:
            item.SetNetCode(alias_nets[net_name].GetNetCode())
            migrated += 1
    if set(removed) != set(TRACK_UUID_EXEMPT):
        raise BuildError(
            "did not remove exactly the authorized source tracks: "
            + repr(
                {
                    "missing": sorted(TRACK_UUID_EXEMPT - set(removed)),
                    "extra": sorted(set(removed) - TRACK_UUID_EXEMPT),
                }
            )
        )
    for zone in board.Zones():
        if zone.GetNetname() in alias_nets:
            zone.SetNetCode(alias_nets[zone.GetNetname()].GetNetCode())
            migrated += 1
        elif zone.GetNetname() in INTERFACE_PANEL_NETS:
            raise BuildError(
                f"interface copper zone cannot be safely migrated: {zone.GetZoneName()}"
            )
    return {
        "removed_tracks_by_exact_source_uuid": dict(sorted(removed.items())),
        "removed_track_count": len(removed),
        "removed_via_count": 0,
        "migrated_semantic_alias_items": migrated,
        "net_alias": POWER_NET_ALIAS,
    }


def reshape_zones_for_board_and_wroom(
    board,
    width_mm: float,
    height_mm: float,
) -> dict[str, object]:
    removed_devkit_keepout = 0
    for zone in list(board.Zones()):
        if zone.GetZoneName() == "DEVKITC_ANTENNA_KEEP_OUT":
            board.Remove(zone)
            removed_devkit_keepout += 1
    if removed_devkit_keepout != 1:
        raise BuildError(
            f"expected exactly one obsolete DEVKITC_ANTENNA_KEEP_OUT, found {removed_devkit_keepout}"
        )

    u1 = board.FindFootprintByReference("U1")
    if u1 is None or len(u1.Zones()) != 1:
        raise BuildError(
            "official WROOM footprint must expose exactly one antenna keepout"
        )
    keepout = u1.Zones()[0]
    if not keepout.GetIsRuleArea():
        raise BuildError("WROOM antenna region is not a rule-area keepout")
    bbox = keepout.GetBoundingBox()
    keepout_box = {
        "left": pcbnew.ToMM(bbox.GetX()),
        "top": pcbnew.ToMM(bbox.GetY()),
        "right": pcbnew.ToMM(bbox.GetRight()),
        "bottom": pcbnew.ToMM(bbox.GetBottom()),
    }
    # At the reviewed 80 x 125 placement the official keepout ends only
    # 0.25 mm inside the right edge.  The copper-zone outline deliberately
    # carries that keepout all the way to the board edge, forming an actual
    # notch rather than relying on fill clipping.
    if keepout_box["right"] < width_mm - 1.0 or keepout_box["left"] >= width_mm:
        raise BuildError(
            f"WROOM antenna keepout is not edge-adjacent enough for a right-edge notch: {keepout_box}"
        )

    left = EDGE_INSET_MM
    top = EDGE_INSET_MM
    right = width_mm - EDGE_INSET_MM
    bottom = height_mm - EDGE_INSET_MM
    notch_left = max(left, keepout_box["left"] - ANTENNA_NOTCH_MARGIN_MM)
    notch_top = max(top, keepout_box["top"] - ANTENNA_NOTCH_MARGIN_MM)
    notch_bottom = min(bottom, keepout_box["bottom"] + ANTENNA_NOTCH_MARGIN_MM)
    if not (left < notch_left < right and top < notch_top < notch_bottom < bottom):
        raise BuildError(f"invalid WROOM notch geometry: {keepout_box}")
    ground_polygon = [
        (left, top),
        (right, top),
        (right, notch_top),
        (notch_left, notch_top),
        (notch_left, notch_bottom),
        (right, notch_bottom),
        (right, bottom),
        (left, bottom),
    ]

    edge_polygons = {
        "EDGE_TOP_KEEP_OUT": [
            (0.0, 0.0),
            (width_mm, 0.0),
            (width_mm, EDGE_INSET_MM),
            (0.0, EDGE_INSET_MM),
        ],
        "EDGE_RIGHT_KEEP_OUT": [
            (right, 0.0),
            (width_mm, 0.0),
            (width_mm, height_mm),
            (right, height_mm),
        ],
        "EDGE_LEFT_KEEP_OUT": [
            (0.0, 0.0),
            (EDGE_INSET_MM, 0.0),
            (EDGE_INSET_MM, height_mm),
            (0.0, height_mm),
        ],
        "EDGE_BOTTOM_KEEP_OUT": [
            (0.0, bottom),
            (width_mm, bottom),
            (width_mm, height_mm),
            (0.0, height_mm),
        ],
    }
    found_edges: set[str] = set()
    ground_layers: dict[str, str] = {}
    for zone in board.Zones():
        name = zone.GetZoneName()
        if name in edge_polygons:
            set_zone_polygon(zone, edge_polygons[name])
            found_edges.add(name)
        if not zone.GetIsRuleArea() and zone.GetNetname() == POWER_NET_ALIAS["/GND"]:
            layer_name = board.GetLayerName(zone.GetLayer())
            if layer_name in {"F.Cu", "B.Cu", "In1.Cu"}:
                set_zone_polygon(zone, ground_polygon)
                ground_layers[layer_name] = name
    if found_edges != set(edge_polygons):
        raise BuildError(
            f"missing B2 edge keepouts: {sorted(set(edge_polygons) - found_edges)}"
        )
    if set(ground_layers) != {"F.Cu", "B.Cu", "In1.Cu"}:
        raise BuildError(f"expected F/B/In1 GND zones, found {ground_layers}")
    return {
        "obsolete_devkit_keepout_removed": removed_devkit_keepout,
        "wroom_keepout_bbox_mm": keepout_box,
        "gnd_notch_polygon_mm": ground_polygon,
        "reshaped_ground_zones": ground_layers,
    }


def _zone_layer_names(board, zone) -> frozenset[str]:
    return frozenset(
        board.GetLayerName(layer)
        for layer in range(pcbnew.PCB_LAYER_ID_COUNT)
        if zone.IsOnLayer(layer)
    )


def _canonical_polygon_iu(zone) -> tuple[tuple[int, int], ...] | None:
    outline = zone.Outline()
    if outline.OutlineCount() != 1 or outline.VertexCount() < 3:
        return None
    points = tuple(
        (int(outline.CVertex(index).x), int(outline.CVertex(index).y))
        for index in range(outline.VertexCount())
    )
    variants: list[tuple[tuple[int, int], ...]] = []
    for sequence in (points, tuple(reversed(points))):
        variants.extend(
            sequence[index:] + sequence[:index] for index in range(len(sequence))
        )
    return min(variants)


def _expected_polygon_iu(
    points_mm: list[tuple[float, float]],
) -> tuple[tuple[int, int], ...]:
    points = tuple(
        (int(pcbnew.FromMM(x)), int(pcbnew.FromMM(y))) for x, y in points_mm
    )
    variants: list[tuple[tuple[int, int], ...]] = []
    for sequence in (points, tuple(reversed(points))):
        variants.extend(
            sequence[index:] + sequence[:index] for index in range(len(sequence))
        )
    return min(variants)


def audit_keepout_and_zone_contract(
    board, width_mm: float, height_mm: float
) -> dict[str, object]:
    expected_copper_layers = frozenset({"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"})
    u1 = board.FindFootprintByReference("U1")
    u1_zones = list(u1.Zones()) if u1 is not None else []
    u1_keepout = u1_zones[0] if len(u1_zones) == 1 else None
    u1_checks = {
        "exactly_one_footprint_zone": len(u1_zones) == 1,
        "rule_area": bool(u1_keepout and u1_keepout.GetIsRuleArea()),
        "all_four_copper_layers": bool(
            u1_keepout
            and _zone_layer_names(board, u1_keepout) == expected_copper_layers
        ),
        "forbids_tracks": bool(
            u1_keepout and u1_keepout.GetDoNotAllowTracks()
        ),
        "forbids_vias": bool(u1_keepout and u1_keepout.GetDoNotAllowVias()),
        "forbids_pads": bool(u1_keepout and u1_keepout.GetDoNotAllowPads()),
        "forbids_footprints": bool(
            u1_keepout and u1_keepout.GetDoNotAllowFootprints()
        ),
        "forbids_zone_fills": bool(
            u1_keepout and u1_keepout.GetDoNotAllowZoneFills()
        ),
    }
    if u1_keepout is not None:
        bbox = u1_keepout.GetBoundingBox()
        u1_bbox_mm = {
            "left": pcbnew.ToMM(bbox.GetX()),
            "top": pcbnew.ToMM(bbox.GetY()),
            "right": pcbnew.ToMM(bbox.GetRight()),
            "bottom": pcbnew.ToMM(bbox.GetBottom()),
        }
        u1_checks["right_edge_adjacent"] = (
            width_mm - 1.0 <= u1_bbox_mm["right"] <= width_mm
        )
    else:
        u1_bbox_mm = None
        u1_checks["right_edge_adjacent"] = False

    left = EDGE_INSET_MM
    top = EDGE_INSET_MM
    right = width_mm - EDGE_INSET_MM
    bottom = height_mm - EDGE_INSET_MM
    edge_polygons = {
        "EDGE_TOP_KEEP_OUT": [
            (0.0, 0.0),
            (width_mm, 0.0),
            (width_mm, top),
            (0.0, top),
        ],
        "EDGE_RIGHT_KEEP_OUT": [
            (right, 0.0),
            (width_mm, 0.0),
            (width_mm, height_mm),
            (right, height_mm),
        ],
        "EDGE_LEFT_KEEP_OUT": [
            (0.0, 0.0),
            (left, 0.0),
            (left, height_mm),
            (0.0, height_mm),
        ],
        "EDGE_BOTTOM_KEEP_OUT": [
            (0.0, bottom),
            (width_mm, bottom),
            (width_mm, height_mm),
            (0.0, height_mm),
        ],
    }
    edge_zones: dict[str, list[object]] = collections.defaultdict(list)
    for zone in board.Zones():
        if zone.GetZoneName() in edge_polygons:
            edge_zones[zone.GetZoneName()].append(zone)
    edge_checks: dict[str, dict[str, bool]] = {}
    for name, polygon in edge_polygons.items():
        matches = edge_zones.get(name, [])
        zone = matches[0] if len(matches) == 1 else None
        edge_checks[name] = {
            "exactly_one": len(matches) == 1,
            "rule_area": bool(zone and zone.GetIsRuleArea()),
            "all_four_copper_layers": bool(
                zone and _zone_layer_names(board, zone) == expected_copper_layers
            ),
            "forbids_tracks": bool(zone and zone.GetDoNotAllowTracks()),
            "forbids_vias": bool(zone and zone.GetDoNotAllowVias()),
            "allows_pads": bool(zone and not zone.GetDoNotAllowPads()),
            "allows_footprints": bool(
                zone and not zone.GetDoNotAllowFootprints()
            ),
            "forbids_zone_fills": bool(
                zone and zone.GetDoNotAllowZoneFills()
            ),
            "polygon_exact": bool(
                zone
                and _canonical_polygon_iu(zone) == _expected_polygon_iu(polygon)
            ),
        }

    ground_zones: dict[str, list[object]] = collections.defaultdict(list)
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and zone.GetNetname() == "GND":
            ground_zones[board.GetLayerName(zone.GetLayer())].append(zone)
    if u1_bbox_mm is not None:
        notch_left = max(left, u1_bbox_mm["left"] - ANTENNA_NOTCH_MARGIN_MM)
        notch_top = max(top, u1_bbox_mm["top"] - ANTENNA_NOTCH_MARGIN_MM)
        notch_bottom = min(
            bottom, u1_bbox_mm["bottom"] + ANTENNA_NOTCH_MARGIN_MM
        )
        expected_ground_polygon = [
            (left, top),
            (right, top),
            (right, notch_top),
            (notch_left, notch_top),
            (notch_left, notch_bottom),
            (right, notch_bottom),
            (right, bottom),
            (left, bottom),
        ]
    else:
        expected_ground_polygon = []
    ground_checks: dict[str, dict[str, bool]] = {}
    for layer_name in ("F.Cu", "In1.Cu", "B.Cu"):
        matches = ground_zones.get(layer_name, [])
        zone = matches[0] if len(matches) == 1 else None
        ground_checks[layer_name] = {
            "exactly_one": len(matches) == 1,
            "not_rule_area": bool(zone and not zone.GetIsRuleArea()),
            "single_layer": bool(
                zone and _zone_layer_names(board, zone) == {layer_name}
            ),
            "notched_polygon_exact": bool(
                zone
                and expected_ground_polygon
                and _canonical_polygon_iu(zone)
                == _expected_polygon_iu(expected_ground_polygon)
            ),
        }

    passed = (
        all(u1_checks.values())
        and all(all(checks.values()) for checks in edge_checks.values())
        and set(ground_zones) == {"F.Cu", "In1.Cu", "B.Cu"}
        and all(all(checks.values()) for checks in ground_checks.values())
    )
    return {
        "passed": passed,
        "u1_keepout": {"checks": u1_checks, "bbox_mm": u1_bbox_mm},
        "edge_keepouts": edge_checks,
        "ground_zone_layers": sorted(ground_zones),
        "ground_zones": ground_checks,
    }


def audit_board(
    board,
    schematic: Path,
    netlist: SchematicNetlist,
    frozen_placements: dict[str, dict[str, object]],
    expected_tracks: collections.Counter[tuple[object, ...]],
    width_mm: float,
    height_mm: float,
) -> dict[str, object]:
    footprints = {
        footprint.GetReference(): footprint for footprint in board.GetFootprints()
    }
    missing_refs = sorted(set(netlist.components) - set(footprints), key=natural_key)
    extra_refs = sorted(
        set(footprints) - set(netlist.components) - BOARD_ONLY_MECHANICAL_REFS,
        key=natural_key,
    )
    duplicate_count = len(list(board.GetFootprints())) - len(footprints)

    footprint_mismatches: list[dict[str, object]] = []
    pad_mismatches: list[dict[str, object]] = []
    for ref, component in sorted(
        netlist.components.items(), key=lambda item: natural_key(item[0])
    ):
        footprint = footprints.get(ref)
        if footprint is None:
            continue
        actual = {
            "value": footprint.GetValue(),
            "footprint": footprint.GetFPID().GetUniStringLibId(),
            "dnp": bool(footprint.IsDNP()),
            "path": footprint.GetPath().AsString(),
            "sheetfile": footprint.GetSheetfile(),
        }
        expected = {
            "value": component.value,
            "footprint": component.footprint,
            "dnp": component.dnp,
            "path": f"/{component.uuid}",
            "sheetfile": schematic.name,
        }
        if actual != expected:
            footprint_mismatches.append(
                {"ref": ref, "expected": expected, "actual": actual}
            )

        pads_by_number: dict[str, list[object]] = collections.defaultdict(list)
        for pad in footprint.Pads():
            if pad.GetNumber():
                pads_by_number[pad.GetNumber()].append(pad)
        missing = sorted(component.pins - set(pads_by_number), key=natural_key)
        allowed_mechanical = ALLOWED_UNCONNECTED_MECHANICAL_PADS.get(ref, frozenset())
        mechanical_net_errors = sorted(
            number
            for number in allowed_mechanical & set(pads_by_number)
            if any(pad.GetNetname() for pad in pads_by_number[number])
        )
        extra = sorted(
            set(pads_by_number) - component.pins - allowed_mechanical,
            key=natural_key,
        )
        wrong: list[dict[str, object]] = []
        for pin in sorted(component.pins & set(pads_by_number), key=natural_key):
            expected_net = netlist.pin_nets[(ref, pin)]
            actual_nets = sorted({pad.GetNetname() for pad in pads_by_number[pin]})
            if actual_nets != [expected_net]:
                wrong.append(
                    {"pin": pin, "expected": expected_net, "actual": actual_nets}
                )
        if missing or extra or wrong or mechanical_net_errors:
            pad_mismatches.append(
                {
                    "ref": ref,
                    "missing": missing,
                    "extra": extra,
                    "wrong": wrong,
                    "mechanical_pad_net_errors": mechanical_net_errors,
                }
            )

    frozen_drift = []
    for ref, expected in sorted(
        frozen_placements.items(), key=lambda item: natural_key(item[0])
    ):
        footprint = footprints.get(ref)
        actual = footprint_state(footprint) if footprint is not None else None
        if actual != expected:
            frozen_drift.append({"ref": ref, "expected": expected, "actual": actual})

    actual_tracks = collections.Counter(
        track_signature(item) for item in board.GetTracks()
    )
    track_missing = list((expected_tracks - actual_tracks).elements())
    track_extra = list((actual_tracks - expected_tracks).elements())
    remaining_exempt_uuids = sorted(
        item_uuid(item)
        for item in board.GetTracks()
        if item_uuid(item) in TRACK_UUID_EXEMPT
    )
    actual_via_count = sum(
        1 for item in board.GetTracks() if isinstance(item, pcbnew.PCB_VIA)
    )

    protected_anchors: dict[str, dict[str, object]] = {}
    for uuid, contract in EXEMPT_TRACK_CONTRACT.items():
        expected_net = POWER_NET_ALIAS.get(str(contract["net"]), str(contract["net"]))
        anchor_mm = contract["anchor_mm"]
        layer_name = str(contract["layer"])
        matching = []
        for item in board.GetTracks():
            if item.GetNetname() != expected_net or isinstance(item, pcbnew.PCB_VIA):
                continue
            if board.GetLayerName(item.GetLayer()) != layer_name:
                continue
            if point_matches_mm(item.GetStart(), anchor_mm) or point_matches_mm(
                item.GetEnd(), anchor_mm
            ):
                matching.append(item_uuid(item))
        protected_anchors[uuid] = {
            "net": expected_net,
            "layer": layer_name,
            "anchor_mm": list(anchor_mm),
            "retained_neighbor_track_uuids": sorted(matching),
            "present": bool(matching),
        }

    stale_alias_items: list[str] = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() in POWER_NET_ALIAS:
                stale_alias_items.append(
                    f"pad:{footprint.GetReference()}.{pad.GetNumber()}:{pad.GetNetname()}"
                )
    for index, item in enumerate(board.GetTracks()):
        if item.GetNetname() in POWER_NET_ALIAS:
            stale_alias_items.append(f"track:{index}:{item.GetNetname()}")
    for zone in board.Zones():
        if zone.GetNetname() in POWER_NET_ALIAS:
            stale_alias_items.append(f"zone:{zone.GetZoneName()}:{zone.GetNetname()}")

    interface_tracks = collections.Counter(
        item.GetNetname()
        for item in board.GetTracks()
        if item.GetNetname() in INTERFACE_PANEL_NETS
    )
    j2 = footprints.get("J2")
    j2_actual_pad_nets: dict[str, list[str]] = {}
    if j2 is not None:
        for pin in J2_REQUIRED_PAD_NETS:
            j2_actual_pad_nets[pin] = sorted(
                {pad.GetNetname() for pad in j2.Pads() if pad.GetNumber() == pin}
            )
    j2_required_match = all(
        j2_actual_pad_nets.get(pin) == [expected]
        for pin, expected in J2_REQUIRED_PAD_NETS.items()
    )
    edge_items = [
        drawing
        for drawing in board.GetDrawings()
        if drawing.GetLayer() == pcbnew.Edge_Cuts
    ]
    if len(edge_items) == 1:
        edge_start = edge_items[0].GetStart()
        edge_end = edge_items[0].GetEnd()
        measured_width = abs(pcbnew.ToMM(edge_end.x - edge_start.x))
        measured_height = abs(pcbnew.ToMM(edge_end.y - edge_start.y))
    else:
        board_bbox = board.GetBoardEdgesBoundingBox()
        measured_width = pcbnew.ToMM(board_bbox.GetWidth())
        measured_height = pcbnew.ToMM(board_bbox.GetHeight())

    keepout_audit = audit_keepout_and_zone_contract(
        board, width_mm, height_mm
    )

    checks = {
        "unique_footprint_refs": duplicate_count == 0,
        "no_missing_schematic_refs": not missing_refs,
        "no_unapproved_board_only_refs": not extra_refs,
        "j3_removed": "J3" not in footprints,
        "j2_present_and_dnp": j2 is not None and bool(j2.IsDNP()),
        "footprint_attributes_paths_match": not footprint_mismatches,
        "all_numbered_pad_nets_match": not pad_mismatches,
        "b2_all_minus_j3_footprint_geometry_unchanged": not frozen_drift,
        "exact_b2_copper_after_11_track_exemptions": not track_missing
        and not track_extra,
        "exactly_75_b2_vias_retained": actual_via_count == 75,
        "only_exact_track_exemptions_removed": not remaining_exempt_uuids,
        "protected_tail_anchors_retained": all(
            item["present"] for item in protected_anchors.values()
        ),
        "j2_seven_mcu_side_pad_nets_match": j2_required_match,
        "stale_semantic_alias_sources_have_no_items": not stale_alias_items,
        "single_rectangular_edge_item": len(edge_items) == 1
        and edge_items[0].GetShapeStr().casefold() == "rect",
        "outline_dimensions_match": abs(measured_width - width_mm) < 0.001
        and abs(measured_height - height_mm) < 0.001,
        "keepout_layers_attributes_and_notch_match": bool(
            keepout_audit["passed"]
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "reference_parity": {
            "schematic_refs": len(netlist.components),
            "board_refs": len(footprints),
            "allowed_board_only": sorted(BOARD_ONLY_MECHANICAL_REFS),
            "missing": missing_refs,
            "extra": extra_refs,
            "duplicate_count": duplicate_count,
        },
        "footprint_mismatches": footprint_mismatches,
        "pad_net_mismatches": pad_mismatches,
        "frozen_geometry_required_refs": sorted(frozen_placements, key=natural_key),
        "frozen_geometry_required_count": len(frozen_placements),
        "frozen_geometry_drift": frozen_drift,
        "critical_route_parity": {
            "expected_items": sum(expected_tracks.values()),
            "actual_items": sum(actual_tracks.values()),
            "missing_count": len(track_missing),
            "extra_count": len(track_extra),
            "missing_sample": track_missing[:20],
            "extra_sample": track_extra[:20],
            "comparison": "EXACT_FROZEN_SOURCE_MINUS_11_TRACK_UUIDS",
            "source_vias_required": 75,
            "output_vias": actual_via_count,
            "remaining_exempt_uuids": remaining_exempt_uuids,
            "protected_anchors": protected_anchors,
        },
        "semantic_net_migration": {
            "aliases": POWER_NET_ALIAS,
            "stale_source_net_items": stale_alias_items,
        },
        "interface_tracks_remaining": dict(sorted(interface_tracks.items())),
        "j2_required_pad_nets": {
            "expected": J2_REQUIRED_PAD_NETS,
            "actual": j2_actual_pad_nets,
        },
        "outline": {
            "requested_mm": {"width": width_mm, "height": height_mm},
            "measured_mm": {"width": measured_width, "height": measured_height},
            "edge_items": len(edge_items),
        },
        "keepout_and_zone_contract": keepout_audit,
    }


def run_drc(
    kicad_cli: Path,
    board_path: Path,
    report_path: Path,
    *,
    authority: str,
) -> dict[str, object]:
    project_path = board_path.with_suffix(".kicad_pro")
    schematic_path = board_path.with_suffix(".kicad_sch")
    if board_path.stem != PROJECT_BASENAME:
        raise BuildError(
            f"DRC board basename must be {PROJECT_BASENAME!r}: {board_path}"
        )
    for required in (
        board_path,
        project_path,
        schematic_path,
        board_path.parent / "fp-lib-table",
        board_path.parent / "sym-lib-table",
    ):
        if not required.is_file():
            raise BuildError(f"self-contained DRC context is incomplete: {required}")
    if sha256_file(schematic_path) != CANONICAL_SCHEMATIC_SHA256:
        raise BuildError("DRC sibling schematic is not the frozen canonical R3 source")
    command = [
        str(kicad_cli),
        "pcb",
        "drc",
        "--format",
        "json",
        "--severity-all",
        "--schematic-parity",
        "--refill-zones",
        "--output",
        str(report_path),
        str(board_path),
    ]
    completed = subprocess.run(
        command,
        cwd=board_path.parent,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    if completed.returncode != 0 or not report_path.is_file():
        raise BuildError(
            "KiCad DRC could not execute: "
            + (completed.stderr.strip() or completed.stdout.strip() or "no diagnostic")
        )
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BuildError(f"KiCad DRC emitted invalid JSON: {exc}") from exc
    if data.get("source") != board_path.name:
        raise BuildError(
            f"KiCad DRC source mismatch: expected {board_path.name!r}, got {data.get('source')!r}"
        )
    if "schematic_parity" not in data or not isinstance(
        data["schematic_parity"], list
    ):
        raise BuildError(
            "KiCad DRC did not emit a schematic_parity result array; parity execution is unproven"
        )
    violations = data.get("violations")
    unconnected = data.get("unconnected_items")
    if not isinstance(violations, list) or not isinstance(unconnected, list):
        raise BuildError("KiCad DRC JSON lacks violation/unconnected result arrays")
    schematic_parity = data["schematic_parity"]
    item_not_allowed = [
        item
        for item in violations
        if item.get("type") == "items_not_allowed"
        or item.get("type") == "item_on_disabled_layer"
        or "not allowed" in str(item.get("description", "")).casefold()
    ]
    violation_categories = collections.Counter(
        str(item.get("type", "UNKNOWN")) for item in violations
    )
    return {
        "execution_passed": True,
        "authority": authority,
        "command": command,
        "project_context_cwd": str(board_path.parent),
        "self_contained_same_basename": True,
        "schematic_parity_requested": "--schematic-parity" in command,
        "schematic_parity_result_present": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "kicad_version": data.get("kicad_version"),
        "report_source": data.get("source"),
        "included_severities": data.get("included_severities"),
        "ignored_checks": data.get("ignored_checks"),
        "violation_count": len(violations),
        "violation_categories": dict(
            sorted(violation_categories.items(), key=lambda item: (-item[1], item[0]))
        ),
        "unconnected_count": len(unconnected),
        "schematic_parity_count": len(schematic_parity),
        "schematic_parity_sample": schematic_parity[:10],
        "items_not_allowed_count": len(item_not_allowed),
        "items_not_allowed_sample": item_not_allowed[:10],
        "status": "EXPECTED_VIOLATIONS_PLACEMENT_NOT_ROUTED"
        if violations or unconnected or schematic_parity
        else "ZERO_VIOLATIONS",
    }


def run_schematic_parity_canary(
    kicad_cli: Path,
    validated_board: Path,
    temp_root: Path,
) -> dict[str, object]:
    """Prove ``--schematic-parity`` runs by removing U1 in a disposable copy."""
    canary_dir = temp_root / "parity_canary"
    context = prepare_self_contained_project(
        canary_dir, board_source=validated_board
    )
    canary_board_path = Path(str(context["board"]))
    canary_board = pcbnew.LoadBoard(str(canary_board_path))
    if canary_board is None:
        raise BuildError("could not load disposable schematic-parity canary board")
    u1 = canary_board.FindFootprintByReference("U1")
    if u1 is None:
        raise BuildError("schematic-parity canary requires U1 on the positive board")
    canary_board.Remove(u1)
    pcbnew.SaveBoard(str(canary_board_path), canary_board)
    report_path = canary_dir / "parity_canary_drc.json"
    drc = run_drc(
        kicad_cli,
        canary_board_path,
        report_path,
        authority="NEGATIVE_PARITY_EXECUTION_CANARY",
    )
    parity_text = json.dumps(
        drc["schematic_parity_sample"], ensure_ascii=False
    )
    if drc["schematic_parity_count"] < 1 or "U1" not in parity_text:
        raise BuildError(
            "schematic-parity canary did not detect deliberately removed U1; an empty positive array cannot be trusted"
        )
    return {
        "passed": True,
        "mutation_scope": "OS_TEMP_COPY_ONLY",
        "deliberately_removed_ref": "U1",
        "schematic_parity_count": drc["schematic_parity_count"],
        "u1_detected": True,
        "drc": drc,
    }


def failure_report(
    width_mm: float,
    height_mm: float,
    message: str,
    traceback_text: str | None = None,
) -> dict[str, object]:
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "REVISION_TO_STAGING_ONLY",
        "state": "HOLD_SYNC_FAILED",
        "overall_status": "HOLD",
        "result": "FAIL",
        "passed": False,
        "sync_passed": False,
        "locally_verified": False,
        "inputs": {
            "b2_board": str(B2_BOARD),
            "canonical_b3_schematic": str(CANONICAL_SCHEMATIC),
            "expected_schematic_sha256": CANONICAL_SCHEMATIC_SHA256,
        },
        "fixed_output": str(OUTPUT_BOARD),
        "board_mm": {"width": width_mm, "height": height_mm},
        "error": message,
        "traceback": traceback_text,
        "formal_b3_modified": False,
        "hardware_accessed": False,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the MF1750 B3 R3 placed PCB staging candidate from frozen B2"
    )
    parser.add_argument(
        "--width-mm",
        type=float,
        default=DEFAULT_WIDTH_MM,
        help="frozen board width; values other than 80.0 are rejected",
    )
    parser.add_argument(
        "--height-mm",
        type=float,
        default=DEFAULT_HEIGHT_MM,
        help="frozen board height; values other than 125.0 are rejected",
    )
    parser.add_argument("--kicad-cli", type=Path)
    parser.add_argument(
        "--kicad-share",
        type=Path,
        default=Path(r"C:\Program Files\KiCad\10.0\share\kicad"),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    schematic = CANONICAL_SCHEMATIC.resolve()
    width_mm = float(args.width_mm)
    height_mm = float(args.height_mm)
    report: dict[str, object]
    staging_candidate: Path | None = None
    try:
        if pcbnew is None:
            raise BuildError(
                "KiCad pcbnew Python module is required; run with KiCad 10 python.exe: "
                + PCBNEW_IMPORT_ERROR
            )
        pcbnew_version = str(pcbnew.GetBuildVersion())
        if pcbnew_version.split(".", 1)[0] != "10":
            raise BuildError(f"KiCad pcbnew 10 is required; found {pcbnew_version!r}")
        schematic_hash_before = require_exact_sha256(
            schematic,
            CANONICAL_SCHEMATIC_SHA256,
            "canonical R3 schematic",
        )
        require_exact_sha256(B2_BOARD, B2_BOARD_SHA256, "frozen B2 PCB")
        if not CANONICAL_PROJECT.is_file():
            raise BuildError(f"canonical B3 project is missing: {CANONICAL_PROJECT}")
        if not FORMAL_B3_BOARD.is_file():
            raise BuildError(f"formal B3 PCB is missing: {FORMAL_B3_BOARD}")
        formal_b3_hash_before = sha256_file(FORMAL_B3_BOARD)
        if (
            abs(width_mm - DEFAULT_WIDTH_MM) > 1e-9
            or abs(height_mm - DEFAULT_HEIGHT_MM) > 1e-9
        ):
            raise BuildError(
                "R3 synchronization outline is frozen at exactly 80.0 x 125.0 mm"
            )
        locks = find_project_locks()
        if locks:
            raise BuildError(
                "close relevant KiCad editors first: " + ", ".join(map(str, locks))
            )
        kicad_cli = find_kicad_cli(args.kicad_cli)
        if kicad_cli is None:
            raise BuildError("KiCad 10 kicad-cli was not found")
        cli_evidence = kicad_cli_version(kicad_cli)
        kicad_share = args.kicad_share.resolve()
        if not (kicad_share / "footprints").is_dir():
            raise BuildError(f"KiCad footprint root is missing: {kicad_share}")

        STAGING.mkdir(parents=True, exist_ok=True)
        # All mutation and every substantive validation step occur in the OS
        # temporary directory.  The repository receives one atomic staging
        # replacement only after the positive audit and negative parity canary
        # both pass.
        with tempfile.TemporaryDirectory(prefix="mf1750-b3-board-r3-") as temp_name:
            temp_root = Path(temp_name)
            positive_dir = temp_root / "positive"
            temp_context = prepare_self_contained_project(positive_dir)
            temp_board = Path(str(temp_context["board"]))
            xml_path = temp_root / "canonical_r3.xml"
            drc_path = positive_dir / "positive_drc.json"
            output_backup = temp_root / "previous_fixed_staging.kicad_pcb"

            export_evidence = export_kicad_xml(kicad_cli, schematic, xml_path)
            schematic_hash_after_export = require_exact_sha256(
                schematic,
                CANONICAL_SCHEMATIC_SHA256,
                "canonical R3 schematic after XML export",
            )
            if schematic_hash_after_export != schematic_hash_before:
                raise BuildError("canonical R3 schematic changed during XML export")
            netlist = parse_kicad_xml(xml_path)
            xml_identity = validate_xml_source_identity(netlist, schematic)

            board = pcbnew.LoadBoard(str(B2_BOARD))
            if board is None:
                raise BuildError("pcbnew could not load frozen B2 PCB")
            source_exemption_evidence = validate_source_exemptions(board)
            b2_all_refs = {
                footprint.GetReference() for footprint in board.GetFootprints()
            }
            footprint_geometry_required = b2_all_refs - OBSOLETE_REFS
            frozen_placements = {
                ref: footprint_state(board.FindFootprintByReference(ref))
                for ref in sorted(footprint_geometry_required, key=natural_key)
                if board.FindFootprintByReference(ref) is not None
            }
            if set(frozen_placements) != footprint_geometry_required:
                raise BuildError(
                    "B2-all-minus-J3 frozen geometry refs missing: "
                    + repr(sorted(footprint_geometry_required - set(frozen_placements)))
                )
            expected_tracks = collections.Counter()
            for item in board.GetTracks():
                uuid = item_uuid(item)
                old_net = item.GetNetname()
                if uuid in TRACK_UUID_EXEMPT:
                    continue
                expected_tracks[
                    track_signature(
                        item, net_name=POWER_NET_ALIAS.get(old_net, old_net)
                    )
                ] += 1

            footprint_sync = synchronize_footprints(
                board,
                schematic,
                netlist,
                kicad_share,
            )
            route_sync = migrate_routes(board)
            set_board_outline(board, width_mm, height_mm)
            zone_sync = reshape_zones_for_board_and_wroom(board, width_mm, height_mm)
            title = board.GetTitleBlock()
            title.SetTitle(
                "MF1750 WROOM B3 power + TF placed synchronization candidate"
            )
            title.SetRevision("B3-WROOM-POWER-TF-R3-PLACED")
            title.SetComment(
                0, "PLACED_CANDIDATE_NOT_ROUTED; frozen B2 driver geometry"
            )
            title.SetComment(1, f"Schematic SHA256 {schematic_hash_before}")

            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(str(temp_board), board)
            if not temp_board.is_file() or temp_board.stat().st_size == 0:
                raise BuildError(
                    "pcbnew SaveBoard did not create the staging candidate"
                )
            reloaded = pcbnew.LoadBoard(str(temp_board))
            if reloaded is None:
                raise BuildError("KiCad could not reload the saved staging PCB")
            audit = audit_board(
                reloaded,
                schematic,
                netlist,
                frozen_placements,
                expected_tracks,
                width_mm,
                height_mm,
            )
            drc = run_drc(
                kicad_cli,
                temp_board,
                drc_path,
                authority="OS_TEMP_SELF_CONTAINED_PRECOMMIT",
            )
            parity_canary = run_schematic_parity_canary(
                kicad_cli, temp_board, temp_root
            )
            sync_passed = (
                bool(audit["passed"])
                and drc["items_not_allowed_count"] == 0
                and bool(drc["schematic_parity_requested"])
                and bool(drc["schematic_parity_result_present"])
                and drc["schematic_parity_count"] == 0
                and bool(parity_canary["passed"])
            )
            if not sync_passed:
                raise BuildError(
                    "post-save PCB audit failed: "
                    + json.dumps(
                        {
                            "checks": audit["checks"],
                            "items_not_allowed_count": drc[
                                "items_not_allowed_count"
                            ],
                            "items_not_allowed_sample": drc[
                                "items_not_allowed_sample"
                            ],
                            "schematic_parity_count": drc[
                                "schematic_parity_count"
                            ],
                            "schematic_parity_sample": drc[
                                "schematic_parity_sample"
                            ],
                            "outline": audit["outline"],
                            "footprint_mismatches": audit["footprint_mismatches"][:5],
                            "pad_net_mismatches": audit["pad_net_mismatches"][:5],
                        },
                        ensure_ascii=False,
                    )
                )

            schematic_hash_before_commit = require_exact_sha256(
                schematic,
                CANONICAL_SCHEMATIC_SHA256,
                "canonical R3 schematic before staging commit",
            )
            if schematic_hash_before_commit != schematic_hash_before:
                raise BuildError("canonical R3 schematic changed before staging commit")
            if sha256_file(FORMAL_B3_BOARD) != formal_b3_hash_before:
                raise BuildError("formal B3 PCB changed during OS-temp validation")
            locks_before_commit = find_project_locks()
            if locks_before_commit:
                raise BuildError(
                    "KiCad lock appeared before staging commit: "
                    + ", ".join(map(str, locks_before_commit))
                )

            validated_board_sha256 = sha256_file(temp_board)
            output_before = (
                sha256_file(OUTPUT_BOARD) if OUTPUT_BOARD.is_file() else None
            )
            had_previous_output = OUTPUT_BOARD.is_file()
            if had_previous_output:
                shutil.copy2(OUTPUT_BOARD, output_backup)
            staging_candidate = STAGING / (
                f".{OUTPUT_BOARD.stem}.{os.getpid()}.{secrets.token_hex(6)}.kicad_pcb"
            )
            if (
                staging_candidate.parent.resolve() != STAGING.resolve()
                or staging_candidate.exists()
            ):
                raise BuildError(
                    f"unsafe or colliding staging candidate path: {staging_candidate}"
                )
            shutil.copy2(temp_board, staging_candidate)
            if sha256_file(staging_candidate) != validated_board_sha256:
                raise BuildError("staging transfer changed the validated PCB bytes")
            os.replace(staging_candidate, OUTPUT_BOARD)
            staging_candidate = None
            try:
                if sha256_file(OUTPUT_BOARD) != validated_board_sha256:
                    raise BuildError("atomic staging replacement changed PCB bytes")
                schematic_hash_after_commit = require_exact_sha256(
                    schematic,
                    CANONICAL_SCHEMATIC_SHA256,
                    "canonical R3 schematic after staging commit",
                )
                formal_b3_hash_after = sha256_file(FORMAL_B3_BOARD)
                if formal_b3_hash_after != formal_b3_hash_before:
                    raise BuildError("formal B3 PCB changed during staging commit")
            except Exception:
                # Promotion is transactional: restore the exact prior staging
                # output if immutable-source/post-copy validation fails.
                if had_previous_output:
                    os.replace(output_backup, OUTPUT_BOARD)
                elif OUTPUT_BOARD.is_file():
                    OUTPUT_BOARD.unlink()
                raise
            report = {
                "schema": 1,
                "tool": Path(__file__).name,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "PLACED_CANDIDATE_NOT_ROUTED",
                "overall_status": "HOLD",
                "result": "HOLD",
                "passed": False,
                "sync_passed": True,
                "locally_verified": False,
                "inputs": {
                    "frozen_b2_board": {
                        "path": str(B2_BOARD),
                        "bytes": B2_BOARD.stat().st_size,
                        "sha256": sha256_file(B2_BOARD),
                    },
                    "canonical_b3_schematic": {
                        "path": str(schematic),
                        "bytes": schematic.stat().st_size,
                        "expected_sha256": CANONICAL_SCHEMATIC_SHA256,
                        "sha256_before_export": schematic_hash_before,
                        "sha256_after_export": schematic_hash_after_export,
                        "sha256_before_commit": schematic_hash_before_commit,
                        "sha256_after_commit": schematic_hash_after_commit,
                        "xml_source": netlist.source,
                        "xml_tool": netlist.tool,
                    },
                    "formal_b3_board_read_only": {
                        "path": str(FORMAL_B3_BOARD),
                        "sha256_before": formal_b3_hash_before,
                        "sha256_after": formal_b3_hash_after,
                        "unchanged": formal_b3_hash_after == formal_b3_hash_before,
                    },
                },
                "tools": {"pcbnew": pcbnew_version, "kicad_cli": cli_evidence},
                "netlist_export": export_evidence,
                "xml_identity": xml_identity,
                "self_contained_validation_context": temp_context,
                "validation_scope": "OS_TEMP_BEFORE_ATOMIC_STAGING_COMMIT",
                "source_lock_check": {
                    "directories": [str(B2_DIR), str(B3_DIR), str(STAGING)],
                    "passed": True,
                    "locks": [],
                    "rechecked_immediately_before_commit": True,
                },
                "schematic_parity_execution_canary": parity_canary,
                "fixed_output": {
                    "path": str(OUTPUT_BOARD),
                    "previous_sha256": output_before,
                    "bytes": OUTPUT_BOARD.stat().st_size,
                    "sha256": sha256_file(OUTPUT_BOARD),
                    "atomic_copy_matches_validated_os_temp": (
                        sha256_file(OUTPUT_BOARD) == validated_board_sha256
                    ),
                },
                "board_mm": {"width": width_mm, "height": height_mm},
                "footprint_sync": footprint_sync,
                "route_sync": route_sync,
                "source_exemption_contract": source_exemption_evidence,
                "zone_sync": zone_sync,
                "audit": audit,
                "drc": drc,
                "holds": [
                    "placement is deterministic review parking, not final current-loop placement",
                    "new B3 nets are intentionally unrouted",
                    f"KiCad DRC reports {drc['violation_count']} violations and {drc['unconnected_count']} unconnected items",
                    f"KiCad schematic parity reports {drc['schematic_parity_count']} warnings",
                    "thermal, SI, mechanical fit and manufacturing readiness are NOT verified",
                ],
                "formal_b3_modified": False,
                "b2_modified": False,
                "schematic_modified": False,
                "hardware_accessed": False,
            }
    except Exception as exc:
        report = failure_report(
            width_mm,
            height_mm,
            f"{type(exc).__name__}: {exc}",
            traceback.format_exc(),
        )
    finally:
        if staging_candidate is not None and staging_candidate.exists():
            if staging_candidate.parent.resolve() != STAGING.resolve():
                raise BuildError(
                    f"refusing to clean candidate outside staging: {staging_candidate}"
                )
            staging_candidate.unlink()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    # A successful synchronization is a useful build operation even though the
    # placed/unrouted design is correctly held from LOCALLY_VERIFIED status.
    return 0 if report.get("sync_passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
