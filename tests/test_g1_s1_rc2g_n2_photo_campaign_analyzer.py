from __future__ import annotations

import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

from host.visible_refresh_campaign import (
    ResultState,
    build_result_record,
    canonical_json_bytes,
    result_file_sha256,
    seal_limit_profile,
)
from tests.test_g1_s1_rc2g_n2_photo_campaign_once import (
    EVALUATED_AT,
    _observation,
    _profile_payload,
)
from tools import g1_s1_rc2g_n2_photo_campaign as compiler
from tools import g1_s1_rc2g_n2_photo_campaign_analyzer as analyzer
from tools import g1_s1_rc2g_n2_photo_campaign_once as fixed


class N2PPhotoCampaignAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = compiler.compile_campaign_manifest()

    def setUp(self) -> None:
        hardware = fixed.REPO_ROOT / ".test-output" / "hardware"
        self.temporary = tempfile.TemporaryDirectory(dir=hardware)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "claims"
        self.registry.mkdir()
        self.compile_patch = mock.patch.object(
            analyzer, "compile_campaign_manifest", return_value=self.manifest
        )
        self.registry_patch = mock.patch.object(
            fixed, "DEFAULT_CLAIM_REGISTRY", self.registry
        )
        self.time_patch = mock.patch.object(
            fixed, "_utc_now", return_value="2026-08-08T00:00:30Z"
        )
        self.compile_patch.start()
        self.registry_patch.start()
        self.time_patch.start()
        self.addCleanup(self.compile_patch.stop)
        self.addCleanup(self.registry_patch.stop)
        self.addCleanup(self.time_patch.stop)

    def _write(self, path: Path, value) -> str:
        payload = canonical_json_bytes(value)
        path.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def _profile(self, *, target: bool):
        return seal_limit_profile(
            _profile_payload(
                self.manifest["p0_campaign_contract"], prior_completed=target
            )
        )

    def _claim(
        self,
        key: str,
        snapshot,
        directory: Path,
        profile,
        profile_file_sha: str,
        attempt_id: str,
        prior_result_sha: str | None,
    ):
        record = {
            "schema_version": 1,
            "kind": fixed.CLAIM_KIND,
            "registry_id": fixed.CLAIM_REGISTRY_ID,
            "action_key": key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "campaign_canonical_sha256": fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
            "p0_campaign_canonical_sha256": (
                fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
            ),
            "execution_supplement_file_sha256": (
                fixed.EXECUTION_SUPPLEMENT_FILE_SHA256
            ),
            "attempt_id": attempt_id,
            "claimed_at": "2026-08-08T00:00:00Z",
            "state": "authorization_permanently_consumed_do_not_rerun",
            "authorization_consumed_permanently": True,
            "authorization_confirmation_sha256": (
                fixed.authorization_confirmation_sha256(key)
            ),
            "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
            "profile_file_sha256": profile_file_sha,
            "prior_result_file_sha256": prior_result_sha,
            "start_temperature_c": 25.0,
            "confirmations": {"synthetic_offline_chain_fixture": True},
            "result_directory": str(directory),
            "maximum_post_requests": 1,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }
        filename = snapshot.action["claim"]["filename"]
        file_sha = self._write(self.registry / filename, record)
        return {
            "registry_id": fixed.CLAIM_REGISTRY_ID,
            "filename": filename,
            "file_sha256": file_sha,
            "attempt_id": attempt_id,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "state": "authorization_permanently_consumed_do_not_rerun",
        }

    def _chain(
        self,
        key: str,
        *,
        score_values: tuple[int, ...] | None = None,
        prior_result_sha: str | None = None,
        camera_capture: bool = False,
    ) -> tuple[Path, str]:
        target = key.endswith("-target")
        snapshot = fixed._load_action_snapshot(
            key, _validated_manifest=self.manifest
        )
        directory = self.root / key
        directory.mkdir()
        profile = self._profile(target=target)
        profile_sha = self._write(directory / fixed.PROFILE_FILENAME, profile)
        attempt_id = f"attempt-{key}"
        claim = self._claim(
            key,
            snapshot,
            directory,
            profile,
            profile_sha,
            attempt_id,
            prior_result_sha,
        )
        lock = {
            "schema_version": 1,
            "kind": fixed.LOCK_KIND,
            "attempt_id": attempt_id,
            "action_key": key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "claim": claim,
            "confirmations": {"synthetic_offline_chain_fixture": True},
            "authorization_confirmation_sha256": (
                fixed.authorization_confirmation_sha256(key)
            ),
            "state": "authorization_permanently_consumed_do_not_rerun",
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }
        self._write(directory / fixed.LOCK_FILENAME, lock)
        protocol = (
            {
                "fresh_boot_preflight": {"job_id": 0},
                "completed_map_evidence": {
                    "job_raw": {"job_id": 1},
                    "diagnostic_raw": {"operation_id": 1},
                },
            }
            if not target
            else {
                "same_cell_primer_live_preflight": {"job_id": 1},
                "network_report": {"protocol_verified": True},
                "target_job_raw": {"job_id": 2},
                "target_diagnostic_raw": {"operation_id": 2},
                "target_diagnostic_validated": {"operation_id": 2},
                "post_refresh_gpio_status_raw": {
                    "busy": 0,
                    "rst": 0,
                    "cs": 0,
                    "cs2": 0,
                },
            }
        )
        evidence = {
            "schema_version": 1,
            "kind": fixed.EVIDENCE_KIND,
            "runner_kind": fixed.RUNNER_KIND,
            "attempt_id": attempt_id,
            "recorded_at": "2026-08-08T00:00:00Z",
            "protocol_completed_at": "2026-08-08T00:00:30Z",
            "action_key": key,
            "cell_id": snapshot.cell_id,
            "phase": snapshot.phase,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "campaign_canonical_sha256": fixed.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
            "p0_campaign_canonical_sha256": (
                fixed.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256
            ),
            "execution_supplement_file_sha256": (
                fixed.EXECUTION_SUPPLEMENT_FILE_SHA256
            ),
            "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
            "reference_preview": dict(snapshot.reference_preview),
            "claim": claim,
            "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
            "profile_file_sha256": profile_sha,
            "profile_evaluated_at": EVALUATED_AT,
            "prior_result_file_sha256": prior_result_sha,
            "start_temperature_c": 25.0,
            "scoring_contract_sha256": fixed.SCORING_CONTRACT_SHA256,
            "camera_observation_contract_sha256": (
                fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
            ),
            "maximum_post_requests": 1,
            "automatic_retry_count": 0,
            "retry_allowed": False,
            "recovery_performed": False,
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
            "protocol_evidence": protocol,
            "request_audit": {
                "post_attempt_count": 1,
                "post_issued_count": 1,
                "calls": [{"method": "POST", "endpoint": "/api/frame"}],
            },
            "error": None,
        }
        evidence_sha = self._write(directory / fixed.EVIDENCE_FILENAME, evidence)
        raw_observation = _observation(snapshot, target=target)
        if target and score_values is not None:
            for dimension, score in zip(analyzer.SCORE_DIMENSIONS, score_values):
                raw_observation["visual"][dimension] = score
        camera_binding = None
        if target and camera_capture:
            image = Image.new("RGB", (8, 8), (20, 40, 60))
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            photo = buffer.getvalue()
            photo_sha = hashlib.sha256(photo).hexdigest()
            (directory / fixed.CAMERA_CAPTURE_FILENAME).write_bytes(photo)
            raw_observation["camera"] = {
                "capture_performed": True,
                "file": "original-camera-photo.png",
                "sha256": photo_sha,
                "camera_id": "same-fixed-camera",
                "tripod_position_id": "n2p-fixed-position-v1",
                "lighting_setup_id": "n2p-fixed-lighting-v1",
                "exposure_mode": "manual-locked",
                "white_balance_mode": "manual-locked",
                "focus_mode": "manual-locked",
                "image_processing": "disabled-or-fixed",
                "full_panel_uncropped": True,
            }
            camera_binding = {
                "copied_file": fixed.CAMERA_CAPTURE_FILENAME,
                "bytes": len(photo),
                "sha256": photo_sha,
                "decoded_format": "PNG",
                "width": 8,
                "height": 8,
                "source_path_recorded_but_not_trusted_after_copy": (
                    "original-camera-photo.png"
                ),
            }
        raw_sha = hashlib.sha256(canonical_json_bytes(raw_observation)).hexdigest()
        stored_observation = {
            **raw_observation,
            "visual_pass": True,
            "electrical_pass": True,
            "post_refresh_temperature_pass": True,
            "overall_state": "PASS",
            "scoring_contract_sha256": fixed.SCORING_CONTRACT_SHA256,
            "camera_observation_contract_sha256": (
                fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
            ),
            "source_observation_file_sha256": raw_sha,
            "verified_camera_evidence": camera_binding,
        }
        observation_sha = self._write(
            directory / fixed.OBSERVATION_FILENAME, stored_observation
        )
        finalization = {
            "schema_version": 1,
            "kind": fixed.FINALIZATION_KIND,
            "action_key": key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "state": "PASS",
            "protocol_evidence_file_sha256": evidence_sha,
            "observation_file_sha256": observation_sha,
            "profile_file_sha256": profile_sha,
            "post_refresh_temperature_c": 26.0,
            "visual_pass": True,
            "electrical_pass": True,
            "post_refresh_temperature_pass": True,
            "visual_and_electrical_assessed_separately": True,
            "scoring_contract_sha256": fixed.SCORING_CONTRACT_SHA256,
            "camera_observation_contract_sha256": (
                fixed.CAMERA_OBSERVATION_CONTRACT_SHA256
            ),
            "camera_capture_file_sha256": (
                camera_binding["sha256"] if camera_binding else None
            ),
            "camera_capture_present_for_this_action": camera_binding is not None,
            "cross_candidate_camera_comparability": (
                "not_established_by_single_action; requires verified fixed-camera "
                "captures for all four N2P targets"
            ),
        }
        finalization_sha = self._write(
            directory / fixed.FINALIZATION_FILENAME, finalization
        )
        result = build_result_record(
            action_identity_sha256=snapshot.action["action_identity_sha256"],
            state=ResultState.PASS,
            completed_at=raw_observation["observed_at"],
            evidence_manifest_sha256=finalization_sha,
            post_request_count=1,
            details="synthetic analyzer fixture",
        )
        self._write(directory / fixed.P0_RESULT_FILENAME, result)
        return directory, result_file_sha256(result)

    def _campaign(
        self,
        *,
        tie: bool = False,
        camera_capture: bool = False,
        missing_camera_cell: int | None = None,
    ) -> dict[str, Path]:
        scores = {
            1: (3, 3, 4, 4, 4, 4),
            2: (3, 4, 4, 4, 4, 4),
            3: (4, 4, 4, 4, 4, 4),
            4: (4, 4, 4, 4, 4, 4) if tie else (5, 4, 4, 4, 4, 4),
        }
        directories: dict[str, Path] = {}
        for cell in range(1, 5):
            primer_key = f"q{cell}-map-primer"
            target_key = f"q{cell}-target"
            primer_dir, primer_sha = self._chain(primer_key)
            target_dir, _target_sha = self._chain(
                target_key,
                score_values=scores[cell],
                prior_result_sha=primer_sha,
                camera_capture=(
                    camera_capture and cell != missing_camera_cell
                ),
            )
            directories[primer_key] = primer_dir
            directories[target_key] = target_dir
        return directories

    def test_unique_score_winner_emits_exact_q4_identity(self) -> None:
        result = analyzer.analyze_n2p_campaign(self._campaign())
        self.assertTrue(result["winner_gates"]["all_pass"])
        self.assertFalse(result["tie_state"]["top_tie"])
        self.assertEqual(result["selected_winner"]["cell_id"], "Q4")
        self.assertEqual(result["selected_winner"]["score_total"], 25)
        self.assertEqual(
            result["selected_winner"]["action_identity_sha256"],
            fixed.FIXED_ACTION_SHA256S["q4-target"],
        )
        self.assertEqual(
            result["selected_winner"]["authorized_use"],
            "N3_branch_selection_only",
        )
        self.assertFalse(result["selected_winner"]["algorithm_qualified"])
        self.assertFalse(result["classification"]["population_inference"])
        self.assertEqual(
            result["selection_interpretation"]["selection_scope"],
            "exact_frozen_N2P_campaign_only",
        )
        self.assertFalse(result["camera_comparability"]["comparable"])
        self.assertEqual(
            result["camera_comparability"]["verified_target_capture_count"], 0
        )

    def test_equal_top_total_is_explicit_tie_without_winner(self) -> None:
        result = analyzer.analyze_n2p_campaign(self._campaign(tie=True))
        self.assertTrue(result["tie_state"]["top_tie"])
        self.assertEqual(result["tie_state"]["top_tied_cell_ids"], ["Q3", "Q4"])
        self.assertFalse(result["tie_state"]["arbitrary_tie_break_performed"])
        self.assertFalse(result["winner_gates"]["all_pass"])
        self.assertIsNone(result["selected_winner"])

    def test_camera_comparable_only_when_all_four_verified_and_same(self) -> None:
        result = analyzer.analyze_n2p_campaign(
            self._campaign(camera_capture=True)
        )
        self.assertTrue(result["camera_comparability"]["comparable"])
        self.assertEqual(
            result["camera_comparability"]["verified_target_capture_count"], 4
        )
        self.assertFalse(
            result["camera_comparability"]["affects_manual_score_winner"]
        )

    def test_three_verified_captures_are_explicitly_not_comparable(self) -> None:
        result = analyzer.analyze_n2p_campaign(
            self._campaign(camera_capture=True, missing_camera_cell=4)
        )
        self.assertFalse(result["camera_comparability"]["comparable"])
        self.assertEqual(
            result["camera_comparability"]["verified_target_capture_count"], 3
        )
        self.assertIn(
            "verified_target_capture_missing",
            result["camera_comparability"]["reasons"],
        )

    def test_missing_and_cross_action_replay_fail_closed(self) -> None:
        directories = self._campaign()
        missing = dict(directories)
        missing.pop("q4-target")
        with self.assertRaisesRegex(analyzer.N2PCampaignAnalysisError, "exactly"):
            analyzer.analyze_n2p_campaign(missing)
        replay = dict(directories)
        replay["q2-target"] = replay["q1-target"]
        with self.assertRaisesRegex(
            analyzer.N2PCampaignAnalysisError, "binding|replay"
        ):
            analyzer.analyze_n2p_campaign(replay)

    def test_finalization_tamper_is_rejected(self) -> None:
        directories = self._campaign()
        path = directories["q3-target"] / fixed.FINALIZATION_FILENAME
        value = json.loads(path.read_text(encoding="utf-8"))
        value["visual_pass"] = False
        path.write_bytes(canonical_json_bytes(value))
        with self.assertRaisesRegex(
            analyzer.N2PCampaignAnalysisError, "result binding|verdict"
        ):
            analyzer.analyze_n2p_campaign(directories)

    def test_resealed_semantic_tamper_is_rejected_by_analysis_validator(self) -> None:
        analysis = analyzer.analyze_n2p_campaign(self._campaign())
        tampered = copy.deepcopy(analysis)
        tampered["classification"]["algorithm_qualified"] = True
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = {
            "canonical_sha256": hashlib.sha256(
                canonical_json_bytes(unsigned)
            ).hexdigest(),
            "canonical_sha256_scope": analyzer.ANALYSIS_HASH_SCOPE,
        }
        with self.assertRaisesRegex(
            analyzer.N2PCampaignAnalysisError, "classification"
        ):
            analyzer.validate_n2p_analysis(tampered)


if __name__ == "__main__":
    unittest.main()
