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
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    TickClock as TargetTickClock,
    _responses as target_responses,
)
from tools import g1_s1_n2_physical_campaign as n2_physical
from tools import g1_s1_n3b_physical_execution as physical
from tools import g1_s1_rc2g_n2_photo_campaign as n2_frozen
from tools import g1_s1_rc2g_n3_once as legacy
from tools import g1_s1_rc2g_n3b_physical_once as runner


SCHEDULE_SECONDS = 150
PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-N3B-0001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
REVIEW_BYTES = b"N3B physical 32-action supervised test binding\n"


class N3BPhysicalOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        cls.temporary = tempfile.TemporaryDirectory(dir=hardware)
        cls.root = Path(cls.temporary.name)
        source_file = cls._write_json(
            "n2-source.json", n2_frozen.compile_campaign_manifest()
        )
        panel_file = cls._write_json("panel.json", PANEL)
        cls.review_file = cls.root / "binding-review.bin"
        cls.review_file.write_bytes(REVIEW_BYTES)
        cls.anchor = n2_physical.compile_physical_manifest_from_files(
            source_file,
            panel_file,
            cls.review_file,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
        )["physical_campaign_contract"]
        cls.context = physical.compile_n3b_physical_execution_context(
            cls.anchor,
            measurement_assets=n3_fixture.registered_assets(),
            binding_review_bytes=REVIEW_BYTES,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
            namespace_prefix="n3b-integration",
        )
        cls.plan_file = cls._write_json("N3B-PHYSICAL.json", cls.context.plan)
        cls.plan_files = runner.N3BPhysicalPlanFiles(
            plan=cls.plan_file,
            binding_review_artifact=cls.review_file,
            minimum_interval_seconds=SCHEDULE_SECONDS,
            planned_cooldown_seconds=SCHEDULE_SECONDS,
        )
        cls.route = cls.context.plan["selected_routes"][0]
        cls.map_key = cls.route["map_action_key"]
        cls.target_key = cls.route["target_action_key"]
        cls.map_snapshot = physical.load_n3b_physical_action_snapshot(
            cls.context, cls.map_key
        )
        cls.target_snapshot = physical.load_n3b_physical_action_snapshot(
            cls.context, cls.target_key
        )
        cls.campaign_file = cls._write_json(
            "block-1-physical-campaign.json", cls.map_snapshot.campaign
        )
        cls.reviewer_key = cls.root / "reviewer.key"
        cls.reviewer_key.write_bytes(bytes(range(32)))
        cls.map_production, cls.map_validated = cls._approve(
            "map",
            evaluated_at="2026-08-08T00:20:00Z",
            reviewed_at="2026-08-08T00:10:00Z",
            valid_from="2026-08-08T00:15:00Z",
            expires_at="2026-08-08T00:29:00Z",
            cumulative=0,
            session=0,
            consecutive=0,
            last_completed_at=None,
            snapshot_at="2026-08-08T00:00:00Z",
        )
        cls.target_production, cls.target_validated = cls._approve(
            "target",
            evaluated_at="2026-08-08T00:35:00Z",
            reviewed_at="2026-08-08T00:25:00Z",
            valid_from="2026-08-08T00:30:00Z",
            expires_at="2026-08-08T00:49:00Z",
            cumulative=1,
            session=1,
            consecutive=1,
            last_completed_at="2026-08-08T00:21:00Z",
            snapshot_at="2026-08-08T00:24:00Z",
        )

    @classmethod
    def tearDownClass(cls) -> None:
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
        authority_schedule_seconds: int,
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
            "issuer": "n3b-physical-test-process-owner",
            "policy_id": f"n3b-{name}-process-policy",
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
    def _approve(
        cls,
        name: str,
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
    ) -> tuple[runner.N3BProductionFiles, production.ValidatedProductionProfile]:
        policy_file = cls._write_json(
            f"{name}-limit-authority.json",
            cls._policy(
                name,
                valid_from=valid_from,
                expires_at=expires_at,
                authority_schedule_seconds=authority_schedule_seconds,
            ),
        )
        usage_file = cls._write_json(
            f"{name}-usage.json",
            {
                "schema_version": 1,
                "kind": production.USAGE_EVIDENCE_KIND,
                "evidence_id": f"n3b-{name}-usage",
                "campaign_canonical_sha256": cls.map_snapshot.campaign["integrity"][
                    "canonical_sha256"
                ],
                "panel": cls.map_snapshot.campaign["panel"],
                "firmware": cls.map_snapshot.campaign["firmware"],
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
            profile_id=f"n3b-{name}-physical-production-profile",
            profile_version="1.0.0",
        )
        draft_file = cls._write_json(f"{name}-draft.json", draft)
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=cls.campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=policy_file,
            usage_evidence_file=usage_file,
            reviewer_id="n3b-physical-test-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=cls.reviewer_key,
        )
        review_file = cls.root / f"{name}-profile-review.json"
        profile_file = cls.root / f"{name}-profile.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        files = runner.N3BProductionFiles(
            profile=profile_file,
            physical_campaign=cls.campaign_file,
            firmware_binary=n2_frozen.FIRMWARE_BINARY,
            limit_authority=policy_file,
            usage_evidence=usage_file,
            review_artifact=review_file,
            reviewer_key=cls.reviewer_key,
        )
        validated = physical.load_n3b_physical_production_profile(
            cls.context,
            cls.map_key if cumulative == 0 else cls.target_key,
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

    def _finalized_map(self, label: str):
        registry = self.root / f"{label}-claims"
        destination = self.root / f"{label}-result"
        scripted = ScriptedRequester(map_responses())
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", scripted),
            mock.patch.object(
                runner, "_utc_now", return_value="2026-08-08T00:20:30Z"
            ),
        ):
            evidence = runner.run_n3b_physical_action_once(
                self.map_key,
                destination,
                "http://device",
                plan_files=self.plan_files,
                production_files=self.map_production,
                evaluated_at="2026-08-08T00:20:00Z",
                authorization_confirmation=runner.required_authorization_confirmation(
                    self.context, self.map_key
                ),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(
                    self.context, self.map_key
                ),
                profile_confirmation=runner.required_production_profile_confirmation(
                    self.map_validated
                ),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        observation = n3_fixture._operator_observation(
            self.map_snapshot,
            root=self.root,
            state=ResultState.PASS,
            metric_offset=0,
            overrides={"observed_at": "2026-08-08T00:21:00Z"},
        )
        observation_file = self._write_json(f"{label}-observation.json", observation)
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                legacy, "_utc_now", return_value="2026-08-08T00:21:30Z"
            ),
        ):
            finalized = runner.finalize_n3b_physical_observation(
                destination,
                observation_file,
                reviewer_key_file=self.reviewer_key,
            )
        return registry, destination, scripted, evidence, finalized

    def test_plan_has_32_dynamic_actions_16_sessions_and_truthful_schedule(self) -> None:
        plan = physical.validate_n3b_physical_execution_context(self.context)
        self.assertEqual(len(plan["fixed_actions"]), 32)
        self.assertEqual(len(plan["selected_routes"]), 16)
        self.assertEqual(
            sum(
                len(item["manifest"]["physical_campaign"]["sessions"])
                for item in plan["physical_rebinds"]
            ),
            16,
        )
        self.assertEqual(
            plan["process_schedule"],
            {
                "classification": "operator_selected_experimental_process_schedule",
                "minimum_interval_seconds": 150.0,
                "not_a_supplier_rating": True,
                "planned_cooldown_seconds": 150.0,
            },
        )
        source_claims = {
            action["claim"]["filename"]
            for branch in plan["source_exact_plan"]["execution_manifest"]["branches"]
            for action in branch["p0_campaign"]["actions"]
        }
        physical_claims = {
            action["claim"]["filename"]
            for item in plan["physical_rebinds"]
            for action in item["manifest"]["physical_campaign"]["actions"]
        }
        self.assertEqual(len(physical_claims), 32)
        self.assertTrue(source_claims.isdisjoint(physical_claims))
        self.assertEqual(
            self.map_validated.report["limit_authority_classification"],
            production.SUPERVISED_PROCESS_AUTHORITY_CLASSIFICATION,
        )

    def test_describe_is_deep_ready_without_claim_or_network(self) -> None:
        registry = self.root / "describe-claims"
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                runner, "http_request", side_effect=AssertionError("network forbidden")
            ),
        ):
            description = runner.describe_n3b_physical_action(
                self.map_key,
                plan_files=self.plan_files,
                production_files=self.map_production,
                evaluated_at="2026-08-08T00:20:00Z",
            )
        self.assertTrue(description["contract_ready"])
        self.assertEqual(description["profile_validation"]["action_allowlist_count"], 8)
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(registry.exists())

    def test_map_target_finalize_replay_and_tamper_rejection(self) -> None:
        registry, map_directory, map_scripted, map_evidence, map_finalized = (
            self._finalized_map("full-chain-map")
        )
        map_result = map_directory / runner.P0_RESULT_FILENAME
        with mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry):
            prior = runner._load_stored_chain(
                map_result, reviewer_key_file=self.reviewer_key
            )
        target_contract = runner._target_contract(self.context, self.target_snapshot)
        responses = target_responses(self.target_snapshot.frame, target_contract)
        completed_map = prior.bundle["evidence"]["protocol_evidence"][
            "completed_map_evidence"
        ]
        responses["/api/job"][0] = (200, json.dumps(completed_map["job_raw"]))
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(completed_map["diagnostic_raw"]),
        )
        target_scripted = ScriptedRequester(responses)
        target_directory = self.root / "full-chain-target-result"
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(runner, "http_request", target_scripted),
            mock.patch.object(
                runner, "_utc_now", return_value="2026-08-08T00:35:30Z"
            ),
        ):
            target_evidence = runner.run_n3b_physical_action_once(
                self.target_key,
                target_directory,
                "http://device",
                plan_files=self.plan_files,
                production_files=self.target_production,
                evaluated_at="2026-08-08T00:35:00Z",
                authorization_confirmation=runner.required_authorization_confirmation(
                    self.context, self.target_key
                ),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(
                    self.context, self.target_key
                ),
                profile_confirmation=runner.required_production_profile_confirmation(
                    self.target_validated
                ),
                start_temperature_c=25,
                primer_result_file=map_result,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_map_fidelity_from_primer=True,
                confirm_esp32_not_restarted_since_primer=True,
                confirm_no_j2_disconnect_since_primer=True,
                confirm_no_panel_power_cycle_since_primer=True,
                confirm_no_other_visible_refresh_since_primer=True,
                sleeper=lambda _seconds: None,
                clock=TargetTickClock(),
            )
        observation = n3_fixture._operator_observation(
            self.target_snapshot,
            root=self.root,
            state=ResultState.PASS,
            metric_offset=0,
            overrides={"observed_at": "2026-08-08T00:36:00Z"},
        )
        observation_file = self._write_json("target-observation.json", observation)
        with (
            mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                legacy, "_utc_now", return_value="2026-08-08T00:36:30Z"
            ),
        ):
            target_finalized = runner.finalize_n3b_physical_observation(
                target_directory,
                observation_file,
                reviewer_key_file=self.reviewer_key,
                primer_result_file=map_result,
            )
            replay = runner.load_n3b_physical_finalized_action_bundle(
                target_directory / runner.P0_RESULT_FILENAME,
                reviewer_key_file=self.reviewer_key,
                primer_result_file=map_result,
            )
            chain = runner._load_stored_chain(
                target_directory / runner.P0_RESULT_FILENAME,
                reviewer_key_file=self.reviewer_key,
                prior_result_file=map_result,
            )
        self.assertTrue(map_evidence["protocol_verified"])
        self.assertTrue(target_evidence["protocol_verified"])
        self.assertEqual(map_finalized["state"], ResultState.PASS.value)
        self.assertEqual(target_finalized["state"], ResultState.PASS.value)
        self.assertEqual(replay["state"], ResultState.PASS.value)
        self.assertEqual(map_scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(target_scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertTrue(
            (target_directory / runner.SESSION_OBSERVATION_FILENAME).is_file()
        )
        self.assertTrue((target_directory / runner.CAMERA_CAPTURE_FILENAME).is_file())
        self.assertFalse((target_directory / "reviewer.key").exists())
        self.assertEqual(target_evidence["effective_minimum_interval_seconds"], 150)
        self.assertTrue(target_evidence["schedule_gates_satisfied"])

        tampered = deepcopy(chain.bundle)
        tampered["finalization"]["effective_minimum_interval_seconds"] = 149
        with self.assertRaises(physical.N3BPhysicalExecutionError):
            physical.validate_n3b_physical_finalized_action_bundle(
                self.context,
                tampered,
                production_profile=chain.production,
                expected_action_key=self.target_key,
                prior_bundle=prior.bundle,
                prior_production_profile=prior.production,
            )

    def test_materialized_interval_and_freshness_fail_before_claim_and_network(self) -> None:
        registry, map_directory, _scripted, _evidence, _finalized = (
            self._finalized_map("blocked-target-map")
        )
        weak_files, weak_profile = self._approve(
            "weak-target",
            evaluated_at="2026-08-08T00:22:00Z",
            reviewed_at="2026-08-08T00:21:10Z",
            valid_from="2026-08-08T00:21:20Z",
            expires_at="2026-08-08T00:29:00Z",
            cumulative=1,
            session=1,
            consecutive=1,
            last_completed_at="2026-08-08T00:21:00Z",
            snapshot_at="2026-08-08T00:21:05Z",
            authority_schedule_seconds=30,
        )
        cases = (
            (
                "materialized-interval",
                "2026-08-08T00:22:30Z",
                runner.required_panel_plan_confirmation(self.context, self.target_key),
                runner.required_production_profile_confirmation(weak_profile),
                "effective physical minimum refresh interval",
            ),
            (
                "stale",
                "2026-08-08T00:27:01Z",
                runner.required_panel_plan_confirmation(self.context, self.target_key),
                runner.required_production_profile_confirmation(weak_profile),
                "too old",
            ),
            (
                "future",
                "2026-08-08T00:21:59Z",
                runner.required_panel_plan_confirmation(self.context, self.target_key),
                runner.required_production_profile_confirmation(weak_profile),
                "must not be future",
            ),
        )
        for label, live_now, plan_token, profile_token, expected in cases:
            destination = self.root / f"blocked-{label}"
            with (
                self.subTest(case=label),
                mock.patch.object(runner, "_utc_now", return_value=live_now),
                mock.patch.object(
                    runner,
                    "_claim_action",
                    side_effect=AssertionError("claim forbidden"),
                ),
                mock.patch.object(
                    runner,
                    "http_request",
                    side_effect=AssertionError("network forbidden"),
                ),
                mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
                self.assertRaisesRegex(runner.N3BPhysicalActionError, expected),
            ):
                runner.run_n3b_physical_action_once(
                    self.target_key,
                    destination,
                    "http://device",
                    plan_files=self.plan_files,
                    production_files=weak_files,
                    evaluated_at="2026-08-08T00:22:00Z",
                    authorization_confirmation=runner.required_authorization_confirmation(
                        self.context, self.target_key
                    ),
                    panel_plan_confirmation=plan_token,
                    profile_confirmation=profile_token,
                    start_temperature_c=25,
                    primer_result_file=map_directory / runner.P0_RESULT_FILENAME,
                    confirm_supervised_supply_cv_current_normal=True,
                    confirm_physical_cutoff_available=True,
                    confirm_single_visible_refresh=True,
                    confirm_map_fidelity_from_primer=True,
                    confirm_esp32_not_restarted_since_primer=True,
                    confirm_no_j2_disconnect_since_primer=True,
                    confirm_no_panel_power_cycle_since_primer=True,
                    confirm_no_other_visible_refresh_since_primer=True,
                )
            self.assertFalse(destination.exists())

        exact_tokens = (
            (
                "wrong-action-token",
                "wrong",
                runner.required_panel_plan_confirmation(self.context, self.target_key),
                runner.required_production_profile_confirmation(
                    self.target_validated
                ),
                "exact action authorization",
            ),
            (
                "wrong-plan-token",
                runner.required_authorization_confirmation(
                    self.context, self.target_key
                ),
                "wrong",
                runner.required_production_profile_confirmation(
                    self.target_validated
                ),
                "exact panel/plan confirmation",
            ),
            (
                "wrong-profile-token",
                runner.required_authorization_confirmation(
                    self.context, self.target_key
                ),
                runner.required_panel_plan_confirmation(self.context, self.target_key),
                "wrong",
                "exact production-profile confirmation",
            ),
        )
        for label, action_token, plan_token, profile_token, expected in exact_tokens:
            destination = self.root / f"blocked-{label}"
            with (
                self.subTest(case=label),
                mock.patch.object(
                    runner, "_utc_now", return_value="2026-08-08T00:35:30Z"
                ),
                mock.patch.object(
                    runner,
                    "_claim_action",
                    side_effect=AssertionError("claim forbidden"),
                ),
                mock.patch.object(
                    runner,
                    "http_request",
                    side_effect=AssertionError("network forbidden"),
                ),
                mock.patch.object(legacy, "DEFAULT_CLAIM_REGISTRY", registry),
                self.assertRaisesRegex(runner.N3BPhysicalActionError, expected),
            ):
                runner.run_n3b_physical_action_once(
                    self.target_key,
                    destination,
                    "http://device",
                    plan_files=self.plan_files,
                    production_files=self.target_production,
                    evaluated_at="2026-08-08T00:35:00Z",
                    authorization_confirmation=action_token,
                    panel_plan_confirmation=plan_token,
                    profile_confirmation=profile_token,
                    start_temperature_c=25,
                    primer_result_file=map_directory / runner.P0_RESULT_FILENAME,
                    confirm_supervised_supply_cv_current_normal=True,
                    confirm_physical_cutoff_available=True,
                    confirm_single_visible_refresh=True,
                    confirm_map_fidelity_from_primer=True,
                    confirm_esp32_not_restarted_since_primer=True,
                    confirm_no_j2_disconnect_since_primer=True,
                    confirm_no_panel_power_cycle_since_primer=True,
                    confirm_no_other_visible_refresh_since_primer=True,
                )
            self.assertFalse(destination.exists())

        cooldown_files, cooldown_profile = self._approve(
            "weak-cooldown",
            evaluated_at="2026-08-08T00:20:00Z",
            reviewed_at="2026-08-08T00:19:10Z",
            valid_from="2026-08-08T00:19:20Z",
            expires_at="2026-08-08T00:29:00Z",
            cumulative=1,
            session=0,
            consecutive=0,
            last_completed_at="2026-08-08T00:19:00Z",
            snapshot_at="2026-08-08T00:19:05Z",
            authority_schedule_seconds=30,
        )
        cooldown_destination = self.root / "blocked-materialized-cooldown"
        cooldown_registry = self.root / "blocked-materialized-cooldown-claims"
        with (
            mock.patch.object(
                runner, "_utc_now", return_value="2026-08-08T00:20:30Z"
            ),
            mock.patch.object(
                runner,
                "_claim_action",
                side_effect=AssertionError("claim forbidden"),
            ),
            mock.patch.object(
                runner,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ),
            mock.patch.object(
                legacy, "DEFAULT_CLAIM_REGISTRY", cooldown_registry
            ),
            self.assertRaisesRegex(
                runner.N3BPhysicalActionError,
                "effective physical inter-session cooldown",
            ),
        ):
            runner.run_n3b_physical_action_once(
                self.map_key,
                cooldown_destination,
                "http://device",
                plan_files=self.plan_files,
                production_files=cooldown_files,
                evaluated_at="2026-08-08T00:20:00Z",
                authorization_confirmation=runner.required_authorization_confirmation(
                    self.context, self.map_key
                ),
                panel_plan_confirmation=runner.required_panel_plan_confirmation(
                    self.context, self.map_key
                ),
                profile_confirmation=runner.required_production_profile_confirmation(
                    cooldown_profile
                ),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
            )
        self.assertFalse(cooldown_destination.exists())
        self.assertFalse(cooldown_registry.exists())

    def test_cli_rejects_nonfinite_schedule_and_accepts_neutral_alias(self) -> None:
        for option, value in (
            ("--minimum-interval-seconds", "nan"),
            ("--minimum-interval-seconds", "inf"),
            ("--planned-cooldown-seconds", "nan"),
        ):
            argv = [
                "--describe-only",
                "--action",
                self.map_key,
                "--physical-plan",
                str(self.plan_file),
                "--binding-review-artifact",
                str(self.review_file),
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
            ]
            argv[argv.index(option) + 1] = value
            with self.subTest(option=option, value=value), self.assertRaises(SystemExit):
                runner.parse_args(argv)
        parsed = runner.parse_args(
            [
                "--describe-only",
                "--action",
                self.map_key,
                "--physical-plan",
                str(self.plan_file),
                "--binding-review-artifact",
                str(self.review_file),
                "--minimum-interval-seconds",
                "150",
                "--planned-cooldown-seconds",
                "150",
                "--limit-profile",
                str(self.map_production.profile),
                "--physical-campaign",
                str(self.map_production.physical_campaign),
                "--firmware-binary",
                str(self.map_production.firmware_binary),
                "--supplier-limits",
                str(self.map_production.limit_authority),
                "--usage-evidence",
                str(self.map_production.usage_evidence),
                "--profile-review-artifact",
                str(self.map_production.review_artifact),
                "--reviewer-key",
                str(self.map_production.reviewer_key),
                "--evaluated-at",
                "2026-08-08T00:20:00Z",
            ]
        )
        self.assertEqual(parsed.limit_authority, self.map_production.limit_authority)


if __name__ == "__main__":
    unittest.main()
