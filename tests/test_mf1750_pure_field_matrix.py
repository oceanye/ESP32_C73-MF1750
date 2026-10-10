from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FRAME_SHA256 = "d2c08f7986ded9dc3bba93970cba7659ff773b36b3564cdfa3325bca4d8e970f"
CS1_SHA256 = "b7239abe691da62db38801bb991d3a118436cdd3f8df8292620aa4f916b5fe25"
CS2_SHA256 = "bc97286c2ade130c8742c5fc174c32a799740f4a9f79446a24eccfd0565251e2"


def _fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _frame() -> bytes:
    packed = bytearray(1024 * 600 // 2)
    for y in range(600):
        row = y // 300
        for x in range(0, 1024, 2):
            controller = x // 512
            slot = row * 4 + (x % 512) // 128
            code = slot if controller == 0 else 7 - slot
            packed[(y * 1024 + x) // 2] = (code << 4) | code
    return bytes(packed)


def _array(source: Path, name: str, size: int) -> bytes:
    text = source.read_text(encoding="utf-8")
    match = re.search(rf"{name}\[{size}\] = \{{(.*?)\n\}};", text, re.DOTALL)
    assert match is not None
    return bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", match.group(1)))


def test_flat_field_frame_is_exact_uniform_code_geometry() -> None:
    frame = _frame()
    assert len(frame) == 307_200
    assert hashlib.sha256(frame).hexdigest() == FRAME_SHA256
    assert _fnv1a(frame) == 0x52FA55C5
    cs1 = b"".join(frame[y * 512 : y * 512 + 256] for y in range(600))
    cs2 = b"".join(frame[y * 512 + 256 : (y + 1) * 512] for y in range(600))
    assert hashlib.sha256(cs1).hexdigest() == CS1_SHA256
    assert hashlib.sha256(cs2).hexdigest() == CS2_SHA256
    assert _fnv1a(cs1) == 0x8935B9C5
    assert _fnv1a(cs2) == 0xD36139C5
    histogram = [0] * 8
    for value in frame:
        histogram[value >> 4] += 1
        histogram[value & 0x0F] += 1
    assert histogram == [76_800] * 8


def test_four_payload_layouts_are_exact_source_slices() -> None:
    sources = [
        ROOT / "src/generated/spd1657_wf20_25_empirical_h3.inc",
        ROOT / "src/generated/spd1657_wf23_25_empirical_h3.inc",
    ]
    payloads = [_array(path, "kR20Payload", 799) for path in sources]
    ff = bytes([0xFF]) * 704
    expected = {
        "M0": (
            "544defe72c8888ea723a4e2abf70576e36915aefd01e117004fde7cefcf03154",
            "ac42b6951ed900e0d44b0990e16965beaf3b0978de134bf94c8eb7054b750e44",
        ),
        "H1": (
            "544defe72c8888ea723a4e2abf70576e36915aefd01e117004fde7cefcf03154",
            "5234e725640f3536b1c1ccc49ba601ab0ff73d872925fa86a9a2ed445a7d8690",
        ),
        "H2": (
            "544defe72c8888ea723a4e2abf70576e36915aefd01e117004fde7cefcf03154",
            "3859ea18267535b8f7e3b26fa31e3936520e6169f2e97b2b1dd468802919cb2f",
        ),
        "H3": (
            "fe3d8750ccf71c42b30f09cd4249b4f1ca5067ee5d4bf704481a2da87151935f",
            "ac42b6951ed900e0d44b0990e16965beaf3b0978de134bf94c8eb7054b750e44",
        ),
    }
    layouts = {
        "M0": ([item[:535] for item in payloads], [ff, ff]),
        "H1": ([item[:535] for item in payloads], [item[95:799] for item in payloads]),
        "H2": (
            [item[:535] for item in payloads],
            [ff[:440] + item[535:799] for item in payloads],
        ),
        "H3": ([item[:799] for item in payloads], [ff, ff]),
    }
    for name, (r20, r21) in layouts.items():
        assert hashlib.sha256(b"".join(r20)).hexdigest() == expected[name][0]
        assert hashlib.sha256(b"".join(r21)).hexdigest() == expected[name][1]


def test_matrix_has_eight_treatments_and_eight_unique_recoveries() -> None:
    ini = (ROOT / "platformio.pure_field_matrix.ini").read_text(encoding="utf-8")
    environments = re.findall(r"^\[env:(ec5_pfm_[^]]+)\]$", ini, re.MULTILINE)
    treatments = [item for item in environments if not item.endswith("_white")]
    recoveries = [item for item in environments if item.endswith("_white")]
    assert len(treatments) == 8
    assert len(recoveries) == 8
    assert len(set(environments)) == 16
    identity = (ROOT / "src/ec5_pure_field_candidate.inc").read_text(encoding="utf-8")
    assert len(set(re.findall(r'#define PF_TREAT_ACTION "([0-9a-f]{64})"', identity))) == 8
    assert len(set(re.findall(r'#define PF_WHITE_ACTION "([0-9a-f]{64})"', identity))) == 8


def test_sources_fail_closed_against_unsafe_search_axes() -> None:
    driver = (ROOT / "src/ec5_dual_r20_h20_driver.inc").read_text(encoding="utf-8")
    main = (ROOT / "src/ec5_dual_r20_h20_main.cpp").read_text(encoding="utf-8")
    ini = (ROOT / "platformio.pure_field_matrix.ini").read_text(encoding="utf-8")
    assert "H3_PATCH_WIDTH = 128" in driver
    assert "H3_PATCH_HEIGHT = 300" in driver
    assert "h3ValidateActualPayloadHashes" in driver
    assert "MF1750_PURE_FIELD_MATRIX=1" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini
    assert r'\"raw_lut_ingress\":false' in main
    assert r'\"timing_parameter_ingress\":false' in main
    assert r'\"vcom_sweep\":false' in main
    assert r'\"automatic_chaining\":false' in main
    assert r'\"retry\":false' in main
