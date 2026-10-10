#!/usr/bin/env python3
"""Build the staging-only MF1750 WROOM B3 R7 edge-access probe.

The sole PCB input is the SHA-256-frozen R7 DRC-hygiene board.  This probe is
deliberately narrow:

* SW1..SW5 keep their centres and rotate from 90 to 270 degrees;
* J5 moves to (3.65, 108.70) mm and rotates to 270 degrees;
* J6 moves to (14.75, 120.00) mm and rotates to 0 degrees;
* all eight source /USB_VBUS tracks are removed by exact UUID and rebuilt on
  F.Cu from the two relocated J5 VBUS pad pairs to F1.1.

The 28 exact F.SilkS graphics that newly cross Edge.Cuts after those rigid
placements move to F.Fab, and the four exact J5 GND pads use a local solid
zone connection.  No /USB_SHIELD pad is changed.

Every non-allowlisted footprint, retained track/via, pad-local definition,
zone definition, and board drawing is preserved.  Publication is fail-closed
behind exact source hashes, a byte-identical double build, project verifier
13/13, fresh DRC identity, schematic parity zero, and an unconnected count of
exactly 139 with a per-net GND-only delta from source 141.  J6 remains a reversible placement candidate: connector, battery
pack, and line-order authority are explicitly still HOLD.

Only new staging artifacts are written.  The formal project, formal PCB,
formal schematic, R7 source, README files, and hardware are not modified or
accessed.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable, Mapping

import build_mf1750_wroom_b3_r7_drc_hygiene as r7base


pcbnew = r7base.pcbnew
PCBNEW_IMPORT_ERROR = r7base.PCBNEW_IMPORT_ERROR

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
B3_DIR = HARDWARE / "mf1750_wroom_b3_power_tf"
STAGING = B3_DIR / "staging"

SOURCE_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_drc_hygiene.kicad_pcb"
SOURCE_BOARD_SHA256 = (
    "88dfc906bd8d15adccecc54ccdbb9a6d2e5f1ec3149ede199475923ba22c1cf8"
)
FORMAL_PROJECT = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pro"
FORMAL_SCHEMATIC = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_sch"
FORMAL_BOARD = B3_DIR / "mf1750_wroom_b3_power_tf.kicad_pcb"
B2_BOARD = (
    HARDWARE
    / "mf1750_devkitc_b2_pcba_margin"
    / "mf1750_devkitc_b2_pcba_margin.kicad_pcb"
)
BOARD_VERIFIER = HARDWARE / "verify_mf1750_wroom_b3_board_r3.py"
R7_HELPER = HARDWARE / "build_mf1750_wroom_b3_r7_drc_hygiene.py"

OUTPUT_BOARD = STAGING / "mf1750_wroom_b3_power_tf_r7_edge_access_probe.kicad_pcb"
OUTPUT_REPORT = STAGING / "r7_edge_access_probe_report.json"
OUTPUT_DRC = STAGING / "r7_edge_access_probe_drc.json"
PREVIEW_DIR = STAGING / "r7_edge_access_probe_preview"
OUTPUT_TOP = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_edge_access_probe_top.png"
OUTPUT_BOTTOM = PREVIEW_DIR / "mf1750_wroom_b3_power_tf_r7_edge_access_probe_bottom.png"

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
    BOARD_VERIFIER: (
        "ebd591073b2d93e9a289e431312d9ba17f1dd96bafbd6bcd40b8c42341b72745"
    ),
    R7_HELPER: (
        "a7cedba80c44cb52e4b18e62eeff2a3eab258c170b2708de2903b7dcfbe19b3a"
    ),
}

SOURCE_PLACEMENTS = {
    "SW1": ("636bc522-8ef6-4608-bdc3-06dfe5d0a17b", 2.0, 64.5, 90.0),
    "SW2": ("e1b45ef9-fc4c-43d7-a18d-6214275ed77b", 2.0, 72.5, 90.0),
    "SW3": ("d99f2bc3-0d43-4fe4-a955-849a404c349e", 2.0, 80.5, 90.0),
    "SW4": ("96807f06-c6b8-48ed-a589-e5ec5aa62fbc", 2.0, 88.5, 90.0),
    "SW5": ("e8042dbe-c4fd-4c0c-bd05-65a8c59cea00", 2.0, 96.5, 90.0),
    "J5": ("5fe280f5-b775-417d-8242-0585b6692145", 5.5, 109.0, 90.0),
    "J6": ("4b971ecc-483c-4c04-b0da-7e4a75735ce0", 16.5, 120.0, 180.0),
}
TARGET_PLACEMENTS = {
    "SW1": (2.0, 64.5, 270.0),
    "SW2": (2.0, 72.5, 270.0),
    "SW3": (2.0, 80.5, 270.0),
    "SW4": (2.0, 88.5, 270.0),
    "SW5": (2.0, 96.5, 270.0),
    "J5": (3.65, 108.70, 270.0),
    "J6": (14.75, 120.0, 0.0),
}
ALLOWED_FOOTPRINTS = frozenset(TARGET_PLACEMENTS)

EDGE_SILK_UUIDS = {
    "SW1": frozenset(
        {
            "076de2f9-67ca-4dee-ad6d-7ea23208f957",
            "162d07e1-9b28-44e0-b16e-2297993597b0",
            "9ccffd49-55cb-4adb-aaca-55426b835f47",
            "e04309a7-5a1f-406d-92cf-c3a69a801aa7",
        }
    ),
    "SW2": frozenset(
        {
            "3c6b26c0-7752-4ef7-8812-09fca6ce15db",
            "a5667f92-c353-4689-8d2d-7d3bf71198fc",
            "cf9350fb-b6c1-4622-b0aa-ca0b492febd7",
            "e832d115-d1ab-4cbb-8d33-065e584d4c85",
        }
    ),
    "SW3": frozenset(
        {
            "129a7f29-7869-44e1-98fa-1b291b155e23",
            "8ccc328a-9e7a-443a-90a0-dca6d2fc2dc6",
            "9b64330e-656c-463e-8d4e-3626c14ed013",
            "a8ac1b82-1b85-4822-806f-39e9329bf6d5",
        }
    ),
    "SW4": frozenset(
        {
            "0b53b716-478c-47ec-9198-cbc744c0c427",
            "951fa177-f7d3-4a92-9463-f8cec0f0b8df",
            "c462663d-10a6-47a4-b767-9adf8cc53391",
            "d2323a28-b5f0-40af-a92e-7700a187b7b2",
        }
    ),
    "SW5": frozenset(
        {
            "634219d3-d43a-4438-b9ca-1f5106069971",
            "a58e58f4-870a-49da-97df-15fd32b40d30",
            "b5268fe4-3879-44ee-89b8-2583d5643400",
            "eace8acb-4d21-4929-8c81-c836574f5127",
        }
    ),
    "J5": frozenset(
        {
            "30293ae8-9099-4bc9-9ae1-b9a5749b50d7",
            "3757d07a-bfde-4395-951d-4faf84c5074e",
        }
    ),
    "J6": frozenset(
        {
            "0f75acac-ce4d-425c-91b7-b85d1be79153",
            "14097df3-ee6c-49ce-98a7-176d977f5ed0",
            "70bf1633-8576-43b9-b337-787a8636183d",
            "7b01afb0-6b6f-4ce5-bb70-990e6a35f490",
            "a736cbb3-519e-456b-b491-e858fddcb0fe",
            "c23291c7-b4ea-4798-8f3c-2d8f0fb5dde7",
        }
    ),
}
ALL_EDGE_SILK_UUIDS = frozenset().union(*EDGE_SILK_UUIDS.values())
if len(ALL_EDGE_SILK_UUIDS) != 28:
    raise RuntimeError("edge silk allowlist cardinality is not 28")

J5_GND_PAD_UUIDS = {
    "A1": "f99a8764-1b0e-4457-a541-108719e1109b",
    "A12": "ec3a4bc1-f693-45cc-92e7-225bfc2260af",
    "B1": "5b00cad5-bd27-4a7f-84f3-ed34abac091d",
    "B12": "ba52cfcd-4633-46fe-90d0-24b317cd331d",
}

SOURCE_USB_VBUS_TRACK_UUIDS = frozenset(
    {
        "4ba3eeee-1dbd-4b91-8ac8-59c552e6d757",
        "5f246612-9ec2-4800-8079-955349892ac3",
        "9962b84c-f230-4bdc-bc6d-9d9acddb9f07",
        "a2e47552-528a-4c30-afb2-80da4e6f5d35",
        "c4cfeafa-930a-4196-9b2c-d4da44a463ea",
        "cda8c336-180e-43b6-9076-9a0cd5a78df8",
        "d0827c8a-86b7-43d7-a504-eb7700384122",
        "d7818204-d4bc-474b-a194-06e12128ac85",
    }
)

# Exactly eight deterministic replacement segments.  The first/third are
# narrow pad necks, the second/fourth widen before the common branch, and the
# final three segments preserve the known-clear F1.1 approach corridor.
USB_VBUS_ROUTE = (
    ((7.695, 106.250), (5.450, 106.650), 0.20),
    ((5.450, 106.650), (4.200, 106.650), 0.40),
    ((7.695, 111.150), (5.450, 110.750), 0.20),
    ((5.450, 110.750), (4.200, 110.750), 0.40),
    ((4.200, 110.750), (4.200, 106.650), 0.60),
    ((4.200, 106.650), (4.800, 105.200), 0.80),
    ((4.800, 105.200), (4.800, 101.000), 0.80),
    ((4.800, 101.000), (7.0375, 99.000), 0.80),
)
ROUTING_UUID_SEED = 0xB3EA7701
EXPECTED_DRC_CATEGORIES = {"drill_out_of_range": 12, "track_dangling": 1}
EXPECTED_SOURCE_UNCONNECTED = 141
EXPECTED_CANDIDATE_UNCONNECTED = 139
EXPECTED_PARITY = 0
B2_PROTECTED_MAX_X_MM = 65.0
B2_PROTECTED_MAX_Y_MM = 60.5
ANTENNA_RULE_BBOX_MM = (58.75, 66.0, 79.75, 114.0)


class ProbeError(RuntimeError):
    """Fail-closed edge-access probe error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def item_uuid(item: Any) -> str:
    return str(item.m_Uuid.AsString())


