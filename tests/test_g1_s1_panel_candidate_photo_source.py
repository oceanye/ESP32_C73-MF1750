from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from host.application.simulation import SimulationAlgorithm
from tools import g1_s1_panel_candidate as tool


SOURCE_LABEL = "unit-test-small-photo.jpg"
SOURCE_RIGHTS = "self-created test fixture"
TEST_ALGORITHM = SimulationAlgorithm.AREA_WEIGHTED_ORDERED


def _small_jpeg() -> bytes:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as error:
        raise unittest.SkipTest("Pillow is required for the photo-source contract") from error

    image = Image.new("RGB", (5, 3))
    image.putdata(
        [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 255),
            (0, 0, 0),
            (32, 64, 96),
            (128, 160, 192),
            (224, 192, 160),
            (17, 33, 65),
            (129, 63, 31),
            (250, 200, 10),
            (10, 200, 250),
            (180, 20, 120),
            (70, 140, 35),
            (90, 45, 180),
        ]
    )
    output = io.BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=91,
        subsampling=0,
        optimize=False,
        progressive=False,
    )
    return output.getvalue()


def _rehash_manifest(manifest: dict) -> None:
    unsigned = dict(manifest)
    del unsigned["manifest_integrity"]
    manifest["manifest_integrity"]["canonical_sha256"] = hashlib.sha256(
        tool._canonical_json(unsigned)
    ).hexdigest()


def _all_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _all_string_values(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _all_string_values(nested)]
    return []


class PanelCandidatePhotoSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source_path = cls.root / "actual-small-source.jpg"
        cls.source_bytes = _small_jpeg()
        cls.source_path.write_bytes(cls.source_bytes)
        cls.manifest, cls.result, cls.frozen_source = tool.build_photo_candidate(
            cls.source_bytes,
            "image/jpeg",
            "cover",
            rotation_degrees=90,
            source_label=SOURCE_LABEL,
            source_rights=SOURCE_RIGHTS,
            algorithm=TEST_ALGORITHM,
            seed=0x10203040,
        )
        cls.bundle = cls.root / "photo-candidate"
        tool.write_candidate_directory(
            cls.bundle,
            cls.manifest,
            cls.result,
            source_input=cls.frozen_source,
        )
        cls.synthetic_manifest, cls.synthetic_result = tool.build_candidate(
            TEST_ALGORITHM,
            seed=0x10203040,
        )
        cls.synthetic_bundle = cls.root / "legacy-synthetic-candidate"
        tool.write_candidate_directory(
            cls.synthetic_bundle,
            cls.synthetic_manifest,
            cls.synthetic_result,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
        super().tearDownClass()

    def test_photo_cli_requires_the_complete_explicit_source_contract(self) -> None:
        complete = [
            "--output-dir",
            "candidate",
            "--source-image",
            "small.jpg",
            "--source-media-type",
            "image/jpeg",
            "--source-label",
            SOURCE_LABEL,
            "--source-rights",
            SOURCE_RIGHTS,
            "--fit",
            "cover",
            "--rotation-degrees",
            "90",
        ]
        args = tool.parse_args(complete)
        self.assertEqual(args.source_image, Path("small.jpg"))
        self.assertEqual(args.source_media_type, "image/jpeg")
        self.assertEqual(args.source_label, SOURCE_LABEL)
        self.assertEqual(args.source_rights, SOURCE_RIGHTS)
        self.assertEqual(args.fit, "cover")
        self.assertEqual(args.rotation_degrees, 90)

        incomplete = [
            ["--output-dir", "candidate", "--source-image", "small.jpg"],
            [
                "--output-dir",
                "candidate",
                "--source-image",
                "small.jpg",
                "--source-media-type",
                "image/jpeg",
                "--source-label",
                SOURCE_LABEL,
                "--source-rights",
                SOURCE_RIGHTS,
                "--fit",
                "cover",
            ],
            ["--output-dir", "candidate", "--source-media-type", "image/jpeg"],
            ["--validate-dir", "candidate", *complete[2:]],
            ["--validate-dir", "candidate", "--algorithm", "atkinson"],
            ["--validate-dir", "candidate", "--seed", "7"],
            ["--validate-dir", "candidate", "--dbs-evaluations", "8"],
            [
                "--output-dir",
                "candidate",
                "--source-im",
                "small.jpg",
                *complete[4:],
            ],
        ]
        for argv in incomplete:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    tool.parse_args(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_dbs_cli_exposes_the_full_application_deterministic_budget(self) -> None:
        args = tool.parse_args(
            [
                "--output-dir",
                "candidate",
                "--algorithm",
                SimulationAlgorithm.MULTICOLOR_DBS.value,
                "--dbs-evaluations",
                str(tool.MAX_DBS_EVALUATIONS),
            ]
        )
        self.assertEqual(args.dbs_evaluations, 1_000_000)
        options = tool._simulation_options(
            SimulationAlgorithm.MULTICOLOR_DBS,
            seed=0x10203040,
            dbs_evaluations=args.dbs_evaluations,
        )
        self.assertIsNotNone(options.budget)
        assert options.budget is not None
        self.assertEqual(options.budget.max_evaluations, 1_000_000)
        self.assertEqual(options.budget.max_accepted_moves, 250_000)
        self.assertEqual(options.budget.stagnation_evaluations, 500_000)

        for invalid in ("3", "1000001"):
            with self.subTest(value=invalid), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    tool.parse_args(
                        [
                            "--output-dir",
                            "candidate",
                            "--algorithm",
                            SimulationAlgorithm.MULTICOLOR_DBS.value,
                            "--dbs-evaluations",
                            invalid,
                        ]
                    )
                self.assertEqual(raised.exception.code, 2)

    def test_actual_small_jpeg_build_is_deterministic_writes_and_deep_validates(self) -> None:
        second_manifest, second_result, second_source = tool.build_photo_candidate(
            self.source_bytes,
            "image/jpeg",
            "cover",
            rotation_degrees=90,
            source_label=SOURCE_LABEL,
            source_rights=SOURCE_RIGHTS,
            algorithm=TEST_ALGORITHM,
            seed=0x10203040,
        )

        self.assertEqual(tool._canonical_json(second_manifest), tool._canonical_json(self.manifest))
        self.assertEqual(second_result.frame, self.result.frame)
        self.assertEqual(second_result.previews, self.result.previews)
        self.assertEqual(second_source, self.source_bytes)
        self.assertEqual(self.frozen_source, self.source_bytes)
        self.assertEqual({path.name for path in self.bundle.iterdir()}, tool.PHOTO_REQUIRED_FILES)
        self.assertEqual((self.bundle / tool.SOURCE_INPUT_FILENAME).read_bytes(), self.source_bytes)

        source = self.manifest["source"]
        self.assertEqual(self.manifest["schema_version"], tool.PHOTO_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(source["source_kind"], tool.PHOTO_SOURCE_KIND)
        self.assertEqual(
            source["input"],
            {
                "file": tool.SOURCE_INPUT_FILENAME,
                "bytes": len(self.source_bytes),
                "sha256": hashlib.sha256(self.source_bytes).hexdigest(),
                "media_type": "image/jpeg",
                "label": SOURCE_LABEL,
                "rights": SOURCE_RIGHTS,
            },
        )
        self.assertEqual(source["normalization"]["decoded_format"], "JPEG")
        self.assertEqual(source["normalization"]["fit"], "cover")
        self.assertEqual(source["normalization"]["explicit_rotation_degrees"], 90)
        self.assertNotIn(str(self.source_path.resolve()), _all_string_values(self.manifest))
        self.assertNotIn("path", source["input"])
        self.assertFalse(self.manifest["classification"]["upload_authorized"])
        self.assertFalse(self.manifest["transport"]["device_io_performed"])
        self.assertEqual(tool.validate_candidate_directory(self.bundle), self.manifest)

    def test_frozen_source_input_tamper_is_rejected(self) -> None:
        candidate = self.root / "tampered-source-candidate"
        shutil.copytree(self.bundle, candidate)
        frozen = candidate / tool.SOURCE_INPUT_FILENAME
        payload = bytearray(frozen.read_bytes())
        payload[len(payload) // 2] ^= 0x01
        frozen.write_bytes(payload)

        with self.assertRaisesRegex(tool.CandidateError, "photo source input identity"):
            tool.validate_candidate_directory(candidate)

    def test_wrong_declared_mime_is_rejected_during_build_and_deep_validation(self) -> None:
        with self.assertRaisesRegex(tool.CandidateError, "declared image/png.*JPEG"):
            tool.build_photo_candidate(
                self.source_bytes,
                "image/png",
                "cover",
                rotation_degrees=90,
                source_label=SOURCE_LABEL,
                source_rights=SOURCE_RIGHTS,
                algorithm=TEST_ALGORITHM,
                seed=0x10203040,
            )

        candidate = self.root / "wrong-mime-candidate"
        shutil.copytree(self.bundle, candidate)
        manifest_path = candidate / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source"]["input"]["media_type"] = "image/png"
        _rehash_manifest(manifest)
        manifest_path.write_bytes(tool._canonical_json(manifest))
        with self.assertRaisesRegex(tool.CandidateError, "declared image/png.*JPEG"):
            tool.validate_candidate_directory(candidate)

    def test_source_symlinks_are_rejected_before_build_and_during_validation(self) -> None:
        source_alias = self.root / "source-alias.jpg"
        try:
            source_alias.symlink_to(self.source_path.name)
        except OSError:
            self.skipTest("this account cannot create file symlinks")

        output = self.root / "source-alias-output"
        stderr = io.StringIO()
        with mock.patch.object(tool, "build_photo_candidate") as build, contextlib.redirect_stderr(
            stderr
        ):
            status = tool.main(
                [
                    "--output-dir",
                    str(output),
                    "--source-image",
                    str(source_alias),
                    "--source-media-type",
                    "image/jpeg",
                    "--source-label",
                    SOURCE_LABEL,
                    "--source-rights",
                    SOURCE_RIGHTS,
                    "--fit",
                    "cover",
                    "--rotation-degrees",
                    "90",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("symlink or reparse point", stderr.getvalue())
        self.assertFalse(output.exists())
        build.assert_not_called()

        real_parent = self.root / "real-source-parent"
        real_parent.mkdir()
        (real_parent / "nested.jpg").write_bytes(self.source_bytes)
        parent_alias = self.root / "source-parent-alias"
        try:
            parent_alias.symlink_to(real_parent, target_is_directory=True)
        except OSError:
            self.skipTest("this account cannot create directory symlinks")
        with self.assertRaisesRegex(tool.CandidateError, "symlink or reparse point"):
            tool._read_source_image(parent_alias / "nested.jpg")

        candidate = self.root / "symlinked-frozen-source-candidate"
        shutil.copytree(self.bundle, candidate)
        frozen = candidate / tool.SOURCE_INPUT_FILENAME
        external = self.root / "frozen-source-outside-bundle.input"
        frozen.replace(external)
        frozen.symlink_to(external)
        with self.assertRaisesRegex(
            tool.CandidateError, "candidate files.*symlink or reparse point"
        ):
            tool.validate_candidate_directory(candidate)

    def test_legacy_synthetic_bundle_contract_still_deep_validates(self) -> None:
        self.assertEqual(
            {path.name for path in self.synthetic_bundle.iterdir()}, tool.REQUIRED_FILES
        )
        self.assertFalse((self.synthetic_bundle / tool.SOURCE_INPUT_FILENAME).exists())
        self.assertEqual(
            self.synthetic_manifest["schema_version"], tool.MANIFEST_SCHEMA_VERSION
        )
        self.assertEqual(
            self.synthetic_manifest["source"]["pattern_id"], tool.SOURCE_PATTERN_ID
        )
        self.assertEqual(
            tool.validate_candidate_directory(self.synthetic_bundle),
            self.synthetic_manifest,
        )

    def test_boolean_legacy_schema_version_is_rejected_after_rehash(self) -> None:
        candidate = self.root / "boolean-schema-candidate"
        shutil.copytree(self.synthetic_bundle, candidate)
        manifest_path = candidate / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = True
        _rehash_manifest(manifest)
        manifest_path.write_bytes(tool._canonical_json(manifest))

        with self.assertRaisesRegex(tool.CandidateError, "manifest identity is invalid"):
            tool.validate_candidate_directory(candidate)

    def test_non_symlink_reparse_candidate_entry_is_rejected_before_read(self) -> None:
        target = (self.bundle / tool.SOURCE_INPUT_FILENAME).absolute()
        real_lstat = tool.os.lstat

        def marked_reparse(path):
            status = real_lstat(path)
            if Path(path).absolute() == target:
                return SimpleNamespace(
                    st_mode=status.st_mode,
                    st_file_attributes=0x0400,
                )
            return status

        with mock.patch.object(tool.os, "lstat", side_effect=marked_reparse):
            with self.assertRaisesRegex(
                tool.CandidateError, "candidate files.*symlink or reparse point"
            ):
                tool.validate_candidate_directory(self.bundle)

    def test_absolute_source_labels_are_rejected_instead_of_frozen(self) -> None:
        for label in (str(self.source_path.resolve()), "/tmp/private/source.jpg"):
            with self.subTest(label=label), self.assertRaisesRegex(
                tool.CandidateError, "source label must not be an absolute filesystem path"
            ):
                tool.build_photo_candidate(
                    self.source_bytes,
                    "image/jpeg",
                    "cover",
                    rotation_degrees=90,
                    source_label=label,
                    source_rights=SOURCE_RIGHTS,
                    algorithm=TEST_ALGORITHM,
                    seed=0x10203040,
                )

        candidate = self.root / "absolute-label-candidate"
        shutil.copytree(self.bundle, candidate)
        manifest_path = candidate / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source"]["input"]["label"] = str(self.source_path.resolve())
        _rehash_manifest(manifest)
        manifest_path.write_bytes(tool._canonical_json(manifest))
        with self.assertRaisesRegex(
            tool.CandidateError, "source label must not be an absolute filesystem path"
        ):
            tool.validate_candidate_directory(candidate)


if __name__ == "__main__":
    unittest.main()
