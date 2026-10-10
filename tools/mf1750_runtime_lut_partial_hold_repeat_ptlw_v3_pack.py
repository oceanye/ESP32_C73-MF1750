#!/usr/bin/env python3
"""Offline identities for the BUSY-qualified repeat-PTLW V3 campaign."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_partial_hold_pack as identity  # noqa: E402
from tools import (  # noqa: E402
    mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_pack as v2,
)


VARIANT_KEY = "L535_FACTORY_OTP_WHITE_REPEAT_PTLW_BUSY_QUALIFIED_V3"
BUILD_TAG = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_2026-08-23"
)
TEST_ID = "EC5-RUNTIME-LUT-PARTIAL-HOLD-REPEAT-PTLW-V3"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3"
NVS_NAMESPACE = "rlph_rptlw_v3"
NVS_KEY = "cursor_rptv3"
PROFILE_ID = v2.PROFILE_ID


def build_report() -> dict[str, Any]:
    """Rebind unchanged V2 panel payloads to wholly new V3 identities."""

    previous = v2.build_report()
    report = deepcopy(previous)
    actions: list[dict[str, Any]] = report["actions"]
    for item in actions:
        item.pop("descriptor_id", None)
        item.pop("action_id", None)
        descriptor = {
            "schema": "mf1750-runtime-lut-repeat-ptlw-descriptor-v3",
            "variant": VARIANT_KEY,
            "profile_id": PROFILE_ID,
            **item,
        }
        item["descriptor_id"] = identity.sha256(identity.canonical(descriptor))
        item["action_id"] = identity.sha256(
            (
                "MF1750_RUNTIME_LUT_REPEAT_PTLW_ACTION_V3|"
                f"{VARIANT_KEY}|{item['ordinal']}|{item['descriptor_id']}"
            ).encode("ascii")
        )

    contract = deepcopy(report["contract"])
    contract.update(
        {
            "schema": "mf1750-runtime-lut-repeat-ptlw-contract-v3",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "campaign_id": CAMPAIGN_ID,
            "nvs_namespace": NVS_NAMESPACE,
            "nvs_key": NVS_KEY,
            "supersedes": previous["contract_id"],
            "busy_qualification": {
                "raw_idle_level": 1,
                "host_preflight_required_for_every_ordinal": True,
                "firmware_arm_required": True,
                "firmware_execute_required": True,
                "firmware_dispatch_required": True,
                "busy_zero_accepted": False,
            },
        }
    )
    contract["actions"] = [
        {
            "ordinal": item["ordinal"],
            "role": item["role"],
            "palette_source": item["palette_source"],
            "dtm_transport": item["dtm_transport"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
        }
        for item in actions
    ]

    report.update(
        {
            "schema_version": 3,
            "kind": "mf1750-runtime-lut-repeat-ptlw-v3-offline-identities",
            "variant_key": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            "test_id": TEST_ID,
            "campaign_id": CAMPAIGN_ID,
            "nvs_namespace": NVS_NAMESPACE,
            "nvs_key": NVS_KEY,
            "contract_id": identity.sha256(identity.canonical(contract)),
            "contract": contract,
        }
    )
    return report


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
