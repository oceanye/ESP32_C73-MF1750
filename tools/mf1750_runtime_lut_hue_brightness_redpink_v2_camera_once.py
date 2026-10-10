#!/usr/bin/env python3
"""One-action camera wrapper for the MF1750 red/pink brightness V2 campaign.

The wrapped hardware runner remains the only component allowed to issue the
campaign's GET/POST requests.  One invocation can consume at most one ordinal.
After an action result has been durably written, this module captures exactly
one photograph and asks :mod:`tools.mf1750_camera_capture_evidence` to create
an immutable sidecar.  It never controls a relay, flashes, resets, retries, or
chains another ordinal.

Camera or report failures never change the action result or permanent claim.
If an action was consumed, every surfaced error says that it must not be
retried.  The separate ``bind-existing-action1`` command performs no device
access and records the already captured action-1 photograph as retrospective,
unproven visual evidence.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_20260827_V2"
)
CLAIMS_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_target_hue_redpink_brightness_v2_claims"
)
ACTION_RESULT_NAMES = {
    1: "action-01-factory-otp-white-anchor.json",
    2: "action-02-source-columns.json",
    3: "action-03-middle-rows.json",
    4: "action-04-redpink-64-candidates.json",
    5: "action-05-redpink-repeat.json",
    6: "action-06-factory-otp-white-recovery.json",
}
DEFAULT_EXISTING_ACTION1_PHOTO = CAMPAIGN_DIR / "camera-after-action-01-white.jpg"
DEFAULT_CAMERA_ID = "USB_VID_32E4_PID_4801"
DEFAULT_MOUNT_ID = "temporary-partial-oblique-20260828"
DEFAULT_REQUESTED_SETTINGS: Mapping[str, Any] = {
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

ActionRunner = Callable[..., Mapping[str, Any]]
CaptureCallable = Callable[..., Mapping[str, Any]]
RenderCallable = Callable[..., Mapping[str, Any]]
NowCallable = Callable[[], str]


class CameraOnceError(RuntimeError):
    """A wrapper step failed without changing the campaign retry contract."""

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        action_consumed: bool,
        failure_sidecar: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.action_consumed = action_consumed
        self.action_must_not_be_retried = action_consumed
        self.failure_sidecar = failure_sidecar

    def as_record(self) -> dict[str, Any]:
        return {
            "kind": "mf1750-redpink-v2-camera-once-error",
            "phase": self.phase,
            "error": str(self),
            "action_consumed": self.action_consumed,
            "action_must_not_be_retried": self.action_must_not_be_retried,
            "retry_permitted": False if self.action_consumed else None,
            "failure_sidecar": (
                str(self.failure_sidecar) if self.failure_sidecar is not None else None
            ),
            "no_autochain": True,
            "relay_controlled": False,
            "firmware_flashed": False,
            "device_reset": False,
        }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(value))
    root.pop("integrity", None)
    root["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical_bytes(root)).hexdigest(),
    }
    return root


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CameraOnceError(
            f"cannot read {label}: {error}",
            phase="local_evidence",
            action_consumed=True,
        ) from error
    if not isinstance(value, dict):
        raise CameraOnceError(
            f"{label} root is not an object",
            phase="local_evidence",
            action_consumed=True,
        )
    return value


def _file_identity(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    return {
        "path": str(Path(path).resolve()),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _claim_path(action_result: Mapping[str, Any]) -> Path | None:
    value = action_result.get("claim_file")
    if not isinstance(value, str) or not value:
        return None
    return Path(value).resolve()


def _snapshot_protected_files(action_result_path: Path) -> dict[str, Any]:
    result = _read_object(action_result_path, label="action result")
    snapshot: dict[str, Any] = {
        "action_result": _file_identity(action_result_path),
        "claim": None,
    }
    claim_path = _claim_path(result)
    if claim_path is not None:
        try:
            snapshot["claim"] = _file_identity(claim_path)
        except OSError as error:
            raise CameraOnceError(
                f"cannot bind permanent claim: {error}",
                phase="local_evidence",
                action_consumed=True,
            ) from error
    return snapshot


def _assert_protected_files_unchanged(
    action_result_path: Path, before: Mapping[str, Any]
) -> None:
    after = _snapshot_protected_files(action_result_path)
    if after != before:
        raise CameraOnceError(
            "camera/report step changed the immutable action result or claim",
            phase="immutability_check",
            action_consumed=True,
        )


def _relative_to_sidecar(path: Path, sidecar_path: Path) -> str:
    try:
        return path.resolve().relative_to(sidecar_path.resolve().parent).as_posix()
    except ValueError:
        return str(path.resolve())


def _action_result_binding(
    action_result_path: Path,
    result: Mapping[str, Any],
    *,
    sidecar_path: Path | None = None,
) -> dict[str, Any]:
    identity = _file_identity(action_result_path)
    integrity = result.get("integrity")
    canonical_integrity = (
        integrity.get("sha256") if isinstance(integrity, Mapping) else None
    )
    terminal = result.get("terminal_report")
    terminal_state = (
        terminal.get("terminal_state") if isinstance(terminal, Mapping) else None
    )
    return {
        "path": (
            _relative_to_sidecar(action_result_path, sidecar_path)
            if sidecar_path is not None
            else str(action_result_path.resolve())
        ),
        "bytes": identity["bytes"],
        "file_sha256": identity["sha256"],
        "canonical_integrity_sha256": canonical_integrity,
        "outcome": result.get("outcome"),
        "terminal_state": terminal_state,
        "visible_refreshes": result.get("visible_refreshes"),
    }


def _failure_sidecar(
    *,
    action_result_path: Path,
    sidecar_path: Path,
    ordinal: int,
    camera_id: str,
    mount_id: str,
    coverage_scope: str,
    error: Exception,
    now_callable: NowCallable,
) -> dict[str, Any]:
    result = _read_object(action_result_path, label="consumed action result")
    action = result.get("action")
    if not isinstance(action, Mapping):
        action = {}
    terminal = result.get("terminal_report")
    if not isinstance(terminal, Mapping):
        terminal = {}
    captured_at = now_callable()
    seed = {
        "ordinal": ordinal,
        "action_result_sha256": _file_identity(action_result_path)["sha256"],
        "captured_at": captured_at,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    record = _seal(
        {
            "schema_version": 1,
            "kind": "mf1750-camera-capture-failure",
            "capture_id": hashlib.sha256(_canonical_bytes(seed)).hexdigest(),
            "capture_binding": "immediate_post_action_capture_failed",
            "campaign_id": terminal.get("campaign_id"),
            "test_id": terminal.get("test_id"),
            "contract_id": terminal.get("contract_id"),
            "firmware_sha256": result.get("firmware_sha256"),
            "boot_nonce": result.get("boot_nonce"),
            "ordinal": ordinal,
            "action_id": action.get("action_id"),
            "descriptor_id": action.get("descriptor_id"),
            "role": action.get("role"),
            "frame_sha256": action.get("frame_sha256"),
            "captured_at": None,
            "capture_timing": {
                "attempt_recorded_at": captured_at,
                "relationship_to_action": "after_action_result_was_durable",
            },
            "action_result": _action_result_binding(
                action_result_path, result, sidecar_path=sidecar_path
            ),
            "camera": {
                "camera_id": camera_id,
                "mount_id": mount_id,
            },
            "photo": None,
            "coverage": {
                "full_panel_visible": coverage_scope == "full_panel",
                "full_panel_uncropped": coverage_scope == "full_panel",
                "scope": coverage_scope,
                "limitations": ["capture_failed_no_image_available"],
            },
            "automated_assessment": {
                "verdict": "INCONCLUSIVE",
                "confidence": "low",
                "analysis_source": "none",
                "candidate_detected": None,
                "limitations": ["capture_failed_no_image_available"],
            },
            "output_write_contract": "O_EXCL",
            "capture_error": {
                "type": type(error).__name__,
                "message": str(error),
            },
            "action_consumed": True,
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_autochain": True,
        }
    )
    _write_new_json(sidecar_path, record)
    return record


def _load_runner() -> ActionRunner:
    try:
        from tools import (  # noqa: PLC0415
            mf1750_runtime_lut_hue_brightness_redpink_v2_once as runner,
        )
    except ModuleNotFoundError as error:
        if error.name != "tools":
            raise
        import mf1750_runtime_lut_hue_brightness_redpink_v2_once as runner  # type: ignore[no-redef]  # noqa: PLC0415

    return runner.run_once


def _load_capture() -> CaptureCallable:
    try:
        from tools import mf1750_camera_capture_evidence as camera  # noqa: PLC0415
    except ModuleNotFoundError as error:
        if error.name != "tools":
            raise
        import mf1750_camera_capture_evidence as camera  # type: ignore[no-redef]  # noqa: PLC0415

    return camera.capture


def _load_bind_existing() -> CaptureCallable:
    try:
        from tools import mf1750_camera_capture_evidence as camera  # noqa: PLC0415
    except ModuleNotFoundError as error:
        if error.name != "tools":
            raise
        import mf1750_camera_capture_evidence as camera  # type: ignore[no-redef]  # noqa: PLC0415

    return camera.bind_existing


def _load_renderer() -> RenderCallable:
    try:
        from tools import mf1750_live_session_report as report  # noqa: PLC0415
    except ModuleNotFoundError as error:
        if error.name != "tools":
            raise
        import mf1750_live_session_report as report  # type: ignore[no-redef]  # noqa: PLC0415

    return report.build_session


def _report_hint(
    campaign_dir: Path, *, generated_at: str, docs_output: Path | None
) -> str:
    command = (
        "python -B tools/mf1750_live_session_report.py build "
        f'--campaign-dir "{campaign_dir}" --generated-at "{generated_at}"'
    )
    if docs_output is not None:
        command += f' --docs-output "{docs_output}"'
    return command


def _render(
    *,
    campaign_dir: Path,
    generated_at: str,
    docs_output: Path | None,
    enabled: bool,
    renderer: RenderCallable | None,
) -> dict[str, Any]:
    hint = _report_hint(
        campaign_dir, generated_at=generated_at, docs_output=docs_output
    )
    if not enabled:
        return {"status": "not_requested", "command_hint": hint}
    selected = renderer
    try:
        selected = selected or _load_renderer()
        report = selected(
            campaign_dir,
            generated_at=generated_at,
            docs_output=docs_output,
        )
        return {
            "status": "rendered",
            "command_hint": hint,
            "result": deepcopy(dict(report)),
        }
    except Exception as error:  # report failure cannot change action state
        return {
            "status": "failed_after_action_and_capture_evidence_persisted",
            "error": {"type": type(error).__name__, "message": str(error)},
            "action_must_not_be_retried": True,
            "command_hint": hint,
        }


def _ordinal4_gate(
    ordinal: int,
    sidecar: Mapping[str, Any],
    *,
    action_complete: bool,
) -> dict[str, Any] | None:
    if ordinal != 4:
        return None
    coverage = sidecar.get("coverage")
    assessment = sidecar.get("automated_assessment")
    photo = sidecar.get("photo")
    full_panel = (
        isinstance(coverage, Mapping)
        and coverage.get("full_panel_visible") is True
        and coverage.get("scope") == "full_panel"
    )
    high_confidence_candidate = (
        isinstance(assessment, Mapping)
        and assessment.get("verdict") == "PASS"
        and assessment.get("confidence") == "high"
        and assessment.get("candidate_detected") is True
        and assessment.get("analysis_source") not in (None, "none")
    )
    eligible = (
        action_complete
        and photo is not None
        and full_panel
        and high_confidence_candidate
    )
    if eligible:
        return {
            "state": "CONSIDER_ORDINAL5_SEPARATELY",
            "message_zh": "检测到全屏覆盖、高置信候选；可单独考虑 ordinal 5。",
            "ordinal5_automatic_authorized": False,
            "ordinal5_automatic_dispatched": False,
            "automated_observer_gate_satisfied": True,
            "stop_after_this_invocation": True,
        }
    return {
        "state": "INCONCLUSIVE_STOP",
        "message_zh": (
            "覆盖不完整、置信度不足或没有高置信候选；结果为 INCONCLUSIVE，"
            "本次停止，不建议据此进入 ordinal 5。"
        ),
        "ordinal5_automatic_authorized": False,
        "ordinal5_automatic_dispatched": False,
        "automated_observer_gate_satisfied": False,
        "stop_after_this_invocation": True,
    }


def _result_complete(value: Mapping[str, Any]) -> bool:
    terminal = value.get("terminal_report")
    return (
        value.get("outcome") == "complete_pass"
        and isinstance(terminal, Mapping)
        and terminal.get("terminal_state") == "COMPLETE"
        and terminal.get("result") is True
    )


def _paths(ordinal: int, campaign_dir: Path) -> tuple[Path, Path, Path]:
    if ordinal not in ACTION_RESULT_NAMES:
        raise CameraOnceError(
            "ordinal must be between 1 and 6",
            phase="arguments",
            action_consumed=False,
        )
    root = Path(campaign_dir).resolve()
    return (
        root / ACTION_RESULT_NAMES[ordinal],
        root / f"camera-action-{ordinal:02d}.jpg",
        root / f"camera-action-{ordinal:02d}.capture.json",
    )


def _require_pending_pre_capture_assessment(
    *, verdict: str, confidence: str, analysis_source: str
) -> None:
    if (verdict, confidence, analysis_source) != ("INCONCLUSIVE", "low", "none"):
        raise CameraOnceError(
            "live or retrospective capture cannot predeclare a conclusive visual "
            "result; use a separate post-capture analysis bound to the photo SHA-256",
            phase="arguments",
            action_consumed=False,
        )


def _preflight_new_capture_paths(
    action_result_path: Path, photo_path: Path, sidecar_path: Path
) -> None:
    occupied = [
        path for path in (action_result_path, photo_path, sidecar_path) if path.exists()
    ]
    if occupied:
        raise CameraOnceError(
            "new action/capture paths are already occupied: "
            + ", ".join(str(path) for path in occupied),
            phase="preflight",
            action_consumed=action_result_path.exists(),
        )


def run_action_and_capture(
    base_url: str,
    ordinal: int,
    *,
    campaign_dir: Path = CAMPAIGN_DIR,
    claims_dir: Path = CLAIMS_DIR,
    camera_id: str = DEFAULT_CAMERA_ID,
    mount_id: str = DEFAULT_MOUNT_ID,
    coverage_scope: str = "partial_panel",
    camera_instance_id: str | None = None,
    camera_index: int | None = None,
    requested_settings: Mapping[str, Any] | None = None,
    warmup_frames: int = 10,
    jpeg_quality: int = 95,
    automated_verdict: str = "INCONCLUSIVE",
    assessment_confidence: str = "low",
    analysis_source: str = "none",
    limitations: Sequence[str] = (),
    coverage_note: str | None = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    visible_candidate_confirmed: bool = False,
    render_report: bool = True,
    docs_output: Path | None = None,
    action_runner: ActionRunner | None = None,
    capture_callable: CaptureCallable | None = None,
    renderer: RenderCallable | None = None,
    now_callable: NowCallable = _now,
) -> dict[str, Any]:
    """Run at most one exact ordinal, then capture one immutable photograph."""

    _require_pending_pre_capture_assessment(
        verdict=automated_verdict,
        confidence=assessment_confidence,
        analysis_source=analysis_source,
    )
    action_result_path, photo_path, sidecar_path = _paths(ordinal, campaign_dir)
    _preflight_new_capture_paths(action_result_path, photo_path, sidecar_path)
    selected_runner = action_runner or _load_runner()
    selected_capture = capture_callable or _load_capture()
    runner_error: Exception | None = None
    result: Mapping[str, Any] | None = None
    try:
        result = selected_runner(
            base_url,
            ordinal,
            claims=Path(claims_dir).resolve(),
            output=action_result_path,
            poll_seconds=poll_seconds,
            poll_count=poll_count,
            visible_candidate_confirmed=visible_candidate_confirmed,
        )
    except Exception as error:
        runner_error = error

    if not action_result_path.is_file():
        message = (
            f"runner stopped before a durable action result: {runner_error}"
            if runner_error is not None
            else "runner returned without a durable action result"
        )
        raise CameraOnceError(
            message,
            phase="runner",
            action_consumed=False,
        ) from runner_error

    stored_result = _read_object(action_result_path, label="action result")
    if result is not None and dict(result) != stored_result:
        raise CameraOnceError(
            "runner return value differs from its durable action result",
            phase="runner_result_binding",
            action_consumed=True,
        )
    protected_before = _snapshot_protected_files(action_result_path)
    settings = dict(requested_settings or DEFAULT_REQUESTED_SETTINGS)
    sidecar: Mapping[str, Any] | None = None
    capture_error: Exception | None = None
    try:
        sidecar = selected_capture(
            action_result_path=action_result_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera_id,
            mount_id=mount_id,
            coverage_scope=coverage_scope,
            camera_instance_id=camera_instance_id,
            camera_index=camera_index,
            requested_settings=settings,
            warmup_frames=warmup_frames,
            jpeg_quality=jpeg_quality,
            require_all_setting_writes=True,
            automated_verdict=automated_verdict,
            assessment_confidence=assessment_confidence,
            analysis_source=analysis_source,
            limitations=tuple(limitations),
            coverage_note=coverage_note,
        )
    except Exception as error:
        capture_error = error

    _assert_protected_files_unchanged(action_result_path, protected_before)
    generated_at = now_callable()
    if capture_error is not None:
        failure_path: Path | None = None
        if not sidecar_path.exists():
            failure_path = sidecar_path
            _failure_sidecar(
                action_result_path=action_result_path,
                sidecar_path=sidecar_path,
                ordinal=ordinal,
                camera_id=camera_id,
                mount_id=mount_id,
                coverage_scope=coverage_scope,
                error=capture_error,
                now_callable=now_callable,
            )
        _render(
            campaign_dir=Path(campaign_dir).resolve(),
            generated_at=generated_at,
            docs_output=docs_output,
            enabled=render_report,
            renderer=renderer,
        )
        raise CameraOnceError(
            "action result is durable and consumed; camera capture failed; "
            "the action must not be retried",
            phase="camera_capture",
            action_consumed=True,
            failure_sidecar=failure_path,
        ) from capture_error

    assert sidecar is not None
    if not sidecar_path.is_file():
        raise CameraOnceError(
            "camera helper returned without a durable sidecar; action remains consumed",
            phase="camera_sidecar",
            action_consumed=True,
        )
    _assert_protected_files_unchanged(action_result_path, protected_before)
    report = _render(
        campaign_dir=Path(campaign_dir).resolve(),
        generated_at=generated_at,
        docs_output=docs_output,
        enabled=render_report,
        renderer=renderer,
    )
    action_complete = _result_complete(stored_result)
    wrapper_result = {
        "schema_version": 1,
        "kind": "mf1750-redpink-v2-one-action-camera-wrapper-result",
        "created_at": generated_at,
        "ordinal": ordinal,
        "action_result": _action_result_binding(action_result_path, stored_result),
        "camera_sidecar": {
            **_file_identity(sidecar_path),
            "path": _relative_to_sidecar(sidecar_path, sidecar_path),
        },
        "photo": (
            {
                **_file_identity(photo_path),
                "path": _relative_to_sidecar(photo_path, sidecar_path),
            }
            if photo_path.is_file()
            else None
        ),
        "capture": deepcopy(dict(sidecar)),
        "runner_error": (
            {
                "type": type(runner_error).__name__,
                "message": str(runner_error),
            }
            if runner_error is not None
            else None
        ),
        "action_consumed": True,
        "action_complete": action_complete,
        "action_must_not_be_retried": True,
        "no_retry": True,
        "no_autochain": True,
        "relay_controlled": False,
        "firmware_flashed": False,
        "device_reset": False,
        "ordinal4_gate": _ordinal4_gate(
            ordinal, sidecar, action_complete=action_complete
        ),
        "report": report,
    }
    if runner_error is not None:
        raise CameraOnceError(
            "runner recorded a consumed outcome; photograph was bound; "
            "the action must not be retried",
            phase="runner_consumed_failure",
            action_consumed=True,
        ) from runner_error
    return wrapper_result


def bind_existing_action1(
    *,
    campaign_dir: Path = CAMPAIGN_DIR,
    photo_path: Path = DEFAULT_EXISTING_ACTION1_PHOTO,
    camera_id: str = DEFAULT_CAMERA_ID,
    mount_id: str = DEFAULT_MOUNT_ID,
    coverage_scope: str = "partial_panel",
    camera_instance_id: str | None = None,
    automated_verdict: str = "INCONCLUSIVE",
    assessment_confidence: str = "low",
    analysis_source: str = "none",
    limitations: Sequence[str] = (
        "retrospective_timestamp_only_not_immediate_capture_proof",
        "partial_oblique_view_not_full_panel_proof",
    ),
    coverage_note: str | None = None,
    render_report: bool = True,
    docs_output: Path | None = None,
    bind_callable: CaptureCallable | None = None,
    renderer: RenderCallable | None = None,
    now_callable: NowCallable = _now,
) -> dict[str, Any]:
    """Bind the existing action-1 image without any device or camera access."""

    _require_pending_pre_capture_assessment(
        verdict=automated_verdict,
        confidence=assessment_confidence,
        analysis_source=analysis_source,
    )
    action_result_path, _, sidecar_path = _paths(1, campaign_dir)
    photo_path = Path(photo_path).resolve()
    if not action_result_path.is_file():
        raise CameraOnceError(
            "action-1 result does not exist",
            phase="retrospective_preflight",
            action_consumed=False,
        )
    if not photo_path.is_file():
        raise CameraOnceError(
            "existing action-1 photograph does not exist",
            phase="retrospective_preflight",
            action_consumed=True,
        )
    if sidecar_path.exists():
        raise CameraOnceError(
            "action-1 camera sidecar already exists",
            phase="retrospective_preflight",
            action_consumed=True,
        )
    selected_bind = bind_callable or _load_bind_existing()
    protected_before = _snapshot_protected_files(action_result_path)
    photo_before = _file_identity(photo_path)
    try:
        sidecar = selected_bind(
            action_result_path=action_result_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera_id,
            mount_id=mount_id,
            coverage_scope=coverage_scope,
            camera_instance_id=camera_instance_id,
            automated_verdict=automated_verdict,
            assessment_confidence=assessment_confidence,
            analysis_source=analysis_source,
            limitations=tuple(limitations),
            coverage_note=coverage_note,
        )
    except Exception as error:
        raise CameraOnceError(
            "retrospective bind failed; action 1 remains consumed and must not be retried",
            phase="retrospective_bind",
            action_consumed=True,
        ) from error
    _assert_protected_files_unchanged(action_result_path, protected_before)
    if _file_identity(photo_path) != photo_before:
        raise CameraOnceError(
            "retrospective bind changed the existing photograph",
            phase="immutability_check",
            action_consumed=True,
        )
    if not sidecar_path.is_file():
        raise CameraOnceError(
            "retrospective bind returned without a durable sidecar",
            phase="retrospective_sidecar",
            action_consumed=True,
        )
    generated_at = now_callable()
    report = _render(
        campaign_dir=Path(campaign_dir).resolve(),
        generated_at=generated_at,
        docs_output=docs_output,
        enabled=render_report,
        renderer=renderer,
    )
    return {
        "schema_version": 1,
        "kind": "mf1750-redpink-v2-retrospective-action1-camera-bind",
        "created_at": generated_at,
        "ordinal": 1,
        "binding": "retrospective_unproven",
        "camera_accessed": False,
        "device_network_accessed": False,
        "action_consumed": True,
        "action_must_not_be_retried": True,
        "capture": deepcopy(dict(sidecar)),
        "camera_sidecar": _file_identity(sidecar_path),
        "photo": photo_before,
        "no_retry": True,
        "no_autochain": True,
        "relay_controlled": False,
        "firmware_flashed": False,
        "device_reset": False,
        "report": report,
    }


def describe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-redpink-v2-one-action-camera-wrapper-description",
        "campaign_dir": str(CAMPAIGN_DIR),
        "actions": deepcopy(ACTION_RESULT_NAMES),
        "one_ordinal_max_per_invocation": True,
        "captures_after_durable_action_result": 1,
        "retrospective_action1_supported": True,
        "runner_result_or_claim_rewritten": False,
        "camera_failure_allows_action_retry": False,
        "autochain": False,
        "relay_control": False,
        "flash": False,
        "reset": False,
        "import_time_camera_access": False,
        "import_time_network_access": False,
        "formal_live_camera_binding": {
            "friendly_name": "48MP USB Camera",
            "usb_vid": "32E4",
            "usb_pid": "4801",
            "excluded_usb_vid": "1BCF",
            "excluded_usb_pid": "0B15",
            "identity_from_directshow_enumeration_not_caller": True,
            "index_fallback": False,
        },
        "ordinal4_gate": {
            "capture_sidecar_initial_assessment": "INCONCLUSIVE_ONLY",
            "conclusive_analysis_requires_post_capture_photo_sha256_binding": True,
            "requires_full_panel_visible": True,
            "requires_automated_verdict": "PASS",
            "requires_confidence": "high",
            "otherwise": "INCONCLUSIVE_STOP",
            "automatically_dispatches_ordinal5": False,
        },
    }


def _add_camera_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mount-id", default=DEFAULT_MOUNT_ID)
    parser.add_argument(
        "--coverage-scope",
        choices=("full_panel", "partial_panel"),
        default="partial_panel",
    )
    parser.add_argument(
        "--automated-verdict",
        choices=("PASS", "FAIL", "INCONCLUSIVE"),
        default="INCONCLUSIVE",
    )
    parser.add_argument(
        "--assessment-confidence",
        choices=("low", "medium", "high"),
        default="low",
    )
    parser.add_argument("--analysis-source", default="none")
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--coverage-note")
    parser.add_argument(
        "--render-report",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--docs-output", type=Path)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe", allow_abbrev=False)

    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument(
        "--confirm-visible-candidate-after-ordinal4",
        action="store_true",
    )
    run.add_argument("--width", type=int, default=4000)
    run.add_argument("--height", type=int, default=3000)
    run.add_argument("--fps", type=float, default=15.0)
    run.add_argument("--warmup-frames", type=int, default=10)
    run.add_argument("--jpeg-quality", type=int, default=95)
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    _add_camera_arguments(run)

    bind = sub.add_parser("bind-existing-action1", allow_abbrev=False)
    bind.add_argument("--photo", type=Path, default=DEFAULT_EXISTING_ACTION1_PHOTO)
    _add_camera_arguments(bind)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "bind-existing-action1":
            limitations = tuple(args.limitation) or (
                "retrospective_timestamp_only_not_immediate_capture_proof",
                "partial_oblique_view_not_full_panel_proof",
            )
            value = bind_existing_action1(
                photo_path=args.photo,
                camera_id=DEFAULT_CAMERA_ID,
                mount_id=args.mount_id,
                coverage_scope=args.coverage_scope,
                camera_instance_id=None,
                automated_verdict=args.automated_verdict,
                assessment_confidence=args.assessment_confidence,
                analysis_source=args.analysis_source,
                limitations=limitations,
                coverage_note=args.coverage_note,
                render_report=args.render_report,
                docs_output=args.docs_output,
            )
        else:
            settings = {
                "fourcc": "MJPG",
                "frame_width": args.width,
                "frame_height": args.height,
                "fps": args.fps,
                "autofocus": 0.0,
                "focus": 79.0,
                "auto_exposure": 0.25,
                "exposure": -6.0,
                "auto_white_balance": 0.0,
                "white_balance_temperature": 4600.0,
            }
            limitations = tuple(args.limitation)
            if args.coverage_scope != "full_panel" and not limitations:
                limitations = ("partial_view_not_full_panel_proof",)
            value = run_action_and_capture(
                args.base_url,
                args.ordinal,
                camera_id=DEFAULT_CAMERA_ID,
                mount_id=args.mount_id,
                coverage_scope=args.coverage_scope,
                camera_instance_id=None,
                camera_index=None,
                requested_settings=settings,
                warmup_frames=args.warmup_frames,
                jpeg_quality=args.jpeg_quality,
                automated_verdict=args.automated_verdict,
                assessment_confidence=args.assessment_confidence,
                analysis_source=args.analysis_source,
                limitations=limitations,
                coverage_note=args.coverage_note,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                visible_candidate_confirmed=(
                    args.confirm_visible_candidate_after_ordinal4
                ),
                render_report=args.render_report,
                docs_output=args.docs_output,
            )
    except CameraOnceError as error:
        print(
            json.dumps(error.as_record(), ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 3 if error.action_consumed else 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
