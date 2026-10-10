#!/usr/bin/env python3
"""Independent offline audit for the fresh V3 factory-white successor."""

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
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_once as runner,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_pack as pack,
)


class AuditError(RuntimeError):
    """Raised when the isolated white-successor contract differs."""


def audit() -> dict[str, Any]:
    white = pack.dry_validate(verify_artifacts=True)
    host = runner.dry_validate()
    source = pack.source_pack.dry_validate(verify_artifacts=True)
    report = pack.build_report(verify_artifacts=True)
    source_report = pack.source_pack.build_report()
    contract = report["contract"]
    accepted = contract["accepted_source_complete_actions"]
    expected = [
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": item["role"],
        }
        for item in source_report["actions"]
        if item["ordinal"] in (3, 4)
    ]
    if (
        white.get("result") != "PASS"
        or host.get("result") != "PASS"
        or source.get("result") != "PASS"
        or source.get("artifacts_sealed") is not True
        or source.get("compiled_identity_binary", {}).get("verified") is not True
        or pack.SOURCE_MAIN_CONTRACT_ID != source_report["contract_id"]
        or accepted != expected
        or contract.get("default_source_complete_ordinal") != 3
        or contract.get("optional_g4_source_requires_explicit_human_confirmation")
        is not True
        or contract.get("current_function_plan_executes_g4") is not False
        or contract.get("automatic_source_selection") is not False
        or contract.get("automatic_execution") is not False
        or contract.get("retry") is not False
        or contract.get("fallback") is not False
        or contract.get("automatic_recovery") is not False
        or contract.get("autochain") is not False
        or contract.get("source_terminal_evidence_required_before_any_live_request")
        is not True
        or contract.get("factory_otp") is not True
        or contract.get("runtime_lut_write") is not False
        or contract.get("custom_waveform_write") is not False
        or contract.get("one_visible_refresh") is not True
        or pack.NVS_NAMESPACE != "lgmpb3w_v1"
        or pack.NVS_KEY != "used_lgmpb3w1"
        or pack.ENVIRONMENT != "ec5_luma_gray_mpb_v3_white_v1"
        or pack.BUILD_ROOT != "b-luma-gray-mpb-v3-white-v1"
        or pack.BASE_ROUTE
        != "/api/ec5/luma-gray-mechanism-position-balanced-v3/white-successor-v1"
        or "position_balanced_v3_white_successor_v1_claims"
        not in str(runner.host.DEFAULT_CLAIMS)
        or "POSITION_BALANCED_V3_WHITE_SUCCESSOR_20260901_V1"
        not in str(runner.host.DEFAULT_OUTPUT)
    ):
        raise AuditError(
            "white-successor identity/source/automatic-action gate differs"
        )

    paths = runner._source_terminal_paths()  # noqa: SLF001
    available = {ordinal: path.is_file() for ordinal, path in paths.items()}
    if available[4]:
        live_admission = "G4_COMPLETE_REQUIRES_EXPLICIT_HUMAN_CONFIRMATION"
    elif available[3]:
        live_admission = "G3_COMPLETE_AVAILABLE_FOR_DEEP_VALIDATION"
    else:
        live_admission = "WAITING_FOR_FRESH_V3_G3_COMPLETE"
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v3-white-successor-v1-independent-audit",
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
        "source_main_identity_and_artifacts_deeply_verified": True,
        "accepted_source_complete_actions": deepcopy(accepted),
        "default_source_complete_ordinal": 3,
        "optional_g4_source_requires_explicit_human_confirmation": True,
        "current_function_plan_executes_g4": False,
        "source_terminal_evidence_available": available,
        "source_terminal_evidence_deep_validation": (
            "DEFERRED_UNTIL_LIVE_G3_OR_EXPLICIT_G4_COMPLETE_EXISTS"
        ),
        "live_admission": live_admission,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__, allow_abbrev=False).parse_args(
        argv
    )


def main(argv: Sequence[str] | None = None) -> int:
    _parse_args(argv)
    try:
        value = audit()
    except (AuditError, RuntimeError, OSError, ValueError) as error:
        print(f"V3 white successor audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
