#!/usr/bin/env python3
"""Fresh one-shot factory-OTP white recovery after V4 partial-HOLD tests.

The facade binds an unconsumed firmware, NVS namespace, descriptor, action,
and claim surface to the tested Stage-III white protocol.  It never flashes,
resets, controls the relay, retries, recovers, or chains another action.
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
    ".pio/build-stage3-post-v4-partial-white-v1/"
    "ec5_stage3_post_v4_partial_white_v1/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-stage3-post-v4-partial-white-v1/"
    "ec5_stage3_post_v4_partial_white_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 785936
FIRMWARE_ELF_BYTES = 13213720
FIRMWARE_BIN_SHA256 = "accdf5f6b52132f61beec9cc6bf3c94ccfebc9f53466c9bf6812a269f07ba193"
FIRMWARE_ELF_SHA256 = "5f8c1999a35a39daea634a9274cd6029391ec9f08d821c4733d2f0823b8cdc98"
BUILD_TAG = "MF1750_EC5_STAGE3_POST_V4_PARTIAL_WHITE_V1_2026-08-23"
CAMPAIGN_ID = "EC5_STAGE3_POST_V4_PARTIAL_WHITE_20260823_V1"
ENVIRONMENT = "ec5_stage3_post_v4_partial_white_v1"
NVS_NAMESPACE = "s3w23_0823p4r"
CONTRACT_ID = "6c258af8165d3f45ac15e650d3049c5d96c5076190f3b4831aa048f60b9a67f3"
DESCRIPTOR_ID = "4cbd2dc7001aebd0beeee3f0803841d3dab816452f8f7c9ea236361c3d7b171d"
ACTION_ID = "31d604d31a41f603368605e59ff7e0634798ad3678bf53b1ae3c2dc32a0df1d6"
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


class PostV4PartialWhiteError(ValueError):
    """The isolated post-V4 partial-HOLD recovery binding differs."""


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
    with _binding_override():
        report = base.describe()
    report.update(
        {
            "kind": "mf1750-stage3-post-v4-partial-white-v1-facade",
            "firmware_binary_bytes": FIRMWARE_BIN_BYTES,
            "firmware_elf_bytes": FIRMWARE_ELF_BYTES,
            "fresh_nvs_namespace": True,
            "single_visible_refresh_if_run": True,
            "supersedes_consumed_action": False,
            "recovery_anchor": "after_v4_external_factory_white_anchor_partial_hold",
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
                raise PostV4PartialWhiteError("diagnostic output already exists")
            report = _diagnose(args)
            base._write_report(  # noqa: SLF001
                args.output, report, "post-V4 partial-HOLD white diagnostic"
            )
        else:
            if args.output.exists():
                raise PostV4PartialWhiteError("result output already exists")
            report = _run(args)
            base._write_report(  # noqa: SLF001
                args.output, report, "post-V4 partial-HOLD white result"
            )
    except (
        PostV4PartialWhiteError,
        base.Stage3WhiteError,
        physical.PhysicalOnceError,
    ) as error:
        print(f"post-V4 partial-HOLD white error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
