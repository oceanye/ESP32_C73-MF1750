from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any

import pytest

from tools import mf1750_raw_p16_endpoint_gallery_v1_once as p16
from tools import (
    mf1750_raw_p16_endpoint_gallery_v1_white_containment_once as p16_post,
)
from tools import mf1750_runtime_lut_luma_gray_v1_once as luma


ORIGINS = (
    (p16._diagnostic_origin, p16.base.runner.RecheckError),  # noqa: SLF001
    (p16_post._private_origin, p16_post.base.ContainmentError),  # noqa: SLF001
    (luma._private_origin, luma.base.runner.RecheckError),  # noqa: SLF001
)
TRANSPORTS = (
    (p16._diagnostic_http_request, p16.urllib_request, p16._NoRedirect),  # noqa: SLF001
    (p16_post._direct_http_request, p16_post.urllib_request, p16_post._NoRedirect),  # noqa: SLF001
    (luma._direct_http_request, luma.urllib_request, luma._NoRedirect),  # noqa: SLF001
)


@pytest.mark.parametrize(("origin", "error_type"), ORIGINS)
def test_live_origins_are_strict_private_literal_ipv4_only(
    origin: Any, error_type: type[Exception]
) -> None:
    assert origin("http://192.168.1.7") == "http://192.168.1.7"
    assert origin("http://10.2.3.4:8080") == "http://10.2.3.4:8080"
    assert origin("http://127.0.0.1:80") == "http://127.0.0.1:80"
    assert origin("http://169.254.7.9") == "http://169.254.7.9"
    for invalid in (
        "https://192.168.1.7",
        "http://localhost",
        "http://8.8.8.8",
        "http://user@192.168.1.7",
        "http://user:secret@192.168.1.7",
        "http://192.168.1.7/",
        "http://192.168.1.7/api",
        "http://192.168.1.7?query=1",
        "http://192.168.1.7#fragment",
        "http://[::1]",
        "http://192.168.1.7:",
        "http://192.168.1.7:0",
        "http://192.168.1.7:65536",
    ):
        with pytest.raises(error_type):
            origin(invalid)


@pytest.mark.parametrize(("requester", "urllib_module", "redirect_type"), TRANSPORTS)
def test_live_transports_ignore_system_proxy_and_install_no_redirect(
    monkeypatch: pytest.MonkeyPatch,
    requester: Any,
    urllib_module: Any,
    redirect_type: type[Any],
) -> None:
    observed: dict[str, Any] = {}
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")

    class Response:
        status = 200

        def read(self, _limit: int) -> bytes:
            return b'{"ok":true}'

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Opener:
        def open(self, request: Any, *, timeout: float) -> Response:
            observed["url"] = request.full_url
            observed["method"] = request.get_method()
            observed["timeout"] = timeout
            return Response()

    def build_opener(*handlers: Any) -> Opener:
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(urllib_module, "build_opener", build_opener)
    status, value = requester(
        "http://192.168.1.7",
        "/api/test",
        method="POST",
        headers={"X-Test-Secret": "never-forward"},
        timeout=3,
    )
    assert status == 200
    assert value == {"ok": True}
    handlers = observed["handlers"]
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], redirect_type)
    assert observed == {
        "handlers": handlers,
        "url": "http://192.168.1.7/api/test",
        "method": "POST",
        "timeout": 3.0,
    }


@pytest.mark.parametrize(("requester", "_urllib_module", "_redirect_type"), TRANSPORTS)
@pytest.mark.parametrize("redirect_status", (301, 302, 307, 308))
def test_post_redirect_is_returned_without_replay(
    requester: Any,
    _urllib_module: Any,
    _redirect_type: type[Any],
    redirect_status: int,
) -> None:
    destination_requests = 0
    redirector_posts = 0

    class Destination(BaseHTTPRequestHandler):
        def _unexpected_request(self) -> None:
            nonlocal destination_requests
            destination_requests += 1
            payload = b'{"unexpected":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            self._unexpected_request()

        def do_GET(self) -> None:  # noqa: N802
            self._unexpected_request()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Redirector(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            nonlocal redirector_posts
            redirector_posts += 1
            payload = b'{"redirect":true}'
            self.send_response(redirect_status)
            self.send_header(
                "Location", f"http://127.0.0.1:{destination.server_port}/replayed"
            )
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    redirector = ThreadingHTTPServer(("127.0.0.1", 0), Redirector)
    workers = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (destination, redirector)
    ]
    for worker in workers:
        worker.start()
    try:
        status, value = requester(
            f"http://127.0.0.1:{redirector.server_port}",
            "/mutate",
            method="POST",
            headers={"X-EC5-Arm-Nonce": "must-not-be-forwarded"},
            timeout=3,
        )
    finally:
        destination.shutdown()
        redirector.shutdown()
        destination.server_close()
        redirector.server_close()
        for worker in workers:
            worker.join(timeout=2)
    assert status == redirect_status
    assert value == {"redirect": True}
    assert redirector_posts == 1
    assert destination_requests == 0


def test_pending_live_runners_bind_only_the_hardened_transport() -> None:
    assert p16.base.runner._origin is p16._diagnostic_origin  # noqa: SLF001
    assert p16.base.runner._http_request is p16._diagnostic_http_request  # noqa: SLF001
    assert p16_post.base._origin is p16_post._private_origin  # noqa: SLF001
    assert p16_post.base._default_requester is p16_post._direct_http_request  # noqa: SLF001
    assert p16_post.base.run_once is p16_post.run_once
    assert luma.base.runner._origin is luma._private_origin  # noqa: SLF001
    assert luma.base.runner._http_request is luma._direct_http_request  # noqa: SLF001


def test_p16_post_rejects_bad_origin_before_claim(tmp_path: Path) -> None:
    claims = tmp_path / "claims"
    with pytest.raises(p16_post.base.ContainmentError):
        p16_post.run_once(
            "http://user:secret@192.168.1.7",
            claims=claims,
            output=tmp_path / "result.json",
            sleeper=lambda _seconds: None,
        )
    assert not claims.exists()
