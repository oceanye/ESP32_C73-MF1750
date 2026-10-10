from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_post_capture_analysis as post_analysis
from tools import mf1750_live_session_report as report


GENERATED_AT = "2026-08-28T08:00:00+08:00"
FIRMWARE_SHA = "1" * 64
CONTRACT_ID = "2" * 64
BOOT_NONCE = "0123456789abcdef"


def _seal(value: dict[str, object]) -> dict[str, object]:
    sealed = dict(value)
    sealed["integrity"] = {
        "algorithm": report.INTEGRITY_ALGORITHM,
        "sha256": report._canonical_sha256(sealed),  # noqa: SLF001
    }
    return sealed


def _descriptor(ordinal: int) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "action_id": hashlib.sha256(f"action-{ordinal}".encode()).hexdigest(),
        "descriptor_id": hashlib.sha256(f"descriptor-{ordinal}".encode()).hexdigest(),
        "role": f"ROLE_{ordinal}",
        "branch": f"BRANCH_{ordinal}",
        "frame_sha256": hashlib.sha256(f"frame-{ordinal}".encode()).hexdigest(),
        "palette_source": "FACTORY_OTP" if ordinal == 1 else "L535_RUNTIME",
        "global_header": None if ordinal == 1 else "active",
    }


def _manifest(count: int) -> dict[str, object]:
    return {
        "kind": "fixture-manifest",
        "campaign_id": "CAMPAIGN",
        "test_id": "TEST",
        "contract_id": CONTRACT_ID,
        "build_tag": "BUILD",
        "action_count": count,
        "actions": [_descriptor(ordinal) for ordinal in range(1, count + 1)],
    }


def _write_action(root: Path, ordinal: int, *, count: int = 1) -> Path:
    descriptor = _descriptor(ordinal)
    terminal = {
        **descriptor,
        "campaign_id": "CAMPAIGN",
        "test_id": "TEST",
        "contract_id": CONTRACT_ID,
        "build_tag": "BUILD",
        "boot_nonce": BOOT_NONCE,
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "driver": {
            "sequence_ok": True,
            "wait_timeout": False,
            "failure_stage": "none",
            "timeout_stage": "none",
            "spi_hz": 1_000_000,
            "pon_ms": 181,
            "drf_ms": 22_521,
            "pof_ms": 141,
            "total_ms": 35_014,
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }
    value = _seal(
        {
            "schema_version": 1,
            "kind": "fixture-action",
            "created_at": GENERATED_AT,
            "firmware_sha256": FIRMWARE_SHA,
            "boot_nonce": BOOT_NONCE,
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "network": {"get": 5, "arm_post": 1, "execute_post": 1},
            "action": descriptor,
            "terminal_report": terminal,
            "transcript": [
                {
                    "endpoint": "manifest",
                    "method": "GET",
                    "response": _manifest(count),
                }
            ],
        }
    )
    path = root / f"action-{ordinal:02d}-fixture.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _jpeg(width: int = 8, height: int = 6) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(
        output, format="JPEG", quality=90
    )
    return output.getvalue()


