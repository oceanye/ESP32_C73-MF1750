#!/usr/bin/env python3
"""Run one fixed N7 MAP SPI action, then adjudicate its offline evidence.

The live phase permanently claims one exact action before any HTTP request and
can issue exactly one POST to its compile-time frequency endpoint.  It has no
retry, recovery, cancel, or alternate route.  A successful live phase remains
``protocol_pass_pending_adjudication`` until the separate offline finalizer
combines serial, scope, electrical, thermal, and visual evidence through the
existing SPI sweep analyzer.  Only a final ``pass`` result can authorize the
next frequency's action identity.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence

from tools import mf1750_frame_tool as frame_tool
from tools import mf1750_refresh_analyzer as analyzer
from tools import mf1750_n7_spi_sweep_campaign as campaign


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULT_KIND = "mf1750-n7-spi-sweep-live-result"
FINAL_RESULT_KIND = "mf1750-n7-spi-sweep-final-result"
CLAIM_KIND = "mf1750-n7-spi-sweep-action-claim"
CLAIM_REGISTRY_ID = "workspace-mf1750-n7-spi-sweep-claim-registry-v1"
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_n7_spi_sweep_claims"
)
ATTEMPT_LOCK_FILENAME = "ATTEMPT-LOCK.json"
LIVE_RESULT_FILENAME = "N7-SWEEP-LIVE-RESULT.json"
FINAL_RESULT_FILENAME = "N7-SWEEP-FINAL-RESULT.json"
DEFAULT_JOB_TIMEOUT_S = 180.0
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_N7_SPI_SWEEP"
LEGACY_LIVE_BLOCK_MESSAGE = (
    "legacy N7 live execution is disabled before claim/network: it is not "
    "bound to a physical panel, authenticated limit authority, current usage, "
    "or trusted profile review; use the physical production runner instead"
)


class N7SweepError(RuntimeError):
    """Rejected before claim, or invalid offline evidence."""


class N7SweepUnknown(N7SweepError):
    """The action claim exists and the visible action must never be repeated."""


@dataclass(frozen=True)
class CampaignSnapshot:
    directory: Path
    document: Mapping[str, Any]
    campaign_file_sha256: str
    firmware_sha256: str


@dataclass(frozen=True)
class Predecessor:
    final_path: Optional[Path]
    final_file_sha256: Optional[str]
    final_document: Optional[Mapping[str, Any]]
    live_document: Optional[Mapping[str, Any]]
    sweep_plan: Mapping[str, Any]


@dataclass(frozen=True)
class ActionContract:
    snapshot: CampaignSnapshot
    template: Mapping[str, Any]
    predecessor: Predecessor
    identity: Mapping[str, Any]
    identity_sha256: str
    authorization_confirmation: str


@dataclass(frozen=True)
class Claim:
    path: Path
    payload_sha256: str
    document: Mapping[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.path.name,
            "sha256": self.payload_sha256,
            "action_identity_sha256": self.document["action_identity_sha256"],
            "authorization_consumed_permanently": True,
        }


def _canonical(value: Any) -> bytes:
    return campaign.canonical_json(value)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _strict_json(payload: bytes, label: str) -> object:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N7SweepError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise N7SweepError(f"{label} contains unsupported constant {value}")

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N7SweepError(f"invalid {label}: {error}") from error


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise N7SweepError(f"{label} must not be a symlink")
    try:
        if not path.is_file():
            raise N7SweepError(f"{label} must be a regular file")
        return path.read_bytes()
    except OSError as error:
        raise N7SweepError(f"cannot read {label}: {error}") from error


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise N7SweepError(f"{label} must be 64 lowercase hexadecimal digits")
    return value


def _require_int(
    value: object, label: str, *, minimum: int = 0, maximum: int = 0xFFFFFFFF
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise N7SweepError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _parse_version_body(body: object) -> Mapping[str, str]:
    if not isinstance(body, str):
        raise N7SweepError("N7 version response must be text")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or lines[0] != campaign.FIRMWARE_BUILD_TAG:
        raise N7SweepError("device is not running the frozen N7 firmware build")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise N7SweepError("N7 version response contains an unscoped line")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in fields:
            raise N7SweepError("N7 version response contains duplicate fields")
        fields[key] = value.strip()
    expected = {
        "Panel": "1024x600",
        "Driver API": campaign.DRIVER_API_VERSION,
        "Frame bytes": str(campaign.FRAME_BYTES),
        "Refresh SPI Hz": "1000000",
        "N7 Sweep SPI Hz": "1000000,2000000,4000000,8000000,10000000",
        "CS1 Mapping": "0,0,0,0",
        "CS2 Mapping": "1,0,0,0",
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            raise N7SweepError(f"N7 version field {key!r} differs")
    for field in ("PSRAM bytes", "Free PSRAM"):
        try:
            if int(fields[field]) <= 0:
                raise ValueError
        except (KeyError, ValueError) as error:
            raise N7SweepError(f"N7 version field {field!r} is invalid") from error
    if set(fields) != {*expected, "PSRAM bytes", "Free PSRAM"}:
        raise N7SweepError("N7 version response fields differ from the fixed contract")
    return fields


def _snapshot_campaign(directory: Path) -> CampaignSnapshot:
    try:
        document = campaign.validate_campaign_directory(directory)
    except campaign.N7CampaignError as error:
        raise N7SweepError(f"campaign validation failed: {error}") from error
    manifest_bytes = _read_regular(directory / "campaign.json", "campaign.json")
    firmware_bytes = _read_regular(directory / "firmware.bin", "firmware.bin")
    if document["firmware"]["sha256"] != _sha256(firmware_bytes):
        raise N7SweepError("campaign firmware changed after validation")
    return CampaignSnapshot(
        directory=directory,
        document=deepcopy(document),
        campaign_file_sha256=_sha256(manifest_bytes),
        firmware_sha256=_sha256(firmware_bytes),
    )


def _action_template(snapshot: CampaignSnapshot, frequency_hz: int) -> Mapping[str, Any]:
    if type(frequency_hz) is not int or frequency_hz not in campaign.FREQUENCIES:
        raise N7SweepError("frequency must be one of 1/2/4/8/10 MHz")
    matches = [
        action
        for action in snapshot.document["actions"]
        if action.get("frequency_hz") == frequency_hz
    ]
    if len(matches) != 1:
        raise N7SweepError("campaign does not contain exactly one requested frequency")
    return deepcopy(matches[0])


def _load_canonical_json_file(path: Path, label: str) -> tuple[Mapping[str, Any], bytes]:
    payload = _read_regular(path, label)
    document = _strict_json(payload, label)
    if not isinstance(document, Mapping):
        raise N7SweepError(f"{label} must contain a JSON object")
    if _canonical(document) + b"\n" != payload:
        raise N7SweepError(f"{label} must be canonical JSON plus one newline")
    return document, payload


def _validate_live_result(
    document: Mapping[str, Any], snapshot: CampaignSnapshot, expected_frequency_hz: int
) -> None:
    if document.get("schema_version") != 1 or document.get("kind") != RESULT_KIND:
        raise N7SweepError("predecessor live result kind/schema is invalid")
    if document.get("outcome") != "protocol_pass_pending_adjudication":
        raise N7SweepError("predecessor live result did not reach protocol pass")
    if document.get("protocol_verified") is not True:
        raise N7SweepError("predecessor live result lacks protocol verification")
    if document.get("frequency_hz") != expected_frequency_hz:
        raise N7SweepError("predecessor live result frequency differs")
    binding = document.get("campaign")
    if not isinstance(binding, Mapping) or binding != {
        "campaign_id": campaign.CAMPAIGN_ID,
        "campaign_file_sha256": snapshot.campaign_file_sha256,
        "firmware_sha256": snapshot.firmware_sha256,
    }:
        raise N7SweepError("predecessor live result campaign binding differs")
    action_sha = _require_sha256(
        document.get("action_identity_sha256"), "predecessor action identity SHA-256"
    )
    identity = document.get("action_identity")
    if not isinstance(identity, Mapping) or _sha256(_canonical(identity)) != action_sha:
        raise N7SweepError("predecessor live action identity changed")
    expected_template = _action_template(snapshot, expected_frequency_hz)
    if identity.get("action_template") != expected_template:
        raise N7SweepError("predecessor live action template differs")
    if (
        identity.get("campaign_file_sha256") != snapshot.campaign_file_sha256
        or identity.get("firmware_sha256") != snapshot.firmware_sha256
        or identity.get("firmware_build_tag") != campaign.FIRMWARE_BUILD_TAG
        or identity.get("driver_api_version") != campaign.DRIVER_API_VERSION
        or identity.get("automatic_retry") is not False
        or identity.get("automatic_recovery") is not False
    ):
        raise N7SweepError("predecessor live action identity contract differs")
    claim = document.get("authorization_claim")
    if (
        not isinstance(claim, Mapping)
        or claim.get("registry_id") != CLAIM_REGISTRY_ID
        or claim.get("action_identity_sha256") != action_sha
        or claim.get("authorization_consumed_permanently") is not True
        or not isinstance(claim.get("filename"), str)
        or not claim.get("filename").endswith(".json")
    ):
        raise N7SweepError("predecessor live result claim binding differs")
    _require_sha256(claim.get("sha256"), "predecessor claim SHA-256")
    _validate_claim_reference(
        claim,
        snapshot=snapshot,
        action_identity_sha256=action_sha,
        frequency_hz=expected_frequency_hz,
        endpoint=expected_template["endpoint"],
    )
    if (
        document.get("authorization_consumed_permanently") is not True
        or document.get("automatic_retry_authorized") is not False
        or document.get("automatic_recovery_authorized") is not False
        or document.get("next_frequency_authorized") is not False
    ):
        raise N7SweepError("predecessor live result safety flags differ")

    plan_before = document.get("sweep_plan_before_action")
    if not isinstance(plan_before, Mapping):
        raise N7SweepError("predecessor live result lacks its sweep plan")
    try:
        plan_analysis = analyzer.analyze_document(plan_before)
    except analyzer.RefreshAnalysisError as error:
        raise N7SweepError(f"predecessor live sweep plan is invalid: {error}") from error
    if plan_analysis.get("next_frequency_hz") != expected_frequency_hz:
        raise N7SweepError("predecessor live frequency was not analyzer-approved")

    version_raw = document.get("version_raw")
    version_fields = document.get("version_fields")
    parsed_version = _parse_version_body(version_raw)
    if not isinstance(version_fields, Mapping) or dict(version_fields) != dict(parsed_version):
        raise N7SweepError("predecessor live parsed version fields differ")

    prior_job = document.get("prior_job")
    prior_diagnostic = document.get("prior_diagnostic")
    prior_gpio = document.get("prior_gpio")
    job = document.get("target_job")
    diagnostic = document.get("target_diagnostic")
    post_gpio = document.get("post_gpio")
    if not all(
        isinstance(value, Mapping)
        for value in (prior_job, prior_diagnostic, prior_gpio, job, diagnostic, post_gpio)
    ):
        raise N7SweepError("predecessor live result lacks target evidence")
    _validate_gpio(prior_gpio, "recorded pre-action")
    _validate_gpio(post_gpio, "recorded post-action")
    index = campaign.FREQUENCIES.index(expected_frequency_hz)
    if index == 0:
        _validate_job(prior_job, expected_id=0, state="idle", result=None)
        if prior_diagnostic != {
            "schema_version": 2,
            "valid": False,
            "error": "no_completed_job_report",
        }:
            raise N7SweepError("first live result did not begin at fresh job0/op0")
        prior_operation_id = 0
    else:
        previous_frequency = campaign.FREQUENCIES[index - 1]
        previous_runs = [
            run
            for run in plan_before["runs"]
            if run.get("spi_hz") == previous_frequency
        ]
        if len(previous_runs) != 1:
            raise N7SweepError("predecessor live plan lacks the previous frequency")
        previous_run = previous_runs[0]
        _validate_job(
            prior_job,
            expected_id=_require_int(previous_run.get("job_id"), "previous run job_id", minimum=1),
            state="completed",
            result=True,
        )
        if prior_diagnostic.get("operation_id") != previous_run.get("report_operation_id"):
            raise N7SweepError("predecessor live operation differs from the PASS plan")
        prior_operation_id = _require_int(
            prior_diagnostic.get("operation_id"), "prior diagnostic operation_id", minimum=1
        )
    expected_job_id = (int(prior_job["job_id"]) + 1) & 0xFFFFFFFF
    if expected_job_id == 0:
        expected_job_id = 1
    _validate_job(job, expected_id=expected_job_id, state="completed", result=True)
    expected_operation_id = (prior_operation_id + 1) & 0xFFFFFFFF
    if expected_operation_id == 0:
        expected_operation_id = 1
    _validate_diagnostic(
        diagnostic,
        frequency_hz=expected_frequency_hz,
        job=job,
        operation_id=expected_operation_id,
    )
    queued_response = document.get("queued_response")
    if not isinstance(queued_response, Mapping) or set(queued_response) != {"ok", "job"}:
        raise N7SweepError("predecessor live enqueue response differs")
    if queued_response.get("ok") is not True or not isinstance(queued_response.get("job"), Mapping):
        raise N7SweepError("predecessor live enqueue response is invalid")
    _validate_job(
        queued_response["job"],
        expected_id=expected_job_id,
        state="queued",
        result=None,
    )
    audit = document.get("request_audit")
    if not isinstance(audit, Mapping):
        raise N7SweepError("predecessor live request audit is missing")
    if (
        audit.get("visible_post_count") != 1
        or audit.get("visible_endpoint") != expected_template["endpoint"]
        or audit.get("retry_count") != 0
        or audit.get("recovery_count") != 0
    ):
        raise N7SweepError("predecessor live request audit safety fields differ")
    calls = audit.get("calls")
    if not isinstance(calls, list) or len(calls) < 8:
        raise N7SweepError("predecessor live request sequence is incomplete")
    expected_prefix = [
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("POST", expected_template["endpoint"]),
    ]
    observed = []
    for sequence, call in enumerate(calls):
        if not isinstance(call, Mapping) or call.get("sequence") != sequence:
            raise N7SweepError("predecessor live request sequence numbering differs")
        observed.append((call.get("method"), call.get("endpoint")))
    if observed[:5] != expected_prefix:
        raise N7SweepError("predecessor live request preflight/POST sequence differs")
    if observed[-2:] != [
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
    ]:
        raise N7SweepError("predecessor live request final evidence sequence differs")
    if any(call != ("GET", "/api/job") for call in observed[5:-2]):
        raise N7SweepError("predecessor live request audit contains a disallowed call")


def _validate_final_result(
    path: Path, snapshot: CampaignSnapshot, expected_frequency_hz: int
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    final, final_payload = _load_canonical_json_file(path, "predecessor final result")
    if final.get("schema_version") != 1 or final.get("kind") != FINAL_RESULT_KIND:
        raise N7SweepError("predecessor final result kind/schema is invalid")
    if final.get("outcome") != "pass" or final.get("hardware_tested") is not True:
        raise N7SweepError("predecessor final result is not PASS")
    if final.get("frequency_hz") != expected_frequency_hz:
        raise N7SweepError("predecessor final result frequency differs")
    if final.get("campaign_file_sha256") != snapshot.campaign_file_sha256:
        raise N7SweepError("predecessor final result campaign differs")
    if final.get("firmware_sha256") != snapshot.firmware_sha256:
        raise N7SweepError("predecessor final result firmware differs")
    live_ref = final.get("live_result")
    if not isinstance(live_ref, Mapping) or set(live_ref) != {"filename", "sha256"}:
        raise N7SweepError("predecessor final result live reference is invalid")
    filename = live_ref.get("filename")
    if filename != LIVE_RESULT_FILENAME:
        raise N7SweepError("predecessor final result references an unexpected live filename")
    live_path = path.parent / filename
    live, live_payload = _load_canonical_json_file(live_path, "predecessor live result")
    if _sha256(live_payload) != _require_sha256(live_ref.get("sha256"), "live result SHA-256"):
        raise N7SweepError("predecessor live result SHA-256 differs")
    _validate_live_result(live, snapshot, expected_frequency_hz)
    if (
        final.get("action_identity_sha256") != live.get("action_identity_sha256")
        or final.get("authorization_claim") != live.get("authorization_claim")
    ):
        raise N7SweepError("predecessor final/live action binding differs")
    plan = final.get("sweep_plan")
    analysis = final.get("analysis")
    if not isinstance(plan, Mapping) or not isinstance(analysis, Mapping):
        raise N7SweepError("predecessor final result lacks analyzer evidence")
    try:
        recomputed = analyzer.analyze_document(plan)
    except analyzer.RefreshAnalysisError as error:
        raise N7SweepError(f"predecessor sweep plan is invalid: {error}") from error
    if analysis != recomputed:
        raise N7SweepError("predecessor analyzer result changed")
    current_rows = [
        row for row in recomputed["results"] if row["spi_hz"] == expected_frequency_hz
    ]
    if (
        len(current_rows) != 1
        or current_rows[0]["status"] != "PASS"
        or recomputed.get("highest_passed_hz") != expected_frequency_hz
    ):
        raise N7SweepError("predecessor analyzer row is not the highest PASS")
    if final.get("plan_sha256") != _sha256(_canonical(plan)):
        raise N7SweepError("predecessor sweep plan hash differs")
    if (
        final.get("next_frequency_authorized") is not True
        or final.get("automatic_retry_authorized") is not False
        or final.get("automatic_recovery_authorized") is not False
    ):
        raise N7SweepError("predecessor final safety flags differ")
    evidence = final.get("manual_and_scope_evidence")
    current_runs = [run for run in plan["runs"] if run.get("spi_hz") == expected_frequency_hz]
    if not isinstance(evidence, Mapping) or len(current_runs) != 1:
        raise N7SweepError("predecessor final evidence is incomplete")
    current_run = current_runs[0]
    evidence_pairs = {
        "serial_log_sha256": "serial_log_raw_sha256",
        "scope_evidence_sha256": "scope_evidence_sha256",
        "timing_evidence_sha256": "timing_evidence_sha256",
        "measured_sclk_hz": "measured_sclk_hz",
        "power_off_s": "power_off_s",
        "supply_voltage_v": "supply_voltage_v",
        "current_limit_a": "current_limit_a",
        "peak_current_a": "peak_current_a",
        "max_temperature_c": "max_temperature_c",
        "visual_pass": "visual_pass",
        "cv_pass": "cv_pass",
        "thermal_pass": "thermal_pass",
        "acoustic_pass": "acoustic_pass",
        "notes": "notes",
    }
    if any(evidence.get(left) != current_run.get(right) for left, right in evidence_pairs.items()):
        raise N7SweepError("predecessor final evidence summary differs from its analyzer row")
    del final_payload
    return final, live


def _load_predecessor(
    snapshot: CampaignSnapshot,
    frequency_hz: int,
    predecessor_result: Optional[Path],
) -> Predecessor:
    index = campaign.FREQUENCIES.index(frequency_hz)
    if index == 0:
        if predecessor_result is not None:
            raise N7SweepError("1 MHz action must not provide a predecessor result")
        return Predecessor(None, None, None, None, analyzer.build_plan(False))
    if predecessor_result is None:
        raise N7SweepError("higher frequencies require the previous PASS result")
    expected_frequency = campaign.FREQUENCIES[index - 1]
    final, live = _validate_final_result(
        predecessor_result, snapshot, expected_frequency
    )
    payload = _read_regular(predecessor_result, "predecessor final result")
    return Predecessor(
        predecessor_result,
        _sha256(payload),
        deepcopy(final),
        deepcopy(live),
        deepcopy(final["sweep_plan"]),
    )


def _authorization(frequency_hz: int, action_sha256: str) -> str:
    mhz = frequency_hz // 1_000_000
    return (
        f"{AUTHORIZATION_PREFIX}_{mhz}MHZ__ACTION_{action_sha256.upper()}"
        "__NO_RETRY_NO_RECOVERY"
    )


def build_action_contract(
    campaign_dir: Path,
    frequency_hz: int,
    *,
    predecessor_result: Optional[Path] = None,
) -> ActionContract:
    snapshot = _snapshot_campaign(campaign_dir)
    template = _action_template(snapshot, frequency_hz)
    predecessor = _load_predecessor(snapshot, frequency_hz, predecessor_result)
    if predecessor.final_document is None:
        predecessor_binding: Mapping[str, Any] = {
            "kind": "fresh-n7-firmware-boot",
            "expected_job_id": 0,
            "expected_operation_id": 0,
        }
    else:
        live = predecessor.live_document
        assert live is not None
        predecessor_binding = {
            "kind": "previous-frequency-pass-result",
            "frequency_hz": campaign.FREQUENCIES[
                campaign.FREQUENCIES.index(frequency_hz) - 1
            ],
            "final_result_file_sha256": predecessor.final_file_sha256,
            "final_result_plan_sha256": predecessor.final_document["plan_sha256"],
            "previous_action_identity_sha256": live["action_identity_sha256"],
            "previous_job_id": live["target_job"]["job_id"],
            "previous_operation_id": live["target_diagnostic"]["operation_id"],
            "esp32_reboot_forbidden": True,
        }
    identity = {
        "schema_version": 1,
        "kind": "mf1750-n7-spi-sweep-action-identity",
        "campaign_id": campaign.CAMPAIGN_ID,
        "campaign_file_sha256": snapshot.campaign_file_sha256,
        "firmware_sha256": snapshot.firmware_sha256,
        "firmware_build_tag": campaign.FIRMWARE_BUILD_TAG,
        "driver_api_version": campaign.DRIVER_API_VERSION,
        "action_template": template,
        "predecessor": predecessor_binding,
        "claim_scope": {
            "registry_id": CLAIM_REGISTRY_ID,
            "workspace_global": True,
            "single_use": True,
        },
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    action_sha = _sha256(_canonical(identity))
    return ActionContract(
        snapshot,
        template,
        predecessor,
        identity,
        action_sha,
        _authorization(frequency_hz, action_sha),
    )


def describe_action(
    campaign_dir: Path,
    frequency_hz: int,
    *,
    predecessor_result: Optional[Path] = None,
) -> Mapping[str, Any]:
    contract = build_action_contract(
        campaign_dir, frequency_hz, predecessor_result=predecessor_result
    )
    return {
        "schema_version": 1,
        "kind": "mf1750-n7-spi-sweep-action-description",
        "campaign_file_sha256": contract.snapshot.campaign_file_sha256,
        "frequency_hz": frequency_hz,
        "endpoint": contract.template["endpoint"],
        "action_identity": deepcopy(contract.identity),
        "action_identity_sha256": contract.identity_sha256,
        "required_authorization_confirmation": contract.authorization_confirmation,
        "claim_created": False,
        "device_io_performed": False,
        "execution_authorized": False,
        "hardware_tested": False,
    }


def _claim_registry() -> Path:
    registry = DEFAULT_AUTHORIZATION_REGISTRY
    if registry.is_symlink():
        raise N7SweepError("N7 authorization registry must not be a symlink")
    try:
        registry.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise N7SweepError(f"cannot create N7 authorization registry: {error}") from error
    if not registry.is_dir():
        raise N7SweepError("N7 authorization registry must be a directory")
    return registry


def _validate_claim_reference(
    reference: Mapping[str, Any],
    *,
    snapshot: CampaignSnapshot,
    action_identity_sha256: str,
    frequency_hz: int,
    endpoint: str,
) -> None:
    registry = DEFAULT_AUTHORIZATION_REGISTRY
    if registry.is_symlink() or not registry.is_dir():
        raise N7SweepError("N7 workspace-global claim registry is unavailable")
    expected_filename = f"{action_identity_sha256}.json"
    if reference.get("filename") != expected_filename:
        raise N7SweepError("N7 claim filename differs from the action identity")
    claim_path = registry / expected_filename
    claim, payload = _load_canonical_json_file(claim_path, "N7 action claim")
    if _sha256(payload) != reference.get("sha256"):
        raise N7SweepError("N7 action claim SHA-256 differs")
    expected_keys = {
        "schema_version",
        "kind",
        "registry_id",
        "campaign_file_sha256",
        "action_identity_sha256",
        "authorization_confirmation_sha256",
        "frequency_hz",
        "endpoint",
        "claimed_at_utc",
        "state",
        "authorization_consumed_permanently",
        "maximum_visible_posts",
        "automatic_retry_authorized",
        "automatic_recovery_authorized",
    }
    if set(claim) != expected_keys:
        raise N7SweepError("N7 action claim fields differ")
    if (
        claim.get("schema_version") != 1
        or claim.get("kind") != CLAIM_KIND
        or claim.get("registry_id") != CLAIM_REGISTRY_ID
        or claim.get("campaign_file_sha256") != snapshot.campaign_file_sha256
        or claim.get("action_identity_sha256") != action_identity_sha256
        or claim.get("authorization_confirmation_sha256")
        != _sha256(_authorization(frequency_hz, action_identity_sha256).encode("ascii"))
        or claim.get("frequency_hz") != frequency_hz
        or claim.get("endpoint") != endpoint
        or not isinstance(claim.get("claimed_at_utc"), str)
        or not claim.get("claimed_at_utc").endswith("Z")
        or claim.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
        or claim.get("authorization_consumed_permanently") is not True
        or claim.get("maximum_visible_posts") != 1
        or claim.get("automatic_retry_authorized") is not False
        or claim.get("automatic_recovery_authorized") is not False
    ):
        raise N7SweepError("N7 action claim contract differs")


def _atomic_new(path: Path, payload: bytes, label: str) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError as error:
        raise N7SweepError(f"{label} already exists; refusing overwrite") from error
    except OSError as error:
        raise N7SweepError(f"cannot write {label}: {error}") from error


def _claim_action(contract: ActionContract, *, claimed_at_utc: str) -> Claim:
    registry = _claim_registry()
    filename = f"{contract.identity_sha256}.json"
    document = {
        "schema_version": 1,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "campaign_file_sha256": contract.snapshot.campaign_file_sha256,
        "action_identity_sha256": contract.identity_sha256,
        "authorization_confirmation_sha256": _sha256(
            contract.authorization_confirmation.encode("ascii")
        ),
        "frequency_hz": contract.template["frequency_hz"],
        "endpoint": contract.template["endpoint"],
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "maximum_visible_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = _canonical(document) + b"\n"
    path = registry / filename
    try:
        _atomic_new(path, payload, "N7 action claim")
    except N7SweepError as error:
        if path.exists():
            raise N7SweepUnknown(
                "this exact N7 action was already permanently consumed; do not retry"
            ) from error
        raise
    return Claim(path, _sha256(payload), document)


class _AuditedRequester:
    def __init__(self, requester: frame_tool.HttpRequester, action_endpoint: str) -> None:
        self.requester = requester
        self.action_endpoint = action_endpoint
        self.calls: list[dict[str, Any]] = []
        self.visible_posts = 0

    def __call__(
        self,
        base_url: str,
        endpoint: str,
        *,
        method: str = "GET",
        data: Optional[bytes] = None,
        timeout: float = 10.0,
    ) -> tuple[int, str]:
        allowed_gets = {
            "/api/version",
            "/api/job",
            "/api/diagnostic/report",
            "/api/diagnostic/status",
        }
        if method == "POST":
            if endpoint != self.action_endpoint or data not in (None, b""):
                raise N7SweepError("N7 requester blocked a non-frozen visible POST")
            self.visible_posts += 1
            if self.visible_posts != 1:
                raise N7SweepError("N7 requester blocked a second visible POST")
        elif method != "GET" or endpoint not in allowed_gets or data is not None:
            raise N7SweepError("N7 requester blocked a route outside the fixed allowlist")
        self.calls.append(
            {"sequence": len(self.calls), "method": method, "endpoint": endpoint}
        )
        return self.requester(
            base_url, endpoint, method=method, data=data, timeout=timeout
        )


def _request_json(
    requester: _AuditedRequester,
    base_url: str,
    endpoint: str,
    *,
    method: str = "GET",
    expected_status: int = 200,
    timeout: float = 20.0,
) -> Mapping[str, Any]:
    try:
        status, body = requester(
            base_url, endpoint, method=method, data=None, timeout=timeout
        )
    except N7SweepError:
        raise
    except Exception as error:
        raise N7SweepError(f"{method} {endpoint} failed: {error}") from error
    if status != expected_status:
        raise N7SweepError(
            f"{method} {endpoint} returned HTTP {status}; expected {expected_status}"
        )
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError) as error:
        raise N7SweepError(f"{method} {endpoint} returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise N7SweepError(f"{method} {endpoint} response must be an object")
    return value


def _version(
    requester: _AuditedRequester, base_url: str
) -> tuple[str, Mapping[str, str]]:
    try:
        status, body = requester(
            base_url, "/api/version", method="GET", data=None, timeout=10.0
        )
    except Exception as error:
        raise N7SweepError(f"GET /api/version failed: {error}") from error
    if status != 200:
        raise N7SweepError("N7 version preflight did not return HTTP 200")
    return body, _parse_version_body(body)


def _validate_job(
    value: Mapping[str, Any], *, expected_id: int, state: str, result: object
) -> None:
    expected_keys = {
        "job_id",
        "action",
        "state",
        "result",
        "queued_at_ms",
        "started_at_ms",
        "finished_at_ms",
        "frame_fnv1a",
    }
    if set(value) != expected_keys:
        raise N7SweepError("job fields differ from the fixed schema")
    if value.get("job_id") != expected_id:
        raise N7SweepError("job ID differs from the expected sequence")
    if value.get("state") != state or value.get("result") is not result:
        raise N7SweepError("job state/result differs")
    expected_action = "none" if expected_id == 0 else campaign.JOB_ACTION
    if value.get("action") != expected_action:
        raise N7SweepError("job action differs")
    expected_hash = 0 if expected_id == 0 else campaign.EXPECTED_FULL_FNV1A
    if value.get("frame_fnv1a") != expected_hash:
        raise N7SweepError("job frame hash differs")
    for key in ("queued_at_ms", "started_at_ms", "finished_at_ms"):
        _require_int(value.get(key), f"job.{key}")
    if state == "completed":
        queued = value["queued_at_ms"]
        started = value["started_at_ms"]
        finished = value["finished_at_ms"]
        if not (queued <= started <= finished):
            raise N7SweepError("job timestamps are not ordered")


def _validate_gpio(value: Mapping[str, Any], label: str) -> None:
    if set(value) != {"busy", "rst", "cs", "cs2"}:
        raise N7SweepError(f"{label} GPIO fields differ")
    if type(value.get("busy")) is not int or value.get("busy") not in (0, 1):
        raise N7SweepError(f"{label} BUSY must be an integer level")
    if any(type(value.get(pin)) is not int or value.get(pin) != 0 for pin in ("rst", "cs", "cs2")):
        raise N7SweepError(f"{label} RST/CS1/CS2 outputs are not all low")


def _validate_busy_trace(value: Mapping[str, Any]) -> None:
    wait_ms = {
        "pon": _require_int(value.get("pon_ms"), "diagnostic.pon_ms"),
        "drf": _require_int(value.get("drf_ms"), "diagnostic.drf_ms"),
        "pof": _require_int(value.get("pof_ms"), "diagnostic.pof_ms"),
        "post_psr": _require_int(
            value.get("post_psr_ms"), "diagnostic.post_psr_ms"
        ),
    }
    try:
        normalized = frame_tool._validate_busy_trace(value, wait_ms)
    except frame_tool.FrameToolError as error:
        raise N7SweepError(f"diagnostic BUSY trace differs: {error}") from error
    if (
        normalized.get("schema_version") != 1
        or normalized.get("command_edge_contract_verified") is not True
        or normalized.get("safe_finish_pin_levels_verified") is not True
        or normalized.get("busy_after_rst_low_is_informational") is not True
    ):
        raise N7SweepError("diagnostic BUSY trace contract is not verified")
    _validate_gpio(normalized["final_gpio"], "diagnostic final")


def _validate_diagnostic(
    value: Mapping[str, Any], *, frequency_hz: int, job: Mapping[str, Any], operation_id: int
) -> None:
    required = {
        "schema_version": 2,
        "firmware_build_tag": campaign.FIRMWARE_BUILD_TAG,
        "driver_api_version": campaign.DRIVER_API_VERSION,
        "job_id": job["job_id"],
        "job_action": campaign.JOB_ACTION,
        "job_state": "completed",
        "job_result": True,
        "job_operation_id": operation_id,
        "operation_id": operation_id,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_assert_grace_ms": 250,
        "busy_missing_stage": "none",
        "pre_command_idle_failure": False,
        "pre_command_busy_stage": "none",
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "spi_hz": frequency_hz,
        "input_fnv1a": campaign.EXPECTED_FULL_FNV1A,
        "cs1_dtm_fnv1a": campaign.EXPECTED_CS1_FNV1A,
        "cs2_dtm_fnv1a": campaign.EXPECTED_CS2_FNV1A,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "busy_trace_schema_version": 1,
    }
    for key, item in required.items():
        if value.get(key) is not item and value.get(key) != item:
            raise N7SweepError(f"diagnostic field {key!r} differs")
    for key in (
        "job_queued_at_ms",
        "job_started_at_ms",
        "job_finished_at_ms",
        "total_ms",
        "cs1_upload_ms",
        "cs2_upload_ms",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
        "last_wait_ms",
    ):
        _require_int(value.get(key), f"diagnostic.{key}")
    if (
        value["job_queued_at_ms"] != job["queued_at_ms"]
        or value["job_started_at_ms"] != job["started_at_ms"]
        or value["job_finished_at_ms"] != job["finished_at_ms"]
    ):
        raise N7SweepError("diagnostic/job timestamps differ")
    expected_mapping = {
        "cs1_source_half": 0,
        "cs1_flip_x": False,
        "cs1_flip_y": False,
        "cs1_nibble_swap": False,
        "cs2_source_half": 1,
        "cs2_flip_x": False,
        "cs2_flip_y": False,
        "cs2_nibble_swap": False,
    }
    if value.get("mapping") != expected_mapping:
        raise N7SweepError("diagnostic mapping differs")
    _validate_busy_trace(value)


def _prepare_result_destination(destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise N7SweepError("result directory must not already exist")
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise N7SweepError("result parent must be an existing non-symlink directory")


def _create_attempt_directory(
    destination: Path, contract: ActionContract, claim: Claim, created_at_utc: str
) -> None:
    try:
        destination.mkdir(parents=False, exist_ok=False)
    except OSError as error:
        raise N7SweepUnknown(
            f"claim consumed but result directory could not be created: {error}"
        ) from error
    lock = {
        "schema_version": 1,
        "kind": "mf1750-n7-spi-sweep-attempt-lock",
        "created_at_utc": created_at_utc,
        "state": "visible_action_may_have_been_attempted_do_not_rerun",
        "action_identity_sha256": contract.identity_sha256,
        "authorization_claim": claim.reference(),
        "maximum_visible_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    _atomic_new(
        destination / ATTEMPT_LOCK_FILENAME,
        _canonical(lock) + b"\n",
        "N7 attempt lock",
    )


def _write_live_result(destination: Path, document: Mapping[str, Any]) -> Path:
    path = destination / LIVE_RESULT_FILENAME
    _atomic_new(path, _canonical(document) + b"\n", "N7 live result")
    return path


def _run_n7_sweep_once_legacy_test_only(
    campaign_dir: Path,
    frequency_hz: int,
    result_dir: Path,
    *,
    base_url: str,
    authorized_campaign_sha256: str,
    confirmation: str,
    predecessor_result: Optional[Path] = None,
    confirm_n7_firmware_flashed: bool = False,
    confirm_panel_power_off_at_least_10s: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_scope_capture_armed: bool = False,
    confirm_single_visible_action: bool = False,
    confirm_esp32_not_rebooted: bool = False,
    requester: Optional[frame_tool.HttpRequester] = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
) -> Mapping[str, Any]:
    """Exercise the pre-production protocol path in isolated unit tests only."""

    contract = build_action_contract(
        campaign_dir, frequency_hz, predecessor_result=predecessor_result
    )
    _require_sha256(authorized_campaign_sha256, "authorized campaign SHA-256")
    if authorized_campaign_sha256 != contract.snapshot.campaign_file_sha256:
        raise N7SweepError("authorized campaign SHA-256 differs from campaign.json")
    if confirmation != contract.authorization_confirmation:
        raise N7SweepError("authorization confirmation differs from the exact N7 action")
    required_confirmations = {
        "n7_firmware_flashed": confirm_n7_firmware_flashed,
        "panel_power_off_at_least_10s": confirm_panel_power_off_at_least_10s,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "scope_capture_armed": confirm_scope_capture_armed,
        "single_visible_action": confirm_single_visible_action,
    }
    if any(type(value) is not bool or not value for value in required_confirmations.values()):
        raise N7SweepError("all N7 supervised safety confirmations are required")
    if frequency_hz != campaign.FREQUENCIES[0] and confirm_esp32_not_rebooted is not True:
        raise N7SweepError("higher frequencies require confirmation that ESP32 did not reboot")
    if isinstance(job_timeout_s, bool) or not isinstance(job_timeout_s, (int, float)):
        raise N7SweepError("job_timeout_s must be a positive finite number")
    if not math.isfinite(float(job_timeout_s)) or float(job_timeout_s) <= 0:
        raise N7SweepError("job_timeout_s must be a positive finite number")
    try:
        normalized_url = frame_tool._normalize_base_url(base_url)
    except frame_tool.FrameToolError as error:
        raise N7SweepError(str(error)) from error
    _prepare_result_destination(result_dir)

    created_at = _utc_now()
    claim = _claim_action(contract, claimed_at_utc=created_at)
    _create_attempt_directory(result_dir, contract, claim, created_at)
    audited = _AuditedRequester(requester or frame_tool.http_request, contract.template["endpoint"])
    evidence: dict[str, Any] = {}
    try:
        version_raw, version_fields = _version(audited, normalized_url)
        evidence["version_raw"] = version_raw
        evidence["version_fields"] = dict(version_fields)
        prior_job = _request_json(audited, normalized_url, "/api/job")
        prior_report = _request_json(
            audited, normalized_url, "/api/diagnostic/report"
        )
        prior_gpio = _request_json(
            audited, normalized_url, "/api/diagnostic/status"
        )
        _validate_gpio(prior_gpio, "pre-action")
        if contract.predecessor.live_document is None:
            _validate_job(prior_job, expected_id=0, state="idle", result=None)
            if prior_report != {
                "schema_version": 2,
                "valid": False,
                "error": "no_completed_job_report",
            }:
                raise N7SweepError("fresh N7 boot has unexpected prior diagnostic")
            prior_operation_id = 0
        else:
            expected_live = contract.predecessor.live_document
            assert expected_live is not None
            if prior_job != expected_live["target_job"]:
                raise N7SweepError("live prior job differs from predecessor PASS result")
            if prior_report != expected_live["target_diagnostic"]:
                raise N7SweepError(
                    "live prior diagnostic differs from predecessor PASS result"
                )
            prior_operation_id = expected_live["target_diagnostic"]["operation_id"]
        evidence["prior_job"] = deepcopy(prior_job)
        evidence["prior_diagnostic"] = deepcopy(prior_report)
        evidence["prior_gpio"] = deepcopy(prior_gpio)

        queued_response = _request_json(
            audited,
            normalized_url,
            contract.template["endpoint"],
            method="POST",
            expected_status=202,
        )
        if set(queued_response) != {"ok", "job"} or queued_response.get("ok") is not True:
            raise N7SweepError("N7 enqueue response fields differ")
        queued_job = queued_response.get("job")
        if not isinstance(queued_job, Mapping):
            raise N7SweepError("N7 enqueue response lacks job object")
        expected_job_id = (int(prior_job["job_id"]) + 1) & 0xFFFFFFFF
        if expected_job_id == 0:
            expected_job_id = 1
        _validate_job(
            queued_job, expected_id=expected_job_id, state="queued", result=None
        )
        evidence["queued_response"] = deepcopy(queued_response)

        deadline = clock() + float(job_timeout_s)
        final_job: Optional[Mapping[str, Any]] = None
        while clock() < deadline:
            observed = _request_json(audited, normalized_url, "/api/job")
            state = observed.get("state")
            if state == "completed":
                _validate_job(
                    observed,
                    expected_id=expected_job_id,
                    state="completed",
                    result=True,
                )
                final_job = observed
                break
            if state not in {"queued", "running"}:
                raise N7SweepError("N7 job reached a non-success terminal state")
            sleeper(0.25)
        if final_job is None:
            raise N7SweepError("N7 job did not complete before the fixed deadline")
        target_diagnostic = _request_json(
            audited, normalized_url, "/api/diagnostic/report"
        )
        expected_operation_id = (int(prior_operation_id) + 1) & 0xFFFFFFFF
        if expected_operation_id == 0:
            expected_operation_id = 1
        _validate_diagnostic(
            target_diagnostic,
            frequency_hz=frequency_hz,
            job=final_job,
            operation_id=expected_operation_id,
        )
        post_gpio = _request_json(
            audited, normalized_url, "/api/diagnostic/status"
        )
        _validate_gpio(post_gpio, "post-action")
        evidence["target_job"] = deepcopy(final_job)
        evidence["target_diagnostic"] = deepcopy(target_diagnostic)
        evidence["post_gpio"] = deepcopy(post_gpio)
        if audited.visible_posts != 1:
            raise N7SweepError("N7 request audit did not observe exactly one visible POST")

        result = {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "recorded_at_utc": _utc_now(),
            "outcome": "protocol_pass_pending_adjudication",
            "protocol_verified": True,
            "hardware_tested": False,
            "frequency_hz": frequency_hz,
            "campaign": {
                "campaign_id": campaign.CAMPAIGN_ID,
                "campaign_file_sha256": contract.snapshot.campaign_file_sha256,
                "firmware_sha256": contract.snapshot.firmware_sha256,
            },
            "action_identity": deepcopy(contract.identity),
            "action_identity_sha256": contract.identity_sha256,
            "authorization_claim": claim.reference(),
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "sweep_plan_before_action": deepcopy(contract.predecessor.sweep_plan),
            "prior_job": evidence["prior_job"],
            "prior_diagnostic": evidence["prior_diagnostic"],
            "prior_gpio": evidence["prior_gpio"],
            "version_raw": evidence["version_raw"],
            "version_fields": evidence["version_fields"],
            "queued_response": evidence["queued_response"],
            "target_job": evidence["target_job"],
            "target_diagnostic": evidence["target_diagnostic"],
            "post_gpio": evidence["post_gpio"],
            "request_audit": {
                "calls": deepcopy(audited.calls),
                "visible_post_count": audited.visible_posts,
                "visible_endpoint": contract.template["endpoint"],
                "retry_count": 0,
                "recovery_count": 0,
            },
            "next_frequency_authorized": False,
            "required_follow_up": "offline_analyzer_adjudication",
        }
        _write_live_result(result_dir, result)
        return result
    except Exception as error:
        if isinstance(error, N7SweepUnknown):
            failure = error
        else:
            failure = N7SweepUnknown(str(error))
        unknown = {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "recorded_at_utc": _utc_now(),
            "outcome": "unknown_do_not_retry",
            "protocol_verified": False,
            "hardware_tested": False,
            "frequency_hz": frequency_hz,
            "campaign": {
                "campaign_id": campaign.CAMPAIGN_ID,
                "campaign_file_sha256": contract.snapshot.campaign_file_sha256,
                "firmware_sha256": contract.snapshot.firmware_sha256,
            },
            "action_identity": deepcopy(contract.identity),
            "action_identity_sha256": contract.identity_sha256,
            "authorization_claim": claim.reference(),
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "available_evidence": deepcopy(evidence),
            "error": str(error),
            "request_audit": {
                "calls": deepcopy(audited.calls),
                "visible_post_count": audited.visible_posts,
                "retry_count": 0,
                "recovery_count": 0,
            },
            "next_frequency_authorized": False,
        }
        try:
            _write_live_result(result_dir, unknown)
        except N7SweepError as record_error:
            raise N7SweepUnknown(
                f"{failure}; live result could not be recorded ({record_error}); do not retry"
            ) from error
        raise failure from error


def run_n7_sweep_once(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
    """Reject the obsolete public live API before claim or network I/O."""

    del args, kwargs
    raise N7SweepError(LEGACY_LIVE_BLOCK_MESSAGE)


def finalize_n7_sweep_result(
    campaign_dir: Path,
    live_result_path: Path,
    serial_log_path: Path,
    scope_evidence_path: Path,
    *,
    measured_sclk_hz: float,
    power_off_s: float,
    supply_voltage_v: float,
    current_limit_a: float,
    peak_current_a: float,
    max_temperature_c: float,
    visual_pass: bool,
    cv_pass: bool,
    thermal_pass: bool,
    acoustic_pass: bool,
    timing_evidence_path: Optional[Path] = None,
    timing_pass: Optional[bool] = None,
    notes: str = "",
) -> Mapping[str, Any]:
    snapshot = _snapshot_campaign(campaign_dir)
    if live_result_path.name != LIVE_RESULT_FILENAME:
        raise N7SweepError("live result must use the frozen N7 filename")
    live, live_payload = _load_canonical_json_file(live_result_path, "N7 live result")
    frequency_hz = live.get("frequency_hz")
    if type(frequency_hz) is not int or frequency_hz not in campaign.FREQUENCIES:
        raise N7SweepError("live result frequency is invalid")
    _validate_live_result(live, snapshot, frequency_hz)
    serial_log = _read_regular(serial_log_path, "serial log")
    scope_evidence = _read_regular(scope_evidence_path, "scope evidence")
    timing_evidence = (
        _read_regular(timing_evidence_path, "timing evidence")
        if timing_evidence_path is not None
        else None
    )
    plan_before = live.get("sweep_plan_before_action")
    if not isinstance(plan_before, Mapping):
        raise N7SweepError("live result lacks the prior sweep plan")
    try:
        before_analysis = analyzer.analyze_document(plan_before)
        expected_next = before_analysis.get("next_frequency_hz")
        if expected_next != frequency_hz:
            raise N7SweepError(
                "live result frequency is not the next analyzer-approved frequency"
            )
        observation = analyzer.extract_observation(
            frequency_hz,
            serial_log,
            live["target_diagnostic"],
            live["target_job"],
            live["version_raw"].encode("utf-8"),
            scope_evidence,
            cold_start=True,
            power_off_s=power_off_s,
            supply_voltage_v=supply_voltage_v,
            current_limit_a=current_limit_a,
            peak_current_a=peak_current_a,
            max_temperature_c=max_temperature_c,
            measured_sclk_hz=measured_sclk_hz,
            sclk_pass=True,
            visual_pass=visual_pass,
            cv_pass=cv_pass,
            thermal_pass=thermal_pass,
            acoustic_pass=acoustic_pass,
            timing_evidence=timing_evidence,
            timing_pass=timing_pass,
            notes=notes,
        )
        populated = analyzer._replace_run(plan_before, observation)
        analysis = analyzer.analyze_document(populated)
    except analyzer.RefreshAnalysisError as error:
        raise N7SweepError(f"N7 analyzer rejected the evidence: {error}") from error
    rows = [row for row in analysis["results"] if row["spi_hz"] == frequency_hz]
    current_pass = (
        len(rows) == 1
        and rows[0]["status"] == "PASS"
        and analysis.get("highest_passed_hz") == frequency_hz
    )
    outcome = "pass" if current_pass else "fail_do_not_continue"
    final = {
        "schema_version": 1,
        "kind": FINAL_RESULT_KIND,
        "recorded_at_utc": _utc_now(),
        "outcome": outcome,
        "hardware_tested": True,
        "frequency_hz": frequency_hz,
        "campaign_file_sha256": snapshot.campaign_file_sha256,
        "firmware_sha256": snapshot.firmware_sha256,
        "action_identity_sha256": live["action_identity_sha256"],
        "authorization_claim": deepcopy(live["authorization_claim"]),
        "live_result": {
            "filename": live_result_path.name,
            "sha256": _sha256(live_payload),
        },
        "plan_sha256": _sha256(_canonical(populated)),
        "sweep_plan": populated,
        "analysis": analysis,
        "manual_and_scope_evidence": {
            "serial_log_sha256": _sha256(serial_log),
            "scope_evidence_sha256": _sha256(scope_evidence),
            "timing_evidence_sha256": (
                _sha256(timing_evidence) if timing_evidence is not None else None
            ),
            "measured_sclk_hz": measured_sclk_hz,
            "power_off_s": power_off_s,
            "supply_voltage_v": supply_voltage_v,
            "current_limit_a": current_limit_a,
            "peak_current_a": peak_current_a,
            "max_temperature_c": max_temperature_c,
            "visual_pass": visual_pass,
            "cv_pass": cv_pass,
            "thermal_pass": thermal_pass,
            "acoustic_pass": acoustic_pass,
            "notes": notes,
        },
        "next_frequency_authorized": current_pass,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    final_path = live_result_path.parent / FINAL_RESULT_FILENAME
    _atomic_new(final_path, _canonical(final) + b"\n", "N7 final result")
    return final


def _frequency(value: str) -> int:
    try:
        frequency = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("frequency must be an integer Hz") from error
    if frequency not in campaign.FREQUENCIES:
        raise argparse.ArgumentTypeError("frequency must be 1000000/2000000/4000000/8000000/10000000")
    return frequency


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    describe = subparsers.add_parser("describe")
    describe.add_argument("campaign_dir", type=Path)
    describe.add_argument("--frequency-hz", type=_frequency, required=True)
    describe.add_argument("--predecessor-result", type=Path)

    run = subparsers.add_parser("run")
    run.add_argument("campaign_dir", type=Path)
    run.add_argument("result_dir", type=Path)
    run.add_argument("--frequency-hz", type=_frequency, required=True)
    run.add_argument("--predecessor-result", type=Path)
    run.add_argument("--url", required=True)
    run.add_argument("--authorized-campaign-sha256", required=True)
    run.add_argument("--confirm", required=True)
    run.add_argument("--confirm-n7-firmware-flashed", action="store_true")
    run.add_argument("--confirm-panel-power-off-at-least-10s", action="store_true")
    run.add_argument("--confirm-supply-and-temperature-normal", action="store_true")
    run.add_argument("--confirm-scope-capture-armed", action="store_true")
    run.add_argument("--confirm-single-visible-action", action="store_true")
    run.add_argument("--confirm-esp32-not-rebooted", action="store_true")
    run.add_argument("--job-timeout", type=_positive_float, default=DEFAULT_JOB_TIMEOUT_S)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("campaign_dir", type=Path)
    finalize.add_argument("live_result", type=Path)
    finalize.add_argument("--serial-log", type=Path, required=True)
    finalize.add_argument("--scope-evidence", type=Path, required=True)
    finalize.add_argument("--timing-evidence", type=Path)
    finalize.add_argument("--measured-sclk-hz", type=_positive_float, required=True)
    finalize.add_argument("--power-off-s", type=_positive_float, required=True)
    finalize.add_argument("--supply-voltage-v", type=_positive_float, required=True)
    finalize.add_argument("--current-limit-a", type=_positive_float, required=True)
    finalize.add_argument("--peak-current-a", type=float, required=True)
    finalize.add_argument("--max-temperature-c", type=float, required=True)
    finalize.add_argument("--visual-pass", action=argparse.BooleanOptionalAction, required=True)
    finalize.add_argument("--cv-pass", action=argparse.BooleanOptionalAction, required=True)
    finalize.add_argument("--thermal-pass", action=argparse.BooleanOptionalAction, required=True)
    finalize.add_argument("--acoustic-pass", action=argparse.BooleanOptionalAction, required=True)
    finalize.add_argument("--timing-pass", action=argparse.BooleanOptionalAction)
    finalize.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "describe":
            result = describe_action(
                args.campaign_dir,
                args.frequency_hz,
                predecessor_result=args.predecessor_result,
            )
        elif args.command == "run":
            raise N7SweepError(LEGACY_LIVE_BLOCK_MESSAGE)
        else:
            result = finalize_n7_sweep_result(
                args.campaign_dir,
                args.live_result,
                args.serial_log,
                args.scope_evidence,
                measured_sclk_hz=args.measured_sclk_hz,
                power_off_s=args.power_off_s,
                supply_voltage_v=args.supply_voltage_v,
                current_limit_a=args.current_limit_a,
                peak_current_a=args.peak_current_a,
                max_temperature_c=args.max_temperature_c,
                visual_pass=args.visual_pass,
                cv_pass=args.cv_pass,
                thermal_pass=args.thermal_pass,
                acoustic_pass=args.acoustic_pass,
                timing_evidence_path=args.timing_evidence,
                timing_pass=args.timing_pass,
                notes=args.notes,
            )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        if args.command == "finalize" and result["outcome"] != "pass":
            return 1
        return 0
    except N7SweepUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N7SweepError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
