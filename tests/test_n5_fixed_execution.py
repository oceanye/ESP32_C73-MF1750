from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from typing import Any, Mapping

import host.extended_color.execution as execution
from tests.n5_execution_fixture import (
    build_pass_bundle,
    hash_text,
    reviewed_limit_profile,
    seal_external_authorization,
)
from tools.mf1750_n5_fixed_execution import (
    action_list,
    compile_default_execution_contract,
    compile_materialized_execution_contract,
    load_action_frame,
)
from tools.mf1750_n5_measurement_campaign import (
    DEFAULT_FIRMWARE,
    DEFAULT_PANEL,
    build_reviewed_transition_recovery_profile,
    compile_campaign_manifest,
    reviewed_panel_cold_profile,
)


def _bound_panel() -> dict[str, str]:
    return {**DEFAULT_PANEL, "serial": "PANEL-N5-EXEC-001"}


def _cold_profile() -> dict[str, object]:
    return reviewed_panel_cold_profile(
        minimum_panel_power_off_seconds=60,
        review_artifact_sha256="1" * 64,
    )


def _recovery_profile() -> dict[str, object]:
    return build_reviewed_transition_recovery_profile(
        panel=_bound_panel(),
        firmware=DEFAULT_FIRMWARE,
        waveform_id="wf-n5-exec-v1",
        waveform_sha256="2" * 64,
        qualification_artifact_sha256="3" * 64,
        reviewer_id="n5-exec-reviewer",
        reviewed_at="2026-08-08T00:00:00Z",
        review_artifact_sha256="4" * 64,
        supplier_limit_profile_sha256="5" * 64,
        usage_limit_contract_sha256="6" * 64,
        temperature_chain_sha256="7" * 64,
    )


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class N5ExecutionCompilerTests(unittest.TestCase):
    def test_default_contract_freezes_descriptive_and_blocks_formal_hardware(self) -> None:
        contract = compile_default_execution_contract()
        self.assertEqual(len(contract["actions"]), 22)
        self.assertEqual(len(contract["sessions"]), 11)
        self.assertEqual({entry["plan_class"] for entry in contract["actions"]}, {"descriptive"})
        self.assertFalse(contract["readiness"]["hardware_ready"])
        self.assertFalse(contract["plan_bindings"]["formal_palette"]["materialized"])
        self.assertFalse(contract["plan_bindings"]["formal_transition"]["materialized"])
        self.assertFalse(contract["classification"]["claim_created"])
        self.assertFalse(contract["classification"]["authorization_created"])

    def test_both_formal_classes_materialize_on_one_shared_p0(self) -> None:
        manifest = compile_campaign_manifest(
            panel=_bound_panel(),
            formal_palette_cold_profile=_cold_profile(),
            formal_transition_recovery_profile=_recovery_profile(),
            formal_transition_power_profile=_cold_profile(),
        )
        contract = compile_materialized_execution_contract(manifest)
        counts = {
            plan_class: sum(
                entry["plan_class"] == plan_class for entry in contract["actions"]
            )
            for plan_class in execution.PLAN_CLASSES
        }
        self.assertEqual(counts, {"descriptive": 22, "formal_palette": 9, "formal_transition": 42})
        self.assertEqual(len(contract["sessions"]), 26)
        transition_sessions = [
            session
            for session in contract["sessions"]
            if session["plan_class"] == "formal_transition"
        ]
        self.assertEqual(len(transition_sessions), 7)
        self.assertTrue(
            all(
                session["power_mode"] == "panel_cold_cycle"
                and len(session["action_identity_sha256s"]) == 6
                and session["automatic_advance"] is False
                for session in transition_sessions
            )
        )

    def test_every_materialized_action_frame_rebinds_to_deterministic_bytes(self) -> None:
        manifest = compile_campaign_manifest(
            panel=_bound_panel(),
            formal_palette_cold_profile=_cold_profile(),
            formal_transition_recovery_profile=_recovery_profile(),
            formal_transition_power_profile=_cold_profile(),
        )
        contract = compile_materialized_execution_contract(manifest)
        frames = [load_action_frame(contract, entry["action_key"]) for entry in contract["actions"]]
        self.assertEqual(len(frames), 73)
        self.assertTrue(all(isinstance(frame, bytes) and len(frame) == 307200 for frame in frames))

    def test_describe_is_pure_and_never_creates_claim_or_authorization(self) -> None:
        contract = compile_default_execution_contract()
        action = contract["actions"][0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                description = execution.describe_fixed_action(
                    contract, action["action_key"]
                )
            self.assertFalse(any(root.rglob("*.json")))
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["hardware_ready"])
        self.assertIn("canonical_reviewed_limit_profile_missing", description["blockers"])

    def test_action_list_is_exact_and_not_caller_extensible(self) -> None:
        contract = compile_default_execution_contract()
        listed = action_list(contract)
        self.assertEqual(len(listed), 22)
        with self.assertRaises(execution.N5ExecutionError):
            execution.load_action_snapshot(contract, "caller-invented-action")


