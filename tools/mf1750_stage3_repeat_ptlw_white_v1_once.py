#!/usr/bin/env python3
"""Fresh factory-OTP white one-shot after repeat-PTLW A/B/C.

This facade binds a new firmware, NVS namespace, descriptor, action, and
claim surface to the validated Stage-III factory-OTP white protocol.  It never
flashes, resets, controls a relay, retries, recovers, or chains another action.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_ec5_runtime_lut_physical_once as physical  # noqa: E402
from tools import mf1750_stage3_wf23_white_once as base  # noqa: E402


FIRMWARE_BIN = Path(
    ".pio/build-stage3-repeat-ptlw-white-v1/"
    "ec5_stage3_repeat_ptlw_white_v1/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-stage3-repeat-ptlw-white-v1/"
    "ec5_stage3_repeat_ptlw_white_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 785920
FIRMWARE_ELF_BYTES = 13213772
FIRMWARE_BIN_SHA256 = "3cc4e5f67141fd71905ccc4daf8a67c493a750989d184511a5a4d26c68d60b69"
FIRMWARE_ELF_SHA256 = "18f352dbf78298b3517da69c1d501d0ed3939ee1d97a2f6d121ac5f07578a3bc"
BUILD_TAG = "MF1750_EC5_STAGE3_REPEAT_PTLW_WHITE_V1_2026-08-23"
CAMPAIGN_ID = "EC5_STAGE3_REPEAT_PTLW_WHITE_20260823_V1"
ENVIRONMENT = "ec5_stage3_repeat_ptlw_white_v1"
NVS_NAMESPACE = "s3w23_0823rp1"
CONTRACT_ID = "96eab0a5cabc453c95c911bcd2b89473ee2a8cd87138bf6fa45db9a1d777dc2e"
DESCRIPTOR_ID = "d13d862b03933e298ed47bb29c78dcad2ff21699cc54b93478adad64ce706616"
ACTION_ID = "8b9078b4f95573ef559516da0662db84427ea7d629b946c659a470c7734d1a1c"
DESCRIPTOR_MARKER = (
    f"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|SHA256={DESCRIPTOR_ID}"
)

_OVERRIDES: dict[str, object] = {
    "FIRMWARE_BIN": FIRMWARE_BIN,
    "FIRMWARE_ELF": FIRMWARE_ELF,
    "FIRMWARE_BIN_SHA256": FIRMWARE_BIN_SHA256,
    "FIRMWARE_ELF_SHA256": FIRMWARE_ELF_SHA256,
    "BUILD_TAG": BUILD_TAG,
    "CAMPAIGN_ID": CAMPAIGN_ID,
    "ENVIRONMENT": ENVIRONMENT,
    "NVS_NAMESPACE": NVS_NAMESPACE,
    "CONTRACT_ID": CONTRACT_ID,
    "DESCRIPTOR_ID": DESCRIPTOR_ID,
    "ACTION_ID": ACTION_ID,
    "DESCRIPTOR_MARKER": DESCRIPTOR_MARKER,
}


class RepeatPtlwWhiteError(ValueError):
    """The isolated repeat-PTLW recovery binding differs."""


@contextmanager
def _binding_override() -> Iterator[None]:
    original = {name: getattr(base, name) for name in _OVERRIDES}
    try:
        for name, value in _OVERRIDES.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(base, name, value)


def describe() -> dict[str, Any]:
    """Describe the fresh binding without making any network request."""

    with _binding_override():
        report = base.describe()
    report.update(
        {
            "kind": "mf1750-stage3-repeat-ptlw-white-v1-facade",
            "firmware_binary_bytes": FIRMWARE_BIN_BYTES,
            "firmware_elf_bytes": FIRMWARE_ELF_BYTES,
            "fresh_nvs_namespace": True,
            "single_visible_refresh_if_run": True,
            "supersedes_consumed_action": False,
            "recovery_anchor": "after_repeat_ptlw_abc",
        }
    )
    return report


def _diagnose(args: argparse.Namespace) -> dict[str, Any]:
    with _binding_override():
        return base._diagnose(args)  # noqa: SLF001


def _run(args: argparse.Namespace) -> dict[str, Any]:
    with _binding_override():
        return base._run(args)  # noqa: SLF001


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("--temperature-c", required=True)
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--timeout-s", type=float, default=6.0)
    diagnose.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--temperature-c", required=True)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--timeout-s", type=float, default=10.0)
    run.add_argument("--claim-registry", type=Path, required=True)
    run.add_argument("--poll-count", type=int, default=10)
    run.add_argument("--poll-interval-seconds", type=float, default=5.0)
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            report = describe()
        elif args.command == "diagnose":
            if args.output.exists():
                raise RepeatPtlwWhiteError("diagnostic output already exists")
            report = _diagnose(args)
            base._write_report(  # noqa: SLF001
                args.output, report, "repeat-PTLW white diagnostic"
            )
        else:
            if args.output.exists():
                raise RepeatPtlwWhiteError("result output already exists")
            report = _run(args)
            base._write_report(  # noqa: SLF001
                args.output, report, "repeat-PTLW white result"
            )
    except (
        RepeatPtlwWhiteError,
        base.Stage3WhiteError,
        physical.PhysicalOnceError,
    ) as error:
        print(f"repeat-PTLW white error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
