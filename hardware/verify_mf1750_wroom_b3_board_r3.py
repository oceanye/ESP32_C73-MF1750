#!/usr/bin/env python3
"""Independent read-only verifier for the MF1750 WROOM B3 R3 PCB.

The verifier binds the frozen B2 PCB by SHA-256, exports the authoritative
R3 schematic to a temporary KiCad XML netlist, and checks a staging PCB.  It
does not import the board generator and never saves or refills a board.

The preservation contract is deliberately asymmetric: protected B2 copper
must be a subset of R3, while new R3 copper is allowed.  Exactly eleven B2
track UUIDs are exempted for the J2/J3 interface migration; no B2 via is
   exempt.  The only source-net normalizations are ``/3V3`` to
   ``/EPD_SW_3V3``, the root-sheet spelling ``/GND`` to global ``GND``, and
   four exact KiCad XML-to-PCB no-connect spellings containing ``{slash}``.

Run this script with KiCad's Python interpreter when ``pcbnew`` is not
installed in the system interpreter.  JSON is emitted to stdout and failure
returns a non-zero status.
"""

from __future__ import annotations

import argparse
import collections
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
from typing import Iterable, Sequence

try:
    import pcbnew  # type: ignore
except Exception as exc:  # pragma: no cover - depends on host interpreter
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    PCBNEW_IMPORT_ERROR = ""


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_BOARD = B2_DIR / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
AUTHORITATIVE_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
STAGING_BOARD = B3_DIR / "staging" / "mf1750_wroom_b3_power_tf_r3_placed.kicad_pcb"

B2_BOARD_SHA256 = "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
EXPECTED_BOARD_BOUNDS_MM = (0.0, 0.0, 80.0, 125.0)
EXPECTED_COPPER_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
ALLOWED_BOARD_ONLY_REFS = frozenset({"H1", "H2"})
OPTIONAL_BOARD_ONLY_REFS = frozenset({"H3", "H4"})
# J1 has two soldered shell/hold-down lands that are intentionally not symbol
# pins.  Keep this allow-list exact: an added electrical pad must still fail.
ALLOWED_MECHANICAL_FOOTPRINT_PADS = frozenset({("J1", "MP1"), ("J1", "MP2")})
REQUIRED_ABSENT_REFS = frozenset({"J3"})

# Exact one-way source normalization.  Do not add wildcard/prefix aliases.
NET_ALIAS = {
    "/3V3": "/EPD_SW_3V3",
    "/GND": "GND",
}
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

J2_EXPECTED_PAD_NETS = {
    "4": "/MCU_BUSY_N",
    "5": "/MCU_RST_N",
    "6": "/MCU_DC",
    "7": "/MCU_CSB",
    "16": "/MCU_CS2",
    "17": "/MCU_SI0",
    "18": "/MCU_SCL",
}


@dataclass(frozen=True)
class TrackExemption:
    net: str
    layer: str
    width_mm: float
    endpoints_mm: tuple[tuple[float, float], tuple[float, float]]
    reason: str


# UUIDs are bound to B2_BOARD_SHA256.  They are used only to remove these
# source objects before geometry comparison; R3 UUID reuse is never required.
TRACK_EXEMPTIONS: dict[str, TrackExemption] = {
    "4d1417b9-2610-4ea8-9606-e6195d1b5abf": TrackExemption(
        "/BUSY_N",
        "F.Cu",
        0.2,
        ((13.62, 58.5), (17.8336, 54.2864)),
        "J2.4 BUSY_N interface tail A",
    ),
    "c7ac9ba3-f6f4-46d4-935c-e214f9bccdbc": TrackExemption(
        "/BUSY_N",
        "B.Cu",
        0.2,
        ((6.4932, 51.3732), (13.62, 58.5)),
        "J2.4 BUSY_N interface tail B",
    ),
    "5efd92a2-34d2-494e-8c59-2932a0ddd77d": TrackExemption(
        "/RST_N",
        "B.Cu",
        0.2,
        ((10.0862, 52.4262), (16.16, 58.5)),
        "J2.5 RST_N interface tail",
    ),
    "0340befd-a85d-4e52-b8ef-655f1d3f1177": TrackExemption(
        "/DC",
        "B.Cu",
        0.2,
        ((12.2199, 52.0199), (18.7, 58.5)),
        "J2.6 DC interface tail",
    ),
    "928a5728-d641-42f7-b774-6d21012d5bbb": TrackExemption(
        "/CSB",
        "B.Cu",
        0.2,
        ((21.24, 58.5), (25.74, 54.0)),
        "J2.7 CSB interface tail A",
    ),
    "afa163df-7a84-4853-b0c1-b422f06590a5": TrackExemption(
        "/CSB",
        "B.Cu",
        0.2,
        ((14.3169, 51.5769), (21.24, 58.5)),
        "J2.7 CSB interface tail B",
    ),
    "32be88ed-7f34-4043-9dce-4fdbcc086e2a": TrackExemption(
        "/CS2",
        "F.Cu",
        0.2,
        ((44.1, 58.5), (45.012, 57.588)),
        "J2.16 CS2 interface tail",
    ),
    "062cf581-1873-4721-a329-56c85f3ec102": TrackExemption(
        "/SI0",
        "B.Cu",
        0.2,
        ((43.2101, 55.0701), (46.64, 58.5)),
        "J2.17 SI0 interface tail",
    ),
    "15478d8c-6cc5-453b-85eb-5549480f929b": TrackExemption(
        "/SCL",
        "B.Cu",
        0.2,
        ((43.9517, 53.2717), (49.18, 58.5)),
        "J2.18 SCL interface tail",
    ),
    "97f80bfc-b49e-4a41-a1d7-24d5ca5f256c": TrackExemption(
        "/3V3",
        "In2.Cu",
        0.6,
        ((12.0, 4.3), (12.0, 10.5)),
        "removed J3.1 legacy power-entry tail",
    ),
    "40f189e3-83b2-4816-9a92-7f26f31c232e": TrackExemption(
        "/GND",
        "F.Cu",
        0.2,
        ((9.0983, 4.3), (10.0, 4.3)),
        "removed J3.2 legacy ground-entry tail",
    ),
}
VIA_EXEMPTIONS: frozenset[str] = frozenset()


