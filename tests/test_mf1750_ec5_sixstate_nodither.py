from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import mf1750_ec5_sixstate_nodither as assets


class SixStateNoDitherGeometryTests(unittest.TestCase):
    def test_layout_has_twelve_pure_mirrored_24px_rois(self) -> None:
        rois = assets.frozen_rois(4)
        self.assertEqual(len(rois), 12)
        self.assertEqual(assets.CANDIDATE_PIXELS, 6912)
        self.assertLessEqual(assets.CANDIDATE_PIXELS, assets.PILOT_PIXEL_LIMIT)
        expected_states = [name for name, _ in assets.INITIAL_STATES]
        for pair_index, expected_name in enumerate(expected_states, start=1):
            pair = [roi for roi in rois if roi["pair_index"] == pair_index]
            self.assertEqual([roi["controller"] for roi in pair], ["CS1", "CS2"])
            self.assertEqual({roi["initial_name"] for roi in pair}, {expected_name})
            left, right = pair
            left_rect = left["rect"]
            right_rect = right["rect"]
            self.assertEqual(left_rect["width"], 24)
            self.assertEqual(left_rect["height"], 24)
            self.assertEqual(right_rect["width"], 24)
            self.assertEqual(right_rect["height"], 24)
            self.assertEqual(right_rect["x0"], assets.WIDTH - left_rect["x1_exclusive"])
            self.assertEqual(
                right_rect["x1_exclusive"], assets.WIDTH - left_rect["x0"]
            )
            self.assertEqual(
                left_rect["x0"], right_rect["x0"] - assets.CONTROLLER_WIDTH
            )
            self.assertEqual(left_rect["y0"], right_rect["y0"])

    def test_primer_and_target_have_frozen_histograms_and_uniform_rois(self) -> None:
        for candidate in assets.CANDIDATES:
            primer, target = assets.build_frames(candidate)
            self.assertEqual(len(primer), assets.FRAME_BYTES)
            self.assertEqual(len(target), assets.FRAME_BYTES)
            self.assertEqual(
                assets._histogram(primer),
                assets.FROZEN_HISTOGRAMS[candidate]["primer"],
            )
            self.assertEqual(
                assets._histogram(target),
                assets.FROZEN_HISTOGRAMS[candidate]["target"],
            )
            for roi in assets.frozen_rois(candidate):
                rect = roi["rect"]
                primer_values = {
                    assets._pixel(primer, x, y)
                    for y in range(rect["y0"], rect["y1_exclusive"])
                    for x in range(rect["x0"], rect["x1_exclusive"])
                }
                target_values = {
                    assets._pixel(target, x, y)
                    for y in range(rect["y0"], rect["y1_exclusive"])
                    for x in range(rect["x0"], rect["x1_exclusive"])
                }
                self.assertEqual(primer_values, {roi["initial_code"]})
                self.assertEqual(target_values, {candidate})

    def test_full_and_controller_identities_are_frozen(self) -> None:
        for candidate in assets.CANDIDATES:
            primer, target = assets.build_frames(candidate)
            for role, frame in (("primer", primer), ("target", target)):
                streams = {
                    "full": frame,
                    "CS1": assets._controller_stream(frame, 0),
                    "CS2": assets._controller_stream(frame, 1),
                }
                for name, stream in streams.items():
                    sha, fnv = assets.FROZEN_IDENTITIES[candidate][role][name]
                    self.assertEqual(assets._sha256(stream), sha)
                    self.assertEqual(assets._fnv1a(stream), fnv)
                self.assertEqual(streams["CS1"], streams["CS2"])

    def test_high_nibble_is_left_pixel(self) -> None:
        primer, _ = assets.build_frames(4)
        black_cs1 = next(
            roi
            for roi in assets.frozen_rois(4)
            if roi["roi_id"] == "BLACK-CS1"
        )
        x = black_cs1["rect"]["x0"]
        y = black_cs1["rect"]["y0"]
        packed = primer[y * assets.ROW_BYTES + x // 2]
        self.assertEqual(packed >> 4, 0)
        self.assertEqual(packed & 0x0F, 0)
        self.assertEqual(assets._pixel(primer, x - 1, y), assets.WHITE_CODE)


class SixStateNoDitherBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_generate_keeps_u04_and_u07_in_separate_directories(self) -> None:
        manifest4 = assets.generate_bundle(self.root, 4)
        manifest7 = assets.generate_bundle(self.root, 7)
        self.assertEqual(manifest4.parent.name, "U04")
        self.assertEqual(manifest7.parent.name, "U07")
        self.assertNotEqual(manifest4.parent, manifest7.parent)
        self.assertEqual(assets.validate_bundle(manifest4)["candidate_id"], "U04")
        self.assertEqual(assets.validate_bundle(manifest7)["candidate_id"], "U07")
        self.assertFalse(
            set(path.name for path in manifest4.parent.iterdir())
            & set(path.name for path in manifest7.parent.iterdir())
        )

    def test_manifest_freezes_mapping_coordinates_hashes_and_safety(self) -> None:
        manifest, generated = assets.build_bundle(4)
        self.assertEqual(manifest["controller_mapping"], assets.MAPPINGS)
        self.assertEqual(manifest["rois"], assets.frozen_rois(4))
        self.assertEqual(manifest["geometry"]["candidate_pixels"], 6912)
        self.assertFalse(manifest["safety"]["dithering_present"])
        self.assertFalse(manifest["safety"]["spatial_mixing_present"])
        self.assertFalse(manifest["safety"]["hardware_execution_authorized"])
        self.assertEqual(manifest["candidate"]["firmware_compile_parameter"], "MF1750_UNKNOWN_PROBE_CODE=4")
        self.assertEqual(set(generated), {
            "u04_primer.raw",
            "u04_target.raw",
            "u04_primer.preview.png",
            "u04_target.preview.png",
            "u04_manifest.json",
        })
        for role in ("primer", "target"):
            frozen = assets.FROZEN_IDENTITIES[4][role]
            self.assertEqual(manifest["frames"][role]["full"]["sha256"], frozen["full"][0])
            self.assertEqual(manifest["frames"][role]["full"]["fnv1a_u32"], frozen["full"][1])
            for controller in ("CS1", "CS2"):
                identity = manifest["frames"][role]["controller_streams"][controller]
                self.assertEqual(identity["sha256"], frozen[controller][0])
                self.assertEqual(identity["fnv1a_u32"], frozen[controller][1])

    def test_preview_is_exact_frame_visualization_with_uniform_pseudocolor(self) -> None:
        for candidate in assets.CANDIDATES:
            _, generated = assets.build_bundle(candidate)
            for role in ("primer", "target"):
                frame = generated[f"u0{candidate}_{role}.raw"]
                png = generated[f"u0{candidate}_{role}.preview.png"]
                self.assertEqual(
                    assets._decode_png(png), assets._preview_rgb(frame, candidate)
                )
            target_rgb = assets._decode_png(
                generated[f"u0{candidate}_target.preview.png"]
            )
            roi = assets.frozen_rois(candidate)[0]["rect"]
            colours = {
                tuple(target_rgb[(y * assets.WIDTH + x) * 3 : (y * assets.WIDTH + x) * 3 + 3])
                for y in range(roi["y0"], roi["y1_exclusive"])
                for x in range(roi["x0"], roi["x1_exclusive"])
            }
            self.assertEqual(colours, {assets.UNKNOWN_PREVIEW_RGB[candidate]})

    def test_generation_refuses_overwrite(self) -> None:
        assets.generate_bundle(self.root, 4)
        with self.assertRaisesRegex(assets.SixStateAssetError, "already exists"):
            assets.generate_bundle(self.root, 4)

    def test_invalid_candidate_fails_closed(self) -> None:
        for value in (0, 1, 5, 6, 8, True, "4"):
            with self.subTest(value=value):
                with self.assertRaises(assets.SixStateAssetError):
                    assets.build_bundle(value)  # type: ignore[arg-type]

    def test_raw_byte_tamper_is_rejected(self) -> None:
        manifest = assets.generate_bundle(self.root, 4)
        raw = manifest.parent / "u04_target.raw"
        changed = bytearray(raw.read_bytes())
        changed[12345] ^= 0x01
        raw.write_bytes(changed)
        with self.assertRaisesRegex(assets.SixStateAssetError, "frozen bytes"):
            assets.validate_bundle(manifest)

    def test_png_tamper_is_rejected(self) -> None:
        manifest = assets.generate_bundle(self.root, 7)
        png = manifest.parent / "u07_target.preview.png"
        changed = bytearray(png.read_bytes())
        changed[-5] ^= 0x01
        png.write_bytes(changed)
        with self.assertRaisesRegex(assets.SixStateAssetError, "frozen bytes"):
            assets.validate_bundle(manifest)

    def test_manifest_tamper_and_duplicate_key_are_rejected(self) -> None:
        manifest = assets.generate_bundle(self.root, 4)
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["geometry"]["candidate_pixels"] = 6911
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(assets.SixStateAssetError, "frozen candidate"):
            assets.validate_bundle(manifest)

        shutil.rmtree(manifest.parent)
        manifest = assets.generate_bundle(self.root, 4)
        encoded = manifest.read_text(encoding="utf-8")
        manifest.write_text(
            encoded.replace("{", '{"kind":"duplicate",', 1), encoding="utf-8"
        )
        with self.assertRaisesRegex(assets.SixStateAssetError, "duplicate key"):
            assets.validate_bundle(manifest)

    def test_cross_candidate_asset_substitution_is_rejected(self) -> None:
        manifest4 = assets.generate_bundle(self.root, 4)
        manifest7 = assets.generate_bundle(self.root, 7)
        source = manifest7.parent / "u07_target.raw"
        destination = manifest4.parent / "u04_target.raw"
        destination.write_bytes(source.read_bytes())
        with self.assertRaisesRegex(assets.SixStateAssetError, "frozen bytes"):
            assets.validate_bundle(manifest4)

    def test_wrong_directory_identity_is_rejected(self) -> None:
        manifest = assets.generate_bundle(self.root, 4)
        moved = self.root / "NOT_U04"
        manifest.parent.rename(moved)
        with self.assertRaisesRegex(assets.SixStateAssetError, "isolated directory"):
            assets.validate_bundle(moved / manifest.name)


class SixStateNoDitherIsolationTests(unittest.TestCase):
    def test_tool_imports_only_offline_standard_library_modules(self) -> None:
        source_path = Path(assets.__file__).resolve()
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported
            <= {
                "__future__",
                "argparse",
                "hashlib",
                "json",
                "pathlib",
                "struct",
                "sys",
                "typing",
                "zlib",
            }
        )
        self.assertTrue(
            imported.isdisjoint(
                {"requests", "serial", "socket", "subprocess", "urllib"}
            )
        )


if __name__ == "__main__":
    unittest.main()