def _write_capture(
    root: Path,
    action_path: Path,
    *,
    ordinal: int = 1,
    scope: str = "full_panel",
    full_visible: bool = True,
    full_uncropped: bool = True,
    supplied_verdict: str = "INCONCLUSIVE",
    confidence: str = "low",
) -> Path:
    action = json.loads(action_path.read_text(encoding="utf-8"))
    descriptor = action["action"]
    photo_path = root / f"camera-action-{ordinal:02d}.jpg"
    photo_path.write_bytes(_jpeg())
    photo_sha = report._file_sha256(photo_path)  # noqa: SLF001
    captured_at = "2026-08-28T08:01:00+08:00"
    limitations = (
        ["full panel is not visible in the camera frame"]
        if scope == "partial_panel"
        else []
    )
    candidate_detected = (
        True
        if supplied_verdict == "PASS"
        else False
        if supplied_verdict == "FAIL"
        else None
    )
    sidecar = _seal(
        {
            "schema_version": 1,
            "kind": report.CAPTURE_KIND,
            "capture_id": camera._canonical_sha256(  # noqa: SLF001
                {
                    "action_id": descriptor["action_id"],
                    "capture_binding": "live_synchronized",
                    "captured_at": captured_at,
                    "photo_sha256": photo_sha,
                }
            ),
            "capture_binding": "live_synchronized",
            "campaign_id": "CAMPAIGN",
            "test_id": "TEST",
            "contract_id": CONTRACT_ID,
            "firmware_sha256": FIRMWARE_SHA,
            "boot_nonce": BOOT_NONCE,
            "ordinal": ordinal,
            "action_id": descriptor["action_id"],
            "descriptor_id": descriptor["descriptor_id"],
            "role": descriptor["role"],
            "frame_sha256": descriptor["frame_sha256"],
            "captured_at": captured_at,
            "capture_timing": {
                "started_at": "2026-08-28T08:00:59+08:00",
                "started_at_utc": "2026-08-28T00:00:59+00:00",
                "frame_retrieved_at": captured_at,
                "frame_retrieved_at_utc": "2026-08-28T00:01:00+00:00",
                "completed_at": "2026-08-28T08:01:01+08:00",
                "completed_at_utc": "2026-08-28T00:01:01+00:00",
                "clock_source": "host_wall_clock",
                "hardware_frame_timestamp": None,
                "hardware_frame_timestamp_null_reason": "UVC unavailable",
            },
            "action_result": {
                "path": action_path.name,
                "bytes": action_path.stat().st_size,
                "file_sha256": report._file_sha256(action_path),  # noqa: SLF001
                "canonical_integrity_sha256": action["integrity"]["sha256"],
                "outcome": "complete_pass",
                "terminal_state": "COMPLETE",
                "visible_refreshes": 1,
            },
            "camera": {
                "camera_id": "VID_32E4&PID_4801",
                "instance_id": "fixture",
                "index": 0,
                "backend": "CAP_DSHOW",
                "requested_settings": {"width": 1920, "height": 1080},
                "effective_settings_before_frame": {},
                "effective_settings_after_frame": {},
                "warmup_frames_requested": 10,
                "warmup_frames_completed": 10,
                "read_failures": 0,
            },
            "photo": {
                "path": photo_path.name,
                "origin": "captured_by_tool",
                "bytes": photo_path.stat().st_size,
                "sha256": photo_sha,
                **camera._decode_jpeg(photo_path.read_bytes()),  # noqa: SLF001
            },
            "coverage": {
                "scope": scope,
                "full_panel_visible": full_visible,
                "full_panel_uncropped": full_uncropped,
                "mount_id": "fixture-mount",
                "note": "fixture",
            },
            "automated_assessment": {
                "verdict": supplied_verdict,
                "confidence": confidence,
                "analysis_source": "fixture"
                if supplied_verdict != "INCONCLUSIVE"
                else "none",
                "candidate_detected": candidate_detected,
                "limitations": limitations,
            },
            "output_write_contract": "O_EXCL",
        }
    )
    path = root / f"camera-action-{ordinal:02d}.capture.json"
    path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return path


def _write_analysis(
    root: Path,
    capture_path: Path,
    *,
    ordinal: int = 1,
    verdict: str = "PASS",
    confidence: str = "high",
    observations: tuple[str, ...] = ("fixture candidate is visible",),
    limitations: tuple[str, ...] = (),
    claim_scope: str | None = None,
) -> Path:
    path = root / f"camera-action-{ordinal:02d}.analysis.json"
    candidate_detected = (
        True if verdict == "PASS" else False if verdict == "FAIL" else None
    )
    post_analysis.create_post_capture_analysis(
        capture_sidecar_path=capture_path,
        analysis_path=path,
        analysis_source="fixture-visual-analyzer",
        model_or_algorithm_id="fixture-v1",
        parameters={"threshold": 0.5},
        roi={"kind": "full_frame"},
        verdict=verdict,
        confidence=confidence,
        candidate_detected=candidate_detected,
        observations=observations,
        limitations=limitations,
        claim_scope=claim_scope,
        analyzed_at="2026-08-28T08:02:00+08:00",
    )
    return path


def _campaign(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1)
    capture = _write_capture(root, action)
    _write_analysis(root, capture)
    return root, action, capture


