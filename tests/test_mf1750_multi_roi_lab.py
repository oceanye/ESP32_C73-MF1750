from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import srgb8_to_lab  # noqa: E402
from tools import mf1750_multi_roi_lab as tool  # noqa: E402


BLOCKS = [
    ("blk_red", 0, (200, 40, 40), (60, 60, 360, 200)),
    ("blk_green", 1, (40, 160, 80), (460, 60, 360, 200)),
    ("blk_blue", 2, (40, 60, 200), (60, 320, 360, 200)),
    ("blk_gray", 3, (120, 120, 120), (460, 320, 360, 200)),
]
WHITE = (235, 235, 235)


def _screen_image() -> np.ndarray:
    image = np.full((600, 1024, 3), WHITE, dtype=np.uint8)
    for _, _, rgb, (x, y, w, h) in BLOCKS:
        image[y : y + h, x : x + w] = rgb
    return image


def _layout(regions=None) -> dict:
    return {
        "screen": {"width": 1024, "height": 600},
        "regions": regions
        if regions is not None
        else [
            {"name": name, "code": code, "x": x, "y": y, "w": w, "h": h}
            for name, code, _, (x, y, w, h) in BLOCKS
        ],
    }


class _FixtureMixin:
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        cv2.imwrite(str(self.dir / "screen.png"), _screen_image()[:, :, ::-1])
        (self.dir / "layout.json").write_text(
            json.dumps(_layout()), encoding="utf-8"
        )

    def report_path(self, name: str = "report.json") -> Path:
        return self.dir / name


class LabConventionTests(unittest.TestCase):
    def test_vectorized_lab_matches_host_pipeline(self) -> None:
        rng = np.random.default_rng(20261020)
        samples = rng.integers(0, 256, size=(512, 3))
        mine = tool.srgb8_to_lab_batch(samples)
        theirs = np.array(
            [srgb8_to_lab(tuple(int(v) for v in px)) for px in samples]
        )
        self.assertLess(float(np.max(np.abs(mine - theirs))), 1e-9)


class WarpedImageModeTests(_FixtureMixin, unittest.TestCase):
    def _run(self, **kwargs) -> dict:
        return tool.measure(
            image=self.dir / "screen.png",
            layout_file=self.dir / "layout.json",
            report_file=self.report_path(),
            **kwargs,
        )

    def test_known_block_lab(self) -> None:
        result = self._run()
        self.assertEqual(result["region_count"], 4)
        report = json.loads(self.report_path().read_text(encoding="utf-8"))
        by_name = {r["name"]: r for r in report["regions"]}
        for name, _, rgb, _ in BLOCKS:
            expected = srgb8_to_lab(rgb)
            measured = by_name[name]
            self.assertAlmostEqual(measured["L"], expected[0], delta=0.05)
            self.assertAlmostEqual(measured["a"], expected[1], delta=0.05)
            self.assertAlmostEqual(measured["b"], expected[2], delta=0.05)
            self.assertAlmostEqual(measured["std_L"], 0.0, delta=0.01)
            self.assertEqual(measured["code"], dict((b[0], b[1]) for b in BLOCKS)[name])

    def test_inset_excludes_border(self) -> None:
        # Region rect is 200x200 but the colour block fills only its central
        # 80%; a 20px black frame sits inside the declared rect. With the 10%
        # per-side inset the measured Lab must be the interior colour only.
        image = np.full((600, 1024, 3), WHITE, dtype=np.uint8)
        image[100:300, 100:300] = (0, 0, 0)
        image[120:280, 120:280] = (60, 180, 90)
        cv2.imwrite(str(self.dir / "framed.png"), image[:, :, ::-1])
        layout = _layout(regions=[{"name": "framed", "code": 5, "x": 100, "y": 100, "w": 200, "h": 200}])
        (self.dir / "framed-layout.json").write_text(json.dumps(layout), encoding="utf-8")
        tool.measure(
            image=self.dir / "framed.png",
            layout_file=self.dir / "framed-layout.json",
            report_file=self.report_path("framed-report.json"),
        )
        report = json.loads(self.report_path("framed-report.json").read_text(encoding="utf-8"))
        region = report["regions"][0]
        self.assertEqual(
            region["analysis_rectangle"],
            {"x": 120, "y": 120, "x1_exclusive": 280, "y1_exclusive": 280},
        )
        expected = srgb8_to_lab((60, 180, 90))
        self.assertAlmostEqual(region["L"], expected[0], delta=0.05)
        self.assertAlmostEqual(region["std_L"], 0.0, delta=0.01)

    def test_illumination_p95_and_ratio(self) -> None:
        result = self._run(reference_p95=200.0)
        illumination = result["illumination"]
        # cv2 grayscale of WHITE=(235,235,235) is exactly 235 everywhere.
        self.assertEqual(illumination["grayscale_p95"], 235.0)
        self.assertAlmostEqual(illumination["ratio"], round(235.0 / 200.0, 4), places=4)
        self.assertTrue(illumination["gate_passed"])
        self.assertGreater(illumination["white_background_pixel_count"], 1000)

    def test_illumination_without_reference_has_null_ratio(self) -> None:
        illumination = self._run()["illumination"]
        self.assertIsNone(illumination["ratio"])
        self.assertIsNone(illumination["gate_passed"])

    def test_integrity_self_seal_and_tamper_detection(self) -> None:
        self._run()
        verified = tool.verify_report(self.report_path())
        report = json.loads(self.report_path().read_text(encoding="utf-8"))
        self.assertEqual(verified["integrity_sha256"], report["integrity"]["sha256"])
        self.assertEqual(
            report["integrity"]["algorithm"], "sha256-canonical-json-without-integrity"
        )
        report["regions"][0]["L"] += 1.0
        tampered = self.dir / "tampered.json"
        tampered.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaises(tool.MultiRoiLabError):
            tool.verify_report(tampered)

    def test_refuses_to_overwrite_report(self) -> None:
        self._run()
        with self.assertRaises(FileExistsError):
            self._run()

    def test_annotated_overlay_written(self) -> None:
        annotated = self.dir / "annotated.png"
        self._run(annotated_file=annotated)
        overlay = cv2.imread(str(annotated))
        self.assertEqual(overlay.shape, (600, 1024, 3))
        self.assertFalse(np.array_equal(overlay, _screen_image()[:, :, ::-1]))


