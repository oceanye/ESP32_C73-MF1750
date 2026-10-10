from __future__ import annotations

from copy import deepcopy
import socket
import subprocess
import unittest
from unittest import mock

from host.visible_refresh_campaign import (
    CAMPAIGN_KIND,
    LIMIT_PROFILE_KIND,
    RESULT_STATES,
    SESSION_KIND,
    CampaignContractError,
    ResultState,
    build_fixed_action_declaration,
    build_result_record,
    build_session_contract,
    canonical_json_bytes,
    describe_action_offline,
    evaluate_limit_profile,
    result_file_sha256,
    seal_campaign_contract,
    seal_limit_profile,
    validate_action_description,
    validate_campaign_contract,
    validate_fixed_action_declaration,
    validate_limit_profile,
    validate_result_record,
    workspace_global_claim_declaration,
)


PANEL = {
    "model": "MF1750-C73",
    "serial": "PANEL-P0-001",
    "board_id": "ESP32-C73-P0",
    "pcb_revision": "rev-a",
}
FIRMWARE = {
    "source_commit": "1" * 40,
    "build_tag": "p0-offline-contract-test",
    "binary_sha256": "2" * 64,
    "driver_api": "mf1750-http-v1",
}
CLASSIFICATION = {
    "offline_compiled": True,
    "hardware_execution_authorized": False,
    "automatic_execution": False,
    "automatic_retry": False,
    "automatic_recovery": False,
    "network_io_performed": False,
    "device_io_performed": False,
}


