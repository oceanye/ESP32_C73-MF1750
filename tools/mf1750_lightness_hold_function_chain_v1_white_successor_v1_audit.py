#!/usr/bin/env python3
"""Independent offline audit for the post-H2 factory-white successor."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_lightness_hold_function_chain_v1_once as source_once  # noqa: E402
from tools import (  # noqa: E402
    mf1750_lightness_hold_function_chain_v1_white_successor_v1_once as runner,
)
from tools import (  # noqa: E402
    mf1750_lightness_hold_function_chain_v1_white_successor_v1_pack as pack,
)


class AuditError(RuntimeError):
    """Raised when the isolated successor boundary differs."""


def audit() -> dict[str, Any]:
    source = pack.source_pack.dry_validate(
        require_source_sealed=True, verify_artifacts=True
    )
    white = pack.dry_validate(verify_artifacts=True)
    host = runner.dry_validate()
    report = pack.build_report(verify_artifacts=True)
    source_report = pack.source_pack.build_report()
    expected = source_report["actions"][4]
    accepted = report["contract"]["accepted_source_complete_actions"]
    fixed_source = source_once.ACTION_OUTPUTS[5].resolve()
    if (
        source.get("result") != "PASS"
        or source.get("artifacts_verified") is not True
        or white.get("result") != "PASS"
        or host.get("result") != "PASS"
        or report["contract"]["accepted_source_ordinals"] != [5]
        or accepted
        != [
            {
                "ordinal": 5,
                "descriptor_id": expected["descriptor_id"],
                "action_id": expected["action_id"],
                "role": expected["role"],
            }
        ]
        or report["contract"]["source_fault_not_accepted"] is not True
        or report["contract"]["source_early_stop_not_accepted"] is not True
        or report["contract"]["factory_otp"] is not True
        or report["contract"]["runtime_lut_write"] is not False
        or report["contract"]["one_visible_refresh"] is not True
        or report["contract"]["autochain"] is not False
        or runner._source_terminal_paths() != {5: fixed_source}  # noqa: SLF001
        or runner.DEVICE_SOURCE_BINDING["source_main_completed_h2_only"] is not True
        or runner.DEVICE_SOURCE_BINDING[
            "source_main_interrupted_or_completed_branch"
        ]
        is not False
    ):
        raise AuditError("post-H2 white successor identity or source gate differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-lightness-hold-function-chain-v1-white-successor-v1-independent-audit",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "descriptor_id": report["descriptor_id"],
        "action_id": report["action_id"],
        "firmware": {
            "bytes": pack.FIRMWARE_BIN_BYTES,
            "sha256": pack.FIRMWARE_BIN_SHA256,
        },
        "elf": {
            "bytes": pack.FIRMWARE_ELF_BYTES,
            "sha256": pack.FIRMWARE_ELF_SHA256,
        },
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "accepted_source_complete_actions": deepcopy(accepted),
        "accepted_source_ordinals": [5],
        "source_fault_accepted": False,
        "source_early_stop_accepted": False,
        "source_terminal_path": fixed_source.relative_to(REPO_ROOT).as_posix(),
        "source_terminal_evidence_available": fixed_source.is_file(),
        "live_admission": (
            "H2_COMPLETE_AVAILABLE_FOR_DEEP_VALIDATION"
            if fixed_source.is_file()
            else "WAITING_FOR_FRESH_ORDINAL5_H2_COMPLETE"
        ),
        "source_terminal_evidence_deep_validation": (
            "DEFERRED_UNTIL_LIVE_H2_COMPLETE_EXISTS"
        ),
        "automatic_source_selection": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }


def main() -> int:
    try:
        value = audit()
    except (AuditError, RuntimeError, OSError, ValueError) as error:
        print(f"lightness/HOLD white successor audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
