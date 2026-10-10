#!/usr/bin/env python3
"""Build deterministic, offline-only low-grain face previews for Ariel 042.

This tool has no network or device surface.  It starts from the exact physical
Atkinson frame already exercised on the MF1750 panel and changes only fully
eligible 2x2 skin cells inside one fixed face ellipse.  Eyes, mouth, hair,
silhouette, and all pixels outside the eroded skin mask retain the Atkinson
codes byte-for-byte.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image, ImageFilter, __version__ as PILLOW_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_PNG = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_ARIEL042_ATKINSON_COVER_20260818_V1"
    / "source.png"
)
ATKINSON_FRAME = SOURCE_PNG.with_name("frame.bin")
MULTICOLOR_FRAME = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_ARIEL042_MULTICOLOR_DBS_262K_COVER_20260818_V1"
    / "frame.bin"
)

EXPECTED_SOURCE_PNG_SHA256 = (
    "3ef6d44fcecd4b58ecd94849e7013c838bf12cad9f276da6281070512894e295"
)
EXPECTED_SOURCE_PIXELS_SHA256 = (
    "7f3f10b1933aa7dacb2af6052af64eb43e015df64790edbc6897248634b66404"
)
EXPECTED_ATKINSON_FRAME_SHA256 = (
    "71cf149582cb089e0ebe5daac25f13906c902aa0b9db170c6946463359cb60ec"
)
EXPECTED_MULTICOLOR_FRAME_SHA256 = (
    "6bb6107b89824a4718645a0aed995cc077f4039d088c7ab673c9e30f0fa0e76b"
)

WIDTH = 1024
HEIGHT = 600
SCHEMA_VERSION = 1
KIND = "mf1750-ariel042-face-smooth-offline-preview"
VARIANT_A = "atlas-local-recipe-2x2"
VARIANT_B = "atlas-three-tone-2x2"
PHYSICAL_CODES = (0, 1, 2, 3, 5, 6)
SKIN_CODES = (0, 1, 2, 3)
PREVIEW_RGB = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 255, 0),
    3: (255, 0, 0),
    5: (0, 0, 255),
    6: (0, 255, 0),
}
FACE_ELLIPSE = {"center_x": 405.0, "center_y": 202.0, "radius_x": 112.0, "radius_y": 132.0}
FACE_CROP = {"x0": 275, "y0": 55, "x1": 540, "y1": 350}
BAYER_2X2_POSITIONS = ((0, 0), (1, 1), (0, 1), (1, 0))
REQUIRED_FILES = frozenset(
    {
        "manifest.json",
        "skin-mask.png",
        "variant-a-frame.bin",
        "variant-a-strict.png",
        "variant-a-model.png",
        "variant-a-face-strict.png",
        "variant-a-face-model.png",
        "variant-b-frame.bin",
        "variant-b-strict.png",
        "variant-b-model.png",
        "variant-b-face-strict.png",
        "variant-b-face-model.png",
    }
)


class FaceSmoothPreviewError(RuntimeError):
    """Raised when fixed preview inputs or generated evidence differ."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _read_exact(path: Path, expected_sha256: str, *, label: str) -> bytes:
    try:
        resolved = path.resolve(strict=True)
        before = resolved.stat()
        if not resolved.is_file() or resolved.is_symlink():
            raise FaceSmoothPreviewError(f"{label} is not a regular non-symlink file")
        payload = resolved.read_bytes()
        after = resolved.stat()
    except OSError as error:
        raise FaceSmoothPreviewError(f"cannot read {label}: {error}") from error
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != after.st_size:
        raise FaceSmoothPreviewError(f"{label} changed while read")
    actual = _sha256(payload)
    if actual != expected_sha256:
        raise FaceSmoothPreviewError(f"{label} SHA-256 differs: {actual}")
    return payload


def _decode_source(payload: bytes) -> np.ndarray:
    from io import BytesIO

    try:
        with Image.open(BytesIO(payload)) as opened:
            opened.load()
            image = opened.convert("RGB")
    except OSError as error:
        raise FaceSmoothPreviewError(f"source PNG decode failed: {error}") from error
    if image.size != (WIDTH, HEIGHT):
        raise FaceSmoothPreviewError("source PNG dimensions differ")
    source = np.asarray(image, dtype=np.uint8)
    if _sha256(source.tobytes()) != EXPECTED_SOURCE_PIXELS_SHA256:
        raise FaceSmoothPreviewError("decoded source pixels differ")
    return source


