#!/usr/bin/env python3
"""One-shot CS1/CS2 transport-code map for the exact L535 reference profile.

The tool never flashes firmware or controls the relay.  It exposes one fresh
atlas action only: CS1 uses slot order 0..7 and CS2 uses slot order 7..0.
Colour names are deliberately left to the operator/photo observation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_runtime_lut_contract as contract  # noqa: E402
from tools import mf1750_ec5_runtime_lut_physical_once as physical  # noqa: E402
from tools import mf1750_pure_field_matrix_once as shared  # noqa: E402


BASE_RELEASE = Path(
    ".test-output/offline/MF1750_STAGE3_REFERENCE_535_MATRIX_20260822_V10/"
    "release.json"
)
BASE_CANDIDATE = "L535_ACTIVE_GLOBAL"
PROFILE_ID = (
    "REF_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535__R21FF__MAP_V1"
)
CAMPAIGN_ID = "EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_20260823_V1"
CONTRACT_ID = "e8b0348622884e86bc9d1f629a8055d2b0921018de21469dac398ee50a26ed25"
RELEASE_ID = "03c407dd06609de1b6bb0c2298efa6a7cf160ad3b127f2a916d4460fa46e6a47"
BUILD_TAG = "MF1750_EC5_CONTROLLER_CODE_MAP_L535_ACTIVE_V1_2026-08-23"
TEST_ID = "EC5-CONTROLLER-CODE-MAP-L535-ACTIVE-V1"
ENVIRONMENT = "ec5_controller_code_map_l535_active_v1"
NVS_NAMESPACE = "ccmaplga1"
DESCRIPTOR_ID = "823c6dfc71ea44fbfd4e6ab52706615890cc0cb482b0c8e4baba524cc5fc6837"
ACTION_ID = "de90b4c247266a1efab5330f1541d8bf7327207ad7d148bda97a0c9c9f51612e"
ROLE = "PURE_FIELD_UNIFORM_CODE_ATLAS"
FIRMWARE_BIN = Path(
    ".pio/build-controller-code-map/ec5_controller_code_map_l535_active_v1/"
    "firmware.bin"
)
FIRMWARE_BIN_SHA256 = (
    "c72f7e110c675c11f182e5129ffbe47d7682df7666fd4be8e6626fd9d991a055"
)
FIRMWARE_ELF = Path(
    ".pio/build-controller-code-map/ec5_controller_code_map_l535_active_v1/"
    "firmware.elf"
)
FIRMWARE_ELF_SHA256 = (
    "2e70784b0353a2aa9044232023ab977e5aaa92677185b553f9fe63b9c48036a7"
)
MONITORS = contract.OPERATOR_MONITORING_CONFIRMATION


class ControllerMapError(ValueError):
    """A fixed artifact or one-shot live gate differs."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_artifacts() -> None:
    for path, wanted, label in (
        (FIRMWARE_BIN, FIRMWARE_BIN_SHA256, "controller-map BIN"),
        (FIRMWARE_ELF, FIRMWARE_ELF_SHA256, "controller-map ELF"),
    ):
        if not path.is_file() or path.is_symlink() or _sha(path) != wanted:
            raise ControllerMapError(f"{label} is absent, unsafe, or differs")
    marker = (
        f"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE={PROFILE_ID}|ROLE=RUNTIME|"
        f"SHA256={DESCRIPTOR_ID}"
    ).encode("ascii")
    binary = FIRMWARE_BIN.read_bytes()
    elf = FIRMWARE_ELF.read_bytes()
    if binary.count(marker) != 1 or elf.count(marker) != 1:
        raise ControllerMapError("controller-map descriptor marker differs")
    for token in (
        PROFILE_ID,
        CAMPAIGN_ID,
        CONTRACT_ID,
        BUILD_TAG,
        TEST_ID,
        ENVIRONMENT,
        NVS_NAMESPACE,
        DESCRIPTOR_ID,
        ACTION_ID,
    ):
        if token.encode("ascii") not in elf:
            raise ControllerMapError(f"compiled identity token is absent: {token}")


def _release_and_candidate():
    release, candidates = shared._release(BASE_RELEASE)  # noqa: SLF001
    base = candidates[BASE_CANDIDATE]
    treatment = type(base.treatment)(
        binary=FIRMWARE_BIN,
        elf=FIRMWARE_ELF,
        binary_sha256=FIRMWARE_BIN_SHA256,
        elf_sha256=FIRMWARE_ELF_SHA256,
        build_tag=BUILD_TAG,
        test_id=TEST_ID,
        environment=ENVIRONMENT,
        nvs_namespace=NVS_NAMESPACE,
        descriptor_id=DESCRIPTOR_ID,
        action_id=ACTION_ID,
        role=ROLE,
    )
    candidate = type(base)(
        key="L535_ACTIVE_CONTROLLER_CODE_MAP_V1",
        profile_id=PROFILE_ID,
        global_header=base.global_header,
        campaign_id=CAMPAIGN_ID,
        contract_id=CONTRACT_ID,
        release_id=RELEASE_ID,
        treatment=treatment,
        recovery=base.recovery,
        electrical=base.electrical,
    )
    return release, base, candidate


