from __future__ import annotations

from copy import deepcopy
import hashlib
from unittest import mock
import unittest

from host.visible_refresh_campaign import (
    LIMIT_PROFILE_KIND,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    result_file_sha256,
    seal_limit_profile,
)
from tools.g1_s1_n8_carryover_campaign import (
    EXPECTED_FROZEN_MANIFEST_CANONICAL_SHA256,
    EXPECTED_FROZEN_MANIFEST_FILE_SHA256,
    N8_SEQUENCE_IDS,
    N8CampaignError,
    build_binding_registry,
    build_measurement_registry,
    build_temperature_bin_plan,
    compile_n8_manifest,
    describe_n8_action,
    describe_n8_schedule,
    describe_panel_cold_variant,
    frozen_manifest_bytes,
    manifest_file_sha256,
    validate_n8_manifest,
)
from tools.g1_s1_rc2g_n2_photo_campaign import FIRMWARE_CONTRACT


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


PANEL = {
    "model": "MF1750-C73",
    "serial": "TEST-ONLY-PANEL-N8-001",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}


def _measurements() -> dict[str, object]:
    return build_measurement_registry(
        external_temperature_sensor_sha256=_hash("temperature-sensor"),
        external_temperature_calibration_sha256=_hash("temperature-calibration"),
        external_temperature_location_sha256=_hash("temperature-location"),
        external_temperature_u95_c=0.25,
        camera_body_sha256=_hash("camera-body"),
        camera_lens_sha256=_hash("camera-lens"),
        camera_mount_sha256=_hash("camera-mount"),
        fixed_exposure_profile_sha256=_hash("fixed-exposure"),
        camera_crop_sha256=_hash("fixed-roi"),
        illumination_sha256=_hash("illumination"),
        electrical_meter_sha256=_hash("electrical-meter"),
        timing_clock_sha256=_hash("timing-clock"),
    )


def _bindings() -> dict[str, object]:
    return build_binding_registry(
        supplier_limit_document_sha256=_hash("supplier-limit-document"),
        panel_instance_binding_sha256=_hash("panel-instance-binding"),
        firmware_build_binding_sha256=_hash("firmware-build-binding"),
    )


def _bins() -> dict[str, object]:
    return build_temperature_bin_plan(
        supplier_definition_sha256=_hash("supplier-temperature-bins"),
        low_minimum_c=0,
        low_maximum_c=15,
        nominal_minimum_c=15,
        nominal_maximum_c=30,
        high_minimum_c=30,
        high_maximum_c=45,
    )


def _profile(
    manifest: dict[str, object],
    *,
    expires_at: str = "2026-08-09T00:00:00Z",
    cumulative_count: int = 1,
    campaign_limit: int = 100,
) -> dict[str, object]:
    allowlist = []
    for action in manifest["p0_campaign"]["actions"]:
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
    return seal_limit_profile(
        {
            "schema_version": 1,
            "kind": LIMIT_PROFILE_KIND,
            "profile_id": "n8-test-only-reviewed-profile",
            "profile_version": "1.0.0",
            "panel": PANEL,
            "firmware": FIRMWARE_CONTRACT,
            "action_allowlist": allowlist,
            "limits": {
                "maximum_campaign_visible_refreshes": campaign_limit,
                "maximum_session_visible_refreshes": 10,
                "maximum_consecutive_visible_refreshes": 10,
                "minimum_interval_seconds": 0,
                "minimum_cooldown_seconds": 0,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 45,
                "maximum_post_refresh_temperature_c": 50,
            },
            "usage": {
                "cumulative_visible_refresh_count": cumulative_count,
                "session_visible_refresh_count": min(cumulative_count, 1),
                "consecutive_visible_refresh_count": min(cumulative_count, 1),
                "last_visible_refresh_completed_at": (
                    "2026-08-08T10:30:00Z" if cumulative_count else None
                ),
                "snapshot_at": "2026-08-08T11:00:00Z",
                "evidence_sha256": _hash("usage-evidence"),
            },
            "validity": {
                "valid_from": "2026-08-08T00:00:00Z",
                "expires_at": expires_at,
            },
            "review": {
                "approved": True,
                "reviewer_id": "test-only-reviewer",
                "reviewed_at": "2026-08-07T23:00:00Z",
                "review_artifact_sha256": _hash("supplier-limit-document"),
            },
        }
    )


