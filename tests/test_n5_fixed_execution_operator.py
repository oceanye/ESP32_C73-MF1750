from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import host.extended_color.execution as execution
from tests.n5_execution_fixture import (
    build_pass_bundle,
    dependency_closure,
    hash_text,
    reviewed_limit_profile,
    seal_external_authorization,
)
from tests.test_n5_compile_cli import _production_profile
from tools import mf1750_n5_fixed_execution as fixed
from tools import mf1750_n5_measurement_campaign as campaign


class N5FixedExecutionOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = campaign.compile_manifest_from_profile(_production_profile())
        cls.contract = fixed.compile_materialized_execution_contract(cls.manifest)
        cls.action = cls.contract["actions"][0]
        cls.snapshot = execution.load_action_snapshot(
            cls.contract, cls.action["action_key"]
        )
        cls.session_start = execution.seal_session_start(
            {
                "schema_version": 1,
                "kind": execution.SESSION_START_KIND,
                "session_id": cls.snapshot.session["session_id"],
                "observed_at": "2026-08-08T00:01:00Z",
                "power_mode": "supervised_continuous",
                "j2_initially_off": False,
                "measured_panel_power_off_seconds": None,
                "controller_fresh_boot_observed": False,
                "j2_on_before_first_action": True,
                "supply_cv_current_normal": True,
                "temperature_normal": True,
                "physical_cutoff_available": True,
                "observation_artifact_sha256": hash_text("operator-session-start"),
            },
            snapshot=cls.snapshot,
        )
        cls.authorization = seal_external_authorization(
            {
                "schema_version": 1,
                "kind": execution.AUTHORIZATION_KIND,
                "authorization_id": "AUTH-N5-OPERATOR-TEST-001",
                "action_identity_sha256": cls.action["action_identity_sha256"],
                "execution_contract_canonical_sha256": cls.contract["integrity"][
                    "canonical_sha256"
                ],
                "session_start_file_sha256": execution._sha256(cls.session_start),
                "issued_at": "2026-08-08T00:02:00Z",
                "expires_at": "2026-08-08T01:02:00Z",
                "operator_id": "n5-operator-test",
                "authorization_artifact_sha256": hash_text("operator-auth"),
                "confirmation_sha256": hash_text("operator-confirmation"),
                "maximum_post_requests": 1,
                "automatic_advance_authorized": False,
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            }
        )
        cls.profile = reviewed_limit_profile(
            cls.contract,
            last_visible_at=datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc),
            snapshot_at=datetime(2026, 8, 8, 0, 1, tzinfo=timezone.utc),
        )
        cls.runtime_gates = {
            "observed_at": "2026-08-08T00:02:30Z",
            "start_temperature_c": 23.0,
            "supply_cv_current_normal": True,
            "j2_on": True,
            "physical_cutoff_available": True,
            "operator_advance_artifact_sha256": hash_text("operator-advance"),
            "runtime_evidence_sha256": hash_text("operator-runtime"),
        }

    def _run(
        self,
        *,
        claim_root: Path,
        result_dir: Path,
        transport,
        driver,
    ) -> dict[str, object]:
        # Structural tests exercise the preserved one-POST engine directly;
        # the public legacy live boundary is intentionally hard-blocked.
        return fixed._run_fixed_action_core(
            self.manifest,
            contract=self.contract,
            action_key=self.action["action_key"],
            limit_profile=self.profile,
            profile_evaluated_at="2026-08-08T00:02:30Z",
            authorization=self.authorization,
            session_start=self.session_start,
            runtime_gates=self.runtime_gates,
            prior_bundle=None,
            attempt_id="attempt-n5-operator-001",
            claimed_at="2026-08-08T00:03:00Z",
            protocol_completed_at="2026-08-08T00:04:00Z",
            claim_root=claim_root,
            result_dir=result_dir,
            base_url="http://192.0.2.1",
            transport=transport,
            protocol_driver=driver,
        )

    def test_production_cli_does_not_expose_an_alternate_claim_root(self) -> None:
        argv = [
            "--manifest",
            "manifest.json",
            "run",
            "--action",
            "frozen-action",
            "--limit-profile",
            "limit.json",
            "--profile-evaluated-at",
            "2026-08-08T00:00:00Z",
            "--authorization",
            "authorization.json",
            "--session-start",
            "session.json",
            "--runtime-gates",
            "runtime.json",
            "--attempt-id",
            "attempt-1",
            "--claimed-at",
            "2026-08-08T00:01:00Z",
            "--protocol-completed-at",
            "2026-08-08T00:02:00Z",
            "--result-dir",
            "result",
            "--url",
            "http://device",
            "--claim-root",
            "alternate-registry",
        ]
        with mock.patch("sys.stderr", new=io.StringIO()), self.assertRaises(
            SystemExit
        ) as caught:
            fixed.parse_args(argv)
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(fixed.PRODUCTION_CLAIM_ROOT, fixed.REPO_ROOT)

    def test_formal_incomplete_measurement_finalizes_fail_and_stops_advance(
        self,
    ) -> None:
        terminal = next(
            entry
            for entry in self.contract["actions"]
            if entry["measurement_slots"]
        )
        included = dependency_closure(
            self.contract, [terminal["action_identity_sha256"]]
        )
        entries_by_sha = {
            entry["action_identity_sha256"]: entry
            for entry in self.contract["actions"]
        }
        bindings: dict[str, list[dict[str, object]]] = {}
        for action_sha in included:
            records = []
            for slot in entries_by_sha[action_sha]["measurement_slots"]:
                phase = slot["measurement_phase"]
                records.append(
                    {
                        "slot_id": slot["slot_id"],
                        "measurement_phase": phase,
                        "source_run_sha256": hash_text(
                            f"formal-source-{action_sha}-{slot['slot_id']}"
                        ),
                        "asset_manifest_sha256": hash_text(
                            f"formal-asset-{action_sha}-{slot['slot_id']}"
                        ),
                        "measurement_record_sha256": hash_text(
                            f"formal-measurement-{action_sha}-{slot['slot_id']}"
                        ),
                        "raw_spectrum_artifact_sha256": hash_text(
                            f"formal-raw-{action_sha}-{slot['slot_id']}"
                        ),
                        "spectral_report_file_sha256": hash_text(
                            f"formal-report-{action_sha}-{slot['slot_id']}"
                        ),
                        "metrics_sha256": (
                            hash_text(
                                f"formal-metrics-{action_sha}-{slot['slot_id']}"
                            )
                            if phase == "transition_final"
                            else None
                        ),
                    }
                )
            bindings[action_sha] = records
        pass_bundle = build_pass_bundle(
            self.contract,
            terminal_action_identity_sha256s=[
                terminal["action_identity_sha256"]
            ],
            measurement_bindings_by_action=bindings,
        )
        target_item = next(
            item
            for item in pass_bundle["actions"]
            if item["action_identity_sha256"]
            == terminal["action_identity_sha256"]
        )
        target_summary = execution._validate_action_item(
            self.contract, target_item
        )
        session_start = next(
            session["session_start"]
            for session in pass_bundle["sessions"]
            if session["finalization"]["session_id"]
            == target_summary["session_id"]
        )
        receipt = execution._seal(
            {
                "schema_version": 1,
                "kind": execution.PROTOCOL_RECEIPT_KIND,
                "authorization": target_item["authorization"],
                "authorization_file_sha256": target_item[
                    "authorization_file_sha256"
                ],
                "session_start": session_start,
                "session_start_file_sha256": execution._sha256(session_start),
                "profile": target_item["profile"],
                "profile_file_sha256": target_item["profile_file_sha256"],
                "claim": target_item["claim"],
                "claim_file_sha256": target_item["claim_file_sha256"],
                "protocol_evidence": target_item["protocol_evidence"],
                "protocol_evidence_file_sha256": target_item[
                    "protocol_evidence_file_sha256"
                ],
            }
        )
        complete_bindings = target_item["manual_observation"]["measurement_bindings"]
        self.assertGreaterEqual(len(complete_bindings), 2)
        for retained_count in (0, 1):
            with self.subTest(
                invalid_measurement_pass_binding_count=retained_count
            ), self.assertRaisesRegex(
                execution.N5ExecutionError,
                "measurement PASS does not bind every frozen measurement slot",
            ):
                invalid_pass = dict(target_item["manual_observation"])
                invalid_pass.pop("integrity")
                invalid_pass.update(
                    {
                        "visual_pass": False,
                        "electrical_pass": False,
                        "thermal_pass": False,
                        "measurement_pass": True,
                        "measurement_bindings": complete_bindings[:retained_count],
                        "notes": "manual gates failed with incomplete formal evidence",
                    }
                )
                execution.seal_manual_observation(
                    invalid_pass,
                    contract=self.contract,
                    action_key=terminal["action_key"],
                    attempt_id=target_item["claim"]["attempt_id"],
                    protocol_evidence_file_sha256=target_item[
                        "protocol_evidence_file_sha256"
                    ],
                )

        non_prefix_failure = dict(target_item["manual_observation"])
        non_prefix_failure.pop("integrity")
        non_prefix_failure.update(
            {
                "visual_pass": False,
                "measurement_pass": False,
                "measurement_bindings": complete_bindings[1:2],
                "notes": "formal measurement failed after a non-prefix slot",
            }
        )
        with self.assertRaisesRegex(
            execution.N5ExecutionError,
            "terminal FAIL/UNKNOWN measurement bindings must be a frozen ordered prefix",
        ):
            execution.seal_manual_observation(
                non_prefix_failure,
                contract=self.contract,
                action_key=terminal["action_key"],
                attempt_id=target_item["claim"]["attempt_id"],
                protocol_evidence_file_sha256=target_item[
                    "protocol_evidence_file_sha256"
                ],
            )

        manual_payload = dict(target_item["manual_observation"])
        manual_payload.pop("integrity")
        manual_payload["measurement_pass"] = False
        manual_payload["measurement_bindings"] = []
        manual_payload["notes"] = "instrument fault; no formal slots accepted"
        failed_manual = execution.seal_manual_observation(
            manual_payload,
            contract=self.contract,
            action_key=terminal["action_key"],
            attempt_id=target_item["claim"]["attempt_id"],
            protocol_evidence_file_sha256=target_item[
                "protocol_evidence_file_sha256"
            ],
        )
        failed_item = execution.finalize_protocol_receipt(
            self.contract,
            receipt,
            failed_manual,
            completed_at=target_item["finalization"]["completed_at"],
        )
        self.assertEqual(failed_item["result"]["state"], "FAIL")
        action_items = [
            failed_item
            if item["action_identity_sha256"]
            == terminal["action_identity_sha256"]
            else item
            for item in pass_bundle["actions"]
        ]
        stopped = execution.build_finalized_bundle(
            self.contract,
            action_items,
            [session["session_start"] for session in pass_bundle["sessions"]],
            finalized_at=pass_bundle["finalized_at"],
            j2_cut_session_ids=[target_summary["session_id"]],
        )
        summary = execution.validate_finalized_bundle(self.contract, stopped)
        self.assertEqual(summary["state"], "abnormal-stop")
        self.assertIn(
            next(
                entry["action_identity_sha256"]
                for entry in self.contract["actions"]
                if entry["plan_class"] == terminal["plan_class"]
                and entry["order"] > terminal["order"]
            ),
            stopped["termination"]["ineligible_action_identity_sha256s"],
        )

    def test_claim_precedes_first_device_io_and_second_claim_never_replays(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()
            calls: list[tuple[str, str]] = []

            def transport(method: str, endpoint: str, _data: bytes | None) -> object:
                claims = list(
                    (claim_root / execution.CLAIM_REGISTRY_RELATIVE_PATH).glob(
                        "*.json"
                    )
                )
                self.assertEqual(len(claims), 1)
                calls.append((method, endpoint))
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                audited.request("GET", "/api/job")
                return {"scripted_loopback_only": True}

            result = self._run(
                claim_root=claim_root,
                result_dir=root / "first-result",
                transport=transport,
                driver=driver,
            )
            self.assertEqual(
                result["state"], "PROTOCOL_PASS_AWAITING_MANUAL_FINALIZATION"
            )
            self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
            calls_before_second_claim = list(calls)

            with self.assertRaises(execution.N5ClaimConsumedError):
                self._run(
                    claim_root=claim_root,
                    result_dir=root / "second-result",
                    transport=transport,
                    driver=driver,
                )

            self.assertEqual(calls, calls_before_second_claim)
            outcome_commit = (
                root
                / "first-result"
                / fixed.RESULT_PROTOCOL_OUTCOME_COMMIT_FILE
            )
            self.assertTrue(outcome_commit.is_file())
            outcome_commit.write_bytes(b'{"tampered":true}')
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError,
                "outcome transaction commit differs",
            ):
                fixed.finalize_fixed_action(
                    manifest=self.manifest,
                    result_dir=root / "first-result",
                    manual_observation_payload={},
                    completed_at="2026-08-08T00:05:00Z",
                    claim_root=claim_root,
                )

    def test_protocol_error_is_unknown_permanent_and_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()
            calls: list[tuple[str, str]] = []

            def transport(method: str, endpoint: str, _data: bytes | None) -> object:
                calls.append((method, endpoint))
                return {"status": 200}

            def wrong_report_driver(
                audited: execution.AuditedTransport, frame: bytes
            ) -> dict[str, bool]:
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                audited.request("GET", "/api/diagnostic/report")
                raise ValueError("scripted wrong completed-job report")

            result = self._run(
                claim_root=claim_root,
                result_dir=root / "unknown-result",
                transport=transport,
                driver=wrong_report_driver,
            )
            self.assertEqual(result["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertTrue((root / "unknown-result" / fixed.RESULT_RECEIPT_FILE).is_file())
            receipt = fixed._strict_json_file(
                root / "unknown-result" / fixed.RESULT_RECEIPT_FILE,
                label="test receipt",
            )
            self.assertEqual(
                receipt["protocol_evidence"]["outcome"], "UNKNOWN_DO_NOT_RETRY"
            )
            self.assertTrue(
                (
                    root
                    / "unknown-result"
                    / fixed.RESULT_PROTOCOL_TERMINAL_READY_FILE
                ).is_file()
            )
            finalized = fixed.finalize_fixed_action(
                manifest=self.manifest,
                result_dir=root / "unknown-result",
                manual_observation_payload={
                    "schema_version": 1,
                    "kind": execution.MANUAL_OBSERVATION_KIND,
                    "execution_contract_canonical_sha256": self.contract[
                        "integrity"
                    ]["canonical_sha256"],
                    "attempt_id": "attempt-n5-operator-001",
                    "action_key": self.action["action_key"],
                    "action_identity_sha256": self.action[
                        "action_identity_sha256"
                    ],
                    "protocol_evidence_file_sha256": receipt[
                        "protocol_evidence_file_sha256"
                    ],
                    "observed_at": "2026-08-08T00:05:00Z",
                    "source_observation_artifact_sha256": hash_text(
                        "unknown-terminal-observation"
                    ),
                    "visual_pass": False,
                    "electrical_pass": False,
                    "thermal_pass": False,
                    "measurement_pass": False,
                    "continuity": execution.expected_continuity(
                        self.contract, self.action["action_key"]
                    ),
                    "measurement_bindings": [],
                    "notes": "protocol outcome unknown; operator cut J2",
                },
                completed_at="2026-08-08T00:06:00Z",
                claim_root=claim_root,
            )
            self.assertEqual(finalized["state"], "UNKNOWN_DO_NOT_RETRY")
            unknown_item = fixed._load_finalized_action_item(
                root / "unknown-result" / fixed.RESULT_ACTION_ITEM_FILE
            )
            unknown_bundle = execution.build_finalized_bundle(
                self.contract,
                [unknown_item],
                [self.session_start],
                finalized_at="2026-08-08T00:07:00Z",
                j2_cut_session_ids=[self.snapshot.session["session_id"]],
            )
            self.assertEqual(unknown_bundle["termination"]["state"], "abnormal-stop")
            self.assertTrue(
                unknown_bundle["sessions"][0]["finalization"][
                    "manual_j2_cut_after_terminal_action"
                ]
            )
            with self.assertRaisesRegex(
                execution.N5ExecutionError, "not PASS"
            ):
                execution.describe_fixed_action(
                    self.contract,
                    self.contract["actions"][1]["action_key"],
                    limit_profile=self.profile,
                    evaluated_at="2026-08-08T00:06:30Z",
                    prior_bundle=unknown_item,
                )
            self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
            before = list(calls)
            with self.assertRaises(execution.N5ClaimConsumedError):
                self._run(
                    claim_root=claim_root,
                    result_dir=root / "forbidden-retry",
                    transport=transport,
                    driver=wrong_report_driver,
                )
            self.assertEqual(calls, before)

    def test_unknown_receipt_rechecks_tampered_disk_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def tampering_driver(
                audited: execution.AuditedTransport, frame: bytes
            ) -> dict[str, bool]:
                audited.request("POST", "/api/frame", frame)
                claim = next(
                    (claim_root / execution.CLAIM_REGISTRY_RELATIVE_PATH).glob(
                        "*.json"
                    )
                )
                claim.write_bytes(b'{"tampered":true}')
                raise ValueError("scripted post-claim failure after claim tamper")

            result = self._run(
                claim_root=claim_root,
                result_dir=root / "unknown-tampered-claim",
                transport=transport,
                driver=tampering_driver,
            )

            self.assertEqual(result["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertTrue(result["terminal_incident_persisted"])
            self.assertTrue(
                (
                    root
                    / "unknown-tampered-claim"
                    / fixed.RESULT_CLAIM_COMMIT_UNKNOWN_FILE
                ).is_file()
            )

    def test_post_claim_receipt_publication_failure_stays_terminal_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()
            calls: list[tuple[str, str]] = []

            def transport(method: str, endpoint: str, _data: bytes | None) -> object:
                calls.append((method, endpoint))
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"scripted_loopback_only": True}

            original_publish = fixed._publish_json

            def fail_receipt(path: Path, value):
                if path.name == fixed.RESULT_RECEIPT_FILE:
                    raise fixed.N5FixedExecutionToolError("injected receipt publish failure")
                return original_publish(path, value)

            with mock.patch.object(fixed, "_publish_json", side_effect=fail_receipt):
                result = self._run(
                    claim_root=claim_root,
                    result_dir=root / "publication-failed",
                    transport=transport,
                    driver=driver,
                )

            self.assertEqual(result["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertTrue(result["terminal_incident_persisted"])
            self.assertTrue(
                (
                    root
                    / "publication-failed"
                    / fixed.RESULT_CLAIM_COMMIT_UNKNOWN_FILE
                ).is_file()
            )
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "permanently UNKNOWN_DO_NOT_RETRY"
            ):
                fixed.finalize_fixed_action(
                    manifest=self.manifest,
                    result_dir=root / "publication-failed",
                    manual_observation_payload={},
                    completed_at="2026-08-08T00:05:00Z",
                    claim_root=claim_root,
                )
            before = list(calls)
            self.assertEqual(sum(method == "POST" for method, _endpoint in before), 1)
            with self.assertRaises(execution.N5ClaimConsumedError):
                self._run(
                    claim_root=claim_root,
                    result_dir=root / "forbidden-after-publish-failure",
                    transport=transport,
                    driver=driver,
                )
            self.assertEqual(calls, before)

    def test_finalized_action_publication_is_idempotently_recoverable(self) -> None:
        manual = {"record": "manual"}
        finalization = {"record": "finalization"}
        result = {"record": "result", "state": "PASS"}
        item = {
            "action_key": "frozen-action",
            "action_identity_sha256": "1" * 64,
            "manual_observation": manual,
            "manual_observation_file_sha256": execution._sha256(manual),
            "finalization": finalization,
            "finalization_file_sha256": execution._sha256(finalization),
            "result": result,
            "result_file_sha256": execution._sha256(result),
            "record": "complete-action-item",
        }
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            original_publish = fixed._publish_json
            failed = False

            def fail_one_derived_file(path: Path, value):
                nonlocal failed
                if path.name == fixed.RESULT_FINALIZATION_FILE and not failed:
                    failed = True
                    raise fixed.N5FixedExecutionToolError(
                        "injected derived-view publication failure"
                    )
                return original_publish(path, value)

            with mock.patch.object(
                fixed, "_publish_json", side_effect=fail_one_derived_file
            ), self.assertRaises(fixed.N5FixedExecutionToolError):
                fixed._publish_finalized_action_files(
                    destination,
                    item,
                    protocol_outcome_ready_file_sha256="2" * 64,
                )

            self.assertTrue((destination / fixed.RESULT_ACTION_ITEM_FILE).is_file())
            self.assertFalse(
                (destination / fixed.RESULT_FINALIZED_COMMIT_FILE).exists()
            )
            hashes = fixed._publish_finalized_action_files(
                destination,
                item,
                protocol_outcome_ready_file_sha256="2" * 64,
            )
            self.assertEqual(len(hashes), 5)
            self.assertEqual(
                fixed._publish_finalized_action_files(
                    destination,
                    item,
                    protocol_outcome_ready_file_sha256="2" * 64,
                ),
                hashes,
            )
            (destination / fixed.RESULT_MANUAL_FILE).write_bytes(b'{"drift":true}')
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "identity drift"
            ):
                fixed._publish_finalized_action_files(
                    destination,
                    item,
                    protocol_outcome_ready_file_sha256="2" * 64,
                )

    def test_missing_ready_blocks_finalization_even_if_incident_marker_write_failed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()
            captured_receipts: list[dict[str, object]] = []

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"scripted_loopback_only": True}

            original_publish = fixed._publish_json

            def fail_receipt_and_incident(path: Path, value):
                if path.name == fixed.RESULT_RECEIPT_FILE:
                    captured_receipts.append(dict(value))
                    raise fixed.N5FixedExecutionToolError("injected receipt failure")
                if path.name == fixed.RESULT_CLAIM_COMMIT_UNKNOWN_FILE:
                    raise fixed.N5FixedExecutionToolError("injected incident failure")
                return original_publish(path, value)

            with mock.patch.object(
                fixed, "_publish_json", side_effect=fail_receipt_and_incident
            ):
                outcome = self._run(
                    claim_root=claim_root,
                    result_dir=root / "double-persistence-failure",
                    transport=transport,
                    driver=driver,
                )

            self.assertEqual(outcome["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertFalse(outcome["terminal_incident_persisted"])
            self.assertEqual(len(captured_receipts), 1)
            original_publish(
                root / "double-persistence-failure" / fixed.RESULT_RECEIPT_FILE,
                captured_receipts[0],
            )
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "outcome-ready commit is absent"
            ):
                fixed.finalize_fixed_action(
                    manifest=self.manifest,
                    result_dir=root / "double-persistence-failure",
                    manual_observation_payload={},
                    completed_at="2026-08-08T00:05:00Z",
                    claim_root=claim_root,
                )

    def test_orphan_ready_after_readback_and_incident_failure_cannot_finalize(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"scripted_loopback_only": True}

            original_publish = fixed._publish_json

            def publish_then_fail_ready_and_fail_incident(path: Path, value):
                if path.name == fixed.RESULT_PROTOCOL_PASS_READY_FILE:
                    original_publish(path, value)
                    raise OSError("injected post-publication READY readback failure")
                if path.name == fixed.RESULT_CLAIM_COMMIT_UNKNOWN_FILE:
                    raise OSError("injected incident marker publication failure")
                return original_publish(path, value)

            with mock.patch.object(
                fixed,
                "_publish_json",
                side_effect=publish_then_fail_ready_and_fail_incident,
            ):
                outcome = self._run(
                    claim_root=claim_root,
                    result_dir=root / "orphan-ready",
                    transport=transport,
                    driver=driver,
                )

            directory = root / "orphan-ready"
            self.assertEqual(outcome["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertFalse(outcome["terminal_incident_persisted"])
            self.assertTrue(
                (directory / fixed.RESULT_PROTOCOL_PASS_READY_FILE).is_file()
            )
            self.assertFalse(
                (directory / fixed.RESULT_PROTOCOL_OUTCOME_COMMIT_FILE).exists()
            )
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError,
                "outcome transaction commit is absent",
            ):
                fixed.finalize_fixed_action(
                    manifest=self.manifest,
                    result_dir=directory,
                    manual_observation_payload={},
                    completed_at="2026-08-08T00:05:00Z",
                    claim_root=claim_root,
                )

    def test_both_ready_builders_reject_boolean_post_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def pass_driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"scripted_loopback_only": True}

            pass_claim_root = root / "pass-claim"
            pass_claim_root.mkdir()
            self._run(
                claim_root=pass_claim_root,
                result_dir=root / "pass-result",
                transport=transport,
                driver=pass_driver,
            )
            pass_receipt = dict(
                fixed._strict_json_file(
                    root / "pass-result" / fixed.RESULT_RECEIPT_FILE,
                    label="PASS receipt",
                )
            )
            pass_receipt = deepcopy(pass_receipt)
            pass_receipt["protocol_evidence"]["request_audit"][
                "post_attempt_count"
            ] = True
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "exact one-POST PASS"
            ):
                fixed._build_protocol_pass_ready(pass_receipt)

            def unknown_driver(
                audited: execution.AuditedTransport, frame: bytes
            ) -> dict[str, bool]:
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                raise ValueError("scripted terminal outcome")

            unknown_claim_root = root / "unknown-claim"
            unknown_claim_root.mkdir()
            self._run(
                claim_root=unknown_claim_root,
                result_dir=root / "unknown-result",
                transport=transport,
                driver=unknown_driver,
            )
            unknown_receipt = dict(
                fixed._strict_json_file(
                    root / "unknown-result" / fixed.RESULT_RECEIPT_FILE,
                    label="UNKNOWN receipt",
                )
            )
            unknown_receipt = deepcopy(unknown_receipt)
            unknown_receipt["protocol_evidence"]["request_audit"][
                "post_issued_count"
            ] = True
            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "core-validated UNKNOWN"
            ):
                fixed._build_protocol_terminal_ready(unknown_receipt)

    def test_disk_claim_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claim-root"
            claim_root.mkdir()

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes):
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                return {"scripted_loopback_only": True}

            self._run(
                claim_root=claim_root,
                result_dir=root / "result",
                transport=transport,
                driver=driver,
            )
            receipt = fixed._strict_json_file(
                root / "result" / fixed.RESULT_RECEIPT_FILE,
                label="test receipt",
            )
            claim_path = (
                claim_root
                / execution.CLAIM_REGISTRY_RELATIVE_PATH
                / receipt["claim"]["filename"]
            )
            claim_path.write_bytes(b'{"tampered":true}')

            with self.assertRaisesRegex(
                fixed.N5FixedExecutionToolError, "disk claim differs"
            ):
                fixed._verify_permanent_claim(receipt, claim_root=claim_root)


if __name__ == "__main__":
    unittest.main()