def test_build_and_validate_complete_full_panel_campaign(tmp_path: Path) -> None:
    root, _, _ = _campaign(tmp_path)
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["automated_adjudication"]["verdict"] == "PASS"
    assert (
        index["actions"][0]["capture"]["automated_assessment"]["effective_verdict"]
        == "INCONCLUSIVE"
    )
    assert index["actions"][0]["analysis"]["effective_verdict"] == "PASS"
    assert index["automated_adjudication"]["qualified_colour_claimed"] is False
    assert (root / report.INDEX_NAME).is_file()
    markdown = (root / report.REPORT_NAME).read_text(encoding="utf-8")
    assert "部署与诊断流程" in markdown
    assert "driver 时序" in markdown
    assert "camera-action-01.jpg" in markdown
    assert "fixture-visual-analyzer" in markdown
    assert "fixture candidate is visible" in markdown
    assert report.validate_session(root) == index


def test_capture_without_post_analysis_cannot_become_visual_pass(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1)
    _write_capture(root, action, supplied_verdict="PASS", confidence="high")
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["actions"][0]["automated_verdict"] == "INCONCLUSIVE"
    assert index["actions"][0]["verdict_source"] == "missing_post_capture_analysis"
    assert index["automated_adjudication"]["next_gate"] == (
        "AUTOMATED_POST_CAPTURE_ANALYSIS_GATE"
    )


def test_partial_capture_remains_inconclusive_and_never_claims_full_panel(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1)
    _write_capture(
        root,
        action,
        scope="partial_panel",
        full_visible=False,
        full_uncropped=False,
        supplied_verdict="INCONCLUSIVE",
        confidence="low",
    )
    index = report.build_session(root, generated_at=GENERATED_AT)
    capture = index["actions"][0]["capture"]
    assert capture["automated_assessment"]["effective_verdict"] == "INCONCLUSIVE"
    assert capture["automated_assessment"]["full_panel_pass_claimed"] is False
    assert index["automated_adjudication"]["verdict"] == "INCONCLUSIVE"
    assert index["automated_adjudication"]["next_gate"] == (
        "CAMERA_REPOSITION_OR_AUTOMATED_RECAPTURE_GATE"
    )
    assert (
        index["derivation"]["human_observation_required_for_automated_verdict"] is False
    )


def test_low_confidence_is_always_inconclusive(tmp_path: Path) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1)
    _write_capture(root, action, supplied_verdict="INCONCLUSIVE", confidence="low")
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["actions"][0]["automated_verdict"] == "INCONCLUSIVE"


def test_partial_post_analysis_cannot_upgrade_visible_roi_to_full_panel(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1)
    capture = _write_capture(
        root,
        action,
        scope="partial_panel",
        full_visible=False,
        full_uncropped=False,
        supplied_verdict="INCONCLUSIVE",
        confidence="low",
    )
    _write_analysis(
        root,
        capture,
        verdict="INCONCLUSIVE",
        confidence="low",
        observations=(),
        limitations=("only a visible ROI was analyzed",),
        claim_scope="visible_roi",
    )
    index = report.build_session(root, generated_at=GENERATED_AT)
    analysis = index["actions"][0]["analysis"]
    assert analysis["effective_verdict"] == "INCONCLUSIVE"
    assert analysis["full_panel_pass_claimed"] is False
    assert (
        "partial_or_low_confidence_analysis_cannot_prove_full_panel"
        in analysis["limitations"]
    )


