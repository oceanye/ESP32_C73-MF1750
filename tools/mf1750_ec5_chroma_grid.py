#!/usr/bin/env python3
"""Build the fixed five-action factory-OTP chroma-history grid offline."""

from __future__ import annotations

import argparse
from collections import Counter
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from PIL import Image


WIDTH = 1024
HEIGHT = 600
HALF_WIDTH = 512
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_BYTES = HALF_WIDTH * HEIGHT // 2
BACKGROUND_CODE = 1
CELL_WIDTH = 52
CELL_HEIGHT = 64
GAP_X = 4
GAP_Y = 4
GRID_X0 = 34
GRID_Y0 = 30
CODE_COUNT = 8

SOURCE_ORDER_CS1 = tuple(range(8))
SOURCE_ORDER_CS2 = tuple(reversed(SOURCE_ORDER_CS1))
COMBINATIONS = (
    (4, 2),
    (4, 3),
    (4, 5),
    (4, 6),
    (7, 2),
    (7, 3),
    (7, 5),
    (7, 6),
)

CODE_RGB = {
    0: (20, 20, 20),
    1: (245, 245, 238),
    2: (235, 210, 25),
    3: (185, 35, 45),
    4: (45, 90, 170),
    5: (30, 135, 190),
    6: (30, 125, 80),
    7: (60, 55, 130),
}


class ChromaGridError(RuntimeError):
    """The fixed chroma-grid contract was not met."""


class Role(str, Enum):
    WHITE = "white"
    SOURCE = "source"
    MID = "mid"
    TARGET = "target"


def fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for item in data:
        value ^= item
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def _set_pixel(frame: bytearray, x: int, y: int, code: int) -> None:
    offset = y * (WIDTH // 2) + x // 2
    if x & 1:
        frame[offset] = (frame[offset] & 0xF0) | code
    else:
        frame[offset] = (frame[offset] & 0x0F) | (code << 4)


def _fill_cell(frame: bytearray, controller: int, row: int, column: int, code: int) -> None:
    x0 = controller * HALF_WIDTH + GRID_X0 + column * (CELL_WIDTH + GAP_X)
    y0 = GRID_Y0 + row * (CELL_HEIGHT + GAP_Y)
    pair = bytes(((code << 4) | code,)) * (CELL_WIDTH // 2)
    row_bytes = WIDTH // 2
    for y in range(y0, y0 + CELL_HEIGHT):
        offset = y * row_bytes + x0 // 2
        frame[offset : offset + CELL_WIDTH // 2] = pair


def _code_for(role: Role, source: int, combination: tuple[int, int]) -> int:
    if role is Role.SOURCE:
        return source
    if role is Role.MID:
        return combination[0]
    if role is Role.TARGET:
        return combination[1]
    raise ChromaGridError("white has no cell code")


def build_frame(role: Role) -> bytes:
    frame = bytearray((0x11,)) * FRAME_BYTES
    if role is Role.WHITE:
        return bytes(frame)
    for controller, source_order in enumerate((SOURCE_ORDER_CS1, SOURCE_ORDER_CS2)):
        combination_order = COMBINATIONS if controller == 0 else tuple(reversed(COMBINATIONS))
        for row, source in enumerate(source_order):
            for column, combination in enumerate(combination_order):
                _fill_cell(
                    frame,
                    controller,
                    row,
                    column,
                    _code_for(role, source, combination),
                )
    return bytes(frame)


def unpack_codes(frame: bytes) -> list[int]:
    if len(frame) != FRAME_BYTES:
        raise ChromaGridError("frame length differs")
    result: list[int] = []
    for item in frame:
        result.extend((item >> 4, item & 0x0F))
    if any(code not in range(CODE_COUNT) for code in result):
        raise ChromaGridError("frame contains a code outside 0..7")
    return result


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != FRAME_BYTES:
        raise ChromaGridError("invalid controller stream request")
    row_bytes = WIDTH // 2
    half_row_bytes = HALF_WIDTH // 2
    offset = controller * half_row_bytes
    return b"".join(
        frame[y * row_bytes + offset : y * row_bytes + offset + half_row_bytes]
        for y in range(HEIGHT)
    )


def frame_identity(frame: bytes) -> dict[str, Any]:
    codes = unpack_codes(frame)
    streams = [controller_stream(frame, controller) for controller in (0, 1)]
    if any(len(stream) != CONTROLLER_BYTES for stream in streams):
        raise ChromaGridError("controller stream length differs")
    return {
        "bytes": len(frame),
        "sha256": hashlib.sha256(frame).hexdigest(),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "histogram": [codes.count(code) for code in range(CODE_COUNT)],
        "controllers": [
            {
                "index": index + 1,
                "bytes": len(stream),
                "sha256": hashlib.sha256(stream).hexdigest(),
                "fnv1a": f"0x{fnv1a(stream):08X}",
            }
            for index, stream in enumerate(streams)
        ],
    }


def semantic_sequences() -> list[dict[str, int]]:
    records: list[dict[str, int]] = []
    for controller, source_order in enumerate((SOURCE_ORDER_CS1, SOURCE_ORDER_CS2), 1):
        combinations = COMBINATIONS if controller == 1 else tuple(reversed(COMBINATIONS))
        for row, source in enumerate(source_order):
            for column, (mid, target) in enumerate(combinations):
                records.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "source": source,
                        "mid": mid,
                        "target": target,
                    }
                )
    keys = [(r["controller"], r["source"], r["mid"], r["target"]) for r in records]
    if len(records) != 128 or len(set(keys)) != 128:
        raise ChromaGridError("semantic sequence coverage differs")
    return records


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _action(role: Role, ordinal: int, prior_action_id: str | None, identity: dict[str, Any]) -> dict[str, Any]:
    descriptor = {
        "ordinal": ordinal,
        "role": role.value,
        "prior_action_id": prior_action_id,
        "frame_sha256": identity["sha256"],
        "cs1_dtm_sha256": identity["controllers"][0]["sha256"],
        "cs2_dtm_sha256": identity["controllers"][1]["sha256"],
        "visible_refresh_count": 1,
    }
    descriptor_id = hashlib.sha256(_canonical(descriptor)).hexdigest()
    action_id = hashlib.sha256(
        _canonical({"descriptor_id": descriptor_id, "campaign": "EC5_CHROMA_GRID_V1"})
    ).hexdigest()
    return {**descriptor, "descriptor_id": descriptor_id, "action_id": action_id}


def build_manifest() -> tuple[dict[str, Any], dict[Role, bytes]]:
    frames = {role: build_frame(role) for role in Role}
    identities = {role: frame_identity(frame) for role, frame in frames.items()}
    roles = (Role.WHITE, Role.SOURCE, Role.MID, Role.TARGET, Role.WHITE)
    actions: list[dict[str, Any]] = []
    prior: str | None = None
    for ordinal, role in enumerate(roles, 1):
        action = _action(role, ordinal, prior, identities[role])
        actions.append(action)
        prior = action["action_id"]
    sequences = semantic_sequences()
    semantic_counts = Counter((r["source"], r["mid"], r["target"]) for r in sequences)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-fixed-factory-otp-chroma-grid-offline-bundle",
        "campaign_id": "EC5_CHROMA_GRID_V1",
        "classification": "FACTORY_OTP_FIXED_CHROMA_HISTORY_NO_RUNTIME_LUT",
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "frame_bytes": FRAME_BYTES,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "grid_x0_per_half": GRID_X0,
            "grid_y0": GRID_Y0,
        },
        "history_design": {
            "sources": list(range(8)),
            "mids": [4, 7],
            "targets": [2, 3, 5, 6],
            "semantic_sequences_per_controller": 64,
            "physical_rois": 128,
            "unique_semantic_sequence_count": len(semantic_counts),
            "left_right_layout": "CS1_FORWARD_CS2_REVERSED_180_DEGREE_POSITIONAL_MIRROR",
            "white_gaps": True,
        },
        "frames": {role.value: identities[role] for role in Role},
        "actions": actions,
        "visible_action_count": len(actions),
        "automatic_chaining": False,
        "retry_allowed": False,
        "runtime_lut_write_present": False,
        "otp_write_present": False,
        "live_authorized": False,
    }
    unsigned = dict(manifest)
    manifest["integrity"] = {
        "canonical_sha256": hashlib.sha256(_canonical(unsigned)).hexdigest(),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return manifest, frames


def _preview(frame: bytes, path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    image.putdata([CODE_RGB[code] for code in unpack_codes(frame)])
    image.save(path)


def write_bundle(output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists():
        raise ChromaGridError(f"output already exists: {output}")
    output.mkdir(parents=True)
    manifest, frames = build_manifest()
    for role, frame in frames.items():
        (output / f"{role.value}.bin").write_bytes(frame)
        _preview(frame, output / f"{role.value}.png")
    (output / "semantic-sequences.json").write_bytes(
        json.dumps(semantic_sequences(), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    (output / "manifest.json").write_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = write_bundle(args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
