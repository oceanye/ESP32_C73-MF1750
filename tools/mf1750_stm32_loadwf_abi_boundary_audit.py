#!/usr/bin/env python3
"""Audit the STM32 ``loadWF`` ingress and decoded-byte boundaries offline.

The audit joins three identity-pinned evidence layers without emitting a
customer key, waveform byte, or runtime payload:

* the supplied REG-tool template and its additive checksum envelope;
* the exact ArmCC object retained in the vendor archive; and
* the separately decoded 800-byte WF20_25/WF23_25 candidate records.

The layers are kept distinct.  In particular, an 800-byte candidate record is
not promoted to the 544-byte ArmCC loader ABI, and filename digits are not
promoted to a supplier-qualified Celsius range.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Final


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_armcc_loadwf_deep_audit as armcc  # noqa: E402
from tools import mf1750_spd1657_reverse_delta as reverse_delta  # noqa: E402
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-stm32-loadwf-abi-boundary-audit"
SCHEMA_VERSION: Final = 1
DEFAULT_REFERENCE_ROOT: Final = reverse_delta.DEFAULT_REFERENCE_ROOT

SAMPLE_MAIN_REL: Final = Path("Sample Code/main.c")
SAMPLE_MAIN_HEADER_REL: Final = Path("Sample Code/main.h")
E28XX_HEADER_REL: Final = Path("Sample Code/E28xx.h")
WF20_REL: Final = Path("Sample Code/WF20_25.h")
SAMPLE_MAIN_BACKUP_REL: Final = Path("Sample Code/main.c.bak")
USER_MAIN_REL: Final = Path("User/main.c")
UART_DATA_REL: Final = Path("User/UartDataDeal.c")
EPD_INIT_HEADER_REL: Final = Path("User/EPD_init.h")
LEGACY_LUT_REL: Final = Path("User/EDP_init.c")
WF23_REL: Final = Path("Projects/MDK-ARM/12")
PROJECT_REL: Final = Path("Projects/MDK-ARM/atk_f103.uvprojx")
PROFILE_PACK_REL: Final = Path("tools/mf1750_spd1657_vendor_profile_pack.py")

# Each vendor source used for a semantic conclusion is size- and hash-pinned.
EXPECTED_VENDOR_SOURCES: Final[dict[Path, tuple[int, str]]] = {
    SAMPLE_MAIN_REL: (
        9_561,
        "b23d4bcda19e93476ca58d27ec92a9bdc4b6bf9bed7028d082015d7211e1642d",
    ),
    SAMPLE_MAIN_HEADER_REL: (
        1_108,
        "a1069677c748df503ec92f0f51fe0e205b8b442fc8e81871e47319b8c039e0ee",
    ),
    E28XX_HEADER_REL: (
        4_358,
        "829974a41a1c3c79588941aa28c8fec39fdd07beb1b41c062c75379e29615c47",
    ),
    WF20_REL: (
        5_570,
        "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821",
    ),
    SAMPLE_MAIN_BACKUP_REL: (
        9_245,
        "e3a30aad634a96dcf0919057d52ff65d21d019b6401a819c8ab25a67e2f11217",
    ),
    USER_MAIN_REL: (
        6_393,
        "ecf13ad33af9dd51e982d3af2daaceb4d74a296618a8c513a06e136f3583387b",
    ),
    UART_DATA_REL: (
        5_047,
        "da853aa6f02c2ec3da271d3bc6dc23c50467b3b6af4e5d8b113dc18304e5d897",
    ),
    EPD_INIT_HEADER_REL: (
        4_919,
        "a7164e6c24e22c431c761cf730b1cbb9fa9e2d4c3b0020b6436b62e4df1f5dbf",
    ),
    LEGACY_LUT_REL: (
        32_220,
        "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5",
    ),
    WF23_REL: (
        5_776,
        "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d",
    ),
    PROJECT_REL: (
        22_696,
        "2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8",
    ),
}

EXPECTED_PROFILE_PACK: Final = (
    21_659,
    "ac5cbbdf46cb658c2f0ac0542829bc305bb1487bd6d60e123a261aed5aa29417",
)


class AbiBoundaryAuditError(RuntimeError):
    """Raised when a pinned identity or semantic invariant changed."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AbiBoundaryAuditError(message)


