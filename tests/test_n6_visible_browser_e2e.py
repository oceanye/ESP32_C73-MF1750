from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

from app.server import ApplicationHttpServer, ApplicationRuntime
from host.application import OfflineAdapter
from host.application.n6_visible_execution import (
    N6_ARM_CONFIRMATION,
    AtomicN6ClaimStore,
    N6BrowserExecutionController,
    N6HttpRefreshDriver,
    measured_gamut_profile_from_n6_manifest,
    measured_palette_from_n6_manifest,
    validate_n6_protocol_receipt,
)
from tests.application_browser_harness import LoopbackFakeDeviceServer
from tests.n6_formal_fixture import (
    CLAIMED_AT,
    COMPLETED_AT,
    artifact_and_config,
    authorization,
    formal_manifest,
    runtime_observation,
    source_png,
)


class _LegacyOfflineBrowserController(N6BrowserExecutionController):
    """Keep the historical loopback E2E kernel test-only after live blocking."""

    def enqueue(self, mappings, *, token_validated, same_origin_validated):
        return self._enqueue_legacy_test_only(
            mappings,
            token_validated=token_validated,
            same_origin_validated=same_origin_validated,
        )


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright.sync_api") is not None
PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE and PILLOW_AVAILABLE,
    "local Playwright Chromium and Pillow are required",
)
class N6FormalRealBrowserE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:
            cls.playwright.stop()
            raise unittest.SkipTest(f"local Chromium is unavailable: {error}") from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def test_real_browser_exact_convert_arm_one_post_report_and_reload_lock(self) -> None:
        from playwright.sync_api import expect

        fake = LoopbackFakeDeviceServer().start()
        fake.mode = "success"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = formal_manifest()
            times = iter((CLAIMED_AT, COMPLETED_AT))
            controller = _LegacyOfflineBrowserController(
                manifest,
                authorization=authorization(),
                claim_store=AtomicN6ClaimStore(workspace),
                protocol_driver=N6HttpRefreshDriver(
                    fake.origin,
                    poll_interval_s=0.001,
                    sleeper=lambda _seconds: None,
                ),
                attempt_id="n6-real-browser-loopback-attempt",
                utc_now=times.__next__,
            )
            palette = measured_palette_from_n6_manifest(manifest)
            profile = measured_gamut_profile_from_n6_manifest(manifest)
            runtime = ApplicationRuntime(
                palette,
                OfflineAdapter(),
                gamut_profiles=(profile,),
                n6_formal_controller=controller,
            )
            server = ApplicationHttpServer(
                ("127.0.0.1", 0),
                runtime,
                security_token="n6-formal-real-browser-token-000001",
            )
            controller.set_runtime_observation(runtime_observation(server.origin))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            context = self.browser.new_context(service_workers="block")
            page = context.new_page()
            external: list[str] = []
            app_requests: list[tuple[str, str]] = []

            def guard(route, request) -> None:  # type: ignore[no-untyped-def]
                parsed = urlsplit(request.url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme in {"blob", "data"} or origin == server.origin:
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
            try:
                page.goto(f"{server.origin}/#token={server.security_token}")
                expect(page.locator("#adapterNotice")).to_contain_text(
                    "原子 claim", timeout=10_000
                )
                self.assertEqual(fake.ledger.snapshot(), [])

                source = source_png()
                page.locator("#imageInput").set_input_files(
                    {
                        "name": "n6-formal-source.png",
                        "mimeType": "image/png",
                        "buffer": source,
                    }
                )
                page.locator("#gamutProfile").select_option(profile.profile_id)
                page.locator("#ditherMode").select_option("none")
                page.locator("#fitPolicy").select_option("contain")
                page.locator("#rotationDegrees").select_option("0")
                page.locator("#generateButton").click()
                expect(page.locator("#offlineBadge")).to_have_text(
                    "YES", timeout=120_000
                )
                expected_artifact, _ = artifact_and_config()
                self.assertIsNotNone(runtime.session.artifact)
                assert runtime.session.artifact is not None
                self.assertEqual(
                    runtime.session.artifact.identity, expected_artifact.identity
                )
                for image_id in (
                    "sourcePreviewImage",
                    "mappedPreviewImage",
                    "previewImage",
                    "modelPreviewImage",
                ):
                    self.assertTrue(
                        page.locator(f"#{image_id}").get_attribute("src")
                    )

                page.locator("#cs1Mapping").fill("0,0,0,0")
                page.locator("#cs2Mapping").fill("1,0,0,0")
                page.locator("#allowConnection").click()
                expect(page.locator("#jobState")).to_have_text("connection_allowed")
                page.locator("#preflightButton").click()
                expect(page.locator("#jobState")).to_have_text("preflight_verified")
                self.assertEqual(fake.ledger.snapshot(), [])
                declaration = manifest["action"]["claim"]
                claim_path = (
                    workspace
                    / declaration["workspace_relative_registry"]
                    / declaration["filename"]
                )
                self.assertFalse(claim_path.exists())

                page.locator("#armPhrase").fill(N6_ARM_CONFIRMATION)
                page.locator("#armButton").click()
                expect(page.locator("#refreshButton")).to_be_enabled()
                page.locator("#refreshButton").click()
                expect(page.locator("#protocolBadge")).to_have_text(
                    "YES", timeout=30_000
                )
                self.assertTrue(claim_path.is_file())
                self.assertEqual(fake.ledger.count("GET", "/api/version"), 1)
                self.assertEqual(fake.ledger.count("POST", "/api/frame"), 1)
                self.assertEqual(fake.ledger.count("GET", "/api/job"), 1)
                self.assertEqual(
                    fake.ledger.count("GET", "/api/diagnostic/report"), 1
                )
                receipt = controller.receipt
                assert receipt is not None
                validate_n6_protocol_receipt(receipt, manifest=manifest)
                self.assertEqual(
                    receipt["browser_observation"]["preview_stages_verified"],
                    ["source", "mapped", "final", "model"],
                )
                self.assertTrue(receipt["browser_observation"]["token_validated"])
                self.assertTrue(
                    receipt["browser_observation"]["same_origin_mutations_validated"]
                )

                cross_origin = context.request.post(
                    server.origin + "/application/device/enqueue",
                    headers={
                        "X-Application-Token": server.security_token,
                        "Origin": "http://127.0.0.1:1",
                        "Content-Type": "application/json",
                    },
                    data={"cs1": [0, 0, 0, 0], "cs2": [1, 0, 0, 0]},
                )
                self.assertEqual(cross_origin.status, 403)

                page.reload()
                expect(page.locator("#refreshButton")).to_be_disabled()
                duplicate = context.request.post(
                    server.origin + "/application/device/enqueue",
                    headers={
                        "X-Application-Token": server.security_token,
                        "Origin": server.origin,
                        "Content-Type": "application/json",
                    },
                    data={"cs1": [0, 0, 0, 0], "cs2": [1, 0, 0, 0]},
                )
                self.assertEqual(duplicate.status, 409)
                self.assertEqual(fake.ledger.count("POST", "/api/frame"), 1)
                self.assertNotIn(
                    ("POST", "/application/device/recover"), app_requests
                )
                self.assertEqual(external, [])
            finally:
                context.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)
                fake.close()


if __name__ == "__main__":
    unittest.main()
