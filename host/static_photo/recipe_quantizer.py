"""Deterministic static-photo quantization to qualified history recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Any

import numpy as np

from host.color_pipeline import RasterImage

from .dual_frame import DualFrameResult, build_dual_frame
from .history_palette import HistoryPalette, HistoryRecipe


class RecipeQuantizationError(ValueError):
    """Raised when an image cannot be mapped to qualified history recipes."""


class RecipeRenderMode(str, Enum):
    NEAREST = "nearest-recipe"
    ORDERED_BAYER = "ordered-bayer-8x8"
    SMOOTH_CLUSTER = "smooth-cluster-4x4"
    EDGE_AWARE_DIFFUSION = "edge-aware-diffusion"


@dataclass(frozen=True)
class RecipeQuantizationResult:
    width: int
    height: int
    mode: RecipeRenderMode
    recipe_cell_px: int
    recipes: tuple[HistoryRecipe, ...]
    recipe_indices: bytes
    dual_frame: DualFrameResult
    report: dict[str, Any]

    def modeled_rgb(self) -> bytes:
        output = bytearray(self.width * self.height * 3)
        for pixel, recipe_index in enumerate(self.recipe_indices):
            start = pixel * 3
            output[start : start + 3] = bytes(self.recipes[recipe_index].preview_rgb)
        return bytes(output)


_BAYER_8X8 = np.asarray(
    (
        (0, 48, 12, 60, 3, 51, 15, 63),
        (32, 16, 44, 28, 35, 19, 47, 31),
        (8, 56, 4, 52, 11, 59, 7, 55),
        (40, 24, 36, 20, 43, 27, 39, 23),
        (2, 50, 14, 62, 1, 49, 13, 61),
        (34, 18, 46, 30, 33, 17, 45, 29),
        (10, 58, 6, 54, 9, 57, 5, 53),
        (42, 26, 38, 22, 41, 25, 37, 21),
    ),
    dtype=np.float64,
)
_CLUSTER_4X4 = np.asarray(
    ((12, 5, 6, 13), (4, 0, 1, 7), (11, 3, 2, 8), (15, 10, 9, 14)),
    dtype=np.float64,
)


def _raster_lab(image: RasterImage) -> np.ndarray:
    channels = image.channels
    raw = np.frombuffer(image.pixels, dtype=np.uint8).reshape(
        image.height, image.width, channels
    )
    rgb = raw[:, :, :3].astype(np.float64) / 255.0
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    if channels == 4:
        alpha = raw[:, :, 3:4].astype(np.float64) / 255.0
        linear = linear * alpha + (1.0 - alpha)
    xyz = np.empty_like(linear)
    xyz[:, :, 0] = (
        0.4124564 * linear[:, :, 0]
        + 0.3575761 * linear[:, :, 1]
        + 0.1804375 * linear[:, :, 2]
    )
    xyz[:, :, 1] = (
        0.2126729 * linear[:, :, 0]
        + 0.7151522 * linear[:, :, 1]
        + 0.0721750 * linear[:, :, 2]
    )
    xyz[:, :, 2] = (
        0.0193339 * linear[:, :, 0]
        + 0.1191920 * linear[:, :, 1]
        + 0.9503041 * linear[:, :, 2]
    )
    scaled = xyz / np.asarray((0.95047, 1.0, 1.08883))
    delta = 6.0 / 29.0
    converted = np.where(
        scaled > delta**3,
        np.cbrt(scaled),
        scaled / (3.0 * delta**2) + 4.0 / 29.0,
    )
    lab = np.empty_like(converted)
    lab[:, :, 0] = 116.0 * converted[:, :, 1] - 16.0
    lab[:, :, 1] = 500.0 * (converted[:, :, 0] - converted[:, :, 1])
    lab[:, :, 2] = 200.0 * (converted[:, :, 1] - converted[:, :, 2])
    return lab


def _delta_e00(values: np.ndarray, reference: np.ndarray) -> np.ndarray:
    l1, a1, b1 = values[:, 0], values[:, 1], values[:, 2]
    l2, a2, b2 = (float(item) for item in reference)
    c1 = np.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - np.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.hypot(a1p, b1)
    c2p = np.hypot(a2p, b2)
    h1p = np.mod(np.degrees(np.arctan2(b1, a1p)), 360.0)
    h2p = np.mod(np.degrees(np.arctan2(b2, a2p)), 360.0)
    dl = l2 - l1
    dc = c2p - c1p
    hue_difference = h2p - h1p
    hue_difference = np.where(
        hue_difference > 180.0, hue_difference - 360.0, hue_difference
    )
    hue_difference = np.where(
        hue_difference < -180.0, hue_difference + 360.0, hue_difference
    )
    hue_difference = np.where(c1p * c2p == 0.0, 0.0, hue_difference)
    dh = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(hue_difference / 2.0))
    lbar = (l1 + l2) / 2.0
    cbarp = (c1p + c2p) / 2.0
    hbar = (h1p + h2p) / 2.0
    hbar = np.where(
        (c1p * c2p != 0.0) & (np.abs(h1p - h2p) > 180.0) & (h1p + h2p < 360.0),
        (h1p + h2p + 360.0) / 2.0,
        hbar,
    )
    hbar = np.where(
        (c1p * c2p != 0.0) & (np.abs(h1p - h2p) > 180.0) & (h1p + h2p >= 360.0),
        (h1p + h2p - 360.0) / 2.0,
        hbar,
    )
    hbar = np.where(c1p * c2p == 0.0, h1p + h2p, hbar)
    t = (
        1.0
        - 0.17 * np.cos(np.radians(hbar - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * hbar))
        + 0.32 * np.cos(np.radians(3.0 * hbar + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * hbar - 63.0))
    )
    dtheta = 30.0 * np.exp(-(((hbar - 275.0) / 25.0) ** 2))
    rc = 2.0 * np.sqrt(cbarp**7 / (cbarp**7 + 25.0**7))
    lightness = lbar - 50.0
    sl = 1.0 + (0.015 * lightness**2) / np.sqrt(20.0 + lightness**2)
    sc = 1.0 + 0.045 * cbarp
    sh = 1.0 + 0.015 * cbarp * t
    rt = -np.sin(np.radians(2.0 * dtheta)) * rc
    lr, cr, hr = dl / sl, dc / sc, dh / sh
    return np.sqrt(np.maximum(0.0, lr**2 + cr**2 + hr**2 + rt * cr * hr))


def _cell_lab(image_lab: np.ndarray, cell: int) -> np.ndarray:
    height, width = image_lab.shape[:2]
    if width % cell or height % cell:
        raise RecipeQuantizationError(
            "image dimensions must be divisible by recipe_cell_px"
        )
    return image_lab.reshape(height // cell, cell, width // cell, cell, 3).mean(
        axis=(1, 3)
    )


def _distance_matrix(values: np.ndarray, palette_lab: np.ndarray) -> np.ndarray:
    flat = values.reshape(-1, 3)
    return np.column_stack([_delta_e00(flat, reference) for reference in palette_lab])


def _threshold_grid(height: int, width: int, matrix: np.ndarray) -> np.ndarray:
    rows = np.arange(height)[:, None] % matrix.shape[0]
    columns = np.arange(width)[None, :] % matrix.shape[1]
    return (matrix[rows, columns] + 0.5) / matrix.size


def _two_choice_assignments(
    values: np.ndarray, palette_lab: np.ndarray, threshold: np.ndarray
) -> np.ndarray:
    distances = _distance_matrix(values, palette_lab)
    if palette_lab.shape[0] == 1:
        return np.zeros(values.shape[:2], dtype=np.uint8)
    nearest_two = np.argpartition(distances, kth=1, axis=1)[:, :2]
    two_distances = np.take_along_axis(distances, nearest_two, axis=1)
    order = np.argsort(two_distances, axis=1, kind="stable")
    nearest_two = np.take_along_axis(nearest_two, order, axis=1)
    two_distances = np.take_along_axis(two_distances, order, axis=1)
    probability_second = np.divide(
        two_distances[:, 0],
        two_distances.sum(axis=1),
        out=np.zeros(two_distances.shape[0]),
        where=two_distances.sum(axis=1) > 1e-12,
    )
    selected = np.where(
        threshold.reshape(-1) < probability_second,
        nearest_two[:, 1],
        nearest_two[:, 0],
    )
    return selected.astype(np.uint8).reshape(values.shape[:2])


def _edge_aware_diffusion(values: np.ndarray, palette_lab: np.ndarray) -> np.ndarray:
    height, width = values.shape[:2]
    work = values.copy()
    assignments = np.zeros((height, width), dtype=np.uint8)
    horizontal = np.linalg.norm(np.diff(values, axis=1), axis=2)
    vertical = np.linalg.norm(np.diff(values, axis=0), axis=2)
    edges = np.zeros((height, width), dtype=bool)
    edges[:, 1:] |= horizontal >= 12.0
    edges[:, :-1] |= horizontal >= 12.0
    edges[1:, :] |= vertical >= 12.0
    edges[:-1, :] |= vertical >= 12.0
    for y in range(height):
        direction = -1 if y & 1 else 1
        x_values = range(width - 1, -1, -1) if direction < 0 else range(width)
        for x in x_values:
            distance = np.sum((palette_lab - work[y, x]) ** 2, axis=1)
            selected = int(np.argmin(distance))
            assignments[y, x] = selected
            if edges[y, x]:
                continue
            residual = work[y, x] - palette_lab[selected]
            for tx, ty, weight in (
                (x + direction, y, 7.0 / 16.0),
                (x - direction, y + 1, 3.0 / 16.0),
                (x, y + 1, 5.0 / 16.0),
                (x + direction, y + 1, 1.0 / 16.0),
            ):
                if 0 <= tx < width and 0 <= ty < height and not edges[ty, tx]:
                    work[ty, tx] += residual * weight
    return assignments


def quantize_to_history_recipes(
    image: RasterImage,
    palette: HistoryPalette,
    *,
    mode: RecipeRenderMode | str,
    recipe_cell_px: int = 1,
) -> RecipeQuantizationResult:
    if not isinstance(image, RasterImage):
        raise RecipeQuantizationError("image must be a RasterImage")
    if not isinstance(palette, HistoryPalette):
        raise RecipeQuantizationError("palette must be a HistoryPalette")
    try:
        selected_mode = (
            mode if isinstance(mode, RecipeRenderMode) else RecipeRenderMode(mode)
        )
    except ValueError as error:
        raise RecipeQuantizationError("unknown recipe render mode") from error
    if type(recipe_cell_px) is not int or recipe_cell_px not in (1, 2, 4, 8):
        raise RecipeQuantizationError("recipe_cell_px must be one of 1,2,4,8")
    recipes = palette.qualified_recipes
    if not recipes:
        raise RecipeQuantizationError("history palette has no qualified recipes")
    required_cell = max(recipe.minimum_recipe_cell_px for recipe in recipes)
    if recipe_cell_px < required_cell:
        raise RecipeQuantizationError(
            f"recipe_cell_px {recipe_cell_px} is below qualified minimum {required_cell}"
        )
    image_lab = _raster_lab(image)
    values = _cell_lab(image_lab, recipe_cell_px)
    palette_lab = np.asarray(
        [recipe.measured_lab for recipe in recipes], dtype=np.float64
    )
    if selected_mode is RecipeRenderMode.NEAREST:
        assignments = (
            np.argmin(_distance_matrix(values, palette_lab), axis=1)
            .astype(np.uint8)
            .reshape(values.shape[:2])
        )
        metric = "CIEDE2000"
    elif selected_mode is RecipeRenderMode.ORDERED_BAYER:
        assignments = _two_choice_assignments(
            values,
            palette_lab,
            _threshold_grid(values.shape[0], values.shape[1], _BAYER_8X8),
        )
        metric = "CIEDE2000-nearest-two"
    elif selected_mode is RecipeRenderMode.SMOOTH_CLUSTER:
        assignments = _two_choice_assignments(
            values,
            palette_lab,
            _threshold_grid(values.shape[0], values.shape[1], _CLUSTER_4X4),
        )
        metric = "CIEDE2000-nearest-two-clustered-threshold"
    else:
        assignments = _edge_aware_diffusion(values, palette_lab)
        metric = "Lab-Euclidean-error-diffusion-with-edge-lock"
    expanded = np.repeat(
        np.repeat(assignments, recipe_cell_px, axis=0), recipe_cell_px, axis=1
    )
    indices = expanded.astype(np.uint8).tobytes()
    dual = build_dual_frame(
        recipes,
        indices,
        width=image.width,
        height=image.height,
    )
    counts = np.bincount(expanded.reshape(-1), minlength=len(recipes))
    report = {
        "schema_version": 1,
        "kind": "MF17506_HISTORY_RECIPE_QUANTIZATION",
        "mode": selected_mode.value,
        "distance_metric": metric,
        "recipe_cell_px": recipe_cell_px,
        "width": image.width,
        "height": image.height,
        "input_raster_sha256": hashlib.sha256(image.pixels).hexdigest(),
        "history_palette_id": palette.palette_id,
        "history_palette_canonical_sha256": palette.mapping()["integrity"][
            "canonical_sha256"
        ],
        "recipes": [
            {
                "recipe_id": recipe.recipe_id,
                "count": int(counts[index]),
                "ratio": float(counts[index] / expanded.size),
                "primer_transport_code": recipe.primer_transport_code,
                "target_transport_code": recipe.target_transport_code,
            }
            for index, recipe in enumerate(recipes)
        ],
        "primer_frame_sha256": dual.primer_identity.sha256,
        "target_frame_sha256": dual.target_identity.sha256,
        "hardware_tested": False,
        "live_authorized": False,
    }
    return RecipeQuantizationResult(
        image.width,
        image.height,
        selected_mode,
        recipe_cell_px,
        recipes,
        indices,
        dual,
        report,
    )
