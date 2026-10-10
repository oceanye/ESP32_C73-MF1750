#!/usr/bin/env python3
"""Reproduce the local SPD1657/E2802 reverse-engineering delta offline.

The command audits only vendor files already present in the workspace.  It
decrypts the structurally self-consistent 800-byte candidate in memory so that
its layout can be hashed and classified, but it deliberately does not emit the
customer key, plaintext waveform bytes, an executable runtime profile, or any
hardware action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any
from zipfile import ZipFile


KIND = "mf1750-spd1657-reverse-delta-audit"
SCHEMA_VERSION = 4
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_ROOT = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
DEFAULT_VENDOR_ARCHIVE = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1).zip"
DEFAULT_CASCADE_SCHEMATIC = (
    REPO_ROOT
    / "参考资料"
    / "55-00300-04736-N-InkCubic_ E2802_cascade 电子纸E6转接板.pdf"
)
DEFAULT_LEGACY_IAR_OBJECT = (
    REPO_ROOT
    / "参考资料"
    / "E6_73_sample code_V1.2_20250116"
    / "E6_73_sample code_V1.2_20250116"
    / "Debug"
    / "Obj"
    / "E2802.r43"
)

WF_HEADER_REL = Path("Sample Code/WF20_25.h")
WF23_HEADER_REL = Path("Projects/MDK-ARM/12")
KEIL_PROJECT_REL = Path("Projects/MDK-ARM/atk_f103.uvprojx")
KEIL_EDITOR_STATE_REL = Path("Projects/MDK-ARM/atk_f103.uvguix.Administrator")
E28XX_SOURCE_REL = Path("Sample Code/E28xx.c")
E28XX_HEADER_REL = Path("Sample Code/E28xx.h")
SAMPLE_MAIN_REL = Path("Sample Code/main.c")
USER_MAIN_REL = Path("User/main.c")
OTP_HEADER_REL = Path("Sample Code/OTP.h")
LEGACY_LUT_REL = Path("User/EDP_init.c")
LIBRARY_REL = Path("lib/eload_3bits_M3_E2802_20251229.lib")

EXPECTED_IDENTITIES = {
    "vendor_archive": "c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead",
    "cascade_schematic": "c3f8f563b1222260224f5d76798052237acaec157e5cb78aca488ec12a30abe3",
    "library": "f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b",
    "library_object": "92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d",
    "wf_source": "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821",
    "wf_wrapper": "97efcac1cbc6604a52b942a00b13df349530e152fd28063ed9eda94a36e2dcc5",
    "candidate_plaintext": "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
    "candidate_first_799": "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
    "candidate_first_535": "54a6fe90594630b58fb50a5f7903f8590eb56a2fc2ec1ccb8f084dd9c30612d1",
    "candidate_tail_264": "fab67d0aa34204ef0f7581a9e32e5979ef25323333a43a03f2499b4da482108a",
    "candidate_r21_h1_704": "050f12e9e75f1f7fe2eadf8dff9de00a6eef28e7b7e82251e38bb2fb7c8815ac",
    "candidate_r21_h2_704": "27c4b947ce4bb82c7823a2bf1f637722d4b66737d17e57f16f2ed5c2dc681789",
    "legacy_lut": "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
    "lut1_ff_704": "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
    "otp_payload": "e2c7c39e6ea2406059610d4e3f5b0c99b06e89652cd318bf8dc575585a1a5699",
    "legacy_iar_object": "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
    "legacy_iar_data0": "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5",
    "legacy_iar_data1": "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
    "wf23_source": "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d",
    "wf23_wrapper": "d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4",
    "wf23_recovered_key": "ef1a0b1112267abc84050c3036ec5b627e13e1ef882753062124e5649c0338e2",
    "wf23_plaintext": "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
    "wf23_first_799": "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb",
    "wf23_first_535": "a0e80080a710e68e4fed64d5640bb3d48ce20ef07c577e66e8566f6c3d119226",
    "wf23_tail_264": "c1bbd11b760e0892cabab5c6b1044c8edc88c3c90bd8d0f704e6a95e835f6f0a",
    "keil_project": "2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8",
    "keil_editor_state": "313c944967fbec713ea4fc318d264e43533cc0b23bcb3e53b873cd12fe1fd800",
}

EXPECTED_WF23_CATEGORY_HASHES = (
    "24699f055dc5ebf86d3b2e28125cb67fdadd74e2882fc134c72695e2503b23ee",
    "b966d38478c98f0db4573084f0956a228bbd809e51564b5912cd5c7cc44c06b2",
    "8ad0bb25e3f4678d565733178ec38951363563dad9cca97c9ac8328dacea2d24",
    "61b7ab7999735322d86db3432de9f0c3eef3ba4ad01be55978e9a48db78fcf49",
    "f7ea759449c98569e20317dbefd403b63726ab449ab7687a4c9be801b4c92af6",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
    "6f6bfda4852064a9193ccf6a677c4aa004803d9f7a84c449081b3d9163e2948d",
    "20e674e54b3bf0d26da055cbed93f73a231550094b3c62332078481739ca7822",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
)

EXPECTED_LEGACY_IAR_DATA1_ROW_HASHES = (
    "0d123be8e2fa72bf8b667aea3f32674fc00e82941c4a7d279fc8c364176ebfb1",
    "975b787f3a9603cb7ae6f8e44a35993b77d55833a5bdbff88f77bc1e8b915b44",
    "a5222e2853abd1ed32343470538c08681565bd38be4438ee86c591647b1c05cf",
    "a806b83d2692bc41c159b839bb6ae9b6dbe74282477036e28d46078c4a07dbcc",
    "18e8e65c0218f932c112ee440319105343fc3c99441f9eaff0c3750dbd796b0a",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
)

EXPECTED_LEGACY_IAR_UPLOAD_SIGNATURES = {
    "upload_section_1e": (0x16B80, "c71e00000000"),
    "lut0_count_031f_and_dataBuff_plus_4": (
        0x17EA7,
        "373e40371f03373d405e0e00000004",
    ),
    "lut0_command_20_and_call_section_1d": (
        0x17F8E,
        "373c403720005e1d00000000",
    ),
    "lut1_command_21_and_call_section_19": (
        0x18174,
        "377c403721005e1900000000",
    ),
    "lut1_loop_counter_clear_and_jump_to_compare": (
        0x18358,
        "370b435e1e000000ae",
    ),
    "lut1_ff_and_call_section_16_context": (
        0x18426,
        "d00000006ed705b52f050205377c435e1600000000",
    ),
    "lut1_increment_compare_02c0_and_loop_branch": (
        0x1860E,
        "371b53373b9037c0025e1e000000a6",
    ),
}
EXPECTED_LEGACY_IAR_DATABUFF_PLUS_4_ANCHOR = (
    0x17F60,
    b"Source: MOV.W   #dataBuff + 4, R13s",
)

EXPECTED_CATEGORY_HASHES = (
    "bc2f094ba81e5552387850b5cf2646daeca571dae86f61aa4ff0b1d30f4d3149",
    "8bee977564059847b43ee359fb34076d9dd282b0dd05593c6ef68c1aebbcfbd1",
    "3db99c9b1bd1d7b004741032ddfbe89cf0b4e8077747493c16bbc0a46575d752",
    "01756c354d1f3983632cadb19b7e16e925b2ed1ec58552f62e1c3067b2b6a3e4",
    "a08520cb2a24e844a1ce135a05fdd70cd649b506f9ca07638908062bab3b837c",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
    "95b90e8a950d43acd622d55b0227b6f1bb83000d7aaae87d60f464e1616a81d9",
    "737e5b08c85ebf0fce4af08a9c94606caae4166805006db9b2cd897c7f58f0ee",
    "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
)

EXPECTED_ARCHIVE_ENTRY_HASHES = {
    "REG-API-oqc/Sample Code/E28xx.c": (
        "7a7601f5baecdda5cfb8cd32780c878fff52c1bd44fe8551114e277976d6c2b3"
    ),
    "REG-API-oqc/Sample Code/E28xx.h": (
        "829974a41a1c3c79588941aa28c8fec39fdd07beb1b41c062c75379e29615c47"
    ),
    "REG-API-oqc/Sample Code/WF20_25.h": (
        "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821"
    ),
    "REG-API-oqc/Projects/MDK-ARM/12": (
        "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d"
    ),
    "REG-API-oqc/Sample Code/main.c": (
        "b23d4bcda19e93476ca58d27ec92a9bdc4b6bf9bed7028d082015d7211e1642d"
    ),
    "REG-API-oqc/User/EDP_init.c": (
        "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5"
    ),
    "REG-API-oqc/User/main.c": (
        "ecf13ad33af9dd51e982d3af2daaceb4d74a296618a8c513a06e136f3583387b"
    ),
    "REG-API-oqc/lib/eload_3bits_M3_E2802_20251229.lib": (
        "f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b"
    ),
}

EXPECTED_OBJECT_NAME = "eload_20250305b1.o"

ORC_CODE_STREAM_OFFSET = 0x3C
LOADWF_CODE_STREAM_OFFSET = 0x4B4
LOADWF_CODE_BYTES = 0x88
EXPECTED_LOADWF_CODE_SHA256 = (
    "98f37782e3257d4bf841d7e6b30f2d58f947b580134031ff6680903dddf0a1ff"
)
LOADWF_RELOCATION_NAME_OFFSET = 0xBA8F
LOADWF_RELOCATION_OFFSET = 0xAB4C
LOADWF_RELOCATION_BYTES = 0x68
EXPECTED_LOADWF_RELOCATION_SHA256 = (
    "2fa51656a10d7bf3ddf161c3ac5d74010429f1fbfa2aa08be430ea0cbaa93eae"
)
EXPECTED_LOADWF_RELOCATIONS = (
    (0x06, 0xEF, 0x0A, "strlen"),
    (0x12, 0xBA, 0x0A, "test_decrypt_cbc_check_key"),
    (0x56, 0xF0, 0x0A, "writeEPD"),
    (0x60, 0xF0, 0x0A, "writeEPD"),
    (0x6C, 0xF0, 0x0A, "writeEPD"),
    (0x78, 0xF0, 0x0A, "writeEPD"),
    (0x88, 0xED, 0x02, "customer_key"),
    (0x8C, 0xC2, 0x02, "key_success"),
    (0x90, 0xC3, 0x02, "wf_success"),
    (0x94, 0xC0, 0x02, "pwr_d"),
    (0x98, 0xBC, 0x02, "in"),
    (0x9C, 0xC1, 0x02, "pll_d"),
    (0xA0, 0xC4, 0x02, "LUT1_DATA"),
)
EXPECTED_DEBUG_GLOBAL_RELOCATIONS = (
    (0xAE34, 0x119, 0xBC, "in"),
    (0xAE44, 0x12D, 0xBD, "iniKey"),
    (0xAE54, 0x142, 0xBE, "ciniKey"),
    (0xAE64, 0x159, 0xBF, "sha256_32"),
    (0xAE74, 0x16C, 0xC0, "pwr_d"),
    (0xAE84, 0x17F, 0xC1, "pll_d"),
    (0xAE94, 0x198, 0xC2, "key_success"),
    (0xAEA4, 0x1B0, 0xC3, "wf_success"),
    (0xAEC4, 0x1D5, 0xC4, "LUT1_DATA"),
)

DWARF_GLOBAL_CU_OFFSET = 0x2670
DWARF_GLOBAL_CU_BYTES = 0x228
DWARF_TYPE_CU_OFFSET = 0x8CD4
DWARF_TYPE_CU_BYTES = 0x304
DWARF_ABBREV_OFFSET = 0x94F8
EXPECTED_DWARF_ARRAYS = {
    "in": (0x23F, 543),
    "pwr_d": (0x249, 5),
    "pll_d": (0x252, 0),
    "iniKey": (0x25B, 74),
    "ciniKey": (0x264, 74),
    "sha256_32": (0x26D, 31),
    "LUT1_DATA": (0x2A9, 703),
}


class ReverseAuditError(ValueError):
    """Raised when a frozen local evidence identity no longer matches."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_required(path: Path) -> bytes:
    if not path.is_file():
        raise ReverseAuditError(f"required evidence file is missing: {path}")
    return path.read_bytes()


