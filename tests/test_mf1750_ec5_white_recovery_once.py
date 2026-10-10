from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.application_browser_harness import (
    _success_diagnostic,
    version_body,
)
from tools import mf1750_ec5_white_recovery_once as runner


PANEL = {
    "model": "MF1750-C73",
    "serial": "MF750M009T6420/1582643AGY44",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
FROZEN_BINARY = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "q1-map-primer-result"
    / "FIRMWARE.bin"
)


def _panel(tmp_path: Path) -> Path:
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(PANEL), encoding="utf-8")
    return path


def _job() -> dict[str, object]:
    return {
        "job_id": 1,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": 1000,
        "started_at_ms": 1010,
        "finished_at_ms": 33060,
        "frame_fnv1a": runner.WHITE_FRAME_FNV1A,
    }


def _diagnostic() -> dict[str, object]:
    value = copy.deepcopy(_success_diagnostic(runner.WHITE_FRAME))
    job = _job()
    value.update(
        {
            "operation_id": 1,
            "job_operation_id": 1,
            "job_id": 1,
            "job_action": job["action"],
            "job_state": job["state"],
            "job_result": job["result"],
            "job_queued_at_ms": job["queued_at_ms"],
            "job_started_at_ms": job["started_at_ms"],
            "job_finished_at_ms": job["finished_at_ms"],
        }
    )
    return value


class FakeRC2G:
    def __init__(self) -> None:
        self.posted = False
        self.requests: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        assert timeout > 0
        self.requests.append((method, path))
        if (method, path) == ("GET", "/api/version"):
            return 200, version_body()
        if (method, path) == ("GET", "/api/job"):
            if not self.posted:
                return 200, json.dumps(
                    {
                        "job_id": 0,
                        "action": "none",
                        "state": "idle",
                        "result": None,
                        "queued_at_ms": 0,
                        "started_at_ms": 0,
                        "finished_at_ms": 0,
                        "frame_fnv1a": 0,
                    }
                )
            return 200, json.dumps(_job())
        if (method, path) == ("GET", "/api/diagnostic/report"):
            if not self.posted:
                return 200, json.dumps(
                    {
                        "schema_version": 2,
                        "valid": False,
                        "error": "no_completed_job_report",
                    }
                )
            return 200, json.dumps(_diagnostic())
        if (method, path) == ("GET", "/api/diagnostic/status"):
            return 200, json.dumps({"busy": 1, "rst": 0, "cs": 0, "cs2": 0})
        if (method, path) == ("POST", "/api/frame"):
            assert data == runner.WHITE_FRAME
            assert not self.posted
            self.posted = True
            return 202, json.dumps(
                {
                    "ok": True,
                    "bytes": runner.WHITE_FRAME_BYTES,
                    "fnv1a": runner.WHITE_FRAME_FNV1A,
                    "free_psram": 7_900_000,
                    "job_id": 1,
                }
            )
        raise AssertionError((method, path))


def test_frozen_white_identity_and_authorizations() -> None:
    assert runner.WHITE_FRAME == b"\x11" * 307_200
    assert runner.WHITE_FRAME_SHA256 == (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
    )
    assert runner.WHITE_FRAME_FNV1A == 0x13340DC5
    assert runner.WHITE_DTM_FNV1A == 0xB7A855C5
    assert len(set(runner.ACTION_IDS.values())) == 3
    for stage in runner.STAGES:
        authorization = runner.required_authorization(stage)
        assert runner.ACTION_IDS[stage].upper() in authorization
        assert authorization.endswith("__NO_RETRY_NO_RECOVERY")


