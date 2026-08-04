"""UI-facing application state machine for refresh locking and recovery."""

from __future__ import annotations

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

    def set_artifact(self, artifact: ApplicationArtifact) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("cannot replace the frame while a refresh is active")
        if not isinstance(artifact, ApplicationArtifact):
            raise SessionError("artifact must be an ApplicationArtifact")
        self.artifact = artifact
        return self.status()

    def allow_device_connection(self) -> Mapping[str, Any]:
        result = self.adapter.allow_connection(True)
        self.state = SessionState.READY
        self.last_device_result = result
        return result

    def arm_refresh(self, confirmation: str) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("cannot arm while another refresh is active")
        result = self.adapter.arm_refresh(confirmation)
        self.state = SessionState.ARMED
        self.last_device_result = result
        return result

    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        result = self.adapter.version_preflight(expected_mappings)
        self.last_device_result = result
        return result

    def frame_ingress(self) -> Mapping[str, Any]:
        if self.artifact is None:
            raise SessionError("generate an offline artifact before frame ingress")
        result = self.adapter.frame_ingress(self.artifact.frame)
        self.last_device_result = result
        return result

    def enqueue_refresh(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        if self.refresh_locked:
            raise SessionError("refresh submission is locked until the active job is resolved")
        if self.artifact is None:
            raise SessionError("generate an offline artifact before refresh")
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
        self.state = SessionState.QUEUED
        self.refresh_locked = True
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = result
        return result

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
        state = result.get("state")
        if state == "running":
            self.state = SessionState.RUNNING
        elif state == "completed_pending_report":
            self.state = SessionState.COMPLETED_PENDING_REPORT
        else:
            self.state = SessionState.QUEUED
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = result
        return result

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
        self.state = SessionState.PROTOCOL_VERIFIED
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = result
        return result

    def recover(self) -> Mapping[str, Any]:
        if not self.recovery_available:
            raise SessionError("there is no recoverable network error")
        result = self.adapter.recover()
        recovered_state = result.get("state")
        try:
            self.state = SessionState(str(recovered_state))
        except ValueError:
            self.state = SessionState.QUEUED
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = result
        return result

    def cancel(self) -> Mapping[str, Any]:
        result = self.adapter.cancel()
        self.last_device_result = result
        return result

    def local_abort(self) -> Mapping[str, Any]:
        result = self.adapter.local_abort()
        self.state = SessionState.LOCAL_ABORTED
        self.refresh_locked = False
        self.recovery_available = False
        self.last_error = None
        self.last_device_result = result
        return result

    def application_report(self) -> Mapping[str, Any]:
        if self.artifact is None:
            raise SessionError("no application artifact is available")
        report = dict(self.artifact.report)
        report["protocol_verified"] = self.state is SessionState.PROTOCOL_VERIFIED
        report["hardware_tested"] = False
        if self.last_device_result is not None:
            report["device_protocol"] = self.last_device_result
        return report

    def status(self) -> Mapping[str, Any]:
        return {
            "state": self.state.value,
            "artifact_available": self.artifact is not None,
            "formal_upload_authorized": bool(
                self.artifact is not None and self.artifact.upload_authorized
            ),
            "refresh_locked": self.refresh_locked,
            "recovery_available": self.recovery_available,
            "error": self.last_error,
            "offline_verified": bool(
                self.artifact is not None
                and self.artifact.report.get("offline_verified") is True
            ),
            "protocol_verified": self.state is SessionState.PROTOCOL_VERIFIED,
            "hardware_tested": False,
        }
