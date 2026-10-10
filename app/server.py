#!/usr/bin/env python3
"""Loopback-only application/Web UI server; offline unless explicitly enabled."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
from pathlib import Path
import secrets
import socket
import sys
import threading
from typing import Any, Callable, Mapping, Optional, Sequence, TypeVar
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application import (  # noqa: E402
    AdapterError,
    ApplicationArtifact,
    ApplicationError,
    ApplicationSession,
    FitPolicy,
    HttpDeviceAdapter,
    InputSource,
    OfflineAdapter,
    PreparationPurpose,
    SimulationBudget,
    SimulationOptions,
    decode_normalized_source,
    SessionError,
    prepare_image,
    prepare_simulation_artifact,
    simulate_panel,
)
from host.application.n6_visible_execution import (  # noqa: E402
    N6BrowserExecutionController,
)
from host.color_pipeline import (  # noqa: E402
    DitherMode,
    Palette,
    PipelineOptions,
    RasterImage,
    load_palette,
    reference_palette,
)
from host.epd_frame import FRAME_BYTES, HEIGHT, WIDTH, ControllerMapping  # noqa: E402
from host.gamut_mapping import (  # noqa: E402
    GamutProfile,
    MappingMode,
    MappingOptions,
    RENDERING_INTENTS,
    build_synthetic_reference_profile,
)


WEB_ROOT = REPO_ROOT / "web"
MAX_JSON_BODY = 64 * 1024
MAX_SOURCE_IMAGE_BODY = 32 * 1024 * 1024
MAX_PREPARATION_HEADER = 16 * 1024
RGBA_BYTES = WIDTH * HEIGHT * 4
BODY_READ_TIMEOUT_S = 1.0
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}

_T = TypeVar("_T")


class RequestRejected(ValueError):
    """A request which must be rejected before application state is touched."""

    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status


def _exact_object(
    value: Any, label: str, keys: set[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    if set(value) != keys:
        missing = sorted(keys.difference(value))
        unknown = sorted(set(value).difference(keys))
        raise ValueError(f"{label} fields differ; missing={missing}, unknown={unknown}")
    return value


def _preparation_header(source: str) -> Mapping[str, Any]:
    if not isinstance(source, str) or not source or len(source) > MAX_PREPARATION_HEADER:
        raise ValueError(
            f"X-MF1750-Preparation must contain 1 through {MAX_PREPARATION_HEADER} characters"
        )
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in source):
        raise ValueError("X-MF1750-Preparation must be unpadded base64url")
    try:
        padding = "=" * ((4 - len(source) % 4) % 4)
        decoded = base64.b64decode(
            (source + padding).encode("ascii"), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as error:
        raise ValueError("X-MF1750-Preparation is invalid base64url") from error
    if len(decoded) > MAX_PREPARATION_HEADER:
        raise ValueError("decoded preparation metadata is too large")
    return _strict_json(decoded)


def _validate_preparation_request(
    value: Mapping[str, Any], runtime: "ApplicationRuntime", content_type: str
) -> dict[str, Any]:
    root = _exact_object(
        value,
        "preparation request",
        {
            "schema",
            "version",
            "source",
            "geometry",
            "mapping",
            "halftone",
            "protections",
            "purpose",
        },
    )
    if root["schema"] != "mf1750-prepare-request" or root["version"] != 2 or type(root["version"]) is not int:
        raise ValueError("preparation request must use mf1750-prepare-request version 2")
    source = _exact_object(
        root["source"], "preparation source", {"expected_sha256", "media_type"}
    )
    expected_sha = source["expected_sha256"]
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha)
    ):
        raise ValueError("source expected_sha256 must be 64 lowercase hex digits")
    if source["media_type"] not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("source media_type must be image/png, image/jpeg, or image/webp")
    if source["media_type"] != content_type:
        raise ValueError("source media_type must equal the request Content-Type")

    geometry = _exact_object(
        root["geometry"], "preparation geometry", {"fit", "rotation_degrees"}
    )
    if geometry["fit"] not in {policy.value for policy in FitPolicy}:
        raise ValueError("geometry fit is invalid")
    if type(geometry["rotation_degrees"]) is not int or geometry["rotation_degrees"] not in (0, 90, 180, 270):
        raise ValueError("rotation_degrees must be integer 0, 90, 180, or 270")

    mapping = _exact_object(
        root["mapping"],
        "preparation mapping",
        {"algorithm", "profile_id", "profile_sha256", "intent", "strength"},
    )
    if mapping["algorithm"] not in {"none", "spectra6-xyz-convex-v1"}:
        raise ValueError("mapping algorithm is invalid")
    if mapping["intent"] not in RENDERING_INTENTS:
        raise ValueError("mapping intent is invalid")
    strength = mapping["strength"]
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise ValueError("mapping strength must be numeric and not boolean")
    strength = float(strength)
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError("mapping strength must be finite and in [0, 1]")
    profile: GamutProfile | None
    if mapping["algorithm"] == "none":
        if mapping["profile_id"] is not None or mapping["profile_sha256"] is not None:
            raise ValueError("mapping=none requires null profile identity")
        profile = None
    else:
        if not isinstance(mapping["profile_id"], str):
            raise ValueError("mapped preparation requires a profile_id")
        profile = runtime.gamut_profiles.get(mapping["profile_id"])
        if profile is None:
            raise ValueError("requested gamut profile is not in the server allowlist")
        if mapping["profile_sha256"] != profile.canonical_sha256:
            raise ValueError("requested gamut profile hash does not match the allowlist")

    halftone = _exact_object(
        root["halftone"], "preparation halftone", {"algorithm", "seed", "budget"}
    )
    capabilities = {
        item["id"]: item for item in runtime.config()["halftone_algorithms"]
    }
    capability = capabilities.get(halftone["algorithm"])
    if capability is None:
        raise ValueError("halftone algorithm is invalid")
    if type(halftone["seed"]) is not int or not 0 <= halftone["seed"] <= 0xFFFFFFFF:
        raise ValueError("halftone seed must be a uint32 integer")
    budget = halftone["budget"]
    if capability["supports_budget"]:
        budget = _exact_object(
            budget,
            "deterministic halftone budget",
            {
                "kind",
                "max_evaluations",
                "max_accepted_moves",
                "stagnation_evaluations",
            },
        )
        if budget["kind"] != "deterministic-work-v1":
            raise ValueError("halftone budget kind is invalid")
        for field in (
            "max_evaluations",
            "max_accepted_moves",
            "stagnation_evaluations",
        ):
            if type(budget[field]) is not int or not 1 <= budget[field] <= 16_384:
                raise ValueError(f"halftone budget {field} must be in [1, 16384]")
        if budget["max_accepted_moves"] > budget["max_evaluations"]:
            raise ValueError("max_accepted_moves cannot exceed max_evaluations")
        if budget["stagnation_evaluations"] > budget["max_evaluations"]:
            raise ValueError("stagnation_evaluations cannot exceed max_evaluations")
    elif budget is not None:
        raise ValueError("the selected fixed-complexity algorithm requires budget=null")
    if halftone["algorithm"] in {
        "area-weighted-ordered-8x8",
        "area-weighted-blue-noise",
    } and profile is None:
        raise ValueError("area-weighted algorithms require an enabled gamut profile")

    protections = _exact_object(
        root["protections"], "preparation protections", {"white", "edge", "text"}
    )
    if any(type(protections[field]) is not bool for field in protections):
        raise ValueError("all protection values must be boolean")
    if root["purpose"] != "offline_preview":
        raise ValueError("G1/S1 v2 currently supports offline_preview only")
    return {
        "source": dict(source),
        "geometry": dict(geometry),
        "mapping": {**mapping, "strength": strength, "profile": profile},
        "halftone": {**halftone, "budget": None if budget is None else dict(budget)},
        "protections": dict(protections),
        "purpose": "offline_preview",
    }


def _strict_json(source: bytes) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value!r} is not allowed")

    value = json.loads(
        source.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON request must be an object")
    return value


def _mapping(value: Any, label: str) -> ControllerMapping:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{label} must be a four-item 0/1 array")
    if any(type(item) is not int or item not in (0, 1) for item in value):
        raise ValueError(f"{label} must contain only integer 0/1 values")
    return ControllerMapping(value[0], *(bool(item) for item in value[1:]))


def _mappings(value: Mapping[str, Any]) -> tuple[ControllerMapping, ControllerMapping]:
    return (_mapping(value.get("cs1"), "cs1"), _mapping(value.get("cs2"), "cs2"))


class ApplicationRuntime:
    def __init__(
        self,
        palette: Palette,
        adapter: OfflineAdapter | HttpDeviceAdapter,
        *,
        gamut_profiles: Sequence[GamutProfile] | None = None,
        n6_formal_controller: N6BrowserExecutionController | None = None,
    ) -> None:
        self.palette = palette
        profiles = (
            (build_synthetic_reference_profile(palette),)
            if gamut_profiles is None
            else tuple(gamut_profiles)
        )
        if not profiles or any(type(profile) is not GamutProfile for profile in profiles):
            raise ValueError("gamut_profiles must contain at least one GamutProfile")
        if any(
            profile.palette_id != palette.palette_id
            or profile.palette_canonical_sha256 != palette.canonical_sha256
            for profile in profiles
        ):
            raise ValueError("every gamut profile must bind the runtime palette")
        if len({profile.profile_id for profile in profiles}) != len(profiles):
            raise ValueError("gamut profile IDs must be unique")
        self.gamut_profiles = {profile.profile_id: profile for profile in profiles}
        self.session = ApplicationSession(adapter)
        self.n6_formal_controller = n6_formal_controller
        # Device mutations are serialized, but the lock is deliberately not
        # held while a request body is arriving or an image is quantized.  It
        # is also never needed by status/config reads, so a slow device cannot
        # make the recovery UI blind.
        self.operation_lock = threading.Lock()
        self.generation_slot = threading.BoundedSemaphore(1)
        self._generation_state_lock = threading.Lock()
        self._generation_active = False
        self._artifact_lock = threading.RLock()
        self.generation_epoch = 0
        self._preview_report_sha256: str | None = None
        self._preview_payloads: dict[str, bytes] = {}

    def invalidate_artifact(self) -> Mapping[str, Any]:
        with self._artifact_lock:
            result = self.session.invalidate_artifact()
            if self.n6_formal_controller is not None:
                self.n6_formal_controller.invalidate_artifact()
            self.generation_epoch += 1
            self._preview_report_sha256 = None
            self._preview_payloads = {}
            return (
                result
                if self.n6_formal_controller is None
                else self.n6_formal_controller.status_overlay(result)
            )

    def begin_generation(self) -> int:
        with self._artifact_lock:
            self.session.invalidate_artifact()
            if self.n6_formal_controller is not None:
                self.n6_formal_controller.invalidate_artifact()
            self.generation_epoch += 1
            self._preview_report_sha256 = None
            self._preview_payloads = {}
            return self.generation_epoch

    def try_begin_generation_work(self) -> bool:
        if not self.generation_slot.acquire(blocking=False):
            return False
        with self._generation_state_lock:
            if self._generation_active:
                self.generation_slot.release()
                raise AssertionError("generation activity and semaphore diverged")
            self._generation_active = True
        return True

    def end_generation_work(self) -> None:
        with self._generation_state_lock:
            if not self._generation_active:
                raise AssertionError("generation activity ended while inactive")
            self._generation_active = False
        self.generation_slot.release()

    def generation_active(self) -> bool:
        with self._generation_state_lock:
            return self._generation_active

    def commit_generation(
        self,
        epoch: int,
        artifact: ApplicationArtifact,
        previews: Mapping[str, bytes] | None = None,
    ) -> Mapping[str, Any]:
        with self._artifact_lock:
            if epoch != self.generation_epoch:
                raise SessionError("image settings changed while conversion was in progress")
            if previews is None:
                final_preview = getattr(artifact, "preview_png", None)
                selected = {} if final_preview is None else {"final": bytes(final_preview)}
            else:
                selected = {key: bytes(value) for key, value in previews.items()}
            if set(selected) not in (
                set(),
                {"final"},
                {"source", "mapped", "final", "model"},
            ):
                raise SessionError("preview stages differ from the application contract")
            expected_previews = {
                "source": getattr(artifact, "source_preview_png", None),
                "mapped": getattr(artifact, "mapped_preview_png", None),
                "final": getattr(artifact, "preview_png", None),
                "model": getattr(artifact, "model_preview_png", None),
            }
            for stage, payload in selected.items():
                expected = expected_previews.get(stage)
                if expected is None or payload != bytes(expected):
                    raise SessionError(
                        f"preview {stage} differs from the bound application artifact"
                    )
            status = self.session.set_artifact(artifact)
            if self.n6_formal_controller is not None:
                self.n6_formal_controller.observe_artifact(artifact)
            self._preview_report_sha256 = (
                None if not selected else artifact.identity["report_sha256"]
            )
            self._preview_payloads = selected
            return (
                status
                if self.n6_formal_controller is None
                else self.n6_formal_controller.status_overlay(status)
            )

    def preview(self, report_sha256: str, stage: str) -> bytes:
        with self._artifact_lock:
            if (
                report_sha256 != self._preview_report_sha256
                or self.session.artifact is None
                or self.session.artifact.identity["report_sha256"] != report_sha256
            ):
                raise SessionError("preview artifact is stale or unavailable")
            payload = self._preview_payloads.get(stage)
            if payload is None:
                raise SessionError("preview stage is unavailable")
            if self.n6_formal_controller is not None:
                self.n6_formal_controller.record_preview_fetch(report_sha256, stage)
            return bytes(payload)

    def config(self) -> Mapping[str, Any]:
        calibration = self.palette.calibration
        return {
            "schema": "mf1750-application-config",
            "version": 2,
            "panel": {
                "width": WIDTH,
                "height": HEIGHT,
                "frame_bytes": FRAME_BYTES,
                "physical_width_mm": 163.84,
                "physical_height_mm": 97.20,
                "soft_proof_pixel_geometry": "non-square physical pitch",
            },
            "palette": {
                "id": self.palette.palette_id,
                "source": self.palette.source,
                "calibrated": self.palette.calibrated,
                "canonical_sha256": self.palette.canonical_sha256,
                "calibration": None
                if calibration is None
                else {
                    "measurement_id": calibration.measurement_id,
                    "artifact_sha256": calibration.artifact_sha256,
                },
            },
            "dither_modes": [mode.value for mode in DitherMode],
            "halftone_algorithms": [
                {
                    "id": identifier,
                    "label": label,
                    "supports_seed": supports_seed,
                    "supports_budget": supports_budget,
                    "simulation_only": simulation_only,
                }
                for identifier, label, supports_seed, supports_budget, simulation_only in (
                    ("none", "最近色 / 无抖动", False, False, False),
                    ("floyd-steinberg", "Floyd–Steinberg", False, False, False),
                    ("atkinson", "Atkinson", False, False, False),
                    (
                        "ordered-bayer-8x8",
                        "Legacy C2 nearest-two · Bayer 8×8",
                        False,
                        False,
                        False,
                    ),
                    ("hashed-threshold", "Legacy hashed threshold", True, False, False),
                    (
                        "blue-noise",
                        "Legacy nearest-two · void-and-cluster 蓝噪声",
                        True,
                        False,
                        True,
                    ),
                    (
                        "area-weighted-ordered-8x8",
                        "六码面积权重 + Bayer 8×8",
                        True,
                        False,
                        True,
                    ),
                    (
                        "area-weighted-blue-noise",
                        "六码面积权重 + 蓝噪声",
                        True,
                        False,
                        True,
                    ),
                    ("multicolor-dbs", "多色 DBS", True, True, True),
                    (
                        "overlap-aware-dbs",
                        "重叠感知多尺度 DBS",
                        True,
                        True,
                        True,
                    ),
                )
            ],
            "gamut_profiles": [
                {
                    "id": profile.profile_id,
                    "version": profile.profile_version,
                    "canonical_sha256": profile.canonical_sha256,
                    "model_kind": profile.model_kind,
                    "characterization_level": profile.characterization_level,
                    "approximation": profile.approximation,
                    "hardware_formal_qualified": False,
                }
                for profile in self.gamut_profiles.values()
            ],
            "rendering_intents": [
                {
                    "id": intent,
                    "label": {
                        "relative-colorimetric": "faithful / relative colorimetric",
                        "perceptual": "photographic / perceptual",
                        "saturation": "vivid / saturation",
                    }[intent],
                }
                for intent in RENDERING_INTENTS
            ],
            "defaults": {
                "gamut_profile_id": next(iter(self.gamut_profiles)),
                "rendering_intent": "perceptual",
                "mapping_strength": 1.0,
                "halftone_algorithm": DitherMode.ATKINSON.value,
                "seed": 0x4D463137,
                "budget": 1024,
            },
            "limits": {
                "source_image_bytes": MAX_SOURCE_IMAGE_BODY,
                "max_optimization_evaluations": 16384,
                "deterministic_work_only": True,
            },
            "formal_eligibility": {
                "eligible": False,
                "reasons": [
                    "bundled gamut profile is synthetic/uncalibrated",
                    "mixture characterization is not hardware-qualified",
                    "runtime panel/waveform/temperature binding is unavailable",
                ],
            },
            "fit_policies": [policy.value for policy in FitPolicy],
            "device_adapter": type(self.session.adapter).__name__,
            "n6_formal_execution_materialized": self.n6_formal_controller is not None,
            "hardware_tested": False,
        }

    def status(self) -> Mapping[str, Any]:
        # If the lock is available, hold it across the entire session snapshot
        # so a mutation cannot complete between reading state and checking the
        # lock.  If a slow device owns it, remain responsive but fail closed:
        # the concurrent fields are informational only until the UI polls a
        # subsequent lock-protected snapshot.
        snapshot_lock_held = self.operation_lock.acquire(blocking=False)
        if snapshot_lock_held:
            try:
                status = dict(self.session.status())
            finally:
                self.operation_lock.release()
            generation_active = self.generation_active()
            status["operation_in_progress"] = generation_active
            if generation_active:
                status["refresh_locked"] = True
                status["armed"] = False
            return (
                status
                if self.n6_formal_controller is None
                else self.n6_formal_controller.status_overlay(status)
            )

        status = dict(self.session.status())
        status["operation_in_progress"] = True
        status["refresh_locked"] = True
        status["armed"] = False
        return (
            status
            if self.n6_formal_controller is None
            else self.n6_formal_controller.status_overlay(status)
        )


class ApplicationHandler(BaseHTTPRequestHandler):
    server: "ApplicationHttpServer"

    def log_message(self, fmt: str, *args: object) -> None:
        # BaseHTTPRequestHandler may pass the complete request line here.  Do
        # not echo it: query strings can contain accidental secrets.
        del fmt, args

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = urlsplit(getattr(self, "path", "")).path or "/"
        sys.stderr.write(
            f"application-ui: {getattr(self, 'command', '-')} {path} {code} {size}\n"
        )

    def log_error(self, fmt: str, *args: object) -> None:
        del fmt, args
        sys.stderr.write("application-ui: request error\n")

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Frame-Options", "DENY")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        try:
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            # A timed-out/short-body client may disconnect before receiving
            # the bounded error response.  Its application operation was
            # never entered, so only close this request thread quietly.
            self.close_connection = True

    def _json(self, status: int, value: Mapping[str, Any]) -> None:
        self._bytes(
            status,
            json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode(
                "utf-8"
            ),
            "application/json; charset=utf-8",
        )

    def _error(self, status: int, error: Exception) -> None:
        self._json(
            status,
            {
                "ok": False,
                "error": type(error).__name__,
                "detail": str(error),
                "hardware_tested": False,
            },
        )

    def _read(self, expected_max: int) -> bytes:
        if self.headers.get("Transfer-Encoding") is not None:
            raise ValueError("Transfer-Encoding is not accepted")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise ValueError("Content-Length is required")
        raw_length = lengths[0]
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Content-Length must be an integer") from error
        if not 0 <= length <= expected_max:
            raise ValueError(f"request body exceeds the {expected_max}-byte limit")
        previous_timeout = self.connection.gettimeout()
        self.connection.settimeout(BODY_READ_TIMEOUT_S)
        try:
            body = self.rfile.read(length)
        except TimeoutError as error:
            self.close_connection = True
            raise RequestRejected(
                HTTPStatus.REQUEST_TIMEOUT, "request body read timed out"
            ) from error
        finally:
            self.connection.settimeout(previous_timeout)
        if len(body) != length:
            self.close_connection = True
            raise RequestRejected(
                HTTPStatus.BAD_REQUEST,
                f"short request body: expected {length} bytes, received {len(body)}",
            )
        return body

    def _read_json(self) -> Mapping[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        return _strict_json(self._read(MAX_JSON_BODY))

    @property
    def _authority(self) -> str:
        return self.server.authority

    def _request_path(self) -> str:
        target = urlsplit(self.path)
        if target.query or target.fragment:
            raise RequestRejected(HTTPStatus.BAD_REQUEST, "query strings are not accepted")
        return target.path

    def _validate_host(self) -> None:
        values = self.headers.get_all("Host", [])
        if len(values) != 1 or values[0] != self._authority:
            raise RequestRejected(HTTPStatus.FORBIDDEN, "Host is not the bound loopback authority")

    def _validate_api_token(self) -> None:
        values = self.headers.get_all("X-Application-Token", [])
        if len(values) != 1 or not hmac.compare_digest(
            values[0].encode("utf-8"), self.server.security_token.encode("ascii")
        ):
            raise RequestRejected(HTTPStatus.FORBIDDEN, "invalid application session token")

    def _validate_post_origin(self) -> None:
        origins = self.headers.get_all("Origin", [])
        if len(origins) != 1 or origins[0] != self.server.origin:
            raise RequestRejected(HTTPStatus.FORBIDDEN, "POST requires the loopback same origin")
        fetch_sites = self.headers.get_all("Sec-Fetch-Site", [])
        if len(fetch_sites) > 1 or (fetch_sites and fetch_sites[0] != "same-origin"):
            raise RequestRejected(HTTPStatus.FORBIDDEN, "cross-site POST is not accepted")

    def _authorize(self, path: str, *, post: bool) -> None:
        self._validate_host()
        if path.startswith("/application/"):
            self._validate_api_token()
        if post:
            self._validate_post_origin()

    def _operation(self, callback: Callable[[], _T]) -> _T:
        lock = self.server.runtime.operation_lock
        if not lock.acquire(blocking=False):
            raise RequestRejected(
                HTTPStatus.CONFLICT, "another application mutation is already in progress"
            )
        try:
            return callback()
        finally:
            lock.release()

    @staticmethod
    def _strict_boolean_header(value: Optional[str], default: bool, label: str) -> bool:
        if value is None:
            return default
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError(f"{label} must be exactly 'true' or 'false'")

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self._request_path()
            self._authorize(path, post=False)
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                if (
                    path in {"/", "/index.html"}
                    and self.server.runtime.n6_formal_controller is not None
                ):
                    self.server.runtime.n6_formal_controller.record_page_load()
                self._bytes(HTTPStatus.OK, (WEB_ROOT / filename).read_bytes(), content_type)
                return
            runtime = self.server.runtime
            if (
                path in {"/application/config", "/application/status"}
                and runtime.n6_formal_controller is not None
            ):
                runtime.n6_formal_controller.record_authenticated_read()
            if path.startswith("/application/artifact/"):
                fields = path.split("/")
                if (
                    len(fields) != 6
                    or fields[1:3] != ["application", "artifact"]
                    or fields[4] != "preview"
                    or len(fields[3]) != 64
                    or any(character not in "0123456789abcdef" for character in fields[3])
                    or fields[5] not in {"source", "mapped", "final", "model"}
                ):
                    raise RequestRejected(
                        HTTPStatus.NOT_FOUND, "unknown application preview route"
                    )
                self._bytes(
                    HTTPStatus.OK,
                    runtime.preview(fields[3], fields[5]),
                    "image/png",
                )
            elif path == "/application/config":
                self._json(HTTPStatus.OK, runtime.config())
            elif path == "/application/status":
                self._json(HTTPStatus.OK, runtime.status())
            elif path == "/application/report":
                self._json(HTTPStatus.OK, runtime.session.application_report())
            elif path in {"/application/device/job", "/application/device/report"}:
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, ValueError("route requires POST"))
            else:
                self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
        except RequestRejected as error:
            self._error(error.status, error)
        except (AdapterError, ApplicationError, SessionError, ValueError) as error:
            self._error(HTTPStatus.CONFLICT, error)

    def do_POST(self) -> None:  # noqa: N802
        runtime = self.server.runtime
        try:
            path = self._request_path()
            self._authorize(path, post=True)
            if path == "/application/convert":
                self._convert(runtime)
                return
            if path == "/application/convert-v2":
                self._convert_v2(runtime)
                return
            known_routes = {
                "/application/artifact/invalidate",
                "/application/device/allow",
                "/application/device/preflight",
                "/application/device/ingress",
                "/application/device/arm",
                "/application/device/enqueue",
                "/application/device/job",
                "/application/device/report",
                "/application/device/recover",
                "/application/device/local-abort",
                "/application/device/cancel",
            }
            if path not in known_routes:
                self._error(HTTPStatus.NOT_FOUND, ValueError("unknown application route"))
                return
            data = self._read_json()

            def mutate() -> Mapping[str, Any]:
                if path == "/application/artifact/invalidate":
                    return runtime.invalidate_artifact()
                n6 = runtime.n6_formal_controller
                if n6 is not None:
                    if path == "/application/device/allow":
                        if data.get("allow") is not True:
                            raise ValueError("device allow requires allow=true")
                        return n6.allow_connection(
                            token_validated=True, same_origin_validated=True
                        )
                    if path == "/application/device/preflight":
                        return n6.local_preflight(
                            _mappings(data),
                            token_validated=True,
                            same_origin_validated=True,
                        )
                    if path == "/application/device/arm":
                        confirmation = data.get("confirmation")
                        if not isinstance(confirmation, str):
                            raise ValueError("confirmation must be a string")
                        if getattr(n6, "physical_production_mode", False):
                            panel_plan_confirmation = data.get(
                                "panel_plan_confirmation"
                            )
                            profile_confirmation = data.get(
                                "profile_confirmation"
                            )
                            if not isinstance(panel_plan_confirmation, str):
                                raise ValueError(
                                    "panel_plan_confirmation must be a string"
                                )
                            if not isinstance(profile_confirmation, str):
                                raise ValueError(
                                    "profile_confirmation must be a string"
                                )
                            return n6.arm(
                                confirmation,
                                panel_plan_confirmation=panel_plan_confirmation,
                                profile_confirmation=profile_confirmation,
                                token_validated=True,
                                same_origin_validated=True,
                            )
                        return n6.arm(
                            confirmation,
                            token_validated=True,
                            same_origin_validated=True,
                        )
                    if path == "/application/device/enqueue":
                        return n6.enqueue(
                            _mappings(data),
                            token_validated=True,
                            same_origin_validated=True,
                        )
                    if path == "/application/device/job":
                        return n6.poll_job(
                            token_validated=True, same_origin_validated=True
                        )
                    if path == "/application/device/report":
                        return n6.diagnostic_report(
                            token_validated=True, same_origin_validated=True
                        )
                    return n6.forbidden_recovery()
                if path == "/application/device/allow":
                    if data.get("allow") is not True:
                        raise ValueError("device allow requires allow=true")
                    return runtime.session.allow_device_connection()
                if path == "/application/device/preflight":
                    return runtime.session.version_preflight(_mappings(data))
                if path == "/application/device/ingress":
                    return runtime.session.frame_ingress()
                if path == "/application/device/arm":
                    confirmation = data.get("confirmation")
                    if not isinstance(confirmation, str):
                        raise ValueError("confirmation must be a string")
                    return runtime.session.arm_refresh(confirmation)
                if path == "/application/device/enqueue":
                    return runtime.session.enqueue_refresh(_mappings(data))
                if path == "/application/device/job":
                    return runtime.session.poll_job()
                if path == "/application/device/report":
                    return runtime.session.retrieve_diagnostic()
                if path == "/application/device/recover":
                    return runtime.session.recover()
                if path == "/application/device/local-abort":
                    return runtime.session.local_abort()
                return runtime.session.cancel()

            result = self._operation(mutate)
            self._json(HTTPStatus.OK, {"ok": True, "result": result})
        except RequestRejected as error:
            self._error(error.status, error)
        except (
            AdapterError,
            ApplicationError,
            SessionError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            self._error(HTTPStatus.CONFLICT, error)

    def _convert(self, runtime: ApplicationRuntime) -> None:
        if self.headers.get_content_type() != "application/octet-stream":
            raise ValueError("conversion Content-Type must be application/octet-stream")
        rgba = self._read(RGBA_BYTES)
        if len(rgba) != RGBA_BYTES:
            raise ValueError(f"normalized RGBA body must contain exactly {RGBA_BYTES} bytes")
        source_hash = self.headers.get("X-Input-SHA256", "")
        source = InputSource(
            "browser-selected-image",
            self.headers.get("X-Input-Media-Type", "application/octet-stream"),
            source_hash,
            "browser-computed SHA256 of original selected file bytes",
        )
        generation_epoch = self._operation(runtime.begin_generation)
        fit = self.headers.get("X-Fit-Policy", FitPolicy.CONTAIN.value)
        options = PipelineOptions(
            dither=self.headers.get("X-Dither-Mode", DitherMode.FLOYD_STEINBERG.value),
            text_mode=self._strict_boolean_header(
                self.headers.get("X-Text-Mode"), False, "X-Text-Mode"
            ),
            white_protection=self._strict_boolean_header(
                self.headers.get("X-White-Protection"), True, "X-White-Protection"
            ),
        )
        artifact = prepare_image(
            RasterImage(WIDTH, HEIGHT, "RGBA", rgba),
            source,
            fit=FitPolicy.STRETCH,
            palette=runtime.palette,
            options=options,
            purpose=(
                PreparationPurpose.FORMAL_UPLOAD
                if runtime.palette.calibrated
                else PreparationPurpose.OFFLINE_PREVIEW
            ),
        )
        adjusted_report = dict(artifact.report)
        adjusted_normalization = dict(adjusted_report["normalization"])
        adjusted_normalization.update(
            {
                "fit": FitPolicy(fit).value,
                "performed_by": "browser_canvas_before_local_C2_quantization",
                "source_sha256_verification": "browser_declared_not_server_recomputed",
            }
        )
        adjusted_report["normalization"] = adjusted_normalization
        artifact = ApplicationArtifact(
            artifact.frame, artifact.preview_png, adjusted_report, artifact.upload_authorized
        )
        status = self._operation(
            lambda: runtime.commit_generation(generation_epoch, artifact)
        )
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "preview_png_base64": base64.b64encode(artifact.preview_png).decode("ascii"),
                "report": artifact.report,
                "status": status,
            },
        )

    def _convert_v2(self, runtime: ApplicationRuntime) -> None:
        """Decode original image bytes and build a fail-closed G1/S1 preview."""

        preparation_headers = self.headers.get_all("X-MF1750-Preparation", [])
        if len(preparation_headers) != 1:
            raise ValueError("exactly one X-MF1750-Preparation header is required")
        content_type_headers = self.headers.get_all("Content-Type", [])
        if len(content_type_headers) != 1 or content_type_headers[0] not in {
            "image/png",
            "image/jpeg",
            "image/webp",
        }:
            raise ValueError(
                "conversion requires exactly one parameter-free PNG/JPEG/WebP Content-Type"
            )
        media_type = content_type_headers[0]
        preparation = _validate_preparation_request(
            _preparation_header(preparation_headers[0]), runtime, media_type
        )
        source_bytes = self._read(MAX_SOURCE_IMAGE_BODY)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        if source_sha256 != preparation["source"]["expected_sha256"]:
            raise ValueError("server-recomputed source SHA-256 does not match the request")

        if not runtime.try_begin_generation_work():
            raise RequestRejected(
                HTTPStatus.CONFLICT, "another G1/S1 simulation is already in progress"
            )
        try:
            generation_epoch = self._operation(runtime.begin_generation)
            geometry = preparation["geometry"]
            decoded = decode_normalized_source(
                source_bytes,
                media_type,
                geometry["fit"],
                rotation_degrees=geometry["rotation_degrees"],
            )
            if decoded.source_sha256 != source_sha256:
                raise ApplicationError("decoder source identity differs from server hash")

            mapping_request = preparation["mapping"]
            mapping_options = MappingOptions(
                mode=(
                    MappingMode.NONE
                    if mapping_request["algorithm"] == "none"
                    else MappingMode.GAMUT_MAP
                ),
                intent=mapping_request["intent"],
                strength=mapping_request["strength"],
            )
            budget_request = preparation["halftone"]["budget"]
            budget = (
                None
                if budget_request is None
                else SimulationBudget(
                    max_evaluations=budget_request["max_evaluations"],
                    max_accepted_moves=budget_request["max_accepted_moves"],
                    stagnation_evaluations=budget_request[
                        "stagnation_evaluations"
                    ],
                )
            )
            protections = preparation["protections"]
            simulation = simulate_panel(
                decoded.raster,
                palette=runtime.palette,
                profile=mapping_request["profile"],
                options=SimulationOptions(
                    algorithm=preparation["halftone"]["algorithm"],
                    mapping=mapping_options,
                    seed=preparation["halftone"]["seed"],
                    budget=budget,
                    white_protection=protections["white"],
                    preserve_edges=protections["edge"],
                    text_mode=protections["text"],
                ),
            )
            source = InputSource(
                "browser-selected-image",
                media_type,
                source_sha256,
                "server-recomputed SHA256 of original selected file bytes",
            )
            artifact = prepare_simulation_artifact(
                simulation,
                source,
                decode_provenance=decoded.provenance,
            )
            status = self._operation(
                lambda: runtime.commit_generation(
                    generation_epoch,
                    artifact,
                    {
                        "source": artifact.source_preview_png,
                        "mapped": artifact.mapped_preview_png,
                        "final": artifact.preview_png,
                        "model": artifact.model_preview_png,
                    },
                )
            )
        finally:
            runtime.end_generation_work()

        identity = artifact.identity
        report = artifact.report
        report_sha256 = identity["report_sha256"]
        previews = {
            stage: {
                **metadata,
                "url": (
                    f"/application/artifact/{report_sha256}/preview/{stage}"
                ),
            }
            for stage, metadata in report["previews"].items()
        }
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "schema": "mf1750-prepare-response",
                "version": 2,
                "artifact_identity": identity,
                "previews": previews,
                "report": report,
                "status": status,
            },
        )


class ApplicationHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        runtime: ApplicationRuntime,
        *,
        security_token: Optional[str] = None,
    ) -> None:
        if security_token is not None and (
            not isinstance(security_token, str)
            or len(security_token) < 32
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in security_token
            )
        ):
            raise ValueError(
                "security_token must contain at least 32 URL-safe ASCII characters"
            )
        requested_address = ipaddress.ip_address(address[0])
        if not requested_address.is_loopback:
            raise ValueError("server address must be a numeric loopback address")
        self.address_family = (
            socket.AF_INET6 if requested_address.version == 6 else socket.AF_INET
        )
        super().__init__(address, ApplicationHandler)
        self.runtime = runtime
        self.security_token = security_token or secrets.token_urlsafe(32)
        bound_host = str(self.server_address[0])
        address_literal = ipaddress.ip_address(bound_host)
        display_host = f"[{bound_host}]" if address_literal.version == 6 else bound_host
        self.authority = f"{display_host}:{self.server_port}"
        self.origin = f"http://{self.authority}"
        if runtime.n6_formal_controller is not None:
            runtime.n6_formal_controller.bind_server_origin(self.origin)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="listen address (default loopback)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--palette", type=Path, help="optional measured palette JSON")
    parser.add_argument("--enable-device", action="store_true", help="enable opt-in HTTP adapter")
    parser.add_argument("--device-url", help="explicit device root URL; never printed or reported")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if not ipaddress.ip_address(args.bind).is_loopback:
            raise SystemExit("--bind must be a numeric loopback address")
    except ValueError as error:
        raise SystemExit("--bind must be a numeric loopback address") from error
    if args.enable_device != bool(args.device_url):
        raise SystemExit("--enable-device and --device-url must be supplied together")
    palette = load_palette(args.palette) if args.palette else reference_palette()
    adapter: OfflineAdapter | HttpDeviceAdapter
    adapter = HttpDeviceAdapter(args.device_url) if args.enable_device else OfflineAdapter()
    runtime = ApplicationRuntime(palette, adapter)
    server = ApplicationHttpServer((args.bind, args.port), runtime)
    print(f"MF-1750 application UI: {server.origin}/#token={server.security_token}")
    print("Hardware tested: NO; no device request is sent until UI connection permission.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