def _context() -> tuple[Mapping[str, Any], Any, physical.ReleaseContext]:
    _validate_artifacts()
    release, base, candidate = _release_and_candidate()
    inherited = shared.load_context(release, base, BASE_RELEASE)
    root = copy.deepcopy(inherited.root)
    root.update(
        {
            "profile_id": PROFILE_ID,
            "campaign_id": CAMPAIGN_ID,
            "contract_id": CONTRACT_ID,
            "release_id": RELEASE_ID,
        }
    )
    profile = root["profile_contract"]
    profile.update(
        {
            "profile_id": PROFILE_ID,
            "campaign_id": CAMPAIGN_ID,
            "contract_id": CONTRACT_ID,
        }
    )
    action = next(item for item in profile["actions"] if item["ordinal"] == 1)
    action.update(
        {
            "profile_id": PROFILE_ID,
            "campaign_id": CAMPAIGN_ID,
            "environment": ENVIRONMENT,
            "nvs_namespace": NVS_NAMESPACE,
            "hardware_action_id": ACTION_ID,
            "transaction_descriptor_sha256": DESCRIPTOR_ID,
            "role": ROLE,
        }
    )
    binding = next(
        item for item in root["action_artifact_bindings"] if item["ordinal"] == 1
    )
    binding.update(
        {
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "campaign_id": CAMPAIGN_ID,
            "environment": ENVIRONMENT,
            "nvs_namespace": NVS_NAMESPACE,
            "hardware_action_id": ACTION_ID,
            "transaction_descriptor_sha256": DESCRIPTOR_ID,
            "firmware_binary_sha256": FIRMWARE_BIN_SHA256,
            "firmware_elf_sha256": FIRMWARE_ELF_SHA256,
            "role": ROLE,
        }
    )
    return release, candidate, physical.ReleaseContext(root=root, release_file=BASE_RELEASE.resolve())


def describe() -> dict[str, Any]:
    _release, _candidate, context = _context()
    action = context.action(1)
    return {
        "schema_version": 1,
        "kind": "mf1750-controller-specific-code-map-description",
        "build_tag": BUILD_TAG,
        "campaign_id": CAMPAIGN_ID,
        "contract_id": CONTRACT_ID,
        "release_id": RELEASE_ID,
        "profile_id": PROFILE_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "firmware": {"bytes": FIRMWARE_BIN.stat().st_size, "sha256": FIRMWARE_BIN_SHA256},
        "action_id": action["hardware_action_id"],
        "descriptor_id": action["transaction_descriptor_sha256"],
        "visible_actions": 1,
        "layout": {
            "logical_screen": "1024x600",
            "per_controller": "2x4 fields, 128x300 each",
            "cs1_slot_order": [0, 1, 2, 3, 4, 5, 6, 7],
            "cs2_slot_order": [7, 6, 5, 4, 3, 2, 1, 0],
            "field_pixels_per_code_across_both_controllers": 76800,
        },
        "runtime_lut": True,
        "partial_refresh": False,
        "spatial_dithering": False,
        "unknown_commands": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "live_authorized": False,
    }


def _diagnose(args: argparse.Namespace) -> dict[str, Any]:
    release, candidate, context = _context()
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with shared._physical_overrides(candidate, release):  # noqa: SLF001
        return physical.diagnose_j2_off(
            context,
            1,
            operator_temperature_c=args.temperature_c,
            operator_screen_state=physical.SCREEN_INITIAL,
            operator_j2_state="OFF",
            operator_monitoring_state=MONITORS,
            requester=requester,
        )


def _run(args: argparse.Namespace) -> dict[str, Any]:
    release, candidate, context = _context()
    diagnostic = physical._read_json(args.diagnostic, label="code-map J2-OFF diagnostic")  # noqa: SLF001
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with shared._physical_overrides(candidate, release):  # noqa: SLF001
        authorization = physical.required_authorization(
            context, 1, args.temperature_c, diagnostic
        )
        return physical.run_once(
            context,
            1,
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
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("--temperature-c", required=True)
    diagnose.add_argument("--base-url", required=True)
    diagnose.add_argument("--timeout-s", type=float, default=6.0)
    diagnose.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--temperature-c", required=True)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--timeout-s", type=float, default=10.0)
    run.add_argument("--claim-registry", type=Path, required=True)
    run.add_argument("--poll-count", type=int, default=12)
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
                raise ControllerMapError("diagnostic output already exists")
            report = _diagnose(args)
            physical._write_new(args.output, report, label="code-map diagnostic")  # noqa: SLF001
        else:
            if args.output.exists():
                raise ControllerMapError("result output already exists")
            report = _run(args)
            physical._write_new(args.output, report, label="code-map result")  # noqa: SLF001
    except (ControllerMapError, physical.PhysicalOnceError, ValueError) as error:
        print(f"controller-code-map error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
