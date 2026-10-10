#!/usr/bin/env python3
"""Build the staging-only MF1750 WROOM B3 R7 DRC-hygiene candidate.

The sole board input is the SHA-256-frozen R6 EPD-boundary candidate.  This
builder makes only three reviewed hygiene changes:

* hide the two reference fields that cross Edge.Cuts (J4 and J5);
* move exactly twenty left-edge switch body lines from F.SilkS to F.Fab; and
* give J4 pad 6 a local solid GND-zone connection so its thermal cannot starve.

The inherited /EPD_SW_3V3 dangling segment is deliberately preserved.  Its
open endpoint is the exact junction of a B2 /3V3 segment that the R3 migration
contract removed.  R6 already connects the retained segment to the switched
EPD supply, so reconnecting the obsolete endpoint would invent topology.  The
remaining dangling finding and the twelve ESP32-S3-WROOM 0.20 mm thermal-via
drills stay explicit HOLD items.

Only new R7 staging artifacts are written.  The formal project, formal PCB,
formal schematic, R6 board, prior reports, and prior previews are protected by
hash and are never output targets.  The board is built twice from fresh R6
loads, and publication occurs only after byte determinism, preservation,
project-verifier, fresh source/candidate DRC-delta, and render gates pass.

No hardware, network, serial port, flashing, or manufacturing action occurs.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover - exercised by wrong interpreter
    pcbnew = None  # type: ignore[assignment]
    PCBNEW_IMPORT_ERROR: Exception | None = exc
else:
    PCBNEW_IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r6_epd_boundary_routed.kicad_pcb"
SOURCE_BOARD_SHA256 = (
    "41fcea36a5ca4cc117b77fa02fb4d6332b248863ad82b5fe25c65b0aa72bcf28"
)
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
R3_BUILDER = HARDWARE / "build_mf1750_wroom_b3_board_r3.py"
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"
R6_CHAIN_AUDIT = STAGING / "r6_critical_route_chain_audit.json"
R6_DRC_EVIDENCE = STAGING / "r6_critical_route_chain_drc.json"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"
OUTPUT_REPORT = STAGING / "r7_drc_hygiene_report.json"
OUTPUT_DRC = STAGING / "r7_drc_hygiene_drc.json"
PREVIEW_DIR = STAGING / "r7_drc_hygiene_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_drc_hygiene_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_drc_hygiene_bottom.png"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
KICAD_PYTHON = Path(r"C:\Program Files\KiCad\10.0\bin\python.exe")

PROTECTED_HASHES = {
    SOURCE_BOARD: SOURCE_BOARD_SHA256,
    FORMAL_PROJECT: (
        "2fa48d53bc7875764500644c2d75c642fbe58eebc81b84eea6276bf937a9fe6c"
    ),
    FORMAL_SCHEMATIC: (
        "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0"
    ),
    FORMAL_BOARD: (
        "6da0e247e50ba4ce9ea984d6f0da72d98c1ac31544bf1aecbbb449bf3707e3a7"
    ),
    B2_BOARD: (
        "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
    ),
    R3_BUILDER: (
        "0f7f9cbda9262b632ccf14d7a6272ad42f2f69d901535d97fa69b745e4e47091"
    ),
    BOARD_VERIFIER: (
        "ebd591073b2d93e9a289e431312d9ba17f1dd96bafbd6bcd40b8c42341b72745"
    ),
    R6_CHAIN_AUDIT: (
        "55495428d70a992433f838267d793057ce37733c9ef2971148bd02776ee40bc7"
    ),
    R6_DRC_EVIDENCE: (
        "af73500847b8838aeada76bf1b82dd2a4ee3442ffe64fc114a8b01323e974214"
    ),
}

REFERENCE_FIELD_UUIDS = {
    "J4": "6d706ec7-cdc5-4f49-b01c-5921a02f077f",
    "J5": "9c5e06b8-30b4-41d7-b62f-bde5404d69cc",
}
BOARD_EDGE_UUID = "37a13e5b-025f-4a63-bf7c-3458e8d58e35"

SWITCH_SILK_UUIDS = {
    "SW1": frozenset(
        {
            "54c94e28-9933-43d5-9aa9-9843b180acab",
            "d85e9bd1-ca19-4097-95a5-a1e049ec5c01",
            "c0de1b49-ac0d-4258-b208-ffec5efaf390",
            "92738b1f-cafc-4513-8332-1c99612c62f0",
        }
    ),
    "SW2": frozenset(
        {
            "c4aee0ad-b778-4af9-b433-06b3f453418e",
            "c6075caa-8ea0-4f6f-9901-8ec35bd65539",
            "38cabba9-7181-47bd-8988-c210bc564aff",
            "75589cf0-f51d-4338-a1c5-3747b4271012",
        }
    ),
    "SW3": frozenset(
        {
            "90e15ff6-b5a4-4eba-9895-3efc0b4fbc20",
            "18c6fdd5-59e3-400f-9dda-e0b82fd523e7",
            "6437ddca-c5ff-472f-b014-da2578e74318",
            "f6bc9566-96c0-4542-b8d0-bf6a3f0fad44",
        }
    ),
    "SW4": frozenset(
        {
            "8e100f3b-a55e-477c-999b-f5cc16e3716b",
            "5cde0ca7-e9dd-49b1-a0f2-2035d448ddf7",
            "e67e8e40-a19b-4ea9-97ea-9bdfe21be8d0",
            "09b9ab33-e5fd-463f-9c19-fd633653dab7",
        }
    ),
    "SW5": frozenset(
        {
            "317afc97-7f26-43fb-8262-0c48caaad51e",
            "e70ea175-72f1-422f-9193-1221da520531",
            "d4178bd1-79e2-488f-a467-c3673670e461",
            "b2889173-0aa3-44b8-8623-26ce64868b77",
        }
    ),
}
ALL_SWITCH_SILK_UUIDS = frozenset().union(*SWITCH_SILK_UUIDS.values())

J4_PAD6_UUID = "7d16c3c2-8a2a-48ce-9c21-d6e28be1f13e"
DANGLING_TRACK_UUID = "c8fc1d9e-21d9-486f-b7f7-18ed683080f0"
REMOVED_B2_FEED_TRACK_UUID = "97f80bfc-b49e-4a41-a1d7-24d5ca5f256c"

U1_DRILL_UUIDS = frozenset(
    {
        "90b67840-18ec-4a80-ad73-3eb14b34fe7e",
        "b7397817-a58c-47ba-9f8d-753f8e2d918a",
        "fe2fa6b6-48d9-4886-adc6-360df953d381",
        "550f2ad6-752e-4464-b208-9da564c30b5c",
        "582c7976-29c6-4e1c-8923-97ddde7bed12",
        "ee5c33e1-63a4-4352-ade7-751fed350485",
        "06571243-6044-4fae-abf9-3f0628f12e42",
        "dfd2279a-1451-454b-ab36-f12724022c1c",
        "2ab2e01b-2077-4034-a28e-d80a44168f76",
        "60318589-e842-4069-964f-85c81be283fb",
        "840f4377-7168-47e2-aa96-ac2b3077c97b",
        "39cac4b3-1f2e-4962-a3d1-c07422cc59c2",
    }
)

EXPECTED_SOURCE_DRC = {
    "drill_out_of_range": 12,
    "silk_edge_clearance": 22,
    "starved_thermal": 1,
    "track_dangling": 1,
}
EXPECTED_CANDIDATE_DRC = {
    "drill_out_of_range": 12,
    "track_dangling": 1,
}


class HygieneError(RuntimeError):
    """Fail-closed R7 staging-builder error."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_command(
    command: list[str], cwd: Path, *, timeout_seconds: int = 300
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
    except subprocess.TimeoutExpired as exc:
        raise HygieneError(
            f"command timed out after {timeout_seconds}s: {command!r}"
        ) from exc


