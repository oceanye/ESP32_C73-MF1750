#!/usr/bin/env python3
"""Generate and validate the blocked offline EC5 0x0..0x7 atlas assets.

The raw fixtures contain literal 4-bit codes, not predicted physical colours.
No function in this module can access a device, network, serial port, claim
registry, or display endpoint. Hardware execution remains blocked until a
future isolated U07T pilot and a newer clean-white recovery are both sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Mapping, Sequence
import zlib


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-eightcode-balanced-atlas-assets"
LAYOUT_ID = "EC5_EIGHTCODE_DUAL_BALANCED_64_V1"
CLASSIFICATION = "OFFLINE_TECHNICAL_CODES_NOT_PHYSICAL_COLOUR_CLAIMS"
EXECUTION_ELIGIBLE = False
WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT
CONTROLLER_WIDTH = WIDTH // 2
CONTROLLER_ROW_BYTES = CONTROLLER_WIDTH // 2
CONTROLLER_FRAME_BYTES = CONTROLLER_ROW_BYTES * HEIGHT
PATCH_SIDE = 64
BORDER = 2
PATCH_PIXELS = PATCH_SIDE * PATCH_SIDE
PAYLOAD_PIXELS_PER_CODE = 2 * PATCH_PIXELS
LOCAL_X = (48, 160, 272, 384)
Y0 = (190, 346)
CS1_ORDER = tuple(range(8))
CS2_ORDER = tuple(reversed(range(8)))
ROLES = ("atlas", "target_u04", "target_u07", "white")

# Codes 0/1/2/3/5/6 use the project's frozen preview mapping
# (black/white/yellow/red/blue/green). Unknown codes 0x4 and 0x7 use
# deliberately conspicuous locator colours in PNGs only. The raw fixtures and
# scientific identities contain codes, never RGB claims.
PREVIEW_PALETTE = (
    (0, 0, 0),
    (255, 255, 255),
    (245, 210, 35),
    (230, 45, 45),
    (0, 190, 220),
    (40, 80, 220),
    (40, 180, 75),
    (210, 55, 210),
)

FROZEN_IDENTITIES: Mapping[str, Mapping[str, tuple[str, int]]] = {
    "atlas": {
        "frame": (
            "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b",
            0xCE553145,
        ),
        "cs1": (
            "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7",
            0x639C1785,
        ),
        "cs2": (
            "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943",
            0x1BADB785,
        ),
    },
    "target_u04": {
        "frame": (
            "25340f6a4a0bc71ec95b74e349e79b4a9e317c415616b6e08f43a54db62b8f22",
            0x7DFB1145,
        ),
        "cs1": (
            "ba8cfa2ff4e0c4c4b43302551de097cfa8902007b8c8edbd60b8ac8625001fbf",
            0x21B7D785,
        ),
        "cs2": (
            "ba8cfa2ff4e0c4c4b43302551de097cfa8902007b8c8edbd60b8ac8625001fbf",
            0x21B7D785,
        ),
    },
    "target_u07": {
        "frame": (
            "fd023d9b618ff464cc48928e0b8c598eb1adfa9ee0451ae07e4666d4a83fe72c",
            0x050A9145,
        ),
        "cs1": (
            "6715daad28d5b7e21892221d178e3011b3c5574b341f9f30027aae394f795ed9",
            0x253F9785,
        ),
        "cs2": (
            "6715daad28d5b7e21892221d178e3011b3c5574b341f9f30027aae394f795ed9",
            0x253F9785,
        ),
    },
    "white": {
        "frame": (
            "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
            0x13340DC5,
        ),
        "cs1": (
            "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
            0xB7A855C5,
        ),
        "cs2": (
            "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
            0xB7A855C5,
        ),
    },
}

FROZEN_HISTOGRAMS: Mapping[str, tuple[int, ...]] = {
    "atlas": (16_640, 548_608, 8_192, 8_192, 8_192, 8_192, 8_192, 8_192),
    "target_u04": (8_448, 540_416, 0, 0, 65_536, 0, 0, 0),
    "target_u07": (8_448, 540_416, 0, 0, 0, 0, 0, 65_536),
    "white": (0, 614_400, 0, 0, 0, 0, 0, 0),
}


class EightCodeAtlasError(ValueError):
    """The offline atlas contract or immutable asset bytes differ."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _set_pixel(frame: bytearray, x: int, y: int, code: int) -> None:
    offset = y * ROW_BYTES + x // 2
    if x & 1:
        frame[offset] = (frame[offset] & 0xF0) | code
    else:
        frame[offset] = (frame[offset] & 0x0F) | (code << 4)


