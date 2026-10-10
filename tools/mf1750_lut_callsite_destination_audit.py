#!/usr/bin/env python3
"""Audit MF1750 LUT call-site provenance and controller destinations offline.

This audit joins two deliberately separate generations of supplied evidence:

* legacy IAR E2801/E2802 objects whose active upload is
  ``2508-byte slot -> dataBuff+4 -> R20/799 + generated R21/704``; and
* the retained ArmCC mode-0 loader whose decoded output is
  ``R20/535 + library-resident R21/704``.

The IAR objects are linked only in fresh ASCII temporary directories with
identity-pinned official XLINK and TI objdump executables.  Targeted
instructions and complete helper hashes prove that their command/data
transports toggle one fixed ``P6OUT.3`` CSB line.  The STM32 source graph is
then checked to distinguish the single-CS ``writeEPD`` candidate from the
separate master/slave/both helper API.

The report contains metadata, hashes, lengths, and bounded semantic facts.  It
never emits waveform bytes, object code, disassembly text, a live payload, or
a hardware action path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Final
import xml.etree.ElementTree as ET


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import e2801_r43_lut_proof as e2801  # noqa: E402
from tools import e2802_r43_lut_proof as e2802  # noqa: E402
from tools import mf1750_armcc_loadwf_deep_audit as armcc  # noqa: E402
from tools import mf1750_armcc_mode1_residual_audit as residual  # noqa: E402
from tools import mf1750_iar_load_lut_const_abi_audit as const_abi  # noqa: E402
from tools import mf1750_iar_project_config_chain_audit as iar_project  # noqa: E402
from tools import mf1750_iar_r43_cross_object_graph as graph  # noqa: E402
from tools import mf1750_iar_temperature_selector_audit as selector  # noqa: E402
from tools import mf1750_stm32_loadwf_abi_boundary_audit as boundary  # noqa: E402


KIND: Final = "mf1750-lut-callsite-destination-audit"
SCHEMA_VERSION: Final = 1

DEFAULT_STM32_ROOT: Final = boundary.DEFAULT_REFERENCE_ROOT
DEFAULT_IAR_ROOT: Final = graph.DEFAULT_IAR_ROOT

PROJECT_REL: Final = Path("Projects/MDK-ARM/atk_f103.uvprojx")
SAMPLE_MAIN_REL: Final = Path("Sample Code/main.c")
SAMPLE_E28XX_REL: Final = Path("Sample Code/E28xx.c")
SAMPLE_COMM_REL: Final = Path("Sample Code/comm.c")
SAMPLE_PIN_REL: Final = Path("Sample Code/pindefine.h")
USER_MAIN_REL: Final = Path("User/main.c")
USER_EPD_C_REL: Final = Path("User/EDP_init.c")
USER_EPD_H_REL: Final = Path("User/EPD_init.h")
IAR_PIN_REL: Final = Path("pindefine.h")
IAR_MCU_HEADER_REL: Final = Path("msp430f5502.h")

EXPECTED_STM32_SOURCES: Final[dict[Path, tuple[int, str]]] = {
    PROJECT_REL: (
        22_696,
        "2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8",
    ),
    SAMPLE_MAIN_REL: (
        9_561,
        "b23d4bcda19e93476ca58d27ec92a9bdc4b6bf9bed7028d082015d7211e1642d",
    ),
    SAMPLE_E28XX_REL: (
        26_501,
        "7a7601f5baecdda5cfb8cd32780c878fff52c1bd44fe8551114e277976d6c2b3",
    ),
    SAMPLE_COMM_REL: (
        9_227,
        "bdcc34bdc85b8ee98191880a3e7aadc17435d8fa9768be4df6b29f9bd31b3dc6",
    ),
    SAMPLE_PIN_REL: (
        2_231,
        "231bd184519426ad9b2e309ce961055efac53926d6e61a18e95af13422e2c498",
    ),
    USER_MAIN_REL: (
        6_393,
        "ecf13ad33af9dd51e982d3af2daaceb4d74a296618a8c513a06e136f3583387b",
    ),
    USER_EPD_C_REL: (
        32_220,
        "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5",
    ),
    USER_EPD_H_REL: (
        4_919,
        "a7164e6c24e22c431c761cf730b1cbb9fa9e2d4c3b0020b6436b62e4df1f5dbf",
    ),
}

EXPECTED_IAR_SOURCES: Final[dict[Path, tuple[int, str]]] = {
    IAR_PIN_REL: (
        1_470,
        "888e8e188ec9ec42ead37570d1900501a4321cbf1c1bb24cfb0ee58d4ba30525",
    ),
    IAR_MCU_HEADER_REL: (
        280_593,
        "0c243e92a7bc2a288da537ad9ec5e4acdf21cdd551f6d747104dcb74175b7f82",
    ),
}

GPIO_HELPER_ANCHORS: Final[dict[str, dict[int, str]]] = {
    "SPI_COMMAND": {
        0x10022: "mov.b r12, r10",
        0x10024: "bic.b #8, &0x0243",
        0x1002E: "bic.b #64, &0x0223",
        0x1008E: "bis.b #8, &0x0243",
    },
    "SPI_DATA": {
        0x1009E: "mov.b r12, r10",
        0x100A0: "bic.b #8, &0x0243",
        0x100AA: "bis.b #64, &0x0223",
        0x1010A: "bis.b #8, &0x0243",
    },
}


class LutCallsiteDestinationAuditError(RuntimeError):
    """Raised when an identity or bounded data-flow invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LutCallsiteDestinationAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_pinned(
    root: Path,
    relative: Path,
    expected: tuple[int, str],
) -> tuple[bytes, dict[str, object]]:
    path = root / relative
    _require(path.is_file(), f"missing pinned input: {path}")
    payload = path.read_bytes()
    expected_bytes, expected_sha256 = expected
    observed_sha256 = _sha256(payload)
    _require(len(payload) == expected_bytes, f"{relative.as_posix()} size changed")
    _require(
        observed_sha256 == expected_sha256,
        f"{relative.as_posix()} SHA-256 changed",
    )
    return payload, {
        "path": relative.as_posix(),
        "bytes": len(payload),
        "sha256": observed_sha256,
    }