class N5OneActionEngineTests(unittest.TestCase):
    def _inputs(self):
        contract = compile_default_execution_contract()
        entry = contract["actions"][0]
        snapshot = execution.load_action_snapshot(contract, entry["action_key"])
        start = execution.seal_session_start(
            {
                "schema_version": 1,
                "kind": execution.SESSION_START_KIND,
                "session_id": snapshot.session["session_id"],
                "observed_at": "2026-08-08T00:31:00Z",
                "power_mode": "supervised_continuous",
                "j2_initially_off": False,
                "measured_panel_power_off_seconds": None,
                "controller_fresh_boot_observed": False,
                "j2_on_before_first_action": True,
                "supply_cv_current_normal": True,
                "temperature_normal": True,
                "physical_cutoff_available": True,
                "observation_artifact_sha256": hash_text("one-action-session-start"),
            },
            snapshot=snapshot,
        )
        authorization = seal_external_authorization(
            {
                "schema_version": 1,
                "kind": execution.AUTHORIZATION_KIND,
                "authorization_id": "AUTH-N5-STRUCTURAL-ONE",
                "action_identity_sha256": entry["action_identity_sha256"],
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "session_start_file_sha256": execution._sha256(start),
                "issued_at": "2026-08-08T00:32:00Z",
                "expires_at": "2026-08-08T01:32:00Z",
                "operator_id": "structural-operator",
                "authorization_artifact_sha256": hash_text("one-action-auth"),
                "confirmation_sha256": hash_text("one-action-confirmation"),
                "maximum_post_requests": 1,
                "automatic_advance_authorized": False,
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            }
        )
        base = datetime(2026, 8, 8, tzinfo=timezone.utc)
        profile = reviewed_limit_profile(
            contract,
            last_visible_at=base,
            snapshot_at=base + timedelta(minutes=30),
        )
        return contract, entry, snapshot, start, authorization, profile

    def test_claim_exists_before_transport_and_exactly_one_post_is_issued(self) -> None:
        contract, entry, _snapshot, start, authorization, profile = self._inputs()
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            store = execution.AtomicWorkspaceClaimStore(workspace)
            observed = []

            def transport(method: str, endpoint: str, data: bytes | None) -> object:
                claim = (
                    workspace
                    / ".test-output/hardware/.visible_refresh_fixed_action_claims_v1"
                    / f"{entry['action_identity_sha256']}.json"
                )
                self.assertTrue(claim.is_file())
                observed.append((method, endpoint, data is not None))
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes) -> Mapping[str, Any]:
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"completed": True}

            receipt = execution.execute_fixed_action_once(
                contract,
                entry["action_key"],
                load_action_frame(contract, entry["action_key"]),
                limit_profile=profile,
                profile_evaluated_at="2026-08-08T00:32:00Z",
                authorization=authorization,
                session_start=start,
                runtime_gates={
                    "observed_at": "2026-08-08T00:32:00Z",
                    "start_temperature_c": 23.0,
                    "supply_cv_current_normal": True,
                    "j2_on": True,
                    "physical_cutoff_available": True,
                    "operator_advance_artifact_sha256": hash_text("one-action-advance"),
                    "runtime_evidence_sha256": hash_text("one-action-runtime"),
                },
                prior_bundle=None,
                attempt_id="one-action-attempt",
                claimed_at="2026-08-08T00:33:00Z",
                protocol_completed_at="2026-08-08T00:34:00Z",
                claim_store=store,
                transport=transport,
                protocol_driver=driver,
            )
            self.assertEqual(observed.count(("POST", "/api/frame", True)), 1)
            self.assertEqual(receipt["protocol_evidence"]["request_audit"]["post_issued_count"], 1)

    def test_second_post_is_blocked_and_claim_cannot_be_reused(self) -> None:
        contract, entry, _snapshot, start, authorization, profile = self._inputs()
        with tempfile.TemporaryDirectory() as temporary:
            store = execution.AtomicWorkspaceClaimStore(Path(temporary))
            calls = []

            def transport(method: str, endpoint: str, data: bytes | None) -> object:
                calls.append((method, endpoint))
                return {"status": 200}

            def bad_driver(audited: execution.AuditedTransport, frame: bytes) -> Mapping[str, Any]:
                audited.request("POST", "/api/frame", frame)
                audited.request("POST", "/api/frame", frame)
                return {"unreachable": True}

            kwargs = dict(
                limit_profile=profile,
                profile_evaluated_at="2026-08-08T00:32:00Z",
                authorization=authorization,
                session_start=start,
                runtime_gates={
                    "observed_at": "2026-08-08T00:32:00Z",
                    "start_temperature_c": 23.0,
                    "supply_cv_current_normal": True,
                    "j2_on": True,
                    "physical_cutoff_available": True,
                    "operator_advance_artifact_sha256": hash_text("bad-advance"),
                    "runtime_evidence_sha256": hash_text("bad-runtime"),
                },
                prior_bundle=None,
                attempt_id="bad-attempt",
                claimed_at="2026-08-08T00:33:00Z",
                protocol_completed_at="2026-08-08T00:34:00Z",
                claim_store=store,
                transport=transport,
                protocol_driver=bad_driver,
            )
            with self.assertRaises(execution.N5PostClaimUnknown) as caught:
                execution.execute_fixed_action_once(
                    contract,
                    entry["action_key"],
                    load_action_frame(contract, entry["action_key"]),
                    **kwargs,
                )
            self.assertEqual(calls.count(("POST", "/api/frame")), 1)
            self.assertEqual(
                caught.exception.receipt["protocol_evidence"]["request_audit"][
                    "post_issued_count"
                ],
                1,
            )
            with self.assertRaises(execution.N5ClaimConsumedError):
                execution.execute_fixed_action_once(
                    contract,
                    entry["action_key"],
                    load_action_frame(contract, entry["action_key"]),
                    **{**kwargs, "protocol_driver": lambda *_: {"unused": True}},
                )


