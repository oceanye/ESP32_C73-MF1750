#!/usr/bin/env python3
"""Loopback-only application/Web UI server; offline unless explicitly enabled."""

from __future__ import annotations

import argparse
import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import sys
import threading
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application import (  # noqa: E402
    AdapterError,
    ApplicationArtifact,
    ApplicationError,
    ApplicationSession,
    FitPolicy,
    HttpDeviceAdapter,
    InputSource,
    OfflineAdapter,
    PreparationPurpose,
    SessionError,
    prepare_image,
)
from host.color_pipeline import (  # noqa: E402
    DitherMode,
    Palette,
    PipelineOptions,
    RasterImage,
    load_palette,
    reference_palette,
)
from host.epd_frame import FRAME_BYTES, HEIGHT, WIDTH, ControllerMapping  # noqa: E402


WEB_ROOT = REPO_ROOT / "web"
MAX_JSON_BODY = 64 * 1024
RGBA_BYTES = WIDTH * HEIGHT * 4
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def _strict_json(source: bytes) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    value = json.loads(source.decode("utf-8"), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError("JSON request must be an object")
    return value


def _mapping(value: Any, label: str) -> ControllerMapping:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{label} must be a four-item 0/1 array")
    if any(type(item) is not int or item not in (0, 1) for item in value):
        raise ValueError(f"{label} must contain only integer 0/1 values")
    return ControllerMapping(value[0], *(bool(item) for item in value[1:]))


def _mappings(value: Mapping[str, Any]) -> tuple[ControllerMapping, ControllerMapping]:
    return (_mapping(value.get("cs1"), "cs1"), _mapping(value.get("cs2"), "cs2"))


class ApplicationRuntime:
    def __init__(self, palette: Palette, adapter: OfflineAdapter | HttpDeviceAdapter) -> None:
        self.palette = palette
        self.session = ApplicationSession(adapter)
        self.lock = threading.RLock()

    def config(self) -> Mapping[str, Any]:
        calibration = self.palette.calibration
        return {
            "schema": "mf1750-application-config",
            "version": 1,
            "panel": {"width": WIDTH, "height": HEIGHT, "frame_bytes": FRAME_BYTES},
            "palette": {
                "id": self.palette.palette_id,
                "source": self.palette.source,
                "calibrated": self.palette.calibrated,
                "canonical_sha256": self.palette.canonical_sha256,
                "calibration": None
                if calibration is None
                else {
                    "measurement_id": calibration.measurement_id,
                    "artifact_sha256": calibration.artifact_sha256,
                },
            },
            "dither_modes": [mode.value for mode in DitherMode],
            "fit_policies": [policy.value for policy in FitPolicy],
            "device_adapter": type(self.session.adapter).__name__,
            "hardware_tested": False,
        }


class ApplicationHandler(BaseHTTPRequestHandler):
    server: "ApplicationHttpServer"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep logs local and limited to loopback application routes.  Device
        # URLs, request bodies, credentials and reports are never logged.
        sys.stderr.write("application-ui: " + (fmt % args) + "\n")

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'",
        )

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: Mapping[str, Any]) -> None:
        self._bytes(
            status,
            json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode(
                "utf-8"
            ),
            "application/json; charset=utf-8",
        )

    def _error(self, status: int, error: Exception) -> None:
        self._json(
            status,
            {
                "ok": False,
                "error": type(error).__name__,
                "detail": str(error),
                "hardware_tested": False,
            },
        )

    def _read(self, expected_max: int) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Content-Length must be an integer") from error
        if not 0 <= length <= expected_max:
            raise ValueError(f"request body exceeds the {expected_max}-byte limit")
        return self.rfile.read(length)

    def _read_json(self) -> Mapping[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        return _strict_json(self._read(MAX_JSON_BODY))

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                self._bytes(HTTPStatus.OK, (WEB_ROOT / filename).read_bytes(), content_type)
                return
            runtime = self.server.runtime
            with runtime.lock:
                if path == "/application/config":
                    self._json(HTTPStatus.OK, runtime.config())
                elif path == "/application/status":
                    self._json(HTTPStatus.OK, runtime.session.status())
                elif path == "/application/report":
                    self._json(HTTPStatus.OK, runtime.session.application_report())
                elif path == "/application/device/job":
                    self._json(HTTPStatus.OK, runtime.session.poll_job())
                elif path == "/application/device/report":
                    self._json(HTTPStatus.OK, runtime.session.retrieve_diagnostic())
                else:
                    self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
        except (AdapterError, ApplicationError, SessionError, ValueError) as error:
            self._error(HTTPStatus.CONFLICT, error)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        runtime = self.server.runtime
        try:
            with runtime.lock:
                if path == "/application/convert":
                    self._convert(runtime)
                    return
                data = self._read_json()
                if path == "/application/device/allow":
                    if data.get("allow") is not True:
                        raise ValueError("device allow requires allow=true")
                    result = runtime.session.allow_device_connection()
                elif path == "/application/device/preflight":
                    result = runtime.session.version_preflight(_mappings(data))
                elif path == "/application/device/ingress":
                    result = runtime.session.frame_ingress()
                elif path == "/application/device/arm":
                    confirmation = data.get("confirmation")
                    if not isinstance(confirmation, str):
                        raise ValueError("confirmation must be a string")
                    result = runtime.session.arm_refresh(confirmation)
                elif path == "/application/device/enqueue":
                    result = runtime.session.enqueue_refresh(_mappings(data))
                elif path == "/application/device/recover":
                    result = runtime.session.recover()
                elif path == "/application/device/local-abort":
                    result = runtime.session.local_abort()
                elif path == "/application/device/cancel":
                    result = runtime.session.cancel()
                else:
                    self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
                    return
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
        except (AdapterError, ApplicationError, SessionError, ValueError, json.JSONDecodeError) as error:
            self._error(HTTPStatus.CONFLICT, error)

    def _convert(self, runtime: ApplicationRuntime) -> None:
        if self.headers.get_content_type() != "application/octet-stream":
            raise ValueError("conversion Content-Type must be application/octet-stream")
        rgba = self._read(RGBA_BYTES)
        if len(rgba) != RGBA_BYTES:
            raise ValueError(f"normalized RGBA body must contain exactly {RGBA_BYTES} bytes")
        source_hash = self.headers.get("X-Input-SHA256", "")
        source = InputSource(
            "browser-selected-image",
            self.headers.get("X-Input-Media-Type", "application/octet-stream"),
            source_hash,
            "browser-computed SHA256 of original selected file bytes",
        )
        fit = self.headers.get("X-Fit-Policy", FitPolicy.CONTAIN.value)
        options = PipelineOptions(
            dither=self.headers.get("X-Dither-Mode", DitherMode.FLOYD_STEINBERG.value),
            text_mode=self.headers.get("X-Text-Mode", "false") == "true",
            white_protection=self.headers.get("X-White-Protection", "true") == "true",
        )
        artifact = prepare_image(
            RasterImage(WIDTH, HEIGHT, "RGBA", rgba),
            source,
            fit=FitPolicy.STRETCH,
            palette=runtime.palette,
            options=options,
            purpose=PreparationPurpose.OFFLINE_PREVIEW,
        )
        adjusted_report = dict(artifact.report)
        adjusted_normalization = dict(adjusted_report["normalization"])
        adjusted_normalization.update(
            {
                "fit": FitPolicy(fit).value,
                "performed_by": "browser_canvas_before_local_C2_quantization",
                "source_sha256_verification": "browser_declared_not_server_recomputed",
            }
        )
        adjusted_report["normalization"] = adjusted_normalization
        artifact = ApplicationArtifact(
            artifact.frame, artifact.preview_png, adjusted_report, artifact.upload_authorized
        )
        runtime.session.set_artifact(artifact)
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "preview_png_base64": base64.b64encode(artifact.preview_png).decode("ascii"),
                "report": artifact.report,
                "status": runtime.session.status(),
            },
        )


class ApplicationHttpServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], runtime: ApplicationRuntime) -> None:
        super().__init__(address, ApplicationHandler)
        self.runtime = runtime


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="listen address (default loopback)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--palette", type=Path, help="optional measured palette JSON")
    parser.add_argument("--enable-device", action="store_true", help="enable opt-in HTTP adapter")
    parser.add_argument("--device-url", help="explicit device root URL; never printed or reported")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if not ipaddress.ip_address(args.bind).is_loopback:
            raise SystemExit("--bind must be a numeric loopback address")
    except ValueError as error:
        raise SystemExit("--bind must be a numeric loopback address") from error
    if args.enable_device != bool(args.device_url):
        raise SystemExit("--enable-device and --device-url must be supplied together")
    palette = load_palette(args.palette) if args.palette else reference_palette()
    adapter: OfflineAdapter | HttpDeviceAdapter
    adapter = HttpDeviceAdapter(args.device_url) if args.enable_device else OfflineAdapter()
    runtime = ApplicationRuntime(palette, adapter)
    server = ApplicationHttpServer((args.bind, args.port), runtime)
    print(f"MF-1750 application UI: http://{args.bind}:{server.server_port}/")
    print("Hardware tested: NO; no device request is sent until UI connection permission.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
