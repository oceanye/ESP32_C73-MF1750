from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
from io import BytesIO
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

from host.visible_refresh_campaign import canonical_json_bytes
from host.visible_refresh_campaign.production_profile import ProductionProfileError
from tests.n2_physical_once_fixture import (
    MAP_EVALUATED_AT,
    PhysicalOnceFixture,
    observation,
)
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import _responses as map_responses
from tools.mf1750_frame_tool import FrameToolNetworkError
from tools import g1_s1_n2_physical_campaign as physical
from tools import g1_s1_rc2g_n2_photo_campaign as frozen
from tools import g1_s1_rc2g_n2_photo_campaign_once as legacy
from tools import g1_s1_rc2g_n2_physical_once as runner


class N2PhysicalOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_manifest = frozen.compile_campaign_manifest()

    def setUp(self) -> None:
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        self.temporary = tempfile.TemporaryDirectory(dir=hardware)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.compile_patch = mock.patch.object(
            physical.frozen,
            "compile_campaign_manifest",
            side_effect=lambda: deepcopy(self.frozen_manifest),
        )
        self.compile_patch.start()
        self.addCleanup(self.compile_patch.stop)
        self.fixture = PhysicalOnceFixture(self.root, self.frozen_manifest)
        self.registry_patch = mock.patch.object(
            runner, "DEFAULT_CLAIM_REGISTRY", self.fixture.registry
        )
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def _run_kwargs(
        self,
        action_key: str,
        *,
        evaluated_at: str | None = None,
        primer_result_dir: Path | None = None,
        fixture: PhysicalOnceFixture | None = None,
    ) -> tuple[runner._Context, dict[str, object]]:
        selected_fixture = self.fixture if fixture is None else fixture
        action = selected_fixture.action(action_key)
        phase = str(action["identity"]["phase"])
        production = selected_fixture.production_inputs(phase)
        if evaluated_at is not None:
            production["evaluated_at"] = evaluated_at
        context = runner._load_live_context(action_key, **production)
        binding_sha = context.operator["physical_binding"]["integrity"][
            "canonical_sha256"
        ]
        kwargs: dict[str, object] = {
            **production,
            "authorization_confirmation": runner.required_action_authorization(
                context.action["action_identity_sha256"]
            ),
            "panel_build_confirmation": runner.required_panel_build_confirmation(
                str(context.campaign["panel"]["serial"]),
                str(context.campaign["firmware"]["build_tag"]),
                str(binding_sha),
            ),
            "profile_confirmation": runner._profile_confirmation(context),
            "start_temperature_c": 25,
            "primer_result_dir": primer_result_dir,
            "confirm_supervised_supply_cv_current_normal": True,
            "confirm_physical_cutoff_available": True,
            "confirm_single_visible_refresh": True,
            "confirm_controller_fresh_boot": phase == "map-primer",
            "confirm_map_fidelity_from_primer": phase == "target",
            "confirm_esp32_not_restarted_since_primer": phase == "target",
            "confirm_no_j2_disconnect_since_primer": phase == "target",
            "confirm_no_panel_power_cycle_since_primer": phase == "target",
            "confirm_no_other_visible_refresh_since_primer": phase == "target",
            "sleeper": lambda _seconds: None,
        }
        return context, kwargs

    def _assert_preclaim_rejected(
        self,
        action_key: str,
        destination: Path,
        kwargs: dict[str, object],
        *,
        now: str,
        expected: str,
    ) -> None:
        scripted = ScriptedRequester(map_responses())
        with (
            mock.patch.object(runner, "_utc_now", return_value=now),
            mock.patch.object(legacy, "http_request", scripted),
            self.assertRaisesRegex(runner.N2PhysicalOnceError, expected),
        ):
            runner.run_physical_action_once(
                action_key,
                destination,
                "http://device",
                **kwargs,
            )
        self.assertEqual(scripted.calls, [])
        self.assertFalse(destination.exists())
        self.assertFalse(self.fixture.registry.exists())

    def _validate(self, directory: Path) -> dict[str, object]:
        return runner.validate_physical_result(
            directory,
            reviewer_key_file=self.fixture.reviewer_key_file,
            require_finalized=True,
        )

    def _validate_with_fixture(
        self, directory: Path, fixture: PhysicalOnceFixture
    ) -> dict[str, object]:
        with mock.patch.object(
            runner, "DEFAULT_CLAIM_REGISTRY", fixture.registry
        ):
            return runner.validate_physical_result(
                directory,
                reviewer_key_file=fixture.reviewer_key_file,
                require_finalized=True,
            )

    def test_describe_uses_dynamic_identities_and_cli_has_no_overrides(self) -> None:
        production = self.fixture.production_inputs("map-primer")
        result = runner.describe_physical_action(
            "q1-map-primer",
            **production,
        )
        self.assertTrue(result["production_ready"])
        self.assertTrue(result["p0_contract_ready"])
        self.assertNotIn(
            result["action_identity_sha256"],
            legacy.FIXED_ACTION_SHA256S.values(),
        )
        self.assertEqual(
            len(result["required_profile_confirmation_sha256"]), 64
        )
        self.assertFalse(result["claim_created"])
        self.assertFalse(self.fixture.registry.exists())

        signature = inspect.signature(runner.run_physical_action_once).parameters
        self.assertIn("profile_confirmation", signature)
        for required in (
            "confirm_no_j2_disconnect_since_primer",
            "confirm_no_panel_power_cycle_since_primer",
            "confirm_no_other_visible_refresh_since_primer",
        ):
            self.assertIn(required, signature)
        source = inspect.getsource(runner.parse_args)
        for forbidden in (
            "--frame",
            "--frame-sha256",
            "--job-id",
            "--candidate-dir",
            "--action-sha256",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("--confirm-profile", source)

    def test_map_claim_precedes_network_one_post_replay_and_deep_finalize(self) -> None:
        directory, scripted = self.fixture.run_and_finalize(
            "q1-map-primer", "q1-map-result"
        )
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        validation = self._validate(directory)
        self.assertTrue(validation["valid"])
        self.assertTrue(validation["finalized"])
        self.assertEqual(validation["state"], "PASS")
        expected_snapshots = {
            runner.COPIED_OPERATOR_FILENAME,
            runner.COPIED_CAMPAIGN_FILENAME,
            runner.COPIED_SOURCE_MANIFEST_FILENAME,
            runner.COPIED_PANEL_FILENAME,
            runner.COPIED_BINDING_REVIEW_FILENAME,
            runner.COPIED_PROFILE_FILENAME,
            runner.COPIED_FIRMWARE_FILENAME,
            runner.COPIED_SUPPLIER_FILENAME,
            runner.COPIED_USAGE_FILENAME,
            runner.COPIED_PROFILE_REVIEW_FILENAME,
        }
        self.assertTrue(expected_snapshots.issubset(path.name for path in directory.iterdir()))
        self.assertFalse((directory / self.fixture.reviewer_key_file.name).exists())
        evidence = json.loads(
            (directory / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["request_audit"]["post_attempt_count"], 1)
        self.assertEqual(evidence["request_audit"]["post_issued_count"], 1)
        self.assertEqual(
            evidence["maximum_live_evaluation_age_seconds"],
            runner.MAX_LIVE_EVALUATED_AT_AGE_SECONDS,
        )

        _context, kwargs = self._run_kwargs("q1-map-primer")
        replay = ScriptedRequester(map_responses())
        with (
            mock.patch.object(runner, "_utc_now", return_value=MAP_EVALUATED_AT),
            mock.patch.object(legacy, "http_request", replay),
            self.assertRaises(runner.N2PhysicalOnceUnknown),
        ):
            runner.run_physical_action_once(
                "q1-map-primer",
                self.root / "q1-map-replay",
                "http://device",
                **kwargs,
            )
        self.assertEqual(replay.calls, [])

    def test_map_get_poll_timeout_is_replayable_and_deep_finalizes(self) -> None:
        context, kwargs = self._run_kwargs("q1-map-primer")
        scripted = ScriptedRequester(map_responses())
        job_get_count = 0

        def flaky_job_poll(
            base_url: str,
            endpoint: str,
            *,
            method: str,
            data: bytes | None,
            timeout: float,
        ) -> tuple[int, str]:
            nonlocal job_get_count
            if method == "GET" and endpoint == "/api/job":
                job_get_count += 1
                if job_get_count == 2:
                    raise FrameToolNetworkError("GET /api/job failed: timed out")
            return scripted(
                base_url,
                endpoint,
                method=method,
                data=data,
                timeout=timeout,
            )

        directory = self.root / "q1-map-poll-timeout"
        with (
            mock.patch.object(runner, "_utc_now", return_value=MAP_EVALUATED_AT),
            mock.patch.object(legacy, "http_request", side_effect=flaky_job_poll),
        ):
            runner.run_physical_action_once(
                "q1-map-primer",
                directory,
                "http://device",
                **kwargs,
            )
        evidence = json.loads(
            (directory / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        exceptions = [
            call
            for call in evidence["request_audit"]["calls"]
            if call["outcome"] == "exception"
        ]
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["endpoint"], "/api/job")
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)

        observation_file = self.fixture.write_json(
            "q1-map-poll-timeout-observation.json",
            observation(context.legacy_snapshot, target=False),
        )
        with mock.patch.object(
            legacy, "_utc_now", return_value="2026-08-08T00:05:00Z"
        ):
            finalized = runner.finalize_physical_observation(
                directory,
                observation_file,
                reviewer_key_file=self.fixture.reviewer_key_file,
            )
        self.assertEqual(finalized["state"], "PASS")
        self.assertEqual(self._validate(directory)["state"], "PASS")

        audit = deepcopy(evidence["request_audit"])
        exception_index = next(
            index
            for index, call in enumerate(audit["calls"])
            if call["outcome"] == "exception"
        )
        invalid_variants = []
        wrong_endpoint = deepcopy(audit)
        wrong_endpoint["calls"][exception_index]["endpoint"] = "/api/version"
        invalid_variants.append(wrong_endpoint)
        wrong_type = deepcopy(audit)
        wrong_type["calls"][exception_index]["error"]["type"] = "RuntimeError"
        invalid_variants.append(wrong_type)
        extra_field = deepcopy(audit)
        extra_field["calls"][exception_index]["status"] = 500
        invalid_variants.append(extra_field)
        post_exception = deepcopy(audit)
        post_exception["calls"][exception_index].update(
            {
                "method": "POST",
                "endpoint": "/api/frame",
                "request_bytes": 307200,
            }
        )
        invalid_variants.append(post_exception)
        for invalid in invalid_variants:
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                runner.N2PhysicalOnceError, "stored request audit exception changed"
            ):
                runner._validate_request_audit(
                    invalid,
                    frame_sha256=context.action["identity"]["frame"]["sha256"],
                )

    def test_target_requires_all_continuity_then_deep_validates(self) -> None:
        primer, _map_scripted = self.fixture.run_and_finalize(
            "q2-map-primer", "q2-map-result"
        )
        context, kwargs = self._run_kwargs(
            "q2-target", primer_result_dir=primer
        )
        kwargs["confirm_no_j2_disconnect_since_primer"] = False
        target_claim = self.fixture.registry / (
            f"{context.action['action_identity_sha256']}.json"
        )
        scripted = ScriptedRequester(map_responses())
        with (
            mock.patch.object(
                runner, "_utc_now", return_value=str(kwargs["evaluated_at"])
            ),
            mock.patch.object(legacy, "http_request", scripted),
            self.assertRaisesRegex(runner.N2PhysicalOnceError, "confirmations"),
        ):
            runner.run_physical_action_once(
                "q2-target",
                self.root / "q2-target-rejected",
                "http://device",
                **kwargs,
            )
        self.assertFalse(target_claim.exists())
        self.assertEqual(scripted.calls, [])

        target, target_scripted = self.fixture.run_and_finalize(
            "q2-target", "q2-target-result", primer_result_dir=primer
        )
        self.assertEqual(target_scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(self._validate(target)["state"], "PASS")
        evidence = json.loads(
            (target / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(evidence["confirmations"]),
            runner._expected_confirmation_keys("target"),
        )
        self.assertTrue(
            all(value is True for value in evidence["confirmations"].values())
        )

    def test_materialized_schedule_overrides_lower_authority_before_claim(self) -> None:
        lower_root = self.root / "lower-authority"
        lower_root.mkdir()
        lower = PhysicalOnceFixture(
            lower_root,
            self.frozen_manifest,
            authority_schedule_seconds=100,
            use_process_policy=True,
        )
        primer, _scripted = lower.run_and_finalize(
            "q2-map-primer", "q2-map-result"
        )
        too_early = "2026-08-08T00:02:40Z"
        context, kwargs = self._run_kwargs(
            "q2-target",
            evaluated_at=too_early,
            primer_result_dir=primer,
            fixture=lower,
        )
        with mock.patch.object(
            runner, "DEFAULT_CLAIM_REGISTRY", lower.registry
        ):
            description = runner.describe_physical_action(
                "q2-target",
                primer_result_dir=primer,
                **{
                    **lower.production_inputs("target"),
                    "evaluated_at": too_early,
                },
            )
        schedule = description["runtime_schedule_decision"]
        self.assertFalse(description["p0_contract_ready"])
        self.assertEqual(schedule["action_identity_minimum_interval_seconds"], 150)
        self.assertEqual(schedule["limit_authority_minimum_interval_seconds"], 100)
        self.assertEqual(schedule["effective_minimum_interval_seconds"], 150)
        self.assertEqual(schedule["elapsed_since_last_visible_refresh_seconds"], 100)
        self.assertEqual(
            schedule["blockers"], ["materialized_action_interval_not_elapsed"]
        )

        destination = lower_root / "too-early-target"
        target_claim = lower.registry / (
            f"{context.action['action_identity_sha256']}.json"
        )
        network = ScriptedRequester(map_responses())
        with (
            mock.patch.object(runner, "DEFAULT_CLAIM_REGISTRY", lower.registry),
            mock.patch.object(runner, "_utc_now", return_value=too_early),
            mock.patch.object(legacy, "http_request", network),
            self.assertRaisesRegex(
                runner.N2PhysicalOnceError,
                "materialized_action_interval_not_elapsed",
            ),
        ):
            runner.run_physical_action_once(
                "q2-target",
                destination,
                "http://device",
                **kwargs,
            )
        self.assertFalse(destination.exists())
        self.assertFalse(target_claim.exists())
        self.assertEqual(network.calls, [])

        target, target_network = lower.run_and_finalize(
            "q2-target",
            "q2-target-boundary",
            primer_result_dir=primer,
            evaluated_at="2026-08-08T00:03:30Z",
        )
        self.assertEqual(target_network.calls.count(("POST", "/api/frame")), 1)
        evidence = json.loads(
            (target / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        boundary = evidence["runtime_schedule_decision"]
        self.assertTrue(boundary["ready"])
        self.assertEqual(boundary["effective_minimum_interval_seconds"], 150)
        self.assertEqual(
            boundary["elapsed_since_last_visible_refresh_seconds"], 150
        )
        self.assertTrue(self._validate_with_fixture(target, lower)["valid"])

        map_context = lower.context("q3-map-primer")
        map_profile = deepcopy(map_context.production.profile)
        map_profile["usage"].update(
            {
                "cumulative_visible_refresh_count": 2,
                "session_visible_refresh_count": 0,
                "consecutive_visible_refresh_count": 0,
                "last_visible_refresh_completed_at": "2026-08-08T00:01:00Z",
                "snapshot_at": "2026-08-08T00:02:00Z",
            }
        )
        map_context = replace(
            map_context,
            production=replace(map_context.production, profile=map_profile),
        )
        cooldown_early = runner._runtime_schedule_decision(
            map_context, evaluated_at=too_early
        )
        self.assertFalse(cooldown_early["ready"])
        self.assertEqual(cooldown_early["effective_minimum_cooldown_seconds"], 150)
        self.assertEqual(
            cooldown_early["blockers"],
            ["materialized_session_cooldown_not_elapsed"],
        )
        self.assertTrue(
            runner._runtime_schedule_decision(
                map_context, evaluated_at="2026-08-08T00:03:30Z"
            )["ready"]
        )

    def test_exact_tokens_and_live_time_fail_before_claim_or_network(self) -> None:
        _context, wrong_profile = self._run_kwargs("q3-map-primer")
        wrong_profile["profile_confirmation"] = "wrong-profile-token"
        self._assert_preclaim_rejected(
            "q3-map-primer",
            self.root / "wrong-profile",
            wrong_profile,
            now=MAP_EVALUATED_AT,
            expected="production-profile confirmation",
        )

        _context, wrong_panel = self._run_kwargs("q3-map-primer")
        wrong_panel["panel_build_confirmation"] = "wrong-panel-token"
        self._assert_preclaim_rejected(
            "q3-map-primer",
            self.root / "wrong-panel",
            wrong_panel,
            now=MAP_EVALUATED_AT,
            expected="panel serial/build confirmation",
        )

        _context, backdated = self._run_kwargs(
            "q3-map-primer", evaluated_at="2026-08-08T00:00:10Z"
        )
        self._assert_preclaim_rejected(
            "q3-map-primer",
            self.root / "backdated-profile",
            backdated,
            now="2026-08-08T00:10:00Z",
            expected="too old",
        )

        _context, future = self._run_kwargs(
            "q3-map-primer", evaluated_at="2026-08-08T00:00:40Z"
        )
        self._assert_preclaim_rejected(
            "q3-map-primer",
            self.root / "future-profile",
            future,
            now="2026-08-08T00:00:30Z",
            expected="future",
        )

    def test_fake_partial_allowlist_and_toctou_fail_before_claim(self) -> None:
        context, kwargs = self._run_kwargs("q4-map-primer")
        partial_profile = deepcopy(context.production.profile)
        partial_profile["action_allowlist"] = partial_profile["action_allowlist"][:-1]
        fake = replace(context.production, profile=partial_profile)
        scripted = ScriptedRequester(map_responses())
        with (
            mock.patch.object(
                runner, "load_validated_production_profile", return_value=fake
            ),
            mock.patch.object(runner, "_utc_now", return_value=MAP_EVALUATED_AT),
            mock.patch.object(legacy, "http_request", scripted),
            self.assertRaisesRegex(runner.N2PhysicalOnceError, "exact physical campaign"),
        ):
            runner.run_physical_action_once(
                "q4-map-primer",
                self.root / "partial-profile",
                "http://device",
                **kwargs,
            )
        self.assertEqual(scripted.calls, [])
        self.assertFalse(self.fixture.registry.exists())

        with (
            mock.patch.object(
                runner,
                "load_validated_production_profile",
                side_effect=ProductionProfileError("profile changed while being read"),
            ),
            mock.patch.object(legacy, "http_request", scripted),
            self.assertRaisesRegex(runner.N2PhysicalOnceError, "changed while"),
        ):
            runner.run_physical_action_once(
                "q4-map-primer",
                self.root / "profile-toctou",
                "http://device",
                **kwargs,
            )
        self.assertEqual(scripted.calls, [])
        self.assertFalse(self.fixture.registry.exists())

    def test_deep_validator_rejects_protocol_lock_observation_and_profile_tamper(self) -> None:
        directory, _scripted = self.fixture.run_and_finalize(
            "q4-map-primer", "q4-tamper-result"
        )
        cases = (
            (
                runner.EVIDENCE_FILENAME,
                lambda value: value["protocol_evidence"]["completed_map_evidence"][
                    "job_raw"
                ].__setitem__("job_id", 2),
            ),
            (
                runner.LOCK_FILENAME,
                lambda value: value["claim"].__setitem__("file_sha256", "0" * 64),
            ),
            (
                runner.OBSERVATION_FILENAME,
                lambda value: value["visual"].__setitem__(
                    "screen_matches_reference", False
                ),
            ),
            (
                runner.COPIED_PROFILE_FILENAME,
                lambda value: value.__setitem__("profile_id", "tampered-profile"),
            ),
            (
                runner.FINALIZATION_FILENAME,
                lambda value: value.__setitem__("visual_pass", False),
            ),
            (
                runner.P0_RESULT_FILENAME,
                lambda value: (
                    value.__setitem__("state", "FAIL"),
                    value.__setitem__("evidence_manifest_sha256", "0" * 64),
                ),
            ),
        )
        for filename, mutate in cases:
            with self.subTest(filename=filename):
                path = directory / filename
                original = path.read_bytes()
                value = json.loads(original.decode("utf-8"))
                mutate(value)
                path.write_bytes(canonical_json_bytes(value))
                try:
                    with self.assertRaises(runner.N2PhysicalOnceError):
                        self._validate(directory)
                finally:
                    path.write_bytes(original)
                self.assertTrue(self._validate(directory)["valid"])

        review_path = directory / runner.COPIED_BINDING_REVIEW_FILENAME
        original_review = review_path.read_bytes()
        review_path.write_bytes(original_review + b"tamper")
        try:
            with self.assertRaises(runner.N2PhysicalOnceError):
                self._validate(directory)
        finally:
            review_path.write_bytes(original_review)

        evidence = json.loads(
            (directory / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        claim_path = self.fixture.registry / evidence["claim"]["filename"]
        original_claim = claim_path.read_bytes()
        claim = json.loads(original_claim.decode("utf-8"))
        claim["maximum_post_requests"] = 2
        claim_path.write_bytes(canonical_json_bytes(claim))
        try:
            with self.assertRaises(runner.N2PhysicalOnceError):
                self._validate(directory)
        finally:
            claim_path.write_bytes(original_claim)

    def test_real_camera_capture_bytes_are_reverified_by_deep_validator(self) -> None:
        image = Image.new("RGB", (8, 8), (80, 100, 120))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        payload = buffer.getvalue()
        capture = self.root / "physical-camera-capture.png"
        capture.write_bytes(payload)
        camera = {
            "capture_performed": True,
            "file": capture.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "camera_id": "fixed-physical-test-camera",
            "tripod_position_id": "n2p-fixed-position-v1",
            "lighting_setup_id": "n2p-fixed-lighting-v1",
            "exposure_mode": "manual-locked",
            "white_balance_mode": "manual-locked",
            "focus_mode": "manual-locked",
            "image_processing": "disabled-or-fixed",
            "full_panel_uncropped": True,
        }
        directory, _scripted = self.fixture.run_and_finalize(
            "q3-map-primer",
            "q3-camera-result",
            camera=camera,
        )
        copied = directory / runner.CAMERA_CAPTURE_FILENAME
        self.assertEqual(copied.read_bytes(), payload)
        self.assertTrue(self._validate(directory)["valid"])
        copied.write_bytes(payload + b"tamper")
        with self.assertRaises(runner.N2PhysicalOnceError):
            self._validate(directory)


if __name__ == "__main__":
    unittest.main()
