from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from host.epd_frame import HEIGHT, WIDTH
from host.extended_color import COLOR_ORDER
from host.extended_color.aggregation import (
    MeasurementAggregationError,
    seal_measurement_plan,
)
from tools.mf1750_n5_measurement_campaign import (
    DEFAULT_FIRMWARE,
    DEFAULT_PANEL,
    N5CampaignError,
    build_reviewed_transition_recovery_profile,
    compile_campaign_manifest,
    formal_transition_template,
    reviewed_panel_cold_profile,
    validate_compiled_manifest,
    validate_transition_recovery_profile,
)


def _bound_panel() -> dict[str, str]:
    return {**DEFAULT_PANEL, "serial": "PANEL-N5-001"}


def _cold_profile() -> dict[str, object]:
    return reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )


def _recovery_profile() -> dict[str, object]:
    return build_reviewed_transition_recovery_profile(
        panel=_bound_panel(),
        firmware=DEFAULT_FIRMWARE,
        waveform_id="wf-n5-reviewed-v1",
        waveform_sha256="2" * 64,
        qualification_artifact_sha256="3" * 64,
        reviewer_id="reviewer-n5",
        reviewed_at="2026-08-08T12:00:00+08:00",
        review_artifact_sha256="4" * 64,
        supplier_limit_profile_sha256="5" * 64,
        usage_limit_contract_sha256="6" * 64,
        temperature_chain_sha256="7" * 64,
    )


