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
# Route A layout: white (code 7) background, seven 192x160 ROIs for codes 0-6.
# Columns/rows keep every ROI fully inside one 512-pixel controller half on
# even byte boundaries, clear of the x=512 cascade seam; slot (792,384) stays
# background as the on-frame white reference.
# ---------------------------------------------------------------------------

ATLAS_BACKGROUND_CODE = 7
ATLAS_ROI_WIDTH = 192
ATLAS_ROI_HEIGHT = 160
ATLAS_ROIS: tuple[dict[str, int], ...] = tuple(
    {"name": f"code{code}", "code": code, "x": x, "y": y,
     "w": ATLAS_ROI_WIDTH, "h": ATLAS_ROI_HEIGHT}
    for code, (x, y) in enumerate(
        ((48, 64), (288, 64), (544, 64), (792, 64), (48, 384), (288, 384), (544, 384))
    )
)
ATLAS_BACKGROUND_REFERENCE = {
    "name": "bg_ref", "code": ATLAS_BACKGROUND_CODE,
    "x": 792, "y": 384, "w": ATLAS_ROI_WIDTH, "h": ATLAS_ROI_HEIGHT,
}


def _validate_atlas_layout() -> None:
    slots = list(ATLAS_ROIS) + [ATLAS_BACKGROUND_REFERENCE]
    if len({roi["code"] for roi in ATLAS_ROIS}) != 7:
        raise RuntimeError("route A ROI codes are not unique")
    if [roi["code"] for roi in ATLAS_ROIS] != [0, 1, 2, 3, 4, 5, 6]:
        raise RuntimeError("route A ROI code order drifted")
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


def build_atlas_frame() -> bytes:
    """Return the fixed packed-4bpp route A frame (even x in the high nibble)."""

    _validate_atlas_layout()
    frame = bytearray(
        [(ATLAS_BACKGROUND_CODE << 4) | ATLAS_BACKGROUND_CODE] * FRAME_BYTES
    )
    for roi in ATLAS_ROIS:
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


def atlas_layout_doc() -> dict[str, Any]:
    return {
        "schema": "mf1750-partial-block-atlas-layout-v1",
        "panel": {"width": WIDTH, "height": HEIGHT,
                  "controller_width": CONTROLLER_WIDTH},
        "background_code": ATLAS_BACKGROUND_CODE,
        "background_is_l535_white_code7": True,
        "rois": [dict(roi) for roi in ATLAS_ROIS],
        "background_reference": dict(ATLAS_BACKGROUND_REFERENCE),
        "packed_format": "4bpp row-major, even x in the high nibble",
        "even_x_and_width": True,
        "seam_avoidance_x512": True,
        "codes_are_transport_codes_not_colour_names": True,
    }


def atlas_roi_list_doc() -> dict[str, Any]:
    """tools/mf1750_multi_roi_lab.py-compatible region list."""

    return {
        "schema": "mf1750-partial-block-atlas-roi-list-v1",
        "screen": {"width": WIDTH, "height": HEIGHT},
        "regions": [
            {"name": roi["name"], "code": roi["code"], "x": roi["x"],
             "y": roi["y"], "w": roi["w"], "h": roi["h"]}
            for roi in list(ATLAS_ROIS) + [ATLAS_BACKGROUND_REFERENCE]
        ],
    }


def ptlw_roi_list_doc() -> dict[str, Any]:
    """Route B measurement regions: both controller halves per window.

    Each partial action paints one symmetric patch pair (same window
    coordinates and code written to CS1 and CS2 separately), so the
    measurement list carries both global positions per window plus two
    patch-free background strips for the outside-window checks.
    """

    regions: list[dict[str, Any]] = []
    for window in PTLW_WINDOWS:
        for controller, x_offset in (("cs1", 0), ("cs2", CONTROLLER_WIDTH)):
            regions.append({
                "name": f"{window['name'].lower()}_{controller}",
                "code": PATCH_CODE,
                "x": window["x"] + x_offset,
                "y": window["y"],
                "w": window["w"],
                "h": window["h"],
            })
    regions.append({"name": "bg_north", "x": 432, "y": 24, "w": 160, "h": 32})
    regions.append({"name": "bg_south", "x": 432, "y": 556, "w": 160, "h": 32})
    return {
        "schema": "mf1750-partial-block-ptlw-roi-list-v1",
        "screen": {"width": WIDTH, "height": HEIGHT},
        "regions": regions,
    }


# ---------------------------------------------------------------------------
# Route B contract: handoff-fixed windows and the sealed clean-PTLW transport.
# ---------------------------------------------------------------------------

