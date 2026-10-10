"""Build immutable, offline-only four-mode static-photo candidate bundles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from host.application.images import FitPolicy, decode_normalized_source
from host.epd_frame import HEIGHT, WIDTH

from .blue_history import PREVIEW_RGB
from .common import attach_integrity, canonical_json_bytes, prepare_empty_output_dir
from .history_palette import HistoryPalette, load_history_palette
from .recipe_quantizer import (
    RecipeQuantizationError,
    RecipeRenderMode,
    quantize_to_history_recipes,
)


class PhotoRenderError(ValueError):
    """Raised when a static-photo candidate bundle cannot be built."""


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    raise PhotoRenderError("source must be JPEG or PNG")


def _png(rgb: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", rgb[:, :, ::-1])
    if not ok:
        raise PhotoRenderError("cannot encode PNG")
    return encoded.tobytes()


def _transport_preview(frame: bytes) -> np.ndarray:
    packed = np.frombuffer(frame, dtype=np.uint8).reshape(HEIGHT, WIDTH // 2)
    codes = np.empty((HEIGHT, WIDTH), dtype=np.uint8)
    codes[:, 0::2] = packed >> 4
    codes[:, 1::2] = packed & 0x0F
    rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for code, colour in PREVIEW_RGB.items():
        rgb[codes == code] = colour
    return rgb


def build_photo_bundle(
    source_file: str | Path,
    palette: HistoryPalette | str | Path,
    *,
    output_dir: str | Path,
    fit: FitPolicy | str = FitPolicy.COVER,
    recipe_cell_px: int = 1,
) -> dict[str, Any]:
    source_path = Path(source_file)
    try:
        source_payload = source_path.read_bytes()
    except OSError as error:
        raise PhotoRenderError(f"cannot read source photo: {error}") from error
    selected_palette = (
        load_history_palette(palette) if isinstance(palette, (str, Path)) else palette
    )
    if not isinstance(selected_palette, HistoryPalette):
        raise PhotoRenderError("palette must be a HistoryPalette or JSON path")
    if not selected_palette.qualified_recipes:
        raise PhotoRenderError("history palette contains no qualified recipes")
    try:
        decoded = decode_normalized_source(
            source_payload,
            _media_type(source_path),
            fit,
            target_width=WIDTH,
            target_height=HEIGHT,
        )
    except Exception as error:
        raise PhotoRenderError(f"source normalization failed: {error}") from error
    output = prepare_empty_output_dir(output_dir)
    original_name = f"source-original{source_path.suffix.lower()}"
    (output / original_name).write_bytes(source_payload)
    raster = decoded.raster
    normalized = np.frombuffer(raster.pixels, dtype=np.uint8).reshape(
        HEIGHT, WIDTH, raster.channels
    )[:, :, :3]
    normalized_payload = _png(normalized)
    (output / "source-normalized.png").write_bytes(normalized_payload)
    candidate_records: list[dict[str, Any]] = []
    modeled_images: list[tuple[str, np.ndarray]] = []
    for mode in RecipeRenderMode:
        try:
            result = quantize_to_history_recipes(
                raster,
                selected_palette,
                mode=mode,
                recipe_cell_px=recipe_cell_px,
            )
        except RecipeQuantizationError as error:
            raise PhotoRenderError(str(error)) from error
        candidate_dir = output / mode.value
        candidate_dir.mkdir()
        modeled = np.frombuffer(result.modeled_rgb(), dtype=np.uint8).reshape(
            HEIGHT, WIDTH, 3
        )
        modeled_payload = _png(modeled)
        primer_preview_payload = _png(_transport_preview(result.dual_frame.primer))
        target_preview_payload = _png(_transport_preview(result.dual_frame.target))
        files = {
            "modeled-final.png": modeled_payload,
            "primer-preview.png": primer_preview_payload,
            "target-code-preview.png": target_preview_payload,
            "primer.bin": result.dual_frame.primer,
            "target.bin": result.dual_frame.target,
        }
        for filename, payload in files.items():
            (candidate_dir / filename).write_bytes(payload)
        candidate_report = dict(result.report)
        candidate_report["files"] = {
            filename: {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for filename, payload in files.items()
        }
        candidate_report = attach_integrity(candidate_report)
        report_payload = canonical_json_bytes(candidate_report) + b"\n"
        (candidate_dir / "RENDER-MANIFEST.json").write_bytes(report_payload)
        candidate_records.append(
            {
                "mode": mode.value,
                "directory": mode.value,
                "manifest_sha256": hashlib.sha256(report_payload).hexdigest(),
                "manifest_canonical_sha256": candidate_report["integrity"][
                    "canonical_sha256"
                ],
                "primer_frame_sha256": result.dual_frame.primer_identity.sha256,
                "target_frame_sha256": result.dual_frame.target_identity.sha256,
            }
        )
        modeled_images.append((mode.value, modeled))
    canvas = np.full((HEIGHT * 2, WIDTH * 3, 3), 245, dtype=np.uint8)
    panels = [("source-normalized", normalized), *modeled_images]
    for index, (label, image) in enumerate(panels):
        row, column = divmod(index, 3)
        canvas[
            row * HEIGHT : (row + 1) * HEIGHT, column * WIDTH : (column + 1) * WIDTH
        ] = image
        cv2.putText(
            canvas,
            label,
            (column * WIDTH + 12, row * HEIGHT + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    contact_payload = _png(canvas)
    (output / "comparison-contact-sheet.png").write_bytes(contact_payload)
    manifest_unsigned = {
        "schema_version": 1,
        "kind": "MF17506_STATIC_PHOTO_FOUR_MODE_OFFLINE_BUNDLE",
        "source": {
            "file": str(source_path.resolve()),
            "bytes": len(source_payload),
            "sha256": hashlib.sha256(source_payload).hexdigest(),
            "copied_as": original_name,
            "normalization": decoded.provenance,
        },
        "history_palette": {
            "palette_id": selected_palette.palette_id,
            "canonical_sha256": selected_palette.mapping()["integrity"][
                "canonical_sha256"
            ],
            "qualified_recipe_count": len(selected_palette.qualified_recipes),
        },
        "recipe_cell_px": recipe_cell_px,
        "candidates": candidate_records,
        "contact_sheet": {
            "file": "comparison-contact-sheet.png",
            "bytes": len(contact_payload),
            "sha256": hashlib.sha256(contact_payload).hexdigest(),
        },
        "selected_candidate": None,
        "hardware_tested": False,
        "live_authorized": False,
        "device_io_performed": False,
        "network_io_performed": False,
        "relay_io_performed": False,
    }
    manifest = attach_integrity(manifest_unsigned)
    payload = canonical_json_bytes(manifest) + b"\n"
    (output / "PHOTO-BUNDLE-MANIFEST.json").write_bytes(payload)
    return {
        "output_dir": str(output.resolve()),
        "candidate_count": 4,
        "history_palette_id": selected_palette.palette_id,
        "manifest_canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "live_authorized": False,
        "device_io_performed": False,
    }
