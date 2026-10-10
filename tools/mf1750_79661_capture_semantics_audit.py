#!/usr/bin/env python3
"""Audit the vendor ``79661.csv`` SPI-analyzer export offline.

The CSV contains decoded byte rows, not logic edges.  This identity-pinned
audit fixes its schema, timestamp sequence, MOSI/MISO identities, and timing
bursts; compares every possible contiguous window with the locally proven
535/704/799/800/1503-byte references; and checks the only adjacent project
residue.  It emits hashes and geometry only, never captured bytes.

The tool deliberately does not infer D/C, chip-select, controller, or
transaction boundaries from byte values or timing gaps.  It has no hardware,
serial, network, flash, refresh, token, or claim path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Final, Iterable
import xml.etree.ElementTree as ET


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_armcc_mode1_residual_audit as residual  # noqa: E402
from tools import mf1750_iar_data0_data1_compatibility_audit as iar_arrays  # noqa: E402
from tools import mf1750_iar_r43_cross_object_graph as iar_graph  # noqa: E402
from tools import mf1750_spd1657_waveform_invariant_stats as stats  # noqa: E402


KIND: Final = "mf1750-79661-capture-semantics-audit"
SCHEMA_VERSION: Final = 2

DEFAULT_REFERENCE_ROOT: Final = residual.DEFAULT_STM32_ROOT
DEFAULT_CAPTURE: Final = DEFAULT_REFERENCE_ROOT / residual.CAPTURE_REL
DEFAULT_IAR_ROOT: Final = iar_graph.DEFAULT_IAR_ROOT

CAPTURE_BYTES: Final = 370_580
CAPTURE_SHA256: Final = (
    "3dd08472fc1fc75866381c6963a2cf35787c712aaa8ff8256687ec86bcac159d"
)
CAPTURE_HEADER: Final = b"Time [s],Packet ID,MOSI,MISO"
CAPTURE_ROWS: Final = 12_722
ROW_RE: Final = re.compile(
    rb"(?P<time>[0-9]+\.[0-9]{10}),(?P<packet>[0-9]+),"
    rb"0x(?P<mosi>[0-9A-F]{2}),0x(?P<miso>[0-9A-F]{2})"
)

EXPECTED_COLUMN_TEXT_SHA256: Final = {
    "Time [s]": "d826e5c54c6e638f9f88a7f42d5a728ef05c1d38484665db46407798e363de51",
    "Packet ID": "5a12886515c8589311114503e8fdba1d3a923ade41c35db540896de24204dcc0",
    "MOSI": "9362d264d1179a9ce1e2c04999f99c766d5a927b96c1768a7ac91400cd1020a2",
    "MISO": "3e7b6309b1b1dba943a0091783a1c90010f023afe28deca523119fd04b526951",
}
EXPECTED_MOSI_SHA256: Final = (
    "57a526c1c5fe0559849ce3df425265fffd7692f25e0305d468b4a4d4985cad19"
)
EXPECTED_MISO_SHA256: Final = (
    "3161fce47232b051d3dc14a2f49d8d70089581fbe5dcefb6999061e56e45c89d"
)

E6_SOURCE_REL: Final = Path(
    "../../E6_73_sample code_V1.2_20250116/E6_73_sample code_V1.2_20250116/E6_73.c"
)
E6_HEADER_REL: Final = Path(
    "../../E6_73_sample code_V1.2_20250116/E6_73_sample code_V1.2_20250116/E6_73.h"
)
PINNED_LOCAL_FILES: Final = {
    E6_SOURCE_REL: (
        9_182,
        "8f511aca743bcd55d751d6d935261733b5931eb2fa101bb6d9f815cd0a8b06e9",
    ),
    E6_HEADER_REL: (
        1_765,
        "56188e68ead9c42d4a86ff0ca6553216921f0fa513a7cd3b816f47eeb718b660",
    ),
    Path("User/IC_drive_code.c"): (
        23_018,
        "20f0094d4e6a0ef1bc6a5a2cd454adb005904081bf4b3cc01ba0790223bc7f51",
    ),
    Path("User/EDP_init.c"): (
        32_220,
        "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5",
    ),
    residual.PROJECT_REL: residual.EXPECTED_IDENTITIES[residual.PROJECT_REL],
    residual.ZHANG_GUI_REL: residual.EXPECTED_IDENTITIES[residual.ZHANG_GUI_REL],
}

# E6_73.c EPD_Init flattened in call order, with D/C deliberately discarded.
E6_INIT_FLAT: Final = bytes.fromhex(
    "aa495520080918013f005f6905401f1f2c086f1f1f22066f1f1717"
    "03005400446002003008503f61032001e0e32f8401"
)
E6_INIT_FLAT_SHA256: Final = (
    "d6f720555ef43754f7e7aa41f67f5f1baada6953844a4113ee1403aae11f1ff8"
)

# Public-source cross-check acquired once through the explicitly authorized,
# immutable raw GitHub URLs.  Normal report generation remains offline: it
# pins the observed file identities and compares only the derived metadata and
# byte sequence below.  The public source itself is never reproduced.
GXEPD2_COMMIT: Final = "de82887e77a78528ea386e68bba2cb0291d2c319"
GXEPD2_SOURCE_URL: Final = (
    "https://raw.githubusercontent.com/ZinggJM/GxEPD2/"
    f"{GXEPD2_COMMIT}/src/epd4c/GxEPD2_213c_GDEY0213F51.cpp"
)
GXEPD2_HEADER_URL: Final = (
    "https://raw.githubusercontent.com/ZinggJM/GxEPD2/"
    f"{GXEPD2_COMMIT}/src/epd4c/GxEPD2_213c_GDEY0213F51.h"
)
GXEPD2_PUBLIC_IDENTITIES: Final = {
    "GxEPD2_213c_GDEY0213F51.cpp": (
        31_749,
        "a1ed92b7c8a33da2f2b9ae74c75d0f904275e78cd8304676aed8942dc5cd00b3",
    ),
    "GxEPD2_213c_GDEY0213F51.h": (
        5_551,
        "e92dbb60af5a8766da4497150bef0e0b9f7ec2d44d935b1c7b93546f2d1d2ccf",
    ),
}
GXEPD2_WIDTH: Final = 128
GXEPD2_WIDTH_VISIBLE: Final = 122
GXEPD2_HEIGHT: Final = 250
GXEPD2_FULL_BUFFER_BYTES: Final = GXEPD2_WIDTH * GXEPD2_HEIGHT // 4
GXEPD2_INIT_GROUPS: Final = (
    bytes.fromhex("4D78"),
    bytes.fromhex("000F29"),
    bytes.fromhex("010700"),
    bytes.fromhex("03105444"),
    bytes.fromhex("0605003F0A25121A"),
    bytes.fromhex("5037"),
    bytes.fromhex("600202"),
    bytes.fromhex("61008000FA"),
    bytes.fromhex("E71C"),
    bytes.fromhex("E322"),
    bytes.fromhex("B4D0"),
    bytes.fromhex("B503"),
    bytes.fromhex("E901"),
    bytes.fromhex("3008"),
    bytes.fromhex("04"),
)
GXEPD2_INIT_FLAT: Final = b"".join(GXEPD2_INIT_GROUPS)
GXEPD2_INIT_FLAT_SHA256: Final = (
    "04cce44a9404bab088ceb54e12cdde51a495804622a5316a29c7fd0e649d1a32"
)

TIMING_THRESHOLD_TICKS: Final = 1_000_000  # 100 us in 0.1 ns ticks.
TARGET_LENGTHS: Final = (535, 704, 799, 800, 1503)
EXTERNAL_PROJECT_TAIL: Final = "WF-JD79661-128X296"


class CaptureSemanticsAuditError(RuntimeError):
    """A pinned identity or semantic invariant changed."""


@dataclass(frozen=True)
class Capture:
    payload: bytes
    times_text: tuple[str, ...]
    time_ticks: tuple[int, ...]
    packet_ids: tuple[int, ...]
    packet_text: tuple[str, ...]
    mosi: bytes
    mosi_text: tuple[str, ...]
    miso: bytes
    miso_text: tuple[str, ...]


@dataclass(frozen=True)
class ReferencePayload:
    name: str
    payload: bytes
    provenance: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureSemanticsAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pin(path: Path, expected: tuple[int, str], label: str) -> bytes:
    _require(path.is_file() and not path.is_symlink(), f"{label} is missing")
    payload = path.read_bytes()
    _require(len(payload) == expected[0], f"{label} byte length changed")
    _require(_sha256(payload) == expected[1], f"{label} SHA-256 changed")
    return payload


def _time_to_ticks(value: bytes) -> int:
    whole, fraction = value.split(b".", 1)
    _require(len(fraction) == 10, "timestamp precision changed")
    return int(whole) * 10_000_000_000 + int(fraction)


def _column_hash(values: Iterable[str]) -> str:
    return _sha256(("\n".join(values) + "\n").encode("ascii"))


def load_capture(path: Path = DEFAULT_CAPTURE) -> Capture:
    """Load only the exact, immutable analyzer export."""

    payload = _pin(path, (CAPTURE_BYTES, CAPTURE_SHA256), "79661.csv")
    _require(payload.endswith(b"\r\n"), "capture no longer ends with CRLF")
    _require(payload.count(b"\r\n") == CAPTURE_ROWS + 1, "CRLF count changed")
    _require(payload.count(b"\n") == CAPTURE_ROWS + 1, "LF count changed")
    _require(payload.count(b"\r") == CAPTURE_ROWS + 1, "CR count changed")
    lines = payload.split(b"\r\n")
    _require(lines[-1] == b"", "capture has trailing non-row bytes")
    _require(lines[0] == CAPTURE_HEADER, "capture header changed")
    rows = lines[1:-1]
    _require(len(rows) == CAPTURE_ROWS, "capture row count changed")

    times_text: list[str] = []
    ticks: list[int] = []
    packet_ids: list[int] = []
    packet_text: list[str] = []
    mosi = bytearray()
    mosi_text: list[str] = []
    miso = bytearray()
    miso_text: list[str] = []
    for ordinal, row in enumerate(rows):
        match = ROW_RE.fullmatch(row)
        _require(match is not None, f"capture row {ordinal} is not canonical")
        assert match is not None
        time_raw = match.group("time")
        packet_raw = match.group("packet")
        mosi_raw = match.group("mosi")
        miso_raw = match.group("miso")
        packet = int(packet_raw)
        _require(packet == ordinal, f"Packet ID {ordinal} is not zero-based contiguous")
        times_text.append(time_raw.decode("ascii"))
        ticks.append(_time_to_ticks(time_raw))
        packet_ids.append(packet)
        packet_text.append(packet_raw.decode("ascii"))
        mosi.append(int(mosi_raw, 16))
        mosi_text.append("0x" + mosi_raw.decode("ascii"))
        miso.append(int(miso_raw, 16))
        miso_text.append("0x" + miso_raw.decode("ascii"))

    _require(
        all(right > left for left, right in zip(ticks, ticks[1:])),
        "timestamps are not strictly increasing",
    )
    observed_columns = {
        "Time [s]": _column_hash(times_text),
        "Packet ID": _column_hash(packet_text),
        "MOSI": _column_hash(mosi_text),
        "MISO": _column_hash(miso_text),
    }
    _require(
        observed_columns == EXPECTED_COLUMN_TEXT_SHA256, "column text identity changed"
    )
    _require(_sha256(bytes(mosi)) == EXPECTED_MOSI_SHA256, "MOSI identity changed")
    _require(_sha256(bytes(miso)) == EXPECTED_MISO_SHA256, "MISO identity changed")
    return Capture(
        payload=payload,
        times_text=tuple(times_text),
        time_ticks=tuple(ticks),
        packet_ids=tuple(packet_ids),
        packet_text=tuple(packet_text),
        mosi=bytes(mosi),
        mosi_text=tuple(mosi_text),
        miso=bytes(miso),
        miso_text=tuple(miso_text),
    )


def _sequence_occurrences(haystack: bytes, needle: bytes) -> int:
    _require(bool(needle), "empty reference sequence")
    count = 0
    start = 0
    while True:
        offset = haystack.find(needle, start)
        if offset < 0:
            return count
        count += 1
        start = offset + 1


def _fragment_set(left: bytes, right: bytes, length: int) -> set[bytes]:
    if length == 0:
        return {b""}
    left_windows = {
        left[index : index + length] for index in range(len(left) - length + 1)
    }
    return {
        right[index : index + length]
        for index in range(len(right) - length + 1)
        if right[index : index + length] in left_windows
    }


def _common_fragment_metadata(left: bytes, right: bytes) -> dict[str, Any]:
    low = 0
    high = min(len(left), len(right))
    while low < high:
        candidate = (low + high + 1) // 2
        if _fragment_set(left, right, candidate):
            low = candidate
        else:
            high = candidate - 1
    fragments = _fragment_set(left, right, low)
    digests = sorted(hashlib.sha256(fragment).digest() for fragment in fragments)
    capture_offsets = sum(
        left[index : index + low] in fragments for index in range(len(left) - low + 1)
    )
    reference_offsets = sum(
        right[index : index + low] in fragments for index in range(len(right) - low + 1)
    )
    unique_counts = [len(set(fragment)) for fragment in fragments]
    return {
        "longest_common_contiguous_fragment_bytes": low,
        "distinct_maximal_fragments": len(fragments),
        "capture_offsets_at_maximum": capture_offsets,
        "reference_offsets_at_maximum": reference_offsets,
        "maximal_fragment_digest_set_sha256": _sha256(b"".join(digests)),
        "maximal_fragment_unique_byte_count_min": min(unique_counts),
        "maximal_fragment_unique_byte_count_max": max(unique_counts),
        "raw_fragment_bytes_emitted": False,
    }


def _longest_common_subsequence_length(left: bytes, right: bytes) -> int:
    previous = [0] * (len(right) + 1)
    for left_value in left:
        current = [0]
        for index, right_value in enumerate(right, 1):
            if left_value == right_value:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _longest_value_run(payload: bytes, value: int) -> int:
    longest = 0
    current = 0
    for observed in payload:
        current = current + 1 if observed == value else 0
        longest = max(longest, current)
    return longest


def _timing_report(capture: Capture) -> dict[str, Any]:
    deltas = [
        right - left for left, right in zip(capture.time_ticks, capture.time_ticks[1:])
    ]
    _require(all(delta > 0 for delta in deltas), "non-positive time delta")
    large_indices = [
        index + 1
        for index, delta in enumerate(deltas)
        if delta > TIMING_THRESHOLD_TICKS
    ]
    boundaries = [0, *large_indices, len(capture.mosi)]
    runs = [capture.mosi[start:end] for start, end in zip(boundaries, boundaries[1:])]
    lengths = [len(run) for run in runs]
    run_hashes = [_sha256(run) for run in runs]
    short = [delta for delta in deltas if delta <= TIMING_THRESHOLD_TICKS]
    large = [delta for delta in deltas if delta > TIMING_THRESHOLD_TICKS]
    _require(
        lengths
        == [57, 7, 2, 2, 6321, 4, 2, 543, 3, 1024, 1024, 1024, 1024, 1024, 657, 4],
        "timing-run geometry changed",
    )
    _require(max(short) == 845_000, "largest intra-run delta changed")
    _require(min(large) == 9_790_000, "smallest inter-run delta changed")
    delta_encoding = b"".join(delta.to_bytes(8, "big") for delta in deltas)
    return {
        "timestamp_unit": "seconds with exactly 10 fractional decimal digits",
        "integer_tick_unit_seconds": "1e-10",
        "first_timestamp": capture.times_text[0],
        "last_timestamp": capture.times_text[-1],
        "duration_ticks": capture.time_ticks[-1] - capture.time_ticks[0],
        "delta_count": len(deltas),
        "delta_big_endian_u64_sha256": _sha256(delta_encoding),
        "segmentation_threshold_ticks": TIMING_THRESHOLD_TICKS,
        "segmentation_threshold_microseconds": 100,
        "largest_intra_run_delta_ticks": max(short),
        "smallest_inter_run_delta_ticks": min(large),
        "large_gap_count": len(large),
        "timing_run_count": len(runs),
        "timing_run_lengths": lengths,
        "timing_run_sha256": run_hashes,
        "timing_run_lengths_matching_declared_payload_sizes": {
            str(length): lengths.count(length) for length in TARGET_LENGTHS
        },
        "timing_run_lengths_matching_command_plus_payload_sizes": {
            str(length + 1): lengths.count(length + 1) for length in TARGET_LENGTHS
        },
        "timing_gaps_are_transaction_boundaries_proven": False,
        "timing_runs_are_spi_transactions_proven": False,
    }


def _gxepd2_public_source_cross_check(
    capture: Capture,
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Compare capture metadata with the pinned public JD79661 example."""

    _require(len(GXEPD2_INIT_FLAT) == 43, "public init flattening length changed")
    _require(
        _sha256(GXEPD2_INIT_FLAT) == GXEPD2_INIT_FLAT_SHA256,
        "public init flattening identity changed",
    )
    _require(GXEPD2_FULL_BUFFER_BYTES == 8_000, "public buffer geometry changed")

    first_run_length = timing["timing_run_lengths"][0]
    first_run = capture.mosi[:first_run_length]
    group_offsets = [first_run.find(group) for group in GXEPD2_INIT_GROUPS]
    matched_offsets = [offset for offset in group_offsets if offset >= 0]
    _require(len(matched_offsets) == 10, "public init group compatibility changed")
    _require(
        _longest_common_subsequence_length(first_run, GXEPD2_INIT_FLAT) == 33,
        "public init subsequence compatibility changed",
    )

    fragment = _common_fragment_metadata(capture.mosi, GXEPD2_INIT_FLAT)
    _require(
        fragment["longest_common_contiguous_fragment_bytes"] == 12,
        "public init common-fragment length changed",
    )
    _require(
        fragment["distinct_maximal_fragments"] == 1,
        "public init maximal-fragment multiplicity changed",
    )
    maximal_length = fragment["longest_common_contiguous_fragment_bytes"]
    maximal_fragments = _fragment_set(
        capture.mosi,
        GXEPD2_INIT_FLAT,
        maximal_length,
    )
    maximal_fragment = next(iter(maximal_fragments))
    capture_offset = capture.mosi.find(maximal_fragment)
    source_offset = GXEPD2_INIT_FLAT.find(maximal_fragment)
    _require(
        (capture_offset, source_offset) == (14, 8),
        "public init maximal-fragment placement changed",
    )

    default_white_encoding = b"\x55" * GXEPD2_FULL_BUFFER_BYTES
    default_white_matches = _sequence_occurrences(
        capture.mosi,
        default_white_encoding,
    )
    longest_default_white_run = _longest_value_run(capture.mosi, 0x55)
    _require(default_white_matches == 0, "complete public white write appeared")
    _require(longest_default_white_run == 5_776, "default-white run changed")
    _require(capture.mosi.count(0x55) == 11_552, "default-white byte count changed")

    identities = {
        filename: {"bytes": identity[0], "sha256": identity[1]}
        for filename, identity in GXEPD2_PUBLIC_IDENTITIES.items()
    }
    return {
        "provenance": {
            "repository": "ZinggJM/GxEPD2",
            "commit": GXEPD2_COMMIT,
            "source_url": GXEPD2_SOURCE_URL,
            "header_url": GXEPD2_HEADER_URL,
            "file_identities": identities,
            "immutable_commit_pinned": True,
            "identity_observed_in_explicitly_authorized_public_read": True,
            "identity_revalidated_by_current_offline_execution": False,
            "report_generation_performs_network_io": False,
        },
        "declared_target": {
            "panel": "GDEY0213F51",
            "controller": "JD79661",
            "width": GXEPD2_WIDTH,
            "visible_width": GXEPD2_WIDTH_VISIBLE,
            "height": GXEPD2_HEIGHT,
            "two_bits_per_pixel_full_buffer_bytes": GXEPD2_FULL_BUFFER_BYTES,
            "external_editor_residue_height": 296,
            "same_dimensions_as_external_editor_residue": False,
        },
        "flattened_init_cross_check": {
            "source_command_groups": len(GXEPD2_INIT_GROUPS),
            "flattened_command_plus_parameter_bytes": len(GXEPD2_INIT_FLAT),
            "flattened_sha256": GXEPD2_INIT_FLAT_SHA256,
            "exact_contiguous_match_count": _sequence_occurrences(
                capture.mosi,
                GXEPD2_INIT_FLAT,
            ),
            "first_timing_run_bytes": first_run_length,
            "exact_source_groups_present_in_first_timing_run": len(matched_offsets),
            "longest_common_subsequence_bytes_in_first_timing_run": 33,
            "all_matched_source_groups_retain_source_order": matched_offsets
            == sorted(matched_offsets),
            "maximal_fragment_capture_offset": capture_offset,
            "maximal_fragment_source_offset": source_offset,
            **fragment,
            "flattening_discards_dc": True,
            "fragment_is_positive_controller_family_compatibility": True,
            "fragment_proves_exact_generator_or_panel": False,
            "fragment_proves_command_data_roles_in_capture": False,
        },
        "default_screen_buffer_cross_check": {
            "source_full_buffer_transfer_bytes": GXEPD2_FULL_BUFFER_BYTES,
            "source_default_white_encoded_value_count": GXEPD2_FULL_BUFFER_BYTES,
            "exact_default_white_transfer_match_count": default_white_matches,
            "capture_longest_contiguous_default_white_value_run": (
                longest_default_white_run
            ),
            "capture_total_default_white_encoded_value_count": capture.mosi.count(0x55),
            "timing_run_length_8000_count": timing["timing_run_lengths"].count(8_000),
            "timing_run_length_8001_count": timing["timing_run_lengths"].count(8_001),
            "exact_source_default_screen_write_present": False,
            "capture_completeness_proven": False,
        },
        "adjudication": {
            "jd79661_init_fragment_compatibility_present": True,
            "exact_flattened_public_init_present": False,
            "exact_public_default_screen_write_sequence_present": False,
            "public_source_binds_capture_to_exact_panel": False,
            "public_source_restores_full_transactions": False,
        },
        "raw_public_init_or_capture_bytes_emitted": False,
    }


