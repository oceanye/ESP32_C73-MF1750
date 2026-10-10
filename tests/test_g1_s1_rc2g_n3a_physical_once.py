from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from host.visible_refresh_campaign import production_profile as production
from tests import n3_bundle_fixture as n3_fixture
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_n2_physical_analyzer import PhysicalAnalyzerFixture
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_n2_physical_campaign as n2_physical
from tools import g1_s1_n3a_physical_execution as physical
from tools import g1_s1_n3a_physical_analyzer as physical_analyzer
from tools import g1_s1_n3a_physical_plan as plan_builder
from tools import g1_s1_rc2g_n2_photo_campaign as n2_frozen
from tools import g1_s1_rc2g_n2_physical_analyzer as n2_analyzer
from tools import g1_s1_rc2g_n3_once as legacy
from tools import g1_s1_rc2g_n3a_physical_once as runner


SCHEDULE_SECONDS = 150
PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-N3A-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
N2_REVIEW_BYTES = b"N2 physical source binding for N3A integration\n"
N3A_REVIEW_BYTES = b"N3A selected winner repeat branch physical binding\n"


class N3APhysicalOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        cls.temporary = tempfile.TemporaryDirectory(dir=hardware)
        cls.root = Path(cls.temporary.name)
        source_n2 = n2_frozen.compile_campaign_manifest()
        cls.operator = n2_physical._assemble_manifest(
            source_n2,
            PANEL,
            n2_physical._review_artifact_record(N2_REVIEW_BYTES),
            n2_physical._operator_process_schedule(
                SCHEDULE_SECONDS, SCHEDULE_SECONDS
            ),
        )
        (cls.root / "n2").mkdir()
        cls.n2_fixture = PhysicalAnalyzerFixture(cls.root / "n2", cls.operator)
        cls.n2_validator_patcher = mock.patch.object(
            n2_analyzer.fixed,
            "validate_physical_result",
            side_effect=cls.n2_fixture.validation,
        )
        cls.n2_validator_patcher.start()
        cls.n2_analysis = n2_analyzer.analyze_n2p_physical_campaign(
            cls.n2_fixture.directories,
            reviewer_key_file=cls.n2_fixture.reviewer_key_file,
        )
        cls.plan = plan_builder.compile_n3a_physical_plan(
            cls.n2_analysis,
            cls.operator,
            n2_result_directories=cls.n2_fixture.directories,
            reviewer_key_file=cls.n2_fixture.reviewer_key_file,
            repeat_count=2,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
            binding_review_bytes=N3A_REVIEW_BYTES,
            measurement_assets=n3_fixture.registered_assets(),
        )
        cls.plan_file = cls._write_json("N3A-PHYSICAL.json", cls.plan)
        cls.review_file = cls.root / "n3a-binding-review.bin"
        cls.review_file.write_bytes(N3A_REVIEW_BYTES)
        cls.plan_files = runner.N3APhysicalPlanFiles(
            plan=cls.plan_file,
            binding_review_artifact=cls.review_file,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
            n2_result_directories=cls.n2_fixture.directories,
            n2_reviewer_key=cls.n2_fixture.reviewer_key_file,
        )
        cls.context = physical.load_n3a_physical_execution_context(
            plan_file=cls.plan_file,
            binding_review_artifact_file=cls.review_file,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
            n2_result_directories=cls.n2_fixture.directories,
            n2_reviewer_key_file=cls.n2_fixture.reviewer_key_file,
        )
        cls.routes = cls.plan["selected_routes"]
        cls.snapshots = {
            key: physical.load_n3a_physical_action_snapshot(cls.context, key)
            for route in cls.routes
            for key in (route["map_action_key"], route["target_action_key"])
        }
        cls.campaign_file = cls._write_json(
            "n3a-physical-campaign.json",
            cls.plan["physical_rebind"]["physical_campaign"],
        )
        cls.profile_reviewer_key = cls.root / "profile-reviewer.key"
        cls.profile_reviewer_key.write_bytes(bytes(reversed(range(32))))
        cls.productions = cls.production_set()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.n2_validator_patcher.stop()
        cls.temporary.cleanup()

    @classmethod
    def _write_json(cls, name: str, value) -> Path:
        path = cls.root / name
        path.write_bytes(canonical_json_bytes(value))
        return path

    @classmethod
    def _policy(
        cls,
        name: str,
        *,
        valid_from: str,
        expires_at: str,
        authority_schedule_seconds: int = SCHEDULE_SECONDS,
    ) -> dict:
        limits = {
            "maximum_campaign_visible_refreshes": 8,
            "maximum_session_visible_refreshes": 2,
            "maximum_consecutive_visible_refreshes": 2,
            "minimum_interval_seconds": authority_schedule_seconds,
            "minimum_cooldown_seconds": authority_schedule_seconds,
            "minimum_start_temperature_c": 0,
            "maximum_start_temperature_c": 50,
            "maximum_post_refresh_temperature_c": 50,
        }
        exact_temperature_fields = {
            "minimum_start_temperature_c",
            "maximum_start_temperature_c",
            "maximum_post_refresh_temperature_c",
        }
        return {
            "schema_version": 1,
            "kind": production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
            "not_a_supplier_rating": True,
            "supervised_only": True,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "issuer": "n3a-physical-test-process-owner",
            "policy_id": "n3a-repeatability-process-policy-v1",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": PANEL["model"],
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": limits,
            "validity": {"valid_from": valid_from, "expires_at": expires_at},
            "field_provenance": {
                field: {
                    "classification": (
                        production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                        if field in exact_temperature_fields
                        else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                    ),
                    "source_document_sha256": (
                        production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                    ),
                }
                for field in limits
            },
        }

    @classmethod
    def approve(
        cls,
        name: str,
        action_key: str,
        *,
        evaluated_at: str,
        reviewed_at: str,
        valid_from: str,
        expires_at: str,
        cumulative: int,
        session: int,
        consecutive: int,
        last_completed_at: str | None,
        snapshot_at: str,
        authority_schedule_seconds: int = SCHEDULE_SECONDS,
    ) -> tuple[runner.N3AProductionFiles, production.ValidatedProductionProfile]:
        policy_file = cls._write_json(
            f"{name}-limit-authority.json",
            cls._policy(
                name,
                valid_from=valid_from,
                expires_at=expires_at,
                authority_schedule_seconds=authority_schedule_seconds,
            ),
        )
        campaign = cls.plan["physical_rebind"]["physical_campaign"]
        usage_file = cls._write_json(
            f"{name}-usage.json",
            {
                "schema_version": 1,
                "kind": production.USAGE_EVIDENCE_KIND,
                "evidence_id": f"n3a-{name}-usage",
                "campaign_canonical_sha256": campaign["integrity"][
                    "canonical_sha256"
                ],
                "panel": campaign["panel"],
                "firmware": campaign["firmware"],
                "usage": {
                    "cumulative_visible_refresh_count": cumulative,
                    "session_visible_refresh_count": session,
                    "consecutive_visible_refresh_count": consecutive,
                    "last_visible_refresh_completed_at": last_completed_at,
                    "snapshot_at": snapshot_at,
                },
            },
        )
        draft = production.compile_production_draft_from_files(
            campaign_file=cls.campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
            profile_id="n3a-physical-repeatability-production-lineage",
            profile_version=f"1.0.{cumulative}",
        )
        draft_file = cls._write_json(f"{name}-draft.json", draft)
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=cls.campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
            reviewer_id="n3a-physical-test-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=cls.profile_reviewer_key,
        )
        review_file = cls.root / f"{name}-profile-review.json"
        profile_file = cls.root / f"{name}-profile.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        files = runner.N3AProductionFiles(
            profile=profile_file,
            physical_campaign=cls.campaign_file,
            firmware_binary=n2_frozen.FIRMWARE_BINARY,
            limit_authority=policy_file,
            usage_evidence=usage_file,
            review_artifact=review_file,
            reviewer_key=cls.profile_reviewer_key,
        )
        validated = physical.load_n3a_physical_production_profile(
            cls.context,
            action_key,
            profile_file=files.profile,
            campaign_file=files.physical_campaign,
            firmware_binary_file=files.firmware_binary,
            limit_authority_file=files.limit_authority,
            usage_evidence_file=files.usage_evidence,
            review_artifact_file=files.review_artifact,
            reviewer_key_file=files.reviewer_key,
            evaluated_at=evaluated_at,
        )
        return files, validated

    @classmethod
    def production_set(cls) -> list[tuple[runner.N3AProductionFiles, production.ValidatedProductionProfile]]:
        schedule = (
            ("s1-map", cls.routes[0]["map_action_key"], "2026-08-08T00:20:00Z", "2026-08-08T00:10:00Z", "2026-08-08T00:15:00Z", 0, 0, 0, None, "2026-08-08T00:00:00Z"),
            ("s1-target", cls.routes[0]["target_action_key"], "2026-08-08T00:23:30Z", "2026-08-08T00:22:45Z", "2026-08-08T00:23:00Z", 1, 1, 1, "2026-08-08T00:21:00Z", "2026-08-08T00:22:30Z"),
            ("s2-map", cls.routes[1]["map_action_key"], "2026-08-08T00:27:00Z", "2026-08-08T00:25:45Z", "2026-08-08T00:26:00Z", 2, 0, 0, "2026-08-08T00:24:00Z", "2026-08-08T00:25:30Z"),
            ("s2-target", cls.routes[1]["target_action_key"], "2026-08-08T00:30:00Z", "2026-08-08T00:28:45Z", "2026-08-08T00:29:00Z", 3, 1, 1, "2026-08-08T00:27:30Z", "2026-08-08T00:28:30Z"),
        )
        return [
            cls.approve(
                name,
                key,
                evaluated_at=evaluated,
                reviewed_at=reviewed,
                valid_from=valid_from,
                expires_at="2026-08-08T00:45:00Z",
                cumulative=cumulative,
                session=session,
                consecutive=consecutive,
                last_completed_at=last,
                snapshot_at=snapshot,
            )
            for (
                name,
                key,
                evaluated,
                reviewed,
                valid_from,
                cumulative,
                session,
                consecutive,
                last,
                snapshot,
            ) in schedule
        ]

    def _run_finalize(
        self,
        *,
        label: str,
        route_index: int,
        phase: str,
        files: runner.N3AProductionFiles,
        validated: production.ValidatedProductionProfile,
        registry: Path,
        live_at: str,
        observed_at: str,
        primer_result: Path | None = None,
        metric_offset: int = 0,
    ) -> tuple[Path, ScriptedRequester, dict, dict]:
        route = self.routes[route_index]
        action_key = route[f"{phase}_action_key"]
        snapshot = self.snapshots[action_key]
        destination = self.root / f"{label}-result"
        if phase == "map":
            scripted = ScriptedRequester(map_responses())
            clock = MapTickClock()
        else:
            self.assertIsNotNone(primer_result)
            with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
                prior = runner.load_n3a_physical_finalized_action_chain(
                    primer_result,
                    n2_result_directories=self.n2_fixture.directories,
                    n2_reviewer_key_file=self.n2_fixture.reviewer_key_file,
                    profile_reviewer_key_file=self.profile_reviewer_key,
                )
            contract = runner._target_contract(self.context, snapshot)
            responses = target_responses(snapshot.frame, contract)
            completed_map = prior.bundle["evidence"]["protocol_evidence"][
                "completed_map_evidence"
            ]
            responses["/api/job"][0] = (200, json.dumps(completed_map["job_raw"]))
            responses["/api/diagnostic/report"][0] = (
                200,
                json.dumps(completed_map["diagnostic_raw"]),
            )
            scripted = ScriptedRequester(responses)
            clock = TargetTickClock()
        kwargs = {
            "confirm_supervised_supply_cv_current_normal": True,
            "confirm_physical_cutoff_available": True,
            "confirm_single_visible_refresh": True,
            **(
                {"confirm_controller_fresh_boot": True}
                if phase == "map"
                else {
                    "confirm_map_fidelity_from_primer": True,
                    "confirm_esp32_not_restarted_since_primer": True,
                    "confirm_no_j2_disconnect_since_primer": True,
                    "confirm_no_panel_power_cycle_since_primer": True,
                    "confirm_no_other_visible_refresh_since_primer": True,
                }
            ),
        }
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", scripted),
            mock.patch.object(runner, "_utc_now", return_value=live_at),
        ):
            evidence = runner.run_n3a_physical_action_once(
                action_key,
                destination,
                "http://device",
                plan_files=self.plan_files,
                production_files=files,
                evaluated_at=validated.report["evaluated_at"],
                authorization_confirmation=runner.required_authorization_confirmation(
                    self.context, action_key
                ),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(
                    self.context, action_key
                ),
                profile_confirmation=runner.required_production_profile_confirmation(
                    validated
                ),
                start_temperature_c=25,
                primer_result_file=primer_result,
                sleeper=lambda _seconds: None,
                clock=clock,
                **kwargs,
            )
        observation = n3_fixture._operator_observation(
            snapshot,
            root=self.root,
            state=ResultState.PASS,
            metric_offset=metric_offset,
            overrides={"observed_at": observed_at},
        )
        observation_file = self._write_json(f"{label}-observation.json", observation)
        with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
            finalized = runner.finalize_n3a_physical_observation(
                destination,
                observation_file,
                n2_result_directories=self.n2_fixture.directories,
                n2_reviewer_key_file=self.n2_fixture.reviewer_key_file,
                profile_reviewer_key_file=self.profile_reviewer_key,
                primer_result_file=primer_result,
            )
        return destination, scripted, evidence, finalized

    def test_describe_and_map_target_deep_replay_single_post(self) -> None:
        production_set = self.productions
        map_files, map_profile = production_set[0]
        before = n2_analyzer.fixed.validate_physical_result.call_count
        description = runner.describe_n3a_physical_action(
            self.routes[0]["map_action_key"],
            plan_files=self.plan_files,
            production_files=map_files,
            evaluated_at=map_profile.report["evaluated_at"],
        )
        self.assertTrue(description["contract_ready"])
        self.assertTrue(description["n2_raw_evidence_replayed"])
        self.assertGreaterEqual(
            n2_analyzer.fixed.validate_physical_result.call_count - before, 8
        )
        registry = self.root / "full-chain-claims"
        map_dir, map_http, _map_evidence, map_final = self._run_finalize(
            label="full-s1-map",
            route_index=0,
            phase="map",
            files=map_files,
            validated=map_profile,
            registry=registry,
            live_at="2026-08-08T00:20:30Z",
            observed_at="2026-08-08T00:21:00Z",
        )
        target_files, target_profile = production_set[1]
        target_dir, target_http, target_evidence, target_final = self._run_finalize(
            label="full-s1-target",
            route_index=0,
            phase="target",
            files=target_files,
            validated=target_profile,
            registry=registry,
            live_at="2026-08-08T00:23:40Z",
            observed_at="2026-08-08T00:24:00Z",
            primer_result=map_dir / runner.P0_RESULT_FILENAME,
        )
        with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
            replay = runner.load_n3a_physical_finalized_action_bundle(
                target_dir / runner.P0_RESULT_FILENAME,
                n2_result_directories=self.n2_fixture.directories,
                n2_reviewer_key_file=self.n2_fixture.reviewer_key_file,
                profile_reviewer_key_file=self.profile_reviewer_key,
                primer_result_file=map_dir / runner.P0_RESULT_FILENAME,
            )
        self.assertEqual(map_http.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(target_http.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(map_final["state"], ResultState.PASS.value)
        self.assertEqual(target_final["state"], ResultState.PASS.value)
        self.assertEqual(replay["state"], ResultState.PASS.value)
        self.assertEqual(target_evidence["effective_minimum_interval_seconds"], 150)
        self.assertTrue((target_dir / runner.SESSION_OBSERVATION_FILENAME).is_file())
        self.assertTrue((target_dir / runner.CAMERA_CAPTURE_FILENAME).is_file())
        self.assertFalse((target_dir / "profile-reviewer.key").exists())
        for filename in (
            runner.PHYSICAL_PLAN_FILENAME,
            runner.BINDING_REVIEW_FILENAME,
            runner.PHYSICAL_CAMPAIGN_FILENAME,
            runner.FIRMWARE_BINARY_FILENAME,
            runner.LIMIT_AUTHORITY_FILENAME,
            runner.USAGE_EVIDENCE_FILENAME,
            runner.PROFILE_REVIEW_FILENAME,
            runner.PRODUCTION_VALIDATION_FILENAME,
        ):
            self.assertTrue((target_dir / filename).is_file())

    def test_claimed_copy_failure_is_durable_unknown_without_network(self) -> None:
        map_files, map_profile = self.productions[0]
        action_key = self.routes[0]["map_action_key"]
        destination = self.root / "claimed-copy-failure-result"
        registry = self.root / "claimed-copy-failure-claims"
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "_utc_now", return_value="2026-08-08T00:20:30Z"),
            mock.patch.object(runner, "_copy_inputs", side_effect=OSError("copy failed")),
            mock.patch.object(runner, "http_request", side_effect=AssertionError("network forbidden")),
            self.assertRaises(runner.N3APhysicalActionUnknown),
        ):
            runner.run_n3a_physical_action_once(
                action_key,
                destination,
                "http://device",
                plan_files=self.plan_files,
                production_files=map_files,
                evaluated_at=map_profile.report["evaluated_at"],
                authorization_confirmation=runner.required_authorization_confirmation(
                    self.context, action_key
                ),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(
                    self.context, action_key
                ),
                profile_confirmation=runner.required_production_profile_confirmation(
                    map_profile
                ),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
            )
        result = json.loads(
            (destination / runner.P0_RESULT_FILENAME).read_text(encoding="utf-8")
        )
        evidence = json.loads(
            (destination / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(result["state"], ResultState.UNKNOWN_DO_NOT_RETRY.value)
        self.assertEqual(result["post_request_count"], 0)
        self.assertEqual(evidence["request_audit"]["post_issued_count"], 0)
        self.assertEqual(len(list(registry.glob("*.json"))), 1)

    def test_operator_cli_parsers_require_raw_n2_and_exact_sessions(self) -> None:
        n2_args = [
            value
            for key, path in self.n2_fixture.directories.items()
            for value in ("--n2-result", f"{key}={path}")
        ]
        parsed = runner.parse_args(
            [
                "--describe-only",
                "--action",
                self.routes[0]["map_action_key"],
                "--physical-plan",
                str(self.plan_file),
                "--binding-review-artifact",
                str(self.review_file),
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
                *n2_args,
                "--n2-reviewer-key",
                str(self.n2_fixture.reviewer_key_file),
            ]
        )
        self.assertEqual(
            set(parsed.n2_result_directories),
            set(n2_analyzer.EXPECTED_RESULT_KEYS),
        )
        analyzed = physical_analyzer.parse_args(
            [
                "--physical-plan",
                str(self.plan_file),
                "--binding-review-artifact",
                str(self.review_file),
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
                *n2_args,
                "--n2-reviewer-key",
                str(self.n2_fixture.reviewer_key_file),
                "--profile-reviewer-key",
                str(self.profile_reviewer_key),
                "--session",
                "map-one.json,target-one.json",
                "--session",
                "map-two.json,target-two.json",
            ]
        )
        self.assertEqual(len(analyzed.sessions), 2)
        with self.assertRaises(SystemExit):
            runner.parse_args(
                [
                    "--describe-only",
                    "--action",
                    self.routes[0]["map_action_key"],
                    "--physical-plan",
                    str(self.plan_file),
                    "--binding-review-artifact",
                    str(self.review_file),
                    "--minimum-interval-seconds",
                    "nan",
                    "--planned-cooldown-seconds",
                    "150",
                    *n2_args,
                    "--n2-reviewer-key",
                    str(self.n2_fixture.reviewer_key_file),
                ]
            )

    def test_tokens_schedule_cross_repeat_and_raw_n2_tamper_fail_closed(self) -> None:
        production_set = self.productions
        map_files, map_profile = production_set[0]
        registry = self.root / "blocked-claims"
        cases = (
            ("action", "wrong", runner.required_panel_plan_confirmation(self.context, self.routes[0]["map_action_key"]), runner.required_production_profile_confirmation(map_profile), "exact action"),
            ("panel", runner.required_authorization_confirmation(self.context, self.routes[0]["map_action_key"]), "wrong", runner.required_production_profile_confirmation(map_profile), "exact panel"),
            ("profile", runner.required_authorization_confirmation(self.context, self.routes[0]["map_action_key"]), runner.required_panel_plan_confirmation(self.context, self.routes[0]["map_action_key"]), "wrong", "exact production"),
        )
        for label, action_token, panel_token, profile_token, message in cases:
            destination = self.root / f"blocked-token-{label}"
            with (
                self.subTest(case=label),
                mock.patch.object(runner, "_utc_now", return_value="2026-08-08T00:20:30Z"),
                mock.patch.object(runner, "_claim_action", side_effect=AssertionError("claim forbidden")),
                mock.patch.object(runner, "http_request", side_effect=AssertionError("network forbidden")),
                self.assertRaisesRegex(runner.N3APhysicalActionError, message),
            ):
                runner.run_n3a_physical_action_once(
                    self.routes[0]["map_action_key"],
                    destination,
                    "http://device",
                    plan_files=self.plan_files,
                    production_files=map_files,
                    evaluated_at=map_profile.report["evaluated_at"],
                    authorization_confirmation=action_token,
                    panel_plan_confirmation=panel_token,
                    profile_confirmation=profile_token,
                    start_temperature_c=25,
                    confirm_supervised_supply_cv_current_normal=True,
                    confirm_physical_cutoff_available=True,
                    confirm_single_visible_refresh=True,
                    confirm_controller_fresh_boot=True,
                )
            self.assertFalse(destination.exists())
        weak_files, weak_profile = self.approve(
            "weak-cooldown",
            self.routes[0]["map_action_key"],
            evaluated_at="2026-08-08T00:20:00Z",
            reviewed_at="2026-08-08T00:19:20Z",
            valid_from="2026-08-08T00:19:30Z",
            expires_at="2026-08-08T00:40:00Z",
            cumulative=1,
            session=0,
            consecutive=0,
            last_completed_at="2026-08-08T00:19:00Z",
            snapshot_at="2026-08-08T00:19:10Z",
            authority_schedule_seconds=30,
        )
        with (
            mock.patch.object(runner, "_utc_now", return_value="2026-08-08T00:20:30Z"),
            mock.patch.object(runner, "_claim_action", side_effect=AssertionError("claim forbidden")),
            mock.patch.object(runner, "http_request", side_effect=AssertionError("network forbidden")),
            self.assertRaisesRegex(runner.N3APhysicalActionError, "inter-session cooldown"),
        ):
            runner.run_n3a_physical_action_once(
                self.routes[0]["map_action_key"],
                self.root / "blocked-cooldown",
                "http://device",
                plan_files=self.plan_files,
                production_files=weak_files,
                evaluated_at=weak_profile.report["evaluated_at"],
                authorization_confirmation=runner.required_authorization_confirmation(self.context, self.routes[0]["map_action_key"]),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(self.context, self.routes[0]["map_action_key"]),
                profile_confirmation=runner.required_production_profile_confirmation(weak_profile),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
            )
        self.assertFalse(registry.exists())

        forged = deepcopy(self.plan)
        forged["selection"]["winner_cell_id"] = "Q3"
        forged["integrity"] = plan_builder._integrity(
            {key: value for key, value in forged.items() if key != "integrity"}
        )
        forged_file = self._write_json("forged-plan.json", forged)
        with self.assertRaises(physical.N3APhysicalExecutionError):
            physical.load_n3a_physical_execution_context(
                plan_file=forged_file,
                binding_review_artifact_file=self.review_file,
                minimum_interval_seconds=SCHEDULE_SECONDS,
                planned_cooldown_seconds=SCHEDULE_SECONDS,
                n2_result_directories=self.n2_fixture.directories,
                n2_reviewer_key_file=self.n2_fixture.reviewer_key_file,
            )

        n2_observation_file = (
            self.n2_fixture.directories["q4-target"]
            / n2_analyzer.fixed.OBSERVATION_FILENAME
        )
        original_n2_observation = n2_observation_file.read_bytes()
        changed = json.loads(original_n2_observation.decode("utf-8"))
        changed["visual"]["detail"] -= 1
        n2_observation_file.write_bytes(canonical_json_bytes(changed))
        try:
            with self.assertRaises(physical.N3APhysicalExecutionError):
                physical.load_n3a_physical_execution_context(
                    plan_file=self.plan_file,
                    binding_review_artifact_file=self.review_file,
                    minimum_interval_seconds=SCHEDULE_SECONDS,
                    planned_cooldown_seconds=SCHEDULE_SECONDS,
                    n2_result_directories=self.n2_fixture.directories,
                    n2_reviewer_key_file=self.n2_fixture.reviewer_key_file,
                )
        finally:
            n2_observation_file.write_bytes(original_n2_observation)

    def test_complete_repeat2_formal_analyzer_and_replay_rejection(self) -> None:
        registry = self.root / "analyzer-claims"
        session_files: list[physical_analyzer.N3APhysicalSessionResultFiles] = []
        times = (
            ("2026-08-08T00:20:30Z", "2026-08-08T00:21:00Z", "2026-08-08T00:23:40Z", "2026-08-08T00:24:00Z"),
            ("2026-08-08T00:27:10Z", "2026-08-08T00:27:30Z", "2026-08-08T00:30:10Z", "2026-08-08T00:30:30Z"),
        )
        for index, (map_live, map_observed, target_live, target_observed) in enumerate(times):
            map_files, map_profile = self.productions[2 * index]
            map_dir, _map_http, _map_evidence, _map_final = self._run_finalize(
                label=f"analysis-s{index + 1}-map",
                route_index=index,
                phase="map",
                files=map_files,
                validated=map_profile,
                registry=registry,
                live_at=map_live,
                observed_at=map_observed,
                metric_offset=index,
            )
            target_files, target_profile = self.productions[2 * index + 1]
            target_dir, _target_http, _target_evidence, _target_final = self._run_finalize(
                label=f"analysis-s{index + 1}-target",
                route_index=index,
                phase="target",
                files=target_files,
                validated=target_profile,
                registry=registry,
                live_at=target_live,
                observed_at=target_observed,
                primer_result=map_dir / runner.P0_RESULT_FILENAME,
                metric_offset=index,
            )
            session_files.append(
                physical_analyzer.N3APhysicalSessionResultFiles(
                    map_dir / runner.P0_RESULT_FILENAME,
                    target_dir / runner.P0_RESULT_FILENAME,
                )
            )
        with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
            report = physical_analyzer.analyze_n3a_physical_result_files(
                plan_files=self.plan_files,
                profile_reviewer_key_file=self.profile_reviewer_key,
                sessions=session_files,
            )
        self.assertTrue(report["analysis_ready"])
        self.assertEqual(report["repeat_count"], 2)
        self.assertEqual(report["verified_visible_action_count"], 4)
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertTrue(report["small_sample_contract"]["all_p95_null"])
        self.assertTrue(report["small_sample_contract"]["all_p99_null"])
        self.assertEqual(
            report["ordered_repeat_drift"]["visual.photo_difference_score"][
                "last_minus_first"
            ],
            1.0,
        )
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            self.assertRaisesRegex(
                runner.N3APhysicalActionError,
                "cross-plan, cross-repeat",
            ),
        ):
            runner.describe_n3a_physical_action(
                self.routes[1]["target_action_key"],
                plan_files=self.plan_files,
                production_files=self.productions[3][0],
                evaluated_at=self.productions[3][1].report["evaluated_at"],
                primer_result_file=session_files[0].map_result_file,
            )
        with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
            physical_analyzer.validate_n3a_physical_analysis_result_files(
                report,
                plan_files=self.plan_files,
                profile_reviewer_key_file=self.profile_reviewer_key,
                sessions=session_files,
            )
        duplicate = [session_files[0], session_files[0]]
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            self.assertRaisesRegex(
                physical_analyzer.N3APhysicalAnalysisError,
                "duplicate result directory",
            ),
        ):
            physical_analyzer.analyze_n3a_physical_result_files(
                plan_files=self.plan_files,
                profile_reviewer_key_file=self.profile_reviewer_key,
                sessions=duplicate,
            )
        target_profile_file = (
            session_files[1].target_result_file.parent / runner.PROFILE_FILENAME
        )
        original_profile = target_profile_file.read_bytes()
        target_profile_file.write_bytes(original_profile + b"\n")
        try:
            with (
                mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
                self.assertRaises(physical_analyzer.N3APhysicalAnalysisError),
            ):
                physical_analyzer.analyze_n3a_physical_result_files(
                    plan_files=self.plan_files,
                    profile_reviewer_key_file=self.profile_reviewer_key,
                    sessions=session_files,
                )
        finally:
            target_profile_file.write_bytes(original_profile)


if __name__ == "__main__":
    unittest.main()
