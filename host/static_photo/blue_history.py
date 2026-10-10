"""Deterministic A/A-prime fixtures for the 16 blue history recipes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    pack_pixels,
    validate_frame,
)

from .common import attach_integrity, canonical_json_bytes, prepare_empty_output_dir
from .history_palette import TRANSPORT_CODES


BLUE_TARGETS = (4, 7)
BACKGROUND_CODE = 1
FACTORY_PROFILE_ID = "factory_otp"
CELL_WIDTH = 220
CELL_HEIGHT = 128
CELL_GAP_X = 8
CELL_GAP_Y = 8
HALF_MARGIN_X = 32
MARGIN_Y = 32
PREVIEW_RGB = {
    0: (20, 20, 20),
    1: (245, 245, 240),
    2: (230, 210, 0),
    3: (190, 25, 35),
    4: (40, 95, 175),
    5: (15, 120, 205),
    6: (15, 115, 70),
    7: (40, 95, 175),
}


class BlueHistoryPlanError(ValueError):
    """Raised when the fixed 16-recipe plan differs."""


@dataclass(frozen=True)
class BlueHistoryROI:
    batch_id: Literal["A", "A-prime"]
    recipe_id: str
    controller: Literal["CS1", "CS2"]
    source_code: int
    target_code: int
    x: int
    y: int
    width: int = CELL_WIDTH
    height: int = CELL_HEIGHT

    def mapping(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "recipe_id": self.recipe_id,
            "controller": self.controller,
            "source_code": self.source_code,
            "target_code": self.target_code,
            "rectangle": {
                "x": self.x,
                "y": self.y,
                "x1_exclusive": self.x + self.width,
                "y1_exclusive": self.y + self.height,
            },
        }


def recipe_id(source_code: int, target_code: int) -> str:
    if source_code not in TRANSPORT_CODES or target_code not in BLUE_TARGETS:
        raise BlueHistoryPlanError("blue recipe codes differ")
    return f"factory-otp-source{source_code}-target{target_code}"


def batch_rois(batch_id: Literal["A", "A-prime"]) -> tuple[BlueHistoryROI, ...]:
    if batch_id not in ("A", "A-prime"):
        raise BlueHistoryPlanError("batch_id must be A or A-prime")
    rois: list[BlueHistoryROI] = []
    for half, controller in enumerate(("CS1", "CS2")):
        target = (4, 7)[half] if batch_id == "A" else (7, 4)[half]
        source_order = range(8) if batch_id == "A" else range(7, -1, -1)
        for slot, source in enumerate(source_order):
            row, column = divmod(slot, 2)
            x = half * (WIDTH // 2) + HALF_MARGIN_X + column * (CELL_WIDTH + CELL_GAP_X)
            y = MARGIN_Y + row * (CELL_HEIGHT + CELL_GAP_Y)
            rois.append(
                BlueHistoryROI(
                    batch_id,
                    recipe_id(source, target),
                    controller,  # type: ignore[arg-type]
                    source,
                    target,
                    x,
                    y,
                )
            )
    return tuple(rois)


def _fill(codes: bytearray, roi: BlueHistoryROI, code: int) -> None:
    for y in range(roi.y, roi.y + roi.height):
        start = y * WIDTH + roi.x
        codes[start : start + roi.width] = bytes((code,)) * roi.width


def build_batch_frame(
    batch_id: Literal["A", "A-prime"], role: Literal["primer", "target", "white"]
) -> bytes:
    if role not in ("primer", "target", "white"):
        raise BlueHistoryPlanError("role must be primer, target, or white")
    codes = bytearray((BACKGROUND_CODE,)) * (WIDTH * HEIGHT)
    if role != "white":
        for roi in batch_rois(batch_id):
            _fill(codes, roi, roi.source_code if role == "primer" else roi.target_code)
    result = pack_pixels(codes, allowed_colors=TRANSPORT_CODES)
    validate_frame(result, allowed_colors=TRANSPORT_CODES)
    return result


def _identity(payload: bytes) -> dict[str, Any]:
    return {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fnv1a": f"0x{fnv1a(payload):08X}",
    }


def _preview(batch_id: Literal["A", "A-prime"], role: str) -> bytes:
    frame = build_batch_frame(batch_id, role)  # type: ignore[arg-type]
    codes = np.empty((HEIGHT, WIDTH), dtype=np.uint8)
    packed = np.frombuffer(frame, dtype=np.uint8).reshape(HEIGHT, WIDTH // 2)
    codes[:, 0::2] = packed >> 4
    codes[:, 1::2] = packed & 0x0F
    rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for code, colour in PREVIEW_RGB.items():
        rgb[codes == code] = colour
    bgr = rgb[:, :, ::-1].copy()
    for roi in batch_rois(batch_id):
        cv2.rectangle(
            bgr,
            (roi.x, roi.y),
            (roi.x + roi.width - 1, roi.y + roi.height - 1),
            (128, 128, 128),
            1,
        )
        cv2.putText(
            bgr,
            f"s{roi.source_code}->t{roi.target_code}",
            (roi.x + 6, roi.y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255) if role != "white" else (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    ok, encoded = cv2.imencode(".png", bgr)
    if not ok:
        raise BlueHistoryPlanError("cannot encode preview")
    return encoded.tobytes()


def build_blue_history_bundle(output_dir: str | Path) -> dict[str, Any]:
    output = prepare_empty_output_dir(output_dir)
    batch_records: list[dict[str, Any]] = []
    for batch_id in ("A", "A-prime"):
        frame_records: dict[str, Any] = {}
        for role in ("primer", "target", "white"):
            frame = build_batch_frame(batch_id, role)  # type: ignore[arg-type]
            if len(frame) != FRAME_BYTES:
                raise AssertionError("frame byte count invariant failed")
            filename = f"{batch_id}-{role}.bin"
            (output / filename).write_bytes(frame)
            preview = _preview(batch_id, role)
            preview_name = f"{batch_id}-{role}-preview.png"
            (output / preview_name).write_bytes(preview)
            streams = [
                controller_stream(
                    frame,
                    ControllerMapping(source_half=half),
                    allowed_colors=TRANSPORT_CODES,
                )
                for half in (0, 1)
            ]
            frame_records[role] = {
                "file": filename,
                "identity": _identity(frame),
                "preview_file": preview_name,
                "preview_identity": _identity(preview),
                "controller_streams": {
                    "CS1": _identity(streams[0]),
                    "CS2": _identity(streams[1]),
                },
            }
        rois = [roi.mapping() for roi in batch_rois(batch_id)]
        batch_records.append(
            {
                "batch_id": batch_id,
                "visible_action_order": ["primer", "target", "white"],
                "powered_between_primer_and_target": True,
                "photo_timepoints_after_target_seconds": [5, 60, 600],
                "rois": rois,
                "frames": frame_records,
            }
        )

    all_recipe_ids = {
        roi.recipe_id for batch_id in ("A", "A-prime") for roi in batch_rois(batch_id)
    }
    expected_ids = {
        recipe_id(source, target) for source in range(8) for target in BLUE_TARGETS
    }
    if all_recipe_ids != expected_ids:
        raise AssertionError("16-recipe coverage invariant failed")
    manifest_unsigned = {
        "schema_version": 1,
        "kind": "MF17506_BLUE_HISTORY_16_RECIPE_OFFLINE_BUNDLE",
        "factory_profile_id": FACTORY_PROFILE_ID,
        "transport_codes": list(TRANSPORT_CODES),
        "recipe_count": 16,
        "batches": batch_records,
        "visible_action_count": 6,
        "normal_action_relay_cycles": 0,
        "live_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "relay_io_performed": False,
        "runtime_lut_used": False,
        "new_pigment_colour_claimed": False,
    }
    manifest = attach_integrity(manifest_unsigned)
    payload = canonical_json_bytes(manifest) + b"\n"
    (output / "BLUE-HISTORY-MANIFEST.json").write_bytes(payload)
    return {
        "output_dir": str(output.resolve()),
        "manifest_file": str((output / "BLUE-HISTORY-MANIFEST.json").resolve()),
        "manifest_file_sha256": hashlib.sha256(payload).hexdigest(),
        "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "recipe_count": 16,
        "visible_action_count": 6,
        "live_authorized": False,
        "device_io_performed": False,
    }
