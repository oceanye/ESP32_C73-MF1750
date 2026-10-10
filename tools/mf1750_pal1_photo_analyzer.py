#!/usr/bin/env python3
"""PAL1 measured-palette photo extractor: PAL1 variant of the dose pipeline.

Thin wrapper over tools/mf1750_lh3_dose_photo_analyzer.py: the full 10-frame
128-ROI pipeline (column-pinned recipes, code-7 white-column tolerance,
per-frame homographies, blackhat dark-session detector) is reused verbatim;
only the recipe pattern, stage map, record kinds and report labels differ.
The PAL1 frame is the single active-header action (column = code 0..7), bound
through the sealed PAL1 package contract and the PAL1 live result record.

No device, network, relay or camera access.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import mf1750_lh3_dose_photo_analyzer as dose  # noqa: E402

ANALYZER_VERSION = "mf1750-pal1-photo-analyzer-v1"


def configure() -> None:
    dose.RECIPE = re.compile(r"PAL1-C([0-7])-R([0-7])")
    dose.STAGE_ORDINAL = {"PAL1": 1}
    dose.RESULT_KIND = "mf1750-pal1-result-v1"
    dose.EXTRACTION_KIND = "mf1750-pal1-extraction-v1"
    dose.STAGE_CONTRACT_KEY = "pal1_stage_contract"
    dose.COMPARISON_PREFIX = "PAL1_C"
    dose.ANALYZER_VERSION = ANALYZER_VERSION


# Re-exported for tests and callers (bound after configure()).
def recipe_cell(recipe_id: str) -> tuple[int, int]:
    configure()
    return dose.recipe_cell(recipe_id)


def validate_blank(entries):
    configure()
    return dose.validate_blank(entries)


def stage_identity(blank, contract, stage, live_result):
    configure()
    return dose.stage_identity(blank, contract, stage, live_result)


def main() -> None:
    configure()
    dose.main()


if __name__ == "__main__":
    main()
