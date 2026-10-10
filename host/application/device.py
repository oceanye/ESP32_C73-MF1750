"""Device adapter boundary with an offline default and an opt-in HTTP adapter.

The HTTP implementation deliberately delegates protocol parsing and evidence
validation to ``tools.mf1750_frame_tool``.  It exposes only the project's fixed
version, frame, job, and diagnostic routes; callers cannot supply a path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from copy import deepcopy
from enum import Enum
import hashlib
import math
import time
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from host.epd_frame import FRAME_BYTES, ControllerMapping, fnv1a
from tools import mf1750_frame_tool as frame_tool

from .pipeline import ApplicationArtifact, ApplicationError, validate_application_frame


ARM_CONFIRMATION = "ARM MF1750 REFRESH"
ARM_TTL_S = 120.0
_REFRESH_VERIFIED_SCOPE = (
    "canonical_frame_dimensions_and_physical_color_codes",
    "firmware_build_api_spi_psram_and_mapping_preflight",
    "frame_upload_bytes_and_fnv1a",
    "job_identity_state_result_and_frame_hash",
    "diagnostic_immutable_driver_operation_identity",
    "diagnostic_build_api_job_mapping_and_dtm_hashes",
    "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
)
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


def _validated_artifact_identity(
    artifact: ApplicationArtifact,
) -> tuple[ApplicationArtifact, dict[str, Any]]:
    """Rebuild the frame identity and match it to both report and artifact."""

    if type(artifact) is not ApplicationArtifact:
        raise AdapterError("refresh requires an ApplicationArtifact")
    try:
        snapshot = artifact.validated_snapshot()
    except (ApplicationError, AttributeError, TypeError) as error:
        raise AdapterError(
            f"application artifact failed complete revalidation "
            f"(SHA256/FNV/report): {error}"
        ) from error
    frame = snapshot.frame
    frame_sha256 = hashlib.sha256(frame).hexdigest()
    frame_fnv1a = fnv1a(frame)
    expected_identity = {
        "frame_sha256": frame_sha256,
        "frame_fnv1a": frame_fnv1a,
        "frame_bytes": len(frame),
    }
    try:
        raw_identity = artifact.identity
    except (AttributeError, TypeError, ValueError) as error:
        raise AdapterError("application artifact does not expose a valid bound identity") from error
    if not isinstance(raw_identity, Mapping):
        raise AdapterError("application artifact identity must be an object")
    required_keys = {*expected_identity, "report_sha256"}
    if set(raw_identity) != required_keys:
        raise AdapterError("application artifact identity has unexpected fields")
    for key, expected in expected_identity.items():
        if raw_identity.get(key) != expected:
            raise AdapterError(f"application artifact identity {key} is stale")
    report_sha256 = raw_identity.get("report_sha256")
    if (
        not isinstance(report_sha256, str)
        or len(report_sha256) != 64
        or any(character not in "0123456789abcdef" for character in report_sha256)
    ):
        raise AdapterError("application artifact report_sha256 is invalid")

    output = snapshot.report.get("output")
    if not isinstance(output, Mapping):
        raise AdapterError("application report output must be an object")
    if output.get("sha256") != frame_sha256:
        raise AdapterError("application report SHA256 does not match the current frame")
    if output.get("fnv1a") != f"0x{frame_fnv1a:08X}":
        raise AdapterError("application report FNV1a does not match the current frame")
    if output.get("bytes") != FRAME_BYTES:
        raise AdapterError("application report byte count does not match the current frame")
    identity = {**expected_identity, "report_sha256": report_sha256}
    return snapshot, identity


def _is_matching_terminal_failed_job(
    data: Mapping[str, Any], job_id: int, frame_hash: int
) -> bool:
    """Return true only for a fully identified, ordered terminal failure.

    ``frame_tool._validate_job`` intentionally raises for failed jobs because
    they can never satisfy the success contract.  The adapter still needs to
    distinguish a trustworthy terminal failure (remote activity has stopped)
    from malformed or mismatched evidence (remote activity remains unknown).
    """

    try:
        if frame_tool._require_int(data, "job_id", "job", minimum=1) != job_id:
            return False
        if frame_tool._require_string(data, "action", "job") != "uploaded_frame":
            return False
        if frame_tool._require_int(data, "frame_fnv1a", "job") != frame_hash:
            return False
        queued_at_ms = frame_tool._require_u32(data, "queued_at_ms", "job")
        started_at_ms = frame_tool._require_u32(data, "started_at_ms", "job")
        finished_at_ms = frame_tool._require_u32(data, "finished_at_ms", "job")
        if frame_tool._require_string(data, "state", "job") != "failed":
            return False
        if data.get("result") is not False:
            return False
        return frame_tool._u32_is_forward_or_equal(
            queued_at_ms, started_at_ms
        ) and frame_tool._u32_is_forward_or_equal(started_at_ms, finished_at_ms)
    except frame_tool.FrameToolError:
        return False


class DeviceAdapter(ABC):
    @abstractmethod
    def bind_artifact(
        self, artifact: Optional[ApplicationArtifact]
    ) -> Mapping[str, Any]:
        """Bind (or explicitly clear) the artifact used by later device actions."""

        raise NotImplementedError

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

    def __init__(self) -> None:
        self._artifact_identity: Optional[dict[str, Any]] = None

    def _identity(self) -> Optional[dict[str, Any]]:
        return deepcopy(self._artifact_identity)

    def bind_artifact(
        self, artifact: Optional[ApplicationArtifact]
    ) -> Mapping[str, Any]:
        if artifact is not None and type(artifact) is not ApplicationArtifact:
            raise AdapterError("artifact must be an ApplicationArtifact or None")
        self._artifact_identity = (
            None if artifact is None else _validated_artifact_identity(artifact)[1]
        )
        return {
            "adapter": "offline",
            "artifact_bound": artifact is not None,
            "artifact_identity": self._identity(),
            "request_sent": False,
            "protocol_verified": False,
            "hardware_tested": False,
            "network_requests": 0,
        }

    def version_preflight(
        self, expected_mappings: Sequence[ControllerMapping]
    ) -> Mapping[str, Any]:
        del expected_mappings
        return {
            "adapter": "offline",
            "state": self.state.value,
            "artifact_identity": self._identity(),
            "protocol_verified": False,
            "hardware_tested": False,
        }

    def frame_ingress(self, frame: bytes) -> Mapping[str, Any]:
        validated = validate_application_frame(frame)
        return {
            "adapter": "offline",
            "bytes": len(validated),
            "fnv1a": fnv1a(validated),
            "artifact_identity": self._identity(),
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
            "artifact_identity": self._identity(),
            "hardware_tested": False,
        }

    def local_abort(self) -> Mapping[str, Any]:
        return {
            "supported": True,
            "status": "local_only",
            "remote_cancelled": False,
            "remote_job_may_continue": False,
            "new_submission_locked": False,
            "unlock_requirement": None,
            "artifact_identity": self._identity(),
            "hardware_tested": False,
        }

    def recover(self) -> Mapping[str, Any]:
        return {
            "supported": False,
            "status": "not_required",
            "artifact_identity": self._identity(),
            "hardware_tested": False,
        }


class HttpDeviceAdapter(DeviceAdapter):
    """Explicitly enabled adapter for the accepted RC2C/V3 protocol routes."""

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
        self._connection_allowed = False
        self._artifact_identity: Optional[dict[str, Any]] = None
        self._preflight_identity: Optional[dict[str, Any]] = None
        self._preflight_mappings: Optional[
            tuple[ControllerMapping, ControllerMapping]
        ] = None
        self._preflight_version: Optional[dict[str, Any]] = None
        self._armed = False
        self._arm_identity: Optional[dict[str, Any]] = None
        self._arm_mappings: Optional[tuple[ControllerMapping, ControllerMapping]] = None
        self._arm_version: Optional[dict[str, Any]] = None
        self._arm_expires_at: Optional[float] = None
        self._resume_state: Optional[AdapterState] = None
        self._frame: Optional[bytes] = None
        self._frame_hash: Optional[int] = None
        self._mappings: Optional[tuple[ControllerMapping, ControllerMapping]] = None
        self._version: Optional[Mapping[str, Any]] = None
        self._job_id: Optional[int] = None
        self._job_identity: Optional[dict[str, Any]] = None
        self._job: Optional[Mapping[str, Any]] = None
        self._diagnostic: Optional[Mapping[str, Any]] = None
        self._enqueue_attempted = False
        self._job_deadline: Optional[float] = None
        # Set immediately before the first /api/frame request and clear only
        # after a matching terminal job has been validated.  A local abort may
        # discard the polling context, but it must not erase this safety fact:
        # the device has no remote cancel route and may still be refreshing.
        self._remote_job_unresolved = False
        # A local abort can intentionally discard the evidence needed to close
        # a submitted job.  This separate latch keeps every new submission
        # blocked even when a matching terminal state proved the device is no
        # longer actively refreshing.
        self._submission_quarantined = False
        self._unresolved_job_context: Optional[dict[str, Any]] = None
        self._route_capability: Optional[tuple[str, str]] = None

    def _identity(self) -> Optional[dict[str, Any]]:
        return deepcopy(self._artifact_identity)

    def _clear_protocol_context(self) -> None:
        # Deliberately preserve the remote/quarantine latches and their compact
        # identity summary.  Callers may discard local protocol evidence, not
        # turn an unknown or unverified job into permission for another refresh.
        self._preflight_identity = None
        self._preflight_mappings = None
        self._preflight_version = None
        self._armed = False
        self._arm_identity = None
        self._arm_mappings = None
        self._arm_version = None
        self._arm_expires_at = None
        self._resume_state = None
        self._frame = None
        self._frame_hash = None
        self._mappings = None
        self._version = None
        self._job_id = None
        self._job_identity = None
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = False
        self._job_deadline = None

    def bind_artifact(
        self, artifact: Optional[ApplicationArtifact]
    ) -> Mapping[str, Any]:
        if self.refresh_in_flight:
            raise AdapterError("cannot replace the artifact while a refresh is active")
        if artifact is None:
            identity = None
        else:
            _, identity = _validated_artifact_identity(artifact)
        self._clear_protocol_context()
        self._artifact_identity = deepcopy(identity)
        self.state = (
            AdapterState.READY if self._connection_allowed else AdapterState.DISCONNECTED
        )
        return {
            "artifact_bound": identity is not None,
            "artifact_identity": self._identity(),
            "connection_allowed": self._connection_allowed,
            "request_sent": False,
            "protocol_verified": False,
            "hardware_tested": False,
        }

    @property
    def refresh_in_flight(self) -> bool:
        if self._remote_job_unresolved or self._submission_quarantined:
            return True
        if self.state is AdapterState.NETWORK_ERROR:
            return self._enqueue_attempted
        if self.state is AdapterState.FAILED:
            return self._enqueue_attempted
        return self.state in {
            AdapterState.QUEUED,
            AdapterState.RUNNING,
            AdapterState.COMPLETED_PENDING_REPORT,
        }

    def allow_connection(self, allowed: bool) -> Mapping[str, Any]:
        if type(allowed) is not bool or not allowed:
            raise AdapterError("device connection requires explicit allow=true")
        if self.refresh_in_flight:
            raise AdapterError("connection policy cannot change during an active refresh")
        self._clear_protocol_context()
        self._connection_allowed = True
        self.state = AdapterState.READY
        return {
            "connection_allowed": True,
            "artifact_identity": self._identity(),
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
        if self._artifact_identity is None:
            raise AdapterError("refresh arm requires a bound application artifact")
        if (
            self._preflight_identity != self._artifact_identity
            or self._preflight_mappings is None
            or self._preflight_version is None
        ):
            raise AdapterError(
                "refresh arm requires a preflight for the current artifact and mappings"
            )
        self._frame = None
        self._frame_hash = None
        self._mappings = None
        self._version = None
        self._job_id = None
        self._job_identity = None
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = False
        self._job_deadline = None
        self._resume_state = None
        self._armed = True
        self._arm_identity = deepcopy(self._preflight_identity)
        self._arm_mappings = self._preflight_mappings
        self._arm_version = deepcopy(self._preflight_version)
        self._arm_expires_at = self._clock() + ARM_TTL_S
        # The preflight capability is moved into this one-shot arm.  It cannot
        # be reused to create another arm after expiry, rejection, or success.
        self._preflight_identity = None
        self._preflight_mappings = None
        self._preflight_version = None
        self.state = AdapterState.ARMED
        return {
            "armed": True,
            "one_shot": True,
            "ttl_s": ARM_TTL_S,
            "artifact_identity": self._identity(),
            "preflight": deepcopy(self._arm_version),
            "request_sent": False,
            "hardware_tested": False,
        }

    def _require_connected(self) -> None:
        if not self._connection_allowed:
            raise AdapterError("device connection has not been explicitly allowed")

    @contextmanager
    def _route_scope(self, method: str, endpoint: str) -> Iterator[None]:
        if self._route_capability is not None:
            raise AdapterError("nested device route capability is not allowed")
        self._route_capability = (method, endpoint)
        try:
            yield
        finally:
            self._route_capability = None

    def _request(self, base_url: str, endpoint: str, **kwargs: Any) -> tuple[int, str]:
        if base_url != self._base_url:
            raise AdapterError("request base URL differs from the configured device root")
        method = kwargs.get("method", "GET")
        if (method, endpoint) not in _ALLOWED_HTTP_ROUTES:
            raise AdapterError("device route is not in the fixed application safety allowlist")
        if self._route_capability != (method, endpoint):
            raise AdapterError(
                "device route is not enabled by the current adapter state transition"
            )
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
        if self._artifact_identity is None:
            raise AdapterError("preflight requires a bound application artifact")
        self._preflight_identity = None
        self._preflight_mappings = None
        self._preflight_version = None
        self._armed = False
        self._arm_identity = None
        self._arm_mappings = None
        self._arm_version = None
        self._arm_expires_at = None
        self.state = AdapterState.READY
        try:
            mappings = frame_tool._require_refresh_mapping_pair(expected_mappings)
            with self._route_scope("GET", "/api/version"):
                version = frame_tool._preflight_version(
                    self._base_url, self._request, mappings
                )
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error
        self._preflight_identity = self._identity()
        self._preflight_mappings = mappings
        self._preflight_version = deepcopy(version)
        self.state = AdapterState.READY
        return {
            **deepcopy(version),
            "artifact_identity": self._identity(),
            "protocol_verified": False,
            "hardware_tested": False,
            "verified_scope": ["firmware_build_api_spi_psram_and_mapping_preflight"],
        }

    def frame_ingress(self, frame: bytes) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("safe ingress is locked while a refresh is active")
        if self._artifact_identity is None:
            raise AdapterError("safe ingress requires a bound application artifact")
        validated = validate_application_frame(frame)
        if (
            hashlib.sha256(validated).hexdigest()
            != self._artifact_identity["frame_sha256"]
            or fnv1a(validated) != self._artifact_identity["frame_fnv1a"]
        ):
            raise AdapterError("safe ingress frame differs from the bound artifact")
        try:
            with self._route_scope("POST", "/api/diagnostic/frame-ingress"):
                result = frame_tool.perform_ingress(
                    self._base_url, validated, requester=self._request
                )
        except frame_tool.FrameToolNetworkError as error:
            raise AdapterNetworkError(str(error)) from error
        except frame_tool.FrameToolError as error:
            raise AdapterError(str(error)) from error
        return {**result, "artifact_identity": self._identity()}

    def refresh_enqueue(
        self,
        artifact: ApplicationArtifact,
        expected_mappings: Sequence[ControllerMapping],
    ) -> Mapping[str, Any]:
        self._require_connected()
        if self.refresh_in_flight:
            raise AdapterError("a refresh is already active; duplicate submission is locked")
        if not self._armed:
            raise AdapterError("refresh requires a one-shot explicit arm confirmation")
        # Consume the one-shot capability before validating any caller-supplied
        # submission field.  A malformed, stale, rejected, or interrupted
        # attempt therefore always requires a fresh preflight and confirmation.
        arm_identity = deepcopy(self._arm_identity)
        arm_mappings = self._arm_mappings
        arm_version = deepcopy(self._arm_version)
        arm_expires_at = self._arm_expires_at
        self._armed = False
        self._arm_identity = None
        self._arm_mappings = None
        self._arm_version = None
        self._arm_expires_at = None
        try:
            snapshot, identity = _validated_artifact_identity(artifact)
            if not snapshot.upload_authorized:
                raise AdapterError(
                    "frame is not authorized for formal upload by a calibrated palette"
                )
            frame = snapshot.frame
            mappings = frame_tool._require_refresh_mapping_pair(expected_mappings)
        except AdapterError:
            self.state = AdapterState.READY
            raise
        except frame_tool.FrameToolError as error:
            self.state = AdapterState.READY
            raise AdapterError(str(error)) from error
        if arm_expires_at is None or self._clock() >= arm_expires_at:
            self.state = AdapterState.READY
            raise AdapterError("refresh arm has expired; run preflight and arm again")
        if self._artifact_identity is None or identity != self._artifact_identity:
            self.state = AdapterState.READY
            raise AdapterError("refresh artifact differs from the currently bound artifact")
        if arm_identity != identity:
            self.state = AdapterState.READY
            raise AdapterError("refresh artifact differs from the armed artifact")
        if mappings != arm_mappings:
            self.state = AdapterState.READY
            raise AdapterError("refresh mappings differ from the armed preflight mapping")
        if arm_version is None:
            self.state = AdapterState.READY
            raise AdapterError("refresh preflight evidence is stale for this artifact")

        self._frame = frame
        self._frame_hash = identity["frame_fnv1a"]
        self._mappings = mappings
        self._version = deepcopy(arm_version)
        self._job_identity = deepcopy(identity)
        self._job_id = None
        self._job = None
        self._diagnostic = None
        self._enqueue_attempted = False
        self._job_deadline = None
        try:
            with self._route_scope("GET", "/api/version"):
                version = frame_tool._preflight_version(
                    self._base_url, self._request, mappings
                )
            if version != arm_version:
                raise AdapterError(
                    "firmware preflight changed after arm; refresh was not submitted"
                )
            frame_hash = identity["frame_fnv1a"]
            self._enqueue_attempted = True
            # The request may reach the ESP32 even if the client later sees a
            # timeout or malformed response.  Latch before performing I/O.
            self._remote_job_unresolved = True
            self._unresolved_job_context = {
                "artifact_identity": deepcopy(identity),
                "frame_fnv1a": frame_hash,
                "job_id": None,
                "state": "enqueue_outcome_unknown",
            }
            with self._route_scope("POST", "/api/frame"):
                status, body = self._request(
                    self._base_url,
                    "/api/frame",
                    method="POST",
                    data=frame,
                    timeout=20.0,
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
        except AdapterError:
            self.state = (
                AdapterState.FAILED if self._enqueue_attempted else AdapterState.READY
            )
            raise
        except frame_tool.FrameToolError as error:
            self.state = (
                AdapterState.FAILED if self._enqueue_attempted else AdapterState.READY
            )
            raise AdapterError(str(error)) from error
        self._version = deepcopy(version)
        self._job_id = job_id
        assert self._unresolved_job_context is not None
        self._unresolved_job_context["job_id"] = job_id
        self._unresolved_job_context["state"] = "queued_or_running"
        self._enqueue_attempted = True
        self._job_deadline = self._clock() + self._job_timeout_s
        self.state = AdapterState.QUEUED
        return {
            "accepted": True,
            "http_status": 202,
            "state": self.state.value,
            "job_id": job_id,
            "artifact_identity": deepcopy(self._job_identity),
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
        assert self._job_identity is not None
        if self._artifact_identity != self._job_identity:
            self.state = AdapterState.FAILED
            raise AdapterError("active job artifact identity no longer matches its binding")
        if self._job_deadline is None or self._clock() >= self._job_deadline:
            self.state = AdapterState.FAILED
            raise AdapterError(
                f"refresh job is stale: no verified terminal result within "
                f"{self._job_timeout_s:g} seconds"
            )
        try:
            with self._route_scope("GET", "/api/job"):
                status, body = self._request(
                    self._base_url, "/api/job", method="GET", data=None, timeout=20.0
                )
            frame_tool._expect_status(status, 200, body, "job poll")
            job = frame_tool._json_object(body, "job poll")
        except AdapterNetworkError:
            raise
        except frame_tool.FrameToolError as error:
            self.state = AdapterState.FAILED
            raise AdapterError(str(error)) from error
        try:
            job_state = frame_tool._validate_job(job, self._job_id, self._frame_hash)
        except frame_tool.FrameToolError as error:
            if _is_matching_terminal_failed_job(job, self._job_id, self._frame_hash):
                self._remote_job_unresolved = False
                if self._unresolved_job_context is not None:
                    self._unresolved_job_context["state"] = "terminal_failed"
            self._job = deepcopy(job)
            self.state = AdapterState.FAILED
            raise AdapterError(str(error)) from error
        self._job = deepcopy(job)
        if job_state == "queued":
            self.state = AdapterState.QUEUED
        elif job_state == "running":
            self.state = AdapterState.RUNNING
        else:
            # _validate_job accepted the matching completed state, identity,
            # result and timestamps.  Only this evidence closes the overlap
            # risk; diagnostic retrieval remains a separate protocol gate.
            self._remote_job_unresolved = False
            if self._unresolved_job_context is not None:
                self._unresolved_job_context["state"] = (
                    "terminal_completed_pending_diagnostic"
                )
            self.state = AdapterState.COMPLETED_PENDING_REPORT
        return {
            "state": self.state.value,
            "job": deepcopy(self._job),
            "artifact_identity": deepcopy(self._job_identity),
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
        assert self._job_id is not None
        assert self._frame_hash is not None
        assert self._job_identity is not None
        if self._artifact_identity != self._job_identity:
            self.state = AdapterState.FAILED
            raise AdapterError("completed job artifact identity no longer matches its binding")
        try:
            job_state = frame_tool._validate_job(
                self._job, self._job_id, self._frame_hash
            )
            if job_state != "completed":
                raise frame_tool.FrameToolError(
                    "diagnostic retrieval requires a privately validated completed job"
                )
            with self._route_scope("GET", "/api/diagnostic/report"):
                status, body = self._request(
                    self._base_url,
                    "/api/diagnostic/report",
                    method="GET",
                    data=None,
                    timeout=20.0,
                )
            frame_tool._expect_status(status, 200, body, "diagnostic report")
            raw_diagnostic = frame_tool._json_object(body, "diagnostic report")
            diagnostic_validation = frame_tool._validate_diagnostic(
                raw_diagnostic,
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
        self._diagnostic = deepcopy(raw_diagnostic)
        self._unresolved_job_context = None
        self.state = AdapterState.PROTOCOL_VERIFIED
        return {
            "mode": "refresh",
            "state": self.state.value,
            "protocol_verified": True,
            "hardware_tested": False,
            "job_id": self._job_id,
            "artifact_identity": deepcopy(self._job_identity),
            "preflight": deepcopy(self._version),
            "job": deepcopy(self._job),
            "diagnostic": deepcopy(self._diagnostic),
            "diagnostic_validation": deepcopy(diagnostic_validation),
            "verified_scope": list(_REFRESH_VERIFIED_SCOPE),
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
            "reason": "RC2C/V3 exposes no remote cancel route",
            "remote_job_may_continue": self._remote_job_unresolved,
            "artifact_identity": self._identity(),
            "hardware_tested": False,
        }

    def local_abort(self) -> Mapping[str, Any]:
        remote_job_may_continue = self._remote_job_unresolved
        new_submission_locked = self.refresh_in_flight
        if new_submission_locked:
            self._submission_quarantined = True
        unresolved_context = deepcopy(self._unresolved_job_context)
        if unresolved_context is not None:
            unresolved_context["local_context_aborted"] = True
            self._unresolved_job_context = deepcopy(unresolved_context)
        self._clear_protocol_context()
        self.state = AdapterState.LOCAL_ABORTED
        return {
            "supported": True,
            "status": "local_only",
            "local_context_cleared": True,
            "remote_cancelled": False,
            "remote_job_may_continue": remote_job_may_continue,
            "new_submission_locked": self._submission_quarantined,
            "unlock_requirement": (
                "verify device idle and safe-finish state before restarting the application service"
                if self._submission_quarantined
                else None
            ),
            "unresolved_job": unresolved_context,
            "artifact_identity": self._identity(),
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
            "artifact_identity": self._identity(),
            "request_sent": False,
            "hardware_tested": False,
        }
