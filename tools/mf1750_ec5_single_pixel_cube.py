#!/usr/bin/env python3
"""Build the fixed five-action 8^3 single-pixel history cube offline."""

from __future__ import annotations

import argparse
import csv
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw


WIDTH = 1024
HEIGHT = 600
HALF_WIDTH = 512
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_BYTES = HALF_WIDTH * HEIGHT // 2
CODE_COUNT = 8
BACKGROUND_CODE = 1

CONTROLLER_COUNT = 2
GRID_COLUMNS_PER_CONTROLLER = 11
GRID_ROWS = 24
CELL_WIDTH = 40
CELL_HEIGHT = 22
GAP_X = 4
GAP_Y = 2
GRID_X0 = 16
GRID_Y0 = 13
SLOTS_PER_CONTROLLER = GRID_COLUMNS_PER_CONTROLLER * GRID_ROWS
TOTAL_SLOTS = CONTROLLER_COUNT * SLOTS_PER_CONTROLLER
RECIPE_COUNT = CODE_COUNT**3
REFERENCE_COUNT_PER_CONTROLLER = CODE_COUNT
CELL_PIXELS = CELL_WIDTH * CELL_HEIGHT

CAMPAIGN_ID = "EC5_SINGLE_PIXEL_CUBE_V1"
CLASSIFICATION = "FACTORY_OTP_FULL_SCREEN_8_CUBED_SINGLE_PIXEL_HISTORY_NO_DITHER"

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


class SinglePixelCubeError(RuntimeError):
    """The fixed single-pixel cube contract was not met."""


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


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _recipe_index(source: int, mid: int, target: int) -> int:
    return (source * CODE_COUNT + mid) * CODE_COUNT + target


def _recipe_records_for_controller(controller: int) -> list[dict[str, Any]]:
    if controller not in (0, 1):
        raise SinglePixelCubeError("controller differs from 0/1")
    records: list[dict[str, Any]] = []
    for source in range(CODE_COUNT):
        for mid in range(CODE_COUNT):
            for target in range(CODE_COUNT):
                if (source + mid + target) & 1 != controller:
                    continue
                records.append(
                    {
                        "kind": "recipe",
                        "recipe_index": _recipe_index(source, mid, target),
                        "source": source,
                        "mid": mid,
                        "target": target,
                    }
                )
    if len(records) != RECIPE_COUNT // 2:
        raise SinglePixelCubeError("controller recipe count differs")
    return records


def roi_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for controller in range(CONTROLLER_COUNT):
        assigned = _recipe_records_for_controller(controller)
        assigned.extend(
            {
                "kind": "reference",
                "recipe_index": None,
                "source": code,
                "mid": code,
                "target": code,
            }
            for code in range(CODE_COUNT)
        )
        if len(assigned) != SLOTS_PER_CONTROLLER:
            raise SinglePixelCubeError("slot assignment differs")
        for slot, assignment in enumerate(assigned):
            row, column = divmod(slot, GRID_COLUMNS_PER_CONTROLLER)
            x0 = controller * HALF_WIDTH + GRID_X0 + column * (CELL_WIDTH + GAP_X)
            y0 = GRID_Y0 + row * (CELL_HEIGHT + GAP_Y)
            records.append(
                {
                    "roi_index": len(records),
                    "controller": controller + 1,
                    "controller_slot": slot,
                    "row": row,
                    "column": column,
                    "x0": x0,
                    "y0": y0,
                    "x1_exclusive": x0 + CELL_WIDTH,
                    "y1_exclusive": y0 + CELL_HEIGHT,
                    **assignment,
                }
            )
    _validate_roi_records(records)
    return records


