from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import inspect
from io import BytesIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from PIL import Image

from host.visible_refresh_campaign import (
    LIMIT_PROFILE_KIND,
    canonical_json_bytes,
    seal_limit_profile,
)
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_rc2g_n2_photo_campaign as compiler
from tools import g1_s1_rc2g_n2_photo_campaign_once as runner


EVALUATED_AT = "2026-08-08T00:02:00Z"
PRIMER_OBSERVED_AT = "2026-08-08T00:01:00Z"
TARGET_OBSERVED_AT = "2026-08-08T00:03:00Z"


def _profile_payload(
    campaign,
    *,
    prior_completed: bool,
    expires_at: str = "2026-09-01T00:00:00Z",
    usage_override: dict[str, object] | None = None,
) -> dict[str, object]:
    allowlist = []
    for action in campaign["actions"]:
        identity = action["identity"]
        allowlist.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": "POST",
                "endpoint": "/api/frame",
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    usage: dict[str, object] = {
        "cumulative_visible_refresh_count": 1 if prior_completed else 0,
        "session_visible_refresh_count": 1 if prior_completed else 0,
        "consecutive_visible_refresh_count": 1 if prior_completed else 0,
        "last_visible_refresh_completed_at": (
            PRIMER_OBSERVED_AT if prior_completed else None
        ),
        "snapshot_at": (
            "2026-08-08T00:01:30Z"
            if prior_completed
            else "2026-08-08T00:00:00Z"
        ),
        "evidence_sha256": "5" * 64,
    }
    usage.update(usage_override or {})
    return {
        "schema_version": 1,
        "kind": LIMIT_PROFILE_KIND,
        "profile_id": "n2p-reviewed-test-profile",
        "profile_version": "1.0.0",
        "panel": dict(campaign["panel"]),
        "firmware": dict(campaign["firmware"]),
        "action_allowlist": allowlist,
        "limits": {
            "maximum_campaign_visible_refreshes": 8,
            "maximum_session_visible_refreshes": 2,
            "maximum_consecutive_visible_refreshes": 2,
            "minimum_interval_seconds": 0,
            "minimum_cooldown_seconds": 0,
            "minimum_start_temperature_c": 10,
            "maximum_start_temperature_c": 40,
            "maximum_post_refresh_temperature_c": 45,
        },
        "usage": usage,
        "validity": {
            "valid_from": "2026-08-08T00:00:00Z",
            "expires_at": expires_at,
        },
        "review": {
            "approved": True,
            "reviewer_id": "n2p-test-reviewer",
            "reviewed_at": "2026-08-07T23:00:00Z",
            "review_artifact_sha256": "4" * 64,
        },
    }


def _camera_none() -> dict[str, object]:
    return {
        "capture_performed": False,
        "file": None,
        "sha256": None,
        "camera_id": None,
        "tripod_position_id": None,
        "lighting_setup_id": None,
        "exposure_mode": None,
        "white_balance_mode": None,
        "focus_mode": None,
        "image_processing": None,
        "full_panel_uncropped": None,
    }


def _electrical_pass() -> dict[str, bool]:
    return {
        "supply_3v3_normal": True,
        "cv_mode_normal": True,
        "current_normal": True,
        "temperature_normal": True,
        "no_odor_sound_hotspot_damage_or_voltage_droop": True,
        "esp32_did_not_restart_during_action": True,
        "physical_cutoff_available": True,
        "visual_quality_scored_independently_from_electrical": True,
    }


def _observation(snapshot, *, target: bool, camera=None) -> dict[str, object]:
    visual: dict[str, object]
    if target:
        visual = {
            "detail": 4,
            "tone": 4,
            "gradients": 4,
            "texture": 4,
            "artifacts": 4,
            "source_fidelity": 4,
            "screen_geometry_matches_reference": True,
            "no_retained_old_regions": True,
        }
    else:
        visual = {
            "screen_matches_reference": True,
            "orientation_correct": True,
            "labels_legible": True,
            "center_seam_correct": True,
            "all_six_colors_present": True,
            "no_retained_old_regions": True,
        }
    return {
        "schema_version": 1,
        "kind": runner.OBSERVATION_KIND,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": TARGET_OBSERVED_AT if target else PRIMER_OBSERVED_AT,
        "observer_id": "operator-test",
        "full_panel_inspected": True,
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "viewing_distance_cm": 60,
        "stable_lighting": True,
        "visual": visual,
        "electrical": _electrical_pass(),
        "post_refresh_temperature_c": 26.0,
        "camera": camera if camera is not None else _camera_none(),
    }


