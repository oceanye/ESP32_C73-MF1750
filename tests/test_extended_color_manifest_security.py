from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.mf1750_asset_manifest import (
    ManifestError,
    build_manifest,
    validate_manifest_report,
    validate_plan_path,
)


def _plan(asset_path: str = "asset.bin") -> dict[str, object]:
    return {
        "run_id": "security-test",
        "root_label": "temporary-test-root",
        "hardware_tested": False,
        "assets": [
            {
                "role": "other",
                "path": asset_path,
                "captured_at": None,
                "instrument_id": None,
            }
        ],
    }


def _report(relative_path: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "mf1750-extended-color-asset-manifest",
        "run_id": "security-test",
        "created_at": "2026-08-05T10:00:00Z",
        "root_label": "temporary-test-root",
        "hardware_tested": False,
        "assets": [
            {
                "role": "other",
                "relative_path": relative_path,
                "bytes": 0,
                "sha256": "0" * 64,
                "captured_at": None,
                "instrument_id": None,
            }
        ],
    }


class ManifestPathSecurityTests(unittest.TestCase):
    def test_report_rejects_backslashes_and_windows_traversal(self) -> None:
        for relative_path in (r"folder\asset.bin", r"..\escape.bin"):
            with self.subTest(relative_path=relative_path):
                with self.assertRaisesRegex(ManifestError, "POSIX"):
                    validate_manifest_report(_report(relative_path))

    def test_asset_plan_rejects_backslash_paths_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "asset.bin").write_bytes(b"asset")
            with self.assertRaisesRegex(ManifestError, "POSIX"):
                build_manifest(_plan(r"folder\asset.bin"), root)

    def test_plan_path_must_be_resolved_local_regular_and_unprotected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = root / "plan.json"
            plan.write_text(json.dumps(_plan()), encoding="utf-8")
            self.assertEqual(validate_plan_path(plan), plan.resolve(strict=True))

            with self.assertRaisesRegex(ManifestError, "regular file"):
                validate_plan_path(root)

            protected = root / ".test-output"
            protected.mkdir()
            protected_plan = protected / "plan.json"
            protected_plan.write_text(json.dumps(_plan()), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, r"\.test-output"):
                validate_plan_path(protected_plan)

            link = root / "linked-plan.json"
            try:
                link.symlink_to(plan)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(ManifestError, "symbolic link"):
                    validate_plan_path(link)

        for unsafe in (Path("COM8.json"), Path(r"\\server\share\plan.json")):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ManifestError):
                    validate_plan_path(unsafe)


class StableAssetHashTests(unittest.TestCase):
    def test_same_descriptor_is_checked_before_and_after_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "asset.bin"
            asset.write_bytes(b"stable evidence")
            real_fstat = os.fstat
            descriptors: list[int] = []

            def changing_fstat(descriptor: int) -> os.stat_result:
                descriptors.append(descriptor)
                result = real_fstat(descriptor)
                if len(descriptors) == 2:
                    fields = list(result)
                    fields[6] += 1
                    return os.stat_result(fields)
                return result

            with patch(
                "tools.mf1750_asset_manifest.os.fstat", side_effect=changing_fstat
            ):
                with self.assertRaisesRegex(ManifestError, "changed while hashing"):
                    build_manifest(_plan(), root)
            self.assertGreaterEqual(len(descriptors), 2)
            self.assertEqual(descriptors[0], descriptors[1])


if __name__ == "__main__":
    unittest.main()