def test_baseline_success_has_global_claim_one_post_and_deep_replay(
    tmp_path: Path,
) -> None:
    fake = FakeRC2G()
    result_file = tmp_path / "baseline-result.json"
    result = runner.run_once(
        stage="baseline",
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization("baseline"),
        panel_file=_panel(tmp_path),
        rc2g_binary_file=FROZEN_BINARY,
        result_file=result_file,
        claim_registry=tmp_path / "claims",
        requester=fake,
        sleeper=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert result["network"]["post_requests"] == 1
    assert fake.requests.count(("POST", "/api/frame")) == 1
    validated = runner.validate_result(
        result_file=result_file,
        panel_file=tmp_path / "panel.json",
        rc2g_binary_file=FROZEN_BINARY,
        claim_registry=tmp_path / "claims",
    )
    assert validated["protocol"]["job_id"] == 1
    assert validated["protocol"]["diagnostic"]["operation_id"] == 1
    assert validated["protocol"]["diagnostic"]["safe_finish_verified"] is True
    with pytest.raises(runner.WhiteRecoveryError, match="already has"):
        runner.run_once(
            stage="baseline",
            base_url="http://192.0.2.1",
            authorization=runner.required_authorization("baseline"),
            panel_file=tmp_path / "panel.json",
            rc2g_binary_file=FROZEN_BINARY,
            result_file=tmp_path / "duplicate.json",
            claim_registry=tmp_path / "claims",
            requester=FakeRC2G(),
        )


def test_wrong_authorization_is_zero_network_and_zero_claim(tmp_path: Path) -> None:
    fake = FakeRC2G()
    with pytest.raises(runner.WhiteRecoveryError, match="authorization"):
        runner.run_once(
            stage="baseline",
            base_url="http://192.0.2.1",
            authorization="wrong",
            panel_file=_panel(tmp_path),
            rc2g_binary_file=FROZEN_BINARY,
            result_file=tmp_path / "result.json",
            claim_registry=tmp_path / "claims",
            requester=fake,
        )
    assert fake.requests == []
    assert not (tmp_path / "claims").exists()


def test_preflight_bad_gpio_is_zero_claim_and_zero_post(tmp_path: Path) -> None:
    fake = FakeRC2G()

    def bad_gpio(*args, **kwargs):  # type: ignore[no-untyped-def]
        status, body = fake(*args, **kwargs)
        if args[1] == "/api/diagnostic/status":
            return status, json.dumps({"busy": 0, "rst": 0, "cs": 0, "cs2": 0})
        return status, body

    with pytest.raises(runner.WhiteRecoveryError, match="GPIO"):
        runner.run_once(
            stage="baseline",
            base_url="http://192.0.2.1",
            authorization=runner.required_authorization("baseline"),
            panel_file=_panel(tmp_path),
            rc2g_binary_file=FROZEN_BINARY,
            result_file=tmp_path / "result.json",
            claim_registry=tmp_path / "claims",
            requester=bad_gpio,
        )
    assert ("POST", "/api/frame") not in fake.requests
    assert not (tmp_path / "claims").exists()


def test_tampered_result_or_claim_is_rejected(tmp_path: Path) -> None:
    result_file = tmp_path / "baseline-result.json"
    runner.run_once(
        stage="baseline",
        base_url="http://192.0.2.1",
        authorization=runner.required_authorization("baseline"),
        panel_file=_panel(tmp_path),
        rc2g_binary_file=FROZEN_BINARY,
        result_file=result_file,
        claim_registry=tmp_path / "claims",
        requester=FakeRC2G(),
        sleeper=lambda _seconds: None,
    )
    value = json.loads(result_file.read_text(encoding="utf-8"))
    value["frame_fnv1a"] = 0
    result_file.chmod(0o600)
    result_file.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(runner.WhiteRecoveryError, match="integrity"):
        runner.validate_result(
            result_file=result_file,
            panel_file=tmp_path / "panel.json",
            rc2g_binary_file=FROZEN_BINARY,
            claim_registry=tmp_path / "claims",
        )


def test_after_stage_requires_replayed_candidate_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRC2G()

    def reject_binding(**_kwargs):  # type: ignore[no-untyped-def]
        raise runner.WhiteRecoveryError("candidate result replay failed")

    monkeypatch.setattr(runner, "load_candidate_result_binding", reject_binding)
    with pytest.raises(runner.WhiteRecoveryError, match="candidate result"):
        runner.run_once(
            stage="after-u04",
            base_url="http://192.0.2.1",
            authorization=runner.required_authorization("after-u04"),
            panel_file=_panel(tmp_path),
            rc2g_binary_file=FROZEN_BINARY,
            release_file=tmp_path / "release.json",
            candidate_result_file=tmp_path / "candidate.json",
            result_file=tmp_path / "result.json",
            claim_registry=tmp_path / "claims",
            requester=fake,
        )
    assert fake.requests == []
    assert not (tmp_path / "claims").exists()


def test_white_recovery_cli_starts_from_the_repository_root() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "tools/mf1750_ec5_white_recovery_once.py",
            "--help",
        ],
        cwd=runner.REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()


