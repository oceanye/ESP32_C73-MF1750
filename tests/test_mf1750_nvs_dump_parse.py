"""NVS dump parser tests: synthetic image roundtrip + pinned real-dump values."""
from __future__ import annotations

import json
from pathlib import Path
import zlib

import pytest

from tools import mf1750_nvs_dump_parse as nvs

DUMP = Path(".test-output/hardware/PAL1_CAL_20260924_V1/nvs-dump.bin")
REPORT = Path(".test-output/offline/NVS_DUMP_PARSE_20260924_V1/nvs-dump-parse.json")


def _entry(ns, etype, key, data, span=1):
    raw = bytes([ns, etype, span, 0xFF]) + b"\0\0\0\0" \
        + key.encode().ljust(16, b"\x00")[:16] + data.ljust(8, b"\xff")[:8]
    return raw


def _page(entries, states):
    bitmap = bytearray(32)
    for slot, state in states.items():
        word = slot // 16
        shift = (slot % 16) * 2
        value = int.from_bytes(bitmap[4 * word:4 * word + 4], "little")
        value &= ~(3 << shift)
        value |= state << shift
        bitmap[4 * word:4 * word + 4] = value.to_bytes(4, "little")
    body = b"".join(entries).ljust(126 * 32, b"\xff")
    return b"\xff" * 32 + bytes(bitmap) + body


def synthetic_dump():
    # namespace decl (id 9), u16 written twice (old erased), u64, 2-span string
    page = _page(
        [_entry(0, 0x01, "testns", bytes([9])),
         _entry(9, 0x02, "cursor", (255).to_bytes(2, "little")),
         _entry(9, 0x08, "boot", 0x1122334455667788 .to_bytes(8, "little")),
         _entry(9, 0x21, "text", (40).to_bytes(2, "little"), span=2),
         b"payload".ljust(32, b"\xff"),
         _entry(9, 0x02, "cursor", (770).to_bytes(2, "little"))],
        {0: 2, 1: 0, 2: 2, 3: 2, 4: 2, 5: 2})
    return page + b"\xff" * 4096


def test_parse_synthetic_dump():
    report = nvs.parse_dump(synthetic_dump())
    assert report["page_count"] == 2
    assert report["namespaces"] == {"9": "testns"}
    active = nvs.active_map(report)
    assert active == {"testns/cursor": 770, "testns/boot": 0x1122334455667788}
    states = [e.get("state") for e in report["entries"]]
    assert states[1] == "erased" and states[5] == "active"
    assert any(e.get("continuation_of_previous_span") for e in report["entries"])
    with pytest.raises(nvs.NvsParseError):
        nvs.parse_dump(b"\xff" * 100)


def test_real_dump_pinned_values():
    report = nvs.parse_dump(DUMP.read_bytes())
    active = nvs.active_map(report)
    # Firmware gate pins (the V2 seven-segment gate's ground truth).
    assert active["lhist_v1/cur_lh1"] == 770
    assert active["lhist_v1/boot_lh1"] == 0x30A9E5989873F4E0
    assert active["lh1reb_v2/cur_lh1r"] == 4
    assert active["lh1reb_v2/boot_lh1r"] == 0x7274E005C8833CA1
    assert active["lh2map_v1/cur_lh2m"] == 4
    assert active["lh2map_v1/boot_lh2m"] == 0xAC92BB9E25C374EF
    assert active["lh2srcw_v1/used_lh2sw1"] == 2
    assert active["lh3srcw_v1/used_lh3sw1"] == 2
    assert active["lh3dose_v1/cur_lh3d"] == 769
    assert active["lh3dose_v2/cur_lh3d2"] == 4
    assert active["lh3dose_v2/boot_lh3d2"] == 0x4D53DE6FE4B39D3B
    # The PAL1 defect-death namespaces: boot key written, cursor NEVER written
    # (first cursor write happens at ARM; both died before any ARM).
    assert "pal1_v1/boot_pal1" in active and "pal1_v1/cur_pal1" not in active
    assert "pal1_v2/boot_pal2" in active and "pal1_v2/cur_pal2" not in active


def test_sealed_report_on_disk():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    body = {k: v for k, v in report.items() if k != "integrity"}
    payload = nvs.canonical(body)
    assert report["integrity"]["sha256"] == __import__("hashlib").sha256(payload).hexdigest()
    assert report["source"]["sha256"] == __import__("hashlib").sha256(DUMP.read_bytes()).hexdigest()
    assert report["hardware_accessed"] is False
    assert report["active_values"]["lh3dose_v2/cur_lh3d2"] == 4