def _pixel(frame: bytes, x: int, y: int) -> int:
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0x0F if x & 1 else value >> 4


def frozen_rois() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for controller, offset, order in (
        ("CS1", 0, CS1_ORDER),
        ("CS2", CONTROLLER_WIDTH, CS2_ORDER),
    ):
        for slot, code in enumerate(order):
            row, column = divmod(slot, 4)
            x0 = offset + LOCAL_X[column]
            y0 = Y0[row]
            result.append(
                {
                    "roi_id": f"{controller}-S{slot}-C{code}",
                    "controller": controller,
                    "slot": slot,
                    "row": row,
                    "column": column,
                    "code": code,
                    "counterbalanced_slot": 7 - slot,
                    "rect": {
                        "x0": x0,
                        "y0": y0,
                        "x1_exclusive": x0 + PATCH_SIDE,
                        "y1_exclusive": y0 + PATCH_SIDE,
                    },
                    "outline_rect": {
                        "x0": x0 - BORDER,
                        "y0": y0 - BORDER,
                        "x1_exclusive": x0 + PATCH_SIDE + BORDER,
                        "y1_exclusive": y0 + PATCH_SIDE + BORDER,
                    },
                    "payload_pixels": PATCH_PIXELS,
                }
            )
    return result


def _role_code(role: str, atlas_code: int) -> int:
    if role == "atlas":
        return atlas_code
    if role == "target_u04":
        return 4
    if role == "target_u07":
        return 7
    if role == "white":
        return 1
    raise EightCodeAtlasError(f"unknown role {role}")


def build_frame(role: str) -> bytes:
    if role not in ROLES:
        raise EightCodeAtlasError(f"unknown role {role}")
    frame = bytearray(b"\x11" * FRAME_BYTES)
    if role == "white":
        return bytes(frame)
    for roi in frozen_rois():
        outline = roi["outline_rect"]
        rect = roi["rect"]
        for y in range(outline["y0"], outline["y1_exclusive"]):
            for x in range(outline["x0"], outline["x1_exclusive"]):
                _set_pixel(frame, x, y, 0)
        code = _role_code(role, int(roi["code"]))
        for y in range(rect["y0"], rect["y1_exclusive"]):
            for x in range(rect["x0"], rect["x1_exclusive"]):
                _set_pixel(frame, x, y, code)
    return bytes(frame)


def controller_stream(frame: bytes, source_half: int) -> bytes:
    if len(frame) != FRAME_BYTES or source_half not in (0, 1):
        raise EightCodeAtlasError("controller stream input differs")
    output = bytearray(CONTROLLER_FRAME_BYTES)
    for y in range(HEIGHT):
        source = y * ROW_BYTES + source_half * CONTROLLER_ROW_BYTES
        target = y * CONTROLLER_ROW_BYTES
        output[target : target + CONTROLLER_ROW_BYTES] = frame[
            source : source + CONTROLLER_ROW_BYTES
        ]
    return bytes(output)


def histogram(frame: bytes) -> tuple[int, ...]:
    if len(frame) != FRAME_BYTES:
        raise EightCodeAtlasError("frame length differs")
    counts = [0] * 8
    for value in frame:
        for code in (value >> 4, value & 0x0F):
            if code > 7:
                raise EightCodeAtlasError("frame contains a code above 0x7")
            counts[code] += 1
    return tuple(counts)


def identity(data: bytes) -> dict[str, Any]:
    fnv = _fnv1a(data)
    return {
        "bytes": len(data),
        "sha256": _sha(data),
        "fnv1a_u32": fnv,
        "fnv1a_hex": f"0x{fnv:08x}",
    }


