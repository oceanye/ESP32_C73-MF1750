#!/usr/bin/env python3
"""Fail-closed host for fresh T4 matched-swap successor V3."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_once as mechanics,
)


class T4MatchedSwapSuccessorV3RunnerError(RuntimeError):
    """Raised before stale or mismatched V3 I/O could occur."""


def _output_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V3"
    )


def _claim_root() -> Path:
    return (
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_claims"
    )


def _source_route_leaked(serialized: str) -> bool:
    predecessors = (
        "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v2",
        "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1",
        "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v2",
    )
    return pack.CONFIG.base_route not in serialized or any(
        route in serialized for route in predecessors
    )


def _bind_wire_action(host: Any) -> None:
    report_action = pack.build_report()["actions"][0]
    wire_actions = deepcopy(host.base.runner.ACTIONS)
    if len(wire_actions) != 1:
        raise T4MatchedSwapSuccessorV3RunnerError("T4 V3 wire action count differs")
    wire_actions[0]["round"] = report_action["round"]
    wire_actions[0]["prior_static_action_id"] = report_action[
        "prior_static_action_id"
    ]
    wire_actions[0]["boot_admission"] = deepcopy(report_action["boot_admission"])
    host.base.runner.ACTIONS = tuple(wire_actions)
    host.base.runner.DESCRIPTOR_IDS = tuple(
        item["descriptor_id"] for item in wire_actions
    )
    host.base.runner.ACTION_IDS = tuple(item["action_id"] for item in wire_actions)


def _install_v3_mechanics() -> None:
    mechanics.pack = pack
    mechanics._output_root = _output_root  # noqa: SLF001
    mechanics._claim_root = _claim_root  # noqa: SLF001
    mechanics.source_route_leaked = _source_route_leaked
    mechanics._bind_wire_action = _bind_wire_action  # noqa: SLF001


def configure() -> Any:
    """Return an isolated V3 host without hardware or network access."""

    _install_v3_mechanics()
    host = mechanics.configure()
    expected = pack.build_report()["actions"][0]
    observed = list(host.base.runner.ACTIONS)
    if len(observed) != 1 or observed[0].get("boot_admission") != expected.get(
        "boot_admission"
    ):
        raise T4MatchedSwapSuccessorV3RunnerError(
            "T4 V3 explicit-null boot admission differs"
        )
    if observed[0]["action_id"] in pack.non_reusable_action_ids():
        raise T4MatchedSwapSuccessorV3RunnerError(
            "predecessor action became executable"
        )
    if len(pack.non_reusable_action_ids()) != 15:
        raise T4MatchedSwapSuccessorV3RunnerError(
            "T4 V3 registry must contain 15 tombstones"
        )
    return host


def dry_validate(
    *, verify_authorities: bool = True, verify_artifacts: bool = True
) -> dict[str, Any]:
    _install_v3_mechanics()
    value = pack.dry_validate(verify_authorities=verify_authorities)
    if verify_artifacts:
        mechanics._verify_artifacts()  # noqa: SLF001
    host = configure()
    report = pack.build_report()
    return {
        **value,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-runner-validation-v3"
        ),
        "artifact_verification_required": verify_artifacts,
        "artifacts_verified": verify_artifacts,
        "default_evidence_root": str(host.DEFAULT_OUTPUT),
        "claim_root": str(host.DEFAULT_CLAIMS),
        "campaign_id": report["contract"]["campaign_id"],
        "v1_diagnostic_failure_authority": deepcopy(
            pack.v1_diagnostic_failure_binding()
        ),
        "v2_diagnostic_failure_authority": deepcopy(
            pack.v2_diagnostic_failure_binding()
        ),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "explicit_base_url_required_for_live_cli": True,
        "default_base_url": None,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    diag.add_argument("--timeout", type=float, default=10.0)
    action = sub.add_parser("run", allow_abbrev=False)
    action.add_argument("--base-url", required=True)
    action.add_argument("--confirm-j2-on", action="store_true", required=True)
    action.add_argument(
        "--confirm-external-pre-white", action="store_true", required=True
    )
    action.add_argument("--poll-seconds", type=float, default=65.0)
    action.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            result = pack.build_report()
        elif args.command == "prebuild-validate":
            result = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            result = dry_validate()
        elif args.command == "diagnose-j2-off":
            host = configure()
            result = host.diagnose_j2_off(
                args.base_url,
                output=host.DIAGNOSTIC_OUTPUT,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            host = configure()
            result = host.run_once(
                args.base_url,
                1,
                claims=host.DEFAULT_CLAIMS,
                output=host.ACTION_OUTPUTS[1],
                confirm_j2_on=args.confirm_j2_on,
                confirm_external_pre_white=args.confirm_external_pre_white,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
            )
    except (ValueError, RuntimeError) as error:
        print(f"RAW-P16 T4 matched-swap successor V3 error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
