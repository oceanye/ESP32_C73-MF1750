from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence

import pytest

from tools import mf1750_app_only_single_boot_flash as helper


def _inputs(tmp_path: Path) -> dict[str, Any]:
    binary = tmp_path / "firmware.bin"
    binary.write_bytes(b"reviewed application image")
    python_exe = tmp_path / "python.exe"
    python_exe.write_bytes(b"placeholder")
    esptool = tmp_path / "esptool.py"
    esptool.write_bytes(b"placeholder")
    return {
        "port": "COM8",
        "binary": binary,
        "expected_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "output": tmp_path / "result.json",
        "python_exe": python_exe,
        "esptool_script": esptool,
        "confirm_j2_off": True,
    }


def test_success_uses_exact_two_step_single_boot_order(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        assert timeout_seconds == helper.DEFAULT_TIMEOUT_SECONDS
        calls.append(list(command))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"step-{len(calls)}-ok".encode(),
            stderr=b"",
        )

    result = helper.flash_and_verify_once(**inputs, runner=runner)

    assert result["success"] is True
    assert result["outcome"] == "app_only_write_verify_single_boot_pass"
    assert len(calls) == 2
    assert calls[0][-7:] == [
        "--before",
        "default_reset",
        "--after",
        "no_reset",
        "write_flash",
        "0x10000",
        str(inputs["binary"].resolve()),
    ]
    assert calls[1][-7:] == [
        "--before",
        "no_reset",
        "--after",
        "hard_reset",
        "verify_flash",
        "0x10000",
        str(inputs["binary"].resolve()),
    ]
    assert all("erase" not in token for command in calls for token in command)
    assert result["binary"]["preflight_verified"] is True
    assert result["binary"]["observed_sha256"] == inputs["expected_sha256"]
    assert result["steps"][0]["returncode"] == 0
    assert result["steps"][1]["returncode"] == 0
    assert (
        result["steps"][0]["stdout"]["sha256"]
        == hashlib.sha256(b"step-1-ok").hexdigest()
    )
    assert json.loads(inputs["output"].read_text(encoding="utf-8")) == result
    assert result["output_write_contract"] == "O_EXCL"


def test_write_failure_stops_before_verify_without_retry(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], _timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        return subprocess.CompletedProcess(
            command, 7, stdout=b"write failed", stderr=b"x"
        )

    result = helper.flash_and_verify_once(**inputs, runner=runner)

    assert len(calls) == 1
    assert result["outcome"] == "write_flash_failed_stopped_no_retry"
    assert result["success"] is False
    assert result["steps"][0]["returncode"] == 7
    assert result["steps"][1]["execution_state"] == "not_run"
    assert result["steps"][1]["returncode"] is None


def test_verify_failure_runs_exactly_twice_and_stops(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], _timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        return subprocess.CompletedProcess(
            command,
            0 if len(calls) == 1 else 9,
            stdout=b"output",
            stderr=b"verify failed" if len(calls) == 2 else b"",
        )

    result = helper.flash_and_verify_once(**inputs, runner=runner)

    assert len(calls) == 2
    assert result["outcome"] == "verify_flash_failed_stopped_no_retry"
    assert result["success"] is False
    assert [step["returncode"] for step in result["steps"]] == [0, 9]


def test_bad_bin_hash_writes_failure_evidence_without_subprocess(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    inputs["expected_sha256"] = "0" * 64
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], _timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        raise AssertionError("runner must not be called")

    result = helper.flash_and_verify_once(**inputs, runner=runner)

    assert calls == []
    assert result["outcome"] == "preflight_failed_no_hardware_action"
    assert result["binary"]["preflight_verified"] is False
    assert all(step["execution_state"] == "not_run" for step in result["steps"])
    assert json.loads(inputs["output"].read_text(encoding="utf-8")) == result


def test_output_exclusive_create_refuses_before_subprocess(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs["output"].write_text("occupied\n", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], _timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        raise AssertionError("runner must not be called")

    with pytest.raises(helper.FlashHelperError, match="overwrite"):
        helper.flash_and_verify_once(**inputs, runner=runner)

    assert calls == []
    assert inputs["output"].read_text(encoding="utf-8") == "occupied\n"


def test_confirmation_is_required_before_output_or_subprocess(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs["confirm_j2_off"] = False
    calls: list[list[str]] = []

    def runner(
        command: Sequence[str], _timeout_seconds: float
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        raise AssertionError("runner must not be called")

    with pytest.raises(helper.FlashHelperError, match="confirm-j2-off"):
        helper.flash_and_verify_once(**inputs, runner=runner)

    assert calls == []
    assert not inputs["output"].exists()
