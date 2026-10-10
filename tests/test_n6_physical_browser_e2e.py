from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

from app.server import ApplicationHttpServer, ApplicationRuntime
from host.application import OfflineAdapter
from host.application.n6_physical_execution import (
    N6PhysicalBrowserController,
    N6PhysicalExecutionError,
    N6PhysicalReceiptPaths,
    N6PhysicalReceiptStore,
    required_n6_action_authorization,
    required_n6_panel_plan_confirmation,
    required_n6_profile_confirmation,
    validate_n6_physical_receipt,
    validate_n6_physical_receipt_durable_commit,
)
from host.application.n6_visible_execution import (
    AtomicN6ClaimStore,
    N6HttpRefreshDriver,
)
from host.gamut_mapping import gamut_profile_from_mapping
from tests.application_browser_harness import LoopbackFakeDeviceServer
from tests.n6_formal_fixture import source_png
from tests.test_n6_physical_execution import (
    CLAIMED_AT,
    COMPLETED_AT,
    INITIAL_LIVE_AT,
    N6PhysicalFixture,
    SequenceClock,
)
from tools import mf1750_frame_tool as frame_tool


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright.sync_api") is not None
PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE and PILLOW_AVAILABLE,
    "local Playwright Chromium and Pillow are required",
)
class N6PhysicalRealBrowserE2ETests(unittest.TestCase):
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

    def test_physical_exact_tokens_four_previews_one_post_and_durable_lock(
        self,
    ) -> None:
        from playwright.sync_api import expect

        fake = LoopbackFakeDeviceServer().start()
        fake.mode = "success"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            application_port = _reserve_loopback_port()
            application_origin = f"http://127.0.0.1:{application_port}"
            fixture = N6PhysicalFixture(
                workspace,
                application_origin=application_origin,
            )
            legacy_manifest = fixture.manifest["legacy_formal_manifest"]
            claim_store = AtomicN6ClaimStore(workspace)
            claim_store.prepare_registry(legacy_manifest)
            claim_path = claim_store.claim_path(legacy_manifest)
            incident_output = claim_path.parent / (
                f"{claim_path.name}.N6-PHYSICAL-UNKNOWN.json"
            )
            receipt_paths = N6PhysicalReceiptPaths(
                receipt_output=(
                    workspace / "n6-physical-receipt.json"
                ).resolve(),
                receipt_commit_output=(
                    workspace / "n6-physical-receipt.commit.json"
                ).resolve(),
                incident_output=incident_output,
            )
            receipt_store = N6PhysicalReceiptStore(
                fixture.manifest,
                paths=receipt_paths,
            )
            self.assertIs(type(receipt_store), N6PhysicalReceiptStore)
            requester_calls = 0
            claim_seen_before_first_device_request = False

            def checked_requester(
                base_url: str,
                endpoint: str,
                **kwargs: object,
            ) -> tuple[int, str]:
                nonlocal requester_calls, claim_seen_before_first_device_request
                if requester_calls == 0:
                    if not claim_path.is_file():
                        raise AssertionError(
                            "N6 device request began before the durable claim"
                        )
                    if fake.ledger.snapshot():
                        raise AssertionError(
                            "N6 fake device received traffic before the claim"
                        )
                    claim_seen_before_first_device_request = True
                requester_calls += 1
                return frame_tool.http_request(base_url, endpoint, **kwargs)

            device_driver = N6HttpRefreshDriver(
                fake.origin,
                requester=checked_requester,
                poll_interval_s=0.001,
                sleeper=lambda _seconds: None,
            )
            self.assertIs(type(device_driver), N6HttpRefreshDriver)
            controller = N6PhysicalBrowserController(
                fixture.manifest,
                sources=fixture.sources,
                production_files=fixture.production_files,
                static_evidence_files=fixture.static_files,
                authorization_envelope=fixture.authorization_envelope,
                runtime_observation_envelope=fixture.runtime_observation_envelope,
                runtime_evidence_files=fixture.runtime_files,
                claim_store=claim_store,
                protocol_driver=device_driver,
                attempt_id="n6-physical-real-browser-loopback-attempt",
                post_claim_receipt_sink=receipt_store,
                utc_now=SequenceClock(INITIAL_LIVE_AT, CLAIMED_AT, COMPLETED_AT),
            )
            self.assertIs(type(controller), N6PhysicalBrowserController)
            profile = gamut_profile_from_mapping(
                fixture.gamut_profile_mapping,
                fixture.measured_palette,
            )
            runtime = ApplicationRuntime(
                fixture.measured_palette,
                OfflineAdapter(),
                gamut_profiles=(profile,),
                n6_formal_controller=controller,
            )
            server = ApplicationHttpServer(
                ("127.0.0.1", application_port),
                runtime,
                security_token="n6-physical-real-browser-token-000001",
            )
            self.assertEqual(server.origin, application_origin)
            for origin in (server.origin, fake.origin):
                parsed_origin = urlsplit(origin)
                assert parsed_origin.hostname is not None
                self.assertTrue(
                    ipaddress.ip_address(parsed_origin.hostname).is_loopback
                )

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            context = self.browser.new_context(service_workers="block")
            page = context.new_page()
            external: list[str] = []
            browser_urls: list[str] = []
            app_requests: list[tuple[str, str]] = []
            enqueue_response_storage: list[
                tuple[bytes | None, bytes | None, bool]
            ] = []

            def guard(route, request) -> None:  # type: ignore[no-untyped-def]
                parsed = urlsplit(request.url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme in {"blob", "data"} or origin == server.origin:
                    route.continue_()
                else:
                    external.append(request.url)
                    route.abort()

            def observe_request(request) -> None:  # type: ignore[no-untyped-def]
                browser_urls.append(request.url)
                app_requests.append((request.method, urlsplit(request.url).path))

            def observe_response(response) -> None:  # type: ignore[no-untyped-def]
                if (
                    response.request.method == "POST"
                    and urlsplit(response.url).path == "/application/device/enqueue"
                ):
                    paths = receipt_store.paths
                    enqueue_response_storage.append(
                        (
                            paths.receipt_output.read_bytes()
                            if paths.receipt_output.is_file()
                            else None,
                            paths.receipt_commit_output.read_bytes()
                            if paths.receipt_commit_output.is_file()
                            else None,
                            paths.incident_output.exists()
                            or paths.incident_output.is_symlink(),
                        )
                    )

            page.route("**/*", guard)
            page.on("request", observe_request)
            page.on("response", observe_response)
            try:
                page.goto(f"{server.origin}/#token={server.security_token}")
                expect(page.locator("#adapterNotice")).to_contain_text(
                    "原子 claim", timeout=10_000
                )
                self.assertEqual(fake.ledger.snapshot(), [])
                self.assertFalse(claim_path.exists())

                page.locator("#imageInput").set_input_files(
                    {
                        "name": "n6-physical-source.png",
                        "mimeType": "image/png",
                        "buffer": source_png(),
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
                self.assertIsNotNone(runtime.session.artifact)
                assert runtime.session.artifact is not None
                self.assertEqual(
                    runtime.session.artifact.identity,
                    fixture.artifact.identity,
                )
                for image_id in (
                    "sourcePreviewImage",
                    "mappedPreviewImage",
                    "previewImage",
                    "modelPreviewImage",
                ):
                    self.assertTrue(page.locator(f"#{image_id}").get_attribute("src"))

                page.locator("#cs1Mapping").fill("0,0,0,0")
                page.locator("#cs2Mapping").fill("1,0,0,0")
                page.locator("#allowConnection").click()
                expect(page.locator("#jobState")).to_have_text("connection_allowed")
                page.locator("#preflightButton").click()
                expect(page.locator("#jobState")).to_have_text("preflight_verified")
                self.assertEqual(fake.ledger.snapshot(), [])
                self.assertFalse(claim_path.exists())

                action_token = required_n6_action_authorization(fixture.manifest)
                panel_token = required_n6_panel_plan_confirmation(fixture.manifest)
                profile_token = required_n6_profile_confirmation(fixture.manifest)
                self.assertEqual(len({action_token, panel_token, profile_token}), 3)
                page.locator("#armPhrase").fill(action_token)
                page.locator("#panelPlanPhrase").fill(panel_token)
                page.locator("#profilePhrase").fill(profile_token)
                page.locator("#armButton").click()
                expect(page.locator("#jobState")).to_have_text("armed_one_shot")
                expect(page.locator("#refreshButton")).to_be_enabled()
                self.assertEqual(fake.ledger.snapshot(), [])
                self.assertFalse(claim_path.exists())

                page.locator("#refreshButton").click()
                expect(page.locator("#protocolBadge")).to_have_text(
                    "YES", timeout=30_000
                )
                self.assertTrue(claim_path.is_file())
                self.assertEqual(requester_calls, 4)
                self.assertTrue(claim_seen_before_first_device_request)
                self.assertEqual(fake.ledger.count("GET", "/api/version"), 1)
                self.assertEqual(fake.ledger.count("POST", "/api/frame"), 1)
                self.assertEqual(fake.ledger.count("GET", "/api/job"), 1)
                self.assertEqual(
                    fake.ledger.count("GET", "/api/diagnostic/report"), 1
                )

                receipt = controller.receipt
                commit = controller.receipt_durable_commit
                assert receipt is not None
                assert commit is not None
                self.assertEqual(controller.receipt_paths, receipt_store.paths)
                validate_n6_physical_receipt(
                    receipt,
                    manifest=fixture.manifest,
                    sources=fixture.sources,
                    production_files=fixture.production_files,
                    static_evidence_files=fixture.static_files,
                    runtime_evidence_files=fixture.runtime_files,
                    evaluated_at=COMPLETED_AT,
                )
                validate_n6_physical_receipt_durable_commit(
                    commit,
                    receipt=receipt,
                    paths=receipt_store.paths,
                )
                stored_receipt_bytes = receipt_store.paths.receipt_output.read_bytes()
                stored_commit_bytes = (
                    receipt_store.paths.receipt_commit_output.read_bytes()
                )
                self.assertEqual(
                    json.loads(stored_receipt_bytes),
                    receipt,
                )
                self.assertEqual(json.loads(stored_commit_bytes), commit)
                self.assertEqual(
                    enqueue_response_storage,
                    [(stored_receipt_bytes, stored_commit_bytes, False)],
                )
                self.assertIsNone(receipt_store.incident)
                self.assertFalse(receipt_store.paths.incident_output.exists())

                self.assertEqual(
                    receipt["required_token_sha256"],
                    {
                        "action_authorization": hashlib.sha256(
                            action_token.encode("utf-8")
                        ).hexdigest(),
                        "panel_plan_confirmation": hashlib.sha256(
                            panel_token.encode("utf-8")
                        ).hexdigest(),
                        "production_profile_confirmation": hashlib.sha256(
                            profile_token.encode("utf-8")
                        ).hexdigest(),
                    },
                )
                observation = receipt["legacy_protocol_receipt"][
                    "browser_observation"
                ]
                self.assertEqual(
                    observation["preview_stages_verified"],
                    ["source", "mapped", "final", "model"],
                )
                self.assertTrue(observation["token_validated"])
                self.assertTrue(
                    observation["same_origin_mutations_validated"]
                )
                self.assertEqual(
                    receipt["classification"]["frame_post_request_count"], 1
                )
                self.assertFalse(receipt["classification"]["retry_allowed"])
                self.assertFalse(receipt["classification"]["recovery_allowed"])

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
                expect(page.locator("#recoverButton")).to_be_hidden()
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
                self.assertEqual(requester_calls, 4)
                self.assertEqual(fake.ledger.count("POST", "/api/frame"), 1)
                self.assertEqual(
                    receipt_store.paths.receipt_output.read_bytes(),
                    stored_receipt_bytes,
                )
                self.assertEqual(
                    receipt_store.paths.receipt_commit_output.read_bytes(),
                    stored_commit_bytes,
                )
                self.assertIsNone(receipt_store.incident)
                self.assertFalse(receipt_store.paths.incident_output.exists())
                self.assertNotIn(
                    ("POST", "/application/device/recover"),
                    app_requests,
                )
                with self.assertRaisesRegex(
                    N6PhysicalExecutionError,
                    "no cancel, retry, or recovery",
                ):
                    controller.forbidden_recovery()
                self.assertEqual(external, [])
                for url in browser_urls:
                    parsed = urlsplit(url)
                    if parsed.scheme in {"http", "https"}:
                        assert parsed.hostname is not None
                        self.assertTrue(
                            ipaddress.ip_address(parsed.hostname).is_loopback
                        )
            finally:
                context.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)
                fake.close()


if __name__ == "__main__":
    unittest.main()
