#!/usr/bin/env python3
"""Generate White records 4-7 mask variants and GrayExt variants, offline.

Mask bit 0 selects White record 4, bit 1 record 5, bit 2 record 6, and bit 3
record 7.  Selected 11-byte records come from the commented R20 table; every
other R20 byte comes from active.  The low-4-bit meaning is unchanged.

The separate records 0-3 group-add capability is available only for the
registered GrayExt bases 0E/0C/0D.  Their family labels 1E/1C/1D mean
"low-nibble base plus the whole records 0-3 group"; they are not reinterpreted
as an 8-bit bitmask.  A mutually exclusive single record-add capability is
registered only for base 0E with labels 0E_R0/0E_R1/0E_R2/0E_R3, each meaning
base 0E plus exactly one records 0-3 member, again not a bitmask.  A further
mutually exclusive record-subset capability is registered only for base 0E
with labels 0E_R0R1/0E_R0R2/0E_R0R3, meaning base 0E plus exactly that pair;
it likewise is not a bitmask.  The generator deliberately excludes the active
baseline and the already-built R2G, G6, R2F, and R2D variants.

No device, network, relay, camera, serial, or flashing access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.runtime_waveform import l535_table_builder as builder  # noqa: E402

PENDING_MASKS = (0x01, 0x02, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E)
EXCLUDED_MASKS = {
    0x00: "active baseline",
    0x03: "MF1750_WF_BISECT_R2G_20261018",
    0x04: "MF1750_WF_G6_WHITE_20261017",
    0x0F: "MF1750_WF_BISECT_R2F_20261018",
}
GROUP_ADD_RECORDS = frozenset({0, 1, 2, 3})
GRAYEXT_VARIANTS = {
    0x0E: {
        "records": frozenset({0, 1, 2, 3, 5, 6, 7}),
        "diff_bytes": 53,
        "r20_sha256": "5f1820da8b935361701bc6fe4d855b9694891c32ed33f420d4a5fce488235f40",
    },
    0x0C: {
        "records": frozenset({0, 1, 2, 3, 6, 7}),
        "diff_bytes": 45,
        "r20_sha256": "7070dc29c1723c4539b4b332ff09b74c682bf09d4b19765be38fddd4743334cf",
    },
    0x0D: {
        "records": frozenset({0, 1, 2, 3, 4, 6, 7}),
        "diff_bytes": 55,
        "r20_sha256": "58b5897fec693b851160456ffab49907b33a1b4ec535f3208f8192727f027119",
    },
}
GRAYEXT_BASE_MASKS = tuple(GRAYEXT_VARIANTS)
SINGLE_RECORD_ADD_BASE_MASK = 0x0E
SINGLE_RECORD_ADD_VARIANTS = {
    0: {
        "records": frozenset({0, 5, 6, 7}),
        "diff_bytes": 27,
        "r20_sha256": "dcf82f0aa317c22f074bfa972dfd0c8b3b79ef69d46258ac06454ec34f12c2fb",
    },
    1: {
        "records": frozenset({1, 5, 6, 7}),
        "diff_bytes": 32,
        "r20_sha256": "3f6219a921145fba5ac80a762bdb8578e6f3b8dfb0a68c981a015de49a9650bc",
    },
    2: {
        "records": frozenset({2, 5, 6, 7}),
        "diff_bytes": 32,
        "r20_sha256": "d634c25fdc427d43c511d1c54b69bdcffd556d7e8934bd41c4b893b5249561cc",
    },
    3: {
        "records": frozenset({3, 5, 6, 7}),
        "diff_bytes": 31,
        "r20_sha256": "7bfed76433d8b6467a444bb9a3f7ff389d86c650d97f942a2aa2c03856877c24",
    },
}
SINGLE_RECORD_ADD_RECORDS = tuple(SINGLE_RECORD_ADD_VARIANTS)
RECORD_SUBSET_ADD_BASE_MASK = 0x0E
RECORD_SUBSET_ADD_VARIANTS = {
    (0, 1): {
        "records": frozenset({0, 1, 5, 6, 7}),
        "diff_bytes": 36,
        "r20_sha256": "01938613895b88ba779089e5ede7b572b0a1cfdc294bccd80fcd5bca56b6de45",
    },
    (0, 2): {
        "records": frozenset({0, 2, 5, 6, 7}),
        "diff_bytes": 36,
        "r20_sha256": "9d8f1eb6f86022d639e1c0b38a5e63838ab10fffc315022a2896b6aacacf98d6",
    },
    (0, 3): {
        "records": frozenset({0, 3, 5, 6, 7}),
        "diff_bytes": 35,
        "r20_sha256": "7c93c6b1532bbbee4e71cffd8d8e83056b321be1ab04fd1dc039906daa5d717b",
    },
}
RECORD_SUBSET_ADD_SUBSETS = tuple(RECORD_SUBSET_ADD_VARIANTS)
WHITE_CATEGORY_START = 183
WHITE_RECORDS_4_7_START = 227
WHITE_CATEGORY_END = 271
RECORD_BYTES = 11
R20_BYTES = 535
R21_BYTES = 704
DATE = "20261018"
GRAYEXT_DATE = "20261019"
PWR_SHA256 = "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2"
PLL_SHA256 = "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
R21_SHA256 = "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
DRIVER_TEMPLATE_PATH = ROOT / "src/wf_bisect_r2g_epd_driver.cpp"
MAIN_TEMPLATE_PATH = ROOT / "src/wf_bisect_r2g_main.cpp"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def mask_label(mask: int) -> str:
    return f"{mask:02X}"


def family_label(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    if record_subset is not None:
        return f"{mask_label(mask)}_{''.join(f'R{record}' for record in record_subset)}"
    if record_add is not None:
        return f"{mask_label(mask)}_R{record_add}"
    return f"1{mask:X}" if group_add else mask_label(mask)


def slug(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    return f"wf_wmask_{family_label(mask, group_add, record_add, record_subset)}"


def tag(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    date = GRAYEXT_DATE if group_add or record_add is not None or record_subset is not None else DATE
    return f"MF1750_WF_WMASK_{family_label(mask, group_add, record_add, record_subset)}_{date}"


def env_name(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    env_label = family_label(mask, group_add, record_add, record_subset).lower()
    if record_add is not None or record_subset is not None:
        env_label = env_label.replace("_", "-")
    return f"esp32-s3-devkitc-1-wf-wmask-{env_label}"


def selected_records(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> list[int]:
    selected_modes = int(group_add) + int(record_add is not None) + int(record_subset is not None)
    if selected_modes > 1:
        raise ValueError("group_add, record_add, and record_subset are mutually exclusive")
    low_records = {4 + bit for bit in range(4) if mask & (1 << bit)}
    if group_add:
        return sorted(low_records | GROUP_ADD_RECORDS)
    if record_add is not None:
        return sorted(low_records | {record_add})
    if record_subset is not None:
        return sorted(low_records | set(record_subset))
    return sorted(low_records)


def source_paths(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> dict[str, Path]:
    stem = slug(mask, group_add, record_add, record_subset)
    return {
        "include": ROOT / f"src/generated/spd1657_{stem}.inc",
        "driver": ROOT / f"src/{stem}_epd_driver.cpp",
        "main": ROOT / f"src/{stem}_main.cpp",
    }


def _reference_array(role: str, name: str) -> bytes:
    text = builder.REFERENCE_INC.read_text(encoding="utf-8")
    chunk = text.split(f"namespace {role} {{", 1)[1]
    if role == "active":
        chunk = chunk.split("namespace commented {", 1)[0]
    match = re.search(re.escape(name) + r"\[\d+\]\s*=\s*\{(.*?)\};", chunk, re.S)
    if match is None:
        raise RuntimeError(f"reference include is missing {role}::{name}")
    return bytes(
        int(value.strip(), 16)
        for value in match.group(1).split(",")
        if value.strip()
    )


def _record_span(record: int) -> tuple[int, int]:
    start = WHITE_CATEGORY_START + RECORD_BYTES * record
    return start, start + RECORD_BYTES


def _fmt_array(name: str, payload: bytes) -> str:
    lines = [f"static constexpr std::uint8_t {name}[{len(payload)}] = {{"]
    for index in range(0, len(payload), 16):
        lines.append(
            "    "
            + ", ".join(f"0x{byte:02X}" for byte in payload[index:index + 16])
            + ","
        )
    lines.append("};")
    return "\n".join(lines)


def _render_include(
    mask: int,
    report: dict,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    namespace = slug(mask, group_add, record_add, record_subset)
    records = "+".join(
        str(record) for record in selected_records(mask, group_add, record_add, record_subset)
    )
    spans = ", ".join(
        f"[{start}:{end}]"
        for start, end in (
            _record_span(record)
            for record in selected_records(mask, group_add, record_add, record_subset)
        )
    )
    if group_add:
        comments = [
            "// Generated by tools/mf1750_wf_wmask_build.py.  Mask bit 0/1/2/3 selects",
            f"// White record 4/5/6/7 from base mask 0x{mask_label(mask)}.  Family label",
            f"// {family_label(mask, True)} additionally selects the whole records 0-3 group;",
            "// it is not an 8-bit bitmask.  Final commented White records are",
            f"// {records} at {spans}; every other R20 byte is exactly active.",
            "// PWR and PLL=0x02 are exactly active.  R21/runtime stay unchanged.",
        ]
    elif record_subset is not None:
        comments = [
            "// Generated by tools/mf1750_wf_wmask_build.py.  Mask bit 0/1/2/3 selects",
            f"// White record 4/5/6/7 from base mask 0x{mask_label(mask)}.  Family label",
            f"// {family_label(mask, False, None, record_subset)} additionally selects exactly White records "
            f"{'+'.join(str(record) for record in record_subset)};",
            "// it is not a bitmask.  Final commented White records are",
            f"// {records} at {spans}; every other R20 byte is exactly active.",
            "// PWR and PLL=0x02 are exactly active.  R21/runtime stay unchanged.",
        ]
    elif record_add is not None:
        comments = [
            "// Generated by tools/mf1750_wf_wmask_build.py.  Mask bit 0/1/2/3 selects",
            f"// White record 4/5/6/7 from base mask 0x{mask_label(mask)}.  Family label",
            f"// {family_label(mask, False, record_add)} additionally selects exactly White record {record_add};",
            "// it is not a bitmask.  Final commented White records are",
            f"// {records} at {spans}; every other R20 byte is exactly active.",
            "// PWR and PLL=0x02 are exactly active.  R21/runtime stay unchanged.",
        ]
    else:
        comments = [
            "// Generated by tools/mf1750_wf_wmask_build.py.  Mask bit 0/1/2/3 selects",
            f"// White record 4/5/6/7.  Mask 0x{mask_label(mask)} selects records {records}",
            f"// at {spans}; every other R20 byte is exactly active.",
            "// PWR and PLL=0x02 are exactly active.  R21/runtime stay unchanged.",
        ]
    lines = [
        "#pragma once",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        *comments,
        "",
        f"namespace mf1750::runtime_lut::{namespace} {{",
        "",
        f"static constexpr std::uint8_t kWhiteRecordMask = 0x{mask_label(mask)};",
    ]
    if group_add:
        lines.append("static constexpr bool kAddWhiteRecords0To3 = true;")
    elif record_subset is not None:
        lines.append(
            "static constexpr std::uint8_t kAddedWhiteRecords[2] = {"
            + ", ".join(f"0x{record:02X}" for record in record_subset)
            + "};"
        )
    elif record_add is not None:
        lines.append(f"static constexpr std::uint8_t kAddedWhiteRecord = 0x{record_add:02X};")
    lines.extend([
        "static constexpr std::size_t kR20PayloadBytes = 535;",
        f"// sha256(R20)={report['r20_sha256']}",
        f"// sha256(PWR)={report['pwr_sha256']}; sha256(PLL)={report['pll_sha256']}",
        "static constexpr std::uint8_t kPowerPayload[6] = {",
        "    " + ", ".join(f"0x{byte:02X}" for byte in report["pwr_payload"]) + ",",
        "};",
        "static constexpr std::uint8_t kPllPayload[1] = {",
        "    0x02,",
        "};",
        _fmt_array("kR20Payload", bytes(report["r20_payload"])),
        f"}}  // namespace mf1750::runtime_lut::{namespace}",
        "",
    ])
    return "\n".join(lines)


def _render_driver(
    mask: int,
    runtime_tail: str,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    label = family_label(mask, group_add, record_add, record_subset)
    stem = slug(mask, group_add, record_add, record_subset)
    records = "+".join(
        str(record) for record in selected_records(mask, group_add, record_add, record_subset)
    )
    guard = f"WfWmask{label}"
    if group_add:
        family_comment = (
            f"// Family label {label} means base 0x{mask_label(mask)} plus the whole records 0-3 group;\n"
            "// it is not an 8-bit bitmask.\n"
        )
        family_assert = (
            "static_assert(l535_variant::kAddWhiteRecords0To3,\n"
            '              "GrayExt records 0-3 group-add flag is not set");\n'
        )
        use_commented = (
            "(index >= 183 && index < 227 && l535_variant::kAddWhiteRecords0To3) ||\n"
            "         (index >= 227 && index < 271 &&\n"
            "          ((l535_variant::kWhiteRecordMask >> ((index - 227) / 11)) & 0x01U) != 0)"
        )
    elif record_subset is not None:
        subset_conditions = []
        for index, record in enumerate(record_subset):
            start, end = _record_span(record)
            subset_conditions.append(
                f"(index >= {start} && index < {end} &&\n"
                f"          l535_variant::kAddedWhiteRecords[{index}] == 0x{record:02X})"
            )
        family_comment = (
            f"// Family label {label} means base 0x{mask_label(mask)} plus exactly White records "
            f"{'+'.join(str(record) for record in record_subset)};\n"
            "// it is not a bitmask.\n"
        )
        family_assert = (
            f"static_assert(l535_variant::kAddedWhiteRecords[0] == 0x{record_subset[0]:02X} &&\n"
            f"                  l535_variant::kAddedWhiteRecords[1] == 0x{record_subset[1]:02X},\n"
            '              "White record-subset identities are not set");\n'
        )
        use_commented = (
            " ||\n         ".join(subset_conditions)
            + " ||\n         (index >= 227 && index < 271 &&\n"
            "          ((l535_variant::kWhiteRecordMask >> ((index - 227) / 11)) & 0x01U) != 0)"
        )
    elif record_add is not None:
        start, end = _record_span(record_add)
        family_comment = (
            f"// Family label {label} means base 0x{mask_label(mask)} plus exactly White record {record_add};\n"
            "// it is not a bitmask.\n"
        )
        family_assert = (
            f"static_assert(l535_variant::kAddedWhiteRecord == 0x{record_add:02X},\n"
            '              "single White record-add identity is not set");\n'
        )
        use_commented = (
            f"(index >= {start} && index < {end} &&\n"
            f"          l535_variant::kAddedWhiteRecord == 0x{record_add:02X}) ||\n"
            "         (index >= 227 && index < 271 &&\n"
            "          ((l535_variant::kWhiteRecordMask >> ((index - 227) / 11)) & 0x01U) != 0)"
        )
    else:
        family_comment = ""
        family_assert = ""
        use_commented = (
            "index >= 227 && index < 271 &&\n"
            "         ((l535_variant::kWhiteRecordMask >> ((index - 227) / 11)) & 0x01U) != 0"
        )
    prefix = f"""// Dedicated translation unit for WF WMASK 0x{label}: commented White records {records}.
{family_comment}// Every unselected R20 byte, PWR, PLL=0x02, R21, PSR, and the runtime sequence
// remain on the sealed active path.  Generated independently of the pinned bisect TUs.
#include "epd_driver.h"

