from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from PIL import Image
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_post_capture_analysis as analysis


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


def _jpeg(colour: tuple[int, int, int] = (210, 220, 230)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), colour).save(output, format="JPEG", quality=93)
    return output.getvalue()


def _action(path: Path, *, ordinal: int = 2) -> None:
    root = {
        "schema_version": 1,
        "kind": "test-action-result",
        "created_at": "2026-08-28T07:20:48.000+08:00",
        "outcome": "complete_pass",
        "boot_nonce": "1ffa520a2537168d",
        "firmware_sha256": "5" * 64,
        "visible_refreshes": 1,
        "action": {
            "action_id": "1" * 64,
            "descriptor_id": "2" * 64,
            "ordinal": ordinal,
            "role": "SOURCE_GRID",
            "frame_sha256": "4" * 64,
        },
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": "CAMPAIGN-V2",
            "test_id": "TEST-V2",
            "contract_id": "3" * 64,
            "build_tag": "BUILD-V2",
            "boot_nonce": "1ffa520a2537168d",
            "action_id": "1" * 64,
            "descriptor_id": "2" * 64,
            "ordinal": ordinal,
            "role": "SOURCE_GRID",
        },
    }
    path.write_text(
        json.dumps(camera._seal(root), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _diagnostics() -> Mapping[str, Any]:
    return {
        "backend": "DSHOW",
        "authenticated_device": _authenticated_device(),
        "effective_settings_before_frame": {"fourcc": "MJPG"},
        "effective_settings_after_frame": {"fourcc": "MJPG"},
        "warmup_frames_completed": 0,
        "read_failures": 0,
        "frame_retrieved_at": "2026-08-28T08:00:00.000+08:00",
        "frame_retrieved_at_utc": "2026-08-28T00:00:00.000+00:00",
    }


def _evidence(tmp_path: Path, *, full: bool = False) -> tuple[Path, Path, Path]:
    action_path = tmp_path / "action-02-source-columns.json"
    photo_path = tmp_path / "camera-action-02.jpg"
    capture_path = tmp_path / "camera-action-02.capture.json"
    _action(action_path)
    camera.capture(
        action_result_path=action_path,
        photo_path=photo_path,
        sidecar_path=capture_path,
        camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
        mount_id="fixture-v1",
        coverage_scope=camera.COVERAGE_FULL if full else camera.COVERAGE_PARTIAL,
        warmup_frames=0,
        capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
        _device_resolver=_authenticated_device,
    )
    return action_path, photo_path, capture_path


def _create_inputs(tmp_path: Path, *, full: bool = False) -> dict[str, Any]:
    _action_path, _photo_path, capture_path = _evidence(tmp_path, full=full)
    return {
        "capture_sidecar_path": capture_path,
        "analysis_path": tmp_path / "camera-action-02.analysis.json",
        "analysis_source": "codex-visual-review",
        "model_or_algorithm_id": "gpt-image-review-2026-08-28",
        "parameters": {"temperature": 0, "prompt_revision": "v1"},
        "roi": {"kind": "entire_captured_frame"},
        "verdict": "INCONCLUSIVE",
        "confidence": "low",
        "candidate_detected": None,
        "limitations": ["partial oblique camera view"],
        "analyzed_at": "2026-08-28T08:01:00.000+08:00",
    }


def test_import_has_no_eager_camera_or_filesystem_state() -> None:
    assert "cv2" not in analysis.__dict__
    assert analysis.describe_schema()["kind"] == analysis.KIND


def test_create_binds_action_capture_and_photo_bytes(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    result = analysis.create_post_capture_analysis(**inputs)

    assert result["kind"] == analysis.KIND
    assert result["ordinal"] == 2
    assert result["bindings"]["capture_sidecar"]["file_sha256"]
    assert result["bindings"]["action_result"]["file_sha256"]
    assert result["bindings"]["photo"]["sha256"]
    assert result["analysis"]["coverage"]["capture_scope"] == "partial_panel"
    assert result["analysis"]["coverage"]["claim_scope"] == "visible_roi"
    assert analysis.validate_post_capture_analysis(inputs["analysis_path"]) == result


def test_refuses_to_overwrite_without_touching_existing_file(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    inputs["analysis_path"].write_text("occupied", encoding="utf-8")

    with pytest.raises(analysis.PostCaptureAnalysisError, match="overwrite"):
        analysis.create_post_capture_analysis(**inputs)
    assert inputs["analysis_path"].read_text(encoding="utf-8") == "occupied"


def test_partial_panel_cannot_make_full_panel_claim(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    inputs["claim_scope"] = "full_panel"

    with pytest.raises(analysis.PostCaptureAnalysisError, match="partial_panel"):
        analysis.create_post_capture_analysis(**inputs)
    assert not inputs["analysis_path"].exists()


def test_partial_visible_roi_can_record_medium_confidence_candidate(
    tmp_path: Path,
) -> None:
    inputs = _create_inputs(tmp_path)
    inputs.update(
        verdict="PASS",
        confidence="medium",
        candidate_detected=True,
        observations=["orange-like candidate visible inside the bounded ROI"],
    )

    result = analysis.create_post_capture_analysis(**inputs)
    assert result["analysis"]["verdict"] == "PASS"
    assert result["analysis"]["coverage"]["claim_scope"] == "visible_roi"


def test_high_pass_candidate_requires_full_panel_capture_and_claim(
    tmp_path: Path,
) -> None:
    inputs = _create_inputs(tmp_path)
    inputs.update(
        verdict="PASS",
        confidence="high",
        candidate_detected=True,
        observations=["candidate"],
    )
    with pytest.raises(analysis.PostCaptureAnalysisError, match="full_panel"):
        analysis.create_post_capture_analysis(**inputs)

    full_dir = tmp_path / "full"
    full_dir.mkdir()
    inputs = _create_inputs(full_dir, full=True)
    inputs.update(
        verdict="PASS",
        confidence="high",
        candidate_detected=True,
        observations=["candidate visible across the intended full-panel grid"],
    )
    result = analysis.create_post_capture_analysis(**inputs)
    assert result["analysis"]["coverage"]["claim_scope"] == "full_panel"


@pytest.mark.parametrize(
    ("verdict", "candidate"),
    [("PASS", False), ("FAIL", True), ("INCONCLUSIVE", False)],
)
def test_verdict_candidate_mapping_is_strict(
    tmp_path: Path, verdict: str, candidate: bool
) -> None:
    inputs = _create_inputs(tmp_path)
    inputs.update(
        verdict=verdict,
        confidence="medium",
        candidate_detected=candidate,
        observations=["observation"],
    )
    with pytest.raises(analysis.PostCaptureAnalysisError, match="candidate_detected"):
        analysis.create_post_capture_analysis(**inputs)


def test_validator_detects_photo_tampering(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    analysis.create_post_capture_analysis(**inputs)
    photo = tmp_path / "camera-action-02.jpg"
    photo.write_bytes(_jpeg((1, 2, 3)))

    with pytest.raises(analysis.PostCaptureAnalysisError, match="capture evidence"):
        analysis.validate_post_capture_analysis(inputs["analysis_path"])


def test_validator_detects_capture_sidecar_tampering(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    analysis.create_post_capture_analysis(**inputs)
    capture_path = inputs["capture_sidecar_path"]
    root = json.loads(capture_path.read_text(encoding="utf-8"))
    root["camera"]["camera_id"] = "tampered"
    capture_path.write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(analysis.PostCaptureAnalysisError, match="capture evidence"):
        analysis.validate_post_capture_analysis(inputs["analysis_path"])


def test_validator_detects_analysis_integrity_tampering(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    analysis.create_post_capture_analysis(**inputs)
    root = json.loads(inputs["analysis_path"].read_text(encoding="utf-8"))
    root["analysis"]["confidence"] = "high"
    inputs["analysis_path"].write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(analysis.PostCaptureAnalysisError, match="integrity"):
        analysis.validate_post_capture_analysis(inputs["analysis_path"])


def test_filename_is_bound_to_action_ordinal(tmp_path: Path) -> None:
    inputs = _create_inputs(tmp_path)
    inputs["analysis_path"] = tmp_path / "wrong.analysis.json"

    with pytest.raises(analysis.PostCaptureAnalysisError, match="filename"):
        analysis.create_post_capture_analysis(**inputs)
    assert not inputs["analysis_path"].exists()


def test_direct_script_describe_runs_from_repository_root() -> None:
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "tools/mf1750_camera_post_capture_analysis.py",
            "describe",
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["kind"] == analysis.KIND
