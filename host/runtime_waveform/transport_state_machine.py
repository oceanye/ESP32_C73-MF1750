"""Compile-disabled, mock-only runtime-waveform transport state model.

This module is deliberately under ``host/`` and is not referenced by any
PlatformIO environment.  It has no GPIO, SPI, serial, HTTP, or firmware driver
imports.  Its only execution surface requires an explicitly marked mock sink.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from . import contracts, execution_plan


FIRMWARE_COMPILE_GATE_ENABLED = False
INITIAL_STATE = "BLOCKED_NO_REGISTERED_PROFILE"
TERMINAL_FAULT = "TERMINAL_FAULT"
COMPLETE = "COMPLETE"

_DTM_IDENTITY_KEYS = {"bytes", "sha256"}
_RESPONSE_KEYS = {"ok", "parameter_length", "parameter_sha256"}


class MockTransportSink(Protocol):
    """Minimal marker/interface accepted by the offline transport model."""

    is_runtime_waveform_mock_sink: bool

    def dispatch(self, event: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TransportStateError(RuntimeError):
    """Raised for repeated execution after a terminal state."""


class _AbortExecution(Exception):
    pass


def _validate_dtm_identities(value: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"CS1", "CS2"}:
        raise TransportStateError("DTM identities require exact CS1/CS2 keys")
    result: dict[str, dict[str, Any]] = {}
    for controller in ("CS1", "CS2"):
        identity = value[controller]
        if not isinstance(identity, Mapping) or set(identity) != _DTM_IDENTITY_KEYS:
            raise TransportStateError(f"{controller} DTM identity keys differ")
        length = identity["bytes"]
        if type(length) is not int or length < 1 or length > 1_048_576:
            raise TransportStateError(f"{controller} DTM length differs")
        try:
            digest = contracts._hash(  # noqa: SLF001
                identity["sha256"], label=f"{controller} DTM sha256"
            )
        except contracts.RuntimeWaveformContractError as error:
            raise TransportStateError(str(error)) from error
        assert digest is not None
        result[controller] = {"bytes": length, "sha256": digest}
    return result


class MockOnlyRuntimeWaveformTransport:
    """One-attempt state machine that can dispatch only sanitized mock events."""

    def __init__(
        self,
        plan: Mapping[str, Any],
        *,
        trusted_format_registration: Mapping[str, Any] | None,
        dtm_identities: Mapping[str, Mapping[str, Any]] | None,
    ) -> None:
        self._plan = plan
        self._registration = trusted_format_registration
        self._dtm_identities = (
            None if dtm_identities is None else _validate_dtm_identities(dtm_identities)
        )
        self._state = INITIAL_STATE
        self._trace: list[dict[str, Any]] = [
            {"state": INITIAL_STATE, "reason": "production_registry_empty_by_default"}
        ]
        self._executing = False
        self._attempted = False
        self._failure_code: str | None = None
        self._event_count = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def event_count(self) -> int:
        return self._event_count

    def _transition(self, state: str, **details: Any) -> None:
        self._state = state
        self._trace.append({"state": state, **details})

    def _fault(self, code: str, **details: Any) -> None:
        if self._state != TERMINAL_FAULT:
            self._failure_code = code
            self._transition(TERMINAL_FAULT, failure_code=code, **details)

    def _report(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "failure_code": self._failure_code,
            "trace": list(self._trace),
            "mock_event_count": self._event_count,
            "firmware_compile_gate_enabled": FIRMWARE_COMPILE_GATE_ENABLED,
            "mock_only": True,
            "hardware_io_performed": False,
            "network_io_performed": False,
            "visible_refresh_authorized": False,
            "hardware_execution_eligible": False,
            "execution_ready": False,
            "automatic_retry_performed": False,
            "automatic_profile_switch_performed": False,
            "automatic_recovery_performed": False,
        }

    def _dispatch(
        self,
        sink: MockTransportSink,
        event: Mapping[str, Any],
        *,
        failure_code: str,
    ) -> Mapping[str, Any]:
        try:
            response = sink.dispatch(event)
        except Exception as error:  # mock boundary must collapse to terminal fault
            self._fault(failure_code, mock_exception_type=type(error).__name__)
            raise _AbortExecution from error
        self._event_count += 1
        if self._state == TERMINAL_FAULT:
            raise _AbortExecution
        if not isinstance(response, Mapping) or response.get("ok") is not True:
            self._fault(failure_code)
            raise _AbortExecution
        return response

    def execute_mock(self, sink: MockTransportSink) -> dict[str, Any]:
        """Run exactly once against a mock sink; never retry or recover."""

        if self._executing:
            self._fault("ILLEGAL_REENTRY")
            return self._report()
        if self._state in {TERMINAL_FAULT, COMPLETE} or self._attempted:
            raise TransportStateError("transport attempt is already terminal/consumed")
        if self._plan.get("compiled") is not True:
            return self._report()
        self._attempted = True
        if getattr(sink, "is_runtime_waveform_mock_sink", False) is not True:
            self._fault("NON_MOCK_SINK_REJECTED")
            return self._report()
        if self._registration is None or self._dtm_identities is None:
            self._fault("REGISTERED_PROFILE_OR_DTM_IDENTITY_MISSING")
            return self._report()
        self._executing = True
        try:
            try:
                plan_report = execution_plan.validate_execution_plan(
                    self._plan,
                    trusted_format_registration=self._registration,
                )
            except execution_plan.ExecutionPlanError as error:
                self._fault("PLAN_VALIDATION_FAILED", detail=str(error))
                return self._report()

            self._transition(
                "PREFLIGHT_IDENTITY",
                plan_canonical_sha256=plan_report["canonical_sha256"],
            )
            self._dispatch(
                sink,
                {
                    "event": "preflight_identity",
                    "plan_canonical_sha256": plan_report["canonical_sha256"],
                },
                failure_code="PREFLIGHT_IDENTITY_FAILED",
            )

            for step in self._plan["steps"]:
                controller = step["controller_target"]
                self._transition(
                    f"PROFILE_PLAN_{controller}",
                    step_index=step["index"],
                    opcode=step["opcode"],
                )
                response = self._dispatch(
                    sink,
                    {
                        "event": "profile_step",
                        "step_index": step["index"],
                        "controller_target": controller,
                        "opcode": step["opcode"],
                        "parameter_length": step["parameter_length"],
                        "parameter_sha256": step["parameter_sha256"],
                    },
                    failure_code=f"{controller}_PROFILE_STEP_FAILED",
                )
                if set(response) != _RESPONSE_KEYS:
                    self._fault(f"{controller}_PROFILE_RESPONSE_SHAPE_INVALID")
                    raise _AbortExecution
                if (
                    response["parameter_length"] != step["parameter_length"]
                    or response["parameter_sha256"] != step["parameter_sha256"]
                ):
                    self._fault(f"{controller}_PROFILE_IDENTITY_MISMATCH")
                    raise _AbortExecution

            self._transition("DTM_IDENTITY_CHECK")
            for controller in ("CS1", "CS2"):
                expected = self._dtm_identities[controller]
                response = self._dispatch(
                    sink,
                    {
                        "event": "dtm_identity",
                        "controller_target": controller,
                        "dtm_length": expected["bytes"],
                        "dtm_sha256": expected["sha256"],
                    },
                    failure_code=f"{controller}_DTM_FAILED",
                )
                if (
                    set(response) != {
                        "ok",
                        "dtm_length",
                        "dtm_sha256",
                    }
                    or response["dtm_length"] != expected["bytes"]
                    or response["dtm_sha256"] != expected["sha256"]
                ):
                    self._fault(f"{controller}_DTM_IDENTITY_MISMATCH")
                    raise _AbortExecution

            self._transition("BOTH_REFRESH")
            response = self._dispatch(
                sink,
                {"event": "both_refresh", "controller_target": "BOTH"},
                failure_code="BOTH_REFRESH_FAILED",
            )
            if set(response) != {"ok", "busy_completed"}:
                self._fault("BOTH_REFRESH_RESPONSE_SHAPE_INVALID")
                raise _AbortExecution
            if response["busy_completed"] is not True:
                self._fault("BUSY_TIMEOUT")
                raise _AbortExecution

            self._transition("SAFE_FINISH")
            response = self._dispatch(
                sink,
                {"event": "safe_finish"},
                failure_code="SAFE_FINISH_FAILED",
            )
            if set(response) != {"ok", "pof_completed"}:
                self._fault("SAFE_FINISH_RESPONSE_SHAPE_INVALID")
                raise _AbortExecution
            if response["pof_completed"] is not True:
                self._fault("POF_TIMEOUT")
                raise _AbortExecution
            self._transition(COMPLETE)
        except _AbortExecution:
            pass
        finally:
            self._executing = False
        return self._report()
