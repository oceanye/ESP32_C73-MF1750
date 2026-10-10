#!/usr/bin/env python3
"""ROI inset probe for PAL1 uniformity failures; fully offline.

Re-runs the audited PAL1 extraction pipeline on the same captured frames with
several CENTRAL_FRACTION values (the fraction of each cell's width/height
sampled around its centre). If a cell's uniform_p95_delta_e76 drops
monotonically as the sampling window shrinks while its column-median Lab stays
within noise, the uniformity failure is edge contamination (the ROI ate the
cell boundary's ink-density transition band), not a real intra-cell patch.

Writes a sealed comparison JSON; per-fraction extractions are kept under the
output directory for audit. No device, network, relay or camera access.
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
from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base  # noqa: E402
from tools import mf1750_lh3_dose_photo_analyzer as dose  # noqa: E402
from tools import mf1750_pal1_photo_analyzer as pal1  # noqa: E402

FAILING = [("CS1", 0, 1), ("CS1", 3, 0), ("CS1", 3, 1), ("CS2", 3, 0),
           ("CS2", 3, 1), ("CS2", 0, 3), ("CS1", 5, 6)]
CONTROLS = [("CS1", 1, 3), ("CS2", 2, 4), ("CS1", 7, 3)]  # known-good cells


def run_extraction(fraction, args, out_dir):
    base.CENTRAL_FRACTION = fraction
    pal1.configure()
    argv = [sys.argv[0], "--frames-dir", str(args.frames_dir), "--stage", "PAL1",
            "--package", str(args.package), "--live-result", str(args.live_result),
            "--middle-extraction", str(args.middle_extraction),
            "--anchor-frame", str(args.anchor_frame),
            "--output", str(out_dir / "extraction.json")]
    old_argv = sys.argv
    sys.argv = argv
    try:
        dose.main()
    finally:
        sys.argv = old_argv
    return json.loads((out_dir / "extraction.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--live-result", type=Path, required=True)
    parser.add_argument("--middle-extraction", type=Path, required=True)
    parser.add_argument("--anchor-frame", type=Path, required=True)
    parser.add_argument("--fractions", type=float, nargs="+",
                        default=[0.6, 0.45, 0.3])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    per_fraction = {}
    for fraction in args.fractions:
        sub = args.output_dir / ("fraction-%.2f" % fraction)
        sub.mkdir()
        extraction = run_extraction(fraction, args, sub)
        extraction.pop("integrity", None)
        rows = {(r["controller"], r["grid_col"], r["grid_row"]): r
                for r in extraction["rows"]}
        entry = {"extraction_sha256": hashlib.sha256(
                     (sub / "extraction.json").read_bytes()).hexdigest(),
                 "cells": {}}
        for key in FAILING + CONTROLS:
            row = rows[key]
            entry["cells"]["%s_C%d_R%d" % key] = {
                "uniform_p95_delta_e76": row["max_uniform_p95_delta_e76"],
                "lab_median": row["lab_median"],
                "role": "failing" if key in FAILING else "control",
            }
        per_fraction[("%.2f" % fraction)] = entry
    report = {
        "kind": "mf1750-pal1-roi-inset-probe-v1",
        "fractions": args.fractions,
        "failing_cells": ["%s_C%d_R%d" % k for k in FAILING],
        "control_cells": ["%s_C%d_R%d" % k for k in CONTROLS],
        "per_fraction": per_fraction,
        "hardware_accessed": False,
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(canonical(report)).hexdigest(),
    }
    out = args.output_dir / "inset-probe.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"result": "PASS", "report": str(out),
                      "hardware_accessed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