def point_iu(point: Any) -> tuple[int, int]:
    return int(point.x), int(point.y)


def point_mm(point: Any) -> tuple[float, float]:
    return round(pcbnew.ToMM(point.x), 6), round(pcbnew.ToMM(point.y), 6)


def natural_key(value: str) -> tuple[Any, ...]:
    return r7base.natural_key(value)


def protected_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for path, expected in PROTECTED_HASHES.items():
        if not path.is_file() or path.is_symlink():
            raise ProbeError(f"protected input absent or symlinked: {path}")
        observed = sha256_file(path)
        if observed.casefold() != expected.casefold():
            raise ProbeError(
                f"protected hash mismatch for {path}: {observed} != {expected}"
            )
        result[str(path.resolve())] = observed
    return dict(sorted(result.items()))


def assert_no_locks() -> None:
    locks = sorted(str(path.resolve()) for path in B3_DIR.rglob("~*.lck"))
    if locks:
        raise ProbeError(f"close KiCad before building: {locks}")


def assert_output_scope() -> None:
    outputs = {OUTPUT_BOARD, OUTPUT_REPORT, OUTPUT_DRC, OUTPUT_TOP, OUTPUT_BOTTOM}
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise ProbeError("output paths alias")
    protected = {path.resolve() for path in PROTECTED_HASHES}
    if any(path.resolve() in protected for path in outputs):
        raise ProbeError("output aliases a protected input")
    staging = STAGING.resolve()
    for path in outputs:
        if staging not in path.resolve().parents:
            raise ProbeError(f"output escapes staging: {path}")


def footprint_transform(footprint: Any) -> tuple[int, int, float]:
    position = footprint.GetPosition()
    return (
        int(position.x),
        int(position.y),
        round(float(footprint.GetOrientationDegrees()) % 360.0, 6),
    )


def footprint_static_signature(footprint: Any) -> tuple[Any, ...]:
    return (
        item_uuid(footprint),
        footprint.GetReference(),
        footprint.GetValue(),
        footprint.GetFPID().GetUniStringLibId(),
        bool(footprint.IsFlipped()),
        int(footprint.GetLayer()),
        bool(footprint.IsLocked()),
        int(footprint.GetAttributes()),
    )


def pad_local_signature(pad: Any, footprint: Any) -> tuple[Any, ...]:
    relative = pad.GetFPRelativePosition()
    size = pad.GetSize()
    drill = pad.GetDrillSize()
    offset = pad.GetOffset()
    relative_angle = (
        float(pad.GetOrientationDegrees())
        - float(footprint.GetOrientationDegrees())
    ) % 360.0
    return (
        item_uuid(pad),
        pad.GetNumber(),
        pad.GetNetname(),
        tuple(int(layer) for layer in pad.GetLayerSet().Seq()),
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
        round(relative_angle, 6),
        int(pad.GetLocalZoneConnection()),
    )