PTLW_COMMAND = 0x83
PTLW_MODE = 0x01
PTLW_PAYLOAD_BYTES = 9
PRELOAD_CODE = 7
PATCH_CODE = 0
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


def route_b_identities() -> dict[str, Any]:
    _validate_ptlw_windows()
    preload = _uniform(CONTROLLER_DTM_BYTES, PRELOAD_CODE)
    crop = _uniform(160 * 120 // 2, PATCH_CODE)
    combined = preload + crop
    return {
        "preload_dtm": {
            "bytes": len(preload), "code": PRELOAD_CODE,
            "fnv1a": _fnv1a(preload), "sha256": _sha256(preload),
        },
        "crop_dtm": {
            "bytes": len(crop), "code": PATCH_CODE,
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
                             layout_sha: str) -> str:
    rois = ",\n".join(
        f"    {{{roi['x']}, {roi['y']}, {roi['w']}, {roi['h']}, 0x{roi['code']:02X}}}"
        for roi in ATLAS_ROIS
    )
    asserts = []
    for index, roi in enumerate(ATLAS_ROIS):
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
    for left_index in range(len(ATLAS_ROIS)):
        for right_index in range(left_index + 1, len(ATLAS_ROIS)):
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
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

// Generated by tools/mf1750_partial_block_build.py.  Route A (P0) layout:
// white (code 7) background with seven fixed 192x160 ROIs, one per transport
// code {{0,1,2,3,4,5,6}}; every ROI sits fully inside one 512-pixel controller
// half, on even byte boundaries, clear of the x=512 cascade seam.  Codes are
// transport codes, not colour names.

namespace mf1750::partial_block::partial_atlas_1e {{

struct AtlasRoi {{
  std::uint16_t x;
  std::uint16_t y;
  std::uint16_t width;
  std::uint16_t height;
  std::uint8_t code;
}};

static constexpr std::uint8_t kBackgroundCode = 0x{ATLAS_BACKGROUND_CODE:02X};
static constexpr std::size_t kRoiCount = {len(ATLAS_ROIS)};
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

}}  // namespace mf1750::partial_block::partial_atlas_1e
"""


def _render_ptlw_contract_inc(identities: dict[str, Any],
                              profiles: dict[str, dict[str, Any]]) -> str:
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
    return f"""#pragma once

#include <cstddef>
#include <cstdint>

// Generated by tools/mf1750_partial_block_build.py.  Route B (P1-P3) contract:
// PTLW command 0x83 with a 9-byte inclusive window (xe=x+w-1, ye=y+h-1,
// mode 0x01), full code-7 controller preload without refresh, then one
// inclusive PTLW and one cropped uniform DTM per controller, then
// PON/DRF/POF with no PTLW repeat after PON.  Each window is written to CS1
// and CS2 separately with identical coordinates and patch code, giving one
// symmetric patch pair per action.  Codes are transport codes, not colour
// names.

namespace mf1750::partial_block::ptlw {{

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
static constexpr std::uint8_t kPatchCode = 0x{PATCH_CODE:02X};
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

}}  // namespace mf1750::partial_block::ptlw
"""


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


def _render_atlas_driver_head() -> str:
    records = wmask.selected_records(0x0E, True)
    return (
        """// Dedicated translation unit for partial-block route A (P0): the fixed 1E
// GrayExt tuple (base 0x0E plus the whole records 0-3 group; the family label
// is not a bitmask) drives one compiled white-background seven-code atlas
// frame through the sealed full-frame L535 path.  R20/PWR/PLL/R21/PSR and the
// runtime sequence are byte-identical to the sealed wf_wmask_1E build; the
// runtime tail below is byte-identical to the pinned R2G template.  Production
// and the wf_wmask_* translation units stay untouched.
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
#include "generated/partial_atlas_1e_layout.inc"
namespace pb_atlas = mf1750::partial_block::partial_atlas_1e;

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


def _render_ptlw_driver_head() -> str:
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
    return (
        """// Dedicated translation unit for partial-block route B (P1-P3): three
// fixed clean-PTLW partial-window actions whose complete R20 tuples are the
// same compiled objects as the sealed wf_wmask_1E / wf_wmask_0E / wf_wmask_1C
// full-frame builds (1E/1C family labels are base-plus-group labels, not
// bitmasks).  PWR, PLL=0x02, R21, PSR bytes are the pinned active payloads
// shared by every WMASK profile; the runtime tail below is byte-identical to
// the pinned R2G template.  Production and the wf_wmask_* translation units
// stay untouched.  Factory-OTP white anchors and closes the action sequence.
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
#include "generated/partial_block_ptlw_contract.inc"
namespace pb = mf1750::partial_block::ptlw;

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


_ROUTE_A_FIXTURE = """
// ===========================================================================
// Route A (P0) compiled multi-code atlas fixture
// (docs/MF1750_PARTIAL_BLOCK_WAVEFORM_HANDOFF_20261020.md).  One fixed
// white-background 1024x600 frame carries seven fixed ROIs, one per transport
// code {0,1,2,3,4,5,6}, refreshed once through the sealed 1E full-frame path.
// The frame is rebuilt and hash-validated before any panel I/O; no
// caller-controlled frame, coordinate, code, LUT, voltage, timing, retry, or
// recovery parameter is accepted.
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


def render_all() -> dict[str, str]:
    """Return {relative_path: content} for every generated source."""

    frame = build_atlas_frame()
    cs1 = controller_stream(frame, False)
    cs2 = controller_stream(frame, True)
    layout_doc = atlas_layout_doc()
    layout_sha = _sha256(_canonical(layout_doc))
    identities = route_b_identities()
    profiles = _profile_reports()

    atlas_driver = (
        _render_atlas_driver_head() + _r2g_tail() + _ROUTE_A_FIXTURE
    )
    ptlw_driver = (
        _render_ptlw_driver_head() + _r2g_tail() + _ROUTE_B_FIXTURE
    )
    main_template = R2G_MAIN_PATH.read_text(encoding="utf-8")
    atlas_main = _render_main(
        main_template,
        ATLAS_TAG,
        "partial block route A: compiled 1E seven-code atlas on white",
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
        PTLW_TAG,
        "partial block route B: clean PTLW windows A=1E B=0E C=1C + factory white",
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
        "src/generated/partial_atlas_1e_layout.inc":
            _render_atlas_layout_inc(frame, cs1, cs2, layout_sha),
        "src/partial_atlas_1e_api.h": _render_atlas_api_header(),
        "src/partial_atlas_1e_epd_driver.cpp": atlas_driver,
        "src/partial_atlas_1e_main.cpp": atlas_main,
        "src/generated/partial_block_ptlw_contract.inc":
            _render_ptlw_contract_inc(identities, profiles),
        "src/partial_block_ptlw_api.h": _render_ptlw_api_header(),
        "src/partial_block_ptlw_epd_driver.cpp": ptlw_driver,
        "src/partial_block_ptlw_main.cpp": ptlw_main,
    }


def build_report() -> dict[str, Any]:
    frame = build_atlas_frame()
    cs1 = controller_stream(frame, False)
    cs2 = controller_stream(frame, True)
    layout_doc = atlas_layout_doc()
    layout_sha = _sha256(_canonical(layout_doc))
    identities = route_b_identities()
    profiles = _profile_reports()
    tail = _r2g_tail()
    tail_sha = _sha256(tail.encode("utf-8"))
    rendered = render_all()
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

    return {
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
            "env": ATLAS_ENV,
            "tag": ATLAS_TAG,
            "profile": profile_summary["1E"],
            "frame": {
                "bytes": len(frame),
                "fnv1a": _fnv1a(frame),
                "sha256": _sha256(frame),
                "background_code": ATLAS_BACKGROUND_CODE,
                "background_is_l535_white_code7": True,
                "roi_codes": [roi["code"] for roi in ATLAS_ROIS],
                "codes_are_transport_codes_not_colour_names": True,
            },
            "controller_streams": {
                "cs1": {"bytes": len(cs1), "fnv1a": _fnv1a(cs1),
                        "sha256": _sha256(cs1)},
                "cs2": {"bytes": len(cs2), "fnv1a": _fnv1a(cs2),
                        "sha256": _sha256(cs2)},
            },
            "layout": {"doc": layout_doc, "sha256": layout_sha},
            "roi_list": atlas_roi_list_doc(),
            "refresh": "sealed full-frame path (PON, BTST2, DRF 0x00, POF 0x00)",
        },
        "route_b": {
            "env": PTLW_ENV,
            "tag": PTLW_TAG,
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
            "roi_list": ptlw_roi_list_doc(),
        },
        "runtime_tail_sha256": tail_sha,
        "r2g_driver_sha256": _sha256(r2g_text.encode("utf-8")),
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
    report = build_report()
    for relative, content in render_all().items():
        path = ROOT / relative
        _write_generated(path, content)
        if _sha256(path.read_bytes()) != report["generated_sources"][relative]["sha256"]:
            raise RuntimeError(f"on-disk hash differs after generation: {path}")
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify on-disk sources match regeneration")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        rendered = render_all()
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
    report = generate_sources()
    print(json.dumps({
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
            "combined_dtm_sha256":
                report["route_b"]["transport"]["combined_dtm"]["sha256"],
        },
        "generated_sources": report["generated_sources"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
