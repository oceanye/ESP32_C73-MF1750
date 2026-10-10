#!/usr/bin/env python3
"""Flash and verify one ESP32-S3 application without an intermediate app boot.

The helper is intentionally narrow: it writes one pre-hashed application image
at 0x10000, leaves the device in the bootloader, verifies the same image, and
only then performs the single hard reset which starts the application.  It
never erases or writes the bootloader, partition table, NVS, or any other
address.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Sequence


APP_ADDRESS = 0x10000
APP_ADDRESS_ARGUMENT = "0x10000"
CHIP = "esp32s3"
DEFAULT_BAUD = 460800
DEFAULT_TIMEOUT_SECONDS = 240.0
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
STDIO_TAIL_BYTES = 4096


class FlashHelperError(RuntimeError):
    """Raised before any esptool process when the invocation is unsafe."""


Runner = Callable[[Sequence[str], float], subprocess.CompletedProcess[Any]]


def _now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _canonical_sha256(sealed),
    }
    return sealed


def _stdio_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8", errors="replace")


def _stdio_summary(value: Any) -> dict[str, Any]:
    data = _stdio_bytes(value)
    tail = data[-STDIO_TAIL_BYTES:]
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "tail_utf8": tail.decode("utf-8", errors="replace"),
        "tail_bytes": len(tail),
        "truncated": len(tail) != len(data),
    }


def _command_sha256(command: Sequence[str]) -> str:
    return hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()


def _default_runner(
    command: Sequence[str], timeout_seconds: float
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603
        list(command),
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )


def _write_json_to_reserved_fd(fd: int, value: dict[str, Any]) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    written = 0
    while written < len(encoded):
        written += os.write(fd, encoded[written:])
    os.fsync(fd)


def _reserve_output(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise FlashHelperError(f"refusing to overwrite output: {path}") from error


def _build_commands(
    *,
    python_exe: Path,
    esptool_script: Path,
    port: str,
    baud: int,
    binary: Path,
) -> tuple[list[str], list[str]]:
    common = [
        str(python_exe),
        str(esptool_script),
        "--chip",
        CHIP,
        "--port",
        port,
        "--baud",
        str(baud),
    ]
    write = [
        *common,
        "--before",
        "default_reset",
        "--after",
        "no_reset",
        "write_flash",
        APP_ADDRESS_ARGUMENT,
        str(binary),
    ]
    verify = [
        *common,
        "--before",
        "no_reset",
        "--after",
        "hard_reset",
        "verify_flash",
        APP_ADDRESS_ARGUMENT,
        str(binary),
    ]
    return write, verify


def _step(name: str, command: Sequence[str]) -> dict[str, Any]:
    return {
        "name": name,
        "command": list(command),
        "command_sha256": _command_sha256(command),
        "execution_state": "not_run",
        "returncode": None,
        "stdout": _stdio_summary(b""),
        "stderr": _stdio_summary(b""),
    }


def _execute_step(
    step: dict[str, Any],
    *,
    runner: Runner,
    timeout_seconds: float,
) -> bool:
    try:
        completed = runner(step["command"], timeout_seconds)
    except subprocess.TimeoutExpired as error:
        step.update(
            {
                "execution_state": "timeout",
                "returncode": None,
                "stdout": _stdio_summary(error.stdout),
                "stderr": _stdio_summary(error.stderr),
                "timeout_seconds": timeout_seconds,
            }
        )
        return False
    except Exception as error:  # Preserve terminal evidence and stop.
        step.update(
            {
                "execution_state": "runner_error",
                "returncode": None,
                "stdout": _stdio_summary(b""),
                "stderr": _stdio_summary(str(error)),
                "runner_error_type": type(error).__name__,
            }
        )
        return False

    step.update(
        {
            "execution_state": (
                "complete_pass" if completed.returncode == 0 else "complete_fail"
            ),
            "returncode": int(completed.returncode),
            "stdout": _stdio_summary(completed.stdout),
            "stderr": _stdio_summary(completed.stderr),
        }
    )
    return completed.returncode == 0


def flash_and_verify_once(
    *,
    port: str,
    binary: Path,
    expected_sha256: str,
    output: Path,
    python_exe: Path,
    esptool_script: Path,
    confirm_j2_off: bool,
    baud: int = DEFAULT_BAUD,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    """Run the fixed two-command transaction and seal its terminal evidence."""

    if confirm_j2_off is not True:
        raise FlashHelperError("explicit --confirm-j2-off is required")
    if not port or not port.strip():
        raise FlashHelperError("a non-empty serial port is required")
    if baud <= 0:
        raise FlashHelperError("baud must be positive")
    if timeout_seconds <= 0:
        raise FlashHelperError("timeout must be positive")

    binary = Path(binary).resolve()
    output = Path(output).resolve()
    python_exe = Path(python_exe).resolve()
    esptool_script = Path(esptool_script).resolve()
    write_command, verify_command = _build_commands(
        python_exe=python_exe,
        esptool_script=esptool_script,
        port=port.strip(),
        baud=baud,
        binary=binary,
    )
    steps = [
        _step("write_flash_stay_in_bootloader", write_command),
        _step("verify_flash_then_single_hard_reset", verify_command),
    ]
    fd = _reserve_output(output)
    started_at = _now()
    record: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-app-only-single-boot-flash-result",
        "started_at": started_at,
        "finished_at": None,
        "outcome": "running",
        "success": False,
        "j2_confirmed_off": True,
        "output_file": str(output),
        "output_write_contract": "O_EXCL",
        "binary": {
            "path": str(binary),
            "bytes": None,
            "expected_sha256": expected_sha256.lower(),
            "observed_sha256": None,
            "preflight_verified": False,
        },
        "transport": {
            "chip": CHIP,
            "port": port.strip(),
            "baud": baud,
            "fixed_application_address": APP_ADDRESS_ARGUMENT,
            "python_exe": str(python_exe),
            "esptool_script": str(esptool_script),
            "timeout_seconds_per_command": timeout_seconds,
        },
        "steps": steps,
        "constraints": {
            "application_only": True,
            "application_start_count_after_write": 1,
            "write_before": "default_reset",
            "write_after": "no_reset",
            "verify_before": "no_reset",
            "verify_after": "hard_reset",
            "bootloader_write": False,
            "partition_table_write": False,
            "nvs_write_or_erase": False,
            "erase_command": False,
            "retry": False,
            "fallback": False,
            "recovery": False,
            "subsequent_hardware_action_after_failure": False,
        },
    }

    try:
        try:
            if SHA256_RE.fullmatch(expected_sha256) is None:
                raise FlashHelperError("expected BIN SHA-256 is malformed")
            if not binary.is_file():
                raise FlashHelperError(f"BIN is missing: {binary}")
            if not python_exe.is_file():
                raise FlashHelperError(f"Python executable is missing: {python_exe}")
            if not esptool_script.is_file():
                raise FlashHelperError(f"esptool script is missing: {esptool_script}")

            data = binary.read_bytes()
            observed_sha256 = hashlib.sha256(data).hexdigest()
            record["binary"].update(
                {
                    "bytes": len(data),
                    "observed_sha256": observed_sha256,
                }
            )
            if observed_sha256 != expected_sha256.lower():
                raise FlashHelperError("BIN SHA-256 differs; no esptool command run")
            record["binary"]["preflight_verified"] = True

            if not _execute_step(
                steps[0], runner=runner, timeout_seconds=timeout_seconds
            ):
                record["outcome"] = "write_flash_failed_stopped_no_retry"
            elif not _execute_step(
                steps[1], runner=runner, timeout_seconds=timeout_seconds
            ):
                record["outcome"] = "verify_flash_failed_stopped_no_retry"
            else:
                record["outcome"] = "app_only_write_verify_single_boot_pass"
                record["success"] = True
        except Exception as error:
            record["outcome"] = "preflight_failed_no_hardware_action"
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        record["finished_at"] = _now()
        sealed = _seal(record)
        _write_json_to_reserved_fd(fd, sealed)
        return sealed
    finally:
        os.close(fd)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--bin", type=Path, required=True, dest="binary")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-exe", type=Path, required=True)
    parser.add_argument("--esptool-script", type=Path, required=True)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--confirm-j2-off", action="store_true", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = flash_and_verify_once(
            port=args.port,
            binary=args.binary,
            expected_sha256=args.expected_sha256,
            output=args.output,
            python_exe=args.python_exe,
            esptool_script=args.esptool_script,
            confirm_j2_off=args.confirm_j2_off,
            baud=args.baud,
            timeout_seconds=args.timeout_seconds,
        )
    except FlashHelperError as error:
        print(f"single-boot flash helper error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["success"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