def local_point(footprint: Any, point: Any) -> tuple[int, int]:
    position = footprint.GetPosition()
    dx = int(point.x) - int(position.x)
    dy = int(point.y) - int(position.y)
    radians = math.radians(-float(footprint.GetOrientationDegrees()))
    x = dx * math.cos(radians) - dy * math.sin(radians)
    y = dx * math.sin(radians) + dy * math.cos(radians)
    return int(round(x)), int(round(y))


def graphic_local_signature(item: Any, footprint: Any) -> tuple[Any, ...]:
    common: list[Any] = [item_uuid(item), type(item).__name__, int(item.GetLayer())]
    if isinstance(item, pcbnew.PCB_SHAPE):
        common.extend(
            [
                int(item.GetShape()),
                local_point(footprint, item.GetStart()),
                local_point(footprint, item.GetEnd()),
                int(item.GetWidth()),
            ]
        )
    elif isinstance(item, pcbnew.PCB_TEXT):
        size = item.GetTextSize()
        common.extend(
            [
                item.GetText(),
                local_point(footprint, item.GetPosition()),
                round(
                    (
                        float(item.GetTextAngleDegrees())
                        - float(footprint.GetOrientationDegrees())
                    )
                    % 360.0,
                    6,
                ),
                int(size.x),
                int(size.y),
                int(item.GetTextThickness()),
                bool(item.IsVisible()),
                bool(item.IsMirrored()),
            ]
        )
    else:
        relative = item.GetFPRelativePosition()
        common.extend([int(relative.x), int(relative.y)])
    return tuple(common)


def field_local_signature(field: Any, footprint: Any) -> tuple[Any, ...]:
    size = field.GetTextSize()
    return (
        item_uuid(field),
        field.GetText(),
        int(field.GetLayer()),
        local_point(footprint, field.GetPosition()),
        round(
            (
                float(field.GetTextAngleDegrees())
                - float(footprint.GetOrientationDegrees())
            )
            % 360.0,
            6,
        ),
        int(size.x),
        int(size.y),
        int(field.GetTextThickness()),
        bool(field.IsVisible()),
        bool(field.IsMirrored()),
    )


def track_signature(item: Any) -> tuple[Any, ...]:
    return r7base.track_signature(item)


def zone_signature(zone: Any) -> tuple[Any, ...]:
    return r7base.zone_signature(zone)


def drawing_signature(item: Any) -> tuple[Any, ...]:
    return r7base.graphic_signature(item)


