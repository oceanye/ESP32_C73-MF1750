from __future__ import annotations

import copy
import contextlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from host.extended_color import execution
from host.extended_color import n5_rc2g_protocol as protocol
from tests.n5_execution_fixture import (
    hash_text,
    reviewed_limit_profile,
    seal_external_authorization,
)
from tests.test_g1_s1_rc2g_map_baseline_once import (
    ScriptedRequester,
    TickClock,
    _responses as map_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    _responses as quality_responses,
)
from tests.test_n5_compile_cli import _production_profile
from tools import mf1750_n5_measurement_campaign as campaign
from tools.mf1750_n5_fixed_execution import (
    compile_default_execution_contract,
    load_action_frame,
)
from tools import mf1750_n5_fixed_execution as fixed


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class N5Rc2gProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = compile_default_execution_contract()
        cls.first_entry = cls.contract["actions"][0]
        cls.second_entry = cls.contract["actions"][1]
        cls.first_snapshot = execution.load_action_snapshot(
            cls.contract, cls.first_entry["action_key"]
        )
        cls.second_snapshot = execution.load_action_snapshot(
            cls.contract, cls.second_entry["action_key"]
        )
        cls.third_entry = cls.contract["actions"][2]
        cls.third_snapshot = execution.load_action_snapshot(
            cls.contract, cls.third_entry["action_key"]
        )
        if (
            cls.first_snapshot.session["session_id"]
            != cls.second_snapshot.session["session_id"]
        ):
            raise AssertionError("focused fixture requires one two-action session")
        cls.full_manifest = campaign.compile_manifest_from_profile(
            _production_profile()
        )
        cls.full_contract = execution.compile_execution_contract(cls.full_manifest)
        cls.cold_entry = next(
            entry
            for entry in cls.full_contract["actions"]
            if entry["session_power_mode"] == "panel_cold_cycle"
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.claim_store = execution.AtomicWorkspaceClaimStore(self.root)
        self.base_time = datetime(2026, 8, 8, tzinfo=timezone.utc)
        self.session_start = execution.seal_session_start(
            {
                "schema_version": 1,
                "kind": execution.SESSION_START_KIND,
                "session_id": self.first_snapshot.session["session_id"],
                "observed_at": _timestamp(self.base_time + timedelta(minutes=1)),
                "power_mode": "supervised_continuous",
                "j2_initially_off": False,
                "measured_panel_power_off_seconds": None,
                "controller_fresh_boot_observed": False,
                "j2_on_before_first_action": True,
                "supply_cv_current_normal": True,
                "temperature_normal": True,
                "physical_cutoff_available": True,
                "observation_artifact_sha256": hash_text("n5-rc2g-session"),
            },
            snapshot=self.first_snapshot,
        )

    def _authorization(
        self,
        entry: dict[str, object],
        *,
        issued_at: datetime,
    ) -> dict[str, object]:
        action_key = str(entry["action_key"])
        return seal_external_authorization(
            {
                "schema_version": 1,
                "kind": execution.AUTHORIZATION_KIND,
                "authorization_id": f"AUTH-{action_key}",
                "action_identity_sha256": entry["action_identity_sha256"],
                "execution_contract_canonical_sha256": self.contract["integrity"][
                    "canonical_sha256"
                ],
                "session_start_file_sha256": execution._sha256(
                    self.session_start
                ),
                "issued_at": _timestamp(issued_at),
                "expires_at": _timestamp(issued_at + timedelta(hours=1)),
                "operator_id": "n5-rc2g-test-operator",
                "authorization_artifact_sha256": hash_text(
                    f"authorization-{action_key}"
                ),
                "confirmation_sha256": hash_text(f"confirmation-{action_key}"),
                "maximum_post_requests": 1,
                "automatic_advance_authorized": False,
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            }
        )

    def _execute(
        self,
        entry: dict[str, object],
        scripted: ScriptedRequester,
        *,
        prior_item: dict[str, object] | None,
        minute: int,
    ) -> dict[str, object]:
        action_key = str(entry["action_key"])
        previous = self.base_time + timedelta(minutes=minute - 2)
        evaluated = self.base_time + timedelta(minutes=minute - 1)
        claimed = self.base_time + timedelta(minutes=minute)
        frame = load_action_frame(self.contract, action_key)
        driver = protocol.make_protocol_driver(
            self.contract,
            action_key,
            prior_item,
            base_url="http://device",
            sleeper=lambda _seconds: None,
            clock=TickClock(),
        )
        receipt = execution.execute_fixed_action_once(
            self.contract,
            action_key,
            frame,
            limit_profile=reviewed_limit_profile(
                self.contract,
                last_visible_at=previous,
                snapshot_at=evaluated - timedelta(seconds=30),
            ),
            profile_evaluated_at=_timestamp(evaluated),
            authorization=self._authorization(entry, issued_at=evaluated),
            session_start=self.session_start,
            runtime_gates={
                "observed_at": _timestamp(evaluated),
                "start_temperature_c": 23.0,
                "supply_cv_current_normal": True,
                "j2_on": True,
                "physical_cutoff_available": True,
                "operator_advance_artifact_sha256": hash_text(
                    f"advance-{action_key}"
                ),
                "runtime_evidence_sha256": hash_text(f"runtime-{action_key}"),
            },
            prior_bundle=prior_item,
            attempt_id=f"attempt-{entry['order']}",
            claimed_at=_timestamp(claimed),
            protocol_completed_at=_timestamp(claimed + timedelta(minutes=1)),
            claim_store=self.claim_store,
            transport=protocol.make_http_transport(
                "http://device", requester=scripted
            ),
            protocol_driver=driver,
        )
        manual = execution.seal_manual_observation(
            {
                "schema_version": 1,
                "kind": execution.MANUAL_OBSERVATION_KIND,
                "execution_contract_canonical_sha256": self.contract["integrity"][
                    "canonical_sha256"
                ],
                "attempt_id": f"attempt-{entry['order']}",
                "action_key": action_key,
                "action_identity_sha256": entry["action_identity_sha256"],
                "protocol_evidence_file_sha256": receipt[
                    "protocol_evidence_file_sha256"
                ],
                "observed_at": _timestamp(claimed + timedelta(minutes=2)),
                "source_observation_artifact_sha256": hash_text(
                    f"manual-{action_key}"
                ),
                "visual_pass": True,
                "electrical_pass": True,
                "thermal_pass": True,
                "measurement_pass": True,
                "continuity": execution.expected_continuity(
                    self.contract, action_key
                ),
                "measurement_bindings": [],
                "notes": "scripted strict RC2G test",
            },
            contract=self.contract,
            action_key=action_key,
            attempt_id=f"attempt-{entry['order']}",
            protocol_evidence_file_sha256=receipt[
                "protocol_evidence_file_sha256"
            ],
        )
        return execution.finalize_protocol_receipt(
            self.contract,
            receipt,
            manual,
            completed_at=_timestamp(claimed + timedelta(minutes=3)),
        )

    def _first_item(self) -> tuple[dict[str, object], ScriptedRequester]:
        action_sha = str(self.first_entry["action_identity_sha256"])
        claim_path = (
            self.root
            / execution.CLAIM_REGISTRY_RELATIVE_PATH
            / f"{action_sha}.json"
        )
        scripted = ScriptedRequester(
            map_responses(), before_first_call=lambda: self.assertTrue(claim_path.is_file())
        )
        return (
            self._execute(
                self.first_entry, scripted, prior_item=None, minute=4
            ),
            scripted,
        )

    def _second_script(self, first_item: dict[str, object]) -> ScriptedRequester:
        frame = load_action_frame(
            self.contract, str(self.second_entry["action_key"])
        )
        candidate = protocol._candidate_snapshot(self.second_snapshot, frame)
        first_evidence = first_item["protocol_evidence"]["device_evidence"]
        run = protocol._completed_run_contract(
            candidate,
            first_evidence["target_job_raw"],
            first_evidence["target_diagnostic_raw"],
            prior_frame_sha256=first_evidence["completed_action"]["frame_sha256"],
            prior_scope="exact preceding finalized N5 strict device evidence",
        )
        responses = quality_responses(frame, run)
        responses["/api/job"][0] = (
            200,
            json.dumps(first_evidence["target_job_raw"]),
        )
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(first_evidence["target_diagnostic_raw"]),
        )
        return ScriptedRequester(responses)

    def _two_items(
        self,
    ) -> tuple[dict[str, object], dict[str, object], ScriptedRequester]:
        first, _first_scripted = self._first_item()
        second_scripted = self._second_script(first)
        second = self._execute(
            self.second_entry,
            second_scripted,
            prior_item=first,
            minute=9,
        )
        return first, second, second_scripted

    def _refinalize_with_device_evidence(
        self,
        item: dict[str, object],
        device_evidence: dict[str, object],
    ) -> dict[str, object]:
        protocol_record = copy.deepcopy(item["protocol_evidence"])
        protocol_record.pop("integrity")
        protocol_record["device_evidence"] = device_evidence
        protocol_record["device_evidence_sha256"] = execution._sha256(
            device_evidence
        )
        protocol_record = execution._seal(protocol_record)
        receipt = execution._seal(
            {
                "schema_version": 1,
                "kind": execution.PROTOCOL_RECEIPT_KIND,
                "authorization": item["authorization"],
                "authorization_file_sha256": item["authorization_file_sha256"],
                "session_start": self.session_start,
                "session_start_file_sha256": execution._sha256(self.session_start),
                "profile": item["profile"],
                "profile_file_sha256": item["profile_file_sha256"],
                "claim": item["claim"],
                "claim_file_sha256": item["claim_file_sha256"],
                "protocol_evidence": protocol_record,
                "protocol_evidence_file_sha256": execution._sha256(protocol_record),
            }
        )
        manual_payload = copy.deepcopy(item["manual_observation"])
        manual_payload.pop("integrity")
        manual_payload["protocol_evidence_file_sha256"] = receipt[
            "protocol_evidence_file_sha256"
        ]
        manual = execution.seal_manual_observation(
            manual_payload,
            contract=self.contract,
            action_key=str(item["action_key"]),
            attempt_id=str(item["claim"]["attempt_id"]),
            protocol_evidence_file_sha256=receipt[
                "protocol_evidence_file_sha256"
            ],
        )
        return execution.finalize_protocol_receipt(
            self.contract,
            receipt,
            manual,
            completed_at=str(item["finalization"]["completed_at"]),
        )

    def test_supervised_dynamic_root_claims_before_first_get_and_posts_once(self) -> None:
        item, scripted = self._first_item()
        evidence = item["protocol_evidence"]["device_evidence"]
        self.assertEqual(
            evidence["preflight_mode"], protocol.PREFLIGHT_SUPERVISED_FRESH
        )
        self.assertEqual(evidence["completed_action"]["job_id"], 1)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        validated = protocol.validate_strict_action_item(self.contract, item)
        self.assertIs(validated["strict_rc2g_verified"], True)

    def test_two_version_reads_bind_independently_when_free_psram_changes(self) -> None:
        responses = map_responses()
        status, second_version = responses["/api/version"][1]
        responses["/api/version"][1] = (
            status,
            second_version.replace("Free PSRAM: 7900000", "Free PSRAM: 7800000"),
        )
        item = self._execute(
            self.first_entry,
            ScriptedRequester(responses),
            prior_item=None,
            minute=4,
        )
        evidence = item["protocol_evidence"]["device_evidence"]
        self.assertNotEqual(
            evidence["preflight"]["version"]["free_psram"],
            evidence["network_report"]["preflight"]["free_psram"],
        )
        validated = protocol.validate_strict_action_item(self.contract, item)
        self.assertIs(validated["strict_rc2g_verified"], True)

    def test_supervised_root_accepts_one_strict_live_completed_baseline(self) -> None:
        first, _first_scripted = self._first_item()
        first_evidence = first["protocol_evidence"]["device_evidence"]
        action_key = str(self.third_entry["action_key"])
        frame = load_action_frame(self.contract, action_key)
        candidate = protocol._candidate_snapshot(self.third_snapshot, frame)
        run = protocol._completed_run_contract(
            candidate,
            first_evidence["target_job_raw"],
            first_evidence["target_diagnostic_raw"],
            prior_frame_sha256=None,
            prior_scope="live strict RC2G report; firmware does not expose SHA-256",
        )
        responses = quality_responses(frame, run)
        responses["/api/job"][0] = (
            200,
            json.dumps(first_evidence["target_job_raw"]),
        )
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(first_evidence["target_diagnostic_raw"]),
        )
        scripted = ScriptedRequester(responses)
        audited = execution.AuditedTransport(
            protocol.make_http_transport("http://device", requester=scripted),
            endpoint="/api/frame",
            frame_sha256=str(self.third_entry["frame_sha256"]),
        )
        driver = protocol.make_protocol_driver(
            self.contract,
            action_key,
            base_url="http://device",
            sleeper=lambda _seconds: None,
            clock=TickClock(),
        )
        evidence = driver(audited, frame)
        self.assertEqual(
            evidence["preflight_mode"], protocol.PREFLIGHT_SUPERVISED_COMPLETED
        )
        self.assertEqual(evidence["preflight"]["job_raw"]["job_id"], 1)
        self.assertEqual(evidence["completed_action"]["job_id"], 2)
        self.assertEqual(audited.snapshot()["post_issued_count"], 1)

    def test_panel_cold_session_root_requires_fresh_job0_preflight(self) -> None:
        action_key = str(self.cold_entry["action_key"])
        frame = load_action_frame(self.full_contract, action_key)
        scripted = ScriptedRequester(map_responses())
        audited = execution.AuditedTransport(
            protocol.make_http_transport("http://device", requester=scripted),
            endpoint="/api/frame",
            frame_sha256=str(self.cold_entry["frame_sha256"]),
        )
        driver = protocol.make_protocol_driver(
            self.full_contract,
            action_key,
            base_url="http://device",
            sleeper=lambda _seconds: None,
            clock=TickClock(),
        )
        evidence = driver(audited, frame)
        self.assertEqual(
            evidence["preflight_mode"], protocol.PREFLIGHT_PANEL_COLD
        )
        self.assertEqual(evidence["preflight"]["job_raw"]["job_id"], 0)
        self.assertEqual(evidence["completed_action"]["job_id"], 1)
        self.assertEqual(audited.snapshot()["post_issued_count"], 1)

    def test_production_cli_run_uses_real_localhost_http_and_strictly_replays(
        self,
    ) -> None:
        contract = self.full_contract
        entry = contract["actions"][0]
        action_key = str(entry["action_key"])
        snapshot = execution.load_action_snapshot(contract, action_key)
        frame = load_action_frame(contract, action_key)
        observed = self.base_time + timedelta(minutes=1)
        evaluated = self.base_time + timedelta(minutes=3)
        claimed = self.base_time + timedelta(minutes=4)
        session_start = execution.seal_session_start(
            {
                "schema_version": 1,
                "kind": execution.SESSION_START_KIND,
                "session_id": snapshot.session["session_id"],
                "observed_at": _timestamp(observed),
                "power_mode": snapshot.session["power_mode"],
                "j2_initially_off": False,
                "measured_panel_power_off_seconds": None,
                "controller_fresh_boot_observed": False,
                "j2_on_before_first_action": True,
                "supply_cv_current_normal": True,
                "temperature_normal": True,
                "physical_cutoff_available": True,
                "observation_artifact_sha256": hash_text("loopback-session"),
            },
            snapshot=snapshot,
        )
        limit_profile = reviewed_limit_profile(
            contract,
            last_visible_at=self.base_time + timedelta(minutes=2),
            snapshot_at=evaluated - timedelta(seconds=30),
        )
        authorization = seal_external_authorization(
            {
                "schema_version": 1,
                "kind": execution.AUTHORIZATION_KIND,
                "authorization_id": "AUTH-N5-LOCALHOST-LOOPBACK",
                "action_identity_sha256": entry["action_identity_sha256"],
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "session_start_file_sha256": execution._sha256(session_start),
                "issued_at": _timestamp(evaluated),
                "expires_at": _timestamp(evaluated + timedelta(hours=1)),
                "operator_id": "n5-loopback-test-operator",
                "authorization_artifact_sha256": hash_text("loopback-auth"),
                "confirmation_sha256": hash_text("loopback-confirmation"),
                "maximum_post_requests": 1,
                "automatic_advance_authorized": False,
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            }
        )
        runtime_gates = {
            "observed_at": _timestamp(evaluated),
            "start_temperature_c": 23.0,
            "supply_cv_current_normal": True,
            "j2_on": True,
            "physical_cutoff_available": True,
            "operator_advance_artifact_sha256": hash_text("loopback-advance"),
            "runtime_evidence_sha256": hash_text("loopback-runtime"),
        }
        external = self.root / "external"
        external.mkdir()

        def publish(name: str, value: object) -> Path:
            path = external / name
            path.write_bytes(execution.canonical_json_bytes(value))
            return path

        manifest_path = publish("manifest.json", self.full_manifest)
        profile_path = publish("profile.json", limit_profile)
        authorization_path = publish("authorization.json", authorization)
        session_path = publish("session-start.json", session_start)
        runtime_path = publish("runtime.json", runtime_gates)
        result_dir = self.root / "cli-result"
        claim_root = self.root / "cli-claim-root"
        claim_root.mkdir()
        claim_path = (
            claim_root
            / execution.CLAIM_REGISTRY_RELATIVE_PATH
            / f"{entry['action_identity_sha256']}.json"
        )
        responses = {
            endpoint: list(values) for endpoint, values in map_responses().items()
        }
        state: dict[str, object] = {
            "calls": [],
            "post_bodies": [],
            "claim_seen_before_first_request": False,
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                del args

            def _serve(self, method: str) -> None:
                if not state["calls"]:
                    state["claim_seen_before_first_request"] = claim_path.is_file()
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b""
                state["calls"].append((method, self.path))
                if method == "POST":
                    state["post_bodies"].append(body)
                response = responses[self.path].pop(0)
                if isinstance(response, Exception):
                    raise response
                status, text_body = response
                encoded = text_body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self) -> None:  # noqa: N802
                self._serve("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._serve("POST")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        output = io.StringIO()

        def structural_test_live_engine(manifest, **kwargs):
            return fixed._run_fixed_action_core(
                manifest,
                contract=fixed._compile_production_execution_contract(manifest),
                **kwargs,
            )

        try:
            with mock.patch.object(
                fixed, "PRODUCTION_CLAIM_ROOT", claim_root
            ), mock.patch.object(
                fixed,
                "run_fixed_action",
                side_effect=structural_test_live_engine,
            ):
                with contextlib.redirect_stdout(output):
                    return_code = fixed.main(
                        [
                            "--manifest",
                            str(manifest_path),
                            "run",
                            "--action",
                            action_key,
                            "--limit-profile",
                            str(profile_path),
                            "--profile-evaluated-at",
                            _timestamp(evaluated),
                            "--authorization",
                            str(authorization_path),
                            "--session-start",
                            str(session_path),
                            "--runtime-gates",
                            str(runtime_path),
                            "--attempt-id",
                            "attempt-localhost-loopback",
                            "--claimed-at",
                            _timestamp(claimed),
                            "--protocol-completed-at",
                            _timestamp(claimed + timedelta(minutes=1)),
                            "--result-dir",
                            str(result_dir),
                            "--url",
                            url,
                        ]
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(return_code, 0, output.getvalue())
        self.assertIs(state["claim_seen_before_first_request"], True)
        self.assertEqual(state["post_bodies"], [frame])
        self.assertEqual(
            [call for call in state["calls"] if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        receipt = json.loads(
            (result_dir / fixed.RESULT_RECEIPT_FILE).read_text(encoding="utf-8")
        )
        manual_path = publish(
            "manual.json",
            {
                "schema_version": 1,
                "kind": execution.MANUAL_OBSERVATION_KIND,
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "attempt_id": "attempt-localhost-loopback",
                "action_key": action_key,
                "action_identity_sha256": entry["action_identity_sha256"],
                "protocol_evidence_file_sha256": receipt[
                    "protocol_evidence_file_sha256"
                ],
                "observed_at": _timestamp(claimed + timedelta(minutes=2)),
                "source_observation_artifact_sha256": hash_text("loopback-manual"),
                "visual_pass": True,
                "electrical_pass": True,
                "thermal_pass": True,
                "measurement_pass": True,
                "continuity": execution.expected_continuity(contract, action_key),
                "measurement_bindings": [],
                "notes": "real localhost HTTP production wiring test",
            },
        )
        finalize_output = io.StringIO()
        with mock.patch.object(
            fixed, "PRODUCTION_CLAIM_ROOT", claim_root
        ), contextlib.redirect_stdout(finalize_output):
            finalize_code = fixed.main(
                [
                    "--manifest",
                    str(manifest_path),
                    "finalize",
                    "--result-dir",
                    str(result_dir),
                    "--manual-observation",
                    str(manual_path),
                    "--completed-at",
                    _timestamp(claimed + timedelta(minutes=3)),
                ]
            )
        self.assertEqual(finalize_code, 0, finalize_output.getvalue())
        item = json.loads(
            (result_dir / fixed.RESULT_ACTION_ITEM_FILE).read_text(encoding="utf-8")
        )
        validated = protocol.validate_strict_action_item(contract, item)
        self.assertIs(validated["strict_rc2g_verified"], True)

    def test_same_session_action_requires_exact_predecessor_and_bundle_replays(self) -> None:
        first, second, scripted = self._two_items()
        evidence = second["protocol_evidence"]["device_evidence"]
        self.assertEqual(
            evidence["preflight_mode"], protocol.PREFLIGHT_EXACT_PREDECESSOR
        )
        self.assertEqual(
            evidence["preflight"]["job_raw"],
            first["protocol_evidence"]["device_evidence"]["target_job_raw"],
        )
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        bundle = execution.build_finalized_bundle(
            self.contract,
            [first, second],
            [self.session_start],
            finalized_at=_timestamp(self.base_time + timedelta(minutes=13)),
        )
        report = protocol.validate_strict_finalized_bundle(self.contract, bundle)
        self.assertIs(report["strict_rc2g_verified"], True)
        self.assertIs(report["network_io_performed"], False)

    def test_wrong_fresh_job_is_unknown_and_permanent_claim_blocks_replay(self) -> None:
        responses = map_responses()
        wrong_job = json.loads(responses["/api/job"][0][1])
        wrong_job["job_id"] = 99
        responses["/api/job"][0] = (200, json.dumps(wrong_job))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(execution.N5PostClaimUnknown) as caught:
            self._execute(
                self.first_entry, scripted, prior_item=None, minute=4
            )
        self.assertEqual(
            caught.exception.receipt["protocol_evidence"]["outcome"],
            "UNKNOWN_DO_NOT_RETRY",
        )
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"], []
        )
        calls = list(scripted.calls)
        with self.assertRaises(execution.N5ClaimConsumedError):
            self._execute(
                self.first_entry,
                ScriptedRequester(map_responses()),
                prior_item=None,
                minute=4,
            )
        self.assertEqual(scripted.calls, calls)

    def test_wrong_target_report_and_transport_loss_are_unknown_without_recovery(self) -> None:
        report_responses = map_responses()
        target = json.loads(report_responses["/api/diagnostic/report"][1][1])
        target["job_operation_id"] = 2
        report_responses["/api/diagnostic/report"][1] = (
            200,
            json.dumps(target),
        )
        with self.assertRaises(execution.N5PostClaimUnknown) as report_error:
            self._execute(
                self.first_entry,
                ScriptedRequester(report_responses),
                prior_item=None,
                minute=4,
            )
        audit = report_error.exception.receipt["protocol_evidence"]["request_audit"]
        self.assertEqual(audit["post_issued_count"], 1)
        self.assertEqual(audit["post_attempt_count"], 1)

        other_root = Path(tempfile.mkdtemp(dir=self.root))
        self.claim_store = execution.AtomicWorkspaceClaimStore(other_root)
        transport_responses = map_responses()
        transport_responses["/api/frame"][0] = OSError("scripted transport loss")
        with self.assertRaises(execution.N5PostClaimUnknown) as transport_error:
            self._execute(
                self.first_entry,
                ScriptedRequester(transport_responses),
                prior_item=None,
                minute=4,
            )
        transport_audit = transport_error.exception.receipt["protocol_evidence"][
            "request_audit"
        ]
        self.assertEqual(transport_audit["post_issued_count"], 1)
        self.assertIsNotNone(transport_error.exception.receipt["claim"])

    def test_core_valid_semantic_tamper_is_rejected_by_deep_bundle_replay(self) -> None:
        first, second, _scripted = self._two_items()
        evidence = copy.deepcopy(second["protocol_evidence"]["device_evidence"])
        evidence["completed_action"]["job_id"] += 1
        tampered_second = self._refinalize_with_device_evidence(second, evidence)
        bundle = execution.build_finalized_bundle(
            self.contract,
            [first, tampered_second],
            [self.session_start],
            finalized_at=_timestamp(self.base_time + timedelta(minutes=13)),
        )
        execution.validate_finalized_bundle(self.contract, bundle)
        with self.assertRaisesRegex(
            protocol.N5Rc2gProtocolError,
            "completed job/action identity changed",
        ):
            protocol.validate_strict_finalized_bundle(self.contract, bundle)

    def test_core_valid_request_hash_and_raw_body_tamper_are_rejected(self) -> None:
        first, _scripted = self._first_item()
        evidence = copy.deepcopy(first["protocol_evidence"]["device_evidence"])
        evidence["strict_request_audit"]["calls"][0]["response_sha256"] = "0" * 64
        hash_tampered = self._refinalize_with_device_evidence(first, evidence)
        execution._validate_action_item(self.contract, hash_tampered)
        with self.assertRaisesRegex(
            protocol.N5Rc2gProtocolError, "inner/outer request audits diverge"
        ):
            protocol.validate_strict_action_item(self.contract, hash_tampered)

        evidence = copy.deepcopy(first["protocol_evidence"]["device_evidence"])
        job_wire = next(
            call
            for call in evidence["wire_responses"]
            if call["endpoint"] == "/api/job"
        )
        wrong_job = json.loads(job_wire["response_body"])
        wrong_job["queued_at_ms"] = 123
        job_wire["response_body"] = json.dumps(wrong_job)
        audit_call = evidence["strict_request_audit"]["calls"][job_wire["index"] - 1]
        encoded = job_wire["response_body"].encode("utf-8")
        audit_call["response_bytes"] = len(encoded)
        audit_call["response_sha256"] = execution._sha256(encoded)
        body_tampered = self._refinalize_with_device_evidence(first, evidence)
        execution._validate_action_item(self.contract, body_tampered)
        with self.assertRaisesRegex(
            protocol.N5Rc2gProtocolError, "raw RC2G jobs do not bind"
        ):
            protocol.validate_strict_action_item(self.contract, body_tampered)


if __name__ == "__main__":
    unittest.main()
