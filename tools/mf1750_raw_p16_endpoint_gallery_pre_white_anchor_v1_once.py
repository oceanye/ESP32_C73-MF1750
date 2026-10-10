#!/usr/bin/env python3
"""One-shot host for the fresh RAW-P16 pre-gallery factory-OTP white anchor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_raw_p16_pre_white_anchor_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load pre-white anchor host: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

base.pack = pack
base.REPORT = pack.build_report(verify_artifacts=False)
base.ACTION = base.REPORT["action"]
base.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.DEFAULT_CLAIMS = REPO_ROOT / (
    ".test-output/hardware/.mf1750_raw_p16_pre_white_anchor_v1_claims"
)
base.DEFAULT_OUTPUT = REPO_ROOT / (
    ".test-output/hardware/MF1750_RAW_P16_PRE_WHITE_ANCHOR_20260828_V1"
)
_base_describe = base.describe


def describe() -> dict[str, object]:
    value = _base_describe()
    value["purpose"] = pack.PURPOSE
    value["target_campaign_id"] = pack.TARGET_CAMPAIGN_ID
    return value


base.describe = describe


def main(argv: Sequence[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
