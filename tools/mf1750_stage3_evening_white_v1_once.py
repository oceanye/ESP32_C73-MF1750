#!/usr/bin/env python3
"""One-shot factory-OTP white containment for the 2026-08-23 evening tests.

This is a new firmware, NVS namespace, action identity, and claim surface.  It
reuses the already tested Stage-III white host protocol only while an exact
constant override is active.  It performs no flash, relay, serial, retry,
automatic recovery, or automatic chaining operation itself.
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
    ".pio/build-stage3-evening-white-v1/"
    "ec5_stage3_evening_white_v1/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-stage3-evening-white-v1/"
    "ec5_stage3_evening_white_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 785904
FIRMWARE_ELF_BYTES = 13213660
FIRMWARE_BIN_SHA256 = (
    "313940d1256dd02cf07ad08f91348f283dbadd6964ca436b768534422a582e94"
)
FIRMWARE_ELF_SHA256 = (
    "f15ee3d39b96fd719d77479d0459f37533358b192a4f0e7a127440ecabd5b5cf"
)
BUILD_TAG = "MF1750_EC5_STAGE3_EVENING_WHITE_V1_2026-08-23"
CAMPAIGN_ID = "EC5_STAGE3_EVENING_WHITE_20260823_V1"
ENVIRONMENT = "ec5_stage3_evening_white_v1"
NVS_NAMESPACE = "s3w23_0823e1"
CONTRACT_ID = "d5bd5f4c6c369f92d8808d780977533c67daec4baccafe28a43c95c94d2a044e"
DESCRIPTOR_ID = (
    "6d1a1907b9c13d6087cffc8a84395fe0ef3e5a936a0512e220960a28d9142497"
)
ACTION_ID = "0797fc11c46494861a96911da83103e193b41b5c4ea7ecb65149695b5a5f3f0c"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|"
    f"SHA256={DESCRIPTOR_ID}"
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


class EveningWhiteError(ValueError):
    """The isolated evening containment binding differs."""


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
            "kind": "mf1750-stage3-evening-white-v1-facade",
            "firmware_binary_bytes": FIRMWARE_BIN_BYTES,
            "firmware_elf_bytes": FIRMWARE_ELF_BYTES,
            "fresh_nvs_namespace": True,
            "single_visible_refresh_if_run": True,
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
                raise EveningWhiteError("diagnostic output already exists")
            report = _diagnose(args)
            base._write_report(args.output, report, "evening white diagnostic")  # noqa: SLF001
        else:
            if args.output.exists():
                raise EveningWhiteError("result output already exists")
            report = _run(args)
            base._write_report(args.output, report, "evening white result")  # noqa: SLF001
    except (EveningWhiteError, base.Stage3WhiteError, physical.PhysicalOnceError) as error:
        print(f"stage3 evening white error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
