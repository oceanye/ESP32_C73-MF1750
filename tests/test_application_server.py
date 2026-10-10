from __future__ import annotations

from http import HTTPStatus
import base64
import hashlib
import http.client
import json
import socket
import threading
import time
from types import SimpleNamespace
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
        extra_headers: dict[str, str] | None = None,
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
        if extra_headers is not None:
            headers.update(extra_headers)
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

    def v2_metadata(
        self, source: bytes, *, algorithm: str = "atkinson"
    ) -> dict[str, object]:
        profile = next(iter(self.runtime.gamut_profiles.values()))
        supports_budget = algorithm in {"multicolor-dbs", "overlap-aware-dbs"}
        return {
            "schema": "mf1750-prepare-request",
            "version": 2,
            "source": {
                "expected_sha256": hashlib.sha256(source).hexdigest(),
                "media_type": "image/png",
            },
            "geometry": {"fit": "contain", "rotation_degrees": 0},
            "mapping": {
                "algorithm": "spectra6-xyz-convex-v1",
                "profile_id": profile.profile_id,
                "profile_sha256": profile.canonical_sha256,
                "intent": "perceptual",
                "strength": 1.0,
            },
            "halftone": {
                "algorithm": algorithm,
                "seed": 7,
                "budget": (
                    {
                        "kind": "deterministic-work-v1",
                        "max_evaluations": 8,
                        "max_accepted_moves": 2,
                        "stagnation_evaluations": 4,
                    }
                    if supports_budget
                    else None
                ),
            },
            "protections": {"white": True, "edge": True, "text": False},
            "purpose": "offline_preview",
        }

    @staticmethod
    def encode_v2_metadata(value: object) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

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

    def test_generation_work_is_visible_as_fail_closed_status(self) -> None:
        runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())
        self.assertTrue(runtime.try_begin_generation_work())
        try:
            status = runtime.status()
            self.assertTrue(status["operation_in_progress"])
            self.assertTrue(status["refresh_locked"])
            self.assertFalse(status["armed"])
            self.assertFalse(runtime.try_begin_generation_work())
        finally:
            runtime.end_generation_work()
        self.assertFalse(runtime.status()["operation_in_progress"])

    def test_preview_publication_rejects_mismatch_and_stale_report_urls(self) -> None:
        runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())

        def artifact(identity_character: str, prefix: bytes) -> SimpleNamespace:
            return SimpleNamespace(
                identity={"report_sha256": identity_character * 64},
                source_preview_png=prefix + b"source",
                mapped_preview_png=prefix + b"mapped",
                preview_png=prefix + b"final",
                model_preview_png=prefix + b"model",
            )

        first = artifact("1", b"one-")
        second = artifact("2", b"two-")

        def bind(value: object) -> dict[str, object]:
            runtime.session.artifact = value  # type: ignore[assignment]
            return {"state": "offline"}

        with (
            mock.patch.object(runtime.session, "invalidate_artifact", return_value={}),
            mock.patch.object(runtime.session, "set_artifact", side_effect=bind),
        ):
            first_epoch = runtime.begin_generation()
            with self.assertRaisesRegex(SessionError, "preview source differs"):
                runtime.commit_generation(
                    first_epoch,
                    first,  # type: ignore[arg-type]
                    {
                        "source": b"wrong",
                        "mapped": first.mapped_preview_png,
                        "final": first.preview_png,
                        "model": first.model_preview_png,
                    },
                )
            runtime.commit_generation(
                first_epoch,
                first,  # type: ignore[arg-type]
                {
                    "source": first.source_preview_png,
                    "mapped": first.mapped_preview_png,
                    "final": first.preview_png,
                    "model": first.model_preview_png,
                },
            )
            self.assertEqual(runtime.preview("1" * 64, "source"), b"one-source")
            second_epoch = runtime.begin_generation()
            runtime.commit_generation(
                second_epoch,
                second,  # type: ignore[arg-type]
                {
                    "source": second.source_preview_png,
                    "mapped": second.mapped_preview_png,
                    "final": second.preview_png,
                    "model": second.model_preview_png,
                },
            )
            with self.assertRaisesRegex(SessionError, "stale"):
                runtime.preview("1" * 64, "source")
            self.assertEqual(runtime.preview("2" * 64, "source"), b"two-source")

    def test_v2_original_byte_route_binds_four_hashed_preview_urls(self) -> None:
        source = b"mocked-png-source"
        preparation = self.v2_metadata(source)
        preview_payloads = {
            stage: f"{stage}-png".encode("ascii")
            for stage in ("source", "mapped", "final", "model")
        }
        preview_metadata = {
            stage: {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "width": 1024,
                "height": 600,
                "semantics": stage,
            }
            for stage, payload in preview_payloads.items()
        }
        identity = {
            "frame_sha256": "1" * 64,
            "frame_fnv1a": 1,
            "frame_bytes": 307200,
            "report_sha256": "2" * 64,
        }
        fake_artifact = SimpleNamespace(
            identity=identity,
            report={"previews": preview_metadata, "hardware_tested": False},
            source_preview_png=preview_payloads["source"],
            mapped_preview_png=preview_payloads["mapped"],
            preview_png=preview_payloads["final"],
            model_preview_png=preview_payloads["model"],
        )
        fake_simulation = SimpleNamespace()
        fake_decoded = SimpleNamespace(
            source_sha256=hashlib.sha256(source).hexdigest(),
            raster=mock.sentinel.raster,
            provenance={"hardware_tested": False},
        )

        def bind_fake(artifact: object) -> dict[str, object]:
            self.runtime.session.artifact = artifact  # type: ignore[assignment]
            return {"state": "offline"}

        with (
            mock.patch("app.server.decode_normalized_source", return_value=fake_decoded),
            mock.patch("app.server.simulate_panel", return_value=fake_simulation),
            mock.patch(
                "app.server.prepare_simulation_artifact",
                return_value=fake_artifact,
            ),
            mock.patch.object(
                self.runtime.session, "set_artifact", side_effect=bind_fake
            ),
        ):
            status, _, payload = self.request(
                "POST",
                "/application/convert-v2",
                body=source,
                token=self.valid_token,
                origin=self.server.origin,
                fetch_site="same-origin",
                content_type="image/png",
                extra_headers={
                    "X-MF1750-Preparation": self.encode_v2_metadata(preparation)
                },
            )
            self.assertEqual(status, HTTPStatus.OK, payload)
            response = json.loads(payload)
            self.assertEqual(response["schema"], "mf1750-prepare-response")
            self.assertEqual(response["artifact_identity"], identity)
            for stage, expected in preview_payloads.items():
                metadata = response["previews"][stage]
                self.assertEqual(metadata["sha256"], preview_metadata[stage]["sha256"])
                preview_status, headers, preview = self.request(
                    "GET", metadata["url"], token=self.valid_token
                )
                self.assertEqual(preview_status, HTTPStatus.OK)
                self.assertEqual(headers["content-type"], "image/png")
                self.assertEqual(preview, expected)

    def test_v2_recomputes_source_hash_before_decode_or_state_mutation(self) -> None:
        source = b"mocked-png-source"
        preparation = self.v2_metadata(source)
        preparation["source"]["expected_sha256"] = "0" * 64  # type: ignore[index]
        epoch = self.runtime.generation_epoch
        with mock.patch("app.server.decode_normalized_source") as decode:
            status, _, payload = self.request(
                "POST",
                "/application/convert-v2",
                body=source,
                token=self.valid_token,
                origin=self.server.origin,
                fetch_site="same-origin",
                content_type="image/png",
                extra_headers={
                    "X-MF1750-Preparation": self.encode_v2_metadata(preparation)
                },
            )
        self.assertEqual(status, HTTPStatus.CONFLICT, payload)
        self.assertIn(b"server-recomputed source SHA-256", payload)
        decode.assert_not_called()
        self.assertEqual(self.runtime.generation_epoch, epoch)

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