def item_uuid(item: Any) -> str:
    return str(item.m_Uuid.AsString())


def point_tuple(point: Any) -> tuple[int, int]:
    return int(point.x), int(point.y)


def point_mm(point: Any) -> tuple[float, float]:
    return round(pcbnew.ToMM(point.x), 6), round(pcbnew.ToMM(point.y), 6)


def natural_key(value: str) -> tuple[Any, ...]:
    parts: list[Any] = []
    current = ""
    numeric = False
    for character in value:
        if character.isdigit() == numeric:
            current += character
            continue
        if current:
            parts.append(int(current) if numeric else current.casefold())
        current = character
        numeric = character.isdigit()
    if current:
        parts.append(int(current) if numeric else current.casefold())
    return tuple(parts)


def assert_no_kicad_locks() -> list[str]:
    locks = sorted(
        str(path.resolve())
        for path in B3_DIR.rglob("~*.lck")
        if path.is_file()
    )
    if locks:
        raise HygieneError(f"KiCad lock files are present: {locks}")
    return locks


def assert_output_scope() -> None:
    outputs = {OUTPUT_BOARD, OUTPUT_REPORT, OUTPUT_DRC, OUTPUT_TOP, OUTPUT_BOTTOM}
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise HygieneError("R7 output paths alias")
    protected = {path.resolve() for path in PROTECTED_HASHES}
    aliases = sorted(str(path) for path in outputs if path.resolve() in protected)
    if aliases:
        raise HygieneError(f"R7 output aliases protected input: {aliases}")
    staging_root = STAGING.resolve()
    for path in outputs:
        if staging_root not in path.resolve().parents:
            raise HygieneError(f"R7 output escapes staging: {path}")


def protected_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for path, expected in PROTECTED_HASHES.items():
        if not path.is_file() or path.is_symlink():
            raise HygieneError(f"protected input is absent or symlinked: {path}")
        observed = sha256_file(path)
        if observed.casefold() != expected.casefold():
            raise HygieneError(
                f"protected hash mismatch for {path}: {observed} != {expected}"
            )
        result[str(path.resolve())] = observed
    return dict(sorted(result.items()))


def footprint_signature(footprint: Any) -> tuple[Any, ...]:
    position = footprint.GetPosition()
    return (
        item_uuid(footprint),
        footprint.GetReference(),
        footprint.GetFPID().GetUniStringLibId(),
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()), 6),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
        bool(footprint.IsLocked()),
    )


def pad_immutable_signature(pad: Any) -> tuple[Any, ...]:
    position = pad.GetPosition()
    relative = pad.GetFPRelativePosition()
    size = pad.GetSize()
    drill = pad.GetDrillSize()
    offset = pad.GetOffset()
    return (
        item_uuid(pad),
        pad.GetNumber(),
        pad.GetNetname(),
        tuple(int(layer) for layer in pad.GetLayerSet().Seq()),
        int(position.x),
        int(position.y),
        int(relative.x),
        int(relative.y),
        int(size.x),
        int(size.y),
        int(drill.x),
        int(drill.y),
        int(offset.x),
        int(offset.y),
        int(pad.GetShape()),
        int(pad.GetAttribute()),
        round(float(pad.GetOrientationDegrees()), 6),
    )


def track_signature(item: Any) -> tuple[Any, ...]:
    if isinstance(item, pcbnew.PCB_VIA):
        position = item.GetPosition()
        return (
            "via",
            item_uuid(item),
            item.GetNetname(),
            int(position.x),
            int(position.y),
            int(item.GetWidth(item.TopLayer())),
            int(item.GetDrillValue()),
            int(item.GetViaType()),
            int(item.TopLayer()),
            int(item.BottomLayer()),
        )
    start = item.GetStart()
    end = item.GetEnd()
    return (
        "track",
        item_uuid(item),
        item.GetNetname(),
        int(item.GetLayer()),
        int(start.x),
        int(start.y),
        int(end.x),
        int(end.y),
        int(item.GetWidth()),
    )


