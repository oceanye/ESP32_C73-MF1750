#!/usr/bin/env python3
"""Generate the MF1750 partial-block first-batch offline sources.

Implements docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md "首批离线实现":

Route A (P0): env esp32-s3-devkitc-1-partial-atlas-1e drives one compiled
white-background 1024x600 frame with seven fixed 192x160 ROIs (one per
transport code 0..6) through the sealed wf_wmask_1E full-frame path.

Route B (P1-P3): env esp32-s3-devkitc-1-partial-block-ptlw runs the sealed
clean-PTLW partial transport (0x83, 9-byte inclusive window, 160x120 window,
full code-7 preload then cropped DTM, PON/DRF/POF with no PTLW repeat after
PON) at the frozen 1 MHz SPI.  Runtime actions A/B/C bind the wf_wmask_1E /
wf_wmask_0E / wf_wmask_1C complete R20 tuples byte-identically; factory-OTP
white anchors and closes the sequence.

V2 (handoff amendment 2, after the P0 anomaly analysis): the route A layout
keeps the eight slot coordinates but swaps (544,384) to the code7 probe and
(792,384) to code6; route B's cropped patch code is 4 instead of 0; both
variants get dedicated *_V2 tags, envs, and generated TUs.  V1 outputs stay
byte-identical.

No hardware, serial, relay, network, camera, or flashing access is performed.
Generated files are never overwritten with different content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_wf_wmask_build as wmask  # noqa: E402

DATE = "20261020"
HANDOFF_DOC = "docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md"

WIDTH = 1024
HEIGHT = 600
CONTROLLER_WIDTH = 512
FRAME_BYTES = WIDTH * HEIGHT // 2
CONTROLLER_DTM_BYTES = CONTROLLER_WIDTH * HEIGHT // 2
ROW_BYTES = WIDTH // 2
CONTROLLER_ROW_BYTES = CONTROLLER_WIDTH // 2

R2G_DRIVER_PATH = ROOT / "src/wf_bisect_r2g_epd_driver.cpp"
R2G_MAIN_PATH = ROOT / "src/wf_bisect_r2g_main.cpp"
R2G_TAG = "MF1750_WF_BISECT_R2G_20261018"
R2G_BOOT = "WF bisection R2G: commented White records 4+5"

ATLAS_ENV = "esp32-s3-devkitc-1-partial-atlas-1e"
ATLAS_TAG = f"MF1750_PARTIAL_BLOCK_ATLAS_1E_{DATE}"
PTLW_ENV = "esp32-s3-devkitc-1-partial-block-ptlw"
PTLW_TAG = f"MF1750_PARTIAL_BLOCK_PTLW_{DATE}"
ATLAS_ENV_V2 = "esp32-s3-devkitc-1-partial-atlas-1e-v2"
ATLAS_TAG_V2 = f"MF1750_PARTIAL_BLOCK_ATLAS_1E_{DATE}_V2"
PTLW_ENV_V2 = "esp32-s3-devkitc-1-partial-block-ptlw-v2"
PTLW_TAG_V2 = f"MF1750_PARTIAL_BLOCK_PTLW_{DATE}_V2"

ATLAS_PATHS = {
    "layout_inc": ROOT / "src/generated/partial_atlas_1e_layout.inc",
    "api_header": ROOT / "src/partial_atlas_1e_api.h",
    "driver": ROOT / "src/partial_atlas_1e_epd_driver.cpp",
    "main": ROOT / "src/partial_atlas_1e_main.cpp",
}
PTLW_PATHS = {
    "contract_inc": ROOT / "src/generated/partial_block_ptlw_contract.inc",
    "api_header": ROOT / "src/partial_block_ptlw_api.h",
    "driver": ROOT / "src/partial_block_ptlw_epd_driver.cpp",
    "main": ROOT / "src/partial_block_ptlw_main.cpp",
}


def _version_names(version: str) -> dict[str, str]:
    if version == "V1":
        return {
            "atlas_env": ATLAS_ENV,
            "atlas_tag": ATLAS_TAG,
            "ptlw_env": PTLW_ENV,
            "ptlw_tag": PTLW_TAG,
            "atlas_layout_inc": "src/generated/partial_atlas_1e_layout.inc",
            "ptlw_contract_inc": "src/generated/partial_block_ptlw_contract.inc",
            "atlas_driver": "src/partial_atlas_1e_epd_driver.cpp",
            "atlas_main": "src/partial_atlas_1e_main.cpp",
            "ptlw_driver": "src/partial_block_ptlw_epd_driver.cpp",
            "ptlw_main": "src/partial_block_ptlw_main.cpp",
            "atlas_boot":
                "partial block route A: compiled 1E seven-code atlas on white",
            "ptlw_boot":
                "partial block route B: clean PTLW windows A=1E B=0E C=1C + factory white",
        }
    if version == "V2":
        return {
            "atlas_env": ATLAS_ENV_V2,
            "atlas_tag": ATLAS_TAG_V2,
            "ptlw_env": PTLW_ENV_V2,
            "ptlw_tag": PTLW_TAG_V2,
            "atlas_layout_inc": "src/generated/partial_atlas_1e_v2_layout.inc",
            "ptlw_contract_inc": "src/generated/partial_block_ptlw_v2_contract.inc",
            "atlas_driver": "src/partial_atlas_1e_v2_epd_driver.cpp",
            "atlas_main": "src/partial_atlas_1e_v2_main.cpp",
            "ptlw_driver": "src/partial_block_ptlw_v2_epd_driver.cpp",
            "ptlw_main": "src/partial_block_ptlw_v2_main.cpp",
            "atlas_boot":
                "partial block route A V2: code7 probe at (544,384), code6 at (792,384)",
            "ptlw_boot":
                "partial block route B V2: patch code4 clean PTLW windows A=1E B=0E C=1C + factory white",
        }
    raise ValueError(f"unknown partial-block version {version!r}")


# ---------------------------------------------------------------------------
# Route A V3 (handoff amendment 2 + anomaly-2 protocols 1+2): one screening
# session env that first normalizes panel residual history, then measures.
# All frames and the step sequence are compile-time pinned; no runtime frame,
# coordinate, or LUT input exists.
# ---------------------------------------------------------------------------

ATLAS_ENV_V3 = "esp32-s3-devkitc-1-partial-atlas-1e-v3"
ATLAS_TAG_V3 = f"MF1750_PARTIAL_BLOCK_ATLAS_1E_{DATE}_V3"
V3_PATHS = {
    "contract_inc": "src/generated/partial_atlas_1e_v3_contract.inc",
    "api_header": "src/partial_atlas_1e_v3_api.h",
    "driver": "src/partial_atlas_1e_v3_epd_driver.cpp",
    "main": "src/partial_atlas_1e_v3_main.cpp",
}
V3_NORMALIZE_SEQUENCE = (
    {"kind": "factory_otp_white", "code": 1},
    {"kind": "factory_otp_white", "code": 1},
    {"kind": "active_uniform", "code": 0},
    {"kind": "active_uniform", "code": 1},
    {"kind": "active_uniform", "code": 0},
    {"kind": "active_uniform", "code": 1},
    {"kind": "active_uniform", "code": 0},
    {"kind": "active_uniform", "code": 1},
)
# Sealed legacy-active 535-byte R20 prefix identity (see
# src/ec5_runtime_lut_true_r20_partial_hold_v1_identity.inc kActiveR20PrefixSha256).
V3_ACTIVE_R20_SHA256 = "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"


def _uniform_frame(code: int) -> bytes:
    return _uniform(FRAME_BYTES, code)


def v3_identities() -> dict[str, Any]:
    frame_v2 = build_atlas_frame("V2")
    black = _uniform_frame(0)
    white = _uniform_frame(1)
    probe7 = _uniform_frame(7)
    frames = {
        "black": black, "white": white, "probe7": probe7, "atlas_v2": frame_v2,
    }
    return {
        "frames": {
            name: {
                "bytes": len(payload),
                "fnv1a": _fnv1a(payload),
                "sha256": _sha256(payload),
            }
            for name, payload in frames.items()
        },
        "streams": {
            "black": _fnv1a(_uniform(CONTROLLER_DTM_BYTES, 0)),
            "white": _fnv1a(_uniform(CONTROLLER_DTM_BYTES, 1)),
            "probe7": _fnv1a(_uniform(CONTROLLER_DTM_BYTES, 7)),
            "atlas_v2_cs1": _fnv1a(controller_stream(frame_v2, False)),
            "atlas_v2_cs2": _fnv1a(controller_stream(frame_v2, True)),
        },
    }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fnv1a(payload: bytes) -> int:
    value = 2166136261
    for byte in payload:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


# ---------------------------------------------------------------------------
# Route A layouts.  V1: white (code 7) background, seven 192x160 ROIs for codes
# 0-6 plus the code-7 background reference slot at (792,384).  V2 (handoff
# amendment 2): same eight slot coordinates, codes 0-5 unchanged, (544,384)
# becomes the code7 probe and (792,384) becomes code6 — discriminating whether
# the P0 olive block follows code7 or the (792,384) position.  Columns/rows
# keep every ROI fully inside one 512-pixel controller half on even byte
# boundaries, clear of the x=512 cascade seam.
# ---------------------------------------------------------------------------

ATLAS_BACKGROUND_CODE = 7
ATLAS_ROI_WIDTH = 192
ATLAS_ROI_HEIGHT = 160
ATLAS_SLOTS: tuple[tuple[int, int], ...] = (
    (48, 64), (288, 64), (544, 64), (792, 64),
    (48, 384), (288, 384), (544, 384), (792, 384),
)
ATLAS_CODES_V1: tuple[int | None, ...] = (0, 1, 2, 3, 4, 5, 6, None)
ATLAS_CODES_V2: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 7, 6)
ATLAS_V2_PROBE_NAME = "code7_probe"
ATLAS_V1_BG_REF_NAME = "bg_ref"
ATLAS_VERSIONS = ("V1", "V2")
PTLW_PATCH_CODES = {"V1": 0, "V2": 4}


def atlas_regions(version: str = "V1") -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return (code regions, optional background-reference region)."""

    codes = ATLAS_CODES_V1 if version == "V1" else ATLAS_CODES_V2
    regions: list[dict[str, Any]] = []
    background_reference: dict[str, Any] | None = None
    for (x, y), code in zip(ATLAS_SLOTS, codes):
        if code is None:
            background_reference = {
                "name": ATLAS_V1_BG_REF_NAME, "code": ATLAS_BACKGROUND_CODE,
                "x": x, "y": y, "w": ATLAS_ROI_WIDTH, "h": ATLAS_ROI_HEIGHT,
            }
            continue
        name = (ATLAS_V2_PROBE_NAME if version == "V2" and (x, y) == (544, 384)
                else f"code{code}")
        regions.append({"name": name, "code": code, "x": x, "y": y,
                        "w": ATLAS_ROI_WIDTH, "h": ATLAS_ROI_HEIGHT})
    return regions, background_reference


ATLAS_ROIS: tuple[dict[str, Any], ...] = tuple(atlas_regions("V1")[0])
ATLAS_BACKGROUND_REFERENCE = atlas_regions("V1")[1]


def _validate_atlas_layout(version: str = "V1") -> None:
    regions, background_reference = atlas_regions(version)
    slots = list(regions) + ([background_reference] if background_reference else [])
    codes = [roi["code"] for roi in regions]
    if len(set(codes)) != len(codes):
        raise RuntimeError("route A ROI codes are not unique")
    if version == "V1" and codes != [0, 1, 2, 3, 4, 5, 6]:
        raise RuntimeError("route A V1 ROI code order drifted")
    if version == "V2" and sorted(codes) != [0, 1, 2, 3, 4, 5, 6, 7]:
        raise RuntimeError("route A V2 ROI code set drifted")
    for roi in slots:
        if roi["x"] % 2 or roi["w"] % 2:
            raise RuntimeError(f"route A ROI {roi['name']} is not byte aligned")
        if roi["x"] + roi["w"] > WIDTH or roi["y"] + roi["h"] > HEIGHT:
            raise RuntimeError(f"route A ROI {roi['name']} escapes the panel")
        left, right = roi["x"], roi["x"] + roi["w"]
        if not (right <= CONTROLLER_WIDTH or left >= CONTROLLER_WIDTH):
            raise RuntimeError(f"route A ROI {roi['name']} crosses the x=512 seam")
    for index, left in enumerate(slots):
        for right in slots[index + 1:]:
            overlap = not (
                left["x"] + left["w"] <= right["x"]
                or right["x"] + right["w"] <= left["x"]
                or left["y"] + left["h"] <= right["y"]
                or right["y"] + right["h"] <= left["y"]
            )
            if overlap:
                raise RuntimeError("route A ROIs overlap")


