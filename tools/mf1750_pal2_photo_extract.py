#!/usr/bin/env python3
"""PAL2 production-path photo extractor: kit-bound variant of the dose pipeline.

Thin wrapper over tools/mf1750_lh3_dose_photo_analyzer.py (via the PAL1 knob
surface): the full 10-frame 128-ROI pipeline is reused verbatim. PAL2 has no
campaign package and no runner result; the extraction binds instead:
  - the analysis kit (tools/mf1750_pal2_swatch_frame.py output): its contract
    carries the swatch frame sha256/fnv1a/histogram and the action digest;
  - a sealed frame-evidence JSON (kind mf1750-pal2-frame-evidence-v1) that
    records the production refresh report (tools/mf1750_frame_tool.py
    --refresh output) and the camera review, and whose frame_sha256 must equal
    the kit's. The production path has no campaign boot; evidence carries an
    operator note instead.

No device, network, relay or camera access.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import mf1750_lh3_dose_photo_analyzer as dose  # noqa: E402

ANALYZER_VERSION = "mf1750-pal2-photo-extract-v1"
EVIDENCE_KIND = "mf1750-pal2-frame-evidence-v1"
KIT_KIND = "mf1750-pal2-analysis-kit-v1"


def configure() -> None:
    dose.RECIPE = re.compile(r"PAL2-C([0-7])-R([0-7])")
    dose.STAGE_ORDINAL = {"PAL2": 1}
    dose.EXTRACTION_KIND = "mf1750-pal2-extraction-v1"
    dose.STAGE_CONTRACT_KEY = "pal2_stage_contract"
    dose.ANALYZER_VERSION = ANALYZER_VERSION
    dose.COMPARISON_PREFIX = "PAL2_C"
    # OTP stock: three white-ish columns (2/5/7) produce no detectable blob,
    # so each row has five detected cells and 40 cells per side.
    dose.MIN_COMPONENT_CELLS = 40
    dose.MIN_ROW_CELLS = 5


def pal2_stage_identity(blank, contract, stage, evidence):
    """Bind the extraction to the kit contract and the sealed frame evidence."""
    configure()
    if contract.get("kind") != KIT_KIND or contract.get("action_count") != 1:
        raise SystemExit("not a PAL2 analysis kit")
    action = contract["actions"][0]
    if action["stage"] != stage:
        raise SystemExit("kit stage/action mismatch")
    if evidence.get("kind") != EVIDENCE_KIND:
        raise SystemExit("frame evidence kind differs")
    if evidence.get("frame_sha256") != action["frame"]["sha256"]:
        raise SystemExit("frame evidence sha does not bind the kit frame")
    for key in ("refresh_report", "camera_review"):
        binding = evidence.get(key)
        if not isinstance(binding, dict) or not binding.get("sha256"):
            raise SystemExit(f"frame evidence must bind {key}")
    if evidence.get("refresh_report", {}).get("sha256") == \
            evidence.get("camera_review", {}).get("sha256"):
        raise SystemExit("refresh report and camera review must be distinct files")
    identity = dict(blank["identity"])
    identity["action_sha256"] = action["action_id"]
    if identity.get("frame_sha256") != action["frame"]["sha256"]:
        raise SystemExit("blank identity frame sha does not bind the kit frame")
    identity["contract_id"] = contract["contract_id"]
    identity["stage"] = stage
    identity["boot_nonce"] = None
    identity["production_no_campaign_boot"] = True
    identity["frame_evidence_sha256"] = evidence.get("integrity", {}).get(
        "sha256") or evidence.get("evidence_sha256")
    identity["campaign_complete"] = True
    return identity, action


def main() -> None:
    configure()
    dose.stage_identity = pal2_stage_identity
    dose.main()


if __name__ == "__main__":
    main()
