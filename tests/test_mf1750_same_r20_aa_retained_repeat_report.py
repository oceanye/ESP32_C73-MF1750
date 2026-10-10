from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_same_r20_aa_retained_repeat_report as repeat


def _authenticated_device() -> dict[str, Any]:
    return {
        "enumerator": camera.DIRECTSHOW_DEVICE_ENUMERATOR,
        "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
        "alternative_name": (
            r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#"
            r"6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
        ),
        "pnp_instance_id": (r"USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000"),
        "directshow_index": 0,
        "usb_vid": "32E4",
        "usb_pid": "4801",
    }


def _jpeg(colour: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), colour).save(output, format="JPEG", quality=93)
    return output.getvalue()


def _action(path: Path) -> None:
    expected = repeat.same_once.base.runner.ACTIONS[0]
    root = {
        "schema_version": 1,
        "kind": "test-same-r20-action-result",
        "created_at": "2026-08-28T08:00:00.000+08:00",
        "outcome": "complete_pass",
        "boot_nonce": "1ffa520a2537168d",
        "firmware_sha256": repeat.same_once.FIRMWARE_SHA256,
        "visible_refreshes": 1,
        "action": {
            "action_id": expected["action_id"],
            "descriptor_id": expected["descriptor_id"],
            "ordinal": 1,
            "role": repeat.EXPECTED_ACTION_ROLE,
            "frame_sha256": expected["frame_sha256"],
        },
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": repeat.same_pack.CAMPAIGN_ID,
            "test_id": repeat.same_pack.TEST_ID,
            "contract_id": repeat.same_once.base.runner.CONTRACT_ID,
            "build_tag": repeat.same_pack.BUILD_TAG,
            "boot_nonce": "1ffa520a2537168d",
            "action_id": expected["action_id"],
            "descriptor_id": expected["descriptor_id"],
            "ordinal": 1,
            "role": repeat.EXPECTED_ACTION_ROLE,
        },
    }
    path.write_text(json.dumps(camera._seal(root), sort_keys=True), encoding="utf-8")


def _capture_backend(
    frame_index: int,
):
    requested = {
        "fourcc": "MJPG",
        "frame_width": 64,
        "frame_height": 48,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
        "auto_exposure": 0.25,
        "exposure": -3.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }
    effective = {
        "fourcc": "MJPG",
        "frame_width": 64,
        "frame_height": 48,
        "fps": 15.0,
        "autofocus": 2,
        "focus": 79,
        "auto_exposure": -1,
        "exposure": -3,
        "auto_white_balance": 0,
        "white_balance_temperature": 4600,
        "brightness": 32,
        "contrast": 34,
        "saturation": 32,
        "hue": 32,
    }
    set_results = {field: True for field in requested}

    def backend(*_args: Any):
        return _jpeg((30 + 40 * frame_index, 120, 140)), {
            "backend": "DSHOW",
            "authenticated_device": _authenticated_device(),
            "set_results": set_results,
            "effective_settings_before_frame": effective,
            "effective_settings_after_frame": dict(effective),
            "warmup_frames_completed": 1,
            "read_failures": 0,
            "frame_retrieved_at": (f"2026-08-28T08:00:0{frame_index}.000+08:00"),
            "frame_retrieved_at_utc": (f"2026-08-28T00:00:0{frame_index}.000+00:00"),
        }

    return requested, backend


def _captures(
    directory: Path, *, mounts: Sequence[str] | None = None
) -> tuple[list[Path], list[Mapping[str, Any]]]:
    action_path = directory / "action.json"
    _action(action_path)
    sidecars: list[Path] = []
    roots: list[Mapping[str, Any]] = []
    mount_values = list(mounts or ["LOCKED-MOUNT"] * 4)
    for frame_index in range(1, 5):
        photo = directory / f"frame-{frame_index}.jpg"
        sidecar = directory / f"frame-{frame_index}.capture.json"
        requested, backend = _capture_backend(frame_index)
        kwargs = {
            "action_result_path": action_path,
            "photo_path": photo,
            "sidecar_path": sidecar,
            "camera_id": camera.TARGET_CAMERA_LOGICAL_ID,
            "camera_instance_id": _authenticated_device()["pnp_instance_id"],
            "mount_id": mount_values[frame_index - 1],
            "coverage_scope": camera.COVERAGE_FULL,
            "requested_settings": requested,
            "warmup_frames": 1,
            "capture_backend": backend,
            "limitations": (
                ("live Same-R20 AA frame",)
                if frame_index == 1
                else (repeat.RETAINED_PROCEDURE_MARKER,)
            ),
            "_device_resolver": _authenticated_device,
        }
        capture_function = (
            camera.capture if frame_index == 1 else camera.capture_locked_retained
        )
        roots.append(capture_function(**kwargs))
        sidecars.append(sidecar)
    return sidecars, roots


