"""Device adapter boundary with an offline default and an opt-in HTTP adapter.

The HTTP implementation deliberately delegates protocol parsing and evidence
validation to ``tools.mf1750_frame_tool``.  It exposes only the project's fixed
version, frame, job, and diagnostic routes; callers cannot supply a path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import math
import time
from typing import Any, Callable, Mapping, Optional, Sequence

from host.epd_frame import FRAME_BYTES, ControllerMapping, fnv1a
from tools import mf1750_frame_tool as frame_tool

from .pipeline import ApplicationArtifact, validate_application_frame


ARM_CONFIRMATION = "ARM MF1750 REFRESH"
_ALLOWED_HTTP_ROUTES = frozenset(
    {
        ("GET", "/api/version"),
        ("POST", "/api/diagnostic/frame-ingress"),
        ("POST", "/api/frame"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
    }
)


class AdapterError(RuntimeError):
    """Raised when adapter state or device evidence is unsafe."""


class AdapterNetworkError(AdapterError):
    """A recoverable transport interruption while a job may still exist."""


class UnsupportedOperationError(AdapterError):
    """The selected adapter or device cannot perform the operation."""


class AdapterState(str, Enum):
    OFFLINE = "offline"
    DISCONNECTED = "disconnected"
    READY = "ready"
    ARMED = "armed"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED_PENDING_REPORT = "completed_pending_report"
    PROTOCOL_VERIFIED = "protocol_verified"
    NETWORK_ERROR = "network_error"
    FAILED = "failed"
    LOCAL_ABORTED = "local_aborted"


class DeviceAdapter(ABC):
    def allow_connection(self, allowed: bool) -> Mapping[str, Any]:
        del allowed
        raise UnsupportedOperationError("this adapter cannot connect to a device")

    def arm_refresh(self, confirmation: str) -> Mapping[str, Any]:
        del confirmation
        raise UnsupportedOperationError("this adapter cannot arm a device refresh")

    @abstractmethod
    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def frame_ingress(self, frame: bytes) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def refresh_enqueue(
        self,
        artifact: ApplicationArtifact,
        expected_mappings: Sequence[ControllerMapping],
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def poll_job(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def diagnostic_report(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def local_abort(self) -> Mapping[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def recover(self) -> Mapping[str, Any]:
        raise NotImplementedError


class OfflineAdapter(DeviceAdapter):
    """Default adapter: validates locally and has no networking capability."""

    state = AdapterState.OFFLINE
    network_requests = 0

    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        del expected_mappings
        return {
            "adapter": "offline",
            "state": self.state.value,
            "protocol_verified": False,
            "hardware_tested": False,
        }

    def frame_ingress(self, frame: bytes) -> Mapping[str, Any]:
        validated = validate_application_frame(frame)
        return {
            "adapter": "offline",
            "bytes": len(validated),
            "fnv1a": fnv1a(validated),
            "offline_verified": True,
            "protocol_verified": False,
            "hardware_tested": False,
            "network_requests": 0,
        }

    def _unsupported(self) -> Mapping[str, Any]:
        raise UnsupportedOperationError("offline adapter does not access a device")

    def refresh_enqueue(
        self,
        artifact: ApplicationArtifact,
        expected_mappings: Sequence[ControllerMapping],
    ) -> Mapping[str, Any]:
        del artifact, expected_mappings
        return self._unsupported()

    def poll_job(self) -> Mapping[str, Any]:
        return self._unsupported()

    def diagnostic_report(self) -> Mapping[str, Any]:
        return self._unsupported()

    def cancel(self) -> Mapping[str, Any]:
        return {
            "supported": False,
            "status": "unsupported",
            "reason": "offline adapter has no remote job",
            "hardware_tested": False,
        }

    def local_abort(self) -> Mapping[str, Any]:
        return {
            "supported": True,
            "status": "local_only",
            "remote_cancelled": False,
            "hardware_tested": False,
        }

    def recover(self) -> Mapping[str, Any]:
        return {
            "supported": False,
            "status": "not_required",
            "hardware_tested": False,
        }


class HttpDeviceAdapter(DeviceAdapter):
    """Explicitly enabled adapter for the fixed RC2B/V2 protocol routes."""

    def __init__(
        self,
        device_url: str,
        *,
        requester: Optional[frame_tool.HttpRequester] = None,
        job_timeout_s: float = frame_tool.DEFAULT_JOB_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not device_url:
            raise AdapterError("an explicit device URL is required")
        try:
            self._base_url = frame_tool._normalize_base_url(device_url)
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error
        self._requester = requester or frame_tool.http_request
        if isinstance(job_timeout_s, bool) or not isinstance(job_timeout_s, (int, float)):
            raise AdapterError("job_timeout_s must be a positive finite number")
        if not math.isfinite(float(job_timeout_s)) or job_timeout_s <= 0:
            raise AdapterError("job_timeout_s must be a positive finite number")
        if not callable(clock):
            raise AdapterError("clock must be callable")
        self._job_timeout_s = float(job_timeout_s)
        self._clock = clock
        self.state = AdapterState.DISCONNECTED
        self.network_requests = 0
        self._armed = False
        self._resume_state: Optional[AdapterState] = None
        self._frame: Optional[bytes] = None
        self._frame_hash: Optional[int] = None
        self._mappings: Optional[tuple[ControllerMapping, ControllerMapping]] = None
        self._version: Optional[Mapping[str, Any]] = None
        self._job_id: Optional[int] = None
        self._job: Optional[Mapping[str, Any]] = None
        self._diagnostic: Optional[Mapping[str, Any]] = None
        self._enqueue_attempted = False
        self._job_deadline: Optional[float] = None

    @property
    def refresh_in_flight(self) -> bool:
        if self.state is AdapterState.NETWORK_ERROR:
            return self._enqueue_attempted
        return self.state in {
            AdapterState.QUEUED,
            AdapterState.RUNNING,
            AdapterState.COMPLETED_PENDING_REPORT,
            AdapterState.FAILED,
        }

    def allow_connection(self, allowed: bool) -> Mapping[str, Any]:
        if type(allowed) is not bool or not allowed:
            raise AdapterError("device connection requires explicit allow=true")
        if self.refresh_in_flight:
            raise AdapterError("connection policy cannot change during an active refresh")
        self.state = AdapterState.READY
        return {
            "connection_allowed": True,
            "request_sent": False,
            "protocol_verified": False,
            "hardware_tested": False,
        }

    def arm_refresh(self, confirmation: str) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("cannot arm while another refresh is active")
        if confirmation != ARM_CONFIRMATION:
            raise AdapterError(f"refresh confirmation must exactly equal {ARM_CONFIRMATION!r}")
        # A new arm starts a fresh protocol identity.  Completed evidence may
        # remain in the caller's report, but it must never seed the next job.
        self._frame = None
        self._frame_hash = None
        self._mappings = None
        self._version = None
        self._job_id = None
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = False
        self._job_deadline = None
        self._resume_state = None
        self._armed = True
        self.state = AdapterState.ARMED
        return {
            "armed": True,
            "one_shot": True,
            "request_sent": False,
            "hardware_tested": False,
        }

    def _require_connected(self) -> None:
        if self.state is AdapterState.DISCONNECTED:
            raise AdapterError("device connection has not been explicitly allowed")

    def _request(self, base_url: str, endpoint: str, **kwargs: Any) -> tuple[int, str]:
        if base_url != self._base_url:
            raise AdapterError("request base URL differs from the configured device root")
        method = kwargs.get("method", "GET")
        if (method, endpoint) not in _ALLOWED_HTTP_ROUTES:
            raise AdapterError("device route is not in the fixed application safety allowlist")
        self.network_requests += 1
        try:
            return self._requester(self._base_url, endpoint, **kwargs)
        except frame_tool.FrameToolNetworkError as error:
            previous = self.state
            self._resume_state = previous
            self.state = AdapterState.NETWORK_ERROR
            raise AdapterNetworkError(str(error)) from error

    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("preflight cannot replace an active refresh context")
        try:
            mappings = frame_tool._require_refresh_mapping_pair(expected_mappings)
            version = frame_tool._preflight_version(self._base_url, self._request, mappings)
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error
        self._mappings = mappings
        self._version = version
        self.state = AdapterState.ARMED if self._armed else AdapterState.READY
        return {
            **version,
            "protocol_verified": False,
            "hardware_tested": False,
            "verified_scope": ["firmware_build_api_spi_psram_and_mapping_preflight"],
        }

    def frame_ingress(self, frame: bytes) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("safe ingress is locked while a refresh is active")
        try:
            return frame_tool.perform_ingress(
                self._base_url, frame, requester=self._request
            )
        except frame_tool.FrameToolNetworkError as error:
            raise AdapterNetworkError(str(error)) from error
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error

    def refresh_enqueue(
        self,
        artifact: ApplicationArtifact,
        expected_mappings: Sequence[ControllerMapping],
    ) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("a refresh is already active; duplicate submission is locked")
        if not isinstance(artifact, ApplicationArtifact):
            raise AdapterError("refresh requires an ApplicationArtifact")
        if not artifact.upload_authorized:
            raise AdapterError("frame is not authorized for formal upload by a calibrated palette")
        frame = validate_application_frame(artifact.frame)
        try:
            mappings = frame_tool._require_refresh_mapping_pair(expected_mappings)
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error
        if not self._armed:
            raise AdapterError("refresh requires a one-shot explicit arm confirmation")
        self._armed = False
        try:
            version = frame_tool._preflight_version(self._base_url, self._request, mappings)
            frame_hash = fnv1a(frame)
            self._enqueue_attempted = True
            status, body = self._request(
                self._base_url, "/api/frame", method="POST", data=frame, timeout=20.0
            )
            frame_tool._expect_status(status, 202, body, "frame refresh enqueue")
            queued = frame_tool._json_object(body, "frame refresh enqueue")
            frame_tool._validate_transfer_response(
                queued, frame_hash, "frame refresh enqueue"
            )
            job_id = frame_tool._require_int(
                queued, "job_id", "frame refresh enqueue", minimum=1
            )
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            self.state = AdapterState.FAILED
            raise AdapterError(str(error)) from error
        self._frame = frame
        self._frame_hash = frame_hash
        self._mappings = mappings
        self._version = version
        self._job_id = job_id
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = True
        self._job_deadline = self._clock() + self._job_timeout_s
        self.state = AdapterState.QUEUED
        return {
            "accepted": True,
            "http_status": 202,
            "state": self.state.value,
            "job_id": job_id,
            "protocol_verified": False,
            "hardware_tested": False,
            "statement": "HTTP 202 means queued only; final job and diagnostic are pending",
        }

    def poll_job(self) -> Mapping[str, Any]:
        if self.state not in {
            AdapterState.QUEUED,
            AdapterState.RUNNING,
            AdapterState.NETWORK_ERROR,
        }:
            raise AdapterError("there is no queued/running job to poll")
        if self.state is AdapterState.NETWORK_ERROR:
            raise AdapterError("call recover before polling after a network error")
        assert self._job_id is not None and self._frame_hash is not None
        if self._job_deadline is None or self._clock() >= self._job_deadline:
            self.state = AdapterState.FAILED
            raise AdapterError(
                f"refresh job is stale: no verified terminal result within "
                f"{self._job_timeout_s:g} seconds"
            )
        try:
            status, body = self._request(
                self._base_url, "/api/job", method="GET", data=None, timeout=20.0
            )
            frame_tool._expect_status(status, 200, body, "job poll")
            job = frame_tool._json_object(body, "job poll")
            job_state = frame_tool._validate_job(job, self._job_id, self._frame_hash)
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            self.state = AdapterState.FAILED
            raise AdapterError(str(error)) from error
        self._job = job
        if job_state == "queued":
            self.state = AdapterState.QUEUED
        elif job_state == "running":
            self.state = AdapterState.RUNNING
        else:
            self.state = AdapterState.COMPLETED_PENDING_REPORT
        return {
            "state": self.state.value,
            "job": job,
            "protocol_verified": False,
            "hardware_tested": False,
        }

    def diagnostic_report(self) -> Mapping[str, Any]:
        if self.state is not AdapterState.COMPLETED_PENDING_REPORT:
            raise AdapterError("diagnostic retrieval requires a matching completed job")
        assert self._frame is not None
        assert self._mappings is not None
        assert self._version is not None
        assert self._job is not None
        try:
            status, body = self._request(
                self._base_url,
                "/api/diagnostic/report",
                method="GET",
                data=None,
                timeout=20.0,
            )
            frame_tool._expect_status(status, 200, body, "diagnostic report")
            diagnostic = frame_tool._validate_diagnostic(
                frame_tool._json_object(body, "diagnostic report"),
                self._frame,
                self._mappings,
                self._version,
                self._job,
            )
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            self.state = AdapterState.FAILED
            raise AdapterError(str(error)) from error
        self._diagnostic = diagnostic
        self.state = AdapterState.PROTOCOL_VERIFIED
        return {
            "state": self.state.value,
            "protocol_verified": True,
            "hardware_tested": False,
            "job_id": self._job_id,
            "job": self._job,
            "diagnostic": diagnostic,
            "manual_observation_required": [
                "full_panel_visual_result",
                "power_supply_cv_and_current",
                "L1_L2_temperature",
            ],
        }

    def cancel(self) -> Mapping[str, Any]:
        return {
            "supported": False,
            "status": "unsupported",
            "reason": "RC2B/V2 exposes no remote cancel route",
            "remote_job_may_continue": self.refresh_in_flight,
            "hardware_tested": False,
        }

    def local_abort(self) -> Mapping[str, Any]:
        was_active = self.refresh_in_flight or self.state in {
            AdapterState.FAILED,
            AdapterState.COMPLETED_PENDING_REPORT,
        }
        self._frame = None
        self._frame_hash = None
        self._mappings = None
        self._version = None
        self._job_id = None
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = False
        self._job_deadline = None
        self._resume_state = None
        self._armed = False
        self.state = AdapterState.LOCAL_ABORTED
        return {
            "supported": True,
            "status": "local_only",
            "local_context_cleared": True,
            "remote_cancelled": False,
            "remote_job_may_continue": was_active,
            "hardware_tested": False,
        }

    def recover(self) -> Mapping[str, Any]:
        if self.state is not AdapterState.NETWORK_ERROR or self._resume_state is None:
            raise AdapterError("adapter has no recoverable network interruption")
        if self._enqueue_attempted and self._job_id is None:
            raise AdapterError(
                "refresh enqueue outcome is ambiguous; remote cancel is unsupported, "
                "so explicit local abort is required before any new submission"
            )
        self.state = self._resume_state
        if self.state is AdapterState.ARMED and not self._armed:
            self.state = AdapterState.READY
        self._resume_state = None
        return {
            "recovered": True,
            "state": self.state.value,
            "request_sent": False,
            "hardware_tested": False,
        }
