#!/usr/bin/env python3
"""Screen fresh W2 for retained atlas/stripe residuals against locked W1.

This evaluator reads pixels; it does not reuse the operator-authored verdict in
the generic post-capture record as its result.  Both source actions, captures,
photos, the 48MP camera instance, mount, requested/effective settings, and
dimensions are deep-bound before W1 and W2 are compared through one explicit
current-photo panel homography.  The result is screening-only and never claims
an absolute or calibrated white.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_camera_post_capture_analysis as post  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_pack,
)


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-w2-discovery-successor-clean-white-residual-screen-v1"
METHOD_ID = "locked-w1-vs-fresh-w2-atlas-grid-and-horizontal-stripe-screen-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

ATLAS_P95_PASS_DE00 = 6.0
ATLAS_P95_REVIEW_DE00 = 10.0
ATLAS_MAX_PASS_DE00 = 10.0
ATLAS_MAX_REVIEW_DE00 = 16.0
GRID_P95_PASS_DE00 = 6.0
GRID_P95_REVIEW_DE00 = 10.0
STRIPE_ROW_MEDIAN_PASS_DE00 = 4.0
STRIPE_ROW_MEDIAN_REVIEW_DE00 = 8.0
GRID_COLUMNS = 24
GRID_ROWS = 12
GRID_MARGIN_X = 24.0
GRID_MARGIN_Y = 24.0


class WhiteResidualScreenError(RuntimeError):
    """Raised when evidence is invalid or the report cannot be sealed safely."""


def _require_equal(observed: Any, expected: Any, *, label: str) -> None:
    if observed != expected:
        raise WhiteResidualScreenError(f"{label} differs")


def _expected_white(stage: str) -> dict[str, Any]:
    if stage == "w1-after-t1":
        matches = [
            dict(item)
            for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
            if item["stage"] == stage
        ]
        if len(matches) != 1:
            raise WhiteResidualScreenError("exact W1 camera binding is unavailable")
        return matches[0]
    if stage != w2_pack.STAGE:
        raise WhiteResidualScreenError(f"unknown white stage {stage!r}")
    report = w2_pack.build_white_report()
    action = report["action"]
    return {
        "stage": w2_pack.STAGE,
        "profile_id": "WF23_25",
        "campaign_id": w2_pack.CONFIG.campaign_id,
        "test_id": w2_pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "build_tag": w2_pack.CONFIG.build_tag,
        "firmware_sha256": w2_pack.WHITE_ARTIFACTS[w2_pack.STAGE]["bin_sha256"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR",
        "marker": w2_pack.marker(),
    }


def _capture_alignment(capture: Mapping[str, Any]) -> dict[str, Any]:
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


def _resolve_binding_path(
    analysis_path: Path, binding: Mapping[str, Any], *, label: str
) -> Path:
    value = binding.get("path")
    if not isinstance(value, str) or not value:
        raise WhiteResidualScreenError(f"{label}.path is invalid")
    candidate = (analysis_path.parent / value).resolve()
    try:
        candidate.relative_to(analysis_path.parent.resolve())
    except ValueError as error:
        raise WhiteResidualScreenError(f"{label}.path escapes analysis tree") from error
    return candidate


def _load_white(
    analysis_path: Path, *, stage: str
) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    resolved = Path(analysis_path).resolve()
    try:
        root = post.validate_post_capture_analysis(resolved)
    except post.PostCaptureAnalysisError as error:
        raise WhiteResidualScreenError(
            f"{stage} post-capture analysis deep validation failed: {error}"
        ) from error
    expected = _expected_white(stage)
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
    ):
        _require_equal(root.get(field), expected[field], label=f"{stage} {field}")
    coverage = root.get("analysis", {}).get("coverage", {})
    if (
        coverage.get("capture_scope") != "full_panel"
        or coverage.get("full_panel_visible") is not True
    ):
        raise WhiteResidualScreenError(f"{stage} does not bind a full-panel capture")

    bindings = root["bindings"]
    capture_path = _resolve_binding_path(
        resolved, bindings["capture_sidecar"], label=f"{stage} capture"
    )
    try:
        capture = camera.validate_capture_evidence(capture_path)
    except camera.CameraCaptureEvidenceError as error:
        raise WhiteResidualScreenError(
            f"{stage} capture deep validation failed: {error}"
        ) from error
    photo_path = _resolve_binding_path(
        resolved, bindings["photo"], label=f"{stage} photo"
    )
    try:
        photo_payload = strict._read_stable_regular(  # noqa: SLF001
            photo_path, label=f"{stage} photo"
        )
    except strict.CrossoverProfileComparisonError as error:
        raise WhiteResidualScreenError(str(error)) from error
    _require_equal(
        len(photo_payload), bindings["photo"]["bytes"], label=f"{stage} photo bytes"
    )
    _require_equal(
        strict.sha256_bytes(photo_payload),
        bindings["photo"]["sha256"],
        label=f"{stage} photo SHA-256",
    )
    try:
        rgb = geometry.base._decode_rgb(photo_payload)  # noqa: SLF001
    except geometry.CrossoverPhotoAnalysisError as error:
        raise WhiteResidualScreenError(
            f"{stage} photo decode failed: {error}"
        ) from error
    alignment = _capture_alignment(capture)
    _require_equal(rgb.shape[1], alignment["photo_width"], label=f"{stage} width")
    _require_equal(rgb.shape[0], alignment["photo_height"], label=f"{stage} height")
    analysis_payload = strict._read_stable_regular(  # noqa: SLF001
        resolved, label=f"{stage} post analysis"
    )
    binding = {
        "stage": stage,
        "analysis_path": resolved.as_posix(),
        "analysis_bytes": len(analysis_payload),
        "analysis_file_sha256": strict.sha256_bytes(analysis_payload),
        "analysis_canonical_integrity_sha256": root["integrity"]["sha256"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "action_id": root["action_id"],
        "capture_sidecar": dict(bindings["capture_sidecar"]),
        "photo": {
            "path": photo_path.as_posix(),
            "bytes": len(photo_payload),
            "file_sha256": strict.sha256_bytes(photo_payload),
            "width": int(rgb.shape[1]),
            "height": int(rgb.shape[0]),
        },
        "capture_alignment": alignment,
        "external_post_capture_verdict": root["analysis"].get("verdict"),
        "external_post_capture_verdict_used_for_residual_classification": False,
    }
    return binding, rgb, root


def _p95(values: Sequence[float]) -> float:
    if not values:
        raise WhiteResidualScreenError("cannot calculate P95 of an empty set")
    ordered = sorted(float(value) for value in values)
    position = 0.95 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _classify(value: float, *, pass_max: float, review_max: float) -> str:
    if value <= pass_max:
        return "PASS"
    if value <= review_max:
        return "REVIEW"
    return "FAIL"


def _sample_pair(
    w1_rgb: Any, w2_rgb: Any, homography: Any, cell: Mapping[str, Any]
) -> dict[str, Any]:
    w1 = geometry.base._sample_cell(w1_rgb, homography, cell)  # noqa: SLF001
    w2 = geometry.base._sample_cell(w2_rgb, homography, cell)  # noqa: SLF001
    de00 = float(
        delta_e_ciede2000(
            w1["camera_relative_lab_d65_from_rgb_median"],
            w2["camera_relative_lab_d65_from_rgb_median"],
        )
    )
    return {
        "sample_id": cell["cell_id"],
        "controller": cell.get("controller"),
        "row": cell["row"],
        "column": cell["column"],
        "code": cell.get("code"),
        "w1_rgb_median": w1["robust_rgb_median"],
        "w2_rgb_median": w2["robust_rgb_median"],
        "w1_lab": w1["camera_relative_lab_d65_from_rgb_median"],
        "w2_lab": w2["camera_relative_lab_d65_from_rgb_median"],
        "delta_e00_w1_to_w2": round(de00, 9),
    }


def _grid_cells() -> list[dict[str, Any]]:
    width = (geometry.LOGICAL_WIDTH - 2.0 * GRID_MARGIN_X) / GRID_COLUMNS
    height = (geometry.LOGICAL_HEIGHT - 2.0 * GRID_MARGIN_Y) / GRID_ROWS
    result = []
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            x = GRID_MARGIN_X + column * width
            y = GRID_MARGIN_Y + row * height
            result.append(
                {
                    "cell_id": f"GRID-R{row}-C{column}",
                    "controller": None,
                    "row": row,
                    "column": column,
                    "code": None,
                    "logical_bounds": [x, y, width, height],
                    "logical_center": [x + width / 2.0, y + height / 2.0],
                }
            )
    return result


def evaluate(
    w1_analysis: Path, w2_analysis: Path, *, panel_corners: str | Any
) -> dict[str, Any]:
    """Compare fresh W2 pixels with locked pre-white W1 pixels."""

    w1_binding, w1_rgb, _w1_root = _load_white(Path(w1_analysis), stage="w1-after-t1")
    w2_binding, w2_rgb, _w2_root = _load_white(Path(w2_analysis), stage=w2_pack.STAGE)
    if w1_binding["capture_alignment"] != w2_binding["capture_alignment"]:
        raise WhiteResidualScreenError(
            "W1/W2 camera instance, mount, settings, or dimensions differ"
        )
    homography, panel_geometry = geometry._fit_panel_homography(  # noqa: SLF001
        panel_corners,
        photo_width=int(w2_rgb.shape[1]),
        photo_height=int(w2_rgb.shape[0]),
    )

    atlas_samples = [
        _sample_pair(w1_rgb, w2_rgb, homography, cell)
        for cell in geometry._all_logical_cells()  # noqa: SLF001
    ]
    grid_samples = [
        _sample_pair(w1_rgb, w2_rgb, homography, cell) for cell in _grid_cells()
    ]
    atlas_values = [item["delta_e00_w1_to_w2"] for item in atlas_samples]
    grid_values = [item["delta_e00_w1_to_w2"] for item in grid_samples]
    row_medians = [
        statistics.median(
            item["delta_e00_w1_to_w2"] for item in grid_samples if item["row"] == row
        )
        for row in range(GRID_ROWS)
    ]
    atlas_p95 = _p95(atlas_values)
    atlas_max = max(atlas_values)
    grid_p95 = _p95(grid_values)
    stripe_max = max(row_medians)
    components = {
        "atlas_cell_p95": _classify(
            atlas_p95,
            pass_max=ATLAS_P95_PASS_DE00,
            review_max=ATLAS_P95_REVIEW_DE00,
        ),
        "atlas_cell_maximum": _classify(
            atlas_max,
            pass_max=ATLAS_MAX_PASS_DE00,
            review_max=ATLAS_MAX_REVIEW_DE00,
        ),
        "full_panel_grid_p95": _classify(
            grid_p95,
            pass_max=GRID_P95_PASS_DE00,
            review_max=GRID_P95_REVIEW_DE00,
        ),
        "horizontal_row_median_maximum": _classify(
            stripe_max,
            pass_max=STRIPE_ROW_MEDIAN_PASS_DE00,
            review_max=STRIPE_ROW_MEDIAN_REVIEW_DE00,
        ),
    }
    ranks = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
    classification = max(components.values(), key=ranks.get)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "screening_only": True,
        "absolute_white_proven": False,
        "physical_colour_calibrated": False,
        "qualified_colour_count": 0,
        "formal_gate_evaluated": False,
        "formal_gate_changed": False,
        "input_bindings": {
            "locked_pre_white_w1": w1_binding,
            "fresh_successor_w2": w2_binding,
        },
        "geometry": panel_geometry,
        "threshold_contract": {
            "atlas_cell_p95_pass_maximum_de00": ATLAS_P95_PASS_DE00,
            "atlas_cell_p95_review_maximum_de00": ATLAS_P95_REVIEW_DE00,
            "atlas_cell_maximum_pass_maximum_de00": ATLAS_MAX_PASS_DE00,
            "atlas_cell_maximum_review_maximum_de00": ATLAS_MAX_REVIEW_DE00,
            "grid_p95_pass_maximum_de00": GRID_P95_PASS_DE00,
            "grid_p95_review_maximum_de00": GRID_P95_REVIEW_DE00,
            "stripe_row_median_pass_maximum_de00": STRIPE_ROW_MEDIAN_PASS_DE00,
            "stripe_row_median_review_maximum_de00": STRIPE_ROW_MEDIAN_REVIEW_DE00,
            "automatic_threshold_relaxation": False,
        },
        "atlas_samples": atlas_samples,
        "full_panel_grid": {
            "rows": GRID_ROWS,
            "columns": GRID_COLUMNS,
            "samples": grid_samples,
            "horizontal_row_median_delta_e00": [
                round(value, 9) for value in row_medians
            ],
        },
        "summary": {
            "classification": classification,
            "component_classifications": components,
            "atlas_cell_p95_delta_e00": round(atlas_p95, 9),
            "atlas_cell_maximum_delta_e00": round(atlas_max, 9),
            "full_panel_grid_p95_delta_e00": round(grid_p95, 9),
            "horizontal_row_median_maximum_delta_e00": round(stripe_max, 9),
            "atlas_residual_candidate_detected": (
                components["atlas_cell_p95"] != "PASS"
                or components["atlas_cell_maximum"] != "PASS"
            ),
            "horizontal_stripe_candidate_detected": (
                components["horizontal_row_median_maximum"] != "PASS"
            ),
            "large_colour_difference_candidate_detected": (
                components["full_panel_grid_p95"] != "PASS"
            ),
            "external_post_capture_verdict_used": False,
        },
        "evidence_boundaries": {
            "same_locked_48mp_camera_required": True,
            "same_mount_settings_and_dimensions_required": True,
            "explicit_current_photo_panel_corners_required": True,
            "w1_is_not_a_calibrated_white_standard": True,
            "screening_only": True,
            "absolute_white_claimed": False,
            "hardware_io_performed": False,
            "camera_accessed": False,
            "network_accessed": False,
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
    """Deep-recompute a residual report from its two source analyses."""

    try:
        payload, root = strict._load_json(Path(path), label="W2 residual report")  # noqa: SLF001
        strict._verify_integrity(root, label="W2 residual report")  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise WhiteResidualScreenError(str(error)) from error
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise WhiteResidualScreenError("W2 residual report schema or kind differs")
    bindings = root.get("input_bindings", {})
    recomputed = evaluate(
        Path(bindings["locked_pre_white_w1"]["analysis_path"]),
        Path(bindings["fresh_successor_w2"]["analysis_path"]),
        panel_corners=root["geometry"]["supplied_panel_corners_tl_tr_br_bl"],
    )
    if recomputed != root:
        raise WhiteResidualScreenError(
            "W2 residual report differs from source-evidence recomputation"
        )
    return root, payload


def _serialize(report: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise WhiteResidualScreenError(
            f"refusing to overwrite output: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--w1-analysis", type=Path, required=True)
    parser.add_argument("--w2-analysis", type=Path, required=True)
    parser.add_argument(
        "--panel-corners",
        required=True,
        help="current W2 photo TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = evaluate(
            args.w1_analysis, args.w2_analysis, panel_corners=args.panel_corners
        )
        payload = _serialize(report)
        _write_exclusive(args.output, payload)
    except WhiteResidualScreenError as error:
        print(f"RAW-P16 fresh W2 residual-screen error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return {"PASS": 0, "REVIEW": 3, "FAIL": 4}[report["summary"]["classification"]]


if __name__ == "__main__":
    raise SystemExit(main())