def polygon_points(poly_set: Any) -> tuple[tuple[tuple[int, int], ...], ...]:
    contours = []
    for index in range(poly_set.OutlineCount()):
        contour = poly_set.COutline(index)
        contours.append(
            tuple(
                point_tuple(contour.CPoint(point))
                for point in range(contour.PointCount())
            )
        )
    return tuple(contours)


def zone_signature(zone: Any) -> tuple[Any, ...]:
    return (
        item_uuid(zone),
        zone.GetZoneName(),
        zone.GetNetname(),
        int(zone.GetLayer()),
        tuple(int(layer) for layer in zone.GetLayerSet().Seq()),
        bool(zone.GetIsRuleArea()),
        int(zone.GetAssignedPriority()),
        int(zone.GetLocalClearance()),
        int(zone.GetMinThickness()),
        int(zone.GetThermalReliefGap()),
        int(zone.GetThermalReliefSpokeWidth()),
        int(zone.GetPadConnection()),
        polygon_points(zone.Outline()),
    )


def bounding_box_signature(item: Any) -> tuple[int, int, int, int]:
    box = item.GetBoundingBox()
    return int(box.GetX()), int(box.GetY()), int(box.GetWidth()), int(box.GetHeight())


def graphic_signature(item: Any) -> tuple[Any, ...]:
    common: list[Any] = [
        item_uuid(item),
        type(item).__name__,
        int(item.GetLayer()),
        bounding_box_signature(item),
    ]
    if isinstance(item, pcbnew.PCB_SHAPE):
        common.extend(
            [
                int(item.GetShape()),
                point_tuple(item.GetStart()),
                point_tuple(item.GetEnd()),
                int(item.GetWidth()),
            ]
        )
    elif isinstance(item, pcbnew.PCB_TEXT):
        position = item.GetPosition()
        size = item.GetTextSize()
        common.extend(
            [
                item.GetText(),
                int(position.x),
                int(position.y),
                round(float(item.GetTextAngleDegrees()), 6),
                int(size.x),
                int(size.y),
                int(item.GetTextThickness()),
                bool(item.IsVisible()),
                bool(item.IsMirrored()),
            ]
        )
    return tuple(common)


def reference_signature(field: Any) -> tuple[Any, ...]:
    position = field.GetPosition()
    size = field.GetTextSize()
    return (
        item_uuid(field),
        field.GetText(),
        int(field.GetLayer()),
        int(position.x),
        int(position.y),
        round(float(field.GetTextAngleDegrees()), 6),
        int(size.x),
        int(size.y),
        int(field.GetTextThickness()),
        bool(field.IsVisible()),
        bool(field.IsMirrored()),
    )


def board_state(board: Any) -> dict[str, Any]:
    footprints = sorted(board.GetFootprints(), key=lambda fp: natural_key(fp.GetReference()))
    return {
        "footprints": {
            footprint.GetReference(): footprint_signature(footprint)
            for footprint in footprints
        },
        "pads": {
            (footprint.GetReference(), item_uuid(pad)): pad_immutable_signature(pad)
            for footprint in footprints
            for pad in footprint.Pads()
        },
        "pad_zone_connections": {
            (footprint.GetReference(), item_uuid(pad)): int(
                pad.GetLocalZoneConnection()
            )
            for footprint in footprints
            for pad in footprint.Pads()
        },
        "references": {
            footprint.GetReference(): reference_signature(footprint.Reference())
            for footprint in footprints
        },
        "graphics": {
            item_uuid(item): (footprint.GetReference(), graphic_signature(item))
            for footprint in footprints
            for item in footprint.GraphicalItems()
        },
        "tracks": {
            item_uuid(item): track_signature(item) for item in board.GetTracks()
        },
        "zones": {item_uuid(zone): zone_signature(zone) for zone in board.Zones()},
        "drawings": {
            item_uuid(item): (
                type(item).__name__,
                int(item.GetLayer()),
                bounding_box_signature(item),
            )
            for item in board.Drawings()
        },
        "children": {
            footprint.GetReference(): {
                "pads": tuple(sorted(item_uuid(pad) for pad in footprint.Pads())),
                "graphics": tuple(
                    sorted(item_uuid(item) for item in footprint.GraphicalItems())
                ),
                "zones": tuple(sorted(item_uuid(zone) for zone in footprint.Zones())),
            }
            for footprint in footprints
        },
    }


def find_pad(board: Any, reference: str, number: str) -> Any:
    footprint = board.FindFootprintByReference(reference)
    if footprint is None:
        raise HygieneError(f"missing footprint {reference}")
    pads = [pad for pad in footprint.Pads() if pad.GetNumber() == number]
    if len(pads) != 1:
        raise HygieneError(f"{reference}.{number} pad cardinality differs")
    return pads[0]


