from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_ec5_color_lab_compiled_identity as gate
from tools import mf1750_ec5_color_lab_contract as contract
from tools import mf1750_ec5_compiled_identity as elf_reader


ROOT = Path(__file__).resolve().parents[1]


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _expected_payloads() -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for role, fields in gate.ROLE_SYMBOL_KEYS.items():
        for field, key in fields.items():
            value = bytes.fromhex(contract.ROLE_IDENTITIES[role][field]["sha256"])
            assert result.setdefault(key, value) == value
    return result


def _fixture_elf(
    *,
    overrides: dict[str, bytes] | None = None,
    omitted: set[str] | None = None,
    trailer: bytes = b"",
) -> bytes:
    overrides = overrides or {}
    omitted = omitted or set()
    keys = [key for key in gate.SYMBOL_NAMES if key not in omitted]
    expected = _expected_payloads()

    section_names = b"\0.shstrtab\0.strtab\0.symtab\0.flash.rodata\0"
    section_name_offsets = {
        name: section_names.index(name.encode("ascii"))
        for name in (".shstrtab", ".strtab", ".symtab", ".flash.rodata")
    }
    symbol_names = bytearray(b"\0")
    symbol_name_offsets: dict[str, int] = {}
    for key in keys:
        symbol_name_offsets[key] = len(symbol_names)
        symbol_names.extend(gate.SYMBOL_NAMES[key].encode("ascii") + b"\0")

    rodata = bytearray()
    rodata_offsets: dict[str, int] = {}
    for key in keys:
        rodata_offsets[key] = len(rodata)
        rodata.extend(overrides.get(key, expected[key]))

    rodata_address = 0x3C000000
    local_object = (elf_reader.STB_LOCAL << 4) | elf_reader.STT_OBJECT
    symbol_entries = [elf_reader.SYMBOL_ENTRY.pack(0, 0, 0, 0, 0, 0)]
    for key in keys:
        symbol_entries.append(
            elf_reader.SYMBOL_ENTRY.pack(
                symbol_name_offsets[key],
                rodata_address + rodata_offsets[key],
                len(overrides.get(key, expected[key])),
                local_object,
                0,
                4,
            )
        )
    symbols = b"".join(symbol_entries)

    image = bytearray(b"\0" * elf_reader.ELF_HEADER.size)
    offsets: dict[str, int] = {}
    payloads = (
        (".shstrtab", section_names),
        (".strtab", bytes(symbol_names)),
        (".symtab", symbols),
        (".flash.rodata", bytes(rodata)),
    )
    for name, payload in payloads:
        image.extend(b"\0" * (_align(len(image)) - len(image)))
        offsets[name] = len(image)
        image.extend(payload)
    image.extend(b"\0" * (_align(len(image)) - len(image)))
    section_offset = len(image)
    image.extend(elf_reader.SECTION_HEADER.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".shstrtab"],
            elf_reader.SHT_STRTAB,
            0,
            0,
            offsets[".shstrtab"],
            len(section_names),
            0,
            0,
            1,
            0,
        )
    )
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".strtab"],
            elf_reader.SHT_STRTAB,
            0,
            0,
            offsets[".strtab"],
            len(symbol_names),
            0,
            0,
            1,
            0,
        )
    )
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".symtab"],
            elf_reader.SHT_SYMTAB,
            0,
            0,
            offsets[".symtab"],
            len(symbols),
            2,
            len(symbol_entries),
            4,
            elf_reader.SYMBOL_ENTRY.size,
        )
    )
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".flash.rodata"],
            1,
            2,
            rodata_address,
            offsets[".flash.rodata"],
            len(rodata),
            0,
            0,
            4,
            0,
        )
    )
    ident = (
        elf_reader.ELF_MAGIC
        + bytes((elf_reader.ELFCLASS32, elf_reader.ELFDATA2LSB, 1))
        + b"\0" * 9
    )
    image[: elf_reader.ELF_HEADER.size] = elf_reader.ELF_HEADER.pack(
        ident,
        2,
        elf_reader.EM_XTENSA,
        1,
        0,
        0,
        section_offset,
        0,
        elf_reader.ELF_HEADER.size,
        0,
        0,
        elf_reader.SECTION_HEADER.size,
        5,
        1,
    )
    image.extend(trailer)
    return bytes(image)


def test_symbol_contract_covers_all_seven_roles_with_thirteen_exact_objects() -> None:
    assert set(gate.ROLE_SYMBOL_KEYS) == set(contract.ROLES)
    assert len(gate.SYMBOL_NAMES) == 13
    assert len(set(gate.SYMBOL_NAMES.values())) == 13
    assert gate.ROLE_SYMBOL_KEYS[contract.ROLE_U04_PRIMER] == (
        gate.ROLE_SYMBOL_KEYS[contract.ROLE_U07_PRIMER]
    )
    assert gate.ROLE_SYMBOL_KEYS[contract.ROLE_ATLAS]["cs1_dtm"] != (
        gate.ROLE_SYMBOL_KEYS[contract.ROLE_ATLAS]["cs2_dtm"]
    )


def test_exact_runtime_symbols_validate_offline(tmp_path: Path) -> None:
    elf = tmp_path / "color-lab.elf"
    elf.write_bytes(_fixture_elf())
    report = gate.validate(elf)
    assert report["valid"] is True
    assert report["offline"] is True
    assert report["device_io_performed"] is False
    assert report["execution_eligible"] is False
    assert report["action_count"] == 23
    assert report["contract_id"] == contract.campaign_manifest()["contract_id"]
    assert len(report["symbols"]) == 13
    assert set(report["roles"]) == set(contract.ROLES)


def test_wrong_exact_symbol_fails_even_if_correct_digest_exists_elsewhere(
    tmp_path: Path,
) -> None:
    expected = _expected_payloads()
    key = "atlas_cs2_dtm"
    elf = tmp_path / "wrong.elf"
    elf.write_bytes(
        _fixture_elf(overrides={key: b"\xAA" * 32}, trailer=expected[key])
    )
    with pytest.raises(
        gate.ColorLabCompiledIdentityError,
        match="symbol atlas_cs2_dtm differs from the frozen role fixture",
    ):
        gate.validate(elf)


def test_missing_runtime_symbol_fails_closed(tmp_path: Path) -> None:
    elf = tmp_path / "missing.elf"
    elf.write_bytes(_fixture_elf(omitted={"u07_target_dtm"}))
    with pytest.raises(
        gate.ColorLabCompiledIdentityError,
        match="must contain exactly one runtime symbol",
    ):
        gate.validate(elf)


def test_cli_emits_machine_readable_offline_report(tmp_path: Path) -> None:
    elf = tmp_path / "color-lab.elf"
    elf.write_bytes(_fixture_elf())
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/mf1750_ec5_color_lab_compiled_identity.py"),
            "--elf",
            str(elf),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["valid"] is True
    assert report["offline"] is True
    assert report["device_io_performed"] is False


def test_current_color_lab_elf_when_present() -> None:
    elf = (
        ROOT
        / ".pio/build/esp32-s3-devkitc-1-ec5-color-lab/firmware.elf"
    )
    if not elf.is_file():
        pytest.skip("current independent COLOR_LAB ELF is absent")
    report = gate.validate(elf)
    assert report["valid"] is True
