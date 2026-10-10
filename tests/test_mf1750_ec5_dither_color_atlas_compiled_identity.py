from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_compiled_identity as elf_reader
from tools import mf1750_ec5_dither_color_atlas_compiled_identity as gate
from tools import mf1750_ec5_dither_color_atlas_contract as contract


ROOT = Path(__file__).resolve().parents[1]
REAL_BUILD = (
    ROOT / ".pio/build/esp32-s3-devkitc-1-ec5-dither-color-atlas"
)


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _role_sha_values() -> dict[str, str]:
    values: dict[str, str] = {}
    fields = ("frame", "cs1_dtm", "cs2_dtm")
    for role, keys in gate.ROLE_SHA_KEYS.items():
        identity = contract.ROLE_IDENTITIES[role]
        for key, field in zip(keys, fields, strict=True):
            value = str(identity[field]["sha256"])
            assert values.setdefault(key, value) == value
    return values


def _encode_call(pc: int, target: int, *, window: int = 2) -> bytes:
    base = (pc + 4) & ~3
    delta = target - base
    assert delta % 4 == 0
    displacement = delta // 4
    assert -(1 << 17) <= displacement < 1 << 17
    instruction = ((displacement & ((1 << 18) - 1)) << 6) | (window << 4) | 5
    return instruction.to_bytes(3, "little")