def apply_hygiene(board: Any) -> dict[str, Any]:
    references = []
    for reference, expected_uuid in sorted(REFERENCE_FIELD_UUIDS.items()):
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise HygieneError(f"missing reference-field footprint {reference}")
        field = footprint.Reference()
        if item_uuid(field) != expected_uuid:
            raise HygieneError(f"{reference} reference-field UUID differs")
        if field.GetLayer() != pcbnew.F_SilkS or not field.IsVisible():
            raise HygieneError(f"{reference} source reference field is not visible F.SilkS")
        before = point_mm(field.GetPosition())
        field.SetVisible(False)
        references.append(
            {
                "reference": reference,
                "uuid": expected_uuid,
                "position_mm": list(before),
                "action": "hidden_without_moving_footprint",
            }
        )

    moved_graphics = []
    for reference, expected_uuids in sorted(SWITCH_SILK_UUIDS.items()):
        footprint = board.FindFootprintByReference(reference)
        if footprint is None:
            raise HygieneError(f"missing switch footprint {reference}")
        graphics = {item_uuid(item): item for item in footprint.GraphicalItems()}
        if not expected_uuids.issubset(graphics):
            raise HygieneError(f"{reference} reviewed silk UUID set differs")
        for uuid in sorted(expected_uuids):
            item = graphics[uuid]
            if not isinstance(item, pcbnew.PCB_SHAPE):
                raise HygieneError(f"{reference} reviewed silk item is not PCB_SHAPE")
            if item.GetLayer() != pcbnew.F_SilkS:
                raise HygieneError(f"{reference} reviewed silk item is not F.SilkS")
            before_box = bounding_box_signature(item)
            item.SetLayer(pcbnew.F_Fab)
            moved_graphics.append(
                {
                    "reference": reference,
                    "uuid": uuid,
                    "from": "F.SilkS",
                    "to": "F.Fab",
                    "geometry_iu": list(before_box),
                }
            )

    pad = find_pad(board, "J4", "6")
    if item_uuid(pad) != J4_PAD6_UUID or pad.GetNetname() != "GND":
        raise HygieneError("J4.6 identity/net differs")
    before_zone_connection = int(pad.GetLocalZoneConnection())
    if before_zone_connection != int(pcbnew.ZONE_CONNECTION_INHERITED):
        raise HygieneError("J4.6 source zone connection is not inherited")
    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    title = board.GetTitleBlock()
    title.SetTitle("MF1750 WROOM B3 R7 DRC hygiene candidate")
    title.SetRevision("B3-WROOM-POWER-TF-R7-DRC-HYGIENE")
    title.SetComment(
        0, "SILK+J4 THERMAL HYGIENE ONLY; U1 DRILLS/DANGLING/ROUTING HOLD"
    )
    title.SetComment(1, f"Source R6 SHA256 {SOURCE_BOARD_SHA256}")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return {
        "reference_fields": references,
        "switch_graphics": moved_graphics,
        "j4_pad6": {
            "reference": "J4",
            "pad": "6",
            "uuid": J4_PAD6_UUID,
            "net": "GND",
            "position_mm": list(point_mm(pad.GetPosition())),
            "before_local_zone_connection": before_zone_connection,
            "after_local_zone_connection": int(pad.GetLocalZoneConnection()),
            "after_name": "ZONE_CONNECTION_FULL",
        },
    }


def compare_states(source: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "footprints_unchanged": source["footprints"] == candidate["footprints"],
        "pad_geometry_net_and_identity_unchanged": source["pads"] == candidate["pads"],
        "all_existing_tracks_and_vias_unchanged": source["tracks"]
        == candidate["tracks"],
        "zone_definitions_and_outlines_unchanged": source["zones"]
        == candidate["zones"],
        "board_drawings_unchanged": source["drawings"] == candidate["drawings"],
        "footprint_child_uuid_sets_unchanged": source["children"]
        == candidate["children"],
    }

    pad_zone_changes = {
        key: (source["pad_zone_connections"][key], candidate["pad_zone_connections"][key])
        for key in source["pad_zone_connections"]
        if source["pad_zone_connections"][key]
        != candidate["pad_zone_connections"][key]
    }
    expected_pad_key = ("J4", J4_PAD6_UUID)
    checks["only_j4_pad6_zone_connection_changed"] = pad_zone_changes == {
        expected_pad_key: (
            int(pcbnew.ZONE_CONNECTION_INHERITED),
            int(pcbnew.ZONE_CONNECTION_FULL),
        )
    }

    reference_changes = {}
    for reference in source["references"]:
        before = source["references"][reference]
        after = candidate["references"][reference]
        if before != after:
            reference_changes[reference] = (before, after)
    reference_ok = set(reference_changes) == set(REFERENCE_FIELD_UUIDS)
    for reference, (before, after) in reference_changes.items():
        reference_ok = reference_ok and before[:-2] == after[:-2]
        reference_ok = reference_ok and before[-2:] == (True, False)
        reference_ok = reference_ok and after[-2:] == (False, False)
    checks["only_j4_j5_reference_visibility_changed"] = reference_ok

    graphic_changes = {}
    for uuid in source["graphics"]:
        before = source["graphics"][uuid]
        after = candidate["graphics"][uuid]
        if before != after:
            graphic_changes[uuid] = (before, after)
    graphics_ok = set(graphic_changes) == set(ALL_SWITCH_SILK_UUIDS)
    for uuid, (before, after) in graphic_changes.items():
        before_ref, before_signature = before
        after_ref, after_signature = after
        graphics_ok = graphics_ok and before_ref == after_ref
        graphics_ok = graphics_ok and before_signature[0:2] == after_signature[0:2]
        graphics_ok = graphics_ok and before_signature[2] == int(pcbnew.F_SilkS)
        graphics_ok = graphics_ok and after_signature[2] == int(pcbnew.F_Fab)
        graphics_ok = graphics_ok and before_signature[3:] == after_signature[3:]
    checks["only_reviewed_switch_silk_layers_changed"] = graphics_ok

    checks["all_preservation_checks_pass"] = all(checks.values())
    return {
        "passed": checks["all_preservation_checks_pass"],
        "checks": checks,
        "counts": {
            "footprints": len(candidate["footprints"]),
            "pads": len(candidate["pads"]),
            "tracks_and_vias": len(candidate["tracks"]),
            "zones": len(candidate["zones"]),
            "drawings": len(candidate["drawings"]),
            "reference_field_changes": len(reference_changes),
            "footprint_graphic_changes": len(graphic_changes),
            "pad_zone_connection_changes": len(pad_zone_changes),
        },
        "changed_reference_fields": sorted(reference_changes),
        "changed_graphic_uuids": sorted(graphic_changes),
        "pad_zone_changes": [
            {
                "reference": key[0],
                "pad_uuid": key[1],
                "before": values[0],
                "after": values[1],
            }
            for key, values in sorted(pad_zone_changes.items())
        ],
    }


