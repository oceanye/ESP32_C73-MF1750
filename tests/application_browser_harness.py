"""Strictly-loopback helpers for the real Chromium application E2E tests."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from typing import Any
from urllib.parse import urlsplit

from host.epd_frame import ControllerMapping, FRAME_BYTES, controller_stream, fnv1a


TEST_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
TEST_DRIVER_API = "MF1750_R16_CASCADE_V3"


def version_body() -> str:
    return "\n".join(
        (
            TEST_BUILD_TAG,
            "Panel: 1024x600",
            f"Driver API: {TEST_DRIVER_API}",
            "Frame bytes: 307200",
            "PSRAM bytes: 8388608",
            "Free PSRAM: 7900000",
            "Refresh SPI Hz: 1000000",
            "CS1 Mapping: 0,0,0,0",
            "CS2 Mapping: 1,0,0,0",
        )
    )


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    body_bytes: int


class RequestLedger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: list[RecordedRequest] = []

    def append(self, method: str, path: str, body_bytes: int) -> None:
        with self._lock:
            self._requests.append(RecordedRequest(method, path, body_bytes))

    def snapshot(self) -> list[RecordedRequest]:
        with self._lock:
            return list(self._requests)

    def count(self, method: str, path: str) -> int:
        return sum(
            item.method == method and item.path == path for item in self.snapshot()
        )


class _FakeDeviceHandler(BaseHTTPRequestHandler):
    server: "LoopbackFakeDeviceServer"

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args

    def _path(self) -> str:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            return ""
        return parsed.path

    def _body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        return self.rfile.read(max(0, length))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"),
            "application/json",
        )

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        self.server.ledger.append("GET", path, 0)
        if path == "/api/version":
            self._send(HTTPStatus.OK, version_body().encode("utf-8"), "text/plain")
            return
        if path == "/api/job":
            if self.server.mode == "success" and self.server.last_frame is not None:
                self._json(HTTPStatus.OK, _success_job(self.server.last_frame))
                return
            self._json(
                HTTPStatus.OK,
                {
                    "job_id": 999,
                    "action": "uploaded_frame",
                    "state": "completed",
                    "result": True,
                    "queued_at_ms": 1,
                    "started_at_ms": 2,
                    "finished_at_ms": 3,
                    "frame_fnv1a": 1,
                },
            )
            return
        if path == "/api/diagnostic/report":
            if self.server.mode == "success" and self.server.last_frame is not None:
                self._json(
                    HTTPStatus.OK, _success_diagnostic(self.server.last_frame)
                )
                return
            self._json(
                HTTPStatus.OK,
                {
                    "schema_version": 2,
                    "operation_id": 999,
                    "job_operation_id": 998,
                    "valid": False,
                },
            )
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = self._path()
        body = self._body()
        self.server.ledger.append("POST", path, len(body))
        mode = self.server.mode
        if path == "/api/frame" and mode == "network_unknown":
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        if path == "/api/frame":
            self.server.last_frame = bytes(body)
            if mode == "success":
                self._json(
                    HTTPStatus.ACCEPTED,
                    {
                        "ok": True,
                        "bytes": FRAME_BYTES,
                        "fnv1a": fnv1a(body),
                        "free_psram": 7_800_000,
                        "job_id": 7,
                    },
                )
                return
            self._json(
                HTTPStatus.ACCEPTED,
                {"accepted": True, "fnv1a": 1, "bytes": len(body), "job_id": 999},
            )
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")


class LoopbackFakeDeviceServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _FakeDeviceHandler)
        self.ledger = RequestLedger()
        self.mode = "http_202_wrong_job_and_report"
        self.last_frame: bytes | None = None
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def start(self) -> "LoopbackFakeDeviceServer":
        self._thread.start()
        return self

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=2.0)


def _success_job(frame: bytes) -> dict[str, Any]:
    return {
        "job_id": 7,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": 1000,
        "started_at_ms": 1010,
        "finished_at_ms": 33060,
        "frame_fnv1a": fnv1a(frame),
    }


def _busy_stage(
    wait_ms: int,
    *,
    gate: int = 1,
    before: int = 1,
    entry: int = 0,
    pre_idle: bool = True,
    assertion: bool = True,
) -> dict[str, Any]:
    return {
        "gate_entry_level": gate,
        "pre_command_level": before,
        "wait_entry_level": entry,
        "wait_exit_level": 1,
        "pre_command_idle_ok": pre_idle,
        "assertion_after_idle": assertion,
        "pre_command_wait_ms": 0,
        "wait_ms": wait_ms,
        "assertion_latency_ms": 0,
    }


def _success_diagnostic(frame: bytes) -> dict[str, Any]:
    mappings = (ControllerMapping(0), ControllerMapping(1))
    job = _success_job(frame)
    return {
        "schema_version": 2,
        "operation_id": 23,
        "job_operation_id": 23,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_assert_grace_ms": 250,
        "busy_missing_stage": "none",
        "mapping_applied": True,
        "spi_hz": 1_000_000,
        "input_fnv1a": fnv1a(frame),
        "cs1_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[0])),
        "cs2_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[1])),
        "total_ms": 32_000,
        "cs1_upload_ms": 1_500,
        "cs2_upload_ms": 1_500,
        "pon_ms": 10,
        "pon_busy_seen": True,
        "drf_ms": 25_000,
        "drf_busy_seen": True,
        "pof_ms": 20,
        "pof_busy_seen": True,
        "post_psr_ms": 20,
        "post_psr_busy_seen": False,
        "last_wait_ms": 20,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "firmware_build_tag": TEST_BUILD_TAG,
        "driver_api_version": TEST_DRIVER_API,
        "job_id": job["job_id"],
        "job_action": job["action"],
        "job_state": job["state"],
        "job_result": job["result"],
        "job_queued_at_ms": job["queued_at_ms"],
        "job_started_at_ms": job["started_at_ms"],
        "job_finished_at_ms": job["finished_at_ms"],
        "mapping": {
            "cs1_source_half": 0,
            "cs1_flip_x": False,
            "cs1_flip_y": False,
            "cs1_nibble_swap": False,
            "cs2_source_half": 1,
            "cs2_flip_x": False,
            "cs2_flip_y": False,
            "cs2_nibble_swap": False,
        },
        "pre_command_idle_failure": False,
        "pre_command_busy_stage": "none",
        "busy_trace_schema_version": 1,
        "busy_trace": {
            "idle_level": 1,
            "pre_command_idle_timeout_ms": 3000,
            "assert_grace_ms": 250,
            "reset": _busy_stage(
                5,
                gate=255,
                before=255,
                entry=0,
                pre_idle=False,
                assertion=False,
            ),
            "pon": _busy_stage(10),
            "drf": _busy_stage(25_000),
            "pof": _busy_stage(20),
            "post_psr": _busy_stage(20, entry=1, assertion=False),
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 0,
                "busy_after_5ms": 0,
            },
            "final_gpio": {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
        },
    }


__all__ = [
    "LoopbackFakeDeviceServer",
    "RecordedRequest",
    "RequestLedger",
    "TEST_BUILD_TAG",
    "TEST_DRIVER_API",
    "version_body",
]