class VerifyError(RuntimeError):
    """Raised when required evidence is missing or malformed."""


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


@dataclass
class Audit:
    checks: dict[str, dict[str, object]] = field(default_factory=dict)

    def add(
        self,
        check_id: str,
        passed: bool,
        message: str,
        evidence: object | None = None,
    ) -> None:
        item: dict[str, object] = {
            "status": "PASS" if passed else "FAIL",
            "message": message,
        }
        if evidence is not None:
            item["evidence"] = evidence
        self.checks[check_id] = item

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(
            item["status"] == "PASS" for item in self.checks.values()
        )

    def summary(self) -> dict[str, int]:
        failed = sum(item["status"] != "PASS" for item in self.checks.values())
        return {
            "total": len(self.checks),
            "passed": len(self.checks) - failed,
            "failed": failed,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(value: str) -> tuple[object, ...]:
    parts: list[object] = []
    token = ""
    digit = False
    for char in value:
        if token and char.isdigit() != digit:
            parts.append((1, int(token)) if digit else (0, token.casefold()))
            token = ""
        token += char
        digit = char.isdigit()
    if token:
        parts.append((1, int(token)) if digit else (0, token.casefold()))
    return tuple(parts)


def limited(items: Sequence[object], limit: int = 20) -> dict[str, object]:
    return {
        "count": len(items),
        "sample": list(items[:limit]),
        "truncated": len(items) > limit,
    }


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
        raise VerifyError(f"kicad-cli --version failed: {version or 'no diagnostic'}")
    if version.split(".", 1)[0] != "10":
        raise VerifyError(f"KiCad 10 is required; found {version!r}")
    return {"path": str(kicad_cli), "version": version}


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
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise VerifyError(
            f"KiCad netlist export failed: {diagnostic or 'no diagnostic'}"
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise VerifyError("KiCad netlist export returned no output")
    return {
        "returncode": completed.returncode,
        "bytes": output.stat().st_size,
        "sha256": sha256_file(output),
    }


def parse_netlist(path: Path) -> SchematicNetlist:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise VerifyError(f"malformed KiCad XML netlist: {exc}") from exc
    if root.tag != "export":
        raise VerifyError(f"unexpected netlist root {root.tag!r}")

    components: dict[str, SchematicComponent] = {}
    for element in root.findall("./components/comp"):
        ref = element.get("ref", "")
        if not ref or ref in components:
            raise VerifyError(f"missing or duplicate schematic reference {ref!r}")
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
        if not footprint or not uuid or not pins:
            raise VerifyError(
                f"schematic component {ref} lacks footprint, UUID, or physical pins"
            )
        components[ref] = SchematicComponent(
            ref=ref,
            value=element.findtext("value", default=""),
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
            raise VerifyError("schematic XML contains an unnamed net")
        if (
            xml_name.startswith("unconnected-(")
            and "/" in xml_name
            and xml_name not in NO_CONNECT_NET_CANONICALIZATION
        ):
            raise VerifyError(
                "unreviewed slash-bearing no-connect net requires exact KiCad "
                f"board-name canonicalization: {xml_name!r}"
            )
        name = NO_CONNECT_NET_CANONICALIZATION.get(xml_name, xml_name)
        nets.add(name)
        for node in net.findall("node"):
            key = (node.get("ref", ""), node.get("pin", ""))
            if not all(key) or key in pin_nets:
                raise VerifyError(f"missing or duplicate schematic net node {key}")
            pin_nets[key] = name

    for component in components.values():
        missing = [
            pin for pin in component.pins if (component.ref, pin) not in pin_nets
        ]
        if missing:
            raise VerifyError(f"schematic {component.ref} pins lack nets: {missing}")
    return SchematicNetlist(
        source=root.findtext("./design/source", default=""),
        tool=root.findtext("./design/tool", default=""),
        components=components,
        pin_nets=pin_nets,
        nets=frozenset(nets),
    )


def normalize_source_net(name: str) -> str:
    return NET_ALIAS.get(name, name)


def point_tuple(point: object) -> tuple[int, int]:
    return (int(point.x), int(point.y))


def item_signature(
    item: object,
    board: object,
    *,
    normalize_source: bool,
) -> tuple[object, ...]:
    net = item.GetNetname()
    if normalize_source:
        net = normalize_source_net(net)
    start = point_tuple(item.GetStart())
    if isinstance(item, pcbnew.PCB_VIA):
        return (
            "via",
            net,
            start,
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            board.GetLayerName(item.TopLayer()),
            board.GetLayerName(item.BottomLayer()),
        )
    end = point_tuple(item.GetEnd())
    endpoints = tuple(sorted((start, end)))
    return (
        "track",
        net,
        board.GetLayerName(item.GetLayer()),
        endpoints,
        int(item.GetWidth()),
        str(item.GetClass()),
    )


def geometry_only_track_signature(item: object, board: object) -> tuple[object, ...]:
    start = point_tuple(item.GetStart())
    end = point_tuple(item.GetEnd())
    return (
        board.GetLayerName(item.GetLayer()),
        tuple(sorted((start, end))),
        int(item.GetWidth()),
        str(item.GetClass()),
    )


def rect_tuple(rect: object) -> tuple[int, int, int, int]:
    return (
        int(rect.GetX()),
        int(rect.GetY()),
        int(rect.GetWidth()),
        int(rect.GetHeight()),
    )


def footprint_geometry(footprint: object) -> tuple[object, ...]:
    pads: list[tuple[object, ...]] = []
    for pad in footprint.Pads():
        size = pad.GetSize()
        drill = pad.GetDrillSize()
        delta = pad.GetDelta()
        pads.append(
            (
                pad.GetNumber(),
                point_tuple(pad.GetPosition()),
                (int(size.x), int(size.y)),
                (int(drill.x), int(drill.y)),
                (int(delta.x), int(delta.y)),
                int(pad.GetShape()),
                int(pad.GetAttribute()),
                int(pad.GetOrientation().AsTenthsOfADegree()),
                pad.GetLayerSet().FmtHex(),
                round(float(pad.GetRoundRectRadiusRatio()), 9),
                int(pad.GetChamferPositions()),
                round(float(pad.GetChamferRectRatio()), 9),
            )
        )
    position = footprint.GetPosition()
    return (
        footprint.GetFPID().GetUniStringLibId(),
        (int(position.x), int(position.y)),
        int(footprint.GetOrientation().AsTenthsOfADegree()),
        int(footprint.GetLayer()),
        bool(footprint.IsFlipped()),
        tuple(sorted(pads)),
        rect_tuple(footprint.GetBoundingBox(False, False)),
    )


def audit_footprint_geometry(
    audit: Audit,
    b2_board: object,
    candidate: object,
) -> None:
    b2 = {item.GetReference(): item for item in b2_board.GetFootprints()}
    actual = {item.GetReference(): item for item in candidate.GetFootprints()}
    required = sorted(set(b2) - REQUIRED_ABSENT_REFS, key=natural_key)
    missing = [ref for ref in required if ref not in actual]
    drift = []
    for ref in required:
        if ref in actual and footprint_geometry(b2[ref]) != footprint_geometry(
            actual[ref]
        ):
            drift.append(ref)
    audit.add(
        "b2_footprint_geometry",
        not missing and not drift,
        "all B2 footprint geometry except J3 is preserved",
        {
            "required_count": len(required),
            "missing": limited(missing),
            "drift": limited(drift),
        },
    )


def validate_exemption_source(
    audit: Audit,
    b2_board: object,
) -> dict[str, object]:
    items = {item.m_Uuid.AsString(): item for item in b2_board.GetTracks()}
    errors: list[dict[str, object]] = []
    geometry: dict[str, tuple[object, ...]] = {}
    for uuid, contract in TRACK_EXEMPTIONS.items():
        item = items.get(uuid)
        if item is None:
            errors.append({"uuid": uuid, "error": "missing"})
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            errors.append({"uuid": uuid, "error": "is via, expected track"})
            continue
        endpoints_mm = tuple(
            sorted(
                (
                    tuple(round(value, 4) for value in pcbnew.ToMM(item.GetStart())),
                    tuple(round(value, 4) for value in pcbnew.ToMM(item.GetEnd())),
                )
            )
        )
        expected_endpoints = tuple(sorted(contract.endpoints_mm))
        observed = {
            "net": item.GetNetname(),
            "layer": b2_board.GetLayerName(item.GetLayer()),
            "width_mm": round(float(pcbnew.ToMM(item.GetWidth())), 4),
            "endpoints_mm": endpoints_mm,
        }
        expected = {
            "net": contract.net,
            "layer": contract.layer,
            "width_mm": contract.width_mm,
            "endpoints_mm": expected_endpoints,
        }
        if observed != expected:
            errors.append(
                {"uuid": uuid, "error": "contract mismatch", "observed": observed}
            )
        geometry[uuid] = geometry_only_track_signature(item, b2_board)

    via_uuids = {
        item.m_Uuid.AsString()
        for item in b2_board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
    }
    unexpected_via_exemptions = sorted(VIA_EXEMPTIONS - via_uuids)
    if unexpected_via_exemptions:
        errors.append(
            {
                "error": "declared via exemptions absent from B2",
                "uuids": unexpected_via_exemptions,
            }
        )
    audit.add(
        "exemption_source_contract",
        not errors and len(TRACK_EXEMPTIONS) == 11 and not VIA_EXEMPTIONS,
        "exactly 11 track and zero via exemptions match frozen B2",
        {
            "track_exemptions": len(TRACK_EXEMPTIONS),
            "via_exemptions": len(VIA_EXEMPTIONS),
            "errors": limited(errors),
        },
    )
    return geometry


def audit_copper_preservation(
    audit: Audit,
    b2_board: object,
    candidate: object,
    exempt_geometry: dict[str, tuple[object, ...]],
) -> None:
    protected: collections.Counter[tuple[object, ...]] = collections.Counter()
    protected_tracks = 0
    protected_vias = 0
    for item in b2_board.GetTracks():
        uuid = item.m_Uuid.AsString()
        if uuid in TRACK_EXEMPTIONS or uuid in VIA_EXEMPTIONS:
            continue
        protected[item_signature(item, b2_board, normalize_source=True)] += 1
        if isinstance(item, pcbnew.PCB_VIA):
            protected_vias += 1
        else:
            protected_tracks += 1

    actual = collections.Counter(
        item_signature(item, candidate, normalize_source=False)
        for item in candidate.GetTracks()
    )
    missing_counter = protected - actual
    missing = [repr(item) for item in missing_counter.elements()]
    audit.add(
        "protected_copper_subset",
        not missing and protected_vias == 75,
        "protected B2 track/via geometry is a subset of R3",
        {
            "protected_tracks": protected_tracks,
            "protected_vias": protected_vias,
            "missing": limited(missing),
        },
    )

    candidate_geometry = collections.Counter(
        geometry_only_track_signature(item, candidate)
        for item in candidate.GetTracks()
        if not isinstance(item, pcbnew.PCB_VIA)
    )
    stale = [
        {"uuid": uuid, "reason": TRACK_EXEMPTIONS[uuid].reason}
        for uuid, signature in exempt_geometry.items()
        if candidate_geometry[signature]
    ]
    audit.add(
        "legacy_interface_tails_absent",
        not stale,
        "all 11 legacy J2/J3 track geometries are removed or rerouted",
        limited(stale),
    )


def audit_zone_preservation(
    audit: Audit,
    b2_board: object,
    candidate: object,
) -> None:
    source_zones = [zone for zone in b2_board.Zones() if not zone.GetIsRuleArea()]
    candidate_zones = [zone for zone in candidate.Zones() if not zone.GetIsRuleArea()]
    failures: list[dict[str, object]] = []
    for source in source_zones:
        key = (
            source.GetZoneName(),
            normalize_source_net(source.GetNetname()),
            b2_board.GetLayerName(source.GetLayer()),
        )
        matches = [
            zone
            for zone in candidate_zones
            if (
                zone.GetZoneName(),
                zone.GetNetname(),
                candidate.GetLayerName(zone.GetLayer()),
            )
            == key
        ]
        remaining = pcbnew.SHAPE_POLY_SET(source.Outline())
        for match in matches:
            remaining.BooleanSubtract(match.Outline())
        remaining_area = float(remaining.Area())
        settings_match = any(
            match.GetMinThickness() == source.GetMinThickness() for match in matches
        )
        if not matches or remaining_area != 0.0 or not settings_match:
            failures.append(
                {
                    "zone": key,
                    "candidate_count": len(matches),
                    "uncovered_area_iu2": remaining_area,
                    "min_thickness_match": settings_match,
                }
            )
    audit.add(
        "b2_copper_zone_subset",
        not failures,
        "B2 copper-zone outlines and minimum thickness remain covered in R3",
        {"source_zone_count": len(source_zones), "failures": limited(failures)},
    )


def pads_by_number(footprint: object) -> dict[str, list[object]]:
    result: dict[str, list[object]] = collections.defaultdict(list)
    for pad in footprint.Pads():
        if pad.GetNumber():
            result[pad.GetNumber()].append(pad)
    return result


def audit_schematic_parity(
    audit: Audit,
    candidate: object,
    schematic: Path,
    netlist: SchematicNetlist,
    additional_board_only_refs: frozenset[str],
) -> None:
    footprints = list(candidate.GetFootprints())
    by_ref = {item.GetReference(): item for item in footprints}
    duplicate_refs = sorted(
        ref
        for ref, count in collections.Counter(
            item.GetReference() for item in footprints
        ).items()
        if count > 1
    )
    missing = sorted(set(netlist.components) - set(by_ref), key=natural_key)
    allowed_board_only_refs = ALLOWED_BOARD_ONLY_REFS | additional_board_only_refs
    extra = sorted(
        set(by_ref) - set(netlist.components) - allowed_board_only_refs,
        key=natural_key,
    )
    optional_mechanical_failures: list[dict[str, object]] = []
    for ref in sorted(additional_board_only_refs, key=natural_key):
        footprint = by_ref.get(ref)
        if footprint is None:
            optional_mechanical_failures.append(
                {"ref": ref, "reason": "allowed mechanical footprint is missing"}
            )
            continue
        attributes = int(footprint.GetAttributes())
        pad_failures = [
            {
                "number": pad.GetNumber(),
                "net": pad.GetNetname(),
            }
            for pad in footprint.Pads()
            if pad.GetNumber() or pad.GetNetname()
        ]
        expected_attribute_mask = int(
            pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
        )
        if (
            not footprint.IsBoardOnly()
            or attributes & expected_attribute_mask != expected_attribute_mask
            or pad_failures
        ):
            optional_mechanical_failures.append(
                {
                    "ref": ref,
                    "board_only": bool(footprint.IsBoardOnly()),
                    "exclude_from_bom": bool(attributes & pcbnew.FP_EXCLUDE_FROM_BOM),
                    "exclude_from_position_files": bool(
                        attributes & pcbnew.FP_EXCLUDE_FROM_POS_FILES
                    ),
                    "electrical_pad_failures": pad_failures,
                }
            )
    footprint_mismatches: list[dict[str, object]] = []
    pad_mismatches: list[dict[str, object]] = []
    accepted_mechanical_pads: list[str] = []

    for ref, component in sorted(
        netlist.components.items(), key=lambda item: natural_key(item[0])
    ):
        footprint = by_ref.get(ref)
        if footprint is None:
            continue
        actual_attributes = {
            "value": footprint.GetValue(),
            "footprint": footprint.GetFPID().GetUniStringLibId(),
            "dnp": bool(footprint.IsDNP()),
            "path": footprint.GetPath().AsString(),
        }
        expected_attributes = {
            "value": component.value,
            "footprint": component.footprint,
            "dnp": component.dnp,
            "path": f"/{component.uuid}",
        }
        if actual_attributes != expected_attributes:
            footprint_mismatches.append(
                {
                    "ref": ref,
                    "expected": expected_attributes,
                    "actual": actual_attributes,
                }
            )

        board_pads = pads_by_number(footprint)
        missing_pins = sorted(component.pins - set(board_pads), key=natural_key)
        extra_pins = []
        for pin in sorted(set(board_pads) - component.pins, key=natural_key):
            if (ref, pin) in ALLOWED_MECHANICAL_FOOTPRINT_PADS and all(
                not pad.GetNetname() for pad in board_pads[pin]
            ):
                accepted_mechanical_pads.append(f"{ref}.{pin}")
            else:
                extra_pins.append(pin)
        wrong = []
        for pin in sorted(component.pins & set(board_pads), key=natural_key):
            expected_net = netlist.pin_nets[(ref, pin)]
            observed_nets = sorted({pad.GetNetname() for pad in board_pads[pin]})
            if observed_nets != [expected_net]:
                wrong.append(
                    {"pin": pin, "expected": expected_net, "actual": observed_nets}
                )
        if missing_pins or extra_pins or wrong:
            pad_mismatches.append(
                {
                    "ref": ref,
                    "missing": missing_pins,
                    "extra": extra_pins,
                    "wrong": wrong,
                }
            )

    parity_ok = not any(
        (
            duplicate_refs,
            missing,
            extra,
            footprint_mismatches,
            pad_mismatches,
            optional_mechanical_failures,
        )
    )
    audit.add(
        "schematic_footprint_pad_net_parity",
        parity_ok,
        "all schematic footprints, attributes, paths, electrical pads, and pad nets match",
        {
            "authoritative_schematic": str(schematic),
            "schematic_footprints": len(netlist.components),
            "board_footprints": len(footprints),
            "allowed_board_only": sorted(allowed_board_only_refs),
            "optional_board_only_contract": {
                "requested": sorted(additional_board_only_refs),
                "failures": optional_mechanical_failures,
            },
            "accepted_unconnected_mechanical_pads": accepted_mechanical_pads,
            "duplicate_refs": limited(duplicate_refs),
            "missing_refs": limited(missing),
            "extra_refs": limited(extra),
            "footprint_mismatches": limited(footprint_mismatches),
            "pad_mismatches": limited(pad_mismatches),
        },
    )

    j2 = by_ref.get("J2")
    observed_j2: dict[str, list[str]] = {}
    if j2 is not None:
        j2_pads = pads_by_number(j2)
        for pin in J2_EXPECTED_PAD_NETS:
            observed_j2[pin] = sorted(
                {pad.GetNetname() for pad in j2_pads.get(pin, [])}
            )
    j2_ok = (
        j2 is not None
        and bool(j2.IsDNP())
        and all(
            observed_j2.get(pin) == [net] for pin, net in J2_EXPECTED_PAD_NETS.items()
        )
    )
    audit.add(
        "j2_dnp_mcu_side_contract",
        j2_ok,
        "J2 is physically retained as DNP with seven MCU-side nets",
        {
            "present": j2 is not None,
            "dnp": bool(j2.IsDNP()) if j2 is not None else None,
            "expected": J2_EXPECTED_PAD_NETS,
            "actual": observed_j2,
        },
    )
    audit.add(
        "j3_removed",
        "J3" not in by_ref and "J3" not in netlist.components,
        "obsolete J3 is absent from schematic and PCB",
        {
            "schematic_present": "J3" in netlist.components,
            "board_present": "J3" in by_ref,
        },
    )


def audit_net_names(
    audit: Audit,
    candidate: object,
    netlist: SchematicNetlist,
) -> None:
    used: set[str] = set()
    stale_locations: list[str] = []
    for footprint in candidate.GetFootprints():
        for pad in footprint.Pads():
            name = pad.GetNetname()
            if name:
                used.add(name)
            if name in NET_ALIAS:
                stale_locations.append(
                    f"pad:{footprint.GetReference()}.{pad.GetNumber()}:{name}"
                )
    for index, item in enumerate(candidate.GetTracks()):
        name = item.GetNetname()
        if name:
            used.add(name)
        if name in NET_ALIAS:
            kind = "via" if isinstance(item, pcbnew.PCB_VIA) else "track"
            stale_locations.append(f"{kind}:{index}:{name}")
    for zone in candidate.Zones():
        if zone.GetIsRuleArea():
            continue
        name = zone.GetNetname()
        if name:
            used.add(name)
        if name in NET_ALIAS:
            stale_locations.append(f"zone:{zone.GetZoneName()}:{name}")

    unexpected = sorted(used - set(netlist.nets))
    audit.add(
        "no_stale_or_unknown_used_nets",
        not stale_locations and not unexpected,
        "pads, tracks, vias, and copper zones use authoritative R3 net names",
        {
            "aliases": NET_ALIAS,
            "stale_items": limited(stale_locations),
            "unknown_used_nets": limited(unexpected),
        },
    )


def audit_board_outline(audit: Audit, board: object) -> None:
    edge_items = [
        item for item in board.GetDrawings() if item.GetLayer() == pcbnew.Edge_Cuts
    ]
    rectangle = (
        edge_items[0]
        if len(edge_items) == 1
        and isinstance(edge_items[0], pcbnew.PCB_SHAPE)
        and edge_items[0].GetShapeStr().casefold() == "rect"
        else None
    )
    observed: tuple[float, float, float, float] | None = None
    if rectangle is not None:
        start = rectangle.GetStart()
        end = rectangle.GetEnd()
        x0 = float(pcbnew.ToMM(min(start.x, end.x)))
        y0 = float(pcbnew.ToMM(min(start.y, end.y)))
        x1 = float(pcbnew.ToMM(max(start.x, end.x)))
        y1 = float(pcbnew.ToMM(max(start.y, end.y)))
        observed = tuple(round(value, 4) for value in (x0, y0, x1 - x0, y1 - y0))
    copper_layers = tuple(
        board.GetLayerName(layer)
        for layer in board.GetEnabledLayers().SeqStackupTop2Bottom()
        if board.GetLayerName(layer).endswith(".Cu")
    )
    audit.add(
        "board_outline_and_layers",
        observed == EXPECTED_BOARD_BOUNDS_MM
        and copper_layers == EXPECTED_COPPER_LAYERS,
        "board is exactly 80 x 125 mm at origin with four copper layers",
        {
            "expected_bounds_mm": EXPECTED_BOARD_BOUNDS_MM,
            "actual_bounds_mm": observed,
            "edge_items": len(edge_items),
            "edge_shapes": [item.GetShapeStr() for item in edge_items],
            "expected_copper_layers": EXPECTED_COPPER_LAYERS,
            "actual_copper_layers": copper_layers,
        },
    )


def audit_wroom_keepout(audit: Audit, board: object) -> None:
    u1 = board.FindFootprintByReference("U1")
    zones = list(u1.Zones()) if u1 is not None else []
    rule_zones = [zone for zone in zones if zone.GetIsRuleArea()]
    keepout = rule_zones[0] if len(rule_zones) == 1 else None
    constraints: dict[str, object] = {}
    layers: list[str] = []
    bbox_mm: dict[str, float] = {}
    zone_intersections: list[dict[str, object]] = []

    if keepout is not None:
        constraints = {
            "zone_fills": bool(keepout.GetDoNotAllowZoneFills()),
            "tracks": bool(keepout.GetDoNotAllowTracks()),
            "vias": bool(keepout.GetDoNotAllowVias()),
            "pads": bool(keepout.GetDoNotAllowPads()),
            "footprints": bool(keepout.GetDoNotAllowFootprints()),
        }
        layer_set = keepout.GetLayerSet()
        layers = [
            name
            for name in EXPECTED_COPPER_LAYERS
            if layer_set.Contains(board.GetLayerID(name))
        ]
        bbox = keepout.GetBoundingBox()
        bbox_mm = {
            "left": round(float(pcbnew.ToMM(bbox.GetX())), 4),
            "top": round(float(pcbnew.ToMM(bbox.GetY())), 4),
            "right": round(float(pcbnew.ToMM(bbox.GetRight())), 4),
            "bottom": round(float(pcbnew.ToMM(bbox.GetBottom())), 4),
        }
        for zone in board.Zones():
            if zone.GetIsRuleArea() or not layer_set.Contains(zone.GetLayer()):
                continue
            intersection = pcbnew.SHAPE_POLY_SET(zone.Outline())
            intersection.BooleanIntersection(keepout.Outline())
            area = float(intersection.Area())
            if area != 0.0:
                zone_intersections.append(
                    {
                        "zone": zone.GetZoneName(),
                        "net": zone.GetNetname(),
                        "layer": board.GetLayerName(zone.GetLayer()),
                        "intersection_area_iu2": area,
                    }
                )

    old_keepout_names = sorted(
        zone.GetZoneName()
        for zone in board.Zones()
        if zone.GetZoneName() == "DEVKITC_ANTENNA_KEEP_OUT"
    )
    board_right = EXPECTED_BOARD_BOUNDS_MM[0] + EXPECTED_BOARD_BOUNDS_MM[2]
    board_bottom = EXPECTED_BOARD_BOUNDS_MM[1] + EXPECTED_BOARD_BOUNDS_MM[3]
    right_edge_gap = round(board_right - bbox_mm.get("right", -1.0), 4)
    inside_board = bool(bbox_mm) and (
        bbox_mm["left"] >= EXPECTED_BOARD_BOUNDS_MM[0]
        and bbox_mm["top"] >= EXPECTED_BOARD_BOUNDS_MM[1]
        and bbox_mm["right"] <= board_right
        and bbox_mm["bottom"] <= board_bottom
    )
    passed = (
        u1 is not None
        and len(rule_zones) == 1
        and constraints
        and all(constraints.values())
        and tuple(layers) == EXPECTED_COPPER_LAYERS
        and inside_board
        and 0.0 <= right_edge_gap <= 0.25
        and not zone_intersections
        and not old_keepout_names
    )
    audit.add(
        "wroom_antenna_rule_area",
        bool(passed),
        "U1 has one all-copper-layer antenna keepout and copper-zone notch",
        {
            "u1_present": u1 is not None,
            "embedded_rule_area_count": len(rule_zones),
            "constraints": constraints,
            "layers": layers,
            "bbox_mm": bbox_mm,
            "inside_board": inside_board,
            "right_edge_gap_mm": right_edge_gap,
            "maximum_right_edge_gap_mm": 0.25,
            "copper_zone_intersections": limited(zone_intersections),
            "obsolete_devkit_keepout": old_keepout_names,
        },
    )


def audit_board(
    b2_path: Path,
    schematic: Path,
    board_path: Path,
    netlist: SchematicNetlist,
    netlist_evidence: dict[str, object],
    cli_evidence: dict[str, object],
    additional_board_only_refs: frozenset[str],
) -> dict[str, object]:
    if pcbnew is None:
        raise VerifyError(f"pcbnew is unavailable: {PCBNEW_IMPORT_ERROR}")
    b2_board = pcbnew.LoadBoard(str(b2_path))
    candidate = pcbnew.LoadBoard(str(board_path))
    if b2_board is None or candidate is None:
        raise VerifyError("pcbnew could not load B2 or staging PCB")

    audit = Audit()
    b2_hash = sha256_file(b2_path)
    audit.add(
        "frozen_b2_sha256",
        b2_hash == B2_BOARD_SHA256,
        "frozen B2 PCB SHA-256 matches",
        {"expected": B2_BOARD_SHA256, "actual": b2_hash},
    )
    audit.add(
        "policy_constants",
        len(TRACK_EXEMPTIONS) == 11
        and not VIA_EXEMPTIONS
        and NET_ALIAS == {"/3V3": "/EPD_SW_3V3", "/GND": "GND"},
        "migration policy has 11 track, zero via, and two exact aliases",
        {
            "track_exemptions": len(TRACK_EXEMPTIONS),
            "via_exemptions": len(VIA_EXEMPTIONS),
            "net_alias": NET_ALIAS,
        },
    )
    exempt_geometry = validate_exemption_source(audit, b2_board)
    audit_footprint_geometry(audit, b2_board, candidate)
    audit_copper_preservation(audit, b2_board, candidate, exempt_geometry)
    audit_zone_preservation(audit, b2_board, candidate)
    audit_schematic_parity(
        audit,
        candidate,
        schematic,
        netlist,
        additional_board_only_refs,
    )
    audit_net_names(audit, candidate, netlist)
    audit_board_outline(audit, candidate)
    audit_wroom_keepout(audit, candidate)

    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "REVIEW_ONLY",
        "inputs": {
            "frozen_b2_pcb": {
                "path": str(b2_path),
                "sha256": b2_hash,
            },
            "authoritative_r3_schematic": {
                "path": str(schematic),
                "sha256": sha256_file(schematic),
                "netlist_source": netlist.source,
                "netlist_tool": netlist.tool,
            },
            "staging_r3_pcb": {
                "path": str(board_path),
                "sha256": sha256_file(board_path),
            },
        },
        "kicad": cli_evidence,
        "temporary_netlist": netlist_evidence,
        "policy": {
            "track_exemption_uuids": sorted(TRACK_EXEMPTIONS),
            "via_exemption_uuids": sorted(VIA_EXEMPTIONS),
            "net_alias": NET_ALIAS,
            "footprint_geometry": "all B2 refs except removed J3",
            "copper_comparison": "protected B2 subset of candidate R3",
            "additional_board_only_refs": sorted(additional_board_only_refs),
        },
        "result": "PASS" if audit.passed else "FAIL",
        "passed": audit.passed,
        "summary": audit.summary(),
        "checks": audit.checks,
        "hardware_accessed": False,
        "boards_modified": False,
        "schematics_modified": False,
    }


def failure_report(
    b2_path: Path,
    schematic: Path,
    board_path: Path,
    message: str,
) -> dict[str, object]:
    return {
        "schema": 1,
        "tool": Path(__file__).name,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "REVIEW_ONLY",
        "inputs": {
            "frozen_b2_pcb": str(b2_path),
            "authoritative_r3_schematic": str(schematic),
            "staging_r3_pcb": str(board_path),
        },
        "result": "FAIL",
        "passed": False,
        "summary": {"total": 1, "passed": 0, "failed": 1},
        "checks": {
            "verifier_internal": {
                "status": "FAIL",
                "message": message,
            }
        },
        "hardware_accessed": False,
        "boards_modified": False,
        "schematics_modified": False,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only MF1750 WROOM B3 R3 staging-PCB verifier"
    )
    parser.add_argument(
        "board",
        nargs="?",
        type=Path,
        default=STAGING_BOARD,
        help=f"staging PCB (default: {STAGING_BOARD})",
    )
    parser.add_argument(
        "--schematic",
        type=Path,
        default=AUTHORITATIVE_SCHEMATIC,
        help=f"authoritative R3 schematic (default: {AUTHORITATIVE_SCHEMATIC})",
    )
    parser.add_argument(
        "--b2",
        type=Path,
        default=B2_BOARD,
        help=f"frozen B2 PCB (default: {B2_BOARD})",
    )
    parser.add_argument(
        "--kicad-cli",
        type=Path,
        help="explicit KiCad 10 kicad-cli path",
    )
    parser.add_argument(
        "--allow-board-only",
        action="append",
        default=[],
        metavar="REF",
        help="allow reviewed optional board-only mechanical ref H3 or H4",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    b2_path = args.b2.resolve()
    schematic = args.schematic.resolve()
    board_path = args.board.resolve()
    additional_board_only_refs = frozenset(args.allow_board_only)
    report: dict[str, object]
    try:
        for label, path, suffix in (
            ("B2 PCB", b2_path, ".kicad_pcb"),
            ("R3 schematic", schematic, ".kicad_sch"),
            ("R3 staging PCB", board_path, ".kicad_pcb"),
        ):
            if path.suffix.casefold() != suffix or not path.is_file():
                raise VerifyError(f"{label} is missing or has wrong suffix: {path}")
            if path.stat().st_size > 100 * 1024 * 1024:
                raise VerifyError(f"{label} exceeds 100 MiB: {path}")
        if sha256_file(b2_path) != B2_BOARD_SHA256:
            raise VerifyError("frozen B2 PCB SHA-256 mismatch")
        unsupported_board_only = additional_board_only_refs - OPTIONAL_BOARD_ONLY_REFS
        if unsupported_board_only:
            raise VerifyError(
                "unsupported optional board-only refs: "
                + repr(sorted(unsupported_board_only, key=natural_key))
            )
        kicad_cli = resolve_kicad_cli(args.kicad_cli)
        if kicad_cli is None:
            raise VerifyError("KiCad 10 kicad-cli was not found")
        cli_evidence = kicad_version(kicad_cli)
        with tempfile.TemporaryDirectory(prefix="mf1750-b3-board-r3-verify-") as name:
            xml_path = Path(name) / "authoritative_r3.xml"
            netlist_evidence = export_netlist(kicad_cli, schematic, xml_path)
            netlist = parse_netlist(xml_path)
            report = audit_board(
                b2_path,
                schematic,
                board_path,
                netlist,
                netlist_evidence,
                cli_evidence,
                additional_board_only_refs,
            )
    except Exception as exc:  # fail closed with machine-readable evidence
        report = failure_report(
            b2_path,
            schematic,
            board_path,
            f"{type(exc).__name__}: {exc}",
        )
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
