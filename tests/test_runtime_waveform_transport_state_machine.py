from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from host.runtime_waveform import execution_plan, transport_state_machine
from tests.runtime_waveform_fixture import build_complete_evidence_fixture


class ScriptedMockSink:
    is_runtime_waveform_mock_sink = True

    def __init__(self, mutator=None) -> None:
        self.events: list[dict[str, Any]] = []
        self.mutator = mutator
        self.transport = None

    def dispatch(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        frozen = dict(event)
        self.events.append(frozen)
        if self.mutator is not None:
            changed = self.mutator(self, frozen)
            if changed is not None:
                return changed
        if event["event"] == "profile_step":
            return {
                "ok": True,
                "parameter_length": event["parameter_length"],
                "parameter_sha256": event["parameter_sha256"],
            }
        if event["event"] == "dtm_identity":
            return {
                "ok": True,
                "dtm_length": event["dtm_length"],
                "dtm_sha256": event["dtm_sha256"],
            }
        if event["event"] == "both_refresh":
            return {"ok": True, "busy_completed": True}
        if event["event"] == "safe_finish":
            return {"ok": True, "pof_completed": True}
        return {"ok": True}


def _dtm() -> dict[str, dict[str, Any]]:
    return {
        "CS1": {"bytes": 16, "sha256": hashlib.sha256(b"cs1-dtm").hexdigest()},
        "CS2": {"bytes": 16, "sha256": hashlib.sha256(b"cs2-dtm").hexdigest()},
    }


def _compiled() -> tuple[dict, dict]:
    fixture = build_complete_evidence_fixture()
    plan = execution_plan.compile_execution_plan(
        fixture["candidate_manifest_bytes"],
        fixture["controller_payload_bytes"],
        evidence_bundle=fixture["bundle"],
        evidence_artifact_bytes=fixture["artifacts"],
        trusted_format_registrations=fixture["registry"],
    )
    return fixture, plan


def _transport(fixture: dict, plan: dict) -> transport_state_machine.MockOnlyRuntimeWaveformTransport:
    return transport_state_machine.MockOnlyRuntimeWaveformTransport(
        plan,
        trusted_format_registration=fixture["registration"],
        dtm_identities=_dtm(),
    )


def test_compile_gate_is_false_and_platformio_does_not_include_transport() -> None:
    assert transport_state_machine.FIRMWARE_COMPILE_GATE_ENABLED is False
    module_name = "runtime_waveform/transport_state_machine.py"
    for path in Path(".").glob("platformio*.ini"):
        assert module_name not in path.read_text(encoding="utf-8")


def test_unregistered_plan_stays_at_initial_block_without_mock_events() -> None:
    fixture = build_complete_evidence_fixture()
    blocked = execution_plan.compile_execution_plan(
        fixture["candidate_manifest_bytes"],
        fixture["controller_payload_bytes"],
    )
    transport = transport_state_machine.MockOnlyRuntimeWaveformTransport(
        blocked, trusted_format_registration=None, dtm_identities=None
    )
    sink = ScriptedMockSink()
    result = transport.execute_mock(sink)
    assert result["state"] == transport_state_machine.INITIAL_STATE
    assert result["mock_event_count"] == 0
    assert sink.events == []
    assert result["execution_ready"] is False


def test_dual_controller_success_trace_is_mock_only() -> None:
    fixture, plan = _compiled()
    transport = _transport(fixture, plan)
    sink = ScriptedMockSink()
    result = transport.execute_mock(sink)
    assert result["state"] == transport_state_machine.COMPLETE
    assert result["failure_code"] is None
    assert result["mock_event_count"] == 9
    assert [event["event"] for event in sink.events] == [
        "preflight_identity",
        "profile_step",
        "profile_step",
        "profile_step",
        "profile_step",
        "dtm_identity",
        "dtm_identity",
        "both_refresh",
        "safe_finish",
    ]
    assert all("payload" not in key for event in sink.events for key in event)
    assert result["hardware_io_performed"] is False
    assert result["visible_refresh_authorized"] is False


@pytest.mark.parametrize("controller", ["CS1", "CS2"])
def test_profile_hash_or_length_mismatch_is_terminal(controller: str) -> None:
    fixture, plan = _compiled()

    def mutate(_sink, event):
        if (
            event["event"] == "profile_step"
            and event["controller_target"] == controller
            and event["opcode"] == 0x20
        ):
            return {
                "ok": True,
                "parameter_length": event["parameter_length"] + 1,
                "parameter_sha256": event["parameter_sha256"],
            }
        return None

    transport = _transport(fixture, plan)
    result = transport.execute_mock(ScriptedMockSink(mutate))
    assert result["state"] == transport_state_machine.TERMINAL_FAULT
    assert result["failure_code"] == f"{controller}_PROFILE_IDENTITY_MISMATCH"
    assert result["automatic_retry_performed"] is False


def test_second_controller_failure_stops_before_dtm_and_refresh() -> None:
    fixture, plan = _compiled()

    def mutate(_sink, event):
        if event["event"] == "profile_step" and event["controller_target"] == "CS2":
            return {"ok": False}
        return None

    sink = ScriptedMockSink(mutate)
    result = _transport(fixture, plan).execute_mock(sink)
    assert result["failure_code"] == "CS2_PROFILE_STEP_FAILED"
    assert not any(event["event"] == "dtm_identity" for event in sink.events)
    assert not any(event["event"] == "both_refresh" for event in sink.events)


def test_dtm_mismatch_busy_timeout_and_pof_timeout_are_terminal() -> None:
    cases = (
        (
            lambda _sink, event: (
                {"ok": True, "dtm_length": event["dtm_length"] + 1, "dtm_sha256": event["dtm_sha256"]}
                if event["event"] == "dtm_identity" and event["controller_target"] == "CS2"
                else None
            ),
            "CS2_DTM_IDENTITY_MISMATCH",
        ),
        (
            lambda _sink, event: (
                {"ok": True, "busy_completed": False}
                if event["event"] == "both_refresh"
                else None
            ),
            "BUSY_TIMEOUT",
        ),
        (
            lambda _sink, event: (
                {"ok": True, "pof_completed": False}
                if event["event"] == "safe_finish"
                else None
            ),
            "POF_TIMEOUT",
        ),
    )
    for mutator, expected in cases:
        fixture, plan = _compiled()
        result = _transport(fixture, plan).execute_mock(ScriptedMockSink(mutator))
        assert result["state"] == transport_state_machine.TERMINAL_FAULT
        assert result["failure_code"] == expected
        assert result["automatic_recovery_performed"] is False


def test_illegal_reentry_duplicate_execute_and_retry_after_fault_are_refused() -> None:
    fixture, plan = _compiled()
    transport = _transport(fixture, plan)

    def reenter(sink, event):
        if event["event"] == "preflight_identity":
            assert sink.transport is not None
            sink.transport.execute_mock(sink)
        return None

    sink = ScriptedMockSink(reenter)
    sink.transport = transport
    result = transport.execute_mock(sink)
    assert result["failure_code"] == "ILLEGAL_REENTRY"
    count = len(sink.events)
    with pytest.raises(transport_state_machine.TransportStateError):
        transport.execute_mock(sink)
    assert len(sink.events) == count

    fixture, plan = _compiled()
    transport = _transport(fixture, plan)
    sink = ScriptedMockSink()
    assert transport.execute_mock(sink)["state"] == transport_state_machine.COMPLETE
    count = len(sink.events)
    with pytest.raises(transport_state_machine.TransportStateError):
        transport.execute_mock(sink)
    assert len(sink.events) == count


def test_opcode_injection_faults_before_any_sink_dispatch() -> None:
    fixture, plan = _compiled()
    changed = copy.deepcopy(plan)
    changed["steps"][0]["opcode"] = 0xA5
    transport = _transport(fixture, changed)
    sink = ScriptedMockSink()
    result = transport.execute_mock(sink)
    assert result["state"] == transport_state_machine.TERMINAL_FAULT
    assert result["failure_code"] == "PLAN_VALIDATION_FAILED"
    assert sink.events == []