def board_state(board: Any) -> dict[str, Any]:
    footprints = sorted(
        board.GetFootprints(), key=lambda footprint: natural_key(footprint.GetReference())
    )
    return {
        "footprint_static": {
            footprint.GetReference(): footprint_static_signature(footprint)
            for footprint in footprints
        },
        "footprint_transform": {
            footprint.GetReference(): footprint_transform(footprint)
            for footprint in footprints
        },
        "pads_local": {
            (footprint.GetReference(), item_uuid(pad)): pad_local_signature(
                pad, footprint
            )
            for footprint in footprints
            for pad in footprint.Pads()
        },
        "graphics_local": {
            (footprint.GetReference(), item_uuid(item)): graphic_local_signature(
                item, footprint
            )
            for footprint in footprints
            for item in footprint.GraphicalItems()
        },
        "fields_local": {
            (footprint.GetReference(), "reference"): field_local_signature(
                footprint.Reference(), footprint
            )
            for footprint in footprints
        }
        | {
            (footprint.GetReference(), "value"): field_local_signature(
                footprint.Value(), footprint
            )
            for footprint in footprints
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
        "tracks": {item_uuid(item): track_signature(item) for item in board.GetTracks()},
        "zones": {item_uuid(zone): zone_signature(zone) for zone in board.Zones()},
        "drawings": {
            item_uuid(item): drawing_signature(item) for item in board.Drawings()
        },
    }


def find_pad(board: Any, reference: str, number: str) -> Any:
    footprint = board.FindFootprintByReference(reference)
    if footprint is None:
        raise ProbeError(f"missing footprint {reference}")
    pads = [pad for pad in footprint.Pads() if pad.GetNumber() == number]
    if len(pads) != 1:
        raise ProbeError(f"{reference}.{number} pad cardinality differs")
    return pads[0]


def verify_source_placements(board: Any) -> None:
    for reference, (uuid, x_mm, y_mm, rotation) in SOURCE_PLACEMENTS.items():
        footprint = board.FindFootprintByReference(reference)
        if footprint is None or item_uuid(footprint) != uuid:
            raise ProbeError(f"source footprint identity differs: {reference}")
        expected = (
            pcbnew.FromMM(x_mm),
            pcbnew.FromMM(y_mm),
            round(rotation % 360.0, 6),
        )
        if footprint_transform(footprint) != expected:
            raise ProbeError(
                f"source placement differs for {reference}: "
                f"{footprint_transform(footprint)} != {expected}"
            )


def add_track(
    board: Any,
    net: Any,
    start_mm: tuple[float, float],
    end_mm: tuple[float, float],
    width_mm: float,
) -> Any:
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(net)
    item.SetLayer(pcbnew.F_Cu)
    item.SetWidth(pcbnew.FromMM(width_mm))
    item.SetStart(pcbnew.VECTOR2I_MM(*start_mm))
    item.SetEnd(pcbnew.VECTOR2I_MM(*end_mm))
    if item.GetStart() == item.GetEnd():
        raise ProbeError(f"zero-length VBUS segment: {start_mm}")
    board.Add(item)
    return item


def apply_probe(board: Any) -> dict[str, Any]:
    verify_source_placements(board)

    placement_changes = []
    for reference in sorted(TARGET_PLACEMENTS, key=natural_key):
        footprint = board.FindFootprintByReference(reference)
        before = footprint_transform(footprint)
        x_mm, y_mm, rotation = TARGET_PLACEMENTS[reference]
        footprint.SetPosition(pcbnew.VECTOR2I_MM(x_mm, y_mm))
        footprint.SetOrientationDegrees(rotation)
        after = footprint_transform(footprint)
        expected = (
            pcbnew.FromMM(x_mm),
            pcbnew.FromMM(y_mm),
            round(rotation % 360.0, 6),
        )
        if after != expected:
            raise ProbeError(f"target placement did not apply: {reference}")
        placement_changes.append(
            {
                "reference": reference,
                "uuid": item_uuid(footprint),
                "before_mm_deg": [
                    round(pcbnew.ToMM(before[0]), 6),
                    round(pcbnew.ToMM(before[1]), 6),
                    before[2],
                ],
                "after_mm_deg": [x_mm, y_mm, rotation],
            }
        )

    silk_changes = []
    for reference in sorted(EDGE_SILK_UUIDS, key=natural_key):
        footprint = board.FindFootprintByReference(reference)
        graphics = {
            item_uuid(item): item for item in footprint.GraphicalItems()
        }
        expected = EDGE_SILK_UUIDS[reference]
        if not expected.issubset(graphics):
            raise ProbeError(f"edge-silk UUID set differs for {reference}")
        for uuid in sorted(expected):
            item = graphics[uuid]
            if not isinstance(item, pcbnew.PCB_SHAPE):
                raise ProbeError(f"allowlisted edge silk is not a shape: {uuid}")
            if item.GetLayer() != pcbnew.F_SilkS:
                raise ProbeError(f"allowlisted edge silk is not F.SilkS: {uuid}")
            item.SetLayer(pcbnew.F_Fab)
            silk_changes.append(
                {
                    "reference": reference,
                    "uuid": uuid,
                    "from": "F.SilkS",
                    "to": "F.Fab",
                }
            )
    if len(silk_changes) != 28:
        raise ProbeError("edge-silk mutation cardinality is not 28")

    j5_ground_changes = []
    for number, expected_uuid in sorted(J5_GND_PAD_UUIDS.items()):
        pad = find_pad(board, "J5", number)
        if item_uuid(pad) != expected_uuid:
            raise ProbeError(f"J5.{number} UUID differs")
        if pad.GetNetname() != "GND":
            raise ProbeError(f"J5.{number} is not GND")
        before_connection = int(pad.GetLocalZoneConnection())
        if before_connection != int(pcbnew.ZONE_CONNECTION_INHERITED):
            raise ProbeError(f"J5.{number} source zone connection is not inherited")
        pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        j5_ground_changes.append(
            {
                "reference": "J5",
                "pad": number,
                "uuid": expected_uuid,
                "net": pad.GetNetname(),
                "before_local_zone_connection": before_connection,
                "after_local_zone_connection": int(pad.GetLocalZoneConnection()),
                "after_name": "ZONE_CONNECTION_FULL",
            }
        )

    source_vbus = {
        item_uuid(item): item
        for item in board.GetTracks()
        if item.GetNetname() == "/USB_VBUS"
    }
    if set(source_vbus) != set(SOURCE_USB_VBUS_TRACK_UUIDS):
        raise ProbeError(
            "source /USB_VBUS UUID set differs: "
            f"{sorted(source_vbus)} != {sorted(SOURCE_USB_VBUS_TRACK_UUIDS)}"
        )
    removed = [
        {
            "uuid": uuid,
            "signature": list(track_signature(source_vbus[uuid])),
        }
        for uuid in sorted(source_vbus)
    ]
    for uuid in sorted(source_vbus):
        board.Remove(source_vbus[uuid])

    net = board.FindNet("/USB_VBUS")
    if net is None:
        raise ProbeError("/USB_VBUS net absent")
    pcbnew.KIID.SeedGenerator(ROUTING_UUID_SEED)
    added_items = [
        add_track(board, net, start, end, width)
        for start, end, width in USB_VBUS_ROUTE
    ]
    if len({item_uuid(item) for item in added_items}) != len(USB_VBUS_ROUTE):
        raise ProbeError("replacement VBUS UUIDs are not unique")
    if set(item_uuid(item) for item in added_items) & set(
        SOURCE_USB_VBUS_TRACK_UUIDS
    ):
        raise ProbeError("replacement VBUS UUID collides with a removed source UUID")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    added = [
        {
            "uuid": item_uuid(item),
            "net": item.GetNetname(),
            "layer": pcbnew.LayerName(item.GetLayer()),
            "start_mm": list(point_mm(item.GetStart())),
            "end_mm": list(point_mm(item.GetEnd())),
            "width_mm": round(pcbnew.ToMM(item.GetWidth()), 6),
        }
        for item in added_items
    ]
    return {
        "placements": placement_changes,
        "edge_silk_to_f_fab": silk_changes,
        "j5_ground_solid_zone": j5_ground_changes,
        "usb_vbus": {
            "removed_count": len(removed),
            "removed": removed,
            "added_count": len(added),
            "added": added,
            "routing_uuid_seed": ROUTING_UUID_SEED,
        },
    }


def expected_transform_mm(reference: str) -> tuple[int, int, float]:
    x_mm, y_mm, rotation = TARGET_PLACEMENTS[reference]
    return pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm), rotation


