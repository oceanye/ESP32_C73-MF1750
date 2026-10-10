#!/usr/bin/env python3
"""Offline, non-qualifying review of the retained T4 V5 4x8 atlas photo.

This adapter is deliberately narrower than the formal position-balanced
photo analyzer.  The V5 capture sidecar declares partial-panel coverage, so
this tool must not promote the image to formal full-panel evidence.  It may
still use the visible 64-cell lattice for camera-relative layout and
controller-difference screening.  It never opens a camera, device, network,
serial port, relay, firmware flasher, or display endpoint.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as analyzer,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_pack as pack,
)
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as base  # noqa: E402


SCHEMA_VERSION = 1
KIND = (
    "mf1750-raw-p16-crossover-t4-v5-retained-camera-relative-layout-"
    "analysis-v1"
)
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
OPERATOR_PROMPT_CONTEXT = (
    "抓拍成功，48MP 身份核验正确；画面完整可见。相机里能看到左右各 4×8，"
    "但左侧偏黄绿/蓝绿，右侧偏红粉/橙棕，差异很明显。现在需要你做一次肉眼"
    "主判：请确认这是否也符合你现场看到的效果，并特别说明右侧是否有稳定的"
    "橙色或粉色。"
)
OPERATOR_REPLY = "没错，你看的是对的。继续推进"


class V5RetainedCameraAnalysisError(RuntimeError):
    """Raised when a frozen input or current-photo lattice differs."""


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise V5RetainedCameraAnalysisError(f"{label} must be an object")
    return value


def _load_integrity_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    path = Path(path).resolve()
    payload = base._read_stable_regular(path, label=label)  # noqa: SLF001
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise V5RetainedCameraAnalysisError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise V5RetainedCameraAnalysisError(f"{label} root must be an object")
    body = deepcopy(value)
    integrity = _mapping(body.pop("integrity", None), label=f"{label}.integrity")
    if (
        integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256")
        != base._sha256_bytes(base._canonical_json(body))  # noqa: SLF001
    ):
        raise V5RetainedCameraAnalysisError(f"{label} canonical integrity differs")
    return payload, value


def _runtime_action(expected: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact compact action emitted by the shared device runner."""

    return {
        "ordinal": expected["ordinal"],
        "round": expected["round"],
        "role": expected["role"],
        "branch": expected["branch"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "frame_sha256": expected["frame"]["sha256"],
        "cs1_dtm_sha256": expected["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected["cs2_dtm"]["sha256"],
        "palette_source": expected["palette_source"],
        "global_header": expected["global_header"],
        "profile_id": expected["profile_id"],
        "global_tuple_id": expected["global_tuple_id"],
        "waveform_binding": expected["waveform_binding"],
        "boot_admission": expected["boot_admission"],
        "prior_static_action_id": expected["prior_static_action_id"],
        "driver_entry": "epdDisplayCompiledChromaGrid",
        "transport_code_histogram": expected["frame"]["histogram"],
    }


def _validate_action(action_root: Mapping[str, Any]) -> dict[str, Any]:
    report = pack.build_report()
    expected = report["actions"][0]
    action = _mapping(action_root.get("action"), label="action.action")
    terminal = _mapping(
        action_root.get("terminal_report"), label="action.terminal_report"
    )
    expected_runtime = _runtime_action(expected)
    if dict(action) != expected_runtime:
        raise V5RetainedCameraAnalysisError("V5 compact runtime action differs")
    exact_terminal = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_complete": True,
        "campaign_id": pack.CONFIG.campaign_id,
        "test_id": pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "build_tag": pack.CONFIG.build_tag,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "ordinal": 1,
        "next_ordinal": 2,
        "role": expected["role"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, expected_value in exact_terminal.items():
        if terminal.get(key) != expected_value:
            raise V5RetainedCameraAnalysisError(f"V5 terminal {key} differs")
    driver = _mapping(terminal.get("driver"), label="terminal.driver")
    if (
        driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("failure_stage") != "none"
        or driver.get("failure_code") != 0
        or driver.get("pre_command_idle_failure") is not False
    ):
        raise V5RetainedCameraAnalysisError("V5 terminal driver evidence differs")
    if (
        action_root.get("kind")
        != (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v5-result"
        )
        or action_root.get("outcome") != "complete_pass"
        or action_root.get("visible_refreshes") != 1
        or action_root.get("firmware_sha256")
        != pack.ARTIFACTS[pack.STAGE]["bin_sha256"]
        or action_root.get("no_retry") is not True
        or action_root.get("no_recovery") is not True
        or action_root.get("no_autochain") is not True
    ):
        raise V5RetainedCameraAnalysisError("V5 action-result semantics differ")
    return {
        "campaign_id": pack.CONFIG.campaign_id,
        "test_id": pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "firmware_sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        "frame_sha256": expected["frame"]["sha256"],
        "cs1_dtm_sha256": expected["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected["cs2_dtm"]["sha256"],
        "profile_id": expected["profile_id"],
        "global_header": expected["global_header"],
        "global_tuple_id": expected["global_tuple_id"],
        "waveform_binding": expected["waveform_binding"],
        "boot_nonce": terminal["boot_nonce"],
        "driver": dict(driver),
    }


def _derive_homography(rgb: Any, initial_corners: Any) -> tuple[Any, dict[str, Any]]:
    cv2, np = base._import_cv()  # noqa: SLF001
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 20, 60)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _hierarchy = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    raw_centers: list[Any] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if (
            3000.0 < area < 40000.0
            and 50 < width < 180
            and 50 < height < 220
            and 400 < x < 2900
            and 600 < y < 1750
            and len(polygon) in (4, 5)
        ):
            raw_centers.append(
                np.asarray((x + width / 2.0, y + height / 2.0), dtype=np.float64)
            )
    clusters: list[list[Any]] = []
    for center in raw_centers:
        for cluster in clusters:
            if float(np.linalg.norm(center - np.mean(cluster, axis=0))) < 7.0:
                cluster.append(center)
                break
        else:
            clusters.append([center])
    observed = np.asarray(
        [np.mean(cluster, axis=0) for cluster in clusters], dtype=np.float64
    )
    observed = observed[(observed[:, 1] > 780.0) & (observed[:, 1] < 1625.0)]

    logical_cells = analyzer._all_logical_cells()  # noqa: SLF001
    logical = np.asarray(
        [cell["logical_center"] for cell in logical_cells], dtype=np.float64
    )
    logical_panel = np.asarray(
        ((0.0, 0.0), (1024.0, 0.0), (1024.0, 600.0), (0.0, 600.0)),
        dtype=np.float32,
    )
    supplied = analyzer._coerce_panel_corners(initial_corners).astype(  # noqa: SLF001
        np.float32
    )
    homography = cv2.getPerspectiveTransform(logical_panel, supplied)
    matches: list[tuple[int, int, float]] = []
    inlier_mask = None
    for _iteration in range(6):
        projected = base._project(homography, logical)  # noqa: SLF001
        distance = np.linalg.norm(
            projected[:, None, :] - observed[None, :, :], axis=2
        )
        chosen_logical: set[int] = set()
        chosen_observed: set[int] = set()
        matches = []
        candidates = sorted(
            (float(distance[i, j]), i, j)
            for i in range(len(projected))
            for j in range(len(observed))
            if distance[i, j] < 65.0
        )
        for candidate_distance, logical_index, observed_index in candidates:
            if (
                logical_index in chosen_logical
                or observed_index in chosen_observed
            ):
                continue
            chosen_logical.add(logical_index)
            chosen_observed.add(observed_index)
            matches.append((logical_index, observed_index, candidate_distance))
        # The deliberately loose seed only needs enough non-white cells to
        # converge.  The final fit below still requires at least 40 inliers.
        if len(matches) < 20:
            raise V5RetainedCameraAnalysisError(
                "fewer than 20 current-photo cell centers matched the frozen lattice"
            )
        source = np.asarray(
            [logical[logical_index] for logical_index, _observed_index, _ in matches],
            dtype=np.float64,
        )
        target = np.asarray(
            [observed[observed_index] for _logical_index, observed_index, _ in matches],
            dtype=np.float64,
        )
        fitted, inlier_mask = cv2.findHomography(source, target, cv2.RANSAC, 8.0)
        if fitted is None or inlier_mask is None:
            raise V5RetainedCameraAnalysisError("current-photo homography fit failed")
        homography = fitted

    inliers = [
        match for match, admitted in zip(matches, inlier_mask.ravel()) if admitted
    ]
    if len(inliers) < 40:
        raise V5RetainedCameraAnalysisError("current-photo homography has too few inliers")
    residuals: list[float] = []
    for logical_index, observed_index, _distance in inliers:
        predicted = base._project(  # noqa: SLF001
            homography, (logical[logical_index],)
        )[0]
        residuals.append(float(np.linalg.norm(predicted - observed[observed_index])))
    final_corners = base._project(homography, logical_panel)  # noqa: SLF001
    admitted_homography, admitted_geometry = analyzer._fit_panel_homography(  # noqa: SLF001
        final_corners,
        photo_width=rgb.shape[1],
        photo_height=rgb.shape[0],
    )
    return admitted_homography, {
        **admitted_geometry,
        "derivation": (
            "current-photo Canny quadrilateral centers matched to the frozen 64-cell "
            "lattice, followed by iterative RANSAC"
        ),
        "initial_panel_corners_tl_tr_br_bl": [
            [round(float(value), 6) for value in point] for point in supplied.tolist()
        ],
        "detected_raw_contour_count": len(raw_centers),
        "deduplicated_candidate_center_count": len(observed),
        "matched_cell_center_count": len(matches),
        "homography_inlier_count": len(inliers),
        "homography_inlier_rmse_px": round(
            float(np.sqrt(np.mean(np.square(residuals)))), 6
        ),
        "homography_inlier_max_px": round(max(residuals), 6),
        "detector_parameters": {
            "canny_low_high": [20, 60],
            "dilation_kernel_px": [3, 3],
            "duplicate_cluster_radius_px": 7.0,
            "nearest_match_limit_px": 65.0,
            "ransac_reprojection_limit_px": 8.0,
            "iteration_count": 6,
        },
        "formal_full_panel_admission": False,
        "formal_full_panel_admission_false_reason": (
            "capture sidecar explicitly declares partial_panel and "
            "full_panel_visible=false/full_panel_uncropped=false"
        ),
    }


def _controller_code_comparison(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = summary["controller_code_groups"]
    output: list[dict[str, Any]] = []
    for code in range(8):
        selected = sorted(
            (item for item in groups if item["code"] == code),
            key=lambda item: item["controller"],
        )
        if len(selected) != 2:
            raise V5RetainedCameraAnalysisError(
                f"camera summary does not contain two groups for code {code}"
            )
        left_lab = selected[0]["camera_relative_lab_component_median"]
        right_lab = selected[1]["camera_relative_lab_component_median"]
        delta_e00 = float(delta_e_ciede2000(left_lab, right_lab))
        delta_e76 = sum(
            (float(left) - float(right)) ** 2
            for left, right in zip(left_lab, right_lab)
        ) ** 0.5
        output.append(
            {
                "code": code,
                "cs1_camera_relative_lab_component_median": left_lab,
                "cs2_camera_relative_lab_component_median": right_lab,
                "cs1_maximum_within_code_delta_e00": selected[0][
                    "maximum_delta_e00_to_group_median"
                ],
                "cs2_maximum_within_code_delta_e00": selected[1][
                    "maximum_delta_e00_to_group_median"
                ],
                "controller_median_delta_e00_camera_relative": round(delta_e00, 6),
                "controller_median_delta_e76_camera_relative": round(delta_e76, 6),
                "heuristic_only": True,
                "qualification_effect": "NONE",
            }
        )
    return output


def analyze(
    *,
    photo_path: Path,
    capture_sidecar_path: Path,
    action_result_path: Path,
    initial_panel_corners: str,
) -> dict[str, Any]:
    action_payload, action_root = _load_integrity_json(
        action_result_path, label="V5 action result"
    )
    action_identity = _validate_action(action_root)
    sidecar_payload, sidecar_root = _load_integrity_json(
        capture_sidecar_path, label="V5 capture sidecar"
    )
    try:
        camera.validate_capture_evidence(capture_sidecar_path)
    except camera.CameraCaptureEvidenceError as error:
        raise V5RetainedCameraAnalysisError(
            f"V5 capture sidecar rejected: {error}"
        ) from error
    photo_payload = base._read_stable_regular(photo_path, label="V5 photo")  # noqa: SLF001
    sidecar_action = _mapping(
        sidecar_root.get("action_result"), label="capture.action_result"
    )
    sidecar_photo = _mapping(sidecar_root.get("photo"), label="capture.photo")
    if (
        sidecar_action.get("file_sha256")
        != base._sha256_bytes(action_payload)  # noqa: SLF001
        or sidecar_photo.get("sha256")
        != base._sha256_bytes(photo_payload)  # noqa: SLF001
        or sidecar_root.get("action_id") != action_identity["action_id"]
        or sidecar_root.get("descriptor_id") != action_identity["descriptor_id"]
        or sidecar_root.get("contract_id") != action_identity["contract_id"]
        or sidecar_root.get("campaign_id") != action_identity["campaign_id"]
        or sidecar_root.get("firmware_sha256")
        != action_identity["firmware_sha256"]
        or sidecar_root.get("frame_sha256") != action_identity["frame_sha256"]
    ):
        raise V5RetainedCameraAnalysisError("V5 capture input binding differs")

    rgb = base._decode_rgb(photo_payload)  # noqa: SLF001
    homography, geometry = _derive_homography(rgb, initial_panel_corners)
    cells = [
        base._sample_cell(rgb, homography, cell)  # noqa: SLF001
        for cell in analyzer._all_logical_cells()  # noqa: SLF001
    ]
    position_summary = analyzer._position_summary(cells)  # noqa: SLF001
    comparisons = _controller_code_comparison(position_summary)
    coverage = _mapping(sidecar_root.get("coverage"), label="capture.coverage")
    camera_value = _mapping(sidecar_root.get("camera"), label="capture.camera")
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "created_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "stage": pack.STAGE,
        "campaign_id": action_identity["campaign_id"],
        "contract_id": action_identity["contract_id"],
        "descriptor_id": action_identity["descriptor_id"],
        "action_id": action_identity["action_id"],
        "source_evidence": {
            "action_result": {
                "path": str(Path(action_result_path).resolve()),
                "bytes": len(action_payload),
                "file_sha256": base._sha256_bytes(action_payload),  # noqa: SLF001
                "canonical_integrity_sha256": action_root["integrity"]["sha256"],
            },
            "capture_sidecar": {
                "path": str(Path(capture_sidecar_path).resolve()),
                "bytes": len(sidecar_payload),
                "file_sha256": base._sha256_bytes(sidecar_payload),  # noqa: SLF001
                "canonical_integrity_sha256": sidecar_root["integrity"]["sha256"],
                "capture_id": sidecar_root["capture_id"],
            },
            "photo": {
                "path": str(Path(photo_path).resolve()),
                "bytes": len(photo_payload),
                "file_sha256": base._sha256_bytes(photo_payload),  # noqa: SLF001
                "width": int(rgb.shape[1]),
                "height": int(rgb.shape[0]),
            },
        },
        "action_binding": action_identity,
        "action_validation_boundary": {
            "canonical_integrity_verified": True,
            "compact_device_action_identity_verified": True,
            "terminal_complete_and_one_driver_verified": True,
            "current_expanded_host_terminal_validator_pass_claimed": False,
            "reason": (
                "this evidence does not claim the current expanded host terminal "
                "validator accepts the shared runner's compact action/claim schema"
            ),
            "action_permanently_consumed": True,
            "retry_authorized": False,
        },
        "capture_boundary": {
            "capture_evidence_integrity_verified": True,
            "camera_id": camera_value.get("camera_id"),
            "camera_instance_id": camera_value.get("instance_id"),
            "mount_id": coverage.get("mount_id"),
            "declared_scope": coverage.get("scope"),
            "declared_full_panel_visible": coverage.get("full_panel_visible"),
            "declared_full_panel_uncropped": coverage.get("full_panel_uncropped"),
            "formal_full_panel_evidence": False,
            "camera_relative_layout_screen_only": True,
        },
        "layout": {
            "logical_width": 1024,
            "logical_height": 600,
            "controller_count": 2,
            "controller_width": 512,
            "rows_per_controller": 4,
            "columns_per_controller": 8,
            "row_codes": [list(row) for row in pack.CODE_ROWS],
            "samples_per_code_per_controller": 4,
            "same_layout_both_controllers": True,
            "spatial_dither": False,
            "cs1_profile": "commented535",
            "cs2_profile": "active535",
            "global_header": "active",
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
            "single_retained_frame_only": True,
        },
        "cells": cells,
        "position_balanced_summary": position_summary,
        "controller_code_comparison": comparisons,
        "camera_relative_findings": {
            "layout_visible_to_algorithm": True,
            "all_64_logical_cell_centres_projected_inside_photo": geometry[
                "all_projected_cells_inside_photo"
            ],
            "large_controller_median_difference_codes_delta_e00_ge_10": [
                item["code"]
                for item in comparisons
                if item["controller_median_delta_e00_camera_relative"] >= 10.0
            ],
            "small_controller_median_difference_codes_delta_e00_lt_3": [
                item["code"]
                for item in comparisons
                if item["controller_median_delta_e00_camera_relative"] < 3.0
            ],
            "thresholds_are_heuristic_only": True,
            "matched_r20_swap_causality_proven": False,
            "cross_stage_comparison_performed": False,
        },
        "operator_confirmation": {
            "prompt_context_verbatim": OPERATOR_PROMPT_CONTEXT,
            "reply_verbatim": OPERATOR_REPLY,
            "reply_confirms_preceding_camera_description_matches_onsite_view": True,
            "contextually_confirmed_description": {
                "left_and_right_each_show_4x8": True,
                "left_tends_yellow_green_and_blue_green": True,
                "right_tends_red_pink_and_orange_brown": True,
                "left_right_difference_is_obvious": True,
            },
            "right_orange_or_pink_stability": (
                "CONTEXTUALLY_AFFIRMED_WITH_PRECEDING_DESCRIPTION_BUT_NOT_"
                "REPEATED_AS_A_SEPARATE_VERBATIM_ANSWER"
            ),
            "not_asked_or_not_confirmed": [
                "per-code four-replicate consistency",
                "edge cleanliness",
                "bottom-edge cleanliness",
                "horizontal or vertical stripes",
                "residual or ghosting",
                "flicker or temporal stability beyond the contextual reply",
            ],
        },
        "classification": {
            "state": "CAMERA_RELATIVE_LAYOUT_AND_CONTROLLER_DIFFERENCE_REVIEW",
            "human_context_supports_camera_description": True,
            "absolute_colour_proven": False,
            "stable_new_colour_proven": False,
            "repeatable_new_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
            "formal_full_panel_evidence": False,
            "profile_following_or_matched_swap_decision_earned": False,
            "reason": (
                "one uncalibrated retained frame with a partial-coverage sidecar and "
                "one contextual human confirmation can screen layout and relative "
                "controller differences only"
            ),
        },
        "offline_execution": {
            "hardware_accessed": False,
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
        "sha256": base._sha256_bytes(base._canonical_json(report)),  # noqa: SLF001
    }
    return report


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--capture-sidecar", type=Path, required=True)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument(
        "--initial-panel-corners",
        required=True,
        help="current-photo TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy seed",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = analyze(
            photo_path=args.photo,
            capture_sidecar_path=args.capture_sidecar,
            action_result_path=args.action_result,
            initial_panel_corners=args.initial_panel_corners,
        )
        base._write_exclusive(args.output, report)  # noqa: SLF001
    except (ValueError, V5RetainedCameraAnalysisError) as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": f"{KIND}-error",
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
