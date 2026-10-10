#!/usr/bin/env python3
"""Generate identity-pinned C++ profiles from the two complete legacy LUTs.

The source is the vendor-delivered ``User/EDP_init.c``.  It contains one
active 535-byte initializer and one complete commented-out 535-byte table.
This generator preserves each table as a whole.  It never mutates a record,
mixes categories, or invents a controller command.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_spd1657_record_semantics_audit as record_audit  # noqa: E402


SOURCE_SHA256 = record_audit.LEGACY_SOURCE_SHA256
R21_BYTES = 704
R20_STORAGE_BYTES = 799


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array(data: bytes, *, width: int = 16) -> str:
    rows = []
    for offset in range(0, len(data), width):
        row = ", ".join(f"0x{value:02X}" for value in data[offset : offset + width])
        rows.append(f"    {row},")
    return "\n".join(rows)


def _profile(namespace: str, source_role: str, payload: bytes) -> str:
    if len(payload) != 535:
        raise ValueError(f"{source_role} payload length changed")
    header = payload[:7]
    r20 = payload + bytes([0xFF]) * (R20_STORAGE_BYTES - len(payload))
    r21 = bytes([0xFF]) * R21_BYTES
    decoded = r20 + b"\x00"
    power = bytes([0x0F]) + header[:5]
    pll = header[6:7]
    return f"""namespace {namespace} {{

static constexpr char kSourceRole[] = "{source_role}";
static constexpr char kSourceArtifactSha256[] = "{SOURCE_SHA256}";
static constexpr char kDecodedPlaintextSha256[] = "{_sha(decoded)}";
static constexpr char kDecodedHeaderSha256[] = "{_sha(header)}";
static constexpr char kPowerPayloadSha256[] = "{_sha(power)}";
static constexpr char kPllPayloadSha256[] = "{_sha(pll)}";
static constexpr char kR20PayloadSha256[] = "{_sha(r20)}";
static constexpr char kR21PayloadSha256[] = "{_sha(r21)}";
static constexpr char kTransmittedR20PrefixSha256[] = "{_sha(payload)}";

static constexpr bool kEmpiricalH3 = true;
static constexpr bool kLiveAuthorized = false;
static constexpr bool kProfileAutoSelected = false;
static constexpr bool kContainsHardwareIo = false;
static constexpr bool kPanelOrFplLimitsProven = false;
static constexpr bool kH3HeaderBindingProven = false;
static constexpr bool kR21IsAllFf = true;
static constexpr bool kDecodedPaddingSentinelWasZero = true;
static constexpr bool kDecodedHeaderByte5IsLegacyVcomSlot = true;
static constexpr bool kDecodedHeaderByte5WrittenByCurrentArmccLoader = false;
static constexpr bool kLegacyCompleteTablePreserved = true;
static constexpr bool kLegacySourceSequenceUsesR20Only = true;
static constexpr bool kArmccAdjacentLoaderAddsR21AllFf = true;

static constexpr std::size_t kDecodedBytes = 800;
static constexpr std::size_t kHeaderBytes = 7;
static constexpr std::size_t kPowerPayloadBytes = 6;
static constexpr std::size_t kPllPayloadBytes = 1;
static constexpr std::size_t kR20PayloadBytes = 799;
static constexpr std::size_t kTransmittedR20PrefixBytes = 535;
static constexpr std::size_t kR21PayloadBytes = 704;
static constexpr std::size_t kDecodedPaddingOffset = 799;

static constexpr std::uint8_t kPowerCommand = 0x01;
static constexpr std::uint8_t kPllCommand = 0x30;
static constexpr std::uint8_t kR20Command = 0x20;
static constexpr std::uint8_t kR21Command = 0x21;
static constexpr int kApparentTemperatureMinC = -128;
static constexpr int kApparentTemperatureMaxC = 127;
static constexpr int kRequestedGatePositiveMv = 20000;
static constexpr int kRequestedGateNegativeMv = -20000;
static constexpr int kRequestedFullSourcePositiveMv = 15000;
static constexpr int kRequestedFullSourceNegativeMv = -15000;
static constexpr int kRequestedVshLvMv = 3000 + 100 * 0x{header[1]:02X};
static constexpr int kRequestedVslLvMv = -(3000 + 100 * 0x{header[2]:02X});
static constexpr int kRequestedVshLv2Mv = 3000 + 100 * 0x{header[3]:02X};
static constexpr int kRequestedVslLv2Mv = -(3000 + 100 * 0x{header[4]:02X});
static constexpr unsigned kRequestedFrameRateHz = 0;

static constexpr std::uint8_t kDecodedHeader[7] = {{
{_array(header)}
}};
static constexpr std::uint8_t kPowerPayload[6] = {{
{_array(power)}
}};
static constexpr std::uint8_t kPllPayload[1] = {{
{_array(pll)}
}};
static constexpr std::uint8_t kR20Payload[799] = {{
{_array(r20)}
}};
static constexpr std::uint8_t kR21Payload[704] = {{
{_array(r21)}
}};

static_assert(sizeof(kR20Payload) == kR20PayloadBytes, "R20 storage changed");
static_assert(sizeof(kR21Payload) == kR21PayloadBytes, "R21 storage changed");
static_assert(kTransmittedR20PrefixBytes == 7 + 6 * 8 * 11,
              "legacy 535-byte geometry changed");

}}  // namespace {namespace}
"""


def render() -> bytes:
    parsed = record_audit._parse_source_tables()  # noqa: SLF001
    payloads = parsed["payloads"]
    active = payloads["active"]
    commented = payloads["commented"]
    if _sha(active) != record_audit.ACTIVE_535_SHA256:
        raise ValueError("active legacy table identity changed")
    if _sha(commented) != record_audit.COMMENTED_535_SHA256:
        raise ValueError("commented legacy table identity changed")
    text = """#pragma once

#include <cstddef>
#include <cstdint>

// Generated from the two complete, identity-pinned 535-byte tables in the
// vendor-delivered EDP_init.c.  The 264-byte 0xFF suffix exists only so this
// evidence can share the fixed 799-byte validation container; Stage-III
// reference builds transmit exactly the first 535 R20 bytes.

namespace mf1750::runtime_lut::legacy_reference {

"""
    text += _profile("active", "compiled_active_initializer", active)
    text += "\n"
    text += _profile("commented", "complete_commented_table", commented)
    text += "\n}  // namespace mf1750::runtime_lut::legacy_reference\n"
    return text.encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    wanted = render()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != wanted:
            print("legacy reference include differs")
            return 2
        print(hashlib.sha256(wanted).hexdigest())
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != wanted:
        raise SystemExit("refusing to overwrite a differing generated include")
    args.output.write_bytes(wanted)
    print(hashlib.sha256(wanted).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