def _strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", text)


def _function_body(text: str, name: str) -> str:
    clean = _strip_c_comments(text)
    match = re.search(
        rf"\b(?:static\s+)?(?:void|unsigned\s+char|char|int|uint8_t)\s+"
        rf"{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{",
        clean,
        flags=re.DOTALL,
    )
    _require(match is not None, f"cannot find function definition {name}")
    assert match is not None
    opening = clean.find("{", match.start())
    depth = 0
    for index in range(opening, len(clean)):
        if clean[index] == "{":
            depth += 1
        elif clean[index] == "}":
            depth -= 1
            if depth == 0:
                return clean[opening + 1 : index]
    raise LutCallsiteDestinationAuditError(f"cannot bound function {name}")


def _has_function_definition(text: str, name: str) -> bool:
    clean = _strip_c_comments(text)
    return (
        re.search(
            rf"\b(?:static\s+)?(?:void|unsigned\s+char|char|int|uint8_t)\s+"
            rf"{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{",
            clean,
            flags=re.DOTALL,
        )
        is not None
    )


def _call_count(body: str, name: str) -> int:
    return len(re.findall(rf"\b{re.escape(name)}\s*\(", body))


def _project_c_sources(project_path: Path) -> list[Path]:
    tree = ET.fromstring(project_path.read_bytes())
    sources: list[Path] = []
    for node in tree.findall(".//FilePath"):
        raw = "" if node.text is None else node.text.strip()
        if not raw.casefold().endswith(".c"):
            continue
        path = (project_path.parent / Path(raw.replace("\\", "/"))).resolve()
        _require(path.is_file(), f"project C source is missing: {raw}")
        sources.append(path)
    _require(len(sources) == len(set(sources)), "project C source list has duplicates")
    return sources