def audit_candidate(
    source: Mapping[str, Any], candidate: Mapping[str, Any], board: Any
) -> dict[str, Any]:
    source_refs = set(source["footprint_static"])
    candidate_refs = set(candidate["footprint_static"])
    changed_transforms = {
        reference
        for reference in source_refs & candidate_refs
        if source["footprint_transform"][reference]
        != candidate["footprint_transform"][reference]
    }
    frozen_drift = [
        reference
        for reference in sorted(source_refs & candidate_refs, key=natural_key)
        if reference not in ALLOWED_FOOTPRINTS
        and source["footprint_transform"][reference]
        != candidate["footprint_transform"][reference]
    ]
    target_exact = {
        reference: candidate["footprint_transform"].get(reference)
        == expected_transform_mm(reference)
        for reference in sorted(TARGET_PLACEMENTS, key=natural_key)
    }

    pad_local_changes = {
        key: (source["pads_local"][key], candidate["pads_local"][key])
        for key in source["pads_local"]
        if source["pads_local"][key] != candidate["pads_local"][key]
    }
    expected_pad_keys = {
        ("J5", uuid) for uuid in J5_GND_PAD_UUIDS.values()
    }
    pad_changes_exact = set(pad_local_changes) == expected_pad_keys
    for before, after in pad_local_changes.values():
        pad_changes_exact = (
            pad_changes_exact
            and before[:-1] == after[:-1]
            and before[-1] == int(pcbnew.ZONE_CONNECTION_INHERITED)
            and after[-1] == int(pcbnew.ZONE_CONNECTION_FULL)
            and before[2] == "GND"
            and after[2] == "GND"
        )

    graphic_local_changes = {
        key: (source["graphics_local"][key], candidate["graphics_local"][key])
        for key in source["graphics_local"]
        if source["graphics_local"][key]
        != candidate["graphics_local"][key]
    }
    expected_graphic_keys = {
        (reference, uuid)
        for reference, uuids in EDGE_SILK_UUIDS.items()
        for uuid in uuids
    }
    graphic_changes_exact = set(graphic_local_changes) == expected_graphic_keys
    for before, after in graphic_local_changes.values():
        graphic_changes_exact = (
            graphic_changes_exact
            and before[:2] == after[:2]
            and before[2] == int(pcbnew.F_SilkS)
            and after[2] == int(pcbnew.F_Fab)
            and before[3:] == after[3:]
        )

    source_tracks = source["tracks"]
    candidate_tracks = candidate["tracks"]
    retained_source = set(source_tracks) - set(SOURCE_USB_VBUS_TRACK_UUIDS)
    removed_present = sorted(set(SOURCE_USB_VBUS_TRACK_UUIDS) & set(candidate_tracks))
    missing_retained = sorted(retained_source - set(candidate_tracks))
    changed_retained = sorted(
        uuid
        for uuid in retained_source & set(candidate_tracks)
        if source_tracks[uuid] != candidate_tracks[uuid]
    )
    extra_tracks = sorted(set(candidate_tracks) - retained_source)
    extra_signatures = [candidate_tracks[uuid] for uuid in extra_tracks]
    expected_route_signatures = sorted(
        (
            "track",
            None,
            "/USB_VBUS",
            int(pcbnew.F_Cu),
            pcbnew.FromMM(start[0]),
            pcbnew.FromMM(start[1]),
            pcbnew.FromMM(end[0]),
            pcbnew.FromMM(end[1]),
            pcbnew.FromMM(width),
        )
        for start, end, width in USB_VBUS_ROUTE
    )
    normalized_extra = sorted(
        (signature[0], None, *signature[2:]) for signature in extra_signatures
    )

    source_count = len(source_tracks)
    candidate_count = len(candidate_tracks)
    checks = {
        "same_footprint_reference_set": source_refs == candidate_refs,
        "only_allowlisted_footprint_transforms_changed": not frozen_drift
        and changed_transforms == set(ALLOWED_FOOTPRINTS),
        "target_placements_exact": all(target_exact.values()),
        "footprint_static_state_exact": source["footprint_static"]
        == candidate["footprint_static"],
        "only_four_j5_gnd_zone_connections_changed": pad_changes_exact,
        "only_28_edge_silk_layers_changed": graphic_changes_exact,
        "footprint_fields_local_exact": source["fields_local"]
        == candidate["fields_local"],
        "footprint_child_uuid_sets_exact": source["children"]
        == candidate["children"],
        "all_non_vbus_source_copper_exact": not missing_retained
        and not changed_retained,
        "all_eight_source_vbus_tracks_absent": not removed_present,
        "exactly_eight_replacement_tracks": len(extra_tracks) == 8,
        "replacement_vbus_geometry_exact": normalized_extra
        == expected_route_signatures,
        "track_via_count_unchanged": source_count == candidate_count,
        "zone_uuid_outline_settings_exact": source["zones"] == candidate["zones"],
        "board_drawings_exact": source["drawings"] == candidate["drawings"],
    }

    j5_expected = {
        "A4": (7.695, 106.25),
        "B9": (7.695, 106.25),
        "A9": (7.695, 111.15),
        "B4": (7.695, 111.15),
    }
    j5_actual = {
        number: point_mm(find_pad(board, "J5", number).GetPosition())
        for number in j5_expected
    }
    checks["j5_vbus_pad_centres_exact"] = j5_actual == j5_expected
    checks["f1_1_anchor_exact"] = point_mm(
        find_pad(board, "F1", "1").GetPosition()
    ) == (7.0375, 99.0)

    board.BuildConnectivity()
    anchor = find_pad(board, "F1", "1")
    connected = list(board.GetConnectivity().GetConnectedItems(anchor))
    connected_pads = {
        (
            item.GetParentFootprint().GetReference(),
            item.GetNumber(),
            item.GetNetname(),
        )
        for item in connected
        if isinstance(item, pcbnew.PAD)
    }
    required_pads = {
        ("F1", "1", "/USB_VBUS"),
        ("J5", "A4", "/USB_VBUS"),
        ("J5", "A9", "/USB_VBUS"),
        ("J5", "B4", "/USB_VBUS"),
        ("J5", "B9", "/USB_VBUS"),
    }
    checks["all_j5_vbus_pads_connected_to_f1_1"] = required_pads.issubset(
        connected_pads
    )

    new_copper = [candidate_tracks[uuid] for uuid in extra_tracks]
    checks["new_copper_f_cu_only"] = all(
        signature[3] == int(pcbnew.F_Cu) for signature in new_copper
    )
    checks["no_new_copper_in_b2"] = all(
        min(pcbnew.ToMM(signature[4]), pcbnew.ToMM(signature[6]))
        > B2_PROTECTED_MAX_X_MM
        or min(pcbnew.ToMM(signature[5]), pcbnew.ToMM(signature[7]))
        > B2_PROTECTED_MAX_Y_MM
        for signature in new_copper
    )
    ax1, ay1, ax2, ay2 = ANTENNA_RULE_BBOX_MM
    checks["no_new_copper_in_antenna_keepout"] = all(
        max(pcbnew.ToMM(signature[4]), pcbnew.ToMM(signature[6])) < ax1
        or min(pcbnew.ToMM(signature[4]), pcbnew.ToMM(signature[6])) > ax2
        or max(pcbnew.ToMM(signature[5]), pcbnew.ToMM(signature[7])) < ay1
        or min(pcbnew.ToMM(signature[5]), pcbnew.ToMM(signature[7])) > ay2
        for signature in new_copper
    )
    checks["no_new_in1_copper"] = all(
        signature[3] != int(pcbnew.In1_Cu) for signature in new_copper
    )
    checks["all_preservation_and_scope_checks_pass"] = all(checks.values())
    return {
        "passed": checks["all_preservation_and_scope_checks_pass"],
        "checks": checks,
        "changed_footprint_transforms": sorted(changed_transforms, key=natural_key),
        "frozen_footprint_drift": frozen_drift,
        "target_placement_checks": target_exact,
        "pad_local_changes": [
            {
                "reference": key[0],
                "pad_uuid": key[1],
                "before": list(values[0]),
                "after": list(values[1]),
            }
            for key, values in sorted(pad_local_changes.items())
        ],
        "graphic_layer_changes": [
            {
                "reference": key[0],
                "graphic_uuid": key[1],
                "before_layer": values[0][2],
                "after_layer": values[1][2],
            }
            for key, values in sorted(graphic_local_changes.items())
        ],
        "missing_retained_copper": missing_retained,
        "changed_retained_copper": changed_retained,
        "removed_source_vbus_still_present": removed_present,
        "replacement_track_uuids": extra_tracks,
        "source_track_via_count": source_count,
        "candidate_track_via_count": candidate_count,
        "j5_vbus_pad_centres_mm": {
            key: list(value) for key, value in sorted(j5_actual.items())
        },
        "f1_1_position_mm": list(point_mm(anchor.GetPosition())),
        "vbus_connected_pads": [list(item) for item in sorted(connected_pads)],
    }