def build_atlas_frame(version: str = "V1") -> bytes:
    """Return the fixed packed-4bpp route A frame (even x in the high nibble)."""

    _validate_atlas_layout(version)
    regions, _background_reference = atlas_regions(version)
    frame = bytearray(
        [(ATLAS_BACKGROUND_CODE << 4) | ATLAS_BACKGROUND_CODE] * FRAME_BYTES
    )
    for roi in regions:
        pair = (roi["code"] << 4) | roi["code"]
        for y in range(roi["y"], roi["y"] + roi["h"]):
            start = y * ROW_BYTES + roi["x"] // 2
            frame[start:start + roi["w"] // 2] = bytes([pair]) * (roi["w"] // 2)
    return bytes(frame)


def controller_stream(frame: bytes, second_controller: bool) -> bytes:
    """MAP_ORIENT_V1 identity mapping: each controller takes its half rows."""

    if len(frame) != FRAME_BYTES:
        raise RuntimeError("route A frame length drifted")
    half = 1 if second_controller else 0
    stream = bytearray()
    for y in range(HEIGHT):
        row = frame[y * ROW_BYTES:(y + 1) * ROW_BYTES]
        stream += row[half * CONTROLLER_ROW_BYTES:(half + 1) * CONTROLLER_ROW_BYTES]
    return bytes(stream)


def atlas_layout_doc(version: str = "V1") -> dict[str, Any]:
    regions, background_reference = atlas_regions(version)
    doc: dict[str, Any] = {
        "schema": "mf1750-partial-block-atlas-layout-v1",
        "panel": {"width": WIDTH, "height": HEIGHT,
                  "controller_width": CONTROLLER_WIDTH},
        "background_code": ATLAS_BACKGROUND_CODE,
        "background_is_l535_white_code7": True,
        "rois": [dict(roi) for roi in regions],
        "background_reference": (
            dict(background_reference) if background_reference else None
        ),
        "packed_format": "4bpp row-major, even x in the high nibble",
        "even_x_and_width": True,
        "seam_avoidance_x512": True,
        "codes_are_transport_codes_not_colour_names": True,
    }
    if version != "V1":
        doc["layout_revision"] = version
        doc["layout_change_vs_v1"] = (
            "(544,384) code6 -> code7 probe; (792,384) code7 background "
            "reference -> code6; slot coordinates unchanged; discriminates "
            "whether the P0 olive block follows code7 or the (792,384) position"
        )
    return doc


def atlas_roi_list_doc(version: str = "V1") -> dict[str, Any]:
    """tools/mf1750_multi_roi_lab.py-compatible region list."""

    regions, background_reference = atlas_regions(version)
    listed = list(regions) + ([background_reference] if background_reference else [])
    doc: dict[str, Any] = {
        "schema": "mf1750-partial-block-atlas-roi-list-v1",
        "screen": {"width": WIDTH, "height": HEIGHT},
        "regions": [
            {"name": roi["name"], "code": roi["code"], "x": roi["x"],
             "y": roi["y"], "w": roi["w"], "h": roi["h"]}
            for roi in listed
        ],
    }
    if version != "V1":
        doc["layout_revision"] = version
    return doc


def ptlw_roi_list_doc(version: str = "V1") -> dict[str, Any]:
    """Route B measurement regions: both controller halves per window.

    Each partial action paints one symmetric patch pair (same window
    coordinates and code written to CS1 and CS2 separately), so the
    measurement list carries both global positions per window plus two
    patch-free background strips for the outside-window checks.
    """

    patch_code = PTLW_PATCH_CODES[version]
    regions: list[dict[str, Any]] = []
    for window in PTLW_WINDOWS:
        for controller, x_offset in (("cs1", 0), ("cs2", CONTROLLER_WIDTH)):
            regions.append({
                "name": f"{window['name'].lower()}_{controller}",
                "code": patch_code,
                "x": window["x"] + x_offset,
                "y": window["y"],
                "w": window["w"],
                "h": window["h"],
            })
    regions.append({"name": "bg_north", "x": 432, "y": 24, "w": 160, "h": 32})
    regions.append({"name": "bg_south", "x": 432, "y": 556, "w": 160, "h": 32})
    doc: dict[str, Any] = {
        "schema": "mf1750-partial-block-ptlw-roi-list-v1",
        "screen": {"width": WIDTH, "height": HEIGHT},
        "regions": regions,
    }
    if version != "V1":
        doc["layout_revision"] = version
    return doc


# ---------------------------------------------------------------------------
# Route B contract: handoff-fixed windows and the sealed clean-PTLW transport.
# ---------------------------------------------------------------------------

PTLW_COMMAND = 0x83
PTLW_MODE = 0x01
PTLW_PAYLOAD_BYTES = 9
PRELOAD_CODE = 7
PTLW_WINDOWS: tuple[dict[str, int], ...] = (
    {"name": "A", "x": 48, "y": 64, "w": 160, "h": 120},
    {"name": "B", "x": 304, "y": 240, "w": 160, "h": 120},
    {"name": "C", "x": 48, "y": 416, "w": 160, "h": 120},
)
PTLW_PROFILE_LABELS = ("1E", "0E", "1C")


def ptlw_payload(window: dict[str, int]) -> bytes:
    x_end = window["x"] + window["w"] - 1
    y_end = window["y"] + window["h"] - 1
    return bytes((
        window["x"] >> 8, window["x"] & 0xFF,
        x_end >> 8, x_end & 0xFF,
        window["y"] >> 8, window["y"] & 0xFF,
        y_end >> 8, y_end & 0xFF,
        PTLW_MODE,
    ))


def _validate_ptlw_windows() -> None:
    if PTLW_PROFILE_LABELS != ("1E", "0E", "1C"):
        raise RuntimeError("route B action profile binding drifted")
    for window in PTLW_WINDOWS:
        if window["w"] != 160 or window["h"] != 120:
            raise RuntimeError("route B window geometry drifted")
        if window["x"] % 2 or window["w"] % 2:
            raise RuntimeError("route B window is not byte aligned")
        if window["x"] + window["w"] > CONTROLLER_WIDTH:
            raise RuntimeError("route B window escapes the controller half")
        if window["y"] + window["h"] > HEIGHT:
            raise RuntimeError("route B window escapes the panel")
    for index, left in enumerate(PTLW_WINDOWS):
        for right in PTLW_WINDOWS[index + 1:]:
            overlap = not (
                left["x"] + left["w"] <= right["x"]
                or right["x"] + right["w"] <= left["x"]
                or left["y"] + left["h"] <= right["y"]
                or right["y"] + right["h"] <= left["y"]
            )
            if overlap:
                raise RuntimeError("route B windows overlap")


def _uniform(byte_count: int, code: int) -> bytes:
    return bytes([(code << 4) | code]) * byte_count


def route_b_identities(version: str = "V1") -> dict[str, Any]:
    _validate_ptlw_windows()
    patch_code = PTLW_PATCH_CODES[version]
    preload = _uniform(CONTROLLER_DTM_BYTES, PRELOAD_CODE)
    crop = _uniform(160 * 120 // 2, patch_code)
    combined = preload + crop
    return {
        "preload_dtm": {
            "bytes": len(preload), "code": PRELOAD_CODE,
            "fnv1a": _fnv1a(preload), "sha256": _sha256(preload),
        },
        "crop_dtm": {
            "bytes": len(crop), "code": patch_code,
            "fnv1a": _fnv1a(crop), "sha256": _sha256(crop),
        },
        "combined_dtm": {
            "bytes": len(combined),
            "fnv1a": _fnv1a(combined), "sha256": _sha256(combined),
        },
        "ptlw_payloads_hex": [ptlw_payload(window).hex() for window in PTLW_WINDOWS],
    }


def _profile_reports() -> dict[str, dict[str, Any]]:
    # Family labels are explicit base-plus-group labels, not bitmasks:
    # 1E = base 0x0E + records 0-3 group, 1C = base 0x0C + group, 0E = base 0x0E.
    grayext_1e, _ = wmask.build_offline_variant(0x0E, True)
    plain_0e, _ = wmask.build_offline_variant(0x0E)
    grayext_1c, _ = wmask.build_offline_variant(0x0C, True)
    return {"1E": grayext_1e, "0E": plain_0e, "1C": grayext_1c}


# ---------------------------------------------------------------------------
# C++ renderers
# ---------------------------------------------------------------------------

def _cpp_spans_predicate(fn_name: str, records: Sequence[int]) -> str:
    spans = " ||\n          ".join(
        f"(index >= {183 + 11 * record} && index < {194 + 11 * record})"
        for record in records
    )
    return (
        f"constexpr bool {fn_name}(std::size_t index) {{\n"
        f"  return {spans};\n"
        f"}}\n"
    )


def _cpp_records_proof(struct_name: str, fn_name: str, ns_alias: str,
                       label: str) -> str:
    return f"""// C++11 compile-time proof for every one of the 535 transmitted R20 bytes.
template <std::size_t INDEX>
struct {struct_name} {{
  static constexpr bool value =
      ({ns_alias}::kR20Payload[INDEX] ==
       ({fn_name}(INDEX)
            ? l535_lut::commented::kR20Payload[INDEX]
            : l535_lut::active::kR20Payload[INDEX])) &&
      {struct_name}<INDEX + 1>::value;
}};
template <>
struct {struct_name}<535> {{
  static constexpr bool value = true;
}};
static_assert({struct_name}<0>::value,
              "{label} R20 sources do not match the preregistered composition");
"""


def _cpp_pwr_pll_asserts(ns_alias: str, label: str) -> str:
    pwr_chain = " &&\n                  ".join(
        f"{ns_alias}::kPowerPayload[{index}] == l535_lut::active::kPowerPayload[{index}]"
        for index in range(6)
    )
    return f"""static_assert({pwr_chain},
              "{label} PWR payload differs from active");
static_assert({ns_alias}::kR20Payload[1] == {ns_alias}::kPowerPayload[2] &&
                  {ns_alias}::kR20Payload[2] == {ns_alias}::kPowerPayload[3] &&
                  {ns_alias}::kR20Payload[3] == {ns_alias}::kPowerPayload[4] &&
                  {ns_alias}::kR20Payload[4] == {ns_alias}::kPowerPayload[5],
              "{label} R20[1:5] != PWR[2:6]: active header/PWR mirror broken");
static_assert({ns_alias}::kPllPayload[0] == 0x02 &&
                  {ns_alias}::kPllPayload[0] == l535_lut::active::kPllPayload[0] &&
                  {ns_alias}::kR20Payload[6] == {ns_alias}::kPllPayload[0],
              "{label} R20[6] != PLL[0] == active 0x02");
"""


def _cpp_r21_proof(struct_name: str, label: str) -> str:
    return f"""// The driver uploads l535_lut::active::kR21Payload directly.  Prove its full
// 704-byte active identity rather than sampling only the endpoints.
template <std::size_t INDEX>
struct {struct_name} {{
  static constexpr bool value =
      l535_lut::active::kR21Payload[INDEX] == 0xFF &&
      {struct_name}<INDEX + 1>::value;
}};
template <>
struct {struct_name}<704> {{
  static constexpr bool value = true;
}};
static_assert(l535_lut::active::kR21PayloadBytes == 704 &&
                  l535_lut::active::kR21IsAllFf &&
                  {struct_name}<0>::value,
              "{label}: active R21 is no longer the sealed 704 x 0xFF payload");
"""


def _r2g_tail() -> str:
    template = R2G_DRIVER_PATH.read_text(encoding="utf-8")
    return template[template.index("namespace {"):]


def _render_atlas_layout_inc(frame: bytes, cs1: bytes, cs2: bytes,
                             layout_sha: str, version: str = "V1") -> str:
    regions, _background_reference = atlas_regions(version)
    rois = ",\n".join(
        f"    {{{roi['x']}, {roi['y']}, {roi['w']}, {roi['h']}, 0x{roi['code']:02X}}}"
        for roi in regions
    )
    asserts = []
    for index, roi in enumerate(regions):
        asserts.append(
            f"static_assert(kRois[{index}].x == {roi['x']} && "
            f"kRois[{index}].y == {roi['y']} && "
            f"kRois[{index}].width == {roi['w']} && "
            f"kRois[{index}].height == {roi['h']} && "
            f"kRois[{index}].code == 0x{roi['code']:02X},\n"
            f"              \"route A ROI {index} identity drifted\");"
        )
        asserts.append(
            f"static_assert(kRois[{index}].x % 2 == 0 && "
            f"kRois[{index}].width % 2 == 0 &&\n"
            f"                  (kRois[{index}].x + kRois[{index}].width <= 512 ||\n"
            f"                   kRois[{index}].x >= 512) &&\n"
            f"                  kRois[{index}].x + kRois[{index}].width <= 1024 &&\n"
            f"                  kRois[{index}].y + kRois[{index}].height <= 600,\n"
            f"              \"route A ROI {index} violates alignment, seam, or bounds\");"
        )
    disjoint = []
    for left_index in range(len(regions)):
        for right_index in range(left_index + 1, len(regions)):
            disjoint.append(
                f"static_assert(kRois[{left_index}].x + kRois[{left_index}].width <= "
                f"kRois[{right_index}].x ||\n"
                f"                  kRois[{right_index}].x + kRois[{right_index}].width <= "
                f"kRois[{left_index}].x ||\n"
                f"                  kRois[{left_index}].y + kRois[{left_index}].height <= "
                f"kRois[{right_index}].y ||\n"
                f"                  kRois[{right_index}].y + kRois[{right_index}].height <= "
                f"kRois[{left_index}].y,\n"
                f"              \"route A ROIs {left_index}/{right_index} overlap\");"
            )
    if version == "V1":
        comment = """// Generated by tools/mf1750_partial_block_build.py.  Route A (P0) layout:
// white (code 7) background with seven fixed 192x160 ROIs, one per transport
// code {0,1,2,3,4,5,6}; every ROI sits fully inside one 512-pixel controller
// half, on even byte boundaries, clear of the x=512 cascade seam.  Codes are
// transport codes, not colour names."""
        namespace = "partial_atlas_1e"
    else:
        comment = """// Generated by tools/mf1750_partial_block_build.py.  Route A (P0) layout V2
// (handoff amendment 2): white (code 7) background; same eight slot
// coordinates as V1; codes 0-5 unchanged; (544,384) carries the code7 probe
// and (792,384) carries code6, discriminating whether the P0 olive block
// follows code7 or the (792,384) position.  Every ROI sits fully inside one
// 512-pixel controller half, on even byte boundaries, clear of the x=512
// cascade seam.  Codes are transport codes, not colour names."""
        namespace = "partial_atlas_1e_v2"
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

{comment}

namespace mf1750::partial_block::{namespace} {{

struct AtlasRoi {{
  std::uint16_t x;
  std::uint16_t y;
  std::uint16_t width;
  std::uint16_t height;
  std::uint8_t code;
}};

static constexpr std::uint8_t kBackgroundCode = 0x{ATLAS_BACKGROUND_CODE:02X};
static constexpr std::size_t kRoiCount = {len(regions)};
static constexpr AtlasRoi kRois[kRoiCount] = {{
{rois},
}};
static constexpr std::uint32_t kFrameFnv1a = 0x{_fnv1a(frame):08X}UL;
static constexpr char kFrameSha256[] = "{_sha256(frame)}";
static constexpr std::uint32_t kCs1DtmFnv1a = 0x{_fnv1a(cs1):08X}UL;
static constexpr std::uint32_t kCs2DtmFnv1a = 0x{_fnv1a(cs2):08X}UL;
static constexpr char kCs1DtmSha256[] = "{_sha256(cs1)}";
static constexpr char kCs2DtmSha256[] = "{_sha256(cs2)}";
static constexpr char kLayoutSha256[] = "{layout_sha}";

{chr(10).join(asserts)}
{chr(10).join(disjoint)}

}}  // namespace mf1750::partial_block::{namespace}
"""


def _render_ptlw_contract_inc(identities: dict[str, Any],
                              profiles: dict[str, dict[str, Any]],
                              version: str = "V1") -> str:
    patch_code = identities["crop_dtm"]["code"]
    windows = ",\n".join(
        f"    {{{window['x']}, {window['y']}, {window['w']}, {window['h']}}}"
        for window in PTLW_WINDOWS
    )
    payloads = ",\n".join(
        "    {" + ", ".join(f"0x{byte:02X}" for byte in bytes.fromhex(payload_hex)) + "}"
        for payload_hex in identities["ptlw_payloads_hex"]
    )
    r20_shas = ",\n".join(
        f'    "{profiles[label]["r20_sha256"]}"' for label in PTLW_PROFILE_LABELS
    )
    labels = ", ".join(f'"{label}"' for label in PTLW_PROFILE_LABELS)
    endpoint_asserts = []
    for index, window in enumerate(PTLW_WINDOWS):
        x_end = window["x"] + window["w"] - 1
        y_end = window["y"] + window["h"] - 1
        endpoint_asserts.append(
            f"static_assert(kWindows[{index}].x + kWindows[{index}].width - 1 == "
            f"0x{x_end:04X} &&\n"
            f"                  kWindows[{index}].y + kWindows[{index}].height - 1 == "
            f"0x{y_end:04X},\n"
            f"              \"route B window {index} inclusive endpoint changed\");"
        )
        endpoint_asserts.append(
            f"static_assert(kWindows[{index}].x % 2 == 0 && "
            f"kWindows[{index}].width % 2 == 0 &&\n"
            f"                  kWindows[{index}].x + kWindows[{index}].width <= 512 &&\n"
            f"                  kWindows[{index}].y + kWindows[{index}].height <= 600,\n"
            f"              \"route B window {index} violates alignment, seam, or bounds\");"
        )
    if version == "V1":
        comment = """// Generated by tools/mf1750_partial_block_build.py.  Route B (P1-P3) contract:
// PTLW command 0x83 with a 9-byte inclusive window (xe=x+w-1, ye=y+h-1,
// mode 0x01), full code-7 controller preload without refresh, then one
// inclusive PTLW and one cropped uniform DTM per controller, then
// PON/DRF/POF with no PTLW repeat after PON.  Each window is written to CS1
// and CS2 separately with identical coordinates and patch code, giving one
// symmetric patch pair per action.  Codes are transport codes, not colour
// names."""
        namespace = "ptlw"
    else:
        comment = """// Generated by tools/mf1750_partial_block_build.py.  Route B (P1-P3) contract
// V2 (handoff amendment 2): identical to V1 except the cropped uniform DTM
// patch code is 4 instead of 0 (code0 proved optically inert under 1E in the
// P0 atlas; P1 needs a visible optical response).  PTLW command 0x83 with a
// 9-byte inclusive window (xe=x+w-1, ye=y+h-1, mode 0x01), full code-7
// controller preload without refresh, then one inclusive PTLW and one cropped
// uniform DTM per controller, then PON/DRF/POF with no PTLW repeat after PON.
// Each window is written to CS1 and CS2 separately with identical coordinates
// and patch code, giving one symmetric patch pair per action.  Codes are
// transport codes, not colour names."""
        namespace = "ptlw_v2"
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

{comment}

namespace mf1750::partial_block::{namespace} {{

struct PtlwWindow {{
  std::uint16_t x;
  std::uint16_t y;
  std::uint16_t width;
  std::uint16_t height;
}};

static constexpr std::uint8_t kPartialWindowCommand = 0x{PTLW_COMMAND:02X};
static constexpr std::uint8_t kPartialWindowPayloadBytes = {PTLW_PAYLOAD_BYTES};
static constexpr std::uint8_t kPartialWindowMode = 0x{PTLW_MODE:02X};
static constexpr std::size_t kRuntimeActionCount = {len(PTLW_WINDOWS)};
static constexpr std::uint32_t kFullControllerDtmBytes = {CONTROLLER_DTM_BYTES};
static constexpr std::uint32_t kCroppedDtmBytes = {160 * 120 // 2};
static constexpr std::uint8_t kPreloadCode = 0x{PRELOAD_CODE:02X};
static constexpr std::uint8_t kPatchCode = 0x{patch_code:02X};
static constexpr PtlwWindow kWindows[kRuntimeActionCount] = {{
{windows},
}};
static constexpr std::uint8_t
    kPtlwPayloads[kRuntimeActionCount][kPartialWindowPayloadBytes] = {{
{payloads},
}};
static constexpr const char *kActionProfileLabels[kRuntimeActionCount] = {{
    {labels}}};
static constexpr char kProfileR20Sha256[kRuntimeActionCount][65] = {{
{r20_shas},
}};
static constexpr char kActivePwrSha256[] = "{wmask.PWR_SHA256}";
static constexpr char kActivePllSha256[] = "{wmask.PLL_SHA256}";
static constexpr char kR21Sha256[] = "{wmask.R21_SHA256}";
static constexpr char kPreloadDtmSha256[] = "{identities['preload_dtm']['sha256']}";
static constexpr std::uint32_t kPreloadDtmFnv1a = 0x{identities['preload_dtm']['fnv1a']:08X}UL;
static constexpr char kCropDtmSha256[] = "{identities['crop_dtm']['sha256']}";
static constexpr std::uint32_t kCropDtmFnv1a = 0x{identities['crop_dtm']['fnv1a']:08X}UL;
static constexpr char kCombinedDtmSha256[] = "{identities['combined_dtm']['sha256']}";
static constexpr std::uint32_t kCombinedDtmFnv1a = 0x{identities['combined_dtm']['fnv1a']:08X}UL;

{chr(10).join(endpoint_asserts)}

}}  // namespace mf1750::partial_block::{namespace}
"""


def _render_v3_contract_inc() -> str:
    identities = v3_identities()
    frames = identities["frames"]
    streams = identities["streams"]
    r20_1e = _profile_reports()["1E"]["r20_sha256"]
    steps = ",\n".join(
        f"    {{pbv3_step_kind::{('FACTORY_OTP_WHITE' if s['kind'] == 'factory_otp_white' else 'ACTIVE_UNIFORM')}, 0x{s['code']:02X}}}"
        for s in V3_NORMALIZE_SEQUENCE
    )
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

// Generated by tools/mf1750_partial_block_build.py.  Route A V3 contract
// (handoff 2026-10-20 amendment 2 + anomaly-2 protocols 1+2): one screening
// session first normalizes panel residual history, then measures.  Every
// frame, tuple, and the step sequence is compile-time pinned; no runtime
// frame, coordinate, or LUT input exists.  NORMALIZE = 2x factory-OTP white
// then 3x (active-table code0 black, active-table code1 white) alternating
// reset pairs, ending on white.  Codes are transport codes, not colour names.

namespace mf1750::partial_block::atlas_v3 {{

enum class pbv3_step_kind : std::uint8_t {{
  FACTORY_OTP_WHITE = 0,
  ACTIVE_UNIFORM = 1,
}};
struct V3NormalizeStep {{
  pbv3_step_kind kind;
  std::uint8_t code;
}};
static constexpr V3NormalizeStep kNormalizeSteps[] = {{
{steps},
}};
static constexpr std::size_t kNormalizeStepCount = {len(V3_NORMALIZE_SEQUENCE)};

static constexpr char kActiveR20Sha256[] = "{V3_ACTIVE_R20_SHA256}";
static constexpr char kProfile1ER20Sha256[] = "{r20_1e}";
static constexpr char kActivePwrSha256[] = "{wmask.PWR_SHA256}";
static constexpr char kActivePllSha256[] = "{wmask.PLL_SHA256}";
static constexpr char kActiveR21Sha256[] = "{wmask.R21_SHA256}";

static constexpr char kBlackFrameSha256[] = "{frames['black']['sha256']}";
static constexpr std::uint32_t kBlackFrameFnv1a = 0x{frames['black']['fnv1a']:08X}UL;
static constexpr char kWhiteFrameSha256[] = "{frames['white']['sha256']}";
static constexpr std::uint32_t kWhiteFrameFnv1a = 0x{frames['white']['fnv1a']:08X}UL;
static constexpr char kProbe7FrameSha256[] = "{frames['probe7']['sha256']}";
static constexpr std::uint32_t kProbe7FrameFnv1a = 0x{frames['probe7']['fnv1a']:08X}UL;
static constexpr char kAtlasV2FrameSha256[] = "{frames['atlas_v2']['sha256']}";
static constexpr std::uint32_t kAtlasV2FrameFnv1a = 0x{frames['atlas_v2']['fnv1a']:08X}UL;

static constexpr std::uint32_t kBlackStreamFnv1a = 0x{streams['black']:08X}UL;
static constexpr std::uint32_t kWhiteStreamFnv1a = 0x{streams['white']:08X}UL;
static constexpr std::uint32_t kProbe7StreamFnv1a = 0x{streams['probe7']:08X}UL;
static constexpr std::uint32_t kAtlasV2Cs1StreamFnv1a = 0x{streams['atlas_v2_cs1']:08X}UL;
static constexpr std::uint32_t kAtlasV2Cs2StreamFnv1a = 0x{streams['atlas_v2_cs2']:08X}UL;

static_assert(kNormalizeStepCount == 8 &&
                  kNormalizeSteps[0].kind == pbv3_step_kind::FACTORY_OTP_WHITE &&
                  kNormalizeSteps[1].kind == pbv3_step_kind::FACTORY_OTP_WHITE &&
                  kNormalizeSteps[2].code == 0x00 &&
                  kNormalizeSteps[3].code == 0x01 &&
                  kNormalizeSteps[4].code == 0x00 &&
                  kNormalizeSteps[5].code == 0x01 &&
                  kNormalizeSteps[6].code == 0x00 &&
                  kNormalizeSteps[7].code == 0x01 &&
                  kNormalizeSteps[7].kind == pbv3_step_kind::ACTIVE_UNIFORM,
              "V3 NORMALIZE sequence drifted from 2x OTP white + 3x "
              "(black,white) alternating reset pairs");

}}  // namespace mf1750::partial_block::atlas_v3
"""


def _render_v3_api_header() -> str:
    return """#pragma once

#include <cstddef>
#include <cstdint>

// Partial-block route A V3 (P0 re-verification with normalization + probes):
// every action is a fixed compiled identity validated before any panel I/O.
// This API accepts no frame, coordinate, colour code, LUT, voltage, timing,
// SPI-frequency, retry, or recovery parameter.  Actions are never chained
// automatically; each runs only on its own explicit endpoint.
enum class EpdPartialAtlasV3Role : std::uint8_t {
  Normalize = 0,
  ProbeCode7 = 1,
  ProbeCode1 = 2,
  AtlasV2 = 3,
  WhiteRecovery = 4,
};

struct EpdPartialAtlasV3StepReport {
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledPartialAtlasV3Fixtures();
bool epdDisplayCompiledPartialAtlasV3(EpdPartialAtlasV3Role role);
const EpdPartialAtlasV3StepReport *epdGetPartialAtlasV3StepReports(
    std::size_t *count);
"""


def _render_v3_driver_head() -> str:
    records = wmask.selected_records(0x0E, True)
    return (
        """// Dedicated translation unit for partial-block route A V3 (P0
// re-verification with normalization + probes, handoff amendment 2 and
// anomaly-2 protocols 1+2): one screening session switches per action between
// the factory-OTP path, the pinned legacy-active runtime tuple (maximal
// charge reset), and the wf_wmask_1E GrayExt tuple (base 0x0E plus the whole
// records 0-3 group; the family label is not a bitmask).  Every tuple's
// R20/PWR/PLL/R21/PSR bytes are the same compiled objects as their sealed
// sources; the runtime tail below is byte-identical to the pinned R2G
// template.  Production, the wf_wmask_*, and the V1/V2 translation units stay
// untouched.
#include "epd_driver.h"

#include <SPI.h>
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD)
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"
#include "partial_atlas_1e_v3_api.h"

#if !defined(MF1750_L535_FRAME_PATH_BUILD) || MF1750_L535_FRAME_PATH_BUILD != 1
#error "route A V3 requires the frozen L535 frame path build"
#endif
#if !defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD) || \\
    MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD != 1
#error "route A V3 requires MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD=1"
#endif
#if !defined(MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY) || \\
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1
#error "route A V3 requires the factory-OTP fixture for its white steps"
#endif
#if !defined(MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1 || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 0
#error "route A V3 binds the WF23_25 factory-OTP white profile exactly"
#endif

#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_wf_wmask_1E.inc"
namespace pb_profile_1e = mf1750::runtime_lut::wf_wmask_1E;
// The inherited full-frame path (unused by every V3 action) binds the 1E
// tuple so the byte-identical runtime tail compiles unchanged.
namespace l535_variant = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/partial_atlas_1e_v2_layout.inc"
namespace pb_atlas_v2 = mf1750::partial_block::partial_atlas_1e_v2;
#include "generated/partial_atlas_1e_v3_contract.inc"
namespace pbv3 = mf1750::partial_block::atlas_v3;

// The V3 atlas action must carry the exact V2 frame: the V2 layout include's
// pinned frame identity is the V2 bundle's frame sha 1bca805d....
static_assert(pb_atlas_v2::kFrameFnv1a == pbv3::kAtlasV2FrameFnv1a,
              "V3 atlas frame fnv1a differs from the V2 frame");

"""
        + _cpp_spans_predicate("pbv3Profile1EUseCommented", records)
        + "\n"
        + _cpp_records_proof("Pbv3Profile1ERecordsMatch", "pbv3Profile1EUseCommented",
                             "pb_profile_1e", "route A V3 1E")
        + "\n"
        + _cpp_pwr_pll_asserts("pb_profile_1e", "route A V3 1E")
        + "\n"
        + _cpp_r21_proof("Pbv3ActiveR21Unchanged", "route A V3")
        + "\n"
    )


def _render_atlas_api_header() -> str:
    return """#pragma once

// Partial-block route A (P0): compiled 1E multi-code atlas fixture.  The
// complete frame, layout, and 1E tuple identities are compiled into the
// binary and validated before any panel I/O.  This API accepts no frame,
// coordinate, colour code, LUT, voltage, timing, SPI-frequency, retry, or
// recovery parameter.
bool epdValidateCompiledPartialAtlas1EFixture();
bool epdDisplayCompiledPartialAtlas1E();
"""


def _render_ptlw_api_header() -> str:
    return """#pragma once

#include <cstdint>

// Partial-block route B (P1-P3): clean-PTLW cross-waveform partial-window
// fixture plus the factory-OTP white anchor/recovery actions.  Every action is
// a fixed compiled identity validated before any panel I/O.  This API accepts
// no frame, coordinate, colour code, LUT, voltage, timing, SPI-frequency,
// retry, or recovery parameter.  Actions are never chained automatically.
enum class EpdPartialBlockPtlwRole : std::uint8_t {
  FactoryWhite = 0,
  PatchA1E = 1,
  PatchB0E = 2,
  PatchC1C = 3,
  WhiteRecovery = 4,
};
bool epdValidateCompiledPartialBlockPtlwFixtures();
bool epdDisplayCompiledPartialBlockPtlw(EpdPartialBlockPtlwRole role);
"""


def _render_atlas_driver_head(version: str = "V1") -> str:
    records = wmask.selected_records(0x0E, True)
    if version == "V1":
        comment = """// Dedicated translation unit for partial-block route A (P0): the fixed 1E
// GrayExt tuple (base 0x0E plus the whole records 0-3 group; the family label
// is not a bitmask) drives one compiled white-background seven-code atlas
// frame through the sealed full-frame L535 path.  R20/PWR/PLL/R21/PSR and the
// runtime sequence are byte-identical to the sealed wf_wmask_1E build; the
// runtime tail below is byte-identical to the pinned R2G template.  Production
// and the wf_wmask_* translation units stay untouched."""
        layout_inc = "partial_atlas_1e_layout.inc"
        atlas_ns = "partial_atlas_1e"
    else:
        comment = """// Dedicated translation unit for partial-block route A (P0) V2 (handoff
// amendment 2): the fixed 1E GrayExt tuple (base 0x0E plus the whole records
// 0-3 group; the family label is not a bitmask) drives the compiled
// white-background atlas frame whose (544,384) slot carries the code7 probe
// and whose (792,384) slot carries code6, through the sealed full-frame L535
// path.  R20/PWR/PLL/R21/PSR and the runtime sequence are byte-identical to
// the sealed wf_wmask_1E build; the runtime tail below is byte-identical to
// the pinned R2G template.  Production and the wf_wmask_* translation units
// stay untouched."""
        layout_inc = "partial_atlas_1e_v2_layout.inc"
        atlas_ns = "partial_atlas_1e_v2"
    return (
        f"""{comment}
#include "epd_driver.h"

#include <SPI.h>
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD)
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"
#include "partial_atlas_1e_api.h"

#if !defined(MF1750_L535_FRAME_PATH_BUILD) || MF1750_L535_FRAME_PATH_BUILD != 1
#error "partial-block route A requires the frozen L535 frame path build"
#endif
#if !defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD) || \\
    MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD != 1
#error "partial-block route A requires MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD=1"
#endif

#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_wf_wmask_1E.inc"
namespace l535_variant = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/{layout_inc}"
namespace pb_atlas = mf1750::partial_block::{atlas_ns};

static_assert(sizeof(l535_variant::kR20Payload) == 535,
              "route A 1E R20 payload must be exactly 535 bytes");

"""
        + _cpp_spans_predicate("pbAtlas1EUseCommented", records)
        + "\n"
        + _cpp_records_proof("PbAtlas1ERecordsMatch", "pbAtlas1EUseCommented",
                             "l535_variant", "route A 1E")
        + "\n"
        + _cpp_pwr_pll_asserts("l535_variant", "route A 1E")
        + "\n"
        + _cpp_r21_proof("PbAtlas1EActiveR21Unchanged", "route A 1E")
        + "\n"
    )


def _render_ptlw_driver_head(version: str = "V1") -> str:
    profile_defs = []
    for struct_name, fn_name, alias, label in (
        ("PbProfileARecordsMatch", "pbProfileAUseCommented", "pb_profile_a", "route B profile A (1E)"),
        ("PbProfileBRecordsMatch", "pbProfileBUseCommented", "pb_profile_b", "route B profile B (0E)"),
        ("PbProfileCRecordsMatch", "pbProfileCUseCommented", "pb_profile_c", "route B profile C (1C)"),
    ):
        mask, group = {"1E": (0x0E, True), "0E": (0x0E, False), "1C": (0x0C, True)}[
            label.split("(")[1].rstrip(")")
        ]
        records = wmask.selected_records(mask, group)
        profile_defs.append(_cpp_spans_predicate(fn_name, records))
        profile_defs.append(
            _cpp_records_proof(struct_name, fn_name, alias, label)
        )
        profile_defs.append(_cpp_pwr_pll_asserts(alias, label))
    pwr_cross = " &&\n                  ".join(
        f"pb_profile_a::kPowerPayload[{index}] == pb_profile_b::kPowerPayload[{index}] &&\n"
        f"                  pb_profile_b::kPowerPayload[{index}] == pb_profile_c::kPowerPayload[{index}]"
        for index in range(6)
    )
    if version == "V1":
        comment = """// Dedicated translation unit for partial-block route B (P1-P3): three
// fixed clean-PTLW partial-window actions whose complete R20 tuples are the
// same compiled objects as the sealed wf_wmask_1E / wf_wmask_0E / wf_wmask_1C
// full-frame builds (1E/1C family labels are base-plus-group labels, not
// bitmasks).  PWR, PLL=0x02, R21, PSR bytes are the pinned active payloads
// shared by every WMASK profile; the runtime tail below is byte-identical to
// the pinned R2G template.  Production and the wf_wmask_* translation units
// stay untouched.  Factory-OTP white anchors and closes the action sequence."""
        contract_inc = "partial_block_ptlw_contract.inc"
        ptlw_ns = "ptlw"
    else:
        comment = """// Dedicated translation unit for partial-block route B (P1-P3) V2 (handoff
// amendment 2): identical to V1 except the cropped uniform DTM patch code is
// 4 instead of 0 (code0 proved optically inert under 1E in the P0 atlas; P1
// needs a visible optical response).  Three fixed clean-PTLW partial-window
// actions whose complete R20 tuples are the same compiled objects as the
// sealed wf_wmask_1E / wf_wmask_0E / wf_wmask_1C full-frame builds (1E/1C
// family labels are base-plus-group labels, not bitmasks).  PWR, PLL=0x02,
// R21, PSR bytes are the pinned active payloads shared by every WMASK profile;
// the runtime tail below is byte-identical to the pinned R2G template.
// Production and the wf_wmask_* translation units stay untouched.
// Factory-OTP white anchors and closes the action sequence."""
        contract_inc = "partial_block_ptlw_v2_contract.inc"
        ptlw_ns = "ptlw_v2"
    return (
        f"""{comment}
#include "epd_driver.h"

#include <SPI.h>
#if defined(MF1750_PARTIAL_BLOCK_PTLW_BUILD)
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"
#include "partial_block_ptlw_api.h"

#if !defined(MF1750_L535_FRAME_PATH_BUILD) || MF1750_L535_FRAME_PATH_BUILD != 1
#error "partial-block route B requires the frozen L535 frame path build"
#endif
#if !defined(MF1750_PARTIAL_BLOCK_PTLW_BUILD) || \\
    MF1750_PARTIAL_BLOCK_PTLW_BUILD != 1
#error "partial-block route B requires MF1750_PARTIAL_BLOCK_PTLW_BUILD=1"
#endif
#if !defined(MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY) || \\
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1
#error "route B white anchor/recovery requires the factory-OTP fixture"
#endif
#if !defined(MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1 || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 0
#error "route B binds the WF23_25 factory-OTP white profile exactly"
#endif

#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_wf_wmask_1E.inc"
namespace pb_profile_a = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/spd1657_wf_wmask_0E.inc"
namespace pb_profile_b = mf1750::runtime_lut::wf_wmask_0E;
#include "generated/spd1657_wf_wmask_1C.inc"
namespace pb_profile_c = mf1750::runtime_lut::wf_wmask_1C;
// The inherited full-frame path (unused by every route B action) binds the
// action-A 1E tuple so the byte-identical runtime tail compiles unchanged.
namespace l535_variant = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/{contract_inc}"
namespace pb = mf1750::partial_block::{ptlw_ns};

static_assert(sizeof(pb_profile_a::kR20Payload) == 535 &&
                  sizeof(pb_profile_b::kR20Payload) == 535 &&
                  sizeof(pb_profile_c::kR20Payload) == 535,
              "route B R20 payloads must be exactly 535 bytes");

"""
        + "\n".join(profile_defs)
        + f"""static_assert({pwr_cross},
              "route B PWR payloads are not the same pinned active bytes");
static_assert(pb_profile_a::kPllPayload[0] == pb_profile_b::kPllPayload[0] &&
                  pb_profile_b::kPllPayload[0] == pb_profile_c::kPllPayload[0],
              "route B PLL payloads are not the same pinned active byte");
"""
        + "\n"
        + _cpp_r21_proof("PbActiveR21Unchanged", "route B")
        + "\n"
    )


def _route_a_fixture(version: str) -> str:
    if version == "V1":
        comment = """// Route A (P0) compiled multi-code atlas fixture
// (docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md).  One fixed
// white-background 1024x600 frame carries seven fixed ROIs, one per transport
// code {0,1,2,3,4,5,6}, refreshed once through the sealed 1E full-frame path."""
    else:
        comment = """// Route A (P0) compiled multi-code atlas fixture V2 (handoff amendment 2).
// One fixed white-background 1024x600 frame carries eight fixed ROIs at the
// V1 slot coordinates with codes {0,1,2,3,4,5,7,6} — the (544,384) slot is the
// code7 probe and the (792,384) slot carries code6 — refreshed once through
// the sealed 1E full-frame path."""
    return (
        "\n// ===========================================================================\n"
        + comment
        + """
// The frame is rebuilt and hash-validated before any panel I/O; no
// caller-controlled frame, coordinate, code, LUT, voltage, timing, retry, or
// recovery parameter is accepted."""
        + _ROUTE_A_FIXTURE_BODY
    )


_ROUTE_A_FIXTURE_BODY = """
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD)

namespace {

constexpr const char *PB_ATLAS_FAILURE_ALLOCATION = "allocation";
constexpr const char *PB_ATLAS_FAILURE_FRAME_IDENTITY = "full_sha";
constexpr const char *PB_ATLAS_FAILURE_CASCADE_PREPARE = "cascade_prepare";
constexpr const char *PB_ATLAS_FAILURE_RUNTIME_LUT = "runtime_lut_load";
constexpr const char *PB_ATLAS_FAILURE_STREAM_IDENTITY = "stream_identity";
constexpr const char *PB_ATLAS_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";

bool pbAtlasDigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

void pbAtlasBuildFrame(uint8_t *frame) {
  const uint8_t backgroundPair = static_cast<uint8_t>(
      (pb_atlas::kBackgroundCode << 4) | pb_atlas::kBackgroundCode);
  std::memset(frame, backgroundPair, EPD_FRAME_BYTES);
  for (size_t index = 0; index < pb_atlas::kRoiCount; ++index) {
    const pb_atlas::AtlasRoi &roi = pb_atlas::kRois[index];
    const uint8_t pair = static_cast<uint8_t>((roi.code << 4) | roi.code);
    for (uint16_t y = roi.y; y < roi.y + roi.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * (EPD_WIDTH / 2) + roi.x / 2,
                  pair, roi.width / 2);
    }
  }
}

bool pbAtlasValidateFrame(uint8_t *frame, uint32_t *fnvOut) {
  pbAtlasBuildFrame(frame);
  const uint32_t frameFnv = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  const int result = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  if (fnvOut) *fnvOut = frameFnv;
  return result == 0 && frameFnv == pb_atlas::kFrameFnv1a &&
         pbAtlasDigestMatchesHex(digest, pb_atlas::kFrameSha256);
}

}  // namespace

bool epdValidateCompiledPartialAtlas1EFixture() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  const bool valid = pbAtlasValidateFrame(frame, nullptr);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledPartialAtlas1E() {
  // epdBeginOperation is diagnostic-only.  The compiled frame identity is
  // checked before SPI startup, controller selection, reset, or any command.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, PB_ATLAS_FAILURE_ALLOCATION);
  }
  uint32_t frameFnv = 0;
  const bool identityOk = pbAtlasValidateFrame(frame, &frameFnv);
  diagnosticReport.inputFrameFnv1a = frameFnv;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PB_ATLAS_FAILURE_FRAME_IDENTITY);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        PB_ATLAS_FAILURE_CASCADE_PREPARE);
  }
  if (!epdLoadL535RuntimeLut()) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PB_ATLAS_FAILURE_RUNTIME_LUT);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);
  if (diagnosticReport.cs1DtmFnv1a != pb_atlas::kCs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != pb_atlas::kCs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        PB_ATLAS_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(PB_ATLAS_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

#endif  // MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD
"""

_ROUTE_B_FIXTURE = """
// ===========================================================================
// Route B (P1-P3) cross-waveform partial-window fixture
// (docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md).  Three fixed
// actions run the sealed clean-PTLW transport: full code-7 controller preload
// without refresh, one inclusive PTLW (0x83, 9-byte payload) per controller,
// one cropped uniform DTM per controller, then PON/DRF/POF with no PTLW
// repeat after PON and no BTST2/CDI stage.  Each action's complete R20 tuple
// is the same compiled object as the corresponding sealed full-frame profile
// build (A=1E, B=0E, C=1C); PWR/PLL/R21 are the shared pinned active payloads.
// No caller-controlled frame, coordinate, code, LUT, voltage, timing, retry,
// or recovery parameter is accepted.
#if defined(MF1750_PARTIAL_BLOCK_PTLW_BUILD)

namespace {

constexpr const char *PB_FAILURE_ALLOCATION = "allocation";
constexpr const char *PB_FAILURE_ROLE = "role";
constexpr const char *PB_FAILURE_PTLW_PAYLOAD = "ptlw_payload";
constexpr const char *PB_FAILURE_TRANSPORT_IDENTITY = "transport_identity";
constexpr const char *PB_FAILURE_PROFILE_IDENTITY = "profile_identity";
constexpr const char *PB_FAILURE_CASCADE_PREPARE = "cascade_prepare";
constexpr const char *PB_FAILURE_GLOBAL_CONFIG = "global_config";
constexpr const char *PB_FAILURE_CS1_WAVEFORM = "cs1_waveform";
constexpr const char *PB_FAILURE_CS2_WAVEFORM = "cs2_waveform";
constexpr const char *PB_FAILURE_PRELOAD_STREAM = "preload_stream_identity";
constexpr const char *PB_FAILURE_STREAM_IDENTITY = "stream_identity";
constexpr const char *PB_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";

bool pbDigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool pbPayloadShaMatches(const uint8_t *payload, size_t length,
                         const char *expected, int32_t *errorCode) {
  if (!payload || length == 0 || !errorCode) return false;
  uint8_t digest[32] = {};
  *errorCode = mbedtls_sha256_ret(payload, length, digest, 0);
  return *errorCode == 0 && pbDigestMatchesHex(digest, expected);
}

const uint8_t *pbProfileR20(size_t actionIndex) {
  switch (actionIndex) {
    case 0:
      return pb_profile_a::kR20Payload;
    case 1:
      return pb_profile_b::kR20Payload;
    case 2:
      return pb_profile_c::kR20Payload;
    default:
      return nullptr;
  }
}

bool pbValidateProfileTuples(int32_t *errorCode) {
  // Runtime re-proof of the compile-time identities: every transmitted R20
  // byte stream hashes to the pinned full-frame profile SHA-256, and the
  // shared PWR/PLL/R21 payloads hash to the pinned active values.
  for (size_t index = 0; index < pb::kRuntimeActionCount; ++index) {
    if (!pbPayloadShaMatches(pbProfileR20(index), 535,
                             pb::kProfileR20Sha256[index], errorCode)) {
      return false;
    }
  }
  return pbPayloadShaMatches(pb_profile_a::kPowerPayload, 6,
                             pb::kActivePwrSha256, errorCode) &&
         pbPayloadShaMatches(pb_profile_b::kPowerPayload, 6,
                             pb::kActivePwrSha256, errorCode) &&
         pbPayloadShaMatches(pb_profile_c::kPowerPayload, 6,
                             pb::kActivePwrSha256, errorCode) &&
         pbPayloadShaMatches(pb_profile_a::kPllPayload, 1,
                             pb::kActivePllSha256, errorCode) &&
         pbPayloadShaMatches(pb_profile_b::kPllPayload, 1,
                             pb::kActivePllSha256, errorCode) &&
         pbPayloadShaMatches(pb_profile_c::kPllPayload, 1,
                             pb::kActivePllSha256, errorCode) &&
         pbPayloadShaMatches(l535_lut::active::kR21Payload, 704,
                             pb::kR21Sha256, errorCode);
}

bool pbUniformDtmIdentity(uint32_t byteCount, uint8_t code, uint32_t *fnvOut,
                          uint8_t digest[32], int32_t *errorCode) {
  if (!fnvOut || !digest || !errorCode || byteCount == 0) return false;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  uint8_t block[256];
  std::memset(block, pair, sizeof(block));
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  uint32_t remaining = byteCount;
  while (result == 0 && remaining > 0) {
    const size_t chunk = remaining < sizeof(block) ? remaining : sizeof(block);
    result = mbedtls_sha256_update_ret(&context, block, chunk);
    for (size_t index = 0; index < chunk; ++index) {
      hash = fnv1aUpdate(hash, pair);
    }
    remaining -= chunk;
  }
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  if (result != 0) return false;
  *fnvOut = hash;
  return true;
}

bool pbCombinedDtmIdentity(uint32_t *fnvOut, uint8_t digest[32],
                           int32_t *errorCode) {
  if (!fnvOut || !digest || !errorCode) return false;
  uint8_t block[256];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (uint8_t stage = 0; stage < 2 && result == 0; ++stage) {
    const uint8_t code = stage == 0 ? pb::kPreloadCode : pb::kPatchCode;
    const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
    uint32_t remaining =
        stage == 0 ? pb::kFullControllerDtmBytes : pb::kCroppedDtmBytes;
    std::memset(block, pair, sizeof(block));
    while (result == 0 && remaining > 0) {
      const size_t chunk = remaining < sizeof(block) ? remaining : sizeof(block);
      result = mbedtls_sha256_update_ret(&context, block, chunk);
      for (size_t index = 0; index < chunk; ++index) {
        hash = fnv1aUpdate(hash, pair);
      }
      remaining -= chunk;
    }
  }
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  if (result != 0) return false;
  *fnvOut = hash;
  return true;
}

bool pbValidateTransportIdentities(int32_t *errorCode) {
  uint32_t fnv = 0;
  uint8_t digest[32] = {};
  if (!pbUniformDtmIdentity(pb::kFullControllerDtmBytes, pb::kPreloadCode,
                            &fnv, digest, errorCode) ||
      fnv != pb::kPreloadDtmFnv1a ||
      !pbDigestMatchesHex(digest, pb::kPreloadDtmSha256)) {
    return false;
  }
  if (!pbUniformDtmIdentity(pb::kCroppedDtmBytes, pb::kPatchCode,
                            &fnv, digest, errorCode) ||
      fnv != pb::kCropDtmFnv1a ||
      !pbDigestMatchesHex(digest, pb::kCropDtmSha256)) {
    return false;
  }
  if (!pbCombinedDtmIdentity(&fnv, digest, errorCode) ||
      fnv != pb::kCombinedDtmFnv1a ||
      !pbDigestMatchesHex(digest, pb::kCombinedDtmSha256)) {
    return false;
  }
  return true;
}

void pbExpectedPtlwPayload(size_t actionIndex,
                           uint8_t out[pb::kPartialWindowPayloadBytes]) {
  const pb::PtlwWindow &window = pb::kWindows[actionIndex];
  const uint16_t xEnd = window.x + window.width - 1;
  const uint16_t yEnd = window.y + window.height - 1;
  out[0] = static_cast<uint8_t>(window.x >> 8);
  out[1] = static_cast<uint8_t>(window.x & 0xFF);
  out[2] = static_cast<uint8_t>(xEnd >> 8);
  out[3] = static_cast<uint8_t>(xEnd & 0xFF);
  out[4] = static_cast<uint8_t>(window.y >> 8);
  out[5] = static_cast<uint8_t>(window.y & 0xFF);
  out[6] = static_cast<uint8_t>(yEnd >> 8);
  out[7] = static_cast<uint8_t>(yEnd & 0xFF);
  out[8] = pb::kPartialWindowMode;
}

bool pbPtlwPayloadMatches(size_t actionIndex) {
  uint8_t expected[pb::kPartialWindowPayloadBytes] = {};
  pbExpectedPtlwPayload(actionIndex, expected);
  return std::memcmp(expected, pb::kPtlwPayloads[actionIndex],
                     pb::kPartialWindowPayloadBytes) == 0;
}

void pbWritePartialWindow(size_t actionIndex, bool secondController) {
  setActiveControllers(!secondController, secondController);
  epdCommand(pb::kPartialWindowCommand);
  for (uint8_t value : pb::kPtlwPayloads[actionIndex]) epdData(value);
}

uint32_t pbStreamUniformDtm(bool secondController, uint32_t byteCount,
                            uint8_t code, uint32_t hash) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(byteCount, pair);
  for (uint32_t index = 0; index < byteCount; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

bool pbApplyTupleGlobalConfig() {
  // Byte-identical to the sealed full-frame runtime LUT load: PSR {5F,E9},
  // active PWR, wait, PLL 0x02, TRES 512x600, broadcast to both controllers.
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  epdWriteL535Payload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  epdWriteL535Payload(0x01, pb_profile_a::kPowerPayload, 6);
  if (!epdWaitIdle("partial-block PWR")) return false;
  epdWriteL535Payload(0x30, pb_profile_a::kPllPayload, 1);
  epdWriteL535Payload(0x61, kControllerTres, sizeof(kControllerTres));
  return true;
}

bool pbUploadTupleToController(bool secondController, size_t actionIndex) {
  setActiveControllers(!secondController, secondController);
  static constexpr uint8_t kHiddenEnable[1] = {0x01};
  epdWriteL535Payload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
  if (!epdWaitIdle(secondController ? "partial-block CS2 E9"
                                    : "partial-block CS1 E9")) {
    return false;
  }
  epdWriteL535Payload(0x20, pbProfileR20(actionIndex), 535);
  epdWriteL535Payload(0x21, l535_lut::active::kR21Payload, 704);
  return true;
}

bool pbRefreshCleanPtlw() {
  // Sealed clean-PTLW refresh: PON -> DRF 0x00 -> POF 0x00, no BTST2/CDI
  // stage and no PTLW repeat after PON.
  setActiveControllers(true, true);
  if (!epdRequireIdleBeforeCommand("PON")) {
    epdRequestFailSafePowerOff("POF cleanup after pre-PON busy");
    return false;
  }
  epdCommand(PON);
  if (!epdWaitBusyThenIdle("PON")) {
    epdRequestFailSafePowerOff("POF cleanup after PON failure");
    return false;
  }
  if (!epdRequireIdleBeforeCommand("DRF")) {
    epdRequestFailSafePowerOff("POF cleanup after pre-DRF busy");
    return false;
  }
  epdCommand(DRF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("DRF")) {
    epdRequestFailSafePowerOff("POF cleanup after DRF failure");
    return false;
  }
  if (!epdRequireIdleBeforeCommand("POF")) {
    epdRequestFailSafePowerOff("POF cleanup after pre-POF busy");
    return false;
  }
  epdCommand(POF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("POF")) {
    diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
    delay(5);
    diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
    return false;
  }
  delay(10);
  return epdPostDisplayPowerCut();
}

bool pbDisplayPartialAction(size_t actionIndex) {
  // epdBeginOperation is diagnostic-only.  Window, PTLW payload, transport,
  // and profile identities are all validated before SPI startup, controller
  // selection, reset, or any command.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (actionIndex >= pb::kRuntimeActionCount) {
    return epdRejectBeforePanelIo(started, PB_FAILURE_ROLE);
  }
  if (!pbPtlwPayloadMatches(actionIndex)) {
    return epdRejectBeforePanelIo(started, PB_FAILURE_PTLW_PAYLOAD);
  }
  int32_t identityError = 0;
  if (!pbValidateTransportIdentities(&identityError)) {
    return epdRejectBeforePanelIo(started, PB_FAILURE_TRANSPORT_IDENTITY,
                                  identityError);
  }
  if (!pbValidateProfileTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PB_FAILURE_PROFILE_IDENTITY,
                                  identityError);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_CASCADE_PREPARE);
  }
  if (!pbApplyTupleGlobalConfig()) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_GLOBAL_CONFIG);
  }
  if (!pbUploadTupleToController(false, actionIndex)) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_CS1_WAVEFORM);
  }
  if (!pbUploadTupleToController(true, actionIndex)) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_CS2_WAVEFORM);
  }

  // Sealed order: full preload on both controllers first (no refresh), then
  // one inclusive PTLW plus one cropped DTM per controller.
  const uint32_t cs1PreloadFnv = pbStreamUniformDtm(
      false, pb::kFullControllerDtmBytes, pb::kPreloadCode, FNV1A_OFFSET_BASIS);
  const uint32_t cs2PreloadFnv = pbStreamUniformDtm(
      true, pb::kFullControllerDtmBytes, pb::kPreloadCode, FNV1A_OFFSET_BASIS);
  const uint32_t cs1Started = millis();
  pbWritePartialWindow(actionIndex, false);
  const uint32_t cs1CombinedFnv = pbStreamUniformDtm(
      false, pb::kCroppedDtmBytes, pb::kPatchCode, cs1PreloadFnv);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  pbWritePartialWindow(actionIndex, true);
  const uint32_t cs2CombinedFnv = pbStreamUniformDtm(
      true, pb::kCroppedDtmBytes, pb::kPatchCode, cs2PreloadFnv);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.cs1DtmFnv1a = cs1CombinedFnv;
  diagnosticReport.cs2DtmFnv1a = cs2CombinedFnv;
  diagnosticReport.mappingApplied = true;
  if (cs1PreloadFnv != pb::kPreloadDtmFnv1a ||
      cs2PreloadFnv != pb::kPreloadDtmFnv1a) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_PRELOAD_STREAM);
  }
  if (cs1CombinedFnv != pb::kCombinedDtmFnv1a ||
      cs2CombinedFnv != pb::kCombinedDtmFnv1a) {
    return epdFinishFailedOperationSafe(started, PB_FAILURE_STREAM_IDENTITY);
  }
  const bool ok = pbRefreshCleanPtlw();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(PB_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

}  // namespace

// The sealed factory-OTP white recovery fixture is supplied by the runtime
// tail above (ec5_factory_otp_white_recovery_driver.inc under
// MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1) and provides the route B white
// anchor and white recovery actions.

bool epdValidateCompiledPartialBlockPtlwFixtures() {
  int32_t errorCode = 0;
  for (size_t index = 0; index < pb::kRuntimeActionCount; ++index) {
    if (!pbPtlwPayloadMatches(index)) return false;
  }
  return pbValidateTransportIdentities(&errorCode) &&
         pbValidateProfileTuples(&errorCode) &&
         epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
}

bool epdDisplayCompiledPartialBlockPtlw(EpdPartialBlockPtlwRole role) {
  switch (role) {
    case EpdPartialBlockPtlwRole::FactoryWhite:
      return epdDisplayCompiledFactoryOtpWhiteRecovery();
    case EpdPartialBlockPtlwRole::PatchA1E:
      return pbDisplayPartialAction(0);
    case EpdPartialBlockPtlwRole::PatchB0E:
      return pbDisplayPartialAction(1);
    case EpdPartialBlockPtlwRole::PatchC1C:
      return pbDisplayPartialAction(2);
    case EpdPartialBlockPtlwRole::WhiteRecovery:
      return epdDisplayCompiledFactoryOtpWhiteRecovery();
  }
  return false;
}

#endif  // MF1750_PARTIAL_BLOCK_PTLW_BUILD
"""


def _render_main(template: str, tag: str, boot: str, api_header: str,
                 build_flag: str, enum_members: str, endpoints: str,
                 switch_cases: str, remove_frame_ingress: bool) -> str:
    if template.count(R2G_TAG) != 1 or template.count(R2G_BOOT) != 1:
        raise RuntimeError("R2G main template identity anchors drifted")
    text = template.replace(R2G_TAG, tag).replace(R2G_BOOT, boot)
    include_anchor = '#include "epd_config.h"\n'
    if text.count(include_anchor) != 1:
        raise RuntimeError("R2G main include anchor drifted")
    text = text.replace(
        include_anchor,
        include_anchor + f'#include "{api_header}"\n'
        f"\n#if !defined({build_flag}) || {build_flag} != 1\n"
        f'#error "this translation unit requires {build_flag}=1"\n'
        f"#endif\n",
    )
    enum_anchor = "  UploadedFrame,\n"
    if text.count(enum_anchor) != 1:
        raise RuntimeError("R2G main enum anchor drifted")
    text = text.replace(enum_anchor, enum_anchor + enum_members)
    if remove_frame_ingress:
        ingress = (
            '  server.on("/api/frame", HTTP_POST,\n'
            "            []() { finishFrameUpload(true); }, handleFrameUploadBody);\n"
            '  server.on("/api/diagnostic/frame-ingress", HTTP_POST,\n'
            "            []() { finishFrameUpload(false); }, handleFrameUploadBody);\n"
        )
        if text.count(ingress) != 1:
            raise RuntimeError("R2G main frame-ingress anchor drifted")
        text = text.replace(ingress, endpoints)
    else:
        ingress_anchor = (
            '  server.on("/api/diagnostic/frame-ingress", HTTP_POST,\n'
            "            []() { finishFrameUpload(false); }, handleFrameUploadBody);\n"
        )
        if text.count(ingress_anchor) != 1:
            raise RuntimeError("R2G main frame-ingress anchor drifted")
        text = text.replace(ingress_anchor, ingress_anchor + endpoints)
    switch_anchor = (
        "      case PendingEpdAction::UploadedFrame:\n"
        "        result = epdDisplayFrame(frameBuffer, EPD_FRAME_BYTES);\n"
        "        resultKnown = true;\n"
        "        break;\n"
    )
    if text.count(switch_anchor) != 1:
        raise RuntimeError("R2G main switch anchor drifted")
    text = text.replace(switch_anchor, switch_anchor + switch_cases)
    return text


_V3_FIXTURE = """
// ===========================================================================
// Route A V3 fixture (handoff amendment 2 + anomaly-2 protocols 1+2): one
// screening session switches per action between the factory-OTP path, the
// pinned legacy-active runtime tuple (maximal charge reset), and the
// wf_wmask_1E tuple.  NORMALIZE runs a compile-time-fixed step sequence and
// reports each step's PON/DRF/POF timing; probes and the atlas action are
// full-frame 1E refreshes over pinned frames.  Every identity is validated
// before any panel I/O; no caller-controlled frame, coordinate, code, LUT,
// voltage, timing, retry, or recovery parameter is accepted.
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD)

namespace {

constexpr const char *PBV3_FAILURE_ALLOCATION = "allocation";
constexpr const char *PBV3_FAILURE_ROLE = "role";
constexpr const char *PBV3_FAILURE_TUPLE_IDENTITY = "tuple_identity";
constexpr const char *PBV3_FAILURE_FRAME_IDENTITY = "frame_identity";
constexpr const char *PBV3_FAILURE_CASCADE_PREPARE = "cascade_prepare";
constexpr const char *PBV3_FAILURE_TUPLE_LOAD = "tuple_load";
constexpr const char *PBV3_FAILURE_STREAM_IDENTITY = "stream_identity";
constexpr const char *PBV3_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";
constexpr const char *PBV3_FAILURE_NORMALIZE_STEP = "normalize_step";

EpdPartialAtlasV3StepReport pbv3StepReports[8];
size_t pbv3StepReportCount = 0;

bool pbv3DigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool pbv3PayloadShaMatches(const uint8_t *payload, size_t length,
                           const char *expected, int32_t *errorCode) {
  if (!payload || length == 0 || !errorCode) return false;
  uint8_t digest[32] = {};
  *errorCode = mbedtls_sha256_ret(payload, length, digest, 0);
  return *errorCode == 0 && pbv3DigestMatchesHex(digest, expected);
}

bool pbv3ValidateTuples(int32_t *errorCode) {
  return pbv3PayloadShaMatches(l535_lut::active::kR20Payload, 535,
                               pbv3::kActiveR20Sha256, errorCode) &&
         pbv3PayloadShaMatches(pb_profile_1e::kR20Payload, 535,
                               pbv3::kProfile1ER20Sha256, errorCode) &&
         pbv3PayloadShaMatches(l535_lut::active::kPowerPayload, 6,
                               pbv3::kActivePwrSha256, errorCode) &&
         pbv3PayloadShaMatches(pb_profile_1e::kPowerPayload, 6,
                               pbv3::kActivePwrSha256, errorCode) &&
         pbv3PayloadShaMatches(l535_lut::active::kPllPayload, 1,
                               pbv3::kActivePllSha256, errorCode) &&
         pbv3PayloadShaMatches(pb_profile_1e::kPllPayload, 1,
                               pbv3::kActivePllSha256, errorCode) &&
         pbv3PayloadShaMatches(l535_lut::active::kR21Payload, 704,
                               pbv3::kActiveR21Sha256, errorCode);
}

bool pbv3UniformFrameIdentity(uint8_t code, uint32_t expectedFnv,
                              const char *expectedSha, int32_t *errorCode) {
  // Identity proof for a uniform full frame without materializing it:
  // stream fixed blocks through one sha256/fnv1a accumulation.
  if (!errorCode) return false;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  uint8_t block[256];
  std::memset(block, pair, sizeof(block));
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  uint32_t remaining = EPD_FRAME_BYTES;
  while (result == 0 && remaining > 0) {
    const size_t chunk = remaining < sizeof(block) ? remaining : sizeof(block);
    result = mbedtls_sha256_update_ret(&context, block, chunk);
    for (size_t index = 0; index < chunk; ++index) hash = fnv1aUpdate(hash, pair);
    remaining -= chunk;
  }
  uint8_t digest[32] = {};
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  return result == 0 && hash == expectedFnv &&
         pbv3DigestMatchesHex(digest, expectedSha);
}

bool pbv3LoadRuntimeTuple(const uint8_t *r20) {
  // Byte-identical command sequence to the sealed epdLoadL535RuntimeLut, with
  // the R20 payload selected per action.  PWR/PLL/R21 are the pinned active
  // payloads shared by every WMASK profile.
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  epdWriteL535Payload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  epdWriteL535Payload(0x01, l535_lut::active::kPowerPayload, 6);
  if (!epdWaitIdle("V3 PWR")) return false;
  epdWriteL535Payload(0x30, l535_lut::active::kPllPayload, 1);
  epdWriteL535Payload(0x61, kControllerTres, sizeof(kControllerTres));
  for (const bool second : {false, true}) {
    setActiveControllers(!second, second);
    static constexpr uint8_t kHiddenEnable[1] = {0x01};
    epdWriteL535Payload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
    if (!epdWaitIdle(second ? "V3 CS2 E9" : "V3 CS1 E9")) return false;
    epdWriteL535Payload(0x20, r20, 535);
    epdWriteL535Payload(0x21, l535_lut::active::kR21Payload, 704);
  }
  setActiveControllers(true, true);
  return true;
}

uint32_t pbv3StreamUniformControllerDtm(bool secondController, uint8_t code,
                                        uint32_t hash) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(EPD_CONTROLLER_FRAME_BYTES, pair);
  for (uint32_t index = 0; index < EPD_CONTROLLER_FRAME_BYTES; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

bool pbv3RefreshFullFrame() {
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
}

bool pbv3OtpWhiteStep() {
  // Byte-identical to the sealed factory-OTP white fixture path: cascade init
  // (PSR 5F,69 selects the OTP LUT), full 0x11 frame to both controllers, then
  // the sealed refresh.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  const uint32_t cs1Fnv = pbv3StreamUniformControllerDtm(false, 0x01, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv3StreamUniformControllerDtm(true, 0x01, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != pbv3::kWhiteStreamFnv1a || cs2Fnv != pbv3::kWhiteStreamFnv1a) {
    return false;
  }
  return pbv3RefreshFullFrame();
}

bool pbv3ActiveUniformStep(uint8_t code) {
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  if (!pbv3LoadRuntimeTuple(l535_lut::active::kR20Payload)) return false;
  const uint32_t expected =
      code == 0x00 ? pbv3::kBlackStreamFnv1a : pbv3::kWhiteStreamFnv1a;
  const uint32_t cs1Fnv = pbv3StreamUniformControllerDtm(false, code, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv3StreamUniformControllerDtm(true, code, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != expected || cs2Fnv != expected) return false;
  return pbv3RefreshFullFrame();
}

bool pbv3RunNormalize() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  pbv3StepReportCount = 0;
  for (size_t index = 0; index < pbv3::kNormalizeStepCount; ++index) {
    pbv3StepReports[index] = EpdPartialAtlasV3StepReport{};
  }
  int32_t identityError = 0;
  if (!pbv3ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  for (size_t step = 0; step < pbv3::kNormalizeStepCount; ++step) {
    const pbv3::V3NormalizeStep &current = pbv3::kNormalizeSteps[step];
    const uint32_t stepStarted = millis();
    const bool ok = current.kind == pbv3::pbv3_step_kind::FACTORY_OTP_WHITE
                        ? pbv3OtpWhiteStep()
                        : pbv3ActiveUniformStep(current.code);
    pbv3StepReports[step].ponMs = diagnosticReport.ponWaitMs;
    pbv3StepReports[step].drfMs = diagnosticReport.drfWaitMs;
    pbv3StepReports[step].pofMs = diagnosticReport.pofWaitMs;
    pbv3StepReports[step].totalMs = millis() - stepStarted;
    pbv3StepReports[step].ok = ok;
    pbv3StepReportCount = step + 1;
    if (!ok) {
      epdRecordFailure(PBV3_FAILURE_NORMALIZE_STEP,
                       static_cast<int32_t>(step) + 1);
      return epdFinishOperation(started, false);
    }
  }
  return epdFinishOperation(started, true);
}

bool pbv3RunProbe(uint8_t code, uint32_t expectedStreamFnv,
                  uint32_t expectedFrameFnv, const char *expectedFrameSha) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  int32_t identityError = 0;
  if (!pbv3ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  if (!pbv3UniformFrameIdentity(code, expectedFrameFnv, expectedFrameSha,
                                &identityError)) {
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_FRAME_IDENTITY,
                                  identityError);
  }
  // With the uniform frame proven, the per-controller DTM fnv1a pins the full
  // stream identity as well.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_CASCADE_PREPARE);
  }
  if (!pbv3LoadRuntimeTuple(pb_profile_1e::kR20Payload)) {
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_TUPLE_LOAD);
  }
  const uint32_t cs1Fnv = pbv3StreamUniformControllerDtm(false, code, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv3StreamUniformControllerDtm(true, code, FNV1A_OFFSET_BASIS);
  diagnosticReport.inputFrameFnv1a = expectedFrameFnv;
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != expectedStreamFnv || cs2Fnv != expectedStreamFnv) {
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_STREAM_IDENTITY);
  }
  const bool ok = pbv3RefreshFullFrame();
  if (!ok) epdRecordFailure(PBV3_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

bool pbv3RunAtlasV2() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  int32_t identityError = 0;
  if (!pbv3ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_ALLOCATION);
  }
  const uint8_t backgroundPair = static_cast<uint8_t>(
      (pb_atlas_v2::kBackgroundCode << 4) | pb_atlas_v2::kBackgroundCode);
  std::memset(frame, backgroundPair, EPD_FRAME_BYTES);
  for (size_t index = 0; index < pb_atlas_v2::kRoiCount; ++index) {
    const pb_atlas_v2::AtlasRoi &roi = pb_atlas_v2::kRois[index];
    const uint8_t pair = static_cast<uint8_t>((roi.code << 4) | roi.code);
    for (uint16_t y = roi.y; y < roi.y + roi.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * (EPD_WIDTH / 2) + roi.x / 2,
                  pair, roi.width / 2);
    }
  }
  const uint32_t frameFnv = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  const int shaResult = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  diagnosticReport.inputFrameFnv1a = frameFnv;
  if (shaResult != 0 || frameFnv != pbv3::kAtlasV2FrameFnv1a ||
      !pbv3DigestMatchesHex(digest, pbv3::kAtlasV2FrameSha256)) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PBV3_FAILURE_FRAME_IDENTITY,
                                  shaResult);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_CASCADE_PREPARE);
  }
  if (!pbv3LoadRuntimeTuple(pb_profile_1e::kR20Payload)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_TUPLE_LOAD);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);
  if (diagnosticReport.cs1DtmFnv1a != pbv3::kAtlasV2Cs1StreamFnv1a ||
      diagnosticReport.cs2DtmFnv1a != pbv3::kAtlasV2Cs2StreamFnv1a) {
    return epdFinishFailedOperationSafe(started, PBV3_FAILURE_STREAM_IDENTITY);
  }
  const bool ok = pbv3RefreshFullFrame();
  if (!ok) epdRecordFailure(PBV3_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

}  // namespace

bool epdValidateCompiledPartialAtlasV3Fixtures() {
  int32_t errorCode = 0;
  return pbv3ValidateTuples(&errorCode) &&
         epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
}

bool epdDisplayCompiledPartialAtlasV3(EpdPartialAtlasV3Role role) {
  switch (role) {
    case EpdPartialAtlasV3Role::Normalize:
      return pbv3RunNormalize();
    case EpdPartialAtlasV3Role::ProbeCode7:
      return pbv3RunProbe(0x07, pbv3::kProbe7StreamFnv1a,
                          pbv3::kProbe7FrameFnv1a, pbv3::kProbe7FrameSha256);
    case EpdPartialAtlasV3Role::ProbeCode1:
      return pbv3RunProbe(0x01, pbv3::kWhiteStreamFnv1a,
                          pbv3::kWhiteFrameFnv1a, pbv3::kWhiteFrameSha256);
    case EpdPartialAtlasV3Role::AtlasV2:
      return pbv3RunAtlasV2();
    case EpdPartialAtlasV3Role::WhiteRecovery:
      return epdDisplayCompiledFactoryOtpWhiteRecovery();
  }
  return false;
}

const EpdPartialAtlasV3StepReport *epdGetPartialAtlasV3StepReports(
    std::size_t *count) {
  if (count) *count = pbv3StepReportCount;
  return pbv3StepReports;
}

#endif  // MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD
"""


def render_v3() -> dict[str, str]:
    """Return {relative_path: content} for the V3 generated sources."""

    v3_driver = (
        _render_v3_driver_head() + _r2g_tail() + _V3_FIXTURE
    )
    main_template = R2G_MAIN_PATH.read_text(encoding="utf-8")
    v3_main = _render_main(
        main_template,
        ATLAS_TAG_V3,
        "partial block route A V3: normalize + probes + atlas V2",
        "partial_atlas_1e_v3_api.h",
        "MF1750_PARTIAL_BLOCK_ATLAS_1E_V3_BUILD",
        "  PartialAtlasV3Normalize,\n"
        "  PartialAtlasV3ProbeCode7,\n"
        "  PartialAtlasV3ProbeCode1,\n"
        "  PartialAtlasV3AtlasV2,\n"
        "  PartialAtlasV3WhiteRecovery,\n",
        '  server.on("/api/partial-atlas-v3/normalize", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV3Normalize,\n'
        '                          "partial_atlas_v3_normalize");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v3/probe-code7", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV3ProbeCode7,\n'
        '                          "partial_atlas_v3_probe_code7");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v3/probe-code1", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV3ProbeCode1,\n'
        '                          "partial_atlas_v3_probe_code1");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v3/atlas-v2", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV3AtlasV2,\n'
        '                          "partial_atlas_v3_atlas_v2");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v3/white-recovery", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV3WhiteRecovery,\n'
        '                          "partial_atlas_v3_white_recovery");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v3/steps", HTTP_GET, []() {\n'
        "    size_t count = 0;\n"
        "    const EpdPartialAtlasV3StepReport *steps =\n"
        "        epdGetPartialAtlasV3StepReports(&count);\n"
        '    String json = "{\\"schema_version\\":1,\\"kind\\":\\"partial-atlas-v3-normalize-steps\\",\\"steps\\":[";\n'
        "    for (size_t index = 0; index < count; ++index) {\n"
        '      if (index) json += ",";\n'
        '      json += String("{\\"ordinal\\":") + String(index + 1) +\n'
        '              ",\\"pon_ms\\":" + String(steps[index].ponMs) +\n'
        '              ",\\"drf_ms\\":" + String(steps[index].drfMs) +\n'
        '              ",\\"pof_ms\\":" + String(steps[index].pofMs) +\n'
        '              ",\\"total_ms\\":" + String(steps[index].totalMs) +\n'
        '              ",\\"ok\\":" + (steps[index].ok ? "true" : "false") + "}";\n'
        "    }\n"
        '    json += "]}";\n'
        '    server.send(200, "application/json", json);\n'
        "  });\n",
        "      case PendingEpdAction::PartialAtlasV3Normalize:\n"
        "        result = epdDisplayCompiledPartialAtlasV3(\n"
        "            EpdPartialAtlasV3Role::Normalize);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV3ProbeCode7:\n"
        "        result = epdDisplayCompiledPartialAtlasV3(\n"
        "            EpdPartialAtlasV3Role::ProbeCode7);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV3ProbeCode1:\n"
        "        result = epdDisplayCompiledPartialAtlasV3(\n"
        "            EpdPartialAtlasV3Role::ProbeCode1);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV3AtlasV2:\n"
        "        result = epdDisplayCompiledPartialAtlasV3(\n"
        "            EpdPartialAtlasV3Role::AtlasV2);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV3WhiteRecovery:\n"
        "        result = epdDisplayCompiledPartialAtlasV3(\n"
        "            EpdPartialAtlasV3Role::WhiteRecovery);\n"
        "        resultKnown = true;\n"
        "        break;\n",
        remove_frame_ingress=True,
    )
    return {
        V3_PATHS["contract_inc"]: _render_v3_contract_inc(),
        V3_PATHS["api_header"]: _render_v3_api_header(),
        V3_PATHS["driver"]: v3_driver,
        V3_PATHS["main"]: v3_main,
    }


# ---------------------------------------------------------------------------
# Route A V4: compact atlas layout for the current camera window (content
# x in [0,545], top edge clipped near x~380; safe rectangle x in [16,520],
# y in [170,580]).  All eight cells move into the visible window on CS1's
# half; the two probe actions are dropped (saves two refreshes).  The 8-step
# normalize sequence is byte-identical to V3.
# ---------------------------------------------------------------------------

ATLAS_ENV_V4 = "esp32-s3-devkitc-1-partial-atlas-1e-v4"
ATLAS_TAG_V4 = f"MF1750_PARTIAL_BLOCK_ATLAS_1E_{DATE}_V4"
V4_PATHS = {
    "contract_inc": "src/generated/partial_atlas_1e_v4_contract.inc",
    "api_header": "src/partial_atlas_1e_v4_api.h",
    "driver": "src/partial_atlas_1e_v4_epd_driver.cpp",
    "main": "src/partial_atlas_1e_v4_main.cpp",
}
V4_CELL = 110
V4_SLOTS: tuple[tuple[int, int], ...] = (
    (20, 190), (140, 190), (260, 190), (380, 190),
    (20, 330), (140, 330), (260, 330), (380, 330),
)
V4_CODES: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 7, 6)
V4_SAFE_RECT = {"x": 16, "y": 170, "w": 504, "h": 410}  # x in [16,520], y in [170,580]


def v4_regions() -> list[dict[str, Any]]:
    return [
        {"name": f"code{code}", "code": code, "x": x, "y": y,
         "w": V4_CELL, "h": V4_CELL}
        for (x, y), code in zip(V4_SLOTS, V4_CODES)
    ]


def _validate_v4_layout() -> None:
    regions = v4_regions()
    if [roi["code"] for roi in regions] != list(V4_CODES):
        raise RuntimeError("V4 cell code order drifted")
    if len({roi["code"] for roi in regions}) != 8:
        raise RuntimeError("V4 cell codes are not unique")
    rect = V4_SAFE_RECT
    for roi in regions:
        if roi["x"] % 2 or roi["w"] % 2:
            raise RuntimeError(f"V4 cell {roi['name']} is not byte aligned")
        if roi["x"] + roi["w"] > CONTROLLER_WIDTH:
            raise RuntimeError(f"V4 cell {roi['name']} crosses the x=512 seam")
        if not (rect["x"] <= roi["x"]
                and roi["x"] + roi["w"] <= rect["x"] + rect["w"]
                and rect["y"] <= roi["y"]
                and roi["y"] + roi["h"] <= rect["y"] + rect["h"]):
            raise RuntimeError(f"V4 cell {roi['name']} escapes the visible safe rect")
        if roi["y"] + roi["h"] > HEIGHT:
            raise RuntimeError(f"V4 cell {roi['name']} escapes the panel")
    for index, left in enumerate(regions):
        for right in regions[index + 1:]:
            overlap = not (
                left["x"] + left["w"] <= right["x"]
                or right["x"] + right["w"] <= left["x"]
                or left["y"] + left["h"] <= right["y"]
                or right["y"] + right["h"] <= left["y"]
            )
            if overlap:
                raise RuntimeError("V4 cells overlap")


def build_v4_frame() -> bytes:
    """Return the compact packed-4bpp route A V4 frame (even x high nibble)."""

    _validate_v4_layout()
    frame = bytearray(
        [(ATLAS_BACKGROUND_CODE << 4) | ATLAS_BACKGROUND_CODE] * FRAME_BYTES
    )
    for roi in v4_regions():
        pair = (roi["code"] << 4) | roi["code"]
        for y in range(roi["y"], roi["y"] + roi["h"]):
            start = y * ROW_BYTES + roi["x"] // 2
            frame[start:start + roi["w"] // 2] = bytes([pair]) * (roi["w"] // 2)
    return bytes(frame)


def v4_layout_doc() -> dict[str, Any]:
    return {
        "schema": "mf1750-partial-block-atlas-layout-v1",
        "layout_revision": "V4",
        "panel": {"width": WIDTH, "height": HEIGHT,
                  "controller_width": CONTROLLER_WIDTH},
        "background_code": ATLAS_BACKGROUND_CODE,
        "background_is_l535_white_code7": True,
        "rois": v4_regions(),
        "background_reference": None,
        "packed_format": "4bpp row-major, even x in the high nibble",
        "even_x_and_width": True,
        "seam_avoidance_x512": True,
        "all_cells_on_cs1_left_half": True,
        "visible_safe_rect": dict(V4_SAFE_RECT),
        "codes_are_transport_codes_not_colour_names": True,
    }


def v4_roi_list_doc() -> dict[str, Any]:
    """tools/mf1750_multi_roi_lab.py-compatible region list for the V4 layout."""

    return {
        "schema": "mf1750-partial-block-atlas-roi-list-v1",
        "layout_revision": "V3",
        "screen": {"width": WIDTH, "height": HEIGHT},
        "regions": v4_regions(),
    }


def v4_identities() -> dict[str, Any]:
    frame = build_v4_frame()
    return {
        "frame": {
            "bytes": len(frame),
            "fnv1a": _fnv1a(frame),
            "sha256": _sha256(frame),
        },
        "streams": {
            "cs1": _fnv1a(controller_stream(frame, False)),
            "cs2": _fnv1a(controller_stream(frame, True)),
        },
        "uniform_streams": {
            "black": _fnv1a(_uniform(CONTROLLER_DTM_BYTES, 0)),
            "white": _fnv1a(_uniform(CONTROLLER_DTM_BYTES, 1)),
        },
        "layout_sha256": _sha256(_canonical(v4_layout_doc())),
    }


def _render_v4_contract_inc() -> str:
    identities = v4_identities()
    frame = identities["frame"]
    streams = identities["streams"]
    r20_1e = _profile_reports()["1E"]["r20_sha256"]
    steps = ",\n".join(
        f"    {{pbv4_step_kind::{('FACTORY_OTP_WHITE' if s['kind'] == 'factory_otp_white' else 'ACTIVE_UNIFORM')}, 0x{s['code']:02X}}}"
        for s in V3_NORMALIZE_SEQUENCE
    )
    rois = ",\n".join(
        f"    {{{roi['x']}, {roi['y']}, {roi['w']}, {roi['h']}, 0x{roi['code']:02X}}}"
        for roi in v4_regions()
    )
    asserts = []
    for index, roi in enumerate(v4_regions()):
        asserts.append(
            f"static_assert(kRois[{index}].x == {roi['x']} && "
            f"kRois[{index}].y == {roi['y']} && "
            f"kRois[{index}].width == {roi['w']} && "
            f"kRois[{index}].height == {roi['h']} && "
            f"kRois[{index}].code == 0x{roi['code']:02X},\n"
            f"              \"route A V4 cell {index} identity drifted\");"
        )
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

// Generated by tools/mf1750_partial_block_build.py.  Route A V4 contract:
// compact atlas layout for the current camera window (safe rectangle
// x in [16,520], y in [170,580]; every cell inside CS1's left half).  The
// 8-step NORMALIZE sequence is byte-identical to V3: 2x factory-OTP white,
// then 3x (active-table code0 black, active-table code1 white) alternating
// reset pairs, ending on white.  Every frame, tuple, and the step sequence is
// compile-time pinned; no runtime frame, coordinate, or LUT input exists.
// Codes are transport codes, not colour names.

namespace mf1750::partial_block::atlas_v4 {{

enum class pbv4_step_kind : std::uint8_t {{
  FACTORY_OTP_WHITE = 0,
  ACTIVE_UNIFORM = 1,
}};
struct V4NormalizeStep {{
  pbv4_step_kind kind;
  std::uint8_t code;
}};
static constexpr V4NormalizeStep kNormalizeSteps[] = {{
{steps},
}};
static constexpr std::size_t kNormalizeStepCount = {len(V3_NORMALIZE_SEQUENCE)};

struct AtlasRoi {{
  std::uint16_t x;
  std::uint16_t y;
  std::uint16_t width;
  std::uint16_t height;
  std::uint8_t code;
}};
static constexpr std::uint8_t kBackgroundCode = 0x{ATLAS_BACKGROUND_CODE:02X};
static constexpr std::size_t kRoiCount = {len(v4_regions())};
static constexpr AtlasRoi kRois[kRoiCount] = {{
{rois},
}};

static constexpr char kActiveR20Sha256[] = "{V3_ACTIVE_R20_SHA256}";
static constexpr char kProfile1ER20Sha256[] = "{r20_1e}";
static constexpr char kActivePwrSha256[] = "{wmask.PWR_SHA256}";
static constexpr char kActivePllSha256[] = "{wmask.PLL_SHA256}";
static constexpr char kActiveR21Sha256[] = "{wmask.R21_SHA256}";

static constexpr char kAtlasFrameSha256[] = "{frame['sha256']}";
static constexpr std::uint32_t kAtlasFrameFnv1a = 0x{frame['fnv1a']:08X}UL;
static constexpr std::uint32_t kAtlasCs1StreamFnv1a = 0x{streams['cs1']:08X}UL;
static constexpr std::uint32_t kAtlasCs2StreamFnv1a = 0x{streams['cs2']:08X}UL;
static constexpr std::uint32_t kBlackStreamFnv1a = 0x{identities['uniform_streams']['black']:08X}UL;
static constexpr std::uint32_t kWhiteStreamFnv1a = 0x{identities['uniform_streams']['white']:08X}UL;
static constexpr char kLayoutSha256[] = "{identities['layout_sha256']}";

{chr(10).join(asserts)}
static_assert(kNormalizeStepCount == 8 &&
                  kNormalizeSteps[0].kind == pbv4_step_kind::FACTORY_OTP_WHITE &&
                  kNormalizeSteps[1].kind == pbv4_step_kind::FACTORY_OTP_WHITE &&
                  kNormalizeSteps[2].code == 0x00 &&
                  kNormalizeSteps[3].code == 0x01 &&
                  kNormalizeSteps[4].code == 0x00 &&
                  kNormalizeSteps[5].code == 0x01 &&
                  kNormalizeSteps[6].code == 0x00 &&
                  kNormalizeSteps[7].code == 0x01 &&
                  kNormalizeSteps[7].kind == pbv4_step_kind::ACTIVE_UNIFORM,
              "V4 NORMALIZE sequence drifted from the V3 8-step sequence");

}}  // namespace mf1750::partial_block::atlas_v4
"""


def _render_v4_api_header() -> str:
    return """#pragma once

#include <cstddef>
#include <cstdint>

// Partial-block route A V4 (compact atlas in the visible camera window):
// every action is a fixed compiled identity validated before any panel I/O.
// This API accepts no frame, coordinate, colour code, LUT, voltage, timing,
// SPI-frequency, retry, or recovery parameter.  Actions are never chained
// automatically; each runs only on its own explicit endpoint.
enum class EpdPartialAtlasV4Role : std::uint8_t {
  Normalize = 0,
  Atlas = 1,
  WhiteRecovery = 2,
};

struct EpdPartialAtlasV4StepReport {
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledPartialAtlasV4Fixtures();
bool epdDisplayCompiledPartialAtlasV4(EpdPartialAtlasV4Role role);
const EpdPartialAtlasV4StepReport *epdGetPartialAtlasV4StepReports(
    std::size_t *count);
"""


def _render_v4_driver_head() -> str:
    records = wmask.selected_records(0x0E, True)
    return (
        """// Dedicated translation unit for partial-block route A V4: the compact
// atlas layout collects all eight transport-code cells into the current
// camera's visible window (safe rectangle x in [16,520], y in [170,580], all
// on CS1's left half).  The two probe actions are dropped; NORMALIZE and
// WHITE_RECOVERY are byte-identical to the sealed V3 paths.  Per-action the
// driver switches between the factory-OTP path, the pinned legacy-active
// runtime tuple (maximal charge reset), and the wf_wmask_1E GrayExt tuple
// (base 0x0E plus the whole records 0-3 group; the family label is not a
// bitmask).  Every tuple's R20/PWR/PLL/R21/PSR bytes are the same compiled
// objects as their sealed sources; the runtime tail below is byte-identical
// to the pinned R2G template.  Production, the wf_wmask_*, and the V1/V2/V3
// translation units stay untouched.
#include "epd_driver.h"

#include <SPI.h>
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD)
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"
#include "partial_atlas_1e_v4_api.h"

#if !defined(MF1750_L535_FRAME_PATH_BUILD) || MF1750_L535_FRAME_PATH_BUILD != 1
#error "route A V4 requires the frozen L535 frame path build"
#endif
#if !defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD) || \\
    MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD != 1
#error "route A V4 requires MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD=1"
#endif
#if !defined(MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY) || \\
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1
#error "route A V4 requires the factory-OTP fixture for its white steps"
#endif
#if !defined(MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1 || \\
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 0
#error "route A V4 binds the WF23_25 factory-OTP white profile exactly"
#endif

#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_wf_wmask_1E.inc"
namespace pb_profile_1e = mf1750::runtime_lut::wf_wmask_1E;
// The inherited full-frame path (unused by every V4 action) binds the 1E
// tuple so the byte-identical runtime tail compiles unchanged.
namespace l535_variant = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/partial_atlas_1e_v4_contract.inc"
namespace pbv4 = mf1750::partial_block::atlas_v4;

"""
        + _cpp_spans_predicate("pbv4Profile1EUseCommented", records)
        + "\n"
        + _cpp_records_proof("Pbv4Profile1ERecordsMatch", "pbv4Profile1EUseCommented",
                             "pb_profile_1e", "route A V4 1E")
        + "\n"
        + _cpp_pwr_pll_asserts("pb_profile_1e", "route A V4 1E")
        + "\n"
        + _cpp_r21_proof("Pbv4ActiveR21Unchanged", "route A V4")
        + "\n"
    )


_V4_FIXTURE = """
// ===========================================================================
// Route A V4 fixture: the V3 normalization + white-recovery paths plus the
// compact atlas action.  The two V3 probe actions are dropped (saves two
// refreshes).  Every identity is validated before any panel I/O; no
// caller-controlled frame, coordinate, code, LUT, voltage, timing, retry, or
// recovery parameter is accepted.
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD)

namespace {

constexpr const char *PBV4_FAILURE_ALLOCATION = "allocation";
constexpr const char *PBV4_FAILURE_ROLE = "role";
constexpr const char *PBV4_FAILURE_TUPLE_IDENTITY = "tuple_identity";
constexpr const char *PBV4_FAILURE_FRAME_IDENTITY = "frame_identity";
constexpr const char *PBV4_FAILURE_CASCADE_PREPARE = "cascade_prepare";
constexpr const char *PBV4_FAILURE_TUPLE_LOAD = "tuple_load";
constexpr const char *PBV4_FAILURE_STREAM_IDENTITY = "stream_identity";
constexpr const char *PBV4_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";
constexpr const char *PBV4_FAILURE_NORMALIZE_STEP = "normalize_step";

EpdPartialAtlasV4StepReport pbv4StepReports[8];
size_t pbv4StepReportCount = 0;

bool pbv4DigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool pbv4PayloadShaMatches(const uint8_t *payload, size_t length,
                           const char *expected, int32_t *errorCode) {
  if (!payload || length == 0 || !errorCode) return false;
  uint8_t digest[32] = {};
  *errorCode = mbedtls_sha256_ret(payload, length, digest, 0);
  return *errorCode == 0 && pbv4DigestMatchesHex(digest, expected);
}

bool pbv4ValidateTuples(int32_t *errorCode) {
  return pbv4PayloadShaMatches(l535_lut::active::kR20Payload, 535,
                               pbv4::kActiveR20Sha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kR20Payload, 535,
                               pbv4::kProfile1ER20Sha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kPowerPayload, 6,
                               pbv4::kActivePwrSha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kPowerPayload, 6,
                               pbv4::kActivePwrSha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kPllPayload, 1,
                               pbv4::kActivePllSha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kPllPayload, 1,
                               pbv4::kActivePllSha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kR21Payload, 704,
                               pbv4::kActiveR21Sha256, errorCode);
}

bool pbv4LoadRuntimeTuple(const uint8_t *r20) {
  // Byte-identical command sequence to the sealed epdLoadL535RuntimeLut, with
  // the R20 payload selected per action.  PWR/PLL/R21 are the pinned active
  // payloads shared by every WMASK profile.
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  epdWriteL535Payload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  epdWriteL535Payload(0x01, l535_lut::active::kPowerPayload, 6);
  if (!epdWaitIdle("V4 PWR")) return false;
  epdWriteL535Payload(0x30, l535_lut::active::kPllPayload, 1);
  epdWriteL535Payload(0x61, kControllerTres, sizeof(kControllerTres));
  for (const bool second : {false, true}) {
    setActiveControllers(!second, second);
    static constexpr uint8_t kHiddenEnable[1] = {0x01};
    epdWriteL535Payload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
    if (!epdWaitIdle(second ? "V4 CS2 E9" : "V4 CS1 E9")) return false;
    epdWriteL535Payload(0x20, r20, 535);
    epdWriteL535Payload(0x21, l535_lut::active::kR21Payload, 704);
  }
  setActiveControllers(true, true);
  return true;
}

uint32_t pbv4StreamUniformControllerDtm(bool secondController, uint8_t code,
                                        uint32_t hash) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(EPD_CONTROLLER_FRAME_BYTES, pair);
  for (uint32_t index = 0; index < EPD_CONTROLLER_FRAME_BYTES; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

bool pbv4RefreshFullFrame() {
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
}

bool pbv4OtpWhiteStep() {
  // Byte-identical to the sealed factory-OTP white fixture path: cascade init
  // (PSR 5F,69 selects the OTP LUT), full 0x11 frame to both controllers, then
  // the sealed refresh.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  const uint32_t cs1Fnv = pbv4StreamUniformControllerDtm(false, 0x01, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv4StreamUniformControllerDtm(true, 0x01, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != pbv4::kWhiteStreamFnv1a || cs2Fnv != pbv4::kWhiteStreamFnv1a) {
    return false;
  }
  return pbv4RefreshFullFrame();
}

bool pbv4ActiveUniformStep(uint8_t code) {
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  if (!pbv4LoadRuntimeTuple(l535_lut::active::kR20Payload)) return false;
  const uint32_t expected =
      code == 0x00 ? pbv4::kBlackStreamFnv1a : pbv4::kWhiteStreamFnv1a;
  const uint32_t cs1Fnv = pbv4StreamUniformControllerDtm(false, code, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv4StreamUniformControllerDtm(true, code, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != expected || cs2Fnv != expected) return false;
  return pbv4RefreshFullFrame();
}

bool pbv4RunNormalize() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  pbv4StepReportCount = 0;
  for (size_t index = 0; index < pbv4::kNormalizeStepCount; ++index) {
    pbv4StepReports[index] = EpdPartialAtlasV4StepReport{};
  }
  int32_t identityError = 0;
  if (!pbv4ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  for (size_t step = 0; step < pbv4::kNormalizeStepCount; ++step) {
    const pbv4::V4NormalizeStep &current = pbv4::kNormalizeSteps[step];
    const uint32_t stepStarted = millis();
    const bool ok = current.kind == pbv4::pbv4_step_kind::FACTORY_OTP_WHITE
                        ? pbv4OtpWhiteStep()
                        : pbv4ActiveUniformStep(current.code);
    pbv4StepReports[step].ponMs = diagnosticReport.ponWaitMs;
    pbv4StepReports[step].drfMs = diagnosticReport.drfWaitMs;
    pbv4StepReports[step].pofMs = diagnosticReport.pofWaitMs;
    pbv4StepReports[step].totalMs = millis() - stepStarted;
    pbv4StepReports[step].ok = ok;
    pbv4StepReportCount = step + 1;
    if (!ok) {
      epdRecordFailure(PBV4_FAILURE_NORMALIZE_STEP,
                       static_cast<int32_t>(step) + 1);
      return epdFinishOperation(started, false);
    }
  }
  return epdFinishOperation(started, true);
}

bool pbv4RunAtlas() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  int32_t identityError = 0;
  if (!pbv4ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_ALLOCATION);
  }
  const uint8_t backgroundPair = static_cast<uint8_t>(
      (pbv4::kBackgroundCode << 4) | pbv4::kBackgroundCode);
  std::memset(frame, backgroundPair, EPD_FRAME_BYTES);
  for (size_t index = 0; index < pbv4::kRoiCount; ++index) {
    const pbv4::AtlasRoi &roi = pbv4::kRois[index];
    const uint8_t pair = static_cast<uint8_t>((roi.code << 4) | roi.code);
    for (uint16_t y = roi.y; y < roi.y + roi.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * (EPD_WIDTH / 2) + roi.x / 2,
                  pair, roi.width / 2);
    }
  }
  const uint32_t frameFnv = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  const int shaResult = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  diagnosticReport.inputFrameFnv1a = frameFnv;
  if (shaResult != 0 || frameFnv != pbv4::kAtlasFrameFnv1a ||
      !pbv4DigestMatchesHex(digest, pbv4::kAtlasFrameSha256)) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_FRAME_IDENTITY,
                                  shaResult);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_CASCADE_PREPARE);
  }
  if (!pbv4LoadRuntimeTuple(pb_profile_1e::kR20Payload)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_TUPLE_LOAD);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);
  if (diagnosticReport.cs1DtmFnv1a != pbv4::kAtlasCs1StreamFnv1a ||
      diagnosticReport.cs2DtmFnv1a != pbv4::kAtlasCs2StreamFnv1a) {
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_STREAM_IDENTITY);
  }
  const bool ok = pbv4RefreshFullFrame();
  if (!ok) epdRecordFailure(PBV4_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

}  // namespace