def _relative_to(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as error:
        raise LutCallsiteDestinationAuditError(
            f"project path escapes pinned root: {path}"
        ) from error


def _stm32_source_graph(
    stm32_root: Path,
    sources: dict[Path, bytes],
    residual_report: dict[str, Any],
) -> dict[str, Any]:
    project_sources = _project_c_sources(stm32_root / PROJECT_REL)
    project_relatives = [_relative_to(stm32_root, path) for path in project_sources]
    _require(len(project_sources) == 33, "project C source count changed")
    _require(USER_MAIN_REL.as_posix() in project_relatives, "User/main.c left project")
    _require(
        SAMPLE_E28XX_REL.as_posix() in project_relatives,
        "Sample Code/E28xx.c left project",
    )
    _require(
        SAMPLE_COMM_REL.as_posix() in project_relatives,
        "Sample Code/comm.c left project",
    )
    _require(
        USER_EPD_C_REL.as_posix() in project_relatives,
        "User/EDP_init.c left project",
    )
    _require(
        SAMPLE_MAIN_REL.as_posix() not in project_relatives,
        "Sample Code/main.c entered project",
    )

    definitions: list[str] = []
    project_loadwf_call_sites: list[str] = []
    for path in project_sources:
        text = path.read_bytes().decode("latin-1")
        relative = _relative_to(stm32_root, path)
        if _has_function_definition(text, "writeEPD"):
            definitions.append(relative)
        clean = _strip_c_comments(text)
        if re.search(r"\bloadWF\s*\(", clean):
            project_loadwf_call_sites.append(relative)
    _require(
        definitions == [SAMPLE_E28XX_REL.as_posix()],
        "project writeEPD definition inventory changed",
    )
    _require(not project_loadwf_call_sites, "a project C source gained loadWF call")

    sample_e28xx = sources[SAMPLE_E28XX_REL].decode("latin-1")
    user_epd_c = sources[USER_EPD_C_REL].decode("latin-1")
    user_epd_h = sources[USER_EPD_H_REL].decode("latin-1")
    sample_main = sources[SAMPLE_MAIN_REL].decode("latin-1")

    write_epd = _function_body(sample_e28xx, "writeEPD")
    send_command = _function_body(sample_e28xx, "sendSPICommand")
    send_data = _function_body(sample_e28xx, "sendSPIData")
    send_multiple = _function_body(sample_e28xx, "sendMutipleSPIData")
    primary_command = _function_body(user_epd_c, "EPD_WriteCMD")
    primary_data = _function_body(user_epd_c, "EPD_WriteDATA")
    select_both = _function_body(user_epd_c, "EPD_Select_Both")

    _require(
        _call_count(write_epd, "sendSPICommand") == 1, "writeEPD command edge changed"
    )
    _require(
        _call_count(write_epd, "sendMutipleSPIData") == 1,
        "writeEPD data edge changed",
    )
    _require(_call_count(send_command, "EPD_WriteCMD") == 1, "command sink changed")
    _require(_call_count(send_data, "EPD_WriteDATA") == 1, "data sink changed")
    _require(_call_count(send_multiple, "sendSPIData") == 1, "data loop edge changed")
    _require(
        all(
            token not in write_epd
            for token in (
                "EPD_WriteCMD_ToBoth",
                "EPD_WriteDATA_ToBoth",
                "EPD_WriteMultiData_ToBoth",
                "EPD_Select_Both",
                "spiChipSelect",
            )
        ),
        "writeEPD gained a dual-target or selector reference",
    )
    _require(
        primary_command.count("E_Paper_CS = 0") == 1
        and primary_command.count("E_Paper_CS = 1") == 1
        and "E_Paper_SLAVE_CS" not in primary_command,
        "primary command CS binding changed",
    )
    _require(
        primary_data.count("E_Paper_CS = 0") == 1
        and primary_data.count("E_Paper_CS = 1") == 1
        and "E_Paper_SLAVE_CS" not in primary_data,
        "primary data CS binding changed",
    )
    _require(
        "E_Paper_CS = 0" in select_both and "E_Paper_SLAVE_CS = 0" in select_both,
        "dual-select helper changed",
    )
    _require(
        re.search(r"#define\s+E_Paper_CS\s+PDout\(8\)", user_epd_h) is not None
        and re.search(r"#define\s+E_Paper_SLAVE_CS\s+PDout\(11\)", user_epd_h)
        is not None,
        "STM32 CS pin definitions changed",
    )
    dual_functions = (
        "EPD_WriteCMD_ToMaster",
        "EPD_WriteCMD_ToSlave",
        "EPD_WriteDATA_ToMaster",
        "EPD_WriteDATA_ToSlave",
        "EPD_WriteCMD_ToBoth",
        "EPD_WriteDATA_ToBoth",
        "EPD_WriteMultiData_ToBoth",
    )
    _require(
        all(_has_function_definition(user_epd_c, name) for name in dual_functions),
        "dual helper definition inventory changed",
    )
    _require(
        len(re.findall(r"\bspiChipSelect\s*=\s*MAS_SLA\s*;", sample_main)) == 3,
        "Sample main selector assignment inventory changed",
    )

    output_chain = residual_report["output_link_chain"]
    _require(output_chain["map_files"] == 7, "MAP count changed")
    _require(
        not output_chain["map_axf_loader_or_mode_marker_hits"], "loader entered maps"
    )
    map_rows: list[dict[str, object]] = []
    for path in sorted(
        (stm32_root / "Output").glob("*.map"), key=lambda item: item.name
    ):
        text = path.read_text("latin-1")
        removed = len(
            re.findall(
                r"Removing e28xx\.o\(i\.writeEPD\), \(24 bytes\)\.",
                text,
            )
        )
        _require(removed == 1, f"{path.name} writeEPD removal changed")
        _require(
            re.search(r"\bloadWF\b", text, flags=re.IGNORECASE) is None,
            f"{path.name} gained loadWF",
        )
        map_rows.append(
            {
                "path": f"Output/{path.name}",
                "loadWF_token_count": 0,
                "writeEPD_removed_count": removed,
            }
        )
    _require(len(map_rows) == 7, "observed MAP inventory changed")

    return {
        "project_C_source_count": len(project_sources),
        "project_entry": USER_MAIN_REL.as_posix(),
        "sample_main_is_project_entry": False,
        "project_loadWF_C_call_sites": project_loadwf_call_sites,
        "project_writeEPD_definitions": definitions,
        "retained_library_resolution_candidate": {
            "call_chain": [
                "loadWF",
                "writeEPD",
                "sendSPICommand/sendMutipleSPIData",
                "EPD_WriteCMD/EPD_WriteDATA",
                "E_Paper_CS",
            ],
            "writeEPD_reads_controller_or_chip_select_argument": False,
            "writeEPD_reads_spiChipSelect_global": False,
            "terminal_primary_CS_macro": "E_Paper_CS=PDout(8)",
            "terminal_slave_CS_macro": "E_Paper_SLAVE_CS=PDout(11)",
            "terminal_slave_CS_used_by_writeEPD_chain": False,
            "source_graph_classification": "SINGLE_PRIMARY_CS_CANDIDATE_ONLY",
        },
        "separate_dual_target_API": {
            "defined_functions": list(dual_functions),
            "EPD_Select_Both_drives_primary_and_slave_low": True,
            "called_by_writeEPD_chain": False,
            "automatically_retargets_loadWF": False,
        },
        "sample_main_selector_residue": {
            "spiChipSelect_equals_MAS_SLA_assignments": 3,
            "sample_main_is_project_entry": False,
            "writeEPD_body_reads_spiChipSelect": False,
            "proves_dual_loader_destination": False,
        },
        "delivered_MAP_closure": {
            "maps": map_rows,
            "all_seven_remove_writeEPD": True,
            "all_seven_omit_loadWF": True,
            "source_resolution_candidate_is_linked_final_path": False,
        },
    }


def _linked_gpio_transport(
    object_path: Path,
    xlink_path: Path,
    objdump_path: Path,
) -> dict[str, Any]:
    contract = const_abi.COMMON_LINK
    with tempfile.TemporaryDirectory(prefix="mf1750-lut-destination-") as temp_name:
        _require(temp_name.isascii(), "temporary link path is not ASCII-only")
        temp_dir = Path(temp_name)
        object_copy = temp_dir / object_path.name
        output_path = temp_dir / "linked.hex"
        shutil.copyfile(object_path, object_copy)
        environment = os.environ.copy()
        environment.pop("XLINK_ENVPAR", None)
        arguments = [
            str(xlink_path),
            "-Fintel-extended",
            "-o",
            str(output_path),
            "-cmsp430",
            selector.CODE_PLACEMENT,
            selector.DATA_PLACEMENT,
            *(
                f"-D{name}=0x{address:X}"
                for name, address in selector.EXTERNAL_DEFINITIONS
            ),
            "-gEPD_Load_LUT",
            str(object_copy),
        ]
        completed = subprocess.run(
            arguments,
            cwd=temp_dir,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(completed.returncode == 0, f"{object_path.name} XLINK failed")
        _require(not completed.stderr, "XLINK unexpectedly used stderr")
        summary = const_abi._parse_link_summary(
            completed.stdout,
            expected_warnings="none",
        )
        _require(output_path.is_file(), "XLINK did not emit Intel HEX")
        intel_hex = output_path.read_bytes()
        _require(
            len(intel_hex) == contract["intel_hex_size_bytes"]
            and _sha256(intel_hex) == contract["intel_hex_sha256"],
            f"{object_path.name} linked image identity changed",
        )
        _require(
            summary
            == {
                "code_bytes": contract["xlink_code_bytes"],
                "data_bytes": contract["xlink_data_bytes"],
                "absolute_symbols": contract["xlink_absolute_symbols"],
            },
            f"{object_path.name} link summary changed",
        )
        image = selector.parse_intel_hex(intel_hex)
        disassembly = subprocess.run(
            [str(objdump_path), "-D", "-b", "ihex", "-m", "msp:14", str(output_path)],
            cwd=temp_dir,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(disassembly.returncode == 0, "objdump failed")
        _require(not disassembly.stderr, "objdump unexpectedly used stderr")
        instructions = selector.parse_objdump_instructions(disassembly.stdout)
        by_address = {row.address: row.normalized_instruction for row in instructions}

        helpers: dict[str, Any] = {}
        for name, helper_contract in contract["helpers"].items():
            start = int(helper_contract["start"])
            end = int(helper_contract["end_exclusive"])
            payload = bytes(image.memory[address] for address in range(start, end))
            rows = [row for row in instructions if start <= row.address < end]
            normalized = ("\n".join(row.stripped_line for row in rows) + "\n").encode(
                "utf-8"
            )
            _require(len(payload) == helper_contract["bytes"], f"{name} size changed")
            _require(
                _sha256(payload) == helper_contract["sha256"], f"{name} hash changed"
            )
            _require(
                len(rows) == helper_contract["instruction_lines"],
                f"{name} instruction count changed",
            )
            _require(
                _sha256(normalized) == helper_contract["normalized_disassembly_sha256"],
                f"{name} normalized disassembly changed",
            )
            for address, expected in GPIO_HELPER_ANCHORS[name].items():
                _require(
                    by_address.get(address) == expected,
                    f"{name} GPIO anchor 0x{address:X} changed",
                )
            p6out_rows = [
                row.normalized_instruction
                for row in rows
                if "&0x0243" in row.normalized_instruction
            ]
            _require(
                p6out_rows == ["bic.b #8, &0x0243", "bis.b #8, &0x0243"],
                f"{name} fixed CS operations changed",
            )
            helpers[name] = {
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "instruction_count": len(rows),
                "normalized_disassembly_sha256": _sha256(normalized),
                "entry_consumes_R12_low_byte": True,
                "fixed_CS_assert_operations": 1,
                "fixed_CS_release_operations": 1,
                "CS_register_address": "0x0243",
                "CS_bit_mask": "0x08",
            }

    return {
        "source_object": {
            "name": object_path.name,
            "bytes": object_path.stat().st_size,
            "sha256": _sha256(object_path.read_bytes()),
        },
        "root_only_link": {
            "root": "EPD_Load_LUT",
            "intel_hex_bytes": len(intel_hex),
            "intel_hex_sha256": _sha256(intel_hex),
            "emitted_memory_bytes": len(image.memory),
            "xlink_summary": summary,
            "temporary_outputs_discarded": True,
        },
        "helpers": helpers,
        "destination_binding": {
            "chip_select_register": "P6OUT",
            "chip_select_register_address": "0x0243",
            "chip_select_bit": 3,
            "chip_select_mask": "0x08",
            "chip_select_polarity": "active-low",
            "clock_register": "P4OUT",
            "clock_bit": 7,
            "serial_data_register": "P4OUT",
            "serial_data_bit": 6,
            "command_data_prefix": "9-bit serial prefix: 0 for command, 1 for data",
            "controller_or_chip_select_argument_consumed": False,
            "mutable_controller_selector_read": False,
            "distinct_second_CS_written": False,
            "physical_controller_identity_proven": False,
        },
    }


def _iar_pin_contract(iar_root: Path, sources: dict[Path, bytes]) -> dict[str, Any]:
    pin = sources[IAR_PIN_REL].decode("latin-1")
    mcu = sources[IAR_MCU_HEADER_REL].decode("latin-1")
    macros = {
        "CSB_L": r"#define\s+CSB_L\s+P6OUT\s*&=\s*0xF7",
        "CSB_H": r"#define\s+CSB_H\s+P6OUT\s*\|=\s*0x08",
        "SCL_L": r"#define\s+SCL_L\s+P4OUT\s*&=\s*0x7F",
        "SCL_H": r"#define\s+SCL_H\s+P4OUT\s*\|=\s*0x80",
        "SDA_L": r"#define\s+SDA_L\s+P4OUT\s*&=\s*0xBF",
        "SDA_H": r"#define\s+SDA_H\s+P4OUT\s*\|=\s*0x40",
    }
    _require(
        all(re.search(pattern, pin) is not None for pattern in macros.values()),
        "IAR GPIO macro contract changed",
    )
    _require(
        re.search(r"unsigned\s+char\s+P4OUT\s*;.*?@0x0223\s*;", mcu, re.DOTALL)
        is not None,
        "P4OUT address declaration changed",
    )
    _require(
        re.search(r"unsigned\s+char\s+P6OUT\s*;.*?@0x0243\s*;", mcu, re.DOTALL)
        is not None,
        "P6OUT address declaration changed",
    )
    return {
        "source_macros": {
            "CSB_L": "P6OUT &= 0xF7",
            "CSB_H": "P6OUT |= 0x08",
            "SCL_L": "P4OUT &= 0x7F",
            "SCL_H": "P4OUT |= 0x80",
            "SDA_L": "P4OUT &= 0xBF",
            "SDA_H": "P4OUT |= 0x40",
        },
        "MCU_header_register_addresses": {
            "P4OUT": "0x0223",
            "P6OUT": "0x0243",
        },
        "macro_to_linked_instruction_agreement": True,
        "source_root": iar_root.relative_to(REPO_ROOT).as_posix(),
    }


def build_report(
    xlink_path: Path,
    objdump_path: Path,
    stm32_root: Path = DEFAULT_STM32_ROOT,
    iar_root: Path = DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build a deterministic metadata-only call-site/destination report."""

    stm32_root = stm32_root.resolve()
    iar_root = iar_root.resolve()
    _require(stm32_root.is_dir(), f"STM32 root does not exist: {stm32_root}")
    _require(iar_root.is_dir(), f"IAR root does not exist: {iar_root}")

    xlink_identity = selector._pin_tool(
        xlink_path,
        selector.EXPECTED_XLINK,
        label="XLINK",
        version_args=[],
        version_banner=selector.XLINK_VERSION_BANNER,
        encoding="cp1252",
    )
    objdump_identity = selector._pin_tool(
        objdump_path,
        selector.EXPECTED_OBJDUMP,
        label="objdump",
        version_args=["--version"],
        version_banner=selector.OBJDUMP_VERSION_BANNER,
        encoding="utf-8",
    )

    stm32_sources: dict[Path, bytes] = {}
    identities: dict[str, Any] = {}
    for relative, expected in EXPECTED_STM32_SOURCES.items():
        payload, identity = _read_pinned(stm32_root, relative, expected)
        stm32_sources[relative] = payload
        identities[f"STM32/{relative.as_posix()}"] = identity
    iar_sources: dict[Path, bytes] = {}
    for relative, expected in EXPECTED_IAR_SOURCES.items():
        payload, identity = _read_pinned(iar_root, relative, expected)
        iar_sources[relative] = payload
        identities[f"IAR/{relative.as_posix()}"] = identity

    deep = armcc.build_report(stm32_root / residual.LIBRARY_REL)
    abi = boundary.build_report(
        reference_root=stm32_root,
        library_path=stm32_root / residual.LIBRARY_REL,
    )
    iar_vendor_root = iar_root.parent
    _require(
        (iar_vendor_root / iar_root.name).resolve() == iar_root.resolve(),
        "IAR inner/outer root relationship changed",
    )
    residual_report = residual.build_report(
        stm32_root=stm32_root,
        iar_root=iar_vendor_root,
    )
    project_report = iar_project.build_report(iar_root)
    e1 = e2801.prove_object(iar_root / graph.OBJECT_DIR_REL / "E2801.r43")
    e2 = e2802.prove_object(iar_root / graph.OBJECT_DIR_REL / "E2802.r43")
    selector_report = selector.build_report(xlink_path, objdump_path, iar_root)

    _require(
        deep["loadwf"]["controller_or_chip_select_argument_present"] is False,
        "ArmCC loadWF gained target argument",
    )
    _require(
        [
            (row["command"], row["parameter_bytes"], row["pointer"])
            for row in deep["loadwf"]["success_transactions"]
        ]
        == [
            ("0x01", 6, "pwr_d"),
            ("0x30", 1, "pll_d"),
            ("0x20", 535, "in"),
            ("0x21", 704, "LUT1_DATA"),
        ],
        "ArmCC success transaction data-flow changed",
    )
    _require(
        e1["direct_call_graph"]["direct_display_caller_count"] == 7,
        "E2801 display caller count changed",
    )
    _require(
        e2["display_refresh_callers"]["logical_callers"] == 7,
        "E2802 display caller count changed",
    )
    for name, proof in (("E2801", e1), ("E2802", e2)):
        upload = proof["upload_temperature_lut"]
        _require(upload["lut0"]["source"] == "dataBuff + 4", f"{name} pointer changed")
        _require(upload["lut0"]["count_bytes"] == 799, f"{name} R20 count changed")
        _require(upload["lut1"]["count_bytes"] == 704, f"{name} R21 count changed")
        _require(upload["lut1"]["value"] == "0xFF", f"{name} R21 value changed")
    _require(
        selector_report["cross_object_adjudication"][
            "both_read_2508_bytes_after_a_match"
        ],
        "IAR matched-slot read changed",
    )
    _require(
        project_report["adjudication"]["current_Debug_Upload_Temperature_LUT_present"]
        is False,
        "runtime upload entered current IAR final",
    )

    gpio_objects: dict[str, Any] = {}
    for name in ("E2801.r43", "E2802.r43"):
        gpio_objects[name.removesuffix(".r43")] = _linked_gpio_transport(
            iar_root / graph.OBJECT_DIR_REL / name,
            xlink_path,
            objdump_path,
        )
    _require(
        len(
            {
                gpio_objects[name]["root_only_link"]["intel_hex_sha256"]
                for name in gpio_objects
            }
        )
        == 1,
        "IAR root-only images differ",
    )

    stm32_graph = _stm32_source_graph(stm32_root, stm32_sources, residual_report)
    iar_pin_contract = _iar_pin_contract(iar_root, iar_sources)

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "offline_read_only": True,
            "source_objects_modified": False,
            "temporary_link_copies_only": True,
            "temporary_outputs_discarded": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_or_refresh_requested": False,
            "visible_refreshes": 0,
            "live_token_or_claim_generated": False,
            "raw_object_code_or_disassembly_emitted": False,
            "raw_waveform_or_payload_emitted": False,
        },
        "identity": {
            "xlink": xlink_identity,
            "objdump": objdump_identity,
            "pinned_sources": identities,
            "STM32_tree_manifest_sha256": residual_report["upstream_cross_checks"][
                "vendor_artifact_hunt"
            ]["stm32_tree_manifest_sha256"],
            "IAR_tree_manifest_sha256": residual_report["upstream_cross_checks"][
                "vendor_artifact_hunt"
            ]["iar_tree_manifest_sha256"],
            "ArmCC_library": residual_report["arm_archive"]["identity"],
            "IAR_final_d43": project_report["final_outputs"]["Debug_d43"],
        },
        "legacy_IAR_active_upload_dataflow": {
            "objects": {
                "E2801": {
                    "direct_display_callers": 7,
                    "matched_slot_read_bytes": 2_508,
                    "matched_slot_destination": "dataBuff",
                    "r20": {
                        "source": "dataBuff+4",
                        "bytes": 799,
                        "dispatch": "EPD_Load_LUT(command,pointer,count)",
                    },
                    "r21": {
                        "source": "generated 0xFF loop",
                        "bytes": 704,
                        "dispatch": "direct SPI_COMMAND/SPI_DATA",
                    },
                    "PSR_inside_upload": True,
                    "PSR_source": "dataBuff[2] with mode-dependent bit 0x20",
                },
                "E2802": {
                    "direct_display_callers": 7,
                    "matched_slot_read_bytes": 2_508,
                    "matched_slot_destination": "dataBuff",
                    "r20": {
                        "source": "dataBuff+4",
                        "bytes": 799,
                        "dispatch": "EPD_Load_LUT(command,pointer,count)",
                    },
                    "r21": {
                        "source": "generated 0xFF loop",
                        "bytes": 704,
                        "dispatch": "direct SPI_COMMAND/SPI_DATA",
                    },
                    "PSR_inside_upload": False,
                    "EPD_Init_uses_prepopulated_dataBuff": True,
                },
            },
            "linked_transport_objects": gpio_objects,
            "GPIO_source_contract": iar_pin_contract,
            "cross_object": {
                "EPD_Load_LUT_register_ABI": "R12=command,R13=pointer,R14=count",
                "both_uploads_close_to_one_fixed_P6OUT_3_CS_path": True,
                "distinct_master_and_slave_destinations_present": False,
                "fixed_CS_path_proves_physical_controller_identity": False,
                "current_delivered_IAR_final_links_E2801_or_E2802": False,
            },
        },
        "ArmCC_mode0_callsite_and_destination": {
            "loadWF_prototype": deep["loadwf"]["prototype_from_dwarf"],
            "controller_or_chip_select_argument_present": False,
            "decoded_and_emitted": abi["exact_armcc_decoded_byte_use"],
            "success_transactions": deep["loadwf"]["success_transactions"],
            "source_and_link_graph": stm32_graph,
            "current_MAP_path_contains_loadWF": False,
            "source_resolvable_writeEPD_destination_if_loader_were_retained": (
                "single primary E_Paper_CS PD8 candidate"
            ),
            "dual_ToBoth_API_is_automatically_used_by_loadWF": False,
        },
        "800_byte_wrapper_gap": {
            "profiles": abi["candidate_800_records"]["profiles"],
            "same_generation_800_to_799_call_site_found": False,
            "same_generation_800_to_dual_controller_destination_found": False,
            "legacy_799_call_site_accepts_current_wrapper_directly": False,
            "current_ArmCC_loader_accepts_800_byte_wrapper": False,
            "candidate_padding_at_799_is_callsite_framing_proof": False,
            "chain_status": (
                "NO_IDENTITY_PINNED_CHAIN_FROM_EITHER_800_BYTE_WRAPPER_TO_A_"
                "SAME_GENERATION_799_BYTE_CALLSITE_OR_DUAL_CONTROLLER_SINK"
            ),
        },
        "field_semantics_boundary": {
            "directly_bound": {
                "ArmCC_mode0_decoded_0_through_4": "dedicated PWR parameters",
                "ArmCC_mode0_decoded_6": "dedicated PLL parameter",
                "IAR_E2801_dataBuff_2": "PSR byte before LUT upload",
                "IAR_both_dataBuff_4_through_802": "opaque R20 byte range",
            },
            "not_bound": {
                "candidate_800_category_labels": True,
                "candidate_800_phase_order_or_duration": True,
                "candidate_800_electrical_fields_beyond_cross_generation_hypothesis": True,
                "IAR_E2802_init_offsets_as_same_2508_slot_layout": True,
                "distinct_controller_specific_LUT_payloads": True,
            },
            "eleven_byte_parser_found_at_any_loader_callsite": False,
            "category_phase_or_voltage_semantics_promoted": False,
        },
        "adjudication": {
            "new_positive_finding": (
                "THE_ACTIVE_LEGACY_799_AND_704_UPLOADS_TERMINATE_IN_ONE_FIXED_"
                "P6OUT_3_CSB_PATH;_THE_ARMCC_SOURCE_RESOLUTION_CANDIDATE_IS_"
                "ALSO_SINGLE_PRIMARY_CS"
            ),
            "remaining_gap": (
                "NO_SUPPLIED_LOADER_CLOSES_EITHER_800_BYTE_WRAPPER_TO_A_SAME_"
                "GENERATION_DUAL_CONTROLLER_DESTINATION"
            ),
            "category_or_phase_fields_recovered": False,
            "current_dual_controller_acceptance_proven": False,
            "authorizes_live_hardware_action": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlink", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--stm32-root", type=Path, default=DEFAULT_STM32_ROOT)
    parser.add_argument("--iar-root", type=Path, default=DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(
            args.xlink,
            args.objdump,
            args.stm32_root,
            args.iar_root,
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
            write_new_bytes_durable(args.output, payload)
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.SubprocessError,
        ET.ParseError,
        DurableWriteError,
    ) as error:
        print(f"LUT call-site destination audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