def validate_frame(role: str, frame: bytes) -> None:
    expected = build_frame(role)
    if frame != expected:
        raise EightCodeAtlasError(f"{role} frame differs from frozen geometry")
    streams = {
        "frame": frame,
        "cs1": controller_stream(frame, 0),
        "cs2": controller_stream(frame, 1),
    }
    for name, payload in streams.items():
        if (_sha(payload), _fnv1a(payload)) != FROZEN_IDENTITIES[role][name]:
            raise EightCodeAtlasError(f"{role} {name} identity drifted")
    if histogram(frame) != FROZEN_HISTOGRAMS[role]:
        raise EightCodeAtlasError(f"{role} histogram drifted")
    if role == "atlas":
        payload_counts = [0] * 8
        for roi in frozen_rois():
            rect = roi["rect"]
            values = {
                _pixel(frame, x, y)
                for y in range(rect["y0"], rect["y1_exclusive"])
                for x in range(rect["x0"], rect["x1_exclusive"])
            }
            if values != {roi["code"]}:
                raise EightCodeAtlasError("atlas ROI is not a pure code region")
            payload_counts[int(roi["code"])] += PATCH_PIXELS
        if payload_counts != [PAYLOAD_PIXELS_PER_CODE] * 8:
            raise EightCodeAtlasError("atlas payload code areas are not equal")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(
        ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
    )


def preview_png(frame: bytes) -> bytes:
    if len(frame) != FRAME_BYTES:
        raise EightCodeAtlasError("preview frame length differs")
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)
        for x in range(WIDTH):
            rows.extend(PREVIEW_PALETTE[_pixel(frame, x, y)])
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + _png_chunk(b"IEND", b"")
    )


def transition_candidates() -> list[dict[str, Any]]:
    return [
        {
            "branch_id": "ATLAS_ONLY_VISUAL",
            "roles": ["atlas", "external_rc2g_white"],
            "visible_refreshes": 2,
            "purpose": "descriptive eight-code side-by-side atlas only",
        },
        {
            "branch_id": "STAGE_B_KNOWN6_TO_U04",
            "roles": ["existing_stage_b_primer", "existing_stage_b_u04_target", "external_rc2g_white"],
            "visible_refreshes": 3,
            "purpose": "reuse audited six-known-initial-state to U04 branch",
        },
        {
            "branch_id": "STAGE_B_KNOWN6_TO_U07",
            "roles": ["existing_stage_b_primer", "existing_stage_b_u07_target", "external_rc2g_white"],
            "visible_refreshes": 3,
            "purpose": "reuse audited six-known-initial-state to U07 branch after U07T gate",
        },
        {
            "branch_id": "ATLAS_TO_U04_TO_U07",
            "roles": ["atlas", "target_u04", "target_u07", "external_rc2g_white"],
            "visible_refreshes": 4,
            "purpose": "all eight initial codes to U04, then directional U04-to-U07",
        },
        {
            "branch_id": "ATLAS_TO_U07_TO_U04",
            "roles": ["atlas", "target_u07", "target_u04", "external_rc2g_white"],
            "visible_refreshes": 4,
            "purpose": "all eight initial codes to U07, then directional U07-to-U04",
        },
    ]