def _sign(value: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(value)
    unsigned.pop("integrity", None)
    unsigned["integrity"] = {
        "algorithm": repeat.INTEGRITY_ALGORITHM,
        "sha256": repeat._sha256_bytes(repeat._canonical_json(unsigned)),
    }
    return unsigned


def _analysis(
    path: Path,
    capture_root: Mapping[str, Any],
    deltas: Sequence[float],
    *,
    geometry_sha256: str = "a" * 64,
) -> Path:
    cells: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for controller in range(2):
        for code in range(8):
            row, column = divmod(code, 4)
            lab = [40.0 + (float(deltas[code]) if controller else 0.0), 0.0, 0.0]
            cells.append(
                {
                    "cell_id": f"C{controller}-CODE{code}",
                    "controller": controller,
                    "row": row,
                    "column": column,
                    "code": code,
                    "logical_bounds": repeat.atlas_contract._logical_bounds(
                        controller, row, column
                    ),
                    "inner_patch_valid_fraction": 1.0,
                    "robust_rgb_median": [100.0, 100.0, 100.0],
                    "robust_rgb_mad": [1.0, 1.0, 1.0],
                    "camera_relative_lab": lab,
                    "cell_to_top_separator_de76": 6.0,
                }
            )
    for code, delta in enumerate(deltas):
        pairs.append(
            {
                "code": code,
                "camera_relative_de76": float(delta),
                "absolute_lstar_difference": float(delta),
                "cs1_lab": [40.0, 0.0, 0.0],
                "cs2_lab": [40.0 + float(delta), 0.0, 0.0],
            }
        )
    noise = 2.0
    threshold = 6.0
    pair_gate = all(float(delta) <= threshold for delta in deltas)
    photo = capture_root["photo"]
    reference = {
        "path": "reference.json",
        "bytes": 123,
        "file_sha256": geometry_sha256,
        "canonical_integrity_sha256": "b" * 64,
        "camera_must_not_have_moved": True,
    }
    source_photo = {
        "path": str(photo["path"]),
        "bytes": photo["bytes"],
        "sha256": photo["sha256"],
        "width": photo["width"],
        "height": photo["height"],
    }
    root = _sign(
        {
            "schema_version": repeat.atlas_contract.ANALYSIS_SCHEMA_VERSION,
            "kind": repeat.atlas_contract.ANALYSIS_KIND,
            "analysis_id": repeat._sha256_bytes(
                repeat._canonical_json(
                    {
                        "photo_sha256": photo["sha256"],
                        "reference_file_sha256": geometry_sha256,
                        "role": repeat.EXPECTED_ANALYSIS_ROLE,
                        "method": repeat.atlas_contract.ANALYSIS_METHOD_ID,
                    }
                )
            ),
            "role": repeat.EXPECTED_ANALYSIS_ROLE,
            "layout": {
                "id": repeat.atlas_contract.LAYOUT_ID,
                "controller_count": 2,
                "rows": 2,
                "columns_per_controller": 4,
                "code_mapping": "code = row * 4 + column",
                "same_dtm_both_controllers": True,
            },
            "source_photo": source_photo,
            "reference_geometry": reference,
            "geometry_guard": {
                "minimum_inner_patch_valid_fraction": 1.0,
                "contrasting_cell_count": 16,
                "minimum_required_contrasting_cells": 8,
                "reference_homography_alignment_guard_pass": True,
            },
            "cells": cells,
            "left_right_pairs": pairs,
            "paired_summary": {
                "camera_relative_de76_median": float(repeat.statistics.median(deltas)),
                "camera_relative_de76_p95": repeat._percentile(deltas, 0.95),
                "camera_relative_de76_max": float(max(deltas)),
                "repeat_noise_p95_de76": noise,
                "exploratory_threshold_de76": threshold,
                "all_pairs_within_exploratory_threshold": pair_gate,
            },
            "classification": {
                "state": (
                    "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
                    if pair_gate
                    else "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
                ),
                "controller_equivalence_proven": False,
                "absolute_colour_proven": False,
                "qualified_new_colour": False,
            },
            "evidence_boundaries": {
                "camera_relative_de76_not_calibrated_de00": True,
                "reference_homography_reuse_requires_fixed_camera": True,
                "compiled_identical_payload_does_not_prove_bus_reception": True,
                "device_io_performed": False,
            },
            "output_write_contract": "O_EXCL",
        }
    )
    path.write_text(json.dumps(root, sort_keys=True), encoding="utf-8")
    return path


def _inputs(
    tmp_path: Path,
    frame_code_deltas: Sequence[Sequence[float]],
    *,
    mounts: Sequence[str] | None = None,
    geometry_hashes: Sequence[str] | None = None,
) -> tuple[list[Path], list[Path]]:
    sidecars, captures = _captures(tmp_path, mounts=mounts)
    hashes = list(geometry_hashes or ["a" * 64] * 4)
    analyses = [
        _analysis(
            tmp_path / f"frame-{frame_index}.analysis.json",
            captures[frame_index - 1],
            frame_code_deltas[frame_index - 1],
            geometry_sha256=hashes[frame_index - 1],
        )
        for frame_index in range(1, 5)
    ]
    return analyses, sidecars


def test_three_of_four_is_repeat_candidate_and_two_of_four_is_not(
    tmp_path: Path,
) -> None:
    frames = [
        [8.0, 8.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        [7.0, 7.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        [9.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    ]
    analyses, sidecars = _inputs(tmp_path, frames)

    result = repeat.build_report(analyses, sidecars)

    code0 = result["per_code"][0]
    code1 = result["per_code"][1]
    assert code0["threshold_exceedance_count"] == 3
    assert code0["consistent_threshold_exceedance_3_of_4"] is True
    assert code0["camera_relative_de76_min"] == 1.0
    assert code0["camera_relative_de76_median"] == 7.5
    assert code0["camera_relative_de76_max"] == 9.0
    assert code0["camera_relative_de76_p95"] == pytest.approx(8.85)
    assert code1["threshold_exceedance_count"] == 2
    assert code1["consistent_threshold_exceedance_3_of_4"] is False
    assert result["summary"]["consistent_threshold_exceedance_codes"] == [0]
    assert result["classification"]["state"] == (
        "CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE"
    )
    assert result["classification"]["controller_mismatch_proven"] is False
    assert result["classification"]["hardware_mismatch_proven"] is False
    assert result["campaign_control"]["next_same_campaign_ordinal_allowed"] is False
    assert result["campaign_control"]["campaign_disposition"] == (
        "STOPPED_AT_ORDINAL_1_CAMERA_MISMATCH_CANDIDATE"
    )
    assert result["campaign_control"]["planned_ordinal_2_is_recovery"] is False
    assert (
        result["campaign_control"]["planned_ordinal_2_must_not_be_used_as_recovery"]
        is True
    )
    assert (
        result["retained_capture_semantics"]["physical_j2_off_proven_by_these_inputs"]
        is False
    )


def test_two_of_four_only_stays_unresolved(tmp_path: Path) -> None:
    frames = [[7.0] * 8, [7.0] * 8, [1.0] * 8, [1.0] * 8]
    analyses, sidecars = _inputs(tmp_path, frames)

    result = repeat.build_report(analyses, sidecars)

    assert result["summary"]["consistent_threshold_exceedance_code_count"] == 0
    assert result["classification"]["state"] == (
        "NO_REPEATABLE_CAMERA_RELATIVE_MISMATCH_RESOLVED"
    )
    assert result["classification"]["controller_equivalence_proven"] is False
    assert result["campaign_control"]["next_same_campaign_ordinal_allowed"] is True


def test_live_then_retained_capture_order_is_strict(tmp_path: Path) -> None:
    analyses, sidecars = _inputs(tmp_path, [[1.0] * 8] * 4)
    sidecars[0], sidecars[1] = sidecars[1], sidecars[0]

    with pytest.raises(repeat.SameR20AARetainedRepeatReportError, match="binding"):
        repeat.build_report(analyses, sidecars)


def test_analysis_photo_hash_must_match_paired_capture(tmp_path: Path) -> None:
    analyses, sidecars = _inputs(tmp_path, [[1.0] * 8] * 4)
    analyses[0], analyses[1] = analyses[1], analyses[0]

    with pytest.raises(
        repeat.SameR20AARetainedRepeatReportError, match="analysis/photo binding"
    ):
        repeat.build_report(analyses, sidecars)


def test_camera_or_mount_drift_is_rejected(tmp_path: Path) -> None:
    analyses, sidecars = _inputs(
        tmp_path,
        [[1.0] * 8] * 4,
        mounts=["LOCKED-MOUNT", "LOCKED-MOUNT", "LOCKED-MOUNT", "MOVED-MOUNT"],
    )

    with pytest.raises(
        repeat.SameR20AARetainedRepeatReportError,
        match="camera or mount signature differs",
    ):
        repeat.build_report(analyses, sidecars)


def test_reference_geometry_drift_is_rejected(tmp_path: Path) -> None:
    analyses, sidecars = _inputs(
        tmp_path,
        [[1.0] * 8] * 4,
        geometry_hashes=["a" * 64, "a" * 64, "a" * 64, "c" * 64],
    )

    with pytest.raises(
        repeat.SameR20AARetainedRepeatReportError,
        match="reference geometry differs",
    ):
        repeat.build_report(analyses, sidecars)


def test_analysis_integrity_tamper_is_rejected(tmp_path: Path) -> None:
    analyses, sidecars = _inputs(tmp_path, [[1.0] * 8] * 4)
    root = json.loads(analyses[2].read_text("utf-8"))
    root["left_right_pairs"][0]["camera_relative_de76"] = 9.0
    analyses[2].write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(repeat.SameR20AARetainedRepeatReportError, match="integrity"):
        repeat.build_report(analyses, sidecars)


def test_exclusive_output_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    repeat._write_exclusive(output, b"first")
    with pytest.raises(
        repeat.SameR20AARetainedRepeatReportError, match="refusing to overwrite"
    ):
        repeat._write_exclusive(output, b"second")
