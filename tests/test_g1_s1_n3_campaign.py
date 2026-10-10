from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from host.visible_refresh_campaign import (
    LIMIT_PROFILE_KIND,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    result_file_sha256,
    seal_limit_profile,
)
from tools.g1_s1_n3_campaign import (
    EXPECTED_FROZEN_N3A_CANONICAL_SHA256,
    EXPECTED_FROZEN_N3A_FILE_SHA256,
    EXPECTED_FROZEN_N3B_CANONICAL_SHA256,
    EXPECTED_FROZEN_N3B_FILE_SHA256,
    N3A_REPEAT_COUNTS,
    N3B_FIXED_SEED,
    N3CampaignError,
    balanced_orders,
    build_measurement_asset_registry,
    compile_n3a_manifest,
    compile_n3b_manifest,
    describe_n3_action,
    ordinary_session_regime,
    panel_cold_session_regime,
    validate_n3a_manifest,
)
from tools.g1_s1_rc2g_n2_photo_campaign import FIRMWARE_CONTRACT, PANEL_CONTRACT


def _assets(*, complete: bool) -> dict[str, object]:
    values = [f"{index:x}" * 64 for index in range(1, 11)] if complete else [None] * 10
    return build_measurement_asset_registry(
        timing_clock_asset_sha256=values[0],
        temperature_sensor_asset_sha256=values[1],
        temperature_calibration_asset_sha256=values[2],
        temperature_location_asset_sha256=values[3],
        camera_body_asset_sha256=values[4],
        camera_lens_asset_sha256=values[5],
        camera_mount_asset_sha256=values[6],
        camera_capture_config_sha256=values[7],
        camera_crop_asset_sha256=values[8],
        illumination_asset_sha256=values[9],
    )


def _draft_profile(manifest: dict[str, object]) -> dict[str, object]:
    return seal_limit_profile(
        {
            "schema_version": 1,
            "kind": LIMIT_PROFILE_KIND,
            "profile_id": "n3-draft-missing-supplier-review-values",
            "profile_version": "1.0.0",
            "panel": manifest["panel"],
            "firmware": manifest["firmware"],
            "action_allowlist": [],
            "limits": {
                "maximum_campaign_visible_refreshes": None,
                "maximum_session_visible_refreshes": None,
                "maximum_consecutive_visible_refreshes": None,
                "minimum_interval_seconds": None,
                "minimum_cooldown_seconds": None,
                "minimum_start_temperature_c": None,
                "maximum_start_temperature_c": None,
                "maximum_post_refresh_temperature_c": None,
            },
            "usage": {
                "cumulative_visible_refresh_count": None,
                "session_visible_refresh_count": None,
                "consecutive_visible_refresh_count": None,
                "last_visible_refresh_completed_at": None,
                "snapshot_at": None,
                "evidence_sha256": None,
            },
            "validity": {"valid_from": None, "expires_at": None},
            "review": {
                "approved": False,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_artifact_sha256": None,
            },
        }
    )