def build_once(destination: Path) -> dict[str, Any]:
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise HygieneError("pcbnew could not load frozen R6 board")
    source_state = board_state(board)
    changes = apply_hygiene(board)
    pcbnew.SaveBoard(str(destination), board)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise HygieneError("pcbnew did not save R7 candidate")
    reloaded = pcbnew.LoadBoard(str(destination.resolve()))
    if reloaded is None:
        raise HygieneError("pcbnew could not reload R7 candidate")
    candidate_state = board_state(reloaded)
    preservation = compare_states(source_state, candidate_state)
    if preservation["passed"] is not True:
        raise HygieneError("R7 footprint/pad/copper preservation gate failed")
    j4 = find_pad(reloaded, "J4", "6")
    if int(j4.GetLocalZoneConnection()) != int(pcbnew.ZONE_CONNECTION_FULL):
        raise HygieneError("R7 J4.6 solid-zone override did not persist")
    return {
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "changes": changes,
        "preservation": preservation,
    }


def copy_validation_context(temp_dir: Path, board_source: Path) -> tuple[Path, Path]:
    stem = "mf1750_wroom_b3_power_tf"
    board_path = temp_dir / f"{stem}.kicad_pcb"
    shutil.copy2(board_source, board_path)
    shutil.copy2(FORMAL_SCHEMATIC, temp_dir / f"{stem}.kicad_sch")
    shutil.copy2(FORMAL_PROJECT, temp_dir / f"{stem}.kicad_pro")
    for table_name in ("fp-lib-table", "sym-lib-table"):
        source = B3_DIR / table_name
        if source.is_file():
            shutil.copy2(source, temp_dir / table_name)
    for library_name in ("b3_wroom_symbols.kicad_sym", "mf1750_local.kicad_sym"):
        source = B3_DIR / library_name
        if source.is_file():
            shutil.copy2(source, temp_dir / library_name)
    for directory_name in (
        "b3_wroom_footprints.pretty",
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
    ):
        source = B3_DIR / directory_name
        if source.is_dir():
            shutil.copytree(source, temp_dir / directory_name)
    return board_path, temp_dir / "drc.json"


