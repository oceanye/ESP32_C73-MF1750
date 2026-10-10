#!/usr/bin/env python3
"""Offline LH1 build with the completed LH4 white source; never performs device I/O."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from tools import mf1750_lightness_history_firmware as original

ROOT = original.ROOT
GENERATOR = ROOT / "tools/mf1750_lightness_history_firmware.py"
WHITE_ACTION = (
    ROOT
    / ".test-output/hardware/MF1750_P2_WHITE_LH4_20260912_V1/action-01-factory-otp-white.json"
)
WHITE_ACTION_ID = "677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19"
WHITE_BIN_SHA = "dc93c95a956eecf7d9cb753e5fb82ea16e5f2142694a8fcd22157481570d2de6"
WHITE_ELF_SHA = "ff3793efde294bf981f3b1932799fdc574917fe33c0f1d15bf636367c5aba067"
WHITE_CLAIM = (
    ROOT
    / ".test-output/hardware/.mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_claims"
    / (WHITE_ACTION_ID + ".json")
)
SOURCE_AUDIT = (
    ROOT / ".test-output/offline/LH1_LH4_SOURCE_AUDIT_20260912_V1/source-audit.json"
)
DEFAULT_OUTPUT = ROOT / ".test-output/offline/LH1_LH4_20260912_R1"


def read_sealed(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing/unsafe source evidence: {path}")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    body = {k: v for k, v in value.items() if k != "integrity"}
    if value.get("integrity") != {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": original.algorithm.digest(original.algorithm.canonical(body)),
    }:
        raise ValueError(f"source evidence integrity differs: {path}")
    return value


def validate_white_source() -> dict:
    """Validate the historical source action/claim; physical admission remains separate."""
    action, claim = read_sealed(WHITE_ACTION), read_sealed(WHITE_CLAIM)
    for value in (action, claim):
        if (
            value["action"]["action_id"] != WHITE_ACTION_ID
            or value["firmware_sha256"] != WHITE_BIN_SHA
            or value["running_app_elf_sha256"] != WHITE_ELF_SHA
        ):
            raise ValueError("LH4 white artifact/action identity differs")
    report = action["terminal_report"]
    if not (
        action["outcome"] == "complete_pass"
        and action["visible_refreshes"] == 1
        and report["terminal_state"] == "COMPLETE"
        and report["valid"] is True
        and report["result"] is True
        and report["driver_call_count_for_action"]
        == report["total_driver_call_count"]
        == 1
        and report["action_id"] == WHITE_ACTION_ID
        and action["boot_nonce"] == claim["boot_nonce"]
        and action["action"] == claim["action"]
        and Path(action["claim_file"]).resolve() == WHITE_CLAIM.resolve()
    ):
        raise ValueError("LH4 white terminal/claim differs")
    if claim["state"] != "permanently_claimed_after_j2_on_preflight_before_first_arm":
        raise ValueError("LH4 claim state differs")
    driver = report["driver"]
    if not (
        driver["valid"] is True
        and driver["sequence_ok"] is True
        and driver["running"] is False
        and driver["wait_timeout"] is False
        and driver["failure_code"] == 0
        and all(
            driver[k] is True
            for k in ("pon_busy_seen", "drf_busy_seen", "pof_busy_seen")
        )
    ):
        raise ValueError("LH4 driver evidence differs")
    read_sealed(SOURCE_AUDIT)
    return {
        **deepcopy(original.SOURCE_WHITE),
        "firmware_sha256": WHITE_BIN_SHA,
        "firmware_elf_sha256": WHITE_ELF_SHA,
        "terminal_evidence": original.bind(WHITE_ACTION),
        "claim_evidence": original.bind(WHITE_CLAIM),
        "clean_white_review": original.bind(SOURCE_AUDIT),
        "binding_generator": original.bind(Path(__file__)),
        "optical_review_scope": "historical operator white observation plus explicit camera/electrical limitations; not current physical admission",
        "historical_source_boot": action["boot_nonce"],
    }


def private_generator():
    spec = importlib.util.spec_from_file_location(
        "_lh1_lh4_isolated_codegen", GENERATOR
    )
    if spec is None or spec.loader is None:
        raise ValueError("cannot load frozen LH1 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE_WHITE = validate_white_source()
    module.CAMPAIGN = "EC5_LIGHTNESS_HISTORY_LH4_V1_20260912"
    module.BUILD_TAG = "MF1750_EC5_LIGHTNESS_HISTORY_LH4_V1_2026-09-12"
    return module


def prepare(out: Path) -> dict:
    # The private module changes source identity, not shared imported globals or old files.
    module = private_generator()
    result = module.prepare(out)
    current = json.loads((out / "contract.json").read_text(encoding="utf-8"))
    old = json.loads(
        (ROOT / ".test-output/offline/LH1_20260911_R3/contract.json").read_text(
            encoding="utf-8"
        )
    )
    for before, after in zip(old["actions"], current["actions"], strict=True):
        for key in (
            "stage",
            "profile",
            "profile_sha256",
            "frame",
            "cs1_dtm",
            "cs2_dtm",
        ):
            if before[key] != after[key]:
                raise ValueError(f"unexpected lightness recipe/drive change: {key}")
        if before["action_id"] == after["action_id"]:
            raise ValueError("changed white source must change action identity")
    if old["nvs"] != current["nvs"]:
        raise ValueError(
            "LH1 consumption namespace cannot be changed to bypass prior use"
        )
    return {
        **result,
        "source_binding_updated": True,
        "frames_and_profiles_unchanged": True,
        "same_nvs_preserved": True,
        "live_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "verify"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.output_dir.resolve())
    elif args.command == "build":
        validate_white_source()
        result = original.build(args.output_dir.resolve())
    else:
        validate_white_source()
        original.verify_package(args.output_dir.resolve())
        result = {"result": "PASS", "hardware_accessed": False, "live_ready": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
