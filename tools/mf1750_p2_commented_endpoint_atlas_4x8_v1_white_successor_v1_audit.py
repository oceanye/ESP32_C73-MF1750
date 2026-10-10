#!/usr/bin/env python3
"""Independent offline audit for the post-P2-C factory-white successor."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_once as source_once  # noqa: E402
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as source_pack  # noqa: E402
from tools import (  # noqa: E402
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_once as runner,
)
from tools import (  # noqa: E402
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_pack as pack,
)


class P2CommentedWhiteSuccessorAuditError(RuntimeError):
    """Raised when any sealed containment boundary differs."""


def audit() -> dict[str, Any]:
    source_artifacts = source_pack.validate_artifacts()
    white = pack.dry_validate(require_sealed=True, verify_artifacts=True)
    host = runner.dry_validate()
    report = pack.build_report(verify_artifacts=True)
    source = source_pack.build_report()
    accepted = report["contract"]["accepted_source_complete_actions"]
    fixed_source = source_once.ACTION_OUTPUTS[1].resolve()
    binding = runner._source_binding(report)  # noqa: SLF001
    expected = source["actions"][0]
    if (
        white.get("result") != "PASS"
        or host.get("result") != "PASS"
        or report["contract"]["source_main_contract_id"]
        != pack.SOURCE_MAIN_CONTRACT_ID
        or report["contract"]["source_main_offline_build_file_sha256"]
        != pack.SOURCE_BUILD_REPORT_FILE_SHA256
        or report["contract"]["source_main_artifacts"] != pack.SOURCE_ARTIFACTS
        or report["contract"]["accepted_source_ordinals"] != [1]
        or accepted
        != [
            {
                "ordinal": 1,
                "descriptor_id": expected["descriptor_id"],
                "action_id": expected["action_id"],
                "role": pack.SOURCE_MAIN_ROLE,
            }
        ]
        or report["contract"]["source_fault_not_accepted"] is not True
        or report["contract"]["source_early_stop_not_accepted"] is not True
        or report["contract"]["factory_otp"] is not True
        or report["contract"]["runtime_lut_write"] is not False
        or report["contract"]["custom_waveform_write"] is not False
        or report["contract"]["one_visible_refresh"] is not True
        or report["contract"]["full_busy_required"] is not True
        or report["contract"]["retry"] is not False
        or report["contract"]["fallback"] is not False
        or report["contract"]["automatic_recovery"] is not False
        or report["contract"]["autochain"] is not False
        or binding["source_main_completed_p2_commented_only"] is not True
        or binding["source_main_interrupted_or_completed_branch"] is not False
        or binding["source_main_resume_forbidden_after_containment"] is not True
        or binding["accepted_source_complete_ordinals"] != [1]
    ):
        raise P2CommentedWhiteSuccessorAuditError(
            "P2-C white successor boundary differs"
        )
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-"
            "independent-audit"
        ),
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
        "source_main_offline_build_file_sha256": (
            pack.SOURCE_BUILD_REPORT_FILE_SHA256
        ),
        "source_main_artifacts": deepcopy(pack.SOURCE_ARTIFACTS),
        "source_artifact_files": source_artifacts,
        "accepted_source_complete_actions": deepcopy(accepted),
        "accepted_source_ordinals": [1],
        "source_fault_accepted": False,
        "source_early_stop_accepted": False,
        "source_terminal_path": fixed_source.relative_to(REPO_ROOT).as_posix(),
        "source_terminal_evidence_available": fixed_source.is_file(),
        "live_admission": (
            "P2_C_ORDINAL1_COMPLETE_AVAILABLE_FOR_DEEP_VALIDATION"
            if fixed_source.is_file()
            else "WAITING_FOR_FRESH_P2_C_ORDINAL1_COMPLETE"
        ),
        "source_terminal_evidence_deep_validation": (
            "DEFERRED_UNTIL_LIVE_P2_C_COMPLETE_EXISTS"
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
    except (OSError, RuntimeError, ValueError) as error:
        print(f"P2-C white successor audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
