#!/usr/bin/env python3
"""Independent offline audit for the fresh LUMA/GRAY mechanism V3 package."""

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
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_once as runner,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as pack,
)


class AuditError(RuntimeError):
    """Raised when any independent frozen-identity gate differs."""


OLD_V2_CONTRACT_ID = "b9baafc7b0e4966a23eb1189372e36d690e8df84d8e17f4c8cbc3536be46f019"
OLD_V2_ACTION_IDS = {
    "5ceab793eb464bac3350f5e08b34d000338a4d1e5e254fe9746867bc27acd1ca",
    "c160bb98b5d28297480fe53f7c96b2f295fd39a03961c025926266d700491bec",
    "8595a460ea089f580516d793c6c1adb7acef1748c9ad42c28cf2394e1686d92d",
    "26310ffc6c3d2781592f4211b28677450ebd98b03468f49cda765ddf933b76be",
}
EXPECTED_REVIEW_INTEGRITY = (
    "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40"
)
EXPECTED_REVIEW_ID = "b0a62b0c7dbf178fa6a2763d0bebf417b61dda6bd86bab701c84f658ae2ba96f"


def audit(*, verify_artifacts: bool = True) -> dict[str, Any]:
    package = pack.dry_validate(verify_artifacts=verify_artifacts)
    host = runner.dry_validate(verify_artifacts=verify_artifacts)
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    source = pack.validate_source_gate()
    action_ids = {item["action_id"] for item in actions}
    if (
        package.get("result") != "PASS"
        or host.get("result") != "PASS"
        or report["contract_id"] == OLD_V2_CONTRACT_ID
        or action_ids & OLD_V2_ACTION_IDS
        or len(actions) != 4
        or len(contract["recipes"]) != 16
        or any(pack.CS1_RECIPE_AT_CELL.count(recipe) != 4 for recipe in range(16))
        or pack.CS2_RECIPE_AT_CELL != tuple(reversed(pack.CS1_RECIPE_AT_CELL))
        or contract.get("spatial_dither") is not False
        or contract.get("spatial_mixing") is not False
        or contract.get("cell_fill_uniform_code") is not True
        or contract.get("required_core_action_ordinals") != [1, 2, 3]
        or contract.get("optional_repeat_action_ordinal") != 4
        or contract.get("automatic_recovery") is not False
        or contract.get("autochain") is not False
        or any(item["driver_role"] == "White" for item in actions)
        or source.get("camera_relative_only") is not True
        or source.get("absolute_white_or_uniformity_qualified") is not False
        or source.get("qualified_level_count") != 0
        or source.get("retained_action_to_capture_continuity_proven") is not False
        or source.get("review_id") != EXPECTED_REVIEW_ID
        or source["bindings"]["camera_white_review"]["canonical_integrity_sha256"]
        != EXPECTED_REVIEW_INTEGRITY
        or pack.CONFIG.environment != "ec5_luma_gray_mpb_v3"
        or pack.CONFIG.build_root != "b-luma-gray-mpb-v3"
        or pack.CONFIG.nvs_namespace != "lgmpb_v3"
        or pack.CONFIG.nvs_key != "cur_lgmpb3"
        or pack.CONFIG.nvs_boot_key != "boot_lgmpb3"
        or pack.CONFIG.base_route != "/api/ec5/luma-gray-mechanism-position-balanced-v3"
        or "position_balanced_v3_claims" not in str(runner.base.runner.DEFAULT_CLAIMS)
        or "20260901_V3" not in str(runner.base.runner.DEFAULT_OUTPUT)
    ):
        raise AuditError("fresh V3 identity/mechanism/source isolation differs")

    white_successor_candidates = (
        REPO_ROOT
        / "platformio.runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1.ini",
        REPO_ROOT
        / "tools/mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_pack.py",
        REPO_ROOT
        / "tools/mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_once.py",
    )
    independent_white_successor_present = all(
        path.is_file() for path in white_successor_candidates
    )
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-independent-audit",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "fresh_campaign_identity": True,
        "old_v2_modified_or_replayed": False,
        "contract_id": report["contract_id"],
        "action_ids": [item["action_id"] for item in actions],
        "actions": 4,
        "recipes": 16,
        "replicas_per_recipe_per_controller": 4,
        "spatial_dither": False,
        "main_action_sequence_embeds_white_recovery": False,
        "g4_optional_identical_target_repeat": True,
        "source_gate": deepcopy(source),
        "camera_relative_only": True,
        "absolute_white_or_uniformity_qualified": False,
        "qualified_level_count": 0,
        "retained_action_to_capture_continuity_proven": False,
        "artifacts_verified": verify_artifacts,
        "independent_white_successor_present": independent_white_successor_present,
        "remaining_gate": (
            None
            if independent_white_successor_present
            else "CREATE_FRESH_INDEPENDENT_FACTORY_OTP_WHITE_SUCCESSOR_AFTER_G3_OR_EXPLICIT_G4_COMPLETE"
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--skip-artifacts", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        value = audit(verify_artifacts=not args.skip_artifacts)
    except (AuditError, RuntimeError, OSError, ValueError) as error:
        print(f"LUMA/GRAY mechanism V3 audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
