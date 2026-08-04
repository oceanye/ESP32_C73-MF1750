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

    def test_web_code_never_labels_hardware_as_passed(self) -> None:
        combined = self.html + self.javascript
        self.assertNotIn('hardware_tested = true', combined)
        self.assertNotIn('hardware_tested: true', combined)
        self.assertNotIn('Hardware tested: YES', combined)


if __name__ == "__main__":
    unittest.main()
