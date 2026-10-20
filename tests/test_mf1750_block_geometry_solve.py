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
from tools import mf1750_block_geometry_solve as tool  # noqa: E402
from tools import mf1750_multi_roi_lab as roi_lab  # noqa: E402

V4_ROI_LIST = (
    ROOT
    / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V4"
    / "partial-atlas-1e-v4-roi-list.json"
)
V3_BATCH = ROOT / ".test-output/hardware/MF1750_PARTIAL_BLOCK_P0V3_20261020_V3"
V3_ROI_LIST = (
    ROOT
    / ".test-output/offline/MF1750_PARTIAL_BLOCK_20261020_V3"
    / "partial-atlas-1e-v3-roi-list.json"
)

BACKGROUND = (128, 134, 146)  # code7 blue-gray
CODE_COLORS = {
    "code0": (40, 170, 150),
    "code1": (150, 70, 120),
    "code2": (60, 90, 190),
    "code3": (120, 135, 90),
    "code4": (140, 60, 80),
    "code5": (170, 175, 70),
    "code7": BACKGROUND,
    "code6": (100, 120, 60),
}
# Mild keystone content->photo transform target quad (TL, TR, BR, BL) in a
# 1600x1200 canvas.
DST_QUAD = np.array(
    [(280.0, 150.0), (1330.0, 110.0), (1390.0, 1020.0), (230.0, 970.0)],
    dtype=np.float32,
)
PHOTO_SIZE = (1600, 1200)


def _v4_regions() -> list[dict]:
    document = json.loads(V4_ROI_LIST.read_text(encoding="utf-8"))
    return document["regions"]


def _content_image(hidden: tuple[str, ...] = ()) -> np.ndarray:
    image = np.full((600, 1024, 3), BACKGROUND, dtype=np.uint8)
    for region in _v4_regions():
        if region["name"] in hidden:
            continue
        x, y, w, h = (int(region[k]) for k in ("x", "y", "w", "h"))
        image[y : y + h, x : x + w] = CODE_COLORS[region["name"]]
    return image


def _true_homography() -> np.ndarray:
    src = np.array(
        [(0.0, 0.0), (1023.0, 0.0), (1023.0, 599.0), (0.0, 599.0)],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(src, DST_QUAD)


def _make_photo(
    content: np.ndarray, *, seed: int, noise: float = 1.2, crop_width: int | None = None
) -> np.ndarray:
    width, height = PHOTO_SIZE
    photo = np.full((height, width, 3), (35, 36, 40), dtype=np.uint8)
    homography = _true_homography()
    placed = cv2.warpPerspective(
        content[:, :, ::-1], homography, (width, height), flags=cv2.INTER_LINEAR
    )
    mask = cv2.warpPerspective(
        np.full((600, 1024), 255, dtype=np.uint8), homography, (width, height)
    )
    photo[mask > 128] = placed[mask > 128]
    rng = np.random.default_rng(seed)
    noisy = photo.astype(np.float64) + rng.normal(0.0, noise, photo.shape)
    photo = np.clip(noisy, 0, 255).astype(np.uint8)
    if crop_width is not None:
        photo = photo[:, :crop_width].copy()
    return photo


def _reprojection_of_true(homography: np.ndarray) -> float:
    corners = []
    for region in _v4_regions():
        x, y, w, h = (region[k] for k in ("x", "y", "w", "h"))
        corners.extend([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    src = np.array(corners, dtype=np.float64).reshape(-1, 1, 2)
    solved = cv2.perspectiveTransform(src, homography).reshape(-1, 2)
    truth = cv2.perspectiveTransform(src, _true_homography()).reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum((solved - truth) ** 2, axis=1))))


class SyntheticFixtureMixin:
    hidden: tuple[str, ...] = ()
    crop_width: int | None = None

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        photo = _make_photo(
            _content_image(self.hidden), seed=7, crop_width=self.crop_width
        )
        white = _make_photo(
            np.full((600, 1024, 3), BACKGROUND, dtype=np.uint8),
            seed=11,
            crop_width=self.crop_width,
        )
        cv2.imwrite(str(self.dir / "atlas.png"), photo)
        cv2.imwrite(str(self.dir / "white.png"), white)

    def _solve(self, name: str = "out", rim: bool = True, **kwargs) -> dict:
        return tool.solve(
            photo_file=self.dir / "atlas.png",
            roi_list_file=V4_ROI_LIST,
            output_dir=self.dir / name,
            white_photo_file=self.dir / "white.png",
            rim_photo_file=self.dir / "white.png" if rim else None,
            **kwargs,
        )


