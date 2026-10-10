#!/usr/bin/env python3
"""One-action fail-closed runner for the code-1-white L535/PTLW V2 probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_v2_pack as pack  # noqa: E402

_V1_RUNNER_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_runtime_lut_partial_hold_v2_private_base", _V1_RUNNER_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load runner base: {_V1_RUNNER_PATH}")
v1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v1)


REPORT = pack.build_report()

# Rebind the shared, already-audited runner facade to a completely isolated V2
# identity/NVS/action set.  Its validators resolve these module globals at call
# time, so no V1 action or cursor can be accepted by this entry point.
v1.pack = pack
v1._REPORT = REPORT
v1.runner.BUILD_TAG = pack.BUILD_TAG
v1.runner.TEST_ID = pack.TEST_ID
v1.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
v1.runner.DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V2"
v1.runner.IDENTITY_REVISION = "runtime-lut-partial-hold-v2"
v1.runner.CONTRACT_ID = REPORT["contract_id"]
v1.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
v1.runner.NVS_KEY = "cursor_v1"
v1.runner.FIRMWARE_SHA256 = (
    "a64cb04e9cc05eb6af65c7700c1fcf7bb9a769f00018648fc825545422115c9a"
)
v1.runner.FIRMWARE_BYTES = 793328
v1.runner.ACTIONS = v1._actions()
v1.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in v1.runner.ACTIONS
)
v1.runner.ACTION_IDS = tuple(item["action_id"] for item in v1.runner.ACTIONS)
v1.runner.DEFAULT_CLAIMS = (
    v1.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_runtime_lut_partial_hold_l535_active_v2_claims"
)
v1.runner.DEFAULT_OUTPUT = (
    v1.runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_20260823_V2"
)


def main(argv: Sequence[str] | None = None) -> int:
    return v1.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
