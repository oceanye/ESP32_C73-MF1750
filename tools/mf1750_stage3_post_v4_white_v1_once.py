#!/usr/bin/env python3
"""Fresh one-shot factory-OTP white containment after the V4 baseline fail.

The facade binds a new firmware, NVS namespace, descriptor, action, and claim
surface to the already tested Stage-III white protocol.  It never flashes,
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
    ".pio/build-stage3-post-v4-white-v1/ec5_stage3_post_v4_white_v1/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-stage3-post-v4-white-v1/ec5_stage3_post_v4_white_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 785904
FIRMWARE_ELF_BYTES = 13213708
FIRMWARE_BIN_SHA256 = "f03c5534c4fcfaeae4a33f935ec3943fabd4f3559d49884fab19a17ae3406b61"
FIRMWARE_ELF_SHA256 = "fafac27e7580852b903f454847a6279a7698d9f285baa60aa2292ec25a180e7f"
BUILD_TAG = "MF1750_EC5_STAGE3_POST_V4_WHITE_V1_2026-08-23"
CAMPAIGN_ID = "EC5_STAGE3_POST_V4_WHITE_20260823_V1"
ENVIRONMENT = "ec5_stage3_post_v4_white_v1"
NVS_NAMESPACE = "s3w23_0823v4"
CONTRACT_ID = "04a59eec67eb740e441bc5bac6d68615012bce3081d5b976161d5331875fc28d"
DESCRIPTOR_ID = "bf698de7b435480dfc97e175ac5f0c79a3e9c205f4ae996858a0a4c24250efd3"
ACTION_ID = "3bbce029b43600456776ff79ffd9e805832ff2f787dbd8a6f16b41cae4f4b10e"
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


class PostV4WhiteError(ValueError):
    """The isolated post-V4 containment binding differs."""


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
            "kind": "mf1750-stage3-post-v4-white-v1-facade",
            "firmware_binary_bytes": FIRMWARE_BIN_BYTES,
            "firmware_elf_bytes": FIRMWARE_ELF_BYTES,
            "fresh_nvs_namespace": True,
            "single_visible_refresh_if_run": True,
            "supersedes_consumed_action": False,
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
                raise PostV4WhiteError("diagnostic output already exists")
            report = _diagnose(args)
            base._write_report(args.output, report, "post-V4 white diagnostic")  # noqa: SLF001
        else:
            if args.output.exists():
                raise PostV4WhiteError("result output already exists")
            report = _run(args)
            base._write_report(args.output, report, "post-V4 white result")  # noqa: SLF001
    except (
        PostV4WhiteError,
        base.Stage3WhiteError,
        physical.PhysicalOnceError,
    ) as error:
        print(f"post-V4 white error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
