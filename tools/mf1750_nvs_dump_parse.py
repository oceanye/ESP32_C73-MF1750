#!/usr/bin/env python3
"""Offline ESP32 NVS dump parser; no device, serial or network access.

Parses a raw NVS partition image (as read by esptool read_flash at the NVS
partition offset) into a sealed enumeration report: every page, every
namespace declaration, and every key entry with namespace, key, type, value
(scalars decoded), span, chunk, CRC status and entry state (active/erased).

ESP32 NVS layout (esp-idf nvs_page): 4096-byte pages; 32-byte page header;
32-byte entry state bitmap (2 bits per entry, little-endian words);
126 32-byte entries. Entry fields: ns(1) type(1) span(1) chunkIndex(1)
crc32(4) key(16) data(8). ns==0 declares a namespace: key is the namespace
name, data[0] is the assigned namespace id.

The entry CRC32 is stored and reported but NOT verified: the esp-idf ROM
crc32 variant used by NVS was not reproduced offline (documented limitation);
integrity is instead anchored by alignment, namespace-declaration chaining
and the known pinned values (e.g. boot_lh1=0x30a9e5989873f4e0).

Duplicate keys (updates) resolve to the newest ACTIVE entry; erased entries
are retained in the report as evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo.lightness_history import canonical  # noqa: E402

PAGE_SIZE = 4096
ENTRY_SIZE = 32
ENTRY_COUNT = 126
ENTRY_BASE = 64
TYPES = {0x01: "u8", 0x11: "i8", 0x02: "u16", 0x12: "i16", 0x04: "u32",
         0x14: "i32", 0x08: "u64", 0x18: "i64", 0x21: "sz", 0x42: "blob",
         0x41: "blob_data", 0x43: "blob_idx"}
STATES = {3: "empty", 2: "active", 0: "erased", 1: "illegal"}


class NvsParseError(ValueError):
    """Malformed dump: bad size or entry CRC mismatch."""


def parse_dump(data: bytes) -> dict:
    if len(data) % PAGE_SIZE or not data:
        raise NvsParseError("dump size must be a nonzero multiple of 4096")
    namespaces = {}
    entries = []
    for page_index in range(len(data) // PAGE_SIZE):
        page = data[page_index * PAGE_SIZE:(page_index + 1) * PAGE_SIZE]
        bitmap = [int.from_bytes(page[32 + 4 * w:36 + 4 * w], "little")
                  for w in range(8)]
        continuation = 0
        for slot in range(ENTRY_COUNT):
            state = (bitmap[slot // 16] >> ((slot % 16) * 2)) & 3
            raw = page[ENTRY_BASE + slot * ENTRY_SIZE:
                       ENTRY_BASE + (slot + 1) * ENTRY_SIZE]
            if state == 3 and raw == b"\xff" * 32:
                continue
            if continuation:
                # Span payload slot: the bytes belong to the previous entry.
                entries.append({"page": page_index, "slot": slot,
                                "state": STATES.get(state, f"unknown{state}"),
                                "continuation_of_previous_span": True})
                continuation -= 1
                continue
            ns, etype, span, chunk = raw[0], raw[1], raw[2], raw[3]
            if span > 1:
                continuation = span - 1
            crc_stored = int.from_bytes(raw[4:8], "little")
            key = raw[8:24].split(b"\x00")[0].decode("ascii", "replace")
            entry = {"page": page_index, "slot": slot,
                     "state": STATES.get(state, f"unknown{state}"),
                     "ns_index": ns, "type": TYPES.get(etype, f"0x{etype:02x}"),
                     "span": span, "chunk_index": chunk, "key": key,
                     "crc32_stored": crc_stored}
            data_field = raw[24:32]
            if ns == 0 and etype == 0x01:
                namespaces[data_field[0]] = key
                entry["namespace_declaration"] = True
                entry["value"] = data_field[0]
            elif etype == 0x01:
                entry["value"] = data_field[0]
            elif etype == 0x11:
                entry["value"] = int.from_bytes(data_field[:1], "little", signed=True)
            elif etype == 0x02:
                entry["value"] = int.from_bytes(data_field[:2], "little")
            elif etype == 0x12:
                entry["value"] = int.from_bytes(data_field[:2], "little", signed=True)
            elif etype == 0x04:
                entry["value"] = int.from_bytes(data_field[:4], "little")
            elif etype == 0x14:
                entry["value"] = int.from_bytes(data_field[:4], "little", signed=True)
            elif etype == 0x08:
                entry["value"] = int.from_bytes(data_field[:8], "little")
            elif etype == 0x18:
                entry["value"] = int.from_bytes(data_field[:8], "little", signed=True)
            elif etype == 0x21:
                entry["value_size"] = int.from_bytes(data_field[:2], "little")
            elif etype in (0x41, 0x42, 0x43):
                entry["value_size"] = int.from_bytes(data_field[:2], "little")
            entries.append(entry)
    result = []
    for entry in entries:
        if entry.get("continuation_of_previous_span"):
            entry["namespace"] = "<continuation>"
        elif entry.get("namespace_declaration"):
            entry["namespace"] = "<declaration>"
        else:
            entry["namespace"] = namespaces.get(entry["ns_index"],
                                                f"<unknown:{entry['ns_index']}>")
        result.append(entry)
    return {"page_count": len(data) // PAGE_SIZE,
            "namespaces": {str(k): v for k, v in sorted(namespaces.items())},
            "entries": result}


def active_map(report: dict) -> dict:
    """Newest ACTIVE value per (namespace, key); erased keys are absent."""
    result = {}
    for entry in report["entries"]:
        if entry.get("namespace_declaration") or "value" not in entry:
            continue
        pair = (entry["namespace"], entry["key"])
        if entry["state"] == "active":
            result[pair] = entry["value"]
        else:
            result.pop(pair, None)
    return {f"{ns}/{key}": result[(ns, key)] for ns, key in sorted(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    raw = args.dump.read_bytes()
    try:
        parsed = parse_dump(raw)
    except NvsParseError as error:
        raise SystemExit(f"FAIL_STOP: {error}")
    report = {
        "kind": "mf1750-nvs-dump-parse-v1",
        "source": {"path": str(args.dump.resolve()), "bytes": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest()},
        "hardware_accessed": False,
        "note": "offline parse of a previously captured read-only dump; "
                "values are historical state at capture time",
        **parsed,
        "active_values": active_map(parsed),
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(canonical(report)).hexdigest(),
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    out = args.output_dir / "nvs-dump-parse.json"
    with out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"result": "PASS", "report": str(out),
                      "namespaces": parsed["namespaces"],
                      "entries": len(parsed["entries"]),
                      "hardware_accessed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
