from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class FirmwarePhotoToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (REPO_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
        html_match = re.search(
            r'static constexpr char INDEX_HTML\[\] PROGMEM = R"HTML\((.*?)\)HTML";',
            cls.source,
            flags=re.DOTALL,
        )
        if html_match is None:
            raise AssertionError("embedded firmware web page was not found")
        cls.html = html_match.group(1)
        script_match = re.search(r"<script>(.*?)</script>", cls.html, flags=re.DOTALL)
        if script_match is None:
            raise AssertionError("embedded firmware JavaScript was not found")
        cls.javascript = script_match.group(1)

    def test_tool_exposes_all_preview_modes(self) -> None:
        for element_id in (
            "source-preview",
            "preview",
            "crop",
            "enhance",
            "dither",
            "send",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        for mode in (
            "none",
            "floyd-steinberg",
            "atkinson",
            "ordered-bayer-8x8",
        ):
            self.assertIn(f'value="{mode}"', self.html)

    def test_preview_pixels_are_the_exact_packed_palette_selection(self) -> None:
        self.assertIn("sourceCtx.getImageData", self.javascript)
        self.assertIn("preview.data[rgba] = selected.rgb[0]", self.javascript)
        self.assertIn("ctx.putImageData(preview, 0, 0)", self.javascript)
        self.assertIn("body: frame", self.javascript)
        self.assertIn("const frame = packed", self.javascript)
        self.assertIn("const frameHash = packedHash", self.javascript)
        self.assertIn("data.fnv1a !== frameHash", self.javascript)
        for code in ("0x0", "0x1", "0x2", "0x3", "0x5", "0x6"):
            self.assertIn(f"code: {code}", self.javascript)

    def test_switching_options_only_rebuilds_preview(self) -> None:
        self.assertIn("cropEl.addEventListener('change', renderLoadedImage)", self.javascript)
        self.assertIn("enhanceEl.addEventListener('change', renderLoadedImage)", self.javascript)
        self.assertIn("ditherEl.addEventListener('change', renderLoadedImage)", self.javascript)
        self.assertEqual(self.javascript.count("fetch('/api/frame'"), 1)
        self.assertIn("sendEl.addEventListener('click'", self.javascript)
        self.assertIn("uploadPending", self.javascript)
        self.assertIn("generation !== imageGeneration", self.javascript)

    def test_embedded_javascript_has_valid_syntax_when_node_is_available(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = self.javascript.replace("%EPD_WIDTH%", "1024")
        script = script.replace("%EPD_HEIGHT%", "600")
        script = script.replace("%UPLOAD_WIDTH%", "1024")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "firmware-web.js"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