bool epdValidateCompiledPartialAtlasV4Fixtures() {
  int32_t errorCode = 0;
  return pbv4ValidateTuples(&errorCode) &&
         epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
}

bool epdDisplayCompiledPartialAtlasV4(EpdPartialAtlasV4Role role) {
  switch (role) {
    case EpdPartialAtlasV4Role::Normalize:
      return pbv4RunNormalize();
    case EpdPartialAtlasV4Role::Atlas:
      return pbv4RunAtlas();
    case EpdPartialAtlasV4Role::WhiteRecovery:
      return epdDisplayCompiledFactoryOtpWhiteRecovery();
  }
  return false;
}

const EpdPartialAtlasV4StepReport *epdGetPartialAtlasV4StepReports(
    std::size_t *count) {
  if (count) *count = pbv4StepReportCount;
  return pbv4StepReports;
}

#endif  // MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD
"""


def render_v4() -> dict[str, str]:
    """Return {relative_path: content} for the V4 generated sources."""

    v4_driver = (
        _render_v4_driver_head() + _r2g_tail() + _V4_FIXTURE
    )
    main_template = R2G_MAIN_PATH.read_text(encoding="utf-8")
    v4_main = _render_main(
        main_template,
        ATLAS_TAG_V4,
        "partial block route A V4: compact atlas in visible window",
        "partial_atlas_1e_v4_api.h",
        "MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD",
        "  PartialAtlasV4Normalize,\n"
        "  PartialAtlasV4Atlas,\n"
        "  PartialAtlasV4WhiteRecovery,\n",
        '  server.on("/api/partial-atlas-v4/normalize", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV4Normalize,\n'
        '                          "partial_atlas_v4_normalize");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v4/atlas-v3", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV4Atlas,\n'
        '                          "partial_atlas_v4_atlas");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v4/white-recovery", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlasV4WhiteRecovery,\n'
        '                          "partial_atlas_v4_white_recovery");\n'
        "  });\n"
        '  server.on("/api/partial-atlas-v4/steps", HTTP_GET, []() {\n'
        "    size_t count = 0;\n"
        "    const EpdPartialAtlasV4StepReport *steps =\n"
        "        epdGetPartialAtlasV4StepReports(&count);\n"
        '    String json = "{\\"schema_version\\":1,\\"kind\\":\\"partial-atlas-v4-normalize-steps\\",\\"steps\\":[";\n'
        "    for (size_t index = 0; index < count; ++index) {\n"
        '      if (index) json += ",";\n'
        '      json += String("{\\"ordinal\\":") + String(index + 1) +\n'
        '              ",\\"pon_ms\\":" + String(steps[index].ponMs) +\n'
        '              ",\\"drf_ms\\":" + String(steps[index].drfMs) +\n'
        '              ",\\"pof_ms\\":" + String(steps[index].pofMs) +\n'
        '              ",\\"total_ms\\":" + String(steps[index].totalMs) +\n'
        '              ",\\"ok\\":" + (steps[index].ok ? "true" : "false") + "}";\n'
        "    }\n"
        '    json += "]}";\n'
        '    server.send(200, "application/json", json);\n'
        "  });\n",
        "      case PendingEpdAction::PartialAtlasV4Normalize:\n"
        "        result = epdDisplayCompiledPartialAtlasV4(\n"
        "            EpdPartialAtlasV4Role::Normalize);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV4Atlas:\n"
        "        result = epdDisplayCompiledPartialAtlasV4(\n"
        "            EpdPartialAtlasV4Role::Atlas);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialAtlasV4WhiteRecovery:\n"
        "        result = epdDisplayCompiledPartialAtlasV4(\n"
        "            EpdPartialAtlasV4Role::WhiteRecovery);\n"
        "        resultKnown = true;\n"
        "        break;\n",
        remove_frame_ingress=True,
    )
    return {
        V4_PATHS["contract_inc"]: _render_v4_contract_inc(),
        V4_PATHS["api_header"]: _render_v4_api_header(),
        V4_PATHS["driver"]: v4_driver,
        V4_PATHS["main"]: v4_main,
    }


def build_v4_report() -> dict[str, Any]:
    """V4 compact-atlas session report (V3 pattern minus the two probes)."""

    identities = v4_identities()
    profiles = _profile_reports()
    tail = _r2g_tail()
    rendered = render_v4()
    return {
        "schema_version": 1,
        "kind": "mf1750-partial-block-v4-session-generation",
        "date": DATE,
        "handoff": HANDOFF_DOC,
        "amendment": (
            "V4: compact 110x110 cells at xs [20,140,260,380] ys [190,330] "
            "inside the current camera window (safe rect x[16,520] "
            "y[170,580]); probes dropped; V3 8-step normalize kept"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "env": ATLAS_ENV_V4,
        "tag": ATLAS_TAG_V4,
        "spi_hz": 1_000_000,
        "spi_hz_is_frozen_default": True,
        "tuples": {
            "factory_otp": {
                "path": "sealed ec5_factory_otp_white_recovery_driver.inc "
                        "cascade path (PSR 5F,69 selects OTP LUT)",
                "runtime_lut_uploaded": False,
            },
            "active": {
                "r20_sha256": V3_ACTIVE_R20_SHA256,
                "pwr_sha256": wmask.PWR_SHA256,
                "pll_sha256": wmask.PLL_SHA256,
                "r21_sha256": wmask.R21_SHA256,
                "byte_identity": "same compiled objects as the sealed legacy "
                                 "active reference (spd1657_legacy_535_reference.inc)",
            },
            "1E": {
                "family_label": "1E",
                "family_label_is_not_bitmask": True,
                "r20_sha256": profiles["1E"]["r20_sha256"],
                "pwr_sha256": profiles["1E"]["pwr_sha256"],
                "pll_sha256": profiles["1E"]["pll_sha256"],
                "r21_sha256": profiles["1E"]["r21_sha256"],
                "byte_identity": "same compiled object as the sealed "
                                 "wf_wmask_1E build",
            },
        },
        "normalize": {
            "sequence": [dict(step) for step in V3_NORMALIZE_SEQUENCE],
            "step_count": len(V3_NORMALIZE_SEQUENCE),
            "byte_identical_to_v3": True,
            "reading": (
                "2x factory-OTP white, then 3x (code0 black, code1 white) "
                "alternating reset pairs under the active tuple, ending on "
                "white; per-step PON/DRF/POF timings published via "
                "/api/partial-atlas-v4/steps"
            ),
            "stop_on_failure": "fail-closed: a failed step aborts the sequence",
        },
        "atlas_layout": {
            "doc": v4_layout_doc(),
            "sha256": identities["layout_sha256"],
            "cell_size": [V4_CELL, V4_CELL],
            "codes_row_major": list(V4_CODES),
        },
        "frame": identities["frame"],
        "controller_stream_fnv1a": identities["streams"],
        "normalize_uniform_stream_fnv1a": identities["uniform_streams"],
        "actions": [
            {"ordinal": 1, "role": "NORMALIZE", "profile": "factory_otp+active",
             "endpoint": "/api/partial-atlas-v4/normalize"},
            {"ordinal": 2, "role": "ATLAS", "profile": "1E",
             "frame_sha256": identities["frame"]["sha256"],
             "endpoint": "/api/partial-atlas-v4/atlas-v3"},
            {"ordinal": 3, "role": "WHITE_RECOVERY", "profile": "factory_otp",
             "endpoint": "/api/partial-atlas-v4/white-recovery"},
        ],
        "runtime_tail_sha256": _sha256(tail.encode("utf-8")),
        "runtime_tail_byte_identical_to_r2g": True,
        "generated_sources": {
            path: {"bytes": len(content.encode("utf-8")),
                   "sha256": _sha256(content.encode("utf-8"))}
            for path, content in sorted(rendered.items())
        },
    }


def render_version(version: str = "V1") -> dict[str, str]:
    """Return {relative_path: content} for one version's generated sources."""

    names = _version_names(version)
    frame = build_atlas_frame(version)
    cs1 = controller_stream(frame, False)
    cs2 = controller_stream(frame, True)
    layout_doc = atlas_layout_doc(version)
    layout_sha = _sha256(_canonical(layout_doc))
    identities = route_b_identities(version)
    profiles = _profile_reports()

    atlas_driver = (
        _render_atlas_driver_head(version) + _r2g_tail() + _route_a_fixture(version)
    )
    ptlw_driver = (
        _render_ptlw_driver_head(version) + _r2g_tail() + _ROUTE_B_FIXTURE
    )
    main_template = R2G_MAIN_PATH.read_text(encoding="utf-8")
    atlas_main = _render_main(
        main_template,
        names["atlas_tag"],
        names["atlas_boot"],
        "partial_atlas_1e_api.h",
        "MF1750_PARTIAL_BLOCK_ATLAS_1E_BUILD",
        "  PartialAtlas1E,\n",
        '  server.on("/api/partial-atlas-1e", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialAtlas1E,\n'
        '                          "partial_atlas_1e_compiled");\n'
        "  });\n",
        "      case PendingEpdAction::PartialAtlas1E:\n"
        "        result = epdDisplayCompiledPartialAtlas1E();\n"
        "        resultKnown = true;\n"
        "        break;\n",
        remove_frame_ingress=False,
    )
    ptlw_main = _render_main(
        main_template,
        names["ptlw_tag"],
        names["ptlw_boot"],
        "partial_block_ptlw_api.h",
        "MF1750_PARTIAL_BLOCK_PTLW_BUILD",
        "  PartialBlockFactoryWhite,\n"
        "  PartialBlockPatchA1E,\n"
        "  PartialBlockPatchB0E,\n"
        "  PartialBlockPatchC1C,\n"
        "  PartialBlockWhiteRecovery,\n",
        '  server.on("/api/partial-block/factory-white", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialBlockFactoryWhite,\n'
        '                          "partial_block_factory_white");\n'
        "  });\n"
        '  server.on("/api/partial-block/patch-a-1e", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialBlockPatchA1E,\n'
        '                          "partial_block_patch_a_1e");\n'
        "  });\n"
        '  server.on("/api/partial-block/patch-b-0e", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialBlockPatchB0E,\n'
        '                          "partial_block_patch_b_0e");\n'
        "  });\n"
        '  server.on("/api/partial-block/patch-c-1c", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialBlockPatchC1C,\n'
        '                          "partial_block_patch_c_1c");\n'
        "  });\n"
        '  server.on("/api/partial-block/white-recovery", HTTP_POST, []() {\n'
        '    queueEpdJobAndRespond(PendingEpdAction::PartialBlockWhiteRecovery,\n'
        '                          "partial_block_white_recovery");\n'
        "  });\n",
        "      case PendingEpdAction::PartialBlockFactoryWhite:\n"
        "        result = epdDisplayCompiledPartialBlockPtlw(\n"
        "            EpdPartialBlockPtlwRole::FactoryWhite);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialBlockPatchA1E:\n"
        "        result = epdDisplayCompiledPartialBlockPtlw(\n"
        "            EpdPartialBlockPtlwRole::PatchA1E);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialBlockPatchB0E:\n"
        "        result = epdDisplayCompiledPartialBlockPtlw(\n"
        "            EpdPartialBlockPtlwRole::PatchB0E);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialBlockPatchC1C:\n"
        "        result = epdDisplayCompiledPartialBlockPtlw(\n"
        "            EpdPartialBlockPtlwRole::PatchC1C);\n"
        "        resultKnown = true;\n"
        "        break;\n"
        "      case PendingEpdAction::PartialBlockWhiteRecovery:\n"
        "        result = epdDisplayCompiledPartialBlockPtlw(\n"
        "            EpdPartialBlockPtlwRole::WhiteRecovery);\n"
        "        resultKnown = true;\n"
        "        break;\n",
        remove_frame_ingress=True,
    )

    return {
        names["atlas_layout_inc"]:
            _render_atlas_layout_inc(frame, cs1, cs2, layout_sha, version),
        "src/partial_atlas_1e_api.h": _render_atlas_api_header(),
        names["atlas_driver"]: atlas_driver,
        names["atlas_main"]: atlas_main,
        names["ptlw_contract_inc"]:
            _render_ptlw_contract_inc(identities, profiles, version),
        "src/partial_block_ptlw_api.h": _render_ptlw_api_header(),
        names["ptlw_driver"]: ptlw_driver,
        names["ptlw_main"]: ptlw_main,
    }


