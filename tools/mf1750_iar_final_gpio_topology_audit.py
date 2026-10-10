#!/usr/bin/env python3
"""Recover the pinned final IAR image's GPIO and board-topology contract.

This audit is deliberately narrower than a general MSP430 disassembler.  It
decodes only identity-pinned instruction forms at the GPIO and CALLA sites in
the delivered absolute ``C2_Example.d43``.  The resulting addressed image is
first required to equal the delivered TI-TXT byte for byte.

The machine-code result is then kept separate from two other evidence layers:
the later V1.2 source tree and the exact MF-1750 specification / adjacent
E2802-cascade adapter schematic.  In particular, a single software CS endpoint
is not promoted into either a single-controller claim or a proven dual-chip
broadcast.  No hardware, serial port, device network, flash, reset, refresh,
physical authorization, LUT payload, or waveform payload interface exists.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_final_d43_provider_chain_audit as final_d43
from tools import mf1750_iar_r43_cross_object_graph as graph


KIND = "mf1750-iar-final-gpio-topology-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]

MF_SPEC_REL = Path("参考资料/MF-1750..1).pdf")
CASCADE_SCHEMATIC_REL = Path(
    "参考资料/55-00300-04736-N-InkCubic_ E2802_cascade 电子纸E6转接板.pdf"
)
SOURCE_ROOT_REL = Path(
    "参考资料/E6_73_sample code_V1.2_20250116/E6_73_sample code_V1.2_20250116"
)

EXPECTED_ADDITIONAL_FILES: dict[Path, tuple[int, str]] = {
    MF_SPEC_REL: (
        2_189_983,
        "c03ef3c34bbf4ece7d280d37197add64c67d0e13c26bff0861a1d399abbed187",
    ),
    CASCADE_SCHEMATIC_REL: (
        23_626,
        "c3f8f563b1222260224f5d76798052237acaec157e5cb78aca488ec12a30abe3",
    ),
    SOURCE_ROOT_REL / "pindefine.h": (
        1_470,
        "888e8e188ec9ec42ead37570d1900501a4321cbf1c1bb24cfb0ee58d4ba30525",
    ),
    SOURCE_ROOT_REL / "E6_73.c": (
        9_182,
        "8f511aca743bcd55d751d6d935261733b5931eb2fa101bb6d9f815cd0a8b06e9",
    ),
    SOURCE_ROOT_REL / "E6_73.h": (
        1_765,
        "56188e68ead9c42d4a86ff0ca6553216921f0fa513a7cd3b816f47eeb718b660",
    ),
    SOURCE_ROOT_REL / "main.c": (
        5_278,
        "b39520e578a257d0c9146fb4c84f65cd5f92743b12e6681c78a658733da710af",
    ),
    SOURCE_ROOT_REL / "Version_Descriptions.txt": (
        105,
        "53c39d6a7a0e14c17c6437727df6d26362f8a5f5c9ca550f28827047e44f9ecc",
    ),
}

EXPECTED_PDFPLUMBER_VERSION = "0.11.10"
EXPECTED_MF_SPEC_PAGE_COUNT = 24
EXPECTED_MF_SPEC_TEXT_SHA256 = (
    "81a10586746b9340ca63c464ffd45712238f414a4cf38d1a9acb045b393d5ec7"
)
EXPECTED_MF_SPEC_CRITICAL_PAGES: dict[int, tuple[int, str]] = {
    4: (1_506, "4c5bb8442825e74f14ad7676b6778cfdafa39186c00289c41147ecc47f98e60b"),
    5: (1_073, "343aa28ecdb89a0fc74065c009c00dac32e4d4fc4993af8c861acceabbe6ae68"),
    6: (1_328, "bdb35a308f1ececf23a2e28f73631512f67bcb20f57f1b8e65335c33978cea7d"),
    7: (1_665, "b2c851800cdc06227ad219df4e052a2b6aabb3f19448d985b2b71c5923db8ef4"),
    9: (1_122, "1ecd63ca5b01429f32d4401814f8bf043cf822eca3b7f7489d2b9c3863292a24"),
    10: (695, "609c12155756a8c1a93d034c5521b7c862586797974e9ecea8d9562fd2059b58"),
}
EXPECTED_CASCADE_TEXT = (
    5_030,
    "334eb15e91cade896bd8817958e511a032e7fb63e0597f498792c42403ff67da",
)

REGISTER_NAMES = {
    0x00: "PSR",
    0x01: "PWR",
    0x02: "POF",
    0x03: "POFS",
    0x04: "PON",
    0x05: "BTST1",
    0x06: "BTST2",
    0x08: "BTST3",
    0x10: "DTM",
    0x12: "DRF",
    0x30: "PLL",
    0x50: "CDI",
    0x60: "TCON",
    0x61: "TRES",
    0x84: "T_VDCS",
    0xE3: "PWS",
}

EXPECTED_INIT_TRANSACTIONS: tuple[tuple[int, tuple[int, ...]], ...] = (
    (0xAA, (0x49, 0x55, 0x20, 0x08, 0x09, 0x18)),
    (0x01, (0x3F,)),
    (0x00, (0x5F, 0x69)),
    (0x05, (0x40, 0x1F, 0x1F, 0x2C)),
    (0x08, (0x6F, 0x1F, 0x1F, 0x22)),
    (0x06, (0x6F, 0x1F, 0x17, 0x17)),
    (0x03, (0x00, 0x54, 0x00, 0x44)),
    (0x60, (0x02, 0x00)),
    (0x30, (0x08,)),
    (0x50, (0x3F,)),
    (0x61, (0x03, 0x20, 0x01, 0xE0)),
    (0xE3, (0x2F,)),
    (0x84, (0x01,)),
)

EXPECTED_DISPLAY_FILL = {
    "EPD_Display_White": 0x11,
    "EPD_Display_Black": 0x00,
    "EPD_Display_Yellow": 0x22,
    "EPD_Display_Red": 0x33,
    "EPD_Display_Blue": 0x55,
    "EPD_Display_Green": 0x66,
}


class FinalGpioTopologyAuditError(RuntimeError):
    """An identity or bounded decoding invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalGpioTopologyAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hex(value: int, width: int = 4) -> str:
    return f"0x{value:0{width}X}"