def build_manifest() -> tuple[dict[str, Any], dict[str, bytes]]:
    assets: dict[str, bytes] = {}
    role_blocks: dict[str, Any] = {}
    for role in ROLES:
        frame = build_frame(role)
        validate_frame(role, frame)
        png = preview_png(frame)
        raw_name = f"eightcode-{role}.raw"
        png_name = f"eightcode-{role}.preview.png"
        assets[raw_name] = frame
        assets[png_name] = png
        role_blocks[role] = {
            "frame": identity(frame),
            "cs1_dtm": identity(controller_stream(frame, 0)),
            "cs2_dtm": identity(controller_stream(frame, 1)),
            "histogram": {
                f"0x{code:x}": count
                for code, count in enumerate(histogram(frame))
            },
            "raw_file": raw_name,
            "preview_file": png_name,
            "preview_sha256": _sha(png),
        }
    root: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "layout_id": LAYOUT_ID,
        "execution_eligible": EXECUTION_ELIGIBLE,
        "hardware_action_id": None,
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "patch_side": PATCH_SIDE,
            "border": BORDER,
            "payload_pixels_per_code": PAYLOAD_PIXELS_PER_CODE,
            "cs1_order": list(CS1_ORDER),
            "cs2_order": list(CS2_ORDER),
            "position_counterbalance": "for every code, CS1 slot + CS2 slot = 7",
            "rois": frozen_rois(),
        },
        "roles": role_blocks,
        "transition_candidates": transition_candidates(),
        "existing_stage_b_reuse": {
            "release_canonical_sha256": "b500fee26d57b11b0bf9f8441076dce5982516429794bed49f04f4ae2bcbdb04",
            "layout_id": "EC5_SIXSTATE_MIRROR24_NODITHER_V1",
            "initial_codes": [1, 0, 3, 2, 5, 6],
            "policy": "reuse identities and validators; never copy historical authorization or claims",
        },
        "hardware_gate": {
            "blocked": True,
            "required_before_refreeze": [
                "isolated_u07t_v2_complete_pass_result_and_permanent_technical_claim",
                "u07t_manual_observation",
                "newer_post_u07t_rc2g_white_result_and_permanent_claim",
                "newer_post_u07t_clean_white_and_electrical_manual_observation",
                "fresh_formal_u07_claim_absence",
                "new_action_identity_and_release",
            ],
            "startup_refresh": False,
            "automatic_execute": False,
            "retry": False,
            "recovery": False,
            "raw_frame_ingress": False,
            "dithering_present": False,
            "spatial_mixing_present": False,
            "custom_lut_or_waveform": False,
        },
        "preview_notice": (
            "PNG codes 0/1/2/3/5/6 use the frozen black/white/yellow/red/blue/"
            "green preview mapping; RGB values for codes 0x4 and 0x7 are "
            "locators only and do not predict physical panel colours"
        ),
        "device_io_performed": False,
        "network_io_performed": False,
        "claims_created": False,
    }
    asset_id = _sha(canonical_json_bytes(root))
    root["offline_asset_id"] = asset_id
    root["integrity"] = {
        "canonical_sha256": _sha(canonical_json_bytes(root)),
        "scope": "entire manifest excluding integrity; canonical UTF-8 JSON",
    }
    manifest_payload = json.dumps(
        root, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8") + b"\n"
    assets["eightcode-atlas-manifest.json"] = manifest_payload
    return root, assets


def _read_regular(path: Path, *, maximum: int) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise EightCodeAtlasError(f"{path.name} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise EightCodeAtlasError(f"{path.name} size differs")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EightCodeAtlasError(f"could not read {path}: {error}") from error
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise EightCodeAtlasError(f"{path.name} changed while read")
    return payload


def generate(output: Path) -> Path:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise EightCodeAtlasError("output already exists; refusing overwrite")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise EightCodeAtlasError("output parent must be a regular directory")
    _, assets = build_manifest()
    output.mkdir()
    try:
        for name, payload in assets.items():
            with (output / name).open("xb") as stream:
                stream.write(payload)
    except (OSError, FileExistsError) as error:
        raise EightCodeAtlasError(f"could not publish asset: {error}") from error
    return output / "eightcode-atlas-manifest.json"


def validate(manifest_file: Path) -> dict[str, Any]:
    manifest_file = Path(manifest_file).resolve(strict=True)
    expected, assets = build_manifest()
    payload = _read_regular(manifest_file, maximum=4 << 20)
    try:
        actual = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EightCodeAtlasError(f"manifest is invalid JSON: {error}") from error
    if actual != expected:
        raise EightCodeAtlasError("manifest differs from frozen contract")
    if _sha(canonical_json_bytes({k: v for k, v in actual.items() if k != "integrity"})) != actual["integrity"]["canonical_sha256"]:
        raise EightCodeAtlasError("manifest canonical integrity differs")
    for name, wanted in assets.items():
        if name == manifest_file.name:
            continue
        maximum = FRAME_BYTES if name.endswith(".raw") else 8 << 20
        if _read_regular(manifest_file.parent / name, maximum=maximum) != wanted:
            raise EightCodeAtlasError(f"{name} bytes differ")
    return {
        "valid": True,
        "kind": KIND,
        "layout_id": LAYOUT_ID,
        "offline_asset_id": expected["offline_asset_id"],
        "manifest_canonical_sha256": expected["integrity"]["canonical_sha256"],
        "execution_eligible": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "claims_created": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("generate", allow_abbrev=False)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate", allow_abbrev=False)
    check.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.output)
            result = validate(manifest)
            result["manifest"] = str(manifest)
        else:
            result = validate(args.manifest)
    except (EightCodeAtlasError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
