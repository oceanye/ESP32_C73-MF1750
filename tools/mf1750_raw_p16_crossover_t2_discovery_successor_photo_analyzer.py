#!/usr/bin/env python3
"""Analyze one fresh T2 coarse-discovery capture without widening legacy gates.

The image geometry and cell sampling implementation are deliberately reused
from the frozen position-balanced analyzer.  This adapter accepts only the
fresh discovery-successor campaign, contract, action, firmware, frame, DTM,
role, and terminal result.  Its output is camera-relative screening evidence;
it never qualifies a colour and never changes the consumed formal T1 gate.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as legacy,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as pack,
)


SCHEMA_VERSION = 1
KIND = (
    "mf1750-raw-p16-crossover-t2-ca-coarse-discovery-successor-single-frame-analysis-v1"
)
INTEGRITY_ALGORITHM = legacy.INTEGRITY_ALGORITHM
STAGE = pack.STAGE

CrossoverDiscoveryPhotoAnalysisError = legacy.CrossoverPhotoAnalysisError


def _runtime_action(expected_action: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact successor subset emitted by the reviewed host runner."""

    return legacy._runtime_action(expected_action)  # noqa: SLF001


def _validate_action(action_root: Mapping[str, Any]) -> dict[str, Any]:
    """Require the fresh successor action and reject the frozen T2 identity."""

    report = pack.build_report()
    expected_action = report["actions"][0]
    cfg = pack.CONFIG
    action = legacy.base._mapping(  # noqa: SLF001
        action_root.get("action"), label="action result.action"
    )
    terminal = legacy.base._mapping(  # noqa: SLF001
        action_root.get("terminal_report"), label="action result.terminal_report"
    )
    for field, expected_value in _runtime_action(expected_action).items():
        if action.get(field) != expected_value:
            raise CrossoverDiscoveryPhotoAnalysisError(
                f"RAW-P16 T2 discovery successor action {field} differs"
            )

    if (
        action_root.get("kind") != f"mf1750-ec5-{cfg.route_slug}-result"
        or action_root.get("outcome") != "complete_pass"
        or action_root.get("visible_refreshes") != 1
        or action_root.get("firmware_sha256") != pack.ARTIFACTS[STAGE]["bin_sha256"]
    ):
        raise CrossoverDiscoveryPhotoAnalysisError(
            "RAW-P16 T2 discovery successor result identity differs"
        )

    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "build_tag": cfg.build_tag,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "ordinal": 1,
        "role": expected_action["role"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
    }
    for field, expected_value in terminal_expected.items():
        if terminal.get(field) != expected_value:
            raise CrossoverDiscoveryPhotoAnalysisError(
                f"RAW-P16 T2 discovery successor terminal {field} differs"
            )
    driver = legacy.base._mapping(terminal.get("driver"), label="terminal.driver")  # noqa: SLF001
    if (
        driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("failure_stage") != "none"
    ):
        raise CrossoverDiscoveryPhotoAnalysisError(
            "RAW-P16 T2 discovery successor terminal driver evidence differs"
        )

    geometry = report["contract"]["geometry"]
    if (
        geometry.get("grid_rows") != 4
        or geometry.get("grid_columns_per_controller") != 8
        or geometry.get("row_codes") != [list(row) for row in pack.CODE_ROWS]
        or geometry.get("samples_per_code_per_controller_per_frame") != 4
        or geometry.get("same_layout_both_controllers") is not True
        or geometry.get("spatial_dither") is not False
    ):
        raise CrossoverDiscoveryPhotoAnalysisError(
            "offline RAW-P16 T2 discovery successor 4x8 geometry differs"
        )

    return {
        "stage": STAGE,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "role": expected_action["role"],
        "frame_sha256": expected_action["frame"]["sha256"],
        "cs1_dtm_sha256": expected_action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected_action["cs2_dtm"]["sha256"],
        "firmware_sha256": pack.ARTIFACTS[STAGE]["bin_sha256"],
        "profile_id": expected_action["profile_id"],
        "global_tuple_id": expected_action["global_tuple_id"],
        "waveform_binding": expected_action["waveform_binding"],
        "global_header": expected_action["global_header"],
    }


