#!/usr/bin/env python3
"""Loopback-only application/Web UI server; offline unless explicitly enabled."""

from __future__ import annotations

import argparse
import base64
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import sys
import threading
from typing import Any, Callable, Mapping, Optional, Sequence, TypeVar
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
BODY_READ_TIMEOUT_S = 1.0
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}

_T = TypeVar("_T")


class RequestRejected(ValueError):
    """A request which must be rejected before application state is touched."""

    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status


def _strict_json(source: bytes) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value!r} is not allowed")

    value = json.loads(
        source.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
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
        # Device mutations are serialized, but the lock is deliberately not
        # held while a request body is arriving or an image is quantized.  It
        # is also never needed by status/config reads, so a slow device cannot
        # make the recovery UI blind.
        self.operation_lock = threading.Lock()
        self.generation_epoch = 0

    def invalidate_artifact(self) -> Mapping[str, Any]:
        result = self.session.invalidate_artifact()
        self.generation_epoch += 1
        return result

    def begin_generation(self) -> int:
        self.session.invalidate_artifact()
        self.generation_epoch += 1
        return self.generation_epoch

    def commit_generation(
        self, epoch: int, artifact: ApplicationArtifact
    ) -> Mapping[str, Any]:
        if epoch != self.generation_epoch:
            raise SessionError("image settings changed while conversion was in progress")
        return self.session.set_artifact(artifact)

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

    def status(self) -> Mapping[str, Any]:
        # If the lock is available, hold it across the entire session snapshot
        # so a mutation cannot complete between reading state and checking the
        # lock.  If a slow device owns it, remain responsive but fail closed:
        # the concurrent fields are informational only until the UI polls a
        # subsequent lock-protected snapshot.
        snapshot_lock_held = self.operation_lock.acquire(blocking=False)
        if snapshot_lock_held:
            try:
                status = dict(self.session.status())
            finally:
                self.operation_lock.release()
            status["operation_in_progress"] = False
            return status

        status = dict(self.session.status())
        status["operation_in_progress"] = True
        status["refresh_locked"] = True
        status["armed"] = False
        return status


class ApplicationHandler(BaseHTTPRequestHandler):
    server: "ApplicationHttpServer"

    def log_message(self, fmt: str, *args: object) -> None:
        # BaseHTTPRequestHandler may pass the complete request line here.  Do
        # not echo it: query strings can contain accidental secrets.
        del fmt, args

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = urlsplit(getattr(self, "path", "")).path or "/"
        sys.stderr.write(
            f"application-ui: {getattr(self, 'command', '-')} {path} {code} {size}\n"
        )

    def log_error(self, fmt: str, *args: object) -> None:
        del fmt, args
        sys.stderr.write("application-ui: request error\n")

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Frame-Options", "DENY")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        try:
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            # A timed-out/short-body client may disconnect before receiving
            # the bounded error response.  Its application operation was
            # never entered, so only close this request thread quietly.
            self.close_connection = True

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
        if self.headers.get("Transfer-Encoding") is not None:
            raise ValueError("Transfer-Encoding is not accepted")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise ValueError("Content-Length is required")
        raw_length = lengths[0]
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Content-Length must be an integer") from error
        if not 0 <= length <= expected_max:
            raise ValueError(f"request body exceeds the {expected_max}-byte limit")
        previous_timeout = self.connection.gettimeout()
        self.connection.settimeout(BODY_READ_TIMEOUT_S)
        try:
            body = self.rfile.read(length)
        except TimeoutError as error:
            self.close_connection = True
            raise RequestRejected(
                HTTPStatus.REQUEST_TIMEOUT, "request body read timed out"
            ) from error
        finally:
            self.connection.settimeout(previous_timeout)
        if len(body) != length:
            self.close_connection = True
            raise RequestRejected(
                HTTPStatus.BAD_REQUEST,
                f"short request body: expected {length} bytes, received {len(body)}",
            )
        return body

    def _read_json(self) -> Mapping[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        return _strict_json(self._read(MAX_JSON_BODY))

    @property
    def _authority(self) -> str:
        return self.server.authority

    def _request_path(self) -> str:
        target = urlsplit(self.path)
        if target.query or target.fragment:
            raise RequestRejected(HTTPStatus.BAD_REQUEST, "query strings are not accepted")
        return target.path

    def _validate_host(self) -> None:
        values = self.headers.get_all("Host", [])
        if len(values) != 1 or values[0] != self._authority:
            raise RequestRejected(HTTPStatus.FORBIDDEN, "Host is not the bound loopback authority")

    def _validate_api_token(self) -> None:
        values = self.headers.get_all("X-Application-Token", [])
        if len(values) != 1 or not hmac.compare_digest(
            values[0].encode("utf-8"), self.server.security_token.encode("ascii")
        ):
            raise RequestRejected(HTTPStatus.FORBIDDEN, "invalid application session token")

    def _validate_post_origin(self) -> None:
        origins = self.headers.get_all("Origin", [])
        if len(origins) != 1 or origins[0] != self.server.origin:
            raise RequestRejected(HTTPStatus.FORBIDDEN, "POST requires the loopback same origin")
        fetch_sites = self.headers.get_all("Sec-Fetch-Site", [])
        if len(fetch_sites) > 1 or (fetch_sites and fetch_sites[0] != "same-origin"):
            raise RequestRejected(HTTPStatus.FORBIDDEN, "cross-site POST is not accepted")

    def _authorize(self, path: str, *, post: bool) -> None:
        self._validate_host()
        if path.startswith("/application/"):
            self._validate_api_token()
        if post:
            self._validate_post_origin()

    def _operation(self, callback: Callable[[], _T]) -> _T:
        lock = self.server.runtime.operation_lock
        if not lock.acquire(blocking=False):
            raise RequestRejected(
                HTTPStatus.CONFLICT, "another application mutation is already in progress"
            )
        try:
            return callback()
        finally:
            lock.release()

    @staticmethod
    def _strict_boolean_header(value: Optional[str], default: bool, label: str) -> bool:
        if value is None:
            return default
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError(f"{label} must be exactly 'true' or 'false'")

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self._request_path()
            self._authorize(path, post=False)
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                self._bytes(HTTPStatus.OK, (WEB_ROOT / filename).read_bytes(), content_type)
                return
            runtime = self.server.runtime
            if path == "/application/config":
                self._json(HTTPStatus.OK, runtime.config())
            elif path == "/application/status":
                self._json(HTTPStatus.OK, runtime.status())
            elif path == "/application/report":
                self._json(HTTPStatus.OK, runtime.session.application_report())
            elif path in {"/application/device/job", "/application/device/report"}:
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, ValueError("route requires POST"))
            else:
                self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
        except RequestRejected as error:
            self._error(error.status, error)
        except (AdapterError, ApplicationError, SessionError, ValueError) as error:
            self._error(HTTPStatus.CONFLICT, error)

    def do_POST(self) -> None:  # noqa: N802
        runtime = self.server.runtime
        try:
            path = self._request_path()
            self._authorize(path, post=True)
            if path == "/application/convert":
                self._convert(runtime)
                return
            known_routes = {
                "/application/artifact/invalidate",
                "/application/device/allow",
                "/application/device/preflight",
                "/application/device/ingress",
                "/application/device/arm",
                "/application/device/enqueue",
                "/application/device/job",
                "/application/device/report",
                "/application/device/recover",
                "/application/device/local-abort",
                "/application/device/cancel",
            }
            if path not in known_routes:
                self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
                return
            data = self._read_json()

            def mutate() -> Mapping[str, Any]:
                if path == "/application/artifact/invalidate":
                    return runtime.invalidate_artifact()
                if path == "/application/device/allow":
                    if data.get("allow") is not True:
                        raise ValueError("device allow requires allow=true")
                    return runtime.session.allow_device_connection()
                if path == "/application/device/preflight":
                    return runtime.session.version_preflight(_mappings(data))
                if path == "/application/device/ingress":
                    return runtime.session.frame_ingress()
                if path == "/application/device/arm":
                    confirmation = data.get("confirmation")
                    if not isinstance(confirmation, str):
                        raise ValueError("confirmation must be a string")
                    return runtime.session.arm_refresh(confirmation)
                if path == "/application/device/enqueue":
                    return runtime.session.enqueue_refresh(_mappings(data))
                if path == "/application/device/job":
                    return runtime.session.poll_job()
                if path == "/application/device/report":
                    return runtime.session.retrieve_diagnostic()
                if path == "/application/device/recover":
                    return runtime.session.recover()
                if path == "/application/device/local-abort":
                    return runtime.session.local_abort()
                return runtime.session.cancel()

            result = self._operation(mutate)
            self._json(HTTPStatus.OK, {"ok": True, "result": result})
        except RequestRejected as error:
            self._error(error.status, error)
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
        generation_epoch = self._operation(runtime.begin_generation)
        fit = self.headers.get("X-Fit-Policy", FitPolicy.CONTAIN.value)
        options = PipelineOptions(
            dither=self.headers.get("X-Dither-Mode", DitherMode.FLOYD_STEINBERG.value),
            text_mode=self._strict_boolean_header(
                self.headers.get("X-Text-Mode"), False, "X-Text-Mode"
            ),
            white_protection=self._strict_boolean_header(
                self.headers.get("X-White-Protection"), True, "X-White-Protection"
            ),
        )
        artifact = prepare_image(
            RasterImage(WIDTH, HEIGHT, "RGBA", rgba),
            source,
            fit=FitPolicy.STRETCH,
            palette=runtime.palette,
            options=options,
            purpose=(
                PreparationPurpose.FORMAL_UPLOAD
                if runtime.palette.calibrated
                else PreparationPurpose.OFFLINE_PREVIEW
            ),
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
        status = self._operation(
            lambda: runtime.commit_generation(generation_epoch, artifact)
        )
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "preview_png_base64": base64.b64encode(artifact.preview_png).decode("ascii"),
                "report": artifact.report,
                "status": status,
            },
        )


class ApplicationHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        runtime: ApplicationRuntime,
        *,
        security_token: Optional[str] = None,
    ) -> None:
        if security_token is not None and (
            not isinstance(security_token, str)
            or len(security_token) < 32
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in security_token
            )
        ):
            raise ValueError(
                "security_token must contain at least 32 URL-safe ASCII characters"
            )
        requested_address = ipaddress.ip_address(address[0])
        if not requested_address.is_loopback:
            raise ValueError("server address must be a numeric loopback address")
        self.address_family = (
            socket.AF_INET6 if requested_address.version == 6 else socket.AF_INET
        )
        super().__init__(address, ApplicationHandler)
        self.runtime = runtime
        self.security_token = security_token or secrets.token_urlsafe(32)
        bound_host = str(self.server_address[0])
        address_literal = ipaddress.ip_address(bound_host)
        display_host = f"[{bound_host}]" if address_literal.version == 6 else bound_host
        self.authority = f"{display_host}:{self.server_port}"
        self.origin = f"http://{self.authority}"


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
    print(f"MF-1750 application UI: {server.origin}/#token={server.security_token}")
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