def _load_reference_payloads(iar_root: Path) -> list[ReferencePayload]:
    datasets = stats._load_datasets()
    references: list[ReferencePayload] = [
        ReferencePayload(
            "legacy_wf_data_535",
            datasets["legacy_wf_data_535"].payload,
            "identity-pinned delivered User/EDP_init.c initializer",
        ),
        ReferencePayload(
            "legacy_iar_data1_704",
            datasets["legacy_iar_data1_704"].payload,
            "identity-pinned E2802.r43 DATA1",
        ),
        ReferencePayload(
            "ff_704",
            datasets["armcc_lut1_704"].payload,
            "byte-identical ArmCC LUT1 and legacy IAR DATA0 tail",
        ),
    ]
    for profile_id in ("WF20_25", "WF23_25"):
        plain = datasets[profile_id].payload
        references.extend(
            (
                ReferencePayload(
                    f"{profile_id}_plain_800",
                    plain,
                    "identity-pinned decoded vendor profile",
                ),
                ReferencePayload(
                    f"{profile_id}_first_535",
                    plain[:535],
                    "mode-0 structural slice candidate",
                ),
                ReferencePayload(
                    f"{profile_id}_first_799",
                    plain[:799],
                    "H3 R20 structural candidate",
                ),
                ReferencePayload(
                    f"{profile_id}_overlap_704",
                    plain[95:799],
                    "H1 R21 structural candidate",
                ),
                ReferencePayload(
                    f"{profile_id}_extension_704",
                    b"\xff" * 440 + plain[535:799],
                    "H2 R21 structural candidate",
                ),
            )
        )

    contract = iar_arrays.OBJECTS["E2802"]
    object_path = iar_root / iar_graph.OBJECT_DIR_REL / str(contract["filename"])
    object_payload = iar_arrays._pin_object(object_path, contract)
    data0 = iar_arrays._extract_tagged_array(
        object_payload,
        label="E2802.DATA0",
        contract=contract["arrays"]["DATA0"],
    )
    _require(len(data0) == 1503, "legacy IAR DATA0 length changed")
    _require(data0[799:] == b"\xff" * 704, "legacy IAR DATA0 tail changed")
    references.extend(
        (
            ReferencePayload(
                "legacy_iar_data0_1503",
                data0,
                "identity-pinned E2802.r43 retained DATA0",
            ),
            ReferencePayload(
                "legacy_iar_data0_first_799",
                data0[:799],
                "structural slice of retained E2802.r43 DATA0",
            ),
        )
    )
    identities = [
        (item.name, len(item.payload), _sha256(item.payload)) for item in references
    ]
    _require(
        len(identities) == len(set(identities)), "duplicate reference name/identity row"
    )
    return references


