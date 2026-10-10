from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_ec5_compiled_identity as gate


REPO_ROOT = Path(__file__).resolve().parents[1]


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _fixture_elf(
    candidate: int,
    *,
    frame_override: bytes | None = None,
    dtm_override: bytes | None = None,
    frame_size: int = 32,
    dtm_size: int = 32,
    trailer: bytes = b"",
) -> bytes:
    expected = gate.generated_identity(candidate)
    frame = frame_override or expected["frame_sha256"]
    dtm = dtm_override or expected["dtm_sha256"]
    assert isinstance(frame, bytes) and isinstance(dtm, bytes)

    section_names = b"\0.shstrtab\0.strtab\0.symtab\0.flash.rodata\0"
    section_name_offsets = {
        name: section_names.index(name.encode())
        for name in (".shstrtab", ".strtab", ".symtab", ".flash.rodata")
    }
    symbol_names = b"\0" + gate.FRAME_SYMBOL.encode() + b"\0" + gate.DTM_SYMBOL.encode() + b"\0"
    frame_name = symbol_names.index(gate.FRAME_SYMBOL.encode())
    dtm_name = symbol_names.index(gate.DTM_SYMBOL.encode())
    rodata = frame + dtm
    rodata_address = 0x3C000000
    local_object = (gate.STB_LOCAL << 4) | gate.STT_OBJECT
    symbols = b"".join(
        (
            gate.SYMBOL_ENTRY.pack(0, 0, 0, 0, 0, 0),
            gate.SYMBOL_ENTRY.pack(
                frame_name, rodata_address, frame_size, local_object, 0, 4
            ),
            gate.SYMBOL_ENTRY.pack(
                dtm_name, rodata_address + len(frame), dtm_size, local_object, 0, 4
            ),
        )
    )

    image = bytearray(b"\0" * gate.ELF_HEADER.size)
    offsets: dict[str, int] = {}
    for name, payload in (
        (".shstrtab", section_names),
        (".strtab", symbol_names),
        (".symtab", symbols),
        (".flash.rodata", rodata),
    ):
        image.extend(b"\0" * (_align(len(image)) - len(image)))
        offsets[name] = len(image)
        image.extend(payload)
    image.extend(b"\0" * (_align(len(image)) - len(image)))
    section_offset = len(image)
    image.extend(gate.SECTION_HEADER.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    image.extend(
        gate.SECTION_HEADER.pack(
            section_name_offsets[".shstrtab"],
            gate.SHT_STRTAB,
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
        gate.SECTION_HEADER.pack(
            section_name_offsets[".strtab"],
            gate.SHT_STRTAB,
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
        gate.SECTION_HEADER.pack(
            section_name_offsets[".symtab"],
            gate.SHT_SYMTAB,
            0,
            0,
            offsets[".symtab"],
            len(symbols),
            2,
            3,
            4,
            gate.SYMBOL_ENTRY.size,
        )
    )
    image.extend(
        gate.SECTION_HEADER.pack(
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
    ident = gate.ELF_MAGIC + bytes((gate.ELFCLASS32, gate.ELFDATA2LSB, 1)) + b"\0" * 9
    header = gate.ELF_HEADER.pack(
        ident,
        2,
        gate.EM_XTENSA,
        1,
        0,
        0,
        section_offset,
        0,
        gate.ELF_HEADER.size,
        0,
        0,
        gate.SECTION_HEADER.size,
        5,
        1,
    )
    image[: gate.ELF_HEADER.size] = header
    image.extend(trailer)
    return bytes(image)


class CompiledIdentityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_pair(self, u04: bytes, u07: bytes) -> tuple[Path, Path]:
        u04_path = self.root / "u04.elf"
        u07_path = self.root / "u07.elf"
        u04_path.write_bytes(u04)
        u07_path.write_bytes(u07)
        return u04_path, u07_path

    def test_independent_generator_has_frozen_stage_a_identities(self) -> None:
        u04 = gate.generated_identity(4)
        u07 = gate.generated_identity(7)
        self.assertEqual(
            u04["frame_sha256"].hex(),
            "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e",
        )
        self.assertEqual(
            u04["dtm_sha256"].hex(),
            "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
        )
        self.assertEqual(u04["frame_fnv1a"], 0x68533DC5)
        self.assertEqual(u04["dtm_fnv1a"], 0x15B7EDC5)
        self.assertEqual(
            u07["frame_sha256"].hex(),
            "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
        )
        self.assertEqual(
            u07["dtm_sha256"].hex(),
            "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        )
        self.assertEqual(u07["frame_fnv1a"], 0xA1C5ADC5)
        self.assertEqual(u07["dtm_fnv1a"], 0x97F125C5)

    def test_exact_runtime_symbols_validate_and_are_candidate_isolated(self) -> None:
        u04, u07 = self._write_pair(_fixture_elf(4), _fixture_elf(7))
        report = gate.validate_pair(u04, u07)
        self.assertTrue(report["valid"])
        self.assertTrue(report["offline"])
        self.assertFalse(report["device_io_performed"])
        for candidate in ("U04", "U07"):
            for symbol in report["variants"][candidate]["symbols"].values():
                self.assertEqual(symbol["size"], 32)
                self.assertEqual(symbol["section"], ".flash.rodata")
        self.assertNotEqual(
            report["variants"]["U04"]["symbols"]["dtm_sha256"]["sha256_bytes"],
            report["variants"]["U07"]["symbols"]["dtm_sha256"]["sha256_bytes"],
        )

    def test_historical_u04_wrong_raw_array_fails_even_if_correct_bytes_exist_elsewhere(self) -> None:
        wrong = bytes.fromhex(
            "a8056cdd450f70709ec75a0a0400dfbfb1f06000ae596420902156bec7bab00d"
        )
        correct = gate.generated_identity(4)["dtm_sha256"]
        assert isinstance(correct, bytes)
        u04, u07 = self._write_pair(
            _fixture_elf(4, dtm_override=wrong, trailer=correct),
            _fixture_elf(7),
        )
        with self.assertRaisesRegex(
            gate.CompiledIdentityError, "U04 dtm_sha256 compiled bytes mismatch"
        ):
            gate.validate_pair(u04, u07)

    def test_symbol_size_must_be_exactly_32(self) -> None:
        u04, u07 = self._write_pair(
            _fixture_elf(4, dtm_size=31),
            _fixture_elf(7),
        )
        with self.assertRaisesRegex(gate.CompiledIdentityError, "size is 31, expected 32"):
            gate.validate_pair(u04, u07)

    def test_swapped_candidate_elfs_fail_closed(self) -> None:
        u04, u07 = self._write_pair(_fixture_elf(4), _fixture_elf(7))
        with self.assertRaisesRegex(
            gate.CompiledIdentityError, "U04 frame_sha256 compiled bytes mismatch"
        ):
            gate.validate_pair(u07, u04)

    def test_cli_validate_is_offline_and_requires_both_elfs(self) -> None:
        u04, u07 = self._write_pair(_fixture_elf(4), _fixture_elf(7))
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools/mf1750_ec5_compiled_identity.py"),
                "validate",
                "--u04-elf",
                str(u04),
                "--u07-elf",
                str(u07),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["valid"])
        self.assertTrue(report["offline"])
        self.assertFalse(report["device_io_performed"])

    def test_current_platformio_elfs_when_present(self) -> None:
        u04 = REPO_ROOT / ".pio/build/esp32-s3-devkitc-1-ec5-u04/firmware.elf"
        u07 = REPO_ROOT / ".pio/build/esp32-s3-devkitc-1-ec5-u07/firmware.elf"
        if not u04.is_file() or not u07.is_file():
            self.skipTest("current Stage-A PlatformIO ELFs are absent")
        report = gate.validate_pair(u04, u07)
        self.assertTrue(report["valid"])


if __name__ == "__main__":
    unittest.main()
