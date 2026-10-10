#!/usr/bin/env python3
"""Screen fresh W3 against its exposure=-3 pre-T2-V2 W2 reference.

This is the V2-only sibling of the frozen W1/W2 residual screen.  It keeps the
same sampling grid and every numeric threshold, but accepts only the exact
48MP exposure=-3 camera contract and the fresh T2-V2/W3 identities.  It is an
offline pixel evaluator and performs no hardware or camera I/O.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_camera_post_capture_analysis as post  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import mf1750_raw_p16_crossover_v2_camera_lock as camera_lock  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_clean_white_residual as frozen,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)


SCHEMA_VERSION = 1
KIND = (
    "mf1750-raw-p16-crossover-w3-discovery-successor-v2-clean-white-residual-screen-v1"
)
METHOD_ID = "exact-exp3-pre-w2-vs-fresh-w3-atlas-grid-and-stripe-screen-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

# These aliases intentionally make threshold parity with the frozen evaluator
# executable and testable instead of silently restating looser values.
ATLAS_P95_PASS_DE00 = frozen.ATLAS_P95_PASS_DE00
ATLAS_P95_REVIEW_DE00 = frozen.ATLAS_P95_REVIEW_DE00
ATLAS_MAX_PASS_DE00 = frozen.ATLAS_MAX_PASS_DE00
ATLAS_MAX_REVIEW_DE00 = frozen.ATLAS_MAX_REVIEW_DE00
GRID_P95_PASS_DE00 = frozen.GRID_P95_PASS_DE00
GRID_P95_REVIEW_DE00 = frozen.GRID_P95_REVIEW_DE00
STRIPE_ROW_MEDIAN_PASS_DE00 = frozen.STRIPE_ROW_MEDIAN_PASS_DE00
STRIPE_ROW_MEDIAN_REVIEW_DE00 = frozen.STRIPE_ROW_MEDIAN_REVIEW_DE00
GRID_COLUMNS = frozen.GRID_COLUMNS
GRID_ROWS = frozen.GRID_ROWS
EXPECTED_THRESHOLD_CONTRACT = {
    "atlas_cell_p95_pass_maximum_de00": 6.0,
    "atlas_cell_p95_review_maximum_de00": 10.0,
    "atlas_cell_maximum_pass_maximum_de00": 10.0,
    "atlas_cell_maximum_review_maximum_de00": 16.0,
    "grid_p95_pass_maximum_de00": 6.0,
    "grid_p95_review_maximum_de00": 10.0,
    "stripe_row_median_pass_maximum_de00": 4.0,
    "stripe_row_median_review_maximum_de00": 8.0,
}


class WhiteResidualV2ScreenError(RuntimeError):
    """Raised when V2 white evidence is invalid or cannot be sealed safely."""


def _validate_contract_constants() -> None:
    observed = {
        "atlas_cell_p95_pass_maximum_de00": ATLAS_P95_PASS_DE00,
        "atlas_cell_p95_review_maximum_de00": ATLAS_P95_REVIEW_DE00,
        "atlas_cell_maximum_pass_maximum_de00": ATLAS_MAX_PASS_DE00,
        "atlas_cell_maximum_review_maximum_de00": ATLAS_MAX_REVIEW_DE00,
        "grid_p95_pass_maximum_de00": GRID_P95_PASS_DE00,
        "grid_p95_review_maximum_de00": GRID_P95_REVIEW_DE00,
        "stripe_row_median_pass_maximum_de00": STRIPE_ROW_MEDIAN_PASS_DE00,
        "stripe_row_median_review_maximum_de00": (STRIPE_ROW_MEDIAN_REVIEW_DE00),
    }
    if observed != EXPECTED_THRESHOLD_CONTRACT:
        raise WhiteResidualV2ScreenError(
            "V2 W2/W3 residual thresholds differ from the frozen contract"
        )
    if camera_lock.EXPECTED_EXPOSURE != -3.0:
        raise WhiteResidualV2ScreenError(
            "V2 W2/W3 camera contract is not exact exposure=-3"
        )


def _validate_exact_exp3_alignment(value: Mapping[str, Any], *, label: str) -> None:
    if value.get("photo_width") != 4000 or value.get("photo_height") != 3000:
        raise WhiteResidualV2ScreenError(f"{label} is not exact 4000x3000 evidence")
    for settings_name in (
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
    ):
        settings = value.get(settings_name)
        if not isinstance(settings, Mapping) or settings.get("exposure") != -3.0:
            raise WhiteResidualV2ScreenError(
                f"{label} {settings_name} is not exact exposure=-3"
            )


def _require_equal(observed: Any, expected: Any, *, label: str) -> None:
    if observed != expected:
        raise WhiteResidualV2ScreenError(f"{label} differs")


def _pack_white_identity(pack: Any) -> dict[str, Any]:
    report = pack.build_white_report()
    action = report["action"]
    return {
        "stage": pack.STAGE,
        "profile_id": "WF23_25",
        "campaign_id": pack.CONFIG.campaign_id,
        "test_id": pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "build_tag": pack.CONFIG.build_tag,
        "firmware_sha256": pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
    }


def _expected_white(stage: str) -> dict[str, Any]:
    if stage == w2_pack.STAGE:
        result = _pack_white_identity(w2_pack)
        result.update(
            {
                "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR",
                "marker": w2_pack.marker(),
            }
        )
        return result
    if stage == w3_pack.STAGE:
        result = _pack_white_identity(w3_pack)
        result.update(
            {
                "marker_role": (
                    "OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2"
                ),
                "marker": w3_pack.marker(),
            }
        )
        return result
    raise WhiteResidualV2ScreenError(f"unknown V2 white stage {stage!r}")


def _resolve_binding_path(
    analysis_path: Path, binding: Mapping[str, Any], *, label: str
) -> Path:
    try:
        return frozen._resolve_binding_path(  # noqa: SLF001
            analysis_path, binding, label=label
        )
    except frozen.WhiteResidualScreenError as error:
        raise WhiteResidualV2ScreenError(str(error)) from error


def _load_white(
    analysis_path: Path, *, stage: str
) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    resolved = Path(analysis_path).resolve()
    try:
        root = post.validate_post_capture_analysis(resolved)
    except post.PostCaptureAnalysisError as error:
        raise WhiteResidualV2ScreenError(
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
        raise WhiteResidualV2ScreenError(f"{stage} does not bind a full-panel capture")

    bindings = root["bindings"]
    capture_path = _resolve_binding_path(
        resolved, bindings["capture_sidecar"], label=f"{stage} capture"
    )
    try:
        capture = camera.validate_capture_evidence(capture_path)
        exact_camera_lock = camera_lock.validate_fixed_capture(capture)
    except (camera.CameraCaptureEvidenceError, camera_lock.V2CameraLockError) as error:
        raise WhiteResidualV2ScreenError(
            f"{stage} exact exposure=-3 capture validation failed: {error}"
        ) from error

    photo_path = _resolve_binding_path(
        resolved, bindings["photo"], label=f"{stage} photo"
    )
    try:
        photo_payload = strict._read_stable_regular(  # noqa: SLF001
            photo_path, label=f"{stage} photo"
        )
    except strict.CrossoverProfileComparisonError as error:
        raise WhiteResidualV2ScreenError(str(error)) from error
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
        raise WhiteResidualV2ScreenError(
            f"{stage} photo decode failed: {error}"
        ) from error
    alignment = frozen._capture_alignment(capture)  # noqa: SLF001
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
        "exact_camera_lock": exact_camera_lock,
        "external_post_capture_verdict": root["analysis"].get("verdict"),
        "external_post_capture_verdict_used_for_residual_classification": False,
    }
    return binding, rgb, root


def evaluate(
    w2_analysis: Path, w3_analysis: Path, *, panel_corners: str | Any
) -> dict[str, Any]:
    """Compare exact-exp3 pre-T2-V2 W2 with the fresh post-action W3."""

    _validate_contract_constants()

    w2_binding, w2_rgb, _w2_root = _load_white(Path(w2_analysis), stage=w2_pack.STAGE)
    w3_binding, w3_rgb, _w3_root = _load_white(Path(w3_analysis), stage=w3_pack.STAGE)
    _validate_exact_exp3_alignment(w2_binding["capture_alignment"], label="W2")
    _validate_exact_exp3_alignment(w3_binding["capture_alignment"], label="W3")
    if w2_binding["capture_alignment"] != w3_binding["capture_alignment"]:
        raise WhiteResidualV2ScreenError(
            "W2/W3 camera instance, mount, exact exposure=-3 settings, or dimensions differ"
        )

    homography, panel_geometry = geometry._fit_panel_homography(  # noqa: SLF001
        panel_corners,
        photo_width=int(w3_rgb.shape[1]),
        photo_height=int(w3_rgb.shape[0]),
    )
    atlas_samples = [
        frozen._sample_pair(w2_rgb, w3_rgb, homography, cell)  # noqa: SLF001
        for cell in geometry._all_logical_cells()  # noqa: SLF001
    ]
    grid_samples = [
        frozen._sample_pair(w2_rgb, w3_rgb, homography, cell)  # noqa: SLF001
        for cell in frozen._grid_cells()  # noqa: SLF001
    ]
    # Rename evidence fields so a V2 report cannot be mistaken for frozen W1/W2.
    for sample in (*atlas_samples, *grid_samples):
        for channel in ("rgb_median", "lab"):
            sample[f"pre_w2_{channel}"] = sample.pop(f"w1_{channel}")
            sample[f"post_w3_{channel}"] = sample.pop(f"w2_{channel}")
        sample["delta_e00_pre_w2_to_post_w3"] = sample.pop("delta_e00_w1_to_w2")

    key = "delta_e00_pre_w2_to_post_w3"
    atlas_values = [item[key] for item in atlas_samples]
    grid_values = [item[key] for item in grid_samples]
    row_medians = [
        statistics.median(item[key] for item in grid_samples if item["row"] == row)
        for row in range(GRID_ROWS)
    ]
    atlas_p95 = frozen._p95(atlas_values)  # noqa: SLF001
    atlas_max = max(atlas_values)
    grid_p95 = frozen._p95(grid_values)  # noqa: SLF001
    stripe_max = max(row_medians)
    components = {
        "atlas_cell_p95": frozen._classify(  # noqa: SLF001
            atlas_p95,
            pass_max=ATLAS_P95_PASS_DE00,
            review_max=ATLAS_P95_REVIEW_DE00,
        ),
        "atlas_cell_maximum": frozen._classify(  # noqa: SLF001
            atlas_max,
            pass_max=ATLAS_MAX_PASS_DE00,
            review_max=ATLAS_MAX_REVIEW_DE00,
        ),
        "full_panel_grid_p95": frozen._classify(  # noqa: SLF001
            grid_p95,
            pass_max=GRID_P95_PASS_DE00,
            review_max=GRID_P95_REVIEW_DE00,
        ),
        "horizontal_row_median_maximum": frozen._classify(  # noqa: SLF001
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
            "exact_exp3_pre_t2_v2_w2": w2_binding,
            "fresh_successor_v2_w3": w3_binding,
        },
        "geometry": panel_geometry,
        "threshold_contract": {
            **EXPECTED_THRESHOLD_CONTRACT,
            "automatic_threshold_relaxation": False,
        },
        "atlas_samples": atlas_samples,
        "full_panel_grid": {
            "rows": GRID_ROWS,
            "columns": frozen.GRID_COLUMNS,
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
            "same_exact_exp3_locked_48mp_camera_required": True,
            "same_mount_settings_and_dimensions_required": True,
            "explicit_current_photo_panel_corners_required": True,
            "pre_w2_is_not_a_calibrated_white_standard": True,
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
    """Deep-recompute a V2 W2/W3 residual report from source evidence."""

    try:
        payload, root = strict._load_json(  # noqa: SLF001
            Path(path), label="V2 W2/W3 residual report"
        )
        strict._verify_integrity(  # noqa: SLF001
            root, label="V2 W2/W3 residual report"
        )
    except strict.CrossoverProfileComparisonError as error:
        raise WhiteResidualV2ScreenError(str(error)) from error
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise WhiteResidualV2ScreenError("V2 W2/W3 residual schema or kind differs")
    bindings = root.get("input_bindings", {})
    recomputed = evaluate(
        Path(bindings["exact_exp3_pre_t2_v2_w2"]["analysis_path"]),
        Path(bindings["fresh_successor_v2_w3"]["analysis_path"]),
        panel_corners=root["geometry"]["supplied_panel_corners_tl_tr_br_bl"],
    )
    if recomputed != root:
        raise WhiteResidualV2ScreenError(
            "V2 W2/W3 residual differs from source-evidence recomputation"
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
        raise WhiteResidualV2ScreenError(
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
    parser.add_argument("--w2-analysis", type=Path, required=True)
    parser.add_argument("--w3-analysis", type=Path, required=True)
    parser.add_argument(
        "--panel-corners",
        required=True,
        help="current W2/W3 TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = evaluate(
            args.w2_analysis, args.w3_analysis, panel_corners=args.panel_corners
        )
        payload = _serialize(report)
        _write_exclusive(args.output, payload)
    except WhiteResidualV2ScreenError as error:
        print(f"RAW-P16 V2 W2/W3 residual-screen error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return {"PASS": 0, "REVIEW": 3, "FAIL": 4}[report["summary"]["classification"]]


if __name__ == "__main__":
    raise SystemExit(main())