def _assert_hash(label: str, payload: bytes, expected: str) -> str:
    actual = _sha256(payload)
    if actual != expected:
        raise ReverseAuditError(
            f"{label} identity mismatch: expected {expected}, observed {actual}"
        )
    return actual


def _interpret_spd1657_power_request(plaintext: bytes) -> dict[str, Any]:
    """Interpret decoded header positions that current loadWF binds to PWR.

    This deliberately emits physical requests rather than the five decoded raw
    bytes.  The register formulas come from the incomplete public SPD1657A
    Rev 1.0 manual; they do not establish panel/FPL limits or live suitability.
    """

    if len(plaintext) < 7:
        raise ReverseAuditError("decoded waveform is too short for its header")
    vgpn = plaintext[0] & 0x03
    gate_abs_v = (20, 17, 13, 10)[vgpn]
    full_source_abs_v = (15, 15, 11, 8)[vgpn]
    level_codes = plaintext[1:5]
    if any(value & 0x80 for value in level_codes):
        raise ReverseAuditError("decoded source-level request sets a reserved bit")
    level_magnitudes = [round(3.0 + 0.1 * value, 1) for value in level_codes]
    documented_code_range = all(value <= 0x78 for value in level_codes)
    within_gate_window = all(value <= gate_abs_v - 2.0 for value in level_magnitudes)
    pll_value = plaintext[6]
    if pll_value & 0xF8:
        raise ReverseAuditError("decoded PLL request sets a reserved bit")
    frame_rate_hz = (25, 32, 43, 50, 65, 75, 85, 100)[pll_value]
    return {
        "binding": "current ArmCC loadWF writes 0x0F + decoded[0:5] to PWR 0x01",
        "requested_gate_rails_v": {"positive": gate_abs_v, "negative": -gate_abs_v},
        "requested_full_source_rails_v": {
            "positive": full_source_abs_v,
            "negative": -full_source_abs_v,
        },
        "requested_intermediate_source_levels_v": {
            "vsh_lv": level_magnitudes[0],
            "vsl_lv": -level_magnitudes[1],
            "vsh_lv2": level_magnitudes[2],
            "vsl_lv2": -level_magnitudes[3],
        },
        "all_level_codes_in_manual_0x00_to_0x78_range": documented_code_range,
        "all_requested_levels_within_vgh_vgl_two_volt_window": within_gate_window,
        "decoded_raw_header_emitted": False,
        "requested_frame_rate_hz": frame_rate_hz,
        "pll_frequency_interpreted": True,
        "manual_evidence": {
            "title": "SPD1657A Rev 1.0",
            "date": "2021-08",
            "pages": [19, 21, 22, 27],
            "bytes": 1_869_383,
            "sha256": "29f9c4e2e9cbd6d1aaa4622df4d2ecac8a51a205701a616a96104d03659b89d0",
            "url": "https://drive.google.com/file/d/1U1hq4dhr821CVItF9kOPBJRxhkNMd6Rb/view",
            "lut_byte_layout_omitted_by_manual": True,
        },
        "panel_batch_or_fpl_limits_proven": False,
        "live_approved": False,
    }


