from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from host.visible_refresh_campaign import physical_rebind as rebind
from host.visible_refresh_campaign import production_profile as production
from tests import n4_v3_bundle_fixture as legacy_fixture
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
from tools import g1_s1_n3_execution_contract as n3
from tools import g1_s1_n4_v3_execution_contract as n4
from tools import g1_s1_n4_v3_physical_execution as n4_physical
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner
from tools import g1_s1_rc2g_n2_photo_campaign as n2_frozen
from tools import g1_s1_rc2g_n4_v3_once as n4_legacy_runner
from tools import g1_s1_rc2g_n4_v3_physical_once as n4_runner


PHYSICAL_PANEL = {
    "model": "MF1750-C73",
    "serial": "MF1750-LAB-PANEL-0002",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
REVIEW_BYTES = b"N3/N4 integration binding to physical N2 campaign test fixture\n"
MINIMUM_INTERVAL_SECONDS = 150
PLANNED_COOLDOWN_SECONDS = 150


class N3N4PhysicalRebindIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        hardware = Path(__file__).resolve().parents[1] / ".test-output" / "hardware"
        cls.temporary = tempfile.TemporaryDirectory(dir=hardware)
        root = cls.root = Path(cls.temporary.name)
        source_file = root / "n2-source.json"
        panel_file = root / "panel.json"
        review_file = cls.binding_review_file = root / "binding-review.bin"
        source_file.write_bytes(canonical_json_bytes(n2_frozen.compile_campaign_manifest()))
        panel_file.write_bytes(canonical_json_bytes(PHYSICAL_PANEL))
        review_file.write_bytes(REVIEW_BYTES)
        cls.anchor = n2_physical.compile_physical_manifest_from_files(
            source_file,
            panel_file,
            review_file,
            minimum_interval_seconds=150,
            planned_cooldown_seconds=150,
        )["physical_campaign_contract"]
        cls.n3_plan = n3.compile_n3b_exact_plan()
        cls.n4_contract = n4.compile_n4_v3_execution_contract()
        cls.n4_rebind = rebind.compile_physical_campaign_rebind(
            cls.n4_contract["p0_campaign"],
            cls.anchor,
            namespace="n4-v3-selected-metric",
            binding_review_bytes=REVIEW_BYTES,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
        )
        cls.n4_context = n4_physical.compile_n4_physical_execution_context(
            cls.n4_rebind,
            cls.n4_rebind["physical_campaign"],
            cls.anchor,
            binding_review_bytes=REVIEW_BYTES,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
        )
        cls.n4_rebind_file = root / "n4-rebind.json"
        cls.n4_campaign_file = root / "n4-physical-campaign.json"
        cls.anchor_file = root / "n2-physical-anchor.json"
        cls.n4_rebind_file.write_bytes(canonical_json_bytes(cls.n4_rebind))
        cls.n4_campaign_file.write_bytes(
            canonical_json_bytes(cls.n4_rebind["physical_campaign"])
        )
        cls.anchor_file.write_bytes(canonical_json_bytes(cls.anchor))
        cls.binding_files = n4_runner.N4PhysicalBindingFiles(
            rebind_manifest=cls.n4_rebind_file,
            physical_campaign=cls.n4_campaign_file,
            physical_anchor_campaign=cls.anchor_file,
            binding_review_artifact=cls.binding_review_file,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
        )
        cls.key_file = root / "reviewer.key"
        cls.key_file.write_bytes(bytes(range(32)))
        cls.map_supplier_file = root / "map-supplier.json"
        cls.map_usage_file = root / "map-usage.json"
        cls.map_supplier_file.write_bytes(
            canonical_json_bytes(
                cls._supplier(
                    document_id="n4-map-limits",
                    valid_from="2026-08-08T00:15:00Z",
                    expires_at="2026-08-08T00:29:00Z",
                )
            )
        )
        cls.map_usage_file.write_bytes(
            canonical_json_bytes(
                cls._usage(
                    evidence_id="n4-map-usage-0",
                    cumulative=0,
                    session=0,
                    consecutive=0,
                    last_completed_at=None,
                    snapshot_at="2026-08-08T00:00:00Z",
                )
            )
        )
        cls.map_production = cls._approve_profile(
            name="map",
            supplier_file=cls.map_supplier_file,
            usage_file=cls.map_usage_file,
            reviewed_at="2026-08-08T00:10:00Z",
        )
        cls.map_validated_production = n4_physical.load_n4_physical_production_profile(
            cls.n4_context,
            profile_file=cls.map_production.profile,
            campaign_file=cls.n4_campaign_file,
            firmware_binary_file=cls.map_production.firmware_binary,
            limit_authority_file=cls.map_production.limit_authority,
            usage_evidence_file=cls.map_production.usage_evidence,
            review_artifact_file=cls.map_production.review_artifact,
            reviewer_key_file=cls.map_production.reviewer_key,
            evaluated_at="2026-08-08T00:20:00Z",
        )
        cls.target_supplier_file = root / "target-supplier.json"
        cls.target_usage_file = root / "target-usage.json"
        cls.target_supplier_file.write_bytes(
            canonical_json_bytes(
                cls._supplier(
                    document_id="n4-target-limits",
                    valid_from="2026-08-08T00:30:00Z",
                    expires_at="2026-08-08T00:49:00Z",
                )
            )
        )
        cls.target_usage_file.write_bytes(
            canonical_json_bytes(
                cls._usage(
                    evidence_id="n4-target-usage-after-map",
                    cumulative=1,
                    session=1,
                    consecutive=1,
                    last_completed_at="2026-08-08T00:21:00Z",
                    snapshot_at="2026-08-08T00:24:00Z",
                )
            )
        )
        cls.target_production = cls._approve_profile(
            name="target",
            supplier_file=cls.target_supplier_file,
            usage_file=cls.target_usage_file,
            reviewed_at="2026-08-08T00:25:00Z",
        )
        cls.target_validated_production = (
            n4_physical.load_n4_physical_production_profile(
                cls.n4_context,
                profile_file=cls.target_production.profile,
                campaign_file=cls.n4_campaign_file,
                firmware_binary_file=cls.target_production.firmware_binary,
                limit_authority_file=cls.target_production.limit_authority,
                usage_evidence_file=cls.target_production.usage_evidence,
                review_artifact_file=cls.target_production.review_artifact,
                reviewer_key_file=cls.target_production.reviewer_key,
                evaluated_at="2026-08-08T00:35:00Z",
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def _supplier(
        cls,
        *,
        document_id,
        valid_from,
        expires_at,
        minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
        minimum_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
    ):
        return {
            "schema_version": 1,
            "kind": production.SUPPLIER_LIMITS_KIND,
            "supplier_id": "mf1750-supplier-integration",
            "document_id": document_id,
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": "MF1750-C73",
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": {
                "maximum_campaign_visible_refreshes": 8,
                "maximum_session_visible_refreshes": 2,
                "maximum_consecutive_visible_refreshes": 2,
                "minimum_interval_seconds": minimum_interval_seconds,
                "minimum_cooldown_seconds": minimum_cooldown_seconds,
                "minimum_start_temperature_c": 10,
                "maximum_start_temperature_c": 40,
                "maximum_post_refresh_temperature_c": 45,
            },
            "validity": {
                "valid_from": valid_from,
                "expires_at": expires_at,
            },
        }

    @classmethod
    def _usage(
        cls,
        *,
        evidence_id,
        cumulative,
        session,
        consecutive,
        last_completed_at,
        snapshot_at,
    ):
        campaign = cls.n4_rebind["physical_campaign"]
        return {
            "schema_version": 1,
            "kind": production.USAGE_EVIDENCE_KIND,
            "evidence_id": evidence_id,
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
        }

    @classmethod
    def _approve_profile(cls, *, name, supplier_file, usage_file, reviewed_at):
        draft = production.compile_production_draft_from_files(
            campaign_file=cls.n4_campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=supplier_file,
            usage_evidence_file=usage_file,
            profile_id=f"n4-physical-{name}",
            profile_version="1.0.0",
        )
        draft_file = cls.root / f"{name}-draft.json"
        draft_file.write_bytes(canonical_json_bytes(draft))
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=cls.n4_campaign_file,
            firmware_binary_file=n2_frozen.FIRMWARE_BINARY,
            supplier_limits_file=supplier_file,
            usage_evidence_file=usage_file,
            reviewer_id="n4-physical-integration-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=cls.key_file,
        )
        review_file = cls.root / f"{name}-profile-review.json"
        profile_file = cls.root / f"{name}-profile.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        return n4_runner.N4ProductionFiles(
            profile=profile_file,
            firmware_binary=n2_frozen.FIRMWARE_BINARY,
            limit_authority=supplier_file,
            usage_evidence=usage_file,
            review_artifact=review_file,
            reviewer_key=cls.key_file,
        )

    @staticmethod
    def _assert_all_priors_rebound(source, physical) -> None:
        source_by_sha = {
            action["action_identity_sha256"]: action for action in source["actions"]
        }
        physical_by_id = {
            action["identity"]["action_id"]: action for action in physical["actions"]
        }
        for old_action in source["actions"]:
            old_prior = old_action["identity"]["prior"]
            new_action = physical_by_id[old_action["identity"]["action_id"]]
            new_prior = new_action["identity"]["prior"]
            if old_prior is None:
                assert new_prior is None
                continue
            old_prior_id = source_by_sha[old_prior["action_identity_sha256"]][
                "identity"
            ]["action_id"]
            assert new_prior is not None
            assert (
                new_prior["action_identity_sha256"]
                == physical_by_id[old_prior_id]["action_identity_sha256"]
            )

    def _create_finalized_map(self, label: str):
        registry = self.root / f"{label}-claims"
        destination = self.root / f"{label}-result"
        scripted = ScriptedRequester(map_responses())
        action_key = "low-balanced-map-primer"
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(n4_runner, "http_request", scripted),
            mock.patch.object(
                n4_runner, "_utc_now", return_value="2026-08-08T00:20:30Z"
            ),
        ):
            n4_runner.run_n4_v3_physical_action_once(
                action_key,
                destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=self.map_production,
                evaluated_at="2026-08-08T00:20:00Z",
                authorization_confirmation=(
                    n4_runner.required_authorization_confirmation(
                        self.n4_context, action_key
                    )
                ),
                panel_build_confirmation=(
                    n4_runner.required_panel_build_confirmation(self.n4_context)
                ),
                profile_confirmation=(
                    n4_runner.required_production_profile_confirmation(
                        self.map_validated_production
                    )
                ),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        snapshot = n4_physical.load_n4_physical_action_snapshot(
            self.n4_context, action_key
        )
        observation = legacy_fixture._operator_observation(
            snapshot,
            root=self.root,
            state=ResultState.PASS,
            score_offset=0,
            electrical_offset=0,
            overrides={"observed_at": "2026-08-08T00:21:00Z"},
        )
        observation_file = self.root / f"{label}-observation.json"
        observation_file.write_bytes(canonical_json_bytes(observation))
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                n4_legacy_runner,
                "_utc_now",
                return_value="2026-08-08T00:21:30Z",
            ),
        ):
            finalized = n4_runner.finalize_n4_v3_physical_observation(
                destination,
                observation_file,
                reviewer_key_file=self.key_file,
            )
        return registry, destination, scripted, finalized

    def test_real_n3b_four_campaigns_rebuild_all_32_actions_and_16_sessions(self) -> None:
        sources = [
            branch["p0_campaign"]
            for branch in self.n3_plan["execution_manifest"]["branches"]
        ]
        self.assertEqual(sum(len(source["actions"]) for source in sources), 32)
        self.assertEqual(sum(len(source["sessions"]) for source in sources), 16)
        source_action_ids = [
            action["identity"]["action_id"]
            for source in sources
            for action in source["actions"]
        ]
        self.assertEqual(len(source_action_ids), len(set(source_action_ids)))

        manifests = [
            rebind.compile_physical_campaign_rebind(
                source,
                self.anchor,
                namespace=f"n3b-block-{index}",
                binding_review_bytes=REVIEW_BYTES,
                minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
                planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
            )
            for index, source in enumerate(sources, start=1)
        ]
        physicals = [manifest["physical_campaign"] for manifest in manifests]
        self.assertEqual(sum(len(item["action_identity_map"]) for item in manifests), 32)
        self.assertEqual(sum(len(item["actions"]) for item in physicals), 32)
        self.assertEqual(sum(len(item["sessions"]) for item in physicals), 16)
        old_hashes = {
            action["action_identity_sha256"]
            for source in sources
            for action in source["actions"]
        }
        new_hashes = {
            action["action_identity_sha256"]
            for physical in physicals
            for action in physical["actions"]
        }
        old_claims = {
            action["claim"]["filename"]
            for source in sources
            for action in source["actions"]
        }
        new_claims = {
            action["claim"]["filename"]
            for physical in physicals
            for action in physical["actions"]
        }
        self.assertEqual(len(new_hashes), 32)
        self.assertEqual(len(new_claims), 32)
        self.assertTrue(old_hashes.isdisjoint(new_hashes))
        self.assertTrue(old_claims.isdisjoint(new_claims))
        for source, physical in zip(sources, physicals):
            self._assert_all_priors_rebound(source, physical)

    def test_real_n4_v3_campaign_rebuilds_all_8_actions_and_4_sessions(self) -> None:
        source = self.n4_contract["p0_campaign"]
        self.assertEqual(len(source["actions"]), 8)
        self.assertEqual(len(source["sessions"]), 4)
        self.assertEqual(
            len({action["identity"]["action_id"] for action in source["actions"]}),
            8,
        )
        manifest = rebind.compile_physical_campaign_rebind(
            source,
            self.anchor,
            namespace="n4-v3-selected-metric",
            binding_review_bytes=REVIEW_BYTES,
            minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
            planned_cooldown_seconds=PLANNED_COOLDOWN_SECONDS,
        )
        physical = manifest["physical_campaign"]
        self.assertEqual(len(manifest["action_identity_map"]), 8)
        self.assertEqual(len(physical["actions"]), 8)
        self.assertEqual(len(physical["sessions"]), 4)
        self.assertTrue(
            {action["action_identity_sha256"] for action in source["actions"]}.isdisjoint(
                {
                    action["action_identity_sha256"]
                    for action in physical["actions"]
                }
            )
        )
        self.assertTrue(
            {action["claim"]["filename"] for action in source["actions"]}.isdisjoint(
                {action["claim"]["filename"] for action in physical["actions"]}
            )
        )
        self._assert_all_priors_rebound(source, physical)

    def test_n4_physical_context_enumerates_only_rebuilt_actions_and_frozen_frames(self) -> None:
        context = self.n4_context
        contract = n4_physical.validate_n4_physical_execution_context(context)
        self.assertEqual(tuple(contract["fixed_actions"]), n4.FIXED_ACTION_KEYS)
        self.assertTrue(contract["power_semantics"]["action_identities_changed"])
        self.assertFalse(contract["power_semantics"]["legacy_action_claims_reusable"])
        old_hashes = set(n4.FIXED_ACTION_SHA256S.values())
        self.assertTrue(old_hashes.isdisjoint(contract["fixed_actions"].values()))
        for action_key in n4.FIXED_ACTION_KEYS:
            with self.subTest(action=action_key):
                physical = n4_physical.load_n4_physical_action_snapshot(
                    context, action_key
                )
                source = n4.load_n4_v3_action_snapshot(action_key)
                self.assertEqual(physical.frame, source.frame)
                self.assertEqual(physical.reference_preview, source.reference_preview)
                self.assertNotEqual(
                    physical.action["action_identity_sha256"],
                    source.action["action_identity_sha256"],
                )

    def test_n4_physical_describe_is_deep_ready_but_zero_claim_and_zero_network(self) -> None:
        registry = self.root / "describe-claims"
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                n4_runner, "http_request", side_effect=AssertionError("network")
            ),
        ):
            description = n4_runner.describe_n4_v3_physical_action(
                "low-balanced-map-primer",
                binding_files=self.binding_files,
                production_files=self.map_production,
                evaluated_at="2026-08-08T00:20:00Z",
            )
        self.assertTrue(description["contract_ready"])
        self.assertTrue(description["profile_validation"]["deep_bindings_valid"])
        self.assertTrue(description["profile_validation"]["production_ready"])
        self.assertEqual(description["profile_validation"]["action_allowlist_count"], 8)
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(registry.exists())
        token = n4_runner.required_authorization_confirmation(
            self.n4_context, "low-balanced-map-primer"
        )
        self.assertIn(
            description["action_identity_sha256"].upper(), token
        )
        self.assertNotIn(
            n4.FIXED_ACTION_SHA256S["low-balanced-map-primer"].upper(), token
        )

    def test_n4_physical_map_fake_http_finalize_and_stored_replay(self) -> None:
        registry = self.root / "map-claims"
        destination = self.root / "map-result"
        responses = map_responses()
        scripted = ScriptedRequester(responses)
        action_key = "low-balanced-map-primer"
        token = n4_runner.required_authorization_confirmation(
            self.n4_context, action_key
        )
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(n4_runner, "http_request", scripted),
            mock.patch.object(
                n4_runner, "_utc_now", return_value="2026-08-08T00:20:30Z"
            ),
        ):
            evidence = n4_runner.run_n4_v3_physical_action_once(
                action_key,
                destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=self.map_production,
                evaluated_at="2026-08-08T00:20:00Z",
                authorization_confirmation=token,
                panel_build_confirmation=(
                    n4_runner.required_panel_build_confirmation(self.n4_context)
                ),
                profile_confirmation=(
                    n4_runner.required_production_profile_confirmation(
                        self.map_validated_production
                    )
                ),
                start_temperature_c=25,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_controller_fresh_boot=True,
                sleeper=lambda _seconds: None,
                clock=MapTickClock(),
            )
        self.assertTrue(evidence["protocol_verified"])
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(
            {
                n4_runner.PHYSICAL_CONTRACT_FILENAME,
                n4_runner.PHYSICAL_REBIND_FILENAME,
                n4_runner.PHYSICAL_CAMPAIGN_FILENAME,
                n4_runner.PHYSICAL_ANCHOR_FILENAME,
                n4_runner.BINDING_REVIEW_FILENAME,
                n4_runner.FIRMWARE_BINARY_FILENAME,
                n4_runner.LIMIT_AUTHORITY_FILENAME,
                n4_runner.USAGE_EVIDENCE_FILENAME,
                n4_runner.PROFILE_REVIEW_FILENAME,
                n4_runner.PRODUCTION_VALIDATION_FILENAME,
                n4_runner.PROFILE_FILENAME,
                n4_runner.LOCK_FILENAME,
                n4_runner.EVIDENCE_FILENAME,
            },
            {path.name for path in destination.iterdir()},
        )
        snapshot = n4_physical.load_n4_physical_action_snapshot(
            self.n4_context, action_key
        )
        observation = legacy_fixture._operator_observation(
            snapshot,
            root=self.root,
            state=ResultState.PASS,
            score_offset=0,
            electrical_offset=0,
            overrides={"observed_at": "2026-08-08T00:21:00Z"},
        )
        observation_file = self.root / "map-observation.json"
        observation_file.write_bytes(canonical_json_bytes(observation))
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
            mock.patch.object(
                n4_legacy_runner,
                "_utc_now",
                return_value="2026-08-08T00:21:30Z",
            ),
        ):
            finalized = n4_runner.finalize_n4_v3_physical_observation(
                destination,
                observation_file,
                reviewer_key_file=self.key_file,
            )
            replay = n4_runner.load_n4_v3_physical_finalized_action_bundle(
                destination / n4_runner.P0_RESULT_FILENAME,
                reviewer_key_file=self.key_file,
            )
        self.assertEqual(finalized["state"], ResultState.PASS.value)
        self.assertTrue(finalized["execution_evidence_verified"])
        self.assertEqual(replay["result_file_sha256"], finalized["result_file_sha256"])
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)

    def test_n4_physical_target_same_cell_chain_and_tamper_rejection(self) -> None:
        map_registry, map_destination, map_scripted, map_finalized = (
            self._create_finalized_map("target-primer")
        )
        map_result_file = map_destination / n4_runner.P0_RESULT_FILENAME
        with mock.patch.object(
            n2_runner, "DEFAULT_CLAIM_REGISTRY", map_registry
        ):
            prior = n4_runner._load_stored_chain(
                map_result_file, reviewer_key_file=self.key_file
            )
        target_action_key = "low-balanced-target"
        target_snapshot = n4_physical.load_n4_physical_action_snapshot(
            self.n4_context, target_action_key
        )
        target_contract = n4_runner._target_contract(
            self.n4_context, target_snapshot
        )
        responses = target_responses(target_snapshot.frame, target_contract)
        completed_map = prior.bundle["evidence"]["protocol_evidence"][
            "completed_map_evidence"
        ]
        responses["/api/job"][0] = (
            200,
            json.dumps(completed_map["job_raw"]),
        )
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(completed_map["diagnostic_raw"]),
        )
        target_scripted = ScriptedRequester(responses)
        target_registry = map_registry
        target_destination = self.root / "target-result"
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", target_registry),
            mock.patch.object(n4_runner, "http_request", target_scripted),
            mock.patch.object(
                n4_runner, "_utc_now", return_value="2026-08-08T00:35:30Z"
            ),
        ):
            evidence = n4_runner.run_n4_v3_physical_action_once(
                target_action_key,
                target_destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=self.target_production,
                evaluated_at="2026-08-08T00:35:00Z",
                authorization_confirmation=(
                    n4_runner.required_authorization_confirmation(
                        self.n4_context, target_action_key
                    )
                ),
                panel_build_confirmation=(
                    n4_runner.required_panel_build_confirmation(self.n4_context)
                ),
                profile_confirmation=(
                    n4_runner.required_production_profile_confirmation(
                        self.target_validated_production
                    )
                ),
                start_temperature_c=25,
                primer_result_file=map_result_file,
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
        self.assertTrue(evidence["protocol_verified"])
        target_observation = legacy_fixture._operator_observation(
            target_snapshot,
            root=self.root,
            state=ResultState.PASS,
            score_offset=0,
            electrical_offset=0,
            overrides={"observed_at": "2026-08-08T00:36:00Z"},
        )
        target_observation_file = self.root / "target-observation.json"
        target_observation_file.write_bytes(canonical_json_bytes(target_observation))
        with (
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", target_registry),
            mock.patch.object(
                n4_legacy_runner,
                "_utc_now",
                return_value="2026-08-08T00:36:30Z",
            ),
        ):
            target_finalized = n4_runner.finalize_n4_v3_physical_observation(
                target_destination,
                target_observation_file,
                reviewer_key_file=self.key_file,
                primer_result_file=map_result_file,
            )
            replay = n4_runner.load_n4_v3_physical_finalized_action_bundle(
                target_destination / n4_runner.P0_RESULT_FILENAME,
                reviewer_key_file=self.key_file,
                primer_result_file=map_result_file,
            )
        self.assertEqual(map_finalized["state"], ResultState.PASS.value)
        self.assertEqual(target_finalized["state"], ResultState.PASS.value)
        self.assertEqual(replay["state"], ResultState.PASS.value)
        self.assertTrue((target_destination / n4_runner.CELL_OBSERVATION_FILENAME).is_file())
        self.assertEqual(map_scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(target_scripted.calls.count(("POST", "/api/frame")), 1)

        with mock.patch.object(
            n2_runner, "DEFAULT_CLAIM_REGISTRY", target_registry
        ):
            target_chain = n4_runner._load_stored_chain(
                target_destination / n4_runner.P0_RESULT_FILENAME,
                reviewer_key_file=self.key_file,
                prior_result_file=map_result_file,
            )
        tampered = deepcopy(target_chain.bundle)
        tampered["finalization"]["profile_confirmation_sha256"] = "0" * 64
        with self.assertRaises(n4_physical.N4PhysicalExecutionError):
            n4_physical.validate_n4_physical_finalized_action_bundle(
                self.n4_context,
                tampered,
                production_profile=target_chain.production,
                expected_action_key=target_action_key,
                prior_bundle=prior.bundle,
                prior_production_profile=prior.production,
            )

        wrong_destination = self.root / "wrong-cell-target"
        with (
            mock.patch.object(
                n2_runner, "DEFAULT_CLAIM_REGISTRY", target_registry
            ),
            mock.patch.object(
                n4_runner,
                "_claim_action",
                side_effect=AssertionError("claim forbidden"),
            ),
            mock.patch.object(
                n4_runner,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ),
            self.assertRaises(n4_runner.N4PhysicalActionError),
        ):
            n4_runner.run_n4_v3_physical_action_once(
                "low-unbalanced-target",
                wrong_destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=self.target_production,
                evaluated_at="2026-08-08T00:35:00Z",
                authorization_confirmation="unreachable",
                panel_build_confirmation="unreachable",
                profile_confirmation="unreachable",
                start_temperature_c=25,
                primer_result_file=map_result_file,
            )
        self.assertFalse(wrong_destination.exists())
        self.assertTrue(map_registry.is_dir())

    def test_n4_live_wrong_tokens_stale_or_future_time_are_zero_claim_zero_network(self) -> None:
        action_key = "low-balanced-map-primer"
        action_token = n4_runner.required_authorization_confirmation(
            self.n4_context, action_key
        )
        panel_token = n4_runner.required_panel_build_confirmation(self.n4_context)
        profile_token = n4_runner.required_production_profile_confirmation(
            self.map_validated_production
        )
        cases = (
            ("wrong-panel", "2026-08-08T00:20:30Z", "wrong", profile_token),
            ("wrong-profile", "2026-08-08T00:20:30Z", panel_token, "wrong"),
            ("stale", "2026-08-08T00:25:01Z", panel_token, profile_token),
            ("future", "2026-08-08T00:19:59Z", panel_token, profile_token),
        )
        for label, live_now, supplied_panel, supplied_profile in cases:
            with self.subTest(case=label):
                destination = self.root / f"blocked-{label}"
                registry = self.root / f"blocked-{label}-claims"
                with (
                    mock.patch.object(
                        n4_runner, "_utc_now", return_value=live_now
                    ),
                    mock.patch.object(
                        n4_runner,
                        "_claim_action",
                        side_effect=AssertionError("claim forbidden"),
                    ),
                    mock.patch.object(
                        n4_runner,
                        "http_request",
                        side_effect=AssertionError("network forbidden"),
                    ),
                    mock.patch.object(
                        n2_runner, "DEFAULT_CLAIM_REGISTRY", registry
                    ),
                    self.assertRaises(n4_runner.N4PhysicalActionError),
                ):
                    n4_runner.run_n4_v3_physical_action_once(
                        action_key,
                        destination,
                        "http://device",
                        binding_files=self.binding_files,
                        production_files=self.map_production,
                        evaluated_at="2026-08-08T00:20:00Z",
                        authorization_confirmation=action_token,
                        panel_build_confirmation=supplied_panel,
                        profile_confirmation=supplied_profile,
                        start_temperature_c=25,
                        confirm_supervised_supply_cv_current_normal=True,
                        confirm_physical_cutoff_available=True,
                        confirm_single_visible_refresh=True,
                        confirm_controller_fresh_boot=True,
                    )
                self.assertFalse(destination.exists())
                self.assertFalse(registry.exists())

    def test_n4_live_enforces_materialized_interval_and_cooldown_before_claim(self) -> None:
        weak_interval_file = self.root / "weak-runtime-interval-limits.json"
        weak_interval_usage = self.root / "weak-runtime-interval-usage.json"
        weak_interval_file.write_bytes(
            canonical_json_bytes(
                self._supplier(
                    document_id="n4-weak-runtime-interval",
                    valid_from="2026-08-08T00:21:20Z",
                    expires_at="2026-08-08T00:29:00Z",
                    minimum_interval_seconds=30,
                    minimum_cooldown_seconds=30,
                )
            )
        )
        weak_interval_usage.write_bytes(
            canonical_json_bytes(
                self._usage(
                    evidence_id="n4-weak-runtime-interval-usage",
                    cumulative=1,
                    session=1,
                    consecutive=1,
                    last_completed_at="2026-08-08T00:21:00Z",
                    snapshot_at="2026-08-08T00:21:05Z",
                )
            )
        )
        interval_production = self._approve_profile(
            name="weak-runtime-interval",
            supplier_file=weak_interval_file,
            usage_file=weak_interval_usage,
            reviewed_at="2026-08-08T00:21:10Z",
        )
        interval_profile = n4_physical.load_n4_physical_production_profile(
            self.n4_context,
            profile_file=interval_production.profile,
            campaign_file=self.n4_campaign_file,
            firmware_binary_file=interval_production.firmware_binary,
            limit_authority_file=interval_production.limit_authority,
            usage_evidence_file=interval_production.usage_evidence,
            review_artifact_file=interval_production.review_artifact,
            reviewer_key_file=interval_production.reviewer_key,
            evaluated_at="2026-08-08T00:22:00Z",
        )
        map_registry, map_destination, _map_scripted, _map_finalized = (
            self._create_finalized_map("runtime-interval-primer")
        )
        target_key = "low-balanced-target"
        target_destination = self.root / "blocked-materialized-interval"
        with (
            mock.patch.object(
                n4_runner, "_utc_now", return_value="2026-08-08T00:22:30Z"
            ),
            mock.patch.object(
                n4_runner,
                "_claim_action",
                side_effect=AssertionError("claim forbidden"),
            ),
            mock.patch.object(
                n4_runner,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ),
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", map_registry),
            self.assertRaisesRegex(
                n4_runner.N4PhysicalActionError,
                "effective physical minimum refresh interval",
            ),
        ):
            n4_runner.run_n4_v3_physical_action_once(
                target_key,
                target_destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=interval_production,
                evaluated_at="2026-08-08T00:22:00Z",
                authorization_confirmation=n4_runner.required_authorization_confirmation(
                    self.n4_context, target_key
                ),
                panel_build_confirmation=n4_runner.required_panel_build_confirmation(
                    self.n4_context
                ),
                profile_confirmation=n4_runner.required_production_profile_confirmation(
                    interval_profile
                ),
                start_temperature_c=25,
                primer_result_file=map_destination / n4_runner.P0_RESULT_FILENAME,
                confirm_supervised_supply_cv_current_normal=True,
                confirm_physical_cutoff_available=True,
                confirm_single_visible_refresh=True,
                confirm_map_fidelity_from_primer=True,
                confirm_esp32_not_restarted_since_primer=True,
                confirm_no_j2_disconnect_since_primer=True,
                confirm_no_panel_power_cycle_since_primer=True,
                confirm_no_other_visible_refresh_since_primer=True,
            )
        self.assertFalse(target_destination.exists())

        weak_cooldown_file = self.root / "weak-runtime-cooldown-limits.json"
        weak_cooldown_usage = self.root / "weak-runtime-cooldown-usage.json"
        weak_cooldown_file.write_bytes(
            canonical_json_bytes(
                self._supplier(
                    document_id="n4-weak-runtime-cooldown",
                    valid_from="2026-08-08T00:19:20Z",
                    expires_at="2026-08-08T00:29:00Z",
                    minimum_interval_seconds=30,
                    minimum_cooldown_seconds=30,
                )
            )
        )
        weak_cooldown_usage.write_bytes(
            canonical_json_bytes(
                self._usage(
                    evidence_id="n4-weak-runtime-cooldown-usage",
                    cumulative=1,
                    session=0,
                    consecutive=0,
                    last_completed_at="2026-08-08T00:19:00Z",
                    snapshot_at="2026-08-08T00:19:05Z",
                )
            )
        )
        cooldown_production = self._approve_profile(
            name="weak-runtime-cooldown",
            supplier_file=weak_cooldown_file,
            usage_file=weak_cooldown_usage,
            reviewed_at="2026-08-08T00:19:10Z",
        )
        cooldown_profile = n4_physical.load_n4_physical_production_profile(
            self.n4_context,
            profile_file=cooldown_production.profile,
            campaign_file=self.n4_campaign_file,
            firmware_binary_file=cooldown_production.firmware_binary,
            limit_authority_file=cooldown_production.limit_authority,
            usage_evidence_file=cooldown_production.usage_evidence,
            review_artifact_file=cooldown_production.review_artifact,
            reviewer_key_file=cooldown_production.reviewer_key,
            evaluated_at="2026-08-08T00:20:00Z",
        )
        map_key = "low-balanced-map-primer"
        cooldown_destination = self.root / "blocked-materialized-cooldown"
        cooldown_registry = self.root / "blocked-materialized-cooldown-claims"
        with (
            mock.patch.object(
                n4_runner, "_utc_now", return_value="2026-08-08T00:20:30Z"
            ),
            mock.patch.object(
                n4_runner,
                "_claim_action",
                side_effect=AssertionError("claim forbidden"),
            ),
            mock.patch.object(
                n4_runner,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ),
            mock.patch.object(
                n2_runner, "DEFAULT_CLAIM_REGISTRY", cooldown_registry
            ),
            self.assertRaisesRegex(
                n4_runner.N4PhysicalActionError,
                "effective physical inter-session cooldown",
            ),
        ):
            n4_runner.run_n4_v3_physical_action_once(
                map_key,
                cooldown_destination,
                "http://device",
                binding_files=self.binding_files,
                production_files=cooldown_production,
                evaluated_at="2026-08-08T00:20:00Z",
                authorization_confirmation=n4_runner.required_authorization_confirmation(
                    self.n4_context, map_key
                ),
                panel_build_confirmation=n4_runner.required_panel_build_confirmation(
                    self.n4_context
                ),
                profile_confirmation=n4_runner.required_production_profile_confirmation(
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


if __name__ == "__main__":
    unittest.main()