#include <SPI.h>
#if MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
    MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
    MF1750_ENABLE_COLOR_LAB || MF1750_ENABLE_OTP_TRANSITION_MATRIX || \
    MF1750_ENABLE_DITHER_COLOR_ATLAS || \
    MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 || \
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"

#if defined(MF1750_L535_FRAME_PATH_BUILD)
#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_{stem}.inc"
namespace l535_variant = mf1750::runtime_lut::{stem};

static_assert(l535_variant::kWhiteRecordMask == 0x{mask_label(mask)},
              "compiled White record mask differs from the preregistered mask");
{family_assert}static_assert(sizeof(l535_variant::kR20Payload) == 535,
              "WMASK R20 payload must be exactly 535 bytes");

constexpr bool wfWmask{label}UseCommented(std::size_t index) {{
  return {use_commented};
}}

// C++11 compile-time proof for every one of the 535 transmitted R20 bytes.
template <std::size_t INDEX>
struct {guard}RecordsMatch {{
  static constexpr bool value =
      (l535_variant::kR20Payload[INDEX] ==
       (wfWmask{label}UseCommented(INDEX)
            ? l535_lut::commented::kR20Payload[INDEX]
            : l535_lut::active::kR20Payload[INDEX])) &&
      {guard}RecordsMatch<INDEX + 1>::value;
}};
template <>
struct {guard}RecordsMatch<535> {{
  static constexpr bool value = true;
}};
static_assert({guard}RecordsMatch<0>::value,
              "WMASK R20 sources do not match the preregistered mask");

