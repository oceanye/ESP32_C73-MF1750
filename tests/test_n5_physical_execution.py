from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.extended_color import execution
from host.extended_color import n5_rc2g_protocol
from host.visible_refresh_campaign import canonical_json_bytes
from host.visible_refresh_campaign import production_profile as production
from tests.test_g1_s1_rc2g_map_baseline_once import (
    ScriptedRequester,
    TickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    _responses as quality_responses,
)
from tests.test_n5_physical_campaign import (
    COOLDOWN_SECONDS,
    FIRMWARE_BYTES,
    INTERVAL_SECONDS,
    _inputs,
)
from tools import mf1750_n5_fixed_execution as fixed
from tools import mf1750_n5_physical_campaign as physical_campaign
from tools import mf1750_n5_physical_execution as physical


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _hash_text(value: str) -> str:
    return physical._sha256(value.encode("utf-8"))


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self.values = list(values)

    def __call__(self) -> str:
        if not self.values:
            raise AssertionError("wall clock was read more times than expected")
        return self.values.pop(0)


class CountingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes | None]] = []

    def __call__(self, method: str, endpoint: str, data: bytes | None) -> object:
        self.calls.append((method, endpoint, data))
        raise AssertionError("preclaim rejection reached transport")


class N5PhysicalExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.materializer_inputs = _inputs()
        cls.plan = physical_campaign.compile_n5_physical_plan(
            cls.materializer_inputs,
            namespace="physical-execution-test-v1",
            minimum_interval_seconds=INTERVAL_SECONDS,
            planned_cooldown_seconds=COOLDOWN_SECONDS,
        )
        cls.context = physical.N5PhysicalContext(
            plan=cls.plan,
            plan_bytes=canonical_json_bytes(cls.plan),
            inputs=cls.materializer_inputs,
            namespace="physical-execution-test-v1",
            minimum_interval_seconds=INTERVAL_SECONDS,
            planned_cooldown_seconds=COOLDOWN_SECONDS,
        )
        cls.contract = cls.plan["execution_contract"]
        cls.entry = cls.contract["actions"][0]
        cls.action_key = cls.entry["action_key"]
        cls.snapshot = execution.load_action_snapshot(cls.contract, cls.action_key)
        cls.base = datetime(2026, 8, 8, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.campaign_file = self._write_json(
            "physical-campaign.json", self.contract["p0_campaign"]
        )
        self.firmware_file = self.root / "firmware.bin"
        self.firmware_file.write_bytes(FIRMWARE_BYTES)
        self.profile_key = self.root / "profile-reviewer.key"
        self.profile_key.write_bytes(b"n5-physical-profile-reviewer-key-v1")

    def _write_json(self, name: str, value) -> Path:
        path = self.root / name
        path.write_bytes(canonical_json_bytes(value))
        return path

    def _policy(
        self,
        *,
        authority_interval: int = 60,
        label: str = "first",
        valid_from: str = "2026-08-08T00:03:50Z",
    ) -> dict:
        limits = {
            "maximum_campaign_visible_refreshes": 100,
            "maximum_session_visible_refreshes": 100,
            "maximum_consecutive_visible_refreshes": 100,
            "minimum_interval_seconds": authority_interval,
            "minimum_cooldown_seconds": authority_interval,
            "minimum_start_temperature_c": 0,
            "maximum_start_temperature_c": 50,
            "maximum_post_refresh_temperature_c": 50,
        }
        temperature_fields = {
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
            "issuer": "n5-physical-test-process-owner",
            "policy_id": f"n5-physical-policy-{label}-{authority_interval}",
            "issued_at": "2026-08-07T20:00:00Z",
            "panel_model": self.contract["p0_campaign"]["panel"]["model"],
            "maximum_usage_snapshot_age_seconds": 7200,
            "limits": limits,
            "validity": {
                "valid_from": valid_from,
                "expires_at": "2026-08-09T00:00:00Z",
            },
            "field_provenance": {
                field: {
                    "classification": (
                        production.EXACT_SUPPLIER_DOCUMENT_PROVENANCE
                        if field in temperature_fields
                        else production.OPERATOR_SELECTED_PROCESS_GATE_PROVENANCE
                    ),
                    "source_document_sha256": (
                        production.MF1750_A1_SOURCE_DOCUMENT_SHA256
                    ),
                }
                for field in limits
            },
        }

    def _production(
        self,
        *,
        last_completed_at: str,
        snapshot_at: str,
        authority_interval: int = 60,
        label: str = "first",
        cumulative: int = 1,
        session_count: int = 1,
        consecutive: int = 1,
        reviewed_at: str = "2026-08-08T00:03:45Z",
        valid_from: str = "2026-08-08T00:03:50Z",
        evaluated_at: str = "2026-08-08T00:04:00Z",
    ) -> tuple[physical.N5ProductionFiles, production.ValidatedProductionProfile]:
        authority_file = self._write_json(
            f"authority-{label}-{authority_interval}.json",
            self._policy(
                authority_interval=authority_interval,
                label=label,
                valid_from=valid_from,
            ),
        )
        usage_file = self._write_json(
            f"usage-{label}.json",
            {
                "schema_version": 1,
                "kind": production.USAGE_EVIDENCE_KIND,
                "evidence_id": "n5-physical-usage-v1",
                "campaign_canonical_sha256": self.contract["p0_campaign"][
                    "integrity"
                ]["canonical_sha256"],
                "panel": self.contract["p0_campaign"]["panel"],
                "firmware": self.contract["p0_campaign"]["firmware"],
                "usage": {
                    "cumulative_visible_refresh_count": cumulative,
                    "session_visible_refresh_count": session_count,
                    "consecutive_visible_refresh_count": consecutive,
                    "last_visible_refresh_completed_at": last_completed_at,
                    "snapshot_at": snapshot_at,
                },
            },
        )
        draft = production.compile_production_draft_from_files(
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            supplier_limits_file=authority_file,
            usage_evidence_file=usage_file,
            profile_id=f"n5-physical-production-profile-{label}",
            profile_version="1.0.0",
        )
        draft_file = self._write_json(f"draft-{label}.json", draft)
        approval = production.create_production_approval(
            draft_profile_file=draft_file,
            campaign_file=self.campaign_file,
            firmware_binary_file=self.firmware_file,
            supplier_limits_file=authority_file,
            usage_evidence_file=usage_file,
            reviewer_id="n5-physical-profile-reviewer",
            reviewed_at=reviewed_at,
            reviewer_key_file=self.profile_key,
        )
        review_file = self.root / f"profile-review-{label}.json"
        profile_file = self.root / f"profile-{label}.json"
        production.publish_approval_bundle(
            approval,
            review_artifact_output=review_file,
            profile_output=profile_file,
        )
        files = physical.N5ProductionFiles(
            profile=profile_file,
            physical_campaign=self.campaign_file,
            firmware_binary=self.firmware_file,
            limit_authority=authority_file,
            usage_evidence=usage_file,
            review_artifact=review_file,
            reviewer_key=self.profile_key,
        )
        validated = physical._load_production_for_snapshot(
            self.context,
            self.snapshot,
            files,
            evaluated_at=evaluated_at,
        )
        return files, validated

    def _session_start(self) -> dict:
        return execution.seal_session_start(
            {
                "schema_version": 1,
                "kind": execution.SESSION_START_KIND,
                "session_id": self.snapshot.session["session_id"],
                "observed_at": "2026-08-08T00:02:00Z",
                "power_mode": self.snapshot.session["power_mode"],
                "j2_initially_off": False,
                "measured_panel_power_off_seconds": None,
                "controller_fresh_boot_observed": False,
                "j2_on_before_first_action": True,
                "supply_cv_current_normal": True,
                "temperature_normal": True,
                "physical_cutoff_available": True,
                "observation_artifact_sha256": _hash_text("n5-session-start"),
            },
            snapshot=self.snapshot,
        )

    def _authorization(
        self,
        production_profile: production.ValidatedProductionProfile,
        session_start: dict,
        *,
        snapshot: execution.ActionSnapshot | None = None,
        entry: dict | None = None,
        issued_at: str = "2026-08-08T00:04:00Z",
        authorization_id: str = "N5-PHYSICAL-AUTH-FIRST-ACTION",
    ) -> tuple[dict, str, str, str]:
        selected_snapshot = self.snapshot if snapshot is None else snapshot
        selected_entry = self.entry if entry is None else entry
        action_token = physical._required_action_token(
            self.context, selected_snapshot
        )
        panel_token = physical._required_panel_plan_token(
            self.context, selected_snapshot
        )
        profile_token = physical.required_profile_token(production_profile)
        confirmation = physical.authorization_confirmation_sha256(
            action_token=action_token,
            panel_plan_token=panel_token,
            profile_token=profile_token,
        )
        payload = {
            "schema_version": 1,
            "kind": execution.AUTHORIZATION_KIND,
            "authorization_id": authorization_id,
            "action_identity_sha256": selected_entry["action_identity_sha256"],
            "execution_contract_canonical_sha256": self.contract["integrity"][
                "canonical_sha256"
            ],
            "session_start_file_sha256": execution._sha256(session_start),
            "issued_at": issued_at,
            "expires_at": "2026-08-08T01:00:00Z",
            "operator_id": "n5-physical-test-operator",
            "authorization_artifact_sha256": _hash_text("n5-physical-auth"),
            "confirmation_sha256": confirmation,
            "maximum_post_requests": 1,
            "automatic_advance_authorized": False,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }
        authorization = execution._seal(payload)
        return authorization, action_token, panel_token, profile_token

    def _run_inputs(self, *, last_completed_at: str):
        files, validated = self._production(
            last_completed_at=last_completed_at,
            snapshot_at="2026-08-08T00:03:30Z",
        )
        session = self._session_start()
        authorization, action, panel, profile = self._authorization(
            validated, session
        )
        return files, session, authorization, action, panel, profile

    def test_policy_below_materialized_schedule_rejects_preclaim_with_zero_io(self) -> None:
        files, session, authorization, action, panel, profile = self._run_inputs(
            last_completed_at="2026-08-08T00:02:00Z"
        )
        claim_root = self.root / "claims"
        result_dir = self.root / "result"
        transport = CountingTransport()
        with mock.patch.object(
            physical,
            "validate_n5_physical_context",
            return_value=self.plan,
        ):
            with self.assertRaisesRegex(
                physical.N5PhysicalExecutionError,
                "effective physical minimum refresh interval",
            ):
                physical.run_n5_physical_action_once(
                    self.context,
                    self.action_key,
                    production_files=files,
                    authorization=authorization,
                    session_start=session,
                    prior_bundle=None,
                    result_dir=result_dir,
                    claim_root=claim_root,
                    base_url="http://device",
                    action_token=action,
                    panel_plan_token=panel,
                    profile_token=profile,
                    start_temperature_c=23,
                    confirm_supply_cv_current_normal=True,
                    confirm_j2_on=True,
                    confirm_physical_cutoff_available=True,
                    wall_clock=SequenceClock(
                        "2026-08-08T00:04:00Z", "2026-08-08T00:04:00Z"
                    ),
                    transport=transport,
                )
        self.assertEqual(transport.calls, [])
        self.assertFalse(claim_root.exists())
        self.assertFalse(result_dir.exists())

    def test_stale_evaluation_and_token_drift_are_preclaim_zero_io(self) -> None:
        files, session, authorization, action, panel, profile = self._run_inputs(
            last_completed_at="2026-08-08T00:00:00Z"
        )
        for label, clock, supplied_action in (
            (
                "300 seconds",
                SequenceClock(
                    "2026-08-08T00:04:00Z", "2026-08-08T00:10:00Z"
                ),
                action,
            ),
            (
                "exact action token",
                SequenceClock(
                    "2026-08-08T00:04:00Z", "2026-08-08T00:04:01Z"
                ),
                action + "-tampered",
            ),
        ):
            claim_root = self.root / f"claims-{label.replace(' ', '-')}"
            result_dir = self.root / f"result-{label.replace(' ', '-')}"
            transport = CountingTransport()
            with mock.patch.object(
                physical,
                "validate_n5_physical_context",
                return_value=self.plan,
            ):
                with self.assertRaisesRegex(
                    physical.N5PhysicalExecutionError, label
                ):
                    physical.run_n5_physical_action_once(
                        self.context,
                        self.action_key,
                        production_files=files,
                        authorization=authorization,
                        session_start=session,
                        prior_bundle=None,
                        result_dir=result_dir,
                        claim_root=claim_root,
                        base_url="http://device",
                        action_token=supplied_action,
                        panel_plan_token=panel,
                        profile_token=profile,
                        start_temperature_c=23,
                        confirm_supply_cv_current_normal=True,
                        confirm_j2_on=True,
                        confirm_physical_cutoff_available=True,
                        wall_clock=clock,
                        transport=transport,
                    )
            self.assertEqual(transport.calls, [])
            self.assertFalse(claim_root.exists())
            self.assertFalse(result_dir.exists())

    def test_live_claim_uses_injected_clock_and_strict_finalize_replays(self) -> None:
        files, session, authorization, action, panel, profile = self._run_inputs(
            last_completed_at="2026-08-08T00:00:00Z"
        )
        claim_root = self.root / "claims-positive"
        result_dir = self.root / "result-positive"
        scripted = ScriptedRequester(map_responses())
        transport = n5_rc2g_protocol.make_http_transport(
            "http://device", requester=scripted
        )
        driver = n5_rc2g_protocol.make_protocol_driver(
            self.contract,
            self.action_key,
            None,
            base_url="http://device",
            sleeper=lambda _seconds: None,
            clock=TickClock(),
        )
        output = physical.run_n5_physical_action_once(
            self.context,
            self.action_key,
            production_files=files,
            authorization=authorization,
            session_start=session,
            prior_bundle=None,
            result_dir=result_dir,
            claim_root=claim_root,
            base_url="http://device",
            action_token=action,
            panel_plan_token=panel,
            profile_token=profile,
            start_temperature_c=23,
            confirm_supply_cv_current_normal=True,
            confirm_j2_on=True,
            confirm_physical_cutoff_available=True,
            wall_clock=SequenceClock(
                "2026-08-08T00:04:00Z", "2026-08-08T00:04:01Z"
            ),
            transport=transport,
            protocol_driver=driver,
        )
        self.assertEqual(output["state"], "PROTOCOL_PASS_AWAITING_MANUAL_FINALIZATION")
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        receipt = json.loads(
            (result_dir / fixed.RESULT_RECEIPT_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["claim"]["claimed_at"], "2026-08-08T00:04:01Z")
        manual = {
            "schema_version": 1,
            "kind": execution.MANUAL_OBSERVATION_KIND,
            "execution_contract_canonical_sha256": self.contract["integrity"][
                "canonical_sha256"
            ],
            "attempt_id": receipt["claim"]["attempt_id"],
            "action_key": self.action_key,
            "action_identity_sha256": self.entry["action_identity_sha256"],
            "protocol_evidence_file_sha256": receipt[
                "protocol_evidence_file_sha256"
            ],
            "observed_at": "2026-08-08T00:05:00Z",
            "source_observation_artifact_sha256": _hash_text("manual-observation"),
            "visual_pass": True,
            "electrical_pass": True,
            "thermal_pass": True,
            "measurement_pass": True,
            "continuity": execution.expected_continuity(
                self.contract, self.action_key
            ),
            "measurement_bindings": [],
            "notes": "physical N5 strict test",
        }
        finalized = physical.finalize_n5_physical_action(
            self.context,
            result_dir,
            manual_observation_payload=manual,
            claim_root=claim_root,
            profile_reviewer_key_file=self.profile_key,
            wall_clock=SequenceClock("2026-08-08T00:05:01Z"),
        )
        self.assertEqual(finalized["state"], "PASS")
        self.assertTrue(
            finalized["physical_replay"]["deep_production_profile_replayed"]
        )
        self.assertTrue(
            finalized["physical_replay"]["strict_rc2g_verified"]
        )
        item = json.loads(
            (result_dir / fixed.RESULT_ACTION_ITEM_FILE).read_text(encoding="utf-8")
        )
        second_entry = self.contract["actions"][1]
        second_key = second_entry["action_key"]
        second_snapshot = execution.load_action_snapshot(
            self.contract, second_key
        )
        second_files, second_profile = self._production(
            label="second",
            last_completed_at="2026-08-08T00:05:01Z",
            snapshot_at="2026-08-08T00:05:10Z",
            cumulative=2,
            session_count=2,
            consecutive=2,
            reviewed_at="2026-08-08T00:05:20Z",
            valid_from="2026-08-08T00:05:30Z",
            evaluated_at="2026-08-08T00:06:02Z",
        )
        second_authorization, second_action, second_panel, second_profile_token = (
            self._authorization(
                second_profile,
                session,
                snapshot=second_snapshot,
                entry=second_entry,
                issued_at="2026-08-08T00:06:02Z",
                authorization_id="N5-PHYSICAL-AUTH-SECOND-ACTION",
            )
        )
        missing_prior_transport = CountingTransport()
        missing_prior_result = self.root / "missing-prior-result"
        with mock.patch.object(
            physical,
            "validate_n5_physical_context",
            return_value=self.plan,
        ), self.assertRaisesRegex(
            physical.N5PhysicalExecutionError,
            "prior result directory",
        ):
            physical.run_n5_physical_action_once(
                self.context,
                second_key,
                production_files=second_files,
                authorization=second_authorization,
                session_start=session,
                prior_bundle=item,
                result_dir=missing_prior_result,
                claim_root=claim_root,
                base_url="http://device",
                action_token=second_action,
                panel_plan_token=second_panel,
                profile_token=second_profile_token,
                start_temperature_c=23,
                confirm_supply_cv_current_normal=True,
                confirm_j2_on=True,
                confirm_physical_cutoff_available=True,
                wall_clock=SequenceClock("2026-08-08T00:06:02Z"),
                transport=missing_prior_transport,
            )
        self.assertEqual(missing_prior_transport.calls, [])
        self.assertFalse(missing_prior_result.exists())
        second_frame = fixed.load_action_frame(self.contract, second_key)
        candidate = n5_rc2g_protocol._candidate_snapshot(
            second_snapshot, second_frame
        )
        first_evidence = item["protocol_evidence"]["device_evidence"]
        second_run = n5_rc2g_protocol._completed_run_contract(
            candidate,
            first_evidence["target_job_raw"],
            first_evidence["target_diagnostic_raw"],
            prior_frame_sha256=first_evidence["completed_action"]["frame_sha256"],
            prior_scope="exact preceding finalized N5 strict device evidence",
        )
        second_responses = quality_responses(second_frame, second_run)
        second_responses["/api/job"][0] = (
            200,
            json.dumps(first_evidence["target_job_raw"]),
        )
        second_responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(first_evidence["target_diagnostic_raw"]),
        )
        second_scripted = ScriptedRequester(second_responses)
        second_transport = n5_rc2g_protocol.make_http_transport(
            "http://device", requester=second_scripted
        )
        second_driver = n5_rc2g_protocol.make_protocol_driver(
            self.contract,
            second_key,
            item,
            base_url="http://device",
            sleeper=lambda _seconds: None,
            clock=TickClock(),
        )
        second_result_dir = self.root / "result-positive-second"
        with mock.patch.object(
            physical,
            "validate_n5_physical_context",
            return_value=self.plan,
        ):
            second_output = physical.run_n5_physical_action_once(
                self.context,
                second_key,
                production_files=second_files,
                authorization=second_authorization,
                session_start=session,
                prior_bundle=item,
                prior_result_dir=result_dir,
                result_dir=second_result_dir,
                claim_root=claim_root,
                base_url="http://device",
                action_token=second_action,
                panel_plan_token=second_panel,
                profile_token=second_profile_token,
                start_temperature_c=23,
                confirm_supply_cv_current_normal=True,
                confirm_j2_on=True,
                confirm_physical_cutoff_available=True,
                wall_clock=SequenceClock(
                    "2026-08-08T00:06:02Z", "2026-08-08T00:08:10Z"
                ),
                transport=second_transport,
                protocol_driver=second_driver,
            )
            self.assertEqual(
                second_output["state"],
                "PROTOCOL_PASS_AWAITING_MANUAL_FINALIZATION",
            )
            second_receipt = json.loads(
                (second_result_dir / fixed.RESULT_RECEIPT_FILE).read_text(
                    encoding="utf-8"
                )
            )
            second_manual = {
                "schema_version": 1,
                "kind": execution.MANUAL_OBSERVATION_KIND,
                "execution_contract_canonical_sha256": self.contract[
                    "integrity"
                ]["canonical_sha256"],
                "attempt_id": second_receipt["claim"]["attempt_id"],
                "action_key": second_key,
                "action_identity_sha256": second_entry[
                    "action_identity_sha256"
                ],
                "protocol_evidence_file_sha256": second_receipt[
                    "protocol_evidence_file_sha256"
                ],
                "observed_at": "2026-08-08T00:09:00Z",
                "source_observation_artifact_sha256": _hash_text(
                    "manual-observation-second"
                ),
                "visual_pass": True,
                "electrical_pass": True,
                "thermal_pass": True,
                "measurement_pass": True,
                "continuity": execution.expected_continuity(
                    self.contract, second_key
                ),
                "measurement_bindings": [],
                "notes": "physical N5 strict second action test",
            }
            second_finalized = physical.finalize_n5_physical_action(
                self.context,
                second_result_dir,
                manual_observation_payload=second_manual,
                claim_root=claim_root,
                profile_reviewer_key_file=self.profile_key,
                wall_clock=SequenceClock("2026-08-08T00:09:01Z"),
            )
            self.assertEqual(second_finalized["state"], "PASS")
        bundle_file = self.root / "physical-session-bundle.json"
        with mock.patch.object(
            physical,
            "validate_n5_physical_context",
            return_value=self.plan,
        ):
            built = physical.build_n5_physical_session_bundle(
                self.context,
                result_dirs=[result_dir, second_result_dir],
                session_starts=[session],
                finalized_at="2026-08-08T00:09:30Z",
                j2_cut_session_ids=[],
                profile_reviewer_key_file=self.profile_key,
                output_file=bundle_file,
            )
            self.assertTrue(built["physical_deep_replay"])
            bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
            bundle_summary = physical.validate_n5_physical_finalized_bundle(
                self.context,
                bundle,
                result_dirs=[result_dir, second_result_dir],
                profile_reviewer_key_file=self.profile_key,
            )
            self.assertTrue(bundle_summary["physical_deep_replay"])
            self.assertTrue(bundle_summary["strict_rc2g_verified"])
            with self.assertRaisesRegex(
                physical.N5PhysicalExecutionError, "duplicate"
            ):
                physical.validate_n5_physical_finalized_bundle(
                    self.context,
                    bundle,
                    result_dirs=[result_dir, result_dir],
                    profile_reviewer_key_file=self.profile_key,
                )
            cross_plan = deepcopy(bundle)
            cross_plan.pop("integrity")
            cross_plan["execution_contract_canonical_sha256"] = "0" * 64
            cross_plan = {
                **cross_plan,
                "integrity": execution._integrity(
                    cross_plan, execution.BUNDLE_HASH_SCOPE
                ),
            }
            with self.assertRaisesRegex(
                physical.N5PhysicalExecutionError,
                "cross-plan|strict physical",
            ):
                physical.validate_n5_physical_finalized_bundle(
                    self.context,
                    cross_plan,
                    result_dirs=[result_dir, second_result_dir],
                    profile_reviewer_key_file=self.profile_key,
                )

    def test_legacy_live_entry_is_hard_blocked_before_transport_or_claim(self) -> None:
        transport = CountingTransport()
        claim_root = self.root / "legacy-claims"
        result_dir = self.root / "legacy-result"
        with self.assertRaisesRegex(
            fixed.N5FixedExecutionToolError,
            "disabled before claim/network",
        ):
            fixed.run_fixed_action(
                self.materializer_inputs.source_manifest,
                action_key="does-not-matter",
                limit_profile={},
                profile_evaluated_at="caller-time",
                authorization={},
                session_start={},
                runtime_gates={},
                prior_bundle=None,
                attempt_id="caller-attempt",
                claimed_at="caller-claimed-at",
                protocol_completed_at="caller-completed-at",
                claim_root=claim_root,
                result_dir=result_dir,
                base_url="http://device",
                transport=transport,
            )
        self.assertEqual(transport.calls, [])
        self.assertFalse(claim_root.exists())
        self.assertFalse(result_dir.exists())

    def test_physical_cli_uses_neutral_authority_and_no_caller_claim_time(self) -> None:
        common = [
            "--physical-plan",
            "plan.json",
            "--compile-profile",
            "compile.json",
            "--source-manifest",
            "source.json",
            "--physical-anchor",
            "anchor.json",
            "--firmware-binary",
            "firmware.bin",
            "--science-review-evidence",
            "science.bin",
            "--science-review-approval",
            "science-approval.json",
            "--science-reviewer-key",
            "science.key",
            "--namespace",
            "n5-production",
            "--minimum-interval-seconds",
            "180",
            "--planned-cooldown-seconds",
            "240",
        ]
        production_args = [
            "--profile",
            "profile.json",
            "--physical-campaign",
            "campaign.json",
            "--limit-authority",
            "authority.json",
            "--usage-evidence",
            "usage.json",
            "--profile-review",
            "review.json",
            "--profile-reviewer-key",
            "profile.key",
        ]
        args = physical.parse_args(
            [
                "run",
                *common,
                *production_args,
                "--action",
                "action-key",
                "--authorization",
                "authorization.json",
                "--session-start",
                "session.json",
                "--result-dir",
                "result",
                "--url",
                "http://device",
                "--action-token",
                "action-token",
                "--panel-plan-token",
                "panel-token",
                "--profile-token",
                "profile-token",
                "--start-temperature-c",
                "23",
            ]
        )
        self.assertEqual(args.limit_authority, Path("authority.json"))
        self.assertFalse(hasattr(args, "claimed_at"))
        self.assertFalse(hasattr(args, "profile_evaluated_at"))
        self.assertFalse(hasattr(args, "attempt_id"))


if __name__ == "__main__":
    unittest.main()
