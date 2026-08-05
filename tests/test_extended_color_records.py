from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from host.extended_color import (
    NULL_MEASUREMENT_FIELDS,
    build_artifact,
    build_empty_transition_profile,
    validate_transition_profile,
)
from tools.mf1750_asset_manifest import (
    FROZEN_PRODUCTION_RELATIVE,
    ManifestError,
    build_manifest,
    validate_manifest_report,
    validate_output_path,
    write_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = REPO_ROOT / "schemas" / "extended_color"


class SchemaDocumentTests(unittest.TestCase):
    def test_local_test_output_is_explicitly_ignored(self) -> None:
        ignored = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn(".test-output/", ignored)

    def test_all_record_schemas_are_strict_json_schema_documents(self) -> None:
        expected = {
            "asset_manifest.schema.json",
            "electrical.schema.json",
            "event_recovery.schema.json",
            "optical.schema.json",
            "run.schema.json",
            "transition_profile.schema.json",
        }
        actual = {path.name for path in SCHEMA_ROOT.glob("*.schema.json")}
        self.assertEqual(actual, expected)
        for name in sorted(expected):
            with self.subTest(name=name):
                schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["type"], "object")
                self.assertFalse(schema["additionalProperties"])

    def test_transition_profile_requires_36_cells_and_nullable_measurements(self) -> None:
        schema = json.loads(
            (SCHEMA_ROOT / "transition_profile.schema.json").read_text(encoding="utf-8")
        )
        cells = schema["properties"]["cells"]
        self.assertEqual((cells["minItems"], cells["maxItems"]), (36, 36))
        self.assertEqual(schema["properties"]["color_codes"]["const"], [0, 1, 2, 3, 5, 6])
        properties = cells["items"]["properties"]
        self.assertEqual(properties["delta_e00_mean"]["$ref"], "#/$defs/nullable_nonnegative")
        self.assertIn("null", schema["$defs"]["nullable_nonnegative"]["type"])

        profile = build_empty_transition_profile()
        self.assertFalse(profile["hardware_tested"])
        self.assertIsNone(profile["generated_at"])
        self.assertEqual(len(profile["cells"]), 36)
        self.assertEqual(
            {(cell["old_code"], cell["new_code"]) for cell in profile["cells"]},
            {(old, new) for old in (0, 1, 2, 3, 5, 6) for new in (0, 1, 2, 3, 5, 6)},
        )
        for cell in profile["cells"]:
            self.assertEqual(cell["sample_count"], 0)
            self.assertTrue(all(cell[field] is None for field in NULL_MEASUREMENT_FIELDS))
        validate_transition_profile(profile)

        duplicate = json.loads(json.dumps(profile))
        duplicate["cells"][1]["old_code"] = duplicate["cells"][0]["old_code"]
        duplicate["cells"][1]["new_code"] = duplicate["cells"][0]["new_code"]
        with self.assertRaisesRegex(ValueError, "duplicate pair"):
            validate_transition_profile(duplicate)

        inconsistent = json.loads(json.dumps(profile))
        inconsistent["cells"][0]["delta_e00_mean"] = 1.0
        with self.assertRaisesRegex(ValueError, "unmeasured values null"):
            validate_transition_profile(inconsistent)

    def test_run_schema_freezes_frame_and_mapping_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "run.schema.json").read_text(encoding="utf-8"))
        identity = schema["properties"]["frame_identity"]["properties"]
        self.assertEqual(identity["width"]["const"], 1024)
        self.assertEqual(identity["height"]["const"], 600)
        self.assertEqual(identity["frame_bytes"]["const"], 307200)
        self.assertEqual(schema["$defs"]["mapping_cs1"]["const"]["source_half"], 0)
        self.assertEqual(schema["$defs"]["mapping_cs2"]["const"]["source_half"], 1)

        generated = build_artifact("transition-target", 1).identity.to_dict()
        required = set(schema["properties"]["frame_identity"]["required"])
        self.assertEqual(set(generated), required)
        self.assertIsInstance(generated["frame_fnv1a"], int)
        self.assertRegex(generated["frame_fnv1a_hex"], r"^0x[0-9A-F]{8}$")
        self.assertEqual(
            [controller["mapping"] for controller in generated["controllers"]],
            [
                schema["$defs"]["mapping_cs1"]["const"],
                schema["$defs"]["mapping_cs2"]["const"],
            ],
        )

    def test_electrical_schema_records_all_input_current_metrics(self) -> None:
        schema = json.loads(
            (SCHEMA_ROOT / "electrical.schema.json").read_text(encoding="utf-8")
        )
        required = set(schema["properties"]["input_power"]["required"])
        self.assertTrue(
            {"peak_current_a", "mean_current_a", "rms_current_a", "energy_j", "droop_v"}
            <= required
        )