static_assert(l535_variant::kPowerPayload[0] == l535_lut::active::kPowerPayload[0] &&
                  l535_variant::kPowerPayload[1] == l535_lut::active::kPowerPayload[1] &&
                  l535_variant::kPowerPayload[2] == l535_lut::active::kPowerPayload[2] &&
                  l535_variant::kPowerPayload[3] == l535_lut::active::kPowerPayload[3] &&
                  l535_variant::kPowerPayload[4] == l535_lut::active::kPowerPayload[4] &&
                  l535_variant::kPowerPayload[5] == l535_lut::active::kPowerPayload[5],
              "WMASK PWR payload differs from active");
static_assert(l535_variant::kR20Payload[1] == l535_variant::kPowerPayload[2] &&
                  l535_variant::kR20Payload[2] == l535_variant::kPowerPayload[3] &&
                  l535_variant::kR20Payload[3] == l535_variant::kPowerPayload[4] &&
                  l535_variant::kR20Payload[4] == l535_variant::kPowerPayload[5],
              "R20[1:5] != PWR[2:6]: active header/PWR mirror broken");
static_assert(l535_variant::kPllPayload[0] == 0x02 &&
                  l535_variant::kPllPayload[0] == l535_lut::active::kPllPayload[0] &&
                  l535_variant::kR20Payload[6] == l535_variant::kPllPayload[0],
              "R20[6] != PLL[0] == active 0x02");