class N5FinalizedBundleTests(unittest.TestCase):
    def test_abnormal_stop_rejects_later_same_plan_sessions(self) -> None:
        contract = compile_default_execution_contract()
        failed_sha = contract["actions"][1]["action_identity_sha256"]
        fail_bundle = build_pass_bundle(
            contract,
            terminal_action_identity_sha256s=[failed_sha],
            fail_action_identity_sha256=failed_sha,
        )
        later_bundle = build_pass_bundle(
            contract,
            terminal_action_identity_sha256s=[
                contract["actions"][3]["action_identity_sha256"]
            ],
        )
        combined_actions = [*fail_bundle["actions"], *later_bundle["actions"]]
        combined_starts = [
            *[session["session_start"] for session in fail_bundle["sessions"]],
            *[session["session_start"] for session in later_bundle["sessions"]],
        ]
        failed_session = fail_bundle["sessions"][0]["finalization"]["session_id"]
        with self.assertRaisesRegex(execution.N5ExecutionError, "made ineligible"):
            execution.build_finalized_bundle(
                contract,
                combined_actions,
                combined_starts,
                finalized_at="2026-08-08T03:00:00Z",
                j2_cut_session_ids=[failed_session],
            )

        forged = build_pass_bundle(
            contract,
            terminal_action_identity_sha256s=[
                contract["actions"][1]["action_identity_sha256"],
                contract["actions"][3]["action_identity_sha256"],
            ],
        )
        failed_item = next(
            item
            for item in fail_bundle["actions"]
            if item["action_identity_sha256"] == failed_sha
        )
        forged["actions"] = [
            failed_item if item["action_identity_sha256"] == failed_sha else item
            for item in forged["actions"]
        ]
        failed_session_record = copy.deepcopy(fail_bundle["sessions"][0])
        unsigned_session = dict(failed_session_record["finalization"])
        unsigned_session.pop("integrity")
        unsigned_session["finalized_at"] = forged["finalized_at"]
        failed_session_record["finalization"] = execution._seal(unsigned_session)
        failed_session_record["finalization_file_sha256"] = execution._sha256(
            failed_session_record["finalization"]
        )
        forged["sessions"] = [
            failed_session_record
            if session["finalization"]["session_id"] == failed_session
            else session
            for session in forged["sessions"]
        ]
        forged["termination"] = copy.deepcopy(fail_bundle["termination"])
        unsigned_forged = dict(forged)
        unsigned_forged.pop("integrity")
        forged["integrity"] = execution._integrity(
            unsigned_forged, execution.BUNDLE_HASH_SCOPE
        )
        with self.assertRaisesRegex(execution.N5ExecutionError, "made ineligible"):
            execution.validate_finalized_bundle(contract, forged)

    def test_bundle_actions_and_sessions_have_one_canonical_contract_order(self) -> None:
        contract = compile_default_execution_contract()
        bundle = build_pass_bundle(
            contract,
            terminal_action_identity_sha256s=[
                contract["actions"][1]["action_identity_sha256"],
                contract["actions"][3]["action_identity_sha256"],
            ],
        )
        starts = [session["session_start"] for session in bundle["sessions"]]
        with self.assertRaisesRegex(execution.N5ExecutionError, "strict execution-contract order"):
            execution.build_finalized_bundle(
                contract,
                list(reversed(bundle["actions"])),
                starts,
                finalized_at=bundle["finalized_at"],
            )

        reordered_actions = copy.deepcopy(bundle)
        reordered_actions["actions"].reverse()
        unsigned = dict(reordered_actions)
        unsigned.pop("integrity")
        reordered_actions["integrity"] = execution._integrity(
            unsigned, execution.BUNDLE_HASH_SCOPE
        )
        with self.assertRaisesRegex(execution.N5ExecutionError, "strict contract order"):
            execution.validate_finalized_bundle(contract, reordered_actions)

        reordered_sessions = copy.deepcopy(bundle)
        reordered_sessions["sessions"].reverse()
        unsigned = dict(reordered_sessions)
        unsigned.pop("integrity")
        reordered_sessions["integrity"] = execution._integrity(
            unsigned, execution.BUNDLE_HASH_SCOPE
        )
        with self.assertRaisesRegex(execution.N5ExecutionError, "sessions.*strict contract order"):
            execution.validate_finalized_bundle(contract, reordered_sessions)

    def test_bundle_and_j2_cut_time_cannot_precede_action_completion(self) -> None:
        contract = compile_default_execution_contract()
        terminal = contract["actions"][1]["action_identity_sha256"]
        bundle = build_pass_bundle(
            contract, terminal_action_identity_sha256s=[terminal]
        )
        starts = [entry["session_start"] for entry in bundle["sessions"]]
        completed = datetime.fromisoformat(
            bundle["actions"][-1]["finalization"]["completed_at"].replace(
                "Z", "+00:00"
            )
        )
        early = _timestamp(completed - timedelta(seconds=1))
        with self.assertRaisesRegex(
            execution.N5ExecutionError, "precedes an included action"
        ):
            execution.build_finalized_bundle(
                contract,
                bundle["actions"],
                starts,
                finalized_at=early,
            )

        tampered = copy.deepcopy(bundle)
        tampered["finalized_at"] = early
        for session in tampered["sessions"]:
            unsigned_session = dict(session["finalization"])
            unsigned_session.pop("integrity")
            unsigned_session["finalized_at"] = early
            session["finalization"] = execution._seal(unsigned_session)
            session["finalization_file_sha256"] = execution._sha256(
                session["finalization"]
            )
        unsigned_bundle = dict(tampered)
        unsigned_bundle.pop("integrity")
        tampered["integrity"] = execution._integrity(
            unsigned_bundle, execution.BUNDLE_HASH_SCOPE
        )
        with self.assertRaisesRegex(
            execution.N5ExecutionError, "precedes an included action"
        ):
            execution.validate_finalized_bundle(contract, tampered)

    def test_bundle_rejects_unknown_extra_and_duplicate_j2_cut_ids(self) -> None:
        contract = compile_default_execution_contract()
        terminal = contract["actions"][1]["action_identity_sha256"]
        bundle = build_pass_bundle(
            contract, terminal_action_identity_sha256s=[terminal]
        )
        starts = [entry["session_start"] for entry in bundle["sessions"]]
        included_session = bundle["sessions"][0]["finalization"]["session_id"]
        another_session = next(
            entry["session_id"]
            for entry in contract["sessions"]
            if entry["session_id"] != included_session
        )
        for cut_ids in (
            ["caller-invented-session"],
            [another_session],
            [included_session],
            [included_session, included_session],
        ):
            with self.subTest(cut_ids=cut_ids), self.assertRaises(
                execution.N5ExecutionError
            ):
                execution.build_finalized_bundle(
                    contract,
                    bundle["actions"],
                    starts,
                    finalized_at="2026-08-08T02:00:00Z",
                    j2_cut_session_ids=cut_ids,
                )

    def test_bundle_binds_immediate_prior_result_and_rejects_flag_tamper(self) -> None:
        contract = compile_default_execution_contract()
        terminal = contract["actions"][1]["action_identity_sha256"]
        bundle = build_pass_bundle(
            contract, terminal_action_identity_sha256s=[terminal]
        )
        summary = execution.validate_finalized_bundle(contract, bundle)
        self.assertEqual(len(summary["actions_by_sha"]), 2)
        target = summary["actions_by_sha"][terminal]
        prior_sha = contract["actions"][0]["action_identity_sha256"]
        self.assertEqual(
            target["prior_result_file_sha256"],
            summary["actions_by_sha"][prior_sha]["result_file_sha256"],
        )
        promoted = copy.deepcopy(bundle)
        promoted["actions"][0]["manual_observation"]["visual_pass"] = False
        with self.assertRaises(execution.N5ExecutionError):
            execution.validate_finalized_bundle(contract, promoted)

    def test_abnormal_action_ineligibilizes_every_later_plan_action(self) -> None:
        contract = compile_default_execution_contract()
        failed = contract["actions"][0]["action_identity_sha256"]
        bundle = build_pass_bundle(
            contract,
            terminal_action_identity_sha256s=[failed],
            fail_action_identity_sha256=failed,
        )
        summary = execution.validate_finalized_bundle(contract, bundle)
        self.assertEqual(summary["state"], "abnormal-stop")
        session_finalization = bundle["sessions"][0]["finalization"]
        self.assertTrue(
            session_finalization["manual_j2_cut_after_terminal_action"]
        )
        self.assertEqual(
            session_finalization["j2_cut_reason"], "abnormal_terminal"
        )
        self.assertEqual(session_finalization["j2_state_after_finalization"], "off")
        with self.assertRaisesRegex(execution.N5ExecutionError, "manual J2 cut"):
            execution.build_finalized_bundle(
                contract,
                bundle["actions"],
                [session["session_start"] for session in bundle["sessions"]],
                finalized_at=bundle["finalized_at"],
            )
        self.assertEqual(
            bundle["termination"]["ineligible_action_identity_sha256s"],
            [entry["action_identity_sha256"] for entry in contract["actions"][1:]],
        )


if __name__ == "__main__":
    unittest.main()