def _frame(seed: int) -> dict[str, object]:
    digits = "0123456789abcdef"
    frame_digit = digits[seed % len(digits)]
    cs1_digit = digits[(seed + 1) % len(digits)]
    cs2_digit = digits[(seed + 2) % len(digits)]
    return {
        "width": 1024,
        "height": 600,
        "bits_per_pixel": 4,
        "bytes": 307200,
        "sha256": frame_digit * 64,
        "fnv1a": f"0x{seed:08X}",
        "controllers": [
            {
                "controller": "CS1",
                "mapping": {
                    "source_half": 0,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": cs1_digit * 64,
                "dtm_fnv1a": f"0x{seed + 1:08X}",
            },
            {
                "controller": "CS2",
                "mapping": {
                    "source_half": 1,
                    "flip_x": False,
                    "flip_y": False,
                    "nibble_swap": False,
                },
                "dtm_bytes": 153600,
                "dtm_sha256": cs2_digit * 64,
                "dtm_fnv1a": f"0x{seed + 2:08X}",
            },
        ],
    }


def _fixture() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    primer = build_fixed_action_declaration(
        campaign_id="campaign-p0",
        session_id="session-a",
        cell_id="cell-a",
        action_id="cell-a-primer",
        phase="primer",
        frame=_frame(1),
    )
    target = build_fixed_action_declaration(
        campaign_id="campaign-p0",
        session_id="session-a",
        cell_id="cell-a",
        action_id="cell-a-target",
        phase="target",
        frame=_frame(4),
        prior_action_identity_sha256=primer["action_identity_sha256"],
        prior_scope="same_cell",
        minimum_interval_since_prior_seconds=30,
    )
    actions = [primer, target]
    session = build_session_contract(
        session_id="session-a",
        cell_id="cell-a",
        power_mode="controller_fresh_boot",
        planned_cooldown_seconds=60,
        final_power_off_required=False,
        action_identity_sha256s=[
            action["action_identity_sha256"] for action in actions
        ],
    )
    campaign = seal_campaign_contract(
        {
            "schema_version": 1,
            "kind": CAMPAIGN_KIND,
            "campaign_id": "campaign-p0",
            "panel": PANEL,
            "firmware": FIRMWARE,
            "actions": actions,
            "sessions": [session],
            "classification": CLASSIFICATION,
        }
    )
    profile = seal_limit_profile(_profile_payload(actions))
    return campaign, profile, actions


def _profile_payload(actions: list[dict[str, object]]) -> dict[str, object]:
    allowlist = []
    for action in actions:
        identity = action["identity"]
        allowlist.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": identity["request"]["method"],
                "endpoint": identity["request"]["endpoint"],
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    return {
        "schema_version": 1,
        "kind": LIMIT_PROFILE_KIND,
        "profile_id": "p0-reviewed-limits",
        "profile_version": "1.0.0",
        "panel": PANEL,
        "firmware": FIRMWARE,
        "action_allowlist": allowlist,
        "limits": {
            "maximum_campaign_visible_refreshes": 2,
            "maximum_session_visible_refreshes": 2,
            "maximum_consecutive_visible_refreshes": 2,
            "minimum_interval_seconds": 20,
            "minimum_cooldown_seconds": 60,
            "minimum_start_temperature_c": 10,
            "maximum_start_temperature_c": 40,
            "maximum_post_refresh_temperature_c": 45,
        },
        "usage": {
            "cumulative_visible_refresh_count": 0,
            "session_visible_refresh_count": 0,
            "consecutive_visible_refresh_count": 0,
            "last_visible_refresh_completed_at": None,
            "snapshot_at": "2026-08-07T11:55:00Z",
            "evidence_sha256": "5" * 64,
        },
        "validity": {
            "valid_from": "2026-08-01T00:00:00Z",
            "expires_at": "2026-09-01T00:00:00Z",
        },
        "review": {
            "approved": True,
            "reviewer_id": "offline-reviewer",
            "reviewed_at": "2026-07-31T12:00:00Z",
            "review_artifact_sha256": "3" * 64,
        },
    }


class VisibleRefreshCampaignContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campaign, self.profile, self.actions = _fixture()

    def _pass_result(self, action_index: int = 0) -> dict[str, object]:
        return build_result_record(
            action_identity_sha256=self.actions[action_index][
                "action_identity_sha256"
            ],
            state=ResultState.PASS,
            completed_at="2026-08-07T12:01:00Z",
            evidence_manifest_sha256="4" * 64,
            post_request_count=1,
            details="supervised fixture",
        )

    def test_builders_and_canonical_identities_are_deterministic(self) -> None:
        campaign_2, profile_2, actions_2 = _fixture()
        self.assertEqual(self.actions, actions_2)
        self.assertEqual(self.campaign, campaign_2)
        self.assertEqual(self.profile, profile_2)
        self.assertEqual(
            canonical_json_bytes(self.campaign), canonical_json_bytes(campaign_2)
        )

    def test_bodyless_fixed_action_is_limited_to_diagnostic_endpoint(self) -> None:
        action = build_fixed_action_declaration(
            campaign_id="campaign-bodyless-diagnostic",
            session_id="session-a",
            cell_id="cell-a",
            action_id="fixed-diagnostic",
            phase="diagnostic",
            frame=_frame(7),
            endpoint="/api/diagnostic/fixed-action",
            request_body="none",
        )
        self.assertEqual(action["identity"]["request"]["body"], "none")
        with self.assertRaisesRegex(
            CampaignContractError, "bodyless fixed action"
        ):
            build_fixed_action_declaration(
                campaign_id="campaign-bodyless-frame",
                session_id="session-a",
                cell_id="cell-a",
                action_id="unsafe-bodyless-frame",
                phase="diagnostic",
                frame=_frame(8),
                endpoint="/api/frame",
                request_body="none",
            )

    def test_complete_reviewed_profile_is_statically_ready(self) -> None:
        decision = evaluate_limit_profile(
            self.profile, evaluated_at="2026-08-07T12:00:00Z"
        )
        self.assertTrue(decision.hardware_ready)
        self.assertEqual(decision.reasons, ())

    def test_any_critical_null_fails_closed(self) -> None:
        payload = _profile_payload(self.actions)
        payload["limits"]["maximum_post_refresh_temperature_c"] = None
        profile = seal_limit_profile(payload)
        decision = evaluate_limit_profile(
            profile, evaluated_at="2026-08-07T12:00:00Z"
        )
        self.assertFalse(decision.hardware_ready)
        self.assertIn(
            "critical_null:limits.maximum_post_refresh_temperature_c",
            decision.reasons,
        )

        usage_payload = _profile_payload(self.actions)
        usage_payload["usage"]["cumulative_visible_refresh_count"] = None
        usage_profile = seal_limit_profile(usage_payload)
        usage_decision = evaluate_limit_profile(
            usage_profile, evaluated_at="2026-08-07T12:00:00Z"
        )
        self.assertFalse(usage_decision.hardware_ready)
        self.assertIn(
            "critical_null:usage.cumulative_visible_refresh_count",
            usage_decision.reasons,
        )

    def test_expired_profile_fails_closed_at_expiry_boundary(self) -> None:
        payload = _profile_payload(self.actions)
        payload["validity"]["expires_at"] = "2026-08-07T12:00:00Z"
        profile = seal_limit_profile(payload)
        decision = evaluate_limit_profile(
            profile, evaluated_at="2026-08-07T12:00:00Z"
        )
        self.assertFalse(decision.hardware_ready)
        self.assertIn("profile_expired", decision.reasons)

    def test_cumulative_session_and_consecutive_usage_exhaust_limits(self) -> None:
        payload = _profile_payload(self.actions)
        payload["usage"].update(
            {
                "cumulative_visible_refresh_count": 2,
                "session_visible_refresh_count": 2,
                "consecutive_visible_refresh_count": 2,
                "last_visible_refresh_completed_at": "2026-08-07T11:54:00Z",
            }
        )
        decision = evaluate_limit_profile(
            seal_limit_profile(payload), evaluated_at="2026-08-07T12:00:00Z"
        )
        self.assertFalse(decision.hardware_ready)
        self.assertIn("campaign_visible_refresh_limit_exhausted", decision.reasons)
        self.assertIn("session_visible_refresh_limit_exhausted", decision.reasons)
        self.assertIn("consecutive_visible_refresh_limit_exhausted", decision.reasons)

    def test_observed_interval_and_new_session_cooldown_are_time_gated(self) -> None:
        interval_payload = _profile_payload(self.actions)
        interval_payload["usage"].update(
            {
                "cumulative_visible_refresh_count": 1,
                "session_visible_refresh_count": 1,
                "consecutive_visible_refresh_count": 1,
                "last_visible_refresh_completed_at": "2026-08-07T11:59:50Z",
                "snapshot_at": "2026-08-07T11:59:55Z",
            }
        )
        interval = evaluate_limit_profile(
            seal_limit_profile(interval_payload),
            evaluated_at="2026-08-07T12:00:00Z",
        )
        self.assertIn("minimum_refresh_interval_not_elapsed", interval.reasons)

        cooldown_payload = _profile_payload(self.actions)
        cooldown_payload["usage"].update(
            {
                "cumulative_visible_refresh_count": 1,
                "session_visible_refresh_count": 0,
                "consecutive_visible_refresh_count": 0,
                "last_visible_refresh_completed_at": "2026-08-07T11:59:50Z",
                "snapshot_at": "2026-08-07T11:59:55Z",
            }
        )
        cooldown = evaluate_limit_profile(
            seal_limit_profile(cooldown_payload),
            evaluated_at="2026-08-07T12:00:00Z",
        )
        self.assertIn(
            "minimum_inter_session_cooldown_not_elapsed", cooldown.reasons
        )

    def test_profile_and_campaign_tampering_are_rejected(self) -> None:
        profile = deepcopy(self.profile)
        profile["limits"]["maximum_campaign_visible_refreshes"] = 3
        with self.assertRaisesRegex(CampaignContractError, "integrity"):
            validate_limit_profile(profile)

        campaign = deepcopy(self.campaign)
        campaign["panel"]["serial"] = "PANEL-TAMPERED"
        with self.assertRaisesRegex(CampaignContractError, "integrity"):
            validate_campaign_contract(campaign)

    def test_action_identity_and_global_claim_tampering_are_rejected(self) -> None:
        action = deepcopy(self.actions[0])
        action["identity"]["request"]["endpoint"] = "/api/other"
        with self.assertRaisesRegex(CampaignContractError, "SHA-256"):
            validate_fixed_action_declaration(action)

        claim_tamper = deepcopy(self.actions[0])
        claim_tamper["claim"]["partitioned_by_campaign_id"] = True
        with self.assertRaisesRegex(CampaignContractError, "workspace-global"):
            validate_fixed_action_declaration(claim_tamper)

        expected = workspace_global_claim_declaration(
            self.actions[0]["action_identity_sha256"]
        )
        self.assertFalse(expected["partitioned_by_campaign_id"])
        self.assertTrue(expected["create_before_network"])
        self.assertFalse(expected["overridable"])

    def test_same_cell_dependency_may_not_cross_cells(self) -> None:
        first = self.actions[0]
        crossed = build_fixed_action_declaration(
            campaign_id="campaign-p0",
            session_id="session-b",
            cell_id="cell-b",
            action_id="cell-b-crossed",
            phase="target",
            frame=_frame(7),
            prior_action_identity_sha256=first["action_identity_sha256"],
            prior_scope="same_cell",
            minimum_interval_since_prior_seconds=30,
        )
        session_a = build_session_contract(
            session_id="session-a",
            cell_id="cell-a",
            power_mode="supervised_continuous",
            planned_cooldown_seconds=60,
            final_power_off_required=False,
            action_identity_sha256s=[first["action_identity_sha256"]],
        )
        session_b = build_session_contract(
            session_id="session-b",
            cell_id="cell-b",
            power_mode="supervised_continuous",
            planned_cooldown_seconds=60,
            final_power_off_required=False,
            action_identity_sha256s=[crossed["action_identity_sha256"]],
        )
        with self.assertRaisesRegex(CampaignContractError, "same_cell"):
            seal_campaign_contract(
                {
                    "schema_version": 1,
                    "kind": CAMPAIGN_KIND,
                    "campaign_id": "campaign-p0",
                    "panel": PANEL,
                    "firmware": FIRMWARE,
                    "actions": [first, crossed],
                    "sessions": [session_a, session_b],
                    "classification": CLASSIFICATION,
                }
            )

    def test_prior_result_replay_and_file_hash_tamper_are_rejected(self) -> None:
        wrong_action_result = self._pass_result(action_index=1)
        with self.assertRaisesRegex(CampaignContractError, "another action"):
            describe_action_offline(
                self.campaign,
                action_identity_sha256=self.actions[1][
                    "action_identity_sha256"
                ],
                limit_profile=self.profile,
                evaluated_at="2026-08-07T12:02:00Z",
                prior_result=wrong_action_result,
                prior_result_sha256=result_file_sha256(wrong_action_result),
            )

        correct = self._pass_result()
        with self.assertRaisesRegex(CampaignContractError, "whole-file"):
            describe_action_offline(
                self.campaign,
                action_identity_sha256=self.actions[1][
                    "action_identity_sha256"
                ],
                limit_profile=self.profile,
                evaluated_at="2026-08-07T12:02:00Z",
                prior_result=correct,
                prior_result_sha256="f" * 64,
            )

    def test_pass_prior_requires_a_usage_snapshot_that_includes_it(self) -> None:
        prior_result = self._pass_result()
        prior_sha = result_file_sha256(prior_result)
        stale = describe_action_offline(
            self.campaign,
            action_identity_sha256=self.actions[1]["action_identity_sha256"],
            limit_profile=self.profile,
            evaluated_at="2026-08-07T12:02:00Z",
            prior_result=prior_result,
            prior_result_sha256=prior_sha,
        )
        self.assertFalse(stale["contract_ready"])
        self.assertIn(
            "usage_snapshot_does_not_record_prior_refresh", stale["blockers"]
        )
        self.assertIn("usage_snapshot_predates_prior_result", stale["blockers"])

        payload = _profile_payload(self.actions)
        payload["usage"].update(
            {
                "cumulative_visible_refresh_count": 1,
                "session_visible_refresh_count": 1,
                "consecutive_visible_refresh_count": 1,
                "last_visible_refresh_completed_at": "2026-08-07T12:01:00Z",
                "snapshot_at": "2026-08-07T12:01:10Z",
            }
        )
        current_profile = seal_limit_profile(payload)
        current = describe_action_offline(
            self.campaign,
            action_identity_sha256=self.actions[1]["action_identity_sha256"],
            limit_profile=current_profile,
            evaluated_at="2026-08-07T12:02:00Z",
            prior_result=prior_result,
            prior_result_sha256=prior_sha,
        )
        self.assertTrue(current["contract_ready"])
        self.assertEqual(
            current["prior_result_binding"]["result_file_sha256"], prior_sha
        )

    def test_non_pass_prior_is_terminal_and_does_not_unlock_dependent(self) -> None:
        failed = build_result_record(
            action_identity_sha256=self.actions[0]["action_identity_sha256"],
            state=ResultState.FAIL,
            completed_at="2026-08-07T12:01:00Z",
            evidence_manifest_sha256="4" * 64,
            post_request_count=1,
        )
        description = describe_action_offline(
            self.campaign,
            action_identity_sha256=self.actions[1]["action_identity_sha256"],
            limit_profile=self.profile,
            evaluated_at="2026-08-07T12:02:00Z",
            prior_result=failed,
            prior_result_sha256=result_file_sha256(failed),
        )
        self.assertFalse(description["contract_ready"])
        self.assertIn("prior_result_not_pass", description["blockers"])
        self.assertFalse(description["automatic_retry_authorized"])
        self.assertFalse(description["automatic_recovery_authorized"])

    def test_signed_but_nonmatching_allowlist_and_limits_fail_closed(self) -> None:
        allowlist_payload = _profile_payload(self.actions)
        allowlist_payload["action_allowlist"][0]["endpoint"] = "/api/other"
        allowlist_profile = seal_limit_profile(allowlist_payload)
        description = describe_action_offline(
            self.campaign,
            action_identity_sha256=self.actions[0]["action_identity_sha256"],
            limit_profile=allowlist_profile,
            evaluated_at="2026-08-07T12:00:00Z",
        )
        self.assertIn("exact_action_not_allowlisted", description["blockers"])

        limit_payload = _profile_payload(self.actions)
        limit_payload["limits"]["maximum_campaign_visible_refreshes"] = 1
        limit_payload["limits"]["maximum_session_visible_refreshes"] = 1
        limit_payload["limits"]["maximum_consecutive_visible_refreshes"] = 1
        limit_profile = seal_limit_profile(limit_payload)
        limited = describe_action_offline(
            self.campaign,
            action_identity_sha256=self.actions[0]["action_identity_sha256"],
            limit_profile=limit_profile,
            evaluated_at="2026-08-07T12:00:00Z",
        )
        self.assertIn(
            "campaign_visible_refresh_limit_exceeded", limited["blockers"]
        )
        self.assertIn("session_visible_refresh_limit_exceeded", limited["blockers"])
        self.assertIn(
            "consecutive_visible_refresh_limit_exceeded", limited["blockers"]
        )

    def test_describe_only_has_zero_io_zero_claim_and_never_authorizes(self) -> None:
        with (
            mock.patch("builtins.open", side_effect=AssertionError("file I/O")),
            mock.patch.object(
                socket, "socket", side_effect=AssertionError("socket I/O")
            ),
            mock.patch.object(
                subprocess, "run", side_effect=AssertionError("process I/O")
            ),
        ):
            description = describe_action_offline(
                self.campaign,
                action_identity_sha256=self.actions[0][
                    "action_identity_sha256"
                ],
                limit_profile=self.profile,
                evaluated_at="2026-08-07T12:00:00Z",
            )
        self.assertTrue(description["contract_ready"])
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["hardware_execution_authorized"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(description["device_io_performed"])
        self.assertEqual(
            description[
                "maximum_post_requests_if_future_executor_is_separately_authorized"
            ],
            1,
        )
        validate_action_description(description)
        tampered = deepcopy(description)
        tampered["claim_created"] = True
        with self.assertRaisesRegex(CampaignContractError, "must keep"):
            validate_action_description(tampered)

    def test_all_result_states_are_terminal_and_do_not_enable_retry(self) -> None:
        self.assertEqual(
            RESULT_STATES,
            ("PASS", "FAIL", "INVALID", "STOP", "UNKNOWN_DO_NOT_RETRY"),
        )
        for state in RESULT_STATES:
            with self.subTest(state=state):
                result = build_result_record(
                    action_identity_sha256=self.actions[0][
                        "action_identity_sha256"
                    ],
                    state=state,
                    completed_at="2026-08-07T12:01:00Z",
                    evidence_manifest_sha256="4" * 64,
                    post_request_count=1 if state == "PASS" else 0,
                )
                validate_result_record(result)
                self.assertTrue(result["terminal"])
                self.assertFalse(result["retry_allowed"])
                self.assertEqual(result["automatic_retry_count"], 0)
                self.assertFalse(result["recovery_performed"])

        tampered = self._pass_result()
        tampered["retry_allowed"] = True
        with self.assertRaisesRegex(CampaignContractError, "no retry"):
            validate_result_record(tampered)

    def test_session_modes_distinguish_controller_boot_from_j2_cycle(self) -> None:
        action_sha = self.actions[0]["action_identity_sha256"]
        continuous = build_session_contract(
            session_id="s-continuous",
            cell_id="cell-a",
            power_mode="supervised_continuous",
            planned_cooldown_seconds=60,
            final_power_off_required=False,
            action_identity_sha256s=[action_sha],
        )
        controller_boot = build_session_contract(
            session_id="s-controller",
            cell_id="cell-a",
            power_mode="controller_fresh_boot",
            planned_cooldown_seconds=60,
            final_power_off_required=False,
            action_identity_sha256s=[action_sha],
        )
        panel_cycle = build_session_contract(
            session_id="s-panel",
            cell_id="cell-a",
            power_mode="panel_cold_cycle",
            planned_cooldown_seconds=60,
            final_power_off_required=True,
            action_identity_sha256s=[action_sha],
            minimum_panel_power_off_seconds=30,
        )
        driver_only_cycle = build_session_contract(
            session_id="s-driver-only",
            cell_id="cell-a",
            power_mode="panel_cold_driver_only",
            planned_cooldown_seconds=60,
            final_power_off_required=True,
            action_identity_sha256s=[action_sha],
            minimum_panel_power_off_seconds=10,
        )
        self.assertEqual(continuous["kind"], SESSION_KIND)
        self.assertFalse(continuous["requires_controller_fresh_boot"])
        self.assertTrue(controller_boot["requires_controller_fresh_boot"])
        self.assertFalse(controller_boot["requires_panel_power_cycle"])
        self.assertTrue(controller_boot["j2_may_remain_on_before_session"])
        self.assertTrue(panel_cycle["requires_panel_power_cycle"])
        self.assertFalse(panel_cycle["j2_may_remain_on_before_session"])
        self.assertFalse(driver_only_cycle["requires_controller_fresh_boot"])
        self.assertTrue(driver_only_cycle["requires_panel_power_cycle"])
        self.assertFalse(driver_only_cycle["j2_may_remain_on_before_session"])
        with self.assertRaisesRegex(CampaignContractError, "off interval null"):
            build_session_contract(
                session_id="s-invalid",
                cell_id="cell-a",
                power_mode="controller_fresh_boot",
                planned_cooldown_seconds=60,
                final_power_off_required=False,
                action_identity_sha256s=[action_sha],
                minimum_panel_power_off_seconds=30,
            )


if __name__ == "__main__":
    unittest.main()