def _window_family(
    capture: bytes, length: int, references: list[ReferencePayload]
) -> dict[str, Any]:
    windows = [
        capture[index : index + length] for index in range(len(capture) - length + 1)
    ]
    window_digests = [hashlib.sha256(window).digest() for window in windows]
    wanted = {
        hashlib.sha256(item.payload).digest(): item.name
        for item in references
        if len(item.payload) == length
    }
    matching_names = sorted(
        {wanted[digest] for digest in window_digests if digest in wanted}
    )
    return {
        "window_bytes": length,
        "ordered_window_count": len(windows),
        "distinct_window_sha256_count": len(set(window_digests)),
        "ordered_window_digest_sequence_sha256": _sha256(b"".join(window_digests)),
        "known_reference_count": len(wanted),
        "known_reference_identity_matches": matching_names,
        "known_reference_identity_match_count": len(matching_names),
        "every_possible_contiguous_window_scanned": True,
        "raw_window_bytes_emitted": False,
    }


def _reference_search(
    capture: bytes, references: list[ReferencePayload]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in references:
        exact = _sequence_occurrences(capture, item.payload)
        _require(exact == 0, f"capture unexpectedly contains {item.name}")
        rows.append(
            {
                "name": item.name,
                "bytes": len(item.payload),
                "sha256": _sha256(item.payload),
                "provenance": item.provenance,
                "exact_contiguous_match_count": exact,
                **_common_fragment_metadata(capture, item.payload),
            }
        )
    families = [
        _window_family(capture, length, references) for length in TARGET_LENGTHS
    ]
    _require(
        all(row["known_reference_identity_match_count"] == 0 for row in families),
        "a known payload identity appeared in the capture",
    )
    return {
        "references": rows,
        "capture_window_families": families,
        "any_complete_known_payload_identity_present": False,
        "short_low_diversity_fragment_matches_are_payload_identity": False,
    }


def _strip_c_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\r\n]*", "", text, flags=re.DOTALL)