def _read_pinned(
    path: Path, expected: tuple[int, str], label: str
) -> tuple[bytes, dict[str, object]]:
    _require(path.is_file(), f"missing {label}: {path}")
    payload = path.read_bytes()
    expected_bytes, expected_sha256 = expected
    observed_sha256 = _sha256(payload)
    _require(len(payload) == expected_bytes, f"{label} byte count changed")
    _require(observed_sha256 == expected_sha256, f"{label} SHA-256 changed")
    return payload, {
        "bytes": len(payload),
        "sha256": observed_sha256,
    }


def _strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", text)


def _strip_c_strings(text: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def _extract_braced_body(text: str, opening: int, label: str) -> str:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AbiBoundaryAuditError(f"cannot find closing brace for {label}")


def _extract_function(text: str, name: str) -> tuple[str, str]:
    match = re.search(
        rf"\b{re.escape(name)}\s*\((?P<parameters>[^)]*)\)\s*\{{",
        text,
        flags=re.DOTALL,
    )
    _require(match is not None, f"cannot find {name} function")
    assert match is not None
    opening = text.find("{", match.start())
    return match.group("parameters"), _extract_braced_body(text, opening, name)


def _extract_switch_case(text: str, label: str) -> str:
    match = re.search(rf"\bcase\s+{re.escape(label)}\s*:", text)
    _require(match is not None, f"cannot find {label} switch case")
    assert match is not None
    tail = text[match.end() :]
    next_case = re.search(r"(?m)^\s*(?:case\b[^:]*|default\s*):", tail)
    _require(next_case is not None, f"cannot bound {label} switch case")
    assert next_case is not None
    return tail[: next_case.start()]


def _counter_comparison_count(code: str) -> int:
    comparison = r"(?:==|!=|<=|>=|<|>)"
    return len(re.findall(rf"\bCOUNTER\s*{comparison}|{comparison}\s*COUNTER\b", code))


def _header_preamble(payload: bytes, initializer_name: str) -> bytes:
    marker = re.search(
        rb"\bconst\s+unsigned\s+char\s+" + initializer_name.encode("ascii") + rb"\b",
        payload,
    )
    _require(marker is not None, f"cannot find {initializer_name} declaration")
    assert marker is not None
    return payload[: marker.start()]


def _temperature_words_found(payload: bytes) -> bool:
    lowered = payload.lower()
    ascii_terms = (b"temperature", b"celsius", b"degree", b"degrees", b"degc")
    encoded_terms = (
        "温度".encode("utf-8"),
        "温度".encode("gb18030"),
        "摄氏".encode("utf-8"),
        "摄氏".encode("gb18030"),
    )
    return any(term in lowered for term in ascii_terms) or any(
        term in payload for term in encoded_terms
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_ingress_report(
    sources: dict[Path, bytes], reference_root: Path
) -> dict[str, object]:
    sample_main = sources[SAMPLE_MAIN_REL].decode("latin-1")
    sample_header = sources[SAMPLE_MAIN_HEADER_REL].decode("latin-1")
    uart_data = sources[UART_DATA_REL].decode("latin-1")
    epd_header = sources[EPD_INIT_HEADER_REL].decode("latin-1")
    project = sources[PROJECT_REL].decode("latin-1")

    check_parameters, check_body = _extract_function(sample_main, "checkData")
    receive_parameters, receive_body = _extract_function(sample_main, "receiveData")
    load_case = _extract_switch_case(sample_main, "_loadWF")
    clean_load_case = _strip_c_strings(_strip_c_comments(load_case))
    uart_parameters, uart_body = _extract_function(uart_data, "Uart_save_wf_data")
    clean_uart_body = _strip_c_strings(_strip_c_comments(uart_body))

    _require(
        re.search(r"#define\s+_loadWF\s+0x20\b", sample_header) is not None,
        "_loadWF command changed",
    )
    _require(
        re.search(
            r"COUNTER\s*=\s*\(unsigned\s+int\)\s*\(\s*"
            r"dataBuff\s*\[\s*4\s*\]\s*\*\s*256\s*\+\s*"
            r"dataBuff\s*\[\s*5\s*\]\s*\)",
            sample_main,
        )
        is not None,
        "COUNTER extraction changed",
    )
    _require(
        re.search(
            r"receiveData\s*\(\s*dataBuff\s*,\s*6\s*\+\s*COUNTER\s*\+\s*1\s*\)",
            _strip_c_comments(sample_main),
        )
        is not None,
        "sample receive length expression changed",
    )
    _require(
        re.search(r"dataBuff\s*\[\s*i\s*\+\s*6\s*\]", check_body) is not None,
        "checksum coverage start changed",
    )
    _require(
        re.search(r"i\s*<\s*dataLen", check_body) is not None,
        "checksum coverage length changed",
    )
    _require(
        re.search(r"checkSum\s*=\s*dataBuff\s*\[\s*6\s*\+\s*COUNTER\s*\]", load_case)
        is not None,
        "checksum field offset changed",
    )
    _require(
        re.search(r"checkData\s*\(\s*COUNTER\s*,\s*checkSum\s*\)", load_case)
        is not None,
        "checksum call changed",
    )
    _require(
        re.search(r"loadWF\s*\(\s*&\s*dataBuff\s*\[\s*6\s*\]\s*\)", load_case)
        is not None,
        "loadWF ingress pointer changed",
    )
    _require(_counter_comparison_count(clean_load_case) == 0, "length gate added")
    _require(
        re.search(r"#define\s+WF_DATA_LENGTH\s+535\b", epd_header) is not None,
        "legacy WF_DATA_LENGTH changed",
    )
    _require(
        re.search(
            r"memcpy\s*\(\s*wf_data\s*,\s*dat_buff\s*,\s*WF_DATA_LENGTH\s*\)",
            clean_uart_body,
        )
        is not None,
        "legacy fixed waveform copy changed",
    )

    receive_stub_clean = _strip_c_comments(receive_body).strip()
    sample_project_entry = r"..\..\Sample Code\main.c" in project
    user_project_entry = r"..\..\User\main.c" in project
    _require(not sample_project_entry and user_project_entry, "project entry changed")

    return {
        "sample_reg_tool_template": {
            "command": "0x20",
            "counter_field_offsets": [4, 5],
            "counter_byte_order": "big-endian",
            "counter_width_bits": 16,
            "payload_offset": 6,
            "receive_total_expression": "6 + COUNTER + 1",
            "checksum_algorithm": "8-bit additive sum",
            "checksum_covered_range": "dataBuff[6 : 6 + COUNTER]",
            "checksum_field_offset": "6 + COUNTER",
            "command_header_covered_by_checksum": False,
            "counter_field_covered_by_checksum": False,
            "cryptographic_authentication_present": False,
            "loadwf_argument": "&dataBuff[6]",
            "counter_passed_to_loadwf": False,
            "exact_length_comparison_count_in_loadwf_case": 0,
            "known_size_gate_present": False,
            "check_function_parameter_names": [
                item.strip() for item in check_parameters.split(",")
            ],
            "receive_function_parameter_names": [
                item.strip() for item in receive_parameters.split(",")
            ],
            "receive_function_is_unimplemented_stub": receive_stub_clean == "",
            "usbcdc_header_present_in_supplied_tree": (
                reference_root / "Sample Code/usbcdc.h"
            ).is_file(),
            "sample_main_is_keil_project_entry": sample_project_entry,
            "user_main_is_keil_project_entry": user_project_entry,
        },
        "legacy_uart_ingress": {
            "function_parameters": [
                item.strip() for item in uart_parameters.split(",")
            ],
            "supplied_length_parameter": "buff_len",
            "fixed_copy_bytes": 535,
            "fixed_copy_uses_wf_data_length": True,
            "function_body_uses_supplied_length": (
                re.search(r"\bbuff_len\b", clean_uart_body) is not None
            ),
        },
    }


def _temperature_report(
    sources: dict[Path, bytes], profile_pack_payload: bytes, reference_root: Path
) -> dict[str, object]:
    sample_main = sources[SAMPLE_MAIN_REL].decode("latin-1")
    sample_backup = sources[SAMPLE_MAIN_BACKUP_REL].decode("latin-1")
    user_main = sources[USER_MAIN_REL].decode("latin-1")
    project = sources[PROJECT_REL].decode("latin-1")
    wf20_preamble = _header_preamble(sources[WF20_REL], "WF20_25")
    wf23_preamble = _header_preamble(sources[WF23_REL], "WF23_25")

    _require('"WF00_05.h"' in sample_main, "WF00_05 include changed")
    _require("WF20_25" in user_main, "WF20_25 use changed")
    _require("WF23_25" in sources[WF23_REL].decode("latin-1"), "WF23_25 changed")
    _require("WF24_24[5]" in user_main, "WF24_24 comment changed")
    _require(
        "loadWF(WF25_25)" in re.sub(r"\s+", "", sample_backup),
        "WF25_25 backup call changed",
    )
    _require(
        not _temperature_words_found(wf20_preamble),
        "WF20 preamble gained temperature semantics",
    )
    _require(
        not _temperature_words_found(wf23_preamble),
        "WF23 preamble gained temperature semantics",
    )

    pack_specs: dict[str, dict[str, object]] = {}
    for profile_id in ("WF20_25", "WF23_25"):
        match = re.fullmatch(r"WF(\d{2})_(\d{2})", profile_id)
        _require(match is not None, f"cannot parse profile identifier {profile_id}")
        assert match is not None
        filename_pair = [int(match.group(1)), int(match.group(2))]
        spec = profile_pack.PROFILES[profile_id]
        configured_pair = [spec.temperature_min_c, spec.temperature_max_c]
        _require(
            configured_pair == filename_pair, f"{profile_id} local mapping changed"
        )
        pack_specs[profile_id] = {
            "filename_numeric_pair": filename_pair,
            "local_profile_spec_celsius_pair": configured_pair,
            "values_equal_filename_digits": True,
            "supplier_qualified_by_this_mapping": False,
        }

    profile_pack_text = profile_pack_payload.decode("utf-8")
    _require(
        "kApparentTemperatureMinC" in profile_pack_text
        and "kApparentTemperatureMaxC" in profile_pack_text,
        "profile pack apparent-temperature labels changed",
    )

    observed_names = [
        {
            "identifier": "WF00_05",
            "numeric_pair": [0, 5],
            "provenance": "Sample Code/main.c conditional include",
            "physical_named_header_present": (
                reference_root / "Sample Code/WF00_05.h"
            ).is_file(),
        },
        {
            "identifier": "WF20_25",
            "numeric_pair": [20, 25],
            "provenance": "supplied named header and User/main.c identifier use",
            "physical_named_header_present": (reference_root / WF20_REL).is_file(),
        },
        {
            "identifier": "WF23_25",
            "numeric_pair": [23, 25],
            "provenance": "extensionless artifact declaring File Name WF23_25.h",
            "physical_named_header_present": (
                reference_root / "Projects/MDK-ARM/WF23_25.h"
            ).is_file(),
        },
        {
            "identifier": "WF24_24",
            "numeric_pair": [24, 24],
            "provenance": "commented VCOM expression in User/main.c",
            "physical_named_header_present": (
                reference_root / "User/WF24_24.h"
            ).is_file(),
        },
        {
            "identifier": "WF25_25",
            "numeric_pair": [25, 25],
            "provenance": "backup Sample Code/main.c.bak loadWF call",
            "physical_named_header_present": (
                reference_root / "Sample Code/WF25_25.h"
            ).is_file(),
        },
    ]

    return {
        "observed_waveform_identifiers": observed_names,
        "wf20_header_preamble_has_explicit_temperature_statement": False,
        "wf23_header_preamble_has_explicit_temperature_statement": False,
        "explicit_celsius_unit_statement_found": False,
        "filename_numeric_components_parsed_by_supplied_loader": False,
        "filename_numeric_components_used_by_supplied_project_selector": False,
        "wf23_listed_in_keil_project": "WF23_25" in project,
        "local_profile_pack": {
            "path": PROFILE_PACK_REL.as_posix(),
            "uses_apparent_temperature_constant_names": True,
            "profiles": pack_specs,
        },
        "classification": {
            "name_to_band_mapping": "filename-only inference",
            "inference_evidence_grade": "C",
            "temperature_semantics_evidence_grade": "U",
            "inclusive_or_exclusive_boundary_semantics_proven": False,
            "panel_or_fpl_temperature_qualification_proven": False,
            "safe_use_band_authority": False,
            "why": (
                "five compatible identifier shapes exist, but no supplied header, "
                "loader, project selector, or comment defines the digits as Celsius "
                "bounds or states boundary semantics"
            ),
        },
    }


def build_report(
    reference_root: Path = DEFAULT_REFERENCE_ROOT,
    library_path: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic metadata-only cross-layer audit report."""

    reference_root = reference_root.resolve()
    _require(
        reference_root.is_dir(), f"reference root does not exist: {reference_root}"
    )

    sources: dict[Path, bytes] = {}
    identities: dict[str, object] = {}
    for relative, expected in EXPECTED_VENDOR_SOURCES.items():
        payload, identity = _read_pinned(
            reference_root / relative,
            expected,
            relative.as_posix(),
        )
        sources[relative] = payload
        identities[relative.as_posix()] = identity

    profile_pack_payload, profile_pack_identity = _read_pinned(
        REPO_ROOT / PROFILE_PACK_REL,
        EXPECTED_PROFILE_PACK,
        PROFILE_PACK_REL.as_posix(),
    )
    identities[PROFILE_PACK_REL.as_posix()] = profile_pack_identity

    if library_path is None:
        library_path = reference_root / reverse_delta.LIBRARY_REL
    deep = armcc.build_report(library_path)
    reverse = reverse_delta.build_report(reference_root=reference_root)

    ingress = _source_ingress_report(sources, reference_root)
    temperature = _temperature_report(
        sources,
        profile_pack_payload,
        reference_root,
    )

    loadwf = deep["loadwf"]
    wrapper = deep["decrypt_gate"]["wrapper_contract"]
    transactions = loadwf["success_transactions"]
    _require(
        loadwf["prototype_from_dwarf"]
        == "unsigned char loadWF(unsigned char const *wf_buffer)",
        "loadWF pointer-only prototype changed",
    )
    _require(
        [
            (row["command"], row["parameter_bytes"], row["pointer"])
            for row in transactions
        ]
        == [
            ("0x01", 6, "pwr_d"),
            ("0x30", 1, "pll_d"),
            ("0x20", 535, "in"),
            ("0x21", 704, "LUT1_DATA"),
        ],
        "loadWF transaction contract changed",
    )
    _require(wrapper["fixed_ciphertext_copy_bytes"] == 544, "decode size changed")
    _require(wrapper["wrapped_length_offsets"] == [544, 545], "length offsets changed")

    candidate20 = reverse["candidate_800"]
    candidate23 = reverse["candidate_wf23_25"]
    _require(candidate20["plaintext"]["bytes"] == 800, "WF20 decoded size changed")
    _require(candidate23["plaintext"]["bytes"] == 800, "WF23 decoded size changed")
    _require(
        candidate20["plaintext"]["layout_formula"] == "7 + 9 * (8 * 11) + 1"
        and candidate23["plaintext"]["layout_formula"] == "7 + 9 * (8 * 11) + 1",
        "candidate geometry changed",
    )
    _require(
        candidate20["category_semantics_evidence"][
            "unique_category_to_pixel_code_mapping_proven"
        ]
        is False,
        "category semantics unexpectedly promoted",
    )

    sample = ingress["sample_reg_tool_template"]
    cross_layer = {
        "producer_declared_length_field": "COUNTER from packet bytes[4:6]",
        "producer_checksum_covers_exactly_counter_bytes": True,
        "producer_passes_length_to_consumer": False,
        "consumer_abi_has_total_length_argument": wrapper[
            "total_input_length_argument_present"
        ],
        "consumer_unconditionally_copies_bytes": wrapper["fixed_ciphertext_copy_bytes"],
        "consumer_reads_length_field_offsets": wrapper["wrapped_length_offsets"],
        "consumer_checks_caller_bound_before_fixed_copy": wrapper[
            "caller_buffer_bound_checked_before_fixed_copy"
        ],
        "counter_at_least_546_gate_present": False,
        "exact_535_544_546_799_800_842_or_876_gate_present": sample[
            "known_size_gate_present"
        ],
        "bytes_read_beyond_counter_are_checksum_covered": False,
        "contract_gap_proven": True,
        "actual_storage_out_of_bounds_proven": False,
        "exploitable_path_proven": False,
        "why_not_exploit_claim": (
            "Sample Code/main.c is not the linked project entry, receiveData is an "
            "empty integration stub, usbcdc.h is absent, and dataBuff capacity plus "
            "the real transport implementation are not supplied"
        ),
    }

    exact_partition = [
        {
            "decoded_range": "[0,5)",
            "bytes": 5,
            "dedicated_register_transaction": "0x01 PWR after literal 0x0F",
            "also_forwarded_inside_r20": True,
        },
        {
            "decoded_range": "[5,6)",
            "bytes": 1,
            "dedicated_register_transaction": None,
            "also_forwarded_inside_r20": True,
        },
        {
            "decoded_range": "[6,7)",
            "bytes": 1,
            "dedicated_register_transaction": "0x30 PLL",
            "also_forwarded_inside_r20": True,
        },
        {
            "decoded_range": "[7,535)",
            "bytes": 528,
            "dedicated_register_transaction": None,
            "also_forwarded_inside_r20": True,
        },
        {
            "decoded_range": "[535,544)",
            "bytes": 9,
            "dedicated_register_transaction": None,
            "also_forwarded_inside_r20": False,
        },
    ]

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_metadata_only_no_runtime_artifact",
        "input_identities": {
            "sources": identities,
            "armcc_archive": {
                "path": reverse_delta.LIBRARY_REL.as_posix(),
                "bytes": deep["archive"]["bytes"],
                "sha256": deep["archive"]["sha256"],
                "object_name": deep["archive"]["object"]["name"],
                "object_sha256": deep["archive"]["object"]["sha256"],
            },
            "upstream_audits": {
                "armcc": {
                    "kind": deep["kind"],
                    "schema_version": deep["schema_version"],
                },
                "candidate": {
                    "kind": reverse["kind"],
                    "schema_version": reverse["schema_version"],
                },
            },
        },
        "source_ingress": ingress,
        "cross_layer_length_boundary": cross_layer,
        "exact_armcc_decoded_byte_use": {
            "evidence_grade": "A",
            "decoded_working_buffer_bytes": 544,
            "ranges": exact_partition,
            "r20": {
                "command": "0x20",
                "bytes": 535,
                "source_range": "decoded[0:535]",
            },
            "r21": {
                "command": "0x21",
                "bytes": 704,
                "source": "independent library-resident all-FF LUT1_DATA",
                "caller_wrapper_source": False,
            },
            "decoded_byte_5_verdict": (
                "not separately applied as PWR, PLL, or VCOM, but still forwarded "
                "inside the opaque 0x20 decoded[0:535] transaction"
            ),
            "decoded_byte_5_not_written_anywhere": False,
            "decoded_bytes_535_through_543_emitted": False,
        },
        "candidate_800_records": {
            "artifact_geometry_evidence_grade": "A",
            "promotion_to_current_armcc_abi_evidence_grade": "U",
            "profiles": {
                "WF20_25": {
                    "source_path": candidate20["source_path"],
                    "source_sha256": candidate20["source_sha256"],
                    "wrapper_bytes": candidate20["wrapper"]["bytes"],
                    "decoded_bytes": candidate20["plaintext"]["bytes"],
                    "layout_formula": candidate20["plaintext"]["layout_formula"],
                    "sentinel_offset": candidate20["plaintext"]["sentinel_offset"],
                    "sentinel_is_zero": candidate20["plaintext"]["sentinel_is_zero"],
                },
                "WF23_25": {
                    "source_path": candidate23["source_path"],
                    "source_sha256": candidate23["source_sha256"],
                    "wrapper_bytes": candidate23["wrapper"]["bytes"],
                    "decoded_bytes": candidate23["plaintext"]["bytes"],
                    "layout_formula": candidate23["plaintext"]["layout_formula"],
                    "sentinel_offset": candidate23["plaintext"]["sentinel_offset"],
                    "sentinel_is_zero": candidate23["plaintext"]["sentinel_is_zero"],
                },
            },
            "current_armcc_loader_compatible": False,
            "same_object_799_byte_write_present": deep["strict_negative_findings"][
                "same_object_799_byte_write_present"
            ],
            "first_799_r20_is_cross_generation_hypothesis": True,
            "first_799_r20_live_eligible": False,
            "raw_record_bytes_emitted": False,
        },
        "semantic_provenance": {
            "category": {
                "candidate_geometry": "9 blocks of 8 groups of 11 bytes",
                "legacy_535_labels": candidate20["category_semantics_evidence"][
                    "legacy_535_labels"
                ],
                "current_armcc_parser_present": False,
                "unique_category_to_pixel_code_mapping_proven": False,
                "semantic_evidence_grade": "U",
            },
            "phase": {
                "eleven_byte_group_geometry_observed": True,
                "current_armcc_eleven_byte_parser_present": False,
                "eleven_bytes_are_phase_durations_proven": False,
                "phase_order_or_polarity_proven": False,
                "semantic_evidence_grade": "U",
            },
            "electrical": {
                "decoded_0_to_4_dedicated_pwr_binding": True,
                "decoded_6_dedicated_pll_binding": True,
                "decoded_5_legacy_label": "VCOM",
                "decoded_5_dedicated_vcom_binding_in_current_loadwf": False,
                "decoded_5_forwarded_inside_r20": True,
                "panel_or_fpl_limits_proven": False,
                "live_approved": False,
            },
        },
        "temperature_name_semantics": temperature,
        "adjudication": {
            "800_byte_current_armcc_abi": "NO-GO",
            "direct_535_plus_704_contract": "PROVEN_FOR_MODE0_OBJECT_ONLY",
            "category_semantics": "UNPROVEN",
            "phase_semantics": "UNPROVEN",
            "electrical_field_binding": (
                "ONLY_DECODED_0_TO_4_PWR_AND_DECODED_6_PLL_ARE_DEDICATED"
            ),
            "temperature_band_authority": "FILENAME_ONLY_NOT_QUALIFIED",
            "authorizes_live_hardware_action": False,
        },
        "evidence_grades": {
            "A": "identity-pinned direct same-object or direct artifact evidence",
            "B": "same-delivery source/build corroboration",
            "C": "cross-generation or naming-pattern inference",
            "U": "unknown; semantics or same-build binding not proved",
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "customer_key_material_emitted": False,
            "raw_wrapper_or_plaintext_emitted": False,
            "runtime_payload_generated": False,
            "vendor_evidence_modified": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.reference_root, args.library)
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=None if args.compact else 2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        AbiBoundaryAuditError,
        armcc.DeepAuditError,
        reverse_delta.ReverseAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
