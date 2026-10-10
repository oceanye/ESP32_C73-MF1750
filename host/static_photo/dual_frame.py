"""Build validated Primer/Target frames from per-pixel history recipes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Sequence

from host.epd_frame import (
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    pack_pixels,
    validate_frame,
)

from .history_palette import HistoryRecipe, TRANSPORT_CODES


class DualFrameError(ValueError):
    """Raised when recipe assignments cannot form exact transport frames."""


@dataclass(frozen=True)
class PayloadIdentity:
    bytes: int
    sha256: str
    fnv1a: str


@dataclass(frozen=True)
class DualFrameResult:
    primer: bytes
    target: bytes
    primer_identity: PayloadIdentity
    target_identity: PayloadIdentity
    primer_cs1: PayloadIdentity
    primer_cs2: PayloadIdentity
    target_cs1: PayloadIdentity
    target_cs2: PayloadIdentity


def payload_identity(payload: bytes) -> PayloadIdentity:
    return PayloadIdentity(
        len(payload), hashlib.sha256(payload).hexdigest(), f"0x{fnv1a(payload):08X}"
    )


def build_dual_frame(
    recipes: Sequence[HistoryRecipe],
    recipe_indices: bytes | bytearray | memoryview | Sequence[int],
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> DualFrameResult:
    if (
        not isinstance(recipes, (tuple, list))
        or not recipes
        or not all(isinstance(recipe, HistoryRecipe) for recipe in recipes)
    ):
        raise DualFrameError("recipes must contain HistoryRecipe values")
    indices = bytes(recipe_indices)
    if len(indices) != width * height:
        raise DualFrameError(
            f"recipe assignment has {len(indices)} pixels; expected {width * height}"
        )
    if max(indices) >= len(recipes):
        raise DualFrameError("recipe assignment contains an out-of-range index")
    primer_codes = bytes(recipes[index].primer_transport_code for index in indices)
    target_codes = bytes(recipes[index].target_transport_code for index in indices)
    primer = pack_pixels(primer_codes, width, height, allowed_colors=TRANSPORT_CODES)
    target = pack_pixels(target_codes, width, height, allowed_colors=TRANSPORT_CODES)
    validate_frame(primer, width, height, allowed_colors=TRANSPORT_CODES)
    validate_frame(target, width, height, allowed_colors=TRANSPORT_CODES)
    if width != WIDTH or height != HEIGHT:
        empty = PayloadIdentity(
            0, hashlib.sha256(b"").hexdigest(), f"0x{fnv1a(b''):08X}"
        )
        return DualFrameResult(
            primer,
            target,
            payload_identity(primer),
            payload_identity(target),
            empty,
            empty,
            empty,
            empty,
        )
    primer_streams = tuple(
        controller_stream(
            primer,
            ControllerMapping(source_half=half),
            allowed_colors=TRANSPORT_CODES,
        )
        for half in (0, 1)
    )
    target_streams = tuple(
        controller_stream(
            target,
            ControllerMapping(source_half=half),
            allowed_colors=TRANSPORT_CODES,
        )
        for half in (0, 1)
    )
    if any(
        len(payload) != CONTROLLER_FRAME_BYTES
        for payload in (*primer_streams, *target_streams)
    ):
        raise AssertionError("controller stream length invariant failed")
    if len(primer) != FRAME_BYTES or len(target) != FRAME_BYTES:
        raise AssertionError("panel frame length invariant failed")
    return DualFrameResult(
        primer,
        target,
        payload_identity(primer),
        payload_identity(target),
        payload_identity(primer_streams[0]),
        payload_identity(primer_streams[1]),
        payload_identity(target_streams[0]),
        payload_identity(target_streams[1]),
    )
