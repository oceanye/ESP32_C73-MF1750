#!/usr/bin/env python3
"""Record-level structural diff across the four panel-proven waveform tables.

Compares L535 active vs L535 commented (535-byte transmitted tables) and the
WF20 / WF23 empirical-H3 tables (first 535 bytes of their 799-byte R20
containers so all four share the L535 geometry: 7-byte header + 6 groups of
8 x 11-byte records).  Outputs identities and structural statistics only:
header byte diffs, per-record equality maps, change clusters, per-position
entropy and exact repeats.  Record field semantics stay OPAQUE - this tool
never assigns meaning to record bytes and never materializes a waveform.

Outputs (O_EXCL) into .test-output/offline/WAVEFORM_STRUCT_DIFF_20261009_V1/.
No device, network, relay or camera access.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.runtime_waveform import l535_table_builder as builder  # noqa: E402

OUT_DIR = ROOT / ".test-output/offline/WAVEFORM_STRUCT_DIFF_20261009_V1"
RECORD_GROUPS = builder.RECORD_GROUPS
RECORDS_PER_GROUP = builder.RECORDS_PER_GROUP
RECORD_BYTES = builder.RECORD_BYTES
HEADER_BYTES = builder.HEADER_BYTES
TABLE_BYTES = builder.TABLE_BYTES

WF20_INC = ROOT / "src/generated/spd1657_wf20_25_empirical_h3.inc"
WF23_INC = ROOT / "src/generated/spd1657_wf23_25_empirical_h3.inc"


def _extract_inc_array(text: str, name: str) -> list[int]:
    match = re.search(re.escape(name) + r"\[\d+\]\s*=\s*\{(.*?)\};", text, re.S)
    if match is None:
        raise SystemExit(f"missing {name}")
    return [int(v.strip(), 16) for v in match.group(1).split(",") if v.strip()]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _records(table: bytes) -> list[bytes]:
    region = table[HEADER_BYTES:]
    return [region[i * RECORD_BYTES:(i + 1) * RECORD_BYTES]
            for i in range(RECORD_GROUPS * RECORDS_PER_GROUP)]


def _load_tables() -> dict[str, bytes]:
    tables = {}
    tables["l535_active"] = builder.from_reference("active").to_bytes()
    tables["l535_commented"] = builder.from_reference("commented").to_bytes()
    for label, inc in (("wf20_h3", WF20_INC), ("wf23_h3", WF23_INC)):
        text = inc.read_text(encoding="utf-8")
        r20 = bytes(_extract_inc_array(text, "kR20Payload"))
        tables[label] = r20[:TABLE_BYTES]
        builder.validate_table_bytes(tables[label])
    return tables


def _header_diff(tables: dict[str, bytes]) -> list[dict]:
    names = list(tables)
    rows = []
    for index in range(HEADER_BYTES):
        values = {name: tables[name][index] for name in names}
        rows.append({
            "index": index,
            "values_hex": {name: f"0x{value:02X}" for name, value in values.items()},
            "all_equal": len(set(values.values())) == 1,
            "knob": builder.knobs_from_header_bytes(tables["l535_active"][:HEADER_BYTES]) and
                    list(builder.knobs_from_header_bytes(tables["l535_active"][:HEADER_BYTES]).keys())[index - 1]
                    if index > 0 else "fixed_zero",
        })
    return rows


def _record_matrix(tables: dict[str, bytes]) -> list[dict]:
    names = list(tables)
    per_table_records = {name: _records(table) for name, table in tables.items()}
    rows = []
    for position in range(RECORD_GROUPS * RECORDS_PER_GROUP):
        group, record = divmod(position, RECORDS_PER_GROUP)
        values = {name: recs[position] for name, recs in per_table_records.items()}
        distinct = len(set(values.values()))
        rows.append({
            "group": group,
            "record": record,
            "distinct_tables": distinct,
            "equal_to_active": {
                name: bool(values[name] == values["l535_active"])
                for name in names if name != "l535_active"
            },
        })
    return rows


def _clusters(diff_positions: list[int]) -> list[list[int]]:
    if not diff_positions:
        return []
    clusters = [[diff_positions[0]]]
    for pos in diff_positions[1:]:
        if pos == clusters[-1][-1] + 1:
            clusters[-1].append(pos)
        else:
            clusters.append([pos])
    return clusters


def _pairwise(tables: dict[str, bytes]) -> list[dict]:
    names = list(tables)
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = tables[names[i]], tables[names[j]]
            diffs = [k for k in range(TABLE_BYTES) if a[k] != b[k]]
            rows.append({
                "pair": f"{names[i]} vs {names[j]}",
                "differing_bytes": len(diffs),
                "ratio": round(len(diffs) / TABLE_BYTES, 4),
                "header_diffs": [k for k in diffs if k < HEADER_BYTES],
                "record_diff_clusters": _clusters([k for k in diffs if k >= HEADER_BYTES]),
            })
    return rows


def _position_stats(tables: dict[str, bytes]) -> list[dict]:
    names = list(tables)
    stats = []
    for pos in range(HEADER_BYTES, TABLE_BYTES):
        values = [tables[name][pos] for name in names]
        distinct = sorted(set(values))
        counts = {v: values.count(v) for v in distinct}
        entropy = 0.0
        for count in counts.values():
            p = count / len(values)
            entropy -= p * math.log2(p)
        stats.append({
            "offset": pos,
            "group": (pos - HEADER_BYTES) // (RECORDS_PER_GROUP * RECORD_BYTES),
            "record": ((pos - HEADER_BYTES) // RECORD_BYTES) % RECORDS_PER_GROUP,
            "byte_in_record": (pos - HEADER_BYTES) % RECORD_BYTES,
            "distinct": len(distinct),
            "entropy_bits": round(entropy, 3),
        })
    return stats


def _repeats(tables: dict[str, bytes]) -> dict:
    out = {}
    for name, table in tables.items():
        records = _records(table)
        unique = len(set(records))
        counter: dict[bytes, int] = {}
        for record in records:
            counter[record] = counter.get(record, 0) + 1
        out[name] = {
            "record_count": len(records),
            "unique_records": unique,
            "max_record_multiplicity": max(counter.values()),
            "all_ff_records": sum(1 for record in records if record == b"\xff" * RECORD_BYTES),
            "all_zero_records": sum(1 for record in records if record == b"\x00" * RECORD_BYTES),
        }
    return out


def main() -> None:
    if OUT_DIR.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    OUT_DIR.mkdir(parents=True, exist_ok=False)

    tables = _load_tables()
    report = {
        "kind": "mf1750-waveform-struct-diff-v1",
        "date": "2026-10-09",
        "geometry": {
            "table_bytes": TABLE_BYTES,
            "header_bytes": HEADER_BYTES,
            "record_groups": RECORD_GROUPS,
            "records_per_group": RECORDS_PER_GROUP,
            "record_bytes": RECORD_BYTES,
            "record_field_semantics": "OPAQUE_BYTES_NO_FIELD_BINDING",
            "wf_tables_note": "WF20/WF23 compared over the first 535 bytes of their 799-byte R20 containers",
        },
        "tables": {name: {"sha256": _sha(table), "header_hex": table[:HEADER_BYTES].hex()}
                   for name, table in tables.items()},
        "header_diff": _header_diff(tables),
        "record_equality_matrix": _record_matrix(tables),
        "pairwise": _pairwise(tables),
        "position_stats": _position_stats(tables),
        "repeats": _repeats(tables),
    }
    (OUT_DIR / "struct-diff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # console digest
    for row in report["pairwise"]:
        print(row["pair"], "diff bytes:", row["differing_bytes"],
              "header:", row["header_diffs"], "clusters:", len(row["record_diff_clusters"]))
    print("repeats:", json.dumps(report["repeats"], ensure_ascii=False))
    print("written", OUT_DIR / "struct-diff.json")


if __name__ == "__main__":
    main()
