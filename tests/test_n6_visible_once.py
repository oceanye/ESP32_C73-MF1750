from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host.application.n6_visible_execution import (
    MANUAL_OBSERVATION_KIND,
    N6_ARM_CONFIRMATION,
    AtomicN6ClaimStore,
    execute_n6_formal_once,
    validate_n6_finalized_bundle,
    validate_n6_formal_manifest,
)
from host.visible_refresh_campaign import canonical_json_bytes
from tests.n6_formal_fixture import (
    CLAIMED_AT,
    COMPLETED_AT,
    MATERIALIZED_AT,
    artifact_and_config,
    authorization,
    browser_observation,
    formal_artifact_review,
    formal_manifest,
    measured_gamut_profile,
    offline_manifest,
    palette_aggregate,
    prior_result,
    reviewed_limit_profile,
    runtime_observation,
    runtime_review,
    success_protocol_result,
)
from tools import mf1750_n6_visible_once as runner


def _write(path: Path, value) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _invoke(arguments: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = runner.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def _receipt(workspace: Path):
    artifact, _ = artifact_and_config()
    return execute_n6_formal_once(
        formal_manifest(),
        artifact,
        authorization=authorization(),
        runtime_observation=runtime_observation(),
        browser_observation=browser_observation(),
        arm_confirmation=N6_ARM_CONFIRMATION,
        attempt_id="n6-cli-test-attempt",
        claimed_at=CLAIMED_AT,
        completed_at=COMPLETED_AT,
        claim_store=AtomicN6ClaimStore(workspace),
        protocol_driver=lambda _frame, _mappings: success_protocol_result(),
    )


class N6VisibleOnceCliTests(unittest.TestCase):
    def test_describe_missing_inputs_is_successful_and_side_effect_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            offline_path = root / "offline.json"
            _write(offline_path, offline_manifest())
            code, stdout, stderr = _invoke(
                [
                    "describe",
                    "--offline-manifest",
                    str(offline_path),
                    "--evaluated-at",
                    MATERIALIZED_AT,
                ]
            )
            self.assertEqual(code, 0, stderr)
            output = json.loads(stdout)
            self.assertFalse(output["materialization_ready"])
            self.assertFalse(output["claim_created"])
            self.assertFalse(output["network_io_performed"])
            self.assertEqual(list(root.iterdir()), [offline_path])

    def test_materialize_requires_complete_evidence_and_never_creates_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = {
                "offline": offline_manifest(),
                "palette": palette_aggregate(),
                "gamut": measured_gamut_profile(),
                "artifact-review": formal_artifact_review(),
                "limit": reviewed_limit_profile(),
                "runtime-review": runtime_review(),
                "prior": prior_result(),
            }
            paths: dict[str, Path] = {}
            for name, value in values.items():
                paths[name] = root / f"{name}.json"
                _write(paths[name], value)
            output_path = root / "formal.json"
            code, stdout, stderr = _invoke(
                [
                    "materialize",
                    "--offline-manifest",
                    str(paths["offline"]),
                    "--palette-aggregate",
                    str(paths["palette"]),
                    "--gamut-profile",
                    str(paths["gamut"]),
                    "--artifact-review",
                    str(paths["artifact-review"]),
                    "--limit-profile",
                    str(paths["limit"]),
                    "--runtime-review",
                    str(paths["runtime-review"]),
                    "--prior-result",
                    str(paths["prior"]),
                    "--materialized-at",
                    MATERIALIZED_AT,
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(code, 0, stderr)
            output = json.loads(stdout)
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            validate_n6_formal_manifest(manifest)
            self.assertFalse(output["claim_created"])
            self.assertFalse(output["device_io_performed"])
            declaration = manifest["action"]["claim"]
            self.assertFalse(
                (
                    root
                    / declaration["workspace_relative_registry"]
                    / declaration["filename"]
                ).exists()
            )
            second_code, _, _ = _invoke(
                [
                    "materialize",
                    "--offline-manifest",
                    str(paths["offline"]),
                    "--palette-aggregate",
                    str(paths["palette"]),
                    "--gamut-profile",
                    str(paths["gamut"]),
                    "--artifact-review",
                    str(paths["artifact-review"]),
                    "--limit-profile",
                    str(paths["limit"]),
                    "--runtime-review",
                    str(paths["runtime-review"]),
                    "--prior-result",
                    str(paths["prior"]),
                    "--materialized-at",
                    MATERIALIZED_AT,
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(second_code, 2)

    def test_finalize_requires_claim_in_same_fixed_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = _receipt(root)
            manifest_path = root / "manifest.json"
            receipt_path = root / "receipt.json"
            observation_path = root / "observation.json"
            _write(manifest_path, formal_manifest())
            _write(receipt_path, receipt)
            observation = {
                "observed_at": "2026-08-08T12:42:00+08:00",
                "observer_id": "n6-cli-test-observer",
                "full_panel_visual_matches_preview": True,
                "map_fidelity_pass": True,
                "orientation_seam_and_ghosting_normal": True,
                "supply_cv_current_normal": True,
                "post_refresh_current_normal": True,
                "temperature_normal": True,
                "esp32_unexpected_restart": False,
                "j2_state_after_observation": "on",
                "manual_evidence_sha256": "a" * 64,
                "notes": "test-only operator judgment",
            }
            _write(observation_path, observation)

            wrong_root = root / "wrong-root"
            wrong_root.mkdir()
            wrong_output = root / "wrong-bundle.json"
            with patch.object(runner, "REPO_ROOT", wrong_root):
                code, _, _ = _invoke(
                    [
                        "finalize",
                        "--manifest",
                        str(manifest_path),
                        "--receipt",
                        str(receipt_path),
                        "--observation",
                        str(observation_path),
                        "--finalized-at",
                        "2026-08-08T12:43:00+08:00",
                        "--output",
                        str(wrong_output),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertFalse(wrong_output.exists())

            output_path = root / "bundle.json"
            with patch.object(runner, "REPO_ROOT", root):
                code, stdout, stderr = _invoke(
                    [
                        "finalize",
                        "--manifest",
                        str(manifest_path),
                        "--receipt",
                        str(receipt_path),
                        "--observation",
                        str(observation_path),
                        "--finalized-at",
                        "2026-08-08T12:43:00+08:00",
                        "--output",
                        str(output_path),
                    ]
                )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout)["state"], "PASS")
            bundle = json.loads(output_path.read_text(encoding="utf-8"))
            validate_n6_finalized_bundle(bundle, manifest=formal_manifest())
            self.assertEqual(bundle["manual_observation"]["kind"], MANUAL_OBSERVATION_KIND)


if __name__ == "__main__":
    unittest.main()
