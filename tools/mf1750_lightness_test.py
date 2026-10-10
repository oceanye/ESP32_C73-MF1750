#!/usr/bin/env python3
"""Create and run the offline MF1750 lightness test. No device operations."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo.common import (  # noqa: E402
    StaticPhotoContractError,
    attach_integrity,
    file_sha256,
    require_sha256,
)
from host.static_photo import lightness_test as suite  # noqa: E402
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as geometry,
)


P2_PATH = (
    ROOT
    / ".test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/p2c-ordinal1-optical-report-v2.json"
)
P2_SHA = "f5bdc0baba86eb1ee6e144d84dd0ab3561979856f211b58549d051936b0f7e9e"
ACTION_SHA = "f9c90f64fc096f301a7b66dc44e2902c09bc536aa8f7e9dc228a06fbf58873de"


def bind(path: Path) -> dict:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": file_sha256(payload),
    }


def verify_file(path: Path, expected: str) -> dict:
    require_sha256(expected, "file hash")
    value = bind(path)
    if value["sha256"] != expected:
        raise suite.LightnessTestError(f"evidence hash mismatch: {path}")
    return value


def write_new(path: Path, value: dict) -> None:
    # Validate serialization before creating a file. Never truncate old evidence.
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    )
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def checked_analysis(data: dict, input_path: Path) -> dict:
    verified = []
    for item in data.get("evidence_files", []):
        verified.append(verify_file(Path(item["path"]), item["sha256"]))
    if data.get("data_origin") == "FIELD_DERIVED":
        if not verified:
            raise suite.LightnessTestError(
                "field data requires existing hashed evidence files"
            )
        hashes = {item["sha256"] for item in verified}
        for row in data.get("observations", []):
            if (
                row.get("lab") is not None
                and row.get("measurement_evidence_sha256") not in hashes
            ):
                raise suite.LightnessTestError(
                    "measurement is not bound to a verified evidence file"
                )
        if (
            data.get("lab_space") == "calibrated"
            and data.get("calibration_evidence_sha256") not in hashes
        ):
            raise suite.LightnessTestError(
                "calibration must be bound to an existing evidence file"
            )
    report = suite.analyze_observations(data)
    report.pop("integrity")
    report["input"] = bind(input_path)
    report["verified_evidence_files"] = verified
    report["verification_scope"] = (
        "file hashes plus input structure; no new raw protocol or calibration adjudication"
    )
    return attach_integrity(report)


def create_package(output: Path) -> dict:
    recipes = geometry.recipe_map()  # Pure metadata; never call build/live/codegen.
    plan = suite.build_plan(recipes)
    observations = suite.blank_observations(recipes)
    run_record = {
        "kind": "mf1750-lightness-construction-record-v1",
        "test_id": suite.VERSION,
        "status": "UNFILLED",
        "test_phase": "SCREEN",
        "run_id": None,
        "panel_id": None,
        "fresh_white_anchor": None,
        "actions": [
            {
                "stage": stage,
                "boot": None,
                "controller_revision": {c: None for c in suite.CONTROLLERS},
                "profile_id": None,
                "profile_hash_with_scope": None,
                "source_state": None,
                "target_state": None,
                "firmware_sha256": None,
                "action_sha256": None,
                "frame_sha256": None,
                "controller_frame_hashes": {c: None for c in suite.CONTROLLERS},
                "temperature_c": None,
                "camera_requested_and_effective_settings": None,
                "roi_definition": None,
                "raw_action_status_files": None,
                "busy_timeline": None,
                "raw_photos_and_sidecars": None,
                "human_observation": None,
                "derived_analysis": None,
                "actual_counts": None,
                "review_verdict": None,
                "waveform_internal_phase": "OPAQUE",
                "next_action_authorized": False,
            }
            for stage in ("SOURCE", "MIDDLE", "TARGET")
        ],
        "fields_are_evidence_slots_not_a_live_gate": True,
        "hardware_accessed": False,
        "qualified_count": 0,
    }
    # Null slots are intentionally incomplete; a hash/boolean cannot grant a gate.
    lifecycle = {
        "kind": "mf1750-lightness-lifecycle-evidence-slots-v1",
        "test_id": suite.VERSION,
        "status": "UNFILLED",
        "qualified_count": 0,
        "automated_qualification": False,
        "levels": [
            {
                "required_level_count": count,
                "prior_accepted_level_count": None,
                "controller_reviews": {
                    controller: {
                        "screen_report": None,
                        "local_hold_action_before_after": None,
                        "fresh_white_chains": [None, None, None],
                        "retention_seconds": {"5": None, "60": None, "600": None},
                        "temperature_and_camera_comparability": None,
                        "human_verdict": None,
                    }
                    for controller in suite.CONTROLLERS
                },
                "cross_controller_optical_match": None,
                "slot_review": None,
            }
            for count in suite.LEVEL_COUNTS
        ],
        "white_erasure_is_transient_failure": False,
    }
    material_paths = [
        Path(__file__),
        ROOT / "host/static_photo/lightness_test.py",
        ROOT / "host/color_pipeline/color.py",
        ROOT / "host/static_photo/common.py",
        ROOT
        / "tools/mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack.py",
        ROOT / "docs/MF1750_SPD1657B_V11_DATASHEET_REVIEW_2026-09-10.md",
        ROOT / "参考资料/SPD1657B_1.1.pdf",
        ROOT / "src/generated/spd1657_legacy_535_reference.inc",
        ROOT / "docs/MF1750_LIGHTNESS_TEST_V1_2026-09-11.md",
    ]
    materials = [bind(path) for path in material_paths]
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (
        ("test-plan.json", plan),
        ("observations.blank.json", observations),
        ("run-record.blank.json", run_record),
        ("lifecycle.blank.json", lifecycle),
        ("thresholds.json", suite.THRESHOLDS),
    ):
        write_new(output / name, value)
    report = checked_analysis(observations, output / "observations.blank.json")
    write_new(output / "blank-evaluation.json", report)
    manifest = attach_integrity(
        {
            "kind": "mf1750-lightness-test-package-manifest-v1",
            "test_id": suite.VERSION,
            "materials": materials,
            "outputs": [bind(p) for p in sorted(output.glob("*.json"))],
            "offline_ready": True,
            "live_ready": False,
            "qualified_count": 0,
            "observations": len(observations["observations"]),
            "hardware_accessed": False,
            "actual_visible_refreshes": 0,
        }
    )
    write_new(output / "manifest.json", manifest)
    return {
        "offline_result": "PASS",
        "live_result": "HOLD_FOR_EVIDENCE",
        "output": str(output),
        "cells": 128,
        "qualified_count": 0,
    }


def review_p2(output: Path) -> dict:
    """Re-evaluate the exact historical P2 archive, preserving missing fields."""
    evidence = [verify_file(P2_PATH, P2_SHA)]
    archive = json.loads(P2_PATH.read_text(encoding="utf-8"))
    evidence.append(verify_file(Path(archive["action_result"]["path"]), ACTION_SHA))
    for phase in ("baseline", "post"):
        captures = archive["capture_evidence"][phase]
        if len(captures) != 10:
            raise suite.LightnessTestError("P2 archive requires ten photos per phase")
        for capture in captures:
            for kind in ("photo", "sidecar"):
                evidence.append(
                    verify_file(
                        Path(capture[kind + "_path"]), capture[kind + "_sha256"]
                    )
                )
    action = archive["action_binding"]
    data = suite.blank_observations(geometry.recipe_map())
    data.update(
        {
            "data_origin": "FIELD_DERIVED",
            "observations": [],
            "evidence_files": evidence,
            "protocol_result": "PASS"
            if archive["protocol"]["identity_and_protocol_pass"]
            else "FAIL",
            "image_result": "PASS"
            if archive["measurement"]["image_and_optical_evidence_valid"]
            else "FAIL",
            "camera": {**archive["camera"], "usb_id": "VID_32E4:PID_4801"},
            "hue_family": None,
            "track": None,
        }
    )
    data["identity"] = {
        "panel_id": "MF-17506-M009F-T historical run unit; physical serial not authenticated",
        "run_id": archive["run_id"],
        "controller_revision": "SPD1657B rev 0x04",
        "boot": action["boot_nonce"],
        "profile_id": action["profile_id"],
        "test_phase": "SCREEN_HISTORICAL_P2_ENDPOINT_DIAGNOSTIC",
        "firmware_sha256": action["firmware_sha256"],
        "action_sha256": action["action_id"],
        "frame_sha256": action["frame_sha256"],
        "source_state": archive["source_state"]["state"],
        "target_state": archive["target_state"]["state"],
        "camera_setup_id": archive["camera"]["mount_id"],
        "illumination_id": None,
        "temperature_c": archive["temperature_c"],
        "roi_definition_id": "P2 current homography + inner 60%; normalized to local white",
    }
    for cell in archive["cells"]:
        noise = cell["baseline_noise"]
        bounds = dict(
            zip(("x", "y", "width", "height"), cell["logical_bounds"], strict=True)
        )
        # The archive's logical bounds include the global CS2 offset.
        if cell["controller_name"] == "CS2":
            bounds["x"] -= 512
        data["observations"].append(
            {
                "controller": cell["controller_name"],
                "comparison_id": "P2_COMPLETE_ENDPOINTS",
                "recipe_id": f"P2-C{cell['code']}",
                "position": ("T" if cell["row"] < 2 else "B")
                + ("L" if cell["column"] < 4 else "R"),
                "roi": bounds,
                "lab": cell["baseline_normalized_post_camera_relative_lab"],
                "noise": {
                    "sample_count": noise["sample_count"],
                    "lstar_mad": noise["lstar_mad"],
                    "lstar_ci95_half_width": noise["lstar_ci95_half_width"],
                    "delta_e00_mad": noise["delta_e00_to_median_mad"],
                    "delta_e00_ci95_half_width": noise[
                        "delta_e00_to_median_ci95_half_width"
                    ],
                },
                "quality_pass": max(cell["quality"].values())
                <= archive["measurement"]["maximum_allowed_roi_high_clip_fraction"],
                "single_pixel_uniform": not archive["target_state"]["spatial_dither"],
                "measurement_evidence_sha256": P2_SHA,
            }
        )
    # Validate everything before reserving new output names.
    suite.analyze_observations(data)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "p2-observations.json", data)
    report = checked_analysis(data, output / "p2-observations.json")
    report.pop("integrity")
    report["historical_report_diagnostic_pairs"] = deepcopy(
        archive["summaries"]["same_hue_lightness_candidates"]
    )
    report["historical_cross_controller_result"] = deepcopy(
        archive["summaries"]["cross_controller_v1_preliminary"]
    )
    report["historical_source_refresh_count"] = 1
    report["new_refresh_count"] = 0
    report["source_report_rewritten"] = False
    report["method_difference"] = (
        "new suite requires position gate and pair separation in all quadrants; historical median-only diagnostic pairs are retained separately"
    )
    write_new(output / "p2-screen-report.json", attach_integrity(report))
    return {
        "output": str(output),
        "verified_archive_files": len(evidence),
        "groups": [
            {
                k: g[k]
                for k in (
                    "controller",
                    "candidate_level_count",
                    "requested_level_screen_pass",
                )
            }
            for g in report["groups"]
        ],
        "verdict": report["verdict"],
        "qualified_count": 0,
        "new_refresh_count": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "review-p2"):
        command = commands.add_parser(name)
        command.add_argument("--output-dir", required=True, type=Path)
    command = commands.add_parser("analyze")
    command.add_argument("--input", required=True, type=Path)
    command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_package(args.output_dir)
        elif args.command == "review-p2":
            result = review_p2(args.output_dir)
        else:
            data = json.loads(args.input.read_text(encoding="utf-8"))
            result = checked_analysis(data, args.input)
            write_new(args.output, result)
            result = {
                "output": str(args.output),
                "verdict": result["verdict"],
                "qualified_count": 0,
            }
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        StaticPhotoContractError,
    ) as error:
        print(
            json.dumps(
                {
                    "verdict": "FAIL_STOP",
                    "error": str(error),
                    "hardware_accessed": False,
                    "qualified_count": 0,
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
