#!/usr/bin/env python3
"""Independent offline audit for the sealed P2-C one-shot atlas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_codegen as codegen  # noqa: E402
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_once as runner  # noqa: E402
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402


OFFLINE_BUILD = REPO_ROOT / "docs/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json"


def audit() -> dict[str, Any]:
    report = pack.build_report()
    action = report["actions"][0]
    artifacts = pack.validate_artifacts()
    host = runner.dry_validate(verify_artifacts=True)
    generated = codegen.generate()
    build_payload = OFFLINE_BUILD.read_bytes()
    build = json.loads(build_payload.decode("utf-8"))
    authority_sources = pack.authority_source_hashes()
    authority_seal = pack.authority_source_seal(authority_sources)
    profile = pack.commented_profile()
    generated_driver = (
        codegen.OUTPUT_ROOT / f"{codegen.PREFIX}_driver.inc"
    ).read_text(encoding="utf-8")
    generated_program = (
        codegen.OUTPUT_ROOT / f"{codegen.PREFIX}_program.inc"
    ).read_text(encoding="utf-8")
    generated_config = (
        codegen.OUTPUT_ROOT / f"{codegen.PREFIX}_main_config.inc"
    ).read_text(encoding="utf-8")
    generated_identity = (
        codegen.OUTPUT_ROOT / f"{codegen.PREFIX}_identity.inc"
    ).read_text(encoding="utf-8")
    platformio_config = (REPO_ROOT / "platformio.p2_commented_endpoint_atlas_4x8_v1.ini").read_text(
        encoding="utf-8"
    )
    flat = [code for row in pack.CODE_ROWS for code in row]
    if (
        host.get("result") != "PASS"
        or build.get("result") != "PASS"
        or build.get("contract_id") != report["contract_id"]
        or build.get("action_descriptor_sha256") != action["descriptor_id"]
        or build.get("action_sha256") != action["action_id"]
        or build.get("artifacts") != artifacts
        or build.get("authority_sources") != authority_sources
        or build.get("authority_source_hashes") != authority_sources
        or build.get("offline_authority_seal") != authority_seal
        or profile["name"] != "commented"
        or profile["cs1"] != profile["cs2"]
        or profile["complete_profile_tuple"] is not True
        or action["waveform_binding"] != profile
        or action["global_header"] != "commented"
        or action["profile_id"] != "LEGACY_COMMENTED_HEADER__CS1_COMMENTED535__CS2_COMMENTED535"
        or action["global_tuple_id"] != "1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038"
        or action["cs1_dtm"] != action["cs2_dtm"]
        or sorted(flat) != [code for code in range(8) for _ in range(4)]
        or report["contract"]["one_driver_call_per_action"] is not True
        or report["contract"]["one_visible_refresh_per_action"] is not True
        or report["contract"]["complete_busy_required"] is not True
        or report["contract"]["retry"] is not False
        or report["contract"]["recovery"] is not False
        or report["contract"]["automatic_chaining"] is not False
        or "useCommentedGlobal = true;" not in generated_driver
        or "if (!useCommentedGlobal) return false;" not in generated_driver
        or "kCommentedProfileCompileTimeOnly = true" not in generated_identity
        or "P2-C commented tuple is immutable" not in generated_driver
        or "const bool active = false;" not in generated_program
        or "-D MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD=1" not in platformio_config
        or "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1" not in platformio_config
        or any(
            token in platformio_config
            for token in (
                "-D MF1750_RUNTIME_LUT_SAME_R20_PARITY_4X8_V2_BUILD=1",
                "-D MF1750_RAW_P16_CROSSOVER_POSBAL_BUILD=1",
                "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD=1",
                "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD=1",
                "-D MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD=1",
            )
        )
        or profile["global_tuple_id"] not in generated_config
    ):
        raise RuntimeError("P2-C sealed boundary differs")
    # Keep the deny-list itself out of the authored-source corpus.  Otherwise
    # this checker would reject its own literals (and a benign ``relay
    # switched_at`` field in the retained-review schema).  Word boundaries are
    # intentional: ``relay switched_at`` is evidence metadata, while an
    # executable relay-control surface remains forbidden.
    forbidden = (
        "Ser" + "ial.",
        "COM" + "14",
        "VID_" + "32E4",
        "relay" + " switch",
        "firmware" + " upload",
    )
    authored = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO_ROOT / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_pack.py",
            REPO_ROOT / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_codegen.py",
            REPO_ROOT / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_build.py",
            REPO_ROOT / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_once.py",
            REPO_ROOT / "tools/mf1750_p2_retained_clean_white_human_review.py",
            REPO_ROOT / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_audit.py",
        )
    )
    if any(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
            authored,
        )
        for token in forbidden
    ):
        raise RuntimeError("P2-C offline authority contains a forbidden I/O surface")
    return {
        "schema_version": 1,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-independent-audit",
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "device_or_campaign_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "frame_sha256": action["frame"]["sha256"],
        "controller_dtm_sha256": action["cs1_dtm"]["sha256"],
        "global_tuple_id": action["global_tuple_id"],
        "artifacts": artifacts,
        "generated_sources": generated["generated"],
        "authority_sources": authority_sources,
        "offline_authority_seal": authority_seal,
        "offline_build": {
            "path": OFFLINE_BUILD.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(build_payload),
            "sha256": hashlib.sha256(build_payload).hexdigest(),
        },
        "driver_calls": 1,
        "visible_refreshes": 1,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "independent_factory_white_successor_required": True,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, sort_keys=True))
