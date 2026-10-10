#!/usr/bin/env python3
"""One-action fail-closed runner for packed-white L535/PTLW V4."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_v4_pack as pack  # noqa: E402

_BASE_PATH = Path(__file__).with_name("mf1750_runtime_lut_partial_hold_once.py")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_partial_hold_v4_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

REPORT = pack.build_report()
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 55.0
base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V4"
base.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-v4"
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = "cursor_v1"
base.runner.FIRMWARE_SHA256 = (
    "e3315ba1a337e041c156728693c4db92c9463ef195296ebaef351b7c07e5ad9c"
)
base.runner.FIRMWARE_BYTES = 793728
base.runner.ACTIONS = base._actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_partial_hold_l535_active_v4_claims"
)
base.runner.DEFAULT_OUTPUT = (
    base.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_20260823_V4"
)

_BASE_VALIDATE_MANIFEST = base._validate_manifest


def _validate_manifest(value: Mapping[str, Any]) -> None:
    _BASE_VALIDATE_MANIFEST(value)
    layout = value.get("history_layout", {})
    if layout.get("full_white_dtm_transport") != "packed_frame_per_controller":
        raise base.runner.RecheckError("V4 packed full-white transport differs")


base._validate_manifest = _validate_manifest


def main(argv: Sequence[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