class N3CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.n3a = compile_n3a_manifest(
            panel=PANEL_CONTRACT,
            firmware=FIRMWARE_CONTRACT,
        )
        cls.n3b = compile_n3b_manifest(
            panel=PANEL_CONTRACT,
            firmware=FIRMWARE_CONTRACT,
        )

    def test_n3a_freezes_four_natural_photo_winner_branches_and_2_3_4(self) -> None:
        manifest = self.n3a
        self.assertTrue(manifest["source_n2"]["natural_photo_input"])
        self.assertTrue(manifest["source_n2"]["scientific_separation_gate_pass"])
        self.assertEqual(
            manifest["source_n2"]["q3_q4_deterministic_max_evaluations"],
            262_144,
        )
        self.assertEqual([branch["winner_cell_id"] for branch in manifest["branches"]], ["Q1", "Q2", "Q3", "Q4"])
        self.assertTrue(all(branch["natural_photo_input"] for branch in manifest["branches"]))
        self.assertTrue(
            all(
                [template["repeat_count"] for template in branch["repeat_templates"]]
                == list(N3A_REPEAT_COUNTS)
                for branch in manifest["branches"]
            )
        )
        campaigns = [
            template["p0_campaign"]
            for branch in manifest["branches"]
            for template in branch["repeat_templates"]
        ]
        self.assertEqual(sum(len(campaign["sessions"]) for campaign in campaigns), 36)
        self.assertEqual(sum(len(campaign["actions"]) for campaign in campaigns), 72)
        action_shas = [
            action["action_identity_sha256"]
            for campaign in campaigns
            for action in campaign["actions"]
        ]
        action_ids = [
            action["identity"]["action_id"]
            for campaign in campaigns
            for action in campaign["actions"]
        ]
        claims = [
            action["claim"]["filename"]
            for campaign in campaigns
            for action in campaign["actions"]
        ]
        self.assertEqual(len(action_shas), len(set(action_shas)))
        self.assertEqual(len(action_ids), len(set(action_ids)))
        self.assertEqual(len(claims), len(set(claims)))

    def test_default_manifest_canonical_and_whole_file_identities_are_frozen(self) -> None:
        self.assertEqual(
            self.n3a["integrity"]["canonical_sha256"],
            EXPECTED_FROZEN_N3A_CANONICAL_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(canonical_json_bytes(self.n3a)).hexdigest(),
            EXPECTED_FROZEN_N3A_FILE_SHA256,
        )
        self.assertEqual(
            self.n3b["integrity"]["canonical_sha256"],
            EXPECTED_FROZEN_N3B_CANONICAL_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(canonical_json_bytes(self.n3b)).hexdigest(),
            EXPECTED_FROZEN_N3B_FILE_SHA256,
        )

    def test_default_sessions_split_controller_map_and_j2_without_forcing_cycle(self) -> None:
        self.assertEqual(ordinary_session_regime()["controller"], {"fresh_boot_required": True})
        self.assertTrue(ordinary_session_regime()["visible_prior"]["own_map_required"])
        campaigns = [
            template["p0_campaign"]
            for branch in self.n3a["branches"]
            for template in branch["repeat_templates"]
        ]
        for campaign in campaigns:
            for session in campaign["sessions"]:
                self.assertEqual(session["power_mode"], "controller_fresh_boot")
                self.assertTrue(session["requires_controller_fresh_boot"])
                self.assertFalse(session["requires_panel_power_cycle"])
                self.assertTrue(session["j2_may_remain_on_before_session"])
                self.assertIsNone(session["minimum_panel_power_off_seconds"])
                first, second = session["action_identity_sha256s"]
                actions = {action["action_identity_sha256"]: action for action in campaign["actions"]}
                self.assertIsNone(actions[first]["identity"]["prior"])
                self.assertEqual(actions[second]["identity"]["prior"]["action_identity_sha256"], first)

    def test_panel_cold_requires_reviewed_profile_and_positive_dwell(self) -> None:
        review_sha = "a" * 64
        regime = panel_cold_session_regime(
            minimum_measured_off_seconds=45,
            review_artifact_sha256=review_sha,
        )
        manifest = compile_n3a_manifest(
            panel=PANEL_CONTRACT,
            firmware=FIRMWARE_CONTRACT,
            session_regime=regime,
        )
        session = manifest["branches"][0]["repeat_templates"][0]["p0_campaign"]["sessions"][0]
        self.assertEqual(session["power_mode"], "panel_cold_cycle")
        self.assertEqual(session["minimum_panel_power_off_seconds"], 45.0)
        self.assertFalse(session["j2_may_remain_on_before_session"])
        with self.assertRaises(N3CampaignError):
            panel_cold_session_regime(
                minimum_measured_off_seconds=0,
                review_artifact_sha256=review_sha,
            )
        with self.assertRaises(N3CampaignError):
            panel_cold_session_regime(
                minimum_measured_off_seconds=45,
                review_artifact_sha256="not-a-hash",
            )

    def test_n3b_fixed_seed_is_position_and_predecessor_balanced_without_carryover(self) -> None:
        orders = balanced_orders(N3B_FIXED_SEED)
        self.assertEqual(orders, self.n3b["order_contract"]["orders"])
        for candidate in ("Q1", "Q2", "Q3", "Q4"):
            self.assertEqual(
                [sum(order[position] == candidate for order in orders) for position in range(4)],
                [1, 1, 1, 1],
            )
        directed_pairs = [
            (order[index], order[index + 1])
            for order in orders
            for index in range(3)
        ]
        self.assertEqual(len(directed_pairs), 12)
        self.assertEqual(len(set(directed_pairs)), 12)
        self.assertFalse(self.n3b["order_contract"]["previous_target_as_prior"])
        self.assertEqual(self.n3b["order_contract"]["carryover_followup"], "N8")
        self.assertEqual(
            sum(len(branch["p0_campaign"]["sessions"]) for branch in self.n3b["branches"]),
            16,
        )
        self.assertEqual(
            sum(len(branch["p0_campaign"]["actions"]) for branch in self.n3b["branches"]),
            32,
        )

    def test_resealed_cross_repeat_route_replay_is_rejected(self) -> None:
        tampered = deepcopy(self.n3a)
        first = tampered["branches"][0]["repeat_templates"][0]["routes"][0]
        foreign = tampered["branches"][0]["repeat_templates"][1]["routes"][0]
        first["target_action_identity_sha256"] = foreign["target_action_identity_sha256"]
        scope = tampered["integrity"]["canonical_sha256_scope"]
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"] = {
            "canonical_sha256": hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest(),
            "canonical_sha256_scope": scope,
        }
        with self.assertRaises(N3CampaignError):
            validate_n3a_manifest(tampered)

    def test_missing_supplier_and_review_values_leave_software_ready_but_hardware_false(self) -> None:
        manifest = compile_n3a_manifest(
            panel=PANEL_CONTRACT,
            firmware=FIRMWARE_CONTRACT,
            measurement_assets=_assets(complete=True),
        )
        template = manifest["branches"][0]["repeat_templates"][0]
        map_sha = template["routes"][0]["map_action_identity_sha256"]
        description = describe_n3_action(
            manifest,
            action_identity_sha256=map_sha,
            limit_profile=_draft_profile(manifest),
            evaluated_at="2026-08-08T12:00:00Z",
        )
        self.assertTrue(description["software_ready"])
        self.assertTrue(description["measurement_assets_ready"])
        self.assertFalse(description["contract_ready"])
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["hardware_execution_authorized"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertIn(
            "critical_null:limits.maximum_campaign_visible_refreshes",
            description["blockers"],
        )
        self.assertIn("review_not_approved", description["blockers"])

    def test_wrong_prior_result_from_another_repeat_is_rejected(self) -> None:
        template = self.n3a["branches"][0]["repeat_templates"][0]
        target_sha = template["routes"][0]["target_action_identity_sha256"]
        foreign_map_sha = template["routes"][1]["map_action_identity_sha256"]
        foreign_result = build_result_record(
            action_identity_sha256=foreign_map_sha,
            state=ResultState.PASS,
            completed_at="2026-08-08T11:50:00Z",
            evidence_manifest_sha256="e" * 64,
            post_request_count=1,
        )
        with self.assertRaises(N3CampaignError):
            describe_n3_action(
                self.n3a,
                action_identity_sha256=target_sha,
                limit_profile=_draft_profile(self.n3a),
                evaluated_at="2026-08-08T12:00:00Z",
                prior_result=foreign_result,
                prior_result_sha256=result_file_sha256(foreign_result),
            )


if __name__ == "__main__":
    unittest.main()