// The driver uploads l535_lut::active::kR21Payload directly.  Prove its full
// 704-byte active identity rather than sampling only the endpoints.
template <std::size_t INDEX>
struct {guard}ActiveR21Unchanged {{
  static constexpr bool value =
      l535_lut::active::kR21Payload[INDEX] == 0xFF &&
      {guard}ActiveR21Unchanged<INDEX + 1>::value;
}};
template <>
struct {guard}ActiveR21Unchanged<704> {{
  static constexpr bool value = true;
}};
static_assert(l535_lut::active::kR21PayloadBytes == 704 &&
                  l535_lut::active::kR21IsAllFf &&
                  {guard}ActiveR21Unchanged<0>::value,
              "active R21 is no longer the sealed 704 x 0xFF payload");
#endif

"""
    return prefix + runtime_tail


def _render_main(
    mask: int,
    template: str,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> str:
    old_tag = "MF1750_WF_BISECT_R2G_20261018"
    old_boot = "WF bisection R2G: commented White records 4+5"
    records = "+".join(
        str(record) for record in selected_records(mask, group_add, record_add, record_subset)
    )
    new_boot = f"WF WMASK {family_label(mask, group_add, record_add, record_subset)}: commented White records {records}"
    if template.count(old_tag) != 1 or template.count(old_boot) != 1:
        raise RuntimeError("R2G main template identity markers changed")
    return template.replace(old_tag, tag(mask, group_add, record_add, record_subset)).replace(old_boot, new_boot)


def _write_generated(path: Path, content: str) -> None:
    payload = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"generated file exists with different content: {path}")
        return
    path.write_bytes(payload)


def build_offline_variant(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> tuple[dict, dict[str, str]]:
    selected_modes = int(group_add) + int(record_add is not None) + int(record_subset is not None)
    if selected_modes > 1:
        raise ValueError("group_add, record_add, and record_subset are mutually exclusive")
    if record_subset is not None:
        if (
            mask != RECORD_SUBSET_ADD_BASE_MASK
            or record_subset not in RECORD_SUBSET_ADD_VARIANTS
        ):
            raise ValueError(
                "record-subset add is registered only for base 0x0E and subsets "
                "(0,1), (0,2), (0,3)"
            )
        if set(selected_records(mask, False, None, record_subset)) != \
                RECORD_SUBSET_ADD_VARIANTS[record_subset]["records"]:
            raise RuntimeError(f"record-subset add base 0x{mask:02X} record set drifted")
    elif record_add is not None:
        if mask != SINGLE_RECORD_ADD_BASE_MASK or record_add not in SINGLE_RECORD_ADD_VARIANTS:
            raise ValueError(
                "single record-add is registered only for base 0x0E and records 0, 1, 2, 3"
            )
        if set(selected_records(mask, False, record_add)) != \
                SINGLE_RECORD_ADD_VARIANTS[record_add]["records"]:
            raise RuntimeError(f"single record-add base 0x{mask:02X} record set drifted")
    elif group_add:
        if mask not in GRAYEXT_VARIANTS:
            raise ValueError(
                f"records 0-3 group-add is registered only for GrayExt bases "
                f"{tuple(f'0x{item:02X}' for item in GRAYEXT_BASE_MASKS)}"
            )
        if set(selected_records(mask, True)) != GRAYEXT_VARIANTS[mask]["records"]:
            raise RuntimeError(f"GrayExt base 0x{mask:02X} record set drifted")
    elif mask not in PENDING_MASKS:
        raise ValueError(f"mask 0x{mask:02X} is excluded or invalid: {EXCLUDED_MASKS.get(mask)}")
    records = selected_records(mask, group_add, record_add, record_subset)
    label = family_label(mask, group_add, record_add, record_subset)
    active = builder.from_reference("active").to_bytes()
    commented = builder.from_reference("commented").to_bytes()
    if len(active) != R20_BYTES or len(commented) != R20_BYTES:
        raise RuntimeError("unexpected L535 geometry")

    variant = bytearray(active)
    for record in records:
        start, end = _record_span(record)
        variant[start:end] = commented[start:end]
    variant_bytes = bytes(variant)
    builder.validate_table_bytes(variant_bytes)

    expected = bytearray(active)
    for record in records:
        start, end = _record_span(record)
        expected[start:end] = commented[start:end]
        if variant_bytes[start:end] != commented[start:end]:
            raise RuntimeError(f"mask/family {label} record {record} is not commented")
        if commented[start:end] == active[start:end]:
            raise RuntimeError(f"mask/family {label} record {record} has no replacement content")
    if variant_bytes != bytes(expected):
        raise RuntimeError(f"mask/family {label} per-byte source reconstruction failed")
    for record in range(8):
        if record in records:
            continue
        start, end = _record_span(record)
        if variant_bytes[start:end] != active[start:end]:
            raise RuntimeError(f"mask/family {label} unselected White record {record} changed")
    if variant_bytes[:WHITE_CATEGORY_START] != active[:WHITE_CATEGORY_START] or \
            variant_bytes[WHITE_CATEGORY_END:] != active[WHITE_CATEGORY_END:]:
        raise RuntimeError(f"mask/family {label} header or non-White category changed")

    pwr = bytes([0x0F]) + active[:5]
    pll = bytes([0x02])
    active_pwr = _reference_array("active", "kPowerPayload")
    active_pll = _reference_array("active", "kPllPayload")
    active_r21 = _reference_array("active", "kR21Payload")
    commented_r21 = _reference_array("commented", "kR21Payload")
    if pwr != active_pwr or _sha256(pwr) != PWR_SHA256:
        raise RuntimeError(f"mask/family {label} PWR differs from pinned active")
    if pll != active_pll or _sha256(pll) != PLL_SHA256:
        raise RuntimeError(f"mask/family {label} PLL differs from pinned active")
    if variant_bytes[1:5] != pwr[2:6] or variant_bytes[6] != pll[0]:
        raise RuntimeError(f"mask/family {label} PWR/PLL mirror failed")
    if len(active_r21) != R21_BYTES or active_r21 != bytes([0xFF] * R21_BYTES) or \
            commented_r21 != active_r21 or _sha256(active_r21) != R21_SHA256:
        raise RuntimeError(f"mask/family {label} active R21 identity failed")

    diff = [index for index in range(R20_BYTES) if variant_bytes[index] != active[index]]
    selected_spans = [_record_span(record) for record in records]
    if any(not any(start <= index < end for start, end in selected_spans) for index in diff):
        raise RuntimeError(f"mask/family {label} diff escaped selected records")
    expected_family = None
    if group_add:
        expected_family = GRAYEXT_VARIANTS[mask]
    elif record_subset is not None:
        expected_family = RECORD_SUBSET_ADD_VARIANTS[record_subset]
    elif record_add is not None:
        expected_family = SINGLE_RECORD_ADD_VARIANTS[record_add]
    if expected_family is not None:
        if len(diff) != expected_family["diff_bytes"]:
            raise RuntimeError(
                f"{label} diff count {len(diff)} != pinned {expected_family['diff_bytes']}"
            )
        if _sha256(variant_bytes) != expected_family["r20_sha256"]:
            raise RuntimeError(f"{label} R20 SHA-256 differs from pinned value")

    report = {
        "schema_version": 1,
        "kind": "mf1750-wf-wmask-generation",
        "variant_id": f"WMASK_{label}_WHITE_RECORDS_{'_'.join(map(str, records))}_COMMENTED",
        "mask_hex": f"0x{mask_label(mask)}",
        "mask_bit_mapping": {"bit0": 4, "bit1": 5, "bit2": 6, "bit3": 7},
        "commented_records": records,
        "active_white_records": [record for record in range(8) if record not in records],
        "selected_spans": [list(span) for span in selected_spans],
        "tag": tag(mask, group_add, record_add, record_subset),
        "env": env_name(mask, group_add, record_add, record_subset),
        "active_r20_sha256": _sha256(active),
        "commented_r20_sha256": _sha256(commented),
        "r20_sha256": _sha256(variant_bytes),
        "pwr_sha256": _sha256(pwr),
        "pll_sha256": _sha256(pll),
        "r21_sha256": _sha256(active_r21),
        "pwr_payload": list(pwr),
        "pll_payload": list(pll),
        "r20_payload": list(variant_bytes),
        "diff_offsets": diff,
        "diff_byte_count_vs_active": len(diff),
        "r21": "active 704 x 0xFF, uploaded directly from the active reference",
        "assertions": {
            "selected_records_exactly_commented": True,
            "every_other_r20_byte_exactly_active": True,
            "pwr_exactly_active_and_r20_mirror": True,
            "pll_exactly_active_0x02_and_r20_mirror": True,
            "r21_active_and_commented_both_704_x_ff": True,
            "diff_confined_to_selected_records": True,
        },
    }
    if group_add:
        report.update({
            "family_label": label,
            "base_mask_hex": f"0x{mask_label(mask)}",
            "records0_3_group_add": True,
            "family_label_is_not_bitmask": True,
            "group_add_records": sorted(GROUP_ADD_RECORDS),
            "expected_diff_byte_count_vs_active": expected_family["diff_bytes"],
            "expected_r20_sha256": expected_family["r20_sha256"],
        })
        report["assertions"].update({
            "grayext_family_is_explicit_base_plus_records0_3_group": True,
            "grayext_diff_byte_count_matches_pin": True,
            "grayext_r20_sha256_matches_pin": True,
        })
    elif record_subset is not None:
        report.update({
            "family_label": label,
            "base_mask_hex": f"0x{mask_label(mask)}",
            "record_subset_add": list(record_subset),
            "family_label_is_not_bitmask": True,
            "expected_diff_byte_count_vs_active": expected_family["diff_bytes"],
            "expected_r20_sha256": expected_family["r20_sha256"],
        })
        report["assertions"].update({
            "record_subset_add_family_is_explicit_base_plus_subset": True,
            "record_subset_add_diff_byte_count_matches_pin": True,
            "record_subset_add_r20_sha256_matches_pin": True,
        })
    elif record_add is not None:
        report.update({
            "family_label": label,
            "base_mask_hex": f"0x{mask_label(mask)}",
            "single_record_add": record_add,
            "family_label_is_not_bitmask": True,
            "expected_diff_byte_count_vs_active": expected_family["diff_bytes"],
            "expected_r20_sha256": expected_family["r20_sha256"],
        })
        report["assertions"].update({
            "single_record_add_family_is_explicit_base_plus_one_record": True,
            "single_record_add_diff_byte_count_matches_pin": True,
            "single_record_add_r20_sha256_matches_pin": True,
        })

    driver_template = DRIVER_TEMPLATE_PATH.read_text(encoding="utf-8")
    runtime_tail = driver_template[driver_template.index("namespace {"):]
    main_template = MAIN_TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = {
        "include": _render_include(mask, report, group_add, record_add, record_subset),
        "driver": _render_driver(mask, runtime_tail, group_add, record_add, record_subset),
        "main": _render_main(mask, main_template, group_add, record_add, record_subset),
    }
    if rendered["driver"][rendered["driver"].index("namespace {"):] != runtime_tail:
        raise RuntimeError(f"mask/family {label} PSR/runtime tail differs from R2G")
    report["runtime_tail_sha256"] = _sha256(runtime_tail.encode("utf-8"))
    report["r2g_runtime_tail_sha256"] = _sha256(runtime_tail.encode("utf-8"))
    report["assertions"]["psr_and_runtime_tail_byte_identical_to_r2g"] = True
    report["compile_time_assertions"] = {
        "all_535_r20_bytes_match_mask_sources": True,
        "all_6_pwr_bytes_equal_active_and_mirror_r20": True,
        "pll_equals_active_0x02_and_r20_6": True,
        "all_704_active_r21_bytes_equal_ff": True,
    }
    if group_add:
        report["compile_time_assertions"]["records0_3_group_flag_and_base_mask"] = True
    elif record_subset is not None:
        report["compile_time_assertions"]["record_subset_add_identities_and_base_mask"] = True
    elif record_add is not None:
        report["compile_time_assertions"]["single_record_add_identity_and_base_mask"] = True
    for kind, content in rendered.items():
        report[f"{kind}_content_lf_sha256"] = _sha256(content.encode("utf-8"))
    del report["r20_payload"]
    return report, rendered


def generate_sources(
    mask: int,
    group_add: bool = False,
    record_add: int | None = None,
    record_subset: tuple[int, ...] | None = None,
) -> dict:
    report, rendered = build_offline_variant(mask, group_add, record_add, record_subset)
    paths = source_paths(mask, group_add, record_add, record_subset)
    for kind, content in rendered.items():
        _write_generated(paths[kind], content)
    for kind, path in paths.items():
        if _sha256(path.read_bytes()) != report[f"{kind}_content_lf_sha256"]:
            raise RuntimeError(f"on-disk {kind} hash differs after generation: {path}")
        report[f"{kind}_path"] = path.relative_to(ROOT).as_posix()
    return report


def _parse_record_subset(value: str) -> tuple[int, ...]:
    try:
        subset = tuple(int(part, 10) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("record subset must be comma-separated integers") from error
    if subset not in RECORD_SUBSET_ADD_VARIANTS:
        raise argparse.ArgumentTypeError(
            "record subset must be one of 0,1 / 0,2 / 0,3"
        )
    return subset


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mask", help="one pending low-4-bit base mask (for example 0A)")
    group.add_argument("--all", action="store_true", help="generate all pending masks (default)")
    parser.add_argument(
        "--group-add",
        action="store_true",
        help="add the whole White records 0-3 group; with --all generates GrayExt 1E/1C/1D",
    )
    parser.add_argument(
        "--record-add",
        type=int,
        choices=SINGLE_RECORD_ADD_RECORDS,
        help="with --mask 0E, add exactly one White record 0, 1, 2, or 3",
    )
    parser.add_argument(
        "--record-subset",
        type=_parse_record_subset,
        help="with --mask 0E, add one registered R0-anchored pair such as 0,1",
    )
    args = parser.parse_args(argv)
    selected_modes = int(args.group_add) + int(args.record_add is not None) + int(args.record_subset is not None)
    if selected_modes > 1:
        parser.error("--group-add, --record-add, and --record-subset are mutually exclusive")
    if args.record_add is not None and not args.mask:
        parser.error("--record-add requires --mask 0E")
    if args.record_subset is not None and not args.mask:
        parser.error("--record-subset requires --mask 0E")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mask:
        masks = (int(args.mask, 16),)
    elif args.group_add:
        masks = GRAYEXT_BASE_MASKS
    else:
        masks = PENDING_MASKS
    reports = [
        generate_sources(mask, args.group_add, args.record_add, args.record_subset)
        for mask in masks
    ]
    print(json.dumps({
        "schema_version": 1,
        "records0_3_group_add": args.group_add,
        "single_record_add": args.record_add,
        "record_subset_add": list(args.record_subset) if args.record_subset is not None else None,
        "family_labels_are_not_bitmasks": (
            args.group_add or args.record_add is not None or args.record_subset is not None
        ),
        "variant_count": len(reports),
        "variants": reports,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