def _pin(path: Path, expected: tuple[int, str], label: str) -> bytes:
    _require(path.is_file(), f"{label} is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == expected[0],
        f"{label} size mismatch: expected {expected[0]}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == expected[1],
        f"{label} SHA-256 mismatch: expected {expected[1]}, got {digest}",
    )
    return payload


def _memory_bytes(memory: Mapping[int, int], start: int, size: int) -> bytes:
    try:
        return bytes(memory[address] for address in range(start, start + size))
    except KeyError as error:
        raise FinalGpioTopologyAuditError(
            f"addressed image is missing byte {_hex(int(error.args[0]))}"
        ) from error


def _decode_call_arg_u16(memory: Mapping[int, int], call_address: int) -> int:
    """Decode the bounded R12 constant forms used immediately before CALLA."""

    four = _memory_bytes(memory, call_address - 4, 4)
    if four[:2] in (b"\x3c\x40", b"\x7c\x40"):
        return int.from_bytes(four[2:], "little")
    two = four[2:]
    constant_generator = {
        b"\x4c\x43": 0,
        b"\x5c\x43": 1,
        b"\x6c\x43": 2,
        b"\x6c\x42": 4,
        b"\x7c\x42": 8,
        b"\x0c\x43": 0,
        b"\x1c\x43": 1,
        b"\x2c\x43": 2,
        b"\x2c\x42": 4,
        b"\x3c\x42": 8,
    }
    _require(
        two in constant_generator,
        f"unsupported R12 constant form before CALLA at {_hex(call_address)}",
    )
    return constant_generator[two]


def _decode_call_arg_u8(memory: Mapping[int, int], call_address: int) -> int:
    value = _decode_call_arg_u16(memory, call_address)
    _require(value <= 0xFF, f"R12 argument is not u8 at {_hex(call_address)}")
    return value