def _function_body(text: str, name: str) -> str:
    match = re.search(rf"\bvoid\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    _require(match is not None, f"cannot locate {name}")
    assert match is not None
    start = match.end() - 1
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    raise CaptureSemanticsAuditError(f"unterminated {name}")


def _write_call_pattern(body: str) -> list[tuple[str, int | None]]:
    result: list[tuple[str, int | None]] = []
    for match in re.finditer(r"\bEPD_Write(CMD|DATA)\s*\(([^;]+)\)\s*;", body):
        role = match.group(1)
        expression = match.group(2).strip()
        literal = re.fullmatch(r"0[xX]([0-9A-Fa-f]+)|([0-9]+)", expression)
        value = None
        if literal is not None:
            value = (
                int(literal.group(1), 16) if literal.group(1) else int(literal.group(2))
            )
            _require(0 <= value <= 0xFF, "adjacent source literal exceeds one byte")
        result.append((role, value))
    return result


def _adjacent_project_evidence(
    reference_root: Path, capture: Capture
) -> dict[str, Any]:
    pinned: dict[str, dict[str, Any]] = {}
    payloads: dict[Path, bytes] = {}
    for relative, expected in PINNED_LOCAL_FILES.items():
        path = (reference_root / relative).resolve()
        payload = _pin(path, expected, relative.as_posix())
        payloads[relative] = payload
        pinned[relative.as_posix()] = {
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }

    e6_source = payloads[E6_SOURCE_REL].decode("ascii")
    e6_header = payloads[E6_HEADER_REL].decode("ascii")
    _require("void EPD_Init()" in e6_source, "E6 EPD_Init marker changed")
    _require("SPI_COMMAND(0xAA);" in e6_source, "E6 init magic call changed")
    for macro in (
        "PSR",
        "PWR",
        "POFS",
        "BTST1",
        "BTST2",
        "BTST3",
        "PLL",
        "CDI",
        "TCON",
        "TRES",
        "T_VDCS",
        "PWS",
    ):
        _require(
            re.search(rf"#define\s+{macro}\s+0x[0-9A-Fa-f]+", e6_header) is not None,
            f"E6 macro {macro} changed",
        )
    _require(len(E6_INIT_FLAT) == 48, "flattened E6 init length changed")
    _require(
        _sha256(E6_INIT_FLAT) == E6_INIT_FLAT_SHA256,
        "flattened E6 init identity changed",
    )
    e6_matches = _sequence_occurrences(capture.mosi, E6_INIT_FLAT)
    _require(e6_matches == 0, "complete known E6 init unexpectedly appeared")

    editor_payload = payloads[residual.ZHANG_GUI_REL]
    try:
        editor_root = ET.fromstring(editor_payload)
    except ET.ParseError as error:
        raise CaptureSemanticsAuditError("editor-state XML is malformed") from error
    external_names = [
        node.text
        for node in editor_root.iter("Name")
        if node.text and EXTERNAL_PROJECT_TAIL.lower() in node.text.lower()
    ]
    _require(len(external_names) == 5, "external 79661 editor-path count changed")
    external_basenames = sorted(
        Path(name.replace("\\", "/")).name for name in external_names
    )
    _require(
        external_basenames
        == ["EPD_DATA.h", "EPD_init.h", "UartDataDeal.h", "pattern.h", "usart.h"],
        "external 79661 editor-path basenames changed",
    )
    delivered_matching_dirs = [
        path.relative_to(reference_root).as_posix()
        for path in reference_root.rglob("*")
        if path.is_dir() and path.name.lower() == EXTERNAL_PROJECT_TAIL.lower()
    ]
    _require(
        not delivered_matching_dirs, "external 79661 project unexpectedly appeared"
    )
    _require(
        b"79661.csv" not in editor_payload, "editor state now directly names capture"
    )

    adjacent_source = _strip_c_comments(
        payloads[Path("User/IC_drive_code.c")].decode("gb18030")
    )
    adjacent_body = _function_body(adjacent_source, "IC_JD79667_initialCode")
    calls = _write_call_pattern(adjacent_body)
    _require(len(calls) == 55, "adjacent JD79667 init call count changed")
    known_positions = [
        index for index, (_, value) in enumerate(calls) if value is not None
    ]
    _require(len(known_positions) == 51, "adjacent JD79667 static call count changed")
    aligned_matches = sum(
        capture.mosi[index] == calls[index][1] for index in known_positions
    )
    aligned_mismatches = len(known_positions) - aligned_matches
    _require(
        aligned_matches == 15 and aligned_mismatches == 36,
        "adjacent source alignment changed",
    )

    project_text = payloads[residual.PROJECT_REL].decode("utf-8")
    _require(
        "IC_drive_code.c" not in project_text, "adjacent source entered current project"
    )
    matching_objects = [
        path.name
        for path in (reference_root / "Output").glob("*")
        if path.name.lower() == "ic_drive_code.o"
    ]
    _require(not matching_objects, "adjacent IC_drive_code object appeared")

    epd_source = _strip_c_comments(payloads[Path("User/EDP_init.c")].decode("gb18030"))
    command_body = _function_body(epd_source, "EPD_WriteCMD")
    data_body = _function_body(epd_source, "EPD_WriteDATA")
    _require(
        command_body.count("EPD_SPI_Write(command)") == 1,
        "command SPI primitive changed",
    )
    _require(data_body.count("EPD_SPI_Write(data)") == 1, "data SPI primitive changed")
    _require(
        re.search(r"E_Paper_DC\s*=\s*0", command_body) is not None,
        "command D/C assignment changed",
    )
    _require(
        re.search(r"E_Paper_DC\s*=\s*1", data_body) is not None,
        "data D/C assignment changed",
    )

    return {
        "pinned_files": pinned,
        "known_e6_init": {
            "flattened_command_plus_parameter_bytes": len(E6_INIT_FLAT),
            "flattened_sha256": _sha256(E6_INIT_FLAT),
            "exact_contiguous_match_count": e6_matches,
            **_common_fragment_metadata(capture.mosi, E6_INIT_FLAT),
            "flattening_discards_dc_but_still_does_not_match": True,
            "capture_may_begin_after_an_unobserved_init": True,
        },
        "editor_residue": {
            "external_project_tail": EXTERNAL_PROJECT_TAIL,
            "matching_path_records": len(external_names),
            "matching_path_basenames": external_basenames,
            "matching_delivered_project_directories": delivered_matching_dirs,
            "editor_state_directly_names_capture_csv": False,
            "capture_filename_numeric_tail_matches_project_tail": True,
            "filename_to_project_provenance_binding_proven": False,
            "external_implementation_source_delivered": False,
        },
        "nearest_adjacent_source": {
            "function": "IC_JD79667_initialCode",
            "write_call_count": len(calls),
            "literal_byte_call_count": len(known_positions),
            "capture_start_aligned_literal_matches": aligned_matches,
            "capture_start_aligned_literal_mismatches": aligned_mismatches,
            "exact_function_byte_pattern_compatible": False,
            "listed_in_current_uvprojx": False,
            "matching_output_object_present": False,
            "same_JD79661_variant_source_proven": False,
        },
        "command_data_observability": {
            "adjacent_command_and_data_calls_use_same_mosi_transmit_primitive": True,
            "adjacent_command_data_role_is_selected_by_dc_level": True,
            "capture_has_dc_column": False,
            "adjacent_source_can_restore_roles_without_exact_provenance": False,
        },
    }


def build_report(
    capture_path: Path = DEFAULT_CAPTURE,
    reference_root: Path = DEFAULT_REFERENCE_ROOT,
    iar_root: Path = DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build the metadata-only, identity-pinned report."""

    capture = load_capture(capture_path)
    references = _load_reference_payloads(iar_root)
    timing = _timing_report(capture)
    reference_search = _reference_search(capture.mosi, references)
    adjacent = _adjacent_project_evidence(reference_root, capture)
    public_source = _gxepd2_public_source_cross_check(capture, timing)

    mosi_frequencies: dict[int, int] = {}
    for value in capture.mosi:
        mosi_frequencies[value] = mosi_frequencies.get(value, 0) + 1
    mosi_entropy = -sum(
        (count / len(capture.mosi)) * math.log2(count / len(capture.mosi))
        for count in mosi_frequencies.values()
    )

    unresolved_cut_positions = len(capture.mosi) - timing["timing_run_count"]
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "capture_identity": {
            "relative_path": residual.CAPTURE_REL.as_posix(),
            "bytes": len(capture.payload),
            "sha256": _sha256(capture.payload),
            "header_columns": ["Time [s]", "Packet ID", "MOSI", "MISO"],
            "header_exact": True,
            "line_ending": "CRLF",
            "ends_with_line_ending": True,
            "data_rows": len(capture.mosi),
            "canonical_row_schema": "decimal time with 10 places, zero-based decimal packet id, uppercase 0xNN MOSI/MISO",
            "canonical_row_count": len(capture.mosi),
        },
        "decoded_sequences": {
            "column_text_sha256": EXPECTED_COLUMN_TEXT_SHA256,
            "packet_ids": {
                "first": capture.packet_ids[0],
                "last": capture.packet_ids[-1],
                "contiguous_zero_based": True,
            },
            "mosi": {
                "decoded_bytes": len(capture.mosi),
                "sha256": _sha256(capture.mosi),
                "unique_byte_value_count": len(mosi_frequencies),
                "maximum_single_value_frequency": max(mosi_frequencies.values()),
                "shannon_entropy_bits_per_byte": round(mosi_entropy, 12),
                "raw_sequence_emitted": False,
            },
            "miso": {
                "decoded_bytes": len(capture.miso),
                "sha256": _sha256(capture.miso),
                "unique_byte_value_count": len(set(capture.miso)),
                "all_decoded_values_zero": not any(capture.miso),
                "controller_readback_proven": False,
                "raw_sequence_emitted": False,
            },
        },
        "timing_only_segmentation": timing,
        "known_payload_search": reference_search,
        "source_and_project_cross_check": adjacent,
        "pinned_public_jd79661_cross_check": public_source,
        "ambiguity_quantification": {
            "decoded_byte_rows": len(capture.mosi),
            "adjacent_cut_positions": len(capture.mosi) - 1,
            "large_timing_gaps_conditionally_forced_as_cuts": timing["large_gap_count"],
            "remaining_unobserved_cut_decisions": unresolved_cut_positions,
            "syntax_agnostic_segmentations_preserving_all_large_gap_cuts": f"2^{unresolved_cut_positions}",
            "unobserved_per_byte_dc_labelings": f"2^{len(capture.mosi)}",
            "missing_capture_columns": ["SCLK", "CS", "D/C", "controller_or_target"],
            "spi_mode_or_bit_order_independently_redecoded": False,
            "command_data_boundaries_proven": False,
            "chip_select_boundaries_proven": False,
            "single_or_dual_controller_target_proven": False,
            "transaction_sequence_recovered": False,
        },
        "adjudication": {
            "verdict": "JD79661_PUBLIC_INIT_FRAGMENT_COMPATIBILITY_ONLY__NO_EXACT_CONTIGUOUS_KNOWN_PAYLOAD_IDENTITY_OR_TRANSACTION_RECOVERY",
            "capture_contains_exact_flattened_known_e6_init": False,
            "capture_has_public_jd79661_init_fragment_compatibility": True,
            "capture_contains_exact_flattened_public_jd79661_init": False,
            "capture_contains_exact_public_default_screen_write_sequence": False,
            "capture_contains_exact_contiguous_known_535_704_799_800_or_1503_payload_identity": False,
            "capture_is_spd1657_runtime_lut_upload_proven": False,
            "capture_is_external_jd79661_project_proven": False,
            "adjacent_jd_family_compatibility_is_exact_generator_provenance": False,
            "authorizes_live_hardware_action": False,
        },
        "evidence_limits": {
            "input_is_decoded_analyzer_rows_not_logic_edges": True,
            "capture_start_precedes_device_reset_or_init_proven": False,
            "capture_end_contains_complete_operation_proven": False,
            "miso_zero_proves_controller_acceptance": False,
            "unknown_payload_may_be_present": True,
            "known_payload_identity_only_was_excluded": True,
        },
        "safety": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "flash_written": False,
            "display_refreshed": False,
            "authorization_or_claim_generated": False,
            "raw_capture_bytes_emitted": False,
            "raw_mosi_or_miso_sequences_emitted": False,
            "raw_public_init_sequence_emitted": False,
            "vendor_key_material_emitted": False,
        },
    }
    report["report_canonical_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_report(
            args.capture.resolve(),
            args.reference_root.resolve(),
            args.iar_root.resolve(),
        )
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                indent=None if args.compact else 2,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output.resolve(), payload)
    except (
        CaptureSemanticsAuditError,
        DurableWriteError,
        OSError,
        stats.WaveformStatsError,
        iar_arrays.DataCompatibilityAuditError,
    ) as error:
        print(f"79661 capture semantics audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
