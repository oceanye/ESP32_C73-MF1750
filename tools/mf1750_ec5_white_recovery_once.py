#!/usr/bin/env python3
"""One-shot RC2G solid-white actions for the EC5 no-dither campaign.

This runner owns three workspace-global actions: the initial white baseline,
the recovery after U04, and the recovery after U07.  It never uploads
firmware.  A permanent host claim is durably created before the sole allowed
``POST /api/frame``.  Every other device request is read-only.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import ControllerMapping, generate_fixture  # noqa: E402
from tools import mf1750_ec5_physical_once as candidate_runner  # noqa: E402
from tools import mf1750_frame_tool as frame_tool  # noqa: E402


RESULT_KIND = "mf1750-ec5-solid-white-physical-once-result"
CLAIM_KIND = "mf1750-ec5-solid-white-permanent-host-claim"
REGISTRY_ID = "workspace-mf1750-ec5-solid-white-claim-registry-v1"
DEFAULT_CLAIM_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_white_claims"
)
RC2G_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_"
    "WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
DRIVER_API = "MF1750_R16_CASCADE_V3"
STAGES = ("baseline", "after-u04", "after-u07")
ACTION_IDS = {
    "baseline": "aace554437b5377138825a473dbb0be1591fc472424c446d77e148bae9eeded7",
    "after-u04": "f528dcbab32691a1faeca019d1845d032ed2d1936be7d496ef9acaec5be07c01",
    "after-u07": "feb0a26499921516473ca68d10ed6a51e1ffd5672f29bae67b46590d3b7f9cf4",
}
WHITE_FRAME = generate_fixture("solid-white")
WHITE_FRAME_BYTES = 307_200
WHITE_FRAME_SHA256 = hashlib.sha256(WHITE_FRAME).hexdigest()
WHITE_FRAME_FNV1A = 0x13340DC5
WHITE_DTM_FNV1A = 0xB7A855C5
RC2G_BINARY_BYTES = 815_664
RC2G_BINARY_SHA256 = (
    "9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772"
)
MAPPINGS = (ControllerMapping(0), ControllerMapping(1))
AUTH_SUFFIX = "__NO_RETRY_NO_RECOVERY"
MAX_JSON_BYTES = 8 * 1024 * 1024
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


class WhiteRecoveryError(RuntimeError):
    """The requested action or evidence failed closed."""


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as error:
        raise WhiteRecoveryError(f"value is not canonical JSON: {error}") from error


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WhiteRecoveryError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file():
            raise WhiteRecoveryError(f"{label} must be a regular non-symlink file")
        before = path.stat()
        if before.st_size > maximum:
            raise WhiteRecoveryError(f"{label} exceeds its size limit")
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise WhiteRecoveryError(f"cannot read {label}: {error}") from error
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(payload) != after.st_size
    ):
        raise WhiteRecoveryError(f"{label} changed while read")
    return payload


def _json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                WhiteRecoveryError(f"{label} contains {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WhiteRecoveryError(f"{label} is not UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise WhiteRecoveryError(f"{label} root must be an object")
    return value


def _keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise WhiteRecoveryError(f"{label} fields differ from contract")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise WhiteRecoveryError(f"{label} must be RFC3339 text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WhiteRecoveryError(f"{label} is not RFC3339") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise WhiteRecoveryError(f"{label} lacks a UTC offset")
    return result


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["integrity"] = {"canonical_sha256": None}
    result["integrity"]["canonical_sha256"] = _sha(_canonical(result))
    return result


def _validate_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _keys(
        root.get("integrity"), {"canonical_sha256"}, label=f"{label}.integrity"
    )
    digest = integrity["canonical_sha256"]
    if not isinstance(digest, str) or _SHA_RE.fullmatch(digest) is None:
        raise WhiteRecoveryError(f"{label} integrity digest is malformed")
    unsigned = deepcopy(dict(root))
    unsigned["integrity"]["canonical_sha256"] = None
    if _sha(_canonical(unsigned)) != digest:
        raise WhiteRecoveryError(f"{label} integrity mismatch")
    return digest


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(value)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise WhiteRecoveryError(f"refusing to overwrite {path}") from error
    return payload


def _panel(path: Path) -> dict[str, str]:
    payload = _read(Path(path), label="live panel identity", maximum=64 * 1024)
    try:
        return candidate_runner._validate_panel(
            _json(payload, label="live panel identity"), label="live panel identity"
        )
    except candidate_runner.Ec5PhysicalError as error:
        raise WhiteRecoveryError(str(error)) from error


def _rc2g_binary(path: Path) -> dict[str, Any]:
    payload = _read(Path(path), label="frozen RC2G firmware", maximum=32 * 1024 * 1024)
    if len(payload) != RC2G_BINARY_BYTES or _sha(payload) != RC2G_BINARY_SHA256:
        raise WhiteRecoveryError(
            "firmware is not the exact hardware-proven RC2G binary; the current "
            "production build is not an allowed substitute"
        )
    if RC2G_BUILD_TAG.encode("ascii") not in payload:
        raise WhiteRecoveryError("frozen RC2G binary omits its exact build tag")
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "sha256": _sha(payload),
    }


def required_authorization(stage: str) -> str:
    stage = stage.lower()
    if stage not in STAGES:
        raise WhiteRecoveryError(f"stage must be one of {STAGES}")
    label = stage.upper().replace("-", "_")
    return (
        f"AUTHORIZE_ONE_VISIBLE_RC2G_EC5_SOLID_WHITE_{label}__ACTION_"
        f"{ACTION_IDS[stage].upper()}{AUTH_SUFFIX}"
    )


def load_candidate_result_binding(
    *,
    release_file: Path,
    candidate_id: str,
    result_file: Path,
    panel_file: Path,
    claim_registry: Path = candidate_runner.DEFAULT_CLAIM_REGISTRY,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    rc2g_binary_file: Path | None = None,
    white_claim_registry: Path | None = None,
) -> dict[str, Any]:
    """Replay a real Stage-A result and its permanent claim."""

    candidate_id = candidate_id.upper()
    if candidate_id not in ("U04", "U07"):
        raise WhiteRecoveryError("candidate_id must be U04 or U07")
    u07_prerequisites = (
        u04_review_file,
        u04_result_file,
        u04_hold_0_file,
        u04_hold_5_file,
        u04_hold_30_file,
        u04_white_recovery_result_file,
        rc2g_binary_file,
    )
    if candidate_id == "U07" and any(path is None for path in u07_prerequisites):
        raise WhiteRecoveryError(
            "U07 replay requires exact U04 result, hold0/5/30, after-u04 white "
            "result, frozen RC2G binary, and finalized review"
        )
    if candidate_id == "U04" and any(
        path is not None for path in (*u07_prerequisites, white_claim_registry)
    ):
        raise WhiteRecoveryError("U04 result replay rejects U07-only prerequisites")
    try:
        context = candidate_runner.load_release(
            Path(release_file), candidate_id, panel_file=Path(panel_file)
        )
        result = candidate_runner.validate_result(
            context,
            Path(result_file),
            claim_registry=Path(claim_registry),
            u04_review_file=u04_review_file,
            u04_result_file=u04_result_file,
            u04_hold_0_file=u04_hold_0_file,
            u04_hold_5_file=u04_hold_5_file,
            u04_hold_30_file=u04_hold_30_file,
            u04_white_recovery_result_file=u04_white_recovery_result_file,
            rc2g_binary_file=rc2g_binary_file,
            white_claim_registry=white_claim_registry,
        )
    except candidate_runner.Ec5PhysicalError as error:
        raise WhiteRecoveryError(f"candidate result replay failed: {error}") from error
    if result["outcome"] != "complete_pass":
        raise WhiteRecoveryError("candidate result is not complete_pass")
    result_payload = _read(Path(result_file), label=f"{candidate_id} physical result")
    claim_path = Path(claim_registry) / f"{context.variant['action_id']}.json"
    claim_payload = _read(claim_path, label=f"{candidate_id} permanent claim")
    return {
        "candidate_id": candidate_id,
        "release_file": str(Path(release_file).resolve()),
        "release_canonical_sha256": context.release_canonical_sha256,
        "firmware_sha256": context.binary_sha256,
        "panel": dict(context.panel),
        "action_id": context.variant["action_id"],
        "attempt_id": result["attempt_id"],
        "outcome": "complete_pass",
        "result_file": str(Path(result_file).resolve()),
        "result_bytes": len(result_payload),
        "result_file_sha256": _sha(result_payload),
        "result_integrity_sha256": result["integrity"]["canonical_sha256"],
        "claim_file": str(claim_path.resolve()),
        "claim_bytes": len(claim_payload),
        "claim_file_sha256": _sha(claim_payload),
    }


def _expected_candidate(stage: str) -> str | None:
    return {"baseline": None, "after-u04": "U04", "after-u07": "U07"}[stage]


def _candidate_binding(
    stage: str,
    *,
    release_file: Path | None,
    candidate_result_file: Path | None,
    panel_file: Path,
    candidate_claim_registry: Path,
    u04_review_file: Path | None,
    u04_result_file: Path | None,
    u04_hold_0_file: Path | None,
    u04_hold_5_file: Path | None,
    u04_hold_30_file: Path | None,
    u04_white_recovery_result_file: Path | None,
    u04_rc2g_binary_file: Path | None,
    u04_white_claim_registry: Path | None,
) -> dict[str, Any] | None:
    candidate = _expected_candidate(stage)
    if candidate is None:
        if (
            release_file is not None
            or candidate_result_file is not None
            or u04_review_file is not None
            or u04_result_file is not None
            or u04_hold_0_file is not None
            or u04_hold_5_file is not None
            or u04_hold_30_file is not None
            or u04_white_recovery_result_file is not None
            or u04_rc2g_binary_file is not None
            or u04_white_claim_registry is not None
        ):
            raise WhiteRecoveryError("baseline does not accept candidate prerequisites")
        return None
    if release_file is None or candidate_result_file is None:
        raise WhiteRecoveryError(
            f"{stage} requires the real {candidate} release and result"
        )
    if candidate == "U04" and any(
        path is not None
        for path in (
            u04_review_file,
            u04_result_file,
            u04_hold_0_file,
            u04_hold_5_file,
            u04_hold_30_file,
            u04_white_recovery_result_file,
            u04_rc2g_binary_file,
            u04_white_claim_registry,
        )
    ):
        raise WhiteRecoveryError("after-u04 rejects U07-only prerequisites")
    return load_candidate_result_binding(
        release_file=release_file,
        candidate_id=candidate,
        result_file=candidate_result_file,
        panel_file=panel_file,
        claim_registry=candidate_claim_registry,
        u04_review_file=u04_review_file,
        u04_result_file=u04_result_file,
        u04_hold_0_file=u04_hold_0_file,
        u04_hold_5_file=u04_hold_5_file,
        u04_hold_30_file=u04_hold_30_file,
        u04_white_recovery_result_file=u04_white_recovery_result_file,
        rc2g_binary_file=u04_rc2g_binary_file,
        white_claim_registry=u04_white_claim_registry,
    )


class _AuditRequester:
    def __init__(self, delegate: frame_tool.HttpRequester):
        self.delegate = delegate
        self.records: list[dict[str, Any]] = []
        self.post_count = 0

    def __call__(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        allowed = {
            ("GET", "/api/version"),
            ("GET", "/api/job"),
            ("GET", "/api/diagnostic/report"),
            ("GET", "/api/diagnostic/status"),
            ("POST", "/api/frame"),
        }
        if (method, path) not in allowed:
            raise WhiteRecoveryError(f"request outside fixed allowlist: {method} {path}")
        if method == "POST":
            self.post_count += 1
            if self.post_count > 1:
                raise WhiteRecoveryError("second POST is permanently forbidden")
            if data != WHITE_FRAME:
                raise WhiteRecoveryError("POST body is not the frozen solid-white frame")
        status, body = self.delegate(
            base_url, path, method=method, data=data, timeout=timeout
        )
        self.records.append(
            {
                "method": method,
                "path": path,
                "request_bytes": 0 if data is None else len(data),
                "request_sha256": None if data is None else _sha(data),
                "status": status,
                "response_body": body,
            }
        )
        return status, body


def _parse_json_body(record: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    body = record.get("response_body")
    if not isinstance(body, str):
        raise WhiteRecoveryError(f"{label} response body is not text")
    return _json(body.encode("utf-8"), label=label)


def _fresh_preflight(
    base_url: str,
    requester: _AuditRequester,
) -> dict[str, Any]:
    try:
        version = frame_tool._preflight_version(base_url, requester, MAPPINGS)
    except frame_tool.FrameToolError as error:
        raise WhiteRecoveryError(f"RC2G version preflight failed: {error}") from error
    if version["build_tag"] != RC2G_BUILD_TAG or version["driver_api"] != DRIVER_API:
        raise WhiteRecoveryError("device is not the exact RC2G build/API")
    raw: dict[str, Any] = {"version": version}
    for key, path in (
        ("job", "/api/job"),
        ("report", "/api/diagnostic/report"),
        ("gpio", "/api/diagnostic/status"),
    ):
        status, body = requester(
            base_url, path, method="GET", data=None, timeout=20.0
        )
        if status != 200:
            raise WhiteRecoveryError(f"fresh preflight {path} returned {status}")
        raw[key] = _json(body.encode("utf-8"), label=f"fresh preflight {path}")
    job = _keys(
        raw["job"],
        {
            "job_id",
            "action",
            "state",
            "result",
            "queued_at_ms",
            "started_at_ms",
            "finished_at_ms",
            "frame_fnv1a",
        },
        label="fresh job",
    )
    if job != {
        "job_id": 0,
        "action": "none",
        "state": "idle",
        "result": None,
        "queued_at_ms": 0,
        "started_at_ms": 0,
        "finished_at_ms": 0,
        "frame_fnv1a": 0,
    }:
        raise WhiteRecoveryError("RC2G is not at fresh job0 idle state")
    report = _keys(
        raw["report"], {"schema_version", "valid", "error"}, label="fresh report"
    )
    if report != {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    }:
        raise WhiteRecoveryError("RC2G already has a completed diagnostic report")
    gpio = _keys(raw["gpio"], {"busy", "rst", "cs", "cs2"}, label="fresh GPIO")
    if gpio != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}:
        raise WhiteRecoveryError("RC2G preflight GPIO is not safe idle")
    return raw


def _claim_path(registry: Path, stage: str) -> Path:
    return Path(registry) / f"{ACTION_IDS[stage]}.json"


def _create_claim(
    *,
    stage: str,
    registry: Path,
    panel: Mapping[str, str],
    preflight: Mapping[str, Any],
    candidate_binding: Mapping[str, Any] | None,
    attempt_id: str,
    rc2g_binary: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes, Path]:
    registry = Path(registry)
    if registry.exists() and (registry.is_symlink() or not registry.is_dir()):
        raise WhiteRecoveryError("white claim registry is unsafe")
    registry.mkdir(parents=True, exist_ok=True)
    path = _claim_path(registry, stage)
    claim = _seal(
        {
            "schema_version": 1,
            "kind": CLAIM_KIND,
            "registry_id": REGISTRY_ID,
            "stage": stage,
            "action_id": ACTION_IDS[stage],
            "attempt_id": attempt_id,
            "created_at": _now(),
            "panel": dict(panel),
            "rc2g_build_tag": RC2G_BUILD_TAG,
            "driver_api": DRIVER_API,
            "rc2g_binary": deepcopy(dict(rc2g_binary)),
            "frame_sha256": WHITE_FRAME_SHA256,
            "frame_fnv1a": WHITE_FRAME_FNV1A,
            "preflight_sha256": _sha(_canonical(preflight)),
            "candidate_binding": deepcopy(candidate_binding),
            "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
        }
    )
    payload = _write_new(path, claim)
    return claim, payload, path


def _claim_reference(claim: Mapping[str, Any], payload: bytes, path: Path) -> dict[str, Any]:
    return {
        "filename": path.name,
        "file_sha256": _sha(payload),
        "integrity_sha256": claim["integrity"]["canonical_sha256"],
        "attempt_id": claim["attempt_id"],
        "state": claim["state"],
    }


def _replay_success(transcript: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(transcript) < 8:
        raise WhiteRecoveryError("successful transcript is too short")
    first_paths = [record.get("path") for record in transcript[:4]]
    if first_paths != [
        "/api/version",
        "/api/job",
        "/api/diagnostic/report",
        "/api/diagnostic/status",
    ]:
        raise WhiteRecoveryError("fresh preflight request order changed")
    if any(record.get("method") != "GET" for record in transcript[:4]):
        raise WhiteRecoveryError("fresh preflight was not GET-only")

    version_body = transcript[0].get("response_body")
    if not isinstance(version_body, str):
        raise WhiteRecoveryError("fresh version response is malformed")
    try:
        version = frame_tool._parse_version(version_body, MAPPINGS)
    except frame_tool.FrameToolError as error:
        raise WhiteRecoveryError(f"stored RC2G version failed replay: {error}") from error
    if version["build_tag"] != RC2G_BUILD_TAG:
        raise WhiteRecoveryError("stored version is not exact RC2G")
    # Re-run the strict fresh-state checks on the stored first four responses.
    job0 = _parse_json_body(transcript[1], label="stored fresh job")
    report0 = _parse_json_body(transcript[2], label="stored fresh report")
    gpio0 = _parse_json_body(transcript[3], label="stored fresh GPIO")
    if job0 != {
        "job_id": 0,
        "action": "none",
        "state": "idle",
        "result": None,
        "queued_at_ms": 0,
        "started_at_ms": 0,
        "finished_at_ms": 0,
        "frame_fnv1a": 0,
    } or report0 != {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    } or gpio0 != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}:
        raise WhiteRecoveryError("stored fresh preflight does not prove job0/safe GPIO")

    posts = [record for record in transcript if record.get("method") == "POST"]
    if len(posts) != 1 or posts[0].get("path") != "/api/frame":
        raise WhiteRecoveryError("stored transcript does not contain exactly one frame POST")
    if posts[0].get("request_bytes") != WHITE_FRAME_BYTES or posts[0].get(
        "request_sha256"
    ) != WHITE_FRAME_SHA256:
        raise WhiteRecoveryError("stored POST is not the frozen white frame")
    if posts[0].get("status") != 202:
        raise WhiteRecoveryError("stored frame POST was not accepted")
    queued = _parse_json_body(posts[0], label="stored enqueue")
    try:
        frame_tool._validate_transfer_response(
            queued, WHITE_FRAME_FNV1A, "stored enqueue"
        )
    except frame_tool.FrameToolError as error:
        raise WhiteRecoveryError(f"stored enqueue failed replay: {error}") from error
    job_id = queued.get("job_id")
    if job_id != 1:
        raise WhiteRecoveryError("solid-white action is not fresh job1")
    terminal_job: Mapping[str, Any] | None = None
    diagnostic_raw: Mapping[str, Any] | None = None
    for record in transcript[4:]:
        pair = (record.get("method"), record.get("path"))
        if pair == ("GET", "/api/job"):
            candidate = _parse_json_body(record, label="stored job")
            try:
                state = frame_tool._validate_job(candidate, job_id, WHITE_FRAME_FNV1A)
            except frame_tool.FrameToolError as error:
                raise WhiteRecoveryError(f"stored job failed replay: {error}") from error
            if state == "completed":
                terminal_job = candidate
        elif pair == ("GET", "/api/diagnostic/report"):
            diagnostic_raw = _parse_json_body(record, label="stored diagnostic")
        elif pair not in (("GET", "/api/version"), ("POST", "/api/frame")):
            raise WhiteRecoveryError(f"unexpected stored request {pair}")
    if terminal_job is None or diagnostic_raw is None:
        raise WhiteRecoveryError("stored terminal job/diagnostic is missing")
    try:
        diagnostic = frame_tool._validate_diagnostic(
            diagnostic_raw, WHITE_FRAME, MAPPINGS, version, terminal_job
        )
    except frame_tool.FrameToolError as error:
        raise WhiteRecoveryError(f"stored diagnostic failed replay: {error}") from error
    if diagnostic["operation_id"] != 1 or diagnostic["job_operation_id"] != 1:
        raise WhiteRecoveryError("solid-white action is not fresh operation1")
    physical = diagnostic["physical_controllers"]
    if [item["dtm_fnv1a"] for item in physical] != [
        WHITE_DTM_FNV1A,
        WHITE_DTM_FNV1A,
    ]:
        raise WhiteRecoveryError("solid-white DTM identity mismatch")
    return {
        "version": version,
        "job": deepcopy(terminal_job),
        "diagnostic": diagnostic,
    }


def preflight(
    *,
    stage: str,
    base_url: str,
    panel_file: Path,
    rc2g_binary_file: Path,
    release_file: Path | None = None,
    candidate_result_file: Path | None = None,
    candidate_claim_registry: Path = candidate_runner.DEFAULT_CLAIM_REGISTRY,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    u04_rc2g_binary_file: Path | None = None,
    u04_white_claim_registry: Path | None = None,
    requester: frame_tool.HttpRequester = frame_tool.http_request,
) -> dict[str, Any]:
    stage = stage.lower()
    if stage not in STAGES:
        raise WhiteRecoveryError(f"stage must be one of {STAGES}")
    binary = _rc2g_binary(rc2g_binary_file)
    panel = _panel(panel_file)
    binding = _candidate_binding(
        stage,
        release_file=release_file,
        candidate_result_file=candidate_result_file,
        panel_file=panel_file,
        candidate_claim_registry=candidate_claim_registry,
        u04_review_file=u04_review_file,
        u04_result_file=u04_result_file,
        u04_hold_0_file=u04_hold_0_file,
        u04_hold_5_file=u04_hold_5_file,
        u04_hold_30_file=u04_hold_30_file,
        u04_white_recovery_result_file=u04_white_recovery_result_file,
        u04_rc2g_binary_file=u04_rc2g_binary_file,
        u04_white_claim_registry=u04_white_claim_registry,
    )
    audited = _AuditRequester(requester)
    fresh = _fresh_preflight(base_url, audited)
    return {
        "stage": stage,
        "action_id": ACTION_IDS[stage],
        "panel": panel,
        "rc2g_binary": binary,
        "candidate_binding": binding,
        "fresh": fresh,
        "transcript": audited.records,
        "get_requests": len(audited.records),
        "post_requests": 0,
        "claim_created": False,
    }


def run_once(
    *,
    stage: str,
    base_url: str,
    authorization: str,
    panel_file: Path,
    rc2g_binary_file: Path,
    result_file: Path,
    release_file: Path | None = None,
    candidate_result_file: Path | None = None,
    candidate_claim_registry: Path = candidate_runner.DEFAULT_CLAIM_REGISTRY,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    u04_rc2g_binary_file: Path | None = None,
    u04_white_claim_registry: Path | None = None,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    requester: frame_tool.HttpRequester = frame_tool.http_request,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    stage = stage.lower()
    if authorization != required_authorization(stage):
        raise WhiteRecoveryError("exact stage/action authorization is required")
    binary = _rc2g_binary(rc2g_binary_file)
    panel = _panel(panel_file)
    binding = _candidate_binding(
        stage,
        release_file=release_file,
        candidate_result_file=candidate_result_file,
        panel_file=panel_file,
        candidate_claim_registry=candidate_claim_registry,
        u04_review_file=u04_review_file,
        u04_result_file=u04_result_file,
        u04_hold_0_file=u04_hold_0_file,
        u04_hold_5_file=u04_hold_5_file,
        u04_hold_30_file=u04_hold_30_file,
        u04_white_recovery_result_file=u04_white_recovery_result_file,
        u04_rc2g_binary_file=u04_rc2g_binary_file,
        u04_white_claim_registry=u04_white_claim_registry,
    )
    if _claim_path(Path(claim_registry), stage).exists():
        raise WhiteRecoveryError("this global white stage already has a permanent claim")
    audited = _AuditRequester(requester)
    fresh = _fresh_preflight(base_url, audited)
    attempt_id = str(uuid.uuid4())
    claim, claim_payload, claim_path = _create_claim(
        stage=stage,
        registry=claim_registry,
        panel=panel,
        preflight=fresh,
        candidate_binding=binding,
        attempt_id=attempt_id,
        rc2g_binary=binary,
    )
    started_at = _now()
    outcome = "unknown_do_not_retry_or_recover"
    error_text: str | None = None
    protocol: Mapping[str, Any] | None = None
    try:
        protocol = frame_tool.perform_refresh(
            base_url,
            WHITE_FRAME,
            expected_mappings=MAPPINGS,
            requester=audited,
            sleeper=sleeper,
            clock=clock,
        )
        replay = _replay_success(audited.records)
        if protocol["preflight"] != replay["version"] or protocol["job"] != replay["job"]:
            raise WhiteRecoveryError("live protocol result differs from transcript replay")
        if protocol["diagnostic"] != replay["diagnostic"]:
            raise WhiteRecoveryError("live diagnostic differs from transcript replay")
        outcome = "complete_pass"
    except Exception as error:  # the durable claim forbids every retry/recovery
        error_text = str(error)
    result = _seal(
        {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "stage": stage,
            "action_id": ACTION_IDS[stage],
            "attempt_id": attempt_id,
            "panel": panel,
            "rc2g_build_tag": RC2G_BUILD_TAG,
            "driver_api": DRIVER_API,
            "rc2g_binary": binary,
            "frame_bytes": WHITE_FRAME_BYTES,
            "frame_sha256": WHITE_FRAME_SHA256,
            "frame_fnv1a": WHITE_FRAME_FNV1A,
            "dtm_fnv1a": WHITE_DTM_FNV1A,
            "candidate_binding": binding,
            "authorization_confirmation_sha256": _sha(authorization.encode("utf-8")),
            "claim": _claim_reference(claim, claim_payload, claim_path),
            "started_at": started_at,
            "completed_at": _now(),
            "outcome": outcome,
            "error": error_text,
            "network": {
                "get_requests": sum(
                    record["method"] == "GET" for record in audited.records
                ),
                "post_requests": audited.post_count,
                "maximum_post_requests": 1,
                "no_retry": True,
                "no_recovery": True,
            },
            "fresh_preflight": fresh,
            "transcript": audited.records,
            "protocol": deepcopy(protocol),
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
    )
    _write_new(Path(result_file), result)
    return result


def validate_result(
    *,
    result_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    release_file: Path | None = None,
    candidate_result_file: Path | None = None,
    candidate_claim_registry: Path = candidate_runner.DEFAULT_CLAIM_REGISTRY,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    u04_rc2g_binary_file: Path | None = None,
    u04_white_claim_registry: Path | None = None,
) -> dict[str, Any]:
    payload = _read(Path(result_file), label="solid-white result")
    root = _json(payload, label="solid-white result")
    _keys(
        root,
        {
            "schema_version",
            "kind",
            "stage",
            "action_id",
            "attempt_id",
            "panel",
            "rc2g_build_tag",
            "driver_api",
            "rc2g_binary",
            "frame_bytes",
            "frame_sha256",
            "frame_fnv1a",
            "dtm_fnv1a",
            "candidate_binding",
            "authorization_confirmation_sha256",
            "claim",
            "started_at",
            "completed_at",
            "outcome",
            "error",
            "network",
            "fresh_preflight",
            "transcript",
            "protocol",
            "state",
            "integrity",
        },
        label="solid-white result",
    )
    if root["schema_version"] != 1 or root["kind"] != RESULT_KIND:
        raise WhiteRecoveryError("unsupported solid-white result")
    _validate_integrity(root, label="solid-white result")
    stage = root["stage"]
    if stage not in STAGES or root["action_id"] != ACTION_IDS[stage]:
        raise WhiteRecoveryError("solid-white stage/action mismatch")
    binary = _rc2g_binary(rc2g_binary_file)
    panel = _panel(panel_file)
    if root["panel"] != panel:
        raise WhiteRecoveryError("solid-white result panel mismatch")
    binding = _candidate_binding(
        stage,
        release_file=release_file,
        candidate_result_file=candidate_result_file,
        panel_file=panel_file,
        candidate_claim_registry=candidate_claim_registry,
        u04_review_file=u04_review_file,
        u04_result_file=u04_result_file,
        u04_hold_0_file=u04_hold_0_file,
        u04_hold_5_file=u04_hold_5_file,
        u04_hold_30_file=u04_hold_30_file,
        u04_white_recovery_result_file=u04_white_recovery_result_file,
        u04_rc2g_binary_file=u04_rc2g_binary_file,
        u04_white_claim_registry=u04_white_claim_registry,
    )
    exact = {
        "rc2g_build_tag": RC2G_BUILD_TAG,
        "driver_api": DRIVER_API,
        "rc2g_binary": binary,
        "frame_bytes": WHITE_FRAME_BYTES,
        "frame_sha256": WHITE_FRAME_SHA256,
        "frame_fnv1a": WHITE_FRAME_FNV1A,
        "dtm_fnv1a": WHITE_DTM_FNV1A,
        "candidate_binding": binding,
        "authorization_confirmation_sha256": _sha(
            required_authorization(stage).encode("utf-8")
        ),
        "state": "authorization_permanently_consumed_do_not_rerun",
    }
    for key, expected in exact.items():
        if root[key] != expected:
            raise WhiteRecoveryError(f"solid-white result {key} mismatch")
    started = _timestamp(root["started_at"], label="result.started_at")
    completed = _timestamp(root["completed_at"], label="result.completed_at")
    if completed < started:
        raise WhiteRecoveryError("solid-white result timestamps are reversed")
    claim_ref = _keys(
        root["claim"],
        {"filename", "file_sha256", "integrity_sha256", "attempt_id", "state"},
        label="solid-white claim reference",
    )
    claim_path = _claim_path(Path(claim_registry), stage)
    if claim_ref["filename"] != claim_path.name:
        raise WhiteRecoveryError("solid-white claim filename mismatch")
    claim_payload = _read(claim_path, label="solid-white permanent claim")
    if claim_ref["file_sha256"] != _sha(claim_payload):
        raise WhiteRecoveryError("solid-white claim bytes mismatch")
    claim = _json(claim_payload, label="solid-white permanent claim")
    _validate_integrity(claim, label="solid-white permanent claim")
    claim_exact = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": REGISTRY_ID,
        "stage": stage,
        "action_id": ACTION_IDS[stage],
        "attempt_id": root["attempt_id"],
        "panel": panel,
        "rc2g_build_tag": RC2G_BUILD_TAG,
        "driver_api": DRIVER_API,
        "rc2g_binary": binary,
        "frame_sha256": WHITE_FRAME_SHA256,
        "frame_fnv1a": WHITE_FRAME_FNV1A,
        "preflight_sha256": _sha(_canonical(root["fresh_preflight"])),
        "candidate_binding": binding,
        "state": "permanently_claimed_before_first_post_no_retry_no_recovery",
    }
    _keys(
        claim,
        set(claim_exact) | {"created_at", "integrity"},
        label="solid-white permanent claim",
    )
    for key, expected in claim_exact.items():
        if claim.get(key) != expected:
            raise WhiteRecoveryError(f"solid-white claim {key} mismatch")
    claim_created = _timestamp(claim["created_at"], label="claim.created_at")
    if claim_created > started:
        raise WhiteRecoveryError("solid-white claim was not created before execution")
    if claim_ref["attempt_id"] != root["attempt_id"] or claim_ref[
        "integrity_sha256"
    ] != claim["integrity"]["canonical_sha256"] or claim_ref["state"] != claim["state"]:
        raise WhiteRecoveryError("solid-white claim reference mismatch")
    network = _keys(
        root["network"],
        {
            "get_requests",
            "post_requests",
            "maximum_post_requests",
            "no_retry",
            "no_recovery",
        },
        label="solid-white network evidence",
    )
    if network["maximum_post_requests"] != 1 or network["post_requests"] not in (0, 1):
        raise WhiteRecoveryError("solid-white POST count is invalid")
    if network["no_retry"] is not True or network["no_recovery"] is not True:
        raise WhiteRecoveryError("solid-white retry/recovery contract mismatch")
    transcript = root["transcript"]
    if not isinstance(transcript, list):
        raise WhiteRecoveryError("solid-white transcript must be a list")
    if network["get_requests"] != sum(
        isinstance(record, Mapping) and record.get("method") == "GET"
        for record in transcript
    ) or network["post_requests"] != sum(
        isinstance(record, Mapping) and record.get("method") == "POST"
        for record in transcript
    ):
        raise WhiteRecoveryError("solid-white request counts differ from transcript")
    if root["outcome"] == "complete_pass":
        if network["post_requests"] != 1 or root["error"] is not None:
            raise WhiteRecoveryError("complete white result lacks exact one POST")
        replay = _replay_success(transcript)
        protocol = root["protocol"]
        if not isinstance(protocol, Mapping):
            raise WhiteRecoveryError("complete white result lacks protocol evidence")
        if protocol.get("preflight") != replay["version"] or protocol.get("job") != replay["job"] or protocol.get("diagnostic") != replay["diagnostic"]:
            raise WhiteRecoveryError("stored protocol differs from raw transcript replay")
    elif root["outcome"] != "unknown_do_not_retry_or_recover":
        raise WhiteRecoveryError("solid-white outcome is invalid")
    return dict(root)


def load_result_binding(
    *,
    result_file: Path,
    panel_file: Path,
    rc2g_binary_file: Path,
    claim_registry: Path = DEFAULT_CLAIM_REGISTRY,
    release_file: Path | None = None,
    candidate_result_file: Path | None = None,
    candidate_claim_registry: Path = candidate_runner.DEFAULT_CLAIM_REGISTRY,
    u04_review_file: Path | None = None,
    u04_result_file: Path | None = None,
    u04_hold_0_file: Path | None = None,
    u04_hold_5_file: Path | None = None,
    u04_hold_30_file: Path | None = None,
    u04_white_recovery_result_file: Path | None = None,
    u04_rc2g_binary_file: Path | None = None,
    u04_white_claim_registry: Path | None = None,
) -> dict[str, Any]:
    """Deeply replay a white result and return its exact immutable reference."""

    result = validate_result(
        result_file=result_file,
        panel_file=panel_file,
        rc2g_binary_file=rc2g_binary_file,
        claim_registry=claim_registry,
        release_file=release_file,
        candidate_result_file=candidate_result_file,
        candidate_claim_registry=candidate_claim_registry,
        u04_review_file=u04_review_file,
        u04_result_file=u04_result_file,
        u04_hold_0_file=u04_hold_0_file,
        u04_hold_5_file=u04_hold_5_file,
        u04_hold_30_file=u04_hold_30_file,
        u04_white_recovery_result_file=u04_white_recovery_result_file,
        u04_rc2g_binary_file=u04_rc2g_binary_file,
        u04_white_claim_registry=u04_white_claim_registry,
    )
    if result["outcome"] != "complete_pass":
        raise WhiteRecoveryError("white result is not complete_pass")
    payload = _read(Path(result_file), label="solid-white result")
    return {
        "stage": result["stage"],
        "action_id": result["action_id"],
        "attempt_id": result["attempt_id"],
        "outcome": "complete_pass",
        "panel": deepcopy(result["panel"]),
        "rc2g_binary": deepcopy(result["rc2g_binary"]),
        "candidate_binding": deepcopy(result["candidate_binding"]),
        "file": str(Path(result_file).resolve()),
        "bytes": len(payload),
        "file_sha256": _sha(payload),
        "integrity_sha256": result["integrity"]["canonical_sha256"],
        "completed_at": result["completed_at"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "run", "validate"):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=STAGES, required=True)
        item.add_argument("--panel", type=Path, required=True)
        item.add_argument("--rc2g-binary", type=Path, required=True)
        item.add_argument("--release", type=Path)
        item.add_argument("--candidate-result", type=Path)
        item.add_argument("--u04-review", type=Path)
        item.add_argument("--u04-result", type=Path)
        item.add_argument("--u04-hold-0", type=Path)
        item.add_argument("--u04-hold-5", type=Path)
        item.add_argument("--u04-hold-30", type=Path)
        item.add_argument("--u04-white-recovery-result", type=Path)
        item.add_argument("--u04-rc2g-binary", type=Path)
        item.add_argument("--u04-white-claim-registry", type=Path)
        item.add_argument(
            "--candidate-claim-registry",
            type=Path,
            default=candidate_runner.DEFAULT_CLAIM_REGISTRY,
        )
        if name in ("preflight", "run"):
            item.add_argument("--base-url", required=True)
        if name in ("run", "validate"):
            item.add_argument("--result", type=Path, required=True)
            item.add_argument("--claim-registry", type=Path, default=DEFAULT_CLAIM_REGISTRY)
        if name == "run":
            item.add_argument("--authorize", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    common = {
        "stage": args.stage,
        "panel_file": args.panel,
        "rc2g_binary_file": args.rc2g_binary,
        "release_file": args.release,
        "candidate_result_file": args.candidate_result,
        "candidate_claim_registry": args.candidate_claim_registry,
        "u04_review_file": args.u04_review,
        "u04_result_file": args.u04_result,
        "u04_hold_0_file": args.u04_hold_0,
        "u04_hold_5_file": args.u04_hold_5,
        "u04_hold_30_file": args.u04_hold_30,
        "u04_white_recovery_result_file": args.u04_white_recovery_result,
        "u04_rc2g_binary_file": args.u04_rc2g_binary,
        "u04_white_claim_registry": args.u04_white_claim_registry,
    }
    try:
        if args.command == "preflight":
            output = preflight(base_url=args.base_url, **common)
        elif args.command == "run":
            output = run_once(
                base_url=args.base_url,
                authorization=args.authorize,
                result_file=args.result,
                claim_registry=args.claim_registry,
                **common,
            )
        else:
            common.pop("stage")
            output = validate_result(
                result_file=args.result,
                claim_registry=args.claim_registry,
                **common,
            )
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except WhiteRecoveryError as error:
        print(f"EC5 white recovery error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