def run_drc(board_source: Path, prefix: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        temp_dir = Path(directory)
        board_path, report_path = copy_validation_context(temp_dir, board_source)
        command = [
            str(KICAD_CLI),
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
        completed = run_command(command, temp_dir)
        if completed.returncode != 0 or not report_path.is_file():
            raise HygieneError(
                "KiCad DRC failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        raw_bytes = report_path.read_bytes()
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HygieneError("KiCad DRC report is not UTF-8 JSON") from exc
    categories = collections.Counter(
        str(item.get("type")) for item in raw.get("violations", [])
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "kicad_version": raw.get("kicad_version"),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "violation_count": len(raw.get("violations", [])),
        "violation_categories": dict(sorted(categories.items())),
        "unconnected_count": len(raw.get("unconnected_items", [])),
        "schematic_parity_count": len(raw.get("schematic_parity", [])),
        "raw": raw,
    }


def violation_item_uuids(violation: Mapping[str, Any]) -> set[str]:
    items = violation.get("items")
    if isinstance(items, Mapping):
        uuid = items.get("uuid")
        return {str(uuid)} if isinstance(uuid, str) else set()
    if isinstance(items, list):
        return {
            str(item["uuid"])
            for item in items
            if isinstance(item, Mapping) and isinstance(item.get("uuid"), str)
        }
    return set()


def validate_source_drc(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("violation_categories") != EXPECTED_SOURCE_DRC:
        raise HygieneError("fresh R6 source DRC categories differ from frozen contract")
    if value.get("unconnected_count") != 141 or value.get("schematic_parity_count") != 0:
        raise HygieneError("fresh R6 source DRC count/parity differs")
    violations = value["raw"]["violations"]
    drill_items = [
        violation_item_uuids(item)
        for item in violations
        if item.get("type") == "drill_out_of_range"
    ]
    drill = set().union(*drill_items)
    silk_items = [
        violation_item_uuids(item)
        for item in violations
        if item.get("type") == "silk_edge_clearance"
    ]
    silk = set().union(*silk_items)
    starved = set().union(
        *(
            violation_item_uuids(item)
            for item in violations
            if item.get("type") == "starved_thermal"
        )
    )
    dangling = set().union(
        *(
            violation_item_uuids(item)
            for item in violations
            if item.get("type") == "track_dangling"
        )
    )
    expected_silk = set(ALL_SWITCH_SILK_UUIDS) | set(REFERENCE_FIELD_UUIDS.values())
    checks = {
        "u1_drill_uuid_set_exact": drill == set(U1_DRILL_UUIDS)
        and all(len(item) == 1 for item in drill_items),
        "silk_uuid_set_exact": silk == expected_silk | {BOARD_EDGE_UUID}
        and all(
            len(item) == 2
            and BOARD_EDGE_UUID in item
            and len(item & expected_silk) == 1
            for item in silk_items
        ),
        "starved_thermal_is_exact_j4_pad6": J4_PAD6_UUID in starved
        and len(starved) == 2,
        "dangling_track_uuid_exact": dangling == {DANGLING_TRACK_UUID},
    }
    if not all(checks.values()):
        detail = {
            "checks": checks,
            "drill_actual": sorted(drill),
            "drill_expected": sorted(U1_DRILL_UUIDS),
            "silk_actual": sorted(silk),
            "silk_expected_with_edge": sorted(expected_silk | {BOARD_EDGE_UUID}),
        }
        raise HygieneError(f"fresh R6 source DRC identity differs: {detail}")
    return {"passed": True, "checks": checks}


def validate_candidate_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    if candidate.get("violation_categories") != EXPECTED_CANDIDATE_DRC:
        raise HygieneError("R7 DRC contains unexpected or unresolved hygiene categories")
    if candidate.get("unconnected_count") != source.get("unconnected_count"):
        raise HygieneError("R7 unconnected count changed")
    if candidate.get("schematic_parity_count") != 0:
        raise HygieneError("R7 schematic parity is nonzero")
    violations = candidate["raw"]["violations"]
    drill = set().union(
        *(
            violation_item_uuids(item)
            for item in violations
            if item.get("type") == "drill_out_of_range"
        )
    )
    dangling = set().union(
        *(
            violation_item_uuids(item)
            for item in violations
            if item.get("type") == "track_dangling"
        )
    )
    checks = {
        "source_parity_zero": source.get("schematic_parity_count") == 0,
        "candidate_parity_zero": candidate.get("schematic_parity_count") == 0,
        "unconnected_unchanged_141": candidate.get("unconnected_count") == 141,
        "silk_edge_zero": candidate["violation_categories"].get(
            "silk_edge_clearance", 0
        )
        == 0,
        "starved_thermal_zero": candidate["violation_categories"].get(
            "starved_thermal", 0
        )
        == 0,
        "u1_drill_hold_exactly_12": drill == set(U1_DRILL_UUIDS),
        "preserved_dangling_hold_exactly_one": dangling
        == {DANGLING_TRACK_UUID},
        "no_new_drc_category": set(candidate["violation_categories"])
        <= set(source["violation_categories"]),
        "violation_delta_exactly_minus_23": candidate.get("violation_count")
        == source.get("violation_count") - 23,
    }
    if not all(checks.values()):
        raise HygieneError(f"R7 DRC delta gate failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "source_categories": source["violation_categories"],
        "candidate_categories": candidate["violation_categories"],
        "category_delta": {
            name: candidate["violation_categories"].get(name, 0)
            - source["violation_categories"].get(name, 0)
            for name in sorted(
                set(source["violation_categories"])
                | set(candidate["violation_categories"])
            )
        },
        "source_violation_count": source["violation_count"],
        "candidate_violation_count": candidate["violation_count"],
        "unconnected_count": candidate["unconnected_count"],
        "schematic_parity_count": candidate["schematic_parity_count"],
    }


def run_board_verifier(candidate: Path) -> dict[str, Any]:
    before = sha256_file(candidate)
    command = [
        str(KICAD_PYTHON),
        str(BOARD_VERIFIER),
        str(candidate.resolve()),
        "--schematic",
        str(FORMAL_SCHEMATIC.resolve()),
        "--b2",
        str(B2_BOARD.resolve()),
        "--kicad-cli",
        str(KICAD_CLI.resolve()),
        "--allow-board-only",
        "H3",
        "--allow-board-only",
        "H4",
    ]
    completed = run_command(command, ROOT)
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HygieneError("project board verifier did not return JSON") from exc
    summary = report.get("summary", {})
    if (
        completed.returncode != 0
        or report.get("passed") is not True
        or summary.get("total") != 13
        or summary.get("passed") != 13
        or summary.get("failed") != 0
    ):
        raise HygieneError(
            "project board verifier failed: "
            + (completed.stderr.strip() or completed.stdout[-2000:])
        )
    if any(
        report.get(key) is not False
        for key in ("hardware_accessed", "boards_modified", "schematics_modified")
    ):
        raise HygieneError("project board verifier mutation/access flags differ")
    selected = report.get("inputs", {}).get("staging_r3_pcb", {})
    if (
        Path(str(selected.get("path", ""))).resolve() != candidate.resolve()
        or str(selected.get("sha256", "")).casefold() != before
    ):
        raise HygieneError("project board verifier is not candidate-hash bound")
    after = sha256_file(candidate)
    if after != before:
        raise HygieneError("project board verifier changed R7 candidate")
    return {
        "passed": True,
        "command": command,
        "summary": summary,
        "candidate_sha256_before": before,
        "candidate_sha256_after": after,
        "report": report,
    }


def render(candidate: Path, side: str, destination: Path, temp_dir: Path) -> bytes:
    output = temp_dir / destination.name
    command = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--side",
        side,
        "--background",
        "opaque",
        "--quality",
        "high",
        "--width",
        "1800",
        "--height",
        "1600",
        "--output",
        str(output),
        str(candidate.resolve()),
    ]
    completed = run_command(command, temp_dir)
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise HygieneError(
            f"{side} preview failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    return output.read_bytes()


def endpoint_evidence() -> dict[str, Any]:
    source = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    b2 = pcbnew.LoadBoard(str(B2_BOARD.resolve()))
    if source is None or b2 is None:
        raise HygieneError("could not load source/B2 board for endpoint proof")

    def track_map(board: Any) -> dict[str, Any]:
        return {item_uuid(item): item for item in board.GetTracks()}

    source_tracks = track_map(source)
    b2_tracks = track_map(b2)
    retained = source_tracks.get(DANGLING_TRACK_UUID)
    old_retained = b2_tracks.get(DANGLING_TRACK_UUID)
    removed_feed = b2_tracks.get(REMOVED_B2_FEED_TRACK_UUID)
    if retained is None or old_retained is None or removed_feed is None:
        raise HygieneError("dangling endpoint provenance tracks are absent")
    if REMOVED_B2_FEED_TRACK_UUID in source_tracks:
        raise HygieneError("R3-removed B2 feed unexpectedly exists in R6")

    expected_endpoint = (12.0, 10.5)
    source_endpoints = {point_mm(retained.GetStart()), point_mm(retained.GetEnd())}
    b2_retained_endpoints = {
        point_mm(old_retained.GetStart()),
        point_mm(old_retained.GetEnd()),
    }
    removed_endpoints = {
        point_mm(removed_feed.GetStart()),
        point_mm(removed_feed.GetEnd()),
    }
    if (
        expected_endpoint not in source_endpoints
        or source_endpoints != b2_retained_endpoints
        or expected_endpoint not in removed_endpoints
        or retained.GetNetname() != "/EPD_SW_3V3"
        or old_retained.GetNetname() != "/3V3"
        or removed_feed.GetNetname() != "/3V3"
        or retained.GetLayer() != pcbnew.In2_Cu
        or removed_feed.GetLayer() != pcbnew.In2_Cu
    ):
        raise HygieneError("dangling endpoint geometry/net migration proof differs")

    endpoint_contacts = []
    for item in source.GetTracks():
        if item_uuid(item) == DANGLING_TRACK_UUID:
            continue
        points = {point_mm(item.GetStart()), point_mm(item.GetEnd())}
        if expected_endpoint in points:
            endpoint_contacts.append(item_uuid(item))
    endpoint_pads = []
    for footprint in source.GetFootprints():
        for pad in footprint.Pads():
            if point_mm(pad.GetPosition()) == expected_endpoint:
                endpoint_pads.append(
                    {
                        "reference": footprint.GetReference(),
                        "pad": pad.GetNumber(),
                        "uuid": item_uuid(pad),
                        "net": pad.GetNetname(),
                    }
                )
    if endpoint_contacts or endpoint_pads:
        raise HygieneError("R6 dangling endpoint unexpectedly has a present target")

    source.BuildConnectivity()
    connected = list(source.GetConnectivity().GetConnectedItems(retained))
    connected_pads = sorted(
        {
            (
                item.GetParentFootprint().GetReference(),
                item.GetNumber(),
                item.GetNetname(),
            )
            for item in connected
            if isinstance(item, pcbnew.PAD)
        }
    )
    required_live_pads = {
        ("U5", "5", "/EPD_SW_3V3"),
        ("R4", "1", "/EPD_SW_3V3"),
        ("R8", "1", "/EPD_SW_3V3"),
    }
    if not required_live_pads.issubset(set(connected_pads)):
        raise HygieneError("retained EPD switched-supply trunk is not live-connected")

    builder_text = R3_BUILDER.read_text(encoding="utf-8")
    if (
        f'"{REMOVED_B2_FEED_TRACK_UUID}": {{' not in builder_text
        or '"net": "/3V3"' not in builder_text
        or '"anchor_mm": (12.0, 10.5)' not in builder_text
        or '"layer": "In2.Cu"' not in builder_text
    ):
        raise HygieneError("R3 explicit removed-feed contract text differs")
    return {
        "passed": True,
        "retained_track": {
            "uuid": DANGLING_TRACK_UUID,
            "r6_net": retained.GetNetname(),
            "b2_net": old_retained.GetNetname(),
            "layer": pcbnew.LayerName(retained.GetLayer()),
            "endpoints_mm": [list(point) for point in sorted(source_endpoints)],
        },
        "removed_b2_feed": {
            "uuid": REMOVED_B2_FEED_TRACK_UUID,
            "net": removed_feed.GetNetname(),
            "layer": pcbnew.LayerName(removed_feed.GetLayer()),
            "endpoints_mm": [list(point) for point in sorted(removed_endpoints)],
            "explicit_r3_exemption_contract": True,
            "absent_from_r6": True,
        },
        "open_endpoint_mm": list(expected_endpoint),
        "r6_other_copper_at_open_endpoint": endpoint_contacts,
        "r6_pads_at_open_endpoint": endpoint_pads,
        "retained_track_live_connected_pads": [list(item) for item in connected_pads],
        "decision": "PRESERVE_SOURCE_COPPER_NO_SAFE_RECONNECTION",
        "reason": (
            "the open endpoint belonged to an explicitly removed external /3V3 "
            "feed; the retained trunk is already supplied by U5, and no current "
            "R6 pad or copper endpoint exists at the old junction"
        ),
        "hold": True,
        "source_copper_deleted": False,
        "new_copper_added": False,
    }


def artifact_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run every gate but do not publish the five R7 staging artifacts",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    script_hash_before = sha256_file(Path(__file__).resolve())
    report: dict[str, Any]
    try:
        if pcbnew is None:
            raise HygieneError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise HygieneError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not KICAD_CLI.is_file() or not KICAD_PYTHON.is_file():
            raise HygieneError("fixed KiCad 10 CLI/Python is absent")
        assert_output_scope()
        assert_no_kicad_locks()
        protected_before = protected_hashes()
        endpoint = endpoint_evidence()

        with tempfile.TemporaryDirectory(prefix="mf1750-r7-drc-hygiene-") as name:
            temp_dir = Path(name)
            first = temp_dir / "run1.kicad_pcb"
            second = temp_dir / "run2.kicad_pcb"
            first_result = build_once(first)
            second_result = build_once(second)
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
            deterministic = {
                "passed": first_bytes == second_bytes,
                "run1": {
                    "bytes": len(first_bytes),
                    "sha256": sha256_bytes(first_bytes),
                },
                "run2": {
                    "bytes": len(second_bytes),
                    "sha256": sha256_bytes(second_bytes),
                },
            }
            if deterministic["passed"] is not True:
                raise HygieneError("R7 double build is not byte deterministic")
            if first_result["preservation"] != second_result["preservation"]:
                raise HygieneError("R7 double-build preservation evidence differs")
            if first_result["changes"] != second_result["changes"]:
                raise HygieneError("R7 double-build change evidence differs")

            source_drc = run_drc(SOURCE_BOARD, "mf1750-r7-source-drc-")
            source_drc_identity = validate_source_drc(source_drc)
            candidate_drc = run_drc(first, "mf1750-r7-candidate-drc-")
            drc_delta = validate_candidate_drc(source_drc, candidate_drc)
            verifier = run_board_verifier(first)
            top_bytes = render(first, "top", OUTPUT_TOP, temp_dir)
            bottom_bytes = render(first, "bottom", OUTPUT_BOTTOM, temp_dir)

            candidate_drc_bytes = json_bytes(candidate_drc["raw"])
            artifacts = {
                "board": artifact_record(OUTPUT_BOARD, first_bytes),
                "drc": artifact_record(OUTPUT_DRC, candidate_drc_bytes),
                "top": artifact_record(OUTPUT_TOP, top_bytes),
                "bottom": artifact_record(OUTPUT_BOTTOM, bottom_bytes),
            }
            script_hash_after = sha256_file(Path(__file__).resolve())
            if script_hash_after != script_hash_before:
                raise HygieneError("R7 builder changed while running")
            protected_after = protected_hashes()
            if protected_after != protected_before:
                raise HygieneError("protected input changed while building R7")
            assert_no_kicad_locks()

            report = {
                "schema": 1,
                "tool": "build_mf1750_wroom_b3_r7_drc_hygiene.py",
                "mode": "STAGING_ONLY_REVISION",
                "state": "R7_DRC_HYGIENE_CANDIDATE_HOLD",
                "overall_status": "HOLD",
                "operation_completed": True,
                "locally_verified": False,
                "manufacturing_release": False,
                "hardware_accessed": False,
                "network_accessed": False,
                "serial_or_com_accessed": False,
                "formal_project_modified": False,
                "formal_schematic_modified": False,
                "formal_board_modified": False,
                "r6_source_modified": False,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "kicad": {
                    "pcbnew": str(pcbnew.GetBuildVersion()),
                    "cli": str(KICAD_CLI.resolve()),
                    "python": str(KICAD_PYTHON.resolve()),
                },
                "builder": {
                    "path": str(Path(__file__).resolve()),
                    "sha256_before": script_hash_before,
                    "sha256_after": script_hash_after,
                    "unchanged": True,
                },
                "source": {
                    "path": str(SOURCE_BOARD.resolve()),
                    "bytes": SOURCE_BOARD.stat().st_size,
                    "sha256": SOURCE_BOARD_SHA256,
                    "fixed_input": True,
                },
                "protected_hashes_before": protected_before,
                "protected_hashes_after": protected_after,
                "protected_hashes_unchanged": True,
                "locks": [],
                "changes": first_result["changes"],
                "preservation": first_result["preservation"],
                "endpoint_proof": endpoint,
                "determinism": deterministic,
                "source_drc_identity": source_drc_identity,
                "drc": {
                    "source": {
                        key: value
                        for key, value in source_drc.items()
                        if key != "raw"
                    },
                    "candidate": {
                        key: value
                        for key, value in candidate_drc.items()
                        if key != "raw"
                    },
                    "delta_gate": drc_delta,
                },
                "project_board_verifier": verifier,
                "artifacts": artifacts,
                "holds": [
                    "12 U1 ESP32-S3-WROOM pad-41 thermal drills remain 0.20 mm; final fabricator drill capability/footprint strategy is HOLD",
                    "the preserved /EPD_SW_3V3 dangling endpoint has no current target; reconnecting or deleting inherited copper without new authority is HOLD",
                    "141 unconnected items remain; whole-board routing is incomplete",
                    "stackup/USB impedance, current/thermal, enclosure, assembly, battery connector/pack/NTC, and manufacturing release remain HOLD",
                ],
                "completed_scope": [
                    "22 source silk_edge_clearance findings reduced to zero",
                    "J4 pad 6 starved_thermal finding reduced to zero by local solid GND-zone connection",
                    "source footprint placement, pad geometry/net/identity, every track/via, and every zone definition preserved",
                    "schematic parity remains zero and unconnected count remains exactly 141",
                ],
                "check_only": bool(args.check_only),
            }
            report_bytes = json_bytes(report)
            report["artifacts"]["report"] = {
                "path": str(OUTPUT_REPORT.resolve()),
                "bytes_without_self_record": len(report_bytes),
                "self_hash_intentionally_omitted": True,
            }
            report_bytes = json_bytes(report)

            if not args.check_only:
                atomic_write_bytes(OUTPUT_BOARD, first_bytes)
                atomic_write_bytes(OUTPUT_DRC, candidate_drc_bytes)
                atomic_write_bytes(OUTPUT_TOP, top_bytes)
                atomic_write_bytes(OUTPUT_BOTTOM, bottom_bytes)
                atomic_write_bytes(OUTPUT_REPORT, report_bytes)
                published = {
                    "board": sha256_file(OUTPUT_BOARD),
                    "drc": sha256_file(OUTPUT_DRC),
                    "top": sha256_file(OUTPUT_TOP),
                    "bottom": sha256_file(OUTPUT_BOTTOM),
                }
                expected = {
                    key: value["sha256"]
                    for key, value in artifacts.items()
                    if key != "report"
                }
                if published != expected:
                    raise HygieneError("published R7 artifact hash differs")
                if protected_hashes() != protected_before:
                    raise HygieneError("protected input changed during publication")

        summary = {
            "state": report["state"],
            "overall_status": report["overall_status"],
            "board": report["artifacts"]["board"],
            "drc": report["drc"]["candidate"],
            "deterministic": report["determinism"]["passed"],
            "preservation_passed": report["preservation"]["passed"],
            "project_board_verifier": report["project_board_verifier"]["summary"],
            "check_only": bool(args.check_only),
        }
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return 0
    except Exception as exc:
        failure = {
            "schema": 1,
            "tool": "build_mf1750_wroom_b3_r7_drc_hygiene.py",
            "state": "R7_DRC_HYGIENE_BUILD_FAILED_HOLD",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        sys.stdout.write(json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