class AssetManifestTests(unittest.TestCase):
    def make_plan(self) -> dict[str, object]:
        return {
            "run_id": "EC5-D-PILOT-001",
            "root_label": "removable-evidence-volume-01",
            "hardware_tested": False,
            "assets": [
                {
                    "role": "raw_camera",
                    "path": "camera/sample.raw",
                    "captured_at": None,
                    "instrument_id": "CAM-01",
                },
                {
                    "role": "oscilloscope",
                    "path": "scope/sample.bin",
                    "captured_at": "2026-08-05T09:30:00+08:00",
                    "instrument_id": "SCOPE-01",
                },
            ],
        }

    def test_explicit_assets_receive_sha256_size_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "camera").mkdir()
            (root / "scope").mkdir()
            raw = b"synthetic raw bytes\x00\x01"
            trace = b"synthetic trace bytes\x02\x03"
            (root / "camera" / "sample.raw").write_bytes(raw)
            (root / "scope" / "sample.bin").write_bytes(trace)
            report = build_manifest(
                self.make_plan(), root, created_at="2026-08-05T10:00:00+08:00"
            )
        self.assertFalse(report["hardware_tested"])
        self.assertEqual(report["assets"][0]["relative_path"], "camera/sample.raw")
        self.assertEqual(report["assets"][0]["bytes"], len(raw))
        self.assertEqual(report["assets"][0]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["assets"][1]["sha256"], hashlib.sha256(trace).hexdigest())

    def test_plan_rejects_traversal_unknown_roles_duplicates_and_extra_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "asset.bin").write_bytes(b"asset")
            base = {
                "run_id": "run",
                "root_label": "root",
                "hardware_tested": False,
                "assets": [
                    {
                        "role": "other",
                        "path": "asset.bin",
                        "captured_at": None,
                        "instrument_id": None,
                    }
                ],
            }
            traversal = json.loads(json.dumps(base))
            traversal["assets"][0]["path"] = "../asset.bin"
            with self.assertRaisesRegex(ManifestError, "relative path"):
                build_manifest(traversal, root)
            role = json.loads(json.dumps(base))
            role["assets"][0]["role"] = "device_refresh"
            with self.assertRaisesRegex(ManifestError, "unsupported"):
                build_manifest(role, root)
            duplicate = json.loads(json.dumps(base))
            duplicate["assets"].append(dict(duplicate["assets"][0]))
            with self.assertRaisesRegex(ManifestError, "duplicate"):
                build_manifest(duplicate, root)
            extra = json.loads(json.dumps(base))
            extra["url"] = "http://device"
            with self.assertRaisesRegex(ManifestError, "unknown keys"):
                build_manifest(extra, root)

    def test_output_is_exclusive_create_and_frozen_production_is_rejected(self) -> None:
        report = {
            "schema_version": 1,
            "kind": "mf1750-extended-color-asset-manifest",
            "run_id": "run",
            "created_at": "2026-08-05T10:00:00+08:00",
            "root_label": "root",
            "hardware_tested": False,
            "assets": [
                {
                    "role": "other",
                    "relative_path": "asset.bin",
                    "bytes": 5,
                    "sha256": hashlib.sha256(b"asset").hexdigest(),
                    "captured_at": None,
                    "instrument_id": None,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "manifest.json"
            write_manifest(report, output)
            with self.assertRaisesRegex(ManifestError, "never overwrites"):
                write_manifest(report, output)

        with self.assertRaisesRegex(ManifestError, "protected production"):
            validate_output_path(REPO_ROOT / FROZEN_PRODUCTION_RELATIVE / "manifest.json")
        with self.assertRaisesRegex(ManifestError, "protected .test-output"):
            validate_output_path(REPO_ROOT / ".test-output" / "manifest.json")

    def test_writer_rejects_schema_invalid_report(self) -> None:
        invalid = {
            "schema_version": 1,
            "kind": "mf1750-extended-color-asset-manifest",
            "run_id": "run",
            "created_at": "2026-08-05T10:00:00+08:00",
            "root_label": "root",
            "hardware_tested": False,
            "assets": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ManifestError, "non-empty"):
                write_manifest(invalid, Path(temporary) / "manifest.json")

        valid = dict(invalid)
        valid["assets"] = [
            {
                "role": "other",
                "relative_path": "asset.bin",
                "bytes": 5,
                "sha256": hashlib.sha256(b"asset").hexdigest(),
                "captured_at": None,
                "instrument_id": None,
            }
        ]
        for unsafe_path in ("C:/outside.bin", r"\\server\share\outside.bin"):
            with self.subTest(unsafe_path=unsafe_path):
                candidate = json.loads(json.dumps(valid))
                candidate["assets"][0]["relative_path"] = unsafe_path
                with self.assertRaisesRegex(ManifestError, "relative POSIX path"):
                    validate_manifest_report(candidate)

    def test_cli_has_no_repo_root_guard_override(self) -> None:
        source = (REPO_ROOT / "tools" / "mf1750_asset_manifest.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("--repo-root", source)


if __name__ == "__main__":
    unittest.main()