class N2PFixedActionRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = compiler.compile_campaign_manifest()

    def setUp(self) -> None:
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        self.temporary = tempfile.TemporaryDirectory(dir=hardware)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "claims"
        self.compile_patch = mock.patch.object(
            runner, "compile_campaign_manifest", return_value=self.manifest
        )
        self.registry_patch = mock.patch.object(
            runner, "DEFAULT_CLAIM_REGISTRY", self.registry
        )
        self.time_patch = mock.patch.object(
            runner, "_utc_now", return_value="2026-08-08T00:00:30Z"
        )
        self.compile_patch.start()
        self.registry_patch.start()
        self.time_patch.start()
        self.addCleanup(self.compile_patch.stop)
        self.addCleanup(self.registry_patch.stop)
        self.addCleanup(self.time_patch.stop)

    def _write_json(self, path: Path, value) -> Path:
        path.write_bytes(canonical_json_bytes(value))
        return path

    def _profile(self, name: str, *, prior: bool, **kwargs) -> Path:
        profile = seal_limit_profile(
            _profile_payload(
                self.manifest["p0_campaign_contract"],
                prior_completed=prior,
                **kwargs,
            )
        )
        return self._write_json(self.root / name, profile)

    def _run_map(self, action_key: str, result_name: str):
        profile = self._profile(f"{result_name}-profile.json", prior=False)
        destination = self.root / result_name
        scripted = ScriptedRequester(map_responses())
        claim_file = self.registry / (
            runner.FIXED_ACTION_SHA256S[action_key] + ".json"
        )

        def claim_before_network(*args, **kwargs):
            self.assertTrue(claim_file.is_file())
            return scripted(*args, **kwargs)

        with (
            mock.patch.object(runner, "_require_physical_panel_binding"),
            mock.patch.object(runner, "http_request", side_effect=claim_before_network),
        ):
            evidence = runner.run_n2p_fixed_action_once(
                action_key,
                destination,
                "http://device",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                authorization_confirmation=runner.required_authorization_confirmation(
                    action_key
                ),
                start_temperature_c=25,
                confirm_reviewed_panel_and_build=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(evidence["request_audit"]["post_issued_count"], 1)
        snapshot = runner._load_action_snapshot(action_key)
        observation_path = self._write_json(
            self.root / f"{result_name}-observation.json",
            _observation(snapshot, target=False),
        )
        finalized = runner.finalize_n2p_observation(destination, observation_path)
        self.assertEqual(finalized["state"], "PASS")
        return destination

    def _run_target(self, action_key: str, primer_dir: Path, result_name: str):
        profile = self._profile(f"{result_name}-profile.json", prior=True)
        destination = self.root / result_name
        snapshot = runner._load_action_snapshot(action_key)
        contract = runner._target_contract(snapshot)
        responses = target_responses(snapshot.frame, contract)
        primer_evidence = json.loads(
            (primer_dir / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        completed = primer_evidence["protocol_evidence"]["completed_map_evidence"]
        responses["/api/job"][0] = (200, json.dumps(completed["job_raw"]))
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(completed["diagnostic_raw"]),
        )
        scripted = ScriptedRequester(responses)
        with (
            mock.patch.object(runner, "_require_physical_panel_binding"),
            mock.patch.object(runner, "http_request", scripted),
        ):
            evidence = runner.run_n2p_fixed_action_once(
                action_key,
                destination,
                "http://device",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                primer_result_file=primer_dir / runner.P0_RESULT_FILENAME,
                authorization_confirmation=runner.required_authorization_confirmation(
                    action_key
                ),
                start_temperature_c=25,
                confirm_reviewed_panel_and_build=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_map_fidelity_from_primer=True,
                confirm_esp32_not_restarted_since_primer=True,
                sleeper=lambda _seconds: None,
                clock=TargetTickClock(),
            )
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(evidence["request_audit"]["post_issued_count"], 1)
        observation_path = self._write_json(
            self.root / f"{result_name}-observation.json",
            _observation(snapshot, target=True),
        )
        finalized = runner.finalize_n2p_observation(destination, observation_path)
        self.assertEqual(finalized["state"], "PASS")
        return destination

    def test_cli_only_enumerates_eight_actions_and_has_no_overrides(self) -> None:
        action = inspect.signature(runner.run_n2p_fixed_action_once).parameters
        for forbidden in (
            "candidate_dir",
            "frame",
            "frame_sha256",
            "manifest_sha256",
            "expected_target_job_id",
            "expected_prior_job_id",
        ):
            self.assertNotIn(forbidden, action)
        parser_source = inspect.getsource(runner.parse_args)
        for forbidden_flag in (
            "--candidate-dir",
            "--frame",
            "--frame-sha256",
            "--manifest-sha256",
            "--expected-target-job-id",
        ):
            self.assertNotIn(forbidden_flag, parser_source)
        for key in runner.FIXED_ACTION_KEYS:
            parsed = runner.parse_args(["--action", key, "--describe-only"])
            self.assertEqual(parsed.action, key)
        with self.assertRaises(SystemExit):
            runner.parse_args(["--action", "q5-target", "--describe-only"])

    def test_describe_missing_profile_is_fail_closed_and_zero_claim_network(self) -> None:
        with mock.patch.object(
            runner, "http_request", side_effect=AssertionError("network")
        ):
            result = runner.describe_n2p_fixed_action("q1-map-primer")
        self.assertFalse(result["contract_ready"])
        self.assertFalse(result["hardware_ready"])
        self.assertFalse(result["claim_created"])
        self.assertIn("reviewed_limit_profile_missing", result["blockers"])
        self.assertFalse(self.registry.exists())

    def test_legacy_unbound_live_is_hard_blocked_before_claim_and_network(self) -> None:
        destination = self.root / "must-not-exist"
        with (
            mock.patch.object(
                runner, "http_request", side_effect=AssertionError("network")
            ),
            self.assertRaisesRegex(
                runner.N2PFixedActionError,
                "legacy N2P live execution is disabled.*UNBOUND",
            ),
        ):
            runner.run_n2p_fixed_action_once(
                "q1-map-primer",
                destination,
                "http://device",
                limit_profile_file=self.root / "not-read.json",
                evaluated_at=EVALUATED_AT,
                authorization_confirmation="not-evaluated",
                start_temperature_c=25,
            )
        self.assertFalse(destination.exists())
        self.assertFalse(self.registry.exists())

    def test_all_eight_actions_each_issue_at_most_one_post(self) -> None:
        for cell in range(1, 5):
            with self.subTest(cell=cell, phase="map-primer"):
                primer = self._run_map(
                    f"q{cell}-map-primer", f"q{cell}-primer-result"
                )
            with self.subTest(cell=cell, phase="target"):
                self._run_target(
                    f"q{cell}-target", primer, f"q{cell}-target-result"
                )

    def test_post_then_failure_records_one_post_unknown_and_replay_has_zero_network(self) -> None:
        profile = self._profile("unknown-profile.json", prior=False)
        responses = map_responses()
        responses["/api/job"][1] = RuntimeError("connection lost after POST")
        scripted = ScriptedRequester(responses)
        destination = self.root / "unknown-result"
        with (
            mock.patch.object(runner, "_require_physical_panel_binding"),
            mock.patch.object(runner, "http_request", scripted),
            self.assertRaises(runner.N2PFixedActionUnknown),
        ):
            runner.run_n2p_fixed_action_once(
                "q1-map-primer",
                destination,
                "http://device",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                authorization_confirmation=runner.required_authorization_confirmation(
                    "q1-map-primer"
                ),
                start_temperature_c=25,
                confirm_reviewed_panel_and_build=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        result = json.loads(
            (destination / runner.P0_RESULT_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(result["state"], "UNKNOWN_DO_NOT_RETRY")
        self.assertEqual(result["post_request_count"], 1)

        second = ScriptedRequester(map_responses())
        with (
            mock.patch.object(runner, "_require_physical_panel_binding"),
            mock.patch.object(runner, "http_request", second),
            self.assertRaises(runner.N2PFixedActionUnknown),
        ):
            runner.run_n2p_fixed_action_once(
                "q1-map-primer",
                self.root / "replay-result",
                "http://device",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                authorization_confirmation=runner.required_authorization_confirmation(
                    "q1-map-primer"
                ),
                start_temperature_c=25,
                confirm_reviewed_panel_and_build=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
            )
        self.assertEqual(second.calls, [])

    def test_expired_and_exhausted_profiles_block_before_claim_and_network(self) -> None:
        expired = self._profile(
            "expired.json", prior=False, expires_at="2026-08-08T00:01:00Z"
        )
        exhausted = self._profile(
            "exhausted.json",
            prior=True,
            usage_override={
                "cumulative_visible_refresh_count": 8,
                "session_visible_refresh_count": 2,
                "consecutive_visible_refresh_count": 2,
            },
        )
        with mock.patch.object(
            runner, "http_request", side_effect=AssertionError("network")
        ):
            expired_result = runner.describe_n2p_fixed_action(
                "q1-map-primer",
                limit_profile_file=expired,
                evaluated_at=EVALUATED_AT,
            )
            exhausted_result = runner.describe_n2p_fixed_action(
                "q1-map-primer",
                limit_profile_file=exhausted,
                evaluated_at=EVALUATED_AT,
            )
        self.assertIn("profile_expired", expired_result["blockers"])
        self.assertIn(
            "campaign_visible_refresh_limit_exhausted",
            exhausted_result["blockers"],
        )
        self.assertFalse(self.registry.exists())

    def test_cross_cell_and_tampered_primer_fail_closed(self) -> None:
        primer = self._run_map("q1-map-primer", "cross-primer")
        profile = self._profile("cross-target-profile.json", prior=True)
        with self.assertRaisesRegex(runner.N2PFixedActionError, "cross-cell"):
            runner.describe_n2p_fixed_action(
                "q2-target",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                primer_result_file=primer / runner.P0_RESULT_FILENAME,
            )
        original = json.loads(
            (primer / runner.P0_RESULT_FILENAME).read_text(encoding="utf-8")
        )
        tampered = copy.deepcopy(original)
        tampered["details"] = "tampered"
        tampered_file = self._write_json(self.root / "tampered-result.json", tampered)
        for sibling in (
            runner.EVIDENCE_FILENAME,
            runner.OBSERVATION_FILENAME,
            runner.FINALIZATION_FILENAME,
        ):
            (self.root / sibling).write_bytes((primer / sibling).read_bytes())
        with self.assertRaisesRegex(runner.N2PFixedActionError, "invalid"):
            runner.describe_n2p_fixed_action(
                "q1-target",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                primer_result_file=tampered_file,
            )

    def test_reparse_profile_is_rejected_before_read(self) -> None:
        profile = self._profile("reparse-profile.json", prior=False)
        real_lstat = os.lstat

        def marked_reparse(path):
            status = real_lstat(path)
            if Path(path).absolute() == profile.absolute():
                return SimpleNamespace(
                    st_mode=status.st_mode,
                    st_file_attributes=0x0400,
                )
            return status

        with mock.patch.object(runner.os, "lstat", side_effect=marked_reparse):
            with self.assertRaisesRegex(
                runner.N2PFixedActionError, "symlink or reparse point"
            ):
                runner.describe_n2p_fixed_action(
                    "q1-map-primer",
                    limit_profile_file=profile,
                    evaluated_at=EVALUATED_AT,
                )

    def test_camera_bytes_are_verified_and_copied(self) -> None:
        profile = self._profile("camera-profile.json", prior=False)
        destination = self.root / "camera-result"
        scripted = ScriptedRequester(map_responses())
        with (
            mock.patch.object(runner, "_require_physical_panel_binding"),
            mock.patch.object(runner, "http_request", scripted),
        ):
            runner.run_n2p_fixed_action_once(
                "q2-map-primer",
                destination,
                "http://device",
                limit_profile_file=profile,
                evaluated_at=EVALUATED_AT,
                authorization_confirmation=runner.required_authorization_confirmation(
                    "q2-map-primer"
                ),
                start_temperature_c=25,
                confirm_reviewed_panel_and_build=True,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        snapshot = runner._load_action_snapshot("q2-map-primer")
        image = Image.new("RGB", (8, 8), (100, 80, 60))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        photo = buffer.getvalue()
        photo_path = self.root / "capture.png"
        photo_path.write_bytes(photo)
        camera = {
            "capture_performed": True,
            "file": photo_path.name,
            "sha256": hashlib.sha256(photo).hexdigest(),
            "camera_id": "fixed-test-camera",
            "tripod_position_id": "n2p-fixed-position-v1",
            "lighting_setup_id": "n2p-fixed-lighting-v1",
            "exposure_mode": "manual-locked",
            "white_balance_mode": "manual-locked",
            "focus_mode": "manual-locked",
            "image_processing": "disabled-or-fixed",
            "full_panel_uncropped": True,
        }
        observation = self._write_json(
            self.root / "camera-observation.json",
            _observation(snapshot, target=False, camera=camera),
        )
        finalized = runner.finalize_n2p_observation(destination, observation)
        self.assertEqual(finalized["state"], "PASS")
        self.assertEqual(
            (destination / runner.CAMERA_CAPTURE_FILENAME).read_bytes(), photo
        )

    def test_observation_timestamp_is_timezone_aware_after_protocol_and_sane(self) -> None:
        snapshot = runner._load_action_snapshot("q1-map-primer")
        profile_path = self._profile("timestamp-profile.json", prior=False)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        minimum = datetime(2026, 8, 8, 0, 0, 30, tzinfo=timezone.utc)
        observation = _observation(snapshot, target=False)
        observation["observed_at"] = "2026-08-08T00:01:00"
        with self.assertRaisesRegex(runner.N2PFixedActionError, "RFC3339"):
            runner._validate_observation(
                observation,
                snapshot,
                profile,
                camera_base_directory=self.root,
                minimum_observed_at=minimum,
            )
        observation["observed_at"] = "2026-08-08T00:00:29Z"
        with self.assertRaisesRegex(runner.N2PFixedActionError, "predates"):
            runner._validate_observation(
                observation,
                snapshot,
                profile,
                camera_base_directory=self.root,
                minimum_observed_at=minimum,
            )
        observation["observed_at"] = "2026-08-08T00:20:00Z"
        with self.assertRaisesRegex(runner.N2PFixedActionError, "future"):
            runner._validate_observation(
                observation,
                snapshot,
                profile,
                camera_base_directory=self.root,
                minimum_observed_at=minimum,
            )

    def test_camera_reparse_and_wrong_byte_hash_fail_closed(self) -> None:
        snapshot = runner._load_action_snapshot("q1-map-primer")
        profile_path = self._profile("camera-guard-profile.json", prior=False)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        image = Image.new("RGB", (4, 4), (1, 2, 3))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        capture = self.root / "guard-capture.png"
        capture.write_bytes(buffer.getvalue())
        camera = {
            "capture_performed": True,
            "file": capture.name,
            "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
            "camera_id": "fixed-test-camera",
            "tripod_position_id": "n2p-fixed-position-v1",
            "lighting_setup_id": "n2p-fixed-lighting-v1",
            "exposure_mode": "manual-locked",
            "white_balance_mode": "manual-locked",
            "focus_mode": "manual-locked",
            "image_processing": "disabled-or-fixed",
            "full_panel_uncropped": True,
        }
        observation = _observation(snapshot, target=False, camera=camera)
        minimum = datetime(2026, 8, 8, 0, 0, 30, tzinfo=timezone.utc)
        wrong = copy.deepcopy(observation)
        wrong["camera"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(runner.N2PFixedActionError, "bytes"):
            runner._validate_observation(
                wrong,
                snapshot,
                profile,
                camera_base_directory=self.root,
                minimum_observed_at=minimum,
            )

        real_lstat = os.lstat

        def marked_reparse(path):
            status = real_lstat(path)
            if Path(path).absolute() == capture.absolute():
                return SimpleNamespace(
                    st_mode=status.st_mode,
                    st_file_attributes=0x0400,
                )
            return status

        with mock.patch.object(runner.os, "lstat", side_effect=marked_reparse):
            with self.assertRaisesRegex(
                runner.N2PFixedActionError, "symlink or reparse point"
            ):
                runner._validate_observation(
                    observation,
                    snapshot,
                    profile,
                    camera_base_directory=self.root,
                    minimum_observed_at=minimum,
                )

    def test_visual_scores_and_electrical_verdict_remain_separate(self) -> None:
        snapshot = runner._load_action_snapshot("q1-target")
        profile_path = self._profile("separation-profile.json", prior=True)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        observation = _observation(snapshot, target=True)
        observation["electrical"]["current_normal"] = False
        outcome = runner._validate_observation(
            observation,
            snapshot,
            profile,
            camera_base_directory=self.root,
            minimum_observed_at=datetime(
                2026, 8, 8, 0, 0, 30, tzinfo=timezone.utc
            ),
        )
        self.assertTrue(outcome[0])
        self.assertFalse(outcome[1])

    def test_execution_supplement_tamper_fails_closed(self) -> None:
        supplement = json.loads(
            runner.EXECUTION_SUPPLEMENT_FILE.read_text(encoding="utf-8")
        )
        supplement["fixed_actions"]["q1-map-primer"] = "0" * 64
        tampered = self._write_json(self.root / "tampered-supplement.json", supplement)
        with mock.patch.object(runner, "EXECUTION_SUPPLEMENT_FILE", tampered):
            with self.assertRaisesRegex(
                runner.N2PFixedActionError, "supplement file identity"
            ):
                runner.describe_n2p_fixed_action("q1-map-primer")


if __name__ == "__main__":
    unittest.main()