class N5DefaultCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = compile_campaign_manifest()

    def test_default_shared_p0_is_11_sessions_22_actions_and_zero_execution(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["counts"]["declared_sessions"], 11)
        self.assertEqual(manifest["counts"]["declared_actions"], 22)
        self.assertEqual(len(manifest["shared_p0"]["sessions"]), 11)
        self.assertEqual(len(manifest["shared_p0"]["actions"]), 22)
        self.assertTrue(
            all(
                session["power_mode"] == "supervised_continuous"
                and session["requires_panel_power_cycle"] is False
                and session["j2_may_remain_on_before_session"] is True
                for session in manifest["shared_p0"]["sessions"]
            )
        )
        classification = manifest["classification"]
        self.assertFalse(classification["claim_created"])
        self.assertFalse(classification["authorization_created"])
        self.assertFalse(classification["device_io_performed"])
        self.assertFalse(classification["network_io_performed"])
        self.assertFalse(classification["real_executor_present"])

    def test_every_descriptive_target_has_a_known_pass_prior(self) -> None:
        actions = self.manifest["shared_p0"]["actions"]
        targets = [action for action in actions if action["identity"]["prior"] is not None]
        self.assertEqual(len(targets), 11)
        self.assertTrue(
            all(
                action["identity"]["prior"]["required_result_state"] == "PASS"
                for action in targets
            )
        )
        self.assertTrue(
            all(
                action["identity"]["automatic_retry"] is False
                and action["identity"]["automatic_recovery"] is False
                for action in actions
            )
        )

    def test_atlas_has_only_formal_codes_histograms_and_no_seam_roi(self) -> None:
        atlas = self.manifest["atlas"]
        self.assertEqual(atlas["formal_physical_codes"], list(COLOR_ORDER))
        self.assertFalse(atlas["unknown_codes_present"])
        self.assertEqual(atlas["asset_count"], 12)
        for asset in atlas["assets"]:
            histogram = asset["physical_code_histogram"]
            self.assertEqual(set(histogram), {str(code) for code in COLOR_ORDER})
            self.assertEqual(sum(histogram.values()), WIDTH * HEIGHT)
            for value in asset["rois"]:
                roi = value.get(
                    "pixel_roi", value.get("imaging_roi", value.get("measurement"))
                )
                if roi is not None:
                    self.assertFalse(roi["x0"] < WIDTH // 2 < roi["x1"])

    def test_mix_and_kernel_semantics_are_hardware_blocked(self) -> None:
        atlas = self.manifest["atlas"]
        mix = atlas["mix_contract"]
        self.assertEqual(mix["pixel_roi"], {"width": 64, "height": 48})
        self.assertFalse(mix["measurement_ready"])
        self.assertIn("pixel_pitch_or_physical_roi_size_not_reviewed", mix["blockers"])
        kernel = atlas["kernel_contract"]
        self.assertEqual(kernel["asset_type"], "camera-imaging-ESF-PSF")
        self.assertFalse(kernel["single_point_lab_is_kernel"])
        self.assertFalse(kernel["measurement_ready"])

    def test_d65_computation_is_distinct_from_camera_raw_lighting(self) -> None:
        modalities = self.manifest["measurement_modalities"]
        self.assertEqual(
            modalities["spectral_palette"]["result_illuminant"],
            "computational CIE D65",
        )
        self.assertFalse(
            modalities["spectral_palette"]["external_5000K_RAW_lighting_required"]
        )
        self.assertEqual(
            modalities["camera_spatial"]["external_lighting_cct_kelvin"],
            {"target": 5000, "tolerance": 100},
        )
        self.assertFalse(modalities["camera_spatial"]["may_create_calibrated_palette"])

    def test_default_transition_is_descriptive_and_cannot_emit_profile(self) -> None:
        plan = self.manifest["descriptive_transition_plan"]
        self.assertEqual(len(plan["expected_slots"]), 72)
        self.assertIn(
            "descriptive_transition_atlas_cannot_emit_measured_profile",
            plan["readiness"]["blockers"],
        )
        template = formal_transition_template()
        self.assertEqual(template["formal_actions"], 30)
        self.assertEqual(template["pilot_actions"], 12)
        self.assertEqual(template["formal_raw_slots"], 360)
        self.assertFalse(template["p0_materialized"])

    def test_manifest_tamper_and_flag_promotion_fail(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["atlas"]["assets"][0]["physical_code_histogram"]["0"] += 1
        with self.assertRaises(N5CampaignError):
            validate_compiled_manifest(tampered)
        promoted = copy.deepcopy(self.manifest)
        promoted["classification"]["calibrated_palette_created"] = True
        with self.assertRaises(N5CampaignError):
            validate_compiled_manifest(promoted)

    def test_compiler_performs_zero_socket_io(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("socket I/O forbidden")):
            manifest = compile_campaign_manifest()
        self.assertFalse(manifest["classification"]["network_io_performed"])


class N5FormalPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = compile_campaign_manifest(
            panel=_bound_panel(),
            formal_palette_cold_profile=_cold_profile(),
        )

    def test_materializes_eight_sessions_nine_actions_on_shared_p0(self) -> None:
        self.assertEqual(self.manifest["counts"]["declared_sessions"], 19)
        self.assertEqual(self.manifest["counts"]["declared_actions"], 31)
        self.assertEqual(len(self.manifest["formal_palette_routes"]), 6)
        formal_sessions = self.manifest["shared_p0"]["sessions"][-8:]
        self.assertTrue(
            all(
                session["power_mode"] == "panel_cold_cycle"
                and session["minimum_panel_power_off_seconds"] == 60.0
                for session in formal_sessions
            )
        )

    def test_formal_palette_count_equals_frozen_six_roi_run_contract(self) -> None:
        plan = self.manifest["formal_palette_plan"]
        template = self.manifest["formal_palette_template"]
        self.assertEqual(len(plan["expected_slots"]), 36)
        self.assertEqual(plan["required_samples_per_cell"], 6)
        self.assertEqual(template["formal_logical_strata"], 36)
        self.assertEqual(template["formal_raw_observations"], 36)
        for orientation in ("vertical", "horizontal"):
            for formal_run in range(1, 4):
                group = [
                    slot
                    for slot in plan["expected_slots"]
                    if slot["orientation"] == orientation
                    and slot["formal_run"] == formal_run
                ]
                self.assertEqual(len(group), 6)
        for code in COLOR_ORDER:
            controllers = [
                slot["controller"]
                for slot in plan["expected_slots"]
                if slot["code"] == code
            ]
            self.assertEqual(controllers.count("CS1"), 3)
            self.assertEqual(controllers.count("CS2"), 3)

    def test_vertical_non_colour_half_cannot_be_forged_as_observation_slot(self) -> None:
        plan = copy.deepcopy(self.manifest["formal_palette_plan"])
        plan.pop("integrity")
        slot = next(
            slot
            for slot in plan["expected_slots"]
            if slot["orientation"] == "vertical" and slot["code"] == 1
        )
        slot["controller"] = "CS2"
        slot["roi"] = {
            **slot["roi"],
            "x0": slot["roi"]["x0"] + WIDTH // 2,
            "x1": slot["roi"]["x1"] + WIDTH // 2,
        }
        with self.assertRaisesRegex(
            MeasurementAggregationError, "non-colour half"
        ):
            seal_measurement_plan(plan)


class N5FormalTransitionMaterializerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = compile_campaign_manifest(
            panel=_bound_panel(),
            formal_transition_recovery_profile=_recovery_profile(),
            formal_transition_power_profile=_cold_profile(),
        )

    def test_requires_both_reviewed_profiles(self) -> None:
        with self.assertRaisesRegex(N5CampaignError, "requires both"):
            compile_campaign_manifest(
                panel=_bound_panel(),
                formal_transition_recovery_profile=_recovery_profile(),
            )

    def test_profile_tamper_cannot_be_resealed_by_flag_only(self) -> None:
        profile = _recovery_profile()
        profile["qualification"]["all_known_initial_states_passed"] = False
        with self.assertRaises(N5CampaignError):
            validate_transition_recovery_profile(profile)

    def test_materializes_pilot_12_and_formal_30_fixed_actions(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["counts"]["declared_sessions"], 18)
        self.assertEqual(manifest["counts"]["declared_actions"], 64)
        routes = manifest["formal_transition_routes"]
        self.assertEqual(len(routes), 7)
        self.assertEqual(
            sum(route["action_count"] for route in routes if route["role"] == "pilot"),
            12,
        )
        self.assertEqual(
            sum(route["action_count"] for route in routes if route["role"] == "formal"),
            30,
        )
        self.assertEqual(len(manifest["formal_transition_plan"]["expected_slots"]), 360)
        self.assertTrue(manifest["formal_transition_template"]["p0_materialized"])

    def test_every_transition_action_is_adjacent_pass_whole_file_dependent(self) -> None:
        for route in self.manifest["formal_transition_routes"]:
            self.assertEqual(
                [action["phase"] for action in route["actions"]],
                ["recovery-1", "recovery-2", "recovery-3", "recovery-4", "initial", "target"],
            )
            for index, action in enumerate(route["actions"]):
                self.assertEqual(action["sequence_index"], index + 1)
                self.assertEqual(action["required_prior_result_state"], "PASS")
                self.assertTrue(
                    action["required_prior_result_whole_file_sha256_at_runtime"]
                )
                self.assertEqual(
                    action["missing_or_nonpass_prior_action"],
                    "STOP_NO_RETRY_NO_RECOVERY",
                )
                if index:
                    self.assertEqual(
                        action["immediate_prior_action_identity_sha256"],
                        route["actions"][index - 1]["action_identity_sha256"],
                    )
            self.assertTrue(
                route["abnormal_stop_contract"]["remaining_actions_become_ineligible"]
            )

    def test_materialized_sessions_are_reviewed_panel_cold_and_nonautomatic(self) -> None:
        sessions = self.manifest["shared_p0"]["sessions"][-7:]
        self.assertEqual(len(sessions), 7)
        self.assertTrue(
            all(
                session["power_mode"] == "panel_cold_cycle"
                and session["minimum_panel_power_off_seconds"] == 60.0
                and session["automatic_advance"] is False
                and session["final_power_off_required"] is True
                and len(session["action_identity_sha256s"]) == 6
                for session in sessions
            )
        )
        self.assertTrue(
            all(
                route["power_semantics"]
                == {
                    "reviewed_panel_cold_start_once_before_repeat": True,
                    "j2_remains_on_within_six_action_chain": True,
                    "manual_j2_cut_after_target_required": True,
                }
                for route in self.manifest["formal_transition_routes"]
            )
        )
        self.assertFalse(self.manifest["classification"]["authorization_created"])
        self.assertFalse(self.manifest["classification"]["claim_created"])


if __name__ == "__main__":
    unittest.main()
