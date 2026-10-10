from __future__ import annotations

import contextlib
from io import BytesIO, StringIO
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock
import urllib.request

from PIL import Image

from host.epd_frame import HEIGHT, WIDTH, controller_stream, fnv1a, unpack_pixels
from tools import g1_s1_macro4_quality_candidate as tool


EXPECTED_COUNTS = {
    "code_order": [0, 1, 2, 3, 5, 6],
    "global": [255952, 139632, 47888, 67152, 53216, 50560],
    "left": [136304, 73360, 42720, 46256, 2528, 6032],
    "right": [119648, 66272, 5168, 20896, 50688, 44528],
    "left_minus_right": [16656, 7088, 37552, 25360, -48160, -38496],
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _transition_matrices(prior: bytes, final: bytes) -> tuple[list[list[int]], ...]:
    code_order = (0, 1, 2, 3, 5, 6)
    index = {code: offset for offset, code in enumerate(code_order)}
    global_matrix = [[0] * 6 for _ in code_order]
    left_matrix = [[0] * 6 for _ in code_order]
    right_matrix = [[0] * 6 for _ in code_order]
    for position, (old_code, new_code) in enumerate(zip(prior, final)):
        row = index[old_code]
        column = index[new_code]
        global_matrix[row][column] += 1
        x_value = position % WIDTH
        (left_matrix if x_value < WIDTH // 2 else right_matrix)[row][column] += 1
    return global_matrix, left_matrix, right_matrix


class Macro4QualityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        with mock.patch.object(
            tool.panel_candidate,
            "validate_candidate_directory",
            wraps=tool.panel_candidate.validate_candidate_directory,
        ) as baseline_validator, mock.patch.object(
            tool.low_spatial,
            "validate_diagnostic_directory",
            wraps=tool.low_spatial.validate_diagnostic_directory,
        ) as prior_validator:
            cls.artifacts = tool.build_macro4_artifacts()
            cls.baseline_validation_calls = baseline_validator.call_count
            cls.prior_validation_calls = prior_validator.call_count
        cls.bundle = cls.root / "macro4"
        cls.bundle.mkdir()
        for filename, payload in cls.artifacts.files().items():
            (cls.bundle / filename).write_bytes(payload)
        cls.manifest = cls.artifacts.manifest
        cls.frame = cls.artifacts.frame
        cls.codes = unpack_pixels(cls.frame)
        cls.prior_codes = unpack_pixels((tool.PRIOR_DIR / "frame.bin").read_bytes())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_box_filter_has_fixed_hash_and_explicit_two_stage_half_up_semantics(self) -> None:
        with Image.open(BytesIO((tool.BASELINE_DIR / "mapped.png").read_bytes())) as image:
            image.load()
            mapped_rgb8 = image.convert("RGB").tobytes()
        low_rgb8 = tool.box_downsample_4x4_half_up(mapped_rgb8)
        self.assertEqual((tool.MACRO_FACTOR, tool.LOW_WIDTH, tool.LOW_HEIGHT), (4, 256, 150))
        self.assertEqual(_sha256(low_rgb8), tool.EXPECTED_LOW_RGB8_SHA256)
        self.assertEqual(
            self.manifest["algorithm"]["downsample"],
            {
                "source": "byte-identical decoded mapped.png RGB8",
                "input_dimensions": [1024, 600],
                "output_dimensions": [256, 150],
                "method": "separable 4-sample uint8 mean with half-up rounding, horizontal then vertical",
                "factor": 4,
                "output_rgb8_sha256": tool.EXPECTED_LOW_RGB8_SHA256,
            },
        )

        # Red row sums 2, 2, 2, 1 prove the specified two-stage rounding:
        # rounded row means are 1, 1, 1, 0 and their rounded mean is 1,
        # whereas a single rounded 16-sample mean would be zero.
        synthetic = bytearray(WIDTH * HEIGHT * 3)
        for y_value, red in enumerate((2, 2, 2, 1)):
            synthetic[(y_value * WIDTH) * 3] = red
        for y_value in range(4):
            for x_value in range(4, 8):
                position = (y_value * WIDTH + x_value) * 3
                synthetic[position : position + 3] = bytes((10, 20, 30))
        reduced = tool.box_downsample_4x4_half_up(bytes(synthetic))
        self.assertEqual(reduced[:6], bytes((1, 0, 0, 10, 20, 30)))
        self.assertEqual(set(reduced[6:]), {0})
        self.assertEqual((7 + 8) // 16, 0)
        with self.assertRaisesRegex(tool.Macro4CandidateError, "fixed RGB8"):
            tool.box_downsample_4x4_half_up(b"short")

    def test_low_full_frame_controller_and_preview_identities_are_frozen(self) -> None:
        low_codes = bytes(
            self.codes[(low_y * tool.MACRO_FACTOR) * WIDTH + low_x * tool.MACRO_FACTOR]
            for low_y in range(tool.LOW_HEIGHT)
            for low_x in range(tool.LOW_WIDTH)
        )
        self.assertEqual(_sha256(low_codes), tool.EXPECTED_LOW_CODES_SHA256)
        self.assertEqual(
            self.manifest["algorithm"]["low_resolution"]["code_counts"],
            [15997, 8727, 2993, 4197, 3326, 3160],
        )
        self.assertEqual(_sha256(self.codes), tool.EXPECTED_CODES_SHA256)
        self.assertEqual(_sha256(self.frame), tool.EXPECTED_FRAME_SHA256)
        self.assertEqual(f"0x{fnv1a(self.frame):08X}", tool.EXPECTED_FRAME_FNV1A)

        controller_records = self.manifest["output"]["controllers"]
        for mapping, record, (expected_sha, expected_fnv) in zip(
            tool.CONTROLLER_MAPPINGS,
            controller_records,
            tool.EXPECTED_CONTROLLER_IDENTITIES,
        ):
            dtm = controller_stream(self.frame, mapping)
            self.assertEqual((_sha256(dtm), f"0x{fnv1a(dtm):08X}"), (expected_sha, expected_fnv))
            self.assertEqual((record["dtm_sha256"], record["dtm_fnv1a"]), (expected_sha, expected_fnv))

        self.assertEqual(_sha256((self.bundle / "strict-final.png").read_bytes()), tool.EXPECTED_STRICT_SHA256)
        self.assertEqual(_sha256((self.bundle / "model.png").read_bytes()), tool.EXPECTED_MODEL_SHA256)
        self.assertEqual(
            self.manifest["previews"]["strict_final"]["sha256"],
            tool.EXPECTED_STRICT_SHA256,
        )
        self.assertEqual(self.manifest["previews"]["model"]["sha256"], tool.EXPECTED_MODEL_SHA256)

    def test_every_output_pixel_is_exact_4x4_nearest_code_replication(self) -> None:
        low_codes = bytearray()
        for low_y in range(tool.LOW_HEIGHT):
            for low_x in range(tool.LOW_WIDTH):
                x0 = low_x * tool.MACRO_FACTOR
                y0 = low_y * tool.MACRO_FACTOR
                block = {
                    self.codes[(y0 + dy) * WIDTH + x0 + dx]
                    for dy in range(tool.MACRO_FACTOR)
                    for dx in range(tool.MACRO_FACTOR)
                }
                self.assertEqual(len(block), 1)
                low_codes.append(next(iter(block)))
        self.assertEqual(tool.expand_codes_4x4(bytes(low_codes)), self.codes)
        self.assertEqual(
            self.manifest["algorithm"]["upsample"],
            {
                "method": "nearest-neighbour exact physical-code replication",
                "macro_pixel_width": 4,
                "macro_pixel_height": 4,
            },
        )

    def test_counts_spatial_controller_and_macro_grid_metrics_are_independent_and_frozen(self) -> None:
        self.assertEqual(self.manifest["output"]["counts"], EXPECTED_COUNTS)
        self.assertEqual(
            [self.codes.count(code) for code in EXPECTED_COUNTS["code_order"]],
            EXPECTED_COUNTS["global"],
        )

        horizontal_internal = seam = vertical = 0
        boundary = bytearray(WIDTH * HEIGHT)
        controller_edges = [0, 0]
        for y_value in range(HEIGHT):
            row = y_value * WIDTH
            for x_value in range(WIDTH - 1):
                if self.codes[row + x_value] == self.codes[row + x_value + 1]:
                    continue
                boundary[row + x_value] = boundary[row + x_value + 1] = 1
                if x_value == WIDTH // 2 - 1:
                    seam += 1
                else:
                    horizontal_internal += 1
                    controller_edges[0 if x_value < WIDTH // 2 else 1] += 1
        for y_value in range(HEIGHT - 1):
            row = y_value * WIDTH
            for x_value in range(WIDTH):
                if self.codes[row + x_value] == self.codes[row + WIDTH + x_value]:
                    continue
                vertical += 1
                boundary[row + x_value] = boundary[row + WIDTH + x_value] = 1
                controller_edges[0 if x_value < WIDTH // 2 else 1] += 1

        expected_spatial = tool.EXPECTED_SPATIAL
        self.assertEqual(
            (horizontal_internal, seam, vertical, horizontal_internal + seam + vertical, sum(boundary)),
            (
                expected_spatial["horizontal_internal"],
                expected_spatial["controller_seam"],
                expected_spatial["vertical"],
                expected_spatial["total_edges"],
                expected_spatial["boundary_pixels"],
            ),
        )
        spatial = self.manifest["output"]["spatial_metrics"]
        for name, count in expected_spatial.items():
            self.assertEqual(spatial[name]["count"], count)
        self.assertEqual(tuple(controller_edges), tool.EXPECTED_CONTROLLER_INTERNAL_EDGES)
        self.assertEqual(
            [record["total_internal_edges"] for record in self.manifest["output"]["controller_internal_edges"]],
            list(tool.EXPECTED_CONTROLLER_INTERNAL_EDGES),
        )
        self.assertEqual(
            self.manifest["output"]["macro_grid_metrics"],
            {
                "definition": "four-neighbour code-difference edges split by 4x4 macro boundaries",
                "horizontal_macro_boundaries": 62792,
                "horizontal_inside_macro": 0,
                "vertical_macro_boundaries": 64204,
                "vertical_inside_macro": 0,
            },
        )

    def test_prior_transition_is_independently_recomputed_and_frozen(self) -> None:
        global_matrix, left_matrix, right_matrix = _transition_matrices(self.prior_codes, self.codes)
        transition = self.manifest["output"]["transition_from_true_screen_prior"]
        self.assertEqual(transition["global"], global_matrix)
        self.assertEqual(transition["left"], left_matrix)
        self.assertEqual(transition["right"], right_matrix)
        unchanged = sum(global_matrix[index][index] for index in range(6))
        self.assertEqual(unchanged, 154721)
        self.assertEqual(transition["unchanged_pixels"], unchanged)
        self.assertEqual(transition["changed_pixels"], tool.EXPECTED_CHANGED_PIXELS)
        self.assertEqual(transition["changed_ratio"], tool.EXPECTED_CHANGED_PIXELS / (WIDTH * HEIGHT))
        self.assertEqual(_sha256(tool._canonical_json(global_matrix)), "269222bb2a65625f0f06ec0ea2ebffcaadcc07c82de6fab25a68d365ba2cd9df")
        self.assertEqual(_sha256(tool._canonical_json(left_matrix)), "f158a241db2ab82f05a8ca21f82acb25a4db3956baebc3069aed73c66a66a73f")
        self.assertEqual(_sha256(tool._canonical_json(right_matrix)), "43ada4e20e44bdd88b3605fb7b2c7d5bb9a39edfe34a53c619588e5a95ea102b")

    def test_build_calls_both_frozen_input_deep_validators(self) -> None:
        self.assertEqual(self.baseline_validation_calls, 1)
        self.assertEqual(self.prior_validation_calls, 1)
        evidence = self.manifest["evidence"]
        self.assertEqual(
            evidence["baseline_blue_noise"]["deep_validator"],
            "tools.g1_s1_panel_candidate.validate_candidate_directory",
        )
        self.assertEqual(
            evidence["true_screen_prior"]["deep_validator"],
            "tools.g1_s1_low_spatial_diagnostic.validate_diagnostic_directory",
        )
        self.assertEqual(
            evidence["baseline_blue_noise"]["manifest_canonical_sha256"],
            tool.BASELINE_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            evidence["true_screen_prior"]["manifest_canonical_sha256"],
            tool.PRIOR_MANIFEST_CANONICAL_SHA256,
        )

    def test_manifest_is_canonical_exact_and_validator_deeply_regenerates(self) -> None:
        raw = (self.bundle / "manifest.json").read_bytes()
        self.assertEqual({path.name for path in self.bundle.iterdir()}, tool.REQUIRED_FILES)
        self.assertEqual(raw, tool._canonical_json(json.loads(raw)))
        self.assertEqual(_sha256(raw), "7c6f8569eb8a1cba9de144b7c660e79b932c1abbcbb5d6aa334ac694056420ad")
        unsigned = dict(self.manifest)
        del unsigned["manifest_integrity"]
        self.assertEqual(
            self.manifest["manifest_integrity"],
            {
                "canonical_sha256": _sha256(tool._canonical_json(unsigned)),
                "canonical_sha256_scope": tool.MANIFEST_HASH_SCOPE,
            },
        )
        with mock.patch.object(
            tool, "build_macro4_artifacts", return_value=self.artifacts
        ) as regenerate:
            self.assertEqual(tool.validate_macro4_directory(self.bundle), self.manifest)
        regenerate.assert_called_once_with()

    def test_writer_produces_only_the_deep_validated_file_set(self) -> None:
        destination = self.root / "written"
        with mock.patch.object(
            tool, "build_macro4_artifacts", return_value=self.artifacts
        ) as regenerate:
            manifest = tool.write_macro4_directory(destination)
        self.assertEqual(regenerate.call_count, 2)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual({path.name for path in destination.iterdir()}, tool.REQUIRED_FILES)
        self.assertEqual(
            {path.name: path.read_bytes() for path in destination.iterdir()},
            self.artifacts.files(),
        )

    def test_manifest_and_transport_remain_explicitly_offline_and_unqualified(self) -> None:
        self.assertEqual(
            self.manifest["classification"],
            {
                "experimental": True,
                "simulation_only": True,
                "formal": False,
                "hardware_qualified": False,
                "hardware_tested": False,
                "upload_authorized": False,
                "preview_review_status": "pending_runtime_authorization_record",
            },
        )
        self.assertEqual(
            self.manifest["transport"],
            {
                "mode": "offline",
                "endpoint": None,
                "method": None,
                "device_io_performed": False,
                "network_io_performed": False,
                "refresh_runner_implemented": False,
                "hardware_tested": False,
                "upload_authorized": False,
            },
        )


class Macro4QualitySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.artifacts = tool.build_macro4_artifacts()
        cls.bundle = cls.root / "macro4"
        cls.bundle.mkdir()
        for filename, payload in cls.artifacts.files().items():
            (cls.bundle / filename).write_bytes(payload)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _copy_bundle(self, name: str) -> Path:
        destination = self.root / name
        shutil.copytree(self.bundle, destination)
        return destination

    def test_tampered_frame_is_rejected_by_deep_regeneration(self) -> None:
        tampered = self._copy_bundle("tampered-frame")
        frame = bytearray((tampered / "frame.bin").read_bytes())
        frame[12345] ^= 0x10
        (tampered / "frame.bin").write_bytes(frame)
        with mock.patch.object(tool, "build_macro4_artifacts", return_value=self.artifacts):
            with self.assertRaisesRegex(tool.Macro4CandidateError, "frame.bin.*deep regeneration"):
                tool.validate_macro4_directory(tampered)

    def test_resigned_manifest_tamper_is_rejected_by_deep_regeneration(self) -> None:
        tampered = self._copy_bundle("resigned-manifest")
        manifest = json.loads((tampered / "manifest.json").read_bytes())
        manifest["classification"]["hardware_tested"] = True
        unsigned = dict(manifest)
        del unsigned["manifest_integrity"]
        manifest["manifest_integrity"] = {
            "canonical_sha256": _sha256(tool._canonical_json(unsigned)),
            "canonical_sha256_scope": tool.MANIFEST_HASH_SCOPE,
        }
        (tampered / "manifest.json").write_bytes(tool._canonical_json(manifest))
        with mock.patch.object(tool, "build_macro4_artifacts", return_value=self.artifacts):
            with self.assertRaisesRegex(tool.Macro4CandidateError, "manifest.*deep regeneration"):
                tool.validate_macro4_directory(tampered)

    def test_extra_file_and_existing_output_are_rejected_before_build(self) -> None:
        extra = self._copy_bundle("extra-file")
        (extra / "unexpected.txt").write_text("owner data", encoding="utf-8")
        with self.assertRaisesRegex(tool.Macro4CandidateError, "file set"):
            tool.validate_macro4_directory(extra)
        with mock.patch.object(
            tool,
            "build_macro4_artifacts",
            side_effect=AssertionError("existing output must be rejected before build"),
        ) as build:
            with self.assertRaisesRegex(tool.Macro4CandidateError, "already exists"):
                tool.write_macro4_directory(self.bundle)
        build.assert_not_called()

    def test_directory_and_file_symlinks_are_rejected(self) -> None:
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlinks unavailable")
        alias = self.root / "directory-alias"
        try:
            alias.symlink_to(self.bundle, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"this account cannot create directory symlinks: {error}")
        try:
            with self.assertRaisesRegex(tool.Macro4CandidateError, "symlink|real local directory"):
                tool.validate_macro4_directory(alias)
        finally:
            alias.unlink()

        linked = self._copy_bundle("linked-file")
        external = self.root / "external-source.png"
        external.write_bytes((linked / "source.png").read_bytes())
        (linked / "source.png").unlink()
        try:
            (linked / "source.png").symlink_to(external)
        except OSError as error:
            self.skipTest(f"this account cannot create file symlinks: {error}")
        with self.assertRaisesRegex(tool.Macro4CandidateError, "symlink"):
            tool.validate_macro4_directory(linked)


class Macro4QualitySurfaceTests(unittest.TestCase):
    def test_cli_exposes_only_mutually_exclusive_output_and_validate_modes(self) -> None:
        with contextlib.redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                tool.parse_args([])
            with self.assertRaises(SystemExit):
                tool.parse_args(["--output-dir", "one", "--validate-dir", "two"])
            for forbidden in (
                "--url",
                "--refresh",
                "--force",
                "--tile",
                "--tile-side",
            ):
                with self.assertRaises(SystemExit):
                    tool.parse_args(["--output-dir", "one", forbidden, "value"])
        output = tool.parse_args(["--output-dir", "one"])
        validate = tool.parse_args(["--validate-dir", "two"])
        self.assertEqual(vars(output), {"output_dir": Path("one"), "validate_dir": None})
        self.assertEqual(vars(validate), {"output_dir": None, "validate_dir": Path("two")})

    def test_module_reload_performs_no_network_or_socket_action(self) -> None:
        with mock.patch.object(
            urllib.request.OpenerDirector,
            "open",
            side_effect=AssertionError("urllib network access attempted"),
        ), mock.patch.object(
            urllib.request,
            "urlopen",
            side_effect=AssertionError("urlopen network access attempted"),
        ), mock.patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("socket connection attempted"),
        ), mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("socket connect attempted"),
        ), mock.patch.object(
            socket.socket,
            "connect_ex",
            side_effect=AssertionError("socket connect_ex attempted"),
        ):
            reloaded = importlib.reload(tool)
        self.assertIs(reloaded, tool)


if __name__ == "__main__":
    unittest.main()
