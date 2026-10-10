#!/usr/bin/env python3
"""PlatformIO-compile a synthetic-anchored LH3 dose package; no live I/O.

The real LH3 dose package (tools/mf1750_lh3_dose_pack.py DEFAULT) seals only
after the LH3 source-white field run (its close-review becomes the anchor).
The generated sources of that future package differ from this synthetic one
only in contract/identity constants, so compiling now proves the LH3 dose
firmware builds under PlatformIO and produces a complete package (contract +
manifest + build-report) that offline host-side tooling tests can use as a
fixture. The synthetic anchor is marked everywhere; this package grants no
live readiness.
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

from host.static_photo import lightness_history_lh3_dose as lh3dose  # noqa: E402
from tools import mf1750_lh3_dose_pack as pack  # noqa: E402

DEFAULT_OUT = ROOT / ".test-output/offline/LH3_DOSE_SYNTHETIC_BUILD_20260921_R1"


def _sealed(value: dict) -> dict:
    body = {k: v for k, v in value.items() if k != "integrity"}
    return {**body, "integrity": {"algorithm": "sha256-canonical-json-without-integrity",
                                  "sha256": hashlib.sha256(lh3dose.canonical(body)).hexdigest()}}


def synthesize_white_records(white: Path) -> tuple[dict, str]:
    # Same recipe as tests/test_mf1750_lh3_dose_pack.py::_white_records.
    white.mkdir()
    terminal_report = {"terminal_state": "COMPLETE", "result": True,
                       "campaign_id": "EC5_LH3_SOURCE_WHITE_V1_20260918",
                       "action_id": "a" * 64, "contract_id": "b" * 64}
    close = _sealed({"kind": "synthetic-lh3-white-close-review", "protocol": "PASS",
                     "terminal_report": terminal_report})
    (white / "close-review-v1.json").write_bytes(lh3dose.canonical(close) + b"\n")
    (white / pack.WHITE_RECORD_NAMES["app_flash"]).write_text(
        json.dumps({"binary": {"observed_sha256": "c" * 64}}), encoding="utf-8")
    (white / "live-white-v1").mkdir()
    (white / "live-white-v1" / "result.json").write_bytes(
        lh3dose.canonical(_sealed({"kind": "synthetic-lh3-white-result",
                                   "terminal_report": terminal_report})) + b"\n")
    (white / "postwhite-optical-review-v1.json").write_bytes(
        lh3dose.canonical(_sealed({"kind": "synthetic-lh3-white-optical-review"})) + b"\n")
    records = {k: white / n for k, n in pack.WHITE_RECORD_NAMES.items()}
    anchor = hashlib.sha256((white / "close-review-v1.json").read_bytes()).hexdigest()
    return records, anchor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    records, anchor = synthesize_white_records(out / "synthetic-white")
    base = pack.configured(records, anchor)
    package = out / "package"
    prepared = base.prepare(package)
    if prepared["result"] != "PASS_OFFLINE_PREPARED":
        raise RuntimeError("synthetic package prepare failed")
    built = base.build(package)
    if built["result"] != "PASS":
        raise RuntimeError("synthetic package build failed")
    summary = {
        "result": "PASS",
        "synthetic_source_white": True,
        "live_ready": False,
        "hardware_accessed": False,
        "package": str(package),
        "contract_id": prepared["contract_id"],
        "build_report": pack.module().bind(package / "build-report.json"),
        "artifacts": built["artifacts"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
