#!/usr/bin/env python3
"""Fresh one-shot white containment for the 2026-08-21 WF23 Stage-III trial.

This facade reuses the validated empirical-H3 physical runner but replaces only
the already-consumed WF23 recovery image/action with a new, source-bound NVS
namespace and action identity.  It exposes no raw frame, LUT, timing, voltage,
profile-switch, retry, recovery-chain, flash, relay, or serial operation.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical


BASE_RELEASE = Path(
    ".test-output/hardware/MF1750_STAGE3_WF23_STANDALONE_20260821/"
    "WF23_25-release.json"
)
BASE_RELEASE_SHA256 = (
    "c06ebabb7096ba848d9635c02609f86f0cc97302ae83cade3b315b6ab6346f3b"
)
FIRMWARE_BIN = Path(
    ".pio/build-stage3-wf23-white-20260821/"
    "ec5_stage3_wf23_white_20260821/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-stage3-wf23-white-20260821/"
    "ec5_stage3_wf23_white_20260821/firmware.elf"
)
FIRMWARE_BIN_SHA256 = (
    "8717cb868a127fbf6645bc7613ab132dfe918a2184dc726e2df63a25dbc0e2e9"
)
FIRMWARE_ELF_SHA256 = (
    "3d73545a037e3deb2815b4b491626039806f89ad34323f79f0995d9d3a2d578f"
)
BUILD_TAG = "MF1750_EC5_STAGE3_WF23_WHITE_V1_2026-08-21"
CAMPAIGN_ID = "EC5_STAGE3_WF23_STANDALONE_20260821"
ENVIRONMENT = "ec5_stage3_wf23_white_20260821"
NVS_NAMESPACE = "s3w23_0821"
CONTRACT_ID = "68175512c06df260d83d60356ed01f6fde00cdaddd7bd6f8d45d0233b83ff457"
DESCRIPTOR_ID = (
    "194e418973e731682d6d4ac8358f0fd02ecb00fc2e4819cba08ca57a3ea0c4a7"
)
ACTION_ID = "b6357c9ee6e7a680b052a6a75586431073a36b0e48ab016131a608080686ccf7"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|"
    f"SHA256={DESCRIPTOR_ID}"
)
MONITORS = contract.OPERATOR_MONITORING_CONFIRMATION
SCREEN_STATE = physical.SCREEN_RECOVERY


class Stage3WhiteError(ValueError):
    """The fixed recovery facade or one of its artifacts differs."""


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path, wanted_sha256: str, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise Stage3WhiteError(f"{label} is absent or unsafe")
    if _sha_file(path) != wanted_sha256:
        raise Stage3WhiteError(f"{label} SHA-256 differs")


def load_context() -> physical.ReleaseContext:
    """Return a base-release-bound context with only ordinal 2 replaced."""

    _require_file(BASE_RELEASE, BASE_RELEASE_SHA256, "base WF23 release")
    _require_file(FIRMWARE_BIN, FIRMWARE_BIN_SHA256, "fresh white BIN")
    _require_file(FIRMWARE_ELF, FIRMWARE_ELF_SHA256, "fresh white ELF")
    base = physical.load_release(BASE_RELEASE)
    root = copy.deepcopy(base.root)
    root["contract_id"] = CONTRACT_ID

    actions = root["profile_contract"]["actions"]
    action = next(item for item in actions if item["ordinal"] == 2)
    action.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "environment": ENVIRONMENT,
            "nvs_namespace": NVS_NAMESPACE,
            "hardware_action_id": ACTION_ID,
            "transaction_descriptor_sha256": DESCRIPTOR_ID,
        }
    )

    bindings = root["action_artifact_bindings"]
    binding = next(item for item in bindings if item["ordinal"] == 2)
    binding.update(
        {
            "build_tag": BUILD_TAG,
            "campaign_id": CAMPAIGN_ID,
            "environment": ENVIRONMENT,
            "nvs_namespace": NVS_NAMESPACE,
            "hardware_action_id": ACTION_ID,
            "transaction_descriptor_sha256": DESCRIPTOR_ID,
            "transaction_descriptor_marker": DESCRIPTOR_MARKER,
            "firmware_binary_sha256": FIRMWARE_BIN_SHA256,
            "firmware_elf_sha256": FIRMWARE_ELF_SHA256,
        }
    )
    return physical.ReleaseContext(root=root, release_file=BASE_RELEASE.resolve())


def describe() -> dict[str, Any]:
    context = load_context()
    return {
        "schema_version": 1,
        "kind": "mf1750-stage3-wf23-fresh-white-facade",
        "base_release_id": context.release_id,
        "profile_id": context.profile_id,
        "ordinal": 2,
        "build_tag": BUILD_TAG,
        "campaign_id": CAMPAIGN_ID,
        "environment": ENVIRONMENT,
        "nvs_namespace": NVS_NAMESPACE,
        "contract_id": CONTRACT_ID,
        "transaction_descriptor_sha256": DESCRIPTOR_ID,
        "hardware_action_id": ACTION_ID,
        "firmware_binary_sha256": FIRMWARE_BIN_SHA256,
        "firmware_elf_sha256": FIRMWARE_ELF_SHA256,
        "requires_prior_runtime_claim": True,
        "raw_ingress": False,
        "retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "profile_switch": False,
        "logic_analyser_required": False,
        "network_requests": 0,
        "visible_refreshes": 0,
    }


@contextmanager
def _descriptor_marker_override():
    """Narrowly expose the fresh descriptor marker to the reused validator."""

    original = contract.compiled_descriptor_marker

    def selected(profile_id: str, role: str) -> str:
        if profile_id == "WF23_25" and role == contract.ROLE_WHITE:
            return DESCRIPTOR_MARKER
        return original(profile_id, role)

    contract.compiled_descriptor_marker = selected
    try:
        yield
    finally:
        contract.compiled_descriptor_marker = original


def _write_report(path: Path, report: Mapping[str, Any], label: str) -> None:
    physical._write_new(path, report, label=label)  # noqa: SLF001


def _diagnose(args: argparse.Namespace) -> dict[str, Any]:
    context = load_context()
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with _descriptor_marker_override():
        return physical.diagnose_j2_off(
            context,
            2,
            operator_temperature_c=args.temperature_c,
            operator_screen_state=SCREEN_STATE,
            operator_j2_state="OFF",
            operator_monitoring_state=MONITORS,
            requester=requester,
        )


def _run(args: argparse.Namespace) -> dict[str, Any]:
    context = load_context()
    diagnostic = physical._read_json(  # noqa: SLF001
        args.diagnostic, label="fresh white J2-OFF diagnostic"
    )
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with _descriptor_marker_override():
        authorization = physical.required_authorization(
            context, 2, args.temperature_c, diagnostic
        )
        return physical.run_once(
            context,
            2,
            operator_temperature_c=args.temperature_c,
            operator_j2_state="ON",
            operator_monitoring_state=MONITORS,
            authorization=authorization,
            diagnostic=diagnostic,
            requester=requester,
            claim_registry=args.claim_registry,
            poll_count=args.poll_count,
            poll_interval_seconds=args.poll_interval_seconds,
        )


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
                raise Stage3WhiteError("diagnostic output already exists")
            report = _diagnose(args)
            _write_report(args.output, report, "fresh white diagnostic")
        else:
            if args.output.exists():
                raise Stage3WhiteError("result output already exists")
            report = _run(args)
            _write_report(args.output, report, "fresh white result")
    except (Stage3WhiteError, physical.PhysicalOnceError) as error:
        print(f"stage3 WF23 white error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