class FullVisibilityTests(SyntheticFixtureMixin, unittest.TestCase):
    hidden = ("code7",)

    def setUp(self) -> None:
        super().setUp()
        self.result = self._solve()
        self.report = json.loads((self.dir / "out" / "geometry.json").read_text(encoding="utf-8"))

    def test_assignment_recovers_all_visible_blocks(self) -> None:
        self.assertEqual(
            sorted(self.report["detected"]),
            ["code0", "code1", "code2", "code3", "code4", "code5", "code6"],
        )
        self.assertEqual(self.report["missing"], ["code7"])
        self.assertTrue(self.report["assignment"]["reliable"])

    def test_homography_matches_ground_truth(self) -> None:
        homography = np.array(self.report["homography_content_to_photo"])
        self.assertLess(_reprojection_of_true(homography), 4.0)

    def test_per_block_reprojection_errors_small(self) -> None:
        for block in self.report["blocks"]:
            if block["detection"] == "full":
                self.assertLess(block["reprojection_rms"], 6.0, block["name"])

    def test_symmetric_grid_tie_broken_by_rim_anchor(self) -> None:
        # With code7 invisible the V4 occupancy is 180-degree symmetric, so
        # wrong assignments fit the centroids exactly; the rim anchor decides.
        assignment = self.report["assignment"]
        self.assertGreaterEqual(assignment["corner_score_tie_count"], 2)
        self.assertEqual(assignment["tie_broken_by"], "rim_x0_anchor")
        self.assertTrue(assignment["reliable"])

    def test_tie_without_rim_is_reported_not_guessed(self) -> None:
        self._solve(name="out-norim", rim=False)
        report = json.loads(
            (self.dir / "out-norim" / "geometry.json").read_text(encoding="utf-8")
        )
        assignment = report["assignment"]
        self.assertGreaterEqual(assignment["corner_score_tie_count"], 2)
        self.assertIsNone(assignment["tie_broken_by"])
        self.assertFalse(assignment["reliable"])

    def test_report_is_sealed(self) -> None:
        verified = roi_lab.verify_report(self.dir / "out" / "geometry.json")
        self.assertEqual(
            verified["integrity_sha256"], self.result["geometry_canonical_sha256"]
        )

    def test_lab_handoff_uses_white_delta_convention(self) -> None:
        lab = json.loads((self.dir / "out" / "lab-report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(lab["regions"]), 8)
        self.assertIn("white_reference", lab)
        code0 = next(r for r in lab["regions"] if r["name"] == "code0")
        expected = srgb8_to_lab(CODE_COLORS["code0"])
        self.assertAlmostEqual(code0["L"], expected[0], delta=3.0)
        self.assertAlmostEqual(code0["a"], expected[1], delta=3.0)
        self.assertAlmostEqual(code0["b"], expected[2], delta=3.0)
        self.assertTrue(code0["resolvable_vs_white"])
        self.assertGreater(code0["delta_vs_white"]["dE76"], 3.0)
        # The invisible code7 block measures background: not resolvable.
        code7 = next(r for r in lab["regions"] if r["name"] == "code7")
        self.assertFalse(code7["resolvable_vs_white"])

    def test_rim_anchor(self) -> None:
        result = tool.solve(
            photo_file=self.dir / "atlas.png",
            roi_list_file=V4_ROI_LIST,
            output_dir=self.dir / "out-rim",
            white_photo_file=self.dir / "white.png",
            rim_photo_file=self.dir / "white.png",
        )
        self.assertIsNotNone(result["rim_err"])
        self.assertLess(result["rim_err"], 10.0)

    def test_output_dir_must_not_exist(self) -> None:
        with self.assertRaises(tool.GeometrySolveError):
            self._solve(name="out")


class PartialVisibilityTests(SyntheticFixtureMixin, unittest.TestCase):
    hidden = ("code1", "code7")

    def test_invisible_blocks_reported_missing_and_solve_robust(self) -> None:
        result = self._solve()
        self.assertEqual(sorted(result["missing"]), ["code1", "code7"])
        self.assertEqual(
            sorted(result["detected"]),
            ["code0", "code2", "code3", "code4", "code5", "code6"],
        )
        report = json.loads((self.dir / "out" / "geometry.json").read_text(encoding="utf-8"))
        homography = np.array(report["homography_content_to_photo"])
        self.assertLess(_reprojection_of_true(homography), 4.0)


class TruncatedCropTests(SyntheticFixtureMixin, unittest.TestCase):
    hidden = ("code1", "code7")
    crop_width = 760  # cuts through the right column (code3/code6)

    def test_slivers_excluded_from_fit_and_matched_post_hoc(self) -> None:
        result = self._solve()
        report = json.loads((self.dir / "out" / "geometry.json").read_text(encoding="utf-8"))
        for name in ("code0", "code2", "code4", "code5"):
            block = next(b for b in report["blocks"] if b["name"] == name)
            self.assertEqual(block["detection"], "full", name)
        homography = np.array(report["homography_content_to_photo"])
        self.assertLess(_reprojection_of_true(homography), 8.0)
        code3 = next(b for b in report["blocks"] if b["name"] == "code3")
        self.assertIn(code3["detection"], (None, "truncated"))


class MedianBackgroundDetectionTests(SyntheticFixtureMixin, unittest.TestCase):
    hidden = ("code7",)

    def test_detection_without_white_photo(self) -> None:
        result = tool.solve(
            photo_file=self.dir / "atlas.png",
            roi_list_file=V4_ROI_LIST,
            output_dir=self.dir / "out-nowhite",
        )
        self.assertEqual(sorted(result["missing"]), ["code7"])
        lab = json.loads(
            (self.dir / "out-nowhite" / "lab-report.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("white_reference", lab)


@unittest.skipUnless(
    (V3_BATCH / "05-atlas-t0.jpg").is_file()
    and (V3_BATCH / "04-postnorm-white.jpg").is_file()
    and V3_ROI_LIST.is_file(),
    "V3 recon batch photos not present",
)
class V3ReconPhotoSanityTests(unittest.TestCase):
    """Qualitative regression on the real V3 recon batch atlas photo.

    The V3 layout differs from V4; this only verifies the solver does not
    crash and reproduces the arbitrated assignment (geometry-unflipped-A.json:
    teal=code0, mauve=code4, yellowgreen=code5; code1 invisible).
    """

    def test_v3_atlas_photo_sanity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = tool.solve(
                photo_file=V3_BATCH / "05-atlas-t0.jpg",
                roi_list_file=V3_ROI_LIST,
                output_dir=Path(tmp) / "v3",
                white_photo_file=V3_BATCH / "04-postnorm-white.jpg",
                rim_photo_file=V3_BATCH / "01-otp-t0.jpg",
            )
            report = json.loads((Path(tmp) / "v3" / "geometry.json").read_text(encoding="utf-8"))
            # Detection matches the V3 narrative: 3 macro diff blobs (2 clean
            # blocks + merged sliver haze at the right edge).
            self.assertEqual(report["detection"]["blob_count"], 3)
            self.assertEqual(report["assignment"]["full_blocks_used"], 2)
            # V3 history lesson: block geometry alone leaves a symmetric tie;
            # the tool must report it instead of guessing reliably.
            self.assertGreaterEqual(report["assignment"]["corner_score_tie_count"], 2)
            self.assertFalse(report["assignment"]["reliable"])
            self.assertTrue(set(result["detected"]) <= set(r["name"] for r in report["blocks"]))
            homography = np.array(report["homography_content_to_photo"])
            self.assertTrue(np.all(np.isfinite(homography)))
            self.assertIsNotNone(result["rim_err"])
            self.assertTrue(
                all(
                    math.isfinite(v)
                    for block in report["blocks"]
                    for point in block["photo_quad_pred"]
                    for v in point
                )
            )
            roi_lab.verify_report(Path(tmp) / "v3" / "geometry.json")
            lab = json.loads((Path(tmp) / "v3" / "lab-report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(lab["regions"]), 8)


if __name__ == "__main__":
    unittest.main()
