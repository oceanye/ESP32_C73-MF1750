#!/usr/bin/env python3
"""One-shot host for fresh endpoint-A/B factory-OTP white containment."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_endpoint_ab_v1_white_containment_pack as pack,
)


_BASE_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_endpoint_ab_white_containment_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load containment host: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

base.pack = pack
base.REPORT = pack.build_report(verify_artifacts=False)
base.ACTION = base.REPORT["action"]
base.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_endpoint_ab_white_containment_v1_claims"
)
base.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_ENDPOINT_AB_WHITE_CONTAINMENT_20260824_V1"
)


def main(argv: Sequence[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
