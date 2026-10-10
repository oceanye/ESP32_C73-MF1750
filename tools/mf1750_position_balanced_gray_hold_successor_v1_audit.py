#!/usr/bin/env python3
"""Independent offline audit for the G3-specific HOLD package and white successor."""

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

from tools import mf1750_position_balanced_gray_hold_successor_v1_once as runner  # noqa: E402
from tools import mf1750_position_balanced_gray_hold_successor_v1_pack as pack  # noqa: E402
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_once as white_runner,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_pack as white_pack,
)


class AuditError(RuntimeError):
    """Raised when a frozen identity or safety boundary differs."""


EXPECTED_MAIN_CONTRACT = (
    "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229"
)
EXPECTED_MAIN_ACTIONS = (
    "366e5e3f337ec2cbe713f906af0f79a083e531de836e80b9b38066c7951255f5",
    "ba7557595d9780f8ef0354abf0083b43735b5a642411aa63ce08a247f40e253c",
)
EXPECTED_WHITE_CONTRACT = (
    "79ac7bae08b912cdcbf3d959029d56c740407275ef70c91de738b8205dcaa433"
)
EXPECTED_WHITE_ACTION = (
    "934330c22eb1057c7595c5db6711bfcbc7647291e56f5bd8acd059aa6a65e21d"
)


def audit(*, verify_artifacts: bool = True) -> dict[str, Any]:
    main_validation = pack.dry_validate(
        require_live_source=False, verify_artifacts=verify_artifacts
    )
    host_validation = runner.dry_validate(verify_artifacts=verify_artifacts)
    white_validation = white_pack.dry_validate(verify_artifacts=verify_artifacts)
    white_host_validation = white_runner.dry_validate()
    report = pack.build_report()
    white_report = white_pack.build_report(verify_artifacts=verify_artifacts)
    contract = report["contract"]
    transport = contract["clean_ptlw_transport"]
    actions = report["actions"]
    windows = contract["hold_windows"]
    if (
        main_validation.get("result") != "PASS"
        or host_validation.get("result") != "PASS"
        or white_validation.get("result") != "PASS"
        or white_host_validation.get("result") != "PASS"
        or report["contract_id"] != EXPECTED_MAIN_CONTRACT
        or tuple(item["action_id"] for item in actions) != EXPECTED_MAIN_ACTIONS
        or [item["ordinal"] for item in actions] != [1, 2]
        or [item["driver_role"] for item in actions]
        != ["ReverseSource", "ReverseTarget"]
        or windows
        != [
            {"x": 64, "y": 8, "width": 320, "height": 24, "cs1_code": 5, "cs2_code": 5},
            {
                "x": 64,
                "y": 568,
                "width": 320,
                "height": 24,
                "cs1_code": 6,
                "cs2_code": 6,
            },
        ]
        or contract.get("windows_outside_candidate_grid") is not True
        or contract.get("windows_nonoverlapping") is not True
        or contract.get("g3_candidate_cells_retained") != 128
        or contract.get("source_action_replayed") is not False
        or contract.get("g1_g2_g3_embedded_or_replayed") is not False
        or contract.get("g4_accepted") is not False
        or contract.get("g4_presence_is_hard_failure") is not True
        or contract.get("boot_auto_action") is not False
        or contract.get("startup_refresh") is not False
        or transport.get("ptlw_payloads_hex")
        != ["0040017f0008001f01", "0040017f0238024f01"]
        or transport.get("cropped_dtm_bytes_per_controller") != [3840, 3840]
        or transport.get("target_codes") != [5, 6]
        or transport.get("one_inclusive_ptlw_per_controller") is not True
        or transport.get("post_pon_ptlw") is not False
        or transport.get("post_pon_cdi") is not False
        or transport.get("post_pon_btst2") is not False
        or transport.get("command_0x86") is not False
        or any(
            contract.get(key) is not False
            for key in ("autochain", "retry", "fallback", "automatic_recovery")
        )
        or white_report["contract_id"] != EXPECTED_WHITE_CONTRACT
        or white_report["action_id"] != EXPECTED_WHITE_ACTION
        or white_report["contract"]["accepted_source_complete_ordinals_default"] != [2]
        or white_report["contract"]["explicit_h1_stop_ordinal"] != 1
        or white_report["contract"]["h1_requires_explicit_selection"] is not True
        or white_report["contract"]["main_campaign_resume_after_containment"]
        is not False
    ):
        raise AuditError(
            "position-balanced G3 HOLD or white-successor boundary differs"
        )
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-hold-successor-v1-independent-audit",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "source_authority": deepcopy(main_validation["source_authority"]),
        "main_contract_id": report["contract_id"],
        "main_action_ids": list(EXPECTED_MAIN_ACTIONS),
        "white_contract_id": white_report["contract_id"],
        "white_action_id": white_report["action_id"],
        "h1_h2_only": True,
        "candidate_cells_retained": 128,
        "hold_windows_outside_grid": True,
        "clean_transport": True,
        "white_default_source": "H2_COMPLETE",
        "white_explicit_alternate_source": "H1_COMPLETE_WITH_EXPLICIT_SELECTION_ONLY",
        "qualified_hold_colours": 0,
        "qualified_gray_levels": 0,
        "artifacts_verified": verify_artifacts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--skip-artifacts", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = audit(verify_artifacts=not args.skip_artifacts)
    except (AuditError, RuntimeError, OSError, ValueError) as error:
        print(f"position-balanced gray HOLD audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