def test_partial_campaign_lists_pending_actions_without_claiming_pass(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    action = _write_action(root, 1, count=2)
    _write_capture(root, action)
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["progress"] == {
        "expected_actions": 2,
        "recorded_actions": 1,
        "captured_actions": 1,
        "analyzed_actions": 0,
        "campaign_complete": False,
        "next_ordinal": 2,
    }
    assert index["actions"][1]["execution_state"] == "NOT_EXECUTED"
    assert index["automated_adjudication"]["verdict"] == "INCONCLUSIVE"


def test_tampered_action_canonical_integrity_is_rejected(tmp_path: Path) -> None:
    root, action, _ = _campaign(tmp_path)
    value = json.loads(action.read_text(encoding="utf-8"))
    value["visible_refreshes"] = 2
    action.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(report.SessionReportError, match="canonical integrity"):
        report.build_session(root, generated_at=GENERATED_AT)


def test_photo_bytes_hash_and_dimensions_are_rechecked(tmp_path: Path) -> None:
    root, _, _ = _campaign(tmp_path)
    photo = root / "camera-action-01.jpg"
    photo.write_bytes(_jpeg(width=9, height=6))
    with pytest.raises(report.SessionReportError, match="photo SHA-256 differs"):
        report.build_session(root, generated_at=GENERATED_AT)


def test_capture_contract_or_boot_mismatch_is_rejected(tmp_path: Path) -> None:
    root, _, capture = _campaign(tmp_path)
    value = json.loads(capture.read_text(encoding="utf-8"))
    value["boot_nonce"] = "fedcba9876543210"
    capture.write_text(
        json.dumps(_seal({k: v for k, v in value.items() if k != "integrity"})),
        encoding="utf-8",
    )
    with pytest.raises(report.SessionReportError, match="boot_nonce differs"):
        report.build_session(root, generated_at=GENERATED_AT)


def test_tampered_post_analysis_binding_is_rejected(tmp_path: Path) -> None:
    root, _, _ = _campaign(tmp_path)
    analysis_path = root / "camera-action-01.analysis.json"
    value = json.loads(analysis_path.read_text(encoding="utf-8"))
    value["bindings"]["photo"]["sha256"] = "f" * 64
    analysis_path.write_text(
        json.dumps(_seal({k: v for k, v in value.items() if k != "integrity"})),
        encoding="utf-8",
    )
    with pytest.raises(report.SessionReportError, match="post-analysis validation"):
        report.build_session(root, generated_at=GENERATED_AT)


def test_ordinal4_high_confidence_full_panel_candidate_only_considers_ordinal5(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    for ordinal in range(1, 5):
        action = _write_action(root, ordinal, count=6)
        capture = _write_capture(root, action, ordinal=ordinal)
        _write_analysis(root, capture, ordinal=ordinal)
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["progress"]["next_ordinal"] == 5
    assert index["automated_adjudication"]["next_gate"] == (
        "CONSIDER_ORDINAL5_SEPARATELY"
    )
    assert index["evidence_boundary"]["automatic_retry_or_autochain_allowed"] is False


def test_ordinal4_inconclusive_analysis_never_considers_ordinal5(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    for ordinal in range(1, 5):
        action = _write_action(root, ordinal, count=6)
        capture = _write_capture(root, action, ordinal=ordinal)
        if ordinal == 4:
            _write_analysis(
                root,
                capture,
                ordinal=ordinal,
                verdict="INCONCLUSIVE",
                confidence="medium",
                observations=(),
            )
        else:
            _write_analysis(root, capture, ordinal=ordinal)
    index = report.build_session(root, generated_at=GENERATED_AT)
    assert index["progress"]["next_ordinal"] == 5
    assert index["automated_adjudication"]["next_gate"] != (
        "CONSIDER_ORDINAL5_SEPARATELY"
    )


def test_capture_photo_path_escape_is_rejected(tmp_path: Path) -> None:
    root, _, capture = _campaign(tmp_path)
    value = json.loads(capture.read_text(encoding="utf-8"))
    value["photo"]["path"] = "../outside.jpg"
    capture.write_text(
        json.dumps(_seal({k: v for k, v in value.items() if k != "integrity"})),
        encoding="utf-8",
    )
    with pytest.raises(report.SessionReportError, match="safe relative|escapes"):
        report.build_session(root, generated_at=GENERATED_AT)


def test_validate_detects_markdown_tampering(tmp_path: Path) -> None:
    root, _, _ = _campaign(tmp_path)
    report.build_session(root, generated_at=GENERATED_AT)
    (root / report.REPORT_NAME).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(report.SessionReportError, match="SESSION_REPORT"):
        report.validate_session(root)


def test_repeated_build_with_same_timestamp_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    root, _, _ = _campaign(tmp_path)
    first = report.build_session(root, generated_at=GENERATED_AT)
    index_bytes = (root / report.INDEX_NAME).read_bytes()
    markdown_bytes = (root / report.REPORT_NAME).read_bytes()
    second = report.build_session(root, generated_at=GENERATED_AT)
    assert first == second
    assert (root / report.INDEX_NAME).read_bytes() == index_bytes
    assert (root / report.REPORT_NAME).read_bytes() == markdown_bytes


def test_optional_docs_copy_has_valid_relative_photo_link(tmp_path: Path) -> None:
    root, _, _ = _campaign(tmp_path)
    docs = tmp_path / "docs" / "REDPINK_SESSION.md"
    report.build_session(root, generated_at=GENERATED_AT, docs_output=docs)
    assert "../campaign/camera-action-01.jpg" in docs.read_text(encoding="utf-8")
    report.validate_session(root, docs_output=docs)
