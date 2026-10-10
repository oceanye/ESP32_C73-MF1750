#!/usr/bin/env python3
"""White-normalize three fresh T2 successor captures with clean-screened W2.

Every successor single-frame analysis is recomputed from its action, capture,
and JPEG.  The W2 white JPEG is accepted only after the independent W1-vs-W2
pixel residual evaluator passes.  This is a camera-relative screening report,
not a formal gate and not colour qualification.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_white_normalized_coarse_screen as common,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_photo_analyzer as analyzer,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_clean_white_residual as residual,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_pack,
)


SCHEMA_VERSION = 1
KIND = (
    "mf1750-raw-p16-crossover-t2-discovery-successor-white-normalized-coarse-screen-v1"
)
METHOD_ID = "t2-successor-three-frame-clean-w2-flat-field-coarse-screen-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM


class T2CoarseScreenError(RuntimeError):
    """Raised when successor evidence cannot be recomputed exactly."""


def _alignment(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "instance_id": capture["camera"]["instance_id"],
        "mount_id": capture["coverage"]["mount_id"],
        "requested_settings": capture["camera"]["requested_settings"],
        "effective_settings_before_frame": capture["camera"][
            "effective_settings_before_frame"
        ],
        "effective_settings_after_frame": capture["camera"][
            "effective_settings_after_frame"
        ],
        "photo_width": capture["photo"]["width"],
        "photo_height": capture["photo"]["height"],
    }


def _validate_alignments(values: Sequence[Mapping[str, Any]]) -> None:
    if len(values) != 4:
        raise T2CoarseScreenError("alignment requires three T2 captures and one W2")
    first = dict(values[0])
    for index, value in enumerate(values[1:], 2):
        if dict(value) != first:
            raise T2CoarseScreenError(
                f"T2/W2 capture alignment fingerprint {index} differs"
            )


def _deep_t2(path: Path, *, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        root, payload = analyzer.validate_analysis(Path(path))
    except analyzer.CrossoverDiscoveryPhotoAnalysisError as error:
        raise T2CoarseScreenError(f"T2 analysis {index} rejected: {error}") from error
    source = root["source_evidence"]
    capture_path = Path(source["capture_sidecar"]["path"])
    try:
        capture = camera.validate_capture_evidence(capture_path)
    except camera.CameraCaptureEvidenceError as error:
        raise T2CoarseScreenError(
            f"T2 capture {index} deep validation failed: {error}"
        ) from error
    binding = {
        "analysis_path": Path(path).resolve().as_posix(),
        "analysis_bytes": len(payload),
        "analysis_file_sha256": strict.sha256_bytes(payload),
        "analysis_canonical_integrity_sha256": root["integrity"]["sha256"],
        "stage": root["stage"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "action_id": root["action_id"],
        "frame_sha256": root["frame_sha256"],
        "source_evidence": source,
        "capture_alignment": _alignment(capture),
    }
    return root, binding


def _normalized_t2_cell(
    t2_cell: Mapping[str, Any], white_cell: Mapping[str, Any]
) -> dict[str, Any]:
    result = common._normalized_cell(t2_cell, white_cell)  # noqa: SLF001
    if "t1_rgb_median" in result:
        result["t2_rgb_median"] = result.pop("t1_rgb_median")
    return result


def screen(
    t2_analyses: Sequence[Path], w2_analysis: Path, w2_residual: Path
) -> dict[str, Any]:
    """Build a sealed T2+W2 coarse screen without camera or device I/O."""

    if (
        len(t2_analyses) != 3
        or len({Path(path).resolve() for path in t2_analyses}) != 3
    ):
        raise T2CoarseScreenError("exactly three distinct T2 analyses are required")
    roots: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for index, path in enumerate(t2_analyses, 1):
        root, binding = _deep_t2(Path(path), index=index)
        roots.append(root)
        bindings.append(binding)

    try:
        residual_root, residual_payload = residual.validate_report(Path(w2_residual))
    except residual.WhiteResidualScreenError as error:
        raise T2CoarseScreenError(f"W2 residual report rejected: {error}") from error
    if residual_root["summary"]["classification"] != "PASS":
        raise T2CoarseScreenError(
            "W2 residual screen must PASS before W2 can normalize T2"
        )
    bound_w2_path = Path(
        residual_root["input_bindings"]["fresh_successor_w2"]["analysis_path"]
    ).resolve()
    if bound_w2_path != Path(w2_analysis).resolve():
        raise T2CoarseScreenError("explicit W2 analysis differs from residual binding")
    try:
        w2_binding, w2_rgb, _w2_root = residual._load_white(  # noqa: SLF001
            Path(w2_analysis), stage=w2_pack.STAGE
        )
    except residual.WhiteResidualScreenError as error:
        raise T2CoarseScreenError(f"W2 analysis rejected: {error}") from error

    _validate_alignments(
        [
            *(binding["capture_alignment"] for binding in bindings),
            w2_binding["capture_alignment"],
        ]
    )
    _cv2, np = analyzer.legacy.base._import_cv()  # noqa: SLF001
    normalized_frames: list[dict[str, Any]] = []
    for index, (root, binding) in enumerate(zip(roots, bindings, strict=True), 1):
        homography = np.asarray(
            root["geometry"]["homography_logical_to_current_photo"],
            dtype=np.float64,
        )
        white_cells = {
            (
                cell["controller"],
                cell["row"],
                cell["column"],
            ): analyzer.legacy.base._sample_cell(  # noqa: SLF001,E501
                w2_rgb, homography, cell
            )
            for cell in analyzer.legacy._all_logical_cells()  # noqa: SLF001
        }
        cells = [
            _normalized_t2_cell(
                cell,
                white_cells[(cell["controller"], cell["row"], cell["column"])],
            )
            for cell in root["cells"]
        ]
        normalized_frames.append(
            {
                "frame_index": index,
                "analysis_file_sha256": binding["analysis_file_sha256"],
                "homography_logical_to_w2_photo": root["geometry"][
                    "homography_logical_to_current_photo"
                ],
                "cells": cells,
            }
        )

    groups = [
        common._group_result(  # noqa: SLF001
            normalized_frames, controller=controller, code=code
        )
        for controller in range(2)
        for code in range(8)
    ]
    counts = Counter(group["classification"] for group in groups)
    ready = counts["PASS"] == 16
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "screening_only": True,
        "formal_gate_evaluated": False,
        "formal_gate_changed": False,
        "qualified_colour_count": 0,
        "coarse_profile_comparison_ready": ready,
        "input_bindings": {
            "t2_successor_analyses": bindings,
            "w2_successor_analysis": w2_binding,
            "w2_clean_white_residual": {
                "path": Path(w2_residual).resolve().as_posix(),
                "bytes": len(residual_payload),
                "file_sha256": strict.sha256_bytes(residual_payload),
                "canonical_integrity_sha256": residual_root["integrity"]["sha256"],
                "classification": residual_root["summary"]["classification"],
            },
        },
        "normalization_contract": {
            "formula": "clip(220*T2_RGB/W2_RGB,0,255)",
            "target_rgb": common.NORMALIZATION_TARGET_RGB,
            "white_reference_min_lstar": common.WHITE_REFERENCE_MIN_LSTAR,
            "white_sampling_geometry": "EACH_T2_HOMOGRAPHY_APPLIED_TO_W2_PHOTO",
            "normalized_rgb_quantization_before_lab": "ROUND_TO_UINT8",
            "lab_space": "sRGB_D65_2DEG_CIE_LAB",
            "w2_residual_algorithmic_pass_required": True,
            "external_post_capture_verdict_used_as_white_algorithm": False,
            "absolute_colour_calibrated": False,
        },
        "threshold_contract": {
            "valid_positions_per_group_per_frame_minimum": common.VALID_POSITIONS_PER_FRAME,
            "valid_frames_per_group_minimum": common.VALID_FRAMES_PER_GROUP,
            "dominant_bucket_positions_of_nominal_four_minimum": common.DOMINANT_BUCKET_POSITIONS,
            "position_pass_maximum_de00": common.POSITION_PASS_MAX_DE00,
            "position_review_maximum_de00": common.POSITION_REVIEW_MAX_DE00,
            "temporal_pass_maximum_de76": common.TEMPORAL_PASS_MAX_DE76,
            "temporal_review_maximum_de76": common.TEMPORAL_REVIEW_MAX_DE76,
            "automatic_threshold_relaxation": False,
        },
        "group_results": groups,
        "summary": {
            "state": (
                "PASS_T2_SUCCESSOR_COARSE_SCREEN"
                if ready
                else "T2_SUCCESSOR_COARSE_SCREEN_NOT_ALL_PASS"
            ),
            "group_count": len(groups),
            "classification_counts": {
                state: counts[state] for state in ("PASS", "REVIEW", "FAIL")
            },
            "maximum_position_de00": common._maximum_optional(  # noqa: SLF001
                groups, "position_maximum_de00"
            ),
            "maximum_temporal_center_de76": common._maximum_optional(  # noqa: SLF001
                groups, "temporal_center_maximum_de76"
            ),
            "coarse_profile_comparison_ready": ready,
            "screening_only": True,
            "formal_gate_evaluated": False,
            "formal_gate_changed": False,
            "qualified_colour_count": 0,
        },
        "evidence_boundaries": {
            "camera_relative_flat_field_screen_only": True,
            "w2_is_not_a_calibrated_white_standard": True,
            "w2_clean_white_residual_algorithm_required": True,
            "formal_t1_gate_unchanged": True,
            "device_io_performed": False,
            "network_accessed": False,
            "camera_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_report(path: Path) -> tuple[dict[str, Any], bytes]:
    """Deep-recompute a T2 coarse screen from its source evidence."""

    try:
        payload, root = strict._load_json(Path(path), label="T2 coarse screen")  # noqa: SLF001
        strict._verify_integrity(root, label="T2 coarse screen")  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T2CoarseScreenError(str(error)) from error
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise T2CoarseScreenError("T2 coarse screen schema or kind differs")
    bindings = root["input_bindings"]
    recomputed = screen(
        [Path(item["analysis_path"]) for item in bindings["t2_successor_analyses"]],
        Path(bindings["w2_successor_analysis"]["analysis_path"]),
        Path(bindings["w2_clean_white_residual"]["path"]),
    )
    if recomputed != root:
        raise T2CoarseScreenError(
            "T2 coarse screen differs from source-evidence recomputation"
        )
    return root, payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--t2-analysis", type=Path, nargs=3, required=True)
    parser.add_argument("--w2-analysis", type=Path, required=True)
    parser.add_argument("--w2-residual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = screen(args.t2_analysis, args.w2_analysis, args.w2_residual)
        payload = common._serialized(report)  # noqa: SLF001
        common.write_exclusive(args.output, payload)
    except (T2CoarseScreenError, common.CoarseScreenError) as error:
        print(f"RAW-P16 T2 successor coarse-screen error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return 0 if report["coarse_profile_comparison_ready"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
