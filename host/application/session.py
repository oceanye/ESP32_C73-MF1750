"""UI-facing application state machine for refresh locking and recovery."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from host.epd_frame import ControllerMapping

from .device import AdapterError, AdapterNetworkError, DeviceAdapter
from .pipeline import ApplicationArtifact


class SessionError(RuntimeError):
    """Raised when a UI/application transition is not safe."""


class SessionState(str, Enum):
    OFFLINE = "offline"
    READY = "ready"
    ARMED = "armed"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED_PENDING_REPORT = "completed_pending_report"
    PROTOCOL_VERIFIED = "protocol_verified"
    NETWORK_ERROR = "network_error"
    FAILED = "failed"
    LOCAL_ABORTED = "local_aborted"


class ApplicationSession:
    def __init__(self, adapter: DeviceAdapter) -> None:
        self.adapter = adapter
        self.artifact: Optional[ApplicationArtifact] = None
        self.state = SessionState.OFFLINE
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error: Optional[str] = None
        self.last_device_result: Optional[Mapping[str, Any]] = None
        self._connection_allowed = False
        self._preflight_identity: Optional[dict[str, Any]] = None
        self._preflight_mappings: Optional[tuple[ControllerMapping, ...]] = None
        self._armed_identity: Optional[dict[str, Any]] = None
        self._protocol_identity: Optional[dict[str, Any]] = None

    def _current_identity(self) -> Optional[dict[str, Any]]:
        return None if self.artifact is None else self.artifact.identity

    def _clear_protocol_evidence(self) -> None:
        self._preflight_identity = None
        self._preflight_mappings = None
        self._armed_identity = None
        self._protocol_identity = None
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = None

    def _record_result(self, result: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise SessionError("device adapter result must be an object")
        snapshot = deepcopy(dict(result))
        snapshot["hardware_tested"] = False
        self.last_device_result = snapshot
        return deepcopy(snapshot)

    @staticmethod
    def _require_result_identity(
        result: Mapping[str, Any], expected: Mapping[str, Any], operation: str
    ) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise SessionError(f"{operation} adapter result must be an object")
        received = result.get("artifact_identity")
        if not isinstance(received, Mapping) or dict(received) != dict(expected):
            raise SessionError(
                f"{operation} result is not bound to the expected application artifact"
            )
        return deepcopy(dict(expected))

    def _require_current_result_identity(
        self, result: Mapping[str, Any], operation: str
    ) -> dict[str, Any]:
        current = self._current_identity()
        if current is None:
            raise SessionError(f"{operation} requires a current application artifact")
        return self._require_result_identity(result, current, operation)

    @staticmethod
    def _protocol_verified_snapshot(
        current: Optional[Mapping[str, Any]],
        state: SessionState,
        protocol_identity: Optional[Mapping[str, Any]],
        last_device_result: Optional[Mapping[str, Any]],
    ) -> bool:
        if (
            current is None
            or state is not SessionState.PROTOCOL_VERIFIED
            or protocol_identity != current
            or last_device_result is None
            or last_device_result.get("protocol_verified") is not True
        ):
            return False
        result_identity = last_device_result.get("artifact_identity")
        return isinstance(result_identity, Mapping) and dict(result_identity) == dict(current)

    def _is_protocol_verified(self) -> bool:
        return self._protocol_verified_snapshot(
            self._current_identity(),
            self.state,
            self._protocol_identity,
            self.last_device_result,
        )

    def set_artifact(self, artifact: ApplicationArtifact) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("cannot replace the frame while a refresh is active")
        if type(artifact) is not ApplicationArtifact:
            raise SessionError("artifact must be an ApplicationArtifact")
        try:
            bound = self.adapter.bind_artifact(artifact)
        except AdapterError as error:
            raise SessionError(f"cannot bind application artifact: {error}") from error
        self._require_result_identity(bound, artifact.identity, "artifact bind")
        self.artifact = artifact
        self._clear_protocol_evidence()
        self.state = (
            SessionState.READY if self._connection_allowed else SessionState.OFFLINE
        )
        return self.status()

    def invalidate_artifact(self) -> Mapping[str, Any]:
        """Clear an inactive artifact and revoke every authorization/evidence link."""

        if self.refresh_locked:
            raise SessionError("cannot invalidate the frame while a refresh is active")
        try:
            result = self.adapter.bind_artifact(None)
        except AdapterError as error:
            raise SessionError(f"cannot clear application artifact: {error}") from error
        if not isinstance(result, Mapping):
            raise SessionError("artifact clear adapter result must be an object")
        self.artifact = None
        self._clear_protocol_evidence()
        self.state = (
            SessionState.READY if self._connection_allowed else SessionState.OFFLINE
        )
        if result.get("artifact_identity") is not None:
            raise SessionError("artifact clear returned a stale artifact identity")
        return self.status()

    def allow_device_connection(self) -> Mapping[str, Any]:
        result = self.adapter.allow_connection(True)
        if (
            not isinstance(result, Mapping)
            or result.get("connection_allowed") is not True
        ):
            raise SessionError("device adapter did not confirm connection permission")
        self._connection_allowed = True
        self._preflight_identity = None
        self._preflight_mappings = None
        self._armed_identity = None
        self._protocol_identity = None
        self.state = SessionState.READY
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        return self._record_result(result)

    def arm_refresh(self, confirmation: str) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("cannot arm while another refresh is active")
        current = self._current_identity()
        if current is None:
            raise SessionError("generate an offline artifact before arming refresh")
        if self._preflight_identity != current or self._preflight_mappings is None:
            raise SessionError(
                "refresh arm requires a successful preflight for the current artifact"
            )
        result = self.adapter.arm_refresh(confirmation)
        self._require_current_result_identity(result, "refresh arm")
        if result.get("armed") is not True:
            raise SessionError("device adapter did not confirm one-shot refresh arm")
        self.state = SessionState.ARMED
        self._armed_identity = deepcopy(current)
        self._protocol_identity = None
        return self._record_result(result)

    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        current = self._current_identity()
        if current is None:
            raise SessionError("generate an offline artifact before device preflight")
        if self.refresh_locked:
            raise SessionError("cannot replace preflight while a refresh is active")
        result = self.adapter.version_preflight(expected_mappings)
        self._require_current_result_identity(result, "device preflight")
        self._preflight_identity = deepcopy(current)
        self._preflight_mappings = tuple(expected_mappings)
        self._armed_identity = None
        self._protocol_identity = None
        self.state = SessionState.READY
        self.recovery_available = False
        self.last_error = None
        return self._record_result(result)

    def frame_ingress(self) -> Mapping[str, Any]:
        if self.artifact is None:
            raise SessionError("generate an offline artifact before frame ingress")
        result = self.adapter.frame_ingress(self.artifact.frame)
        self._require_current_result_identity(result, "frame ingress")
        return self._record_result(result)

    def enqueue_refresh(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("refresh submission is locked until the active job is resolved")
        if self.artifact is None:
            raise SessionError("generate an offline artifact before refresh")
        current = self.artifact.identity
        mappings = tuple(expected_mappings)
        if self._armed_identity != current:
            raise SessionError("refresh requires a one-shot arm for the current artifact")
        # Every submission attempt consumes both the arm and its preflight
        # capability, including a local mismatch rejected before device I/O.
        self._armed_identity = None
        self.state = SessionState.READY
        preflight_matches = (
            self._preflight_identity == current
            and self._preflight_mappings == mappings
        )
        self._preflight_identity = None
        self._preflight_mappings = None
        if not preflight_matches:
            raise SessionError(
                "refresh requires the current artifact and mappings to match preflight"
            )
        try:
            result = self.adapter.refresh_enqueue(self.artifact, expected_mappings)
        except AdapterNetworkError as error:
            self.state = SessionState.NETWORK_ERROR
            self.refresh_locked = bool(getattr(self.adapter, "refresh_in_flight", False))
            self.recovery_available = True
            self.last_error = str(error)
            raise
        except AdapterError as error:
            self.state = SessionState.FAILED
            self.refresh_locked = bool(getattr(self.adapter, "refresh_in_flight", True))
            self.recovery_available = False
            self.last_error = str(error)
            raise
        self._require_current_result_identity(result, "refresh enqueue")
        self.state = SessionState.QUEUED
        self.refresh_locked = True
        self.recovery_available = False
        self.last_error = None
        self._protocol_identity = None
        return self._record_result(result)

    def poll_job(self) -> Mapping[str, Any]:
        if not self.refresh_locked:
            raise SessionError("there is no active refresh to poll")
        try:
            result = self.adapter.poll_job()
        except AdapterNetworkError as error:
            self.state = SessionState.NETWORK_ERROR
            self.recovery_available = True
            self.last_error = str(error)
            raise
        except AdapterError as error:
            self.state = SessionState.FAILED
            self.recovery_available = False
            self.last_error = str(error)
            raise
        self._require_current_result_identity(result, "job poll")
        state = result.get("state")
        if state == "running":
            self.state = SessionState.RUNNING
        elif state == "completed_pending_report":
            self.state = SessionState.COMPLETED_PENDING_REPORT
        else:
            self.state = SessionState.QUEUED
        self.recovery_available = False
        self.last_error = None
        return self._record_result(result)

    def retrieve_diagnostic(self) -> Mapping[str, Any]:
        if self.state is not SessionState.COMPLETED_PENDING_REPORT:
            raise SessionError("a completed job is required before diagnostic retrieval")
        try:
            result = self.adapter.diagnostic_report()
        except AdapterNetworkError as error:
            self.state = SessionState.NETWORK_ERROR
            self.recovery_available = True
            self.last_error = str(error)
            raise
        except AdapterError as error:
            self.state = SessionState.FAILED
            self.recovery_available = False
            self.last_error = str(error)
            raise
        current = self._require_current_result_identity(result, "diagnostic report")
        if result.get("protocol_verified") is not True:
            self.state = SessionState.FAILED
            self.refresh_locked = True
            raise SessionError("diagnostic report did not verify the device protocol")
        self.state = SessionState.PROTOCOL_VERIFIED
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        self._protocol_identity = deepcopy(current)
        return self._record_result(result)

    def recover(self) -> Mapping[str, Any]:
        if not self.recovery_available:
            raise SessionError("there is no recoverable network error")
        result = self.adapter.recover()
        self._require_current_result_identity(result, "network recovery")
        recovered_state = result.get("state")
        try:
            self.state = SessionState(str(recovered_state))
        except ValueError:
            self.state = SessionState.QUEUED
        self.recovery_available = False
        self.last_error = None
        self.refresh_locked = self.state in {
            SessionState.QUEUED,
            SessionState.RUNNING,
            SessionState.COMPLETED_PENDING_REPORT,
            SessionState.NETWORK_ERROR,
            SessionState.FAILED,
        }
        return self._record_result(result)

    def cancel(self) -> Mapping[str, Any]:
        result = self.adapter.cancel()
        if self.artifact is not None:
            self._require_current_result_identity(result, "cancel status")
        return self._record_result(result)

    def local_abort(self) -> Mapping[str, Any]:
        result = self.adapter.local_abort()
        self.state = SessionState.LOCAL_ABORTED
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        self._preflight_identity = None
        self._preflight_mappings = None
        self._armed_identity = None
        self._protocol_identity = None
        if self.artifact is not None:
            self._require_current_result_identity(result, "local abort")
        return self._record_result(result)

    def application_report(self) -> Mapping[str, Any]:
        # Use one immutable artifact reference throughout so a concurrent UI
        # conversion cannot combine the old report with the new identity.
        artifact = self.artifact
        if artifact is None:
            raise SessionError("no application artifact is available")
        current = artifact.identity
        state = self.state
        protocol_identity = deepcopy(self._protocol_identity)
        last_device_result = self.last_device_result
        report = artifact.report
        report["protocol_verified"] = self._protocol_verified_snapshot(
            current, state, protocol_identity, last_device_result
        )
        report["hardware_tested"] = False
        if last_device_result is not None:
            result_identity = last_device_result.get("artifact_identity")
            if isinstance(result_identity, Mapping) and dict(result_identity) == current:
                report["device_protocol"] = deepcopy(last_device_result)
        return report

    def status(self) -> Mapping[str, Any]:
        # Derive every artifact-related field from one immutable local
        # reference.  Status intentionally remains available while device I/O
        # is blocked, but must never mix None/new/old artifact fields.
        artifact = self.artifact
        current = None if artifact is None else artifact.identity
        state = self.state
        protocol_identity = deepcopy(self._protocol_identity)
        last_device_result = self.last_device_result
        return {
            "state": state.value,
            "artifact_available": artifact is not None,
            "formal_upload_authorized": bool(
                artifact is not None and artifact.upload_authorized
            ),
            "refresh_locked": self.refresh_locked,
            "recovery_available": self.recovery_available,
            "error": self.last_error,
            "offline_verified": bool(
                artifact is not None and artifact.report.get("offline_verified") is True
            ),
            "connection_allowed": self._connection_allowed,
            "preflight_verified": bool(
                artifact is not None and self._preflight_identity == current
            ),
            "armed": bool(
                artifact is not None
                and self._armed_identity == current
                and state is SessionState.ARMED
            ),
            "artifact_identity": current,
            "protocol_verified": self._protocol_verified_snapshot(
                current, state, protocol_identity, last_device_result
            ),
            "hardware_tested": False,
        }
