#!/usr/bin/env python3
"""Audit the supplied vendor E6 and STM32/E2802 references without hardware.

The report deliberately contains metadata and contract evidence only.  It does
not decrypt waveform packages, emit customer key material, read the OTP payload,
or reproduce either waveform byte array.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


KIND = "mf1750-stm32-waveform-reference-audit"
SCHEMA_VERSION = 3
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_ROOT = (
    REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
)
E6_REFERENCE_ROOT = (
    REPO_ROOT
    / "参考资料"
    / "E6_73_sample code_V1.2_20250116"
    / "E6_73_sample code_V1.2_20250116"
)

EDP_INIT_REL = Path("User/EDP_init.c")
UART_DATA_REL = Path("User/UartDataDeal.c")
USART_SOURCE_REL = Path("Drivers/SYSTEM/usart/usart.c")
LCD_CONFIG_REL = Path("User/LCDConfig.h")
USER_MAIN_REL = Path("User/main.c")
E28XX_SOURCE_REL = Path("Sample Code/E28xx.c")
E28XX_HEADER_REL = Path("Sample Code/E28xx.h")
SAMPLE_MAIN_REL = Path("Sample Code/main.c")
WF_HEADER_REL = Path("Sample Code/WF20_25.h")
LIB_REL = Path("lib/eload_3bits_M3_E2802_20251229.lib")
UVPROJ_REL = Path("Projects/MDK-ARM/atk_f103.uvprojx")

EXPECTED_LUT_CATEGORIES = ("VCOM", "Black", "White", "Yellow", "Red", "Power")
EXPECTED_LIB_MARKERS = {
    "e5_3bit_mode_macro": b"E5_3Bit_Mode 0",
    "decoded_size_544": b"WF_DeCode_SIZE 544",
    "waveform_size_535": b"WF_SIZE 535",
    "loadwf": b"loadWF",
    "aes": b"AES_CBC_decrypt_buffer",
    "md5": b"tiny_md5",
    "sha": b"sha256_32",
    "lut1_data": b"LUT1_DATA",
}
EXPECTED_LIBRARY_SHA256 = "f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b"
EXPECTED_OBJECT_NAME = "eload_20250305b1.o"
EXPECTED_OBJECT_SHA256 = "92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d"
ORC_CODE_STREAM_OFFSET = 0x3C
ORC_CODE_STREAM_BYTES = 0x1453
EXPECTED_CODE_STREAM_SHA256 = "2918a3da3a82a15e168fff6587aa545ad6eb0d093ee345040a3a17272429b252"
LOADWF_CODE_OFFSET = 0x4B4
LOADWF_CODE_BYTES = 0x88
EXPECTED_LOADWF_SHA256 = "98f37782e3257d4bf841d7e6b30f2d58f947b580134031ff6680903dddf0a1ff"
DECRYPT_CHECK_CODE_OFFSET = 0x116C
DECRYPT_CHECK_CODE_BYTES = 0xCC
EXPECTED_DECRYPT_CHECK_SHA256 = (
    "ba955f2bf76c68bcc859707e68edae7b3a51884f4da695975a0841376d0219b2"
)


class AuditError(ValueError):
    """Raised when the reference tree cannot satisfy the audit contract."""


def _read_bytes(root: Path, relative: Path) -> bytes:
    path = root / relative
    if not path.is_file():
        raise AuditError(f"required reference file is missing: {relative.as_posix()}")
    return path.read_bytes()


def _read_text(root: Path, relative: Path) -> str:
    # All audited tokens are ASCII.  Latin-1 keeps the audit deterministic even
    # though some comments in the vendor tree use a legacy Chinese code page.
    return _read_bytes(root, relative).decode("latin-1")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _extract_initializer(text: str, declaration_pattern: str, label: str) -> str:
    match = re.search(declaration_pattern, text, flags=re.MULTILINE)
    if match is None:
        raise AuditError(f"cannot locate {label} initializer")
    opening = text.find("{", match.start())
    if opening < 0:
        raise AuditError(f"cannot locate opening brace for {label}")
    depth = 0
    for index in range(opening, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AuditError(f"cannot locate closing brace for {label}")


def _strip_c_comments(text: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", without_blocks)


def _hex_values(initializer: str) -> list[int]:
    active = _strip_c_comments(initializer)
    return [int(value, 16) for value in re.findall(r"\b0[xX]([0-9A-Fa-f]+)\b", active)]


def _audit_wf_data(root: Path) -> dict[str, Any]:
    payload = _read_bytes(root, EDP_INIT_REL)
    text = payload.decode("latin-1")
    declaration = re.search(r"\buint8_t\s+wf_data\s*\[\s*(\d+)\s*\]\s*=", text)
    if declaration is None:
        raise AuditError("cannot locate wf_data declaration")
    declared_size = int(declaration.group(1))
    initializer = _extract_initializer(
        text,
        r"\buint8_t\s+wf_data\s*\[\s*\d+\s*\]\s*=",
        "wf_data",
    )
    values = _hex_values(initializer)

    groups: list[tuple[str, int, int]] = []
    for line in initializer.splitlines():
        code, separator, comment = line.partition("//")
        if not separator or not re.search(r"\b0[xX][0-9A-Fa-f]+\b", code):
            continue
        category = re.search(
            r"\b(VCOM|Black|White|Yellow|Red|Power)-GROUP\s*(\d+)\b",
            comment,
        )
        if category is not None:
            groups.append(
                (
                    category.group(1),
                    int(category.group(2)),
                    len(re.findall(r"\b0[xX][0-9A-Fa-f]+\b", code)),
                )
            )

    categories_in_order: list[str] = []
    group_numbers: dict[str, list[int]] = {}
    group_widths: dict[str, list[int]] = {}
    for category, group_number, width in groups:
        if category not in group_numbers:
            categories_in_order.append(category)
            group_numbers[category] = []
            group_widths[category] = []
        group_numbers[category].append(group_number)
        group_widths[category].append(width)

    expected_total = 7 + 6 * 8 * 11
    layout_valid = (
        declared_size == expected_total
        and len(values) == expected_total
        and tuple(categories_in_order) == EXPECTED_LUT_CATEGORIES
        and all(group_numbers.get(category) == list(range(1, 9)) for category in EXPECTED_LUT_CATEGORIES)
        and all(group_widths.get(category) == [11] * 8 for category in EXPECTED_LUT_CATEGORIES)
        and len(groups) == 6 * 8
    )
    command_writer = re.search(
        r"\bvoid\s+EPD_WriteCMD\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+EPD_WriteDATA\s*\()",
        text,
        flags=re.DOTALL,
    )
    data_writer = re.search(
        r"\bvoid\s+EPD_WriteDATA\s*\([^)]*\)\s*\{(.*?)(?=\n\s*(?://|void|unsigned))",
        text,
        flags=re.DOTALL,
    )
    if command_writer is None or data_writer is None:
        raise AuditError("cannot locate the plaintext LUT CS write path")
    write_path = command_writer.group(1) + data_writer.group(1)
    master_only_write_path = (
        "E_Paper_CS" in write_path and "E_Paper_SLAVE_CS" not in write_path
    )

    epd_initial = re.search(
        r"\bvoid\s+EPD_initial\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if epd_initial is None:
        raise AuditError("cannot locate EPD_initial runtime LUT application")
    epd_initial_body = epd_initial.group(1)
    header_assignments = {
        field: re.search(
            rf"EPD_setting\.{field}\s*=\s*wf_data\s*\[\s*{index}\s*\]",
            text,
        )
        is not None
        for index, field in enumerate(("unused", "V1", "V2", "V3", "V4", "VCOM", "Frame"))
        if index > 0
    }
    power_fields_applied = all(
        re.search(rf"EPD_WriteDATA\s*\(\s*EPD_setting\.{field}\s*\)", epd_initial_body)
        is not None
        for field in ("V1", "V2", "V3", "V4")
    )
    header_vcom_applied = "EPD_setting.VCOM" in epd_initial_body
    header_frame_applied = "EPD_setting.Frame" in epd_initial_body
    vcom_uses_separate_global = (
        re.search(r"EPD_WriteDATA\s*\(\s*vcom\s*\|\s*0x80\s*\)", epd_initial_body)
        is not None
    )
    pll_is_hard_coded = (
        re.search(
            r"EPD_WriteCMD\s*\(\s*0x30\s*\).*?EPD_WriteDATA\s*\(\s*0x08\s*\)",
            epd_initial_body,
            flags=re.DOTALL,
        )
        is not None
    )
    full_panel_tres = all(
        token in epd_initial_body
        for token in (
            "LCD_XSIZE/256",
            "LCD_XSIZE%256",
            "LCD_YSIZE/256",
            "LCD_YSIZE%256",
        )
    )
    cascade_config_present = (
        re.search(r"EPD_WriteCMD\s*\(\s*0x[eE]0\s*\)", epd_initial_body)
        is not None
    )

    uart_text = _read_text(root, UART_DATA_REL)
    uart_save = re.search(
        r"\bvoid\s+Uart_save_wf_data\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        uart_text,
        flags=re.DOTALL,
    )
    if uart_save is None:
        raise AuditError("cannot locate Uart_save_wf_data")
    uart_body = uart_save.group(1)
    uart_fixed_copy = (
        re.search(
            r"memcpy\s*\(\s*wf_data\s*,\s*dat_buff\s*,\s*WF_DATA_LENGTH\s*\)",
            uart_body,
        )
        is not None
    )
    uart_length_checked = re.search(r"\bbuff_len\b", uart_body) is not None
    busy_wait = re.search(
        r"\bvoid\s+EPD_Check_Busy\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if busy_wait is None:
        raise AuditError("cannot locate EPD_Check_Busy")
    busy_body = _strip_c_comments(busy_wait.group(1))
    busy_wait_is_unbounded = (
        re.search(r"\bwhile\s*\(\s*1\s*\)", busy_body) is not None
        and re.search(r"HAL_GetTick|millis|timeout|time_out", busy_body, flags=re.IGNORECASE)
        is None
    )
    return {
        "path": EDP_INIT_REL.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "declared_size": declared_size,
        "actual_value_count": len(values),
        "initializer_sha256": _sha256(bytes(values)),
        "layout": {
            "header_values": 7,
            "category_count": 6,
            "groups_per_category": 8,
            "values_per_group": 11,
            "formula": "7 + 6 * 8 * 11",
            "expected_total": expected_total,
        },
        "categories": categories_in_order,
        "group_numbers": group_numbers,
        "only_expected_categories": set(categories_in_order) == set(EXPECTED_LUT_CATEGORIES),
        "layout_valid": layout_valid,
        "write_path": {
            "master_cs_symbol": "E_Paper_CS",
            "slave_cs_symbol_present": "E_Paper_SLAVE_CS" in write_path,
            "master_only": master_only_write_path,
        },
        "application_contract": {
            "header_fields_loaded": header_assignments,
            "power_fields_v1_to_v4_applied": power_fields_applied,
            "header_vcom_applied": header_vcom_applied,
            "header_frame_applied": header_frame_applied,
            "vcom_uses_separate_global": vcom_uses_separate_global,
            "pll_frame_is_hard_coded": pll_is_hard_coded,
            "header_runtime_mismatch": (
                all(header_assignments.values())
                and power_fields_applied
                and not header_vcom_applied
                and not header_frame_applied
                and vcom_uses_separate_global
                and pll_is_hard_coded
            ),
            "tres_uses_full_1024x600_macros": full_panel_tres,
            "cascade_config_present": cascade_config_present,
            "master_only_full_panel_geometry_mismatch": (
                master_only_write_path and full_panel_tres and not cascade_config_present
            ),
            "busy_wait_timeout_present": not busy_wait_is_unbounded,
            "unbounded_busy_wait": busy_wait_is_unbounded,
        },
        "uart_update_contract": {
            "path": UART_DATA_REL.as_posix(),
            "fixed_535_copy": uart_fixed_copy,
            "provided_length_checked": uart_length_checked,
            "unsafe_length_contract": uart_fixed_copy and not uart_length_checked,
        },
    }


def _audit_packaged_waveform(root: Path) -> dict[str, Any]:
    payload = _read_bytes(root, WF_HEADER_REL)
    text = payload.decode("latin-1")
    declared = re.search(r"^\s*#define\s+SIZE\s+(\d+)\b", text, flags=re.MULTILINE)
    if declared is None:
        raise AuditError("cannot locate WF20_25 SIZE")
    initializer = _extract_initializer(
        text,
        r"\bWF20_25\s*\[\s*SIZE\s*\]\s*=",
        "WF20_25",
    )
    values = _hex_values(initializer)
    banner_2bit = re.search(
        r"E5\s+2-bit\s+DEvelopment\s+Environment",
        text,
        flags=re.IGNORECASE,
    ) is not None
    wrapper = bytes(values)
    source_text = _read_text(root, E28XX_SOURCE_REL)
    key_match = re.search(
        r'\bcustomer_key\s*\[\s*\]\s*=\s*"([^"]+)"',
        source_text,
    )
    if key_match is None:
        raise AuditError("cannot locate customer_key metadata")
    customer_key = key_match.group(1).encode("ascii")

    loader_ciphertext_bytes = 0x220
    loader_key_length_offset = loader_ciphertext_bytes
    loader_wrapped_key_offset = loader_key_length_offset + 2
    loader_key_length = int.from_bytes(
        wrapper[loader_key_length_offset:loader_wrapped_key_offset],
        "big",
    )
    loader_key_field_fits = (
        loader_wrapped_key_offset + loader_key_length <= len(wrapper)
    )

    # The supplied wrapper has a self-consistent tail at a different offset.
    # This is only a structural predicate.  No waveform bytes are decrypted or
    # emitted, and the alternate layout is not promoted to a live-load format.
    candidate_key_length_offset = len(wrapper) - 2 - len(customer_key)
    candidate_wrapped_key_offset = candidate_key_length_offset + 2
    candidate_key_length = int.from_bytes(
        wrapper[candidate_key_length_offset:candidate_wrapped_key_offset],
        "big",
    )
    candidate_wrapped_key = wrapper[candidate_wrapped_key_offset:]
    recovered_candidate_key = bytes(
        candidate_wrapped_key[index] ^ wrapper[index]
        for index in range(len(candidate_wrapped_key))
    )
    candidate_key_matches_source = (
        candidate_key_length == len(customer_key)
        and recovered_candidate_key == customer_key
    )
    sample_main = _read_text(root, SAMPLE_MAIN_REL)
    required_include = re.search(r'#include\s+"(WF00_05\.h)"', sample_main)
    required_include_name = required_include.group(1) if required_include else None
    required_include_present = (
        required_include_name is not None and (root / "Sample Code" / required_include_name).is_file()
    )
    return {
        "path": WF_HEADER_REL.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "declared_size": int(declared.group(1)),
        "actual_value_count": len(values),
        "initializer_sha256": _sha256(wrapper),
        "banner": "E5 2-bit Development Environment" if banner_2bit else None,
        "is_e5_2bit": banner_2bit,
        "size_valid": int(declared.group(1)) == 842 and len(values) == 842,
        "loader_abi": {
            "fixed_ciphertext_bytes": loader_ciphertext_bytes,
            "key_length_offset": loader_key_length_offset,
            "key_length_encoding": "two-byte big-endian",
            "wrapped_key_offset": loader_wrapped_key_offset,
            "observed_key_length": loader_key_length,
            "key_field_fits_wrapper": loader_key_field_fits,
            "compatible_with_supplied_loader": False,
        },
        "different_candidate_layout": {
            "ciphertext_bytes": candidate_key_length_offset,
            "key_length_offset": candidate_key_length_offset,
            "key_length": candidate_key_length,
            "wrapped_key_offset": candidate_wrapped_key_offset,
            "wrapped_key_bytes": len(candidate_wrapped_key),
            "wrapped_key_sha256": _sha256(candidate_wrapped_key),
            "recovered_key_matches_source": candidate_key_matches_source,
            "classification": (
                "self-consistent 800+2+40 candidate layout incompatible with "
                "supplied 544-byte loader"
            ),
            "matching_loader_supplied": False,
            "authoritative_abi_proven": False,
            "valid_waveform_proven": False,
            "relative_age_inferred": False,
        },
        "customer_key_metadata": {
            "source_path": E28XX_SOURCE_REL.as_posix(),
            "bytes": len(customer_key),
            "sha256": _sha256(customer_key),
            "raw_value_emitted": False,
        },
        "sample_main_required_waveform": {
            "include": required_include_name,
            "present": required_include_present,
        },
        "raw_values_emitted": False,
    }


def _parse_ar_members(payload: bytes) -> list[dict[str, Any]]:
    if not payload.startswith(b"!<arch>\n"):
        return []
    position = 8
    raw_members: list[tuple[str, int, bytes]] = []
    while position < len(payload):
        if position + 60 > len(payload):
            raise AuditError("truncated ar member header")
        header = payload[position : position + 60]
        if header[58:60] != b"`\n":
            raise AuditError("invalid ar member header trailer")
        raw_name = header[:16].decode("ascii", errors="replace").strip()
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as error:
            raise AuditError("invalid ar member size") from error
        start = position + 60
        end = start + size
        if end > len(payload):
            raise AuditError("truncated ar member body")
        raw_members.append((raw_name, size, payload[start:end]))
        position = end + (size & 1)

    string_table = next((body for name, _, body in raw_members if name == "//"), b"")
    members: list[dict[str, Any]] = []
    for raw_name, size, body in raw_members:
        name = raw_name
        if re.fullmatch(r"/\d+", raw_name) and string_table:
            offset = int(raw_name[1:])
            tail = string_table[offset:]
            terminators = [index for token in (b"/\n", b"\n", b"/") if (index := tail.find(token)) >= 0]
            stop = min(terminators) if terminators else len(tail)
            name = tail[:stop].decode("ascii", errors="replace")
        elif raw_name.endswith("/") and raw_name not in ("/", "//"):
            name = raw_name[:-1]
        kind = "object"
        if raw_name == "/":
            kind = "symbol_table"
        elif raw_name == "//":
            kind = "string_table"
        members.append(
            {
                "name": name,
                "raw_name": raw_name,
                "bytes": size,
                "kind": kind,
                "object_magic_hex": body[:4].hex() if kind == "object" else None,
            }
        )
    return members


def _extract_ar_member(payload: bytes, member_name: str) -> tuple[bytes, int]:
    """Return an ar member body and its archive data offset."""

    if not payload.startswith(b"!<arch>\n"):
        raise AuditError("library is not a Unix ar archive")
    position = 8
    records: list[tuple[str, int, bytes]] = []
    while position < len(payload):
        if position + 60 > len(payload):
            raise AuditError("truncated ar member header")
        header = payload[position : position + 60]
        if header[58:60] != b"`\n":
            raise AuditError("invalid ar member header trailer")
        raw_name = header[:16].decode("ascii", errors="replace").strip()
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as error:
            raise AuditError("invalid ar member size") from error
        data_offset = position + 60
        end = data_offset + size
        if end > len(payload):
            raise AuditError("truncated ar member body")
        records.append((raw_name, data_offset, payload[data_offset:end]))
        position = end + (size & 1)

    string_table = next((body for name, _, body in records if name == "//"), b"")
    for raw_name, data_offset, body in records:
        resolved_name = raw_name
        if re.fullmatch(r"/\d+", raw_name) and string_table:
            offset = int(raw_name[1:])
            tail = string_table[offset:]
            terminators = [
                index
                for token in (b"/\n", b"\n", b"/")
                if (index := tail.find(token)) >= 0
            ]
            stop = min(terminators) if terminators else len(tail)
            resolved_name = tail[:stop].decode("ascii", errors="replace")
        elif raw_name.endswith("/") and raw_name not in ("/", "//"):
            resolved_name = raw_name[:-1]
        if resolved_name == member_name:
            return body, data_offset
    raise AuditError(f"ar member is missing: {member_name}")


def _audit_library(root: Path) -> dict[str, Any]:
    payload = _read_bytes(root, LIB_REL)
    is_ar = payload.startswith(b"!<arch>\n")
    markers = {name: marker in payload for name, marker in EXPECTED_LIB_MARKERS.items()}
    members = _parse_ar_members(payload) if is_ar else []
    object_body, object_archive_offset = _extract_ar_member(payload, EXPECTED_OBJECT_NAME)
    code_stream = object_body[
        ORC_CODE_STREAM_OFFSET : ORC_CODE_STREAM_OFFSET + ORC_CODE_STREAM_BYTES
    ]
    loadwf_code = code_stream[
        LOADWF_CODE_OFFSET : LOADWF_CODE_OFFSET + LOADWF_CODE_BYTES
    ]
    decrypt_check_code = code_stream[
        DECRYPT_CHECK_CODE_OFFSET : DECRYPT_CHECK_CODE_OFFSET + DECRYPT_CHECK_CODE_BYTES
    ]
    exact_binary_identity = all(
        (
            _sha256(payload) == EXPECTED_LIBRARY_SHA256,
            _sha256(object_body) == EXPECTED_OBJECT_SHA256,
            object_body[:4] == bytes.fromhex("f74f5243"),
            len(code_stream) == ORC_CODE_STREAM_BYTES,
            _sha256(code_stream) == EXPECTED_CODE_STREAM_SHA256,
            len(loadwf_code) == LOADWF_CODE_BYTES,
            _sha256(loadwf_code) == EXPECTED_LOADWF_SHA256,
            len(decrypt_check_code) == DECRYPT_CHECK_CODE_BYTES,
            _sha256(decrypt_check_code) == EXPECTED_DECRYPT_CHECK_SHA256,
        )
    )
    if not exact_binary_identity:
        raise AuditError("vendor loadWF binary identity or code boundary mismatch")
    return {
        "path": LIB_REL.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "format": "unix-ar" if is_ar else "unknown",
        "is_ar_archive": is_ar,
        "members": members,
        "markers": markers,
        "all_required_markers_present": all(markers.values()),
        "e5_3bit_mode_macro_value": 0 if markers["e5_3bit_mode_macro"] else None,
        "e5_3bit_mode_zero_semantics_known": False,
        "decoded_waveform_size": 544 if markers["decoded_size_544"] else None,
        "lut_waveform_size": 535 if markers["waveform_size_535"] else None,
        "reverse_contract": {
            "method": (
                "exact ar/member/code-range SHA-256 plus local Thumb disassembly; "
                "CROF relocations remain unresolved"
            ),
            "exact_binary_identity": exact_binary_identity,
            "object": {
                "name": EXPECTED_OBJECT_NAME,
                "archive_data_offset": object_archive_offset,
                "archive_data_offset_hex": f"0x{object_archive_offset:X}",
                "bytes": len(object_body),
                "sha256": _sha256(object_body),
                "magic_hex": object_body[:4].hex(),
                "format": "ArmCC ORC/CROF, not standard ELF",
                "compiler_banner_present": (
                    b"ARM Compiler 5.06 update 3 (build 300)" in object_body
                ),
                "evaluation_macro_present": b"__EVAL" in object_body,
            },
            "code_stream": {
                "member_offset": ORC_CODE_STREAM_OFFSET,
                "member_offset_hex": f"0x{ORC_CODE_STREAM_OFFSET:X}",
                "archive_offset": object_archive_offset + ORC_CODE_STREAM_OFFSET,
                "archive_offset_hex": (
                    f"0x{object_archive_offset + ORC_CODE_STREAM_OFFSET:X}"
                ),
                "bytes": len(code_stream),
                "sha256": _sha256(code_stream),
            },
            "loadwf": {
                "actual_return_type": "uint8_t",
                "code_stream_offset": LOADWF_CODE_OFFSET,
                "code_stream_offset_hex": f"0x{LOADWF_CODE_OFFSET:X}",
                "member_offset": ORC_CODE_STREAM_OFFSET + LOADWF_CODE_OFFSET,
                "member_offset_hex": (
                    f"0x{ORC_CODE_STREAM_OFFSET + LOADWF_CODE_OFFSET:X}"
                ),
                "archive_offset": (
                    object_archive_offset + ORC_CODE_STREAM_OFFSET + LOADWF_CODE_OFFSET
                ),
                "archive_offset_hex": (
                    "0x"
                    f"{object_archive_offset + ORC_CODE_STREAM_OFFSET + LOADWF_CODE_OFFSET:X}"
                ),
                "bytes": len(loadwf_code),
                "sha256": _sha256(loadwf_code),
                "returns": {
                    "0x00": "success",
                    "0xE1": "key check failed",
                    "0xE2": "waveform/decrypt flag failed",
                },
                "success_writes": [
                    {
                        "command": "0x01",
                        "bytes": 6,
                        "source": "0x0F followed by decoded bytes 0..4",
                    },
                    {"command": "0x30", "bytes": 1, "source": "decoded byte 6"},
                    {
                        "command": "0x20",
                        "bytes": 535,
                        "source": "decoded global buffer",
                    },
                    {
                        "command": "0x21",
                        "bytes": 704,
                        "source": "library-resident LUT1_DATA global",
                    },
                ],
                "controller_or_cs_argument": False,
                "busy_poll_present": False,
                "refresh_sequence_present": False,
                "otp_recovery_present": False,
            },
            "decrypt_check": {
                "code_stream_offset": DECRYPT_CHECK_CODE_OFFSET,
                "code_stream_offset_hex": f"0x{DECRYPT_CHECK_CODE_OFFSET:X}",
                "member_offset": ORC_CODE_STREAM_OFFSET + DECRYPT_CHECK_CODE_OFFSET,
                "member_offset_hex": (
                    f"0x{ORC_CODE_STREAM_OFFSET + DECRYPT_CHECK_CODE_OFFSET:X}"
                ),
                "archive_offset": (
                    object_archive_offset
                    + ORC_CODE_STREAM_OFFSET
                    + DECRYPT_CHECK_CODE_OFFSET
                ),
                "archive_offset_hex": (
                    "0x"
                    f"{object_archive_offset + ORC_CODE_STREAM_OFFSET + DECRYPT_CHECK_CODE_OFFSET:X}"
                ),
                "bytes": len(decrypt_check_code),
                "sha256": _sha256(decrypt_check_code),
                "fixed_ciphertext_bytes": 544,
                "key_length_offset": 544,
                "key_length_encoding": "two-byte big-endian",
                "wrapped_key_offset": 546,
                "wrapped_key_bounds_check_present": False,
                "key_validation": (
                    "wrapped_key[i] XOR wrapper[i], then exact length/byte comparison"
                ),
                "aes_key_derivation": "SHA-256(recovered key)",
                "aes_iv_derivation": "MD5(recovered key)",
                "cipher": "AES-256-CBC over exactly 544 bytes",
            },
            "lut1_data": {
                "public_symbol_present": markers["lut1_data"],
                "write_command": "0x21",
                "write_bytes": 704,
                "derived_from_caller_wrapper_by_loadwf": False,
                "const_qualification_proven": False,
                "authoritative_bytes_or_hash_recovered": False,
                "phase_or_color_semantics_proven": False,
            },
        },
        "waveform_decrypted": False,
        "customer_key_material_emitted": False,
    }


def _required_int_define(text: str, name: str, path: Path) -> int:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+(\d+)\b", text, flags=re.MULTILINE)
    if match is None:
        raise AuditError(f"cannot locate {name} in {path.as_posix()}")
    return int(match.group(1))


def _audit_lcd(root: Path) -> dict[str, Any]:
    payload = _read_bytes(root, LCD_CONFIG_REL)
    text = payload.decode("latin-1")
    width = _required_int_define(text, "LCD_XSIZE", LCD_CONFIG_REL)
    height = _required_int_define(text, "LCD_YSIZE", LCD_CONFIG_REL)
    return {
        "path": LCD_CONFIG_REL.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "width": width,
        "height": height,
        "is_1024x600": width == 1024 and height == 600,
    }


def _audit_project(root: Path) -> dict[str, Any]:
    payload = _read_bytes(root, UVPROJ_REL)
    text = payload.decode("latin-1")
    expected = {
        "e28xx_source": r"..\..\Sample Code\E28xx.c",
        "edp_init_source": r"..\..\User\EDP_init.c",
        "waveform_library": r"..\..\lib\eload_3bits_M3_E2802_20251229.lib",
    }
    included = {name: path in text for name, path in expected.items()}
    return {
        "path": UVPROJ_REL.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "includes": included,
        "all_required_inputs_listed": all(included.values()),
    }


def _newest_m009_map(root: Path) -> Path:
    output = root / "Output"
    candidates = [path for path in output.glob("*M009F-T*.map") if path.is_file()]
    if not candidates:
        raise AuditError("no M009F-T linker map found")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _audit_map(root: Path) -> dict[str, Any]:
    map_path = _newest_m009_map(root)
    payload = map_path.read_bytes()
    text = payload.decode("latin-1")
    relative = map_path.relative_to(root)
    nootp_removed = re.search(
        r"Removing\s+main\.o\(i\.EPD_initial_noOTP\),\s*\(288 bytes\)\.", text
    ) is not None
    wf_const_removed = re.search(
        r"Removing\s+main\.o\(\.constdata\),\s*\(842 bytes\)\.", text
    ) is not None
    epd_initial_from_e28xx = (
        re.search(r"main\.o\(i\.main\) refers to e28xx\.o\(i\.epdInitial\)", text) is not None
        and re.search(r"\bepdInitial\b.*\be28xx\.o\(i\.epdInitial\)", text) is not None
    )
    loadwf_linked = re.search(r"\bloadWF\b", text) is not None
    plain_2bit_lut_linked = all(
        re.search(pattern, text) is not None
        for pattern in (
            r"\bi\.EPD_initial\b",
            r"\bi\.Uart_save_wf_data\b",
            r"\bwf_data\s+0x[0-9a-fA-F]+\s+Data\s+535\s+edp_init\.o",
        )
    )
    return {
        "path": relative.as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "selected_as_newest_m009_map": True,
        "epd_initial_nootp_removed": nootp_removed,
        "main_constdata_842_removed": wf_const_removed,
        "epd_initial_provider": "e28xx.o" if epd_initial_from_e28xx else None,
        "epd_initial_from_e28xx": epd_initial_from_e28xx,
        "encrypted_loadwf_linked": loadwf_linked,
        "plain_2bit_runtime_lut_linked": plain_2bit_lut_linked,
        "proves_encrypted_loadwf_path_absent": (
            nootp_removed and wf_const_removed and epd_initial_from_e28xx and not loadwf_linked
        ),
        "mtime_ns": map_path.stat().st_mtime_ns,
    }


def _audit_loadwf_contract(root: Path) -> dict[str, Any]:
    header = _read_text(root, E28XX_HEADER_REL)
    caller = _read_text(root, SAMPLE_MAIN_REL)
    source = _read_text(root, E28XX_SOURCE_REL)
    legacy = _read_text(root, EDP_INIT_REL)
    project = _read_text(root, UVPROJ_REL)
    declaration = re.search(
        r"\b(void|unsigned\s+char|uint8_t)\s+loadWF\s*\(\s*const\s+unsigned\s+char\s*\*",
        header,
    )
    if declaration is None:
        raise AuditError("cannot locate loadWF declaration")
    assignment_count = len(re.findall(r"\bresOfLoadWF\s*=\s*loadWF\s*\(", caller))
    unsigned_result = re.search(r"\bunsigned\s+char\s+resOfLoadWF\b", caller) is not None
    conflict = declaration.group(1) == "void" and assignment_count > 0 and unsigned_result
    sample_main_is_project_entry = r"..\..\Sample Code\main.c" in project
    user_main_is_project_entry = r"..\..\User\main.c" in project
    undefined_selector_assignment = (
        "spiChipSelect=MAS_SLA" in caller
        and re.search(r"\b(?:spiChipSelect|MAS_SLA)\b", header + source) is None
    )
    writeepd = re.search(
        r"\bvoid\s+writeEPD\s*\([^)]*\)\s*\{(.*?)(?=\n\s*(?:void|unsigned))",
        source,
        flags=re.DOTALL,
    )
    if writeepd is None:
        raise AuditError("cannot locate writeEPD source glue")
    writeepd_body = writeepd.group(1)
    legacy_command = re.search(
        r"\bvoid\s+EPD_WriteCMD\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+EPD_WriteDATA)",
        legacy,
        flags=re.DOTALL,
    )
    legacy_data = re.search(
        r"\bvoid\s+EPD_WriteDATA\s*\([^)]*\)\s*\{(.*?)(?=\n\s*(?://|void))",
        legacy,
        flags=re.DOTALL,
    )
    if legacy_command is None or legacy_data is None:
        raise AuditError("cannot locate legacy writeEPD target glue")
    legacy_write_path = legacy_command.group(1) + legacy_data.group(1)
    writeepd_uses_generic_path = all(
        token in writeepd_body for token in ("sendSPICommand", "sendMutipleSPIData")
    )
    legacy_path_master_only = (
        "E_Paper_CS" in legacy_write_path
        and "E_Paper_SLAVE_CS" not in legacy_write_path
    )
    return {
        "header_path": E28XX_HEADER_REL.as_posix(),
        "caller_path": SAMPLE_MAIN_REL.as_posix(),
        "header_return_type": declaration.group(1),
        "caller_result_type": "unsigned char" if unsigned_result else None,
        "assigned_call_count": assignment_count,
        "return_type_conflict": conflict,
        "binary_actual_return_type": "uint8_t",
        "binary_proves_header_wrong": conflict,
        "sample_main_is_project_entry": sample_main_is_project_entry,
        "user_main_is_project_entry": user_main_is_project_entry,
        "sample_main_selector_symbols_missing": undefined_selector_assignment,
        "dual_controller": {
            "handled_inside_loadwf": False,
            "loadwf_target_argument": False,
            "delegation": "external writeEPD(command, data, length)",
            "writeepd_uses_generic_path": writeepd_uses_generic_path,
            "legacy_path_observed_cs": "E_Paper_CS only" if legacy_path_master_only else None,
            "legacy_path_master_only": legacy_path_master_only,
            "separate_dual_target_apis_exist": all(
                token in legacy
                for token in (
                    "EPD_Select_Master",
                    "EPD_Select_Slave",
                    "EPD_Select_Both",
                )
            ),
            "selector_assignment_proves_broadcast": False,
            "verified_dual_controller_load": False,
        },
    }


def _audit_uart_control_plane(root: Path) -> dict[str, Any]:
    usart = _read_text(root, USART_SOURCE_REL)
    uart_data = _read_text(root, UART_DATA_REL)
    main = _read_text(root, USER_MAIN_REL)
    epd = _read_text(root, EDP_INIT_REL)

    command_bodies: dict[int, str] = {}
    for command in (5, 7, 8):
        match = re.search(
            rf"\bcase\s+{command}\s*:(.*?)(?=\n\s*case\s+\d+\s*:|\n\s*\}})",
            usart,
            flags=re.DOTALL,
        )
        if match is None:
            raise AuditError(f"cannot locate UART command {command}")
        command_bodies[command] = match.group(1)

    set_branch = re.search(
        r"else\s+if\s*\(\s*usart_cmd\s*==\s*USART_CMD_SET_VCOM\s*\)\s*"
        r"\{(.*?)\n\s*\}",
        main,
        flags=re.DOTALL,
    )
    if set_branch is None:
        raise AuditError("cannot locate main SET_VCOM branch")
    set_branch_body = set_branch.group(1)
    waveform_handler = re.search(
        r"void\s+Uart_save_wf_data\s*\([^)]*\)\s*\{(.*?)\n\s*\}",
        uart_data,
        flags=re.DOTALL,
    )
    if waveform_handler is None:
        raise AuditError("cannot locate Uart_save_wf_data body")
    waveform_handler_body = waveform_handler.group(1)

    control_sources: list[str] = []
    for relative_root in (Path("User"), Path("Sample Code"), Path("Drivers/SYSTEM")):
        source_root = root / relative_root
        for path in source_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {
                ".c",
                ".h",
                ".txt",
                ".xml",
                ".uvprojx",
            }:
                control_sources.append(path.read_bytes().decode("latin-1", errors="replace"))
    control_text = "\n".join(control_sources)
    bluetooth_marker = re.search(
        r"\bBluetooth\b|\bBLE\b|\bGATT\b|\bcharacteristic\b",
        control_text,
        flags=re.IGNORECASE,
    )
    wireless_app_artifact = any(
        path.is_file() and path.suffix.lower() in {".apk", ".ipa"}
        for path in root.rglob("*")
    )

    command_5 = command_bodies[5]
    command_7 = command_bodies[7]
    command_8 = command_bodies[8]
    packet_frame_proven = all(
        token in usart
        for token in (
            "USART1_RData[0]==0x41",
            "USART1_RData[1]==0x41",
            "USART1_RData[number_sum-1]==0x0D",
            "cmd_type   = USART1_RData[4]",
            "ComputeChecksumBytes(USART1_RData,number_sum-3)",
        )
    )
    set_updates_raw_vcom = re.search(
        r"\bvcom\s*=\s*USART1_RData\s*\[\s*6\s*\]",
        command_8,
    ) is not None
    set_range_validation = re.search(r"\b(?:if|switch)\s*\(", command_8) is not None
    set_direct_epd_write = re.search(r"\bEPD_Write(?:CMD|DATA)\s*\(", set_branch_body) is not None
    set_ack_only = "Uart_ask_set_vcom();" in set_branch_body and not set_direct_epd_write
    return {
        "paths": {
            "parser": USART_SOURCE_REL.as_posix(),
            "handlers": UART_DATA_REL.as_posix(),
            "dispatch": USER_MAIN_REL.as_posix(),
            "legacy_epd": EDP_INIT_REL.as_posix(),
        },
        "supplied_transport_evidence": {
            "uart1_protocol_present": packet_frame_proven,
            "bluetooth_or_ble_stack_present": bluetooth_marker is not None,
            "gatt_contract_present": False,
            "wireless_app_artifact_present": wireless_app_artifact,
            "bluetooth_to_uart_bridge_proven": False,
            "only_uart_side_of_possible_bridge_is_supplied": True,
        },
        "physical_uart": {
            "instance": "USART1" if "huart1.Instance = USART1" in usart else None,
            "tx_pin": "PA9"
            if "GPIO_InitStruct.Pin = GPIO_PIN_9" in usart
            and "GPIO_MODE_AF_PP" in usart
            else None,
            "rx_pin": "PA10"
            if "GPIO_InitStruct.Pin = GPIO_PIN_10" in usart
            and "GPIO_MODE_INPUT" in usart
            else None,
            "baud": 115200 if "huart1.Init.BaudRate = 115200" in usart else None,
            "data_bits": 8 if "UART_WORDLENGTH_8B" in usart else None,
            "stop_bits": 1 if "UART_STOPBITS_1" in usart else None,
            "parity": "none" if "UART_PARITY_NONE" in usart else None,
            "hardware_flow_control": "none"
            if "UART_HWCONTROL_NONE" in usart
            else None,
            "rx_dma_and_idle_irq": (
                "HAL_UART_Receive_DMA" in usart
                and "__HAL_UART_ENABLE_IT(&huart1, UART_IT_IDLE)" in usart
            ),
        },
        "frame": {
            "header_hex": "41 41",
            "length_encoding": "two-byte big-endian at offsets 2..3",
            "command_type_offset": 4,
            "command_subtype_offset": 5,
            "payload_offset": 6,
            "crc": "CRC-16 over bytes before the final CRC and terminator",
            "terminator_hex": "0D",
            "validated_by_source": packet_frame_proven,
        },
        "commands": {
            "5": {
                "observed_role": "legacy plaintext waveform upload",
                "calls_uart_save_wf_data": "Uart_save_wf_data" in command_5,
                "declared_payload_length_expression": "number_sum - 9",
                "downstream_fixed_copy_bytes": 535,
                "downstream_fixed_copy_present": (
                    "memcpy(wf_data,dat_buff,WF_DATA_LENGTH)" in waveform_handler_body
                ),
                "downstream_checks_supplied_length": "buff_len" in waveform_handler_body,
            },
            "7": {
                "observed_role": "request VCOM measurement/readback",
                "sets_get_vcom_dispatch": "USART_CMD_GET_VCOM" in command_7,
                "later_calls_get_vcom": "get_vcom();" in main,
                "controller_read_register": "0x81" if "EPD_Read_reg(0x81,&vcom,1)" in epd else None,
            },
            "8": {
                "observed_role": "set unchecked raw VCOM byte in RAM",
                "sets_set_vcom_dispatch": "USART_CMD_SET_VCOM" in command_8,
                "source_byte_offset": 6,
                "updates_global_vcom": set_updates_raw_vcom,
                "range_or_unit_validation_present": set_range_validation,
                "main_branch_ack_only": set_ack_only,
                "direct_controller_write_in_set_branch": set_direct_epd_write,
                "commented_epd_setting_assignment_present": re.search(
                    r"//\s*EPD_setting\.VCOM\s*=\s*vcom",
                    set_branch_body,
                )
                is not None,
            },
        },
        "application_semantics": {
            "legacy_initial_later_writes_vcom_or_0x80": "EPD_WriteDATA(vcom|0x80)" in epd,
            "legacy_initial_is_master_only": True,
            "all_display_paths_reinitialize_legacy_path": False,
            "direct_brightness_command_present": re.search(
                r"\bbrightness\b|\blightness\b|\bluminance\b",
                control_text,
                flags=re.IGNORECASE,
            )
            is not None,
            "direct_contrast_command_present": re.search(
                r"\bcontrast\b",
                control_text,
                flags=re.IGNORECASE,
            )
            is not None,
            "waveform_upload_brightness_or_contrast_semantics_proven": False,
            "raw_vcom_is_approved_brightness_control": False,
            "contrast_mapping_proven": False,
        },
    }


def _function_nibble(text: str, function_name: str) -> int:
    function = re.search(
        rf"\bvoid\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if function is None:
        raise AuditError(f"cannot locate {function_name}")
    data = re.search(r"EPD_WriteDATA_To(?:Master|Slave)\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)", function.group(1))
    if data is None:
        raise AuditError(f"cannot locate color byte in {function_name}")
    byte = int(data.group(1), 16)
    if (byte >> 4) != (byte & 0x0F):
        raise AuditError(f"non-uniform packed color byte in {function_name}")
    return byte & 0x0F


def _function_data_byte(text: str, function_name: str) -> int:
    function = re.search(
        rf"\bvoid\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if function is None:
        raise AuditError(f"cannot locate {function_name}")
    data = re.search(r"EPD_WriteDATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)", function.group(1))
    if data is None:
        raise AuditError(f"cannot locate color byte in {function_name}")
    return int(data.group(1), 16)


def _audit_color_codes(root: Path) -> dict[str, Any]:
    user_source = _read_text(root, EDP_INIT_REL)
    user_single_color_bytes = {
        "black": _function_data_byte(user_source, "EPD_display_Black"),
        "white": _function_data_byte(user_source, "EPD_display_White"),
        "yellow": _function_data_byte(user_source, "EPD_display_yellow"),
        "red": _function_data_byte(user_source, "EPD_display_Red"),
    }
    combined = re.search(
        r"\bvoid\s+EPD_display_B_W_R_Y_B\s*\([^)]*\)\s*\{(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        user_source,
        flags=re.DOTALL,
    )
    if combined is None:
        raise AuditError("cannot locate EPD_display_B_W_R_Y_B")
    combined_literals = [
        int(value, 16)
        for value in re.findall(
            r"EPD_WriteDATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)",
            combined.group(1),
        )
    ]
    if combined_literals[:4] != [0x00, 0x55, 0xFF, 0xAA]:
        raise AuditError("unexpected B/W/R/Y combined 2-bit fill literals")
    user_uniform_2bit_bytes = dict(
        zip(("black", "white", "red", "yellow"), combined_literals[:4], strict=True)
    )
    user_2bit = {
        name: byte & 0x03 for name, byte in user_uniform_2bit_bytes.items()
    }
    single_color_conflict = user_single_color_bytes != user_uniform_2bit_bytes

    sample_source = _read_text(root, E28XX_SOURCE_REL)
    sample_3bit = {
        "black": _function_nibble(sample_source, "display_Black"),
        "white": _function_nibble(sample_source, "display_White"),
        "red": _function_nibble(sample_source, "display_Red"),
        "yellow": _function_nibble(sample_source, "display_Yellow"),
        "blue": _function_nibble(sample_source, "display_B"),
        "green": _function_nibble(sample_source, "display_G"),
    }
    esp_text = (REPO_ROOT / "src/epd_config.h").read_text(encoding="utf-8")
    esp: dict[str, int] = {}
    for name in ("BLACK", "WHITE", "YELLOW", "RED", "BLUE", "GREEN"):
        match = re.search(rf"EPD_COLOR_{name}\s*=\s*0x([0-9A-Fa-f]+)", esp_text)
        if match is None:
            raise AuditError(f"cannot locate ESP32 EPD_COLOR_{name}")
        esp[name.lower()] = int(match.group(1), 16)
    internal_conflict = (
        user_2bit["yellow"] == sample_3bit["red"]
        and user_2bit["red"] == sample_3bit["yellow"]
    )
    esp_matches_user_2bit = all(esp[name] == code for name, code in user_2bit.items())
    esp_matches_sample_3bit = all(esp[name] == code for name, code in sample_3bit.items())
    return {
        "user_2bit_path": EDP_INIT_REL.as_posix(),
        "sample_3bit_path": E28XX_SOURCE_REL.as_posix(),
        "esp32_path": "src/epd_config.h",
        "user_2bit": user_2bit,
        "user_2bit_packed_bytes": {
            name: f"0x{byte:02X}" for name, byte in user_uniform_2bit_bytes.items()
        },
        "user_single_color_function_bytes": {
            name: f"0x{byte:02X}" for name, byte in user_single_color_bytes.items()
        },
        "user_single_color_fill_conflict": single_color_conflict,
        "sample_3bit": sample_3bit,
        "esp32": esp,
        "internal_conflict": internal_conflict,
        "esp32_matches_user_2bit": esp_matches_user_2bit,
        "esp32_matches_sample_3bit": esp_matches_sample_3bit,
    }


def _audit_artifact_age(root: Path, map_report: dict[str, Any]) -> dict[str, Any]:
    main_path = root / USER_MAIN_REL
    map_path = root / Path(map_report["path"])
    main_mtime = main_path.stat().st_mtime_ns
    map_mtime = map_path.stat().st_mtime_ns
    return {
        "source_path": USER_MAIN_REL.as_posix(),
        "map_path": map_report["path"],
        "source_mtime_ns": main_mtime,
        "map_mtime_ns": map_mtime,
        "source_is_newer": main_mtime > map_mtime,
        "delta_seconds": (main_mtime - map_mtime) / 1_000_000_000,
    }


def _extract_void_function(text: str, function_name: str) -> str:
    function = re.search(
        rf"\bvoid\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{"
        r"(.*?)(?=\n\s*void\s+\w+\s*\(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if function is None:
        raise AuditError(f"cannot locate E6 function {function_name}")
    return function.group(1)


def _audit_e6_sample() -> dict[str, Any]:
    root = E6_REFERENCE_ROOT.resolve()
    if not root.is_dir():
        return {
            "present": False,
            "reference_root": str(root),
            "usable_as_target_lut_or_electrical_authority": False,
        }

    version_path = root / "Version_Descriptions.txt"
    main_path = root / "main.c"
    source_path = root / "E6_73.c"
    header_path = root / "E6_73.h"
    pin_path = root / "pindefine.h"
    for path in (version_path, main_path, source_path, header_path, pin_path):
        if not path.is_file():
            raise AuditError(f"required E6 sample file is missing: {path.name}")

    version_payload = version_path.read_bytes()
    main_payload = main_path.read_bytes()
    source_payload = source_path.read_bytes()
    header_payload = header_path.read_bytes()
    pin_payload = pin_path.read_bytes()
    version = version_payload.decode("latin-1")
    main = main_payload.decode("latin-1")
    source = source_payload.decode("latin-1")
    pins = pin_payload.decode("latin-1")

    tres = re.search(
        r"SPI_COMMAND\s*\(\s*TRES\s*\)\s*;\s*"
        r"SPI_DATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)\s*;\s*"
        r"SPI_DATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)\s*;\s*"
        r"SPI_DATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)\s*;\s*"
        r"SPI_DATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)",
        source,
        flags=re.DOTALL,
    )
    if tres is None:
        raise AuditError("cannot locate E6 TRES geometry")
    width = (int(tres.group(1), 16) << 8) | int(tres.group(2), 16)
    height = (int(tres.group(3), 16) << 8) | int(tres.group(4), 16)

    display_names = (
        "EPD_Display_White",
        "EPD_Display_Black",
        "EPD_Display_Yellow",
        "EPD_Display_Red",
        "EPD_Display_Blue",
        "EPD_Display_Green",
    )
    expected_bytes = {
        "EPD_Display_White": 0x11,
        "EPD_Display_Black": 0x00,
        "EPD_Display_Yellow": 0x22,
        "EPD_Display_Red": 0x33,
        "EPD_Display_Blue": 0x55,
        "EPD_Display_Green": 0x66,
    }
    displays: dict[str, dict[str, Any]] = {}
    all_cut_vdd = True
    all_have_expected_payload = True
    for name in display_names:
        body = _extract_void_function(source, name)
        loop = re.search(r"for\s*\([^;]+;\s*\w+\s*<\s*(\d+)\s*;", body)
        data = re.search(r"SPI_DATA\s*\(\s*0x([0-9A-Fa-f]{2})\s*\)", body)
        if loop is None or data is None:
            raise AuditError(f"cannot locate E6 packed payload for {name}")
        loop_bytes = int(loop.group(1))
        packed_byte = int(data.group(1), 16)
        cuts_vdd = all(token in body for token in ("CSB_L", "RSTN_L", "SDA_L", "SWC_L"))
        all_cut_vdd = all_cut_vdd and cuts_vdd
        all_have_expected_payload = (
            all_have_expected_payload
            and loop_bytes == width * height // 2
            and packed_byte == expected_bytes[name]
        )
        displays[name.removeprefix("EPD_Display_").lower()] = {
            "packed_byte": f"0x{packed_byte:02X}",
            "payload_bytes": loop_bytes,
            "vdd_cut_at_end": cuts_vdd,
        }

    init_calls = len(re.findall(r"\bEPD_Init\s*\(\s*\)\s*;", main))
    display_calls = len(re.findall(r"\bEPD_Display_\w+\s*\(\s*\)\s*;", main))
    first_display = main.find("EPD_Display_White();")
    later_repower = "SWC_H" in main[first_display:] if first_display >= 0 else False
    later_reinitialize = (
        "EPD_Init();" in main[first_display + len("EPD_Display_White();") :]
        if first_display >= 0
        else False
    )
    single_cs = "CSB_L" in pins and not re.search(r"SLAVE|CSB2|CS1", pins)
    source_level_lut_api = re.search(
        r"\b(?:loadWF|LUT1_DATA|R20_LUT0|R21_LUT1)\b",
        source + header_payload.decode("latin-1") + main,
    ) is not None
    brightness_api = re.search(
        r"\b(?:brightness|lightness|luminance|contrast)\b",
        source + main,
        flags=re.IGNORECASE,
    ) is not None
    sequence_inconsistent = (
        all_cut_vdd
        and init_calls == 1
        and display_calls == 7
        and not later_repower
        and not later_reinitialize
    )
    return {
        "present": True,
        "reference_root": str(root),
        "file_count": sum(1 for path in root.rglob("*") if path.is_file()),
        "files": {
            "Version_Descriptions.txt": {
                "bytes": len(version_payload),
                "sha256": _sha256(version_payload),
            },
            "main.c": {"bytes": len(main_payload), "sha256": _sha256(main_payload)},
            "E6_73.c": {
                "bytes": len(source_payload),
                "sha256": _sha256(source_payload),
            },
            "E6_73.h": {
                "bytes": len(header_payload),
                "sha256": _sha256(header_payload),
            },
        },
        "vendor_copyright_present": b"E Ink Holdings Inc." in source_payload,
        "version": "V1.2",
        "version_date": "2025-01-16",
        "version_adds_vdd_cut_each_display": (
            "V1.2 20250116" in version and "VDD cut sequence at each display" in version
        ),
        "declared_scope": "EL073 Version 2 host initialization",
        "only_el073_comment_present": "only avaliable for EL073 series" in main,
        "mcu": "MSP430F5502",
        "geometry": {
            "width": width,
            "height": height,
            "is_800x480": (width, height) == (800, 480),
        },
        "pixel_format": {
            "bits_per_pixel": 4,
            "pixels_per_byte": 2,
            "inference": "uniform doubled nibbles and 800*480/2-byte DTM loops",
            "all_six_payloads_consistent": all_have_expected_payload,
        },
        "colors": displays,
        "single_display_tail": {
            "sequence": [
                "DTM",
                "PON/busy",
                "DRF 0x00/busy",
                "POF 0x00/busy",
                "delay >=10 ms",
                "delay 6 s",
                "PSR 0x4F 0x6E/busy",
                "delay 1 s",
                "CS/RST/SDA low",
                "VDD switch off",
            ],
            "all_six_functions_cut_vdd": all_cut_vdd,
        },
        "main_sequence": {
            "initialization_calls": init_calls,
            "display_calls": display_calls,
            "repower_after_first_display": later_repower,
            "reinitialize_after_first_display": later_reinitialize,
            "v1_2_sequential_demo_internally_inconsistent": sequence_inconsistent,
        },
        "dual_reset_comment_means_two_reset_pulses": source.count("RSTN_L; // Reset") == 2,
        "single_cs_only": bool(single_cs),
        "source_level_runtime_lut_api_found": source_level_lut_api,
        "source_level_brightness_api_found": brightness_api,
        "usable_as_target_lut_or_electrical_authority": False,
    }


def audit(reference_root: Path = DEFAULT_REFERENCE_ROOT) -> dict[str, Any]:
    root = reference_root.resolve()
    if not root.is_dir():
        raise AuditError(f"reference root is not a directory: {root}")

    wf_data = _audit_wf_data(root)
    packaged = _audit_packaged_waveform(root)
    library = _audit_library(root)
    lcd = _audit_lcd(root)
    project = _audit_project(root)
    link_map = _audit_map(root)
    loadwf = _audit_loadwf_contract(root)
    uart_control = _audit_uart_control_plane(root)
    colors = _audit_color_codes(root)
    age = _audit_artifact_age(root, link_map)
    e6_sample = _audit_e6_sample()

    reasons = [
        {
            "code": "bit_depth_contract_mismatch",
            "evidence": "WF20_25 is labelled E5 2-bit while the 3bits-named library records E5_3Bit_Mode=0 with undocumented semantics",
        },
        {
            "code": "active_lut_has_no_blue_or_green_category",
            "evidence": "wf_data categories are VCOM, Black, White, Yellow, Red, and Power only",
        },
        {
            "code": "encrypted_3bit_loadwf_not_linked",
            "evidence": "the newest M009 map removes noOTP/842-byte constdata and has no loadWF symbol, although a separate plaintext 2-bit LUT path is linked",
        },
        {
            "code": "linked_plain_2bit_path_is_master_only",
            "evidence": "the linked 535-byte EPD_initial path writes E_Paper_CS but does not select E_Paper_SLAVE_CS",
        },
        {
            "code": "plaintext_lut_header_fields_not_applied",
            "evidence": "the 535-byte header VCOM and Frame fields are loaded into EPD_setting but EPD_initial uses a separate VCOM global and a hard-coded PLL/frame value",
        },
        {
            "code": "plaintext_lut_full_panel_master_geometry_mismatch",
            "evidence": "the master-only plaintext path programs full-panel 1024x600 TRES and does not configure cascade mode",
        },
        {
            "code": "uart_lut_copy_ignores_length",
            "evidence": "Uart_save_wf_data accepts buff_len but always copies WF_DATA_LENGTH without checking the supplied length",
        },
        {
            "code": "bluetooth_brightness_contrast_mapping_unproven",
            "evidence": "the supplied files prove only a UART control plane: command 5 uploads the unsafe legacy 535-byte waveform, command 7 reads VCOM, and command 8 stores an unchecked raw VCOM byte before an ACK; no BLE/GATT implementation, contrast command, approved optical mapping, unit, range, or complete application timing is supplied",
        },
        {
            "code": "plaintext_lut_busy_wait_has_no_timeout",
            "evidence": "EPD_Check_Busy spins in while(1) until the BUSY input changes and has no timeout contract",
        },
        {
            "code": "loadwf_return_contract_conflict",
            "evidence": "the header declares void, callers assign unsigned char, and exact binary disassembly returns 0x00/0xE1/0xE2 in r0",
        },
        {
            "code": "packaged_waveform_loader_abi_mismatch",
            "evidence": "the 544-byte loader reads big-endian key length 5157 at wrapper offset 544, which exceeds the supplied 842-byte WF20_25 object; the self-consistent 800+2+40 candidate layout has no supplied matching loader or authoritative format",
        },
        {
            "code": "sample_main_required_waveform_missing",
            "evidence": "Sample Code/main.c includes WF00_05.h, but the supplied tree and original ZIP contain only WF20_25.h",
        },
        {
            "code": "runtime_loadwf_master_only_glue",
            "evidence": "loadWF has no CS argument and delegates to writeEPD; the supplied STM32 writeEPD path ultimately asserts E_Paper_CS only, while spiChipSelect/MAS_SLA are undefined in supplied C/H sources",
        },
        {
            "code": "reference_internal_color_code_conflict",
            "evidence": "User/EDP_init.c 2-bit uses yellow=2/red=3, but Sample Code/E28xx.c 3-bit uses red=2/yellow=3",
        },
        {
            "code": "reference_2bit_fill_literal_conflict",
            "evidence": "the combined B/W/R/Y 2-bit fill uses white=0x55 while the standalone white function writes 0x11",
        },
        {
            "code": "link_artifact_older_than_source",
            "evidence": "User/main.c is newer than the newest M009 linker map",
        },
        {
            "code": "panel_waveform_compatibility_unproven",
            "evidence": "the reference does not establish a safe decoded waveform/voltage contract for the connected MF1750 panel",
        },
        {
            "code": "e6_reference_not_target_and_sequence_inconsistent",
            "evidence": "the E6 sample is single-CS EL073 800x480 code whose solid-fill loops are consistent with 4-bpp packing; V1.2 cuts VDD after each display but main initializes once and then calls seven displays without repower/reinitialization",
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "reference_root": str(root),
        "safety": {
            "scope": "this formal audit invocation only",
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_accessed": False,
            "network_accessed": False,
            "waveform_decrypted": False,
            "accepted_loader_plaintext_decrypted": False,
            "separate_reverse_evidence_candidate_decrypt_in_memory": True,
            "customer_key_material_emitted": False,
            "otp_payload_read": False,
            "raw_waveform_values_emitted": False,
            "live_payload_generated": False,
        },
        "wf_data": wf_data,
        "packaged_waveform": packaged,
        "library": library,
        "lcd": lcd,
        "project": project,
        "link_map": link_map,
        "loadwf_contract": loadwf,
        "uart_control_plane": uart_control,
        "color_codes": colors,
        "artifact_age": age,
        "e6_sample": e6_sample,
        "vendor_sample_crosscheck": {
            "e6_red_packed_byte": e6_sample.get("colors", {}).get("red", {}).get("packed_byte"),
            "e6_yellow_packed_byte": (
                e6_sample.get("colors", {}).get("yellow", {}).get("packed_byte")
            ),
            "reg_3bit_red_code": colors["sample_3bit"]["red"],
            "reg_3bit_yellow_code": colors["sample_3bit"]["yellow"],
            "red_yellow_codes_conflict_across_samples": (
                e6_sample.get("colors", {}).get("red", {}).get("packed_byte") == "0x33"
                and e6_sample.get("colors", {}).get("yellow", {}).get("packed_byte")
                == "0x22"
                and colors["sample_3bit"]["red"] == 2
                and colors["sample_3bit"]["yellow"] == 3
            ),
            "cross_sample_register_or_color_transplant_allowed": False,
        },
        "compatibility_ready": False,
        "compatibility_blockers": reasons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline, read-only audit of the supplied STM32 E2802 waveform reference."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT,
        help="reference root (defaults to the checked-in REG-API-oqc tree)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit(args.root)
    except (AuditError, OSError) as error:
        json.dump(
            {"schema_version": SCHEMA_VERSION, "kind": KIND, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2
    # ASCII escaping also makes stdout deterministic on Windows hosts whose
    # console code page is not UTF-8 (the default root contains Chinese text).
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
