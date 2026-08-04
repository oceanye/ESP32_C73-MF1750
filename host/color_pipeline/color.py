"""Dependency-free colour conversion and CIEDE2000 helpers.

The conversion path uses the IEC sRGB transfer curve, the sRGB/D65 matrix,
and CIE 1976 Lab with the D65 reference white.  Lab values are never presented
as measured panel values; calibration metadata belongs to :mod:`palette`.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple


Lab = Tuple[float, float, float]
LinearRGB = Tuple[float, float, float]

_D65 = (0.95047, 1.0, 1.08883)
_DELTA = 6.0 / 29.0


class ColorValueError(ValueError):
    """Raised when a colour value has an invalid shape or range."""


def _triple(values: Sequence[float], label: str) -> Tuple[float, float, float]:
    try:
        length = len(values)
    except TypeError as error:
        raise ColorValueError(f"{label} must contain exactly three components") from error
    if length != 3:
        raise ColorValueError(f"{label} must contain exactly three components")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise ColorValueError(f"{label} components must be numeric and not boolean")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise ColorValueError(f"{label} components must be finite")
    return result  # type: ignore[return-value]


def _finite_channel(channel: float, label: str) -> float:
    if isinstance(channel, bool) or not isinstance(channel, (int, float)):
        raise ColorValueError(f"{label} must be numeric and not boolean")
    result = float(channel)
    if not math.isfinite(result):
        raise ColorValueError(f"{label} must be finite")
    return result


def srgb_channel_to_linear(channel: float) -> float:
    """Convert one normalized sRGB channel to normalized linear light."""

    channel = _finite_channel(channel, "normalized sRGB channel")
    if not 0.0 <= channel <= 1.0:
        raise ColorValueError("normalized sRGB channel must be finite and in [0, 1]")
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def linear_channel_to_srgb(channel: float) -> float:
    """Convert one normalized linear-light channel to normalized sRGB."""

    channel = _finite_channel(channel, "linear-light channel")
    channel = min(1.0, max(0.0, channel))
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * (channel ** (1.0 / 2.4)) - 0.055


SRGB8_TO_LINEAR = tuple(srgb_channel_to_linear(value / 255.0) for value in range(256))


def srgb8_to_linear_rgb(rgb: Sequence[int]) -> LinearRGB:
    """Convert an 8-bit sRGB triple to normalized linear-light RGB."""

    try:
        length = len(rgb)
    except TypeError as error:
        raise ColorValueError("8-bit sRGB must contain exactly three components") from error
    if length != 3:
        raise ColorValueError("8-bit sRGB must contain exactly three components")
    converted = []
    for channel in rgb:
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 255:
            raise ColorValueError("8-bit sRGB components must be integers in [0, 255]")
        converted.append(SRGB8_TO_LINEAR[channel])
    return tuple(converted)  # type: ignore[return-value]


def linear_rgb_to_xyz(rgb: Sequence[float]) -> Tuple[float, float, float]:
    red, green, blue = _triple(rgb, "linear RGB")
    return (
        0.4124564 * red + 0.3575761 * green + 0.1804375 * blue,
        0.2126729 * red + 0.7151522 * green + 0.0721750 * blue,
        0.0193339 * red + 0.1191920 * green + 0.9503041 * blue,
    )


def xyz_to_linear_rgb(xyz: Sequence[float]) -> LinearRGB:
    x_value, y_value, z_value = _triple(xyz, "XYZ")
    return (
        3.2404542 * x_value - 1.5371385 * y_value - 0.4985314 * z_value,
        -0.9692660 * x_value + 1.8760108 * y_value + 0.0415560 * z_value,
        0.0556434 * x_value - 0.2040259 * y_value + 1.0572252 * z_value,
    )


def _lab_forward(value: float) -> float:
    if value > _DELTA**3:
        return value ** (1.0 / 3.0)
    return value / (3.0 * _DELTA**2) + 4.0 / 29.0


def _lab_inverse(value: float) -> float:
    if value > _DELTA:
        return value**3
    return 3.0 * _DELTA**2 * (value - 4.0 / 29.0)


def xyz_to_lab(xyz: Sequence[float]) -> Lab:
    x_value, y_value, z_value = _triple(xyz, "XYZ")
    x_scaled = _lab_forward(x_value / _D65[0])
    y_scaled = _lab_forward(y_value / _D65[1])
    z_scaled = _lab_forward(z_value / _D65[2])
    return (
        116.0 * y_scaled - 16.0,
        500.0 * (x_scaled - y_scaled),
        200.0 * (y_scaled - z_scaled),
    )


def lab_to_xyz(lab: Sequence[float]) -> Tuple[float, float, float]:
    lightness, a_value, b_value = _triple(lab, "Lab")
    y_scaled = (lightness + 16.0) / 116.0
    x_scaled = y_scaled + a_value / 500.0
    z_scaled = y_scaled - b_value / 200.0
    return (
        _D65[0] * _lab_inverse(x_scaled),
        _D65[1] * _lab_inverse(y_scaled),
        _D65[2] * _lab_inverse(z_scaled),
    )


def linear_rgb_to_lab(rgb: Sequence[float]) -> Lab:
    return xyz_to_lab(linear_rgb_to_xyz(rgb))


def lab_to_linear_rgb(lab: Sequence[float], *, clamp: bool = True) -> LinearRGB:
    if type(clamp) is not bool:
        raise ColorValueError("clamp must be boolean")
    result = xyz_to_linear_rgb(lab_to_xyz(lab))
    if clamp:
        return tuple(min(1.0, max(0.0, value)) for value in result)  # type: ignore[return-value]
    return result


def srgb8_to_lab(rgb: Sequence[int]) -> Lab:
    return linear_rgb_to_lab(srgb8_to_linear_rgb(rgb))


def lab_to_srgb8(lab: Sequence[float]) -> Tuple[int, int, int]:
    linear = lab_to_linear_rgb(lab, clamp=True)
    return tuple(
        min(255, max(0, int(round(linear_channel_to_srgb(channel) * 255.0))))
        for channel in linear
    )  # type: ignore[return-value]


def delta_e_ciede2000(lab1: Sequence[float], lab2: Sequence[float]) -> float:
    """Return the CIEDE2000 colour difference using unit weighting factors."""

    l1, a1, b1 = _triple(lab1, "Lab 1")
    l2, a2, b2 = _triple(lab2, "Lab 2")
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    c_bar_7 = c_bar**7
    g_value = 0.5 * (1.0 - math.sqrt(c_bar_7 / (c_bar_7 + 25.0**7)))
    a1_prime = (1.0 + g_value) * a1
    a2_prime = (1.0 + g_value) * a2
    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)

    h1_prime = math.degrees(math.atan2(b1, a1_prime)) % 360.0
    h2_prime = math.degrees(math.atan2(b2, a2_prime)) % 360.0
    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime
    if c1_prime * c2_prime == 0.0:
        delta_h_prime_degrees = 0.0
    else:
        hue_difference = h2_prime - h1_prime
        if hue_difference > 180.0:
            hue_difference -= 360.0
        elif hue_difference < -180.0:
            hue_difference += 360.0
        delta_h_prime_degrees = hue_difference
    delta_h_prime = 2.0 * math.sqrt(c1_prime * c2_prime) * math.sin(
        math.radians(delta_h_prime_degrees / 2.0)
    )

    l_bar_prime = (l1 + l2) / 2.0
    c_bar_prime = (c1_prime + c2_prime) / 2.0
    if c1_prime * c2_prime == 0.0:
        h_bar_prime = h1_prime + h2_prime
    else:
        hue_distance = abs(h1_prime - h2_prime)
        if hue_distance <= 180.0:
            h_bar_prime = (h1_prime + h2_prime) / 2.0
        elif h1_prime + h2_prime < 360.0:
            h_bar_prime = (h1_prime + h2_prime + 360.0) / 2.0
        else:
            h_bar_prime = (h1_prime + h2_prime - 360.0) / 2.0

    t_value = (
        1.0
        - 0.17 * math.cos(math.radians(h_bar_prime - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * h_bar_prime))
        + 0.32 * math.cos(math.radians(3.0 * h_bar_prime + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * h_bar_prime - 63.0))
    )
    delta_theta = 30.0 * math.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    c_bar_prime_7 = c_bar_prime**7
    r_c = 2.0 * math.sqrt(c_bar_prime_7 / (c_bar_prime_7 + 25.0**7))
    lightness_term = l_bar_prime - 50.0
    s_l = 1.0 + (0.015 * lightness_term**2) / math.sqrt(20.0 + lightness_term**2)
    s_c = 1.0 + 0.045 * c_bar_prime
    s_h = 1.0 + 0.015 * c_bar_prime * t_value
    r_t = -math.sin(math.radians(2.0 * delta_theta)) * r_c

    l_ratio = delta_l_prime / s_l
    c_ratio = delta_c_prime / s_c
    h_ratio = delta_h_prime / s_h
    return math.sqrt(
        l_ratio**2 + c_ratio**2 + h_ratio**2 + r_t * c_ratio * h_ratio
    )