def _validate_roi_records(records: list[dict[str, Any]]) -> None:
    if len(records) != TOTAL_SLOTS:
        raise SinglePixelCubeError("physical ROI count differs")
    recipes = [record for record in records if record["kind"] == "recipe"]
    references = [record for record in records if record["kind"] == "reference"]
    recipe_keys = {
        (record["source"], record["mid"], record["target"]) for record in recipes
    }
    if len(recipes) != RECIPE_COUNT or len(recipe_keys) != RECIPE_COUNT:
        raise SinglePixelCubeError("8^3 recipe coverage differs")
    if len(references) != CONTROLLER_COUNT * REFERENCE_COUNT_PER_CONTROLLER:
        raise SinglePixelCubeError("reference ROI count differs")
    for controller in (1, 2):
        controller_records = [r for r in records if r["controller"] == controller]
        controller_recipes = [r for r in controller_records if r["kind"] == "recipe"]
        controller_refs = [r for r in controller_records if r["kind"] == "reference"]
        if len(controller_records) != SLOTS_PER_CONTROLLER:
            raise SinglePixelCubeError("controller slot count differs")
        if len(controller_recipes) != RECIPE_COUNT // 2:
            raise SinglePixelCubeError("controller recipe split differs")
        if [r["target"] for r in controller_refs] != list(range(CODE_COUNT)):
            raise SinglePixelCubeError("controller references differ")
        for axis in ("source", "mid", "target"):
            counts = [
                sum(r[axis] == code for r in controller_recipes)
                for code in range(CODE_COUNT)
            ]
            if counts != [32] * CODE_COUNT:
                raise SinglePixelCubeError(f"controller {axis} distribution differs")