def render_all() -> dict[str, str]:
    """Return {relative_path: content} for the V1 generated sources."""

    return render_version("V1")


def build_report(version: str = "V1") -> dict[str, Any]:
    names = _version_names(version)
    frame = build_atlas_frame(version)
    cs1 = controller_stream(frame, False)
    cs2 = controller_stream(frame, True)
    layout_doc = atlas_layout_doc(version)
    layout_sha = _sha256(_canonical(layout_doc))
    identities = route_b_identities(version)
    profiles = _profile_reports()
    tail = _r2g_tail()
    tail_sha = _sha256(tail.encode("utf-8"))
    rendered = render_version(version)
    r2g_text = R2G_DRIVER_PATH.read_text(encoding="utf-8")

    profile_summary = {}
    for label, report in profiles.items():
        profile_summary[label] = {
            "family_label": label,
            "family_label_is_not_bitmask": True,
            "base_mask_hex": report["mask_hex"],
            "commented_records": report["commented_records"],
            "r20_sha256": report["r20_sha256"],
            "diff_byte_count_vs_active": report["diff_byte_count_vs_active"],
            "pwr_sha256": report["pwr_sha256"],
            "pll_sha256": report["pll_sha256"],
            "r21_sha256": report["r21_sha256"],
            "byte_identity": (
                "the route B driver binds the same compiled kR20Payload object "
                "as the sealed wf_wmask_{} build".format(label)
            ),
        }

    report = {
        "schema_version": 1,
        "kind": "mf1750-partial-block-first-batch-generation",
        "date": DATE,
        "handoff": HANDOFF_DOC,
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "panel": {"width": WIDTH, "height": HEIGHT,
                  "controller_width": CONTROLLER_WIDTH,
                  "frame_bytes": FRAME_BYTES,
                  "controller_dtm_bytes": CONTROLLER_DTM_BYTES},
        "spi_hz": 1_000_000,
        "spi_hz_is_frozen_default": True,
        "route_a": {
            "env": names["atlas_env"],
            "tag": names["atlas_tag"],
            "profile": profile_summary["1E"],
            "frame": {
                "bytes": len(frame),
                "fnv1a": _fnv1a(frame),
                "sha256": _sha256(frame),
                "background_code": ATLAS_BACKGROUND_CODE,
                "background_is_l535_white_code7": True,
                "roi_codes": [roi["code"] for roi in atlas_regions(version)[0]],
                "codes_are_transport_codes_not_colour_names": True,
            },
            "controller_streams": {
                "cs1": {"bytes": len(cs1), "fnv1a": _fnv1a(cs1),
                        "sha256": _sha256(cs1)},
                "cs2": {"bytes": len(cs2), "fnv1a": _fnv1a(cs2),
                        "sha256": _sha256(cs2)},
            },
            "layout": {"doc": layout_doc, "sha256": layout_sha},
            "roi_list": atlas_roi_list_doc(version),
            "refresh": "sealed full-frame path (PON, BTST2, DRF 0x00, POF 0x00)",
        },
        "route_b": {
            "env": names["ptlw_env"],
            "tag": names["ptlw_tag"],
            "profiles": {label: profile_summary[label]
                         for label in PTLW_PROFILE_LABELS},
            "windows": [dict(window) for window in PTLW_WINDOWS],
            "window_semantics": (
                "x,y,width,height; inclusive controller endpoints "
                "xe=x+w-1, ye=y+h-1; each window is written to CS1 and CS2 "
                "separately with identical coordinates and patch code"
            ),
            "ptlw": {
                "command": "0x83",
                "payload_bytes": PTLW_PAYLOAD_BYTES,
                "mode": PTLW_MODE,
                "payloads_hex": identities["ptlw_payloads_hex"],
                "writes_per_controller_per_action": 1,
                "repeat_after_pon": False,
            },
            "transport": {
                "preload_dtm": identities["preload_dtm"],
                "crop_dtm": identities["crop_dtm"],
                "combined_dtm": identities["combined_dtm"],
                "order": [
                    "LOAD_SELECTED_PWR_PLL_PSR_TRES_BROADCAST",
                    "LOAD_SELECTED_R20_R21_CS1",
                    "LOAD_SAME_SELECTED_R20_R21_CS2",
                    "FULL_CODE7_DTM_PRESTAGE_CS1_NO_REFRESH",
                    "FULL_CODE7_DTM_PRESTAGE_CS2_NO_REFRESH",
                    "PTLW_CS1_INCLUSIVE_ONCE",
                    "CROPPED_TARGET_DTM_CS1",
                    "PTLW_CS2_INCLUSIVE_ONCE",
                    "CROPPED_TARGET_DTM_CS2",
                    "PON_BUSY_COMPLETE",
                    "DRF_00_BUSY_COMPLETE",
                    "POF_00_BUSY_COMPLETE",
                ],
                "action_stage_btst2": False,
                "action_stage_cdi": False,
                "command_0x86": False,
                "refresh_deviation_from_full_frame_tail": (
                    "partial actions use the sealed clean-PTLW PON/DRF/POF "
                    "refresh without the full-frame BTST2 stage"
                ),
            },
            "actions": [
                {"ordinal": 1, "role": "FACTORY_WHITE_ANCHOR",
                 "transport": "FACTORY_OTP_FULL_FRAME_0X11",
                 "window": None, "profile": None},
                {"ordinal": 2, "role": "PATCH_A_1E_WINDOW_A",
                 "transport": "CLEAN_PTLW_PARTIAL",
                 "window": dict(PTLW_WINDOWS[0]), "profile": "1E"},
                {"ordinal": 3, "role": "PATCH_B_0E_WINDOW_B_HOLD_A",
                 "transport": "CLEAN_PTLW_PARTIAL",
                 "window": dict(PTLW_WINDOWS[1]), "profile": "0E"},
                {"ordinal": 4, "role": "PATCH_C_1C_WINDOW_C_HOLD_AB",
                 "transport": "CLEAN_PTLW_PARTIAL",
                 "window": dict(PTLW_WINDOWS[2]), "profile": "1C"},
                {"ordinal": 5, "role": "WHITE_RECOVERY",
                 "transport": "FACTORY_OTP_FULL_FRAME_0X11",
                 "window": None, "profile": None},
            ],
            "busy_timeline_evidence": (
                "per-action EpdOperationReport (pon/drf/pof wait ms and busy "
                "stage evidence) published via /api/diagnostic/report"
            ),
            "roi_list": ptlw_roi_list_doc(version),
        },
        "runtime_tail_sha256": tail_sha,
        "r2g_driver_sha256": _sha256(r2g_text.encode("utf-8")),
        "generated_sources": {
            path: {"bytes": len(content.encode("utf-8")),
                   "sha256": _sha256(content.encode("utf-8"))}
            for path, content in sorted(rendered.items())
        },
    }
    if version != "V1":
        report["layout_revision"] = version
        report["changes_vs_v1"] = {
            "route_a_layout": (
                "slot coordinates unchanged; (544,384) code6 -> code7 probe; "
                "(792,384) code7 background reference -> code6 block; "
                "discriminates whether the P0 olive block follows code7 or "
                "the (792,384) position"
            ),
            "route_b_patch_code": (
                "cropped uniform DTM patch code 0 -> 4 (fill byte 0x00 -> "
                "0x44); preload, PTLW payloads, windows, profiles, and the "
                "refresh sequence are byte-identical to V1"
            ),
            "reason": (
                "handoff amendment 2 after P0 anomaly analysis "
                "(PARTIAL_BLOCK_P0_ANOMALY_ANALYSIS_20261020_V1)"
            ),
        }
    return report


