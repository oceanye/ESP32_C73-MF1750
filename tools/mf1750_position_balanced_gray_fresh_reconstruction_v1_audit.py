#!/usr/bin/env python3
"""Offline audit for reconstruction main plus its R3 white successor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_codegen as codegen,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_once as runner,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as pack,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_codegen as white_codegen,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_once as white_runner,
)
from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_pack as white_pack,
)


class FreshReconstructionAuditError(RuntimeError):
    """Raised when an offline architecture or gate differs."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def audit() -> dict[str, Any]:
    main_report = pack.build_report()
    main_validation = runner.dry_validate(
        require_sealed=True,
        verify_artifacts=True,
    )
    white_report = white_pack.build_report(verify_artifacts=True)
    white_validation = white_runner.dry_validate(require_sealed=True)
    main_sources = codegen.render_sources(main_report)
    white_sources = white_codegen.render_sources(white_report)
    old = pack.first_pack.build_report()
    if (
        len(main_report["actions"]) != 3
        or main_report["contract"]["g4_present"] is not False
        or any(
            current[key] != prior[key]
            for current, prior in zip(
                main_report["actions"], old["actions"][:3], strict=True
            )
            for key in ("frame", "cs1_dtm", "cs2_dtm")
        )
        or main_validation["g4_accepted"] is not False
        or white_report["contract"]["accepted_source_ordinals"] != [3]
        or white_validation["accepted_source_ordinals"] != [3]
    ):
        raise FreshReconstructionAuditError("action lineage or cardinality differs")
    if not pack.source_package_is_sealed():
        raise FreshReconstructionAuditError(
            "sealed HOLD-white predecessor package is required"
        )
    if pack.source_authority_is_sealed() or pack.first_construction_reference_is_sealed():
        raise FreshReconstructionAuditError(
            "audit expected explicit unsealed live-evidence gates"
        )
    if not pack.artifacts_are_sealed() or not white_pack.artifacts_are_sealed():
        raise FreshReconstructionAuditError(
            "main and R3-only white successor artifacts must be sealed"
        )
    main_config = main_sources[codegen.CONFIG_NAME].decode("utf-8")
    white_main = white_sources[white_codegen.MAIN_NAME].decode("utf-8")
    if (
        old["actions"][3]["action_id"] in main_config
        or '\\"accepted_source_complete_ordinals\\":[3]' not in white_main
        or '\\"accepted_source_complete_ordinals\\":[5]' in white_main
    ):
        raise FreshReconstructionAuditError("G4/H2 leaked into generated surface")
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-fresh-reconstruction-v1-offline-audit",
        "result": "PASS_OFFLINE_SEALED_LIVE_EXECUTION_GATED",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "main_identity_status": "SEALED_OFFLINE_LIVE_RUN_GATES_PENDING",
        "main_contract_id": main_report["contract_id"],
        "main_action_count": 3,
        "g4_present_or_accepted": False,
        "optical_bytes_match_first_f1_v3_g1_g2_g3": True,
        "new_campaign_action_descriptor_identities": True,
        "source_hold_white_predecessor_package_sealed": True,
        "source_hold_white_authority_sealed": False,
        "first_construction_g3_reference_sealed": False,
        "main_artifacts_sealed": True,
        "main_artifact_evidence": pack.verify_artifact_files(),
        "white_successor_identity_status": (
            "SEALED_OFFLINE_RECONSTRUCTION_R3_LIVE_GATE_PENDING"
        ),
        "white_successor_contract_id": white_report["contract_id"],
        "white_successor_descriptor_id": white_report["descriptor_id"],
        "white_successor_action_id": white_report["action_id"],
        "white_successor_accepted_source_ordinals": [3],
        "white_successor_artifacts_sealed": True,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "generated_template_sources": {
            name: {"bytes": len(payload), "sha256": _sha(payload)}
            for name, payload in sorted(main_sources.items())
        },
        "generated_white_template_sources": {
            name: {"bytes": len(payload), "sha256": _sha(payload)}
            for name, payload in sorted(white_sources.items())
        },
        "blocking_gates": [
            "HOLD_WHITE_COMPLETE_PERMANENT_CLAIM_RELAY_OFF_48MP_CLEAN_WHITE_REVIEW",
            "FIRST_F1_V3_G3_COMPLETE_PERMANENT_CLAIM_48MP_CAPTURE_AND_CAMERA_RELATIVE_OBSERVATION",
            "RECONSTRUCTION_R3_COMPLETE",
            "SECOND_CONSTRUCTION_SAME_GEOMETRY_AND_CAMERA_SETTINGS_COMPARISON",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