def _fill_cell(frame: bytearray, record: dict[str, Any], code: int) -> None:
    if code not in range(CODE_COUNT):
        raise SinglePixelCubeError("cell code differs from 0..7")
    x0 = int(record["x0"])
    y0 = int(record["y0"])
    if x0 & 1 or CELL_WIDTH & 1:
        raise SinglePixelCubeError("cell is not packed-byte aligned")
    pair = bytes(((code << 4) | code,)) * (CELL_WIDTH // 2)
    row_bytes = WIDTH // 2
    for y in range(y0, y0 + CELL_HEIGHT):
        offset = y * row_bytes + x0 // 2
        frame[offset : offset + CELL_WIDTH // 2] = pair


def _code_for(role: Role, record: dict[str, Any]) -> int:
    if role is Role.SOURCE:
        return int(record["source"])
    if role is Role.MID:
        return int(record["mid"])
    if role is Role.TARGET:
        return int(record["target"])
    raise SinglePixelCubeError("white has no ROI code")


def build_frame(role: Role) -> bytes:
    frame = bytearray((0x11,)) * FRAME_BYTES
    if role is Role.WHITE:
        return bytes(frame)
    for record in roi_records():
        _fill_cell(frame, record, _code_for(role, record))
    return bytes(frame)


def unpack_codes(frame: bytes) -> list[int]:
    if len(frame) != FRAME_BYTES:
        raise SinglePixelCubeError("frame length differs")
    result: list[int] = []
    for item in frame:
        result.extend((item >> 4, item & 0x0F))
    if any(code not in range(CODE_COUNT) for code in result):
        raise SinglePixelCubeError("frame contains a code outside 0..7")
    return result


def controller_stream(frame: bytes, controller: int) -> bytes:
    if controller not in (0, 1) or len(frame) != FRAME_BYTES:
        raise SinglePixelCubeError("invalid controller stream request")
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


def _action(
    role: Role, ordinal: int, prior: str | None, identity: dict[str, Any]
) -> dict[str, Any]:
    descriptor = {
        "ordinal": ordinal,
        "role": role.value,
        "prior_action_id": prior,
        "frame_sha256": identity["sha256"],
        "cs1_dtm_sha256": identity["controllers"][0]["sha256"],
        "cs2_dtm_sha256": identity["controllers"][1]["sha256"],
        "visible_refresh_count": 1,
    }
    descriptor_id = hashlib.sha256(_canonical(descriptor)).hexdigest()
    action_id = hashlib.sha256(
        _canonical({"descriptor_id": descriptor_id, "campaign": CAMPAIGN_ID})
    ).hexdigest()
    return {**descriptor, "descriptor_id": descriptor_id, "action_id": action_id}


def build_manifest() -> tuple[dict[str, Any], dict[Role, bytes]]:
    records = roi_records()
    frames = {role: build_frame(role) for role in Role}
    identities = {role: frame_identity(frame) for role, frame in frames.items()}
    actions: list[dict[str, Any]] = []
    prior: str | None = None
    for ordinal, role in enumerate(
        (Role.WHITE, Role.SOURCE, Role.MID, Role.TARGET, Role.WHITE), 1
    ):
        action = _action(role, ordinal, prior, identities[role])
        actions.append(action)
        prior = action["action_id"]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-fixed-factory-otp-single-pixel-cube-offline-bundle",
        "campaign_id": CAMPAIGN_ID,
        "classification": CLASSIFICATION,
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "frame_bytes": FRAME_BYTES,
            "controllers": CONTROLLER_COUNT,
            "columns_per_controller": GRID_COLUMNS_PER_CONTROLLER,
            "rows": GRID_ROWS,
            "slots_per_controller": SLOTS_PER_CONTROLLER,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
            "grid_x0_per_half": GRID_X0,
            "grid_y0": GRID_Y0,
        },
        "history_design": {
            "codes": list(range(CODE_COUNT)),
            "unique_three_step_recipes": RECIPE_COUNT,
            "physical_recipe_rois": RECIPE_COUNT,
            "reference_rois": CONTROLLER_COUNT * REFERENCE_COUNT_PER_CONTROLLER,
            "physical_rois": len(records),
            "assignment": "PARITY_BALANCED_256_RECIPES_PLUS_8_REFERENCES_PER_CONTROLLER",
            "uniform_code_inside_each_roi": True,
            "white_gaps": True,
            "spatial_mixing": False,
        },
        "frames": {role.value: identities[role] for role in Role},
        "actions": actions,
        "visible_action_count": len(actions),
        "profile_source": "factory_otp",
        "spi_hz": 1_000_000,
        "automatic_chaining": False,
        "retry_allowed": False,
        "runtime_lut_write_present": False,
        "otp_write_present": False,
        "partial_refresh_present": False,
        "window_command_present": False,
        "interlace_0x86_present": False,
        "power_cut_during_refresh_present": False,
        "spi_sweep_present": False,
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


def _annotated_layout(path: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), CODE_RGB[BACKGROUND_CODE])
    draw = ImageDraw.Draw(image)
    for record in roi_records():
        colour = CODE_RGB[int(record["target"])]
        box = (
            int(record["x0"]),
            int(record["y0"]),
            int(record["x1_exclusive"]) - 1,
            int(record["y1_exclusive"]) - 1,
        )
        draw.rectangle(box, fill=colour)
        label = (
            f"R{record['target']}"
            if record["kind"] == "reference"
            else f"{record['source']}{record['mid']}{record['target']}"
        )
        brightness = sum(colour)
        text_colour = (255, 255, 255) if brightness < 300 else (0, 0, 0)
        draw.text((box[0] + 2, box[1] + 5), label, fill=text_colour)
    image.save(path)


def _write_roi_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = (
        "roi_index",
        "controller",
        "controller_slot",
        "row",
        "column",
        "x0",
        "y0",
        "x1_exclusive",
        "y1_exclusive",
        "kind",
        "recipe_index",
        "source",
        "mid",
        "target",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def write_bundle(output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists():
        raise SinglePixelCubeError(f"output already exists: {output}")
    output.mkdir(parents=True)
    manifest, frames = build_manifest()
    records = roi_records()
    for role, frame in frames.items():
        (output / f"{role.value}.bin").write_bytes(frame)
        _preview(frame, output / f"{role.value}.png")
    _annotated_layout(output / "target-annotated-layout.png")
    (output / "roi-map.json").write_bytes(
        json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    _write_roi_csv(output / "roi-map.csv", records)
    (output / "manifest.json").write_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
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