def _pass_result(action_sha: str, minute: int = 20) -> dict[str, object]:
    return build_result_record(
        action_identity_sha256=action_sha,
        state=ResultState.PASS,
        completed_at=f"2026-08-08T10:{minute:02d}:00Z",
        evidence_manifest_sha256=_hash(f"evidence:{action_sha}"),
        post_request_count=1,
        details="test-only immutable result",
    )


class N8CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = compile_n8_manifest()
        first = compile_n8_manifest(
            panel=PANEL,
            measurement_registry=_measurements(),
            binding_registry=_bindings(),
            temperature_bin_plan=_bins(),
        )
        profile = _profile(first)
        cls.ready_contract = compile_n8_manifest(
            panel=PANEL,
            measurement_registry=_measurements(),
            binding_registry=_bindings(),
            temperature_bin_plan=_bins(),
            limit_profile=profile,
        )

    def test_frozen_source_schedule_counts_and_hashes(self) -> None:
        manifest = self.frozen
        self.assertEqual(manifest["source_n2"]["canonical_sha256"], "976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b")
        self.assertEqual(manifest["source_n2"]["source_input_sha256"], "04034fbc1836791e0d1370d70d1871f174407b877ca24563f6cb0cf97a63eb07")
        self.assertEqual(manifest["frames"]["MAP"]["frame"]["sha256"], "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36")
        self.assertEqual(manifest["frames"]["Q1"]["frame"]["sha256"], "7aa33f337903b93ba094265e212909f5986ab48eebb0a2dd352b7571a6ea7c96")
        self.assertEqual(manifest["frames"]["Q4"]["frame"]["sha256"], "4183b84b40578589938531076eb92845aa53f533c6e29ee5a54986903c7e8f86")
        self.assertEqual(manifest["compiler_effects"]["visible_action_declarations"], 15)
        self.assertEqual(manifest["compiler_effects"]["sessions"], 5)
        self.assertEqual(manifest["compiler_effects"]["dependent_prior_result_bindings"], 10)
        self.assertEqual(
            manifest["integrity"]["canonical_sha256"],
            EXPECTED_FROZEN_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            manifest_file_sha256(manifest),
            EXPECTED_FROZEN_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(frozen_manifest_bytes()).hexdigest(),
            EXPECTED_FROZEN_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(manifest["analysis_contract"]["qualification_state"], "NOT_QUALIFIED")
        self.assertFalse(manifest["analysis_contract"]["population_inference_allowed"])

    def test_aba_warm_and_temperature_sequences_are_prebuilt(self) -> None:
        sequences = self.frozen["sequences"]
        self.assertEqual(
            [action["role"] for action in sequences[0]["actions"]],
            ["MAP", "A1", "B", "A2"],
        )
        self.assertEqual(
            [action["frame_source_id"] for action in sequences[0]["actions"]],
            ["MAP", "Q1", "Q4", "Q1"],
        )
        self.assertEqual(
            [action["role"] for action in sequences[1]["actions"]],
            ["MAP", "W1", "W2", "W3", "W4"],
        )
        self.assertEqual(
            [sequence["temperature_bin_id"] for sequence in sequences[2:]],
            ["supplier-low", "supplier-nominal", "supplier-high"],
        )
        self.assertTrue(
            all(
                [action["role"] for action in sequence["actions"]]
                == ["MAP", "TARGET"]
                for sequence in sequences[2:]
            )
        )

    def test_every_action_has_unique_p0_identity_and_workspace_global_claim(self) -> None:
        actions = self.frozen["p0_campaign"]["actions"]
        identities = [action["action_identity_sha256"] for action in actions]
        claims = [action["claim"]["filename"] for action in actions]
        self.assertEqual(len(set(identities)), 15)
        self.assertEqual(len(set(claims)), 15)
        self.assertTrue(
            all(
                action["claim"]["partitioned_by_campaign_id"] is False
                and action["claim"]["create_before_network"] is True
                for action in actions
            )
        )
        for sequence in self.frozen["sequences"]:
            for ordinal, action in enumerate(sequence["actions"]):
                self.assertEqual(action["prior_result_requirement"]["required"], ordinal > 0)
                if ordinal:
                    self.assertEqual(
                        action["prior_result_requirement"]["required_result_state"],
                        ResultState.PASS.value,
                    )

    def test_normal_sessions_do_not_force_j2_cycle(self) -> None:
        warm, fresh, cold = (
            self.frozen["power_semantics"][name]
            for name in (
                "supervised_continuous",
                "controller_fresh_boot",
                "panel_cold_cycle",
            )
        )
        self.assertFalse(warm["controller_fresh_boot_required"])
        self.assertTrue(warm["j2_may_remain_on"])
        self.assertTrue(fresh["controller_fresh_boot_required"])
        self.assertFalse(fresh["panel_power_cycle_required"])
        self.assertTrue(fresh["j2_may_remain_on"])
        self.assertEqual(cold["used_by_default"], [])
        self.assertTrue(cold["requires_current_reviewed_limit_profile"])
        for session in self.frozen["p0_campaign"]["sessions"]:
            self.assertFalse(session["requires_panel_power_cycle"])
            self.assertTrue(session["j2_may_remain_on_before_session"])

    def test_missing_supplier_limits_external_temperature_and_bindings_fail_closed(self) -> None:
        blockers = self.frozen["hardware_readiness"]["blockers"]
        for required in (
            "missing_supplier_limit:maximum_campaign_visible_refreshes",
            "missing_supplier_limit:maximum_session_visible_refreshes",
            "missing_supplier_limit:maximum_consecutive_visible_refreshes",
            "missing_supplier_limit:minimum_interval_seconds",
            "missing_supplier_limit:minimum_cooldown_seconds",
            "missing_external_temperature:sensor_asset_sha256",
            "missing_binding:panel_instance_binding_sha256",
            "missing_binding:firmware_build_binding_sha256",
        ):
            self.assertIn(required, blockers)
        readiness = self.frozen["hardware_readiness"]
        self.assertFalse(readiness["internal_temperature_available"])
        self.assertFalse(readiness["swc_temperature_available"])
        self.assertTrue(readiness["inference_from_internal_or_swc_forbidden"])
        self.assertFalse(readiness["ready"])

    def test_describe_binds_exact_prior_pass_result_and_remains_zero_io(self) -> None:
        sequence = self.ready_contract["sequences"][0]
        primer, a1 = sequence["actions"][:2]
        primer_result = _pass_result(primer["action_identity_sha256"])
        description = describe_n8_action(
            self.ready_contract,
            action_identity_sha256=a1["action_identity_sha256"],
            evaluated_at="2026-08-08T12:00:00Z",
            prior_result=primer_result,
            prior_result_sha256=result_file_sha256(primer_result),
        )
        binding = description["p0_description"]["prior_result_binding"]
        self.assertEqual(binding["result_file_sha256"], result_file_sha256(primer_result))
        self.assertEqual(binding["observed_state"], ResultState.PASS.value)
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(description["device_io_performed"])

    def test_replay_cross_sequence_and_tamper_are_rejected(self) -> None:
        aba = self.ready_contract["sequences"][0]
        warm = self.ready_contract["sequences"][1]
        aba_primer, a1 = aba["actions"][:2]
        wrong = _pass_result(warm["actions"][0]["action_identity_sha256"])
        with self.assertRaises(N8CampaignError):
            describe_n8_action(
                self.ready_contract,
                action_identity_sha256=a1["action_identity_sha256"],
                evaluated_at="2026-08-08T12:00:00Z",
                prior_result=wrong,
                prior_result_sha256=result_file_sha256(wrong),
            )
        right = _pass_result(aba_primer["action_identity_sha256"])
        with self.assertRaises(N8CampaignError):
            describe_n8_action(
                self.ready_contract,
                action_identity_sha256=a1["action_identity_sha256"],
                evaluated_at="2026-08-08T12:00:00Z",
                prior_result=right,
                prior_result_sha256="f" * 64,
            )
        with self.assertRaises(N8CampaignError):
            describe_n8_schedule(
                self.ready_contract,
                sequence_id=N8_SEQUENCE_IDS[0],
                evaluated_at="2026-08-08T12:00:00Z",
                result_bindings={
                    warm["actions"][0]["action_identity_sha256"]: {
                        "result": wrong,
                        "result_file_sha256": result_file_sha256(wrong),
                    }
                },
            )
        tampered = deepcopy(self.frozen)
        tampered["sequences"][0]["actions"][1]["frame_sha256"] = "0" * 64
        unsigned = dict(tampered)
        unsigned.pop("integrity")
        tampered["integrity"]["canonical_sha256"] = hashlib.sha256(
            canonical_json_bytes(unsigned)
        ).hexdigest()
        with self.assertRaises(N8CampaignError):
            validate_n8_manifest(tampered)

    def test_expired_and_exhausted_profiles_stay_blocked(self) -> None:
        template = compile_n8_manifest(
            panel=PANEL,
            measurement_registry=_measurements(),
            binding_registry=_bindings(),
            temperature_bin_plan=_bins(),
        )
        root_action = template["sequences"][0]["actions"][0]["action_identity_sha256"]
        expired = _profile(template, expires_at="2026-08-08T11:59:59Z")
        expired_description = describe_n8_action(
            template,
            action_identity_sha256=root_action,
            evaluated_at="2026-08-08T12:00:00Z",
            limit_profile=expired,
        )
        self.assertIn("profile_expired", expired_description["blockers"])
        exhausted = _profile(template, cumulative_count=15, campaign_limit=15)
        exhausted_description = describe_n8_action(
            template,
            action_identity_sha256=root_action,
            evaluated_at="2026-08-08T12:00:00Z",
            limit_profile=exhausted,
        )
        self.assertIn(
            "campaign_visible_refresh_limit_exhausted",
            exhausted_description["blockers"],
        )

    def test_abnormal_result_stops_scheduler_without_retry_or_recovery(self) -> None:
        first = self.ready_contract["sequences"][0]["actions"][0]
        abnormal = build_result_record(
            action_identity_sha256=first["action_identity_sha256"],
            state=ResultState.FAIL,
            completed_at="2026-08-08T10:20:00Z",
            evidence_manifest_sha256=_hash("abnormal-evidence"),
            post_request_count=1,
            details="test-only abnormal result",
        )
        plan = describe_n8_schedule(
            self.ready_contract,
            sequence_id=N8_SEQUENCE_IDS[0],
            evaluated_at="2026-08-08T12:00:00Z",
            result_bindings={
                first["action_identity_sha256"]: {
                    "result": abnormal,
                    "result_file_sha256": result_file_sha256(abnormal),
                }
            },
        )
        self.assertEqual(plan["terminal_state"], ResultState.UNKNOWN_DO_NOT_RETRY.value)
        self.assertTrue(plan["stop_remaining_actions"])
        self.assertEqual(plan["remaining_action_identity_sha256s"], [])
        self.assertFalse(plan["automatic_advance"])
        self.assertFalse(plan["claim_created"])
        self.assertFalse(plan["authorization_created"])

    def test_panel_cold_is_description_only_and_never_reuses_default_sessions(self) -> None:
        description = describe_panel_cold_variant(
            self.ready_contract,
            evaluated_at="2026-08-08T12:00:00Z",
            minimum_measured_panel_off_seconds=45,
        )
        self.assertEqual(description["power_mode"], "panel_cold_cycle")
        self.assertTrue(description["requires_panel_power_cycle"])
        self.assertFalse(description["j2_may_remain_on_before_session"])
        self.assertIn("distinct_panel_cold_p0_session_not_compiled", description["blockers"])
        self.assertFalse(description["hardware_ready"])
        with self.assertRaises(N8CampaignError):
            describe_panel_cold_variant(
                self.ready_contract,
                evaluated_at="2026-08-08T12:00:00Z",
                minimum_measured_panel_off_seconds=0,
            )

    def test_compile_and_describe_have_no_network_or_device_path(self) -> None:
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")), mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("network")
        ):
            manifest = compile_n8_manifest()
            first = manifest["sequences"][0]["actions"][0]["action_identity_sha256"]
            description = describe_n8_action(
                manifest,
                action_identity_sha256=first,
                evaluated_at="2026-08-08T12:00:00Z",
            )
        self.assertEqual(manifest["compiler_effects"]["network_requests"], 0)
        self.assertEqual(manifest["compiler_effects"]["device_operations"], 0)
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(description["device_io_performed"])


if __name__ == "__main__":
    unittest.main()