def _transaction_rows(
    parsed: Mapping[str, Any], caller: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memory = parsed["memory"]
    calls = [row for row in parsed["calls"] if row["caller"] == caller]
    transactions: list[dict[str, Any]] = []
    non_transport: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for call in calls:
        target = str(call["target"])
        address = int(call["address"])
        if target == "SPI_COMMAND":
            command = _decode_call_arg_u8(memory, address)
            current = {
                "command": _hex(command, 2),
                "command_name": REGISTER_NAMES.get(command),
                "call_site": _hex(address),
                "data": [],
                "data_call_sites": [],
            }
            transactions.append(current)
        elif target == "SPI_DATA":
            _require(current is not None, f"{caller} DATA call precedes COMMAND")
            current["data"].append(_hex(_decode_call_arg_u8(memory, address), 2))
            current["data_call_sites"].append(_hex(address))
        else:
            non_transport.append(
                {
                    "call_site": _hex(address),
                    "target": target,
                    "source_line": int(call["source_line"]),
                }
            )
    return transactions, non_transport


def _find_all(block: bytes, signature: bytes, base: int) -> list[int]:
    positions: list[int] = []
    offset = block.find(signature)
    while offset >= 0:
        positions.append(base + offset)
        offset = block.find(signature, offset + 1)
    return positions


def _machine_gpio_contract(parsed: Mapping[str, Any]) -> dict[str, Any]:
    memory: Mapping[int, int] = parsed["memory"]
    frame_by_name = {str(row["name"]): row for row in parsed["function_frames"]}
    final_block = _memory_bytes(memory, 0xA000, 2_000)

    local_addresses: dict[str, set[int]] = {}
    for row in parsed["local_data_symbols"]:
        local_addresses.setdefault(str(row["name"]), set()).add(int(row["address"]))
    expected_symbols = {
        "PBOUT_H": {0x0223},
        "PBDIR_H": {0x0225},
        "PCOUT_L": {0x0242},
        "PCOUT_H": {0x0243},
        "PCDIR_L": {0x0244},
        "PCDIR_H": {0x0245},
        "P6IN": {0x0241},
    }
    for name, expected in expected_symbols.items():
        _require(
            local_addresses.get(name) == expected,
            f"decoded register address set changed for {name}",
        )

    macro_expectations = {
        "SCL_L": {"P4OUT&=0x7F"},
        "SCL_H": {"P4OUT|=0x80"},
        "SDA_L": {"P4OUT&=0xBF"},
        "SDA_H": {"P4OUT|=0x40"},
        "DC_L": {"P5OUT&=0xFE"},
        "BS_H": {"P5OUT|=0x02"},
        "SWC_L": {"P6OUT&=0xFE"},
        "SWC_H": {"P6OUT|=0x01"},
        "RSTN_L": {"P6OUT&=0xFD"},
        "RSTN_H": {"P6OUT|=0x02"},
        "CSB_L": {"P6OUT&=0xF7"},
        "CSB_H": {"P6OUT|=0x08"},
        "BUSYN": {"P6IN_bit.P6IN2"},
    }
    for name, expected in macro_expectations.items():
        _require(
            parsed["macros"].get(name) == expected,
            f"decoded final macro changed for {name}",
        )

    p6_signatures = {
        ("SWC", "low"): bytes.fromhex("D2C34302"),
        ("SWC", "high"): bytes.fromhex("D2D34302"),
        ("RST_N", "low"): bytes.fromhex("E2C34302"),
        ("RST_N", "high"): bytes.fromhex("E2D34302"),
        ("CSB", "low"): bytes.fromhex("F2C24302"),
        ("CSB", "high"): bytes.fromhex("F2D24302"),
    }
    expected_p6_sites = {
        ("SWC", "low"): [0xA25C],
        ("SWC", "high"): [0xA782],
        ("RST_N", "low"): [0xA65E, 0xA696],
        ("RST_N", "high"): [0xA67A, 0xA6B2, 0xA77E],
        ("CSB", "low"): [0xA56A, 0xA5E6],
        ("CSB", "high"): [0xA5D4, 0xA650, 0xA772],
    }
    p6_rows: list[dict[str, Any]] = []
    for key, signature in p6_signatures.items():
        sites = _find_all(final_block, signature, 0xA000)
        _require(sites == expected_p6_sites[key], f"P6OUT sites changed for {key}")
        p6_rows.append(
            {
                "role": key[0],
                "level": key[1],
                "register_address": "0x0243",
                "bit_mask": {"SWC": "0x01", "RST_N": "0x02", "CSB": "0x08"}[key[0]],
                "instruction_sites": [_hex(site) for site in sites],
            }
        )
    all_pcout_h_literals = [
        0xA000 + offset
        for offset in range(len(final_block) - 1)
        if final_block[offset : offset + 2] == b"\x43\x02"
    ]
    decoded_operand_literals = sorted(
        site + len(signature) - 2
        for key, signature in p6_signatures.items()
        for site in expected_p6_sites[key]
    )
    _require(
        all_pcout_h_literals == decoded_operand_literals,
        "an unclassified 0x0243 operand literal appeared in final code",
    )

    p5_sites = {
        "BS_high": _find_all(final_block, bytes.fromhex("E2D34202"), 0xA000),
        "DC_low": _find_all(final_block, bytes.fromhex("D2C34202"), 0xA000),
    }
    _require(
        p5_sites == {"BS_high": [0xA776], "DC_low": [0xA77A]}, "P5OUT writes changed"
    )
    all_pcout_l_literals = [
        0xA000 + offset
        for offset in range(len(final_block) - 1)
        if final_block[offset : offset + 2] == b"\x42\x02"
    ]
    _require(
        all_pcout_l_literals == [0xA778, 0xA77C],
        "an unclassified 0x0242 operand literal appeared in final code",
    )

    transport_rows: dict[str, Any] = {}
    for name, dc_signature, dc_level, expected_signature_count in (
        ("SPI_COMMAND", bytes.fromhex("F2C040002302"), 0, 3),
        ("SPI_DATA", bytes.fromhex("F2D040002302"), 1, 2),
    ):
        frame = frame_by_name[name]
        start = int(frame["start"])
        size = int(frame["size"])
        block = _memory_bytes(memory, start, size)
        low = bytes.fromhex("F2C24302")
        high = bytes.fromhex("F2D24302")
        _require(
            block.find(low) == 4 and block.count(low) == 1, f"{name} CS low changed"
        )
        _require(
            block.find(high) == 110 and block.count(high) == 1,
            f"{name} CS high changed",
        )
        _require(
            block.find(dc_signature) == 14
            and block.count(dc_signature) == expected_signature_count,
            f"{name} ninth-bit write changed",
        )
        _require(
            block.count(bytes.fromhex("F2D080002302")) == 2,
            f"{name} SCL-high static site count changed",
        )
        _require(
            block.count(bytes.fromhex("F2C080002302")) == 2,
            f"{name} SCL-low static site count changed",
        )
        transport_rows[name] = {
            "function_start": _hex(start),
            "function_size_bytes": size,
            "CSB_low_site": _hex(start + 4),
            "ninth_DC_bit_on_SDA": dc_level,
            "ninth_bit_site": _hex(start + 14),
            "payload_bit_order": "D7_to_D0",
            "payload_clock_edges_per_dynamic_call": 8,
            "CSB_high_site": _hex(start + 110),
            "same_fixed_CSB_endpoint": True,
        }

    busy_frame = frame_by_name["check_busy_high"]
    busy_start = int(busy_frame["start"])
    busy_block = _memory_bytes(memory, busy_start, int(busy_frame["size"]))
    _require(
        busy_block == bytes.fromhex("3C40D007B013BAA7E2B241020E7E5E534E93FA271001"),
        "check_busy_high machine sequence changed",
    )

    reset_calls = [row for row in parsed["calls"] if row["caller"] == "reset"]
    _require(len(reset_calls) == 9, "reset delay call count changed")
    _require(
        all(
            _decode_call_arg_u16(memory, int(row["address"])) == 42_000
            for row in reset_calls
        ),
        "reset delay argument changed",
    )

    main_frame = frame_by_name["main"]
    main_block = _memory_bytes(
        memory, int(main_frame["start"]), int(main_frame["size"])
    )
    direction_signatures = {
        "P4DIR_bits_6_7_output": bytes.fromhex("F2D0C0002502F2F0C0002502"),
        "P5DIR_bits_0_1_output": bytes.fromhex("F2D003004402F2F003004402"),
        "P6DIR_bits_0_1_3_output_bit_2_input": bytes.fromhex(
            "F2D00B004502F2F00B004502"
        ),
    }
    for name, signature in direction_signatures.items():
        _require(
            main_block.count(signature) == 1, f"main direction setup changed: {name}"
        )

    return {
        "decoded_register_symbols": {
            name: _hex(next(iter(addresses)))
            for name, addresses in sorted(expected_symbols.items())
        },
        "pin_roles": {
            "SCL": {"MCU_pin": "P4.7", "register": "P4OUT/0x0223", "mask": "0x80"},
            "SDA": {"MCU_pin": "P4.6", "register": "P4OUT/0x0223", "mask": "0x40"},
            "DC_physical": {
                "MCU_pin": "P5.0",
                "register": "P5OUT/0x0242",
                "mask": "0x01",
            },
            "BS": {"MCU_pin": "P5.1", "register": "P5OUT/0x0242", "mask": "0x02"},
            "SWC": {"MCU_pin": "P6.0", "register": "P6OUT/0x0243", "mask": "0x01"},
            "RST_N": {"MCU_pin": "P6.1", "register": "P6OUT/0x0243", "mask": "0x02"},
            "BUSY_N": {"MCU_pin": "P6.2", "register": "P6IN/0x0241", "mask": "0x04"},
            "CSB": {"MCU_pin": "P6.3", "register": "P6OUT/0x0243", "mask": "0x08"},
        },
        "direction_initialization": {
            "P4.6_and_P4.7_outputs": True,
            "P5.0_and_P5.1_outputs": True,
            "P6.0_P6.1_P6.3_outputs": True,
            "P6.2_input": True,
        },
        "P6OUT_classified_writes": p6_rows,
        "P6OUT_operand_literal_count": len(all_pcout_h_literals),
        "all_P6OUT_operand_literals_classified": True,
        "P5OUT_classified_writes": {
            name: [_hex(site) for site in sites] for name, sites in p5_sites.items()
        },
        "all_P5OUT_operand_literals_classified": True,
        "transport": {
            "protocol": "software_9bit_3wire_SPI",
            "physical_DC_is_initialized_low_once": True,
            "physical_DC_high_write_present": False,
            "command_or_data_is_ninth_bit_on_SDA": True,
            "functions": transport_rows,
            "independent_second_CS_software_endpoint_present": False,
        },
        "reset": {
            "single_RST_N_software_endpoint": True,
            "active_low_pulse_count": 2,
            "delay_calls_between_edges": 9,
            "each_delay_argument": 42_000,
            "source_comment_dual_reset_does_not_identify_two_physical_sinks": True,
        },
        "busy": {
            "single_BUSY_N_software_endpoint": True,
            "polled_register": "P6IN/0x0241",
            "polled_mask": "0x04",
            "initial_delay_argument": 2_000,
            "waits_until_high": True,
            "timeout_or_second_busy_endpoint_present": False,
        },
        "power_switch": {
            "single_SWC_software_endpoint": True,
            "set_high_in_spi_9b_init": True,
            "set_low_once_at_end_of_main": True,
            "per_display_power_cut_present_in_final_D43": False,
        },
    }


def _command_contract(parsed: Mapping[str, Any]) -> dict[str, Any]:
    init, init_other = _transaction_rows(parsed, "EPD_Init")
    init_pairs = tuple(
        (
            int(row["command"], 16),
            tuple(int(value, 16) for value in row["data"]),
        )
        for row in init
    )
    _require(init_pairs == EXPECTED_INIT_TRANSACTIONS, "EPD_Init transactions changed")
    _require(
        [row["target"] for row in init_other] == ["reset", "check_busy_high", "delay"],
        "EPD_Init non-transport sequence changed",
    )
    memory = parsed["memory"]
    init_delay = next(
        row
        for row in parsed["calls"]
        if row["caller"] == "EPD_Init" and row["target"] == "delay"
    )
    _require(
        _decode_call_arg_u16(memory, int(init_delay["address"])) == 42_000,
        "EPD_Init post-busy delay changed",
    )

    display_rows: dict[str, Any] = {}
    for name, fill in EXPECTED_DISPLAY_FILL.items():
        transactions, other = _transaction_rows(parsed, name)
        pairs = [
            (
                int(row["command"], 16),
                [int(value, 16) for value in row["data"]],
            )
            for row in transactions
        ]
        _require(
            pairs
            == [
                (0x10, [fill]),
                (0x04, []),
                (0x06, [0x6F, 0x1F, 0x17, 0x49]),
                (0x12, [0x00]),
                (0x02, [0x00]),
            ],
            f"display transactions changed for {name}",
        )
        _require(
            [row["target"] for row in other]
            == ["check_busy_high", "check_busy_high", "check_busy_high"],
            f"display BUSY sequence changed for {name}",
        )
        fill_site = int(transactions[0]["data_call_sites"][0], 16)
        loop_signature = bytes.fromhex("1A530B632B93")
        frame = next(row for row in parsed["function_frames"] if row["name"] == name)
        block = _memory_bytes(memory, int(frame["start"]), int(frame["size"]))
        _require(
            block.count(loop_signature) == 1, f"display loop counter changed for {name}"
        )
        _require(
            bytes.fromhex("3A9000EE") in block,
            f"display low loop bound changed for {name}",
        )
        display_rows[name] = {
            "DTM_command": "0x10",
            "fill_byte": _hex(fill, 2),
            "fill_call_site_inside_loop": _hex(fill_site),
            "dynamic_fill_call_count": 192_000,
            "geometry_implied_by_4bpp_fill_only": "800x480",
            "post_DTM_sequence": ["PON", "BTST2", "DRF", "POF"],
            "busy_waits": 3,
            "per_display_delay_after_POF_present": False,
            "per_display_PSR_rewrite_present": False,
            "per_display_GPIO_power_cut_present": False,
        }

    commands = [command for command, _data in init_pairs]
    commands.extend([0x10, 0x04, 0x06, 0x12, 0x02])
    return {
        "EPD_Init_transactions": init,
        "EPD_Init_non_transport_calls": init_other,
        "named_register_values": {
            "PWR": {"command": "0x01", "data": ["0x3F"]},
            "PSR": {"command": "0x00", "data": ["0x5F", "0x69"]},
            "PLL": {"command": "0x30", "data": ["0x08"]},
            "TRES": {
                "command": "0x61",
                "data": ["0x03", "0x20", "0x01", "0xE0"],
                "decoded_dimensions": [800, 480],
            },
        },
        "display_functions": display_rows,
        "main_display_order": [
            "EPD_Display_White",
            "EPD_Display_Black",
            "EPD_Display_Red",
            "EPD_Display_Yellow",
            "EPD_Display_Blue",
            "EPD_Display_Green",
            "EPD_Display_White",
        ],
        "command_0xE0_CCSET_present": 0xE0 in commands,
        "command_0x20_runtime_LUT_present": 0x20 in commands,
        "command_0x21_runtime_LUT_present": 0x21 in commands,
        "raw_0xE0_as_TRES_height_byte_not_a_command": True,
    }


def _extract_pdf(
    payload: bytes, *, words: bool = False
) -> tuple[list[str], list[dict[str, Any]], str]:
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - environment failure
        raise FinalGpioTopologyAuditError(
            "pdfplumber is required for PDF extraction"
        ) from error
    try:
        with pdfplumber.open(io.BytesIO(payload)) as document:
            pages = [page.extract_text() or "" for page in document.pages]
            extracted_words = (
                document.pages[0].extract_words(x_tolerance=1, y_tolerance=3)
                if words
                else []
            )
    except Exception as error:  # pragma: no cover - parser failure
        raise FinalGpioTopologyAuditError(
            f"could not parse pinned PDF: {error}"
        ) from error
    return pages, extracted_words, str(pdfplumber.__version__)


def _word_anchor(
    words: Iterable[Mapping[str, Any]], text: str, top: float
) -> dict[str, Any]:
    matches = [
        word
        for word in words
        if word["text"] == text and abs(float(word["top"]) - top) < 0.001
    ]
    _require(len(matches) == 1, f"schematic word anchor changed: {text}@{top}")
    word = matches[0]
    return {
        "text": text,
        "x0": round(float(word["x0"]), 3),
        "top": round(float(word["top"]), 3),
    }


def _pdf_topology_contract(
    mf_payload: bytes, schematic_payload: bytes
) -> dict[str, Any]:
    mf_pages, _unused, mf_version = _extract_pdf(mf_payload)
    _require(
        mf_version == EXPECTED_PDFPLUMBER_VERSION,
        "pdfplumber version changed for MF specification",
    )
    _require(len(mf_pages) == EXPECTED_MF_SPEC_PAGE_COUNT, "MF spec page count changed")
    _require(
        _sha256("\f".join(mf_pages).encode("utf-8")) == EXPECTED_MF_SPEC_TEXT_SHA256,
        "MF spec extracted text changed",
    )
    critical_rows: dict[str, Any] = {}
    for page_number, expected in EXPECTED_MF_SPEC_CRITICAL_PAGES.items():
        text = mf_pages[page_number - 1]
        actual = (len(text), _sha256(text.encode("utf-8")))
        _require(actual == expected, f"MF spec page {page_number} text changed")
        critical_rows[str(page_number)] = {
            "characters": actual[0],
            "sha256": actual[1],
        }
    required_lines = {
        4: ["1024×600 pixels", "3-bit E6 full display capabilities"],
        5: ["0.5T+SPD1657*2ea."],
        6: [
            "4 SL_CSB Slave Chip Select input pin (SL_CSB)",
            "24 TSCL Cascade signal, connect a pull-up resistor",
            "25 TSDA Cascade signal, connect a pull-up resistor",
            "28 RST_N Reset",
            "29 BUSY_N Busy state output pin",
            "30 DC Data /Command control pin (D/C)",
        ],
        7: [
            "31 CSB Chip Select input pin (CSB)",
            "The Reset is active low.",
            "When Busy is High",
        ],
        9: [
            "The 3-wire SPI consists of serial clock SCL, serial data SDA and CSB.",
            "DC pin is not used and it must be tied to LOW.",
            "a 9-bit data will be shifted",
        ],
        10: ["Part Name SPD1657B"],
    }
    for page_number, needles in required_lines.items():
        for needle in needles:
            _require(
                needle in mf_pages[page_number - 1],
                f"MF spec semantic text changed on page {page_number}: {needle}",
            )

    schematic_pages, words, schematic_version = _extract_pdf(
        schematic_payload, words=True
    )
    _require(
        schematic_version == EXPECTED_PDFPLUMBER_VERSION,
        "pdfplumber version changed for cascade schematic",
    )
    _require(len(schematic_pages) == 1, "cascade schematic page count changed")
    schematic_text = schematic_pages[0]
    _require(
        (len(schematic_text), _sha256(schematic_text.encode("utf-8")))
        == EXPECTED_CASCADE_TEXT,
        "cascade schematic extracted text changed",
    )
    anchors = {
        "U1_pin4_number": _word_anchor(words, "4", 249.186766),
        "U1_pin4_drawn_name": _word_anchor(words, "FPL_VCOM", 246.281866),
        "U1_pin5_number": _word_anchor(words, "5", 256.386766),
        "U1_pin5_drawn_name": _word_anchor(words, "NC", 253.481866),
        "U1_SL_CSB_net": _word_anchor(words, "SL_CSB", 250.626766),
        "U1_pin4_series_resistor": _word_anchor(words, "R10", 249.411398),
        "U1_CSB_symbol": _word_anchor(words, "CSB", 447.881866),
        "J1_reference": _word_anchor(words, "J1", 416.946766),
        "J1_single_CS_label": _word_anchor(words, "CS", 458.681866),
        "J4_reference": _word_anchor(words, "J4", 613.87104),
        "J4_SL_CSB_label": _word_anchor(words, "SL_CSB", 625.026766),
        "J4_CS_label": _word_anchor(words, "CS", 632.226766),
        "J2_TSCL_reference": _word_anchor(words, "J2", 510.19104),
        "J2_TSCL_label": _word_anchor(words, "TSCL", 520.626766),
        "J2_pullup_resistor": _word_anchor(words, "R15", 541.731398),
        "J3_TSDA_reference": _word_anchor(words, "J3", 563.47104),
        "J3_TSDA_label": _word_anchor(words, "TSDA", 574.626766),
        "J3_pullup_resistor": _word_anchor(words, "R16", 594.952098),
    }
    return {
        "extractor": {
            "name": "pdfplumber",
            "version": EXPECTED_PDFPLUMBER_VERSION,
        },
        "exact_MF1750_specification": {
            "page_count": len(mf_pages),
            "full_extracted_text_sha256": EXPECTED_MF_SPEC_TEXT_SHA256,
            "critical_page_text": critical_rows,
            "panel_model": "MF-17506-M009F-T / M009F-T",
            "geometry": "1024x600",
            "pixel_transport": "3-bit E6",
            "controller_count": 2,
            "controller_marking": "SPD1657; reference BOM names SPD1657B",
            "pins": {
                "SL_CSB": 4,
                "TSCL": 24,
                "TSDA": 25,
                "RST_N": 28,
                "BUSY_N": 29,
                "DC": 30,
                "CSB": 31,
                "SCL": 32,
                "SI0": 33,
            },
            "TSCL_and_TSDA_require_pullups": True,
            "three_wire_contract": {
                "DC_tied_low": True,
                "nine_bits_per_transfer": True,
                "first_bit_selects_command_or_data": True,
            },
        },
        "adjacent_vendor_E2802_cascade_adapter": {
            "word_coordinate_anchors": anchors,
            "external_J1_exposes_one_CS": True,
            "J4_exposes_CS_and_SL_CSB_as_two_separate_header_pins": True,
            "J4_bridge_closed_by_copper_in_schematic": False,
            "J4_can_be_shorted_to_fan_one_CS_out_to_SL_CSB": True,
            "J2_and_J3_offer_jumperable_4k7_pullups_for_TSCL_TSDA": True,
            "U1_pin4_net_is_named_SL_CSB_through_R10_0R": True,
            "U1_graphical_pin4_name_is_FPL_VCOM": True,
            "U1_graphical_pin5_name_is_NC": True,
            "U1_pin4_symbol_FPL_VCOM_conflicts_with_net_SL_CSB": True,
            "U1_graphical_symbol_conflicts_with_exact_MF_spec_pin4_name": True,
            "physical_header_population_or_jumper_state_proven": False,
            "exact_current_panel_or_board_identity_proven_by_schematic": False,
        },
    }


def _source_lineage_contract(
    pinned: Mapping[Path, bytes], parsed: Mapping[str, Any]
) -> dict[str, Any]:
    source = pinned[SOURCE_ROOT_REL / "E6_73.c"].decode("latin-1")
    pins = pinned[SOURCE_ROOT_REL / "pindefine.h"].decode("latin-1")
    versions = pinned[SOURCE_ROOT_REL / "Version_Descriptions.txt"].decode("ascii")
    _require(
        "V1.2 20250116 --> add VDD cut sequence at each display function" in versions,
        "version description changed",
    )
    _require(source.count("//20250116") == 6, "V1.2 display-tail marker count changed")
    _require(source.count("delay_1s(6);") == 6, "V1.2 six-second delay count changed")
    _require(source.count("SWC_L;//VDD SW off") == 6, "V1.2 SWC cut count changed")
    expected_pin_lines = (
        "#define DC_L    P5OUT&=0xFE",
        "#define RSTN_L  P6OUT&=0xFD",
        "#define CSB_L  \tP6OUT&=0xF7",
        "#define SCL_L  \tP4OUT&=0x7F",
        "#define SDA_L \tP4OUT&=0xBF",
        "#define BS_H    P5OUT|=0x02",
        "#define SWC_L    P6OUT&=0xFE",
        "#define BUSYN \tP6IN_bit.P6IN2",
    )
    for line in expected_pin_lines:
        _require(line in pins, f"V1.2 pin macro changed: {line}")
    scoped_names = set(parsed["scoped_names"].values())
    return {
        "delivered_tree_version": "V1.2 20250116",
        "final_D43_embedded_source_lineage": "V1.1 20231030",
        "same_build_source_and_final_binary": False,
        "V1_2_declared_change": "add VDD cut sequence at each display function",
        "V1_2_display_tail_count": 6,
        "V1_2_each_tail_contains_six_second_delay_and_SWC_low": True,
        "delay_1s_scoped_name_present_in_final_D43": "delay_1s" in scoped_names,
        "final_D43_each_display_contains_V1_2_tail": False,
        "shared_pin_macro_text_matches_final_debug_macros": True,
        "source_text_can_define_final_transport_topology_without_machine_check": False,
    }


def build_report(
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    xlib_identity = final_d43._pin_xlib(xlib_path)
    d43_payload = _pin(
        iar_root / "Debug/Exe/C2_Example.d43",
        final_d43.EXPECTED_FILES["Debug/Exe/C2_Example.d43"],
        "final D43",
    )
    ti_txt_payload = _pin(
        iar_root / "Debug/Exe/C2_Example.txt",
        final_d43.EXPECTED_FILES["Debug/Exe/C2_Example.txt"],
        "final TI-TXT",
    )
    pinned: dict[Path, bytes] = {}
    for relative, expected in EXPECTED_ADDITIONAL_FILES.items():
        pinned[relative] = _pin(repo_root / relative, expected, relative.as_posix())

    listing = final_d43._run_xlib_list_object_code(
        xlib_path, iar_root / "Debug/Exe/C2_Example.d43"
    )
    parsed = final_d43.parse_xlib_object_code(listing)
    final_d43._validate_direct_call_machine_bytes(parsed)
    ti_txt = final_d43._parse_ti_txt(ti_txt_payload)
    _require(parsed["memory"] == ti_txt["memory"], "D43 and TI-TXT bytes differ")
    _require(len(parsed["memory"]) == 2_002, "addressed final image size changed")
    _require(parsed["embedded_v1_1_path_rows"] > 0, "V1.1 lineage disappeared")
    _require(parsed["embedded_v1_2_path_rows"] == 0, "V1.2 lineage appeared in D43")

    frame_by_name = {str(row["name"]): row for row in parsed["function_frames"]}
    for name in (
        "EPD_Init",
        *EXPECTED_DISPLAY_FILL,
        "SPI_DATA",
        "SPI_COMMAND",
        "reset",
        "spi_9b_init",
        "check_busy_high",
        "main",
    ):
        _require(name in frame_by_name, f"required final frame is missing: {name}")

    machine = _machine_gpio_contract(parsed)
    commands = _command_contract(parsed)
    pdf_topology = _pdf_topology_contract(
        pinned[MF_SPEC_REL], pinned[CASCADE_SCHEMATIC_REL]
    )
    source_lineage = _source_lineage_contract(pinned, parsed)

    identity_rows = {
        relative.as_posix(): {
            "size_bytes": len(payload),
            "sha256": _sha256(payload),
        }
        for relative, payload in sorted(
            pinned.items(), key=lambda item: item[0].as_posix()
        )
    }
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refresh_requested": False,
            "physical_action_token_or_claim_created": False,
            "raw_D43_or_TI_TXT_bytes_emitted": False,
            "raw_LUT_or_waveform_emitted": False,
        },
        "identity": {
            "xlib": xlib_identity,
            "final_D43": {
                "path": "Debug/Exe/C2_Example.d43",
                "size_bytes": len(d43_payload),
                "sha256": _sha256(d43_payload),
            },
            "final_TI_TXT": {
                "path": "Debug/Exe/C2_Example.txt",
                "size_bytes": len(ti_txt_payload),
                "sha256": _sha256(ti_txt_payload),
            },
            "additional_evidence": identity_rows,
        },
        "absolute_image_proof": {
            "official_operation": "XLIB LIST-OBJECT-CODE on delivered absolute D43",
            "D43_decoded_image_equals_TI_TXT_addressed_image": True,
            "addressed_byte_count": len(parsed["memory"]),
            "segments": [
                {"start": "0xA000", "size_bytes": 2_000},
                {"start": "0xFFFE", "size_bytes": 2},
            ],
            "all_direct_CALLA_machine_targets_validated": True,
        },
        "final_machine_gpio_contract": machine,
        "final_machine_command_contract": commands,
        "source_binary_lineage": source_lineage,
        "panel_and_adapter_topology": pdf_topology,
        "adjudication": {
            "final_D43_software_CS_endpoint_count": 1,
            "exact_MF1750_physical_controller_count": 2,
            "adjacent_adapter_has_conditional_one_to_two_CS_fanout_path": True,
            "fanout_condition": "J4 electrically closed between CS and SL_CSB",
            "J4_current_physical_state": "UNKNOWN",
            "if_J4_open_on_adjacent_adapter": (
                "P6OUT.3 reaches only the adapter CS/CSB path; SL_CSB is separate"
            ),
            "if_J4_closed_on_adjacent_adapter": (
                "P6OUT.3 broadcasts identical select timing to CSB and SL_CSB"
            ),
            "pin4_symbol_FPL_VCOM_vs_net_SL_CSB_conflict_is_blocker": True,
            "exact_as_built_dual_controller_fanout_proven": False,
            "independent_controller_selection_possible_from_final_D43": False,
            "per_controller_payload_or_load_order_recoverable_from_final_D43": False,
            "shared_or_separate_RST_BUSY_DC_sinks_physically_proven": False,
            "CCSET_or_other_dual_controller_enable_present_in_final_D43": False,
            "final_D43_geometry_matches_exact_MF1750": False,
            "final_D43_geometry": "800x480/192000 packed bytes",
            "exact_MF1750_geometry": "1024x600/two SPD1657",
            "adjacent_adapter_verdict": "CONDITIONAL_FANOUT_PATH_SHOWN",
            "exact_as_built_board_verdict": "NOT_PROVEN",
            "blocking_reason": (
                "The adjacent adapter draws pin 4 as FPL_VCOM while naming its incoming "
                "net SL_CSB through R10 0R; J4 population/state is also unknown."
            ),
        },
        "evidence_boundaries": {
            "single_software_CS_does_not_prove_single_physical_controller": True,
            "single_software_CS_does_not_prove_dual_broadcast": True,
            "adapter_jumper_option_does_not_prove_as_built_state": True,
            "adapter_graphical_pin4_FPL_VCOM_conflict_is_not_silently_resolved": True,
            "exact_MF_spec_pin4_SL_CSB_is_kept_as_separate_direct_evidence": True,
            "source_V1_2_is_not_promoted_to_final_D43_machine_behavior": True,
            "command_data_values_are_exact_but_electrical_voltages_are_not_inferred": True,
            "no_runtime_LUT_loader_or_recovery_contract_is_inferred": True,
            "required_next_discriminator": (
                "identity-pinned as-built continuity/population evidence for J4 or a full "
                "CS/SL_CSB/SCL/SDA/RST/BUSY capture from the exact board"
            ),
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.xlib, args.iar_root, args.repo_root)
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
        subprocess.SubprocessError,
        FinalGpioTopologyAuditError,
        final_d43.FinalD43AuditError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