def _unpack_frame(payload: bytes) -> np.ndarray:
    from host.epd_frame import unpack_pixels, validate_frame

    validate_frame(payload, WIDTH, HEIGHT)
    return np.frombuffer(unpack_pixels(payload, WIDTH, HEIGHT), dtype=np.uint8).reshape(
        HEIGHT, WIDTH
    )


def _pack_codes(codes: np.ndarray) -> bytes:
    from host.epd_frame import pack_pixels, validate_frame

    if codes.shape != (HEIGHT, WIDTH) or codes.dtype != np.uint8:
        raise FaceSmoothPreviewError("candidate codes have the wrong shape or dtype")
    if not set(np.unique(codes).tolist()).issubset(PHYSICAL_CODES):
        raise FaceSmoothPreviewError("candidate codes escaped the physical six-code set")
    packed = pack_pixels(codes.reshape(-1).tolist(), WIDTH, HEIGHT)
    validate_frame(packed, WIDTH, HEIGHT)
    return packed


def _skin_mask(source: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    image = Image.fromarray(source, mode="RGB")
    ycbcr = np.asarray(image.convert("YCbCr"), dtype=np.uint8)
    smooth = np.asarray(image.filter(ImageFilter.GaussianBlur(radius=2.0)), dtype=np.uint8)
    smooth_y = np.asarray(
        Image.fromarray(smooth, mode="RGB").convert("YCbCr"), dtype=np.uint8
    )[..., 0]
    red = source[..., 0].astype(np.int16)
    green = source[..., 1].astype(np.int16)
    blue = source[..., 2].astype(np.int16)
    cb = ycbcr[..., 1]
    cr = ycbcr[..., 2]
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    ellipse = (
        ((xx - FACE_ELLIPSE["center_x"]) / FACE_ELLIPSE["radius_x"]) ** 2
        + ((yy - FACE_ELLIPSE["center_y"]) / FACE_ELLIPSE["radius_y"]) ** 2
        <= 1.0
    )
    raw = (
        ellipse
        & (cb >= 77)
        & (cb <= 135)
        & (cr >= 133)
        & (cr <= 180)
        & (red > green)
        & (green > blue)
        & (red > 85)
    )
    eroded = raw.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.zeros_like(raw)
            y0 = max(0, dy)
            y1 = HEIGHT + min(0, dy)
            x0 = max(0, dx)
            x1 = WIDTH + min(0, dx)
            shifted[y0:y1, x0:x1] = raw[y0 - dy : y1 - dy, x0 - dx : x1 - dx]
            eroded &= shifted
    return eroded, smooth, smooth_y


def _recipes() -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for counts in itertools.product(range(5), repeat=len(SKIN_CODES)):
        if sum(counts) != 4:
            continue
        rgb = np.zeros(3, dtype=np.float64)
        expanded: list[int] = []
        for code, count in zip(SKIN_CODES, counts, strict=True):
            rgb += np.asarray(PREVIEW_RGB[code], dtype=np.float64) * count / 4.0
            expanded.extend([code] * count)
        candidates.append(
            {
                "counts": tuple(int(value) for value in counts),
                "expanded": tuple(expanded),
                "rgb": rgb,
                "colour_count": sum(1 for value in counts if value),
            }
        )
    return tuple(candidates)


RECIPES = _recipes()


def _choose_recipe(target_rgb: np.ndarray) -> dict[str, Any]:
    def key(recipe: Mapping[str, Any]) -> tuple[float, int, tuple[int, ...]]:
        delta = np.asarray(recipe["rgb"]) - target_rgb.astype(np.float64)
        colour_penalty = 500.0 * max(0, int(recipe["colour_count"]) - 1)
        black_penalty = 40.0 * int(recipe["counts"][0])
        return (
            float(np.dot(delta, delta) + colour_penalty + black_penalty),
            int(recipe["colour_count"]),
            tuple(int(value) for value in recipe["counts"]),
        )

    return dict(min(RECIPES, key=key))


def _apply_recipe(codes: np.ndarray, y: int, x: int, recipe: Mapping[str, Any]) -> None:
    values = list(recipe["expanded"])
    if len(values) != 4:
        raise FaceSmoothPreviewError("2x2 recipe does not contain four pixels")
    # Codes are ordered by physical-code/luminance and placed through a fixed
    # Bayer rank.  Equal recipes therefore have exactly the same local phase.
    for value, (dy, dx) in zip(values, BAYER_2X2_POSITIONS, strict=True):
        codes[y + dy, x + dx] = int(value)


def _eligible_cells(mask: np.ndarray) -> tuple[tuple[int, int], ...]:
    cells: list[tuple[int, int]] = []
    for y in range(0, HEIGHT - 1, 2):
        for x in range(0, WIDTH - 1, 2):
            if bool(mask[y : y + 2, x : x + 2].all()):
                cells.append((y, x))
    return tuple(cells)


def _build_variants(
    source: np.ndarray, base: np.ndarray, mask: np.ndarray, smooth: np.ndarray, smooth_y: np.ndarray
) -> tuple[np.ndarray, np.ndarray, Mapping[str, Any]]:
    cells = _eligible_cells(mask)
    if len(cells) < 4_000:
        raise FaceSmoothPreviewError("fixed skin mask produced too few complete 2x2 cells")

    variant_a = base.copy()
    recipe_usage_a: dict[tuple[int, ...], int] = {}
    for y, x in cells:
        target = smooth[y : y + 2, x : x + 2].astype(np.float64).mean(axis=(0, 1))
        recipe = _choose_recipe(target)
        _apply_recipe(variant_a, y, x, recipe)
        key = tuple(int(value) for value in recipe["counts"])
        recipe_usage_a[key] = recipe_usage_a.get(key, 0) + 1

    cell_luminance = np.asarray(
        [float(smooth_y[y : y + 2, x : x + 2].mean()) for y, x in cells],
        dtype=np.float64,
    )
    threshold_low, threshold_high = np.quantile(cell_luminance, (0.35, 0.70)).tolist()
    class_targets: list[np.ndarray] = []
    class_recipes: list[dict[str, Any]] = []
    for low, high in ((-1.0, threshold_low), (threshold_low, threshold_high), (threshold_high, 256.0)):
        selected = [
            smooth[y : y + 2, x : x + 2].reshape(-1, 3)
            for (y, x), luminance in zip(cells, cell_luminance, strict=True)
            if low <= luminance < high
        ]
        if not selected:
            raise FaceSmoothPreviewError("three-tone skin class is empty")
        target = np.concatenate(selected, axis=0).astype(np.float64).mean(axis=0)
        class_targets.append(target)
        class_recipes.append(_choose_recipe(target))

    variant_b = base.copy()
    class_cell_counts = [0, 0, 0]
    for (y, x), luminance in zip(cells, cell_luminance, strict=True):
        class_index = 0 if luminance < threshold_low else 1 if luminance < threshold_high else 2
        _apply_recipe(variant_b, y, x, class_recipes[class_index])
        class_cell_counts[class_index] += 1

    metadata = {
        "raw_skin_pixels": int(mask.sum()),
        "eligible_full_2x2_cells": len(cells),
        "replaced_pixels_per_variant": len(cells) * 4,
        "variant_a_recipe_usage_cells": [
            {"counts_k_w_y_r": list(key), "cells": recipe_usage_a[key]}
            for key in sorted(recipe_usage_a)
        ],
        "variant_b": {
            "luminance_thresholds": [threshold_low, threshold_high],
            "class_cell_counts": class_cell_counts,
            "class_target_rgb": [target.tolist() for target in class_targets],
            "class_recipes_counts_k_w_y_r": [
                list(recipe["counts"]) for recipe in class_recipes
            ],
        },
    }
    return variant_a, variant_b, metadata


def _strict_rgb(codes: np.ndarray) -> bytes:
    lut = np.zeros((16, 3), dtype=np.uint8)
    for code, rgb in PREVIEW_RGB.items():
        lut[code] = rgb
    return lut[codes].tobytes()


def _model_rgb(codes: np.ndarray) -> bytes:
    from host.halftone_optimization.model import OverlapObservationModel
    from host.halftone_optimization.optimizer import _simulation_preview  # noqa: SLF001

    model = OverlapObservationModel.gaussian_simulation(size=3, sigma_x=0.8)
    observed = model.render_linear_rgb(codes.reshape(-1).tobytes(), WIDTH, HEIGHT)
    return _simulation_preview(observed)


def _crop_rgb(rgb: bytes) -> tuple[int, int, bytes]:
    x0, y0, x1, y1 = (FACE_CROP[key] for key in ("x0", "y0", "x1", "y1"))
    array = np.frombuffer(rgb, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
    cropped = array[y0:y1, x0:x1]
    return x1 - x0, y1 - y0, cropped.tobytes()


def _transition_metrics(codes: np.ndarray, mask: np.ndarray) -> Mapping[str, Any]:
    horizontal_mask = mask[:, 1:] & mask[:, :-1]
    vertical_mask = mask[1:, :] & mask[:-1, :]
    different = np.concatenate(
        [
            (codes[:, 1:] != codes[:, :-1])[horizontal_mask],
            (codes[1:, :] != codes[:-1, :])[vertical_mask],
        ]
    )
    rgb = np.frombuffer(_strict_rgb(codes), dtype=np.uint8).reshape(HEIGHT, WIDTH, 3).astype(
        np.float64
    )
    h_delta = np.sqrt(np.square(rgb[:, 1:] - rgb[:, :-1]).sum(axis=2))[horizontal_mask]
    v_delta = np.sqrt(np.square(rgb[1:, :] - rgb[:-1, :]).sum(axis=2))[vertical_mask]
    delta = np.concatenate([h_delta, v_delta])
    return {
        "eligible_neighbour_pairs": int(different.size),
        "different_code_ratio": float(different.mean()),
        "strict_neighbour_rgb_delta_mean": float(delta.mean()),
        "strict_neighbour_rgb_delta_p90": float(np.quantile(delta, 0.90)),
    }


def _file_reference(payload: bytes) -> Mapping[str, Any]:
    return {"bytes": len(payload), "sha256": _sha256(payload)}


def build() -> tuple[Mapping[str, Any], Mapping[str, bytes]]:
    from host.color_pipeline.preview import encode_rgb_png
    from host.epd_frame import fnv1a

    source_payload = _read_exact(
        SOURCE_PNG, EXPECTED_SOURCE_PNG_SHA256, label="normalized Ariel source PNG"
    )
    atkinson_payload = _read_exact(
        ATKINSON_FRAME, EXPECTED_ATKINSON_FRAME_SHA256, label="Atkinson frame"
    )
    multicolor_payload = _read_exact(
        MULTICOLOR_FRAME, EXPECTED_MULTICOLOR_FRAME_SHA256, label="multicolor frame"
    )
    source = _decode_source(source_payload)
    atkinson = _unpack_frame(atkinson_payload)
    multicolor = _unpack_frame(multicolor_payload)
    mask, smooth, smooth_y = _skin_mask(source)
    variant_a, variant_b, algorithm = _build_variants(source, atkinson, mask, smooth, smooth_y)

    mask_rgb = np.repeat((mask.astype(np.uint8) * 255)[..., None], 3, axis=2).tobytes()
    files: dict[str, bytes] = {
        "skin-mask.png": encode_rgb_png(WIDTH, HEIGHT, mask_rgb),
    }
    variant_records: dict[str, Any] = {}
    for prefix, name, codes in (
        ("variant-a", VARIANT_A, variant_a),
        ("variant-b", VARIANT_B, variant_b),
    ):
        frame = _pack_codes(codes)
        strict = _strict_rgb(codes)
        model = _model_rgb(codes)
        crop_width, crop_height, strict_crop = _crop_rgb(strict)
        _, _, model_crop = _crop_rgb(model)
        payloads = {
            f"{prefix}-frame.bin": frame,
            f"{prefix}-strict.png": encode_rgb_png(WIDTH, HEIGHT, strict),
            f"{prefix}-model.png": encode_rgb_png(WIDTH, HEIGHT, model),
            f"{prefix}-face-strict.png": encode_rgb_png(
                crop_width, crop_height, strict_crop
            ),
            f"{prefix}-face-model.png": encode_rgb_png(crop_width, crop_height, model_crop),
        }
        files.update(payloads)
        variant_records[name] = {
            "frame": {
                **_file_reference(frame),
                "fnv1a": f"0x{fnv1a(frame):08X}",
                "file": f"{prefix}-frame.bin",
            },
            "previews": {
                key.removeprefix(f"{prefix}-").removesuffix(".png"): {
                    **_file_reference(value),
                    "file": key,
                }
                for key, value in payloads.items()
                if key.endswith(".png")
            },
            "skin_transition_metrics": _transition_metrics(codes, mask),
        }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "mode": "offline-preview-only",
        "source": {
            "file": str(SOURCE_PNG.resolve()),
            "file_sha256": EXPECTED_SOURCE_PNG_SHA256,
            "decoded_pixels_sha256": EXPECTED_SOURCE_PIXELS_SHA256,
            "width": WIDTH,
            "height": HEIGHT,
            "pillow_version": PILLOW_VERSION,
        },
        "base_atkinson_frame": {
            "file": str(ATKINSON_FRAME.resolve()),
            "file_sha256": EXPECTED_ATKINSON_FRAME_SHA256,
            "skin_transition_metrics": _transition_metrics(atkinson, mask),
        },
        "rejected_multicolor_reference": {
            "file": str(MULTICOLOR_FRAME.resolve()),
            "file_sha256": EXPECTED_MULTICOLOR_FRAME_SHA256,
            "operator_observation": "face grain visibly worse than Atkinson",
            "skin_transition_metrics": _transition_metrics(multicolor, mask),
        },
        "face_mask": {
            "ellipse": deepcopy(FACE_ELLIPSE),
            "ycbcr_thresholds": {"cb": [77, 135], "cr": [133, 180]},
            "rgb_rules": ["R>G", "G>B", "R>85"],
            "erosion": "one 3x3 binary erosion",
            "replacement_gate": "all four pixels of a globally phased 2x2 cell eligible",
            "mask_file": {"file": "skin-mask.png", **_file_reference(files["skin-mask.png"])},
            "face_crop": deepcopy(FACE_CROP),
        },
        "algorithm": {
            **algorithm,
            "physical_codes_used_inside_skin": list(SKIN_CODES),
            "variant_a": "choose one K/W/Y/R four-pixel recipe per eligible 2x2 cell",
            "variant_b": "choose one fixed recipe for each of three smoothed-luminance bands",
            "outside_replacement_cells": "exact Atkinson physical codes",
            "optical_model": "uncalibrated 3x3 Gaussian sigma=0.8 simulation",
        },
        "variants": variant_records,
        "safety": {
            "device_io_performed": False,
            "network_io_performed": False,
            "refresh_authorized": False,
            "hardware_tested": False,
            "hardware_qualified": False,
            "generative_face_editing_used": False,
            "manual_preview_selection_required_before_any_live_packaging": True,
        },
    }
    manifest["integrity"] = {
        "canonical_sha256": _sha256(_canonical_json(manifest)),
        "scope": "entire manifest excluding integrity; canonical UTF-8 JSON",
    }
    files["manifest.json"] = _canonical_json(manifest)
    return manifest, files


def _safe_destination(path: Path, *, must_exist: bool) -> Path:
    if not isinstance(path, Path):
        raise FaceSmoothPreviewError("directory must be pathlib.Path")
    if path.is_absolute():
        resolved = path.resolve(strict=must_exist)
    else:
        resolved = (REPO_ROOT / path).resolve(strict=must_exist)
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise FaceSmoothPreviewError("directory escaped the workspace") from error
    return resolved


def write(output_dir: Path) -> Mapping[str, Any]:
    destination = _safe_destination(output_dir, must_exist=False)
    if os.path.lexists(destination):
        raise FaceSmoothPreviewError("output directory already exists")
    if not destination.parent.is_dir():
        raise FaceSmoothPreviewError("output parent does not exist")
    manifest, files = build()
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=str(destination.parent))
    )
    try:
        for name in sorted(files):
            (temporary / name).write_bytes(files[name])
        temporary.rename(destination)
    except BaseException:
        for candidate in temporary.glob("*"):
            candidate.unlink(missing_ok=True)
        temporary.rmdir()
        raise
    return validate(destination)


def validate(directory: Path) -> Mapping[str, Any]:
    resolved = _safe_destination(directory, must_exist=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise FaceSmoothPreviewError("preview directory is not a regular non-symlink directory")
    actual_names = frozenset(item.name for item in resolved.iterdir())
    if actual_names != REQUIRED_FILES:
        raise FaceSmoothPreviewError("preview directory file set differs")
    expected_manifest, expected_files = build()
    for name, expected in expected_files.items():
        path = resolved / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise FaceSmoothPreviewError(f"preview artifact differs: {name}")
    return expected_manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path)
    mode.add_argument("--validate-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = write(args.output_dir) if args.output_dir else validate(args.validate_dir)
    except FaceSmoothPreviewError as error:
        print(f"ERROR: {error}")
        return 2
    print(_canonical_json(manifest).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
