#!/usr/bin/env python3
"""One-action fail-closed runner for cross-palette active-to-commented V1."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.mf1750_runtime_lut_cross_palette_v1_runner import configure  # noqa: E402


base = configure("ab")


def main(argv: Sequence[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