def build_v3_report() -> dict[str, Any]:
    """V3 session env report: normalization + probes + V2 atlas identities."""

    identities = v3_identities()
    profiles = _profile_reports()
    tail = _r2g_tail()
    rendered = render_v3()
    return {
        "schema_version": 1,
        "kind": "mf1750-partial-block-v3-session-generation",
        "date": DATE,
        "handoff": HANDOFF_DOC,
        "amendment": (
            "handoff amendment 2 + anomaly-2 protocols 1+2 "
            "(PARTIAL_BLOCK_P0_ANOMALY2_ANALYSIS_20261020_V1)"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "env": ATLAS_ENV_V3,
        "tag": ATLAS_TAG_V3,
        "spi_hz": 1_000_000,
        "spi_hz_is_frozen_default": True,
        "tuples": {
            "factory_otp": {
                "path": "sealed ec5_factory_otp_white_recovery_driver.inc "
                        "cascade path (PSR 5F,69 selects OTP LUT)",
                "runtime_lut_uploaded": False,
            },
            "active": {
                "r20_sha256": V3_ACTIVE_R20_SHA256,
                "pwr_sha256": wmask.PWR_SHA256,
                "pll_sha256": wmask.PLL_SHA256,
                "r21_sha256": wmask.R21_SHA256,
                "byte_identity": "same compiled objects as the sealed legacy "
                                 "active reference (spd1657_legacy_535_reference.inc)",
            },
            "1E": {
                "family_label": "1E",
                "family_label_is_not_bitmask": True,
                "r20_sha256": profiles["1E"]["r20_sha256"],
                "pwr_sha256": profiles["1E"]["pwr_sha256"],
                "pll_sha256": profiles["1E"]["pll_sha256"],
                "r21_sha256": profiles["1E"]["r21_sha256"],
                "byte_identity": "same compiled object as the sealed "
                                 "wf_wmask_1E build",
            },
        },
        "normalize": {
            "sequence": [dict(step) for step in V3_NORMALIZE_SEQUENCE],
            "step_count": len(V3_NORMALIZE_SEQUENCE),
            "reading": (
                "2x factory-OTP white, then 3x (code0 black, code1 white) "
                "alternating reset pairs under the active tuple, ending on "
                "white; per-step PON/DRF/POF timings published via "
                "/api/partial-atlas-v3/steps"
            ),
            "stop_on_failure": "fail-closed: a failed step aborts the sequence",
        },
        "frames": identities["frames"],
        "controller_stream_fnv1a": identities["streams"],
        "actions": [
            {"ordinal": 1, "role": "NORMALIZE", "profile": "factory_otp+active",
             "endpoint": "/api/partial-atlas-v3/normalize"},
            {"ordinal": 2, "role": "PROBE_CODE7", "profile": "1E",
             "frame_sha256": identities["frames"]["probe7"]["sha256"],
             "endpoint": "/api/partial-atlas-v3/probe-code7"},
            {"ordinal": 3, "role": "PROBE_CODE1", "profile": "1E",
             "frame_sha256": identities["frames"]["white"]["sha256"],
             "endpoint": "/api/partial-atlas-v3/probe-code1"},
            {"ordinal": 4, "role": "ATLAS_V2", "profile": "1E",
             "frame_sha256": identities["frames"]["atlas_v2"]["sha256"],
             "endpoint": "/api/partial-atlas-v3/atlas-v2"},
            {"ordinal": 5, "role": "WHITE_RECOVERY", "profile": "factory_otp",
             "endpoint": "/api/partial-atlas-v3/white-recovery"},
        ],
        "atlas_layout": "V2 (unchanged): frame sha256 1bca805d...",
        "runtime_tail_sha256": _sha256(tail.encode("utf-8")),
        "runtime_tail_byte_identical_to_r2g": True,
        "generated_sources": {
            path: {"bytes": len(content.encode("utf-8")),
                   "sha256": _sha256(content.encode("utf-8"))}
            for path, content in sorted(rendered.items())
        },
    }


def _write_generated(path: Path, content: str) -> None:
    payload = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"generated file exists with different content: {path}")
        return
    path.write_bytes(payload)