def test_wrong_rc2g_binary_is_rejected_before_network_or_claim(tmp_path: Path) -> None:
    wrong_binary = tmp_path / "wrong-rc2g.bin"
    payload = bytearray(FROZEN_BINARY.read_bytes())
    payload[0] ^= 1
    wrong_binary.write_bytes(payload)
    fake = FakeRC2G()
    with pytest.raises(runner.WhiteRecoveryError, match="hardware-proven RC2G"):
        runner.run_once(
            stage="baseline",
            base_url="http://192.0.2.1",
            authorization=runner.required_authorization("baseline"),
            panel_file=_panel(tmp_path),
            rc2g_binary_file=wrong_binary,
            result_file=tmp_path / "result.json",
            claim_registry=tmp_path / "claims",
            requester=fake,
        )
    assert fake.requests == []
    assert not (tmp_path / "claims").exists()


def test_empty_white_result_is_not_recovery_evidence(tmp_path: Path) -> None:
    result_file = tmp_path / "fake-white-result.json"
    result_file.write_text("{}\n", encoding="utf-8")
    with pytest.raises(runner.WhiteRecoveryError, match="fields differ"):
        runner.load_result_binding(
            result_file=result_file,
            panel_file=_panel(tmp_path),
            rc2g_binary_file=FROZEN_BINARY,
            claim_registry=tmp_path / "claims",
        )


def test_after_u07_missing_or_tampered_u04_chain_is_zero_network_and_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRC2G()
    common = {
        "stage": "after-u07",
        "base_url": "http://192.0.2.1",
        "authorization": runner.required_authorization("after-u07"),
        "panel_file": _panel(tmp_path),
        "rc2g_binary_file": FROZEN_BINARY,
        "release_file": tmp_path / "release.json",
        "candidate_result_file": tmp_path / "u07-result.json",
        "result_file": tmp_path / "white-result.json",
        "claim_registry": tmp_path / "claims",
        "requester": fake,
    }
    with pytest.raises(runner.WhiteRecoveryError, match="U07 replay requires"):
        runner.run_once(**common)
    assert fake.requests == []
    assert not (tmp_path / "claims").exists()

    def reject_binding(**_kwargs):  # type: ignore[no-untyped-def]
        raise runner.WhiteRecoveryError("candidate result replay failed: U04 review integrity")

    monkeypatch.setattr(runner, "load_candidate_result_binding", reject_binding)
    with pytest.raises(runner.WhiteRecoveryError, match="U04 review integrity"):
        runner.run_once(
            **common,
            u04_review_file=tmp_path / "tampered-review.json",
            u04_result_file=tmp_path / "u04-result.json",
            u04_hold_0_file=tmp_path / "hold0.json",
            u04_hold_5_file=tmp_path / "hold5.json",
            u04_hold_30_file=tmp_path / "hold30.json",
            u04_white_recovery_result_file=tmp_path / "after-u04-white.json",
            u04_rc2g_binary_file=FROZEN_BINARY,
            u04_white_claim_registry=tmp_path / "u04-white-claims",
        )
    assert fake.requests == []
    assert not (tmp_path / "claims").exists()
