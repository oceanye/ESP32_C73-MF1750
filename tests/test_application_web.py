from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class WebUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.javascript = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    def test_ui_exposes_required_controls_and_scoped_statuses(self) -> None:
        for identifier in (
            "imageInput",
            "fitPolicy",
            "ditherMode",
            "paletteMode",
            "previewImage",
            "frameBytes",
            "inputHash",
            "frameHash",
            "paletteWarning",
            "allowConnection",
            "armPhrase",
            "refreshButton",
            "jobState",
            "errorDetail",
            "recoverButton",
        ):
            self.assertIn(f'id="{identifier}"', self.html)
        for scoped_status in ("offline_verified", "protocol_verified", "hardware_tested"):
            self.assertIn(scoped_status, self.html)
        self.assertIn("Hardware tested", self.html)
        self.assertIn("NO", self.html)

    def test_ui_locks_refresh_and_has_network_recovery(self) -> None:
        self.assertIn("state.refreshLocked = true", self.javascript)
        self.assertIn("refresh submission", (REPO_ROOT / "host" / "application" / "session.py").read_text(encoding="utf-8"))
        self.assertIn("/application/device/recover", self.javascript)
        self.assertIn("HTTP 202", self.javascript)
        self.assertIn("completed_pending_report", self.javascript)
        self.assertIn("protocol_verified", self.javascript)

    def test_ui_uses_fragment_session_token_for_every_application_request(self) -> None:
        self.assertIn('fragment.get("token")', self.javascript)
        self.assertIn("sessionStorage.setItem", self.javascript)
        self.assertIn("history.replaceState", self.javascript)
        self.assertIn('"X-Application-Token": state.token', self.javascript)
        self.assertEqual(self.javascript.count("fetch("), 1)

    def test_ui_invalidates_artifact_and_recovers_by_server_state(self) -> None:
        self.assertIn('/application/artifact/invalidate', self.javascript)
        self.assertIn("artifactVisible", self.javascript)
        self.assertIn("page_reload_without_visible_artifact", self.javascript)
        self.assertIn("status.operation_in_progress === true", self.javascript)
        self.assertIn("watchOperationCompletion", self.javascript)
        self.assertIn("reconcileInvisibleArtifact", self.javascript)
        self.assertIn("reconcileAfterMutationError", self.javascript)
        for identifier in (
            "input_file_changed",
            "fitPolicy",
            "ditherMode",
            "textMode",
            "whiteProtection",
            "generation_started",
            "generation_failed",
        ):
            self.assertIn(identifier, self.javascript)
        self.assertIn('jsonRequest("/application/status")', self.javascript)
        self.assertIn('postJson("/application/device/job", {})', self.javascript)
        self.assertIn('postJson("/application/device/report", {})', self.javascript)
        self.assertNotIn('jsonRequest("/application/device/job")', self.javascript)
        self.assertNotIn('jsonRequest("/application/device/report")', self.javascript)
        self.assertIn('recovered.state === "completed_pending_report"', self.javascript)

    def test_web_code_never_labels_hardware_as_passed(self) -> None:
        combined = self.html + self.javascript
        self.assertNotIn('hardware_tested = true', combined)
        self.assertNotIn('hardware_tested: true', combined)
        self.assertNotIn('Hardware tested: YES', combined)


if __name__ == "__main__":
    unittest.main()
