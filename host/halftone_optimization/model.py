"""Overlap-aware display simulation for six-state colour halftones.

The model in this module is deliberately a simulation model.  It does not
claim that the bundled Gaussian point-spread function represents an MF-1750
panel.  A future camera/colourimeter workflow may fit the six kernels, but
that evidence boundary must be handled outside this package.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from host.color_pipeline.palette import Palette, reference_palette
from host.epd_frame import PHYSICAL_COLOR_CODES


LinearRGB = Tuple[float, float, float]
ALLOWED_CODES = tuple(sorted(PHYSICAL_COLOR_CODES))
UNCONSTRAINED_CODE = 0xFF


class HalftoneModelError(ValueError):
    """Raised when a simulated observation model violates its contract."""


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise HalftoneModelError(f"{label} must be a positive integer")
    return value


def validate_six_codes(codes: bytes | bytearray | memoryview, expected: int) -> bytes:
    """Return immutable codes after enforcing the physical six-code contract."""

    try:
        raw = bytes(memoryview(codes).cast("B"))
    except (TypeError, ValueError) as error:
        raise HalftoneModelError("codes must be contiguous byte data") from error
    if len(raw) != expected:
        raise HalftoneModelError(f"codes contain {len(raw)} pixels; expected {expected}")
    invalid = sorted(set(raw).difference(PHYSICAL_COLOR_CODES))
    if invalid:
        rendered = ", ".join(f"0x{value:X}" for value in invalid)
        raise HalftoneModelError(
            f"codes contain non-physical values: {rendered}; allowed={ALLOWED_CODES}"
        )
    return raw


def validate_code_constraints(
    constraints: bytes | bytearray | memoryview | None, expected: int
) -> bytes:
    """Return an immutable lock mask; ``0xff`` denotes no constraint."""

    if constraints is None:
        return bytes((UNCONSTRAINED_CODE,)) * expected
    try:
        raw = bytes(memoryview(constraints).cast("B"))
    except (TypeError, ValueError) as error:
        raise HalftoneModelError("code constraints must be contiguous byte data") from error
    if len(raw) != expected:
        raise HalftoneModelError(
            f"code constraints contain {len(raw)} pixels; expected {expected}"
        )
    invalid = sorted(set(raw).difference((*ALLOWED_CODES, UNCONSTRAINED_CODE)))
    if invalid:
        rendered = ", ".join(f"0x{value:X}" for value in invalid)
        raise HalftoneModelError(
            f"code constraints contain invalid values: {rendered}"
        )
    return raw


def _map_edge(coordinate: int, limit: int) -> int:
    """Clamp one coordinate to the image edge.

    Explicit edge replication avoids toroidal leakage from the left edge to
    the right edge while keeping every convolution normalized.
    """

    if coordinate < 0:
        return 0
    if coordinate >= limit:
        return limit - 1
    return coordinate


@dataclass(frozen=True)
class SpatialKernel:
    """Odd-sized, normalized, non-negative two-dimensional convolution kernel."""

    width: int
    height: int
    weights: Tuple[float, ...]

    def __post_init__(self) -> None:
        width = _positive_int(self.width, "kernel width")
        height = _positive_int(self.height, "kernel height")
        if width % 2 == 0 or height % 2 == 0:
            raise HalftoneModelError("kernel dimensions must be odd")
        if not isinstance(self.weights, (tuple, list)):
            raise HalftoneModelError("kernel weights must be a sequence")
        if len(self.weights) != width * height:
            raise HalftoneModelError(
                f"kernel has {len(self.weights)} weights; expected {width * height}"
            )
        normalized = []
        for value in self.weights:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HalftoneModelError("kernel weights must be numeric and not boolean")
            converted = float(value)
            if not math.isfinite(converted) or converted < 0.0:
                raise HalftoneModelError("kernel weights must be finite and non-negative")
            normalized.append(converted)
        total = math.fsum(normalized)
        if total <= 0.0:
            raise HalftoneModelError("kernel weight sum must be positive")
        object.__setattr__(self, "weights", tuple(value / total for value in normalized))

    @classmethod
    def from_rows(cls, rows: Sequence[Sequence[float]]) -> "SpatialKernel":
        if not isinstance(rows, (tuple, list)) or not rows:
            raise HalftoneModelError("kernel rows must be a non-empty sequence")
        if not all(isinstance(row, (tuple, list)) for row in rows):
            raise HalftoneModelError("each kernel row must be a sequence")
        width = len(rows[0])
        if width == 0 or any(len(row) != width for row in rows):
            raise HalftoneModelError("kernel rows must have equal non-zero width")
        return cls(width, len(rows), tuple(value for row in rows for value in row))

    @classmethod
    def gaussian(
        cls,
        size: int = 3,
        *,
        sigma_x: float = 0.8,
        sigma_y: float | None = None,
    ) -> "SpatialKernel":
        size = _positive_int(size, "Gaussian kernel size")
        if size % 2 == 0:
            raise HalftoneModelError("Gaussian kernel size must be odd")
        if isinstance(sigma_x, bool) or not isinstance(sigma_x, (int, float)):
            raise HalftoneModelError("sigma_x must be a positive finite number")
        sigma_x = float(sigma_x)
        sigma_y = sigma_x if sigma_y is None else sigma_y
        if isinstance(sigma_y, bool) or not isinstance(sigma_y, (int, float)):
            raise HalftoneModelError("sigma_y must be a positive finite number")
        sigma_y = float(sigma_y)
        if not math.isfinite(sigma_x) or sigma_x <= 0.0:
            raise HalftoneModelError("sigma_x must be a positive finite number")
        if not math.isfinite(sigma_y) or sigma_y <= 0.0:
            raise HalftoneModelError("sigma_y must be a positive finite number")
        radius = size // 2
        weights = []
        for y_value in range(-radius, radius + 1):
            for x_value in range(-radius, radius + 1):
                exponent = -0.5 * (
                    (x_value / sigma_x) ** 2 + (y_value / sigma_y) ** 2
                )
                weights.append(math.exp(exponent))
        return cls(size, size, tuple(weights))

    @property
    def radius_x(self) -> int:
        return self.width // 2

    @property
    def radius_y(self) -> int:
        return self.height // 2

    def taps(self) -> Iterable[Tuple[int, int, float]]:
        for row in range(self.height):
            for column in range(self.width):
                yield (
                    column - self.radius_x,
                    row - self.radius_y,
                    self.weights[row * self.width + column],
                )


@dataclass(frozen=True)
class OverlapObservationModel:
    """Six-mask convolution model with optional per-colour point-spread kernels."""

    model_id: str
    kernels: Tuple[Tuple[int, SpatialKernel], ...]
    boundary: str = "edge-replication"
    calibration_state: str = "simulation"
    hardware_qualified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise HalftoneModelError("model_id must be a non-empty string")
        if self.boundary != "edge-replication":
            raise HalftoneModelError("only edge-replication boundary handling is supported")
        if self.calibration_state != "simulation" or self.hardware_qualified is not False:
            raise HalftoneModelError(
                "S1 observation models are simulation-only and not hardware-qualified"
            )
        if not isinstance(self.kernels, (tuple, list)):
            raise HalftoneModelError("kernels must be code/kernel pairs")
        normalized: Dict[int, SpatialKernel] = {}
        for pair in self.kernels:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise HalftoneModelError("each kernel entry must be a code/kernel pair")
            code, kernel = pair
            if type(code) is not int or code not in PHYSICAL_COLOR_CODES:
                raise HalftoneModelError(f"invalid physical colour code in model: {code!r}")
            if not isinstance(kernel, SpatialKernel):
                raise HalftoneModelError("model kernels must be SpatialKernel instances")
            if code in normalized:
                raise HalftoneModelError(f"duplicate kernel for physical code {code}")
            normalized[code] = kernel
        if set(normalized) != set(PHYSICAL_COLOR_CODES):
            raise HalftoneModelError(f"model kernels must cover exactly {ALLOWED_CODES}")
        object.__setattr__(self, "model_id", self.model_id.strip())
        object.__setattr__(self, "kernels", tuple(sorted(normalized.items())))

    @classmethod
    def gaussian_simulation(
        cls,
        *,
        size: int = 3,
        sigma_x: float = 0.8,
        sigma_y: float | None = None,
    ) -> "OverlapObservationModel":
        kernel = SpatialKernel.gaussian(size, sigma_x=sigma_x, sigma_y=sigma_y)
        return cls(
            model_id=f"s1-gaussian-{size}x{size}-simulation-v1",
            kernels=tuple((code, kernel) for code in ALLOWED_CODES),
        )

    @property
    def by_code(self) -> Mapping[int, SpatialKernel]:
        return dict(self.kernels)

    def metadata(self) -> Dict[str, object]:
        return {
            "model_id": self.model_id,
            "boundary": self.boundary,
            "calibration_state": self.calibration_state,
            "hardware_qualified": False,
            "hardware_tested": False,
            "kernels": [
                {
                    "code": code,
                    "width": kernel.width,
                    "height": kernel.height,
                    "weights": list(kernel.weights),
                }
                for code, kernel in self.kernels
            ],
        }

    def source_response(
        self,
        code: int,
        source_x: int,
        source_y: int,
        width: int,
        height: int,
    ) -> Dict[int, float]:
        """Return exact affected output pixels for one source-mask impulse.

        At an image boundary several convolution taps can replicate the same
        source pixel.  Accumulating those taps here makes DBS local deltas
        exactly match a full rerender, including corner pixels.
        """

        width = _positive_int(width, "image width")
        height = _positive_int(height, "image height")
        if type(code) is not int or code not in PHYSICAL_COLOR_CODES:
            raise HalftoneModelError(f"invalid physical colour code: {code!r}")
        if not (0 <= source_x < width and 0 <= source_y < height):
            raise HalftoneModelError("source coordinate is outside the image")
        kernel = self.by_code[code]
        result: Dict[int, float] = {}
        min_x = max(0, source_x - kernel.radius_x)
        max_x = min(width - 1, source_x + kernel.radius_x)
        min_y = max(0, source_y - kernel.radius_y)
        max_y = min(height - 1, source_y + kernel.radius_y)
        taps = tuple(kernel.taps())
        for output_y in range(min_y, max_y + 1):
            for output_x in range(min_x, max_x + 1):
                contribution = 0.0
                for offset_x, offset_y, weight in taps:
                    sampled_x = _map_edge(output_x + offset_x, width)
                    sampled_y = _map_edge(output_y + offset_y, height)
                    if sampled_x == source_x and sampled_y == source_y:
                        contribution += weight
                if contribution:
                    result[output_y * width + output_x] = contribution
        return result

    def render_linear_rgb(
        self,
        codes: bytes | bytearray | memoryview,
        width: int,
        height: int,
        *,
        palette: Palette | None = None,
    ) -> array:
        """Convolve all six mutually-exclusive masks into linear RGB."""

        width = _positive_int(width, "image width")
        height = _positive_int(height, "image height")
        raw_codes = validate_six_codes(codes, width * height)
        selected_palette = reference_palette() if palette is None else palette
        if type(selected_palette) is not Palette:
            raise HalftoneModelError("palette must be a Palette instance or None")
        colours = {entry.code: entry.diffusion_rgb for entry in selected_palette.entries}
        kernels = self.by_code
        taps = {code: tuple(kernel.taps()) for code, kernel in kernels.items()}
        shared_kernel = all(kernel == kernels[ALLOWED_CODES[0]] for kernel in kernels.values())
        shared_taps = taps[ALLOWED_CODES[0]] if shared_kernel else ()
        output = array("f", [0.0]) * (width * height * 3)
        for output_y in range(height):
            row = output_y * width
            for output_x in range(width):
                red = green = blue = 0.0
                # K_code * M_code, followed by the per-code linear colour,
                # is equivalent to selecting the kernel from each sampled
                # source code and summing all six mask contributions.
                if shared_kernel:
                    for offset_x, offset_y, weight in shared_taps:
                        source_x = _map_edge(output_x + offset_x, width)
                        source_y = _map_edge(output_y + offset_y, height)
                        code = raw_codes[source_y * width + source_x]
                        colour = colours[code]
                        red += weight * colour[0]
                        green += weight * colour[1]
                        blue += weight * colour[2]
                else:
                    for code in ALLOWED_CODES:
                        for offset_x, offset_y, weight in taps[code]:
                            source_x = _map_edge(output_x + offset_x, width)
                            source_y = _map_edge(output_y + offset_y, height)
                            if raw_codes[source_y * width + source_x] != code:
                                continue
                            colour = colours[code]
                            red += weight * colour[0]
                            green += weight * colour[1]
                            blue += weight * colour[2]
                offset = (row + output_x) * 3
                output[offset] = red
                output[offset + 1] = green
                output[offset + 2] = blue
        return output


def box_blur_rgb(values: Sequence[float], width: int, height: int, size: int) -> array:
    """Apply a normalized odd square box blur using O(width*height) passes."""

    width = _positive_int(width, "image width")
    height = _positive_int(height, "image height")
    size = _positive_int(size, "box blur size")
    if size % 2 == 0:
        raise HalftoneModelError("box blur size must be odd")
    if len(values) != width * height * 3:
        raise HalftoneModelError(
            f"RGB field has {len(values)} components; expected {width * height * 3}"
        )
    if any(not math.isfinite(float(value)) for value in values):
        raise HalftoneModelError("RGB field must contain only finite values")
    radius = size // 2
    horizontal = array("f", [0.0]) * len(values)
    inverse = 1.0 / size
    for y_value in range(height):
        row = y_value * width
        for channel in range(3):
            running = (radius + 1) * float(values[(row * 3) + channel])
            for x_value in range(1, radius + 1):
                sampled_x = min(width - 1, x_value)
                running += float(values[((row + sampled_x) * 3) + channel])
            horizontal[(row * 3) + channel] = running * inverse
            for x_value in range(1, width):
                removed_x = _map_edge(x_value - radius - 1, width)
                added_x = _map_edge(x_value + radius, width)
                running += float(values[((row + added_x) * 3) + channel])
                running -= float(values[((row + removed_x) * 3) + channel])
                horizontal[((row + x_value) * 3) + channel] = running * inverse
    output = array("f", [0.0]) * len(values)
    for x_value in range(width):
        for channel in range(3):
            running = (radius + 1) * horizontal[(x_value * 3) + channel]
            for y_value in range(1, radius + 1):
                sampled_y = min(height - 1, y_value)
                running += horizontal[((sampled_y * width + x_value) * 3) + channel]
            output[(x_value * 3) + channel] = running * inverse
            for y_value in range(1, height):
                removed_y = _map_edge(y_value - radius - 1, height)
                added_y = _map_edge(y_value + radius, height)
                running += horizontal[((added_y * width + x_value) * 3) + channel]
                running -= horizontal[((removed_y * width + x_value) * 3) + channel]
                output[((y_value * width + x_value) * 3) + channel] = running * inverse
    return output


def box_source_response(
    source_x: int,
    source_y: int,
    width: int,
    height: int,
    size: int,
) -> Dict[int, float]:
    """Return exact box-filter output weights affected by one input sample."""

    width = _positive_int(width, "image width")
    height = _positive_int(height, "image height")
    size = _positive_int(size, "box blur size")
    if size % 2 == 0:
        raise HalftoneModelError("box blur size must be odd")
    if not (0 <= source_x < width and 0 <= source_y < height):
        raise HalftoneModelError("source coordinate is outside the image")
    radius = size // 2
    x_weights: Dict[int, int] = {}
    for output_x in range(max(0, source_x - radius), min(width - 1, source_x + radius) + 1):
        count = sum(
            1
            for offset in range(-radius, radius + 1)
            if _map_edge(output_x + offset, width) == source_x
        )
        if count:
            x_weights[output_x] = count
    y_weights: Dict[int, int] = {}
    for output_y in range(max(0, source_y - radius), min(height - 1, source_y + radius) + 1):
        count = sum(
            1
            for offset in range(-radius, radius + 1)
            if _map_edge(output_y + offset, height) == source_y
        )
        if count:
            y_weights[output_y] = count
    inverse_area = 1.0 / (size * size)
    return {
        output_y * width + output_x: x_count * y_count * inverse_area
        for output_y, y_count in y_weights.items()
        for output_x, x_count in x_weights.items()
    }
