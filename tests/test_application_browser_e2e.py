from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import importlib.metadata
import importlib.util
import json
import re
import threading
import time
import unittest
from urllib.parse import urlsplit

from app.server import ApplicationHttpServer, ApplicationRuntime
from host.application import (
    HttpDeviceAdapter,
    N6BrowserCampaignError,
    OfflineAdapter,
    VISIBLE_ABNORMALITY_SCENARIOS,
    build_n6_offline_manifest,
    build_n6_visible_abnormality_result,
    describe_n6_action_offline,
    validate_n6_action_description,
    validate_n6_offline_manifest,
)
from host.color_pipeline import reference_palette
from tests.application_browser_harness import (
    LoopbackFakeDeviceServer,
    TEST_BUILD_TAG,
    TEST_DRIVER_API,
)


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright.sync_api") is not None
PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None

PANEL = {
    "model": "MF1750-C73",
    "serial": "N6-LOOPBACK-NO-PANEL",
    "board_id": "N6-LOOPBACK-NO-BOARD",
    "pcb_revision": "test-only",
}
FIRMWARE = {
    "source_commit": "a" * 40,
    "build_tag": TEST_BUILD_TAG,
    "binary_sha256": "b" * 64,
    "driver_api": TEST_DRIVER_API,
}


def _wide_png() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (8, 2))
    image.putdata(
        [(230, 20, 20)] * 4
        + [(20, 40, 220)] * 4
        + [(20, 180, 40)] * 4
        + [(240, 210, 20)] * 4
    )
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _decode_preparation(value: str) -> dict[str, object]:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(value + padding))


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE and PILLOW_AVAILABLE,
    "local Playwright Chromium and Pillow are required",
)
class ApplicationRealBrowserE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.fake_clock = [1000.0]
        cls.fake_device = LoopbackFakeDeviceServer().start()
        cls.offline_runtime = ApplicationRuntime(reference_palette(), OfflineAdapter())
        cls.offline_server = ApplicationHttpServer(
            ("127.0.0.1", 0),
            cls.offline_runtime,
            security_token="n6-offline-browser-token-00000001",
        )
        cls.offline_thread = threading.Thread(
            target=cls.offline_server.serve_forever, daemon=True
        )
        cls.offline_thread.start()

        cls.http_adapter = HttpDeviceAdapter(
            cls.fake_device.origin, clock=lambda: cls.fake_clock[0]
        )
        cls.http_runtime = ApplicationRuntime(reference_palette(), cls.http_adapter)
        cls.http_server = ApplicationHttpServer(
            ("127.0.0.1", 0),
            cls.http_runtime,
            security_token="n6-http-browser-token-00000000001",
        )
        cls.http_thread = threading.Thread(
            target=cls.http_server.serve_forever, daemon=True
        )
        cls.http_thread.start()

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:
            cls.playwright.stop()
            cls._close_servers()
            raise unittest.SkipTest(f"local Chromium is unavailable: {error}") from error
        cls.browser_version = cls.browser.version

    @classmethod
    def _close_servers(cls) -> None:
        for server, thread in (
            (cls.offline_server, cls.offline_thread),
            (cls.http_server, cls.http_thread),
        ):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)
        cls.fake_device.close()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        cls._close_servers()

    def _page(self, server: ApplicationHttpServer):
        context = self.browser.new_context(service_workers="block")
        page = context.new_page()
        external: list[str] = []
        app_requests: list[tuple[str, str]] = []
        allowed_origin = server.origin

        def guard(route, request) -> None:  # type: ignore[no-untyped-def]
            parsed = urlsplit(request.url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme in {"blob", "data"} or origin == allowed_origin:
                route.continue_()
            else:
                external.append(request.url)
                route.abort()

        page.route("**/*", guard)
        page.on(
            "request",
            lambda request: app_requests.append(
                (request.method, urlsplit(request.url).path)
            ),
        )
        return context, page, external, app_requests

    @staticmethod
    def _open(page, server: ApplicationHttpServer) -> None:  # type: ignore[no-untyped-def]
        from playwright.sync_api import expect

        page.goto(f"{server.origin}/#token={server.security_token}")
        expect(page.locator("#paletteWarning")).not_to_contain_text(
            "正在读取", timeout=10_000
        )

    def test_00_default_ui_is_offline_and_has_no_device_request_path(self) -> None:
        from playwright.sync_api import expect

        context, page, external, requests = self._page(self.offline_server)
        try:
            self._open(page, self.offline_server)
            expect(page.locator("#adapterNotice")).to_contain_text("OfflineAdapter")
            expect(page.locator("#armButton")).to_be_disabled()
            expect(page.locator("#refreshButton")).to_be_disabled()
            self.assertEqual(self.fake_device.ledger.snapshot(), [])
            self.assertNotIn(("POST", "/application/device/enqueue"), requests)
            self.assertEqual(external, [])
            self.assertRegex(self.browser_version, r"^\d+\.\d+\.\d+\.\d+$")
            self.assertRegex(importlib.metadata.version("playwright"), r"^\d+\.\d+")
        finally:
            context.close()

    def test_01_real_convert_previews_geometry_and_fail_closed_device_gate(self) -> None:
        from PIL import Image
        from playwright.sync_api import expect

        source = _wide_png()
        context, page, external, app_requests = self._page(self.http_server)
        convert_requests = []

        def capture_convert(request) -> None:  # type: ignore[no-untyped-def]
            if urlsplit(request.url).path == "/application/convert-v2":
                convert_requests.append(request)

        page.on("request", capture_convert)
        try:
            self._open(page, self.http_server)
            expect(page.locator("#adapterNotice")).to_contain_text(
                "尚未获得 UI 连接许可"
            )
            self.assertEqual(self.fake_device.ledger.snapshot(), [])

            page.locator("#imageInput").set_input_files(
                {"name": "n6-wide.png", "mimeType": "image/png", "buffer": source}
            )
            page.locator("#gamutProfile").select_option("none")
            page.locator("#ditherMode").select_option("none")
            page.locator("#fitPolicy").select_option("contain")
            expect(page.locator("#generateButton")).to_be_enabled()
            page.locator("#generateButton").click()
            expect(page.locator("#offlineBadge")).to_have_text("YES", timeout=120_000)

            first = self.http_runtime.session.artifact
            self.assertIsNotNone(first)
            assert first is not None
            first_report = first.report
            self.assertEqual(first_report["purpose"], "offline_preview")
            self.assertFalse(first_report["formal_upload_authorized"])
            self.assertFalse(first_report["hardware_tested"])
            self.assertEqual(first_report["normalization"]["fit"], "contain")
            self.assertEqual(
                page.locator("#inputHash").inner_text(), hashlib.sha256(source).hexdigest()
            )
            self.assertEqual(
                page.locator("#frameHash").inner_text(), first.identity["frame_sha256"]
            )
            self.assertEqual(len(convert_requests), 1)
            preparation = _decode_preparation(
                convert_requests[0].headers["x-mf1750-preparation"]
            )
            self.assertEqual(preparation["purpose"], "offline_preview")
            self.assertEqual(preparation["geometry"]["fit"], "contain")
            self.assertEqual(
                preparation["source"]["expected_sha256"],
                hashlib.sha256(source).hexdigest(),
            )
            self.assertEqual(convert_requests[0].post_data_buffer, source)

            preview_payloads = {
                "source": first.source_preview_png,
                "mapped": first.mapped_preview_png,
                "final": first.preview_png,
                "model": first.model_preview_png,
            }
            image_ids = {
                "source": "sourcePreviewImage",
                "mapped": "mappedPreviewImage",
                "final": "previewImage",
                "model": "modelPreviewImage",
            }
            for stage, payload in preview_payloads.items():
                with self.subTest(stage=stage):
                    self.assertEqual(
                        hashlib.sha256(payload).hexdigest(),
                        first_report["previews"][stage]["sha256"],
                    )
                    locator = page.locator(f"#{image_ids[stage]}")
                    expect(locator).to_have_attribute("src", re.compile(r"^blob:"))
                    self.assertEqual(locator.evaluate("image => image.naturalWidth"), 1024)
                    self.assertEqual(locator.evaluate("image => image.naturalHeight"), 600)
            contained = Image.open(BytesIO(first.source_preview_png)).convert("RGB")
            self.assertEqual(contained.getpixel((0, 0)), (255, 255, 255))
            self.assertNotEqual(contained.getpixel((512, 300)), (255, 255, 255))
            first_report_sha = first.identity["report_sha256"]

            page.locator("#fitPolicy").select_option("cover")
            expect(page.locator("#offlineBadge")).to_have_text("PENDING")
            expect(page.locator("#generateButton")).to_be_enabled()
            page.locator("#generateButton").click()
            expect(page.locator("#offlineBadge")).to_have_text("YES", timeout=120_000)
            second = self.http_runtime.session.artifact
            self.assertIsNotNone(second)
            assert second is not None
            second_report = second.report
            self.assertEqual(second_report["normalization"]["fit"], "cover")
            self.assertNotEqual(
                second.identity["report_sha256"], first.identity["report_sha256"]
            )
            covered = Image.open(BytesIO(second.source_preview_png)).convert("RGB")
            self.assertNotEqual(covered.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(len(convert_requests), 2)
            second_preparation = _decode_preparation(
                convert_requests[1].headers["x-mf1750-preparation"]
            )
            self.assertEqual(second_preparation["geometry"]["fit"], "cover")

            stale = context.request.get(
                f"{self.http_server.origin}/application/artifact/"
                f"{first_report_sha}/preview/source",
                headers={"X-Application-Token": self.http_server.security_token},
            )
            self.assertEqual(stale.status, 409)

            manifest = build_n6_offline_manifest(
                second,
                self.http_runtime.config(),
                panel=PANEL,
                firmware=FIRMWARE,
            )
            validate_n6_offline_manifest(manifest)
            self.assertEqual(
                manifest,
                build_n6_offline_manifest(
                    second,
                    self.http_runtime.config(),
                    panel=PANEL,
                    firmware=FIRMWARE,
                ),
            )
            tampered_manifest = deepcopy(manifest)
            tampered_manifest["p0_claim_declaration"]["overridable"] = True
            with self.assertRaises(N6BrowserCampaignError):
                validate_n6_offline_manifest(tampered_manifest)
            description = describe_n6_action_offline(
                manifest, evaluated_at="2026-08-08T12:00:00+08:00"
            )
            validate_n6_action_description(description, manifest=manifest)
            tampered_description = deepcopy(description)
            tampered_description["second_frame_post_authorized"] = True
            with self.assertRaises(N6BrowserCampaignError):
                validate_n6_action_description(
                    tampered_description, manifest=manifest
                )
            self.assertFalse(description["hardware_ready"])
            self.assertFalse(description["hardware_execution_authorized"])
            self.assertFalse(description["claim_created"])
            self.assertEqual(description["actual_frame_post_request_count"], 0)
            self.assertEqual(description["actual_recovery_request_count"], 0)
            self.assertIn(
                "measured_palette_missing_or_unqualified", description["blockers"]
            )
            self.assertIn(
                "measured_gamut_profile_missing_or_unqualified",
                description["blockers"],
            )
            action = manifest["p0_campaign"]["actions"][0]
            self.assertEqual(
                manifest["p0_claim_declaration"], action["claim"]
            )
            self.assertFalse(action["identity"]["automatic_retry"])
            self.assertFalse(action["identity"]["automatic_recovery"])
            self.assertEqual(action["identity"]["request"]["maximum_post_requests"], 1)
            for scenario_id in VISIBLE_ABNORMALITY_SCENARIOS:
                result = build_n6_visible_abnormality_result(
                    manifest,
                    scenario_id=scenario_id,
                    completed_at="2026-08-08T12:01:00+08:00",
                    evidence_manifest_sha256="c" * 64,
                    observed_frame_post_count=1,
                )
                self.assertEqual(result["state"], "UNKNOWN_DO_NOT_RETRY")
                self.assertEqual(result["post_request_count"], 1)
                self.assertEqual(result["automatic_retry_count"], 0)
                self.assertFalse(result["retry_allowed"])
                self.assertFalse(result["recovery_performed"])

            page.locator("#cs1Mapping").fill("0,0,0,0")
            page.locator("#cs2Mapping").fill("1,0,0,0")
            page.locator("#allowConnection").click()
            expect(page.locator("#jobState")).to_have_text("connection_allowed")
            expect(page.locator("#preflightButton")).to_be_enabled()
            page.locator("#preflightButton").click()
            expect(page.locator("#jobState")).to_have_text("preflight_verified")
            expect(page.locator("#jobDetail")).to_contain_text(TEST_BUILD_TAG)
            self.assertEqual(self.fake_device.ledger.count("GET", "/api/version"), 1)
            expect(page.locator("#armButton")).to_be_disabled()
            expect(page.locator("#refreshButton")).to_be_disabled()

            enqueue_before = app_requests.count(
                ("POST", "/application/device/enqueue")
            )
            refresh = page.locator("#refreshButton")
            box = refresh.bounding_box()
            self.assertIsNotNone(box)
            assert box is not None
            for mode in (
                "http_202_wrong_job_and_report",
                "network_unknown",
            ):
                self.fake_device.mode = mode
                page.mouse.dblclick(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
            self.fake_clock[0] += 121.0
            page.wait_for_timeout(100)
            self.assertEqual(
                app_requests.count(("POST", "/application/device/enqueue")),
                enqueue_before,
            )
            self.assertEqual(self.fake_device.ledger.count("POST", "/api/frame"), 0)
            self.assertEqual(self.fake_device.ledger.count("GET", "/api/job"), 0)
            self.assertEqual(
                self.fake_device.ledger.count("GET", "/api/diagnostic/report"), 0
            )
            self.assertNotIn(
                ("POST", "/application/device/recover"), app_requests
            )

            current_report_sha = second.identity["report_sha256"]
            page.reload()
            expect(page.locator("#offlineBadge")).to_have_text("PENDING")
            expect(page.locator("#refreshButton")).to_be_disabled()
            deadline = time.monotonic() + 5.0
            while self.http_runtime.session.artifact is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(self.http_runtime.session.artifact)
            reloaded_stale = context.request.get(
                f"{self.http_server.origin}/application/artifact/"
                f"{current_report_sha}/preview/final",
                headers={"X-Application-Token": self.http_server.security_token},
            )
            self.assertEqual(reloaded_stale.status, 409)
            self.assertEqual(self.fake_device.ledger.count("POST", "/api/frame"), 0)
            self.assertNotIn(
                ("POST", "/application/device/recover"), app_requests
            )
            self.assertEqual(external, [])
        finally:
            context.close()

    def test_02_real_browser_token_and_origin_rejections(self) -> None:
        from playwright.sync_api import expect

        context, page, external, requests = self._page(self.offline_server)
        try:
            page.goto(self.offline_server.origin + "/")
            expect(page.locator("#errorDetail")).to_contain_text(
                "URL 中没有应用会话 token"
            )
            self.assertNotIn(("GET", "/application/config"), requests)

            page.goto(self.offline_server.origin + "/index.html#token=" + "z" * 32)
            expect(page.locator("#errorDetail")).to_contain_text(
                "invalid application session token"
            )

            missing = context.request.get(
                self.offline_server.origin + "/application/status"
            )
            wrong = context.request.get(
                self.offline_server.origin + "/application/status",
                headers={"X-Application-Token": "z" * 32},
            )
            cross_origin = context.request.post(
                self.offline_server.origin + "/application/artifact/invalidate",
                headers={
                    "X-Application-Token": self.offline_server.security_token,
                    "Origin": "http://127.0.0.1:1",
                    "Content-Type": "application/json",
                },
                data={},
            )
            self.assertEqual(missing.status, 403)
            self.assertEqual(wrong.status, 403)
            self.assertEqual(cross_origin.status, 403)
            self.assertEqual(self.fake_device.ledger.count("POST", "/api/frame"), 0)
            self.assertEqual(external, [])
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