def generate_sources() -> dict[str, Any]:
    reports = {}
    for version in ATLAS_VERSIONS:
        report = build_report(version)
        for relative, content in render_version(version).items():
            path = ROOT / relative
            _write_generated(path, content)
            if _sha256(path.read_bytes()) != \
                    report["generated_sources"][relative]["sha256"]:
                raise RuntimeError(f"on-disk hash differs after generation: {path}")
        reports[version] = report
    v3_report = build_v3_report()
    for relative, content in render_v3().items():
        path = ROOT / relative
        _write_generated(path, content)
        if _sha256(path.read_bytes()) != \
                v3_report["generated_sources"][relative]["sha256"]:
            raise RuntimeError(f"on-disk hash differs after generation: {path}")
    reports["V3"] = v3_report
    v4_report = build_v4_report()
    for relative, content in render_v4().items():
        path = ROOT / relative
        _write_generated(path, content)
        if _sha256(path.read_bytes()) != \
                v4_report["generated_sources"][relative]["sha256"]:
            raise RuntimeError(f"on-disk hash differs after generation: {path}")
    reports["V4"] = v4_report
    return reports


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify on-disk sources match regeneration")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        rendered = {
            path: content
            for version in ATLAS_VERSIONS
            for path, content in render_version(version).items()
        }
        rendered.update(render_v3())
        rendered.update(render_v4())
        drift = [
            path for path, content in rendered.items()
            if not (ROOT / path).is_file()
            or (ROOT / path).read_bytes() != content.encode("utf-8")
        ]
        if drift:
            print(json.dumps({"drift": drift}, indent=1))
            return 1
        print(json.dumps({"check": "ok", "sources": len(rendered)}, indent=1))
        return 0
    reports = generate_sources()
    summary = {}
    for version, report in reports.items():
        if version == "V4":
            summary[version] = {
                "kind": report["kind"],
                "env": report["env"],
                "tag": report["tag"],
                "normalize_steps": report["normalize"]["step_count"],
                "atlas_frame_sha256": report["frame"]["sha256"],
                "layout_sha256": report["atlas_layout"]["sha256"],
                "generated_sources": report["generated_sources"],
            }
            continue
        if version == "V3":
            summary[version] = {
                "kind": report["kind"],
                "env": report["env"],
                "tag": report["tag"],
                "normalize_steps": report["normalize"]["step_count"],
                "atlas_frame_sha256": report["frames"]["atlas_v2"]["sha256"],
                "generated_sources": report["generated_sources"],
            }
            continue
        summary[version] = {
            "kind": report["kind"],
            "route_a": {
                "env": report["route_a"]["env"],
                "tag": report["route_a"]["tag"],
                "frame_sha256": report["route_a"]["frame"]["sha256"],
                "layout_sha256": report["route_a"]["layout"]["sha256"],
                "r20_sha256": report["route_a"]["profile"]["r20_sha256"],
            },
            "route_b": {
                "env": report["route_b"]["env"],
                "tag": report["route_b"]["tag"],
                "profile_r20_sha256": {
                    label: report["route_b"]["profiles"][label]["r20_sha256"]
                    for label in PTLW_PROFILE_LABELS
                },
                "patch_code": report["route_b"]["transport"]["crop_dtm"]["code"],
                "combined_dtm_sha256":
                    report["route_b"]["transport"]["combined_dtm"]["sha256"],
            },
            "generated_sources": report["generated_sources"],
        }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