def build_once(destination: Path) -> dict[str, Any]:
    board = pcbnew.LoadBoard(str(SOURCE_BOARD.resolve()))
    if board is None:
        raise ProbeError("pcbnew could not load frozen R7 board")
    source = board_state(board)
    changes = apply_probe(board)
    pcbnew.SaveBoard(str(destination), board)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ProbeError("pcbnew did not save edge-access candidate")
    reloaded = pcbnew.LoadBoard(str(destination.resolve()))
    if reloaded is None:
        raise ProbeError("pcbnew could not reload edge-access candidate")
    candidate = board_state(reloaded)
    audit = audit_candidate(source, candidate, reloaded)
    if audit["passed"] is not True:
        raise ProbeError(
            "edge-access source-preservation audit failed: "
            + json.dumps(audit, ensure_ascii=False)
        )
    return {
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "changes": changes,
        "audit": audit,
    }


def violation_identity(value: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    return sorted(
        (
            str(item.get("type")),
            tuple(sorted(r7base.violation_item_uuids(item))),
        )
        for item in value["raw"].get("violations", [])
    )


def unconnected_by_net(value: Mapping[str, Any]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for violation in value["raw"].get("unconnected_items", []):
        items = violation.get("items", [])
        if isinstance(items, Mapping):
            items = [items]
        nets = {
            match
            for item in items
            if isinstance(item, Mapping)
            for match in re.findall(r"\[([^\]]+)\]", str(item.get("description", "")))
        }
        if len(nets) != 1:
            raise ProbeError(
                f"could not assign unconnected item to one net: {violation}"
            )
        counts[next(iter(nets))] += 1
    return dict(sorted(counts.items()))


def validate_drc(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    source_identity = violation_identity(source)
    candidate_identity = violation_identity(candidate)
    source_drills = {
        uuid
        for category, uuids in source_identity
        if category == "drill_out_of_range"
        for uuid in uuids
    }
    source_dangling = {
        uuid
        for category, uuids in source_identity
        if category == "track_dangling"
        for uuid in uuids
    }
    source_unconnected_by_net = unconnected_by_net(source)
    candidate_unconnected_by_net = unconnected_by_net(candidate)
    unconnected_delta_by_net = {
        net: candidate_unconnected_by_net.get(net, 0)
        - source_unconnected_by_net.get(net, 0)
        for net in sorted(
            set(source_unconnected_by_net) | set(candidate_unconnected_by_net)
        )
        if candidate_unconnected_by_net.get(net, 0)
        != source_unconnected_by_net.get(net, 0)
    }
    checks = {
        "source_categories_exact": source["violation_categories"]
        == EXPECTED_DRC_CATEGORIES,
        "candidate_categories_exact": candidate["violation_categories"]
        == EXPECTED_DRC_CATEGORIES,
        "source_violation_count_13": source["violation_count"] == 13,
        "candidate_violation_count_13": candidate["violation_count"] == 13,
        "source_unconnected_141": source["unconnected_count"]
        == EXPECTED_SOURCE_UNCONNECTED,
        "candidate_unconnected_139": candidate["unconnected_count"]
        == EXPECTED_CANDIDATE_UNCONNECTED,
        "unconnected_not_increased": candidate["unconnected_count"]
        <= source["unconnected_count"],
        "unconnected_delta_only_gnd_minus_2": unconnected_delta_by_net
        == {"GND": -2},
        "usb_vbus_ratline_count_unchanged_zero": source_unconnected_by_net.get(
            "/USB_VBUS", 0
        )
        == 0
        and candidate_unconnected_by_net.get("/USB_VBUS", 0) == 0,
        "source_parity_zero": source["schematic_parity_count"] == EXPECTED_PARITY,
        "candidate_parity_zero": candidate["schematic_parity_count"]
        == EXPECTED_PARITY,
        "candidate_violation_identity_exactly_source": candidate_identity
        == source_identity,
        "source_u1_drill_uuid_set_exact": source_drills
        == set(r7base.U1_DRILL_UUIDS),
        "source_dangling_uuid_exact": source_dangling
        == {r7base.DANGLING_TRACK_UUID},
    }
    if not all(checks.values()):
        detail = {
            "checks": checks,
            "source": {
                "violation_count": source["violation_count"],
                "categories": source["violation_categories"],
                "unconnected_count": source["unconnected_count"],
                "schematic_parity_count": source["schematic_parity_count"],
            },
            "candidate": {
                "violation_count": candidate["violation_count"],
                "categories": candidate["violation_categories"],
                "unconnected_count": candidate["unconnected_count"],
                "schematic_parity_count": candidate["schematic_parity_count"],
            },
            "unconnected_delta_by_net": unconnected_delta_by_net,
        }
        raise ProbeError(
            "DRC/parity/connectivity gate failed: "
            + json.dumps(detail, ensure_ascii=False, sort_keys=True)
        )
    return {
        "passed": True,
        "checks": checks,
        "source_categories": source["violation_categories"],
        "candidate_categories": candidate["violation_categories"],
        "source_violation_identity": [
            [category, list(uuids)] for category, uuids in source_identity
        ],
        "candidate_violation_identity": [
            [category, list(uuids)] for category, uuids in candidate_identity
        ],
        "unconnected_count": candidate["unconnected_count"],
        "source_unconnected_by_net": source_unconnected_by_net,
        "candidate_unconnected_by_net": candidate_unconnected_by_net,
        "unconnected_delta_by_net": unconnected_delta_by_net,
        "schematic_parity_count": candidate["schematic_parity_count"],
    }


def vbus_connectivity_evidence(board_path: Path) -> dict[str, Any]:
    board = pcbnew.LoadBoard(str(board_path.resolve()))
    if board is None:
        raise ProbeError(f"could not load board for VBUS proof: {board_path}")
    board.BuildConnectivity()
    anchor = find_pad(board, "F1", "1")
    if anchor.GetNetname() != "/USB_VBUS":
        raise ProbeError("F1.1 is not /USB_VBUS")
    connected = list(board.GetConnectivity().GetConnectedItems(anchor))
    connected_uuids = {item_uuid(item) for item in connected}
    connected_pads = sorted(
        {
            (
                item.GetParentFootprint().GetReference(),
                item.GetNumber(),
                item.GetNetname(),
                item_uuid(item),
            )
            for item in connected
            if isinstance(item, pcbnew.PAD)
        }
    )
    tracks = [
        item for item in board.GetTracks() if item.GetNetname() == "/USB_VBUS"
    ]
    required_pads = {
        ("F1", "1"),
        ("J5", "A4"),
        ("J5", "A9"),
        ("J5", "B4"),
        ("J5", "B9"),
    }
    actual_pads = {(item[0], item[1]) for item in connected_pads}
    track_records = sorted(
        [
            {
                "uuid": item_uuid(item),
                "start_mm": list(point_mm(item.GetStart())),
                "end_mm": list(point_mm(item.GetEnd())),
                "width_mm": round(pcbnew.ToMM(item.GetWidth()), 6),
                "layer": pcbnew.LayerName(item.GetLayer()),
            }
            for item in tracks
        ],
        key=lambda item: item["uuid"],
    )
    checks = {
        "exactly_eight_vbus_tracks": len(tracks) == 8,
        "all_eight_tracks_in_f1_1_connected_set": all(
            item_uuid(item) in connected_uuids for item in tracks
        ),
        "f1_and_all_four_j5_vbus_pads_in_one_connected_set": required_pads
        <= actual_pads,
        "all_vbus_tracks_are_f_cu": all(
            item.GetLayer() == pcbnew.F_Cu for item in tracks
        ),
    }
    if not all(checks.values()):
        raise ProbeError(f"/USB_VBUS connected-set proof failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "anchor": {
            "reference": "F1",
            "pad": "1",
            "uuid": item_uuid(anchor),
            "net": anchor.GetNetname(),
            "position_mm": list(point_mm(anchor.GetPosition())),
        },
        "connected_pads": [list(item) for item in connected_pads],
        "tracks": track_records,
    }


def bbox_mm(box: Any) -> list[float]:
    return [
        round(pcbnew.ToMM(box.GetX()), 6),
        round(pcbnew.ToMM(box.GetY()), 6),
        round(pcbnew.ToMM(box.GetRight()), 6),
        round(pcbnew.ToMM(box.GetBottom()), 6),
    ]


def mechanical_evidence(board_path: Path) -> dict[str, Any]:
    board = pcbnew.LoadBoard(str(board_path.resolve()))
    if board is None:
        raise ProbeError("could not load candidate for mechanical evidence")
    refs = {ref: board.FindFootprintByReference(ref) for ref in ("J6", "H3", "C49", "J4")}
    if any(footprint is None for footprint in refs.values()):
        raise ProbeError("mechanical evidence footprint is absent")
    courtyards = {
        ref: bbox_mm(footprint.GetCourtyard(pcbnew.F_CrtYd).BBox())
        for ref, footprint in refs.items()
    }
    j6_pad_boxes = [pad.GetBoundingBox() for pad in refs["J6"].Pads()]
    j6_copper = [
        min(box.GetX() for box in j6_pad_boxes),
        min(box.GetY() for box in j6_pad_boxes),
        max(box.GetRight() for box in j6_pad_boxes),
        max(box.GetBottom() for box in j6_pad_boxes),
    ]
    j6_copper_mm = [round(pcbnew.ToMM(value), 6) for value in j6_copper]
    j6 = courtyards["J6"]
    h3 = courtyards["H3"]
    c49 = courtyards["C49"]
    j4 = courtyards["J4"]
    gaps = {
        "h3_to_j6_x_mm": round(j6[0] - h3[2], 6),
        "j6_to_c49_x_mm": round(c49[0] - j6[2], 6),
        "j6_to_j4_x_mm": round(j4[0] - j6[2], 6),
        "j6_pad_copper_to_bottom_edge_mm": round(125.0 - j6_copper_mm[3], 6),
        "j6_pad_copper_to_left_edge_mm": j6_copper_mm[0],
    }
    checks = {
        "j6_position_exact": point_mm(refs["J6"].GetPosition()) == (14.75, 120.0),
        "j6_rotation_exact": round(
            float(refs["J6"].GetOrientationDegrees()) % 360.0, 6
        )
        == 0.0,
        "h3_courtyard_clear": gaps["h3_to_j6_x_mm"] > 0.0,
        "c49_courtyard_clear": gaps["j6_to_c49_x_mm"] > 0.0,
        "j4_courtyard_clear": gaps["j6_to_j4_x_mm"] > 0.0,
        "j6_pad_copper_inside_board": gaps[
            "j6_pad_copper_to_bottom_edge_mm"
        ]
        > 0.5,
    }
    if not all(checks.values()):
        raise ProbeError(f"J6 mechanical evidence gate failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "courtyard_bboxes_mm": courtyards,
        "j6_pad_copper_bbox_mm": j6_copper_mm,
        "gaps": gaps,
        "j6_connector_pack_line_order_status": "HOLD",
    }


def artifact_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run every gate without publishing staging artifacts",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    script = Path(__file__).resolve()
    script_hash_before = sha256_file(script)
    try:
        if pcbnew is None:
            raise ProbeError(f"KiCad pcbnew unavailable: {PCBNEW_IMPORT_ERROR}")
        if str(pcbnew.GetBuildVersion()).split(".", 1)[0] != "10":
            raise ProbeError(f"KiCad 10 required, found {pcbnew.GetBuildVersion()}")
        if not KICAD_CLI.is_file() or not KICAD_PYTHON.is_file():
            raise ProbeError("fixed KiCad 10 CLI/Python is absent")
        assert_output_scope()
        assert_no_locks()
        protected_before = protected_hashes()

        with tempfile.TemporaryDirectory(prefix="mf1750-r7-edge-access-") as name:
            temp_dir = Path(name)
            first = temp_dir / "run1.kicad_pcb"
            second = temp_dir / "run2.kicad_pcb"
            first_result = build_once(first)
            second_result = build_once(second)
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
            deterministic = {
                "passed": first_bytes == second_bytes,
                "run1_sha256": sha256_bytes(first_bytes),
                "run2_sha256": sha256_bytes(second_bytes),
                "run1_bytes": len(first_bytes),
                "run2_bytes": len(second_bytes),
            }
            if deterministic["passed"] is not True:
                raise ProbeError("double build is not byte deterministic")
            if first_result["changes"] != second_result["changes"]:
                raise ProbeError("double-build change evidence differs")
            if first_result["audit"] != second_result["audit"]:
                raise ProbeError("double-build preservation evidence differs")

            source_drc = r7base.run_drc(SOURCE_BOARD, "mf1750-edge-source-drc-")
            candidate_drc = r7base.run_drc(first, "mf1750-edge-candidate-drc-")
            drc_gate = validate_drc(source_drc, candidate_drc)
            source_vbus = vbus_connectivity_evidence(SOURCE_BOARD)
            candidate_vbus = vbus_connectivity_evidence(first)
            mechanics = mechanical_evidence(first)
            verifier = r7base.run_board_verifier(first)
            top_bytes = r7base.render(first, "top", OUTPUT_TOP, temp_dir)
            bottom_bytes = r7base.render(first, "bottom", OUTPUT_BOTTOM, temp_dir)
            candidate_drc_bytes = json_bytes(candidate_drc["raw"])

            script_hash_after = sha256_file(script)
            if script_hash_after != script_hash_before:
                raise ProbeError("builder changed while running")
            protected_after = protected_hashes()
            if protected_after != protected_before:
                raise ProbeError("protected input changed while building")
            assert_no_locks()

            artifacts = {
                "board": artifact_record(OUTPUT_BOARD, first_bytes),
                "drc": artifact_record(OUTPUT_DRC, candidate_drc_bytes),
                "top": artifact_record(OUTPUT_TOP, top_bytes),
                "bottom": artifact_record(OUTPUT_BOTTOM, bottom_bytes),
            }
            report = {
                "schema": 1,
                "tool": script.name,
                "mode": "REVISION_TO_STAGING_ONLY",
                "state": "R7_EDGE_ACCESS_PROBE_CANDIDATE_HOLD",
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
                "r7_source_modified": False,
                "generated_at_utc": dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "kicad": {
                    "pcbnew": str(pcbnew.GetBuildVersion()),
                    "cli": str(KICAD_CLI.resolve()),
                    "python": str(KICAD_PYTHON.resolve()),
                },
                "builder": {
                    "path": str(script),
                    "sha256_before": script_hash_before,
                    "sha256_after": script_hash_after,
                    "unchanged": True,
                },
                "source": {
                    "path": str(SOURCE_BOARD.resolve()),
                    "sha256": SOURCE_BOARD_SHA256,
                    "bytes": SOURCE_BOARD.stat().st_size,
                    "fixed_input": True,
                },
                "protected_hashes_before": protected_before,
                "protected_hashes_after": protected_after,
                "protected_hashes_unchanged": True,
                "changes": first_result["changes"],
                "preservation": first_result["audit"],
                "determinism": deterministic,
                "drc": {
                    "source": {
                        key: value for key, value in source_drc.items() if key != "raw"
                    },
                    "candidate": {
                        key: value
                        for key, value in candidate_drc.items()
                        if key != "raw"
                    },
                    "gate": drc_gate,
                },
                "connectivity_evidence": {
                    "usb_vbus_source": source_vbus,
                    "usb_vbus_candidate": candidate_vbus,
                    "usb_vbus_conclusion": "CONNECTED_SET_PRESERVED_NOT_REDUCED",
                    "unconnected_reduction": {
                        "source_total": source_drc["unconnected_count"],
                        "candidate_total": candidate_drc["unconnected_count"],
                        "delta_by_net": drc_gate["unconnected_delta_by_net"],
                        "reason": "the relocated J5 A1/A12/B1/B12 GND pads use solid F.Cu GND-plane connections; /USB_VBUS was already one connected set in frozen R7 and remains one connected set",
                        "all_other_net_ratline_counts_unchanged": True,
                    },
                },
                "project_board_verifier": verifier,
                "artifacts": artifacts,
                "mechanical_evidence": {
                    "board_outline_mm": [80.0, 125.0],
                    "switches": "centres retained; all side actuators rotated outward",
                    "j5": {
                        "position_mm": [3.65, 108.70],
                        "rotation_deg": 270.0,
                        "selection_reason": "moves the left-edge USB opening outward while increasing the C50 courtyard margin over the 108.1/108.2 alternatives",
                    },
                    "j6": mechanics,
                },
                "holds": [
                    "J6 connector choice, battery-pack mating envelope, and /BAT_POS-GND-/BAT_NTC line order remain HOLD",
                    "J5 enclosure cutout and complete cable mating envelope remain HOLD",
                    "SW1-SW5 lack 3D actuator-travel models; enclosure pushrod travel remains HOLD",
                    "12 U1 0.20 mm thermal drills, the preserved /EPD_SW_3V3 dangling endpoint, and 139 remaining unconnected items remain HOLD",
                    "stackup/USB impedance, enclosure, assembly, thermal, RF, and manufacturing release remain HOLD",
                ],
                "check_only": bool(args.check_only),
            }
            preliminary_report = json_bytes(report)
            report["artifacts"]["report"] = {
                "path": str(OUTPUT_REPORT.resolve()),
                "bytes_without_self_record": len(preliminary_report),
                "self_hash_intentionally_omitted": True,
            }
            report_bytes = json_bytes(report)

            if not args.check_only:
                r7base.atomic_write_bytes(OUTPUT_BOARD, first_bytes)
                r7base.atomic_write_bytes(OUTPUT_DRC, candidate_drc_bytes)
                r7base.atomic_write_bytes(OUTPUT_TOP, top_bytes)
                r7base.atomic_write_bytes(OUTPUT_BOTTOM, bottom_bytes)
                r7base.atomic_write_bytes(OUTPUT_REPORT, report_bytes)
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
                    raise ProbeError("published artifact hash differs")
                if protected_hashes() != protected_before:
                    raise ProbeError("protected input changed during publication")

        summary = {
            "state": report["state"],
            "overall_status": report["overall_status"],
            "operation_completed": report["operation_completed"],
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
            "tool": Path(__file__).name,
            "state": "R7_EDGE_ACCESS_PROBE_BUILD_FAILED_HOLD",
            "overall_status": "HOLD",
            "operation_completed": False,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "candidate_artifacts_published": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        if not args.check_only:
            failure["failure_report"] = str(OUTPUT_REPORT.resolve())
            r7base.atomic_write_bytes(OUTPUT_REPORT, json_bytes(failure))
        sys.stdout.write(json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
