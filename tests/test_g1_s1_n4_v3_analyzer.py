from __future__ import annotations

from copy import deepcopy
import hashlib
from unittest import mock
import unittest

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from tests.n4_v3_bundle_fixture import build_finalized_bundle, fixture_sha256
from tools import g1_s1_n4_v3_execution_contract as execution
from tools import g1_s1_root_cause_2x2_v3 as v3
from tools.g1_s1_n4_v3_analyzer import (
    CELL_ORDER,
    EXPECTED_CONTRACT_CANONICAL_SHA256,
    EXPECTED_CONTRACT_FILE_SHA256,
    N4V3AnalysisError,
    OBSERVATION_HASH_SCOPE,
    analyze_n4_v3,
    build_n4_v3_cell_observation,
    compile_n4_v3_analysis_contract,
    contract_file_sha256,
    frozen_contract_bytes,
    validate_n4_v3_analysis_contract,
    validate_n4_v3_cell_observation,
    validate_n4_v3_report,
)


def _resign_observation(value: dict[str, object]) -> None:
    unsigned = dict(value)
    unsigned.pop("integrity")
    value["integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest(),
        "canonical_sha256_scope": OBSERVATION_HASH_SCOPE,
    }


class N4V3AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.execution_contract = execution.compile_n4_v3_execution_contract()
        cls.contract = compile_n4_v3_analysis_contract()
        cls.bundle_pairs: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
        cls.observations: list[dict[str, object]] = []
        score_offsets = (0.00, 0.02, 0.06, 0.10)
        electrical_offsets = (0.000, 0.001, 0.002, 0.004)
        for cell, score_offset, electrical_offset in zip(
            cls.contract["cell_contracts"],
            score_offsets,
            electrical_offsets,
            strict=True,
        ):
            cell_id = cell["cell_id"]
            map_bundle = build_finalized_bundle(
                f"{cell_id}-map-primer",
                contract=cls.execution_contract,
                electrical_offset=electrical_offset,
            )
            target_bundle = build_finalized_bundle(
                f"{cell_id}-target",
                contract=cls.execution_contract,
                prior_bundle=map_bundle,
                score_offset=score_offset,
                electrical_offset=electrical_offset,
            )
            cls.bundle_pairs[cell_id] = (map_bundle, target_bundle)
            cls.observations.append(
                build_n4_v3_cell_observation(
                    cls.contract,
                    cell_id=cell_id,
                    map_bundle=map_bundle,
                    target_bundle=target_bundle,
                )
            )

    def _complete_observations(self) -> list[dict[str, object]]:
        return deepcopy(self.observations)

    def test_frozen_contract_binds_shared_source_and_execution_envelopes(self) -> None:
        contract = self.contract
        self.assertEqual(
            contract["integrity"]["canonical_sha256"],
            EXPECTED_CONTRACT_CANONICAL_SHA256,
        )
        self.assertEqual(contract_file_sha256(contract), EXPECTED_CONTRACT_FILE_SHA256)
        self.assertEqual(
            hashlib.sha256(frozen_contract_bytes()).hexdigest(),
            EXPECTED_CONTRACT_FILE_SHA256,
        )
        self.assertEqual(
            contract["execution_contract_canonical_sha256"],
            execution.EXPECTED_CONTRACT_CANONICAL_SHA256,
        )
        self.assertEqual(
            contract["execution_contract_file_sha256"],
            execution.EXPECTED_CONTRACT_FILE_SHA256,
        )
        source = contract["source_v3"]
        self.assertEqual(
            source["manifest_canonical_sha256"],
            v3.EXPECTED_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(source["manifest_file_sha256"], v3.EXPECTED_MANIFEST_FILE_SHA256)
        self.assertEqual(
            source["proof_canonical_sha256"],
            v3.EXPECTED_PROOF_CANONICAL_SHA256,
        )
        self.assertEqual(source["proof_file_sha256"], v3.EXPECTED_PROOF_FILE_SHA256)

    def test_power_supplement_changes_only_session_envelopes_not_actions(self) -> None:
        source = self.contract["source_p0_campaign"]
        campaign = self.contract["p0_campaign"]
        self.assertEqual(source["actions"], campaign["actions"])
        self.assertTrue(all(item["final_power_off_required"] for item in source["sessions"]))
        self.assertTrue(
            all(item["final_power_off_required"] is False for item in campaign["sessions"])
        )
        power = self.contract["power_semantics"]
        self.assertTrue(power["j2_may_remain_on_between_cells"])
        self.assertTrue(power["controller_fresh_boot_required_before_each_map_primer"])
        self.assertTrue(power["power_off_required_after_campaign_or_abnormality"])
        self.assertTrue(
            power["power_off_required_before_firmware_or_configuration_change"]
        )
        self.assertFalse(power["action_identities_changed"])

    def test_cells_bind_exact_map_target_frame_preview_and_new_sessions(self) -> None:
        campaign = self.contract["p0_campaign"]
        expected_frames = {
            "low-balanced": "784ebc8ae122ff3a70ca3319373c0ec9050809f05fbfeb591178b066d09b1c10",
            "low-unbalanced": "1987c3673d1cf50be9c4e5922632e361acd08c5ab106387a3a71e83d11c81858",
            "high-balanced": "ffbde85223cf67e7df728684e5e0a17db84b5ab72e84865ba08a60403b1434b8",
            "high-unbalanced": "3279144da2af2b409bf5b5fd22274c4ccd3995229bacc2075b8cbf61a01a84d0",
        }
        expected_previews = {
            "low-balanced": "bb5bb62286429217a65a85a9076418afaa6587b34f745e1ec3332bee10eacd15",
            "low-unbalanced": "c8a89c15b0d3300ff768629f5e846678f11f5e238f75acd16d3a1ea2486c835e",
            "high-balanced": "cf183f80631d10036faa1f9b5aa247a3a25e5e29b1a5a2fdd7de7c11658f1ad0",
            "high-unbalanced": "b20dfbc15e7e6393177d7a1793896fc6d7d66ab975fd325098be8d21ce4fb6fd",
        }
        self.assertEqual(
            [cell["cell_id"] for cell in self.contract["cell_contracts"]],
            list(CELL_ORDER),
        )
        for index, cell in enumerate(self.contract["cell_contracts"]):
            primer, target = campaign["actions"][2 * index : 2 * index + 2]
            session = campaign["sessions"][index]
            self.assertEqual(
                target["identity"]["prior"]["action_identity_sha256"],
                primer["action_identity_sha256"],
            )
            self.assertEqual(
                target["identity"]["frame"]["sha256"],
                expected_frames[cell["cell_id"]],
            )
            self.assertEqual(
                cell["strict_preview_sha256"],
                expected_previews[cell["cell_id"]],
            )
            self.assertEqual(session["power_mode"], "controller_fresh_boot")
            self.assertFalse(session["final_power_off_required"])
            self.assertFalse(cell["j2_disconnect_after_nominal_cell_required"])

    def test_complete_deep_evidence_produces_descriptive_separated_analysis(self) -> None:
        report = analyze_n4_v3(
            self.contract,
            observations=self._complete_observations(),
        )
        self.assertTrue(report["complete"])
        self.assertTrue(report["execution_evidence_verified"])
        self.assertEqual(report["verified_visible_action_count"], 8)
        self.assertEqual(report["observed_cell_count"], 4)
        self.assertEqual(
            report["terminal_state"],
            "EVIDENCE_CHAIN_COMPLETE_DESCRIPTIVE_ONLY",
        )
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertIsNone(report["visual_electrical_joint_conclusion"])
        self.assertEqual(
            set(report["visual_analysis"]),
            {"fidelity_score", "ghosting_score", "artifact_severity_score"},
        )
        self.assertEqual(
            set(report["electrical_analysis"]),
            {
                "map_peak_current_a",
                "target_peak_current_a",
                "map_job_duration_ms",
                "target_job_duration_ms",
                "session_max_temperature_c",
                "target_voltage_droop_v",
            },
        )
        for group in (report["visual_analysis"], report["electrical_analysis"]):
            for metric in group.values():
                self.assertEqual(metric["n_per_cell"], 1)
                self.assertIsNone(metric["p95"])
                self.assertIsNone(metric["p99"])
                self.assertEqual(metric["qualification_state"], "NOT_QUALIFIED")
        self.assertTrue(
            report["classification"]["source_execution_evidence_deep_validated"]
        )
        self.assertFalse(report["inference_contract"]["causal_attribution_allowed"])
        self.assertFalse(report["inference_contract"]["hardware_qualification_allowed"])

    def test_factorial_main_and_interaction_fields_follow_preregistration(self) -> None:
        report = analyze_n4_v3(
            self.contract,
            observations=self._complete_observations(),
        )
        effect = report["visual_analysis"]["fidelity_score"]
        values = effect["cell_values"]
        lb = values["low-balanced"]
        lu = values["low-unbalanced"]
        hb = values["high-balanced"]
        hu = values["high-unbalanced"]
        self.assertAlmostEqual(
            effect["spatial_frequency_main_effect_high_minus_low"],
            ((hb + hu) - (lb + lu)) / 2,
        )
        self.assertAlmostEqual(
            effect["half_load_main_effect_unbalanced_minus_balanced"],
            ((lu + hu) - (lb + hb)) / 2,
        )
        self.assertAlmostEqual(
            effect["interaction_effect_coded_level_means"],
            ((hu + lb) - (hb + lu)) / 2,
        )
        self.assertAlmostEqual(
            effect["interaction_difference_of_differences"],
            (hu - hb) - (lu - lb),
        )
        self.assertTrue(effect["interaction_scaling_check"])

    def test_loose_results_are_not_an_input_and_missing_cell_is_rejected(self) -> None:
        cell = self.contract["cell_contracts"][0]
        map_bundle, target_bundle = self.bundle_pairs[cell["cell_id"]]
        with self.assertRaises(TypeError):
            build_n4_v3_cell_observation(
                self.contract,
                cell_id=cell["cell_id"],
                map_result=map_bundle["result"],
                target_result=target_bundle["result"],
            )
        with self.assertRaisesRegex(N4V3AnalysisError, "missing cells"):
            analyze_n4_v3(
                self.contract,
                observations=self._complete_observations()[:3],
            )

    def test_cross_cell_prior_and_replay_are_rejected(self) -> None:
        first, second = self.contract["cell_contracts"][:2]
        first_map, _ = self.bundle_pairs[first["cell_id"]]
        _, second_target = self.bundle_pairs[second["cell_id"]]
        with self.assertRaisesRegex(N4V3AnalysisError, "finalized runner evidence"):
            build_n4_v3_cell_observation(
                self.contract,
                cell_id=second["cell_id"],
                map_bundle=first_map,
                target_bundle=second_target,
            )
        first_observation = self._complete_observations()[0]
        with self.assertRaises(N4V3AnalysisError):
            analyze_n4_v3(
                self.contract,
                observations=[first_observation, first_observation],
            )

    def test_finalization_and_derived_observation_tamper_fail_closed(self) -> None:
        cell = self.contract["cell_contracts"][0]
        map_bundle, target_bundle = deepcopy(self.bundle_pairs[cell["cell_id"]])
        target_bundle["finalization"]["claim_file_sha256"] = "0" * 64
        with self.assertRaisesRegex(N4V3AnalysisError, "finalized runner evidence"):
            build_n4_v3_cell_observation(
                self.contract,
                cell_id=cell["cell_id"],
                map_bundle=map_bundle,
                target_bundle=target_bundle,
            )

        observation = self._complete_observations()[0]
        observation["visual"]["fidelity_score"] = 0.0
        _resign_observation(observation)
        with self.assertRaisesRegex(N4V3AnalysisError, "derived measurement"):
            validate_n4_v3_cell_observation(observation, self.contract)

    def test_any_target_abnormality_is_unknown_and_stops_remaining_cells(self) -> None:
        cell = self.contract["cell_contracts"][0]
        map_bundle, _ = self.bundle_pairs[cell["cell_id"]]
        target_bundle = build_finalized_bundle(
            f"{cell['cell_id']}-target",
            contract=self.execution_contract,
            prior_bundle=map_bundle,
            state=ResultState.FAIL,
        )
        abnormal = build_n4_v3_cell_observation(
            self.contract,
            cell_id=cell["cell_id"],
            map_bundle=map_bundle,
            target_bundle=target_bundle,
        )
        report = analyze_n4_v3(self.contract, observations=[abnormal])
        self.assertEqual(report["terminal_state"], ResultState.UNKNOWN_DO_NOT_RETRY.value)
        self.assertTrue(report["stop_remaining_cells"])
        self.assertTrue(report["execution_evidence_verified"])
        self.assertIsNone(report["visual_analysis"])
        self.assertIsNone(report["electrical_analysis"])
        self.assertEqual(report["qualification_state"], "NOT_QUALIFIED")
        self.assertIn("target_result_state:FAIL", abnormal["protocol_abnormal_reasons"])
        self.assertIn(
            "visual_not_pass:target_fidelity_pass",
            abnormal["visual_abnormal_reasons"],
        )

    def test_cross_cell_method_drift_is_rejected_before_factorial_arithmetic(self) -> None:
        observations = self._complete_observations()
        cell = self.contract["cell_contracts"][1]
        map_bundle, _ = self.bundle_pairs[cell["cell_id"]]
        target_bundle = build_finalized_bundle(
            f"{cell['cell_id']}-target",
            contract=self.execution_contract,
            prior_bundle=map_bundle,
            score_offset=0.02,
            overrides={
                "visual": {
                    "roi_definition_sha256": fixture_sha256("different-roi")
                }
            },
        )
        observations[1] = build_n4_v3_cell_observation(
            self.contract,
            cell_id=cell["cell_id"],
            map_bundle=map_bundle,
            target_bundle=target_bundle,
        )
        with self.assertRaisesRegex(N4V3AnalysisError, "visual method/assets changed"):
            analyze_n4_v3(self.contract, observations=observations)

    def test_fixed_camera_bundles_are_derived_without_loose_camera_claims(self) -> None:
        cell = self.contract["cell_contracts"][0]
        camera_override = {
            "camera": {
                "observation_kind": "fixed-camera",
                "fixed_exposure_profile_sha256": fixture_sha256("fixed-exposure-v1"),
            }
        }
        map_bundle = build_finalized_bundle(
            f"{cell['cell_id']}-map-primer",
            contract=self.execution_contract,
            overrides=camera_override,
        )
        target_bundle = build_finalized_bundle(
            f"{cell['cell_id']}-target",
            contract=self.execution_contract,
            prior_bundle=map_bundle,
            overrides=camera_override,
        )
        observation = build_n4_v3_cell_observation(
            self.contract,
            cell_id=cell["cell_id"],
            map_bundle=map_bundle,
            target_bundle=target_bundle,
        )
        self.assertEqual(observation["visual"]["observation_kind"], "fixed-camera")
        self.assertIsNotNone(observation["visual"]["capture_file_sha256"])
        self.assertTrue(observation["execution_evidence_verified"])

    def test_report_and_contract_tamper_fail_closed(self) -> None:
        report = analyze_n4_v3(
            self.contract,
            observations=self._complete_observations(),
        )
        tampered_report = deepcopy(report)
        tampered_report["qualification_state"] = "QUALIFIED"
        with self.assertRaises(N4V3AnalysisError):
            validate_n4_v3_report(tampered_report, self.contract)
        tampered_contract = deepcopy(self.contract)
        tampered_contract["power_semantics"]["j2_may_remain_on_between_cells"] = False
        with self.assertRaises(N4V3AnalysisError):
            validate_n4_v3_analysis_contract(tampered_contract)
        with self.assertRaisesRegex(N4V3AnalysisError, "only the shared frozen"):
            compile_n4_v3_analysis_contract(
                p0_campaign=self.contract["source_p0_campaign"]
            )

    def test_analysis_path_performs_no_network_device_claim_or_authorization(self) -> None:
        cell = self.contract["cell_contracts"][0]
        map_bundle, target_bundle = self.bundle_pairs[cell["cell_id"]]
        with (
            mock.patch("socket.create_connection", side_effect=AssertionError("network")),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")),
        ):
            observation = build_n4_v3_cell_observation(
                self.contract,
                cell_id=cell["cell_id"],
                map_bundle=map_bundle,
                target_bundle=target_bundle,
            )
        self.assertEqual(
            observation["analyzer_effects"],
            {
                "claim_created": False,
                "authorization_created": False,
                "network_io_performed": False,
                "device_io_performed": False,
                "visible_refreshes": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
