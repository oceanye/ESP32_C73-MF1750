from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_runtime_lut_hue_brightness_redpink_v2_camera_once as camera_once,
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _action_result(ordinal: int, claim: Path) -> dict[str, Any]:
    token = f"{ordinal:064x}"
    return {
        "schema_version": 1,
        "kind": "synthetic-redpink-v2-result",
        "created_at": "2026-08-28T08:00:00.000+08:00",
        "firmware_sha256": "a" * 64,
        "boot_nonce": "0123456789abcdef",
        "action": {
            "ordinal": ordinal,
            "action_id": token,
            "descriptor_id": "b" * 64,
            "role": f"ACTION_{ordinal}",
            "frame_sha256": "c" * 64,
        },
        "claim_file": str(claim.resolve()),
        "terminal_report": {
            "campaign_id": "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2",
            "test_id": "EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V2",
            "contract_id": "d" * 64,
            "terminal_state": "COMPLETE",
            "result": True,
        },
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": "e" * 64,
        },
    }


def _runner(calls: list[dict[str, Any]]):
    def run(
        _base_url: str,
        ordinal: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        calls.append({"ordinal": ordinal, **kwargs})
        claim = Path(kwargs["claims"]) / f"claim-{ordinal}.json"
        _write_json(claim, {"ordinal": ordinal, "integrity": {"sha256": "f" * 64}})
        result = _action_result(ordinal, claim)
        _write_json(Path(kwargs["output"]), result)
        return result

    return run


def _capture(
    calls: list[dict[str, Any]],
    *,
    full_panel: bool = False,
    verdict: str = "INCONCLUSIVE",
    confidence: str = "low",
    candidate_detected: bool | None = None,
    analysis_source: str = "none",
):
    def capture(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        photo = Path(kwargs["photo_path"])
        sidecar = Path(kwargs["sidecar_path"])
        photo.write_bytes(b"synthetic-jpeg")
        value = {
            "capture_binding": "live_synchronized",
            "photo": {"path": photo.name, "sha256": "1" * 64},
            "coverage": {
                "scope": "full_panel" if full_panel else "partial_panel",
                "full_panel_visible": full_panel,
            },
            "automated_assessment": {
                "verdict": verdict,
                "confidence": confidence,
                "candidate_detected": candidate_detected,
                "analysis_source": analysis_source,
                "limitations": [],
            },
        }
        _write_json(sidecar, value)
        return value

    return capture


def _render(_root: Path, **_kwargs: Any) -> dict[str, Any]:
    return {"result": "PASS", "session_report": "SESSION_REPORT.md"}


def test_one_invocation_runs_one_ordinal_and_preserves_result_and_claim(
    tmp_path: Path,
) -> None:
    runner_calls: list[dict[str, Any]] = []
    capture_calls: list[dict[str, Any]] = []
    result = camera_once.run_action_and_capture(
        "http://192.168.1.11",
        2,
        campaign_dir=tmp_path / "campaign",
        claims_dir=tmp_path / "claims",
        action_runner=_runner(runner_calls),
        capture_callable=_capture(capture_calls),
        renderer=_render,
        now_callable=lambda: "2026-08-28T08:01:00.000+08:00",
    )
    assert len(runner_calls) == 1
    assert runner_calls[0]["ordinal"] == 2
    assert len(capture_calls) == 1
    action_path = tmp_path / "campaign" / camera_once.ACTION_RESULT_NAMES[2]
    stored = json.loads(action_path.read_text(encoding="utf-8"))
    claim_path = Path(stored["claim_file"])
    assert stored == _action_result(2, claim_path)
    assert json.loads(claim_path.read_text(encoding="utf-8"))["ordinal"] == 2
    assert result["action_complete"] is True
    assert result["action_must_not_be_retried"] is True
    assert result["no_autochain"] is True
    assert result["relay_controlled"] is False


def test_camera_api_receives_exact_supported_settings(tmp_path: Path) -> None:
    captures: list[dict[str, Any]] = []
    camera_once.run_action_and_capture(
        "http://192.168.1.11",
        3,
        campaign_dir=tmp_path / "campaign",
        claims_dir=tmp_path / "claims",
        action_runner=_runner([]),
        capture_callable=_capture(captures),
        render_report=False,
    )
    assert captures[0]["coverage_scope"] == "partial_panel"
    assert captures[0]["requested_settings"] == {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
        "auto_exposure": 0.25,
        "exposure": -6.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }
    assert captures[0]["camera_id"] == camera_once.DEFAULT_CAMERA_ID
    assert captures[0]["camera_instance_id"] is None
    assert captures[0]["camera_index"] is None
    assert captures[0]["require_all_setting_writes"] is True
    assert captures[0]["analysis_source"] == "none"


def test_capture_failure_seals_attempt_and_never_allows_action_retry(
    tmp_path: Path,
) -> None:
    def fail_capture(**_kwargs: Any) -> Mapping[str, Any]:
        raise RuntimeError("synthetic camera unavailable")

    campaign = tmp_path / "campaign"
    with pytest.raises(camera_once.CameraOnceError) as caught:
        camera_once.run_action_and_capture(
            "http://192.168.1.11",
            2,
            campaign_dir=campaign,
            claims_dir=tmp_path / "claims",
            action_runner=_runner([]),
            capture_callable=fail_capture,
            renderer=_render,
        )
    error = caught.value
    assert error.action_consumed is True
    assert error.action_must_not_be_retried is True
    sidecar = json.loads(
        (campaign / "camera-action-02.capture.json").read_text(encoding="utf-8")
    )
    assert sidecar["kind"] == "mf1750-camera-capture-failure"
    assert sidecar["photo"] is None
    assert sidecar["automated_assessment"]["verdict"] == "INCONCLUSIVE"
    assert sidecar["action_must_not_be_retried"] is True


def test_ordinal4_partial_or_low_confidence_is_inconclusive_stop() -> None:
    gate = camera_once._ordinal4_gate(  # noqa: SLF001
        4,
        {
            "photo": {"path": "photo.jpg"},
            "coverage": {"scope": "partial_panel", "full_panel_visible": False},
            "automated_assessment": {
                "verdict": "PASS",
                "confidence": "high",
                "candidate_detected": True,
                "analysis_source": "synthetic-detector-v1",
            },
        },
        action_complete=True,
    )
    assert gate is not None
    assert gate["state"] == "INCONCLUSIVE_STOP"
    assert gate["automated_observer_gate_satisfied"] is False
    assert gate["ordinal5_automatic_dispatched"] is False


def test_ordinal4_full_panel_high_confidence_candidate_is_consider_only() -> None:
    gate = camera_once._ordinal4_gate(  # noqa: SLF001
        4,
        {
            "photo": {"path": "photo.jpg"},
            "coverage": {"scope": "full_panel", "full_panel_visible": True},
            "automated_assessment": {
                "verdict": "PASS",
                "confidence": "high",
                "candidate_detected": True,
                "analysis_source": "synthetic-detector-v1",
            },
        },
        action_complete=True,
    )
    assert gate is not None
    assert gate["state"] == "CONSIDER_ORDINAL5_SEPARATELY"
    assert gate["automated_observer_gate_satisfied"] is True
    assert gate["ordinal5_automatic_authorized"] is False
    assert gate["ordinal5_automatic_dispatched"] is False
    assert gate["stop_after_this_invocation"] is True


def test_pre_capture_conclusive_claim_is_rejected_before_runner(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    with pytest.raises(camera_once.CameraOnceError, match="post-capture") as caught:
        camera_once.run_action_and_capture(
            "http://192.168.1.11",
            4,
            campaign_dir=tmp_path / "campaign",
            claims_dir=tmp_path / "claims",
            automated_verdict="PASS",
            assessment_confidence="high",
            analysis_source="synthetic-detector-v1",
            action_runner=_runner(calls),
            capture_callable=_capture([]),
            render_report=False,
        )
    assert caught.value.action_consumed is False
    assert calls == []


def test_retrospective_action1_binds_existing_photo_without_runner_or_camera(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    action_path = campaign / camera_once.ACTION_RESULT_NAMES[1]
    claim = tmp_path / "claims" / "claim-1.json"
    _write_json(claim, {"ordinal": 1})
    _write_json(action_path, _action_result(1, claim))
    photo = campaign / "camera-after-action-01-white.jpg"
    photo.write_bytes(b"existing-jpeg")
    action_before = action_path.read_bytes()
    photo_before = photo.read_bytes()
    calls: list[dict[str, Any]] = []

    def bind(**kwargs: Any) -> Mapping[str, Any]:
        calls.append(kwargs)
        value = {
            "capture_binding": "retrospective_unproven",
            "photo": {"path": photo.name},
            "coverage": {"scope": "partial_panel", "full_panel_visible": False},
            "automated_assessment": {
                "verdict": "INCONCLUSIVE",
                "confidence": "low",
                "analysis_source": "none",
                "candidate_detected": None,
                "limitations": ["retrospective"],
            },
        }
        _write_json(Path(kwargs["sidecar_path"]), value)
        return value

    result = camera_once.bind_existing_action1(
        campaign_dir=campaign,
        photo_path=photo,
        bind_callable=bind,
        renderer=_render,
    )
    assert len(calls) == 1
    assert result["binding"] == "retrospective_unproven"
    assert result["camera_accessed"] is False
    assert result["device_network_accessed"] is False
    assert action_path.read_bytes() == action_before
    assert photo.read_bytes() == photo_before


def test_preexisting_capture_path_refuses_before_runner(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "camera-action-02.jpg").write_bytes(b"occupied")
    calls: list[dict[str, Any]] = []
    with pytest.raises(camera_once.CameraOnceError) as caught:
        camera_once.run_action_and_capture(
            "http://192.168.1.11",
            2,
            campaign_dir=campaign,
            claims_dir=tmp_path / "claims",
            action_runner=_runner(calls),
            capture_callable=_capture([]),
            render_report=False,
        )
    assert caught.value.action_consumed is False
    assert calls == []


def test_report_failure_is_recorded_without_changing_completed_action(
    tmp_path: Path,
) -> None:
    def fail_report(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        raise RuntimeError("synthetic report renderer failed")

    result = camera_once.run_action_and_capture(
        "http://192.168.1.11",
        2,
        campaign_dir=tmp_path / "campaign",
        claims_dir=tmp_path / "claims",
        action_runner=_runner([]),
        capture_callable=_capture([]),
        renderer=fail_report,
    )
    assert result["action_complete"] is True
    assert result["report"]["status"] == (
        "failed_after_action_and_capture_evidence_persisted"
    )
    assert result["report"]["action_must_not_be_retried"] is True
    assert "mf1750_live_session_report.py build" in result["report"]["command_hint"]


def test_description_exposes_no_mutating_auxiliary_capability() -> None:
    value = camera_once.describe()
    assert value["one_ordinal_max_per_invocation"] is True
    assert value["autochain"] is False
    assert value["relay_control"] is False
    assert value["flash"] is False
    assert value["reset"] is False
    assert value["import_time_camera_access"] is False
    assert value["import_time_network_access"] is False
    assert value["formal_live_camera_binding"] == {
        "friendly_name": "48MP USB Camera",
        "usb_vid": "32E4",
        "usb_pid": "4801",
        "excluded_usb_vid": "1BCF",
        "excluded_usb_pid": "0B15",
        "identity_from_directshow_enumeration_not_caller": True,
        "index_fallback": False,
    }


@pytest.mark.parametrize(
    "forbidden_argument",
    ("--camera-id", "--camera-instance-id", "--camera-index"),
)
def test_formal_wrapper_cli_exposes_no_camera_identity_or_index_override(
    forbidden_argument: str,
) -> None:
    with pytest.raises(SystemExit):
        camera_once._parse_args(  # noqa: SLF001
            [
                "run",
                "--base-url",
                "http://192.168.1.11",
                "--ordinal",
                "2",
                "--confirm-j2-on",
                forbidden_argument,
                "spoofed",
            ]
        )