class RawPhotoModeTests(_FixtureMixin, unittest.TestCase):
    def _make_photo(self) -> Path:
        # Synthesize the camera photo by inverse-warping the screen image
        # through the default batch quad into a 1600x1000 frame.
        photo = np.full((1000, 1600, 3), (30, 30, 30), dtype=np.uint8)
        quad = np.array(
            [[x * 1600, y * 1000] for x, y in tool.DEFAULT_RELATIVE_QUAD],
            dtype=np.float32,
        )
        target = np.array(
            [[0, 0], [1023, 0], [1023, 599], [0, 599]], dtype=np.float32
        )
        screen_to_photo = cv2.getPerspectiveTransform(target, quad)
        placed = cv2.warpPerspective(
            _screen_image()[:, :, ::-1], screen_to_photo, (1600, 1000),
            flags=cv2.INTER_LINEAR,
        )
        mask = cv2.warpPerspective(
            np.full((600, 1024), 255, dtype=np.uint8), screen_to_photo, (1600, 1000)
        )
        photo[mask > 128] = placed[mask > 128]
        path = self.dir / "photo.png"
        cv2.imwrite(str(path), photo)
        return path

    def test_photo_quad_warp_recovers_block_lab(self) -> None:
        photo = self._make_photo()
        result = tool.measure(
            photo=photo,
            layout_file=self.dir / "layout.json",
            report_file=self.report_path("photo-report.json"),
            warped_out_file=self.dir / "warped.png",
        )
        report = json.loads(self.report_path("photo-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["registration"]["mode"], "raw-photo-quad-warp")
        self.assertTrue(report["registration"]["default_batch_quad_used"])
        warped = cv2.imread(str(self.dir / "warped.png"))
        self.assertEqual(warped.shape, (600, 1024, 3))
        by_name = {r["name"]: r for r in report["regions"]}
        for name, _, rgb, _ in BLOCKS:
            expected = srgb8_to_lab(rgb)
            measured = by_name[name]
            self.assertAlmostEqual(measured["L"], expected[0], delta=1.0)
            self.assertAlmostEqual(measured["a"], expected[1], delta=1.0)
            self.assertAlmostEqual(measured["b"], expected[2], delta=1.0)
            self.assertLess(measured["std_L"], 2.0)
        self.assertTrue(math.isfinite(result["illumination"]["grayscale_p95"]))


class ValidationTests(_FixtureMixin, unittest.TestCase):
    def test_warped_image_must_be_screen_size(self) -> None:
        small = np.full((300, 512, 3), 200, dtype=np.uint8)
        cv2.imwrite(str(self.dir / "small.png"), small)
        with self.assertRaises(tool.MultiRoiLabError):
            tool.measure(
                image=self.dir / "small.png",
                layout_file=self.dir / "layout.json",
                report_file=self.report_path(),
            )

    def test_region_outside_screen_rejected(self) -> None:
        layout = _layout(regions=[{"name": "bad", "code": 0, "x": 900, "y": 0, "w": 200, "h": 100}])
        (self.dir / "bad.json").write_text(json.dumps(layout), encoding="utf-8")
        with self.assertRaises(tool.MultiRoiLabError):
            tool.measure(
                image=self.dir / "screen.png",
                layout_file=self.dir / "bad.json",
                report_file=self.report_path(),
            )

    def test_duplicate_region_names_rejected(self) -> None:
        regions = [
            {"name": "dup", "code": 0, "x": 10, "y": 10, "w": 100, "h": 100},
            {"name": "dup", "code": 1, "x": 200, "y": 10, "w": 100, "h": 100},
        ]
        (self.dir / "dup.json").write_text(
            json.dumps(_layout(regions=regions)), encoding="utf-8"
        )
        with self.assertRaises(tool.MultiRoiLabError):
            tool.measure(
                image=self.dir / "screen.png",
                layout_file=self.dir / "dup.json",
                report_file=self.report_path(),
            )

    def test_exactly_one_input_required(self) -> None:
        with self.assertRaises(tool.MultiRoiLabError):
            tool.measure(
                layout_file=self.dir / "layout.json",
                report_file=self.report_path(),
            )
        with self.assertRaises(tool.MultiRoiLabError):
            tool.measure(
                image=self.dir / "screen.png",
                photo=self.dir / "screen.png",
                layout_file=self.dir / "layout.json",
                report_file=self.report_path(),
            )


class CliTests(_FixtureMixin, unittest.TestCase):
    def test_main_roundtrip_and_verify(self) -> None:
        rc = tool.main(
            [
                "--image", str(self.dir / "screen.png"),
                "--layout", str(self.dir / "layout.json"),
                "--report", str(self.report_path()),
                "--reference-p95", "235",
            ]
        )
        self.assertEqual(rc, 0)
        rc = tool.main(["--verify", str(self.report_path())])
        self.assertEqual(rc, 0)

    def test_main_error_returns_2(self) -> None:
        rc = tool.main(
            [
                "--image", str(self.dir / "missing.png"),
                "--layout", str(self.dir / "layout.json"),
                "--report", str(self.report_path()),
            ]
        )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