def _fixture_elf(
    *,
    tamper_action_fnv: bool = False,
    tamper_driver_sha: str | None = None,
    display_call_count: int = 1,
    validator_call_count: int = 1,
    forbidden_runtime_string: str | None = None,
    extra_fixture_main: str | None = None,
    trailer: bytes = b"",
) -> bytes:
    assert display_call_count in (0, 1, 2)
    assert validator_call_count in (0, 1, 2)
    rodata_address = 0x3C000000
    text_address = 0x42000000
    rodata = bytearray()

    def reserve(size: int, *, alignment: int = 4) -> int:
        rodata.extend(b"\0" * (_align(len(rodata), alignment) - len(rodata)))
        offset = len(rodata)
        rodata.extend(b"\0" * size)
        return offset

    actions_offset = reserve(
        gate.ACTION_RECORD.size * len(contract.DESCRIPTORS)
    )
    identities_offset = reserve(
        gate.DRIVER_IDENTITY_RECORD.size * len(contract.ROLES)
    )

    expected_sha = _role_sha_values()
    sha_offsets: dict[str, int] = {}
    runtime_strings: dict[str, int] = {}
    for key in gate.DRIVER_SHA_SYMBOLS:
        value = expected_sha[key]
        payload = value.encode("ascii") + b"\0"
        if key == tamper_driver_sha:
            payload = b"f" * 64 + b"\0"
        offset = reserve(len(payload), alignment=1)
        rodata[offset : offset + len(payload)] = payload
        sha_offsets[key] = offset
        if key != tamper_driver_sha:
            runtime_strings.setdefault(value, offset)

    def add_runtime_string(value: str) -> int:
        existing = runtime_strings.get(value)
        if existing is not None:
            return existing
        payload = value.encode("ascii") + b"\0"
        offset = reserve(len(payload), alignment=1)
        rodata[offset : offset + len(payload)] = payload
        runtime_strings[value] = offset
        return offset

    for value in gate.required_identity_strings():
        add_runtime_string(value)
    if forbidden_runtime_string is not None:
        add_runtime_string(forbidden_runtime_string)

    for index, descriptor in enumerate(contract.DESCRIPTORS):
        role = str(descriptor["role"])
        identity = contract.ROLE_IDENTITIES[role]
        prior = descriptor["action_identity_preimage"]["prior_static_action_id"]
        frame_fnv = int(identity["frame"]["fnv1a_u32"])
        if tamper_action_fnv and index == 0:
            frame_fnv ^= 1
        values = (
            int(descriptor["ordinal"]),
            gate.DRIVER_ROLE_BY_ROLE[role],
            rodata_address + add_runtime_string(role),
            int(descriptor["round"]),
            rodata_address + add_runtime_string(str(descriptor["branch"])),
            rodata_address
            + add_runtime_string(str(descriptor["descriptor_id"])),
            rodata_address
            + add_runtime_string(str(descriptor["hardware_action_id"])),
            0 if prior is None else rodata_address + add_runtime_string(str(prior)),
            rodata_address
            + add_runtime_string(str(descriptor["frame_sha256"])),
            rodata_address
            + add_runtime_string(str(descriptor["cs1_dtm_sha256"])),
            rodata_address
            + add_runtime_string(str(descriptor["cs2_dtm_sha256"])),
            frame_fnv,
            int(identity["cs1_dtm"]["fnv1a_u32"]),
            int(identity["cs2_dtm"]["fnv1a_u32"]),
            *gate._histogram(role),
        )
        packed = gate.ACTION_RECORD.pack(*values)
        start = actions_offset + index * gate.ACTION_RECORD.size
        rodata[start : start + len(packed)] = packed

    for index, role in enumerate(contract.ROLES):
        identity = contract.ROLE_IDENTITIES[role]
        keys = gate.ROLE_SHA_KEYS[role]
        values = (
            int(identity["frame"]["fnv1a_u32"]),
            int(identity["cs1_dtm"]["fnv1a_u32"]),
            int(identity["cs2_dtm"]["fnv1a_u32"]),
            rodata_address + sha_offsets[keys[0]],
            rodata_address + sha_offsets[keys[1]],
            rodata_address + sha_offsets[keys[2]],
            *gate._histogram(role),
        )
        packed = gate.DRIVER_IDENTITY_RECORD.pack(*values)
        start = identities_offset + index * gate.DRIVER_IDENTITY_RECORD.size
        rodata[start : start + len(packed)] = packed

    setup_offset = 0x20
    display_offset = 0x100
    fixture_validator_offset = 0x110
    text = bytearray(b"\0" * 0x114)
    for index in range(display_call_count):
        call_offset = index * 4
        text[call_offset : call_offset + 3] = _encode_call(
            text_address + call_offset,
            text_address + display_offset,
        )
    for index in range(validator_call_count):
        call_offset = setup_offset + index * 4
        text[call_offset : call_offset + 3] = _encode_call(
            text_address + call_offset,
            text_address + fixture_validator_offset,
        )

    local_file = (gate.STB_LOCAL << 4) | gate.STT_FILE
    local_object = (gate.STB_LOCAL << 4) | gate.STT_OBJECT
    global_function = (gate.STB_GLOBAL << 4) | gate.STT_FUNC
    symbol_definitions: list[tuple[str, int, int, int, int, int]] = [
        (gate.EXPECTED_MAIN_FILE, 0, 0, local_file, 0, gate.SHN_ABS)
    ]
    if extra_fixture_main is not None:
        symbol_definitions.append(
            (extra_fixture_main, 0, 0, local_file, 0, gate.SHN_ABS)
        )
    symbol_definitions.extend(
        (
            (
                gate.ACTION_SYMBOL,
                rodata_address + actions_offset,
                gate.ACTION_RECORD.size * len(contract.DESCRIPTORS),
                local_object,
                0,
                4,
            ),
            (
                gate.DRIVER_IDENTITIES_SYMBOL,
                rodata_address + identities_offset,
                gate.DRIVER_IDENTITY_RECORD.size * len(contract.ROLES),
                local_object,
                0,
                4,
            ),
        )
    )
    for key, symbol_name in gate.DRIVER_SHA_SYMBOLS.items():
        symbol_definitions.append(
            (
                symbol_name,
                rodata_address + sha_offsets[key],
                65,
                local_object,
                0,
                4,
            )
        )
    first_global = len(symbol_definitions) + 1
    symbol_definitions.extend(
        (
            (gate.LOOP_SYMBOL, text_address, 8, global_function, 0, 5),
            (
                gate.SETUP_SYMBOL,
                text_address + setup_offset,
                8,
                global_function,
                0,
                5,
            ),
            (
                gate.DISPLAY_SYMBOL,
                text_address + display_offset,
                4,
                global_function,
                0,
                5,
            ),
            (
                gate.FIXTURE_VALIDATOR_SYMBOL,
                text_address + fixture_validator_offset,
                4,
                global_function,
                0,
                5,
            ),
        )
    )

    symbol_names = bytearray(b"\0")
    symbol_name_offsets: dict[str, int] = {}
    for name, *_rest in symbol_definitions:
        if name not in symbol_name_offsets:
            symbol_name_offsets[name] = len(symbol_names)
            symbol_names.extend(name.encode("ascii") + b"\0")
    symbol_entries = [elf_reader.SYMBOL_ENTRY.pack(0, 0, 0, 0, 0, 0)]
    for name, value, size, info, other, section_index in symbol_definitions:
        symbol_entries.append(
            elf_reader.SYMBOL_ENTRY.pack(
                symbol_name_offsets[name], value, size, info, other, section_index
            )
        )
    symtab = b"".join(symbol_entries)

    section_names = (
        b"\0.shstrtab\0.strtab\0.symtab\0.flash.rodata\0.flash.text\0"
    )
    section_name_offsets = {
        name: section_names.index(name.encode("ascii"))
        for name in (
            ".shstrtab",
            ".strtab",
            ".symtab",
            ".flash.rodata",
            ".flash.text",
        )
    }
    image = bytearray(b"\0" * elf_reader.ELF_HEADER.size)
    offsets: dict[str, int] = {}
    for name, payload in (
        (".shstrtab", section_names),
        (".strtab", bytes(symbol_names)),
        (".symtab", symtab),
        (".flash.rodata", bytes(rodata)),
        (".flash.text", bytes(text)),
    ):
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
            len(symtab),
            2,
            first_global,
            4,
            elf_reader.SYMBOL_ENTRY.size,
        )
    )
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".flash.rodata"],
            1,
            gate.SHF_ALLOC,
            rodata_address,
            offsets[".flash.rodata"],
            len(rodata),
            0,
            0,
            4,
            0,
        )
    )
    image.extend(
        elf_reader.SECTION_HEADER.pack(
            section_name_offsets[".flash.text"],
            1,
            gate.SHF_ALLOC | gate.SHF_EXECINSTR,
            text_address,
            offsets[".flash.text"],
            len(text),
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
        text_address,
        0,
        section_offset,
        0,
        elf_reader.ELF_HEADER.size,
        0,
        0,
        elf_reader.SECTION_HEADER.size,
        6,
        1,
    )
    image.extend(trailer)
    return bytes(image)


def _fixture_bin(elf: bytes) -> bytes:
    binary = bytearray(b"\0" * (gate.EMBEDDED_ELF_SHA256_OFFSET + 32))
    binary[0] = 0xE9
    binary[
        gate.APP_DESCRIPTOR_OFFSET : gate.APP_DESCRIPTOR_OFFSET
        + len(gate.APP_DESCRIPTOR_MAGIC)
    ] = gate.APP_DESCRIPTOR_MAGIC
    binary[
        gate.EMBEDDED_ELF_SHA256_OFFSET : gate.EMBEDDED_ELF_SHA256_OFFSET + 32
    ] = hashlib.sha256(elf).digest()
    binary.extend(elf)
    return bytes(binary)


def _write_pair(
    tmp_path: Path, elf: bytes, binary: bytes | None = None
) -> tuple[Path, Path]:
    elf_file = tmp_path / "firmware.elf"
    binary_file = tmp_path / "firmware.bin"
    elf_file.write_bytes(elf)
    binary_file.write_bytes(_fixture_bin(elf) if binary is None else binary)
    return elf_file, binary_file


def test_exact_actions_driver_calls_and_pair_validate(tmp_path: Path) -> None:
    elf_file, binary_file = _write_pair(tmp_path, _fixture_elf())
    report = gate.validate_artifacts(elf_file, binary_file)
    assert report["valid"] is True
    assert report["offline"] is True
    assert report["device_io_performed"] is False
    assert report["serial_io_performed"] is False
    assert report["network_io_performed"] is False
    assert report["upload_performed"] is False
    assert report["visible_refreshes"] == 0
    assert report["main"]["action_count"] == 2
    assert report["driver"]["role_count"] == 2
    assert report["executable"]["display_direct_call_count"] == 1
    assert report["executable"]["fixture_validator_direct_call_count"] == 1
    assert report["firmware"]["binary_elf_link"]["exact_match"] is True
    assert set(report["driver"]["roles"]) == set(contract.ROLES)


def test_tampered_exact_action_object_fails(tmp_path: Path) -> None:
    elf_file, binary_file = _write_pair(
        tmp_path, _fixture_elf(tamper_action_fnv=True)
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="ActionDescriptor ordinal 1 scalar identity differs",
    ):
        gate.validate_artifacts(elf_file, binary_file)


def test_tampered_exact_sha_symbol_fails_with_correct_sha_elsewhere(
    tmp_path: Path,
) -> None:
    elf_file, binary_file = _write_pair(
        tmp_path, _fixture_elf(tamper_driver_sha="atlas_frame")
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="exact SHA-256 object differs",
    ):
        gate.validate_artifacts(elf_file, binary_file)


def test_bin_bound_to_different_elf_fails(tmp_path: Path) -> None:
    original = _fixture_elf()
    wrong = _fixture_elf(trailer=b"different-exact-elf")
    elf_file, binary_file = _write_pair(
        tmp_path, wrong, binary=_fixture_bin(original)
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="does not bind the selected exact ELF",
    ):
        gate.validate_artifacts(elf_file, binary_file)


def test_duplicate_display_call_fails_closed(tmp_path: Path) -> None:
    elf_file, binary_file = _write_pair(
        tmp_path, _fixture_elf(display_call_count=2)
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="exactly one direct call.*found 2",
    ):
        gate.validate_artifacts(elf_file, binary_file)


@pytest.mark.parametrize("validator_call_count", [0, 2])
def test_missing_or_duplicate_fixture_validator_call_fails_closed(
    tmp_path: Path, validator_call_count: int
) -> None:
    elf_file, binary_file = _write_pair(
        tmp_path, _fixture_elf(validator_call_count=validator_call_count)
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match=(
            "exactly one direct call to the dither-atlas fixture validator; "
            f"found {validator_call_count}"
        ),
    ):
        gate.validate_artifacts(elf_file, binary_file)


def test_raw_endpoint_and_other_fixture_main_fail_closed(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    elf_file, binary_file = _write_pair(
        raw_dir, _fixture_elf(forbidden_runtime_string="/api/frame")
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="forbidden fixture identity or mutation endpoint '/api/frame'",
    ):
        gate.validate_artifacts(elf_file, binary_file)

    other_dir = tmp_path / "other-main"
    other_dir.mkdir()
    elf_file, binary_file = _write_pair(
        other_dir,
        _fixture_elf(extra_fixture_main="ec5_other_fixture_main.cpp"),
    )
    with pytest.raises(
        gate.DitherColorAtlasCompiledIdentityError,
        match="fixture-main source identity differs",
    ):
        gate.validate_artifacts(elf_file, binary_file)


def test_cli_validate_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    elf_file, binary_file = _write_pair(tmp_path, _fixture_elf())
    args = gate.parse_args(
        [
            "validate-artifacts",
            "--elf",
            str(elf_file),
            "--binary",
            str(binary_file),
        ]
    )
    assert args.command == "validate-artifacts"
    assert args.elf == elf_file
    assert args.binary == binary_file
    assert gate.main(
        [
            "validate-artifacts",
            "--elf",
            str(elf_file),
            "--binary",
            str(binary_file),
        ]
    ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == (
        "mf1750-ec5-dither-color-atlas-compiled-identity-validation"
    )
    assert report["firmware"]["binary_elf_link"]["exact_match"] is True


def test_current_real_artifacts_pass_when_present() -> None:
    elf_file = REAL_BUILD / "firmware.elf"
    binary_file = REAL_BUILD / "firmware.bin"
    if not elf_file.is_file() or not binary_file.is_file():
        pytest.skip("current dither color-atlas build artifacts are absent")
    report = gate.validate_artifacts(elf_file, binary_file)
    assert report["main"]["action_count"] == 2
    assert report["driver"]["role_count"] == 2
    assert report["executable"]["display_direct_call_count"] == 1
    assert report["executable"]["fixture_validator_direct_call_count"] == 1
    assert report["firmware"]["binary_elf_link"]["exact_match"] is True