def _comparison_projection(
    *,
    action_identity: Mapping[str, Any],
    camera_lock: Mapping[str, Any],
    geometry: Mapping[str, Any],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reuse the frozen CA geometry/profile projection under fresh identity."""

    projection = legacy._comparison_projection(  # noqa: SLF001
        stage="t2-ca",
        action_identity=action_identity,
        camera_lock=camera_lock,
        geometry=geometry,
        cells=cells,
    )
    projection["stage"] = STAGE
    return projection


def analyze(
    *,
    photo_path: Path,
    capture_sidecar_path: Path,
    action_result_path: Path,
    panel_corners: str | Any,
) -> dict[str, Any]:
    """Deep-validate and analyze one successor T2 capture, entirely offline."""

    photo_path = Path(photo_path).resolve()
    capture_sidecar_path = Path(capture_sidecar_path).resolve()
    action_result_path = Path(action_result_path).resolve()
    try:
        capture_root = camera.validate_capture_evidence(capture_sidecar_path)
    except camera.CameraCaptureEvidenceError as error:
        raise CrossoverDiscoveryPhotoAnalysisError(
            f"formal capture evidence rejected: {error}"
        ) from error
    camera_lock = legacy.base._validate_fixed_capture(capture_root)  # noqa: SLF001
    action_payload, action_root = legacy.base._load_json(  # noqa: SLF001
        action_result_path, label="action result"
    )
    action_identity = _validate_action(action_root)

    sidecar_action = legacy.base._mapping(  # noqa: SLF001
        capture_root.get("action_result"), label="capture.action_result"
    )
    sidecar_photo = legacy.base._mapping(  # noqa: SLF001
        capture_root.get("photo"), label="capture.photo"
    )
    resolved_action = (
        capture_sidecar_path.parent / str(sidecar_action.get("path"))
    ).resolve()
    resolved_photo = (
        capture_sidecar_path.parent / str(sidecar_photo.get("path"))
    ).resolve()
    if resolved_action != action_result_path or resolved_photo != photo_path:
        raise CrossoverDiscoveryPhotoAnalysisError(
            "explicit photo/action paths differ from formal capture bindings"
        )
    photo_payload = legacy.base._read_stable_regular(  # noqa: SLF001
        photo_path, label="formal photo"
    )
    if (
        sidecar_photo.get("sha256") != legacy.base._sha256_bytes(photo_payload)  # noqa: SLF001
        or sidecar_action.get("file_sha256")
        != legacy.base._sha256_bytes(action_payload)  # noqa: SLF001
    ):
        raise CrossoverDiscoveryPhotoAnalysisError(
            "formal successor photo/action SHA-256 binding differs"
        )
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if capture_root.get(field) != action_identity[field]:
            raise CrossoverDiscoveryPhotoAnalysisError(
                f"capture sidecar {field} differs from exact successor binding"
            )

    rgb = legacy.base._decode_rgb(photo_payload)  # noqa: SLF001
    homography, geometry = legacy._fit_panel_homography(  # noqa: SLF001
        panel_corners, photo_width=rgb.shape[1], photo_height=rgb.shape[0]
    )
    cells = [
        legacy.base._sample_cell(rgb, homography, cell)  # noqa: SLF001
        for cell in legacy._all_logical_cells()  # noqa: SLF001
    ]
    summary = legacy._position_summary(cells)  # noqa: SLF001
    projection = _comparison_projection(
        action_identity=action_identity,
        camera_lock=camera_lock,
        geometry=geometry,
        cells=cells,
    )
    sidecar_payload = legacy.base._read_stable_regular(  # noqa: SLF001
        capture_sidecar_path, label="capture sidecar"
    )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "stage": STAGE,
        "campaign_id": action_identity["campaign_id"],
        "contract_id": action_identity["contract_id"],
        "action_id": action_identity["action_id"],
        "frame_sha256": action_identity["frame_sha256"],
        "cs1_dtm_sha256": action_identity["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action_identity["cs2_dtm_sha256"],
        "source_evidence": {
            "photo": {
                "path": str(photo_path),
                "bytes": len(photo_payload),
                "sha256": legacy.base._sha256_bytes(photo_payload),  # noqa: SLF001
                "width": rgb.shape[1],
                "height": rgb.shape[0],
            },
            "capture_sidecar": {
                "path": str(capture_sidecar_path),
                "bytes": len(sidecar_payload),
                "sha256": legacy.base._sha256_bytes(sidecar_payload),  # noqa: SLF001
                "canonical_integrity_sha256": legacy.base._sha256(  # noqa: SLF001
                    legacy.base._mapping(  # noqa: SLF001
                        capture_root.get("integrity"), label="capture.integrity"
                    ).get("sha256"),
                    label="capture.integrity.sha256",
                ),
            },
            "action_result": {
                "path": str(action_result_path),
                "bytes": len(action_payload),
                "sha256": legacy.base._sha256_bytes(action_payload),  # noqa: SLF001
                "canonical_integrity_sha256": legacy.base._sha256(  # noqa: SLF001
                    legacy.base._mapping(  # noqa: SLF001
                        action_root.get("integrity"), label="action.integrity"
                    ).get("sha256"),
                    label="action.integrity.sha256",
                ),
            },
        },
        "action_binding": action_identity,
        "camera_lock": camera_lock,
        "layout": {
            "logical_width": legacy.LOGICAL_WIDTH,
            "logical_height": legacy.LOGICAL_HEIGHT,
            "controller_count": legacy.CONTROLLER_COUNT,
            "controller_width": legacy.CONTROLLER_WIDTH,
            "rows_per_controller": 4,
            "columns_per_controller": 8,
            "row_codes": [list(row) for row in pack.CODE_ROWS],
            "samples_per_code_per_controller": 4,
            "same_layout_both_controllers": True,
            "spatial_dither": False,
            "legacy_endpoint_4x2_analyzer_used": False,
        },
        "geometry": geometry,
        "measurement_method": {
            "rgb_statistic": "per-channel median over projected inner 60% polygon",
            "spread_statistic": "per-channel median absolute deviation",
            "lab_derivation": "camera JPEG RGB interpreted as sRGB D65/2deg Lab",
            "delta_e": "CIEDE2000 plus Delta-E76",
            "physical_colour_calibrated": False,
            "absolute_colour_measurement": False,
            "repeatability_measurement": False,
        },
        "cells": cells,
        "position_balanced_summary": summary,
        "comparison_projection": projection,
        "classification": {
            "state": "CAMERA_RELATIVE_DISCOVERY_SUCCESSOR_SCREENING_ONLY",
            "camera_relative_candidates_only": True,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
            "formal_gate_evaluated": False,
            "formal_gate_changed": False,
            "cross_stage_equivalence_proven": False,
        },
        "hardware_io_performed_by_analyzer": False,
        "camera_access_performed_by_analyzer": False,
        "visible_refresh_authorized": False,
        "output_write_contract": "O_EXCL",
    }
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": legacy.base._sha256_bytes(  # noqa: SLF001
            legacy.base._canonical_json(result)  # noqa: SLF001
        ),
    }
    return result


def validate_analysis(path: Path) -> tuple[dict[str, Any], bytes]:
    """Recompute an analysis from its immutable source evidence and compare it."""

    resolved = Path(path).resolve()
    payload, root = legacy.base._load_json(resolved, label="successor analysis")  # noqa: SLF001
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise CrossoverDiscoveryPhotoAnalysisError(
            "successor analysis schema or kind differs"
        )
    source = legacy.base._mapping(  # noqa: SLF001
        root.get("source_evidence"), label="analysis.source_evidence"
    )
    geometry = legacy.base._mapping(root.get("geometry"), label="analysis.geometry")  # noqa: SLF001
    recomputed = analyze(
        photo_path=Path(source["photo"]["path"]),
        capture_sidecar_path=Path(source["capture_sidecar"]["path"]),
        action_result_path=Path(source["action_result"]["path"]),
        panel_corners=geometry["supplied_panel_corners_tl_tr_br_bl"],
    )
    if recomputed != root:
        raise CrossoverDiscoveryPhotoAnalysisError(
            "successor analysis differs from full source-evidence recomputation"
        )
    return root, payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--capture-sidecar", type=Path, required=True)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument(
        "--panel-corners",
        required=True,
        help="current-photo TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze(
            photo_path=args.photo,
            capture_sidecar_path=args.capture_sidecar,
            action_result_path=args.action_result,
            panel_corners=args.panel_corners,
        )
        legacy.base._write_exclusive(args.output, report)  # noqa: SLF001
        if args.overlay_output is not None:
            payload = legacy.base._read_stable_regular(  # noqa: SLF001
                args.photo, label="formal photo"
            )
            legacy.base._write_bytes_exclusive(  # noqa: SLF001
                args.overlay_output,
                legacy._render_overlay(payload, report),  # noqa: SLF001
                label="successor crossover geometry overlay",
            )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except CrossoverDiscoveryPhotoAnalysisError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "mf1750-raw-p16-crossover-t2-discovery-analysis-error",
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
