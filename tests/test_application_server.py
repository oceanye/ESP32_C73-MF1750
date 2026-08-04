from __future__ import annotations

from http import HTTPStatus
import http.client
import json
import socket
import threading
import time
import unittest
from unittest import mock

from app.server import (
    BODY_READ_TIMEOUT_S,
    RGBA_BYTES,
    ApplicationHandler,
    ApplicationHttpServer,
    ApplicationRuntime,
    _strict_json,
)
from host.application import OfflineAdapter
from host.application import SessionError
from host.color_pipeline import reference_palette


class ApplicationServerSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())
        cls.server = ApplicationHttpServer(
            ("127.0.0.1", 0), cls.runtime, security_token="test-token-32-bytes-minimum-value"
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        host: str | None = None,
        token: str | None = None,
        origin: str | None = None,
        fetch_site: str | None = None,
        content_type: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {"Host": host if host is not None else self.server.authority}
        if token is not None:
            headers["X-Application-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        if fetch_site is not None:
            headers["Sec-Fetch-Site"] = fetch_site
        if content_type is not None:
            headers["Content-Type"] = content_type
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2.0
        )
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, response_headers, payload

    @property
    def valid_token(self) -> str:
        return self.server.security_token

    def valid_post(self, path: str, value: object) -> tuple[int, dict[str, str], bytes]:
        return self.request(
            "POST",
            path,
            body=json.dumps(value).encode("utf-8"),
            token=self.valid_token,
            origin=self.server.origin,
            fetch_site="same-origin",
            content_type="application/json",
        )

    def test_token_is_required_and_is_not_exposed_by_get(self) -> None:
        status, _, _ = self.request("GET", "/application/config")
        self.assertEqual(status, HTTPStatus.FORBIDDEN)
        status, _, _ = self.request(
            "GET", "/application/config", token="incorrect-token"
        )
        self.assertEqual(status, HTTPStatus.FORBIDDEN)

        status, _, payload = self.request(
            "GET", "/application/config", token=self.valid_token
        )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertNotIn(self.valid_token.encode("ascii"), payload)
        status, _, html = self.request("GET", "/")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertNotIn(self.valid_token.encode("ascii"), html)

    def test_host_origin_and_fetch_metadata_are_strict(self) -> None:
        status, _, _ = self.request(
            "GET",
            "/application/status",
            host=f"localhost:{self.server.server_port}",
            token=self.valid_token,
        )
        self.assertEqual(status, HTTPStatus.FORBIDDEN)

        body = b'{"allow":true}'
        for origin, fetch_site in (
            ("http://attacker.invalid", "same-origin"),
            (self.server.origin, "cross-site"),
            (None, None),
        ):
            status, _, _ = self.request(
                "POST",
                "/application/device/allow",
                body=body,
                token=self.valid_token,
                origin=origin,
                fetch_site=fetch_site,
                content_type="application/json",
            )
            self.assertEqual(status, HTTPStatus.FORBIDDEN)

    def test_security_headers_deny_framing(self) -> None:
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        csp = headers.get("content-security-policy", "")
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("form-action 'self'", csp)

    def test_queries_are_rejected_and_device_polling_get_has_no_side_effect(self) -> None:
        status, _, _ = self.request(
            "GET", "/application/status?debug=true", token=self.valid_token
        )
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)

        with mock.patch.object(
            self.runtime.session, "poll_job", return_value={"state": "queued"}
        ) as poll:
            status, _, _ = self.request(
                "GET", "/application/device/job", token=self.valid_token
            )
            self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED)
            poll.assert_not_called()

            status, _, payload = self.valid_post("/application/device/job", {})
            self.assertEqual(status, HTTPStatus.OK, payload)
            poll.assert_called_once_with()

    def test_status_does_not_wait_for_operation_lock(self) -> None:
        self.assertTrue(self.runtime.operation_lock.acquire(blocking=False))
        try:
            started = time.monotonic()
            status, _, payload = self.request(
                "GET", "/application/status", token=self.valid_token
            )
            elapsed = time.monotonic() - started
        finally:
            self.runtime.operation_lock.release()
        self.assertEqual(status, HTTPStatus.OK, payload)
        self.assertLess(elapsed, 0.5)
        snapshot = json.loads(payload)
        self.assertTrue(snapshot["operation_in_progress"])
        self.assertTrue(snapshot["refresh_locked"])
        self.assertFalse(snapshot["armed"])

        snapshot_started = threading.Event()
        mutation_entered = threading.Event()
        mutation_during_snapshot = threading.Event()
        worker_start_failed = threading.Event()
        original_status = self.runtime.session.status

        def delayed_status() -> object:
            snapshot_started.set()
            time.sleep(0.05)
            if mutation_entered.is_set():
                mutation_during_snapshot.set()
            return original_status()

        def concurrent_mutation() -> None:
            if not snapshot_started.wait(timeout=1.0):
                worker_start_failed.set()
                return
            with self.runtime.operation_lock:
                mutation_entered.set()

        worker = threading.Thread(target=concurrent_mutation)
        with mock.patch.object(self.runtime.session, "status", side_effect=delayed_status):
            worker.start()
            status, _, payload = self.request(
                "GET", "/application/status", token=self.valid_token
            )
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())
        self.assertFalse(worker_start_failed.is_set())
        self.assertFalse(mutation_during_snapshot.is_set())
        self.assertTrue(mutation_entered.is_set())
        self.assertEqual(status, HTTPStatus.OK, payload)
        self.assertFalse(json.loads(payload)["operation_in_progress"])

    def test_slow_partial_conversion_body_does_not_block_status(self) -> None:
        slow = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2.0)
        request_head = (
            "POST /application/convert HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            "Sec-Fetch-Site: same-origin\r\n"
            f"X-Application-Token: {self.valid_token}\r\n"
            "Content-Type: application/octet-stream\r\n"
            f"Content-Length: {RGBA_BYTES}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        slow.sendall(request_head + b"\x00" * 16)
        time.sleep(0.05)
        try:
            started = time.monotonic()
            status, _, payload = self.request(
                "GET", "/application/status", token=self.valid_token
            )
            elapsed = time.monotonic() - started
        finally:
            slow.close()
        self.assertEqual(status, HTTPStatus.OK, payload)
        self.assertLess(elapsed, BODY_READ_TIMEOUT_S * 0.75)

    def test_strict_boolean_and_json_parsing(self) -> None:
        parse = ApplicationHandler._strict_boolean_header
        self.assertTrue(parse("true", False, "flag"))
        self.assertFalse(parse("false", True, "flag"))
        with self.assertRaisesRegex(ValueError, "exactly"):
            parse("TRUE", False, "flag")
        with self.assertRaises(ValueError):
            _strict_json(b'{"value":NaN}')

    def test_generation_epoch_rejects_a_stale_conversion_commit(self) -> None:
        runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())
        with mock.patch.object(
            runtime.session, "invalidate_artifact", return_value={"state": "offline"}
        ):
            stale_epoch = runtime.begin_generation()
            current_epoch = runtime.begin_generation()
        self.assertGreater(current_epoch, stale_epoch)
        with self.assertRaisesRegex(SessionError, "settings changed"):
            runtime.commit_generation(stale_epoch, mock.sentinel.stale_artifact)
        with mock.patch.object(
            runtime.session, "set_artifact", return_value={"state": "ready"}
        ) as commit:
            result = runtime.commit_generation(
                current_epoch, mock.sentinel.current_artifact
            )
        self.assertEqual(result["state"], "ready")
        commit.assert_called_once_with(mock.sentinel.current_artifact)

    def test_injected_server_token_must_remain_high_entropy_and_url_safe(self) -> None:
        runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())
        for token in ("short", "x" * 31, "x" * 31 + "!"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, "32 URL-safe"):
                    ApplicationHttpServer(
                        ("127.0.0.1", 0), runtime, security_token=token
                    )
        with self.assertRaisesRegex(ValueError, "numeric loopback"):
            ApplicationHttpServer(
                ("0.0.0.0", 0),
                runtime,
                security_token="test-token-32-bytes-minimum-value",
            )


if __name__ == "__main__":
    unittest.main()