def _strip_c_comments(text: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", without_blocks)


def _extract_braced_body(text: str, start: int, label: str) -> str:
    opening = text.find("{", start)
    if opening < 0:
        raise ReverseAuditError(f"cannot find opening brace for {label}")
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise ReverseAuditError(f"cannot find closing brace for {label}")


def _extract_initializer(payload: bytes, name: str) -> bytes:
    text = payload.decode("latin-1")
    match = re.search(
        rf"\b{re.escape(name)}\s*\[[^\]]*\]\s*=\s*\{{",
        text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ReverseAuditError(f"cannot locate {name} initializer")
    body = _strip_c_comments(_extract_braced_body(text, match.start(), name))
    return bytes(
        int(value, 16) for value in re.findall(r"\b0[xX]([0-9A-Fa-f]+)\b", body)
    )


def _extract_function(text: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*\([^;]*?\)\s*\{{", text)
    if match is None:
        raise ReverseAuditError(f"cannot locate function {name}")
    return _extract_braced_body(text, match.start(), name)


def _parse_ar_member(payload: bytes, wanted_name: str) -> tuple[bytes, int]:
    if not payload.startswith(b"!<arch>\n"):
        raise ReverseAuditError("waveform library is not a Unix ar archive")
    position = 8
    records: list[tuple[str, int, bytes]] = []
    while position < len(payload):
        header = payload[position : position + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ReverseAuditError("invalid ar member header")
        raw_name = header[:16].decode("ascii", errors="replace").strip()
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as error:
            raise ReverseAuditError("invalid ar member size") from error
        data_offset = position + 60
        end = data_offset + size
        if end > len(payload):
            raise ReverseAuditError("truncated ar member")
        records.append((raw_name, data_offset, payload[data_offset:end]))
        position = end + (size & 1)

    string_table = next((body for name, _, body in records if name == "//"), b"")
    for raw_name, data_offset, body in records:
        name = raw_name
        if re.fullmatch(r"/\d+", raw_name) and string_table:
            tail = string_table[int(raw_name[1:]) :]
            stops = [
                offset
                for marker in (b"/\n", b"\n", b"/")
                if (offset := tail.find(marker)) >= 0
            ]
            name = tail[: min(stops) if stops else len(tail)].decode(
                "ascii", errors="replace"
            )
        elif raw_name.endswith("/") and raw_name not in ("/", "//"):
            name = raw_name[:-1]
        if name == wanted_name:
            return body, data_offset
    raise ReverseAuditError(f"ar member is missing: {wanted_name}")


def _read_uleb128(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(payload) or shift >= 64:
            raise ReverseAuditError("invalid ULEB128 in ArmCC DWARF")
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7


def _read_sleb128(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(payload) or shift >= 64:
            raise ReverseAuditError("invalid SLEB128 in ArmCC DWARF")
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            if byte & 0x40:
                value |= -(1 << shift)
            return value, offset


def _parse_dwarf_abbreviations(
    payload: bytes, offset: int
) -> dict[int, tuple[int, bool, tuple[tuple[int, int], ...]]]:
    abbreviations: dict[int, tuple[int, bool, tuple[tuple[int, int], ...]]] = {}
    while True:
        code, offset = _read_uleb128(payload, offset)
        if code == 0:
            return abbreviations
        tag, offset = _read_uleb128(payload, offset)
        if offset >= len(payload):
            raise ReverseAuditError("truncated ArmCC DWARF abbreviation")
        has_children = payload[offset] != 0
        offset += 1
        attributes: list[tuple[int, int]] = []
        while True:
            attribute, offset = _read_uleb128(payload, offset)
            form, offset = _read_uleb128(payload, offset)
            if attribute == 0 and form == 0:
                break
            attributes.append((attribute, form))
        if code in abbreviations:
            raise ReverseAuditError("duplicate ArmCC DWARF abbreviation code")
        abbreviations[code] = (tag, has_children, tuple(attributes))


def _read_dwarf_form(
    payload: bytes, offset: int, form: int, address_size: int
) -> tuple[Any, int]:
    if form == 0x16:  # DW_FORM_indirect
        indirect_form, offset = _read_uleb128(payload, offset)
        return _read_dwarf_form(payload, offset, indirect_form, address_size)
    fixed_sizes = {
        0x01: address_size,  # DW_FORM_addr
        0x05: 2,  # DW_FORM_data2
        0x06: 4,  # DW_FORM_data4
        0x07: 8,  # DW_FORM_data8
        0x0B: 1,  # DW_FORM_data1
        0x0C: 1,  # DW_FORM_flag
        0x10: address_size,  # DW_FORM_ref_addr in DWARF v3
        0x11: 1,  # DW_FORM_ref1
        0x12: 2,  # DW_FORM_ref2
        0x13: 4,  # DW_FORM_ref4
        0x14: 8,  # DW_FORM_ref8
    }
    if form in fixed_sizes:
        size = fixed_sizes[form]
        end = offset + size
        if end > len(payload):
            raise ReverseAuditError("truncated fixed-size ArmCC DWARF form")
        return int.from_bytes(payload[offset:end], "little"), end
    if form == 0x08:  # DW_FORM_string
        end = payload.find(b"\x00", offset)
        if end < 0:
            raise ReverseAuditError("unterminated ArmCC DWARF string")
        return payload[offset:end].decode("latin-1"), end + 1
    if form in (0x03, 0x04):  # DW_FORM_block2 / DW_FORM_block4
        count_bytes = 2 if form == 0x03 else 4
        count_end = offset + count_bytes
        if count_end > len(payload):
            raise ReverseAuditError("truncated ArmCC DWARF block length")
        count = int.from_bytes(payload[offset:count_end], "little")
        end = count_end + count
        if end > len(payload):
            raise ReverseAuditError("truncated ArmCC DWARF block")
        return payload[count_end:end], end
    if form in (0x09, 0x0A):  # DW_FORM_block / DW_FORM_block1
        if form == 0x09:
            count, data_offset = _read_uleb128(payload, offset)
        else:
            if offset >= len(payload):
                raise ReverseAuditError("truncated ArmCC DWARF block1")
            count = payload[offset]
            data_offset = offset + 1
        end = data_offset + count
        if end > len(payload):
            raise ReverseAuditError("truncated ArmCC DWARF block payload")
        return payload[data_offset:end], end
    if form == 0x0D:  # DW_FORM_sdata
        return _read_sleb128(payload, offset)
    if form in (0x0F, 0x15):  # DW_FORM_udata / DW_FORM_ref_udata
        return _read_uleb128(payload, offset)
    raise ReverseAuditError(f"unsupported ArmCC DWARF form: 0x{form:02X}")


def _parse_dwarf_cu(
    payload: bytes,
    cu_offset: int,
    expected_bytes: int,
    abbreviations: dict[int, tuple[int, bool, tuple[tuple[int, int], ...]]],
) -> list[dict[str, Any]]:
    if cu_offset + 11 > len(payload):
        raise ReverseAuditError("truncated ArmCC DWARF compilation unit")
    unit_length = struct.unpack_from("<I", payload, cu_offset)[0]
    if unit_length + 4 != expected_bytes:
        raise ReverseAuditError("unexpected ArmCC DWARF compilation-unit length")
    version = struct.unpack_from("<H", payload, cu_offset + 4)[0]
    abbreviation_offset = struct.unpack_from("<I", payload, cu_offset + 6)[0]
    address_size = payload[cu_offset + 10]
    if (version, abbreviation_offset, address_size) != (3, 0, 4):
        raise ReverseAuditError("unexpected ArmCC DWARF CU header")

    end = cu_offset + expected_bytes
    offset = cu_offset + 11
    depth = 0
    dies: list[dict[str, Any]] = []
    while offset < end:
        die_offset = offset - cu_offset
        code, offset = _read_uleb128(payload, offset)
        if code == 0:
            depth -= 1
            continue
        if code not in abbreviations:
            raise ReverseAuditError("unknown ArmCC DWARF abbreviation code")
        tag, has_children, specifications = abbreviations[code]
        attributes: dict[int, Any] = {}
        for attribute, form in specifications:
            attributes[attribute], offset = _read_dwarf_form(
                payload, offset, form, address_size
            )
        dies.append(
            {
                "offset": die_offset,
                "depth": depth,
                "tag": tag,
                "attributes": attributes,
            }
        )
        if has_children:
            depth += 1
    if offset != end:
        raise ReverseAuditError("ArmCC DWARF parser crossed the CU boundary")
    return dies


def _audit_formal_loader_bindings(object_body: bytes) -> dict[str, Any]:
    if object_body[:8] != b"\xf7ORC\x01\x01\x01\x00":
        raise ReverseAuditError("unexpected ArmCC ORC header")
    section_header_offset = struct.unpack_from("<I", object_body, 0x20)[0]
    section_header_bytes = struct.unpack_from("<H", object_body, 0x2E)[0]
    section_count = struct.unpack_from("<H", object_body, 0x30)[0]
    section_name_index = struct.unpack_from("<H", object_body, 0x32)[0]
    if (
        section_header_offset,
        section_header_bytes,
        section_count,
        section_name_index,
    ) != (
        0xD240,
        40,
        271,
        268,
    ):
        raise ReverseAuditError("unexpected ArmCC ORC section geometry")

    relocation_name = b".reli.loadWF\x00"
    if (
        object_body.find(relocation_name) != LOADWF_RELOCATION_NAME_OFFSET
        or object_body.rfind(relocation_name) != LOADWF_RELOCATION_NAME_OFFSET
    ):
        raise ReverseAuditError("loadWF relocation section name is not unique")

    expected_raw_rows = tuple(
        (offset, (symbol << 8) | relocation_type)
        for offset, symbol, relocation_type, _ in EXPECTED_LOADWF_RELOCATIONS
    )
    signature_hits: list[int] = []
    for candidate_offset in range(
        0x34, section_header_offset - LOADWF_RELOCATION_BYTES + 1
    ):
        rows = tuple(
            struct.unpack_from("<II", object_body, candidate_offset + index * 8)
            for index in range(len(expected_raw_rows))
        )
        if rows == expected_raw_rows:
            signature_hits.append(candidate_offset)
    if signature_hits != [LOADWF_RELOCATION_OFFSET]:
        raise ReverseAuditError(
            f"loadWF relocation signature is not unique: {signature_hits}"
        )
    relocation_payload = object_body[
        LOADWF_RELOCATION_OFFSET : LOADWF_RELOCATION_OFFSET + LOADWF_RELOCATION_BYTES
    ]
    _assert_hash(
        "loadWF relocation payload",
        relocation_payload,
        EXPECTED_LOADWF_RELOCATION_SHA256,
    )

    code_start = ORC_CODE_STREAM_OFFSET + LOADWF_CODE_STREAM_OFFSET
    loadwf_code = object_body[code_start : code_start + LOADWF_CODE_BYTES]
    _assert_hash("loadWF code", loadwf_code, EXPECTED_LOADWF_CODE_SHA256)
    ldr_literal = struct.unpack_from("<H", loadwf_code, 0x74)[0]
    if ldr_literal & 0xF800 != 0x4800 or (ldr_literal >> 8) & 0x07 != 1:
        raise ReverseAuditError(
            "loadWF fourth-write pointer is not a Thumb LDR r1 literal"
        )
    literal_offset = ((0x74 + 4) & ~0x03) + (ldr_literal & 0xFF) * 4
    if literal_offset != 0xA0:
        raise ReverseAuditError("loadWF fourth-write literal does not resolve to +0xA0")
    if loadwf_code[0x70:0x7C] != bytes.fromhex("4ff430720a492120fff7feff"):
        raise ReverseAuditError(
            "loadWF 0x21/704 fourth-write instruction sequence changed"
        )

    debug_relocations: list[dict[str, Any]] = []
    for member_offset, dwarf_offset, symbol, name in EXPECTED_DEBUG_GLOBAL_RELOCATIONS:
        actual_dwarf_offset, info = struct.unpack_from(
            "<II", object_body, member_offset
        )
        if (actual_dwarf_offset, info >> 8, info & 0xFF) != (
            dwarf_offset,
            symbol,
            0x02,
        ):
            raise ReverseAuditError(f"DWARF relocation changed for {name}")
        debug_relocations.append(
            {
                "dwarf_offset": dwarf_offset,
                "symbol_index": symbol,
                "relocation_type": "ARM_ABS32",
                "name": name,
            }
        )

    abbreviations = _parse_dwarf_abbreviations(object_body, DWARF_ABBREV_OFFSET)
    global_dies = _parse_dwarf_cu(
        object_body,
        DWARF_GLOBAL_CU_OFFSET,
        DWARF_GLOBAL_CU_BYTES,
        abbreviations,
    )
    type_dies = _parse_dwarf_cu(
        object_body,
        DWARF_TYPE_CU_OFFSET,
        DWARF_TYPE_CU_BYTES,
        abbreviations,
    )
    variables = {
        die["attributes"].get(0x03): die
        for die in global_dies
        if die["tag"] == 0x34 and isinstance(die["attributes"].get(0x03), str)
    }
    type_die_indices = {die["offset"]: index for index, die in enumerate(type_dies)}
    array_reports: dict[str, Any] = {}
    for name, (type_offset, upper_bound) in EXPECTED_DWARF_ARRAYS.items():
        variable = variables.get(name)
        if variable is None or variable["attributes"].get(0x49) != type_offset:
            raise ReverseAuditError(f"DWARF variable/type binding changed for {name}")
        array_index = type_die_indices.get(type_offset)
        if array_index is None:
            raise ReverseAuditError(f"DWARF array type is missing for {name}")
        array_die = type_dies[array_index]
        if array_die["tag"] != 0x01 or array_index + 1 >= len(type_dies):
            raise ReverseAuditError(f"DWARF type is not an array for {name}")
        subrange = type_dies[array_index + 1]
        if (
            subrange["tag"] != 0x21
            or subrange["depth"] != array_die["depth"] + 1
            or subrange["attributes"].get(0x2F) != upper_bound
        ):
            raise ReverseAuditError(f"DWARF array bound changed for {name}")
        array_reports[name] = {
            "type_die_offset": type_offset,
            "upper_bound": upper_bound,
            "bytes": upper_bound + 1,
        }

    constdata_layout = {
        "md5_padding": (0x17FB, 0x183B, 64),
        "sbox": (0x183B, 0x193B, 256),
        "rsbox": (0x193B, 0x1A3B, 256),
        "Rcon": (0x1A3B, 0x1A46, 11),
        "alignment_padding": (0x1A46, 0x1A54, 14),
        "sha256_K": (0x1A54, 0x1B54, 256),
        "LUT1_DATA": (0x1B54, 0x1E14, 704),
    }
    constdata_report: dict[str, Any] = {}
    for name, (start, end, expected_bytes) in constdata_layout.items():
        if end - start != expected_bytes or end > len(object_body):
            raise ReverseAuditError(f"constdata range changed for {name}")
        constdata_report[name] = {
            "member_start": start,
            "member_end_exclusive": end,
            "bytes": expected_bytes,
        }

    relocation_entries = [
        {
            "offset": offset,
            "symbol_index": symbol,
            "relocation_type": (
                "ARM_THM_CALL" if relocation_type == 0x0A else "ARM_ABS32"
            ),
            "symbol_name": name,
        }
        for offset, symbol, relocation_type, name in EXPECTED_LOADWF_RELOCATIONS
    ]
    return {
        "orc_header": {
            "magic_hex": object_body[:8].hex(),
            "section_header_offset": section_header_offset,
            "section_header_entry_bytes": section_header_bytes,
            "section_count": section_count,
            "section_name_index": section_name_index,
            "generic_orc_section_descriptor_decoder_available": False,
        },
        "loadwf_code": {
            "code_stream_offset": LOADWF_CODE_STREAM_OFFSET,
            "bytes": len(loadwf_code),
            "sha256": _sha256(loadwf_code),
        },
        "relocation_section": {
            "name": ".reli.loadWF",
            "name_member_offset": LOADWF_RELOCATION_NAME_OFFSET,
            "data_member_offset": LOADWF_RELOCATION_OFFSET,
            "bytes": len(relocation_payload),
            "sha256": _sha256(relocation_payload),
            "format": "13 standard Elf32_Rel pairs inside ArmCC ORC",
            "unique_signature_match": True,
            "entries": relocation_entries,
        },
        "dwarf": {
            "version": 3,
            "global_cu": {
                "member_offset": DWARF_GLOBAL_CU_OFFSET,
                "bytes": DWARF_GLOBAL_CU_BYTES,
            },
            "type_cu": {
                "member_offset": DWARF_TYPE_CU_OFFSET,
                "bytes": DWARF_TYPE_CU_BYTES,
            },
            "abbreviation_table_member_offset": DWARF_ABBREV_OFFSET,
            "debug_global_relocations": debug_relocations,
            "array_types": array_reports,
        },
        "constdata_layout": constdata_report,
        "fourth_write_binding": {
            "command": "0x21",
            "parameter_bytes": 704,
            "pointer_register": "r1",
            "ldr_instruction_offset": 0x74,
            "literal_relocation_offset": literal_offset,
            "literal_symbol_index": 0xC4,
            "literal_symbol_name": "LUT1_DATA",
            "writeepd_call_relocation_offset": 0x78,
            "formal_binding_proven": True,
            "source_is_independent_symbol_not_in_plus_95": True,
        },
    }


def _ff_runs(payload: bytes, minimum: int = 32) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(payload):
        if payload[index] != 0xFF:
            index += 1
            continue
        end = index + 1
        while end < len(payload) and payload[end] == 0xFF:
            end += 1
        if end - index >= minimum:
            runs.append((index, end - index))
        index = end
    return runs


def _audit_vendor_archive(reference_root: Path, archive_path: Path) -> dict[str, Any]:
    archive = _read_required(archive_path)
    archive_sha = _assert_hash(
        "vendor archive", archive, EXPECTED_IDENTITIES["vendor_archive"]
    )
    entry_reports: list[dict[str, Any]] = []
    with ZipFile(archive_path) as vendor_zip:
        for name, expected_hash in EXPECTED_ARCHIVE_ENTRY_HASHES.items():
            try:
                zipped = vendor_zip.read(name)
            except KeyError as error:
                raise ReverseAuditError(
                    f"vendor archive entry is missing: {name}"
                ) from error
            zipped_sha = _assert_hash(f"archive entry {name}", zipped, expected_hash)
            relative = Path(*Path(name).parts[1:])
            extracted = _read_required(reference_root / relative)
            entry_reports.append(
                {
                    "entry": name,
                    "bytes": len(zipped),
                    "sha256": zipped_sha,
                    "matches_extracted_tree": zipped == extracted,
                }
            )
    return {
        "path": str(archive_path.relative_to(REPO_ROOT)),
        "bytes": len(archive),
        "sha256": archive_sha,
        "entries": entry_reports,
        "all_frozen_entries_match_extracted_tree": all(
            item["matches_extracted_tree"] for item in entry_reports
        ),
    }


def _decrypt_candidate(reference_root: Path) -> tuple[bytes, dict[str, Any]]:
    wf_source = _read_required(reference_root / WF_HEADER_REL)
    _assert_hash("WF20_25 source", wf_source, EXPECTED_IDENTITIES["wf_source"])
    wrapper = _extract_initializer(wf_source, "WF20_25")
    _assert_hash("WF20_25 wrapper", wrapper, EXPECTED_IDENTITIES["wf_wrapper"])
    if len(wrapper) != 842:
        raise ReverseAuditError("WF20_25 wrapper is not 842 bytes")

    source = _read_required(reference_root / E28XX_SOURCE_REL).decode("latin-1")
    key_match = re.search(r'\bcustomer_key\s*\[\s*\]\s*=\s*"([^"]+)"', source)
    if key_match is None:
        raise ReverseAuditError("cannot locate customer_key source metadata")
    source_key = key_match.group(1).encode("ascii")
    key_length = int.from_bytes(wrapper[800:802], "big")
    wrapped_key = wrapper[802:]
    recovered_key = bytes(
        wrapped_key[index] ^ wrapper[index] for index in range(len(wrapped_key))
    )
    if key_length != 40 or recovered_key != source_key:
        raise ReverseAuditError(
            "800+2+40 candidate key contract does not self-validate"
        )

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as error:
        raise ReverseAuditError(
            "cryptography is required for the offline audit"
        ) from error

    aes_key = hashlib.sha256(recovered_key).digest()
    aes_iv = hashlib.md5(recovered_key).digest()  # noqa: S324 - vendor ABI evidence
    decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv)).decryptor()
    plaintext = decryptor.update(wrapper[:800]) + decryptor.finalize()
    _assert_hash(
        "candidate plaintext", plaintext, EXPECTED_IDENTITIES["candidate_plaintext"]
    )
    _assert_hash(
        "candidate first 799",
        plaintext[:799],
        EXPECTED_IDENTITIES["candidate_first_799"],
    )
    _assert_hash(
        "candidate first 535",
        plaintext[:535],
        EXPECTED_IDENTITIES["candidate_first_535"],
    )
    _assert_hash(
        "candidate tail 264",
        plaintext[535:799],
        EXPECTED_IDENTITIES["candidate_tail_264"],
    )

    legacy_source = _read_required(reference_root / LEGACY_LUT_REL)
    legacy = _extract_initializer(legacy_source, "wf_data")
    _assert_hash("legacy 535-byte LUT", legacy, EXPECTED_IDENTITIES["legacy_lut"])
    if len(legacy) != 535:
        raise ReverseAuditError("legacy wf_data is not 535 bytes")

    header = plaintext[:7]
    categories = [
        plaintext[7 + index * 88 : 7 + (index + 1) * 88] for index in range(9)
    ]
    if len(plaintext) != 800 or plaintext[799] != 0:
        raise ReverseAuditError("candidate 7+9*88+1 structure is absent")
    if tuple(_sha256(category) for category in categories) != EXPECTED_CATEGORY_HASHES:
        raise ReverseAuditError("candidate category identities changed")

    sample_color_codes = _sample_color_codes(source)
    all_ff_category_indices = [
        index for index, category in enumerate(categories) if category == b"\xff" * 88
    ]
    assigned_codes = sorted(sample_color_codes.values())
    unassigned_codes = sorted(set(range(8)) - set(assigned_codes))

    legacy_text = legacy_source.decode("latin-1")
    legacy_declaration = re.search(r"\bwf_data\s*\[\s*535\s*\]\s*=", legacy_text)
    if legacy_declaration is None:
        raise ReverseAuditError("cannot locate labeled legacy 535-byte LUT")
    legacy_body = _extract_braced_body(
        legacy_text, legacy_declaration.start(), "legacy wf_data"
    )
    legacy_labels: list[str] = []
    for label in re.findall(
        r"//\s*(VCOM|Black|White|Yellow|Red|Power)-GROUP1\b", legacy_body
    ):
        if label not in legacy_labels:
            legacy_labels.append(label)
    if legacy_labels != ["VCOM", "Black", "White", "Yellow", "Red", "Power"]:
        raise ReverseAuditError("legacy 535-byte LUT category labels changed")

    loader_key_length_at_544 = int.from_bytes(wrapper[544:546], "big")
    r20_mode0_candidate = plaintext[:535]
    r20_h3 = plaintext[:799]
    r21_ff = b"\xff" * 704
    r21_h1 = plaintext[95:799]
    r21_h2 = b"\xff" * 440 + plaintext[535:799]
    _assert_hash(
        "candidate R21 hypothesis H1",
        r21_h1,
        EXPECTED_IDENTITIES["candidate_r21_h1_704"],
    )
    _assert_hash(
        "candidate R21 hypothesis H2",
        r21_h2,
        EXPECTED_IDENTITIES["candidate_r21_h2_704"],
    )
    shared_header_transactions = [
        {
            "command": "0x01",
            "parameter_bytes": 6,
            "parameter_sha256": _sha256(b"\x0f" + plaintext[:5]),
            "source": "literal 0x0F + plain[0:5]",
        },
        {
            "command": "0x30",
            "parameter_bytes": 1,
            "parameter_sha256": _sha256(plaintext[6:7]),
            "source": "plain[6:7]",
        },
    ]
    report = {
        "source_path": WF_HEADER_REL.as_posix(),
        "source_sha256": _sha256(wf_source),
        "wrapper": {
            "bytes": len(wrapper),
            "sha256": _sha256(wrapper),
            "layout": "800-byte ciphertext + 2-byte big-endian key length + 40-byte wrapped key",
            "ciphertext_bytes": 800,
            "key_length_offset": 800,
            "key_length": key_length,
            "wrapped_key_offset": 802,
            "wrapped_key_bytes": len(wrapped_key),
            "recovered_key_matches_supplied_source": recovered_key == source_key,
            "customer_key_sha256": _sha256(source_key),
            "customer_key_material_emitted": False,
        },
        "supplied_loader_mismatch": {
            "loader_ciphertext_bytes": 544,
            "loader_key_length_offset": 544,
            "observed_key_length_at_544": loader_key_length_at_544,
            "observed_key_field_fits_wrapper": (
                546 + loader_key_length_at_544 <= len(wrapper)
            ),
            "compatible": False,
        },
        "plaintext": {
            "bytes": len(plaintext),
            "sha256": _sha256(plaintext),
            "layout_formula": "7 + 9 * (8 * 11) + 1",
            "header_bytes": len(header),
            "header_sha256": _sha256(header),
            "category_count": len(categories),
            "groups_per_category": 8,
            "bytes_per_group": 11,
            "sentinel_offset": 799,
            "sentinel_is_zero": plaintext[799] == 0,
            "first_535_sha256": _sha256(plaintext[:535]),
            "tail_264_sha256": _sha256(plaintext[535:799]),
            "raw_plaintext_emitted": False,
        },
        "header_positional_contract": {
            "byte_0_to_4_used_by_binary_for_power": True,
            "byte_5_legacy_label": "VCOM",
            "byte_5_written_by_loadwf": False,
            "byte_6_used_by_binary_for_pll": True,
            "semantics_fully_proven": False,
        },
        "electrical_request_interpretation": _interpret_spd1657_power_request(
            plaintext
        ),
        "categories": [
            {
                "index": index,
                "bytes": len(category),
                "sha256": _sha256(category),
                "all_ff": category == b"\xff" * 88,
                "unique_byte_count": len(set(category)),
                "ff_byte_count": category.count(0xFF),
            }
            for index, category in enumerate(categories)
        ],
        "category_semantics_evidence": {
            "legacy_535_labels": legacy_labels,
            "legacy_layout_formula": "7-byte header + 6 * 88-byte labeled categories",
            "candidate_first_535_has_same_geometry": (
                len(r20_mode0_candidate) == 7 + 6 * 88
            ),
            "sample_3bit_color_codes": sample_color_codes,
            "assigned_pixel_codes": assigned_codes,
            "unassigned_pixel_codes": unassigned_codes,
            "all_ff_category_indices": all_ff_category_indices,
            "category_5_legacy_position_is_power": legacy_labels[5] == "Power",
            "category_5_cannot_be_uniquely_promoted_to_pixel_code_4": True,
            "tail_categories_6_and_7_are_active": all(
                categories[index] != b"\xff" * 88 for index in (6, 7)
            ),
            "tail_category_8_is_all_ff": categories[8] == b"\xff" * 88,
            "unique_category_to_pixel_code_mapping_proven": False,
            "banner_conflict": (
                "WF20_25 says E5 2-bit while the supplied E28xx API and color fills are 3-bit"
            ),
        },
        "register_view_inference": {
            "current_mode0_r20_geometry": {
                "command": "0x20",
                "plaintext_slice": "[0:535]",
                "bytes": len(r20_mode0_candidate),
                "sha256": _sha256(r20_mode0_candidate),
                "layout": "7-byte header + six 88-byte categories",
                "legacy_category_labels": legacy_labels,
                "support": (
                    "the current E5_3Bit_Mode=0 ArmCC binary directly writes 535 bytes; "
                    "this does not prove the mode-1 length"
                ),
            },
            "mode1_hypotheses": {
                "H1_overlapping_eight_rows": {
                    "construction": "R20=plain[0:535], R21=plain[95:799]",
                    "r20_bytes": 535,
                    "r20_sha256": _sha256(r20_mode0_candidate),
                    "r21_bytes": len(r21_h1),
                    "r21_sha256": _sha256(r21_h1),
                    "slice_offset": 95,
                    "slice_offset_formula": "7 + 88",
                    "row_all_ff": [
                        r21_h1[index * 88 : (index + 1) * 88] == b"\xff" * 88
                        for index in range(8)
                    ],
                    "row_hashes_equal_categories_1_through_8": (
                        tuple(
                            _sha256(r21_h1[index * 88 : (index + 1) * 88])
                            for index in range(8)
                        )
                        == EXPECTED_CATEGORY_HASHES[1:]
                    ),
                    "overlap_with_r20_bytes": 440,
                    "problem": (
                        "requires treating legacy Power position category 5 as pixel code 4"
                    ),
                },
                "H2_extension_slots_5_to_7": {
                    "construction": ("R20=plain[0:535], R21=FF*440+plain[535:799]"),
                    "r20_bytes": 535,
                    "r20_sha256": _sha256(r20_mode0_candidate),
                    "r21_bytes": len(r21_h2),
                    "r21_sha256": _sha256(r21_h2),
                    "row_all_ff": [
                        r21_h2[index * 88 : (index + 1) * 88] == b"\xff" * 88
                        for index in range(8)
                    ],
                    "tail_row_hashes_equal_categories_6_through_8": (
                        tuple(
                            _sha256(r21_h2[index * 88 : (index + 1) * 88])
                            for index in range(5, 8)
                        )
                        == EXPECTED_CATEGORY_HASHES[6:9]
                    ),
                    "structural_interpretation": (
                        "rows 0..4 remain disabled; rows 5/6 carry active blue/green-like "
                        "extensions; row 7 remains disabled"
                    ),
                    "preferred_by_legacy_labels": True,
                    "direct_mode1_binary_proof": False,
                },
                "H3_full_799_r20_ff_r21": {
                    "construction": "R20=plain[0:799], R21=FF*704",
                    "r20_bytes": len(r20_h3),
                    "r20_sha256": _sha256(r20_h3),
                    "r21_bytes": len(r21_ff),
                    "r21_sha256": _sha256(r21_ff),
                    "decoded_padding_byte_excluded": plaintext[799] == 0,
                    "support": (
                        "matches 800-byte CBC decode alignment, the current 544->535 "
                        "compile-time size delta, and a legacy E2802 runtime path that "
                        "writes 0x20/799 then 0x21/704 all-FF"
                    ),
                    "same_generation_mode1_binary_proof": False,
                },
            },
            "preferred_hypothesis": "H3_full_799_r20_ff_r21",
            "ambiguity_resolved": False,
            "mode1_source_binary_or_spi_capture_required": True,
            "support": (
                "H3 is now the strongest cross-generation structural hypothesis; H1/H2 "
                "remain exact alternative constructions and none has same-build mode-1 proof"
            ),
            "direct_mode1_loader_or_relocation_proof": False,
            "live_payload_approved": False,
        },
        "metadata_only_spi_hypotheses": {
            "controllers_required": ["CS1", "CS2"],
            "identical_profile_hashes_on_both_controllers_required": True,
            "controller_transaction_order_proven": False,
            "common_header_transactions": shared_header_transactions,
            "H1_overlapping_eight_rows": {
                "lut_transactions": [
                    {
                        "command": "0x20",
                        "parameter_bytes": 535,
                        "parameter_sha256": _sha256(r20_mode0_candidate),
                    },
                    {
                        "command": "0x21",
                        "parameter_bytes": 704,
                        "parameter_sha256": _sha256(r21_h1),
                    },
                ],
                "mock_trace_complete": True,
                "live_eligible": False,
            },
            "H2_extension_slots_5_to_7": {
                "lut_transactions": [
                    {
                        "command": "0x20",
                        "parameter_bytes": 535,
                        "parameter_sha256": _sha256(r20_mode0_candidate),
                    },
                    {
                        "command": "0x21",
                        "parameter_bytes": 704,
                        "parameter_sha256": _sha256(r21_h2),
                    },
                ],
                "mock_trace_complete": True,
                "live_eligible": False,
            },
            "H3_full_799_r20_ff_r21": {
                "lut_transactions": [
                    {
                        "command": "0x20",
                        "parameter_bytes": 799,
                        "parameter_sha256": _sha256(r20_h3),
                    },
                    {
                        "command": "0x21",
                        "parameter_bytes": 704,
                        "parameter_sha256": _sha256(r21_ff),
                    },
                ],
                "mock_trace_complete": True,
                "live_eligible": False,
            },
            "raw_parameters_emitted": False,
        },
        "legacy_535_comparison": {
            "path": LEGACY_LUT_REL.as_posix(),
            "sha256": _sha256(legacy),
            "equal": plaintext[:535] == legacy,
            "equal_byte_positions": sum(
                left == right for left, right in zip(plaintext[:535], legacy)
            ),
            "total_byte_positions": 535,
        },
    }
    return plaintext, report


def _audit_hidden_wf23_25(
    reference_root: Path, wf20_plaintext: bytes
) -> dict[str, Any]:
    source = _read_required(reference_root / WF23_HEADER_REL)
    source_sha = _assert_hash(
        "hidden WF23_25 source", source, EXPECTED_IDENTITIES["wf23_source"]
    )
    source_text = source.decode("latin-1")
    required_markers = (
        "E5 2-bit DEvelopment Environment",
        "File Name : WF23_25.h",
        "Date : 2025.12.26,14:48",
        "#define SIZE 876",
    )
    if not all(marker in source_text for marker in required_markers):
        raise ReverseAuditError("hidden WF23_25 source metadata changed")

    wrapper = _extract_initializer(source, "WF23_25")
    wrapper_sha = _assert_hash(
        "hidden WF23_25 wrapper", wrapper, EXPECTED_IDENTITIES["wf23_wrapper"]
    )
    if len(wrapper) != 876:
        raise ReverseAuditError("hidden WF23_25 wrapper is not 876 bytes")
    ciphertext_bytes = 800
    key_length = int.from_bytes(wrapper[800:802], "big")
    wrapped_key = wrapper[802:]
    if key_length != 74 or len(wrapped_key) != key_length:
        raise ReverseAuditError("hidden WF23_25 800+2+74 envelope is absent")
    recovered_key = bytes(
        wrapped_key[index] ^ wrapper[index] for index in range(key_length)
    )
    _assert_hash(
        "hidden WF23_25 recovered key",
        recovered_key,
        EXPECTED_IDENTITIES["wf23_recovered_key"],
    )
    if not all(0x20 <= value < 0x7F for value in recovered_key):
        raise ReverseAuditError("hidden WF23_25 recovered key is not printable ASCII")

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as error:
        raise ReverseAuditError(
            "cryptography is required for the offline audit"
        ) from error
    aes_key = hashlib.sha256(recovered_key).digest()
    aes_iv = hashlib.md5(recovered_key).digest()  # noqa: S324 - vendor ABI evidence
    decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv)).decryptor()
    plaintext = decryptor.update(wrapper[:ciphertext_bytes]) + decryptor.finalize()
    _assert_hash(
        "hidden WF23_25 plaintext",
        plaintext,
        EXPECTED_IDENTITIES["wf23_plaintext"],
    )
    _assert_hash(
        "hidden WF23_25 first 799",
        plaintext[:799],
        EXPECTED_IDENTITIES["wf23_first_799"],
    )
    _assert_hash(
        "hidden WF23_25 first 535",
        plaintext[:535],
        EXPECTED_IDENTITIES["wf23_first_535"],
    )
    _assert_hash(
        "hidden WF23_25 tail 264",
        plaintext[535:799],
        EXPECTED_IDENTITIES["wf23_tail_264"],
    )
    categories = [
        plaintext[7 + index * 88 : 7 + (index + 1) * 88] for index in range(9)
    ]
    if len(plaintext) != 800 or plaintext[799] != 0:
        raise ReverseAuditError("hidden WF23_25 7+9*88+1 structure is absent")
    if tuple(_sha256(category) for category in categories) != (
        EXPECTED_WF23_CATEGORY_HASHES
    ):
        raise ReverseAuditError("hidden WF23_25 category identities changed")

    project = _read_required(reference_root / KEIL_PROJECT_REL)
    _assert_hash("Keil project", project, EXPECTED_IDENTITIES["keil_project"])
    editor_state = _read_required(reference_root / KEIL_EDITOR_STATE_REL)
    _assert_hash(
        "Keil editor state",
        editor_state,
        EXPECTED_IDENTITIES["keil_editor_state"],
    )
    project_text = project.decode("latin-1")
    editor_text = editor_state.decode("latin-1")
    editor_only_path_marker = "REG-API-FOG\\Projects\\MDK-ARM\\12</Name>" in editor_text
    r21_ff = b"\xff" * 704
    return {
        "source_path": WF23_HEADER_REL.as_posix(),
        "source_bytes": len(source),
        "source_sha256": source_sha,
        "declared_filename": "WF23_25.h",
        "declared_date": "2025-12-26 14:48",
        "declared_display_generation": "E5 2-bit",
        "vendor_filename_numeric_tokens": [23, 25],
        "temperature_filename_semantics_proven": False,
        "temperature_compatibility_qualified": False,
        "wrapper": {
            "bytes": len(wrapper),
            "sha256": wrapper_sha,
            "layout": (
                "800-byte ciphertext + 2-byte big-endian key length + "
                "74-byte wrapped key"
            ),
            "ciphertext_bytes": ciphertext_bytes,
            "key_length_offset": 800,
            "key_length": key_length,
            "wrapped_key_offset": 802,
            "wrapped_key_bytes": len(wrapped_key),
            "xor_recovered_key_is_printable_ascii": True,
            "recovered_key_sha256": _sha256(recovered_key),
            "customer_key_material_emitted": False,
        },
        "plaintext": {
            "bytes": len(plaintext),
            "sha256": _sha256(plaintext),
            "layout_formula": "7 + 9 * (8 * 11) + 1",
            "header_bytes": 7,
            "header_sha256": _sha256(plaintext[:7]),
            "category_count": len(categories),
            "groups_per_category": 8,
            "bytes_per_group": 11,
            "sentinel_offset": 799,
            "sentinel_is_zero": plaintext[799] == 0,
            "first_535_sha256": _sha256(plaintext[:535]),
            "tail_264_sha256": _sha256(plaintext[535:799]),
            "raw_plaintext_emitted": False,
        },
        "categories": [
            {
                "index": index,
                "bytes": len(category),
                "sha256": _sha256(category),
                "all_ff": category == b"\xff" * 88,
                "all_ff_group_indices": [
                    group
                    for group in range(8)
                    if category[group * 11 : (group + 1) * 11] == b"\xff" * 11
                ],
            }
            for index, category in enumerate(categories)
        ],
        "comparison_to_wf20_25": {
            "same_800_byte_geometry": len(wf20_plaintext) == len(plaintext),
            "equal_plaintext_positions": sum(
                left == right for left, right in zip(wf20_plaintext, plaintext)
            ),
            "total_plaintext_positions": len(plaintext),
            "equal_category_indices": [
                index
                for index in range(9)
                if wf20_plaintext[7 + index * 88 : 7 + (index + 1) * 88]
                == categories[index]
            ],
            "same_pll_request": wf20_plaintext[6] == plaintext[6],
            "same_power_request": wf20_plaintext[:5] == plaintext[:5],
        },
        "electrical_request_interpretation": _interpret_spd1657_power_request(
            plaintext
        ),
        "metadata_only_h3": {
            "construction": "R20=plain[0:799], R21=FF*704",
            "r20_bytes": 799,
            "r20_sha256": _sha256(plaintext[:799]),
            "r21_bytes": len(r21_ff),
            "r21_sha256": _sha256(r21_ff),
            "decoded_padding_byte_excluded": plaintext[799] == 0,
            "same_build_loader_proof": False,
            "live_eligible": False,
            "raw_parameters_emitted": False,
        },
        "build_linkage": {
            "keil_project_path": KEIL_PROJECT_REL.as_posix(),
            "keil_project_sha256": _sha256(project),
            "listed_in_keil_project": "WF23_25" in project_text,
            "editor_state_path": KEIL_EDITOR_STATE_REL.as_posix(),
            "editor_state_sha256": _sha256(editor_state),
            "opened_as_editor_document": editor_only_path_marker,
            "linked_loader_or_reachable_call_path_found": False,
        },
        "classification": {
            "second_vendor_supplied_decodable_profile": True,
            "same_envelope_family_as_wf20_25": True,
            "same_profile_as_wf20_25": plaintext == wf20_plaintext,
            "current_544_byte_loader_compatible": False,
            "same_build_800_byte_loader_found": False,
            "same_panel_batch_or_fpl_proven": False,
            "temperature_qualified_now": False,
            "live_payload_approved": False,
        },
    }


def _sample_color_codes(source: str) -> dict[str, int]:
    functions = {
        "black": "display_Black",
        "white": "display_White",
        "red": "display_Red",
        "yellow": "display_Yellow",
        "blue": "display_B",
        "green": "display_G",
    }
    result: dict[str, int] = {}
    for color, function_name in functions.items():
        body = _extract_function(source, function_name)
        match = re.search(
            r"EPD_WriteDATA_ToMaster\s*\(\s*0[xX]([0-9A-Fa-f]+)\s*\)", body
        )
        if match is None:
            raise ReverseAuditError(f"cannot recover solid fill for {function_name}")
        packed = int(match.group(1), 16)
        if (packed >> 4) != (packed & 0x0F):
            raise ReverseAuditError(
                f"solid fill is not a doubled nibble: {function_name}"
            )
        result[color] = packed & 0x0F
    return result


def _audit_library(reference_root: Path) -> dict[str, Any]:
    library = _read_required(reference_root / LIBRARY_REL)
    library_sha = _assert_hash(
        "waveform library", library, EXPECTED_IDENTITIES["library"]
    )
    object_body, archive_data_offset = _parse_ar_member(library, EXPECTED_OBJECT_NAME)
    object_sha = _assert_hash(
        "waveform object", object_body, EXPECTED_IDENTITIES["library_object"]
    )
    formal_bindings = _audit_formal_loader_bindings(object_body)
    runs = _ff_runs(object_body)
    if runs != [(0x1B54, 704)]:
        raise ReverseAuditError(f"unexpected long 0xFF runs: {runs}")
    lut_offset, lut_bytes = runs[0]
    lut_payload = object_body[lut_offset : lut_offset + lut_bytes]
    lut_hash = _assert_hash(
        "704-byte LUT1 candidate", lut_payload, EXPECTED_IDENTITIES["lut1_ff_704"]
    )

    selector_macros = {
        "MASTER_0": "0x00",
        "SLAVE_1": "0x01",
        "SLAVE_2": "0x02",
        "SLAVE_3": "0x03",
        "SLAVE_4": "0x04",
        "SLAVE_5": "0x05",
        "SLAVE_6": "0x06",
        "SLAVE_7": "0x07",
        "MAS_SLA": "0x10",
    }
    macro_presence = {
        name: f"{name} {value}".encode("ascii") in object_body
        for name, value in selector_macros.items()
    }
    supplied_header = _read_required(reference_root / E28XX_HEADER_REL).decode(
        "latin-1"
    )
    supplied_source = _read_required(reference_root / E28XX_SOURCE_REL).decode(
        "latin-1"
    )
    sample_main = _read_required(reference_root / SAMPLE_MAIN_REL).decode("latin-1")
    write_epd = _extract_function(supplied_source, "writeEPD")

    return {
        "path": LIBRARY_REL.as_posix(),
        "bytes": len(library),
        "sha256": library_sha,
        "object": {
            "name": EXPECTED_OBJECT_NAME,
            "bytes": len(object_body),
            "sha256": object_sha,
            "archive_data_offset": archive_data_offset,
            "archive_data_offset_hex": f"0x{archive_data_offset:X}",
            "magic_hex": object_body[:4].hex(),
            "armcc_banner_present": (
                b"ARM Compiler 5.06 update 3 (build 300)" in object_body
            ),
        },
        "compile_contract": {
            "wf_decode_size_544": b"WF_DeCode_SIZE 544" in object_body,
            "wf_size_535": b"WF_SIZE 535" in object_body,
            "e5_3bit_mode_0": b"E5_3Bit_Mode 0" in object_body,
            "compiled_header_path": "../eink_code/E28xx.h",
            "compiled_header_path_present": b"..\\eink_code\\E28xx.h" in object_body,
            "selector_macros": selector_macros,
            "all_selector_macros_present_in_debug": all(macro_presence.values()),
            "spi_chip_select_symbol_present_in_debug": b"spiChipSelect" in object_body,
        },
        "formal_loader_bindings": formal_bindings,
        "current_mode0_counterevidence": {
            "mode_branch_present": False,
            "r21_source": "independent symbol C4 LUT1_DATA[704]",
            "r21_source_is_decoded_in_plus_95": False,
            "r21_source_binding_formally_proven": formal_bindings[
                "fourth_write_binding"
            ]["formal_binding_proven"],
            "candidate_mode1_register_view_used_by_this_build": False,
        },
        "delivered_header_version_gap": {
            "path": E28XX_HEADER_REL.as_posix(),
            "mas_sla_declared": re.search(r"\bMAS_SLA\b", supplied_header) is not None,
            "spi_chip_select_declared": (
                re.search(r"\bspiChipSelect\b", supplied_header) is not None
            ),
            "sample_main_assigns_mas_sla": (
                re.search(r"spiChipSelect\s*=\s*MAS_SLA", sample_main) is not None
            ),
            "compiled_and_delivered_headers_are_contract_compatible": False,
        },
        "delivered_writeepd_glue": {
            "path": E28XX_SOURCE_REL.as_posix(),
            "references_spi_chip_select": "spiChipSelect" in write_epd,
            "uses_both_writer": "ToBoth" in write_epd,
            "uses_legacy_generic_writer": (
                "sendSPICommand" in write_epd and "sendMutipleSPIData" in write_epd
            ),
            "generic_send_path_is_master_only_in_delivered_tree": True,
            "honors_sample_main_mas_sla_assignment": False,
        },
        "lut1_candidate": {
            "member_offset": lut_offset,
            "member_offset_hex": f"0x{lut_offset:X}",
            "archive_offset": archive_data_offset + lut_offset,
            "archive_offset_hex": f"0x{archive_data_offset + lut_offset:X}",
            "bytes": lut_bytes,
            "sha256": lut_hash,
            "all_ff": lut_payload == b"\xff" * 704,
            "only_long_ff_run_in_object": len(runs) == 1,
            "public_lut1_data_symbol_present": b"LUT1_DATA" in object_body,
            "formal_relocation_binding_proven_by_this_tool": formal_bindings[
                "fourth_write_binding"
            ]["formal_binding_proven"],
            "ff_semantics_known": False,
        },
    }


def _audit_schematic(schematic_path: Path) -> dict[str, Any]:
    payload = _read_required(schematic_path)
    schematic_sha = _assert_hash(
        "cascade schematic", payload, EXPECTED_IDENTITIES["cascade_schematic"]
    )
    try:
        import pdfplumber
    except ImportError as error:
        raise ReverseAuditError(
            "pdfplumber is required for schematic text audit"
        ) from error
    with pdfplumber.open(schematic_path) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        pages = len(document.pages)
        metadata = document.metadata or {}
    tokens = {
        "SL_CSB": "SL_CSB" in text,
        "CS": re.search(r"\bCS\b", text) is not None,
        "CSB": "CSB" in text,
        "J1": "J1" in text,
        "J4": "J4" in text,
        "E2802_CASCADE_50PIN": "E2802_CASCADE_50PIN" in text,
    }
    return {
        "path": str(schematic_path.relative_to(REPO_ROOT)),
        "bytes": len(payload),
        "sha256": schematic_sha,
        "pages": pages,
        "creator": metadata.get("Creator"),
        "tokens": tokens,
        "all_topology_tokens_present": all(tokens.values()),
        "topology_evidence": {
            "external_8pin_j1_exposes_one_cs": True,
            "controller_symbol_has_csb_and_sl_csb": True,
            "j4_places_cs_and_sl_csb_on_a_two_pin_header": True,
            "j4_is_jumperable_bridge": True,
            "physical_jumper_population_or_state_proven": False,
        },
    }


def _audit_initialization_paths(reference_root: Path) -> dict[str, Any]:
    sample_source = _read_required(reference_root / E28XX_SOURCE_REL).decode("latin-1")
    user_main = _read_required(reference_root / USER_MAIN_REL).decode("latin-1")
    factory_init = _extract_function(sample_source, "epdInitial")
    nootp_init = _extract_function(user_main, "EPD_initial_noOTP")

    gate_match = re.search(r"\bGate\s*=\s*(\d+)\s*;", nootp_init)
    source_match = re.search(r"\bSource\s*=\s*(\d+)\s*;", nootp_init)
    if gate_match is None or source_match is None:
        raise ReverseAuditError("cannot recover dormant no-OTP geometry")
    nootp_geometry = [int(source_match.group(1)), int(gate_match.group(1))]
    wrapper_indices = sorted(
        {int(value) for value in re.findall(r"WF20_25\s*\[\s*(\d+)\s*\]", nootp_init)}
    )
    if nootp_geometry != [428, 428] or wrapper_indices != [1, 2, 3, 4, 6]:
        raise ReverseAuditError("dormant no-OTP source contract changed")

    nootp_tokens = {
        "psr_0x0f_0x89": bool(
            re.search(
                r"EPD_WriteCMD\s*\(\s*0x00\s*\).*?"
                r"EPD_WriteDATA\s*\(\s*0x0F\s*\).*?"
                r"EPD_WriteDATA\s*\(\s*0x89\s*\)",
                nootp_init,
                flags=re.DOTALL | re.IGNORECASE,
            )
        ),
        "e9_0x01": bool(
            re.search(
                r"EPD_WriteCMD\s*\(\s*0xE9\s*\).*?"
                r"EPD_WriteDATA\s*\(\s*0x01\s*\)",
                nootp_init,
                flags=re.DOTALL | re.IGNORECASE,
            )
        ),
        "uses_generic_writer": "EPD_WriteCMD(" in nootp_init
        and "EPD_WriteDATA(" in nootp_init,
        "uses_both_writer": "ToBoth" in nootp_init,
    }
    if not all((nootp_tokens["psr_0x0f_0x89"], nootp_tokens["e9_0x01"])):
        raise ReverseAuditError("dormant no-OTP PSR/E9 sequence changed")

    factory_tokens = {
        "calls_reset": re.search(r"\breset\s*\(\s*\)", factory_init) is not None,
        "uses_both_writer": "EPD_WriteCMD_ToBoth" in factory_init
        and "EPD_WriteDATA_ToBoth" in factory_init,
        "psr_0x5f_0x69": bool(
            re.search(
                r"EPD_WriteCMD_ToBoth\s*\(\s*R00_PSR\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x5F\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x69\s*\)",
                factory_init,
                flags=re.DOTALL | re.IGNORECASE,
            )
        ),
        "tres_512x600": bool(
            re.search(
                r"EPD_WriteCMD_ToBoth\s*\(\s*R61_TRES\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x02\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x00\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x02\s*\).*?"
                r"EPD_WriteDATA_ToBoth\s*\(\s*0x58\s*\)",
                factory_init,
                flags=re.DOTALL | re.IGNORECASE,
            )
        ),
    }
    if not all(factory_tokens.values()):
        raise ReverseAuditError("factory initialization source contract changed")

    return {
        "dormant_nootp_path": {
            "path": USER_MAIN_REL.as_posix(),
            "function": "EPD_initial_noOTP",
            "definition_is_never_called_in_delivered_user_main": (
                len(re.findall(r"\bEPD_initial_noOTP\s*\(", user_main)) == 1
            ),
            "geometry_source_by_gate": nootp_geometry,
            "reads_wrapper_ciphertext_indices_as_register_values": wrapper_indices,
            "uses_decoded_plaintext_header": False,
            **nootp_tokens,
            "matches_current_dual_controller_runtime_contract": False,
        },
        "factory_init_path": {
            "path": E28XX_SOURCE_REL.as_posix(),
            "function": "epdInitial",
            **factory_tokens,
            "formal_runtime_to_factory_otp_recovery_proven": False,
        },
        "conclusion": (
            "the dormant 428x428 master-only no-OTP path is not a usable companion "
            "for WF20_25; reset plus epdInitial is a recovery candidate, not a proven "
            "post-runtime recovery contract"
        ),
    }


def _audit_otp_payload(
    reference_root: Path, candidate_plaintext: bytes
) -> dict[str, Any]:
    otp_source = _read_required(reference_root / OTP_HEADER_REL)
    otp_payload = _extract_initializer(otp_source, "OTP_DATA")
    otp_sha = _assert_hash("OTP_DATA", otp_payload, EXPECTED_IDENTITIES["otp_payload"])
    candidate_groups = [
        candidate_plaintext[
            7 + category * 88 + group * 11 : 7 + category * 88 + (group + 1) * 11
        ]
        for category in range(9)
        for group in range(8)
    ]
    exact_group_matches = sum(group in otp_payload for group in candidate_groups)
    return {
        "path": OTP_HEADER_REL.as_posix(),
        "bytes": len(otp_payload),
        "sha256": otp_sha,
        "three_384_byte_program_blocks": len(otp_payload) == 3 * 384,
        "contains_candidate_800": candidate_plaintext in otp_payload,
        "contains_candidate_first_535": candidate_plaintext[:535] in otp_payload,
        "exact_11_byte_candidate_group_matches": exact_group_matches,
        "classification": "separate OTP programming payload, not a runtime-LUT format oracle",
        "hardware_otp_read": False,
        "otp_programming_attempted": False,
    }


def _extract_iar_byte_items(
    payload: bytes,
    *,
    marker_offset: int,
    section_id: int,
    item_offset: int,
    item_count: int,
    label: str,
) -> bytes:
    marker = bytes((0xC7, section_id, 0, 0, 0, 0))
    if payload[marker_offset : marker_offset + len(marker)] != marker:
        raise ReverseAuditError(f"{label} IAR section marker changed")
    if (
        payload.find(marker) != marker_offset
        or payload.find(marker, marker_offset + 1) >= 0
    ):
        raise ReverseAuditError(f"{label} IAR section marker is not unique")
    encoded = payload[item_offset : item_offset + 2 * item_count]
    if len(encoded) != 2 * item_count or encoded[0::2] != b"\x36" * item_count:
        raise ReverseAuditError(f"{label} IAR byte-item encoding changed")
    return encoded[1::2]


def _assert_unique_binary_signature(
    payload: bytes, *, label: str, expected_offset: int, signature: bytes
) -> None:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = payload.find(signature, cursor)
        if offset < 0:
            break
        offsets.append(offset)
        cursor = offset + 1
    if offsets != [expected_offset]:
        rendered = ", ".join(f"0x{offset:X}" for offset in offsets) or "none"
        raise ReverseAuditError(
            f"{label} signature mismatch: expected 0x{expected_offset:X}; found {rendered}"
        )


def _audit_legacy_iar_e2802(iar_object_path: Path) -> dict[str, Any]:
    payload = _read_required(iar_object_path)
    object_sha = _assert_hash(
        "legacy IAR E2802 object",
        payload,
        EXPECTED_IDENTITIES["legacy_iar_object"],
    )
    if len(payload) != 328_062:
        raise ReverseAuditError("legacy IAR E2802 object size changed")

    data0 = _extract_iar_byte_items(
        payload,
        marker_offset=0x53D0,
        section_id=0x14,
        item_offset=0x53D6,
        item_count=1503,
        label="DATA0",
    )
    data1 = _extract_iar_byte_items(
        payload,
        marker_offset=0x5F94,
        section_id=0x15,
        item_offset=0x5F9A,
        item_count=704,
        label="DATA1",
    )
    _assert_hash("legacy IAR DATA0", data0, EXPECTED_IDENTITIES["legacy_iar_data0"])
    _assert_hash("legacy IAR DATA1", data1, EXPECTED_IDENTITIES["legacy_iar_data1"])

    data0_blocks = [data0[7 + index * 88 : 7 + (index + 1) * 88] for index in range(17)]
    if len(data0) != 7 + 17 * 88:
        raise ReverseAuditError("legacy IAR DATA0 no longer has 7+17*88 geometry")
    data1_rows = [data1[index * 88 : (index + 1) * 88] for index in range(8)]
    if (
        tuple(_sha256(row) for row in data1_rows)
        != EXPECTED_LEGACY_IAR_DATA1_ROW_HASHES
    ):
        raise ReverseAuditError("legacy IAR DATA1 row identities changed")

    required_symbols = (
        b"EPD_Load_LUT",
        b"EPD_Load_LUT_const",
        b"Upload_Temperature_LUT",
        b"DATA0",
        b"DATA1",
    )
    if not all(payload.count(symbol) >= 1 for symbol in required_symbols):
        raise ReverseAuditError("legacy IAR LUT symbol set changed")

    upload_signatures: dict[str, Any] = {}
    for label, (
        expected_offset,
        signature_hex,
    ) in EXPECTED_LEGACY_IAR_UPLOAD_SIGNATURES.items():
        signature = bytes.fromhex(signature_hex)
        _assert_unique_binary_signature(
            payload,
            label=label,
            expected_offset=expected_offset,
            signature=signature,
        )
        upload_signatures[label] = {
            "file_offset": f"0x{expected_offset:X}",
            "sha256": _sha256(signature),
            "bytes": len(signature),
            "occurrences_in_object": 1,
        }
    anchor_offset, anchor = EXPECTED_LEGACY_IAR_DATABUFF_PLUS_4_ANCHOR
    _assert_unique_binary_signature(
        payload,
        label="dataBuff_plus_4_source_anchor",
        expected_offset=anchor_offset,
        signature=anchor,
    )

    return {
        "path": str(iar_object_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "bytes": len(payload),
        "sha256": object_sha,
        "format": "IAR MSP430 UBROF object",
        "data0": {
            "section_id": "0x14",
            "marker_file_offset": "0x53D0",
            "item_file_offset": "0x53D6",
            "bytes": len(data0),
            "sha256": _sha256(data0),
            "layout_formula": "7 + 17 * 88",
            "active_88_byte_blocks": [
                index
                for index, block in enumerate(data0_blocks)
                if block != b"\xff" * 88
            ],
            "all_ff_88_byte_blocks": [
                index
                for index, block in enumerate(data0_blocks)
                if block == b"\xff" * 88
            ],
        },
        "data1": {
            "section_id": "0x15",
            "marker_file_offset": "0x5F94",
            "item_file_offset": "0x5F9A",
            "bytes": len(data1),
            "sha256": _sha256(data1),
            "layout_formula": "8 * 88",
            "rows": [
                {
                    "index": index,
                    "sha256": _sha256(row),
                    "non_ff_bytes": sum(value != 0xFF for value in row),
                    "all_ff": row == b"\xff" * 88,
                }
                for index, row in enumerate(data1_rows)
            ],
            "referenced_by_active_upload_path": False,
        },
        "reverse_engineered_runtime_sequence": {
            "transactions": [
                {
                    "command": "0x20",
                    "parameter_bytes": 799,
                    "source": "dataBuff+4",
                },
                {
                    "command": "0x21",
                    "parameter_bytes": 704,
                    "source": "literal 0xFF repeated",
                },
            ],
            "data1_constant_is_not_the_active_r21_source": True,
            "unique_ubrof_machine_signatures": upload_signatures,
            "dataBuff_plus_4_source_anchor_file_offset": f"0x{anchor_offset:X}",
            "machine_signature_binding_reproduced_by_this_tool": True,
            "same_generation_as_current_armcc_loader": False,
            "same_build_as_wf20_25": False,
            "can_uniquely_prove_current_mode1_contract": False,
        },
        "limits": {
            "single_controller_only": True,
            "runtime_to_otp_recovery_present": False,
            "e9_command_in_runtime_upload_present": False,
            "safe_live_artifact_derivable_from_this_object_alone": False,
        },
    }


def build_report(
    reference_root: Path = DEFAULT_REFERENCE_ROOT,
    vendor_archive: Path = DEFAULT_VENDOR_ARCHIVE,
    cascade_schematic: Path = DEFAULT_CASCADE_SCHEMATIC,
    legacy_iar_object: Path = DEFAULT_LEGACY_IAR_OBJECT,
) -> dict[str, Any]:
    reference_root = reference_root.resolve()
    vendor_archive = vendor_archive.resolve()
    cascade_schematic = cascade_schematic.resolve()
    legacy_iar_object = legacy_iar_object.resolve()
    archive_report = _audit_vendor_archive(reference_root, vendor_archive)
    candidate_plaintext, candidate_report = _decrypt_candidate(reference_root)
    wf23_report = _audit_hidden_wf23_25(reference_root, candidate_plaintext)
    library_report = _audit_library(reference_root)
    schematic_report = _audit_schematic(cascade_schematic)
    initialization_report = _audit_initialization_paths(reference_root)
    otp_report = _audit_otp_payload(reference_root, candidate_plaintext)
    legacy_iar_report = _audit_legacy_iar_e2802(legacy_iar_object)

    blockers = [
        {
            "code": "matching_800_byte_loader_missing",
            "evidence": "the supplied library reads a 544-byte ciphertext and a key length at offset 544",
        },
        {
            "code": "mode1_loader_direct_proof_missing",
            "evidence": (
                "legacy E2802 code makes H3 0x20/799 + 0x21/704*FF the strongest "
                "cross-generation hypothesis, but H1/H2 remain exact alternatives and no "
                "same-build mode-1 loader, source, or SPI capture selects the current ABI"
            ),
        },
        {
            "code": "delivered_dual_cs_glue_incomplete",
            "evidence": "sample main sets MAS_SLA, while the delivered writeEPD callback ignores spiChipSelect",
        },
        {
            "code": "matching_runtime_initialization_missing",
            "evidence": (
                "the only delivered no-OTP source is dormant, 428x428, master-only, "
                "and reads ciphertext wrapper indices instead of a decoded header"
            ),
        },
        {
            "code": "lut1_ff_semantics_unknown",
            "evidence": "the mode-0 library-resident 704-byte table is all FF, whose controller meaning is undocumented",
        },
        {
            "code": "otp_equivalent_k0_missing",
            "evidence": "no qualified runtime profile is tied to the current panel batch, temperature, and OTP baseline",
        },
        {
            "code": "candidate_temperature_qualification_missing",
            "evidence": (
                "the two vendor artifacts are named WF20_25 and WF23_25, but no "
                "vendor or primary source defines those numeric filename tokens as "
                "temperature bands; the previously observed 37 C does not qualify "
                "either profile"
            ),
        },
        {
            "code": "deterministic_runtime_to_otp_recovery_missing",
            "evidence": "the supplied loadWF has no reset, readback, refresh, or recovery transaction",
        },
    ]
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "reference_root": str(reference_root),
        "vendor_archive": archive_report,
        "candidate_800": candidate_report,
        "candidate_wf23_25": wf23_report,
        "library": library_report,
        "cascade_schematic": schematic_report,
        "initialization_paths": initialization_report,
        "otp_payload": otp_report,
        "legacy_iar_e2802": legacy_iar_report,
        "newest_evidence": {
            "category_semantics": (
                "legacy 535-byte source labels its six 88-byte blocks VCOM, Black, White, "
                "Yellow, Red, Power; category 5 therefore cannot be uniquely relabeled code 4"
            ),
            "register_views": (
                "legacy E2802 runtime code writes 0x20/799 then 0x21/704 all-FF, making H3 "
                "stronger than H1/H2; the current same-generation mode-1 build remains missing"
            ),
            "second_vendor_profile": (
                "a hidden 2025-12-26 WF23_25 artifact independently self-validates as "
                "800+2+74, decrypts to the same 7+9*88+1 geometry, and differs from "
                "WF20_25 at 357 of 800 positions; it was editor-opened but is absent "
                "from the Keil project and all linked loader paths"
            ),
            "electrical_header": (
                "the current ArmCC loadWF binding plus SPD1657A PWR formulas now convert "
                "both decoded headers to metadata-only requested rails; this does not "
                "establish panel/FPL limits or live suitability"
            ),
            "legacy_iar_side_evidence": (
                "the 2020 IAR object uses 0x20/799 plus an explicit 704-byte all-FF 0x21; "
                "its retained DATA1 constant is not that active upload source"
            ),
            "formal_mode0_binding": (
                "13 targeted CROF relocations plus DWARF prove the current build writes "
                "independent symbol C4 LUT1_DATA[704], not decoded in+95"
            ),
            "dual_controller_contract": (
                "the binary was compiled against selector-aware glue, but the delivered header "
                "and writeEPD adapter do not implement that contract"
            ),
            "schematic_contract": (
                "CS and SL_CSB are jumperable on J4; actual population/state still requires "
                "non-invasive physical confirmation"
            ),
        },
        "runtime_profile_ready": False,
        "visible_runtime_test_authorized": False,
        "first_live_test_target": {
            "goal": "one controlled sacrificial-panel vendor-K0 refresh followed by OTP white recovery",
            "vendor_waveform_must_be_unmodified": True,
            "candidate_profile_ids": ["WF20_25", "WF23_25"],
            "vendor_filename_numeric_tokens_by_profile": {
                "WF20_25": [20, 25],
                "WF23_25": [23, 25],
            },
            "temperature_filename_semantics_proven": False,
            "temperature_compatibility_qualified": False,
            "experimental_fixed_temperature_guard_c": [25.0, 25.0],
            "temperature_guard_basis": (
                "adjacent_2020_E2801_E2802_fixed_selector_25_not_vendor_band"
            ),
            "vendor_temperature_band_claim": False,
            "profile_priority_resolved": False,
            "matching_mode1_loader_or_spi_capture_required": True,
            "dual_controller_delivery_proof_required": True,
            "materialized": False,
            "authorized": False,
        },
        "blockers": blockers,
        "safety": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_accessed": False,
            "device_network_accessed": False,
            "flash_written": False,
            "display_refreshed": False,
            "otp_read_from_hardware": False,
            "otp_programmed": False,
            "candidate_decrypted_in_memory": True,
            "vendor_profiles_decrypted_in_memory": 2,
            "customer_key_material_emitted": False,
            "raw_waveform_plaintext_emitted": False,
            "live_payload_generated": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the local SPD1657/E2802 reverse delta without hardware."
    )
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    parser.add_argument("--vendor-archive", type=Path, default=DEFAULT_VENDOR_ARCHIVE)
    parser.add_argument(
        "--cascade-schematic", type=Path, default=DEFAULT_CASCADE_SCHEMATIC
    )
    parser.add_argument(
        "--legacy-iar-object", type=Path, default=DEFAULT_LEGACY_IAR_OBJECT
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(
            reference_root=args.reference_root,
            vendor_archive=args.vendor_archive,
            cascade_schematic=args.cascade_schematic,
            legacy_iar_object=args.legacy_iar_object,
        )
    except ReverseAuditError as error:
        json.dump(
            {"kind": KIND, "schema_version": SCHEMA_VERSION, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
